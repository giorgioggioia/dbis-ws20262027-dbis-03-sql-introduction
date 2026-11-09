"""Autograder tests for DB&IS Exercise 03 (SQL Introduction).

Run from the root of a student repository (the Classroom 50 runner uses the
repository as working directory):

    python -m pytest -p no:cacheprovider path/to/test_sql.py

Needs the sqlite3 command-line tool (`.import`, `.mode`, ... are CLI commands).
Students choose their own schema, so the tests only check what the sheet asks
for: the files exist, `cat movies.sql queries.sql | sqlite3` runs cleanly,
the tables are typed, filled and use keys, and the three questions are
answered correctly.
"""
import pathlib
import re
import shutil
import sqlite3
import subprocess

import pytest

ROOT = pathlib.Path.cwd()
TIMEOUT = 60

ACTING_WINNERS = {
    # actor surname: (role keyword, movie keyword, category keywords)
    "Hoffman": ("Ted", "Kramer", ("actor",)),
    "Streep": ("Joanna", "Kramer", ("actress", "support")),
    "Rockwell": ("Dixon", "Billboards", ("actor", "support")),
}
MCDORMAND_WINS = {"Fargo": "Marge", "Billboards": "Mildred"}
# People who must never show up in the answer to question 3 (did not win an
# acting Oscar for these movies, or won in a non-acting category).
NOT_ACTING_WINNERS = ["DiCaprio", "Winslet", "Harrelson", "Macy", "Buscemi", "Stormare",
                      "Bates", "Gloria Stuart", "Hedges", "Benton", "Jaffe", "Cameron", "Landau"]


def _read(name: str) -> str:
    path = ROOT / name
    if not path.is_file():
        pytest.fail(f"{name} not found in the repository root")
    return path.read_text(encoding="utf-8", errors="replace")


def _sqlite(script: str, db: str = ":memory:") -> subprocess.CompletedProcess:
    exe = shutil.which("sqlite3")
    if exe is None:
        pytest.fail("the sqlite3 command-line tool is not installed")
    return subprocess.run([exe, db], input=script, capture_output=True, text=True,
                          cwd=ROOT, timeout=TIMEOUT)


@pytest.fixture(scope="module")
def run() -> subprocess.CompletedProcess:
    """`cat movies.sql queries.sql | sqlite3`, exactly as in the README."""
    return _sqlite(_read("movies.sql") + _read("queries.sql"))


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> sqlite3.Connection:
    """A database file built from movies.sql alone."""
    path = tmp_path_factory.mktemp("db") / "movies.db"
    _sqlite(_read("movies.sql"), str(path))
    con = sqlite3.connect(path)
    yield con
    con.close()


def _tables(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]


def _section(output: str, marker: str) -> str:
    """Output printed after the question matching `marker`, up to the next question."""
    # An unquoted `.print \nQuestion?\n` prints real newlines
    # on older sqlite3 but a literal backslash-n on newer ones (e.g. 3.45 on the
    # grading runner). Treat both the same.
    lines = output.replace("\\n", "\n").splitlines()
    for i, line in enumerate(lines):
        if re.search(marker, line, re.I):
            body = []
            for nxt in lines[i + 1:]:
                if nxt.rstrip().endswith("?"):
                    break
                body.append(nxt)
            return "\n".join(body)
    pytest.fail(f"question matching '{marker}' is not printed (use .print as in the template)")


def test_required_files():
    for name in ("movies.sql", "queries.sql"):
        assert (ROOT / name).is_file(), f"{name} is missing"
    tsv = [p for p in ROOT.rglob("*.tsv") if ".git" not in p.parts]
    assert tsv, "no TSV files with your data found"


def test_runs_without_errors(run, db):
    assert _tables(db), "movies.sql does not create any tables"
    assert run.returncode == 0, f"sqlite3 exited with {run.returncode}:\n{run.stderr}"
    assert run.stderr.strip() == "", f"sqlite3 reported errors or warnings:\n{run.stderr}"


def test_tables_typed_and_filled(db):
    tables = _tables(db)
    assert len(tables) >= 3, f"expected at least 3 tables, found {tables}"
    for table in tables:
        cols = db.execute(f'PRAGMA table_info("{table}")').fetchall()
        untyped = [c[1] for c in cols if not c[2].strip()]
        assert not untyped, f"columns without a type in table {table}: {untyped}"
        rows = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        assert rows > 0, f"table {table} is empty (did the .import work?)"


def test_primary_and_foreign_keys(db):
    tables = _tables(db)
    with_pk = [t for t in tables
               if any(c[5] for c in db.execute(f'PRAGMA table_info("{t}")'))]
    with_fk = [t for t in tables if db.execute(f'PRAGMA foreign_key_list("{t}")').fetchall()]
    assert with_pk, "no table declares a PRIMARY KEY"
    assert with_fk, "no table declares a FOREIGN KEY (REFERENCES ...)"
    violations = db.execute("PRAGMA foreign_key_check").fetchall()
    assert not violations, f"foreign keys point to missing rows: {violations[:5]}"


def test_question_1_titanic(run):
    out = _section(run.stdout, r"titanic\s+released")
    assert "1997" in out, "Titanic's release year (1997) is missing"
    assert re.search(r"\b\d\.\d+\b", out), "Titanic's IMDb rating is missing"
    for other in ("Fargo", "Kramer", "Billboards", "1996", "1979", "2017"):
        assert other not in out, f"answer also contains {other}, which is not about Titanic"


def test_question_2_fargo(run):
    out = _section(run.stdout, r"directed\s+fargo")
    assert re.search(r"joel\W+coen|coen\W+joel", out, re.I), "Joel Coen is missing"
    for other in ("Benton", "McDonagh", "Cameron"):
        assert other not in out, f"answer also contains {other}, who did not direct Fargo"


def test_question_3_oscars(run):
    out = _section(run.stdout, r"won\s+oscars")
    rows = out.splitlines()
    for wrong in NOT_ACTING_WINNERS:
        assert wrong.lower() not in out.lower(), f"{wrong} did not win an acting Oscar here"
    for actor, (role, movie, categories) in ACTING_WINNERS.items():
        hits = [r for r in rows if actor in r]
        assert len(hits) == 1, f"expected exactly one row for {actor}, got {len(hits)}"
        row = hits[0].lower()
        for needed in (role, movie, *categories):
            assert needed.lower() in row, f"row for {actor} lacks '{needed}': {hits[0].strip()}"
    mcd = [r for r in rows if "McDormand" in r]
    assert len(mcd) == 2, f"Frances McDormand won twice, got {len(mcd)} rows"
    for movie, role in MCDORMAND_WINS.items():
        assert any(movie in r and role in r and "actress" in r.lower() for r in mcd), \
            f"McDormand's Best Actress win for {movie} ({role}) is missing or wrong"
