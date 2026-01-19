from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import List
from datetime import datetime
import logging
import json

from models.file_model import ScanRequest, ScanResponse
from models.scan_points_model import Point, PerspectiveScanRequest
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
        
        # Validar tipo de archivo
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
        
        # Leer contenido del archivo
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
        
        # Procesar imagen, convertir a PDF y extraer texto con OCR
        logger.info("Procesando imagen, generando PDF y extrayendo texto...")
        processed_pdf_bytes, extension, ocr_data = image_processor.process_image(
            image_bytes,
            max_height=settings.MAX_IMAGE_HEIGHT,
            perform_ocr=True  # Habilitar OCR
        )
        
        # Generar nombre del archivo PDF
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
        
        logger.info("Creando registro en base de datos...")
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
            # Revertir subida a Nextcloud
            nextcloud_client.delete_file(folder_path, file_name)
            logger.error(f"Error al crear registro en BD: {e}")
            raise HTTPException(status_code=500, detail="Error al crear registro en base de datos")
        
        # Otorgar permisos automáticos
        try:
            file_service.grant_automatic_permissions(file_id, id_uploader, departamento)
            logger.info("Permisos automáticos otorgados")
        except Exception as e:
            logger.warning(f"Error al otorgar permisos automáticos: {e}")
        
        logger.info(f"PDF creado exitosamente: {file_name}")
        
        response_message = "Documento escaneado y convertido a PDF exitosamente"
        if ocr_data.get('has_text'):
            response_message += f" | Texto extraído: {ocr_data['word_count']} palabras (confianza: {ocr_data['confidence']:.1f}%)"
        
        return ScanResponse(
            message=response_message,
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
            raise HTTPException(status_code=400, detail="Debe proporcionar al menos una imagen")
        
        # Obtener información de la carpeta
        folder_info = file_service.get_folder_info(id_folder, departamento)
        if not folder_info:
            raise HTTPException(
                status_code=404,
                detail=f"Carpeta con ID {id_folder} no encontrada en el departamento {departamento}"
            )
        
        folder_path = f"{departamento}/{folder_info['name']}"
        
        # Recopilar todas las imágenes válidas
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
        
        # Verificar si el folio base ya existe
        if file_service.check_file_exists(folio_base):
            raise HTTPException(status_code=400, detail=f"Ya existe un archivo con el folio {folio_base}")
        
        # Procesar todas las imágenes, crear PDF y extraer texto
        logger.info(f"Procesando {len(images_to_process)} imágenes, generando PDF y extrayendo texto...")
        try:
            pdf_bytes, ocr_results = image_processor.process_multiple_images_to_pdf(
                images_to_process,
                max_height=settings.MAX_IMAGE_HEIGHT,
                perform_ocr=True  # Habilitar OCR
            )
        except Exception as e:
            logger.error(f"Error al procesar imágenes múltiples: {e}")
            raise HTTPException(status_code=500, detail=f"Error al procesar imágenes: {str(e)}")
        
        # Generar nombre del archivo PDF
        base_name = file_service.generate_file_name(folio_base, departamento)
        file_name = f"{base_name}.pdf"
        
        # Verificar si el archivo ya existe en Nextcloud
        if nextcloud_client.file_exists(folder_path, file_name):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {file_name} ya existe en Nextcloud en {folder_path}"
            )
        
        # Subir el PDF a Nextcloud
        logger.info(f"Subiendo PDF múltiple a Nextcloud: {folder_path}/{file_name}")
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
            nextcloud_client.delete_file(folder_path, file_name)
            logger.error(f"Error al crear registro para PDF múltiple: {e}")
            raise HTTPException(status_code=500, detail="Error al crear registro en base de datos")
        
        logger.info(f"DF múltiple creado exitosamente: {file_name} con {len(images_to_process)} páginas")
        
        total_words = sum(ocr['word_count'] for ocr in ocr_results if ocr.get('word_count', 0) > 0)
        response_message = f"PDF creado con {len(images_to_process)} páginas procesadas"
        if total_words > 0:
            avg_confidence = sum(ocr['confidence'] for ocr in ocr_results) / len(ocr_results)
            response_message += f" | Texto extraído: {total_words} palabras totales (confianza: {avg_confidence:.1f}%)"
        
        return ScanResponse(
            message=response_message,
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


@router.get("/health")
async def health_check():
    """Verifica el estado del servicio"""
    return {
        "status": "healthy",
        "service": "scanner",
        "timestamp": datetime.now().isoformat()
    }

@router.post("/detect-corners")
async def detect_corners(file: UploadFile = File(...)):

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Debe ser una imagen")

    image_bytes = await file.read()

    image = image_processor.bytes_to_cv2(image_bytes)
    corners = image_processor.detect_corners(image)

    if not corners:
        return {"found": False, "corners": []}

    return {"found": True, "corners": corners}


@router.post("/transform-perspective")
async def transform_perspective(
    file: UploadFile = File(...),
    points: str = Form(...)
):
    """
    Aplica transformación de perspectiva a una imagen usando 4 puntos.
    
    Args:
        file: Imagen a transformar
        points: JSON string con array de 4 puntos [{"x": float, "y": float}, ...]
               Orden esperado: top-left, top-right, bottom-right, bottom-left
    
    Returns:
        JSON con la imagen transformada en formato base64 (data URI)
        para renderizar directamente en Angular con <img [src]="imageData">
    """
    try:
        # Validar tipo de archivo
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
        
        # Parsear los puntos desde JSON
        try:
            points_data = json.loads(points)
            if len(points_data) != 4:
                raise HTTPException(
                    status_code=400, 
                    detail="Se requieren exactamente 4 puntos"
                )
            
            # Convertir a lista de tuplas
            point_tuples = [(p["x"], p["y"]) for p in points_data]
            
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, 
                detail="Formato de puntos inválido. Debe ser JSON: [{\"x\": 0, \"y\": 0}, ...]"
            )
        except KeyError:
            raise HTTPException(
                status_code=400, 
                detail="Cada punto debe tener propiedades 'x' e 'y'"
            )
        
        # Leer imagen
        image_bytes = await file.read()
        
        if len(image_bytes) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo excede el tamaño máximo permitido ({settings.MAX_FILE_SIZE / 1024 / 1024}MB)"
            )
        
        # Aplicar transformación
        logger.info(f"Aplicando transformación de perspectiva con puntos: {point_tuples}")
        
        transformed_image_base64 = image_processor.apply_perspective_transform(
            image_bytes, 
            point_tuples
        )
        
        return JSONResponse(content={
            "success": True,
            "message": "Imagen transformada exitosamente",
            "image": transformed_image_base64
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al transformar perspectiva: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error al procesar la transformación: {str(e)}"
        )


@router.post("/detect-corners-multiple")
async def detect_corners_multiple(files: List[UploadFile] = File(...)):
    """
    Detecta las esquinas de múltiples imágenes.
    
    Args:
        files: Lista de imágenes a procesar
    
    Returns:
        JSON con array de resultados, cada uno con las esquinas detectadas
        [{"index": 0, "filename": "img.jpg", "found": true, "corners": [...]}, ...]
    """
    try:
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="Debe proporcionar al menos una imagen")
        
        results = []
        
        for idx, file in enumerate(files):
            result = {
                "index": idx,
                "filename": file.filename,
                "found": False,
                "corners": []
            }
            
            # Validar tipo de archivo
            if not file.content_type.startswith("image/"):
                result["error"] = "No es una imagen válida"
                results.append(result)
                continue
            
            try:
                image_bytes = await file.read()
                
                if len(image_bytes) > settings.MAX_FILE_SIZE:
                    result["error"] = "Archivo excede tamaño máximo"
                    results.append(result)
                    continue
                
                image = image_processor.bytes_to_cv2(image_bytes)
                corners = image_processor.detect_corners(image)
                
                if corners:
                    result["found"] = True
                    result["corners"] = corners
                
            except Exception as e:
                logger.warning(f"Error procesando imagen {idx}: {e}")
                result["error"] = str(e)
            
            results.append(result)
        
        found_count = sum(1 for r in results if r["found"])
        
        return JSONResponse(content={
            "success": True,
            "total": len(files),
            "detected": found_count,
            "results": results
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al detectar esquinas múltiples: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar las imágenes: {str(e)}"
        )


@router.post("/transform-perspective-multiple")
async def transform_perspective_multiple(
    files: List[UploadFile] = File(...),
    points_list: str = Form(...)
):
    """
    Aplica transformación de perspectiva a múltiples imágenes.
    
    Args:
        files: Lista de imágenes a transformar
        points_list: JSON string con array de arrays de 4 puntos para cada imagen
                    [[{"x": float, "y": float}, ...], [...], ...]
                    Debe haber un array de 4 puntos por cada imagen
    
    Returns:
        JSON con array de imágenes transformadas en formato base64 (data URI)
        para renderizar directamente en Angular
    """
    try:
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="Debe proporcionar al menos una imagen")
        
        # Parsear los puntos desde JSON
        try:
            all_points_data = json.loads(points_list)
            
            if len(all_points_data) != len(files):
                raise HTTPException(
                    status_code=400,
                    detail=f"El número de conjuntos de puntos ({len(all_points_data)}) debe coincidir con el número de imágenes ({len(files)})"
                )
            
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Formato de puntos inválido. Debe ser JSON: [[{\"x\": 0, \"y\": 0}, ...], ...]"
            )
        
        results = []
        
        for idx, (file, points_data) in enumerate(zip(files, all_points_data)):
            result = {
                "index": idx,
                "filename": file.filename,
                "success": False,
                "image": None
            }
            
            # Validar tipo de archivo
            if not file.content_type.startswith("image/"):
                result["error"] = "No es una imagen válida"
                results.append(result)
                continue
            
            # Validar puntos
            if len(points_data) != 4:
                result["error"] = "Se requieren exactamente 4 puntos"
                results.append(result)
                continue
            
            try:
                # Convertir a lista de tuplas
                point_tuples = [(p["x"], p["y"]) for p in points_data]
                
                image_bytes = await file.read()
                
                if len(image_bytes) > settings.MAX_FILE_SIZE:
                    result["error"] = "Archivo excede tamaño máximo"
                    results.append(result)
                    continue
                
                logger.info(f"Transformando imagen {idx} con puntos: {point_tuples}")
                
                transformed_image_base64 = image_processor.apply_perspective_transform(
                    image_bytes,
                    point_tuples
                )
                
                result["success"] = True
                result["image"] = transformed_image_base64
                
            except KeyError:
                result["error"] = "Cada punto debe tener propiedades 'x' e 'y'"
            except Exception as e:
                logger.warning(f"Error transformando imagen {idx}: {e}")
                result["error"] = str(e)
            
            results.append(result)
        
        success_count = sum(1 for r in results if r["success"])
        
        return JSONResponse(content={
            "success": True,
            "total": len(files),
            "transformed": success_count,
            "message": f"{success_count} de {len(files)} imágenes transformadas exitosamente",
            "results": results
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al transformar perspectiva múltiple: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar las transformaciones: {str(e)}"
        )
