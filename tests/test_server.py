import base64
from io import BytesIO
import json
import unittest
from unittest.mock import Mock

from packet_tracer_mcp.server import MCPServer, TOOLS, TOOL_MAP, validate_arguments


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.server = MCPServer(self.backend)

    def call(self, method, params=None, request_id=1):
        return self.server.handle({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})

    def initialize(self):
        return self.call("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "test", "version": "1"}, "capabilities": {}})

    def test_initialize_tools_and_protocol_negotiation(self):
        result = self.initialize()["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        listing = self.call("tools/list")["result"]["tools"]
        self.assertEqual(len(listing), 14)
        self.assertTrue(all("inputSchema" in t and "annotations" in t for t in listing))
        self.assertEqual(self.call("initialize", {"protocolVersion": "future", "clientInfo": {}, "capabilities": {}})["result"]["protocolVersion"], "2025-06-18")

    def test_no_tools_before_initialization_and_notifications_have_no_response(self):
        self.assertIn("error", self.call("tools/list"))
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.call("ping")["result"], {})

    def test_image_content_contains_real_binary_and_optional_path(self):
        self.initialize()
        binary = b"\x89PNG\r\n\x1a\n\0test"
        self.backend.topology_png.return_value = (binary, {"bytes": len(binary)})
        result = self.call("tools/call", {"name": "pt_topology_png", "arguments": {}})["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(base64.b64decode(result["content"][1]["data"]), binary)

    def test_validation_happens_before_mutation(self):
        self.initialize()
        for args in [{"discard_current": "false"}, {"unexpected": True}]:
            result = self.call("tools/call", {"name": "pt_new_network", "arguments": args})["result"]
            self.assertTrue(result["isError"])
        self.backend.new_network.assert_not_called()
        with self.assertRaises(ValueError):
            validate_arguments(TOOL_MAP["pt_ping"], {"device": "PC", "destination": "1.1.1.1", "attempts": True})

    def test_failures_are_tool_errors_and_bad_methods_are_rpc_errors(self):
        self.initialize()
        self.backend.list_devices.side_effect = ConnectionError("Packet Tracer is closed")
        self.assertTrue(self.call("tools/call", {"name": "pt_list_devices"})["result"]["isError"])
        self.assertEqual(self.call("tools/call", {"name": "missing"})["error"]["code"], -32602)
        self.assertEqual(self.call("missing")["error"]["code"], -32601)

    def test_stdio_is_newline_json_handles_parse_errors_and_keeps_unicode(self):
        self.backend.status.return_value = {"connected": True, "label": "交换机"}
        requests = [
            b"not JSON\n",
            (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "clientInfo": {}, "capabilities": {}}}) + "\n").encode(),
            b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n',
            b'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"pt_status"}}\n',
        ]
        output = BytesIO()
        self.server.run(BytesIO(b"".join(requests)), output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(responses), 3)
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertIn("交换机", responses[2]["result"]["content"][0]["text"])
        self.backend.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
