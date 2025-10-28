import socket
from functools import lru_cache

# --- Load /etc/hosts ---
def load_hosts(hosts_path="/etc/hosts"):
    hosts = {}
    try:
        with open(hosts_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    ip, *names = parts
                    for name in names:
                        hosts[name.lower()] = ip
    except Exception:
        pass
    return hosts

HOSTS_CACHE = load_hosts()

# --- Patch socket.getaddrinfo ---
_original_getaddrinfo = socket.getaddrinfo

@lru_cache(maxsize=1024)
def cached_getaddrinfo(host, port=0, *args, **kwargs):
    lname = host.rstrip('.').lower()
    if lname in HOSTS_CACHE:
        ip = HOSTS_CACHE[lname]
        # Return a tuple exactly as getaddrinfo would
        try:
            return _original_getaddrinfo(ip, port, *args, **kwargs)
        except socket.gaierror:
            # Fallback to IPv4 if resolution fails
            return _original_getaddrinfo(ip, port, socket.AF_INET, *args, **kwargs)
    # Fallback: normal DNS lookup
    return _original_getaddrinfo(host, port, *args, **kwargs)

def install_dns_cache():
    """Activates /etc/hosts caching for all socket-based libraries (requests, urllib, etc.)."""
    socket.getaddrinfo = cached_getaddrinfo
