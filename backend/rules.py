def parse_hhmm(text: str) -> int:
    """'HH:MM' -> 当天分钟数，非法输入抛 ValueError。"""
    parts = (text or "").strip().split(":")
    if len(parts) != 2:
        raise ValueError("时间格式须为 HH:MM")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError("时间格式须为 HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("时间超出 00:00 到 23:59 范围")
    return hour * 60 + minute


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def in_curfew(start_min: int, end_min: int, now_min: int) -> bool:
    """闭区间判定；start > end 视为跨零点窗口（如 22:00 到次日 06:00）。"""
    if start_min <= end_min:
        return start_min <= now_min <= end_min
    return now_min >= start_min or now_min <= end_min


def judge(doc: dict) -> tuple[str, str]:
    steps = doc.get("steps") or []
    fry = next((s for s in steps if s.get("name") == "清炒"), None)
    if fry is None:
        return "未放行", "缺少清炒工序"
    temp = float(fry.get("temp_c", 0))
    minutes = float(fry.get("minutes", 0))
    if not 80 <= temp <= 150:
        return "未放行", "清炒温度不在范围内"
    if not 5 <= minutes <= 30:
        return "未放行", "清炒时长不在范围内"
    return "放行", "清炒工序符合炮制要求"
