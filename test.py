import os
from paho.mqtt.client import Client, MQTTv311

try:
    CLIENT_USER=os.environ['MQTT_USER']
    CLIENT_PASS=os.environ['MQTT_PASS']
except KeyError as e:
    raise EnvironmentError(f'{e} not bound in environment')

client = Client(
    client_id="",
    protocol=MQTTv311
)
client.username_pw_set(username=CLIENT_USER, password=CLIENT_PASS)

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe("application/4dcbfc34-d6ef-49c2-99d5-992b20d80fac/device/+/event/up")

def on_message(client, userdata, msg):
    print(f"{msg.topic}: {msg.payload!s}")

client.on_connect = on_connect
client.on_message = on_message

client.connect("cqu-iot.ovangle.com", 1884)
client.loop_forever()
