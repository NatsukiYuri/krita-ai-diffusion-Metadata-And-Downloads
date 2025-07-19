"""
Settings extensions for custom features
Adds necessary parameters for custom features
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox
from PyQt5.QtCore import QObject

from ..settings import Settings, Setting
from ..localization import _
from ..root import root
from .auto_save import auto_save_all_history_images
from .metadata_downloads_widget import MetadataDownloadsWidget


# Legacy widgets for backward compatibility
class AutoSaveSettingsWidget(QWidget):
    """
    Legacy widget for automatic save settings
    Deprecated: Use MetadataDownloadsWidget instead
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Redirect to new widget
        new_widget = MetadataDownloadsWidget(self)
        layout.addWidget(new_widget)


class MetadataSettingsWidget(QWidget):
    """
    Legacy widget for metadata display settings
    Deprecated: Use MetadataDownloadsWidget instead
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Redirect to new widget
        new_widget = MetadataDownloadsWidget(self)
        layout.addWidget(new_widget)


 