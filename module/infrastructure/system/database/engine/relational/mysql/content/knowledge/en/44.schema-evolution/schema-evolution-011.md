# Evaluating pt-online-schema-change and gh-ost by Conditions and Limitations

Altering large tables in MySQL can force applications to wait for a long time if using traditional `ALTER TABLE`. Online schema change tools such as **pt-online-schema-change** and **gh-ost** reduce disruption by creating a new table, copying data in chunks, synchronizing ongoing changes occurring during the copy, and swapping table names during cutover.

Both tools solve the same problem using different synchronization mechanisms. `pt-online-schema-change` (`pt-osc`) uses triggers on the source table to mirror changes into the new table. `gh-ost` reads the binary log to capture changes and apply them to the new table. That underlying mechanism determines compatibility conditions, generated load, trigger/foreign-key constraints, and runtime operational controls.

This lesson belongs to the **DATABASE_MYSQL** module and focuses on safe schema evolution: evaluating tools by table structure, MySQL version, replication topology, write load, storage capacity, data constraints, and recoverability. Neither tool guarantees a completely lock-free `ALTER`; both still require a brief metadata lock during cutover.

## 1. Why is online schema change needed?

An `ALTER TABLE` on a large table may rebuild the table, build indexes, or convert data. Depending on engine, `ALTER` type, and MySQL version, the operation may:

- Block writes or reads for an extended duration.
- Hold metadata locks and cause other queries to queue.
- Generate heavy I/O, CPU, and redo/undo log pressure.
- Generate large binary logs, spiking replica lag.
- Require extra temporary space roughly equal to table size, or even more when building indexes or retaining the old copy.

MySQL supports several DDL algorithms such as `INSTANT`, `INPLACE`, and `COPY`. Before picking an external tool, check whether the change can use MySQL's native online DDL:

~~~sql
ALTER TABLE app.orders
  ADD COLUMN source_tag VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
~~~

This example works only for supported changes and versions supporting `INSTANT`. If MySQL reports that the requested algorithm is unsupported, re-evaluate the DDL and version rather than simply deleting `ALGORITHM` and assuming the operation stays non-blocking.

Online schema change is an option for changes that cannot execute safely via native DDL algorithms or when fine-grained control over copying is needed. It does not turn an incompatible change into a risk-free one.

## 2. How pt-online-schema-change works

`pt-online-schema-change` is part of Percona Toolkit. It creates a new table with the modified structure, copies rows from the source table in chunks, and uses triggers to keep the new table updated while the application continues writing to the source table.

High-level workflow:

1. Inspect the source table definition and create the target table with the requested DDL changes.
2. Create triggers on the source table to mirror `INSERT`, `UPDATE`, and `DELETE` to the target table.
3. Copy existing rows in chunks.
4. Monitor load and replication lag; throttle or pause when thresholds are exceeded.
5. Once data is synchronized, rename the tables during cutover.
6. Retain or drop the old table per your retention policy after verification.

Triggers let `pt-osc` capture writes occurring concurrently with the copy. However, triggers execute inline in the application's write path. Thus, every `INSERT`/`UPDATE`/`DELETE` on the source table incurs extra writes to the new table. On high-write tables, trigger overhead can directly impact transaction latency.

### Conditions and limits to evaluate

- The tool must create triggers on the source table; check `TRIGGER` privileges and required DDL/DML permissions.
- By default, existing triggers can prevent `pt-osc` from running because it needs to install its own triggers. The **`--preserve-triggers`** option supports preserving existing triggers on MySQL 5.7.2+, though you must check whether triggers reference dropped/renamed columns and test on your exact toolkit version.
- The table needs a suitable primary key or unique key for chunking and row identification.
- Tables referenced by foreign keys require dedicated handling when swapping tables. `pt-osc` offers options such as rebuilding constraints or drop/rename in certain scenarios; each option has distinct impacts and limits.
- Extra triggers increase write load, potentially lengthening transactions or hurting latency-sensitive workloads.
- Complex DDL changes, generated columns, partitions, views, triggers, constraints, and data type conversions must be tested with the exact tool version.

### Foreign keys with pt-osc

Foreign keys are a decisive factor in whether `pt-osc` can be used. When a source table is referenced by child tables, switching to the new table may require updating constraints on those child tables.

`pt-osc` provides strategies via **`--alter-foreign-keys-method`**. Commonly evaluated options include:

- **`rebuild_constraints`:** alters constraints on child tables to reference the new table. This may run `ALTER` on child tables, generating load and metadata locks; large child tables complicate cutover.
- **`drop_swap`:** uses a drop/rename sequence during table swap. This carries higher risk if interrupted at a sensitive moment; do not choose it without understanding the window during which the source table temporarily does not exist and having a verified recovery plan.

Confirm exact option names and behavior against your installed Percona Toolkit version's documentation. The **`drop_swap`** method disables foreign key checks, drops the source table, and then renames the new table into place; in between, the table does not exist, and a rename failure can permanently lose the old table. Consider it only when explicitly accepting that risk with a tested recovery plan. Before running, inventory all child tables and foreign key constraints referencing the source table, and estimate each child table's size and `ALTER` duration.

### Dry-run and execution examples

~~~bash
pt-online-schema-change \
  --alter "ADD COLUMN source_tag VARCHAR(32) NULL" \
  D=app,t=orders \
  --dry-run
~~~

**`--dry-run`** only creates and alters the new table to validate DDL; it does not create triggers, copy data, or perform cutover. Therefore, dry-run cannot measure copy duration or real load. To rehearse copying more realistically, evaluate **`--no-swap-tables`** in a test environment; this option creates the new table and copies data, then cleans up the new table without swapping the source table. Confirm cleanup behavior and impact for your version before running.

After reviewing logs, privileges, triggers, load, and cutover strategy, build a dedicated execution command:

~~~bash
pt-online-schema-change \
  --alter "ADD COLUMN source_tag VARCHAR(32) NULL" \
  D=app,t=orders \
  --max-load Threads_running=25 \
  --critical-load Threads_running=50 \
  --chunk-time 0.5 \
  --max-lag 2 \
  --execute
~~~

This is an illustrative configuration. Load thresholds must reflect your system baseline; thresholds set too low stall progress constantly, whereas thresholds set too high degrade the application. Option names, units, and behaviors may vary by toolkit version.

## 3. How gh-ost works

`gh-ost` is an online schema migration tool for MySQL that uses the binary log to capture changes on the source table and apply them to the target table. It creates a ghost table, copies data in chunks, reads change events, and synchronizes data before cutover.

High-level workflow:

1. Connect to the MySQL topology and identify the binary log source.
2. Create the ghost table with the new structure per the requested `ALTER` statement.
3. Copy existing rows in chunks.
4. Read row events from the binary log and apply corresponding changes to the ghost table.
5. Throttle copy speed, monitor lag, and wait until the ghost table catches up.
6. Perform cutover by renaming tables.
7. Retain or drop the old table according to configuration and operational runbook.

Because it uses binlogs instead of triggers on the source table, `gh-ost` adds no sync triggers to the application's write path, avoiding per-write trigger overhead. However, per current limitation docs, `gh-ost` does not support tables with triggers; it is not a drop-in replacement for `pt-osc` on a table that already has triggers. The tool depends heavily on binary log configuration, row events, and topology log readability.

### Compatibility requirements

Before using `gh-ost`, verify at minimum:

- Binary logging is enabled and the tool can read binary logs from the selected source.
- Per `gh-ost` requirements, at least one server must provide row-based binary logs; the supported row image is **`FULL`**. If reading binlogs from a replica, the table schema on that replica must match the source schema. `gh-ost` prefers reading from a replica; in that setup, the source may still use statement-based logging if the replica emits suitable row-based logs.
- Current `gh-ost` documentation requires MySQL 5.7 or newer. Re-verify minimum version and support matrix for your installed `gh-ost` release.
- Continuous binary logs remain available throughout the migration; do not let retention or purges delete files the tool still needs to read.
- The account holds required privileges to read metadata, read binlogs, create tables, write data, and execute cutover per version docs.
- The table has a suitable primary key or unique key for copying and applying changes.
- Replication topology, hostnames, channels, replicas, and binlog source are properly recognized by `gh-ost`.
- Evaluated compatibility with foreign keys, triggers, partitions, and table DDL characteristics. `gh-ost` has specific structural limits; check the version support matrix instead of assuming compatibility just because the tool connects cleanly.

`gh-ost` requires row-based binary logging and currently supports **`FULL`** row image. **`MINIMAL`** is unsupported per the referenced project requirements. Check settings on the actual server serving as the binlog source:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
SHOW BINARY LOGS;
~~~

Compare values against the `gh-ost` documentation for your exact version. Never blindly alter production binary log settings just to make a tool run; such changes affect replication and all other binlog consumers.

### Important gh-ost limitations

Per project requirements and limitation docs:

- **Foreign keys are unsupported.** If a table has foreign key constraints, choose another approach or design a multi-phase migration after evaluating all dependencies.
- **Triggers are unsupported.** Do not use `gh-ost` on tables with triggers that must be preserved while this limitation applies.
- Source and target tables must share the same primary key or unique key used as the migration key. Columns in this key cannot contain `NULL`; nullable unique keys are not accepted by default.
- Migration keys containing `ENUM` columns can severely degrade performance.
- Encrypted binary logs are unsupported per current documentation.
- Multi-source replication when reading via a replica is unsupported. Master-master topologies are supported only in active-passive mode; active-active with concurrent writes on both masters is unsupported.
- Certain table types or `ALTER` operations, such as `FEDERATED` tables and renaming tables via `ALTER RENAME`, are out of scope.

Re-verify these limits against your actual `gh-ost` release. Do not pick `gh-ost` solely because row binlogs are enabled; foreign keys, triggers, and topology can disqualify the tool during preflight.

### Throttling and cutover control

`gh-ost` provides mechanisms to throttle speed by server load, replica lag, and control flags. You can combine load thresholds, lag caps, pause flags, and cutover-postpone flags so DBAs control exact table-swap timing.

Illustrative command skeleton:

~~~bash
gh-ost \
  --host=mysql-primary.example \
  --database=app \
  --table=orders \
  --alter="ADD COLUMN source_tag VARCHAR(32) NULL" \
  --user=schema_migrator \
  --max-load=Threads_running=25 \
  --critical-load=Threads_running=50 \
  --max-lag-millis=1500 \
  --chunk-size=1000 \
  --postpone-cut-over-flag-file=/tmp/gh-ost.postpone \
  --execute
~~~

This is an illustrative example; add topology flags, authentication, and privileges matching your environment. Control flag file paths must be created and managed on the exact host running `gh-ost`. Remove the postpone-cutover flag only after DBAs confirm the application is ready for table swap.

## 4. Comparing the two tools

| Criterion | pt-online-schema-change | gh-ost |
|---|---|---|
| Synchronization mechanism | Triggers on the source table | Reads binary logs and applies row events |
| Impact on app write path | Triggers generate extra inline DML | No sync triggers added to the source table |
| Binary log requirement | Does not rely on binlogs as primary table-sync mechanism | Depends on row-based binlogs and log readability |
| Existing triggers | Refuses by default if triggers exist; `--preserve-triggers` available on MySQL 5.7.2+ with compatibility testing | Triggers unsupported per current requirements docs |
| Foreign keys | Supports `rebuild_constraints` and `drop_swap`; both carry impact, and `drop_swap` has a window where the table does not exist | Foreign keys unsupported per current requirements docs |
| Row image | Does not use row images as primary sync mechanism | Requires row-based binlogs with `FULL` row image per current docs |
| Cutover control | Tool renames tables once synchronized | Supports postponing cutover via flag files for explicit timing control |
| Load throttling | Chunk time, max-load, critical-load, max-lag, and pause file | Chunk size, max-load, critical-load, replica lag, and control flags |
| Best suited when | Environment allows triggers and FK handling has a safe plan | Row binlogs fit, triggers must be avoided, and binlog-driven control is desired |

Neither tool wins in every scenario. Choose based on actual table conditions, versions, topology, write load, constraints, and operational processes.

## 5. Conditions to verify before choosing

### Table size and disk capacity

During most of the run, the tool keeps both the source table and ghost table side by side while copying. Required capacity is not just the source table's size:

- The altered ghost table may grow larger due to added columns or indexes.
- New indexes require separate space and may consume temporary sort space.
- Binary logs, relay logs, redo logs, and undo logs grow during copying.
- The old table may be retained post-cutover for recovery or investigation.

Estimate disk space across both the data directory and the filesystem holding binlogs. For safety margins, measure actual sizes and test on a representative data copy; never apply a fixed multiplier blindly to every table.

### Write rate and long transactions

`pt-osc` executes extra trigger work for DML on the source table. `gh-ost` reads and applies binlog changes while copying rows. Both are affected by high write rates or long-running transactions.

If change rate exceeds the tool's apply capacity, backlog grows. This lengthens the migration, increases required log retention, and can drive replica lag up. Measure write rate, transaction size, updated row volume, and trial runtimes to tune chunk size, chunk time, and throttling.

### Primary keys and unique keys

A stable key lets the tool chunk rows, locate records, and apply changes accurately. Tables without a suitable primary key or unique key add complexity and may not be supported as desired.

Never add a primary key hastily alongside a major migration without analyzing cost and how the tool identifies rows. Split steps if needed, test the DDL plan, and assess replication impact.

### Foreign keys, triggers, and partitions

Inventory dependencies before running:

~~~sql
-- Inspect table definition and indexes
SHOW CREATE TABLE app.orders\G
SHOW INDEX FROM app.orders;

-- Find foreign keys referencing the orders table
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  CONSTRAINT_NAME,
  COLUMN_NAME,
  REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'app'
  AND REFERENCED_TABLE_NAME = 'orders';

-- Inspect triggers attached to the table
SHOW TRIGGERS FROM app LIKE 'orders';
~~~

Additionally, check partitions, generated columns, check constraints, views, routines, events, and dependent objects. An `ALTER` on a table never exists in isolation; changes can impact applications, reports, and ETL pipelines.

### MySQL version and tool version

DDL capabilities, metadata locks, multi-trigger support, row events, and administrative privileges vary across MySQL releases. Percona Toolkit and `gh-ost` also evolve across versions. Record the exact server, toolkit, `gh-ost`, and OS versions in the migration plan.

Never run an outdated tool version against a newer server just because syntax appears compatible. Read release notes, check known issues, and test on a clone matching version, config, and data size.

## 6. Assessing whether the DDL fits the tool

Not every `ALTER TABLE` translates straightforwardly into an online schema change. Before constructing commands, analyze the intended change:

- Adding or dropping columns, changing data types, changing charset/collation.
- Adding, dropping, or altering indexes and unique constraints.
- Changing the primary key.
- Changing partitioning or storage engine.
- Changing nullability/defaults, generated columns, or expressions.
- Whether the change invalidates existing data.

Some changes require per-row data conversion. For example, converting a column from `VARCHAR` to numeric can fail or lose data if unconvertible strings exist. Online schema change tools merely copy and apply DDL; they do not interpret business semantics of data transformations.

### Checking data before changing types

Suppose `quantity` must convert from `VARCHAR` to `INT`. First locate unconvertible values:

~~~sql
SELECT quantity
FROM app.inventory
WHERE quantity IS NOT NULL
  AND quantity NOT REGEXP '^-?[0-9]+$'
LIMIT 100;
~~~

Continue checking value ranges, `NULL`s, empty strings, overflows, and whitespace values. Define how invalid data will be handled before running DDL.

### Not every ALTER should run via shadow-table tools

If a change safely uses MySQL's `INSTANT` or `INPLACE` on your exact version, native MySQL DDL is usually simpler with fewer moving parts. If a change requires `COPY`, online schema change reduces write-blocking duration yet still copies the entire table and performs cutover.

For changes with complex data transformations, build a multi-phase migration: add a new column, dual-write or backfill safely, verify data, switch application reads to the new column, and only then drop the old column. This is usually safer than forcing one giant `ALTER` to convert the whole table.

## 7. Metadata locks and cutover

The most critical moment for both `pt-osc` and `gh-ost` is cutover. Once the new table is copied and synchronized, the tool renames the old and new tables so the application starts using the new structure.

Renaming requires metadata locks. If long transactions, queries holding metadata locks, or active sessions touch the table at cutover, the tool must wait. A pending metadata lock request can also queue new queries behind it, making the application appear hung even though the rename itself is brief.

Before cutover:

1. Check open transactions and long-running queries.
2. Inspect metadata locks on both the source and ghost tables.
3. Confirm replication lag is within acceptable bounds.
4. Confirm the ghost table has caught up to source data.
5. Confirm the application is compatible with the new schema.
6. Pick a low-traffic window with active operator monitoring.

Inspect open transactions:

~~~sql
SELECT
  trx_id,
  trx_mysql_thread_id,
  trx_started,
  trx_state,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Inspect metadata locks via Performance Schema:

~~~sql
SELECT
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'app'
  AND OBJECT_NAME = 'orders';
~~~

Available columns and query access depend on version, instrumentation settings, and Performance Schema privileges. Reconcile actual state right before cutover.

### Limits of cutover

- You cannot guarantee cutover will never wait on metadata locks.
- Long transactions can push wait times past the maintenance window.
- Certain DDL operations or foreign key dependencies complicate renames.
- If the application caches prepared statements or metadata, verify behavior after structural changes.
- If the tool stops during cutover, inspect state and logs before deciding whether to resume or recover.

Never blindly kill sessions just because a metadata lock is waiting. Identify the transaction owner, business impact, and runbook procedure for blocking sessions first.

## 8. Throttling, replica lag, and topology impact

Copying a large table generates heavy reads from the source table and writes to the ghost table. Synchronizing ongoing changes adds further work. Across replication topologies, this increases binary logs, relay logs, applier queues, and replica lag.

### Monitoring server load

Track metrics with established baselines:

- `Threads_running` and active connection counts.
- CPU, IOPS, throughput, and storage latency.
- Data directory usage, temporary space, and binary log disk usage.
- InnoDB history list length, redo pressure, and transaction duration.
- Replica lag, I/O/applier thread states, and relay log queue size.
- Application query latency and timeout rates.

Never watch only a single metric. For instance, `Threads_running` can look low while storage latency spikes; replica lag can start low and climb sharply once copy rate outpaces applier capacity.

### Tuning speed

With `pt-osc`, tune chunk time, max-load, critical-load, max-lag, and pause files. With `gh-ost`, tune chunk size, max-load, critical-load, max-lag, and throttle/cutover flags. Confirm exact names, units, and behavior for your tool version.

Principles:

- Start with small chunks and conservative speed.
- Observe impact on both the source and all replicas.
- Ramp speed incrementally while latency and lag stay stable.
- Pause when thresholds are breached; never wait until the system stops serving traffic.
- Resume only after identifying the cause and confirming system recovery.

If the tool reads binlogs from a replica, still verify that replica keeps up with the source and retains sufficient logs. Reading from a replica offloads some binlog-read work from the primary, yet does not eliminate migration write load or ghost-table replication impact.

### Impact on backups and PITR

During migrations, binary logs can grow quickly. Verify retention, disk space, and binlog archiving capacity. Never purge logs needed by replicas or point-in-time recovery windows merely to free migration space.

If backups or backup locks are running, confirm the schema change tool can coexist safely. Avoid scheduling cutover alongside backups, other DDLs, or uncoordinated topology switches.

## 9. Privileges and operational accounts

Never use the production application account to run schema changes. Create a dedicated migration account and grant privileges scoped to the exact tool, version, operation, and topology.

Privileges commonly reviewed:

- Reading metadata and data on the source table.
- Creating, altering, writing, and dropping the ghost table.
- Creating triggers if using `pt-osc`.
- Reading replication state or binary logs if using `gh-ost`.
- Performing rename/cutover and table cleanup per policy.
- Reading Performance Schema tables or status metrics for throttling.

Exact privilege lists depend on tool version and connection mode. Follow the official docs for your installed version to construct minimal `GRANT`s, then test in a staging environment. Never grant `SUPER` or global admin privileges just to avoid investigating required permissions.

Account skeleton example:

~~~sql
CREATE USER 'schema_migrator'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';
~~~

Grant each identified privilege scoped by tool and schema. Retrieve secrets from a secret manager—never store them in shell history, shared scripts, or migration docs.

## 10. When to choose pt-online-schema-change?

`pt-osc` can be a good fit when:

- The environment permits creating triggers on the source table.
- No conflicting existing triggers exist, or the toolkit's trigger-preservation support has been tested.
- Foreign keys have a clear handling plan and child-table `ALTER` costs are acceptable.
- You cannot or prefer not to rely on `gh-ost`'s row-based binlog requirements.
- Operations teams know Percona Toolkit and have monitoring for chunks, load, lag, and cutover.

Do not pick `pt-osc` merely because it is already installed. On very high-write tables, per-transaction trigger overhead can have severe impact. With many foreign keys or complex triggers, test on a data clone before deciding.

## 11. When to choose gh-ost?

`gh-ost` can be a good fit when:

- Binary logs and topology satisfy `gh-ost`'s requirements.
- Row-based binlogs with the required row image can be used.
- You want binlog-based sync rather than adding triggers to the source table.
- You need fine-grained throttling and cutover postponement until an operator signals go.
- Foreign key, trigger, partition, and DDL limitations do not affect the target table.

Do not pick `gh-ost` without verifying binlog streams, retention, log-read privileges, and topology. If servers lack the required row format or purge logs before the tool finishes reading, the migration will fail or fall out of sync.

## 12. Pre-production evaluation workflow

**Phase 1 — Survey the table**

- Document DDL, data size, and index size.
- Identify primary key, unique keys, foreign keys, triggers, and partitions.
- Find dependent views, routines, events, and applications.
- Measure write rate, long transactions, peak hours, and replica lag.
- Determine whether MySQL's `INSTANT`/`INPLACE` DDL can handle the change.

**Phase 2 — Validate the tool**

- Record MySQL, Percona Toolkit, or `gh-ost` versions.
- Check DDL and table-structure support matrices.
- Verify migration account privileges.
- For `pt-osc`, verify triggers and foreign-key strategy.
- For `gh-ost`, verify row-based binlog source, `binlog_row_image=FULL`, binlog server, replica schema match, and retention.

**Phase 3 — Rehearse**

- Use a clone with production-like data size and write rate.
- Run dry runs or tool-supported test modes.
- Measure copy time, binlog volume, temporary disk usage, and replica lag.
- Test pause, resume, throttling, and cutover.
- Verify application behavior against the new schema.

**Phase 4 — Prepare deployment**

- Ensure valid backups and verified restore capability.
- Set load thresholds, lag caps, and an owner authorized to halt the migration.
- Schedule the cutover window, metadata-lock monitoring, and blocker handling.
- Define old-table retention, data verification, and rollback plans.
- Notify application, DBA, and operations teams per internal process.

## 13. Running the migration and verifying results

During execution, monitor tool logs alongside source/replica metrics. Do not simply wait for the process to exit successfully. Before and after cutover, verify:

- The new table structure matches the requested DDL.
- Row counts and critical business data match the source table.
- Indexes, constraints, triggers, and related objects are properly in place.
- The application reads and writes cleanly using the new schema.
- Replicas catch up with zero SQL applier errors.
- Query latency, error rates, and connection pools return to normal baselines.

Example structural and row-count checks:

~~~sql
SHOW CREATE TABLE app.orders\G
SHOW INDEX FROM app.orders;
SELECT COUNT(*) FROM app.orders;
~~~

On large tables, `COUNT(*)` can be expensive depending on engine and system state. Use primary-key range stats or chunked checksums instead, understanding each method's accuracy and snapshot timing. Never compare a changing primary against a lagging replica and immediately conclude the migration lost data.

## 14. Rollback and handling failed migrations

Rollback must be planned before running. Retaining the old table after cutover helps investigation or recovery in certain scenarios, but does not automatically create a safe rollback path.

After cutover, the application may already have written new data into the new table. Renaming back to the old table without syncing post-cutover changes loses new data. Therefore:

- Retain the old table only for a defined window and protect it from accidental deletion.
- Never treat reverse-renaming as a complete rollback once post-cutover writes occur.
- If the schema is wrong while data remains intact, evaluate a forward-fix migration or reverse synchronization.
- If data loss or corruption occurs, halt writes per incident protocol, preserve logs and backups, and identify recovery points.
- Never drop the old table or ghost table before verifying final state.

If the tool stops mid-run, read logs to determine whether it stopped during table creation, copying, syncing, or cutover. Never immediately re-run with the same auxiliary table names without checking leftover temp tables and triggers. Use the cleanup commands appropriate for your exact tool and version after understanding their impact.

## 15. Decision matrix

| Environment condition | Evaluation direction |
|---|---|
| Table has critical existing triggers | Check `pt-osc` `--preserve-triggers`, MySQL version, and whether triggers touch altered columns; `gh-ost` does not support triggers per current docs |
| Table has referencing foreign keys | Analyze `rebuild_constraints` or `drop_swap` risks with `pt-osc`; `gh-ost` does not support foreign keys per current docs |
| Binary logs not `ROW` or wrong row image | Do not run `gh-ost` until binlog requirements and topology impacts are resolved |
| High write rate table | Evaluate `pt-osc` trigger overhead vs. `gh-ost` binlog read/apply throughput; test under realistic load |
| Replica lag already elevated | Delay migration or throttle down; never start just because the primary has spare headroom |
| Insufficient disk for source + ghost table | Do not run; expand storage or design a multi-phase migration |
| DDL safely supports `INSTANT` | Evaluate native MySQL DDL first |
| Table lacks a suitable unique key | Redesign keys or choose another migration strategy after testing |
| Manual cutover control required | Evaluate `gh-ost` postpone-cut-over flags and `pt-osc` cutover controls |

This table is a directional guide, not a substitute for checking version documentation. Specific limitations may change across tool releases.

## 16. Final checklist

- [ ] Checked whether `ALTER` can use MySQL `INSTANT`/`INPLACE`.
- [ ] Reviewed DDL and inspected PK/unique keys, FKs, triggers, and partitions.
- [ ] Confirmed supported MySQL and tool versions.
- [ ] Verified minimal privileges for the migration account.
- [ ] Measured table size, disk capacity, and write rate.
- [ ] Verified binlogs and topology if using `gh-ost`.
- [ ] Evaluated trigger cost and FK strategy if using `pt-osc`.
- [ ] Rehearsed with production-like data and load.
- [ ] Configured max-load, critical-load, and replica-lag thresholds.
- [ ] Checked long transactions and metadata locks before cutover.
- [ ] Assigned an owner to approve cutover timing and halt if needed.
- [ ] Verified schema, data, indexes, application, and replicas post-migration.
- [ ] Prepared old-table retention, backups, and data recovery procedures.

## References

- [Percona Toolkit — pt-online-schema-change](https://docs.percona.com/percona-toolkit/pt-online-schema-change.html)
- [Percona Toolkit — --alter-foreign-keys-method](https://docs.percona.com/percona-toolkit/pt-online-schema-change.html#alter-foreign-keys-method)
- [GitHub gh-ost — Requirements and limitations](https://github.com/github/gh-ost/blob/master/doc/requirements-and-limitations.md)
- [GitHub gh-ost — User guide](https://github.com/github/gh-ost/blob/master/doc/README.md)

## Conclusion

Both `pt-online-schema-change` and `gh-ost` minimize disruption when altering large tables by creating a new table, copying data, and syncing live changes prior to cutover. `pt-osc` uses triggers, requiring careful evaluation of write load, existing triggers, and foreign keys. `gh-ost` uses binary logs, requiring row-based logging, compatible row images, sufficient retention, and a supported topology. Both can still wait on metadata locks and consume substantial resources. Prefer native online DDL when suitable, choose tools based on table constraints, rehearse realistically, monitor load, and keep verified recovery plans ready.
