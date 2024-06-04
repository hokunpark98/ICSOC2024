from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

@app.get("/d")
async def d(value: int):
    result_value = value + 1
    return {"result": result_value}
