# 애드센스 준비 상태 — chipandcell.com

작성 2026-09-22.

## 광고 코드

게시자 ID 는 `site/.env.local` 의 `PUBLIC_ADSENSE_CLIENT` 하나로 관리한다.
값이 있으면 `src/layouts/Base.astro` 가 전 페이지 `<head>` 에 로더를 넣고,
`src/pages/ads.txt.js` 가 `/ads.txt` 를 만든다. 비어 있으면 둘 다 나오지 않는다.

**Vercel 환경변수에도 같은 값을 넣어야 한다.** 로컬 `.env.local` 은 배포에 안 딸려간다.

```
PUBLIC_ADSENSE_CLIENT=ca-pub-0000000000000000 npx astro build
cat dist/ads.txt
```

## 2026-09-22 에 만든 필수 페이지

`about` 과 `methodology` 밖에 없어서 애드센스 심사에 필요한 것이 빠져 있었다.
새로 만들고 푸터에 전부 연결했다.

| 페이지 | 넣은 이유 |
|---|---|
| `/privacy/` | 애드센스 필수. 구글·파트너의 쿠키 사용, 개인 맞춤 광고 해제 경로(Google Ads Settings·aboutads.info·Your Online Choices) 명시 |
| `/terms/` | 이용 조건, 투자 자문 아님, 자동 수집 데이터의 무보증 |
| `/contact/` | 애드센스가 연락 수단을 본다. 데이터 오류 신고 절차 포함 |
| `/disclaimer/` | 주식 정보 사이트라 별도로 뒀다. 자동 파이프라인이 틀리는 방식(피드 정체·티커 개편·정정 공시), 모델 보조 작성, 대상 기업에서 금전 받지 않음 |

연락처는 `hello@chipandcell.com` 으로 적었다. **이 주소의 포워딩을 아직 만들지
않았다면 먼저 만들어야 한다** — 애드센스가 확인하는 항목이고, 닿지 않는 주소는
없느니만 못하다.

## 사이트맵

`/sitemap.xml` 은 404 가 맞다. Astro 의 sitemap 통합이 `/sitemap-index.xml` 과
`/sitemap-0.xml` 을 만들고 robots.txt 도 그쪽을 가리킨다. 63페이지가 들어 있다.
