# Z Flip3 webcam helper (experimental)

Safe-path webcam for Z Flip3 OpenWrt **without kernel change**.

- Camera: `/dev/video1` (CAMSS, 1824×1368, 10-bit packed Bayer).
- `unpack10` converts 10-bit packed to 8-bit grey.
- `ffmpeg` encodes MJPEG.
- `stream.py` serves `http://<device>:8082/stream` as multipart MJPEG.

Laptop: open the URL in VLC / browser, or add as IP camera source in OBS and
use OBS Virtual Camera for Zoom/Meet. This is a **network stream**, not a USB
webcam class device.

## Limitations

- Kernel lacks `CONFIG_USB_CONFIGFS_F_UVC` and `CONFIG_USB_CONFIGFS_F_UAC1/2`,
  so true USB webcam/speaker needs a kernel rebuild + boot image flash.
- Output is grayscale (Bayer demosaic not implemented yet).
- eSIM is not covered here; ModemManager sees only the physical SIM slot.

## Build

GitHub Actions builds a static aarch64-musl `unpack10` and uploads artifacts.

## Install on device

```sh
scp -O unpack10 stream.py setup-camera.sh root@192.168.44.1:/usr/bin/
chmod 0755 /usr/bin/unpack10 /usr/bin/stream.py /usr/bin/setup-camera.sh
setup-camera.sh front
/usr/bin/stream.py &
```

Open `http://192.168.44.1:8082/` (USB) or `http://192.168.45.1:8082/` (WiFi).
