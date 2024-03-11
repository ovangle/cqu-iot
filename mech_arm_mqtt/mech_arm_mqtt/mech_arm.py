from asyncio import Future
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable
from pymycobot import MyCobot

from mech_arm_mqtt.schema.actions import MoveAction
from mech_arm_mqtt.schema.events import MoveComplete, SessionNotReadyError


@dataclass
class MechArmState:
    current_coords: Any


class MechArm:
    def __init__(self, mqtt_client_id: str, mecharm_port: int):
        self.mqtt_client_id = mqtt_client_id
        self.mecharm_port = mecharm_port

        self.loop = asyncio.get_running_loop()
        self._mecharm = MyCobot(self.mecharm_port)
        self._mecharm_thread_executor = ThreadPoolExecutor(max_workers=1)
        self._current_action = None

    def get_coords(self) -> tuple[int, int, int]:
        return self._mecharm.get_coords()

    def do_move(self, move_action: MoveAction) -> tuple[int, int, int]:
        self._mecharm.send_coords(move_action.to_coords, speed=50)
        return self.get_coords()

    def subscribe_on_event(self):
        pass

    async def move(
        self, move_action: MoveAction, on_progress: Callable[tuple[int, int, int], None]
    ) -> tuple:
        if self._current_action is not None:
            raise SessionNotReadyError(self._session, move_action)
        self.current_action = move_action.action_id

        return await self.loop.run_in_executor(
            self._mecharm_thread_executor, self.do_move
        )

    def add_on_progress_handler(self, handler: Callable[[MechArmState], None]):
        pass
