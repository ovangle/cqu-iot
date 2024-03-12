import asyncio
from typing import Any
import click

from .client import MyCobotRemoteClient

@click.group()
@click.option("--debug/--no-debug", default=False)
@click.option("--host", default="node-red.cqu-edu.au")
@click.option("--port", default=8883)
@click.option("--user")
@click.option("--password")
def controller_cli(debug, host, port, user, password):
    click.echo(f"Debug mode: {'on' if debug else 'off'}")

    client = MyCobotRemoteClient(
        host,
        port,
        username=user,
        password=password
    )

@controller_cli.command()
@click.option("--coords", default=None)
def move(ctx: Any, coords: None):
    click.echo(f"Moving to {coords}")

    asyncio.run(ctx.client.move(coords))
