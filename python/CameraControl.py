from pathlib import Path
import pecamerapy
import numpy as np
# 'CA000011038'

class Controller:
    def __init__(self, serial):
        self.camera = pecamerapy.Camera()
        self.serial = serial

    def open(self):
        mode = self._OpenMode()
        index = self.camera.search(mode, self.serial)
        self.camera.open(index, mode)

    def Configure(self, exposure_s = 1E-3):
        self._Configure_ExposureTime(exposure_s)

        self.camera.set_metadata_enabled(True)

    def Acquire_Frame(self):
        python_buffer_size = 10
        self.camera.capture(1, python_buffer_size)
        image, metadata = self.camera.get_image(5)
        return image, metadata

    def _Configure_ExposureTime(self, exposure_s):
        self.camera.set_exposure_time(exposure_s)

    def close(self):
        self.camera.close()

    def abort(self):
        self.camera.abort()

    @staticmethod
    def _OpenMode():
       return pecamerapy.OpenMode.USB3

# import CameraControl
# import pecamerapy
# cam = pecamerapy.Camera()
# mode = pecamerapy.OpenMode.USB3
# camera = CameraControl.Controller(cam.find_first(mode)[1])
# camera.open()

# print(dir(pecamerapy))
# cam = pecamerapy.Camera()
# mode = pecamerapy.OpenMode.USB3
# index = -1
# try:
#     index, serial = cam.find_first(mode)
# except Exception as e:
#     print(f"Error: {e}")
#     exit(-1)
# try:
#     cam.open(index, mode)
# except pecamerapy.CommOpenError as e:
#     print(f"Error: {e}")
#     exit(-1)
# my_mode = cam.get_trigger_mode()
# cam.set_trigger_mode(pecamerapy.TRIGGER_FALLING_EDGE)
# cam.set_trigger_mode(my_mode)
# cam.get_trigger_mode()
# try:
#     cam.capture(3, 3)
#     img, metadata = cam.get_image(timeout_sec=1)
#     print(f"Image values: \n {img}")
#     print(f"Counter: {metadata.counter}")
#     cam.abort()
#     cam.close()
# except Exception as e:
#     print(f"Error: {e}")
