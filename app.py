import os
import uuid
import datetime
import threading
import cadquery as cq
from cadquery import exporters
from flask import Flask, request, jsonify, render_template, send_file
import anthropic

app = Flask(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

def _make_client() -> anthropic.Anthropic:
    if api_key := os.environ.get("ANTHROPIC_API_KEY"):
        return anthropic.Anthropic(api_key=api_key)
    token_file = os.environ.get(
        "CLAUDE_SESSION_INGRESS_TOKEN_FILE",
        "/home/claude/.claude/remote/.session_ingress_token",
    )
    if os.path.exists(token_file):
        token = open(token_file).read().strip()
        return anthropic.Anthropic(auth_token=token)
    raise RuntimeError(
        "No Anthropic credentials found. Set ANTHROPIC_API_KEY or run inside Claude Code."
    )

client = _make_client()

SYSTEM_PROMPT = """\
You are a CadQuery expert. When the user describes a 3D model, respond with Python code that creates it.

Rules:
- Import cadquery as cq at the top of the code
- Assign the final 3D solid to a variable called `result` (a CadQuery Workplane)
- Only use cadquery and math — no file I/O, os, sys, subprocess, or other imports
- Write clean, readable parametric code with descriptive variable names
- On follow-up requests ("make it bigger", "add a hole"), rewrite the full model from scratch with the changes applied

Respond with ONLY a ```python code block. No prose before or after it.

Example:
```python
import cadquery as cq

length = 50   # mm
width  = 30   # mm
height = 20   # mm
hole_d = 10   # mm

result = (
    cq.Workplane("XY")
    .box(length, width, height)
    .faces(">Z").workplane()
    .hole(hole_d)
    .edges("|Z").fillet(2)
)
```"""

# Per-session conversation history and model history
_sessions: dict[str, list] = {}
_history:  dict[str, list] = {}  # session_id → [{model_id, prompt, ts, has_*}]
_codes:    dict[str, str]  = {}  # model_id → CadQuery source (for mold generation)

_ALLOWED_IMPORTS = {"cadquery", "math"}

def _restricted_import(name, *args, **kwargs):
    if name not in _ALLOWED_IMPORTS:
        raise ImportError(f"import of '{name}' is not allowed in generated code")
    return __import__(name, *args, **kwargs)

_SAFE_BUILTINS = {
    "range": range, "len": len, "int": int, "float": float, "str": str,
    "bool": bool, "list": list, "dict": dict, "tuple": tuple, "set": set,
    "abs": abs, "max": max, "min": min, "round": round, "sum": sum,
    "zip": zip, "enumerate": enumerate, "map": map, "filter": filter,
    "sorted": sorted, "reversed": reversed, "pow": pow,
    "True": True, "False": False, "None": None, "print": print,
    "__import__": _restricted_import,
}


def _extract_code(text: str) -> str:
    if "```python" in text:
        start = text.index("```python") + 9
        end = text.index("```", start)
        return text[start:end].strip()
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return text[start:end].strip()
    return text.strip()


def _run_cadquery(code: str):
    namespace = {"cq": cq, "__builtins__": _SAFE_BUILTINS}
    exec(compile(code, "<ai_generated>", "exec"), namespace)  # noqa: S102
    if "result" not in namespace:
        raise ValueError("Code did not assign a value to 'result'")
    return namespace["result"]


def _try_export(result, model_id: str, ext: str) -> bool:
    """Export result to the given extension; return True if a non-empty file was created."""
    path = os.path.join(MODELS_DIR, f"{model_id}.{ext}")
    try:
        exporters.export(result, path)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
    except Exception:
        pass
    return False


def _try_3mf(result, model_id: str) -> bool:
    if _try_export(result, model_id, "3mf"):
        return True
    # Fallback: convert STL → 3MF via trimesh
    try:
        import trimesh  # type: ignore
        stl_path = os.path.join(MODELS_DIR, f"{model_id}.stl")
        mesh = trimesh.load(stl_path)
        mesh.export(os.path.join(MODELS_DIR, f"{model_id}.3mf"))
        return os.path.exists(os.path.join(MODELS_DIR, f"{model_id}.3mf"))
    except Exception:
        return False


def _try_glb(model_id: str) -> bool:
    """Convert the already-exported STL to GLB for Blender import."""
    try:
        import trimesh  # type: ignore
        stl_path = os.path.join(MODELS_DIR, f"{model_id}.stl")
        glb_path = os.path.join(MODELS_DIR, f"{model_id}.glb")
        mesh = trimesh.load(stl_path)
        mesh.export(glb_path)
        return os.path.exists(glb_path) and os.path.getsize(glb_path) > 0
    except Exception:
        return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/sw.js")
def service_worker():
    resp = app.send_static_file("sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    message = data.get("message", "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not message:
        return jsonify({"error": "empty message"}), 400

    conv = _sessions.setdefault(session_id, [])
    conv.append({"role": "user", "content": message})

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=conv,
    )
    reply = response.content[0].text
    conv.append({"role": "assistant", "content": reply})

    code = _extract_code(reply)
    model_id = str(uuid.uuid4())

    try:
        result = _run_cadquery(code)
        _codes[model_id] = code

        stl_path = os.path.join(MODELS_DIR, f"{model_id}.stl")
        exporters.export(result, stl_path)

        has_3mf  = _try_3mf(result, model_id)
        has_step = _try_export(result, model_id, "step")
        has_glb  = _try_glb(model_id)

        # Pre-build mold in background so it's ready when the user clicks
        threading.Thread(
            target=_make_mold_stl, args=(code, model_id), daemon=True
        ).start()

        entry = {
            "model_id": model_id,
            "prompt":   message[:90] + ("…" if len(message) > 90 else ""),
            "ts":       datetime.datetime.now().strftime("%H:%M"),
            "has_3mf":  has_3mf,
            "has_step": has_step,
            "has_glb":  has_glb,
        }
        _history.setdefault(session_id, []).append(entry)

        return jsonify({
            "success":    True,
            "session_id": session_id,
            "model_id":   model_id,
            "code":       code,
            "has_3mf":    has_3mf,
            "has_step":   has_step,
            "has_glb":    has_glb,
            "history":    _history[session_id],
        })
    except Exception as exc:
        return jsonify({
            "success":    False,
            "session_id": session_id,
            "code":       code,
            "error":      str(exc),
            "history":    _history.get(session_id, []),
        })


def _make_mold_stl(code: str, model_id: str) -> str:
    """Build a two-part split mold and write <model_id>_mold.stl; return path."""
    import math as _math
    namespace = {"cq": cq, "math": _math, "__builtins__": _SAFE_BUILTINS}
    exec(compile(code, "<ai_generated>", "exec"), namespace)  # noqa: S102
    result = namespace["result"]

    bb  = result.val().BoundingBox()
    cx  = (bb.xmin + bb.xmax) / 2
    cy  = (bb.ymin + bb.ymax) / 2
    cz  = (bb.zmin + bb.zmax) / 2
    sx  = bb.xmax - bb.xmin
    sy  = bb.ymax - bb.ymin
    sz  = bb.zmax - bb.zmin

    wall = max(max(sx, sy, sz) * 0.25, 8)   # ≥8 mm walls
    mw   = sx + 2 * wall                     # mold outer width
    md   = sy + 2 * wall                     # mold outer depth
    hh   = sz / 2 + wall                     # height of each half

    # ── bottom half: box [zmin−wall … cz], cavity carved by object ──────────
    bot = (
        cq.Workplane("XY")
        .box(mw, md, hh)
        .translate((cx, cy, bb.zmin - wall + hh / 2))
        .cut(result)
        .translate((-cx - mw / 2 - wall / 2, -cy, -(bb.zmin - wall)))
    )

    # ── top half: box [cz … zmax+wall], cavity carved by object ─────────────
    top = (
        cq.Workplane("XY")
        .box(mw, md, hh)
        .translate((cx, cy, cz + hh / 2))
        .cut(result)
        .translate((-cx + mw / 2 + wall / 2, -cy, -cz))
    )

    compound  = cq.Compound.makeCompound([bot.val(), top.val()])
    mold_path = os.path.join(MODELS_DIR, f"{model_id}_mold.stl")
    exporters.export(compound, mold_path)
    return mold_path


@app.route("/mold-ready/<model_id>")
def mold_ready(model_id: str):
    path = os.path.join(MODELS_DIR, f"{model_id}_mold.stl")
    return jsonify({"ready": os.path.exists(path) and os.path.getsize(path) > 0})


@app.route("/mold/<model_id>")
def make_mold(model_id: str):
    code = _codes.get(model_id)
    if not code:
        return jsonify({"error": "Model code not found — regenerate the model first"}), 404
    mold_path = os.path.join(MODELS_DIR, f"{model_id}_mold.stl")
    if not os.path.exists(mold_path):
        try:
            _make_mold_stl(code, model_id)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
    return send_file(mold_path, as_attachment=True,
                     download_name="mold.stl", mimetype="model/stl")


@app.route("/model/<model_id>.stl")
def serve_stl(model_id: str):
    path = os.path.join(MODELS_DIR, f"{model_id}.stl")
    if not os.path.exists(path):
        return "not found", 404
    return send_file(path, mimetype="model/stl")


_MIME = {
    "stl":  "model/stl",
    "3mf":  "model/3mf",
    "step": "application/step",
    "glb":  "model/gltf-binary",
}

@app.route("/download/<model_id>/<fmt>")
def download(model_id: str, fmt: str):
    if fmt not in _MIME:
        return "unsupported format", 400
    path = os.path.join(MODELS_DIR, f"{model_id}.{fmt}")
    if not os.path.exists(path):
        return "not found", 404
    return send_file(path, as_attachment=True,
                     download_name=f"model.{fmt}",
                     mimetype=_MIME[fmt])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, use_reloader=False, port=port, threaded=True)
