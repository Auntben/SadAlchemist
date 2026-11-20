# SadAlchemist
A quick tool to convert an image sequence into a video file using FFMPEG. 

The files will be named with this nomenclature: Folder Name_Take Number_Task Code

Final renders are named: Folder Name_Final_vN (N is one higher than the latest version of that folder already in the output folder)

An optional Prefix and Suffix can be added to either: Prefix_Folder Name_Take Number_Task Code_Suffix

## Features:
- Drag and Drop image sequence folders (or single frames) to create render queue, or use Add Folder.
- Any frame numbering works (e.g. sequences starting at 1001); the frame range is shown per folder and missing frames are flagged.
- Optionally add an audio source from Audio or Video files
  - Compatible Audio Source File Types: .wav, .mp3, .aac, .flac, .m4a, .ogg, .mp4, .mov, .mkv, .avi, .webm, .m4v
  - Image Sequence duration will always overrule audio source duration
- Autofill and Auto-Increase take number based on audio source name allowing use of previous takes for audio source
- Final render mode with automatic version numbering
- Live preview of file output name, with warnings before overwriting existing files.
- Live preview of ffmpeg output, per-item status, and a Cancel button.
- Changeable Frame Rate for Renders (default: 24fps, NTSC rates like 23.976 supported)
- Nvidia Hardware Accelerated Encoding for MP4 with Auto-Detection for compatibility
- Encoding Presets: H.264 MP4 at 25 Mbps, Apple ProRes 422 Proxy, 422 LT, 422, 422 HQ, 4444 and 4444 XQ (4444 presets keep alpha)
- EXR sequences are converted from linear to sRGB
- Settings (output folder, task code, preset, frame rate) are remembered between sessions
- FFMPEG and FFPROBE included within the build

When running from source, ffmpeg/ffprobe are found in `ffmpeg_win/` (Windows) or `ffmpeg_osx/` (macOS), falling back to your PATH.

## Built With
Windows:
```
pyinstaller -F --noconsole --icon=SadAlchemist.ico --add-data "ffmpeg_win/ffmpeg.exe;bin" --add-data "ffmpeg_win/ffprobe.exe;bin" --add-data "SadAlchemist.ico;." SadAlchemist.py
```
Do this with venv active.

Make sure there's a ffmpeg.exe and ffprobe.exe in the ffmpeg_win folder. You can get the latest versions at https://www.gyan.dev/ffmpeg/builds/
Choose "release full" ZIP

OSX:
```
pyinstaller --noconfirm --add-binary="/opt/homebrew/bin/ffmpeg:bin" --add-binary="/opt/homebrew/bin/ffprobe:bin" --osx-bundle-identifier ca.sadfish.sadalchemist --icon=SadAlchemist.ico --add-data "SadAlchemist.ico:." -w SadAlchemist.py
```

You will need to have ffmpeg and ffprobe installed via the ffmpeg homebrew package.
