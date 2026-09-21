// 애드센스 ads.txt — PUBLIC_ADSENSE_CLIENT(ca-pub-…)에서 게시자 번호를 뽑아 쓴다.
// 값이 없으면 빈 파일 대신 404 를 내서, 설정을 빠뜨린 걸 바로 알아채게 한다.
export function GET() {
  const client = import.meta.env.PUBLIC_ADSENSE_CLIENT ?? "";
  const pub = client.replace(/^ca-/, "").trim();
  if (!/^pub-\d+$/.test(pub)) {
    return new Response("PUBLIC_ADSENSE_CLIENT not set", { status: 404 });
  }
  return new Response(`google.com, ${pub}, DIRECT, f08c47fec0942fa0\n`, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
