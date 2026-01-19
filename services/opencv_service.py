import cv2
import numpy as np
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class OpenCVService:

    # ---------- DETECCIÓN DE DOCUMENTO ----------

    @staticmethod
    def detect_document_corners(image: np.ndarray) -> List[Tuple[int, int]]:
        """
        Detecta las 4 esquinas de un documento en una imagen.
        Usa múltiples técnicas para mejorar la detección.
        """
        height, width = image.shape[:2]
        image_area = height * width
        min_area = image_area * 0.1  # El documento debe ocupar al menos 10% de la imagen
        
        # Preprocesamiento mejorado
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Aplicar CLAHE para mejorar contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Intentar múltiples métodos de detección
        methods = [
            lambda: OpenCVService._detect_with_canny_multi(enhanced, min_area),
            lambda: OpenCVService._detect_with_adaptive_threshold(enhanced, min_area),
            lambda: OpenCVService._detect_with_morphology(enhanced, min_area),
            lambda: OpenCVService._detect_with_hough_lines(enhanced, width, height),
        ]
        
        for method in methods:
            try:
                corners = method()
                if corners and len(corners) == 4:
                    if OpenCVService._validate_quadrilateral(corners, width, height, min_area):
                        logger.info(f"Documento detectado con método: {method.__name__ if hasattr(method, '__name__') else 'lambda'}")
                        return corners
            except Exception as e:
                logger.debug(f"Método de detección falló: {e}")
                continue
        
        logger.warning("No se pudo detectar el documento con ningún método")
        return []

    @staticmethod
    def _detect_with_canny_multi(gray: np.ndarray, min_area: float) -> Optional[List[Tuple[int, int]]]:
        """Detección con Canny usando múltiples umbrales."""
        best_contour = None
        max_area = min_area
        
        # Probar diferentes combinaciones de umbrales Canny
        canny_params = [
            (30, 100),
            (50, 150),
            (75, 200),
            (100, 250),
        ]
        
        for low, high in canny_params:
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blur, low, high)
            
            # Dilatar para conectar bordes fragmentados
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges, kernel, iterations=1)
            
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            
            contour = OpenCVService._find_best_quadrilateral(contours, min_area)
            if contour is not None:
                area = cv2.contourArea(contour)
                if area > max_area:
                    best_contour = contour
                    max_area = area
        
        if best_contour is not None:
            points = [(int(p[0][0]), int(p[0][1])) for p in best_contour]
            return OpenCVService.order_points(points)
        return None

    @staticmethod
    def _detect_with_adaptive_threshold(gray: np.ndarray, min_area: float) -> Optional[List[Tuple[int, int]]]:
        """Detección usando umbralización adaptativa."""
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Umbral adaptativo
        thresh = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # Operaciones morfológicas para limpiar
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best = OpenCVService._find_best_quadrilateral(contours, min_area)
        if best is not None:
            points = [(int(p[0][0]), int(p[0][1])) for p in best]
            return OpenCVService.order_points(points)
        return None

    @staticmethod
    def _detect_with_morphology(gray: np.ndarray, min_area: float) -> Optional[List[Tuple[int, int]]]:
        """Detección usando gradiente morfológico."""
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Gradiente morfológico para detectar bordes
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        gradient = cv2.morphologyEx(blur, cv2.MORPH_GRADIENT, kernel)
        
        # Umbralizar el gradiente
        _, thresh = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Cerrar huecos
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_close, iterations=2)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best = OpenCVService._find_best_quadrilateral(contours, min_area)
        if best is not None:
            points = [(int(p[0][0]), int(p[0][1])) for p in best]
            return OpenCVService.order_points(points)
        return None

    @staticmethod
    def _detect_with_hough_lines(gray: np.ndarray, width: int, height: int) -> Optional[List[Tuple[int, int]]]:
        """Detección usando líneas de Hough como método de respaldo."""
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        
        # Detectar líneas
        lines = cv2.HoughLinesP(
            edges, 1, np.pi/180, threshold=80,
            minLineLength=min(width, height) * 0.2,
            maxLineGap=20
        )
        
        if lines is None or len(lines) < 4:
            return None
        
        # Separar líneas horizontales y verticales
        horizontal = []
        vertical = []
        
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            
            if angle < 30 or angle > 150:  # Horizontal
                horizontal.append(line[0])
            elif 60 < angle < 120:  # Vertical
                vertical.append(line[0])
        
        if len(horizontal) < 2 or len(vertical) < 2:
            return None
        
        # Encontrar las líneas más extremas
        horizontal = sorted(horizontal, key=lambda l: (l[1] + l[3]) / 2)
        vertical = sorted(vertical, key=lambda l: (l[0] + l[2]) / 2)
        
        top_line = horizontal[0]
        bottom_line = horizontal[-1]
        left_line = vertical[0]
        right_line = vertical[-1]
        
        # Calcular intersecciones
        corners = [
            OpenCVService._line_intersection(top_line, left_line),
            OpenCVService._line_intersection(top_line, right_line),
            OpenCVService._line_intersection(bottom_line, right_line),
            OpenCVService._line_intersection(bottom_line, left_line),
        ]
        
        if None in corners:
            return None
        
        # Validar que los puntos estén dentro de la imagen
        valid_corners = []
        for x, y in corners:
            x = max(0, min(width - 1, int(x)))
            y = max(0, min(height - 1, int(y)))
            valid_corners.append((x, y))
        
        return OpenCVService.order_points(valid_corners)

    @staticmethod
    def _line_intersection(line1, line2) -> Optional[Tuple[float, float]]:
        """Calcula la intersección de dos líneas."""
        x1, y1, x2, y2 = line1
        x3, y3, x4, y4 = line2
        
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return None
        
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        
        return (x, y)

    @staticmethod
    def _find_best_quadrilateral(contours: List, min_area: float) -> Optional[np.ndarray]:
        """Encuentra el mejor contorno cuadrilátero."""
        candidates = []
        
        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            
            # Probar diferentes valores de epsilon para aproximación
            for eps_mult in [0.02, 0.03, 0.04, 0.05]:
                approx = cv2.approxPolyDP(cnt, eps_mult * peri, True)
                
                if len(approx) == 4:
                    area = cv2.contourArea(approx)
                    if area > min_area:
                        # Verificar convexidad
                        if cv2.isContourConvex(approx):
                            candidates.append((approx, area))
                    break
        
        if not candidates:
            return None
        
        # Ordenar por área y devolver el más grande
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    @staticmethod
    def _validate_quadrilateral(corners: List[Tuple[int, int]], width: int, height: int, min_area: float) -> bool:
        """Valida que el cuadrilátero detectado sea razonable."""
        if len(corners) != 4:
            return False
        
        pts = np.array(corners, dtype=np.float32)
        
        # Verificar área
        area = cv2.contourArea(pts)
        if area < min_area:
            return False
        
        # Verificar que no sea demasiado estrecho (ratio de aspecto)
        rect = cv2.minAreaRect(pts)
        w, h = rect[1]
        if w == 0 or h == 0:
            return False
        
        aspect_ratio = max(w, h) / min(w, h)
        if aspect_ratio > 10:  # Muy estrecho
            return False
        
        # Verificar que los puntos estén dentro de la imagen
        for x, y in corners:
            if x < 0 or x >= width or y < 0 or y >= height:
                return False
        
        return True

    # ---------- ORDENAR ESQUINAS ----------

    @staticmethod
    def order_points(pts: List[Tuple[int, int]]):
        pts = np.array(pts)

        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)

        tl = pts[np.argmin(s)]
        br = pts[np.argmax(s)]
        tr = pts[np.argmin(diff)]
        bl = pts[np.argmax(diff)]

        # Convertir a tipos nativos de Python para serialización JSON
        return [
            (int(tl[0]), int(tl[1])),
            (int(tr[0]), int(tr[1])),
            (int(br[0]), int(br[1])),
            (int(bl[0]), int(bl[1]))
        ]

    # ---------- TRANSFORMACIÓN DE PERSPECTIVA ----------

    @staticmethod
    def perspective_transform(image: np.ndarray, pts: List[Tuple[int, int]]) -> np.ndarray:
        (tl, tr, br, bl) = pts

        widthA = np.linalg.norm(np.array(br) - np.array(bl))
        widthB = np.linalg.norm(np.array(tr) - np.array(tl))
        maxW = int(max(widthA, widthB))

        heightA = np.linalg.norm(np.array(tr) - np.array(br))
        heightB = np.linalg.norm(np.array(tl) - np.array(bl))
        maxH = int(max(heightA, heightB))

        dst = np.array([
            [0, 0],
            [maxW - 1, 0],
            [maxW - 1, maxH - 1],
            [0, maxH - 1]
        ], dtype="float32")

        src = np.array(pts, dtype="float32")

        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(image, M, (maxW, maxH))

        return warped

    # ---------- EFECTO ESCÁNER ----------

    @staticmethod
    def enhance_for_scan(image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(
            blur, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )
        return thresh
