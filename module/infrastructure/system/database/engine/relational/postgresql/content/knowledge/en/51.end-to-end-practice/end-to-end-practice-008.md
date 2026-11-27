# Designing Time-Series Data with Partitioning and Retention Policies

Time-series data appears across many PostgreSQL systems: application events, logs, transactions, status histories, device telemetry, audit trails, and analytical records. These tables tend to grow continuously, are queried over time ranges, and carry explicit retention periods. When modeled as a single unbounded table, querying, maintenance, backups, and purging old data grow increasingly expensive.

PostgreSQL declarative partitioning lets you split a logical table into multiple physical tables based on a partition key. For time-series data, `RANGE` partitioning on a timestamp is typically the natural fit: each partition holds a time slice such as a day or a month. Combined with a retention policy, teams can drop entire expired partitions far faster than deleting rows one by one.

A sound design must simultaneously address choosing the partition key and size, writing queries so partition pruning activates, pre-creating partitions on schedule, handling late-arriving data, archiving or purging expired data, and governing backups, access permissions, and compliance requirements. Partitioning is a data-management mechanism; it does not automatically make every query faster or enforce retention policies on its own.

## 1. Why Does Time-Series Data Require Dedicated Design?

### 1.1. Characteristics of Time-Series Workloads

A time-series table typically exhibits these traits:

- New data arrives continuously or in frequent batches.
- Most queries filter by a time range.
- Older data is rarely updated, yet may still need to be queried or archived.
- Storage grows steadily and predictably from ingest velocity.
- Some datasets have retention limits measured in days, months, or years.
- Whole-table maintenance grows increasingly heavy as the table expands.

For example, a `telemetry.events` table stores device events. The application frequently requests events for a device over the past 24 hours, aggregates daily counts, or inspects errors over a week. A single monolithic table holding years of data causes indexes and maintenance operations to balloon.

### 1.2. What Does Partitioning Solve?

Partitioning creates a parent table (partitioned table) acting as the logical interface and child tables (partitions) holding the physical rows. PostgreSQL routes writes to the appropriate partition based on the partition key. When a query carries a matching filter, the planner can skip irrelevant partitions before reading data—a mechanism known as partition pruning.

Common benefits:

- Time-range queries scan only relevant partitions.
- Indexes, storage parameters, and maintenance can be tailored per partition.
- Expired data can be detached, archived, or dropped in bulk.
- Data can be loaded by time slice with a clear lifecycle.
- Vacuum, analyze, and index maintenance scope can be bounded per partition.

Costs and limitations to weigh:

- Every partition is a separate relation, multiplying metadata and index objects.
- Too many partitions increase planning time, catalog overhead, and operational complexity.
- Unique constraints on a partitioned table must include the partition key per PostgreSQL rules.
- DDL to add, detach, or drop partitions can acquire locks and affect concurrent queries.
- Queries lacking a filter on the partition key may still touch many or all partitions.
- Autovacuum, analyze, privileges, and monitoring must be observed across physical partitions.

Partitioning does not replace indexing, query design, or capacity planning. Benchmark with representative data and queries before settling on partition counts and sizes.

## 2. Choosing a Partitioning Strategy

PostgreSQL supports three primary declarative partitioning strategies:

| Strategy | How Data Is Split | Common Use Cases |
|---|---|---|
| `RANGE` | Contiguous, non-overlapping value intervals | Timestamps, dates, sequence numbers, or ID ranges. |
| `LIST` | Discrete sets of explicit values | Regions, event types, or small tenant groups. |
| `HASH` | Hash result of the key with modulus/remainder | Spreading rows evenly when no natural range or list exists. |

### 2.1. `RANGE` by Time

For time-series data, `RANGE` is the most common strategy. Each partition spans a half-open interval: inclusive of the lower bound, exclusive of the upper bound.

Example partition for November 2026:

```sql
CREATE TABLE telemetry.events_2026_11
PARTITION OF telemetry.events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
             TO ('2026-12-01 00:00:00+00');
```

The interval `[2026-11-01, 2026-12-01)` ensures an event at exact midnight on December 1 lands cleanly in December's partition with zero overlap. Follow the same half-open boundary rule for daily or hourly partitions.

### 2.2. `LIST` by Group

`LIST` suits a small, stable set of categorical values, such as severity levels:

```sql
CREATE TABLE telemetry.alerts (
    occurred_at timestamptz NOT NULL,
    alert_id uuid NOT NULL,
    severity text NOT NULL,
    payload jsonb
) PARTITION BY LIST (severity);

CREATE TABLE telemetry.alerts_critical
PARTITION OF telemetry.alerts
FOR VALUES IN ('critical');

CREATE TABLE telemetry.alerts_warning
PARTITION OF telemetry.alerts
FOR VALUES IN ('warning');

CREATE TABLE telemetry.alerts_other
PARTITION OF telemetry.alerts
DEFAULT;
```

For large time-series datasets, `LIST` partitioning by tenant or severity can spawn too many partitions if distinct values grow unchecked. If you need both time and group splits, subpartitioning is possible, provided you evaluate total resulting partition counts carefully.

### 2.3. `HASH` by Key

`HASH` distributes rows into buckets, useful when spreading a table across tenants or keys lacking natural ranges:

```sql
CREATE TABLE telemetry.events_by_tenant (
    tenant_id bigint NOT NULL,
    event_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY HASH (tenant_id);

CREATE TABLE telemetry.events_by_tenant_0
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE telemetry.events_by_tenant_1
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE telemetry.events_by_tenant_2
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE telemetry.events_by_tenant_3
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

`HASH` creates no time ordering. If monthly retention is required, `HASH` alone cannot detach or drop expired rows by date. You can use `RANGE` by time as the outer level and `HASH` as the inner level if there is a clear justification.

## 3. Choosing the Partition Key and Partition Size

### 3.1. Choosing the Right Timestamp Column

Common candidates:

- `occurred_at`: when the event actually happened.
- `ingested_at`: when the system received or recorded the event.
- `created_at`: when the record was created in the application.
- `business_date`: business date under a specific time zone or calendar.

Pick the column aligning with your query filters and retention policy. If you partition by `occurred_at`, late-arriving data may have to be written into historical partitions. If you partition by `ingested_at`, late arrivals land easily in the current partition, yet queries filtering only by `occurred_at` will not prune partitions effectively unless an `ingested_at` bound is also provided.

Never pick a timestamp column simply because one happens to exist. Clarify timestamp semantics, clock sources, time zones, late-arrival likelihood, and when the retention clock starts.

### 3.2. Use `timestamptz` and Standardize on UTC

For system-wide points in time, `timestamptz` is generally superior to `timestamp without time zone`. PostgreSQL stores instants in normalized UTC form and formats them using the session `TimeZone`. The column does not store the original time-zone name; if you need the source local time zone for business logic, store that zone identifier separately.

A clean operational convention is aligning partition boundaries to UTC months. Note that a local business day in another time zone will not align with UTC midnight boundaries. If retention or reporting follows a local calendar, explicitly convert timestamps when defining boundaries and writing queries.

Example determining the start of the UTC month:

```sql
SELECT date_trunc('month', now() AT TIME ZONE 'UTC') AS utc_month_start;
```

Avoid constructing boundaries from offset-less timestamp strings when sessions may use differing time zones. Include `+00` in DDL or generate explicit `timestamptz` values.

### 3.3. Choosing Daily, Monthly, or Quarterly Partitions

No single partition interval fits every workload. Choose granularity based on:

- Daily row volume and byte growth.
- Query volume and typical time windows accessed.
- Granularity required for retention and archiving.
- Total projected partitions over the data lifecycle.
- Time required for index builds, vacuum, analyze, and backups.
- Catalog limits, planning time, and operational tooling capacity.

| Interval | Advantages | Costs / Risks |
|---|---|---|
| Hourly | Very fine-grained purge/archive; tiny partitions | Partition count explodes rapidly; high overhead. |
| Daily | Suits high ingest rates and day-level retention | Can accumulate thousands of partitions over several years. |
| Monthly | Easy to manage, moderate partition count, aligns with month/year retention | Individual partitions can grow huge at extreme ingest rates; purging isn't day-exact. |
| Quarterly / Yearly | Fewest partitions and simplest DDL | Large partitions, slower per-partition vacuum/index/restore; coarse retention. |

For example, a table ingesting millions of rows daily may warrant daily or monthly partitions depending on row width and query patterns. A low-volume audit table may only need monthly or quarterly partitions. Benchmark index creation and vacuum timings on expected partition sizes.

### 3.4. Avoiding Over-Partitioning

Too many partitions inflate relation counts, index counts, catalog entries, planning overhead, and operational work. A query lacking a time predicate may have to inspect hundreds or thousands of partitions. Every partition also requires indexes and maintenance.

Add subpartitioning only when there is a measurable benefit—such as shrinking per-tenant indexes or isolating contention on a hot partition. Never subpartition across hundreds of thousands of tenants when time `RANGE` partitioning paired with a tenant index suffices.

## 4. Designing Partitioned Tables in PostgreSQL

### 4.1. Creating a Time-Based `RANGE` Parent Table

Example telemetry events table:

```sql
CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE telemetry.events (
    occurred_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    tenant_id bigint NOT NULL,
    device_id bigint NOT NULL,
    event_type text NOT NULL,
    value double precision,
    attributes jsonb,
    PRIMARY KEY (occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);
```

The partition key is `occurred_at`. The primary key includes both `occurred_at` and `event_id`. PostgreSQL requires any unique constraint or primary key on a partitioned table to include all partition key columns so uniqueness can be verified locally per partition without a global index.

If business rules require `event_id` to be globally unique across the entire table, the constraint above only enforces uniqueness of the `(occurred_at, event_id)` pair. There is no built-in global unique index spanning partitions to forbid duplicate `event_id` values across different partitions. Use sufficiently random UUIDs to minimize collision risk, coordinate sequences at the application tier, or maintain a separate non-partitioned registry table if strict global uniqueness is mandatory. Never assume the composite primary key guarantees global uniqueness of `event_id` alone.

### 4.2. Creating Monthly Partitions

```sql
CREATE TABLE telemetry.events_2026_11
PARTITION OF telemetry.events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
             TO ('2026-12-01 00:00:00+00');

CREATE TABLE telemetry.events_2026_12
PARTITION OF telemetry.events
FOR VALUES FROM ('2026-12-01 00:00:00+00')
             TO ('2027-01-01 00:00:00+00');

CREATE TABLE telemetry.events_2027_01
PARTITION OF telemetry.events
FOR VALUES FROM ('2027-01-01 00:00:00+00')
             TO ('2027-02-01 00:00:00+00');
```

Partition names should clearly reflect their time ranges using a consistent format like `events_YYYY_MM`. When reading logs, catalogs, or dashboards, operators can identify partitions immediately without decoding arbitrary names.

### 4.3. Creating Indexes on the Parent Table

Creating a partitioned index on the parent causes PostgreSQL to create corresponding indexes on existing partitions and attach indexes automatically for future partitions:

```sql
CREATE INDEX events_tenant_time_idx
ON telemetry.events (tenant_id, occurred_at DESC);

CREATE INDEX events_type_time_idx
ON telemetry.events (event_type, occurred_at DESC);
```

Indexes should mirror actual queries. Avoid adding excessive indexes on ingest-heavy tables because every insert must update each partition's indexes. For very large tables appended roughly in chronological order, BRIN can save substantial space compared to B-tree for certain range scans:

```sql
CREATE INDEX events_occurred_at_brin_idx
ON telemetry.events
USING brin (occurred_at)
WITH (pages_per_range = 128);
```

BRIN works well when column values correlate closely with physical page placement. If late-arriving data scrambles physical insertion order relative to event timestamps, BRIN effectiveness drops. Measure with `EXPLAIN (ANALYZE, BUFFERS)`.

### 4.4. Partition-Specific Storage Parameters

You can set storage parameters per individual partition. For instance, lowering `fillfactor` or tuning autovacuum scale factors on a partition with unusual update patterns:

```sql
ALTER TABLE telemetry.events_2026_11 SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
);
```

These values are examples and must be tuned from observed metrics. Each partition is a physical relation and can carry its own `reloptions`. Apply policies consistently when creating new partitions and monitor so old and new partitions do not drift into wildly inconsistent maintenance behavior.

### 4.5. The `DEFAULT` Partition

You can create a `DEFAULT` partition to catch rows matching no defined range:

```sql
CREATE TABLE telemetry.events_default
PARTITION OF telemetry.events DEFAULT;
```

`DEFAULT` prevents insert failures when a partition is missing, yet it can mask broken partition-creation automation. It also complicates adding future partitions: PostgreSQL must verify that no rows inside `DEFAULT` fall into the new partition's bounds. If overlapping rows exist, you must move them out and add constraints proving the range is empty before attaching the new partition; that verification can scan the table and acquire locks.

If you use a `DEFAULT` partition, monitor its row count and alert immediately whenever rows land in it. In tightly controlled pipelines, omitting `DEFAULT` lets missing-partition inserts fail loudly so the ingest layer handles them explicitly.

## 5. Partition Pruning and Writing Queries

### 5.1. What Is Partition Pruning?

Partition pruning lets the planner or executor skip partitions whose bounds do not overlap the query predicate. Example:

```sql
SELECT event_type, count(*)
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
  AND tenant_id = 42
GROUP BY event_type;
```

With the time predicate above, the planner inspects only the November 2026 partition. The `tenant_id` predicate then leverages the local index inside that partition.

### 5.2. Use Half-Open Intervals

Use `>= start` and `< end`:

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
```

Avoid `BETWEEN` across adjacent partition boundaries because `BETWEEN` is inclusive on both ends. If two consecutive query windows both include the boundary instant, an event falling right on that instant can be double-counted across reports.

### 5.3. Avoid Wrapping the Partition Key in Unnecessary Expressions

Direct predicates on the partition key prune most reliably. Example:

```sql
-- Good: direct predicate on occurred_at.
SELECT *
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
```

If you write:

```sql
SELECT *
FROM telemetry.events
WHERE date(occurred_at) = DATE '2026-11-14';
```

the planner cannot always deduce partition bounds from that expression. Rewrite it into an explicit timestamp range with explicit time zone:

```sql
SELECT *
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
```

### 5.4. Inspecting the Execution Plan

Use `EXPLAIN` to confirm partition pruning:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT count(*)
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
  AND tenant_id = 42;
```

The plan will display `Seq Scan`, `Index Scan`, or `Bitmap Heap Scan` on the specific partition, or an `Append`/`Parallel Append` over only the selected partitions. With prepared statements or parameterized queries, pruning may occur at execution time rather than planning time. Look for `Subplans Removed` or skipped subplans in the output appropriate to your version.

### 5.5. Toggling Partition Pruning and Partition-Wise Operations

Parameters such as `enable_partition_pruning`, `enable_partitionwise_join`, and `enable_partitionwise_aggregate` influence the planner. Partition-wise joins and aggregates process matching partition pairs independently, though they increase subplan counts and planner memory usage. Never enable them merely because a table is partitioned; benchmark real queries and keep defaults unless measurements prove a clear gain.

## 6. Scheduled Partition Management

### 6.1. Pre-Creating Partitions Before Data Arrives

Do not wait until inserts fail to create partitions. Run a scheduled job to pre-create upcoming partitions—for example, 2–3 months ahead. Lead time depends on deployment cadence, ingest schedules, and schema change processes.

Example manually creating the next monthly partition:

```sql
CREATE TABLE telemetry.events_2027_02
PARTITION OF telemetry.events
FOR VALUES FROM ('2027-02-01 00:00:00+00')
             TO ('2027-03-01 00:00:00+00');
```

When automating partition creation:

- Compute boundaries using the agreed standard time zone.
- Use a strict naming convention.
- Verify existing partition names and actual bounds before skipping.
- Alert on partition-creation failures.
- Ensure required indexes, storage parameters, privileges, and policies apply.
- Alert when future partition buffer runs low.
- Verify the job is idempotent and never produces duplicate or overlapping partitions.

`CREATE TABLE IF NOT EXISTS` prevents errors if a relation with that name exists, but does not verify that the existing relation has the expected bounds or parent structure. Automation must still validate catalog metadata.

### 6.2. Example: Pre-Creating Three Monthly UTC Partitions

The following `DO` block illustrates creating partitions for the current month and next two months using explicit UTC bounds:

```sql
DO $$
DECLARE
    v_month date := date_trunc('month', now() AT TIME ZONE 'UTC')::date;
    v_start timestamptz;
    v_end timestamptz;
    v_name text;
    i integer;
BEGIN
    FOR i IN 0..2 LOOP
        v_start := make_timestamptz(
            extract(year FROM v_month)::integer,
            extract(month FROM v_month)::integer,
            1, 0, 0, 0, 'UTC'
        );
        v_end := v_start + interval '1 month';
        v_name := 'events_' || to_char(v_month, 'YYYY_MM');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS telemetry.%I '
            'PARTITION OF telemetry.events '
            'FOR VALUES FROM (%L) TO (%L)',
            v_name, v_start, v_end
        );

        v_month := (v_month + interval '1 month')::date;
    END LOOP;
END
$$;
```

This snippet illustrates safe dynamic DDL using `format()` with identifier `%I` and literal `%L`. In production, add checks verifying bounds of existing partitions, error handling, logging, and least-privilege execution under an authorized role for the schema and parent table.

### 6.3. Handling Late-Arriving Data

When partitioning by `occurred_at`, an event can arrive days or months late—for example, an offline device flushing last month's buffer. The system must decide how to handle it:

- Keep historical partitions open to late writes for an explicit grace window.
- Recreate historical partitions if detached but not yet purged.
- Route to a staging/late-arrival table for batch reconciliation.
- Reject records older than the allowed window and emit explicit errors.
- Route overly old data to a separate archive store.

Do not treat the `DEFAULT` partition as an unbounded dumping ground for late data. If old rows enter `DEFAULT`, attaching a properly bounded historical partition later requires moving rows out and validating constraints.

If partitioning by `ingested_at`, late arrivals write easily, though queries by event time need supplemental indexing or summary tables. Choosing the partition key is a semantic and workload decision, not merely a DDL detail.

### 6.4. Making Historical Partitions Read-Only

Seldom-modified historical partitions can be protected with read-only grants or moved to lower-cost tablespaces/storage where supported. Example:

```sql
REVOKE INSERT, UPDATE, DELETE
ON telemetry.events_2025_01
FROM telemetry_writer;

GRANT SELECT
ON telemetry.events_2025_01
TO telemetry_reader;
```

If applications access only the parent table and inherit privileges via your current governance setup, audit effective permissions on both the parent and child partitions. Per-partition privileges can diverge when new partitions are created; manage them via automation and audit periodically.

## 7. Designing Data Retention Policies

A retention policy defines what data is kept, for how long, where it lives, who can read it, and what happens upon expiration. Partitioning helps enforce retention in bulk, but policies must originate from business and regulatory requirements.

### 7.1. Defining Retention Windows by Data Class

Do not apply a blanket retention period to every dataset. Examples:

| Data Class | Illustrative Policy | Handling |
|---|---|---|
| Detailed operational metrics | 30–90 days | Retain in PostgreSQL for fast queries, then delete or roll up. |
| Investigative event logs | 6–12 months | Archive before deletion if traceability is needed. |
| Audit logs | Per legal/organizational policy | Tamper-evident controlled storage with audited access. |
| Aggregated analytics | Multiple years if needed | Retain rolled-up aggregates at reduced granularity per policy. |
| Personal data | Per processing purpose and erasure duties | Implement deletion or anonymization across systems and copies. |

These durations are illustrative examples, not legal advice. Data owners, legal counsel, and security teams must determine retention windows based on purpose, contracts, and applicable regulations.

### 7.2. Distinguishing Hot, Warm, and Cold Data

A multi-tier storage lifecycle:

```text
Hot data
  - Recent data, queried frequently
  - PostgreSQL primary/replica, full indexes
          |
          v
Warm data
  - Less frequently accessed, still queryable
  - Historical partitions, cost-optimized storage or archive database
          |
          v
Cold data
  - Rarely accessed, long-term retention
  - Object storage, columnar files, or dedicated archive vault
          |
          v
Expiration
  - Purge once expired and free of legal holds
  - Retain destruction evidence per policy
```

Tiering requires specifying file formats, schema versions, encryption, queryability, restore cost, and retrieval SLA. Cold archives sit outside PostgreSQL transactions, so applications require dedicated retrieval workflows.

### 7.3. Defining When the Retention Clock Starts

Retention duration can be measured from:

- When the event occurred.
- When the record was ingested.
- When a contract ended.
- When a case was closed.
- When a customer relationship terminated.

Choosing the wrong anchor can purge data prematurely or retain it longer than permitted. For operational time-series events, retention anchored to `occurred_at` usually works well; for business records, retention often ties to closure status or end dates rather than ingest timestamps.

### 7.4. Legal Holds and Exceptions

Before detaching or dropping a partition, verify whether it contains rows under a legal hold, investigation, dispute, or special retention mandate. If a subset of rows must be retained longer than the rest, time-based partitioning alone cannot satisfy per-record holds; extract held records or maintain a case-level archive/registry.

Retention automation should include hold checks and approvals. Never drop data solely based on partition name or age if customer- or record-level exceptions exist.

## 8. Enforcing Retention via Detach, Archive, and Drop

### 8.1. Why Dropping Partitions Beats Bulk `DELETE`

Purging old rows via standard SQL might look like:

```sql
DELETE FROM telemetry.events
WHERE occurred_at < TIMESTAMPTZ '2025-01-01 00:00:00+00';
```

This generates massive dead tuples, heavy WAL volume, long-held locks, and heavy autovacuum pressure. On a time-partitioned table, when an entire partition predates the retention cutoff, you can detach or drop that relation directly. This is orders of magnitude faster because rows are not deleted individually.

Only drop a partition once every row inside it has expired. If the retention boundary falls in the middle of a partition, handle that slice by splitting/migrating rows or executing throttled batched deletes.

### 8.2. Detaching a Partition Before Deletion

Example detaching an old partition:

```sql
ALTER TABLE telemetry.events
DETACH PARTITION telemetry.events_2025_01;
```

Once detached, `telemetry.events_2025_01` remains a standalone table but is no longer part of the parent partitioned table. You can inspect, export, relocate tablespaces, or drop it per your retention workflow.

On supported PostgreSQL versions, use `DETACH PARTITION CONCURRENTLY` to minimize locking on the parent table:

```sql
ALTER TABLE telemetry.events
DETACH PARTITION telemetry.events_2025_01 CONCURRENTLY;
```

`CONCURRENTLY` carries version-specific restrictions and cannot run inside a transaction block. If interrupted in a pending-detach state, PostgreSQL provides `DETACH PARTITION ... FINALIZE` to complete cleanup under qualifying conditions. Check the documentation for your major version and verify constraints—especially if the parent has a `DEFAULT` partition.

### 8.3. Archiving Before Dropping

After detaching, export data to an archive store before dropping the table:

```sql
-- Illustrative export via psql client to controlled storage.
\copy telemetry.events_2025_01 TO 'events_2025_01.csv' WITH (FORMAT csv, HEADER true)
```

`\copy` is a `psql` meta-command whose file path resides on the client host. For large volumes, prefer compressed or columnar formats and reliable object-storage upload pipelines; CSV files grow large and lose strict database type metadata.

After verifying the archive is readable and recording metadata, drop the detached table:

```sql
DROP TABLE telemetry.events_2025_01;
```

If archiving is unnecessary and policy permits direct deletion, use a detach-then-drop workflow. Always verify partition name, bounds, legal holds, backups, and approvals before dropping. `DROP TABLE` cannot be undone via rollback once committed.

### 8.4. Retaining Detached Partitions Instead of Immediate Drop

Some systems require historical records without keeping them in hot tables. You can detach a partition and then:

- Keep the standalone table in an archive database.
- Move it to a tablespace on cheaper storage if supported.
- Export to object storage in Parquet or another analytics-friendly format.
- Record schema metadata, checksums, export timestamps, and pipeline versions.
- Grant read-only access strictly to investigation or compliance teams.

Detaching only alters partition membership; it does not automatically move bytes to cheaper storage or reduce bills. Perform the archive relocation explicitly and account for storage and retrieval costs.

### 8.5. Batched Retention When Boundaries Do Not Align

If a partition holds both active and expired rows, delete in bounded batches:

```sql
WITH batch AS (
    SELECT ctid
    FROM telemetry.events_2025_02
    WHERE occurred_at < TIMESTAMPTZ '2025-02-15 00:00:00+00'
    LIMIT 10000
)
DELETE FROM telemetry.events_2025_02 AS e
USING batch
WHERE e.ctid = batch.ctid;
```

Repeat in a throttled job, committing each batch while monitoring vacuum and WAL. `ctid` is valid only within a single statement; never persist `ctid` across transactions or treat it as a business key. Use primary keys instead when clearer handling is preferred.

If retention always requires exact cutoffs at high volume, consider smaller partitions (e.g., daily) so partition drops align cleanly with cutoff boundaries. Balance that benefit against total partition count.

## 9. Managing Indexes, Vacuum, and Statistics per Partition

### 9.1. Indexes Created on the Parent Table

An index on a partitioned table is a logical partitioned index containing no rows directly. Each partition owns a corresponding physical index. When a new partition is added, PostgreSQL automatically creates and attaches matching child indexes for any partitioned indexes on the parent.

Inspect per-partition indexes:

```sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS partition_schema,
    child.relname AS partition_name,
    child_index.relname AS partition_index
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_index AS idx
    ON idx.indrelid = parent.oid
JOIN pg_class AS parent_index
    ON parent_index.oid = idx.indexrelid
JOIN pg_inherits AS index_inh
    ON index_inh.inhparent = parent_index.oid
   AND index_inh.inhrelid IN (
       SELECT indexrelid
       FROM pg_index
       WHERE indrelid = child.oid
   )
JOIN pg_class AS child_index
    ON child_index.oid = index_inh.inhrelid
WHERE parent.oid = 'telemetry.events'::regclass
ORDER BY child.relname, child_index.relname;
```

In day-to-day operations, `\d+ telemetry.events` in `psql` or version-appropriate catalog queries can inspect partitions and indexes. If building child indexes individually first, follow the `CREATE INDEX ... ON ONLY` and `ALTER INDEX ... ATTACH PARTITION` workflow.

### 9.2. Building Indexes Concurrently on Live Partitioned Tables

`CREATE INDEX CONCURRENTLY` cannot run directly on a partitioned parent table. The standard pattern builds indexes concurrently on each partition, creates the parent index with `ON ONLY`, and attaches each child index. Exact syntax and capabilities depend on your PostgreSQL version; verify documentation before running.

Workflow skeleton:

```sql
CREATE INDEX CONCURRENTLY events_2026_11_tenant_time_idx
ON telemetry.events_2026_11 (tenant_id, occurred_at DESC);

CREATE INDEX events_tenant_time_idx
ON ONLY telemetry.events (tenant_id, occurred_at DESC);

ALTER INDEX telemetry.events_tenant_time_idx
ATTACH PARTITION telemetry.events_2026_11_tenant_time_idx;
```

Repeat for every partition. The parent index remains marked invalid until all required partitions are attached. If a new partition is created mid-rollout, include it before completion.

### 9.3. Autovacuum and Analyze

Each partition maintains separate storage and statistics. Autovacuum vacuums and analyzes physical partitions based on their individual activity. Insert-only new partitions may rely on insert-triggered autovacuum to freeze tuples, while static historical partitions may still require anti-wraparound freezing based on XID age.

Crucially, autovacuum does not automatically run `ANALYZE` on a partitioned parent table because the parent holds no physical tuples. After significant data shifts across partitions, manually run `ANALYZE` on the parent to refresh inherited planner statistics:

```sql
ANALYZE telemetry.events;
```

Monitor individual partitions via `pg_stat_all_tables`, `pg_class`, and `pg_stat_progress_vacuum`. Never assume the parent's `last_autovacuum` reflects the health of child partitions.

### 9.4. Monitoring Partition Size and Count

```sql
SELECT
    relid::regclass AS partition_name,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_partition_tree('telemetry.events')
WHERE isleaf
ORDER BY relid::regclass::text;
```

`pg_partition_tree()` exposes the partition hierarchy on supported versions. `pg_total_relation_size()` includes heap, indexes, and TOAST. Track partition counts, min/max sizes, empty partitions, missing upcoming partitions, and `DEFAULT` partition growth.

## 10. Security and Access Control Across Partitions

Applications typically query the parent table rather than referencing partitions directly. Manage privileges on the parent and verify effective privileges after creating new partitions. PostgreSQL supports row-level security (RLS) on partitioned tables; parent policies apply to queries routed through the parent per RLS rules. Direct access to child partitions, however, requires separate consideration of privileges and policies.

If applications never query partitions directly, avoid granting broad privileges on the schema holding child tables. Detached archive partitions can be moved to a dedicated schema with read-only grants restricted to authorized teams.

Retention itself is a privileged operation. Use a dedicated role with scoped permissions, verify bounds and legal holds, log operator identity, and require approval for bulk drops. Never grant ingest application roles permission to drop partitions.

## 11. Testing Partitioning and Retention Designs

Before production rollout, test at least these scenarios:

1. Inserts at the exact start and end of each partition boundary.
2. Inserts at the exact `TO` boundary of an older partition to verify routing into the next partition.
3. Inserts when a partition is missing to verify expected behavior (explicit error vs. `DEFAULT`).
4. Queries spanning one day, one month, and multiple months; verify pruning via `EXPLAIN`.
5. Queries omitting time predicates to measure full-partition scan cost.
6. Late-arriving events targeting closed or archived partitions.
7. Creating new partitions while the application is actively writing.
8. Detaching/dropping partitions during active queries to measure lock/downtime impact.
9. Archiving a partition, reading back the archive, and verifying row counts/checksums.
10. Restoring from backup/PITR to verify how dropped partitions recover.
11. Auditing permissions on parent, child, `DEFAULT`, and archive schemas.
12. Observing autovacuum, analyze, and XID age across partitions under varied workloads.

### 11.1. Boundary Testing

```sql
INSERT INTO telemetry.events (
    occurred_at, event_id, tenant_id, device_id, event_type, value
)
VALUES
    ('2026-11-30 23:59:59.999+00', gen_random_uuid(), 42, 7, 'reading', 10.5),
    ('2026-12-01 00:00:00+00', gen_random_uuid(), 42, 7, 'reading', 10.6);
```

Then inspect `tableoid` to confirm which physical partition holds each row:

```sql
SELECT
    tableoid::regclass AS physical_partition,
    occurred_at,
    event_id
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-30 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-02 00:00:00+00'
ORDER BY occurred_at;
```

`tableoid` is helpful for testing and diagnostics; never rely on partition names as a business contract inside application logic.

### 11.2. Archive Reconciliation

Before dropping an archived partition, verify:

- Exported row count matches the partition row count at the agreed snapshot.
- Minimum and maximum timestamps align with partition bounds.
- Checksums or business control totals match.
- Files can be read back cleanly with documented tools and schemas.
- Recorded metadata includes table name, bounds, export timestamp, schema version, checksum, and storage location.
- The archive satisfies encryption, access control, retention, and legal-hold policies.

## 12. Common Errors and Remedies

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `no partition of relation found for row` | Missing partition for the inserted timestamp | Pre-create partitions, inspect scheduling jobs, and alert on low future buffer. |
| Queries still scan many partitions | Missing partition-key predicate or non-prunable expression | Write direct range predicates and verify with `EXPLAIN`. |
| Cannot create new partition due to overlap | Overlapping bounds or `DEFAULT` already holds rows in that range | Inspect bounds, move rows out of `DEFAULT`, and add validating constraints. |
| Partition created with existing name but wrong bounds | `IF NOT EXISTS` only checks relation name | Validate catalog metadata and bounds; fix automation instead of ignoring silently. |
| Primary key / unique constraint creation fails | Constraint omits partition key column(s) | Include full partition key in composite constraint or use a separate uniqueness registry. |
| Dropping a partition blocks or hangs | Locks, dependencies, foreign keys, or active transactions holding the relation | Identify blockers, inspect dependencies, and schedule detach/maintenance windows. |
| Archive created but fails to restore | Missing schema, metadata, data types, or corrupted files | Persist schema version and checksums, and run periodic restore drills. |
| `DEFAULT` partition grows continuously | Future-partition job failed or late arrivals go unclassified | Alert on row growth, trace ingest sources, and route rows to proper partitions. |
| Historical partitions still consume heavy storage | Detaching does not move or reclaim storage automatically | Archive/drop detached tables or relocate to lower-cost tablespaces. |
| Excessive partitions slow down query planning | Partitions too granular/numerous or queries fail to prune | Coarsen partition interval, optimize predicates, and measure planning time. |
| Stale planner statistics after bulk load | Parent lacks `ANALYZE` or partition stats lag | Run `ANALYZE` appropriately on both parent and child partitions. |

## 13. Daily and Monthly Operational Runbook

### Daily

- Verify upcoming future partitions cover the ingest horizon.
- Monitor insert errors, `DEFAULT` partition row counts, and late-arriving events.
- Track partition sizes, index sizes, WAL volume, and ingest growth rates.
- Check archive/retention job execution status, errors, and runtimes.
- Monitor autovacuum/analyze activity, dead tuples, and XID age.

### Monthly

- Reconcile the partition inventory against the calendar and retention schedule.
- Confirm expired partitions, legal holds, and approvals prior to detach/drop.
- Test readability and checksum integrity of recent archives.
- Verify backup/PITR coverage spans required recovery windows.
- Review partition sizes, index counts, and query planning latencies.
- Adjust partition granularity if data volume or query patterns shift significantly.
- Audit roles and privileges across new partitions, old partitions, and archive schemas.

## 14. Conclusion

Designing time-series data in PostgreSQL starts with timestamp semantics, query patterns, and retention horizons. Time-based `RANGE` partitioning enables effective partition pruning and bulk lifecycle management. Partition sizing must balance storage, query frequency, relation counts, and maintenance costs. Use half-open intervals, standardize on UTC where appropriate, and pre-create partitions ahead of ingest to avoid boundary failures.

Retention policies require defining data classes, retention start anchors, archiving formats, legal holds, purge permissions, and reconciliation evidence. Detaching, archiving, and dropping partitions is far more efficient than bulk `DELETE`s, yet still demands verifying bounds, dependencies, locks, recoverability, and archive integrity. Combining partition monitoring, autovacuum tracking, index hygiene, WAL observation, and automated maintenance keeps the system scaling smoothly as data continues to grow.

## References

- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [PostgreSQL — Declarative Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE)
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [PostgreSQL — CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html)
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html)
