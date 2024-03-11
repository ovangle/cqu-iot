from pathlib import Path
from pydantic_settings import Settings


class ClientSettings(Settings):
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
