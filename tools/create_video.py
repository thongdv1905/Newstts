#!/usr/bin/env python3
"""Create an MP4 video from one or more images and an audio file."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
TTS_ENGINES = {"auto", "pyttsx3", "espeak", "say"}


def positive_float(value: str) -> float:
    """Parse a positive float for argparse."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def collect_images(image_input: Path) -> list[Path]:
    """Return sorted image paths from a file or directory."""
    if image_input.is_file():
        if image_input.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image extension: {image_input.suffix}")
        return [image_input]

    if image_input.is_dir():
        images = sorted(
            path for path in image_input.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if images:
            return images
        raise ValueError(f"No supported image files found in {image_input}")

    raise ValueError(f"Image path does not exist: {image_input}")


def resolve_prompt_text(text: str | None, text_file: Path | None) -> str | None:
    """Resolve narration text from an inline prompt or a text file."""
    if text and text_file:
        raise ValueError("Use either --text or --text-file, not both")
    if text_file:
        if not text_file.is_file():
            raise ValueError(f"Text file does not exist: {text_file}")
        resolved = text_file.read_text(encoding="utf-8").strip()
    else:
        resolved = text.strip() if text else ""

    return resolved or None


def synthesize_with_pyttsx3(text: str, output: Path, voice: str | None, rate: int | None) -> None:
    """Create speech audio with pyttsx3 when that optional package is installed."""
    import pyttsx3

    engine = pyttsx3.init()
    if voice:
        for available_voice in engine.getProperty("voices"):
            voice_id = getattr(available_voice, "id", "")
            voice_name = getattr(available_voice, "name", "")
            if voice.lower() in voice_id.lower() or voice.lower() in voice_name.lower():
                engine.setProperty("voice", voice_id)
                break
    if rate:
        engine.setProperty("rate", rate)
    engine.save_to_file(text, str(output))
    engine.runAndWait()


def synthesize_with_espeak(text: str, output: Path, voice: str | None, rate: int | None) -> None:
    """Create speech audio with the espeak command-line tool."""
    command = ["espeak", "-w", str(output)]
    if voice:
        command.extend(["-v", voice])
    if rate:
        command.extend(["-s", str(rate)])
    command.append(text)
    subprocess.run(command, check=True)


def synthesize_with_say(text: str, output: Path, voice: str | None, rate: int | None) -> None:
    """Create speech audio with macOS say and convert it to WAV with ffmpeg."""
    with tempfile.TemporaryDirectory(prefix="image_audio_tts_") as temp_dir:
        aiff_output = Path(temp_dir) / "speech.aiff"
        command = ["say", "-o", str(aiff_output)]
        if voice:
            command.extend(["-v", voice])
        if rate:
            command.extend(["-r", str(rate)])
        command.append(text)
        subprocess.run(command, check=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(aiff_output), str(output)], check=True)


def synthesize_speech(
    text: str,
    output: Path,
    engine: str,
    voice: str | None = None,
    rate: int | None = None,
) -> Path:
    """Create narration audio from prompt text using an available TTS engine."""
    if engine not in TTS_ENGINES:
        raise ValueError(f"Unsupported TTS engine: {engine}")

    output.parent.mkdir(parents=True, exist_ok=True)
    candidates = [engine] if engine != "auto" else ["pyttsx3", "espeak", "say"]
    errors: list[str] = []

    for candidate in candidates:
        try:
            if candidate == "pyttsx3":
                if importlib.util.find_spec("pyttsx3") is None:
                    errors.append("pyttsx3 is not installed")
                    continue
                synthesize_with_pyttsx3(text, output, voice, rate)
                return output
            if candidate == "espeak":
                if shutil.which("espeak") is None:
                    errors.append("espeak was not found in PATH")
                    continue
                synthesize_with_espeak(text, output, voice, rate)
                return output
            if candidate == "say":
                if shutil.which("say") is None:
                    errors.append("say was not found in PATH")
                    continue
                synthesize_with_say(text, output, voice, rate)
                return output
        except subprocess.CalledProcessError as exc:
            errors.append(f"{candidate} failed: {exc}")

    detail = "; ".join(errors) if errors else "no TTS engine was attempted"
    raise ValueError(f"Could not synthesize speech ({detail})")


def mix_audio_files(
    background_audio: Path,
    narration_audio: Path,
    output: Path,
    background_volume: float = 0.35,
    narration_volume: float = 1.0,
) -> Path:
    """Mix existing audio with generated narration, lowering the background track."""
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(background_audio),
        "-i",
        str(narration_audio),
        "-filter_complex",
        f"[0:a]volume={background_volume}[bg];"
        f"[1:a]volume={narration_volume}[voice];"
        "[bg][voice]amix=inputs=2:duration=longest:dropout_transition=2[a]",
        "-map",
        "[a]",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output),
    ]
    subprocess.run(command, check=True)
    return output


def build_single_image_command(
    image: Path,
    audio: Path,
    output: Path,
    fps: int,
    resolution: str,
) -> list[str]:
    """Build an ffmpeg command that loops one image for the whole audio track."""
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image),
        "-i",
        str(audio),
        "-vf",
        f"scale={resolution}:force_original_aspect_ratio=decrease,"
        f"pad={resolution}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        str(output),
    ]


def build_slideshow_command(
    image_list_file: Path,
    audio: Path,
    output: Path,
    fps: int,
    resolution: str,
) -> list[str]:
    """Build an ffmpeg command for a timed image slideshow with audio."""
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(image_list_file),
        "-i",
        str(audio),
        "-vf",
        f"scale={resolution}:force_original_aspect_ratio=decrease,"
        f"pad={resolution}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        str(output),
    ]


def write_concat_file(images: list[Path], duration: float, destination: Path) -> None:
    """Write an ffmpeg concat demuxer file for the slideshow."""
    lines: list[str] = []
    for image in images:
        safe_path = str(image.resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")
        lines.append(f"duration {duration}")
    # The concat demuxer needs the last file repeated so its duration is honored.
    last_path = str(images[-1].resolve()).replace("'", "'\\''")
    lines.append(f"file '{last_path}'")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_video(
    images: list[Path],
    audio: Path,
    output: Path,
    image_duration: float,
    fps: int,
    resolution: str,
) -> None:
    """Create a video from images and audio using ffmpeg."""
    if not audio.is_file():
        raise ValueError(f"Audio file does not exist: {audio}")

    output.parent.mkdir(parents=True, exist_ok=True)

    if len(images) == 1:
        command = build_single_image_command(images[0], audio, output, fps, resolution)
        subprocess.run(command, check=True)
        return

    with tempfile.TemporaryDirectory(prefix="image_audio_video_") as temp_dir:
        concat_file = Path(temp_dir) / "images.txt"
        write_concat_file(images, image_duration, concat_file)
        command = build_slideshow_command(concat_file, audio, output, fps, resolution)
        subprocess.run(command, check=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an MP4 video from one image or a folder of images plus an audio file."
    )
    parser.add_argument("--images", required=True, type=Path, help="Image file or image folder.")
    parser.add_argument("--audio", type=Path, help="Audio file, such as MP3 or WAV. Optional when --text or --text-file is used.")
    parser.add_argument("--text", help="Prompt text to turn into narration audio when --audio is omitted.")
    parser.add_argument("--text-file", type=Path, help="UTF-8 text file to turn into narration audio when --audio is omitted.")
    parser.add_argument("--tts-output", type=Path, help="Where to save generated narration audio. Default: beside output video.")
    parser.add_argument(
        "--tts-engine",
        choices=sorted(TTS_ENGINES),
        default="auto",
        help="Text-to-speech engine. Default: auto.",
    )
    parser.add_argument(
        "--voice",
        help="Voice name/id passed to the selected TTS engine, for example vi or vi+f3 for espeak.",
    )
    parser.add_argument("--speech-rate", type=int, help="Speech rate passed to the selected TTS engine.")
    parser.add_argument(
        "--background-volume",
        type=positive_float,
        default=0.35,
        help="Background audio volume when mixing --audio with generated narration. Default: 0.35.",
    )
    parser.add_argument(
        "--narration-volume",
        type=positive_float,
        default=1.0,
        help="Generated narration volume when mixing with --audio. Default: 1.0.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Output MP4 file path.")
    parser.add_argument(
        "--image-duration",
        type=positive_float,
        default=5.0,
        help="Seconds to show each image when --images is a folder. Default: 5.",
    )
    parser.add_argument("--fps", type=int, default=30, help="Output frames per second. Default: 30.")
    parser.add_argument(
        "--resolution",
        default="1920:1080",
        help="Output resolution as WIDTH:HEIGHT for ffmpeg scale/pad. Default: 1920:1080.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if shutil.which("ffmpeg") is None:
        print("Error: ffmpeg is required but was not found in PATH.", file=sys.stderr)
        return 127

    try:
        images = collect_images(args.images)
        prompt_text = resolve_prompt_text(args.text, args.text_file)
        audio = args.audio
        if audio is None and prompt_text is None:
            raise ValueError("Provide --audio or prompt narration with --text/--text-file")

        with tempfile.TemporaryDirectory(prefix="image_audio_mix_") as temp_dir:
            if prompt_text is not None:
                tts_output = args.tts_output or args.output.with_suffix(".narration.wav")
                narration_audio = synthesize_speech(
                    text=prompt_text,
                    output=tts_output,
                    engine=args.tts_engine,
                    voice=args.voice,
                    rate=args.speech_rate,
                )
                if audio is None:
                    audio = narration_audio
                else:
                    audio = mix_audio_files(
                        background_audio=audio,
                        narration_audio=narration_audio,
                        output=Path(temp_dir) / "mixed_audio.m4a",
                        background_volume=args.background_volume,
                        narration_volume=args.narration_volume,
                    )

            create_video(
                images=images,
                audio=audio,
                output=args.output,
                image_duration=args.image_duration,
                fps=args.fps,
                resolution=args.resolution,
            )
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Created video: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
