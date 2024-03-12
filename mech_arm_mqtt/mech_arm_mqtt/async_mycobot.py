from abc import abstractmethod
from asyncio import AbstractEventLoop, Future
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, AsyncIterable, Awaitable, Callable, Generic, TypeVar
from pymycobot import MyCobot # type: ignore

from .schema.actions import MechArmAction, MoveAction
from .schema.events import ActionResponse, MechArmEvent, MoveComplete, SessionExit, SessionNotReadyError
from .schema.protocol import MechArmSession

TAction = TypeVar('TAction', bound=MechArmAction)

class MechArmTask(Generic[TAction]):
    def __init__(
        self, 
        action: TAction,
        on_complete: Callable[[ActionResponse[TAction]], None]
    ):
        self.action = action
        self.on_complete = on_complete

    @abstractmethod
    def __call__(self, bot: MyCobot) -> ActionResponse[TAction]:
        raise NotImplementedError

class MoveTask(MechArmTask[MoveAction]):
    def __call__(self, bot: MyCobot):
        bot.send_coords(list(self.action.to_coords))
        return MoveComplete(
            action=self.action,
            coords=self.action.to_coords
        )


class AsyncMyCobot(MechArmSession):
    def __init__(self, mecharm_port: int):
        self.mecharm_port = mecharm_port

        self._loop = asyncio.get_running_loop()
        self._thread_executor = ThreadPoolExecutor(max_workers=1)
        self._task_queue: asyncio.Queue[MechArmTask]
        self._current_task = None

    def get_bot(self) -> MyCobot:
        return MyCobot(self.mecharm_port)

    def get_coords(self) -> tuple[int, int, int]:
        return self.get_bot().get_coords()

    async def run(self):
        if self._current_task is None:
            raise RuntimeError("Can only execute at most one command at a time")

        next_task = await self._task_queue.get()
        self._current_task = next_task
        result = await self.loop.run_in_executor(
            self._thread_executor, 
            next_task
        )
        next_task.on_complete(result)
        self._current_task.task_done()
        self._current_task = None

    async def set_response(self, response: MoveComplete):
        pass

    _move_complete: AsyncIterable[MoveComplete]

    async def move(
        self, move_action: MoveAction
    ) -> MoveComplete:
        future = self._loop.create_future()
        def on_move_complete(complete: MoveComplete): 
            future.set_result(complete)

        await self._task_queue.put(MoveTask(move_action, on_move_complete))
        return await future

    async def exit(self):
        return SessionExit()
