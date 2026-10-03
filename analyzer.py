import ast

from radon.complexity import cc_visit
from radon.metrics import mi_visit


def analyze_code(code):

    tree = ast.parse(code)

    lines = len(code.splitlines())

    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )
        )
    ]

    classes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]

    complexity = cc_visit(code)

    if complexity:
        average_complexity = (
            sum(
                item.complexity
                for item in complexity
            )
            / len(complexity)
        )
    else:
        average_complexity = 0

    maintainability = mi_visit(
        code,
        multi=True
    )
"""CodeLens analyzer: static analysis of Python source.

Keeps the original contract (lines, functions, classes, average_complexity,
maintainability, complexity[radon blocks]) and adds much richer data.
"""

import ast
from dataclasses import dataclass, asdict

from radon.complexity import cc_visit, cc_rank
from radon.metrics import mi_visit, h_visit
from radon.raw import analyze as raw_analyze


@dataclass
class Issue:
    severity: str      # "error" | "warning" | "info"
    category: str
    message: str
    line: int
    function: str = ""

    def to_dict(self):
        return asdict(self)


NESTING_NODES = (
    ast.If, ast.For, ast.While, ast.Try, ast.With,
    ast.AsyncFor, ast.AsyncWith,
)


def _max_depth(node, depth=0):
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, NESTING_NODES):
            deepest = max(deepest, _max_depth(child, depth + 1))
        elif not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            deepest = max(deepest, _max_depth(child, depth))
    return deepest


def _unused_imports(tree):
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    imported[a.asname or a.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {
        n.value.id for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
    }
    return [(name, line) for name, line in imported.items() if name not in used]


def analyze_code(code: str, thresholds: dict | None = None) -> dict:
    t = {"complexity": 10, "length": 50, "args": 5, "nesting": 3, "line_length": 100}
    t.update(thresholds or {})

    tree = ast.parse(code)  # raises SyntaxError for the UI to catch

    # ---- radon metrics -------------------------------------------------
    blocks = cc_visit(code)
    complexities = [b.complexity for b in blocks]
    avg_cc = sum(complexities) / len(complexities) if complexities else 0.0
    maintainability = mi_visit(code, multi=True)

    raw = raw_analyze(code)

    try:
        h = h_visit(code).total
        halstead = {
            "volume": h.volume, "difficulty": h.difficulty,
            "effort": h.effort, "bugs": h.bugs, "time": h.time,
        }
    except Exception:
        halstead = {"volume": 0, "difficulty": 0, "effort": 0, "bugs": 0, "time": 0}

    cc_by_line = {(b.name, b.lineno): b for b in blocks}

    # ---- per-function details -----------------------------------------
    functions, issues = [], []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = node.args
        n_args = len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)
        n_args += bool(a.vararg) + bool(a.kwarg)
        if n_args and a.args and a.args[0].arg in ("self", "cls"):
            n_args -= 1
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        depth = _max_depth(node)
        has_doc = ast.get_docstring(node) is not None
        block = cc_by_line.get((node.name, node.lineno))
        cc = block.complexity if block else 1

        functions.append({
            "name": node.name, "line": node.lineno, "complexity": cc,
            "rank": cc_rank(cc), "length": length, "args": n_args,
            "nesting": depth, "docstring": has_doc,
        })

        if cc > 2 * t["complexity"]:
            issues.append(Issue("error", "Complexity",
                f"Very high complexity ({cc}). Split into smaller functions.", node.lineno, node.name))
        elif cc > t["complexity"]:
            issues.append(Issue("warning", "Complexity",
                f"High complexity ({cc}, limit {t['complexity']}).", node.lineno, node.name))
        if length > t["length"]:
            issues.append(Issue("warning", "Length",
                f"Function is {length} lines long (limit {t['length']}).", node.lineno, node.name))
        if n_args > t["args"]:
            issues.append(Issue("warning", "Parameters",
                f"{n_args} parameters (limit {t['args']}). Group them into an object.", node.lineno, node.name))
        if depth > t["nesting"]:
            issues.append(Issue("warning", "Nesting",
                f"Nesting depth {depth} (limit {t['nesting']}). Use early returns.", node.lineno, node.name))
        if not has_doc and not node.name.startswith("_"):
            issues.append(Issue("info", "Docs", "Missing docstring.", node.lineno, node.name))
        for d in a.defaults + [x for x in a.kw_defaults if x]:
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                issues.append(Issue("error", "Bug risk",
                    "Mutable default argument is shared between calls.", d.lineno, node.name))

    class_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    for c in class_nodes:
        if ast.get_docstring(c) is None:
            issues.append(Issue("info", "Docs", "Class is missing a docstring.", c.lineno, c.name))

    # ---- file-wide checks ----------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(Issue("error", "Bug risk",
                "Bare `except:` hides real errors. Catch specific exceptions.", node.lineno))
        elif isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            issues.append(Issue("warning", "Style", "Wildcard import pollutes the namespace.", node.lineno))
        elif isinstance(node, ast.Global):
            issues.append(Issue("warning", "Style", "`global` makes code harder to reason about.", node.lineno))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            issues.append(Issue("error", "Security",
                f"`{node.func.id}()` can execute arbitrary code.", node.lineno))

    for name, line in _unused_imports(tree):
        issues.append(Issue("info", "Style", f"Import `{name}` appears unused.", line))

    lines = code.splitlines()
    for i, text in enumerate(lines, 1):
        if len(text) > t["line_length"]:
            issues.append(Issue("info", "Style",
                f"Line is {len(text)} characters (limit {t['line_length']}).", i))
        if "TODO" in text or "FIXME" in text:
            issues.append(Issue("info", "Todo", text.strip()[:80], i))

    issues.sort(key=lambda x: ({"error": 0, "warning": 1, "info": 2}[x.severity], x.line))

    documentable = functions and len(functions) or 0
    documented = sum(f["docstring"] for f in functions)
    doc_cov = (documented / documentable * 100) if documentable else 100.0

    imports = sorted({
        (a.name if isinstance(n, ast.Import) else (n.module or ""))
        .split(".")[0]
        for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in n.names
    } - {""})

    return {
        # original contract
        "lines": len(lines),
        "functions": len(functions),
        "classes": len(class_nodes),
        "average_complexity": avg_cc,
        "maintainability": maintainability,
        "complexity": blocks,
        # new data
        "raw": {
            "loc": raw.loc, "sloc": raw.sloc, "comments": raw.comments,
            "multi": raw.multi, "blank": raw.blank,
        },
        "halstead": halstead,
        "function_details": sorted(functions, key=lambda f: -f["complexity"]),
        "issues": [i.to_dict() for i in issues],
        "docstring_coverage": doc_cov,
        "imports": imports,
        "max_complexity": max(complexities, default=0),
    }
    return {
        "lines": lines,
        "functions": len(functions),
        "classes": len(classes),
        "complexity": complexity,
        "average_complexity": average_complexity,
        "maintainability": maintainability
    }