from flask import Flask, request, redirect, render_template_string, jsonify
import json, os, subprocess

APP_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
STATUS_PATH = os.path.join(os.path.dirname(__file__), "status.json")


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

def validate(cfg):
    # Keep it strict and safe.
    if not (1 <= int(cfg["send_hz"]) <= 60): return "send_hz must be 1..60"
    if not (0.0 <= float(cfg["deadzone"]) <= 0.5): return "deadzone must be 0..0.5"
    if not (1 <= int(cfg["server_port"]) <= 65535): return "server_port invalid"
    for k in ["axis_steer","axis_drive","axis_tilt","axis_lift"]:
        if not (0 <= int(cfg[k]) <= 10): return f"{k} must be 0..10"
    if not (0 <= int(cfg["btn_estop"]) <= 30): return "btn_estop must be 0..30"
    return None

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pi Settings</title>
  <style>
    body { font-family: Arial; max-width: 820px; margin: 20px auto; padding: 0 12px; }
    .row { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:10px; }
    label { display:block; font-size: 13px; color:#333; margin-bottom:4px; }
    input[type=text], input[type=number] { width: 260px; padding: 8px; }
    .box { border:1px solid #ddd; padding: 14px; border-radius: 10px; margin-bottom: 14px; }
    .err { color: #b00020; margin: 10px 0; }
    .ok { color: #0a7a0a; margin: 10px 0; }
    button { padding: 10px 14px; cursor:pointer; }
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
</div>

<script>
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

  }catch(e){
    document.getElementById('tcpText').innerText = 'TCP: status error';
    document.getElementById('joyText').innerText = 'Remote: status error';
  }
}
setInterval(refreshStatus, 1000);
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
    cfg = read_cfg()
    return render_template_string(HTML, cfg=cfg, msg=None, cls=None)

@app.post("/")
def save():
    cfg = read_cfg()

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

    err = validate(cfg)
    if err:
        return render_template_string(HTML, cfg=cfg, msg=err, cls="err"), 400

    write_cfg(cfg)

    action = request.form.get("action")
    if action == "save_restart":
        # simplest apply method
        subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME], check=False)
        return render_template_string(HTML, cfg=cfg, msg="Saved and restarted.", cls="ok")

    return render_template_string(HTML, cfg=cfg, msg="Saved.", cls="ok")

@app.get("/api/config")
def api_config():
    return jsonify(read_cfg())

@app.get("/api/status")
def api_status():
    try:
        with open(STATUS_PATH, "r") as f:
            return jsonify(json.load(f))
    except:
        return jsonify({"tcp_connected": False, "joystick_connected": False, "tcp_error": "no status yet"})


if __name__ == "__main__":
    # Listen on the LAN so your computer can access it
    app.run(host="0.0.0.0", port=8088)
