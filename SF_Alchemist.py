import sys
import os
import subprocess
import re

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QLabel, QLineEdit, QMessageBox, QComboBox, QListWidget, QListWidgetItem,
    QHBoxLayout, QTextEdit
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QColor, QPixmap, QPainter

class FFmpegGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Sequence to Video (FFmpeg + NVIDIA)")
        self.layout = QVBoxLayout()

        self.input_label = QLabel("Image Sequence Folders (drag & drop supported):")
        self.layout.addWidget(self.input_label)
        self.input_list = QListWidget()
        self.input_list.setAcceptDrops(True)
        self.input_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.input_list.viewport().setAcceptDrops(True)
        self.input_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.layout.addWidget(self.input_list)

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
        self.hwaccel_combo.addItems(["Auto-detect", "NVIDIA (h264_nvenc)", "CPU (libx264)"])
        self.layout.addWidget(self.hwaccel_combo)

        # Add encoding preset selection
        self.preset_label = QLabel("Encoding Preset:")
        self.layout.addWidget(self.preset_label)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "ProRes 422",
            "ProRes 422 Proxy",
            "H.264 25Mbps"
        ])
        self.layout.addWidget(self.preset_combo)

        self.run_btn = QPushButton("Convert All")
        self.run_btn.clicked.connect(self.run_ffmpeg_batch)
        self.layout.addWidget(self.run_btn)

        self.status_label = QLabel("")
        self.layout.addWidget(self.status_label)

        # Add toggle button and ffmpeg output box
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

    def toggle_ffmpeg_output(self, checked):
        if checked:
            self.toggle_output_btn.setText("Hide FFmpeg Output")
            self.ffmpeg_output.setVisible(True)
        else:
            self.toggle_output_btn.setText("Show FFmpeg Output")
            self.ffmpeg_output.setVisible(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            folder_name = os.path.basename(os.path.normpath(path))
            existing_paths = [self.input_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.input_list.count())]
            if os.path.isdir(path) and path not in existing_paths:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setData(Qt.ItemDataRole.UserRole + 1, None)  # Audio path
                widget = self._create_folder_widget(folder_name, item)
                self.input_list.addItem(item)
                self.input_list.setItemWidget(item, widget)

    def _create_folder_widget(self, folder_name, item):
        return FolderWidget(folder_name, item, self)

    def _browse_audio(self, item, audio_label, folder_widget=None):
        options = QFileDialog.Option.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Audio/Video File", "",
            "Audio/Video Files (*.wav *.mp3 *.aac *.flac *.m4a *.ogg *.mp4 *.mov *.mkv *.avi *.webm *.m4v)", options=options)
        if file:
            has_audio = self._audio_file_has_audio(file)
            item.setData(Qt.ItemDataRole.UserRole + 1, file if has_audio else None)
            if folder_widget:
                folder_widget.set_audio_file(file)
            else:
                if has_audio:
                    audio_label.setText(os.path.basename(file))
                    # audio_label.setStyleSheet("color: black;")
                else:
                    audio_label.setText(os.path.basename(file))
                    audio_label.setStyleSheet("color: red;")

    def _audio_file_has_audio(self, file):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", file],
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

        if not os.path.isdir(output_dir):
            QMessageBox.critical(self, "Error", "Invalid output folder.")
            return

        folders = [self.input_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.input_list.count())]
        audio_files = [self.input_list.item(i).data(Qt.ItemDataRole.UserRole + 1) for i in range(self.input_list.count())]
        items = [self.input_list.item(i) for i in range(self.input_list.count())]
        if not folders:
            QMessageBox.critical(self, "Error", "No input folders selected.")
            return

        for folder, audio_file, item in zip(folders, audio_files, items):
            self.status_label.setText(f"Rendering: {folder}")
            QApplication.processEvents()
            success, error_msg = self.run_ffmpeg(folder, output_dir, fps, hwaccel, preset, audio_file)
            if success:
                self.set_item_checkmark(item)
            else:
                folder_name = os.path.basename(folder)
                QMessageBox.critical(self, "Error", f"Failed rendering: {folder_name}\n\nError:\n{error_msg}")
                self.status_label.setText(f"Error rendering: {folder_name}")
                return  # Abort further operations
        self.status_label.setText("All renders finished.")

    def set_item_checkmark(self, item):
        # Get the widget for this item and add a green checkmark to the left of the red X
        widget = self.input_list.itemWidget(item)
        if widget:
            layout = widget.layout()
            # Remove existing checkmark if present
            if layout.count() > 2 and isinstance(layout.itemAt(0).widget(), QLabel):
                layout.itemAt(0).widget().deleteLater()
                layout.removeItem(layout.itemAt(0))
            # Add green checkmark QLabel
            check_label = QLabel()
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QColor("green"))
            painter.setBrush(QColor("green"))
            # Draw checkmark
            painter.drawLine(4, 10, 8, 14)
            painter.drawLine(8, 14, 13, 5)
            painter.end()
            check_label.setPixmap(pixmap)
            layout.insertWidget(0, check_label)

    def run_ffmpeg(self, input_dir, output_dir, fps, hwaccel, preset, audio_file=None):
        files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'))])
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

        if preset == "ProRes 422":
            output_file = os.path.join(output_dir, f"{base_name}_prores422.mov")
            codec = "prores_ks"
            ffmpeg_args = ["-profile:v", "3"]
        elif preset == "ProRes 422 Proxy":
            output_file = os.path.join(output_dir, f"{base_name}_prores422proxy.mov")
            codec = "prores_ks"
            ffmpeg_args = ["-profile:v", "0"]
        elif preset == "H.264 25Mbps":
            output_file = os.path.join(output_dir, f"{base_name}_h264.mp4")
            use_nvenc = False
            if hwaccel == "NVIDIA (h264_nvenc)":
                use_nvenc = True
            elif hwaccel == "Auto-detect":
                try:
                    result = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if "h264_nvenc" in result.stdout:
                        use_nvenc = True
                except Exception:
                    pass
            codec = "h264_nvenc" if use_nvenc else "libx264"
            ffmpeg_args = ["-b:v", "25M"]
        else:
            output_file = os.path.join(output_dir, f"{base_name}.mp4")
            codec = "libx264"
            ffmpeg_args = []

        cmd = [
            "ffmpeg",
            "-framerate", fps,
            "-i", input_pattern,
        ]

        # Add audio if provided
        if audio_file:
            cmd += ["-i", audio_file, "-map", "0:v:0", "-map", "1:a:0?"]
        # If no audio, just map video
        else:
            cmd += []

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

    def remove_selected_folders(self):
        for item in self.input_list.selectedItems():
            self.input_list.takeItem(self.input_list.row(item))

    def browse_output(self):
        options = QFileDialog.Option.DontUseNativeDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", options=options)
        if folder:
            self.output_path.setText(folder)

    def _remove_item(self, item):
        row = self.input_list.row(item)
        widget = self.input_list.itemWidget(item)
        if widget:
            widget.deleteLater()
        self.input_list.takeItem(row)

class FolderWidget(QWidget):
    AUDIO_EXTS = ('.wav', '.mp3', '.aac', '.flac', '.m4a', '.ogg', '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v')

    def __init__(self, folder_name, item, parent):
        super().__init__()
        self.item = item
        self.parent = parent  # Reference to FFmpegGUI
        self.setAcceptDrops(True)
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        self.check_label = QLabel()
        self.check_label.setFixedSize(QSize(16, 16))
        layout.addWidget(self.check_label)
        remove_btn = QPushButton()
        remove_btn.setFixedSize(QSize(20, 20))
        remove_btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
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
        remove_btn.clicked.connect(lambda: parent._remove_item(item))
        label = QLabel(folder_name)
        # label.setStyleSheet("color: black;")
        layout.addWidget(remove_btn)
        layout.addWidget(label)

        # Separator for clarity
        separator = QLabel(" | ")
        separator.setStyleSheet("color: gray;")
        layout.addWidget(separator)

        self.audio_label = QLabel("No audio")
        # self.audio_label.setStyleSheet("color: black;")
        self.browse_audio_btn = QPushButton("Browse Audio")
        self.browse_audio_btn.setFixedSize(QSize(90, 22))
        self.browse_audio_btn.clicked.connect(lambda: parent._browse_audio(item, self.audio_label, self))
        layout.addWidget(self.audio_label)
        layout.addWidget(self.browse_audio_btn)
        # Red X for removing audio, hidden by default
        self.remove_audio_btn = QPushButton()
        self.remove_audio_btn.setFixedSize(QSize(20, 20))
        self.remove_audio_btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
        pixmap2 = QPixmap(16, 16)
        pixmap2.fill(Qt.GlobalColor.transparent)
        painter2 = QPainter(pixmap2)
        painter2.setPen(QColor("red"))
        painter2.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter2.drawLine(4, 4, 12, 12)
        painter2.drawLine(12, 4, 4, 12)
        painter2.end()
        self.remove_audio_btn.setIcon(QIcon(pixmap2))
        self.remove_audio_btn.setIconSize(QSize(16, 16))
        self.remove_audio_btn.clicked.connect(self.remove_audio)
        self.remove_audio_btn.hide()
        layout.addWidget(self.remove_audio_btn)
        layout.addStretch()
        self.setLayout(layout)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(self.AUDIO_EXTS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file = url.toLocalFile()
            if file.lower().endswith(self.AUDIO_EXTS):
                self.set_audio_file(file)
                break

    def set_audio_file(self, file):
        has_audio = self.parent._audio_file_has_audio(file)
        self.item.setData(Qt.ItemDataRole.UserRole + 1, file if has_audio else None)
        if has_audio:
            self.audio_label.setText(os.path.basename(file))
            # self.audio_label.setStyleSheet("color: black;")
            self.browse_audio_btn.hide()
            self.remove_audio_btn.show()
        else:
            self.audio_label.setText(os.path.basename(file))
            self.audio_label.setStyleSheet("color: red;")
            self.browse_audio_btn.hide()
            self.remove_audio_btn.show()

    def remove_audio(self):
        self.item.setData(Qt.ItemDataRole.UserRole + 1, None)
        self.audio_label.setText("No audio")
        # self.audio_label.setStyleSheet("color: black;")
        self.browse_audio_btn.show()
        self.remove_audio_btn.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FFmpegGUI()
    window.show()
    sys.exit(app.exec())