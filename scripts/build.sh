#!/bin/sh

OSM=$1
PROFILE=$2
osrm-extract "/${OSM}" -p "/${PROFILE}" && \
osrm-contract "/`echo ${OSM} | sed -e "s/\.osm\.pbf$/.osrm/g"`"
