"""夜间禁写窗：每日禁写时间段的判定逻辑（纯函数，不依赖框架，便于单测）。

时间段以 "HH:MM" 表示，按当日分钟数比较。闭区间：起点与终点所在分钟都算禁写。
start > end 视为跨夜窗口（如 22:00~06:00）；start == end 仅覆盖那一分钟。
"""


def parse_hhmm(text: str) -> int:
    """"HH:MM" 解析为当日分钟数（0~1439），非法输入抛 ValueError。"""
    if not isinstance(text, str):
        raise ValueError("时间格式须为 HH:MM")
    parts = text.strip().split(":")
    if len(parts) != 2:
        raise ValueError("时间格式须为 HH:MM")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError("时间格式须为 HH:MM") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("时间超出当天范围（00:00~23:59）")
    return hour * 60 + minute


def fmt_hhmm(minutes: int) -> str:
    """当日分钟数格式化为 "HH:MM"。"""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def in_window(start_min: int, end_min: int, now_min: int) -> bool:
    """判断 now_min 是否落在每日禁写闭区间 [start_min, end_min] 内。"""
    if start_min <= end_min:
        return start_min <= now_min <= end_min
    return now_min >= start_min or now_min <= end_min
