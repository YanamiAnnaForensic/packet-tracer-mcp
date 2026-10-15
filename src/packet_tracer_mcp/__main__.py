import argparse
import json
from pathlib import Path
import sys

from .backend import PacketTracer
from .config import state_directory
from .setup import register_user_config, setup_exapp


def main() -> None:
    # Windows CI and redirected consoles may default to ASCII/cp1252. The CLI
    # contains Chinese text; MCP itself always writes UTF-8 to the binary stream.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Packet Tracer MCP / Packet Tracer原生接口MCP服务")
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("serve", help="Run the MCP stdio service (default). / 启动MCP服务。")
    subs.add_parser("status", help="Check native IPC connection. / 检查IPC连接。")
    setup = subs.add_parser("setup", help="Generate a local ExApp manifest. / 生成本机ExApp。")
    setup.add_argument("--pt-home", type=Path, required=True)
    setup.add_argument("--pt-version", default="8.0")
    setup.add_argument("--output-dir", type=Path)
    setup.add_argument("--register-user-config", action="store_true", help="Windows PT 8.0 only; close PT first. / 自动登记，须先关闭PT。")
    setup.add_argument("--user-config", type=Path)
    remove = subs.add_parser("unregister", help="Remove only this manifest from user settings. / 移除本项目登记。")
    remove.add_argument("--pt-home", type=Path, required=True)
    remove.add_argument("--user-config", type=Path, required=True)
    remove.add_argument("--manifest", type=Path, default=state_directory() / "packet-tracer-mcp.pta")
    args = parser.parse_args()
    if args.command in (None, "serve"):
        from .server import run_stdio
        run_stdio()
        return
    try:
        if args.command == "setup":
            result = setup_exapp(args.pt_home, args.pt_version, args.output_dir, args.register_user_config, args.user_config)
        elif args.command == "unregister":
            result = register_user_config(args.user_config, args.pt_home / "bin/PT.conf", args.manifest, remove=True)
        else:
            tracer = PacketTracer()
            try:
                result = tracer.status()
            finally:
                tracer.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "status" and not result["connected"]:
            sys.exit(1)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
