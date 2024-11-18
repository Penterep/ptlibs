from hashlib import sha256
from http.cookies import SimpleCookie
import datetime
import os
import pickle
import signal
import sys
import tempfile
import typing
import re

import requests
from requests_toolbelt.utils import dump

from ptlibs import ptdefs
from ptlibs.ptprinthelper import out_if, ptprint



def signal_handler(sig, frame):
    ptprint(f"\r", clear_to_eol=True)
    ptprint( out_if(f"{ptdefs.colors['ERROR']}Script terminating. Press CTRL+C again to force.{ptdefs.colors['TEXT']}", "ERROR"), clear_to_eol=True)

    #with open(os.devnull, "w") as devnull:
    #    sys.stdout = devnull
        #sys.stderr = devnull
    sys.exit(1)

# Register the signal handler for SIGINT
signal.signal(signal.SIGINT, signal_handler)

def read_file(file: str) -> list[str]:
    with open(file, "r") as f:
        domain_list = [line.strip("\n") for line in f]
        return domain_list


def pairs(pair):
    if len(pair.split(":")) == 2:
        return pair
    else:
        raise ValueError('Not a pair')


def get_wordlist(file_handler, begin_with=""):
    while True:
        data = file_handler.readline().strip()
        if not data:
            break
        if data.startswith(begin_with):
            yield data


def time2str(time):
    return str(str(datetime.timedelta(seconds=time))).split(".")[0]


def save_object(obj: dict,  filename) -> None:
    with open(os.path.join(tempfile.gettempdir(), "pentereptools", filename), "wb") as output_file:
        pickle.dump(obj, output_file, pickle.HIGHEST_PROTOCOL)


def load_object(filename) -> object:
    with open(os.path.join(tempfile.gettempdir(), "pentereptools", filename), "rb") as input_file:
        return pickle.load(input_file)


def exists_temp(filename: str) -> bool:
    """Checks whether a file exists in tmp and is created in the last day

    Args:
        filename (str): name of the file

    Returns:
        bool: True if the file exists and is created in the last day
    """

    #check if file exists in tmp
    if not os.path.isfile(os.path.join(tempfile.gettempdir(), "pentereptools", filename)):
        return False

    #check if file is created in the last day
    file_older_than_day = get_file_modification_age(filename).days > 1
    if file_older_than_day:
        os.remove(os.path.join(tempfile.gettempdir(), "pentereptools", filename))
        return False
    else:
        return True


def get_file_modification_age(filename: str) -> datetime.timedelta:
    return (datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(tempfile.gettempdir(), "pentereptools", filename))))


def get_temp_filename_from_url(url: str, method: str, headers: dict) -> str:
    input_bytes = (url + method + str(headers)).encode()
    return sha256(input_bytes).hexdigest()


def get_response_data_dump(response: requests.models.Response) -> dict:
    """Returns a dictionary containing dump of response data from provided response object

    Args:
        response (requests.models.Response): response object

    Returns:
        dict: {"request_data": str, "response_data": str}
    """
    try:
        response_dump = dump.dump_response(response, request_prefix="req:", response_prefix="res:").decode("utf-8", "ignore")
        req = re.sub("req:", "", '\n'.join(re.findall(r"(req:.*)", response_dump, re.MULTILINE)))
        res = re.sub("^res:", "", ''.join(re.search(r"(res:(.|\n)*)", response_dump, re.MULTILINE).groups()), flags=re.MULTILINE)[:-1]
        return {"request": req, "response": res}
    except Exception as e:
        return {"request": "error", "response": "error"}


def _get_response(url: str, method: str, headers: dict, proxies: dict, data: dict = None, timeout: int = None, redirects: bool = False, verify: bool = False, auth: tuple[str, str] = None) -> requests.Response:
    try:
        cookies = _get_cookies_from_headers(headers)
        response = requests.request(method, url, proxies=proxies, allow_redirects=redirects, headers=headers, verify=verify, timeout=timeout, data=data, auth=auth, cookies=cookies)
    except requests.exceptions.RequestException as error:
        raise error
    return response


def _get_cookies_from_headers(headers: dict) -> dict | None:
    if "Cookie" not in headers:
        return None

    cookies_object = SimpleCookie()
    cookies_object.load(headers["Cookie"])
    cookies = {key: morsel.value for key, morsel in cookies_object.items()}
    return cookies


def load_url_from_web_or_temp(url: str, method: str, headers: dict = {}, proxies: dict = {}, data: dict = None, timeout: int = None, redirects: bool = False, verify: bool = False, cache: bool = False, dump_response: bool = False, auth: tuple[str, str] = None) -> requests.Response:
    """Returns HTTP response from URL.
       If param <cache_request> is present, response will be saved into a temp file. If response is already saved in a temp file, it will be loaded from there.

    Args:
        url            (str)  : request url
        method         (str)  : request method
        headers        (dict) : request headers
        proxies        (dict) : request proxies
        data           (dict) : request post data
        timeout        (int)  : request timeout
        redirects      (bool) : follow redirects
        verify         (bool) : verify requests
        cache          (bool) : cache request-response
        dump_response  (bool) : dump request-response
        auth           (tuple[str, str]) : use HTTP authentication

    Returns:
        default:
            requests.models.Response: response
        with dump_response:
            tuple: ( response: requests.Response, request_dump: dict )
    """
    if cache:
        # Create penterep dir in tmp if not present
        if not os.path.exists(os.path.join(tempfile.gettempdir(), "pentereptools")):
            os.makedirs(os.path.join(tempfile.gettempdir(), "pentereptools"))

        filename = get_temp_filename_from_url(url, method, headers)
        if exists_temp(filename):
            obj = load_object(filename)
            return obj["response"] if not dump_response else (obj["response"], obj["response_dump"])
        else:
            response = _get_response(url, method, headers, proxies, data, timeout, redirects, verify, auth)
            response_dump = get_response_data_dump(response)
            save_object({"response": response, "response_dump": response_dump}, filename)
            return response if not dump_response else (response, response_dump)
    else:
        response = _get_response(url, method, headers, proxies, data, timeout, redirects, verify, auth)
        return response if not dump_response else (response, get_response_data_dump(response))


def clean_html(input_html):
    """
    Removes all HTML tags from the input string, replacing <br>, <br/> and </p> tags with newlines.

    Parameters:
    input_html (str): A string containing HTML content.

    Returns:
    str: The cleaned string with no HTML tags and certain tags replaced by newline characters.
    """
    # Replace <br>, <br/>, and </p> tags with \n
    patterns_to_newline = re.compile(r'(<br\s*/?>|</p>)', re.IGNORECASE)
    text_with_newlines = re.sub(patterns_to_newline, '\n', input_html)

    # Remove all other HTML tags
    clean_text = re.sub(r'<.*?>', '', text_with_newlines)

    return clean_text.rstrip()
