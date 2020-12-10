FROM ubuntu:20.04

# образ ubuntu:20.04 весит 72.9 MB, что меньше, чем у легковесного slim-buster 113 MB.

ENV TZ=Europe/Moscow
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y && apt-get install osmium-tool python3-pip -y
RUN DEBIAN_FRONTEND=noninteractive apt-get install libspatialindex-dev libgdal-dev -y
RUN pip3 install shapely --no-binary shapely
RUN pip3 install pygeos --no-binary pygeos
RUN pip3 install polyline tqdm argh geopandas requests
