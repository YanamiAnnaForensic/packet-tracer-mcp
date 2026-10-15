"""Small real MCP stdio client, also used for integration checks (no dependencies)."""

import json
from pathlib import Path
import queue
import subprocess
import sys
import threading


class Client:
    def __init__(self, env=None):
        launcher = Path(__file__).resolve().parents[1] / "run_server.py"
        self.process = subprocess.Popen([sys.executable, str(launcher), "serve"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.queue = queue.Queue()
        self.sequence = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in iter(self.process.stdout.readline, b""):
            try:
                self.queue.put(json.loads(line))
            except ValueError as exc:
                self.queue.put(exc)
        self.queue.put(EOFError("MCP server stopped."))

    def send(self, value):
        self.process.stdin.write((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def request(self, method, params=None, timeout=45):
        self.sequence += 1
        self.send({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params or {}})
        response = self.queue.get(timeout=timeout)
        if isinstance(response, Exception):
            raise response
        if response.get("id") != self.sequence or "error" in response:
            raise RuntimeError(response)
        return response["result"]

    def initialize(self):
        result = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "packet-tracer-mcp-example", "version": "0.1.0"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def tool(self, tool_name, **arguments):
        result = self.request("tools/call", {"name": tool_name, "arguments": arguments}, timeout=130)
        text = json.loads(result["content"][0]["text"])
        if result.get("isError"):
            raise RuntimeError(text)
        return text

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(5)
        errors = self.process.stderr.read().decode("utf-8", errors="replace")
        if self.process.returncode or errors:
            raise RuntimeError(f"MCP process exit {self.process.returncode}: {errors}")


if __name__ == "__main__":
    client = Client()
    try:
        print(json.dumps(client.initialize(), ensure_ascii=False, indent=2))
        print(json.dumps(client.tool("pt_status"), ensure_ascii=False, indent=2))
        print(json.dumps(client.tool("pt_list_devices"), ensure_ascii=False, indent=2))
    finally:
        client.close()
