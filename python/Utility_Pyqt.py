import numpy as np
import imageio
from PyQt6 import QtGui
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QApplication, QFileDialog, QLabel, QSpinBox, QRubberBand
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QRect, QPoint, QSize

import cv2
import os
import sys
import glob
from os import listdir
from os.path import isfile, isdir, join


class WidgetDesign:

    @staticmethod
    def Layout_Widget(Widgets, Orientation='Vertical'):
        Layout = QtWidgets.QVBoxLayout()
        if Orientation == 'Horizontal':
            Layout = QtWidgets.QHBoxLayout()
        elif Orientation == 'Stacked':
            Layout = QtWidgets.QStackedLayout()

        try:
            for Widget_k in Widgets:
                Layout.addWidget(Widget_k)
        except TypeError:
            Layout.addWidget(Widgets)

        return Layout

    @staticmethod
    def Layout_Frame_Layout(UpperLayout, LowerLayout, Title):
        GroupBox = QtWidgets.QGroupBox(Title)
        GroupBox.setLayout(LowerLayout)
        UpperLayout.addWidget(GroupBox)
        del LowerLayout

    @staticmethod
    def Init_Entry(Entry, DefaultVal, Size=(200, 30), AlignPos=QtCore.Qt.AlignmentFlag.AlignCenter):
        Entry.setAlignment(AlignPos)
        Entry.setText(str(DefaultVal))
        Entry.setFixedSize(Size[0], Size[1])

class WidgetFunction:
    @staticmethod
    def tabClicked(Tab):
        Tab.BindConfigurationVariables()

    @staticmethod
    def Checkbox_Toggle(checked, btn):
        btn.setEnabled(checked)

    @staticmethod
    def Open_File(caption = "Open File", directory = "", filter = "All Files (*)"):
        if not directory:
            directory = os.getcwd()

        filepath, _ = QFileDialog.getOpenFileName(parent=None, caption=caption, directory=directory, filter = filter)
        return filepath

    @staticmethod
    def Select_Path():
        fd = os.getcwd()

        folderpath = QFileDialog.getExistingDirectory(parent=None, caption="Open Folder", directory=f"{fd}/")
        return folderpath


class CustomFunction:

    @staticmethod
    def cv2qt(cvimage, vmin=None, vmax=None):
        """Convert from an opencv image to QPixmap"""

        if cvimage is None or cvimage.size == 0:
            return None

        # 1. Adjust and Normalize to Target bit depth
        display_image = CustomFunction.Normalize_Image(cvimage, vmin, vmax)
        display_image = np.ascontiguousarray(display_image, dtype=np.uint8)
        # 2. Resize
        # cvimage_bit = cv2.resize(cvimage_bit, dsize=(0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)

        # 3. Convert CV RGB Style
        # if len(cvimage_bit.shape) == 2:
        #     rgb_image = cv2.cvtColor(cvimage_bit, cv2.COLOR_GRAY2RGB)
        # else:
        #     rgb_image = cv2.cvtColor(cvimage_bit, cv2.COLOR_BGR2RGB)

        # 4. Convert to QT Style
        h, w = display_image.shape
        # bytes_per_line = (display_image.strides[0])
        qimage = QtGui.QImage(display_image.data, w, h, display_image.strides[0], QtGui.QImage.Format.Format_Grayscale8).copy()
        # p = convert_to_Qt_format.scaled(self.disply_width, self.display_height, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        return QtGui.QPixmap.fromImage(qimage)

    @staticmethod
    def Normalize_Image(cvimage, vmin, vmax):
        """Normalize and convert image depth into bitdepth"""

        c_min = float(vmin) if vmin is not None else float(np.min(cvimage))
        c_max = float(vmax) if vmax is not None else float(np.max(cvimage))

        if c_max == c_min:
            c_max = c_min + 1

        img_normalized = np.clip(cvimage, c_min, c_max)
        cvimage_bit = ((2**8-1) * (img_normalized - c_min) / (c_max - c_min)).astype(np.uint8)

        return cvimage_bit

    @staticmethod
    def Read_Image(filepath, fileformat, filedtype, ImageSize):
        read_data = np.array([], dtype=np.float64)
        file_now = filepath

        if os.path.isdir(filepath):
            search_pattern = os.path.join(filepath, f'*.{fileformat}')
            list_of_files = glob.glob(search_pattern)

            if not list_of_files:
                return None
            file_now = max(list_of_files, key=os.path.getmtime)
        elif not os.path.isfile(filepath):
            return None

        # try:
        #     onlyfiles = [f for f in listdir(filepath) if isfile(join(filepath, f))]
        #     file_now = onlyfiles[-1]
        # except NotADirectoryError:
        #     file_now = filepath

        if fileformat == 'raw':
                try:
                    read_data = EventHelper.Read_RawFile(file_now, fileformat, filedtype, ImageSize)
                except ValueError:
                    print(f'{file_now} Skipped')

        elif fileformat == ('tif' or 'tiff' or 'png'):
            try:
                read_data = EventHelper.Read_cv2File(file_now, fileformat, filedtype, ImageSize)

            except ValueError:
                print(f'{file_now} Skipped')

        elif fileformat == 'bin':
            try:
                read_data = EventHelper.Read_binFile(file_now, fileformat, filedtype, ImageSize)

            except ValueError:
                print(f'{file_now} Skipped')
        return np.array(4095-read_data, dtype=np.float64)


class EventHelper:
    @staticmethod
    def Read_RawFile(filenow, fileformat, filedtype, ImageSize):
        fid = open(filenow, "rb")
        read_data_now = np.fromfile(fid, dtype=filedtype, sep="")
        read_data_now = read_data_now.reshape(ImageSize)
        fid.close()
        return read_data_now

    @staticmethod
    def Read_cv2File(filenow, fileformat, filedtype, ImageSize):
        read_data_now = cv2.imread(filenow, cv2.IMREAD_UNCHANGED)
        return read_data_now

    @staticmethod
    def Read_binFile(filenow, fileformat, filedtype, ImageSize):
        read_data_now = np.fromfile(filenow, dtype=filedtype)
        read_data_now = read_data_now.reshape(ImageSize)
        return read_data_now

    @staticmethod
    def Save_Files(filepath, filedtype, dformat, data, fnlist=False):

        filepath, selected_filter = QFileDialog.getSaveFileName(parent=None, caption="Save as", dir=filepath, filter="All Files(*)")

        for k, d in enumerate(data):
            if fnlist:
                fname = filepath + f"/{fnlist[k][:-4]}.{dformat}"
            else:
                fname = filepath + f"/IMG{k:04} + W{data.shape[1]}xH{data.shape[2]} {filedtype.__name__}.{dformat}"
            if dformat == 'raw':
                with open(fname, 'wb') as f:
                    f.write((d.astype(filedtype)).tobytes())
                    f.close()
            elif dformat == "tif":
                imageio.imwrite(fname, d.astype(filedtype))

class SliderHelper:

    @staticmethod
    def _init_range_slider(Slider, Spin_L, Spin_R, Value_L, Value_R, step = 1):
        Slider.setOrientation(Qt.Orientation.Horizontal)
        Slider.setRange(Value_L, Value_R)
        Slider.setValue((Value_L, Value_R))
        Slider.setSingleStep(step)

        Spin_L.setRange(Value_L, Value_R)
        Spin_L.setValue(Value_L)

        Spin_R.setRange(Value_L, Value_R)
        Spin_R.setValue(Value_R)


    @staticmethod
    def RangeSpinChanged(Spin_Left, Spin_Right, Slider):

        Current_Left, Current_Right = Slider.value()

        if Spin_Left > Current_Right:
            Spin_Left = Current_Right

        if Spin_Right < Current_Left:
            Spin_Right = Current_Left

        Slider.setValue((Spin_Left, Spin_Right))

    @staticmethod
    def RangeSliderChanged(Spin_Left, Spin_Right, values):
        minimum, maximum = values
        Spin_Left.setValue(minimum)
        Spin_Right.setValue(maximum)


class ClickableImageLabel(QLabel):
    pixel_clicked = QtCore.pyqtSignal(int, int)
    roi_selected = QtCore.pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_shape = None

        self.drag_start = None
        self.dragging = False
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def set_image_shape(self, shape):
        self.image_shape = shape

    def clear_roi(self):
        self.drag_start = None
        self.rubber_band.hide()

    def mousePressEvent(self, event):
        if (event.button() != QtCore.Qt.MouseButton.LeftButton):
            return

        position = self._Label_to_Image(event.position().x(), event.position().y())

        if position is None:
            return

        self.drag_start = event.position().toPoint()
        self.dragging = False
        self.rubber_band.setGeometry(QRect(self.drag_start, QSize()))
        self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if self.drag_start is None:
            return
        current = event.position().toPoint()
        rect = QRect(self.drag_start, current).normalized()

        if (rect.width() >= 3 or rect.height() >= 3):
            self.dragging = True
        self.rubber_band.setGeometry(rect)

    def mouseReleaseEvent(self, event):
        if self.drag_start is None:
            return
        end_point = event.position().toPoint()
        start_image = self._Label_to_Image(self.drag_start.x(), self.drag_start.y())
        end_image = self._Label_to_Image(end_point.x(), end_point.y())

        if (start_image is None or end_image is None):
            self.drag_start = None
            self.rubber_band.hide()
            return

        x0, y0 = start_image
        x1, y1 = end_image
        if not self.dragging:
            self.pixel_clicked.emit(x0, y0)
            self.rubber_band.hide()
        else:
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            self.roi_selected.emit(x0, y0, x1, y1)

        self.drag_start = None
        self.dragging = False

    def _Label_to_Image(self, label_x, label_y):

        alignment = self.alignment()

        pixmap = self.pixmap()
        if (pixmap is None or self.image_shape is None):
            return

        label_w = self.width()
        label_h = self.height()

        pix_w = pixmap.width()
        pix_h = pixmap.height()

        if alignment & QtCore.Qt.AlignmentFlag.AlignLeft:
            x_offset = 0
        elif alignment & QtCore.Qt.AlignmentFlag.AlignRight:
            x_offset = label_w - pix_w
        else:
            x_offset = (label_w - pix_w) / 2

        if alignment & QtCore.Qt.AlignmentFlag.AlignTop:
            y_offset = 0
        elif alignment & QtCore.Qt.AlignmentFlag.AlignBottom:
            y_offset = label_h - pix_h
        else:
            y_offset = (label_h - pix_h) / 2

        x = label_x - x_offset
        y = label_y - y_offset

        if(x<0 or y<0 or x>=pix_w or y>=pix_h):
            return

        image_h, image_w = self.image_shape[:2]
        image_x = int(x*image_w/pix_w)
        image_y = int(y*image_h/pix_h)

        image_x = np.clip(image_x, 0, image_w-1)
        image_y = np.clip(image_y, 0, image_h-1)

        return (int(image_x), int(image_y))





#
# class ROIControl(QtWidgets.QWidget):
#     roichanged = QtCore.pyqtSignal(float, float)
#
#     def __init__(self, parent=None, minimum=0, maximum=640):
#         super().__init__(parent)
#         self.minimum = minimum
#         self.maximum = maximum