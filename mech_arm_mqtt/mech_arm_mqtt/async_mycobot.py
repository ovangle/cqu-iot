from __future__ import annotations

from abc import abstractmethod
from asyncio import AbstractEventLoop, Future
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
from types import TracebackType
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Generic,
    Literal,
    Self,
    TypeAlias,
    TypeVar,
    cast,
)
from mech_arm_mqtt.schema.model import ActionError, ActionEvent, MechArmSessionInfo, SessionAction
from pymycobot import MyCobot  # type: ignore

from .schema.actions import BeginSession, MechArmAction, MoveAction
from .schema.events import (
    ActionResponse,
    MechArmEvent,
    MoveComplete,
    MoveProgress,
    ActionProgress,
    SessionCreated,
    SessionDestroyed,
    SessionReady,
)
from .schema.session import MechArmSession, MechArm

TAction = TypeVar("TAction", bound=MechArmAction)

ProgressCallback = Callable[[ActionProgress[TAction]], None]

class MyCobotTask(Generic[TAction]):
    def __init__(
        self, 
        context: MyCobotTaskContext[TAction],
        action: TAction
    ):
        self.context = context
        self.action = action

    @property
    def bot(self) -> MyCobot:
        return self.context.bot

    @property
    def session_info(self) -> MechArmSessionInfo:
        return self.context.session.info

    @abstractmethod
    def __call__(self) -> ActionResponse[TAction]:
        """
        Runs the task given the current bot.
        Raise an ActionError if the task cannot be completed.
        """
        raise NotImplementedError


class MyCobotTaskContext(AsyncContextManager, Generic[TAction]):

    def __init__(
        self, 
        session: AsyncMyCobot,
    ):
        self.session = session

        self._executor = session._executor
        self._loop = asyncio.get_running_loop()

        self._event_queue = asyncio.Queue[ActionEvent[TAction]]()

    async def events(self) -> AsyncIterator[ActionEvent[TAction]]:
        while not self._closed:
            yield await self._event_queue.get()

    @property
    def bot(self):
        return MyCobot(self.session.mecharm_port)

    async def __aenter__(self) -> MyCobotTaskContext[TAction]:
        return self

    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None = None,
        __exc_value: BaseException | None = None,
        __traceback: TracebackType | None = None,
    ) -> bool | None:
        self._closed = True
        return await super().__aexit__(__exc_type, __exc_value, __traceback)

    async def run(self, action: TAction):
        task = self.session.task_factory(self, action)
        response = await self._loop.run_in_executor(self._executor, task, action)
        await self._event_queue.put(response)

    def add_progress_notification(self, progress: ActionProgress[TAction]):
        assert self._event_queue
        self._loop.call_soon_threadsafe(self._event_queue.put, progress)

    @property
    async def notifications(self) -> AsyncIterator[ActionEvent[TAction]]:
        assert self._event_queue
        while not self._closed:
            yield await self._event_queue.get()
            await asyncio.sleep(1)

        # async for item in self._notification_queue:
        #    if not self._closed:
        #        yield item


class MoveTask(MyCobotTask[MoveAction]):
    def __init__(self, context: MyCobotTaskContext[MoveAction], action: MoveAction):
        super().__init__(context, action)
        self.progress_id = 0

    def emit_progress(self):
        coords = self.bot.get_coords()
        self.context.add_progress_notification(MoveProgress(
            name="move_progress",
            action=self.action,
            session=self.session_info,
            progress_id=self.progress_id,
            current_coords=coords,
            dest_coords=self.action.to_coords
        ))
        self.progress_id += 1

    def __call__(self):
        self.progress_id = 0
        self.bot.send_coords(list(self.action.to_coords))

        while self.bot.is_moving:
            self.emit_progress(self.action)
            time.sleep(5)

        return MoveComplete(
            name="move_complete",
            error_code=None,
            action=self.action, 
            session=self.session_info,
            coords=self.action.to_coords
        )


class AsyncMyCobot(MechArmSession):
    def __init__(
        self, session_id: int, _begin_session: BeginSession, mecharm_port: int
    ):
        self.session_id = session_id
        self._begin_session = _begin_session
        self.mecharm_port = mecharm_port

        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._action_queue = asyncio.Queue[SessionAction]()
        self._event_queue: asyncio.Queue[MechArmEvent] = asyncio.Queue()

    @property
    def client_id(self):
        return self._begin_session.mecharm_client_id

    @property
    def remote_client_id(self):
        return self._begin_session.remote_client_id

    def task_factory(self, context: MyCobotTaskContext, action: TAction) -> MyCobotTask[TAction]:
        match action.name:
            case "move":
                return cast(MyCobotTask[TAction], MoveTask(context, cast(MoveAction, action)))
            case _:
                raise ValueError(f"Unhandled task: {action.name}")

    async def on_action(self, action: TAction):
        async with MyCobotTaskContext[TAction](self) as context:
            async def relay_notifications():
                for notification in context.notifications:
                    self._event_queue.put(notification)
            loop = asyncio.get_running_loop()
            loop.call_soon(relay_notifications())
            return await context.run(action)

    async def run(self):
        while not self._closed:
            action = await self._action_queue.get()
            await self._run_action(action)

            if self._action_queue.empty():
                await self._event_queue.put(
                    SessionReady(name="session_ready", session=self.info)
                )

    async def events(self) -> AsyncIterator[MechArmEvent]:
        if not self._event_queue:
            raise ValueError('Session not initialized')
        while self._event_queue:
            yield await self._event_queue.get()

    async def __aenter__(self) -> AsyncMyCobot:
        self._executor = ThreadPoolExecutor(max_workers=1)
        await self._event_queue.put(
            SessionCreated(name="session_created", action=self._begin_session, session=self.info)
        )
        return self
    
    async def __aexit__(self, __exc_type, __exc_value, __exc_traceback) -> None:
        self._executor.shutdown()
        await self._event_queue.put(
            SessionDestroyed(name="session_destroyed", exit_code=4, session=self.info)
        )
