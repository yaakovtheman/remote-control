# remote_pi_client.py
import socket, time, pygame, sys
import json, os
import signal

STATUS_PATH = os.path.join(os.path.dirname(__file__), "status.json")

def write_status(obj: dict):
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, STATUS_PATH)

RUNNING = True

def handle_exit(sig, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

cfg = load_config()

SERVER_IP   = cfg["server_ip"]
SERVER_PORT = int(cfg["server_port"])
SEND_HZ     = int(cfg["send_hz"])
DEADZONE    = float(cfg["deadzone"])

AXIS_STEER  = int(cfg["axis_steer"])
AXIS_DRIVE  = int(cfg["axis_drive"])
AXIS_TILT   = int(cfg["axis_tilt"])
AXIS_LIFT   = int(cfg["axis_lift"])

INVERT_STEER = bool(cfg["invert_steer"])
INVERT_DRIVE = bool(cfg["invert_drive"])
INVERT_TILT  = bool(cfg["invert_tilt"])
INVERT_LIFT  = bool(cfg["invert_lift"])

BTN_ESTOP   = int(cfg["btn_estop"])

if "--ip" in sys.argv:
    SERVER_IP = sys.argv[sys.argv.index("--ip") + 1]
print(f"[cfg] using {SERVER_IP}")

# ==== Button bitmask (must match Arduino) ====
BTN_PARK      = 1 << 0   # bit 0
BTN_IMPL      = 1 << 1   # bit 1
BTN_SPDUP     = 1 << 2   # bit 2
BTN_SPDDN     = 1 << 3   # bit 3
BTN_KEYON     = 1 << 4   # bit 4
BTN_KEYSTART  = 1 << 5   # bit 5
BTN_ES        = 1 << 6   # bit 6

# ==== Helpers ====
def clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v

def apply_deadzone(x, dz=DEADZONE):
    return 0.0 if abs(x) < dz else x

def axis_to_0_1023(val, invert=False):
    # pygame axis: -1..1 -> 0..1023
    v = -val if invert else val
    v = clamp(v, -1.0, 1.0)
    v = (v + 1.0) * 0.5   # -> 0..1
    return int(round(v * 1023))

def connect_tcp():
    while RUNNING:
        try:
            s = socket.create_connection((SERVER_IP, SERVER_PORT), timeout=2.0)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print("[tcp] connected")
            tcp_connected = True
            return s
        except Exception as e:
            tcp_connected = False
            last_tcp_error = str(e)
            print(f"[tcp] connect failed: {e}; retrying...")
            try:
                write_status({
                    "ts": time.time(),
                    "tcp_connected": False,
                    "tcp_error": str(e),
                    "server": f"{SERVER_IP}:{SERVER_PORT}",
                })
            except:
                pass
            time.sleep(0.5)

def init_joystick():
    pygame.joystick.quit()
    pygame.joystick.init()
    n = pygame.joystick.get_count()
    if n == 0:
        return None
    js = pygame.joystick.Joystick(0)
    js.init()
    print(f"[joy] {js.get_name()} ready ({js.get_numaxes()} axes, {js.get_numbuttons()} buttons)")
    
    return js

# ==== Main ====
def main():
    pygame.init()
    js = init_joystick()
    sock = connect_tcp()
    tcp_connected = (sock is not None)
    period = 1.0 / SEND_HZ
    last_send_print = 0.0
    last_status_write = 0.0
    tcp_connected = False
    last_tcp_error = None

    try:
        while RUNNING:
            t0 = time.time()
            # Keep joystick fresh / hot-plug
            if js is None or not js.get_init():
                js = init_joystick()

            pygame.event.pump()  # process internal queue

            # Default: STOP if no joystick
            if js is None:
                line = b"STOP\n"
            else:
                # Read axes
                steer_raw = js.get_axis(AXIS_STEER)
                drive_raw = js.get_axis(AXIS_DRIVE)
                tilt_raw  = js.get_axis(AXIS_TILT)
                lift_raw  = js.get_axis(AXIS_LIFT)

                # Dead-zone
                steer_raw = apply_deadzone(steer_raw)
                drive_raw = apply_deadzone(drive_raw)
                tilt_raw  = apply_deadzone(tilt_raw)
                lift_raw  = apply_deadzone(lift_raw)

                # Map to 0..1023
                steer = axis_to_0_1023(steer_raw, INVERT_STEER)
                drive = axis_to_0_1023(drive_raw, INVERT_DRIVE)
                tilt  = axis_to_0_1023(tilt_raw,  INVERT_TILT)
                lift  = axis_to_0_1023(lift_raw,  INVERT_LIFT)

                # E-STOP? (X button)
                estop = js.get_button(BTN_ESTOP) == 1
                if estop:
                    line = b"STOP\n"
                else:
                    # ---------- Build buttons bitmask ----------
                    buttons = 0

                    # Face buttons (right side)
                    # Triangle (index 2) -> Speed up
                    if js.get_button(2):
                        buttons |= BTN_SPDUP
                    # Circle (index 1) -> Speed down
                    if js.get_button(1):
                        buttons |= BTN_SPDDN
                    # Square (index 3) -> Park toggle
                    if js.get_button(3):
                        buttons |= BTN_PARK
                    # X (index 0) is E-STOP and handled above, so NOT mapped here.

                    # Shoulder buttons
                    # Right top  (index 5) -> KEYON (ignition)
                    if js.get_button(5):
                        buttons |= BTN_KEYON
                    # Right bottom (index 7) -> KEYSTART (starter)
                    if js.get_button(7):
                        buttons |= BTN_KEYSTART
                    # Left bottom (index 6) -> ES (emergency shutdown override)
                    if js.get_button(6):
                        buttons |= BTN_ES
                    # Left top (index 4) -> Hydraulic lockout
                    if js.get_button(4):
                        buttons |= BTN_IMPL

                    # D-pad (HAT 0) – optional extra mappings
                    if js.get_numhats() > 0:
                        hx, hy = js.get_hat(0)
                        if hy > 0:   # D-pad up
                            buttons |= BTN_SPDUP
                        if hy < 0:   # D-pad down
                            buttons |= BTN_SPDDN
                        if hx > 0:   # D-pad right
                            buttons |= BTN_IMPL
                        if hx < 0:   # D-pad left
                            buttons |= BTN_PARK

                    # Build full SET line including buttons
                    line = f"SET {lift} {tilt} {drive} {steer} {buttons}\n".encode()

                    # --- Log what we’re sending (once per second) ---
                if time.time() - last_send_print > 1:
                    try:
                        dbg = line.decode().strip()
                    except Exception:
                        dbg = str(line)
                        tcp_connected = False
                        last_tcp_error = str(e)
                    print(f"[send] {dbg}")
                    last_send_print = time.time()
            if time.time() - last_status_write > 1.0:
                status = {
                    "ts": time.time(),
                    "tcp_connected": bool(tcp_connected),
                    "tcp_error": last_tcp_error,
                    "server": f"{SERVER_IP}:{SERVER_PORT}",
                    "joystick_connected": bool(js is not None and js.get_init()),
                    "joystick_name": (js.get_name() if js is not None and js.get_init() else None),
                }
                write_status(status)
                last_status_write = time.time()

            # Send (and auto-reconnect on error)
            try:
                if sock is None:
                    # shutting down or couldn't connect
                    time.sleep(0.2)
                    continue
                sock.sendall(line)
                tcp_connected = True
                last_tcp_error = None
            except Exception as e:
                print(f"[tcp] send failed: {e}; reconnecting...")
                tcp_connected = False
                last_tcp_error = str(e)
                try:
                    sock.close()
                except:
                    pass
                sock = connect_tcp()
                tcp_connected = (sock is not None)
                # Try to send STOP once on reconnect to be safe
                try:
                    sock.sendall(b"STOP\n")
                except:
                    pass

            # Pace to SEND_HZ
            dt = time.time() - t0
            if dt < period:
                time.sleep(period - dt)
    except KeyboardInterrupt:
        try:
            sock.sendall(b"STOP\n")
        except:
            pass
        try:
            sock.close()
        except:
            pass
        pygame.quit()
        print("STOP sent, bye.")
    except Exception as e:
        print(f"[fatal] {e}")
        try:
            sock.sendall(b"STOP\n")
        except:
            pass
        try:
            sock.close()
        except:
            pass
        pygame.quit()
        sys.exit(1)

if __name__ == "__main__":
    main()
