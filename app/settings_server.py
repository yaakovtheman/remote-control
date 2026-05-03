from flask import Flask, request, redirect, render_template_string, jsonify
import json, os, subprocess, sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
STATUS_PATH = os.path.join(APP_DIR, "status.json")


# If you run remote_pi_client as a systemd service, put the service name here:
SERVICE_NAME = "remote-pi-client"  # change to your actual systemd service name

def read_cfg():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def write_cfg(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)

def apply_mapping_defaults(cfg):
    cfg.setdefault("btn_speed_up", 2)
    cfg.setdefault("btn_speed_down", 1)
    cfg.setdefault("btn_park", 3)
    cfg.setdefault("btn_key_on", 5)
    cfg.setdefault("btn_key_start", 7)
    cfg.setdefault("btn_es", 6)
    cfg.setdefault("btn_impl", 4)
    cfg.setdefault("hat_speed_up_dir", 0)
    cfg.setdefault("hat_speed_down_dir", 1)
    cfg.setdefault("hat_impl_dir", 2)
    cfg.setdefault("hat_park_dir", 3)
    return cfg

def validate(cfg):
    # Keep it strict and safe.
    if not (1 <= int(cfg["send_hz"]) <= 60): return "send_hz must be 1..60"
    if not (0.0 <= float(cfg["deadzone"]) <= 0.5): return "deadzone must be 0..0.5"
    if not (1 <= int(cfg["server_port"]) <= 65535): return "server_port invalid"
    for k in ["axis_steer","axis_drive","axis_tilt","axis_lift"]:
        if not (0 <= int(cfg[k]) <= 10): return f"{k} must be 0..10"
    if not (0 <= int(cfg["btn_estop"]) <= 30): return "btn_estop must be 0..30"
    for k in ["btn_speed_up", "btn_speed_down", "btn_park", "btn_key_on", "btn_key_start", "btn_es", "btn_impl"]:
        if not (0 <= int(cfg[k]) <= 30): return f"{k} must be 0..30"
    for k in ["hat_speed_up_dir", "hat_speed_down_dir", "hat_impl_dir", "hat_park_dir"]:
        if not (-1 <= int(cfg[k]) <= 3): return f"{k} must be -1..3"
    return None

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pi Settings</title>
  <style>
    body {
      font-family: Arial;
      max-width: 900px;
      margin: 20px auto;
      padding: 0 12px;
      background: linear-gradient(180deg, #f8fbff 0%, #f6f8fc 100%);
      color: #0f172a;
    }
    .row { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:10px; }
    label { display:block; font-size: 13px; color:#333; margin-bottom:4px; }
    input[type=text], input[type=number] { width: 260px; padding: 8px; }
    .box {
      border: 1px solid #dbe3ef;
      padding: 14px;
      border-radius: 12px;
      margin-bottom: 14px;
      background: #ffffff;
      box-shadow: 0 6px 22px rgba(15, 23, 42, 0.05);
    }
    h2 { margin-bottom: 12px; }
    h3 { margin: 0 0 10px 0; color: #1d4ed8; }
    .err { color: #b00020; margin: 10px 0; }
    .ok { color: #0a7a0a; margin: 10px 0; }
    button {
      padding: 10px 14px;
      cursor: pointer;
      border-radius: 8px;
      border: 1px solid #bfdbfe;
      background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
      color: #1e3a8a;
      font-weight: 600;
      transition: transform .08s ease, box-shadow .15s ease;
    }
    button:hover { box-shadow: 0 4px 14px rgba(37, 99, 235, 0.2); }
    button:active { transform: translateY(1px); }
    .chips { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
    .chip {
      border: 1px solid #cfd8e7;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      background: #f8fafc;
      color: #334155;
      transition: all .15s ease;
    }
    .chip.active {
      background: linear-gradient(180deg, #dcfce7 0%, #bbf7d0 100%);
      border-color: #22c55e;
      color: #14532d;
      font-weight: 600;
      box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15);
    }
    .dpad {
      margin-top: 10px;
      display: grid;
      grid-template-columns: 38px 38px 38px;
      grid-template-rows: 38px 38px 38px;
      gap: 5px;
      align-items: center;
      justify-content: start;
    }
    .dpad .dir {
      border: 1px solid #d1d5db;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      background: #f3f4f6;
      color: #4b5563;
    }
    .dpad .dir.active {
      background: #dbeafe;
      border-color: #3b82f6;
      color: #1d4ed8;
      font-weight: 700;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.14);
    }
    .axis-grid {
      margin-top: 10px;
      display: grid;
      grid-template-columns: repeat(2, minmax(160px, 1fr));
      gap: 8px;
    }
    .axis-box {
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 8px;
      font-size: 12px;
      background: #fafafa;
    }
    .axis-box b { display: block; margin-bottom: 4px; font-size: 12px; }
    .muted { opacity: 0.75; font-size: 12px; }
    select { padding: 8px; }
    .mapper-row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:8px; }
    .pill {
      display: inline-block;
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      padding: 5px 9px;
      margin: 4px 6px 0 0;
      font-size: 12px;
      background: #f8fafc;
    }
    .last-pressed {
      min-width: 84px;
      text-align: center;
      font-weight: 700;
      color: #1e3a8a;
      background: linear-gradient(180deg, #dbeafe 0%, #bfdbfe 100%);
      border-color: #93c5fd;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
    }
    .last-pressed.flash {
      animation: pulsePress .35s ease;
    }
    @keyframes pulsePress {
      0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.45); }
      60% { transform: scale(1.06); box-shadow: 0 0 0 10px rgba(59, 130, 246, 0.0); }
      100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.0); }
    }
    .btn-mapper { margin-top: 10px; }
    .btn-map-row {
      display: grid;
      grid-template-columns: 100px 220px;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
      padding: 6px 8px;
      border-radius: 8px;
      background: #f8fbff;
      border: 1px solid #e2e8f0;
    }
  </style>
</head>
<body>
  <h2>Remote Pi Client Settings</h2>

  {% if msg %}<div class="{{ cls }}">{{ msg }}</div>{% endif %}

  <div class="box">
  <h3>Live Status</h3>

  <div style="display:flex; gap:18px; flex-wrap:wrap; align-items:center;">
    <div style="display:flex; align-items:center; gap:8px;">
      <span id="tcpDot" style="width:12px;height:12px;border-radius:50%;background:#999;display:inline-block;"></span>
      <span id="tcpText">TCP: …</span>
    </div>

    <div style="display:flex; align-items:center; gap:8px;">
      <span id="joyDot" style="width:12px;height:12px;border-radius:50%;background:#999;display:inline-block;"></span>
      <span id="joyText">Remote: …</span>
    </div>

    <div id="serverText" style="opacity:0.85;"></div>
  </div>

  <div id="errText" style="margin-top:8px; color:#b00020;"></div>
  <div id="cmdText" style="margin-top:8px; font-family:monospace;"></div>
  <div id="inputText" style="margin-top:8px; font-family:monospace; white-space:pre-wrap;"></div>
</div>

<script>
let cachedCfg = null;
let lastCfgFetch = 0;
let mapperInitialized = false;
let lastPressedButton = null;
let prevPressedButtons = new Set();
const knownButtons = new Set([0,1,2,3,4,5,6,7,11,12,13,14]);
let lastMapperSignature = '';
const actionDefs = [
  {field: 'btn_speed_up', label: 'SPEED_UP'},
  {field: 'btn_speed_down', label: 'SPEED_DOWN'},
  {field: 'btn_park', label: 'PARK'},
  {field: 'btn_impl', label: 'IMPLEMENT'},
  {field: 'btn_key_on', label: 'KEY_ON'},
  {field: 'btn_key_start', label: 'KEY_START'},
  {field: 'btn_es', label: 'ES'},
];

async function getCfg(){
  const now = Date.now();
  if (!cachedCfg || (now - lastCfgFetch) > 5000){
    cachedCfg = await (await fetch('/api/config', {cache:'no-store'})).json();
    lastCfgFetch = now;
  }
  return cachedCfg;
}

function setLastPressed(btn){
  if (btn === null || btn === undefined) return;
  lastPressedButton = Number(btn);
  const txt = document.getElementById('lastPressedText');
  if (txt){
    txt.innerText = 'B' + lastPressedButton;
    txt.classList.remove('flash');
    void txt.offsetWidth;
    txt.classList.add('flash');
  }
}

function syncHiddenMappingFromCfg(cfg){
  for (const a of actionDefs){
    const el = document.getElementById('input-' + a.field);
    if (el) el.value = String(cfg[a.field]);
  }
}

function readHiddenMapping(){
  const out = {};
  for (const a of actionDefs){
    const el = document.getElementById('input-' + a.field);
    out[a.field] = el ? Number(el.value) : 0;
  }
  return out;
}

function renderActionAssignments(){
  const wrap = document.getElementById('actionAssignments');
  if (!wrap) return;
  const mapping = readHiddenMapping();
  const pills = actionDefs.map(a => {
    const btn = mapping[a.field];
    return '<span class="pill">' + a.label + ' -> B' + btn + '</span>';
  });
  wrap.innerHTML = pills.join('');
}

function getButtonToActionMap(){
  const mapping = readHiddenMapping();
  const out = {};
  for (const a of actionDefs){
    const btn = Number(mapping[a.field]);
    if (Number.isFinite(btn) && btn > 0) out[btn] = a.field;
  }
  return out;
}

function actionOptionsHtml(selectedField){
  let html = '<option value="">(none)</option>';
  for (const a of actionDefs){
    const sel = selectedField === a.field ? ' selected' : '';
    html += '<option value="' + a.field + '"' + sel + '>' + a.label + '</option>';
  }
  return html;
}

function setHiddenMapping(mapping){
  for (const a of actionDefs){
    const el = document.getElementById('input-' + a.field);
    if (el) el.value = String(mapping[a.field] ?? 0);
  }
}

function onButtonActionChange(button, actionField){
  const mapping = readHiddenMapping();
  for (const a of actionDefs){
    if (Number(mapping[a.field]) === button) mapping[a.field] = 0;
  }
  if (actionField) mapping[actionField] = button;
  setHiddenMapping(mapping);
  renderActionAssignments();
  renderButtonMapper(true);
}

function renderButtonMapper(force){
  const wrap = document.getElementById('buttonMapperRows');
  if (!wrap) return;
  const sorted = Array.from(knownButtons).sort((a, b) => a - b);
  const reverse = getButtonToActionMap();
  const sig = JSON.stringify(sorted) + '|' + JSON.stringify(readHiddenMapping());
  if (!force && sig === lastMapperSignature) return;
  lastMapperSignature = sig;

  wrap.innerHTML = sorted.map((btn) => {
    const selected = reverse[btn] || '';
    return (
      '<div class="btn-map-row">' +
      '<div><b>B' + btn + '</b></div>' +
      '<div><select class="button-action-select" data-button="' + btn + '">' +
      actionOptionsHtml(selected) +
      '</select></div>' +
      '</div>'
    );
  }).join('');

  wrap.querySelectorAll('.button-action-select').forEach((el) => {
    el.addEventListener('change', (ev) => {
      const btn = Number(ev.target.getAttribute('data-button'));
      onButtonActionChange(btn, ev.target.value);
    });
  });
}

function initMapper(cfg){
  if (mapperInitialized) return;
  mapperInitialized = true;
  syncHiddenMappingFromCfg(cfg);
  for (const a of actionDefs) knownButtons.add(Number(cfg[a.field]));
  renderActionAssignments();
  renderButtonMapper(true);
}

async function refreshStatus(){
  try{
    const r = await fetch('/api/status', {cache:'no-store'});
    const s = await r.json();

    const tcpOk = !!s.tcp_connected;
    const joyOk = !!s.joystick_connected;

    document.getElementById('tcpDot').style.background = tcpOk ? '#16a34a' : '#dc2626';
    document.getElementById('joyDot').style.background = joyOk ? '#16a34a' : '#dc2626';

    document.getElementById('tcpText').innerText = 'TCP: ' + (tcpOk ? 'Connected' : 'Not connected');
    document.getElementById('joyText').innerText = 'Remote: ' + (joyOk ? (s.joystick_name || 'Connected') : 'Not connected');

    document.getElementById('serverText').innerText = s.server ? ('Target: ' + s.server) : '';

    const err = (!tcpOk && s.tcp_error) ? ('Error: ' + s.tcp_error) : '';
    document.getElementById('errText').innerText = err;
    document.getElementById('cmdText').innerText = s.last_command ? ('Last: ' + s.last_command) : '';
    document.getElementById('inputText').innerText = s.inputs ? (
      'Buttons pressed: ' + JSON.stringify(s.inputs.buttons_pressed || []) + '\\n' +
      'Hat: ' + JSON.stringify(s.inputs.hat) + '\\n' +
      'Axes raw: ' + JSON.stringify(s.inputs.axes_raw || []) + '\\n' +
      'Mapped axes: ' + JSON.stringify(s.inputs.axes_mapped || {}) + '\\n' +
      'Button mask: ' + (s.inputs.buttons_mask ?? '')
    ) : '';

    const cfg = await getCfg();
    initMapper(cfg);
    const inp = s.inputs || {};
    const pressed = new Set(inp.buttons_pressed || []);
    for (const b of pressed) knownButtons.add(Number(b));
    const newlyPressed = Array.from(pressed).filter(b => !prevPressedButtons.has(b));
    if (newlyPressed.length > 0) setLastPressed(newlyPressed[newlyPressed.length - 1]);
    prevPressedButtons = pressed;
    renderButtonMapper(false);

  }catch(e){
    document.getElementById('tcpText').innerText = 'TCP: status error';
    document.getElementById('joyText').innerText = 'Remote: status error';
  }
}
setInterval(refreshStatus, 150);
refreshStatus();
</script>


  <form method="post">
    <div class="box">
      <h3>TCP</h3>
      <div class="row">
        <div>
          <label>Server IP</label>
          <input type="text" name="server_ip" value="{{cfg.server_ip}}">
        </div>
        <div>
          <label>Server Port</label>
          <input type="number" name="server_port" value="{{cfg.server_port}}">
        </div>
      </div>
    </div>

    <div class="box">
      <h3>Timing</h3>
      <div class="row">
        <div>
          <label>SEND_HZ (1..60)</label>
          <input type="number" name="send_hz" value="{{cfg.send_hz}}">
        </div>
        <div>
          <label>DEADZONE (0..0.5)</label>
          <input type="number" step="0.01" name="deadzone" value="{{cfg.deadzone}}">
        </div>
      </div>
    </div>

    <div class="box">
      <h3>Joystick Mapping</h3>
      <div class="row">
        <div><label>AXIS_STEER</label><input type="number" name="axis_steer" value="{{cfg.axis_steer}}"></div>
        <div><label>AXIS_DRIVE</label><input type="number" name="axis_drive" value="{{cfg.axis_drive}}"></div>
        <div><label>AXIS_TILT</label><input type="number" name="axis_tilt" value="{{cfg.axis_tilt}}"></div>
        <div><label>AXIS_LIFT</label><input type="number" name="axis_lift" value="{{cfg.axis_lift}}"></div>
      </div>

      <div class="row">
        <label><input type="checkbox" name="invert_steer" {% if cfg.invert_steer %}checked{% endif %}> invert steer</label>
        <label><input type="checkbox" name="invert_drive" {% if cfg.invert_drive %}checked{% endif %}> invert drive</label>
        <label><input type="checkbox" name="invert_tilt" {% if cfg.invert_tilt %}checked{% endif %}> invert tilt</label>
        <label><input type="checkbox" name="invert_lift" {% if cfg.invert_lift %}checked{% endif %}> invert lift</label>
      </div>

      <div class="row">
        <div>
          <label>BTN_ESTOP</label>
          <input type="number" name="btn_estop" value="{{cfg.btn_estop}}">
        </div>
      </div>
    </div>

    <div class="box">
      <h3>Action Mapping (Buttons)</h3>
      <p style="margin-top:0; opacity:0.8;">Each physical button gets a dropdown. Pick the action directly on that row.</p>
      <div class="mapper-row">
        <div>
          <label>Last pressed</label>
          <div id="lastPressedText" class="pill last-pressed">none</div>
        </div>
      </div>
      <div id="buttonMapperRows" class="btn-mapper"></div>
      <div id="actionAssignments" style="margin-top:10px;"></div>

      <input type="hidden" id="input-btn_speed_up" name="btn_speed_up" value="{{cfg.btn_speed_up}}">
      <input type="hidden" id="input-btn_speed_down" name="btn_speed_down" value="{{cfg.btn_speed_down}}">
      <input type="hidden" id="input-btn_park" name="btn_park" value="{{cfg.btn_park}}">
      <input type="hidden" id="input-btn_key_on" name="btn_key_on" value="{{cfg.btn_key_on}}">
      <input type="hidden" id="input-btn_key_start" name="btn_key_start" value="{{cfg.btn_key_start}}">
      <input type="hidden" id="input-btn_es" name="btn_es" value="{{cfg.btn_es}}">
      <input type="hidden" id="input-btn_impl" name="btn_impl" value="{{cfg.btn_impl}}">
    </div>

    <div class="box">
      <h3>Action Mapping (D-pad / Hat)</h3>
      <p style="margin-top:0; opacity:0.8;">Direction values: -1=disabled, 0=up, 1=down, 2=right, 3=left.</p>
      <div class="row">
        <div><label>SPEED_UP direction</label><input type="number" name="hat_speed_up_dir" value="{{cfg.hat_speed_up_dir}}"></div>
        <div><label>SPEED_DOWN direction</label><input type="number" name="hat_speed_down_dir" value="{{cfg.hat_speed_down_dir}}"></div>
      </div>
      <div class="row">
        <div><label>IMPLEMENT direction</label><input type="number" name="hat_impl_dir" value="{{cfg.hat_impl_dir}}"></div>
        <div><label>PARK direction</label><input type="number" name="hat_park_dir" value="{{cfg.hat_park_dir}}"></div>
      </div>
    </div>

    <button type="submit" name="action" value="save">Save</button>
    <button type="submit" name="action" value="save_restart">Save + Restart Client</button>
  </form>

  <hr />
  <p>Tip: open this page from your computer: <b>http://PI_IP:8088</b></p>
</body>
</html>
"""

@app.get("/")
def index():
    cfg = apply_mapping_defaults(read_cfg())
    return render_template_string(HTML, cfg=cfg, msg=None, cls=None)

@app.post("/")
def save():
    cfg = apply_mapping_defaults(read_cfg())

    # Update from form
    cfg["server_ip"] = request.form.get("server_ip", cfg["server_ip"]).strip()
    cfg["server_port"] = int(request.form.get("server_port", cfg["server_port"]))
    cfg["send_hz"] = int(request.form.get("send_hz", cfg["send_hz"]))
    cfg["deadzone"] = float(request.form.get("deadzone", cfg["deadzone"]))

    cfg["axis_steer"] = int(request.form.get("axis_steer", cfg["axis_steer"]))
    cfg["axis_drive"] = int(request.form.get("axis_drive", cfg["axis_drive"]))
    cfg["axis_tilt"] = int(request.form.get("axis_tilt", cfg["axis_tilt"]))
    cfg["axis_lift"] = int(request.form.get("axis_lift", cfg["axis_lift"]))

    cfg["invert_steer"] = "invert_steer" in request.form
    cfg["invert_drive"] = "invert_drive" in request.form
    cfg["invert_tilt"] = "invert_tilt" in request.form
    cfg["invert_lift"] = "invert_lift" in request.form

    cfg["btn_estop"] = int(request.form.get("btn_estop", cfg["btn_estop"]))
    cfg["btn_speed_up"] = int(request.form.get("btn_speed_up", cfg["btn_speed_up"]))
    cfg["btn_speed_down"] = int(request.form.get("btn_speed_down", cfg["btn_speed_down"]))
    cfg["btn_park"] = int(request.form.get("btn_park", cfg["btn_park"]))
    cfg["btn_key_on"] = int(request.form.get("btn_key_on", cfg["btn_key_on"]))
    cfg["btn_key_start"] = int(request.form.get("btn_key_start", cfg["btn_key_start"]))
    cfg["btn_es"] = int(request.form.get("btn_es", cfg["btn_es"]))
    cfg["btn_impl"] = int(request.form.get("btn_impl", cfg["btn_impl"]))
    cfg["hat_speed_up_dir"] = int(request.form.get("hat_speed_up_dir", cfg["hat_speed_up_dir"]))
    cfg["hat_speed_down_dir"] = int(request.form.get("hat_speed_down_dir", cfg["hat_speed_down_dir"]))
    cfg["hat_impl_dir"] = int(request.form.get("hat_impl_dir", cfg["hat_impl_dir"]))
    cfg["hat_park_dir"] = int(request.form.get("hat_park_dir", cfg["hat_park_dir"]))

    err = validate(cfg)
    if err:
        return render_template_string(HTML, cfg=cfg, msg=err, cls="err"), 400

    write_cfg(cfg)

    action = request.form.get("action")
    if action == "save_restart":
        if sys.platform.startswith("linux"):
            subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME], check=False)
            return render_template_string(HTML, cfg=cfg, msg="Saved and restarted.", cls="ok")
        return render_template_string(
            HTML,
            cfg=cfg,
            msg="Saved. Restart the joystick / remote client manually to apply settings (automatic restart uses systemd on Linux only).",
            cls="ok",
        )

    return render_template_string(HTML, cfg=cfg, msg="Saved.", cls="ok")

@app.get("/api/config")
def api_config():
    return jsonify(apply_mapping_defaults(read_cfg()))

@app.get("/api/status")
def api_status():
    try:
        with open(STATUS_PATH, "r") as f:
            return jsonify(json.load(f))
    except:
        return jsonify({"tcp_connected": False, "joystick_connected": False, "tcp_error": "no status yet"})

@app.get("/api/inputs")
def api_inputs():
    try:
        with open(STATUS_PATH, "r") as f:
            s = json.load(f)
        return jsonify(s.get("inputs") or {})
    except:
        return jsonify({})


if __name__ == "__main__":
    # Listen on the LAN so your computer can access it
    app.run(host="0.0.0.0", port=8088)
