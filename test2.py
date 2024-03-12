import os
import logging
from paho.mqtt.client import Client, MQTTv31

try:
    CLIENT_USER=os.environ['MQTT_USER']
    CLIENT_PASS=os.environ['MQTT_PASS']
except KeyError as e:
    raise EnvironmentError(f'{e} not bound in environment')

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('paho.mqtt')

client = Client(
    clean_session=True,
    client_id="",
    protocol=MQTTv31,
    reconnect_on_failure=False
)
client.enable_logger(logger)
client.username_pw_set(username=CLIENT_USER, password=CLIENT_PASS)

def on_connect(client, userdata, flags, rc, *args):
    client._logger.debug(f"Connected with result code {rc}", *args)
    client.subscribe("application/4dcbfc34-d6ef-49c2-99d5-992b20d80fac/device/+/event/up")

def on_connect_fail(client):
    client.logger.debug(f"Connect failed")

def on_message(client, userdata, msg):
    print(f"{msg.topic}: {msg.payload!s}")

client.on_connect_fail = on_connect_fail
client.on_connect = on_connect
client.on_message = on_message

client.connect("node-red.cqu.edu.au", 8883)
client.loop_forever()
