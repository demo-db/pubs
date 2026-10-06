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

The `ingitdb/` directory contains 255 source table rows across 11 collections. It is a Git-backed, queryable snapshot prepared from the pinned SQLite fixture. Verify and query it with the installed inGitDB CLI:

```sh
ingitdb validate --path ingitdb
ingitdb select --path ingitdb --from authors_84094218 --limit 1 --format json
```

[`ingitdb/export-manifest.json`](ingitdb/export-manifest.json) maps each native table to its collection, row count, original primary and foreign keys, column types, transport encodings, and SHA-256 of its record file. The source fixture SHA-256 is `b45b08b7c06441cc0b138b031ea5bd32bd5866aebf874c89d2ebf7fc6abb3691`. These bytes were exported against provider commit `6c06c5c7395b03ff1a02c2b1a21485add3e1b65b`; the source fixture hash also matches this repository's pinned fixture. Record keys encode native primary keys where present; keyless tables use stable ordinal IDs, which are not native keys. Native key relationships are descriptive metadata, not enforced in this snapshot. Exact decimal values travel as strings and binary values as base64 where marked in column metadata. Source view definitions are retained as metadata only; they are not materialized in inGitDB. Source rights and original notices remain in [`data-source/`](data-source/) and [`LICENSE`](LICENSE).
