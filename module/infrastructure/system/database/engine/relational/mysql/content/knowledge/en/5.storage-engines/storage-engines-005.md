# CSV, ARCHIVE, FEDERATED, and conditions for use

## Objectives

After this lesson, you will be able to:

- Explain the purpose and storage characteristics of CSV, ARCHIVE, and FEDERATED.
- Create and inspect tables using each engine when supported by the server.
- Recognize limitations regarding indexes, transactions, data updates, and network dependencies.
- Choose the right engine for data exchange, historical data, or remotely accessed tables.
- Distinguish storage engines from CSV import/export tools, replication, and data integration solutions.

## 1. Role of specialized storage engines

MySQL supports multiple storage engines. Each engine determines how a table stores data and governs aspects of reading, writing, locking, and recovery. InnoDB is the standard choice for business data requiring transactions, foreign keys, and concurrent updates. Other engines serve narrower use cases:

- **CSV** stores rows in comma-separated text format, suited for certain simple data exchange workflows.
- **ARCHIVE** stores data in compressed form, suited for historical data that is primarily appended and read back.
- **FEDERATED** provides a local table acting as an access interface to a table on a remote MySQL server.

These engines do not offer the same feature set as InnoDB. Before using one, verify whether the engine is built or installed in your running MySQL version, then evaluate workload, data integrity requirements, transactions, and operability.

```mermaid
flowchart TB
    SQL[Application sends SQL to MySQL] --> TABLE[Table in MySQL]
    TABLE --> CSV[CSV: text-based data]
    TABLE --> ARC[ARCHIVE: compressed data]
    TABLE --> FED[FEDERATED: forwards requests to remote server]
    FED --> REMOTE[Remote MySQL server and actual table]
```

The diagram illustrates intended usage. With CSV and ARCHIVE, table data resides in storage managed by the local server. With FEDERATED, the table's data lives on a remote server; the local server holds the definition and forwards requests over a network connection.

## 2. Checking engine availability before creating tables

Run the following commands on the target server:

```sql
SHOW ENGINES;
SHOW PLUGINS;
```

`SHOW ENGINES` lists engines and their support status. `SHOW PLUGINS` helps check whether the corresponding plugin is loaded. Depending on product, version, and packaging, CSV or ARCHIVE may be built-in, while FEDERATED may need to be enabled or installed as a separate plugin. Do not assume every distribution provides the same list.

You can query metadata:

```sql
SELECT ENGINE, SUPPORT, COMMENT, TRANSACTIONS, XA, SAVEPOINTS
FROM information_schema.ENGINES
WHERE ENGINE IN ('InnoDB', 'CSV', 'ARCHIVE', 'FEDERATED');
```

Columns in `information_schema.ENGINES` and advertised engine names may vary by version. If an engine is missing or its status is not `YES`/`DEFAULT`, check the installation documentation for your exact server version before creating tables.

After creating a table, verify the actual engine:

```sql
SHOW CREATE TABLE table_name;

SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'table_name';
```

Do not infer the engine solely from the creation statement or `default_storage_engine`; the table's metadata is what confirms the engine in use.

## 3. CSV Storage Engine

### 3.1. How does CSV store data?

The CSV (Comma-Separated Values) Storage Engine stores row contents in comma-separated text format. Data can be read by MySQL through SQL and has a format familiar to standard CSV processing tools.

This engine has significant limitations:

- No index support, so filter or join queries may require scanning data.
- No transaction or rollback mechanism like InnoDB.
- No foreign keys to enforce referential relationships.
- Unsuitable for concurrent update workloads or high-performance queries.
- Data types and table operations must abide by engine constraints; do not assume every InnoDB DDL feature exists in CSV.

CSV is typically suitable for small staging tables, simple data exchange, or cases needing a table whose data is represented directly in CSV form. If you need indexes, constraint checks, transactions, or frequent querying, load the data into an InnoDB table.

### 3.2. Creating a CSV table

Example creating a simple data-ingestion table:

```sql
CREATE TABLE csv_contacts (
    contact_id INT NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    created_at DATETIME
) ENGINE = CSV
  DEFAULT CHARACTER SET = utf8mb4;
```

Insert and read data with SQL:

```sql
INSERT INTO csv_contacts (contact_id, full_name, email, created_at)
VALUES
    (1, 'Nguyen An', 'an@example.test', '2026-01-10 09:00:00'),
    (2, 'Tran Binh', 'binh@example.test', '2026-01-11 10:30:00');

SELECT contact_id, full_name, email
FROM csv_contacts;
```

Do not add `PRIMARY KEY`, `UNIQUE`, or indexes as if CSV had InnoDB's indexing capabilities. If duplicate checking is needed, perform it in a data-processing step or move into an InnoDB staging table with appropriate constraints.

### 3.3. The CSV Storage Engine is not the same as CSV import/export

This distinction is important. You do not need to create a table with the CSV engine to import or export CSV files. For most ETL workflows, the common approach is using `LOAD DATA` to import into an InnoDB table and `SELECT ... INTO OUTFILE` to export data.

Example loading a CSV file into an InnoDB staging table:

```sql
CREATE TABLE contact_stage (
    contact_id INT NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    created_at DATETIME
) ENGINE = InnoDB;

LOAD DATA LOCAL INFILE 'contacts.csv'
INTO TABLE contact_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(contact_id, full_name, email, created_at);
```

`LOCAL` reads the file from the client machine; omitting `LOCAL` reads the file under server-side permissions and configuration. Verify `local_infile`, file permissions, line formatting, delimiters, enclosure quotes, encoding, and newline handling to match the data source. Do not grant `LOCAL INFILE` permissions more broadly than system security requires.

After loading, you can validate data, filter bad rows, normalize types, and insert into the business table:

```sql
SELECT COUNT(*) AS imported_rows
FROM contact_stage;

INSERT INTO contacts (contact_id, full_name, email, created_at)
SELECT contact_id, TRIM(full_name), email, created_at
FROM contact_stage;
```

In real workflows, handle duplicate keys, missing values, invalid date/time values, and row-count reconciliation before writing into production business tables.

### 3.4. When to use and when to avoid CSV

| Scenario | Assessment |
|---|---|
| Simple data-exchange table with infrequent queries | CSV can be considered if engine limits are acceptable |
| Temporary staging data before moving to InnoDB | Usually prefer an InnoDB table for validation, indexes, and transactions; CSV fits only when direct CSV file traits are needed |
| Business tables with concurrent updates | Unsuitable |
| Frequent multi-column searches or JOINs | Unsuitable due to lack of indexes |
| Rolling back multiple operations as one transaction | Unsuitable |
| Importing/exporting CSV files | Typically use `LOAD DATA` or `SELECT ... INTO OUTFILE`; the CSV engine is unnecessary |

Do not directly edit data files managed by the server while MySQL is running. Modifying files externally can desynchronize file contents from engine-managed state. Use SQL or maintenance procedures supported by the engine's documentation.

## 4. ARCHIVE Storage Engine

### 4.1. Purpose and how it works

ARCHIVE is designed for compressed archival storage, typically data with high insert frequency that is read back when needed. The engine uses compression to reduce storage footprint; in return, compression/decompression and limited random access can increase CPU cost or read times.

Key characteristics to remember:

- Primarily an append-and-read usage pattern.
- Does not support `UPDATE` and `DELETE` the way InnoDB does; ARCHIVE is not designed for row-level modifications or deletions.
- Very limited indexing; MySQL supports indexing an `AUTO_INCREMENT` column within the engine's scope, without general-purpose indexing like InnoDB.
- Does not support transactions or foreign keys like InnoDB.
- Queries filtering on unindexed columns may have to read substantial amounts of compressed data.

Thus, ARCHIVE can be useful for logs or historical data that rarely changes, but carefully evaluate if frequent searches by timestamp, user, or event type are needed. You may need time-based partitioning at the design layer, summary tables, or keeping hot query data in InnoDB.

### 4.2. Creating an ARCHIVE table

Example of a historical event table where `event_id` is an auto-incrementing key:

```sql
CREATE TABLE archived_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_time DATETIME NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload MEDIUMTEXT NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = ARCHIVE;
```

Insert and read data:

```sql
INSERT INTO archived_events (event_time, event_type, payload)
VALUES
    ('2026-01-10 09:15:00', 'LOGIN', '{"userId": 101}'),
    ('2026-01-10 09:20:00', 'ORDER_CREATED', '{"orderId": 9001}');

SELECT event_id, event_time, event_type
FROM archived_events
WHERE event_id >= 1;
```

The index on `event_id` supports the `AUTO_INCREMENT` mechanism; do not assume you can add regular indexes on `event_time` or `event_type` as with InnoDB. Queries filtering on those columns may scan many rows.

### 4.3. Designing a data pipeline for ARCHIVE

A common architecture keeps recent data in InnoDB for updates and operational queries, then moves closed or expired records to an ARCHIVE table.

```text
Application writes events
        |
        v
InnoDB: active data
        |
        | Archival process by time / status
        v
ARCHIVE: compressed historical data
        |
        v
Reporting reads or historical lookups
```

The data-migration workflow must be designed carefully because operations across the two engines do not form a single transaction. A workflow may include:

1. Identifying the data range eligible for archiving.
2. Writing the records into the ARCHIVE table.
3. Reconciling row counts and key values between source and destination.
4. Only after successful verification, deleting old records from the InnoDB table per the retention policy.
5. Recording progress and designing safe re-runs if the job is interrupted.

Do not delete source data before verifying the destination data. Since ARCHIVE does not provide InnoDB-equivalent transactions, the pipeline needs idempotency, small batches, progress logging, and mid-run failure recovery.

### 4.4. When to use and when to avoid ARCHIVE

| Scenario | Assessment |
|---|---|
| Completed logs or events that rarely change | May fit when storage savings are prioritized and queries are infrequent |
| Historical data read sequentially or by auto-increment key | Worth considering after benchmarking realistic performance |
| Tables requiring frequent row updates or deletes | Unsuitable |
| Reporting queries needing fast filtering across multiple columns | Usually unsuitable without indexes; consider InnoDB or an analytical system |
| Requiring transactions, foreign keys, or complex concurrent updates | Unsuitable |
| Data requiring low-latency random access | Must benchmark; compression and index limits may fall short |

ARCHIVE does not replace a backup policy. Compressed data still requires backups, restore testing, and reconciliation per organizational retention requirements.

## 5. FEDERATED Storage Engine

### 5.1. How does FEDERATED work?

FEDERATED allows a local MySQL Server to expose a table whose structure corresponds to a table on a remote MySQL server. When an application queries the local table, the engine forwards the request to the remote server over the network and returns the result to the client.

```mermaid
flowchart LR
    APP[Application] --> LOCAL[Local MySQL Server]
    LOCAL --> FT[FEDERATED table: definition and endpoint]
    FT -->|MySQL protocol over network| REMOTE[Remote MySQL Server]
    REMOTE --> RT[Actual table on remote server]
    RT --> DATA[(Remote data)]
```

The local FEDERATED table is an interface to the remote table, not a data copy. Actual data resides on the remote server; therefore, read/write operations depend on network connectivity, the remote server, account privileges, and the target table's state.

FEDERATED is not replication: it does not maintain a synchronized local copy or a continuous replication stream. Nor is it a distributed transaction mechanism between two servers.

### 5.2. Prerequisites for creating a FEDERATED table

Before using it, verify:

- The FEDERATED engine/plugin is available and loaded on the local server.
- The remote server is reachable over the network and supports the protocol and statements required by the workload.
- The target table already exists on the remote server.
- Column definitions and related attributes on the local table match the target table: column order, data types, lengths, nullability, charset/collation, and required indexes.
- The remote connection account has least-privilege permissions needed for the operations.
- DNS, firewalls, TLS, timeouts, and connection resilience are properly configured.

If the engine does not appear in `SHOW ENGINES`, consult documentation for your exact distribution to install or enable the plugin. Plugin filenames, loading methods, and availability vary by OS, version, and product; do not copy plugin-installation commands from another platform.

### 5.3. Creating the remote table and local FEDERATED table

First, create the actual table on the remote server. For example, run in the `sales` database on the remote server:

```sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_time DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_time (customer_id, order_time)
) ENGINE = InnoDB;
```

On the local server, create a table with the matching definition and specify the remote endpoint:

```sql
CREATE TABLE remote_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_time DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_time (customer_id, order_time)
) ENGINE = FEDERATED
CONNECTION = 'mysql://fed_user:password@db.example.internal:3306/sales/orders';
```

In this example, replace `password` with the credential issued for the remote connection account. Never commit strings containing passwords to source control or shared documentation; protect metadata read access and use an environment-appropriate secrets manager. If the password contains special characters, follow the encoding rules for the connection string format.

The path in the connection string has the general form:

```text
mysql://user[:password]@host[:port]/database/table
```

Example querying the FEDERATED table:

```sql
SELECT order_id, customer_id, order_time, total_amount
FROM remote_orders
WHERE customer_id = 101
ORDER BY order_time DESC;
```

The SQL statement executes via the remote server. Performance depends on the network, round-trip count, returned data volume, query plan, and indexes on the actual table. Having indexes in the local definition does not replace checking indexes and execution plans on the remote server.

### 5.4. Limitations and risks of FEDERATED

- **Network dependency:** latency and remote connection errors directly impact local queries.
- **Target server dependency:** remote server downtime, overload, or schema changes can break the FEDERATED table.
- **No local copy:** every operation must contact the remote server; do not use FEDERATED as a cache.
- **No distributed transactions:** do not assume a local transaction can roll back changes sent to the remote server or guarantee ACID across two servers.
- **Performance limits:** queries returning large datasets or triggering many network round trips can be significantly slow.
- **Schema management:** changes to the remote table must be coordinated with the local FEDERATED table definition.
- **Connection credential security:** endpoints and credentials must be protected; the remote account should hold only required privileges.

Before allowing applications to write through FEDERATED, test behavior during timeouts, mid-operation network loss, target server restarts, and partially failed statements. If the business requires consistent transactions across multiple databases, use architectures and technologies that support distributed transactions or design appropriate saga/outbox patterns instead of assuming FEDERATED provides that capability.

### 5.5. When to use and when to avoid FEDERATED

| Scenario | Assessment |
|---|---|
| Simple integration with a remote MySQL table, moderate workload | Worth considering after checking plugin support, privileges, latency, and network errors |
| Need direct queries to data on another server without local replication | Suitable if dependency on the remote server is acceptable |
| Low-latency queries, heavy load, or caching needs | Usually unsuitable; consider read replicas, caches, or dedicated query services |
| Joining multiple sources with distributed optimization | Do not assume FEDERATED will optimize well; benchmark and consider a data integration layer |
| Requiring ACID transactions across two servers | Unsuitable |
| Requiring independent operation when the remote server loses connectivity | Unsuitable without another replica or fallback mechanism |

## 6. Comparing CSV, ARCHIVE, FEDERATED, and InnoDB

| Criterion | CSV | ARCHIVE | FEDERATED | InnoDB |
|---|---|---|---|---|
| Data location | Server-managed CSV-format file | Compressed archival data on server | Actual table on remote server | Local server tablespaces/logs |
| Primary purpose | Simple data exchange | Compressed historical storage | Accessing a remote MySQL table | Business data and OLTP |
| Indexes | Not supported | Very limited; supports `AUTO_INCREMENT` within engine limits | Depends on definition and indexes on remote table | Supports rich suitable index types |
| Transactions | No | No | No distributed transactions; do not assume cross-server ACID | Yes |
| Row updates/deletes | Limited, without InnoDB-style transactional behavior | Does not support `UPDATE`/`DELETE` in standard usage | Sends operations to remote table if engine/server supports them | Yes |
| Foreign keys | No | No | Does not provide cross-server referential integrity | Yes |
| Network dependency | No external server needed | No external server needed | Yes | No external server needed for local operations |
| Best suited for | Simple CSV-shaped data | Append/read historical data | Modest-scale remote table integration | Most business data |

This comparison table is high-level. Specific capabilities depend on MySQL/MariaDB, version, plugins, and configuration. In particular, FEDERATED can vary in statement support and behavior across implementations.

## 7. Engine selection workflow

Before selecting an engine, answer these questions in order:

1. **Where does the data reside?** If stored locally, CSV or ARCHIVE may be considered for narrow workloads; if on another server, FEDERATED is one direct-access option.
2. **How does the data change?** Data needing frequent updates or deletes should use an engine that fully supports those operations, typically InnoDB.
3. **Are transactions needed?** If multiple operations must commit or roll back together, choose a transactional engine.
4. **Are indexes and fast queries needed?** If filtering, joining, sorting, or looking up across multiple columns is common, use an engine and index design suited for it.
5. **Are foreign keys needed?** If the server must enforce referential relationships, use an engine supporting foreign keys.
6. **Are external dependencies acceptable?** FEDERATED makes queries depend on the network and remote server; evaluate timeouts, privileges, security, and fallback capacity.
7. **What are the backup/restore and operational capabilities?** Test recovery, monitoring, and error-handling procedures on the exact engine before moving to production.

Absent a verified special requirement, InnoDB is generally the safer default for business tables. Choose CSV, ARCHIVE, or FEDERATED only when their traits solve a specific need and their limitations are explicitly accepted.

## 8. Post-deployment verification and operations

After creating tables, inspect their engines and definitions:

```sql
SHOW CREATE TABLE csv_contacts;
SHOW CREATE TABLE archived_events;
SHOW CREATE TABLE remote_orders;

SELECT TABLE_NAME, ENGINE, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('csv_contacts', 'archived_events', 'remote_orders');
```

`TABLE_ROWS` may be only an estimate or carry different semantics across engines; do not use it in place of `COUNT(*)` when exact reconciliation is needed. For FEDERATED, local size metrics do not reflect the data size on the remote server.

Some operational principles:

- **CSV:** validate data after loading, standardize encoding and delimiters; use SQL to interact with the table while the server manages it.
- **ARCHIVE:** monitor storage usage, ingestion speed, read cost, and archival migration jobs; verify backups can be restored.
- **FEDERATED:** monitor network errors, query latency, target server health, account privileges, and schema changes; never expose credentials in logs or source control.
- **All engines:** document server version, plugins, table definitions, and backup/restore plans. Re-verify after upgrades because plugins or features may change.

## 9. Conclusion

CSV serves simple text-based data; ARCHIVE targets compressed historical data that is mostly appended and read; FEDERATED provides an SQL interface to tables on a remote MySQL server. Each engine has clear constraints around indexes, transactions, updates, or network dependencies.

Choose an engine based on how data is written, read, updated, and recovered. For business data requiring transactions, indexes, and referential integrity, InnoDB is typically the better fit. For CSV, ARCHIVE, and FEDERATED, verify plugins, test realistic workloads, and design reconciliation, backup, and security procedures prior to deployment.
