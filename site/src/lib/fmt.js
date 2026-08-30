export function won(n) {
  if (n == null) return "—";
  return "₩" + Math.round(n).toLocaleString("en-US");
}

export function pct(n) {
  if (n == null) return { text: "—", cls: "" };
  const text = (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
  return { text, cls: n > 0 ? "up" : n < 0 ? "down" : "" };
}

export function bil(n) {
  if (n == null) return "—";
  return "₩" + n.toLocaleString("en-US") + "B";
}
