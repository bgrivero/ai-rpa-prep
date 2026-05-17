import openmeteo_requests

import pandas as pd
import requests_cache
import time
from datetime import datetime
from retry_requests import retry

from geopy.geocoders import Nominatim

# Helper function that turns string city inputs into longitude and latitude coordinates.
def convert_GPS(city: str) -> tuple[float, float]:
	geolocator = Nominatim(user_agent="sampleapplication")
	location = geolocator.geocode(city)
	if location is None:
		raise ValueError(f"{city} cannot be found.")
	return (location.latitude, location.longitude) 


def ETL_weather(longitude: float, latitude: float, days:int) -> tuple[dict, dict]:
	# Setup the Open-Meteo API client with cache and retry on error
	cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
	retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
	openmeteo = openmeteo_requests.Client(session = retry_session)

	# Make sure all required weather variables are listed here
	# The order of variables in hourly or daily is important to assign them correctly below
	url = "https://api.open-meteo.com/v1/forecast"
	params = {
		"latitude":  latitude,
		"longitude": longitude,
		"daily": ["temperature_2m_max", "temperature_2m_min", "weather_code", "precipitation_sum"],
		"hourly": ["temperature_2m", "relative_humidity_2m", "precipitation_probability", "precipitation", "pressure_msl", "wind_speed_10m", "wind_direction_10m", "temperature_80m", "soil_moisture_0_to_1cm"],
		"timezone": "Asia/Bangkok",
		"temperature_unit": "fahrenheit",
		"forecast_days": days
	}
	responses = openmeteo.weather_api(url, params = params)

	# Process first location. Add a for-loop for multiple locations or weather models
	response = responses[0]

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


	# Export to csv and excel
	current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
	hourly_dataframe.to_csv(f"../datasets/weather-data/{current_datetime}_hourly_weather_data.csv")
	daily_dataframe.to_csv(f"../datasets/weather-data/{current_datetime}_daily_weather_data.csv")

	hourly_dataframe["date"] = hourly_dataframe["date"].dt.tz_localize(None)
	daily_dataframe["date"] = daily_dataframe["date"].dt.tz_localize(None)
	hourly_dataframe.to_excel(f"../datasets/weather-data/{current_datetime}_hourly_weather_data.xlsx")
	daily_dataframe.to_excel(f"../datasets/weather-data/{current_datetime}_daily_weather_data.xlsx")
	return (hourly_dataframe.to_dict(), daily_dataframe.to_dict())
