# find_cameras.py
import socket
import ipaddress
import concurrent.futures
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

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
        return None, None, []

    net = ipaddress.ip_network(local_ip + "/24", strict=False)
    hosts = [str(ip) for ip in net.hosts() if str(ip) != local_ip]
    return local_ip, str(net), hosts


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
    local_ip, subnet, hosts = get_hosts()

    if not local_ip:
        return {
            "local_ip": None,
            "subnet": None,
            "count": 0,
            "cameras": [],
            "error": "Could not determine local IPv4 address",
        }

    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for result in ex.map(check_camera, hosts):
            if result:
                found.append(result)

    found.sort(key=lambda cam: tuple(int(x) for x in cam["ip"].split(".")))

    return {
        "local_ip": local_ip,
        "subnet": subnet,
        "count": len(found),
        "cameras": found,
    }


def print_pretty(result):
    print(f"Local IP: {result['local_ip']}")
    print(f"Subnet:   {result['subnet']}")
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
    result = scan_cameras()

    if "--pretty" in sys.argv:
        print_pretty(result)
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()