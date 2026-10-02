import os, sys, base64, secrets

key = os.environ.get("CF_API_KEY", "").strip()
if not key:
    print("ERROR: CF_API_KEY is empty. Add it under Settings > Secrets and variables > Actions.")
    sys.exit(1)

raw = key.encode("utf-8")
pad = secrets.token_bytes(max(32, len(raw)))
blob = bytes(b ^ pad[i] for i, b in enumerate(raw))

with open("_cf_secret.py", "w", encoding="utf-8") as f:
    f.write(f'_A = "{base64.b64encode(pad).decode()}"\n')
    f.write(f'_B = "{base64.b64encode(blob).decode()}"\n')
print("_cf_secret.py written (key not printed).")
