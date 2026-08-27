from pylablib.devices import Thorlabs

SERIAL = "49402484"

POSITION_SCALE = 1_228_800
VELOCITY_SCALE = 65_961_984
ACCEL_SCALE = 13_584.249

stage = Thorlabs.KinesisMotor(SERIAL, scale=(POSITION_SCALE, VELOCITY_SCALE, ACCEL_SCALE))


try:
    print("Device information:")
    print(stage.get_device_info())

    pos = stage.get_position()
    print("Scale:", stage.get_scale())
    print("Units:", stage.get_scale_units())
    print("Current position", pos, "mm")

    target = pos + 1

    stage.move_to(target)
    stage.wait_move()

    print("Current position", stage.get_position(), "mm")

finally:
    stage.close()