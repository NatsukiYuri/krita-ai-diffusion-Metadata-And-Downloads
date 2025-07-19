from __future__ import annotations
from textwrap import wrap as wrap_text
from typing import cast
from PyQt5.QtCore import Qt, QEvent, QMetaObject, QSize, QPoint, QTimer, QUuid, pyqtSignal
from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtGui import QGuiApplication, QMouseEvent, QKeyEvent, QKeySequence
from PyQt5.QtGui import QPalette, QColor, QIcon
from PyQt5.QtWidgets import QAction, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QProgressBar
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QListView, QSizePolicy
from PyQt5.QtWidgets import QComboBox, QCheckBox, QMenu, QMessageBox, QToolButton
from PyQt5.QtWidgets import QLabel, QTextEdit, QFileDialog, QDialog, QDialogButtonBox

from ..properties import Binding, Bind, bind, bind_combo, bind_toggle
from ..image import Bounds, Extent, Image
from ..jobs import Job, JobQueue, JobState, JobKind, JobParams
from ..model import Model, InpaintContext, RootRegion, ProgressKind, Workspace
from ..style import Styles
from ..root import root
from ..workflow import InpaintMode, FillMode
from ..localization import translate as _
from ..resources import Arch
from ..util import ensure, flatten, sequence_equal
from .widget import WorkspaceSelectWidget, StyleSelectWidget, StrengthWidget, QueueButton
from .widget import GenerateButton, ErrorBox, create_wide_tool_button
from .region import RegionPromptWidget
from . import theme


class HistoryWidget(QListWidget):
    _model: Model
    _connections: list[QMetaObject.Connection]
    _last_job_params: JobParams | None = None

    item_activated = pyqtSignal(QListWidgetItem)

    _thumb_size = 96
    _applied_icon = Image.load(theme.icon_path / "star.png")
    _list_css = f"""
        QListWidget {{ background-color: transparent; }}
        QListWidget::item:selected {{ border: 1px solid {theme.grey}; }}
    """
    _button_css = f"""
        QPushButton {{
            border: 1px solid {theme.grey};
            background: {"rgba(64, 64, 64, 170)" if theme.is_dark else "rgba(240, 240, 240, 160)"};
            padding: 2px;
        }}
        QPushButton:hover {{
            background: {"rgba(72, 72, 72, 210)" if theme.is_dark else "rgba(240, 240, 240, 200)"};
        }}
    """

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)
        self._model = root.active_model
        self._connections = []

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setResizeMode(QListView.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFlow(QListView.LeftToRight)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(theme.screen_scale(self, QSize(self._thumb_size, self._thumb_size)))
        self.setFrameStyle(QListWidget.NoFrame)
        self.setStyleSheet(self._list_css)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setDragEnabled(False)
        self.itemClicked.connect(self.handle_preview_click)
        self.itemDoubleClicked.connect(self.item_activated)
        self.itemSelectionChanged.connect(self.select_item)

        self._apply_button = QPushButton(theme.icon("apply"), _("Apply"), self)
        self._apply_button.setStyleSheet(self._button_css)
        self._apply_button.setVisible(False)
        self._apply_button.clicked.connect(self._activate_selection)

        self._context_button = QPushButton(theme.icon("context"), "", self)
        self._context_button.setStyleSheet(self._button_css)
        self._context_button.setVisible(False)
        self._context_button.clicked.connect(self._show_context_menu_dropdown)

        f = self.fontMetrics()
        self._apply_button.setFixedHeight(f.height() + 8)
        self._context_button.setFixedWidth(f.height() + 8)
        if scrollbar := self.verticalScrollBar():
            scrollbar.valueChanged.connect(self.update_apply_button)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    @property
    def model_(self):
        return self._model

    @model_.setter
    def model_(self, model: Model):
        Binding.disconnect_all(self._connections)
        self._model = model
        jobs = model.jobs
        self._connections = [
            jobs.selection_changed.connect(self.update_selection),
            jobs.job_finished.connect(self.add),
            jobs.job_discarded.connect(self.remove),
            jobs.result_used.connect(self.update_image_thumbnail),
            jobs.result_discarded.connect(self.remove_image),
        ]
        self.rebuild()
        self.update_selection()

    def add(self, job: Job):
        if not self.is_finished(job):
            return  # Only finished diffusion/animation jobs have images to show

        scrollbar = self.verticalScrollBar()
        scroll_to_bottom = scrollbar and scrollbar.value() >= scrollbar.maximum() - 4

        if not JobParams.equal_ignore_seed(self._last_job_params, job.params):
            self._last_job_params = job.params
            prompt = job.params.name if job.params.name != "" else "<no prompt>"
            strength = job.params.metadata.get("strength", 1.0)
            strength = f"{strength * 100:.0f}% - " if strength != 1.0 else ""

            header = QListWidgetItem(f"{job.timestamp:%H:%M} - {strength}{prompt}")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setData(Qt.ItemDataRole.UserRole, job.id)
            header.setData(Qt.ItemDataRole.ToolTipRole, job.params.prompt)
            header.setSizeHint(QSize(9999, self.fontMetrics().lineSpacing() + 4))
            header.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
            self.addItem(header)

        if job.kind is JobKind.diffusion:
            for i, img in enumerate(job.results):
                item = QListWidgetItem(self._image_thumbnail(job, i), None)  # type: ignore (text can be None)
                item.setData(Qt.ItemDataRole.UserRole, job.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, i)
                item.setData(Qt.ItemDataRole.ToolTipRole, self._job_info(job.params))
                self.addItem(item)

        if job.kind is JobKind.animation:
            item = AnimatedListItem([
                self._image_thumbnail(job, i) for i in range(len(job.results))
            ])
            item.setData(Qt.ItemDataRole.UserRole, job.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, 0)
            item.setData(Qt.ItemDataRole.ToolTipRole, self._job_info(job.params))
            self.addItem(item)

        if scroll_to_bottom:
            self.scrollToBottom()

    _job_info_translations = {
        "prompt": _("Prompt"),
        "negative_prompt": _("Negative Prompt"),
        "style": _("Style"),
        "strength": _("Strength"),
        "checkpoint": _("Model"),
        "loras": _("LoRA"),
        "sampler": _("Sampler"),
        "seed": _("Seed"),
    }

    def _job_info(self, params: JobParams, tooltip_header: bool = True):
        title = params.name if params.name != "" else "<no prompt>"
        if len(title) > 70:
            title = title[:66] + "..."
        if params.strength != 1.0:
            title = f"{title} @ {params.strength * 100:.0f}%"
        style = Styles.list().find(params.style)
        strings: list[str | list[str]] = (
            [
                title + "\n",
                _("Click to toggle preview, double-click to apply."),
                "",
            ]
            if tooltip_header
            else []
        )
        for key, value in params.metadata.items():
            if key == "style" and style:
                value = style.name
            if isinstance(value, list) and len(value) == 0:
                continue
            if isinstance(value, list) and isinstance(value[0], dict):
                value = "\n  ".join(
                    (
                        f"{v.get('name')} ({v.get('strength')})"
                        for v in value
                        if v.get("enabled", True)
                    )
                )
            s = f"{self._job_info_translations.get(key, key)}: {value}"
            if tooltip_header:
                s = wrap_text(s, 80, subsequent_indent=" ")
            strings.append(s)
        strings.append(_("Seed") + f": {params.seed}")
        return "\n".join(flatten(strings))

    def remove(self, job: Job):
        self._remove_items(ensure(job.id))

    def remove_image(self, id: JobQueue.Item):
        self._remove_items(id.job, id.image)

    def _remove_items(self, job_id: str, image_index: int = -1):
        def _job_id(item: QListWidgetItem | None):
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        item_was_selected = False
        with theme.SignalBlocker(self):
            # Remove all the job's items before triggering potential selection changes
            current = next((i for i in range(self.count()) if _job_id(self.item(i)) == job_id), -1)
            if current >= 0:
                item = self.item(current)
                while item and _job_id(item) == job_id:
                    _, index = self.item_info(item)
                    if image_index == index or (index is not None and image_index == -1):
                        item_was_selected = item_was_selected or item.isSelected()
                        self.takeItem(current)
                    else:
                        if index and index > image_index:
                            item.setData(Qt.ItemDataRole.UserRole + 1, index - 1)
                        current += 1
                    item = self.item(current)

        if item_was_selected:
            self._model.jobs.selection = []
        else:
            self.update_apply_button()  # selection may have moved

        for i in range(self.count()):
            item = self.item(i)
            next_item = self.item(i + 1)
            if item and item.text() != "" and next_item and next_item.text() != "":
                self.takeItem(i)

    def update_selection(self):
        current = [self._item_data(i) for i in self.selectedItems()]
        changed = not sequence_equal(self._model.jobs.selection, current)

        with theme.SignalBlocker(self):
            for i in range(self.count()):
                item = self.item(i)
                if item and item.type() == QListWidgetItem.ItemType.UserType:
                    cast(AnimatedListItem, item).stop_animation()

            if changed:  # don't mess with widget's state if it already matches
                self.clearSelection()

            for selection in self._model.jobs.selection:
                if item := self._find(selection):
                    if changed:
                        item.setSelected(True)
                    if item.type() == QListWidgetItem.ItemType.UserType:
                        cast(AnimatedListItem, item).start_animation()

        self.update_apply_button()

    def update_apply_button(self):
        selected = self.selectedItems()
        if len(selected) > 0:
            rect = self.visualItemRect(selected[0])
            font = self._apply_button.fontMetrics()
            context_visible = rect.width() >= 0.6 * self.iconSize().width()
            apply_text_visible = font.width(_("Apply")) < 0.35 * rect.width()
            apply_pos = QPoint(rect.left() + 3, rect.bottom() - self._apply_button.height() - 2)
            if context_visible:
                cw = self._context_button.width()
                context_pos = QPoint(rect.right() - cw - 2, apply_pos.y())
                context_size = QSize(cw, self._apply_button.height())
            else:
                context_pos = QPoint(rect.right(), apply_pos.y())
                context_size = QSize(0, 0)
            apply_size = QSize(context_pos.x() - rect.left() - 5, self._apply_button.height())
            self._apply_button.setVisible(True)
            self._apply_button.move(apply_pos)
            self._apply_button.resize(apply_size)
            self._apply_button.setText(_("Apply") if apply_text_visible else "")
            self._context_button.setVisible(context_visible)
            if context_visible:
                self._context_button.move(context_pos)
                self._context_button.resize(context_size)
        else:
            self._apply_button.setVisible(False)
            self._context_button.setVisible(False)

    def update_image_thumbnail(self, id: JobQueue.Item):
        if item := self._find(id):
            job = ensure(self._model.jobs.find(id.job))
            item.setIcon(self._image_thumbnail(job, id.image))

    def select_item(self):
        self._model.jobs.selection = [self._item_data(i) for i in self.selectedItems()]

    def _toggle_selection(self):
        self._model.jobs.toggle_selection()

    def _activate_selection(self):
        items = self.selectedItems()
        if len(items) > 0:
            self.item_activated.emit(items[0])

    def is_finished(self, job: Job):
        return job.kind in [JobKind.diffusion, JobKind.animation] and job.state is JobState.finished

    def rebuild(self):
        self.clear()
        for job in filter(self.is_finished, self._model.jobs):
            self.add(job)
        self.scrollToBottom()

    def item_info(self, item: QListWidgetItem) -> tuple[str, int]:  # job id, image index
        return item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1)

    @property
    def selected_job(self) -> Job | None:
        items = self.selectedItems()
        if len(items) > 0:
            job_id, _ = self.item_info(items[0])
            return self._model.jobs.find(job_id)
        return None

    def handle_preview_click(self, item: QListWidgetItem):
        if item.text() != "" and item.text() != "<no prompt>":
            if clipboard := QGuiApplication.clipboard():
                prompt = item.data(Qt.ItemDataRole.ToolTipRole)
                clipboard.setText(prompt)

    def mousePressEvent(self, e: QMouseEvent | None):
        if (  # make single click deselect current item (usually requires Ctrl+click)
            e is not None
            and e.button() == Qt.MouseButton.LeftButton
            and e.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            item = self.itemAt(e.pos())
            if item is not None and item.isSelected():
                self.clearSelection()
                e.accept()
                return
        super().mousePressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update_apply_button()

    def event(self, e: QEvent | None):
        assert e is not None
        # Disambiguate shortcut events which Krita overrides
        if e.type() == QEvent.Type.ShortcutOverride:
            assert isinstance(e, QKeyEvent)
            if e.matches(QKeySequence.StandardKey.Delete):
                self._discard_image()
                e.accept()
            elif e.key() == Qt.Key.Key_Space:
                self._toggle_selection()
                e.accept()
        return super().event(e)

    def _find(self, id: JobQueue.Item):
        items = (ensure(self.item(i)) for i in range(self.count()))
        return next((item for item in items if self._item_data(item) == id), None)

    def _item_data(self, item: QListWidgetItem):
        return JobQueue.Item(
            item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1)
        )

    def _image_thumbnail(self, job: Job, index: int):
        image = job.results[index]
        # Use 2x thumb size for good quality on high-DPI screens
        thumb = Image.scale_to_fit(image, Extent(self._thumb_size * 2, self._thumb_size * 2))
        min_height = min(4 * self._apply_button.height(), 2 * self._thumb_size)
        if thumb.extent.height < min_height:
            thumb = Image.crop(thumb, Bounds(0, 0, thumb.extent.width, min_height))
        if job.result_was_used(index):  # add tiny star icon to mark used results
            thumb.draw_image(self._applied_icon, offset=(thumb.extent.width - 28, 4))
        return thumb.to_icon()

    def _show_context_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if item is not None:
            job = self._model.jobs.find(self._item_data(item).job)
            menu = QMenu(self)
            menu.addAction(_("Copy Prompt"), self._copy_prompt)
            menu.addAction(_("Copy Strength"), self._copy_strength)
            style_action = ensure(menu.addAction(_("Copy Style"), self._copy_style))
            if job is None or Styles.list().find(job.params.style) is None:
                style_action.setEnabled(False)
            menu.addAction(_("Copy Seed"), self._copy_seed)
            menu.addAction(_("Info to Clipboard"), self._info_to_clipboard)
            menu.addAction(_("Afficher les métadonnées"), self._show_metadata)
            menu.addSeparator()
            save_action = ensure(menu.addAction(_("Save Image"), self._save_image))
            if self._model.document.filename == "":
                save_action.setEnabled(False)
                save_action.setToolTip(
                    _(
                        "Save as separate image to the same folder as the document.\nMust save the document first!"
                    )
                )
                menu.setToolTipsVisible(True)
            menu.addAction(_("Discard Image"), self._discard_image)
            menu.addSeparator()
            menu.addAction(_("Clear History"), self._clear_all)
            menu.exec(self.mapToGlobal(pos))

    def _show_context_menu_dropdown(self):
        pos = self._context_button.pos()
        pos.setY(pos.y() + self._context_button.height())
        self._show_context_menu(pos)

    def _copy_prompt(self):
        if job := self.selected_job:
            active = self._model.regions.active_or_root
            active.positive = job.params.prompt
            if isinstance(active, RootRegion):
                active.negative = job.params.metadata.get("negative_prompt", "")

            if clipboard := QGuiApplication.clipboard():
                clipboard.setText(job.params.prompt)

            if self._model.workspace is Workspace.custom and self._model.document.is_active:
                self._model.custom.try_set_params(job.params.metadata)

    def _copy_strength(self):
        if job := self.selected_job:
            self._model.strength = job.params.strength

    def _copy_style(self):
        if job := self.selected_job:
            if style := Styles.list().find(job.params.style):
                self._model.style = style

    def _copy_seed(self):
        if job := self.selected_job:
            self._model.fixed_seed = True
            self._model.seed = job.params.seed

    def _info_to_clipboard(self):
        if (job := self.selected_job) and (clipboard := QGuiApplication.clipboard()):
            clipboard.setText(self._job_info(job.params, tooltip_header=False))

    def _show_metadata(self):
        if job := self.selected_job:
            # Créer un message détaillé avec toutes les métadonnées
            metadata_text = self._format_detailed_metadata(job)
            
            QMessageBox.information(
                self,
                _("Métadonnées de l'image"),
                metadata_text,
                QMessageBox.Ok,
            )

    def _format_detailed_metadata(self, job: Job) -> str:
        """Formate les métadonnées de manière détaillée et lisible"""
        lines = []
        
        # Informations de base
        lines.append(f"📝 **Prompt:** {job.params.prompt}")
        if job.params.name and job.params.name != job.params.prompt:
            lines.append(f"📋 **Nom:** {job.params.name}")
        
        # Seed et paramètres techniques
        lines.append(f"🎲 **Seed:** {job.params.seed}")
        lines.append(f"💪 **Strength:** {job.params.strength * 100:.1f}%")
        
        # Style
        style = Styles.list().find(job.params.style)
        if style:
            lines.append(f"🎨 **Style:** {style.name}")
        
        # Métadonnées détaillées
        if job.params.metadata:
            lines.append("\n🔧 **Paramètres techniques:**")
            for key, value in job.params.metadata.items():
                if key == "style" and style:
                    continue  # Déjà affiché plus haut
                
                # Traduire les clés
                translated_key = self._job_info_translations.get(key, key)
                
                # Formater les valeurs spéciales
                if isinstance(value, list) and len(value) == 0:
                    continue
                elif isinstance(value, list) and isinstance(value[0], dict):
                    # LoRA ou autres paramètres complexes
                    formatted_values = []
                    for v in value:
                        if v.get("enabled", True):
                            name = v.get('name', 'Unknown')
                            strength = v.get('strength', 1.0)
                            formatted_values.append(f"{name} ({strength})")
                    value = ", ".join(formatted_values) if formatted_values else "Aucun"
                elif key == "negative_prompt" and value:
                    lines.append(f"❌ **{translated_key}:** {value}")
                    continue
                
                lines.append(f"  • **{translated_key}:** {value}")
        
        # Informations temporelles
        lines.append(f"\n⏰ **Généré le:** {job.timestamp.strftime('%d/%m/%Y à %H:%M:%S')}")
        
        # Type de job
        job_type = "Diffusion"
        if job.kind is JobKind.animation:
            job_type = "Animation"
        elif job.kind is JobKind.upscaling:
            job_type = "Upscaling"
        lines.append(f"🖼️ **Type:** {job_type}")
        
        # Nombre d'images
        if len(job.results) > 1:
            lines.append(f"📊 **Images générées:** {len(job.results)}")
        
        return "\n".join(lines)

    def _save_image(self):
        items = self.selectedItems()
        for item in items:
            job_id, image_index = self.item_info(item)
            self._model.save_result(job_id, image_index)

    def _discard_image(self):
        items = self.selectedItems()
        next_item = self.row(items[0]) if len(items) > 0 else -1
        for item in items:
            job_id, image_index = self.item_info(item)
            self._model.jobs.discard(job_id, image_index)
        if next_item >= 0:
            self.setCurrentRow(next_item, QItemSelectionModel.SelectionFlag.Current)

    def _clear_all(self):
        reply = QMessageBox.warning(
            self,
            _("Clear History"),
            _("Are you sure you want to discard all generated images?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._model.jobs.clear()
            self.clear()


class AnimatedListItem(QListWidgetItem):
    def __init__(self, images: list[QIcon]):
        super().__init__(images[0], None, type=QListWidgetItem.ItemType.UserType)
        self._images = images
        self._current = 0
        self._is_running = False
        self._timer = QTimer()
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._next_frame)

    def start_animation(self):
        if not self._is_running:
            self._is_running = True
            self._timer.start(40)

    def stop_animation(self):
        if self._is_running:
            self._timer.stop()
            self._is_running = False
            self._current = 0
            self.setIcon(self._images[self._current])

    def _next_frame(self):
        self._current = (self._current + 1) % len(self._images)
        self.setIcon(self._images[self._current])


class CustomInpaintWidget(QWidget):
    _model: Model
    _model_bindings: list[QMetaObject.Connection | Binding]

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._model = root.active_model
        self._model_bindings = []

        self.use_inpaint_button = QCheckBox(self)
        self.use_inpaint_button.setText(_("Seamless"))
        self.use_inpaint_button.setToolTip(_("Generate content which blends into the surroundings"))

        self.use_prompt_focus_button = QCheckBox(self)
        self.use_prompt_focus_button.setText(_("Focus"))
        self.use_prompt_focus_button.setToolTip(
            _(
                "Use the text prompt to describe the selected region rather than the context area / Use only one regional prompt"
            )
        )

        self.fill_mode_combo = QComboBox(self)
        fill_icon = theme.icon("fill")
        self.fill_mode_combo.addItem(theme.icon("fill-empty"), _("None"), FillMode.none)
        self.fill_mode_combo.addItem(fill_icon, _("Neutral"), FillMode.neutral)
        self.fill_mode_combo.addItem(fill_icon, _("Blur"), FillMode.blur)
        self.fill_mode_combo.addItem(fill_icon, _("Border"), FillMode.border)
        self.fill_mode_combo.addItem(fill_icon, _("Inpaint"), FillMode.inpaint)
        self.fill_mode_combo.setStyleSheet(theme.flat_combo_stylesheet)
        self.fill_mode_combo.setToolTip(_("Pre-fill the selected region before diffusion"))

        def ctx_icon(name):
            return theme.icon(f"context-{name}")

        self.context_combo = QComboBox(self)
        self.context_combo.addItem(
            ctx_icon("automatic"), _("Automatic Context"), InpaintContext.automatic
        )
        self.context_combo.addItem(
            ctx_icon("mask"), _("Selection Bounds"), InpaintContext.mask_bounds
        )
        self.context_combo.addItem(
            ctx_icon("image"), _("Entire Image"), InpaintContext.entire_image
        )
        self.context_combo.setStyleSheet(theme.flat_combo_stylesheet)
        self.context_combo.setToolTip(
            _("Part of the image around the selection which is used as context.")
        )
        self.context_combo.setMinimumContentsLength(20)
        self.context_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLength
        )
        self.context_combo.currentIndexChanged.connect(self.set_context)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.use_inpaint_button)
        layout.addWidget(self.use_prompt_focus_button)
        layout.addWidget(self.fill_mode_combo)
        layout.addWidget(self.context_combo, 1)
        self.setLayout(layout)

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, model: Model):
        if self._model != model:
            Binding.disconnect_all(self._model_bindings)
            self._model = model
            self._model_bindings = [
                bind_combo(model.inpaint, "fill", self.fill_mode_combo),
                bind_toggle(model.inpaint, "use_inpaint", self.use_inpaint_button),
                bind_toggle(model.inpaint, "use_prompt_focus", self.use_prompt_focus_button),
                model.style_changed.connect(self.update_widgets_enabled),
                model.strength_changed.connect(self.update_widgets_enabled),
                model.layers.changed.connect(self.update_context_layers),
            ]
            self.update_widgets_enabled()
            self.update_context_layers()
            self.update_context()

    def update_widgets_enabled(self):
        arch = self._model.arch
        self.fill_mode_combo.setEnabled(self.model.strength == 1.0)
        self.use_inpaint_button.setEnabled(arch.is_sdxl_like or arch.has_controlnet_inpaint)
        self.use_prompt_focus_button.setEnabled(arch is Arch.sd15 or arch.is_sdxl_like)

    def update_context_layers(self):
        current = self.context_combo.currentData()
        with theme.SignalBlocker(self.context_combo):
            while self.context_combo.count() > 3:
                self.context_combo.removeItem(self.context_combo.count() - 1)
            icon = theme.icon("context-layer")
            for layer in self._model.layers.masks:
                self.context_combo.addItem(icon, f"{layer.name}", layer.id)
        current_index = self.context_combo.findData(current)
        if current_index >= 0:
            self.context_combo.setCurrentIndex(current_index)

    def update_context(self):
        if self._model.inpaint.context == InpaintContext.layer_bounds:
            i = self.context_combo.findData(self._model.inpaint.context_layer_id)
            self.context_combo.setCurrentIndex(i)
        else:
            i = self.context_combo.findData(self._model.inpaint.context)
            self.context_combo.setCurrentIndex(i)

    def set_context(self):
        data = self.context_combo.currentData()
        if isinstance(data, QUuid):
            self._model.inpaint.context = InpaintContext.layer_bounds
            self._model.inpaint.context_layer_id = data
        elif isinstance(data, InpaintContext):
            self._model.inpaint.context = data


class ProgressBar(QProgressBar):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._model = root.active_model
        self._model_bindings: list[QMetaObject.Connection] = []
        self._palette = self.palette()
        self.setMinimum(0)
        self.setMaximum(1000)
        self.setTextVisible(False)
        self.setFixedHeight(6)

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, model: Model):
        if self._model != model:
            Binding.disconnect_all(self._model_bindings)
            self._model = model
            self._model_bindings = [
                self._model.progress_changed.connect(self._update_progress),
                self._model.progress_kind_changed.connect(self._update_progress_kind),
            ]

    def _update_progress_kind(self):
        palette = self._palette
        if self._model.progress_kind is ProgressKind.upload:
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.progress_alt))
        self.setPalette(palette)

    def _update_progress(self):
        if self._model.progress >= 0:
            self.setValue(int(self._model.progress * 1000))
        else:
            if self.value() >= 100:
                self.reset()
            self.setValue(min(99, self.value() + 2))


class GenerationWidget(QWidget):
    _model: Model
    _model_bindings: list[QMetaObject.Connection | Binding]

    def __init__(self):
        super().__init__()
        self._model = root.active_model
        self._model_bindings = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 2, 0)
        self.setLayout(layout)

        self.workspace_select = WorkspaceSelectWidget(self)
        self.style_select = StyleSelectWidget(self)

        style_layout = QHBoxLayout()
        style_layout.addWidget(self.workspace_select)
        style_layout.addWidget(self.style_select)
        layout.addLayout(style_layout)

        self.region_prompt = RegionPromptWidget(self)
        layout.addWidget(self.region_prompt)

        self.strength_slider = StrengthWidget(parent=self)
        self.add_region_button = create_wide_tool_button("region-add", _("Add Region"), self)
        self.add_control_button = create_wide_tool_button(
            "control-add", _("Add Control Layer"), self
        )
        strength_layout = QHBoxLayout()
        strength_layout.addWidget(self.strength_slider)
        strength_layout.addWidget(self.add_control_button)
        strength_layout.addWidget(self.add_region_button)
        layout.addLayout(strength_layout)

        self.custom_inpaint = CustomInpaintWidget(self)
        layout.addWidget(self.custom_inpaint)

        self.generate_button = GenerateButton(JobKind.diffusion, self)

        self.inpaint_mode_button = QToolButton(self)
        self.inpaint_mode_button.setArrowType(Qt.ArrowType.DownArrow)
        self.inpaint_mode_button.setFixedHeight(self.generate_button.height() - 2)
        self.inpaint_mode_button.clicked.connect(self.show_inpaint_menu)
        self.inpaint_menu = self._create_inpaint_menu()
        self.refine_menu = self._create_refine_menu()
        self.generate_region_menu = self._create_generate_region_menu()
        self.refine_region_menu = self._create_refine_region_menu()
        self.edit_menu = self._create_edit_menu()

        self.region_mask_button = QToolButton(self)
        self.region_mask_button.setIcon(theme.icon("region-alpha"))
        self.region_mask_button.setCheckable(True)
        self.region_mask_button.setFixedHeight(self.generate_button.height() - 2)
        self.region_mask_button.setToolTip(
            _("Generate the active layer region only (use layer transparency as mask)")
        )

        generate_layout = QHBoxLayout()
        generate_layout.setSpacing(0)
        generate_layout.addWidget(self.generate_button)
        generate_layout.addWidget(self.inpaint_mode_button)
        generate_layout.addWidget(self.region_mask_button)

        self.queue_button = QueueButton(parent=self)
        self.queue_button.setFixedHeight(self.generate_button.height() - 2)

        actions_layout = QHBoxLayout()
        actions_layout.addLayout(generate_layout)
        actions_layout.addWidget(self.queue_button)
        layout.addLayout(actions_layout)

        self.progress_bar = ProgressBar(self)
        layout.addWidget(self.progress_bar)

        self.error_box = ErrorBox(self)
        layout.addWidget(self.error_box)

        self.history = HistoryWidget(self)
        self.history.item_activated.connect(self.apply_result)
        layout.addWidget(self.history)

        # Widget pour afficher les métadonnées
        self.metadata_widget = MetadataWidget(self)
        layout.addWidget(self.metadata_widget)
        
        # Connecter le paramètre pour afficher/masquer l'interface des métadonnées
        from ..settings import settings
        self._metadata_visibility_connection = settings.changed.connect(self._update_metadata_visibility)
        self._update_metadata_visibility()

        self.update_generate_button()

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, model: Model):
        if self._model != model:
            Binding.disconnect_all(self._model_bindings)
            self._model = model
            self._model_bindings = [
                bind(model, "workspace", self.workspace_select, "value", Bind.one_way),
                bind(model, "style", self.style_select, "value"),
                bind(model, "strength", self.strength_slider, "value"),
                bind(model, "error", self.error_box, "error", Bind.one_way),
                bind_toggle(model, "region_only", self.region_mask_button),
                model.inpaint.mode_changed.connect(self.update_generate_button),
                model.strength_changed.connect(self.update_generate_button),
                model.document.selection_bounds_changed.connect(self.update_generate_button),
                model.document.layers.active_changed.connect(self.update_generate_button),
                model.regions.active_changed.connect(self.update_generate_button),
                model.region_only_changed.connect(self.update_generate_button),
                model.style_changed.connect(self.update_generate_button),
                self.add_control_button.clicked.connect(model.regions.add_control),
                self.add_region_button.clicked.connect(model.regions.create_region_group),
                self.region_prompt.activated.connect(model.generate),
                self.generate_button.clicked.connect(model.generate),
            ]
            self.region_prompt.regions = model.regions
            self.custom_inpaint.model = model
            self.generate_button.model = model
            self.queue_button.model = model
            self.progress_bar.model = model
            self.strength_slider.model = model
            self.history.model_ = model
            self.metadata_widget.model = model
            self.update_generate_button()

    def apply_result(self, item: QListWidgetItem):
        job_id, index = self.history.item_info(item)
        self.model.apply_generated_result(job_id, index)

    _inpaint_text = {
        InpaintMode.automatic: _("Default (Auto-detect)"),
        InpaintMode.fill: _("Fill"),
        InpaintMode.expand: _("Expand"),
        InpaintMode.add_object: _("Add Content"),
        InpaintMode.remove_object: _("Remove Content"),
        InpaintMode.replace_background: _("Replace Background"),
        InpaintMode.custom: _("Generate (Custom)"),
    }

    def _mk_action(self, mode: InpaintMode, text: str, icon: str):
        action = QAction(text, self)
        action.setIcon(theme.icon(icon))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(lambda: self.change_inpaint_mode(mode))
        return action

    def _create_inpaint_menu(self):
        menu = QMenu(self)
        for mode in InpaintMode:
            text = self._inpaint_text[mode]
            menu.addAction(self._mk_action(mode, text, f"inpaint-{mode.name}"))
        return menu

    def _create_generate_region_menu(self):
        menu = QMenu(self)
        menu.addAction(
            self._mk_action(InpaintMode.automatic, _("Generate Region"), "generate-region")
        )
        menu.addAction(
            self._mk_action(InpaintMode.custom, _("Generate Region (Custom)"), "inpaint-custom")
        )
        return menu

    def _create_refine_menu(self):
        menu = QMenu(self)
        menu.addAction(self._mk_action(InpaintMode.automatic, _("Refine"), "refine"))
        menu.addAction(self._mk_action(InpaintMode.custom, _("Refine (Custom)"), "inpaint-custom"))
        return menu

    def _create_refine_region_menu(self):
        menu = QMenu(self)
        menu.addAction(self._mk_action(InpaintMode.automatic, _("Refine Region"), "refine-region"))
        menu.addAction(
            self._mk_action(InpaintMode.custom, _("Refine Region (Custom)"), "inpaint-custom")
        )
        return menu

    def _create_edit_menu(self):
        menu = QMenu(self)
        menu.addAction(self._mk_action(InpaintMode.automatic, _("Edit"), "refine"))
        menu.addAction(self._mk_action(InpaintMode.custom, _("Edit (Custom)"), "inpaint-custom"))
        return menu

    def show_inpaint_menu(self):
        width = self.generate_button.width() + self.inpaint_mode_button.width()
        pos = QPoint(0, self.generate_button.height())
        if self.model.arch.is_edit:
            menu = self.edit_menu
        elif self.model.strength == 1.0:
            if self.model.region_only:
                menu = self.generate_region_menu
            else:
                menu = self.inpaint_menu
        else:
            if self.model.region_only:
                menu = self.refine_region_menu
            else:
                menu = self.refine_menu
        menu.setFixedWidth(width)
        menu.exec_(self.generate_button.mapToGlobal(pos))

    def change_inpaint_mode(self, mode: InpaintMode):
        self.model.inpaint.mode = mode

    def toggle_region_only(self, checked: bool):
        self.model.region_only = checked

    def update_generate_button(self):
        if not self.model.has_document:
            return
        has_regions = len(self.model.regions) > 0
        has_active_region = self.model.regions.is_linked(self.model.layers.active)
        is_region_only = has_regions and has_active_region and self.model.region_only
        self.region_mask_button.setVisible(has_regions)
        self.region_mask_button.setEnabled(has_active_region)
        self.region_mask_button.setIcon(_region_mask_button_icons[is_region_only])

        if self.model.document.selection_bounds is None and not is_region_only:
            self.inpaint_mode_button.setVisible(False)
            self.custom_inpaint.setVisible(False)
            if self.model.arch.is_edit:
                icon = "refine"
                text = _("Edit")
            elif self.model.strength == 1.0:
                icon = "workspace-generation"
                text = _("Generate")
            else:
                icon = "refine"
                text = _("Refine")
        else:
            self.inpaint_mode_button.setVisible(True)
            self.custom_inpaint.setVisible(self.model.inpaint.mode is InpaintMode.custom)
            mode = self.model.resolve_inpaint_mode()
            text = _("Generate")
            if self.model.arch.is_edit:
                text = _("Edit")
            elif self.model.strength < 1:
                text = _("Refine")
            if is_region_only:
                text += " " + _("Region")
            if mode is InpaintMode.custom:
                text += " " + _("(Custom)")
            if self.model.strength == 1.0 and not self.model.arch.is_edit:
                if mode is InpaintMode.custom:
                    icon = "inpaint-custom"
                elif is_region_only:
                    icon = "generate-region"
                else:
                    icon = f"inpaint-{mode.name}"
                    text = self._inpaint_text[mode]
            else:
                if mode is InpaintMode.custom:
                    icon = "inpaint-custom"
                elif is_region_only:
                    icon = "refine-region"
                else:
                    icon = "refine"

        self.generate_button.operation = text
        self.generate_button.setIcon(theme.icon(icon))
    
    def _update_metadata_visibility(self):
        """Met à jour la visibilité de l'interface des métadonnées selon le paramètre"""
        from ..settings import settings
        self.metadata_widget.setVisible(settings.show_metadata_interface)
    



class MetadataWidget(QWidget):
    """Widget pour afficher les métadonnées de l'image sélectionnée"""
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._model = root.active_model
        self._model_bindings = []
        
        # Charger les paramètres sauvegardés
        from ..settings import settings
        self._font_size = settings.metadata_font_size
        self._widget_height = settings.metadata_widget_height
        self._text_height = self._widget_height - 10
        
        # Augmenter la taille par défaut si c'est la première fois
        if self._font_size == 10:  # Valeur par défaut
            self._font_size = 12
            settings.metadata_font_size = 12
        if self._widget_height == 220:  # Valeur par défaut
            self._widget_height = 280
            self._text_height = 270
            settings.metadata_widget_height = 280
        
        # Configuration du widget
        self.setMaximumHeight(self._widget_height)
        self.setMinimumHeight(100)
        
        # Layout principal
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        
        # Barre d'outils pour les contrôles de taille
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)
        
        # Label pour la taille de police
        font_label = QLabel("Size:", self)
        font_label.setStyleSheet("color: #e0e0e0; font-size: 9px;")
        toolbar_layout.addWidget(font_label)
        
        # Boutons pour ajuster la taille de police
        self._font_smaller_btn = QPushButton("A-", self)
        self._font_smaller_btn.setFixedSize(24, 20)
        self._font_smaller_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 2px;
                color: #e0e0e0;
                font-size: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        self._font_smaller_btn.clicked.connect(self._decrease_font_size)
        toolbar_layout.addWidget(self._font_smaller_btn)
        
        self._font_larger_btn = QPushButton("A+", self)
        self._font_larger_btn.setFixedSize(24, 20)
        self._font_larger_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 2px;
                color: #e0e0e0;
                font-size: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        self._font_larger_btn.clicked.connect(self._increase_font_size)
        toolbar_layout.addWidget(self._font_larger_btn)
        
        # Séparateur
        separator = QLabel("|", self)
        separator.setStyleSheet("color: #666; font-size: 9px; margin: 0 4px;")
        toolbar_layout.addWidget(separator)
        
        # Label pour la hauteur
        height_label = QLabel("Height:", self)
        height_label.setStyleSheet("color: #e0e0e0; font-size: 9px;")
        toolbar_layout.addWidget(height_label)
        
        # Boutons pour ajuster la hauteur
        self._height_smaller_btn = QPushButton("−", self)
        self._height_smaller_btn.setFixedSize(20, 20)
        self._height_smaller_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 2px;
                color: #e0e0e0;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        self._height_smaller_btn.clicked.connect(self._decrease_height)
        toolbar_layout.addWidget(self._height_smaller_btn)
        
        self._height_larger_btn = QPushButton("+", self)
        self._height_larger_btn.setFixedSize(20, 20)
        self._height_larger_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 2px;
                color: #e0e0e0;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        self._height_larger_btn.clicked.connect(self._increase_height)
        toolbar_layout.addWidget(self._height_larger_btn)
        
        # Espace flexible au milieu
        toolbar_layout.addStretch()
        
        # Bouton pour sauvegarder l'image finale avec métadonnées
        self.save_with_metadata_button = QPushButton("Save", self)
        self.save_with_metadata_button.setFixedSize(50, 20)
        self.save_with_metadata_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 120, 60, 0.8);
                border: 1px solid #555;
                border-radius: 2px;
                color: #e0e0e0;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 140, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 100, 40, 0.9);
            }
            QPushButton:disabled {
                background-color: rgba(60, 60, 60, 0.5);
                color: #888;
            }
        """)
        self.save_with_metadata_button.setToolTip("Save the current Krita document as PNG with AI generation metadata")
        self.save_with_metadata_button.clicked.connect(self._save_document_with_metadata)
        toolbar_layout.addWidget(self.save_with_metadata_button)
        
        layout.addLayout(toolbar_layout)
        
        # Zone de texte pour les métadonnées
        # Créer une classe personnalisée pour le QTextEdit
        class MetadataTextEdit(QTextEdit):
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
        
        # Créer le QTextEdit personnalisé
        self._metadata_text = MetadataTextEdit(self)
        self._metadata_text.setReadOnly(True)
        self._metadata_text.setMaximumHeight(self._text_height)
        self._metadata_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self._metadata_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._metadata_text.customContextMenuRequested.connect(self._show_text_context_menu)
        self._update_text_style()
        layout.addWidget(self._metadata_text)
        
        # Boutons d'action
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        
        # Bouton pour charger une image
        self._load_image_button = QPushButton("Load Image", self)
        self._load_image_button.setFixedSize(100, 25)
        self._load_image_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 2px;
                color: #e0e0e0;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        self._load_image_button.clicked.connect(self._load_external_image)
        buttons_layout.addWidget(self._load_image_button)
        
        # Espace flexible au milieu
        buttons_layout.addStretch()
        
        # Bouton de copie
        self._copy_button = QPushButton("Copy", self)
        self._copy_button.setFixedSize(80, 25)
        self._copy_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 2px;
                color: #e0e0e0;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        self._copy_button.clicked.connect(self._copy_metadata)
        buttons_layout.addWidget(self._copy_button)
        
        layout.addLayout(buttons_layout)
        
        # Default message
        self._metadata_text.setPlainText("Select an image to see its metadata")
        
    @property
    def model(self):
        return self._model
    
    @model.setter
    def model(self, model: Model):
        if self._model != model:
            Binding.disconnect_all(self._model_bindings)
            self._model = model
            self._model_bindings = [
                model.jobs.selection_changed.connect(self._update_metadata)
            ]
            self._update_metadata()
    
    def _update_metadata(self):
        """Updates metadata display based on selection"""
        selection = self._model.jobs.selection
        if not selection:
            self._metadata_text.setPlainText("Select an image to see its metadata")
            return
        
        # Take the first selected image
        job_id, image_index = selection[0]
        job = self._model.jobs.find(job_id)
        
        if not job:
            self._metadata_text.setPlainText("Image not found")
            return
        
        # Format metadata
        metadata_text = self._format_metadata_for_display(job)
        self._metadata_text.setPlainText(metadata_text)
    
    def _format_metadata_for_display(self, job: Job) -> str:
        """Formats metadata for display in the widget"""
        sections = []
        
        # Section 1: Prompt
        sections.append("PROMPT")
        sections.append("─" * 40)
        sections.append(f"{job.params.prompt}")
        if job.params.name and job.params.name != job.params.prompt:
            sections.append("")
            sections.append("NAME")
            sections.append("─" * 40)
            sections.append(f"{job.params.name}")
        
        # Section 2: Basic parameters
        sections.append("")
        sections.append("PARAMETERS")
        sections.append("─" * 40)
        sections.append(f"Seed: {job.params.seed}")
        sections.append(f"Strength: {job.params.strength * 100:.1f}%")
        
        # Style
        style = Styles.list().find(job.params.style)
        if style:
            sections.append(f"Style: {style.name}")
        
        # Section 3: Technical parameters
        if job.params.metadata:
            sections.append("")
            sections.append("TECHNICAL")
            sections.append("─" * 40)
            
            for key, value in job.params.metadata.items():
                if key == "style" and style:
                    continue
                
                translated_key = self._get_translation(key)
                
                if isinstance(value, list) and len(value) == 0:
                    continue
                elif isinstance(value, list) and isinstance(value[0], dict):
                    formatted_values = []
                    for v in value:
                        if v.get("enabled", True):
                            name = v.get('name', 'Unknown')
                            strength = v.get('strength', 1.0)
                            formatted_values.append(f"{name} ({strength})")
                    value = ", ".join(formatted_values) if formatted_values else "None"
                elif key == "negative_prompt" and value:
                    sections.append(f"Negative: {value}")
                    continue
                
                sections.append(f"{translated_key}: {value}")
        
        # Section 4: Information
        sections.append("")
        sections.append("INFORMATION")
        sections.append("─" * 40)
        
        # Job type
        job_type = "Diffusion"
        if job.kind is JobKind.animation:
            job_type = "Animation"
        elif job.kind is JobKind.upscaling:
            job_type = "Upscaling"
        sections.append(f"Type: {job_type}")
        
        # Generation date
        sections.append(f"Generated: {job.timestamp.strftime('%d/%m/%Y at %H:%M')}")
        
        # Number of images
        if len(job.results) > 1:
            sections.append(f"Images: {len(job.results)}")
        
        return "\n".join(sections)
    
    def _get_translation(self, key: str) -> str:
        """Translates metadata keys"""
        translations = {
            "checkpoint": "Model",
            "sampler": "Sampler",
            "steps": "Steps",
            "cfg": "CFG",
            "loras": "LoRA",
            "negative_prompt": "Negative prompt",
            "strength": "Strength",
            "style": "Style"
        }
        return translations.get(key, key)
    
    def _update_text_style(self):
        """Met à jour le style du texte avec la taille de police actuelle"""
        self._metadata_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(50, 50, 50, 0.2);
                border: 1px solid #444;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: {self._font_size}px;
                color: #e0e0e0;
                padding: 6px;
            }}
        """)
    
    def _decrease_font_size(self):
        """Diminue la taille de la police"""
        if self._font_size > 6:
            self._font_size -= 1
            self._update_text_style()
            # Sauvegarder le paramètre
            from ..settings import settings
            settings.metadata_font_size = self._font_size
    
    def _increase_font_size(self):
        """Augmente la taille de la police"""
        if self._font_size < 16:
            self._font_size += 1
            self._update_text_style()
            # Sauvegarder le paramètre
            from ..settings import settings
            settings.metadata_font_size = self._font_size
    
    def _decrease_height(self):
        """Diminue la hauteur du widget"""
        if self._widget_height > 120:
            self._widget_height -= 20
            self._text_height -= 20
            self.setMaximumHeight(self._widget_height)
            self._metadata_text.setMaximumHeight(self._text_height)
            # Sauvegarder le paramètre
            from ..settings import settings
            settings.metadata_widget_height = self._widget_height
    
    def _increase_height(self):
        """Augmente la hauteur du widget"""
        if self._widget_height < 400:
            self._widget_height += 20
            self._text_height += 20
            self.setMaximumHeight(self._widget_height)
            self._metadata_text.setMaximumHeight(self._text_height)
            # Sauvegarder le paramètre
            from ..settings import settings
            settings.metadata_widget_height = self._widget_height
    
    def _copy_metadata(self):
        """Copie les métadonnées dans le presse-papiers"""
        text = self._metadata_text.toPlainText()
        if text and text != "Select an image to see its metadata" and text != "Image not found":
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
    

    
    def _show_text_context_menu(self, pos):
        """Affiche le menu contextuel pour le texte des métadonnées"""
        menu = QMenu(self)
        
        # Copy action
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self._copy_selected_text)
        menu.addAction(copy_action)
        
        # Action Tout sélectionner
        select_all_action = QAction("Select All", self)
        select_all_action.triggered.connect(self._select_all_text)
        menu.addAction(select_all_action)
        
        # Empêcher la propagation vers le widget parent
        menu.aboutToShow.connect(lambda: self.setFocus())
        menu.exec_(self._metadata_text.mapToGlobal(pos))
    
    def _copy_selected_text(self):
        """Copie le texte sélectionné"""
        text = self._metadata_text.textCursor().selectedText()
        if text:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
            # Empêcher la propagation vers le widget parent
            return True
        return False
    
    def _select_all_text(self):
        """Sélectionne tout le texte"""
        cursor = self._metadata_text.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self._metadata_text.setTextCursor(cursor)

    def _save_document_with_metadata(self):
        """Sauvegarde le document Krita actuel avec les métadonnées de génération AI"""
        if not self._model.has_document:
            QMessageBox.warning(self, "Warning", "No document open. Please open a Krita document first.")
            return
        
        # Demander le chemin de sauvegarde
        from pathlib import Path
        from datetime import datetime
        
        # Nom de fichier par défaut basé sur le document actuel
        doc_filename = self._model.document.filename
        if doc_filename:
            base_name = Path(doc_filename).stem
        else:
            base_name = "krita_document"
        
        # Ajouter timestamp
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        default_filename = f"{base_name}_with_metadata_{timestamp}.png"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Document with Metadata", 
            default_filename,
            "PNG Images (*.png)"
        )
        
        if not file_path:
            return
        
        try:
            # Obtenir l'image complète du document
            from ..image import Bounds
            document_bounds = Bounds(0, 0, *self._model.document.extent)
            document_image = self._model._get_current_image(document_bounds)
            
            # Préparer les métadonnées de génération (format standard)
            metadata = {}
            
            # Métadonnées de base du modèle
            metadata["prompt"] = self._model.regions.positive
            metadata["negative_prompt"] = self._model.regions.negative
            metadata["seed"] = self._model.seed
            metadata["strength"] = self._model.strength
            
            # Métadonnées de style
            if self._model.style:
                metadata["style"] = self._model.style.filename
            
            # Métadonnées de génération
            metadata["generation_type"] = "Document Export"
            metadata["job_kind"] = "document_export"
            metadata["timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            metadata["batch_index"] = 0
            metadata["total_images"] = 1
            
            # Métadonnées techniques
            metadata["document_width"] = self._model.document.extent.width
            metadata["document_height"] = self._model.document.extent.height
            
            # Convertir en JSON compact
            import json
            metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))
            
            # Créer le dictionnaire de métadonnées pour QImageWriter
            metadata_dict = {"metadata": metadata_json}
            
            # Sauvegarder l'image avec métadonnées
            document_image.save(file_path, metadata=metadata_dict)
            
            QMessageBox.information(
                self, 
                "Success", 
                f"Document saved with metadata to:\n{file_path}"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to save document with metadata:\n{str(e)}"
            )

    def _load_external_image(self):
        """Ouvre un fichier image, affiche un aperçu et ses métadonnées dans une boîte de dialogue."""
        from PyQt5.QtGui import QPixmap
        from pathlib import Path
        # No translation needed - interface stays in English

        file_path, _ = QFileDialog.getOpenFileName(self, "Select an image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not file_path:
            return

        # Charger l'image pour l'aperçu
        try:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                QMessageBox.warning(self, "Error", "Unable to load image")
                return
        except Exception as e:
            QMessageBox.warning(self, "Error", "Unable to load image: " + str(e))
            return

        # Extraire les métadonnées basiques
        metadata = {}
        file_info = Path(file_path)
        metadata["Nom du fichier"] = file_info.name
        metadata["Chemin"] = str(file_info.parent)
        metadata["Taille du fichier"] = f"{file_info.stat().st_size / 1024:.1f} KB"
        metadata["Dimensions"] = f"{pixmap.width()} x {pixmap.height()} pixels"
        metadata["Format"] = file_info.suffix.upper()[1:] if file_info.suffix else "Inconnu"
        
        # Essayer d'extraire les métadonnées EXIF et autres métadonnées
        try:
            from PyQt5.QtGui import QImage
            qimage = QImage(file_path)
            if not qimage.isNull():
                # Métadonnées basiques de l'image
                metadata["Profondeur de couleur"] = f"{qimage.depth()} bits"
                try:
                    format_name = qimage.format().name()
                    if hasattr(format_name, 'decode'):
                        metadata["Format Qt"] = format_name.decode()
                    else:
                        metadata["Format Qt"] = str(format_name)
                except:
                    metadata["Format Qt"] = "Inconnu"
                
                # Essayer d'extraire les métadonnées PNG (pour les images générées par l'IA)
                if file_info.suffix.lower() == '.png':
                    # Les métadonnées PNG sont souvent stockées dans les chunks tEXt
                    # On va essayer de lire le fichier binaire pour extraire les métadonnées
                    try:
                        with open(file_path, 'rb') as f:
                            data = f.read()
                            
                        # Chercher les chunks tEXt dans le PNG
                        import re
                        text_chunks = re.findall(b'tEXt(.*?)(?=tEXt|IDAT|IEND)', data, re.DOTALL)
                        
                        for chunk in text_chunks:
                            try:
                                # Le format est: keyword\0text
                                null_pos = chunk.find(b'\0')
                                if null_pos != -1:
                                    keyword = chunk[:null_pos].decode('utf-8', errors='ignore')
                                    text_data = chunk[null_pos+1:].decode('utf-8', errors='ignore')
                                    
                                    # Vérifier si c'est notre JSON de métadonnées (nouveau format non compressé)
                                    if keyword == "AI_METADATA_JSON" or keyword == "AI" or keyword == "AI_META":
                                        try:
                                            import json
                                            # Nettoyer le JSON
                                            cleaned_json = text_data.strip()
                                            parsed_metadata = json.loads(cleaned_json)
                                            metadata["AI_METADATA_JSON"] = parsed_metadata
                                        except Exception as e:
                                            # Si le parsing JSON échoue, afficher comme texte brut
                                            metadata[f"PNG_tEXt_{keyword}"] = f"Error parsing JSON: {str(e)}"
                                    elif keyword == "metadata":
                                        # Ancien format (pour compatibilité)
                                        try:
                                            import json
                                            # Nettoyer le JSON
                                            cleaned_json = text_data.strip()
                                            parsed_metadata = json.loads(cleaned_json)
                                            metadata["AI_METADATA_JSON"] = parsed_metadata
                                        except:
                                            # Si le parsing JSON échoue, afficher comme texte brut
                                            metadata[f"PNG_tEXt_{keyword}"] = text_data
                                    else:
                                        # Afficher les autres métadonnées trouvées
                                        metadata[f"PNG_tEXt_{keyword}"] = text_data
                            except:
                                continue
                                
                        # Chercher aussi dans les chunks zTXt (métadonnées compressées)
                        ztxt_chunks = re.findall(b'zTXt(.*?)(?=zTXt|IDAT|IEND)', data, re.DOTALL)
                        
                        for chunk in ztxt_chunks:
                            try:
                                null_pos = chunk.find(b'\0')
                                if null_pos != -1:
                                    keyword = chunk[:null_pos].decode('utf-8', errors='ignore')
                                    
                                    # Vérifier si c'est notre JSON de métadonnées (nouveau format non compressé)
                                    if keyword == "AI_METADATA_JSON" or keyword == "AI" or keyword == "AI_META":
                                        try:
                                            import json
                                            import zlib
                                            
                                            # Les données zTXt sont compressées avec zlib
                                            # Format: keyword\0compression_method\0compressed_data
                                            compression_method = chunk[null_pos + 1]
                                            if compression_method == 0:  # zlib compression
                                                compressed_data = chunk[null_pos + 2:]
                                                decompressed_data = zlib.decompress(compressed_data)
                                                text_data = decompressed_data.decode('utf-8', errors='ignore')
                                                
                                                # Parser le JSON
                                                cleaned_json = text_data.strip()
                                                parsed_metadata = json.loads(cleaned_json)
                                                metadata["AI_METADATA_JSON"] = parsed_metadata
                                            else:
                                                metadata[f"PNG_zTXt_{keyword}"] = f"Compression non supportée: {compression_method}"
                                        except Exception as e:
                                            metadata[f"PNG_zTXt_{keyword}"] = f"Error parsing JSON: {str(e)}"
                                    elif keyword == "metadata":
                                        # Ancien format compressé (pour compatibilité)
                                        try:
                                            import json
                                            import zlib
                                            
                                            # Les données zTXt sont compressées avec zlib
                                            # Format: keyword\0compression_method\0compressed_data
                                            compression_method = chunk[null_pos + 1]
                                            if compression_method == 0:  # zlib compression
                                                compressed_data = chunk[null_pos + 2:]
                                                decompressed_data = zlib.decompress(compressed_data)
                                                text_data = decompressed_data.decode('utf-8', errors='ignore')
                                                
                                                # Parser le JSON
                                                cleaned_json = text_data.strip()
                                                parsed_metadata = json.loads(cleaned_json)
                                                metadata["AI_METADATA_JSON"] = parsed_metadata
                                            else:
                                                metadata[f"PNG_zTXt_{keyword}"] = f"Compression non supportée: {compression_method}"
                                        except Exception as e:
                                            metadata[f"PNG_zTXt_{keyword}"] = f"Erreur décompression/parsing: {str(e)}"
                                    else:
                                        # Les données sont compressées, on les ignore pour l'instant
                                        metadata[f"PNG_zTXt_{keyword}"] = "Données compressées"
                            except Exception as e:
                                metadata[f"PNG_zTXt_{keyword}_error"] = f"Erreur lecture: {str(e)}"
                                continue
                                
                        # Chercher dans les chunks iTXt (métadonnées internationales)
                        itxt_chunks = re.findall(b'iTXt(.*?)(?=iTXt|IDAT|IEND)', data, re.DOTALL)
                        
                        for chunk in itxt_chunks:
                            try:
                                null_pos = chunk.find(b'\0')
                                if null_pos != -1:
                                    keyword = chunk[:null_pos].decode('utf-8', errors='ignore')
                                    # Essayer d'extraire le texte après les métadonnées de langue
                                    text_start = chunk.find(b'\0', null_pos + 1)
                                    if text_start != -1:
                                        text_data = chunk[text_start+1:].decode('utf-8', errors='ignore')
                                        metadata[f"PNG_iTXt_{keyword}"] = text_data
                            except:
                                continue
                                
                    except Exception as e:
                        metadata["Erreur extraction PNG"] = str(e)
                
                # Essayer d'extraire les métadonnées EXIF pour JPEG
                elif file_info.suffix.lower() in ['.jpg', '.jpeg']:
                    # Les métadonnées EXIF sont plus complexes à extraire sans bibliothèque spécialisée
                    # On peut essayer de chercher des patterns dans les données
                    try:
                        with open(file_path, 'rb') as f:
                            data = f.read()
                            
                        # Chercher des patterns de métadonnées AI courants
                        patterns = [
                            (b'prompt', 'Prompt'),
                            (b'negative_prompt', 'Negative Prompt'),
                            (b'seed', 'Seed'),
                            (b'steps', 'Steps'),
                            (b'cfg', 'CFG'),
                            (b'sampler', 'Sampler'),
                            (b'model', 'Model'),
                            (b'stable diffusion', 'Stable Diffusion'),
                            (b'comfyui', 'ComfyUI'),
                            (b'parameters', 'Parameters'),
                            (b'comment', 'Comment'),
                            (b'description', 'Description'),
                            (b'software', 'Software'),
                            (b'artist', 'Artist'),
                            (b'copyright', 'Copyright'),
                        ]
                        
                        for pattern, label in patterns:
                            if pattern in data.lower():
                                # Essayer d'extraire le contexte autour du pattern
                                pos = data.lower().find(pattern)
                                if pos != -1:
                                    start = max(0, pos - 50)
                                    end = min(len(data), pos + 100)
                                    context = data[start:end].decode('utf-8', errors='ignore')
                                    metadata[f"JPEG_Trouvé_{label}"] = context
                                    
                        # Chercher aussi les sections EXIF
                        exif_sections = re.findall(b'Exif(.*?)(?=Exif|JFIF|EOI)', data, re.DOTALL)
                        for i, section in enumerate(exif_sections):
                            try:
                                # Essayer d'extraire du texte lisible
                                text_data = section.decode('utf-8', errors='ignore')
                                if len(text_data.strip()) > 10:  # Seulement si il y a du contenu
                                    metadata[f"JPEG_EXIF_Section_{i}"] = text_data[:200] + "..." if len(text_data) > 200 else text_data
                            except:
                                continue
                                
                    except Exception as e:
                        metadata["Erreur extraction JPEG"] = str(e)
                        
        except Exception as e:
            metadata["Erreur générale"] = str(e)

        # Créer la boîte de dialogue
        dlg = QDialog(self)
        dlg.setWindowTitle("Preview and metadata")
        dlg.setMinimumWidth(600)
        dlg.setMinimumHeight(500)
        vbox = QVBoxLayout(dlg)

        # Aperçu
        preview = QLabel(dlg)
        scaled_pixmap = pixmap.scaledToWidth(300, Qt.SmoothTransformation)
        preview.setPixmap(scaled_pixmap)
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet("border: 1px solid #555; border-radius: 3px; padding: 8px;")
        vbox.addWidget(preview)

        # Métadonnées
        meta_text = QTextEdit(dlg)
        meta_text.setReadOnly(True)
        meta_text.setMaximumHeight(350)
        meta_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        meta_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                background-color: rgba(30, 30, 30, 0.8);
                border: 1px solid #444;
                border-radius: 3px;
                color: #e0e0e0;
                padding: 12px;
            }
        """)
        
        if metadata:
            formatted_lines = []
            has_ai_metadata = False
            
            # Vérifier d'abord si on a nos métadonnées JSON
            if "AI_METADATA_JSON" in metadata:
                has_ai_metadata = True
                ai_metadata = metadata["AI_METADATA_JSON"]
                
                formatted_lines.append("=== AI METADATA (Krita Extension) ===")
                formatted_lines.append("")
                
                # Afficher les métadonnées de base
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
                
                if "sampler" in ai_metadata and ai_metadata["sampler"]:
                    formatted_lines.append("SAMPLER:")
                    formatted_lines.append(ai_metadata["sampler"])
                    formatted_lines.append("")
                
                if "loras" in ai_metadata and ai_metadata["loras"]:
                    formatted_lines.append("LORAS:")
                    if isinstance(ai_metadata["loras"], list):
                        for lora in ai_metadata["loras"]:
                            if isinstance(lora, dict):
                                name = lora.get("name", "Unknown")
                                strength = lora.get("strength", 1.0)
                                formatted_lines.append(f"  • {name} (force: {strength})")
                    else:
                        formatted_lines.append(str(ai_metadata["loras"]))
                    formatted_lines.append("")
                
                if "generation_type" in ai_metadata:
                    formatted_lines.append("INFORMATION:")
                    formatted_lines.append(f"Type: {ai_metadata['generation_type']}")
                    if "job_kind" in ai_metadata:
                        formatted_lines.append(f"Job: {ai_metadata['job_kind']}")
                    if "timestamp" in ai_metadata:
                        formatted_lines.append(f"Generated: {ai_metadata['timestamp']}")
                    if "batch_index" in ai_metadata:
                        formatted_lines.append(f"Index: {ai_metadata['batch_index']}")
                    if "total_images" in ai_metadata:
                        formatted_lines.append(f"Total: {ai_metadata['total_images']} image(s)")
                    formatted_lines.append("")
                
                # Display other parameters
                other_params = {k: v for k, v in ai_metadata.items() 
                              if k.startswith("param_") and k not in ["prompt", "negative_prompt", "style", "checkpoint", "sampler", "loras"]}
                if other_params:
                    formatted_lines.append("OTHER PARAMETERS:")
                    for key, value in other_params.items():
                        param_name = key.replace("param_", "")
                        formatted_lines.append(f"  • {param_name}: {value}")
                    formatted_lines.append("")
                
                if ai_metadata.get("truncated", False):
                    formatted_lines.append("⚠️  TRUNCATED METADATA (too large)")
                    formatted_lines.append("")
            
            # Traiter les autres métadonnées (ancien format ou autres)
            for k, v in metadata.items():
                if k.startswith("AI_prompt") and isinstance(v, str):
                    has_ai_metadata = True
                    # Essayer de parser et formater le JSON
                    try:
                        import json
                        # Nettoyer le JSON en supprimant les caractères parasites
                        cleaned_json = v.strip()
                        # Chercher la fin du JSON valide (dernière accolade fermante)
                        last_brace = cleaned_json.rfind('}')
                        if last_brace != -1:
                            cleaned_json = cleaned_json[:last_brace + 1]
                        
                        parsed = json.loads(cleaned_json)
                        formatted_lines.append("=== AI METADATA (Old format) ===")
                        formatted_lines.append("")
                        
                        # Extraire directement les informations importantes
                        for node_id, node_data in parsed.items():
                            class_type = node_data.get("class_type", "")
                            inputs = node_data.get("inputs", {})
                            
                            if class_type == "CLIPTextEncode":
                                text = inputs.get("text", "")
                                if any(word in text.lower() for word in ["worst", "bad", "low quality", "watermark"]):
                                    formatted_lines.append("NEGATIVE PROMPT:")
                                    formatted_lines.append(text)
                                    formatted_lines.append("")
                                else:
                                    formatted_lines.append("PROMPT:")
                                    formatted_lines.append(text)
                                    formatted_lines.append("")
                                    
                            elif class_type == "KSampler":
                                formatted_lines.append("PARAMETERS:")
                                formatted_lines.append(f"Seed: {inputs.get('seed', 'N/A')}")
                                formatted_lines.append(f"Steps: {inputs.get('steps', 'N/A')}")
                                formatted_lines.append(f"CFG: {inputs.get('cfg', 'N/A')}")
                                formatted_lines.append(f"Sampler: {inputs.get('sampler_name', 'N/A')}")
                                formatted_lines.append(f"Scheduler: {inputs.get('scheduler', 'N/A')}")
                                formatted_lines.append("")
                                
                            elif class_type == "CheckpointLoaderSimple":
                                formatted_lines.append("MODEL:")
                                formatted_lines.append(inputs.get("ckpt_name", "N/A"))
                                formatted_lines.append("")
                                
                            elif class_type == "LoraLoader":
                                lora_name = inputs.get("lora_name", "")
                                if lora_name:
                                    formatted_lines.append("LORA:")
                                    formatted_lines.append(f"Name: {lora_name}")
                                    formatted_lines.append(f"Strength Model: {inputs.get('strength_model', 'N/A')}")
                                    formatted_lines.append(f"Strength Clip: {inputs.get('strength_clip', 'N/A')}")
                                    formatted_lines.append("")
                                    
                            elif class_type == "EmptyLatentImage":
                                formatted_lines.append("DIMENSIONS:")
                                formatted_lines.append(f"Width: {inputs.get('width', 'N/A')}")
                                formatted_lines.append(f"Height: {inputs.get('height', 'N/A')}")
                                formatted_lines.append("")
                            
                    except Exception as e:
                        # En cas d'erreur, afficher le JSON brut mais formaté
                        formatted_lines.append("=== AI METADATA (RAW JSON) ===")
                        formatted_lines.append("")
                        formatted_lines.append(f"ERROR: {str(e)}")
                        formatted_lines.append("")
                        try:
                            import json
                            parsed = json.loads(v)
                            formatted_json = json.dumps(parsed, indent=2, ensure_ascii=False)
                            # Diviser le JSON en lignes pour un meilleur affichage
                            for line in formatted_json.split('\n'):
                                formatted_lines.append(line)
                        except:
                            formatted_lines.append(v)
                        formatted_lines.append("")
                else:
                    formatted_lines.append(f"{k}: {v}")
            
            # Afficher toutes les métadonnées trouvées
            if has_ai_metadata:
                formatted_lines.append("")
                formatted_lines.append("=== DETECTED AI METADATA ===")
                formatted_lines.append("")
            else:
                formatted_lines.append("")
                formatted_lines.append("=== AVAILABLE METADATA ===")
                formatted_lines.append("")
                formatted_lines.append("No AI generation metadata found, but here are all available metadata:")
                formatted_lines.append("")
            
            meta_text.setPlainText("\n".join(formatted_lines))
        else:
            meta_text.setPlainText("No metadata found.")
        vbox.addWidget(meta_text)

        # Boutons
        buttons_layout = QHBoxLayout()
        
        # Copy button
        copy_btn = QPushButton("Copy", dlg)
        copy_btn.setFixedSize(80, 30)
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(meta_text.toPlainText()))
        buttons_layout.addWidget(copy_btn)
        
        # Espace flexible
        buttons_layout.addStretch()
        
        # Bouton OK
        ok_btn = QPushButton("OK", dlg)
        ok_btn.setFixedSize(80, 30)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0.8);
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 0.9);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 0.9);
            }
        """)
        ok_btn.clicked.connect(dlg.accept)
        buttons_layout.addWidget(ok_btn)
        
        vbox.addLayout(buttons_layout)

        dlg.exec_()


_region_mask_button_icons = {
    True: theme.icon("region-alpha-active"),
    False: theme.icon("region-alpha"),
}
