"""Build a CA bundle that includes the OS trust store, for libs that ignore it.

`truststore` (injected in config.py) fixes stdlib ssl / requests / alpaca-py, but
some libs talk through their own libcurl/curl_cffi and read trust roots from the
CURL_CA_BUNDLE env var, NOT the Windows store. Behind this box's TLS-intercepting
proxy/AV that root lives only in the Windows store, so those libs fail with
"unable to get local issuer certificate".

This module exports the Windows ROOT + CA stores to PEM, concatenates certifi's
bundle, writes data_cache/ca_bundle.pem, and points CURL_CA_BUNDLE /
REQUESTS_CA_BUNDLE / SSL_CERT_FILE at it. Idempotent; safe no-op on non-Windows
or on any error. Ported from copper_brain/copper_brain/certs.py.
"""
from __future__ import annotations

import os
import ssl
from pathlib import Path

_BUNDLE: Path | None = None


def _windows_pem_blocks() -> list[str]:
    blocks: list[str] = []
    if not hasattr(ssl, "enum_certificates"):
        return blocks
    for store in ("ROOT", "CA"):
        try:
            for cert_bytes, enc, _trust in ssl.enum_certificates(store):
                if enc == "x509_asn":
                    blocks.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
        except Exception:  # noqa: BLE001
            continue
    return blocks


def ensure_ca_bundle(out_path: Path) -> Path | None:
    """Write a combined certifi + Windows-store PEM and set the env vars.

    Returns the bundle path, or None if it couldn't be built (env left as-is)."""
    global _BUNDLE
    if _BUNDLE is not None:
        return _BUNDLE
    try:
        import certifi
        pem = Path(certifi.where()).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pem = ""
    win = _windows_pem_blocks()
    if not pem and not win:
        return None
    combined = pem + "\n" + "\n".join(win)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(combined, encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None
    for var in ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        os.environ.setdefault(var, str(out_path))
    _BUNDLE = out_path
    return out_path
