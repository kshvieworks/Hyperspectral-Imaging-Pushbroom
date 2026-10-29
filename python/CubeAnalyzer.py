import json
import numpy as np
import shutil
import sys
import os
from datetime import datetime
os.environ["QT_API"] = "pyqt6"

from TestWindow import ImagePreviewWidgets, SpectrumPreviewWidgets, StatusWidgets
from AnalysisTab import AnalysisWidgets
import multiprocessing as mp
import sys

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
                             QMessageBox, QFileDialog)

import Utility_Pyqt as Uqt


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.window = CubeAnalyzerWindow(self)
        self.setCentralWidget(self.window)
        self.setWindowTitle("Cube Analyzer")
        self.show()


class CubeAnalyzerWindow(QWidget):
    def __init__(self, parent= None):
        super(CubeAnalyzerWindow, self).__init__(parent)
    # Cube
        self.cube = None
        self.cube_path = None

    # Metadata
        self.Metadata = None
        self.metadata_path = None

    # Correction Images
        self.dark_frame = None
        self.flat_frame = None
        self.dark_enabled = False
        self.flat_enabled = False
        self.dark_path = None
        self.flat_path = None
        self.dark = None
        self.flat = None

    # ROI
        self.roi = None

    # Calibration
        self.spectrum_x = 0
        self.spectrum_y = 0
        self.calibration_enabled = False
        self.wavelength_range = None

    # Miscellaneous Field
        self.live_band_image = None
        self.live_band_lines = 0

        PageLayout = QVBoxLayout()
        FileLayout = QHBoxLayout()
        BodyLayout = QHBoxLayout()
        PreviewLayout =QVBoxLayout()
        StatusLayout =QVBoxLayout()
        AnalysisLayout = QVBoxLayout()

        self.init_Layout(PageLayout, FileLayout, BodyLayout, PreviewLayout, StatusLayout, AnalysisLayout)
        self.setLayout(PageLayout)

    def init_Layout(self, PageLayout, FileLayout, BodyLayout, PreviewLayout, StatusLayout, AnalysisLayout):
        BodyLayout.addLayout(PreviewLayout, stretch = 4)
        BodyLayout.addLayout(StatusLayout, stretch = 1)
        BodyLayout.addLayout(AnalysisLayout, stretch = 2)

        PageLayout.addLayout(FileLayout)
        PageLayout.addLayout(BodyLayout)

        self.init_FileLayout(FileLayout)
        self.init_Preview(PreviewLayout)
        self.init_Status(StatusLayout)
        self.init_Analysis(AnalysisLayout)

        self.EventProcess()

    def init_FileLayout(self, Layout):

        self.Cube_Button = QPushButton("Cube File...")
        self.Metadata_Button = QPushButton("Metadata...")

        self.Dark_Enable_Checkbox = QCheckBox()
        self.Dark_Enable_Checkbox.setChecked(False)
        self.Dark_Button = QPushButton("Dark File...")
        self.Flat_Enable_Checkbox = QCheckBox()
        self.Flat_Enable_Checkbox.setChecked(False)
        self.Flat_Button = QPushButton("Flat File...")

        Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Cube_Button, self.Metadata_Button), "Horizontal"))
        Layout.addStretch()
        Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Dark_Enable_Checkbox, self.Dark_Button,
                                                         self.Flat_Enable_Checkbox, self.Flat_Button), "Horizontal"))

    def init_Preview(self, Layout):

        self.ImagePreview = ImagePreviewWidgets()
        self.SpectrumPreview = SpectrumPreviewWidgets()

        self.ImagePreview.Dark_Enable_Checkbox.hide()
        self.ImagePreview.DarkPath_BTN.hide()
        self.ImagePreview.Flat_Enable_Checkbox.hide()
        self.ImagePreview.FlatPath_BTN.hide()
        self.ImagePreview.Save_Preview_Button.hide()
        self.ImagePreview.Preview_Mode_Button.hide()

        Layout.addWidget(self.ImagePreview)
        Layout.addWidget(self.SpectrumPreview)

    def init_Status(self, Layout):
        self.Status = StatusWidgets()
        self.Status.Save_Button.hide()
        Layout.addWidget(self.Status)

    def init_Analysis(self, Layout):
        self.Analysis = AnalysisWidgets()
        Layout.addWidget(self.Analysis)

    def EventProcess(self):

        self.Cube_Button.clicked.connect(self.__Load_Cube)
        self.Metadata_Button.clicked.connect(self.__Load_Metadata)

        self.Dark_Button.clicked.connect(lambda: self.__Load_Correction_File("dark"))
        self.Flat_Button.clicked.connect(lambda: self.__Load_Correction_File("flat"))
        self.Dark_Enable_Checkbox.toggled.connect(lambda _: self.__Correction_State_Changed())
        self.Flat_Enable_Checkbox.toggled.connect(lambda _: self.__Correction_State_Changed())

        self.ImagePreview.spectrum_position_selected.connect(self.__Image_Spectrum_Position_Selected)
        self.ImagePreview.roi_selected.connect(self.__Image_ROI_Selected)

        self.Status.Calibration_Wavelength_StartPixel_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Wavelength_EndPixel_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Wavelength_Startwl_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Wavelength_Endwl_Spinbox.valueChanged.connect(self.__Update_Wavelength_Calibration)
        self.Status.Calibration_Enable_Checkbox.toggled.connect(self.__Calibration_Mode_Changed)
        self.Status.Band1_Slider.valueChanged.connect(self.__Band_Slider_Changed)
        self.Status.Band1_L_Spinbox.editingFinished.connect(self.__Band_Spinbox_Changed)
        self.Status.Band1_R_Spinbox.editingFinished.connect(self.__Band_Spinbox_Changed)
        # self.Status.Save_Button.clicked.connect(self.__Save_HSI_Cube)

    def __Load_Cube(self):
        path = Uqt.WidgetFunction.Open_File(caption = "Load HSI Cube", directory = "", filter = "Numpy Cube (*.npy)")
        if not path:
            return
        try:
            cube = np.load(path, mmap_mode = "r")

            if cube.ndim != 3:
                raise ValueError("HSI Cube must be 3-Dimensional")

            self.__Release_Cube()

            self.cube = cube
            self.cube_path = path

            self.roi = None
            self.ImagePreview.PreviewLabel.clear_roi()

            self.live_band_lines = cube.shape[0]
            spectral_size = cube.shape[2]
            self.Status.Band1_Slider.setRange(0, spectral_size - 1)
            self.Status.Band1_Slider.setValue((0, spectral_size - 1))

            self.Status.Calibration_Wavelength_StartPixel_Spinbox.setMaximum(spectral_size - 1)
            self.Status.Calibration_Wavelength_EndPixel_Spinbox.setMaximum(spectral_size - 1)
            self.__Update_Band_Image()
            self.__Update_Spectrum()
            self.Cube_Button.setText("Cube ✔")
            self.Cube_Button.setToolTip(path)

        except Exception as e:
            QMessageBox.critical(self, "Cube Error", f"{type(e).__name__}: {e}")

    def __Load_Metadata(self):
        path = Uqt.WidgetFunction.Open_File(caption = "Load Metadata", directory = "", filter = "JSON Metadata (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding = "utf-8") as f:
                metadata = json.load(f)
            self.Metadata = metadata
            self.metadata_path = path
            self.__Update_Metadata()

            self.Metadata_Button.setText("Metadata ✔")
            self.Metadata_Button.setToolTip(path)
        except Exception as e:
            QMessageBox.critical(self, "Metadata Error", f"{type(e).__name__}: {e}")

    def __Load_Correction_File(self, file_type):

        if self.cube is None:
            QMessageBox.warning(self, "Correction File", "Please load a cube first")
            return

        expected_shape = (self.cube.shape[1], self.cube.shape[2])

        path = Uqt.WidgetFunction.Open_File(caption = "Load Correction File", directory = "", filter = "NumPy Image (*.npy)")

        if not path:
            return
        try:
            image = np.load(path)
            if image.ndim != 2:
                raise ValueError("Correction Image must be 2D Image")

            if (self.cube is not None and image.shape != expected_shape):
                raise ValueError(f"Correction image shape {image.shape} does not match cube frame shape {expected_shape}")
            image = np.asarray(image, dtype=np.float32)

            if file_type == "dark":
                self.dark_frame = image
                self.dark_path = path
                self.Dark_Button.setText("Dark ✔")
                self.Dark_Button.setToolTip(path)

            elif file_type == "flat":
                self.flat_frame = image
                self.flat_path = path
                self.Flat_Button.setText("Flat ✔")
                self.Flat_Button.setToolTip(path)

            self.__Update_Correction_Model()
        except Exception as e:
            QMessageBox.critical(self, "Correction File Error", f"{type(e).__name__}: {e}")

    def __Release_Cube(self):
        if self.cube is not None:
            if isinstance(self.cube, np.memmap):
                mmap_object = getattr(self.cube, "_mmap", None)

                if mmap_object is not None:
                    mmap_object.close()
        self.cube = None
        self.cube_path = None

    def __Update_Metadata(self):
        if self.Metadata is None:
            return

        acquisition = self.Metadata.get("acquisition", {})
        stage = self.Metadata.get("stage", {})
        calibration = self.Metadata.get("calibration", {})
        data = self.Metadata.get("data", {})

        timestamp = acquisition.get("timestamp")
        exposure = acquisition.get("exposure_s")
        temperature = acquisition.get("temperature_c")
        detector_mode = acquisition.get("detector_mode")
        shape = data.get("shape")

        self.Status.Status_Camera_Value.setText("Cube Loaded")
        self.Status.Meta_TimeStamp_Value.setText("--" if timestamp is None else f"{timestamp:.22}")
        self.Status.Meta_ExposureTime_Value.setText("--" if exposure is None else f"{exposure} s")
        self.Status.Meta_SensorTemp_Value.setText("--" if temperature is None else f"{temperature:.1f} °C")
        self.Status.Meta_Gain_Value.setText("--" if detector_mode is None else f" Mode {detector_mode}")

        if shape is not None:
            scan, spatial, spectral = shape

            self.Status.Status_AcquiredFrames_Value.setText(f"{scan}")
            self.Status.Meta_ImageSize_Value.setText(f"{spectral} × {spatial}")
        else:
            self.Status.Status_AcquiredFrames_Value.setText("--")
            self.Status.Meta_ImageSize_Value.setText("--")

        enabled = calibration.get("enabled", False)
        left_pixel = calibration.get("left_pixel")
        left_wavelength = calibration.get("left_wavelength_nm")
        right_pixel = calibration.get("right_pixel")
        right_wavelength = calibration.get("right_wavelength_nm")

        widgets = [self.Status.Calibration_Wavelength_StartPixel_Spinbox,
                   self.Status.Calibration_Wavelength_EndPixel_Spinbox,
                   self.Status.Calibration_Wavelength_Startwl_Spinbox,
                   self.Status.Calibration_Wavelength_Endwl_Spinbox,
                   self.Status.Calibration_Enable_Checkbox]

        for widget in widgets:
            widget.blockSignals(True)

        try:
            if left_pixel is not None:
                self.Status.Calibration_Wavelength_StartPixel_Spinbox.setValue(int(left_pixel))
            if left_wavelength is not None:
                self.Status.Calibration_Wavelength_Startwl_Spinbox.setValue(float(left_wavelength))
            if right_pixel is not None:
                self.Status.Calibration_Wavelength_EndPixel_Spinbox.setValue(int(right_pixel))
            if right_wavelength is not None:
                self.Status.Calibration_Wavelength_Endwl_Spinbox.setValue(float(right_wavelength))
            self.Status.Calibration_Enable_Checkbox.setChecked(bool(enabled))
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        self.calibration_enabled = bool(enabled)
        if enabled:
            self.__Update_Wavelength_Calibration()
        self.__Update_Band_Spinboxes()
        self.__Update_Spectrum()

    def __Update_Band_Image(self):
        if self.cube is None:
            return

        band_cube, band_range = self.__Select_Band_Range(self.cube)
        if band_cube is None:
            return
        band_cube = self.__Apply_Correction(band_cube, band_range)

        band_image = np.mean(band_cube, axis=-1, dtype=np.float32)
        self.live_band_image = np.ascontiguousarray(band_image.T)
        self.live_band_index = band_range
        self.live_band_lines = self.cube.shape[0]

        self.__Update_Preview()

    def __Update_Preview(self):

        if self.live_band_image is None:
            return
        image = self.live_band_image[:, :self.live_band_lines]
        align_left = True
        self.ImagePreview.Update_Preview(image, align_left = align_left)

    @pyqtSlot()
    def __Band_Range_Changed(self):
        if self.cube is not None:
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

    def __Select_Band_Range(self, data):
        if data is None:
            return None, None
        spectral_size = data.shape[-1]
        band_left, band_right = self.Status.Band1_Slider.value()
        band_left = int(band_left)
        band_right = int(band_right)
        selected = data[..., band_left:band_right+1]
        return (selected, (band_left, band_right))

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

    def __Apply_Correction(self, data, band_range=None):
        if data is None:
            return None

        if (self.dark is None and self.flat is None):
            return data

        result = np.asarray(data, dtype=np.float32).copy()
        dark = self.dark
        flat = self.flat

        if band_range is not None:
            left, right = band_range
            if dark is not None:
                dark = dark[:, left:right + 1]
            if flat is not None:
                flat = flat[:, left:right + 1]
        if dark is not None:
            result -= dark
        if flat is not None:
            result *= flat

        return result

    def __Correction_State_Changed(self):
        self.__Update_Correction_Model()

        if self.cube is not None:
            self.__Update_Band_Image()
        self.__Update_Spectrum()

        if self.roi is not None:
            self.__Update_ROI_Spectrum()

    def __Update_Correction_Model(self):

        self.flat = None

        dark_activate = (self.Dark_Enable_Checkbox.isChecked() and self.dark_frame is not None)
        flat_activate = (self.Flat_Enable_Checkbox.isChecked() and self.flat_frame is not None)

        self.dark = self.dark_frame if dark_activate else None

        if flat_activate:
            flat_reference = self.flat_frame.copy()
            if dark_activate:
                flat_reference -= self.dark

            threshold = max(1.0, 0.01*float(np.nanpercentile(flat_reference, 95)))
            valid = flat_reference > threshold

            if np.any(valid):
                normalization = float(np.mean(flat_reference[valid]))
                flat = np.zeros_like(flat_reference, dtype=np.float32)
                flat[valid] = normalization / flat_reference[valid]
                self.flat = flat.copy()

    def __Image_Spectrum_Position_Selected(self, preview_mode, x, y):
        self.roi = None
        self.ImagePreview.PreviewLabel.clear_roi()

        self.spectrum_x = x
        self.spectrum_y = y
        self.__Update_Spectrum()

    def __Update_Spectrum(self):

        if self.cube is None:
            return

        x = int(np.clip(self.spectrum_x, 0, self.cube.shape[0] -1))
        y = int(np.clip(self.spectrum_y, 0, self.cube.shape[1] - 1))

        intensity = self.__Apply_Spectrum_Correction(self.cube[x, y, :], y)

        spectral_size = self.cube.shape[2]
        if (self.wavelength_range is not None and len(self.wavelength_range) == spectral_size and self.calibration_enabled):
            x_axis = self.wavelength_range
            self.SpectrumPreview.set_x_axis_mode(True)
        else:
            x_axis = np.arange(spectral_size)
            self.SpectrumPreview.set_x_axis_mode(False)

        intensity_T = self.__Transform_Spectrum(intensity)

        self.SpectrumPreview.set_spectrum(x_axis, intensity_T)
        return intensity

    def __Apply_Spectrum_Correction(self, spectrum, spatial_y):
        result = np.asarray(spectrum, dtype=np.float32).copy()
        if self.dark is not None:
            result -= self.dark[spatial_y, :]
        if self.flat is not None:
            result *= self.flat[spatial_y, :]

        return result

    def __Update_Wavelength_Calibration(self):
        pixel_left = self.Status.Calibration_Wavelength_StartPixel_Spinbox.value()
        pixel_right = self.Status.Calibration_Wavelength_EndPixel_Spinbox.value()
        wavelength_left = self.Status.Calibration_Wavelength_Startwl_Spinbox.value()
        wavelength_right = self.Status.Calibration_Wavelength_Endwl_Spinbox.value()

        if pixel_right <= pixel_left:
            self.wavelength_range = None
            self.Status.Calibration_Wavelength_Value.setText("Invalid Pixel Range")
            return

        if self.cube is not None:
            spectral_size = self.cube.shape[-1]
        else:
            spectral_size = self.Status.Calibration_Wavelength_EndPixel_Spinbox.maximum() + 1

        slope = (wavelength_right - wavelength_left) / (pixel_right - pixel_left)

        pixels = np.arange(spectral_size, dtype=np.float32)
        self.wavelength_range = wavelength_left + (pixels - pixel_left) * slope
        self.Status.Calibration_Wavelength_Value.setText(f"{self.wavelength_range[0]:.1f} - {self.wavelength_range[-1]:.1f} nm")
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

    @pyqtSlot(bool, int, int, int, int)
    def __Image_ROI_Selected(self, preview_mode, x0, y0, x1, y1):

        self.roi = (x0, y0, x1, y1)
        self.__Update_ROI_Spectrum()

    def __Update_ROI_Spectrum(self):
        if self.roi is None:
            return
        cube = self.cube
        if cube is None:
            return
        x0, y0, x1, y1 = self.roi
        x0 = int(np.clip(x0, 0, cube.shape[0] - 1))
        x1 = int(np.clip(x1, x0, cube.shape[0] - 1))
        y0 = int(np.clip(y0, 0, cube.shape[1] - 1))
        y1 = int(np.clip(y1, y0, cube.shape[1] - 1))
        roi_cube = np.asarray(cube[x0:x1+1, y0:y1+1], dtype=np.float32)

        if self.dark is not None:
            roi_cube -= self.dark[y0:y1 +1, :][None, :, :]
        if self.flat is not None:
            roi_cube *= self.flat[y0:y1 +1, :][None, :, :]

        mean_spectrum = np.mean(roi_cube, axis=(0, 1))

        spectral_size = mean_spectrum.size
        if (self.calibration_enabled and self.wavelength_range is not None and len(self.wavelength_range) == spectral_size):
            x_axis = self.wavelength_range
            self.SpectrumPreview.set_x_axis_mode(True)
        else:
            x_axis = np.arange(spectral_size)
            self.SpectrumPreview.set_x_axis_mode(False)

        mean_spectrum_T = self.__Transform_Spectrum(mean_spectrum)
        self.SpectrumPreview.set_spectrum(x_axis, mean_spectrum_T)
        return mean_spectrum

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

    def __Reflectance_To_Absorbance(self, reflectance):
        return -np.log10(np.clip(reflectance, 1E-6, None))

    def __SNV(self, spectrum):
        spectrum = np.asarray(spectrum, dtype=np.float32)
        mean = np.nanmean(spectrum)
        std = np.nanstd(spectrum)

        if std <= 1E-12:
            return spectrum
        return (spectrum - mean) / std

    def __Transform_Spectrum(self, reflectance):
        mode = self.SpectrumPreview.Spectrum_Mode_Radio.checkedButton().text()
        if mode == "Pseudo-Absorbance":
            spectrum = self.__Reflectance_To_Absorbance(reflectance)
        else:
            spectrum = reflectance.copy()

        if self.SpectrumPreview.SNV_Checkbox.isChecked():
            spectrum = self.__SNV(spectrum)
        return spectrum

    def __Add_Current_ROI(self):
        if self.roi is None:
            spectrum_R = self.__Update_Spectrum()
        else:
            spectrum_R = self.__Update_ROI_Spectrum()

        if spectrum_R is None:
            QMessageBox.warning(self, "ROI", "Spectrum not found.")
            return

        material = self.AnalysisTab.A.Material_Combo.currentText().strip()
        specimen = self.Analysis.Specimen_Edit.text().strip()

        x0, y0, x1, y1 = self.roi
        pixel_count = (x1 - x0 + 1) * (y1 - y0 + 1)
        roi_id = f"ROI_{len(self.roi_dataset) + 1:04d}"
        self.roi_dataset[roi_id] = {"material": material, "specimen": specimen, "cube_path":self.cube_path,
                                    "roi": tuple(self.roi), "pixel_count": pixel_count, "wavelength": self.wavelength_range.copy(),
                                    "reflectance": spectrum_R.copy(), "dark_path": self.dark_path, "flat_path": self.flat_path}
        self.__Add_ROI_To_Tree(roi_id)




if __name__ == '__main__':
    mp.freeze_support()
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())