# static_html.py -- Kompakte Single Page App (Dark Glassmorphism UI)

HTML_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>signalrpi Gateway</title>
<style>
:root{--bg:#0f172a;--card:rgba(30,41,59,0.7);--border:rgba(255,255,255,0.1);--accent:#38bdf8;--text:#f8fafc;--text-dim:#94a3b8;--green:#22c55e;--red:#ef4444}
*{box-sizing:border-box;margin:0;padding:0;font-family:system-ui,-apple-system,sans-serif}
body{background:var(--bg);color:var(--text);padding:1rem;min-height:100vh}
.header{display:flex;justify-content:space-between;align-items:center;padding:0.75rem 1.25rem;background:var(--card);backdrop-filter:blur(12px);border:1px solid var(--border);border-radius:12px;margin-bottom:1rem}
.brand{font-size:1.25rem;font-weight:700;color:var(--accent);display:flex;align-items:center;gap:8px}
.pill{background:rgba(34,197,94,0.2);color:var(--green);padding:4px 10px;border-radius:20px;font-size:0.8rem;font-weight:600}
.nav{display:flex;gap:8px;margin-bottom:1rem}
.nav-btn{background:var(--card);border:1px solid var(--border);color:var(--text-dim);padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:600}
.nav-btn.active{background:var(--accent);color:#0f172a}
.card{background:var(--card);border:1px solid var(--border);backdrop-filter:blur(12px);border-radius:12px;padding:1.25rem;margin-bottom:1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem}
.device-card{background:rgba(15,23,42,0.6);border:1px solid var(--border);padding:1rem;border-radius:10px}
.val-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.val-box{background:rgba(255,255,255,0.03);padding:8px;border-radius:6px;border:1px solid rgba(255,255,255,0.05)}
.val-title{font-size:0.75rem;color:var(--text-dim)}
.val-num{font-size:1.2rem;font-weight:700;color:var(--accent)}
.btn{background:var(--accent);color:#0f172a;border:none;padding:6px 12px;border-radius:6px;font-weight:600;cursor:pointer}
.btn-del{background:var(--red);color:#fff}
.sniffer-box{max-height:400px;overflow-y:auto;font-family:monospace;font-size:0.85rem}
.packet{padding:8px;border-bottom:1px solid rgba(255,255,255,0.05);display:flex;justify-content:space-between;align-items:center}
.form-input{width:100%;padding:8px;background:rgba(15,23,42,0.8);border:1px solid var(--border);color:#fff;border-radius:6px;margin:6px 0 12px}
</style>
</head>
<body>
<div class="header">
  <div class="brand">📻 signalrpi Gateway</div>
  <div class="pill" id="sys-status">Online</div>
</div>
<div class="nav">
  <button class="nav-btn active" onclick="showTab('tab-devices')">Geräte</button>
  <button class="nav-btn" onclick="showTab('tab-sniffer')">Live Sniffer</button>
  <button class="nav-btn" onclick="showTab('tab-it')">Intertechno</button>
  <button class="nav-btn" onclick="showTab('tab-system')">System</button>
</div>

<div id="tab-devices" class="tab-content">
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
      <h3>Bekannte Funk-Geräte</h3>
      <button class="btn" onclick="refreshDevices()">Aktualisieren</button>
    </div>
    <div id="devices-list" class="grid">Lade Geräte...</div>
  </div>
</div>

<div id="tab-sniffer" class="tab-content" style="display:none">
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
      <h3>433 & 868 MHz Live Sniffer</h3>
      <span class="pill" style="background:rgba(56,189,248,0.2);color:var(--accent)">Echtzeit-Empfang</span>
    </div>
    <div id="sniffer-list" class="sniffer-box">Warte auf Signale...</div>
  </div>
</div>

<div id="tab-it" class="tab-content" style="display:none">
  <div class="card">
    <h3>Intertechno Schalter anlernen & testen</h3>
    <p style="color:var(--text-dim);margin:8px 0 16px;font-size:0.9rem">Steckdosen und Aktoren direkt per Funk schalten.</p>
    <div style="max-width:320px">
      <label>Gerätename:</label>
      <input id="it-name" class="form-input" value="Stehlampe">
      <label>Hauscode (A..P):</label>
      <input id="it-family" class="form-input" value="A" maxlength="1">
      <label>Gruppe (1..4):</label>
      <input id="it-group" class="form-input" type="number" value="1" min="1" max="4">
      <label>Kanal (1..4):</label>
      <input id="it-device" class="form-input" type="number" value="1" min="1" max="4">
      <div style="display:flex;gap:8px">
        <button class="btn" style="background:var(--green);color:#fff" onclick="sendIT('on')">EINSCHALTEN</button>
        <button class="btn" style="background:var(--red);color:#fff" onclick="sendIT('off')">AUSSCHALTEN</button>
        <button class="btn" onclick="saveITDevice()">In HA anlegen</button>
      </div>
    </div>
  </div>
</div>

<div id="tab-system" class="tab-content" style="display:none">
  <div class="card">
    <h3>System Status & Diagnose</h3>
    <div class="val-grid" style="max-width:400px;margin-top:1rem">
      <div class="val-box"><div class="val-title">IP-Adresse</div><div class="val-num" id="s-ip">...</div></div>
      <div class="val-box"><div class="val-title">WLAN Signal</div><div class="val-num" id="s-rssi">...</div></div>
      <div class="val-box"><div class="val-title">Freier RAM</div><div class="val-num" id="s-ram">...</div></div>
      <div class="val-box"><div class="val-title">MQTT Broker</div><div class="val-num" id="s-mqtt">Verbunden</div></div>
    </div>
  </div>
</div>

<script>
function showTab(tabId){
  document.querySelectorAll('.tab-content').forEach(el=>el.style.display='none');
  document.querySelectorAll('.nav-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById(tabId).style.display='block';
  event.target.classList.add('active');
}
async function refreshDevices(){
  try{
    let res = await fetch('/api/devices');
    let data = await res.json();
    let c = document.getElementById('devices-list');
    if(!data.length){c.innerHTML='<p style="color:var(--text-dim)">Keine Geräte angelegt.</p>';return;}
    c.innerHTML = data.map(d=>`
      <div class="device-card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong>${d.name}</strong>
          <span style="font-size:0.75rem;color:var(--accent)">${d.protocol}</span>
        </div>
        <div style="font-size:0.8rem;color:var(--text-dim);margin-top:4px">ID: ${d.id} | Kanal: ${d.channel||'-'}</div>
        <div class="val-grid">
          ${(d.entities||[]).map(e=>`
            <div class="val-box"><div class="val-title">${e.name}</div><div class="val-num" id="val_${d.id}_${e.key}">-- ${e.unit||''}</div></div>
          `).join('')}
        </div>
        <button class="btn btn-del" onclick="delDevice('${d.id}')">Löschen</button>
      </div>
    `).join('');
  }catch(e){console.error(e);}
}
async function delDevice(id){
  if(confirm('Gerät '+id+' wirklich löschen?')){
    await fetch('/api/devices?id='+id, {method:'DELETE'});
    refreshDevices();
  }
}
async function updateSystem(){
  try{
    let res = await fetch('/api/status');
    let s = await res.json();
    document.getElementById('s-ip').innerText = s.ip;
    document.getElementById('s-rssi').innerText = s.wifi_rssi+' dBm';
    document.getElementById('s-ram').innerText = Math.round(s.free_ram/1024)+' kB';
  }catch(e){}
}
function startSniffer(){
  let s = document.getElementById('sniffer-list');
  let poll = async ()=>{
    try{
      let r = await fetch('/api/live');
      let pkts = await r.json();
      pkts.forEach(p=>{
        let div = document.createElement('div');
        div.className = 'packet';
        div.innerHTML = `<div><strong>[${p.band}]</strong> ${p.proto} (ID: ${p.id||'?'}) <span style="color:var(--accent)">${p.rssi} dBm</span></div><div><button class="btn" onclick="adoptDevice('${p.proto}','${p.id||''}')">Anlernen</button></div>`;
        s.insertBefore(div, s.firstChild);
        if(s.children.length>40) s.removeChild(s.lastChild);
      });
    }catch(e){}
    setTimeout(poll, 1500);
  };
  poll();
}
function adoptDevice(proto, id){
  let name = prompt('Name für dieses Gerät (z.B. Garten):', proto+' '+id);
  if(name){
    fetch('/api/devices', {
      method:'POST',
      body: JSON.stringify({id:'dev_'+id, name:name, protocol:proto, type:'sensor', entities:[{key:'temperature',name:'Temperatur',unit:'°C',device_class:'temperature'},{key:'humidity',name:'Feuchte',unit:'%',device_class:'humidity'}]})
    }).then(()=>refreshDevices());
  }
}
refreshDevices();
updateSystem();
startSniffer();
setInterval(updateSystem, 5000);
</script>
</body>
</html>
"""
