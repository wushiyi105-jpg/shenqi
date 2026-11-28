"""Web 界面：http.server，零依赖。

左边合同列表，右边粘贴框和体检结果。规则的结果永远在，模型那部分跑挂了也不影响
页面可用——这是刻意的：没网、没 key 的时候，它仍然是个能查硬伤的合同检查器。
"""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import llm, review, store

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>审契 · 签之前两版差在哪</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0b0f14;color:#c9d1d9;font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:16px 24px;border-bottom:1px solid #21262d;display:flex;align-items:baseline;gap:12px}
h1{margin:0;font-size:18px;color:#7ee787;font-weight:600}
.sub{color:#8b949e;font-size:13px}
main{display:grid;grid-template-columns:300px 1fr;gap:0;min-height:calc(100vh - 60px)}
aside{border-right:1px solid #21262d;padding:16px}
section{padding:20px 24px}
textarea{width:100%;height:150px;background:#161b22;color:#c9d1d9;border:1px solid #30363d;
border-radius:8px;padding:10px;font:14px/1.6 inherit;resize:vertical}
input[type=text]{width:100%;background:#161b22;color:#c9d1d9;border:1px solid #30363d;
border-radius:8px;padding:8px 10px;font:14px inherit;margin-bottom:8px}
button{background:#238636;color:#fff;border:0;border-radius:6px;padding:8px 14px;font:14px inherit;cursor:pointer}
button.ghost{background:#21262d;color:#c9d1d9}
button:disabled{opacity:.5;cursor:default}
.item{padding:10px;border:1px solid #21262d;border-radius:8px;margin-bottom:8px;cursor:pointer;background:#0d1117}
.item:hover{border-color:#30363d}
.item .t{font-weight:600}
.item .m{color:#8b949e;font-size:12px}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;margin-right:6px}
.high{background:#4a1d1d;color:#ff7b72}
.medium{background:#3d2b13;color:#e3b341}
.low{background:#1c2f3d;color:#79c0ff}
.ok{background:#15321f;color:#7ee787}
.issue{border-left:3px solid #30363d;padding:8px 0 8px 14px;margin:14px 0}
.issue.high{border-color:#ff7b72;background:transparent}
.issue.medium{border-color:#e3b341;background:transparent}
.issue.low{border-color:#79c0ff;background:transparent}
.issue b{color:#e6edf3}
.k{color:#8b949e;font-size:13px}
.q{background:#161b22;border-radius:6px;padding:6px 10px;margin:6px 0;color:#8b949e;font-family:ui-monospace,Consolas,monospace;font-size:13px}
.empty{color:#8b949e}

:root{--maxw:1080px;--bg:#f4efdf;--card:#fffdf6;--ink:#22201b;--text:#22201b;--dim:#6e695d;--line:#d9cfb8;--accent:#8f2f2c;--muted:#6e695d}
.wrap{max-width:1080px}
body{background:#f4efdf;color:#22201b;font-family:"Songti SC","SimSun",Georgia,serif}
h1{color:#22201b}
header{max-width:1080px;margin:0 auto}
input,textarea,select{background:#fff;color:#22201b;border-color:#d9cfb8;border-radius:2px}
button:not(.ghost):not(.tab){background:#8f2f2c;color:#fff;border-radius:2px}
button.ghost{background:transparent!important;color:#8f2f2c!important;border:1px solid #d9cfb8!important}
h2,h3{color:#8f2f2c}
pre{background:#fafaf6;color:#22201b;border-color:#d9cfb8}
.item,.card{border-color:#d9cfb8;background:#fffdf6}
.k,.empty,.hint{color:#6e695d}

h1{font-size:clamp(31px,5vw,39px);line-height:1.26}
.prod{display:block;font-size:11px;line-height:1.4;letter-spacing:.18em;font-weight:650;margin-bottom:8px;opacity:.72}
.lede,.sub{max-width:62ch;line-height:1.75}
.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin:16px auto 20px;border:1px solid var(--line);background:var(--line);max-width:var(--maxw)}
.route span{padding:11px 13px;background:var(--card);font-size:12px;line-height:1.5}
.route b{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:3px;opacity:.66}
button{min-height:46px}
input,select{min-height:44px}
pre{white-space:pre-wrap}
@media(max-width:680px){
  .wrap{padding:20px 16px 56px}
  .route{grid-template-columns:1fr}
  h1{font-size:30px!important}
  .row>div{min-width:100%!important}
  button{width:100%}
}

body{background:#f4efdf;color:#22201b}
header{display:block!important;max-width:1080px;margin:0 auto;padding:24px 20px 0;background:transparent;border:0}
header h1{color:#22201b;font-size:38px;line-height:1.24}
header .sub{display:block;color:#6e695d;font-size:14px;margin-top:6px;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:1080px;margin:0 auto;background:#fffdf6;border-left:1px solid #d9cfb8;border-right:1px solid #d9cfb8;grid-template-columns:330px 1fr;min-height:calc(100vh - 150px)}
aside{background:#f9f4e7;border-right:1px solid #d9cfb8}
section{background:#fffdf6}
input,textarea,select{background:#fff;color:#22201b;border-color:#d3c7ae;border-radius:1px}
input:focus,textarea:focus,select:focus{border-color:#8f2f2c;box-shadow:0 0 0 2px #ead8d3}
button{background:#8f2f2c;color:#fff;border-radius:1px}
button:hover{background:#782521}
.item,.card{background:#fff;border-color:#d9cfb8;border-radius:1px}
h2{color:#8f2f2c}
.empty,.k{color:#6e695d}
pre{background:#fbf6e9;color:#22201b;border-color:#d9cfb8}


/* mobile-32 */
input[type=text],input[type=number],input[type=email]{background:#fff;color:#22201b;border-color:#d9cfb8}

@media(max-width:760px){
  main{grid-template-columns:1fr!important}
  aside{border-right:0!important;border-bottom:1px solid #d9cfb8;width:auto!important}
  section{padding:16px!important}
  .row{flex-wrap:wrap!important}
  .row>div{min-width:100%!important}
  h1{font-size:30px!important}
  .route{grid-template-columns:1fr!important}
  button{min-height:48px}
  pre{overflow-x:auto}
}

/* mobile-height */
@media(max-width:760px){main{min-height:auto!important}aside{min-height:0!important}}

/* mobile-sticky-cta */
.mobile-cta{display:none}
@media(max-width:760px){
  body{padding-bottom:88px}
  .route{grid-template-columns:repeat(3,minmax(0,1fr))!important}
  .route span{padding:8px 8px!important;font-size:11px!important;line-height:1.35!important}
  .route b{font-size:9px!important;margin-bottom:1px!important}
  .mobile-cta{position:fixed;left:12px;right:12px;bottom:12px;z-index:80;display:flex;
    padding:8px;border:1px solid rgba(0,0,0,.08);border-radius:12px;
    background:rgba(255,255,255,.94);backdrop-filter:blur(10px);
    box-shadow:0 10px 28px rgba(16,24,40,.18)}
  .mobile-cta button{width:100%;min-height:52px;margin:0!important;font-size:15px}
}
</style></head><body>
<header><h1><span class="prod">审契</span>签之前，这两版差在哪</h1><p class="lede">给小团队签前的条款核对：每条待复核项回到原条款和版本，能备注、提问、生成修订草稿，也能标记已交专业人士复核。</p></header>
  <div class="route" aria-label="任务步骤"><span><b>01</b>导入两版合同</span><span><b>02</b>对条款差异</span><span><b>03</b>生成谈判清单</span></div>

<main>
<aside>
  <input type="text" id="title" placeholder="合同名字，比如：云盘服务合同">
  <textarea id="text" placeholder="把合同正文粘进来…（也可以先用 CLI 导入）"></textarea>
  <div style="margin-top:8px;display:flex;gap:8px">
    <button id="add">导入</button>
    <button id="rules" class="ghost">只跑规则</button>
  </div>
  <div id="list" style="margin-top:20px"></div>
</aside>
<section id="detail"><p class="empty">左边选一份合同，或者粘一段正文进来。</p></section>
</main>
<script>
let current = null;
const $ = s => document.querySelector(s);
const LV = {high:'高', medium:'中', low:'低'};

async function loadList(){
  const r = await fetch('/api/contracts');
  const items = (await r.json()).items;
  $('#list').innerHTML = items.length ? items.map(it =>
    `<div class="item" data-id="${it.id}">
       <div class="t">${esc(it.title)}</div>
       <div class="m">${it.score===null?'未体检':it.score+' 分 · '+esc(it.verdict||'')} · ${it.reviews} 次</div>
     </div>`).join('') : '<p class="empty">还没有合同。</p>';
  document.querySelectorAll('.item').forEach(el => el.onclick = () => show(+el.dataset.id));
}

function esc(s){ return (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

async function show(id){
  current = id;
  const r = await fetch('/api/contract?id=' + id);
  const d = await r.json();
  const rv = d.review;
  let html = `<h2 style="font-size:17px">${esc(d.title)} <span class="k">#${id} · ${d.clauses} 条</span></h2>`;
  html += `<div style="margin:10px 0"><button id="run">跑体检</button>
           <button id="runRules" class="ghost">只跑规则</button>
           <button id="del" class="ghost">删除</button></div>`;
  if(!rv){
    html += `<p class="empty">这份还没体检过。</p>`;
  } else {
    html += `<p><span class="badge ${rv.score>=80?'ok':'medium'}">${rv.score} 分</span>
             <b>${esc(rv.verdict)}</b> <span class="k">· 高 ${count(rv,'high')} 中 ${count(rv,'medium')} 低 ${count(rv,'low')}
             · 缺 ${rv.missing.length} 项 · 规则 ${rv.rule_count} / 模型 ${rv.model_count}</span></p>`;
    if(rv.summary) html += `<div class="q">${esc(rv.summary)}</div>`;
    if(rv.missing.length) html += `<p class="k">缺的必备条款：${rv.missing.map(m=>esc(m.name)).join('、')}</p>`;
    html += rv.issues.map(i => `<div class="issue ${i.level}">
        <b>${esc(i.name)}</b> <span class="k">（${esc(i.clause_no)}）</span>
        ${i.quote?`<div class="q">${esc(i.quote)}</div>`:''}
        <div><span class="k">为什么：</span>${esc(i.why)}</div>
        <div><span class="k">怎么改：</span>${esc(i.suggestion)}</div></div>`).join('');
  }
  $('#detail').innerHTML = html;
  $('#run').onclick = () => run(id, false);
  $('#runRules').onclick = () => run(id, true);
  $('#del').onclick = async () => { await fetch('/api/rm', {method:'POST', body: JSON.stringify({id})}); loadList(); $('#detail').innerHTML='<p class="empty">已删除。</p>'; };
}

function count(rv, lv){ return rv.issues.filter(i=>i.level===lv).length; }

async function run(id, rulesOnly){
  const btn = rulesOnly ? $('#runRules') : $('#run');
  btn.disabled = true; btn.textContent = '跑着…';
  const r = await fetch('/api/review', {method:'POST', body: JSON.stringify({id, rules_only: rulesOnly})});
  const d = await r.json();
  btn.disabled = false; btn.textContent = rulesOnly ? '只跑规则' : '跑体检';
  if(d.error && !rulesOnly){ alert('模型没跑成：' + d.error + '（规则的结果仍然会显示）'); }
  await show(id);
}
$('#add').onclick = async () => {
  const text = $('#text').value.trim();
  if(!text) return alert('先粘一段合同正文');
  const r = await fetch('/api/add', {method:'POST', body: JSON.stringify({title: $('#title').value, text})});
  const d = await r.json();
  $('#text').value=''; loadList(); show(d.id);
};
$('#rules').onclick = async () => {
  const text = $('#text').value.trim();
  if(!text) return alert('先粘一段合同正文');
  const r = await fetch('/api/add', {method:'POST', body: JSON.stringify({title: $('#title').value, text})});
  const d = await r.json();
  $('#text').value=''; await loadList(); await show(d.id); run(d.id, true);
};
loadList();
</script>
<script>
(function(){
  var want = "跑体检";
  function norm(t){ return String(t||'').replace(/\s+/g,''); }
  var all=[].slice.call(document.querySelectorAll('button'));
  var src=null, fallback=null;
  for(var i=0;i<all.length;i++){
    var b=all[i];
    if(b.offsetParent===null||b.disabled) continue;
    if(!fallback) fallback=b;
    if(norm(b.textContent).indexOf(norm(want))>=0){ src=b; break; }
  }
  if(!src) src=fallback;
  if(!src) return;
  var bar=document.createElement('div'); bar.className='mobile-cta';
  var btn=src.cloneNode(true); btn.removeAttribute('id'); btn.type='button';
  btn.addEventListener('click',function(e){e.preventDefault(); src.click();});
  bar.appendChild(btn); document.body.appendChild(bar);
})();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    conn = None

    def log_message(self, fmt, *args):  # 别把每条请求都刷到终端
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/contracts":
            self._json({"items": store.list_contracts(self.conn)})
            return
        if parsed.path == "/api/contract":
            try:
                cid = int(qs.get("id", ["0"])[0])
            except ValueError:
                self._json({"error": "id 不合法"}, 400)
                return
            row = store.get_contract(self.conn, cid)
            if not row:
                self._json({"error": "没有这份合同"}, 404)
                return
            from . import text as T
            self._json({
                "id": row["id"],
                "title": row["title"],
                "source": row["source"],
                "clauses": len(T.split_clauses(row["text"])),
                "review": store.latest_review(self.conn, cid),
            })
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        body = self._body()
        if parsed.path == "/api/add":
            text = (body.get("text") or "").strip()
            if not text:
                self._json({"error": "正文为空"}, 400)
                return
            title = (body.get("title") or "").strip() or "未命名合同"
            cid = store.add_contract(self.conn, title, text, source="web")
            self._json({"id": cid})
            return
        if parsed.path == "/api/review":
            try:
                cid = int(body.get("id"))
            except (TypeError, ValueError):
                self._json({"error": "id 不合法"}, 400)
                return
            row = store.get_contract(self.conn, cid)
            if not row:
                self._json({"error": "没有这份合同"}, 404)
                return
            rules_only = bool(body.get("rules_only"))
            try:
                result = review.review(row["text"], config=llm.default_config(), use_model=not rules_only)
            except Exception as e:  # noqa: BLE001  页面不能因为一次调用就 500
                self._json({"error": repr(e)}, 500)
                return
            store.save_review(self.conn, cid, result)
            self._json({"ok": True, "error": result.get("error", ""), "score": result["score"]["score"]})
            return
        if parsed.path == "/api/rm":
            try:
                cid = int(body.get("id"))
            except (TypeError, ValueError):
                self._json({"error": "id 不合法"}, 400)
                return
            store.delete_contract(self.conn, cid)
            self._json({"ok": True})
            return
        self._json({"error": "not found"}, 404)


def make_server(conn, host: str = "127.0.0.1", port: int = 8768) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"conn": conn})
    return ThreadingHTTPServer((host, port), handler)


def serve(conn, host: str = "127.0.0.1", port: int = 8768):
    httpd = make_server(conn, host, port)
    print(f"审契已起：http://{host}:{port}  （Ctrl+C 退出）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n再见。")
    finally:
        httpd.server_close()
