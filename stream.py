#!/usr/bin/env python3
"""MJPEG webcam streamer for Z Flip3 OpenWrt (socket-only, no http.server).

Capture: v4l2-ctl -> unpack10 (10-bit Bayer -> RGB24 demosaic) -> ffmpeg -> MJPEG.
Serve: http://<device>:8082/stream (multipart/x-mixed-replace).
Mode comes from /etc/zflip3-cam.mode (written by setup-camera.sh), default rear.
"""
import socket
import subprocess
import sys
import threading
import time

PORT = 8082
UNPACK = "/usr/bin/unpack10"
SETUP = "/usr/bin/setup-camera.sh"
MODE_FILE = "/etc/zflip3-cam.mode"
FRAME_DUMP = "/tmp/flip3-cam.rgb"

MODES = {
    "rear":      dict(dev="/dev/video4", w=2104, h=1560, bpl=2640, pix="pBAA", pat="bggr"),
    "rear_full": dict(dev="/dev/video4", w=4208, h=3120, bpl=5264, pix="pBAA", pat="bggr"),
    "front":     dict(dev="/dev/video1", w=1824, h=1368, bpl=2288, pix="pgAA", pat="grbg"),
}


def load_mode():
    try:
        with open(MODE_FILE) as f:
            name = f.read().strip()
    except OSError:
        name = "rear"
    return name if name in MODES else "rear"


MODE = load_mode()
M = MODES[MODE]
W, H, VIDEO = M["w"], M["h"], M["dev"]
OW, OH = int(M["w"]) // 2, int(M["h"]) // 2   # unpack10 emits half-res RGB (2x2 block debayer)

CMD = (
    "v4l2-ctl -d {v} --set-fmt-video=width={w},height={h},pixelformat={p} >/dev/null 2>&1; "
    "v4l2-ctl -d {v} --stream-mmap --stream-count=100000 --stream-to=- | "
    "{u} {w} {h} {b} {d} {pat} | "
    "ffmpeg -hide_banner -loglevel error -f rawvideo -pix_fmt rgb24 "
    "-s {ow}x{oh} -framerate 10 -i - -c:v mjpeg -q:v 5 -f mjpeg -"
)

proc = None
OUT = None
buf = bytearray()
lock = threading.Lock()


def start_pipeline():
    global proc, OUT, buf
    if proc is not None:
        proc.terminate()
        proc.wait()
    subprocess.call([SETUP, MODE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = CMD.format(v=VIDEO, u=UNPACK, w=W, h=H, b=M["bpl"], p=M["pix"], pat=M["pat"],
                     d=FRAME_DUMP, ow=OW, oh=OH)
    proc = subprocess.Popen(
        ["/bin/sh", "-c", cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    OUT = proc.stdout
    buf.clear()


start_pipeline()


def read_frame():
    global buf
    with lock:
        while True:
            i = buf.find(b"\xff\xd8")
            if i >= 0:
                j = buf.find(b"\xff\xd9", i + 2)
                if j >= 0:
                    frame = bytes(buf[i:j + 2])
                    del buf[:j + 2]
                    return frame
            chunk = OUT.read(8192) if OUT else b""
            if not chunk:
                start_pipeline()
                time.sleep(1)
                continue
            buf.extend(chunk)


def reply(conn, ctype, body, extra=b""):
    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: " + ctype + b"\r\n" +
                 b"Content-Length: " + str(len(body)).encode() + b"\r\n" +
                 extra + b"Connection: close\r\n\r\n" + body)


def handle_audio(conn, length, first=b""):
    if length <= 0 or length > 10 * 1024 * 1024:
        conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        return
    player = subprocess.Popen(
        ["aplay", "-q", "-f", "S16_LE", "-r", "44100", "-c", "1"],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    STDIN = player.stdin
    assert STDIN is not None
    remaining = length
    chunk = first
    try:
        while remaining > 0:
            if not chunk:
                chunk = conn.recv(min(65536, remaining))
                if not chunk:
                    break
            n = min(len(chunk), remaining)
            STDIN.write(chunk[:n])
            remaining -= n
            chunk = chunk[n:]
        STDIN.close()
        player.wait(timeout=10)
        reply(conn, b"application/json", b'{"ok":true,"service":"zflip3-speaker"}')
    except Exception:
        try:
            player.kill()
        except Exception:
            pass
        conn.sendall(b"HTTP/1.1 500 Error\r\nContent-Length: 0\r\n\r\n")


def handle(conn):
    try:
        req = conn.recv(4096)
        parts = req.split(b" ")
        method = parts[0] if parts else b"GET"
        path = parts[1] if len(parts) > 1 else b"/"
        length = 0
        for line in req.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                try:
                    length = int(line.split(b":", 1)[1].strip())
                except ValueError:
                    length = 0
        hend = req.find(b"\r\n\r\n")
        first = req[hend + 4:] if hend >= 0 else b""
        if method == b"POST" and path == b"/audio":
            handle_audio(conn, length, first)
            return
        if path == b"/health":
            reply(conn, b"application/json", b'{"ok":true,"service":"zflip3-webcam"}')
        elif path == b"/stream":
            conn.sendall(b"HTTP/1.1 200 OK\r\n"
                         b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
                         b"Cache-Control: no-store\r\nConnection: close\r\n\r\n")
            while True:
                frame = read_frame()
                conn.sendall(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                             str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
        elif path in (b"/", b"/index.html"):
            body = (b"<html><body><img src='/stream' style='width:100%'>"
                    b"</body></html>")
            reply(conn, b"text/html", body)
        else:
            conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print("webcam stream on port %d" % PORT, flush=True)
    try:
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        if proc is not None:
            proc.terminate()
        srv.close()


if __name__ == "__main__":
    sys.exit(main())
