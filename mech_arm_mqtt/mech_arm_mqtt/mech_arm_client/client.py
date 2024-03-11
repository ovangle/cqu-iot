from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeVar
import dataclasses
from typing import Generic
from paho.mqtt import MQTTv311
from asyncio_mqtt import Client as MQTTClient

from mech_arm_mqtt.schema.actions import (
    BeginSession,
    MechArmAction,
    action_from_json_object,
)

from .env import ClientSettings


from mech_arm_mqtt.schema.events import (
    ActionReceived,
    BroadcastEvent,
    Busy,
    BadAction,
    InvalidMessage,
    MechArmEvent,
    SessionCreated,
    SessionEvent,
    action_from_json_object,
    event_to_json_object,
)

if TYPE_CHECKING:
    from .session import MechArmSession


class MechArmClient(MQTTClient):
    def __init__(self, client_id: str, client_settings: ClientSettings):
        super().__init__(
            client_settings.MQTT_HOSTNAME,
            client_settings.MQTT_PORT,
            username=client_settings.MQTT_USER,
            password=client_settings.MQTT_PASSWORD,
            protocol=MQTTv311,
            client_id=client_id,
        )
        self.settings = client_settings

    @property
    def broadcast_topic(self):
        return f"application/{self.settings.MQTT_APP_ID}/device/{self.settings.MQTT_DEVICE_ID}/up"

    TBroadcastEvent = TypeVar("TBroadcastEvent", bound=BroadcastEvent)

    async def emit_broadcast_event(self, event: TBroadcastEvent) -> TBroadcastEvent:
        await self.publish(
            topic=self.broadcast_topic, payload=json.dumps(event_to_json_object(event))
        )
        return event

    @property
    def session_begin_topic(self):
        return f"application{self.settings.MQTT_APP_ID}/devices/{self.settings.MQTT_DEVICE_ID}/session/create"

    async def subscribe_session_begin_action(self, qos: int = 0, timeout: int = 10):
        return await self.subscribe(self.session_begin_topic, qos=qos, timeout=timeout)

    async def emit_busy(self, busy: Busy):
        return await self.emit_broadcast_event(busy)

    async def emit_session_created(self, session_created: SessionCreated):
        return self.emit_broadcast_event(session_created)

    def session_topic(self, session_id: int):
        return f"application/{self.settings.MQTT_APP_ID}/device/{self.settings.MQTT_DEVICE_ID}/session/{session_id}"

    async def subscribe_session_actions(
        self, session_id: int, qos: int = 0, timeout: int = 10
    ):
        return await self.subscribe(
            self.session_topic(session_id), qos=qos, timeout=timeout
        )

    TSessionEvent = TypeVar("TSessionEvent", bound=SessionEvent)

    async def emit_session_event(
        self, session_id: int, event: TSessionEvent
    ) -> TSessionEvent:
        assert event.session_id == session_id
        await self.publish(
            topic=self.session_topic(session_id),
            payload=json.dumps(event_to_json_object(event)),
        )
        return event

        TAction = TypeVar("TAction", bound=MechArmEvent)

    _all_action_handlers: dict[str, list[Callable[[Any], Any]]]

    def add_action_handler(
        self, action_name: str, handler: Callable[[TAction], None]
    ) -> Callable[[], None]:
        self._all_action_handlers.setdefault(action_name, [])
        handlers = self._all_action_handlers[action_name]
        handler_idx = len(handlers)
        handlers.append(handler)

        def unsubscribe():
            del handlers[handler_idx]

        return unsubscribe

    @property
    def mqtt_client_id(self):
        return self.settings.MQTT_APP_ID

    @property
    def application_topic(self):
        return f"application/{self.settings.MQTT_APP_ID}"

    @property
    def event_broadcast_topic(self) -> str:
        return f"application/{self.settings.MQTT_APP_ID}/device/+/event/up"

    def emit(self, evt: MechArmEvent):
        evt_dict = dataclasses.asdict(evt)
        self.publish(
            self.event_broadcast_topic,
            json.dumps(evt_dict),
        )

    async def on_begin_session(self, begin_session: BeginSession) -> None:
        from .session import MechArmSession

        if begin_session.mecharm_client_id != self.mqtt_client_id:
            # If this is a request for a different mecharm, then ignore.
            return

        if self.current_session is not None:
            await self.emit_busy(
                Busy(
                    controller_client_id=begin_session.controller_client_id,
                    **dataclasses.asdict(begin_session),
                )
            )
            return

        async with MechArmSession(self, begin_session.controller_client_id) as session:
            self.current_session = session

            await self.emit_session_created(
                SessionCreated(
                    session_id=self.current_session.session_id,
                    **dataclasses.asdict(begin_session),
                )
            )
