# ${SOURCE:-osm/source.osm.pbf} ${CROP:-osm/area.geojson} ${TARGET:-osm/data.osm.pbf}

osmium extract $1 -p $2 -o $3
