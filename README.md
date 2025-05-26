# SadAlchemist
A quick tool to convert an image sequence into a video file using FFMPEG. 

The files will be named with this nomenclature: <Folder Name>_<Take Number>_<Task Code>

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
