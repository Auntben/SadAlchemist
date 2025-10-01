# SadAlchemist
A quick tool to convert an image sequence into a video file using FFMPEG. 

The files will be named with this nomenclature: Folder Name_Take Number_Task Code

## Features:
- Drag and Drop image sequence folders to create render queue.
- Optionally add an audio source from Audio or Video files
  - Compatible Audio Source File Types: .wav, .mp3, .aac, .flac, .m4a, .ogg, .mp4, .mov, .mkv, .avi, .webm, .m4v
  - Image Sequence duration will always overrule audio source duration
- Autofill and Auto-Increase take number based on audio source name allowing use of previous takes for audio source
- Live preview of file output name.
- Live preview of ffmpeg output.
- Changeable Frame Rate for Renders (default: 24fps)
- Nvidia Hardware Accelerated Encoding for MP4 with Auto-Detection for compatibility
- 3 Encoding Presets: h.264 MP4 at 15MBPS, Apple ProRes Proxy, Apple ProRes 422
- FFMPEG and FFPROBE included within the build

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
pyinstaller --noconfirm --add-binary="./ffmpeg_osx/ffmpeg:bin"  --add-binary="./ffmpeg_osx/ffprobe:bin" --osx-bundle-identifier ca.sadfish.sadalchemist --icon=SadAlchemist.ico --add-data "SadAlchemist.ico:." -w SadAlchemist.py
```

Make sure there's a ffmpeg and ffprobe in the ffmpeg_osx folder. You can get the latest versions at https://evermeet.cx/ffmpeg/
