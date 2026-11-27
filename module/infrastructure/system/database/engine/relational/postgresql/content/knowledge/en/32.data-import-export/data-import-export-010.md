# Distinguishing Data Exports, Logical Dumps, and Recoverable Backups

In PostgreSQL, **data exports**, **logical dumps**, and **recoverable backups** are related concepts, but they are not interchangeable. A CSV file holds data rows for interchange; a `pg_dump` file captures a database's structure and data at a single snapshot; and an incident recovery plan must prove that files, permissions, software, WAL, and operational procedures are sufficient to bring the system back within **the scope and point in time the business requires**.

For example, an `orders.csv` file contains no users, indexes, constraints, or sequence states. A `pg_dump -Fc` archive can rebuild a database, yet holds no WAL history to recover to 15:59 when the dump snapshot was taken at 01:00. A physical copy from `pg_basebackup` can restore a cluster, yet **PITR** to an arbitrary point in time requires a complete WAL chain and a working retrieval mechanism. Even when a backup file opens cleanly, never having rehearsed a restore remains a serious operational risk.

This lesson belongs to the **Data Import & Export** chapter of the **Database Engine Relational PostgreSQL** module. Its goal is to help you select the right tool for data interchange, migration, and protection while distinguishing **having an artifact** from **verified recoverability**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the differences between an export, a logical dump, a physical backup, and a recoverable backup.
2. Use `COPY`, `\copy`, `pg_dump`, `pg_restore`, `pg_dumpall`, and `pg_basebackup` for their intended purposes.
3. Distinguish plain SQL, custom, directory, and tar dump formats.
4. Understand how snapshots, DDL, multiple databases, and external operations affect consistency.
5. Choose a backup strategy based on **RPO** and **RTO**.
6. Understand the relationship between base backups, WAL archives, recovery targets, and PITR.
7. Identify roles, tablespaces, extensions, secrets, configuration files, and dependencies omitted by common exports.
8. Perform test restores into isolated environments and verify both data integrity and usability.
9. Avoid dangerous mistakes such as restoring onto production accidentally or running `--clean` without safeguards.
10. Design checklists for retention, encryption, integrity checks, and periodic recovery drills.

## 2. Big Picture

~~~text
                 Running PostgreSQL
                          |
            +-------------+---------------+
            |             |               |
            v             v               v
          EXPORT     LOGICAL DUMP   PHYSICAL BACKUP
          COPY         pg_dump        pg_basebackup
          \copy        pg_dumpall     filesystem snapshot
            |             |               |
            v             v               v
       CSV/TSV/JSON   SQL/archive    Data pages + WAL
            |             |               |
            v             v               v
       COPY FROM/ETL  psql/pg_restore Physical recovery
            |             |               |
            +-------------+---------------+
                          |
                          v
            Test restore + measure RPO/RTO +
             verify business data integrity
~~~

### 2.1. Three distinct questions

- **Export:** "Which rows and columns do I want to extract for use elsewhere?"
- **Logical dump:** "Which database objects and data do I want to reconstruct using SQL semantics?"
- **Recoverable backup:** "If the source vanishes or data corrupts right now, can I rebuild the exact scope needed at the expected point in time?"

### 2.2. A backup is an outcome contract

You must define scope, point in time, completeness, copy locations, access permissions, encryption keys, PostgreSQL version, and restore prerequisites. A `.sql`, `.dump`, `.tar`, or `.csv` file extension **does not prove** a backup meets requirements.

## 3. Key Comparison Table

| Attribute | Data export | Logical dump | Physical backup with WAL |
|---|---|---|---|
| Tools | `COPY`, `\copy`, SQL/ETL | `pg_dump`, `pg_dumpall` | `pg_basebackup`, properly coordinated snapshot |
| Unit | Query/table/data slice | Single database, or cluster via multiple dumps | Entire database cluster |
| Rows | Yes | Yes | Yes, via physical data files |
| Schema, indexes | Usually no | Yes, in full dumps | Yes, inside data files |
| Cluster-wide roles | No | Requires globals via `pg_dumpall` | Yes, inside cluster catalog |
| WAL for PITR | No | No | Must ensure complete WAL coverage |
| Single-table recovery | Import into target schema | Selectively restorable via `pg_restore` | Usually requires spinning up a secondary cluster |
| Major version upgrade | Via import | Usually convenient when compatible | Cannot serve directly as a cross-major upgrade |
| RPO | As of exported data | As of dump snapshot | Depends on base backup + retained WAL |
| Recoverability | Needs target schema and ETL | Requires successful restore | Requires physical restore + WAL replay |
| Secret protection | May contain PII | Contains data, grants, and metadata | Contains cluster data, potentially secrets |

A **complete logical dump is a valid backup** when restoring from that snapshot satisfies RPO and RTO. Saying "`pg_dump` is not a backup" is overly extreme; saying "having `pg_dump` gives you PITR" is also wrong.

## 4. What Does Data Export Mean?

Exporting data extracts a file or structured result set for interchange, ETL, reporting, or controlled synchronization.

Example:

~~~sql
SELECT
    order_id, customer_id, total_amount, created_at
FROM sales.orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
ORDER BY order_id;
~~~

### 4.1. Export contract

Document the column list and order, UTF-8 encoding, CSV/JSON format, delimiters, quoting rules, `NULL` representation, timezone conventions, decimal precision, pagination, query filters, and format version.

### 4.2. Exports do not embed database schema

A CSV knows nothing about table constraints, foreign keys, indexes, triggers, views, stored functions, sequences, identity columns, RLS policies, or role grants.

### 4.3. No automatic guarantee of system completeness

A `SELECT` with a `WHERE` clause only exports matching rows. Even an export containing every row of `orders` excludes customers, refunds, and audit events.

### 4.4. Appropriate use cases

Sharing data with partners, analytics, dashboards, loading data warehouses, sharing masked datasets, or migrating a set of records to another system under an explicit schema contract.

## 5. COPY and \copy Read/Write Files in Different Places

### 5.1. COPY TO a server-side file

~~~sql
COPY sales.orders (order_id, customer_id, total_amount)
TO '/srv/postgresql/exports/orders.csv'
WITH (FORMAT csv, HEADER true);
~~~

The path lives on **the PostgreSQL server filesystem**. Server-side file access is strictly privileged; applications should never receive broad server-file privileges just to write CSVs.

### 5.2. \copy in psql

~~~text
\copy (SELECT order_id, customer_id, total_amount FROM sales.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
~~~

This command belongs to **psql**, so the file resides on the machine running `psql`. It streams via the client `COPY` protocol; the database role still requires `SELECT` privilege.

### 5.3. COPY TO STDOUT

~~~sql
COPY (
    SELECT order_id, total_amount
    FROM sales.orders
    ORDER BY order_id
) TO STDOUT WITH (FORMAT csv, HEADER true);
~~~

Streams rows over the client protocol; the server does not write a local file on the user's machine itself.

### 5.4. COPY FROM STDIN

Accepts data streamed from the client. pgJDBC provides a dedicated `COPY` API for streaming large datasets cleanly outside `psql`.

### 5.5. Distinguish commands in documentation

`COPY` is SQL, whereas `\copy` is a `psql` meta-command. Never send a `\copy` string through a JDBC `PreparedStatement` expecting the PostgreSQL server to parse it as SQL.

## 6. CSV Export Example and Snapshot Semantics

Suppose we have this table:

~~~sql
CREATE SCHEMA sales;
CREATE TABLE sales.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

In `psql`:

~~~text
\copy (SELECT order_id, customer_id, total_amount, created_at FROM sales.orders ORDER BY order_id) TO 'orders-export.csv' WITH (FORMAT csv, HEADER true)
~~~

### 6.1. ORDER BY is required for deterministic order

Without `ORDER BY`, PostgreSQL makes no guarantee of primary-key order. Stable ordering simplifies file diffs and downstream processing.

### 6.2. NUMERIC exports as text

Numbers in CSV are textual representations; the importing target schema governs `NUMERIC` precision, scale, bounds, and rounding.

### 6.3. TIMESTAMPTZ formatting depends on session timezone

Two exports can format the exact same instant with different timezone offsets. Document the timezone convention explicitly, and never assume a timestamp string preserves an original `ZoneId`.

### 6.4. One export query sees one MVCC snapshot

However, **two separate export queries can see two different snapshots**. When consistency across multiple tables or files is required, design an explicit transaction/snapshot strategy or ETL synchronization mechanism.

## 7. Multi-Table Exports Can Be Inconsistent

~~~text
10:00   Export customers.csv  (snapshot S1)
10:01   Transaction updates customer and inserts order
10:02   COMMIT
10:03   Export orders.csv     (snapshot S2)
~~~

When re-imported, a new order can reference stale customer metadata from an earlier moment. Neither file is "corrupted," yet they represent different points in time.

### 7.1. MVCC does not synchronize separate files automatically

To hold one logical snapshot across exports, run them within an appropriate isolation level in one transaction or coordinate exported snapshots across clients where supported.

### 7.2. Long-running exports have operational impact

Holding a long snapshot pins old tuple versions, impeding `VACUUM` cleanup and driving bloat. For massive exports, consider incremental ETL or CDC with well-defined semantics.

### 7.3. External system boundaries

If orders reference objects in object storage or a payment provider, a PostgreSQL snapshot does not simultaneously capture the state of those external services.

## 8. Why Aren't CSVs Enough as Disaster Backups?

Suppose you only have:

~~~text
orders.csv
customers.csv
payments.csv
~~~

These files do not carry:

- `CREATE TABLE` definitions and exact column types.
- `PRIMARY KEY`, `UNIQUE`, `CHECK`, and `FOREIGN KEY` constraints.
- Sequence/identity states and index definitions.
- Triggers, functions, procedures, and materialized views.
- Role definitions, grants, and row-level security policies.
- Extension versions, collations, and tablespaces.
- Referential import ordering.
- WAL or timelines for point-in-time recovery near a failure.

### 8.1. Re-importing can trigger new side effects

`COPY FROM` passes through active constraints and triggers. If destination triggers publish events or write audit rows, reloading CSVs causes side effects unlike physical recovery.

### 8.2. Importing explicit IDs affects sequences

Reloading order IDs `1–10000` does not automatically advance target identity sequences past `10000`. After importing, inspect and synchronize ID generators to avoid primary-key collisions.

### 8.3. CSVs cannot prove full application recoverability

Matching `COUNT(*)` alone does not guarantee broken references, missing permissions, or application workflows will work.

## 9. What Is a Logical Dump?

A **logical dump** is a representation of database objects and data using SQL logic rather than copying raw PostgreSQL data pages.

Related tools:

- `pg_dump` — dumps a single database.
- `pg_dumpall` — generates SQL scripts for cluster databases and global objects depending on options.
- `pg_restore` — restores non-plain archives created by `pg_dump`.
- `psql` — executes plain-text SQL scripts.

### 9.1. A full dump contains far more than rows

Within the selected scope, it includes `CREATE TABLE`, `INDEX`, `VIEW`, constraints, functions, row data, ownership, and `GRANT` statements.

### 9.2. Logical dumps hold no WAL history

A logical dump captures a single snapshot, without a WAL stream to replay subsequent transactions.

### 9.3. Dumps aid migrations and rebuilds

Because objects are represented logically, dump/restore is often ideal for upgrading across PostgreSQL major versions when objects, extensions, and SQL features remain compatible.

### 9.4. Do not confuse with schema-only dumps

A `--schema-only` dump contains no row data; a `--data-only` dump cannot initialize schemas in an empty database by itself.

## 10. Example of a pg_dump Custom Archive

Terminal example for source database `trainingdb`:

~~~sh
pg_dump -h db.example.test -U backup_reader -d trainingdb -F c -f trainingdb.dump
~~~

### 10.1. -d selects exactly one database

`pg_dump` never dumps all databases in a cluster automatically.

### 10.2. -F c selects the custom archive format

Custom format embeds a Table of Contents (TOC), supporting selective object filtering and flexible restore workflows.

### 10.3. -f specifies the output artifact

Store artifacts on secured, encrypted filesystems or object storage with retention policies—never inside public web directories.

### 10.4. Never pass passwords on the command line

Avoid embedding production secrets in URIs or CLI flags where logs or process lists can leak them. Use interactive prompts, `.pgpass`, or secure secret injection.

### 10.5. Verify command exit status

Checking that a file exists is insufficient: verify exit status, `stderr`, job logs, and readability via `pg_restore` or a real restore test.

## 11. pg_dump Formats

| Format | Flag | Restore tool | Description |
|---|---|---|---|
| Plain SQL | `-F p` | `psql` | Plain-text SQL script |
| Custom | `-F c` | `pg_restore` | TOC-enabled archive, highly flexible |
| Directory | `-F d` | `pg_restore` | Directory archive suited for parallel workflows |
| Tar | `-F t` | `pg_restore` | Tar archive with specific limitations |

### 11.1. Plain SQL

~~~sh
pg_dump -d trainingdb -F p -f trainingdb.sql
psql -X -v ON_ERROR_STOP=1 -d training_restore -f trainingdb.sql
~~~

`-X` ignores user `.psqlrc` startup files; `ON_ERROR_STOP=1` halts immediately on SQL errors. Always restore into a properly prepared target database.

### 11.2. Custom

~~~sh
pg_dump -d trainingdb -F c -f trainingdb.dump
pg_restore --list trainingdb.dump
~~~

Use `pg_restore` to inspect and restore custom archives—not `psql -f`.

### 11.3. Directory

~~~sh
pg_dump -d trainingdb -F d -f trainingdb-directory
~~~

A directory archive spans multiple files; always copy the entire directory and its metadata together, never individual files alone.

### 11.4. Tar

~~~sh
pg_dump -d trainingdb -F t -f trainingdb.tar
~~~

Tar format carries differences and restrictions compared to custom/directory formats, notably around parallel restores. Never assume a `.tar` extension means you can untar it and start PostgreSQL directly like a physical backup.

### 11.5. Compression

Several formats and options support compression; available algorithms, levels, and compatibility depend on PostgreSQL/`pg_dump` versions. Compression saves storage while altering CPU load and restore duration.

## 12. pg_restore: Picking the Right Target and Contents

~~~sh
pg_restore --list trainingdb.dump
createdb training_restore
pg_restore -d training_restore trainingdb.dump
~~~

### 12.1. The target database usually must exist

Unless using database creation flags (`-C`) against a maintenance database, `-d` must point to an existing database.

### 12.2. --schema-only and --data-only

Useful when separating DDL from data loads. Neither alone counts as a complete database backup.

### 12.3. -n and -t

Allow restoring specific schemas or tables from an archive, though external dependencies outside your selection may not restore automatically.

### 12.4. -j parallel jobs

Supported archive formats allow parallelized restoration. This speeds up large database restores at the cost of extra connections, CPU, and disk I/O without guaranteed linear scaling.

### 12.5. --clean and --if-exists are highly destructive

`--clean` drops existing objects before recreating them; `--if-exists` does not render it harmless. Run them only after verifying host, target database, scope, and rollback options.

### 12.6. --no-owner and --no-acl

Helpful when migrating into environments with different roles, though omitting ownership and `GRANT`s changes the security posture. Always apply an explicit permissions plan afterward.

## 13. Consistent Snapshots in pg_dump

`pg_dump` uses a database snapshot to capture a transactionally consistent view even while concurrent writers update rows under MVCC.

~~~text
01:00  pg_dump acquires snapshot S
01:05  Writer INSERT orders #101 COMMIT
01:20  pg_dump continues dumping tables at snapshot S
01:40  pg_dump completes artifact
~~~

### 13.1. The dump does not reflect "01:40"

Even if the job finishes at 01:40, its contents reflect the earlier snapshot taken at 01:00 and exclude commits made afterward.

### 13.2. Does not block all DML

`pg_dump` runs safely alongside active OLTP reads and writes, though it acquires `ACCESS SHARE` locks that protect structures and can conflict with concurrent DDL.

### 13.3. Not a distributed system-wide snapshot

External services, other databases in the same cluster, and external files are not atomically captured at the same distributed timestamp.

### 13.4. Long-running snapshots have costs

A lengthy dump pins old tuple versions, delays `VACUUM` cleanup, increases bloat, and raises contention against schema migrations.

### 13.5. Sequences have special semantics

Sequence advances do not roll back like MVCC row mutations. When dumping and restoring active write workloads, verify sequence states before reopening application writes.

## 14. What pg_dump Omits Automatically

Running `pg_dump -d trainingdb` does not back up the whole cluster or its operational environment.

### 14.1. Global roles and passwords

Role definitions live cluster-wide; a database dump references owners and grantees without containing the cluster's complete `CREATE ROLE` definitions.

### 14.2. Tablespace definitions

Tablespace filesystem paths and privileges belong to the cluster level and may require recreation or remapping on target hosts.

### 14.3. Configuration and networking

Files like `postgresql.conf`, `pg_hba.conf`, TLS keys/certs, OS systemd units, DNS/firewalls, and external secrets sit outside logical dumps.

### 14.4. Extensions and external binaries

A dump emits `CREATE EXTENSION` statements, yet restoring requires compatible shared libraries and packages installed on the target OS/PostgreSQL build.

### 14.5. Large objects and filtering flags

Full database dumps typically include large objects per `pg_dump` semantics, whereas partial dumps with `-n`/`-t` flags may omit them unless requested explicitly. Verify scope rather than guessing.

### 14.6. Foreign tables, brokers, and object storage

Restoring SQL foreign-table definitions does not copy data residing in remote databases, message queues, or object storage buckets.

## 15. pg_dumpall for Cluster Globals

To dump global role and tablespace definitions:

~~~sh
pg_dumpall --globals-only -f globals.sql
~~~

### 15.1. Restore globals before databases when appropriate

If a database dump grants privileges to `app_reader`, that role must already exist on the destination cluster unless ownership/grants are stripped or remapped.

### 15.2. Globals contain sensitive security material

Password verifiers and authentication metadata are sensitive secrets. Protect globals dumps with strong encryption, tight IAM, and strict retention.

### 15.3. pg_dumpall outputs plain SQL

Both full `pg_dumpall` and `--globals-only` output plain SQL executed via `psql` with sufficient privileges—not custom archives for `pg_restore`.

### 15.4. No atomic cross-database snapshot

`pg_dumpall` dumps databases sequentially, meaning there is no single cluster-wide atomic MVCC snapshot across databases. Cross-database consistency requires separate coordination.

### 15.5. Rebuilding logical objects is not rebuilding infrastructure

You must still manage HA topology, endpoints, TLS certificates, tablespace directories, replication slots, WAL retention, and host config.

## 16. Can a Logical Dump Count as a Backup?

**Yes**, when aligned with explicit recovery objectives and verified through restore drills.

For instance, if the business tolerates up to 24 hours of data loss and a small database restores in tens of minutes, nightly offsite `pg_dump`s with integrity checks and tested restores can meet requirements.

### 16.1. Point-in-time constraints

If a dump snapshot ran at 01:00 and corruption hits at 16:00, the dump reflects only 01:00. You cannot use `pg_restore` to replay transactions up to 15:59 from a dump file alone.

### 16.2. Speed constraints

Logical restores must execute DDL, rebuild indexes, validate constraints, and load every row. At large scale, restore time can exceed RTO even when the dump is flawless.

### 16.3. Scope constraints

If your application relies on roles, extensions, local filesystem assets, secrets, and external services, include them in the full recovery plan.

### 16.4. Selective recovery advantage

Custom archives make extracting specific tables or spinning up shadow copies easier than physical restores, though external dependencies must still be checked carefully.

## 17. What Is a Physical Backup?

A **physical backup** copies underlying physical database files/pages using a protocol PostgreSQL can recover consistently, rather than generating SQL scripts.

Common methods:

- `pg_basebackup` over PostgreSQL's replication protocol.
- Filesystem or storage snapshots coordinated per PostgreSQL backup requirements.
- Dedicated backup managers coordinating full, differential, and incremental backups alongside WAL archives.

### 17.1. Never blindly copy a running data directory

Copying live files sequentially under active writes captures pages from mismatched moments in time. Without proper WAL and backup protocol coordination, the resulting copy may fail crash recovery completely.

### 17.2. Base backups are cluster-scoped

A physical backup covers the entire cluster—all databases and shared system catalogs—not a single selected table like `COPY`.

### 17.3. PostgreSQL major version dependency

Physical backups are tied to the internal binary/page layout of a specific PostgreSQL major version and architecture. Never use them as direct cross-major upgrades outside supported procedures.

### 17.4. Host layout and filesystem considerations

Check tablespace mount points, symlinks, file ownership, permissions, paths on the destination host, and free disk during restores.

## 18. pg_basebackup: Example

~~~sh
pg_basebackup -h primary.example.test -U backup_agent -D /backup/base-20261114 -F p -X stream -P
~~~

### 18.1. -D: target directory

Must point to an empty, suitably sized destination—never the `PGDATA` directory of a running primary.

### 18.2. -F p: plain physical format

Writes physical files directly into a directory hierarchy; `-F t` tar format follows separate extraction steps.

### 18.3. -X stream: streams WAL needed during the backup

Streams WAL generated while the base backup runs so the backup is self-consistent at completion. Having a consistent base backup **does not** archive subsequent WAL for future PITR.

### 18.4. -P: progress reporting

Displays terminal progress; it adds no extra durability guarantee.

### 18.5. Connection privileges

The backup role needs replication privilege, matching `pg_hba.conf` entries, and sufficient `max_wal_senders`; apply least privilege.

### 18.6. Post-backup verification remains mandatory

Command success is necessary, yet only real restores and validation checks prove recoverability.

## 19. How Does WAL Relate to Backups?

WAL (Write-Ahead Log) records changes prior to data-page flushes to power crash recovery and replication. It logs the physical and logical records needed to restore pages consistently.

~~~text
A transaction modifies a table
          |
          v
Records written to WAL
          |
          v
Commit / data pages flushed asynchronously
          |
          +------> Independent WAL archive
                         |
                         v
                 Replayed during recovery
~~~

### 19.1. WAL alone is not a full database copy

WAL segments by themselves cannot reconstruct tables and indexes without a starting baseline. PITR requires a **recoverable base backup** plus a continuous WAL chain up to the recovery target.

### 19.2. pg_wal on the primary is not an offsite archive

If the primary host or disk dies, WAL sitting only on `pg_wal` is lost too. Ship WAL to independent storage with retention and integrity verification.

### 19.3. A WAL archive must have zero gaps

If even one required WAL segment goes missing, replay stops before reaching your target. A valid base backup paired with a broken WAL chain fails PITR.

### 19.4. Retention applies to the entire backup chain

Retaining 30 days of base backups while deleting older WAL segments required by those backups breaks intermediate PITR points. Enforce chain-aware retention across base backups and WAL together.

### 19.5. Replication slots do not replace archiving

Slots hold WAL on the primary for active consumers without storing safe offsite copies. Abandoned slots can also fill primary disks indefinitely if unmonitored.

## 20. Continuous Archiving and Point-In-Time Recovery (PITR)

**PITR** (*point-in-time recovery*) restores a PostgreSQL cluster to a chosen recovery target by starting from a base backup and replaying archived WAL.

~~~text
00:00   Base backup B0
00:30   WAL archive W1
01:00   WAL archive W2
01:30   WAL archive W3
01:47   Accidental DELETE commits
02:00   Incident reported
            |
            v
     Restore B0 in an isolated secondary cluster
            |
            v
     Replay WAL just before the DELETE
            |
            v
     Inspect data and execute controlled cutover
~~~

### 20.1. Targets must be specified unambiguously

A local timestamp without a timezone offset is ambiguous. Always specify timezone offsets and cross-check transaction commit logs before choosing a target.

### 20.2. PITR operates at the cluster level

You cannot apply WAL directly to "undo one row" inside live production. For a dropped table or accidental delete, recover **a separate cluster** just prior to the mistake, extract the lost rows, and carefully reconcile them back into production.

### 20.3. You cannot selectively skip arbitrary committed transactions in WAL

PostgreSQL WAL replay is sequential recovery, not a filter that drops one middle transaction while cleanly replaying dependent later transactions.

### 20.4. Cluster timelines

Promotions and failovers advance PostgreSQL to a new timeline ID; recovery tooling must follow the proper timeline history rather than mixing segments across branches.

### 20.5. "PITR works" must be rehearsed

Maintain a documented procedure to retrieve artifacts, boot an isolated cluster, replay WAL, validate data, promote safely, and switch application traffic cleanly.

## 21. Recovery Configuration Illustration

In modern PostgreSQL versions, recovery uses `recovery.signal` alongside runtime recovery parameters. The snippet below is **conceptual only**, not a copy-paste production guide:

~~~conf
restore_command = 'command-to-fetch-archived-wal %f %p'
recovery_target_time = '2026-11-14 10:00:00+07'
recovery_target_action = 'pause'
~~~

### 21.1. restore_command is a placeholder

`command-to-fetch-archived-wal` is illustrative. In production, substitute a hardened retrieval command that handles WAL filenames, verifies downloads, logs errors, and exits non-zero cleanly when files are absent.

### 21.2. recovery.signal

Follow instructions matching your running PostgreSQL version; never blindly apply legacy `recovery.conf` instructions from very old PostgreSQL versions to modern clusters.

### 21.3. Pause vs. promote

Pausing at a target to inspect data differs from immediately promoting a new writable primary. Cutovers must prevent split-brain where applications write to two primaries at once.

### 21.4. Never experiment inside the live primary's data directory

Misplacing signal files or starting against live directories risks corruption or downtime. Always recover in a completely isolated directory, port, and network.

### 21.5. Fail safely when WAL is missing

Recovery automation must fail loudly if an archive segment is missing or a target cannot be reached—never silently declare success merely because PostgreSQL started at an earlier LSN.

## 22. Can a Physical Base Backup Restore Without PITR?

Yes: a self-contained base backup (for instance, with `-X stream`) includes enough WAL to start consistently at backup completion time, even without subsequent archived WAL for arbitrary later targets.

### 22.1. Two distinct capabilities

- **Restoring a base backup:** recovers to the consistent point captured by the backup itself.
- **PITR:** recovers to any specific point across an archived WAL history window.

### 22.2. Without post-backup WAL

With only a 01:00 base backup and zero archived WAL afterward, you cannot recover to 13:59.

### 22.3. Daily full backups alone cannot guarantee a low RPO

If business RPO is 5 minutes, nightly full backups cannot meet it. Continuous WAL archiving or synchronous replication architectures are required.

### 22.4. WAL archiving is not instantaneous

Archived segments wait until a WAL file fills or `archive_timeout` fires, plus network transfer time. Actual RPO reflects whichever WAL reached durable offsite storage before the crash.

## 23. Does a Storage-Layer Snapshot Count as a Backup?

Yes—**if** the snapshot procedure guarantees PostgreSQL crash/backup consistency and covers every required storage component atomically.

### 23.1. Atomic snapshots

All volumes holding `PGDATA`, tablespaces, and needed WAL must be snapshotted consistently at the same instant or coordinated via PostgreSQL backup APIs.

### 23.2. Snapshotting one volume while missing a tablespace

If a database puts a tablespace on a separate volume, snapshotting only `PGDATA` omits critical datafiles.

### 23.3. Snapshotting a live PostgreSQL instance

Understand crash consistency, WAL alignment, checkpoints, and storage-provider guarantees. Plain file-by-file copies or WAL-less snapshots are not valid backups.

### 23.4. Local snapshots share failure domains

Snapshots stored in the same storage account or host that fails or gets compromised alongside the primary cannot protect against disaster or ransomware. Replicate copies offsite with isolated IAM.

### 23.5. Snapshots and logical exports operate at different layers

Storage snapshots do not replace partner CSV exports, and CSVs do not replace cluster snapshots.

## 24. Incremental and Differential Backups

Many PostgreSQL deployments use incremental or differential backups to trim backup sizes and transfer times. Native incremental backup support and tools like `pg_combinebackup` depend on PostgreSQL version, while external backup tools implement their own chain formats.

### 24.1. Full backup

Captures a complete baseline. Easiest to restore standalone, though heaviest in disk and copy time.

### 24.2. Incremental

Stores only blocks/changes modified since the preceding reference backup per the tool's design. Restoring requires the entire chain from base forward; losing one link breaks recovery.

### 24.3. Differential

Often captures changes relative to the last full backup. Do not assume every backup product defines incremental and differential identically.

### 24.4. Never mistake small size for standalone completeness

A 500 MB incremental file cannot restore a 2 TB cluster without its full baseline and intermediate links.

### 24.5. Define chain-aware retention

Never expire a base backup while newer incrementals still depend on it. Manage manifests, catalogs, checksums, and retrieval SLAs across storage tiers.

## 25. RPO and RTO Are Independent Objectives

**RPO — Recovery Point Objective:** maximum acceptable data loss, typically measured as the time gap between the recovered state and the incident.

**RTO — Recovery Time Objective:** maximum acceptable downtime to restore the service after an incident.

### 25.1. Example

~~~text
Backup snapshot:       01:00
Incident occurs:       13:00
Recovery completes:    15:30

Recent data lost:      12 hours (back to 01:00 backup)
Recovery duration:     2 hours 30 minutes
~~~

If the business targets a 15-minute RPO and a 1-hour RTO, this setup misses both.

### 25.2. Actual RPO differs from nominal targets

Turning on WAL archiving does not instantly put every transaction offsite. Measure real archive lag and verify the latest WAL is durable and replayable.

### 25.3. RTO spans every recovery step

Downloading artifacts, decrypting, provisioning servers, restoring files, replaying WAL, rebuilding indexes (for logical restores), running migrations, checking invariants, repointing endpoints, and validating app traffic all consume RTO.

### 25.4. RPO = 0 is demanding

Asynchronous WAL archiving cannot guarantee zero transaction loss. Achieving zero data loss requires synchronous replication/HA architecture under a clear threat model, paired with independent historical backups.

### 25.5. RPO and RTO do not substitute for each other

Taking backups every 5 minutes does not prove you can restore within 5 minutes. Conversely, fast replica failover does not restore accidentally deleted data or replace historical backups.

## 26. Selecting Solutions by RPO/RTO

| Need | Reference approach | Key measurement |
|---|---|---|
| Share data with a partner | CSV/JSON export | Contract conformance and quality |
| Move selected tables | `COPY`/ETL or selective `pg_dump` | Dependencies, schema, validation |
| Upgrade database major version | Logical dump/restore | Compatibility, downtime |
| Restore small DB to last night | Full `pg_dump` + globals | Restore speed, acceptable data loss |
| Rebuild large cluster after disk loss | Physical base backup | Provisioning, WAL, disk/network I/O |
| Recover right before an accidental delete | Physical backup + WAL/PITR | Target accuracy, unbroken WAL chain |
| Survive primary host outage quickly | HA standby promotion | Actual RTO, clean failover |
| Protect against deletes replicating to standby | Independent historical backups | Retention depth, PITR availability |
| Defend against ransomware/storage compromise | Offsite immutable backups | Delete permissions, key availability |

### 26.1. Combining multiple layers

Large systems commonly combine physical base backups + WAL for PITR, logical dumps for migrations/table extracts, and CSV exports for analytics.

### 26.2. Never choose by tool name alone

Test actual recovery scenarios against business requirements rather than trusting a "backup job succeeded" badge.

## 27. High Availability Is Not Automatically a Backup

Streaming replication keeps standbys synchronized with the primary—meaning a `DROP TABLE` on the primary replays onto the standby as well, deleting the table on both.

### 27.1. Replication copies mistakes alongside valid writes

Accidental deletes, bad `UPDATE`s, broken DDL, and application corruption propagate straight to replicas.

### 27.2. Standby promotion serves availability

Failover slashes RTO when hardware dies, without providing historical rollback points for PITR.

### 27.3. Logical replication is also not a backup

Logical replication helps migrations and integration, yet does not automatically replicate roles, DDL, extension binaries, sequences, or cluster-wide backup semantics.

### 27.4. Taking backups from a standby

Offloading backups to a standby reduces primary load depending on tooling and configuration, provided snapshot consistency, WAL/timeline continuity, and lag bounds are handled cleanly. Never assume copying files off a standby works unconditionally.

## 28. Version and Architecture Compatibility

### 28.1. pg_dump and source server versions

`pg_dump` generally supports dumping older server versions within compatibility limits, while overly old `pg_dump` binaries should not dump newer servers. Check your exact PostgreSQL tool compatibility matrix.

### 28.2. Logical dumps to newer servers

Logical SQL works well for major upgrades, yet deprecated syntax, extensions, collations, and privileges can still break. Always run migration rehearsals.

### 28.3. Physical backups

Require matching binary/on-disk format, PostgreSQL major version, checksum configuration, CPU architecture, and tablespace layout. Never boot a newer major binary against an older `PGDATA` backup directly.

### 28.4. Encoding, locale, and collations

Unicode dumps can still hit sort-order or uniqueness issues if OS libc/ICU collations differ between source and destination. Inspect affected indexes and constraints and plan reindexing where needed.

### 28.5. Extensions

A dump containing `CREATE EXTENSION` fails on restore if the target server lacks the matching extension binaries or version. Inventory extensions before migrating or restoring.

## 29. A Complete Backup File Differs From a Usable Backup

A backup file may sit on disk yet fail because it was:

- Written by an aborted job.
- Truncated due to full storage.
- Corrupted during upload.
- Encrypted with a lost key.
- Missing files inside a directory archive.
- Missing WAL segments needed for PITR.
- Incompatible with the target version.
- Missing roles, grants, or extension libraries.
- Stored on the same failed disk as the primary.

### 29.1. Integrity is not recoverability

Matching SHA-256 checksums prove bytes weren't altered; **they do not prove the database restores and serves traffic**.

### 29.2. pg_restore --list

Verifies that a custom archive's TOC can be parsed:

~~~sh
pg_restore --list trainingdb.dump
~~~

A useful smoke check, but never a substitute for restoring.

### 29.3. pg_verifybackup

On physical backups with manifests, `pg_verifybackup` validates the manifest and file checksums within tool scope. It cannot verify host bootability, downstream WAL retention, or application correctness.

### 29.4. Restore drills provide stronger proof

Standing up an isolated PostgreSQL instance from artifacts, running validation queries, and verifying business invariants proves far more than file checksums.

## 30. Operational Backup Metadata and Manifests

Track external metadata for every backup artifact:

| Field | Example | Purpose |
|---|---|---|
| Backup ID | `pg-base-20261114-001` | Traceability |
| Scope | `cluster/orders-db` | Protected scope |
| Type | logical / physical / incremental | Restore path |
| Start/end | Timezone-aware timestamps | Job lifecycle |
| Snapshot/consistent point | LSN/time metadata | Recovery reference |
| PostgreSQL version | Major/minor | Compatibility |
| Tool version | `pg_dump`, backup manager | Reproducibility |
| WAL/timeline coverage | LSN/timeline range | PITR eligibility |
| Storage URI | Private object storage path | Retrieval |
| Encryption key reference | Key ID (never raw key) | Decryption |
| Checksum/manifest | Digest inventory | Integrity |
| Last restore test | Outcome and timestamp | Proven recoverability |

### 30.1. Never put secrets inside manifests

Manifests must never store plaintext database passwords, storage tokens, IAM secrets, or raw encryption keys.

### 30.2. File mtime is not snapshot time

A 40-minute dump finishes with a file creation/modification timestamp long after the logical snapshot point. Record exact snapshot metadata separately.

### 30.3. Version-control restore runbooks

If recovery steps live solely in one DBA's head, RTO collapses whenever that person is unreachable.

## 31. Retention and Multi-Copy Policies

### 31.1. A single copy on the primary host is a severe risk

If the host dies or storage fails, `/backup` on the same machine vanishes alongside the database. Keep offsite/cross-zone copies matched to your threat model.

### 31.2. The 3-2-1 guideline

Maintain multiple copies across different storage media/domains with at least one offsite copy. Tune exact copy counts to compliance requirements, data volume, cost, and threat models.

### 31.3. Immutable and append-only backups

Prevent compromised production credentials from deleting historical backups. Separate IAM roles cleanly for backup writers, restore readers, and deletion admins.

### 31.4. Retention must respect WAL chains

Never purge WAL segments still needed by active base backups or PITR recovery windows. Enforce dependency-aware retention.

### 31.5. Delete permissions and encryption keys

If an attacker can wipe backups or destroy KMS keys—or keys are simply lost—recovery fails. Separate key governance and test key retrieval during disaster drills.

## 32. Security Risks of Exports and Dumps

### 32.1. CSVs contain PII

Exports holding names, emails, addresses, or transaction IDs are sensitive assets. Never drop them onto public sharing buckets simply because they are "reporting files."

### 32.2. Plain SQL dumps may contain embedded secrets

API keys, token hashes, session records, or configuration tables end up inside dumps unless excluded. Never commit dumps to Git, public CI artifacts, or support tickets.

### 32.3. Globals carry authentication metadata

`pg_dumpall --globals-only` can expose password verifiers; encrypt and restrict it like secret material.

### 32.4. Restores execute arbitrary SQL

Plain SQL dumps can define functions, alter roles, and execute DDL. Restore only trusted artifacts into intended targets, avoiding superuser execution when unnecessary.

### 32.5. Test restores require masking and isolation

A restored production clone containing real PII remains sensitive production data. Test environments require network isolation, RBAC, short retention, and masking per policy.

## 33. Incident Scenarios and Recovery Choices

### 33.1. Lost partner CSV export

Re-run the export query against the requested snapshot window if source rows remain intact. No cluster restore needed.

### 33.2. Accidentally deleted 10 rows with last night's logical dump available

Restore the dump into a scratch database, extract the 10 rows by primary key, and reconcile carefully into production—never overwrite production wholesale and wipe newer valid transactions.

### 33.3. Accidentally dropped table with PITR enabled

Spin up a secondary cluster via PITR targeting just before `DROP TABLE`, verify the extracted data, and merge it into production under a controlled plan.

### 33.4. Total cluster storage failure

Recover from physical base backup + WAL (or logical dump + globals if scope and RTO permit). Re-provision PostgreSQL, roles, endpoints, and applications.

### 33.5. Ransomware wipes on-host backups

Local copies alone leave nothing to recover. Offsite immutable storage with isolated credentials saves the cluster.

### 33.6. Failed schema migration

Pre-migration backups recover cleanly in isolated scratch instances, yet if live writes occurred after migration started, rolling back the whole DB loses newer valid orders. Maintain migration rollback and reconciliation protocols.

## 34. Roadmap for Restoring a Database From a Logical Dump

~~~text
Select artifact and identify snapshot
              |
              v
Spin up isolated PostgreSQL environment
              |
              v
Prepare versions, extensions, roles
              |
              v
Create clean target database
              |
              v
psql or pg_restore
              |
              v
Check errors, indexes, constraints
              |
              v
Verify row counts, invariants, queries
              |
              v
Measure RPO/RTO, decide cutover
~~~

### 34.1. Never test-restore directly onto production

If a backup is corrupt and you run `--clean` against production, you destroy existing data before learning the restore failed.

### 34.2. Restoring globals can require elevated privileges

Execute only inside dedicated isolated clusters; never replay role/superuser statements blindly into a shared multi-tenant cluster.

### 34.3. Schema-only or data-only is not a full restore

A complete recovery restores both structures and data alongside external dependencies.

### 34.4. Verify permissions and data health

Confirm service roles hold proper `SELECT`/`INSERT` privileges, indexes exist, sequences will not collide, and extension functions run properly.

## 35. Roadmap for Restoring a Physical Cluster

~~~text
Select base backup and recovery target
              |
              v
Verify complete WAL/timeline chain
              |
              v
Provision compatible host/storage/version
              |
              v
Decrypt/download/restore physical files
              |
              v
Configure WAL restore and recovery target
              |
              v
Start PostgreSQL on isolated network
              |
              v
Replay WAL and inspect recovery state
              |
              v
Verify data, extensions, roles, services
              |
              v
Promote and cut over cleanly
~~~

### 35.1. Database restore alone is not full application recovery

Endpoints, TLS certs, proxies, DNS, external integrations, and secret distribution must also be restored or repointed.

### 35.2. Version compatibility is mandatory

Physical backups cannot upgrade across PostgreSQL major versions. Use supported upgrade procedures or logical migration when moving major versions.

### 35.3. Keep a rollback plan

If post-restore checks fail, retain a clean path back to pre-cutover state without causing split-brain or misrouted writes.

## 36. Notes on Taking Backups From Standbys and Replicas

Offloading backups to a standby reduces primary load depending on setup and tooling, provided you verify:

- Exactly what point in time the backup recovers to.
- Compatibility of WAL archives with timeline and replay positions.
- Complete inclusion of filesystem and tablespace components.
- How standby lag shifts the achievable recovery point.
- How failover/promotion alters timelines and WAL archival.

### 36.1. Replicas do not retain infinite history

A standby replays committed primary changes; valid SQL deletes erase data on both nodes.

### 36.2. Never hot-copy files casually off a standby

Use official backup protocols or properly coordinated snapshots. A standby replaying WAL is actively mutating files on disk.

### 36.3. Choose backup sources purposefully

Choosing primary vs. standby involves consistency, network bandwidth, resource contention, and RPO—not merely connection count.

## 37. When to Use Physical Recovery vs. Logical Restoration?

| Decision factor | Logical | Physical |
|---|---|---|
| Recover one dropped table | Usually easier | Requires restoring a secondary cluster |
| Major PostgreSQL version upgrade | Typically suited | Cannot reuse raw `PGDATA` across majors |
| Very large dataset needing fast RTO | Rebuilding rows/indexes can take too long | Often faster depending on storage/network |
| PITR to exact moment before mistake | Impossible from dump alone | Base backup + WAL |
| Single-database scope | Fits directly | Backs up entire cluster |
| Global roles and server configs | Must track separately | Roles in catalog; external configs still separate |
| Ad-hoc query export | No full dump needed | Not applicable |
| Exact physical cluster restoration | Logical SQL rebuild, not byte copy | Built specifically for this |

### 37.1. No single tool wins every scenario

Production platforms often run both: physical backups + WAL for DR/PITR alongside logical dumps for upgrades/table extraction and CSV exports for analytics.

### 37.2. Benchmark on realistic data volumes

RTO measured on a 10 MB test database cannot be extrapolated linearly to a 2 TB cluster with large indexes, extensions, and heavy traffic.

## 38. Integrated Lab: Preparing a Test Environment

**Never run labs in production.** These examples use an isolated database, assuming you hold privileges to create test databases and schemas. If names collide with existing objects, choose distinct names rather than dropping anything.

In a terminal with appropriate credentials:

~~~sh
createdb backup_lab
psql -d backup_lab
~~~

Inside `psql`, create the schema and tables:

~~~sql
CREATE SCHEMA training;

CREATE TABLE training.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE training.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES training.customers(customer_id),
    amount NUMERIC(18,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX orders_customer_created_idx
ON training.orders (customer_id, created_at);
~~~

### 38.1. Insert sample data

~~~sql
INSERT INTO training.customers(customer_name)
VALUES ('Nguyễn An'), ('Trần Bình');

INSERT INTO training.orders(customer_id, amount, status)
SELECT customer_id, 125.50, 'new'
FROM training.customers
WHERE customer_name = 'Nguyễn An';

INSERT INTO training.orders(customer_id, amount, status)
SELECT customer_id, 400.00, 'paid'
FROM training.customers
WHERE customer_name = 'Trần Bình';
~~~

### 38.2. Why include foreign keys and indexes?

The lab intentionally includes structures a plain CSV cannot capture automatically: `UNIQUE`, `FK`, `CHECK`, identity columns, and indexes. This highlights the contrast between exports and dumps.

### 38.3. Verify baseline data

~~~sql
SELECT
    count(*) AS order_count,
    sum(amount) AS sum_amount
FROM training.orders;

SELECT c.customer_name, o.order_id, o.amount, o.status
FROM training.orders AS o
JOIN training.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Record these results to compare after restoring, without treating count and sum as the only proof needed.

## 39. Lab: Exporting orders.csv

In `psql` connected to `backup_lab`:

~~~text
\copy (SELECT order_id, customer_id, amount, status, created_at FROM training.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
~~~

### 39.1. Where is the file saved?

In the working directory where `psql` runs—not on the database server if `psql` connects remotely.

### 39.2. What does it contain?

Only the CSV header and rows from the `SELECT` query—zero `CREATE TABLE`, FK, or index definitions.

### 39.3. Confirm schema is absent from the CSV

Inspect the file in a text editor: there is no SQL DDL capable of rebuilding the PostgreSQL table faithfully.

### 39.4. Exporting one table leaves parents behind

`training.customers` is absent from `orders.csv`. Importing orders into a fresh FK-enforced schema requires loading customers first or staging appropriately.

### 39.5. Never copy real production PII into labs casually

This lab uses synthetic names; for real data, enforce masking or synthetic fixtures and restrict file permissions.

## 40. Lab: Importing CSV Into a Staging Table

In the test database, create a staging table for the CSV:

~~~sql
CREATE TABLE training.orders_imported (
    order_id BIGINT,
    customer_id BIGINT,
    amount NUMERIC(18,2),
    status TEXT,
    created_at TIMESTAMPTZ
);
~~~

In `psql`:

~~~text
\copy training.orders_imported (order_id, customer_id, amount, status, created_at) FROM 'orders.csv' WITH (FORMAT csv, HEADER true)
~~~

### 40.1. COUNT and SUM check

~~~sql
SELECT
    count(*) AS rows_imported,
    sum(amount) AS amount_imported
FROM training.orders_imported;
~~~

### 40.2. Why weren't foreign keys created automatically?

Only your `CREATE TABLE` statement defines constraints. `\copy` never infers primary keys, foreign keys, or `NOT NULL` rules from a CSV.

### 40.3. Two copies can coexist unlinked

A staging table does not automatically synchronize with production tables. Partial recoveries require explicit validation, merging, and conflict resolution.

### 40.4. NULL vs. empty string

In CSV mode, distinguishing `NULL` from empty strings depends on quoting and `COPY` options. Stick to an explicit format contract so semantics don't shift.

### 40.5. CSV formula injection

If exported CSVs are opened in spreadsheet tools, values starting with formula prefixes can execute formulas upon opening. Sanitize spreadsheet-bound exports appropriately without mangling values needed for PostgreSQL re-imports.

## 41. Lab: Creating a Custom Logical Dump

Exit `psql` and run in your terminal:

~~~sh
pg_dump -d backup_lab -F c -f backup_lab.dump
~~~

### 41.1. Database scope

This dumps only `backup_lab`, omitting other databases and cluster-wide roles.

### 41.2. Archive holds objects and data

Within the dump scope, it includes DDL for schemas, tables, indexes, and constraints alongside row data.

### 41.3. Inspect the Table of Contents

~~~sh
pg_restore --list backup_lab.dump
~~~

You will see a listing of archived objects. Remember that reading the TOC checks archive readability, **not recoverability**.

### 41.4. Note that the dump includes staging too

Because `orders_imported` existed before `pg_dump` ran, it gets included too. To keep artifacts clean, dump prior to temporary staging steps or filter scope explicitly.

### 41.5. Record manifest metadata

Log database name, server major version, `pg_dump` version, snapshot/job timestamp, and file checksum in a separate backup manifest.

## 42. Lab: Restoring a Custom Dump Into a New Database

In your terminal:

~~~sh
createdb backup_lab_restored
pg_restore --exit-on-error --no-owner --no-acl -d backup_lab_restored backup_lab.dump
~~~

### 42.1. Why use --no-owner and --no-acl in the lab?

To avoid failing on missing source roles when restoring in a sandbox. Note that **this alters the security state**, so it never proves production permissions were faithfully restored.

### 42.2. Why use --exit-on-error?

Ensures any failed SQL command halts immediately instead of continuing silently and leaving a broken restore marked successful.

### 42.3. Verify schema and counts

~~~sh
psql -d backup_lab_restored
~~~

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'training'
ORDER BY table_name;

SELECT count(*), sum(amount)
FROM training.orders;
~~~

### 42.4. Verify constraints

Inside `psql`:

~~~text
\d+ training.orders
~~~

Inspect `PRIMARY KEY`, `FK`, `CHECK`, indexes, and defaults/identity properties—don't stop at row counts.

### 42.5. Verify joins

~~~sql
SELECT c.customer_name, count(o.order_id), sum(o.amount)
FROM training.customers AS c
LEFT JOIN training.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

### 42.6. Verify ID generation

Inserting a test row inside the restored lab database confirms identity sequences advance cleanly without primary-key collisions (do this only in test databases).

## 43. Lab: Plain SQL Dump vs. Archive

~~~sh
pg_dump -d backup_lab -F p -f backup_lab.sql
createdb backup_lab_plain
psql -X -v ON_ERROR_STOP=1 -d backup_lab_plain -f backup_lab.sql
~~~

### 43.1. Plain SQL is human-readable text

It contains SQL DDL and load statements, though it lacks the TOC, selective restoration, and parallel restore advantages of custom/directory formats.

### 43.2. pg_restore does not read plain dumps

`pg_restore` handles archive formats; use `psql` for plain SQL scripts.

### 43.3. Mind your command shell

The commands above run in a shell one by one. Under PowerShell or bash, invoke CLI binaries cleanly without mistaking SQL inside `.sql` files for shell commands.

### 43.4. Never treat plain SQL dumps as untrusted-safe

SQL scripts can define functions and alter objects. Restore only trusted files into verified targets.

## 44. Lab: Dumping a Single Schema and What Gets Missed

~~~sh
pg_dump -d backup_lab -F c -n training -f training_schema.dump
~~~

### 44.1. Filtering narrows scope

However, cross-schema dependencies are not guaranteed to follow. If a table inside `training` references an enum, function, or extension in another schema, restoring `training` alone can fail on missing dependencies.

### 44.2. Does not replace a full database backup

A schema dump omits objects in other schemas as well as cluster globals.

### 44.3. Extracting a single table

You can use `-t` or selective `pg_restore`; always review related tables and constraints beforehand.

### 44.4. Never blindly push partial restores into production

A table may have inbound FKs, event-emitting triggers, or shared sequences. Restoring one table in isolation risks breaking business invariants.

## 45. Lab: Inventorying Globals Without Printing Secrets

In a test environment with suitable privileges:

~~~sh
pg_dumpall --globals-only -f globals-backup.sql
~~~

### 45.1. Scope

Captures `CREATE ROLE`, `ALTER ROLE`, tablespaces, and global definitions depending on options and version—not database table rows.

### 45.2. File access controls

Because the output can include password verifiers and auth metadata, never print the file to logs, chat messages, or CI artifacts, and restrict read access strictly.

### 45.3. Evaluate before restoring globals

Never blindly replay globals onto a cluster with pre-existing roles. Production restores need deliberate ownership/security plans and isolated environments.

### 45.4. Database dumps and globals dumps are separate artifacts

Keep matching globals paired with their database dumps so permissions stay aligned during full rebuilds.

## 46. Lab: Physical Base Backups and Manifest Verification

On an authorized backup host with independent storage, an illustrative command looks like:

~~~sh
pg_basebackup -h primary.example.test -U backup_agent -D /backup/base-test -F p -X stream -P
~~~

### 46.1. Never target a live data directory

`/backup/base-test` is a clean lab destination directory. Never point `-D` at an active cluster's `PGDATA`.

### 46.2. Connection prerequisites

The role needs replication privileges and matching HBA rules; the backup host needs sufficient storage, network reachability, and compatible PostgreSQL version tools.

### 46.3. Manifests

On PostgreSQL versions supporting backup manifests, `pg_basebackup` generates a manifest verifiable via:

~~~sh
pg_verifybackup /backup/base-test
~~~

### 46.4. pg_verifybackup is not a restore drill

Manifest checks verify file lists and checksums within tool limits, without proving bootability, application queries, external dependencies, or post-backup WAL archival.

### 46.5. Rehearse physical recovery in isolation

Because physical backups clone the entire cluster, restore drills must use isolated hosts/directories matching the PostgreSQL major version—never test by overwriting production.

## 47. What Proves a Backup Is Truly "Recoverable"?

A backup meets recovery criteria only when all of these hold evidence:

1. **Complete artifact:** archives or chains can be read end-to-end.
2. **Accessible:** storage, network, IAM permissions, and decryption keys remain available when the primary is gone.
3. **Software-compatible:** matching PostgreSQL and extension/runtime versions can load it.
4. **Complete scope:** objects, roles, tablespaces, WAL, and external dependencies are accounted for.
5. **Correct recovery point:** restored state meets the target RPO.
6. **Timely:** full end-to-end recovery finishes within RTO.
7. **Business-valid:** applications run cleanly and data passes constraint and reconciliation checks.
8. **Repeatable runbook:** operators can execute recovery without relying on one person's tribal memory.

### 47.1. Yesterday's valid backup may fail today

Adding a new tablespace, extension, or database can render old backup scripts incomplete. Re-verify backup scope whenever architecture evolves.

### 47.2. Succeeding after missing RTO still fails the goal

If business RTO is 30 minutes and restoration takes 6 hours, intact files still fail disaster recovery requirements.

### 47.3. Restore drills must not oversimplify failures

Copying a local backup on the same host does not test surviving host or region loss. Rehearse against realistic failure conditions.

### 47.4. Log every drill outcome

Record backup ID, recovery target, restore timestamp, download/decryption/startup timings, errors, checks, operator roles, and runbook updates.

## 48. Multi-Layered RPO/RTO Architecture Example

Suppose an e-commerce platform maintains:

- Daily CSV exports for reporting.
- Nightly full `pg_dump`.
- Daily physical base backup.
- Continuous WAL archiving with lag alerts.
- Hot standby in another availability zone.
- Offsite immutable backup copies.

### 48.1. CSV serves analytics

Never rely on CSV exports for cluster recovery.

### 48.2. pg_dump serves logical recovery

Ideal for extracting an accidentally dropped table or handling major upgrades, with RPO bounded to the dump snapshot.

### 48.3. Base backups + WAL power PITR

Handles data corruption or accidental deletes needing recovery to a precise moment, provided the WAL chain is intact.

### 48.4. Standbys serve high availability

Minimizes downtime upon primary host failure, though standbys replay bad mutations too and never replace backup history.

### 48.5. Offsite immutable copies defend against destruction

Prevents backups from being deleted alongside compromised primaries, provided key retrieval, download bandwidth, and restore timings are tested.

### 48.6. Do not blindly conflate RPOs across scenarios

Actual RPO varies by incident: host hardware failure uses the standby; widespread logical corruption uses PITR. Define explicit RPO/RTO targets per failure mode.

## 49. Recovering a Single Accidentally Dropped Table

### 49.1. Do not rush to roll back all of production to yesterday

Doing so wipes valid recent transactions across every unaffected table.

### 49.2. Spin up a shadow database from a logical dump

If a recent dump covers the needed table, restore it into `restore_tmp`, export the missing table cleanly, and merge into production under review.

### 49.3. Spin up a shadow cluster using PITR

When you need state right before `DROP TABLE`, restore a secondary cluster from base backup + WAL to that exact target, inspect the table, and extract only the rows needed.

### 49.4. Reconciliation matters

If other tables (`customers`, `payments`, child records, or external events) kept changing after the incident, blindly re-inserting rows risks duplicate charges or broken foreign keys. Follow strict merge rules.

### 49.5. Resynchronize sequences after import

Whenever inserting explicit primary keys back in, inspect and advance sequences/identities before reopening writes.

### 49.6. Preserve audit trails

Document incident repairs—including operator, scope, and justification—per governance policy.

## 50. Sample Disaster Recovery Runbook

### Phase A — Assess the Incident

- Classify failure: host loss, accidental delete, data corruption, ransomware, or app bug.
- Freeze further damaging writes where necessary.
- Determine recovery target, timeline, and scope.
- Confirm target RPO and RTO.

### Phase B — Select Artifacts

- Verify backup ID, job completion, and manifest/checksums.
- Verify continuous WAL/timeline coverage (for PITR).
- Confirm availability of globals/roles, tablespaces, extension packages, and configs.
- Confirm storage and decryption keys are accessible independently of the primary.

### Phase C — Provision Environment

- Provision compatible PostgreSQL versions.
- Isolate networks, ports, and credentials to prevent writing onto production.
- Prepare filesystem ownership, mount paths, and tablespaces.
- Download and decrypt artifacts under authorized access.

### Phase D — Restore

- Logical: create clean target database, run `psql`/`pg_restore`, and record all logs/errors.
- Physical: restore base backup, configure WAL retrieval and target, start PostgreSQL in isolation.
- Track progress, disk/CPU/network metrics, and errors.
- Promote or cut over only upon incident commander approval.

### Phase E — Verify

- Check row counts and business totals.
- Verify FK, unique, and check constraints along with indexes.
- Confirm sequences/identities won't generate duplicate keys.
- Inspect roles, ownership, RLS policies, extensions, and grants.
- Validate application connectivity and end-to-end read/write flows.
- Record actual recovered timestamp and downtime duration.

### Phase F — Reopen Traffic and Monitor

- Allow writes only after confirming a single authoritative primary.
- Update endpoints, connection pools, and secrets as needed.
- Watch error logs, replica lag, and downstream reconciliation backlogs.
- Document postmortem findings, refine the runbook, and schedule the next drill.

## 51. Common Misconceptions

### 51.1. "A CSV containing all rows is a full database backup"

**False.** It lacks schemas, grants, WAL, and numerous dependencies.

### 51.2. "COPY TO '/path' writes to the user's laptop"

**False.** Server-side paths write on the PostgreSQL server host; `\copy` writes on the `psql` client host.

### 51.3. "psql \copy is SQL runnable from JDBC"

**False.** It is a `psql` client meta-command.

### 51.4. "Two consecutive CSV exports automatically share one snapshot"

**False.** Separate statements can acquire different snapshots.

### 51.5. "pg_dump -d db1 also backs up db2"

**False.** It dumps only the specified database.

### 51.6. "pg_dump -Fc produces plain-text SQL"

**False.** It produces a custom archive restored via `pg_restore`.

### 51.7. "pg_restore reads any .sql file"

**False.** Plain SQL scripts run via `psql`; filenames do not dictate format.

### 51.8. "pg_dumpall guarantees an atomic snapshot across all databases"

**False.** It dumps databases sequentially at potentially different points in time.

### 51.9. "pg_dump backs up all cluster users and server configs"

**False.** Globals and configuration files require separate backup steps.

### 51.10. "pg_dump --schema-only still exports rows"

**False.** It outputs only schema definitions within scope.

### 51.11. "pg_dump --data-only restores cleanly into an empty database"

**False.** Schemas and dependencies must already exist.

### 51.12. "Being able to list TOC proves restore will succeed"

**False.** Only an actual restore test verifies recoverability.

### 51.13. "Restoring with --no-owner --no-acl preserves original privileges"

**False.** Those flags deliberately omit ownership and grant statements.

### 51.14. "--clean and --if-exists are always harmless"

**False.** They still drop existing objects on the target database.

### 51.15. "A single WAL segment can rebuild an entire database"

**False.** You must start from a valid base backup plus an unbroken WAL chain.

### 51.16. "WAL inside pg_wal survives primary disk loss"

**False.** WAL stored on the same disk dies with the cluster.

### 51.17. "pg_basebackup -X stream enables future PITR indefinitely"

**False.** `-X stream` only collects WAL generated during the backup itself; future PITR needs ongoing WAL archiving.

### 51.18. "A physical backup restores onto any PostgreSQL major version"

**False.** Physical layouts are tied to matching major versions and architectures.

### 51.19. "A hot standby replaces historical backups"

**False.** Replicas replay accidental drops and deletes too.

### 51.20. "PITR has a flag to undo one row while keeping later transactions"

**False.** PITR restores the entire cluster to a chosen recovery point.

### 51.21. "Matching file checksums prove the application works"

**False.** Checksums do not validate business invariants, roles, or external dependencies.

### 51.22. "Daily backups meet a 5-minute RPO"

**False** without continuous WAL archiving or reliable data-retention layers covering the gap.

### 51.23. "Recovering data in 10 hours satisfies a 30-minute RTO"

**False.** RTO measures total time from outage until the service resumes healthy operation.

### 51.24. "Keeping backups on the same instance protects against losing that instance"

**False.** Backups need independent offsite storage.

### 51.25. "Encrypted backups eliminate the need to protect keys"

**False.** Losing keys locks you out of recovery; leaking keys compromises confidentiality.

### 51.26. "A logical dump can never count as a backup"

**False.** When snapshot recovery fits RPO and RTO and restores are verified, it is a valid backup.

### 51.27. "Any storage snapshot is automatically consistent"

**False.** It must obey PostgreSQL crash-consistency requirements and span all volumes/tablespaces.

### 51.28. "Restoring a table from dump automatically resyncs external services"

**False.** Queues, payment gateways, and object stores require explicit reconciliation.

### 51.29. "Data warehouse exports serve as a cluster DR plan"

**False.** Analytics exports lack schema, permissions, and transactional recovery guarantees.

### 51.30. "Last year's restore test proves today's backups work"

**False.** Schemas, volumes, storage, permissions, and PostgreSQL versions evolve constantly.

## 52. Practice Exercises

### Exercise 1 — Classify a CSV

You receive `customers.csv` containing `customer_id` and names. Is this a data export, a logical dump, or a physical backup?

**Answer:** Data export.

### Exercise 2 — Missing schema

Why can't indexes and foreign keys be reconstructed from a CSV alone without a schema contract?

**Hint:** CSVs carry row values, not full DDL metadata.

### Exercise 3 — COPY path

Which host does `COPY table TO '/tmp/x.csv'` write to?

**Answer:** The PostgreSQL server host.

### Exercise 4 — \copy path

Which host does `\copy table TO 'x.csv'` write to?

**Answer:** The client machine running `psql`.

### Exercise 5 — JDBC

Can you send `\copy` directly inside a JDBC SQL statement?

**Answer:** No; use `COPY` SQL or the driver's `COPY` streaming API.

### Exercise 6 — Two export snapshots

Why can exporting `orders` and `customers` in two separate queries produce inconsistent data?

**Hint:** Two separate MVCC snapshots taken at different times.

### Exercise 7 — Filtering

Does a CSV generated by `SELECT ... WHERE` contain all rows in the table?

**Answer:** No; only rows matching the predicate.

### Exercise 8 — CSV import IDs

After importing a CSV containing explicit historical IDs, what ID-generation mechanism must you check?

**Hint:** Identity columns / sequences.

### Exercise 9 — Logical dump scope

Does `pg_dump -d trainingdb` dump the entire cluster?

**Answer:** No.

### Exercise 10 — Format flag

What format does `pg_dump -F c` create?

**Answer:** Custom archive.

### Exercise 11 — Inspecting custom archives

Which command lists the TOC of a custom archive?

**Answer:** `pg_restore --list`.

### Exercise 12 — Restoring plain SQL

Which tool executes a plain SQL dump?

**Answer:** `psql`.

### Exercise 13 — Directory dumps

Can you copy one arbitrary file out of a directory archive and treat it as a complete dump?

**Answer:** No; the entire directory archive is required.

### Exercise 14 — Schema-only

Does `--schema-only` include table rows?

**Answer:** No.

### Exercise 15 — Data-only

Can `--data-only` create all tables inside a fresh empty database?

**Answer:** No.

### Exercise 16 — pg_restore -j

Which flag enables parallel restoration on supported archive formats?

**Answer:** `-j`.

### Exercise 17 — --clean

Why is `--clean` risky?

**Hint:** It drops existing objects on the target database before recreating them.

### Exercise 18 — --no-acl

Why doesn't `--no-acl` prove permissions were restored faithfully?

**Hint:** It omits `GRANT`/`REVOKE` statements.

### Exercise 19 — Globals

Which tool and flag dump cluster-wide roles and tablespaces?

**Hint:** `pg_dumpall --globals-only`.

### Exercise 20 — Password verifiers

What sensitive data can a globals dump contain?

**Hint:** Authentication metadata and password verifiers.

### Exercise 21 — Dump snapshot timing

If a dump runs from 01:00 to 01:45, does it automatically include all transactions committed up to 01:45?

**Answer:** No.

### Exercise 22 — Multi-database consistency

Does `pg_dumpall` guarantee a single atomic snapshot across every database?

**Answer:** No.

### Exercise 23 — WAL alone

Does WAL contain all data pages needed to reconstruct a database on its own?

**Answer:** No; a base backup is required.

### Exercise 24 — Basebackup scope

Does `pg_basebackup` back up one table or the whole database cluster?

**Answer:** The whole cluster.

### Exercise 25 — PITR prerequisites

What core components are needed for PITR?

**Hint:** A base backup, an unbroken WAL chain, recovery configuration/target, and a compatible environment.

### Exercise 26 — Missing WAL segment

What happens if a required WAL segment is missing?

**Hint:** Replay may fail to reach the intended recovery target.

### Exercise 27 — pg_wal location

Is WAL sitting on the primary's local disk an offsite backup?

**Answer:** No.

### Exercise 28 — Replication slots

Why don't replication slots replace backups, and how can they fill disk?

**Hint:** They retain WAL locally for consumers without copying offsite; stalled consumers build unbounded backlogs.

### Exercise 29 — RPO

What does an RPO of 15 minutes mean?

**Hint:** Maximum acceptable data loss measured in time (at most 15 minutes of data).

### Exercise 30 — RTO

What does an RTO of 1 hour mean?

**Hint:** The service must return to an acceptable operational state within at most 1 hour.

### Exercise 31 — RPO with dumps

Dump runs at 01:00, outage hits at 12:00, and only dumps exist. Roughly what is the worst-case RPO here?

**Hint:** Up to ~11 hours if the dump snapshot was taken at 01:00.

### Exercise 32 — RTO in practice

Outage starts at 12:00, service recovers at 15:30. What was the recovery time?

**Answer:** 3 hours 30 minutes.

### Exercise 33 — Replica protection

Does a streaming replica automatically shield against a replayed `DROP TABLE`?

**Answer:** No.

### Exercise 34 — Logical migration

Why is dump/restore often well suited for PostgreSQL major version upgrades?

**Hint:** Logical SQL reconstructs objects under the new engine's format.

### Exercise 35 — Physical migration

Why can't you boot a newer PostgreSQL major binary directly on an older major's `PGDATA`?

**Hint:** Incompatible internal data formats and catalog layouts.

### Exercise 36 — Missing extensions

A dump contains `CREATE EXTENSION`, yet the target server lacks the shared library. What happens?

**Hint:** Restore fails or dependent objects break.

### Exercise 37 — Checksums

Does a verified file checksum prove the application can boot and function?

**Answer:** No.

### Exercise 38 — pg_verifybackup

Can `pg_verifybackup` replace a full restore drill?

**Answer:** No.

### Exercise 39 — Secondary cluster recovery

Why restore an accidentally dropped table into a separate cluster or scratch database first?

**Hint:** To avoid overwriting valid recent transactions on live production.

### Exercise 40 — Chain retention

Why must you never delete a base backup while incremental backups still depend on it?

**Hint:** The dependent chain becomes unrestorable.

### Exercise 41 — Same-disk backups

Do backups kept on the primary disk protect against total disk failure?

**Answer:** No.

### Exercise 42 — Encryption keys

What happens if an encrypted backup exists but its encryption key is lost?

**Hint:** The backup cannot be decrypted or restored.

### Exercise 43 — Cross-version restore

An older backup came from PostgreSQL 14 and the target host runs PostgreSQL 17. Which strategy fits better: logical or physical?

**Hint:** Logical dump/restore (assuming SQL and extensions remain compatible); raw v14 `PGDATA` will not run on v17.

### Exercise 44 — External storage

If a database stores pointers to 5 TB in object storage, does `pg_dump` back up those objects too?

**Answer:** No.

### Exercise 45 — Integrated architecture design

A 2 TB PostgreSQL system requires a 5-minute RPO, 1-hour RTO, HA standby, recovery from accidental deletes, and survival against losing a whole region. What layers will you implement?

**Hint:** Scheduled physical backups, continuous WAL archiving with lag alerts, offsite/immutable cross-region storage, HA standby for fast failover, chain-aware retention, automated restore drills, cross-region key/credential management, PITR rehearsal measuring real RPO/RTO, plus optional logical dumps for fast single-table extraction.

## 53. Checklist Before Calling a Backup "Recoverable"

### 53.1. Objectives

- [ ] Specific disaster scenarios defined?
- [ ] Scope clear: rows, table, database, or full cluster?
- [ ] Numeric RPO and RTO defined?
- [ ] Need PITR or snapshot-only restore?
- [ ] Need to preserve valid writes after a logical mistake?
- [ ] External services requiring reconciliation identified?

### 53.2. Artifacts

- [ ] Backup job completed with clean exit code?
- [ ] Complete files and backup manifest present?
- [ ] Globals, roles, tablespaces, and extension dependencies captured?
- [ ] Full WAL segment and timeline coverage verified?
- [ ] PostgreSQL and backup tool versions recorded?
- [ ] Consistent snapshot / LSN metadata captured?
- [ ] Checksum and manifest integrity verified?
- [ ] Backup chain dependencies tracked?

### 53.3. Storage and security

- [ ] Storage physically independent from primary?
- [ ] Offsite / cross-zone / cross-region copies maintained if required?
- [ ] IAM separates backup writers, restore readers, and deletion admins?
- [ ] Encrypted at rest and in transit?
- [ ] Decryption keys accessible independently during disaster?
- [ ] Artifacts never leaked via public storage, CI logs, or Git?
- [ ] Immutable retention enabled to block malicious deletion?
- [ ] Storage headroom and WAL archive failures monitored?

### 53.4. Restore tests

- [ ] Actually spun up a fresh database/cluster from artifacts?
- [ ] Inspected restore logs and errors?
- [ ] Executed data verification queries?
- [ ] Checked indexes, constraints, and sequences?
- [ ] Tested roles, grants, RLS policies, and extensions?
- [ ] Verified live application connectivity and read/write flows?
- [ ] Measured actual RPO and RTO?
- [ ] Recorded drill outcomes and responsible operators?
- [ ] Simulated realistic infrastructure loss rather than copying local files?

## 54. Tool Selection Decision Tree

~~~text
What do you need to do?
    |
    +-- Share or load query-level data?
    |       |
    |       +--> COPY / \copy / ETL / JSON export
    |
    +-- Migrate or rebuild specific database objects?
    |       |
    |       +--> pg_dump + pg_restore / psql
    |               |
    |               +--> Need cluster roles/tablespaces?
    |                        |
    |                        +--> pg_dumpall --globals-only
    |
    +-- Recover data after an incident?
            |
            +-- Only need last night's snapshot;
            |   DB small enough and RTO acceptable?
            |        |
            |        +--> Verified logical dump
            |
            +-- Need full cluster recovery or PITR?
                     |
                     +--> Physical base backup
                          + WAL archiving/retention
                          + recovery runbook
                          + regular restore drills
    |
    v
Always verify RPO, RTO, dependencies, and security
~~~

### 54.1. No single tool serves every goal

CSV exports excel at data exchange. `pg_dump` excels at logical snapshots. Physical base backups plus WAL are essential for cluster-level recovery and PITR.

### 54.2. Design for the worst-case scenario you claim to survive

A setup that recovers a single table well can still fail completely during a regional outage. Align RPO, RTO, and cost to a realistic threat model.

## 55. Quick Reference Table

| Term | Key takeaway |
|---|---|
| `SELECT` | Queries row data |
| `COPY ... TO` | SQL data export (writes to server path when given a filename) |
| `\copy` | Client-side `psql` file export/import |
| CSV/TSV/JSON | Data formats lacking full database metadata |
| `pg_dump` | Logical dump of one database |
| `pg_dumpall` | Plain SQL script for cluster databases and globals |
| `--globals-only` | Dumps cluster-wide roles and tablespace metadata |
| `-F p` | Plain SQL format |
| `-F c` | Custom archive format |
| `-F d` | Directory archive format |
| `-F t` | Tar archive format |
| `psql -f` | Restores plain SQL scripts |
| `pg_restore` | Restores custom, directory, and tar archives |
| `pg_restore --list` | Prints archive TOC (not a restore test) |
| `--clean` | Drops objects before recreating—use with extreme caution |
| `--no-owner` | Skips restoring object ownership |
| `--no-acl` | Skips restoring `GRANT`/`REVOKE` permissions |
| `pg_basebackup` | Physical base backup of an entire cluster |
| `WAL` | Write-Ahead Log powering recovery and replication |
| WAL archive | Offsite/independent WAL storage for history recovery |
| PITR | Cluster recovery to a chosen target point |
| `recovery.signal` | Recovery trigger file in modern PostgreSQL |
| `restore_command` | Fetches archived WAL segments during recovery |
| `pg_verifybackup` | Verifies physical backup manifest and checksums |
| RPO | Maximum tolerable data loss window |
| RTO | Maximum tolerable recovery time window |
| Hot standby | High availability failover node, not historical backup |
| Incremental chain | Requires retaining every dependent baseline and link |
| Restore drill | Real proof of recoverability |
| Offsite/immutable backup | Protects against primary storage loss or tampering |
| Extension/role dependencies | Must be verified alongside row data |
| External systems | Require separate backups and reconciliation |

---

## 56. Conclusion

**Data exports, logical dumps, and recoverable backups are three related concepts that cannot substitute for one another.** Exporting via `COPY`, `\copy`, or CSV/JSON queries extracts rows cleanly for interchange and ETL, without capturing schemas, constraints, privileges, or WAL. Logical dumps via `pg_dump` rebuild a database's objects and snapshot data—great for migrations and snapshot restores—yet lack the WAL stream required for later PITR.

**Cluster-wide and point-in-time recovery rely on physical base backups paired with complete, verified WAL archives.** An improperly taken physical copy or a broken WAL chain fails recovery even when files appear intact on disk. Replicas and hot standbys slash downtime for hardware failures, yet replicate accidental deletes and never substitute for backup history.

Whether a backup truly meets requirements is determined by **proven RPO/RTO and successful restore drills**—never file size or a "job completed" flag. Reliable recovery protects artifacts and encryption keys offsite, includes globals, extensions, and external dependencies, enforces chain-aware retention, uses isolated test environments to check constraints, transactions, and live apps, and rehearses real failure scenarios regularly.

**Practical rule:** use exports when you need *data*, use `pg_dump` when you need a *logical snapshot*, use physical backups and WAL when you need *disaster recovery and PITR*, and only call something a **recoverable backup** once you have proven it restores the exact scope and point in time within the business's recovery window.
