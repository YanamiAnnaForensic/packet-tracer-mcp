"""Local configuration. Credentials are never included in status responses."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys


def state_directory() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "PacketTracerMCP"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/PacketTracerMCP"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "packet-tracer-mcp"


def config_path() -> Path:
    return Path(os.environ.get("PT_MCP_CONFIG", state_directory() / "connection.json")).expanduser()


@dataclass(frozen=True)
class ConnectionConfig:
    app_id: str
    secret: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 39000
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if not self.app_id or not self.secret or any("\0" in x for x in [self.app_id, self.secret, self.host]):
            raise ValueError("The application ID, secret and host must be nonempty and NUL-free.")
        if not 1 <= self.port <= 65535 or not 0 < self.timeout <= 300:
            raise ValueError("Invalid IPC port or timeout (expected 0 < timeout <= 300).")

    @classmethod
    def load(cls) -> "ConnectionConfig":
        path = config_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        app_id = os.environ.get("PT_MCP_APP_ID", data.get("app_id", ""))
        secret = os.environ.get("PT_MCP_SECRET", data.get("secret", ""))
        if not app_id or not secret:
            raise ValueError("No ExApp credentials. Run 'packet-tracer-mcp setup' and register the generated .pta.")
        return cls(
            app_id=app_id,
            secret=secret,
            host=os.environ.get("PT_MCP_HOST", data.get("host", "127.0.0.1")),
            port=int(os.environ.get("PT_MCP_PORT", data.get("port", 39000))),
            timeout=float(os.environ.get("PT_MCP_TIMEOUT", data.get("timeout", 30))),
        )
