#!/usr/bin/env python3
import datetime
import os
import signal
import subprocess
import time

LOG = "/tmp/pepper-camera-watchdog.log"
CAMERA_PORT = ":8888"


def run(cmd, timeout=5):
    try:
        return subprocess.run(
            cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        ).stdout.strip()
    except Exception as exc:
        return "ERR {}".format(exc)


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[{}] {}\n".format(ts, msg))


def active_camera_clients():
    out = run("ss -Htn state established")
    count = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and CAMERA_PORT in parts[2]:
            count += 1
    return count


def ffmpeg_pids():
    out = run("ps -eo pid=,etimes=,comm=,args=")
    items = []
    for line in out.splitlines():
        fields = line.strip().split(maxsplit=3)
        if len(fields) < 4 or not fields[0].isdigit():
            continue
        pid, age, comm, args = int(fields[0]), int(fields[1]), fields[2], fields[3]
        if comm == "ffmpeg" and "/dev/video0" in args:
            items.append((pid, age))
    return items


def kill_stale_ffmpeg(pids):
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            log("sent SIGTERM to stale ffmpeg pid={}".format(pid))
        except ProcessLookupError:
            pass
        except Exception as exc:
            log("failed SIGTERM pid={} err={}".format(pid, exc))
    time.sleep(2)
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            log("sent SIGKILL to stale ffmpeg pid={}".format(pid))
        except ProcessLookupError:
            pass
        except Exception as exc:
            log("failed SIGKILL pid={} err={}".format(pid, exc))


def main():
    clients = active_camera_clients()
    pid_items = ffmpeg_pids()
    pids = [pid for pid, age in pid_items]
    load = run("cut -d' ' -f1-3 /proc/loadavg")
    temp = run("vcgencmd measure_temp 2>/dev/null || true")
    throttled = run("vcgencmd get_throttled 2>/dev/null || true")

    if clients == 0 and pids:
        log("no clients but ffmpeg alive; pids={} load={} {} {}".format(pids, load, temp, throttled))
        kill_stale_ffmpeg(pids)
    else:
        log("ok clients={} ffmpeg_pids={} load={} {} {}".format(clients, pids, load, temp, throttled))


if __name__ == "__main__":
    main()
