# ${SOURCE:-osm/source.osm.pbf} ${CROP:-osm/area.geojson} ${TARGET:-osm/data.osm.pbf}

osmium extract $1 -p $2 -o osm/tmp.osm.pbf --overwrite
osmium tags-filter osm/tmp.osm.pbf wr/highway -o $3 --overwrite
