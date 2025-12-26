import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from core.config import settings
import logging

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    _connection_pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance
    
    def _initialize_pool(self):
        
        try:
            self._connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,  # minconn
                20,  # maxconn
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                database=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD
            )
            logger.info("Pool de conexiones inicializado correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar pool de conexiones: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = self._connection_pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error en conexión: {e}")
            raise
        finally:
            if conn:
                self._connection_pool.putconn(conn)
    
    def close_all_connections(self):
        """Cierra todas las conexiones del pool"""
        if self._connection_pool:
            self._connection_pool.closeall()
            logger.info("Todas las conexiones cerradas")


db = Database()