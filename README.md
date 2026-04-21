# pepper-monitor

胡椒宝宝监控系统 — 基于 Raspberry Pi 的摄像头 + 音频实时监控，支持公网 HTTPS 访问、iOS 全屏、双向对讲。

## 系统架构

```
Pi (192.168.5.10)
├── pi/scripts/camera_server.py   :8888  从 Home Assistant 拉取摄像头图像（2s 后台缓存）
├── pi/scripts/monitor_server.py  :8889  ffmpeg plughw:2,0 → WebSocket PCM 16kHz
└── pi/systemd/rainyun-tunnel.service    SSH 反向隧道
      -R 8082:localhost:8888   (摄像头)
      -R 8083:localhost:8889   (音频)

远程服务器 (103.45.162.207)
├── remote/server_async_simple_fix.py  :8443 HTTPS
│     GET  /camera.jpg     → 127.0.0.1:8082 (SSH隧道→Pi:8888)
│     WebSocket /ws/audio  → 127.0.0.1:8445
└── remote/ws_audio_proxy_fixed.py     :8445
      → 127.0.0.1:8083 (SSH隧道) → Pi:8889

公网访问：https://103.45.162.206:54325  (NAT → 103.45.162.207:8443)
```

## 功能特性

- **实时摄像头** — 每 2 秒自动刷新，后台预取缓存，响应零延迟
- **实时音频监听** — WebSocket PCM 流，浏览器端实时播放
- **双向对讲** — 麦克风录音发送到 Pi 播放
- **iOS 全屏** — 支持 `requestFullscreen`，不可用时 CSS overlay fallback
- **开机自启** — Pi 和远程服务器所有服务均已 `systemctl enable`，Linger=yes

## Pi 部署

```bash
# 1. 复制脚本
cp pi/scripts/camera_server.py  ~/.openclaw/workspace/scripts/
cp pi/scripts/monitor_server.py ~/.openclaw/workspace/scripts/

# 2. 安装 systemd user 服务
cp pi/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rainyun-tunnel pepper-camera-pi pepper-monitor-pi openclaw-gateway
loginctl enable-linger $USER

# 3. 音频默认输出（USB 扬声器）
cp pi/asoundrc ~/.asoundrc

# 4. 验证
systemctl --user status rainyun-tunnel pepper-camera-pi pepper-monitor-pi
```

## 远程服务器部署

```bash
# 1. 复制代码
cp remote/server_async_simple_fix.py /opt/webcam-dashboard/
cp remote/ws_audio_proxy_fixed.py    /opt/webcam-dashboard/
cp -r remote/templates/              /opt/webcam-dashboard/templates/

# 2. SSL 证书（自签名，有效期1年）
openssl req -x509 -newkey rsa:2048 -keyout /opt/webcam-dashboard/key.pem \
  -out /opt/webcam-dashboard/cert.pem -days 365 -nodes \
  -subj "/CN=pepper-monitor"

# 3. 安装 systemd system 服务
cp remote/systemd/pepper-monitor.service  /etc/systemd/system/
cp remote/systemd/ws-audio-proxy.service  /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pepper-monitor ws-audio-proxy

# 4. 验证
systemctl status pepper-monitor ws-audio-proxy
```

## 依赖

**Pi 端：**
- Python 3 标准库（`http.server`, `socketserver`, `threading`）
- `ffmpeg`（音频采集）
- `websockets` Python 包

**远程服务器端：**
- Python 3 + `aiohttp`, `aiohttp_session`, `websockets`
- SSL 证书（`cert.pem` / `key.pem`）

## 设备说明

| 设备 | 用途 |
|------|------|
| Pi 摄像头 | 通过 Home Assistant `/api/camera_proxy/...` 获取图像 |
| `plughw:2,0` | USB 摄像头内置麦克风，支持 16kHz 立体声采集 |
| `card 1` (`.asoundrc`) | USB 扬声器，默认音频输出 |

## 文件结构

```
pepper-monitor/
├── README.md
├── pi/
│   ├── scripts/
│   │   ├── camera_server.py      # HTTP :8888，摄像头图像缓存服务
│   │   └── monitor_server.py     # WebSocket :8889，PCM 音频流
│   ├── systemd/
│   │   ├── rainyun-tunnel.service    # SSH 反向隧道（-R 8082 -R 8083）
│   │   ├── pepper-camera-pi.service  # 启动 camera_server.py
│   │   ├── pepper-monitor-pi.service # 启动 monitor_server.py
│   │   └── openclaw-gateway.service  # OpenClaw AI 网关
│   └── asoundrc                  # ALSA 默认音频配置
└── remote/
    ├── server_async_simple_fix.py    # 主 HTTPS 服务 :8443
    ├── ws_audio_proxy_fixed.py       # 音频 WebSocket 代理 :8445
    ├── templates/
    │   ├── index.html            # 前端页面（摄像头+音频+对讲+全屏）
    │   └── login.html            # 登录页
    └── systemd/
        ├── pepper-monitor.service    # 主服务
        └── ws-audio-proxy.service    # 音频代理服务
```
