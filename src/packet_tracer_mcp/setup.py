"""Generate an ExApp with Cisco's own meta utility; optionally register PT 8.0 user settings."""

from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import tempfile
from xml.etree import ElementTree as ET
import zlib

from .config import config_path, state_directory
from . import __version__


def atomic_write(path: Path, data: bytes, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        if private:
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def decode_options(data: bytes) -> bytes:
    if len(data) < 6:
        raise ValueError("PT.conf is too short.")
    size = len(data)
    plain = bytes(value ^ ((size - i) & 255) for i, value in enumerate(data))
    expected = struct.unpack(">I", plain[:4])[0]
    if expected > 8 * 1024 * 1024:
        raise ValueError("PT.conf exceeds the supported size.")
    decoder = zlib.decompressobj()
    xml = decoder.decompress(plain[4:], expected + 1)
    if len(xml) != expected or not decoder.eof:
        raise ValueError("PT.conf decompressed size does not match its header.")
    return xml


def encode_options(xml: bytes) -> bytes:
    data = struct.pack(">I", len(xml)) + zlib.compress(xml)
    size = len(data)
    return bytes(value ^ ((size - i) & 255) for i, value in enumerate(data))


def find_meta(pt_home: Path) -> Path:
    for relative in ["bin/meta.exe", "extensions/meta.exe", "extensions/meta", "bin/meta", "meta.exe", "meta"]:
        candidate = pt_home / relative
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("Cisco's meta utility was not found under --pt-home.")


def ensure_packet_tracer_closed() -> None:
    if sys.platform != "win32":
        raise ValueError("Automatic user-config registration is verified only on Windows Packet Tracer 8.0.")
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PacketTracer.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, errors="replace", check=True)
    if '"packettracer.exe"' in result.stdout.lower():
        raise RuntimeError("Close Packet Tracer normally before editing its user PT.conf, then restart it afterward.")


def register_user_config(path: Path, default_path: Path, manifest: Path, remove: bool = False) -> dict:
    ensure_packet_tracer_closed()
    original = path.read_bytes() if path.exists() else b""
    source = original or default_path.read_bytes()
    root = ET.fromstring(decode_options(source))
    manager = root.find("IPC_MANAGER")
    if manager is None:
        raise ValueError("PT.conf has no IPC_MANAGER. No configuration was changed.")
    target = str(manifest.resolve()).replace("\\", "/")
    matches = [node for node in manager.findall("METAFILE_PATH") if (node.text or "").replace("\\", "/") == target]
    if remove:
        for node in matches:
            manager.remove(node)
    elif not matches:
        ET.SubElement(manager, "METAFILE_PATH").text = target
    else:
        return {"changed": False, "user_config": str(path)}
    if remove and not matches:
        return {"changed": False, "user_config": str(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".packet-tracer-mcp-" + datetime.now().strftime("%Y%m%d%H%M%S%f") + ".bak")
    atomic_write(backup, original, private=True)
    atomic_write(path, encode_options(b"<!DOCTYPE Options>\n" + ET.tostring(root, encoding="utf-8")))
    return {"changed": True, "user_config": str(path), "backup": str(backup)}


def setup_exapp(pt_home: Path, pt_version: str = "8.0", output_dir: Path | None = None,
                register: bool = False, user_config: Path | None = None) -> dict:
    if register and pt_version != "8.0":
        raise ValueError("Automatic PT.conf registration is verified only for Packet Tracer 8.0.")
    if register:
        ensure_packet_tracer_closed()
    meta = find_meta(pt_home)
    output = output_dir or state_directory()
    output.mkdir(parents=True, exist_ok=True)
    credentials = output / "connection.json" if output_dir else config_path()
    if credentials.exists():
        data = json.loads(credentials.read_text(encoding="utf-8"))
        if not data.get("app_id") or not data.get("secret"):
            raise ValueError("Existing credentials are incomplete; no files were changed.")
    else:
        data = {"app_id": "org.packet-tracer-mcp", "secret": secrets.token_hex(32), "host": "127.0.0.1", "port": 39000}
        atomic_write(credentials, json.dumps(data, indent=2).encode("utf-8"), private=True)
    manifest = output / "packet-tracer-mcp.pta"
    document = ET.Element("PT_APP_META")
    values = {"PT_VERSION": pt_version, "IPC_VERSION": "1.0", "NAME": "Packet Tracer MCP", "VERSION": __version__,
              "ID": data["app_id"], "DESCRIPTION": "Native topology, IOS and connectivity tools over MCP.",
              "AUTHOR": "YanamiAnnaForensic", "CONTACT": "", "EXECUTABLE_PATH": sys.executable, "KEY": data["secret"]}
    for key, value in values.items():
        ET.SubElement(document, key).text = value
    privileges = ET.SubElement(document, "SECURITY_SETTINGS")
    for name in ["GET_NETWORK_INFO", "CHANGE_NETWORK_INFO", "SIMULATION_MODE", "MISC_GUI", "FILE", "APPLICATION"]:
        ET.SubElement(privileges, "PRIVILEGE").text = name
    for key, value in [("LOADING", "ON_DEMAND"), ("SAVING", "NEVER"), ("INSTANCES", "4")]:
        ET.SubElement(document, key).text = value
    with tempfile.TemporaryDirectory(prefix="packet-tracer-mcp-") as temporary:
        xml = Path(temporary) / "manifest.xml"
        xml.write_bytes(ET.tostring(document, encoding="utf-8", xml_declaration=True))
        os.chmod(xml, 0o600)
        generated = Path(temporary) / "manifest.pta"
        completed = subprocess.run([str(meta), str(generated), str(xml)], capture_output=True, timeout=30)
        if completed.returncode or not generated.is_file():
            raise RuntimeError("Cisco meta did not generate a manifest. Check --pt-home and --pt-version.")
        atomic_write(manifest, generated.read_bytes(), private=True)
    result = {"manifest": str(manifest.resolve()), "credentials": str(credentials.resolve()), "registered": False}
    if register:
        default = pt_home / "bin/PT.conf"
        path = user_config or Path.home() / f"Cisco Packet Tracer {pt_version}/PT.conf"
        result["registration"] = register_user_config(path, default, manifest)
        result["registered"] = True
    return result
