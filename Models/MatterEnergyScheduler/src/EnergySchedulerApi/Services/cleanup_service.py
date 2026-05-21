import time
import logging
from pathlib import Path
from .database_service import DatabaseService

logger = logging.getLogger(__name__)

class CleanupService:
    """Service to prevent data buildup on local devices by removing old cache and database records"""
    
    def __init__(self, db_service: DatabaseService, retention_days: int = 7):
        self.db_service = db_service
        self.retention_days = retention_days
        self.cache_dirs = [
            Path("data/price_cache"),
            Path("data/solar_cache")
        ]

    def run_cleanup(self):
        """Perform all cleanup tasks"""
        logger.info("Starting scheduled data cleanup...")
        try:
            self._cleanup_cache_files()
            self._cleanup_database()
            logger.info("Data cleanup completed.")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    def _cleanup_cache_files(self):
        """Remove old JSON cache files"""
        # Calculate cutoff time in seconds
        cutoff = time.time() - (self.retention_days * 86400)
        
        for cache_dir in self.cache_dirs:
            if not cache_dir.exists():
                continue
                
            files_removed = 0
            for file in cache_dir.glob("*.json"):
                if file.is_file() and file.stat().st_mtime < cutoff:
                    try:
                        file.unlink()
                        files_removed += 1
                    except Exception as e:
                        logger.error(f"Failed to delete old cache file {file}: {e}")
            
            if files_removed > 0:
                logger.info(f"Removed {files_removed} old cache files from {cache_dir}")

    def _cleanup_database(self):
        """Remove old completed/failed schedules from database"""
        self.db_service.cleanup_old_schedules(days=self.retention_days)
