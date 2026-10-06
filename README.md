# Pubs DemoDB

This repository publishes Microsoft's classic Pubs sample as a reproducible SQLite fixture. It preserves the original eleven table names, seeded records, primary and foreign keys, seven useful indexes, the `titleview`, and the eight embedded publisher-logo GIFs.

## Source and rights

The source is [`instpubs.sql`](data-source/instpubs.sql) from [`microsoft/sql-server-samples`](https://github.com/microsoft/sql-server-samples/tree/beaab06ef72831089ca80e5355d65e661fd19b26/samples/databases/northwind-pubs) at commit `beaab06ef72831089ca80e5355d65e661fd19b26`. The upstream README identifies it as the SQL Server 2000 Pubs script. Its SHA-256 is `c66479d429f482ef788290dd94bb315f2277327765f480b2b21be6f359eb4bad`. The repository's MIT license is retained in [`data-source/LICENSE.txt`](data-source/LICENSE.txt), and the script's Microsoft 1994–2000 copyright header remains intact.

The MIT notice is included with the original Microsoft copyright notice. The upstream script's `M�nchen` publisher text is preserved as encoded in the pinned source.

## SQLite conversion

Run `python3 scripts/rebuild-source.py` to rebuild `data-source/source.sqlite` from the pinned SQL. The converter is intentionally limited to this exact script and rejects a source whose hash changes. It imports all 255 source `INSERT` statements and checks the expected row counts, primary keys, foreign keys, sample joins, view rows, and GIF signatures. Run `python3 scripts/rebuild-source.py --check` to rebuild in a temporary directory and compare the complete logical schema, constraints, indexes, view rows, every table row, and BLOB bytes against the checked-in artifact without replacing it. CI uses this check because SQLite can produce different file bytes across library versions; the checked-in file itself is still verified against its manifest SHA-256.

The smallest required SQL Server adaptations are documented here:

- Database creation, `GO` batches, SQL Server statistics/setup, triggers, and stored procedures are omitted; they are not SQLite data objects.
- The SQL Server clustered and nonclustered indexes are recreated as ordinary SQLite indexes. Because SQLite index names are database-wide, their generated names are prefixed by their table name.
- `MONEY` is stored with SQLite numeric affinity, `IMAGE` as `BLOB`, and `DATETIME` as ISO date text. SQLite does not enforce SQL Server's fixed four-decimal `MONEY` scale. Two-digit source dates are interpreted as their original 1988–1994 years. The source specifies no collation, so SQLite's default binary text comparisons may differ from the SQL Server installation's default collation. SQL Server `LIKE` character ranges in `CHECK` constraints are translated to SQLite `GLOB` ranges.
- The source omits `pubdate` on two titles and relies on `GETDATE()`. The conversion fixes both dynamic values to `2000-01-01`; within one SQLite library version, rebuilding produces the same fixture bytes. The `jobs.job_id` identity becomes an SQLite integer primary key.
- SQL Server primary keys imply `NOT NULL`; the converter states that explicitly for SQLite text and composite keys, where SQLite does not enforce it implicitly.
- The source has two publisher strings with the literal U+FFFD replacement character (`M�nchen`). They are preserved exactly rather than guessed from an earlier encoding. The two source rows that omit `pubdate` rely on `GETDATE()` and are frozen to `2000-01-01`.
- SQLite and JSON exports preserve SQL `NULL`. CSV has no standard NULL marker, so NULL cells are written as empty fields and cannot be distinguished from empty text by reading CSV alone. BLOB values in JSON and CSV are base64 encoded.

The seed contains 23 authors, 8 publishers, 18 titles, 25 title-author links, 6 stores, 21 sales rows, 86 royalty-schedule rows, 3 discounts, 14 jobs, 8 publisher records, and 43 employees. The `titleview` returns 25 rows. No sample rows are invented or dropped.

The source has no primary key or unique index on `discounts` or `roysched`; the converter checks those physical constraints and their ModelSpec entities omit `key`. The public schema records an empty primary-key list for these tables. The current descriptor format does not yet include a unique-key inventory, so an omitted unique-key field is not used to infer uniqueness.

## Generated contract

The database manifest, schema, exports, ModelSpec, MeaningGraph, and public OVDB descriptor are generated using the shared DemoDB provider tool. The read-only OVDB query capability remains disabled until a live backend mount is verified.

## Native inGitDB snapshot

The `ingitdb/` directory contains 255 source rows in 11 collections, exported from the pinned SQLite fixture by DataTug's generic DALgo → inGitDB exporter. The source fixture SHA-256 is `b45b08b7c06441cc0b138b031ea5bd32bd5866aebf874c89d2ebf7fc6abb3691`. This Git-backed edition is a queryable snapshot, not a live SQL database.

Use DataTug CLI v0.61.1 or newer to reproduce this export, and inGitDB CLI v0.70.0 or newer to validate and query this edition.

```sh
ingitdb validate --path ingitdb
ingitdb select --path ingitdb --from 'authors' --limit 1 --format json
```

Each source table has a `.collection/definition.yaml` with ordered fields, source primary-key columns, portable indexes and foreign-key groups/actions. `.ingitdb/source-collections.json` maps native collection IDs to exact SQLite table names; names outside inGitDB’s ID alphabet use a deterministic `dt_` UTF-8 hex ID. Its `source_schema.source_definition_json` retains the original SQLite DDL, declared column types, defaults and complete index details. The native record file is `records.json`, keyed by deterministic transport IDs derived from the ordered source primary key; keyless tables use source-row ordinals. These transport IDs are not new SQL columns. Exact decimals are stored as strings, BLOBs as base64, and `source-storage-*.jsonl` sidecars retain decimal SQLite storage classes where needed. The 1 source view definitions remain in `.ingitdb/source-views.yaml` as metadata; they are not materialized collections.

The checked-in Git snapshot is the published inGitDB edition. [`ingitdb/export-manifest.json`](ingitdb/export-manifest.json) records the DataTug version, binary hash, pinned source and record checksums, plus the independent parity receipt at [`ingitdb/native-parity-report.json`](ingitdb/native-parity-report.json). Its `prepared-not-hosted` status describes the generated bundle before repository publication and also covers BigQuery load files; it does not imply a hosted BigQuery service.

The published record format is DataTug's default JSON. To produce another edition from a verified, decoded copy of this pinned SQLite fixture, choose a **new** destination and pass `--records-format json` (default), `jsonl`, `ingr`, `csv`, or `yaml`:

```sh
datatug db export --from sqlite:///absolute/path/to/pinned-source.sqlite \
  --to ingitdb:///absolute/path/to/new-output --records-format json
```

The independent checker in `demo-db/websites/scripts/hosting-tools/validate_datatug_exports.py` compares the native schema and every typed row at its transport ID with this repository's pinned source. Run it from a checkout containing both repositories:

```sh
python3 ../websites/scripts/hosting-tools/validate_datatug_exports.py . ingitdb \
  --report /private/tmp/pubs-ingitdb-parity.json
```

The source primary keys, foreign keys, UNIQUE and CHECK constraints, defaults, collations and SQL actions are preserved as source metadata; inGitDB does not enforce their full SQL behavior on later record edits. Source rights and original notices remain in [`data-source/`](data-source/) and [`LICENSE`](LICENSE).
