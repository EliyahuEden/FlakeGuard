"""Copy sanitized projections of existing actual reports; never runs/modifies CommerceGuard."""

import argparse
import hashlib
import json
from pathlib import Path

from flakeguard.failures import redact
from flakeguard.parsers import parse_report, relative_file

parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path, help="Path to the separate CommerceGuard checkout")
args = parser.parse_args()
destination = Path("examples/reports")
destination.mkdir(parents=True, exist_ok=True)
sources = [
    (
        "docs/evidence/redesign/regression-verified-raw.json",
        "commerceguard-regression.json",
        "real",
    ),
    (
        "docs/evidence/redesign/defects/CG-D01/injected/results.json",
        "commerceguard-injected.json",
        "injected",
    ),
    (
        "docs/evidence/redesign/defects/CG-D01/restored/results.json",
        "commerceguard-restored.json",
        "real",
    ),
]
manifest = []
for origin, name, provenance in sources:
    raw = (args.source / origin).read_bytes()
    data = json.loads(raw)
    root = data["config"]["rootDir"]

    def sanitize(value, report_root=root):
        if isinstance(value, dict):
            excluded = {
                "stdout",
                "stderr",
                "argv",
                "configFile",
                "outputDir",
                "metadata",
                "body",
                "snippet",
            }
            return {key: sanitize(child) for key, child in value.items() if key not in excluded}
        if isinstance(value, list):
            return [sanitize(child) for child in value]
        if isinstance(value, str):
            value = value.replace(report_root, "<commerceguard>").replace(
                report_root.replace("/", "\\"), "<commerceguard>"
            )
            value = value.replace(str(args.source.resolve()), "<commerceguard>")
            return redact(value)
        return value

    def suites(items, report_root=root):
        for suite in items:
            if suite.get("file"):
                suite["file"] = relative_file(suite["file"], report_root)
            for spec in suite.get("specs", []):
                if spec.get("file"):
                    spec["file"] = relative_file(spec["file"], report_root)
            suites(suite.get("suites", []))

    suites(data["suites"])
    sanitized = sanitize(data)
    sanitized["config"]["rootDir"] = "."
    content = json.dumps(sanitized, indent=2, ensure_ascii=False).encode("utf-8")
    parsed = parse_report(content, name)
    (destination / name).write_bytes(content)
    manifest.append(
        {
            "file": name,
            "source_relative_path": origin,
            "original_sha256": hashlib.sha256(raw).hexdigest(),
            "provenance": provenance,
            "executions": len(parsed.results),
            "report_timestamp": parsed.executed_at.isoformat() if parsed.executed_at else None,
            "note": "Sanitized projection of an existing actual CommerceGuard Playwright execution. Not rerun by FlakeGuard; browser not inferred from project name.",
        }
    )
Path("docs/evidence").mkdir(parents=True, exist_ok=True)
Path("docs/evidence/commerceguard.json").write_text(
    json.dumps(manifest, indent=2), encoding="utf-8"
)
print(
    json.dumps(
        [
            {k: v for k, v in item.items() if k in {"file", "executions", "provenance"}}
            for item in manifest
        ]
    )
)
