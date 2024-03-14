from typing import TypeVar
from pydantic_settings import BaseSettings
from asyncio_mqtt.client import Client as MQTTClient

from ..core import MechArmAction, MechArmInfo, MechArmSessionInfo

class MQTTClientSettings(BaseSettings):
    """
    These user settings can be assumed to
    be bound in the elephant robotics raspberry PI
    controller environment.
    """

    # The hostname of the iot server that the
    # robot arm is connected to.
    MQTT_HOSTNAME: str = "node-red.cqu.edu.au"
    MQTT_PORT: int = 8883

    # The username/password of an READ/WRITE user
    # for the mqtt broker.
    MQTT_USER: str
    MQTT_PASSWORD: str

    # The application ID of the mecharm we are using
    MQTT_APP_ID: str
    MQTT_DEVICE_ID: str

class BaseMechArmMQTT:
    settings: MQTTClientSettings
    client: MQTTClient

    @property
    def device_topic_prefix(self):
        return f"/application/{self.settings.MQTT_APP_ID}/device/{self.settings.MQTT_DEVICE_ID}"

    @property
    def action_topic(self):
        return f"{self.device_topic_prefix}/down"
    
    @property
    def event_topic(self):
        return f"{self.device_topic_prefix}/up"

    @property
    def mech_arm_info(self):
        return MechArmInfo(client_id=self.client.id)

class BaseMechArmMQTTSession:
    mech_arm: BaseMechArmMQTT
    client: MQTTClient
    session_id: int
    remote_client_id: str

    @property
    def session_topic_prefix(self):
        return f"{self.mech_arm.device_topic_prefix}/sessions/{self.session_id}"

    @property
    def session_action_topic(self):
        return f"{self.session_topic_prefix}/down"

    @property
    def session_events_topic(self):
        return f"{self.session_topic_prefix}/up"

    @property
    def session_info(self) -> MechArmSessionInfo:
        return MechArmSessionInfo(
            id=self.session_id,
            client_id=self.client.id,
            remote_client_id=self.remote_client_id,
        )

    @property
    def mech_arm_info(self) -> MechArmInfo:
        return MechArmInfo(
            client_id=self.client.id
        )

TAction = TypeVar('TAction', bound=MechArmAction)
