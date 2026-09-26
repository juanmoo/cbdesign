import json
from pathlib import Path
import re

from cbdesign.models import load_plan
from cbdesign.offline_replay import replay_html, unavailable_html

ROOT = Path(__file__).parents[1]


def test_offline_walkthrough_includes_all_operations():
    plan = load_plan(json.loads((ROOT / 'examples/checkerboard.json').read_text()))
    html = replay_html(plan).decode()
    payload = re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html, re.S)
    assert payload
    data = json.loads(payload.group(1))
    assert len(data['frames']) == len(plan.operations) + 2
    assert len(data['manifest']['steps']) == len(data['frames'])
    assert all(frame['html'] for frame in data['frames'])
    assert 'fetch(' not in html
    assert 'src="http' not in html
    assert 'ArrowRight' in html


def test_offline_limit_returns_explicit_notice(monkeypatch):
    import cbdesign.offline_replay as module
    plan = load_plan(json.loads((ROOT / 'examples/checkerboard.json').read_text()))
    monkeypatch.setattr(module, 'MAX_REPLAY_BYTES', 500)
    html = replay_html(plan)
    assert b'Walkthrough unavailable' in html
    assert b'id="replay-data"' not in html
    assert b'operations.csv' in html


def test_notice_escapes_untrusted_text():
    html = unavailable_html('</p><script>alert(1)</script>')
    assert b'<script>alert' not in html
    assert b'&lt;script&gt;' in html


def test_embedded_frames_cannot_close_json_script(monkeypatch):
    from cbdesign import render_replay
    monkeypatch.setattr(render_replay, 'build_walkthrough', lambda plan: object())
    monkeypatch.setattr(render_replay, 'walkthrough_manifest', lambda plan, result: {'steps': [{'label': '</script>'}]})
    monkeypatch.setattr(render_replay, 'walkthrough_step', lambda plan, result, index: {'html': '<p>&lt;safe&gt;</p>', 'title': '</script><script>bad()</script>'})
    html = replay_html(object()).decode()
    payload = re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert '</script>' not in payload
    assert json.loads(payload)['frames'][0]['title'] == '</script><script>bad()</script>'
