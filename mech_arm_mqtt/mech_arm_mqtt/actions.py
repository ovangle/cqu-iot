from __future__ import annotations

from .core import MechArmAction, MechArmSessionInfo, SessionAction, mecharm_action


@mecharm_action("begin_session")
class BeginSession(MechArmAction):
    remote_client_id: str


@mecharm_action("end_session")
class ExitSession(SessionAction):
    exit_code: int


@mecharm_action("move")
class MoveAction(SessionAction):
    session: MechArmSessionInfo
    to_coords: tuple[int, int, int]
