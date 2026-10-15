"""A synchronous PTMP/IPC client with framing, authentication and event support.

Only one call owns a connection at a time. Transport failures close it; mutations
are never retried automatically because their outcome may already be committed.
"""

from collections import deque
from dataclasses import dataclass
from enum import IntEnum
import hashlib
import socket
import threading
import time
from typing import Any
import uuid

from .config import ConnectionConfig


class ProtocolError(RuntimeError):
    """Malformed or unsupported PTMP data."""


class IPCError(RuntimeError):
    """Packet Tracer rejected an IPC method call."""


class Wire(IntEnum):
    BOOL = 2
    INT = 4
    DOUBLE = 7
    STRING = 8
    QSTRING = 9
    IPV4 = 10
    UUID = 13


@dataclass(frozen=True)
class Argument:
    kind: Wire
    value: Any


@dataclass(frozen=True)
class Step:
    name: str
    args: tuple[Argument, ...] = ()


def step(name: str, *args: tuple[Wire, Any]) -> Step:
    return Step(name, tuple(Argument(kind, value) for kind, value in args))


@dataclass(frozen=True)
class Event:
    object_id: str
    name: str
    args: tuple[Any, ...]


class Cursor:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def token(self) -> str:
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise ProtocolError("Unterminated PTMP token.")
        raw = self.data[self.pos:end]
        self.pos = end + 1
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Invalid UTF-8 in PTMP token.") from exc

    def value(self, kind: int | None = None, depth: int = 0) -> Any:
        if depth > 32:
            raise ProtocolError("PTMP value nesting limit exceeded.")
        kind = int(self.token()) if kind is None else kind
        if kind == 0:
            return None
        if kind == 14:
            return [self.value(depth=depth + 1), self.value(depth=depth + 1)]
        if kind == 15:
            element_kind, count = int(self.token()), int(self.token())
            if not 0 <= count <= 1_000_000:
                raise ProtocolError("Invalid PTMP vector length.")
            if element_kind == 1:
                end = self.pos + count
                if end > len(self.data):
                    raise ProtocolError("Truncated PTMP byte vector.")
                result = self.data[self.pos:end]
                self.pos = end
                return result
            return [self.value(element_kind, depth + 1) for _ in range(count)]
        if kind == 16:
            name = self.token()
            if name == "CommandHistory":
                return {"history": self.value(depth=depth + 1), "maxCount": self.value(depth=depth + 1)}
            raise ProtocolError(f"Unsupported PTMP value object: {name}")
        if not 1 <= kind <= 13:
            raise ProtocolError(f"Unknown PTMP value code: {kind}")
        text = self.token()
        if kind == 2:
            if text not in ("true", "false"):
                raise ProtocolError("Invalid PTMP boolean.")
            return text == "true"
        if kind in (1, 3, 4, 5):
            return int(text)
        if kind in (6, 7):
            return float(text)
        return text


class PTMPClient:
    MAX_FRAME = 16 * 1024 * 1024

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.sock: socket.socket | None = None
        self.buffer = bytearray()
        self.sequence = 0
        self.events: deque[Event] = deque(maxlen=2048)
        self.lock = threading.RLock()

    def connect(self) -> None:
        with self.lock:
            if self.sock is not None:
                return
            self.sock = socket.create_connection((self.config.host, self.config.port), timeout=self.config.timeout)
            try:
                self._send(0, "PTMP", 1, "{" + str(uuid.uuid4()) + "}", 1, 1, 1, 4,
                           time.strftime("%Y%m%d%H%M%S"), 0, "")
                hello = Cursor(self._frame())
                if hello.token() != "1" or hello.token() != "PTMP":
                    raise ProtocolError("Packet Tracer did not accept PTMP negotiation.")
                self._send(2, self.config.app_id)
                challenge = Cursor(self._frame())
                if challenge.token() != "3":
                    raise IPCError("ExApp registration rejected. Register the .pta before connecting.")
                # MD5 is mandated by PTMP's challenge-response protocol.
                digest = hashlib.md5((challenge.token() + self.config.secret).encode("utf-8")).hexdigest().upper()
                self._send(4, self.config.app_id, digest, "")
                status = Cursor(self._frame())
                if status.token() != "5" or status.token() != "true":
                    raise IPCError("ExApp authentication failed. Check the registration and local credentials.")
            except BaseException:
                self.close()
                raise

    def _send(self, *fields: Any) -> None:
        if self.sock is None:
            raise ConnectionError("PTMP is not connected.")
        tokens = []
        for field in fields:
            text = str(field).lower() if isinstance(field, bool) else str(field)
            if "\0" in text:
                raise ValueError("IPC arguments cannot contain NUL characters.")
            tokens.append(text)
        body = ("\0".join(tokens) + "\0").encode("utf-8")
        self.sock.sendall(str(len(body)).encode("ascii") + b"\0" + body)

    def _frame(self) -> bytes:
        if self.sock is None:
            raise ConnectionError("PTMP is not connected.")
        try:
            while b"\0" not in self.buffer:
                if len(self.buffer) > 12:
                    raise ProtocolError("PTMP length header is too long.")
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise EOFError("Packet Tracer closed the IPC connection.")
                self.buffer.extend(chunk)
            split = self.buffer.index(0)
            header = bytes(self.buffer[:split])
            if not header.isdigit() or len(header) > 12:
                raise ProtocolError("Invalid PTMP length header.")
            length = int(header)
            if not 1 <= length <= self.MAX_FRAME:
                raise ProtocolError("PTMP frame exceeds the supported size.")
            end = split + 1 + length
            while len(self.buffer) < end:
                chunk = self.sock.recv(min(65536, end - len(self.buffer)))
                if not chunk:
                    raise EOFError("Packet Tracer disconnected during a PTMP frame.")
                self.buffer.extend(chunk)
            frame = bytes(self.buffer[split + 1:end])
            del self.buffer[:end]
            return frame
        except (EOFError, ProtocolError):
            self.close()
            raise

    def _dispatch(self, frame: bytes) -> tuple[str, int, Any] | None:
        cur = Cursor(frame)
        message = cur.token()
        if message == "6":
            return None
        if message == "7":
            raise ConnectionError("Packet Tracer disconnected the external application.")
        if message == "103":
            cur.token()  # event token
            cur.token()  # class
            object_id, name = cur.token(), cur.token()
            values = []
            while cur.pos < len(frame):
                kind = int(cur.token())
                if kind == 0:
                    break
                values.append(cur.value(kind))
            self.events.append(Event(object_id, name, tuple(values)))
            return None
        if message not in ("101", "102"):
            raise ProtocolError(f"Unexpected PTMP message type: {message}")
        sequence = int(cur.token())
        if message == "101":
            return message, sequence, cur.token() + ": " + cur.token()
        return message, sequence, cur.value() if cur.pos < len(frame) else None

    def call(self, *steps: str | Step) -> Any:
        with self.lock:
            self.connect()
            assert self.sock is not None
            self.sock.settimeout(self.config.timeout)
            self.sequence += 1
            fields: list[Any] = [100, self.sequence]
            for item in steps:
                item = Step(item) if isinstance(item, str) else item
                fields.append(item.name)
                for arg in item.args:
                    fields.extend([int(arg.kind), arg.value])
                fields.append(0)
            try:
                self._send(*fields)
                deadline = time.monotonic() + self.config.timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Packet Tracer did not finish the IPC call.")
                    self.sock.settimeout(remaining)
                    result = self._dispatch(self._frame())
                    if result is None:
                        continue
                    message, sequence, value = result
                    if sequence != self.sequence:
                        raise ProtocolError("PTMP reply sequence does not match the request.")
                    if message == "101":
                        raise IPCError(value)
                    return value
            except (OSError, EOFError, ProtocolError):
                self.close()
                raise

    def receive_events(self, timeout: float) -> None:
        with self.lock:
            if self.sock is None:
                raise ConnectionError("PTMP is not connected.")
            self.sock.settimeout(timeout)
            self._dispatch(self._frame())

    def subscribe(self, object_id: str, event: str, enabled: bool) -> None:
        self._send(104, "TerminalLine", object_id, event, enabled)

    def device(self, name: str, *steps: str | Step) -> Any:
        return self.call("network", step("getDevice", (Wire.QSTRING, name)), *steps)

    def workspace(self, *steps: str | Step) -> Any:
        return self.call("appWindow", "getActiveWorkspace", "getLogicalWorkspace", *steps)

    def ios(self, device: str, command: str, mode: str = "") -> tuple[int, str]:
        result = self.device(device, step("enterCommand", (Wire.STRING, command), (Wire.STRING, mode)))
        if not isinstance(result, list) or len(result) != 2:
            raise ProtocolError("Expected an IOS command result pair.")
        return result[0], result[1]

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock = None
        self.buffer.clear()
        self.events.clear()
