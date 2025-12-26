import requests
from requests.auth import HTTPBasicAuth
import os
from typing import Optional
import logging
from core.config import settings
logger = logging.getLogger(__name__)

class NextcloudClient:
    
    def __init__(self):
        self.base_url = settings.NEXTCLOUD_BASE_URL
        self.username = settings.NEXTCLOUD_USERNAME
        self.password = settings.NEXTCLOUD_PASSWORD
        self.timeout = 120
        
        if not all([self.base_url, self.username, self.password]):
            raise ValueError("Faltan credenciales de Nextcloud en variables de entorno")
    
    def upload_file(self, file_content: bytes, folder_path: str, file_name: str) -> str:
        """
        Sube un archivo a Nextcloud
        Retorna la ruta relativa del archivo
        """
        try:
            # Construir URL
            clean_folder_path = folder_path.strip("/")
            if clean_folder_path:
                file_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{clean_folder_path}/{file_name}"
            else:
                file_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{file_name}"
            
            # Subir archivo
            response = requests.put(
                file_url,
                data=file_content,
                auth=HTTPBasicAuth(self.username, self.password),
                headers={
                    "Content-Type": "application/octet-stream"
                },
                timeout=self.timeout
            )
            
            if response.status_code not in [201, 204]:
                raise Exception(f"Error al subir archivo a Nextcloud (status: {response.status_code}): {response.text}")
            
            relative_path = f"{clean_folder_path}/{file_name}" if clean_folder_path else file_name
            logger.info(f"Archivo subido exitosamente a Nextcloud: {relative_path}")
            return relative_path
            
        except Exception as e:
            logger.error(f"Error al subir archivo a Nextcloud: {e}")
            raise
    
    def file_exists(self, folder_path: str, file_name: str) -> bool:
        """Verifica si un archivo existe en Nextcloud"""
        try:
            clean_folder_path = folder_path.strip("/")
            if clean_folder_path:
                file_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{clean_folder_path}/{file_name}"
            else:
                file_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{file_name}"
            
            response = requests.head(
                file_url,
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.timeout
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error al verificar existencia de archivo: {e}")
            return False
    
    def delete_file(self, folder_path: str, file_name: str) -> bool:
        """Elimina un archivo de Nextcloud"""
        try:
            clean_folder_path = folder_path.strip("/")
            if clean_folder_path:
                file_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{clean_folder_path}/{file_name}"
            else:
                file_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{file_name}"
            
            response = requests.delete(
                file_url,
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.timeout
            )
            
            if response.status_code in [204, 404]:
                return True
            
            logger.warning(f"Error al eliminar archivo (status: {response.status_code})")
            return False
            
        except Exception as e:
            logger.error(f"Error al eliminar archivo: {e}")
            return False

nextcloud_client = NextcloudClient()