from __future__ import annotations

from abc import abstractmethod
from asyncio import AbstractEventLoop, Future
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from types import TracebackType
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterable,
    Awaitable,
    Callable,
    Generic,
    TypeVar,
)
from pymycobot import MyCobot

from .schema.actions import MechArmAction, MoveAction
from .schema.events import (
    ActionResponse,
    MechArmEvent,
    MoveComplete,
    MoveProgress,
    SessionExit,
    SessionNotReadyError,
    ActionProgress,
)

TAction = TypeVar("TAction", bound=MechArmAction)


class MyCobotTask(Generic[TAction]):
    def __init__(
        self, action: TAction, on_complete: Callable[[ActionResponse[TAction]], None]
    ):
        self.action = action
        self.on_complete = on_complete

    @abstractmethod
    def __call__(self, context: MyCobotTaskContext) -> ActionResponse[TAction]:
        """
        Runs the task given the current bot.
        """
        raise NotImplementedError

    def notify_progress(self, context: MyCobotTaskContext, progress: MoveProgress):
        raise NotImplementedError


TTask = TypeVar("TTask", bound=MyCobotTask)


class MyCobotTaskContext(AsyncContextManager[TTask], Generic[TTask]):
    _notification_queue: asyncio.Queue[MoveProgress] | None

    def __init__(self, task: TTask):
        self._loop = asyncio.get_running_loop()
        self._thread_executor = ThreadPoolExecutor()

        self._closed = False
        self._notification_queue = None
        self._task = task

    async def __aenter__(self) -> TTask:
        self._notification_queue = asyncio.Queue[TTask]()

        return self._task

    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None = None,
        __exc_value: BaseException | None = None,
        __traceback: TracebackType | None = None,
    ) -> bool | None:
        if __exc_type is not None:
            self._loop.call_exception_handler()

        self._closed = True
        self._notification_queue = None
        return await super().__aexit__(__exc_type, __exc_value, __traceback)

    async def run(self):
        await self._loop.run_in_executor(self._thread_executor, self._current_task)

    def add_progress_notification(self, move_progress):
        self._loop.call_soon_threadsafe(self._notification_queue.put, move_progress)

    @property
    async def progress_notifications(self):
        while not self._closed:
            yield await self._notification_queue.get()
            await asyncio.sleep()

        # async for item in self._notification_queue:
        #    if not self._closed:
        #        yield item


class MoveTask(MyCobotTask[MoveAction]):
    def __call__(self, bot: MyCobot):
        bot.send_coords(list(self.action.to_coords))

        while True:
            bot.get_coords()
        return MoveComplete(action=self.action, coords=self.action.to_coords)


class AsyncMyCobot(MechArmSession):
    def __init__(self, mecharm_port: int):
        self.mecharm_port = mecharm_port

        self._loop = asyncio.get_running_loop()
        self._thread_executor = ThreadPoolExecutor(max_workers=1)
        self._task_queue: asyncio.Queue[MyCobotTask]
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
        result = await self.loop.run_in_executor(self._thread_executor, next_task)
        next_task.on_complete(result)
        self._current_task.task_done()
        self._current_task = None

    async def set_response(self, response: MoveComplete):
        pass

    _move_complete: AsyncIterable[MoveComplete]

    async def move(self, move_action: MoveAction) -> MoveComplete:
        future = self._loop.create_future()

        def on_move_complete(complete: ActionResponse[MoveAction]):
            assert isinstance(complete, MoveComplete)
            future.set_result(complete)
            return None

        await self._task_queue.put(MoveTask(move_action, on_move_complete))
        return await future

    async def exit(self):
        return SessionExit()
