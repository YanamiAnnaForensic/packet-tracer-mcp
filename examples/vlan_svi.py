"""Build a small SVI demonstration through real MCP calls, with explicit workspace replacement.

Run: python examples/vlan_svi.py --output /absolute/demo.pkt --replace-workspace
The output must not already exist. Save any current Packet Tracer project first.
"""

import argparse
import json
from pathlib import Path

from stdio_client import Client


def build(client, output, replace=False):
    client.tool("pt_new_network", discard_current=replace)
    for name, kind, x, y in [("Core", "multilayer_switch", 350, 100),
                             ("Access", "switch", 350, 250), ("PC-A", "pc", 200, 430), ("PC-B", "pc", 500, 430)]:
        client.tool("pt_create_device", name=name, kind=kind, x=x, y=y)
    for a, pa, b, pb, cable in [("Core", "GigabitEthernet0/1", "Access", "GigabitEthernet0/1", "crossover"),
                                ("PC-A", "FastEthernet0", "Access", "FastEthernet0/5", "straight"),
                                ("PC-B", "FastEthernet0", "Access", "FastEthernet0/10", "straight")]:
        client.tool("pt_connect_devices", device_a=a, port_a=pa, device_b=b, port_b=pb, cable=cable)
    for name, address, gateway in [("PC-A", "192.168.10.1", "192.168.10.254"), ("PC-B", "192.168.20.1", "192.168.20.254")]:
        client.tool("pt_set_pc_ipv4", device=name, address=address, netmask="255.255.255.0", gateway=gateway)
    access = ["hostname Access", "vlan 10", "name v10", "exit", "vlan 20", "name v20", "exit"]
    for port, vlan in [(5, 10), (10, 20)]:
        access.extend([f"interface FastEthernet0/{port}", "switchport mode access", f"switchport access vlan {vlan}", "no shutdown", "exit"])
    access.extend(["interface GigabitEthernet0/1", "switchport mode trunk", "switchport trunk allowed vlan 10,20", "no shutdown", "exit"])
    client.tool("pt_configure_ios", device="Access", commands=access)
    core = ["hostname Core"]
    for vlan in [10, 20]:
        core.extend([f"vlan {vlan}", f"name v{vlan}", "exit", f"interface Vlan{vlan}",
                     f"ip address 192.168.{vlan}.254 255.255.255.0", "no shutdown", "exit"])
    core.extend(["interface GigabitEthernet0/1", "switchport trunk encapsulation dot1q", "switchport mode trunk",
                 "switchport trunk allowed vlan 10,20", "no shutdown", "exit", "ip routing"])
    client.tool("pt_configure_ios", device="Core", commands=core)
    client.tool("pt_fast_forward")
    result = client.tool("pt_ping", device="PC-A", destination="192.168.20.1", attempts=3)
    if not result["success"]:
        raise RuntimeError("The demonstration's real ping failed.")
    client.tool("pt_save_network", path=str(output))
    client.tool("pt_topology_png", path=str(output.with_suffix(".png")))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build an SVI topology using MCP. / 使用MCP构建SVI拓扑。")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace-workspace", action="store_true")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists() or output.with_suffix(".png").exists():
        parser.error("Output .pkt/.png already exists. Choose a new name.")
    client = Client()
    try:
        client.initialize()
        print(json.dumps(build(client, output, args.replace_workspace), ensure_ascii=False, indent=2))
    finally:
        client.close()
