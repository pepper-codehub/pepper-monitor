import asyncio
import subprocess

from websockets.asyncio.server import serve

# 配置
PORT = 8889
MIC_DEVICE = "plughw:2,0"
SAMPLE_RATE = 16000
CHUNK_SIZE = 3200  # 16000Hz * 0.1s * 2 bytes = 3200 bytes per 100ms

async def audio_stream(websocket):
    print(f"[音频] 客户端已连接: {websocket.remote_address}")
    # arecord 采集原始 S16_LE PCM
    cmd = ['ffmpeg', '-f', 'alsa', '-i', MIC_DEVICE, '-ar', str(SAMPLE_RATE), '-ac', '1', '-f', 's16le', '-']
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    try:
        while True:
            # 使用 readexactly 确保每一帧大小固定，消除滴滴声
            try:
                data = await proc.stdout.readexactly(CHUNK_SIZE)
            except asyncio.IncompleteReadError as e:
                data = e.partial
                if not data: break
            
            await websocket.send(data)
    except Exception as e:
        print(f"[音频] 传输中断: {e}")
    finally:
        if proc.returncode is None:
            proc.terminate()
        print(f"[音频] 客户端断开: {websocket.remote_address}")

async def main():
    print(f"🌶️ 音频服务启动 (端口 {PORT})...")
    async with serve(
        audio_stream,
        "0.0.0.0",
        PORT,
        reuse_address=True,
        reuse_port=True,
    ):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
