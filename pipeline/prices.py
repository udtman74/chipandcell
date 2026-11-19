"""가격 시세 접근 단일 창구.

FinanceDataReader는 배치 머신(미니)에만 설치되어 있다. 이 모듈은 import 시점이 아니라
호출 시점에 지연 로드하고, 테스트에서는 `set_reader()`로 대체 구현을 주입한다.
(모듈 최상단에서 fdr을 import 하면 배치가 아닌 환경에서 테스트·점검이 아예 불가능해진다.)
"""


class PriceSourceUnavailable(RuntimeError):
    """가격 소스(fdr)가 없거나 빈 응답을 돌려줬다."""


_READER = None


def set_reader(fn):
    """테스트용 대체 리더 주입. fn(symbol) -> DataFrame(OHLCV). None이면 기본 fdr."""
    global _READER
    _READER = fn


def _default_reader():
    import FinanceDataReader as fdr
    return fdr.DataReader


def read(symbol):
    """지수/종목 일봉(OHLCV)을 읽는다. 실패는 예외로 드러낸다(조용한 빈 값 금지)."""
    fn = _READER
    if fn is None:
        try:
            fn = _default_reader()
        except ImportError as e:                     # 미니가 아닌 머신
            raise PriceSourceUnavailable(f"FinanceDataReader unavailable: {e}") from e
    df = fn(symbol)
    if df is None or len(df) == 0:
        raise PriceSourceUnavailable(f"empty price frame for {symbol}")
    return df
