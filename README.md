# AI 3D Model Builder

A web app that uses Claude AI and CadQuery to generate editable 3D models from natural language descriptions, with export to STL and 3MF (ready for 3D printing or CAD import).

## How it works

1. Describe a 3D model in plain English ("a flanged cylinder 60 mm tall with a 5 mm wall")
2. Claude generates [CadQuery](https://cadquery.readthedocs.io/) Python code for the model
3. The model renders live in the browser (Three.js viewer)
4. Refine it conversationally ("add a 2 mm fillet to the top edges")
5. Download as **STL** or **3MF**

CadQuery is an open-source parametric CAD library built on OpenCASCADE — no AutoCAD license needed. The exported DXF/STEP/STL files open in AutoCAD, Fusion 360, or any slicer.

## Setup

```bash
# 1. Clone and install dependencies
pip install -r requirements.txt

# 2. Set your Anthropic API key
cp .env.example .env
# edit .env and add your key

# 3. Start the server
ANTHROPIC_API_KEY=sk-ant-... python app.py
```

Then open http://localhost:5000 in your browser.

## Deploy to Railway

```bash
npm install -g @railway/cli   # if you don't have it
railway login
railway init                  # or: railway link, if the project already exists
railway variables --set ANTHROPIC_API_KEY=sk-ant-...
railway up
```

Railway auto-detects `railway.toml` and builds from the `Dockerfile`. It
injects its own `PORT` env var at runtime, which `app.py` already reads
(`os.environ.get("PORT", 5000)`), and serves the app over HTTPS by default —
required for installing it as a PWA on your phone. Once deployed, open the
generated `*.up.railway.app` URL on your phone and use "Add to Home Screen".

## Deploy with Docker (any host)

```bash
docker build -t ai3d-builder .
docker run -p 5000:5000 -e ANTHROPIC_API_KEY=sk-ant-... ai3d-builder
```

This runs the app behind gunicorn. Deploy the image to any Docker-capable
host (Render, Fly.io, a VPS, etc.) and set `ANTHROPIC_API_KEY` as a runtime
environment variable/secret on that platform.

## Example prompts

- `A 50×30×20 mm rectangular box with a 10 mm through-hole and 2 mm edge fillets`
- `A flanged pipe fitting: 80 mm tall, 30 mm OD, 4 mm wall, 60 mm circular flange`
- `A mounting bracket: L-shaped, 40×40 mm arms, 5 mm thick, four M4 counterbored holes`
- `A hexagonal nut M10, standard dimensions`

Follow-up refinements work too: *"Make the hole bigger"*, *"Add a chamfer to the bottom"*.

## Tech stack

| Layer | Library |
|-------|---------|
| AI | [Anthropic Claude](https://anthropic.com) (claude-opus-4-8) |
| CAD engine | [CadQuery 2.x](https://cadquery.readthedocs.io/) / OpenCASCADE |
| 3MF conversion | [trimesh](https://trimesh.org/) |
| Web server | Flask |
| 3D preview | Three.js (STL Loader) |

## Security note

This app executes AI-generated Python code in a restricted sandbox (limited builtins, CadQuery only). It is intended for personal/local use. Do not expose it to the public internet without additional hardening.
