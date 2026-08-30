# Chip & Cell (chipandcell.com) — 설계 스펙

날짜: 2026-08-30 · 상태: 사용자 승인 완료(채팅) · 승계: kstockreviewglobal.blogspot.com AdSense 2회 거절("가치 낮은 콘텐츠", 7/31·8/30) 후 전환 결정

## 배경과 목표

기존 영문 블로그는 KR 블로그(kstockreview)의 자동 번역판이었고, YMYL(금융)+자동발행 볼륨+유기 트래픽 0의 조합으로 AdSense에 2회 거절되었다. 이를 폐기 수순(동결)으로 두고, **한국 반도체·배터리 섹터만 파고드는 영어 전문 사이트**로 완전히 새로 출발한다.

- 성공 기준(장기): GSC 색인률 50%+ 및 구글 검색 클릭 실발생 → 그 후에만 AdSense 신청
- 단기 가치: AI 답변엔진 fetcher 유입(기존 블로그에서 검증된 수요) + 니치 전문성

## 정체성

| 항목 | 값 |
|---|---|
| 이름 | Chip & Cell |
| 도메인 | chipandcell.com (2026-08-30 whois 가용 확인, 사용자 구매 예정. 구매 전까지 chipandcell.vercel.app) |
| 태그라인 | Korean Semiconductor & Battery Stocks — Data & Deep Dives |
| 언어 | 영어 단일 |
| 범위 | KOSPI/KOSDAQ 내 반도체·배터리 밸류체인 종목만 |
| 필수 고지 | About/각 페이지 푸터에 "not investment advice" + 데이터 출처·방법론 공개(E-E-A-T) |

## 콘텐츠 구조 (3층)

1. **데이터 페이지(자동 갱신, 고정 URL)** — 차별화 핵심. 종목별 페이지 27개 + 섹터 대시보드 2개(반도체/배터리) + 시장 개요 1개(KOSPI/KOSDAQ). 스크리너 EOD 데이터로 매일 값만 갱신, URL 고정(신규 URL 양산 없음 = scaled-content 패턴 회피). 내용: 주가·등락, 외인/기관 수급, 52주 위치, 섹터 상대성과, 기본 밸류에이션.
2. **심층 글(일 1건)** — 기존 blog_stock_deep 구조(핵심수치 표 → 주가 → 수급 → 글로벌 맥락 → LLM 심층해설 → 면책)를 영어로 확장. 커버리지 종목 로테이션 + 급등락/실적 이벤트 우선.
3. **주간 섹터 리뷰(주 1건)** — 반도체·배터리 주간 종합.

발행량 = 주 ~8건 (기존 일 5건 대비 대폭 감축). 신선도는 데이터 페이지가 담당.

## 커버리지 종목 (27)

- **반도체 15**: 삼성전자(005930), SK하이닉스(000660), 한미반도체(042700), HPSP(403870), 이오테크닉스(039030), 리노공업(058470), 원익IPS(240810), 주성엔지니어링(036930), DB하이텍(000990), 솔브레인(357780), 동진쎄미켐(005290), 티씨케이(064760), 하나마이크론(067310), ISC(095340), 가온칩스(399720)
- **배터리 12**: LG에너지솔루션(373220), 삼성SDI(006400), SK이노베이션(096770), 에코프로비엠(247540), 에코프로(086520), 포스코퓨처엠(003670), 엘앤에프(066970), 코스모신소재(005070), SKC(011790), 롯데에너지머티리얼즈(020150), 나노신소재(121600), 천보(278280)

종목코드는 구현 시 스크리너 데이터로 전수 검증한다(추정 금지 원칙).

## 아키텍처

- **리포**: `chipandcell` (GitHub, kstockreview와 완전 분리). 개발은 에어 `~/chipandcell`, 미니에 클론(파이프라인 실행지).
- **사이트**: Astro 정적 사이트(lifelaw `~/kr-legal-tools/site` 패턴 재사용), Vercel 배포.
- **파이프라인(미니)**: kr-screener 데이터 **읽기 전용** 사용.
  - `pipeline/export_data.py` → `site/src/data/*.json` (데이터 페이지 재료)
  - `pipeline/gen_deep_dive.py` → `site/src/content/posts/*.md` (심층 글, LLM=Gemini 소량+Ollama 폴백 — 구현 시 확정)
  - astro build → vercel deploy
- **launchd(미니) 일 1회**: 장 마감 EOD 적재·17:40 스냅샷 이후인 **18:10**. 배포 로그 전체 보존(/dev/null 은폐 금지), 실패 시 로그 기록만(블로그 건 텔레그램 발송 금지 규칙 준수).
- **git 규칙**: Vercel 연동 리포이므로 커밋 author = github noreply(udtman74) 고정.

## 구 블로그 동결

- 미니 kr-screener에서 EN 잔존 발행 3종(blog_daily_deep, blog_stock_deep, blog_sector_story)의 EN 발행 차단(`publish_english=False` 또는 동등 처리) → 커밋 + 스케줄러 즉시 재시작.
- KR 블로그 발행은 전량 유지(변경 없음).
- 구 EN 블로그 상단에 새 사이트 안내 배너 1개 추가.
- 기존 80건은 아카이브로 보존(fetcher 유입 유지).

## 단계

1. **Phase 1**: 리포+Astro 뼈대+데이터 페이지 30개+About/Methodology → Vercel 라이브(chipandcell.vercel.app)
2. **Phase 2**: 심층 글 파이프라인(일 1건)+주간 리뷰+launchd+구 블로그 동결
3. **Phase 3**: 유통 — 도메인 연결 후 GSC/Bing 등록, sitemap+IndexNow, (선택) Bluesky/Mastodon 스포트라이트(utiltools 패턴)
4. **AdSense**: 색인·검색 클릭 지표 확인 후에만 신청(수개월 뒤)

## 사용자 몫

- chipandcell.com 구매 + Vercel DNS 연결
- (한참 뒤) AdSense 신청 시점 결정

## 결정 로그

- 플랫폼: Vercel 새 정적 사이트 (Blogger 리브랜딩·커스텀도메인 안 기각, 사용자 선택)
- 구 블로그: 동결 (병행 유지·점진 폐쇄 기각)
- 콘텐츠 모델: 데이터+심층 하이브리드 (순수 저비용 블로그·현행 볼륨 유지 기각)
- 이름: Chip & Cell — chipandcell.com (KChipCell·Chips & Cells·KorSemi 기각)
