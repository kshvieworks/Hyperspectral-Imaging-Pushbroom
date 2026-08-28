from PyQt6.QtCore import QObject, pyqtSignal


class AcquisitionWorker(QObject):

    frame_ready = pyqtSignal(object, float, int)