from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QProcess, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QColor, QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from avatar_controller.studio.bootstrap import initialize_studio
from avatar_controller.studio.analysis_report import load_profile_analysis
from avatar_controller.studio.commands import StudioCommand, StudioCommandBuilder
from avatar_controller.studio.profiles import (
    AvatarProfile,
    AvatarProfileStore,
    ProfileStatus,
    StudioProfileError,
)
from avatar_controller.studio.video_preflight import (
    TimingClassification,
    VideoTimingReport,
)
from avatar_controller.segments import SegmentError, load_segments, validate_segments
from avatar_controller.video_io import VideoIOError, read_video_metadata


STATUS_LABELS = {
    ProfileStatus.NEEDS_ANALYSIS: "Pendiente de análisis",
    ProfileStatus.REVIEW_REQUIRED: "Revisión necesaria",
    ProfileStatus.READY: "Listo para usar",
}

STATUS_COLORS = {
    ProfileStatus.NEEDS_ANALYSIS: "#e9b85e",
    ProfileStatus.REVIEW_REQUIRED: "#ef8f78",
    ProfileStatus.READY: "#6fb8ff",
}

EDIT_SEGMENTS_BUTTON_TEXT = "Corregir segmentos"
KEY_GUIDE_TEXT = (
    "Flechas o WASD  Movimiento     R  Centro     Espacio  Pausa     Q  Salir"
)
VIDEO_TIMING_REPORT_FILENAME = "video_timing_report.json"
PROFILE_MUTATION_ROLES = frozenset({"analysis", "edit"})


class MetricBox(QFrame):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricBox")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self.value_label = QLabel("-")
        self.value_label.setObjectName("metricValue")
        title = QLabel(label.upper())
        title.setObjectName("metricLabel")
        layout.addWidget(self.value_label)
        layout.addWidget(title)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class AvatarStudioWindow(QMainWindow):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root.resolve()
        self.store: AvatarProfileStore = initialize_studio(self.project_root)
        self.commands = StudioCommandBuilder(self.project_root)
        self.current_profile: AvatarProfile | None = None
        self.processes: list[QProcess] = []
        self._pending_automatic_analysis_profile_ids: list[str] = []

        self.setWindowTitle("Avatar Studio")
        self.setMinimumSize(1180, 760)
        self.resize(1380, 860)
        self.setStyleSheet(STYLESHEET)

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.0)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.mediaStatusChanged.connect(self._on_media_status)

        self._build_ui()
        self._load_profiles()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(286)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(24, 26, 20, 22)
        sidebar_layout.setSpacing(16)

        brand = QLabel("AVATAR\nSTUDIO")
        brand.setObjectName("brand")
        sidebar_layout.addWidget(brand)
        subtitle = QLabel("Biblioteca de avatares de vídeo")
        subtitle.setObjectName("sidebarSubtitle")
        subtitle.setWordWrap(True)
        sidebar_layout.addWidget(subtitle)

        self.import_button = QPushButton("Importar vídeo")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.import_button.clicked.connect(self._import_video)
        sidebar_layout.addWidget(self.import_button)

        library_label = QLabel("PERFILES")
        library_label.setObjectName("sectionLabel")
        sidebar_layout.addWidget(library_label)

        self.profile_list = QListWidget()
        self.profile_list.setObjectName("profileList")
        self.profile_list.setSpacing(5)
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        sidebar_layout.addWidget(self.profile_list, 1)

        policy = QLabel(
            "Los vídeos originales nunca se editan. Un perfil nuevo permanece experimental hasta su revisión."
        )
        policy.setObjectName("policyText")
        policy.setWordWrap(True)
        sidebar_layout.addWidget(policy)
        shell.addWidget(sidebar)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(34, 26, 34, 28)
        workspace_layout.setSpacing(18)

        header = QHBoxLayout()
        heading_column = QVBoxLayout()
        heading_column.setSpacing(2)
        self.profile_name = QLabel("Avatar")
        self.profile_name.setObjectName("pageTitle")
        self.video_path = QLabel("")
        self.video_path.setObjectName("pathLabel")
        self.video_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        heading_column.addWidget(self.profile_name)
        heading_column.addWidget(self.video_path)
        header.addLayout(heading_column, 1)
        self.status_badge = QLabel("-")
        self.status_badge.setObjectName("statusBadge")
        header.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        workspace_layout.addLayout(header)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setObjectName("contentSplitter")
        content_splitter.setChildrenCollapsible(False)

        preview_panel = QFrame()
        preview_panel.setObjectName("previewPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        self.video_widget = QVideoWidget()
        self.video_widget.setObjectName("videoWidget")
        self.video_widget.setMinimumSize(640, 360)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.media_player.setVideoOutput(self.video_widget)
        preview_layout.addWidget(self.video_widget, 1)

        media_bar = QFrame()
        media_bar.setObjectName("mediaBar")
        media_layout = QHBoxLayout(media_bar)
        media_layout.setContentsMargins(14, 10, 14, 10)
        self.media_toggle = QPushButton("Pausar vídeo")
        self.media_toggle.setObjectName("quietButton")
        self.media_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.media_toggle.clicked.connect(self._toggle_media)
        media_layout.addWidget(self.media_toggle)
        media_layout.addStretch(1)
        media_note = QLabel("Vista previa del archivo original · sin filtros")
        media_note.setObjectName("mediaNote")
        media_layout.addWidget(media_note)
        preview_layout.addWidget(media_bar)
        content_splitter.addWidget(preview_panel)

        inspector = QFrame()
        inspector.setObjectName("inspector")
        inspector.setMinimumWidth(310)
        inspector.setMaximumWidth(360)
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(22, 22, 22, 22)
        inspector_layout.setSpacing(14)
        inspector_title = QLabel("Preparación")
        inspector_title.setObjectName("panelTitle")
        inspector_layout.addWidget(inspector_title)
        self.stage_text = QLabel("")
        self.stage_text.setObjectName("stageText")
        self.stage_text.setWordWrap(True)
        inspector_layout.addWidget(self.stage_text)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setObjectName("analysisProgress")
        self.analysis_progress.setRange(0, 0)
        self.analysis_progress.setTextVisible(False)
        self.analysis_progress.hide()
        inspector_layout.addWidget(self.analysis_progress)

        self.analyze_button = self._action_button(
            "Analizar movimientos",
            QStyle.StandardPixmap.SP_BrowserReload,
            self._analyze_profile,
        )
        self.review_button = self._action_button(
            "Revisar segmentos",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            self._review_profile,
        )
        self.edit_button = self._action_button(
            EDIT_SEGMENTS_BUTTON_TEXT,
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            self._edit_profile,
        )
        self.confirm_button = self._action_button(
            "Confirmar revisión",
            QStyle.StandardPixmap.SP_DialogApplyButton,
            self._confirm_review,
        )
        inspector_layout.addWidget(self.analyze_button)
        inspector_layout.addWidget(self.review_button)
        inspector_layout.addWidget(self.edit_button)
        inspector_layout.addWidget(self.confirm_button)
        inspector_layout.addSpacing(8)

        output_title = QLabel("SALIDA")
        output_title.setObjectName("sectionLabel")
        inspector_layout.addWidget(output_title)
        self.preview_button = self._action_button(
            "Abrir controlador",
            QStyle.StandardPixmap.SP_MediaPlay,
            self._launch_preview,
            primary=True,
        )
        self.camera_button = self._action_button(
            "Activar cámara virtual",
            QStyle.StandardPixmap.SP_ComputerIcon,
            self._launch_virtual_camera,
        )
        inspector_layout.addWidget(self.preview_button)
        inspector_layout.addWidget(self.camera_button)
        inspector_layout.addStretch(1)

        controls = QLabel(KEY_GUIDE_TEXT)
        controls.setObjectName("keyGuide")
        controls.setWordWrap(True)
        inspector_layout.addWidget(controls)
        content_splitter.addWidget(inspector)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 0)
        workspace_layout.addWidget(content_splitter, 1)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(10)
        self.resolution_metric = MetricBox("Resolución")
        self.fps_metric = MetricBox("Fotogramas por segundo")
        self.duration_metric = MetricBox("Duración")
        self.frames_metric = MetricBox("Fotogramas")
        metrics.addWidget(self.resolution_metric, 0, 0)
        metrics.addWidget(self.fps_metric, 0, 1)
        metrics.addWidget(self.duration_metric, 0, 2)
        metrics.addWidget(self.frames_metric, 0, 3)
        workspace_layout.addLayout(metrics)

        self.detail_tabs = QTabWidget()
        self.detail_tabs.setObjectName("detailTabs")

        analysis_page = QWidget()
        analysis_layout = QVBoxLayout(analysis_page)
        analysis_layout.setContentsMargins(8, 10, 8, 8)
        analysis_layout.setSpacing(8)
        self.analysis_summary_label = QLabel("")
        self.analysis_summary_label.setObjectName("analysisSummary")
        analysis_layout.addWidget(self.analysis_summary_label)
        self.analysis_table = QTableWidget(0, 5)
        self.analysis_table.setObjectName("analysisTable")
        self.analysis_table.setHorizontalHeaderLabels(
            ["Segmento", "Rango", "Duración", "Confianza", "Estado"]
        )
        self.analysis_table.verticalHeader().setVisible(False)
        self.analysis_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.analysis_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.analysis_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.analysis_table.setAlternatingRowColors(True)
        header_view = self.analysis_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        analysis_layout.addWidget(self.analysis_table)
        self.detail_tabs.addTab(analysis_page, "Segmentos")

        self.log_output = QTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("La actividad de análisis aparecerá aquí.")
        self.detail_tabs.addTab(self.log_output, "Actividad")
        self.detail_tabs.setMaximumHeight(245)
        workspace_layout.addWidget(self.detail_tabs)
        shell.addWidget(workspace, 1)

    def _action_button(
        self,
        text: str,
        icon: QStyle.StandardPixmap,
        callback: Callable[[], None],
        *,
        primary: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("primaryButton" if primary else "actionButton")
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(QSize(18, 18))
        button.clicked.connect(callback)
        return button

    def _load_profiles(self, select_id: str | None = None) -> None:
        previous_id = select_id or (self.current_profile.profile_id if self.current_profile else None)
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        selected_item: QListWidgetItem | None = None
        for profile in self.store.list_profiles():
            item = QListWidgetItem(f"{profile.name}\n{STATUS_LABELS[profile.status]}")
            item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
            item.setSizeHint(QSize(220, 64))
            item.setToolTip(str(profile.video_path))
            self.profile_list.addItem(item)
            if profile.profile_id == previous_id or selected_item is None:
                selected_item = item
        self.profile_list.blockSignals(False)
        if selected_item is not None:
            self.profile_list.setCurrentItem(selected_item)
            self._select_profile(str(selected_item.data(Qt.ItemDataRole.UserRole)))

    def _on_profile_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is not None:
            self._select_profile(str(current.data(Qt.ItemDataRole.UserRole)))

    def _select_profile(self, profile_id: str) -> None:
        try:
            profile = self.store.get_profile(profile_id)
        except StudioProfileError as exc:
            self._show_error(str(exc))
            return
        self.current_profile = profile
        self.profile_name.setText(profile.name)
        self.video_path.setText(str(profile.video_path))
        color = STATUS_COLORS[profile.status]
        self.status_badge.setText(STATUS_LABELS[profile.status])
        self.status_badge.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; background: transparent;"
        )
        self.resolution_metric.set_value(f"{profile.width} × {profile.height}")
        self.fps_metric.set_value(f"{profile.fps:.2f}")
        self.duration_metric.set_value(self._duration(profile.duration_seconds))
        self.frames_metric.set_value(f"{profile.frame_count:,}".replace(",", "."))
        self._show_analysis(profile)
        self._update_actions(profile)
        self.media_player.stop()
        self.media_player.setSource(QUrl.fromLocalFile(str(profile.video_path)))
        QTimer.singleShot(180, self.media_player.play)
        self.media_toggle.setText("Pausar vídeo")
        self.media_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def _update_actions(self, profile: AvatarProfile) -> None:
        has_segments = profile.segments_path.exists()
        task_active = _profile_mutation_active(getattr(self, "processes", ()))
        self.analyze_button.setEnabled(not task_active)
        self.review_button.setEnabled(has_segments)
        self.edit_button.setEnabled(has_segments and not task_active)
        self.confirm_button.setEnabled(
            has_segments and profile.status is ProfileStatus.REVIEW_REQUIRED
        )
        self.preview_button.setEnabled(has_segments)
        self.camera_button.setEnabled(profile.status is ProfileStatus.READY)
        if profile.status is ProfileStatus.NEEDS_ANALYSIS:
            text = "Analiza el vídeo para localizar centro, izquierda, derecha, arriba y abajo."
        elif profile.status is ProfileStatus.REVIEW_REQUIRED:
            text = "La propuesta automática está lista. Revísala antes de publicar el avatar."
        else:
            text = "Perfil revisado y disponible para reproducción o cámara virtual."
        timing_note = _profile_timing_note(profile)
        if timing_note:
            text += f" {timing_note}"
        self.stage_text.setText(text)

    def _show_analysis(self, profile: AvatarProfile) -> None:
        summary = load_profile_analysis(profile)
        self.analysis_table.setRowCount(len(summary.segments))
        for row, segment in enumerate(summary.segments):
            range_text = (
                f"{segment.start_frame}–{segment.end_frame}"
                if segment.is_detected
                else "—"
            )
            duration_text = (
                f"{segment.duration_seconds:.2f} s"
                if segment.duration_seconds is not None
                else "—"
            )
            confidence_text = (
                f"{segment.confidence:.0%}"
                if segment.confidence is not None
                else "—"
            )
            if not segment.is_detected:
                state_text = "Falta"
                state_color = "#ef8f78"
            elif segment.warnings or (
                segment.confidence is not None and segment.confidence < 0.55
            ):
                state_text = "Revisar"
                state_color = "#e9b85e"
            else:
                state_text = "Correcto"
                state_color = "#4dd19d"
            values = [segment.name, range_text, duration_text, confidence_text, state_text]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 4:
                    item.setForeground(QColor(state_color))
                if segment.warnings:
                    item.setToolTip("\n".join(segment.warnings))
                self.analysis_table.setItem(row, column, item)

        method = f" · método: {summary.method}" if summary.method else ""
        if profile.status is ProfileStatus.NEEDS_ANALYSIS:
            self.analysis_summary_label.setText(
                "Análisis pendiente · se requieren 13 segmentos para los cinco estados."
            )
        else:
            self.analysis_summary_label.setText(
                f"{summary.detected_count}/{summary.required_count} segmentos detectados"
                f"{method}"
            )

    def _import_video(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Importar vídeo de avatar",
            str(Path.home()),
            "Vídeos (*.mp4 *.mov *.mkv *.avi *.webm)",
        )
        if not filename:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            metadata = read_video_metadata(filename)
            profile = self.store.create_imported_profile(filename, metadata)
        except (VideoIOError, StudioProfileError) as exc:
            self._show_error(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.log_output.append(f"Vídeo importado: {profile.video_path}")
        self._load_profiles(profile.profile_id)
        timing_report_path = profile.config_path.parent / VIDEO_TIMING_REPORT_FILENAME
        if timing_report_path.exists():
            if profile.status is ProfileStatus.NEEDS_ANALYSIS:
                self.log_output.append(
                    "La cadencia ya estaba comprobada. Separando automáticamente "
                    "los cinco movimientos del avatar."
                )
                self._start_profile_analysis(profile, automatic=True)
            return
        try:
            command = self.commands.inspect_timing(profile, timing_report_path)
        except StudioProfileError as exc:
            self.log_output.append(
                f"No se pudo iniciar el diagnóstico de cadencia: {exc}"
            )
            return
        self.log_output.append(
            "Comprobando la cadencia del vídeo en segundo plano; "
            "puedes seguir usando Avatar Studio."
        )
        self._start_process(
            command,
            "Diagnóstico de cadencia",
            role="timing",
            on_success=lambda: self._timing_inspection_complete(profile.profile_id),
        )

    def _timing_inspection_complete(self, profile_id: str) -> None:
        self.log_output.append(
            "Diagnóstico de cadencia completado sin modificar el vídeo original."
        )
        self._load_profiles(profile_id)
        try:
            profile = self.store.get_profile(profile_id)
        except StudioProfileError as exc:
            self._show_error(str(exc))
            return
        if profile.status is ProfileStatus.NEEDS_ANALYSIS:
            self.log_output.append(
                "Separando automáticamente centro, derecha, izquierda, arriba y abajo; "
                "después solo tendrás que revisar el resultado."
            )
            if _profile_mutation_active(getattr(self, "processes", ())):
                self._enqueue_automatic_analysis(profile.profile_id)
                return
            self._start_profile_analysis(profile, automatic=True)

    def _analyze_profile(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        self._start_profile_analysis(profile, automatic=False)

    def _start_profile_analysis(
        self,
        profile: AvatarProfile,
        *,
        automatic: bool,
    ) -> bool:
        if _profile_mutation_active(getattr(self, "processes", ())):
            if automatic:
                self._enqueue_automatic_analysis(profile.profile_id)
            else:
                self._show_error("Espera a que termine el análisis o editor en curso")
            return False
        try:
            command = self.commands.analyze(profile)
        except StudioProfileError as exc:
            if automatic:
                self.log_output.append(
                    f"No se pudo iniciar la separación automática: {exc}"
                )
            else:
                self._show_error(str(exc))
            return False
        self.analysis_progress.show()
        self.analyze_button.setEnabled(False)
        self.import_button.setEnabled(True)
        self.detail_tabs.setCurrentWidget(self.log_output)
        self._start_process(
            command,
            "Preparación automática del avatar" if automatic else "Análisis automático",
            role="analysis",
            on_success=lambda: self._analysis_complete(profile.profile_id),
        )
        return True

    def _automatic_analysis_queue(self) -> list[str]:
        queue = getattr(self, "_pending_automatic_analysis_profile_ids", None)
        if queue is None:
            queue = []
            self._pending_automatic_analysis_profile_ids = queue
        return queue

    def _enqueue_automatic_analysis(self, profile_id: str) -> bool:
        queue = self._automatic_analysis_queue()
        if profile_id in queue:
            self.log_output.append(
                "Este vídeo ya estaba en la cola de preparación automática."
            )
            return False
        queue.append(profile_id)
        self.log_output.append(
            "Hay otro perfil en preparación. Este vídeo queda en cola y se "
            "analizará automáticamente a continuación."
        )
        return True

    def _drain_pending_automatic_analysis(self) -> bool:
        if _profile_mutation_active(getattr(self, "processes", ())):
            return False

        queue = self._automatic_analysis_queue()
        while queue:
            profile_id = queue.pop(0)
            try:
                profile = self.store.get_profile(profile_id)
            except StudioProfileError:
                continue
            if profile.status is not ProfileStatus.NEEDS_ANALYSIS:
                continue
            if self._start_profile_analysis(profile, automatic=True):
                return True
            if _profile_mutation_active(getattr(self, "processes", ())):
                return False
        return False

    def _analysis_complete(self, profile_id: str) -> None:
        updated = self.store.update_status(profile_id, ProfileStatus.REVIEW_REQUIRED)
        self.log_output.append("Análisis completado. Revisión visual obligatoria.")
        self._load_profiles(updated.profile_id)

    def _review_profile(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        try:
            command = self.commands.review(profile)
        except StudioProfileError as exc:
            self._show_error(str(exc))
            return
        self._start_process(command, "Revisión de segmentos", role="review")

    def _edit_profile(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        if _profile_mutation_active(getattr(self, "processes", ())):
            self._show_error("Espera a que termine el análisis o editor en curso")
            return
        try:
            command = self.commands.edit(profile)
        except StudioProfileError as exc:
            self._show_error(str(exc))
            return
        original_digest = _file_sha256(profile.segments_path)
        if original_digest is None:
            self._show_error(
                f"No se pudo leer el archivo de segmentos: {profile.segments_path}"
            )
            return
        self.media_player.pause()
        self.edit_button.setEnabled(False)
        self.detail_tabs.setCurrentWidget(self.log_output)
        self._start_process(
            command,
            "Editor manual de segmentos",
            role="edit",
            on_finished=lambda exit_code: self._segments_edit_complete(
                profile.profile_id,
                original_digest,
                exit_code,
            ),
        )

    def _segments_edit_complete(
        self,
        profile_id: str,
        original_digest: str,
        exit_code: int = 0,
    ) -> None:
        try:
            profile = self.store.get_profile(profile_id)
            current_digest = _file_sha256(profile.segments_path)
            if current_digest != original_digest:
                self.store.invalidate_continuity_after_segment_edit(profile_id)
                outcome = (
                    " aunque el editor notificó un error"
                    if exit_code != 0
                    else ""
                )
                self.log_output.append(
                    f"Segmentos modificados{outcome}. "
                    "El perfil vuelve a requerir revisión."
                )
            else:
                self.log_output.append(
                    "Editor manual cerrado sin cambios en los segmentos."
                )
        except StudioProfileError as exc:
            self._show_error(str(exc))
        self._load_profiles(profile_id)

    def _confirm_review(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        response = QMessageBox.question(
            self,
            "Confirmar revisión visual",
            "¿Has comprobado los movimientos y los loops del perfil completo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response == QMessageBox.StandardButton.Yes:
            try:
                segment_set = load_segments(profile.segments_path)
                validation = validate_segments(segment_set, profile.frame_count)
            except SegmentError as exc:
                self._show_error(str(exc))
                return
            if validation.errors:
                details = "\n".join(f"• {issue.format()}" for issue in validation.errors[:5])
                self._show_error(
                    "El perfil todavía no está completo y no puede publicarse:\n\n" + details
                )
                return
            updated = self.store.update_status(profile.profile_id, ProfileStatus.READY)
            self._load_profiles(updated.profile_id)

    def _launch_preview(self) -> None:
        self._launch_output(virtual_camera=False)

    def _launch_virtual_camera(self) -> None:
        self._launch_output(virtual_camera=True)

    def _launch_output(self, *, virtual_camera: bool) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        try:
            command = self.commands.preview(profile, virtual_camera=virtual_camera)
        except StudioProfileError as exc:
            self._show_error(str(exc))
            return
        self.media_player.pause()
        label = "Cámara virtual" if virtual_camera else "Controlador de avatar"
        self._start_process(command, label, role="playback")

    def _start_process(
        self,
        command: StudioCommand,
        label: str,
        *,
        role: str,
        on_success: Callable[[], None] | None = None,
        on_finished: Callable[[int], None] | None = None,
    ) -> None:
        process = QProcess(self)
        process.setWorkingDirectory(str(self.project_root))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setProperty("studio_role", role)
        process.readyReadStandardOutput.connect(lambda: self._read_process(process))

        def finished(exit_code: int, _status: QProcess.ExitStatus) -> None:
            try:
                self._read_process(process)
                if role == "analysis":
                    self.analysis_progress.hide()
                    self.import_button.setEnabled(True)
                if exit_code == 0:
                    self.log_output.append(f"{label}: finalizado correctamente.")
                    if on_success is not None:
                        on_success()
                else:
                    self.log_output.append(f"{label}: terminó con código {exit_code}.")
                if on_finished is not None:
                    on_finished(exit_code)
            finally:
                if process in self.processes:
                    self.processes.remove(process)
                process.deleteLater()
                try:
                    if self.current_profile is not None:
                        self._update_actions(self.current_profile)
                finally:
                    if role in PROFILE_MUTATION_ROLES:
                        self._drain_pending_automatic_analysis()

        process.finished.connect(finished)
        self.processes.append(process)
        self.log_output.append(f"{label}: iniciando…")
        process.start(command.program, list(command.arguments))
        if role in PROFILE_MUTATION_ROLES and self.current_profile is not None:
            self._update_actions(self.current_profile)

    def _read_process(self, process: QProcess) -> None:
        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        if output:
            self.log_output.append(output)

    def _toggle_media(self) -> None:
        if self.media_player.playbackState() is QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.media_toggle.setText("Reanudar vídeo")
            self.media_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        else:
            self.media_player.play()
            self.media_toggle.setText("Pausar vídeo")
            self.media_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status is QMediaPlayer.MediaStatus.EndOfMedia:
            self.media_player.setPosition(0)
            self.media_player.play()

    def _require_profile(self) -> AvatarProfile | None:
        if self.current_profile is None:
            self._show_error("Selecciona un perfil de avatar")
        return self.current_profile

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Avatar Studio", message)

    @staticmethod
    def _duration(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        minutes, remaining = divmod(total, 60)
        return f"{minutes}:{remaining:02d}"

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.media_player.stop()
        for process in list(self.processes):
            if process.state() is not QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(1500):
                    process.kill()
                    process.waitForFinished(1000)
        event.accept()


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _profile_mutation_active(processes: Iterable[QProcess]) -> bool:
    for process in processes:
        if (
            process.property("studio_role") in PROFILE_MUTATION_ROLES
            and process.state() is not QProcess.ProcessState.NotRunning
        ):
            return True
    return False


def _profile_timing_note(profile: AvatarProfile) -> str | None:
    report_path = profile.config_path.parent / VIDEO_TIMING_REPORT_FILENAME
    if not report_path.exists():
        return None
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        classification = TimingClassification(str(raw.get("classification")))
    except (OSError, json.JSONDecodeError, ValueError):
        return "No se pudo leer el diagnóstico de cadencia del vídeo."
    return _timing_note(classification)


def _timing_note(classification: TimingClassification) -> str | None:
    if classification is TimingClassification.CFR:
        return None
    if classification is TimingClassification.NEAR_CFR:
        return "Cadencia casi constante; compatible con una pequeña variación temporal."
    if classification is TimingClassification.VFR:
        return (
            "Cadencia variable detectada; el original se conserva y el análisis "
            "puede necesitar Corregir segmentos."
        )
    if classification is TimingClassification.INVALID_TIMESTAMPS:
        return (
            "Marcas de tiempo irregulares detectadas; revisa con cuidado los "
            "segmentos propuestos."
        )
    return "No se pudo verificar la cadencia; el vídeo se mantiene sin modificar."


def _timing_log_message(report: VideoTimingReport) -> str:
    note = _timing_note(report.classification)
    if note is None:
        note = "Cadencia constante verificada."
    fps_text = (
        f", mediana {report.median_fps:.2f} FPS"
        if report.median_fps is not None
        else ""
    )
    return (
        f"Cadencia: {report.classification.value} "
        f"({report.frames_observed} fotogramas{fps_text}). {note}"
    )


def run_studio(project_root: Path | str, *, smoke_test: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Avatar Studio")
    app.setOrganizationName("AvatarLab")
    app.setFont(QFont("Segoe UI Variable Text", 10))
    window = AvatarStudioWindow(Path(project_root))
    window.show()
    if smoke_test:
        QTimer.singleShot(350, app.quit)
    return app.exec()


STYLESHEET = """
QWidget {
    color: #f4f1e8;
    background: #17191b;
    font-family: "Segoe UI Variable Text", "Segoe UI";
    font-size: 14px;
}
#sidebar {
    background: #202326;
    border-right: 1px solid #34383b;
}
#brand {
    color: #f7f3e8;
    font-family: "Bahnschrift SemiCondensed";
    font-size: 27px;
    font-weight: 700;
    line-height: 0.9;
}
#sidebarSubtitle, #policyText, #pathLabel, #mediaNote {
    color: #9ea7a6;
}
#sidebarSubtitle { font-size: 13px; }
#policyText { font-size: 12px; line-height: 1.35; }
#sectionLabel, #metricLabel {
    color: #89918f;
    font-size: 11px;
    font-weight: 700;
}
#profileList {
    background: transparent;
    border: 0;
    outline: 0;
}
#profileList::item {
    background: #272b2e;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 10px 12px;
    color: #d8dcda;
}
#profileList::item:hover { background: #2d3235; }
#profileList::item:selected {
    background: #313836;
    border-color: #4dd19d;
    color: #ffffff;
}
#workspace { background: #17191b; }
#pageTitle {
    font-family: "Bahnschrift SemiCondensed";
    font-size: 31px;
    font-weight: 650;
}
#pathLabel { font-size: 12px; }
#statusBadge {
    border-radius: 5px;
    padding: 7px 12px;
    font-size: 12px;
    font-weight: 700;
}
#previewPanel, #inspector, #metricBox, #logOutput, #analysisTable {
    background: #23272a;
    border: 1px solid #353a3d;
    border-radius: 7px;
}
#videoWidget { background: #0d0e0f; border-radius: 7px; }
#mediaBar { background: #1e2224; border-top: 1px solid #34393c; }
#inspector { background: #202427; }
#panelTitle { font-size: 19px; font-weight: 650; }
#stageText { color: #b8c0bd; font-size: 13px; line-height: 1.35; }
#metricValue { font-size: 18px; font-weight: 650; color: #f8f4e9; }
#metricLabel { font-size: 10px; }
#keyGuide {
    color: #aeb6b3;
    background: #191c1e;
    border: 1px solid #33383a;
    border-radius: 6px;
    padding: 12px;
    font-family: "Cascadia Mono";
    font-size: 11px;
}
QPushButton {
    min-height: 40px;
    border-radius: 6px;
    padding: 0 14px;
    text-align: left;
    font-weight: 600;
}
#primaryButton {
    background: #4dd19d;
    color: #102019;
    border: 1px solid #4dd19d;
}
#primaryButton:hover { background: #62dda9; }
#primaryButton:pressed { background: #3fbd8c; }
#actionButton, #quietButton {
    background: #2a2f32;
    color: #e9ece8;
    border: 1px solid #3b4245;
}
#actionButton:hover, #quietButton:hover {
    border-color: #6f7a78;
    background: #303639;
}
QPushButton:disabled {
    color: #68706e;
    background: #222629;
    border-color: #2e3335;
}
#logOutput {
    color: #b8c2bf;
    padding: 8px;
    font-family: "Cascadia Mono";
    font-size: 11px;
}
#analysisSummary { color: #b8c2bf; font-size: 12px; padding: 0 4px; }
#analysisTable {
    gridline-color: #343a3d;
    selection-background-color: #303a37;
    alternate-background-color: #202427;
}
#analysisTable QHeaderView::section {
    background: #1d2022;
    color: #9ea7a6;
    border: 0;
    border-bottom: 1px solid #3a4043;
    padding: 7px 10px;
    font-size: 11px;
    font-weight: 700;
}
#detailTabs::pane { border: 1px solid #353a3d; border-radius: 6px; background: #202427; }
#detailTabs QTabBar::tab {
    background: #1c1f21;
    color: #929b99;
    border: 1px solid #34393c;
    padding: 8px 18px;
    min-width: 84px;
}
#detailTabs QTabBar::tab:selected { color: #f4f1e8; border-bottom-color: #4dd19d; }
#analysisProgress { height: 5px; border: 0; background: #303537; }
#analysisProgress::chunk { background: #4dd19d; }
QSplitter::handle { background: #17191b; width: 12px; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: #464d4f; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
