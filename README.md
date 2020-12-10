# Walking distance of public transit stops

This project calculates minimum walking distance (by streets/footways/paths) from houses to public transit stops.


## Prerequisites

The project has Docker containers to keep packages in them, but you can run the shell and Python scripts on their own in Linux. If you want to run it in containers, install

* [Docker](https://docs.docker.com/engine/install/)
* [Docker-Compose](https://docs.docker.com/compose/install/).

Also, install Git for your platform.

## Preparation

1. Clone the repository and enter the folder:

    git clone https://github.com/culebron/stops_access.git
    cd stops_access

2. Download an OSM extract for your country (from GeoFabrik.de or other providers).

3. Rename/copy the `.osm.pbf` file as `osm/source.osm.pbf`.

## Creating a router

1. Create an area file, save it to osm/area.geojson
2. Run crop container:

    docker-compose up crop

By default the script `scripts/crop.sh` will take `osm/source.osm.pbf` file, crop it and filter to keep only objects with `highway` tag, and save to `osm/data.osm.pbf`.

3. Build routing graph:

    docker-compose up build

(Both containers exit when their scripts finish.)

## Running a router

Launch the routing backend with a frontend by a command:

    docker-compose up backend frontend

This will run both containers and block the shell. You can exit them with Ctrl+C.

Open `http://localhost:9966` to see the frontend and test if routing is working.

*Troubleshooting:*

1. if routes aren't built in your area, check where OSRM projects the points (you may have cropped it in a wrong area)
2. check if frontend points at localhost and appropriate port. Open developer tools in the browser and in Network tab, see where XHR requests go.
3. check if the backend router is up and running (see if `osrm-routed` process is running in `htop`, or see running containers `docker ps`)
4. enable requests logging in router (in `docker-compose.yml` search for `NO_LOGS`) and see backend output

*Running backend in background*

    docker-compose up -d backend [frontend]

## Running the distances script

Put houses and stops files into `tmp` folder (it's mapped to `/tmp` inside container).

Start `calc` container and enter its bash shell:

    docker-compose up -d calc
    docker-compose exec calc bash

In the container:

    cd /tmp

Run the script:

    python3 /scripts/houses_to_stops.py houses.gpkg stops.gpkg result.gpkg

Or change max distance (in metres):

    python3 /scripts/houses_to_stops.py houses.gpkg stops.gpkg result.gpkg -m 1000
