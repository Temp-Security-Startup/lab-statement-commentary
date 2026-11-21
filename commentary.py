"""Quarterly statement-commentary job.

Drafts each client's portfolio commentary for the quarterly statement, one OpenRouter request per
client. Reads its settings from config/llm.yaml:
  api_key_file: /etc/statement-commentary/openrouter.key   (a local copy of the key)
  api_key: vault:secret/openrouter/statement-commentary    (or: read the key from Vault)

  python3 commentary.py [--dry-run] [--sample N] [--quarter 2026-Q3]
--dry-run drafts the commentary but writes it to /out/dry-run/ instead of the statement run.
"""
import argparse, json, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def settings():
    conf = {}
    for line in open(os.path.join(HERE, "config", "llm.yaml")):
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            conf[k.strip()] = v.strip()
    return conf


def api_key(conf):
    if "api_key" in conf and conf["api_key"].startswith("vault:"):
        path = conf["api_key"][len("vault:"):].replace("secret/", "secret/data/", 1)
        token = open(os.environ.get("VAULT_TOKEN_FILE", "/vault-tokens/statement-commentary")).read().strip()
        r = urllib.request.Request(f"{os.environ['VAULT_ADDR']}/v1/{path}", headers={"X-Vault-Token": token})
        return json.load(urllib.request.urlopen(r))["data"]["data"]["api_key"]
    return open(conf["api_key_file"]).read().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--quarter", default=time.strftime("%Y") + "-Q4")
    a = ap.parse_args()
    conf = settings()
    key = api_key(conf)
    clients = [l.strip() for l in open(os.path.join(HERE, "clients.txt")) if l.strip()]
    if a.sample:
        clients = clients[: a.sample]
    outdir = "/out/dry-run" if a.dry_run else "/out/statements"
    os.makedirs(outdir, exist_ok=True)
    ok = failed = 0
    for c in clients:
        body = json.dumps({"model": conf.get("model", "commentary-model"),
                           "messages": [{"role": "user", "content": f"Portfolio commentary for {c}, {a.quarter}"}]}).encode()
        req = urllib.request.Request(f"{os.environ['OPENROUTER_URL']}/api/v1/chat/completions", data=body,
                                     headers={"authorization": "Bearer " + key, "content-type": "application/json"})
        try:
            resp = json.load(urllib.request.urlopen(req))
            open(os.path.join(outdir, f"{c}-{a.quarter}.txt"), "w").write(resp["choices"][0]["message"]["content"])
            ok += 1
        except urllib.error.HTTPError as e:
            print(f"{c}: OpenRouter {e.code} {e.read().decode()[:120]}", file=sys.stderr)
            failed += 1
    print(json.dumps({"quarter": a.quarter, "dry_run": a.dry_run, "statements": ok, "failed": failed}))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
