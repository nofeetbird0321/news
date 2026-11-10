"""Record protected-field hashes for newly published articles (run once per new article; never to hide edits)."""
import hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "qa/source-lock.json"
FIELDS = ["id", "date", "published_at", "ingested_at", "source", "original"]
lock = json.loads(LOCK.read_text()) if LOCK.exists() else {"protected_fields": FIELDS, "sha256_by_id": {}}
for path in sorted((ROOT / "content/articles").glob("*.json")):
    a = json.loads(path.read_text(encoding="utf-8"))
    if a["id"] in lock["sha256_by_id"] and "--force" not in sys.argv:
        continue
    protected = {k: a[k] for k in lock["protected_fields"] if k in a}
    lock["sha256_by_id"][a["id"]] = hashlib.sha256(json.dumps(protected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print("locked", a["id"])
LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n")
