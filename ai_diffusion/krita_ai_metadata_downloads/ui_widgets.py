"""
Custom UI widgets for custom features
All user interface components specific to custom features
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QMenu, QAction, QDialog, QMessageBox, QFileDialog,
    QSpinBox, QCheckBox, QFrame, QTabWidget, QScrollArea
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QGuiApplication, QPixmap, QImage, QImageReader

from .metadata_panel import MetadataPanel
from .settings_extensions import AutoSaveSettingsWidget, MetadataSettingsWidget
from .utils import StyleManager
from ..ui.theme import theme
from ..localization import _


class CustomFeaturesTabWidget(QTabWidget):
    """
    Tab widget to group all custom features
    Can be integrated into main settings
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_tabs()
    
    def setup_tabs(self):
        """Configure custom feature tabs"""
        # Metadata and Downloads tab
        from .metadata_downloads_widget import MetadataDownloadsWidget
        self.metadata_downloads_tab = MetadataDownloadsWidget()
        self.addTab(self.metadata_downloads_tab, _("Metadata and Downloads"))
        
        # Advanced configuration tab
        self.advanced_tab = AdvancedSettingsWidget()
        self.addTab(self.advanced_tab, _("Advanced Configuration"))


class AdvancedSettingsWidget(QWidget):
    """
    Widget for advanced custom feature settings
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Configuration section
        config_group = QFrame()
        config_group.setFrameStyle(QFrame.StyledPanel)
        config_layout = QVBoxLayout(config_group)
        
        config_title = QLabel(_("Feature Configuration"))
        config_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        config_layout.addWidget(config_title)
        
        # Debug options
        self.debug_checkbox = QCheckBox(_("Debug mode for custom features"))
        config_layout.addWidget(self.debug_checkbox)
        
        # Performance options
        self.performance_checkbox = QCheckBox(_("Performance optimizations"))
        config_layout.addWidget(self.performance_checkbox)
        
        layout.addWidget(config_group)
        
        # Maintenance section
        maintenance_group = QFrame()
        maintenance_group.setFrameStyle(QFrame.StyledPanel)
        maintenance_layout = QVBoxLayout(maintenance_group)
        
        maintenance_title = QLabel(_("Maintenance"))
        maintenance_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        maintenance_layout.addWidget(maintenance_title)
        
        # Maintenance buttons
        buttons_layout = QHBoxLayout()
        
        self.reset_button = QPushButton(_("Reset Settings"))
        self.reset_button.clicked.connect(self.reset_settings)
        buttons_layout.addWidget(self.reset_button)
        
        self.export_button = QPushButton(_("Export Configuration"))
        self.export_button.clicked.connect(self.export_config)
        buttons_layout.addWidget(self.export_button)
        
        self.import_button = QPushButton(_("Import Configuration"))
        self.import_button.clicked.connect(self.import_config)
        buttons_layout.addWidget(self.import_button)
        
        maintenance_layout.addLayout(buttons_layout)
        layout.addWidget(maintenance_group)
        
        layout.addStretch()
    
    def reset_settings(self):
        """Reset custom feature settings"""
        reply = QMessageBox.question(
            self, 
            _("Confirmation"), 
            _("Are you sure you want to reset all custom feature settings?"),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            from ..settings import settings
            # Reset settings
            settings.auto_save_generated = False
            settings.auto_save_folder = "generated_images"
            settings.show_metadata_interface = True
            settings.metadata_font_size = 12
            settings.metadata_widget_height = 280
            settings.save()
            QMessageBox.information(self, _("Success"), _("Settings reset"))
    
    def export_config(self):
        """Export configuration"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            _("Export Configuration"),
            "",
            _("JSON Files (*.json)")
        )
        
        if file_path:
            from ..settings import settings
            import json
            from pathlib import Path
            
            config_data = {
                "auto_save_generated": settings.auto_save_generated,
                "auto_save_folder": settings.auto_save_folder,
                "show_metadata_interface": settings.show_metadata_interface,
                "metadata_font_size": settings.metadata_font_size,
                "metadata_widget_height": settings.metadata_widget_height
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(self, _("Success"), _("Configuration exported"))
    
    def import_config(self):
        """Import configuration"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            _("Import Configuration"),
            "",
            _("JSON Files (*.json)")
        )
        
        if file_path:
            from ..settings import settings
            import json
            from pathlib import Path
            
            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Apply settings
            if "auto_save_generated" in config_data:
                settings.auto_save_generated = config_data["auto_save_generated"]
            if "auto_save_folder" in config_data:
                settings.auto_save_folder = config_data["auto_save_folder"]
            if "show_metadata_interface" in config_data:
                settings.show_metadata_interface = config_data["show_metadata_interface"]
            if "metadata_font_size" in config_data:
                settings.metadata_font_size = config_data["metadata_font_size"]
            if "metadata_widget_height" in config_data:
                settings.metadata_widget_height = config_data["metadata_widget_height"]
            
            settings.save()
            QMessageBox.information(self, _("Success"), _("Configuration imported"))


class CustomFeaturesStatusWidget(QWidget):
    """
    Widget to display custom feature status
    Can be integrated into status bar or as floating widget
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.update_status()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Status icon
        self.status_icon = QLabel("🔧")
        self.status_icon.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.status_icon)
        
        # Status text
        self.status_text = QLabel(_("Custom Features"))
        self.status_text.setStyleSheet("color: #e0e0e0; font-size: 11px;")
        layout.addWidget(self.status_text)
        
        # Quick configuration button
        self.config_button = QPushButton(_("Config"))
        self.config_button.setFixedSize(50, 20)
        self.config_button.setStyleSheet(StyleManager.get_button_style())
        self.config_button.clicked.connect(self.show_quick_config)
        layout.addWidget(self.config_button)
    
    def update_status(self):
        """Updates status display"""
        from ..settings import settings
        
        # Check enabled features via settings
        enabled_features = []
        if settings.auto_save_generated:
            enabled_features.append("Automatic Save")
        if settings.show_metadata_interface:
            enabled_features.append("Metadata Panel")
        
        if enabled_features:
            self.status_icon.setText("✅")
            self.status_text.setText(f"{len(enabled_features)} active features")
        else:
            self.status_icon.setText("⚠️")
            self.status_text.setText(_("No active features"))
    
    def show_quick_config(self):
        """Shows quick configuration"""
        dialog = QuickConfigDialog(self)
        dialog.exec_()


class QuickConfigDialog(QDialog):
    """
    Quick configuration dialog for custom features
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Quick Configuration - Custom Features"))
        self.setFixedSize(400, 300)
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QVBoxLayout(self)
        
        # Feature list based on settings
        from ..settings import settings
        
        # Automatic save feature
        auto_save_widget = FeatureToggleWidget("auto_save", {
            "name": "Automatic Save",
            "enabled": settings.auto_save_generated
        })
        layout.addWidget(auto_save_widget)
        
        # Metadata panel feature
        metadata_widget = FeatureToggleWidget("metadata_panel", {
            "name": "Metadata Panel", 
            "enabled": settings.show_metadata_interface
        })
        layout.addWidget(metadata_widget)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.ok_button = QPushButton(_("OK"))
        self.ok_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.ok_button)
        
        self.cancel_button = QPushButton(_("Cancel"))
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        
        layout.addLayout(buttons_layout)


class FeatureToggleWidget(QWidget):
    """
    Widget to enable/disable a feature
    """
    
    def __init__(self, feature_name: str, feature_config, parent=None):
        super().__init__(parent)
        self.feature_name = feature_name
        self.feature_config = feature_config
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Checkbox to enable/disable
        self.enable_checkbox = QCheckBox(self.feature_config["name"])
        self.enable_checkbox.setChecked(self.feature_config["enabled"])
        self.enable_checkbox.toggled.connect(self.toggle_feature)
        layout.addWidget(self.enable_checkbox)
        
        layout.addStretch()
    
    def toggle_feature(self, enabled: bool):
        """Enable or disable the feature"""
        from ..settings import settings
        
        if self.feature_name == "auto_save":
            settings.auto_save_generated = enabled
        elif self.feature_name == "metadata_panel":
            settings.show_metadata_interface = enabled
        
        settings.save()


class CustomFeaturesToolbar(QWidget):
    """
    Toolbar for custom features
    Can be integrated into main interface
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        
        # Button to show metadata
        self.metadata_button = QPushButton(_("Metadata"))
        self.metadata_button.setFixedSize(80, 24)
        self.metadata_button.clicked.connect(self.show_metadata_panel)
        layout.addWidget(self.metadata_button)
        
        # Button for manual save
        self.save_button = QPushButton(_("Save"))
        self.save_button.setFixedSize(80, 24)
        self.save_button.clicked.connect(self.manual_save)
        layout.addWidget(self.save_button)
        
        # Configuration button
        self.config_button = QPushButton(_("Config"))
        self.config_button.setFixedSize(60, 24)
        self.config_button.clicked.connect(self.show_config)
        layout.addWidget(self.config_button)
        
        layout.addStretch()
    
    def show_metadata_panel(self):
        """Shows the metadata panel"""
        # This method will be connected to the main system
        pass
    
    def manual_save(self):
        """Launches a manual save"""
        from .auto_save import auto_save_all_history_images
        from ..root import root
        
        if root.active_model:
            count = auto_save_all_history_images(root.active_model)
            QMessageBox.information(self, _("Success"), 
                _("{} images have been saved").format(count))
    
    def show_config(self):
        """Shows the configuration"""
        dialog = CustomFeaturesTabWidget(self)
        dialog.exec_()


# Utility functions for UI integration
def create_metadata_panel(parent=None):
    """Factory function to create a metadata panel"""
    return MetadataPanel(parent)


def create_auto_save_settings(parent=None):
    """Factory function to create automatic save settings (legacy)"""
    return AutoSaveSettingsWidget(parent)


def create_metadata_downloads_settings(parent=None):
    """Factory function to create unified metadata and downloads settings"""
    from .metadata_downloads_widget import MetadataDownloadsWidget
    return MetadataDownloadsWidget(parent)


def create_custom_features_tabs(parent=None):
    """Factory function to create custom feature tabs"""
    return CustomFeaturesTabWidget(parent)


def create_status_widget(parent=None):
    """Factory function to create status widget"""
    return CustomFeaturesStatusWidget(parent)


def create_toolbar(parent=None):
    """Factory function to create toolbar"""
    return CustomFeaturesToolbar(parent) 