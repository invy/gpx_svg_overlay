#!/bin/bash
#
# This script is part of GXSM2. gxsm.sf.net and is copyrighted under GPL.
#

DATAFILE=$1
XLABEL='time [s]'

set -i CX
# time [s]: 1
# distance [m]: 4
CX=1

#P:10, BPM:11, ele:7, lap:3, m/s:8, rpm:9
columns=' -bxy $CX:10 -bxy $CX:11 -bxy $CX:3 -bxy $CX:7'

xmgrace  -graph 0 -pexec "title \"$TITLE\""  \
-pexec "xaxis label \"$XLABEL \[$XUNIT\] \"" -pexec "yaxis label \"$YLABEL \[$YUNIT\]\"" \
-block $DATAFILE $columns
