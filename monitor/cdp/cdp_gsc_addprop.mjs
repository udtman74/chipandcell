// GSC 속성 추가 1단계: welcome에서 URL 접두어 입력 → 계속 → HTML 파일 검증 파일명 추출
// usage: PORT=9222 node cdp_gsc_addprop.mjs <tabId> <propertyUrl>
// 출력: FILE:google<hex>.html (성공) / 페이지 관통 텍스트 일부 (진단)
const PORT = process.env.PORT || "9222";
const [tabId, prop] = process.argv.slice(2);
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
await send("Page.enable");

const PIERCE = `
function __pierceText() {
  function txt(node) {
    let out = "";
    if (node.shadowRoot) out += txt(node.shadowRoot);
    for (const c of node.childNodes) {
      if (c.nodeType === 3) out += c.textContent + " ";
      else if (c.nodeType === 1) out += txt(c);
    }
    return out;
  }
  return txt(document.body).replace(/\\s+/g, " ");
}
function __allCoords(needle) {
  const hits = [];
  function walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) walk(el.shadowRoot);
      const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim();
      if (own.includes(needle)) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) hits.push({ x: r.x + r.width / 2, y: r.y + r.height / 2 });
      }
    }
  }
  walk(document);
  return hits;
}
function __inputs() {
  const found = [];
  function walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === "INPUT") {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) found.push({ x: r.x + r.width / 2, y: r.y + r.height / 2 });
      }
    }
  }
  walk(document);
  return found;
}`;

await send("Page.navigate", { url: "https://search.google.com/search-console/welcome" });
await sleep(8000);

// URL 접두어 카드의 입력창 = 화면 오른쪽(최대 x) 입력
const inputs = await evalJs(`(() => { ${PIERCE} return JSON.stringify(__inputs()); })()`);
const ins = JSON.parse(inputs || "[]");
if (!ins.length) { console.log("no-input; text=", (await evalJs(`(() => { ${PIERCE} return __pierceText(); })()`) || "").slice(0, 300)); process.exit(1); }
const inp = ins.reduce((a, b) => (b.x > a.x ? b : a));
await click(inp.x, inp.y);
await sleep(800);
await send("Input.insertText", { text: prop });
await sleep(800);

// "계속" 버튼: 오른쪽 카드의 것 = 최대 x
const conts = JSON.parse(await evalJs(`(() => { ${PIERCE} return JSON.stringify(__allCoords("계속")); })()`) || "[]");
if (!conts.length) { console.log("no-continue"); process.exit(1); }
const btn = conts.reduce((a, b) => (b.x > a.x ? b : a));
await click(btn.x, btn.y);
await sleep(10000);

// 검증 다이얼로그에서 HTML 파일명 추출 (필요시 재시도)
for (let i = 0; i < 4; i++) {
  const text = (await evalJs(`(() => { ${PIERCE} return __pierceText(); })()`)) || "";
  const m = text.match(/google[0-9a-f]+\.html/);
  if (m) { console.log("FILE:" + m[0]); process.exit(0); }
  if (/이미 확인된|소유권이 자동으로 확인|확인된 소유자/.test(text)) { console.log("ALREADY-VERIFIED"); console.log(text.slice(0, 400)); process.exit(0); }
  await sleep(5000);
}
console.log("no-file; text=", ((await evalJs(`(() => { ${PIERCE} return __pierceText(); })()`)) || "").slice(0, 600));
