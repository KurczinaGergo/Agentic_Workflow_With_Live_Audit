import argparse
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from audit_model import derive_graph_state, load_audit_snapshot, load_events, load_transcripts
from workflow_config import resolve_audit_dir


POLL_INTERVAL_SECONDS = 0.5


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


def read_new_jsonl_lines(path: Path, offset: int) -> tuple[list[dict], int]:
    if not path.exists():
        return [], offset
    size = path.stat().st_size
    if size < offset:
        offset = 0
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        for line in handle:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        offset = handle.tell()
    return entries, offset


def live_view_html(workflow_name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{workflow_name} Live Audit</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --line: #cbd5e1;
      --ink: #0f172a;
      --muted: #475569;
      --blue: #2563eb;
      --green: #15803d;
      --amber: #b45309;
      --red: #b91c1c;
      --radius: 8px;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ min-height: 100%; }}
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--ink); }}
    header {{ padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--line); }}
    h1 {{ margin: 0 0 2px; font-size: 1.15rem; }}
    p {{ margin: 0; color: var(--muted); }}
    main {{ width: 100%; min-height: calc(100vh - 58px); margin: 0; padding: 8px; display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 8px; }}
    .toolbar, section {{ background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 8px; }}
    .toolbar {{ position: sticky; top: 0; z-index: 10; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: 6px; }}
    .stat {{ border: 1px solid var(--line); border-radius: var(--radius); padding: 5px 7px; }}
    .stat span {{ display: block; color: var(--muted); font-size: 0.75rem; text-transform: uppercase; }}
    .stat strong {{ display: block; margin-top: 1px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    button, select {{ border: 1px solid var(--line); background: white; border-radius: var(--radius); padding: 6px 9px; cursor: pointer; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .tab-button[aria-selected="true"] {{ background: var(--blue); border-color: var(--blue); color: white; }}
    .graph-filters {{ display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; grid-column: 1 / -1; padding-top: 2px; color: var(--muted); }}
    .graph-filter {{ display: inline-flex; align-items: center; gap: 5px; font-size: 0.85rem; }}
    .graph-filter input {{ margin: 0; }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .tab-panel.layout.active {{ display: grid; }}
    input[type="range"] {{ flex: 1; min-width: 220px; }}
    .layout {{ display: grid; grid-template-columns: minmax(300px, 1fr) minmax(320px, 0.8fr); gap: 14px; }}
    #graphPanel.active {{ min-height: calc(100vh - 156px); display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 6px; padding: 8px; }}
    #graphPanel h2 {{ margin: 0; font-size: 1rem; }}
    .graph {{ min-height: 0; position: relative; overflow: auto; }}
    .node-graph {{ border: 1px solid var(--line); border-radius: var(--radius); background: #f8fafc; height: 100%; min-height: calc(100vh - 204px); overflow: auto; }}
    .graph-svg {{ display: block; width: 100%; min-width: var(--graph-min-width, 960px); height: 100%; min-height: var(--graph-min-height, 640px); }}
    .graph-edge {{ stroke: #64748b; stroke-width: 1.8; fill: none; }}
    .graph-edge.message-edge {{ stroke: var(--blue); stroke-dasharray: 5 5; }}
    .graph-edge.channel-edge {{ stroke: var(--green); }}
    .graph-edge.terminated-edge, .graph-edge.closed-edge {{ stroke: var(--red); }}
    .graph-label {{ fill: var(--muted); font-size: 11px; text-anchor: middle; paint-order: stroke; stroke: #f8fafc; stroke-width: 4px; stroke-linejoin: round; }}
    .graph-node rect, .graph-node circle {{ stroke: #64748b; stroke-width: 1.6; fill: #ffffff; }}
    .graph-node.agent.active rect {{ stroke: var(--blue); fill: #eff6ff; }}
    .graph-node.agent.terminated rect {{ stroke: var(--red); fill: #fef2f2; }}
    .graph-node.delegation rect {{ stroke: var(--amber); fill: #fffbeb; }}
    .graph-node.delegation.completed rect {{ stroke: var(--green); fill: #ecfdf5; }}
    .graph-node.channel circle {{ stroke: var(--green); fill: #f0fdf4; }}
    .graph-node.channel.closed circle {{ stroke: var(--red); fill: #fef2f2; }}
    .graph-node.role rect {{ stroke-dasharray: 4 3; fill: #f8fafc; }}
    .graph-node text {{ fill: var(--ink); font-size: 12px; text-anchor: middle; pointer-events: none; }}
    .graph-node .sub {{ fill: var(--muted); font-size: 10px; }}
    .agents, .edges {{ display: grid; gap: 8px; }}
    .agent, .edge, .timeline-item {{ border: 1px solid var(--line); border-radius: var(--radius); padding: 8px; background: #f8fafc; }}
    .agent.active {{ border-color: var(--blue); }}
    .agent.terminated {{ border-color: var(--red); background: #fef2f2; }}
    .edge.completed {{ border-color: var(--green); background: #ecfdf5; }}
    .edge.failed, .edge.rejected {{ border-color: var(--red); background: #fef2f2; }}
    .edge.danger {{ border-color: var(--red); background: #fef2f2; }}
    .edge.warning {{ border-color: var(--amber); background: #fffbeb; }}
    .edge.open, .edge.created {{ border-color: var(--amber); background: #fffbeb; }}
    .message {{ border-color: var(--blue); background: #eff6ff; }}
    .meta {{ color: var(--muted); font-size: 0.82rem; overflow-wrap: anywhere; }}
    .timeline {{ display: grid; gap: 6px; max-height: 720px; overflow: auto; }}
    .timeline-item.current {{ outline: 2px solid var(--blue); }}
    .attention {{ color: var(--red); }}
    @media (max-width: 900px) {{
      main {{ min-height: calc(100vh - 74px); }}
      .toolbar {{ grid-template-columns: 1fr; }}
      .layout {{ grid-template-columns: 1fr; }}
      #graphPanel.active {{ min-height: calc(100vh - 250px); }}
      .node-graph {{ min-height: calc(100vh - 300px); }}
      .graph-svg {{ min-width: var(--graph-min-width, 760px); min-height: var(--graph-min-height, 520px); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{workflow_name} Live Workflow Audit</h1>
    <p>Live graph, event stream, and timestamp replay from canonical workflow audit JSONL files.</p>
  </header>
  <main>
    <div class="toolbar">
      <div class="stats" id="stats"></div>
      <div class="controls">
        <button id="liveButton">Live</button>
        <button id="resetButton">Reset</button>
        <button id="playButton">Play</button>
        <button id="pauseButton">Pause</button>
        <label>Speed <select id="speed"><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="2">2x</option><option value="5">5x</option><option value="10">10x</option></select></label>
        <input id="scrubber" type="range" min="0" value="0">
        <span id="clock" class="meta">No events</span>
      </div>
      <div class="tabs" role="tablist" aria-label="Audit views">
        <button class="tab-button" type="button" role="tab" aria-selected="true" aria-controls="graphPanel" data-tab-target="graphPanel">Graph</button>
        <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="detailsPanel" data-tab-target="detailsPanel">Replay And Details</button>
      </div>
      <div class="graph-filters" aria-label="Graph filters">
        <span class="meta">Graph filters</span>
        <label class="graph-filter"><input type="checkbox" data-graph-filter="showClosed"> Show terminated or closed nodes</label>
        <label class="graph-filter"><input type="checkbox" data-graph-filter="showChannels"> Show channels</label>
        <label class="graph-filter"><input type="checkbox" data-graph-filter="showTasks" checked> Show tasks</label>
      </div>
    </div>
    <section class="tab-panel active" id="graphPanel" role="tabpanel">
      <h2>Live Graph</h2>
      <div class="graph">
        <div class="node-graph" id="nodeGraph"></div>
      </div>
    </section>
    <div class="tab-panel layout" id="detailsPanel" role="tabpanel">
      <section>
        <h2>Audit Details</h2>
        <div>
          <h3>Attention</h3>
          <div class="edges" id="attention"></div>
          <h3>Agents</h3>
          <div class="agents" id="agents"></div>
          <h3>Contracts And Channels</h3>
          <div class="edges" id="edges"></div>
          <h3>Messages</h3>
          <div class="edges" id="messages"></div>
        </div>
      </section>
      <section>
        <h2>Replay Timeline</h2>
        <div class="timeline" id="timeline"></div>
      </section>
    </div>
  </main>
  <script>
    let fullSnapshot = null;
    let liveMode = true;
    let playTimer = null;
    const graphFilters = {{ showClosed: false, showChannels: false, showTasks: true }};
    const state = {{ events: [], transcripts: [], timeline: [] }};

    const stats = document.querySelector("#stats");
    const nodeGraphEl = document.querySelector("#nodeGraph");
    const attentionEl = document.querySelector("#attention");
    const agentsEl = document.querySelector("#agents");
    const edgesEl = document.querySelector("#edges");
    const messagesEl = document.querySelector("#messages");
    const timelineEl = document.querySelector("#timeline");
    const scrubber = document.querySelector("#scrubber");
    const clock = document.querySelector("#clock");
    const graphFilterInputs = document.querySelectorAll("[data-graph-filter]");

    function byTime(items) {{
      return [...items].sort((a, b) => {{
        const at = Date.parse(a.timestamp || "");
        const bt = Date.parse(b.timestamp || "");
        if (Number.isNaN(at) && Number.isNaN(bt)) return (a.sequence || 0) - (b.sequence || 0);
        if (Number.isNaN(at)) return 1;
        if (Number.isNaN(bt)) return -1;
        return at - bt || ((a.sequence || 0) - (b.sequence || 0));
      }});
    }}

    function timelineFrom(events, transcripts) {{
      let seq = 0;
      return byTime([
        ...events.map((entry) => ({{ kind: "event", timestamp: entry.timestamp, entry, sequence: seq++ }})),
        ...transcripts.map((entry) => ({{ kind: "transcript", timestamp: entry.timestamp, entry, sequence: seq++ }})),
      ]);
    }}

    function derive(items) {{
      const events = items.filter((item) => item.kind === "event").map((item) => item.entry);
      const transcripts = items.filter((item) => item.kind === "transcript").map((item) => item.entry);
      const workflowPersistentRoles = new Set(["architect"]);
      const runPersistentRoles = new Set(["main_context"]);
      const requiredDelegationEventTypes = new Set([
        "delegation.created",
        "runtime.agent.spawned",
        "binding.delegation_runtime_agent",
        "runtime.channel.created",
        "binding.delegation_channel"
      ]);
      const workflowCloseEventTypes = new Set(["workflow.closed", "workflow.completed"]);
      const agents = new Map();
      const delegations = new Map();
      const channels = new Map();
      const messages = [];
      const attention = [];
      function roleRequiresRuntimeTermination(role) {{
        return !workflowPersistentRoles.has(role || "") && !runPersistentRoles.has(role || "");
      }}
      function roleRequiresTerminationOnClose(role) {{
        return workflowPersistentRoles.has(role || "");
      }}
      function addAttention(kind, severity, summary) {{
        if (!attention.some((item) => item.kind === kind && item.severity === severity && item.summary === summary)) {{
          attention.push({{ kind, severity, summary }});
        }}
      }}
      function agent(id) {{
        if (!id) return null;
        if (!agents.has(id)) agents.set(id, {{ id, role: "", status: "active", spawned_at: null, terminated_at: null, last_seen_at: null }});
        return agents.get(id);
      }}
      function isRolePlaceholderTarget(event) {{
        const payload = event.payload || {{}};
        return event.event_type === "delegation.created" && event.target_agent_id && payload.target_role && event.target_agent_id === payload.target_role;
      }}
      for (const event of events) {{
        const payload = event.payload || {{}};
        const src = agent(event.source_agent_id);
        const dst = isRolePlaceholderTarget(event) ? null : agent(event.target_agent_id);
        if (src) src.last_seen_at = event.timestamp;
        if (dst) dst.last_seen_at = event.timestamp;
        if (event.event_type === "runtime.agent.spawned" && dst) {{
          dst.role = payload.role || dst.role;
          dst.status = "active";
          dst.spawned_at = event.timestamp;
        }}
        if (event.event_type === "runtime.agent.terminated" && dst) {{
          dst.status = "terminated";
          dst.terminated_at = event.timestamp;
          dst.ended_reason = payload.ended_reason || payload.summary;
        }}
        if (event.delegation_id) {{
          if (!delegations.has(event.delegation_id)) delegations.set(event.delegation_id, {{ id: event.delegation_id, status: "open", events: [] }});
          const del = delegations.get(event.delegation_id);
          del.events.push(event);
          del.source_agent_id = del.source_agent_id || event.source_agent_id;
          del.target_agent_id = del.target_agent_id || event.target_agent_id;
          del.workflow_step = del.workflow_step || event.workflow_step;
          del.target_role = del.target_role || payload.target_role || payload.role;
          del.summary = payload.summary || payload.purpose || del.summary;
          if (event.event_type === "delegation.created") del.status = payload.status || "created";
          if (event.event_type === "binding.delegation_runtime_agent") del.runtime_agent_id = event.target_agent_id;
          if (event.event_type === "binding.delegation_channel") del.channel_id = event.channel_id;
          if (["delegation.completed", "delegation.failed", "delegation.rejected"].includes(event.event_type)) {{
            del.status = payload.status || event.event_type.split(".").pop();
            del.result = payload.result;
            del.ended_at = event.timestamp;
          }}
        }}
        if (event.channel_id) {{
          if (!channels.has(event.channel_id)) channels.set(event.channel_id, {{ id: event.channel_id, status: "open" }});
          const channel = channels.get(event.channel_id);
          channel.delegation_id = channel.delegation_id || event.delegation_id;
          if (event.event_type === "runtime.channel.created") {{
            channel.status = "open";
            channel.owners = payload.owners || [event.source_agent_id, event.target_agent_id].filter(Boolean);
          }}
          if (event.event_type === "runtime.channel.closed") channel.status = "closed";
        }}
        if (event.event_type === "logical.message.sent") messages.push({{ id: event.event_id, kind: "event", ...event }});
      }}
      for (const transcript of transcripts) messages.push({{ id: transcript.message_id, kind: "transcript", ...transcript }});
      for (const delegation of delegations.values()) {{
        const eventTypes = new Set((delegation.events || []).map((event) => event.event_type));
        const terminals = (delegation.events || []).map((event, index) => ({{ event, index }})).filter((item) => ["delegation.completed", "delegation.failed", "delegation.rejected"].includes(item.event.event_type));
        if (!eventTypes.has("delegation.created") && terminals.length) {{
          addAttention("lifecycle", "danger", `${{delegation.id}} has a terminal delegation event without delegation.created`);
        }}
        for (const requiredType of requiredDelegationEventTypes) {{
          if (!eventTypes.has(requiredType)) {{
            addAttention("lifecycle", "warning", `${{delegation.id}} missing required event: ${{requiredType}}`);
          }}
        }}
        const runtimeAgent = delegation.runtime_agent_id ? agents.get(delegation.runtime_agent_id) : null;
        const runtimeRole = delegation.target_role || (runtimeAgent ? runtimeAgent.role : "");
        if (delegation.runtime_agent_id) {{
          for (const terminal of terminals) {{
            if (terminal.event.source_agent_id !== delegation.runtime_agent_id) {{
              addAttention("lifecycle", "danger", `${{delegation.id}} terminal event source_agent_id ${{terminal.event.source_agent_id}} does not match bound runtime agent ${{delegation.runtime_agent_id}}`);
            }}
          }}
        }}
        if (terminals.length) {{
          const terminalIndex = terminals[terminals.length - 1].index;
          (delegation.events || []).forEach((event, index) => {{
            if (index > terminalIndex && requiredDelegationEventTypes.has(event.event_type) && event.event_type !== "delegation.created") {{
              addAttention("lifecycle", "danger", `${{delegation.id}} ${{event.event_type}} appears after terminal delegation event`);
            }}
          }});
        }}
        if (
          ["completed", "failed", "rejected"].includes(delegation.status)
          && runtimeAgent
          && roleRequiresRuntimeTermination(runtimeRole)
          && runtimeAgent.status !== "terminated"
        ) {{
          addAttention("lifecycle", "warning", `${{delegation.id}} ended as ${{delegation.status}} but runtime agent ${{delegation.runtime_agent_id}} has no runtime.agent.terminated event`);
        }}
        const channel = delegation.channel_id ? channels.get(delegation.channel_id) : null;
        if (["completed", "failed", "rejected"].includes(delegation.status) && channel && channel.status !== "closed") {{
          addAttention("lifecycle", "warning", `${{delegation.id}} ended as ${{delegation.status}} but channel ${{delegation.channel_id}} has no runtime.channel.closed event`);
        }}
      }}
      for (const delegation of delegations.values()) {{
        const terminals = (delegation.events || []).filter((event) => ["delegation.completed", "delegation.failed", "delegation.rejected"].includes(event.event_type));
        for (const terminal of terminals) {{
          const sourceAgent = terminal.source_agent_id ? agents.get(terminal.source_agent_id) : null;
          if (["codex_main", "MainContext"].includes(terminal.source_agent_id)) continue;
          if (sourceAgent && !sourceAgent.spawned_at && !sourceAgent.role) {{
            addAttention("lifecycle", "warning", `${{terminal.source_agent_id}} produced a terminal event without runtime.agent.spawned evidence`);
          }}
        }}
      }}
      if (events.some((event) => workflowCloseEventTypes.has(event.event_type))) {{
        for (const item of agents.values()) {{
          if (roleRequiresTerminationOnClose(item.role) && item.status !== "terminated") {{
            addAttention("lifecycle", "warning", `workflow close requires runtime.agent.terminated for ${{item.role}} ${{item.id}}`);
          }}
        }}
      }}
      return {{ agents: [...agents.values()], delegations: [...delegations.values()], channels: [...channels.values()], messages, attention }};
    }}

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\\"": "&quot;",
        "'": "&#39;"
      }}[char]));
    }}

    function shortId(value, max = 28) {{
      const text = String(value ?? "");
      return text.length > max ? `${{text.slice(0, max - 1)}}…` : text;
    }}

    function layoutRow(nodes, y, width) {{
      const count = Math.max(nodes.length, 1);
      const usable = Math.max(width - 160, 160);
      nodes.forEach((node, index) => {{
        node.x = 80 + (usable * (index + 0.5)) / count;
        node.y = y;
      }});
    }}

    function isClosedStatus(status) {{
      return ["closed", "completed", "failed", "rejected"].includes(status);
    }}

    function getVisibleGraph(graph) {{
      const agents = (graph.agents || []).filter((agent) => graphFilters.showClosed || agent.status !== "terminated");
      const delegations = graphFilters.showTasks
        ? (graph.delegations || []).filter((delegation) => graphFilters.showClosed || !isClosedStatus(delegation.status))
        : [];
      const channels = graphFilters.showChannels
        ? (graph.channels || []).filter((channel) => graphFilters.showClosed || !isClosedStatus(channel.status))
        : [];
      const visibleAgentIds = new Set(agents.map((agent) => agent.id));
      const messages = (graph.messages || []).filter((message) => (
        visibleAgentIds.has(message.source_agent_id) && visibleAgentIds.has(message.target_agent_id)
      ));
      return {{ agents, delegations, channels, messages }};
    }}

    function renderNodeGraph(graph) {{
      const visibleGraph = getVisibleGraph(graph);
      const agents = visibleGraph.agents.map((item) => ({{ ...item, kind: "agent", key: `agent:${{item.id}}` }}));
      const delegations = visibleGraph.delegations.map((item) => ({{ ...item, kind: "delegation", key: `delegation:${{item.id}}` }}));
      const channels = visibleGraph.channels.map((item) => ({{ ...item, kind: "channel", key: `channel:${{item.id}}` }}));
      const roleMap = new Map();

      for (const delegation of delegations) {{
        if (!delegation.runtime_agent_id && delegation.target_role) {{
          const key = `role:${{delegation.target_role}}`;
          if (!roleMap.has(key)) roleMap.set(key, {{ id: delegation.target_role, kind: "role", key }});
        }}
      }}

      const roles = [...roleMap.values()];
      const top = [...agents, ...roles];
      const rowCount = Math.max(top.length, delegations.length, channels.length, 1);
      const width = Math.max(nodeGraphEl.clientWidth || 1100, rowCount * 210, 960);
      const height = Math.max(nodeGraphEl.clientHeight || 700, 680);
      nodeGraphEl.style.setProperty("--graph-min-width", `${{width}}px`);
      nodeGraphEl.style.setProperty("--graph-min-height", `${{height}}px`);
      layoutRow(top, Math.max(80, height * 0.16), width);
      layoutRow(delegations, Math.max(220, height * 0.5), width);
      layoutRow(channels, Math.max(360, height * 0.84), width);

      const nodes = [...top, ...delegations, ...channels];
      const byKey = new Map(nodes.map((node) => [node.key, node]));
      const edges = [];

      for (const delegation of delegations) {{
        const source = byKey.get(`agent:${{delegation.source_agent_id}}`);
        const target = byKey.get(`delegation:${{delegation.id}}`);
        const runtime = byKey.get(`agent:${{delegation.runtime_agent_id}}`) || byKey.get(`role:${{delegation.target_role}}`);
        if (source && target) edges.push({{ from: source, to: target, label: delegation.status || "delegation", className: `delegation-edge ${{delegation.status || ""}}` }});
        if (target && runtime) edges.push({{ from: target, to: runtime, label: delegation.workflow_step || "assigned", className: `delegation-edge ${{delegation.status || ""}}` }});
        if (delegation.channel_id) {{
          const channel = byKey.get(`channel:${{delegation.channel_id}}`);
          if (target && channel) edges.push({{ from: target, to: channel, label: "channel", className: "channel-edge" }});
        }}
      }}

      for (const channel of channels) {{
        const channelNode = byKey.get(`channel:${{channel.id}}`);
        for (const owner of channel.owners || []) {{
          const ownerNode = byKey.get(`agent:${{owner}}`);
          if (ownerNode && channelNode) edges.push({{ from: ownerNode, to: channelNode, label: channel.status || "channel", className: `channel-edge ${{channel.status === "closed" ? "closed-edge" : ""}}` }});
        }}
      }}

      for (const message of visibleGraph.messages.slice(-12)) {{
        const source = byKey.get(`agent:${{message.source_agent_id}}`);
        const target = byKey.get(`agent:${{message.target_agent_id}}`);
        if (source && target) edges.push({{ from: source, to: target, label: message.message_type || "message", className: "message-edge" }});
      }}

      if (!nodes.length) {{
        nodeGraphEl.innerHTML = "<p class='meta' style='padding: 12px;'>No graph nodes yet.</p>";
        return;
      }}

      const edgeSvg = edges.map((edge) => {{
        const midX = (edge.from.x + edge.to.x) / 2;
        const midY = (edge.from.y + edge.to.y) / 2;
        const curve = Math.max(Math.abs(edge.to.y - edge.from.y) * 0.35, 24);
        const path = `M ${{edge.from.x}} ${{edge.from.y}} C ${{edge.from.x}} ${{edge.from.y + curve}}, ${{edge.to.x}} ${{edge.to.y - curve}}, ${{edge.to.x}} ${{edge.to.y}}`;
        return `<path class="graph-edge ${{edge.className}}" marker-end="url(#arrow)" d="${{path}}"></path><text class="graph-label" x="${{midX}}" y="${{midY - 5}}">${{escapeHtml(shortId(edge.label, 18))}}</text>`;
      }}).join("");

      const nodeSvg = nodes.map((node) => {{
        const title = escapeHtml(shortId(node.id, 34));
        const sub = escapeHtml(shortId(node.role || node.status || node.kind, 26));
        const status = escapeHtml(node.status || "");
        if (node.kind === "channel") {{
          return `<g class="graph-node channel ${{status}}" transform="translate(${{node.x}}, ${{node.y}})"><circle r="38"></circle><text y="-2">${{title}}</text><text class="sub" y="15">${{sub}}</text></g>`;
        }}
        const width = node.kind === "delegation" ? 178 : 158;
        return `<g class="graph-node ${{node.kind}} ${{status}}" transform="translate(${{node.x - width / 2}}, ${{node.y - 30}})"><rect width="${{width}}" height="60" rx="8"></rect><text x="${{width / 2}}" y="25">${{title}}</text><text class="sub" x="${{width / 2}}" y="43">${{sub}}</text></g>`;
      }}).join("");

      nodeGraphEl.innerHTML = `<svg class="graph-svg" viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="Workflow node graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"></path>
          </marker>
        </defs>
        ${{edgeSvg}}
        ${{nodeSvg}}
      </svg>`;
    }}

    function render(snapshot, visibleItems = null) {{
      const graph = visibleItems ? derive(visibleItems) : snapshot.graph;
      stats.innerHTML = [
        ["Events", snapshot.events.length],
        ["Transcripts", snapshot.transcripts.length],
        ["Agents", graph.agents.length],
        ["Delegations", graph.delegations.length],
        ["Channels", graph.channels.length],
        ["Attention", (graph.attention || []).length],
        ["Timeline", state.timeline.length]
      ].map(([label, value]) => `<div class="stat"><span>${{label}}</span><strong>${{value}}</strong></div>`).join("");
      renderNodeGraph(graph);
      attentionEl.innerHTML = (graph.attention || []).map((item) => `<div class="edge ${{item.severity || "warning"}}"><strong>${{item.kind || "attention"}}</strong><div class="meta">${{escapeHtml(item.summary || "")}}</div></div>`).join("") || "<p class='meta'>No attention items.</p>";
      agentsEl.innerHTML = graph.agents.map((agent) => `<div class="agent ${{agent.status || "active"}}"><strong>${{agent.id}}</strong><div class="meta">${{agent.role || ""}} ${{agent.status || ""}}</div></div>`).join("") || "<p class='meta'>No agents yet.</p>";
      edgesEl.innerHTML = [
        ...graph.delegations.map((item) => `<div class="edge ${{item.status || "open"}}"><strong>Delegation ${{item.id}}</strong><div class="meta">${{item.source_agent_id || ""}} -> ${{item.runtime_agent_id || item.target_role || ""}}<br>${{item.workflow_step || ""}} ${{item.status || ""}}</div></div>`),
        ...graph.channels.map((item) => `<div class="edge ${{item.status || "open"}}"><strong>Channel ${{item.id}}</strong><div class="meta">${{(item.owners || []).join(" <-> ")}}<br>${{item.status || ""}}</div></div>`)
      ].join("") || "<p class='meta'>No contracts or channels yet.</p>";
      messagesEl.innerHTML = graph.messages.slice(-20).reverse().map((item) => `<div class="edge message"><strong>${{item.message_type || item.event_type || "message"}}</strong><div class="meta">${{item.source_agent_id || ""}} -> ${{item.target_agent_id || ""}}<br>${{item.timestamp || ""}}</div></div>`).join("") || "<p class='meta'>No messages yet.</p>";
      timelineEl.innerHTML = state.timeline.map((item, index) => `<div class="timeline-item" data-index="${{index}}"><strong>${{item.kind}}</strong> ${{item.entry.event_type || item.entry.message_type || ""}}<div class="meta">${{item.timestamp || "missing timestamp"}}</div></div>`).join("");
      scrubber.max = Math.max(state.timeline.length - 1, 0);
      clock.textContent = state.timeline.length ? state.timeline[Math.min(Number(scrubber.value), state.timeline.length - 1)].timestamp || "missing timestamp" : "No events";
    }}

    function applyReplayIndex(index) {{
      liveMode = false;
      const visible = state.timeline.slice(0, index + 1);
      document.querySelectorAll(".timeline-item").forEach((item) => item.classList.toggle("current", Number(item.dataset.index) === index));
      render(fullSnapshot, visible);
      scrubber.value = index;
    }}

    async function loadSnapshot() {{
      const response = await fetch("/api/snapshot");
      fullSnapshot = await response.json();
      state.events = fullSnapshot.events;
      state.transcripts = fullSnapshot.transcripts;
      state.timeline = timelineFrom(state.events, state.transcripts);
      render(fullSnapshot);
      scrubber.value = Math.max(state.timeline.length - 1, 0);
    }}

    function connectEvents() {{
      const stream = new EventSource("/api/events");
      stream.addEventListener("workflow_event", (event) => {{
        state.events.push(JSON.parse(event.data));
        state.timeline = timelineFrom(state.events, state.transcripts);
        fullSnapshot.events = state.events;
        fullSnapshot.graph = derive(state.timeline);
        if (liveMode) {{
          scrubber.value = Math.max(state.timeline.length - 1, 0);
          render(fullSnapshot);
        }}
      }});
      stream.addEventListener("channel_message", (event) => {{
        state.transcripts.push(JSON.parse(event.data));
        state.timeline = timelineFrom(state.events, state.transcripts);
        fullSnapshot.transcripts = state.transcripts;
        fullSnapshot.graph = derive(state.timeline);
        if (liveMode) {{
          scrubber.value = Math.max(state.timeline.length - 1, 0);
          render(fullSnapshot);
        }}
      }});
    }}

    scrubber.addEventListener("input", () => applyReplayIndex(Number(scrubber.value)));
    document.querySelector("#liveButton").addEventListener("click", () => {{ liveMode = true; scrubber.value = Math.max(state.timeline.length - 1, 0); render(fullSnapshot); }});
    document.querySelector("#resetButton").addEventListener("click", () => applyReplayIndex(0));
    document.querySelector("#pauseButton").addEventListener("click", () => clearInterval(playTimer));
    document.querySelector("#playButton").addEventListener("click", () => {{
      clearInterval(playTimer);
      liveMode = false;
      playTimer = setInterval(() => {{
        const next = Number(scrubber.value) + 1;
        if (next >= state.timeline.length) {{ clearInterval(playTimer); liveMode = true; return; }}
        applyReplayIndex(next);
      }}, 1000 / Number(document.querySelector("#speed").value));
    }});
    document.querySelectorAll(".tab-button").forEach((button) => {{
      button.addEventListener("click", () => {{
        document.querySelectorAll(".tab-button").forEach((item) => item.setAttribute("aria-selected", "false"));
        document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
        button.setAttribute("aria-selected", "true");
        document.querySelector(`#${{button.dataset.tabTarget}}`).classList.add("active");
        if (button.dataset.tabTarget === "graphPanel" && fullSnapshot) renderNodeGraph(fullSnapshot.graph);
      }});
    }});
    graphFilterInputs.forEach((input) => {{
      const filterName = input.dataset.graphFilter;
      graphFilters[filterName] = input.checked;
      input.addEventListener("change", () => {{
        graphFilters[filterName] = input.checked;
        if (!fullSnapshot) return;
        if (liveMode) {{
          render(fullSnapshot);
        }} else {{
          applyReplayIndex(Number(scrubber.value));
        }}
      }});
    }});
    window.addEventListener("resize", () => {{
      if (fullSnapshot && document.querySelector("#graphPanel").classList.contains("active")) renderNodeGraph(fullSnapshot.graph);
    }});

    loadSnapshot().then(connectEvents);
  </script>
</body>
</html>"""


class LiveAuditHandler(BaseHTTPRequestHandler):
    audit_dir: Path
    workflow_name: str

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, payload: object) -> None:
        body = json_bytes(payload)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = live_view_html(self.workflow_name).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/snapshot":
            self.send_json(load_audit_snapshot(self.audit_dir))
            return

        if parsed.path == "/api/events":
            self.stream_events()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def stream_events(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        log_path = self.audit_dir / "workflow_log.jsonl"
        channels_dir = self.audit_dir / "channels"
        offsets: dict[Path, int] = {log_path: log_path.stat().st_size if log_path.exists() else 0}

        try:
            while True:
                entries, offsets[log_path] = read_new_jsonl_lines(log_path, offsets.get(log_path, 0))
                for entry in entries:
                    self.write_sse("workflow_event", entry)

                if channels_dir.exists():
                    for transcript_path in sorted(channels_dir.glob("*.jsonl")):
                        if transcript_path not in offsets:
                            offsets[transcript_path] = transcript_path.stat().st_size
                            continue
                        messages, offsets[transcript_path] = read_new_jsonl_lines(
                            transcript_path,
                            offsets.get(transcript_path, 0),
                        )
                        for message in messages:
                            message["_file_name"] = transcript_path.name
                            self.write_sse("channel_message", message)

                self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
                time.sleep(POLL_INTERVAL_SECONDS)
        except (BrokenPipeError, ConnectionResetError):
            return

    def write_sse(self, event_name: str, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str)
        self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a live workflow audit graph and replay viewer.")
    parser.add_argument("--workflow-name", help="Workflow folder name under the configured audit root.")
    parser.add_argument("--config", help="Path to workflow.config.yaml for the target repository.")
    parser.add_argument("--audit-root", help="Override the audit root path from config.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    audit_dir, workflow_name, _ = resolve_audit_dir(args.workflow_name, args.config, args.audit_root)
    (audit_dir / "channels").mkdir(parents=True, exist_ok=True)
    (audit_dir / "workflow_log.jsonl").touch(exist_ok=True)

    handler = type(
        "ConfiguredLiveAuditHandler",
        (LiveAuditHandler,),
        {"audit_dir": audit_dir, "workflow_name": workflow_name},
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Live audit viewer: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
