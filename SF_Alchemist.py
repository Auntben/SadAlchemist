import sys
import os
import subprocess
import re

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QLabel, QLineEdit, QMessageBox, QComboBox, QListWidget
)
from PyQt6.QtCore import Qt

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

        self.setLayout(self.layout)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path) and path not in [self.input_list.item(i).text() for i in range(self.input_list.count())]:
                self.input_list.addItem(path)

    def browse_output(self):
        options = QFileDialog.Option.DontUseNativeDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", options=options)
        if folder:
            self.output_path.setText(folder)

    def run_ffmpeg_batch(self):
        output_dir = self.output_path.text()
        fps = self.fps_input.text()
        hwaccel = self.hwaccel_combo.currentText()
        preset = self.preset_combo.currentText()

        if not os.path.isdir(output_dir):
            QMessageBox.critical(self, "Error", "Invalid output folder.")
            return

        folders = [self.input_list.item(i).text() for i in range(self.input_list.count())]
        if not folders:
            QMessageBox.critical(self, "Error", "No input folders selected.")
            return

        for folder in folders:
            self.status_label.setText(f"Rendering: {folder}")
            QApplication.processEvents()
            success = self.run_ffmpeg(folder, output_dir, fps, hwaccel, preset)
            if success:
                QMessageBox.information(self, "Done", f"Finished rendering: {os.path.basename(folder)}")
            else:
                QMessageBox.critical(self, "Error", f"Failed rendering: {os.path.basename(folder)}")
        self.status_label.setText("All renders finished.")

    def run_ffmpeg(self, input_dir, output_dir, fps, hwaccel, preset):
        # Find first image file and extension
        files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'))])
        if not files:
            return False

        # Try to detect a sequence pattern like name0001.png
        pattern = None
        match = re.match(r"(.*?)(\d+)(\.[^.]+)$", files[0])
        if match:
            prefix, digits, ext = match.groups()
            num_digits = len(digits)
            pattern = f"{prefix}%0{num_digits}d{ext}"
        else:
            # fallback: just use the first file (will only process one frame)
            pattern = files[0]

        input_pattern = os.path.join(input_dir, pattern)
        base_name = os.path.basename(os.path.normpath(input_dir))

        # Set output extension and ffmpeg options based on preset
        if preset == "ProRes 422":
            output_file = os.path.join(output_dir, f"{base_name}_prores422.mov")
            codec = "prores_ks"
            ffmpeg_args = ["-profile:v", "3"]  # Profile 3 = ProRes 422
        elif preset == "ProRes 422 Proxy":
            output_file = os.path.join(output_dir, f"{base_name}_prores422proxy.mov")
            codec = "prores_ks"
            ffmpeg_args = ["-profile:v", "0"]  # Profile 0 = Proxy
        elif preset == "H.264 25Mbps":
            output_file = os.path.join(output_dir, f"{base_name}_h264.mp4")
            # Only use GPU for H.264
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
            # fallback
            output_file = os.path.join(output_dir, f"{base_name}.mp4")
            codec = "libx264"
            ffmpeg_args = []

        cmd = [
            "ffmpeg",
            "-framerate", fps,
            "-i", input_pattern,
            "-c:v", codec,
            *ffmpeg_args,
            "-pix_fmt", "yuv420p",
            "-y",
            output_file
        ]

        try:
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FFmpegGUI()
    window.show()
    sys.exit(app.exec())