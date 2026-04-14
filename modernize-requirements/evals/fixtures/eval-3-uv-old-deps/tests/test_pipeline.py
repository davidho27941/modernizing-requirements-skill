import pytest
import numpy as np
from src.pipeline import preprocess_image, load_config


def test_load_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("batch_size: 32\nlr: 0.001\n")
    result = load_config(str(cfg))
    assert result["batch_size"] == 32
