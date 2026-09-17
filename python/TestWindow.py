"""
Pushbroom HSI User Interface using PyQt
"""
import os
os.environ["QT_API"] = "pyqt6"

import pecamerapy

import sys
import numpy as np
import multiprocessing as mp
from queue import Empty

from PyQt6.QtCore import (Qt, QObject, pyqtSignal, pyqtSlot, QTimer, QThread)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QPushButton, QSlider, QCheckBox,
                             QDoubleSpinBox, QComboBox, QSpinBox, QGroupBox, QFileDialog, QMessageBox, QLineEdit, QStyle)
from superqt import QRangeSlider

import pyqtgraph as pg
import Utility_Pyqt as Uqt
# import CameraControl as CC
import Utility_Pushbroom as UP
import shutil
import uuid
import psutil
from datetime import datetime

from pylablib.devices import Thorlabs
from pecamerapy import Camera
from pecamerapy.include._pecamerapy import Metadata
import cv2

STEPS_PER_MM = 1_228_800
VELOCITY_SCALE = 65_961_984
ACCELERATION_SCALE = 13_584.249


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
        self.camera_command_queue = None
        self.camera_stop_event = None

        # self.thread = None
        # self.worker_camera = None
        self.Metadata = None

    # Preview Timer
        self.latest_camera_image = None
        self.camera_image_flag = False
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(5)
        self.preview_timer.timeout.connect(self.__Update_Camera_Preview)

    # Process Timer
        self.process_timer = QTimer(self)
        self.process_timer.setInterval(100)
        self.process_timer.timeout.connect(self.__Poll_Camera_Process)

    # Stage Controller
        self.stage_thread = QThread(self)
        self.stage_worker = UP.StageWorker()
        self.stage_worker.moveToThread(self.stage_thread)
        self.stage_thread.finished.connect(self.stage_worker.deleteLater)
        self.stage_thread.start()

    # Cube Acquisition Process
        self.acquisition_process = None
        self.acquisition_frame_queue = None
        self.acquisition_status_queue = None
        self.acquisition_stop_event = None
        self.pending_scan = False
        self.pending_scan_params = None
        self.stage_connected = False

    # Acquisition Timer
        self.acquisition_timer = QTimer(self)
        self.acquisition_timer.setInterval(50)
        self.acquisition_timer.timeout.connect(self.__Poll_Acquisition_Process)

    # Define Cube
        self.cube = None
        self.cube_path = None
        self.live_cube = None
        self.live_band_image = None
        self.live_band_index = None
        self.live_band_lines = 0

    # Spectral Calibration
        self.calibration_enabled = False
        self.wavelength_range = None

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
        self.init_StatusLayout(StatusLayout)
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

    def init_StatusLayout(self, StatusLayout):
        self.Status = StatusWidgets()
        StatusLayout.addWidget(self.Status)

    def EventProcess(self):
        self.Config.camera_connect_requested.connect(self.Connect_Camera)
        self.Config.camera_disconnect_requested.connect(self.Disconnect_Camera)
        self.Config.SpectrumY_Spinbox.valueChanged.connect(self.__Spectrum_Position_Changed)
        self.ImagePreview.spectrum_position_selected.connect(self.Config.SpectrumY_Spinbox.setValue)
        self.ImagePreview.Preview_Mode_Button.toggled.connect(lambda: self.__Update_Preview())
        self.Config.stage_connect_requested.connect(self.stage_worker.connect_stage)
        self.Config.stage_disconnect_requested.connect(self.stage_worker.disconnect_stage)

        self.Config.stage_move_requested.connect(self.stage_worker.move_to)
        self.Config.stage_home_requested.connect(self.stage_worker.home)
        self.Config.stage_speed_requested.connect(self.stage_worker.set_speed)
        self.Config.start_acquisition_requested.connect(self.Start_Acquisition)
        self.Config.camera_config_requested.connect(self.__Update_Camera_Configuration)

        self.Status.Calibration_Wavelength_StartPixel_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Wavelength_EndPixel_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Wavelength_Startwl_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Wavelength_Endwl_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Enable_Checkbox.toggled.connect(self.__Calibration_Mode_Changed)
        self.Status.Band1_Slider.valueChanged.connect(self.__Band_Slider_Changed)
        self.Status.Band1_L_Spinbox.editingFinished.connect(self.__Band_Spinbox_Changed)
        self.Status.Band1_R_Spinbox.editingFinished.connect(self.__Band_Spinbox_Changed)
        self.Status.Save_Button.clicked.connect(self.__Save_HSI_Cube)

        self.stage_worker.connected.connect(self.__Stage_Connected)
        self.stage_worker.position_updated.connect(self.__Update_Stage_Position)
        self.stage_worker.motion_finished.connect(self.__Update_Stage_Position)
        self.stage_worker.error.connect(self.__Stage_Error)
        self.stage_worker.disconnected.connect(self.__Stage_Disconnected)

    @pyqtSlot()
    def Start_Acquisition(self):

        if self.camera_process is not None:
            QMessageBox.warning(self, "Acquisition", "Disconnect the camera preview first")
            return
        if self.stage_connected:
            QMessageBox.warning(self, 'Acquisition', 'Disconnect the stage manual control first')
            return

        self.__Release_Cube()

        self.live_cube = None
        self.live_band_image = None
        self.live_band_index = None
        self.live_band_lines = 0

        camera_serial = self.Config.Serial_Entry.text().strip()
        stage_serial = self.Config.Stage_Serial_Entry.text().strip()
        exposure = self.Config.Exposure_Spinbox.value()
        temperature = self.Config.Temperature_Spinbox.value()
        detector_mode = self.Config.Gain_Combo.currentData()
        stage_speed = self.Config.Stage_Speed_Spinbox.value()
        start_mm = self.Config.Stage_Start_Spinbox.value()
        end_mm = self.Config.Stage_End_Spinbox.value()
        step_mm = self.Config.Stage_Steps_Spinbox.value()

        settle_s = 0.1

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(os.getcwd(), f"HSI_Cube_{timestamp}.npy")

        self._Start_Acquisition_Process(camera_serial = camera_serial, stage_serial = stage_serial, exposure = exposure, temperature = temperature,
                                        detector_mode = detector_mode, stage_speed = stage_speed, start_mm = start_mm, end_mm = end_mm, step_mm = step_mm,
                                        settle_s = settle_s, output_path = output_path)

    def Connect_Camera(self, serial):
        if (self.camera_process is not None and self.camera_process.is_alive()):
            return
        exposure = self.Config.Exposure_Spinbox.value()
        fps = self.Config.FPS_Spinbox.value()
        temperature = self.Config.Temperature_Spinbox.value()
        self.Config.Connection_Button.setEnabled(False)
        self.Config.Connection_Button.setText("Connecting...")
        self._Start_Camera_Process(serial = serial, exposure = exposure, fps = fps, temperature = temperature)

    def Disconnect_Camera(self):
        if self.camera_process is None:
            return
        if not self.camera_process.is_alive():
            self._Camera_Process_Finished()
            return
        self.Config.Connection_Button.setEnabled(False)
        self.Config.Connection_Button.setText("Disconnecting...")
        self.Status.Status_Camera_Value.setText("Idle")
        self.camera_stop_event.set()

    # def Connect_Stage(self, serial):

    @pyqtSlot(str)
    def Camera_Error(self, message):
        QMessageBox.critical(self, "Camera Error", f"{message}")

    def _Start_Acquisition_Process(self, camera_serial, stage_serial, exposure, temperature, detector_mode,stage_speed, start_mm, end_mm, step_mm, settle_s, output_path):
        if (self.acquisition_process is not None and self.acquisition_process.is_alive()):
            return

        ctx = mp.get_context('spawn')
        self.acquisition_frame_queue = ctx.Queue(maxsize=3)
        self.acquisition_status_queue = ctx.Queue()
        self.acquisition_stop_event = ctx.Event()
        self.acquisition_process = ctx.Process(target = UP.acquisition_process_main,
                                               args = (camera_serial, stage_serial, exposure, temperature, detector_mode, stage_speed, start_mm, end_mm, step_mm, settle_s, output_path,
                                                       self.acquisition_frame_queue, self.acquisition_status_queue, self.acquisition_stop_event))
        self.Config.Start_Acquisition_Button.setEnabled(False)
        self.Config.Start_Acquisition_Button.setText("Acquisition...")
        self.acquisition_process.start()
        self.acquisition_timer.start()

    def _Start_Camera_Process(self, serial, exposure, fps, temperature):
        ctx = mp.get_context('spawn')
        self.camera_frame_queue = ctx.Queue(maxsize=3) # Important Parameter for Preivew
        self.camera_status_queue = ctx.Queue()
        self.camera_stop_event = ctx.Queue()
        self.camera_stop_event = ctx.Event()

        self.camera_process = ctx.Process(target = UP.camera_process_main,
                                          args=(serial, exposure, fps, temperature, self.camera_frame_queue, self.camera_status_queue, self.camera_command_queue,self.camera_stop_event))
        self.camera_process.start()
        self.preview_timer.start()
        self.process_timer.start()

    def _Camera_Process_Finished(self):
        process = self.camera_process
        if process is None:
            return
        if process.is_alive():
            return

        self.preview_timer.stop()
        self.process_timer.stop()

        process.join()
        process.close()

        if self.camera_frame_queue is not None:
            self.camera_frame_queue.close()
        if self.camera_status_queue is not None:
            self.camera_status_queue.close()
        if self.camera_command_queue is not None:
            self.camera_command_queue.close()

        self.camera_process = None
        self.camera_frame_queue = None
        self.camera_status_queue = None
        self.camera_command_queue = None
        self.camera_stop_event = None
        self.Config.Connection_Button.setEnabled(True)
        self.Config.Connection_Button.setText("Now Disconnected. Click to Connect")

    def _Acquisition_Process_Finished(self):
        process = self.acquisition_process

        if process is None:
            return
        if process.is_alive():
            return

        process.join()
        process.close()

        if self.acquisition_frame_queue is not None:
            self.acquisition_frame_queue.close()
        if self.acquisition_status_queue is not None:
            self.acquisition_status_queue.close()

        self.acquisition_process = None
        self.acquisition_frame_queue = None
        self.acquisition_status_queue = None
        self.acquisition_stop_event = None
        self.acquisition_timer.stop()

        self.Config.Start_Acquisition_Button.setEnabled(True)
        self.Config.Start_Acquisition_Button.setText("Start Cube Acquisition")

    def __Update_Preview(self):
        show_frame = self.ImagePreview.Preview_Mode_Button.isChecked()
        if show_frame:
            if self.latest_camera_image is None:
                return
            image = self.__Build_Band_Preview(self.latest_camera_image)

            align_left = False

        else:
            if self.live_band_image is None:
                return
            image = self.live_band_image[:, :self.live_band_lines]
            align_left = True

        self.ImagePreview.Update_Preview(image, align_left = align_left)

    def __Select_Band_Range(self, data):
        if data is None:
            return None, None
        spectral_size = data.shape[-1]
        band_left, band_right = self.Status.Band1_Slider.value()
        band_left = int(band_left)
        band_right = int(band_right)
        selected = data[..., band_left:band_right+1]
        return (selected, (band_left, band_right))

    def __Build_Band_Preview(self, image):
        if image is None:
            return None

        selected, band_range = self.__Select_Band_Range(image)

        if selected is None:
            return None

        band_left, band_right = band_range
        preview = np.zeros_like(image)
        preview[..., band_left:band_right+1] = selected
        return preview

    def __Update_Acquisition_Frame(self):
        if self.acquisition_frame_queue is None:
            return
        latest_packet = None
        try:
            while True:
                latest_packet = (self.acquisition_frame_queue.get_nowait())
        except Empty:
            pass

        if latest_packet is None:
            return

        image, metadata = latest_packet

        self.latest_camera_image = image
        self.__Update_Metadata(metadata)
        self.__Update_Spectrum_Range(image)
        self.__Update_Preview()
        # self.ImagePreview.Update_Preview(latest_image)
        self.__Update_Spectrum()

    @pyqtSlot()
    def __Poll_Acquisition_Process(self):
        self.__Update_Acquisition_Frame()
        if self.acquisition_status_queue is not None:
            try:
                while True:
                    status, data = (self.acquisition_status_queue.get_nowait())
                    self.Status.Status_CPU_Value.setText(f"{psutil.cpu_percent()}%")
                    if status == "started":
                        total = data["lines"]
                        self.Status.Status_Camera_Value.setText("Acquiring")
                        self.Status.Status_AcquiredFrames_Value.setText(f"0 / {total}")
                        self.Config.Start_Acquisition_Button.setText(f"Acquiring 0 / {total}")
                    elif status == "progress":
                        linenumber = data["index"]
                        index = linenumber - 1
                        total = data["total"]
                        position = data["position"]
                        image_now = data['image']
                        self.Status.Status_AcquiredFrames_Value.setText(f"{linenumber} / {total}")

                        if self.live_cube is None:
                            self.live_cube = np.empty((total, image_now.shape[0], image_now.shape[1]), dtype = image_now.dtype)
                        self.live_cube[index] = image_now
                        self.live_band_lines = linenumber
                        self.__Update_Live_Band_Image()

                        self.Config.Start_Acquisition_Button.setText(f"Acquiring {linenumber} / {total}")
                        self.Config.Stage_Position.setText(f"{position:.3f} mm")

                    elif status == "finished":
                        cube_path = data["path"]
                        self.cube_path = os.path.abspath(cube_path)
                        self.cube = np.load(self.cube_path, mmap_mode = "r")
                        self.live_band_lines = self.cube.shape[0]
                        self.__Update_Band_Image()
                        QMessageBox.information(self, "Acquisition Finished", f"Cube saved:\n{cube_path}")
                        self.Status.Save_Button.setEnabled(True)
                        self.Status.Status_Camera_Value.setText("Idle")
                        self.Config.Start_Acquisition_Button.setText(str(data["lines"]))

                    elif status == "aborted":
                        QMessageBox.warning(self, "Acquisition Aborted", f"Acquired lines: {data['lines']}")
                    elif status == "error":
                        QMessageBox.critical(self, "Acquisition Error", data)
                        self.Status.Status_Camera_Value.setText("Error")
                    elif status == "telemetry":
                        self.__Update_Telemetry(data)
            except Empty:
                pass

        if (self.acquisition_process is not None and not self.acquisition_process.is_alive()):
            self._Acquisition_Process_Finished()

    @pyqtSlot(float)
    def __Stage_Connected(self, position):
        self.stage_connected = True
        self.Config.Stage_Connection_Button.setText("Now Connected. Click to Disconnect")
        self.__Update_Stage_Position(position)
        self.Config.stage_speed_requested.emit(self.Config.Stage_Speed_Spinbox.value())

    @pyqtSlot()
    def __Stage_Disconnected(self):
        self.stage_connected = False
        self.Config.Stage_Connection_Button.setText("Now Disconnected. Click to Connect")

    @pyqtSlot(float)
    def __Update_Stage_Position(self, position):
        self.Config.Stage_Position.setText(f"{position:.3f} mm")

    @pyqtSlot(str)
    def __Stage_Error(self, message):
        QMessageBox.critical(self, "Stage Error", f"{message}")

    @pyqtSlot()
    def __Update_Camera_Preview(self):
        if self.camera_frame_queue is None:
            return
        latest_packet = None
        try:
            while True:
                latest_packet = (self.camera_frame_queue.get_nowait())
        except Empty:
            pass

        if latest_packet is None:
            return

        image, metadata = latest_packet
        self.latest_camera_image = image
        self.__Update_Metadata(metadata)
        self.__Update_Spectrum_Range(image)
        self.__Update_Preview()
        # self.ImagePreview.Update_Preview(latest_image)
        self.__Update_Spectrum()

    def __Update_Camera_Configuration(self, name, value):
        if (self.camera_process is None or not self.camera_process.is_alive() or self.camera_command_queue is None):
            return
        self.camera_command_queue.put((name, value))

    @pyqtSlot()
    def __Poll_Camera_Process(self):
        if self.camera_status_queue is not None:
            try:
                while True:
                    status, data = (self.camera_status_queue.get_nowait())
                    self.Status.Status_CPU_Value.setText(f"{psutil.cpu_percent()}%")
                    if status == "connected":
                        self.Config.Connection_Button.setEnabled(True)
                        self.Config.Connection_Button.setText("Now Connected. Click to Disconnect")
                        self.Status.Status_Camera_Value.setText("Preview")
                    elif status == "error":
                        QMessageBox.critical(self, "Camera Connection Error", data)
                        self.Status.Status_Camera_Value.setText("Error")
                    elif status == "disconnected":
                        self.Status.Status_Camera_Value.setText("Disconnected")
                        pass
                    elif status == "detector_modes":
                        self.Config.Update_Gain_Modes(data)
                    elif status == "telemetry":
                        self.__Update_Telemetry(data)
            except Empty:
                pass
        if (self.camera_process is not None and not self.camera_process.is_alive()):
            self._Camera_Process_Finished()

    @pyqtSlot(int)
    def __Spectrum_Position_Changed(self, position):
        self.__Update_Spectrum()

    def __Update_Spectrum(self):
        image = self.latest_camera_image

        if image is None:
            return

        if image.ndim != 2:
            return

        spatial_size = image.shape[0]
        spectral_size = image.shape[1]

        position = self.Config.SpectrumY_Spinbox.value()
        position = np.clip(position, 0, spatial_size - 1)
        intensity = image[int(position), :].astype(np.float32)

        if (self.wavelength_range is not None and len(self.wavelength_range) == spectral_size and self.calibration_enabled):
            x_axis = self.wavelength_range
            self.SpectrumPreview.set_x_axis_mode(True)
        else:
            x_axis = np.arange(spectral_size)
            self.SpectrumPreview.set_x_axis_mode(False)

        self.SpectrumPreview.set_spectrum(x_axis, intensity)

    def __Update_Spectrum_Range(self, image:np.ndarray):
        spatial_max = image.shape[0] - 1

        if (self.Config.SpectrumY_Spinbox.maximum() != spatial_max):
            self.Config.SpectrumY_Spinbox.setMaximum(spatial_max)
            self.Config.SpectrumY_Slider.setMaximum(spatial_max)

    def __Update_Live_Band_Image(self):
        if (self.live_cube is None or self.live_band_lines <= 0):
            return
        current_cube = self.live_cube[:self.live_band_lines]
        band_cube, band_range = self.__Select_Band_Range(current_cube)
        band_image = np.mean(band_cube, axis=-1, dtype=np.float32)
        self.live_band_image = np.ascontiguousarray(band_image.T)
        self.live_band_index = band_range
        if not self.ImagePreview.Preview_Mode_Button.isChecked():
            self.__Update_Preview()


    def __Update_Band_Image(self):
        if self.cube is None:
            return

        band_cube, band_range = self.__Select_Band_Range(self.cube)
        if band_cube is None:
            return

        band_image = np.mean(band_cube, axis=-1, dtype=np.float32)
        self.live_band_image = np.ascontiguousarray(band_image.T)
        self.live_band_index = band_range
        self.live_band_lines = self.cube.shape[0]
        if not (self.ImagePreview.Preview_Mode_Button.isChecked()):
            self.__Update_Preview()

    @pyqtSlot()
    def __Band_Range_Changed(self):
        if self.ImagePreview.Preview_Mode_Button.isChecked():
            self.__Update_Preview()
        elif (self.acquisition_process is not None and self.live_cube is not None):
            self.__Update_Live_Band_Image()
        elif self.cube is not None:
                self.__Update_Band_Image()

    def __Band_Slider_Changed(self, value):
        self.__Update_Band_Spinboxes()
        self.__Band_Range_Changed()

    def __Update_Band_Spinboxes(self):
        pixel_left, pixel_right = self.Status.Band1_Slider.value()
        left_box = self.Status.Band1_L_Spinbox
        right_box = self.Status.Band1_R_Spinbox
        left_box.blockSignals(True)
        right_box.blockSignals(True)
        try:
            if (self.calibration_enabled and self.wavelength_range is not None):
                wavelength_min = float(np.min(self.wavelength_range))
                wavelength_max = float(np.max(self.wavelength_range))
                for box in (left_box, right_box):
                    box.setDecimals(1)
                    box.setRange(wavelength_min, wavelength_max)
                    box.setSuffix(" nm")
                left_box.setValue(self.__Pixel_To_Wavelength(pixel_left))
                right_box.setValue(self.__Pixel_To_Wavelength(pixel_right))
            else:
                spectral_max = self.Status.Band1_Slider.maximum()
                for box in (left_box, right_box):
                    box.setDecimals(0)
                    box.setRange(0, spectral_max)
                    box.setSuffix(" px")
                left_box.setValue(pixel_left)
                right_box.setValue(pixel_right)
        finally:
            left_box.blockSignals(False)
            right_box.blockSignals(False)

    def __Band_Spinbox_Changed(self):
        left_value = self.Status.Band1_L_Spinbox.value()
        right_value = self.Status.Band1_R_Spinbox.value()
        if (self.calibration_enabled and self.wavelength_range is not None):
            pixel_left = self.__Wavelength_To_Pixel(left_value)
            pixel_right = self.__Wavelength_To_Pixel(right_value)
        else:
            pixel_left = int(round(left_value))
            pixel_right = int(round(right_value))
        pixel_left, pixel_right = sorted((pixel_left, pixel_right))
        self.Status.Band1_Slider.setValue((pixel_left, pixel_right))

    @pyqtSlot(bool)
    def __Calibration_Mode_Changed(self, checked):
        if checked:
            self.__Update_Wavelength_Calibration()
            if self.wavelength_range is None:
                QMessageBox.warning(self, "Calibration", "Invalid wavelength calibration.")
                self.Status.Calibration_Enable_Checkbox.blockSignals(True)
                self.Status.Calibration_Enable_Checkbox.setChecked(False)
                self.Status.Calibration_Enable_Checkbox.blockSignals(False)
                self.calibration_enabled = False
                return
        self.calibration_enabled = checked
        # if self.calibration_enabled:
        self.__Update_Band_Spinboxes()
        self.__Update_Spectrum()

    def __Pixel_To_Wavelength(self, pixel):
        if self.wavelength_range is None:
            return None
        pixel = int(np.clip(pixel, 0, len(self.wavelength_range) - 1))
        return float(self.wavelength_range[pixel])

    def __Wavelength_To_Pixel(self, wavelength):
        if self.wavelength_range is None:
            return None
        return int(np.argmin(np.abs(self.wavelength_range - wavelength)))

    def __Update_Wavelength_Calibration(self):
        pixel_left = self.Status.Calibration_Wavelength_StartPixel_Spinbox.value()
        pixel_right = self.Status.Calibration_Wavelength_EndPixel_Spinbox.value()
        wavelength_left = self.Status.Calibration_Wavelength_Startwl_Spinbox.value()
        wavelength_right = self.Status.Calibration_Wavelength_Endwl_Spinbox.value()

        if pixel_right <= pixel_left:
            self.wavelength_range = None
            self.Status.Calibration_Wavelength_Value.setText("Invalid Pixel Range")
            return

        if self.latest_camera_image is not None:
            spectral_size = self.latest_camera_image.shape[1]
        elif self.cube is not None:
            spectral_size = self.cube.shape[-1]
        else:
            spectral_size = self.Status.Calibration_Wavelength_EndPixel_Spinbox.maximum() + 1

        slope = (wavelength_right - wavelength_left) / (pixel_right - pixel_left)

        pixels = np.arange(spectral_size, dtype=np.float32)
        self.wavelength_range = wavelength_left + (pixels - pixel_left) * slope
        self.Status.Calibration_Wavelength_Value.setText(f"{self.wavelength_range[0]:.1f} - {self.wavelength_range[-1]:.1f} nm")
        self.__Update_Spectrum()

    def __Release_Cube(self):
        if self.cube is not None:
            if isinstance(self.cube, np.memmap):
                mmap_object = getattr(self.cube, "_mmap", None)

                if mmap_object is not None:
                    mmap_object.close()
        self.cube = None
        self.cube_path = None

    def __Update_Metadata(self, metadata):
        if metadata is None:
            return

        frame_id = metadata.get("frame_id")
        timestamp = metadata.get("timestamp")
        exposure = metadata.get("exposure_time")
        shape = metadata.get("image_shape")

        self.Status.Meta_FrameID_Value.setText("--" if frame_id is None else f"{frame_id}")
        self.Status.Meta_TimeStamp_Value.setText("--" if timestamp is None else f"{timestamp:.3f}")
        self.Status.Meta_ExposureTime_Value.setText("--" if exposure is None else f"{exposure}")

        if shape is None:
            self.Status.Meta_ImageSize_Value.setText("--")
        else:
            height, width = shape[:2]
            self.Status.Meta_ImageSize_Value.setText(f"{width} × {height}")

    def __Update_Telemetry(self, telemetry):
        temp = telemetry.get("sensor_temperature")
        fps = telemetry.get("fps")
        gain = telemetry.get("gain")
        if temp is not None:
            self.Status.Status_SensorTemp_Value.setText(f"{temp:.1f} °C")
            self.Status.Meta_SensorTemp_Value.setText(f"{temp:.1f} °C")
        if fps is not None:
            self.Status.Status_FPS_Value.setText(f"{fps:.1f}")
        if gain is not None:
            self.Status.Meta_Gain_Value.setText(f"{gain}")


    def __Save_HSI_Cube(self):
        if (self.cube is None or self.cube_path is None):
            QMessageBox.warning(self, "Save HSI Cube", "No HSI cube is available.")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"HSI_Cube_{timestamp}.npy"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save HSI Cube", default_name, "Numpy Cube (*.npy)")
        if not file_path:
            return
        if not file_path.lower().endswith(".npy"):
            file_path += ".npy"
        source = os.path.abspath(self.cube_path)
        destination = os.path.abspath(file_path)
        try:
            if source != destination:
                shutil.copy2(source, destination)
            QMessageBox.information(self, "Save HSI Cube", f"Cube Saved \n {destination}")
        except Exception as e:
            QMessageBox.critical(self, "Save HSI Cube", f"{type(e).__name__}: {e}")


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


class ConfigWidget(QWidget):
    camera_connect_requested = pyqtSignal(str)
    camera_disconnect_requested = pyqtSignal()
    camera_config_requested = pyqtSignal(str, object)
    stage_connect_requested = pyqtSignal(str)
    stage_disconnect_requested = pyqtSignal()
    stage_move_requested = pyqtSignal(float)
    stage_home_requested = pyqtSignal()
    stage_speed_requested = pyqtSignal(float)
    start_acquisition_requested = pyqtSignal()

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
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Gain_Prompt, self.Gain_Combo), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Acquisition Setting')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.ROI_Prompt, self.ROI_L_Spinbox, self.ROI_Slider, self.ROI_R_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.SpectrumY_Prompt, self.SpectrumY_Slider, self.SpectrumY_Spinbox), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Spectrum Settings')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Serial_Prompt, self.Stage_Serial_Entry), 'Horizontal'))
        Temp_Layout.addWidget(self.Stage_Connection_Button)
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Speed_Prompt, self.Stage_Speed_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Move_Prompt, self.Stage_Move_Spinbox, self.Stage_Home_Button, self.Stage_Position), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Stage Settings')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Start_Prompt, self.Stage_Start_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_End_Prompt, self.Stage_End_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Stage_Steps_Prompt, self.Stage_Steps_Spinbox), 'Horizontal'))
        Temp_Layout.addWidget(self.Start_Acquisition_Button)
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Stage Scan')

        # Layout.addLayout(self.DesignUtil.Layout_Widget((self.Interval_Prompt, self.Interval_Entry), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.ImagePath_BTN, self.DarkPath_BTN, self.FlatPath_BTN), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.ImagePath_Prompt, self.ImagePath_Label), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.DarkPath_CheckBox, self.DarkPath_Label), 'Horizontal'))
        # Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.FlatPath_CheckBox, self.FlatPath_Label), 'Horizontal'))

    def UI_Component(self):

        ButtonSize = (75, 30)
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
        self.FPS_Spinbox.setValue(50)
        self.FPS_Spinbox.setRange(0.1, 1000)
        self.FPS_Spinbox.setSuffix(" fps")

        self.Gain_Prompt = QLabel("Analog Gain")
        self.Gain_Prompt.setFixedSize(*LabelSize)
        self.Gain_Combo = QComboBox()
        # self.Gain_Combo.addItems(["Free Run", "Software", "External"])

    # UI for Preview Configuration
        self.ROI_Prompt = QLabel("ROI")
        self.ROI_Prompt.setFixedSize(*LabelSize)
        self.ROI_Slider = QRangeSlider()
        self.ROI_Slider.setOrientation(Qt.Orientation.Horizontal)
        self.ROI_Slider.setRange(0, 511)
        self.ROI_Slider.setValue((0, 511))
        self.ROI_Slider.setSingleStep(1)
        self.ROI_L_Spinbox = QSpinBox()
        self.ROI_L_Spinbox.setRange(0, 511)
        self.ROI_L_Spinbox.setValue(0)
        self.ROI_R_Spinbox = QSpinBox()
        self.ROI_R_Spinbox.setRange(0, 511)
        self.ROI_R_Spinbox.setValue(511)

        self.SpectrumY_Prompt = QLabel("Spectrum Position")
        self.SpectrumY_Prompt.setFixedSize(*LabelSize)
        self.SpectrumY_Spinbox = QSpinBox()
        self.SpectrumY_Spinbox.setRange(0, 511)
        self.SpectrumY_Spinbox.setValue(256)
        self.SpectrumY_Slider = QSlider(Qt.Orientation.Horizontal)
        self.SpectrumY_Slider.setRange(0, 511)
        self.SpectrumY_Slider.setSingleStep(1)
        self.SpectrumY_Slider.setValue(255)

        self.Stage_Serial_Prompt = QLabel("Serial Number")
        self.Stage_Serial_Prompt.setFixedSize(*LabelSize)
        self.Stage_Serial_Entry = QLineEdit()
        self.Stage_Serial_Entry.setFixedSize(*EntrySize)
        self.Stage_Serial_Entry.setPlaceholderText("Enter Stage serial number")
        self.Stage_Serial_Entry.setText("49402484")

        self.Stage_Connection_Button = QPushButton("Now Disconnected. Click to Connect")

        self.Stage_Speed_Prompt = QLabel("Speed")
        self.Stage_Speed_Prompt.setFixedSize(*LabelSize)
        self.Stage_Speed_Spinbox = QDoubleSpinBox()
        self.Stage_Speed_Spinbox.setRange(1E-3, 5)
        self.Stage_Speed_Spinbox.setValue(0.1)
        self.Stage_Speed_Spinbox.setSuffix(" mm/s")
        self.Stage_Speed_Spinbox.setKeyboardTracking(False)

        self.Stage_Move_Prompt = QLabel("Stage Control")
        self.Stage_Move_Prompt.setFixedSize(*LabelSize)
        self.Stage_Move_Spinbox = QDoubleSpinBox()
        self.Stage_Move_Spinbox.setRange(0, 50)
        self.Stage_Move_Spinbox.setValue(0)
        self.Stage_Move_Spinbox.setSuffix(" mm")
        self.Stage_Move_Spinbox.setKeyboardTracking(False)

        self.Stage_Home_Button = QPushButton("Init")
        self.Stage_Home_Button.setFixedSize(*ButtonSize)

        self.Stage_Position = QLabel("0")

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
        self.Stage_Steps_Spinbox.setRange(0.001, 50)
        self.Stage_Steps_Spinbox.setValue(0.1)
        self.Stage_Steps_Spinbox.setSuffix(" mm")

        self.Start_Acquisition_Button = QPushButton("Start Cube Acquisition")


    def EventProcess(self):

        self.Connection_Button.clicked.connect(self.CameraConnection_Event)
        self.ROI_L_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(value, self.ROI_Slider.value()[1], self.ROI_Slider))
        self.ROI_R_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(self.ROI_Slider.value()[0], value, self.ROI_Slider))
        self.ROI_Slider.valueChanged.connect(lambda values: Uqt.SliderHelper.RangeSliderChanged(self.ROI_L_Spinbox, self.ROI_R_Spinbox, values))
        self.SpectrumY_Slider.valueChanged.connect(self.SpectrumY_Spinbox.setValue)
        self.SpectrumY_Spinbox.valueChanged.connect(self.SpectrumY_Slider.setValue)

        self.Stage_Connection_Button.clicked.connect(self.StageConnection_Event)
        self.Stage_Move_Spinbox.editingFinished.connect(self.StageMove_Event)
        self.Stage_Speed_Spinbox.editingFinished.connect(lambda: self.stage_speed_requested.emit(self.Stage_Speed_Spinbox.value()))
        self.Stage_Home_Button.clicked.connect(self.StageHome_Event)

        self.Start_Acquisition_Button.clicked.connect(self.Start_Acquisition_Event)

        self.Exposure_Spinbox.editingFinished.connect(lambda: self.camera_config_requested.emit("exposure", self.Exposure_Spinbox.value()))
        self.FPS_Spinbox.editingFinished.connect(lambda: self.camera_config_requested.emit("fps", self.FPS_Spinbox.value()))
        self.Temperature_Spinbox.editingFinished.connect(lambda: self.camera_config_requested.emit("temperature", self.Temperature_Spinbox.value()))
        self.Gain_Combo.currentIndexChanged.connect(self.__Gain_Changed)

    def CameraConnection_Event(self):
        if self.Connection_Button.text() == "Now Disconnected. Click to Connect":
            serial = self.Serial_Entry.text().strip()

            if not serial:
                QMessageBox.warning(self, "Error", "Please enter a serial number.")
                return

            self.camera_connect_requested.emit(serial)
        else:
            self.camera_disconnect_requested.emit()

    def StageConnection_Event(self):
        if self.Stage_Connection_Button.text() == "Now Disconnected. Click to Connect":

            serial = self.Stage_Serial_Entry.text().strip()
            if not serial:
                QMessageBox.warning(self, "Stage Error", "Please enter a serial number.")
                return
            self.stage_connect_requested.emit(serial)
        else:
            self.stage_disconnect_requested.emit()

    def StageMove_Event(self):
        target = self.Stage_Move_Spinbox.value()
        self.stage_move_requested.emit(target)

    def StageHome_Event(self):
        self.stage_home_requested.emit()

    def Start_Acquisition_Event(self):
        self.start_acquisition_requested.emit()

    def Update_Gain_Modes(self, modes):
        self.Gain_Combo.blockSignals(True)
        self.Gain_Combo.clear()
        for item in modes:
            mode = item["mode"]
            gain = item["gain"]
            self.Gain_Combo.addItem(f"Mode {mode} - Gain {gain}", mode)
        self.Gain_Combo.blockSignals(False)

    def __Gain_Changed(self):
        mode = self.Gain_Combo.currentData()
        if mode is None:
            return
        self.camera_config_requested.emit("detector_mode", mode)



class ImagePreviewWidgets(QWidget):

    spectrum_position_selected = pyqtSignal(int)

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

        Layout.addWidget(self.Preview_Mode_Button, alignment = Qt.AlignmentFlag.AlignRight)

        self.PreviewLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        Layout.addWidget(self.PreviewLabel)
        Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.CRange_L_Spinbox, self.ColorRange_Slider, self.CRange_R_Spinbox), 'Horizontal'))

    def UI_Component(self):

        self.Preview_Mode_Button = QPushButton("Camera Preview Mode")
        self.Preview_Mode_Button.setCheckable(True)
        self.Preview_Mode_Button.setChecked(True)

        self.PreviewLabel = Uqt.ClickableImageLabel()
        self.PreviewLabel.setMinimumSize(640, 512)
        self.PreviewLabel.setScaledContents(False)
        self.PreviewLabel.setStyleSheet("border: 1px solid gray;")

        self.ColorRange_Slider = QRangeSlider()
        self.ColorRange_Slider.setOrientation(Qt.Orientation.Horizontal)
        self.ColorRange_Slider.setRange(0, 2**16-1)
        self.ColorRange_Slider.setValue((0, 2**16-1))
        self.ColorRange_Slider.setSingleStep(1)

        self.CRange_L_Spinbox = QSpinBox()
        self.CRange_L_Spinbox.setRange(0, 65535)
        self.CRange_L_Spinbox.setValue(0)
        self.CRange_R_Spinbox = QSpinBox()
        self.CRange_R_Spinbox.setRange(0, 65535)
        self.CRange_R_Spinbox.setValue(65535)

    def EventProcess(self):
        self.Preview_Mode_Button.toggled.connect(self._Preview_Mode_Event)
        self.ColorRange_Slider.valueChanged.connect(self.Update_Display)
        self.PreviewLabel.pixel_clicked.connect(self.__Image_Clicked)
        self.CRange_L_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(value, self.ColorRange_Slider.value()[1], self.ColorRange_Slider))
        self.CRange_R_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(self.ColorRange_Slider.value()[0], value, self.ColorRange_Slider))
        self.ColorRange_Slider.valueChanged.connect(lambda values: Uqt.SliderHelper.RangeSliderChanged(self.CRange_L_Spinbox, self.CRange_R_Spinbox, values))


    def Update_Preview(self, Image, align_left=False):

        if Image is None or Image.size == 0:
            return

        self.current_image = Image
        self.PreviewLabel.set_image_shape(Image.shape)
        if align_left:
            self.PreviewLabel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.PreviewLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.Update_Display()

    def Update_Display(self):
        if self.current_image is None:
            return
        vmin, vmax = self.ColorRange_Slider.value()
        pixmap = Uqt.CustomFunction.cv2qt(self.current_image, vmin, vmax)
        if pixmap:
            self.PreviewLabel.setPixmap(pixmap)

    def _Preview_Mode_Event(self, checked):
        if checked:
            self.Preview_Mode_Button.setText("Camera Preview Mode")
        else:
            self.Preview_Mode_Button.setText("Cube Image Mode")

    def __Image_Clicked(self, x, y):
        self.spectrum_position_selected.emit(y)


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

    def set_x_axis_mode(self, calibrated):
        if calibrated:
            self.plot.setLabel("bottom", "Wavelength", units="nm")
        else:
            self.plot.setLabel("bottom", "Spectral Pixel")


class StatusWidgets(QWidget):
    wavelength_range_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super(StatusWidgets, self).__init__(parent)

        Layout = QVBoxLayout()
        self.initUI(Layout)
        self.setLayout(Layout)

    def initUI(self, Layout):

        self.UI_Component()
        self.UI_Layout(Layout)
        # self.EventProcess()

    def UI_Layout(self, Layout):

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Status_Camera_Prompt, self.Status_Camera_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Status_SensorTemp_Prompt, self.Status_SensorTemp_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Status_AcquiredFrames_Prompt, self.Status_AcquiredFrames_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Status_FPS_Prompt, self.Status_FPS_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Status_CPU_Prompt, self.Status_CPU_Value), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Acquisition Status')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Meta_FrameID_Prompt, self.Meta_FrameID_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Meta_TimeStamp_Prompt, self.Meta_TimeStamp_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Meta_ExposureTime_Prompt, self.Meta_ExposureTime_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Meta_SensorTemp_Prompt, self.Meta_SensorTemp_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Meta_ImageSize_Prompt, self.Meta_ImageSize_Value), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Meta_Gain_Prompt, self.Meta_Gain_Value), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Metadata (Last Frame)')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Calibration_Wavelength_Prompt, self.Calibration_Wavelength_Value, self.Calibration_Enable_Checkbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Calibration_Wavelength_StartPixel_Prompt, self.Calibration_Wavelength_StartPixel_Spinbox,
                                                             self.Calibration_Wavelength_Startwl_Prompt, self.Calibration_Wavelength_Startwl_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Calibration_Wavelength_EndPixel_Prompt, self.Calibration_Wavelength_EndPixel_Spinbox,
                                                             self.Calibration_Wavelength_Endwl_Prompt, self.Calibration_Wavelength_Endwl_Spinbox), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Calibration')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Band1_Prompt, self.Band1_Weight), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Band1_L_Spinbox, self.Band1_Slider, self.Band1_R_Spinbox), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Save_Button), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Post Processing')

    def UI_Component(self):

        ButtonSize = (75, 30)
        LabelSize = (150, 30)
        EntrySize = (200, 30)

    # UI for Camera Settings
        self.Status_Camera_Prompt = QLabel("Status")
        self.Status_Camera_Prompt.setFixedSize(*LabelSize)
        self.Status_Camera_Value = QLabel("--")

        self.Status_SensorTemp_Prompt = QLabel("Sensor Temperature")
        self.Status_SensorTemp_Prompt.setFixedSize(*LabelSize)
        self.Status_SensorTemp_Value = QLabel("-- °C")

        self.Status_AcquiredFrames_Prompt = QLabel("Frames Acquired")
        self.Status_AcquiredFrames_Prompt.setFixedSize(*LabelSize)
        self.Status_AcquiredFrames_Value = QLabel("--")

        self.Status_FPS_Prompt = QLabel("FPS")
        self.Status_FPS_Prompt.setFixedSize(*LabelSize)
        self.Status_FPS_Value = QLabel("--")

        self.Status_CPU_Prompt = QLabel("CPU Usage")
        self.Status_CPU_Prompt.setFixedSize(*LabelSize)
        self.Status_CPU_Value = QLabel("--")

        self.Meta_FrameID_Prompt = QLabel("Frame ID")
        self.Meta_FrameID_Prompt.setFixedSize(*LabelSize)
        self.Meta_FrameID_Value = QLabel("--")

        self.Meta_TimeStamp_Prompt = QLabel("Time Stamp")
        self.Meta_TimeStamp_Prompt.setFixedSize(*LabelSize)
        self.Meta_TimeStamp_Value = QLabel("--")

        self.Meta_ExposureTime_Prompt = QLabel("Exposure Time")
        self.Meta_ExposureTime_Prompt.setFixedSize(*LabelSize)
        self.Meta_ExposureTime_Value = QLabel("--")

        self.Meta_SensorTemp_Prompt = QLabel("Sensor Temperature")
        self.Meta_SensorTemp_Prompt.setFixedSize(*LabelSize)
        self.Meta_SensorTemp_Value = QLabel("--")

        self.Meta_ImageSize_Prompt = QLabel("Image Size")
        self.Meta_ImageSize_Prompt.setFixedSize(*LabelSize)
        self.Meta_ImageSize_Value = QLabel("--")

        self.Meta_Gain_Prompt = QLabel("Analog Gain")
        self.Meta_Gain_Prompt.setFixedSize(*LabelSize)
        self.Meta_Gain_Value = QLabel("--")

        self.Calibration_Wavelength_Prompt = QLabel("Wavelength Range")
        self.Calibration_Wavelength_Prompt.setFixedSize(*LabelSize)
        self.Calibration_Wavelength_Value = QLabel("--")

        self.Calibration_Enable_Checkbox = QCheckBox("Enable")
        self.Calibration_Enable_Checkbox.setChecked(False)

        self.Calibration_Wavelength_StartPixel_Prompt = QLabel("Pixel (Left)  ")
        # self.Calibration_Wavelength_StartPixel_Prompt.setFixedSize(*LabelSize)
        self.Calibration_Wavelength_StartPixel_Spinbox = QSpinBox()
        self.Calibration_Wavelength_StartPixel_Spinbox.setRange(0, 639)
        self.Calibration_Wavelength_StartPixel_Spinbox.setValue(0)
        self.Calibration_Wavelength_StartPixel_Spinbox.setKeyboardTracking(False)

        self.Calibration_Wavelength_Startwl_Prompt = QLabel("λ")
        # self.Calibration_Wavelength_Startwl_Prompt.setFixedSize(*LabelSize)
        self.Calibration_Wavelength_Startwl_Spinbox = QDoubleSpinBox()
        self.Calibration_Wavelength_Startwl_Spinbox.setDecimals(1)
        self.Calibration_Wavelength_Startwl_Spinbox.setRange(400, 2000)
        self.Calibration_Wavelength_Startwl_Spinbox.setValue(900)
        self.Calibration_Wavelength_Startwl_Spinbox.setSuffix(" nm")
        self.Calibration_Wavelength_Startwl_Spinbox.setKeyboardTracking(False)

        self.Calibration_Wavelength_EndPixel_Prompt = QLabel("Pixel (Right)")
        # self.Calibration_Wavelength_StartPixel_Prompt.setFixedSize(*LabelSize)
        self.Calibration_Wavelength_EndPixel_Spinbox = QSpinBox()
        self.Calibration_Wavelength_EndPixel_Spinbox.setRange(0, 639)
        self.Calibration_Wavelength_EndPixel_Spinbox.setValue(639)
        self.Calibration_Wavelength_EndPixel_Spinbox.setKeyboardTracking(False)

        self.Calibration_Wavelength_Endwl_Prompt = QLabel("λ")
        # self.Calibration_Wavelength_Startwl_Prompt.setFixedSize(*LabelSize)
        self.Calibration_Wavelength_Endwl_Spinbox = QDoubleSpinBox()
        self.Calibration_Wavelength_Endwl_Spinbox.setDecimals(1)
        self.Calibration_Wavelength_Endwl_Spinbox.setRange(400, 2000)
        self.Calibration_Wavelength_Endwl_Spinbox.setValue(1600)
        self.Calibration_Wavelength_Endwl_Spinbox.setSuffix(" nm")
        self.Calibration_Wavelength_Endwl_Spinbox.setKeyboardTracking(False)

        self.Band1_Prompt = QLabel("Band 1")
        self.Band1_Prompt.setFixedSize(*LabelSize)
        self.Band1_Weight = QSpinBox()
        self.Band1_Weight.setRange(0, 1)
        self.Band1_Weight.setValue(1)
        self.Band1_Weight.setKeyboardTracking(False)

        self.Band1_Slider = QRangeSlider()
        self.Band1_L_Spinbox = QDoubleSpinBox()
        self.Band1_L_Spinbox.setDecimals(0)
        self.Band1_R_Spinbox = QDoubleSpinBox()
        self.Band1_R_Spinbox.setDecimals(0)


        Uqt.SliderHelper._init_range_slider(self.Band1_Slider, self.Band1_L_Spinbox, self.Band1_R_Spinbox, 0, 639, 1)

        self.Save_Button = QPushButton("Save HSI Cube")
        self.Save_Button.setEnabled(False)

    # def EventProcess(self):
    #     self.Band1_L_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(value, self.Band1_Slider.value()[1], self.Band1_Slider))
    #     self.Band1_R_Spinbox.valueChanged.connect(lambda value: Uqt.SliderHelper.RangeSpinChanged(self.Band1_Slider.value()[0], value, self.Band1_Slider))
    #     self.Band1_Slider.valueChanged.connect(lambda values: Uqt.SliderHelper.RangeSliderChanged(self.Band1_L_Spinbox, self.Band1_R_Spinbox, values))


if __name__ == '__main__':
    mp.freeze_support()
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())

