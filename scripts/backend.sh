#!/bin/sh

OSM=$1
THREADS=$2
osrm-routed "/`echo ${OSM} | sed -e "s/\.osm\.pbf$/.osrm/g"`" -t $THREADS --max-table-size=100000
