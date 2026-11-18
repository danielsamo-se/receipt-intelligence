"""Explicit setup-only download. Runtime embedding never accesses the network."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
lock = json.loads((ROOT / "app/data/embedding_model.json").read_text(encoding="utf-8"))
target = ROOT / "app/.local/embeddings" / lock["revision"]
for name, expected in lock["files"].items():
    path = target / Path(name).name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
        print("Verified:", name)
        continue
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".download")
    url = f"https://huggingface.co/{lock['model']}/resolve/{lock['revision']}/{name}"
    digest = hashlib.sha256()
    with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise RuntimeError("Downloaded file failed SHA-256 verification: " + name)
    temporary.replace(path)
    print("Downloaded and verified:", name)
print("Local semantic retrieval ready. No Jev requests made.")
