"""
Servicio para realizar OCR (Reconocimiento Óptico de Caracteres) en documentos
"""

import pytesseract
from PIL import Image
import cv2
import numpy as np
from typing import Dict, List
import logging
import io

logger = logging.getLogger(__name__)


class OCRService:
    """
    Servicio para extraer texto de imágenes usando Tesseract OCR
    """
    
    def __init__(self):
        # Configurar idiomas (español e inglés)
        self.languages = 'spa+eng'
        
        # Configuración de Tesseract
        self.config = '--oem 3 --psm 6'  # OEM 3 = Default, PSM 6 = Assume uniform block of text
        
    def extract_text_from_bytes(self, image_bytes: bytes) -> Dict[str, any]:
        """
        Extrae texto de una imagen en bytes
        
        Args:
            image_bytes: Bytes de la imagen
            
        Returns:
            Dict con texto extraído, confianza y detalles
        """
        try:
            # Decodificar imagen desde bytes
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                raise ValueError("No se pudo decodificar la imagen")
            
            # Preprocesar imagen para mejor OCR
            processed_image = self._preprocess_for_ocr(image)
            
            # Convertir a PIL Image
            pil_image = Image.fromarray(processed_image)
            
            # Extraer texto con Tesseract
            logger.info("Ejecutando OCR con Tesseract...")
            text = pytesseract.image_to_string(
                pil_image,
                lang=self.languages,
                config=self.config
            )
            
            # Obtener datos detallados (incluye confianza)
            data = pytesseract.image_to_data(
                pil_image,
                lang=self.languages,
                config=self.config,
                output_type=pytesseract.Output.DICT
            )
            
            # Calcular confianza promedio
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            # Contar palabras detectadas
            words = [word for word in data['text'] if word.strip()]
            word_count = len(words)
            
            # Limpiar texto
            cleaned_text = self._clean_text(text)
            
            logger.info(f"OCR completado: {word_count} palabras, confianza: {avg_confidence:.1f}%")
            
            return {
                'text': cleaned_text,
                'raw_text': text,
                'word_count': word_count,
                'confidence': round(avg_confidence, 2),
                'has_text': bool(cleaned_text.strip()),
                'languages': self.languages
            }
            
        except Exception as e:
            logger.error(f"Error al extraer texto con OCR: {e}")
            return {
                'text': '',
                'raw_text': '',
                'word_count': 0,
                'confidence': 0,
                'has_text': False,
                'error': str(e)
            }
    
    def extract_text_from_image_array(self, image: np.ndarray) -> Dict[str, any]:
        """
        Extrae texto de una imagen en formato numpy array
        
        Args:
            image: Imagen en formato numpy array (OpenCV)
            
        Returns:
            Dict con texto extraído y detalles
        """
        try:
            # Preprocesar imagen
            processed_image = self._preprocess_for_ocr(image)
            
            # Convertir a PIL Image
            pil_image = Image.fromarray(processed_image)
            
            # Extraer texto
            text = pytesseract.image_to_string(
                pil_image,
                lang=self.languages,
                config=self.config
            )
            
            # Obtener datos detallados
            data = pytesseract.image_to_data(
                pil_image,
                lang=self.languages,
                config=self.config,
                output_type=pytesseract.Output.DICT
            )
            
            # Calcular estadísticas
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            words = [word for word in data['text'] if word.strip()]
            
            cleaned_text = self._clean_text(text)
            
            return {
                'text': cleaned_text,
                'raw_text': text,
                'word_count': len(words),
                'confidence': round(avg_confidence, 2),
                'has_text': bool(cleaned_text.strip())
            }
            
        except Exception as e:
            logger.error(f"Error al extraer texto: {e}")
            return {
                'text': '',
                'raw_text': '',
                'word_count': 0,
                'confidence': 0,
                'has_text': False,
                'error': str(e)
            }
    
    def _preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocesa la imagen para mejorar resultados de OCR
        
        Args:
            image: Imagen en formato numpy array
            
        Returns:
            Imagen procesada
        """
        # Convertir a escala de grises
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Aplicar umbral adaptativo
        # Esto mejora el contraste entre texto y fondo
        processed = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2
        )
        
        # Reducir ruido
        processed = cv2.fastNlMeansDenoising(processed, None, 10, 7, 21)
        
        # Dilatar ligeramente para unir caracteres fragmentados
        kernel = np.ones((1, 1), np.uint8)
        processed = cv2.dilate(processed, kernel, iterations=1)
        
        return processed
    
    def _clean_text(self, text: str) -> str:
        """
        Limpia el texto extraído eliminando espacios extras y líneas vacías
        
        Args:
            text: Texto a limpiar
            
        Returns:
            Texto limpio
        """
        # Dividir en líneas
        lines = text.split('\n')
        
        # Eliminar líneas vacías y espacios extras
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        
        # Unir líneas
        cleaned_text = '\n'.join(cleaned_lines)
        
        return cleaned_text
    
    def extract_structured_data(self, image: np.ndarray) -> Dict[str, List[Dict]]:
        """
        Extrae datos estructurados de la imagen (palabras con posiciones)
        
        Args:
            image: Imagen en formato numpy array
            
        Returns:
            Dict con palabras y sus posiciones en la imagen
        """
        try:
            # Preprocesar
            processed = self._preprocess_for_ocr(image)
            pil_image = Image.fromarray(processed)
            
            # Obtener datos estructurados
            data = pytesseract.image_to_data(
                pil_image,
                lang=self.languages,
                config=self.config,
                output_type=pytesseract.Output.DICT
            )
            
            # Organizar por palabras
            words_data = []
            for i in range(len(data['text'])):
                if data['text'][i].strip() and int(data['conf'][i]) > 0:
                    words_data.append({
                        'text': data['text'][i],
                        'confidence': int(data['conf'][i]),
                        'position': {
                            'x': data['left'][i],
                            'y': data['top'][i],
                            'width': data['width'][i],
                            'height': data['height'][i]
                        },
                        'block': data['block_num'][i],
                        'paragraph': data['par_num'][i],
                        'line': data['line_num'][i]
                    })
            
            return {
                'words': words_data,
                'total_words': len(words_data)
            }
            
        except Exception as e:
            logger.error(f"Error al extraer datos estructurados: {e}")
            return {'words': [], 'total_words': 0, 'error': str(e)}
    
    @staticmethod
    def is_tesseract_available() -> bool:
        """
        Verifica si Tesseract está instalado y disponible
        
        Returns:
            True si está disponible, False en caso contrario
        """
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_available_languages() -> List[str]:
        """
        Obtiene la lista de idiomas disponibles en Tesseract
        
        Returns:
            Lista de códigos de idiomas disponibles
        """
        try:
            langs = pytesseract.get_languages()
            return langs
        except Exception as e:
            logger.error(f"Error al obtener idiomas disponibles: {e}")
            return []