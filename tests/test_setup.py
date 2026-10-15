import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
import zlib

from packet_tracer_mcp.backend import PacketTracer
from packet_tracer_mcp.config import ConnectionConfig
from packet_tracer_mcp.setup import decode_options, encode_options, register_user_config


class SetupTests(unittest.TestCase):
    def test_config_codec_rejects_wrong_size_and_roundtrips_unicode(self):
        data = '<Options><Label>交换机</Label></Options>'.encode()
        self.assertEqual(decode_options(encode_options(data)), data)
        corrupted = bytearray(encode_options(data))
        corrupted[3] ^= 1
        with self.assertRaises(ValueError):
            decode_options(bytes(corrupted))

    def test_registration_backup_idempotence_and_unregistration_preserve_other_apps(self):
        xml = b'<Options><OTHER keep="yes"/><IPC_MANAGER><METAFILE_PATH>other.pta</METAFILE_PATH></IPC_MANAGER></Options>'
        with tempfile.TemporaryDirectory() as directory, patch("packet_tracer_mcp.setup.ensure_packet_tracer_closed"):
            root = Path(directory)
            user = root / "user/PT.conf"
            default = root / "default.conf"
            default.write_bytes(encode_options(xml))
            manifest = root / "our.pta"
            result = register_user_config(user, default, manifest)
            self.assertEqual(Path(result["backup"]).read_bytes(), b"")
            first = user.read_bytes()
            self.assertFalse(register_user_config(user, default, manifest)["changed"])
            self.assertEqual(user.read_bytes(), first)
            document = ET.fromstring(decode_options(first))
            document.find("OTHER").set("new_setting", "preserved")
            user.write_bytes(encode_options(ET.tostring(document)))
            result = register_user_config(user, default, manifest, remove=True)
            final = ET.fromstring(decode_options(user.read_bytes()))
            self.assertEqual(final.find("OTHER").get("new_setting"), "preserved")
            self.assertEqual([n.text for n in final.findall("IPC_MANAGER/METAFILE_PATH")], ["other.pta"])
            self.assertTrue(Path(result["backup"]).is_file())

    def test_invalid_user_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch("packet_tracer_mcp.setup.ensure_packet_tracer_closed"):
            root = Path(directory)
            user = root / "PT.conf"
            user.write_bytes(b"unknown version")
            with self.assertRaises((ValueError, zlib.error)):
                register_user_config(user, root / "unused", root / "manifest.pta")
            self.assertEqual(user.read_bytes(), b"unknown version")

    def test_credentials_are_not_in_repr_or_status_without_configuration(self):
        config = ConnectionConfig("test", "never-display-this-value")
        self.assertNotIn(config.secret, repr(config))
        with patch.dict("os.environ", {"PT_MCP_APP_ID": "", "PT_MCP_SECRET": "", "PT_MCP_CONFIG": "/nonexistent/config"}):
            result = PacketTracer().status()
        self.assertFalse(result["connected"])
        self.assertNotIn("never-display-this-value", json.dumps(result))

    def test_show_does_not_accept_command_injection(self):
        tracer = PacketTracer()
        for command in ["show vlan\nreload", "reload", "show vlan\0bad"]:
            with self.assertRaises(ValueError):
                tracer.show("Switch", command)


if __name__ == "__main__":
    unittest.main()
