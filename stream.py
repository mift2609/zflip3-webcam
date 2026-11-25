#!/usr/bin/env python3
"""MJPEG webcam streamer for Z Flip3 OpenWrt (socket-only, no http.server).

Capture: v4l2-ctl -> unpack10 (10-bit packed to gray8) -> ffmpeg -> MJPEG.
Serve: http://<device>:8082/stream (multipart/x-mixed-replace).
"""
import socket
import subprocess
import sys
import threading
import time

W, H = 1824, 1368
PORT = 8082
VIDEO = "/dev/video1"
UNPACK = "/usr/bin/unpack10"

CMD = (
    "v4l2-ctl -d {v} --stream-mmap --stream-count=100000 --stream-to=- | "
    "{u} 1824 1368 2288 | ffmpeg -hide_banner -loglevel error -f rawvideo -pix_fmt gray "
    "-s {w}x{h} -framerate 10 -i - -c:v mjpeg -q:v 5 -f mjpeg -"
).format(v=VIDEO, u=UNPACK, w=W, h=H)

proc = None
OUT = None
buf = bytearray()
lock = threading.Lock()


def start_pipeline():
    global proc, OUT, buf
    if proc is not None:
        proc.terminate()
    proc = subprocess.Popen(
        ["/bin/sh", "-c", CMD],
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
