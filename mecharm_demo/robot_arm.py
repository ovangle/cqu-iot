#pip install paho-mqtt

import paho.mqtt.client as mqtt
from pymycobot.mycobot import MyCobot
from pymycobot.genre import Angle
from pymycobot import PI_PORT, PI_BAUD
import time

topic = "application/robotarm/mel_01"

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("$SYS/#")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))

#get angles
def angles(mc):
    # Get the coordinates of the current location
    angle_datas = mc.get_angles()
    parsed_angle = str(angle_datas)
    print(parsed_angle)
    return parsed_angle

def main():
    mc = MyCobot(PI_PORT, PI_BAUD)
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set("MEL-RA01", "DDUvdNb2C5BQ9aLq29Lw")
    #client.connect("192.168.75.179", 8883, 60)
    client.connect("node-red.cqu.edu.au", 8883, 60)
    while(True):
    #payload = input("prompt\n")
        payload = angles(mc)
        client.publish(topic, payload=payload, qos=0, retain=False)
    # Blocking call that processes network traffic, dispatches callbacks and
        time.sleep(1)
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.

    #client.loop_forever()

if __name__ == "__main__":
    main()

