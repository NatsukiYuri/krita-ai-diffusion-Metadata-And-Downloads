"""
Configuration des fonctionnalités personnalisées
Gestion des versions, paramètres et compatibilité
"""

from dataclasses import dataclass
from typing import Dict, Any, List
from pathlib import Path


@dataclass
class CustomFeatureConfig:
    """Configuration d'une fonctionnalité personnalisée"""
    name: str
    version: str
    description: str
    enabled: bool = True
    dependencies: List[str] = None
    settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.settings is None:
            self.settings = {}


class CustomFeaturesConfig:
    """Configuration globale des fonctionnalités personnalisées"""
    
    VERSION = "1.0.0"
    AUTHOR = "Custom Developer"
    DESCRIPTION = "Fonctionnalités personnalisées pour l'extension AI Diffusion"
    
    def __init__(self):
        self.features = {
            "metadata_panel": CustomFeatureConfig(
                name="Panneau de Métadonnées",
                version="1.0.0",
                description="Affiche et permet de copier les métadonnées des images générées",
                enabled=True,
                dependencies=[],
                settings={
                    "show_interface": True,
                    "font_size": 12,
                    "widget_height": 280,
                    "enable_external_images": True
                }
            ),
            "auto_save": CustomFeatureConfig(
                name="Sauvegarde Automatique",
                version="1.0.0",
                description="Sauvegarde automatiquement les images générées selon leur type",
                enabled=True,
                dependencies=[],
                settings={
                    "enabled": False,
                    "folder": "generated_images",
                    "organize_by_type": True,
                    "include_metadata": True,
                    "max_metadata_size": 4000
                }
            )
        }
    
    def get_feature(self, feature_name: str) -> CustomFeatureConfig:
        """Retourne la configuration d'une fonctionnalité"""
        return self.features.get(feature_name)
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Vérifie si une fonctionnalité est activée"""
        feature = self.get_feature(feature_name)
        return feature.enabled if feature else False
    
    def get_feature_setting(self, feature_name: str, setting_name: str, default=None):
        """Retourne un paramètre d'une fonctionnalité"""
        feature = self.get_feature(feature_name)
        if feature and feature.settings:
            return feature.settings.get(setting_name, default)
        return default
    
    def set_feature_setting(self, feature_name: str, setting_name: str, value):
        """Définit un paramètre d'une fonctionnalité"""
        feature = self.get_feature(feature_name)
        if feature:
            feature.settings[setting_name] = value
    
    def enable_feature(self, feature_name: str):
        """Active une fonctionnalité"""
        feature = self.get_feature(feature_name)
        if feature:
            feature.enabled = True
    
    def disable_feature(self, feature_name: str):
        """Désactive une fonctionnalité"""
        feature = self.get_feature(feature_name)
        if feature:
            feature.enabled = False
    
    def get_enabled_features(self) -> List[str]:
        """Retourne la liste des fonctionnalités activées"""
        return [name for name, feature in self.features.items() if feature.enabled]
    
    def get_all_features(self) -> Dict[str, CustomFeatureConfig]:
        """Retourne toutes les fonctionnalités"""
        return self.features.copy()
    
    def add_feature(self, feature_name: str, config: CustomFeatureConfig):
        """Ajoute une nouvelle fonctionnalité"""
        self.features[feature_name] = config
    
    def remove_feature(self, feature_name: str):
        """Supprime une fonctionnalité"""
        if feature_name in self.features:
            del self.features[feature_name]
    
    def check_compatibility(self, base_version: str) -> Dict[str, bool]:
        """
        Vérifie la compatibilité avec la version de base
        Retourne un dictionnaire {feature_name: compatible}
        """
        compatibility = {}
        
        # Version minimale requise pour les fonctionnalités personnalisées
        min_base_version = "0.1.0"  # À ajuster selon les besoins
        
        for feature_name, feature in self.features.items():
            # Vérification basique de compatibilité
            # Ici vous pouvez ajouter une logique plus sophistiquée
            compatibility[feature_name] = True
        
        return compatibility
    
    def export_config(self, file_path: Path):
        """Exporte la configuration vers un fichier JSON"""
        import json
        
        config_data = {
            "version": self.VERSION,
            "author": self.AUTHOR,
            "description": self.DESCRIPTION,
            "features": {}
        }
        
        for name, feature in self.features.items():
            config_data["features"][name] = {
                "name": feature.name,
                "version": feature.version,
                "description": feature.description,
                "enabled": feature.enabled,
                "dependencies": feature.dependencies,
                "settings": feature.settings
            }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
    
    def import_config(self, file_path: Path):
        """Importe la configuration depuis un fichier JSON"""
        import json
        
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Mettre à jour la version et les informations générales
        if "version" in config_data:
            self.VERSION = config_data["version"]
        if "author" in config_data:
            self.AUTHOR = config_data["author"]
        if "description" in config_data:
            self.DESCRIPTION = config_data["description"]
        
        # Mettre à jour les fonctionnalités
        if "features" in config_data:
            for name, feature_data in config_data["features"].items():
                config = CustomFeatureConfig(
                    name=feature_data.get("name", name),
                    version=feature_data.get("version", "1.0.0"),
                    description=feature_data.get("description", ""),
                    enabled=feature_data.get("enabled", True),
                    dependencies=feature_data.get("dependencies", []),
                    settings=feature_data.get("settings", {})
                )
                self.features[name] = config


# Instance globale de configuration
custom_config = CustomFeaturesConfig()


def get_config() -> CustomFeaturesConfig:
    """Retourne l'instance globale de configuration"""
    return custom_config


def load_config_from_file(file_path: Path):
    """Charge la configuration depuis un fichier"""
    if file_path.exists():
        custom_config.import_config(file_path)


def save_config_to_file(file_path: Path):
    """Sauvegarde la configuration vers un fichier"""
    custom_config.export_config(file_path)


# Configuration par défaut
DEFAULT_CONFIG_FILE = Path(__file__).parent / "custom_config.json"

# Charger la configuration par défaut si elle existe
if DEFAULT_CONFIG_FILE.exists():
    load_config_from_file(DEFAULT_CONFIG_FILE)
else:
    # Créer le fichier de configuration par défaut
    save_config_to_file(DEFAULT_CONFIG_FILE) 