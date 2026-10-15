# Packet Tracer MCP

[English](README.md) | [简体中文](README.zh-CN.md)

通过MCP客户端和Cisco Packet Tracer的原生PTMP/IPC接口，创建设备与连线、配置IOS与PC地址、执行真实ping、保存`.pkt`文件，并导出原生拓扑PNG。

**仅需Python 3.10及以上，无运行时依赖，不使用桌面自动化。** 你需要自行安装Packet Tracer，通过正常流程登录并启动软件。本项目是独立开源项目，并非Cisco官方产品。

## 已验证范围

- 已在**Windows + Packet Tracer 8.0.0.0212**上实际验证。
- MCP stdio流程包含初始化、14个工具、设备创建、连线、地址与IOS配置、ping、`.pkt`保存与重开、PNG导出。
- 使用独立的两VLAN SVI示例，验证了开启路由时通信、关闭路由时隔离、恢复路由后再次通信。
- Python及协议测试无需安装Packet Tracer。其他Packet Tracer版本、macOS和Linux的原生连接**尚未实机验证**；Python能运行不代表原生IPC一定兼容。

## 快速开始

```sh
git clone https://github.com/YanamiAnnaForensic/packet-tracer-mcp.git
cd packet-tracer-mcp
python run_server.py --help
```

可以直接运行源码，无须安装依赖。也可以执行`python -m pip install .`，安装后使用`packet-tracer-mcp`命令。

### 1. 生成本机ExApp

Packet Tracer只接受已登记的外部应用（ExApp）。以下命令调用Cisco自带的`meta`工具，生成本机清单和随机连接凭据：

```powershell
python run_server.py setup --pt-home "C:\Program Files\Cisco Packet Tracer 8.0" --pt-version 8.0
```

命令只输出`packet-tracer-mcp.pta`和`connection.json`的路径，不打印密钥。默认目录：Windows为`%LOCALAPPDATA%\PacketTracerMCP`；macOS为`~/Library/Application Support/PacketTracerMCP`；Linux为`$XDG_CONFIG_HOME/packet-tracer-mcp`，未设置时使用`~/.config/packet-tracer-mcp`。重复执行会沿用已有凭据。

### 2. 登记清单

在Packet Tracer中选择**Extensions → IPC → Configure Apps → Add**，添加生成的`.pta`文件并确认。正常退出软件一次，使配置写入磁盘，然后重新启动。确认IPC已启用，端口为39000。

对于**Windows上的Packet Tracer 8.0**，还可以先正常关闭Packet Tracer，再使用以下代码登记方式：

```powershell
python run_server.py setup --pt-home "C:\Program Files\Cisco Packet Tracer 8.0" --register-user-config
```

它只向**用户目录**的`PT.conf`添加本项目清单，先生成带时间戳的备份，不修改安装目录。检测到`PacketTracer.exe`仍在运行时会拒绝修改；原有设置及其他ExApp登记会保留。如果你的IPC原来已禁用，此命令不会替你启用。详情和撤销方法见[登记说明](docs/registration.md)。

### 3. 检查连接

```sh
python run_server.py status
```

正常时输出`connected: true`、安装版本和设备数量。若生成清单时用了`--output-dir`，启动服务前请把`PT_MCP_CONFIG`设为该目录中的`connection.json`。

### 4. 加入MCP客户端

把Python和脚本路径改为你电脑上的绝对路径。客户端通过**stdio**启动服务：

```json
{
  "mcpServers": {
    "packet-tracer": {
      "command": "python",
      "args": ["C:/path/to/packet-tracer-mcp/run_server.py", "serve"]
    }
  }
}
```

如果客户端找不到`python`，请填写Python可执行文件的绝对路径。通用配置示例见[examples/mcp-client.json](examples/mcp-client.json)，不同客户端的配置格式可能不同。

## 工具列表

| 工具 | 用途 |
| --- | --- |
| `pt_status` | 查看连接、软件版本、设备数量 |
| `pt_list_devices` | 列出设备名称、型号、类型 |
| `pt_new_network` | 新建空工作区 |
| `pt_open_network` | 打开本机`.pkt`文件 |
| `pt_save_network` | 保存`.pkt`，覆盖须明确指定 |
| `pt_create_device` | 创建PC、路由器、2960、3560等设备 |
| `pt_connect_devices` | 用直通线或交叉线连接指定端口 |
| `pt_set_pc_ipv4` | 设置PC地址、掩码、默认网关 |
| `pt_configure_ios` | 执行IOS配置命令，可执行`write memory`保存 |
| `pt_show` | 返回单条IOS `show`命令的真实输出 |
| `pt_pc_ipconfig` | 读取PC真实地址信息 |
| `pt_ping` | 执行真实ping，保留每次回复和收发统计 |
| `pt_fast_forward` | 推进仿真时间 |
| `pt_topology_png` | 以MCP图片内容返回原生拓扑PNG，可另存文件 |

工具说明均为中英双语。网络操作按顺序执行，作用于Packet Tracer当前工作区。替换已有工作区须指定`discard_current=true`；覆盖文件须指定`overwrite=true`。连接中断后不会自动重试网络修改，重试前请先检查实际状态。

`pt_configure_ios`自动进入全局配置模式，传入通常在`configure terminal`后执行的命令即可。遇到语法错误会停止并返回执行记录；之前成功执行的命令仍然有效。`pt_ping`可在地址学习后重试，每次实际输出都保留，不会把失败或无法解析的结果当成成功。

`pt_topology_png`导出软件原生逻辑拓扑，并非CLI窗口或桌面截图。Packet Tracer自身导出的部分设备标签可能重叠。

## 示例

先保存当前Packet Tracer工程，再选择一个位于已有目录中的新文件名：

```powershell
python examples/vlan_svi.py --output "C:\labs\demo.pkt" --replace-workspace
```

示例通过真实MCP调用构建独立的VLAN10/VLAN20 SVI网络，测试跨VLAN通信，保存`.pkt`和`.png`。`--replace-workspace`明确表示放弃当前工作区；当前为空时可不加。示例拒绝覆盖已有输出。

仅检查连接与设备时，可运行`python examples/stdio_client.py`。

## 配置

| 环境变量 | 含义和默认值 |
| --- | --- |
| `PT_MCP_CONFIG` | 本机`connection.json`路径 |
| `PT_MCP_APP_ID`、`PT_MCP_SECRET` | 覆盖ExApp连接凭据 |
| `PT_MCP_HOST` | IPC主机，默认`127.0.0.1` |
| `PT_MCP_PORT` | IPC端口，默认`39000` |
| `PT_MCP_TIMEOUT` | 单次IPC调用超时秒数，默认`30` |

所有文件路径都属于运行MCP服务的电脑。请勿公开`connection.json`、`.pta`或`PT.conf`备份；`.pta`同样包含本机密钥。PTMP的MD5认证由Packet Tracer协议要求，传输本身未加密。使用本机IPC，并关闭Packet Tracer中的**Allow Remote Applications**。

## 开发与测试

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

测试覆盖分片与二进制PTMP帧、中文、认证、断线、响应匹配、配置备份、MCP握手和工具参数验证。参见[贡献说明](CONTRIBUTING.md)、[协议记录](docs/protocol.md)、[验证记录](docs/verification.md)。

## 来源与许可

MIT许可证，版权归YanamiAnnaForensic。参见[LICENSE](LICENSE)。

开发参考了[Cisco PTMP规范](https://tutorials.ptnetacad.net/help/default/files/CiscoPacketTracerPTMPSpecification.pdf)、本机Cisco IPC框架、[pktctl](https://github.com/TantiE100/pktctl)及[PT Python示例](https://github.com/bfranske/pt-python-examples)，详见[NOTICE.md](NOTICE.md)。本仓库不分发Cisco二进制文件、SDK归档、第三方完整API索引、账户凭据或课程作业。
