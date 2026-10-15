# Contributing / 参与贡献

Use Python 3.10 or later. Clone the repository, then run:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Keep network operations serialized. Do not add GUI/keyboard/mouse automation to the native backend. Never synthesize success from a timeout or replace actual Packet Tracer output with fabricated results. A new native method should document its exact argument codes, supported model/version, and live verification. Protocol handling changes need meaningful malformed/fragmented-message tests. Keep stdout exclusive to MCP JSON-RPC.

For live checks, save the current workspace, use a disposable network, and restore the original afterward. Do not commit `.pkt`, `.pka`, `.pta`, `connection.json`, PT.conf backups, credentials or personal lab materials. Cross-platform Python tests do not prove Packet Tracer compatibility: state which native installations you actually tested.

使用Python 3.10及以上。修改协议时添加分片、错误消息等实际有意义的测试；新原生接口记录参数编码、型号、软件版本和实测结果。保持串行网络操作，不加入鼠标键盘控制，不编造测试成功，标准输出仅用于MCP。实机测试前先保存当前工程，使用临时网络，结束后恢复。不要提交工程、活动文件、清单、凭据、配置备份或个人实验资料。跨平台Python测试通过不代表Packet Tracer实机兼容。
