# Online Schema Change Using Shadow Tables, Triggers, or Binary Logs

Changing the schema on a large MySQL table can take a long time and directly affect the application. An `ALTER TABLE` statement may have to rebuild the table, read and write millions of rows, build indexes, generate heavy I/O load, or hold metadata locks at the start and end. If deployed improperly, schema changes can spike latency, cause replica lag, or block application writes during cutover.

**Online schema change** refers to techniques that alter a table's structure while the system continues serving most queries. Common methods include MySQL's built-in online DDL, creating a shadow table and syncing changes via triggers, or creating a shadow table and replaying changes from the binary log. Tools like `pt-online-schema-change` and `gh-ost` implement the latter two approaches.

No method guarantees zero locking. Both built-in online DDL and shadow-table tools require brief metadata locks at critical moments. Proper design selects a method based on change type, table size, primary key, foreign keys, replication topology, observability, and downtime budget.

This lesson uses MySQL 8.0 and the terms `SOURCE`/`REPLICA`. Online DDL capabilities, tool requirements, and specific options vary by version; always test on the exact target version and table structure before running in production.

## Learning objectives

After this lesson, you will be able to:

- Distinguish built-in online DDL from shadow-table-based online schema change.
- Describe how triggers and binary logs synchronize changes while data is being copied.
- Choose between native DDL, `pt-online-schema-change`, and `gh-ost` based on table characteristics.
- Identify requirements for primary keys, triggers, foreign keys, binary logs, and replication.
- Plan chunked copying, throttling, cutover, and metadata lock handling.
- Deploy schema changes using expand-contract so the application stays compatible throughout.
- Verify data, replicas, and recoverability after the change.

## 1. Why is online schema change needed?

Suppose the `orders` table has hundreds of millions of rows and needs a new column, a data type change, or an index added. A DDL statement may perform one of the following:

- Modify metadata without rebuilding the entire table.
- Alter structure while still allowing certain concurrent reads/writes.
- Create a table copy, copy data into the new structure, and rename tables.

Cost depends on DDL type, storage engine, MySQL version, row width, indexes, constraints, and concurrent load. Adding a column may be `INSTANT` on supported versions, whereas changing a column type or row format may require a rebuild. Never infer from an operation's name alone that it is always fast or lock-free.

Online schema change is typically considered when:

- The table is large and copy/rebuild duration exceeds an acceptable maintenance window.
- The application must continue reading and writing while data migrates to the new structure.
- Native DDL does not offer an acceptable algorithm/lock for the required change.
- Copy speed, replica lag, and cutover timing must be tightly controlled.

For small tables or DDLs supported via `ALGORITHM=INSTANT`, native DDL is usually simpler with fewer operational moving parts. Shadow-table tools carry additional storage and write overhead, so they are not the default choice for every change.

## 2. Evaluate native online DDL first

MySQL InnoDB supports different DDL algorithms. The three common names are:

| Algorithm | General mechanism | Cost and limits |
|---|---|---|
| `INSTANT` | Modifies metadata without rebuilding the entire table in supported cases | Fast, low I/O; applies only to specific operations and version-dependent conditions |
| `INPLACE` | InnoDB applies changes internally; may or may not rebuild depending on DDL | May allow concurrent reads/writes yet consume heavy I/O, CPU, and disk space |
| `COPY` | Builds a new table copy and copies data | Usually slow with concurrency limits; can block writes for most of the operation |

`INPLACE` does not mean no rebuild. `INSTANT` also does not mean all subsequent operations are free: MySQL still updates metadata, checks conditions, and may wait on metadata locks.

### 2.1. Checking algorithms and locks

Before running DDL, check version and operation support. On MySQL 8.0.18 and newer, use `EXPLAIN ALTER TABLE` to inspect the expected DDL plan:

```sql
EXPLAIN ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL;
```

This is a prediction step and does not replace testing on a representative data clone. You can explicitly require an algorithm and lock level so MySQL errors out if unable to comply:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM = INSTANT;
```

Or for operations supporting concurrent DML:

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_created_at (created_at),
  ALGORITHM = INPLACE,
  LOCK = NONE;
```

`LOCK=NONE` instructs MySQL to allow concurrent reads and writes during DDL phases where supported by the operation. If unsupported, MySQL fails rather than silently switching to a stricter lock. However, preparation and completion phases still require metadata locks.

### 2.2. Metadata locks

MySQL uses metadata locks (MDL) to protect table definitions while sessions access objects. DDL needs exclusive metadata locks at certain points. A long transaction holding a shared metadata lock can force `ALTER TABLE` to wait; while DDL waits, incoming queries can queue behind it depending on lock rules.

Before changing schemas:

- Check for long transactions and sessions holding tables open.
- Avoid starting migrations during long batch jobs or reports.
- Monitor `performance_schema.metadata_locks` and the process list.
- Set an appropriate wait timeout, such as `lock_wait_timeout`, in the migration session.
- Prepare a way to abort waiting DDL before it forms a query queue.

Inspect metadata locks:

```sql
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
```

Correlate results with `performance_schema.threads` or `SHOW PROCESSLIST` to identify sessions holding or waiting on locks. Never kill a session from a single result row alone; identify the transaction owner and business impact first.

## 3. The shadow table pattern

Online schema change tools generally create a shadow table with the new structure, copy data from the original table to the shadow table, synchronize ongoing changes occurring during the copy, and swap table names at cutover.

General flow:

```text
               Original table: orders
             (serving live application)
                        |
              +---------+---------+
              |                   |
         Chunked copy      New DML from app
              |                   |
              v                   v
        Shadow table: orders_new <--- sync changes
              |
              |  verify data and lag
              v
        Wait for cutover window
              |
              v
        Atomic multi-table rename
              |
              v
        orders = new table
        orders_old = old table (retained temporarily)
```

During copying, the original table continues serving reads and writes. The shadow table gradually fills and receives live updates. Once both tables are synchronized, the tool acquires metadata locks to rename or swap the tables. Cutover is usually much shorter than a full-table rebuild, yet can still be blocked by long transactions.

Two common synchronization methods:

- **Trigger-based:** triggers on the original table mirror changes into the shadow table.
- **Binlog-based:** the tool reads row events from the binary log and applies them to the shadow table.

Do not hand-roll shadow tables with custom triggers or binlog sync without handling event ordering, primary keys, error retries, concurrent DDL, foreign keys, and cutover thoroughly. Dedicated tools already address many of these edge cases, though they still require proper configuration and monitoring.

## 4. Trigger-based sync: pt-online-schema-change

`pt-online-schema-change` (`pt-osc`) is part of Percona Toolkit. It creates a new table with the altered structure, installs triggers on the original table to sync DML, copies data in chunks, and swaps the tables.

### 4.1. How it works

General workflow:

1. Read the original table definition and create a shadow table with the requested schema changes.
2. Create triggers on the original table to mirror `INSERT`, `UPDATE`, and `DELETE` into the shadow table.
3. Copy existing rows in chunks over a suitable index.
4. Monitor system load and replication lag; throttle copy speed or pause.
5. Once copying finishes, wait for cutover conditions and metadata locks.
6. Rename the original and shadow tables in an atomic multi-table rename.
7. Clean up the old table and triggers per the chosen retention/rollback policy.

Triggers reflect new changes into the shadow table immediately while historical data copies. However, triggers run synchronously inside the application's transaction, adding extra work to every DML statement and potentially increasing latency. If a trigger fails, the originating DML fails with it; factor this into your risk assessment.

### 4.2. Requirements and limitations

- The table needs a suitable primary key or unique index so the tool can chunk copy and identify rows.
- The tool account needs privileges to inspect schemas, create/drop tables, create triggers, manipulate data, and rename tables as required by the tool/version.
- Tables with pre-existing triggers must be carefully checked. Multi-trigger support and how `pt-osc` interacts with existing triggers depend on MySQL and Percona Toolkit versions.
- Foreign keys referencing the original table complicate cutover because child tables must point to the new table after rename.
- Triggers can conflict with application logic, auditing, or replication filters; never run concurrent migrations on the same table.
- Track shadow table, trigger, and old table names to avoid accidentally deleting data after a failed migration.

If a table lacks a primary key or suitable unique index, do not force `pt-osc` hoping it handles it automatically. Evaluate adding a key first, using native DDL, or selecting another approach.

### 4.3. Dry-run and execution examples

The example below illustrates adding a column in dry-run mode:

```bash
pt-online-schema-change \
  --alter "ADD COLUMN source_channel VARCHAR(30) NULL" \
  --dry-run \
  D=app,t=orders
```

After verifying the plan, privileges, triggers, foreign keys, and load test, execute the real migration following your approved workflow:

```bash
pt-online-schema-change \
  --alter "ADD COLUMN source_channel VARCHAR(30) NULL" \
  --execute \
  D=app,t=orders
```

This is a syntax illustration, not a complete production command. Configure secure connections, load/replica-lag thresholds, cutover wait timeouts, foreign-key handling, and old-table retention rules. Never pass passwords directly on the command line or leave secrets in shell history.

Commonly used options:

| Option | Purpose |
|---|---|
| `--dry-run` | Build and test the execution plan without performing the full migration |
| `--execute` | Perform the actual schema change |
| `--chunk-time` | Dynamically size chunks based on target execution duration |
| `--max-load` | Pause when specified status variables exceed load thresholds |
| `--critical-load` | Abort migration when load crosses critical thresholds |
| `--max-lag` | Throttle based on replica lag monitored by the tool |
| `--alter-foreign-keys-method` | Choose how child tables with foreign keys referencing the altered table are updated |

Exact option names and behaviors depend on the Percona Toolkit version. Read `pt-online-schema-change --help` and version docs; notably, never pick a foreign-key method blindly just to make a migration proceed without evaluating lock time and integrity.

### 4.4. Foreign keys and cutover

When other tables reference `orders`, renaming tables can leave foreign key constraints pointing to the old table or require the tool to update child table constraints. Certain methods rebuild child tables or introduce a sensitive swap window.

Before migrating tables with foreign keys:

- List every child table and referencing constraint.
- Check child table row counts and sizes.
- Review the exact impact of `--alter-foreign-keys-method` in your tool version.
- Estimate lock duration and disk space needed if child tables rebuild.
- Test both the happy path and delayed cutover scenarios.

If foreign-key handling exceeds downtime limits, pick a different schema strategy or schedule an explicit maintenance window. Never drop constraints in production just to simplify cutover unless equivalent integrity protections exist.

## 5. Binary-log sync: gh-ost

`gh-ost` is an online schema migration tool that reads binary logs to capture changes on the original table and apply them to the shadow table. It does not install triggers on the original table; instead, it consumes row events from the binlog and orchestrates shadow-table copying and updates.

### 5.1. How it works

General flow:

1. Create the ghost table with the new schema.
2. Copy existing rows in chunks into the ghost table.
3. Read the binary log to follow ongoing changes to the original table.
4. Apply row events onto the ghost table in the required order.
5. Throttle copy speed based on load, replica lag, or throttle signals.
6. Once data is synchronized, perform cutover via a controlled table rename.

By avoiding triggers on the original table, `gh-ost` eliminates per-DML trigger overhead. In exchange, it depends strictly on binary logs, row event format, retention, and the tool's ability to parse and apply binlog events.

### 5.2. Prerequisites to verify

- Binary logging must be enabled on the server providing events.
- `binlog_format=ROW` is a critical requirement for row-event-based synchronization.
- `binlog_row_image=FULL` is required for common `gh-ost` versions; do not assume `MINIMAL` provides enough information to apply row events.
- If `gh-ost` reads binlogs from a replica rather than the primary, the replica generally requires `log_replica_updates=ON` so upstream events appear in its local binlog.
- Binary logs must be retained long enough so the tool never loses events mid-migration.
- The table needs a suitable primary key or unique key for chunking and row identification.
- `gh-ost` does not support migrating tables with foreign keys; if the table or referencing relationships have foreign keys, choose another method or verify exact limits of your tool version before designing.
- Check existing triggers, partitioning, replication topology, and table features supported by your `gh-ost` version.

Check binlog settings and available log files:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'binlog_format',
  'binlog_row_image',
  'log_replica_updates',
  'binlog_expire_logs_seconds'
);

SHOW BINARY LOGS;
```

On older MySQL versions, `log_replica_updates` may be named `log_slave_updates`. Never assume `gh-ost` supports every table feature; verify the support matrix for your exact version first.

### 5.3. Throttling and binlog source

`gh-ost` can read binlogs from the primary or a designated replica. Reading from a replica can offload read traffic from the primary, but requires the replica to have full binlogs and `log_replica_updates` enabled. Ensure that replica does not lag heavily and the tool connects to the right source.

Throttling slows copying when the system gets busy. You can track replica lag, MySQL load, query latency, and other operational signals. If a binlog file is purged before the tool reads it, the migration cannot safely continue; stop and reassess state rather than skipping events.

Illustrative `gh-ost` command skeleton:

```bash
gh-ost \
  --host=db-primary.example \
  --user=gh_ost \
  --database=app \
  --table=orders \
  --alter="ADD COLUMN source_channel VARCHAR(30) NULL" \
  --allow-on-master \
  --throttle-control-replicas="db-replica-1.example" \
  --max-load="Threads_running=40" \
  --critical-load="Threads_running=80" \
  --execute
```

Parameters above are illustrative only; host selection, replica flags, privileges, flags permitting execution on primary, and load thresholds depend on your topology and `gh-ost` version. Run dry checks first, inspect output, verify binlog settings, and use secure configuration files for credentials. Never copy `Threads_running` thresholds blindly across environments.

### 5.4. When binary logs are insufficient

If binlogs are purged, change format, lack full row images, or the tool cannot read events within the retention window, the ghost table will not reflect all changes from the original table. Never cut over in that state. Determine the last applied binlog position, inspect data, and restart the migration safely if needed.

## 6. Comparing pt-osc, gh-ost, and native DDL

| Criterion | Native online DDL | pt-online-schema-change | gh-ost |
|---|---|---|---|
| Mechanism | InnoDB DDL algorithms | Shadow table + triggers | Shadow table + binlog events |
| Original table impact | Handled directly by MySQL | Installs triggers on original table | Reads binlogs; no sync triggers on original table |
| Extra write load | Depends on DDL and algorithm | Triggers run inline with DML, adding write cost | Tool reads/applies binlogs and writes ghost table |
| Binlog requirement | Not a general DDL requirement | Consider replication and binlogs per topology | Core synchronization source |
| Existing triggers | Creates no migration triggers | Can conflict or depend on version support | Uses no migration triggers, though table limits still apply |
| Foreign keys | Handled by MySQL DDL | Has dedicated methods, can be complex | Unsupported for tables with foreign keys in common versions |
| Load throttling | More limited control | Chunk/load/lag controls | Flexible throttling and cutover controls |
| Cutover | Finalizes DDL and metadata lock | Table rename, requires metadata lock | Table rename, requires metadata lock |
| Operational complexity | Lower if DDL fits | Higher; manage triggers and FKs | Higher; manage binlogs and topology |

Choose native DDL when supported with an acceptable algorithm and lock level. Choose `pt-osc` when trigger-based copying fits the table and topology. Consider `gh-ost` when avoiding triggers, having suitable row-based binlogs, and staying clear of tool limits. With foreign keys or special table features, test thoroughly or schedule a maintenance window.

## 7. Application design with expand-contract

Online schema change solves only the structural change piece. The application must also stay compatible with both old and new schemas throughout rollout. The **expand-contract** pattern divides migrations into backward-compatible steps.

Suppose `orders.customer_name` needs to become `customer_display_name`:

### Phase 1: Expand

Add the new column while keeping the old column:

```sql
ALTER TABLE orders
  ADD COLUMN customer_display_name VARCHAR(200) NULL,
  ALGORITHM = INSTANT;
```

Use `INSTANT` only when supported by your version and table structure. Otherwise select an evaluated DDL or tool.

### Phase 2: Dual write or read compatibility

Deploy code capable of writing both columns or writing the new column while maintaining old data during transition. Avoid letting old instances fail to recognize the new column or new instances assume backfill has already completed.

### Phase 3: Backfill

Populate legacy values into the new column in checkpointed batches:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE id > 0
  AND id <= 10000
  AND customer_display_name IS NULL;
```

The application or job iterates over successive primary-key ranges, commits each batch, and saves checkpoints. The query above illustrates a single batch; tailor predicates and batch size to indexes, load, and actual data.

### Phase 4: Switch reads

After reconciling row counts and values, switch the application to read the new column. Monitor errors and business metrics during an observation period.

### Phase 5: Contract

Once no application versions depend on the old column, drop it in a separate migration:

```sql
ALTER TABLE orders
  DROP COLUMN customer_name;
```

Dropping a column may require a rebuild or different algorithm depending on version; evaluate beforehand. Keeping both columns during transition eases application rollback, though you must define when dual-writing stops and which column is authoritative.

## 8. Planning a production migration

A safe migration starts by gathering table and workload details:

```sql
SHOW CREATE TABLE app.orders\G
SHOW TABLE STATUS FROM app LIKE 'orders'\G
SHOW INDEX FROM app.orders;
```

Also inspect:

- Row counts, data size, and index size.
- Primary key, unique keys, foreign keys, partitions, and existing triggers.
- Key read/write queries, long transactions, and peak traffic windows.
- Binary log format, row image, retention, and replica topology.
- Disk space for shadow tables, binlogs, relay logs, temporary files, and backups.
- Account, privileges, and connectivity for the migration tool.
- Application compatibility with the schema at every stage.

### 8.1. Pre-testing

Test on a clone close to production size and workload. Measure:

- Shadow table creation time and copy throughput.
- CPU, disk I/O, disk growth, and network throughput.
- Latency impact on live DML against the original table.
- Replica lag and binlog apply time.
- Metadata lock wait and cutover duration.
- Tool behavior when throttled, paused, restarted, or encountering errors.

Do not measure average runtime alone. Track p95/p99 latency and impact on critical queries during the migration.

### 8.2. Load throttling

Set load thresholds from production baselines. Pause or slow copying when:

- `Threads_running` or CPU exceeds limits.
- Replica lag breaches SLOs.
- Disk utilization or I/O latency spikes.
- Transaction lock waits rise.
- Free disk space risks running short for shadow tables and binlogs.

Never hardcode generic thresholds. Thresholds must reflect normal traffic, replica capacity, and application latency targets.

### 8.3. Cutover and metadata locks

Before cutover:

1. Confirm copying is complete and all ongoing changes are applied.
2. Check replica lag and tool status.
3. Identify long sessions/transactions that could hold MDL.
4. Pick a low-traffic window and notify operations/application teams.
5. Set lock wait timeouts and watch query queues.
6. Allow rename only after the tool confirms data synchronization.
7. Verify the table after cutover before cleaning up the old table.

Atomic rename swaps table names in one metadata operation, yet does not eliminate locks or wait times. If cutover cannot acquire metadata locks, delaying is usually safer than forcing execution without understanding which session holds the lock.

## 9. Post-migration verification and recovery plans

After cutover, verify:

- `SHOW CREATE TABLE` confirms the expected new schema.
- Required indexes, unique constraints, foreign keys, and triggers are intact.
- Row counts and key business aggregates match baseline.
- Core read/write queries work and execution plans did not regress unexpectedly.
- Replicas caught up without applier errors and GTID/binlog progression continues.
- Fresh backups succeed and PITR procedures remain intact.
- The application is not querying wrong columns or assuming old schema layout.

Basic verification queries:

```sql
SHOW CREATE TABLE app.orders\G
SELECT COUNT(*) FROM app.orders;
SHOW INDEX FROM app.orders;
```

Full `COUNT(*)` on huge tables can be costly; choose verification suited to table size and requirements, such as primary-key range stats or chunked checksums. Never treat matching row counts alone as full proof that all column values match.

### 9.1. Retaining the old table and rollback

After cutover, tools can retain the old table temporarily to aid investigation or rollback. However, once the application writes new data to the new table, the old table quickly becomes stale. Renaming back to the old table would lose transactions committed after cutover.

Therefore:

- Explicitly define old-table retention duration and deletion criteria.
- Never treat the old table as a consistent backup once writes resume on the new table.
- If data rollback is needed, prepare reverse synchronization or backup/binlog recovery.
- Check disk capacity before keeping two copies of a huge table simultaneously.
- Drop the old table only after application, data, and replication are verified.

Application rollback and schema rollback are separate concerns. Expand-contract supports reverting application versions during the compatibility window, whereas reverting data written after cutover requires a dedicated data strategy.

## 10. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| `ALTER TABLE` waits long despite `LOCK=NONE` | Waiting on metadata lock at start/completion phase | Find transaction holding MDL, check process list, and cap wait timeout |
| `pt-osc` fails to create triggers | Missing privileges, existing triggers, or unsupported table layout | Check grants, triggers, and Percona Toolkit version |
| `pt-osc` raises write latency | Sync triggers add DML work to shadow table | Reduce chunk/load thresholds, monitor latency, or evaluate another method |
| Foreign keys prolong cutover | Child tables need constraint updates or rebuilds | Evaluate FK method and test on representative data |
| `gh-ost` fails reading binlogs | Wrong binlog format/row image, privileges, or binlog source | Verify configuration, replication privileges, and log retention |
| Migration misses events | Binlogs purged before tool read them | Do not cut over; reassess checkpoint and rebuild migration |
| Replica lag spikes | Copy/apply generates heavy load or replica lacks capacity | Throttle/pause, extend migration window, and tune load limits |
| Disk space exhaustion | Shadow table, binlogs, and temp files grow together | Pause safely, free or add disk space per plan |
| Rollback rename loses new data | Old table missed post-cutover writes | Recover via backup/binlog or planned data sync |

## 11. Practice exercise

An `app.orders` table has 80 million rows, InnoDB, primary key `id`, several secondary indexes, and two child tables referencing it via foreign keys. The application handles steady write traffic all day. The team needs to add `source_channel`, create an index on `created_at`, and later rename a legacy column once the application switches to the new name.

Design a migration plan:

1. Which changes should be tried with native DDL first? How will you check algorithm and lock behavior?
2. If native DDL cannot meet runtime or lock limits, how do `pt-osc` and `gh-ost` differ in sync mechanics?
3. For the two child tables with foreign keys, what must be investigated before using `pt-osc` or `gh-ost`?
4. If using `pt-osc`, how do triggers affect write latency and migration account privileges?
5. If using `gh-ost`, how do you verify `binlog_format`, `binlog_row_image`, `log_replica_updates`, and retention?
6. Propose throttling thresholds based on baseline CPU, `Threads_running`, disk I/O, and replica lag.
7. How do you prevent metadata locks held by long transactions during cutover?
8. Write an expand-contract plan for renaming the column, covering dual writes, backfill, read switch, and dropping the old column.
9. After cutover and new application writes, why can you not simply rename the old table back?
10. List post-migration checks for schema, data, execution plans, replication, and backups.

A solid plan specifies the chosen tool, rationale, disk headroom, throttling rules, cutover preconditions, old-table retention window, and abort criteria. Rehearse both mid-copy stops and cutover blocked by metadata locks.

## Conclusion

Online schema change enables altering large tables while the application continues operating for most of the process. Native online DDL should be evaluated first due to fewer operational parts; when a shadow table is required, `pt-online-schema-change` uses triggers to sync DML while `gh-ost` reads binary logs to apply changes. Every approach requires an appropriate primary key, storage headroom, load controls, and a metadata-lock cutover plan. Combining expand-contract, data verification, replica monitoring, and a clear rollback strategy keeps migrations controllable and recoverable when incidents occur.
