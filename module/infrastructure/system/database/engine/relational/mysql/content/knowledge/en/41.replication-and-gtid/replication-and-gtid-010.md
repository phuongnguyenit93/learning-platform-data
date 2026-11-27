# Replication filters and risks with cross-database transactions

MySQL replication filters allow a replica to apply only a subset of events received from the source—for example, keeping just one schema or one group of tables. This can be useful when creating a reporting replica or isolating a smaller dataset. However, filters do not understand business relationships across tables. A single transaction on the source can update multiple databases while the replica applies only part of the changes, leaving replica data inconsistent with the committed application state.

The risk is especially severe with cross-database transactions. For instance, one transaction updates both `sales.orders` and `billing.invoices`. If a replica filters out `billing`, the order may transition to paid while its invoice remains unpaid. With GTID, a transaction being recorded as processed does not mean any changes filtered out will automatically be replayed later.

This lesson explains where replication filters operate, the difference between database-level and table-level filtering, the impact of `binlog_format`, how GTID interacts with filters, and the testing process before using a filtered replica in production.

## 1. Where do replication filters operate?

In asynchronous replication, the source writes events to the binary log. The replica receives events, stores them in the relay log, and the applier reads the relay log and decides which events to apply. Standard replication filters are configured on the replica and take effect during the apply step.

```text
Application
   |
   v
MySQL source
   |  commit transaction
   v
Binary log (transaction events)
   |
   |  replication connection
   v
Relay log on replica
   |
   v
Replication applier + filter
   |                         |
   | kept events             | filtered events
   v                         v
Update replica tables      Skip corresponding changes
```

Filters do not prevent the source from writing data to the database, nor are they an access-control mechanism. Anyone with permission to read binary logs on the source can still access data recorded in the logs. If the goal is restricting data visibility, use SQL accounts and privileges; if the goal is creating a separate dataset, design an intentional extraction or sync pipeline.

Distinguish two configuration groups:

- **Source-side binary log filters:** `binlog-do-db` and `binlog-ignore-db` affect what the source writes into the binary log. Downstream replicas cannot apply events the source never wrote.
- **Replica-side replication filters:** `replicate-do-db`, `replicate-ignore-db`, `replicate-do-table`, `replicate-ignore-table`, `replicate-wild-do-table`, and `replicate-wild-ignore-table` affect what the replica applies.

These two groups have different scopes and evaluation rules. Do not treat similarly named options as having the same semantics. This lesson focuses on replica-side filters.

## 2. Types of replication filters

Commonly used options include:

| Option | Purpose |
|---|---|
| `replicate-do-db` | Applies only events belonging to the specified database, following log-format-dependent rules. |
| `replicate-ignore-db` | Skips events belonging to the specified database, following log-format-dependent rules. |
| `replicate-do-table` | Applies only changes matching the specified database and table. |
| `replicate-ignore-table` | Skips changes matching the specified database and table. |
| `replicate-wild-do-table` | Applies only tables matching the wildcard pattern. |
| `replicate-wild-ignore-table` | Skips tables matching the wildcard pattern. |

Example configuration keeping only tables in the `sales` schema:

```ini
[mysqld]
replicate-wild-do-table=sales.%
```

Example skipping audit tables in the `sales` schema:

```ini
[mysqld]
replicate-wild-ignore-table=sales.audit_%
```

The `%` character matches any sequence of characters in the wildcard patterns of these options. Check syntax and special-character handling for your running MySQL version. Do not configure overlapping rules without verifying how multiple matching filters resolve.

Filters can be set via startup options or changed dynamically with `CHANGE REPLICATION FILTER` on supported versions. Illustrative example:

```sql
STOP REPLICA SQL_THREAD;

CHANGE REPLICATION FILTER
  REPLICATE_WILD_DO_TABLE = ('sales.%');

START REPLICA SQL_THREAD;
```

This example uses MySQL 8.0 syntax and demonstrates changing filters while the applier is stopped. Before running, verify replication administration privileges, channel state, exact version syntax, and the impact of stopping the SQL thread. With multi-channel replication, determine whether the filter applies globally or to a specific channel using the corresponding `FOR CHANNEL` clause. Record the previous configuration so you can roll back.

## 3. Differences between STATEMENT and ROW

This is the most common pitfall when using database-level filters. With `replicate-do-db` and `replicate-ignore-db`, MySQL evaluates the database differently depending on the binary log format.

### Statement-based logging

With `binlog_format=STATEMENT`, database filters evaluate against the default database currently selected via `USE`, rather than always inspecting the database explicitly qualified in the SQL table name.

Example:

```sql
USE sales;
UPDATE billing.invoices
SET paid = 1
WHERE invoice_id = 9001;
```

If the replica uses `replicate-do-db=sales`, the statement above can be treated as belonging to the default database `sales` and applied, even though the table actually updated resides in `billing`. Conversely:

```sql
USE billing;
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 9001;
```

Filtering by default database can cause this statement to be skipped even though the target table belongs to `sales`.

Therefore, when using statement-based replication, never infer filter behavior solely from schema qualifiers written before table names in SQL. Inspect the default database at the time the statement runs and test with the application's actual statements.

### Row-based logging

With `binlog_format=ROW`, the binary log contains row change events. Database filters are evaluated based on the database containing the modified table. This is more intuitive when statements use fully qualified database names, yet it can still cause a cross-database transaction to be applied only partially.

For example, the source executes:

```sql
START TRANSACTION;

UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 9001;

UPDATE billing.invoices
SET paid = 1
WHERE order_id = 9001;

COMMIT;
```

If a replica filters to apply only `sales` using a database filter in row-based mode, the change on `sales.orders` can be kept while the change on `billing.invoices` is skipped. The source committed both changes in a single InnoDB transaction; the replica no longer reflects the full business outcome of that transaction.

With `replicate-do-table` and table wildcard filters, matching is evaluated by table object and follows specific rules for statements, row events, and multi-table statements. Do not extrapolate the behavior of a database filter to a table filter. In particular, DDL and multi-table statements must be tested individually for your version and `binlog_format`.

### Comparison table for choosing filters

| Criterion | Database filter | Table/wildcard filter |
|---|---|---|
| Scope | Entire database/schema | Specific tables or table patterns |
| Statement-based | `do-db`/`ignore-db` depends on the selected default database | Has table-specific matching rules; multi-table statements require testing |
| Row-based | Based on the database of the modified table | Based on the modified table |
| Main risk | Misfiltering due to default database assumptions; dropping part of cross-schema changes | May omit dependent tables in the same transaction or miss newly created tables |
| When to consider | Only when database boundaries align with business boundaries | When specific tables are needed and dependency mapping is complete |

For new systems, row-based logging generally makes events reflect actual data changes more clearly, but it does not make replication filters business-safe. If a filter drops part of the row events, the replica can still end up missing related data.

## 4. Risks of cross-database transactions

A cross-database transaction is a transaction that updates two or more schemas in a single commit. With InnoDB, the source can commit these changes as an atomic unit. Applications rely on this to guarantee that related tables transition state together.

Consider an e-commerce system with three schemas:

- `sales.orders`: order status.
- `billing.invoices`: invoice status.
- `inventory.stock`: stock quantity.

A payment confirmation operation may update all three schemas inside one transaction. If a replica keeps only `sales`, the invoice and inventory updates are not applied. Reporting queries on the replica may show an order as paid while stock and invoice remain unchanged.

Potential consequences include:

1. **Violated business invariants:** order, payment, and inventory states fall out of sync.
2. **Broken joins:** reports joining across schemas return incomplete numbers or inconsistent states.
3. **Incomplete foreign keys and logical references:** retained records may reference objects filtered out, even if physical constraints across schemas are not declared.
4. **Applications reading the replica make wrong decisions:** a replica used for reports or background jobs may trigger actions based on incomplete data.
5. **Unsafe failover:** if a filtered replica is promoted to become the new source, skipped data will not reappear automatically and the topology may continue propagating an incomplete state.

Not every cross-database transaction is guaranteed to be split; the outcome depends on the filter and event types. However, if a transaction touches both retained tables and excluded tables, treat it as a hazard until testing proves the exact behavior.

### Illustrative example of divergent state

**Before the transaction:**

| Table | State |
|---|---|
| `sales.orders` | `PENDING` |
| `billing.invoices` | `UNPAID` |
| `inventory.stock` | `10` |

The source commits a transaction: sets the order to `PAID`, the invoice to `PAID`, and reduces stock to `9`. The replica filters to keep only the `sales` schema:

| Table | Source after commit | Filtered replica |
|---|---|---|
| `sales.orders` | `PAID` | `PAID` |
| `billing.invoices` | `PAID` | `UNPAID` |
| `inventory.stock` | `9` | `10` |

The replica no longer represents a complete business state. If a report calculates revenue from `sales.orders` while reconciling invoices from `billing.invoices`, the results will be unreliable.

## 5. GTID and filtered transactions

A GTID (Global Transaction Identifier) identifies a transaction written to the binary log. Replicas use GTID auto-position to exchange executed transaction sets and determine missing transactions upon reconnecting.

Replication filters and GTIDs solve two different problems:

- Filters decide which changes are applied to the replica's data.
- GTIDs track which transactions have been processed in the replication stream.

When a transaction is filtered out completely or partially, the replica can still record the corresponding GTID as processed. With filtered transactions, GTID is not proof that every table on the replica received all changes from the transaction. Thus, `Executed_Gtid_Set` can advance while data in certain schemas or tables remains missing compared to the source.

Important consequence: if you later remove a filter or change it to include additional tables, GTID auto-position will not ask the source to resend transactions the replica has already marked as executed. Previously skipped changes will not be backfilled. You must load the missing data via a controlled synchronization workflow, such as rebuilding the replica from a suitable snapshot or resyncing the affected tables.

Checking GTID and replication status:

```sql
SHOW REPLICA STATUS\G

SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
```

`Retrieved_Gtid_Set` and `Executed_Gtid_Set` in `SHOW REPLICA STATUS` help inspect received and processed transactions. They do not measure data completeness after filtering. To verify data, compare table contents or checksums across the schemas within the replica's scope.

Never add fake GTIDs to `gtid_purged` or alter `gtid_executed` to mask data divergence. Those actions can make MySQL believe transactions were processed without restoring the lost changes. Identify the exact transactions and plan a resync before modifying GTID state.

## 6. Designing safer filters

Before setting up a filter, map business and data dependencies. Schema boundaries in MySQL do not necessarily align with service or transaction boundaries. An application can update multiple schemas in one transaction, use triggers that write to another schema, or call stored procedures touching multiple tables.

Follow these steps:

1. **List tables to retain:** identify source tables, reference tables, lookup tables, configuration tables, and audit tables needed by the replica workload.
2. **Map dependencies:** find transactions, triggers, procedures, events, and application jobs that may write across multiple schemas.
3. **Choose the filter scope:** prefer selecting a dataset with clear business boundaries. If specific tables are required, use table/wildcard filters and test matching rules.
4. **Verify log format:** record `binlog_format` and test any remaining statement-based queries if the topology uses them.
5. **Test DDL:** test `CREATE`, `ALTER`, `RENAME`, `DROP`, `TRUNCATE`, triggers, and related procedures. DDL is typically logged as query events and cannot be inferred solely from row event tests.
6. **Define invariants:** write assertions that must hold on the replica, e.g., every `PAID` order in scope must have a corresponding invoice.
7. **Evaluate failover:** decide whether a filtered replica is allowed to be promoted or restricted strictly to read workloads.
8. **Plan resync:** define how data will be rebuilt if filters change or transactions are accidentally skipped.

If the goal is merely offloading read queries, consider a full replica with read permissions restricted by schema or workload. If the goal is supplying a smaller dataset to another system, an ETL/CDC pipeline with explicit schema mapping and transaction controls is usually easier to govern than using replication filters as a general-purpose data distribution mechanism.

## 7. Configuration example and verification

Suppose a reporting replica needs only tables in the `reporting` schema and certain dimension tables in `reference`. Illustrative wildcard configuration:

```ini
[mysqld]
replicate-wild-do-table=reporting.%
replicate-wild-do-table=reference.dim_%
```

Before deploying, verify how multiple values for an option are configured in the config file, how multiple rules combine, and how newly created tables behave. Repeating options can depend on the MySQL config parser; use the exact syntax supported by your version's documentation. Never copy this example into production without testing on a clone of the topology.

Check status:

```sql
SHOW REPLICA STATUS\G
```

Look closely at filter-related fields such as `Replicate_Do_DB`, `Replicate_Ignore_DB`, `Replicate_Do_Table`, `Replicate_Ignore_Table`, `Replicate_Wild_Do_Table`, and `Replicate_Wild_Ignore_Table`. Also monitor:

- `Replica_IO_Running` and `Replica_SQL_Running` to verify whether receiver and applier are active.
- `Last_SQL_Error` and `Last_IO_Error` to catch apply or log-fetch errors.
- `Seconds_Behind_Source` as a lag indicator, not proof of data completeness.
- `Retrieved_Gtid_Set` and `Executed_Gtid_Set` to understand transaction progress.

Field names vary by version; in modern MySQL 8.0, use `SHOW REPLICA STATUS`. Older releases may use `SHOW SLAVE STATUS` and its corresponding field names.

You can inspect events written by the source using `mysqlbinlog` on unencrypted files or via a remote reader if logs are encrypted:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000456
```

For row-based events, `-vv` displays detailed row values in comments. Protect the output because it may contain sensitive data. If binary logs are encrypted, read through a server with the keyring rather than assuming direct disk reads will succeed.

## 8. Testing procedure for cross-database transactions

Testing should run on an isolated source and replica with the same version, log settings, and planned filters. Create two sample schemas:

```sql
CREATE DATABASE sales;
CREATE DATABASE billing;

CREATE TABLE sales.orders (
  order_id BIGINT PRIMARY KEY,
  status VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE billing.invoices (
  invoice_id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL,
  paid TINYINT NOT NULL
) ENGINE=InnoDB;

INSERT INTO sales.orders VALUES (1001, 'PENDING');
INSERT INTO billing.invoices VALUES (5001, 1001, 0);
```

On the source, run a transaction updating both schemas:

```sql
START TRANSACTION;
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;

UPDATE billing.invoices
SET paid = 1
WHERE order_id = 1001;
COMMIT;
```

Once the replica catches up, compare each table on the source and replica. Repeat the test with both `STATEMENT` and `ROW` on a separate test topology, while switching the default database via `USE` and using fully qualified table names. Add test cases for:

- Transactions updating only a retained schema.
- Transactions updating only an excluded schema.
- Transactions updating both a retained schema and an excluded schema simultaneously.
- Multi-table statements or procedures/triggers writing across schemas.
- DDL creating, renaming, or dropping tables within the filter scope.
- Changing filters after the replica has already processed some GTIDs.

Record the result of each test: which tables changed, which GTIDs executed, any applier errors, and whether business invariants still hold. Green replication status metrics do not replace actual data comparison.

## 9. Diagnosing and recovering from divergence

| Symptom | Possible cause | Remediation |
|---|---|---|
| Replica GTID advances, yet a table lacks data | Transaction was completely or partially filtered out | Compare filters against transactions; plan table resync or replica rebuild. |
| Retained schema table updates, other schema does not | Cross-database transaction was filtered by schema | Identify violated business invariants; do not use this replica for queries needing both schemas. |
| SQL uses fully qualified schema names, yet filter behaves unexpectedly | `replicate-do-db`/`ignore-db` under statement-based mode depends on default database | Check `USE`, `binlog_format`, and actual events; consider table filters after testing. |
| After removing the filter, replica still lacks historical data | GTIDs were marked processed when transactions were filtered | Backfill/resync data; GTID auto-position does not automatically replay already-marked transactions. |
| Replica SQL thread stops | Apply error, incompatible DDL, missing object, or schema mismatch | Read `Last_SQL_Error`, inspect events and schema; fix root cause and resume per runbook. |
| Replica promoted, yet application discovers missing tables/rows | Replica was designed to retain only a subset of data | Do not promote a filtered replica as a full replacement; recover from a full replica or appropriate backup. |

When a misconfigured filter is discovered, first halt expanding read traffic or promoting the replica. Save replication status, filter config, GTID sets, and relevant logs. Then determine the scope of skipped data, select a resync strategy, and verify via data comparison. Proceed only after workload invariants are restored.

Never remove a filter, run `START REPLICA`, and assume data will fill itself in automatically. Transactions already marked executed may not be resent under GTID auto-position. Backfilling requires a consistent snapshot or export, handling concurrent writes, and a plan to avoid overwriting newer changes.

## 10. Recommendations for production architectures

Replication filters are suitable when the replica's dataset is clearly defined, table dependencies are controlled, and the workload tolerates omitted data. A replica holding only select tables can serve bounded reporting, provided it is clearly documented which schemas are present and which queries are disallowed on it.

Principles to follow:

- Do not use a filtered replica as a full failover standby unless a procedure exists to reconstruct excluded data.
- Avoid cross-database transactions spanning retained and excluded schemas; if unavoidable, do not assume the replica preserves business atomicity.
- Do not treat executed GTIDs as proof that every row event was applied.
- Monitor schema changes and new tables; wildcard filters may unexpectedly include new objects.
- Use SQL privileges to restrict users, not replication filters as a security boundary.
- Maintain a full backup and a full replica if HA requires source replacement capability.
- Periodically verify checksums or compare data on tables within the replica's scope.

If the application requires consistency across multiple schemas, the safe choice is usually full replication. If you only need to deliver selective data to another system, consider CDC or ETL with well-defined data contracts, transaction ordering, and relationship handling rules.

## 11. Checklist before deploying filters to production

- [ ] Clearly defined the replica's purpose and workload; all consumers know which data is excluded.
- [ ] Documented MySQL version, `binlog_format`, and filter types in use.
- [ ] Distinguished source-side `binlog-do-db`/`binlog-ignore-db` from replica-side `replicate-*`.
- [ ] Mapped triggers, procedures, events, and transactions writing across schemas.
- [ ] Tested cross-database transactions under both `STATEMENT` and `ROW` with actual configuration.
- [ ] Tested DDL, multi-table statements, wildcards, and newly created tables.
- [ ] Verified filter outcomes on actual data, not solely via SQL thread status or GTIDs.
- [ ] Understood that changing filters does not automatically backfill prior transactions already marked executed.
- [ ] Established resync and data verification procedures when filters change or are misconfigured.
- [ ] Filtered replica clearly marked ineligible for failover without a recovery step for excluded data.
- [ ] Maintained a full backup and recovery plan independent of the filtered replica.

A replication filter is a tool for selecting events to apply, not an engine that understands business transactions. When a source transaction updates multiple databases, a filter can leave a replica with only part of the committed result. Combining `binlog_format`-specific testing, GTID monitoring, and real data verification helps prevent mistakenly relying on an incomplete replica for reporting, business processing, or failover.
