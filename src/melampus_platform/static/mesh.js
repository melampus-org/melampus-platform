"use strict";

let meshData = null, meshSelected = null, meshController = null;
let meshCodebase = new URLSearchParams(location.search).get("codebase") || "";
labels.unobserved = "No execution";
const declarationLabels = {matching:"Matches catalog", mismatch:"Declaration mismatch", unknown:"No catalog", unobserved:"Not observed"};

async function refreshMesh() {
  meshController?.abort();
  const controller = new AbortController();
  meshController = controller;
  const query = new URLSearchParams({minutes:$("meshTime").value, environment:$("meshEnvironment").value});
  if (meshCodebase) query.set("codebase", meshCodebase);
  try {
    const result = await api(`/api/mesh?${query}`, {signal:controller.signal});
    if (meshController !== controller) return;
    meshData = result;
    meshCodebase = result.codebase;
    $("meshCodebase").innerHTML = result.catalogs.length ? result.catalogs.map(c => `<option value="${escapeHTML(c.codebase)}">${escapeHTML(c.codebase)}</option>`).join("") : '<option value="">Observed functions · no catalog</option>';
    $("meshCodebase").value = meshCodebase;
    const url = new URL(location.href);
    if (state.view === "mesh" && meshCodebase) { url.searchParams.set("codebase", meshCodebase); history.replaceState(null, "", url); }
    const environment = $("meshEnvironment").value || state.environment;
    $("meshEnvironment").innerHTML = '<option value="">All environments</option>' + [...new Set([...environments, environment])].filter(Boolean).sort().map(e => `<option value="${escapeHTML(e)}">${escapeHTML(e)}</option>`).join("");
    $("meshEnvironment").value = environment;
    $("meshProvenance").textContent = result.revision ? `${result.codebase === "checkout-demo" ? "Synthetic demo · " : result.codebase === "melampus-platform" ? "Platform itself · " : ""}Catalog revision ${result.revision} · Text explicitly supplied by the catalog · Runtime: ${$("meshTime").selectedOptions[0].textContent.toLowerCase()}` : "No catalog imported. Observed hashes are available; readable intent stays unknown until you import declarations.";
    $("meshSummary").innerHTML = [["Declared boundaries",result.summary.declared],["Observed",result.summary.observed],["No execution",result.summary.unobserved],["Intent drift",result.summary.drift],["Declaration mismatches",result.summary.mismatch]].map(([label,count]) => `<span>${escapeHTML(label)} <strong>${fmt(count)}</strong></span>`).join("");
    if (!result.nodes.some(n => n.id === meshSelected)) meshSelected = (result.nodes.find(n => n.outcome === "drift") || result.nodes[0])?.id || null;
    renderMesh();
    $("errorBanner").hidden = true;
  } catch (error) { if (error.name !== "AbortError") showError(error); }
}

function meshNodes() {
  const query = $("meshSearch").value.trim().toLowerCase();
  return (meshData?.nodes || []).filter(node => !query || [node.function,node.service,node.declaration?.intent,...(node.declaration?.checks || []).map(c => c.contract)].join(" ").toLowerCase().includes(query));
}

function renderMesh() {
  const active = document.activeElement;
  const focusedNode = active.dataset.meshNode, focusedTrace = active.dataset.meshTrace;
  const focusRegion = active.closest("#meshRows") ? "meshRows" : active.closest("#meshInspector") ? "meshInspector" : "meshCanvas";
  const nodes = meshNodes(), drawn = nodes.slice(0, 160);
  if (!nodes.some(n => n.id === meshSelected)) meshSelected = nodes[0]?.id || null;
  const groups = new Map();
  drawn.forEach(n => { const key = `${n.service} / ${n.module}`; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(n); });
  const positions = new Map(), headings = [];
  const columns = Math.min(3, Math.max(1, groups.size));
  const groupList = [...groups];
  let y = 20;
  for (let start = 0; start < groupList.length; start += columns) {
    const row = groupList.slice(start, start + columns);
    row.forEach(([title, functions], col) => {
      const x = 20 + col * 250;
      headings.push(`<div class="mesh-module" style="left:${x}px;top:${y}px;width:218px" title="${escapeHTML(title)}">${escapeHTML(title)}</div>`);
      functions.forEach((n, index) => positions.set(n.id, {x, y:y + 36 + index * 90}));
    });
    y += Math.max(...row.map(([,functions]) => functions.length)) * 90 + 82;
  }
  const edges = (meshData?.edges || []).filter(e => positions.has(e.source) && positions.has(e.target));
  const paths = edges.map(e => {
    const a = positions.get(e.source), b = positions.get(e.target);
    const dx=b.x-a.x, dy=b.y-a.y;
    const x1=Math.abs(dx)>50 ? a.x+(dx>0 ? 218 : 0) : a.x+109;
    const x2=Math.abs(dx)>50 ? b.x+(dx>0 ? 0 : 218) : b.x+109;
    const y1=Math.abs(dx)>50 ? a.y+36 : a.y+(dy>0 ? 74 : 0);
    const y2=Math.abs(dx)>50 ? b.y+36 : b.y+(dy>0 ? 0 : 74);
    const bend=Math.max(20,Math.abs(x2-x1)/3), direction=x2>=x1 ? 1 : -1;
    const path=e.source === e.target ? `M ${a.x+218} ${a.y+15} C ${a.x+253} ${a.y-12}, ${a.x+253} ${a.y+90}, ${a.x+218} ${a.y+58}` : (Math.abs(dx)>50 ? `M ${x1} ${y1} C ${x1+direction*bend} ${y1}, ${x2-direction*bend} ${y2}, ${x2} ${y2}` : `M ${x1} ${y1} C ${x1} ${(y1+y2)/2}, ${x2} ${(y1+y2)/2}, ${x2} ${y2}`);
    return `<path d="${path}" class="${e.calls ? "mesh-observed-edge" : "mesh-declared-edge"}" marker-end="url(#mesh-arrow)"><title>${e.calls ? `${e.calls} observed calls${e.declared ? " · also declared" : ""}` : "Declared dependency · not observed"}</title></path>`;
  }).join("");
  $("meshCanvas").style.width = drawn.length ? `${columns * 250 + 30}px` : "100%";
  $("meshCanvas").style.height = drawn.length ? `${Math.max(300,y)}px` : "300px";
  $("meshCanvas").innerHTML = drawn.length ? `<svg class="mesh-edges" width="100%" height="100%" aria-hidden="true"><defs><marker id="mesh-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="var(--muted)" stroke="none"/></marker></defs>${paths}</svg>${headings.join("")}${drawn.map(n => {
    const p = positions.get(n.id);
    return `<button class="mesh-node ${n.id === meshSelected ? "selected" : ""} ${n.outcome === "unobserved" ? "not-observed" : ""}" data-mesh-node="${n.id}" aria-pressed="${n.id === meshSelected}" style="left:${p.x}px;top:${p.y}px" title="${escapeHTML(n.function)}"><strong>${escapeHTML(shortFunction(n.function))}</strong><span class="mesh-node-evidence"><span class="outcome-dot ${n.outcome}"></span>${escapeHTML(labels[n.outcome])}<span>${fmt(n.calls)} calls</span></span>${n.declaration_status === "mismatch" ? '<span class="mesh-mismatch">Catalog mismatch</span>' : `<small>${n.declaration ? `${n.declaration.checks.length} declared checks` : "Intent text unavailable"}</small>`}</button>`;
  }).join("")}` : '<div class="empty-state"><h2>No matching code boundaries</h2><p>Clear the search or import a catalog to include your declared functions, even before they run.</p></div>';
  $("meshLimit").hidden = nodes.length <= drawn.length && !meshData?.truncated;
  $("meshLimit").textContent = `Map shows ${drawn.length} of ${nodes.length} loaded matches. Search narrows the map; the inventory lists all loaded functions.${meshData?.truncated ? ` Server snapshot is bounded: ${meshData.total_nodes} total nodes and ${meshData.total_edges} edges.` : ""}`;
  $("meshInventoryCount").textContent = `${nodes.length} functions`;
  $("meshRows").innerHTML = nodes.length ? nodes.map(n => `<tr><td><button class="trace-name" data-mesh-node="${n.id}">${escapeHTML(n.function)}</button><div class="row-meta">${escapeHTML(n.service)}</div></td><td class="mesh-intent-cell">${escapeHTML(n.declaration?.intent || "Intent text unavailable · import a catalog")}</td><td>${badge(n.outcome)}<div class="row-meta">${fmt(n.calls)} calls · ${fmt(n.failed_checks)} failed checks</div></td><td><span class="${n.declaration_status === "mismatch" ? "failed-number" : ""}">${declarationLabels[n.declaration_status]}</span></td></tr>`).join("") : '<tr><td colspan="4" class="loading-cell">No functions match the current search.</td></tr>';
  renderMeshInspector();
  if (!active.isConnected) {
    const target = focusedNode ? [...$(focusRegion).querySelectorAll("[data-mesh-node]")].find(b => b.dataset.meshNode === focusedNode) : focusedTrace ? document.querySelector(`[data-mesh-trace="${focusedTrace}"]`) : null;
    (target || $("meshSearch")).focus({preventScroll:true});
  }
}

function renderMeshInspector() {
  const n = meshData?.nodes.find(node => node.id === meshSelected);
  if (!n) { $("meshInspector").innerHTML = '<h2>Select a code boundary</h2><p>Import a declaration catalog to read intent and contracts, including functions without execution evidence.</p>'; return; }
  const d = n.declaration;
  const relationships = meshData.edges.filter(e => e.source === n.id || e.target === n.id);
  $("meshInspector").innerHTML = `<div class="mesh-inspector-heading"><h2>${escapeHTML(shortFunction(n.function))}</h2><code>${escapeHTML(n.module)}</code><p>${escapeHTML(n.service)}</p>${badge(n.outcome)}</div>
    ${n.declaration_status === "mismatch" ? '<p class="mesh-warning" role="status">Observed declaration hashes differ from this catalog. The text below describes the catalog revision; it does not explain mismatched calls.</p>' : ""}
    <div class="mesh-evidence-line">${fmt(n.calls)} observed calls · ${fmt(n.matching_calls)} match this declaration${n.mismatched_calls ? ` · ${fmt(n.mismatched_calls)} mismatched` : ""}</div>
    <h3>Declared intent</h3><p class="mesh-intent-text">${escapeHTML(d?.intent || "No catalog declaration. Runtime hashes cannot reveal intent text.")}</p>
    ${d ? `<p class="hash-field">Intent SHA-256<br>${escapeHTML(d.intent_hash)}</p><h3>Executable contracts <span class="muted-note">(${d.checks.length})</span></h3>${d.checks.length ? d.checks.map(c => {
      const evidence = n.check_observations[c.id] || {};
      return `<div class="mesh-contract"><strong>${escapeHTML(c.id)}</strong><p>${escapeHTML(c.contract)}</p><p class="mesh-check-evidence">${Object.keys(evidence).length ? Object.entries(evidence).map(([outcome,count]) => `${escapeHTML(labels[outcome])}: ${fmt(count)}`).join(" · ") : "No matching execution evidence"}</p><div class="hash-field">${escapeHTML(c.contract_hash)}<br>Configured sample rate · ${(c.sample*100).toLocaleString(undefined,{maximumSignificantDigits:15})}% · rate ${c.sample}</div></div>`;
    }).join("") : '<p class="evidence-note">This declaration has no executable checks.</p>'}<p class="evidence-note">Check totals above include only calls matching the full catalog declaration. Suppressed and missing evidence never count as passes.</p><h3>Assumptions</h3>${d.assumptions.length ? `<ul>${d.assumptions.map(a => `<li>${escapeHTML(a)}</li>`).join("")}</ul>` : '<p class="muted-note">No assumptions declared.</p>'}` : ""}
    <h3>Connections</h3>${relationships.length ? `<ul class="mesh-connections">${relationships.slice(0,20).map(e => {
      const neighbor=meshData.nodes.find(other => other.id === (e.source === n.id ? e.target : e.source));
      return `<li><button class="text-button" data-mesh-node="${neighbor.id}">${e.source === n.id ? "To" : "From"} ${escapeHTML(shortFunction(neighbor.function))}</button><span>${e.calls ? `${fmt(e.calls)} observed calls${e.declared ? " · declared" : ""}` : "Declared · no observed calls"}</span></li>`;
    }).join("")}</ul>` : '<p class="muted-note">No declared or observed connections in this window.</p>'}
    <h3>Execution traces</h3>${n.trace_ids.length ? n.trace_ids.map(id => `<a class="mesh-trace-link" data-mesh-trace="${id}" href="/?trace=${id}&minutes=${$("meshTime").value}"><code>${id.slice(0,16)}</code>${icon("arrow")}</a>`).join("") : '<p class="muted-note">No traces in this time and environment window. This does not establish that the function passes.</p>'}`;
}

$("meshView").addEventListener("click", event => {
  const node=event.target.closest("[data-mesh-node]");
  if (!node) return;
  meshSelected=node.dataset.meshNode;
  renderMesh();
  if (matchMedia("(max-width:1100px)").matches) { $("meshInspector").focus({preventScroll:true}); $("meshInspector").scrollIntoView({behavior:"auto",block:"start"}); }
});
$("meshSearch").addEventListener("input", renderMesh);
$("meshCodebase").addEventListener("change", () => { meshCodebase=$("meshCodebase").value; meshSelected=null; refreshMesh(); });
$("meshTime").addEventListener("change", () => { state.minutes=Number($("meshTime").value); writeURL(); refreshMesh(); });
$("meshEnvironment").addEventListener("change", () => { state.environment=$("meshEnvironment").value; writeURL(); refreshMesh(); });
$("meshReset").addEventListener("click", () => { $("meshSearch").value=""; $("meshScroll").scrollTo({top:0,left:0}); renderMesh(); });
$("meshImport").addEventListener("click", () => $("meshFile").click());
$("meshFile").addEventListener("change", async () => {
  const file=$("meshFile").files[0];
  if (!file) return;
  $("meshImport").disabled=true;
  try {
    if (file.size > 1024*1024) throw new Error("Catalog exceeds 1 MiB.");
    const document=JSON.parse(await file.text());
    const result=await api("/api/catalog",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(document)});
    meshCodebase=result.codebase; meshSelected=null;
    await refreshMesh(); toast(`${result.functions} declarations imported for ${result.codebase}`);
  } catch(error) { showError(error); }
  finally { $("meshImport").disabled=false; $("meshFile").value=""; }
});
$("meshTime").value=String(state.minutes);
if (state.view === "mesh") refreshMesh();
