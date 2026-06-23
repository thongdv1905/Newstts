from pathlib import Path

import pytest

from tools.create_video import collect_images, positive_float, resolve_prompt_text, write_concat_file
from web.app import safe_filename


def test_positive_float_accepts_positive_values() -> None:
    assert positive_float("2.5") == 2.5


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_positive_float_rejects_invalid_values(value: str) -> None:
    with pytest.raises(Exception):
        positive_float(value)


def test_collect_images_from_directory(tmp_path: Path) -> None:
    second = tmp_path / "b.png"
    first = tmp_path / "a.jpg"
    ignored = tmp_path / "notes.txt"
    second.write_bytes(b"fake")
    first.write_bytes(b"fake")
    ignored.write_text("not an image", encoding="utf-8")

    assert collect_images(tmp_path) == [first, second]


def test_write_concat_file_repeats_last_image(tmp_path: Path) -> None:
    first = tmp_path / "one.jpg"
    second = tmp_path / "two.jpg"
    first.write_bytes(b"fake")
    second.write_bytes(b"fake")
    concat_file = tmp_path / "images.txt"

    write_concat_file([first, second], 3.0, concat_file)

    content = concat_file.read_text(encoding="utf-8")
    assert f"file '{first.resolve()}'" in content
    assert content.count(f"file '{second.resolve()}'") == 2
    assert "duration 3.0" in content


def test_resolve_prompt_text_from_inline_text() -> None:
    assert resolve_prompt_text("  Xin chào Việt Nam  ", None) == "Xin chào Việt Nam"


def test_resolve_prompt_text_from_file(tmp_path: Path) -> None:
    text_file = tmp_path / "prompt.txt"
    text_file.write_text("Nội dung giọng đọc\n", encoding="utf-8")

    assert resolve_prompt_text(None, text_file) == "Nội dung giọng đọc"


def test_resolve_prompt_text_rejects_two_sources(tmp_path: Path) -> None:
    text_file = tmp_path / "prompt.txt"
    text_file.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError):
        resolve_prompt_text("hello", text_file)


def test_safe_filename_strips_path_components() -> None:
    assert safe_filename("../folder/photo.png") == "photo.png"
