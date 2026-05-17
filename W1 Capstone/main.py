from fastapi import FastAPI, Query, Path, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Annotated
import time
from contextlib import asynccontextmanager
import pandas as pd
from pathlib import Path as FilePath

from etlscript import convert_GPS, ETL_weather, load_data, load_all_data
from auth import router as auth_router, get_current_active_user, User
# Temporary database creation with local dict. Will be changed later when integrated with sql.
OUTPUT_DIR = FilePath(__file__).parent.parent / "datasets" / "weather-data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

class TransformRequest(BaseModel):
    city: str
    days: Annotated[int, Field(ge=1, le=16)]

def create_data():
    time.sleep(2)
    hourly_db = pd.read_csv(OUTPUT_DIR / "hourly.csv").to_dict()
    daily_db = pd.read_csv(OUTPUT_DIR / "daily.csv").to_dict()

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_data()
    yield

app = FastAPI(lifespan=lifespan, 
              title="Weather ETL App", 
              description="Fetches and transforms weather data via Open-Meteo",
              version="1.0.0")

app.include_router(auth_router)

@app.post("/transform")
async def get_new_forecast_data(request: TransformRequest, current_user: Annotated[User, Depends(get_current_active_user)]):
    city = request.city
    days = request.days
    try:
        convert_GPS(city)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    hourly_data, daily_data = ETL_weather(city=city, days=days)
    return {"Hourly data": hourly_data, "Daily data": daily_data}

@app.get("/data/{city}")
async def fetch_forecast_data(city: str):
    try:
        hourly_data, daily_data = load_data(city)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"Hourly data": hourly_data, "Daily data": daily_data}

@app.get("/data")
async def fetch_all_data():
    hourly_data, daily_data = load_all_data()
    return {"Hourly data": hourly_data, "Daily data": daily_data}

