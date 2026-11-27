# Reconciling Row Counts, Business Control Totals, and INVALID Objects After Migration

After migrating an Oracle Database using Data Pump, transportable tablespaces, RMAN, or another method, the job does not end when the import command returns success. DBAs and application teams must prove that target data is complete, business-accurate, metadata is valid, and applications can operate normally.

Post-migration reconciliation should be performed across multiple layers:

1. **Snapshot consistency:** confirm that the source and target data being compared belong to the same business point in time.
2. **Row counts:** compare record counts by table, partition, and business dimensions.
3. **Business control totals:** compare monetary totals, quantities, min/max, null counts, distinct counts, and control totals.
4. **Row-level reconciliation:** locate missing, extra, duplicate, or differing rows using business keys and bidirectional comparisons.
5. **Metadata and object status:** verify tables, indexes, constraints, triggers, sequences, synonyms, grants, and INVALID objects.
6. **Application testing:** confirm transaction flows, reports, jobs, and post-cutover performance.

No single checksum number proves an entire database is correct. Identical row counts can still hide corrupted data; identical monetary totals can still hide two swapped transactions; VALID object status does not prove business logic works properly. Combine independent checks and preserve results as migration evidence.

## 1. Reconciliation Goals and Scope

### 1.1. Why reconcile?

A migration can finish technically yet still harbor defects:

- Some tables were not exported/imported due to filters or privileges.
- New data generated after export time was not synchronized.
- Rows were dropped due to conversion, constraint, or data type errors.
- Character conversion altered characters.
- Timezone-aware timestamps display or convert differently.
- Indexes/constraints/triggers were disabled or INVALID.
- Stored procedures/views/packages fail to compile due to dependencies or feature differences.
- Sequences/identities are too low, leading to duplicate key errors after cutover.
- Grants, synonyms, database links, Scheduler jobs, or directory objects are missing.
- Data imported accurately, yet the application connects to the wrong service/schema.

Reconciliation catches these issues before opening production traffic or before the rollback window closes.

### 1.2. Verification layers

| Layer | Question to answer | Evidence |
|---|---|---|
| Snapshot | Do source and target share the same data scope? | SCN, freeze time, export log |
| Completeness | Are all records present? | Exact row counts, partition counts |
| Business correctness | Are totals and distributions right? | Control totals, aggregates |
| Row correctness | Which rows are missing/extra/different? | Key-based diff, mismatch report |
| Structural integrity | Are schemas and objects valid? | Constraints, indexes, INVALID objects |
| Operational readiness | Does the application run properly? | Smoke tests, job tests, application sign-off |

### 1.3. Reconciliation scope

Clearly define which schemas, tablespaces, tables, partitions, LOBs, views, materialized views, and non-schema objects fall within migration scope. If include/exclude filters were used, record the expected list and compare against the actual list.

Do not check only large tables. Small configuration tables, mapping tables, business permission tables, and status tables can matter even more for application correctness.

### 1.4. Defining acceptance criteria

Before running the migration, agree on:

- Which tables require exact row count equality?
- Which tables may differ due to post-snapshot activity?
- Which aggregates must match strictly?
- Which columns have rounding or timezone conversion rules?
- Are any temporary INVALID objects acceptable? If so, what is the list and remediation deadline?
- Which constraints must be ENABLED and VALIDATED?
- Who signs off functionally and who signs off technically?

Never define criteria after seeing discrepancies. Agree on criteria beforehand to avoid rationalizing mismatches.

## 2. Ensuring Source and Target Share the Same Snapshot

### 2.1. Snapshot consistency

A reconciliation is meaningful only when both sides represent the same time window. If the source keeps accepting transactions during export/import, source row counts at comparison time can exceed target counts even when migration lost zero data.

Common strategies:

- Freeze data writes during the migration window.
- Use Data Pump Flashback SCN or Flashback Time to export from a consistent snapshot.
- Use CDC/replication or delta exports to catch post-snapshot changes.
- Record watermarks or business cutoffs to reconcile data as of a boundary.

### 2.2. Capturing the source SCN

You can capture the current SCN:

```sql
SELECT current_scn
FROM v$database;
```

Record the SCN, timestamp, database identity, and cutoff time. An SCN is a consistency point within one database; SCNs from two independent databases do not automatically share meaning or allow direct comparison.

### 2.3. Exporting with FLASHBACK_SCN

Data Pump Export example:

```text
expdp system@SRCDB \
  schemas=APP \
  directory=DP_DIR \
  dumpfile=app_snapshot_%U.dmp \
  logfile=app_snapshot_exp.log \
  parallel=4 \
  flashback_scn=123456789
```

Replace the SCN placeholder with the actual value captured from source. Data Pump reads data at the specified snapshot SCN within supported bounds. Ensure enough UNDO remains available for consistent reads throughout the export; long exports can hit ORA-01555 if undo is insufficient.

### 2.4. FLASHBACK_TIME

You can use FLASHBACK_TIME to specify a timestamp; Data Pump converts it to the corresponding SCN. When exact reproducibility is required, record the actual SCN or capture the SCN explicitly before exporting.

### 2.5. Concurrent DDL and data changes

Flashback consistency for data does not mean all DDL changes are locked into a snapshot the way a DBA might assume. During the migration window, control DDL, grants, triggers, and schema changes. Log any unplanned changes.

### 2.6. Reconciling when the source remains active

If the source cannot be frozen for the entire migration:

1. Select an initial snapshot point.
2. Export data at that snapshot.
3. Capture changes occurring after the SCN via CDC, redo-based capture, or business watermarks.
4. Apply deltas to the target.
5. Enforce a write freeze or cutover barrier.
6. Re-reconcile deltas and control totals at cutover.

Never compare a target snapshot row count against a live source and conclude the migration lost data.

## 3. Pre/Post Table and Metadata Inventory

### 3.1. List of tables in the schema

On source and target, list tables:

```sql
SELECT owner,
       table_name,
       partitioned,
       temporary,
       nested,
       iot_type
FROM dba_tables
WHERE owner = 'APP'
ORDER BY table_name;
```

Compare both lists to spot missing, extra, or differently typed tables. Note that DBA_TABLES does not list every object type; also check views, materialized views, sequences, synonyms, triggers, packages, and related metadata.

### 3.2. NUM_ROWS is not an exact row count

NUM_ROWS in DBA_TABLES/ALL_TABLES/USER_TABLES comes from optimizer statistics. It is an estimate/value from the last statistics collection and may be stale or NULL. It does not update on every DML and is not an exact count.

Quick check example:

```sql
SELECT table_name, num_rows, last_analyzed, stale_stats
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND object_type = 'TABLE'
ORDER BY table_name;
```

Use NUM_ROWS for preliminary triage, not as final evidence when exact row counts are required.

### 3.3. Exact COUNT(*)

Count a table accurately:

```sql
SELECT COUNT(*) AS row_count
FROM app.orders;
```

COUNT(*) reads the necessary data to count and can consume I/O/CPU on large tables. Run on both source and target at a consistent snapshot. Never substitute COUNT(column), because COUNT(column) skips NULLs.

### 3.4. Counting by business group

A table can have identical total row counts yet wrong distribution. Count by status or business date:

```sql
SELECT order_status,
       COUNT(*) AS row_count
FROM app.orders
GROUP BY order_status
ORDER BY order_status;
```

Count by day:

```sql
SELECT TRUNC(created_at) AS business_day,
       COUNT(*) AS row_count
FROM app.orders
GROUP BY TRUNC(created_at)
ORDER BY business_day;
```

If `created_at` is TIMESTAMP WITH TIME ZONE, establish the business timezone before applying TRUNC or grouping by day. Never compare dates across different session timezones.

### 3.5. Counting by partition

For partitioned tables, check row counts per partition:

```sql
SELECT partition_name,
       num_rows,
       last_analyzed
FROM dba_tab_partitions
WHERE table_owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY partition_position;
```

These are partition statistics, not exact counts. When exact counts are needed, run COUNT(*) with a partition-key predicate or generate a script to count each partition. Partition pruning reduces scan scope when predicates align.

### 3.6. Generating a list of count queries

You can generate statements to execute sequentially:

```sql
SELECT 'SELECT ''' || table_name ||
       ''' AS table_name, COUNT(*) AS row_count FROM APP."' ||
       REPLACE(table_name, '"', '""') || '";' AS count_sql
FROM dba_tables
WHERE owner = 'APP'
  AND temporary = 'N'
  AND nested = 'NO'
ORDER BY table_name;
```

This script generates SQL for the DBA to review and run. For object names with special characters, quoted identifiers, clustered tables, or special objects, handle according to actual metadata. Never execute dynamic SQL from an unverified list.

### 3.7. Temporary and external tables

Global temporary tables hold session/transaction-scoped data and are normally excluded from persistent table reconciliation. External tables read from files outside the database; importing metadata does not mean external files were copied. Define separate validation and transfer steps for these objects.

### 3.8. Nested tables and IOTs

Nested table storage and index-organized tables have different structures from standard heap tables. Avoid mistaking internal storage tables for standalone business tables. Use metadata and schema design to define reconciliation units.

## 4. Row Counts: Interpretation and Special Cases

### 4.1. COUNT(*) vs. COUNT(column)

- COUNT(*) counts every row.
- COUNT(column) counts only rows where the column value is non-NULL.
- COUNT(DISTINCT column) counts distinct values, ignoring NULLs.

These three numbers answer different questions. When comparing data, record both total row counts and null counts of key columns.

### 4.2. Empty tables

COUNT(*) = 0 can be accurate if the table genuinely held zero rows at the snapshot. Also verify whether the table was imported, excluded by a filter, or modified by triggers/jobs post-import.

### 4.3. Large tables

For billion-row tables:

- Count by partition/key range to track progress and isolate mismatches.
- Use controlled parallel query if resources permit.
- Run during off-peak hours.
- Avoid creating contention with production workloads.
- Save per-partition results and aggregate afterward.

Example:

```sql
SELECT /*+ PARALLEL(o, 8) */
       COUNT(*) AS row_count
FROM app.orders o;
```

Degree 8 is illustrative only; weigh CPU, I/O, Resource Manager, and concurrent workloads.

### 4.4. Snapshot differs from query execution time

COUNT(*) on source at 10:00 and target at 10:30 cannot be compared if the source continues receiving DML. Use a freeze, flashback query at the proper SCN, or watermark/CDC-based reconciliation.

### 4.5. Row counts and duplicates

Two tables can share identical row counts while one has duplicate keys and missing keys. Therefore, verify:

- Unique/primary key duplicates.
- Missing keys.
- Unexpected extra keys.
- Null keys if a business key permits NULL.
- Cardinality across business dimensions.

### 4.6. Checking duplicate keys

```sql
SELECT order_id,
       COUNT(*) AS occurrences
FROM app.orders
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;
```

If a primary key is ENABLED VALIDATED, duplicates cannot exist under that constraint. However, constraints may be DISABLED or NOVALIDATE, so always inspect metadata.

## 5. Business Control Totals

### 5.1. Why aggregates are needed

Row counts measure volume only. Business aggregates validate content against business meaning. For instance, the ORDER table may have exactly 1 million rows while some amounts turned NULL, flipped sign, or received wrong statuses.

Common control totals:

- Total transaction count.
- Total monetary amount.
- Total item quantity.
- Order counts by status.
- Total tax/discount.
- Distinct customer or account counts.
- Min/max values and date ranges.
- Null counts on mandatory columns.
- Record counts by branch, tenant, currency, or business date.

### 5.2. Basic aggregates

```sql
SELECT COUNT(*)                    AS row_count,
       COUNT(order_id)             AS nonnull_order_id,
       COUNT(DISTINCT customer_id) AS distinct_customers,
       SUM(total_amount)           AS sum_amount,
       MIN(total_amount)           AS min_amount,
       MAX(total_amount)           AS max_amount,
       SUM(tax_amount)             AS sum_tax
FROM app.orders;
```

Compare each metric between source and target. SUM ignores NULLs; if all values are NULL, SUM returns NULL. Never coerce NULL to zero on one side without an explicit business rule.

### 5.3. Null counts

```sql
SELECT COUNT(*) AS total_rows,
       SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END)
           AS null_customer_id,
       SUM(CASE WHEN total_amount IS NULL THEN 1 ELSE 0 END)
           AS null_total_amount,
       SUM(CASE WHEN created_at IS NULL THEN 1 ELSE 0 END)
           AS null_created_at
FROM app.orders;
```

Null counts catch unintended conversion or defaulting bugs even when total row count and sum of amounts barely change.

### 5.4. Totals by date and status

```sql
SELECT TRUNC(created_at) AS business_day,
       order_status,
       COUNT(*) AS row_count,
       SUM(total_amount) AS amount_total,
       SUM(tax_amount) AS tax_total
FROM app.orders
GROUP BY TRUNC(created_at), order_status
ORDER BY business_day, order_status;
```

If business dates follow a specific timezone, convert timestamps to that timezone before grouping. Source and target must apply the exact same timezone rule.

### 5.5. Totals by currency

Never sum amounts across different currencies into a single combined total without converting at a standardized exchange rate and point in time:

```sql
SELECT currency_code,
       COUNT(*) AS row_count,
       SUM(total_amount) AS amount_total
FROM app.orders
GROUP BY currency_code
ORDER BY currency_code;
```

### 5.6. Totals by tenant or business unit

```sql
SELECT business_unit_id,
       COUNT(*) AS row_count,
       SUM(net_amount) AS net_total
FROM app.invoice
GROUP BY business_unit_id
ORDER BY business_unit_id;
```

Grouping isolates discrepancies to a specific business unit rather than merely showing a schema-wide total difference.

### 5.7. Rounding and numeric precision

When business logic uses rounding, determine whether totals are computed by:

- Summing per-row rounded values.
- Rounding after summing.
- Rounding according to currency scale.

These three approaches can yield different figures. Compare using the agreed business rule; never apply arbitrary tolerances to hide discrepancies.

### 5.8. Aggregates do not prove row-by-row equality

For example, source has amounts 100 and 200 while target has 150 and 150. Row counts match and SUM equals 300 on both, yet individual transactions differ. Thus, aggregates are high-level checks; critical tables need row-level diffs.

## 6. Data Checksums and Fingerprints

### 6.1. What is a checksum?

A checksum/fingerprint is a value computed from data contents to help detect differences. It can be computed per row, per partition, or per group. A sound checksum consistently represents:

- Column ordering.
- Data types.
- NULLs.
- Character encoding.
- Date/time formatting and timezones.
- NUMBER precision/scale.
- LOB contents.
- Data normalization rules.

### 6.2. Why simple checksums can mislead

Do not treat a simple SUM of a numeric column or ORA_HASH as absolute proof. Aggregation functions can collide:

- Swapping two values leaves SUM unchanged.
- Two different datasets can produce the same summed hash.
- ORA_HASH has a finite value space and is not a cryptographic hash.
- Concatenating strings without delimiters/length prefixes can yield identical strings for different tuples.
- NLS-dependent date/number formatting can yield different fingerprints across two databases for equivalent data.

Checksums are just one verification layer and must be paired with key-based comparisons and business totals.

### 6.3. Canonical representation

Before hashing, convert each value into a stable canonical representation:

- NUMBER: format decimal separator explicitly, independent of NLS_NUMERIC_CHARACTERS.
- DATE/TIMESTAMP: format precision and timezone rules explicitly.
- Character: define Unicode normalization/encoding if required by the application.
- NULL: represent distinctly without colliding with empty strings or sentinel values that could appear in real data.
- Fields: use length prefixes or safely escaped delimiters.
- LOB: hash the full content, not just the locator or length.

Do not trim whitespace, change casing, or normalize Unicode unless permitted by the business contract.

### 6.4. Per-row hash

For scalar columns, you can construct a canonical string per primary key and content, then apply a cryptographic hash. Illustrative example for a simple table:

```sql
SELECT order_id,
       STANDARD_HASH(
           NVL(TO_CHAR(customer_id), '<NULL>') || '|' ||
           NVL(TO_CHAR(total_amount,
               'FM999999999999990D999999',
               'NLS_NUMERIC_CHARACTERS=''.,'''), '<NULL>') || '|' ||
           NVL(TO_CHAR(created_at,
               'YYYY-MM-DD"T"HH24:MI:SS'), '<NULL>') || '|' ||
           NVL(order_status, '<NULL>'),
           'SHA256'
       ) AS row_hash
FROM app.orders;
```

This is an illustrative example, not a general-purpose canonical serializer. The `<NULL>` sentinel could collide with real data; the delimiter could appear inside strings; TO_CHAR format must match actual precision; TIMESTAMP WITH TIME ZONE needs explicit timezone handling. Production designs should use length-prefix/type tags or a thoroughly tested canonical serialization function.

### 6.5. STANDARD_HASH

STANDARD_HASH provides hash algorithms such as SHA1/SHA256/SHA384/SHA512 depending on release. It does not replace serialization. It has input data type limits; LOBs are not handled directly like standard VARCHAR2 expressions in every context. Check release documentation and use DBMS_CRYPTO or appropriate streaming functions for LOBs.

### 6.6. DBMS_CRYPTO

DBMS_CRYPTO can compute cryptographic hashes over RAW and LOBs in supported overloads. Verify package EXECUTE privileges and data types/encodings. For CLOBs, define explicitly how characters are encoded into bytes; for BLOBs, hash raw bytes as-is.

Conceptual PL/SQL example for an already-canonicalized CLOB:

```sql
DECLARE
    l_hash RAW(32);
    l_text CLOB;
BEGIN
    -- l_text must be produced by a serialization with stable rules.
    l_hash := DBMS_CRYPTO.HASH(
        src => l_text,
        typ => DBMS_CRYPTO.HASH_SH256
    );
    DBMS_OUTPUT.PUT_LINE(RAWTOHEX(l_hash));
END;
/
```

Adapt the snippet to your release's DBMS_CRYPTO overloads and LOB construction logic. Never use a short VARCHAR2 concatenation function to hash large data or truncated LOBs.

### 6.7. Hashing by partition or chunk

For very large tables, compute fingerprints by partition or key range:

1. Divide data into deterministic groups.
2. Compute row counts and business totals for each group.
3. Compute per-row/key hashes inside groups if needed.
4. Compare groups first to isolate discrepancies.
5. Run deep row-level diffs only on mismatched groups.

Chunks must have stable boundaries; never rely on ROWNUM without ORDER BY or physical row order.

### 6.8. Hashes are not security signatures

Hashing detects data differences. It does not replace HMACs/signatures for proving provenance or defending against intentional tampering. If cryptographic integrity proof is required, design a signing/hashing workflow with separate secret/key management.

## 7. Row-Level Comparison Between Source and Target

### 7.1. Comparing by primary key

When both databases have a database link, you can compare local target against remote source. Example:

```sql
SELECT t.order_id,
       t.total_amount AS target_amount,
       s.total_amount AS source_amount
FROM app.orders t
FULL OUTER JOIN app.orders@SRC_LINK s
  ON s.order_id = t.order_id
WHERE t.order_id IS NULL
   OR s.order_id IS NULL
   OR NVL(t.total_amount, -999999999) <>
      NVL(s.total_amount, -999999999);
```

This example illustrates only one numeric column. Sentinels must sit outside the valid value domain; production comparisons should handle NULLs explicitly, compare all important columns, and handle special data types/LOBs separately. For many columns, use DECODE or suitable null-safe expressions.

### 7.2. Null-safe comparison

DECODE treats two NULLs as equal and can be used for supported scalar types:

```sql
SELECT t.order_id
FROM app.orders t
JOIN app.orders@SRC_LINK s
  ON s.order_id = t.order_id
WHERE DECODE(t.customer_id, s.customer_id, 0, 1) = 1
   OR DECODE(t.order_status, s.order_status, 0, 1) = 1
   OR DECODE(t.total_amount, s.total_amount, 0, 1) = 1;
```

DECODE has data type limits and is not a direct comparison for all LOB/object types. For TIMESTAMP WITH TIME ZONE, decide whether to compare instants or region semantics before choosing the comparison operator.

### 7.3. Finding keys missing on the target

```sql
SELECT s.order_id
FROM app.orders@SRC_LINK s
WHERE NOT EXISTS (
    SELECT 1
    FROM app.orders t
    WHERE t.order_id = s.order_id
);
```

### 7.4. Finding extra keys on the target

```sql
SELECT t.order_id
FROM app.orders t
WHERE NOT EXISTS (
    SELECT 1
    FROM app.orders@SRC_LINK s
    WHERE s.order_id = t.order_id
);
```

### 7.5. Bidirectional MINUS

For scalar columns comparable with set operators:

```sql
SELECT order_id, customer_id, order_status, total_amount
FROM app.orders
MINUS
SELECT order_id, customer_id, order_status, total_amount
FROM app.orders@SRC_LINK;

SELECT order_id, customer_id, order_status, total_amount
FROM app.orders@SRC_LINK
MINUS
SELECT order_id, customer_id, order_status, total_amount
FROM app.orders;
```

Run in both directions to find rows present on only one side. MINUS eliminates duplicate rows and does not support all data types, notably LOBs. If multiplicity/duplicates matter, compare by primary key or GROUP BY all comparable columns with COUNT(*).

### 7.6. Comparing by hash

You can compute row hashes on both sides, join on primary key, and find differing hashes. This cuts down columns transmitted over the database link, though it still requires unified canonical serialization and computing hashes on the exact same snapshot.

### 7.7. Never use ROWID as a business key

ROWID can change after export/import, table move, reorganization, or rebuild. Always use a primary key or stable business key for reconciliation.

### 7.8. Tables without a primary key

If a table lacks a PK:

- Identify a business key from domain rules.
- Check duplicates on that key.
- If no stable key exists, compare multisets over comparable columns and occurrence counts.
- Consider adding a staging identifier before migration if permitted.

Never fabricate a synthetic key from ROW_NUMBER without a uniquely deterministic ORDER BY.

## 8. Reconciling Duplicates, Orphans, and Relationships

### 8.1. Duplicate keys

```sql
SELECT customer_id,
       COUNT(*) AS occurrences
FROM app.customer
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Run for critical primary/unique/business keys on both source and target.

### 8.2. Orphan foreign keys

Example checking orders referencing non-existent customers:

```sql
SELECT o.order_id,
       o.customer_id
FROM app.orders o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM app.customer c
      WHERE c.customer_id = o.customer_id
  );
```

Check on the target to catch inconsistent data after import, even when foreign keys are DISABLED.

### 8.3. Constraint status

```sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred
FROM dba_constraints
WHERE owner = 'APP'
ORDER BY table_name, constraint_name;
```

ENABLE NOVALIDATE is not equivalent to ENABLE VALIDATE. A NOVALIDATE constraint may enforce new DML without proving existing data satisfies the constraint. Migration sign-off must specify which states are acceptable.

### 8.4. Disabled constraints

A disabled constraint can allow the application to write invalid data. Compare constraint definitions between source and target, not just constraint counts.

### 8.5. Foreign key load order

Data Pump can import tables and constraints in appropriate order, yet filters, disabled constraints, or object errors can leave states incomplete. After import, re-verify ENABLED/VALIDATED statuses and orphan rows.

## 9. Indexes, Triggers, and Dependent Objects

### 9.1. Index status

```sql
SELECT owner,
       index_name,
       table_name,
       index_type,
       uniqueness,
       status,
       visibility
FROM dba_indexes
WHERE owner = 'APP'
ORDER BY table_name, index_name;
```

For partitioned indexes, also check DBA_IND_PARTITIONS and DBA_IND_SUBPARTITIONS, because the top-level index may not reflect every partition's state.

### 9.2. Unusable indexes

An index or index partition in UNUSABLE state can slow down queries or cause DML errors depending on index type. Identify the cause and rebuild per plan, especially for bitmap, function-based, domain, and partitioned indexes.

### 9.3. Trigger status

```sql
SELECT owner,
       trigger_name,
       table_name,
       status,
       triggering_event
FROM dba_triggers
WHERE owner = 'APP'
ORDER BY table_name, trigger_name;
```

Disabled triggers can break auditing, sequence assignment, denormalization, or business logic. Do not blindly enable every trigger if the migration intentionally disabled some; cross-check design and cutover plans.

### 9.4. Views and materialized views

Check status of views, materialized views, and refresh state. Materialized views may need refreshing after import; fast refresh may be unavailable if materialized view logs or dependencies are missing.

### 9.5. Synonyms and database links

Check synonym targets, database link definitions, and credential dependencies. An object can be VALID yet point to a non-existent service/schema or one unreachable from the target.

### 9.6. Grants and roles

Compare system/object privileges, role grants, default roles, and grants on procedures/packages. Data Pump can be configured to include/exclude grants; verify empirically rather than assuming.

### 9.7. Scheduler jobs

Inspect job metadata, enabled state, credentials, destinations, job classes, and next run dates. Never enable jobs that send emails, process payments, synchronize data, or call external systems until cutover is approved.

## 10. INVALID Objects After Migration

### 10.1. What is an INVALID object?

An INVALID object is a database object requiring compilation that is currently invalid. Common objects include:

- PACKAGE and PACKAGE BODY.
- PROCEDURE and FUNCTION.
- VIEW.
- TRIGGER.
- TYPE and TYPE BODY.
- MATERIALIZED VIEW.
- Certain Java/XML/feature-specific objects.

INVALID objects can result from missing dependencies, objects imported before their dependencies, insufficient privileges, data type differences, uninstalled features/components, mispointed synonyms, or release-incompatible source code.

### 10.2. Listing INVALID objects

```sql
SELECT owner,
       object_type,
       object_name,
       status,
       last_ddl_time
FROM dba_objects
WHERE owner = 'APP'
  AND status = 'INVALID'
ORDER BY object_type, object_name;
```

### 10.3. Counting INVALID objects by type

```sql
SELECT object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE owner = 'APP'
  AND status = 'INVALID'
GROUP BY object_type
ORDER BY object_type;
```

### 10.4. Viewing compile errors

```sql
SELECT owner,
       name,
       type,
       sequence,
       line,
       position,
       text
FROM dba_errors
WHERE owner = 'APP'
ORDER BY name, type, sequence;
```

DBA_ERRORS shows existing compile errors. For objects with zero error rows yet INVALID status, inspect dependencies, object types, and recompile to obtain diagnostics.

### 10.5. Dependencies

```sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP'
ORDER BY name, referenced_owner, referenced_name;
```

Dependencies may point to objects outside the schema, synonyms, or remote objects. Confirm target objects exist and required privileges are granted.

### 10.6. Component registry

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

If a database component is not installed or is INVALID, many system/feature-dependent objects may fail to compile. Do not repeatedly recompile the application schema if the root cause lies in the component registry.

## 11. Recompiling INVALID Objects

### 11.1. Compiling a single object

Procedure:

```sql
ALTER PROCEDURE app.refresh_summary COMPILE;
```

Package spec/body:

```sql
ALTER PACKAGE app.report_pkg COMPILE;
ALTER PACKAGE app.report_pkg COMPILE BODY;
```

View:

```sql
ALTER VIEW app.v_order_summary COMPILE;
```

Trigger:

```sql
ALTER TRIGGER app.trg_orders_audit COMPILE;
```

After compiling, re-query DBA_OBJECTS and DBA_ERRORS. A compile command succeeding at the SQL level does not mean all dependencies are healthy.

### 11.2. DBMS_UTILITY.COMPILE_SCHEMA

You can compile objects in a schema:

```sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema      => 'APP',
        compile_all => FALSE
    );
END;
/
```

Schema compilation can generate CPU load and dictionary activity. Run in an appropriate window and check object errors upon completion.

### 11.3. UTL_RECOMP

Oracle provides UTL_RECOMP to compile invalid objects in dependency order. Example:

```sql
BEGIN
    UTL_RECOMP.RECOMP_SERIAL('APP');
END;
/
```

Or compile in parallel in suitable environments:

```sql
BEGIN
    UTL_RECOMP.RECOMP_PARALLEL(
        degree  => 4,
        schema  => 'APP'
    );
END;
/
```

UTL_RECOMP is normally executed by DBA/SYS per privileges and Oracle guidance. Degree 4 is illustrative only; do not run excessive parallelism on a busy database.

### 11.4. utlrp.sql

After a database upgrade or major import, Oracle may require running the invalid-object compilation script:

```sql
@?/rdbms/admin/utlrp.sql
```

The script resides in Oracle Home and matches the release behavior. Run it in the proper database/container per upgrade guidelines. In CDB/PDB, identify which containers require compilation; running once in root does not necessarily replace operations inside each PDB.

### 11.5. Compiling does not fix logic bugs

An object that compiles as VALID can still:

- Call the wrong synonym or service.
- Contain outdated business logic.
- Lack runtime privileges.
- Raise runtime exceptions.
- Return different results due to NLS/timezone.

Therefore, smoke tests and application tests remain mandatory after compiling.

### 11.6. When not to compile everything

Do not blindly compile all objects if:

- Some objects are intentionally invalid in the deployment.
- External database dependencies are not built yet.
- The component registry is invalid.
- Objects are actively being altered by another deployment.
- Compilation could cause heavy system load.

Maintain an expected-invalid list and address each group by root cause.

## 12. Sequences and Identities After Migration

### 12.1. Why verify?

Sequences may fall out of sync with the highest imported key value. After cutover, an application calling NEXTVAL can generate an already-existing key and hit unique constraint violations.

### 12.2. Checking sequence metadata

```sql
SELECT sequence_owner,
       sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM dba_sequences
WHERE sequence_owner = 'APP'
ORDER BY sequence_name;
```

LAST_NUMBER reflects the cached/next dictionary value, not always the exact next NEXTVAL while caching is active. Never use LAST_NUMBER as absolute proof of the next issued value.

### 12.3. Comparing with MAX(primary key)

```sql
SELECT MAX(order_id) AS max_order_id
FROM app.orders;
```

Compare against the corresponding sequence and increment direction. For ascending sequences, the next issued value must exceed existing keys per policy. For descending sequences, cycling sequences, or sequences shared across tables, analyze individually.

### 12.4. Never call NEXTVAL just to check

NEXTVAL advances the sequence and cannot be rolled back. Never invoke NEXTVAL casually on production just to inspect it. Use a test sequence or a maintenance procedure that accounts for consumed values.

### 12.5. Identity columns

Check:

```sql
SELECT owner,
       table_name,
       column_name,
       generation_type,
       sequence_name
FROM dba_tab_identity_cols
WHERE owner = 'APP'
ORDER BY table_name, column_name;
```

Identity columns use internal sequences; do not manage them like standard application sequences without understanding how Oracle attaches identity metadata. Test insert behavior after import and never assume internal sequence names stay identical across releases.

## 13. LOBs, Indexes, Constraints, and Special Data

### 13.1. LOB columns

Check tables with CLOB/BLOB/NCLOB/BFILE:

```sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length
FROM dba_tab_columns
WHERE owner = 'APP'
  AND data_type IN ('CLOB', 'BLOB', 'NCLOB', 'BFILE')
ORDER BY table_name, column_id;
```

LOB reconciliation requires checking lengths and contents/hashes; row counts are not enough. BFILE stores only a locator/path to an external file outside the database, not proving the file itself was copied.

### 13.2. LOB segment metadata

DBA_LOBS and DBA_LOB_PARTITIONS show segment/tablespace and storage metadata. Verify SecureFiles/BasicFiles, compression, deduplication, encryption, and tablespace mappings if altered during migration.

### 13.3. Index status and usability

INVALID/UNUSABLE indexes can degrade queries or break DML. For partitioned indexes, inspect every partition/subpartition:

```sql
SELECT index_owner,
       index_name,
       partition_name,
       status
FROM dba_ind_partitions
WHERE index_owner = 'APP'
ORDER BY index_name, partition_position;
```

### 13.4. Constraint validation

Check primary keys, unique keys, foreign keys, check constraints, and ENABLED/VALIDATED status. A constraint that exists yet is DISABLED does not enforce data correctness.

### 13.5. Trigger side effects

Triggers may be disabled during loading to boost speed. After import, determine which triggers must be enabled, which must not fire retroactively on legacy data, and which might trigger side effects when enabled.

### 13.6. Materialized views

Check compile status, staleness, refresh mode, and materialized view logs. Refreshing can generate heavy load or alter results; refresh only after confirming dependencies and business cutoffs.

## 14. Automating Reconciliation

### 14.1. Reconciliation manifest

Create a manifest with one row per table/reconciliation unit:

| Field | Contents |
|---|---|
| Schema/table | Object name |
| Snapshot ID | SCN or business cutoff |
| Source count | Exact count |
| Target count | Exact count |
| Count delta | Target minus source |
| Business totals | Key aggregates |
| Checksum version | Canonicalization/hash rules |
| Mismatch count | Count of differing keys/rows |
| Status | PASS/FAIL/EXCEPTION |
| Evidence | Query ID, log path, timestamp |

Never record only PASS/FAIL without preserving queries, snapshots, and evidence for reproducibility.

### 14.2. Status semantics

- PASS: all agreed criteria are met.
- FAIL: unexplained mismatch or object fails requirements.
- EXCEPTION: discrepancy accepted by business via formal explicit approval.
- NOT_RUN: not yet executed.

EXCEPTION requires an owner, reason, impact, expiry, and evidence; never use exceptions to mask unexecuted checks.

### 14.3. Running by priority tier

Prioritize checking:

1. Critical transaction tables.
2. Master/configuration tables.
3. Balance/ledger/financial control tables.
4. Relational and mapping tables.
5. Large audit/history tables.
6. Low-criticality tables or regenerable data.

Prioritization catches cutover-blocking issues earlier.

### 14.4. Controlled parallel execution

Tables or partitions can be divided across workers, provided source/target are not overloaded. Consider:

- CPU and I/O capacity.
- Database link bandwidth.
- Undo/redo generation.
- Locking and concurrency.
- Resource Manager.
- Result set size and temp usage.

### 14.5. Never compare over actively changing data

If source/target continue accepting writes, the manifest can mix figures from different points in time. Tag every result with a snapshot ID and never combine metrics from different snapshots into a PASS report.

## 15. End-to-End Reconciliation Workflow

### Phase A — Pre-migration

1. Lock in schema/table/object scope.
2. Collect Oracle release, character sets, timezone file, and COMPATIBLE.
3. Record baseline row counts/aggregates.
4. Identify primary/business keys.
5. Define business control totals.
6. Inventory objects, grants, constraints, indexes, triggers, and sequences.
7. Choose snapshot/SCN and freeze/delta strategy.
8. Agree on acceptance criteria.

### Phase B — During migration

1. Capture SCN or enforce write freeze.
2. Run export and retain logs/parameter files.
3. Transfer dumps/datafiles over controlled channels.
4. Run import/transport.
5. Save import logs and all warnings/errors.
6. Apply deltas if applicable.
7. Keep source in a rollback-capable state per plan.

### Phase C — Technical reconciliation

1. Compare object inventories.
2. Run exact COUNT(*) by table/partition.
3. Compare aggregates across business dimensions.
4. Compare keys and row values bidirectionally.
5. Check duplicates/orphans.
6. Check LOB contents/lengths.
7. Check constraints/indexes/triggers.
8. List INVALID objects and compile by root cause.
9. Check sequences/identities.
10. Check grants, synonyms, database links, and Scheduler jobs.

### Phase D — Application testing

1. Smoke test logins/connectivity.
2. Execute critical read/write flows.
3. Verify reports and business totals.
4. Test batch/Scheduler jobs.
5. Verify timestamps, timezones, and Unicode.
6. Monitor application errors and performance.

### Phase E — Cutover sign-off

1. Confirm all critical tables PASS.
2. Account for every delta and exception.
3. Close out required INVALID objects.
4. Confirm constraint/index/sequence states.
5. Obtain DBA and business owner sign-off.
6. Open traffic per plan.
7. Monitor post-cutover.
8. Release source/backup/rollback paths only after the approved holding period.

## 16. Sample Reconciliation Query Suite

### 16.1. Row count

Run on source and target at the same snapshot:

```sql
SELECT COUNT(*) AS orders_count
FROM app.orders;
```

### 16.2. Business totals

```sql
SELECT currency_code,
       order_status,
       COUNT(*) AS row_count,
       SUM(total_amount) AS amount_total,
       SUM(tax_amount) AS tax_total,
       MIN(created_at) AS first_created,
       MAX(created_at) AS last_created
FROM app.orders
GROUP BY currency_code, order_status
ORDER BY currency_code, order_status;
```

### 16.3. Null counts

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(*) - COUNT(customer_id) AS null_customer_id,
       COUNT(*) - COUNT(total_amount) AS null_total_amount,
       COUNT(*) - COUNT(order_status) AS null_order_status
FROM app.orders;
```

### 16.4. Missing keys

```sql
SELECT s.order_id
FROM app.orders@SRC_LINK s
WHERE NOT EXISTS (
    SELECT 1
    FROM app.orders t
    WHERE t.order_id = s.order_id
);
```

### 16.5. Different values

```sql
SELECT s.order_id
FROM app.orders@SRC_LINK s
JOIN app.orders t
  ON t.order_id = s.order_id
WHERE DECODE(t.customer_id, s.customer_id, 0, 1) = 1
   OR DECODE(t.order_status, s.order_status, 0, 1) = 1
   OR DECODE(t.total_amount, s.total_amount, 0, 1) = 1;
```

### 16.6. Invalid objects

```sql
SELECT object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE owner = 'APP'
  AND status = 'INVALID'
GROUP BY object_type
ORDER BY object_type;
```

### 16.7. Compile errors

```sql
SELECT name, type, line, position, text
FROM dba_errors
WHERE owner = 'APP'
ORDER BY name, type, sequence;
```

### 16.8. Constraints not enabled and validated

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE owner = 'APP'
  AND (status <> 'ENABLED' OR validated <> 'VALIDATED')
ORDER BY table_name, constraint_name;
```

### 16.9. Unusable indexes

```sql
SELECT index_name, table_name, status
FROM dba_indexes
WHERE owner = 'APP'
  AND status <> 'VALID'
ORDER BY table_name, index_name;
```

### 16.10. Disabled triggers

```sql
SELECT trigger_name, table_name, status
FROM dba_triggers
WHERE owner = 'APP'
  AND status = 'DISABLED'
ORDER BY table_name, trigger_name;
```

## 17. Mismatch Reporting and Investigation

### 17.1. Classifying mismatches

Classify each mismatch:

- MISSING_TARGET: row present on source but missing on target.
- EXTRA_TARGET: row present on target but missing on source.
- VALUE_MISMATCH: same key yet differing contents.
- COUNT_MISMATCH: differing row counts.
- AGGREGATE_MISMATCH: differing business totals.
- METADATA_MISMATCH: missing or differing objects/constraints/indexes.
- INVALID_OBJECT: object fails to compile.
- EXPECTED_DELTA: discrepancy anticipated due to snapshot/cutover timing.

### 17.2. Investigating by impact

Prioritize:

1. Financial totals or ledger imbalances.
2. Missing transaction/master data.
3. Duplicate keys and orphan references.
4. Timestamp/character conversions.
5. Invalid code paths and disabled triggers.
6. Index/statistics/performance issues.
7. Discrepancies in regenerable tables.

### 17.3. Recording root cause

For each mismatch, document:

- Object and key or partition.
- Source/target snapshot.
- Source/target values.
- Reproduction query.
- Affected count.
- Root cause.
- Remediation/reload method.
- Re-reconciliation result.
- Approver if accepted as an exception.

### 17.4. Do not modify target before saving evidence

If discrepancies are found, save results and logs before fixing. After reloading/correcting, rerun the exact reconciliation query at the proper snapshot. Never delete mismatch reports simply because the target has been patched.

## 18. Common Pitfalls

### 18.1. Using NUM_ROWS instead of COUNT(*)

NUM_ROWS can be stale or merely a statistics estimate. Use exact counts for critical tables.

### 18.2. Comparing live source with target snapshot

Source may receive DML after export. Stamp snapshot SCN or business watermarks onto reports.

### 18.3. Comparing only total row counts

A table can simultaneously miss rows and have extra rows totaling the same count. Compare keys and row contents.

### 18.4. Comparing only SUM

Two distinct sets of values can share the same sum. Compare by groups and at the row level.

### 18.5. Treating ORA_HASH as an absolute checksum

ORA_HASH is not a cryptographic hash and has collisions. Never use a single summed ORA_HASH to declare data identical.

### 18.6. MINUS on tables with duplicates

MINUS removes duplicates. If multiplicity matters, compare by key or GROUP BY with COUNT.

### 18.7. Ignoring NULLs

SUM, COUNT(column), and MIN/MAX ignore NULLs. Check null counts explicitly.

### 18.8. Not normalizing timezones

Two timestamps can represent the same instant yet display different timezones, or show the same local time yet represent different instants. Decide whether to compare instants or business-local times.

### 18.9. NLS-dependent string hashing

TO_CHAR on numbers/dates without explicit format masks and NLS parameters can yield different hashes across source/target.

### 18.10. Object VALID yet fails at runtime

A compiled object can still lack privileges, point to a wrong synonym, or call a missing database link. Run application smoke tests.

### 18.11. Unclassified INVALID objects

Some objects may be intentionally INVALID during deployment; others are real defects. Compare against baselines/expected lists and document exceptions explicitly.

### 18.12. Overlooking sequences

Row counts and constraints may all pass while sequences sit below MAX(primary key). Verify before opening write traffic.

## 19. Migration Reconciliation Practice Lab

Perform in two lab schemas holding identical data, then deliberately introduce minor mismatches to practice detection. Never run test DML in production.

### Step 1 — Prepare tables

Create an orders table with primary key, customer_id, status, amount, currency, and created_at. Load sample data into source, then export/import to target.

### Step 2 — Lock in snapshot

Record source's current SCN or pause writes in the lab. Document timestamp and database identity.

### Step 3 — Count exact rows

Run COUNT(*) on source and target. Record results in a manifest.

### Step 4 — Count by status/date

Run GROUP BY status and business date. Identify any differing groups.

### Step 5 — Compute business totals

Compare SUM(amount), SUM(tax), COUNT(DISTINCT customer_id), null counts, and MIN/MAX dates by currency.

### Step 6 — Introduce deliberate mismatches

In the target lab, alter the amount on one order, delete one row, and insert a different row. Keep total row count equal to source to simulate a case where total row counts fail to detect discrepancies.

### Step 7 — Find missing/extra keys

Run bidirectional NOT EXISTS or FULL OUTER JOIN on PK. Record missing and extra keys.

### Step 8 — Find value mismatches

Join on PK and use null-safe comparisons across scalar columns. Count mismatched rows.

### Step 9 — Check duplicates/orphans

Deliberately create a duplicate or orphan in the lab when constraints permit, then run detection queries. Restore data after testing.

### Step 10 — Create an INVALID object

In the lab schema, create a view/procedure depending on a non-existent object or break a dependency so it compiles INVALID. Inspect DBA_OBJECTS and DBA_ERRORS.

### Step 11 — Compile and verify

Fix the dependency, compile the object, verify VALID status, and test execution logic. Do not rely on status alone.

### Step 12 — Check sequences

Compare MAX(primary key) against sequence policy. Do not invoke NEXTVAL on business sequences unnecessarily.

### Step 13 — Finalize manifest

Record source/target counts, aggregates, mismatch counts, invalid objects, exceptions, and evidence.

## 20. Migration Sign-Off Checklist

- [ ] Accurately defined schema/table/object scope.
- [ ] Recorded snapshot SCN or business cutoff.
- [ ] Compared source and target over the same time window.
- [ ] Ran exact COUNT(*) for critical tables.
- [ ] Compared row counts across partitions/business dimensions.
- [ ] Used NUM_ROWS only as reference statistics.
- [ ] Compared business totals by currency/status/date/tenant.
- [ ] Checked null counts and distinct counts.
- [ ] Checked key-level missing/extra rows bidirectionally.
- [ ] Listed and resolved value mismatches.
- [ ] Documented checksum canonicalization/version.
- [ ] Did not use standalone SUM/ORA_HASH as complete proof.
- [ ] Checked duplicate keys and orphan references.
- [ ] Constraints are ENABLED/VALIDATED as required.
- [ ] No UNUSABLE indexes or index partitions outside approved exceptions.
- [ ] Trigger statuses match cutover plan.
- [ ] Checked LOB contents/lengths and BFILE external files.
- [ ] Checked views/materialized views and dependencies.
- [ ] Listed, classified, compiled/tested INVALID objects.
- [ ] No unexplained errors in DBA_ERRORS on critical objects.
- [ ] DBA_REGISTRY components in required states.
- [ ] Sequences/identities not below the next key range to issue.
- [ ] Confirmed grants, roles, synonyms, database links, and directory objects.
- [ ] Scheduler jobs/credentials enabled at the proper time.
- [ ] Passed application smoke tests and business tests.
- [ ] Every exception has an owner, impact, and approval.
- [ ] Signed off report/evidence and rollback decision.

## 21. Self-Check Questions

1. Why is a successful Data Pump import insufficient to declare migration complete?
2. What does snapshot consistency mean when reconciling source and target?
3. How does FLASHBACK_SCN assist Data Pump Export?
4. Why can SCNs from two independent databases not be compared directly?
5. How does NUM_ROWS differ from COUNT(*)?
6. How does COUNT(*) differ from COUNT(column)?
7. Why count by partition and business dimension?
8. What defects can identical row counts conceal?
9. Which metrics should business control totals include?
10. Why must monetary totals be grouped by currency?
11. How does per-row rounding differ from post-sum rounding?
12. Why do identical aggregates not prove row-level equality?
13. Which data types must a checksum canonicalize?
14. Why is ORA_HASH not a cryptographic checksum?
15. Why can delimiters and NULL sentinels make serialization ambiguous?
16. What roles do STANDARD_HASH and DBMS_CRYPTO play?
17. When should LOBs be hashed using streaming mechanisms?
18. Why compare by primary/business key instead of ROWID?
19. What limitations does bidirectional MINUS have with duplicates and LOBs?
20. How do you find missing keys and extra keys?
21. Why check duplicate keys and orphan foreign keys?
22. How does ENABLE NOVALIDATE differ from ENABLE VALIDATE?
23. How do DBA_OBJECTS and DBA_ERRORS help locate INVALID objects?
24. How does DBA_REGISTRY relate to compilation failures?
25. When are DBMS_UTILITY.COMPILE_SCHEMA and UTL_RECOMP used?
26. Why is compiling to VALID insufficient for sign-off?
27. Is sequence LAST_NUMBER always the exact next NEXTVAL?
28. How should identity columns be checked after import?
29. Which objects beyond table data must be verified after migration?
30. What evidence should a migration sign-off report retain?

**Key principle to remember:** Reconciliation is valid only when source and target represent the same snapshot or a controlled delta. Exact row counts verify completeness; business totals verify distribution and meaning; key-based diffs find missing/extra/differing rows; metadata checks confirm constraints, indexes, triggers, sequences, and object states. NUM_ROWS is statistics, and standalone SUM or ORA_HASH is never complete proof. Classify and fix every mismatch, compile/test INVALID objects, verify sequences before opening production writes, and archive evidence alongside sign-off.
