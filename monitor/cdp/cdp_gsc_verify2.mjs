// GSC 검증: own-text "확인" 스팬의 조상 버튼을 JS로 직접 click() → 결과 텍스트
// usage: PORT=9222 node cdp_gsc_verify2.mjs <tabId> <nearY>  (nearY에 가장 가까운 후보 클릭)
const PORT = process.env.PORT || "9222";
const [tabId, nearY] = process.argv.slice(2);
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

const res = await evalJs(`(() => {
  const cands = [];
  function own(el) { return [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim(); }
  function walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) walk(el.shadowRoot);
      if (own(el) === "확인") {
        const btn = el.closest("button,[role=button]") ||
          (el.getRootNode() instanceof ShadowRoot ? el.getRootNode().host.closest("button,[role=button]") : null);
        const r = el.getBoundingClientRect();
        if (r.width > 0) cands.push({ y: Math.round(r.y), hasBtn: !!btn, el, btn });
      }
    }
  }
  walk(document);
  const target = cands.filter(c => c.hasBtn).sort((a, b) => Math.abs(a.y - ${Number(nearY)}) - Math.abs(b.y - ${Number(nearY)}))[0];
  if (!target) return JSON.stringify({ clicked: false, cands: cands.map(c => ({ y: c.y, hasBtn: c.hasBtn })) });
  target.btn.click();
  return JSON.stringify({ clicked: true, y: target.y });
})()`);
console.log("CLICK:", res);
await sleep(10000);
const text = (await evalJs(`(() => {
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
})()`)) || "";
const m = text.match(/(소유권이 확인됨|소유권 확인됨|확인되었습니다|확인하지 못했|실패|오류가 발생)[^|]{0,80}/g);
console.log("RESULT:", m ? m.slice(0, 4).join(" | ") : "no-match; " + text.slice(text.indexOf("소유권"), text.indexOf("소유권") + 300));
