from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import redis
from dotenv import load_dotenv
import yaml
import os

load_dotenv()

app = FastAPI(title="My API")

class Item(BaseModel):
    name: str
    price: float

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
)

@app.get("/items/{item_id}")
async def get_item(item_id: str):
    cached = redis_client.get(f"item:{item_id}")
    if cached:
        return yaml.safe_load(cached)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.example.com/items/{item_id}")
        return resp.json()

@app.post("/items")
async def create_item(item: Item):
    redis_client.set(f"item:{item.name}", yaml.dump(item.model_dump()))
    return {"status": "created"}
