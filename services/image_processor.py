import cv2
import numpy as np
from PIL import Image
import io
from typing import Tuple

class ImageProcessor:
    
    @staticmethod
    def order_points(pts: np.ndarray) -> np.ndarray:
        """Ordena los puntos: top-left, top-right, bottom-right, bottom-left"""
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
        """Aplica transformación de perspectiva"""
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
            [0, maxHeight - 1]], dtype="float32")
        
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
        
        return warped
    
    @staticmethod
    def detect_document(image: np.ndarray) -> np.ndarray:
        """Detecta los bordes del documento"""
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
            screenCnt = np.array([
                [[0, 0]], 
                [[width, 0]], 
                [[width, height]], 
                [[0, height]]
            ])
        
        return screenCnt.reshape(4, 2)
    
    @staticmethod
    def enhance_document(image: np.ndarray) -> np.ndarray:
        """Mejora la calidad del documento escaneado"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        enhanced = cv2.adaptiveThreshold(
            gray, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        enhanced = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
        
        return enhanced
    
    @staticmethod
    def process_image(image_bytes: bytes, max_height: int = 1500) -> Tuple[bytes, str]:
        """
        Procesa una imagen: detecta, corrige perspectiva y mejora calidad
        Retorna: (imagen_procesada_bytes, extension)
        """
        # Decodificar imagen
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise ValueError("No se pudo decodificar la imagen")
        
        # Redimensionar si es muy grande
        if image.shape[0] > max_height:
            ratio = max_height / image.shape[0]
            image = cv2.resize(image, None, fx=ratio, fy=ratio)
        
        # Detectar documento
        document_contour = ImageProcessor.detect_document(image)
        
        # Aplicar transformación de perspectiva
        warped = ImageProcessor.four_point_transform(image, document_contour)
        
        # Mejorar la imagen
        enhanced = ImageProcessor.enhance_document(warped)
        
        # Convertir a RGB para PIL
        enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
        
        # Convertir a PIL Image
        pil_image = Image.fromarray(enhanced_rgb)
        
        # Convertir a bytes
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG', quality=95)
        img_byte_arr.seek(0)
        
        return img_byte_arr.getvalue(), "png"