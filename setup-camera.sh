#!/bin/sh
# Configure the CAMSS media pipeline for the Z Flip3 cameras.
# Usage: setup-camera.sh [rear|rear_full|front]
#
# Hard-won details (b2q, mainline camss):
#   * rear main imx258 must feed msm_csid1 -> msm_vfe1_rdi0 (/dev/video4).
#     Routing it to msm_vfe0_rdi0 fails STREAMON with
#     "Failed to start media pipeline: -32".
#   * front imx374 uses msm_csiphy3 -> msm_csid0 -> msm_vfe0_rdi0 (/dev/video1).
#   * Bayer codes: rear = SBGGR10_1X10 (+ pixelformat pBAA),
#     front = SGRBG10_1X10 (+ pixelformat pgAA).
set -eu

MODE=${1:-rear}
case "$MODE" in
rear)      PHY=2; CSID=1; VFE=1; SENSOR="imx258 15-001a"; CODE=SBGGR10_1X10; PIX=pBAA; W=2104; H=1560; VID=/dev/video4 ;;
rear_full) PHY=2; CSID=1; VFE=1; SENSOR="imx258 15-001a"; CODE=SBGGR10_1X10; PIX=pBAA; W=4208; H=3120; VID=/dev/video4 ;;
front)     PHY=3; CSID=0; VFE=0; SENSOR="imx374 14-001a"; CODE=SGRBG10_1X10; PIX=pgAA; W=1824; H=1368; VID=/dev/video1 ;;
*) echo "usage: $0 [rear|rear_full|front]" >&2; exit 1 ;;
esac

MEDIA=/dev/media0
SENSOR_DEV=$(media-ctl -d "$MEDIA" -e "$SENSOR" 2>/dev/null || true)

# Rear uses VFE1, front uses VFE0: drop the other path's output link first.
for L in 0 1; do
	[ "$L" = "$VFE" ] && continue
	media-ctl -d "$MEDIA" -l "\"msm_csid$L\":1->\"msm_vfe${L}_rdi0\":0[0]" 2>/dev/null || true
done

media-ctl -d "$MEDIA" -l "\"msm_csiphy$PHY\":1->\"msm_csid$CSID\":0[1]"
media-ctl -d "$MEDIA" -l "\"msm_csid$CSID\":1->\"msm_vfe${VFE}_rdi0\":0[1]"

for E in "$SENSOR:0" "msm_csiphy$PHY:0" "msm_csiphy$PHY:1" "msm_csid$CSID:0" "msm_csid$CSID:1" "msm_vfe${VFE}_rdi0:0"; do
	media-ctl -d "$MEDIA" --set-v4l2 "\"${E%:*}\":${E##*:}[fmt:$CODE/${W}x${H}]"
done

v4l2-ctl -d "$VID" --set-fmt-video=width=$W,height=$H,pixelformat=$PIX

# The imx258 in this kernel powers up at ~1/15 of the brightness a normal scene
# needs (raw 10-bit mean ~70/1023), so the sensor has to be driven near its
# limits. Values are overridable from /etc/zflip3-cam.gain (EXPOSURE=, AG=, DG=).
EXPOSURE=${EXPOSURE:-1582}
AG=${AG:-480}
DG=${DG:-1024}
[ -f /etc/zflip3-cam.gain ] && . /etc/zflip3-cam.gain
case "$MODE" in
rear|rear_full)
	# Leave the sensor's default mirror/flip alone: which way is "correct"
	# depends on how the phone is mounted.
	v4l2-ctl -d "$SENSOR_DEV" -c exposure=$EXPOSURE,analogue_gain=$AG,digital_gain=$DG
	;;
esac

echo "$MODE" > /etc/zflip3-cam.mode
echo "camera ready: $MODE $SENSOR -> $VID ${W}x${H} $PIX exp=$EXPOSURE ag=$AG dg=$DG"
