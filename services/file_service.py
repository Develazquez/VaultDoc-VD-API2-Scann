import requests
from datetime import datetime
from typing import Optional, Dict, Any
from core.config import settings
from core.database import db
import logging

logger = logging.getLogger(__name__)

class FileService:
    
    def __init__(self):
        self.go_api_url = settings.GO_API_URL
        self.timeout = settings.GO_API_TIMEOUT
    
    def generate_file_name(self, folio: str, departamento: str) -> str:
        """Genera el nombre del archivo según el formato SOTCH"""
        abreviaciones = {
            "Dirección General": "DG",
            "Área Técnica": "AT",
            "Comisaria": "C",
            "Coordinación Juridica": "CJ",
            "Gerencia Administrativa": "GA",
            "Gerencia Operativa": "GO",
            "Departamento de Finanzas": "DF",
            "Departamento de Planeación": "DP",
            "Departamento de Sistema Eléctrico": "DSE",
            "Departamento de Sistema Hidrosánitario y Aire Acondicionado": "DSHAA",
            "Departamento de Mantenimiento General": "DMG",
            "Departamento de Voz y Datos": "DVD",
            "Departamento de Seguridad e Higiene": "DSH"
        }
        
        abreviacion = abreviaciones.get(departamento, "UNK")
        year = datetime.now().year
        
        return f"SOTCH-{abreviacion}-{folio}-{year}"
    
    def get_folder_info(self, folder_id: int, departamento: str) -> Optional[Dict[str, Any]]:
        """Obtiene información de la carpeta desde la BD"""
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = """
                        SELECT id, name, departamento, id_uploader
                        FROM folders
                        WHERE id = %s AND departamento = %s
                    """
                    cursor.execute(query, (folder_id, departamento))
                    result = cursor.fetchone()
                    
                    if result:
                        return {
                            "id": result[0],
                            "name": result[1],
                            "departamento": result[2],
                            "id_uploader": result[3]
                        }
                    return None
        except Exception as e:
            logger.error(f"Error al obtener información de carpeta: {e}")
            raise
    
    def check_file_exists(self, folio: str) -> bool:
        """Verifica si ya existe un archivo con el mismo folio"""
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = "SELECT COUNT(*) FROM files WHERE folio = %s"
                    cursor.execute(query, (folio,))
                    count = cursor.fetchone()[0]
                    return count > 0
        except Exception as e:
            logger.error(f"Error al verificar existencia de archivo: {e}")
            raise
    
    def create_file_record(
        self,
        departamento: str,
        nombre: str,
        tamano: int,
        fecha: str,
        folio: str,
        extension: str,
        id_folder: int,
        id_uploader: int,
        directorio: str
    ) -> int:
        """Crea un registro de archivo en la base de datos"""
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO files 
                        (departamento, nombre, tamano, fecha, folio, extension, 
                         id_folder, id_uploader, directorio)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """
                    cursor.execute(query, (
                        departamento, nombre, tamano, fecha, folio, extension,
                        id_folder, id_uploader, directorio
                    ))
                    file_id = cursor.fetchone()[0]
                    conn.commit()
                    return file_id
        except Exception as e:
            logger.error(f"Error al crear registro de archivo: {e}")
            raise
    
    def grant_automatic_permissions(self, file_id: int, uploader_id: int, departamento: str):
        """Otorga permisos automáticos al archivo"""
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Obtener usuarios con permisos
                    users_to_grant = [uploader_id]
                    
                    # Jefes del departamento (id_rol = 2)
                    cursor.execute(
                        "SELECT id FROM usuarios WHERE id_rol = 2 AND departamento = %s",
                        (departamento,)
                    )
                    dept_bosses = [row[0] for row in cursor.fetchall()]
                    users_to_grant.extend(dept_bosses)
                    
                    # Administradores (id_rol = 3)
                    cursor.execute("SELECT id FROM usuarios WHERE id_rol = 3")
                    admins = [row[0] for row in cursor.fetchall()]
                    users_to_grant.extend(admins)
                    
                    # Eliminar duplicados
                    unique_users = list(set(users_to_grant))
                    
                    # Otorgar permisos
                    for user_id in unique_users:
                        # Permiso de visualización
                        cursor.execute(
                            """
                            INSERT INTO view_files (id_file, id_user)
                            VALUES (%s, %s)
                            ON CONFLICT (id_file, id_user) DO NOTHING
                            """,
                            (file_id, user_id)
                        )
                        
                        # Permiso de edición
                        cursor.execute(
                            """
                            INSERT INTO change_files (id_file, id_user)
                            VALUES (%s, %s)
                            ON CONFLICT (id_file, id_user) DO NOTHING
                            """,
                            (file_id, user_id)
                        )
                    
                    conn.commit()
                    logger.info(f"Permisos otorgados a {len(unique_users)} usuarios para archivo {file_id}")
        except Exception as e:
            logger.error(f"Error al otorgar permisos automáticos: {e}")
            raise
    
    def upload_to_nextcloud(
        self,
        file_content: bytes,
        file_name: str,
        folder_path: str
    ) -> str:

        try:
            files = {
                'file': (file_name, file_content, 'image/png')
            }
            
            # Nota: Revisas endpoint de nextcloud para ra subida de archovos
            
            # Por ahora, construimos la ruta relativa como lo hace go
            relative_path = f"{folder_path}/{file_name}"
            
            logger.info(f"Archivo preparado para Nextcloud: {relative_path}")
            return relative_path
            
        except Exception as e:
            logger.error(f"Error al subir archivo a Nextcloud: {e}")
            raise