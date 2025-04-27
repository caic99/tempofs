from functools import cached_property
import requests
import io
import logging

class HTTPRangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url = url
        self.session = requests.Session()
        self.head = self.session.head(url=url)
        self.head.raise_for_status()
        self.size = int(self.head.headers.get("Content-Length", 0))
        self.pos = 0
        # Check if file is seekable based on Accept-Ranges header
    def seekable(self) -> bool:
        return self.is_seekable
    @cached_property
    def is_seekable(self):
        seekable = self.head.headers.get("Accept-Ranges") == "bytes"
        if not seekable:
            accept_ranges = self.head.headers.get("Accept-Ranges", "none")
            if accept_ranges not in ["none", "false", "False", "0", "no", "No"]:
                logging.warning(f"Unknown Accept-Ranges value: {accept_ranges}")
            logging.warning(f"File at {self.url} is not seekable, seek operations may fail")
        return seekable

    def readable(self):
        return True

    def read(self, size=-1):
        if size < 0:
            # Read until EOF in one request
            if self.pos >= self.size:
                return b''  # EOF
            end = self.size - 1
            resp = self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
            resp.raise_for_status()
            data = resp.content
            self.pos += len(data)
            return data
        elif size == 0:
            return b''
        else:
            # Read specified amount
            buffer = bytearray(size)
            n = self.readinto(buffer)
            if n < size:
                buffer = buffer[:n]
            return bytes(buffer)
    def readinto(self, b) -> int:
        if self.pos >= self.size:
            return 0  # EOF
        end = min(self.pos + len(b) - 1, self.size - 1)
        resp = self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        resp.raise_for_status()
        data = resp.content
        n = len(data)
        b[:n] = data
        self.pos += n
        return n

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            newpos = offset
        elif whence == io.SEEK_CUR:
            newpos = self.pos + offset
        elif whence == io.SEEK_END:
            newpos = self.size + offset
        else:
            raise ValueError("invalid whence")
        if newpos < 0:
            raise OSError("Negative seek position")
        self.pos = newpos
        return self.pos

    def tell(self):
        return self.pos

    def close(self):
        try:
            self.session.close()
        finally:
            super().close()

def open_http(url, mode="rb", encoding=None, errors=None, newline=None):
    """
    Open a remote URL for read access via HTTP Range requests.

    Parameters:
      - url: the HTTP(S) URL to open.
      - mode: 'rb' (binary, default) or 'r'/'rt' (text).
      - encoding: text encoding (e.g. 'utf-8'); defaults to locale.getpreferredencoding().
      - errors: error handling for decoding ('strict', 'ignore', etc.).
      - newline: newline translation mode (None, '', '\\n', '\\r\\n', etc.).

    Returns:
      - a file-like object supporting .read(), .seek(), .tell(), .close(), etc.
    """
    # Only reading is supported
    if any(m in mode for m in ("w", "a", "+")):
        raise ValueError("only read modes are supported ('rb' or 'r')")
    raw = HTTPRangeFile(url)
    buf = io.BufferedReader(raw)
    # Text mode?
    if "b" not in mode:
        # Default encoding if not specified
        encoding = encoding or io.text_encoding or io.TextIOBase().encoding
        return io.TextIOWrapper(buf, encoding=encoding, errors=errors, newline=newline)
    else:
        return buf


# ── Usage ──
if __name__ == "__main__":
    # Binary read:
    with open_http("https://modelcontextprotocol.io/introduction.md", "rb") as fbin:
        chunk = fbin.read(512)
        print(f"Read {len(chunk)} bytes in binary mode")

    # Text read with default UTF-8:
    with open_http(
        "https://modelcontextprotocol.io/introduction.md", "r", encoding="utf-8"
    ) as ftxt:
        line1 = ftxt.readline()
        print("First line:", line1.rstrip())
