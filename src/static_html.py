# static_html.py -- Kompakte Single Page App (Dark Glassmorphism UI mit Re-Assign & Zeitstempel)

HTML_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>signalrpi Gateway</title>
<style>
:root{--bg:#0f172a;--card:rgba(30,41,59,0.7);--border:rgba(255,255,255,0.1);--accent:#38bdf8;--text:#f8fafc;--text-dim:#94a3b8;--green:#22c55e;--red:#ef4444;--amber:#f59e0b}
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
.val-num{font-size:1.15rem;font-weight:700;color:var(--accent)}
.btn{background:var(--accent);color:#0f172a;border:none;padding:6px 12px;border-radius:6px;font-weight:600;cursor:pointer}
.btn-amber{background:var(--amber);color:#0f172a}
.btn-del{background:var(--red);color:#fff}
.sniffer-box{max-height:500px;overflow-y:auto;font-family:monospace;font-size:0.85rem}
.packet{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;justify-content:space-between;align-items:center;gap:12px}
.packet:hover{background:rgba(255,255,255,0.02)}
.form-input{width:100%;padding:8px;background:rgba(15,23,42,0.8);border:1px solid var(--border);color:#fff;border-radius:6px;margin:6px 0 12px}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);backdrop-filter:blur(4px);justify-content:center;align-items:center;z-index:100}
.modal-card{background:#1e293b;border:1px solid var(--border);padding:1.5rem;border-radius:12px;width:90%;max-width:400px}
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
      <h3>Bekannte Funk-Geräte (Home Assistant)</h3>
      <button class="btn" onclick="refreshDevices()">Aktualisieren</button>
    </div>
    <div id="devices-list" class="grid">Lade Geräte...</div>
  </div>
</div>

<div id="tab-sniffer" class="tab-content" style="display:none">
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
      <h3>Live Sniffer (433 & 868 MHz)</h3>
      <span class="pill" style="background:rgba(56,189,248,0.2);color:var(--accent)">Echtzeit-Empfang</span>
    </div>
    <div id="sniffer-list" class="sniffer-box">Warte auf Signale...</div>
  </div>
</div>

<div id="tab-it" class="tab-content" style="display:none">
  <div class="card">
    <h3>Intertechno Funksteckdosen</h3>
    <div style="max-width:320px;margin-top:1rem">
      <label>Gerätename:</label>
      <input id="it-name" class="form-input" value="Stehlampe">
      <label>Hauscode (A..P):</label>
      <input id="it-family" class="form-input" value="A" maxlength="1">
      <label>Gruppe (1..4):</label>
      <input id="it-group" class="form-input" type="number" value="1" min="1" max="4">
      <label>Kanal (1..4):</label>
      <input id="it-device" class="form-input" type="number" value="1" min="1" max="4">
      <div style="display:flex;gap:8px">
        <button class="btn" style="background:var(--green);color:#fff" onclick="alert('Schaltbefehl ON gesendet!')">EIN</button>
        <button class="btn" style="background:var(--red);color:#fff" onclick="alert('Schaltbefehl OFF gesendet!')">AUS</button>
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

  <div class="card">
    <h3>🚀 Firmware & OTA Updates</h3>
    <p style="color:var(--text-dim);font-size:0.85rem;margin:8px 0 16px">Aktualisiere den Pico W kabellos direkt über GitHub oder flashe einzelne Dateien.</p>
    
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem">
      <div style="background:rgba(15,23,42,0.6);border:1px solid var(--border);padding:1rem;border-radius:10px">
        <h4 style="color:var(--accent);margin-bottom:8px">1. GitHub OTA Update</h4>
        <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:12px">Lädt den neuesten Stand des Haupt-Branches von GitHub herunter und startet neu.</p>
        <button class="btn" onclick="triggerGitHubOTA()" id="btn-ota">Jetzt von GitHub aktualisieren</button>
        <div id="ota-status" style="font-size:0.8rem;margin-top:8px;color:var(--amber)"></div>
      </div>

      <div style="background:rgba(15,23,42,0.6);border:1px solid var(--border);padding:1rem;border-radius:10px">
        <h4 style="color:var(--accent);margin-bottom:8px">2. Firmware-Datei (Flash)</h4>
        <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:12px">Lade eine geänderte Python-Datei (.py) direkt in das Flash-Dateisystem des Pico hoch.</p>
        <input type="file" id="file-upload-input" accept=".py" style="font-size:0.8rem;margin-bottom:8px;color:var(--text-dim)">
        <button class="btn btn-amber" onclick="uploadFile()">Datei flashen</button>
        <div id="upload-status" style="font-size:0.8rem;margin-top:8px;color:var(--green)"></div>
      </div>

      <div style="background:rgba(15,23,42,0.6);border:1px solid var(--border);padding:1rem;border-radius:10px">
        <h4 style="color:var(--accent);margin-bottom:8px">3. Geräte-Konfiguration (Backup & Restore)</h4>
        <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:10px">Sichere alle bekannten Geräte oder lade ein devices.json Backup wieder zurück.</p>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">
          <a href="/api/devices/download" download="devices.json" class="btn" style="text-decoration:none;display:inline-block">💾 Download</a>
        </div>
        <div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:8px">
          <label style="font-size:0.75rem;color:var(--text-dim)">devices.json wiederherstellen:</label>
          <input type="file" id="devices-upload-input" accept=".json" style="font-size:0.8rem;margin:6px 0;color:var(--text-dim);display:block">
          <button class="btn btn-amber" onclick="uploadDevicesJson()">Wiederherstellen</button>
          <div id="devices-upload-status" style="font-size:0.8rem;margin-top:6px;color:var(--green)"></div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Modal für generisches Sensor-Anlernen & Konfiguration -->
<div id="config-modal" class="modal">
  <div class="modal-card" style="max-width:500px">
    <h3 style="margin-bottom:8px">⚙ Sensor anlernen & konfigurieren</h3>
    <div id="cfg-modal-info" style="background:rgba(255,255,255,0.05);padding:8px;border-radius:6px;font-size:0.85rem;margin-bottom:12px"></div>
    
    <label style="font-size:0.8rem;color:var(--text-dim)">Gerätename:</label>
    <input id="cfg-name" class="form-input" type="text" placeholder="z.B. Wohnzimmer Thermometer">
    
    <label style="font-size:0.8rem;color:var(--text-dim)">Erkannte Messwerte / Entitäten:</label>
    <div id="cfg-entities-list" style="margin:8px 0 16px;display:flex;flex-direction:column;gap:8px"></div>
    
    <div style="margin-bottom:16px;background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05)">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:0.85rem">
        <input type="checkbox" id="cfg-enabled" checked style="width:18px;height:18px">
        <b>Für Home Assistant / MQTT sofort freigeben</b>
      </label>
      <div style="font-size:0.75rem;color:var(--text-dim);margin-left:26px;margin-top:2px">Ist dies deaktiviert, empfängt signalrpi die Daten nur intern und sendet nichts an MQTT.</div>
    </div>
    
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button class="btn" style="background:#64748b;color:#fff" onclick="closeConfigModal()">Abbrechen</button>
      <button class="btn" onclick="saveConfiguredDevice()">Speichern</button>
    </div>
  </div>
</div>

<!-- Modal für Batteriewechsel / Neu-Zuordnung -->
<div id="reassign-modal" class="modal">
  <div class="modal-card">
    <h3 style="margin-bottom:8px">Sensor neu zuordnen</h3>
    <p style="color:var(--text-dim);font-size:0.85rem;margin-bottom:12px">Wähle das bestehende Home Assistant Gerät aus, dem diese neue ID nach einem Batteriewechsel zugewiesen werden soll:</p>
    <div id="modal-info" style="background:rgba(255,255,255,0.05);padding:8px;border-radius:6px;font-size:0.85rem;margin-bottom:12px"></div>
    <label style="font-size:0.85rem;color:var(--text-dim)">Bestehendes Gerät:</label>
    <select id="modal-select" class="form-input"></select>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:1rem">
      <button class="btn" style="background:#64748b;color:#fff" onclick="closeModal()">Abbrechen</button>
      <button class="btn btn-amber" onclick="executeReassign()">Zuordnen</button>
    </div>
  </div>
</div>

<!-- Modal für Rohdaten-Inspektor / Signal-Export -->
<div id="raw-modal" class="modal">
  <div class="modal-card" style="max-width:540px">
    <h3 style="margin-bottom:8px">🔬 Signal-Rohdaten & Export</h3>
    <div id="raw-modal-meta" style="font-size:0.85rem;color:var(--text-dim);margin-bottom:10px"></div>
    <label style="font-size:0.8rem;color:var(--text-dim)">Pulsfolge / Rohdaten:</label>
    <textarea id="raw-modal-text" style="width:100%;height:150px;background:rgba(15,23,42,0.9);color:#38bdf8;border:1px solid var(--border);border-radius:6px;padding:8px;font-family:monospace;font-size:0.75rem;margin:6px 0 12px;resize:vertical" readonly></textarea>
    <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between">
      <div style="display:flex;gap:6px">
        <button class="btn" onclick="copyRaw('json')">📋 JSON kopieren</button>
        <button class="btn btn-amber" onclick="copyRaw('text')">📋 SignalESP/FHEM</button>
      </div>
      <button class="btn" style="background:#64748b;color:#fff" onclick="closeRawModal()">Schließen</button>
    </div>
  </div>
</div>

<script>
let knownDevices = [];
let pendingReassign = null;
let currentRawData = null;

function showTab(tabId){
  document.querySelectorAll('.tab-content').forEach(el=>el.style.display='none');
  document.querySelectorAll('.nav-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById(tabId).style.display='block';
  event.target.classList.add('active');
}

async function refreshDevices(){
  try{
    let res = await fetch('/api/devices');
    knownDevices = await res.json();
    let c = document.getElementById('devices-list');
    if(!knownDevices.length){c.innerHTML='<p style="color:var(--text-dim)">Keine Geräte angelegt.</p>';return;}
    c.innerHTML = knownDevices.map(d=>{
      let isEn = d.enabled !== false;
      // MQTT-Badge wird oben NUR angezeigt, wenn MQTT aktiv ist (transparentes Grün)
      let mqttBadge = isEn 
        ? `<span style="background:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.3);padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600">MQTT</span>`
        : '';

      let currentProf = d.profile || (d.entities && d.entities.length > 2 ? 'thermo_hygro' : (d.entities && d.entities.some(e=>e.key==='state') ? 'contact' : 'thermo'));

      return `
        <div class="device-card">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <strong style="font-size:1.05rem">${d.name}</strong>
            <div style="display:flex;gap:6px;align-items:center">
              ${mqttBadge}
              <span style="font-size:0.75rem;color:var(--accent);font-weight:600">${d.protocol}</span>
            </div>
          </div>
          <div style="font-size:0.8rem;color:var(--text-dim);margin:6px 0">
            HA-ID: <code>${d.id}</code> | Funk-ID: <b>${d.device_id||'Auto'}</b> ${d.channel?'| Kanal: '+d.channel:''}
          </div>
          <div class="val-grid">
            ${(d.entities||[]).filter(e => e.key !== 'channel' && e.key !== 'forced_send').map(e=>{
              let val = (d.latest && d.latest[e.key] !== undefined) ? d.latest[e.key] : (d.last_values ? d.last_values[e.key] : null);
              return `
                <div class="val-box">
                  <div class="val-title">${e.name}</div>
                  <div class="val-num">${val!==null && val!==undefined ? val+(e.unit?' '+e.unit:'') : '--'}</div>
                </div>
              `;
            }).join('')}
          </div>
          <div style="font-size:0.75rem;color:var(--text-dim);margin-bottom:10px">
            Empfang: <b>${(d.latest && d.latest._time) ? d.latest._time : (d.last_seen ? new Date(d.last_seen*1000).toLocaleTimeString() : 'Warte auf Signal...')}</b>
          </div>
          <!-- Funktionsleiste am unteren Rand -->
          <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:6px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.06)">
            <select class="form-input" style="width:auto;margin:0;padding:4px 6px;font-size:0.75rem" onchange="changeDeviceProfile('${d.id}', this.value)">
              <option value="thermo_hygro" ${currentProf==='thermo_hygro'?'selected':''}>Temp + Feuchte</option>
              <option value="thermo" ${currentProf==='thermo'?'selected':''}>Nur Temperatur</option>
              <option value="contact" ${currentProf==='contact'?'selected':''}>Tür-/Fensterkontakt</option>
            </select>
            <div style="display:flex;gap:6px">
              <button class="btn ${isEn ? 'btn-amber' : ''}" style="padding:4px 10px;font-size:0.75rem" onclick="toggleDevice('${d.id}')">
                ${isEn ? 'MQTT deregistrieren' : 'MQTT registrieren'}
              </button>
              <button class="btn btn-del" style="padding:4px 8px;font-size:0.75rem" onclick="deleteDevice('${d.id}')">Löschen</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }catch(e){}
}

async function changeDeviceProfile(id, profile){
  try{
    await fetch('/api/devices/profile', {
      method: 'POST',
      body: JSON.stringify({id: id, profile: profile})
    });
    refreshDevices();
  }catch(e){}
}

async function toggleDevice(id){
  try{
    let res = await fetch('/api/devices/toggle', {
      method: 'POST',
      body: JSON.stringify({id: id})
    });
    refreshDevices();
  }catch(e){}
}

async function delDevice(id){
  if(confirm('Gerät '+id+' wirklich löschen?')){
    await fetch('/api/devices?id='+id, {method:'DELETE'});
    refreshDevices();
  }
}

function deleteDevice(id){
  return delDevice(id);
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
        
        let devBadge = p.device_name ? `<span style="background:rgba(34,197,94,0.2);color:var(--green);padding:2px 8px;border-radius:12px;font-weight:600;font-size:0.75rem;margin-left:6px">✔ ${p.device_name}</span>` : '';
        let dataStr = Object.entries(p.data||{}).map(([k,v])=>`${k}: <b>${v}</b>`).join(' | ');
        
        let rawBtn = p.raw ? `<button class="btn" style="background:#475569;color:#fff" onclick='openRawModal(${JSON.stringify(p)})'>🔬 Rohdaten</button>` : '';
        let reassignBtn = p.proto!=='RAW_433' && p.proto!=='RAW_868_OOK' && p.proto!=='RAW_868_FSK' 
          ? `<button class="btn btn-amber" onclick="openReassign('${p.proto}','${p.id}','${p.channel||''}')">Zuordnen</button>
             <button class="btn" onclick='openAdoptModal(${JSON.stringify(p)})'>Neu anlernen</button>` 
          : '';

        div.innerHTML = `
          <div>
            <span style="color:var(--text-dim)">[${p.time}]</span> 
            <span style="color:var(--accent);font-weight:700">[${p.band}]</span> 
            <b>${p.proto}</b> 
            (ID: <code>${p.id}</code>${p.channel?' Ch:'+p.channel:''}) 
            ${devBadge}
            <span style="background:rgba(255,255,255,0.08);padding:2px 6px;border-radius:4px;font-size:0.75rem;margin-left:4px">${p.rssi} dBm</span>
            <div style="font-size:0.8rem;color:var(--text-dim);margin-top:4px">${dataStr||(p.raw ? 'Rohsignal ('+(Array.isArray(p.raw)?p.raw.length+' Pulse':p.raw.length+' Zeichen')+')' : 'Rohdaten')}</div>
          </div>
          <div style="display:flex;gap:6px">
            ${rawBtn}
            ${reassignBtn}
          </div>
        `;
        s.insertBefore(div, s.firstChild);
        if(s.children.length>50) s.removeChild(s.lastChild);
      });
    }catch(e){}
    setTimeout(poll, 1500);
  };
  poll();
}

function openRawModal(pkt){
  currentRawData = pkt;
  let isArr = Array.isArray(pkt.raw);
  let countInfo = isArr ? `${pkt.raw.length} Flanken / Pulse` : `${pkt.raw.length} Zeichen (Hex-Stream)`;
  document.getElementById('raw-modal-meta').innerHTML = `
    <b>Band:</b> ${pkt.band} | <b>Signal:</b> ${pkt.proto} | <b>RSSI:</b> ${pkt.rssi} dBm | <b>Länge:</b> ${countInfo}
  `;
  let ta = document.getElementById('raw-modal-text');
  if(isArr){
    ta.value = JSON.stringify(pkt.raw);
  } else {
    ta.value = pkt.raw || '';
  }
  document.getElementById('raw-modal').style.display = 'flex';
}

function closeRawModal(){
  document.getElementById('raw-modal').style.display = 'none';
  currentRawData = null;
}

function copyRaw(fmt){
  if(!currentRawData || !currentRawData.raw) return;
  let txt = '';
  if(fmt === 'json'){
    txt = JSON.stringify(currentRawData.raw);
  } else if(fmt === 'text'){
    if(Array.isArray(currentRawData.raw)){
      txt = currentRawData.raw.map(v => (v > 0 ? '+' : '') + v).join(' ');
    } else {
      txt = currentRawData.raw;
    }
  }
  navigator.clipboard.writeText(txt).then(()=>{
    alert('In die Zwischenablage kopiert (' + fmt.toUpperCase() + ')!');
  }).catch(()=>{
    prompt('Kopieren fehlgeschlagen. Hier manuell kopieren:', txt);
  });
}

function openAdoptModal(pkt){
  pendingAdoptPacket = pkt;
  document.getElementById('cfg-modal-info').innerHTML = `
    <b>Protokoll:</b> ${pkt.proto} | <b>Funk-ID:</b> <code>${pkt.id}</code> ${pkt.channel ? '| <b>Kanal:</b> '+pkt.channel : ''}
  `;
  document.getElementById('cfg-name').value = pkt.proto + ' ' + pkt.id;
  
  // Dynamische Entitätenerkennung aus pkt.data
  let listEl = document.getElementById('cfg-entities-list');
  listEl.innerHTML = '';
  
  let entries = Object.entries(pkt.data || {}).filter(([k,v]) => k !== 'channel' && k !== 'forced_send');
  if(!entries.length){
    entries = [['state', '1']];
  }
  
  entries.forEach(([key, val])=>{
    let unit = '';
    let devClass = 'sensor';
    let defName = key;
    
    if(key === 'temperature') { unit = '°C'; devClass = 'temperature'; defName = 'Temperatur'; }
    else if(key === 'humidity') { unit = '%'; devClass = 'humidity'; defName = 'Luftfeuchtigkeit'; }
    else if(key === 'battery_low') { unit = ''; devClass = 'battery'; defName = 'Batterie Status'; }
    else if(key === 'wind_speed') { unit = 'km/h'; devClass = 'wind_speed'; defName = 'Windgeschwindigkeit'; }
    else if(key === 'rain') { unit = 'mm'; devClass = 'precipitation'; defName = 'Niederschlag'; }
    else if(key === 'state' || key === 'contact') { unit = ''; devClass = 'door'; defName = 'Zustand'; }
    
    let row = document.createElement('div');
    row.className = 'cfg-ent-row';
    row.style = 'display:grid;grid-template-columns:24px 1fr 1fr 80px;gap:6px;align-items:center;background:rgba(255,255,255,0.02);padding:6px;border-radius:6px';
    row.innerHTML = `
      <input type="checkbox" checked class="ent-enable" data-key="${key}" style="width:16px;height:16px">
      <input type="text" class="ent-name form-input" style="margin:0;padding:4px 8px;font-size:0.8rem" value="${defName}" placeholder="Name">
      <input type="text" class="ent-unit form-input" style="margin:0;padding:4px 8px;font-size:0.8rem" value="${unit}" placeholder="Einheit">
      <select class="ent-class form-input" style="margin:0;padding:4px 4px;font-size:0.75rem">
        <option value="sensor" ${devClass!=='battery'?'selected':''}>Sensor</option>
        <option value="binary_sensor" ${devClass==='battery'?'selected':''}>Binär</option>
      </select>
    `;
    listEl.appendChild(row);
  });
  
  document.getElementById('config-modal').style.display = 'flex';
}

function closeConfigModal(){
  document.getElementById('config-modal').style.display = 'none';
  pendingAdoptPacket = null;
}

async function saveConfiguredDevice(){
  if(!pendingAdoptPacket) return;
  let name = document.getElementById('cfg-name').value.trim();
  if(!name) { alert('Bitte einen Namen angeben'); return; }
  
  let safeId = name.toLowerCase()
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]/g, '_');
  let isEnabled = document.getElementById('cfg-enabled').checked;
  
  let entities = [];
  document.querySelectorAll('.cfg-ent-row').forEach(row=>{
    let cb = row.querySelector('.ent-enable');
    if(cb && cb.checked){
      let key = cb.getAttribute('data-key');
      let entName = row.querySelector('.ent-name').value.trim() || key;
      let unit = row.querySelector('.ent-unit').value.trim();
      let cls = row.querySelector('.ent-class').value;
      let entObj = {key: key, name: entName, device_class: cls};
      if(unit) entObj.unit = unit;
      entities.push(entObj);
    }
  });
  
  let payload = {
    id: safeId,
    name: name,
    protocol: pendingAdoptPacket.proto,
    device_id: pendingAdoptPacket.id,
    channel: pendingAdoptPacket.channel ? parseInt(pendingAdoptPacket.channel) : null,
    type: 'sensor',
    enabled: isEnabled,
    entities: entities
  };
  
  await fetch('/api/devices', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  
  closeConfigModal();
  refreshDevices();
  alert('Gerät "'+name+'" wurde erfolgreich angelegt' + (isEnabled ? ' und für Home Assistant/MQTT freigegeben!' : ' (MQTT pausiert).'));
}

function openReassign(proto, id, ch){
  pendingReassign = {proto: proto, new_id: id, channel: ch?parseInt(ch):null};
  document.getElementById('modal-info').innerHTML = `Neues Signal: <b>${proto}</b> | Neue Funk-ID: <code>${id}</code> ${ch?'(Kanal '+ch+')':''}`;
  let sel = document.getElementById('modal-select');
  sel.innerHTML = knownDevices.map(d=>`<option value="${d.id}">${d.name} (${d.id})</option>`).join('');
  document.getElementById('reassign-modal').style.display = 'flex';
}

function closeModal(){
  document.getElementById('reassign-modal').style.display = 'none';
  pendingReassign = null;
}

async function executeReassign(){
  if(!pendingReassign) return;
  let ha_id = document.getElementById('modal-select').value;
  await fetch('/api/reassign', {
    method: 'POST',
    body: JSON.stringify({ha_id: ha_id, new_id: pendingReassign.new_id, channel: pendingReassign.channel})
  });
  closeModal();
  refreshDevices();
  alert('Funk-ID erfolgreich aktualisiert! Die Home Assistant Kurven laufen nahtlos weiter.');
}

function saveITDevice(){
  let name = document.getElementById('it-name').value;
  let fam = document.getElementById('it-family').value;
  let grp = parseInt(document.getElementById('it-group').value);
  let dev = parseInt(document.getElementById('it-device').value);
  let id = 'it_'+fam.toLowerCase()+'_'+grp+'_'+dev;
  fetch('/api/devices', {
    method:'POST',
    body: JSON.stringify({id: id, name: name, protocol:'IT', type:'switch', it_code:{family:fam, group:grp, device:dev}, icon:'mdi:power-socket-de', enabled:true})
  }).then(()=>{alert('Intertechno Schalter angelegt!'); refreshDevices();});
}

async function triggerGitHubOTA(){
  if(!confirm('GitHub OTA Update jetzt starten? Der Pico lädt die Dateien herunter und startet neu.')) return;
  let btn = document.getElementById('btn-ota');
  let st = document.getElementById('ota-status');
  btn.disabled = true;
  st.innerText = 'OTA Download läuft... Bitte ca. 10 Sekunden warten.';
  try{
    await fetch('/api/ota', {method:'POST'});
    st.innerText = 'Pico startet neu... Verbinde in 5s neu...';
    setTimeout(()=>{ location.reload(); }, 6000);
  }catch(e){
    st.innerText = 'Fehler beim Auslösen des OTA Updates.';
    btn.disabled = false;
  }
}

async function uploadFile(){
  let input = document.getElementById('file-upload-input');
  let st = document.getElementById('upload-status');
  if(!input.files || !input.files[0]){
    alert('Bitte zuerst eine Datei auswählen!');
    return;
  }
  let file = input.files[0];
  st.innerText = 'Lade ' + file.name + ' hoch...';
  try{
    let reader = new FileReader();
    reader.onload = async function(e){
      let content = e.target.result;
      let res = await fetch('/api/upload?filename='+encodeURIComponent(file.name), {
        method: 'POST',
        body: content
      });
      if(res.ok){
        st.innerText = 'Datei ' + file.name + ' erfolgreich geflasht!';
        alert('Datei erfolgreich hochgeladen!');
      } else {
        st.innerText = 'Fehler beim Hochladen.';
      }
    };
    reader.readAsArrayBuffer(file);
  }catch(e){
    st.innerText = 'Upload fehlgeschlagen: ' + e;
  }
}

async function uploadDevicesJson(){
  let input = document.getElementById('devices-upload-input');
  let st = document.getElementById('devices-upload-status');
  if(!input.files || !input.files[0]){
    alert('Bitte zuerst eine devices.json Datei auswählen!');
    return;
  }
  let file = input.files[0];
  if(!file.name.endsWith('.json')){
    alert('Bitte eine gültige .json Datei auswählen!');
    return;
  }
  st.innerText = 'Lade Geräte-Konfiguration hoch...';
  try{
    let reader = new FileReader();
    reader.onload = async function(e){
      let text = e.target.result;
      try{
        JSON.parse(text); // Validierungsprüfung
      }catch(err){
        alert('Ungültiges JSON-Format! Abbruch.');
        st.innerText = 'Fehler: Ungültiges JSON';
        return;
      }
      let res = await fetch('/api/upload?filename=devices.json', {
        method: 'POST',
        body: text
      });
      if(res.ok){
        st.innerText = 'Geräte erfolgreich wiederhergestellt & geladen!';
        refreshDevices();
        alert('Geräte-Konfiguration erfolgreich wiederhergestellt!');
      } else {
        st.innerText = 'Fehler beim Wiederherstellen.';
      }
    };
    reader.readAsText(file);
  }catch(e){
    st.innerText = 'Upload fehlgeschlagen: ' + e;
  }
}

refreshDevices();
updateSystem();
startSniffer();
setInterval(updateSystem, 5000);
setInterval(refreshDevices, 3000);
</script>
</body>
</html>
"""
