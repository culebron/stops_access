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

MAX_TABLE_SIZE = 100_000
retries_limit = 10
WGS = CRS4326 = pyproj.CRS.from_epsg(4326)
SIB = pyproj.crs.ProjectedCRS(pyproj.crs.coordinate_operation.AlbersEqualAreaConversion(52, 64, 0, 105, 18500000, 0), name='Albers Siberia')


def read_dataframe(input_path):
	df = gpd.read_file(input_path)
	if df.crs is None:
		df.crs = WGS

	return df.to_crs(SIB)  # albers siberia projection for entire russia


def write_dataframe(df, output_path):
	df.to_file(output_path, driver='GPKG')


def get_local_houses(stops_df, houses_df, dist):
	houses_match = gpd.sjoin(gpd.GeoDataFrame({'geometry': [stops_df['geometry'].values[0].buffer(dist, resolution=5)]}, crs=SIB), houses_df)
	houses_local = houses_df[houses_df.index.isin(houses_match.index_right)]
	houses_dict = dict(enumerate(houses_local.index))
	return houses_local, houses_dict


@argh.dispatch_command
def main(houses_file, stops_file, router_url, output_houses, max_dist: float = 500):
	with ExitStack() as stack, tqdm(desc='Routing from stops') as tt:
		if DEBUG:
			import ipdb
			stack.enter_context(ipdb.slaunch_ipdb_on_exception())

		houses_df = read_dataframe(houses_file)
		stops_df = read_dataframe(stops_file)

		tt.total = len(stops_df)
		tt.refresh()

		# make circes around stops (lower number), and glue together
		# the .geoms object is polygons that stuck together
		partitions = gpd.GeoDataFrame({
			'geometry': stops_df.geometry.buffer(max_dist / 3, resolution=4).unary_union.geoms},
			crs=SIB)

		if DEBUG:
			write_dataframe(partitions, '/tmp/partitions.gpkg')

		# match stops and houses to partitions
		# gpd.sjoin is much faster than filtering a gdf by geometry
		stops_match = gpd.sjoin(partitions, stops_df)

		global_mins = None
		debug_dfs = []
		request_count = 0

		# walk throuh 
		for partition_id, stops_group in stops_match.groupby(stops_match.index):
			stops_local = stops_df[stops_df.index.isin(stops_group.index_right)]

			houses_local, houses_dict = get_local_houses(stops_group, houses_df, max_dist / 2)

			if len(houses_local) == 0:
				tt.update(len(stops_local))
				continue
			
			max_stops = int(MAX_TABLE_SIZE / len(houses_local))

			for s in range(0, len(stops_local), max_stops):
				stops_slice = stops_local[s:s + max_stops].copy()
				stops_dict = dict(enumerate(stops_slice.index))
				
				houses_local, houses_dict = get_local_houses(stops_slice, houses_df, max_dist)
				if len(houses_local) == 0:
					tt.update(len(stops_slice))
					continue
				
				# iterate over stops, make table requests
				sources_coords = stops_slice.geometry.to_crs(WGS).to_list()
				destinations_coords = houses_local.geometry.to_crs(WGS).to_list()

				all_points = sources_coords + destinations_coords
				encoded = encode_poly([(p.y, p.x) for p in all_points])
				source_num = len(sources_coords)

				params = {
					'sources': ';'.join(str(i) for i in range(source_num)),
					'destinations': ';'.join(str(i) for i in range(source_num, len(all_points))),
					'generate_hints': 'false',
					'annotations': 'distance',
				}

				encoded_params = urllib.parse.quote_plus(urllib.parse.urlencode(params))
				encoded_url = f'{router_url}/table/v1/driving/polyline({encoded})?{encoded_params}'

				for i in range(retries_limit):
					sleep(i)

					try:
						response = requests.get(encoded_url)
						request_count += 1
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

				results_df = pd.DataFrame(resp_data['distances'])

				sources_snap = pd.DataFrame(resp_data['sources'])['distance']
				destinations_snap = pd.DataFrame(resp_data['destinations'])['distance']
				# adding snap distances
				# df + vector => each vector item is added to corresponding _column_
				results_df = ((results_df + destinations_snap).T + sources_snap).T
				results_df = results_df.reset_index().rename(columns={'index': 'stop'}).melt(var_name='house', value_name='distance', id_vars='stop')

				# translate back to original ids
				results_df['house'] = results_df.house.map(houses_dict)
				results_df['stop'] = results_df.stop.map(stops_dict)
				
				# grouping by house (don't need stops)
				local_results = results_df.groupby('house').agg({'distance': 'min'})
				if global_mins is None:
					global_mins = local_results
				else:
					global_mins = pd.concat([global_mins, local_results]).groupby('house').agg({'distance': 'min'})

				tt.update(len(stops_slice))

				if DEBUG:
					results_df['geometry_source'] = results_df['stop'].map(stops_df['geometry'])
					results_df['geometry_dest'] = results_df['house'].map(houses_df['geometry'])

					results_df['geometry'] = results_df.apply(lambda r: LineString([r.geometry_source, r.geometry_dest]), axis=1)
					results_df.drop(['geometry_source', 'geometry_dest'], axis=1, inplace=True)
					results_df = gpd.GeoDataFrame(results_df)
					debug_dfs.append(results_df)

		houses_df['min_distance'] = houses_df.index.map(global_mins.distance.to_dict()).fillna(np.inf)
		write_dataframe(houses_df.to_crs(WGS), output_houses)

		if DEBUG:
			write_dataframe(pd.concat(debug_dfs), '/tmp/debug_lines.gpkg')
			print(f'{request_count} http requests')
