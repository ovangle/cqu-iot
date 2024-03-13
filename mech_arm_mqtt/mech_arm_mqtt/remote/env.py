from pydantic_settings import BaseSettings


class ClientSettings(BaseSettings):
    MQTT_HOST: str = "node-red.cqu-edu.au"
    MQTT_PORT: int = 8883

    MQTT_USER: str
    MQTT_PASSWORD: str

    MECHARM_APP_ID: str


class LocalClientSettings(ClientSettings):
    MYCOBOT_PORT: int


class RemoteClientSettings(ClientSettings):
    REMOTE_CLIENT_ID: str
