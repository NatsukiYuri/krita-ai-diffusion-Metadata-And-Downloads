from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any
from PyQt5.QtCore import QObject, QByteArray
from PyQt5.QtGui import QImageReader
from PyQt5.QtWidgets import QMessageBox

from .api import InpaintMode, FillMode
from .image import ImageCollection
from .model import Model, InpaintContext
from .custom_workflow import CustomWorkspace
from .control import ControlLayer, ControlLayerList
from .region import RootRegion, Region
from .jobs import Job, JobKind, JobParams, JobQueue, JobState
from .style import Style, Styles
from .properties import serialize, deserialize
from .settings import settings
from .localization import translate as _
from .util import client_logger as log, encode_json

# Version of the persistence format, increment when there are breaking changes
version = 1


@dataclass
class RecentlyUsedSync:
    """Stores the most recently used parameters for various settings across all models.
    This is used to initialize new models with the last used parameters if they are
    created from scratch (not opening an existing .kra with stored settings).
    """

    style: str = ""
    batch_count: int = 1
    translation_enabled: bool = True
    inpaint_mode: str = "automatic"
    inpaint_fill: str = "neutral"
    inpaint_use_model: bool = True
    inpaint_use_prompt_focus: bool = False
    inpaint_context: str = "automatic"
    upscale_model: str = ""

    @staticmethod
    def from_settings():
        try:
            return RecentlyUsedSync(**settings.document_defaults)
        except Exception as e:
            log.warning(f"Failed to load default document settings: {type(e)} {e}")
            return RecentlyUsedSync()

    def track(self, model: Model):
        try:
            if _find_annotation(model.document, "ui.json") is None:
                model.style = Styles.list().find(self.style) or Styles.list().default
                model.batch_count = self.batch_count
                model.translation_enabled = self.translation_enabled
                model.inpaint.mode = InpaintMode[self.inpaint_mode]
                model.inpaint.fill = FillMode[self.inpaint_fill]
                model.inpaint.use_inpaint = self.inpaint_use_model
                model.inpaint.use_prompt_focus = self.inpaint_use_prompt_focus
                model.upscale.upscaler = self.upscale_model
                if self.inpaint_context != InpaintContext.layer_bounds.name:
                    model.inpaint.context = InpaintContext[self.inpaint_context]
        except Exception as e:
            log.warning(f"Failed to apply default settings to new document: {type(e)} {e}")

        model.style_changed.connect(self._set("style"))
        model.batch_count_changed.connect(self._set("batch_count"))
        model.translation_enabled_changed.connect(self._set("translation_enabled"))
        model.inpaint.mode_changed.connect(self._set("inpaint_mode"))
        model.inpaint.fill_changed.connect(self._set("inpaint_fill"))
        model.inpaint.use_inpaint_changed.connect(self._set("inpaint_use_model"))
        model.inpaint.use_prompt_focus_changed.connect(self._set("inpaint_use_prompt_focus"))
        model.inpaint.context_changed.connect(self._set("inpaint_context"))
        model.upscale.upscaler_changed.connect(self._set("upscale_model"))

    def _set(self, key):
        def setter(value):
            if isinstance(value, Style):
                value = value.filename
            if isinstance(value, Enum):
                value = value.name
            setattr(self, key, value)
            self._save()

        return setter

    def _save(self):
        settings.document_defaults = asdict(self)
        settings.save()


@dataclass
class _HistoryResult:
    id: str
    slot: int  # annotation slot where images are stored
    offsets: list[int]  # offsets in bytes for result images
    params: JobParams
    kind: JobKind = JobKind.diffusion
    in_use: dict[int, bool] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict[str, Any]):
        data["params"] = JobParams.from_dict(data["params"])
        data["kind"] = JobKind[data.get("kind", "diffusion")]
        data["in_use"] = {int(k): v for k, v in data.get("in_use", {}).items()}
        return _HistoryResult(**data)


class ModelSync:
    """Synchronizes the model with the document's annotations."""

    _model: Model
    _history: list[_HistoryResult]
    _memory_used: dict[int, int]  # slot -> memory used for images in bytes
    _slot_index = 0

    def __init__(self, model: Model):
        self._model = model
        self._history = []
        self._memory_used = {}
        if state_bytes := _find_annotation(model.document, "ui.json"):
            try:
                self._load(model, state_bytes.data())
            except Exception as e:
                msg = _("Failed to load state from") + f" {model.document.filename}: {e}"
                log.exception(msg)
                QMessageBox.warning(None, "AI Diffusion Plugin", msg)
        self._track(model)

    def _save(self):
        model = self._model
        state = _serialize(model)
        state["version"] = version
        state["preview_layer"] = model.preview_layer_id
        state["inpaint"] = _serialize(model.inpaint)
        state["upscale"] = _serialize(model.upscale)
        state["live"] = _serialize(model.live)
        state["animation"] = _serialize(model.animation)
        state["custom"] = _serialize_custom(model.custom)
        state["history"] = [asdict(h) for h in self._history]
        state["root"] = _serialize(model.regions)
        state["control"] = [_serialize(c) for c in model.regions.control]
        state["regions"] = []
        for region in model.regions:
            state["regions"].append(_serialize(region))
            state["regions"][-1]["control"] = [_serialize(c) for c in region.control]
        state_str = json.dumps(state, indent=2, default=encode_json)
        state_bytes = QByteArray(state_str.encode("utf-8"))
        model.document.annotate("ui.json", state_bytes)

    def _load(self, model: Model, state_bytes: bytes):
        state = json.loads(state_bytes.decode("utf-8"))
        model.try_set_preview_layer(state.get("preview_layer", ""))
        _deserialize(model, state)
        _deserialize(model.inpaint, state.get("inpaint", {}))
        _deserialize(model.upscale, state.get("upscale", {}))
        _deserialize(model.live, state.get("live", {}))
        _deserialize(model.animation, state.get("animation", {}))
        _deserialize_custom(model.custom, state.get("custom", {}), model.name)
        _deserialize(model.regions, state.get("root", {}))
        for control_state in state.get("control", []):
            _deserialize(model.regions.control.emplace(), control_state)
        for region_state in state.get("regions", []):
            region = model.regions.emplace()
            _deserialize(region, region_state)
            for control_state in region_state.get("control", []):
                _deserialize(region.control.emplace(), control_state)

        for result in state.get("history", []):
            item = _HistoryResult.from_dict(result)
            if images_bytes := _find_annotation(model.document, f"result{item.slot}.webp"):
                job = model.jobs.add_job(Job(item.id, item.kind, item.params))
                job.in_use = item.in_use
                results = ImageCollection.from_bytes(images_bytes, item.offsets)
                model.jobs.set_results(job, results)
                model.jobs.notify_finished(job)
                self._history.append(item)
                self._memory_used[item.slot] = images_bytes.size()
                self._slot_index = max(self._slot_index, item.slot + 1)

    def _track(self, model: Model):
        model.modified.connect(self._save)
        model.inpaint.modified.connect(self._save)
        model.upscale.modified.connect(self._save)
        model.live.modified.connect(self._save)
        model.animation.modified.connect(self._save)
        model.custom.modified.connect(self._save)
        model.jobs.job_finished.connect(self._save_results)
        model.jobs.job_discarded.connect(self._remove_results)
        model.jobs.result_discarded.connect(self._remove_image)
        model.jobs.result_used.connect(self._save)
        model.jobs.selection_changed.connect(self._save)
        self._track_regions(model.regions)

    def _track_control(self, control: ControlLayer):
        self._save()
        control.modified.connect(self._save)

    def _track_control_layers(self, control_layers: ControlLayerList):
        control_layers.added.connect(self._track_control)
        control_layers.removed.connect(self._save)
        for control in control_layers:
            self._track_control(control)

    def _track_region(self, region: Region):
        region.modified.connect(self._save)
        self._track_control_layers(region.control)

    def _track_regions(self, root_region: RootRegion):
        root_region.added.connect(self._track_region)
        root_region.removed.connect(self._save)
        root_region.modified.connect(self._save)
        self._track_control_layers(root_region.control)
        for region in root_region:
            self._track_region(region)

    def _save_results(self, job: Job):
        if job.kind in [JobKind.diffusion, JobKind.animation, JobKind.upscaling] and len(job.results) > 0:
            slot = self._slot_index
            self._slot_index += 1
            image_data, image_offsets = job.results.to_bytes()
            self._model.document.annotate(f"result{slot}.webp", image_data)
            self._history.append(
                _HistoryResult(job.id or "", slot, image_offsets, job.params, job.kind, job.in_use)
            )
            self._memory_used[slot] = image_data.size()
            self._prune()
            self._save()
            
            # Auto-save generated images if enabled
            if settings.auto_save_generated:
                self._auto_save_images(job)

    def _remove_results(self, job: Job):
        index = next((i for i, h in enumerate(self._history) if h.id == job.id), None)
        if index is not None:
            item = self._history.pop(index)
            self._model.document.remove_annotation(f"result{item.slot}.webp")
            self._memory_used.pop(item.slot, None)
        self._save()

    def _remove_image(self, item: JobQueue.Item):
        if history := next((h for h in self._history if h.id == item.job), None):
            if job := self._model.jobs.find(item.job):
                image_data, history.offsets = job.results.to_bytes()
                self._model.document.annotate(f"result{history.slot}.webp", image_data)
                self._memory_used[history.slot] = image_data.size()
                self._save()

    @property
    def memory_used(self):
        return sum(self._memory_used.values())

    def _prune(self):
        limit = settings.history_storage * 1024 * 1024
        used = self.memory_used
        while used > limit and len(self._history) > 0:
            slot = self._history.pop(0).slot
            self._model.document.remove_annotation(f"result{slot}.webp")
            used -= self._memory_used.pop(slot, 0)

    def _auto_save_images(self, job):
        from pathlib import Path
        import os
        from datetime import datetime
        
        # Debug: afficher le nombre d'images dans le batch
        log.info(f"Auto-save: job has {len(job.results)} images")
        
        # Dossier de base configuré par l'utilisateur
        base_folder = Path(settings.auto_save_folder)
        base_folder.mkdir(parents=True, exist_ok=True)
        
        # Nom du fichier Krita (sans extension)
        doc_filename = self._model.document.filename
        if doc_filename:
            doc_name = Path(doc_filename).stem
        else:
            doc_name = "document_non_sauvegarde"
        
        # Créer le sous-dossier pour ce fichier Krita
        doc_folder = base_folder / doc_name
        doc_folder.mkdir(exist_ok=True)
        
        # Déterminer le type d'image selon le type de job
        if job.kind is JobKind.upscaling:
            image_type = "Upscale"
        else:
            # Déterminer le type d'image (générée ou raffinée)
            is_refined = hasattr(job.params, 'strength') and job.params.strength < 1.0
            image_type = "Refine" if is_refined else "ImgGenerate"
        
        # Créer le sous-dossier pour le type d'image
        type_folder = doc_folder / image_type
        type_folder.mkdir(exist_ok=True)
        
        # Debug: afficher les détails du job
        log.info(f"Auto-save: saving to {type_folder}, type={image_type}, job_kind={job.kind}, strength={getattr(job.params, 'strength', 'N/A')}")
        
        for i, img in enumerate(job.results):
            # Nom de fichier : prompt, date, index, etc.
            prompt = getattr(job.params, 'name', 'image')
            prompt = str(prompt).replace(' ', '_')[:50]
            
            # Timestamp unique pour chaque image (ajouter des millisecondes)
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]  # Inclure millisecondes
            
            # Ajouter le type dans le nom de fichier
            filename = f"{prompt}_{timestamp}_{image_type}_{i}.png"
            path = type_folder / filename
            
            # Debug: afficher chaque image sauvegardée
            log.info(f"Auto-save: saving image {i+1}/{len(job.results)} to {path}")
            
            try:
                # Préparer toutes les métadonnées dans un dictionnaire
                all_metadata = {}
                
                # Métadonnées de base
                all_metadata["prompt"] = _clean_metadata_value(job.params.prompt)
                all_metadata["negative_prompt"] = _clean_metadata_value(job.params.metadata.get("negative_prompt", ""))
                all_metadata["seed"] = job.params.seed
                all_metadata["strength"] = job.params.strength
                all_metadata["style"] = _clean_metadata_value(job.params.metadata.get("style", ""))
                all_metadata["checkpoint"] = _clean_metadata_value(job.params.metadata.get("checkpoint", ""))
                all_metadata["sampler"] = _clean_metadata_value(job.params.metadata.get("sampler", ""))
                
                # Métadonnées de génération
                all_metadata["generation_type"] = image_type
                all_metadata["job_kind"] = job.kind.name
                all_metadata["timestamp"] = job.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                all_metadata["batch_index"] = i
                all_metadata["total_images"] = len(job.results)
                
                # Métadonnées techniques
                if "loras" in job.params.metadata:
                    loras = job.params.metadata["loras"]
                    if isinstance(loras, list):
                        lora_list = []
                        for lora in loras:
                            if isinstance(lora, dict) and lora.get("enabled", True):
                                lora_list.append({
                                    "name": _clean_metadata_value(lora.get("name", "Unknown")),
                                    "strength": lora.get("strength", 1.0)
                                })
                        all_metadata["loras"] = lora_list
                    else:
                        all_metadata["loras"] = str(loras)
                
                # Ajouter toutes les autres métadonnées du job
                for key, value in job.params.metadata.items():
                    if key not in ["prompt", "negative_prompt", "style", "checkpoint", "sampler", "loras"]:
                        # Nettoyer et limiter la taille des valeurs
                        clean_value = _clean_metadata_value(str(value))
                        if len(clean_value) > 500:  # Limiter à 500 caractères
                            clean_value = clean_value[:497] + "..."
                        all_metadata[f"param_{key}"] = clean_value
                
                # Convertir en JSON compact et nettoyer
                import json
                metadata_json = json.dumps(all_metadata, ensure_ascii=False, separators=(',', ':'))
                
                # Limiter la taille totale du JSON (max 4KB)
                if len(metadata_json) > 4000:
                    # Tronquer en gardant les métadonnées essentielles
                    essential_metadata = {
                        "prompt": all_metadata.get("prompt", ""),
                        "seed": all_metadata.get("seed", 0),
                        "strength": all_metadata.get("strength", 1.0),
                        "generation_type": all_metadata.get("generation_type", ""),
                        "timestamp": all_metadata.get("timestamp", ""),
                        "truncated": True
                    }
                    metadata_json = json.dumps(essential_metadata, ensure_ascii=False, separators=(',', ':'))
                
                # Créer le dictionnaire de métadonnées pour QImageWriter
                metadata = {"metadata": metadata_json}
                
                # Sauvegarder avec métadonnées
                img.save(str(path), metadata=metadata)
                log.info(f"Auto-save: successfully saved {path} with JSON metadata ({len(metadata_json)} chars)")
            except Exception as e:
                log.warning(f"Auto-save failed for {path}: {e}")


def _serialize(obj: QObject):
    def converter(obj):
        if isinstance(obj, Style):
            return obj.filename
        return obj

    return serialize(obj, converter)


def _deserialize(obj: QObject, data: dict[str, Any]):
    def converter(type, value):
        if type is Style:
            style = Styles.list().find(value)
            return style or Styles.list().default
        return value

    if "unblur_strength" in data and not isinstance(data["unblur_strength"], float):
        data["unblur_strength"] = 0.5

    return deserialize(obj, data, converter)


def _serialize_custom(custom: CustomWorkspace):
    result = _serialize(custom)
    result["workflow_id"] = custom.workflow_id
    result["graph"] = custom.graph.root if custom.graph else None
    return result


def _deserialize_custom(custom: CustomWorkspace, data: dict[str, Any], document_name: str):
    _deserialize(custom, data)
    workflow_id = data.get("workflow_id", "")
    graph = data.get("graph", None)
    if workflow_id and graph:
        custom.set_graph(workflow_id, graph, document_name)


def _find_annotation(document, name: str):
    if result := document.find_annotation(name):
        return result
    without_ext = name.rsplit(".", 1)[0]
    if result := document.find_annotation(without_ext):
        return result
    return None


def import_prompt_from_file(model: Model):
    exts = (".png", ".jpg", ".jpeg", ".webp")
    filename = model.document.filename
    if model.regions.positive == "" and model.regions.negative == "" and filename.endswith(exts):
        try:
            reader = QImageReader(filename)
            # A1111
            if text := reader.text("parameters"):
                if "Negative prompt:" in text:
                    positive, negative = text.split("Negative prompt:", 1)
                    model.regions.positive = positive.strip()
                    model.regions.negative = negative.split("Steps:", 1)[0].strip()
            # ComfyUI
            elif text := reader.text("prompt"):
                prompt: dict[str, dict] = json.loads(text)
                for node in prompt.values():
                    if node["class_type"] in _comfy_sampler_types:
                        inputs = node["inputs"]
                        model.regions.positive = _find_text_prompt(prompt, inputs["positive"][0])
                        model.regions.negative = _find_text_prompt(prompt, inputs["negative"][0])

        except Exception as e:
            log.warning(f"Failed to read PNG metadata from {filename}: {e}")


_comfy_sampler_types = ["KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"]


def _find_text_prompt(workflow: dict[str, dict], node_key: str):
    if node := workflow.get(node_key):
        if node["class_type"] == "CLIPTextEncode":
            text = node.get("inputs", {}).get("text", "")
            return text if isinstance(text, str) else ""
        for input in node.get("inputs", {}).values():
            if isinstance(input, list):
                return _find_text_prompt(workflow, input[0])
    return ""


def _clean_metadata_value(value: str) -> str:
    """Nettoie une valeur de métadonnée en supprimant les caractères parasites et de contrôle"""
    if not isinstance(value, str):
        value = str(value)
    
    # Supprimer les caractères de contrôle et les caractères parasites
    import re
    # Supprimer les caractères de contrôle (0x00-0x1F) sauf tab et newline
    value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
    # Supprimer les caractères Unicode problématiques
    value = re.sub(r'[\uFFFD\uFFFE\uFFFF]', '', value)
    # Nettoyer les espaces en début et fin
    value = value.strip()
    
    return value


def _auto_save_images_from_history(model):
    """Télécharge toutes les images de l'historique actuel"""
    from pathlib import Path
    from datetime import datetime
    
    if not settings.auto_save_generated:
        return 0
    
    # Dossier de base configuré par l'utilisateur
    base_folder = Path(settings.auto_save_folder)
    base_folder.mkdir(parents=True, exist_ok=True)
    
    # Nom du fichier Krita (sans extension)
    doc_filename = model.document.filename
    if doc_filename:
        doc_name = Path(doc_filename).stem
    else:
        doc_name = "document_non_sauvegarde"
    
    # Créer le sous-dossier pour ce fichier Krita
    doc_folder = base_folder / doc_name
    doc_folder.mkdir(exist_ok=True)
    
    total_saved = 0
    
    # Parcourir tous les jobs finis
    for job in model.jobs._entries:
        if job.state != JobState.finished or len(job.results) == 0:
            continue
            
        # Déterminer le type d'image selon le type de job
        if job.kind is JobKind.upscaling:
            image_type = "Upscale"
        else:
            # Déterminer le type d'image (générée ou raffinée)
            is_refined = hasattr(job.params, 'strength') and job.params.strength < 1.0
            image_type = "Refine" if is_refined else "ImgGenerate"
        
        # Créer le sous-dossier pour le type d'image
        type_folder = doc_folder / image_type
        type_folder.mkdir(exist_ok=True)
        
        for i, img in enumerate(job.results):
            # Nom de fichier : prompt, date, index, etc.
            prompt = getattr(job.params, 'name', 'image')
            prompt = str(prompt).replace(' ', '_')[:50]
            
            # Timestamp unique pour chaque image (ajouter des millisecondes)
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]  # Inclure millisecondes
            
            # Ajouter le type dans le nom de fichier
            filename = f"{prompt}_{timestamp}_{image_type}_{i}.png"
            path = type_folder / filename
            
            try:
                # Préparer toutes les métadonnées dans un dictionnaire
                all_metadata = {}
                
                # Métadonnées de base
                all_metadata["prompt"] = _clean_metadata_value(job.params.prompt)
                all_metadata["negative_prompt"] = _clean_metadata_value(job.params.metadata.get("negative_prompt", ""))
                all_metadata["seed"] = job.params.seed
                all_metadata["strength"] = job.params.strength
                all_metadata["style"] = _clean_metadata_value(job.params.metadata.get("style", ""))
                all_metadata["checkpoint"] = _clean_metadata_value(job.params.metadata.get("checkpoint", ""))
                all_metadata["sampler"] = _clean_metadata_value(job.params.metadata.get("sampler", ""))
                
                # Métadonnées de génération
                all_metadata["generation_type"] = image_type
                all_metadata["job_kind"] = job.kind.name
                all_metadata["timestamp"] = job.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                all_metadata["batch_index"] = i
                all_metadata["total_images"] = len(job.results)
                
                # Métadonnées techniques
                if "loras" in job.params.metadata:
                    loras = job.params.metadata["loras"]
                    if isinstance(loras, list):
                        lora_list = []
                        for lora in loras:
                            if isinstance(lora, dict) and lora.get("enabled", True):
                                lora_list.append({
                                    "name": _clean_metadata_value(lora.get("name", "Unknown")),
                                    "strength": lora.get("strength", 1.0)
                                })
                        all_metadata["loras"] = lora_list
                    else:
                        all_metadata["loras"] = str(loras)
                
                # Ajouter toutes les autres métadonnées du job
                for key, value in job.params.metadata.items():
                    if key not in ["prompt", "negative_prompt", "style", "checkpoint", "sampler", "loras"]:
                        # Nettoyer et limiter la taille des valeurs
                        clean_value = _clean_metadata_value(str(value))
                        if len(clean_value) > 500:  # Limiter à 500 caractères
                            clean_value = clean_value[:497] + "..."
                        all_metadata[f"param_{key}"] = clean_value
                
                # Convertir en JSON compact et nettoyer
                import json
                metadata_json = json.dumps(all_metadata, ensure_ascii=False, separators=(',', ':'))
                
                # Limiter la taille totale du JSON (max 4KB)
                if len(metadata_json) > 4000:
                    # Tronquer en gardant les métadonnées essentielles
                    essential_metadata = {
                        "prompt": all_metadata.get("prompt", ""),
                        "seed": all_metadata.get("seed", 0),
                        "strength": all_metadata.get("strength", 1.0),
                        "generation_type": all_metadata.get("generation_type", ""),
                        "timestamp": all_metadata.get("timestamp", ""),
                        "truncated": True
                    }
                    metadata_json = json.dumps(essential_metadata, ensure_ascii=False, separators=(',', ':'))
                
                # Créer le dictionnaire de métadonnées pour QImageWriter
                metadata = {"metadata": metadata_json}
                
                # Sauvegarder avec métadonnées
                img.save(str(path), metadata=metadata)
                total_saved += 1
                log.info(f"History save: successfully saved {path} with JSON metadata ({len(metadata_json)} chars)")
            except Exception as e:
                log.warning(f"History save failed for {path}: {e}")
    
    return total_saved
