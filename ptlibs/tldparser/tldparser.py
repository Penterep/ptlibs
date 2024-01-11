import requests
import tempfile
import re
import os

from ptlibs import ptnethelper
from urllib.parse import urlparse

def parse_url(url: str) -> object:
    """Parse provided <url>"""

    parsed_url = urlparse(url)

    if not all([parsed_url.netloc, parsed_url.scheme]):
        raise ValueError("Not a valid URL")

    domain = None
    subdomains = None
    scheme = parsed_url.scheme
    port = parsed_url.port
    if port:
        _netloc = parsed_url.netloc.split(":"+str(port))[0]
    else:
        _netloc = parsed_url.netloc

    suffix = get_tld(_netloc)

    if suffix:
        _netloc = ''.join(_netloc.split("." + suffix))

    if not ptnethelper.is_valid_ip_address(_netloc):
        subdomains = '.'.join(_netloc.split(".")[:-1])
        domain = ''.join(_netloc.split(".")[-1])
    else:
        domain = _netloc

    return {
        "scheme": scheme,
        "subdomain": subdomains,
        "domain": domain,
        "suffix": suffix,
        "port": port,
    }


def get_tld(url) -> str:
    """Retrieve TLD from <url>"""
    result = sorted([w for w in _get_public_suffix_list() if url.endswith(w)])
    return result[0][1:] if result else None


def get_scheme(url) -> str | None:
    return url.split("://")[0] if re.match(r"\w*://", url) else None


def _get_public_suffix_list() -> list:
    """Load PSL from tmp, if not present then proceed to download it from www.publicsuffix.org and save it to temp"""
    def download_psl():
        response = requests.get("https://www.publicsuffix.org/list/public_suffix_list.dat")
        suffix_list = ["." + w for w in response.text.split("\n") if w and not w.startswith("//")]
        return suffix_list

    def save_psl(suffix_list: list) -> None:
        with open(os.path.join(tempfile.gettempdir(), "PSL.txt"), "w") as file:
            file.write("\n".join(suffix_list))

    def load_psl_from_tmp() -> list | None:
        try:
            with open(os.path.join(tempfile.gettempdir(), "PSL.txt"), "r") as file:
                suffix_list = [w for w in file.read().split("\n") if w and not w.startswith("//")]
                return suffix_list
        except FileNotFoundError as exc:
            raise exc

    try:
        suffix_list = load_psl_from_tmp()
    except FileNotFoundError:
        suffix_list = download_psl()
        save_psl(suffix_list)
    return suffix_list
