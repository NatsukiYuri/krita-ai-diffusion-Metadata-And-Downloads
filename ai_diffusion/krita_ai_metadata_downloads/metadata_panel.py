"""
Module for metadata display panel
Custom feature to display and copy metadata from generated images
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QMenu, QAction, QDialog, QMessageBox, QFileDialog
)
from PyQt5.QtCore import Qt, QByteArray
from PyQt5.QtGui import QGuiApplication, QPixmap, QImage, QImageReader

from ..ui.theme import theme
from ..localization import _
from ..model import Model, Job
from ..root import root
from .utils import MetadataFormatter, StyleManager


class MetadataTextEdit(QTextEdit):
    """Custom QTextEdit for metadata display with quick copy"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            text = self.textCursor().selectedText()
            if text:
                clipboard = QGuiApplication.clipboard()
                clipboard.setText(text)
            event.accept()
            return
        super().keyPressEvent(event)


class MetadataPanel(QWidget):
    """
    Widget to display metadata of selected image
    Custom feature added to the base extension
    """
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._model = root.active_model
        self._model_bindings = []
        
        # Load saved settings
        from ..settings import settings
        self._font_size = settings.metadata_font_size
        self._widget_height = settings.metadata_widget_height
        self._text_height = self._widget_height - 10
        
        # Increase default size if first time
        if self._font_size == 10:  # Default value
            self._font_size = 12
            settings.metadata_font_size = 12
        if self._widget_height == 220:  # Default value
            self._widget_height = 280
            self._text_height = 270
            settings.metadata_widget_height = 280
        
        # Widget configuration
        self.setMaximumHeight(self._widget_height)
        self.setMinimumHeight(100)
        
        self._setup_ui()
        self._setup_connections()
        
        # Default message
        self._metadata_text.setPlainText(_("Select an image to see its metadata"))
    
    def _setup_ui(self):
        """Configure the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        
        # Toolbar for size controls
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)
        
        # Font size label
        font_label = QLabel(_("Size:"), self)
        font_label.setStyleSheet("color: #e0e0e0; font-size: 9px;")
        toolbar_layout.addWidget(font_label)
        
        # Buttons to adjust font size
        self._font_smaller_btn = QPushButton("A-", self)
        self._font_smaller_btn.setFixedSize(24, 20)
        self._font_smaller_btn.setStyleSheet(StyleManager.get_button_style())
        self._font_smaller_btn.clicked.connect(self._decrease_font_size)
        toolbar_layout.addWidget(self._font_smaller_btn)
        
        self._font_larger_btn = QPushButton("A+", self)
        self._font_larger_btn.setFixedSize(24, 20)
        self._font_larger_btn.setStyleSheet(StyleManager.get_button_style())
        self._font_larger_btn.clicked.connect(self._increase_font_size)
        toolbar_layout.addWidget(self._font_larger_btn)
        
        # Height label
        height_label = QLabel(_("Height:"), self)
        height_label.setStyleSheet("color: #e0e0e0; font-size: 9px;")
        toolbar_layout.addWidget(height_label)
        
        # Buttons to adjust height
        self._height_smaller_btn = QPushButton("-", self)
        self._height_smaller_btn.setFixedSize(20, 20)
        self._height_smaller_btn.setStyleSheet(StyleManager.get_button_style())
        self._height_smaller_btn.clicked.connect(self._decrease_height)
        toolbar_layout.addWidget(self._height_smaller_btn)
        
        self._height_larger_btn = QPushButton("+", self)
        self._height_larger_btn.setFixedSize(20, 20)
        self._height_larger_btn.setStyleSheet(StyleManager.get_button_style())
        self._height_larger_btn.clicked.connect(self._increase_height)
        toolbar_layout.addWidget(self._height_larger_btn)
        
        # Flexible space on the right
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)
        
        # Text area for metadata
        self._metadata_text = MetadataTextEdit(self)
        self._metadata_text.setReadOnly(True)
        self._metadata_text.setMaximumHeight(self._text_height)
        self._metadata_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._metadata_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._metadata_text.customContextMenuRequested.connect(self._show_text_context_menu)
        self._update_text_style()
        layout.addWidget(self._metadata_text)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        
        # Button to load an image
        self._load_image_button = QPushButton(_("Load Image"), self)
        self._load_image_button.setFixedSize(80, 20)
        self._load_image_button.setStyleSheet(StyleManager.get_button_style())
        self._load_image_button.clicked.connect(self._load_external_image)
        buttons_layout.addWidget(self._load_image_button)
        
        # Flexible space in the middle
        buttons_layout.addStretch()
        
        # Copy button
        self._copy_button = QPushButton(_("Copy"), self)
        self._copy_button.setFixedSize(60, 20)
        self._copy_button.setStyleSheet(StyleManager.get_button_style())
        self._copy_button.clicked.connect(self._copy_metadata)
        buttons_layout.addWidget(self._copy_button)
        
        layout.addLayout(buttons_layout)
    
    def _setup_connections(self):
        """Configure connections with the model"""
        if self._model:
            self._model_bindings = [
                self._model.jobs.selection_changed.connect(self._update_metadata)
            ]
            self._update_metadata()
    
    @property
    def model(self):
        return self._model
    
    @model.setter
    def model(self, model: Model):
        if self._model != model:
            from ..util import Binding
            Binding.disconnect_all(self._model_bindings)
            self._model = model
            self._setup_connections()
    
    def _update_metadata(self):
        """Updates metadata display based on selection"""
        selection = self._model.jobs.selection
        if not selection:
            self._metadata_text.setPlainText(_("Select an image to see its metadata"))
            return
        
        # Take the first selected image
        job_id, image_index = selection[0]
        job = self._model.jobs.find(job_id)
        
        if not job:
            self._metadata_text.setPlainText(_("Image not found"))
            return
        
        # Format metadata
        metadata_text = MetadataFormatter.format_for_display(job)
        self._metadata_text.setPlainText(metadata_text)
    
    def _update_text_style(self):
        """Updates text style based on font size"""
        self._metadata_text.setStyleSheet(StyleManager.get_text_style(self._font_size))
    
    def _decrease_font_size(self):
        """Decreases font size"""
        if self._font_size > 8:
            self._font_size -= 1
            self._update_text_style()
            # Save parameter
            from ..settings import settings
            settings.metadata_font_size = self._font_size
    
    def _increase_font_size(self):
        """Increases font size"""
        if self._font_size < 20:
            self._font_size += 1
            self._update_text_style()
            # Save parameter
            from ..settings import settings
            settings.metadata_font_size = self._font_size
    
    def _decrease_height(self):
        """Decreases widget height"""
        if self._widget_height > 120:
            self._widget_height -= 20
            self._text_height -= 20
            self.setMaximumHeight(self._widget_height)
            self._metadata_text.setMaximumHeight(self._text_height)
            # Save parameter
            from ..settings import settings
            settings.metadata_widget_height = self._widget_height
    
    def _increase_height(self):
        """Increases widget height"""
        if self._widget_height < 400:
            self._widget_height += 20
            self._text_height += 20
            self.setMaximumHeight(self._widget_height)
            self._metadata_text.setMaximumHeight(self._text_height)
            # Save parameter
            from ..settings import settings
            settings.metadata_widget_height = self._widget_height
    
    def _copy_metadata(self):
        """Copies metadata to clipboard"""
        text = self._metadata_text.toPlainText()
        if text and text != _("Select an image to see its metadata") and text != _("Image not found"):
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
    
    def _show_text_context_menu(self, pos):
        """Shows context menu for metadata text"""
        menu = QMenu(self)
        
        # Copy action
        copy_action = QAction(_("Copy"), self)
        copy_action.triggered.connect(self._copy_selected_text)
        menu.addAction(copy_action)
        
        # Select all action
        select_all_action = QAction(_("Select All"), self)
        select_all_action.triggered.connect(self._select_all_text)
        menu.addAction(select_all_action)
        
        # Prevent propagation to parent widget
        menu.aboutToShow.connect(lambda: self.setFocus())
        menu.exec_(self._metadata_text.mapToGlobal(pos))
    
    def _copy_selected_text(self):
        """Copies selected text"""
        text = self._metadata_text.textCursor().selectedText()
        if text:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
            return True
        return False
    
    def _select_all_text(self):
        """Selects all text"""
        cursor = self._metadata_text.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self._metadata_text.setTextCursor(cursor)
    
    def _load_external_image(self):
        """Loads an external image to display its metadata"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            _("Load an image"),
            "",
            _("Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff)")
        )
        
        if not file_path:
            return
        
        self._show_image_metadata(file_path)
    
    def _show_image_metadata(self, image_path: str):
        """Displays metadata of an external image"""
        from ..util import client_logger as log
        
        # Load image
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            QMessageBox.warning(self, _("Error"), _("Unable to load image"))
            return
        
        # Extract metadata
        metadata = self._extract_image_metadata(image_path)
        
        # Create dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(_("Preview and Metadata"))
        dlg.setMinimumWidth(600)
        dlg.setMinimumHeight(500)
        vbox = QVBoxLayout(dlg)

        # Preview
        preview = QLabel(dlg)
        scaled_pixmap = pixmap.scaledToWidth(300, Qt.SmoothTransformation)
        preview.setPixmap(scaled_pixmap)
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet("border: 1px solid #555; border-radius: 3px; padding: 8px;")
        vbox.addWidget(preview)

        # Metadata
        meta_text = QTextEdit(dlg)
        meta_text.setReadOnly(True)
        meta_text.setMaximumHeight(350)
        meta_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        meta_text.setStyleSheet(StyleManager.get_text_style(12))
        
        if metadata:
            formatted_lines = []
            has_ai_metadata = False
            
            # Check first if we have our JSON metadata
            if "AI_METADATA_JSON" in metadata:
                has_ai_metadata = True
                ai_metadata = metadata["AI_METADATA_JSON"]
                
                formatted_lines.append("=== AI METADATA (Krita Extension) ===")
                formatted_lines.append("")
                
                # Display basic metadata
                if "prompt" in ai_metadata:
                    formatted_lines.append("PROMPT:")
                    formatted_lines.append(ai_metadata["prompt"])
                    formatted_lines.append("")
                
                if "negative_prompt" in ai_metadata and ai_metadata["negative_prompt"]:
                    formatted_lines.append("NEGATIVE PROMPT:")
                    formatted_lines.append(ai_metadata["negative_prompt"])
                    formatted_lines.append("")
                
                if "seed" in ai_metadata:
                    formatted_lines.append("PARAMETERS:")
                    formatted_lines.append(f"Seed: {ai_metadata['seed']}")
                    if "strength" in ai_metadata:
                        formatted_lines.append(f"Strength: {ai_metadata['strength'] * 100:.1f}%")
                    formatted_lines.append("")
                
                if "style" in ai_metadata and ai_metadata["style"]:
                    formatted_lines.append("STYLE:")
                    formatted_lines.append(ai_metadata["style"])
                    formatted_lines.append("")
                
                if "checkpoint" in ai_metadata and ai_metadata["checkpoint"]:
                    formatted_lines.append("CHECKPOINT:")
                    formatted_lines.append(ai_metadata["checkpoint"])
                    formatted_lines.append("")
            
            # Display all found metadata
            if has_ai_metadata:
                formatted_lines.append("")
                formatted_lines.append("=== DETECTED AI METADATA ===")
                formatted_lines.append("")
            else:
                formatted_lines.append("")
                formatted_lines.append("=== AVAILABLE METADATA ===")
                formatted_lines.append("")
            
            # Display all metadata
            for key, value in metadata.items():
                if key != "AI_METADATA_JSON":
                    formatted_lines.append(f"{key}: {value}")
            
            meta_text.setPlainText("\n".join(formatted_lines))
        else:
            meta_text.setPlainText(_("No metadata found in this image"))
        
        vbox.addWidget(meta_text)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        close_button = QPushButton(_("Close"), dlg)
        close_button.clicked.connect(dlg.accept)
        buttons_layout.addWidget(close_button)
        
        vbox.addLayout(buttons_layout)
        dlg.exec_()
    
    def _extract_image_metadata(self, image_path: str) -> Dict[str, Any]:
        """Extracts metadata from an image"""
        metadata = {}
        
        try:
            # Read image with QImageReader to access metadata
            reader = QImageReader(image_path)
            
            # Custom PNG metadata
            if image_path.lower().endswith('.png'):
                # Look for our custom JSON metadata
                json_metadata = reader.text("metadata")
                if json_metadata:
                    try:
                        ai_metadata = json.loads(json_metadata)
                        metadata["AI_METADATA_JSON"] = ai_metadata
                    except json.JSONDecodeError:
                        pass
            
            # EXIF and other metadata
            for key in reader.textKeys():
                if key not in ["metadata"]:  # Avoid duplicates
                    metadata[key] = reader.text(key)
            
            # Basic image information
            if reader.size().isValid():
                metadata["Dimensions"] = f"{reader.size().width()}x{reader.size().height()}"
            
            if reader.format():
                metadata["Format"] = str(reader.format(), 'utf-8')
            
        except Exception as e:
            from ..util import client_logger as log
            log.warning(f"Error extracting metadata: {e}")
        
        return metadata