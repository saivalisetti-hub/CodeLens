import html
import json
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analyzer import analyze_code
from scoring import calculate_score, score_breakdown, grade

st.set_page_config(page_title="CodeLens", page_icon="🔍", layout="wide")

# --------------------------------------------------
# STYLE
# --------------------------------------------------
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1300px;}
.hero {padding: 1.4rem 1.6rem; border-radius: 16px; margin-bottom: 1rem;
  background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%); color: white;}
.hero h1 {margin: 0; font-size: 2rem;}
.hero p {margin: .2rem 0 0; opacity: .9;}
div[data-testid="stMetric"] {background: rgba(128,128,128,.08); padding: 14px 16px;
  border-radius: 12px; border: 1px solid rgba(128,128,128,.18);}
.code-view {font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px;
  border: 1px solid rgba(128,128,128,.25); border-radius: 10px; overflow-x: auto;
  max-height: 520px; overflow-y: auto;}
.code-view .ln {display: flex; padding: 0 10px; white-space: pre;}
.code-view .no {color: #888; width: 42px; flex: none; user-select: none;}
.code-view .error {background: rgba(239,68,68,.22);}
.code-view .warning {background: rgba(245,158,11,.20);}
.code-view .info {background: rgba(59,130,246,.15);}
.pill {display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;}
.pill.error {background:#ef4444; color:white;} .pill.warning {background:#f59e0b; color:black;}
.pill.info {background:#3b82f6; color:white;}
</style>
""", unsafe_allow_html=True)

SAMPLE = '''import os, sys

def process(data, mode, flag, verbose, retries, timeout, cache=[]):
    result = []
    for item in data:
        if item:
            if mode == "a":
                for sub in item:
                    if sub > 0:
                        if flag:
                            result.append(sub)
                        elif verbose:
                            print(sub)
            elif mode == "b":
                try:
                    result.append(eval(item))
                except:
                    pass
    return result


class Helper:
    def total(self, numbers):
        """Sum numbers."""
        return sum(numbers)
'''

SEV_ICON = {"error": "🔴", "warning": "🟡", "info": "🔵"}

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
st.session_state.setdefault("code", "")
st.session_state.setdefault("history", [])

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    thresholds = {
        "complexity": st.slider("Max complexity / function", 5, 30, 10),
        "length": st.slider("Max function length (lines)", 10, 200, 50),
        "args": st.slider("Max parameters", 2, 12, 5),
        "nesting": st.slider("Max nesting depth", 1, 8, 3),
        "line_length": st.slider("Max line length", 80, 160, 100),
    }
    st.divider()
    st.subheader("🕘 History")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-8:]):
            st.write(f"`{h['time']}` · **{h['score']}** ({h['grade']}) · {h['lines']} lines")
        if st.button("Clear history", width="stretch"):
            st.session_state.history = []
            st.rerun()
    else:
        st.caption("Your analyses will appear here.")

# --------------------------------------------------
# HEADER + INPUT
# --------------------------------------------------
st.markdown("""
<div class="hero"><h1>🔍 CodeLens</h1>
<p>Python code quality, complexity &amp; maintainability analyzer</p></div>
""", unsafe_allow_html=True)

in_paste, in_upload = st.tabs(["✍️ Paste code", "📁 Upload .py file"])

with in_paste:
    c1, c2 = st.columns([5, 1])
    with c2:
        if st.button("Load sample", width="stretch"):
            st.session_state.code = SAMPLE
        if st.button("Clear", width="stretch"):
            st.session_state.code = ""
    with c1:
        st.text_area("Python code", key="code", height=300,
                     placeholder="Paste your Python code here...",
                     label_visibility="collapsed")

with in_upload:
    up = st.file_uploader("Upload a Python file", type=["py"])
    if up is not None:
        st.session_state.upload = up.getvalue().decode("utf-8", errors="replace")
        st.success(f"Loaded **{up.name}** ({len(st.session_state.upload.splitlines())} lines)")
    else:
        st.session_state.pop("upload", None)

source = st.session_state.get("upload") or st.session_state.code
run = st.button("🔍 Analyze Code", type="primary", width="stretch")

# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------
if run:
    if not source.strip():
        st.warning("Please paste or upload some Python code first.")
        st.stop()
    try:
        result = analyze_code(source, thresholds)
    except SyntaxError as e:
        st.error(f"❌ Python syntax error on line {e.lineno}: {e.msg}")
        st.stop()
    except Exception as e:
        st.error(f"❌ An unexpected error occurred: {e}")
        st.stop()

    score = calculate_score(result["maintainability"], result["average_complexity"],
                            result["lines"], result["issues"], result["docstring_coverage"])
    prev = st.session_state.history[-1]["score"] if st.session_state.history else None
    st.session_state.history.append({
        "time": datetime.now().strftime("%H:%M"), "score": score,
        "grade": grade(score), "lines": result["lines"],
    })
    st.session_state.last = {"result": result, "score": score, "prev": prev, "source": source}

if "last" not in st.session_state:
    st.info("👆 Paste or upload code, then click **Analyze Code**. Try **Load sample** for a demo.")
    st.stop()

result = st.session_state.last["result"]
score = st.session_state.last["score"]
prev = st.session_state.last["prev"]
source = st.session_state.last["source"]
issues = result["issues"]
funcs = result["function_details"]
breakdown = score_breakdown(result["maintainability"], result["average_complexity"],
                            result["lines"], issues, result["docstring_coverage"])

st.divider()

# --------------------------------------------------
# SCORE HEADER
# --------------------------------------------------
g_col, r_col = st.columns([1, 1])
color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"

with g_col:
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta", value=score,
        delta={"reference": prev} if prev is not None else None,
        number={"suffix": f"  ({grade(score)})"},
        title={"text": "Code Health Score"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": color},
               "steps": [{"range": [0, 60], "color": "rgba(239,68,68,.15)"},
                         {"range": [60, 80], "color": "rgba(245,158,11,.15)"},
                         {"range": [80, 100], "color": "rgba(34,197,94,.15)"}]}))
    fig.update_layout(height=300, margin=dict(l=30, r=30, t=60, b=10))
    st.plotly_chart(fig, width="stretch")

with r_col:
    cats = list(breakdown)
    vals = list(breakdown.values())
    radar = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=cats + cats[:1],
                                      fill="toself", line_color=color))
    radar.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), showlegend=False,
                        height=300, margin=dict(l=50, r=50, t=40, b=20),
                        title="Quality Dimensions")
    st.plotly_chart(radar, width="stretch")

m = st.columns(6)
m[0].metric("Lines", result["lines"])
m[1].metric("Functions", result["functions"])
m[2].metric("Classes", result["classes"])
m[3].metric("Avg Complexity", f"{result['average_complexity']:.1f}")
m[4].metric("Maintainability", f"{result['maintainability']:.0f}")
m[5].metric("Docstrings", f"{result['docstring_coverage']:.0f}%")

# --------------------------------------------------
# TABS
# --------------------------------------------------
n_err = sum(i["severity"] == "error" for i in issues)
t_over, t_cx, t_fn, t_iss, t_code, t_exp = st.tabs([
    "📊 Overview", "🧠 Complexity", "🧩 Functions",
    f"🚨 Issues ({len(issues)})", "📝 Annotated Code", "📤 Export"])

# ---- Overview
with t_over:
    a, b = st.columns(2)
    raw = result["raw"]
    with a:
        pie = go.Figure(go.Pie(
            labels=["Code", "Comments", "Docstrings", "Blank"],
            values=[raw["sloc"], raw["comments"], raw["multi"], raw["blank"]], hole=.55))
        pie.update_layout(title="Line Composition", height=320, margin=dict(t=50, b=10))
        st.plotly_chart(pie, width="stretch")
    with b:
        sev = {s: sum(i["severity"] == s for i in issues) for s in ("error", "warning", "info")}
        bar = go.Figure(go.Bar(x=list(sev), y=list(sev.values()),
                               marker_color=["#ef4444", "#f59e0b", "#3b82f6"],
                               text=list(sev.values()), textposition="auto"))
        bar.update_layout(title="Issues by Severity", height=320, margin=dict(t=50, b=10))
        st.plotly_chart(bar, width="stretch")

    h = result["halstead"]
    st.subheader("Halstead metrics")
    hc = st.columns(4)
    hc[0].metric("Volume", f"{h['volume']:.0f}")
    hc[1].metric("Difficulty", f"{h['difficulty']:.1f}")
    hc[2].metric("Est. bugs", f"{h['bugs']:.2f}")
    hc[3].metric("Effort", f"{h['effort']:.0f}")

    if result["imports"]:
        st.subheader("Dependencies")
        st.write(" ".join(f"`{i}`" for i in result["imports"]))

    st.subheader("💡 Recommendations")
    recs = []
    if result["average_complexity"] > 10 or result["max_complexity"] > thresholds["complexity"]:
        recs.append("Break complex functions into smaller, single-purpose ones.")
    if result["functions"] == 0:
        recs.append("Organize code into reusable functions.")
    if result["lines"] > 300:
        recs.append("This file is large. Consider splitting it into modules.")
    if result["docstring_coverage"] < 60 and result["functions"]:
        recs.append("Add docstrings to your functions (coverage is low).")
    if n_err:
        recs.append(f"Fix the {n_err} error-level issue(s) first. They are likely bugs or security risks.")
    for r in recs or ["Your code structure looks good. No major issues detected."]:
        st.info(f"💡 {r}")

# ---- Complexity
with t_cx:
    if funcs:
        names = [f["name"] for f in funcs]
        cx = [f["complexity"] for f in funcs]
        colors = ["#22c55e" if c <= 5 else "#f59e0b" if c <= thresholds["complexity"] else "#ef4444" for c in cx]
        fig = go.Figure(go.Bar(x=names, y=cx, marker_color=colors, text=cx, textposition="auto"))
        fig.add_hline(y=thresholds["complexity"], line_dash="dash", line_color="#ef4444",
                      annotation_text="limit")
        fig.update_layout(xaxis_title="Function", yaxis_title="Cyclomatic Complexity",
                          height=420, margin=dict(t=30))
        st.plotly_chart(fig, width="stretch")

        sc = go.Figure(go.Scatter(
            x=[f["length"] for f in funcs], y=cx, mode="markers+text", text=names,
            textposition="top center",
            marker=dict(size=[10 + f["args"] * 5 for f in funcs], color=colors, opacity=.8)))
        sc.update_layout(title="Length vs Complexity (bubble size = parameters)",
                         xaxis_title="Lines", yaxis_title="Complexity", height=400)
        st.plotly_chart(sc, width="stretch")
    else:
        st.info("No functions were detected.")

# ---- Functions table
with t_fn:
    if funcs:
        df = pd.DataFrame(funcs).rename(columns={
            "name": "Function", "line": "Line", "complexity": "Complexity", "rank": "Rank",
            "length": "Length", "args": "Params", "nesting": "Nesting", "docstring": "Docstring"})
        q = st.text_input("🔎 Filter by name")
        if q:
            df = df[df["Function"].str.contains(q, case=False)]
        st.dataframe(
            df, width="stretch", hide_index=True,
            column_config={
                "Complexity": st.column_config.ProgressColumn(
                    "Complexity", min_value=0, max_value=max(20, int(df["Complexity"].max() if len(df) else 20))),
                "Docstring": st.column_config.CheckboxColumn("Docstring"),
            })
    else:
        st.info("No functions were detected.")

# ---- Issues
with t_iss:
    if not issues:
        st.success("🎉 No issues found.")
    else:
        sel = st.multiselect("Severity", ["error", "warning", "info"],
                             default=["error", "warning", "info"])
        cats = sorted({i["category"] for i in issues})
        csel = st.multiselect("Category", cats, default=cats)
        shown = [i for i in issues if i["severity"] in sel and i["category"] in csel]
        for i in shown:
            where = f" in `{i['function']}`" if i["function"] else ""
            st.markdown(f"{SEV_ICON[i['severity']]} **Line {i['line']}**{where} · "
                        f"_{i['category']}_ — {i['message']}")

# ---- Annotated code
with t_code:
    by_line = {}
    rank = {"error": 0, "warning": 1, "info": 2}
    for i in issues:
        cur = by_line.get(i["line"])
        if cur is None or rank[i["severity"]] < rank[cur["severity"]]:
            by_line[i["line"]] = i
    rows = []
    for n, text in enumerate(source.splitlines(), 1):
        i = by_line.get(n)
        cls = i["severity"] if i else ""
        tip = f' title="{html.escape(i["message"])}"' if i else ""
        rows.append(f'<div class="ln {cls}"{tip}><span class="no">{n}</span>'
                    f'<span>{html.escape(text) or " "}</span></div>')
    st.caption("Hover over a highlighted line to see the issue.")
    st.markdown(f'<div class="code-view">{"".join(rows)}</div>', unsafe_allow_html=True)

# ---- Export
with t_exp:
    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "score": score, "grade": grade(score), "breakdown": breakdown,
        "summary": {k: result[k] for k in ("lines", "functions", "classes",
                                           "average_complexity", "maintainability",
                                           "docstring_coverage")},
        "functions": funcs, "issues": issues,
    }
    md = [f"# CodeLens Report\n\n**Score:** {score}/100 ({grade(score)})\n",
          "## Summary\n"] + [f"- {k}: {v:.1f}" if isinstance(v, float) else f"- {k}: {v}"
                              for k, v in report["summary"].items()]
    md += ["\n## Issues\n"] + [f"- [{i['severity']}] line {i['line']}: {i['message']}" for i in issues]
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ JSON report", json.dumps(report, indent=2, default=str),
                       "codelens_report.json", "application/json", width="stretch")
    c2.download_button("⬇️ Markdown report", "\n".join(md),
                       "codelens_report.md", "text/markdown", width="stretch")