import os
import uuid
import cadquery as cq
from cadquery import exporters
from flask import Flask, request, jsonify, render_template, send_file
import anthropic

app = Flask(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """\
You are a CadQuery expert. When the user describes a 3D model, respond with Python code that creates it.

Rules:
- Import cadquery as cq at the top of the code
- Assign the final 3D solid to a variable called `result` (a CadQuery Workplane)
- Only use cadquery — no file I/O, os, sys, subprocess, or other imports
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

# Session history keyed by session_id
_sessions: dict[str, list] = {}

# Allowed builtins for exec sandbox
_SAFE_BUILTINS = {
    k: v for k, v in __builtins__.items()  # type: ignore[union-attr]
    if k in {
        "range", "len", "int", "float", "str", "bool", "list", "dict",
        "tuple", "set", "abs", "max", "min", "round", "sum", "zip",
        "enumerate", "map", "filter", "sorted", "reversed",
        "True", "False", "None", "print",
    }
} if isinstance(__builtins__, dict) else {
    "range": range, "len": len, "int": int, "float": float, "str": str,
    "bool": bool, "list": list, "dict": dict, "tuple": tuple, "set": set,
    "abs": abs, "max": max, "min": min, "round": round, "sum": sum,
    "zip": zip, "enumerate": enumerate, "map": map, "filter": filter,
    "sorted": sorted, "reversed": reversed,
    "True": True, "False": False, "None": None, "print": print,
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


def _try_3mf(result, model_id: str) -> bool:
    path = os.path.join(MODELS_DIR, f"{model_id}.3mf")
    try:
        exporters.export(result, path)
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        pass
    # Fallback: convert STL → 3MF via trimesh
    try:
        import trimesh  # type: ignore
        stl_path = os.path.join(MODELS_DIR, f"{model_id}.stl")
        mesh = trimesh.load(stl_path)
        mesh.export(path)
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    message = data.get("message", "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not message:
        return jsonify({"error": "empty message"}), 400

    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": message})

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})

    code = _extract_code(reply)
    model_id = str(uuid.uuid4())

    try:
        result = _run_cadquery(code)
        stl_path = os.path.join(MODELS_DIR, f"{model_id}.stl")
        exporters.export(result, stl_path)
        has_3mf = _try_3mf(result, model_id)

        return jsonify({
            "success": True,
            "session_id": session_id,
            "model_id": model_id,
            "code": code,
            "has_3mf": has_3mf,
        })
    except Exception as exc:
        return jsonify({
            "success": False,
            "session_id": session_id,
            "code": code,
            "error": str(exc),
        })


@app.route("/model/<model_id>.stl")
def serve_stl(model_id: str):
    path = os.path.join(MODELS_DIR, f"{model_id}.stl")
    if not os.path.exists(path):
        return "not found", 404
    return send_file(path, mimetype="model/stl")


@app.route("/download/<model_id>/<fmt>")
def download(model_id: str, fmt: str):
    if fmt not in ("stl", "3mf"):
        return "unsupported format", 400
    path = os.path.join(MODELS_DIR, f"{model_id}.{fmt}")
    if not os.path.exists(path):
        return "not found", 404
    return send_file(path, as_attachment=True, download_name=f"model.{fmt}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
