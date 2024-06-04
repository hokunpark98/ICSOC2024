from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import uvicorn

app = FastAPI()


@app.get("/b")
async def b(value: int):
    new_value = value + 1
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f'http://service-c:11002/c?value={new_value}')
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
