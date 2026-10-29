import json
import numpy as np
import shutil
import sys
import os
from datetime import datetime
os.environ["QT_API"] = "pyqt6"

from TestWindow import ImagePreviewWidgets, SpectrumPreviewWidgets, StatusWidgets
import multiprocessing as mp
import sys

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
                             QMessageBox, QFileDialog, QTreeWidget)

import Utility_Pyqt as Uqt


class AnalysisWidgets(QWidget):
    def __init__(self, parent=None):
        super(AnalysisWidgets, self).__init__(parent)
        self.roi_dataset = {}

    def initUI(self, Layout):
        self.UI_Component()
        self.UI_Layout(Layout)

    def UI_Layout(self, Layout):
        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Sample_Tree), 'Vertical'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'RoI List')

    def UI_Component(self):

        self.Sample_Tree = QTreeWidget()
        self.Sample_Tree.setHeaderLabels(["Sample", "ROI", "Pixel", "Cube"])



