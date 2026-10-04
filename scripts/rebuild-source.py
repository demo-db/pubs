#!/usr/bin/env python3
"""Build the SQLite Pubs fixture from the pinned Microsoft SQL Server 2000 script.

This deliberately supports only the syntax used by this one pinned source file.
It does not try to be a general T-SQL converter.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data-source" / "instpubs.sql"
OUTPUT = ROOT / "data-source" / "source.sqlite"
MANIFEST = ROOT / "manifest.json"
EXPECTED_SOURCE_SHA256 = "c66479d429f482ef788290dd94bb315f2277327765f480b2b21be6f359eb4bad"


def split_top_level(text: str) -> list[str]:
    """Split comma-delimited SQL fragments outside strings and parentheses."""
    parts: list[str] = []
    start = depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if in_string and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_string = not in_string
        elif not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(text[start:i].strip())
                start = i + 1
        i += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def matching_paren(text: str, opening: int) -> int:
    depth = 0
    in_string = False
    i = opening
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if in_string and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_string = not in_string
        elif not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError("unclosed parenthesized SQL expression")


def sqlite_column(fragment: str) -> str:
    fragment = re.sub(r"\bCONSTRAINT\s+[A-Za-z_][\w$]*\s+", "", fragment, flags=re.I)
    fragment = re.sub(r"\b(?:CLUSTERED|NONCLUSTERED)\b", "", fragment, flags=re.I)
    fragment = re.sub(r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)", "", fragment, flags=re.I)
    fragment = re.sub(r"\bSMALLINT\b|\bTINYINT\b|\bBIT\b", "INTEGER", fragment, flags=re.I)
    fragment = re.sub(r"\bMONEY\b", "NUMERIC", fragment, flags=re.I)
    fragment = re.sub(r"\bIMAGE\b", "BLOB", fragment, flags=re.I)
    fragment = re.sub(r"\bDATETIME\b", "TEXT", fragment, flags=re.I)
    fragment = re.sub(r"\bLIKE\b", "GLOB", fragment, flags=re.I)
    # The upstream seed omits pubdate for one row and relies on GETDATE(). Freeze
    # that dynamic default to keep the generated fixture reproducible.
    fragment = re.sub(r"\bGETDATE\s*\(\s*\)", "'2000-01-01'", fragment, flags=re.I)
    # SQL Server primary keys imply NOT NULL. SQLite does not enforce that
    # implication for non-INTEGER rowid keys unless it is stated explicitly.
    if re.search(r"\bPRIMARY\s+KEY\b", fragment, flags=re.I) and not re.search(r"\bPRIMARY\s+KEY\s*\(", fragment, flags=re.I):
        if not re.search(r"\bNOT\s+NULL\b", fragment, flags=re.I):
            fragment = re.sub(r"\bPRIMARY\s+KEY\b", "NOT NULL PRIMARY KEY", fragment, count=1, flags=re.I)
    return " ".join(fragment.split())


def create_tables(db: sqlite3.Connection, source: str) -> set[str]:
    matches = list(re.finditer(r"CREATE\s+TABLE\s+(\w+)\s*\(", source, flags=re.I))
    tables: set[str] = set()
    for match in matches:
        name = match.group(1)
        opening = match.end() - 1
        closing = matching_paren(source, opening)
        body = source[opening + 1 : closing]
        definitions: list[str] = []
        table_primary_key_columns: list[str] = []
        for item in split_top_level(body):
            if re.match(r"CONSTRAINT\b", item, flags=re.I):
                item = re.sub(r"^CONSTRAINT\s+[A-Za-z_][\w$]*\s+", "", item, flags=re.I)
                item = re.sub(r"\b(?:CLUSTERED|NONCLUSTERED)\b", "", item, flags=re.I)
                item = sqlite_column(item)
                primary_key = re.search(r"\bPRIMARY\s+KEY\s*\(([^)]*)\)", item, flags=re.I)
                if primary_key:
                    table_primary_key_columns.extend(column.strip().strip('"[]') for column in primary_key.group(1).split(","))
                definitions.append(item)
            else:
                definitions.append(sqlite_column(item))
        for column_name in table_primary_key_columns:
            for i, definition in enumerate(definitions):
                column = re.match(r"([A-Za-z_][\w$]*)\b", definition)
                if column and column.group(1).lower() == column_name.lower():
                    if not re.search(r"\bNOT\s+NULL\b", definition, flags=re.I):
                        typed_column = re.match(r"^(\w+\s+\w+(?:\s*\([^)]*\))?)", definition)
                        if not typed_column:
                            raise ValueError(f"table {name}: cannot determine type for primary key column {column_name}")
                        definitions[i] = typed_column.group(1) + " NOT NULL" + definition[typed_column.end() :]
                    break
            else:
                raise ValueError(f"table {name}: primary key column {column_name} is missing")
        db.execute(f'CREATE TABLE "{name}" ({", ".join(definitions)})')
        tables.add(name)
    return tables


def insert_statements(source: str):
    pattern = re.compile(r"\bINSERT\s+(?:INTO\s+)?([A-Za-z_][\w$]*)(?:\s*\([^)]*\))?\s+VALUES\s*\(", re.I)
    pos = 0
    while match := pattern.search(source, pos):
        opening = match.end() - 1
        closing = matching_paren(source, opening)
        yield match.group(1), source[match.start() : closing + 1]
        pos = closing + 1


DATE_TABLES = {"sales", "employee", "titles"}


def sqlite_insert(table: str, statement: str) -> str:
    statement = re.sub(
        r"^INSERT\s+(?:INTO\s+)?[A-Za-z_][\w$]*(\s*\([^)]*\))?(\s+VALUES\b)",
        lambda match: f'INSERT INTO "{table}"{match.group(1) or ""}{match.group(2)}',
        statement,
        flags=re.I,
    )
    if table == "jobs" and re.search(r'^INSERT\s+INTO\s+"jobs"\s+VALUES\b', statement, flags=re.I):
        statement = re.sub(
            r'^(INSERT\s+INTO\s+"jobs")\s+VALUES\b',
            r"\1 (job_desc, min_lvl, max_lvl) VALUES",
            statement,
            flags=re.I,
        )
    output: list[str] = []
    in_string = False
    i = 0
    while i < len(statement):
        if statement[i] == "'":
            output.append(statement[i])
            if in_string and i + 1 < len(statement) and statement[i + 1] == "'":
                output.append("'")
                i += 2
                continue
            in_string = not in_string
            i += 1
            continue
        if not in_string and statement[i : i + 2].lower() == "0x":
            match = re.match(r"0x([0-9A-F]+)", statement[i:], flags=re.I)
            if match:
                output.append("X'" + match.group(1) + "'")
                i += len(match.group(0))
                continue
        if not in_string and statement[i] == "$":
            match = re.match(r"\$(\d+(?:\.\d+)?)", statement[i:])
            if match:
                output.append(match.group(1))
                i += len(match.group(0))
                continue
        output.append(statement[i])
        i += 1
    statement = "".join(output)
    if table in DATE_TABLES:
        def date_to_iso(match: re.Match[str]) -> str:
            month, day, year = map(int, match.groups())
            # Every source year in the 2-digit date literals is 1988-1994.
            if year > 49:
                year += 1900
            else:
                year += 2000
            return f"'{year:04d}-{month:02d}-{day:02d}'"
        statement = re.sub(r"'(\d{1,2})/(\d{1,2})/(\d{2})'", date_to_iso, statement)
    return statement


def create_indexes(db: sqlite3.Connection, source: str) -> int:
    pattern = re.compile(r"CREATE\s+(?:(?:NON)?CLUSTERED\s+)?INDEX\s+(\w+)\s+ON\s+(\w+)\s*\(([^)]*)\)", re.I)
    count = 0
    used: set[str] = set()
    for match in pattern.finditer(source):
        index, table, columns = match.groups()
        name = f"{table}_{index}"
        if name.lower() in used:
            raise ValueError(f"duplicate converted index name: {name}")
        used.add(name.lower())
        db.execute(f'CREATE INDEX "{name}" ON "{table}" ({columns})')
        count += 1
    return count


def create_titleview(db: sqlite3.Connection, source: str) -> None:
    match = re.search(r"CREATE\s+VIEW\s+titleview\s+AS\s+(.*?)\s+GO\b", source, flags=re.I | re.S)
    if not match:
        raise ValueError("pinned source no longer contains titleview")
    db.execute("CREATE VIEW titleview AS " + " ".join(match.group(1).split()))


def validate(db: sqlite3.Connection, tables: set[str], insertion_count: int) -> None:
    expected_tables = {
        "authors", "publishers", "titles", "titleauthor", "stores", "sales",
        "roysched", "discounts", "jobs", "pub_info", "employee",
    }
    expected_rows = {
        "authors": 23, "publishers": 8, "titles": 18, "titleauthor": 25,
        "stores": 6, "sales": 21, "roysched": 86, "discounts": 3,
        "jobs": 14, "pub_info": 8, "employee": 43,
    }
    if tables != expected_tables:
        raise ValueError(f"source table set changed: {sorted(tables)}")
    if insertion_count != sum(expected_rows.values()):
        raise ValueError(f"source insert count changed: {insertion_count}")
    for table, expected in expected_rows.items():
        actual = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if actual != expected:
            raise ValueError(f"{table}: expected {expected} rows, got {actual}")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("SQLite integrity check failed")
    fk_errors = db.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        raise ValueError(f"SQLite foreign-key check failed: {fk_errors[:3]}")
    if db.execute("SELECT COUNT(*) FROM titleview").fetchone()[0] != 25:
        raise ValueError("titleview row count changed")
    if db.execute("SELECT COUNT(*) FROM pub_info WHERE logo IS NOT NULL").fetchone()[0] != 8:
        raise ValueError("expected all eight publisher logos to remain binary data")
    if db.execute("SELECT COUNT(*) FROM publishers WHERE city = 'M�nchen'").fetchone()[0] != 1:
        raise ValueError("the pinned source's publisher city replacement character changed")
    if db.execute("SELECT COUNT(*) FROM pub_info WHERE pr_info LIKE '%M�nchen%'").fetchone()[0] != 1:
        raise ValueError("the pinned source's publisher text replacement character changed")
    if db.execute("SELECT hex(substr(logo, 1, 6)) FROM pub_info WHERE logo IS NOT NULL LIMIT 1").fetchone()[0] != "474946383961":
        raise ValueError("publisher logo GIF signature was not preserved")
    if db.execute("SELECT COUNT(*) FROM sales JOIN titles USING(title_id) JOIN stores USING(stor_id)").fetchone()[0] != 21:
        raise ValueError("sample sales join changed")
    expected_primary_keys = {
        "authors": ["au_id"], "publishers": ["pub_id"], "titles": ["title_id"],
        "titleauthor": ["au_id", "title_id"], "stores": ["stor_id"],
        "sales": ["stor_id", "ord_num", "title_id"], "jobs": ["job_id"],
        "pub_info": ["pub_id"], "employee": ["emp_id"],
    }
    expected_keyless_tables = {"discounts", "roysched"}
    for table, columns in expected_primary_keys.items():
        info = db.execute(f'PRAGMA table_info("{table}")').fetchall()
        actual = [row[1] for row in sorted((row for row in info if row[5]), key=lambda row: row[5])]
        if actual != columns:
            raise ValueError(f"{table}: expected primary key {columns}, got {actual}")
        if table != "jobs":
            nulls = [row[1] for row in info if row[1] in columns and not row[3]]
            if nulls:
                raise ValueError(f"{table}: SQLite does not enforce NOT NULL on primary key columns {nulls}")
    for table in expected_keyless_tables:
        info = db.execute(f'PRAGMA table_info("{table}")').fetchall()
        primary_key = [row[1] for row in sorted((row for row in info if row[5]), key=lambda row: row[5])]
        if primary_key:
            raise ValueError(f"{table}: expected no declared primary key, got {primary_key}")
        unique_indexes = [row[1] for row in db.execute(f'PRAGMA index_list("{table}")') if row[2] and row[3] != "pk"]
        if unique_indexes:
            raise ValueError(f"{table}: expected no unique indexes, got {unique_indexes}")
    null_pk_attempts = [
        "INSERT INTO authors (au_id, au_lname, au_fname, phone, contract) VALUES (NULL, 'Test', 'Test', 'UNKNOWN', 0)",
        "INSERT INTO publishers (pub_id, country) VALUES (NULL, 'USA')",
        "INSERT INTO titles (title_id, title, type, pub_id) VALUES (NULL, 'Test', 'business', '1389')",
        "INSERT INTO titleauthor (au_id, title_id) VALUES (NULL, 'BU1032')",
        "INSERT INTO titleauthor (au_id, title_id) VALUES ('409-56-7008', NULL)",
        "INSERT INTO stores (stor_id, stor_name) VALUES (NULL, 'Test')",
        "INSERT INTO sales (stor_id, ord_num, ord_date, qty, payterms, title_id) VALUES (NULL, 'TEST', '2000-01-01', 1, 'Net 30', 'BU1032')",
        "INSERT INTO sales (stor_id, ord_num, ord_date, qty, payterms, title_id) VALUES ('6380', 'TEST', '2000-01-01', 1, 'Net 30', NULL)",
        "INSERT INTO pub_info (pub_id) VALUES (NULL)",
        "INSERT INTO employee (emp_id, fname, lname, job_id, pub_id) VALUES (NULL, 'Test', 'Test', 1, '1389')",
    ]
    for statement in null_pk_attempts:
        db.execute("SAVEPOINT null_primary_key_probe")
        try:
            db.execute(statement)
        except sqlite3.IntegrityError:
            db.execute("ROLLBACK TO null_primary_key_probe")
            db.execute("RELEASE null_primary_key_probe")
        else:
            db.execute("ROLLBACK TO null_primary_key_probe")
            db.execute("RELEASE null_primary_key_probe")
            raise ValueError(f"SQLite accepted a NULL primary-key value: {statement}")
    if db.execute("SELECT COUNT(*) FROM titleview").fetchone()[0] != 25:
        raise ValueError("NULL-key rejection probes changed the published fixture")


def build_database(output: Path) -> None:
    source_bytes = SOURCE.read_bytes()
    actual_hash = hashlib.sha256(source_bytes).hexdigest()
    if actual_hash != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"pinned source SHA-256 mismatch: {actual_hash}")
    source = source_bytes.decode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    db = sqlite3.connect(output)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        tables = create_tables(db, source)
        inserted = 0
        for table, statement in insert_statements(source):
            if table not in tables:
                raise ValueError(f"insert targets unknown table: {table}")
            converted = sqlite_insert(table, statement)
            try:
                db.execute(converted)
            except sqlite3.Error as error:
                raise ValueError(f"could not import {table}: {converted[:180]}") from error
            inserted += 1
        index_count = create_indexes(db, source)
        create_titleview(db, source)
        validate(db, tables, inserted)
        db.commit()
        print(f"built {output}: {len(tables)} tables, {inserted} source rows, {index_count} indexes, titleview")
    finally:
        db.close()


def sqlite_snapshot(path: Path) -> dict[str, object]:
    """Capture logical schema and all table/view values, independent of file headers."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        db.row_factory = None
        objects = db.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = [row[1] for row in objects if row[0] == "table"]
        views = [row[1] for row in objects if row[0] == "view"]

        def encode_cell(value: object) -> list[object]:
            if isinstance(value, bytes):
                return ["blob", value.hex()]
            if value is None:
                return ["null"]
            if isinstance(value, int):
                return ["integer", value]
            if isinstance(value, float):
                return ["real", value.hex()]
            return ["text", value]

        def canonical_rows(name: str) -> list[list[list[object]]]:
            rows = [[encode_cell(value) for value in row] for row in db.execute(f'SELECT * FROM "{name}"')]
            return sorted(rows, key=lambda row: json.dumps(row, ensure_ascii=False, separators=(",", ":")))

        table_metadata = {}
        for table in tables:
            columns = db.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
            foreign_keys = db.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            indexes = []
            for index in db.execute(f'PRAGMA index_list("{table}")').fetchall():
                indexes.append((index, db.execute(f'PRAGMA index_xinfo("{index[1]}")').fetchall()))
            table_metadata[table] = {
                "columns": columns,
                "foreignKeys": foreign_keys,
                "indexes": indexes,
                "rows": canonical_rows(table),
            }
        return {
            "objects": objects,
            "tables": table_metadata,
            "views": {view: canonical_rows(view) for view in views},
        }
    finally:
        db.close()


def check_rebuild() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected_hash = manifest["source"]["databaseSha256"]
    actual_hash = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"checked-in SQLite artifact SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")
    with tempfile.TemporaryDirectory(prefix="pubs-source-check-") as temp_dir:
        rebuilt = Path(temp_dir) / "rebuilt.sqlite"
        build_database(rebuilt)
        if sqlite_snapshot(OUTPUT) != sqlite_snapshot(rebuilt):
            raise ValueError(
                "rebuilt database differs logically from data-source/source.sqlite "
                "(schema, constraints, indexes, views, rows, or BLOBs)"
            )
    print(f"verified checked-in SQLite artifact {expected_hash} and full logical rebuild equivalence")


def main() -> None:
    if sys.argv[1:] == ["--check"]:
        check_rebuild()
    elif sys.argv[1:]:
        raise ValueError("usage: rebuild-source.py [--check]")
    else:
        build_database(OUTPUT)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"build failed: {error}", file=sys.stderr)
        raise
