from pylablib.devices import Thorlabs

class Controller:
    def __init__(self, serial):
        POSITION_SCALE = 1_228_800
        VELOCITY_SCALE = 65_961_984
        ACCEL_SCALE = 13_584.249

        self.stage = Thorlabs.KinesisMotor(serial, scale=(POSITION_SCALE, VELOCITY_SCALE, ACCEL_SCALE))

    def position(self):
        return self.stage.get_position()

    def move_to(self, position_mm):
        self.stage.move_to(float(position_mm))
        # self.stage.wait_move()

    def move_by(self, distance_mm):
        self.stage.move_by(float(distance_mm))
        # self.stage.wait_move()

    def jog(self, distance_mm):
        self.stage.move_by(float(distance_mm))

    def home(self):
        self.stage.home(force=True)
        # self.stage.wait_move()

    def set_speed(self, speed_mm_s):
        self.stage.setup_velocity(max_velocity=float(speed_mm_s))

    def stop(self):
        try:
            self.stage.stop()
        except Exception:
            pass

    def close(self):
        self.stage.close()

    def _is_moving(self):
        return self.stage.is_moving()


# SERIAL = "49402484"
#
# POSITION_SCALE = 1_228_800
# VELOCITY_SCALE = 65_961_984
# ACCEL_SCALE = 13_584.249

# stage = Thorlabs.KinesisMotor(SERIAL, scale=(POSITION_SCALE, VELOCITY_SCALE, ACCEL_SCALE))

#
# try:
#     print("Device information:")
#     print(stage.get_device_info())
#
#     pos = stage.get_position()
#     print("Scale:", stage.get_scale())
#     print("Units:", stage.get_scale_units())
#     print("Current position", pos, "mm")
#
#     target = pos + 1
#
#     stage.move_to(target)
#     stage.wait_move()
#
#     print("Current position", stage.get_position(), "mm")
#
# finally:
#     stage.close()