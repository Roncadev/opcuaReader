"""
OPC UA security tool of the AINIMA client (2026-11-23). Run it on the machine
PC from C:\\app\\ainima_client with the client's Python:

    venv\\Scripts\\python.exe opcua_tool.py --endpoints         read only: what the PLC offers
    venv\\Scripts\\python.exe opcua_tool.py --new-cert          new client certificate (20 years)
    venv\\Scripts\\python.exe opcua_tool.py --save-server-cert  trust the PLC certificate (pinning)
    venv\\Scripts\\python.exe opcua_tool.py --test              test login with config.yaml security

--endpoints and --test never change the PLC or the running client (--test
opens a second session, reads the server time and closes it). --new-cert keeps
the old files as *.old_<time>; the running client keeps the certificate it
loaded until /restart_client. Never prints passwords or the private key.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.utils import opcua_security as sec


def _client_cfg() -> dict:
    from config.config import ConfigLoader
    cfg = ConfigLoader().get_opcua_client_config() or {}
    return cfg


def _url(args) -> str:
    url = (args.url or str(_client_cfg().get("url", "") or "")).strip()
    if not url:
        sys.exit("opcua.client.url missing in config.yaml (or pass --url)")
    return url


async def _endpoints(url):
    from asyncua import Client
    c = Client(url=url)
    c.application_uri = sec.APP_URI
    return await c.connect_and_get_server_endpoints()


def _print_cert(title, data):
    try:
        i = sec.certificate_info(data)
        print(f"{title}: CN={i['subject_cn']} | valid {i['not_before']:%Y-%m-%d} -> {i['not_after']:%Y-%m-%d} "
              f"| uri={i['application_uri'] or '-'} | sha256={i['sha256'][:16]}...")
    except Exception as e:
        print(f"{title}: not readable ({type(e).__name__})")


def cmd_endpoints(args):
    url = _url(args)
    eps = asyncio.run(_endpoints(url))
    print(f"PLC {url}: {len(eps)} endpoints")
    for ep in eps:
        print("  " + sec.describe_endpoint(ep))
    server = next((ep.ServerCertificate for ep in eps if ep.ServerCertificate), None)
    if server:
        _print_cert("PLC certificate", server)
    pinned = sec.trusted_server_cert()
    print("Trusted PLC certificate (pki/%s): %s" % (sec.SERVER_CERT_FILE, "present" if pinned else "not set"))
    if pinned and server:
        err = sec.check_server_certificate(server)
        print("  -> " + ("MATCHES the PLC" if not err else "DOES NOT MATCH: " + err))
    cert_path, _ = sec.cert_paths()
    if os.path.exists(cert_path):
        with open(cert_path, "rb") as f:
            _print_cert("Client certificate", f.read())
    else:
        print("Client certificate: none in pki/")
    return 0


def cmd_new_cert(args):
    info = sec.generate_client_certificate(force=True, days=args.days)
    with open(info["cert"], "rb") as f:
        _print_cert("New client certificate", f.read())
    print(f"File to import in TIA Portal (trusted clients): {info['der']}")
    if info["replaced"]:
        print("The old certificate and key are kept in pki/ as *.old_<time>.")
    print("The running client keeps using the old one until /restart_client.")
    return 0


def cmd_save_server_cert(args):
    url = _url(args)
    eps = asyncio.run(_endpoints(url))
    secure = [ep for ep in eps if ep.ServerCertificate and "Basic256Sha256" in str(ep.SecurityPolicyUri)]
    ep = secure[0] if secure else next((ep for ep in eps if ep.ServerCertificate), None)
    if ep is None:
        sys.exit("The PLC sent no certificate: is a secure policy enabled in TIA?")
    _print_cert("PLC certificate", ep.ServerCertificate)
    path = sec.save_trusted_server_cert(ep.ServerCertificate)
    print(f"Saved as trusted: {path}")
    print("From now on the client connects (with security) only to a PLC presenting this certificate.")
    return 0


async def _test(url, cfg):
    from asyncua import ua

    from app.utils.opcua_utils import OPCUAExplorer
    raw = next((v for k, v in cfg.items() if isinstance(k, str) and k.lower() == "autenticazione"), False)
    auth = str(raw).strip().lower() in ("1", "true", "yes", "si", "sì", "on")
    username = str(cfg.get("username", "") or "").strip() if auth else ""
    password = str(cfg.get("password", "") or "").strip() if auth else ""
    mode = str(cfg.get("security_mode", "") or "").strip() or ("Sign & Encrypt" if auth else "None")
    policy = str(cfg.get("security_policy", "") or "").strip() or ("Basic256SHA256" if auth else "None")
    print(f"Test: user={'(guest)' if not auth else username or '?'} | policy={policy} | mode={mode}")
    ex = OPCUAExplorer(url, anonymous=not auth, username=username or None, password=password or None,
                       security_mode=mode, security_policy=policy)
    await ex.connect()
    try:
        node = ex.client.get_node(ua.ObjectIds.Server_ServerStatus_CurrentTime)
        print(f"Connected. PLC time: {await node.read_value()}")
    finally:
        await ex.disconnect()


def cmd_test(args):
    cfg = _client_cfg()
    asyncio.run(_test(_url(args), cfg))
    print("Test OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--endpoints", action="store_true")
    g.add_argument("--new-cert", action="store_true")
    g.add_argument("--save-server-cert", action="store_true")
    g.add_argument("--test", action="store_true")
    ap.add_argument("--url", help="PLC endpoint (default: opcua.client.url of config.yaml)")
    ap.add_argument("--days", type=int, default=sec.CERT_DAYS, help="client certificate validity (default 7300 = 20 years)")
    args = ap.parse_args(argv)
    if args.endpoints:
        return cmd_endpoints(args)
    if args.new_cert:
        return cmd_new_cert(args)
    if args.save_server_cert:
        return cmd_save_server_cert(args)
    return cmd_test(args)


if __name__ == "__main__":
    sys.exit(main())
