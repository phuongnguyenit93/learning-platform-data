# Comparing postgres_fdw, dblink, and Data Replication

PostgreSQL offers several ways to work with data stored in another database. Three common approaches are using `postgres_fdw` to query remote tables as if they were tables in the current database, using `dblink` to send SQL statements over another PostgreSQL connection, or copying data to the target database via replication or an ETL pipeline.

Each approach addresses different requirements. `postgres_fdw` fits when applications need to access source data directly via SQL and want PostgreSQL to participate in query planning. `dblink` is useful when you need to issue a remote statement explicitly or embed a remote SQL call inside a function. Data replication fits when the system needs a local copy of data for reads, analytics, decoupling from live connectivity, or redundancy.

## 1. Distinguishing the Three Integration Approaches

Suppose there is a `sales` database on a source server and an `analytics` database on an analytics server. The analytics system needs to read the `public.orders` table from `sales`.

### 1.1. postgres_fdw: Accessing Remote Tables via Foreign Tables

`postgres_fdw` is the Foreign Data Wrapper (FDW) for PostgreSQL. You define a foreign server, a user mapping, and a foreign table in the target database. The foreign table mirrors the column structure of the remote object, so queries can reference the table name just like a regular SQL object:

```sql
SELECT order_id, customer_id, total_amount
FROM ext_sales.orders
WHERE order_date >= DATE '2026-01-01';
```

The data remains stored in the source database. When a query runs, PostgreSQL connects to the source and fetches the needed rows. The target database stores metadata for the foreign table rather than storing a copy of the data rows itself.

### 1.2. dblink: Sending SQL Over a Remote Connection

`dblink` provides functions to open another PostgreSQL connection, send SQL, and receive results. The remote SQL statement is written explicitly in the function call:

```sql
SELECT *
FROM dblink(
    'host=db.example.net port=5432 dbname=sales user=sales_reader',
    'SELECT order_id, customer_id, total_amount FROM public.orders'
) AS remote_orders(
    order_id bigint,
    customer_id bigint,
    total_amount numeric(12, 2)
);
```

The output of `dblink` has its column types declared on the caller side using `AS ...`. PostgreSQL does not treat the inner SQL string as a foreign table relation for planning joins with other tables. The query author must explicitly craft the remote SQL and define the result shape.

### 1.3. Data Replication: Creating a Copy at the Destination

Replication or ETL moves data from the source to a target database. Once the data is copied, applications query the local copy in `analytics`:

```sql
SELECT order_id, customer_id, total_amount
FROM reporting.orders;
```

Queries do not need to connect to the source database at read time. In exchange, the target dataset may lag behind the source by some interval and requires refresh workflows, lag monitoring, and schema-change handling.

There are multiple styles of replication. One-off export/import or scheduled ETL produces snapshots or periodically refreshed datasets. Logical replication streams data changes for selected tables. Physical streaming replication ships WAL to maintain a full-cluster standby.

## 2. High-Level Comparison Table

| Criterion | `postgres_fdw` | `dblink` | Data Replication |
|---|---|---|---|
| Model | Query remote data through foreign tables | Invoke remote SQL via functions | Transfer data into a target copy |
| Where is data stored? | Primarily at the source | Primarily at the source, unless results are persisted | A local copy exists at the target |
| How is it queried? | SQL against foreign tables | SQL passed as a string to a function | SQL against local replicated tables |
| Query planner integration | Yes; the FDW can push down certain operations to the source | Limited; the remote SQL is controlled by the author | Local queries; planner does not need source access |
| Data freshness | Read from source at query time under a remote transaction snapshot | Read or written remotely when the function is called | Depends on replication lag or ETL schedule |
| Network dependency at read time | Yes | Yes | No for queries against the updated local copy |
| Writing data | Supports certain writes through the FDW when permitted by the source | Can send write commands using `dblink_exec` | Written via replication or pipeline; not equivalent to direct source writes |
| Granularity | Per foreign table and server | Per SQL call and connection | Per publication, cluster, or ETL scope |
| Best fit | Federation, live query integration | Targeted remote commands, functions, or ad-hoc operations | Analytics, offloading the source, local reads, HA/DR depending on replication type |

No single option is always best. Determine whether the system prioritizes real-time freshness, local queryability, independence from the source, data scope, acceptable lag, and operational model.

## 3. postgres_fdw

### 3.1. Components and How It Works

A `postgres_fdw` setup typically consists of:

- **Foreign data wrapper**: the component interfacing with the remote data system—in this case, `postgres_fdw`.
- **Foreign server**: stores connection details for the remote server and database.
- **User mapping**: maps a local role to an account accessing the source database.
- **Foreign table**: local definition representing a remote table or view.

Access flow:

```text
Application / SQL query
        |
        v
Target database: ext_sales.orders (foreign table)
        |
        v
postgres_fdw
        |
        | connects via foreign server and user mapping
        v
Source database: sales.public.orders
        |
        v
Actual data
```

PostgreSQL can push down certain filter predicates, column lists, sorts, row limits, joins, and aggregates to the remote server when expressions and configuration satisfy pushdown conditions. This avoids shipping the entire table to the target database. However, not every expression or join can be pushed down to the source.

### 3.2. Basic Configuration

Execute these commands in the target database:

```sql
-- Install the extension.
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

-- Define the source server.
CREATE SERVER sales_source
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'db.example.net',
    port '5432',
    dbname 'sales'
);

-- Map the current role to a read account on the source.
CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_source
OPTIONS (
    user 'sales_reader',
    password '<secret-managed-outside-source-control>'
);

-- Prepare a schema to hold foreign tables.
CREATE SCHEMA IF NOT EXISTS ext_sales;

-- Import selected tables.
IMPORT FOREIGN SCHEMA public
    LIMIT TO (orders, customers)
    FROM SERVER sales_source
    INTO ext_sales;
```

The role on the source database must have connect privileges, `USAGE` on the schema, and required privileges on the tables or views. The local role needs privileges on the foreign server, schema, and foreign tables. Credentials must be managed securely; never commit real passwords into scripts stored in a repository.

After importing, you can query and combine foreign tables with local tables:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    SUM(o.total_amount) AS revenue
FROM ext_sales.customers AS c
JOIN ext_sales.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_date >= DATE '2026-01-01'
GROUP BY c.customer_id, c.customer_name
ORDER BY revenue DESC;
```

### 3.3. Writing Data via postgres_fdw

`postgres_fdw` supports `INSERT`, `UPDATE`, `DELETE`, and `TRUNCATE` under suitable conditions. Write capability depends on the remote object type, foreign table definition, FDW options, and remote account permissions.

Example updating a foreign table:

```sql
UPDATE ext_sales.orders
SET total_amount = 125.50
WHERE order_id = 9001;
```

This statement modifies data in the source database if the operation is supported and the remote account has privileges. Therefore, if the goal is read-only access, use a source account with read-only permissions. You can also configure the foreign table or foreign server to restrict writes according to system policy.

### 3.4. Transactions and Performance

`postgres_fdw` manages remote transactions tied to the local transaction. When a query needs data from a server, the FDW opens a corresponding remote transaction and maintains the connection according to session lifecycle rules. This enables remote operations to participate in PostgreSQL's transaction context.

However, when a transaction interacts with multiple remote servers, do not assume a complete, atomic distributed commit protocol spans all servers. Network failures or commit errors on one server can leave results inconsistent across sources. If you must update multiple systems, design error handling, reconciliation, and replayability.

Key performance considerations:

- Add remotely executable filter predicates and select only required columns to reduce network data transfer.
- Use `EXPLAIN (VERBOSE)` to inspect `Remote SQL` and see which operations are pushed down to the source.
- Ensure source tables have indexes matching filter predicates and join keys.
- Consider `use_remote_estimate` if cost estimates from local statistics are inaccurate; keep in mind fetching remote estimates also carries overhead.
- Tune `fetch_size` when queries return many rows to balance network round trips and buffer memory.
- Evaluate latency, bandwidth, and load on the source server; a heavy aggregation query can still place substantial load on the source.

Example plan inspection:

```sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, total_amount
FROM ext_sales.orders
WHERE customer_id = 1001;
```

`postgres_fdw` fits when you want a fairly natural SQL access layer, have multiple reusable queries, and want the planner to optimize part of the remote work. It does not create a local data copy for independent querying if the source loses connectivity.

## 4. dblink

### 4.1. How It Works

`dblink` is an extension providing functions to connect to another PostgreSQL server and execute SQL there. The author controls the remote statement and then declares the result structure in the local query when rows are returned.

Install the extension in the database calling the functions:

```sql
CREATE EXTENSION IF NOT EXISTS dblink;
```

### 4.2. One-Off Remote Queries

```sql
SELECT *
FROM dblink(
    'host=db.example.net port=5432 dbname=sales user=sales_reader password=<secret>',
    'SELECT order_id, customer_id, total_amount
     FROM public.orders
     WHERE order_date >= DATE ''2026-01-01'''
) AS r(
    order_id bigint,
    customer_id bigint,
    total_amount numeric(12, 2)
);
```

A `dblink` call has two key parts: connection information and the SQL string sent to the source. Because PostgreSQL treats the function return type as `record`, the `AS r(...)` clause must declare the column names and data types of the returned columns. Declared data types must match the actual result.

When passing a direct connection string, protect credentials carefully. Never store real passwords in source code, logs, or command history. You can manage connections via a foreign server and user mapping through `dblink_fdw` instead of embedding credentials in every SQL statement.

### 4.3. Named Connections and Reuse

If you need multiple calls to the same source within a session, open a named connection:

```sql
SELECT dblink_connect(
    'sales_conn',
    'host=db.example.net port=5432 dbname=sales user=sales_reader'
);

SELECT *
FROM dblink(
    'sales_conn',
    'SELECT order_id, total_amount FROM public.orders LIMIT 10'
) AS r(
    order_id bigint,
    total_amount numeric(12, 2)
);

SELECT dblink_disconnect('sales_conn');
```

A named connection persists in the local database session until disconnected or the session ends. Close connections when finished and handle mid-function errors to avoid leaking resources. A `dblink` call passing a connection string directly opens a connection for that call; named connections are useful when you want reuse.

### 4.4. Sending Commands That Do Not Return Rows

`dblink_exec` is typically used for remote commands that do not return a result set, such as `INSERT`, `UPDATE`, `DELETE`, or certain administrative commands:

```sql
SELECT dblink_exec(
    'sales_conn',
    'UPDATE public.orders
     SET total_amount = 125.50
     WHERE order_id = 9001'
);
```

The function returns the execution status of the remote command. The connection account must hold appropriate permissions on the source.

### 4.5. Remote Transactions and Limitations

A `dblink` connection maintains its own transaction context on the remote server. A write sent over a connection in autocommit mode can commit on the source even if the local transaction later rolls back. If you need explicit control over the remote transaction, send `BEGIN`, `COMMIT`, and `ROLLBACK` through the named connection itself:

```sql
SELECT dblink_exec('sales_conn', 'BEGIN');

SELECT dblink_exec(
    'sales_conn',
    'UPDATE public.orders
     SET total_amount = 125.50
     WHERE order_id = 9001'
);

SELECT dblink_exec('sales_conn', 'COMMIT');
```

Managing the remote transaction this way is the responsibility of the application or function. A `ROLLBACK` in the local database does not automatically roll back an already-committed remote transaction. Conversely, if a remote transaction remains open, you must explicitly roll it back or handle broken connections. Multiple `dblink` calls must never be treated as a single atomic distributed transaction.

A major limitation is that the SQL statement is passed as a string. `dblink` does not provide bind-parameter ergonomics like ordinary SQL queries against local tables. When interpolating values into dynamic SQL, use safe quoting such as `format('%L', value)` for literals and `format('%I', identifier)` for object names; never concatenate untrusted input directly into SQL strings. If query logic is complex, reused across multiple consumers, or needs the planner to optimize remote joins and filters, `postgres_fdw` is usually easier to maintain.

`dblink` is well-suited for a targeted remote action, an orchestration function, or running SQL that the foreign table model cannot express cleanly. It generally requires the author to manage connections, result types, dynamic SQL, transactions, and error handling explicitly.

## 5. Data Replication

Data replication creates a copy of data in the receiving database. When querying the replica, applications do not need to connect to the source database. You should distinguish three categories of approaches because their mechanisms, latency, and scope differ.

### 5.1. Snapshots or Scheduled ETL

A snapshot is a point-in-time capture of data. ETL (Extract, Transform, Load) reads data from a source, transforms it, and writes it to target tables. Pipelines may run once, hourly, daily, or on a business schedule.

For example, once `postgres_fdw` is configured, you can create a snapshot in the target database:

```sql
CREATE TABLE reporting.orders_snapshot AS
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM ext_sales.orders;
```

Or load data into an existing table:

```sql
INSERT INTO reporting.orders_snapshot (
    order_id,
    customer_id,
    order_date,
    total_amount
)
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM ext_sales.orders;
```

This example demonstrates materializing query results as local data. It does not by itself establish continuous synchronization. When run repeatedly, you must define how to handle duplicate records, updated records, and deleted records. Options include truncate-and-load, key-based upsert, updated-timestamp watermarks, or dedicated ETL/CDC tools depending on volume and consistency needs.

`COPY` and `\copy` can also export/import data via files. `COPY` operates on files on the PostgreSQL server host; `\copy` is a `psql` meta-command that reads/writes files on the client host. Both are great for bulk loading, though neither is a continuous change-sync mechanism between two databases on its own.

### 5.2. Logical Replication

Logical replication streams logical data changes from a publisher to a subscriber. You can choose specific tables to publish rather than replicating the entire cluster. The subscriber maintains its own tables to receive changes and can serve local queries.

Key concepts:

- **Publisher**: the source database hosting a publication.
- **Publication**: the set of tables and operation types published.
- **Subscriber**: the target database subscribing to changes.
- **Subscription**: the configuration connecting to and receiving data from a publication.
- **Replication slot**: retains the WAL position needed so the subscriber can continue receiving changes.

Basic flow:

```text
Publisher (source database)
       |
       | Publication: orders_pub
       | WAL + logical decoding
       v
Replication connection
       |
       v
Subscriber (target database)
       |
       | Subscription: orders_sub
       v
Local table reporting.orders
```

#### Preparing the Publisher

The publisher must be configured for logical replication, with `wal_level` set to `logical`. Parameters governing replication slots and WAL senders must accommodate the expected subscriber count. `pg_hba.conf` must allow the replication role to connect from the subscriber. Parameter changes require a restart or reload depending on the specific parameter.

Create a role for replication connections and grant read permissions on published tables:

```sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD '<secret-managed-outside-source-control>';

GRANT CONNECT ON DATABASE sales TO replicator;
GRANT USAGE ON SCHEMA public TO replicator;
GRANT SELECT ON TABLE public.orders, public.order_items TO replicator;
```

Create the publication:

```sql
CREATE PUBLICATION orders_pub
FOR TABLE public.orders, public.order_items;
```

A publication can be scoped to specific tables and operation types. For `UPDATE` or `DELETE` operations, source tables require an appropriate replica identity, typically a primary key. If no suitable key exists, evaluate `REPLICA IDENTITY` settings and their overhead.

#### Preparing the Subscriber

On the target database, create receiving tables with compatible schemas. Logical replication does not automatically replicate DDL table creations from the publisher; schemas must be prepared and managed separately.

Then create the subscription:

```sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=db.example.net port=5432 dbname=sales user=replicator password=<secret> sslmode=verify-full'
PUBLICATION orders_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
```

With `copy_data = true`, PostgreSQL performs an initial data copy for the subscribed tables and then continuously applies new changes. By default, the subscription is enabled and creates a replication slot on the publisher when using the corresponding defaults. Plan for WAL disk capacity, slot counts, and recovery if the subscriber stays offline for extended periods.

Logical replication usually runs asynchronously, so the subscriber may lag behind the publisher. Lag depends on change generation rate, network speed, apply speed, and subscriber load. Monitor subscription status and replication slots, and alert when lag or WAL accumulation exceeds operational thresholds.

#### What Logical Replication Does Not Do Automatically

- Does not automatically replicate DDL such as `CREATE TABLE`, `ALTER TABLE`, or index changes. Schema changes must be deployed on the subscriber via a separate process.
- Does not synchronize sequence state as part of table data. When failing over writes or cutting over, synchronize sequence values explicitly.
- Does not automatically resolve all conflicts if independent writes occur on the subscriber. Standard design keeps the publisher as the owner of replicated data; avoid modifying those rows directly on the subscriber without a conflict-resolution strategy.
- Is not an automatic multi-master solution. Core PostgreSQL logical replication flows from publisher to subscriber; bidirectional writes require dedicated architecture and conflict resolution.
- Does not replace backups. Replication propagates accidental deletes or bad updates too, so backups and point-in-time recovery remain essential.

Logical replication works well when you need a selective, continuously updated dataset for local reads or cross-system data integration. It is especially useful when the subscriber needs a subset of the publisher's data and can tolerate replication lag.

### 5.3. Physical Streaming Replication

Physical replication streams physical WAL records to maintain a standby of a PostgreSQL cluster. The standby is a storage/WAL-level replica of the entire cluster rather than a selective copy of a few tables like logical replication.

Key characteristics:

- Commonly used for high availability (HA), disaster recovery (DR), and read-only standbys.
- The standby replays WAL to stay close to the primary's state. Streaming replication can be asynchronous or configured as synchronous as required.
- A hot standby can serve read queries while receiving and replaying WAL.
- When switching roles, a standby is promoted to primary via a failover procedure.
- A physical standby must match the major version and physical requirements of PostgreSQL; it is not a tool for copying a subset of tables into an independent database.

Physical replication is appropriate when the goal is maintaining a full-cluster replica for redundancy or failover. If the goal is bringing only the `orders` table into an analytics database with its own schema and workload, logical replication or ETL is usually a better fit.

## 6. Deep Dive Comparison by Operational Criteria

### 6.1. Data Freshness and Availability

| Scenario | postgres_fdw | dblink | Data Replica |
|---|---|---|---|
| Need the latest data from the source | Queries the source directly | Calls SQL directly on the source | May lag based on replication or ETL schedule |
| Source temporarily loses connectivity | Queries depending on source fail | Calls depending on source fail | Local copy remains readable |
| Frequent high-volume reads | Can strain network and source; needs pushdown | Can strain network; author must tune remote SQL | Local reads are usually better once loaded |
| Need a point-in-time snapshot | Can materialize a snapshot from query results | Can fetch results and write to a table | The natural purpose of snapshot/ETL |

`postgres_fdw` and `dblink` read source data at query execution time, which also makes read availability dependent on the network and source health. A local replica improves read independence at the cost of accepting and managing data lag.

### 6.2. Transactions and Consistency

With `postgres_fdw`, remote operations are managed within the FDW's transaction context. It is convenient when querying and updating foreign tables via SQL. Still, do not assume modifications across multiple remote servers commit as a single atomic distributed transaction.

With `dblink`, the remote connection has an independent transaction. The author must explicitly manage `BEGIN`, `COMMIT`, and `ROLLBACK` to group multiple remote statements into one transaction. Local and remote transactions do not automatically share commit/rollback outcomes.

With logical replication, the publisher commits changes first and the subscriber receives and applies them afterward. This is a normal asynchronous stream; at any instant, the subscriber may not yet reflect every committed publisher change. With physical synchronous replication, synchronous settings can require standby acknowledgment according to policy, though you must weigh durability gains against commit latency.

With scheduled ETL, consistency depends on how the pipeline captures snapshots and tracks progress. Each run should have a clear cutoff point, idempotent error recovery, and safeguards against missing or duplicating records.

### 6.3. Performance and Scalability

`postgres_fdw` reduces SQL boilerplate, yet queries still incur network latency and source server load. Push down filter conditions and aggregations to the source whenever possible. If reports run repeatedly over large datasets, a local copy generally reduces source load and read-time network cost.

`dblink` gives the author full control over the remote SQL string. That helps for specialized operations, but increases responsibility for safe SQL construction, result-type definitions, and tuning plans on both sides. The local planner does not optimize the SQL embedded inside a `dblink` call.

Logical replication introduces continuous change streaming and apply overhead. It avoids re-reading entire tables after the initial copy, at the cost of WAL retention, replication slots, network traffic, and apply workers. Batch ETL can be efficient for large volumes but creates load spikes during scheduled runs. Physical replication ships WAL for the whole cluster and excels for physical standbys, though it cannot selectively replicate individual tables.

### 6.4. Security and Access Control

For all three options, enforce least privilege:

- Use dedicated integration accounts granted access only to necessary databases, schemas, and tables.
- Protect credentials; prefer secret management, strong authentication, and TLS suited to the environment.
- Restrict connections via `pg_hba.conf`, firewalls, and `CONNECT` privileges on the source.
- For `postgres_fdw`, manage `USAGE` on foreign servers, user mappings, schemas, and foreign tables in the target database.
- For `dblink`, avoid exposing sensitive data in dynamic SQL, logs, or scripts; properly quote literals and identifiers.
- For logical replication, grant replication and table-read privileges narrowly; restrict subscriber source addresses.
- Never use a superuser account merely to simplify integration setup.

## 7. When to Choose Which Option?

| Requirement | Option to Consider | Rationale |
|---|---|---|
| Query remote PostgreSQL tables using standard SQL | `postgres_fdw` | Foreign tables integrate natively with PostgreSQL queries and the planner. |
| Join remote tables with local tables | `postgres_fdw` | Can push down eligible joins/filters; query syntax is easy to reuse. |
| Run a specific remote statement inside a function or orchestrator | `dblink` | Function call makes the exact remote SQL explicit. |
| Manually control a remote sequence of commands or transaction | `dblink` | Allows issuing remote SQL in explicit order, though errors/commits must be managed manually. |
| Heavy recurring reports while offloading the source | Logical replication or ETL | Data is stored locally for queries without hitting the source every time. |
| Hourly or daily data snapshots only | ETL or batch load | Avoids maintaining continuous connections and change streams. |
| Maintain a selective copy of specific tables | Logical replication | Uses publications/subscriptions for continuous selective sync. |
| Redundancy or failover for an entire PostgreSQL cluster | Physical streaming replication | Maintains a physical cluster standby. |
| Must serve reads even when the source is disconnected | Local replica | Queries do not depend on source connectivity at read time. |

Approaches can also be combined. For instance, `postgres_fdw` can pull source data inside an ETL pipeline, which then writes transformed results into local tables. Logical replication can feed changes into a staging database while local views and summary tables power reporting. What matters is giving each layer a clear owner, update mechanism, and error-handling rule.

## 8. Scenario-Based Design Examples

### 8.1. Application Looking Up Current Order Status

An ordering service needs live order statuses from the `sales` database without maintaining its own replica. `postgres_fdw` is a sensible fit if query volume and source load are controlled. Import only the required tables, grant read access, and expose a local view as a stable interface.

If only a single administrative function needs to dispatch a tightly controlled remote update, `dblink` may fit. Remember that the remote transaction will not automatically roll back with the local transaction.

### 8.2. Analytics Warehouse Needing Large Order Volumes

An analytics warehouse runs numerous aggregation reports across millions of orders. If every report hits the source via FDW, the source faces heavy query load and network transfer costs. Logical replication can copy the orders table into the analytics database, or ETL can load only the normalized fields needed for reporting.

The subscriber or target table allows adding analytics-specific indexes, partitioning, and structures. In return, operations must monitor replication lag or ETL schedules and manage schema changes.

### 8.3. System Needing a Standby for Disaster Recovery

If the objective is recovering the entire database cluster when the primary fails, physical streaming replication is the right choice. FDW and `dblink` do not create physical standbys and do not replace backup/restore procedures.

If only a few business tables need to be available in another database, logical replication can fulfill that need. However, a logical subscriber does not automatically act as a promotable HA standby equivalent to a physical standby.

## 9. Common Errors and Risks

| Issue | Cause | How to Address |
|---|---|---|
| Foreign table queries are slow | Filters or joins not pushed down; slow network; missing source indexes | Inspect `EXPLAIN (VERBOSE)`, trim columns/rows, check indexes and cost estimates. |
| `postgres_fdw` fails to connect | Wrong server options, user mapping, authentication, TLS, or `pg_hba.conf` | Check each connection layer and permissions on both databases. |
| `dblink` throws a record-type error | Missing or mismatched column list in `AS record(...)` | Define exact names and types matching the remote result. |
| SQL passed via `dblink` fails on quotes | Multi-level nested quotes or unsafe string concatenation | Use dollar quoting where suitable and `format('%L', ...)` / `format('%I', ...)` for dynamic SQL. |
| Remote command committed despite local rollback | `dblink` connection had an independent transaction and committed remotely | Manage remote transactions explicitly; design reconciliation and compensation on error. |
| Subscriber receives no changes | Broken subscription, missing replication privileges, network failure, or inactive slot | Check subscription status, apply worker logs, replication slots, and connection config. |
| Logical replication stalls on update/delete | Source table lacks proper replica identity or subscriber hits a conflict | Check primary key/replica identity and subscriber data state. |
| Subscriber is missing new columns | DDL is not automatically replicated by logical replication | Apply schema migrations on the subscriber in a compatible order. |
| WAL grows rapidly on the publisher | Replication slot retains WAL while subscriber is stopped or lagging | Monitor slots and lag; recover the subscriber or handle the slot safely. |
| Snapshot ETL has duplicate or missing data | Re-runs lack idempotent keys or reliable watermarks | Design explicit upserts, staging, checkpoints, and delete handling. |

## 10. Deployment and Operations Workflow

Before choosing a solution, answer these questions:

1. How fresh must the data be: real-time, seconds/minutes lag, or scheduled updates?
2. Must the system remain queryable if the source loses connectivity?
3. Do you need a few tables or the entire cluster?
4. Do you need to write back to the source or only read?
5. What are the expected query volume and network data transfer?
6. Can the target schema lag behind the source? Who owns DDL changes?
7. How should connection, apply, or ETL failures be handled?

Once an approach is chosen, establish corresponding operational procedures:

- **With `postgres_fdw`**: manage foreign servers and user mappings via migrations; audit privileges; monitor query duration, Remote SQL, source load, and connection errors; update foreign tables when source schemas change.
- **With `dblink`**: govern the list of remote SQL queries; manage connection lifecycles; safely quote input values; define explicit result types; handle remote transactions and errors explicitly.
- **With logical replication**: manage publications/subscriptions; monitor replication slots, WAL usage, and lag; deploy DDL separately on subscribers; sync sequences during cutovers; handle conflicts and recovery.
- **With physical replication**: monitor WAL receiver/replay state and lag; rehearse failover/failback; verify backups and restore procedures.
- **With ETL/snapshots**: make jobs idempotent; track checkpoints and watermarks; log row counts, data timestamps, and errors; ensure safe re-runs without duplicating or dropping records.

Every approach should be tested in an environment closely matching production in data size, permissions, network, workload, and failure behavior. For critical integrations, implement periodic reconciliation between source and target—such as comparing row counts, update time ranges, or grouped checksums.

## 11. Conclusion

`postgres_fdw` provides a natural way to query remote tables through foreign tables while leveraging query planner pushdown. `dblink` lets you send explicit remote SQL, offering flexibility for specialized operations at the cost of managing more details manually. Data replication creates local copies: ETL fits snapshots or transformation pipelines, logical replication fits continuous selective synchronization, and physical replication fits full-cluster standbys.

Your choice should rest on data freshness requirements, availability during source outages, query load, replication scope, transaction guarantees, and operational capacity. Also remember that replication does not replace backups, FDWs do not create independent copies, and `dblink` does not automatically bind remote and local transactions together.

## References

- [PostgreSQL — postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html)
- [PostgreSQL — dblink](https://www.postgresql.org/docs/current/dblink.html)
- [PostgreSQL — Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html)
- [PostgreSQL — Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [PostgreSQL — COPY](https://www.postgresql.org/docs/current/sql-copy.html)