import click
from .controller_client import ControllerClient


@click.group()
@click.option("--debug/--no-debug", default=False)
@click.option("--host", default="node-red.cqu-edu.au")
@click.option("--port", default=8883)
@click.option("--user")
@click.option("--password")
def controller_cli(debug, host, port, user, password):
    click.echo(f"Debug mode: {'on' if debug else 'off'}")

    client = ControllerClient()
