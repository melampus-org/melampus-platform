"use strict";

const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const labels = {drift:"Intent drift", error:"Error", incomplete:"Incomplete", aligned:"Aligned", unverified:"Unverified", passed:"Passed", failed:"Failed", sampled_out:"Sampled out", budget:"Budget limited", disabled:"Disabled", not_executed:"Not executed"};
const originLabels = {application:"Application", platform:"Platform itself", demo:"Synthetic demo"};
const explanations = {
  passed:"The predicate returned true for the observed result.",
  failed:"The predicate returned false. The observed result did not satisfy this contract.",
  error:"The predicate raised an exception or returned a value other than bool. This is incomplete evidence.",
  sampled_out:"Sampling skipped this check. No verdict was evaluated.",
  budget:"The check execution budget was exhausted. No verdict was evaluated.",
  disabled:"The operator disabled checks on this function. No verdict was evaluated.",
  not_executed:"The function did not return successfully, or evidence is incomplete. No verdict was evaluated.",
};
const fmt = value => Number(value).toLocaleString();
const duration = value => value < 1 ? `${(value * 1000).toFixed(0)} µs` : value < 1000 ? `${value.toFixed(value < 10 ? 2 : 1)} ms` : `${(value / 1000).toFixed(2)} s`;
const clock = ns => new Date(ns / 1e6).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"});
const timeFull = ns => new Date(ns / 1e6).toLocaleString();
const ago = ns => {
  const seconds = Math.max(0, Math.floor((Date.now() - ns / 1e6) / 1000));
  return seconds < 60 ? `${seconds}s ago` : seconds < 3600 ? `${Math.floor(seconds / 60)}m ago` : seconds < 86400 ? `${Math.floor(seconds / 3600)}h ago` : `${Math.floor(seconds / 86400)}d ago`;
};
const shortFunction = name => (name.includes(":") ? name.split(":").slice(1).join(":") : name);
const badge = outcome => `<span class="badge ${escapeHTML(outcome)}"><span class="outcome-dot ${escapeHTML(outcome)}"></span>${escapeHTML(labels[outcome] || outcome)}</span>`;
const params = new URLSearchParams(location.search);
const state = {
  query: params.get("query") || "", service: params.get("service") || "", environment: params.get("environment") || "",
  origin: params.get("origin") || "", outcome: params.get("outcome") || "", minutes: Number(params.get("minutes")) || 60,
  sort: params.get("sort") || "failures", offset: 0, limit: 50,
  since_ns: Number(params.get("since_ns")) || null, until_ns: Number(params.get("until_ns")) || null,
  view: params.get("view") || "explorer", trace: null, span: null, tab: "checks", live: true,
};
if (![15, 60, 1440, 10080].includes(state.minutes)) state.minutes = 60;
if (!(state.outcome in labels) || !["", "drift", "error", "incomplete", "aligned", "unverified"].includes(state.outcome)) state.outcome = "";
if (!["", "application", "platform", "demo"].includes(state.origin)) state.origin = "";
if (!["failures", "recent", "duration"].includes(state.sort)) state.sort = "failures";
if (!["explorer", "functions", "mesh", "setup"].includes(state.view)) state.view = "explorer";
let data = null, statusData = null, requestController = null, traceController = null;
let toastTimer, searchTimer, busyDemo = false, returningFocus = null, returningTraceId = null;
const services = new Set(), environments = new Set();
const panelMedia = matchMedia("(max-width: 800px)");

function rememberFocus() {
  const active = document.activeElement;
  if (active.dataset.filter) return { element:active, kind:"filter", key:active.dataset.filter, value:active.value };
  if (active.dataset.trace) return { element:active, kind:"trace", value:active.dataset.trace };
  if (active.dataset.bin !== undefined) return { element:active, kind:"bin", value:active.dataset.bin };
  if (active.dataset.function !== undefined) return { element:active, kind:"function", value:active.dataset.functionName, service:active.dataset.functionService };
  return null;
}

function restoreFocus(saved) {
  if (!saved || saved.element.isConnected) return;
  let target;
  if (saved.kind === "filter") target = [...document.querySelectorAll("#facets input")].find(input => input.dataset.filter === saved.key && input.value === saved.value);
  if (saved.kind === "trace") target = [...document.querySelectorAll("#traceRows button[data-trace]")].find(button => button.dataset.trace === saved.value);
  if (saved.kind === "bin") target = [...document.querySelectorAll("#histogram button")].find(button => button.dataset.bin === saved.value);
  if (saved.kind === "function") target = [...document.querySelectorAll("#functionRows button")].find(button => button.dataset.functionName === saved.value && button.dataset.functionService === saved.service);
  (target || $("searchInput")).focus({preventScroll:true});
}

function configurePanelAccessibility() {
  const modal = !$("tracePanel").hidden && panelMedia.matches;
  $("main").inert = modal;
  document.querySelector(".sidebar").inert = modal;
  if (modal) {
    $("tracePanel").setAttribute("role", "dialog");
    $("tracePanel").setAttribute("aria-modal", "true");
    if (!$("tracePanel").contains(document.activeElement)) $("closeTrace").focus({preventScroll:true});
  } else {
    $("tracePanel").removeAttribute("role");
    $("tracePanel").removeAttribute("aria-modal");
  }
}
panelMedia.addEventListener("change", configurePanelAccessibility);

function writeURL() {
  const url = new URL(location.href);
  url.search = "";
  for (const key of ["query", "service", "environment", "origin", "outcome", "sort", "minutes", "since_ns", "until_ns"]) {
    if (state[key]) url.searchParams.set(key, state[key]);
  }
  if (state.view !== "explorer") url.searchParams.set("view", state.view);
  if (state.trace) url.searchParams.set("trace", state.trace.trace_id);
  history.replaceState(null, "", url);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); if (typeof body.detail === "string") message = body.detail; } catch {}
    throw new Error(message);
  }
  return response.json();
}

function showError(error) {
  $("errorText").textContent = `${error.message} Check that the local collector is running, then retry.`;
  $("errorBanner").hidden = false;
  $("footerDot").style.background = "var(--red)";
  $("footerStatus").textContent = "Collector unavailable";
}

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 2600);
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied to clipboard"); }
  catch { toast("Clipboard unavailable. Select and copy the text directly."); }
}

async function refresh() {
  if (requestController) requestController.abort();
  const controller = new AbortController();
  requestController = controller;
  const query = new URLSearchParams();
  for (const key of ["query", "service", "environment", "origin", "outcome", "minutes", "sort", "offset", "limit", "since_ns", "until_ns"]) {
    if (state[key] !== null && state[key] !== "") query.set(key, state[key]);
  }
  $("refreshButton").disabled = true;
  $("refreshButton").setAttribute("aria-label", "Refreshing traces");
  try {
    const [result, collector] = await Promise.all([api(`/api/traces?${query}`, {signal:controller.signal}), api("/api/status", {signal:controller.signal})]);
    if (requestController !== controller) return;
    data = result;
    statusData = collector;
    result.facets.services.forEach(s => services.add(s));
    result.facets.environments.forEach(e => environments.add(e));
    render();
    $("errorBanner").hidden = true;
    const dropped = collector.telemetry_dropped + collector.demo_telemetry_dropped;
    $("footerDot").style.background = dropped ? "var(--amber)" : "#57ad81";
    $("footerStatus").textContent = dropped ? `${fmt(dropped)} telemetry spans dropped · check storage capacity` : `${fmt(collector.stored_spans)} spans stored · ${collector.retention_days}-day retention · ${state.live ? "updated just now" : "live updates paused"}`;
  } catch (error) { if (error.name !== "AbortError") showError(error); }
  finally {
    if (requestController === controller) {
      $("refreshButton").disabled = false;
      $("refreshButton").setAttribute("aria-label", "Refresh traces");
    }
  }
}

function setFilter(key, value) {
  state[key] = value;
  state.offset = 0;
  $("searchInput").value = state.query;
  writeURL();
  refresh();
}

function clearFilters() {
  for (const key of ["query", "service", "environment", "origin", "outcome"]) state[key] = "";
  state.since_ns = null;
  state.until_ns = null;
  state.offset = 0;
  $("searchInput").value = "";
  $("environmentSelect").value = "";
  writeURL();
  refresh();
}

function facetOption(key, value, label, count, dot = "") {
  return `<label class="facet-option"><input type="checkbox" data-filter="${key}" value="${escapeHTML(value)}" ${state[key] === value ? "checked" : ""}>${dot ? `<span class="outcome-dot ${dot}"></span>` : ""}<span class="facet-name" title="${escapeHTML(label)}">${escapeHTML(label)}</span>${count !== undefined ? `<span class="facet-count">${fmt(count)}</span>` : ""}</label>`;
}

function render() {
  const savedFocus = rememberFocus();
  const summary = data.summary;
  $("summary").innerHTML = [
    ["Traces", fmt(summary.traces), "", ""],
    ["Failed checks", fmt(summary.failed_checks), "failed-value", summary.check_errors ? `${fmt(summary.check_errors)} errors` : ""],
    ["Evaluated pass rate", summary.pass_rate === null ? "—" : `${(summary.pass_rate * 100).toFixed(1)}%`, "", summary.evaluated_checks ? `${fmt(summary.evaluated_checks)} checks` : "No evidence"],
    ["Incomplete checks", fmt(summary.incomplete_checks), "", ""],
    ["p95 trace duration", summary.p95_ms === null ? "—" : duration(summary.p95_ms), "", ""],
  ].map(([label, value, style, detail]) => `<div><span>${label}</span><strong class="${style}">${value}</strong>${detail ? `<small>${detail}</small>` : ""}</div>`).join("");
  $("summary").title = "Pass rate includes only predicates that returned passed or failed. Suppressed, unexecuted, and errored checks are excluded.";
  renderChart();
  $("outcomeFacets").innerHTML = ["drift", "error", "incomplete", "aligned", "unverified"].map(outcome => facetOption("outcome", outcome, labels[outcome], data.facets.outcomes[outcome] || 0, outcome)).join("");
  $("serviceFacets").innerHTML = [...services].sort().map(service => facetOption("service", service, service)).join("") || '<span class="muted-note">No services observed</span>';
  $("environmentFacets").innerHTML = [...environments].sort().map(environment => facetOption("environment", environment, environment)).join("") || '<span class="muted-note">No environments observed</span>';
  $("originFacets").innerHTML = ["application", "platform", "demo"].map(origin => facetOption("origin", origin, originLabels[origin], data.facets.origins[origin] || 0)).join("");
  if (state.environment) environments.add(state.environment);
  $("environmentSelect").innerHTML = '<option value="">All environments</option>' + [...environments].sort().map(e => `<option value="${escapeHTML(e)}">${escapeHTML(e)}</option>`).join("");
  $("environmentSelect").value = state.environment;
  renderFilters();
  $("allCount").textContent = fmt(Object.values(data.facets.outcomes).reduce((a, b) => a + b, 0));
  $("driftCount").textContent = fmt(data.facets.outcomes.drift || 0);
  $("allTracesButton").classList.toggle("selected", !state.outcome);
  $("allTracesButton").setAttribute("aria-pressed", String(!state.outcome));
  $("failedTracesButton").classList.toggle("selected", state.outcome === "drift");
  $("failedTracesButton").setAttribute("aria-pressed", String(state.outcome === "drift"));
  $("resultCount").textContent = `${fmt(data.total)} ${data.total === 1 ? "trace" : "traces"}`;
  $("resultSubtitle").textContent = state.outcome ? labels[state.outcome] : "Matching this view";
  const maxDuration = Math.max(1, ...data.traces.map(t => t.duration_ms));
  $("traceRows").innerHTML = data.traces.map(trace => `<tr class="trace-row ${state.trace?.trace_id === trace.trace_id ? "selected" : ""}" data-trace="${trace.trace_id}">
    <td><button class="trace-name" data-trace="${trace.trace_id}" title="${escapeHTML(trace.name)}">${escapeHTML(shortFunction(trace.name))}</button><div class="row-meta"><code>${trace.trace_id.slice(0, 12)}</code><span>${trace.span_count} spans</span>${trace.origin !== "application" ? `<span class="badge source">${escapeHTML(originLabels[trace.origin])}</span>` : ""}</div></td>
    <td><span class="service-label">${escapeHTML(trace.service)}</span></td><td>${badge(trace.outcome)}</td>
    <td class="numeric"><span class="${trace.failed_checks ? "failed-number" : ""}">${trace.failed_checks ? `${trace.failed_checks} failed` : trace.evaluated_checks}</span>${trace.failed_checks ? `<span class="check-fraction"> / ${trace.evaluated_checks}</span>` : ""}</td>
    <td class="numeric duration-cell">${duration(trace.duration_ms)}<div class="duration-track"><span style="width:${Math.max(3, trace.duration_ms / maxDuration * 100)}%"></span></div></td>
    <td title="${escapeHTML(timeFull(trace.start_ns))}">${ago(trace.start_ns)}</td></tr>`).join("");
  $("tableWrap").hidden = !data.total;
  $("emptyState").hidden = Boolean(data.total);
  const filtered = [state.query, state.service, state.environment, state.origin, state.outcome, state.since_ns].some(Boolean);
  $("emptyTitle").textContent = filtered ? "No traces match these filters." : "Your intent traces belong here.";
  $("emptyDescription").textContent = filtered ? "Try a wider time range or clear your filters to see more execution evidence." : "Connect a Melampus instrumented application or run the synthetic demo to explore actual SDK check outcomes.";
  $("emptyAction").textContent = filtered ? "Clear filters" : "Connect your SDK";
  $("emptyAction").dataset.action = filtered ? "clear" : "setup";
  $("pagination").hidden = !data.total;
  $("pageDescriptionText").textContent = `${fmt(state.offset + 1)}–${fmt(state.offset + data.traces.length)} of ${fmt(data.total)}`;
  $("previousPage").disabled = state.offset === 0;
  $("nextPage").disabled = state.offset + state.limit >= data.total;
  renderFunctions();
  renderStatus();
  restoreFocus(savedFocus);
}

function renderFilters() {
  const filters = ["query", "service", "environment", "origin", "outcome"].filter(key => state[key]);
  $("activeFilters").innerHTML = filters.map(key => {
    const value = key === "origin" ? originLabels[state[key]] : key === "outcome" ? labels[state[key]] : state[key];
    return `<button class="filter-chip" data-clear="${key}" aria-label="Remove ${escapeHTML(key)} filter">${escapeHTML(key)}: ${escapeHTML(value)}${icon("close")}</button>`;
  }).join("") + (state.since_ns ? `<button class="filter-chip" data-clear="time" aria-label="Clear selected time window">${clock(state.since_ns)}–${clock(state.until_ns)}${icon("close")}</button>` : "");
  $("activeFilters").hidden = !filters.length && !state.since_ns;
  $("clearFilters").disabled = !filters.length && !state.since_ns;
}

function renderChart() {
  const maximum = Math.max(1, ...data.histogram.map(b => b.total));
  $("chartMax").textContent = fmt(data.histogram.some(b => b.total) ? maximum : 0);
  $("histogram").innerHTML = data.histogram.map((bin, i) => {
    const title = `${clock(bin.start_ns)} · ${bin.total} traces · ${bin.drift} drift · ${bin.error} errors. Select this time window.`;
    return `<button class="chart-bin" data-bin="${i}" aria-label="${escapeHTML(title)}" title="${escapeHTML(title)}"><span class="bin-error" style="height:${bin.error / maximum * 100}%"></span><span class="bin-drift" style="height:${bin.drift / maximum * 100}%"></span><span style="height:${(bin.total - bin.drift - bin.error) / maximum * 100}%"></span></button>`;
  }).join("");
  $("histogram").setAttribute("role", "group");
  $("histogram").setAttribute("aria-label", `${data.total} traces between ${timeFull(data.since_ns)} and ${timeFull(data.until_ns)}. Select a bar to filter by time.`);
  $("tickStart").textContent = clock(data.since_ns);
  $("tickMiddle").textContent = clock((data.since_ns + data.until_ns) / 2);
  $("tickEnd").textContent = clock(data.until_ns);
  $("windowDescription").textContent = state.since_ns ? "Selected time window" : $("timeSelect").selectedOptions[0].textContent;
}

function renderFunctions() {
  $("functionRows").innerHTML = data.functions.length ? data.functions.map((f, index) => `<tr class="function-row"><td><button class="trace-name" data-function="${index}" data-function-name="${escapeHTML(f.function)}" data-function-service="${escapeHTML(f.service)}">${escapeHTML(f.function)}</button><div class="row-meta">${fmt(f.evaluated)} evaluated checks · ${fmt(f.errors)} check errors</div></td><td>${escapeHTML(f.service)}</td><td class="numeric">${fmt(f.calls)}</td><td class="numeric ${f.failed ? "failed-number" : ""}">${fmt(f.failed)}</td><td class="numeric">${fmt(f.incomplete)}</td><td class="numeric">${f.intent_hashes.length}</td></tr>`).join("") : '<tr><td colspan="6" class="loading-cell">No instrumented functions in the current trace filters. Connect your SDK or clear filters in the explorer.</td></tr>';
  $("functionsNote").textContent = "Aggregated from all traces matching the explorer's filters, including pages beyond the current table. Intent versions count distinct observed hashes; prose stays in your codebase.";
}

function renderStatus() {
  if (!statusData) return;
  $("collectorStats").innerHTML = [
    ["Stored spans", fmt(statusData.stored_spans)], ["Capacity", fmt(statusData.max_spans)],
    ["Retention", `${statusData.retention_days} days`], ["Self telemetry drops", fmt(statusData.telemetry_dropped)],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
}

function showView(view) {
  state.view = view;
  for (const v of ["explorer", "functions", "mesh", "setup"]) $(v === "explorer" ? "exploreView" : `${v}View`).hidden = v !== view;
  document.querySelectorAll("[data-view]").forEach(button => {
    button.classList.toggle("active", button.dataset.view === view);
    if (button.dataset.view === view) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  });
  $("pageTitle").textContent = {explorer:"Trace Explorer", functions:"Functions", mesh:"System Mesh", setup:"Connect SDK"}[view];
  $("pageDescription").textContent = {explorer:"From a failed intent check to the code that ran.", functions:"Intent and check evidence, across your codebase.", mesh:"Declared intent and contracts, connected to the code that runs.", setup:"Send execution evidence to your local workspace."}[view];
  $("connectButton").hidden = view === "setup";
  document.querySelector(".privacy-note").textContent = view === "mesh" ? "Opt-in catalog text" : "Hashed declarations";
  document.title = `${$("pageTitle").textContent} · Melampus`;
  writeURL();
  if (view === "mesh" && typeof refreshMesh === "function") refreshMesh();
}

async function openTrace(id, trigger) {
  if (traceController) traceController.abort();
  traceController = new AbortController();
  returningFocus = trigger || document.activeElement;
  returningTraceId = returningFocus?.dataset?.trace || null;
  $("tracePanel").hidden = false;
  document.body.classList.add("has-panel");
  $("traceDetail").innerHTML = '<div class="panel-heading"><h2 id="tracePanelTitle">Loading trace…</h2><p>Fetching execution evidence</p></div>';
  configurePanelAccessibility();
  $("closeTrace").focus();
  try {
    const result = await api(`/api/traces/${encodeURIComponent(id)}`, {signal:traceController.signal});
    state.trace = result;
    const failed = result.spans.find(s => s.outcome === "drift") || result.spans.find(s => s.outcome === "error" || s.outcome === "incomplete");
    state.span = failed || result.spans.find(s => s.is_melampus) || result.spans[0];
    state.tab = "checks";
    renderTrace();
    writeURL();
    document.querySelectorAll("#traceRows .trace-row").forEach(row => row.classList.toggle("selected", row.dataset.trace === id));
  } catch (error) {
    if (error.name !== "AbortError") $("traceDetail").innerHTML = `<div class="panel-heading"><h2 id="tracePanelTitle">Trace unavailable</h2><p>${escapeHTML(error.message)}</p><button class="button" data-retry-trace="${escapeHTML(id)}">Retry trace</button></div>`;
  }
}

function closeTrace(restore = true) {
  const wasOpen = !$("tracePanel").hidden;
  if (traceController) traceController.abort();
  state.trace = null;
  state.span = null;
  $("tracePanel").hidden = true;
  document.body.classList.remove("has-panel");
  configurePanelAccessibility();
  writeURL();
  document.querySelectorAll("#traceRows .trace-row").forEach(row => row.classList.remove("selected"));
  if (wasOpen && restore) {
    const rowButton = [...document.querySelectorAll("#traceRows button[data-trace]")].find(button => button.dataset.trace === returningTraceId);
    (rowButton || (returningFocus?.isConnected ? returningFocus : $("searchInput"))).focus({preventScroll:true});
  }
}

function orderedSpans(spans) {
  const byId = new Map(spans.map(s => [s.span_id, s]));
  const children = new Map();
  spans.forEach(s => { const key = byId.has(s.parent_span_id) ? s.parent_span_id : null; if (!children.has(key)) children.set(key, []); children.get(key).push(s); });
  const result = [], visited = new Set();
  const walk = (span, depth) => {
    if (visited.has(span.span_id)) return;
    visited.add(span.span_id);
    result.push({span, depth:Math.min(depth, 6)});
    (children.get(span.span_id) || []).sort((a, b) => a.start_ns - b.start_ns).forEach(child => walk(child, depth + 1));
  };
  (children.get(null) || []).sort((a, b) => a.start_ns - b.start_ns).forEach(root => walk(root, 0));
  spans.forEach(s => { if (!visited.has(s.span_id)) walk(s, 0); });
  return result;
}

function renderTrace() {
  const trace = state.trace;
  const failures = trace.spans.flatMap(s => s.checks.filter(c => c.result === "failed").map(c => `${shortFunction(s.function)} → ${c.id}`));
  const spanRows = orderedSpans(trace.spans);
  const length = Math.max(1, trace.end_ns - trace.start_ns);
  $("traceDetail").innerHTML = `
    <div class="panel-heading"><h2 id="tracePanelTitle">${escapeHTML(shortFunction(trace.name))}</h2><p>${trace.trace_id}</p><div class="panel-badges">${badge(trace.outcome)}<span class="service-label">${escapeHTML(trace.service)}</span><span class="badge source">${escapeHTML(trace.environment)}</span>${trace.origin !== "application" ? `<span class="badge source">${escapeHTML(originLabels[trace.origin])}</span>` : ""}</div></div>
    <div class="panel-facts"><div><span>Duration</span>${duration(trace.duration_ms)}</div><div><span>Spans</span>${trace.span_count}</div><div><span>Evaluated checks</span>${trace.evaluated_checks}</div><div><span>Started</span>${clock(trace.start_ns)}</div></div>
    ${failures.length ? `<div class="failure-summary"><strong>${failures.length} failed ${failures.length === 1 ? "intent check" : "intent checks"}</strong>${failures.map(f => escapeHTML(f)).join("<br>")}</div>` : ""}
    <section class="waterfall-section" aria-label="Trace waterfall"><div class="waterfall-heading"><h2>Execution waterfall</h2><span>Select a span to inspect its checks</span></div><div class="waterfall-ruler"><span>0</span><span>${duration(trace.duration_ms / 2)}</span><span>${duration(trace.duration_ms)}</span></div>
    ${spanRows.map(({span, depth}) => `<button class="waterfall-row ${state.span.span_id === span.span_id ? "selected" : ""}" data-span="${span.span_id}" aria-pressed="${state.span.span_id === span.span_id}" title="${escapeHTML(span.function)} · ${duration(span.duration_ms)}"><span class="waterfall-label" style="--indent:${depth * 12}px"><span class="outcome-dot ${span.outcome}"></span><span>${escapeHTML(shortFunction(span.function))}</span></span><span class="waterfall-timeline"><span class="waterfall-bar ${span.outcome}" style="--start:${(span.start_ns - trace.start_ns) / length * 100}%;--duration:${(span.end_ns - span.start_ns) / length * 100}%"></span></span></button>`).join("")}</section>
    <section class="span-section" aria-label="Selected span evidence"><h3>${escapeHTML(state.span.function)}</h3><div class="detail-tabs" role="group" aria-label="Span details"><button data-tab="checks" class="${state.tab === "checks" ? "selected" : ""}" aria-pressed="${state.tab === "checks"}">Intent checks <span>(${state.span.checks.length})</span></button><button data-tab="attributes" class="${state.tab === "attributes" ? "selected" : ""}" aria-pressed="${state.tab === "attributes"}">Attributes</button></div><div id="spanContent">${renderSpan()}</div></section>`;
}

function renderSpan() {
  const span = state.span;
  if (state.tab === "attributes") {
    const attrs = {"span.id":span.span_id, "parent.span.id":span.parent_span_id || "Root span", "duration":duration(span.duration_ms), ...span.resource, ...span.attributes};
    return `<dl class="attribute-list">${Object.entries(attrs).map(([key, value]) => `<div><dt>${escapeHTML(key)}</dt><dd>${escapeHTML(typeof value === "object" ? JSON.stringify(value) : value)}</dd></div>`).join("")}</dl><p class="evidence-note">Only Melampus declarations and selected service resource metadata are persisted. Span events and unrelated attributes are excluded.</p>`;
  }
  if (!span.checks.length) return `<p class="evidence-note">${span.is_melampus ? "This function declares no checks. Its intent is unverified." : "This is an ordinary OpenTelemetry context span. It carries no Melampus intent checks."}</p>`;
  return `<div class="hash-field">Intent SHA-256<br>${escapeHTML(span.intent_hash)}</div>${span.checks.map(check => `<div class="check-row"><div><strong>${escapeHTML(check.id)}</strong>${badge(check.result)}</div><p>${escapeHTML(explanations[check.result])}</p><div class="hash-field">Contract SHA-256 · ${escapeHTML(check.contract_hash)}<br>Configured sample rate · ${(check.sample_rate * 100).toFixed(0)}%</div></div>`).join("")}<p class="evidence-note">Intent prose and predicate source stay in your codebase. Compare these hashes with the reviewed declaration; the platform never reconstructs or invents the contract text.</p>`;
}

async function runDemo() {
  if (busyDemo) return;
  busyDemo = true;
  $("demoButton").disabled = true;
  $("demoButton").textContent = "Generating SDK traces…";
  try {
    const result = await api("/api/demo", {method:"POST"});
    state.origin = "demo";
    state.outcome = "drift";
    state.service = "";
    state.query = "";
    state.environment = "";
    state.since_ns = null;
    state.until_ns = null;
    state.offset = 0;
    $("searchInput").value = "";
    writeURL();
    await refresh();
    toast(`${result.generated_traces} synthetic checkout traces generated with the Melampus SDK`);
  } catch (error) { showError(error); }
  finally { busyDemo = false; $("demoButton").disabled = false; $("demoButton").innerHTML = `${icon("play")}Run synthetic demo`; }
}

$("searchInput").value = state.query;
$("timeSelect").value = String(state.minutes);
$("sortSelect").value = state.sort;
$("searchForm").addEventListener("submit", event => { event.preventDefault(); clearTimeout(searchTimer); setFilter("query", $("searchInput").value.trim()); });
$("searchInput").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => setFilter("query", $("searchInput").value.trim()), 350); });
$("environmentSelect").addEventListener("change", event => setFilter("environment", event.target.value));
$("sortSelect").addEventListener("change", event => setFilter("sort", event.target.value));
$("timeSelect").addEventListener("change", event => { state.since_ns = null; state.until_ns = null; setFilter("minutes", Number(event.target.value)); });
$("facets").addEventListener("change", event => { if (event.target.dataset.filter) setFilter(event.target.dataset.filter, event.target.checked ? event.target.value : ""); });
$("clearFilters").addEventListener("click", clearFilters);
$("activeFilters").addEventListener("click", event => {
  const button = event.target.closest("[data-clear]");
  if (!button) return;
  if (button.dataset.clear === "time") { state.since_ns = null; state.until_ns = null; state.offset = 0; writeURL(); refresh(); }
  else setFilter(button.dataset.clear, "");
});
$("allTracesButton").addEventListener("click", () => setFilter("outcome", ""));
$("failedTracesButton").addEventListener("click", () => setFilter("outcome", "drift"));
$("refreshButton").addEventListener("click", refresh);
$("retryButton").addEventListener("click", refresh);
$("liveButton").addEventListener("click", () => { state.live = !state.live; $("liveButton").setAttribute("aria-pressed", String(state.live)); $("liveButton").querySelector("span:last-child").textContent = state.live ? "Live" : "Paused"; refresh(); });
$("mobileFilters").addEventListener("click", () => { const open = $("facets").classList.toggle("is-open"); $("mobileFilters").setAttribute("aria-expanded", String(open)); });
$("previousPage").addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); refresh(); });
$("nextPage").addEventListener("click", () => { state.offset += state.limit; refresh(); });
$("traceRows").addEventListener("click", event => { const row = event.target.closest("[data-trace]"); if (row) openTrace(row.dataset.trace, row.querySelector("button") || row); });
$("traceDetail").addEventListener("click", event => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.span) { state.span = state.trace.spans.find(s => s.span_id === button.dataset.span); renderTrace(); $("traceDetail").querySelector(`[data-span="${state.span.span_id}"]`).focus({preventScroll:true}); }
  if (button.dataset.tab) { state.tab = button.dataset.tab; renderTrace(); $("traceDetail").querySelector(`[data-tab="${state.tab}"]`).focus({preventScroll:true}); }
  if (button.dataset.retryTrace) openTrace(button.dataset.retryTrace);
});
$("histogram").addEventListener("click", event => {
  const bin = event.target.closest("[data-bin]");
  if (!bin) return;
  const index = Number(bin.dataset.bin);
  state.since_ns = data.histogram[index].start_ns;
  state.until_ns = data.histogram[index + 1]?.start_ns || data.until_ns;
  state.offset = 0;
  writeURL(); refresh();
});
$("functionRows").addEventListener("click", event => {
  const button = event.target.closest("[data-function]");
  if (!button) return;
  const fn = data.functions[Number(button.dataset.function)];
  state.query = fn.function; state.service = fn.service; state.outcome = ""; state.offset = 0;
  $("searchInput").value = state.query;
  showView("explorer"); refresh();
});
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => { closeTrace(false); showView(button.dataset.view); }));
$("connectButton").addEventListener("click", () => { closeTrace(false); showView("setup"); });
$("emptyAction").addEventListener("click", () => $("emptyAction").dataset.action === "clear" ? clearFilters() : showView("setup"));
$("demoButton").addEventListener("click", runDemo);
$("closeTrace").addEventListener("click", () => closeTrace());
$("copyTrace").addEventListener("click", () => { if (state.trace) copyText(state.trace.trace_id); });
document.addEventListener("keydown", event => {
  if (event.key === "Tab" && !$("tracePanel").hidden && panelMedia.matches) {
    const controls = [...$("tracePanel").querySelectorAll('button:not([disabled]), a[href], input, select, textarea, [tabindex="0"]')].filter(element => element.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (!$("tracePanel").contains(document.activeElement) || (event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  }
  if (event.key === "Escape" && !$("tracePanel").hidden) closeTrace();
  if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { event.preventDefault(); showView("explorer"); $("searchInput").focus(); }
});

const endpoint = `${location.origin}/v1/traces`;
$("endpointText").textContent = endpoint;
const snippet = `from melampus import Check, instrumented
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

provider = TracerProvider(resource=Resource.create({
    "service.name": "my-application",
    "deployment.environment.name": "local",
}))
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint=${JSON.stringify(endpoint)})
))
trace.set_tracer_provider(provider)  # Configure once at application startup.

@instrumented(
    intent="Return a nonnegative total",
    checks=[Check("nonnegative", lambda r: r >= 0, "Total is nonnegative")],
)
def calculate_total():
    return 42

calculate_total()
provider.shutdown()  # Flush before process exit.`;
$("setupSnippet").textContent = snippet;
$("copyEndpoint").addEventListener("click", () => copyText(endpoint));
$("copySnippet").addEventListener("click", () => copyText(snippet));
const initialTrace = params.get("trace");
showView(state.view);
refresh().then(() => { if (initialTrace) openTrace(initialTrace); });
setInterval(() => { if (state.live && !document.hidden && !busyDemo && state.view !== "setup") state.view === "mesh" ? refreshMesh() : refresh(); }, 5000);
