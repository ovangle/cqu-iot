from enum import IntEnum


class MechArmError(IntEnum):
    BAD_ACTION = 300
    SESSION_BUSY = 400
    MOVE_ERROR = 500
