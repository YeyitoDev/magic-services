"""Tests for utility functions."""

import pytest
from utils.text_parser import extract_amount, clean_text, extract_date


class TestTextParser:
    def test_extract_amount_yape(self):
        assert extract_amount("¡Yapeaste! S/ 50.00 a Juan") == 50.0

    def test_extract_amount_plin(self):
        assert extract_amount("Enviaste S/ 150.00 por Plin") == 150.0

    def test_extract_amount_soles(self):
        assert extract_amount("Transferencia por S/ 200") == 200.0

    def test_extract_amount_no_match(self):
        assert extract_amount("Hola mundo") is None

    def test_clean_text_fixes_ocr(self):
        result = clean_text("Hola\nMundo  5/ 100")
        assert "S/" in result
        assert "\n" not in result

    def test_extract_date_ddmmyyyy(self):
        assert extract_date("05/07/2024") == "05072024"

    def test_extract_date_ymd(self):
        assert extract_date("2024-07-05") == "05072024"

    def test_extract_date_no_match(self):
        assert extract_date("Hola mundo") is None


class TestDatetimeUtils:
    def test_get_lima_time(self):
        from utils.datetime_utils import get_lima_time
        now = get_lima_time()
        assert now is not None
        assert str(now.tzinfo) == "America/Lima"

    def test_format_date_spanish(self):
        from utils.datetime_utils import format_date_spanish
        from datetime import datetime
        dt = datetime(2025, 1, 15, 14, 30)
        result = format_date_spanish(dt)
        assert "enero" in result
        assert "2025" in result
