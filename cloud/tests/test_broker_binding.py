import socket
import unittest

from amqtt.contexts import ListenerType
from tools.run_broker import ExclusiveBroker


@unittest.skipUnless(hasattr(socket, "SO_EXCLUSIVEADDRUSE"), "Windows socket semantics")
class BrokerBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_broker_rejects_competing_reuseaddr_listener(self):
        broker = ExclusiveBroker({"listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
                                  "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}})
        server = await broker._create_server_instance("default", ListenerType.TCP, "127.0.0.1", 0, None)
        try:
            port = server.sockets[0].getsockname()[1]
            with socket.socket() as duplicate:
                duplicate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                with self.assertRaises(OSError):
                    duplicate.bind(("127.0.0.1", port))
                    duplicate.listen()
        finally:
            server.close()
            await server.wait_closed()

    async def test_existing_listener_prevents_new_broker(self):
        broker = ExclusiveBroker({"listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
                                  "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}})
        with socket.socket() as existing:
            existing.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            existing.bind(("127.0.0.1", 0))
            existing.listen()
            with self.assertRaises(OSError):
                await broker._create_server_instance("default", ListenerType.TCP, "127.0.0.1",
                                                      existing.getsockname()[1], None)
