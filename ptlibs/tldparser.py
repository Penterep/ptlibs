import os
import re
import tempfile

from dataclasses import dataclass
from functools import lru_cache
import urllib

import requests

@dataclass
class TLDParseResult:
    """Result object of extract/parse methods"""
    scheme: str
    subdomain: str
    domain: str
    suffix: str
    port: str

    @property
    def get_domain(self):
       return ''.join(part for part in [self.subdomain, self.domain, self.suffix] if part)


def extract(url_or_domain: str) -> TLDParseResult:
    return parse(url_or_domain)

def parse(url_or_domain: str) -> TLDParseResult:
    # TODO: IP parsing
    if is_url(url_or_domain):
        parsed = urllib.parse.urlparse(url_or_domain)
    elif is_domain(url_or_domain):
        parsed = parse_schemeless_url_correctly(url_or_domain)
    else:
        return

    subdomain, base_domain, suffix, port = _parse_full_domain(parsed.netloc, get_suffix(parsed.netloc.split(":")[0]))
    return TLDParseResult(parsed.scheme, subdomain, base_domain, suffix, port)

def is_domain(string: str) -> bool:
    base_url = urllib.parse.urlparse(string).netloc or string.split('/')[0]
    # Match against a domain pattern with an optional port
    return bool(re.match(r'^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(:\d+)?$', base_url))

def is_url(string: str) -> bool:
    parsed = urllib.parse.urlparse(string)
    return True if all([parsed.netloc, parsed.scheme]) else False

def _parse_full_domain(domain: str, suffix: str):
    # Split the domain from the port if present
    domain_parts = domain.split(':')
    domain_without_port = domain_parts[0]
    port = domain_parts[1] if len(domain_parts) > 1 else ""

    # Check and strip the suffix
    if suffix and domain_without_port.endswith(suffix):
        domain_without_suffix = domain_without_port[:-len(suffix)].rstrip('.')
    else:
        domain_without_suffix = domain_without_port

    # Extract subdomains and base domain
    subdomain_parts = domain_without_suffix.split('.')
    base_domain = subdomain_parts[-1] if len(subdomain_parts) > 1 else domain_without_suffix
    subdomains = '.'.join(subdomain_parts[:-1]) if len(subdomain_parts) > 1 else ''

    return subdomains, base_domain, suffix, port

def get_suffix(url_or_domain) -> str:
    """Retrieve the TLD/suffix from a URL or domain using the Public Suffix List."""
    suffix_list = _get_public_suffix_list()
    result = [suffix for suffix in suffix_list if url_or_domain.endswith(suffix)]
    result = sorted(result, key=len, reverse=True)
    return result[0].lstrip(".") if result else ""

def parse_schemeless_url_correctly(url) -> urllib.parse.ParseResult:
    """Corrects the parsing of schemeless URL"""
    parsed = urllib.parse.urlparse("http://" + url if "://" not in url else url)
    return urllib.parse.ParseResult(
        scheme="",
        netloc=parsed.netloc,
        path=parsed.path,
        params=parsed.params,
        query=parsed.query,
        fragment=parsed.fragment
    )

@lru_cache(maxsize=None)
def _get_public_suffix_list() -> list:
    """Load the Public Suffix List (PSL) from a temporary file, or download it if not present."""
    try:
        return _load_psl_from_tmp()
    except FileNotFoundError:
        suffix_list = _download_psl()
        with open(os.path.join(tempfile.gettempdir(), "PSL.txt"), "w") as file:
            file.write("\n".join(suffix_list))
        return suffix_list

@lru_cache(maxsize=None)
def _load_psl_from_tmp() -> list:
    """Load the PSL from a temporary file."""
    with open(os.path.join(tempfile.gettempdir(), "PSL.txt"), "r") as file:
        return [line.strip() for line in file if line.strip() and not line.startswith("//")]

@lru_cache(maxsize=None)
def _download_psl() -> list:
    """Download the PSL from the official Public Suffix List site."""
    response = requests.get("https://publicsuffix.org/list/public_suffix_list.dat")
    if response.status_code == 200:
        return ["." + line.strip() for line in response.text.split("\n") if line.strip() and not line.startswith("//")]
    else:
        raise Exception("Failed to download the Public Suffix List")