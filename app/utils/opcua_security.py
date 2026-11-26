"""
OPC UA security of the AINIMA client towards the PLC (2026-11-23).

- Client certificate: RSA 2048, SHA-256, valid CERT_DAYS (20 years, up to
  ~2046: dates after 2049 use another encoding that some OPC UA stacks read
  badly), names and ApplicationUri of AINIMA. The ApplicationUri in the
  certificate must be the same the client announces (APP_URI): S7-1500 checks it.
- PLC certificate pinning: when pki/trusted_server_cert.der exists, the client
  connects only to a server presenting exactly that certificate (it is saved
  once with `opcua_tool.py --save-server-cert`). Without the file: no check.
- pki/ is next to ainima_client.py, whatever the working directory.
Pure functions: no asyncua here, so they are tested without it. The private
key is written with mode 600 where the OS allows it and is never printed.
"""
from __future__ import annotations

import hashlib
import os
import socket
from datetime import datetime, timedelta, timezone

APP_URI = "urn:AINIMA:OPCUA:VariablesReader"   # tool of the colleague, distinct from the plant client
APP_NAME = "AINIMA OPC UA VariablesReader"
CERT_DAYS = 7300                     # 20 years
CERT_FILE = "client_cert.pem"
CERT_DER_FILE = "client_cert.der"    # the copy to import into TIA Portal
KEY_FILE = "client_key.pem"
SERVER_CERT_FILE = "trusted_server_cert.der"

CLIENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def pki_dir(root: str | None = None) -> str:
    return os.path.join(root or CLIENT_ROOT, "pki")


def cert_paths(root: str | None = None) -> tuple[str, str]:
    d = pki_dir(root)
    return os.path.join(d, CERT_FILE), os.path.join(d, KEY_FILE)


def _write_private(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def generate_client_certificate(root: str | None = None, days: int = CERT_DAYS, force: bool = False,
                                now: datetime | None = None) -> dict:
    """Creates pki/client_key.pem, client_cert.pem and client_cert.der. With
    force=True the old files are kept as *.old_<timestamp> first. Returns
    {'cert': path, 'der': path, 'not_after': datetime, 'replaced': bool}."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    d = pki_dir(root)
    os.makedirs(d, exist_ok=True)
    cert_path, key_path = cert_paths(root)
    der_path = os.path.join(d, CERT_DER_FILE)
    exists = os.path.exists(cert_path) or os.path.exists(key_path)
    if exists and not force:
        raise FileExistsError("pki/ already has a client certificate: use force=True to replace it")
    now = now or datetime.now(timezone.utc)
    if exists:
        stamp = now.strftime("%Y%m%d_%H%M%S")
        for p in (cert_path, key_path, der_path):
            if os.path.exists(p):
                os.replace(p, f"{p}.old_{stamp}")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, APP_NAME),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AINIMA"),
    ])
    host = socket.gethostname() or "localhost"
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=10))
        .not_valid_after(now + timedelta(days=int(days)))
        .add_extension(x509.SubjectAlternativeName([
            x509.UniformResourceIdentifier(APP_URI), x509.DNSName(host)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=True,
                                     data_encipherment=True, key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH,
                                              ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private(key_path, key.private_bytes(serialization.Encoding.PEM,
                                               serialization.PrivateFormat.TraditionalOpenSSL,
                                               serialization.NoEncryption()))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(der_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.DER))
    return {"cert": cert_path, "der": der_path, "not_after": _not_after(cert), "replaced": exists}


def _not_after(cert):
    # cryptography < 42 has only the naive not_valid_after
    v = getattr(cert, "not_valid_after_utc", None)
    return v if v is not None else cert.not_valid_after.replace(tzinfo=timezone.utc)


def _not_before(cert):
    v = getattr(cert, "not_valid_before_utc", None)
    return v if v is not None else cert.not_valid_before.replace(tzinfo=timezone.utc)


def certificate_info(data: bytes) -> dict:
    """Subject CN, validity, ApplicationUri, SHA-256 thumbprint of a DER or PEM
    certificate (public data only)."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    cert = (x509.load_pem_x509_certificate(data) if data.lstrip().startswith(b"-----BEGIN")
            else x509.load_der_x509_certificate(data))
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        uris = san.get_values_for_type(x509.UniformResourceIdentifier)
    except x509.ExtensionNotFound:
        uris = []
    from cryptography.hazmat.primitives import serialization
    der = cert.public_bytes(serialization.Encoding.DER)
    return {
        "subject_cn": cn[0].value if cn else "",
        "not_before": _not_before(cert),
        "not_after": _not_after(cert),
        "application_uri": uris[0] if uris else "",
        "sha256": hashlib.sha256(der).hexdigest(),
    }


def thumbprint(der: bytes) -> str:
    return hashlib.sha256(der or b"").hexdigest()


def trusted_server_cert(root: str | None = None) -> bytes | None:
    p = os.path.join(pki_dir(root), SERVER_CERT_FILE)
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None


def save_trusted_server_cert(der: bytes, root: str | None = None) -> str:
    d = pki_dir(root)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, SERVER_CERT_FILE)
    with open(p, "wb") as f:
        f.write(der)
    return p


def check_server_certificate(presented: bytes | None, root: str | None = None) -> str:
    """'' when the PLC certificate is accepted, else the reason. No pinned file:
    accepted (pinning not configured)."""
    pinned = trusted_server_cert(root)
    if pinned is None:
        return ""
    if not presented:
        return "the PLC sent no certificate"
    if thumbprint(presented) != thumbprint(pinned):
        return (f"PLC certificate {thumbprint(presented)[:16]}... is not the trusted one "
                f"{thumbprint(pinned)[:16]}... (pki/{SERVER_CERT_FILE})")
    return ""


def describe_endpoint(ep) -> str:
    """One line per endpoint: policy, mode, login types (works on asyncua
    EndpointDescription or any object with the same attributes)."""
    policy = str(getattr(ep, "SecurityPolicyUri", "") or "").rsplit("#", 1)[-1] or "?"
    mode = getattr(ep, "SecurityMode", "")
    mode = getattr(mode, "name", None) or str(mode)
    tokens = []
    for t in getattr(ep, "UserIdentityTokens", None) or []:
        tt = getattr(t, "TokenType", "")
        tokens.append(getattr(tt, "name", None) or str(tt))
    return f"{getattr(ep, 'EndpointUrl', '')} | policy={policy} | mode={mode} | login={','.join(tokens) or '-'}"
