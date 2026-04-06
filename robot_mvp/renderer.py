from __future__ import annotations

import json
from pathlib import Path

import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "web" / "robot_renderer" / "dist"
JS_BUNDLE = DIST_DIR / "renderer.js"


def bundle_available() -> bool:
    return JS_BUNDLE.exists()


def render_threejs_scene(
    payload: dict,
    fallback_html: str,
    *,
    height: int = 420,
) -> None:
    bundle_js = JS_BUNDLE.read_text(encoding="utf-8")
    payload_json = json.dumps(payload, ensure_ascii=False)
    html = f"""
    <div id="renderer-root" style="width:100%;height:{height - 12}px;"></div>
    <div id="renderer-fallback">{fallback_html}</div>
    <script>
      window.__ROBOT_RENDERER_PAYLOAD__ = {payload_json};
    </script>
    <script>
    {bundle_js}
    </script>
    <script>
    (function () {{
      const root = document.getElementById("renderer-root");
      const fallback = document.getElementById("renderer-fallback");
      try {{
        if (!window.RobotRenderer || typeof window.RobotRenderer.render !== "function") {{
          throw new Error("RobotRenderer bundle is not ready.");
        }}
        window.RobotRenderer.render(root, window.__ROBOT_RENDERER_PAYLOAD__);
        fallback.style.display = "none";
      }} catch (error) {{
        console.error("Three.js renderer failed, fallback to SVG.", error);
        root.style.display = "none";
        fallback.style.display = "block";
        const notice = document.createElement("div");
        notice.style.cssText = "margin:0 0 8px 0;padding:8px 10px;border-radius:10px;background:rgba(255,122,144,0.14);color:#ffd6dd;font:12px/1.4 sans-serif;";
        notice.textContent = "Three.js 渲染失败，已自动回退到 SVG 视图。";
        fallback.prepend(notice);
      }}
    }})();
    </script>
    """
    components.html(html, height=height, scrolling=False)
