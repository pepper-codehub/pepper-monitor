#!/usr/bin/env python3
"""
摄像头服务器 - 带后台缓存，消除 HA 响应延迟导致的离线问题
"""
import http.server
import socketserver
import urllib.request
import json
import time
import threading
import subprocess

PORT = 8888
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI3M2IwZjA1Y2EwYzA0ZmU1YjEyODBhYTU5MTE3NzQ1ZSIsImlhdCI6MTc3MjEwOTMwMiwiZXhwIjoyMDg3NDY5MzAyfQ.D4iYuqtGd2elNkJ5PIbSp2Dss0wcIhp-i_EpTLwVXec"
HA_URL = "http://192.168.5.10:8123"
CAMERA_ENTITY = "camera.192_168_5_10"
FETCH_INTERVAL = 2.0
HA_TIMEOUT = 8.0

# ── 全局缓存 ──────────────────────────────────────────────────────────────
_cache_lock  = threading.Lock()
_cached_img  = None
_cache_ts    = 0.0
_cache_fails = 0

def _fetch_from_ha():
    url = "{}/api/camera_proxy/{}".format(HA_URL, CAMERA_ENTITY)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + HA_TOKEN,
        "Accept": "image/jpeg",
    })
    return urllib.request.urlopen(req, timeout=HA_TIMEOUT).read()

def _background_fetcher():
    global _cached_img, _cache_ts, _cache_fails
    print("[CACHE] 后台拉取线程启动")
    while True:
        try:
            data = _fetch_from_ha()
            with _cache_lock:
                _cached_img  = data
                _cache_ts    = time.time()
                _cache_fails = 0
        except Exception as e:
            with _cache_lock:
                _cache_fails += 1
            if _cache_fails <= 3 or _cache_fails % 10 == 0:
                print("[CACHE] HA 拉取失败 (#{}): {}".format(_cache_fails, e))
        time.sleep(FETCH_INTERVAL)


class CameraHandler(http.server.BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/api/play_audio":
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            tmp = "/tmp/intercom.webm"
            with open(tmp, "wb") as f:
                f.write(data)
            print("[CAMERA] 收到语音对讲，开始播放...")
            subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp])
            self._json(200, b'{"ok": true}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/camera.jpg":
            self._serve_camera()
        elif p == "/health":
            self._serve_health()
        elif p == "/":
            self._serve_index()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_camera(self):
        global _cached_img, _cache_ts
        # 先取缓存
        with _cache_lock:
            data = _cached_img
            ts   = _cache_ts

        if data is None:
            # 缓存尚未预热，同步拉一次
            try:
                data = _fetch_from_ha()
                with _cache_lock:
                    _cached_img = data
                    _cache_ts   = time.time()
                ts = _cache_ts
            except Exception as e:
                print("[CAMERA] 同步拉取失败: {}".format(e))
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"camera unavailable")
                return

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print("[CAMERA] 缓存图片: {} 字节  age={:.2f}s".format(len(data), time.time() - ts))

    def _serve_health(self):
        with _cache_lock:
            age  = round(time.time() - _cache_ts, 1) if _cache_ts else None
            ok   = _cached_img is not None
            size = len(_cached_img) if _cached_img else 0
        body = json.dumps({
            "status": "ok" if ok else "no_cache",
            "cache_age_sec": age,
            "cache_size": size,
            "consecutive_fails": _cache_fails,
        }).encode()
        self._json(200, body)

    def _serve_index(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Pepper Camera</h1><img src=/camera.jpg width=640>")

    def _json(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main():
    global _cached_img, _cache_ts
    print("Pepper Camera Server  port={}".format(PORT))
    threading.Thread(target=_background_fetcher, daemon=True).start()
    time.sleep(1)  # 预热 1 秒
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), CameraHandler) as httpd:
        print("[HTTP] 监听 0.0.0.0:{}".format(PORT))
        httpd.serve_forever()

if __name__ == "__main__":
    main()
