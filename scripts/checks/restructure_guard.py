"""
Restructure guard: prove that moving files did not change how the code behaves.

Take a snapshot before a change and another after it, then compare them:

    python scripts/checks/restructure_guard.py snapshot before.json
    # ... move files ...
    python scripts/checks/restructure_guard.py snapshot after.json
    python scripts/checks/restructure_guard.py compare before.json after.json

A snapshot records:
  - tests:   the outcome of every test (pytest junit XML)
  - modules: every module under the importable packages, whether it imports,
             and its public names
  - refs:    every first-party import statement in every tracked .py file
             (scripts included), and whether it still resolves
  - api:     the public API of the top-level ``cognicore`` package
  - cli:     ``cognicore --help`` output and the pyproject entry points
  - apps:    each deployable ASGI app, imported and asked for ``/health``
  - aliases: every old module path in ``cognicore._compat`` resolves to the
             same module object as its new path

``compare`` maps old module names and file paths to new ones using
``cognicore._compat.MOVED_MODULES`` and ``MOVED_PATHS`` from the *after* tree,
and fails if anything that worked before no longer works.
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

# Packages whose every module is imported. Script folders (benchmarks, examples,
# ...) are only checked statically, because importing a script runs it.
IMPORTABLE_PACKAGES = ["cognicore", "content_studio", "env", "server"]

FIRST_PARTY = {
    "cognicore", "content_studio", "env", "server", "api", "benchmarks",
    "cognicore_bench", "cognicore_benchmarks", "inference",
}

# Deploy files whose "module:attr" strings name ASGI apps to boot.
DEPLOY_FILES = ["railway.toml", "Procfile", "Dockerfile", "render.yaml", "fly.toml"]
EXTRA_APPS = ["server.app:app", "cognicore.server.app:create_app()"]

APP_ENV = {
    "COGNICORE_JWT_SECRET": "guard-secret",
    "COGNICORE_PUBLIC_URL": "http://localhost:8000",
    "GITHUB_CLIENT_ID": "guard",
    "GITHUB_CLIENT_SECRET": "guard",
    "COGNICORE_USE_SEMANTIC": "0",
    "SUPABASE_URL": "https://example.supabase.co",
}


def _run(code, timeout=120, env=None, cwd=ROOT):
    """Run python code in a fresh interpreter; return (rc, stdout, stderr)."""
    full_env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8", **(env or {}))
    try:
        p = subprocess.run([PY, "-c", code], cwd=cwd, capture_output=True, check=False, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=full_env)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"


def _tracked_py():
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, check=False, text=True).stdout
    return [p for p in out.splitlines() if (ROOT / p).exists()]


def _module_name(relpath):
    parts = Path(relpath).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


# --------------------------------------------------------------------------- tests

TEST_SUITES = ["tests", "plugins/cognicore-experience/tests"]


def snap_tests(tmp):
    results = {}
    for i, suite in enumerate(TEST_SUITES):
        xml = Path(tmp) / f"junit{i}.xml"
        subprocess.run([PY, "-m", "pytest", suite, "-q", "-n", "auto", "-p", "no:cacheprovider",
                        "-o", "addopts=", f"--junitxml={xml}"], cwd=ROOT, capture_output=True, check=False, text=True)
        for case in ET.parse(xml).getroot().iter("testcase"):
            nodeid = f"{suite}::{case.get('classname')}::{case.get('name')}"
            outcome = "passed"
            for child in case:
                if child.tag in ("failure", "error"):
                    outcome = "failed"
                elif child.tag == "skipped":
                    outcome = "skipped"
            results[nodeid] = outcome
    return results


# --------------------------------------------------------------------------- modules

def _import_module_check(name):
    code = (
        "import importlib, json\n"
        f"m = importlib.import_module({name!r})\n"
        "print('@@' + json.dumps(sorted(n for n in dir(m) if not n.startswith('_'))))\n"
    )
    # Some modules write files when imported; keep that out of the repo.
    with tempfile.TemporaryDirectory() as cwd:
        rc, out, err = _run(code, timeout=90, env={"COGNICORE_USE_SEMANTIC": "0"}, cwd=cwd)
    if rc == 0 and "@@" in out:
        return name, {"ok": True, "names": json.loads(out.split("@@", 1)[1].strip().splitlines()[0])}
    last = (err.strip().splitlines() or ["?"])[-1][:300]
    return name, {"ok": False, "error": last}


def snap_modules():
    names = sorted({
        _module_name(p) for p in _tracked_py()
        if Path(p).parts[0] in IMPORTABLE_PACKAGES and "__main__" not in p
    })
    with ThreadPoolExecutor(max_workers=max(4, (os.cpu_count() or 4))) as ex:
        results = dict(ex.map(_import_module_check, names))
    # Some script-like modules (cognicore.nexus.*) share files at import time and
    # can collide when imported in parallel; retry failures one at a time.
    for name in [n for n, r in results.items() if not r["ok"]]:
        results[name] = _import_module_check(name)[1]
    return results


# --------------------------------------------------------------------------- refs

def _collect_refs():
    """Every first-party import statement in every tracked .py file."""
    refs = []
    for rel in _tracked_py():
        path = ROOT / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            refs.append({"file": rel, "kind": "syntax", "target": ""})
            continue
        file_dir = path.parent
        pkg = _module_name(rel).rsplit(".", 1)[0] if "." in _module_name(rel) else ""
        if rel.endswith("__init__.py"):
            pkg = _module_name(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    refs.append(_ref(rel, file_dir, a.name, None))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = pkg.split(".")
                    if node.level > 1:
                        base = base[: len(base) - (node.level - 1)]
                    mod = ".".join([*base, node.module] if node.module else base)
                else:
                    mod = node.module or ""
                for a in node.names:
                    refs.append(_ref(rel, file_dir, mod, a.name))
    return [r for r in refs if r]


def _ref(rel, file_dir, module, name):
    top = module.split(".")[0]
    if top in FIRST_PARTY:
        return {"file": rel, "kind": "import", "module": module, "name": name}
    # Sibling-local import inside a script folder ("from tracker import X").
    if (file_dir / f"{top}.py").exists() or (file_dir / top).is_dir():
        sub = file_dir.joinpath(*module.split("."))
        ok = sub.with_suffix(".py").exists() or (sub / "__init__.py").exists() or sub.is_dir()
        return {"file": rel, "kind": "local", "module": module, "name": name, "ok": ok}
    return None


_RESOLVE = r"""
import ast, importlib, json, sys
from pathlib import Path
ROOT = Path.cwd()
FIRST_PARTY = set(json.loads(sys.argv[3]))

def source_of(module):
    p = ROOT.joinpath(*module.split('.'))
    for f in (p.with_suffix('.py'), p / '__init__.py'):
        if f.exists():
            return f
    return p if p.is_dir() else None

def top_level_names(path):
    names, star = set(), False
    def visit(body):
        nonlocal star
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(n.name)
            elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name):
                            names.add(x.id)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    if a.name == '*':
                        star = True
                    names.add(a.asname or a.name.split('.')[0])
            elif isinstance(n, (ast.If, ast.Try, ast.With)):
                visit(n.body)
                for h in getattr(n, 'handlers', []):
                    visit(h.body)
                visit(getattr(n, 'orelse', []))
                visit(getattr(n, 'finalbody', []))
    visit(ast.parse(path.read_text(encoding='utf-8', errors='replace')).body)
    return names, star

def static(module, name):
    # The import failed on a third-party package; check the first-party part on disk.
    src = source_of(module)
    if src is None:
        return 'static:missing module'
    if not name or name == '*' or source_of(module + '.' + name) is not None:
        return 'static:ok'
    if src.is_dir():
        return 'static:missing name'
    names, star = top_level_names(src)
    return 'static:ok' if (name in names or star) else 'static:missing name'

refs = json.load(open(sys.argv[1], encoding='utf-8'))
out = []
for r in refs:
    if r['kind'] != 'import':
        out.append(r.get('ok', r['kind'] != 'syntax')); continue
    try:
        m = importlib.import_module(r['module'])
        if r['name'] and r['name'] != '*' and not hasattr(m, r['name']):
            importlib.import_module(r['module'] + '.' + r['name'])
        out.append(True)
    except BaseException as e:
        missing = getattr(e, 'name', None)
        if isinstance(e, ModuleNotFoundError) and missing and missing.split('.')[0] not in FIRST_PARTY:
            out.append(static(r['module'], r['name']))
        else:
            out.append(type(e).__name__ + ': ' + str(e)[:200])
json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'))
"""


def snap_refs(tmp):
    refs = _collect_refs()
    unique = {}
    for r in refs:
        key = (r["kind"], r.get("module"), r.get("name"), r.get("ok"), r["file"] if r["kind"] != "import" else "")
        unique.setdefault(key, r)
    items = list(unique.values())
    src, dst = Path(tmp) / "refs_in.json", Path(tmp) / "refs_out.json"
    src.write_text(json.dumps(items), encoding="utf-8")
    script = Path(tmp) / "resolve.py"
    script.write_text(_RESOLVE, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT), COGNICORE_USE_SEMANTIC="0", PYTHONIOENCODING="utf-8")
    subprocess.run([PY, str(script), str(src), str(dst), json.dumps(sorted(FIRST_PARTY))], cwd=ROOT, env=env,
                   capture_output=True, check=False, text=True, timeout=900)
    results = json.loads(dst.read_text(encoding="utf-8"))
    status = {}
    for r, res in zip(items, results):
        status[json.dumps([r["kind"], r.get("module"), r.get("name"), r["file"] if r["kind"] != "import" else ""])] = res
    out = []
    for r in refs:
        res = status[json.dumps([r["kind"], r.get("module"), r.get("name"), r["file"] if r["kind"] != "import" else ""])]
        out.append({**r, "result": res})
    return out


# --------------------------------------------------------------------------- api / cli

def snap_api():
    code = (
        "import json, cognicore\n"
        "api = {n: type(getattr(cognicore, n)).__name__ + ':' + str(getattr(getattr(cognicore, n), '__qualname__', ''))"
        " for n in cognicore.__all__}\n"
        "print('@@' + json.dumps({'all': api, 'dir': sorted(n for n in dir(cognicore) if not n.startswith('_'))}))\n"
    )
    rc, out, err = _run(code, env={"COGNICORE_USE_SEMANTIC": "0"})
    return json.loads(out.split("@@", 1)[1]) if rc == 0 else {"error": err[-500:]}


def snap_cli():
    import tomllib
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    result = {}
    for name, target in scripts.items():
        mod, func = target.split(":")
        rc, _, err = _run(f"import importlib; f = getattr(importlib.import_module({mod!r}), {func!r}); assert callable(f)")
        result[f"entry:{name}"] = "ok" if rc == 0 else (err.strip().splitlines() or ["?"])[-1]
    rc, out, err = _run("import sys; sys.argv=['cognicore','--help']; from cognicore.cli import main; main()")
    result["cognicore --help"] = out
    return result


# --------------------------------------------------------------------------- apps

def _deploy_targets():
    targets = set(EXTRA_APPS)
    for f in DEPLOY_FILES:
        p = ROOT / f
        if p.exists():
            targets.update(m.group(1) for m in re.finditer(r"\b([a-zA-Z_][\w.]*:app)\b", p.read_text(encoding="utf-8")))
    return sorted(targets)


def _boot(target):
    factory = target.endswith("()")
    mod, attr = target.rstrip("()").split(":")
    code = (
        "import importlib, json\n"
        "from starlette.testclient import TestClient\n"
        f"obj = getattr(importlib.import_module({mod!r}), {attr!r})\n"
        f"app = obj() if {factory} else obj\n"
        "r = TestClient(app).get('/health')\n"
        "body = r.json() if r.headers.get('content-type','').startswith('application/json') else r.text[:200]\n"
        "print('@@' + json.dumps({'status': r.status_code, 'body': body}))\n"
    )
    with tempfile.TemporaryDirectory() as d:
        env = dict(APP_ENV, COGNICORE_DATA_DIR=d, COGNICORE_EXTENSION_DIR=d)
        rc, out, err = _run(code, timeout=120, env=env)
    if rc == 0 and "@@" in out:
        return target, json.loads(out.split("@@", 1)[1].strip().splitlines()[0])
    return target, {"error": (err.strip().splitlines() or ["?"])[-1][:300]}


def snap_apps(extra=()):
    targets = sorted(set(_deploy_targets()) | set(extra))
    with ThreadPoolExecutor(max_workers=4) as ex:
        return dict(ex.map(_boot, targets))


# --------------------------------------------------------------------------- aliases

def _compat_maps():
    rc, out, _ = _run(
        "import json\n"
        "try:\n"
        "    from cognicore import _compat\n"
        "    print('@@' + json.dumps({'modules': _compat.MOVED_MODULES, 'paths': getattr(_compat, 'MOVED_PATHS', {})}))\n"
        "except ImportError:\n"
        "    print('@@' + json.dumps({'modules': {}, 'paths': {}}))\n"
    )
    return json.loads(out.split("@@", 1)[1]) if rc == 0 else {"modules": {}, "paths": {}}


def snap_aliases(maps):
    def check(item):
        old, new = item
        rc, out, err = _run(
            "import importlib\n"
            f"o = importlib.import_module({old!r}); n = importlib.import_module({new!r})\n"
            "print('@@same' if o is n else '@@different')\n",
            env={"COGNICORE_USE_SEMANTIC": "0", **APP_ENV},
        )
        if rc == 0 and "@@same" in out:
            return old, "ok"
        return old, out.strip() or (err.strip().splitlines() or ["?"])[-1][:300]

    with ThreadPoolExecutor(max_workers=max(4, (os.cpu_count() or 4))) as ex:
        return dict(ex.map(check, sorted(maps["modules"].items())))


# --------------------------------------------------------------------------- snapshot / compare

def _untracked():
    out = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, check=False, text=True).stdout
    return set(out.splitlines())


def snapshot(path, skip_tests=False):
    existing = _untracked()
    try:
        _snapshot(path, skip_tests)
    finally:
        # Importing some modules writes files into the repo (e.g.
        # cognicore.nexus.export_trajectories); remove what this run created.
        for f in sorted(_untracked() - existing):
            (ROOT / f).unlink(missing_ok=True)
            print(f"removed side-effect file: {f}")


def _snapshot(path, skip_tests=False):
    maps = _compat_maps()
    with tempfile.TemporaryDirectory() as tmp:
        data = {
            "maps": maps,
            "tests": {} if skip_tests else snap_tests(tmp),
            "modules": snap_modules(),
            "refs": snap_refs(tmp),
            "api": snap_api(),
            "cli": snap_cli(),
            "apps": snap_apps(extra=_old_app_targets(maps)),
            "aliases": snap_aliases(maps),
        }
    Path(path).write_text(json.dumps(data, indent=1), encoding="utf-8")
    t = data["tests"]
    print(f"snapshot -> {path}: {sum(v == 'passed' for v in t.values())} passed, "
          f"{sum(v == 'failed' for v in t.values())} failed, {sum(v == 'skipped' for v in t.values())} skipped; "
          f"{sum(m['ok'] for m in data['modules'].values())}/{len(data['modules'])} modules import; "
          f"{sum(r['result'] is True for r in data['refs'])}/{len(data['refs'])} refs resolve "
          f"(+{sum(r['result'] == 'static:ok' for r in data['refs'])} verified statically); "
          f"{len(data['apps'])} apps; {len(data['aliases'])} aliases")


def _old_app_targets(maps):
    """Old module paths of moved apps, so both old and new targets get booted."""
    rev = {new: old for old, new in maps["modules"].items()}
    out = []
    for t in _deploy_targets():
        mod, attr = t.rstrip("()").split(":")
        if mod in rev:
            out.append(f"{rev[mod]}:{attr}")
    return out


def _map_module(name, mods):
    best = max((o for o in mods if name == o or name.startswith(o + ".")), key=len, default=None)
    return mods[best] + name[len(best):] if best else name


def _map_path(path, paths):
    p = path.replace("\\", "/")
    best = max((o for o in paths if p == o or p.startswith(o.rstrip("/") + "/")), key=len, default=None)
    return paths[best] + p[len(best):] if best else p


def compare(before_path, after_path):
    before = json.loads(Path(before_path).read_text(encoding="utf-8"))
    after = json.loads(Path(after_path).read_text(encoding="utf-8"))
    paths = dict(after["maps"]["paths"])
    mods = dict(after["maps"]["modules"])
    # Moved folders are also renamed import roots (cognicore_benchmarks -> benchmarks).
    for old, new in paths.items():
        if not old.endswith((".md", ".py")):
            mods.setdefault(old.replace("/", "."), new.replace("/", "."))
    # Moved modules are also moved files.
    for old, new in after["maps"]["modules"].items():
        o, n = old.replace(".", "/"), new.replace(".", "/")
        paths.setdefault(o + ".py", n + ".py")
        paths.setdefault(o, n)
    problems = []

    # tests
    for nodeid, outcome in before["tests"].items():
        now = after["tests"].get(nodeid)
        if outcome == "passed" and now != "passed":
            problems.append(f"TEST  {nodeid}: passed -> {now}")
    if before["tests"] and len(after["tests"]) < len(before["tests"]):
        problems.append(f"TEST  count dropped {len(before['tests'])} -> {len(after['tests'])}")

    # modules
    for name, info in before["modules"].items():
        if not info["ok"]:
            continue
        new = _map_module(name, mods)
        now = after["modules"].get(new)
        if now is None:
            problems.append(f"MOD   {name} -> {new}: no longer exists")
        elif not now["ok"]:
            problems.append(f"MOD   {name} -> {new}: import fails: {now['error']}")
        else:
            missing = set(info["names"]) - set(now["names"])
            if missing:
                problems.append(f"MOD   {new}: lost public names {sorted(missing)}")

    # refs: every ref that resolved before must resolve after (mapped to its new file and target)
    def key(r):
        return (_map_path(r["file"], paths), r["kind"], _map_module(r.get("module") or "", mods), r.get("name"))

    after_refs = {}
    for r in after["refs"]:
        after_refs.setdefault(key(r), r["result"])
    def good(res):
        return res is True or res == "static:ok"

    before_keys = {key(r) for r in before["refs"]}
    notes = []
    for r in before["refs"]:
        if not good(r["result"]):
            continue
        k = key(r)
        if k not in after_refs:
            notes.append(f"REF   {k[0]}: import of {k[2]} {k[3] or ''} no longer present (rewritten or removed)")
        elif not good(after_refs[k]):
            problems.append(f"REF   {k[0]}: {k[2]} {k[3] or ''} -> {after_refs[k]}")
    # New import statements (e.g. written during the change) must resolve too.
    for r in after["refs"]:
        if not good(r["result"]) and key(r) not in before_keys:
            problems.append(f"REF   {r['file']}: new import {r.get('module')} {r.get('name') or ''} -> {r['result']}")

    # api
    if before["api"] != after["api"]:
        b, a = before["api"], after["api"]
        if "error" in a:
            problems.append(f"API   cognicore import fails: {a['error']}")
        else:
            for n, v in b["all"].items():
                if a["all"].get(n) != v:
                    problems.append(f"API   cognicore.{n}: {v} -> {a['all'].get(n)}")
            lost = set(b["dir"]) - set(a["dir"])
            if lost:
                problems.append(f"API   cognicore lost attributes {sorted(lost)}")

    # cli
    for k, v in before["cli"].items():
        if after["cli"].get(k) != v:
            problems.append(f"CLI   {k} changed")

    # apps: each app must answer /health the same way, at its old and its new path
    for target, res in before["apps"].items():
        mod, attr = target.rstrip("()").split(":")
        for t in {target, f"{_map_module(mod, mods)}:{attr}" + ("()" if target.endswith("()") else "")}:
            if after["apps"].get(t) != res:
                problems.append(f"APP   {t}: {res} -> {after['apps'].get(t)}")

    # aliases
    for old, res in after["aliases"].items():
        if res != "ok":
            problems.append(f"ALIAS {old}: {res}")

    for n in notes:
        print("  note: " + n)
    if problems:
        print(f"FAIL: {len(problems)} regression(s)")
        for p in problems:
            print("  " + p)
        return 1
    print("OK: no regressions "
          f"({sum(v == 'passed' for v in after['tests'].values())} tests passing, "
          f"{len(after['modules'])} modules, {len(after['refs'])} refs, "
          f"{len(after['apps'])} app targets, {len(after['aliases'])} aliases)")
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "snapshot":
        snapshot(sys.argv[2], skip_tests="--skip-tests" in sys.argv)
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "compare":
        return compare(sys.argv[2], sys.argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
