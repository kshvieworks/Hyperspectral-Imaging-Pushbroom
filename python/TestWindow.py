"""
Pushbroom HSI User Interface using PyQt
"""

import Utility_Pushbroom as util
import sys
import numpy as np

from PyQt6.QtCore import (Qt, QObject, QThread, pyqtSignal, pyqtSlot)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                             QDoubleSpinBox, QGroupBox, QFileDialog, QMessageBox)

import pyqtgraph as pg
from pylablib.devices import Thorlabs
from pecamerapy import Camera

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
        self.setWindowTitle("Image Processor")
        self.show()


class HSIWindow(QWidget):
    def __init__(self, parent):
        super(HSIWindow, self).__init__(parent)

    # Import Helper

        self.stage = None
        self.camera = None
        self.thread = None
        self.worker = None

    # Define Cube
        self.cube = None

    # Define Layouts
        PageLayout = QVBoxLayout()
        PreviewLayout =QHBoxLayout()
        ConfigLayout = QVBoxLayout()

        self.init_Layout(PageLayout, PreviewLayout, ConfigLayout)
        self.setLayout(PageLayout)

    def init_Layout(self, PageLayout, PreviewLayout, ConfigLayout):
        PageLayout.addLayout(PreviewLayout)
        PageLayout.addLayout(ConfigLayout)

        self.init_ConfigureTab(ConfigLayout)
        self.init_Preview(PreviewLayout)

        self.Config.ImagePath.connect(self.Preview.Load_Image)
        self.Config.stateChanged.connect(self.Preview.Update_Correction_State)

    def init_Preview(self, PreviewLayout):
        self.Preview = PreviewWidget()
        PreviewLayout.addWidget(self.Preview)

    def init_ConfigureTab(self, ConfigLayout):
        self.Config = ConfigWidget()
        ConfigLayout.addWidget(self.Config)


class ConfigWidget(QtWidgets.QWidget):
    ImagePath = pyqtSignal(str, str, str)
    stateChanged = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super(ConfigWidget, self).__init__(parent)

        self.DesignUtil = util.WidgetDesign()

        Layout = QtWidgets.QVBoxLayout()
        self.initUI(Layout)
        self.setLayout(Layout)

    def initUI(self, Layout):

        self.UI_Component()
        self.UI_Layout(Layout)
        self.EventProcess()

    def UI_Layout(self, Layout):

        # Layout.addLayout(self.DesignUtil.Layout_Widget((self.Interval_Prompt, self.Interval_Entry), 'Horizontal'))
        Layout.addLayout(self.DesignUtil.Layout_Widget((self.ImagePath_BTN, self.DarkPath_BTN, self.FlatPath_BTN), 'Horizontal'))
        Layout.addLayout(self.DesignUtil.Layout_Widget((self.ImagePath_Prompt, self.ImagePath_Label), 'Horizontal'))
        Layout.addLayout(self.DesignUtil.Layout_Widget((self.DarkPath_CheckBox, self.DarkPath_Label), 'Horizontal'))
        Layout.addLayout(self.DesignUtil.Layout_Widget((self.FlatPath_CheckBox, self.FlatPath_Label), 'Horizontal'))

    def UI_Component(self):

        ButtonSize = (100, 40)
        LabelSize = (150, 30)
        EntrySize = (200, 30)

        self.ImagePath_BTN = QtWidgets.QPushButton("Image Path")
        self.ImagePath_BTN.setFixedSize(*ButtonSize)

        self.DarkPath_BTN = QtWidgets.QPushButton("Dark Path")
        self.DarkPath_BTN.setFixedSize(*ButtonSize)

        self.FlatPath_BTN = QtWidgets.QPushButton("Flat Path")
        self.FlatPath_BTN.setFixedSize(*ButtonSize)

        self.ImagePath_Prompt = QtWidgets.QLabel("Image Path")
        self.ImagePath_Prompt.setFixedSize(*LabelSize)
        self.ImagePath_Label = QtWidgets.QLabel()

        self.DarkPath_CheckBox = QtWidgets.QCheckBox("Dark Path", self)
        self.DarkPath_CheckBox.toggled.connect(lambda checked: self.Checkbox_Event('Dark', checked, self.DarkPath_BTN))
        self.DarkPath_CheckBox.setChecked(True)
        self.DarkPath_Label = QtWidgets.QLabel()

        self.FlatPath_CheckBox = QtWidgets.QCheckBox("Flat Path", self)
        self.FlatPath_CheckBox.toggled.connect(lambda checked: self.Checkbox_Event('Flat', checked, self.FlatPath_BTN))
        self.FlatPath_CheckBox.setChecked(True)
        self.FlatPath_Label = QtWidgets.QLabel()

    def EventProcess(self):
        self.ImagePath_BTN.clicked.connect(lambda checked=False: self.PathConfig('Folder', self.ImagePath_Label))
        self.DarkPath_BTN.clicked.connect(lambda checked=False: self.PathConfig('File', self.DarkPath_Label, 'Dark'))
        self.FlatPath_BTN.clicked.connect(lambda checked=False: self.PathConfig('File', self.FlatPath_Label, 'Flat'))

    def PathConfig(self, filetype, label, imagetype = 'Image'):
        fpath = ""

        if filetype == 'Folder':
            fpath = util.WidgetFunction.Select_Path()
        elif filetype == 'File':
            fpath = util.WidgetFunction.Open_File()
        else:
            print('file type must be "Folder" or "File"')

        if fpath:
            label.setText((fpath[-30:]))

            self.ImagePath.emit(filetype, fpath, imagetype)

    def Checkbox_Event(self, imagetype, checked, btn):

        util.WidgetFunction.Checkbox_Toggle(checked, btn)
        self.stateChanged.emit(imagetype, checked)


class PreviewWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(PreviewWidget, self).__init__(parent)

        self.DesignUtil = util.WidgetDesign()
        self.CustomFunction = util.CustomFunction()

        PreviewLayout = QtWidgets.QVBoxLayout()
        self.initUI(PreviewLayout)
        self.setLayout(PreviewLayout)

        self.DarkImage, self.FlatImage, self.Image, self.Corrected_Image, self.Image_Folderpath = 0, 0, 0, 0, ""
        self.use_dark, self.use_flat = True, True
        self.is_playing = False
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.Update_Image)
        # self.VideoThread()

    def initUI(self, Layout):

        self.UI_Component()
        self.UI_Layout(Layout)
        self.EventProcess()

    def UI_Layout(self, Layout):

        # PreviewStackLayout = QtWidgets.QStackedLayout()
        # PreviewStackLayout.addWidget(self.PreviewLabel)
        self.PreviewLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        Layout.addWidget(self.PreviewLabel)
        Layout.addWidget(self.PauseResume_Button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        ContrastLayout = QtWidgets.QGridLayout()
        ContrastLayout.addWidget(QtWidgets.QLabel("Min:"), 0, 0)
        ContrastLayout.addWidget(self.vmin_slider, 0, 1)
        ContrastLayout.addWidget(self.vmin_spin, 0, 2)

        ContrastLayout.addWidget(QtWidgets.QLabel("Max:"), 1, 0)
        ContrastLayout.addWidget(self.vmax_slider, 1, 1)
        ContrastLayout.addWidget(self.vmax_spin, 1, 2)

        ContrastGroup = QtWidgets.QGroupBox("Contrast Control")
        ContrastGroup.setLayout(ContrastLayout)
        Layout.addWidget(ContrastGroup)

    def UI_Component(self):

        self.PreviewLabel = QtWidgets.QLabel("Waiting for Images ...")
        self.PreviewLabel.setMinimumSize(512, 512)
        self.PreviewLabel.setStyleSheet("border: 1px solid gray;")

        self.PauseResume_Button = QtWidgets.QPushButton()
        self.PauseResume_Button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))
        self.PauseResume_Button.setFixedSize(100, 40)

        # Colorbar
        max_12bit = 4095

        self.vmin_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.vmin_slider.setRange(0, max_12bit)
        self.vmin_slider.setValue(0)

        self.vmin_spin = QtWidgets.QSpinBox()
        self.vmin_spin.setRange(0, max_12bit)
        self.vmin_spin.setValue(0)

        self.vmax_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.vmax_slider.setRange(0, max_12bit)
        self.vmax_slider.setValue(max_12bit)

        self.vmax_spin = QtWidgets.QSpinBox()
        self.vmax_spin.setRange(0, max_12bit)
        self.vmax_spin.setValue(max_12bit)

    def EventProcess(self):
        self.PauseResume_Button.clicked.connect(lambda checked=False: self.VideoActiveControl(self.PauseResume_Button))

        self.vmin_slider.valueChanged.connect(self.vmin_spin.setValue)
        self.vmin_spin.valueChanged.connect(self.vmin_slider.setValue)

        self.vmax_slider.valueChanged.connect(self.vmax_spin.setValue)
        self.vmax_spin.valueChanged.connect(self.vmax_slider.setValue)

        self.vmin_slider.valueChanged.connect(self.Update_Display)
        self.vmax_slider.valueChanged.connect(self.Update_Display)

    def Update_Correction_State(self, imagetype, state):
        if imagetype == 'Dark':
            self.use_dark = state
        if imagetype == 'Flat':
            self.use_flat = state

        if (self.Image_Folderpath and not self.is_playing):
            self.Update_Image()


    # Parameters for Read_Image Call back function should be modified as value from user by entries.
    def Load_Image(self, identifier, path, imagetype):

        if identifier == 'File':
            if imagetype == 'Dark':
                self.DarkImage = util.CustomFunction.Read_Image(path, 'bin', np.uint16, (512, 512))

            elif imagetype == 'Flat':
                self.FlatImage = util.CustomFunction.Read_Image(path, 'bin', np.uint16, (512, 512))
            else:
                print("Image file must be Dark or Flat")
        elif identifier == 'Folder':
            if path:
                self.Image_Folderpath = path
                self.Update_Image()

    def Update_Image(self):

        self.Image = util.CustomFunction.Read_Image(self.Image_Folderpath, 'bin', np.uint16, (512, 512))
        dark = self.DarkImage if self.use_dark else 0
        flat = self.FlatImage if self.use_flat else 0
        self.Corrected_Image = self.Apply_Corrections(self.Image, dark, flat)
        self.Update_Display()

    @staticmethod
    def Apply_Corrections(Image, Dark = 0, Flat = 0):

        if Image is None or Image.size == 0:
            return

        Corrected_Image = Image.copy().astype(np.float64)
        Corrected_Image = Corrected_Image - Dark
        Corrected_Image = np.clip(Corrected_Image, -500, None)

        Corrected_Flat = Flat - Dark
        Corrected_Flat = np.clip(Corrected_Flat, -500, None)

        Flat_safe = np.where(Corrected_Flat == 0, 1, Corrected_Flat)
        Corrected_Image = np.average(Flat_safe) * Corrected_Image / Flat_safe
        return Corrected_Image

    def Update_Display(self):

        if self.Corrected_Image is None or self.Corrected_Image.size == 0:
            return

        vmin = self.vmin_slider.value()
        vmax = self.vmax_slider.value()

        if vmin >= vmax:
            vmin = vmax - 1

        pixmap = util.CustomFunction.cv2qt(self.Corrected_Image, vmin, vmax)
        if pixmap:
            self.PreviewLabel.setPixmap(pixmap)

    def VideoActiveControl(self, PauseResume_Button):
        if not self.is_playing:
            self.timer.start(100)
            self.is_playing = True
            PauseResume_Button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPause))

        else:
            self.timer.stop()
            self.is_playing = False
            PauseResume_Button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))



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

    app = QtWidgets.QApplication(sys.argv)
    window = App()
    app.exec()

