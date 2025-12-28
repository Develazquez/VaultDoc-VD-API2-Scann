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

    try:
        
        logger.info(f"Folio: {folio}, Carpeta: {id_folder}, Usuario: {id_uploader}")
        logger.info(f"Departamento: {departamento}, Archivo: {file.filename}")
        
       
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
        
       
        image_bytes = await file.read()
        
        if len(image_bytes) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo excede el tamaño máximo permitido ({settings.MAX_FILE_SIZE / 1024 / 1024}MB)"
            )
        
        
        if file_service.check_file_exists(folio):
            raise HTTPException(status_code=400, detail=f"Ya existe un archivo con el folio {folio}")
        
       
        folder_info = file_service.get_folder_info(id_folder, departamento)
        if not folder_info:
            raise HTTPException(
                status_code=404,
                detail=f"Carpeta con ID {id_folder} no encontrada en el departamento {departamento}"
            )
        
        
        logger.info("Procesando imagen y generando PDF...")
        processed_pdf_bytes, extension = image_processor.process_image(
            image_bytes,
            max_height=settings.MAX_IMAGE_HEIGHT
        )
        
        base_name = file_service.generate_file_name(folio, departamento)
        file_name = f"{base_name}.{extension}"
        
        folder_path = f"{departamento}/{folder_info['name']}"
        
        if nextcloud_client.file_exists(folder_path, file_name):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {file_name} ya existe en Nextcloud en {folder_path}"
            )
        
        
        logger.info(f"Subiendo PDF a Nextcloud: {folder_path}/{file_name}")
        try:
            relative_path = nextcloud_client.upload_file(
                processed_pdf_bytes,
                folder_path,
                file_name
            )
        except Exception as e:
            logger.error(f"Error al subir PDF a Nextcloud: {e}")
            raise HTTPException(status_code=500, detail=f"Error al subir PDF a Nextcloud: {str(e)}")
        
        logger.info("Creando registro en la base de datos...")
        try:
            file_id = file_service.create_file_record(
                departamento=departamento,
                nombre=file_name,
                tamano=len(processed_pdf_bytes),
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
        
        
        try:
            file_service.grant_automatic_permissions(file_id, id_uploader, departamento)
            logger.info("Permisos automáticos otorgados")
        except Exception as e:
            logger.warning(f"Error al otorgar permisos automáticos: {e}")
        
        logger.info(f"✅ PDF creado exitosamente: {file_name}")
        
        return ScanResponse(
            message="Documento escaneado y convertido a PDF exitosamente",
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
        
        logger.info(f"Folio base: {folio_base}, Carpeta: {id_folder}, Usuario: {id_uploader}")
        logger.info(f"Departamento: {departamento}, Número de archivos: {len(files)}")
        
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="Debe subir por lo menos una imagen")
        
        
        folder_info = file_service.get_folder_info(id_folder, departamento)
        if not folder_info:
            raise HTTPException(
                status_code=404,
                detail=f"Carpeta con ID {id_folder} no encontrada en el departamento {departamento}"
            )
        
        folder_path = f"{departamento}/{folder_info['name']}"
        
        
        images_to_process = []
        
        for idx, file in enumerate(files, start=1):
            if not file.content_type.startswith('image/'):
                logger.warning(f"Archivo {idx} no es una imagen, omitiendo")
                continue
            
            image_bytes = await file.read()
            
            if len(image_bytes) > settings.MAX_FILE_SIZE:
                logger.warning(f"Archivo {idx} excede tamaño máximo, omitiendo")
                continue
            
            images_to_process.append(image_bytes)
        
        if len(images_to_process) == 0:
            raise HTTPException(status_code=400, detail="No hay imágenes válidas para procesar")
        
        
        if file_service.check_file_exists(folio_base):
            raise HTTPException(status_code=400, detail=f"Ya existe un archivo con el folio {folio_base}")
        
       
        logger.info(f"Procesando {len(images_to_process)} imágenes y generando PDF múltiple...")
        try:
            pdf_bytes = image_processor.process_multiple_images_to_pdf(
                images_to_process,
                max_height=settings.MAX_IMAGE_HEIGHT
            )
        except Exception as e:
            logger.error(f"Error al procesar imágenes múltiples: {e}")
            raise HTTPException(status_code=500, detail=f"Error al procesar imágenes: {str(e)}")
        
        
        base_name = file_service.generate_file_name(folio_base, departamento)
        file_name = f"{base_name}.pdf"
        
        
        if nextcloud_client.file_exists(folder_path, file_name):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {file_name} ya existe en Nextcloud en {folder_path}"
            )
        
        
        logger.info(f"Subiendo PDF de múltiples imagenes a Nextcloud: {folder_path}/{file_name}")
        try:
            relative_path = nextcloud_client.upload_file(
                pdf_bytes,
                folder_path,
                file_name
            )
        except Exception as e:
            logger.error(f"Error al subir PDF múltiple: {e}")
            raise HTTPException(status_code=500, detail=f"Error al subir PDF a Nextcloud: {str(e)}")
        
        # Crear UN SOLO registro en la BD para el PDF completo
        logger.info("Creando registro en base de datos...")
        try:
            file_id = file_service.create_file_record(
                departamento=departamento,
                nombre=file_name,
                tamano=len(pdf_bytes),
                fecha=datetime.now().strftime("%Y-%m-%d"),
                folio=folio_base,
                extension="pdf",
                id_folder=id_folder,
                id_uploader=id_uploader,
                directorio=relative_path
            )
            
            # Otorgar permisos
            file_service.grant_automatic_permissions(file_id, id_uploader, departamento)
            logger.info("Permisos automáticos otorgados")
            
        except Exception as e:
            # Revertir subida a Nextcloud
            nextcloud_client.delete_file(folder_path, file_name)
            logger.error(f"Error al crear registro para PDF múltiple: {e}")
            raise HTTPException(status_code=500, detail="Error al crear registro en base de datos")
        
        logger.info(f"PDF múltiple creado exitosamente: {file_name} con {len(images_to_process)} páginas")
        
        return ScanResponse(
            message=f"PDF creado con {len(images_to_process)} páginas procesadas",
            file_id=file_id,
            file_name=file_name,
            file_path=relative_path,
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado al escanear múltiples documentos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar los documentos: {str(e)}")




""" 
Enpdpoint opcional para debuging
@router.post("/debug")
async def debug_request(
    file: UploadFile = File(None),
    folio: str = Form(None),
    id_folder: str = Form(None),
    id_uploader: str = Form(None),
    departamento: str = Form(None)
):

    logger.info(f"file: {file.filename if file else 'None'}")
    logger.info(f"folio: {folio}")
    logger.info(f"id_folder: {id_folder}")
    logger.info(f"id_uploader: {id_uploader}")
    logger.info(f"departamento: {departamento}")
    
    return {
        "file": file.filename if file else None,
        "folio": folio,
        "id_folder": id_folder,
        "id_uploader": id_uploader,
        "departamento": departamento
    }

"""