# References and attribution / 参考与署名

This repository contains an independently written Python PTMP client, a small MCP stdio adapter, setup tooling and examples. Development used the following references to understand public/native interface behavior:

本仓库包含独立编写的Python PTMP客户端、MCP stdio适配层、登记工具及示例。开发参考了以下资料以理解协议及本机接口行为：

- Cisco's [Packet Tracer PTMP Specification](https://tutorials.ptnetacad.net/help/default/files/CiscoPacketTracerPTMPSpecification.pdf) and the IPC framework/Javadoc included in the user's installed Packet Tracer.
- [TantiE100/pktctl](https://github.com/TantiE100/pktctl): reference for observed IPC argument signatures, PTMP message/value codes, and ExApp manifest fields.
- [bfranske/pt-python-examples](https://github.com/bfranske/pt-python-examples): reference for PTMP negotiation and external-application connectivity.
- [Model Context Protocol specification](https://modelcontextprotocol.io/specification/2025-06-18): stdio JSON-RPC lifecycle, tools and content blocks.

These references are linked, not vendored. No third-party source files or full generated IPC index are shipped. No Cisco executables, SDK archives, project files, activity files, course materials or real credentials are included. Cisco and Packet Tracer are trademarks of their respective owners. This project is not affiliated with or endorsed by Cisco.

上述资料仅链接，不随仓库打包；不分发第三方源码文件或完整生成的接口索引，不分发Cisco程序、SDK、工程、活动文件、课程材料或真实凭据。Cisco和Packet Tracer商标归相应权利人所有。本项目与Cisco无隶属或背书关系。
