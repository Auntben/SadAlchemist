import os
import re
import shutil
import subprocess
import sys

from PyQt6.QtCore import Qt, QSize, QProcess, QSettings, QUrl, QRegularExpression, QLocale
from PyQt6.QtGui import (
    QIcon, QFont, QColor, QPixmap, QPainter, QDesktopServices, QKeySequence,
    QShortcut, QRegularExpressionValidator, QDoubleValidator, QValidator
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QFileDialog, QLabel, QLineEdit, QMessageBox, QComboBox,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QInputDialog, QProgressBar,
    QCheckBox, QHeaderView, QSpinBox
)

APP_NAME = "SadAlchemist"
APP_VERSION = "26.1"

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.exr')
AUDIO_EXTS = ('.wav', '.mp3', '.aac', '.flac', '.m4a', '.ogg',
              '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v')

# Every preset carries everything needed to build both the filename and the ffmpeg command.
# "codec": "h264" is resolved at render time to h264_nvenc or libx264.
# "even": scale to even dimensions (required by 4:2:0 / 4:2:2 chroma subsampling).
PRORES_AUDIO = ["-c:a", "pcm_s24le"]
PRESETS = [
    {"key": "h264", "label": "H.264 MP4 - Preview 25 Mbps", "ext": "mp4", "codec": "h264",
     "args": ["-b:v", "25M", "-movflags", "+faststart"], "pix_fmt": "yuv420p", "even": True,
     "audio": ["-c:a", "aac", "-b:a", "320k"]},
    {"key": "prores_proxy", "label": "ProRes 422 Proxy", "ext": "mov", "codec": "prores_ks",
     "args": ["-profile:v", "0", "-vendor", "apl0"], "pix_fmt": "yuv422p10le", "even": True,
     "audio": PRORES_AUDIO},
    {"key": "prores_lt", "label": "ProRes 422 LT", "ext": "mov", "codec": "prores_ks",
     "args": ["-profile:v", "1", "-vendor", "apl0"], "pix_fmt": "yuv422p10le", "even": True,
     "audio": PRORES_AUDIO},
    {"key": "prores_422", "label": "ProRes 422", "ext": "mov", "codec": "prores_ks",
     "args": ["-profile:v", "2", "-vendor", "apl0"], "pix_fmt": "yuv422p10le", "even": True,
     "audio": PRORES_AUDIO},
    {"key": "prores_hq", "label": "ProRes 422 HQ", "ext": "mov", "codec": "prores_ks",
     "args": ["-profile:v", "3", "-vendor", "apl0"], "pix_fmt": "yuv422p10le", "even": True,
     "audio": PRORES_AUDIO},
    {"key": "prores_4444", "label": "ProRes 4444 (keeps alpha)", "ext": "mov", "codec": "prores_ks",
     "args": ["-profile:v", "4", "-vendor", "apl0"], "pix_fmt": "yuva444p10le", "even": False,
     "audio": PRORES_AUDIO},
    {"key": "prores_4444xq", "label": "ProRes 4444 XQ (keeps alpha)", "ext": "mov", "codec": "prores_ks",
     "args": ["-profile:v", "5", "-vendor", "apl0"], "pix_fmt": "yuva444p10le", "even": False,
     "audio": PRORES_AUDIO},
]
PRESETS_BY_KEY = {p["key"]: p for p in PRESETS}

FPS_CHOICES = ["23.976", "24", "25", "29.97", "30", "48", "50", "59.94", "60"]
NTSC_RATES = {"23.976": "24000/1001", "29.97": "30000/1001",
              "47.952": "48000/1001", "59.94": "60000/1001"}

HWACCEL_CHOICES = ["Auto-detect", "NVIDIA (h264_nvenc)", "CPU (libx264)"]

# Tree columns
COL_REMOVE, COL_FOLDER, COL_FRAMES, COL_TAKE, COL_AUDIO, COL_OUTPUT, COL_STATUS = range(7)

SEQ_RE = re.compile(r"^(.*?)(\d+)(\.[^.]+)$")

if sys.platform == "win32":
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    CREATE_NO_WINDOW = 0


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def find_tool(name):
    """ Look for a bundled binary first, then the dev folders, then common install locations and PATH """
    exe = name + ".exe" if sys.platform == "win32" else name
    candidates = [resource_path(os.path.join("bin", exe))]
    if not hasattr(sys, '_MEIPASS'):
        dev_folder = "ffmpeg_win" if sys.platform == "win32" else "ffmpeg_osx"
        candidates.append(resource_path(os.path.join(dev_folder, exe)))
        candidates.append(resource_path(os.path.join("ffmpeg_bin", exe)))
    if sys.platform == "darwin":
        # GUI apps on macOS don't inherit the shell PATH
        candidates += [os.path.join("/opt/homebrew/bin", exe), os.path.join("/usr/local/bin", exe)]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return shutil.which(name)


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


def parse_fps(text):
    """ Returns (ffmpeg framerate string, float fps), or None if invalid """
    text = text.strip()
    try:
        value = float(text)
    except ValueError:
        return None
    if value <= 0 or value > 1000:
        return None
    if text in NTSC_RATES:
        num, den = NTSC_RATES[text].split("/")
        return NTSC_RATES[text], int(num) / int(den)
    return text, value


def scan_sequence(folder):
    """ Find the image sequence in a folder. Returns (info dict, None) or (None, error message). """
    try:
        names = os.listdir(folder)
    except OSError as e:
        return None, str(e)
    groups = {}
    for name in names:
        if not name.lower().endswith(IMAGE_EXTS):
            continue
        match = SEQ_RE.match(name)
        if match:
            prefix, digits, ext = match.groups()
            groups.setdefault((prefix, ext), []).append(digits)
    if not groups:
        return None, "No numbered image files found."

    # Use the largest sequence if the folder holds more than one
    (prefix, ext), digit_strings = max(groups.items(), key=lambda kv: len(kv[1]))
    frames = sorted(int(d) for d in digit_strings)
    # The smallest width works for padded, unpadded, and padded-then-overflowing numbering
    pad = min(len(d) for d in digit_strings)
    start, end = frames[0], frames[-1]

    # ffmpeg stops reading at the first missing frame
    first_gap = None
    for prev, cur in zip(frames, frames[1:]):
        if cur != prev + 1:
            first_gap = prev + 1
            break
    render_frames = (first_gap - start) if first_gap is not None else len(frames)

    return {
        "pattern": f"{prefix.replace('%', '%%')}%0{pad}d{ext}",
        "ext": ext,
        "start": start,
        "end": end,
        "count": len(frames),
        "missing": (end - start + 1) - len(frames),
        "first_gap": first_gap,
        "render_frames": render_frames,
    }, None


def next_final_version(base_name, existing_names):
    """ Highest existing <base>_Final_v<N>[_suffix].* version plus one """
    rx = re.compile(re.escape(base_name) + r"_Final_v(\d+)(?:_[^.]*)?\.[^.]+$", re.IGNORECASE)
    versions = [int(m.group(1)) for name in existing_names if (m := rx.match(name))]
    return max(versions, default=0) + 1


def norm_path(path):
    return os.path.normcase(os.path.normpath(path))


def clean_name_part(text):
    """ Trim spaces and separators so we don't end up with double underscores """
    return text.strip().strip("_-. ")


class TakeSpinBox(QSpinBox):
    """ Shows take numbers as tk01, tk02... and accepts typing "3" or "tk3" """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(1, 999)
        self.setPrefix("tk")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def textFromValue(self, value):
        return f"{value:02d}"

    def valueFromText(self, text):
        digits = re.sub(r"\D", "", text)
        return int(digits) if digits else self.value()

    def validate(self, text, pos):
        stripped = re.sub(r"^tk", "", text, flags=re.IGNORECASE)
        if stripped == "":
            return QValidator.State.Intermediate, text, pos
        if stripped.isdigit() and 1 <= int(stripped) <= 999:
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Invalid, text, pos


def x_icon():
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QColor("red"))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawLine(4, 4, 12, 12)
    painter.drawLine(12, 4, 4, 12)
    painter.end()
    return QIcon(pixmap)


def check_icon():
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("green"))
    painter.drawLine(4, 10, 8, 14)
    painter.drawLine(8, 14, 13, 5)
    painter.end()
    return QIcon(pixmap)


class FFmpegGUI(QWidget):
    _nvenc_ok = None  # Cached NVENC probe result

    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(resource_path("SadAlchemist.ico")))
        self.resize(950, 860)
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.settings = QSettings("Sadfish", APP_NAME)

        self.process = None
        self.jobs = []
        self.job_index = -1
        self.cancel_requested = False
        self.batch_results = {"done": 0, "failed": 0}
        self.seq_info = {}  # normalized folder path -> scan_sequence info
        self._read_buffer = ""

        self.layout = QVBoxLayout()

        # --- Title ---
        self.title_label = QLabel(f"{APP_NAME} v{APP_VERSION}")
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Image Sequence to Video Conversion")
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle_font.setItalic(True)
        self.subtitle_label.setFont(subtitle_font)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.subtitle_label)

        # --- Render queue ---
        queue_group = QGroupBox("Render Queue")
        queue_layout = QVBoxLayout()
        queue_group.setLayout(queue_layout)

        self.queue_hint = QLabel(
            "Drag & drop image sequence folders anywhere on this window, or use Add Folder. "
            "Delete removes selected rows.")
        self.queue_hint.setWordWrap(True)
        self.queue_hint.setStyleSheet("color: gray;")
        queue_layout.addWidget(self.queue_hint)

        self.input_tree = QTreeWidget()
        self.input_tree.setColumnCount(7)
        self.input_tree.setHeaderLabels(
            ["", "IMG SQ Folder", "Frames", "Take #", "Audio Source (optional)", "Output Filename", "Status"])
        self.input_tree.setRootIsDecorated(False)
        self.input_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.input_tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.input_tree.setAcceptDrops(True)
        self.input_tree.viewport().setAcceptDrops(True)
        self.input_tree.setDragDropMode(QTreeWidget.DragDropMode.NoDragDrop)
        self.input_tree.setColumnWidth(COL_REMOVE, 32)
        self.input_tree.setColumnWidth(COL_FOLDER, 170)
        self.input_tree.setColumnWidth(COL_FRAMES, 110)
        self.input_tree.setColumnWidth(COL_TAKE, 80)
        self.input_tree.setColumnWidth(COL_AUDIO, 170)
        self.input_tree.setColumnWidth(COL_OUTPUT, 230)
        self.input_tree.header().setStretchLastSection(True)
        self.input_tree.header().setSectionResizeMode(COL_REMOVE, QHeaderView.ResizeMode.Fixed)
        queue_layout.addWidget(self.input_tree)

        for key in (QKeySequence.StandardKey.Delete, QKeySequence(Qt.Key.Key_Backspace)):
            delete_shortcut = QShortcut(QKeySequence(key), self.input_tree)
            delete_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            delete_shortcut.activated.connect(self.remove_selected)

        queue_buttons = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add Folder...")
        self.add_folder_btn.clicked.connect(self.browse_input_folder)
        queue_buttons.addWidget(self.add_folder_btn)
        self.clear_queue_btn = QPushButton("Clear Queue")
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        queue_buttons.addWidget(self.clear_queue_btn)
        queue_buttons.addStretch()
        queue_layout.addLayout(queue_buttons)
        self.layout.addWidget(queue_group, stretch=1)

        # --- Naming ---
        naming_group = QGroupBox("Naming")
        naming_layout = QFormLayout()
        naming_group.setLayout(naming_layout)

        self.final_check = QCheckBox("Final render  (names files Folder_Final_vN, version auto-increments)")
        naming_layout.addRow(self.final_check)

        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("e.g. COMP, ACO, FX")
        # Keep characters that are illegal in filenames out of the task code
        self.task_input.setValidator(QRegularExpressionValidator(QRegularExpression(r'[^\\/:*?"<>|]*')))
        naming_layout.addRow("Task Code:", self.task_input)

        affix_layout = QHBoxLayout()
        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("optional, e.g. PROJ")
        self.prefix_input.setValidator(QRegularExpressionValidator(QRegularExpression(r'[^\\/:*?"<>|]*')))
        affix_layout.addWidget(self.prefix_input)
        affix_layout.addWidget(QLabel("Suffix:"))
        self.suffix_input = QLineEdit()
        self.suffix_input.setPlaceholderText("optional, e.g. forClient")
        self.suffix_input.setValidator(QRegularExpressionValidator(QRegularExpression(r'[^\\/:*?"<>|]*')))
        affix_layout.addWidget(self.suffix_input)
        naming_layout.addRow("Prefix:", affix_layout)

        self.naming_hint = QLabel()
        self.naming_hint.setStyleSheet("color: gray;")
        self.naming_hint.setWordWrap(True)
        naming_layout.addRow(self.naming_hint)
        self.layout.addWidget(naming_group)

        # --- Output ---
        output_group = QGroupBox("Output")
        output_layout = QHBoxLayout()
        output_group.setLayout(output_layout)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Choose where rendered videos are saved")
        output_layout.addWidget(self.output_path)
        self.output_btn = QPushButton("Browse...")
        self.output_btn.clicked.connect(self.browse_output)
        output_layout.addWidget(self.output_btn)
        self.show_output_btn = QPushButton("Open Folder")
        self.show_output_btn.clicked.connect(self.open_output_folder)
        output_layout.addWidget(self.show_output_btn)
        self.layout.addWidget(output_group)

        # --- Encoding ---
        encoding_group = QGroupBox("Encoding")
        encoding_layout = QFormLayout()
        encoding_group.setLayout(encoding_layout)

        self.preset_combo = QComboBox()
        for preset in PRESETS:
            self.preset_combo.addItem(preset["label"], preset["key"])
        encoding_layout.addRow("Preset:", self.preset_combo)

        self.fps_input = QComboBox()
        self.fps_input.setEditable(True)
        self.fps_input.addItems(FPS_CHOICES)
        self.fps_input.setCurrentText("24")
        fps_validator = QDoubleValidator(0.001, 1000.0, 3)
        fps_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        fps_validator.setLocale(QLocale.c())  # Always a dot decimal, whatever the system locale
        self.fps_input.setValidator(fps_validator)
        encoding_layout.addRow("Frames per Second:", self.fps_input)

        self.hwaccel_combo = QComboBox()
        self.hwaccel_combo.addItems(HWACCEL_CHOICES)
        self.hwaccel_label = QLabel("Hardware Acceleration:")
        encoding_layout.addRow(self.hwaccel_label, self.hwaccel_combo)
        self.layout.addWidget(encoding_group)

        # --- Run / cancel ---
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("Convert All")
        self.run_btn.setMinimumHeight(34)
        run_font = self.run_btn.font()
        run_font.setBold(True)
        self.run_btn.setFont(run_font)
        self.run_btn.clicked.connect(self.run_ffmpeg_batch)
        run_layout.addWidget(self.run_btn, stretch=1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(34)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_batch)
        run_layout.addWidget(self.cancel_btn)
        self.layout.addLayout(run_layout)

        # --- Status bar with progress ---
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; background: transparent;")
        self.layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bbb;
                border-radius: 5px;
                background: #eee;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
            }
        """)
        self.layout.addWidget(self.progress_bar)

        self.toggle_output_btn = QPushButton("Show FFmpeg Output")
        self.toggle_output_btn.setCheckable(True)
        self.toggle_output_btn.toggled.connect(self.toggle_ffmpeg_output)
        self.layout.addWidget(self.toggle_output_btn)

        self.ffmpeg_output = QPlainTextEdit()
        self.ffmpeg_output.setReadOnly(True)
        self.ffmpeg_output.setMaximumBlockCount(10000)
        self.ffmpeg_output.setVisible(False)
        self.layout.addWidget(self.ffmpeg_output, stretch=1)

        self.setLayout(self.layout)
        self.setAcceptDrops(True)

        self._load_settings()

        # Connect after settings load so restoring values doesn't fire half-built updates
        self.task_input.textChanged.connect(self.update_all_previews)
        self.prefix_input.textChanged.connect(self.update_all_previews)
        self.suffix_input.textChanged.connect(self.update_all_previews)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.output_path.textChanged.connect(self.update_all_previews)
        self.final_check.toggled.connect(self._on_final_toggled)
        self._on_preset_changed()
        self._on_final_toggled(self.final_check.isChecked())

    # ---------- Settings ----------

    def _load_settings(self):
        s = self.settings
        self.output_path.setText(s.value("output_dir", "", str))
        self.task_input.setText(s.value("task_code", "", str))
        self.prefix_input.setText(s.value("prefix", "", str))
        self.suffix_input.setText(s.value("suffix", "", str))
        self.fps_input.setCurrentText(s.value("fps", "24", str))
        idx = self.preset_combo.findData(s.value("preset", "h264", str))
        if idx != -1:
            self.preset_combo.setCurrentIndex(idx)
        hw = s.value("hwaccel", HWACCEL_CHOICES[0], str)
        if hw in HWACCEL_CHOICES:
            self.hwaccel_combo.setCurrentText(hw)
        self.final_check.setChecked(s.value("final", False, bool))

    def _save_settings(self):
        s = self.settings
        s.setValue("output_dir", self.output_path.text().strip())
        s.setValue("task_code", self.task_input.text().strip())
        s.setValue("prefix", self.prefix_input.text().strip())
        s.setValue("suffix", self.suffix_input.text().strip())
        s.setValue("fps", self.fps_input.currentText().strip())
        s.setValue("preset", self.preset_combo.currentData())
        s.setValue("hwaccel", self.hwaccel_combo.currentText())
        s.setValue("final", self.final_check.isChecked())

    # ---------- Drag & drop / adding folders ----------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.is_rendering():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and path.lower().endswith(IMAGE_EXTS):
                # Dropping a frame adds the folder it lives in
                path = os.path.dirname(path)
            if os.path.isdir(path):
                self.add_folder(path)
        event.accept()

    def browse_input_folder(self):
        options = QFileDialog.Option.DontUseNativeDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Image Sequence Folder", options=options)
        if folder:
            self.add_folder(folder)

    def add_folder(self, path):
        if self.is_rendering():
            return
        path = os.path.normpath(path)
        key = norm_path(path)
        existing = {norm_path(self.input_tree.topLevelItem(i).data(COL_FOLDER, Qt.ItemDataRole.UserRole))
                    for i in range(self.input_tree.topLevelItemCount())}
        if key in existing:
            self.status_label.setText(f"Already in queue: {os.path.basename(path)}")
            return

        info, error = scan_sequence(path)
        self.seq_info[key] = info

        self.input_tree.blockSignals(True)
        item = QTreeWidgetItem(["", os.path.basename(path), "", "", "", "", ""])
        item.setToolTip(COL_FOLDER, path)
        item.setData(COL_FOLDER, Qt.ItemDataRole.UserRole, path)
        item.setData(COL_TAKE, Qt.ItemDataRole.UserRole, "tk01")
        item.setData(COL_AUDIO, Qt.ItemDataRole.UserRole, None)
        if info:
            item.setText(COL_FRAMES, f"{info['start']}-{info['end']} ({info['count']})")
            item.setToolTip(COL_FRAMES, os.path.join(path, info["pattern"]))
        else:
            item.setText(COL_FRAMES, "none")
        self.input_tree.addTopLevelItem(item)
        self.input_tree.blockSignals(False)

        self._set_remove_button(item)
        self._set_take_spinbox(item)
        self._set_audio_button(item)
        self._reset_status(item)
        self.update_all_previews()

    # ---------- Row widgets ----------

    def _set_remove_button(self, item):
        remove_btn = QPushButton()
        remove_btn.setFixedSize(QSize(20, 20))
        remove_btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
        remove_btn.setIcon(x_icon())
        remove_btn.setIconSize(QSize(16, 16))
        remove_btn.setToolTip("Remove from queue")
        remove_btn.clicked.connect(lambda: self._remove_item(item))
        self.input_tree.setItemWidget(item, COL_REMOVE, remove_btn)

    def _set_take_spinbox(self, item):
        # A real widget instead of inline editing, which drew the editor over the old text
        spin = TakeSpinBox()
        spin.setFixedHeight(22)
        spin.setToolTip("Take number")
        spin.valueChanged.connect(lambda value: self._on_take_changed(item, value))
        self.input_tree.setItemWidget(item, COL_TAKE, spin)

    def _set_audio_button(self, item):
        btn = QPushButton("Add Audio")
        btn.setFixedSize(QSize(90, 22))
        btn.clicked.connect(lambda: self._browse_audio(item))
        self.input_tree.setItemWidget(item, COL_AUDIO, btn)

    def _set_remove_audio_button(self, item, filename, has_audio):
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(filename if has_audio else f"{filename} (no audio stream)")
        label.setStyleSheet("color: green;" if has_audio else "color: red;")
        label.setToolTip(item.toolTip(COL_AUDIO))
        layout.addWidget(label)
        btn = QPushButton()
        btn.setFixedSize(QSize(22, 22))
        btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
        btn.setIcon(x_icon())
        btn.setIconSize(QSize(16, 16))
        btn.setToolTip("Remove audio")
        btn.clicked.connect(lambda: self._remove_audio(item))
        layout.addWidget(btn)
        layout.addStretch()
        widget.setLayout(layout)
        self.input_tree.setItemWidget(item, COL_AUDIO, widget)

    def _set_row_widgets_enabled(self, enabled):
        for i in range(self.input_tree.topLevelItemCount()):
            item = self.input_tree.topLevelItem(i)
            for col in (COL_REMOVE, COL_TAKE, COL_AUDIO):
                widget = self.input_tree.itemWidget(item, col)
                if widget:
                    widget.setEnabled(enabled)

    def _browse_audio(self, item):
        if self.is_rendering():
            return
        image_folder = item.data(COL_FOLDER, Qt.ItemDataRole.UserRole)
        start_dir = os.path.dirname(image_folder) if image_folder else ""
        options = QFileDialog.Option.DontUseNativeDialog
        exts = " ".join(f"*{e}" for e in AUDIO_EXTS)
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Audio/Video File", start_dir, f"Audio/Video Files ({exts})", options=options)
        if not file:
            return
        has_audio = self._audio_file_has_audio(file)
        item.setData(COL_AUDIO, Qt.ItemDataRole.UserRole, file if has_audio else None)
        item.setToolTip(COL_AUDIO, file)
        filename = os.path.basename(file)

        # Auto-increase the take number from the audio source name (e.g. a previous take's render)
        take_match = re.search(r'tk(\d+)', filename, re.IGNORECASE)
        take_number = None
        if take_match:
            take_number = f"tk{int(take_match.group(1)) + 1:02d}"
        elif not self.final_check.isChecked():
            text, ok = QInputDialog.getText(self, "Take Number", "Enter take number (digits only, e.g., 1):")
            if ok and text.strip().isdigit():
                take_number = f"tk{int(text):02d}"
        if take_number:
            self._set_take(item, take_number)

        self._set_remove_audio_button(item, filename, has_audio)
        self.update_all_previews()

    def _remove_audio(self, item):
        if self.is_rendering():
            return
        item.setData(COL_AUDIO, Qt.ItemDataRole.UserRole, None)
        item.setToolTip(COL_AUDIO, "")
        self._set_audio_button(item)

    def _remove_item(self, item):
        if self.is_rendering():
            return
        idx = self.input_tree.indexOfTopLevelItem(item)
        if idx != -1:
            self.input_tree.takeTopLevelItem(idx)
            self.update_all_previews()

    def remove_selected(self):
        for item in self.input_tree.selectedItems():
            self._remove_item(item)

    def clear_queue(self):
        if self.is_rendering():
            return
        self.input_tree.clear()
        self.status_label.setText("")
        self.progress_bar.setValue(0)

    # ---------- Take number / naming ----------

    def _on_take_changed(self, item, value):
        item.setData(COL_TAKE, Qt.ItemDataRole.UserRole, f"tk{value:02d}")
        self.update_all_previews()

    def _set_take(self, item, take):
        item.setData(COL_TAKE, Qt.ItemDataRole.UserRole, take)
        spin = self.input_tree.itemWidget(item, COL_TAKE)
        if spin:
            spin.blockSignals(True)
            spin.setValue(int(take[2:]))
            spin.blockSignals(False)

    def _current_preset(self):
        return PRESETS_BY_KEY[self.preset_combo.currentData()]

    def _output_name_for(self, item, taken_names):
        """ Single source of truth for output filenames (used by the preview and the render) """
        folder = item.data(COL_FOLDER, Qt.ItemDataRole.UserRole)
        base_name = os.path.basename(os.path.normpath(folder))
        ext = self._current_preset()["ext"]
        prefix, suffix = self._name_affixes()
        if self.final_check.isChecked():
            # The prefix is part of the versioned name; the suffix doesn't affect numbering
            version = next_final_version(prefix + base_name, taken_names)
            return f"{prefix}{base_name}_Final_v{version}{suffix}.{ext}"
        take_number = item.data(COL_TAKE, Qt.ItemDataRole.UserRole) or "tk01"
        task_code = self.task_input.text().strip() or "TASK"
        return f"{prefix}{base_name}_{take_number}_{task_code}{suffix}.{ext}"

    def _name_affixes(self):
        """ Returns ("PREFIX_", "_SUFFIX"), or empty strings when unused """
        prefix = clean_name_part(self.prefix_input.text())
        suffix = clean_name_part(self.suffix_input.text())
        return (f"{prefix}_" if prefix else ""), (f"_{suffix}" if suffix else "")

    def _compute_output_names(self, items):
        output_dir = self.output_path.text().strip()
        try:
            taken = os.listdir(output_dir) if output_dir and os.path.isdir(output_dir) else []
        except OSError:
            taken = []
        names = []
        for item in items:
            name = self._output_name_for(item, taken)
            # Later rows with the same folder name get the next version / are flagged as clashes
            taken.append(name)
            names.append(name)
        return names

    def _queue_items(self):
        return [self.input_tree.topLevelItem(i) for i in range(self.input_tree.topLevelItemCount())]

    def update_all_previews(self):
        items = self._queue_items()
        names = self._compute_output_names(items)
        counts = {}
        for name in names:
            counts[name.lower()] = counts.get(name.lower(), 0) + 1
        self.input_tree.blockSignals(True)
        for item, name in zip(items, names):
            item.setText(COL_OUTPUT, name)
            if counts[name.lower()] > 1:
                item.setForeground(COL_OUTPUT, QColor("red"))
                item.setToolTip(COL_OUTPUT, "Another row in the queue has the same output name")
            else:
                item.setForeground(COL_OUTPUT, QColor())
                item.setToolTip(COL_OUTPUT, "")
        self.input_tree.blockSignals(False)
        self._update_naming_hint()

    def _update_naming_hint(self):
        ext = self._current_preset()["ext"]
        prefix, suffix = self._name_affixes()
        if self.final_check.isChecked():
            self.naming_hint.setText(
                f"Files will be named  {prefix}FolderName_Final_vN{suffix}.{ext}  — N is one higher than the "
                f"latest version already in the output folder.")
        else:
            task = self.task_input.text().strip() or "TASK"
            self.naming_hint.setText(f"Files will be named  {prefix}FolderName_tkXX_{task}{suffix}.{ext}")

    def _on_final_toggled(self, checked):
        self.task_input.setEnabled(not checked)
        self.input_tree.setColumnHidden(COL_TAKE, checked)
        self.update_all_previews()

    def _on_preset_changed(self, *_):
        is_h264 = self._current_preset()["codec"] == "h264"
        self.hwaccel_combo.setEnabled(is_h264)
        self.hwaccel_label.setEnabled(is_h264)
        self.update_all_previews()

    # ---------- Misc UI ----------

    def browse_output(self):
        options = QFileDialog.Option.DontUseNativeDialog
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self.output_path.text().strip(), options=options)
        if folder:
            self.output_path.setText(os.path.normpath(folder))

    def toggle_ffmpeg_output(self, checked):
        self.toggle_output_btn.setText("Hide FFmpeg Output" if checked else "Show FFmpeg Output")
        self.ffmpeg_output.setVisible(checked)

    def open_output_folder(self):
        folder = self.output_path.text().strip()
        if os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QMessageBox.warning(self, "Warning", "Output folder does not exist.")

    def _set_status(self, item, text, color=None):
        item.setText(COL_STATUS, text)
        item.setForeground(COL_STATUS, QColor(color) if color else QColor())

    def _reset_status(self, item):
        item.setIcon(COL_FOLDER, QIcon())
        info = self.seq_info.get(norm_path(item.data(COL_FOLDER, Qt.ItemDataRole.UserRole)))
        if info is None:
            self._set_status(item, "No images found", "red")
        elif info["missing"]:
            self._set_status(item, f"{info['missing']} missing frames", "darkorange")
            item.setToolTip(COL_STATUS, f"Rendering will stop at the first gap (frame {info['first_gap']}).")
        else:
            self._set_status(item, "Ready")

    def _audio_file_has_audio(self, file):
        try:
            result = subprocess.run(
                [FFPROBE, "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=CREATE_NO_WINDOW
            )
            return "audio" in result.stdout
        except Exception:
            return False

    def _nvenc_available(self):
        if FFmpegGUI._nvenc_ok is None:
            ok = False
            try:
                result = subprocess.run(
                    [FFMPEG, '-hide_banner', '-encoders'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    creationflags=CREATE_NO_WINDOW
                )
                if "h264_nvenc" in result.stdout:
                    # Make sure NVENC actually works on this machine (some GPUs reject tiny frames)
                    test_result = subprocess.run(
                        [FFMPEG, "-hide_banner", "-f", "lavfi", "-i", "testsrc=duration=1:size=256x256:rate=1",
                         "-c:v", "h264_nvenc", "-f", "null", "-"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        creationflags=CREATE_NO_WINDOW
                    )
                    ok = test_result.returncode == 0
            except Exception:
                ok = False
            FFmpegGUI._nvenc_ok = ok
        return FFmpegGUI._nvenc_ok

    # ---------- Batch rendering ----------

    def is_rendering(self):
        return self.process is not None

    def _set_controls_enabled(self, enabled):
        for widget in (self.run_btn, self.add_folder_btn, self.clear_queue_btn, self.task_input,
                       self.prefix_input, self.suffix_input,
                       self.final_check, self.output_path, self.output_btn, self.preset_combo,
                       self.fps_input, self.hwaccel_combo):
            widget.setEnabled(enabled)
        if enabled:
            # Restore the state-dependent enables
            self._on_preset_changed()
            self._on_final_toggled(self.final_check.isChecked())
        self.cancel_btn.setEnabled(not enabled)
        self._set_row_widgets_enabled(enabled)

    def run_ffmpeg_batch(self):
        if self.is_rendering():
            return
        output_dir = self.output_path.text().strip()
        if not os.path.isdir(output_dir):
            QMessageBox.critical(self, "Error", "Please choose a valid output folder.")
            return

        fps = parse_fps(self.fps_input.currentText())
        if not fps:
            QMessageBox.critical(self, "Error", "Frames per second must be a number greater than 0.")
            return

        items = self._queue_items()
        if not items:
            QMessageBox.critical(self, "Error", "No input folders in the queue.")
            return

        # Re-scan folders in case frames changed since they were added
        for item in items:
            folder = item.data(COL_FOLDER, Qt.ItemDataRole.UserRole)
            info, _ = scan_sequence(folder)
            self.seq_info[norm_path(folder)] = info
            self._reset_status(item)

        names = self._compute_output_names(items)
        self.update_all_previews()

        empty = [item.text(COL_FOLDER) for item in items
                 if self.seq_info.get(norm_path(item.data(COL_FOLDER, Qt.ItemDataRole.UserRole))) is None]
        if empty:
            QMessageBox.critical(self, "Error", "No numbered image files found in:\n\n" + "\n".join(empty))
            return

        lowered = [n.lower() for n in names]
        clashes = sorted({n for n in names if lowered.count(n.lower()) > 1})
        if clashes:
            QMessageBox.critical(
                self, "Error",
                "These output names are used by more than one row; change a take number:\n\n" + "\n".join(clashes))
            return

        warnings = []
        gaps = []
        for item in items:
            info = self.seq_info[norm_path(item.data(COL_FOLDER, Qt.ItemDataRole.UserRole))]
            if info["missing"]:
                gaps.append(f"{item.text(COL_FOLDER)}: {info['missing']} missing, "
                            f"render stops at frame {info['first_gap'] - 1}")
        if gaps:
            warnings.append("Some sequences have missing frames:\n" + "\n".join(gaps))
        existing = [n for n in names if os.path.exists(os.path.join(output_dir, n))]
        if existing:
            warnings.append("These files already exist and will be overwritten:\n" + "\n".join(existing))
        if warnings:
            answer = QMessageBox.question(
                self, "Continue?", "\n\n".join(warnings) + "\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return

        preset = self._current_preset()
        codec = preset["codec"]
        if codec == "h264":
            hwaccel = self.hwaccel_combo.currentText()
            if hwaccel == "NVIDIA (h264_nvenc)":
                use_nvenc = True
            elif hwaccel == "Auto-detect":
                self.status_label.setText("Checking for NVIDIA encoder...")
                QApplication.processEvents()
                use_nvenc = self._nvenc_available()
            else:
                use_nvenc = False
            codec = "h264_nvenc" if use_nvenc else "libx264"

        self._save_settings()
        self.jobs = []
        for item, name in zip(items, names):
            folder = item.data(COL_FOLDER, Qt.ItemDataRole.UserRole)
            info = self.seq_info[norm_path(folder)]
            output_file = os.path.join(output_dir, name)
            audio_file = item.data(COL_AUDIO, Qt.ItemDataRole.UserRole)
            args = self._build_ffmpeg_args(folder, info, audio_file, output_file, preset, codec, fps)
            self.jobs.append({"item": item, "args": args, "output": output_file, "frames": info["render_frames"],
                              "existed_before": os.path.exists(output_file)})
            self._set_status(item, "Queued")

        self.job_index = -1
        self.cancel_requested = False
        self.batch_results = {"done": 0, "failed": 0}
        self.ffmpeg_output.clear()
        self._set_controls_enabled(False)
        self._start_next_job()

    def _build_ffmpeg_args(self, folder, info, audio_file, output_file, preset, codec, fps):
        fps_str, fps_val = fps
        args = ["-hide_banner", "-y"]
        if info["ext"].lower() == ".exr":
            # EXR frames are linear; convert to sRGB so the video isn't dark
            args += ["-apply_trc", "iec61966_2_1"]
        args += [
            "-framerate", fps_str,
            "-start_number", str(info["start"]),
            "-i", os.path.join(folder, info["pattern"]),
        ]
        if audio_file:
            args += ["-i", audio_file, "-map", "0:v:0", "-map", "1:a:0?"]
        args += ["-c:v", codec, *preset["args"]]
        if preset["even"]:
            args += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        args += ["-pix_fmt", preset["pix_fmt"]]
        if audio_file:
            args += preset["audio"]
        # The image sequence always sets the duration, even if the audio is longer
        args += ["-t", f"{info['render_frames'] / fps_val:.6f}", output_file]
        return args

    def _start_next_job(self):
        self.job_index += 1
        if self.job_index >= len(self.jobs):
            self._finish_batch()
            return
        job = self.jobs[self.job_index]
        item = job["item"]
        self.progress_bar.setMaximum(max(job["frames"], 1))
        self.progress_bar.setValue(0)
        self.status_label.setText(
            f"Rendering {self.job_index + 1} of {len(self.jobs)}: {item.text(COL_FOLDER)}")
        self._set_status(item, "Rendering 0%", "blue")
        self.input_tree.scrollToItem(item)
        self.ffmpeg_output.appendPlainText(
            f"\n=== {item.text(COL_FOLDER)} ===\n$ ffmpeg {subprocess.list2cmdline(job['args'])}\n")

        self._read_buffer = ""
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_process_output)
        self.process.finished.connect(self._on_process_finished)
        self.process.errorOccurred.connect(self._on_process_error)
        self.process.start(FFMPEG, job["args"])

    def _on_process_output(self):
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._read_buffer += data
        # ffmpeg ends progress lines with \r rather than \n
        parts = re.split(r'[\r\n]', self._read_buffer)
        self._read_buffer = parts.pop()
        job = self.jobs[self.job_index]
        for line in parts:
            if not line.strip():
                continue
            self.ffmpeg_output.appendPlainText(line.rstrip())
            frame_match = re.search(r'frame=\s*(\d+)', line)
            if frame_match:
                current = min(int(frame_match.group(1)), job["frames"])
                self.progress_bar.setValue(current)
                self._set_status(job["item"], f"Rendering {current * 100 // max(job['frames'], 1)}%", "blue")

    def _on_process_error(self, error):
        # Only FailedToStart skips the finished signal
        if error == QProcess.ProcessError.FailedToStart:
            self._job_done(False, f"Could not start ffmpeg: {self.process.errorString()}")

    def _on_process_finished(self, exit_code, exit_status):
        if self._read_buffer.strip():
            self.ffmpeg_output.appendPlainText(self._read_buffer.rstrip())
            self._read_buffer = ""
        ok = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        self._job_done(ok, f"ffmpeg exited with code {exit_code}")

    def _job_done(self, ok, error_msg):
        job = self.jobs[self.job_index]
        item = job["item"]
        if self.process:
            self.process.deleteLater()
            self.process = None

        if self.cancel_requested:
            self._set_status(item, "Cancelled", "darkorange")
            # Don't leave a half-written video behind
            try:
                if os.path.exists(job["output"]):
                    os.remove(job["output"])
            except OSError:
                pass
            for later in self.jobs[self.job_index + 1:]:
                self._set_status(later["item"], "Skipped", "gray")
            self.job_index = len(self.jobs)
            self._finish_batch()
            return

        if ok:
            self.batch_results["done"] += 1
            self.progress_bar.setValue(self.progress_bar.maximum())
            self._set_status(item, "Done", "green")
            item.setIcon(COL_FOLDER, check_icon())
        else:
            # Keep going with the rest of the queue; the log has the details
            self.batch_results["failed"] += 1
            self._set_status(item, "Failed (see FFmpeg output)", "red")
            item.setToolTip(COL_STATUS, error_msg)
            item.setIcon(COL_FOLDER, x_icon())
            self.ffmpeg_output.appendPlainText(f"!!! {error_msg}")
            # Remove broken new files so they don't count as a Final version (keep files that were already there)
            if not job["existed_before"]:
                try:
                    if os.path.exists(job["output"]):
                        os.remove(job["output"])
                except OSError:
                    pass
        self._start_next_job()

    def _finish_batch(self):
        self.process = None
        self._set_controls_enabled(True)
        done, failed = self.batch_results["done"], self.batch_results["failed"]
        if self.cancel_requested:
            self.status_label.setText(f"Cancelled. {done} finished before cancelling.")
        elif failed:
            self.status_label.setText(f"Finished with errors: {done} done, {failed} failed.")
            if not self.toggle_output_btn.isChecked():
                self.toggle_output_btn.setChecked(True)
            QMessageBox.warning(self, "Renders failed",
                                f"{failed} render(s) failed. Check the FFmpeg output for details.")
        else:
            self.status_label.setText(f"All {done} renders finished.")
        # Versions in the output folder may have changed
        self.update_all_previews()

    def cancel_batch(self):
        if self.process:
            self.cancel_requested = True
            self.status_label.setText("Cancelling...")
            self.process.kill()

    def closeEvent(self, event):
        if self.is_rendering():
            answer = QMessageBox.question(
                self, "Rendering in progress", "A render is still running. Cancel it and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_requested = True
            self.process.kill()
            self.process.waitForFinished(3000)
        self._save_settings()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("SadAlchemist.ico")))
    missing = [name for name, path in (("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)) if not path]
    if missing:
        QMessageBox.critical(
            None, "Error",
            f"Could not find {' and '.join(missing)}.\n\n"
            "Place the binaries in the ffmpeg_win (Windows) or ffmpeg_osx (macOS) folder, "
            "or install ffmpeg so it is on your PATH.")
        sys.exit(1)
    window = FFmpegGUI()
    window.show()
    sys.exit(app.exec())
