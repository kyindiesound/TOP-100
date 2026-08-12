import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from collectors import PublicCatalogCollector

app = FastAPI(title="KY INDIE SOUND API", version="2.0")

# Настройка CORS для связи с фронтендом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

collector = PublicCatalogCollector()

@app.get("/api/charts")
async def get_charts():
    """Эндпоинт для получения актуальных музыкальных данных."""
    data = await collector.fetch_all_platform_data()
    return {"status": "success", "data": data}

@app.get("/")
async def root():
    return {"status": "KY INDIE SOUND API is running"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
