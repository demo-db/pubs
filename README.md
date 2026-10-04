# Pubs DemoDB

This repository publishes Microsoft's classic Pubs sample as a reproducible SQLite fixture. It preserves the original eleven table names, seeded records, primary and foreign keys, seven useful indexes, the `titleview`, and the eight embedded publisher-logo GIFs.

## Source and rights

The source is [`instpubs.sql`](data-source/instpubs.sql) from [`microsoft/sql-server-samples`](https://github.com/microsoft/sql-server-samples/tree/beaab06ef72831089ca80e5355d65e661fd19b26/samples/databases/northwind-pubs) at commit `beaab06ef72831089ca80e5355d65e661fd19b26`. The upstream README identifies it as the SQL Server 2000 Pubs script. Its SHA-256 is `c66479d429f482ef788290dd94bb315f2277327765f480b2b21be6f359eb4bad`. The repository's MIT license is retained in [`data-source/LICENSE.txt`](data-source/LICENSE.txt), and the script's Microsoft 1994–2000 copyright header remains intact.

The MIT notice is included with the original Microsoft copyright notice. The upstream script's `M�nchen` publisher text is preserved as encoded in the pinned source.

## SQLite conversion

Run `python3 scripts/rebuild-source.py` to rebuild `data-source/source.sqlite` from the pinned SQL. The converter is intentionally limited to this exact script and rejects a source whose hash changes. It imports all 255 source `INSERT` statements and checks the expected row counts, primary keys, foreign keys, sample joins, view rows, and GIF signatures.

The smallest required SQL Server adaptations are documented here:

- Database creation, `GO` batches, SQL Server statistics/setup, triggers, and stored procedures are omitted; they are not SQLite data objects.
- The SQL Server clustered and nonclustered indexes are recreated as ordinary SQLite indexes. Because SQLite index names are database-wide, their generated names are prefixed by their table name.
- `MONEY` is stored with SQLite numeric affinity, `IMAGE` as `BLOB`, and `DATETIME` as ISO date text. SQLite does not enforce SQL Server's fixed four-decimal `MONEY` scale. Two-digit source dates are interpreted as their original 1988–1994 years. The source specifies no collation, so SQLite's default binary text comparisons may differ from the SQL Server installation's default collation. SQL Server `LIKE` character ranges in `CHECK` constraints are translated to SQLite `GLOB` ranges.
- The source omits `pubdate` on two titles and relies on `GETDATE()`. The conversion fixes both dynamic values to `2000-01-01` so repeated builds produce identical bytes. The `jobs.job_id` identity becomes an SQLite integer primary key.
- SQL Server primary keys imply `NOT NULL`; the converter states that explicitly for SQLite text and composite keys, where SQLite does not enforce it implicitly.

The seed contains 23 authors, 8 publishers, 18 titles, 25 title-author links, 6 stores, 21 sales rows, 86 royalty-schedule rows, 3 discounts, 14 jobs, 8 publisher records, and 43 employees. The `titleview` returns 25 rows. No sample rows are invented or dropped.

The source has no primary key or unique index on `discounts` or `roysched`; the converter checks those physical constraints and their ModelSpec entities omit `key`. The public schema records an empty primary-key list for these tables. The current descriptor format does not yet include a unique-key inventory, so an omitted unique-key field is not used to infer uniqueness.

## Generated contract

The database manifest, schema, exports, ModelSpec, MeaningGraph, and public OVDB descriptor are generated using the shared DemoDB provider tool. The read-only OVDB query capability remains disabled until a live backend mount is verified.
