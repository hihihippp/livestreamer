from requests import Session, __build__ as requests_version
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException

try:
    from requests.packages.urllib3.util import Timeout
    TIMEOUT_ADAPTER_NEEDED = requests_version < 0x020300
except ImportError:
    TIMEOUT_ADAPTER_NEEDED = False

from ...exceptions import PluginError
from ...utils import parse_json, parse_xml

__all__ = ["HTTPSession"]


def _parse_keyvalue_list(val):
    for keyvalue in val.split(";"):
        try:
            key, value = keyvalue.split("=")
            yield key.strip(), value.strip()
        except ValueError:
            continue


class HTTPAdapterWithReadTimeout(HTTPAdapter):
    """This is a backport of the timeout behaviour from requests 2.3.0+
       where timeout is applied to both connect and read."""

    def get_connection(self, *args, **kwargs):
        conn = HTTPAdapter.get_connection(self, *args, **kwargs)

        # Override the urlopen method on this connection
        if not hasattr(conn.urlopen, "wrapped"):
            orig_urlopen = conn.urlopen

            def urlopen(*args, **kwargs):
                timeout = kwargs.pop("timeout", None)
                if isinstance(timeout, Timeout):
                    timeout = Timeout.from_float(timeout.connect_timeout)

                return orig_urlopen(*args, timeout=timeout, **kwargs)

            conn.urlopen = urlopen
            conn.urlopen.wrapped = True

        return conn


class HTTPSession(Session):
    def __init__(self, *args, **kwargs):
        Session.__init__(self, *args, **kwargs)

        if TIMEOUT_ADAPTER_NEEDED:
            self.mount("http://", HTTPAdapterWithReadTimeout())
            self.mount("https://", HTTPAdapterWithReadTimeout())

    @classmethod
    def json(cls, res, *args, **kwargs):
        """Parses JSON from a response."""
        return parse_json(res.text, *args, **kwargs)

    @classmethod
    def xml(cls, res, *args, **kwargs):
        """Parses XML from a response."""
        return parse_xml(res.text, *args, **kwargs)

    def parse_cookies(self, cookies, **kwargs):
        """Parses a semi-colon delimited list of cookies.

        Example: foo=bar;baz=qux
        """
        for name, value in _parse_keyvalue_list(cookies):
            self.cookies.set(name, value, **kwargs)

    def parse_headers(self, headers):
        """Parses a semi-colon delimited list of headers.

        Example: foo=bar;baz=qux
        """
        for name, value in _parse_keyvalue_list(headers):
            self.headers[name] = value

    def parse_query_params(self, cookies, **kwargs):
        """Parses a semi-colon delimited list of query parameters.

        Example: foo=bar;baz=qux
        """
        for name, value in _parse_keyvalue_list(cookies):
            self.params[name] = value

    def request(self, method, url, *args, **kwargs):
        exception = kwargs.pop("exception", PluginError)
        headers = kwargs.pop("headers", {})
        params = kwargs.pop("params", {})
        proxies = kwargs.pop("proxies", self.proxies)
        session = kwargs.pop("session", None)
        timeout = kwargs.pop("timeout", 20)

        if session:
            headers.update(session.headers)
            params.update(session.params)

        try:
            res = Session.request(self, method, url,
                                  headers=headers,
                                  params=params,
                                  timeout=timeout,
                                  proxies=proxies,
                                  *args, **kwargs)
            res.raise_for_status()
        except (RequestException, IOError) as rerr:
            err = exception("Unable to open URL: {url} ({err})".format(url=url,
                                                                       err=rerr))
            err.err = rerr
            raise err

        return res
