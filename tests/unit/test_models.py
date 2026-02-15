from src.core.models import SignalDirection, SignalStatus


def test_signal_direction_values():
    assert SignalDirection.LONG == "long"
    assert SignalDirection.SHORT == "short"
    assert SignalDirection.NEUTRAL == "neutral"


def test_signal_status_values():
    assert SignalStatus.NEW == "new"
    assert SignalStatus.ACTIVE == "active"
    assert SignalStatus.HIT_TP == "hit_tp"
    assert SignalStatus.HIT_SL == "hit_sl"
