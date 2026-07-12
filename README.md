# Pepper Monitor

胡椒监控系统稳定版备份仓库。

## 服务与端口

- Pi 摄像头服务：`camera_server.py`，端口 `8888`
- Pi 音频监听服务：`monitor_server.py`，端口 `8889`
- SSH 反向隧道：远程 `8082` → Pi `8888`，远程 `8083` → Pi `8889`
- 远程 HTTPS 面板：`server_async_simple_fix.py`，端口 `8443`
- 远程音频代理：`ws_audio_proxy_fixed.py`，端口 `8445`
- 视频流：`640x360`、`5fps`、MJPEG
- 采集策略：有客户端观看时启动 ffmpeg，无客户端时停止 ffmpeg
- 多客户端：iOS 原生 MJPEG，Android/Via fetch 拆帧
- watchdog：Pi 端 crontab 每分钟运行 `pepper_camera_watchdog.py`

## 运行要求

- Python 3.9 或更高版本（Python 3.10+ 使用 `websockets 16.1`）
- `python3-venv`
- `ffmpeg` / `ffplay`
- OpenSSH 客户端
- 可用的 V4L2 摄像头和 ALSA 录音/播放设备

Python 依赖统一记录在根目录的 `requirements.txt` 中。

## 目录

- `pi/scripts/`：树莓派 live 脚本
- `pi/systemd/`：树莓派 user systemd 服务
- `remote/`：雨云服务器端面板与代理
- `remote/systemd/`：雨云服务器 systemd 服务
- `scripts/`：Pi 与远程服务器部署脚本

## 部署 Pi

先安装系统依赖（以 Raspberry Pi OS / Debian 为例）：

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg openssh-client
./scripts/deploy-pi.sh
```

脚本会将程序安装到 `~/.local/share/pepper-monitor`，创建 Python
虚拟环境，并启用摄像头与音频 user services。若 `~/.asoundrc`
已经存在，脚本会保留现有配置。

首次部署时，编辑 SSH 隧道配置：

```bash
editor ~/.config/pepper-monitor/tunnel.env
systemctl --user enable --now rainyun-tunnel.service
```

如果 user services 需要在用户退出登录后继续运行，执行：

```bash
sudo loginctl enable-linger "$USER"
```

查看运行状态：

```bash
systemctl --user status pepper-camera-pi pepper-monitor-pi rainyun-tunnel
```

watchdog 仍按稳定版方式由 crontab 每分钟运行，部署后的脚本路径为：

```text
~/.local/share/pepper-monitor/pi/scripts/pepper_camera_watchdog.py
```

## 部署远程服务器

远程服务需要 TLS 证书和私钥。首次部署时通过环境变量提供文件：

```bash
sudo env \
  CERT_FILE=/path/to/fullchain.pem \
  KEY_FILE=/path/to/privkey.pem \
  AVATAR_FILE=/path/to/avatar.jpg \
  ./scripts/deploy-remote.sh
```

`AVATAR_FILE` 可省略。脚本将文件部署到 `/opt/webcam-dashboard`，
安装并启动 `ws-audio-proxy.service` 与 `pepper-monitor.service`。
后续部署若目标目录已有证书，可以不再传 `CERT_FILE` 和 `KEY_FILE`。

查看运行状态：

```bash
sudo systemctl status ws-audio-proxy pepper-monitor
```

## 备份

- Pi 最新备份：`/home/ckjoy/.openclaw/workspace/pepper-monitor-backup-latest.tar.gz`
- Pi 归档备份：`/home/ckjoy/openclaw-monitor-backup/pepper_monitor_20260505_2244.tar.gz`
- 坚果云：`/OpenClaw_Backups/monitor/pepper-monitor-backup-20260505_2244.tar.gz`
- 最近备份时间：`2026-05-05 22:44 CST`
