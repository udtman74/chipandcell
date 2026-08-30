// 탭 이동 후 최종 URL/타이틀 출력 (판정용, 항상 종료)
// usage: PORT=9222 node cdp_goto.mjs <tabId> <url> [waitMs]
const PORT = process.env.PORT || "9222";
const [tabId, url, waitMs] = process.argv.slice(2);
const hardExit = setTimeout(() => { console.log("HARD-TIMEOUT"); process.exit(3); }, 45000);
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
await new Promise((r) => (ws.onopen = r));
await send("Page.navigate", { url });
await new Promise((r) => setTimeout(r, Number(waitMs || 10000)));
const info = await send("Runtime.evaluate", { expression: "JSON.stringify({u: location.href, t: document.title})", returnByValue: true });
console.log(info.result?.value);
clearTimeout(hardExit);
process.exit(0);
