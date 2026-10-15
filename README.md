# Packet Tracer MCP

[English](README.md) | [简体中文](README.zh-CN.md)

Control Cisco Packet Tracer from an MCP client through its native PTMP/IPC interface. Create devices and links, configure IOS and PC addresses, run real ping tests, save `.pkt` files, and export the native topology as a PNG.

**Python 3.10+, no runtime dependencies, no desktop automation.** Packet Tracer itself must be installed, running and authenticated through its normal workflow. This is an independent project, not a Cisco product.

## What is verified

- Live-tested on **Windows with Packet Tracer 8.0.0.0212**.
- The MCP stdio flow covers initialization, 14 tool definitions, native device creation, cabling, addressing, IOS configuration, ping, `.pkt` save/reopen and PNG export.
- A separate two-VLAN SVI example verifies communication with routing enabled, isolation with routing disabled, and communication again after restoration.
- Python/protocol tests run without Packet Tracer. Compatibility with other Packet Tracer versions, macOS and Linux **has not been live-tested**. Python portability does not guarantee native IPC compatibility.

## Quick start

```sh
git clone https://github.com/YanamiAnnaForensic/packet-tracer-mcp.git
cd packet-tracer-mcp
python run_server.py --help
```

You can run directly from the checkout. Package installation is optional: `python -m pip install .` provides the `packet-tracer-mcp` command.

### 1. Generate local ExApp credentials

Packet Tracer accepts registered external applications (ExApps). Use its included `meta` utility to generate a manifest:

```powershell
python run_server.py setup --pt-home "C:\Program Files\Cisco Packet Tracer 8.0" --pt-version 8.0
```

The command prints the paths of `packet-tracer-mcp.pta` and `connection.json`, without printing the secret. By default they live under `%LOCALAPPDATA%\PacketTracerMCP` on Windows, `~/Library/Application Support/PacketTracerMCP` on macOS, or `$XDG_CONFIG_HOME/packet-tracer-mcp` (`~/.config` fallback) on Linux. Re-running setup reuses existing credentials.

### 2. Register the manifest

In Packet Tracer, use **Extensions → IPC → Configure Apps → Add**, choose the generated `.pta`, and confirm. Exit Packet Tracer normally once so its settings persist, then restart it. Confirm that IPC is enabled and uses port 39000.

Alternatively, for **Windows Packet Tracer 8.0 only**, close Packet Tracer normally and run:

```powershell
python run_server.py setup --pt-home "C:\Program Files\Cisco Packet Tracer 8.0" --register-user-config
```

This adds only the manifest entry to the **user** `PT.conf`, creates a timestamped backup, and leaves installation files unchanged. It refuses to run while `PacketTracer.exe` is running. Existing options and other registered apps are retained. It does not enable IPC if your settings disabled it. Details and undo instructions: [Registration](docs/registration.md).

### 3. Check the connection

```sh
python run_server.py status
```

Expected: `connected: true`, the installed version and the current device count. If setup used `--output-dir`, set `PT_MCP_CONFIG` to that directory's `connection.json` before starting the server.

### 4. Add to an MCP client

Replace the Python command and script path with absolute paths on your computer. The client launches this process over **stdio**:

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

If the MCP client cannot resolve `python`, use the absolute Python executable path. A generic example is in [examples/mcp-client.json](examples/mcp-client.json). Client-specific configuration formats may differ.

## Tools

| Tool | Function |
| --- | --- |
| `pt_status` | Connection, version and device count |
| `pt_list_devices` | Device names, models and type codes |
| `pt_new_network` | Create an empty workspace |
| `pt_open_network` | Open a local `.pkt` |
| `pt_save_network` | Save `.pkt`; overwriting is explicit |
| `pt_create_device` | Add a PC, router, 2960 switch or 3560 multilayer switch |
| `pt_connect_devices` | Connect exact port names with straight/crossover cables |
| `pt_set_pc_ipv4` | Set a PC's IPv4 address, mask and gateway |
| `pt_configure_ios` | Run IOS config lines and optionally `write memory` |
| `pt_show` | Return real output from a single IOS `show` command |
| `pt_pc_ipconfig` | Read real PC address output |
| `pt_ping` | Return actual replies and sent/received/lost statistics for every attempt |
| `pt_fast_forward` | Advance simulator time |
| `pt_topology_png` | Return a native PNG as MCP image content; optionally save it |

Tool descriptions are bilingual. Mutations are serialized against Packet Tracer's active workspace. Opening/replacing a populated workspace requires `discard_current=true`. File replacement requires `overwrite=true`. Tools do not retry network mutations automatically after a transport failure; inspect the actual state before retrying.

`pt_configure_ios` enters global configuration mode automatically. Supply only commands that would follow `configure terminal`. Syntax errors stop the operation and return the command transcript; previously accepted commands remain applied. `pt_ping` may retry after address learning, but every attempt's real output is retained and reported. An unsuccessful or unparseable ping is never synthesized into success.

`pt_topology_png` exports the native logical workspace. It is not a screenshot of a CLI dialog or the desktop. Some native labels may overlap in Packet Tracer's export.

## Example

First save your active Packet Tracer project. Choose a new output filename in an existing directory:

```powershell
python examples/vlan_svi.py --output "C:\labs\demo.pkt" --replace-workspace
```

This builds a small, independent VLAN10/VLAN20 SVI topology through real MCP calls, checks cross-VLAN ping, and saves `.pkt` and `.png` outputs. `--replace-workspace` explicitly discards the current workspace; omit it when starting from an empty one. The example refuses existing output files.

For a connection-only example, run `python examples/stdio_client.py`.

## Configuration

| Environment variable | Meaning / default |
| --- | --- |
| `PT_MCP_CONFIG` | Path to local `connection.json` |
| `PT_MCP_APP_ID` / `PT_MCP_SECRET` | Override ExApp credentials |
| `PT_MCP_HOST` | IPC host; defaults to `127.0.0.1` |
| `PT_MCP_PORT` | IPC port; defaults to `39000` |
| `PT_MCP_TIMEOUT` | Per-IPC-call timeout in seconds; defaults to `30` |

All paths refer to the computer running the MCP server. Keep `connection.json`, `.pta` and `PT.conf` backups private. The `.pta` also contains the local secret. PTMP's MD5 authentication is required by Packet Tracer; this connection is not an encrypted transport. Use local IPC with Packet Tracer's **Allow Remote Applications** disabled.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Tests cover fragmented/binary PTMP frames, Unicode, authentication, disconnects, reply matching, configuration backups, MCP handshake and tool validation. See [contributing](CONTRIBUTING.md), [protocol notes](docs/protocol.md), and [test evidence](docs/verification.md).

## Credits and license

MIT, copyright YanamiAnnaForensic. See [LICENSE](LICENSE).

The PTMP implementation was informed by [Cisco's PTMP specification](https://tutorials.ptnetacad.net/help/default/files/CiscoPacketTracerPTMPSpecification.pdf), the installed Cisco IPC framework, [pktctl](https://github.com/TantiE100/pktctl) and [PT Python examples](https://github.com/bfranske/pt-python-examples). See [NOTICE.md](NOTICE.md). No Cisco binaries, SDK archives, third-party API index, account credentials or course assignments are distributed.
