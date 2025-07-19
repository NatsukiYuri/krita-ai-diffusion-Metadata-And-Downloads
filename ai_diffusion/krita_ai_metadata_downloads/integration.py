"""
Integration module for custom features
Connects custom features to base code in a modular way
"""

from typing import Optional, Callable
from PyQt5.QtWidgets import QWidget

from .metadata_panel import MetadataPanel
from .auto_save import AutoSaveManager, auto_save_job_images
from .settings_extensions import AutoSaveSettingsWidget, MetadataSettingsWidget


class CustomFeaturesIntegration:
    """
    Integration class to manage the addition of custom features
    Allows easy activation/deactivation of features
    """
    
    def __init__(self):
        self._metadata_panel: Optional[MetadataPanel] = None
        self._auto_save_manager: Optional[AutoSaveManager] = None
        self._integration_hooks = {}
    
    def setup_metadata_panel(self, parent_widget: QWidget) -> MetadataPanel:
        """
        Configure and return the metadata panel
        To be called from the main generation widget
        """
        if not self._metadata_panel:
            self._metadata_panel = MetadataPanel(parent_widget)
        
        return self._metadata_panel
    
    def setup_auto_save(self, model) -> AutoSaveManager:
        """
        Configure and return the automatic save manager
        To be called during model initialization
        """
        if not self._auto_save_manager:
            self._auto_save_manager = AutoSaveManager(model)
        
        return self._auto_save_manager
    
    def get_auto_save_settings_widget(self, parent=None) -> AutoSaveSettingsWidget:
        """Returns the automatic save settings widget (legacy)"""
        return AutoSaveSettingsWidget(parent)
    
    def get_metadata_settings_widget(self, parent=None) -> MetadataSettingsWidget:
        """Returns the metadata display settings widget (legacy)"""
        return MetadataSettingsWidget(parent)
    
    def get_metadata_downloads_widget(self, parent=None) -> 'MetadataDownloadsWidget':
        """Returns the unified metadata and downloads settings widget"""
        from .metadata_downloads_widget import MetadataDownloadsWidget
        return MetadataDownloadsWidget(parent)
    
    def register_auto_save_hook(self, hook_function: Callable):
        """
        Register a hook function for automatic saving
        This function will be called after each image generation
        """
        self._integration_hooks['auto_save'] = hook_function
    
    def register_metadata_hook(self, hook_function: Callable):
        """
        Register a hook function for metadata display
        This function will be called when selecting images
        """
        self._integration_hooks['metadata'] = hook_function
    
    def call_auto_save_hook(self, model, job):
        """Calls the automatic save hook"""
        if 'auto_save' in self._integration_hooks:
            try:
                self._integration_hooks['auto_save'](model, job)
            except Exception as e:
                from ..util import client_logger as log
                log.warning(f"Auto-save hook failed: {e}")
    
    def call_metadata_hook(self, model, job):
        """Calls the metadata display hook"""
        if 'metadata' in self._integration_hooks:
            try:
                self._integration_hooks['metadata'](model, job)
            except Exception as e:
                from ..util import client_logger as log
                log.warning(f"Metadata hook failed: {e}")
    
    def cleanup(self):
        """Cleans up custom feature resources"""
        if self._metadata_panel:
            self._metadata_panel.deleteLater()
            self._metadata_panel = None
        
        self._auto_save_manager = None
        self._integration_hooks.clear()


# Instance globale pour l'intégration
custom_integration = CustomFeaturesIntegration()


def integrate_with_generation_widget(generation_widget, model):
    """
    Utility function to integrate custom features
    into the main generation widget
    """
    from ..settings import settings
    
    # Integrate metadata panel
    if settings.show_metadata_interface:
        metadata_panel = custom_integration.setup_metadata_panel(generation_widget)
        metadata_panel.model = model
        
        # Add panel to generation widget layout
        if hasattr(generation_widget, 'layout'):
            generation_widget.layout().addWidget(metadata_panel)
    
    # Configure automatic saving
    auto_save_manager = custom_integration.setup_auto_save(model)
    
    # Register automatic save hook
    def auto_save_hook(model, job):
        if settings.auto_save_generated and job.results:
            auto_save_job_images(model, job)
    
    custom_integration.register_auto_save_hook(auto_save_hook)
    
    return metadata_panel if settings.show_metadata_interface else None


def integrate_with_settings_dialog(settings_dialog):
    """
    Utility function to integrate custom settings widgets
    into the settings dialog
    """
    # Add unified metadata and downloads tab
    metadata_downloads_widget = custom_integration.get_metadata_downloads_widget()
    settings_dialog.add_tab("Metadata and Downloads", metadata_downloads_widget)


def patch_persistence_module():
    """
    Applies necessary patches to the persistence module
    to integrate automatic saving
    """
    # This function will be called to modify the behavior
    # of the existing persistence.py module
    pass


def patch_generation_widget():
    """
    Applies necessary patches to the generation widget
    to integrate the metadata panel
    """
    # This function will be called to modify the behavior
    # of the existing generation widget
    pass 