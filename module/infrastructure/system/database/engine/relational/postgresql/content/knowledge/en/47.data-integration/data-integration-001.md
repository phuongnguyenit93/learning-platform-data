# Foreign Data Wrapper and the External Data Table Model in PostgreSQL

PostgreSQL can query data located outside the current database through a **Foreign Data Wrapper (FDW)**. With an FDW, a table in another system can be represented in PostgreSQL as a foreign table. Applications send SQL to PostgreSQL; the planner and executor coordinate with the FDW to translate the appropriate portion of the work into operations against the external data source.

This model is useful when you need to integrate multiple databases, read data from legacy systems, combine operational data with external sources, or access files/objects/services through an appropriate wrapper. Users can query a foreign table using familiar SQL without having to write a custom connector for each query.

However, a foreign table is not the same as a local table. The data usually still resides at the remote source; latency, availability, permissions, transaction semantics, type mapping, and query pushdown depend on the FDW and the data source. Good design requires understanding which parts run on local PostgreSQL, which parts run on the remote system, and how to limit access costs.

This lesson covers FDW architecture, configuration objects, deploying `postgres_fdw`, importing schemas, querying and writing external data, optimizing query pushdown, security, operations, limitations, and hands-on exercises.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain Foreign Data Wrappers and the foreign table architecture.
2. Distinguish between local tables, foreign tables, views, and materialized views.
3. Identify the roles of the FDW handler, validator, foreign server, and user mapping.
4. Install, configure, and use `postgres_fdw`.
5. Import a foreign schema or declare a foreign table manually.
6. Query, join, filter, aggregate, and write data through foreign tables.
7. Understand query pushdown and read `EXPLAIN VERBOSE` to verify remote SQL.
8. Tune fetch size, remote estimates, batch writes, and network round trips.
9. Manage credentials, user mappings, privileges, and network security.
10. Understand transaction behavior, consistency, and distributed transaction limitations.
11. Monitor latency, remote sessions, errors, and availability.
12. Choose between FDW, ETL/ELT, replication, APIs, and materialization.
13. Design labs and runbooks for safe data integration.

## 2. What Is a Foreign Data Wrapper?

### 2.1. Concept

A Foreign Data Wrapper is an extension/interface in PostgreSQL that enables access to external data through foreign tables. An FDW hides the communication details with the data source and provides metadata so the PostgreSQL planner/executor knows how to read or write that data.

For example, `postgres_fdw` allows one PostgreSQL database to access tables located in another PostgreSQL server. From the local database, a user can run:

~~~sql
SELECT customer_id, email
FROM remote_crm.customers
WHERE active = true;
~~~

The foreign table `remote_crm.customers` is not a copy of the remote table. When the query is executed, the FDW can send SQL to the remote server and return the results to the local executor.

### 2.2. FDW Is Not Replication

| Characteristic | FDW | Replication |
| --- | --- | --- |
| Data | Usually reads/writes directly to the external source | Has a copy on the subscriber/replica |
| When data is fetched | When the query runs | Via stream/schedule |
| Local query | May require a network round trip | Reads from a local copy |
| Availability | Depends on remote source/network | Can continue reading the copy when the source is unavailable, depending on setup |
| Freshness | Near query time, following remote consistency | Subject to replication lag |
| Local storage | Metadata, does not necessarily store data | Stores a copy of the data |
| Best suited for | Federation, lookups, direct integration | Read scaling, DR, data distribution |

An FDW does not automatically create a durable copy. If you need fast, reliable queries when the remote source is down, consider materializing/copying the data or using replication.

### 2.3. FDW Is Not ETL

ETL/ELT typically extracts data, transforms it, and loads it into a target system to serve analytics or applications. An FDW enables direct federated querying at runtime. An FDW can be used as a source for ETL, but an FDW does not itself provide orchestration, retry policies, data quality pipelines, or historical snapshots.

### 2.4. Foreign Table

A foreign table is a local relation that has a schema and columns, while its data is provided by an FDW. It can appear in SQL like a table, join, or view. The catalog stores metadata; the data usually resides in the external source.

A foreign table can be declared manually or imported from a remote schema. PostgreSQL checks the declared column names/types against the FDW's capabilities; an incorrect mapping can cause errors or unexpected data casts.

### 2.5. Types of Data Sources

Depending on the wrapper, foreign data can come from:

- PostgreSQL or other relational databases;
- CSV/text files;
- ODBC/JDBC-accessible sources via an appropriate wrapper;
- Key-value/document stores;
- REST/API endpoints or specialized systems;
- Object storage or external services.

There is no single core FDW that supports every source. Each wrapper has its own prerequisites, feature set, security model, and compatibility matrix.

## 3. FDW Architecture and Objects

### 3.1. General Processing Flow

~~~text
Application / SQL client
        |
        v
Local PostgreSQL parser and planner
        |
        v
Foreign table metadata
        |
        v
FDW planner callbacks
        |
        +---- pushable filters / joins / sorts ----> Remote source
        |                                              |
        <------------- rows / remote results ----------+
        |
        v
Local executor: remaining filters / joins / projection
        |
        v
Query result
~~~

The planner decides which parts can be sent remotely based on the FDW's capabilities, expressions, options, and type/collation compatibility. Anything not pushed down runs on local PostgreSQL after the data is transferred over the network.

### 3.2. FDW Handler

A handler is a function provided by the extension that returns function pointers for the callbacks PostgreSQL uses during planning and execution. Depending on the wrapper, callbacks can support scans, modifications, explain, analyze, schema import, parallel execution, or asynchronous execution.

### 3.3. FDW Validator

A validator checks the options passed when creating a foreign server, user mapping, or foreign table. For example, a validator can check whether an option name, format, or value is valid.

### 3.4. Foreign-Data Wrapper Object

The wrapper is a database object bound to an extension/library:

~~~sql
CREATE FOREIGN DATA WRAPPER wrapper_name
HANDLER handler_function
VALIDATOR validator_function;
~~~

Usually an extension installs the wrapper via `CREATE EXTENSION`; DBAs do not need to define handlers manually for built-in or packaged wrappers.

### 3.5. Foreign Server

A foreign server is a configuration representing an external data source. With `postgres_fdw`, options typically include host, port, and database name:

~~~sql
CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm'
);
~~~

`CREATE SERVER` does not open a persistent connection to the remote database. A connection is established when a query or operation needs to use the foreign server.

### 3.6. User Mapping

A user mapping maps a local PostgreSQL user to credentials/identity on the remote source:

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER crm_server
OPTIONS (
    user 'crm_readonly',
    password 'replace-with-secret'
);
~~~

Do not put real passwords into source control, public migration scripts, or logs. The example above uses a placeholder only; use secret management and appropriate catalog access controls in production.

### 3.7. Foreign Table

A foreign table defines columns and maps to a remote object:

~~~sql
CREATE FOREIGN TABLE remote_customers (
    customer_id bigint,
    email text,
    active boolean
)
SERVER crm_server
OPTIONS (
    schema_name 'public',
    table_name 'customers'
);
~~~

### 3.8. Local Schema and Remote Schema

The local schema containing a foreign table can differ from the schema of the remote object. The `schema_name`/`table_name` options of `postgres_fdw` identify the remote relation; the local schema only organizes the namespace in the current database.

### 3.9. Privileges

Permissions are checked on both sides:

- The local user needs USAGE privilege on the foreign server;
- The local user needs USAGE privilege on the foreign-data wrapper if required by policy;
- The local user needs the corresponding SELECT/INSERT/UPDATE/DELETE privileges on the foreign table;
- A user mapping must exist for the local user or PUBLIC;
- The remote identity needs privileges on the remote database/schema/table.

A local GRANT does not automatically grant remote privileges.

### 3.10. Important Catalogs

Useful catalog views:

| Catalog/view | Purpose |
| --- | --- |
| `pg_foreign_data_wrapper` | Registered wrappers |
| `pg_foreign_server` | Foreign servers |
| `pg_user_mappings` | User mappings; sensitive information may be masked based on privileges |
| `pg_foreign_table` | Foreign table options |
| `information_schema.foreign_tables` | Foreign tables per information schema |
| `pg_class`/`pg_attribute` | Relation and column metadata |

## 4. Installing and Configuring postgres_fdw

### 4.1. When to Use postgres_fdw?

Use `postgres_fdw` when local PostgreSQL needs to access data from another PostgreSQL database and you want SQL-based query federation. Both servers need network connectivity and appropriate version/feature compatibility.

### 4.2. Checking the Extension

On the local database:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
~~~

The extension package/library must be installed on the database server host/container. In managed PostgreSQL, the provider must support the extension and may require an allowlist or special privileges.

### 4.3. Creating a Foreign Server

~~~sql
CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm',
    application_name 'local-fdw-crm'
);
~~~

`application_name` helps identify remote connections in `pg_stat_activity` if the remote server supports receiving this value from libpq options.

### 4.4. Creating a User Mapping

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER crm_server
OPTIONS (
    user 'crm_readonly',
    password 'use-a-secret-manager'
);
~~~

A mapping can be created for a specific local role or for PUBLIC. A PUBLIC mapping widens the scope of the shared identity; choose it only when your policy/security model permits.

### 4.5. Granting Local Privileges

~~~sql
GRANT USAGE ON FOREIGN SERVER crm_server TO app_reader;
GRANT USAGE ON FOREIGN DATA WRAPPER postgres_fdw TO app_reader;
~~~

Once foreign tables are created, grant privileges on the schema/tables:

~~~sql
GRANT USAGE ON SCHEMA remote_crm TO app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA remote_crm TO app_reader;
~~~

`GRANT SELECT ON ALL TABLES` affects existing tables. Default privileges need to be configured separately if new foreign tables will be created later.

### 4.6. Creating a Local Schema

~~~sql
CREATE SCHEMA IF NOT EXISTS remote_crm;
GRANT USAGE ON SCHEMA remote_crm TO app_reader;
~~~

### 4.7. Importing a Foreign Schema

`IMPORT FOREIGN SCHEMA` reads remote metadata and creates local foreign tables:

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders, order_items)
FROM SERVER crm_server
INTO remote_crm;
~~~

You can use `EXCEPT` to exclude certain tables:

~~~sql
IMPORT FOREIGN SCHEMA public
EXCEPT (audit_log, internal_secrets)
FROM SERVER crm_server
INTO remote_crm;
~~~

Importing only creates foreign table metadata; it does not copy data. Verify remote privileges and object-creation privileges in the local schema.

### 4.8. Checking Created Foreign Tables

~~~sql
SELECT
    foreign_table_schema,
    foreign_table_name,
    foreign_server_name
FROM information_schema.foreign_tables
WHERE foreign_table_schema = 'remote_crm'
ORDER BY foreign_table_name;
~~~

### 4.9. Checking Servers and Mappings

~~~sql
SELECT
    srvname,
    fdwname,
    srvoptions
FROM pg_foreign_server AS s
JOIN pg_foreign_data_wrapper AS w ON w.oid = s.srvfdw
ORDER BY srvname;

SELECT
    srvname,
    usename,
    umoptions
FROM pg_user_mappings;
~~~

Credentials in catalogs must not be exposed in shared output/logs. Access to view user mappings can expose sensitive options; restrict read access.

### 4.10. Testing the Connection

~~~sql
SELECT *
FROM remote_crm.customers
LIMIT 10;
~~~

The first query may incur network connection setup and authentication overhead. Check DNS, firewall, TLS, remote role, schema/table names, and type mappings if the connection fails.

## 5. Querying Foreign Tables

### 5.1. Basic SELECT

A foreign table is used in FROM just like a local table:

~~~sql
SELECT customer_id, email
FROM remote_crm.customers
WHERE active
ORDER BY customer_id
LIMIT 100;
~~~

Whether filtering/ordering/limiting is sent remotely depends on the FDW and its pushdown capabilities. Do not assume every clause runs remotely.

### 5.2. Joining Local and Foreign Tables

~~~sql
SELECT
    o.order_id,
    o.created_at,
    c.email
FROM public.local_orders AS o
JOIN remote_crm.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= current_date - interval '7 days';
~~~

If the join is not pushed down, PostgreSQL may fetch a set of rows from the remote server and join locally. This can be very expensive over the network if the foreign side is large. Inspect the plan before putting the query into production.

### 5.3. Joining Between Foreign Tables on the Same Server

When both foreign tables share the same foreign server and the same user mapping/compatible options, `postgres_fdw` can push the join down to the remote server under supported conditions. A remote join typically reduces the amount of data transferred back to the local instance.

~~~sql
SELECT
    c.customer_id,
    c.email,
    o.order_id,
    o.total_amount
FROM remote_crm.customers AS c
JOIN remote_crm.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.created_at >= date '2026-01-01';
~~~

Verify with `EXPLAIN VERBOSE`; do not infer pushdown merely from both tables being foreign.

### 5.4. Aggregate Pushdown

`postgres_fdw` can push down certain aggregate queries when expressions and semantics are compatible. For example:

~~~sql
SELECT status, count(*), sum(total_amount)
FROM remote_crm.orders
GROUP BY status;
~~~

If the aggregate runs remotely, only the grouped rows are transferred back. Without pushdown, all qualifying rows may have to traverse the network to be aggregated locally.

### 5.5. ORDER BY and LIMIT

~~~sql
SELECT order_id, created_at
FROM remote_crm.orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Pushing down ORDER BY/LIMIT can significantly reduce data transfer. Incompatible collations, NULL ordering, expressions, or semantics can prevent pushdown.

### 5.6. Filter Pushdown

Simple predicates on foreign columns often have a good chance of being pushed down. For example:

~~~sql
SELECT *
FROM remote_crm.orders
WHERE customer_id = 1001
  AND created_at >= timestamp '2026-01-01 00:00:00';
~~~

Local PostgreSQL may still retain some filters if an expression is not evaluated as safe by the FDW or cannot be translated equivalently.

### 5.7. Projection Pushdown

Select only the columns you need. Avoid `SELECT *` when the remote table has many wide columns, JSON/BLOBs, or large text payloads. Projection pushdown reduces bytes sent over the network when supported by the FDW.

~~~sql
SELECT order_id, status
FROM remote_crm.orders
WHERE customer_id = 1001;
~~~

### 5.8. Subqueries and CTEs

The planner can flatten/inline or materialize subqueries/CTEs depending on query semantics and version. Do not assume a CTE always runs remotely or is always materialized locally. Read the execution plan and measure actual behavior.

### 5.9. Functions and Expressions

A local function or an expression unsupported remotely can block pushdown. Timezone/collation conversions, user-defined functions, and casts require special attention. Expressions can be evaluated locally after fetching rows, but that increases network transfer.

### 5.10. EXPLAIN VERBOSE

Use:

~~~sql
EXPLAIN (VERBOSE, COSTS, SETTINGS)
SELECT order_id, status
FROM remote_crm.orders
WHERE customer_id = 1001
ORDER BY created_at DESC
LIMIT 50;
~~~

In a `postgres_fdw` plan, look for `Foreign Scan` and `Remote SQL`. Remote SQL shows which predicates/projections/orders/limits were sent to the remote server. `EXPLAIN` does not execute the query; add `ANALYZE` to measure runtime, keeping in mind that the query will actually execute.

### 5.11. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS, SETTINGS)
SELECT count(*)
FROM remote_crm.orders
WHERE created_at >= current_date - 30;
~~~

`BUFFERS` mainly describes local buffers; it does not replace remote server metrics. To understand remote cost, inspect the plan, logs, and statistics on the remote server as well.

### 5.12. Query Timeout

Local `statement_timeout` can cancel a query waiting on a remote operation. Also configure appropriate timeouts and network behavior on the client/remote side. Verify how the FDW propagates cancellation and remote query state in the version you are running.

## 6. Query Pushdown and Planner Costing

### 6.1. What Is Pushdown?

Pushdown is moving part of the query work from local PostgreSQL to the remote source. For example, filters, projections, sorts, limits, aggregates, or joins are evaluated where the data resides.

### 6.2. Why Does Pushdown Matter?

Suppose a remote table has 50 million rows, but a query only needs 200 rows. If the filter runs remotely, only 200 rows traverse the network. If the filter runs locally, millions of rows may have to be transferred before being discarded.

### 6.3. Non-Pushable Predicates

Common reasons include:

- Local functions/expressions without a remote equivalent;
- Different cast or operator semantics;
- Incompatible collations;
- Queries spanning multiple foreign servers;
- Join conditions that do not satisfy pushdown requirements;
- FDW version/implementation not yet supporting that clause;
- FDW options or planner costs causing a different plan to be chosen.

### 6.4. Remote Estimates

`postgres_fdw` has the `use_remote_estimate` option. When enabled, the planner can ask the remote server for estimates/costs instead of relying solely on local assumptions. This can improve plans for large remote tables, at the cost of additional round trips and planning overhead.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD use_remote_estimate 'true');
~~~

Or set it on a foreign table per supported options. Benchmark with it enabled and disabled to compare planning time, chosen plans, and execution time; remote estimates are not always better if network latency is high or remote statistics are stale.

### 6.5. fdw_startup_cost and fdw_tuple_cost

Costing options such as `fdw_startup_cost` and `fdw_tuple_cost` help the planner estimate the cost of connecting to and receiving rows from a foreign server. Values that are too low can cause the planner to choose remote paths too aggressively; values that are too high can cause it to avoid beneficial pushdowns.

~~~sql
ALTER SERVER crm_server
OPTIONS (
    ADD fdw_startup_cost '100',
    ADD fdw_tuple_cost '0.2'
);
~~~

These numbers are illustrative only. Measure latency, network throughput, and row width, and calibrate using real workloads.

### 6.6. fetch_size

`fetch_size` specifies how many rows `postgres_fdw` retrieves per fetch from a remote cursor. Larger values reduce round trips but use more memory/buffers; smaller values reduce memory per fetch but increase network overhead.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD fetch_size '10000');
~~~

You can set this option on a specific foreign table if needed. Choose based on row width, network latency, and concurrent query count.

### 6.7. batch_size for Writes

`batch_size` controls how many rows are sent in a single batch for certain remote INSERT paths. Larger values can reduce round trips, while increasing payload/memory usage and potentially affecting error handling. Depending on the version and DML pattern, this option may not apply to all writes.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD batch_size '1000');
~~~

### 6.8. async_capable

Some versions of `postgres_fdw` support asynchronous execution for eligible foreign scans. The `async_capable` option lets the planner consider this capability. Async execution does not magically make a single remote query faster; the main benefit comes from running independent foreign scans concurrently.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD async_capable 'true');
~~~

Verify your major version, query plans, and remote connection capacity before enabling it.

### 6.9. Parallel Execution

Parallel scan capability depends on the FDW, PostgreSQL version, query plan, and remote source. Do not assume a foreign table scan can use parallel workers. Check the plan and the specific wrapper's documentation.

### 6.10. Local Statistics

The planner needs estimates for foreign tables. You can run:

~~~sql
ANALYZE remote_crm.orders;
~~~

An FDW can provide a sampling/analysis method so local statistics reflect remote data. With `postgres_fdw`, ANALYZE on a foreign table reads samples from the remote server. Refresh frequency depends on the data change rate and query planning sensitivity.

### 6.11. Stale Statistics

When remote data changes, local foreign table statistics do not update instantaneously. If local estimates are stale, the planner may pick a poor join order or scan path. Schedule ANALYZE or use remote estimates where appropriate.

### 6.12. Planner Pushdown Does Not Replace Remote Indexing

A pushed-down predicate can still run slowly if the remote table lacks an index or has a poor remote plan. Check `EXPLAIN` on the remote database and optimize indexes/statistics where the data actually lives.

## 7. Writing Data Through Foreign Tables

### 7.1. Supported DML

`postgres_fdw` supports common write operations on foreign tables, including INSERT, UPDATE, and DELETE, when the remote server, user mapping, and permissions allow them. Exact capabilities vary across FDWs; some wrappers are read-only.

### 7.2. INSERT

~~~sql
INSERT INTO remote_crm.customers (customer_id, email, active)
VALUES (90001, 'new@example.com', true);
~~~

The command is sent to the remote database. Remote constraints, triggers, defaults, and permissions are enforced according to the remote table's semantics.

### 7.3. UPDATE

~~~sql
UPDATE remote_crm.customers
SET active = false
WHERE customer_id = 90001;
~~~

Filters can be pushed down so the remote server locates the rows to modify. Verify remote execution and affected row counts; avoid broad updates without verifying the predicate.

### 7.4. DELETE

~~~sql
DELETE FROM remote_crm.customers
WHERE customer_id = 90001;
~~~

A DELETE on a foreign table modifies remote data. Ensure appropriate remote permissions, an audit trail, and a confirmation process for destructive operations.

### 7.5. INSERT SELECT

~~~sql
INSERT INTO remote_crm.order_archive (order_id, customer_id, archived_at)
SELECT order_id, customer_id, now()
FROM public.orders
WHERE status = 'CLOSED'
  AND closed_at < current_date - interval '1 year';
~~~

Local PostgreSQL reads the local source and writes rows to the remote server. This can generate significant network transfer and WAL and is not automatically an optimal bulk load. Chunk into batches, control retries, and handle duplicate behavior.

### 7.6. Batch INSERT

`batch_size` is a `postgres_fdw` option for certain INSERT paths. It can group multiple rows into a remote statement to reduce network round trips. Verify version, plan, row size, and error behavior before configuring large batches.

### 7.7. UPDATE/DELETE Are Not Always Batched

Do not assume `batch_size` applies uniformly to UPDATE/DELETE. If you need to limit impact, split target rows by primary-key ranges or time windows and commit per batch.

### 7.8. RETURNING

Support for `RETURNING` and pushing expressions to the remote server depends on the wrapper and version. With `postgres_fdw`, check the current documentation and test the exact DML pattern; do not design pipelines around unverified assumptions.

### 7.9. Remote Triggers and Defaults

Remote triggers and defaults run on the remote database under its own semantics. Local PostgreSQL does not necessarily know all side effects produced by remote triggers; carefully design auditing, generated values, and application expectations.

### 7.10. Upsert

Do not assume every FDW supports `INSERT ... ON CONFLICT` the same way a local table does. Check the wrapper and PostgreSQL version before using it. If upsert is unsupported, design the operation on the remote server (such as a remote function/API) or build a pipeline with idempotency keys.

### 7.11. TRUNCATE

Do not assume a foreign table supports every table utility command like a local table. Check the FDW documentation; with `postgres_fdw`, supported DML commands differ from utility operations. Avoid using `TRUNCATE` on a foreign relation unless the wrapper explicitly documents support.

### 7.12. DML Privileges and Auditing

Local GRANT INSERT/UPDATE/DELETE only permits a user to operate on the local foreign table; the remote identity must still have privileges to execute DML. Audit both the local request and the remote actor to trace changes.

## 8. Transaction Semantics and Consistency

### 8.1. Local Transactions and Remote Transactions

When a local transaction accesses a foreign server via `postgres_fdw`, the wrapper opens/maintains a corresponding remote transaction. Multiple statements within the same local transaction can share the same remote transaction according to FDW behavior.

### 8.2. Commit and Rollback

Local COMMIT/ROLLBACK is forwarded to the remote transaction. If the local transaction rolls back, uncommitted remote changes are rolled back according to FDW behavior. However, a network error or remote crash at commit time creates an ambiguous outcome for the client; critical workflows require reconciliation and idempotency.

### 8.3. Multiple Foreign Servers

A single local transaction can access multiple foreign servers. You should not assume that remote commits and the local commit form a complete distributed atomic commit protocol across every failure scenario. `postgres_fdw` has its own transaction coordination and version-dependent behavior; consult the documentation before relying on atomicity across multiple systems.

### 8.4. Two-Phase Commit

Do not treat FDW as a replacement for XA/2PC or a distributed transaction coordinator. If business requirements demand atomic commits across multiple databases under all crash scenarios, design a dedicated transaction protocol, saga/outbox pattern, or an appropriate coordinator system.

### 8.5. Isolation Level

Local transaction isolation and remote transaction snapshots can have different semantics depending on the isolation level and FDW. `postgres_fdw` has documented behaviors and limitations regarding remote transaction isolation; check the documentation for your exact version to understand how snapshots and remote transactions are maintained.

### 8.6. Snapshot Consistency

A foreign table query reads a snapshot from the remote server. When querying multiple foreign servers, there is no automatic unified global snapshot across the entire system. Data across sources may reflect different points in time.

### 8.7. Long-Running Transactions

A local transaction left open while holding a remote transaction can hold remote snapshots/locks, consume connections, and interfere with vacuum on the remote PostgreSQL server. Commit or roll back promptly; never hold transactions open while waiting for user input or external APIs.

### 8.8. Savepoints

`postgres_fdw` supports savepoint/subtransaction mapping in documented scenarios. Even so, test rollback-to-savepoint, remote errors, and nested transaction behavior on your target version before using them in complex workflows.

### 8.9. Prepared Transactions

Do not assume a remote FDW transaction can be controlled like a local prepared transaction in all cases. If an application requires `PREPARE TRANSACTION`/2PC, explicitly verify wrapper and transaction coordinator support; do not leave prepared transactions lingering because they hold resources.

### 8.10. Retries and Exactly-Once

A network disconnect can leave the client unsure whether a remote statement committed. Exactly-once delivery is not provided automatically by an FDW. Use idempotency keys, unique constraints, durable job state, and reconciliation when retrying DML.

### 8.11. Remote Availability

If the remote database is unavailable, foreign table queries can fail or time out. Define the application fallback: fail closed, serve a cached/materialized copy, or return a degraded response. Never turn a remote failure into an empty result if it could be misinterpreted as missing data.

## 9. Type Mapping, Collation, and Schema Drift

### 9.1. Declaring Compatible Types

Foreign table column definitions must be compatible with the remote columns. With `postgres_fdw`, `IMPORT FOREIGN SCHEMA` helps fetch metadata, but after importing you should still verify type mapping, precision, and nullability.

### 9.2. Numeric Precision

Remote `numeric(p,s)` and local `numeric`/integer declarations must be compatible. Avoid declaring smaller local precision than the remote column if doing so could cause overflow or rounding.

### 9.3. Timestamp and Timezone

Distinguish between `timestamp without time zone` and `timestamp with time zone` (`timestamptz`). Different local/remote `TimeZone` settings can make output display differ even for the same instant. Use explicit timezone conversions when business semantics require them.

### 9.4. Text Encoding

Two PostgreSQL databases with different encodings may not be able to convert every character. Check server/database encodings and client encoding. Unrepresentable characters can cause errors during transfer.

### 9.5. Collation

String comparison and ordering can vary by collation and collation version. This affects pushdown safety, sorting, joins, and uniqueness. Do not assume local and remote text semantics are identical if collations differ.

### 9.6. Domains and Enums

Remote domains/enums can be represented according to the FDW's type mapping. Inspect catalog metadata, labels, and behavior when the remote side adds an enum value or changes domain constraints. The local schema does not automatically sync every remote change.

### 9.7. Arrays, Ranges, and Custom Types

Support for custom types, arrays, ranges, composites, and extension-defined types depends on the wrapper and version. Test import mapping and value round-trips. When uncertain, use an explicit scalar/text representation and a conversion layer.

### 9.8. Schema Drift

If a remote column is renamed, dropped, or has its type changed, the local foreign table may retain stale metadata, causing queries to fail or map incorrectly. Establish a schema change coordination process between the remote owner and the local owner.

### 9.9. Schema Import Does Not Auto-Refresh

`IMPORT FOREIGN SCHEMA` creates foreign table definitions at the time it runs. If the remote schema changes afterward, local foreign tables do not update automatically. Re-importing can conflict with existing objects; plan controlled alter/recreate migrations.

### 9.10. Schema Contract

Define a contract for the remote source: owner, schema version, backward compatibility window, deprecation notices, and change process. With multiple consumers, avoid abrupt column drops or renames.

## 10. Security and Access Management

### 10.1. Least Privilege on Both Sides

Create a dedicated remote role per integration with minimal privileges. For example, a reporting user only needs SELECT on specific tables/views; never use a remote superuser for a local application.

~~~sql
-- Run on the remote database with an appropriate administrative role
CREATE ROLE crm_fdw_reader LOGIN PASSWORD 'set-through-secret-management';
GRANT CONNECT ON DATABASE crm TO crm_fdw_reader;
GRANT USAGE ON SCHEMA public TO crm_fdw_reader;
GRANT SELECT ON public.customers, public.orders TO crm_fdw_reader;
~~~

This example illustrates the privilege structure only. Manage passwords via a secret manager and controlled provisioning; do not store real passwords in repositories or migration scripts.

### 10.2. Dedicated Local Roles

Create local roles for applications or analysts, granting privileges only on the required foreign schema and foreign tables. Do not grant CREATE on the integration schema to read-only users.

### 10.3. User Mapping Scope

A user mapping can be attached to a specific local role or to PUBLIC. Per-role mappings aid auditing and remote identity separation; PUBLIC mappings are simpler but widen access to use the mapping. Choose according to your threat model.

### 10.4. Credentials in the Catalog

User mapping options can contain credentials. Restrict administrative privileges on foreign servers/mappings, catalog read privileges, and privileges to create/alter user mappings. Avoid dumping catalog options into logs or tickets.

### 10.5. Network Security

Restrict firewall/security groups so only the local PostgreSQL host can connect to the required remote endpoint and port. Use private networks, VPNs, or peering where appropriate, and avoid exposing the remote database publicly.

### 10.6. TLS

For remote PostgreSQL, configure SSL/TLS using libpq parameters, such as an appropriate `sslmode` and CA verification. `verify-full` verifies both the certificate chain and hostname; the proper CA certificate must be installed on the database host. Never downgrade TLS verification just to make a connection work.

~~~sql
CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm',
    sslmode 'verify-full',
    sslrootcert '/etc/ssl/certs/company-ca.pem'
);
~~~

Connection options must be supported by your FDW/libpq version. Protect CA/key files and monitor hostnames and certificate rotation.

### 10.7. Application Identity and Auditing

Set `application_name` to identify the connection source on the remote server. Combine remote logs, `pg_stat_activity`, role identity, and local job/request IDs for tracing. Never log credentials or sensitive row values.

### 10.8. SQL Injection and Dynamic SQL

Foreign tables do not inherently create SQL injection vulnerabilities, but code that builds dynamic SQL/DDL for foreign servers, schema/table names, and options still carries risk. Use proper identifier quoting/parameterization APIs, allowlist object names, and never concatenate user input into connection options.

### 10.9. Server-Side File Access

With wrappers that read files on the database host, filesystem and server-program privileges can significantly expand risk. Allow only trusted roles, restrict paths, and never let arbitrary users execute programs through an FDW.

### 10.10. Secret Rotation

Establish a process to rotate remote passwords/certificates, update user mappings, and verify that new connections succeed. Some sessions cache remote connections; check how the FDW manages its connection cache and when connections are closed or re-established.

### 10.11. Drop and Revoke

When an integration is retired, revoke local grants, drop user mappings, foreign tables/servers, and the extension if no dependencies remain. Check object dependencies before running `DROP ... CASCADE`; avoid blind cascades that drop unrelated objects.

## 11. Connection Lifecycle and postgres_fdw Options

### 11.1. Connection Cache

`postgres_fdw` can keep a remote connection open in a local backend session for reuse across statements. This reduces connection setup cost, but the remote server may see many connections proportional to the number of local backend sessions and foreign servers used.

### 11.2. keep_connections

The server option `keep_connections` controls whether connections are retained for reuse; exact behavior and defaults depend on version. Closing connections can lower the remote connection count but increases authentication/connection overhead on subsequent queries. Check the documentation and benchmark your workload.

### 11.3. Remote Connection Capacity

Calculate the number of local application sessions, connection pool size, foreign servers, and remote connection limits. If many local backends query the remote server simultaneously, they can trigger a connection storm even when the local connection pool looks normal.

### 11.4. Connection Poolers

Combining an FDW with PgBouncer or a remote pooler requires understanding pooling modes and session features. `postgres_fdw` may rely on session-level state and transaction semantics; verify compatibility with transaction pooling and test prepared statements and session behavior.

### 11.5. connect_timeout

You can configure `connect_timeout` in server options when supported by libpq/FDW. Connect timeout differs from statement timeout; it limits how long establishing a connection can take, not remote query execution time.

### 11.6. application_name

Set application name per integration/service so remote DBAs can filter connections. Avoid dynamic values with excessively high cardinality if logging/monitoring indexes by that label.

### 11.7. Option Scope

Options can apply at the foreign-data wrapper, server, user mapping, or foreign table level depending on the wrapper and option. `ALTER SERVER`, `ALTER USER MAPPING`, and `ALTER FOREIGN TABLE` modify configuration; the validator rejects invalid options.

### 11.8. Changing Options

~~~sql
ALTER SERVER crm_server
OPTIONS (
    SET fetch_size '5000',
    SET use_remote_estimate 'true'
);
~~~

Option changes affect subsequent planning/connections according to each option's semantics. If a connection is already cached, verify whether you need to disconnect/reconnect or cycle sessions to pick up the new configuration.

### 11.9. Dropping Options

~~~sql
ALTER SERVER crm_server
OPTIONS (DROP use_remote_estimate);
~~~

Inspect current options before running DROP/SET to avoid unintentionally altering shared configuration.

### 11.10. Reading Options Safely

Catalog options can contain hostnames, usernames, or secrets. Display only what is needed for troubleshooting and redact sensitive values before posting output to tickets or chat.

## 12. Other FDWs and Data Sources

### 12.1. file_fdw

`file_fdw` is a PostgreSQL-provided extension for reading files on the database server's filesystem, typically text/CSV. It is suitable for lightweight staging/imports or querying structured files; it is not a general-purpose remote database connector.

~~~sql
CREATE EXTENSION IF NOT EXISTS file_fdw;

CREATE SERVER csv_files
FOREIGN DATA WRAPPER file_fdw;

CREATE FOREIGN TABLE staging_external_customers (
    customer_id bigint,
    email text,
    active boolean
)
SERVER csv_files
OPTIONS (
    filename '/srv/postgresql/import/customers.csv',
    format 'csv',
    header 'true'
);
~~~

The file path is read on the host running the PostgreSQL server, not on the psql client machine. The PostgreSQL OS user must have read permission on the file; database privileges to access server-side files are restricted via special roles/superuser policy.

### 12.2. file_fdw Security

Never allow untrusted users to choose arbitrary paths on the server. Grant least privilege, restrict directories, inspect symlinks/permissions, and never expose sensitive files. The `program` option can execute server-side programs and requires special privileges; use it only with reviewed, fixed commands and never concatenate user input.

### 12.3. A File-Backed Foreign Table Is Not a Data Copy

Reading CSV via a foreign table still depends on file existence, encoding, delimiter, header, and schema. If the file changes between queries, query results can also change. For pipelines requiring snapshot or transactional ingestion, load into a staging table, validate, and commit.

### 12.4. Community FDWs

Community wrappers exist for Oracle, MySQL, ODBC, MongoDB, Redis, HTTP/API, S3, and many other sources. Package names, licenses, support matrices, write capabilities, and maintenance quality vary. Evaluate project activity, security advisories, PostgreSQL major version compatibility, and SLAs before production use.

### 12.5. Read-Only vs. Read-Write Wrappers

Some wrappers only support SELECT; some support INSERT/UPDATE/DELETE; some have limited pushdown or transaction support. Do not assume features of `postgres_fdw` apply to other wrappers. Read the documentation, README, and release notes for the exact extension.

### 12.6. ODBC/JDBC

ODBC/JDBC are driver interfaces; they are not FDWs on their own. You need a wrapper that integrates the corresponding driver and must configure client libraries on the server host. Manage driver versions, DSNs, TLS, credentials, and type mappings.

### 12.7. REST/API Wrappers

APIs commonly involve pagination, rate limits, retries, expiring authentication, and evolving response schemas. An FDW may be a poor fit for query patterns requiring arbitrary joins or transactions across an API. Consider ingesting/caching data into local tables to control reliability.

### 12.8. Choosing a Wrapper

Evaluate:

- PostgreSQL major version compatibility;
- Source protocol/driver version;
- Read/write support;
- Predicate/join/aggregate pushdown;
- Transaction semantics;
- Type mapping;
- TLS/authentication;
- Parallel/async capabilities;
- Maintenance and community support;
- Observability and error handling.

## 13. Performance and Workload Design

### 13.1. Network Latency Is Part of Query Cost

Foreign scans incur network round trips, connection setup, serialization, and remote execution costs. A query that takes a few milliseconds locally can take hundreds of milliseconds when the remote database is in another region.

### 13.2. Reduce Rows and Columns Before Transfer

Prefer pushable predicates and select lists, and avoid pulling an entire remote table only to filter locally. Do not use `SELECT *` when only a few columns are needed.

### 13.3. Join Location

If joining two foreign tables on the same server can be pushed down, letting the remote database perform the join usually saves transfer. When joining a foreign table with a large local table, check the plan and consider staging/materialization if remote transfer is excessive.

### 13.4. Choosing fetch_size

Measure row width and latency. Larger fetch sizes help over high-latency networks but increase memory usage. Test several values under concurrent workloads; do not tune based on a single isolated query.

### 13.5. Choosing batch_size

For bulk inserts via `postgres_fdw`, larger batch sizes can reduce round trips. However, you must balance remote statement size, memory, transaction duration, WAL generation, and error recovery.

### 13.6. Remote Indexes

Optimize indexes on the remote source for pushed predicates, join keys, and ordering. A local foreign table has no local index storing rows like an ordinary table; indexes must live where the data actually resides.

### 13.7. ANALYZE Local Foreign Tables

Local statistics help the planner choose join orders and estimate cardinality. Run ANALYZE after major remote data changes or on a schedule; measure the cost of sampling over the network.

### 13.8. use_remote_estimate

Enable remote estimates when local stats are insufficient or remote data distributions shift rapidly; disable it if planning round trips add too much latency and local stats are adequate. Compare both planning time and execution time.

### 13.9. Materialized Views as a Cache

If the remote source does not need to be read in real time, you can materialize the results:

~~~sql
CREATE MATERIALIZED VIEW reporting.customer_summary AS
SELECT
    customer_id,
    count(*) AS order_count,
    sum(total_amount) AS lifetime_value
FROM remote_crm.orders
GROUP BY customer_id;
~~~

Refresh:

~~~sql
REFRESH MATERIALIZED VIEW reporting.customer_summary;
~~~

A materialized view stores a local copy; data can be stale until the next refresh. Concurrent refresh requires an appropriate unique index and has its own operational constraints. Define a refresh schedule, freshness SLA, and handling for remote outages.

### 13.10. Staging Tables

For ETL, load remote data into local staging tables in batches, then validate, transform, and merge. Staging decouples application queries from network dependencies, enforces data quality controls, and preserves historical snapshots.

### 13.11. Caching and Freshness

Define freshness requirements: real-time, a few minutes, hourly, or daily. Do not put an FDW directly on a critical request path if remote latency/availability cannot meet the SLO and there is no fallback.

### 13.12. N+1 Remote Queries

Avoid application loops that run one foreign query per local row. Batch keys into a single pushable query/join, or batch-fetch. Many small repeated round trips can be far more expensive than a single larger query.

### 13.13. Network Payload

Large text, JSON, bytea, or wide rows increase serialization and transfer overhead. Select only needed columns, limit rows, and avoid pulling blobs over an FDW unnecessarily.

### 13.14. Remote Workload Isolation

Foreign queries consume resources on the remote production database. Use a read replica or reporting endpoint when appropriate, along with a remote role that has resource controls and rate limits. Keep in mind that replica lag can make data slightly stale.

### 13.15. Connection Contention

Connection caching reduces setup overhead, yet many local backends can open many remote sessions. Cap local pool limits, monitor remote `max_connections`, and consider a dedicated integration role and `application_name`.

### 13.16. Do Not Use FDW as a Substitute for Query Design

A foreign query is not automatically optimal just because the SQL syntax is concise. Understand data volume, filter selectivity, remote plans, transfer size, and join location. If queries frequently scan most of a remote dataset, ingestion or replication may be a better fit.

## 14. Observability and Troubleshooting

### 14.1. Observing Local Foreign Scans

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS, SETTINGS)
SELECT customer_id, email
FROM remote_crm.customers
WHERE active;
~~~

Record planning time, execution time, actual rows, loops, and `Remote SQL`. Compare against running the query directly on the remote server to separate network/FDW overhead from remote execution cost.

### 14.2. Observing Remote Sessions

On the remote PostgreSQL server:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS query_age,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE application_name = 'local-fdw-crm'
ORDER BY query_start;
~~~

The `application_name` filter is only effective if configured and accepted by the remote server.

### 14.3. Remote Logs

Configure remote logging per policy to capture durations/errors and identify FDW workloads. Consider `log_min_duration_statement` or log sampling while avoiding excessive logging of sensitive query literals.

### 14.4. Statistics Resets

Remote/local statistics counters can reset after restarts or manual reset commands. Store reset timestamps alongside snapshots so small counter values are not misinterpreted as fresh workloads.

### 14.5. Connection Refused/Timeout Errors

Check:

1. DNS/host/port;
2. Firewall/security groups/routing;
3. Remote PostgreSQL listen addresses;
4. `pg_hba.conf`/authentication rules;
5. TLS mode/certificates;
6. Remote connection limits;
7. `connect_timeout` and network health.

### 14.6. Password Authentication Errors

Check the local user mapping, remote username/password, password rotation status, remote role login status, and authentication method. Never print passwords to logs while debugging.

### 14.7. Permission Denied

Distinguish local USAGE/SELECT errors on the foreign server/table from remote CONNECT/USAGE/SELECT errors on the remote object. Identify which remote identity the user mapping selects.

### 14.8. Relation/Column Does Not Exist

Check local foreign table options, remote schema/table names, case-sensitive quoted identifiers, and schema drift. Schema imports do not auto-update when remote DDL changes.

### 14.9. Type Conversion Errors

Check local foreign table column types, remote column types, precision, encoding, timezones, and custom types. Do not arbitrarily change local types without checking against the remote schema contract.

### 14.10. Query Is Slow Despite Having a Filter in SQL

Use EXPLAIN VERBOSE to confirm the filter appears in Remote SQL. If not, check whether an expression, cast, or collation prevents pushdown. If it is present, inspect the remote plan, indexes, statistics, and network latency.

### 14.11. Too Many Rows Fetched

Check projection, filters, LIMIT, join/aggregate pushdown, and row estimates. Optimize the remote query or materialize data if the workload requires repeated local joins.

### 14.12. Deadlocks and Lock Waits

Foreign DML can lock rows remotely while a local transaction simultaneously locks local rows. Inspect deadlock logs on both local and remote servers, keep transactions short, and enforce consistent lock ordering in application code.

### 14.13. Remote Transaction Left Open

Check local backend state/transaction age and remote `pg_stat_activity`. A local idle-in-transaction session can keep a remote transaction and connection open. Close transactions promptly and fix connection pool/session leaks.

### 14.14. Remote Server Restarts

A remote restart invalidates cached connections. The next query may error and require a retry once the connection is re-established. Applications must handle transient errors according to an idempotency policy.

### 14.15. FDW Errors in Logs

Enable enough logging to identify the server, local role, remote identity (without exposing secrets), query duration, and SQLSTATE. Redact credentials and sensitive data before sharing logs.

## 15. When Should You Use an FDW?

### 15.1. When FDW Is a Good Fit

An FDW is usually appropriate when:

- You need selective lookups or joins against external data;
- You want query federation without copying the entire source;
- The remote source has a clear owner and meets availability requirements;
- The workload pushes down well;
- Latency and network costs are acceptable;
- Transaction semantics and the security model are well understood.

### 15.2. When to Consider Replication

Replication is a better fit when you need high read throughput, local availability during remote source outages, or local data locality to cut network latency. You must be willing to accept replication lag, storage overhead, and operational complexity.

### 15.3. When to Use ETL/ELT

ETL/ELT is appropriate when you need historical snapshots, multi-step transformations, data quality checks, retry/reconciliation, and analytics over large datasets. It also isolates production sources from reporting workloads.

### 15.4. When to Use a Materialized View

A materialized view fits when the remote query is expensive but data can be stale for a bounded interval. You need a freshness SLA, refresh schedule, a unique index for concurrent refresh if required, and a procedure for remote unavailability.

### 15.5. When to Call an API Directly

An API is appropriate when the source enforces business operations, authorization, or rate limits through a service contract. An FDW does not replace the service layer or API-level business validation.

### 15.6. Decision Matrix

| Need | Typical Best Fit | Key Decision Question |
| --- | --- | --- |
| Lookup a few rows at query time | FDW | Does remote latency meet the SLO? |
| Join tables on the same remote PostgreSQL | postgres_fdw | Do joins and filters push down? |
| CSV file on the database host | file_fdw or staging load | Is file access secure and stable? |
| Local read scaling | Replication | Are lag and copy storage acceptable? |
| Large history/analytics | ETL/ELT | Are snapshots and transformations needed? |
| Scheduled query cache | Materialized view | What is the acceptable freshness interval? |
| Business operation via service | API/service integration | Are service authorization/rules required? |

### 15.7. Hybrid Architecture

A single system may use an FDW for small lookups, CDC/replication for operational read models, and ETL for analytics. You do not have to force one technology onto every data integration problem.

## 16. End-to-End Example: Integrating a PostgreSQL CRM

Scenario: the local `appdb` database needs to read customers/orders from the remote `crm` database. The application only needs read access to CRM data to display customer profiles and order history.

### 16.1. Remote Prerequisites

The remote DBA creates a read-only role and grants privileges:

~~~sql
CREATE ROLE crm_fdw_reader LOGIN;
GRANT CONNECT ON DATABASE crm TO crm_fdw_reader;
GRANT USAGE ON SCHEMA public TO crm_fdw_reader;
GRANT SELECT ON public.customers, public.orders TO crm_fdw_reader;
~~~

Provision credentials via a secret manager; configure the network allowlist and TLS.

### 16.2. Local Extension and Server

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm',
    application_name 'appdb-fdw-crm',
    sslmode 'verify-full',
    sslrootcert '/etc/ssl/certs/company-ca.pem'
);
~~~

### 16.3. User Mapping and Schema

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER crm_server
OPTIONS (
    user 'crm_fdw_reader',
    password 'managed-outside-source-control'
);

CREATE SCHEMA remote_crm;
GRANT USAGE ON FOREIGN SERVER crm_server TO app_reader;
GRANT USAGE ON SCHEMA remote_crm TO app_reader;
~~~

### 16.4. Import Selected Tables

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders)
FROM SERVER crm_server
INTO remote_crm;

GRANT SELECT ON ALL TABLES IN SCHEMA remote_crm TO app_reader;
~~~

### 16.5. Profile Query

~~~sql
SELECT
    c.customer_id,
    c.email,
    o.order_id,
    o.created_at,
    o.total_amount
FROM remote_crm.customers AS c
JOIN remote_crm.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 90001
ORDER BY o.created_at DESC
LIMIT 20;
~~~

Because both foreign tables belong to the same server, `postgres_fdw` can push down the join, order, and limit if conditions are compatible. Use `EXPLAIN VERBOSE` to confirm the remote SQL.

### 16.6. ANALYZE and Plan

~~~sql
ANALYZE remote_crm.customers;
ANALYZE remote_crm.orders;

EXPLAIN (VERBOSE, COSTS)
SELECT customer_id, email
FROM remote_crm.customers
WHERE customer_id = 90001;
~~~

Compare the local plan with the remote plan, check indexes on the remote primary key/`customer_id`, and measure actual latency.

### 16.7. Application Grants

~~~sql
GRANT SELECT ON remote_crm.customers, remote_crm.orders TO app_reader;
~~~

Do not grant DML if the application is read-only. The remote role likewise remains SELECT-only.

### 16.8. Verify and Operationalize

- Verify TLS connection and authentication;
- Verify local and remote privileges;
- Inspect Remote SQL and query plans;
- Measure p95 latency and bytes transferred;
- Monitor remote connection counts;
- Test behavior when CRM is unavailable;
- Set alerts for connection failures/timeouts;
- Document schema owners and change notification procedures.

## 17. Operating Foreign Data Integration

### 17.1. Before Going to Production

1. Identify the remote source owner and SLA;
2. Verify PostgreSQL/FDW versions and supported options;
3. Design local/remote roles and user mappings;
4. Set up TLS, firewall rules, and secrets;
5. Selectively import/define foreign tables;
6. Test query pushdown with EXPLAIN VERBOSE;
7. Measure latency, throughput, and remote connection load;
8. Test remote outage, timeout, retry, and cancellation handling;
9. Define consistency/freshness semantics;
10. Write runbooks and define alert ownership.

### 17.2. Daily Checks

- Remote endpoint reachability;
- Authentication errors;
- Query latency/timeouts;
- Remote connection counts;
- Remote server CPU/I/O/load;
- Local application error rates;
- Remote schema change notifications.

### 17.3. Weekly Checks

- Slow foreign queries and top Remote SQL patterns;
- Age of local foreign table statistics;
- Remote indexes/statistics for pushed predicates;
- Connection pool usage and remote `max_connections`;
- Network throughput/errors;
- Credential and certificate expiration dates.

### 17.4. Schema Change Coordination

The remote owner notifies consumers before renaming, dropping, or changing column types. The local owner checks dependencies, tests in staging, and updates foreign table metadata/application code in a compatible rollout. Never automatically re-import schemas and overwrite local definitions in production.

### 17.5. Credential Rotation

Rotate remote credentials following a structured procedure:

1. Create/rotate the remote credential;
2. Update the secret manager;
3. Update the user mapping;
4. Verify a new connection succeeds;
5. Close/recycle cached sessions per guidelines;
6. Revoke the old credential;
7. Record an audit event.

### 17.6. Remote Outage Runbook

When the remote source is down:

- Identify the scope of affected queries and services;
- Check network, authentication, and remote health;
- Pause jobs that aggressively retry;
- Serve from cache/materialized view if business policy permits;
- Never return fake empty rows as valid data;
- Monitor remote recovery and connection re-establishment;
- Reconcile writes/outcomes if DML disconnected during commit.

### 17.7. Retiring an Integration

Before removing an integration, search for dependencies in views, functions, jobs, and applications. Revoke application grants, remove mappings and foreign tables/servers in dependency order, then drop the extension if no longer used. Retain audit/config metadata needed for history.

### 17.8. Change Management

Every change to remote server options, user mappings, FDW extension versions, TLS settings, or fetch/batch tuning needs an owner, change record, validation, and rollback plan. Never change shared server options during peak hours without knowing all consumers.

## 18. Limitations and Trade-Offs to Remember

### 18.1. FDW Does Not Turn Remote Data into Local Data

A foreign table is a metadata mapping; each query may still incur remote connections, execution, and network transfer. Do not judge performance merely because the SQL syntax looks like a local table.

### 18.2. Remote Availability Is a Dependency

A remote source outage can cause local queries to fail. If an endpoint sits on a critical request path, add a fallback/cache/replica or adjust the architecture.

### 18.3. No Default Global Snapshot

Multiple remote systems can return data from different points in time. Do not assume a federated query reflects a global transactional snapshot.

### 18.4. Limited Distributed Atomicity

A single local transaction accessing multiple remote servers does not automatically guarantee atomic commit across all systems in every crash scenario. Design idempotency, outbox/saga patterns, or a coordinator when required.

### 18.5. Pushdown Depends on the Wrapper

Not every filter, join, aggregate, sort, LIMIT, or DML statement is pushed down. A community wrapper may support only a small subset of SQL.

### 18.6. Type Mapping Can Lose Information

Numeric precision, timestamp timezones, text encodings, collations, and custom types must be verified. A foreign table definition does not automatically guarantee lossless round-trips.

### 18.7. Statistics Can Go Stale

Local planner statistics do not automatically reflect every remote change. Run ANALYZE or use remote estimates depending on the workload.

### 18.8. Schema Drift Does Not Sync Automatically

Remote DDL does not automatically update local foreign table definitions. This can cause query errors after renames, drops, or type changes.

### 18.9. Credentials and Connection Counts

User mappings can store secrets; local backend sessions can open remote connections. Enforce least privilege, secret rotation, and capacity planning.

### 18.10. FDW Does Not Replace ETL/CDC for All Use Cases

Historical snapshots, large-scale transformations, replay, lineage, data quality checks, and heavy analytics usually require dedicated pipelines or materialized data.

### 18.11. Resource Isolation

Local queries can overload a remote database. Limit concurrency, target a read replica where appropriate, and monitor remote resource consumption.

### 18.12. Extension Maintenance

Community FDWs require tracking releases, security patches, and compatibility. PostgreSQL major upgrades may require rebuilding extensions or migrating configuration.

## 19. Hands-On Lab

The steps below use two PostgreSQL databases that can connect to each other. Use lab credentials; never open networks or grant broad privileges in production.

### 19.1. Preparing the Remote Database

On the remote database, create sample data:

~~~sql
CREATE TABLE public.lab_customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE public.lab_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.lab_customers (customer_id, email)
VALUES
    (1, 'one@example.test'),
    (2, 'two@example.test'),
    (3, 'three@example.test');

INSERT INTO public.lab_orders (order_id, customer_id, total_amount)
VALUES
    (101, 1, 120.00),
    (102, 1, 80.00),
    (103, 2, 250.00);
~~~

Create a read-only remote role and grant privileges on both tables.

### 19.2. Local Configuration

On the local database:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER lab_remote
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host '127.0.0.1',
    port '5433',
    dbname 'remote_lab'
);

CREATE USER MAPPING FOR CURRENT_USER
SERVER lab_remote
OPTIONS (
    user 'lab_reader',
    password 'lab-only-secret'
);

CREATE SCHEMA lab_remote;
~~~

Adjust host/port/database/credentials to match your actual lab. Never use example passwords in any shared environment.

### 19.3. Import the Schema

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (lab_customers, lab_orders)
FROM SERVER lab_remote
INTO lab_remote;
~~~

### 19.4. Query Foreign Tables

~~~sql
SELECT *
FROM lab_remote.lab_customers;

SELECT
    c.email,
    count(o.order_id) AS order_count,
    coalesce(sum(o.total_amount), 0) AS total_spent
FROM lab_remote.lab_customers AS c
LEFT JOIN lab_remote.lab_orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email
ORDER BY total_spent DESC;
~~~

### 19.5. Observe Pushdown

~~~sql
EXPLAIN (VERBOSE, COSTS)
SELECT order_id, total_amount
FROM lab_remote.lab_orders
WHERE customer_id = 1
ORDER BY created_at DESC
LIMIT 10;
~~~

Look for Remote SQL and confirm whether the filter, order, and limit are pushed down when supported by the plan.

### 19.6. Test DML

Run only if the lab remote role has been granted write privileges:

~~~sql
INSERT INTO lab_remote.lab_customers (customer_id, email, active)
VALUES (4, 'four@example.test', true);

UPDATE lab_remote.lab_customers
SET active = false
WHERE customer_id = 4;

DELETE FROM lab_remote.lab_customers
WHERE customer_id = 4;
~~~

Inspect the remote data after each operation and test transaction rollback.

### 19.7. Test fetch_size

Configure different fetch sizes on the foreign server/table in the lab, run the same query returning many rows, and measure execution time and memory. Only compare under equivalent dataset, network, and cache conditions.

### 19.8. Simulate a Remote Outage

Temporarily stop the remote service in the lab, run a foreign query, and observe the error/timeout. Start it again and confirm connections re-establish and queries succeed.

### 19.9. Simulate Schema Drift

Rename or alter a remote column in the lab. Query the local foreign table to observe the behavior; update the local definition/import following a change process.

### 19.10. Cleanup

~~~sql
DROP SCHEMA lab_remote CASCADE;
DROP USER MAPPING FOR CURRENT_USER SERVER lab_remote;
DROP SERVER lab_remote;
DROP EXTENSION postgres_fdw;
~~~

Only drop the extension if no other FDW objects or dependencies remain in the lab database.

## 20. Practice Exercises: Foreign Data Wrapper

Perform these on lab/staging. For questions that depend on a wrapper or PostgreSQL major version, verify the corresponding documentation before drawing conclusions.

### Exercise 1 — FDW Concept

Explain what a Foreign Data Wrapper is and the role of a foreign table. State the differences between a foreign table and a local table.

### Exercise 2 — FDW vs. Replication

Compare FDW with logical replication in terms of freshness, availability, storage, latency, and use cases.

### Exercise 3 — FDW vs. ETL

A report needs multi-year historical data and multi-step transformations. Explain why ETL/ELT may be more suitable than querying an FDW directly.

### Exercise 4 — Architecture

Diagram the flow across the parser/planner, FDW callbacks, remote source, and local executor. Identify which filters might run locally vs. remotely.

### Exercise 5 — Foreign Server

Write a CREATE SERVER statement for a remote PostgreSQL instance with host, port, and dbname.

### Exercise 6 — User Mapping

Write a CREATE USER MAPPING statement for a local role. Explain why credentials should not be stored in source control.

### Exercise 7 — Privileges

List the local and remote privileges required for a user to have read-only access to a foreign table.

### Exercise 8 — Import Schema

Write an IMPORT FOREIGN SCHEMA statement that imports only two tables, plus an example using EXCEPT.

### Exercise 9 — Manual Foreign Table

Write a CREATE FOREIGN TABLE statement for remote customers with `schema_name`/`table_name` options.

### Exercise 10 — Basic Query

Write a SELECT on a foreign table with WHERE, ORDER BY, and LIMIT. Explain why EXPLAIN is needed to confirm pushdown.

### Exercise 11 — Local/Foreign Join

Join a local orders table with foreign customers. State the risk if the foreign table has many rows and the join is not pushed down.

### Exercise 12 — Remote Join

Write a query joining two foreign tables on the same server. Identify the Remote SQL in EXPLAIN VERBOSE.

### Exercise 13 — Aggregate Pushdown

Write a GROUP BY count/sum query on foreign orders. List factors that can prevent aggregate pushdown.

### Exercise 14 — Projection Pushdown

A remote table has 80 columns and several large JSON payloads. Write a query selecting only three required columns and explain the benefit.

### Exercise 15 — Remote Estimates

Enable `use_remote_estimate` and explain the trade-off between estimate quality and planning round trips.

### Exercise 16 — fetch_size

Explain `fetch_size`. Design a test comparing three values and measuring throughput and memory.

### Exercise 17 — batch_size

Explain `batch_size` in `postgres_fdw` and why you should not assume this option applies identically to all DML operations.

### Exercise 18 — INSERT/UPDATE/DELETE

Write three DML statements against a foreign table and list the required local and remote privileges.

### Exercise 19 — Transaction

A local transaction writes to a foreign table and then rolls back. Describe the expected behavior and explain a network failure scenario during commit that leaves the outcome unclear.

### Exercise 20 — Multiple Foreign Servers

A transaction writes to two remote PostgreSQL servers. Explain why a global atomic commit cannot be assumed across all failure scenarios.

### Exercise 21 — Type Mapping

Compare `timestamp without time zone` and `timestamptz`. Explain how timezone settings can cause displayed output to differ.

### Exercise 22 — Schema Drift

A remote DBA renames a column. Does the local foreign table update automatically? Design a schema-change coordination workflow.

### Exercise 23 — Security

Design a least-privilege remote role, local role, user mapping, TLS configuration, and firewall policy for a reporting integration.

### Exercise 24 — Connection Capacity

Local PostgreSQL has 300 backend sessions and each session queries three foreign servers. Explain how to estimate remote connection pressure and list mitigation measures.

### Exercise 25 — file_fdw

Write a foreign table reading a CSV via `file_fdw`. Which host is the file read from, and what permission controls are needed?

### Exercise 26 — Query Performance

A query pulls 5 million remote rows to the local server and filters down to 100 rows. Propose how to diagnose and improve pushdown.

### Exercise 27 — Remote Outage

Design a fallback when the CRM database is unavailable for a customer profile API. Why should you not return an empty result as if the customer did not exist?

### Exercise 28 — Materialized View

Create a materialized view from foreign orders to cache a daily summary. Define the freshness SLA and refresh strategy.

### Exercise 29 — Observability

Write a query against remote `pg_stat_activity` filtering by the FDW `application_name`. List the local and remote metrics needed on a dashboard.

### Exercise 30 — Capstone: Federated Customer Data

A PostgreSQL application needs to combine local orders, remote CRM customers, remote billing invoices, and a CSV file containing country mappings. Remote CRM and Billing belong to two different teams; CRM has 20 million customers and Billing has 200 million invoices. The profile API requires a p95 under 250 ms, remote billing may experience brief outages, and the reporting team needs monthly historical data.

**Requirements:**

1. Choose FDW, replication, ETL, or materialization for each source and justify your choice.
2. Design foreign servers, user mappings, roles, and TLS/firewall policies.
3. Select specific tables/columns to import rather than importing entire schemas indiscriminately.
4. Write the customer profile query and verify query pushdown.
5. Design local/foreign joins to minimize rows/bytes transferred.
6. Benchmark and select `fetch_size`, remote estimates, and connection pool limits.
7. Design a cache/materialized view or degraded response for remote outages.
8. Define transaction/idempotency policies for any DML operations.
9. Design a schema-change contract across teams.
10. Build a dashboard tracking remote latency, connections, failures, query duration, and freshness.
11. Design ETL/staging for historical reporting, retention, and data quality.
12. Write runbooks for credential rotation, schema drift, network outages, and remote overload.

**Passing criteria:** the architecture meets latency/freshness targets, bounds load on remote systems, does not rely on a global transaction snapshot, protects credentials, and establishes clear fallback and operational ownership.

## 21. Frequently Asked Questions

### 21.1. Does a foreign table store data locally?

Usually no. A foreign table stores metadata/mapping; data is read from the external source when a query runs. To maintain a local copy, use a local table, staging table, materialized view, or replication.

### 21.2. Is an FDW an extension?

FDW is an extensibility mechanism in PostgreSQL. Wrappers like `postgres_fdw` and `file_fdw` are provided as extensions and must be installed/enabled per environment.

### 21.3. Does postgres_fdw stay continuously connected to the remote server?

Not necessarily. It typically opens connections on demand and can cache/reuse a connection within a local backend session depending on options and version.

### 21.4. Does IMPORT FOREIGN SCHEMA copy rows?

No. It creates foreign table definitions from remote metadata; the data remains on the remote source.

### 21.5. Can foreign tables be created manually?

Yes. Use CREATE FOREIGN TABLE with column definitions, a foreign server, and options mapping to the remote schema/table.

### 21.6. Can a foreign table be JOINed with a local table?

Yes. The planner can join local and foreign data, though if the join is not pushed down, many remote rows may be transferred locally. Check EXPLAIN VERBOSE.

### 21.7. Are WHERE filters always pushed down?

No. An FDW only pushes down safe and supported expressions. Functions, casts, collations, or operator semantics can force a filter to run locally.

### 21.8. How do I verify whether pushdown is working?

Run EXPLAIN VERBOSE and inspect Foreign Scan and Remote SQL. Use EXPLAIN ANALYZE to measure actual runtime and remote monitoring to observe the remote query.

### 21.9. Is use_remote_estimate always better?

No. It can improve cardinality and cost estimates, but it adds remote planning round trips. Benchmark against local statistics using real workloads.

### 21.10. Is a larger fetch_size always faster?

No. It reduces round trips but increases memory/buffer consumption and payload size. Choose by benchmarking according to row width, latency, and concurrency.

### 21.11. Does batch_size apply to UPDATE and DELETE?

Do not assume it does. In `postgres_fdw`, this option primarily relates to batch INSERT paths; check the documentation for your version and batch UPDATE/DELETE manually if needed.

### 21.12. Can you INSERT/UPDATE/DELETE on a foreign table?

Yes with `postgres_fdw` under supported conditions and when the remote user holds the required privileges. Other FDWs may be read-only.

### 21.13. Is a local GRANT SELECT sufficient?

No. The local user needs privileges on the foreign server, schema, and table plus a user mapping; the remote identity needs CONNECT/USAGE/SELECT on the remote database, schema, and table.

### 21.14. Is a PUBLIC user mapping safe?

It extends the mapping to all local users permitted to use the server. Prefer per-role mappings when identity separation and auditing are required.

### 21.15. Where are user mapping passwords stored?

User mapping options are stored in the system catalog; read access can be restricted, but credentials remain sensitive data. Manage catalog privileges, secret rotation, and logs carefully.

### 21.16. Does FDW support TLS?

With `postgres_fdw`, you can use libpq SSL/TLS connection options such as `sslmode` and a CA certificate. Verify version support and use hostname verification.

### 21.17. Is a transaction writing to two remote servers atomic?

Do not assume a global atomic commit across all failure scenarios. Use idempotency, outbox/saga patterns, or a distributed transaction coordinator if stronger business guarantees are needed.

### 21.18. What happens if the remote database goes down?

Foreign queries can fail or time out. Applications need fallback, caching, degraded behavior, or fail-closed handling depending on business requirements. Never convert a remote failure into a fake empty result.

### 21.19. What does ANALYZE on a foreign table do?

It updates local planner statistics using sampling/analysis supported by the FDW. This helps the local planner estimate row counts and select better join paths.

### 21.20. If the remote schema changes, does the local foreign table update automatically?

No. Local metadata can become stale. A schema-change contract and controlled local migrations are required.

### 21.21. Can file_fdw read a file from my laptop?

Not directly. `file_fdw` reads files on the host running the PostgreSQL server. Client files must be uploaded/staged on the server or imported using a client-side workflow.

### 21.22. Does file_fdw write CSV files?

`file_fdw` is primarily for reading files; do not assume DML support. Use COPY, ETL/staging, or another wrapper for writes.

### 21.23. Does an FDW replace an API?

No. An API enforces business logic, authorization, and service contracts. An FDW is for accessing a data source; it does not replace a service layer.

### 21.24. Is an FDW suitable for large analytics?

It can work for selective queries and federation, but large scans are often constrained by network bandwidth and remote workload impact. ETL/ELT, replication, or local materialization are usually better for heavy or repeated analytics.

### 21.25. When should you choose a materialized view?

When remote data can be stale for a bounded window and fast, predictable local queries are needed. Define a refresh schedule, freshness SLA, and handling for refresh failures.

### 21.26. Does an FDW automatically sync data between two databases?

No. An FDW allows querying/writing remotely per query. Replication, CDC, or ETL are the mechanisms for continuous or scheduled synchronization.

### 21.27. Can PgBouncer be used with postgres_fdw?

Test carefully according to pooling mode, connection/session semantics, and transaction behavior. Do not assume transaction pooling is compatible with every FDW usage pattern.

### 21.28. How do you limit remote load?

Cap local concurrency/pools, use dedicated roles or replicas, push down filters and projections, tune fetch/batch sizes, enforce rate limits, and monitor remote resource consumption.

### 21.29. Is there a single FDW that supports every database?

No. Each wrapper supports one or a group of sources, with its own feature set, version compatibility, and dependencies. Choose and evaluate each wrapper individually.

### 21.30. What is the pre-production checklist?

Verify versions/support, source owner/SLA, least privilege, TLS/networking, schema contracts, pushdown plans, latency/connection capacity, transaction/fallback semantics, monitoring, and runbooks.

## 22. Official Reference Documentation

Choose the documentation matching the PostgreSQL major version you run; options, pushdown capabilities, and transaction behavior can change:

- [Foreign Data Wrappers](https://www.postgresql.org/docs/current/ddl-foreign-data.html): concepts of foreign tables, wrappers, and server mappings.
- [CREATE FOREIGN DATA WRAPPER](https://www.postgresql.org/docs/current/sql-createforeigndatawrapper.html): registering an FDW.
- [CREATE SERVER](https://www.postgresql.org/docs/current/sql-createserver.html): declaring a foreign server.
- [CREATE USER MAPPING](https://www.postgresql.org/docs/current/sql-createusermapping.html): mapping local users to remote identities.
- [CREATE FOREIGN TABLE](https://www.postgresql.org/docs/current/sql-createforeigntable.html): declaring a foreign table.
- [IMPORT FOREIGN SCHEMA](https://www.postgresql.org/docs/current/sql-importforeignschema.html): importing remote schema metadata.
- [postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html): configuration, options, pushdown, DML, and transaction behavior.
- [file_fdw](https://www.postgresql.org/docs/current/file-fdw.html): reading CSV/text files from the server filesystem.
- [Foreign Data Wrapper Functions](https://www.postgresql.org/docs/current/fdwhandler.html): FDW handler APIs and callbacks for extension authors.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): reading execution plans and remote SQL.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity, locks, and statistics.
- [libpq Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html): connection parameters, TLS, and service files.
- [Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html): storing query results locally and refreshing them.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): an alternative when local copies are required.

## 23. Summary

Foreign Data Wrappers allow PostgreSQL to access external data through foreign tables while keeping familiar SQL syntax. With `postgres_fdw`, a local database can connect to a remote PostgreSQL server, import schemas, query/join tables, and perform certain DML operations. Query pushdown reduces data transferred over the network; EXPLAIN VERBOSE shows what SQL is sent remotely.

| Component | Role |
| --- | --- |
| FDW | Adapter communicating with the data source |
| Foreign server | External endpoint/source configuration |
| User mapping | Remote identity/credentials for a local user |
| Foreign table | Local metadata mapping to a remote relation |
| Pushdown | Runs filters/joins/aggregates/sorts remotely when supported |
| ANALYZE | Updates local planner statistics |
| Connection options | Tunes estimates, fetch, batch, and lifecycle |
| Monitoring | Tracks local plans, remote sessions, latency, and errors |

FDW does not create local copies, does not automatically synchronize data, and does not guarantee a global transaction snapshot or atomic commit across multiple systems. Remote availability, networking, schema drift, credentials, and query pushdown all directly impact applications.

Choose an FDW when direct access to an external source provides clear benefits with acceptable latency and freshness. Use replication, ETL/ELT, staging, or materialized views when you need local availability, history, transformations, or heavy analytics. Always design with least privilege, TLS, schema contracts, monitoring, and fallbacks.

**A well-designed FDW integration does not just make a foreign table queryable; it also controls where queries run, what data crosses the network, which remote identity is used, and how the application responds when the external source changes or loses connectivity.**
