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
import queue
import subprocess
import os
import signal
import socket

PORT = 8888
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI3M2IwZjA1Y2EwYzA0ZmU1YjEyODBhYTU5MTE3NzQ1ZSIsImlhdCI6MTc3MjEwOTMwMiwiZXhwIjoyMDg3NDY5MzAyfQ.D4iYuqtGd2elNkJ5PIbSp2Dss0wcIhp-i_EpTLwVXec"
HA_URL = "http://192.168.5.10:8123"
CAMERA_ENTITY = "camera.192_168_5_10"
FETCH_INTERVAL = 2.0
HA_TIMEOUT = 8.0
GO2RTC_FRAME_URL = "http://127.0.0.1:1984/api/frame.jpeg?src=my_cam"
STREAM_FPS = 5.0
STREAM_BOUNDARY = "pepperframe"

# ── 全局缓存 ──────────────────────────────────────────────────────────────
_cache_lock  = threading.Lock()
stream_lock = threading.Lock()
INTERCOM_MAX_BYTES = 2 * 1024 * 1024
INTERCOM_VOLUME = "60"
intercom_lock = threading.Lock()
intercom_proc = None


class MjpegHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = set()
        self.process = None
        self.thread = None

    def _cmd(self):
        return [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel", "warning",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", "640x360",
            "-framerate", "15",
            "-i", "/dev/video0",
            "-an",
            "-vf", "fps=5",
            "-q:v", "3",
            "-f", "mjpeg",
            "pipe:1",
        ]

    def add_client(self):
        q = queue.Queue(maxsize=2)
        with self.lock:
            self.clients.add(q)
            if self.process is None or self.process.poll() is not None:
                self._start_locked()
        return q

    def remove_client(self, q):
        with self.lock:
            self.clients.discard(q)
            if not self.clients:
                self._stop_locked()

    def _start_locked(self):
        self.process = subprocess.Popen(
            self._cmd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            preexec_fn=os.setsid,
        )
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()
        print("[STREAM] shared MJPEG ffmpeg started pid={}".format(self.process.pid), flush=True)

    def _stop_locked(self):
        proc = self.process
        self.process = None
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=2)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        print("[STREAM] shared MJPEG ffmpeg stopped", flush=True)

    def _broadcast_frame(self, jpg):
        part = (
            b"--ffmpeg\r\n"
            b"Content-Type: image/jpeg\r\n"
            + b"Content-Length: " + str(len(jpg)).encode("ascii") + b"\r\n\r\n"
            + jpg + b"\r\n"
        )
        with self.lock:
            clients = list(self.clients)
        for q in clients:
            while q.full():
                try:
                    q.get_nowait()
                except Exception:
                    break
            try:
                q.put_nowait(part)
            except queue.Full:
                pass

    def _notify_end(self):
        with self.lock:
            clients = list(self.clients)
        for q in clients:
            try:
                q.put_nowait(None)
            except queue.Full:
                pass

    def _pump(self):
        proc = self.process
        buf = bytearray()
        try:
            while proc and proc.poll() is None:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                while True:
                    soi = buf.find(b"\xff\xd8")
                    if soi < 0:
                        if len(buf) > 65536:
                            del buf[:-2]
                        break
                    eoi = buf.find(b"\xff\xd9", soi + 2)
                    if eoi < 0:
                        if soi > 0:
                            del buf[:soi]
                        break
                    jpg = bytes(buf[soi:eoi + 2])
                    del buf[:eoi + 2]
                    self._broadcast_frame(jpg)
        finally:
            self._notify_end()
            with self.lock:
                if self.process is proc:
                    self.process = None
            print("[STREAM] shared MJPEG pump exited", flush=True)


mjpeg_hub = MjpegHub()
_cached_img  = None
_cache_ts    = 0.0
_cache_fails = 0

def _stop_intercom_process(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _fetch_frame():
    try:
        return urllib.request.urlopen(GO2RTC_FRAME_URL, timeout=4.0).read()
    except Exception as e:
        print("[STREAM] go2rtc frame failed: {}".format(e))
        return _fetch_from_ha()


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
            global intercom_proc
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > INTERCOM_MAX_BYTES:
                print("[CAMERA] reject intercom audio length={}".format(length), flush=True)
                self._json(413, b'{"ok": false, "error": "audio too large"}')
                return
            data = self.rfile.read(length)
            tmp = "/tmp/intercom.webm"
            with open(tmp, "wb") as f:
                f.write(data)
            print("[CAMERA] 收到语音对讲，开始播放 length={}".format(length), flush=True)
            with intercom_lock:
                _stop_intercom_process(intercom_proc)
                intercom_proc = subprocess.Popen([
                    "ffplay", "-nodisp", "-vn", "-autoexit", "-loglevel", "warning",
                    "-volume", INTERCOM_VOLUME, tmp
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._json(200, b'{"ok": true}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/camera.jpg":
            self._serve_camera()
        elif p == "/camera.mjpg":
            self._serve_mjpeg()
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
                data = _fetch_frame()
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

    def _serve_mjpeg(self):
        q = mjpeg_hub.add_client()
        print("[STREAM] shared MJPEG client connected: {}".format(self.client_address))
        try:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=ffmpeg")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.connection.settimeout(5.0)

            while True:
                try:
                    chunk = q.get(timeout=10)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout, OSError):
            pass
        except Exception as e:
            print("[STREAM] shared MJPEG client error: {}".format(e))
        finally:
            mjpeg_hub.remove_client(q)
            print("[STREAM] shared MJPEG client disconnected: {}".format(self.client_address))

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
    # Camera frames are fetched on demand by /camera.jpg and /camera.mjpg.
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), CameraHandler) as httpd:
        print("[HTTP] 监听 0.0.0.0:{}".format(PORT))
        httpd.serve_forever()

if __name__ == "__main__":
    main()