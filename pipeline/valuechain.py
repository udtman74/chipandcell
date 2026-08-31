"""밸류체인 단계 SSOT. 관계선은 공개 자료로 확인된 것만 포함한다.

각 종목은 정확히 한 단계에 속한다(test_valuechain이 전건 강제).
LINKS의 source는 확인 가능한 URL, year는 그 자료의 연도여야 한다.
tier="disclosure"는 공시·회사 공식발표·사업보고서 수치 기반,
tier="reported"는 주요 언론이 양사를 명시했으나 계약 공시는 아닌 경우다.

의도적으로 제외한 관계(2026-09-01 조사):
- 042700 → 005930: 반증됨. 삼성은 HBM4에 세메스 TC-NCF 본더 사용, 한미는 "논의" 단계만 보도
- 011790 → 373220: 반증됨. SKC 조회공시 답변 "합의된 사실 없다", LGES "전혀 사실 아님"
- 399720 → 005930: 방향이 반대. 삼성 파운드리는 가온칩스의 고객이 아니라 웨이퍼를 맡기는 상류 팹
- 005070 → 373220: 실제 공시 상대방은 LG화학(051910)으로 커버리지 밖
- 086520 → 006400: 공급 주체가 비상장 자회사 에코프로이노베이션이며 086520 본체가 아님
- 064760 → 005930/000660: 직접 고객은 Lam·AMAT·TEL 등 장비 OEM, IDM에는 간접 도달
- 121600 → 셀 3사: 출처가 증권사 커버리지로만 환원되어 1차 확인 불가
"""
import json
import os

STAGES = {
    "semiconductor": [
        {"key": "design", "label": "Design & IP", "codes": ["399720"]},
        {"key": "equipment", "label": "Equipment",
         "codes": ["042700", "403870", "039030", "240810", "036930"]},
        {"key": "materials", "label": "Materials",
         "codes": ["357780", "005290", "064760"]},
        {"key": "memory", "label": "Chip Manufacturing",
         "codes": ["005930", "000660", "000990"]},
        {"key": "backend", "label": "Back-end & Test",
         "codes": ["058470", "067310", "095340"]},
    ],
    "battery": [
        {"key": "cathode", "label": "Cathode & Precursor",
         "codes": ["247540", "086520", "003670", "066970", "005070"]},
        {"key": "submaterials", "label": "Sub-materials & Equipment",
         "codes": ["011790", "020150", "121600", "278280"]},
        {"key": "cell", "label": "Cell Makers",
         "codes": ["373220", "006400", "096770"]},
    ],
}

# 분류가 회사 실체를 오해시킬 수 있는 경우의 각주.
NOTES = {
    "096770": ("Refining and energy group; battery cells are produced by SK On, "
               "its unlisted subsidiary. Refining supplied the majority of FY2025 revenue."),
    "086520": ("Holding company. Its battery-materials operations — cathode, precursor and "
               "lithium hydroxide — sit in subsidiaries."),
    "011790": ("Classified by its copper-foil business (anode current collector). "
               "Chemicals remains its largest segment by revenue."),
    "399720": ("Design house in Samsung Foundry's SAFE partner programme. "
               "It designs chips for fabless customers and does not manufacture."),
}

LINKS = [
    # --- tier: disclosure (공시·회사 공식발표·사업보고서 수치) ---
    {"from": "042700", "to": "000660", "tier": "disclosure", "year": 2026,
     "label": "₩44.2bn contract for TC Bonder 4.5 Griffin thermo-compression bonders for HBM4",
     "source": "https://zdnet.co.kr/view/?no=20260608150728"},
    {"from": "240810", "to": "005930", "tier": "disclosure", "year": 2019,
     "label": "₩25.2bn semiconductor manufacturing equipment supply contract",
     "source": "https://www.mt.co.kr/stock/2019/01/04/2019010413492052250"},
    {"from": "067310", "to": "000660", "tier": "disclosure", "year": 2025,
     "label": "OSAT turnkey packaging, test and module assembly; Vietnam plant runs a dedicated line",
     "source": "https://www.thelec.kr/news/articleView.html?idxno=40459"},
    {"from": "005290", "to": "005930", "tier": "disclosure", "year": 2023,
     "label": "Photoresist and semiconductor materials — 37.9% of Dongjin's revenue",
     "source": "https://www.bloter.net/news/articleView.html?idxno=601286"},
    {"from": "005290", "to": "000660", "tier": "disclosure", "year": 2023,
     "label": "Semiconductor materials — 9.9% of Dongjin's revenue; HBM CMP slurry from 2024",
     "source": "https://www.bloter.net/news/articleView.html?idxno=601286"},
    {"from": "247540", "to": "006400", "tier": "disclosure", "year": 2023,
     "label": "₩43.9tn contracted high-nickel NCA cathode supply, 2024–2028",
     "source": "https://ecoprobm.com/sub0701/view/page/1/id/1385"},
    {"from": "247540", "to": "096770", "tier": "disclosure", "year": 2021,
     "label": "₩10.1tn contracted high-nickel NCM cathode supply, deliveries 2024–2026",
     "source": "https://www.asiae.co.kr/article/2021090908174965042"},
    {"from": "066970", "to": "373220", "tier": "disclosure", "year": 2022,
     "label": "₩7.2tn contracted NCMA high-nickel cathode volume agreement for 2023–2024",
     "source": "https://www.hankyung.com/finance/article/2022051976016"},
    {"from": "066970", "to": "006400", "tier": "disclosure", "year": 2026,
     "label": "~₩1.6tn contracted LFP cathode for ESS from 2027, for the Indiana JV",
     "source": "https://www.sedaily.com/article/20023273"},
    {"from": "066970", "to": "096770", "tier": "disclosure", "year": 2024,
     "label": "₩13.2tn contracted high-nickel cathode to 2030 — counterparty is SK On, the unlisted subsidiary",
     "source": "https://dealsite.co.kr/articles/126901"},
    {"from": "003670", "to": "006400", "tier": "disclosure", "year": 2022,
     "label": "₩40tn contracted high-nickel NCA cathode supply, 2023–2032",
     "source": "https://www.poscofuturem.com/pr/view.do?num=658"},
    {"from": "003670", "to": "373220", "tier": "disclosure", "year": 2023,
     "label": "₩30.3tn contracted high-nickel NCM/NCMA cathode supply, 2023–2029",
     "source": "https://www.poscofuturem.com/pr/view.do?num=684"},
    # --- tier: reported (주요 언론이 양사를 명시, 계약 공시는 아님) ---
    {"from": "036930", "to": "000660", "tier": "reported", "year": 2021,
     "label": "Sole-sourced the full order of high-k ALD deposition tools for next-generation DRAM",
     "source": "https://www.thelec.kr/news/articleView.html?idxno=11987"},
    {"from": "357780", "to": "005930", "tier": "reported", "year": 2023,
     "label": "Etchants and cleaning chemicals; sole supplier of the copper-removal CMP slurry used in HBM",
     "source": "https://www.sedaily.com/NewsView/29VWM1ESLV"},
    {"from": "357780", "to": "000660", "tier": "reported", "year": 2023,
     "label": "Etchants and cleaning chemicals; sole supplier of the copper-removal CMP slurry used in HBM",
     "source": "https://www.sedaily.com/NewsView/29VWM1ESLV"},
    {"from": "403870", "to": "005930", "tier": "reported", "year": 2026,
     "label": "High-pressure hydrogen annealing tools, stated on the record in a patent-court filing",
     "source": "https://zdnet.co.kr/view/?no=20260415175505"},
    {"from": "403870", "to": "000660", "tier": "reported", "year": 2026,
     "label": "High-pressure hydrogen annealing tools, stated on the record in a patent-court filing",
     "source": "https://zdnet.co.kr/view/?no=20260415175505"},
    {"from": "039030", "to": "005930", "tier": "reported", "year": 2024,
     "label": "Sole supplier of DRAM laser annealing equipment; laser markers across semiconductor lines",
     "source": "https://www.thelec.kr/news/articleView.html?idxno=25347"},
    {"from": "095340", "to": "005930", "tier": "reported", "year": 2023,
     "label": "Test sockets across memory and non-memory; named as the largest customer",
     "source": "https://news.mtn.co.kr/news-detail/2023071015404074724"},
    {"from": "058470", "to": "005930", "tier": "reported", "year": 2026,
     "label": "Test pins and sockets; named among the company's global customers",
     "source": "https://v.daum.net/v/20260212060542498"},
    {"from": "058470", "to": "000660", "tier": "reported", "year": 2026,
     "label": "Test pins and sockets; named among the company's global customers",
     "source": "https://v.daum.net/v/20260212060542498"},
    {"from": "278280", "to": "373220", "tier": "reported", "year": 2023,
     "label": "Electrolyte salts (LiFSI) and additives; named as a customer",
     "source": "https://dealsite.co.kr/articles/102668"},
    {"from": "278280", "to": "006400", "tier": "reported", "year": 2023,
     "label": "Electrolyte salts (LiFSI) and additives; named as a customer",
     "source": "https://dealsite.co.kr/articles/102668"},
    {"from": "005070", "to": "006400", "tier": "reported", "year": 2023,
     "label": "Cathode material for small-cell and ESS grades; named as a principal customer",
     "source": "https://www.thelec.kr/news/articleView.html?idxno=19516"},
    {"from": "020150", "to": "006400", "tier": "reported", "year": 2024,
     "label": "Copper foil for StarPlus Energy, the Samsung SDI–Stellantis US joint venture",
     "source": "https://www.hankyung.com/article/202408231431i"},
]

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "..", "site", "src", "data", "valuechain.json")


def stage_of(code):
    for stages in STAGES.values():
        for s in stages:
            if code in s["codes"]:
                return s["key"]
    return None


def export_json():
    with open(OUT, "w") as f:
        json.dump({"stages": STAGES, "links": LINKS, "notes": NOTES},
                  f, ensure_ascii=False, indent=1)
    print(f"valuechain OK stages={sum(len(v) for v in STAGES.values())} "
          f"links={len(LINKS)} notes={len(NOTES)}")


if __name__ == "__main__":
    export_json()
