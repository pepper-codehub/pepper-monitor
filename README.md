# Pepper Monitor

胡椒监控系统稳定版备份仓库。

## 当前稳定版（2026-04-25 20:38:46 CST）

- Pi 摄像头服务：`camera_server.py`，端口 `8888`
- Pi 音频监听服务：`monitor_server.py`，端口 `8889`
- 远程 HTTPS 面板：`server_async_simple_fix.py`
- 远程音频代理：`ws_audio_proxy_fixed.py`
- 视频流：`640x360`、`5fps`、MJPEG
- 采集策略：有客户端观看时启动 ffmpeg，无客户端时停止 ffmpeg
- 多客户端：iOS 原生 MJPEG，Android/Via fetch 拆帧
- watchdog：Pi 端 crontab 每分钟运行 `pepper_camera_watchdog.py`

## 备份

- Pi 最新备份：`/home/ckjoy/.openclaw/workspace/pepper-monitor-backup-latest.tar.gz`
- Pi 归档备份：`/home/ckjoy/openclaw-monitor-backup/pepper_monitor_20260505_2244.tar.gz`
- 坚果云：`/OpenClaw_Backups/monitor/pepper-monitor-backup-20260505_2244.tar.gz`
- 最近备份时间：`2026-05-05 22:44 CST`

## 目录

- `pi/scripts/`：树莓派 live 脚本
- `pi/systemd/`：树莓派 user systemd 服务
- `remote/`：雨云服务器端面板与代理
- `remote/systemd/`：雨云服务器 systemd 服务
