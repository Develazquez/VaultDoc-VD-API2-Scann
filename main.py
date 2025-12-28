from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from controllers.scan_controller import router as scan_router
app.include_router(scan_router, prefix="/api/scan", tags=["Scan"])



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )