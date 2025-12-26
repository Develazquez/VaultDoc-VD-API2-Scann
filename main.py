
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from controllers.scan_controller import router as scan_router
from core.config import settings
import uvicorn

app = FastAPI(
    title="VaultDoc Scanner API",
    version="1.0.0",
    description="API para escanear y procesar documentos"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan_router, prefix="/api/scan", tags=["Scan"])

@app.get("/")
def read_root():
    return {
        "message": "VaultDoc Scanner API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
import requests
from requests.auth import HTTPBasicAuth

import requests
from requests.auth import HTTPBasicAuth
