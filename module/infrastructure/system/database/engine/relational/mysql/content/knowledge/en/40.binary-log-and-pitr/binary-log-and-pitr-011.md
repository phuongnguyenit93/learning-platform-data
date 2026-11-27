# Verifying PITR Results with Business Data

Point-in-time recovery (PITR) restores MySQL from a baseline backup and replays binary logs up to a chosen point in time or position. Having MySQL start up cleanly with all tables present only proves the recovery passed basic technical checks. To confirm data is usable, you must also validate business rules: orders have all their line items, totals match, payments are not double-counted, inventory balances make sense, and transaction statuses match the recovery point.

In the `DATABASE_MYSQL` module, this lesson connects binary logs and PITR with relational data, foreign keys, transactions, aggregate queries, and operations. The goal is to build an evidence-backed, repeatable verification method with explicit acceptance criteria.

After this lesson, you will be able to:

- Identify the PITR target anchor to verify and understand why replay must stop at transaction boundaries.
- Inspect backup metadata, binary logs, GTIDs, and the recovery timestamp.
- Reconcile row counts, keys, relationships, and data aggregates against business rules.
- Detect missing, duplicate, orphaned, or invalid-state records.
- Use independent evidence such as application logs, transaction IDs, and reconciliation reports.
- Produce a verification report and decide whether to accept or redo a recovery run.

## 1. At Which Layers Must PITR Be Verified?

PITR comprises two parts of data: database state when the baseline backup was taken and changes recorded in the binary log afterward. During log replay, MySQL applies events sequentially. Picking the wrong stop anchor can omit valid transactions or include the erroneous transaction in recovered data.

A PITR run should be verified across four layers:

| Verification layer | Question to answer | Example evidence |
|---|---|---|
| Technical | Can the instance open data and complete recovery? | Error log, InnoDB status, backup metadata, MySQL version |
| Structural | Do required schemas, tables, indexes, and constraints exist? | `INFORMATION_SCHEMA`, `SHOW CREATE TABLE`, `CHECK TABLE` |
| Data | Are records, relationships, and values consistent? | Row counts, foreign keys, checksums, orphan-record queries |
| Business | Does data accurately reflect business activity at the target point? | Order totals, order statuses, payment reconciliation, inventory, application logs |

No single query proves all data is accurate. `COUNT(*)` may look right even if some orders lack line items; `CHECK TABLE` may report a table is structurally sound while failing to catch incorrect totals. Combine multiple independent checks and define expected outcomes beforehand.

## 2. Pinpointing the Exact Data Anchor to Recover

Before checking data, answer the question: at what point in time must the system reflect state? For example, operations detects an accidental delete at 14:35 and wants to recover to immediately before that transaction. The target anchor must be established with evidence, not solely from the hour users reported an incident.

### 2.1. Recording baseline backup metadata

For each backup set, collect:

- Backup start and completion timestamps.
- MySQL version and the tool that created the backup.
- List of schemas or data scope backed up.
- Binary log position and file/position recorded at backup time, if provided by the tool.
- Corresponding GTID set, if the system uses GTIDs.
- Required incremental backups and their ordering.
- Encryption status and the keyring required to open data.

Metadata accompanying the backup is the starting point for determining which binary logs to replay. Never infer starting positions from filenames or file creation timestamps. For physical backups, use metadata recorded by the backup tool; for logical backups, use consistent coordinates recorded during the dump and your system's PITR procedure.

### 2.2. Finding transaction boundaries in the binary log

Binary logs may contain GTID events, statement events, row-change events, and transaction end markers. With row-based logging, changed data is logged as row events rather than always appearing as readable SQL statements. You can decode them for investigation:

```bash
mysqlbinlog \
  --base64-output=DECODE-ROWS \
  -vv \
  --start-position=4 \
  /backup/binlog.000123 > /tmp/binlog-decoded.txt
```

In the output, administrators can inspect GTIDs, event timestamps, `Table_map`, `Write_rows`/`Update_rows`/`Delete_rows` events, and transaction end markers such as `Xid` or corresponding commit events. Exact structure depends on format and MySQL version.

When selecting a stop position, identify the last valid transaction to retain and its commit boundary. Avoid stopping mid-way through a multi-statement transaction or between row events of the same transaction. Stopping too early can omit part of a business operation; stopping too late can replay the erroneous transaction.

You can filter logs by time to aid investigation:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 13:00:00" \
  --stop-datetime="2026-11-19 14:34:59" \
  /backup/binlog.000123 > /tmp/binlog-window.sql
```

Timestamps in the example are illustrative only. Before using `--start-datetime` or `--stop-datetime`, confirm server time zone, how logs record timestamps, and actual transaction times. Event timestamps are a locating aid; for incidents requiring high precision, cross-check event positions and transaction boundaries. Never treat application clock timestamps as strictly identical to MySQL commit timestamps.

### 2.3. Replaying logs on an isolated server

Replay binary logs only into an isolated recovery instance. Illustrative example using previously verified file/positions:

```bash
mysqlbinlog \
  --start-position=4 \
  --stop-position=456789 \
  /backup/binlog.000123 \
  /backup/binlog.000124 | \
mysql --host=127.0.0.1 --port=3307 --user=restore_admin -p
```

`456789` is a hypothetical position; do not use verbatim. When replaying multiple files, preserve strict log order and ensure no intermediate file is skipped. For MySQL using GTIDs, follow the procedure matching the backup's GTID set and execution state on the target server; never arbitrarily alter `gtid_purged` or disable logging just to force an import command through.

After replaying, record the final file/position or final GTID applied according to your system's mechanism. This forms part of the evidence showing exactly which anchor data reached.

## 3. Preparing Reference Data for Reconciliation

Querying the recovery server only reveals that server's current state. To know whether that state is correct, you need an independent reference source or a validated set of rules.

Reference sources may include:

- Business reports finalized close to the PITR anchor.
- Application logs recording order IDs, payment IDs, or user actions.
- Reconciliation reports from payment gateways or accounting systems.
- Row counts and checksums recorded during an earlier backup or reconciliation run.
- Lists of transactions confirmed completed by upstream systems.
- Change logs or operator-verified operations journals.

Pick reference data matching the same scope and exact timeframe as PITR. Never compare total orders in a database recovered to 14:30 against a production report generated at 15:00 if valid transactions occurred during those 30 minutes. When complete external references are unavailable, clearly document which parts were verified solely by internal rules and note the remaining confidence limits.

Before running queries, specify:

1. Timestamp and time zone of the recovered data.
2. Scope of schemas, tables, and transaction types to check.
3. Business rules active at that anchor, including which statuses count as valid.
4. Reference source, data owner, and how independence is verified.
5. Acceptable discrepancy tolerance. For monetary amounts and row counts, tolerance should usually be 0 or adhere to published rounding rules.

## 4. Checking Structure and Relational Integrity

Before reconciling business numbers, verify that schemas and table relationships were restored cleanly.

### 4.1. Checking tables and definitions

```sql
SHOW DATABASES;
SHOW TABLES FROM shop_restore;
SHOW CREATE TABLE shop_restore.orders\G
SHOW CREATE TABLE shop_restore.order_items\G
```

Compare table definitions against approved schemas: data types, primary keys, unique keys, indexes, foreign keys, charsets/collations, and engines. If PITR spans a DDL change, confirm the post-recovery structure matches the target point in time.

### 4.2. Checking table status

```sql
CHECK TABLE shop_restore.orders;
CHECK TABLE shop_restore.order_items;
CHECK TABLE shop_restore.payments;
```

`CHECK TABLE` can detect certain table issues, but it does not replace business checks and can be resource-intensive on large tables. Run it on the recovery instance with an appropriate scope.

### 4.3. Finding orphaned records

Suppose `order_items.order_id` references `orders.order_id`:

```sql
SELECT COUNT(*) AS orphan_item_count
FROM shop_restore.order_items AS i
LEFT JOIN shop_restore.orders AS o
    ON o.order_id = i.order_id
WHERE o.order_id IS NULL;
```

Expected result is `0`. If non-zero, pull a sample to investigate:

```sql
SELECT i.order_id, i.product_id, i.quantity
FROM shop_restore.order_items AS i
LEFT JOIN shop_restore.orders AS o
    ON o.order_id = i.order_id
WHERE o.order_id IS NULL
ORDER BY i.order_id
LIMIT 20;
```

Run similar checks for payments, shipments, inventory movements, or other child tables. Some systems permit referenced parent records to be purged by archival policy; in that case, identify valid exceptions rather than assuming every missing relationship is a PITR error.

## 5. Checking Row Counts and Data Ranges

Row counts are a quick check to spot broad missing data. Compare them against reference figures matching the exact timestamp and scope.

```sql
SELECT 'orders' AS table_name, COUNT(*) AS row_count
FROM shop_restore.orders
UNION ALL
SELECT 'order_items', COUNT(*)
FROM shop_restore.order_items
UNION ALL
SELECT 'payments', COUNT(*)
FROM shop_restore.payments;
```

Check key and time ranges:

```sql
SELECT
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    MIN(created_at) AS first_order_at,
    MAX(created_at) AS last_order_at
FROM shop_restore.orders;
```

Matching `MIN`/`MAX` bounds do not prove no records are missing in between. Combine with daily or business-partition distributions:

```sql
SELECT
    DATE(created_at) AS order_day,
    COUNT(*) AS order_count
FROM shop_restore.orders
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
GROUP BY DATE(created_at)
ORDER BY order_day;
```

Dates in the query are examples only. Use date ranges aligned with the PITR anchor and system time zone rules. If the application stores UTC, filter in UTC and convert to business time in the reporting layer.

To detect duplicates on a business key that must be unique:

```sql
SELECT external_order_ref, COUNT(*) AS duplicate_count
FROM shop_restore.orders
WHERE external_order_ref IS NOT NULL
GROUP BY external_order_ref
HAVING COUNT(*) > 1;
```

Expected result is zero duplicate groups if `external_order_ref` is defined as unique. If uniqueness applies only per store or per tenant, include that scope key in `GROUP BY`.

## 6. Reconciling Business Invariants

Business invariants are conditions data must always satisfy if transactions were recorded properly. This is the most important layer for detecting whether PITR omitted or included extra transactions.

### 6.1. Order total matches line items

Suppose `orders.total_amount` is computed from `order_items.quantity * order_items.unit_price`. The following query finds orders whose item sum differs from the stored total:

```sql
SELECT
    o.order_id,
    o.total_amount,
    ROUND(SUM(i.quantity * i.unit_price), 2) AS item_total
FROM shop_restore.orders AS o
LEFT JOIN shop_restore.order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING ABS(
    o.total_amount - ROUND(COALESCE(SUM(i.quantity * i.unit_price), 0), 2)
) > 0.01;
```

This is an example only if order totals exclude tax, shipping, discounts, or other adjustments. In real systems, apply the exact business formula and prescribed `DECIMAL` types. Never use `FLOAT` to reconcile money when exact decimal arithmetic is required.

### 6.2. Payments match order status

Suppose `payments` records payment transactions and `payment_status='SETTLED'` denotes settled payments. You can locate orders marked paid whose settled amounts do not match:

```sql
SELECT
    o.order_id,
    o.total_amount,
    COALESCE(SUM(
        CASE WHEN p.payment_status = 'SETTLED'
             THEN p.amount ELSE 0 END
    ), 0) AS settled_amount
FROM shop_restore.orders AS o
LEFT JOIN shop_restore.payments AS p
    ON p.order_id = o.order_id
WHERE o.order_status = 'PAID'
GROUP BY o.order_id, o.total_amount
HAVING ABS(
    o.total_amount - COALESCE(SUM(
        CASE WHEN p.payment_status = 'SETTLED'
             THEN p.amount ELSE 0 END
    ), 0)
) > 0.01;
```

Interpret results according to the payment model. An order might support split payments, partial refunds, or separate fees. Adjust the formula to your system's policy and also inspect payment gateway transaction IDs to catch duplicate transactions.

### 6.3. Inventory matches movement ledger

If the system stores current stock in `inventory_balance` and movement history in `inventory_movements`, you can check the general relation:

```sql
SELECT
    b.product_id,
    b.warehouse_id,
    b.quantity_on_hand,
    b.opening_quantity,
    COALESCE(SUM(m.quantity_delta), 0) AS movement_total
FROM shop_restore.inventory_balance AS b
LEFT JOIN shop_restore.inventory_movements AS m
    ON m.product_id = b.product_id
   AND m.warehouse_id = b.warehouse_id
GROUP BY
    b.product_id,
    b.warehouse_id,
    b.quantity_on_hand,
    b.opening_quantity
HAVING b.quantity_on_hand <>
       b.opening_quantity + COALESCE(SUM(m.quantity_delta), 0);
```

This query assumes the balance table has `opening_quantity` and all movements since opening are stored in the movement table. If the system includes cycle counts, adjustments, transfers, or periodic snapshots, incorporate those operations into the formula. The invariant must mirror exactly how the system computes inventory.

### 6.4. Valid states and event sequences

Certain states can only transition in a defined order; for instance, an order cannot jump straight from `CREATED` to `SHIPPED` without passing payment confirmation and packing steps. If the system records status history, check for invalid transitions against the defined state machine.

For example, if `order_status_history` stores states after each transition:

```sql
SELECT order_id, COUNT(*) AS invalid_transition_count
FROM shop_restore.order_status_history
WHERE (previous_status = 'CREATED' AND new_status = 'SHIPPED')
   OR (previous_status = 'CANCELLED' AND new_status = 'PAID')
GROUP BY order_id;
```

The transitions above are illustrative only. Some systems support cash-on-delivery or reopening cancelled orders via dedicated workflows. Use the business-approved transition list to avoid false positives.

## 7. Reconciling Against Independent Evidence

Internal invariants catch inconsistent data, yet an inaccurate dataset can still be internally self-consistent. For example, if both an order and its payment are missing together, remaining table totals may still balance. That is why reconciliation against independent systems is necessary.

### 7.1. Reconciling by transaction ID

Select a set of transaction IDs confirmed by upstream systems prior to the incident anchor. For each ID, check:

- Whether exactly one order exists in the recovered schema.
- Whether all line items and product quantities are present.
- Whether the payment transaction ID exists and has the right status.
- Whether monetary amounts and currencies match independent evidence.
- Whether creation, payment, and update timestamps fall before the stop anchor.

Do not sample only the first and last transactions. Sample across time intervals, amounts, statuses, and product groups, while verifying all business-critical transactions flagged by stakeholders.

### 7.2. Aggregate reconciliation

Example summary report of order counts and gross amounts by day:

```sql
SELECT
    DATE(created_at) AS order_day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS gross_amount
FROM shop_restore.orders
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
  AND order_status IN ('PAID', 'SHIPPED', 'COMPLETED')
GROUP BY DATE(created_at)
ORDER BY order_day;
```

Compare with business reports using identical filter predicates, time zone, and PITR anchor. Two reports are only comparable when definitions of revenue, refunds, cancellations, and taxes match.

### 7.3. Distinguishing missing data from post-anchor data

A transaction absent from the recovered database is not necessarily lost. If the transaction was created after the PITR anchor, its absence is expected. Conversely, a transaction confirmed before the stop anchor that does not appear may indicate an incomplete baseline backup or binlog gap.

To classify accurately, compare three timestamps:

1. When the event was recorded in the upstream system.
2. When the transaction committed in MySQL or appeared in the binary log.
3. The chosen PITR stop anchor.

For systems using asynchronous synchronization, lag between upstream and MySQL can cause the two timestamps to differ. Understand the architecture's recording order before concluding data loss occurred.

## 8. Verifying PITR Excluded the Erroneous Transaction

A common PITR objective is keeping every valid transaction prior to a bad operation while excluding that operation and unwanted transactions after it.

For example, at 14:20 an administrator accidentally ran `DELETE` on `orders`; at 14:35 operations started recovery. You must identify:

- The last valid transaction prior to the delete statement.
- That transaction's GTID or file/position, if applicable.
- The position and scope of the delete transaction.
- Other valid transactions occurring afterward but before incident detection.
- Whether valid transactions after the stop anchor must be selectively reapplied manually.

Never eyeball a timestamp and stop arbitrarily. A transaction may start before a wall-clock mark and commit afterward; large transactions may span many binlog events. Confirm commit boundaries and verify critical business IDs before accepting.

If valid transactions occurred after the erroneous transaction, you may need to recover to before the bad transaction and selectively reapply valid ones via a controlled procedure. Reapplication must guarantee idempotency or duplicate checks while logging every manual change. Never blindly replay the rest of the log after the bad anchor without analyzing inter-transaction dependencies.

## 9. Post-PITR Verification Workflow

A repeatable workflow should execute in the following sequence:

1. **Freeze the target:** document exact target timestamp, time zone, file/position or GTID, and rationale for the anchor.
2. **Verify sources:** inspect baseline backup, checksums, metadata, and all required binary logs.
3. **Restore in isolation:** restore baseline backup, prepare keyring, replay logs, and keep the instance off the production network.
4. **Record state:** capture MySQL version, final file/position, GTID set, error log, and completion time.
5. **Verify structure:** validate schemas, tables, indexes, foreign keys, views, triggers, and routines.
6. **Verify data:** reconcile row counts, ID ranges, date ranges, duplicates, and orphaned records.
7. **Verify business logic:** run invariants for orders, payments, inventory, or domain-specific rules.
8. **Reconcile independently:** compare against reports, application logs, or upstream systems at the same anchor.
9. **Test with applications:** run read-only smoke tests and safe business flows in a test environment.
10. **Decide:** accept, accept with limitations, or restart recovery from scratch; archive evidence and approvers.

Keep `event_scheduler` disabled and block outbound connections to production services throughout verification. If write flows must be tested, use test-environment endpoints and mock data, then revert to the verified state or rebuild a clean environment.

## 10. Verification Report Template

Record results by check group so others can audit the outcome. A concise report can follow this structure:

| Field | Values to record |
|---|---|
| Incident / request | Incident ID or drill request |
| Baseline backup | ID, timestamp, checksum, and backup tool |
| PITR anchor | Time zone, timestamp, final binlog file/position or GTID |
| Environment | Test host, port, MySQL version, and isolation status |
| Technical checks | Startup result, error log, InnoDB, and keyring |
| Structural checks | Counts of schemas/tables/views/routines, keys, and indexes |
| Data checks | Row counts, duplicate/orphan checks, and checksums if available |
| Business checks | Order totals, payment totals, inventory, and other rules |
| Independent evidence | Upstream reports, application logs, reconciliation, and comparison scope |
| Discrepancies | Counts, severity, root cause, and remediation |
| Conclusion | PASS, PASS WITH LIMITATIONS, or FAIL |
| Sign-off | Executor and business data owner |

Never put passwords, tokens, keyring contents, or KMS secrets into the report. Use reference identifiers pointing to a controlled secret vault if access details must be tracked.

### 10.1. Suggested acceptance criteria

A PITR run can be accepted when:

- The stop anchor is clearly defined and ends on a valid transaction boundary.
- MySQL starts and opens all required tablespaces; no unexplained critical errors exist.
- Essential schemas and objects exist matching the target point in time.
- Relational checks find zero orphaned records outside documented exceptions.
- Critical business invariants meet agreed thresholds.
- Sampled transactions reconcile against independent evidence with zero unexplained discrepancies.
- The recovery server remains isolated and caused no unintended side effects.

If no independent reference exists for a data group, do not mark that group fully verified. Document the limitation, residual risk, and the authorized stakeholder accepting that limitation.

## 11. Common Discrepancies and Troubleshooting

| Symptom | Possible cause | Investigation approach |
|---|---|---|
| Order count lower than report | Baseline backup missing data or binlog stopped too early | Check backup metadata, binlogs, GTIDs, and missing order IDs |
| Order count higher than expected | PITR replayed past anchor, duplicate import, or transaction reapplied twice | Check stop anchor, transaction IDs, GTIDs, and duplicate business keys |
| Totals mismatch | Missing line items, wrong status, refunds, or inconsistent aggregation formula | Compare individual orders, payment references, and revenue calculation rules |
| Child records lack parent records | Partial transaction missing or incomplete schema restored | Check foreign keys, import order, and related binlog events |
| Inventory drift | Missing movements, duplicate replay, or skipped count snapshot | Reconcile ledger, snapshots, and warehouse transaction IDs |
| Orders exist after PITR anchor | Misread timestamp/time zone or logs replayed too far | Check timestamps, transaction boundaries, file/position, and time source |
| Tables valid but business state wrong | Checks stopped at structure or row counts | Add business invariants and independent reconciliation |
| Unable to open encrypted tables | Keyring or key access does not match backup | Inspect keyring configuration, key history, and error log |

When discrepancies appear, preserve the original backup, recovery instance, and investigation logs. Record exact queries, parameters, execution times, and outputs. If the PITR anchor must change, rebuild from a clean baseline backup and replay logs to the new anchor; avoid continuing log replay on an instance in an ambiguous state.

## 12. Practice Scenario

An online store uses three main tables:

- `orders`: order ID, status, total amount, and creation time.
- `order_items`: products, quantities, and unit prices per order.
- `payments`: payment transaction ID, amount, and settlement status.

At 14:20, an accidental delete removed a batch of orders. Operations has a baseline backup and continuous binary logs past the incident time. The requirement is to recover to immediately before the delete transaction, then prove data matches business activity at that point.

Execute in a lab environment:

1. Record baseline backup metadata, file/position or GTID, and MySQL version.
2. Use `mysqlbinlog` to read logs around the incident time, identifying the delete transaction and the last valid committed transaction before it.
3. Restore the backup onto an isolated instance and replay binary logs up to the chosen boundary.
4. Record the final applied position or GTID; inspect the error log and confirm tables open cleanly.
5. Run queries counting orders, line items, and payments; check for orphaned records and duplicate order keys.
6. Recalculate order totals from line items according to the lab's tax, fee, and discount rules.
7. Reconcile a sample of order IDs and payment IDs against application logs or a reconciliation file generated at the same timestamp.
8. Verify orders created after the stop anchor do not appear while valid transactions before the anchor remain intact.
9. Produce a PASS/FAIL report per check group, documenting discrepancies and causes.
10. Practice shifting the stop anchor in a fresh recovery run to observe how omitting or including one extra transaction affects business invariants.

**Self-assessment questions:**

- Why is MySQL starting up successfully insufficient to prove PITR accuracy?
- Why must binary log replay stop at a transaction's commit boundary?
- Why cannot `COUNT(*)` and `CHECK TABLE` replace business reconciliation?
- How do you distinguish a lost transaction from one created after the PITR anchor?
- Why must payment totals be checked against an independent source instead of only comparing two tables inside the same database?
- When valid transactions exist after the erroneous transaction, how should you handle them to avoid duplicate replay or breaking business ordering?
- What details must a verification report capture so someone else can audit the results?

## Conclusion

PITR verification must answer two questions: did MySQL recover to the exact transaction boundary, and does data at that boundary accurately reflect business operations? Combine backup metadata, final position or GTID, structural checks, relational queries, business invariants, and independent evidence. Accept results only once discrepancies are explained, residual limitations are documented, and the recovery environment remains properly isolated.
