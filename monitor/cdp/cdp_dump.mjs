// 현재 탭의 Shadow DOM 관통 텍스트 + 보이는 input/버튼류 좌표 덤프 (진단용)
// usage: PORT=9222 node cdp_dump.mjs <tabId>
const PORT = process.env.PORT || "9222";
const [tabId] = process.argv.slice(2);
const list = await (await fetch(`http://localhost:${PORT}/json/list`)).json();
const tab = list.find((x) => x.id === tabId);
if (!tab) { console.log("no-tab"); process.exit(1); }
const ws = new WebSocket(tab.webSocketDebuggerUrl);
let mid = 0; const pend = {};
ws.addEventListener("message", (ev) => {
  const d = JSON.parse(ev.data);
  if (d.id && pend[d.id]) { pend[d.id](d.result); delete pend[d.id]; }
});
const send = (m, p = {}) => new Promise((res) => { const id = ++mid; pend[id] = res; ws.send(JSON.stringify({ id, method: m, params: p })); });
const evalJs = async (e) => (await send("Runtime.evaluate", { expression: e, returnByValue: true })).result?.value;
await new Promise((r) => (ws.onopen = r));

const out = await evalJs(`(() => {
  function txt(node) {
    let o = "";
    if (node.shadowRoot) o += txt(node.shadowRoot);
    for (const c of node.childNodes) {
      if (c.nodeType === 3) o += c.textContent + " ";
      else if (c.nodeType === 1) o += txt(c);
    }
    return o;
  }
  const widgets = [];
  function walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) walk(el.shadowRoot);
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && ["INPUT", "BUTTON", "TEXTAREA"].includes(el.tagName)) {
        widgets.push({ tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
          label: (el.getAttribute("aria-label") || el.placeholder || txt(el)).trim().slice(0, 40),
          value: (el.value || "").slice(0, 60) });
      }
    }
  }
  walk(document);
  return JSON.stringify({ url: location.href, text: txt(document.body).replace(/\\s+/g, " ").slice(0, 1200), widgets }, null, 1);
})()`);
console.log(out);
