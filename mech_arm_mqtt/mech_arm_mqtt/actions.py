from __future__ import annotations

from .core import MechArmAction, MechArmSessionInfo, SessionAction, mecharm_action


@mecharm_action("begin_session")
class BeginSession(MechArmAction):
    remote_client_id: str


@mecharm_action("end_session")
class ExitSession(SessionAction):
    exit_code: int

@mecharm_action("get_session_info")

@mecharm_action("set_reference_coords")
class SetReferenceCoords(SessionAction):
    """
    Set the reference coordinate system for the remainder of the session
    """
    head_coords: tuple[float, float, float]
    head_orientation: tuple[float, float, float]

    def validate(self):
        for i, coord in enumerate(self.head_coords):
            if coord < -280 or coord > 280:
                raise ValueError(f'Invalid value for head coordinate {i}. Must a float in range [-280, 280]')
        for i, offset in enumerate(self.head_orientation):
            if offset < -314 or offset > 314:
                raise ValueError(f'Invalid value for offset angle {i}. Must be a float in range [-314, 314]')


@mecharm_action("move")
class MoveAction(SessionAction):
    session: MechArmSessionInfo
    to_joint_angles: ( 
        tuple[float, float, float, float, float, float]
        | None
    ) = None

    to_joint_radians: (
        tuple[float, float, float, float, float, float]
    ) | None = None

    to_joint_values: (
        tuple[int, int, int, int, int, int, int]
        | None
    ) = None

    to_coords: tuple[float, float, float] | None = None
    head_orientation: tuple[float, float, float] | None = None

    speed: int = 50

    def validate(self, ):
        if self.to_joint_angles is not None:
            for i, angle in enumerate(self.to_joint_angles):
                if angle < -170 or angle > 170:
                    raise ValueError(f'joint {i} out of range {value}. Must be a float between -170 and 170')
        elif self.to_joint_values is not None:
            for i, value in enumerate(self.to_joint_values):
                if value < 0 or value > 4096:
                    raise ValueError(f'joint {i} out of range {value}. Must be an int in range [0, 4096]')
        elif self.to_joint_radians is not None:
            for i, value in enumerate(self.to_joint_radians):
                if value < -5 or value > 5:
                    raise ValueError(f'joint {i} out of range {value}. Must be a flaot in range (-5, 5)')
        elif self.to_coords is not None:
            if self.head_orientation is None:
                raise ValueError('Head orientation must be provided when specifying to_coords')
        else:
            raise ValueError('One of to_joint_angles, to_joint_values, to_joint_radians, to_coords must be provided')

        if self.to_coords is None and self.head_orientation is not None:
            raise ValueError('Head orientation cannot be provided when specifying to_coords')

        if self.speed < 0 or self.speed > 100:
            raise ValueError(f'Invalid value for speed {self.speed}. Must be an int in range [0, 100]')


@mecharm_action("move_joint")
class MoveJointAction(SessionAction):
    """
    Moves a single joint of the mecharm
    """
    joint: int

    # represent a value (in degrees) for the position of the mecharm
    angle: int

    speed: int = 50

    def validate(self):
        if self.joint <= 0 or self.joint > 6:
            raise IndexError('Invalid joint identifier. Must between int between 1 and 6')

        if self.angle < -170 or self.angle >= 170:
            raise IndexError(f'Invalid value for joint target {self.angle}. Must be a float between -170 and 170')

        if self.speed < 0 or self.speed > 100:
            raise IndexError(f'Invalid speed. Must be an integer in range 1-100')