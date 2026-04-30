"""Tests for the converter dispatcher and image detection.

We don't import python-docx / pypdf here — those are heavyweight; they're
exercised via integration through their own libraries. We just verify the
*dispatch logic* and a few format paths that are stdlib-only.
"""
from shared import converters


def test_image_detection_by_extension():
    assert converters.is_image("photo.png", "")
    assert converters.is_image("scan.JPEG", "")
    assert converters.is_image("doc.tiff", "")
    assert not converters.is_image("notes.txt", "")
    assert not converters.is_image("report.pdf", "")


def test_image_detection_by_content_type():
    assert converters.is_image("blob", "image/png")
    assert converters.is_image("blob", "image/jpeg")
    assert not converters.is_image("blob", "application/pdf")
    assert not converters.is_image("blob", "text/plain")


def test_convert_text():
    out = converters.convert_text(b"hello world\nsecond line")
    assert "hello world" in out
    assert "second line" in out


def test_convert_html_strips_tags_and_scripts():
    html = b"<html><head><style>x</style></head><body><p>hi <b>there</b></p><script>alert(1)</script></body></html>"
    out = converters.convert_html(html)
    assert "hi" in out
    assert "there" in out
    assert "alert(1)" not in out
    assert "<p>" not in out


def test_convert_csv_tab_separates():
    out = converters.convert_csv(b"a,b,c\n1,2,3\n")
    assert "a\tb\tc" in out
    assert "1\t2\t3" in out


def test_convert_json_pretty_prints():
    out = converters.convert_json(b'{"a":1,"b":[2,3]}')
    assert '"a": 1' in out
    assert '"b"' in out


def test_convert_json_falls_back_for_invalid():
    out = converters.convert_json(b"not json {{")
    assert "not json" in out


def test_dispatch_by_extension():
    # Plain-text path uses convert_text
    out = converters.convert("notes.txt", "text/plain", b"hi")
    assert out == "hi"


def test_dispatch_by_content_type_when_extension_unknown():
    # Unknown extension, but content type says CSV
    out = converters.convert("blob.bin", "text/csv", b"a,b\n1,2\n")
    assert "a\tb" in out


def test_dispatch_unknown_falls_back_to_text():
    out = converters.convert("file.weirdext", "", b"plain bytes")
    assert "plain bytes" in out
