# Protocol notes / 协议记录

## Architecture / 结构

```text
MCP client ── stdio JSON-RPC ── Python MCP adapter ── TCP PTMP/IPC ── Packet Tracer
```

The server implements MCP initialization, `ping`, `tools/list` and `tools/call`. It advertises only tools; it does not claim prompts, resources, HTTP transport or background tasks. Supported protocol versions: `2024-11-05`, `2025-03-26`, `2025-06-18`. Other requested versions receive `2025-06-18` in the initialization response. Incoming messages use UTF-8, one JSON-RPC object per line, with a 1 MiB input limit. Tool execution is synchronous and serial; cancellation notifications are accepted without actively interrupting in-flight operations. Calls use bounded timeouts. Standard output contains only JSON-RPC.

服务实现MCP初始化、`ping`、`tools/list`、`tools/call`，仅声明工具能力。不提供prompt、resource、HTTP或后台任务。支持的协议版本见上方；未知版本在初始化回复中返回`2025-06-18`。输入为UTF-8逐行JSON-RPC，单条上限1MiB。工具同步串行执行，不主动中断正在执行的取消请求；操作有超时限制。标准输出只包含协议消息。

## PTMP transport / PTMP传输

Each frame is `<ASCII byte length> NUL <body>`. Text fields are UTF-8 and NUL-terminated. Byte-vector values contain raw binary bytes, so a PNG must not be parsed by splitting the entire payload as text.

帧格式为`ASCII字节长度 + NUL + 正文`。文本字段采用UTF-8并以NUL结束。字节向量直接包含二进制数据，PNG不能按文本切分。

The client negotiates text encoding, no encryption, no compression and the protocol-mandated MD5 authentication. The challenge digest is uppercase hexadecimal MD5 of `challenge + local secret`. No credentials are shipped in the repository.

客户端协商文本编码、无加密、无压缩以及协议要求的MD5认证。摘要为`challenge + 本机密钥`的MD5大写十六进制。仓库不包含实际凭据。

| Message | Purpose / 用途 |
| --- | --- |
| 0–1 | Negotiation / 协商 |
| 2–5 | Application authentication / 应用认证 |
| 6–7 | Keepalive or disconnect / 保活或断开 |
| 100–102 | IPC request, error, result / 请求、错误、结果 |
| 103–104 | Events and subscriptions / 事件和订阅 |

Verified argument codes include `2=bool`, `4=int`, `7=double`, `8=string`, `9=QString`, `10=IPv4`, `13=UUID`. String and QString are distinct method signatures even though both are text on the wire. `14` is a pair, `15` is a typed vector. Only the known `CommandHistory` value object is decoded for code `16`; unsupported value layouts fail explicitly.

已验证参数编码包括上表所列类型。`string`和`QString`线上都为文本，但接口签名不同。`14`代表二元组，`15`代表有类型的向量；`16`仅解析已知`CommandHistory`对象，未知布局明确报错。

The client checks frame sizes, fragmented reads, response IDs and disconnects. It closes a broken transport and never automatically repeats a failed mutation. PC command results are collected from real `TerminalLine.outputWritten` / `commandEnded` events. `pt_ping` advances native simulation time while waiting and preserves all actual attempts.

客户端检查帧大小、分片读取、请求响应编号及断线；连接损坏后关闭，不自动重放修改操作。PC结果来自真实`TerminalLine`事件，ping等待期间推进仿真时间并保留所有实际尝试。

References: [MCP 2025-06-18 specification](https://modelcontextprotocol.io/specification/2025-06-18), [Cisco PTMP specification](https://tutorials.ptnetacad.net/help/default/files/CiscoPacketTracerPTMPSpecification.pdf), [NOTICE](../NOTICE.md).
