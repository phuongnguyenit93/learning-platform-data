# Data Movement and Migration

## Reconciling Row Counts, Checksums, and Business Invariants

After loading data into a new MySQL server, an import command finishing with exit code 0 is not enough to conclude the data transferred accurately. Some rows may be missing or duplicated, values may have been type-converted, table relationships may be broken, or monetary totals and inventory balances may no longer match business reality. Reconciliation requires multiple verification layers to catch both technical discrepancies and application-meaningful mismatches.

In the **DATABASE_MYSQL** module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, tuning queries, authorization, backups, and handling relational database operational issues. These skills help you verify data after export/import, restore, or system migration: knowing which transactions belong to the same snapshot, which keys identify a row, and which business rules must hold invariant.

This lesson builds a reconciliation workflow spanning row counts, keys, range-based checksums/hashes, aggregates, and business invariants. Examples use orders, order items, payments, and inventory tables; adapt formulas to your system's real rules.

### 1. What Questions Must Reconciliation Answer?

Post-migration data reconciliation should answer at least five questions:

1. **Are counts complete?** Are any rows, tables, partitions, or objects missing or extra?
2. **Are identities right?** Are primary keys and business keys complete, unique, and mapped accurately?
3. **Do values match?** Were important columns truncated, re-encoded, rounded, or timezone-shifted?
4. **Are relationships intact?** Are foreign keys, parent-child links, and business associations unbroken?
5. **Are business results valid?** Do order totals, payments, balances, inventory, and ledgers preserve defined invariants?

No single check answers all five questions. Two tables with the same `COUNT(*)` can still contain different sets of primary keys. Two tables with identical monetary totals can still miss one order and carry an extra order of equal value. A matching aggregate checksum likewise does not substitute for checking relationships and business rules.

### 2. Lock a Common Data Checkpoint Before Comparing

Comparing source and target is meaningful only when both sides represent the same logical state. If the source keeps taking writes while you count rows, while the target was imported from an older backup, discrepancies may simply be valid transactions committed after the snapshot.

#### 2.1. Using a Consistent Snapshot with InnoDB

On a source read connection, you can open a consistent snapshot at `REPEATABLE READ` isolation:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) FROM appdb.orders;
SELECT COUNT(*) FROM appdb.order_items;
SELECT SUM(total_amount) FROM appdb.orders;

COMMIT;
```

InnoDB consistent reads inside this transaction see the exact same snapshot. Run all queries to reconcile within the same transaction and connection. This snapshot excludes changes committed after the snapshot was established.

`START TRANSACTION WITH CONSISTENT SNAPSHOT` applies to InnoDB and appropriate isolation levels; it does not automatically create a distributed snapshot across two independent servers. If querying across multiple connections or systems, coordinate the data checkpoint explicitly.

#### 2.2. Choosing a Watermark for Live-Write Migrations

For systems still taking writes, a common workflow is:

1. Take a full backup or consistent snapshot and record its metadata.
2. Record the binlog/GTID coordinates matching the snapshot per the backup tool.
3. Load the snapshot into the target.
4. Replay post-snapshot changes via replication or CDC.
5. At cutover, block new writes, drain in-flight transactions, and capture a final watermark.
6. Wait for the target to apply up to the watermark; then reconcile on a stable state.

With GTID, use `WAIT_FOR_EXECUTED_GTID_SET()` on the target to wait for the transaction set recorded on the source to finish executing. With file/position, use coordinates supplied by the backup or CDC tool. Never grab binary log status at an arbitrary moment and treat it as the coordinate of an earlier snapshot.

If writes cannot be paused or changes caught up completely, clearly define the reconciliation window and classify deltas occurring after the watermark. Never alter target data just to make two totals temporarily match.

### 3. Checking Row Counts and Data Scope

#### 3.1. Exact Counting

For InnoDB tables, `COUNT(*)` gives an exact count as of the query's snapshot:

```sql
SELECT COUNT(*) AS order_count
FROM appdb.orders;

SELECT COUNT(*) AS item_count
FROM appdb.order_items;
```

`INFORMATION_SCHEMA.TABLES.TABLE_ROWS` is typically an estimate for InnoDB. Use it to gauge scale, not as exact reconciliation proof.

Also check non-`NULL` primary keys and distinct keys:

```sql
SELECT
  COUNT(*) AS total_rows,
  COUNT(order_id) AS nonnull_order_ids,
  COUNT(DISTINCT order_id) AS distinct_order_ids
FROM appdb.orders;
```

If `order_id` is the primary key, these counts must match the schema definition. For tables lacking a primary key, identify a business key or column combination that uniquely identifies each record; without a stable key, row-by-row reconciliation is harder and requires custom rules.

#### 3.2. Counting by Business Partitions

Full-table counts can hide offsetting discrepancies across groups. Break counts down by date, status, tenant, or partition:

```sql
SELECT
  DATE(created_at) AS order_date,
  status,
  COUNT(*) AS row_count
FROM appdb.orders
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
```

Compare identical groups across source and target. If total orders match yet one day is short 100 orders and another day has 100 extra, partitioned counts expose the discrepancy.

For large partitioned tables, filter on the partition key and primary key to split into stable chunks. Example:

```sql
SELECT COUNT(*) AS chunk_rows,
       MIN(order_id) AS min_id,
       MAX(order_id) AS max_id
FROM appdb.orders
WHERE order_id >= 100000
  AND order_id < 110000;
```

Chunk boundaries should be non-overlapping, gap-free, and anchored on a stable key. Avoid paginating with `LIMIT offset` on large tables because growing offsets are expensive and unstable when data changes.

#### 3.3. Finding Missing or Extra Keys

When both schemas are queryable within one MySQL instance, use an anti-join to find keys present on only one side:

```sql
-- Present in source but missing in target.
SELECT s.order_id
FROM source_db.orders AS s
LEFT JOIN target_db.orders AS t
  ON t.order_id = s.order_id
WHERE t.order_id IS NULL;

-- Present in target but missing in source.
SELECT t.order_id
FROM target_db.orders AS t
LEFT JOIN source_db.orders AS s
  ON s.order_id = t.order_id
WHERE s.order_id IS NULL;
```

If source and target live on separate servers, export key lists or chunk hashes to files or staging tables and compare using data-movement tools. Never assume MySQL can join directly across two independent servers unless remote access mechanisms are configured.

Check for duplicate business keys:

```sql
SELECT external_order_no, COUNT(*) AS occurrences
FROM appdb.orders
GROUP BY external_order_no
HAVING COUNT(*) > 1;
```

A surrogate key may be unique in each database while a business key is duplicated due to faulty mapping or repeated imports. Verify both technical keys and business identifiers.

### 4. Aggregate Checks and Checksums

#### 4.1. Aggregating Key Columns

Supplement row counts with sums, min/max values, and data distributions:

```sql
SELECT
  COUNT(*) AS order_count,
  COUNT(DISTINCT customer_id) AS customer_count,
  COALESCE(SUM(total_amount), 0) AS total_order_amount,
  MIN(created_at) AS first_order_at,
  MAX(created_at) AS last_order_at
FROM appdb.orders;
```

Compare further by status:

```sql
SELECT
  status,
  COUNT(*) AS order_count,
  COALESCE(SUM(total_amount), 0) AS total_amount
FROM appdb.orders
GROUP BY status
ORDER BY status;
```

Aggregates surface discrepancies fast, though they do not prove individual rows match. Use them as a screening layer before drilling into specific keys and values.

#### 4.2. Data Type and Normalization Considerations

Two values can only be compared reliably once their representation rules match:

- **Currency:** use `DECIMAL` with appropriate precision/scale; avoid summing monetary values with `FLOAT` or `DOUBLE` when exact reconciliation is required.
- **`NULL`:** distinguish `NULL` from empty strings, zero, and default values. `SUM()` returns `NULL` when given no input rows; use `COALESCE()` when business rules define an empty sum as 0.
- **Temporal values:** align session time zones. `TIMESTAMP` converts across session time zones; `DATETIME` stores literal date-times without session conversion. Never compare two temporal columns before establishing UTC vs. local-time conventions.
- **Strings:** check charset, collation, case sensitivity, accents, trailing spaces, and Unicode normalization rules. Two strings considered equal by a collation do not necessarily share identical bytes.
- **Integers:** verify signed/unsigned and value ranges; out-of-range values may fail or coerce depending on SQL mode.
- **JSON:** compare logical content per application schema; do not assume byte serialization across versions or tools is identical.
- **Generated/default values:** inspect generated columns, defaults, triggers, and time expressions. Imports can generate different values if data or session context is not preserved.

Record `sql_mode`, charset/collation, and time zone used throughout export/import. If source and target follow different rules, normalize explicitly before computing checksums.

#### 4.3. CHECKSUM TABLE and Its Limitations

MySQL provides the command:

```sql
CHECKSUM TABLE appdb.orders;
```

This command can be helpful when comparing two compatible tables in the same environment, but it is not a universal logical checksum across all engines and versions. Support and results can depend on storage engine, table structure, and implementation details. Never rely on a single table checksum as sole proof that data moved accurately across different engines or versions.

Tools such as `pt-table-checksum` from Percona Toolkit can chunk tables and help detect drift in replication topologies. Before using it, review tool version, privileges, query load, replication/filter settings, and topology-specific guidance. Checksum tools also require a comparable data state; they do not replace watermarks and business checks.

### 5. Per-Row Hashing and Chunk Reconciliation

When you need to pinpoint which values differ, compute a hash over a canonicalized representation of important columns and compare by primary key.

Illustrative example for `orders`:

```sql
SELECT
  order_id,
  SHA2(
    CONCAT(
      IF(customer_code IS NULL,
         'N;',
         CONCAT('V', OCTET_LENGTH(CAST(customer_code AS BINARY)),
                ':', HEX(CAST(customer_code AS BINARY)), ';')),
      IF(status IS NULL,
         'N;',
         CONCAT('V', OCTET_LENGTH(CAST(status AS BINARY)),
                ':', HEX(CAST(status AS BINARY)), ';')),
      IF(total_amount IS NULL,
         'N;',
         CONCAT('V', CAST(total_amount AS CHAR), ';')),
      IF(created_at IS NULL,
         'N;',
         CONCAT('V', DATE_FORMAT(created_at,
                 '%Y-%m-%dT%H:%i:%s.%f'), ';'))
    ),
    256
  ) AS row_hash
FROM appdb.orders
WHERE order_id >= 100000
  AND order_id < 110000
ORDER BY order_id;
```

The example uses an `N` marker for `NULL` and a `V` marker for present values; strings are HEX-encoded with byte length to avoid ambiguity if delimiters appear inside data. `DECIMAL` values are cast to string at column scale. Before comparing `TIMESTAMP`, set identical time zones—such as `SET time_zone = '+00:00'` on both sessions; for `DATETIME`, agree on business time zone meaning. Include all meaningful columns in the payload and use the exact same expression on both sides.

Hashing requires a clear canonicalization design:

- Include meaningful columns; omit environment-specific columns whose values are allowed to differ.
- Define representations for `NULL`, strings, numbers, temporal types, and JSON.
- Use identical column order and expressions on source and target.
- Include or key hashes by primary key so you know which exact row differs.
- To verify exact bytes, hash raw bytes; to verify logical values, canonicalize per agreed rules.

Do not compute just a single aggregate hash for the entire table. Partition by key range or table partition, compare row counts and hashes per chunk, and drill down to primary keys in mismatching chunks. Pairs of `(chunk_id, row_count, digest)` can be stored in staging tables for reporting.

Aggregate digests like `BIT_XOR(CRC32(...))` work as a fast screen but carry collision risk and do not prove byte-for-byte identity. `GROUP_CONCAT()` over all hashes can hit `group_concat_max_len`, consume excessive memory, and silently truncate results. For strict checks, compare keyed SHA-256 hashes or inspect rows individually inside suspect chunks.

Hashes are only as trustworthy as their canonicalization. If both sides use different collations yet you hash raw string bytes, results can differ even when SQL considers values equal; conversely, over-normalizing can mask byte differences that should have been preserved. State clearly whether the goal is byte-level or business-value comparison.

### 6. Checking Relationships and Referential Integrity

A table with the right row count can still contain foreign keys whose parent rows are missing. For `orders` and `order_items`, check:

```sql
SELECT COUNT(*) AS orphan_item_count
FROM appdb.order_items AS i
LEFT JOIN appdb.orders AS o
  ON o.order_id = i.order_id
WHERE o.order_id IS NULL;
```

The result must be 0 if every line item must belong to an order. Repeat for key relationships such as payment-to-order, shipment-to-order, invoice-to-customer, and inventory movement-to-product.

Check duplicate business keys, unexpected `NULL`s, invalid statuses, and out-of-range values:

```sql
SELECT COUNT(*) AS invalid_amount_count
FROM appdb.orders
WHERE total_amount < 0;

SELECT COUNT(*) AS missing_customer_count
FROM appdb.orders
WHERE customer_id IS NULL;
```

Conditions must reflect business rules. For example, refund orders might legitimately carry negative totals if the data model permits them; in that case `total_amount < 0` is not automatically an error. Document valid states and exceptions before flagging discrepancies.

### 7. Reconciling Business Invariants

Business invariants are cross-data relationships that must hold even across multiple tables. This verification layer is vital because an import can preserve row counts while corrupting relationships or values.

#### 7.1. Orders and Order Items

If `subtotal` is defined as the sum of `quantity * unit_price` before tax, discounts, and shipping, verify:

```sql
SELECT
  o.order_id,
  o.subtotal,
  COALESCE(SUM(i.quantity * i.unit_price), 0) AS calculated_subtotal
FROM appdb.orders AS o
LEFT JOIN appdb.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.subtotal
HAVING o.subtotal <> calculated_subtotal;
```

In production systems, account for line-level/order-level discounts, taxes, fees, rounding, and cancelled orders per exact product rules. When money is stored as `DECIMAL`, calculation expressions must preserve appropriate precision/scale.

A general formula might be:

**order_total = item_subtotal - discount + tax + shipping_fee**

Apply this only if it accurately reflects your product rules. Never guess rounding order or discount allocation logic.

#### 7.2. Payments, Refunds, and Receivables

Payment reconciliation must distinguish `AUTHORIZED`, `CAPTURED`, `SETTLED`, `REFUNDED`, `VOIDED`, and `CHARGEBACK` states. An authorized transaction has not necessarily collected funds; refunds may be partial or occur multiple times.

For example, if the model stores each capture/refund as a row with a positive amount and explicit status:

```sql
SELECT
  order_id,
  SUM(
    CASE
      WHEN status IN ('CAPTURED', 'SETTLED') THEN amount
      WHEN status = 'REFUNDED' THEN -amount
      ELSE 0
    END
  ) AS net_collected
FROM appdb.payments
GROUP BY order_id;
```

Compare `net_collected` against collected amounts in business ledgers or order statuses. Adjust the formula if refunds live in a separate table, amounts are signed, settlements deduct fees, or chargebacks follow accounting periods.

For double-entry ledgers, total debits and credits must balance per journal/batch and currency:

```sql
SELECT journal_id, currency,
       SUM(debit_amount) AS total_debit,
       SUM(credit_amount) AS total_credit
FROM appdb.ledger_lines
GROUP BY journal_id, currency
HAVING SUM(debit_amount) <> SUM(credit_amount);
```

Never sum different currencies into a single total without converting using defined exchange rates and effective timestamps.

#### 7.3. Inventory and Stock Movements

If the model computes inventory from an opening balance and movements:

**on_hand = opening_balance + receipts - shipments + adjustments**

reconcile the recalculated balance against the current balance table. Example:

```sql
SELECT
  b.product_id,
  b.warehouse_id,
  b.on_hand,
  COALESCE(SUM(
    CASE
      WHEN m.movement_type = 'RECEIPT' THEN m.quantity
      WHEN m.movement_type = 'SHIPMENT' THEN -m.quantity
      WHEN m.movement_type = 'ADJUSTMENT' THEN m.signed_quantity
      ELSE 0
    END
  ), 0) + b.opening_balance AS calculated_on_hand
FROM appdb.inventory_balance AS b
LEFT JOIN appdb.inventory_movements AS m
  ON m.product_id = b.product_id
 AND m.warehouse_id = b.warehouse_id
GROUP BY b.product_id, b.warehouse_id, b.on_hand, b.opening_balance
HAVING b.on_hand <> calculated_on_hand;
```

This example assumes the sign conventions above and that the balance table stores the opening balance. Systems may also use periodic snapshots, inter-warehouse transfers, reserved stock, returns, or reversal movements; include all transaction types in the official formula. Reconcile by `product_id` and `warehouse_id`, not merely system-wide total stock.

#### 7.4. Other Invariants

- Shipped quantities must not exceed ordered quantities allowed for shipment per backorder policy.
- Total allocations/fulfillments must not exceed allocatable stock.
- Issued invoices must link to valid customers and orders; invoice line totals must match invoice totals per tax rules.
- Every payment/refund must link to a valid order or account.
- Every journal entry must balance by currency and period.
- Order, payment, and shipment statuses must obey valid state-transition graphs.

Turn critical invariants into repeatable queries and archive results with the migration report. Legitimate exceptions must be defined with explicit conditions up front—never excluded ad hoc after a query flags an anomaly.

### 8. Reconciliation Workflow in a Data Migration

**Before Export**

1. List schemas, tables, partitions, views, triggers, routines, and events to move.
2. Identify primary/business keys and relationships to verify.
3. Lock snapshot/watermark strategy, charset/collation, time zone, SQL mode, and source/target data types.
4. Capture baseline: row counts, grouped counts, monetary totals, min/max timestamps, and business invariants.
5. Save queries, run timestamps, GTID/file-position, and schema version for reproducibility.

**During Import**

1. Load into target in dependency order, ensuring compatible schemas and constraints.
2. Log errors, warnings, inserted row counts, and completed tables/partitions.
3. Never skip type-conversion, duplicate-key, or constraint errors just to keep importing without formal sign-off.
4. If using CDC/replication catch-up, monitor watermarks and apply errors.

**Before Cutover**

1. Block new writes on the source and drain active transactions per plan.
2. Record the final watermark once source writes stop.
3. Wait for the target to apply up to the watermark.
4. Run row counts, key coverage, chunked checksums/hashes, and business invariants on the identical logical state.
5. Drill down into every mismatching chunk or group; fix root causes and re-run checks.
6. Approve cutover only when all discrepancies are explained and signed off in writing.

**After Cutover**

1. Verify application reads/writes on the target and confirm business outcomes.
2. Monitor constraint errors, duplicates, new data, monetary totals, and inventory over a full operational cycle.
3. Keep the source in a reconcilable/rollback-ready state per the approved plan; never allow independent writes on both sides.
4. Archive reports, watermarks, checksums, queries, accepted exceptions, and approvers.

### 9. Classifying Discrepancies and Handling Them

| Reconciliation Finding | Likely Cause | Resolution Approach |
|---|---|---|
| Lower row count on target | Interrupted import, filter, missed partition, or wrong watermark | Compare by chunk/partition; inspect import logs and source data |
| Equal row count but different keys | One key set missing and another extra, bad ID mapping, or repeated import | Bidirectional anti-join on primary/business keys |
| Same keys but different hashes | Column values converted, truncated, or differing time zone/collation/precision | Compare columns individually after normalization; check warnings and session config |
| Different checksums with identical row count | One or more rows differ in values, or checksum algorithm varies by engine/version | Drill down by chunk and keyed hashes; verify checksum calculation method |
| Orphan foreign keys | Missing parent table rows, wrong load order, or unaligned filters | Find missing parent keys, restore data, and re-verify relationships |
| Different monetary totals | Missing transactions, differing payment statuses, rounding, or data types | Reconcile by order/currency/status and verify rounding rules |
| Different inventory | Missing/duplicate movements, wrong snapshot, or formula missing transfers/returns | Reconcile by product/warehouse and rebuild from movement ledger |
| Time-shifted source/target mismatch | Non-aligned snapshots or watermarks | Re-lock watermark, catch up, and re-run reconciliation on a stable state |

Never patch the target with a blanket `UPDATE` just to force aggregates to match. Before fixing anything, determine which source record is authoritative, what operation occurred, whether an audit trail is required, and whether the fix triggers new transactions in replication/CDC.

### 10. Reporting and Acceptance Criteria

A reconciliation report can be stored as a table or file with these fields:

| Field | Content |
|---|---|
| `migration_id` | Migration run identifier |
| `source_id`, `target_id` | Source and target instances/schemas |
| `snapshot_id` / `watermark` | GTID, file/position, or snapshot ID |
| `table_name`, `chunk_id` | Table and key range checked |
| `source_count`, `target_count` | Row counts on both sides |
| `source_digest`, `target_digest` | Digests/hashes under identical canonicalization |
| `business_check` | Name of invariant or business query |
| `mismatch_count` | Number of discrepancies found |
| `result`, `approved_by` | Outcome and exception approver |
| `checked_at` | Reconciliation timestamp |

Define acceptance criteria in advance:

- Zero missing or extra tables/partitions within migration scope.
- Row counts and key coverage match at the same watermark, or discrepancies are classified and approved.
- Chunked hashes show zero unexplained differences.
- Foreign keys, business keys, and mandatory relationships are intact.
- Order, payment, ledger, and inventory invariants pass.
- Zero unexplained import errors/warnings that could alter data.
- Application smoke tests on the target return accurate results.

Never set a generic threshold like "99.9% row match" across all tables. Missing a single financial record can be severe even at a tiny mismatch rate. Acceptance thresholds must reflect data criticality, business impact, and compliance controls.

### 11. Practice Exercise

You need to migrate the `sales` database to a new MySQL instance. After import, total row counts for `orders` match on both sides, yet the total monetary amount differs by 0.8%. `order_items` has 12 fewer rows; `payments` has the same row count, yet the refunded total differs. The source kept receiving transactions during the import.

1. Why does an equal total row count in `orders` not prove the two tables are identical?
2. Which snapshot and watermark must you establish before re-comparing?
3. Write anti-join queries to find `order_id` values missing on the target and extra `order_id` values on the target.
4. How would you break down total amounts by date, status, and currency?
5. Which payment statuses belong in the net collected formula? What must you ask business owners before writing the formula?
6. How would you verify order `subtotal` against summed order items while accounting for discounts, taxes, and rounding?
7. Design a primary-key and chunk-based hashing strategy to isolate differing rows without stuffing all hashes into one `GROUP_CONCAT()`.
8. Write an inventory invariant by product and warehouse, and list all movement types that must be included.
9. Define acceptance criteria and a discrepancy report before allowing applications to write to the target.

### 12. Operational Principles

Reliable reconciliation begins with a defensible snapshot or watermark. Row counts catch volume mismatches; primary and business keys catch missing or extra records; checksums/hashes localize value differences; relationships and business invariants confirm data still makes sense. Normalize data types, `NULL` handling, time zones, charsets, and collations before comparing. Cut over only when discrepancies have been investigated, resolved, or accepted against predefined criteria, and archive enough evidence for someone else to reproduce the verification.
