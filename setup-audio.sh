#!/bin/sh
# Enable Z Flip3 speaker for the network audio sink.
set -eu
amixer -c 0 sset 'Speaker Amp Gain ZC' on >/dev/null
amixer -c 0 sset 'Speaker Analog PCM' 14 >/dev/null
echo "speaker ready: amp on, PCM 70%"
