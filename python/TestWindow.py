"""
Pushbroom HSI User Interface using PyQt
"""
import pecamerapy

import Utility_Pushbroom
import Utility_Pyqt as Uqt

# import CameraControl as CC
import Utility_Pushbroom as UP

import sys
import numpy as np
import multiprocessing as mp
from queue import Empty

from PyQt6.QtCore import (Qt, QObject, pyqtSignal, pyqtSlot, QTimer)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QPushButton, QSlider,
                             QDoubleSpinBox, QComboBox, QSpinBox, QGroupBox, QFileDialog, QMessageBox, QLineEdit)
from qtrangeslider import QRangeSlider



import pyqtgraph as pg
from pylablib.devices import Thorlabs
from pecamerapy import Camera
from pecamerapy.include._pecamerapy import Metadata


import cv2

STEPS_PER_MM = 1_228_800
VELOCITY_SCALE = 65_961_984
ACCELERATION_SCALE = 13_584.249

WAVELENGTH_START_NM = 900.0
WAVELENGTH_END_NM = 1700.0


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.window = HSIWindow(self)
        self.setCentralWidget(self.window)
        self.setWindowTitle("SWIR Pushbroom HSI")
        self.show()


class HSIWindow(QWidget):
    def __init__(self, parent):
        super(HSIWindow, self).__init__(parent)

    # Import Helper
        self.stage = None

    # Camera Multiprocessing
        self.camera_process = None
        self.camera_frame_queue = None
        self.camera_status_queue = None
        self.camera_stop_event = None

        # self.thread = None
        # self.worker_camera = None
        self.Metadata = None

    # Preview Timer
        self.latest_camera_image = None
        self.camera_image_flag = False
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(100)
        self.preview_timer.timeout.connect(self.__Update_Camera_Preview)

        self.process_timer = QTimer(self)
        self.process_timer.setInterval(100)
        self.process_timer.timeout.connect(self.__Poll_Camera_Process)

    # Define Cube
        self.cube = None

    # Define Layouts
        PageLayout = QHBoxLayout()
        ConfigLayout = QVBoxLayout()
        PreviewLayout =QVBoxLayout()
        StatusLayout =QVBoxLayout()

        self.init_Layout(PageLayout, ConfigLayout, PreviewLayout, StatusLayout)
        self.setLayout(PageLayout)

    def init_Layout(self, PageLayout, ConfigLayout, PreviewLayout, StatusLayout):
        PageLayout.addLayout(ConfigLayout)
        PageLayout.addLayout(PreviewLayout)
        PageLayout.addLayout(StatusLayout)

        self.init_ConfigureTab(ConfigLayout)
        self.init_Preview(PreviewLayout)
        # self.init_StatusLayout(StatusLayout)
        self.EventProcess()

        # self.Config.ImagePath.connect(self.Preview.Load_Image)
        # self.Config.stateChanged.connect(self.Preview.Update_Correction_State)

    def init_ConfigureTab(self, ConfigLayout):
        self.Config = ConfigWidget()
        ConfigLayout.addWidget(self.Config)


    def init_Preview(self, PreviewLayout):
        self.ImagePreview = ImagePreviewWidgets()
        self.SpectrumPreview = SpectrumPreviewWidgets()
        PreviewLayout.addWidget(self.ImagePreview)
        PreviewLayout.addWidget(self.SpectrumPreview)

    def EventProcess(self):
        self.Config.camera_connect_requested.connect(self.Connect_Camera)
        self.Config.camera_disconnect_requested.connect(self.Disconnect_Camera)

    def Connect_Camera(self, serial):
        if (self.camera_process is not None and self.camera_process.is_alive()):
            return
        exposure = self.Config.Exposure_Spinbox.value()
        fps = self.Config.FPS_Spinbox.value()
        self.Config.Connection_Button.setEnabled(False)
        self.Config.Connection_Button.setText("Connecting...")
        self._Start_Camera_Process(serial = serial, exposure = exposure, fps = fps)

    def Disconnect_Camera(self):
        if self.camera_process is None:
            return
        if not self.camera_process.is_alive():
            self._Camera_Process_Finished()
            return
        self.Config.Connection_Button.setEnabled(False)
        self.Config.Connection_Button.setText("Disconnecting...")
        self.camera_stop_event.set()

    @pyqtSlot(str)
    def Camera_Error(self, message):
        QMessageBox.critical(self, "Camera Error", f"{message}")

    def _Camera_Process_Finished(self):
        self.preview_timer.stop()
        self.process_timer.stop()

        if self.camera_process is not None:
            self.camera_process.join(timeout=0)
            self.camera_process.close()
        self.camera_process = None
        self.camera_frame_queue = None
        self.camera_status_queue = None
        self.camera_stop_event = None
        self.Config.Connection_Button.setEnabled(True)
        self.Config.Connection_Button.setText("Now Disconnected. Click to Connect")

    def _Start_Camera_Process(self, serial, exposure, fps):
        ctx = mp.get_context('spawn')
        self.camera_frame_queue = ctx.Queue(maxsize=1)
        self.camera_status_queue = ctx.Queue()
        self.camera_stop_event = ctx.Event()

        self.camera_process = ctx.Process(target = UP.camera_process_main,
                                          args=(serial, exposure, fps, self.camera_frame_queue, self.camera_status_queue, self.camera_stop_event),
                                          daemon=True)
        self.camera_process.start()
        self.preview_timer.start()
        self.process_timer.start()


    @pyqtSlot()
    def __Update_Camera_Preview(self):
        if self.camera_frame_queue is None:
            return
        lastest_image = None
        try:
            while True:
                lastest_image = (self.camera_frame_queue.get_nowait())
        except Empty:
            pass
        if lastest_image is None:
            return

        self.ImagePreview.Update_Preview(lastest_image)

    @pyqtSlot()
    def __Poll_Camera_Process(self):
        if self.camera_status_queue is not None:
            try:
                while True:
                    status, message = (self.camera_status_queue.get_nowait())
                    if status == "connected":
                        self.Config.Connection_Button.setEnabled(True)
                        self.Config.Connection_Button.setText("Now Connected. Click to Disconnect")
                    elif status == "error":
                        QMessageBox.critical(self, "Camera Connection Error", message)
                    elif status == "disconnected":
                        pass
            except Empty:
                pass
        if (self.camera_process is not None and self.camera_process.is_alive()):
            self._Camera_Process_Finished()




    # @pyqtSlot(object)
    # def __Receive_Camera_Image(self, image):
    #     self.latest_camera_image = image

    # @pyqtSlot()
    # def __Update_Camera_Preview(self, image):
    #     if image is None:
    #         return
    #     self.ImagePreview.Update_Preview(self.image)

    def __SaveMetadata(self, metadata):
        self.Metadata = None

    # def init_StatusLayout(self, StatusLayout):
    #     self.Status = StatusWidget()
    #     StatusLayout.addWidget(self.Status)


class ConfigWidget(QWidget):
    camera_connect_requested = pyqtSignal(str)
    camera_disconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super(ConfigWidget, self).__init__(parent)

        Layout = QVBoxLayout()

        self.initUI(Layout)
        self.setLayout(Layout)

    def initUI(self, Layout):

        self.UI_Component()
        self.UI_Layout(Layout)
        self.EventProcess()

    def UI_Layout(self, Layout):

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Camera_Prompt, self.Camera_Combo), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Serial_Prompt, self.Serial_Entry), 'Horizontal'))
        Temp_Layout.addWidget(self.Connection_Button)
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Temperature_Prompt, self.Temperature_Spinbox), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Camera Settings')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Exposure_Prompt, self.Exposure_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.FPS_Prompt, self.FPS_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Trigger_Prompt, self.Trigger_Combo), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Acquisition Setting')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.ROI_Prompt, self.ROI_L_Spinbox, self.ROI_Slider, self.ROI_R_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.SpectrumY_Prompt, self.SpectrumY_Slider, self.SpectrumY_Spinbox), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Spectrum Settings')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Start_Prompt, self.Stage_Start_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_End_Prompt, self.Stage_End_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Steps_Prompt, self.Stage_Steps_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Speed_Prompt, self.Stage_Speed_Spinbox), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Stage Settings')

        # Layout.addLayout(self.DesignUtil.Layout_Widget((self.Interval_Prompt, self.Interval_Entry), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.ImagePath_BTN, self.DarkPath_BTN, self.FlatPath_BTN), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.ImagePath_Prompt, self.ImagePath_Label), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.DarkPath_CheckBox, self.DarkPath_Label), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.FlatPath_CheckBox, self.FlatPath_Label), 'Horizontal'))

    def UI_Component(self):

        ButtonSize = (100, 40)
        LabelSize = (150, 30)
        EntrySize = (200, 30)

    # UI for Camera Settings
        self.Camera_Prompt = QLabel("Camera Name")
        self.Camera_Prompt.setFixedSize(*LabelSize)
        self.Camera_Combo = QComboBox()
        self.Camera_Combo.addItem('Alize 1.7s')

        self.Serial_Prompt = QLabel("Serial Number")
        self.Serial_Prompt.setFixedSize(*LabelSize)
        self.Serial_Entry = QLineEdit()
        self.Serial_Entry.setFixedSize(*EntrySize)
        self.Serial_Entry.setPlaceholderText("Enter camera serial number")
        self.Serial_Entry.setText('CA000011038')

        self.Temperature_Prompt = QLabel("Sensor Temperature")
        self.Temperature_Prompt.setFixedSize(*LabelSize)
        self.Temperature_Spinbox = QSpinBox()
        self.Temperature_Spinbox.setRange(-60, 30)
        self.Temperature_Spinbox.setValue(0)
        self.Temperature_Spinbox.setSuffix(" °C")

        self.Connection_Button = QPushButton("Now Disconnected. Click to Connect")

    # UI for Acquisition Control

        self.Exposure_Prompt = QLabel("Exposure Time")
        self.Exposure_Prompt.setFixedSize(*LabelSize)
        self.Exposure_Spinbox = QDoubleSpinBox()
        self.Exposure_Spinbox.setRange(0.001, 10)
        self.Exposure_Spinbox.setValue(0.02)
        self.Exposure_Spinbox.setDecimals(3)
        self.Exposure_Spinbox.setSuffix(" s")

        self.FPS_Prompt = QLabel("Frame Rate")
        self.FPS_Prompt.setFixedSize(*LabelSize)
        self.FPS_Spinbox = QDoubleSpinBox()
        self.FPS_Spinbox.setValue(30)
        self.FPS_Spinbox.setRange(0.1, 1000)
        self.FPS_Spinbox.setSuffix(" fps")

        self.Trigger_Prompt = QLabel("Trigger Time")
        self.Trigger_Prompt.setFixedSize(*LabelSize)
        self.Trigger_Combo = QComboBox()
        self.Trigger_Combo.addItems(["Free Run", "Software", "External"])

    # UI for Preview Configuration
        self.ROI_Prompt = QLabel("ROI")
        self.ROI_Prompt.setFixedSize(*LabelSize)
        self.ROI_Slider = QRangeSlider(Qt.Orientation.Horizontal)
        self.ROI_Slider.setRange(0, 512)
        self.ROI_Slider.setValue((0, 512))
        self.ROI_Slider.setSingleStep(1)
        self.ROI_L_Spinbox = QSpinBox()
        self.ROI_L_Spinbox.setRange(0, 512)
        self.ROI_L_Spinbox.setValue(0)
        self.ROI_R_Spinbox = QSpinBox()
        self.ROI_R_Spinbox.setRange(0, 512)
        self.ROI_R_Spinbox.setValue(512)

        self.ROI_L_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(value, self.ROI_Slider.value()[1], self.ROI_Slider))
        self.ROI_R_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(self.ROI_Slider.value()[0], value, self.ROI_Slider))
        self.ROI_Slider.valueChanged.connect(lambda values: Uqt.SliderHelper.RangeSliderChanged(self.ROI_L_Spinbox, self.ROI_R_Spinbox, values))


        self.SpectrumY_Prompt = QLabel("Spectrum Position")
        self.SpectrumY_Prompt.setFixedSize(*LabelSize)
        self.SpectrumY_Spinbox = QSpinBox()
        self.SpectrumY_Spinbox.setRange(0, 512)
        self.SpectrumY_Spinbox.setValue(256)
        self.SpectrumY_Slider = QSlider(Qt.Orientation.Horizontal)
        self.SpectrumY_Slider.setRange(0, 512)
        self.SpectrumY_Slider.setSingleStep(1)
        self.SpectrumY_Slider.setValue(256)

        self.SpectrumY_Slider.valueChanged.connect(self.SpectrumY_Spinbox.setValue)
        self.SpectrumY_Spinbox.valueChanged.connect(self.SpectrumY_Slider.setValue)

        self.Stage_Start_Prompt = QLabel("Start Position")
        self.Stage_Start_Prompt.setFixedSize(*LabelSize)
        self.Stage_Start_Spinbox = QDoubleSpinBox()
        self.Stage_Start_Spinbox.setRange(0, 50)
        self.Stage_Start_Spinbox.setValue(10)
        self.Stage_Start_Spinbox.setSuffix(" mm")

        self.Stage_End_Prompt = QLabel("End Position")
        self.Stage_End_Prompt.setFixedSize(*LabelSize)
        self.Stage_End_Spinbox = QDoubleSpinBox()
        self.Stage_End_Spinbox.setRange(0, 50)
        self.Stage_End_Spinbox.setValue(30)
        self.Stage_End_Spinbox.setSuffix(" mm")

        self.Stage_Steps_Prompt = QLabel("Steps")
        self.Stage_Steps_Prompt.setFixedSize(*LabelSize)
        self.Stage_Steps_Spinbox = QDoubleSpinBox()
        self.Stage_Steps_Spinbox.setRange(0, 50)
        self.Stage_Steps_Spinbox.setValue(0.1)
        self.Stage_Steps_Spinbox.setSuffix(" mm")

        self.Stage_Speed_Prompt = QLabel("Speed")
        self.Stage_Speed_Prompt.setFixedSize(*LabelSize)
        self.Stage_Speed_Spinbox = QDoubleSpinBox()
        self.Stage_Speed_Spinbox.setRange(1E-3, 5)
        self.Stage_Speed_Spinbox.setValue(0.1)
        self.Stage_Speed_Spinbox.setSuffix(" mm/s")

    def EventProcess(self):
        self.Connection_Button.clicked.connect(self.CameraConnection_Event)

    def CameraConnection_Event(self):
        if self.Connection_Button.text() == "Now Disconnected. Click to Connect":
            serial = self.Serial_Entry.text().strip()

            if not serial:
                QMessageBox.warning(self, "Error", "Please enter a serial number.")
                return

            self.camera_connect_requested.emit(serial)
        else:
            self.camera_disconnect_requested.emit()


class ImagePreviewWidgets(QWidget):
    def __init__(self, parent=None):
        super(ImagePreviewWidgets, self).__init__(parent)

        Layout = QVBoxLayout()

        self.current_image = None

        self.initUI(Layout)
        self.setLayout(Layout)


    def initUI(self, Layout):

        self.UI_Component()
        self.UI_Layout(Layout)
        self.EventProcess()

    def UI_Layout(self, Layout):

        self.PreviewLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        Layout.addWidget(self.PreviewLabel)
        Layout.addWidget(self.ColorRange_Slider)

    def UI_Component(self):

        self.PreviewLabel = QLabel()
        self.PreviewLabel.setMinimumSize(512, 640)
        self.PreviewLabel.setScaledContents(False)
        self.PreviewLabel.setStyleSheet("border: 1px solid gray;")

        self.ColorRange_Slider = QRangeSlider(Qt.Orientation.Horizontal)
        self.ColorRange_Slider.setRange(0, 2**16-1)
        self.ColorRange_Slider.setValue((0, 2**16-1))
        self.ColorRange_Slider.setSingleStep(1)

    def EventProcess(self):
        self.ColorRange_Slider.valueChanged.connect(self.Update_Display)


    def Update_Preview(self, Image):

        if Image is None or Image.size == 0:
            return

        self.current_image = Image
        self.Update_Display()

    def Update_Display(self):
        if self.current_image is None:
            return
        vmin, vmax = self.ColorRange_Slider.value()
        pixmap = Uqt.CustomFunction.cv2qt(self.current_image, vmin, vmax)
        if pixmap:
            self.PreviewLabel.setPixmap(pixmap)


class SpectrumPreviewWidgets(QWidget):
    def __init__(self, parent=None):
        super(SpectrumPreviewWidgets, self).__init__(parent)

        Layout = QVBoxLayout()
        self.initUI(Layout)
        self.setLayout(Layout)

    def initUI(self, Layout):
        self.UI_Component()
        self.UI_Layout(Layout)
        # self.EventProcess()

    def UI_Layout(self, Layout):
        Layout.addWidget(self.plot)

    def UI_Component(self):
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Wavelength", units="nm")
        self.plot.setLabel("left", "Intensity", units="DN")
        self.plot.showGrid(x=True, y=True)
        self.curve = self.plot.plot()

    def set_spectrum(self, wavelength, intensity):
        self.curve.setData(wavelength, intensity)


# class PreviewWidget(QtWidgets.QWidget):
#     def __init__(self, parent=None):
#         super(PreviewWidget, self).__init__(parent)
#
#         self.DesignUtil = util.WidgetDesign()
#         self.CustomFunction = util.CustomFunction()
#
#         PreviewLayout = QtWidgets.QVBoxLayout()
#         self.initUI(PreviewLayout)
#         self.setLayout(PreviewLayout)
#
#         self.DarkImage, self.FlatImage, self.Image, self.Corrected_Image, self.Image_Folderpath = 0, 0, 0, 0, ""
#         self.use_dark, self.use_flat = True, True
#         self.is_playing = False
#         self.timer = QtCore.QTimer(self)
#         self.timer.timeout.connect(self.Update_Image)
#         # self.VideoThread()
#
#     def initUI(self, Layout):
#
#         self.UI_Component()
#         self.UI_Layout(Layout)
#         self.EventProcess()
#
#     def UI_Layout(self, Layout):
#
#         # PreviewStackLayout = QtWidgets.QStackedLayout()
#         # PreviewStackLayout.addWidget(self.PreviewLabel)
#         self.PreviewLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
#         Layout.addWidget(self.PreviewLabel)
#         Layout.addWidget(self.PauseResume_Button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
#
#         ContrastLayout = QtWidgets.QGridLayout()
#         ContrastLayout.addWidget(QtWidgets.QLabel("Min:"), 0, 0)
#         ContrastLayout.addWidget(self.vmin_slider, 0, 1)
#         ContrastLayout.addWidget(self.vmin_spin, 0, 2)
#
#         ContrastLayout.addWidget(QtWidgets.QLabel("Max:"), 1, 0)
#         ContrastLayout.addWidget(self.vmax_slider, 1, 1)
#         ContrastLayout.addWidget(self.vmax_spin, 1, 2)
#
#         ContrastGroup = QtWidgets.QGroupBox("Contrast Control")
#         ContrastGroup.setLayout(ContrastLayout)
#         Layout.addWidget(ContrastGroup)
#
#     def UI_Component(self):
#
#         self.PreviewLabel = QtWidgets.QLabel("Waiting for Images ...")
#         self.PreviewLabel.setMinimumSize(512, 512)
#         self.PreviewLabel.setStyleSheet("border: 1px solid gray;")
#
#
#         # Colorbar
#         max_12bit = 4095
#
#         self.vmin_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
#         self.vmin_slider.setRange(0, max_12bit)
#         self.vmin_slider.setValue(0)
#
#         self.vmin_spin = QtWidgets.QSpinBox()
#         self.vmin_spin.setRange(0, max_12bit)
#         self.vmin_spin.setValue(0)
#
#         self.vmax_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
#         self.vmax_slider.setRange(0, max_12bit)
#         self.vmax_slider.setValue(max_12bit)
#
#         self.vmax_spin = QtWidgets.QSpinBox()
#         self.vmax_spin.setRange(0, max_12bit)
#         self.vmax_spin.setValue(max_12bit)
#
#     def EventProcess(self):
#         self.PauseResume_Button.clicked.connect(lambda checked=False: self.VideoActiveControl(self.PauseResume_Button))
#
#         self.vmin_slider.valueChanged.connect(self.vmin_spin.setValue)
#         self.vmin_spin.valueChanged.connect(self.vmin_slider.setValue)
#
#         self.vmax_slider.valueChanged.connect(self.vmax_spin.setValue)
#         self.vmax_spin.valueChanged.connect(self.vmax_slider.setValue)
#
#         self.vmin_slider.valueChanged.connect(self.Update_Display)
#         self.vmax_slider.valueChanged.connect(self.Update_Display)
#
#     def Update_Correction_State(self, imagetype, state):
#         if imagetype == 'Dark':
#             self.use_dark = state
#         if imagetype == 'Flat':
#             self.use_flat = state
#
#         if (self.Image_Folderpath and not self.is_playing):
#             self.Update_Image()
#
#
#     # Parameters for Read_Image Call back function should be modified as value from user by entries.
#     def Load_Image(self, identifier, path, imagetype):
#
#         if identifier == 'File':
#             if imagetype == 'Dark':
#                 self.DarkImage = util.CustomFunction.Read_Image(path, 'bin', np.uint16, (512, 512))
#
#             elif imagetype == 'Flat':
#                 self.FlatImage = util.CustomFunction.Read_Image(path, 'bin', np.uint16, (512, 512))
#             else:
#                 print("Image file must be Dark or Flat")
#         elif identifier == 'Folder':
#             if path:
#                 self.Image_Folderpath = path
#                 self.Update_Image()
#
#     def Update_Image(self):
#
#         self.Image = util.CustomFunction.Read_Image(self.Image_Folderpath, 'bin', np.uint16, (512, 512))
#         dark = self.DarkImage if self.use_dark else 0
#         flat = self.FlatImage if self.use_flat else 0
#         self.Corrected_Image = self.Apply_Corrections(self.Image, dark, flat)
#         self.Update_Display()
#
#     @staticmethod
#     def Apply_Corrections(Image, Dark = 0, Flat = 0):
#
#         if Image is None or Image.size == 0:
#             return
#
#         Corrected_Image = Image.copy().astype(np.float64)
#         Corrected_Image = Corrected_Image - Dark
#         Corrected_Image = np.clip(Corrected_Image, -500, None)
#
#         Corrected_Flat = Flat - Dark
#         Corrected_Flat = np.clip(Corrected_Flat, -500, None)
#
#         Flat_safe = np.where(Corrected_Flat == 0, 1, Corrected_Flat)
#         Corrected_Image = np.average(Flat_safe) * Corrected_Image / Flat_safe
#         return Corrected_Image
#
#     def Update_Display(self):
#
#         if self.Corrected_Image is None or self.Corrected_Image.size == 0:
#             return
#
#         vmin = self.vmin_slider.value()
#         vmax = self.vmax_slider.value()
#
#         if vmin >= vmax:
#             vmin = vmax - 1
#
#         pixmap = util.CustomFunction.cv2qt(self.Corrected_Image, vmin, vmax)
#         if pixmap:
#             self.PreviewLabel.setPixmap(pixmap)
#
#     def VideoActiveControl(self, PauseResume_Button):
#         if not self.is_playing:
#             self.timer.start(100)
#             self.is_playing = True
#             PauseResume_Button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPause))
#
#         else:
#             self.timer.stop()
#             self.is_playing = False
#             PauseResume_Button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))



    #
    # def VideoThread(self):
    #
    #     asdf = 1
    #     # self.Video = AP.getFrame()
    #     # QtCore.QCoreApplication.processEvents()
    #     # self.Video.FrameUpdate.connect(self.FrameUpdateSlot)
    #     # self.Video.start()
    #
    # def FrameUpdateSlot(self, Image):
    #     qtImage = self.CustomFunction.cv2qt(Image)
    #     self.PreviewLabel.setPixmap(qtImage)
    #
    # def VideoActiveControl(self, BTN):
    #     if self.Video.ThreadActive == False:
    #         BTN.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPause))
    #         self.Video.ThreadActive = True
    #         self.Video.start()
    #     else:
    #         BTN.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))
    #         self.Video.ThreadActive = False
    #         # self.AOAutoScanStatus = False



if __name__ == '__main__':
    mp.freeze_support()
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())

