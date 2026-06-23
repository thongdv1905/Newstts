# Newstts

## Tool tạo video từ hình ảnh và âm thanh

Repo này cung cấp script `tools/create_video.py` để tạo video MP4 từ một ảnh hoặc một thư mục ảnh. Bạn có thể dùng file âm thanh có sẵn hoặc nhập text/prompt để tool tự tạo giọng đọc làm audio.

### Yêu cầu

- Python 3.10+
- `ffmpeg` có trong `PATH`
- Một engine tạo giọng đọc nếu dùng `--text` hoặc `--text-file`: `pyttsx3`, `espeak`, hoặc `say` trên macOS


## Web chạy localhost:2000

Bạn có thể chạy giao diện web local để upload ảnh, audio nền và nhập text/prompt tạo giọng đọc:

```bash
python web/app.py
```

Sau đó mở trình duyệt tại:

```text
http://localhost:2000
```

Web hỗ trợ chọn nhiều ảnh để tạo slideshow, upload audio nền, nhập prompt để tạo giọng đọc, trộn audio nền với giọng đọc, và tải video MP4 sau khi tạo xong. File đầu ra được lưu trong thư mục `generated_videos/`.

### Cách dùng CLI

Tạo video từ một ảnh và một file âm thanh:

```bash
python tools/create_video.py --images path/to/image.jpg --audio path/to/audio.mp3 --output output/video.mp4
```


Tạo video từ ảnh và text/prompt, tool sẽ tự tạo file giọng đọc:

```bash
python tools/create_video.py \
  --images path/to/image.jpg \
  --text "Xin chào, đây là nội dung giọng đọc cho video." \
  --output output/video.mp4 \
  --voice vi
```

Tạo video từ nội dung trong file text UTF-8:

```bash
python tools/create_video.py \
  --images path/to/images \
  --text-file path/to/prompt.txt \
  --output output/video.mp4 \
  --tts-engine espeak \
  --voice vi \
  --speech-rate 150
```

Nếu truyền đồng thời `--audio` và `--text`/`--text-file`, tool sẽ tạo giọng đọc rồi trộn với audio nền. Có thể chỉnh âm lượng bằng `--background-volume` và `--narration-volume`.

Tạo slideshow từ một thư mục ảnh và file âm thanh có sẵn:

```bash
python tools/create_video.py \
  --images path/to/images \
  --audio path/to/audio.mp3 \
  --output output/slideshow.mp4 \
  --image-duration 4 \
  --fps 30 \
  --resolution 1920:1080
```

### Tuỳ chọn chính

- `--images`: đường dẫn tới một ảnh hoặc một thư mục chứa ảnh (`jpg`, `jpeg`, `png`, `webp`, `bmp`).
- `--audio`: đường dẫn tới file âm thanh, ví dụ `mp3` hoặc `wav`; không bắt buộc nếu dùng `--text` hoặc `--text-file`.
- `--text`: text/prompt cần chuyển thành giọng đọc.
- `--text-file`: file text UTF-8 cần chuyển thành giọng đọc.
- `--tts-output`: nơi lưu file audio giọng đọc được tạo; mặc định là file `.narration.wav` cạnh video đầu ra.
- `--tts-engine`: engine tạo giọng đọc: `auto`, `pyttsx3`, `espeak`, hoặc `say`; mặc định là `auto`.
- `--voice`: tên/id giọng đọc truyền cho engine, ví dụ `vi` hoặc `vi+f3` với `espeak`.
- `--speech-rate`: tốc độ đọc truyền cho engine.
- `--background-volume`: âm lượng audio nền khi trộn với giọng đọc; mặc định là `0.35`.
- `--narration-volume`: âm lượng giọng đọc khi trộn với audio nền; mặc định là `1.0`.
- `--output`: đường dẫn file video MP4 đầu ra.
- `--image-duration`: số giây hiển thị mỗi ảnh khi tạo slideshow từ thư mục ảnh; mặc định là `5`.
- `--fps`: số khung hình mỗi giây; mặc định là `30`.
- `--resolution`: kích thước video theo định dạng `WIDTH:HEIGHT`; mặc định là `1920:1080`.
