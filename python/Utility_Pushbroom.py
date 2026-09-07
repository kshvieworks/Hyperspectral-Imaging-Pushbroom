import numpy as np
from PyQt6.QtCore import (QObject, QThread, QTimer, pyqtSignal, pyqtSlot)
import multiprocessing as mp
from queue import Empty, Full

import CameraControl as CC
import StageControl as SC

import time

from pecamerapy.include._pecamerapy import Metadata

'''
Manual Control for Camera
'''

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
        camera.Start_Preview(fps=fps, buffer_size=1)
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

'''
Cube Builder
'''

def build_scan_positions(start_mm, end_mm, step_mm):
    if step_mm <= 0:
        raise ValueError("Step size must be greater than 0")
    if end_mm < start_mm:
        raise ValueError("End mm must be greater than start position.")

    n_steps = int(np.floor((end_mm - start_mm)/step_mm)) + 1
    positions = (start_mm + np.arange(n_steps) * step_mm)
    return positions

def acquisition_process_main(camera_serial, stage_serial, exposure, temperature, stage_speed, start_mm, end_mm, step_mm, settle_s, output_path, frame_queue, status_queue, stop_event):
    camera = None
    stage = None
    cube = None

    try:
        # --------------
        # Open Camera
        # --------------
        camera = CC.Controller(camera_serial)
        camera.open()
        camera.Configure(exposure_s = exposure, temperature_c = temperature)

        # --------------
        # Open Stage
        # --------------
        stage = SC.Controller(stage_serial)
        stage.set_speed(stage_speed)

        # --------------
        # Build Positions
        # --------------
        positions = build_scan_positions(start_mm, end_mm, step_mm)
        n_lines = len(positions)
        status_queue.put(("started", {"lines": n_lines}))

        acquired_lines = 0

        # --------------
        # Step and Shoot
        # --------------
        for i, position_mm in enumerate(positions):
            if stop_event.is_set():
                break

            # 1. Move
            stage.move_to(position_mm)

            # 2. Wait
            stage.wait_move()
            if stop_event.is_set():
                break

            # 3. Settling
            if settle_s > 0:
                time.sleep(settle_s)

            # 4. Capture
            image_now, metadata = (camera.Acquire_Frame())

            # 5. Allocate Cube at first frame
            if cube is None:
                cube = np.empty((n_lines, image_now.shape[0], image_now.shape[1]), dtype = image_now.dtype)

            # 6. Store
            cube[i, :, :] = image_now
            acquired_lines += 1

            # 7. Send latest frame
            put_latest(frame_queue, image_now)

            # 8. Status
            status_queue.put(("progress", {"index": i+1, "total": n_lines, "position": float(position_mm),}))

        # --------------
        # Finished / Aborted
        # --------------
        if cube is not None:
            cube = cube[:acquired_lines]
            np.save(output_path, cube)

        if stop_event.is_set():
            status_queue.put(("aborted", {"lines": acquired_lines, "path": output_path,}))
        else:
            status_queue.put(("finished", {"lines": acquired_lines, "path": output_path,}))

    except Exception as e:
        status_queue.put(("error", f"{type(e).__name__}: {e}"))
    finally:
        if stage is not None:
            try:
                stage.stop()
            except Exception:
                pass

        if camera is not None:
            try:
                camera.Stop_Acquisition()
            except Exception:
                pass

            try:
                camera.close()
            except Exception:
                pass

class StageWorker(QObject):
    connected = pyqtSignal(float)
    disconnected = pyqtSignal()
    position_updated = pyqtSignal(float)
    motion_started = pyqtSignal()
    motion_finished = pyqtSignal(float)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.stage = None

        self.motion_timer = QTimer(self)
        self.motion_timer.setInterval(50)
        self.motion_timer.timeout.connect(self._poll_motion)

    @pyqtSlot(str)
    def connect_stage(self, stage):

        try:
            self.stage = SC.Controller(stage)
            position = self.stage.position()
            self.connected.emit(position)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    @pyqtSlot()
    def disconnect_stage(self):
        if self.stage is None:
            return
        try:
            if self.motion_timer.isActive():
                self.motion_timer.stop()
            if self.stage.is_moving():
                self.stage.stop()
            self.stage.close()
            self.stage = None
            self.disconnected.emit()
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
















