"""获取固定版本 Panda 资产；校验上游 blob，不覆盖不同内容的已有文件。"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1, sha256
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

COMMIT = "822c2d8f877dd166c5b7d3c9f7e3c3b6589473b7"
REPO = "google-deepmind/mujoco_menagerie"
PREFIX = "franka_emika_panda/"
ROOT = Path(__file__).resolve().parents[1] / "assets" / "robots" / "panda"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Robots-Panda-asset-fetch"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read()


def main() -> None:
    raw = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{PREFIX}"
    xml = fetch(raw + "panda.xml")
    required = {"panda.xml", "scene.xml", "LICENSE", "README.md"}
    required.update("assets/" + node.attrib["file"] for node in ET.fromstring(xml).findall("asset/mesh"))
    tree = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1"))
    blobs = {entry["path"]: entry["sha"] for entry in tree["tree"] if entry["type"] == "blob"}

    def download(name: str) -> tuple[str, str]:
        target = ROOT / name
        data = target.read_bytes() if target.exists() else (xml if name == "panda.xml" else fetch(raw + name))
        blob = sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != blobs[PREFIX + name]:
            raise ValueError(f"资产内容与固定上游版本不一致，未覆盖：{target}")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return name, sha256(data).hexdigest()

    with ThreadPoolExecutor(max_workers=4) as pool:
        checksums = dict(pool.map(download, sorted(required)))
    manifest = {"repository": f"https://github.com/{REPO}", "commit": COMMIT,
                "directory": PREFIX, "license": "Apache-2.0", "sha256": checksums}
    target = ROOT / "SOURCES.json"
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != encoded:
        raise ValueError("已有来源清单不同，不自动覆盖")
    target.write_bytes(encoded.encode("utf-8"))
    print(json.dumps({"root": str(ROOT), "commit": COMMIT, "files": len(checksums),
                      "bytes": sum((ROOT / name).stat().st_size for name in checksums)}))


if __name__ == "__main__":
    main()
