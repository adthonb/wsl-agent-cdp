import socket
import socketserver
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while data := self.request.recv(1024 * 1024):
            self.request.sendall(data)


class RelayTest(unittest.TestCase):
    def test_binary_payload_larger_than_one_frame(self):
        try:
            echo_server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), EchoHandler)
        except PermissionError as error:
            self.skipTest(f"network sandbox prevents socket tests: {error}")
        with echo_server as echo:
            thread = threading.Thread(target=echo.serve_forever, daemon=True)
            thread.start()
            relay_port = self.free_port()
            process = subprocess.Popen([
                sys.executable,
                str(ROOT / "scripts" / "cdp_relay.py"),
                "--listen-port", str(relay_port),
                "--target-host", "127.0.0.1",
                "--target-port", str(echo.server_address[1]),
            ])
            try:
                # Larger than the relay's high-water mark to exercise partial
                # writes rather than just a single in-memory buffer.
                payload = bytes(range(256)) * 32769
                for _ in range(50):
                    try:
                        client = socket.create_connection(("127.0.0.1", relay_port), .1)
                        break
                    except OSError:
                        time.sleep(.02)
                else:
                    self.fail("relay did not start")
                with client:
                    client.sendall(payload)
                    received = bytearray()
                    while len(received) < len(payload):
                        received.extend(client.recv(1024 * 1024))
                self.assertEqual(payload, received)
            finally:
                process.terminate()
                process.wait(timeout=5)

    @staticmethod
    def free_port():
        try:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                return sock.getsockname()[1]
        except PermissionError as error:
            raise unittest.SkipTest(f"network sandbox prevents socket tests: {error}")


if __name__ == "__main__":
    unittest.main()
