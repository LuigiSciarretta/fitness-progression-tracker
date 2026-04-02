from datetime import date, timedelta

import progression_engine as pe


def _session(days_ago: int, max_weight: float, avg_reps: float, total_volume: float, reps_list: list[int]):
    """Build a synthetic aggregated session row used by progression tests."""
    return {
        "workout_date": date.today() - timedelta(days=days_ago),
        "max_weight": max_weight,
        "avg_reps": avg_reps,
        "total_volume": total_volume,
        "reps_list": reps_list,
    }


def test_no_data_returns_no_data(monkeypatch):
    """Engine should return NO_DATA when no training history exists."""
    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: [])
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: None)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=False)

    assert suggestion.type == pe.SuggestionType.NO_DATA
    assert suggestion.suggested_weight_kg is None
    assert suggestion.suggested_reps_target == pe.DEFAULT_TARGET.target_reps_min


def test_comeback_after_more_than_14_days(monkeypatch):
    """Inactivity over 14 days should trigger a comeback recommendation."""
    sessions = [_session(21, 60.0, 10.0, 1800.0, [10, 10, 10])]

    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: sessions)
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: None)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=False)

    assert suggestion.type == pe.SuggestionType.COMEBACK
    assert suggestion.suggested_weight_kg == 48.0


def test_declining_performance_suggests_deload(monkeypatch):
    """A downtrend in performance should suggest a deload."""
    sessions = [
        _session(0, 57.5, 8.0, 1380.0, [8, 8, 8]),
        _session(7, 60.0, 9.0, 1620.0, [9, 9, 9]),
        _session(14, 62.5, 10.0, 1875.0, [10, 10, 10]),
    ]

    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: sessions)
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: None)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=False)

    assert suggestion.type == pe.SuggestionType.DELOAD
    assert suggestion.suggested_weight_kg == 52.0


def test_plateau_has_priority_over_weight_increase(monkeypatch):
    """Plateau rule should fire before plain weight increase when both apply."""
    sessions = [
        _session(0, 60.0, 12.0, 2160.0, [12, 12, 12]),
        _session(7, 60.0, 12.0, 2160.0, [12, 12, 12]),
        _session(14, 60.0, 12.0, 2160.0, [12, 12, 12]),
    ]

    target = {
        "target_sets": 3,
        "target_reps_min": 8,
        "target_reps_max": 12,
        "progression_step_kg": 2.5,
    }

    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: sessions)
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: target)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=False)

    assert suggestion.type == pe.SuggestionType.PLATEAU_CHANGE
    assert suggestion.suggested_weight_kg == 62.5


def test_all_sets_at_target_max_increases_weight(monkeypatch):
    """When all sets hit rep ceiling, engine should increase weight."""
    sessions = [_session(0, 60.0, 12.0, 2160.0, [12, 12, 12])]
    target = {
        "target_sets": 3,
        "target_reps_min": 8,
        "target_reps_max": 12,
        "progression_step_kg": 2.5,
    }

    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: sessions)
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: target)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=False)

    assert suggestion.type == pe.SuggestionType.INCREASE_WEIGHT
    assert suggestion.suggested_weight_kg == 62.5
    assert suggestion.suggested_reps_target == 8


def test_sets_in_range_increases_reps(monkeypatch):
    """If sets are in range but below cap, engine should push reps first."""
    sessions = [_session(0, 60.0, 9.0, 1620.0, [8, 9, 10])]
    target = {
        "target_sets": 3,
        "target_reps_min": 8,
        "target_reps_max": 12,
        "progression_step_kg": 2.5,
    }

    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: sessions)
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: target)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=False)

    assert suggestion.type == pe.SuggestionType.INCREASE_REPS
    assert suggestion.suggested_weight_kg == 60.0
    assert suggestion.suggested_reps_target == 10


def test_below_min_reps_maintains_weight(monkeypatch):
    """Any set below minimum reps should keep the same weight."""
    sessions = [_session(0, 60.0, 7.0, 1260.0, [7, 7, 7])]
    target = {
        "target_sets": 3,
        "target_reps_min": 8,
        "target_reps_max": 12,
        "progression_step_kg": 2.5,
    }

    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: sessions)
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: target)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=False)

    assert suggestion.type == pe.SuggestionType.MAINTAIN
    assert suggestion.suggested_weight_kg == 60.0


def test_save_true_persists_suggestion(monkeypatch):
    """With save=True, engine should persist decision context to storage."""
    sessions = [_session(0, 60.0, 9.0, 1620.0, [8, 9, 10])]
    target = {
        "target_sets": 3,
        "target_reps_min": 8,
        "target_reps_max": 12,
        "progression_step_kg": 2.5,
    }
    called = {}

    monkeypatch.setattr(pe.db, "get_recent_sessions", lambda user_id, exercise_id, limit=8: sessions)
    monkeypatch.setattr(pe.db, "get_exercise_target", lambda user_id, exercise_id: target)

    def _save_progression_suggestion(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(pe.db, "save_progression_suggestion", _save_progression_suggestion)

    suggestion = pe.analyze_exercise(user_id=1, exercise_id=10, save=True)

    assert suggestion.type == pe.SuggestionType.INCREASE_REPS
    assert called["user_id"] == 1
    assert called["exercise_id"] == 10
    assert called["suggestion_type"] == pe.SuggestionType.INCREASE_REPS.value
