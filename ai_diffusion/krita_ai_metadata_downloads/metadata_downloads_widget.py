"""
Metadata and Downloads Settings Widget
Combines metadata display and automatic download settings in a single tab
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QMessageBox, QFrame, QGroupBox, QGridLayout
)
from PyQt5.QtCore import Qt

from ..settings import settings
from ..localization import _
from ..root import root
from .auto_save import auto_save_all_history_images
from .utils import StyleManager


class MetadataDownloadsWidget(QWidget):
    """
    Widget for metadata and downloads settings
    Combines metadata display and automatic download functionality
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Metadata Display Section
        metadata_group = self._create_metadata_section()
        layout.addWidget(metadata_group)
        
        # Downloads Section
        downloads_group = self._create_downloads_section()
        layout.addWidget(downloads_group)
        
        # Actions Section
        actions_group = self._create_actions_section()
        layout.addWidget(actions_group)
        
        layout.addStretch()
    
    def _create_metadata_section(self):
        """Create metadata display settings section"""
        group = QGroupBox(_("Metadata Display"))
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # Enable metadata interface
        from ..ui.settings_widgets import SwitchSetting
        self.show_metadata_interface = SwitchSetting(
            settings._show_metadata_interface, 
            self
        )
        layout.addWidget(self.show_metadata_interface)
        
        # Font size setting
        from ..ui.settings_widgets import SpinBoxSetting
        font_layout = QHBoxLayout()
        font_label = QLabel(_("Font Size:"))
        font_label.setFixedWidth(80)
        font_layout.addWidget(font_label)
        
        self.metadata_font_size = SpinBoxSetting(
            settings._metadata_font_size, 
            self, 
            8, 
            20
        )
        font_layout.addWidget(self.metadata_font_size)
        font_layout.addStretch()
        layout.addLayout(font_layout)
        
        # Widget height setting
        height_layout = QHBoxLayout()
        height_label = QLabel(_("Widget Height:"))
        height_label.setFixedWidth(80)
        height_layout.addWidget(height_label)
        
        self.metadata_widget_height = SpinBoxSetting(
            settings._metadata_widget_height, 
            self, 
            100, 
            500
        )
        height_layout.addWidget(self.metadata_widget_height)
        height_layout.addStretch()
        layout.addLayout(height_layout)
        
        return group
    
    def _create_downloads_section(self):
        """Create automatic downloads settings section"""
        group = QGroupBox(_("Automatic Downloads"))
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # Enable automatic downloads
        from ..ui.settings_widgets import SwitchSetting, LineEditSetting
        self.auto_save_switch = SwitchSetting(
            settings._auto_save_generated, 
            (_("Enabled"), _("Disabled")), 
            self
        )
        layout.addWidget(self.auto_save_switch)
        
        # Download folder setting
        folder_layout = QHBoxLayout()
        folder_label = QLabel(_("Download Folder:"))
        folder_label.setFixedWidth(100)
        folder_layout.addWidget(folder_label)
        
        self.auto_save_folder = LineEditSetting(
            settings._auto_save_folder, 
            self
        )
        folder_layout.addWidget(self.auto_save_folder)
        folder_layout.addStretch()
        layout.addLayout(folder_layout)
        
        return group
    
    def _create_actions_section(self):
        """Create action buttons section"""
        group = QGroupBox(_("Actions"))
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # Download all images button
        self._download_all_button = QPushButton(_("Download All Images from History"))
        self._download_all_button.setStyleSheet(StyleManager.get_button_style())
        self._download_all_button.clicked.connect(self._download_all_images)
        layout.addWidget(self._download_all_button)
        
        # Reset settings button
        self._reset_button = QPushButton(_("Reset to Defaults"))
        self._reset_button.setStyleSheet(StyleManager.get_button_style())
        self._reset_button.clicked.connect(self._reset_settings)
        layout.addWidget(self._reset_button)
        
        return group
    
    def _download_all_images(self):
        """Downloads all images from current history"""
        if not root.active_model:
            QMessageBox.warning(self, _("Error"), _("No active model found"))
            return
            
        if not settings.auto_save_folder:
            QMessageBox.warning(self, _("Error"), _("Please configure a download folder first"))
            return
            
        try:
            count = auto_save_all_history_images(root.active_model)
            QMessageBox.information(self, _("Success"), 
                _("{} images have been downloaded to the configured folder").format(count))
        except Exception as e:
            QMessageBox.critical(self, _("Error"), 
                _("Error during download: {}").format(str(e)))
    
    def _reset_settings(self):
        """Reset settings to defaults"""
        reply = QMessageBox.question(
            self, 
            _("Confirmation"), 
            _("Are you sure you want to reset all metadata and download settings to defaults?"),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Reset metadata settings
            settings.show_metadata_interface = True
            settings.metadata_font_size = 12
            settings.metadata_widget_height = 280
            
            # Reset download settings
            settings.auto_save_generated = False
            settings.auto_save_folder = "generated_images"
            
            settings.save()
            QMessageBox.information(self, _("Success"), _("Settings reset to defaults")) 