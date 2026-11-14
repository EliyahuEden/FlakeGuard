"""FlakeGuard's graphite workspace, backed entirely by the analysis API."""

import json
from datetime import UTC, datetime, time, timedelta
from html import escape
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

from flakeguard.config import Settings

st.set_page_config(
    page_title="FlakeGuard · Reliability workspace",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
settings = Settings()
BASE = settings.flakeguard_api_url.rstrip("/")
HEADERS = {"X-API-Key": settings.flakeguard_api_key.get_secret_value()}
PALETTE = {
    "passed": "#E4E4E9",
    "failed": "#F0A1A7",
    "timedOut": "#DCC39C",
    "skipped": "#777780",
    "unknown": "#777780",
    "interrupted": "#BCB0D7",
}
st.markdown(
    "<style>"
    + (Path(__file__).parent / "assets/dashboard.css").read_text(encoding="utf-8")
    + "</style>",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=10, show_spinner=False)
def read(path: str, params: dict[str, Any]) -> Any:
    response = httpx.get(BASE + "/api" + path, params=params, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.json()


def api(path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return read(path, params or {})
    except httpx.HTTPError:
        st.error("Cannot retrieve API data. Check the API URL, API key, database, and migrations.")
        st.stop()


def write(path: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    try:
        response = httpx.post(
            BASE + "/api" + path, json=payload, headers=HEADERS, timeout=120, **kwargs
        )
        if response.is_error:
            st.error(response.json().get("detail", "Request failed"))
            return None
        read.clear()
        return response.json()
    except (httpx.HTTPError, ValueError):
        st.error("Request failed or timed out. Inspect import status before retrying.")
        return None


def percent(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "—"


def html(value: str) -> None:
    st.markdown(value, unsafe_allow_html=True)


def navigate(page: str) -> None:
    st.session_state.workspace_page = page


def refresh() -> None:
    read.clear()


def chart(fig: Any, height: int = 270) -> None:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#8D8D98", "size": 10},
        margin={"l": 0, "r": 8, "t": 10, "b": 8},
        legend_title_text="",
        height=height,
        hoverlabel={"bgcolor": "#28282D", "font_color": "#F0F0F4", "bordercolor": "#414148"},
    )
    fig.update_xaxes(showgrid=False, title=None, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.055)", zeroline=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "responsive": True})


options = api("/options")
with st.sidebar:
    html(
        '<div class="fg-brand"><svg viewBox="0 0 28 28" fill="none" aria-hidden="true"><path d="M14 2 25 8v12L14 26 3 20V8L14 2Z" stroke="#eeeef2" stroke-width="1.5"/><path d="m9 14 3.2 3.1L19 10" stroke="#eeeef2" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>FlakeGuard</div>'
    )
    html(
        '<div class="fg-workspace"><strong>Reliability workspace</strong><span class="dot"></span>Connected to analysis API</div>'
    )
    html('<div class="fg-overline">WORKSPACE</div>')
    page = st.radio(
        "Workspace",
        ["Overview", "Flaky Tests", "Failure Analysis", "Test Details", "CI Integration"],
        key="workspace_page",
        label_visibility="collapsed",
    )
    html('<div class="fg-overline">YOUR DATA</div>')
    html(
        f'<div class="fg-side-note">{len(options["repositories"])} imported repositories<br>Observed execution history<br>Explainable investigation signals</div>'
    )
    st.link_button(
        "API documentation", BASE + "/docs", icon=":material/open_in_new:", width="stretch"
    )
    html(
        '<div class="fg-profile"><div class="fg-avatar">FG</div><div>Engineering workspace<small>Evidence before assumptions</small></div></div>'
    )

with st.container(key="workspace_header"):
    header, refresh_col, import_col = st.columns([6, 1.15, 1.4], vertical_alignment="center")
    with header:
        html(f'<div class="fg-breadcrumb">Workspace / <span>{escape(page)}</span></div>')
    with refresh_col:
        st.button("Refresh", icon=":material/refresh:", on_click=refresh, width="stretch")
    with import_col:
        st.button(
            "Data sources" if settings.flakeguard_read_only else "Import report",
            icon=":material/add:",
            type="primary",
            on_click=navigate,
            args=("CI Integration",),
            key="header_import",
            width="stretch",
        )
st.title("Your test suite, in focus." if page == "Overview" else page)
subtitles = {
    "Overview": "A clearer view of reliability. Every number traces back to a test execution.",
    "Flaky Tests": "Find the tests that need a closer look. Follow the evidence behind every score.",
    "Failure Analysis": "Connect recurring diagnostics, inspect their evidence, and plan the next investigation.",
    "Test Details": "One test. Its complete execution story, from first attempt to final outcome.",
    "CI Integration": "Bring your execution history together. Local reports and authorized GitHub runs.",
}
html(f'<div class="fg-subtitle">{subtitles[page]}</div>')
params: dict[str, Any] = {}
with st.expander("Filter workspace", icon=":material/tune:"):
    columns = st.columns(4)
    for index, (key, label, values) in enumerate(
        [
            ("repository", "Repository", options["repositories"]),
            ("provenance", "Data provenance", options["provenances"]),
            ("branch", "Branch", options["branches"]),
            ("suite", "Suite", options["suites"]),
            ("browser", "Browser", options["browsers"]),
            ("environment", "Environment", options["environments"]),
        ]
    ):
        with columns[index % 4]:
            chosen = st.selectbox(label, ["All", *values], key=f"filter_{key}")
            if chosen != "All":
                params[key] = chosen
    with columns[2]:
        status = st.selectbox("Status", ["All", *PALETTE])
        if status != "All":
            params["status"] = status
    with columns[3]:
        dates = st.date_input("Date range (optional)", value=[], key="date_range")
        if isinstance(dates, (tuple, list)) and len(dates) == 2:
            params["start"] = datetime.combine(dates[0], time.min, UTC).isoformat()
            params["end"] = datetime.combine(dates[1], time.max, UTC).isoformat()
if "status" in params:
    st.warning("Status filtering selects outcomes and can bias reliability history.")
chips = [
    f'<span class="fg-chip">{escape(str(key).replace("_", " "))}: {escape(str(value))}</span>'
    for key, value in params.items()
]
if not chips:
    chips = [
        '<span class="fg-chip">All repositories</span>',
        '<span class="fg-chip">All branches</span>',
    ]
source = escape(str(params.get("provenance", "Includes synthetic & injected demo data")))
html(
    '<div class="fg-scope"><span class="fg-scope-label">SCOPE</span>'
    + "".join(chips)
    + f'<span class="fg-chip fg-chip-source">{source}</span></div>'
)

if page == "Overview":
    data = api("/dashboard", params)
    m = data["metrics"]
    with st.container(key="metric_strip"):
        columns = st.columns(4)
        values = [
            f"{m['total_executions']:,}",
            f"{m['failed']:,}",
            str(m["suspected_flaky_tests"]),
            f"{m['average_duration_ms'] / 1000:.2f}s"
            if m["average_duration_ms"] is not None
            else "—",
        ]
        for col, label, value in zip(
            columns,
            ["Test executions", "Final failures", "Suspected flaky tests", "Average duration"],
            values,
            strict=True,
        ):
            col.metric(label, value)
    st.write("")
    left, right = st.columns([1.95, 1], gap="medium")
    with left, st.container(key="panel_reliability", border=True):
        html(
            '<div class="fg-panel-heading">Reliability over time<span>Final observed outcomes</span></div>'
        )
        html(
            f'<div class="fg-hero-value">{percent(m["pass_rate"])}</div><span class="fg-chip">Final pass rate</span><span class="fg-chip">{m["passed"]:,} / {m["eligible_executions"]:,} eligible executions</span>'
        )
        if data["trends"]:
            window = st.segmented_control(
                "Trend window",
                ["7 days", "14 days", "30 days", "All"],
                default="All",
                label_visibility="collapsed",
            )
            frame = pd.DataFrame(data["trends"])
            if window and window != "All":
                cutoff = pd.to_datetime(frame["date"]).max() - timedelta(
                    days=int(window.split()[0]) - 1
                )
                frame = frame[pd.to_datetime(frame["date"]) >= cutoff]
            fig = px.line(frame, x="date", y="pass_rate", color_discrete_sequence=["#EDEDF2"])
            fig.update_traces(
                line_width=2,
                fill="tozeroy",
                fillcolor="rgba(235,235,245,.035)",
                hovertemplate="%{x}<br>Pass rate %{y:.1%}<extra></extra>",
            )
            fig.update_yaxes(tickformat=".0%", range=[0, 1.05], title=None, nticks=4)
            chart(fig, height=235)
        else:
            st.info("Import a report or run the demo to populate this workspace.")
        html(
            f'<div class="fg-mini-note">{m["excluded"]:,} skipped, interrupted, or unknown outcomes are excluded. The chart window ends at the latest observed execution.</div>'
        )
    with right, st.container(key="panel_first_attempt", border=True):
        html(
            '<div class="fg-panel-heading">First-attempt reliability<span>Observed data</span></div>'
        )
        progress = 100 * (m["first_attempt_pass_rate"] or 0)
        html(
            f'<div class="fg-ring" style="--progress:{progress:.3f}%"><div class="fg-ring-center"><strong>{percent(m["first_attempt_pass_rate"])}</strong><span>first-attempt pass rate</span></div></div>'
        )
        html(
            f'<div class="fg-pair"><span>Initial attempts known</span><strong>{m["first_attempt_observations"]:,}</strong></div><div class="fg-pair"><span>Retry recoveries</span><strong>{m["retry_recoveries"]:,}</strong></div><div class="fg-pair"><span>Recovery rate</span><strong>{percent(m["retry_recovery_rate"])}</strong></div>'
        )
        html(
            f'<div class="fg-mini-note">Recovery denominator: {m["initially_failed_with_retries"]} initially failed executions that were actually retried. Missing retry information stays unknown.</div>'
        )
    st.write("")
    left, right = st.columns([1.95, 1], gap="medium")
    with left, st.container(key="panel_recent", border=True):
        st.subheader("Recent test runs")
        recent = api("/runs", {**params, "limit": 8})
        if recent:
            table = pd.DataFrame(recent)
            table["commit_sha"] = table["commit_sha"].fillna("unknown").str.slice(0, 8)
            st.dataframe(
                table[["external_id", "branch", "commit_sha", "provenance", "executed_at"]],
                hide_index=True,
                width="stretch",
                height=310,
                column_config={
                    "external_id": "Run",
                    "branch": "Branch",
                    "commit_sha": "Commit",
                    "provenance": "Source",
                    "executed_at": st.column_config.DatetimeColumn(
                        "Executed", format="MMM D, HH:mm"
                    ),
                },
            )
        else:
            st.info("No imported runs in this scope.")
    with right, st.container(key="panel_signals", border=True):
        html(
            '<div class="fg-panel-heading">Investigation queue<span>In selected history</span></div>'
        )
        html(
            f'<div class="fg-signal"><span>Suspected flaky tests</span><strong>{m["suspected_flaky_tests"]}</strong></div><div class="fg-signal"><span>Newly failing observations</span><strong>{len(data["newly_failing"])}</strong></div><div class="fg-signal"><span>Final failure rate</span><strong>{percent(m["failure_rate"])}</strong></div>'
        )
        st.button(
            "Review test evidence",
            icon=":material/arrow_forward:",
            on_click=navigate,
            args=("Flaky Tests",),
            width="stretch",
        )
        html(
            '<div class="fg-mini-note">Signals prioritize investigation. Suspected flakiness never bypasses a quality gate. Newly failing observations are capped at the latest 100.</div>'
        )
    st.write("")
    with st.container(key="panel_suites", border=True):
        st.subheader("Suites needing attention")
        suites = sorted(data["suites"], key=lambda row: row["failure_rate"] or 0, reverse=True)
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Suite": s["name"],
                        "Executions": s["total_executions"],
                        "Failures": s["failed"],
                        "Pass rate": percent(s["pass_rate"]),
                    }
                    for s in suites
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with st.expander("Breakdowns and newly failing tests"):
        st.write("By browser")
        st.dataframe(data["browsers"], hide_index=True)
        st.write("By branch")
        st.dataframe(data["branches"], hide_index=True)
        st.write("Failures after the previous eligible observation passed")
        st.dataframe(data["newly_failing"], hide_index=True)

elif page == "Flaky Tests":
    rows = api("/reliability", params)
    left, right = st.columns([2, 1])
    search = left.text_input("Search test or suite", placeholder="checkout, API, cart…")
    classification = right.selectbox(
        "Evidence category",
        [
            "All",
            "suspected_flaky",
            "consistently_failing",
            "consistently_passing",
            "insufficient_history",
            "intermittent_failures",
        ],
    )
    filtered = [
        r
        for r in rows
        if search.lower() in (r["name"] + r["suite"]).lower()
        and (classification == "All" or r["classification"] == classification)
    ]
    st.caption(
        "One row per test, branch, environment/browser, and provenance. Reliability may be overstated where retry history is unknown."
    )
    if filtered:
        fields = [
            "name",
            "suite",
            "project",
            "browser",
            "branch",
            "provenance",
            "observations",
            "distinct_runs",
            "failure_frequency",
            "retry_recoveries",
            "known_retry_observations",
            "reliability_score",
            "suspicion_score",
            "classification",
            "priority",
            "last_execution",
        ]
        st.dataframe(
            pd.DataFrame(filtered)[fields],
            hide_index=True,
            width="stretch",
            height=460,
            column_config={
                "name": "Test",
                "suite": "Suite",
                "project": "Project",
                "browser": "Browser",
                "branch": "Branch",
                "provenance": "Source",
                "observations": "Observations",
                "reliability_score": st.column_config.ProgressColumn(
                    "Reliability", min_value=0, max_value=100, format="%.1f"
                ),
                "suspicion_score": st.column_config.ProgressColumn(
                    "Suspicion", min_value=0, max_value=100, format="%.1f"
                ),
                "failure_frequency": st.column_config.NumberColumn(
                    "Failure frequency", format="percent"
                ),
            },
        )
        st.download_button(
            "Export reliability data",
            pd.DataFrame(filtered).to_csv(index=False).encode(),
            file_name="flakeguard-reliability.csv",
            mime="text/csv",
            icon=":material/download:",
        )
        selected = st.selectbox(
            "Inspect scoring evidence",
            range(len(filtered)),
            format_func=lambda i: (
                f"{filtered[i]['name']} · {filtered[i]['project']} · {filtered[i]['browser'] or 'browser unknown'} · {filtered[i]['branch']}"
            ),
        )
        st.info(filtered[selected]["explanation"])
        st.write(
            "95% Wilson interval for observed final pass frequency:",
            filtered[selected]["pass_rate_interval_95"],
        )
        st.caption(
            "The interval estimates a proportion under independent observations; correlated CI runs can make it optimistic. It is not the probability that a test is flaky."
        )
    else:
        st.info("No tests match the current filters.")

elif page == "Failure Analysis":
    data = api("/failures", params)
    clusters = data["clusters"]
    st.warning(
        "A shared fingerprint means matching normalized diagnostics. It does not establish a shared root cause."
    )
    if clusters:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Pattern": c["fingerprint"][:12],
                        "Failed attempts": c["occurrences"],
                        "Affected tests": c["affected_tests"],
                        "Runs": c["runs"],
                        "First seen": c["first_seen"],
                        "Last seen": c["last_seen"],
                        "Category": c["classification"]["category"],
                        "Evidence": c["classification"]["evidence_strength"],
                    }
                    for c in clusters
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        selected = st.selectbox(
            "Failure pattern",
            range(len(clusters)),
            format_func=lambda i: (
                f"{clusters[i]['fingerprint'][:12]} · {clusters[i]['normalized_text'][:100]}"
            ),
        )
        cluster = clusters[selected]
        st.code(cluster["normalized_text"], language="text")
        c = cluster["classification"]
        left, right = st.columns(2)
        with left:
            st.subheader("Supporting evidence")
            st.write(f"**{c['category']}** · {c['evidence_strength']} evidence")
            for signal in c["signals"]:
                st.write("• " + signal)
            st.caption(c["explanation"])
        with right:
            st.subheader("Investigation steps")
            for step in c["investigation_steps"]:
                st.write("• " + step)
        for example in cluster["examples"]:
            with st.expander(f"{example['name']} · run {example['run_id']}"):
                st.code(
                    example["error_message"] or example["stack_trace"] or "No diagnostic text",
                    language="text",
                )
                if example["stack_trace"]:
                    st.code(example["stack_trace"], language="text")
        with st.expander("Similar wording (separate patterns)"):
            st.caption(data["similarity_note"])
            st.dataframe(data["similarity_suggestions"], hide_index=True)
    else:
        st.info("No failed attempts match these filters.")

elif page == "Test Details":
    scores = api("/reliability", params)
    unique = {s["test_id"]: s for s in scores}
    if unique:
        test_id = st.selectbox(
            "Test identity",
            list(unique),
            format_func=lambda key: (
                f"{unique[key]['name']} · {unique[key]['project']} · {unique[key]['repository']}"
            ),
        )
        detail = api(f"/tests/{test_id}/history", {**params, "limit": 2000})
        frame = pd.DataFrame(detail["history"])
        st.caption(
            f"Showing {len(frame)} / {detail['total']} observations. API pagination supports longer histories."
        )
        a, b = st.columns(2)
        with a:
            st.subheader("Execution duration")
            chart(
                px.line(
                    frame,
                    x="executed_at",
                    y="duration_ms",
                    color="status",
                    markers=True,
                    color_discrete_map=PALETTE,
                )
            )
        with b:
            st.subheader("Observed outcomes")
            chart(
                px.scatter(
                    frame, x="executed_at", y="status", color="status", color_discrete_map=PALETTE
                )
            )
        st.dataframe(
            frame[
                [
                    "run_id",
                    "branch",
                    "status",
                    "duration_ms",
                    "retries",
                    "retry_recovered",
                    "browser",
                    "environment",
                    "provenance",
                    "executed_at",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
        selected = st.selectbox(
            "Execution diagnostics",
            range(len(frame)),
            format_func=lambda i: (
                f"Run {detail['history'][i]['run_id']} · {detail['history'][i]['status']}"
            ),
            index=len(frame) - 1,
        )
        ex = detail["history"][selected]
        if ex["ci_url"] and ex["ci_url"].startswith("https://github.com/"):
            st.link_button("Open CI run", ex["ci_url"])
        for attempt in ex["attempts"]:
            st.write(
                f"**Attempt {attempt['ordinal'] + 1}** · {attempt['status']} · retry index {attempt['retry_index'] if attempt['retry_index'] is not None else 'unknown'}"
            )
            if attempt["fingerprint"]:
                st.caption("Related failure pattern: " + attempt["fingerprint"])
            if attempt["error_message"] or attempt["stack_trace"]:
                st.code(attempt["error_message"] or attempt["stack_trace"], language="text")
            if attempt["artifacts"]:
                st.dataframe(attempt["artifacts"], hide_index=True)
                st.caption(
                    "Artifact paths are source metadata; local files are not served by this API."
                )
    else:
        st.info("No test history available. Import reports through CI Integration.")

elif page == "CI Integration":
    if settings.flakeguard_read_only:
        st.info(
            "Read-only portfolio demo. Import and GitHub synchronization are available in the full local platform; this public instance only displays its labeled demonstration history."
        )
    left, right = st.columns(2)
    with left:
        st.subheader("Import a local report")
        st.caption(
            "Standard Playwright JSON or JUnit XML. Retry metadata is preserved only when supplied."
        )
        with st.form("upload_report"):
            file = st.file_uploader(
                "Test report", type=["json", "xml"], disabled=settings.flakeguard_read_only
            )
            repository = st.text_input("Repository", value="local/project")
            run_id = st.text_input("Unique run identifier", placeholder="local-2026-11-14-001")
            branch = st.text_input("Branch", value="main")
            commit = st.text_input("Commit SHA (optional)")
            provenance = st.selectbox("Report provenance", ["real", "injected", "synthetic"])
            submitted = st.form_submit_button(
                "Import report",
                type="primary",
                key="upload_submit",
                disabled=settings.flakeguard_read_only,
            )
        if submitted:
            if file is None or not run_id:
                st.error("Choose a report and supply a stable run identifier.")
            else:
                context = {
                    "repository": repository,
                    "run_id": run_id,
                    "branch": branch,
                    "commit_sha": commit or None,
                    "provenance": provenance,
                }
                # Multipart requests cannot also carry a JSON request body.
                try:
                    response = httpx.post(
                        BASE + "/api/imports",
                        headers=HEADERS,
                        data={"context": json.dumps(context)},
                        files={"file": (file.name, file.getvalue())},
                        timeout=60,
                    )
                    if response.is_success:
                        read.clear()
                        st.success(
                            f"Imported {response.json()['imported']} executions; {response.json()['duplicates']} duplicates."
                        )
                    else:
                        st.error(response.json().get("detail", "Import failed"))
                except httpx.HTTPError:
                    st.error("Import request failed. Check API connectivity and import status.")
    with right:
        st.subheader("GitHub Actions")
        st.caption(
            "The server must allowlist the repository in GITHUB_REPOSITORIES. Configure an Actions-read token in the server environment for private repositories."
        )
        with st.form("github_sync"):
            repo = st.text_input("GitHub repository", placeholder="owner/repository")
            pattern = st.text_input("Report artifact name pattern", value="*test-results*")
            count = st.number_input("Recent completed runs", min_value=1, max_value=100, value=20)
            configure = st.form_submit_button(
                "Configure repository", disabled=settings.flakeguard_read_only
            )
            synchronize = st.form_submit_button(
                "Synchronize now", type="primary", disabled=settings.flakeguard_read_only
            )
        if configure:
            result = write("/repositories", {"name": repo, "github_enabled": True})
            if result:
                st.success("Repository configured.")
        if synchronize:
            with st.spinner("Downloading and importing available reports…"):
                result = write(
                    "/github/sync",
                    {"repository": repo, "max_runs": count, "artifact_pattern": pattern},
                )
            if result:
                st.dataframe(result["runs"], hide_index=True)
        st.caption(
            "Choose one report format per test suite to avoid counting JSON and JUnit representations as separate test identities."
        )
    st.divider()
    st.subheader("Ingestion activity")
    activity = api("/imports")
    imports, errors, syncs = st.tabs(["Reports", "Errors", "GitHub runs"])
    imports.dataframe(activity["imports"], hide_index=True, width="stretch")
    errors.dataframe(activity["errors"], hide_index=True, width="stretch")
    syncs.dataframe(activity["syncs"], hide_index=True, width="stretch")
