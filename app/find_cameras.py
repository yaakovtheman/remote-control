# find_cameras.py
import socket
import ipaddress
import concurrent.futures
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def read_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_config(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_PATH)


def check_pi(ip):
    url = f"http://{ip}:8088/api/status"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(1000).decode("utf-8", errors="ignore")
            data = json.loads(body)

            if isinstance(data, dict) and (
                "server" in data
                or "tcp_connected" in data
                or "joystick_connected" in data
                or "tcp_client_connected" in data
                or "telemetry_connected" in data
            ):
                return {
                    "ip": ip,
                    "status": resp.status,
                    "endpoint": url,
                    "pi": True,
                    "data": data,
                }

    except Exception:
        pass

    return None


def scan_pi():
    local_ip, subnets, hosts = get_hosts()

    if not local_ip:
        return {
            "local_ip": None,
            "subnets": [],
            "found": False,
            "pi": None,
            "error": "Could not determine local IPv4 address",
        }

    found = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for result in ex.map(check_pi, hosts):
            if result:
                found = result
                break

    return {
        "local_ip": local_ip,
        "subnets": subnets,
        "found": found is not None,
        "pi": found,
    }


def update_config_with_pi(ip):
    cfg = read_config()
    cfg["server_ip"] = ip
    write_config(cfg)
    return cfg

TIMEOUT = 0.7
MAX_WORKERS = 32


def get_local_ip():
    candidates = []

    # First try: common UDP trick
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        finally:
            s.close()
    except Exception:
        pass

    # Second try: hostname lookup
    try:
        hostname = socket.gethostname()
        for res in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            ip = res[4][0]
            if ip and not ip.startswith("127."):
                candidates.append(ip)
    except Exception:
        pass

    # Third try: all interfaces via gethostbyname_ex
    try:
        hostname = socket.gethostname()
        _, _, ips = socket.gethostbyname_ex(hostname)
        for ip in ips:
            if ip and not ip.startswith("127."):
                candidates.append(ip)
    except Exception:
        pass

    # Return first private IPv4 if possible
    for ip in candidates:
        try:
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.version == 4 and ip_obj.is_private:
                return ip
        except Exception:
            pass

    # Otherwise first non-loopback candidate
    for ip in candidates:
        if ip and not ip.startswith("127."):
            return ip

    return None


def get_hosts():
    local_ip = get_local_ip()
    if not local_ip:
        return None, [], []

    candidate_networks = []
    seen = set()

    def add_network(cidr: str):
        net = ipaddress.ip_network(cidr, strict=False)
        key = str(net)
        if key not in seen:
            seen.add(key)
            candidate_networks.append(net)

    # First scan the local /24
    add_network(f"{local_ip}/24")

    # Then scan the most common fallback camera subnets
    for cidr in [
        "192.168.10.0/24",
        "192.168.0.0/24",
        "192.168.1.0/24",
        "10.0.0.0/24",
    ]:
        add_network(cidr)

    hosts = []
    for net in candidate_networks:
        for ip in net.hosts():
            ip_str = str(ip)
            if ip_str != local_ip:
                hosts.append(ip_str)

    return local_ip, [str(net) for net in candidate_networks], hosts


def parse_preview(body: str):
    body_l = body.lower()

    if 'xmlns="http://www.ipc.com/ver10"' in body_l:
        vendor = "ipc.com/ver10"
    else:
        vendor = "unknown"

    if "unauthorized" in body_l:
        auth = "unauthorized"
    else:
        auth = "unknown"

    return {
        "vendor": vendor,
        "auth": auth,
    }


def build_result(ip: str, status: int, body: str):
    meta = parse_preview(body)
    return {
        "ip": ip,
        "status": status,
        "vendor": meta["vendor"],
        "auth": meta["auth"],
        "endpoint": f"http://{ip}/onvif/device_service",
        "onvif": True,
    }


def check_camera(ip):
    url = f"http://{ip}/onvif/device_service"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(500).decode("utf-8", errors="ignore")
            if "<config" in body or 'xmlns="http://www.ipc.com/ver10"' in body:
                return build_result(ip, resp.status, body)

    except HTTPError as e:
        try:
            body = e.read(500).decode("utf-8", errors="ignore")
        except Exception:
            body = ""

        if "<config" in body or 'xmlns="http://www.ipc.com/ver10"' in body:
            return build_result(ip, e.code, body)

    except (URLError, TimeoutError, OSError):
        pass

    return None


def scan_cameras():
    local_ip, subnets, hosts = get_hosts()

    if not local_ip:
        return {
            "local_ip": None,
            "subnets": [],
            "count": 0,
            "cameras": [],
            "error": "Could not determine local IPv4 address",
        }

    found = []
    seen_ips = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for result in ex.map(check_camera, hosts):
            if result and result["ip"] not in seen_ips:
                seen_ips.add(result["ip"])
                found.append(result)

    found.sort(key=lambda cam: tuple(int(x) for x in cam["ip"].split(".")))

    return {
        "local_ip": local_ip,
        "subnets": subnets,
        "count": len(found),
        "cameras": found,
    }


def print_pretty(result):
    print(f"Local IP: {result['local_ip']}")
    print("Subnets:")
    for subnet in result.get("subnets", []):
        print(f"  - {subnet}")
    print()

    if result.get("error"):
        print(f"Error: {result['error']}")
        return

    if not result["cameras"]:
        print("No matching cameras found.")
        return

    print("Found cameras:\n")
    for cam in result["cameras"]:
        print(f"IP:       {cam['ip']}")
        print(f"Status:   {cam['status']}")
        print(f"Vendor:   {cam['vendor']}")
        print(f"Auth:     {cam['auth']}")
        print(f"Endpoint: {cam['endpoint']}")
        print()


def main():
    run_pi = False
    run_cam = False

    # flags
    if "--pi" in sys.argv:
        run_pi = True
    if "--cam" in sys.argv:
        run_cam = True

    # default = both
    if not run_pi and not run_cam:
        run_pi = True
        run_cam = True

    # ---- PI ----
    if run_pi:
        pi_result = scan_pi()

        if pi_result.get("found") and pi_result.get("pi"):
            ip = pi_result["pi"]["ip"]

            update_config_with_pi(ip)

            if "--pretty" in sys.argv:
                print(f"\n[PI] Found Raspberry Pi: {ip}")
                print(f"Endpoint: {pi_result['pi']['endpoint']}")
                print(f"Updated config.json server_ip -> {ip}")
        else:
            if "--pretty" in sys.argv:
                print("\n[PI] Not found")

    # ---- CAMERAS ----
    if run_cam:
        cam_result = scan_cameras()

        if "--pretty" in sys.argv:
            print("\n[CAMERAS]")
            print_pretty(cam_result)
        else:
            print(json.dumps(cam_result, indent=2))


if __name__ == "__main__":
    main()