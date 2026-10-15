"""Dependency-free MCP stdio server.

Implements JSON-RPC initialization, ping, tools/list and tools/call with MCP text
and image content. Standard output is reserved exclusively for newline-delimited
JSON-RPC; commands execute serially because Packet Tracer owns one active workspace.
"""

from dataclasses import dataclass
import base64
import json
import logging
import math
from typing import Any, BinaryIO

from . import __version__
from .backend import PacketTracer

SUPPORTED_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
MAX_MESSAGE = 1024 * 1024


def string(description: str, enum: list[str] | None = None) -> dict:
    result: dict[str, Any] = {"type": "string", "description": description}
    if enum:
        result["enum"] = enum
    return result


def boolean(description: str, default: bool = False) -> dict:
    return {"type": "boolean", "description": description, "default": default}


def number(description: str) -> dict:
    return {"type": "number", "description": description}


@dataclass(frozen=True)
class Tool:
    name: str
    method: str
    description: str
    properties: dict
    required: tuple[str, ...] = ()
    read_only: bool = False
    destructive: bool = False

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {"type": "object", "properties": self.properties, "required": list(self.required),
                            "additionalProperties": False},
            "annotations": {"readOnlyHint": self.read_only, "destructiveHint": self.destructive,
                            "idempotentHint": self.read_only, "openWorldHint": False},
        }


TOOLS = [
    Tool("pt_status", "status", "Read native IPC connection status and Packet Tracer version. / 查看连接状态与版本。", {}, read_only=True),
    Tool("pt_list_devices", "list_devices", "List device names, models and type codes. / 列出设备名称、型号及类型。", {}, read_only=True),
    Tool("pt_new_network", "new_network", "Create an empty network; occupied workspace requires explicit discard_current. / 新建空网络，替换现有网络须明确指定。",
         {"discard_current": boolean("Discard the current workspace without saving. / 放弃当前工作区。")}, destructive=True),
    Tool("pt_open_network", "open_network", "Open a local .pkt, replacing the occupied workspace only when requested. / 打开本地pkt。",
         {"path": string("Absolute local .pkt path. / 本机pkt绝对路径。"), "discard_current": boolean("Discard current workspace. / 放弃当前工作区。")}, ("path",), destructive=True),
    Tool("pt_save_network", "save_network", "Save the active network as .pkt; overwrite is explicit. / 保存当前网络，覆盖须明确指定。",
         {"path": string("Absolute .pkt output path; parent must exist. / pkt输出路径。"), "overwrite": boolean("Replace an existing output. / 覆盖已有文件。")}, ("path",), destructive=True),
    Tool("pt_create_device", "create_device", "Add a named PC, router or switch with native IPC. / 通过原生接口添加设备。",
         {"name": string("Unique device name. / 唯一名称。"), "kind": string("Device kind. / 类型。", ["pc", "router", "switch", "multilayer_switch"]),
          "x": number("Workspace x coordinate. / 横坐标。"), "y": number("Workspace y coordinate. / 纵坐标。"),
          "model": string("Optional exact model, e.g. 2911, 2960-24TT, 3560-24PS, PC-PT. / 可选型号。")}, ("name", "kind", "x", "y")),
    Tool("pt_connect_devices", "connect_devices", "Connect two available ports using a straight/crossover cable. / 连接两个空闲端口。",
         {"device_a": string("First device. / 设备一。"), "port_a": string("First exact port name. / 端口一。"),
          "device_b": string("Second device. / 设备二。"), "port_b": string("Second exact port name. / 端口二。"),
          "cable": string("Cable type; default straight. / 线缆类型，默认直通。", ["straight", "crossover"])},
         ("device_a", "port_a", "device_b", "port_b")),
    Tool("pt_set_pc_ipv4", "set_pc_ipv4", "Configure a PC's static IPv4 address, mask and gateway. / 配置PC静态地址、掩码、网关。",
         {"device": string("PC name. / PC名称。"), "address": string("IPv4 address. / IPv4地址。"), "netmask": string("Dotted subnet mask. / 子网掩码。"),
          "gateway": string("IPv4 gateway in the same subnet. / 同网段网关。"), "port": string("Host port; default FastEthernet0. / PC接口。")},
         ("device", "address", "netmask", "gateway"), destructive=True),
    Tool("pt_configure_ios", "configure_ios", "Run IOS config lines in order, stop on syntax errors, optionally write memory. Supply commands after configure terminal. / 按顺序执行全局配置命令并可保存。",
         {"device": string("Router or switch name. / 路由器或交换机名称。"), "commands": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 500,
          "description": "One IOS command per element; global configuration mode is entered automatically. / 每项一条命令，自动进入全局配置。"},
          "save": boolean("Save startup configuration; default true. / 保存启动配置，默认是。", True)}, ("device", "commands"), destructive=True),
    Tool("pt_show", "show", "Run one IOS show command and return its real output. / 返回show命令实际输出。",
         {"device": string("Router or switch name. / 设备名。"), "command": string("Single show command, e.g. show vlan brief. / 单条show命令。")},
         ("device", "command"), read_only=True),
    Tool("pt_pc_ipconfig", "pc_ipconfig", "Read real PC ipconfig output. / 读取PC实际ipconfig输出。", {"device": string("PC name. / PC名称。")}, ("device",), read_only=True),
    Tool("pt_ping", "ping", "Run PC ping and retain actual output for every attempt. Advances simulator time while waiting. / 执行真实PC ping，保留每次结果并推进仿真时间。",
         {"device": string("Source PC. / 源PC。"), "destination": string("Destination IPv4 address. / 目标IPv4。"),
          "attempts": {"type": "integer", "minimum": 1, "maximum": 3, "default": 2, "description": "Attempts; retry after address learning. / 测试次数。"},
          "timeout": {"type": "number", "minimum": 1, "maximum": 120, "default": 30, "description": "Seconds per attempt. / 每次超时秒数。"}}, ("device", "destination")),
    Tool("pt_fast_forward", "fast_forward", "Advance simulator time for boot, STP or command completion. / 推进仿真时间。", {}),
    Tool("pt_topology_png", "topology_png", "Return a native workspace PNG as MCP image content; optionally save it. / 返回原生拓扑PNG，可另存。",
         {"path": string("Optional local .png output; parent must exist. / 可选png保存路径。"), "overwrite": boolean("Replace an existing PNG. / 覆盖已有图片。")}, destructive=True),
]
TOOL_MAP = {tool.name: tool for tool in TOOLS}


def validate_arguments(tool: Tool, args: Any) -> dict:
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object.")
    unknown = set(args) - set(tool.properties)
    missing = set(tool.required) - set(args)
    if unknown or missing:
        raise ValueError("Unknown or missing arguments: " + ", ".join(sorted(unknown | missing)))
    for name, value in args.items():
        schema = tool.properties[name]
        kind = schema["type"]
        valid = (kind == "string" and isinstance(value, str)) or (kind == "boolean" and isinstance(value, bool))
        valid |= kind == "integer" and isinstance(value, int) and not isinstance(value, bool)
        valid |= kind == "number" and isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)
        valid |= kind == "array" and isinstance(value, list) and all(isinstance(x, str) for x in value)
        if not valid:
            raise ValueError(f"Argument {name} must have type {kind}.")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"Argument {name} has an unsupported value.")
        if kind in ("number", "integer") and (value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf)):
            raise ValueError(f"Argument {name} is outside the supported range.")
        if kind == "array" and not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000):
            raise ValueError(f"Argument {name} contains an unsupported number of items.")
        if kind == "string" and len(value) > 100_000:
            raise ValueError(f"Argument {name} is too long.")
    return args


def text_content(value: Any) -> dict:
    return {"type": "text", "text": json.dumps(value, ensure_ascii=False)}


class MCPServer:
    def __init__(self, backend: PacketTracer | None = None):
        self.backend = backend or PacketTracer()
        self.initialized = False

    @staticmethod
    def error(request_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def handle(self, request: Any) -> dict | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return self.error(request.get("id") if isinstance(request, dict) else None, -32600, "Invalid JSON-RPC request.")
        request_id = request.get("id")
        method = request["method"]
        if "id" not in request:
            return None  # notifications/initialized, cancelled, and other notifications
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            return self.error(None, -32600, "Request ID must be a string or integer.")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "Parameters must be an object.")
        if method == "initialize":
            requested = params.get("protocolVersion")
            if not isinstance(requested, str) or not isinstance(params.get("capabilities"), dict) or not isinstance(params.get("clientInfo"), dict):
                return self.error(request_id, -32602, "Expected protocolVersion, capabilities and clientInfo.")
            self.initialized = True
            result = {"protocolVersion": requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[-1],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "packet-tracer-mcp", "version": __version__},
                      "instructions": "Controls an installed Packet Tracer through native IPC. Save the active workspace before replacing it. / 使用原生IPC控制本机Packet Tracer，替换工作区前先保存。"}
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return self.error(request_id, -32002, "Initialize the MCP session first.")
        elif method == "tools/list":
            result = {"tools": [tool.metadata() for tool in TOOLS]}
        elif method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str) or name not in TOOL_MAP:
                return self.error(request_id, -32602, "Unknown tool.")
            tool = TOOL_MAP[name]
            try:
                args = validate_arguments(tool, params.get("arguments", {}))
                value = getattr(self.backend, tool.method)(**args)
                if name == "pt_topology_png":
                    data, metadata = value
                    content = [text_content(metadata), {"type": "image", "mimeType": "image/png", "data": base64.b64encode(data).decode("ascii")}]
                else:
                    content = [text_content(value)]
                failed = isinstance(value, dict) and value.get("ok") is False
                result = {"content": content, "isError": failed}
            except Exception as exc:
                result = {"content": [text_content({"error": type(exc).__name__, "message": str(exc)})], "isError": True}
        else:
            return self.error(request_id, -32601, "Method not found.")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def run(self, reader: BinaryIO, writer: BinaryIO) -> None:
        def reject_constant(value):
            raise ValueError("Nonfinite JSON values are not permitted.")
        try:
            while True:
                line = reader.readline(MAX_MESSAGE + 1)
                if not line:
                    break
                if len(line) > MAX_MESSAGE:
                    # Drain only to this newline, then accept subsequent requests.
                    while line and not line.endswith(b"\n"):
                        line = reader.readline(MAX_MESSAGE + 1)
                    response = self.error(None, -32600, "JSON-RPC message exceeds 1 MiB.")
                else:
                    try:
                        request = json.loads(line, parse_constant=reject_constant)
                    except (ValueError, UnicodeDecodeError):
                        response = self.error(None, -32700, "Invalid JSON.")
                    else:
                        response = self.handle(request)
                if response is not None:
                    writer.write((json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8"))
                    writer.flush()
        finally:
            self.backend.close()


def run_stdio() -> None:
    import sys
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    MCPServer().run(sys.stdin.buffer, sys.stdout.buffer)
