from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List
from datetime import datetime
import logging

from models.file_model import ScanRequest, ScanResponse
from services.image_processor import ImageProcessor
from services.file_service import FileService
from services.nextcloud_client import nextcloud_client
from core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

image_processor = ImageProcessor()
file_service = FileService()

@router.post("/single", response_model=ScanResponse)
async def scan_single_document(
    file: UploadFile = File(...),
    folio: str = Form(...),
    id_folder: int = Form(...),
    id_uploader: int = Form(...),
    departamento: str = Form(...)
):
    """
    Escanea una sola imagen y la sube al sistema
    """
    try:
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
        
        image_bytes = await file.read()
        
        if len(image_bytes) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo excede el tamaño máximo permitido ({settings.MAX_FILE_SIZE / 1024 / 1024}MB)"
            )
        
        # Verificar si el folio ya existe
        if file_service.check_file_exists(folio):
            raise HTTPException(status_code=400, detail=f"Ya existe un archivo con el folio {folio}")
        
        # Obtener información de la carpeta
        folder_info = file_service.get_folder_info(id_folder, departamento)
        if not folder_info:
            raise HTTPException(
                status_code=404,
                detail=f"Carpeta con ID {id_folder} no encontrada en el departamento {departamento}"
            )
        
        # Procesar imagen (detectar bordes, corregir perspectiva, mejorar calidad)
        processed_image_bytes, extension = image_processor.process_image(
            image_bytes,
            max_height=settings.MAX_IMAGE_HEIGHT
        )
        
        # Generar nombre del archivo
        base_name = file_service.generate_file_name(folio, departamento)
        file_name = f"{base_name}.{extension}"
        
        # Construir ruta de carpeta
        folder_path = f"{departamento}/{folder_info['name']}"
        
        # Verificar si el archivo ya existe en Nextcloud
        if nextcloud_client.file_exists(folder_path, file_name):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {file_name} ya existe en Nextcloud en {folder_path}"
            )
        
        try:
            relative_path = nextcloud_client.upload_file(
                processed_image_bytes,
                folder_path,
                file_name
            )
        except Exception as e:
            logger.error(f"Error al subir archivo a Nextcloud: {e}")
            raise HTTPException(status_code=500, detail="Error al subir archivo a Nextcloud")
        
        try:
            file_id = file_service.create_file_record(
                departamento=departamento,
                nombre=file_name,
                tamano=len(processed_image_bytes),
                fecha=datetime.now().strftime("%Y-%m-%d"),
                folio=folio,
                extension=extension,
                id_folder=id_folder,
                id_uploader=id_uploader,
                directorio=relative_path
            )
        except Exception as e:
            nextcloud_client.delete_file(folder_path, file_name)
            logger.error(f"Error al crear registro en BD: {e}")
            raise HTTPException(status_code=500, detail="Error al crear registro en base de datos")
        
        # Otorgar permisos automáticos
        try:
            file_service.grant_automatic_permissions(file_id, id_uploader, departamento)
        except Exception as e:
            logger.warning(f"Error al otorgar permisos automáticos: {e}")
        
        return ScanResponse(
            message="Documento escaneado y subido exitosamente",
            file_id=file_id,
            file_name=file_name,
            file_path=relative_path,
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado al escanear documento: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar el documento: {str(e)}")

@router.post("/multiple", response_model=ScanResponse)
async def scan_multiple_documents(
    files: List[UploadFile] = File(...),
    folio_base: str = Form(...),
    id_folder: int = Form(...),
    id_uploader: int = Form(...),
    departamento: str = Form(...)
):

    try:
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="Debe proporcionar al menos una imagen")
        
        folder_info = file_service.get_folder_info(id_folder, departamento)
        if not folder_info:
            raise HTTPException(
                status_code=404,
                detail=f"Carpeta con ID {id_folder} no encontrada en el departamento {departamento}"
            )
        
        folder_path = f"{departamento}/{folder_info['name']}"
        uploaded_files = []
        file_ids = []
        
        for idx, file in enumerate(files, start=1):
            if not file.content_type.startswith('image/'):
                continue
            
            image_bytes = await file.read()
            
            if len(image_bytes) > settings.MAX_FILE_SIZE:
                logger.warning(f"Archivo {idx} excede tamaño máximo, omitiendo")
                continue
            
            folio = f"{folio_base}-{idx}"
            
            if file_service.check_file_exists(folio):
                logger.warning(f"Folio {folio} ya existe, omitiendo")
                continue
            
            processed_image_bytes, extension = image_processor.process_image(
                image_bytes,
                max_height=settings.MAX_IMAGE_HEIGHT
            )
            
            base_name = file_service.generate_file_name(folio, departamento)
            file_name = f"{base_name}.{extension}"
            
            try:
                relative_path = nextcloud_client.upload_file(
                    processed_image_bytes,
                    folder_path,
                    file_name
                )
            except Exception as e:
                logger.error(f"Error al subir archivo {idx}: {e}")
                continue
            
            try:
                file_id = file_service.create_file_record(
                    departamento=departamento,
                    nombre=file_name,
                    tamano=len(processed_image_bytes),
                    fecha=datetime.now().strftime("%Y-%m-%d"),
                    folio=folio,
                    extension=extension,
                    id_folder=id_folder,
                    id_uploader=id_uploader,
                    directorio=relative_path
                )
                
                # Otorgar permisos
                file_service.grant_automatic_permissions(file_id, id_uploader, departamento)
                
                uploaded_files.append(file_name)
                file_ids.append(file_id)
                
            except Exception as e:
                nextcloud_client.delete_file(folder_path, file_name)
                logger.error(f"Error al crear registro para archivo {idx}: {e}")
                continue
        
        if len(uploaded_files) == 0:
            raise HTTPException(status_code=400, detail="No se pudo procesar ninguna imagen")
        
        return ScanResponse(
            message=f"{len(uploaded_files)} documentos escaneados y subidos exitosamente",
            file_id=file_ids[0] if file_ids else None,
            file_name=", ".join(uploaded_files),
            file_path=folder_path,
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado al escanear múltiples documentos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar los documentos: {str(e)}")

@router.get("/health")
async def health_check():
    """Verifica el estado del servicio"""
    return {
        "status": "healthy",
        "service": "scanner",
        "timestamp": datetime.now().isoformat()
    }