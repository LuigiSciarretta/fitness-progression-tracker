"""Progression Engine — Deterministic rule-based system for workout progression.

Analyzes workout history per exercise and generates actionable suggestions:
- Progressive overload (weight/rep increases)
- Plateau detection
- Fatigue/deload management
- Comeback after inactivity

Every suggestion is saved with full context for future ML training.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

import database as db


# ─── Types ───────────────────────────────────────────────────────────────────

class SuggestionType(str, Enum):
    INCREASE_WEIGHT = "increase_weight"
    INCREASE_REPS = "increase_reps"
    MAINTAIN = "maintain"
    DELOAD = "deload"
    PLATEAU_CHANGE = "plateau_change"
    COMEBACK = "comeback"
    NO_DATA = "no_data"


# Mapping human-readable labels & icons
SUGGESTION_DISPLAY = {
    SuggestionType.INCREASE_WEIGHT: ("⬆️ Aumenta peso", "success"),
    SuggestionType.INCREASE_REPS:   ("🔄 Aumenta ripetizioni", "info"),
    SuggestionType.MAINTAIN:        ("✊ Mantieni", "info"),
    SuggestionType.DELOAD:          ("😴 Deload consigliato", "warning"),
    SuggestionType.PLATEAU_CHANGE:  ("🧱 Plateau rilevato", "warning"),
    SuggestionType.COMEBACK:        ("🔙 Ripresa graduale", "info"),
    SuggestionType.NO_DATA:         ("📭 Dati insufficienti", "info"),
}


@dataclass
class Suggestion:
    """A single progression suggestion with full context."""
    type: SuggestionType
    suggested_weight_kg: float | None
    suggested_reps_target: int | None
    reasoning: str
    # Context snapshot
    current_weight: float
    current_avg_reps: float
    current_volume: float
    sessions_analyzed: int


@dataclass
class ExerciseTarget:
    """Rep range and progression parameters for an exercise."""
    target_sets: int = 3
    target_reps_min: int = 8
    target_reps_max: int = 12
    progression_step_kg: float = 2.5


DEFAULT_TARGET = ExerciseTarget()


# ─── Analysis helpers ────────────────────────────────────────────────────────

def _is_plateau(sessions: list[dict], tolerance_kg: float = 0.5,
                tolerance_reps: int = 1, window: int = 3) -> bool:
    """Detect plateau: same weight ± tolerance AND same avg reps ± tolerance
    for `window` consecutive sessions."""
    if len(sessions) < window:
        return False

    recent = sessions[:window]  # already sorted desc
    base_weight = recent[0]["max_weight"]
    base_reps = recent[0]["avg_reps"]

    return all(
        abs(s["max_weight"] - base_weight) <= tolerance_kg
        and abs(s["avg_reps"] - base_reps) <= tolerance_reps
        for s in recent[1:]
    )


def _is_declining(sessions: list[dict], window: int = 2) -> bool:
    """Detect performance decline: both weight AND reps trending down
    over `window` consecutive sessions (most recent first)."""
    if len(sessions) < window + 1:
        return False

    recent = sessions[:window + 1]
    for i in range(len(recent) - 1):
        newer, older = recent[i], recent[i + 1]
        # At least one of weight/reps must decline, and neither improves
        weight_dropped = newer["max_weight"] < older["max_weight"]
        reps_dropped = newer["avg_reps"] < older["avg_reps"]
        weight_same_or_down = newer["max_weight"] <= older["max_weight"]
        reps_same_or_down = newer["avg_reps"] <= older["avg_reps"]

        if not ((weight_dropped or reps_dropped) and weight_same_or_down and reps_same_or_down):
            return False
    return True


def _days_since_last_session(sessions: list[dict]) -> int | None:
    """Days since the most recent session, or None if no sessions."""
    if not sessions:
        return None
    last_date = sessions[0]["workout_date"]
    if isinstance(last_date, str):
        last_date = date.fromisoformat(last_date)
    return (date.today() - last_date).days


def _needs_deload_from_volume(sessions: list[dict],
                              weeks_threshold: int = 4) -> bool:
    """Heuristic: if volume has been consistently high (no deload) for
    a long stretch, suggest proactive deload."""
    if len(sessions) < weeks_threshold:
        return False

    recent = sessions[:weeks_threshold]
    # Check that sessions span at least `weeks_threshold` weeks
    dates = [s["workout_date"] for s in recent]
    if isinstance(dates[0], str):
        dates = [date.fromisoformat(d) for d in dates]
    span_days = (dates[0] - dates[-1]).days
    if span_days < (weeks_threshold - 1) * 7:
        return False

    # If no session had notably lower volume (deload), flag it
    volumes = [s["total_volume"] for s in recent]
    avg_vol = sum(volumes) / len(volumes)
    # A deload session would typically be <70% of average
    has_deload = any(v < avg_vol * 0.7 for v in volumes)
    return not has_deload


def _all_sets_at_target_max(session: dict, target: ExerciseTarget) -> bool:
    """Check if all sets in the most recent session hit target_reps_max."""
    reps_list = session.get("reps_list", [])
    if not reps_list:
        return False
    return all(r >= target.target_reps_max for r in reps_list)


def _all_sets_in_range(session: dict, target: ExerciseTarget) -> bool:
    """Check if all sets are within the target rep range."""
    reps_list = session.get("reps_list", [])
    if not reps_list:
        return False
    return all(target.target_reps_min <= r <= target.target_reps_max for r in reps_list)


def _some_sets_below_min(session: dict, target: ExerciseTarget) -> bool:
    """Check if any set fell below the minimum rep target."""
    reps_list = session.get("reps_list", [])
    if not reps_list:
        return False
    return any(r < target.target_reps_min for r in reps_list)


# ─── Core engine ─────────────────────────────────────────────────────────────

def analyze_exercise(user_id: int, exercise_id: int,
                     save: bool = True) -> Suggestion:
    """Run the progression engine for a single exercise.

    Priority order of rules:
    1. No data / insufficient data
    2. Comeback after inactivity (>14 days)
    3. Fatigue / declining performance → deload
    4. Volume overload without deload → proactive deload
    5. Plateau detection → change scheme
    6. All sets at rep max → increase weight
    7. All sets in range → increase reps
    8. Some sets below min → maintain / consolidate
    """

    sessions = db.get_recent_sessions(user_id, exercise_id, limit=8)

    # Load target or use defaults
    target_row = db.get_exercise_target(user_id, exercise_id)
    if target_row:
        target = ExerciseTarget(
            target_sets=target_row["target_sets"],
            target_reps_min=target_row["target_reps_min"],
            target_reps_max=target_row["target_reps_max"],
            progression_step_kg=target_row["progression_step_kg"],
        )
    else:
        target = DEFAULT_TARGET

    # ── Rule 1: No data ──
    if not sessions:
        return Suggestion(
            type=SuggestionType.NO_DATA,
            suggested_weight_kg=None,
            suggested_reps_target=target.target_reps_min,
            reasoning="Nessun dato disponibile per questo esercizio. "
                      "Registra almeno un allenamento per ricevere suggerimenti.",
            current_weight=0, current_avg_reps=0, current_volume=0,
            sessions_analyzed=0,
        )

    latest = sessions[0]
    current_weight = latest["max_weight"]
    current_avg_reps = float(latest["avg_reps"])
    current_volume = float(latest["total_volume"])
    n_sessions = len(sessions)

    def _make(stype: SuggestionType, weight: float | None,
              reps: int | None, reason: str) -> Suggestion:
        s = Suggestion(
            type=stype,
            suggested_weight_kg=weight,
            suggested_reps_target=reps,
            reasoning=reason,
            current_weight=current_weight,
            current_avg_reps=current_avg_reps,
            current_volume=current_volume,
            sessions_analyzed=n_sessions,
        )
        if save:
            db.save_progression_suggestion(
                user_id=user_id, exercise_id=exercise_id,
                context_last_sessions=n_sessions,
                context_current_weight=current_weight,
                context_current_avg_reps=current_avg_reps,
                context_current_volume=current_volume,
                suggestion_type=stype.value,
                suggested_weight_kg=weight,
                suggested_reps_target=reps,
                reasoning=reason,
            )
        return s

    # ── Rule 2: Comeback after inactivity ──
    days_off = _days_since_last_session(sessions)
    if days_off is not None and days_off > 14:
        comeback_weight = round(current_weight * 0.8 * 2) / 2  # round to 0.5
        return _make(
            SuggestionType.COMEBACK,
            comeback_weight,
            target.target_reps_min,
            f"Sono passati {days_off} giorni dall'ultimo allenamento di questo esercizio. "
            f"Riparti con -20% del peso ({comeback_weight:.1f} kg) per "
            f"riscaldarti e ridurre il rischio infortuni. "
            f"Obiettivo: {target.target_reps_min} reps per ricostruire il pattern motorio.",
        )

    # ── Rule 3: Declining performance → deload ──
    if _is_declining(sessions):
        deload_weight = round(current_weight * 0.9 * 2) / 2
        return _make(
            SuggestionType.DELOAD,
            deload_weight,
            target.target_reps_min,
            f"Performance in calo nelle ultime sessioni: peso o ripetizioni "
            f"in diminuzione. Deload consigliato: riduci a {deload_weight:.1f} kg "
            f"(-10%) con {target.target_reps_min} reps. "
            f"Questo permette al sistema nervoso di recuperare "
            f"e preparare il prossimo ciclo di progressione.",
        )

    # ── Rule 4: Proactive deload (volume overload) ──
    if _needs_deload_from_volume(sessions, weeks_threshold=4):
        deload_weight = round(current_weight * 0.9 * 2) / 2
        return _make(
            SuggestionType.DELOAD,
            deload_weight,
            target.target_reps_min,
            f"Volume elevato costante per 4+ settimane senza scarico. "
            f"Settimana di deload consigliata: {deload_weight:.1f} kg (-10%), "
            f"riduci il numero di serie a {max(1, target.target_sets - 1)}. "
            f"Il deload proattivo previene plateau e overtraining.",
        )

    # ── Rule 5: Plateau detection ──
    if n_sessions >= 3 and _is_plateau(sessions):
        bump_weight = round((current_weight + target.progression_step_kg) * 2) / 2
        return _make(
            SuggestionType.PLATEAU_CHANGE,
            bump_weight,
            target.target_reps_min,
            f"Plateau rilevato: stesso peso ({current_weight:.1f} kg) e "
            f"ripetizioni simili per 3+ sessioni consecutive. "
            f"Opzioni: (1) Micro-aumento a {bump_weight:.1f} kg con "
            f"{target.target_reps_min} reps, (2) Cambia schema di ripetizioni "
            f"(es. 5x5 se eri su 3x10), (3) Variante dell'esercizio. "
            f"Il cambio di stimolo rompe l'adattamento.",
        )

    # ── Rule 6: Progressive overload — all sets at max reps ──
    if _all_sets_at_target_max(latest, target):
        new_weight = round((current_weight + target.progression_step_kg) * 2) / 2
        return _make(
            SuggestionType.INCREASE_WEIGHT,
            new_weight,
            target.target_reps_min,
            f"Tutte le serie hanno raggiunto {target.target_reps_max} reps a "
            f"{current_weight:.1f} kg — ottimo lavoro! "
            f"Aumenta a {new_weight:.1f} kg (+{target.progression_step_kg} kg) "
            f"e ripeti da {target.target_reps_min} reps. "
            f"Questa è la progressione lineare classica (double progression).",
        )

    # ── Rule 7: In range but not at max — push reps ──
    if _all_sets_in_range(latest, target):
        return _make(
            SuggestionType.INCREASE_REPS,
            current_weight,
            min(int(current_avg_reps) + 1, target.target_reps_max),
            f"Tutte le serie sono nel range ({target.target_reps_min}-"
            f"{target.target_reps_max}) ma non ancora al massimo. "
            f"Mantieni {current_weight:.1f} kg e punta a +1 rep per serie. "
            f"Quando raggiungi {target.target_reps_max} su tutte le serie, "
            f"sarà il momento di aumentare il peso.",
        )

    # ── Rule 8: Some sets below minimum — consolidate ──
    if _some_sets_below_min(latest, target):
        return _make(
            SuggestionType.MAINTAIN,
            current_weight,
            target.target_reps_min,
            f"Alcune serie sotto il target minimo di {target.target_reps_min} reps. "
            f"Mantieni {current_weight:.1f} kg e lavora per portare tutte le "
            f"serie almeno a {target.target_reps_min} reps prima di progredire. "
            f"Concentrati sulla tecnica e il tempo sotto tensione.",
        )

    # ── Fallback: maintain ──
    return _make(
        SuggestionType.MAINTAIN,
        current_weight,
        target.target_reps_min,
        f"Continua con {current_weight:.1f} kg. Punta a completare tutte le "
        f"serie nel range {target.target_reps_min}-{target.target_reps_max} reps.",
    )


# ─── Batch analysis ─────────────────────────────────────────────────────────

def analyze_all_exercises(user_id: int,
                          save: bool = True) -> list[tuple[dict, Suggestion]]:
    """Run the engine on all exercises that have targets configured.
    Returns list of (exercise_dict, suggestion) tuples."""
    targets = db.get_all_exercise_targets(user_id)
    results = []
    for t in targets:
        suggestion = analyze_exercise(user_id, t["exercise_id"], save=save)
        exercise_info = {
            "id": t["exercise_id"],
            "name": t["exercise_name"],
            "category": t["category"],
        }
        results.append((exercise_info, suggestion))
    return results


def get_exercise_suggestion_for_workout(user_id: int,
                                        exercise_id: int) -> Suggestion | None:
    """Quick suggestion for the workout logging page. Does NOT save to DB
    (to avoid duplicates — only the dashboard save is authoritative)."""
    target_row = db.get_exercise_target(user_id, exercise_id)
    if not target_row:
        return None
    return analyze_exercise(user_id, exercise_id, save=False)


# ─── Feedback loop: match outcomes to suggestions ────────────────────────────

def record_outcome_for_exercise(user_id: int, exercise_id: int,
                                actual_weight: float, actual_avg_reps: float,
                                workout_date: date):
    """After logging a workout, check if there's a pending suggestion
    and record whether the user followed it."""
    latest = db.get_latest_suggestion(user_id, exercise_id)
    if not latest or latest.get("outcome_accepted") is not None:
        return  # no pending suggestion

    # Determine if the user followed the suggestion
    suggested_w = latest.get("suggested_weight_kg")
    if suggested_w is not None:
        weight_tolerance = 1.0  # kg
        accepted = abs(actual_weight - suggested_w) <= weight_tolerance
    else:
        accepted = True  # no weight suggestion, count as accepted

    db.update_progression_outcome(
        log_id=latest["id"],
        accepted=accepted,
        actual_weight=actual_weight,
        actual_avg_reps=actual_avg_reps,
        outcome_date=workout_date,
    )
