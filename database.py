"""Database module for the Fitness Tracker multi-user application (PostgreSQL)."""

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
import streamlit as st
from datetime import date
from contextlib import contextmanager
from threading import Lock


_POOL_LOCK = Lock()
_POOLS: dict[str, SimpleConnectionPool] = {}


def _get_db_url() -> str:
    """Read the database URL from Streamlit secrets."""
    return st.secrets["database"]["url"]


def _get_pool() -> SimpleConnectionPool:
    """Get or create a connection pool for the configured DB URL."""
    db_url = _get_db_url()
    with _POOL_LOCK:
        pool = _POOLS.get(db_url)
        if pool is None:
            # Keep the pool conservative for hosted free-tier environments.
            pool = SimpleConnectionPool(minconn=1, maxconn=8, dsn=db_url)
            _POOLS[db_url] = pool
    return pool


@contextmanager
def get_connection():
    """Context manager for database connections."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _fetchall(conn, query: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def _fetchone(conn, query: str, params: tuple = ()) -> dict | None:
    """Execute a query and return one row as dict."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _execute(conn, query: str, params: tuple = ()):
    """Execute a query without returning rows."""
    with conn.cursor() as cur:
        cur.execute(query, params)


# ─── Schema ──────────────────────────────────────────────────────────────────

def init_db():
    """Initialize the database schema."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS exercises (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (user_id, name)
                );

                CREATE TABLE IF NOT EXISTS workout_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    exercise_id INTEGER NOT NULL REFERENCES exercises(id),
                    workout_date DATE NOT NULL,
                    set_number INTEGER NOT NULL,
                    reps INTEGER NOT NULL,
                    weight_kg REAL NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_workout_user
                    ON workout_logs(user_id);
                CREATE INDEX IF NOT EXISTS idx_workout_date
                    ON workout_logs(user_id, workout_date);
                CREATE INDEX IF NOT EXISTS idx_workout_exercise
                    ON workout_logs(user_id, exercise_id);

                -- ═══ Progression Engine tables ═══

                CREATE TABLE IF NOT EXISTS exercise_targets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                    target_sets INTEGER NOT NULL DEFAULT 3,
                    target_reps_min INTEGER NOT NULL DEFAULT 8,
                    target_reps_max INTEGER NOT NULL DEFAULT 12,
                    progression_step_kg REAL NOT NULL DEFAULT 2.5,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(user_id, exercise_id)
                );

                CREATE TABLE IF NOT EXISTS progression_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                    generated_at TIMESTAMPTZ DEFAULT NOW(),
                    context_last_sessions INTEGER NOT NULL,
                    context_current_weight REAL NOT NULL,
                    context_current_avg_reps REAL NOT NULL,
                    context_current_volume REAL NOT NULL,
                    suggestion_type TEXT NOT NULL,
                    suggested_weight_kg REAL,
                    suggested_reps_target INTEGER,
                    reasoning TEXT NOT NULL,
                    outcome_accepted BOOLEAN,
                    outcome_actual_weight REAL,
                    outcome_actual_avg_reps REAL,
                    outcome_date DATE
                );

                CREATE INDEX IF NOT EXISTS idx_progression_user_exercise
                    ON progression_log(user_id, exercise_id);
                CREATE INDEX IF NOT EXISTS idx_progression_generated
                    ON progression_log(user_id, generated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_targets_user_exercise
                    ON exercise_targets(user_id, exercise_id);
            """)


# ─── User CRUD ───────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> dict | None:
    """Return a user row by username."""
    with get_connection() as conn:
        return _fetchone(conn, "SELECT * FROM users WHERE username = %s", (username,))


def create_user(username: str, name: str, password_hash: str) -> int:
    """Create a new user. Returns the new user id."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, name, password_hash) VALUES (%s, %s, %s) RETURNING id",
                (username.strip().lower(), name.strip(), password_hash),
            )
            return cur.fetchone()[0]


def get_all_users() -> list[dict]:
    """Return all users (for building the authenticator config)."""
    with get_connection() as conn:
        return _fetchall(conn, "SELECT id, username, name, password_hash FROM users ORDER BY username")


def update_user_password(username: str, new_password_hash: str):
    """Update a user's password hash."""
    with get_connection() as conn:
        _execute(conn, "UPDATE users SET password_hash = %s WHERE username = %s",
                 (new_password_hash, username))


# ─── Exercise CRUD ───────────────────────────────────────────────────────────

def get_all_exercises(user_id: int) -> list[dict]:
    """Return all exercises for a specific user, ordered by category and name."""
    with get_connection() as conn:
        return _fetchall(conn, "SELECT * FROM exercises WHERE user_id = %s ORDER BY category, name", (user_id,))


def get_exercises_by_category(user_id: int) -> dict:
    """Return exercises grouped by category for a specific user."""
    exercises = get_all_exercises(user_id)
    grouped: dict[str, list] = {}
    for ex in exercises:
        grouped.setdefault(ex["category"], []).append(ex)
    return grouped


def add_exercise(name: str, category: str, user_id: int) -> int:
    """Add a new exercise for a specific user. Returns the new exercise id."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO exercises (user_id, name, category) VALUES (%s, %s, %s) RETURNING id",
                (user_id, name.strip(), category.strip()),
            )
            return cur.fetchone()[0]


def delete_exercise(exercise_id: int, user_id: int):
    """Delete an exercise and all its logs (only if owned by user)."""
    with get_connection() as conn:
        _execute(conn, "DELETE FROM workout_logs WHERE exercise_id = %s AND user_id = %s", (exercise_id, user_id))
        _execute(conn, "DELETE FROM exercises WHERE id = %s AND user_id = %s", (exercise_id, user_id))


# ─── Workout Logs CRUD (all user-scoped) ─────────────────────────────────────

def log_set(user_id: int, exercise_id: int, workout_date: date,
            set_number: int, reps: int, weight_kg: float, notes: str = "") -> int:
    """Log a single set for a user. Returns the log id."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workout_logs
                   (user_id, exercise_id, workout_date, set_number, reps, weight_kg, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (user_id, exercise_id, workout_date.isoformat(), set_number, reps, weight_kg, notes),
            )
            return cur.fetchone()[0]


def get_logs_for_date(user_id: int, workout_date: date) -> list[dict]:
    """Return all logs for a specific user and date."""
    with get_connection() as conn:
        return _fetchall(conn,
            """SELECT wl.*, e.name AS exercise_name, e.category
               FROM workout_logs wl
               JOIN exercises e ON e.id = wl.exercise_id
               WHERE wl.user_id = %s AND wl.workout_date = %s
               ORDER BY wl.created_at""",
            (user_id, workout_date.isoformat()),
        )


def get_logs_for_exercise(user_id: int, exercise_id: int, limit: int = 200) -> list[dict]:
    """Return recent logs for a specific exercise and user."""
    with get_connection() as conn:
        return _fetchall(conn,
            """SELECT wl.*, e.name AS exercise_name, e.category
               FROM workout_logs wl
               JOIN exercises e ON e.id = wl.exercise_id
               WHERE wl.user_id = %s AND wl.exercise_id = %s
               ORDER BY wl.workout_date DESC, wl.set_number
               LIMIT %s""",
            (user_id, exercise_id, limit),
        )


def delete_log(user_id: int, log_id: int):
    """Delete a single workout log entry (only if owned by user)."""
    with get_connection() as conn:
        _execute(conn, "DELETE FROM workout_logs WHERE id = %s AND user_id = %s",
                 (log_id, user_id))


def get_workout_dates(user_id: int) -> list[str]:
    """Return distinct workout dates for a user (most recent first)."""
    with get_connection() as conn:
        rows = _fetchall(conn,
            """SELECT DISTINCT workout_date FROM workout_logs
               WHERE user_id = %s ORDER BY workout_date DESC""",
            (user_id,),
        )
    return [str(r["workout_date"]) for r in rows]


def get_exercise_progress(user_id: int, exercise_id: int) -> list[dict]:
    """Return per-session aggregated data for an exercise and user."""
    with get_connection() as conn:
        return _fetchall(conn,
            """SELECT
                 workout_date,
                 MAX(weight_kg) AS max_weight,
                 SUM(weight_kg * reps) AS total_volume,
                 MAX(reps) AS max_reps,
                 COUNT(*) AS num_sets
               FROM workout_logs
               WHERE user_id = %s AND exercise_id = %s
               GROUP BY workout_date
               ORDER BY workout_date""",
            (user_id, exercise_id),
        )


# ─── Seed ────────────────────────────────────────────────────────────────────

def seed_default_exercises_for_user(user_id: int):
    """Insert default exercises for a user if they have none."""
    with get_connection() as conn:
        row = _fetchone(conn, "SELECT COUNT(*) AS c FROM exercises WHERE user_id = %s", (user_id,))
        if row and row["c"] > 0:
            return

    defaults = [
        # Petto
        ("Panca piana (bilanciere)", "Petto"),
        ("Panca piana (manubri)", "Petto"),
        ("Panca inclinata (bilanciere)", "Petto"),
        ("Panca inclinata (manubri)", "Petto"),
        ("Croci ai cavi", "Petto"),
        ("Chest press", "Petto"),
        ("Pectoral machine", "Petto"),
        # Schiena
        ("Lat machine", "Schiena"),
        ("Pulley basso", "Schiena"),
        ("Rematore con bilanciere", "Schiena"),
        ("Rematore con manubrio", "Schiena"),
        ("Trazioni alla sbarra", "Schiena"),
        ("Pull down", "Schiena"),
        # Spalle
        ("Military press", "Spalle"),
        ("Lento avanti (manubri)", "Spalle"),
        ("Alzate laterali", "Spalle"),
        ("Alzate frontali", "Spalle"),
        ("Face pull", "Spalle"),
        ("Shoulder press (macchina)", "Spalle"),
        # Gambe
        ("Squat", "Gambe"),
        ("Leg press", "Gambe"),
        ("Leg extension", "Gambe"),
        ("Leg curl", "Gambe"),
        ("Affondi", "Gambe"),
        ("Stacco rumeno", "Gambe"),
        ("Calf raise", "Gambe"),
        ("Hip thrust", "Gambe"),
        # Braccia
        ("Curl con bilanciere", "Braccia"),
        ("Curl con manubri", "Braccia"),
        ("Curl alla panca Scott", "Braccia"),
        ("Pushdown ai cavi (tricipiti)", "Braccia"),
        ("French press", "Braccia"),
        ("Dip alle parallele", "Braccia"),
        # Core
        ("Crunch", "Core"),
        ("Plank", "Core"),
        ("Russian twist", "Core"),
        ("Leg raise", "Core"),
    ]

    for name, category in defaults:
        try:
            add_exercise(name, category, user_id)
        except psycopg2.errors.UniqueViolation:
            with get_connection() as conn:
                pass  # already exists, skip


# ─── Exercise Targets (Progression Engine) ───────────────────────────────────

def get_exercise_target(user_id: int, exercise_id: int) -> dict | None:
    """Return the progression target for an exercise, or None if not set."""
    with get_connection() as conn:
        return _fetchone(conn,
            """SELECT * FROM exercise_targets
               WHERE user_id = %s AND exercise_id = %s""",
            (user_id, exercise_id))


def upsert_exercise_target(user_id: int, exercise_id: int,
                           target_sets: int, target_reps_min: int,
                           target_reps_max: int, progression_step_kg: float):
    """Create or update the progression target for an exercise."""
    with get_connection() as conn:
        _execute(conn,
            """INSERT INTO exercise_targets
                   (user_id, exercise_id, target_sets, target_reps_min,
                    target_reps_max, progression_step_kg, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT (user_id, exercise_id)
               DO UPDATE SET
                   target_sets = EXCLUDED.target_sets,
                   target_reps_min = EXCLUDED.target_reps_min,
                   target_reps_max = EXCLUDED.target_reps_max,
                   progression_step_kg = EXCLUDED.progression_step_kg,
                   updated_at = NOW()""",
            (user_id, exercise_id, target_sets, target_reps_min,
             target_reps_max, progression_step_kg))


def get_all_exercise_targets(user_id: int) -> list[dict]:
    """Return all configured targets for a user, with exercise info."""
    with get_connection() as conn:
        return _fetchall(conn,
            """SELECT et.*, e.name AS exercise_name, e.category
               FROM exercise_targets et
               JOIN exercises e ON e.id = et.exercise_id
               WHERE et.user_id = %s
               ORDER BY e.category, e.name""",
            (user_id,))


# ─── Session-level data for Progression Engine ──────────────────────────────

def get_recent_sessions(user_id: int, exercise_id: int, limit: int = 8) -> list[dict]:
    """Return per-session aggregated data for the last N sessions of an exercise.

    Each row contains: workout_date, avg_weight, max_weight, min_reps, max_reps,
    avg_reps, total_volume, num_sets, and arrays of per-set details.
    """
    with get_connection() as conn:
        return _fetchall(conn,
            """SELECT
                 workout_date,
                 AVG(weight_kg) AS avg_weight,
                 MAX(weight_kg) AS max_weight,
                 MIN(reps) AS min_reps,
                 MAX(reps) AS max_reps,
                 AVG(reps) AS avg_reps,
                 SUM(weight_kg * reps) AS total_volume,
                 COUNT(*) AS num_sets,
                 ARRAY_AGG(weight_kg ORDER BY set_number) AS weights,
                 ARRAY_AGG(reps ORDER BY set_number) AS reps_list
               FROM workout_logs
               WHERE user_id = %s AND exercise_id = %s
               GROUP BY workout_date
               ORDER BY workout_date DESC
               LIMIT %s""",
            (user_id, exercise_id, limit))


# ─── Progression Log ────────────────────────────────────────────────────────

def save_progression_suggestion(user_id: int, exercise_id: int,
                                context_last_sessions: int,
                                context_current_weight: float,
                                context_current_avg_reps: float,
                                context_current_volume: float,
                                suggestion_type: str,
                                suggested_weight_kg: float | None,
                                suggested_reps_target: int | None,
                                reasoning: str) -> int:
    """Save a progression suggestion. Returns the log id."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO progression_log
                       (user_id, exercise_id, context_last_sessions,
                        context_current_weight, context_current_avg_reps,
                        context_current_volume, suggestion_type,
                        suggested_weight_kg, suggested_reps_target, reasoning)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (user_id, exercise_id, context_last_sessions,
                 context_current_weight, context_current_avg_reps,
                 context_current_volume, suggestion_type,
                 suggested_weight_kg, suggested_reps_target, reasoning))
            return cur.fetchone()[0]


def update_progression_outcome(log_id: int, accepted: bool,
                               actual_weight: float, actual_avg_reps: float,
                               outcome_date: date):
    """Record what the user actually did after a suggestion."""
    with get_connection() as conn:
        _execute(conn,
            """UPDATE progression_log
               SET outcome_accepted = %s,
                   outcome_actual_weight = %s,
                   outcome_actual_avg_reps = %s,
                   outcome_date = %s
               WHERE id = %s""",
            (accepted, actual_weight, actual_avg_reps,
             outcome_date.isoformat(), log_id))


def get_latest_suggestion(user_id: int, exercise_id: int) -> dict | None:
    """Return the most recent suggestion for an exercise."""
    with get_connection() as conn:
        return _fetchone(conn,
            """SELECT * FROM progression_log
               WHERE user_id = %s AND exercise_id = %s
               ORDER BY generated_at DESC LIMIT 1""",
            (user_id, exercise_id))


def get_pending_suggestions(user_id: int) -> list[dict]:
    """Return suggestions that haven't been followed up yet."""
    with get_connection() as conn:
        return _fetchall(conn,
            """SELECT pl.*, e.name AS exercise_name, e.category
               FROM progression_log pl
               JOIN exercises e ON e.id = pl.exercise_id
               WHERE pl.user_id = %s AND pl.outcome_accepted IS NULL
               ORDER BY pl.generated_at DESC""",
            (user_id,))


def get_suggestion_history(user_id: int, exercise_id: int,
                           limit: int = 20) -> list[dict]:
    """Return suggestion history for an exercise."""
    with get_connection() as conn:
        return _fetchall(conn,
            """SELECT * FROM progression_log
               WHERE user_id = %s AND exercise_id = %s
               ORDER BY generated_at DESC
               LIMIT %s""",
            (user_id, exercise_id, limit))
