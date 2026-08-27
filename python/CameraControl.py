from pathlib import Path
import pecamerapy
import numpy as np

class Controller:
    def __init__(self, serial):
        self.camera = pecamerapy.Camera()
        self.serial = serial

    def open(self):
        mode = self._OpenMode()
        index, serial_selected = self.camera.find_first(mode)
        if serial_selected == self.serial:
            self.camera.open(index, mode)


    @staticmethod

    @staticmethod
    def _OpenMode():
       return pecamerapy.OpenMode.USB3




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
