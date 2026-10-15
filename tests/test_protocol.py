import hashlib
import socket
import threading
import unittest

from packet_tracer_mcp.config import ConnectionConfig
from packet_tracer_mcp.protocol import Cursor, IPCError, ProtocolError, PTMPClient, Wire, step


def packet(*fields):
    body = ("\0".join(map(str, fields)) + "\0").encode("utf-8")
    return str(len(body)).encode() + b"\0" + body


class FakePeer:
    """A real TCP peer exercising handshake and fragmented binary replies."""

    def __init__(self, callback):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.callback = callback
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    @staticmethod
    def read(connection):
        header = bytearray()
        while True:
            byte = connection.recv(1)
            if not byte:
                raise EOFError()
            if byte == b"\0":
                break
            header.extend(byte)
        length = int(header)
        body = bytearray()
        while len(body) < length:
            chunk = connection.recv(length - len(body))
            if not chunk:
                raise EOFError()
            body.extend(chunk)
        return bytes(body)

    def run(self):
        try:
            connection, _ = self.listener.accept()
            with connection:
                connection.settimeout(3)
                assert self.read(connection).startswith(b"0\0PTMP\0")
                connection.sendall(packet(1, "PTMP", 1))
                assert self.read(connection) == b"2\0test.app\0"
                connection.sendall(packet(3, "challenge"))
                authentication = self.read(connection).decode().split("\0")
                expected = hashlib.md5(b"challengeprivate-test-secret").hexdigest().upper()
                assert authentication[2] == expected
                connection.sendall(packet(5, "true"))
                self.callback(connection, self.read(connection))
        except Exception as exc:
            self.error = exc
        finally:
            self.listener.close()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.thread.join(5)
        if self.thread.is_alive():
            raise AssertionError("Fake PTMP peer did not finish.")
        if self.error:
            raise self.error


class ProtocolTests(unittest.TestCase):
    def client(self, peer):
        return PTMPClient(ConnectionConfig("test.app", "private-test-secret", port=peer.port, timeout=3))

    def test_auth_unicode_arguments_events_and_binary_fragmentation(self):
        binary = b"\x89PNG\r\n\x1a\n\0binary\xff\0payload"

        def answer(connection, request):
            self.assertIn("交换机".encode(), request)
            self.assertIn(b"2\0false\0", request)
            event = packet(103, 99, "TerminalLine", "{object}", "outputWritten", 8, "实际输出", 0)
            body = b"102\0" + b"1\0" + b"15\0" + b"1\0" + str(len(binary)).encode() + b"\0" + binary
            response = event + str(len(body)).encode() + b"\0" + body
            for i in range(0, len(response), 3):
                connection.sendall(response[i:i + 3])

        with FakePeer(answer) as peer:
            client = self.client(peer)
            try:
                self.assertEqual(client.call(step("example", (Wire.QSTRING, "交换机"), (Wire.BOOL, False))), binary)
                event = client.events.popleft()
                self.assertEqual((event.object_id, event.name, event.args), ("{object}", "outputWritten", ("实际输出",)))
            finally:
                client.close()

    def test_ipc_error_keeps_transport_available(self):
        def answer(connection, request):
            connection.sendall(packet(101, 1, "Device", "No such port"))
            self.assertTrue(FakePeer.read(connection).startswith(b"100\x002\x00"))
            connection.sendall(packet(102, 2, 4, 7))

        with FakePeer(answer) as peer:
            client = self.client(peer)
            try:
                with self.assertRaisesRegex(IPCError, "No such port"):
                    client.call("badPort")
                self.assertEqual(client.call("count"), 7)
            finally:
                client.close()

    def test_disconnect_during_frame_is_not_an_infinite_read(self):
        def answer(connection, request):
            connection.sendall(b"100\0truncated")

        with FakePeer(answer) as peer:
            client = self.client(peer)
            with self.assertRaises(EOFError):
                client.call("getSomething")
            self.assertIsNone(client.sock)

    def test_reply_sequence_mismatch_closes_connection(self):
        with FakePeer(lambda connection, request: connection.sendall(packet(102, 99, 4, 1))) as peer:
            client = self.client(peer)
            with self.assertRaises(ProtocolError):
                client.call("count")
            self.assertIsNone(client.sock)

    def test_oversized_frame_is_rejected_before_payload(self):
        with FakePeer(lambda connection, request: connection.sendall(b"999999999\0")) as peer:
            client = self.client(peer)
            with self.assertRaises(ProtocolError):
                client.call("anything")
            self.assertIsNone(client.sock)

    def test_pairs_vectors_and_truncated_bytes(self):
        self.assertEqual(Cursor(b"14\x004\x000\x008\x00done\x00").value(), [0, "done"])
        self.assertEqual(Cursor(b"15\x004\x002\x0010\x0020\x00").value(), [10, 20])
        with self.assertRaises(ProtocolError):
            Cursor(b"15\x001\x005\x00abc").value()

    def test_nul_in_arguments_is_rejected(self):
        client = PTMPClient(ConnectionConfig("app", "secret"))
        client.sock, other = socket.socketpair()
        try:
            with self.assertRaises(ValueError):
                client._send(100, "bad\0argument")
        finally:
            client.close()
            other.close()


if __name__ == "__main__":
    unittest.main()
