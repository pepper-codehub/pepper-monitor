import asyncio
import ssl
import os
import time
import json
import urllib.parse
import hashlib
import base64
import sys
import traceback

PORT = 8443
WS_PROXY_HOST = '127.0.0.1'
WS_PROXY_PORT = 8445
PASSWORD = '8848'
SSL_CERT = 'cert.pem'
SSL_KEY = 'key.pem'
HTML_DIR = 'templates'

def load_sessions():
    try:
        with open('sessions.json', 'r') as f: return json.load(f)
    except: return {}

def save_sessions(s):
    with open('sessions.json', 'w') as f: json.dump(s, f)

def new_token(): return base64.b64encode(os.urandom(24)).decode()

def get_session_token(cookie_str):
    for c in cookie_str.split(';'):
        if 'session=' in c: return c.split('=')[1].strip()
    return None

def check_session(cookie_str):
    if not cookie_str: return False
    tok = get_session_token(cookie_str)
    s = load_sessions()
    if tok in s:
        s[tok]['time'] = time.time()
        save_sessions(s)
        return True
    return False

def read_index():
    path = os.path.join(HTML_DIR, 'index.html')
    try:
        with open(path, 'rb') as f: return f.read()
    except: return b'<h1>index.html not found</h1>'

LOGIN_HTML = """<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>🌶️ 胡椒监控系统</title>
<style>
body{margin:0;padding:0;height:100vh;display:flex;align-items:center;justify-content:center;font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(135deg,#1e1e2f,#2a2a40);background-size:cover;color:#fff;}
.login-container{background:rgba(255,255,255,0.05);backdrop-filter:blur(15px);-webkit-backdrop-filter:blur(15px);border-radius:20px;border:1px solid rgba(255,255,255,0.1);padding:40px 30px;width:300px;text-align:center;box-shadow:0 15px 35px rgba(0,0,0,0.3);}
.avatar{width:110px;height:110px;border-radius:50%;object-fit:cover;border:3px solid rgba(255,255,255,0.2);margin-bottom:15px;box-shadow:0 8px 20px rgba(0,0,0,0.4);background:#000;}
h2{margin:0 0 25px;font-weight:600;font-size:22px;letter-spacing:1px;text-shadow:0 2px 4px rgba(0,0,0,0.3);}
input{width:100%;padding:14px 15px;margin-bottom:20px;box-sizing:border-box;border:none;border-radius:12px;background:rgba(0,0,0,0.25);color:#fff;font-size:15px;outline:none;transition:all 0.3s;}
input::placeholder{color:rgba(255,255,255,0.5);}
input:focus{background:rgba(0,0,0,0.4);box-shadow:0 0 0 2px rgba(229,62,62,0.6);}
button{width:100%;padding:14px;border:none;border-radius:12px;background:linear-gradient(135deg,#e53e3e,#c53030);color:white;font-size:16px;font-weight:bold;cursor:pointer;transition:all 0.3s;box-shadow:0 4px 15px rgba(229,62,62,0.4);}
button:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(229,62,62,0.6);}
button:active{transform:scale(0.98);}
.footer{margin-top:25px;font-size:12px;color:rgba(255,255,255,0.4);}
</style>
</head>
<body>
<div class="login-container">
    <img src="/avatar.jpg" alt="Pepper" class="avatar">
    <h2>胡椒监控系统</h2>
    <form method="POST" action="/login">
        <input type="password" name="password" placeholder="请输入访问密码..." required>
        <button type="submit">进 入</button>
    </form>
    <div class="footer">Powered by OpenClaw</div>
</div>
</body></html>""".encode('utf-8')

async def send_response(writer, status, headers, body=b''):
    status_text = {200:'OK',302:'Found',400:'Bad Request',401:'Unauthorized',404:'Not Found',502:'Bad Gateway'}.get(status,'Unknown')
    res = f'HTTP/1.1 {status} {status_text}\r\n'
    for k,v in headers: res += f'{k}: {v}\r\n'
    res += f'Content-Length: {len(body)}\r\n\r\n'
    writer.write(res.encode() + body)
    await writer.drain()

async def handle_ws(reader, writer, req_headers, raw_req):
    try:
        pr, pw = await asyncio.wait_for(asyncio.open_connection(WS_PROXY_HOST, WS_PROXY_PORT), timeout=5)
    except Exception as e:
        writer.close(); return

    pw.write(raw_req)
    await pw.drain()

    async def pipe(src, dst):
        try:
            while True:
                d = await asyncio.wait_for(src.read(65536), timeout=3600)
                if not d: break
                dst.write(d)
                await dst.drain()
        except: pass
        finally:
            try: dst.close()
            except: pass

    await asyncio.gather(pipe(reader, pw), pipe(pr, writer), return_exceptions=True)

async def handle_client(reader, writer):
    try:
        raw = b''
        while b'\r\n\r\n' not in raw:
            chunk = await asyncio.wait_for(reader.read(8192), timeout=10)
            if not chunk: return
            raw += chunk
        hdr_part, body_start = raw.split(b'\r\n\r\n', 1)
        lines = hdr_part.decode(errors='replace').split('\r\n')
        req_line = lines[0]
        method, path_qs, *_ = req_line.split(' ')
        path = path_qs.split('?')[0]

        headers = {}
        for l in lines[1:]:
            if ':' in l:
                k,v = l.split(':',1)
                headers[k.strip().lower()] = v.strip()

        cookie_hdr = headers.get('cookie','')
        authed = check_session(cookie_hdr)

        if headers.get('upgrade','').lower() == 'websocket':
            if not authed:
                await send_response(writer, 401, [('Content-Type','text/plain')], b'Unauthorized')
                return
            await handle_ws(reader, writer, headers, raw)
            return

        if method == 'GET':
            if path in ('/', '/index', '/index.html'):
                if not authed:
                    await send_response(writer, 302, [('Location','/login'),('Content-Type','text/html')], b'')
                    return
                body = read_index()
                await send_response(writer, 200, [('Content-Type','text/html; charset=utf-8')], body)

            elif path == '/login':
                await send_response(writer, 200, [('Content-Type','text/html; charset=utf-8')], LOGIN_HTML)

            elif path == '/avatar.jpg':
                try:
                    with open('/opt/webcam-dashboard/avatar.jpg', 'rb') as f: img = f.read()
                    await send_response(writer, 200, [('Content-Type','image/jpeg'),('Cache-Control','max-age=86400')], img)
                except:
                    await send_response(writer, 404, [], b'')

            elif path == '/camera.jpg':
                try:
                    cr, cw = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 8082), timeout=5)
                    cw.write(b'GET /camera.jpg HTTP/1.0\r\nHost: localhost\r\n\r\n')
                    await cw.drain()
                    resp = b''
                    try:
                        while True:
                            d = await asyncio.wait_for(cr.read(65536), timeout=3.0)
                            if not d: break
                            resp += d
                    except asyncio.TimeoutError:
                        pass
                    cw.close()
                    
                    if b'\r\n\r\n' in resp:
                        _, img = resp.split(b'\r\n\r\n', 1)
                        await send_response(writer, 200, [('Content-Type','image/jpeg'),('Cache-Control','no-cache')], img)
                    else:
                        await send_response(writer, 502, [], b'')
                except Exception as e:
                    await send_response(writer, 502, [], b'')

            elif path == '/camera.mjpg':
                try:
                    cr, cw = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 8082), timeout=5)
                    cw.write(b'GET /camera.mjpg HTTP/1.0\r\nHost: localhost\r\n\r\n')
                    await cw.drain()
                    header_data = b''
                    while b'\r\n\r\n' not in header_data:
                        d = await asyncio.wait_for(cr.read(4096), timeout=5)
                        if not d: break
                        header_data += d
                    if b'\r\n\r\n' not in header_data:
                        cw.close()
                        await send_response(writer, 502, [], b'')
                        return
                    headers_part, body_start = header_data.split(b'\r\n\r\n', 1)
                    header_lines = headers_part.decode().split('\r\n')
                    writer.write((header_lines[0] + '\r\n').encode())
                    for line in header_lines[1:]:
                        if 'content-length' not in line.lower():
                            writer.write((line + '\r\n').encode())
                    writer.write(b'\r\n')
                    await writer.drain()
                    if body_start:
                        writer.write(body_start)
                        await writer.drain()
                    async def pipe_stream(src, dst):
                        try:
                            while True:
                                d = await asyncio.wait_for(src.read(65536), timeout=3600)
                                if not d: break
                                dst.write(d)
                                await dst.drain()
                        except: pass
                        finally:
                            try: dst.close()
                            except: pass
                    await asyncio.gather(pipe_stream(cr, writer), return_exceptions=True)
                    cw.close()
                except:
                    await send_response(writer, 502, [], b'')

            elif path == '/api/status':
                try:
                    cr, cw = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 8082), timeout=3)
                    cw.write(b'GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n')
                    await cw.drain()
                    resp = b''
                    while True:
                        d = await asyncio.wait_for(cr.read(4096), timeout=3)
                        if not d: break
                        resp += d
                    cw.close()
                    if b'\r\n\r\n' in resp:
                        body = resp.split(b'\r\n\r\n',1)[1]
                        await send_response(writer, 200, [('Content-Type','application/json')], body)
                    else:
                        await send_response(writer, 200, [('Content-Type','application/json')], b'{"status":"online"}')
                except:
                    await send_response(writer, 200, [('Content-Type','application/json')], b'{"status":"offline"}')

            elif path == '/check_auth':
                authed = check_session(cookie_hdr)
                body = json.dumps({'authenticated': authed}).encode()
                await send_response(writer, 200, [('Content-Type','application/json')], body)

            elif path == '/logout':
                tok = get_session_token(cookie_hdr)
                if tok:
                    s = load_sessions(); s.pop(tok, None); save_sessions(s)
                await send_response(writer, 302, [('Location','/login'),('Set-Cookie','session=; Path=/; Max-Age=0')], b'')
            else:
                await send_response(writer, 404, [('Content-Type','text/html')], b'<h1>404</h1>')

        elif method == 'POST':
            content_len = int(headers.get('content-length','0'))
            body_bytes = body_start
            while len(body_bytes) < content_len:
                d = await asyncio.wait_for(reader.read(content_len - len(body_bytes)), timeout=5)
                if not d: break
                body_bytes += d

            if path == '/login':
                params = dict(urllib.parse.parse_qsl(body_bytes.decode(errors='replace')))
                if params.get('password') == PASSWORD:
                    tok = new_token()
                    s = load_sessions(); s[tok] = {'authenticated': True, 'time': time.time()}; save_sessions(s)
                    await send_response(writer, 302, [('Location','/'), ('Set-Cookie', f'session={tok}; Path=/; HttpOnly; SameSite=Lax')], b'')
                else:
                    await send_response(writer, 200, [('Content-Type','text/html')], b'<html><body><h2>Wrong Password</h2><a href="/login">Back</a></body></html>')

            elif path == '/api/play_audio':
                if not authed:
                    await send_response(writer, 401, [], b''); return
                try:
                    cr, cw = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 8082), timeout=5)
                    req = f'POST /api/play_audio HTTP/1.0\r\nHost: localhost\r\nContent-Length: {len(body_bytes)}\r\nContent-Type: {headers.get("content-type","audio/webm")}\r\n\r\n'.encode() + body_bytes
                    cw.write(req); await cw.drain()
                    resp = b''
                    while True:
                        d = await asyncio.wait_for(cr.read(4096), timeout=10)
                        if not d: break
                        resp += d
                    cw.close()
                    body_out = resp.split(b'\r\n\r\n',1)[1] if b'\r\n\r\n' in resp else b'{"ok":true}'
                    await send_response(writer, 200, [('Content-Type','application/json')], body_out)
                except Exception as e:
                    await send_response(writer, 502, [], b'{"ok":false}')
            else:
                await send_response(writer, 404, [], b'')
        else:
            await send_response(writer, 405, [], b'')

    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print(f'[HTTP] Error: {e}')
    finally:
        try: writer.close()
        except: pass

async def main():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(SSL_CERT, SSL_KEY)
    server = await asyncio.start_server(handle_client, '0.0.0.0', PORT, ssl=ctx)
    print(f'[Server] Listening on https://0.0.0.0:{PORT}')
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
