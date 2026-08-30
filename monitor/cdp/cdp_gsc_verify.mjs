// GSC 검증 다이얼로그: "확인"류 버튼 탐색(--list) 또는 지정 좌표 클릭 후 결과 텍스트 출력
// usage: PORT=9222 node cdp_gsc_verify.mjs <tabId> --list
//        PORT=9222 node cdp_gsc_verify.mjs <tabId> <x> <y>
const PORT = process.env.PORT || "9222";
const [tabId, a1, a2] = process.argv.slice(2);
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
await new Promise((r) => (ws.onopen = r));

const FINDBTN = `
function __btns() {
  const hits = [];
  function own(el) { return [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim(); }
  function walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) walk(el.shadowRoot);
      const t = own(el);
      if (["확인", "완료", "나중에", "확인하기", "속성으로 이동", "VERIFY", "DONE"].includes(t)) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) hits.push({ t, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), w: Math.round(r.width) });
      }
    }
  }
  walk(document);
  return hits;
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

if (a1 === "--list") {
  console.log(await evalJs(`(() => { ${FINDBTN} return JSON.stringify(__btns()); })()`));
  process.exit(0);
}
const x = Number(a1), y = Number(a2);
await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
await sleep(9000);
const text = (await evalJs(`(() => { ${FINDBTN} return __text(); })()`)) || "";
const m = text.match(/(소유권[^.]{0,80}|확인(되었|하지 못)[^.]{0,60}|오류[^.]{0,60})/g);
console.log("RESULT:", m ? m.slice(0, 5).join(" | ") : text.slice(0, 400));
console.log("BTNS:", await evalJs(`(() => { ${FINDBTN} return JSON.stringify(__btns()); })()`));
