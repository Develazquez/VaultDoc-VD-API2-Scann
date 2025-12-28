from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class FileBase(BaseModel):
    departamento: str
    folio: str
    id_folder: int
    id_uploader: int

class FileCreate(FileBase):
    """Modelo para crear un archivo escaneado"""
    pass

class FileResponse(BaseModel):

    id: int
    departamento: str
    nombre: str
    tamano: int
    fecha: str
    folio: str
    extension: str
    id_folder: int
    id_uploader: int
    directorio: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    class Config:
        from_attributes = True

class ScanRequest(BaseModel):
    
    folio: str = Field(..., description="Folio del documento")
    id_folder: int = Field(..., gt=0, description="ID de la carpeta destino")
    id_uploader: int = Field(..., gt=0, description="ID del usuario que sube")
    departamento: str = Field(..., description="Departamento del documento")
    
    @validator('departamento')
    def validate_departamento(cls, v):
        departamentos_validos = [
            'Dirección General',
            'Área Técnica',
            'Comisaria',
            'Coordinación Juridica',
            'Gerencia Administrativa',
            'Gerencia Operativa',
            'Departamento de Finanzas',
            'Departamento de Planeación',
            'Departamento de Sistema Eléctrico',
            'Departamento de Sistema Hidrosánitario y Aire Acondicionado',
            'Departamento de Mantenimiento General',
            'Departamento de Voz y Datos',
            'Departamento de Seguridad e Higiene'
        ]
        if v not in departamentos_validos:
            raise ValueError(f'Departamento no válido. Debe ser uno de: {", ".join(departamentos_validos)}')
        return v

class ScanResponse(BaseModel):
    
    message: str
    file_id: Optional[int] = None
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    success: bool