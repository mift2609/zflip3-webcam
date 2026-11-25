#!/usr/bin/env python3
"""MJPEG webcam streamer for Z Flip3 OpenWrt.

Capture: v4l2-ctl -> unpack10 (10-bit packed to gray8) -> ffmpeg -> MJPEG.
Serve: http://<device>:8082/stream (multipart/x-mixed-replace).
"""
import http.server
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

proc = subprocess.Popen(["/bin/sh", "-c", CMD], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
OUT = proc.stdout
assert OUT is not None
buf = bytearray()
lock = threading.Lock()


def read_frame():
    global buf
    while True:
        i = buf.find(b"\xff\xd8")
        if i >= 0:
            j = buf.find(b"\xff\xd9", i + 2)
            if j >= 0:
                frame = bytes(buf[i:j + 2])
                del buf[:j + 2]
                return frame
        chunk = OUT.read(8192)
        if not chunk:
            raise RuntimeError("capture pipeline ended")
        buf.extend(chunk)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (b"<html><body><img src='/stream' style='width:100%'>"
                    b"</body></html>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"service":"zflip3-webcam"}')
            return
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    frame = read_frame()
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n")
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        self.send_error(404)


def main():
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("webcam stream on port %d" % PORT, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
