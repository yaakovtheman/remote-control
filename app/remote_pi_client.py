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
BTN_PARK      = 1 << 0
BTN_IMPL      = 1 << 1
BTN_SPDUP     = 1 << 2
BTN_SPDDN     = 1 << 3
BTN_KEYON     = 1 << 4
BTN_KEYSTART  = 1 << 5
BTN_ES        = 1 << 6

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

def connect_tcp():
    while RUNNING:
        try:
            s = socket.create_connection((SERVER_IP, SERVER_PORT), timeout=2.0)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print("[tcp] connected")
            return s
        except Exception as e:
            print(f"[tcp] connect failed: {e}; retrying...")
            try:
                write_status({
                    "ts": time.time(),
                    "tcp_connected": False,
                    "tcp_error": str(e),
                    "server": f"{SERVER_IP}:{SERVER_PORT}",
                    "joystick_connected": False,
                    "joystick_name": None,
                })
            except:
                pass
            time.sleep(0.5)
    return None

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

def safe_read_inputs(js):
    """
    Returns (line_bytes, ok, joy_name)
    ok=False means joystick is gone/broken.
    """
    try:
        pygame.event.pump()

        # If the OS says no joystick, treat as disconnected immediately
        if not joystick_present_now():
            return b"STOP\n", False, None

        steer_raw = js.get_axis(AXIS_STEER)
        drive_raw = js.get_axis(AXIS_DRIVE)
        tilt_raw  = js.get_axis(AXIS_TILT)
        lift_raw  = js.get_axis(AXIS_LIFT)

        steer_raw = apply_deadzone(steer_raw)
        drive_raw = apply_deadzone(drive_raw)
        tilt_raw  = apply_deadzone(tilt_raw)
        lift_raw  = apply_deadzone(lift_raw)

        steer = axis_to_0_1023(steer_raw, INVERT_STEER)
        drive = axis_to_0_1023(drive_raw, INVERT_DRIVE)
        tilt  = axis_to_0_1023(tilt_raw,  INVERT_TILT)
        lift  = axis_to_0_1023(lift_raw,  INVERT_LIFT)

        # E-STOP?
        if js.get_button(BTN_ESTOP) == 1:
            return b"STOP\n", True, js.get_name()

        buttons = 0
        if js.get_button(2): buttons |= BTN_SPDUP
        if js.get_button(1): buttons |= BTN_SPDDN
        if js.get_button(3): buttons |= BTN_PARK
        if js.get_button(5): buttons |= BTN_KEYON
        if js.get_button(7): buttons |= BTN_KEYSTART
        if js.get_button(6): buttons |= BTN_ES
        if js.get_button(4): buttons |= BTN_IMPL

        if js.get_numhats() > 0:
            hx, hy = js.get_hat(0)
            if hy > 0: buttons |= BTN_SPDUP
            if hy < 0: buttons |= BTN_SPDDN
            if hx > 0: buttons |= BTN_IMPL
            if hx < 0: buttons |= BTN_PARK

        line = f"SET {lift} {tilt} {drive} {steer} {buttons}\n".encode()
        return line, True, js.get_name()

    except Exception:
        # Unplug / invalid handle / SDL hiccup
        return b"STOP\n", False, None

# ==== Main ====
def main():
    pygame.init()
    pygame.joystick.init()

    js = init_joystick()
    sock = connect_tcp()

    tcp_connected = (sock is not None)
    last_tcp_error = None

    period = 1.0 / SEND_HZ
    last_send_print = 0.0
    last_status_write = 0.0

    # Don’t spam re-init
    last_joy_probe = 0.0
    joy_probe_every = 0.8  # seconds

    joy_name = None
    joy_connected = bool(js is not None)

    try:
        while RUNNING:
            t0 = time.time()

            # Periodically probe for joystick presence and re-init when needed
            now = time.time()
            if now - last_joy_probe > joy_probe_every:
                last_joy_probe = now
                if js is None:
                    js = init_joystick()
                    joy_connected = bool(js is not None)
                    joy_name = js.get_name() if js is not None else None

            # Build outgoing line
            if js is None:
                line = b"STOP\n"
                joy_connected = False
                joy_name = None
            else:
                line, ok, nm = safe_read_inputs(js)
                if not ok:
                    print("[joy] disconnected -> sending STOP and waiting for reconnect")
                    js = None
                    line = b"STOP\n"
                    joy_connected = False
                    joy_name = None
                else:
                    joy_connected = True
                    joy_name = nm

            # Log what we’re sending (once per second)
            if time.time() - last_send_print > 1:
                try:
                    dbg = line.decode().strip()
                except Exception:
                    dbg = str(line)
                print(f"[send] {dbg}")
                last_send_print = time.time()

            # Write status (once per second)
            if time.time() - last_status_write > 1.0:
                status = {
                    "ts": time.time(),
                    "tcp_connected": bool(tcp_connected),
                    "tcp_error": last_tcp_error,
                    "server": f"{SERVER_IP}:{SERVER_PORT}",
                    "joystick_connected": bool(joy_connected),
                    "joystick_name": joy_name,
                }
                try:
                    write_status(status)
                except Exception as e:
                    print(f"[warn] unexpected status write error: {e}")
                last_status_write = time.time()

            # Send (and auto-reconnect on error)
            try:
                if sock is None:
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
                try:
                    if sock is not None:
                        sock.sendall(b"STOP\n")
                except:
                    pass

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
