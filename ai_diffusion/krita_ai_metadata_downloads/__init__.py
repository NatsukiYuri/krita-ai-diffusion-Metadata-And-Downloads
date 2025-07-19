"""
Module for custom features of the AI Diffusion extension
Clear separation between base code and custom additions
"""

from .metadata_panel import MetadataPanel
from .auto_save import AutoSaveManager, auto_save_job_images, auto_save_all_history_images
from .settings_extensions import AutoSaveSettingsWidget, MetadataSettingsWidget
from .metadata_downloads_widget import MetadataDownloadsWidget
from .integration import CustomFeaturesIntegration, custom_integration
from .ui_widgets import (
    CustomFeaturesTabWidget, AdvancedSettingsWidget, CustomFeaturesStatusWidget,
    QuickConfigDialog, FeatureToggleWidget, CustomFeaturesToolbar,
    create_metadata_panel, create_auto_save_settings, create_custom_features_tabs,
    create_status_widget, create_toolbar
)
from .utils import MetadataFormatter, ImageTypeDetector, StyleManager

__version__ = "1.0.0"
__author__ = "Custom Developer"

__all__ = [
    # Classes principales
    'MetadataPanel',
    'AutoSaveManager', 
    'CustomFeaturesIntegration',
    
    # Widgets d'interface de base
    'AutoSaveSettingsWidget',
    'MetadataSettingsWidget',
    'MetadataDownloadsWidget',
    
    # Widgets UI personnalisés
    'CustomFeaturesTabWidget',
    'AdvancedSettingsWidget', 
    'CustomFeaturesStatusWidget',
    'QuickConfigDialog',
    'FeatureToggleWidget',
    'CustomFeaturesToolbar',
    
    # Classes utilitaires
    'MetadataFormatter',
    'ImageTypeDetector', 
    'StyleManager',
    
    # Fonctions utilitaires
    'auto_save_job_images',
    'auto_save_all_history_images',
    
    # Factory functions pour UI
    'create_metadata_panel',
    'create_auto_save_settings', 
    'create_custom_features_tabs',
    'create_status_widget',
    'create_toolbar',
    
    # Instances globales
    'custom_integration',
    
    # Version et métadonnées
    '__version__',
    '__author__'
] 