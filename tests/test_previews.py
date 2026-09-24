"""Preview helpers use the CLI and never follow colliding PNG symlinks."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_png_preflight_rejects_dangling_symlink_before_cli(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('previews', ROOT / 'scripts/regenerate_previews.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    examples = tmp_path / 'examples'; examples.mkdir()
    (examples / 'example.json').write_text('{}')
    previews = tmp_path / 'previews'; target = previews / 'example'; target.mkdir(parents=True)
    missing = tmp_path / 'missing'
    (target / 'stock.png').symlink_to(missing)
    monkeypatch.setattr(module, 'EXAMPLES', examples)
    monkeypatch.setattr(module, 'PREVIEWS', previews)
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: pytest.fail('CLI must not run'))
    with pytest.raises(SystemExit, match='nonregular preview target'):
        module.main(['--png'])
    assert not missing.exists()
