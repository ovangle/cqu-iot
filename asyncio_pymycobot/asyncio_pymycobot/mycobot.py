from __future__ import annotations

import asyncio
from typing import Callable, Literal, TypedDict
from pymycobot import MyCobot

class MoveProgressInfo(TypedDict):
    pass

class Coords(TypedDict):
    head: tuple[int, int, int]
    orientation: tuple[int, int, int]

JointAngles = tuple[float, float, float, float, float, float]
JointRadians = tuple[float, float, float, float, float, float]

class AsyncMyCobot:
    def __init__(
        self,
        port: int,
        baudrate: str = '115200',
        timeout=0.1,
        debug=False,
        thread_lock=True
    ):
        self._delegate = MyCobot(
            port,
            baudrate=baudrate,
            timeout=timeout,
            debug=debug,
            thread_lock=thread_lock
        )
        self._loop = asyncio.get_running_loop()

    def get_robot_version(self) -> int:
        return self._delegate.get_robot_version()

    def get_system_version(self) -> int:
        return self._delegate.get_system_version()

    def get_robot_id(self) -> int:
        return self._delegate.get_robot_id()

    def set_robot_id(self, id: int):
        return self._delegate.set_robot_id(id)

    def release_all_servos(self, damping_mode: Literal['damped', 'undamped'] = 'damped'):
        self._delegate.release_all_servos(
            1 if damping_mode == 'undamped' else 0
        )

    def is_moving(self):
        return self._delegate.is_moving()

    def pause(self):
        return self._delegate.pause()

    def resume(self):
        return self._delegate.resume()

    def is_paused(self):
        return self._delegate.is_paused()

    def stop(self):
        self._cancel_tasks()
        return self._delegate.stop()

    def get_radians(
        self, 
    ) -> JointRadians:
        return tuple(self._delegate.get_radians())

    async def send_radians(
        self,
        radians: JointRadians,
        speed: int = 50,
        on_progress: Callable[[MoveProgressInfo], None] | None = None
    ) -> None:
        raise NotImplementedError

    def get_angles(self) -> JointAngles:
        return tuple(self._delegate.get_angles())

    def sync_send_angles(
        self,
        degrees: JointAngles,
        speed: int = 50,
        timeout: int = 15
    ) -> AsyncMyCobot:
        self._delegate.sync_send_angles(degrees, speed, timeout)
        return self

    async def send_angle(
        self,
        joint_id: int,
        angle: float,
        speed: int = 50,
        on_progress: Callable[[MoveProgressInfo], None] | None = None
    ) -> None:
        raise NotImplementedError

    def get_coords(self) -> Coords:
        raw_coords = self._delegate.get_coords()
        return {
            "head": tuple(raw_coords[:3]),
            "orientation": tuple(raw_coords[3:])
        }

    def sync_send_coords(
        self,
        coords: Coords,
        speed: int = 50,
        mode: Literal['angular', 'linear'] = 'linear',
        timeout: int = 15
    ) -> AsyncMyCobot:
        coord_list = [*coords["head"], *coords["orientation"]]
        self._delegate.sync_send_coords(coord_list, speed, 0 if mode == 'angular' else 1, timeout)
        return self

    async def send_coords(
            self,
        coords: Coords,
        speed: int = 50,
        mode: Literal['angular', 'linear'] = 'linear',
        on_progress: Callable[[MoveProgressInfo], None] | None = None
    ) -> None:
        raise NotImplementedError

    def is_at_coords(self, coords: Coords) -> bool:
        return self._delegate.is_in_position(
            [*coords["head"], *coords["orientation"]],
            1
        )

    def get_acceleration(self):
        return self._delegate.get_acceleration()

    def set_acceleration(self, acceleration: float):
        return self._delegate.set_acceleration(acceleration)

    def get_speed(self):
        return self._delegate.get_speed()

    def set_speed(self, speed: int = 50):
        self._delegate.set_speed(speed)
