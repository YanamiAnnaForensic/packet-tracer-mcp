"""Testable native operations. No mouse, keyboard, screenshots of the desktop, or shell execution."""

from contextlib import contextmanager
import ipaddress
from pathlib import Path
import re
import socket
import threading
import time
from typing import Iterator

from .config import ConnectionConfig
from .protocol import PTMPClient, Wire, step


class PacketTracer:
    def __init__(self, config: ConnectionConfig | None = None):
        self.config = config
        self.client: PTMPClient | None = None
        self.lock = threading.RLock()

    @contextmanager
    def session(self) -> Iterator[PTMPClient]:
        # Whole operations, not just individual frames, must be serialized.
        with self.lock:
            if self.client is None:
                self.client = PTMPClient(self.config or ConnectionConfig.load())
            try:
                self.client.connect()
                yield self.client
            except (OSError, EOFError):
                self.client.close()
                self.client = None
                raise

    def close(self) -> None:
        with self.lock:
            if self.client is not None:
                self.client.close()
                self.client = None

    def status(self) -> dict:
        try:
            with self.session() as p:
                return {"connected": True, "version": p.call("appWindow", "getVersion"),
                        "device_count": p.call("network", "getDeviceCount")}
        except (OSError, EOFError, ValueError, RuntimeError) as exc:
            return {"connected": False, "problem": str(exc)}

    def list_devices(self) -> list[dict]:
        with self.session() as p:
            result = []
            for i in range(p.call("network", "getDeviceCount")):
                path = ("network", step("getDeviceAt", (Wire.INT, i)))
                result.append({"name": p.call(*path, "getName"), "model": p.call(*path, "getModel"),
                               "type": p.call(*path, "getType")})
            return result

    def new_network(self, discard_current: bool = False) -> dict:
        with self.session() as p:
            if p.call("network", "getDeviceCount") and not discard_current:
                raise ValueError("The workspace is occupied. Save it first, or explicitly set discard_current=true.")
            if not p.call("appWindow", step("fileNew", (Wire.BOOL, False))):
                raise RuntimeError("Packet Tracer did not create a new workspace.")
            return {"created": True}

    def open_network(self, path: str, discard_current: bool = False) -> dict:
        target = Path(path).expanduser().resolve()
        if not target.is_file() or target.suffix.lower() != ".pkt":
            raise ValueError("Expected an existing .pkt file on the MCP server's computer.")
        with self.session() as p:
            # Opening into a nonempty workspace can show a modal prompt. Clear it
            # only when explicitly requested, using Packet Tracer's native API.
            if p.call("network", "getDeviceCount"):
                if not discard_current:
                    raise ValueError("Save the current network, then explicitly set discard_current=true to replace it.")
                self.new_network(discard_current=True)
            code = p.call("appWindow", step("fileOpen", (Wire.QSTRING, str(target))))
            if code != 0:
                raise RuntimeError(f"Packet Tracer could not open the .pkt (return code {code}).")
            return {"opened": str(target)}

    @staticmethod
    def _output_path(path: str, suffix: str, overwrite: bool) -> Path:
        target = Path(path).expanduser().resolve()
        if target.suffix.lower() != suffix:
            raise ValueError(f"Expected a {suffix} output path.")
        if target.exists() and not overwrite:
            raise FileExistsError("Output already exists; set overwrite=true to replace it.")
        if not target.parent.is_dir():
            raise ValueError("The output directory must already exist.")
        return target

    def save_network(self, path: str, overwrite: bool = False) -> dict:
        target = self._output_path(path, ".pkt", overwrite)
        with self.session() as p:
            p.call("appWindow", step("fileSaveAsNoPrompt", (Wire.QSTRING, str(target)), (Wire.BOOL, False)))
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError("Packet Tracer returned without creating a nonempty file.")
        return {"saved": str(target), "bytes": target.stat().st_size}

    def create_device(self, name: str, kind: str, x: float, y: float, model: str | None = None) -> dict:
        models = {"router": (0, "2911"), "switch": (1, "2960-24TT"),
                  "multilayer_switch": (16, "3560-24PS"), "pc": (8, "PC-PT")}
        if kind not in models or not name.strip() or any(c in name for c in "\r\n\0"):
            raise ValueError("Use a nonempty device name and a documented device kind.")
        device_type, default_model = models[kind]
        model = model or default_model
        with self.session() as p:
            if any(d["name"] == name for d in self.list_devices()):
                raise ValueError(f"A device named {name} already exists.")
            generated = p.workspace(step("addDevice", (Wire.INT, device_type), (Wire.STRING, model),
                                         (Wire.DOUBLE, x), (Wire.DOUBLE, y)))
            if not generated:
                raise RuntimeError("Packet Tracer could not add this model.")
            try:
                p.device(generated, step("setName", (Wire.QSTRING, name)))
                if kind != "pc":
                    p.device(name, "skipBoot")
            except Exception:
                p.workspace(step("removeDevice", (Wire.QSTRING, generated)))
                raise
        return {"name": name, "kind": kind, "model": model}

    def connect_devices(self, device_a: str, port_a: str, device_b: str, port_b: str,
                        cable: str = "straight") -> dict:
        cables = {"straight": 8100, "crossover": 8101}
        if cable not in cables:
            raise ValueError("Cable must be straight or crossover.")
        with self.session() as p:
            ok = p.workspace(step("createLink", (Wire.QSTRING, device_a), (Wire.STRING, port_a),
                                  (Wire.QSTRING, device_b), (Wire.STRING, port_b), (Wire.INT, cables[cable])))
            if not ok:
                raise RuntimeError("Could not connect these ports. Check model, port names and occupied links.")
        return {"connected": True, "from": [device_a, port_a], "to": [device_b, port_b], "cable": cable}

    def set_pc_ipv4(self, device: str, address: str, netmask: str, gateway: str,
                    port: str = "FastEthernet0") -> dict:
        interface = ipaddress.IPv4Interface(f"{address}/{netmask}")
        gw = ipaddress.IPv4Address(gateway)
        if gw not in interface.network:
            raise ValueError("The PC's gateway must belong to its configured IPv4 subnet.")
        with self.session() as p:
            p.device(device, step("setDhcpFlag", (Wire.BOOL, False)))
            path = (step("getPort", (Wire.STRING, port)),)
            p.device(device, *path, step("setIpSubnetMask", (Wire.IPV4, str(interface.ip)),
                                        (Wire.IPV4, str(interface.netmask))))
            p.device(device, *path, step("setDefaultGateway", (Wire.IPV4, str(gw))))
        return {"device": device, "address": str(interface.ip), "netmask": str(interface.netmask), "gateway": str(gw)}

    @staticmethod
    def _command(command: str) -> str:
        if not command.strip() or any(c in command for c in "\r\n\0"):
            raise ValueError("Each IOS command must be a single nonempty line.")
        return command.strip()

    def configure_ios(self, device: str, commands: list[str], save: bool = True) -> dict:
        if not commands or len(commands) > 500:
            raise ValueError("Supply 1 to 500 IOS configuration commands.")
        commands = [self._command(c) for c in commands]
        records = []
        with self.session() as p:
            p.ios(device, "!", "global")
            try:
                for command in commands:
                    code, output = p.ios(device, command)
                    records.append({"command": command, "code": code, "output": output})
                    if re.search(r"%\s*(?:Invalid|Incomplete|Ambiguous|Unrecognized)", output, re.I):
                        return {"ok": False, "failed_command": command, "records": records, "saved": False}
            finally:
                p.ios(device, "end")
            if save:
                code, output = p.ios(device, "write memory", "enable")
                records.append({"command": "write memory", "code": code, "output": output})
        return {"ok": True, "records": records, "saved": save}

    def show(self, device: str, command: str) -> dict:
        command = self._command(command)
        if not command.lower().startswith("show "):
            raise ValueError("This tool only accepts a single IOS 'show ...' command.")
        with self.session() as p:
            code, output = p.ios(device, command, "enable")
        return {"device": device, "command": command, "code": code, "output": output}

    @staticmethod
    def _fast(p: PTMPClient) -> None:
        p.call("appWindow", "getRealtimeToolbar", "fastForwardTime")

    def fast_forward(self) -> dict:
        with self.session() as p:
            self._fast(p)
        return {"advanced": True}

    def _host_command(self, p: PTMPClient, device: str, command: str, timeout: float) -> str:
        object_id = p.device(device, "getCommandPrompt", "getObjectUuid")
        p.events.clear()
        for event in ("outputWritten", "commandEnded"):
            p.subscribe(object_id, event, True)
        output = []
        deadline = time.monotonic() + timeout
        try:
            p.device(device, "getCommandPrompt", step("enterCommand", (Wire.STRING, command)))
            done = False
            while not done:
                while p.events:
                    event = p.events.popleft()
                    if event.object_id != object_id:
                        continue
                    if event.name == "outputWritten" and event.args:
                        output.append(str(event.args[0]))
                    if event.name == "commandEnded":
                        done = True
                if done:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("PC command timed out; no successful ping result was inferred.")
                try:
                    p.receive_events(min(2, remaining))
                except socket.timeout:
                    self._fast(p)
        finally:
            if p.sock is not None:
                p.sock.settimeout(p.config.timeout)
                for event in ("outputWritten", "commandEnded"):
                    p.subscribe(object_id, event, False)
        return "".join(output)

    def pc_ipconfig(self, device: str) -> dict:
        with self.session() as p:
            return {"device": device, "output": self._host_command(p, device, "ipconfig", 20)}

    def ping(self, device: str, destination: str, attempts: int = 2, timeout: float = 30) -> dict:
        address = str(ipaddress.IPv4Address(destination))
        if not 1 <= attempts <= 3 or not 1 <= timeout <= 120:
            raise ValueError("Expected 1 to 3 attempts and a 1 to 120 second timeout per attempt.")
        records = []
        with self.session() as p:
            for _ in range(attempts):
                output = self._host_command(p, device, "ping " + address, timeout)
                matches = list(re.finditer(r"Sent = (\d+), Received = (\d+), Lost = (\d+)", output))
                if not matches:
                    raise RuntimeError("Packet Tracer returned no parseable ping statistics; success is unknown.")
                sent, received, lost = map(int, matches[-1].groups())
                records.append({"sent": sent, "received": received, "lost": lost, "output": output})
                if sent > 0 and received == sent:
                    break
                self._fast(p)
        last = records[-1]
        return {"device": device, "destination": address, "success": last["sent"] > 0 and last["received"] == last["sent"],
                "attempts": records}

    def topology_png(self, path: str | None = None, overwrite: bool = False) -> tuple[bytes, dict]:
        target = self._output_path(path, ".png", overwrite) if path else None
        with self.session() as p:
            data = p.workspace(step("getWorkspaceImage", (Wire.QSTRING, "PNG")))
        if not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Packet Tracer did not return a valid native workspace PNG.")
        if target is not None:
            target.write_bytes(data)
        return data, {"bytes": len(data), "path": str(target) if target else None, "source": "Packet Tracer workspace export"}
