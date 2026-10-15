# ExApp registration / ExApp登记

## English

The default setup path generates a manifest using the `meta` program shipped with Packet Tracer. It does not distribute a manifest with shared credentials. Each machine generates its own random secret. Registration is normally completed through Packet Tracer's **Extensions → IPC → Configure Apps** menu.

For Windows **8.0**, `--register-user-config` provides an optional code-only registration method. Packet Tracer must be closed first: it caches settings and could overwrite an external change on exit. The command refuses a running `PacketTracer.exe`.

The user options format tested on 8.0 is a four-byte big-endian uncompressed length followed by zlib-compressed XML; each resulting byte is XORed with the low eight bits of the remaining file length. This is a version-specific implementation detail, not a Cisco-supported registration API. The command validates the size and XML before touching settings. It updates only `IPC_MANAGER/METAFILE_PATH`, retaining other entries. The install directory's `bin/PT.conf` is read as a baseline when user settings are absent; it is never written.

By default the user file is `~/Cisco Packet Tracer 8.0/PT.conf`. If your installation uses another user location, supply `--user-config`. Before every change, the original user file (or empty bytes when absent) is backed up as `PT.conf.packet-tracer-mcp-<timestamp>.bak`. The actual update uses an atomic file replacement. An already registered path is left unchanged.

To remove only this project's manifest, close Packet Tracer normally and run:

```powershell
python run_server.py unregister --pt-home "C:\Program Files\Cisco Packet Tracer 8.0" --user-config "$env:USERPROFILE\Cisco Packet Tracer 8.0\PT.conf"
```

For a custom manifest location, add `--manifest "C:\path\packet-tracer-mcp.pta"`. Unregistration removes that exact path while retaining subsequent settings changes and other applications. It also makes a fresh backup. To restore the entire prior settings file instead, with Packet Tracer closed, copy the matching backup back to `PT.conf`; if the backup is empty, the user file originally did not exist. Full restoration reverts all intervening user settings, so prefer targeted unregistration.

Other versions or operating systems should use the normal registration menu. Pass `--pt-version` when generating a manifest for another installed version, but treat native API compatibility as unverified. `--register-user-config` does not silently enable IPC or change remote-access settings.

## 中文

默认setup调用Packet Tracer自带的`meta`生成清单，不提供使用共享密钥的`.pta`。每台电脑生成独立随机密钥。通常在**Extensions → IPC → Configure Apps**菜单登记。

Windows **8.0**可选择`--register-user-config`实现代码登记。必须先正常关闭软件：Packet Tracer会缓存配置，退出时可能覆盖外部修改。命令发现`PacketTracer.exe`仍在运行时会拒绝执行。

8.0实测用户配置格式为四字节大端原始长度、zlib压缩XML，再按剩余文件长度低八位逐字节异或。这是版本相关实现细节，并非Cisco承诺支持的配置接口。命令验证长度和XML后，仅更新`IPC_MANAGER/METAFILE_PATH`。用户配置不存在时读取安装目录`bin/PT.conf`作为基线，绝不写入安装目录。

默认用户文件为`~/Cisco Packet Tracer 8.0/PT.conf`，可用`--user-config`指定其他位置。修改前备份原文件；原文件不存在时备份为空。备份名为`PT.conf.packet-tracer-mcp-<时间戳>.bak`，更新采用原子替换。已登记的路径不重复添加。

撤销时先正常关闭软件，再执行上方`unregister`命令；自定义清单路径用`--manifest`指定。它只删除指定清单，保留其他应用和后续设置，并再次备份。也可在软件关闭时将对应备份复制回`PT.conf`，但这样会撤销备份之后的其他设置；空备份表示用户配置原先不存在。一般优先使用定向移除。

其他版本或系统请用正常登记菜单，生成时可指定`--pt-version`，但原生接口兼容性未实测。自动登记不会自行启用IPC或修改远程访问设置。
