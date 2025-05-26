import sys
import os
import subprocess
import re

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QLabel, QLineEdit, QMessageBox, QComboBox, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QInputDialog
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QColor, QPixmap, QPainter, QFont


class FFmpegGUI(QWidget):
    AUDIO_EXTS = ('.wav', '.mp3', '.aac', '.flac', '.m4a', '.ogg',
                  '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v')

    def __init__(self):
        super().__init__()
        self.resize(800, 800)
        self.setWindowTitle("SadAlchemist v25.0")
        self.layout = QVBoxLayout()

        # --- Add large title at the very top ---
        self.title_label = QLabel("SadAlchemist v25.0")
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.title_label)
        # --- End title addition ---

        # --- Add subtitle under the title ---
        self.subtitle_label = QLabel("Image Sequence to Video Conversion")
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle_font.setItalic(True)
        self.subtitle_label.setFont(subtitle_font)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.subtitle_label)
        # --- End subtitle addition ---

        # Add vertical space
        self.layout.addWidget(QLabel(""))  # Blank label for space
        # Or, for more control:
        # spacer = QLabel()
        # spacer.setFixedHeight(12)
        # self.layout.addWidget(spacer)

        # 1. Task Code at the top
        self.task_label = QLabel("Task Code (e.g. COMP, ACO, FX, etc.):")
        self.layout.addWidget(self.task_label)
        self.task_input = QLineEdit()
        self.layout.addWidget(self.task_input)

        # Folder/Audio list with headers
        self.input_label = QLabel("Image Sequence Folders (drag & drop supported):")
        self.layout.addWidget(self.input_label)
        self.input_tree = QTreeWidget()
        self.input_tree.setColumnCount(5)
        self.input_tree.setHeaderLabels(["", "IMG SQ Folder", "Take #", "Audio Source (optional)", "Filename Preview"])
        self.input_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.input_tree.setAcceptDrops(True)
        self.input_tree.viewport().setAcceptDrops(True)
        self.input_tree.setDropIndicatorShown(True)
        self.input_tree.setDragDropMode(QTreeWidget.DragDropMode.NoDragDrop)
        # Set column widths
        self.input_tree.setColumnWidth(0, 32)   # Remove button column
        self.input_tree.setColumnWidth(1, 200)  # Folder column
        self.input_tree.setColumnWidth(2, 60)
        self.input_tree.setColumnWidth(3, 150)   # Take number column
        self.input_tree.setColumnWidth(4, 250)  # Preview filename column
        self.layout.addWidget(self.input_tree)

        # Make take number column editable
        self.input_tree.itemChanged.connect(self._on_item_changed)

        # --- Add Clear Queue button here ---
        self.clear_queue_btn = QPushButton("Clear Queue")
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        self.layout.addWidget(self.clear_queue_btn)
        # --- End addition ---

        self.output_label = QLabel("Output Folder:")
        self.layout.addWidget(self.output_label)
        self.output_path = QLineEdit()
        self.layout.addWidget(self.output_path)
        self.output_btn = QPushButton("Browse")
        self.output_btn.clicked.connect(self.browse_output)
        self.layout.addWidget(self.output_btn)

        self.fps_label = QLabel("Frames per Second:")
        self.layout.addWidget(self.fps_label)
        self.fps_input = QLineEdit("24")
        self.layout.addWidget(self.fps_input)

        self.hwaccel_label = QLabel("Hardware Acceleration:")
        self.layout.addWidget(self.hwaccel_label)
        self.hwaccel_combo = QComboBox()
        self.hwaccel_combo.addItems(
            ["Auto-detect", "NVIDIA (h264_nvenc)", "CPU (libx264)"])
        self.layout.addWidget(self.hwaccel_combo)

        self.preset_label = QLabel("Encoding Preset:")
        self.layout.addWidget(self.preset_label)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Preview MP4 - H.264 25Mbps",
            "ProRes MOV - 422 Proxy",
            "ProRes MOV - 422 Standard"           
        ])
        self.layout.addWidget(self.preset_combo)

        # Place these lines here, after both widgets are created:
        self.task_input.textChanged.connect(self.update_all_previews)
        self.preset_combo.currentIndexChanged.connect(self.update_all_previews)

        self.run_btn = QPushButton("Convert All")
        self.run_btn.clicked.connect(self.run_ffmpeg_batch)
        self.layout.addWidget(self.run_btn)

        self.status_label = QLabel("")
        self.layout.addWidget(self.status_label)

        self.toggle_output_btn = QPushButton("Show FFmpeg Output")
        self.toggle_output_btn.setCheckable(True)
        self.toggle_output_btn.toggled.connect(self.toggle_ffmpeg_output)
        self.layout.addWidget(self.toggle_output_btn)

        self.ffmpeg_output = QTextEdit()
        self.ffmpeg_output.setReadOnly(True)
        self.ffmpeg_output.setVisible(False)
        self.layout.addWidget(self.ffmpeg_output)

        self.setLayout(self.layout)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file = url.toLocalFile()
            if os.path.isdir(file):
                folder_name = os.path.basename(os.path.normpath(file))
                existing_paths = [self.input_tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) for i in range(self.input_tree.topLevelItemCount())]
                if file not in existing_paths:
                    item = QTreeWidgetItem(["", folder_name, "tk01", "No audio", ""])
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsEditable)
                    item.setData(1, Qt.ItemDataRole.UserRole, file)
                    item.setData(2, Qt.ItemDataRole.UserRole, "tk01")  # Take number
                    item.setData(3, Qt.ItemDataRole.UserRole, None)    # Audio
                    self.input_tree.addTopLevelItem(item)
                    self._set_remove_button(item)
                    self._set_audio_button(item)
                    self._update_preview_filename(item)
        event.accept()

    def _set_remove_button(self, item):
        remove_btn = QPushButton()
        remove_btn.setFixedSize(QSize(20, 20))
        remove_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; }")
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QColor("red"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawLine(4, 4, 12, 12)
        painter.drawLine(12, 4, 4, 12)
        painter.end()
        remove_btn.setIcon(QIcon(pixmap))
        remove_btn.setIconSize(QSize(16, 16))
        remove_btn.clicked.connect(lambda: self._remove_item(item))
        self.input_tree.setItemWidget(item, 0, remove_btn)

    def _set_audio_button(self, item):
        btn = QPushButton("Add Audio")
        btn.setFixedSize(QSize(90, 22))
        btn.clicked.connect(lambda: self._browse_audio(item))
        self.input_tree.setItemWidget(item, 3, btn)

    def _set_remove_audio_button(self, item, filename):
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(filename)
        label.setStyleSheet("color: green;")
        layout.addWidget(label)
        btn = QPushButton()
        btn.setFixedSize(QSize(22, 22))
        btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QColor("red"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawLine(4, 4, 12, 12)
        painter.drawLine(12, 4, 4, 12)
        painter.end()
        btn.setIcon(QIcon(pixmap))
        btn.setIconSize(QSize(16, 16))
        btn.clicked.connect(lambda: self._remove_audio(item))
        layout.addWidget(btn)
        widget.setLayout(layout)
        self.input_tree.setItemWidget(item, 3, widget)

    def _browse_audio(self, item):
        image_folder = item.data(1, Qt.ItemDataRole.UserRole)
        if image_folder:
            start_dir = os.path.dirname(image_folder)
        else:
            start_dir = ""
        options = QFileDialog.Option.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Audio/Video File", start_dir,
            "Audio/Video Files (*.wav *.mp3 *.aac *.flac *.m4a *.ogg *.mp4 *.mov *.mkv *.avi *.webm *.m4v)", options=options)
        if file:
            has_audio = self._audio_file_has_audio(file)
            item.setData(3, Qt.ItemDataRole.UserRole, file if has_audio else None)
            filename = os.path.basename(file)
            # 2 & 3. Extract and format take number
            take_match = re.search(r'tk(\d{2})', filename, re.IGNORECASE)
            if take_match:
                num = int(take_match.group(1))
                take_number = f"tk{num+1:02d}"
            else:
                # Prompt user for take number (just digits)
                take_number, ok = QInputDialog.getText(self, "Take Number", "Enter take number (digits only, e.g., 1):")
                if ok and take_number.isdigit():
                    take_number = f"tk{int(take_number):02d}"
                else:
                    take_number = "tk01"
            item.setText(2, take_number)
            item.setData(2, Qt.ItemDataRole.UserRole, take_number)
            if has_audio:
                item.setText(3, filename)
                item.setForeground(3, QColor())
            else:
                item.setText(3, filename)
                item.setForeground(3, QColor("red"))
            self._set_remove_audio_button(item, filename)
            self._update_preview_filename(item)

    def _update_preview_filename(self, item):
        # Get current values
        folder_name = item.text(1)
        take_number = item.text(2)
        task_code = self.task_input.text().strip() or "TASK"
        # Guess extension based on preset (optional: you can improve this)
        preset = self.preset_combo.currentText() if hasattr(self, 'preset_combo') else ""
        if "mov" in preset.lower():
            ext = "mov"
        else:
            ext = "mp4"
        preview = f"{folder_name}_{take_number}_{task_code}.{ext}"
        item.setText(4, preview)

    # Optionally, update preview for all rows when task code or preset changes:
    def update_all_previews(self):
        for i in range(self.input_tree.topLevelItemCount()):
            self._update_preview_filename(self.input_tree.topLevelItem(i))

    # Call this after task code or preset changes:
    # self.task_input.textChanged.connect(self.update_all_previews)
    # self.preset_combo.currentIndexChanged.connect(self.update_all_previews)

    def _remove_audio(self, item):
        item.setData(3, Qt.ItemDataRole.UserRole, None)
        item.setText(3, "No audio")
        item.setForeground(3, QColor())
        self._set_audio_button(item)

    def _on_item_changed(self, item, column):
        # Ensure take number is always formatted as tkXX
        if column == 2:
            text = item.text(2)
            match = re.match(r'tk?(\d{1,2})', text, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                formatted = f"tk{num:02d}"
                item.setText(2, formatted)
                item.setData(2, Qt.ItemDataRole.UserRole, formatted)
            else:
                item.setText(2, "tk01")
                item.setData(2, Qt.ItemDataRole.UserRole, "tk01")
        self._update_preview_filename(item)

    def browse_output(self):
        options = QFileDialog.Option.DontUseNativeDialog
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", options=options)
        if folder:
            self.output_path.setText(folder)

    def clear_queue(self):
        self.input_tree.clear()

    def _audio_file_has_audio(self, file):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a",
                    "-show_entries", "stream=codec_type", "-of", "csv=p=0", file],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return "audio" in result.stdout
        except Exception:
            return False

    def run_ffmpeg_batch(self):
        output_dir = self.output_path.text()
        fps = self.fps_input.text()
        hwaccel = self.hwaccel_combo.currentText()
        preset = self.preset_combo.currentText()
        task_code = self.task_input.text().strip()

        if not os.path.isdir(output_dir):
            QMessageBox.critical(self, "Error", "Invalid output folder.")
            return

        items = [self.input_tree.topLevelItem(i) for i in range(self.input_tree.topLevelItemCount())]
        if not items:
            QMessageBox.critical(self, "Error", "No input folders selected.")
            return

        for item in items:
            folder = item.data(1, Qt.ItemDataRole.UserRole)
            audio_file = item.data(3, Qt.ItemDataRole.UserRole)
            take_number = item.data(2, Qt.ItemDataRole.UserRole)
            self.status_label.setText(f"Rendering: {folder}")
            QApplication.processEvents()
            success, error_msg = self.run_ffmpeg(folder, output_dir, fps, hwaccel, preset, audio_file, take_number, task_code)
            if success:
                self.set_item_checkmark(item)
            else:
                folder_name = os.path.basename(folder)
                QMessageBox.critical(self, "Error", f"Failed rendering: {folder_name}\n\nError:\n{error_msg}")
                self.status_label.setText(f"Error rendering: {folder_name}")
                return  # Abort further operations
        self.status_label.setText("All renders finished.")

    def set_item_checkmark(self, item):
        # Add a green checkmark icon to the folder column
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("green"))
        painter.setBrush(QColor("green"))
        painter.drawLine(4, 10, 8, 14)
        painter.drawLine(8, 14, 13, 5)
        painter.end()
        item.setIcon(1, QIcon(pixmap))

    def toggle_ffmpeg_output(self, checked):
        if checked:
            self.toggle_output_btn.setText("Hide FFmpeg Output")
            self.ffmpeg_output.setVisible(True)
        else:
            self.toggle_output_btn.setText("Show FFmpeg Output")
            self.ffmpeg_output.setVisible(False)

    def run_ffmpeg(self, input_dir, output_dir, fps, hwaccel, preset, audio_file=None, take_number="tk01", task_code="TASK"):
        files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(
            ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'))])
        if not files:
            return False, "No image files found."

        pattern = None
        match = re.match(r"(.*?)(\d+)(\.[^.]+)$", files[0])
        if match:
            prefix, digits, ext = match.groups()
            num_digits = len(digits)
            pattern = f"{prefix}%0{num_digits}d{ext}"
        else:
            pattern = files[0]

        input_pattern = os.path.join(input_dir, pattern)
        base_name = os.path.basename(os.path.normpath(input_dir))

        # Increment take number if audio had one
        if take_number and re.match(r'tk\d{2}', take_number, re.IGNORECASE):
            try:
                num = int(take_number[2:])
                take_number_out = f"tk{num+1:02d}"
            except Exception:
                take_number_out = take_number
        else:
            take_number_out = take_number or "tk01"

        # Use task_code or default
        task_code_out = task_code if task_code else "TASK"

        # Choose extension based on preset
        if preset == "ProRes MOV - 422 Standard":
            ext = "mov"
            codec = "prores_ks"
            ffmpeg_args = ["-profile:v", "3"]
        elif preset == "ProRes MOV - 422 Proxy":
            ext = "mov"
            codec = "prores_ks"
            ffmpeg_args = ["-profile:v", "0"]
        elif preset == "Preview MP4 - H.264 25Mbps":
            ext = "mp4"
            use_nvenc = False
            if hwaccel == "NVIDIA (h264_nvenc)":
                use_nvenc = True
            elif hwaccel == "Auto-detect":
                try:
                    result = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if "h264_nvenc" in result.stdout:
                        use_nvenc = True
                except Exception:
                    pass
            codec = "h264_nvenc" if use_nvenc else "libx264"
            ffmpeg_args = ["-b:v", "25M"]
        else:
            ext = "mp4"
            codec = "libx264"
            ffmpeg_args = []

        # Build output filename
        output_file = os.path.join(
            output_dir,
            f"{base_name}_{take_number}_{task_code_out}.{ext}"
        )

        cmd = [
            "ffmpeg",
            "-framerate", fps,
            "-i", input_pattern,
        ]

        # Add audio if provided
        if audio_file:
            cmd += ["-i", audio_file, "-map", "0:v:0", "-map", "1:a:0?"]
        # If no audio, just map video
        cmd += [
            "-c:v", codec,
            *ffmpeg_args,
            "-pix_fmt", "yuv420p",
            "-y",
            output_file
        ]

        self.ffmpeg_output.clear()
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            output_lines = []
            for line in process.stdout:
                self.ffmpeg_output.append(line.rstrip())
                output_lines.append(line.rstrip())
                QApplication.processEvents()
            process.wait()
            if process.returncode == 0:
                return True, ""
            else:
                return False, "\n".join(output_lines[-20:])
        except Exception as e:
            return False, str(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FFmpegGUI()
    window.show()
    sys.exit(app.exec())
