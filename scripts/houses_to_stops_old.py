from contextlib import ExitStack
from polyline import encode as encode_poly
from shapely.geometry import LineString
from time import sleep
from tqdm import tqdm
import argh
import geopandas as gpd
import numpy as np
import os
import pandas as pd
import pyproj
import requests
import urllib


DEBUG = (os.environ.get('DEBUG', 0) == '1')

retries_limit = 10
WGS = CRS4326 = pyproj.CRS.from_epsg(4326)
SIB = pyproj.crs.ProjectedCRS(pyproj.crs.coordinate_operation.AlbersEqualAreaConversion(52, 64, 0, 105, 18500000, 0), name='Albers Siberia')


def read_dataframe(input_path):
	df = gpd.read_file(input_path)
	if df.crs is None:
		df.crs = WGS

	return df.to_crs(SIB)  # albers siberia projection for entire russia


@argh.dispatch_command
def main(houses_file, stops_file, router_url, output_houses, max_dist: float = 500):
	with ExitStack() as stack:
		if DEBUG:
			import ipdb
			stack.enter_context(ipdb.slaunch_ipdb_on_exception())

		houses_df = read_dataframe(houses_file)
		stops_df = read_dataframe(stops_file)

		stops_bufs = gpd.GeoDataFrame({'geometry': stops_df.geometry.buffer(max_dist)}, index=stops_df.index)

		matches = gpd.sjoin(stops_bufs, houses_df)

		houses_filter = houses_df.index.isin(matches.index_right.unique())
		houses_no_radius = houses_df[~houses_filter]

		results = []
		for source_id, gr in tqdm(matches.groupby(matches.index)):
			# iterate over stops, make table requests
			source = stops_df.geometry.to_crs(WGS).loc[source_id]

			destinations = gr.index_right.map(houses_df['geometry'].to_crs(WGS)).to_list()

			all_points = [source] + destinations
			encoded = encode_poly([(p.y, p.x) for p in all_points])

			params = {
				'sources': '0',
				'destinations': ';'.join(str(i) for i in range(1, len(all_points))),
				'generate_hints': 'false',
				'annotations': 'distance',
			}

			encoded_params = urllib.parse.quote_plus(urllib.parse.urlencode(params))
			encoded_url = f'{router_url}/table/v1/driving/polyline({encoded})?{encoded_params}'

			for i in range(retries_limit):
				sleep(i)

				try:
					response = requests.get(encoded_url)
				except requests.exceptions.ConnectionError as er:
					last_error = er
					continue

				if response.status_code != 200:
					last_error = Exception(f"server response {response.status_code}")
					continue

				resp_data = response.json()
				if resp_data['code'] != 'Ok':
					last_error = Exception(f"response ok, json code not ok: {resp_data['code']}")
					continue

				break  # good response, stop the cycle and don't exec the 'else' clause below

			else:  # ran out of retries limit.
				raise last_error

			results_df = pd.DataFrame({'distance': resp_data['distances'][0]})
			results_df['distance'] = results_df['distance'].astype(float)

			results_df['source_snap'] = resp_data['sources'][0]['distance']
			results_df['destination_snap'] = [i['distance'] for i in resp_data['destinations']]
			results_df['destination'] = gr['index_right'].values

			# instead of join/merge lookup
			results_df['geometry'] = results_df.destination.map(houses_df['geometry'].to_crs(WGS))

			if DEBUG:
				results_df['geometry_dest'] = source
				results_df['geometry'] = results_df.apply(lambda r: LineString([r.geometry, r.geometry_dest]), axis=1)
				results_df.drop('geometry_dest', axis=1, inplace=True)

			# shift back by the given offset
			results_df['destination'] = results_df['destination'].astype(int) + 1
			results_df['source'] = source_id

			results.append(results_df)

		houses_distances = gpd.GeoDataFrame(pd.concat(results))
		houses_distances['distance'] += houses_distances.source_snap + houses_distances.destination_snap
		houses_distances[['geometry', 'distance', 'source', 'destination']]
		houses_no_radius = houses_no_radius[['geometry']].to_crs(WGS)
		houses_no_radius['distance'] = np.inf
		houses_no_radius['source'] = None
		houses_no_radius['destination'] = houses_no_radius.index

		houses_distances = houses_distances.groupby('destination').agg({'geometry': 'first', 'distance': 'min'}).reset_index()

		all_houses = gpd.GeoDataFrame(pd.concat([houses_distances, houses_no_radius]), crs=WGS)
		all_houses.to_file(output_houses, driver='GPKG')
