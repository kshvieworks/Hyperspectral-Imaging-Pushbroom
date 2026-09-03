import numpy as np
from PyQt6.QtCore import (QObject, pyqtSignal, pyqtSlot)
import time

from pecamerapy.include._pecamerapy import Metadata


class CameraWorker(QObject):
    image_ready = pyqtSignal(object)
    meta_ready = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = False

    @pyqtSlot()
    def run(self):
        self.running = True

        try:
            while self.running:
                image, metadata = (self.camera.Acquire_Frame())

                if not self.running:
                    break

                self.image_ready.emit(image)
                self.meta_ready.emit(metadata)

        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
        finally:
            self.finished.emit()

    def stop(self):
        self.running = False
        try:
            self.camera.abort()
        except Exception:
            pass


class AcquisitionWorker(QObject):

    frame_ready = pyqtSignal(np.ndarray, float, int)
    spectrum_ready = pyqtSignal(np.ndarray)
    progress = pyqtSignal(int, int)
    position_changed = pyqtSignal(float)
    finished = pyqtSignal(np.ndarray)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, stage, camera, start_mm, stop_mm, step_mm, expsure_s):
        super().__init__()
        self.stage = stage
        self.camera = camera
        self.start_mm = start_mm
        self.stop_mm = stop_mm
        self.step_mm = step_mm
        self.expsure_s = expsure_s

        self.running = True

    @pyqtSlot()
    def run(self):
        try:

            self.camera.configure(self.expsure_s)

            positions = np.arange(self.start_mm, self.stop_mm + self.step_mm/2, self.step_mm,)
            n_lines = len(positions)
            self.status.emit(f"Acquisition started: {n_lines}")


            cubes = []

            for i, position_mm in enumerate(positions):
                if not self.running:
                    break

                #1. Move Stage
                self.status.emit(f"Moving stage: {position_mm:.3f} mm")
                self.stage.move_to(position_mm)
                self.position_changed.emit(position_mm)

                #2. Acquire Camera Frame
                self.status.emit(f"Acquiring line {i+1}/{n_lines}")
                image_now, metadata = self.camera.Acquire_Frame()

                #3. Store Cube
                cubes.append(image_now)

                #4. Current Spectrum
                spectrum_now = np.mean(image_now, axis=0)

                #5. Emit data to main UI
                self.frame_ready.emit(image_now, position_mm, i)
                self.spectrum_ready.emit(spectrum_now)
                self.progress.emit(i+1, n_lines)

            if len(cubes) > 0:
                cubes = np.array(cubes)
            else:
                cubes =np.empty((0, 0, 0), dtype=np.float32)

            self.status.emit("Acquisition Finished")
            self.finished.emit(cubes)

        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


    def abort(self):
        self.running = False

        try:
            self.stage.stop()
        except Exception:
            pass


















