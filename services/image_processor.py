import cv2
import numpy as np
from PIL import Image
import io
from typing import Tuple, List
import logging
import img2pdf

logger = logging.getLogger(__name__)


class ImageProcessor:
    
    @staticmethod
    def order_points(pts: np.ndarray) -> np.ndarray:

        rect = np.zeros((4, 2), dtype="float32")
        
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        
        return rect
    
    @staticmethod
    def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:

        rect = ImageProcessor.order_points(pts)
        (tl, tr, br, bl) = rect
        
        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))
        
        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))
        
        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]
        ], dtype="float32")
        
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
        
        return warped
    
    @staticmethod
    def detect_document(image: np.ndarray) -> np.ndarray:

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        edged = cv2.Canny(blurred, 75, 200)
        
        contours, _ = cv2.findContours(
            edged.copy(), 
            cv2.RETR_LIST, 
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
        
        screenCnt = None
        
        for c in contours:
            peri = cv2.arcLength(c, True)
            
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            
            if len(approx) == 4:
                screenCnt = approx
                break
        
        if screenCnt is None:
            height, width = image.shape[:2]
            logger.warning("No se detectó contorno del documento, usando imagen completa")
            screenCnt = np.array([
                [[0, 0]], 
                [[width, 0]], 
                [[width, height]], 
                [[0, height]]
            ])
        
        return screenCnt.reshape(4, 2)
    
    # Mejora la calidad del documento
    @staticmethod
    def enhance_document(image: np.ndarray) -> np.ndarray:

        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        enhanced = cv2.adaptiveThreshold(
            gray, 
            255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 
            11, 
            2
        )
        
        # Reducir ruido con denoising
        enhanced = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
        
        return enhanced
    
    @staticmethod
    def process_image_to_bytes(image_bytes: bytes, max_height: int = 1500) -> bytes:

        try:
            # Decodificar imagen desde bytes
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                raise ValueError("No se pudo decodificar la imagen")
            
            logger.info(f"Imagen original: {image.shape[1]}x{image.shape[0]} px")
            
            # Redimensionar si la imagen es muy grande
            ratio = 1.0
            if image.shape[0] > max_height:
                ratio = max_height / image.shape[0]
                new_width = int(image.shape[1] * ratio)
                new_height = int(image.shape[0] * ratio)
                image = cv2.resize(image, (new_width, new_height))
                logger.info(f"Imagen redimensionada a: {new_width}x{new_height} px (ratio: {ratio:.2f})")
            
            logger.info("Detectando bordes del documento")
            document_contour = ImageProcessor.detect_document(image)
            
            logger.info("Aplicando corrección de perspectiva")
            warped = ImageProcessor.four_point_transform(image, document_contour)
            
            logger.info("Mejorando calidad de imagen")
            enhanced = ImageProcessor.enhance_document(warped)
            
            enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
            
            pil_image = Image.fromarray(enhanced_rgb)
            
            # Convertir a bytes en formato PNG
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format='PNG', quality=95)
            img_byte_arr.seek(0)
            
            processed_bytes = img_byte_arr.getvalue()
            logger.info(f"Imagen procesada: {len(processed_bytes)} bytes")
            
            return processed_bytes
            
        except Exception as e:
            logger.error(f"Error al procesar imagen: {e}")
            raise ValueError(f"Error al procesar imagen: {str(e)}")
    
    @staticmethod
    def process_image(image_bytes: bytes, max_height: int = 1500) -> Tuple[bytes, str]:
        
        # Procesa una imagen y la convierte a PDF
        
        try:
            
            processed_image_bytes = ImageProcessor.process_image_to_bytes(image_bytes, max_height)
            
            logger.info("Convirtiendo imagen a PDF...")
            pdf_bytes = img2pdf.convert(processed_image_bytes)
            
            logger.info(f"PDF generado: {len(pdf_bytes)} bytes")
            
            return pdf_bytes, "pdf"
            
        except Exception as e:
            logger.error(f"Error al generar PDF: {e}")
            raise ValueError(f"Error al generar PDF: {str(e)}")
    
    @staticmethod
    def process_multiple_images_to_pdf(images_bytes: List[bytes], max_height: int = 1500) -> bytes:
        
        # Procesa múltiples imágenes y las combina en un solo PDF
    
        try:
            processed_images = []
            
            logger.info(f"Procesando {len(images_bytes)} imágenes para PDF múltiple...")
            
            for idx, img_bytes in enumerate(images_bytes, 1):
                logger.info(f"Procesando imagen {idx}/{len(images_bytes)}...")
                processed_img = ImageProcessor.process_image_to_bytes(img_bytes, max_height)
                processed_images.append(processed_img)
            
            
            logger.info("Combinando imágenes en PDF")
            pdf_bytes = img2pdf.convert(processed_images)
            
            logger.info(f"PDF múltiple generado: {len(pdf_bytes)} bytes con {len(images_bytes)} páginas")
            
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"Error al generar PDF múltiple: {e}")
            raise ValueError(f"Error al generar PDF múltiple: {str(e)}")
        #ok