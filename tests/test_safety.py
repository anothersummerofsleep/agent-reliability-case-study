from __future__ import annotations

from agent_reliability.safety import detect_safety_critical


def test_positive_active_smoke():
    assert detect_safety_critical(
        "Burning-insulation smell and light smoke near AHU-2's motor starter; unit still running."
    ) is True


def test_positive_active_fire():
    assert detect_safety_critical("There's a fire in the level-2 store room, flames visible.") is True


def test_negated_hazard_list():
    assert detect_safety_critical(
        "Discharge 400 psi, one condenser fan not running. There is no smoke, fire, or burning smell."
    ) is False


def test_resolved_isolated_hazard():
    assert detect_safety_critical(
        "The burning smell earlier has been cleared and the unit is isolated."
    ) is False


def test_plain_incident_no_hazard():
    assert detect_safety_critical("RTU-40 unit 3 tripped NW-A11, discharge 415 psi, coil fouled.") is False


def test_real_hazard_not_falsely_negated():
    # 'no' governs 'cooling', not the later 'smoke'
    assert detect_safety_critical("There is no cooling, but smoke is pouring from the panel.") is True
