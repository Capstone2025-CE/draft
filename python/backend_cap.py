from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# Model to receive counter value from Flutter
class CounterUpdate(BaseModel):
    value: int

@app.post("/update-counter")
async def update_counter(counter: CounterUpdate):
    print(f"Counter updated to: {counter.value}")  
    return {"message": f"Counter received: {counter.value}"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
