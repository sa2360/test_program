"""Run one MQTT broker with exclusive TCP binding on Windows."""
import argparse
import asyncio
from functools import partial
import logging
from pathlib import Path
import socket

from amqtt.broker import Broker
from amqtt.contexts import ListenerType
from amqtt.utils import read_yaml_config


class ExclusiveBroker(Broker):
    async def _create_server_instance(self, listener_name, listener_type, address, port, ssl_context):
        if listener_type != ListenerType.TCP or not hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            return await super()._create_server_instance(listener_name, listener_type, address, port, ssl_context)
        # amqtt 0.11 uses SO_REUSEADDR, which permits competing listeners on Windows.
        sock = socket.socket(socket.AF_INET6 if address and ":" in address else socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((address or "0.0.0.0", port))
            sock.setblocking(False)
            return await asyncio.start_server(partial(self.stream_connected, listener_name=listener_name),
                                              sock=sock, ssl=ssl_context)
        except BaseException:
            sock.close()
            raise


async def serve(config):
    broker = ExclusiveBroker(config)
    await broker.start()  # Do not hide bind failures in an unobserved task.
    try:
        await asyncio.Event().wait()
    finally:
        await broker.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", type=Path, default=Path(__file__).resolve().parents[1] / "broker.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("transitions").setLevel(logging.WARNING)
    try:
        asyncio.run(serve(read_yaml_config(args.config)))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit(f"Broker startup/runtime failed: {exc}") from exc


if __name__ == "__main__":
    main()
