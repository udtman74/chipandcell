"""Chip & Cell 커버리지 종목 SSOT. (code, name_en, name_kr, sector)"""
SEMI = [
    ("005930", "Samsung Electronics", "삼성전자"),
    ("000660", "SK Hynix", "SK하이닉스"),
    ("042700", "Hanmi Semiconductor", "한미반도체"),
    ("403870", "HPSP", "HPSP"),
    ("039030", "EO Technics", "이오테크닉스"),
    ("058470", "Leeno Industrial", "리노공업"),
    ("240810", "Wonik IPS", "원익IPS"),
    ("036930", "Jusung Engineering", "주성엔지니어링"),
    ("000990", "DB HiTek", "DB하이텍"),
    ("357780", "Soulbrain", "솔브레인"),
    ("005290", "Dongjin Semichem", "동진쎄미켐"),
    ("064760", "TCK", "티씨케이"),
    ("067310", "Hana Micron", "하나마이크론"),
    ("095340", "ISC", "ISC"),
    ("399720", "Gaonchips", "가온칩스"),
]
BATT = [
    ("373220", "LG Energy Solution", "LG에너지솔루션"),
    ("006400", "Samsung SDI", "삼성SDI"),
    ("096770", "SK Innovation", "SK이노베이션"),
    ("247540", "EcoPro BM", "에코프로비엠"),
    ("086520", "EcoPro", "에코프로"),
    ("003670", "POSCO Future M", "포스코퓨처엠"),
    ("066970", "L&F", "엘앤에프"),
    ("005070", "Cosmo AM&T", "코스모신소재"),
    ("011790", "SKC", "SKC"),
    ("020150", "Lotte Energy Materials", "롯데에너지머티리얼즈"),
    ("121600", "Nano Materials", "나노신소재"),
    ("278280", "Chunbo", "천보"),
]
TICKERS = [(c, en, kr, "semiconductor") for c, en, kr in SEMI] + \
          [(c, en, kr, "battery") for c, en, kr in BATT]
SECTOR_LABELS = {"semiconductor": "Semiconductor", "battery": "Battery"}
