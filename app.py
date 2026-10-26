"""Pay-per-print server (single file): admin panel, QR upload form, payment check, auto-print.
Run: pip install -r requirements.txt && SECRET_KEY=change-me python app.py
"""
import os, io, re, json, ipaddress, shutil, tempfile, zipfile, math, base64, string, contextlib, hmac, hashlib, secrets, sqlite3, subprocess, sys, threading, time
from functools import wraps
import pyotp, qrcode, requests
from flask import (Flask, request, session, redirect, render_template, flash,
                   send_file, abort, jsonify, g, has_request_context)
from jinja2 import DictLoader
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from decimal import Decimal
from urllib.parse import urlencode, quote
from pypdf import PdfReader, PdfWriter, PageObject, Transformation
from PIL import Image, ImageDraw
from itsdangerous import URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash as H, check_password_hash as C

# ---------- page designs (formerly ui.py) ----------
CS = '<input type=hidden name=csrf value="{{csrf}}">'
PIN = '<input type=hidden name=pin>'
CSS = r"""
:root{--ink:#14213d;--mut:#5b6678;--bg:#eef3fa;--acc:#0e7c86;--acc2:#7c3aed;--card:#ffffffcc;--line:#d6e0ee;--ok:#15803d}
@media(prefers-color-scheme:dark){:root{--ink:#e8eefc;--mut:#a3b3d1;--bg:#0b1020;--card:#141c36cc;--line:#27335a;--ok:#4ade80}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;font:16px/1.55 system-ui,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);overflow-x:hidden}a{color:var(--acc)}
.blob{position:fixed;border-radius:50%;filter:blur(80px);opacity:.3;z-index:-1;animation:drift 20s ease-in-out infinite}.b1{width:440px;height:440px;background:var(--acc);top:-140px;left:-120px}
.b2{width:380px;height:380px;background:var(--acc2);bottom:-120px;right:-90px;animation-delay:-7s}.b3{width:260px;height:260px;background:#f59e0b;top:45%;left:60%;opacity:.16;animation-delay:-12s}
@keyframes drift{50%{transform:translate(50px,36px) scale(1.15)}}
header,main{max-width:800px;margin:0 auto;padding:14px 16px}main{padding-bottom:70px}
.brand{display:inline-flex;align-items:center;gap:10px;font-weight:800;font-size:1.25rem;color:var(--ink);text-decoration:none}
.logo{width:40px;height:40px;overflow:visible}.logo *{transform-box:fill-box;transform-origin:center}.logo .body{fill:var(--acc)}
.logo .paper,.logo .out{fill:#fff;stroke:var(--acc);stroke-width:2;animation:feed 3s ease-in-out infinite}.logo .out{animation-name:eject}.logo .led{fill:#a7f3d0;animation:blink 1.4s infinite}
@keyframes feed{50%{transform:translateY(5px)}}@keyframes eject{50%{transform:translateY(7px)}}@keyframes blink{50%{opacity:.2}}
h1{font-size:clamp(1.7rem,5vw,2.4rem);line-height:1.15;margin:.3em 0 .35em;background:linear-gradient(90deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;color:transparent;animation:rise .7s both}
h2{font-size:1.1rem;margin:0 0 .6em}.lead{color:var(--mut);margin:0 0 18px;animation:rise .7s .1s both}.mut{color:var(--mut)}
.card{background:var(--card);backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:18px;padding:18px;margin:0 0 16px;box-shadow:0 8px 30px #0b10201a;animation:rise .6s both;transition:transform .25s,box-shadow .25s}
.card:hover{transform:translateY(-2px);box-shadow:0 14px 36px #0b102026}
main>:nth-child(3){animation-delay:.08s}main>:nth-child(4){animation-delay:.16s}main>:nth-child(5){animation-delay:.24s}main>:nth-child(n+6){animation-delay:.3s}
@keyframes rise{from{opacity:0;transform:translateY(20px)}}@keyframes slide{from{opacity:0;transform:translateX(-24px)}}@keyframes pop{from{opacity:0;transform:scale(.4)}}
label{display:block;margin:.8em 0 .25em;font-weight:600}
input,select{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:12px;font:inherit;color:inherit;background:#ffffff14;transition:border-color .2s,box-shadow .2s}
input:focus,select:focus{outline:none;border-color:var(--acc);box-shadow:0 0 0 4px #0e7c8633}
button,.btn{position:relative;overflow:hidden;display:inline-block;background:linear-gradient(135deg,var(--acc),var(--acc2));color:#fff;border:0;border-radius:12px;padding:11px 18px;font:inherit;font-weight:700;cursor:pointer;margin-top:14px;text-decoration:none;transition:transform .2s,box-shadow .2s}
button:hover,.btn:hover{transform:translateY(-2px);box-shadow:0 8px 18px #7c3aed44}button:active{transform:scale(.97)}
button::after{content:"";position:absolute;top:0;left:-60%;width:40%;height:100%;background:#fff5;transform:skewX(-20deg);transition:left .5s}button:hover::after{left:130%}.gray{background:#64748b}
.msg{padding:11px 14px;border-radius:12px;margin:8px 0;animation:slide .45s both;font-weight:600}.ok{background:#dcfce7;color:#14532d}.err{background:#fee2e2;color:#7f1d1d}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:middle}th{color:var(--mut);font-size:.85rem}
tbody tr{animation:slide .4s both}.scroll{overflow-x:auto}.fresh{animation:flash 2.5s}@keyframes flash{from{background:#fde68a;transform:scale(1.02)}}
.hp{position:absolute;left:-9999px}
.drop{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center;padding:28px 14px;border:2px dashed var(--acc);border-radius:18px;cursor:pointer;margin:14px 0 0;transition:background .25s,transform .25s;background:linear-gradient(90deg,#0e7c8610,#7c3aed10,#0e7c8610);background-size:200% 100%;animation:shimmer 4s linear infinite}
.drop:hover,.drop.over{background-color:#0e7c8622;transform:scale(1.015)}.drop input{position:absolute;opacity:0;width:1px;height:1px}
.ic{width:46px;height:46px;color:var(--acc);animation:hop 2s ease-in-out infinite}@keyframes hop{50%{transform:translateY(-7px)}}@keyframes shimmer{to{background-position:-200% 0}}
.steps{display:flex;gap:8px;list-style:none;padding:0;flex-wrap:wrap}.steps li{flex:1;min-width:110px;padding:10px;border-radius:12px;background:#0e7c8614;text-align:center;font-weight:600;animation:pop .5s both}
.steps li:nth-child(2){animation-delay:.12s}.steps li:nth-child(3){animation-delay:.24s}.steps li:nth-child(4){animation-delay:.36s}
.opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.opt{position:relative;margin:0;border:2px solid var(--line);border-radius:14px;padding:12px;text-align:center;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;transition:all .25s}
.opt input{position:absolute;opacity:0}.opt:hover{transform:translateY(-2px)}.opt:has(input:checked){border-color:var(--acc);background:#0e7c8618;transform:translateY(-3px) scale(1.03);box-shadow:0 8px 18px #0e7c8628}
.opt:has(input:focus-visible){outline:3px solid var(--acc)}.pg{width:34px;height:46px;border:2px solid var(--acc);border-radius:4px;background:#fff}.pg.ls{width:46px;height:34px}
.cu{max-height:0;overflow:hidden;transition:max-height .4s}.cu.on{max-height:150px}
.prev{width:140px;height:190px;margin:14px auto 0;border:2px solid var(--acc);border-radius:6px;background:#fff;display:grid;gap:4px;padding:6px;transition:all .4s}.prev.ls{width:190px;height:140px}
.prev i{background:linear-gradient(135deg,#c7d2fe,#99f6e4);border-radius:3px;animation:pop .4s both}
.prev.n1{grid-template:1fr/1fr}.prev.n2{grid-template:1fr 1fr/1fr}.prev.n2.ls{grid-template:1fr/1fr 1fr}.prev.n4{grid-template:1fr 1fr/1fr 1fr}.prev.n6{grid-template:repeat(3,1fr)/1fr 1fr}.prev.n6.ls{grid-template:1fr 1fr/repeat(3,1fr)}.prev.n9{grid-template:repeat(3,1fr)/repeat(3,1fr)}
.price{font-size:2.2rem;font-weight:800;color:var(--acc)}.amt{font-weight:800;color:var(--acc);font-size:1.3rem}
.qrbox{text-align:center}.qrwrap{display:inline-block;position:relative;padding:12px;background:#fff;border-radius:18px;animation:ring 2s infinite}.qr{width:240px;max-width:100%;display:block}
.qrwrap::after{content:"";position:absolute;left:12px;right:12px;height:3px;border-radius:3px;background:linear-gradient(90deg,transparent,var(--acc),transparent);animation:scan 2.4s linear infinite}
@keyframes scan{0%{top:12px}100%{top:calc(100% - 15px)}}@keyframes ring{0%{box-shadow:0 0 0 0 #0e7c8666}100%{box-shadow:0 0 0 22px #0e7c8600}}
.stage{text-align:center;padding-top:8px}.check{width:64px;height:64px;display:none;margin:0 auto}.stage.paid .check,.stage.printing .check,.stage.printed .check{display:block}
.check circle{fill:none;stroke:var(--ok);stroke-width:3;stroke-dasharray:151;stroke-dashoffset:151;animation:draw .7s forwards}.check path{fill:none;stroke:var(--ok);stroke-width:4;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:40;stroke-dashoffset:40;animation:draw .5s .6s forwards}
@keyframes draw{to{stroke-dashoffset:0}}.bar{display:none;height:8px;border-radius:8px;background:var(--line);overflow:hidden;margin:10px auto;max-width:260px}.bar i{display:block;height:100%;width:40%;background:linear-gradient(90deg,var(--acc),var(--acc2));animation:run 1.4s ease-in-out infinite}
@keyframes run{0%{transform:translateX(-100%)}100%{transform:translateX(260%)}}.stage.paid .bar,.stage.printing .bar{display:block}
.lock{font-size:2.6rem;animation:bob 2.4s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-8px) rotate(-6deg)}}
.chk{list-style:none;padding:0;margin:10px 0}.chk li{padding:5px 0;color:var(--mut)}.chk li.yes{color:var(--ok);font-weight:600;animation:pop .4s both}progress{width:100%;height:12px;accent-color:var(--acc)}
.help{display:none;margin:12px 0;padding:12px;border-radius:12px;background:#0e7c8612}
.f:has(input[value=usb]:checked) .h-usb,.f:has(input[value=wifi]:checked) .h-wifi,.f:has(input[value=wifidirect]:checked) .h-wifidirect,.f:has(input[value=ethernet]:checked) .h-ethernet{display:block;animation:rise .4s}
.hero{display:flex;gap:22px;align-items:center;flex-wrap:wrap;justify-content:center}.tiles{display:flex;gap:14px;flex-wrap:wrap}.tiles div{padding:12px 18px;border-radius:14px;background:#0e7c8614;animation:pop .6s both}.tiles b{display:block;font-size:1.6rem}
.url{word-break:break-all;font-weight:700}.big{font-size:clamp(4rem,20vw,8rem);font-weight:900;margin:0;line-height:1;background:linear-gradient(90deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;color:transparent;animation:bob 3s infinite}
dialog{border:1px solid var(--line);border-radius:16px;background:var(--bg);color:var(--ink)}dialog::backdrop{backdrop-filter:blur(4px);background:#0006}dialog[open]{animation:rise .3s}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
"""
RAW = {}
def T(name, title, body): RAW[name] = "{% extends 'base.html' %}{% block t %}" + title + "{% endblock %}{% block b %}" + body + "{% endblock %}"
RAW["base.html"] = """<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content="noindex">
<title>{% block t %}{% endblock %} · {{shop}}</title><style nonce="{{nonce}}">""" + CSS + """</style>
<div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>
<header><a class=brand href="/"><svg class=logo viewBox="0 0 48 48" aria-hidden=true><rect class=paper x=14 y=4 width=20 height=16 rx=2 /><rect class=body x=5 y=18 width=38 height=18 rx=6 /><rect class=out x=14 y=30 width=20 height=14 rx=2 /><circle class=led cx=36 cy=26 r=2 /></svg><span>{{shop}}</span></a></header>
<main>{% for c,m in get_flashed_messages(with_categories=true) %}<div class="msg {{c}}" role=status>{{m}}</div>{% endfor %}{% block b %}{% endblock %}</main>
<dialog id=pinbox><form method=dialog><label for=pinin>Enter your security code</label><input id=pinin type=password autocomplete=off><button value=ok>Confirm</button> <button value=cancel class=gray>Cancel</button></form></dialog>
<script nonce="{{nonce}}">document.querySelectorAll('form.sens').forEach(f=>f.addEventListener('submit',e=>{if(f.dataset.ok)return;e.preventDefault();
const d=document.getElementById('pinbox'),i=document.getElementById('pinin');d.onclose=()=>{if(d.returnValue==='ok'){f.querySelector('[name=pin]').value=i.value;f.dataset.ok=1;f.submit()}i.value=''};d.showModal();i.focus()}))</script></html>"""
T("upload.html", "Print", """<h1>Print anything,<br>pay in a tap</h1><p class=lead>Upload a photo, PDF or Word file, choose how it prints, then pay by UPI. Printing starts by itself.</p>
<section class=card><form method=post enctype=multipart/form-data id=uf>@CS<input type=hidden name=tok value="{{tok}}"><div class=hp aria-hidden=true><label>Leave this empty<input name=website tabindex=-1 autocomplete=off></label></div>
<label for=nm>Your name</label><input id=nm name=name maxlength=40 required autocomplete=name placeholder="Shown in the payment history">
<label class=drop id=drop for=f><svg class=ic viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="M12 16V5m0 0l-4 4m4-4l4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
<b id=dt>Drop your file here or tap to choose</b><span class=mut>Photo (PNG, JPG), PDF or Word (DOC, DOCX) · up to 25 MB</span>
<input id=f type=file name=file accept=".pdf,.png,.jpg,.jpeg,.doc,.docx" required></label><button>Continue to print options</button></form></section>
<section class=card><h2>How it works</h2><ol class=steps><li>1 · Upload</li><li>2 · Choose layout</li><li>3 · Pay</li><li>4 · Collect</li></ol><p class=mut>₹{{price}} per printed sheet.</p></section>
<script nonce="{{nonce}}">const d=document.getElementById('drop'),f=document.getElementById('f'),t=document.getElementById('dt');
function show(){if(f.files[0])t.textContent='📄 '+f.files[0].name}f.addEventListener('change',show);
['dragenter','dragover'].forEach(n=>d.addEventListener(n,e=>{e.preventDefault();d.classList.add('over')}));
['dragleave','drop'].forEach(n=>d.addEventListener(n,e=>{e.preventDefault();d.classList.remove('over')}));
d.addEventListener('drop',e=>{f.files=e.dataTransfer.files;show()})</script>""")
T("options.html", "Options", """<h1>Print options</h1><p class=lead><b>{{j.filename}}</b> · {{j.pages}} page(s)</p>
<form method=post id=of>@CS
<section class=card><h2>1 · Layout</h2><div class=opts><label class=opt><input type=radio name=layout value=portrait checked><span class=pg></span><b>Portrait</b></label><label class=opt><input type=radio name=layout value=landscape><span class="pg ls"></span><b>Landscape</b></label></div></section>
<section class=card><h2>2 · Pages</h2><div class=opts><label class=opt><input type=radio name=range value=all checked><b>All pages</b></label><label class=opt><input type=radio name=range value=odd><b>Odd pages only</b></label><label class=opt><input type=radio name=range value=even><b>Even pages only</b></label><label class=opt><input type=radio name=range value=custom><b>Custom</b></label></div>
<div id=cu class=cu><label for=cv>Pages (example: 1-5, 8, 11-13)</label><input id=cv name=custom maxlength=100 placeholder="1-5, 8, 11-13" autocomplete=off></div></section>
<section class=card><h2>3 · Pages per sheet</h2><div class=opts>{% for n in (1,2,4,6,9) %}<label class=opt><input type=radio name=per_sheet value={{n}} {{'checked' if n==1}}><b>{{n}}</b></label>{% endfor %}</div><div class="prev n1" id=pv aria-label="Sheet preview"></div></section>
{% if colour %}<section class=card><h2>4 · Colour</h2><div class=opts><label class=opt><input type=radio name=color value=color checked><b>Colour</b></label><label class=opt><input type=radio name=color value=mono><b>Black &amp; white</b></label></div></section>{% else %}<input type=hidden name=color value=mono>{% endif %}
<section class=card><p>Selected <b id=ns>{{j.pages}}</b> page(s) on <b id=nsh>{{j.pages}}</b> sheet(s)</p><div class=price>₹<span id=pr>0</span></div><button>Continue to payment</button></section></form>
<script nonce="{{nonce}}">const T={{j.pages}},P={{price}},f=document.getElementById('of');
function sel(){const m=f.range.value;let n=[];for(let i=1;i<=T;i++)n.push(i);if(m=='odd')n=n.filter(i=>i%2);if(m=='even')n=n.filter(i=>!(i%2));
if(m=='custom'){const s=new Set();let ok=true;f.custom.value.replace(/\\s/g,'').split(',').forEach(p=>{const r=/^(\\d+)(?:-(\\d+))?$/.exec(p);if(!r){ok=false;return}const a=+r[1],b=+(r[2]||r[1]);if(a<1||b<a||b>T){ok=false;return}for(let i=a;i<=b;i++)s.add(i)});n=ok?[...s]:[]}return n.length}
function upd(){const c=sel(),per=+f.per_sheet.value,sh=Math.ceil(c/per);document.getElementById('ns').textContent=c;document.getElementById('nsh').textContent=sh;document.getElementById('pr').textContent=(sh*P/100).toFixed(2);
document.getElementById('cu').classList.toggle('on',f.range.value=='custom');const pv=document.getElementById('pv');pv.className='prev n'+per+(f.layout.value=='landscape'?' ls':'');pv.innerHTML='<i></i>'.repeat(per)}
f.addEventListener('input',upd);upd()</script>""")
T("pay.html", "Pay", """<h1>Pay &amp; print</h1><section class=card><p><b>{{j.filename}}</b><br>{{j.sel}} page(s) on {{j.sheets}} sheet(s) · <span class=amt>₹{{'%.2f'|format(j.amount/100)}}</span></p>
{% if j.status=='pending' %}<div id=qrbox class=qrbox><div class=qrwrap><img id=qrimg class=qr src="{{ j.qr_url or '/pay/'+j.id+'/qr.png' }}" alt="Payment QR for this file only"></div>
<p>Scan with Google Pay, PhonePe, Paytm or any UPI app and pay exactly ₹{{'%.2f'|format(j.amount/100)}}. Printing starts after payment is confirmed.</p>
{% if j.provider=='upi' %}<p>Reference <b>{{j.id[:6]}}</b>. Show your payment success screen to the operator, who confirms it.</p>{% endif %}
{% if S('pay_mode')=='mock' and admin %}<form method=post action="/mock-pay/{{j.id}}">@CS<button>Test mode: simulate payment</button></form>{% endif %}</div>{% endif %}
<div id=stage class="stage {{j.status}}"><svg class=check viewBox="0 0 52 52" aria-hidden=true><circle cx=26 cy=26 r=24 /><path d="M14 27l8 8 16-17" /></svg><div class=bar><i></i></div><p id=st aria-live=polite>Status: {{j.status}}</p></div></section>
<script nonce="{{nonce}}">const L={pending:'Waiting for payment…',paid:'Paid. Sending to the printer…',printing:'Printing now…',printed:'Done! Please collect your pages 🎉',print_failed:'Paid, but printing failed. Please tell the operator.',expired:'This job expired. Upload the file again.'};
let cur='{{v}}';async function p(){const r=await (await fetch('/status/{{j.id}}?v='+cur)).json();if(r.qr){document.getElementById('qrimg').src=r.qr}if(r.v)cur=r.v;
document.getElementById('st').textContent=L[r.status]||r.status;document.getElementById('stage').className='stage '+r.status;
if(r.status!='pending'){const b=document.getElementById('qrbox');if(b)b.remove()}if(!['printed','print_failed','expired'].includes(r.status))setTimeout(p,3000)}p()</script>""")
T("error.html", "{{code}}", """<section class=card><p class=big>{{code}}</p><h2>{{msg}}</h2><a class=btn href="/">Back to start</a></section>""")
T("setup.html", "Setup", """<div class=lock>🛠️</div><h1>Create the first admin</h1><section class=card><form method=post>@CS<label for=sc>Setup code (printed in the server console)</label><input id=sc name=setup_code autocomplete=off required>
<label for=u>Username</label><input id=u name=username required><label for=p>Password</label><input id=p name=password type=password minlength=10 required><button>Create admin</button></form></section>""")
T("login.html", "Login", """<div class=lock>🔐</div><h1>Admin login</h1><section class=card><form method=post>@CS<label for=u>Username</label><input id=u name=username required autocomplete=username><label for=p>Password</label><input id=p name=password type=password required autocomplete=current-password><button>Log in</button></form></section>""")
T("totp.html", "Verify", """<div class=lock>📲</div><h1>Two-step login</h1><section class=card><form method=post>@CS<label for=c>Code from your authenticator app</label><input id=c name=code inputmode=numeric autocomplete=one-time-code required><button>Verify</button></form></section>""")
T("pin.html", "Security code", """<div class=lock>🗝️</div><h1>Security code</h1><section class=card><p>This PIN or password protects payment settings and account changes. Only you know it.</p><form method=post>@CS
{% if admin.pin_hash %}<label for=o>Current code</label><input id=o name=pin type=password required>{% endif %}<label for=n>New code (6+ characters)</label><input id=n name=new_pin type=password minlength=6 required><button>Save security code</button></form></section>""")
T("live.html", "Live board", """<h1>Live board</h1><p class=lead><a href="{{AP}}">← Settings</a></p>
<section class="card hero"><div class=qrwrap><img class=qr src="{{AP}}/form-qr.png" alt="Scan to print"></div><div><h2>📱 Scan to print</h2><p class=url>{{url}}</p></div></section>
<section class=card><h2>🔒 Setup code</h2><p class=mut>The setup code guards UPI changes, the key vault and this form. Keep it private; only you should know it.</p><form method=post action={{AP}}/live/setup-code class=sens>@CS@PIN<label for=sc2>Current setup code</label><input id=sc2 name=setup_code type=password autocomplete=off required><label for=nsc>New setup code (10+ letters, numbers, - or _)</label><input id=nsc name=new_setup_code type=password minlength=10 required autocomplete=off><button>Change setup code</button></form></section>
<section class=card><h2>Payment history (admin only)</h2><div class=scroll><table><thead><tr><th>Name<th>Amount<th>Date<th>Time<th>Sheets<th>Via</tr></thead><tbody id=rows>{% for r in rows %}<tr data-id="{{r.id}}"><td>{{r.name}}<td>{{r.amount}}<td>{{r.date}}<td>{{r.time}}<td>{{r.sheets}}<td>{{r.via}}</tr>{% endfor %}</tbody></table></div><p class=mut>Updates by itself every few seconds.</p></section>
<script nonce="{{nonce}}">const AP="{{AP}}",seen=new Set([...document.querySelectorAll('#rows tr')].map(r=>r.dataset.id));
async function tick(){try{const r=await (await fetch(AP+'/live/data')).json();const tb=document.getElementById('rows');tb.textContent='';
r.rows.forEach(x=>{const tr=document.createElement('tr');tr.dataset.id=x.id;if(!seen.has(x.id)){tr.className='fresh';seen.add(x.id)}[x.name,x.amount,x.date,x.time,x.sheets,x.via].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td)});tb.appendChild(tr)})}catch(e){}setTimeout(tick,5000)}setTimeout(tick,5000)</script>""")
T("vault.html", "Vault", """<h1>🔑 Key vault</h1><p class=lead><a href="{{AP}}">← Back to admin</a></p>
{% if state=='create' %}<section class=card><h2>Create the vault password</h2><p>Separate from your admin password. It only opens this page.</p><form method=post action={{AP}}/vault/create>@CS<label for=sc>Setup code</label><input id=sc name=setup_code type=password autocomplete=off required>
<label for=v1>Vault password (10+ characters, letters and numbers)</label><input id=v1 name=vpass type=password minlength=10 required><label for=v2>Repeat it</label><input id=v2 name=vpass2 type=password minlength=10 required><button>Create vault</button></form></section>
{% elif state=='locked' %}<section class=card><h2>Unlock the vault</h2><form method=post action={{AP}}/vault/unlock>@CS<label for=vp>Vault password</label><input id=vp name=vpass type=password required><button>Unlock for 5 minutes</button></form></section>
{% else %}<section class=card><h2>Stored keys</h2>{% if items %}<div class=scroll><table><tr><th>Name<th>Value<th></tr>{% for n,m in items %}<tr><td>{{n}}<td>{{m}}<td><form method=post action={{AP}}/vault/set>@CS<input type=hidden name=name value="{{n}}"><input name=value type=password aria-label="New value for {{n}}" placeholder="new value" required><button>Replace</button></form>
<form method=post action={{AP}}/vault/delete>@CS<input type=hidden name=name value="{{n}}"><button class=gray>Remove</button></form></tr>{% endfor %}</table></div>{% else %}<p>No keys yet.</p>{% endif %}
{% if missing %}<p class=mut>Used by the app but not set: {% for n in missing %}{{known[n]}} ({{n}}){{ ', ' if not loop.last }}{% endfor %}</p>{% endif %}</section>
<section class=card><h2>Add a key</h2><form method=post action={{AP}}/vault/set>@CS<label for=an>Name</label><input id=an name=name list=kn required><datalist id=kn>{% for n in known %}<option value="{{n}}">{% endfor %}</datalist><label for=av>Value</label><input id=av name=value type=password autocomplete=off required><button>Save key</button></form></section>
<section class=card><h2>Vault password</h2><form method=post action={{AP}}/vault/password>@CS<label for=cp>Current</label><input id=cp name=cur type=password required><label for=np2>New</label><input id=np2 name=new type=password minlength=10 required><button>Change vault password</button></form>
<form method=post action={{AP}}/vault/lock>@CS<button class=gray>Lock now</button></form></section>{% endif %}""")
T("admin.html", "Admin", """<h1>Admin · {{admin.username}}</h1><p class=lead><a href={{AP}}/vault>🔑 Key vault</a>{% if done %} · <a href={{AP}}/live>📺 Live board</a>{% endif %}</p>
<section class=card><h2>Setup checklist</h2><progress max={{steps|length}} value={{ndone}}></progress><ul class=chk>{% for t,ok,req in steps %}<li class="{{'yes' if ok}}">{{'✓' if ok else '○'}} {{t}}{{'' if req else ' (recommended)'}}</li>{% endfor %}</ul>
{% if done %}<a class=btn href={{AP}}/live>Open the live board →</a>{% else %}<p class=mut>Finish the required steps to unlock the live board (form QR + payment history).</p>{% endif %}</section>
{% if S('pay_mode')=='upi' or waiting %}<section class=card><h2>Waiting for your confirmation</h2>{% if waiting %}<div class=scroll><table><tr><th>Ref<th>Name<th>Pages<th>₹<th></tr>{% for j in waiting %}<tr><td>{{j.id[:6]}}<td>{{j.name}}<td>{{j.sheets}} sheet(s)<td>{{'%.2f'|format(j.amount/100)}}<td><form method=post action={{AP}}/confirm/{{j.id}}>@CS<button>Confirm paid</button></form></tr>{% endfor %}</table></div>{% else %}<p>No payments waiting.</p>{% endif %}
<p><a href={{AP}}>Refresh</a>. Confirm only after you see the same amount arrive in your UPI app.</p></section>{% endif %}
<section class=card><h2>🖨️ Printer connection &amp; settings</h2><form method=post action={{AP}}/printer class=f>@CS
<div class=opts>{% for k,v in conn.items() %}<label class=opt><input type=radio name=conn_type value={{k}} {{'checked' if S('conn_type')==k}}><b>{{v}}</b></label>{% endfor %}</div>
<div class="help h-usb">Plug the printer into this computer with the USB cable and switch it on. Then use “Detect USB printers” below.</div>
<div class="help h-wifi">Connect the printer to the same Wi-Fi as this computer. Find its IP address on the printer's network page, then add it below.</div>
<div class="help h-wifidirect">Switch on Wi-Fi Direct on the printer and join the printer's own Wi-Fi from this computer (it needs a second connection, such as Ethernet, for internet). Then add the printer IP shown on its screen.</div>
<div class="help h-ethernet">Connect the printer to the router with a network cable. Find its IP address on the printer's network page, then add it below.</div>
<label for=pr>Printer</label><select id=pr name=printer><option value="">System default</option>{% for p in printers %}<option {{'selected' if p==S('printer')}}>{{p}}</option>{% endfor %}</select>{% if pstat %}<p class=mut>{{pstat}}</p>{% endif %}
<label for=pa>Paper size</label><select id=pa name=paper>{% for p in paper %}<option {{'selected' if p==S('paper')}}>{{p}}</option>{% endfor %}</select>
{% if not colour_auto %}<label for=pc>Can this printer print in colour? (Windows cannot detect it)</label><select id=pc name=printer_colour><option value=no {{'selected' if S('printer_colour')!='1'}}>No, black &amp; white only</option><option value=yes {{'selected' if S('printer_colour')=='1'}}>Yes, colour too</option></select>{% endif %}
<label for=qu>Quality</label><select id=qu name=quality>{% for x in ('draft','normal','high') %}<option {{'selected' if S('quality')==x}}>{{x}}</option>{% endfor %}</select>
<label for=si>Sides</label><select id=si name=sides><option value=one {{'selected' if S('sides')=='one'}}>One-sided</option><option value=two {{'selected' if S('sides')=='two'}}>Double-sided</option></select>
<label for=mp>Max pages per file</label><input id=mp name=max_pages type=number min=1 max=500 value="{{S('max_pages')}}">
<label for=pu>Public website address (shown in the QR)</label><input id=pu name=public_url value="{{S('public_url')}}" placeholder="https://print.example.com"><button>Save printer settings</button></form>
<form method=post action={{AP}}/printer/test>@CS<button class=gray>Print a test page</button></form></section>
<section class=card><h2>➕ Add a printer</h2><p>Wi-Fi, Wi-Fi Direct and Ethernet printers: enter the printer's IP address.</p><form method=post action={{AP}}/printer/add class=sens>@CS@PIN
<label for=pn>Queue name</label><input id=pn name=name required pattern="[A-Za-z0-9_-]{2,30}" placeholder=ShopPrinter><label for=ph>Printer IP address (like 192.168.1.50)</label><input id=ph name=host required>
<label for=pt>Connection</label><select id=pt name=conn_type><option value=wifi>Wi-Fi / wireless</option><option value=wifidirect>Wi-Fi Direct</option><option value=ethernet>Ethernet</option></select><button>Add network printer</button></form>
<p><a href="{{AP}}?detect=1">🔌 Detect USB printers</a></p>{% if usb is not none %}{% if usb %}{% for u in usb %}<form method=post action={{AP}}/printer/add class=sens>@CS@PIN<input type=hidden name=uri value="{{u}}"><input name=name aria-label="Queue name" required pattern="[A-Za-z0-9_-]{2,30}" placeholder="queue name"><button>Add {{u}}</button></form>{% endfor %}{% else %}<p>No USB printer found. Check the cable, the power, and that CUPS is installed.</p>{% endif %}{% endif %}</section>
<section class=card><h2>Form QR code</h2><div class=qrbox><div class=qrwrap><img class=qr src={{AP}}/form-qr.png alt="QR code that opens the upload form"></div></div></section>
<section class=card><h2>UPI ID for the payment QR</h2><p>Current: <b>{{S('upi_id') or 'not set'}}</b> {{S('upi_name')}}</p><form method=post action={{AP}}/upi class=sens>@CS@PIN
<label for=ui>New UPI ID</label><input id=ui name=upi_id placeholder=shop@bank required><label for=un>Payee name shown in the app</label><input id=un name=upi_name required><label for=us>Setup code</label><input id=us name=setup_code type=password autocomplete=off required><button>Change UPI ID</button></form>
<p class=mut>Needs your security code and the setup code kept on the server in <code>.setup_code</code>.</p></section>
<section class=card><h2>Payment settings</h2><form method=post action={{AP}}/payment class=sens>@CS@PIN<label for=pp>Price per printed sheet (₹)</label><input id=pp name=price type=number step=0.01 min=0.01 value="{{S('price_paise')|int/100}}">
<label for=m>Mode</label><select id=m name=mode>{% if not prod %}<option value=mock {{'selected' if S('pay_mode')=='mock'}}>Test (no real payment)</option>{% endif %}<option value=razorpay {{'selected' if S('pay_mode')=='razorpay'}}>Razorpay UPI QR</option><option value=paytm {{'selected' if S('pay_mode')=='paytm'}}>Paytm Dynamic QR</option><option value=upi {{'selected' if S('pay_mode')=='upi'}}>Direct UPI ID (you confirm each payment)</option></select>
<p>API keys are kept in the <a href={{AP}}/vault>Key vault</a>.</p><button>Save payment settings</button></form></section>
<section class=card><h2>Your account</h2><form method=post action={{AP}}/account class=sens>@CS@PIN<label for=nu>New username</label><input id=nu name=username value="{{admin.username}}"><label for=np>New password (blank keeps current)</label><input id=np name=password type=password minlength=10><button>Save account changes</button></form><p><a href={{AP}}/pin>Change security code</a></p></section>
<section class=card><h2>Two-step login</h2>{% if admin.totp_on %}<form method=post action={{AP}}/2fa/off class=sens>@CS@PIN<button>Turn off</button></form>
{% elif pending2fa %}<img class=qr src={{AP}}/2fa.png alt="Authenticator QR"><form method=post action={{AP}}/2fa/confirm>@CS<label for=tc>Enter the 6-digit code</label><input id=tc name=code required><button>Turn on</button></form>
{% else %}<form method=post action={{AP}}/2fa/start>@CS<button>Set up two-step login</button></form>{% endif %}</section>
<section class=card><h2>Admins</h2><table>{% for a in admins %}<tr><td>{{a.username}}</td></tr>{% endfor %}</table><form method=post action={{AP}}/admins class=sens>@CS@PIN<label for=au>New admin username</label><input id=au name=username required><label for=ap>Temporary password</label><input id=ap name=password type=password minlength=10 required><button>Add admin</button></form></section>
<section class=card><h2>Recent jobs</h2><div class=scroll><table><tr><th>Name<th>Sheets<th>₹<th>Status<th></tr>{% for j in jobs %}<tr><td>{{j.name}}<td>{{j.sheets}}<td>{{'%.2f'|format(j.amount/100)}}<td>{{j.status}}<td>{% if j.status=='print_failed' and j.path %}<form method=post action={{AP}}/retry/{{j.id}}>@CS<button>Retry</button></form>{% endif %}</tr>{% endfor %}</table></div></section>
<section class=card><h2>Security log</h2><div class=scroll><table><tr><th>Time<th>Who<th>IP<th>Event</tr>{% for t,w,i,e in audit %}<tr><td>{{t}}<td>{{w}}<td>{{i}}<td>{{e}}</tr>{% endfor %}</table></div></section>
<form method=post action={{AP}}/logout>@CS<button class=gray>Log out</button></form>""")
TEMPLATES = {k: v.replace("@CS", CS).replace("@PIN", PIN) for k, v in RAW.items()}

BASE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.join(BASE, "uploads"); os.makedirs(UP, exist_ok=True)
SECRET = os.path.join(BASE, ".secret"); os.makedirs(SECRET, mode=0o700, exist_ok=True)  # payment records and settings: owner-only folder, read by admin pages only
DB = os.path.join(SECRET, "print.db")
for _ext in ("", "-wal", "-shm"):  # move a database from the old location, if there is one
    _old = os.path.join(BASE, "print.db" + _ext)
    if os.path.exists(_old) and not os.path.exists(DB + _ext): shutil.move(_old, DB + _ext)
app = Flask(__name__, static_folder=None)  # no static file route at all
def keyfile(name, make):  # secrets live in owner-only files, never in the code
    p = os.path.join(BASE, name)
    if not os.path.exists(p):
        with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT, 0o600), "w") as f: f.write(make())
    return open(p).read().strip()
app.secret_key = os.environ.get("SECRET_KEY") or keyfile(".secret_key", lambda: secrets.token_hex(32))
FER = Fernet(keyfile(".enc_key", lambda: Fernet.generate_key().decode()).encode())
_env_ap = os.environ.get("ADMIN_PATH", "").strip()
if _env_ap:  # a chosen address is also written to .admin_path, so `cat .admin_path` and backups always have it
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", _env_ap): sys.exit("ADMIN_PATH must be 8-64 letters, numbers, - or _.")
    with os.fdopen(os.open(os.path.join(BASE, ".admin_path"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f: f.write(_env_ap)
    _ap = _env_ap
else:
    _ap = keyfile(".admin_path", lambda: secrets.token_urlsafe(12))
if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", _ap): sys.exit("The saved .admin_path is invalid. Delete it to get a new random address.")
AP = "/" + _ap  # the admin panel lives here; /admin does not exist
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("HTTPS") == "1", SESSION_COOKIE_NAME="__Host-session" if os.environ.get("HTTPS") == "1" else "session", PERMANENT_SESSION_LIFETIME=900)  # 15 min idle logout
if os.environ.get("PROXY") == "1":  # only set behind your own reverse proxy (nginx, Caddy, Cloudflare tunnel)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
SETUP_TOKEN = os.environ.get("SETUP_TOKEN") or keyfile(".setup_code", lambda: secrets.token_urlsafe(9))  # owner code: first setup, UPI ID change, vault creation
DUMMY = H("dummy-password-for-timing")
SHOP = os.environ.get("SHOP_NAME", "Print Hub")
PRODUCTION = os.environ.get("PRODUCTION") == "1"  # real internet use: no test mode, HTTPS required
if PRODUCTION and os.environ.get("HTTPS") != "1": sys.exit("PRODUCTION=1 needs HTTPS=1: serve only over HTTPS.")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
SIGS = {b"%PDF": "pdf", b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"PK\x03\x04": "docx", b"\xd0\xcf\x11\xe0": "doc"}  # photos, PDF, Word
DEFAULTS = {"printer": "", "price_paise": "200", "pay_mode": "mock", "public_url": "",
            "rzp_key": "", "rzp_secret": "", "rzp_webhook": "", "max_pages": "100",
            "paytm_mid": "", "paytm_key": "", "paytm_host": "https://secure.paytmpayments.com", "upi_id": "", "upi_name": "", "conn_type": "", "printer_ip": "", "paper": "A4", "color": "color",
            "quality": "normal", "sides": "one", "printer_cfg": "", "pay_saved": "", "printer_colour": ""}
pin_fails = {}  # admin id -> (count, locked_until)

# ---------- database ----------
def db():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row; c.execute("pragma journal_mode=wal"); return c
def q(sql, a=(), one=False, write=False):
    c = db()
    try:  # always close, even on errors, so a failed write can never leave the database locked
        cur = c.execute(sql, a); r = cur.fetchone() if one else cur.fetchall()
        if write: c.commit()
        n = cur.rowcount
    finally: c.close()
    return n if write else r
with contextlib.closing(db()) as c:
    c.executescript("""create table if not exists admins(id integer primary key, username text unique,
      pw_hash text, pin_hash text, totp_secret text, totp_on int default 0);
      create table if not exists settings(k text primary key, v text);
      create table if not exists jobs(id text primary key, filename text, path text, pages int,
      amount int, status text, created real, qr_url text);
      create table if not exists audit(ts real, who text, ip text, ev text);
      create table if not exists payments(pid text primary key);""")
try:
    with contextlib.closing(db()) as c: c.execute("alter table admins add column sv int default 0")
except sqlite3.OperationalError: pass
try:
    with contextlib.closing(db()) as c: c.execute("alter table jobs add column provider text default 'razorpay'")
except sqlite3.OperationalError: pass
for col in ("refs text default ''", "qr_at real default 0", "payee text default ''", "name text default ''", "paid_at real default 0", "opts text default ''", "sel int default 0", "sheets int default 0"):
    try:
        with contextlib.closing(db()) as c: c.execute("alter table jobs add column " + col)
    except sqlite3.OperationalError: pass
# ---------- key vault: API keys in a hidden, encrypted folder, edited from the admin panel ----------
VAULT = os.path.join(BASE, ".vault"); os.makedirs(VAULT, mode=0o700, exist_ok=True); os.chmod(VAULT, 0o700)
VFILE = os.path.join(VAULT, "keys.enc"); VAUTH = os.path.join(VAULT, "auth")
KNOWN = {"rzp_key": "Razorpay key id", "rzp_secret": "Razorpay key secret", "rzp_webhook": "Razorpay webhook secret",
         "paytm_mid": "Paytm MID", "paytm_key": "Paytm merchant key", "paytm_host": "Paytm API host"}
PT_HOST_RE = r"https://[a-z0-9.-]+\.(paytmpayments\.(com|in)|paytm\.in)"
vlock = threading.Lock(); _vc = {"m": 0, "d": {}}
def write_private(path, data, binary=False):
    tmp = path + ".tmp"
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb" if binary else "w") as f: f.write(data)
    os.replace(tmp, path)
def vload():
    try: m = os.path.getmtime(VFILE)
    except OSError: return {}
    if m != _vc["m"]:
        try: _vc.update(m=m, d=json.loads(FER.decrypt(open(VFILE, "rb").read())))
        except Exception: _vc.update(m=m, d={})
    return _vc["d"]
def vget(k): return vload().get(k, "")
def vsave(d):
    with vlock: write_private(VFILE, FER.encrypt(json.dumps(d).encode()), True); _vc["m"] = 0
ENC = ("rzp_key", "rzp_secret", "rzp_webhook", "paytm_key")  # payment secrets are encrypted in the database
def S(k):
    if k in KNOWN and vget(k): return vget(k)  # API keys live in the vault
    if PRODUCTION and k == "pay_mode":  # test mode is disabled online
        r = q("select v from settings where k='pay_mode'", one=True)
        return r["v"] if r and r["v"] in ("razorpay", "paytm", "upi") else "razorpay"
    r = q("select v from settings where k=?", (k,), one=True)
    if not r: return DEFAULTS[k]
    if k in ENC and r["v"]:
        try: return FER.decrypt(r["v"].encode()).decode()
        except Exception: return ""
    return r["v"]
def setS(k, v):
    q("insert or replace into settings values(?,?)", (k, FER.encrypt(v.encode()).decode() if k in ENC and v else v), write=True)

# ---------- printing ----------
PAPER = {"A4": (595, 842), "A3": (842, 1191), "A5": (420, 595), "Letter": (612, 792), "Legal": (612, 1008)}
CONN = {"usb": "USB connection (wired setup)", "wifi": "Wi-Fi / wireless connection", "wifidirect": "Wi-Fi Direct", "ethernet": "Ethernet (wired network) connection"}
WIN = sys.platform.startswith("win")
def sh(cmd, t=15):
    try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=t); return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e: return False, str(e)
def printers():
    ok, out = sh(["powershell", "-NoProfile", "-Command", "(Get-Printer).Name"]) if WIN else sh(["lpstat", "-e"])
    return (out.splitlines() if WIN else out.split()) if ok else []
def printer_can_colour():  # asks CUPS what the chosen printer can do; Windows cannot be asked, so the admin's yes/no setting is used
    if not WIN:
        ok, out = sh(["lpoptions"] + (["-p", S("printer")] if S("printer") else []) + ["-l"])
        line = next((l for l in out.splitlines() if l.startswith("ColorModel")), "") if ok else ""
        if line:
            tokens = set(line.split(":", 1)[-1].replace("*", " ").split())
            return bool(tokens & {"RGB", "RGBA", "RGB16", "CMYK", "Color", "Colour"})
    return S("printer_colour") == "1"
def usb_found():
    ok, out = sh(["lpinfo", "-v"])
    return [l.split()[1] for l in out.splitlines() if len(l.split()) > 1 and l.split()[1].startswith("usb://")] if ok else []
def parse_pages(mode, custom, total):
    nums = list(range(1, total + 1))
    if mode == "odd": nums = nums[0::2]
    elif mode == "even": nums = nums[1::2]
    elif mode == "custom":
        out = set()
        for part in custom.replace(" ", "").split(","):
            m = re.fullmatch(r"(\d{1,4})(?:-(\d{1,4}))?", part)
            if not m: raise ValueError("bad range")
            a, b = int(m[1]), int(m[2] or m[1])
            if a < 1 or b < a or b > total: raise ValueError("out of range")
            out.update(range(a, b + 1))
        nums = sorted(out)
    if not nums: raise ValueError("no pages")
    return nums
def build_print_pdf(src, out, pages, landscape, per_sheet, paper):  # picks pages, lays them out n-up, sets orientation
    pw, ph = PAPER.get(paper, PAPER["A4"]); W, H = (ph, pw) if landscape else (pw, ph)
    cols, rows = {1: (1, 1), 2: (2, 1) if landscape else (1, 2), 4: (2, 2), 6: (3, 2) if landscape else (2, 3), 9: (3, 3)}[per_sheet]
    rd = PdfReader(src); w = PdfWriter()
    for i in range(0, len(pages), per_sheet):
        sheet = PageObject.create_blank_page(width=W, height=H)
        for k, n in enumerate(pages[i:i + per_sheet]):
            p = rd.pages[n - 1]
            try: p.transfer_rotation_to_content()
            except Exception: pass
            sw, shh = float(p.mediabox.width), float(p.mediabox.height); cw, ch = W / cols, H / rows
            sc = min(cw / sw, ch / shh) * 0.97; c, r = k % cols, k // cols
            tx = c * cw + (cw - sw * sc) / 2 - float(p.mediabox.left) * sc
            ty = H - (r + 1) * ch + (ch - shh * sc) / 2 - float(p.mediabox.bottom) * sc
            sheet.merge_transformed_page(p, Transformation().scale(sc, sc).translate(tx, ty))
        w.add_page(sheet)
    with open(out, "wb") as fh: w.write(fh)
def to_pdf_image(src, out):  # photos are re-encoded onto a clean A4 page: strips metadata and hidden payloads
    Image.MAX_IMAGE_PIXELS = 40_000_000
    with Image.open(src) as im: im.verify()
    with Image.open(src) as im:
        im = im.convert("RGB"); W, H = 1654, 2339
        if im.width > im.height: W, H = H, W
        im.thumbnail((W, H)); canvas = Image.new("RGB", (W, H), "white")
        canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2)); canvas.save(out, "PDF", resolution=200)
def doc_ok(path, kind):  # no macros, no zip bombs
    if kind == "docx":
        with zipfile.ZipFile(path) as z:
            n = z.namelist()
            if "word/document.xml" not in n or any("vbaproject" in x.lower() for x in n) or len(n) > 2000 or sum(i.file_size for i in z.infolist()) > 150 * 2**20:
                raise ValueError("unsafe Word file")
    else:
        raw = open(path, "rb").read()
        if any(x in raw for x in (b"VBA", "VBA".encode("utf-16le"), "Macros".encode("utf-16le"))): raise ValueError("macros")
def _limits():
    import resource; resource.setrlimit(resource.RLIMIT_CPU, (60, 60)); resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 2**20,) * 2)
convsem = threading.Semaphore(2)  # at most 2 Word conversions at once
def doc_to_pdf(src, out):  # LibreOffice in an empty environment, own profile folder, time and size limits
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe or os.environ.get("ALLOW_DOC") == "0": raise RuntimeError("Word files are not enabled on this server")
    if not convsem.acquire(timeout=10): raise RuntimeError("busy, try again")
    tmp = tempfile.mkdtemp(dir=UP)
    try:
        subprocess.run([exe, f"-env:UserInstallation=file://{tmp}/profile", "--headless", "--norestore", "--convert-to", "pdf", "--outdir", tmp, src],
                       env={"PATH": os.environ.get("PATH", ""), "HOME": tmp, "LANG": "C.UTF-8"}, capture_output=True, timeout=60, check=True,
                       **({"preexec_fn": _limits} if os.name == "posix" else {}))
        shutil.move(os.path.join(tmp, os.path.splitext(os.path.basename(src))[0] + ".pdf"), out)
    finally: convsem.release(); shutil.rmtree(tmp, ignore_errors=True)
def add_printer(name, uri): return sh(["lpadmin", "-p", name, "-E", "-v", uri, "-m", "everywhere"], 60)
def print_file(path, color="mono"):
    if WIN: os.startfile(path, "print"); return  # Windows: default printer only
    cmd = ["lp"] + (["-d", S("printer")] if S("printer") else []) + ["-o", "media=" + S("paper"), "-o", "sides=" + ("two-sided-long-edge" if S("sides") == "two" else "one-sided"),
           "-o", "print-color-mode=" + ("color" if color == "color" else "monochrome"), "-o", "print-quality=" + {"draft": "3", "normal": "4", "high": "5"}[S("quality")], path]
    subprocess.run(cmd, check=True, timeout=60)
def run_print(jid):
    j = q("select * from jobs where id=?", (jid,), one=True)
    q("update jobs set status='printing' where id=?", (jid,), write=True)
    try:
        if not j["path"] or not os.path.exists(j["path"]): raise FileNotFoundError("file already removed")
        o = json.loads(j["opts"] or "{}"); out = j["path"][:-4] + "-print.pdf"
        build_print_pdf(j["path"], out, o.get("pages") or list(range(1, j["pages"] + 1)), o.get("landscape", False), o.get("per_sheet", 1), S("paper"))
        print_file(out, o.get("color", "mono")); st = "printed"
    except Exception as e: print("print failed:", e); st = "print_failed"; log(f"print failed job={jid}", "system")
    q("update jobs set status=? where id=?", (st, jid), write=True)

def mark_paid(jid, paid, pid=None):
    j = q("select * from jobs where id=?", (jid,), one=True)
    if not j or int(paid) != j["amount"]:  # amount must match exactly
        log(f"payment rejected job={jid} paid={paid}", "system"); return False
    if pid:
        try: q("insert into payments values(?)", (pid,), write=True)
        except sqlite3.IntegrityError: return True  # same payment sent twice: ignore
    if q("update jobs set status='paid', paid_at=? where id=? and status='pending'", (time.time(), jid), write=True):
        log(f"payment accepted job={jid}", "system")
        threading.Thread(target=run_print, args=(jid,), daemon=True).start()
    elif j["status"] == "expired": log(f"PAID AFTER EXPIRY job={jid}: refund needed", "system")
    return True
def rzp_qr(jid, amount):  # one single-use, fixed-amount QR per job
    r = requests.post("https://api.razorpay.com/v1/payments/qr_codes", auth=(S("rzp_key"), S("rzp_secret")),
        json={"type": "upi_qr", "name": "Print " + jid[:6], "usage": "single_use", "fixed_amount": True,
              "payment_amount": amount, "description": "Print job", "notes": {"job_id": jid}}, timeout=15)
    r.raise_for_status(); return r.json()["image_url"]

# ---------- Paytm: dynamic UPI QR, payment confirmed by asking Paytm directly ----------
PT_IV = b"@@@@&&&&####$$$$"
def pt_sign(text, key):  # Paytm checksum: AES-128-CBC over sha256(text|salt)+salt
    salt = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(4))
    pad = padding.PKCS7(128).padder()
    data = pad.update((hashlib.sha256(f"{text}|{salt}".encode()).hexdigest() + salt).encode()) + pad.finalize()
    e = Cipher(algorithms.AES(key.encode()), modes.CBC(PT_IV)).encryptor()
    return base64.b64encode(e.update(data) + e.finalize()).decode()
def pt_verify(text, sig, key):
    try:
        d = Cipher(algorithms.AES(key.encode()), modes.CBC(PT_IV)).decryptor()
        raw = d.update(base64.b64decode(sig)) + d.finalize()
        u = padding.PKCS7(128).unpadder(); h = (u.update(raw) + u.finalize()).decode()
    except Exception: return False
    return hmac.compare_digest(hashlib.sha256(f"{text}|{h[-4:]}".encode()).hexdigest(), h[:-4])
def pt_call(path, body):
    b = json.dumps(body)
    payload = json.dumps({"body": body, "head": {"signature": pt_sign(b, S("paytm_key"))}})
    r = requests.post(S("paytm_host").rstrip("/") + path, data=payload, headers={"Content-Type": "application/json"}, timeout=15)
    r.raise_for_status(); return r.json()["body"]
def paytm_qr(jid, amount):
    d = pt_call("/paymentservices/qr/create", {"mid": S("paytm_mid"), "orderId": jid, "amount": f"{amount / 100:.2f}",
                "businessType": "UPI_QR_CODE", "posId": "PRINT01", "displayName": "Print"})
    if d["resultInfo"]["resultStatus"] != "SUCCESS": raise RuntimeError(d["resultInfo"]["resultMsg"])
    b = io.BytesIO(); qrcode.make(d["qrData"]).save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
last_check = {}
def paytm_check(jid):  # never trust a browser or webhook: ask Paytm, then compare the exact amount
    if time.time() - last_check.get(jid, 0) < 4: return
    if len(last_check) > 5000: last_check.clear()
    last_check[jid] = time.time()
    j = q("select * from jobs where id=?", (jid,), one=True)
    try:
        for ref in refs_of(j)[-3:]:  # the customer may have paid a QR that was replaced a moment ago
            b = pt_call("/v3/order/status", {"mid": S("paytm_mid"), "orderId": ref})
            if b["resultInfo"]["resultStatus"] == "TXN_SUCCESS" and b.get("orderId") == ref:
                mark_paid(jid, int((Decimal(b["txnAmount"]) * 100).to_integral_value()), "paytm:" + b["txnId"]); break
    except Exception as e: print("paytm check failed:", e)

# ---------- QR codes: direct UPI, and automatic replacement of expired QR codes ----------
QR_TTL = int(os.environ.get("QR_TTL", "540"))  # Paytm QR codes last about 10 minutes; ours are replaced at 9
def qr_data_uri(text):
    b = io.BytesIO(); qrcode.make(text).save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def upi_qr(jid, amount, payee):
    if not payee: raise RuntimeError("UPI ID is not set")
    qs = urlencode({"pa": payee, "pn": S("upi_name") or "Print", "am": f"{amount / 100:.2f}", "cu": "INR",
                    "tn": "Print " + jid[:6], "tr": jid}, quote_via=lambda s, safe="", encoding=None, errors=None: quote(s, safe="@"))
    return qr_data_uri("upi://pay?" + qs)
def qr_version(j): return hashlib.sha1((j["qr_url"] or "").encode()).hexdigest()[:10]
def refs_of(j): return [r for r in (j["refs"] or "").split(",") if r] or [j["id"]]
def refresh_qr(jid):  # a fresh QR appears by itself when the old one expired or the UPI ID changed
    j = q("select * from jobs where id=?", (jid,), one=True)
    if not j or j["status"] != "pending": return
    try:
        if j["provider"] == "paytm" and time.time() - (j["qr_at"] or j["created"]) > QR_TTL:
            refs = refs_of(j)
            if len(refs) >= 7: return  # about an hour of renewals, then the job expires
            ref = f"{jid}-{len(refs)}"; qr = paytm_qr(ref, j["amount"])  # Paytm needs a new order id per QR
            q("update jobs set qr_url=?, qr_at=?, refs=? where id=? and status='pending'", (qr, time.time(), ",".join(refs + [ref]), jid), write=True)
        elif j["provider"] == "upi" and S("upi_id") and j["payee"] != S("upi_id"):
            q("update jobs set qr_url=?, qr_at=?, payee=? where id=? and status='pending'", (upi_qr(jid, j["amount"], S("upi_id")), time.time(), S("upi_id"), jid), write=True)
    except Exception as e: print("QR refresh failed:", e)

# ---------- helpers ----------
def png(data):
    b = io.BytesIO(); qrcode.make(data).save(b, "PNG"); b.seek(0)
    return send_file(b, mimetype="image/png")
def me():
    a = q("select * from admins where id=?", (session.get("aid"),), one=True)
    if a and session.get("sv") != a["sv"]: session.clear(); return None  # password/code changed elsewhere
    return a
def bump(a):  # log out this admin's other sessions
    q("update admins set sv=sv+1 where id=?", (a["id"],), write=True)
    if session.get("aid") == a["id"]: session["sv"] = a["sv"] + 1
def log(ev, who=None):
    ip = request.remote_addr if has_request_context() else "-"
    q("insert into audit values(?,?,?,?)", (time.time(), who or (me() or {"username": "-"})["username"], ip, ev), write=True)
fails = {}
used = {}
def tsec(a):
    try: return FER.decrypt(a["totp_secret"].encode()).decode()
    except Exception: return a["totp_secret"]  # secret saved before encryption existed
def totp_ok(a, code):
    code = code.strip(); k = (a["id"], code)
    if time.time() - used.get(k, 0) < 120: return False  # each code works once
    if not pyotp.TOTP(tsec(a)).verify(code, valid_window=1): return False
    if len(used) > 1000: used.clear()
    used[k] = time.time(); return True
def locked(k): return time.time() < fails.get(k, (0, 0))[1]
def fail(k, limit=5, secs=600):
    if len(fails) > 10000: fails.clear()  # cap memory
    n = fails.get(k, (0, 0))[0] + 1; fails[k] = (n, time.time() + secs if n >= limit else 0)
WEAK = "Use a password with 10+ characters that mixes letters and numbers."
def weak(p): return len(p) < 10 or p.isalpha() or p.isdigit() or p.lower() in ("password123", "1234567890", "qwertyuiop")
def admin(f):
    @wraps(f)
    def w(*a, **k):
        if not me(): return redirect(AP + "/login")
        if not me()["pin_hash"] and request.path != AP + "/pin": return redirect(AP + "/pin")
        return f(*a, **k)
    return w
def pin_ok(a):
    n, until = pin_fails.get(a["id"], (0, 0))
    if time.time() < until: return False
    if a["pin_hash"] and C(a["pin_hash"], request.form.get("pin", "")):
        pin_fails.pop(a["id"], None); return True
    n += 1; pin_fails[a["id"]] = (n, time.time() + 300 if n >= 5 else 0); log("wrong security code", a["username"])
    flash("Wrong security code." if n < 5 else "Too many wrong codes. Try again in 5 minutes.", "err")
    return False
@app.context_processor
def ctx():
    a = me(); session.setdefault("csrf", secrets.token_hex(16))
    return {"csrf": session["csrf"], "S": S, "admin": a, "nonce": getattr(g, "nonce", ""), "prod": PRODUCTION, "AP": AP, "shop": SHOP}
ALLOW = [ipaddress.ip_network(x.strip(), strict=False) for x in os.environ.get("ADMIN_ALLOW", "").split(",") if x.strip()]
HOSTS = [h.strip().lower() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
RL = {}
@app.before_request
def admin_allowlist():  # ADMIN_ALLOW=1.2.3.4,192.168.1.0/24 limits who can even see the admin address
    if ALLOW and (request.path == AP or request.path.startswith(AP + "/")):
        try: ok = any(ipaddress.ip_address(request.remote_addr) in n for n in ALLOW)
        except ValueError: ok = False
        if not ok: abort(404)
@app.before_request
def guard():  # per-IP request limits, and only our own domain names are served
    if HOSTS and request.host.split(":")[0].lower() not in HOSTS: abort(400)
    if request.path.startswith("/webhook/"): return
    ip = request.remote_addr or "?"; now = time.time(); hits = [t for t in RL.get(ip, []) if now - t < 60] + [now]
    if len(RL) > 20000: RL.clear()
    RL[ip] = hits
    if len(hits) > 600: abort(429)
@app.before_request
def csrf_check():  # every form carries a one-time token tied to the visitor's session
    if request.method == "POST" and not request.path.startswith("/webhook/") and request.form.get("csrf") != session.get("csrf"): abort(400)
@app.before_request
def make_nonce(): g.nonce = secrets.token_urlsafe(16)
@app.after_request
def secure_headers(r):
    n = getattr(g, "nonce", "")
    r.headers["Content-Security-Policy"] = (f"default-src 'self'; img-src 'self' data: https:; style-src 'nonce-{n}'; "
        f"script-src 'nonce-{n}'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
    r.headers.update({"X-Content-Type-Options": "nosniff", "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Resource-Policy": "same-origin", "X-Robots-Tag": "noindex, nofollow", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                      "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
    if request.path.startswith((AP, AP + "/setup")): r.headers["Cache-Control"] = "no-store"
    if os.environ.get("HTTPS") == "1": r.headers["Strict-Transport-Security"] = "max-age=31536000"
    return r
def cleanup():  # delete files: unpaid after 1h, printed after 10 min, failed after 24h
    while True:
        now = time.time()
        for j in q("select id,path,status,created from jobs where path!=''"):
            age = now - j["created"]
            if (j["status"] in ("pending", "draft") and age > 3600) or (j["status"] == "printed" and age > 600) or (j["status"] == "print_failed" and age > 86400):
                for p in (j["path"], j["path"][:-4] + "-print.pdf"):
                    try: os.remove(p)
                    except OSError: pass
                q("update jobs set path='', status=? where id=?", ("expired" if j["status"] in ("pending", "draft") else j["status"], j["id"]), write=True)
        time.sleep(300)

# ---------- public: upload form + payment ----------
uploads = {}
EXT = {"pdf": ("pdf",), "png": ("png",), "jpg": ("jpg", "jpeg"), "docx": ("docx",), "doc": ("doc",)}
TS = URLSafeTimedSerializer(app.secret_key, salt="upload-form")
@app.route("/", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        now = time.time(); ts = [t for t in uploads.get(request.remote_addr, []) if now - t < 600]
        if len(ts) >= 30: flash("Too many uploads. Wait a few minutes and try again.", "err"); return redirect("/")
        if len(uploads) > 10000: uploads.clear()
        uploads[request.remote_addr] = ts + [now]
        try: born = TS.loads(request.form.get("tok", ""), max_age=3600, return_timestamp=True)[1].timestamp()
        except Exception: born = None
        if request.form.get("website") or born is None or now - born < 2:  # honeypot field, signed form token, no instant bots
            flash("Please reload the page and try again.", "err"); return redirect("/")
        name = request.form.get("name", "").strip()
        if not re.fullmatch(r"[\w .'-]{2,40}", name): flash("Please enter your name (2 to 40 letters).", "err"); return redirect("/")
        f = request.files.get("file")
        if not f or not f.filename: flash("Choose a file to upload.", "err"); return redirect("/")
        head = f.stream.read(8); f.stream.seek(0)
        kind = next((v for sg, v in SIGS.items() if head.startswith(sg)), None)
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if not kind or ext not in EXT[kind]: flash("Only photos (PNG, JPG), PDF and Word (DOC, DOCX) files are accepted.", "err"); return redirect("/")
        jid = secrets.token_urlsafe(12); src = os.path.join(UP, jid + ".src"); path = os.path.join(UP, jid + ".pdf"); f.save(src)
        try:
            if kind == "pdf":
                if re.search(rb"/(JavaScript|JS|Launch|EmbeddedFile)\b", open(src, "rb").read()): raise ValueError("active content")
                shutil.copy(src, path)
            elif kind in ("png", "jpg"): to_pdf_image(src, path)
            else: doc_ok(src, kind); doc_to_pdf(src, path)
            rd = PdfReader(path)
            if rd.is_encrypted: raise ValueError("password protected")
            pages = len(rd.pages)
            if not 1 <= pages <= int(S("max_pages")): raise ValueError("page limit")
        except Exception as e:
            try: os.remove(path)
            except OSError: pass
            log(f"upload rejected: {e}", "visitor")
            flash("Word files can't be printed on this server right now." if "not enabled" in str(e) else
                  f"This file can't be accepted. Use a file without a password or active content, up to {S('max_pages')} pages.", "err"); return redirect("/")
        finally:
            try: os.remove(src)
            except OSError: pass
        q("insert into jobs(id,filename,path,pages,amount,status,created,qr_url,provider,refs,qr_at,payee,name) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (jid, os.path.basename(f.filename)[:120], path, pages, 0, "draft", time.time(), "", "", "", 0, "", name), write=True)
        return redirect(f"/options/{jid}")
    return render_template("upload.html", tok=TS.dumps(1), price="%.2f" % (int(S("price_paise")) / 100))
@app.route("/options/<jid>", methods=["GET", "POST"])
def options(jid):
    j = q("select * from jobs where id=?", (jid,), one=True) or abort(404)
    if j["status"] != "draft": return redirect(f"/pay/{jid}")
    if request.method == "POST":
        rng, per = request.form.get("range", "all"), request.form.get("per_sheet", "1")
        if rng not in ("all", "odd", "even", "custom") or per not in ("1", "2", "4", "6", "9") or request.form.get("layout") not in ("portrait", "landscape"): abort(400)
        try: pages = parse_pages(rng, request.form.get("custom", ""), j["pages"])
        except ValueError: flash(f"Check the page numbers. Example: 1-5, 8, 11-13. This file has {j['pages']} page(s).", "err"); return redirect(f"/options/{jid}")
        per = int(per); sheets = math.ceil(len(pages) / per); amount = sheets * int(S("price_paise")); qr = ""; mode = S("pay_mode"); payee = ""
        try:
            if mode == "razorpay": qr = rzp_qr(jid, amount)
            elif mode == "paytm": qr = paytm_qr(jid, amount)
            elif mode == "upi": payee = S("upi_id"); qr = upi_qr(jid, amount, payee)
        except Exception as e: print("QR creation failed:", e); flash("Payment is unavailable right now. Please tell the operator.", "err"); return redirect(f"/options/{jid}")
        color = request.form.get("color", "mono") if printer_can_colour() else "mono"
        if color not in ("color", "mono"): abort(400)
        o = json.dumps({"pages": pages, "landscape": request.form["layout"] == "landscape", "per_sheet": per, "color": color})
        q("update jobs set status='pending', amount=?, sel=?, sheets=?, opts=?, qr_url=?, provider=?, refs=?, qr_at=?, payee=? where id=? and status='draft'",
          (amount, len(pages), sheets, o, qr, mode, jid if mode == "paytm" else "", time.time(), payee, jid), write=True)
        return redirect(f"/pay/{jid}")
    return render_template("options.html", j=j, price=int(S("price_paise")), colour=printer_can_colour())
@app.route("/pay/<jid>")
def pay(jid):
    j = q("select * from jobs where id=?", (jid,), one=True) or abort(404)
    if j["status"] == "pending": refresh_qr(jid); j = q("select * from jobs where id=?", (jid,), one=True)
    return render_template("pay.html", j=j, v=qr_version(j))
@app.route("/pay/<jid>/qr.png")
def pay_qr(jid): return png(request.url_root + f"pay/{jid}")  # mock mode only
@app.route("/status/<jid>")
def status(jid):
    j = q("select status, provider from jobs where id=?", (jid,), one=True) or abort(404)
    if j["status"] == "pending":
        if j["provider"] == "paytm": paytm_check(jid)
        refresh_qr(jid)
    j = q("select status, qr_url from jobs where id=?", (jid,), one=True)
    out = {"status": j["status"]}
    if j["status"] == "pending":
        out["v"] = qr_version(j)
        if request.args.get("v") != out["v"]: out["qr"] = j["qr_url"]  # the new QR is pushed to the open page at once
    return jsonify(out)
@app.route("/mock-pay/<jid>", methods=["POST"])
def mock_pay(jid):
    if S("pay_mode") != "mock" or not me() or request.form.get("csrf") != session.get("csrf"): abort(404)  # admin-only test button
    j = q("select amount from jobs where id=?", (jid,), one=True) or abort(404)
    mark_paid(jid, j["amount"]); return redirect(f"/pay/{jid}")
retrying = set()
def _later(jid): time.sleep(5); retrying.discard(jid); paytm_check(jid)
@app.route("/webhook/paytm", methods=["POST"])
def webhook_paytm():  # Paytm only says "look at this order"; the amount is confirmed by asking Paytm directly
    d = request.get_json(silent=True); d = d if isinstance(d, dict) else {}
    ref = str(request.form.get("ORDERID") or d.get("orderId") or "")
    j = q("select id from jobs where provider='paytm' and status='pending' and instr(',' || refs || ',', ?) > 0", ("," + ref + ",",), one=True)
    if j and ref:
        paytm_check(j["id"])  # if Paytm has not settled yet, or this was throttled, look once more in 5 seconds
        if j["id"] not in retrying and len(retrying) < 200: retrying.add(j["id"]); threading.Thread(target=_later, args=(j["id"],), daemon=True).start()
    return "ok"
@app.route("/healthz")
def healthz(): return "ok"
@app.route("/webhook/razorpay", methods=["POST"])
def webhook():
    raw = request.get_data(); sig = request.headers.get("X-Razorpay-Signature", "")
    good = hmac.new(S("rzp_webhook").encode(), raw, hashlib.sha256).hexdigest()
    if not S("rzp_webhook") or not hmac.compare_digest(good, sig): abort(400)
    d = request.get_json()
    if d.get("event") == "qr_code.credited":
        p = d["payload"]; notes = p["qr_code"]["entity"].get("notes") or {}
        jid = notes.get("job_id") if isinstance(notes, dict) else None
        if jid: mark_paid(jid, p["payment"]["entity"]["amount"], p["payment"]["entity"]["id"])
    return "ok"

# ---------- admin ----------
def setup_status():  # the live board opens only when every required step is done
    a = me(); mode = S("pay_mode")
    pay = {"razorpay": all(S(k) for k in ("rzp_key", "rzp_secret", "rzp_webhook")), "paytm": bool(S("paytm_mid") and S("paytm_key")),
           "upi": bool(S("upi_id")), "mock": not PRODUCTION}.get(mode, False)
    items = [("Security code created", bool(a and a["pin_hash"]), True),
             ("Printer connection chosen and printer selected", bool(S("conn_type") and (S("printer") or WIN)), True),
             ("Printer settings saved", S("printer_cfg") == "1", True),
             ("Payment details complete and saved", bool(pay and S("pay_saved") == "1"), True),
             ("Public website address set", bool(S("public_url")), True),
             ("Two-step login turned on", bool(a and a["totp_on"]), PRODUCTION)]
    return items, all(ok for _, ok, req in items if req)
def home(): return AP + "/live" if setup_status()[1] else AP
def history(limit=100):
    out = []
    for r in q("select * from jobs where paid_at>0 order by paid_at desc limit ?", (limit,)):
        t = time.localtime(r["paid_at"])
        out.append({"id": r["id"], "name": r["name"] or "Customer", "amount": f"₹{r['amount'] / 100:.2f}", "date": time.strftime("%d %b %Y", t),
                    "time": time.strftime("%I:%M %p", t), "sheets": r["sheets"], "via": {"razorpay": "Razorpay", "paytm": "Paytm", "upi": "UPI", "mock": "Test"}.get(r["provider"], r["provider"])})
    return out
def today():
    start = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
    r = q("select count(*) n, coalesce(sum(amount),0) s from jobs where paid_at>=?", (start,), one=True)
    return {"count": r["n"], "total": f"₹{r['s'] / 100:.2f}"}
@app.route(AP + "/setup", methods=["GET", "POST"])
def setup():
    if q("select 1 from admins", one=True): abort(404)
    if request.method == "POST":
        if not hmac.compare_digest(request.form.get("setup_code", ""), SETUP_TOKEN):
            log("wrong setup code", "visitor"); flash("Wrong setup code. It is printed in the server console.", "err"); return render_template("setup.html")
        if weak(request.form["password"]): flash(WEAK, "err"); return render_template("setup.html")
        q("insert into admins(username,pw_hash) values(?,?)", (request.form["username"].strip(), H(request.form["password"])), write=True)
        a = q("select * from admins", one=True); session.clear(); session.permanent = True
        session["aid"] = a["id"]; session["sv"] = a["sv"]; log("first admin created", a["username"]); return redirect(AP + "/pin")
    return render_template("setup.html")
@app.route(AP + "/login", methods=["GET", "POST"])
def login():
    if not q("select 1 from admins", one=True): return redirect(AP + "/setup")
    if request.method == "POST":
        u = request.form["username"].strip(); k = ("login", request.remote_addr, u.lower())
        if locked(k): flash("Too many attempts. Try again in 10 minutes.", "err"); return render_template("login.html")
        a = q("select * from admins where username=?", (u,), one=True)
        good = C(a["pw_hash"] if a else DUMMY, request.form["password"])  # same work whether or not the user exists
        if a and good:
            fails.pop(k, None); session.clear(); session.permanent = True
            if a["totp_on"]: session["pre"] = a["id"]; return redirect(AP + "/totp")
            session["aid"] = a["id"]; session["sv"] = a["sv"]; log("login", a["username"]); return redirect(home())
        fail(k); log("login failed: " + u[:40], "visitor"); print(f"FAILED_LOGIN ip={request.remote_addr}", flush=True); flash("Wrong username or password.", "err")
    return render_template("login.html")
@app.route(AP + "/totp", methods=["GET", "POST"])
def totp():
    a = q("select * from admins where id=?", (session.get("pre"),), one=True) or abort(403)
    k = ("totp", a["id"])
    if request.method == "POST":
        if locked(k): flash("Too many wrong codes. Try again in 10 minutes.", "err"); return render_template("totp.html")
        if totp_ok(a, request.form["code"]):
            fails.pop(k, None); session.pop("pre"); session["aid"] = a["id"]; session["sv"] = a["sv"]
            log("login (2FA)", a["username"]); return redirect(home())
        fail(k); log("wrong 2FA code", a["username"]); flash("That code didn't match. Try the newest code.", "err")
    return render_template("totp.html")
@app.route(AP + "/logout", methods=["POST"])
def logout():
    log("logout"); session.clear(); return redirect(AP + "/login")
@app.route(AP + "/live")
@admin
def live():
    if not setup_status()[1]: flash("Finish the setup checklist to open the live board.", "err"); return redirect(AP)
    return render_template("live.html", rows=history(), url=(S("public_url") or request.url_root).rstrip("/") + "/")
@app.route(AP + "/live/data")
@admin
def live_data(): return jsonify(rows=history())
@app.route(AP + "/live/setup-code", methods=["POST"])
@admin
def change_setup_code():  # the setup code guards UPI changes, the key vault and this change itself
    global SETUP_TOKEN
    if not pin_ok(me()): return redirect(AP + "/live")
    if os.environ.get("SETUP_TOKEN"): flash("The setup code is set in .env on this server. Change it there.", "err"); return redirect(AP + "/live")
    cur, new = request.form.get("setup_code", ""), request.form.get("new_setup_code", "")
    if not hmac.compare_digest(cur, SETUP_TOKEN): log("wrong setup code", me()["username"]); flash("The current setup code is wrong.", "err"); return redirect(AP + "/live")
    if len(new) < 10 or not re.fullmatch(r"[A-Za-z0-9_-]+", new): flash("The new setup code needs 10+ letters, numbers, - or _.", "err"); return redirect(AP + "/live")
    with os.fdopen(os.open(os.path.join(BASE, ".setup_code"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f: f.write(new)
    SETUP_TOKEN = new; log("setup code changed", me()["username"]); flash("Setup code changed. Keep it safe.", "ok"); return redirect(AP + "/live")
@app.route(AP)
@admin
def dash():
    steps, done = setup_status(); pr = S("printer"); ok, ps = sh(["lpstat", "-p", pr], 4) if pr and not WIN else (False, "")
    return render_template("admin.html", steps=steps, done=done, ndone=sum(1 for x in steps if x[1]), conn=CONN, colour_auto=not WIN, paper=list(PAPER), printers=printers(), pstat=ps if ok else "",
        usb=usb_found() if request.args.get("detect") else None, admins=q("select id,username from admins"),
        waiting=q("select * from jobs where provider='upi' and status='pending' order by created desc limit 20"),
        jobs=q("select * from jobs where status!='draft' order by created desc limit 15"),
        audit=[(time.strftime("%d %b %H:%M", time.localtime(r["ts"])), r["who"], r["ip"], r["ev"]) for r in q("select * from audit order by ts desc limit 15")],
        pending2fa=bool(me()["totp_secret"] and not me()["totp_on"]))
@app.route(AP + "/form-qr.png")
@admin
def form_qr(): return png((S("public_url") or request.url_root).rstrip("/") + "/")
@app.route(AP + "/pin", methods=["GET", "POST"])
@admin
def pin():
    a = me()
    if request.method == "POST":
        if a["pin_hash"] and not pin_ok(a): return redirect(AP + "/pin")
        new = request.form["new_pin"]
        if len(new) < 6: flash("Use at least 6 characters.", "err"); return redirect(AP + "/pin")
        q("update admins set pin_hash=? where id=?", (H(new), a["id"]), write=True); bump(a); log("security code changed")
        flash("Security code saved.", "ok"); return redirect(AP)
    return render_template("pin.html")
@app.route(AP + "/printer", methods=["POST"])
@admin
def set_printer():
    f = request.form
    if f.get("conn_type") in CONN: setS("conn_type", f["conn_type"])
    if "printer" in f and f["printer"] in [""] + printers(): setS("printer", f["printer"])  # only fields that were sent are changed
    for k, allowed in (("paper", PAPER), ("quality", ("draft", "normal", "high")), ("sides", ("one", "two"))):
        if f.get(k) in allowed: setS(k, f[k])
    if "printer_colour" in f: setS("printer_colour", "1" if f["printer_colour"] == "yes" else "")
    if "public_url" in f:
        pu = f["public_url"].strip()
        if pu and not re.fullmatch(r"https?://[A-Za-z0-9.:-]{3,100}/?", pu): flash("The website address should look like https://print.example.com", "err"); return redirect(AP)
        setS("public_url", pu.rstrip("/"))
    try:
        if "max_pages" in f: setS("max_pages", str(min(500, max(1, int(f["max_pages"])))))
    except ValueError: pass
    setS("printer_cfg", "1"); log("printer settings changed"); flash("Printer settings saved.", "ok"); return redirect(AP)
@app.route(AP + "/printer/add", methods=["POST"])
@admin
def printer_add():
    if not pin_ok(me()): return redirect(AP)
    name = request.form.get("name", "").strip(); uri = request.form.get("uri", ""); ct = "usb"
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,30}", name): flash("Printer name: 2 to 30 letters, numbers, - or _.", "err"); return redirect(AP)
    if uri:
        if uri not in usb_found(): flash("That USB printer is not connected.", "err"); return redirect(AP)
    else:
        host = request.form.get("host", "").strip(); ct = request.form.get("conn_type", "wifi")
        try: ip = ipaddress.ip_address(host); okh = ip.version == 4 and (ip.is_private or ip.is_link_local)
        except ValueError: okh = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{2,80}", host))
        if ct not in ("wifi", "wifidirect", "ethernet") or not okh: flash("Enter the printer's address on your own network, like 192.168.1.50.", "err"); return redirect(AP)
        uri = f"ipp://{host}/ipp/print"
    ok, out = add_printer(name, uri)
    if ok: setS("printer", name); setS("conn_type", ct); log(f"printer added: {name}"); flash(f"Printer {name} added and selected.", "ok")
    else: print("lpadmin failed:", out); flash("Could not add the printer. Check the address, that it is on, and that CUPS is installed.", "err")
    return redirect(AP)
@app.route(AP + "/printer/test", methods=["POST"])
@admin
def printer_test():
    out = os.path.join(UP, "test-" + secrets.token_hex(4) + ".pdf")
    try:
        im = Image.new("RGB", (1240, 1754), "white")
        ImageDraw.Draw(im).text((100, 120), f"{SHOP} - printer test page\n{time.strftime('%d %b %Y %H:%M')}\nIf you can read this, printing works.", fill="black")
        im.save(out, "PDF", resolution=150); print_file(out); log("test page printed"); flash("Test page sent to the printer.", "ok")
    except Exception as e: print("test print failed:", e); flash("Could not print the test page. Check the printer connection.", "err")
    finally:
        try: os.remove(out)
        except OSError: pass
    return redirect(AP)
@app.route(AP + "/payment", methods=["POST"])
@admin
def set_payment():
    if not pin_ok(me()): return redirect(AP)
    try: price = round(float(request.form["price"]) * 100)  # round, not int(): 2.3*100 is 229.999...
    except ValueError: price = 0
    if price < 1 or request.form["mode"] not in (("razorpay", "paytm", "upi") if PRODUCTION else ("mock", "razorpay", "paytm", "upi")): flash("Enter a valid price and mode.", "err"); return redirect(AP)
    setS("price_paise", str(price)); setS("pay_mode", request.form["mode"])
    setS("pay_saved", "1"); log("payment settings changed"); flash("Payment settings saved.", "ok"); return redirect(AP)
@app.route(AP + "/account", methods=["POST"])
@admin
def account():
    a = me()
    if not pin_ok(a): return redirect(AP)
    pw = request.form.get("password")
    if pw and weak(pw): flash(WEAK, "err"); return redirect(AP)
    try:
        if request.form.get("username"): q("update admins set username=? where id=?", (request.form["username"].strip(), a["id"]), write=True)
    except sqlite3.IntegrityError: flash("That username is taken.", "err"); return redirect(AP)
    if pw: q("update admins set pw_hash=? where id=?", (H(pw), a["id"]), write=True); bump(a)
    log("account updated"); flash("Account updated.", "ok"); return redirect(AP)
@app.route(AP + "/admins", methods=["POST"])
@admin
def add_admin():
    if not pin_ok(me()): return redirect(AP)
    if weak(request.form["password"]): flash(WEAK, "err"); return redirect(AP)
    try: q("insert into admins(username,pw_hash) values(?,?)", (request.form["username"].strip(), H(request.form["password"])), write=True)
    except sqlite3.IntegrityError: flash("That username is taken.", "err"); return redirect(AP)
    log("admin added: " + request.form["username"].strip()[:40]); flash("Admin added. They set their own security code at first login.", "ok"); return redirect(AP)
@app.route(AP + "/confirm/<jid>", methods=["POST"])
@admin
def confirm(jid):  # direct-UPI mode: the operator has seen the money arrive
    j = q("select * from jobs where id=?", (jid,), one=True)
    if j and j["provider"] == "upi" and j["status"] == "pending":
        mark_paid(jid, j["amount"]); log(f"payment confirmed by admin job={jid} amount={j['amount']}")
        flash("Payment confirmed. Printing started.", "ok")
    return redirect(AP)
UPI_RE = re.compile(r"[A-Za-z0-9._-]{2,64}@[A-Za-z][A-Za-z0-9]{1,31}")
@app.route(AP + "/upi", methods=["POST"])
@admin
def set_upi():  # changing where the money goes needs the admin's security code AND the owner's setup code
    a = me(); k = ("setupcode", a["id"])
    if locked(k): flash("Too many wrong setup codes. Try again in 10 minutes.", "err"); return redirect(AP)
    if not pin_ok(a): return redirect(AP)
    if not hmac.compare_digest(request.form.get("setup_code", ""), SETUP_TOKEN):
        fail(k); log("wrong setup code on UPI change"); flash("Wrong setup code.", "err"); return redirect(AP)
    upi = request.form.get("upi_id", "").strip(); name = request.form.get("upi_name", "").strip()
    if not UPI_RE.fullmatch(upi) or not re.fullmatch(r"[A-Za-z0-9 .&'-]{1,40}", name):
        flash("Enter a valid UPI ID (like shop@bank) and a simple payee name.", "err"); return redirect(AP)
    old = S("upi_id"); setS("upi_id", upi); setS("upi_name", name); fails.pop(k, None)
    log(f"UPI ID changed {old or '-'} -> {upi}"); flash("UPI ID changed. Every new and waiting QR uses it now.", "ok"); return redirect(AP)
def vault_open():
    v = session.get("vault"); return bool(v) and v[0] == session.get("aid") and time.time() < v[1]
def vault_gate():
    if not vault_open(): flash("The vault is locked. Unlock it first.", "err"); return False
    return True
@app.route(AP + "/vault")
@admin
def vault():
    st = "create" if not os.path.exists(VAUTH) else ("open" if vault_open() else "locked")
    d = vload() if st == "open" else {}
    return render_template("vault.html", state=st, known=KNOWN, missing=[n for n in KNOWN if n not in d],
                           items=[(n, "••••" + v[-4:] if len(v) > 8 else "••••") for n, v in sorted(d.items())])
@app.route(AP + "/vault/create", methods=["POST"])
@admin
def vault_create():
    a = me(); k = ("setupcode", a["id"])
    if os.path.exists(VAUTH): abort(404)
    if locked(k) or not hmac.compare_digest(request.form.get("setup_code", ""), SETUP_TOKEN):
        fail(k); log("wrong setup code on vault creation"); flash("Wrong setup code.", "err"); return redirect(AP + "/vault")
    p = request.form.get("vpass", "")
    if p != request.form.get("vpass2") or weak(p): flash(WEAK + " Both entries must match.", "err"); return redirect(AP + "/vault")
    write_private(VAUTH, H(p)); session["vault"] = [a["id"], time.time() + 300]; log("vault created")
    return redirect(AP + "/vault")
@app.route(AP + "/vault/unlock", methods=["POST"])
@admin
def vault_unlock():
    a = me(); k = ("vault", a["id"])
    if locked(k): flash("Too many attempts. Try again in 10 minutes.", "err"); return redirect(AP + "/vault")
    try: ok = C(open(VAUTH).read(), request.form.get("vpass", ""))
    except OSError: ok = False
    if ok: fails.pop(k, None); session["vault"] = [a["id"], time.time() + 300]; log("vault unlocked")
    else: fail(k); log("wrong vault password"); flash("Wrong vault password.", "err")
    return redirect(AP + "/vault")
@app.route(AP + "/vault/lock", methods=["POST"])
@admin
def vault_lock(): session.pop("vault", None); return redirect(AP + "/vault")
@app.route(AP + "/vault/set", methods=["POST"])
@admin
def vault_set():
    if not vault_gate(): return redirect(AP + "/vault")
    n = request.form.get("name", "").strip().lower(); v = request.form.get("value", "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", n) or not v or len(v) > 500:
        flash("Name: 2 to 40 letters, numbers or _. A value is required.", "err"); return redirect(AP + "/vault")
    if n == "paytm_host" and not re.fullmatch(PT_HOST_RE, v):
        flash("Paytm host must be an https address on paytmpayments.com, paytmpayments.in or paytm.in.", "err"); return redirect(AP + "/vault")
    d = dict(vload()); d[n] = v; vsave(d); log(f"vault: saved {n}"); flash(f"Saved {n}.", "ok")
    return redirect(AP + "/vault")
@app.route(AP + "/vault/delete", methods=["POST"])
@admin
def vault_delete():
    if not vault_gate(): return redirect(AP + "/vault")
    n = request.form.get("name", ""); d = dict(vload())
    if d.pop(n, None) is not None: vsave(d); log(f"vault: removed {n}"); flash(f"Removed {n}.", "ok")
    return redirect(AP + "/vault")
@app.route(AP + "/vault/password", methods=["POST"])
@admin
def vault_password():
    if not vault_gate(): return redirect(AP + "/vault")
    new = request.form.get("new", "")
    if not C(open(VAUTH).read(), request.form.get("cur", "")) or weak(new): flash("Current password wrong, or the new one is too weak. " + WEAK, "err"); return redirect(AP + "/vault")
    write_private(VAUTH, H(new)); log("vault password changed"); flash("Vault password changed.", "ok"); return redirect(AP + "/vault")
@app.route(AP + "/retry/<jid>", methods=["POST"])
@admin
def retry(jid):
    j = q("select status,path from jobs where id=?", (jid,), one=True)
    if j and j["status"] == "print_failed" and j["path"]:
        log(f"print retried job={jid}"); threading.Thread(target=run_print, args=(jid,), daemon=True).start()
    return redirect(AP)
@app.route(AP + "/2fa/start", methods=["POST"])
@admin
def tfa_start():
    q("update admins set totp_secret=?, totp_on=0 where id=?", (FER.encrypt(pyotp.random_base32().encode()).decode(), me()["id"]), write=True); return redirect(AP)
@app.route(AP + "/2fa.png")
@admin
def tfa_png(): return png(pyotp.TOTP(tsec(me())).provisioning_uri(me()["username"], issuer_name="Print Admin"))
@app.route(AP + "/2fa/confirm", methods=["POST"])
@admin
def tfa_confirm():
    if totp_ok(me(), request.form["code"]):
        q("update admins set totp_on=1 where id=?", (me()["id"],), write=True); log("2FA on"); flash("Two-step login is on.", "ok")
    else: flash("That code didn't match.", "err")
    return redirect(AP)
@app.route(AP + "/2fa/off", methods=["POST"])
@admin
def tfa_off():
    if pin_ok(me()): q("update admins set totp_on=0, totp_secret=NULL where id=?", (me()["id"],), write=True); log("2FA off"); flash("Two-step login is off.", "ok")
    return redirect(AP)

# ---------- templates ----------
ERRMSG = {400: "That request didn't look right.", 404: "We couldn't find that page.", 413: "That file is too big (25 MB at most).", 429: "Too many requests. Please slow down for a moment."}
@app.errorhandler(Exception)
def oops(e):
    code = e.code if isinstance(e, HTTPException) else 500
    if code == 500: print("ERROR:", repr(e), flush=True)
    return render_template("error.html", code=code, msg=ERRMSG.get(code, "Something went wrong on our side.")), code
app.jinja_loader = DictLoader(TEMPLATES)
print(f"\n*** Admin panel address: {AP}   (saved in .admin_path) ***")
if not q("select 1 from admins", one=True): print(f"*** First-time setup: open {AP}/setup and use code {SETUP_TOKEN} ***\n")
threading.Thread(target=cleanup, daemon=True).start()  # also runs under gunicorn/waitress
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
