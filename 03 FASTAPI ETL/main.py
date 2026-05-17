from fastapi import FastAPI, Query, Path, HTTPException
from pydantic import BaseModel, Field

from typing import Annotated

from etlscript import convert_GPS, ETL_weather

# 1. Basic definition and path
app = FastAPI()

@app.get("/")
async def root():
    return {"message":"Hello World"}

# 2. Path Parameters
@app.get("/items/{item_id}")
async def get_item(item_id: int):
    return {"item_id": item_id}

# 3. Query Parameters
sample_db = [{"item_name":"Acer Aspire 7"},
             {"item_name":"ASUS"},
             {"item_name":"Laptop"}]

@app.get("/laptops")
async def get_laptop(laptop_id: int = 0, limit: int = len(sample_db)):
    return sample_db[laptop_id: laptop_id+limit]

# 4. Request Body using Pydantic Model

phone_db = []

class Phone(BaseModel):
    name: str
    phone_id: int
    description: str | None = None
    price: float
    tax: float | None = None

@app.post("/phones")
async def create_phone(phone: Phone):
    phone_dict = phone.model_dump()
    if phone.tax is not None:
        phone_dict.update({"price after tax": phone.tax + phone.price})
    phone_db.append(phone_dict)
    return phone_dict

@app.get("/phones")
async def read_phones(phone_id: int=0, limit: int=5):
    return phone_db[phone_id: phone_id + limit]

# 5. Use with ETL Script
hourly_db = {}
daily_db = {}

class TransformRequest(BaseModel):
    city: str
    days: Annotated[int, Field(ge=1, le=16)]

@app.post("/transform")
async def get_new_forecast_data(request: TransformRequest):
    city = request.city
    days = request.days
    try:
        latitude, longitude = convert_GPS(city)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    hourly_data, daily_data = ETL_weather(latitude=latitude, longitude=longitude, days=days)
    hourly_db[city] = hourly_data
    daily_db[city] = daily_data
    return {"Hourly data": hourly_data, "Daily data": daily_data}

@app.get("/data/{city}")
async def fetch_forecast_data(city: str):
    if city not in hourly_db:
        raise HTTPException(status_code=404, detail="City not yet found")
    return {"Hourly data": hourly_db[city], "Daily data": daily_db[city]}

@app.get("/data")
async def fetch_all_data():
    return {"Hourly data": hourly_db, "Daily data": daily_db}
