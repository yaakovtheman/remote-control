# remote_pi_client.py
import socket, time, pygame, sys
import json, os
import signal

STATUS_PATH = os.path.join(os.path.dirname(__file__), "status.json")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

RUNNING = True

def write_status(obj: dict, retries: int = 5, delay: float = 0.05):
    tmp = STATUS_PATH + ".tmp"

    for attempt in range(retries):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp, STATUS_PATH)
            return True

        except PermissionError as e:
            # Windows may fail here if another process is reading status.json
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            print(f"[warn] status write permission error: {e}")
            return False

        except Exception as e:
            print(f"[warn] status write failed: {e}")
            return False

        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

def handle_exit(sig, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

cfg = load_config()

def cfg_int(key, default):
    try:
        return int(cfg.get(key, default))
    except Exception:
        return int(default)

SERVER_IP      = cfg["server_ip"]
SERVER_PORT    = int(cfg["server_port"])
SEND_HZ        = int(cfg["send_hz"])
DEADZONE       = float(cfg["deadzone"])

AXIS_STEER  = int(cfg["axis_steer"])
AXIS_DRIVE  = int(cfg["axis_drive"])   # legacy; no longer used for drive direction
AXIS_TILT   = int(cfg["axis_tilt"])
AXIS_LIFT   = int(cfg["axis_lift"])

INVERT_STEER = bool(cfg["invert_steer"])
INVERT_DRIVE = bool(cfg["invert_drive"])
INVERT_TILT  = bool(cfg["invert_tilt"])
INVERT_LIFT  = bool(cfg["invert_lift"])

# Throttle axis (trigger). -1 = not yet configured.
# throttle_rest: raw axis value when trigger is fully released (SDL2 Xbox RT rests at -1.0).
AXIS_THROTTLE   = cfg_int("axis_throttle", -1)
INVERT_THROTTLE = bool(cfg.get("invert_throttle", False))
THROTTLE_REST   = float(cfg.get("throttle_rest", -1.0))

BTN_ESTOP      = cfg_int("btn_estop", 0)
BTN_SPDUP_IN   = cfg_int("btn_speed_up", 2)
BTN_SPDDN_IN   = cfg_int("btn_speed_down", 1)
BTN_PARK_IN    = cfg_int("btn_park", 3)
BTN_KEYON_IN   = cfg_int("btn_key_on", 5)
BTN_KEYSTART_IN = cfg_int("btn_key_start", 7)
BTN_ES_IN      = cfg_int("btn_es", 6)
BTN_IMPL_IN    = cfg_int("btn_impl", 4)

# Gear-select buttons. -1 = not yet configured.
# Gear-Up:   PARK→DRIVE,  DRIVE→DRIVE,   REVERSE→PARK
# Gear-Down: DRIVE→PARK,  PARK→REVERSE,  REVERSE→REVERSE
BTN_GEAR_UP_IN = cfg_int("btn_gear_up", -1)
BTN_GEAR_DN_IN = cfg_int("btn_gear_dn", -1)

# -1 disables the mapping.
HAT_SPDUP_DIR  = cfg_int("hat_speed_up_dir", 0)    # 0=up,1=down,2=right,3=left
HAT_SPDDN_DIR  = cfg_int("hat_speed_down_dir", 1)
HAT_IMPL_DIR   = cfg_int("hat_impl_dir", 2)
HAT_PARK_DIR   = cfg_int("hat_park_dir", 3)

if "--ip" in sys.argv:
    SERVER_IP = sys.argv[sys.argv.index("--ip") + 1]
print(f"[cfg] using {SERVER_IP}")

# ==== Button bitmask (must match Arduino) ====
BTN_PARK      = 1 << 0
BTN_IMPL      = 1 << 1
BTN_SPDUP     = 1 << 2
BTN_SPDDN     = 1 << 3
BTN_KEYON     = 1 << 4
BTN_KEYSTART  = 1 << 5
BTN_ES        = 1 << 6

# ==== Gear state (client-side) ====
GEAR_PARK    = 0
GEAR_DRIVE   = 1
GEAR_REVERSE = 2
GEAR_NAMES   = {GEAR_PARK: "PARK", GEAR_DRIVE: "DRIVE", GEAR_REVERSE: "REVERSE"}

_gear_state       = GEAR_PARK
_gear_up_prev     = False   # last-frame state of gear-up button (rising-edge detection)
_gear_dn_prev     = False
# Throttle lockout: True until trigger returns to rest after a gear change.
_throttle_must_release = False

# ==== Speed button pulse state machine ====
# Each physical press queues one pulse: HIGH for _SPD_HIGH_FRAMES, then LOW for
# _SPD_LOW_FRAMES. The LOW gap ensures the Arduino sees a falling edge before the
# next press, so N rapid clicks produce N distinct rising edges.
_SPD_HIGH_FRAMES = 2   # at 20 Hz: 2 × 50 ms = 100 ms HIGH
_SPD_LOW_FRAMES  = 1   # 1 × 50 ms LOW gap between pulses
_SPD_QUEUE_MAX   = 8   # ignore unreasonably large bursts

_spd_up_queue = 0
_spd_dn_queue = 0
_spd_up_state = 'idle'  # 'idle' | 'high' | 'low'
_spd_up_left  = 0
_spd_dn_state = 'idle'
_spd_dn_left  = 0
_hat_prev_xy  = (0, 0)
_spdup_prev   = False   # previous frame button state for rising-edge detection
_spddn_prev   = False


def _spd_tick(queue, state, left):
    """Advance speed-pulse state machine one frame.
    Returns (bit_active, new_queue, new_state, new_left)."""
    if state == 'idle':
        if queue > 0:
            return True, queue - 1, 'high', _SPD_HIGH_FRAMES - 1
        return False, 0, 'idle', 0
    if state == 'high':
        if left > 0:
            return True, queue, 'high', left - 1
        return False, queue, 'low', _SPD_LOW_FRAMES - 1
    # state == 'low'
    if left > 0:
        return False, queue, 'low', left - 1
    if queue > 0:
        return True, queue - 1, 'high', _SPD_HIGH_FRAMES - 1
    return False, 0, 'idle', 0


def throttle_to_0_1023(raw):
    """Normalize a trigger axis value to 0..1023 (0 = idle, 1023 = full press).

    THROTTLE_REST is the raw axis value when the trigger is fully released
    (typically -1.0 for SDL2 Xbox triggers). The span from rest to +1.0 is
    the usable range. Returns 0 when the axis is at or below rest.
    """
    span = 1.0 - THROTTLE_REST
    if span <= 0:
        return 0
    norm = (raw - THROTTLE_REST) / span   # 0.0 (idle) → 1.0 (full)
    if INVERT_THROTTLE:
        norm = 1.0 - norm
    norm = max(0.0, min(1.0, norm))
    if norm < DEADZONE:
        norm = 0.0
    return int(round(norm * 1023))


def reset_gear():
    """Reset gear to PARK and clear throttle lockout. Call on (re)connect."""
    global _gear_state, _gear_up_prev, _gear_dn_prev, _throttle_must_release
    _gear_state            = GEAR_PARK
    _gear_up_prev          = False
    _gear_dn_prev          = False
    _throttle_must_release = False


def reset_spd_queues():
    global _spd_up_queue, _spd_dn_queue
    global _spd_up_state, _spd_dn_state
    global _spd_up_left, _spd_dn_left
    global _hat_prev_xy, _spdup_prev, _spddn_prev
    _spd_up_queue = _spd_dn_queue = 0
    _spd_up_state = _spd_dn_state = 'idle'
    _spd_up_left = _spd_dn_left = 0
    _hat_prev_xy = (0, 0)
    _spdup_prev = _spddn_prev = False


def _hat_matches(hx, hy, direction):
    if direction == 0: return hy > 0
    if direction == 1: return hy < 0
    if direction == 2: return hx > 0
    if direction == 3: return hx < 0
    return False


def _hat_spd_enqueue(hx, hy):
    """Queue one speed pulse when hat transitions to a speed direction."""
    global _hat_prev_xy, _spd_up_queue, _spd_dn_queue
    px, py = _hat_prev_xy
    if HAT_SPDUP_DIR >= 0:
        if _hat_matches(hx, hy, HAT_SPDUP_DIR) and not _hat_matches(px, py, HAT_SPDUP_DIR):
            if _spd_up_queue < _SPD_QUEUE_MAX:
                _spd_up_queue += 1
    if HAT_SPDDN_DIR >= 0:
        if _hat_matches(hx, hy, HAT_SPDDN_DIR) and not _hat_matches(px, py, HAT_SPDDN_DIR):
            if _spd_dn_queue < _SPD_QUEUE_MAX:
                _spd_dn_queue += 1
    _hat_prev_xy = (hx, hy)


# ==== Helpers ====
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def apply_deadzone(x, dz=DEADZONE):
    return 0.0 if abs(x) < dz else x

def axis_to_0_1023(val, invert=False):
    # pygame axis: -1..1 -> 0..1023
    v = -val if invert else val
    v = clamp(v, -1.0, 1.0)
    v = (v + 1.0) * 0.5
    return int(round(v * 1023))

def _try_connect_tcp():
    """Single non-blocking TCP attempt. Returns (socket, None) or (None, error_str)."""
    try:
        s = socket.create_connection((SERVER_IP, SERVER_PORT), timeout=1.0)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        local_ip = cfg.get("mediamtx_host") or s.getsockname()[0]
        s.sendall(f"HOST {local_ip}\n".encode())
        print(f"[tcp] connected (mediamtx host: {local_ip})")
        return s, None
    except Exception as e:
        print(f"[tcp] connect failed: {e}")
        return None, str(e)

def init_joystick():
    # Re-scan joysticks
    try:
        pygame.joystick.quit()
        pygame.joystick.init()
        n = pygame.joystick.get_count()
        if n <= 0:
            return None
        js = pygame.joystick.Joystick(0)
        js.init()
        print(f"[joy] {js.get_name()} ready ({js.get_numaxes()} axes, {js.get_numbuttons()} buttons)")
        return js
    except Exception as e:
        print(f"[joy] init failed: {e}")
        return None

def joystick_present_now():
    # This is the only reliable "is it plugged" signal we have in pygame.
    try:
        pygame.joystick.init()
        return pygame.joystick.get_count() > 0
    except Exception:
        return False

def safe_read_inputs(js, conn_start_ms=None):
    """
    Returns (line_bytes, ok, joy_name, inputs)
    ok=False means joystick is gone/broken.
    conn_start_ms: int(time.time()*1000) at the moment the TCP socket connected.
    When provided, SET commands carry ms-elapsed-since-connect so the Pi can
    detect stale buffered commands without requiring clock sync.
    """
    try:
        global _spd_up_queue, _spd_dn_queue, _spd_up_state, _spd_dn_state, _spd_up_left, _spd_dn_left
        global _spdup_prev, _spddn_prev
        global _gear_state, _gear_up_prev, _gear_dn_prev, _throttle_must_release

        # pump() keeps SDL's internal state fresh without draining the event queue.
        # event.get() was previously used here but caused SDL2 on macOS to surface
        # JOYDEVICEREMOVED events (IOKit re-enumeration), which invalidated the
        # joystick handle and produced spurious STOP commands.
        pygame.event.pump()

        steer_raw = js.get_axis(AXIS_STEER)
        tilt_raw  = js.get_axis(AXIS_TILT)
        lift_raw  = js.get_axis(AXIS_LIFT)

        steer_raw = apply_deadzone(steer_raw)
        tilt_raw  = apply_deadzone(tilt_raw)
        lift_raw  = apply_deadzone(lift_raw)

        steer = axis_to_0_1023(steer_raw, INVERT_STEER)
        tilt  = axis_to_0_1023(tilt_raw,  INVERT_TILT)
        lift  = axis_to_0_1023(lift_raw,  INVERT_LIFT)

        # --- Throttle (right trigger) ---
        if AXIS_THROTTLE >= 0 and AXIS_THROTTLE < js.get_numaxes():
            throttle_raw = js.get_axis(AXIS_THROTTLE)
        else:
            throttle_raw = THROTTLE_REST  # axis not configured or out of range → no throttle

        throttle_norm_raw = throttle_to_0_1023(throttle_raw)

        # Throttle lockout: once cleared (trigger at rest after gear change), allow throttle.
        # A trigger reading of 0 means it is at rest — clear the lockout flag here.
        if throttle_norm_raw == 0:
            _throttle_must_release = False

        throttle = 0 if _throttle_must_release else throttle_norm_raw

        # --- Gear state machine (rising-edge on gear-up / gear-dn buttons) ---
        gear_up_now = (BTN_GEAR_UP_IN >= 0
                       and BTN_GEAR_UP_IN < js.get_numbuttons()
                       and bool(js.get_button(BTN_GEAR_UP_IN)))
        gear_dn_now = (BTN_GEAR_DN_IN >= 0
                       and BTN_GEAR_DN_IN < js.get_numbuttons()
                       and bool(js.get_button(BTN_GEAR_DN_IN)))

        if gear_up_now and not _gear_up_prev:
            # REVERSE→PARK, PARK→DRIVE, DRIVE stays DRIVE
            if _gear_state == GEAR_REVERSE:
                _gear_state = GEAR_PARK
            elif _gear_state == GEAR_PARK:
                _gear_state = GEAR_DRIVE
            _throttle_must_release = True  # require trigger release before throttle resumes

        if gear_dn_now and not _gear_dn_prev:
            # DRIVE→PARK, PARK→REVERSE, REVERSE stays REVERSE
            if _gear_state == GEAR_DRIVE:
                _gear_state = GEAR_PARK
            elif _gear_state == GEAR_PARK:
                _gear_state = GEAR_REVERSE
            _throttle_must_release = True

        _gear_up_prev = gear_up_now
        _gear_dn_prev = gear_dn_now

        # --- E-STOP ---
        nbtns = js.get_numbuttons()
        if BTN_ESTOP < nbtns and js.get_button(BTN_ESTOP) == 1:
            reset_spd_queues()
            return b"STOP\n", True, js.get_name(), {
                "estop_pressed": True,
                "hat": js.get_hat(0) if js.get_numhats() > 0 else None,
                "buttons_pressed": [i for i in range(js.get_numbuttons()) if js.get_button(i)],
                "axes_raw": [round(js.get_axis(i), 3) for i in range(min(8, js.get_numaxes()))],
            }

        buttons = 0

        # Rising-edge detection for speed buttons via state polling.
        spdup_now = 0 <= BTN_SPDUP_IN < nbtns and bool(js.get_button(BTN_SPDUP_IN))
        spddn_now = 0 <= BTN_SPDDN_IN < nbtns and bool(js.get_button(BTN_SPDDN_IN))
        if spdup_now and not _spdup_prev and _spd_up_queue < _SPD_QUEUE_MAX:
            _spd_up_queue += 1
        if spddn_now and not _spddn_prev and _spd_dn_queue < _SPD_QUEUE_MAX:
            _spd_dn_queue += 1
        _spdup_prev = spdup_now
        _spddn_prev = spddn_now

        # Advance speed-pulse state machine
        up_bit, _spd_up_queue, _spd_up_state, _spd_up_left = _spd_tick(
            _spd_up_queue, _spd_up_state, _spd_up_left)
        dn_bit, _spd_dn_queue, _spd_dn_state, _spd_dn_left = _spd_tick(
            _spd_dn_queue, _spd_dn_state, _spd_dn_left)
        if up_bit: buttons |= BTN_SPDUP
        if dn_bit: buttons |= BTN_SPDDN

        if 0 <= BTN_PARK_IN < nbtns and js.get_button(BTN_PARK_IN): buttons |= BTN_PARK
        if 0 <= BTN_KEYON_IN < nbtns and js.get_button(BTN_KEYON_IN): buttons |= BTN_KEYON
        if 0 <= BTN_KEYSTART_IN < nbtns and js.get_button(BTN_KEYSTART_IN): buttons |= BTN_KEYSTART
        if 0 <= BTN_ES_IN < nbtns and js.get_button(BTN_ES_IN): buttons |= BTN_ES
        if 0 <= BTN_IMPL_IN < nbtns and js.get_button(BTN_IMPL_IN): buttons |= BTN_IMPL

        hat = None
        if js.get_numhats() > 0:
            hx, hy = js.get_hat(0)
            hat = [hx, hy]

            _hat_spd_enqueue(hx, hy)  # rising-edge detection via _hat_prev_xy

            if HAT_IMPL_DIR == 0 and hy > 0: buttons |= BTN_IMPL
            if HAT_IMPL_DIR == 1 and hy < 0: buttons |= BTN_IMPL
            if HAT_IMPL_DIR == 2 and hx > 0: buttons |= BTN_IMPL
            if HAT_IMPL_DIR == 3 and hx < 0: buttons |= BTN_IMPL

            if HAT_PARK_DIR == 0 and hy > 0: buttons |= BTN_PARK
            if HAT_PARK_DIR == 1 and hy < 0: buttons |= BTN_PARK
            if HAT_PARK_DIR == 2 and hx > 0: buttons |= BTN_PARK
            if HAT_PARK_DIR == 3 and hx < 0: buttons |= BTN_PARK

        elapsed_ms = int(time.time() * 1000) - conn_start_ms if conn_start_ms is not None else 0
        # New protocol: SET lift tilt throttle steer buttons gear elapsed_ms
        line = (f"SET {lift} {tilt} {throttle} {steer} {buttons}"
                f" {_gear_state} {elapsed_ms}\n").encode()

        return line, True, js.get_name(), {
            "estop_pressed": False,
            "hat": hat,
            "buttons_pressed": [i for i in range(js.get_numbuttons()) if js.get_button(i)],
            "axes_raw": [round(js.get_axis(i), 3) for i in range(min(8, js.get_numaxes()))],
            "axes_mapped": {
                "steer":    steer,
                "throttle": throttle,
                "tilt":     tilt,
                "lift":     lift,
            },
            "buttons_mask":           buttons,
            "gear":                   _gear_state,
            "gear_name":              GEAR_NAMES[_gear_state],
            "throttle_must_release":  _throttle_must_release,
            "throttle_axis":          AXIS_THROTTLE,
            "throttle_raw":           round(throttle_raw, 3) if AXIS_THROTTLE >= 0 else None,
            "gear_up_btn":            BTN_GEAR_UP_IN,
            "gear_dn_btn":            BTN_GEAR_DN_IN,
        }

    except Exception:
        # Unplug / invalid handle / SDL hiccup
        return b"STOP\n", False, None, None

# ==== Main ====
def main():
    pygame.init()
    pygame.joystick.init()

    # Warn clearly if safety-critical axes/buttons are not yet mapped in config.json
    if AXIS_THROTTLE < 0:
        print("[cfg] WARN: axis_throttle=-1 (not configured). Throttle disabled. "
              "Run test_buttons.py, identify your right trigger axis, then set axis_throttle in config.json.")
    else:
        print(f"[cfg] throttle -> axis {AXIS_THROTTLE}  rest={THROTTLE_REST}  invert={INVERT_THROTTLE}")
    if BTN_GEAR_UP_IN < 0:
        print("[cfg] WARN: btn_gear_up=-1 (not configured). Gear-Up disabled.")
    else:
        print(f"[cfg] gear-up  -> button {BTN_GEAR_UP_IN}")
    if BTN_GEAR_DN_IN < 0:
        print("[cfg] WARN: btn_gear_dn=-1 (not configured). Gear-Down disabled.")
    else:
        print(f"[cfg] gear-dn  -> button {BTN_GEAR_DN_IN}")

    js = init_joystick()
    sock = None
    conn_start_ms = None
    last_tcp_attempt = 0.0
    TCP_RETRY_INTERVAL = 3.0

    tcp_connected = False
    last_tcp_error = None

    period = 1.0 / SEND_HZ
    last_send_print = 0.0
    last_status_write = 0.0
    status_every = 0.12

    # Don’t spam re-init
    last_joy_probe = 0.0
    joy_probe_every = 0.8  # seconds

    joy_name = None
    joy_connected = bool(js is not None)
    last_command = "STOP"
    last_inputs = None

    try:
        while RUNNING:
            t0 = time.time()

            # Periodically probe for joystick presence and re-init when needed
            now = time.time()
            if now - last_joy_probe > joy_probe_every:
                last_joy_probe = now
                if js is None:
                    js = init_joystick()
                    if js is not None:
                        joy_connected = True
                        joy_name = js.get_name()
                        reset_gear()   # operator must re-select gear after joystick reconnect
                        reset_spd_queues()

            # Build outgoing line
            if js is None:
                pygame.event.pump()  # keep SDL2 alive so it can detect controller reconnects
                line = b"STOP\n"
                joy_connected = False
                joy_name = None
            else:
                line, ok, nm, inputs = safe_read_inputs(js, conn_start_ms)
                if not ok:
                    print("[joy] disconnected -> sending STOP and waiting for reconnect")
                    js = None
                    line = b"STOP\n"
                    joy_connected = False
                    joy_name = None
                    last_inputs = None
                    reset_spd_queues()
                    reset_gear()
                else:
                    joy_connected = True
                    joy_name = nm
                    last_inputs = inputs

            # Log what we’re sending (once per second)
            if time.time() - last_send_print > 1:
                try:
                    dbg = line.decode().strip()
                except Exception:
                    dbg = str(line)
                print(f"[send] {dbg}")
                last_command = dbg
                last_send_print = time.time()

            # Write status frequently so web UI reacts quickly.
            if time.time() - last_status_write > status_every:
                status = {
                    "ts": time.time(),
                    "tcp_connected": bool(tcp_connected),
                    "tcp_error": last_tcp_error,
                    "server": f"{SERVER_IP}:{SERVER_PORT}",
                    "joystick_connected": bool(joy_connected),
                    "joystick_name": joy_name,
                    "last_command": last_command,
                    "inputs": last_inputs,
                    "gear": _gear_state,
                    "gear_name": GEAR_NAMES[_gear_state],
                }
                try:
                    write_status(status)
                except Exception as e:
                    print(f"[warn] unexpected status write error: {e}")
                last_status_write = time.time()

            # Connect or reconnect TCP (non-blocking, rate-limited)
            if sock is None and now - last_tcp_attempt >= TCP_RETRY_INTERVAL:
                last_tcp_attempt = now
                sock, err = _try_connect_tcp()
                if sock is not None:
                    conn_start_ms = int(now * 1000)
                    tcp_connected = True
                    last_tcp_error = None
                    reset_gear()
                else:
                    tcp_connected = False
                    last_tcp_error = err

            # Send
            if sock is not None:
                try:
                    sock.sendall(line)
                    tcp_connected = True
                    last_tcp_error = None
                except Exception as e:
                    print(f"[tcp] send failed: {e}")
                    tcp_connected = False
                    last_tcp_error = str(e)
                    try:
                        sock.close()
                    except:
                        pass
                    sock = None
                    conn_start_ms = None
                    reset_gear()

            # Pace to SEND_HZ
            dt = time.time() - t0
            if dt < period:
                time.sleep(period - dt)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[fatal] {e}")
        sys.exit(1)
    finally:
        # Always try to STOP on exit
        try:
            if sock is not None:
                sock.sendall(b"STOP\n")
        except:
            pass
        try:
            if sock is not None:
                sock.close()
        except:
            pass
        pygame.quit()
        print("STOP sent, bye.")

if __name__ == "__main__":
    main()
