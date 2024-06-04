from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import uvicorn

app = FastAPI()


@app.get("/c")
async def c(value: int):
    new_value = value + 1
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f'http://service-d:11003/d?value={new_value}')
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
