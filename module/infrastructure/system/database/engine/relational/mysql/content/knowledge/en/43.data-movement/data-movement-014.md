# Migrating from Other DBMSs and Handling Data Type / SQL Semantics Differences

## Objectives

Migrating data from PostgreSQL, SQL Server, Oracle, or another DBMS to MySQL is more than rewriting `CREATE TABLE` syntax and reloading rows. Two systems can interpret the same data type, SQL expression, null/empty value, time zone, auto-increment key, and constraint in different ways. Moving data without preserving semantics can leave the new system running while returning wrong results, dropping data, or failing under application load.

This lesson belongs to the **DATABASE_MYSQL** module, covering table design, data types, keys, SQL, indexes, transactions, concurrency control, reading execution plans, query tuning, and relational database operations. It guides you through inventorying the source system, mapping data types, converting SQL, migrating data in phases, and verifying equivalence after cutover.

After this lesson, you will be able to:

- Inventory schemas, data, constraints, routines, privileges, and dependencies on the source system.
- Build a verifiable data-type mapping table and conversion rules.
- Identify differences in `NULL`, empty strings, collations, date/time handling, arithmetic, and SQL syntax.
- Choose how to load data, sync changes, and cut applications over to MySQL.
- Reconcile counts, content, relationships, and business behavior before putting the new system into production.

## 1. Start by Inventorying the Source System

Before writing DDL or ETL, determine what exists on the source and which behaviors the application depends on. Inventorying tables alone is insufficient: views, sequences, triggers, stored procedures, functions, jobs, privileges, collations, time zones, isolation levels, and application-side logic all affect migration outcomes.

Collect at least these information groups:

| Group | What to Record | Why It Matters |
|---|---|---|
| Platform | DBMS name, version, extensions, encoding, time zone | Determines compatibility and extraction method |
| Structure | Schemas, tables, columns, types, defaults, generated columns, partitions | Forms the basis for target DDL |
| Constraints | Primary keys, unique keys, foreign keys, checks, triggers | Preserves integrity and load order |
| Data | Row counts, sizes, distributions, `NULL`s, min/max, anomalous values | Estimates duration and catches unmappable values |
| SQL and apps | Queries, views, procedures, functions, ORMs, migration scripts | Identifies syntax and semantics needing changes |
| Operations | Backups, CDC, batch schedules, accounts, privileges, audits | Ensures safe cutover and recovery |

Identify which system is the authoritative writer during migration. Document external integrations such as ETL jobs, reports, queues, payment services, and scheduled tasks. A table unused by the primary application may still feed another pipeline.

## 2. Building a Data-Type Mapping Table

No single automated conversion table fits every DBMS and application. Mapping must rely on actual value ranges, required precision, and how the application consumes the data.

Common mapping directions:

| Source Type or Concept | Candidate MySQL Type | What to Verify |
|---|---|---|
| 16/32/64-bit integers | `SMALLINT`, `INT`, `BIGINT` | Value ranges, signedness, and overflow risk; never switch to `UNSIGNED` if the source permits negative numbers |
| Exact decimals | `DECIMAL(p,s)` | Preserve precision/scale; check maximum values and fractional digits |
| Approximate floats | `FLOAT`, `DOUBLE` | Whether binary rounding error is acceptable or `DECIMAL` is required |
| Boolean | `BOOLEAN` or `TINYINT(1)` | In MySQL, `BOOLEAN` is an alias for `TINYINT(1)`; check whether source contains values outside 0/1 |
| Unicode strings | `VARCHAR`, `TEXT` with `utf8mb4` | Length in characters vs. bytes, collation, supplementary BMP characters, and index limits |
| Dates and timestamps | `DATE`, `DATETIME(fsp)`, `TIMESTAMP(fsp)` | Time zone, fractional seconds precision, and supported date range |
| UUID | `BINARY(16)` or `CHAR(36)` | Byte order, canonicalization, readability, and app compatibility |
| Binary large object | `BLOB`, `MEDIUMBLOB`, `LONGBLOB` | Maximum size, encoding, and transfer mechanism |
| JSON or document | `JSON` or relational tables | Structure, numeric types, indexes, and per-attribute queries |
| Array or collection | Relational child table or `JSON` | Whether joins, per-element constraints, and element-level filters are needed |

Select types based on data and business semantics, not source type names alone. For example, an Oracle `NUMBER` column can represent counts, currency, ratios, or identifiers; each case carries different requirements.

### Integers and Decimals

For currency or measurements requiring exactness, prefer `DECIMAL(p,s)` over `FLOAT`/`DOUBLE`. Choose `p` large enough for total digits and `s` large enough for fractional digits. Before loading, profile values exceeding bounds or having greater scale than the target; never round silently.

For instance, if the source stores monetary amounts up to 12 total digits and 2 decimal places, `DECIMAL(12,2)` fits. If the source holds more digits, increase precision or establish a business-approved rounding rule.

### Booleans, Bits, and Default Values

MySQL accepts `BOOLEAN` as an alias for `TINYINT(1)`, yet this type does not automatically restrict values to 0 and 1. If enforcement is needed, use a `CHECK` constraint on supported versions and audit historical data before enabling it. In MySQL 8.0.16 and later, `CHECK` constraints are enforced; earlier versions may parse without enforcing them.

Do not convert source bit or boolean columns to `TINYINT` without checking how drivers read and write them. Verify `true`, `false`, `NULL`, defaults, and malformed values.

## 3. Dates, Time Zones, and Precision

Date and time handling is a frequent failure point because DBMSs do not all share identical storage and display rules.

- `DATE` stores a calendar date without time.
- `DATETIME(fsp)` stores date and time literally as supplied, without converting by session time zone.
- `TIMESTAMP(fsp)` converts between session time zone and UTC on write/read; its supported range is narrower than `DATETIME` and version-dependent.
- `fsp` from 0 to 6 specifies fractional second precision; match source precision.

If the source stores absolute instants with time zone offsets, normalize to UTC during extraction or ETL, and document the convention in MySQL. If the source stores local wall-clock times without time zone metadata, exact offsets cannot be inferred reliably across daylight saving transitions or historical rule changes. Establish the business time zone for every temporal field.

Example checking time zones in MySQL:

```sql
SELECT @@GLOBAL.time_zone,
       @@SESSION.time_zone,
       NOW(),
       UTC_TIMESTAMP();
```

Do not convert every temporal column to `TIMESTAMP` out of habit. Event timestamps may fit UTC, whereas store appointment hours or birth dates are usually local calendar values better suited to `DATETIME` or `DATE`. Document conventions in the data dictionary.

## 4. Strings, Encoding, Collation, and NULL

Modern MySQL deployments should use `utf8mb4` for Unicode data. `utf8mb4` supports full Unicode, including characters outside the BMP. When creating schemas or tables, declare charset and collation explicitly to avoid depending on server defaults:

```sql
CREATE DATABASE app_migrated
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

`utf8mb4_0900_ai_ci` is available in MySQL 8.0; if compatibility with another version is needed, pick a collation supported by the target version. The suffix `ai_ci` denotes accent-insensitive and case-insensitive comparisons. If business logic requires sensitivity, select and test the appropriate collation.

Collation governs comparisons, sorting, and unique indexes. For instance, two strings differing only in case or accents may be treated as equal under an insensitive collation. A valid unique key on the source can collide as a duplicate when loaded into MySQL. Before creating unique indexes, search for value groups that collide under the target collation.

Distinguish three states:

- `NULL`: absent or unknown value per the data model.
- Empty string `''`: a valid string value of length zero.
- Whitespace-only string: still a string value; do not auto-`TRIM` unless business rules dictate it.

Oracle treats empty strings in certain character types as `NULL`, whereas MySQL distinguishes `''` from `NULL`. When migrating from Oracle, identify which columns use empty strings to signify missing data and convert intentionally. Never apply `NULLIF(column, '')` globally if empty strings are legitimate values.

Verify nullability, defaults, and unique constraints. MySQL permits multiple `NULL` values in a unique index per its rules; if the source behaves differently, add validation and supplemental constraints.

## 5. JSON, Arrays, UUIDs, and Specialized Types

**JSON:** MySQL provides a `JSON` type with validation and JSON query functions. However, numeric types, date formatting, key ordering, and operators can differ from the source DBMS. If an attribute is frequently joined, filtered, or constrained, consider extracting it into a typed column or indexed generated column instead of keeping everything inside JSON.

**Arrays:** MySQL has no general relational array type equivalent to PostgreSQL's. If elements require joins, uniqueness, foreign keys, or frequent filtering, normalize into a child table with one row per element. Use `JSON` only when data is genuinely document-oriented and per-element querying is not a primary access path.

**UUIDs:** `CHAR(36)` is readable and interoperable, though it consumes more space. `BINARY(16)` is compact but demands consistent conversion rules. If using `UUID_TO_BIN()` and `BIN_TO_UUID()`, standardize the swap flag across all applications and tools; mismatched conventions return scrambled UUIDs.

**Sequences and identity:** PostgreSQL sequences, SQL Server `IDENTITY`, or Oracle sequences generally map to `AUTO_INCREMENT` where appropriate. `AUTO_INCREMENT` does not guarantee gapless sequences and can leave gaps after rollbacks or errors. If source IDs must be preserved, load explicit IDs and set the next counter value appropriately after checking `MAX(id)`.

**Enums and domains:** do not automatically translate source enums/domains into MySQL `ENUM`. `VARCHAR` with a `CHECK` constraint or a lookup table is usually far more flexible when allowed values evolve or carry metadata.

## 6. Translating SQL Semantics

Even standard SQL varies across products, versions, and SQL modes. Test critical queries rather than merely fixing syntax until errors disappear.

| Topic | Common Differences | Handling in MySQL |
|---|---|---|
| String concatenation | SQL Server commonly uses `+`; PostgreSQL/Oracle have `\|\|`; MySQL defaults to treating `\|\|` as logical OR unless a special SQL mode is set | Use `CONCAT()` or `CONCAT_WS()` and test behavior with `NULL` |
| Row limiting | SQL Server has `TOP`; Oracle/PostgreSQL have distinct syntax | Use `LIMIT` and `OFFSET` paired with deterministic `ORDER BY` |
| Upsert | PostgreSQL uses `ON CONFLICT`; SQL Server/Oracle use other forms | Use `INSERT ... ON DUPLICATE KEY UPDATE` and test which unique key triggers it |
| Date/time functions | Function names, arithmetic rules, and time zones differ | Use matching MySQL functions; test month-end, leap-day, and DST boundaries |
| Boolean | Some systems have a dedicated boolean type | `BOOLEAN` is an alias for `TINYINT(1)`; validate allowed value ranges |
| Identifiers | Identifier quoting differs | Use backticks for identifiers in MySQL; avoid relying on reserved words or case |
| `GROUP BY` | Some systems allow non-grouped columns under custom rules | Comply with `ONLY_FULL_GROUP_BY` and specify aggregates explicitly |
| Pagination | Large `OFFSET` is costly and unstable without unique ordering | Use a unique `ORDER BY`; consider keyset pagination for large datasets |

### NULL and Expressions

In SQL, comparing against `NULL` with `= NULL` never yields true; use `IS NULL` or `IS NOT NULL`. `NOT IN` can produce unexpected empty results if the subquery set contains `NULL`; consider `NOT EXISTS` when porting queries.

MySQL's `CONCAT()` returns `NULL` if any argument is `NULL` under normal modes. If the source ignores `NULL` when concatenating strings, use `CONCAT_WS()` or `COALESCE()` according to the desired rule. Write tests covering all non-null, one null, and all null columns.

### Upsert and REPLACE

MySQL supports `INSERT ... ON DUPLICATE KEY UPDATE`, triggered by collisions on a primary key or unique key. If a table has multiple unique indexes, check which collision triggers the update branch. Never replace every `MERGE` or `ON CONFLICT` with this syntax without comparing match predicates and affected row counts.

Avoid using `REPLACE` as a generic upsert: MySQL may delete the old row and insert a new one, altering triggers, foreign keys, auto-increment values, and audit trails. `INSERT IGNORE` is likewise unsafe as a default because it can downgrade errors into warnings and silently drop invalid data.

### GROUP BY and SQL Mode

MySQL enables `ONLY_FULL_GROUP_BY` in the default SQL mode of many modern releases. Queries selecting columns that are neither aggregated nor functionally dependent on grouped columns are rejected. Do not disable the mode just to let legacy queries run; rewrite queries with aggregates, add columns to `GROUP BY`, or pick a deterministic row via an appropriate window function.

Check active settings:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

Run applications under strict mode in test environments. Strict mode surfaces out-of-range numbers, truncated strings, and invalid dates rather than silently coercing them.

## 7. Keys, Indexes, Constraints, and Transactions

Data movement must preserve cross-table relationships. Load parent tables before child tables when foreign keys are enabled, or load into staging, validate, and create constraints once data is clean. Never disable foreign key checks without a follow-up verification step.

MySQL InnoDB uses a clustered index ordered by the primary key. Choose a primary key suited to size, uniqueness, and write patterns. If the source uses random UUIDs as keys, evaluate the impact on page locality and secondary index size. You can keep the business UUID in a unique key and use an integer surrogate key if the design allows.

Source indexes do not always translate one-to-one to MySQL. Differences in collations, index key length, prefixes, selectivity, optimizer behavior, and data types can alter effectiveness. After loading representative data, create needed indexes and inspect key queries with `EXPLAIN`.

DDL in MySQL can cause implicit commits. Although some DDL is atomic in modern versions, never assume an entire schema migration can roll back like a DML transaction. Break migrations into small steps, test on clones, and prepare recovery plans.

Verify isolation levels, locking, and deadlock patterns. Applications moving from a DBMS with a different default isolation level may see data or lock waits differently. Determine required isolation levels and test concurrent transactions before cutover.

## 8. Designing the Data Movement Pipeline

Small systems can export/import within a maintenance window. Large systems or tight downtime budgets typically combine an initial full load with Change Data Capture (CDC) to sync changes occurring during the load.

General workflow:

1. **Prepare target schema:** create databases, charsets, collations, tables, data types, keys, and constraints per the approved mapping.
2. **Consistent extraction:** take a point-in-time snapshot; record the source tool's log position, LSN, SCN, or checkpoint.
3. **Initial data load:** use dump/import, bulk load, ETL, or an appropriate migration tool; stage data if cleansing or transformation is needed.
4. **Sync ongoing changes:** run CDC or a delta stream to propagate inserts, updates, and deletes in order with checkpoints.
5. **Verify:** compare row counts, canonicalized checksums, keys, relationships, and business metrics.
6. **Rehearse cutover:** measure write-freeze duration, final delta time, app checks, and rollback procedures.
7. **Cutover:** stop or fence writes on the source, apply remaining changes up to the sync checkpoint, verify alignment, and switch app endpoints.
8. **Post-cutover monitoring:** watch for errors, latency, new writes, slow queries, and business outcomes.

CDC is a general pattern; exact log capture and ordering guarantees depend on the source DBMS and tool. Verify whether the tool captures DDL, how it handles truncates/partitions, how it buffers large transactions, and whether it resumes cleanly from checkpoints after restarts.

## 9. Loading Data and Staging Processing

Never push unvalidated data directly into production tables. Staging tables preserve raw extracted values, expose defects, and support repeatable mapping transformations.

Example target table:

```sql
CREATE TABLE customers (
  customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_system VARCHAR(32) NOT NULL,
  source_customer_id VARCHAR(128) NOT NULL,
  email VARCHAR(320) NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (customer_id),
  UNIQUE KEY uq_customer_source (source_system, source_customer_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

A unique key on `(source_system, source_customer_id)` preserves source identity even when MySQL's internal key differs from the source key. If `email` serves as a unique identifier, decide case-sensitivity and collation rules before creating the unique index.

For CSV files with verified encoding and delimiters, `LOAD DATA` loads rapidly into staging:

```sql
LOAD DATA LOCAL INFILE 'customers.csv'
INTO TABLE stg_customers
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES;
```

`LOCAL` reads the file on the client side and depends on client/server settings; enable it only when security policy permits. CSV format must explicitly define `NULL`, empty strings, embedded newlines, delimiters, and escapes. Inspect warnings after load and reconcile actual row counts; never ignore warnings caused by truncation or type conversion.

## 10. Verifying Data and Semantics

No single count proves a migration is correct. Apply layered checks:

| Check | Example | What It Catches |
|---|---|---|
| Counts | `COUNT(*)` by table and partition | Missing or extra rows |
| Value ranges | `MIN`, `MAX`, `SUM`, percentiles | Overflows, wrong scale, truncated values |
| `NULL` and empty strings | Counts of `IS NULL`, `= ''`, string lengths | Altered missing-data semantics |
| Unique keys | `GROUP BY key HAVING COUNT(*) > 1` | Collation or mapping collisions |
| Relationships | Anti-join between child and parent tables | Orphan foreign keys |
| Timestamps | Min/max, samples around DST and day boundaries | Wrong time zone or precision |
| Content | Hashes over canonicalized batch serializations | Post-conversion value drift |
| Business logic | Total amounts, order counts by status, balances, stock | Discrepancies even when row counts match |

Example checking duplicate keys under target collation:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
```

Example checking child records without parent records:

```sql
SELECT o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
```

Hashes must be computed over identical canonicalizations on both sides: standardize time zone, encoding, column order, `NULL` markers, decimals, and strings. Partition data into batches to localize mismatches. Hashing does not replace business checks or constraint validation.

## 11. Cutover and Rollback Plan

Cutover requires clear criteria before starting. A solid runbook designates who authorizes stopping writes, who confirms the CDC checkpoint, who verifies data, and who decides to switch endpoints.

Typical sequence:

1. Announce the maintenance window and stop source writers per plan.
2. Wait for in-flight transactions to finish; record the source's final checkpoint.
3. Apply all deltas/CDC up to that checkpoint on MySQL.
4. Run rapid checks on row counts, keys, business totals, and replication/CDC status.
5. Switch applications to MySQL endpoints, start writers in order, and monitor errors.
6. Keep the old source read-only or write-isolated during the validation window.

Rollback is not simply flipping endpoints back. Once applications write new data to MySQL, the old source lacks those transactions. Rolling back without data loss requires a pre-rehearsed reverse replication/CDC, reconciliation, and reverse-cutover plan. If no reverse-sync path exists, rollback decisions must explicitly state how new target data will be preserved.

Define go/no-go criteria, such as zero critical data errors, zero check discrepancies or all within approved tolerances, cutover duration within RTO, and critical read/write flows passing smoke tests.

## 12. Common Conversion Pitfalls

- **Numeric truncation or rounding:** target precision/scale too small. Profile value ranges and check warnings before loading production.
- **Time zone shift:** timestamps shifted by hours or missing sub-second precision. Standardize on UTC and explicitly identify local-time fields.
- **Unique collisions after collation change:** previously distinct strings treated as equal by target collation. Check for duplicates before adding unique indexes.
- **Empty string turned into `NULL` or vice versa:** missing-value counts change. Define per-column rules and profile separately.
- **Wrong semantics for `CONCAT`, `NULL`, `NOT IN`, or `GROUP BY`:** queries run yet return different results. Write comparative tests on edge-case datasets.
- **Lost sequence/identity:** next ID collides or jumps incorrectly. Load source IDs cleanly and reset `AUTO_INCREMENT` properly.
- **CDC missing deletes or DDL:** target diverges from source. Verify tool capture capabilities and handle DDL explicitly.
- **Wrong relational load order:** foreign keys fail or orphan rows appear. Load following the dependency graph and verify afterward.
- **Cutover before delta finishes:** MySQL misses final transactions. Lock checkpoint, wait for full apply, and confirm before opening writes.
- **Rolling back after target writes:** new data does not exist on the old source. Rehearse reverse sync or data-preservation procedures prior to cutover.

## 13. Practice Exercise

Suppose you must migrate an e-commerce application from PostgreSQL or SQL Server to MySQL:

1. Inventory customers, orders, order-items tables, data types, primary/foreign keys, views, and critical queries.
2. Build a mapping table for IDs, decimals, booleans, timestamps, text, UUIDs, and JSON; specify rules for `NULL`, empty strings, time zones, and collations.
3. Create the MySQL schema using InnoDB, `utf8mb4`, and appropriate keys and constraints.
4. Load a sample dataset into staging, resolve out-of-range values, and log every warning.
5. Port queries using `TOP`, `||`, `+`, upserts, `GROUP BY`, or date/time functions to MySQL SQL; write tests for edge-case data.
6. Reconcile row counts, monetary totals, order counts by status, duplicate keys, foreign keys, and timestamps.
7. Rehearse full load plus delta/CDC, lock a checkpoint, and cut the app over to MySQL in a test environment.
8. Test the rollback procedure and define how post-cutover transactions are preserved.

**Completion Criteria:** the MySQL schema accurately reflects data domains; business queries return equivalent results under agreed rules; no data is truncated or silently coerced; and operations can execute cutover, verification, and rollback following the runbook.

## Conclusion

Migrating to MySQL means transferring both data and the semantics applications rely upon. Inventory the source system, map types by actual value domain, explicitly handle time zones, collations, `NULL`s, and SQL modes, and move data using consistent snapshots and checkpointed deltas. Cut over only when data and business checks pass, and rehearse how new writes are preserved if rollback becomes necessary.
