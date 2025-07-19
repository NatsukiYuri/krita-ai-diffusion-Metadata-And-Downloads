"""
Module for automatic saving of generated images
Custom feature to automatically save images according to their type
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from ..model import Model, Job, JobKind
from ..settings import settings
from ..util import client_logger as log
from ..localization import _
from .utils import MetadataFormatter, ImageTypeDetector


class AutoSaveManager:
    """
    Manager for automatic saving of generated images
    Custom feature to organize images by type
    """
    
    def __init__(self, model: Model):
        self._model = model
    
    def save_job_images(self, job: Job) -> int:
        """
        Automatically saves images from a completed job
        Returns the number of saved images
        """
        if not settings.auto_save_generated:
            return 0
        
        if not job.results:
            return 0
        
        # Debug: display number of images in batch
        log.info(f"Auto-save: job has {len(job.results)} images")
        
        # Base folder configured by user
        base_folder = Path(settings.auto_save_folder)
        base_folder.mkdir(parents=True, exist_ok=True)
        
        # Krita filename (without extension)
        doc_filename = self._model.document.filename
        if doc_filename:
            doc_name = Path(doc_filename).stem
        else:
            doc_name = "unsaved_document"
        
        # Create subfolder for this Krita file
        doc_folder = base_folder / doc_name
        doc_folder.mkdir(exist_ok=True)
        
        # Determine image type based on job type
        image_type = self._get_image_type(job)
        
        # Create subfolder for image type
        type_folder = doc_folder / image_type
        type_folder.mkdir(exist_ok=True)
        
        # Debug: display job details
        log.info(f"Auto-save: saving to {type_folder}, type={image_type}, job_kind={job.kind}, strength={getattr(job.params, 'strength', 'N/A')}")
        
        saved_count = 0
        for i, img in enumerate(job.results):
            try:
                # Filename: prompt, date, index, etc.
                prompt = getattr(job.params, 'name', 'image')
                prompt = str(prompt).replace(' ', '_')[:50]
                
                # Unique timestamp for each image (include milliseconds)
                timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]  # Include milliseconds
                
                # Add type to filename
                filename = f"{prompt}_{timestamp}_{image_type}_{i}.png"
                path = type_folder / filename
                
                # Debug: display each saved image
                log.info(f"Auto-save: saving image {i+1}/{len(job.results)} to {path}")
                
                # Prepare all metadata in a dictionary
                all_metadata = MetadataFormatter.prepare_for_save(job, i, image_type)
                
                # Create JSON metadata
                metadata_json = json.dumps(all_metadata, ensure_ascii=False, separators=(',', ':'))
                
                # Limit total JSON size (max 4KB)
                if len(metadata_json) > 4000:
                    # Truncate keeping essential metadata
                    essential_metadata = {
                        "prompt": all_metadata.get("prompt", ""),
                        "seed": all_metadata.get("seed", 0),
                        "strength": all_metadata.get("strength", 1.0),
                        "generation_type": all_metadata.get("generation_type", ""),
                        "timestamp": all_metadata.get("timestamp", ""),
                        "truncated": True
                    }
                    metadata_json = json.dumps(essential_metadata, ensure_ascii=False, separators=(',', ':'))
                
                # Create metadata dictionary for QImageWriter
                metadata = {"metadata": metadata_json}
                
                # Save with metadata
                img.save(str(path), metadata=metadata)
                log.info(f"Auto-save: successfully saved {path} with JSON metadata ({len(metadata_json)} chars)")
                saved_count += 1
                
            except Exception as e:
                log.warning(f"Auto-save failed for {path}: {e}")
        
        return saved_count
    
    def _get_image_type(self, job: Job) -> str:
        """Determines image type based on job"""
        return ImageTypeDetector.get_image_type(job)
    
    def save_all_history_images(self) -> int:
        """
        Saves all images from current history
        Returns total number of saved images
        """
        if not settings.auto_save_generated:
            return 0
        
        # Base folder configured by user
        base_folder = Path(settings.auto_save_folder)
        base_folder.mkdir(parents=True, exist_ok=True)
        
        # Krita filename (without extension)
        doc_filename = self._model.document.filename
        if doc_filename:
            doc_name = Path(doc_filename).stem
        else:
            doc_name = "unsaved_document"
        
        # Create subfolder for this Krita file
        doc_folder = base_folder / doc_name
        doc_folder.mkdir(exist_ok=True)
        
        total_saved = 0
        
        # Process all finished jobs
        for job in self._model.jobs._entries:
            if job.results and job.kind in [JobKind.diffusion, JobKind.animation, JobKind.upscaling]:
                try:
                    saved_count = self.save_job_images(job)
                    total_saved += saved_count
                    log.info(f"Auto-save: saved {saved_count} images from job {job.id}")
                except Exception as e:
                    log.warning(f"Auto-save: failed to save job {job.id}: {e}")
        
        log.info(f"Auto-save: total images saved from history: {total_saved}")
        return total_saved


def create_auto_save_manager(model: Model) -> AutoSaveManager:
    """Factory function to create an automatic save manager"""
    return AutoSaveManager(model)


def auto_save_job_images(model: Model, job: Job) -> int:
    """
    Utility function to automatically save images from a job
    Used by the existing persistence system
    """
    manager = AutoSaveManager(model)
    return manager.save_job_images(job)


def auto_save_all_history_images(model: Model) -> int:
    """
    Utility function to save all images from history
    Used by the settings interface
    """
    manager = AutoSaveManager(model)
    return manager.save_all_history_images() 