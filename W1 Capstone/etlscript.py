import openmeteo_requests

import pandas as pd
import requests_cache
import time
from datetime import datetime
from retry_requests import retry
from pathlib import Path

from geopy.geocoders import Nominatim

OUTPUT_DIR = Path(__file__).parent.parent / "datasets" / "weather-data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Helper function that turns string city inputs into longitude and latitude coordinates.
def convert_GPS(city: str) -> tuple[float, float]:
	geolocator = Nominatim(user_agent="sampleapplication")
	location = geolocator.geocode(city)
	if location is None:
		raise ValueError(f"{city} cannot be found.")
	return (location.longitude, location.latitude) 

def extract_data(city: str, days:int) -> tuple[dict, dict]:
	# Setup the Open-Meteo API client with cache and retry on error
	cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
	retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
	openmeteo = openmeteo_requests.Client(session = retry_session)

	longitude, latitude = convert_GPS(city)

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

	hourly_dataframe["city"] = city
	daily_dataframe["city"] = city
	return (hourly_dataframe, daily_dataframe)

def transform_data(hourly_dataframe: pd.DataFrame, daily_dataframe: pd.DataFrame) \
	-> tuple[pd.DataFrame, pd.DataFrame]:
	# Extract the time and date column
	hourly_dataframe["timestamp"] = hourly_dataframe["date"].dt.time
	hourly_dataframe["day_of_record"] = hourly_dataframe["date"].dt.date
	daily_dataframe["day_of_record"] = daily_dataframe["date"].dt.date

	# Convert temperature to celsius
	def to_celsius(series):
		return (series-32)*5/9

	hourly_dataframe["temperature_2m_cs"] = to_celsius(hourly_dataframe["temperature_2m"])
	hourly_dataframe["temperature_80m_cs"] = to_celsius(hourly_dataframe["temperature_80m"])
	daily_dataframe["temperature_2m_max_cs"] = to_celsius(daily_dataframe["temperature_2m_max"])
	daily_dataframe["temperature_2m_min_cs"] = to_celsius(daily_dataframe["temperature_2m_min"])

	hourly_dataframe.set_index(["city"], inplace=True)
	daily_dataframe.set_index(["city"], inplace=True)
	return (hourly_dataframe, daily_dataframe)

def log_data(hourly_dataframe: pd.DataFrame, daily_dataframe: pd.DataFrame, city:str):
	def save_with_upsert(new_dataframe: pd.DataFrame, path: Path, is_Excel: bool):
		if path.exists():
			prev_dataframe = pd.read_excel(path) if is_Excel else pd.read_csv(path)
			prev_dataframe.set_index(["city"], inplace=True)
			prev_dataframe = prev_dataframe.drop(index=city, errors="ignore")
			
			combined_dataframe = pd.concat([prev_dataframe, new_dataframe])
		else:
			combined_dataframe = new_dataframe
		combined_dataframe = combined_dataframe.reset_index()
		if is_Excel:
			combined_dataframe.to_excel(path, index=False)
		else:
			combined_dataframe.to_csv(path, index=False)
	
	save_with_upsert(hourly_dataframe, OUTPUT_DIR / "hourly.csv", False )
	save_with_upsert(daily_dataframe, OUTPUT_DIR / "daily.csv", False )
	
	hourly_dataframe["date"] = hourly_dataframe["date"].dt.tz_localize(None)
	daily_dataframe["date"] = daily_dataframe["date"].dt.tz_localize(None)

	save_with_upsert(hourly_dataframe, OUTPUT_DIR / "hourly.xlsx", True )
	save_with_upsert(daily_dataframe, OUTPUT_DIR / "daily.xlsx", True )

def ETL_weather(city:str, days:int) -> tuple[dict, dict]:
	hourly_dataframe, daily_dataframe = extract_data(
		city=city,
		days=days)
	
	hourly_dataframe, daily_dataframe = transform_data(
		hourly_dataframe=hourly_dataframe,
		daily_dataframe=daily_dataframe
	)
	log_data(hourly_dataframe=hourly_dataframe, daily_dataframe=daily_dataframe, city=city)
	return (hourly_dataframe.to_dict(orient="records"), daily_dataframe.to_dict(orient="records"))

# Read from the csv for a specific city
def load_data(city: str) -> tuple[dict, dict]:
	hourly_dataframe = pd.read_csv(OUTPUT_DIR / "hourly.csv")
	daily_dataframe = pd.read_csv(OUTPUT_DIR / "daily.csv")

	if city not in hourly_dataframe["city"].values:
		raise ValueError(f"{city} does not currently exist in the database. Consider doing a request.")
	
	hourly_dataframe = hourly_dataframe[hourly_dataframe["city"] == city]
	daily_dataframe = daily_dataframe[daily_dataframe["city"] == city]
	return (hourly_dataframe.to_dict(orient="records"), daily_dataframe.to_dict(orient="records"))

def load_all_data() -> tuple[dict, dict]:
	hourly_dataframe = pd.read_csv(OUTPUT_DIR / "hourly.csv")
	daily_dataframe = pd.read_csv(OUTPUT_DIR / "daily.csv")
	return (hourly_dataframe.to_dict(orient="records"), daily_dataframe.to_dict(orient="records"))

# ETL_weather("San Jose del Monte City", 1)