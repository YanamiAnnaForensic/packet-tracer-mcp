# Verification / 验证记录

Release preparation date: **2026-10-15**. / 发布前验证日期：**2026-10-15**。

## Automated checks / 自动检查

18 tests passed using `python -m unittest discover -s tests -v` on Windows with Python 3.13. Tests use a local fake TCP peer and an isolated MCP backend, so contributors can run them without Cisco software or real credentials.

Windows、Python 3.13环境下18项测试通过。协议测试使用本地模拟TCP端，MCP测试使用隔离后端，无须安装Cisco程序或提供实际凭据。

Checks include fragmented PNG byte vectors containing NUL/non-UTF-8 bytes, Unicode arguments, challenge authentication, IPC errors, EOF during payload reads, wrong response IDs, oversized frames, PT.conf round trips/backup/idempotence/unregistration, JSON-RPC initialization, tool validation and image content.

## Live native checks / 原生实测

Environment: Windows, **Cisco Packet Tracer 8.0.0.0212**, Python 3.13. All actions below ran through a separate MCP stdio process, not mouse or keyboard control.

环境：Windows、**Cisco Packet Tracer 8.0.0.0212**、Python 3.13。以下操作均通过独立MCP stdio进程执行，无鼠标键盘控制。

| Check / 检查 | Observed result / 实际结果 |
| --- | --- |
| Initialize + tools/list | Negotiated 2025-06-18; 14 tools / 协商版本与14个工具 |
| Native create/connect/configure | Core3560-class device, 2960-class device, two PCs, links and IOS accepted / 设备、连线及配置成功 |
| PC IPv4 + ipconfig | Configured addresses read back / 地址读回成功 |
| Cross-VLAN ping with SVI routing | Final attempt: 4 sent, 4 received, 0 lost / 最终4发4收 |
| `no ip routing` | 4 sent, 0 received, 4 lost / 关闭后4发0收 |
| Restore `ip routing` | 4 sent, 4 received, 0 lost / 恢复后4发4收 |
| Save `.pkt`, reopen, ping | Saved file reopened; 4 sent, 4 received / 重开后4发4收 |
| Native topology export | Nonempty native PNG saved through MCP / 原生PNG已保存 |
| Restore prior workspace | Original workspace reopened; original saved file hash unchanged / 恢复原工作区，文件哈希未变 |
| ExApp setup | Cisco's installed `meta.exe` generated a local .pta; no plaintext manifest retained / 本机清单生成成功，无明文清单残留 |

The release contains source and synthetic test fixtures only. Actual credential files, personal topologies and raw course logs are intentionally absent. Python CI targets Windows/macOS/Linux; native Packet Tracer interoperability has only been verified on the Windows/version combination above.

发布包仅含源码与模拟测试数据，不包含真实凭据、个人拓扑或课程日志。CI检查Python跨平台运行；原生Packet Tracer仅在上方Windows和版本组合实测。
