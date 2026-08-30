// GSC 사이트맵 제출: sitemaps 페이지에서 입력창에 경로 입력 → 제출 → 결과 텍스트
// usage: PORT=9222 node cdp_gsc_sitemap.mjs <tabId> <resource_id> <sitemapPath>
const PORT = process.env.PORT || "9222";
const [tabId, resource, path] = process.argv.slice(2);
const hardExit = setTimeout(() => { console.log("HARD-TIMEOUT"); process.exit(3); }, 90000);
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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const click = async (x, y) => {
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
};
await new Promise((r) => (ws.onopen = r));
await send("Page.navigate", { url: "https://search.google.com/search-console/sitemaps?resource_id=" + encodeURIComponent(resource) });
await sleep(9000);

const HELPERS = `
function __inputs() {
  const found = [];
  function walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === "INPUT") {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) found.push({ x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width,
          label: (el.getAttribute("aria-label") || el.placeholder || "").slice(0, 40) });
      }
    }
  }
  walk(document);
  return found;
}
function __clickText(needle) {
  let done = false;
  function own(el) { return [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim(); }
  function walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) walk(el.shadowRoot);
      if (!done && own(el) === needle) {
        const btn = el.closest("button,[role=button]") ||
          (el.getRootNode() instanceof ShadowRoot ? el.getRootNode().host.closest("button,[role=button]") : null);
        (btn || el).click();
        done = true;
      }
    }
  }
  walk(document);
  return done;
}
function __text() {
  function txt(node) {
    let o = "";
    if (node.shadowRoot) o += txt(node.shadowRoot);
    for (const c of node.childNodes) {
      if (c.nodeType === 3) o += c.textContent + " ";
      else if (c.nodeType === 1 && !["SCRIPT", "STYLE"].includes(c.tagName)) o += txt(c);
    }
    return o;
  }
  return txt(document.body).replace(/\\s+/g, " ");
}`;

// 사이트맵 입력창(가장 넓은 보이는 input, "사이트맵" aria 우선)
const ins = JSON.parse((await evalJs(`(() => { ${HELPERS} return JSON.stringify(__inputs()); })()`)) || "[]");
const cand = ins.find((i) => i.label.includes("사이트맵")) || ins.filter((i) => i.x > 0).sort((a, b) => b.w - a.w)[0];
if (!cand) { console.log("no-input", JSON.stringify(ins)); process.exit(1); }
await click(cand.x, cand.y);
await sleep(700);
await send("Input.insertText", { text: path });
await sleep(700);
const submitted = await evalJs(`(() => { ${HELPERS} return __clickText("제출"); })()`);
console.log("submit-click:", submitted);
await sleep(9000);
const text = (await evalJs(`(() => { ${HELPERS} return __text(); })()`)) || "";
const i = text.indexOf("사이트맵");
console.log("RESULT:", text.slice(Math.max(0, i), i + 400));
clearTimeout(hardExit);
process.exit(0);
