#!/usr/bin/env python3
"""Boat Search price tracker.

Merges boat_tracker/new_scan.json into boat_tracker/listings.json,
appends every observed price to boat_tracker/price_log.csv, and
regenerates ../dashboard.html.

new_scan.json format: list of
  {"id": "cl-7939722168", "source": "craigslist", "title": "...",
   "price": 54900, "location": "San Diego", "url": "https://...",
   "length_ft": 25.0 or null}
"""
import csv
import json
import math
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LISTINGS = HERE / "listings.json"
SCAN = HERE / "new_scan.json"
PRICELOG = HERE / "price_log.csv"
CONFIG = HERE / "config.json"
DASHBOARD = HERE.parent / "dashboard.html"


def load_json(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


YEAR_RE = re.compile(r"\b(19[4-9]\d|20[0-2]\d)\b")


def extract_year(title):
    """Pull a plausible model year out of a listing title."""
    for m in YEAR_RE.finditer(title or ""):
        y = int(m.group(1))
        if 1950 <= y <= date.today().year + 1:
            return y
    return None


def solve3(A, b):
    """Solve a 3x3 linear system via Gaussian elimination."""
    M = [A[i][:] + [b[i]] for i in range(3)]
    for i in range(3):
        piv = max(range(i, 3), key=lambda r: abs(M[r][i]))
        if abs(M[piv][i]) < 1e-9:
            return None
        M[i], M[piv] = M[piv], M[i]
        d = M[i][i]
        M[i] = [v / d for v in M[i]]
        for r in range(3):
            if r != i:
                f = M[r][i]
                M[r] = [v - f * w for v, w in zip(M[r], M[i])]
    return [M[0][3], M[1][3], M[2][3]]


def compute_analytics(listings):
    """Fair-value model: regress log(price) on year + length across active
    listings, then score each boat as % over/under its expected price.
    Also computes price-per-foot and price percentile within the fleet."""
    active = [l for l in listings.values() if l["status"] != "gone"]
    prices = sorted(l["price_history"][-1]["price"] for l in active)

    rows = []
    for l in active:
        p = l["price_history"][-1]["price"]
        if l.get("year") and l.get("length_ft") and p and p > 0:
            rows.append((l["year"], l["length_ft"], math.log(p)))

    coef = None
    if len(rows) >= 8:
        XtX = [[0.0] * 3 for _ in range(3)]
        Xty = [0.0] * 3
        for yr, ln, ly in rows:
            x = (1.0, float(yr), float(ln))
            for i in range(3):
                Xty[i] += x[i] * ly
                for j in range(3):
                    XtX[i][j] += x[i] * x[j]
        coef = solve3(XtX, Xty)

    out = {}
    n = len(prices)
    for l in listings.values():
        p = l["price_history"][-1]["price"]
        a = {"ppf": None, "expected_price": None, "value_pct": None,
             "price_pctile": None}
        if l.get("length_ft") and p:
            a["ppf"] = round(p / l["length_ft"])
        if n and p:
            a["price_pctile"] = round(
                100 * sum(1 for q in prices if q <= p) / n)
        if coef and l.get("year") and l.get("length_ft") and p:
            exp_p = math.exp(
                coef[0] + coef[1] * l["year"] + coef[2] * l["length_ft"])
            a["expected_price"] = round(exp_p)
            a["value_pct"] = round((p - exp_p) / exp_p * 100)
        out[l["id"]] = a
    return out


def main():
    today = date.today().isoformat()
    config = load_json(CONFIG, {})
    listings = load_json(LISTINGS, {})  # id -> listing dict
    scan = load_json(SCAN, [])

    new_count, change_count = 0, 0
    changes = []

    for item in scan:
        lid = item["id"]
        price = item.get("price")
        if lid in listings:
            l = listings[lid]
            l["last_seen"] = today
            l["title"] = item.get("title", l["title"])
            l["url"] = item.get("url", l["url"])
            if item.get("length_ft") and not l.get("length_ft"):
                l["length_ft"] = item["length_ft"]
            if item.get("year") and not l.get("year"):
                l["year"] = item["year"]
            last_price = l["price_history"][-1]["price"]
            if price is not None and price != last_price:
                l["price_history"].append({"date": today, "price": price})
                change_count += 1
                changes.append(
                    f'{l["title"][:60]}: ${last_price:,} -> ${price:,}'
                )
        else:
            listings[lid] = {
                "id": lid,
                "source": item.get("source", "craigslist"),
                "title": item.get("title", ""),
                "location": item.get("location", ""),
                "url": item.get("url", ""),
                "length_ft": item.get("length_ft"),
                "year": item.get("year") or extract_year(item.get("title")),
                "first_seen": today,
                "last_seen": today,
                "price_history": [{"date": today, "price": price}],
            }
            new_count += 1

    # backfill year from title for older records
    for l in listings.values():
        if not l.get("year"):
            l["year"] = extract_year(l.get("title"))

    # merge harvested listing photos (images.json: id -> url, null = no photo)
    images = load_json(HERE / "images.json", {})
    for lid, img in images.items():
        if lid in listings and "image" not in listings[lid]:
            listings[lid]["image"] = img

    # status
    stale_days = int(config.get("stale_days", 14))
    for l in listings.values():
        last = datetime.fromisoformat(l["last_seen"]).date()
        gone_days = (date.today() - last).days
        if gone_days > stale_days:
            l["status"] = "gone"
        elif l["first_seen"] == today:
            l["status"] = "new"
        elif len(l["price_history"]) > 1:
            l["status"] = (
                "drop"
                if l["price_history"][-1]["price"] < l["price_history"][0]["price"]
                else "rise"
            )
        else:
            l["status"] = "active"

    with open(LISTINGS, "w", encoding="utf-8") as f:
        json.dump(listings, f, indent=1)

    # flat price log (Excel-friendly); skip rows already logged today
    new_file = not PRICELOG.exists()
    seen = set()
    if not new_file:
        with open(PRICELOG, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if row and row[0] == today:
                    seen.add(row[1])
    with open(PRICELOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "id", "source", "title", "price", "url"])
        for item in scan:
            if item["id"] in seen:
                continue
            w.writerow(
                [today, item["id"], item.get("source", ""), item.get("title", ""),
                 item.get("price", ""), item.get("url", "")]
            )

    render_dashboard(listings, config, today)

    active = sum(1 for l in listings.values() if l["status"] != "gone")
    print(f"Scan {today}: {len(scan)} scanned | {new_count} new | "
          f"{change_count} price changes | {active} active | "
          f"{len(listings)} total tracked")
    for c in changes:
        print("  PRICE CHANGE:", c)


def render_dashboard(listings, config, today):
    analytics = compute_analytics(listings)
    enriched = []
    for l in sorted(listings.values(),
                    key=lambda l: (l["status"] == "gone", l["first_seen"])):
        e = dict(l)
        e.update(analytics[l["id"]])
        enriched.append(e)
    data = {
        "updated": datetime.now().strftime("%B %d, %Y %I:%M %p"),
        "config": config,
        "listings": enriched,
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data))
    with open(DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Boat Search — Price Tracker</title>
<style>
  :root{
    --bg:#0d1b2a; --panel:#13263b; --panel2:#1b3350; --line:#23456b;
    --text:#e8f0f8; --dim:#8fa8c2; --accent:#4fc3f7; --green:#5dd39e;
    --red:#ff7d6b; --amber:#ffd166;
  }
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif;
       background:var(--bg);color:var(--text);padding:28px 4vw}
  h1{font-size:26px;margin:0 0 2px}
  h1 .anchor{color:var(--accent)}
  .sub{color:var(--dim);font-size:13px;margin-bottom:22px}
  .cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:22px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
        padding:14px 22px;min-width:130px}
  .card .num{font-size:28px;font-weight:700}
  .card .lbl{font-size:12px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
  .card.green .num{color:var(--green)} .card.red .num{color:var(--red)}
  .card.blue .num{color:var(--accent)}
  .controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;align-items:center}
  .controls input{background:var(--panel);border:1px solid var(--line);color:var(--text);
        border-radius:8px;padding:8px 12px;width:240px;font-size:14px}
  .fbtn{background:var(--panel);border:1px solid var(--line);color:var(--dim);
        border-radius:20px;padding:6px 14px;font-size:13px;cursor:pointer}
  .fbtn.on{background:var(--accent);color:#06121f;border-color:var(--accent);font-weight:600}
  table{width:100%;border-collapse:collapse;background:var(--panel);
        border:1px solid var(--line);border-radius:12px;overflow:hidden}
  th{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim);
     text-align:left;padding:10px 12px;background:var(--panel2);cursor:pointer;
     user-select:none;white-space:nowrap}
  th:hover{color:var(--text)}
  td{padding:10px 12px;border-top:1px solid var(--line);vertical-align:middle}
  tr:hover td{background:rgba(79,195,247,.05)}
  a{color:var(--accent);text-decoration:none}
  a:visited{color:#b98ef7}
  a:hover{text-decoration:underline}
  .price{font-weight:700;white-space:nowrap}
  .chg{font-size:12px;white-space:nowrap}
  .chg.down{color:var(--green)} .chg.up{color:var(--red)} .chg.flat{color:var(--dim)}
  .badge{display:inline-block;font-size:11px;font-weight:600;border-radius:6px;
         padding:2px 8px;text-transform:uppercase;letter-spacing:.04em}
  .b-new{background:rgba(93,211,158,.15);color:var(--green)}
  .b-drop{background:rgba(93,211,158,.15);color:var(--green)}
  .b-rise{background:rgba(255,125,107,.15);color:var(--red)}
  .b-active{background:rgba(143,168,194,.15);color:var(--dim)}
  .b-gone{background:rgba(255,209,102,.12);color:var(--amber)}
  .src{font-size:12px;color:var(--dim)}
  .dim{color:var(--dim);font-size:12px}
  tr.gone td{opacity:.45}
  .spark{vertical-align:middle}
  .charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin-bottom:8px}
  .chart{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
  .chart h3{margin:0 0 6px;font-size:12px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.05em}
  .chart svg{width:100%;height:auto;display:block}
  .pt{fill:var(--accent);opacity:.5;cursor:pointer}
  .pt:hover{opacity:1}
  .pt.nw{fill:var(--green);opacity:.9}
  .pt.gn{fill:#8a97a5;opacity:.28}
  .pt.gn:hover{opacity:.7}
  .pt.sel{fill:var(--amber);opacity:1;stroke:#fff;stroke-width:1.5}
  .axis{stroke:var(--line);stroke-width:1}
  .tick{fill:var(--dim);font-size:9px}
  tr.sel td{background:rgba(255,209,102,.1)!important}
  tr[data-id]{cursor:pointer}
  .hint{color:var(--dim);font-size:12px;margin:0 0 14px}
  #tip{position:fixed;display:none;z-index:10;background:var(--panel2);border:1px solid var(--line);
       border-radius:10px;padding:8px;max-width:262px;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.5)}
  #tip img{width:246px;height:auto;border-radius:6px;display:block;margin-bottom:6px}
  #tip .t{font-size:12px;color:var(--text);line-height:1.35}
  #tip .d{font-size:11px;color:var(--dim);margin-top:2px}
  @media(max-width:800px){.hide-sm{display:none}}
</style>
</head>
<body>
<h1><span class="anchor">&#9875;</span> Boat Search — Price Tracker</h1>
<div class="sub" id="sub"></div>
<div class="cards" id="cards"></div>
<div class="controls">
  <input id="q" placeholder="Search boats, locations...">
  <button class="fbtn on" data-f="all">All</button>
  <button class="fbtn" data-f="new">New</button>
  <button class="fbtn" data-f="drop">Price drops</button>
  <button class="fbtn" data-f="deal">Good deals</button>
  <button class="fbtn" data-f="gone">Gone / sold?</button>
</div>
<div class="charts">
  <div class="chart"><h3>Price vs Year</h3><div id="c1"></div></div>
  <div class="chart"><h3>Price vs Length</h3><div id="c2"></div></div>
  <div class="chart"><h3>Year vs Length &middot; bubble size = price</h3><div id="c3"></div></div>
</div>
<div class="hint">Click any boat row or chart dot to highlight that boat across all charts; click again to clear. Green dots = new boats from the latest scan. Gray dots = gone/sold listings (kept as market history).</div>
<table>
  <thead><tr>
    <th data-k="title">Boat</th>
    <th data-k="year">Year</th>
    <th data-k="length_ft">Length</th>
    <th data-k="price">Price</th>
    <th data-k="ppf" class="hide-sm">$/ft</th>
    <th data-k="value_pct">Value</th>
    <th data-k="change">Change</th>
    <th class="hide-sm">History</th>
    <th data-k="location" class="hide-sm">Location</th>
    <th data-k="first_seen" class="hide-sm">First seen</th>
    <th data-k="status">Status</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
<div id="tip"></div>
<script>
const DATA = __DATA__;
const L = DATA.listings.map(l => {
  const ph = l.price_history;
  l.price = ph[ph.length-1].price;
  l.change = l.price - ph[0].price;
  return l;
});
document.getElementById('sub').textContent =
  (DATA.config.search_name || 'Boat search') + ' • 20–30 ft • up to $' +
  (DATA.config.max_price||60000).toLocaleString() + ' • last updated ' + DATA.updated;

let filter='all', query='', sortK='first_seen', sortDir=-1;
let selectedId=null;

function cards(){
  const act = L.filter(l=>l.status!=='gone');
  const drops = L.filter(l=>l.change<0);
  const deals = act.filter(l=>l.value_pct!=null && l.value_pct<=-15);
  const news = L.filter(l=>l.status==='new');
  const avg = act.length? Math.round(act.reduce((s,l)=>s+l.price,0)/act.length):0;
  document.getElementById('cards').innerHTML =
    card(act.length,'Active listings','blue')+
    card(news.length,'New this scan','green')+
    card(drops.length,'Price drops','green')+
    card(deals.length,'Good deals','green')+
    card('$'+avg.toLocaleString(),'Avg price','');
}
function card(n,t,c){return `<div class="card ${c}"><div class="num">${n}</div><div class="lbl">${t}</div></div>`}

function spark(ph){
  if(ph.length<2) return '<span class="dim">—</span>';
  const w=90,h=22,p=2;
  const vals=ph.map(x=>x.price);
  const mn=Math.min(...vals), mx=Math.max(...vals), rg=(mx-mn)||1;
  const pts=vals.map((v,i)=>
    `${p+i*(w-2*p)/(vals.length-1)},${h-p-(v-mn)*(h-2*p)/rg}`).join(' ');
  const col = vals[vals.length-1]<vals[0] ? 'var(--green)':'var(--red)';
  const tip = ph.map(x=>x.date+': $'+x.price.toLocaleString()).join('\n');
  return `<svg class="spark" width="${w}" height="${h}"><title>${tip}</title>
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2"/></svg>`;
}

function render(){
  cards();
  charts();
  let rows = L.filter(l=>{
    if(filter==='new' && l.status!=='new') return false;
    if(filter==='drop' && l.change>=0) return false;
    if(filter==='deal' && !(l.value_pct!=null && l.value_pct<=-15)) return false;
    if(filter==='gone' && l.status!=='gone') return false;
    if(filter==='all' && l.status==='gone') return false;
    if(query){
      const s=(l.title+' '+l.location+' '+l.source).toLowerCase();
      if(!s.includes(query)) return false;
    }
    return true;
  });
  rows.sort((a,b)=>{
    let x=a[sortK], y=b[sortK];
    if(x==null) return 1; if(y==null) return -1;
    if(typeof x==='string'){x=x.toLowerCase();y=String(y).toLowerCase();}
    return (x<y?-1:x>y?1:0)*sortDir;
  });
  document.getElementById('rows').innerHTML = rows.map(l=>{
    const chg = l.change===0 ? '<span class="chg flat">—</span>'
      : `<span class="chg ${l.change<0?'down':'up'}">${l.change<0?'▼':'▲'} $${Math.abs(l.change).toLocaleString()}</span>`;
    return `<tr class="${l.status==='gone'?'gone':''}${l.id===selectedId?' sel':''}" data-id="${l.id}">
      <td><a href="${l.url}" target="_blank">${esc(l.title)}</a></td>
      <td>${l.year||'<span class="dim">?</span>'}</td>
      <td>${l.length_ft? l.length_ft+'′':'<span class="dim">?</span>'}</td>
      <td class="price">$${l.price.toLocaleString()}</td>
      <td class="hide-sm">${l.ppf?'$'+l.ppf.toLocaleString():'<span class="dim">—</span>'}</td>
      <td>${valBadge(l)}</td>
      <td>${chg}</td>
      <td class="hide-sm">${spark(l.price_history)}</td>
      <td class="hide-sm">${esc(l.location)}</td>
      <td class="dim hide-sm">${l.first_seen}</td>
      <td><span class="badge b-${l.status}">${l.status==='gone'?'gone/sold?':l.status}</span></td>
    </tr>`;
  }).join('') || '<tr><td colspan="11" class="dim" style="text-align:center;padding:30px">No listings match</td></tr>';
}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')}

function valBadge(l){
  if(l.value_pct==null){
    return l.price_pctile!=null
      ? `<span class="dim" title="Not enough info (need year + length) for the fair-value model">P${l.price_pctile}</span>`
      : '<span class="dim">—</span>';
  }
  const tip = `Model expects ~$${l.expected_price.toLocaleString()} for a ${l.year} boat at ${l.length_ft}′.\nFleet price percentile: ${l.price_pctile} (0 = cheapest).`;
  if(l.value_pct<=-10) return `<span class="badge b-drop" title="${tip}">&#9660; ${Math.abs(l.value_pct)}% under</span>`;
  if(l.value_pct>=10)  return `<span class="badge b-rise" title="${tip}">&#9650; ${l.value_pct}% over</span>`;
  return `<span class="badge b-active" title="${tip}">fair</span>`;
}

document.querySelectorAll('.fbtn').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.fbtn').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); filter=b.dataset.f; render();
});
document.getElementById('q').oninput=e=>{query=e.target.value.toLowerCase();render();};
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{
  const k=th.dataset.k;
  sortDir = (sortK===k)? -sortDir : (k==='title'||k==='location'?1:-1);
  sortK=k; render();
});
function fmtP(v){return '$'+(v>=1000? Math.round(v/1000)+'k' : Math.round(v))}
function drawScatter(el,pts,xk,yk,opt){
  opt=opt||{};
  const box=document.getElementById(el);
  if(!pts.length){box.innerHTML='<div class="dim">Not enough data</div>';return}
  const W=320,H=215,m={l:42,r:12,t:10,b:26};
  const xs=pts.map(p=>p[xk]), ys=pts.map(p=>p[yk]);
  let x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  if(x0===x1){x0-=1;x1+=1} if(y0===y1){y0-=1;y1+=1}
  const px=v=>m.l+(v-x0)/(x1-x0)*(W-m.l-m.r);
  const py=v=>H-m.b-(v-y0)/(y1-y0)*(H-m.t-m.b);
  let s='';
  for(let i=0;i<=3;i++){
    const xv=x0+(x1-x0)*i/3, yv=y0+(y1-y0)*i/3;
    s+=`<text class="tick" x="${px(xv)}" y="${H-m.b+12}" text-anchor="middle">${opt.xFmt?opt.xFmt(xv):Math.round(xv)}</text>`;
    s+=`<text class="tick" x="${m.l-5}" y="${py(yv)+3}" text-anchor="end">${opt.yFmt?opt.yFmt(yv):Math.round(yv)}</text>`;
  }
  s+=`<line class="axis" x1="${m.l}" y1="${H-m.b}" x2="${W-m.r}" y2="${H-m.b}"/>`;
  s+=`<line class="axis" x1="${m.l}" y1="${m.t}" x2="${m.l}" y2="${H-m.b}"/>`;
  let rOf=()=>4.5;
  if(opt.sizeKey){
    const ss=pts.map(p=>p[opt.sizeKey]);
    const s0=Math.min(...ss), s1=Math.max(...ss);
    rOf=p=>3+8*Math.sqrt((p[opt.sizeKey]-s0)/((s1-s0)||1));
  }
  const rank=p=>p.id===selectedId?3:(p.status==='new'?2:(p.status==='gone'?0:1));
  const ordered=pts.slice().sort((a,b)=>rank(a)-rank(b));
  for(const p of ordered){
    const sel=p.id===selectedId, gn=p.status==='gone', nw=p.status==='new';
    s+=`<circle class="pt${sel?' sel':(gn?' gn':(nw?' nw':''))}" data-id="${p.id}" cx="${px(p[xk]).toFixed(1)}" cy="${py(p[yk]).toFixed(1)}" r="${(sel?rOf(p)+2:rOf(p)).toFixed(1)}"></circle>`;
  }
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}">${s}</svg>`;
}
function charts(){
  drawScatter('c1',L.filter(l=>l.year),'year','price',{yFmt:fmtP});
  drawScatter('c2',L.filter(l=>l.length_ft),'length_ft','price',{yFmt:fmtP,xFmt:v=>Math.round(v)+"'"});
  drawScatter('c3',L.filter(l=>l.year&&l.length_ft),'year','length_ft',{sizeKey:'price',yFmt:v=>Math.round(v)+"'"});
}
function toggleSel(id){selectedId = selectedId===id? null : id; render();}
document.getElementById('rows').addEventListener('click',e=>{
  if(e.target.closest('a'))return;
  const tr=e.target.closest('tr[data-id]');
  if(tr) toggleSel(tr.dataset.id);
});
document.querySelector('.charts').addEventListener('click',e=>{
  const c=e.target.closest('circle[data-id]');
  if(c) toggleSel(c.dataset.id);
});
const tipEl=document.getElementById('tip');
function moveTip(e){
  const w=tipEl.offsetWidth||262,h=tipEl.offsetHeight||220;
  let x=e.clientX+16,y=e.clientY+12;
  if(x+w>innerWidth-8)x=e.clientX-w-16;
  if(y+h>innerHeight-8)y=Math.max(8,e.clientY-h-12);
  tipEl.style.left=x+'px';tipEl.style.top=y+'px';
}
document.querySelector('.charts').addEventListener('mouseover',e=>{
  const c=e.target.closest('circle[data-id]');
  if(!c){tipEl.style.display='none';return}
  const l=L.find(x=>x.id===c.dataset.id);
  if(!l)return;
  let flags='';
  if(l.status==='gone')flags=' &bull; gone/sold?';
  else if(l.status==='new')flags=' &bull; NEW today';
  tipEl.innerHTML=(l.image?`<img src="${l.image}" alt="">`:'')+
    `<div class="t">${esc(l.title)}</div>`+
    `<div class="d">${l.year||'?'} &bull; ${l.length_ft?l.length_ft+'&prime;':'?'} &bull; $${l.price.toLocaleString()}${flags}${l.image===undefined?' &bull; photo pending':(l.image===null?' &bull; ad has no photo':'')}</div>`;
  tipEl.style.display='block'; moveTip(e);
});
document.querySelector('.charts').addEventListener('mousemove',e=>{
  if(tipEl.style.display==='block')moveTip(e);
});
document.querySelector('.charts').addEventListener('mouseleave',()=>{tipEl.style.display='none'});
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
# v2: year + fair-value analytics
