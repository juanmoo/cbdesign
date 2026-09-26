"""Self-contained, bounded HTML walkthroughs for exported nominal plans."""
from __future__ import annotations

import json
from html import escape

# Exports remain useful even when a particularly large trace cannot be embedded.
MAX_REPLAY_BYTES = 16 * 1024 * 1024

STYLE = """
:root { color-scheme: light; --ground:#f1f5f7; --surface:#ffffff; --ink:#20323f;
  --muted:#526673; --line:#b8c9d2; --accent:#176483; }
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
  --ground:#15232c;--surface:#20323f;--ink:#edf4f7;--muted:#b5c8d2;--line:#526673;--accent:#85d0ed;}}
:root[data-theme="dark"]{color-scheme:dark;--ground:#15232c;--surface:#20323f;
  --ink:#edf4f7;--muted:#b5c8d2;--line:#526673;--accent:#85d0ed;}
*{box-sizing:border-box} body{margin:0;background:var(--ground);color:var(--ink);
  font:16px/1.5 system-ui,sans-serif;padding-inline:16px;padding-block:24px;}
main{max-width:1200px;margin:auto}h1,h2,h3{text-wrap:balance;line-height:1.2}
h1{font-family:Georgia,serif;font-size:2rem;margin:0}p{max-width:75ch}
small,.note{color:var(--muted)}nav{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
  padding-block:16px;position:sticky;top:0;background:var(--ground);z-index:1}
button,select{font:inherit;border:1px solid var(--line);border-radius:4px;padding:9px 12px;
  background:var(--surface);color:var(--ink);max-width:100%;cursor:pointer}
select{flex:1;min-width:0}button:disabled{opacity:.5;cursor:default}
:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
#step{padding:16px;background:var(--surface);border:1px solid var(--line);overflow-wrap:anywhere}
#step svg{max-width:100%;height:auto;background:white;color:#20323f}
#step table{display:block;max-width:100%;overflow-x:auto;border-collapse:collapse}
#step td,#step th{padding:6px;text-align:left;border-bottom:1px solid var(--line)}
#step a{color:var(--accent)}#position{font-variant-numeric:tabular-nums}
code{font-family:ui-monospace,monospace} [hidden]{display:none!important}
@media(max-width:500px){body{padding-block:16px}nav select{flex-basis:100%;order:-1}}
"""

SCRIPT = """
const data=JSON.parse(document.getElementById('replay-data').textContent);
const select=document.getElementById('step-select'), content=document.getElementById('step');
let current=0;
data.manifest.steps.forEach((s,i)=>{const o=document.createElement('option');
  o.value=i;o.textContent=s.label||s.title||String(i);select.append(o);});
function show(index){
  if(!Number.isInteger(index)||index<0||index>=data.frames.length)return;
  current=index;select.value=String(index);const frame=data.frames[index];
  content.innerHTML=frame.html;
  document.getElementById('position').textContent=frame.title||data.manifest.steps[index].label||'';
  document.getElementById('previous').disabled=index===0;
  document.getElementById('next').disabled=index===data.frames.length-1;
}
select.addEventListener('change',()=>show(Number(select.value)));
document.getElementById('previous').addEventListener('click',()=>show(current-1));
document.getElementById('next').addEventListener('click',()=>show(current+1));
content.addEventListener('click',e=>{const link=e.target.closest('[data-step]');
  if(link){e.preventDefault();show(Number(link.dataset.step));}});
document.addEventListener('keydown',e=>{
  if(e.target.closest('input,select,textarea')||e.altKey||e.ctrlKey||e.metaKey)return;
  if(e.key==='ArrowLeft'){e.preventDefault();show(current-1);}
  if(e.key==='ArrowRight'){e.preventDefault();show(current+1);}
});
show(0);
"""


def _page(content: str) -> bytes:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<title>Fabrication Replay</title><style>{STYLE}</style></head><body><main>'
            f'<h1>Fabrication replay</h1><p class="note">Nominal geometry only. '
            f'This walkthrough does not certify machine safety or physical suitability.</p>'
            f'{content}</main></body></html>').encode('utf-8')


def unavailable_html(reason: str) -> bytes:
    """Keep other fabrication reports accessible when the optional viewer is too large."""
    return _page('<h2>Walkthrough unavailable</h2><p>' + escape(reason) +
                 '</p><p>The complete plan and operation sequence remain in '
                 '<code>plan.json</code> and <code>operations.csv</code>. '
                 'No partial visual walkthrough is presented.</p>')


def replay_html(plan, traced=None) -> bytes:
    """Render all validated steps with the same adapter used by the local server."""
    from .render_replay import build_walkthrough, walkthrough_manifest, walkthrough_step
    from .replay_trace import TraceLimitError

    try:
        result = traced if traced is not None else build_walkthrough(plan)
        manifest = walkthrough_manifest(plan, result)
        frames = []
        size = 0
        for index in range(len(manifest['steps'])):
            frame = walkthrough_step(plan, result, index)
            # Only embed navigation/display fields, not repeated geometry metadata.
            item = {'html': frame['html'], 'title': frame.get('title', '')}
            size += len(json.dumps(item, ensure_ascii=True).encode('utf-8'))
            if size > MAX_REPLAY_BYTES:
                return unavailable_html('The complete walkthrough exceeds the 16 MiB offline export limit.')
            frames.append(item)
        payload = json.dumps({'manifest': manifest, 'frames': frames}, ensure_ascii=True,
                             separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        page = _page('<p>Start with the stock overview, then inspect each actual operation. '
                     'Use the arrow buttons or Left/Right keys. Part links jump to their producer or next use.</p>'
                     '<nav aria-label="Replay navigation"><button id="previous" type="button">Previous</button>'
                     '<label for="step-select">Step</label><select id="step-select"></select>'
                     '<button id="next" type="button">Next</button></nav>'
                     '<p id="position" aria-live="polite"></p><section id="step" aria-label="Selected step"></section>'
                     '<noscript>Enable JavaScript to navigate this offline walkthrough. '
                     'The complete operation sequence is also in operations.csv.</noscript>'
                     f'<script id="replay-data" type="application/json">{payload}</script><script>{SCRIPT}</script>')
        if len(page) > MAX_REPLAY_BYTES:
            return unavailable_html('The complete walkthrough exceeds the 16 MiB offline export limit.')
        return page
    except TraceLimitError as exc:
        return unavailable_html(str(exc))
