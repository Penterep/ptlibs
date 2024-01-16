import requests
import tempfile
import re
import os

from ptlibs import ptnethelper
from urllib.parse import urlparse, urlunparse, ParseResult

class ParsedResult:
    def __init__(self, kwargs):
        self.__dict__.update(kwargs)

    def __getitem__(self, key):
        return getattr(self, key, None)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __repr__(self):
        return repr(self.__dict__)


def parse_url(url: str) -> ParsedResult:
    """Parse provided <url>"""

    if is_domain(url):
        parsed_url = _move_path_to_netloc(url)
    elif is_url(url):
        parsed_url = urlparse(url)
    else:
        raise ValueError("Provided <url> is neither a valid url nor domain")

    scheme = parsed_url.scheme if parsed_url.scheme else ""
    port   = parsed_url.port
    netloc = parsed_url.netloc.split(":"+str(port))[0] if port else parsed_url.netloc
    suffix = get_tld(netloc)
    netloc = ''.join(netloc.split("." + suffix)) if suffix else netloc
    domain = netloc
    subdomains = ""

    if not ptnethelper.is_valid_ip_address(netloc):
        subdomains = '.'.join(netloc.split(".")[:-1])
        domain = ''.join(netloc.split(".")[-1])

    return ParsedResult({
        "scheme": scheme,
        "subdomain": subdomains,
        "domain": domain,
        "suffix": suffix,
        "port": port,
    })

def _move_path_to_netloc(url) -> ParseResult:
    """If <url> lacks a scheme, the urllib.urlparse() function incorrectly sets the netloc to the path. This function fixes this issue."""
    parsed_url = urlparse(url)

    return ParseResult(
        scheme=parsed_url.scheme,
        netloc=parsed_url.path.split("/", 1)[0],
        path=parsed_url.path.split("/", 1)[1] if len(parsed_url.path.split("/", 1)) > 1 else "",
        params=parsed_url.params,
        query=parsed_url.query,
        fragment=parsed_url.fragment
    )

def is_domain(string: str) -> bool:
    return True if not all([urlparse(string).netloc, urlparse(string).scheme]) and urlparse(string).path and "." in string else False

def is_url(string: str) -> bool:
    return True if all([urlparse(string).netloc, urlparse(string).scheme]) else False

def get_tld(url) -> str:
    """Retrieve TLD from <url>"""
    result = sorted([w for w in _get_public_suffix_list() if url.endswith(w)])
    return result[0][1:] if result else ""


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
