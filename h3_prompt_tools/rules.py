from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import normalize_mode


class RuleBundle:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        manifest_path = self.root / "manifest.json"
        self.manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))

    @property
    def styles(self) -> tuple[str, ...]:
        return tuple(self.manifest["styles"].keys())

    def _read(self, relative_path: str) -> str:
        path = (self.root / relative_path).resolve()
        if self.root not in path.parents:
            raise ValueError(f"Rule path escapes bundle root: {relative_path}")
        return path.read_text(encoding="utf-8").strip()

    def compose(self, workflow_mode: str, style: str = "None") -> str:
        mode = normalize_mode(workflow_mode)
        styles = self.manifest["styles"]
        if style not in styles:
            raise ValueError(f"Unknown H3 style: {style!r}")

        sections = [self._read(path) for path in self.manifest["composition"]["always"]]
        sections.append(self._read(self.manifest["composition"]["mode"][mode]))
        style_path = styles[style]
        if style_path:
            sections.append(self._read(self.manifest["composition"]["optional_style_contract"]))
            sections.append(self._read(style_path))
        return "\n\n---\n\n".join(sections).strip() + "\n"

