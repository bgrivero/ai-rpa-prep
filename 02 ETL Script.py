import openmeteo_requests

from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import requests_cache
import time
from datetime import datetime
from retry_requests import retry


def ETL_weather():
	# Setup the Open-Meteo API client with cache and retry on error
	cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
	retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
	openmeteo = openmeteo_requests.Client(session = retry_session)

	# Make sure all required weather variables are listed here
	# The order of variables in hourly or daily is important to assign them correctly below
	url = "https://api.open-meteo.com/v1/forecast"
	params = {
		"latitude": 14.822561873922758,
		"longitude": 121.07891514331311,
		"daily": ["temperature_2m_max", "temperature_2m_min", "weather_code", "precipitation_sum"],
		"hourly": ["temperature_2m", "relative_humidity_2m", "precipitation_probability", "precipitation", "pressure_msl", "wind_speed_10m", "wind_direction_10m", "temperature_80m", "soil_moisture_0_to_1cm"],
		"timezone": "Asia/Bangkok",
		"temperature_unit": "fahrenheit"
	}
	responses = openmeteo.weather_api(url, params = params)

	# Process first location. Add a for-loop for multiple locations or weather models
	response = responses[0]
	print(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")
	print(f"Elevation: {response.Elevation()} m asl")
	print(f"Timezone: {response.Timezone()}{response.TimezoneAbbreviation()}")
	print(f"Timezone difference to GMT+0: {response.UtcOffsetSeconds()}s")

	# Process hourly data. The order of variables needs to be the same as requested.
	hourly = response.Hourly()
	hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
	hourly_relative_humidity_2m = hourly.Variables(1).ValuesAsNumpy()
	hourly_precipitation_probability = hourly.Variables(2).ValuesAsNumpy()
	hourly_precipitation = hourly.Variables(3).ValuesAsNumpy()
	hourly_pressure_msl = hourly.Variables(4).ValuesAsNumpy()
	hourly_wind_speed_10m = hourly.Variables(5).ValuesAsNumpy()
	hourly_wind_direction_10m = hourly.Variables(6).ValuesAsNumpy()
	hourly_temperature_80m = hourly.Variables(7).ValuesAsNumpy()
	hourly_soil_moisture_0_to_1cm = hourly.Variables(8).ValuesAsNumpy()

	hourly_data = {
		"date": pd.date_range(
			start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
			end =  pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
			freq = pd.Timedelta(seconds = hourly.Interval()),
			inclusive = "left"
		).tz_convert(response.Timezone().decode())
	}

	hourly_data["temperature_2m"] = hourly_temperature_2m
	hourly_data["relative_humidity_2m"] = hourly_relative_humidity_2m
	hourly_data["precipitation_probability"] = hourly_precipitation_probability
	hourly_data["precipitation"] = hourly_precipitation
	hourly_data["pressure_msl"] = hourly_pressure_msl
	hourly_data["wind_speed_10m"] = hourly_wind_speed_10m
	hourly_data["wind_direction_10m"] = hourly_wind_direction_10m
	hourly_data["temperature_80m"] = hourly_temperature_80m
	hourly_data["soil_moisture_0_to_1cm"] = hourly_soil_moisture_0_to_1cm

	hourly_dataframe = pd.DataFrame(data = hourly_data)
	print("\nHourly data\n", hourly_dataframe.head())

	# Process daily data. The order of variables needs to be the same as requested.
	daily = response.Daily()
	daily_temperature_2m_max = daily.Variables(0).ValuesAsNumpy()
	daily_temperature_2m_min = daily.Variables(1).ValuesAsNumpy()
	daily_weather_code = daily.Variables(2).ValuesAsNumpy()
	daily_precipitation_sum = daily.Variables(3).ValuesAsNumpy()

	daily_data = {
		"date": pd.date_range(
			start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
			end =  pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
			freq = pd.Timedelta(seconds = daily.Interval()),
			inclusive = "left"
		).tz_convert(response.Timezone().decode())
	}

	daily_data["temperature_2m_max"] = daily_temperature_2m_max
	daily_data["temperature_2m_min"] = daily_temperature_2m_min
	daily_data["weather_code"] = daily_weather_code
	daily_data["precipitation_sum"] = daily_precipitation_sum

	daily_dataframe = pd.DataFrame(data = daily_data)
	print("\nDaily data\n", daily_dataframe.head())

	# Check for types
	print(f"Dtypes for daily: \n {daily_dataframe.dtypes}")
	print(f"Dtypes for hourly: \n {hourly_dataframe.dtypes}")

	# Check for nulls
	print(f"Nulls for daily: \n {daily_dataframe.isna().sum()}")
	print(f"Nulls for hourly: \n {hourly_dataframe.isna().sum()}")

	# Extract the time and date column
	hourly_dataframe["timestamp"] = hourly_dataframe["date"].dt.time
	hourly_dataframe["day_of_record"] = hourly_dataframe["date"].dt.date
	daily_dataframe["timestamp"] = daily_dataframe["date"].dt.time
	daily_dataframe["day_of_record"] = daily_dataframe["date"].dt.date

	# Convert temperature to celsius
	def to_celsius(series):
		return (series-32)*5/9

	hourly_dataframe["temperature_2m_cs"] = to_celsius(hourly_dataframe["temperature_2m"])
	hourly_dataframe["temperature_80m_cs"] = to_celsius(hourly_dataframe["temperature_80m"])
	daily_dataframe["temperature_2m_max_cs"] = to_celsius(daily_dataframe["temperature_2m_max"])
	daily_dataframe["temperature_2m_min_cs"] = to_celsius(daily_dataframe["temperature_2m_min"])

	# Check the extracted columns
	print("\nDaily data\n", daily_dataframe.head())
	print("\nHourly data\n", hourly_dataframe.head())
	print(f"Dtypes for daily: \n {daily_dataframe.dtypes}")
	print(f"Dtypes for hourly: \n {hourly_dataframe.dtypes}")

	# Export to csv and excel
	current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
	hourly_dataframe.to_csv(f"datasets/weather-data/{current_datetime}_hourly_weather_data.csv")
	daily_dataframe.to_csv(f"datasets/weather-data/{current_datetime}_daily_weather_data.csv")

	hourly_dataframe["date"] = hourly_dataframe["date"].dt.tz_localize(None)
	daily_dataframe["date"] = daily_dataframe["date"].dt.tz_localize(None)
	hourly_dataframe.to_excel(f"datasets/weather-data/{current_datetime}_hourly_weather_data.xlsx")
	daily_dataframe.to_excel(f"datasets/weather-data/{current_datetime}_daily_weather_data.xlsx")

scheduler = BackgroundScheduler()
scheduler.add_job(ETL_weather, 'interval', minutes=30)
ETL_weather()
scheduler.start()

try:
	while True:
		time.sleep(60)
except (KeyboardInterrupt, SystemExit):
       scheduler.shutdown()