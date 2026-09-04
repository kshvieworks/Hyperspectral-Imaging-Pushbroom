import numpy as np
from PyQt6.QtCore import (QObject, QThread, QTimer, pyqtSignal, pyqtSlot)
import multiprocessing as mp
from queue import Empty, Full

import CameraControl as CC
import StageControl as SC

import time

from pecamerapy.include._pecamerapy import Metadata

def put_latest(queue, data):
    try:
        queue.put_nowait(data)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        try:
            queue.put_nowait(data)
        except Full:
            pass

def camera_process_main(serial, exposure, fps, temperature, frame_queue, status_queue, stop_event):
    camera = None
    frame_queue.cancel_join_thread()
    try:
        camera = CC.Controller(serial)
        camera.open()
        camera.Configure(exposure_s = exposure, temperature_c = temperature)
        camera.Start_Preview(fps=fps, buffer_size=3)
        status_queue.put(("connected", None))
        while not stop_event.is_set():
            image, metadata = camera.Get_Preview_Frame(timeout_s = 1)
            if stop_event.is_set():
                break
            put_latest(frame_queue, image)
    except Exception as e:
        status_queue.put(("error", f"{type(e).__name__}: {e}"))
    finally:
        if camera is not None:
            try:
                camera.Stop_Acquisition()
            except Exception:
                pass
            try:
                camera.close()
            except Exception:
                pass
        try:
            status_queue.put(("disconnected", None))
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

    def __init__(self, stage, camera, start_mm, stop_mm, step_mm, exposure_s):
        super().__init__()
        self.stage = stage
        self.camera = camera
        self.start_mm = start_mm
        self.stop_mm = stop_mm
        self.step_mm = step_mm
        self.exposure_s = exposure_s

        self.running = True

    @pyqtSlot()
    def run(self):
        try:

            self.camera.configure(self.exposure_s)

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


class StageWorker(QObject):
    connected = pyqtSignal(float)
    position_updated = pyqtSignal(float)
    motion_started = pyqtSignal()
    motion_finished = pyqtSignal(float)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.stage = None

        self.motion_timer = QTimer()
        self.motion_timer.setInterval(50)
        self.motion_timer.timeout.connect(self._poll_motion)

    @pyqtSlot(str)
    def connect_stage(self, stage):

        try:
            self.stage = SC.Controller
            position = self.stage.position
            self.connected.emit(position)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    @pyqtSlot(float)
    def move_to(self, position):
        if self.stage is None:
            return
        try:
            self.stage.move_to(position)
            self.motion_started.emit()
            self.motion_timer.start()

        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    @pyqtSlot(float)
    def jog(self, distance):
        if self.stage is None:
            return
        try:
            self.stage.jog(distance)
            self.motion_started.emit()
            self.motion_timer.start()
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    @pyqtSlot(float)
    def set_speed(self, speed):
        if self.stage is None:
            return
        try:
            self.stage.set_speed(speed)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    @pyqtSlot()
    def stop(self):
        if self.stage is None:
            return
        try:
            self.stage.stop()
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    @pyqtSlot()
    def home(self):
        if self.stage is None:
            return
        try:
            self.stage.home()
            self.motion_started.emit()
            self.motion_timer.start()

        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    @pyqtSlot()
    def _poll_motion(self):
        if self.stage is None:
            return
        try:
            position = self.stage.position()
            self.position_updated.emit(position)
            if not self.stage.is_moving():
                self.motion_timer.stop()
                self.motion_finished.emit(position)

        except Exception as e:
            self.motion_timer.stop()
            self.error.emit(f"{type(e).__name__}: {e}")
















