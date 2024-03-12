import os

from .env import ClientSettings
from .client import MechArmClient

client_settings = ClientSettings()


def main():
    client = MechArmClient("", client_settings)

    client.connect()
