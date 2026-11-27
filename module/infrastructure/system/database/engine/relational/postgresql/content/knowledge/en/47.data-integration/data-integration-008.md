# Connecting BI Tools, ETL Pipelines, and Analytics Systems to PostgreSQL

PostgreSQL often serves as the transactional data source for business applications. Business Intelligence (BI) tools, Extract, Transform, Load (ETL) platforms, data warehouses, and analytics systems need to read data from PostgreSQL to build reports, data models, and analytical pipelines. A sound integration must preserve data consistency, control load on the transactional system, protect sensitive data, and detect when data flows slow down or stall.

This lesson covers common integration patterns, from direct queries and batch exports to continuous change synchronization via logical replication or Change Data Capture (CDC). Examples use PostgreSQL SQL and components commonly encountered in BI/ETL ecosystems. Exact menu labels and configuration screens vary by product, but the principles governing connectivity, permissions, transactions, synchronization, and operations remain consistent.

## 1. PostgreSQL's Role in an Analytics Architecture

In a typical system, PostgreSQL handles application transactions: creating orders, updating customers, recording payments, and tracking processing states. BI systems aggregate data by date, region, product, or customer segment. ETL/ELT tools move data from the source into analytical storage, then normalize and model tables for reporting.

Common components include:

- **Transactional source (OLTP):** PostgreSQL stores normalized data and handles short application reads/writes.
- **Extraction mechanism:** JDBC, ODBC, libpq, `COPY`, SQL queries, logical replication, or a CDC connector reading changes from WAL.
- **Staging area:** holds raw copies or intermediate data before cleansing and consolidation.
- **Data warehouse / lakehouse:** stores historical and modeled data for broad analytical workloads.
- **BI modeling layer:** defines metrics, dimensions, relationships, and data access permissions.
- **BI tool:** builds dashboards, reports, ad-hoc queries, and scheduled report deliveries.
- **Orchestrator:** schedules runs, manages dependencies, handles retries, sends alerts, and tracks pipeline status.

A simple flow can be illustrated as follows:

```text
Business application
        |
        v
PostgreSQL OLTP
   |         |
   |         +----> Read replica ----> Direct BI queries
   |
   +----> Batch ETL / CDC connector
                    |
                    v
              Staging / Raw
                    |
                    v
             Transform / ELT
                    |
                    v
             Data warehouse
                    |
                    v
             BI model / Dashboard
```

Not every system needs all components. A small team can start with a read replica and a BI tool. As report volume, data sources, and historical retention needs grow, offloading data into a dedicated analytics store helps isolate workloads and manage models cleanly.

## 2. Distinguishing BI, ETL, ELT, and CDC

These concepts are related yet solve different parts of the problem.

| Concept | Role | Example Tasks |
|---|---|---|
| BI | Explore and present data to support decisions | Revenue dashboards, inventory reports |
| ETL | Extract, transform, and then load data into the target | Read orders, standardize currency codes, write to data warehouse |
| ELT | Load raw data first, then transform inside the target system | Load source tables into `raw` schema, run SQL to build `mart` tables |
| CDC | Capture changes as they occur at the source | Emit insert/update/delete events from WAL to Kafka or another target |
| Orchestration | Coordinate schedules, dependencies, retries, and monitoring | Run source sync before refreshing dashboards |

ETL and ELT describe the order of transformation and loading. CDC describes how source changes are captured; CDC can feed both ETL and ELT. BI is the layer consuming organized data for querying and presentation.

## 3. Choosing the Right Connection Method

### Direct Queries via JDBC or ODBC

Many BI tools ship with built-in PostgreSQL connectors or support JDBC/ODBC. The tool opens a connection, sends SQL, and receives result sets. This is easy to set up and fits dashboards with moderate query load and near-real-time needs.

The advantages are zero separate replication pipelines, reading live data from PostgreSQL, and using SQL to control joins and aggregations. The limitations are that dashboards can open many concurrent queries, heavy queries compete for resources with OLTP traffic, and each read typically reflects only a point-in-time snapshot.

### Read Replica

PostgreSQL can run a standby in hot standby mode to serve read-only queries. Connecting BI tools to a replica offloads read traffic from the primary. Monitor replication lag because reports may observe data behind the primary. Long-running queries on a standby can also conflict with WAL replay; depending on configuration, PostgreSQL may cancel queries to let recovery proceed or delay recovery within configured limits.

### Batch ETL via SQL, `COPY`, or Connectors

Scheduled pipelines read data by time window or incremental key, write to staging, and transform at the destination. This fits when minutes or hours of latency are acceptable, or when explicit control over each load batch is desired.

### Logical Replication and CDC

PostgreSQL logical replication streams table-level logical changes via publications and subscriptions. CDC connectors can also consume logical decoding from WAL and forward events to downstream systems. This suits continuous synchronization, but requires managing replication slots, permissions, schema evolution, and event replay.

### Snapshot Exports and Imports

`pg_dump`, `COPY`, or ETL exports produce a consistent point-in-time extraction for initial loads, migrations, or periodic reporting. For large datasets, plan storage capacity, runtime, and I/O impact carefully.

| Need | Suitable Approach | What to Monitor |
|---|---|---|
| Small, low-latency dashboards | JDBC/ODBC to PostgreSQL or read replica | Connection counts, heavy queries, caching |
| Multi-user dashboards | Read replica or data warehouse | Lag, query load, infrastructure cost |
| Hourly/daily reporting | Batch ETL | Watermarks, retries, late-arriving data |
| Continuous change synchronization | Logical replication or CDC | Slots, WAL retention, lag, event ordering |
| Very large initial loads | Snapshot via `COPY`/`pg_dump`/connector bulk load | Consistent snapshots, disk space, and duration |

## 4. Preparing PostgreSQL for BI and ETL Connections

Before configuring external tools, define allowed databases, schemas, tables, authentication methods, connection limits, and network rules. BI accounts usually need read-only access. ETL accounts may need read access on the source and write access on the target database; never use a single superuser account for both roles.

### Creating a Read-Only Role

The following example creates a login role for BI tools. Replace database names, schemas, and passwords for your environment; supply passwords via a secret manager or approved authentication mechanism rather than storing them in source code.

```sql
CREATE ROLE bi_reader LOGIN;

GRANT CONNECT ON DATABASE sales TO bi_reader;

GRANT USAGE ON SCHEMA reporting TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO bi_reader;

ALTER DEFAULT PRIVILEGES IN SCHEMA reporting
    GRANT SELECT ON TABLES TO bi_reader;
```

`GRANT SELECT ON ALL TABLES` applies to tables existing at execution time. `ALTER DEFAULT PRIVILEGES` affects future objects created by the role that owns those default privileges. If tables are created by multiple roles, configure default privileges for each table-creating role.

If BI needs to read views, materialized views, or sequence metadata, verify object-specific privileges. For views, underlying data access also depends on how the view is defined and applied security settings. Never grant broad permissions on application schemas just because a BI tool needs a few reporting tables.

### Separating a Reporting Schema

You can create a dedicated schema holding views and materialized views for BI:

```sql
CREATE SCHEMA reporting AUTHORIZATION reporting_owner;

CREATE VIEW reporting.daily_sales AS
SELECT
    date_trunc('day', created_at)::date AS sales_date,
    count(*) AS order_count,
    sum(total_amount) AS gross_amount
FROM public.orders
WHERE status = 'paid'
GROUP BY date_trunc('day', created_at)::date;
```

A reporting schema stabilizes the data contract for BI tools. Applications can evolve internal tables while reporting views maintain agreed column names and semantics. Manage view changes as part of migrations, because dashboards and pipelines depend on column names, types, and meanings.

### Network Access Control and TLS

`listen_addresses` defines which interfaces PostgreSQL listens on. `pg_hba.conf` defines allowed clients, databases, roles, and authentication methods. Restrict network access to required BI/ETL hosts only; never expose database ports publicly to the Internet without proper protections.

Example `pg_hba.conf` line requiring TLS and SCRAM for a private subnet:

```text
hostssl  sales  bi_reader  10.20.30.0/24  scram-sha-256
```

The subnet above is only an example. Actual rules must match your tool hosts' subnet. Over untrusted networks, configure TLS certificates and verify server identity on the client. Avoid using `trust` for external connections.

### Configuring Connections in Tools

A PostgreSQL connection URI looks like:

```text
postgresql://bi_reader@db-reporting.internal:5432/sales?sslmode=verify-full
```

Passwords can be entered separately in the tool UI or retrieved from a secret manager. `verify-full` instructs the client to verify both the certificate and the hostname; the server must present a valid matching certificate. With JDBC, configure SSL properties per the driver and BI tool.

Typical connection settings include hostname, port, database, username, authentication, SSL mode, default schema, and timeouts. Verify driver compatibility with your PostgreSQL version and tool runtime.

## 5. Direct BI Connections and Designing the Reporting Data Layer

Establishing a connection is only the first step. BI tools need to know which tables are facts, which are dimensions, how they relate, the reporting timezone, and metric definitions.

### Using Views as a Data Contract

Instead of having every dashboard join multiple operational tables itself, create views with stable names and data types:

```sql
CREATE VIEW reporting.order_metrics AS
SELECT
    o.id AS order_id,
    o.created_at,
    o.customer_id,
    c.region_code,
    o.total_amount,
    o.currency_code
FROM public.orders AS o
JOIN public.customers AS c
  ON c.id = o.customer_id
WHERE o.status = 'paid';
```

The view above is a simple example. In large systems, evaluate whether joins and aggregations introduce heavy load, and explicitly define how refunded, canceled, or post-payment modified orders are handled.

### Materialized Views for Scheduled Aggregations

A materialized view stores query results on disk and is refreshed on a schedule or on demand:

```sql
CREATE MATERIALIZED VIEW reporting.sales_by_day AS
SELECT
    created_at::date AS sales_date,
    currency_code,
    count(*) AS order_count,
    sum(total_amount) AS total_amount
FROM public.orders
WHERE status = 'paid'
GROUP BY created_at::date, currency_code;

CREATE UNIQUE INDEX sales_by_day_key
    ON reporting.sales_by_day (sales_date, currency_code);
```

Use `REFRESH MATERIALIZED VIEW` to update it. `REFRESH MATERIALIZED VIEW CONCURRENTLY` lets queries keep reading the materialized view during refresh, though it requires a suitable unique index covering all rows and has specific limitations. Refreshes still consume resources and require scheduled planning.

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY reporting.sales_by_day;
```

Materialized views do not update automatically on every source change. Dashboards should display the last refresh timestamp so users understand data freshness.

### Standardizing Timestamps, Currencies, and Metric Definitions

`timestamp with time zone` (`timestamptz`) stores an absolute point in time; when displayed, PostgreSQL converts it to the session timezone. Standardize storage and display rules—for example, store transaction times in `timestamptz` and convert to the reporting timezone in the BI model.

Monetary values must carry a currency code. Never sum amounts across multiple currencies directly without converting via defined exchange rates and effective timestamps. For financial figures, `numeric` is usually preferable to binary floating-point types when exact decimal arithmetic is needed.

Metric definitions must be consistent. For instance, "revenue" might mean total paid order value, revenue net of refunds, or revenue excluding tax. If each dashboard applies different filters, figures across departments will diverge even when technical connections work fine.

## 6. Batch ETL: Extracting Consistent Data

A batch pipeline typically follows these steps: define the data window, read from PostgreSQL, land in staging, run row-count and quality checks, transform, and commit into target tables. Pipelines must persist progress state so they can safely re-run after failures.

### Extracting with `COPY`

`COPY` can export data more efficiently than an application reading row by row. Example exporting a filtered slice:

```sql
COPY (
    SELECT id, customer_id, created_at, total_amount, currency_code
    FROM public.orders
    WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
      AND created_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
) TO STDOUT WITH (FORMAT csv, HEADER true);
```

`COPY TO STDOUT` streams data over the client connection; the ETL program or driver writes the stream. `COPY ... TO '/path/file.csv'` writes files on the PostgreSQL server host and requires OS and PostgreSQL permissions, so avoid server-side file syntax when you do not control the server host.

When loading, `COPY ... FROM STDIN` can load into a staging table. Load into a staging table with proper types and validation rules before merging into target tables.

### Incremental Loads with Watermarks

To avoid re-reading entire tables on every run, a pipeline can store a watermark, such as the maximum processed `updated_at` value. The next run reads rows with `updated_at` newer than the watermark.

```sql
SELECT
    id,
    customer_id,
    status,
    total_amount,
    updated_at
FROM public.orders
WHERE updated_at >= :window_start
  AND updated_at <  :window_end
ORDER BY updated_at, id;
```

The time window can overlap slightly to catch late-arriving records or boundary timestamps. The target must deduplicate using natural/primary keys and upserts. Do not rely solely on timestamps if the system can update rows without updating `updated_at`, if host clocks skew, or if multiple rows share identical timestamps.

Update the watermark only after data is written and committed at the destination. Updating the watermark prior to commit risks skipping a data slice on the next run if the load fails.

### Upserting into Staging or Target Tables

`INSERT ... ON CONFLICT` merges repeated records by unique key:

```sql
INSERT INTO analytics.orders (
    order_id,
    customer_id,
    status,
    total_amount,
    source_updated_at
)
VALUES (
    :order_id,
    :customer_id,
    :status,
    :total_amount,
    :source_updated_at
)
ON CONFLICT (order_id) DO UPDATE
SET customer_id = EXCLUDED.customer_id,
    status = EXCLUDED.status,
    total_amount = EXCLUDED.total_amount,
    source_updated_at = EXCLUDED.source_updated_at
WHERE analytics.orders.source_updated_at
      <= EXCLUDED.source_updated_at;
```

The timestamp guard prevents late older events from overwriting newer versions. If the source lacks reliable versions or timestamps, design an alternative ordering rule. The target should also record source metadata and load timestamps for investigation.

### Handling Deletes

Incremental loads based only on `updated_at` usually miss hard deletes at the source. Use soft-delete columns (`deleted_at`, `is_deleted`), a change-log table, or CDC to propagate delete events. Without such a mechanism, deleted source rows remain in the warehouse.

### Consistent Snapshots Across Multiple Queries

If a pipeline extracts multiple related tables requiring a single consistent point-in-time view, consider transaction isolation. `REPEATABLE READ` provides a stable snapshot within one transaction on the same database:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM public.orders;
SELECT count(*) FROM public.order_items;

COMMIT;
```

Queries within the transaction see the same snapshot. Holding read transactions open too long blocks vacuum from reclaiming dead tuples and increases table bloat risk, so cap extraction duration or use connector-supported snapshot mechanisms.

## 7. Using Logical Replication for Continuous Synchronization

Logical replication copies table-level changes from a publisher to a subscriber. The publisher defines a publication listing tables to stream. The subscriber creates a subscription to receive data and apply changes.

### Preparing the Publisher

Logical replication requires appropriate WAL settings, including `wal_level = logical`, along with limits for replication slots and WAL senders sized for system scale. Some configuration changes require a PostgreSQL restart. Check documentation for your running version before modifying parameters.

Create a publication:

```sql
CREATE PUBLICATION analytics_pub
FOR TABLE public.customers, public.orders, public.order_items;
```

A publication can restrict the table list. Privileges to create publications and access tables depend on configuration, version, and permission models. Create publications with an appropriate data-management role and control published tables explicitly.

### Preparing the Subscriber

On the subscriber database, create a subscription pointing to the publisher:

```sql
CREATE SUBSCRIPTION analytics_sub
CONNECTION 'host=pg-primary.internal port=5432 dbname=sales user=replicator sslmode=verify-full'
PUBLICATION analytics_pub;
```

The connection string above is an example; passwords should be supplied via your environment's secret management mechanism. When creating a subscription, PostgreSQL can create a replication slot and perform initial table synchronization per options. Ensure target schemas and tables on the subscriber are compatible with source tables before syncing.

Logical replication typically requires the publisher role to have login, `REPLICATION`, and `SELECT` privileges on replicated tables per PostgreSQL version rules. Configure `pg_hba.conf` to allow replication connections from the subscriber with appropriate authentication and TLS.

### Checking Replication Status

On the publisher, inspect WAL-sending connections:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

On the subscriber, inspect subscription status:

```sql
SELECT
    subname,
    pid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

Column names and availability in monitoring views can vary by version. Check the catalog on your version before building monitoring dashboards.

### Limitations to Know

PostgreSQL's built-in logical replication replicates data changes for subscribed tables, but does not automatically sync all DDL. When adding columns, altering types, or changing schemas, deploy matching changes on the subscriber in a safe sequence. Sequence state and large objects are not replicated as ordinary row changes. DDL, roles, permissions, and configuration must also be managed separately.

By default, published tables require a replica identity to identify rows on updates or deletes; a primary key is usually best. If a table lacks a primary key, you might consider `REPLICA IDENTITY FULL`, though this increases WAL volume and processing overhead because PostgreSQL logs the entire row as the identifier.

Logical replication does not automatically resolve conflicts if multiple writers modify subscriber data. Standard practice treats the publisher as the primary writer while the subscriber receives changes. If writes are needed on the subscriber, design data-ownership partitioning and conflict resolution explicitly.

## 8. CDC Connectors and Event Streams

A CDC connector reads logical decoding from WAL, turns changes into events, and sends them to an intermediary such as a message broker or analytical target. Downstream consumers can store raw events, maintain current tables, or build change histories.

A CDC event typically carries:

- Source schema and table name.
- Operation type: insert, update, or delete.
- Row identifying key.
- Before/after values if provided by the connector and configuration.
- Log position or ordering metadata such as LSN.
- Event timestamp and transaction metadata if supported.

Never assume all connectors emit identical event structures or semantics. Verify how your connector handles initial snapshots, large transactions, schema changes, tombstones, retries, and offset commits.

### Initial Snapshot and Resuming WAL Reads

When starting CDC on an existing populated table, the connector typically takes an initial snapshot of current state while establishing a WAL position to stream subsequent changes. Coordinating the snapshot and WAL boundary is critical to avoid losing or duplicating changes at the seam. Use the connector's built-in snapshot workflow; never stitch an arbitrary `SELECT` together with an unrelated WAL position.

### Idempotency and Duplicate Event Handling

Consumers may receive duplicate events during retries or after restarts. Target systems should process events idempotently, such as recording event keys/LSNs or upserting by row key and version. Do not rely on "exactly once" assumptions spanning PostgreSQL, brokers, connectors, and warehouses unless the entire chain shares a unified transaction protocol.

A common pattern is:

1. Write events to a raw table with source, table, key, and position metadata.
2. Use a target transaction to update the current table and mark the event applied.
3. Enforce a unique key to prevent reapplying the same event.
4. Retain tombstones or delete flags so downstream systems know rows were deleted.
5. Maintain a replay procedure from saved offsets/LSNs for recovery.

### Replication Slots and WAL Retention Risk

A replication slot retains WAL that the consumer has not yet confirmed as processed. If a connector stops for a long time, the slot stops advancing and WAL can accumulate on the publisher, filling the disk. Monitor slots, retained WAL size, consumer downtime, and filesystem capacity.

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal
FROM pg_replication_slots;
```

`restart_lsn` indicates the earliest WAL position the slot still needs to retain. The expression above estimates WAL distance from the current position back to `restart_lsn`; verify column types and availability for your PostgreSQL version. Never drop an active slot arbitrarily to free disk space: doing so prevents the consumer from resuming at its previous position and forces a full re-snapshot.

## 9. Integration via Foreign Data Wrappers

A Foreign Data Wrapper (FDW) lets PostgreSQL query external systems via foreign tables. `postgres_fdw` is commonly used to access another PostgreSQL server.

Example creating the extension, server, and user mapping:

```sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER source_sales
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (host 'pg-source.internal', port '5432', dbname 'sales');

CREATE USER MAPPING FOR bi_reader
    SERVER source_sales
    OPTIONS (user 'report_reader', password 'managed-outside-source');

CREATE SCHEMA source_sales_fdw;

IMPORT FOREIGN SCHEMA reporting
    FROM SERVER source_sales
    INTO source_sales_fdw;
```

The password string in the example merely illustrates option placement; production setups must use proper secret management and restrict access to user mappings. Foreign tables enable querying remote data but do not turn the source into a data warehouse. Performance depends on predicate pushdown, rows shipped across the network, statistics, and remote server load.

FDW fits controlled federated queries or small source integrations. Running many heavy dashboard queries over FDW can overload both databases and introduces sensitivity to network stability. For high-volume analytics or historical reporting, copying data into an analytical warehouse is usually easier to govern.

## 10. Optimizing Performance for Analytical Workloads

BI queries typically scan many rows, join multiple tables, and group/aggregate data. This differs from OLTP queries that touch a few rows via indexes. Design systems so analytical workloads do not degrade transactional latency.

### Creating Indexes Matching Real Filters and Joins

Example dashboard filtering paid orders by timestamp:

```sql
CREATE INDEX orders_paid_created_at_idx
    ON public.orders (created_at)
    WHERE status = 'paid';
```

A partial index stores only rows matching the predicate. It helps when dashboards consistently filter `status = 'paid'` and query conditions match the index predicate. Avoid indexing every column pulled into BI reports; every index adds write overhead and maintenance cost.

### Reading Execution Plans

Use `EXPLAIN` to inspect plans. `EXPLAIN ANALYZE` executes the query for real, so be careful with heavy queries or queries with side effects:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    date_trunc('day', created_at)::date AS sales_date,
    sum(total_amount)
FROM public.orders
WHERE status = 'paid'
  AND created_at >= now() - interval '30 days'
GROUP BY 1
ORDER BY 1;
```

Check estimated vs. actual row counts, scan types, join strategies, buffer hits/reads, and per-node timing. If statistics are stale or data is skewed, `ANALYZE` helps the planner make better estimates.

### Limiting Queries and Connections

Set sensible timeouts on BI roles so runaway queries cannot tie up resources indefinitely:

```sql
ALTER ROLE bi_reader SET statement_timeout = '2min';
ALTER ROLE bi_reader SET idle_in_transaction_session_timeout = '1min';
```

These values are examples; base limits on dashboard SLAs and query profiles. `statement_timeout` caps individual statement execution time. `idle_in_transaction_session_timeout` terminates sessions sitting idle inside a transaction; this prevents long-open transactions, though client compatibility should be checked.

Use connection pooling or cap BI tool concurrency to avoid opening hundreds of simultaneous connections. Poolers in transaction pooling mode have restrictions on session state, temporary tables, prepared statements, and session-scoped features; verify pooling mode compatibility with drivers and BI tools.

### Monitoring Queries and Resources

`pg_stat_activity` shows active sessions and running queries. `pg_stat_database` provides database-level aggregates. `pg_stat_statements` (when installed and configured) aggregates normalized queries to pinpoint expensive workloads. Combine these views with CPU, RAM, I/O, disk space, WAL, and replication lag to diagnose root causes.

Do not blindly raise `work_mem` globally just to speed up one dashboard. `work_mem` can be allocated per sort/hash node across multiple concurrent sessions, so total memory usage can escalate rapidly. Adjust it per role or session for measured workloads instead.

## 11. Security and Governance for Analytical Data

Data warehouses often centralize data from many systems, amplifying the blast radius of data leaks. Classify data and define who is authorized to view each tier.

### Least-Privilege Principles

- BI readers only have read access to required reporting views or tables.
- ETL readers only read designated source schemas.
- ETL writers only write to required staging schemas or target databases.
- Migration administration roles are separated from pipeline runtime accounts.
- Application, BI, and CDC accounts never share passwords or privileges.

### Row-Level Security

Row-Level Security (RLS) restricts which rows a role may see:

```sql
ALTER TABLE reporting.customer_sales ENABLE ROW LEVEL SECURITY;

CREATE POLICY customer_sales_region_policy
ON reporting.customer_sales
FOR SELECT
TO regional_bi_reader
USING (region_code = current_setting('app.region_code', true));
```

Implement this pattern carefully. Users allowed to set session variables can alter `app.region_code`; never treat a custom setting as a trusted identity if clients can set it arbitrarily. Use secure identity mapping, region-specific roles, or a controlled access tier. Table owners, superusers, and roles with `BYPASSRLS` bypass RLS where applicable; audit the actual privileges of connecting accounts.

### Anonymization and Data Minimization

If a dashboard only needs age brackets, regions, or customer counts, do not extract emails, phone numbers, street addresses, or unnecessary identifiers. Create views that omit or mask sensitive fields before granting BI access. Staging tables, export files, logs, and backups must be protected with the same rigor as source data.

### Secret Management and Auditing

Never commit passwords, private keys, or credentialed connection strings to Git, notebooks, shared config files, or pipeline logs. Use a secret manager, rotate credentials, and restrict secret read access. Audit role creation, privilege changes, publications, subscriptions, and connection changes under governance policies.

## 12. Schema Evolution and Data Contracts

Pipelines depend on table names, column names, data types, nullability, and business semantics. A schema migration can break pipelines even while the application keeps running smoothly.

### Controlled Schema Changes

When adding new columns, consider phased rollouts: add nullable columns or columns with safe defaults, update producers, backfill historical data, update pipelines and BI models, and only then tighten constraints. With logical replication, deploy compatible schema changes on subscribers in proper sequence because DDL is not automatically streamed like row changes.

### Using Views to Stabilize Interfaces

Reporting views can shield downstream consumers from internal source table changes. When renaming or changing output column types, create a new view version or coordinate consumer updates before dropping old columns. Never change a column's business meaning while keeping the same name if downstream consumers will misinterpret metrics.

### Enforcing Data Contracts

Pipelines should validate checks such as:

- Required columns contain no unexpected `NULL`s.
- Primary or business keys have no duplicates.
- Status codes belong to valid value sets.
- Foreign keys meet expected match rates.
- Total row counts and monetary sums fall within reasonable ranges compared to prior periods.
- Timestamps fall within expected time windows.

These checks act as pipeline data-quality gates, not replacements for PostgreSQL constraints. Database constraints protect data at the source; pipeline checks protect the integrity of replicas and analytical models.

## 13. Pipeline Orchestration, Retries, and Recovery

A production pipeline requires run state tracking, logs, metrics, bounded retries, and alerting. Each run should record `run_id`, start/end timestamps, start/end watermarks, rows read/written, error counts, and pipeline code version.

### Designing Idempotent Steps

A pipeline can fail after partially writing target data. If re-running creates duplicate rows or double-counts metrics, outputs become wrong. Design for idempotency using unique keys, upserts, `run_id`-scoped staging, and transactional publishing after validation.

A batch processing pattern:

1. Create an orchestration run record for `run_id` and capture the starting watermark.
2. Extract into staging tagged with `run_id`.
3. Validate row counts, types, keys, and time ranges.
4. Merge/upsert staging into target tables inside a suitable transaction.
5. Advance the watermark only after the merge succeeds.
6. Record metrics and mark the run complete.

### Retries and Dead-Letter Handling

Retries help with transient network glitches, timeouts, or brief target outages. Never retry permanent data errors such as type mismatches or unique violations indefinitely. Unprocessable events can be routed to a dead-letter queue or error table with payload, error code, and timestamp; restrict access since payloads may contain sensitive data.

### Source-to-Target Reconciliation

Reconciliation goes beyond comparing total row counts. Compare by date partition, status, tenant, or grouped checksums. For transactional data, reconcile both counts and monetary totals by currency code. Classify discrepancies: normal lag, late-arriving data, unpropagated deletes, transformation bugs, or lost events.

## 14. Operational Monitoring

Build operational dashboards covering both PostgreSQL and pipelines. Important signals include:

| Category | Metrics | Meaning |
|---|---|---|
| Connections | Session counts, waiting sessions, auth failures | Detect connection exhaustion or misconfigured auth |
| Queries | p95/p99 latency, slow queries, buffer reads | Spot dashboards generating excessive load |
| Batch pipelines | Runtime, rows read/written, watermarks | Spot slow jobs or missed data windows |
| CDC | Consumer lag, offset/LSN, slot age, retained WAL | Spot stalled change streams |
| Replicas | Replay lag, standby status, conflicts | Assess freshness of read data |
| Data quality | Error row counts, duplicate keys, null rates, reconciliation diffs | Detect invalid or corrupted data |
| Infrastructure | CPU, RAM, I/O, filesystem space | Spot bottlenecks or disk-full risks |

Useful alerts must map to concrete actions. For example, an alert on WAL retained by a replication slot should identify the specific slot, consumer, and remaining disk space. A delayed pipeline alert should show expected watermark, actual watermark, and last run timestamp.

### Useful Monitoring Queries

Count connections by state:

```sql
SELECT
    datname,
    usename,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY sessions DESC;
```

Find long-running queries:

```sql
SELECT
    pid,
    usename,
    application_name,
    now() - query_start AS duration,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start < now() - interval '1 minute'
ORDER BY query_start;
```

Check COPY progress when your PostgreSQL version provides the progress view:

```sql
SELECT *
FROM pg_stat_progress_copy;
```

Monitoring queries may require privileges to observe other sessions, such as membership in a monitoring role or appropriate administrative rights. Never grant superuser privileges merely to power an operational dashboard.

## 15. Troubleshooting Common Connection Issues

### `connection refused`

Verify PostgreSQL is running, check port, `listen_addresses`, firewalls, routing, and hostname. If the client runs inside a container, `localhost` points to the client container itself rather than the database container.

### `no pg_hba.conf entry`

Check the client IP address actually seen by the server, database name, username, rule ordering in `pg_hba.conf`, and whether TLS is used. After editing the file, reload configuration if the change supports reload.

### TLS Certificate Errors

Check the CA trusted by the client, certificate expiration, hostname/SAN match, and SSL mode. Never resolve certificate errors in production by downgrading to unverified modes.

### `password authentication failed`

Confirm the role exists, the password/secret is accurate, whether secrets were rotated, and whether the client is reading an outdated environment variable or secret version. Verify the authentication method configured in `pg_hba.conf`.

### `too many connections`

Check `max_connections`, session counts per role/database, and how tools close connections. Consider connection pooling, concurrency caps, reducing workers, and separating workloads. Simply raising `max_connections` increases memory footprint and resource contention.

### BI Reading Stale Data

Check whether the tool caches results, refresh timestamps, timezones, transaction snapshots, replica lag, and pipeline watermarks. Distinguish BI-layer caching from database or warehouse lag.

### CDC Not Advancing

Check whether the connector is running, replication privileges, whether the slot is active, whether LSN/offset advances, schema errors, and WAL space. Never drop the slot before evaluating consumer recovery options.

## 16. Onboarding Workflow for a New Integration

A rollout workflow can follow this sequence:

1. **Define data goals:** which tables dashboards need, max acceptable lag, historical retention, and metric definitions.
2. **Select architecture:** direct queries, read replica, batch ETL, logical replication, CDC, or FDW.
3. **Design access control:** create dedicated roles, scope schemas/tables, configure TLS and network rules.
4. **Standardize contracts:** agree on column names, data types, timezones, currencies, keys, and metric semantics.
5. **Load test:** run representative queries and measure concurrency, latency, I/O, and OLTP impact.
6. **Build the pipeline:** initial snapshot, incremental load, or CDC; persist watermarks/offsets and ensure idempotency.
7. **Validate quality:** check keys, nulls, counts, totals, and source/target reconciliation.
8. **Set up monitoring:** dashboards, lag alerts, WAL retention, job failures, slow queries, and disk capacity.
9. **Rehearse recovery:** stop the connector, re-run jobs, replay events, restore from snapshot, and verify zero data loss.
10. **Hand over to operations:** document owners, SLAs, secret rotation, schema change processes, and incident runbooks.

## 17. Example Pipeline Design: Orders from PostgreSQL to a Data Warehouse

Suppose an application stores `orders` in PostgreSQL. The data warehouse needs a `fact_orders` table to analyze order counts, revenue, and cancellation rates by date, region, and currency.

### Target Table and Load Metadata

```sql
CREATE TABLE analytics.fact_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint,
    order_status text NOT NULL,
    created_at timestamptz NOT NULL,
    total_amount numeric(14, 2),
    currency_code char(3) NOT NULL,
    source_updated_at timestamptz NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analytics.etl_watermark (
    pipeline_name text PRIMARY KEY,
    last_updated_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

`fact_orders` tracks the current state of each order. If historical analysis of every status transition is required, add an event history table or Slowly Changing Dimension (SCD) instead of overwriting the current row alone.

### Extracting a Data Window

Suppose each run reads the interval `[window_start, window_end)`. Set `window_start` with slight overlap behind the prior watermark to reduce the risk of missing late-arriving changes. Upsert at the target by `order_id`, applying changes only when `source_updated_at` is newer than or equal to the stored value.

```sql
SELECT
    id,
    customer_id,
    status,
    created_at,
    total_amount,
    currency_code,
    updated_at
FROM public.orders
WHERE updated_at >= :window_start
  AND updated_at <  :window_end
ORDER BY updated_at, id;
```

If the source performs hard deletes, add a tombstone table or switch to CDC so the target knows rows were deleted. If multiple transactions frequently update the same order, low-resolution timestamps may be insufficient to disambiguate order; consider versions or LSNs.

### Validation and Publishing

After loading staging, validate duplicate keys, required fields, currency values, and timestamp bounds. Then merge into `fact_orders`, update the watermark inside the target transaction, and mark `run_id` complete. If the merge fails, the watermark must not advance.

### Dashboard

The dashboard can aggregate by date and currency:

```sql
SELECT
    created_at::date AS order_date,
    currency_code,
    count(*) FILTER (WHERE order_status = 'paid') AS paid_orders,
    sum(total_amount) FILTER (WHERE order_status = 'paid') AS paid_amount,
    count(*) FILTER (WHERE order_status = 'cancelled') AS cancelled_orders
FROM analytics.fact_orders
GROUP BY created_at::date, currency_code
ORDER BY order_date, currency_code;
```

Before releasing the dashboard, confirm whether `paid_amount` includes tax, shipping fees, discounts, and refunds. That definition belongs to the business data contract and cannot be inferred from SQL data types alone.

## 18. Design Pitfalls to Avoid

- Letting BI tools connect as a superuser or an application role with write access across the entire database.
- Letting multiple dashboards run heavy aggregation queries directly on the primary without concurrency limits.
- Using timestamps as watermarks without handling late records, duplicate timestamps, or deletes.
- Advancing watermarks before target data is committed.
- Assuming CDC guarantees end-to-end exactly-once semantics across all components without idempotency.
- Neglecting replication slots and letting WAL grow until disks fill up.
- Assuming logical replication automatically syncs DDL, sequences, or large objects.
- Letting BI dashboards define metrics inconsistently across teams.
- Failing to standardize timezones and currencies during aggregation.
- Storing passwords in repositories, notebooks, or logs.
- Altering source schemas without notifying pipeline and dashboard owners.
- Lacking source-to-target reconciliation or post-incident replay procedures.

## 19. Practice Exercises

### Exercise 1: Create a Read-Only BI Account

Create a `bi_reader` role, grant connect on the `sales` database, usage on the `reporting` schema, and `SELECT` on existing reporting tables. Configure default privileges for the role owning reporting tables. Verify that `bi_reader` can query reporting views but cannot `INSERT`, `UPDATE`, or `DELETE` operational tables.

### Exercise 2: Create a Dashboard View

Create a `reporting.daily_sales` view aggregating paid order counts by date and currency code. Connect a BI tool using the read-only role and build a time-series chart. Clearly display the timezone and revenue definition.

### Exercise 3: Build an Incremental Load

Create a staging table in the target. Extract `orders` by `updated_at` using an overlapping window. Use `INSERT ... ON CONFLICT` to upsert. Run the pipeline twice over the same range and verify results are not duplicated.

### Exercise 4: Handle Source Deletes

Simulate soft deletes with `deleted_at`. Update the pipeline to propagate deleted state to the target. Then explain how the design would change if the source performs hard deletes without a change-log table.

### Exercise 5: Monitor Logical Replication

Create a publication in a test environment, a subscription in a subscriber database, and sync a table with a primary key. Insert, update, and delete several rows; observe results on the subscriber and in replication monitoring views. Document behavior when the subscriber pauses temporarily.

### Exercise 6: Simulate Slow CDC

In a test environment, stop the consumer while keeping the replication slot. Monitor `restart_lsn`, retained WAL size, and alerts. Restart the consumer and verify offsets advance and WAL is reclaimed as the system catches up.

### Exercise 7: Measure BI Query Impact

Run a representative aggregation query with `EXPLAIN (ANALYZE, BUFFERS)` on test data. Compare before and after creating a suitable index. Measure the overhead on a representative write workload to understand index maintenance costs.

### Exercise 8: Validate Data Contracts

Write queries to detect duplicate keys, unexpected `NULL` required fields, invalid currency codes, and anomalous totals. Integrate these checks into the pipeline validation step before publishing data for BI.

## 20. Review Questions

**1. When should BI query PostgreSQL directly?**

When query volume and user counts are manageable, low latency is important, and queries do not noticeably impact OLTP workloads. As load grows, consider a read replica or data warehouse.

**2. Does a read replica guarantee dashboards always see the latest data?**

No. A standby can have replication lag. Dashboards must tolerate and surface lag, or read from a source offering consistency aligned with business requirements.

**3. Why use a dedicated read-only role for BI?**

To restrict data scope and reduce the risk of dashboards or ad-hoc queries mutating operational data. Separate roles also simplify auditing and independent credential rotation.

**4. When can an `updated_at`-based watermark miss data?**

When updates do not change the timestamp, late-arriving records fall behind the watermark, clocks skew, boundary timestamps tie, or rows are hard-deleted without tombstones. Overlap windows, upserts, versions, and CDC mitigate these risks.

**5. Why must ETL pipelines be idempotent?**

Pipelines may retry after failures or reprocess data. Idempotency ensures re-runs do not duplicate rows, overwrite newer state with stale records, or corrupt metrics.

**6. Does logical replication sync DDL?**

It does not automatically replicate all DDL. Schema changes must be deployed on subscribers via a separate process. Sequence states and large objects also require separate handling.

**7. How can a replication slot fill up the disk?**

A slot retains WAL not yet acknowledged by its consumer. If the consumer stops or lags severely, WAL cannot be recycled and `pg_wal` disk usage can grow rapidly.

**8. When should materialized views be used?**

When aggregation queries are expensive and scheduled data freshness is acceptable. Plan refresh schedules and display the last refresh timestamp.

**9. Why standardize timezones and currencies?**

Without consistent timezones, metrics can fall onto different reporting dates. Summing disparate currencies without defined conversion rates and rules yields meaningless totals.

**10. What should be monitored beyond job success status?**

Watermarks, rows read/written, latency/lag, replication slots, WAL retention, slow queries, disk capacity, data quality, and reconciliation discrepancies. A job reporting success can still produce missing or inaccurate data.

## 21. PostgreSQL References

- PostgreSQL Documentation — Client Authentication (`pg_hba.conf`): https://www.postgresql.org/docs/current/client-authentication.html
- PostgreSQL Documentation — Database Roles: https://www.postgresql.org/docs/current/user-manag.html
- PostgreSQL Documentation — `GRANT`: https://www.postgresql.org/docs/current/sql-grant.html
- PostgreSQL Documentation — `ALTER DEFAULT PRIVILEGES`: https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html
- PostgreSQL Documentation — `COPY`: https://www.postgresql.org/docs/current/sql-copy.html
- PostgreSQL Documentation — `CREATE PUBLICATION`: https://www.postgresql.org/docs/current/sql-createpublication.html
- PostgreSQL Documentation — `CREATE SUBSCRIPTION`: https://www.postgresql.org/docs/current/sql-createsubscription.html
- PostgreSQL Documentation — Logical Replication: https://www.postgresql.org/docs/current/logical-replication.html
- PostgreSQL Documentation — Logical Decoding: https://www.postgresql.org/docs/current/logicaldecoding.html
- PostgreSQL Documentation — Replication Progress Reporting: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — `postgres_fdw`: https://www.postgresql.org/docs/current/postgres-fdw.html
- PostgreSQL Documentation — Materialized Views: https://www.postgresql.org/docs/current/rules-materializedviews.html
- PostgreSQL Documentation — `EXPLAIN`: https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL Documentation — Row Security Policies: https://www.postgresql.org/docs/current/ddl-rowsecurity.html

Connecting BI, ETL, and analytics systems is part of overall data architecture. Choosing the right extraction method, creating least-privilege roles, standardizing data contracts, designing replayable incremental loads or CDC, and monitoring lag keep analytics trustworthy while protecting transactional PostgreSQL workloads.
