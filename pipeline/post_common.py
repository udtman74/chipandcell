"""글 생성 공통: frontmatter 직렬화 · 마크다운 표 · 면책."""

DISCLAIMER = ("*This note was produced by Chip & Cell's data pipeline with "
              "model-assisted analysis. It is not investment advice; verify all "
              "figures against primary sources.*")


def frontmatter(title, date, description, ticker=None, sector=None, tags=None):
    lines = ["---", f'title: "{title}"', f"date: {date}",
             f'description: "{description}"']
    if ticker:
        lines.append(f'ticker: "{ticker}"')
    if sector:
        lines.append(f"sector: {sector}")
    if tags:
        lines.append("tags: [" + ", ".join(f'"{t}"' for t in tags) + "]")
    lines.append("---")
    return "\n".join(lines)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def fmt_pct(v):
    return "—" if v is None else f"{v:+.2f}%"


def fmt_won(v):
    return "—" if v is None else f"₩{round(v):,}"


def market_line(market):
    """프롬프트용 시장 컨텍스트 한 줄. 지수 피드가 스테일이면 수치 대신 명시적 불가 표기."""
    mk, mq = market.get("kospi", {}), market.get("kosdaq", {})
    if mk.get("stale") or mq.get("stale"):
        return "Market index context unavailable today (index feed stale) — do not comment on the broader market."
    return (f"Market: KOSPI {fmt_pct(mk.get('pct'))} today, "
            f"KOSDAQ {fmt_pct(mq.get('pct'))}")
