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
                             QMessageBox, QFileDialog, QTreeWidget, QComboBox, QLabel)

import Utility_Pyqt as Uqt
import pyqtgraph as pg



class AnalysisWidgets(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.roi_dataset = {}

        self.analysis_result = None

        Layout = QVBoxLayout()
        self.initUI(Layout)
        self.setLayout(Layout)

    def initUI(self, Layout):
        self.UI_Component()
        self.UI_Layout(Layout)

    def UI_Layout(self, Layout):

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addWidget(self.PCA_Plot)
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Analysis_Mode_Combo, self.PCA_Button), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.PCA_Info_Label, self.Best_Band_Label), 'Vertical'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'PCA Analysis')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((QLabel("Material"), self.Material_Combo), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((QLabel("Specimen"), self.Specimen_Combo), 'Horizontal'))
        Temp_Layout.addLayout(Uqt.WidgetDesign.Layout_Widget((self.Add_ROI_Button, self.Delete_ROI_Button), 'Horizontal'))
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'Sample Selection')

        Temp_Layout = QVBoxLayout()
        Temp_Layout.addWidget(self.Sample_Tree)
        Uqt.WidgetDesign.Layout_Frame_Layout(Layout, Temp_Layout, 'ROI Dataset')

    def UI_Component(self):

        self.Material_Combo = QComboBox()
        self.Material_Combo.addItems(['PP', 'PS', 'PE', 'PET', 'PVC'])
        self.Material_Combo.setEditable(True)

        self.Specimen_Combo = QComboBox()
        self.Specimen_Combo.setEditable(True)

        self.Add_ROI_Button = QPushButton('Add Current ROI')
        self.Delete_ROI_Button = QPushButton('Delete ROI')

        self.Sample_Tree = QTreeWidget()
        self.Sample_Tree.setHeaderLabels(["Material", "Specimen", "ROI", "Pixels", "Cube"])
        self.Sample_Tree.setRootIsDecorated(False)

        self.PCA_Button = QPushButton('Calculate PCA')
        self.PCA_Info_Label = QLabel("PCA: --")
        self.PCA_Plot = pg.PlotWidget()
        self.PCA_Plot.setLabel("bottom", "PC1")
        self.PCA_Plot.setLabel("left", "PC2")
        self.PCA_Plot.showGrid(x=True, y=True)
        self.PCA_Legend = self.PCA_Plot.addLegend()

        self.Analysis_Mode_Combo = QComboBox()
        self.Analysis_Mode_Combo.addItems(['PCA Score', 'PCA Loading', 'Wavelength Score'])
        self.Best_Band_Label = QLabel("Best Band: --")





