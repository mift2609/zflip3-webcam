#!/bin/sh
# Configure CAMSS media pipeline for the Z Flip3 camera.
# Usage: setup-camera.sh [front|rear]
set -eu

SIDE=${1:-front}
case "$SIDE" in
	front)
		PHY=3; CSID=0; SENSOR="imx374 14-001a" ;;
	rear)
		PHY=2; CSID=1; SENSOR="imx258 15-001a" ;;
	*)
		echo "usage: $0 [front|rear]" >&2; exit 1 ;;
esac

DEVICE=/dev/media0
VIDEO=/dev/video1
W=1824
H=1368

media-ctl -d "$DEVICE" -l "\"msm_csiphy$PHY\":1->\"msm_csid$CSID\":0[1]"
media-ctl -d "$DEVICE" -l "\"msm_csid$CSID\":1->\"msm_vfe0_rdi0\":0[1]"
media-ctl -d "$DEVICE" --set-v4l2 "\"$SENSOR\":0[fmt:SGRBG10_1X10/${W}x${H}]"
media-ctl -d "$DEVICE" --set-v4l2 "\"msm_csiphy$PHY\":0[fmt:SGRBG10_1X10/${W}x${H}]"
media-ctl -d "$DEVICE" --set-v4l2 "\"msm_csiphy$PHY\":1[fmt:SGRBG10_1X10/${W}x${H}]"
media-ctl -d "$DEVICE" --set-v4l2 "\"msm_csid$CSID\":0[fmt:SGRBG10_1X10/${W}x${H}]"
media-ctl -d "$DEVICE" --set-v4l2 "\"msm_csid$CSID\":1[fmt:SGRBG10_1X10/${W}x${H}]"
v4l2-ctl -d "$VIDEO" --set-fmt-video=width=$W,height=$H,pixelformat=pgAA

echo "camera ready: $SIDE $SENSOR -> $VIDEO ${W}x${H}"
