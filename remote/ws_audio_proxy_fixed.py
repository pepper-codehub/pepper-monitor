#!/usr/bin/env python3
"""
WebSocket 音频代理 - 直接透传版本
不做任何帧解析，直接双向透传
"""
import socket
import threading
import struct
import hashlib
import base64
import os

WS_PORT = 8445
PI_HOST = "127.0.0.1"
PI_PORT = 8083
PI_WS_PATH = "/listen"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

def encode_ws_frame(payload, opcode=0x02):
    n = len(payload)
    if n < 126:
        hdr = bytes([0x82, n])
    elif n < 65536:
        hdr = bytes([0x82, 126]) + struct.pack(">H", n)
    else:
        hdr = bytes([0x82, 127]) + struct.pack(">Q", n)
    return hdr + payload

def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        d = sock.recv(n - len(data))
        if not d:
            return b''
        data += d
    return data

def pipe(src, dst, name):
    """直接透传，不做任何解析"""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception as e:
        print(f"[{name}] 断开: {e}")
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

def handle_client(client_sock, addr):
    print(f"[代理] 浏览器连接: {addr}")
    pi_sock = None
    
    try:
        # 1. 读取浏览器 WebSocket 握手请求
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = client_sock.recv(1)
            if not chunk:
                return
            request += chunk
        
        lines = request.decode(errors="ignore").split("\r\n")
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        
        key = headers.get("sec-websocket-key", "")
        if not key:
            client_sock.close()
            return
        
        # 2. 发送 WebSocket 握手响应给浏览器
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "\r\n"
        ).encode()
        client_sock.sendall(response)
        
        # 3. 连接 Pi 的 WebSocket
        pi_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        pi_sock.settimeout(10)
        pi_sock.connect((PI_HOST, PI_PORT))
        pi_sock.settimeout(3600)
        
        pi_key = base64.b64encode(os.urandom(16)).decode()
        pi_ws_req = (
            f"GET {PI_WS_PATH} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{PI_PORT}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {pi_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        pi_sock.sendall(pi_ws_req.encode())
        
        # 读取 Pi 的握手响应
        resp = b""
        while b"\r\n\r\n" not in resp:
            d = pi_sock.recv(1)
            if not d:
                raise Exception("Pi WebSocket 握手失败")
            resp += d
        
        if b"101" not in resp.split(b"\r\n")[0]:
            raise Exception(f"Pi WS 握手非 101: {resp[:100]}")
        
        print(f"[代理] Pi 已连接，开始透传音频数据")
        
        # 4. 双向直接透传，不做任何帧解析！
        t1 = threading.Thread(target=pipe, args=(pi_sock, client_sock, "Pi->浏览器"), daemon=True)
        t2 = threading.Thread(target=pipe, args=(client_sock, pi_sock, "浏览器->Pi"), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
    except Exception as e:
        print(f"[代理] 错误: {e}")
    finally:
        try: client_sock.close()
        except: pass
        try: pi_sock.close()
        except: pass
        print(f"[代理] 会话关闭: {addr}")

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", WS_PORT))
    server.listen(10)
    print(f"[代理] 音频代理监听 0.0.0.0:{WS_PORT}")
    print(f"[代理] 透传到 Pi {PI_HOST}:{PI_PORT}")
    
    while True:
        try:
            client_sock, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
            t.start()
        except KeyboardInterrupt:
            print("\n[代理] 关闭")
            break

if __name__ == "__main__":
    import os
    main()
