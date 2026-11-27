# Bulk Data Loading with Constraints, Triggers, and Indexes

A CSV file with a few hundred rows can easily load into PostgreSQL with a handful of `INSERT` statements. When volume grows to millions or hundreds of millions of records, that approach exposes deeper problems: malformed values abort the entire batch, foreign keys perform millions of lookups, unique indexes require constant updates, row triggers write per-row audit entries, WAL and disk usage surge, replicas lag, and huge transactions hold resources for far too long. Turning off all checks just for speed makes the database load faster, yet destroys the very guarantees that make the data trustworthy.

**Proper bulk data loading** is a balancing act across **throughput, correctness, recoverability, availability, and operational cost**. PostgreSQL provides `COPY`, transactions, staging tables, `INSERT ... SELECT`, `ON CONFLICT`, `CHECK`/`FOREIGN KEY`/`UNIQUE` constraints, triggers, and index build/validation tools. No single sequence fits every workload: loading an empty offline table differs fundamentally from updating a table serving users 24/7.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose among `COPY`, `\copy`, batch `INSERT`, or JDBC `CopyManager` based on data source and environment.
2. Explain the impact of `NOT NULL`, `CHECK`, `UNIQUE`, primary keys, foreign keys, and triggers during bulk loads.
3. Design two core strategies: **direct loading** vs. **staging → validate → merge**.
4. Capture faulty rows without letting invalid records slip into business tables.
5. Control duplicates, idempotency, batch identifiers, and failure retries.
6. Use `INSERT ... ON CONFLICT` to upsert from staging while avoiding no-op updates.
7. Distinguish when to build indexes after loading vs. when `CREATE INDEX CONCURRENTLY` is required.
8. Understand `NOT VALID` and `VALIDATE CONSTRAINT` for supported constraint types.
9. Evaluate the cost of row vs. statement triggers, auditing, and transition tables during bulk loads.
10. Plan transaction sizes, batching, WAL, checkpoints, vacuuming, and `ANALYZE`.
11. Use `pg_stat_progress_copy`, `pg_stat_activity`, and load metrics to pinpoint bottlenecks.
12. Implement Java/JDBC streaming `COPY` with proper transaction and error handling.
13. Plan online loads, cutovers, partitioning/replica impact, and rollbacks.
14. Build verification checks for row counts, uniqueness, foreign keys, checksums, and batch reconciliation.

> **Lab scope:** Modern PostgreSQL; error classification via `pg_input_is_valid` requires **PostgreSQL 16 or newer**. On older versions, validate types in the application or use exception-handling parsing helpers before casting text to target types. Any `TRUNCATE`, `ALTER TABLE`, `DROP INDEX`, or trigger changes must be carefully evaluated for production; examples use the `lesson_bulk_load` schema in a practice database.

## 2. The Big Picture

```text
                    file / object storage / API export
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                Direct COPY               COPY into staging
                    │                           │
                    ▼                           ▼
             PostgreSQL target           Raw rows (TEXT, batch)
           ┌────────┼────────┐                  │
           │        │        │                  ▼
        checks    indexes  triggers       Validate / normalize
           │        │        │            ┌─────┴──────┐
           │        │        │            ▼            ▼
           │        │        │         accepted      rejects
           │        │        │            │            │
           │        │        │            ▼            ▼
           │        │        │        INSERT/UPSERT  Repair / export
           │        │        │            │
           └────────┴────────┴────────────┘
                              │
                            COMMIT
                              │
                     ANALYZE / reconcile
                              │
                     Monitor + publish status
```

**Direct COPY** minimizes steps and fits clean inputs targeting tightly controlled schemas. **Staging** adds an I/O pass, yet preserves raw input, classifies errors, deduplicates, and supports controlled retries before touching business tables.

## 3. Why Numerous Individual INSERTs Are Usually Slow

A naive loop:

```java
for (Row row : rows) {
    // Each row opens a connection, runs INSERT, commits, and closes.
}
```

generates millions of network round trips, commits, statement parses, and connection startups.

### Better Approaches

| Approach | Strengths | Trade-offs |
|---|---|---|
| One `INSERT` per row, autocommit | Simple | Massive round-trip and commit overhead |
| JDBC `addBatch`/`executeBatch` | Fewer round trips, easy parameterized APIs | Batch sizing, memory, and retry semantics |
| Multi-row `INSERT ... VALUES` | Easy to write, one statement for many rows | Large SQL text, parameter limits, conflict semantics |
| `COPY FROM STDIN` | Typically very high streaming throughput | Bad types/rows can abort the whole batch |
| `COPY` into raw staging | Preserves raw input, decouples validation | Extra storage, orchestration, and merge step |
| `INSERT ... SELECT` from staging | Set-based processing, enforces target constraints/triggers | Needs idempotency, deduplication, and transaction planning |

Never claim `COPY` outperforms every alternative in every scenario: index count, triggers, I/O sources, data types, batch sizes, and transaction durability all matter.

## 4. What Is COPY?

`COPY` is a PostgreSQL statement that moves data between a table or query result and a file or `STDIN`/`STDOUT` stream in a supported format.

Example:

```sql
COPY lesson_bulk_load.raw_orders (
    batch_id, row_no, tenant_raw, source_key_raw,
    customer_raw, amount_raw, ordered_on_raw
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
```

With `COPY FROM STDIN`, the client implements the **COPY protocol** and streams data over that connection; this SQL statement does not search your laptop for a CSV file on its own.

### COPY Is Not "Unchecked INSERT"

For `COPY FROM` into a normal table, PostgreSQL enforces constraints and fires applicable row triggers. `COPY` does **not** bypass `CHECK`, `NOT NULL`, uniqueness, or foreign keys.

### One Exception to Remember

PostgreSQL `COPY FROM` does not fire **query rewrite rules** the way a rewritten `INSERT` does, so never rely on `RULE`s to control data loading. Use constraints, triggers, or well-designed staging instead.

## 5. Server-Side COPY vs. Client-Side \copy

Two easily confused commands:

```sql
-- PostgreSQL server SQL: file path belongs to the DB server host.
COPY lesson_bulk_load.raw_orders
FROM '/server/import/orders.csv'
WITH (FORMAT csv, HEADER true);
```

```text
-- psql meta-command: file path belongs to the machine running psql.
\copy lesson_bulk_load.raw_orders FROM '/client/import/orders.csv' WITH (FORMAT csv, HEADER true)
```

| Characteristic | `COPY FROM 'file'` | `\copy ... FROM 'file'` |
|---|---|---|
| Who reads the file? | PostgreSQL server process | `psql` client |
| Whose filesystem is the path on? | Database server machine | Machine running `psql` |
| Command type | SQL | `psql` meta-command |
| Filesystem permissions | Server-side OS & predefined DB roles | Client-side OS file permissions |
| Network transfer | Server reads locally | Client streams over PostgreSQL connection |
| Usage from JDBC | Via driver COPY protocol | Cannot send `psql` meta-command directly |

For applications and managed PostgreSQL, **client-side streaming COPY** or `\copy` is usually far easier to deploy than server-side filesystem access.

### Security Warning

`COPY ... PROGRAM` executes commands on the server under elevated privileges, carrying high risk; never grant this capability to ordinary CSV-loading application roles.

## 6. CSV Data and Common Error Sources

Suppose the input file has headers:

```csv
batch_id,row_no,tenant_raw,source_key_raw,customer_raw,amount_raw,ordered_on_raw
B-2026-11,1,10,SO-001,CUS-01,125000.00,2026-11-01
B-2026-11,2,10,SO-002,CUS-02,300500.00,2026-11-02
B-2026-11,3,10,SO-003,CUS-X,28000.00,2026-11-03
B-2026-11,4,oops,SO-004,CUS-01,5000.00,2026-11-04
B-2026-11,5,10,SO-005,CUS-01,-100.00,2026-11-05
B-2026-11,6,10,SO-006,CUS-01,not-a-number,2026-11-06
```

Potential errors include:

- Invalid numeric or date/time values.
- Missing referenced customer.
- Negative amount violating `CHECK`.
- Duplicate `(tenant_id, source_key)`.
- Missing columns, wrong delimiter, or broken quotes/escapes.
- Duplicate rows from re-sending the same file.
- Text containing commas, newlines, CRLF, or Unicode characters.
- Encoding mismatched with `client_encoding`.

When loading straight into typed tables, one bad row mid-file aborts the entire statement. With raw staging, suspect fields land as `TEXT` and are classified cleanly before casting.

## 7. Creating the Lab Schema and Reference Table

Run on a fresh practice database:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_bulk_load;

CREATE TABLE lesson_bulk_load.customers (
    tenant_id BIGINT NOT NULL,
    customer_ref TEXT NOT NULL,
    display_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_ref)
);

INSERT INTO lesson_bulk_load.customers (
    tenant_id, customer_ref, display_name
)
VALUES
    (10, 'CUS-01', 'Công ty Hòa Bình'),
    (10, 'CUS-02', 'Công ty An Việt'),
    (20, 'CUS-01', 'Công ty Sao Mai');
```

`tenant_id` is part of the primary key because the same `customer_ref` can exist across multiple tenants. Foreign keys from orders to customers must match **both tenant and `customer_ref`**, preventing cross-tenant references.

## 8. Constrained Target Table

```sql
CREATE TABLE lesson_bulk_load.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    source_key TEXT NOT NULL,
    customer_ref TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    ordered_on DATE NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_orders_tenant_source
        UNIQUE (tenant_id, source_key),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (tenant_id, customer_ref)
        REFERENCES lesson_bulk_load.customers (
            tenant_id, customer_ref
        )
);

CREATE INDEX ix_orders_tenant_date
ON lesson_bulk_load.orders (
    tenant_id, ordered_on DESC, order_id DESC
);
```

### Immediate Guarantees

| Constraint / Index | Protection |
|---|---|
| `PRIMARY KEY (order_id)` | Unique surrogate ID per row |
| `UNIQUE (tenant_id, source_key)` | Prevents loading the same source order twice per tenant |
| `NOT NULL` | Enforces required fields |
| `CHECK amount >= 0` | Rejects negative amounts |
| `FOREIGN KEY` | Customer must exist **within the matching tenant** |
| B-tree `tenant_id, ordered_on` | Accelerates tenant/date queries |

`ix_orders_tenant_date` is a **query index**, not a uniqueness constraint. When loading millions of rows, every index adds insert and WAL overhead—align index count with actual workload needs.

## 9. Raw Staging Table and Batch Identity

```sql
CREATE TABLE lesson_bulk_load.raw_orders (
    batch_id TEXT NOT NULL,
    row_no BIGINT NOT NULL,
    tenant_raw TEXT,
    source_key_raw TEXT,
    customer_raw TEXT,
    amount_raw TEXT,
    ordered_on_raw TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_no)
);
```

In staging, CSV fields are `TEXT`, with no business FKs or `CHECK`s. Thus rows with `tenant_raw='oops'` or `amount_raw='not-a-number'` still load cleanly for inspection.

### Should Staging Keep a Primary Key?

In the lab, `PK (batch_id, row_no)` catches accidental duplicate line reloads right away. On massive staging tables, a PK index adds write overhead. Depending on restart/idempotency needs, you can:

- Load into an unindexed raw heap first, then build/verify uniqueness.
- Track `load_id` + file offset from an ingestion coordinator.
- Create a dedicated temporary or `UNLOGGED` staging table per batch.

Never drop all keys and simply assume deduplication works cleanly when inputs lack stable row identifiers.

## 10. Loading Sample Rows into Staging

To run the lab immediately without external files:

```sql
INSERT INTO lesson_bulk_load.raw_orders (
    batch_id, row_no, tenant_raw, source_key_raw,
    customer_raw, amount_raw, ordered_on_raw
)
VALUES
    ('B-2026-11', 1, '10', 'SO-001', 'CUS-01', '125000.00', '2026-11-01'),
    ('B-2026-11', 2, '10', 'SO-002', 'CUS-02', '300500.00', '2026-11-02'),
    ('B-2026-11', 3, '10', 'SO-003', 'CUS-X',  '28000.00',  '2026-11-03'),
    ('B-2026-11', 4, 'oops', 'SO-004', 'CUS-01', '5000.00',  '2026-11-04'),
    ('B-2026-11', 5, '10', 'SO-005', 'CUS-01', '-100.00',   '2026-11-05'),
    ('B-2026-11', 6, '10', 'SO-006', 'CUS-01', 'not-a-number','2026-11-06'),
    ('B-2026-11', 7, '20', 'SO-007', 'CUS-01', '92000.00',  '2026-11-07');
```

These seven rows include:

- **3 valid rows** (`row_no` 1, 2, 7).
- One row with a nonexistent customer in that tenant (3).
- One row with an unparseable tenant ID (4).
- One row with a negative amount (5).
- One row with an unparseable amount (6).

These expected counts apply to **this initial dataset**; extra runs or edits will change them.

## 11. Loading Real Files with psql \copy

With a CSV file on the machine running `psql`:

```text
\copy lesson_bulk_load.raw_orders (batch_id,row_no,tenant_raw,source_key_raw,customer_raw,amount_raw,ordered_on_raw) FROM '/client/path/orders.csv' WITH (FORMAT csv, HEADER true)
```

This is a **`psql` meta-command** (not SQL for a JDBC `PreparedStatement`). `ingested_at` is omitted from the COPY list so it takes its default.

### Paths and Headers

- Paths resolve on the **`psql` client machine**.
- Headers must match the file layout; `HEADER true` skips the header row.
- The `COPY` column list maps fields by **positional order** in the file; it does not auto-match column names from headers in standard modes.
- In CSV format, NULL and empty string have specific semantics—do not assume they are identical.
- Verify `client_encoding` and UTF-8 bytes.

### Note After Running Sample INSERTs

If you load a file sharing `(batch_id, row_no)` with rows already in lab staging, the PK raises an error. That signals an unhandled replay rather than a `\copy` bug. Use a fresh `batch_id` or an idempotent workflow.

## 12. COPY CSV with Commas Inside Numeric Strings

A record may contain:

```csv
B-2026-12,8,10,SO-008,CUS-01,"125,000.00",2026-12-01
```

The CSV parser reads `"125,000.00"` as **one text field**, yet **PostgreSQL's numeric parser normally rejects thousands-separator commas** if cast directly.

### Two Distinct Layers

1. **CSV formatting** governs field delimiters and quoting.
2. **Domain validation** defines acceptable numeric formatting.

If business inputs allow `125,000.00`, normalize explicitly per locale rules—never run `replace(',', '')` blindly when other files might use commas as decimal points.

## 13. Why Persist Rejects Separately?

A resilient ingestion pipeline splits into:

```text
raw source
   ├── accepted → typed target
   └── rejected → row number + reason + raw payload
```

Persisting rejects lets you:

- Repair source files and re-run subsets easily.
- Separate type errors, FK failures, and business-rule failures.
- Report error rates and data-quality SLOs.
- Maintain a per-batch audit trail for investigation.

Schema:

```sql
CREATE TABLE lesson_bulk_load.load_rejects (
    batch_id TEXT NOT NULL,
    row_no BIGINT NOT NULL,
    reason TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_no)
);
```

### Security Policy

Raw payloads can hold PII or secrets. Protect the rejects table with strict access permissions and retention windows rather than storing sensitive data indefinitely.

## 14. Classifying Raw Data Before Casting

On PostgreSQL 16+, `pg_input_is_valid(text, type)` checks whether a string is accepted by a type's input function prior to casting.

Example:

```sql
SELECT
    pg_input_is_valid('10', 'bigint') AS tenant_valid,
    pg_input_is_valid('oops', 'bigint') AS tenant_invalid,
    pg_input_is_valid('125000.00', 'numeric(14,2)') AS amount_valid,
    pg_input_is_valid('not-a-number', 'numeric(14,2)') AS amount_invalid,
    pg_input_is_valid('2026-11-01', 'date') AS date_valid;
```

For built-in types here, you can route rows cleanly before casting. `pg_input_is_valid` validates **PostgreSQL type syntax**, without checking business rules like non-negative amounts, per-tenant customer existence, or uniqueness.

### Why Not Just `WHERE tenant_raw ~ '^\d+$'`?

A regex misses `bigint` integer overflows; for dates, `YYYY-MM-DD` fails to reject `2026-02-30`. PostgreSQL's input validation handles parse and typmod rules far more reliably.

### Limitations

Checking input at step A and casting at step B must share identical inputs, encoding, and semantics; for custom types whose input functions lack full soft-error support, test on your target version. In this lab, all checked fields use built-in `bigint`, `numeric`, and `date`.

## 15. Building a Normalized Set Inside One Transaction

Build a temp table with casts guarded by `CASE`:

```sql
BEGIN;

CREATE TEMP TABLE tmp_orders_typed
ON COMMIT DROP
AS
SELECT
    r.batch_id,
    r.row_no,
    CASE
        WHEN pg_input_is_valid(btrim(r.tenant_raw), 'bigint')
        THEN btrim(r.tenant_raw)::bigint
        ELSE NULL
    END AS tenant_id,
    NULLIF(btrim(r.source_key_raw), '') AS source_key,
    NULLIF(btrim(r.customer_raw), '') AS customer_ref,
    CASE
        WHEN pg_input_is_valid(btrim(r.amount_raw), 'numeric(14,2)')
        THEN btrim(r.amount_raw)::numeric(14,2)
        ELSE NULL
    END AS amount,
    CASE
        WHEN pg_input_is_valid(btrim(r.ordered_on_raw), 'date')
        THEN btrim(r.ordered_on_raw)::date
        ELSE NULL
    END AS ordered_on,
    to_jsonb(r) AS raw_payload
FROM lesson_bulk_load.raw_orders AS r
WHERE r.batch_id = 'B-2026-11';
```

`CASE` ensures **invalid values are never cast**. `NULLIF(btrim(...), '')` treats whitespace-only strings as missing.

### Do Not COMMIT Immediately

The temp table uses `ON COMMIT DROP`, meaning it disappears on commit. Rejection routing and merge steps must run **within the same transaction**, before `COMMIT`.

### Transaction Sizing in Production

This lab uses a handful of rows. For millions of rows, process in controlled batches or partitions instead of holding one huge transaction across all temp data, rejects, and target writes.

## 16. Business-Rule and Reference Classification

Continuing **inside the transaction started above**, build a temp table tagging explicit rejection reasons:

```sql
CREATE TEMP TABLE tmp_orders_checked
ON COMMIT DROP
AS
WITH ranked AS (
    SELECT
        t.*,
        row_number() OVER (
            PARTITION BY t.tenant_id, t.source_key
            ORDER BY t.row_no
        ) AS key_rank
    FROM tmp_orders_typed AS t
)
SELECT
    r.*,
    CASE
        WHEN r.tenant_id IS NULL
            THEN 'INVALID_TENANT'
        WHEN r.source_key IS NULL
            THEN 'MISSING_SOURCE_KEY'
        WHEN r.customer_ref IS NULL
            THEN 'MISSING_CUSTOMER'
        WHEN r.amount IS NULL
            THEN 'INVALID_AMOUNT'
        WHEN r.amount < 0
            THEN 'NEGATIVE_AMOUNT'
        WHEN r.ordered_on IS NULL
            THEN 'INVALID_DATE'
        WHEN c.customer_ref IS NULL
            THEN 'UNKNOWN_CUSTOMER_IN_TENANT'
        WHEN r.key_rank > 1
            THEN 'DUPLICATE_SOURCE_KEY_IN_BATCH'
        ELSE NULL
    END AS reject_reason
FROM ranked AS r
LEFT JOIN lesson_bulk_load.customers AS c
  ON c.tenant_id = r.tenant_id
 AND c.customer_ref = r.customer_ref;
```

### Why Check Tenant Alongside Customer?

`CUS-01` existing under tenant 20 does **not** make a tenant 10 order referencing `CUS-01` valid. The `LEFT JOIN` matches both columns to enforce tenant isolation.

### Why Still Keep the Target FOREIGN KEY?

Staging validation can have bugs, be skipped, or race against concurrent transactions deleting a customer. **The target FK** is the final safeguard during `INSERT`/`UPDATE`. Pre-validation provides clear error reporting—it never replaces constraints.

## 17. Counting Accepted vs. Rejected Rows Before Merging

Still inside the transaction:

```sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (
        WHERE reject_reason IS NULL
    ) AS accepted_rows,
    count(*) FILTER (
        WHERE reject_reason IS NOT NULL
    ) AS rejected_rows
FROM tmp_orders_checked;
```

For the initial dataset:

```text
total_rows    = 7
accepted_rows = 3
rejected_rows = 4
```

Inspect details:

```sql
SELECT
    batch_id,
    row_no,
    tenant_id,
    source_key,
    amount,
    reject_reason
FROM tmp_orders_checked
ORDER BY row_no;
```

Group by reason:

```sql
SELECT
    reject_reason,
    count(*) AS rows
FROM tmp_orders_checked
WHERE reject_reason IS NOT NULL
GROUP BY reject_reason
ORDER BY rows DESC, reject_reason;
```

### What If One Row Has Multiple Errors?

`CASE` records the **first failing reason by precedence**. Systems needing all errors per row can emit a `TEXT[]` of reason codes or a child diagnostics table. That is a contract design choice, not a trivial SQL tweak.

## 18. Re-Runnable Reject Logging

```sql
INSERT INTO lesson_bulk_load.load_rejects (
    batch_id,
    row_no,
    reason,
    raw_payload
)
SELECT
    batch_id,
    row_no,
    reject_reason,
    raw_payload
FROM tmp_orders_checked
WHERE reject_reason IS NOT NULL
ON CONFLICT (batch_id, row_no)
DO UPDATE
SET reason = EXCLUDED.reason,
    raw_payload = EXCLUDED.raw_payload;
```

`ON CONFLICT` ensures re-running classification on the **same batch** updates existing reject entries instead of colliding on the primary key.

### Is This Fully Idempotent?

Not completely. If an operator edits a raw row inside the same batch from invalid to valid, the old reject entry would still remain. Define a clear protocol:

- **Immutable batch IDs:** each corrected file version gets a new `batch_id`, preserving historical rejects.
- Or **reconcile rejects:** delete or mark resolved any rows that now validate cleanly.

Never wipe reject history in production if audit traceability is required.

## 19. Creating an Audit Trigger on the Target Table

Suppose the system must log every actual change applied to `orders`.

```sql
CREATE TABLE lesson_bulk_load.order_audit (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    old_row JSONB,
    new_row JSONB,
    event_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION lesson_bulk_load.audit_orders()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO lesson_bulk_load.order_audit (
            order_id, action, old_row, new_row
        )
        VALUES (
            NEW.order_id, 'INSERT',
            NULL, to_jsonb(NEW)
        );

    ELSIF TG_OP = 'UPDATE' THEN
        IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            INSERT INTO lesson_bulk_load.order_audit (
                order_id, action, old_row, new_row
            )
            VALUES (
                NEW.order_id, 'UPDATE',
                to_jsonb(OLD), to_jsonb(NEW)
            );
        END IF;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO lesson_bulk_load.order_audit (
            order_id, action, old_row, new_row
        )
        VALUES (
            OLD.order_id, 'DELETE',
            to_jsonb(OLD), NULL
        );
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_orders_audit
AFTER INSERT OR UPDATE OR DELETE
ON lesson_bulk_load.orders
FOR EACH ROW
EXECUTE FUNCTION lesson_bulk_load.audit_orders();
```

### Execution Order

Create the trigger **before inserting rows from staging**. Creating it after data already loaded will not backfill audit history.

### Why AFTER ROW?

`AFTER ROW` triggers inspect finalized `NEW`/`OLD` values and log history into a separate table. For a multi-row `INSERT ... SELECT`, the function runs once per row, adding CPU, JSONB serialization, index writes, and WAL overhead.

## 20. Merging Valid Rows with UPSERT

Still inside the transaction after creating the trigger:

```sql
INSERT INTO lesson_bulk_load.orders AS o (
    tenant_id,
    source_key,
    customer_ref,
    amount,
    ordered_on
)
SELECT
    tenant_id,
    source_key,
    customer_ref,
    amount,
    ordered_on
FROM tmp_orders_checked
WHERE reject_reason IS NULL
ON CONFLICT (tenant_id, source_key)
DO UPDATE
SET customer_ref = EXCLUDED.customer_ref,
    amount = EXCLUDED.amount,
    ordered_on = EXCLUDED.ordered_on
WHERE (
    o.customer_ref,
    o.amount,
    o.ordered_on
) IS DISTINCT FROM (
    EXCLUDED.customer_ref,
    EXCLUDED.amount,
    EXCLUDED.ordered_on
);
```

### Role of the Unique Constraint

`ON CONFLICT (tenant_id, source_key)` needs a matching unique arbiter. Without that unique index/constraint, UPSERT cannot identify matching source orders.

### Why Include WHERE IS DISTINCT FROM?

When re-running the same batch, unchanged existing rows trigger zero `UPDATE`s. This cuts:

- Heap tuple churn.
- Audit trigger events.
- WAL and index maintenance overhead from redundant writes.

### Why Still Deduplicate in Staging?

A single `INSERT ... ON CONFLICT DO UPDATE` **cannot affect the same target row twice in one statement**. If inputs contain two rows sharing `(tenant_id, source_key)` and both reach UPSERT, PostgreSQL raises a cardinality violation. `row_number()` in classification picks one deterministic winner beforehand.

## 21. Committing and Inspecting Results

After merging:

```sql
COMMIT;

SELECT
    tenant_id,
    source_key,
    customer_ref,
    amount,
    ordered_on
FROM lesson_bulk_load.orders
ORDER BY tenant_id, source_key;

SELECT
    action,
    count(*) AS events
FROM lesson_bulk_load.order_audit
GROUP BY action
ORDER BY action;

SELECT
    row_no,
    reason
FROM lesson_bulk_load.load_rejects
WHERE batch_id = 'B-2026-11'
ORDER BY row_no;
```

With the sample dataset on an initially empty target, expect:

- Target holds 3 valid orders.
- Rejects holds 4 rows.
- Audit records 3 `INSERT` events for the inserted orders.

### Do Not Confuse Accepted Count with Actual INSERT Count

On batch replays, accepted rows may **already exist**; `UPSERT` with `WHERE ... IS DISTINCT FROM` performs zero DML on unchanged rows. Thus, accepted rows in a file do **not** always equal newly inserted rows.

### Note on Creating Trigger Functions Inside a Transaction

In this lab flow, the audit trigger was created after `BEGIN`; PostgreSQL DDL is transactional and commits with the batch. In production, deploy schemas and triggers via dedicated migrations beforehand to avoid prolonged DDL locks and separate privileges.

## 22. Why Both Validate in Staging and Keep Target Constraints?

They serve distinct purposes:

**Staging validation:**

- Pinpoints **which error** occurred on **which row**.
- Helps users repair source inputs.
- Classifies data for reprocessing.
- Supports batch error-rate thresholds.

**Target constraints:**

- Guarantee no code path (`COPY`, `INSERT`, `UPDATE`, batch job, admin tool) ever writes invalid data.
- Guard against race conditions if reference data changes between validation and merge.
- Provide a strong contract for downstream readers.

Validating in staging while disabling target FKs or `CHECK`s leaves the database vulnerable to every other writer.

## 23. When Direct COPY into the Target Table Fits

When the source is known-clean and needs a simple atomic load:

```text
\copy lesson_bulk_load.orders (tenant_id,source_key,customer_ref,amount,ordered_on) FROM '/client/path/clean-orders.csv' WITH (FORMAT csv, HEADER true)
```

PostgreSQL still enforces target constraints and fires applicable triggers, incurring costs for:

- Unique/PK index updates.
- FK lookups.
- `CHECK` evaluation and type conversion.
- Maintaining `ix_orders_tenant_date`.
- `AFTER INSERT` audit logging per row.

### A Difference Regarding Identity Columns

`order_id` is omitted from the COPY column list, so PostgreSQL generates identity values. If migrating historical IDs, evaluate identity semantics (`OVERRIDING` / `GENERATED BY DEFAULT`) and sequence alignment—never reassign IDs arbitrarily if other tables reference them.

### What If Rows Have Errors?

Direct `COPY` cannot run `INSERT ... ON CONFLICT DO UPDATE` UPSERT logic. Duplicates or missing FKs abort the `COPY`. Whenever reconciling imperfect or overlapping sources, staging is usually better.

## 24. What Happens When COPY Fails Partway Through?

By default, a single bad row aborts `COPY FROM` and fails the statement. Inside an explicit transaction, the unhandled error aborts the transaction, requiring `ROLLBACK`.

### Important Disk Behavior

Tuples already written to the heap before the error still consume physical storage even though they never become visible committed rows. PostgreSQL may need `VACUUM` to reclaim space after a massive failed `COPY`.

### On-Error Support Depends on Version

Newer PostgreSQL versions support `ON_ERROR ignore` and related options for certain formats and conversion errors. **Never assume every PostgreSQL version ignores every error class**: unique violations, FK errors, trigger exceptions, and CSV structural errors obey stricter rules—check documentation for your exact version.

For pipelines requiring complete rejection reports and controlled repair/retry, raw staging remains clear and version-independent.

## 25. COPY and Row Triggers

A table with an `AFTER INSERT` row trigger invokes that trigger for every row inserted by `COPY`.

Across 5 million rows, trigger costs can include:

- Invoking PL/pgSQL 5 million times.
- Converting each row to JSONB.
- Inserting 5 million audit rows.
- Maintaining indexes on the audit table.
- Generating WAL for both target and audit tables.

### Not Every Trigger Writes Full Row Snapshots

A lightweight `BEFORE` trigger normalizing one column adds modest overhead, whereas an `AFTER` trigger issuing extra SQL queries per row creates a severe bottleneck.

### Correctness Considerations

When auditing is mandatory, disabling triggers for speed breaks the audit chain. Switch audit mechanisms only with an approved alternative preserving provenance and compliance.

## 26. Triggers and Constraints Are Not Interchangeable

| Mechanism | During Load | Interchangeable? |
|---|---|---|
| `NOT NULL` | Blocks missing values | Never replace with staging-only checks |
| `CHECK` | Enforces per-row predicate | Triggers do not match full semantics |
| `UNIQUE/PK` | Prevents duplicates, enables `ON CONFLICT` | Staging `ROW_NUMBER` cannot replace target arbiter |
| `FOREIGN KEY` | Guarantees referenced parent exists | Pre-load `LEFT JOIN` still has check-then-insert races |
| `BEFORE` trigger | Custom normalization/validation | Simple logic often belongs in `CHECK`/generated columns |
| `AFTER` trigger | Auditing and side effects | Account for overhead and transaction semantics |
| Non-unique query index | Speeds `SELECT`, slows writes | Can be built post-load on offline tables |

A **constraint** expresses an enduring engine-enforced data invariant. A **trigger** defines behavior on DML events. Never view them as equivalent ways to "validate inputs".

## 27. Using FOREIGN KEYs with Large Loads

The FK on `orders(tenant_id, customer_ref)` references `customers`. During `COPY` or `INSERT` into target, PostgreSQL verifies every referenced key.

### Common Slowdown Factors

- Index lookups against parent keys.
- Locks and concurrent writes on parent rows.
- High row volume multiplying relational checks.
- Index cache hit ratios.

### Safe Practices

1. Load parent table `customers` before child table `orders`.
2. Filter missing FKs out in staging.
3. Keep PK/unique indexes on referenced parent columns.
4. Monitor lock waits if loads stall.
5. When loading a **fresh offline table**, consider adding FKs afterward and validating per plan.

Never disable FK constraint triggers on a live production table just for load speed and assume data remains valid.

## 28. Foreign Keys Are Implemented via Internal Constraint Triggers

In PostgreSQL, foreign keys execute using internal **constraint triggers**. Therefore:

```sql
-- Very dangerous if used in the wrong environment:
-- ALTER TABLE lesson_bulk_load.orders DISABLE TRIGGER ALL;
```

can affect not only business audit triggers, but also referential integrity triggers (depending on privileges, trigger types, and commands).

### Why This Is Discouraged

- Allows orphan rows to enter.
- Re-enabling triggers does not retroactively fix bad rows.
- Disabling internal constraint triggers can require superuser or elevated privileges.
- Concurrent apps can write corrupt data while invariants are off.

Even if you run a post-load check, any window where a live table accepts invalid data violates invariants. Prefer staging, offline constraint creation, or `NOT VALID`/`VALIDATE CONSTRAINT` where applicable.

## 29. NOT VALID for CHECK and FOREIGN KEY

On a table **already holding data**, you can add certain constraints without **scanning all existing rows immediately at `ADD CONSTRAINT` time**:

```sql
-- Illustrative on an eligible table; skip if constraint name already exists:
ALTER TABLE lesson_bulk_load.orders
ADD CONSTRAINT chk_orders_upper_amount
CHECK (amount <= 1000000000)
NOT VALID;
```

Key behaviors:

- `NOT VALID` skips validating **existing rows** when adding the constraint.
- All new `INSERT`/`UPDATE` operations are checked immediately.
- Once legacy rows are cleaned up, run `VALIDATE CONSTRAINT`:

```sql
ALTER TABLE lesson_bulk_load.orders
VALIDATE CONSTRAINT chk_orders_upper_amount;
```

### Supported Constraint Types Only

Do not treat `NOT VALID` as universal across every constraint type. It applies commonly to `CHECK` and `FOREIGN KEY`; uniqueness and primary keys rely on unique indexes and cannot simply be declared `UNIQUE ... NOT VALID`.

### Plan Locking Carefully

Adding and validating constraints still acquires locks and scans tables. `VALIDATE CONSTRAINT` typically reduces blocking of concurrent writes compared to immediate full-table validation at `ADD CONSTRAINT`, yet it is not free—review lock behavior for your workload.

## 30. Adding FKs After Loading a Fresh Table

Suppose a newly loaded table already has `(tenant_id, customer_ref)` columns without an FK yet.

Pattern under managed schema changes:

```sql
ALTER TABLE lesson_bulk_load.orders
ADD CONSTRAINT fk_orders_extra_example
FOREIGN KEY (tenant_id, customer_ref)
REFERENCES lesson_bulk_load.customers (
    tenant_id, customer_ref
)
NOT VALID;

ALTER TABLE lesson_bulk_load.orders
VALIDATE CONSTRAINT fk_orders_extra_example;
```

This adds an FK duplicating `fk_orders_customer` already present in the lab, so **do not run it** unless testing on a copy lacking the FK. In production, duplicate FKs add pure overhead.

### Recommended Sequence

1. Build referenced PK/unique index on the parent table.
2. Load and clean the child table.
3. Run an anti-join to catch orphan rows.
4. Add FK `NOT VALID` if minimizing initial lock duration.
5. Run `VALIDATE CONSTRAINT`.
6. Ensure all subsequent writers operate under the enforced FK.

## 31. Finding Orphan Records Before VALIDATE

Example:

```sql
SELECT
    o.tenant_id,
    o.customer_ref,
    count(*) AS affected_orders
FROM lesson_bulk_load.orders AS o
LEFT JOIN lesson_bulk_load.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_ref = o.customer_ref
WHERE c.customer_ref IS NULL
GROUP BY o.tenant_id, o.customer_ref
ORDER BY affected_orders DESC;
```

With the lab FK enforced from the start, expect **0 rows** unless constraints were bypassed or manually altered.

### Why Pre-Check?

If `VALIDATE CONSTRAINT` hits an orphan in a massive table, it aborts and forces you to fix and re-scan. A batched anti-join reveals all broken references upfront for structured cleanup.

Still, pre-checks **never replace official validation** because concurrent writers can alter rows; the validated constraint provides the final guarantee.

## 32. CHECK Constraints and NULL Semantics

In PostgreSQL, `CHECK` rejects rows only when the expression evaluates to **FALSE**; if it evaluates to SQL `NULL`, the row passes. Hence:

```sql
CHECK (amount >= 0)
```

does not enforce `amount NOT NULL`.

### Proper Design

```sql
amount NUMERIC(14,2) NOT NULL
    CHECK (amount >= 0)
```

Two constraints solve two problems: missing values and negative values.

### Relevance to Staging

If `amount_raw` fails to parse and turns into `NULL`, staging classification must reject it. Passing `NULL` into a `NOT NULL` target fails too, yet target-level errors lack helpful `(batch_id, row_no)` diagnostics.

## 33. UNIQUE Constraints and Building Indexes Before vs. After Load

In PostgreSQL, primary keys and unique constraints are backed by unique indexes. Every new row forces the engine to verify key uniqueness.

**Loading a fresh offline table:** loading the heap first and creating indexes/constraints afterward is often faster than updating multiple indexes per row; however, while uniqueness is absent, duplicates can slip in. Only use this when the table is hidden from writers/readers and validated before cutover.

**Loading a live online table:** never drop unique arbiters that live requests rely on; keep existing constraints/indexes, stage data, and merge in batches.

### Decision by Scenario

| Scenario | Approach |
|---|---|
| Fresh empty offline table, clean data | `COPY` first, then build secondary indexes/constraints |
| Online table with `UPSERT` | Keep unique index so `ON CONFLICT` works |
| Query-only index unused during load | Can be created after bulk loading on a new table |
| Index backing production SLAs | Never drop for load speed without a downtime plan |
| New unique constraint on large existing table | Deduplicate first, then build unique index concurrently |

There is no rule saying "always drop all indexes before COPY". On live tables, dropping and rebuilding causes app failures, locks, and integrity gaps.

## 34. How Secondary Indexes Slow Down INSERTs

When one row enters `orders`:

```text
heap INSERT
 ├── PK index (order_id)
 ├── UNIQUE index (tenant_id, source_key)
 └── B-tree index (tenant_id, ordered_on, order_id)
      + WAL / index page activity
```

Adding five more indexes means maintaining five more index trees on every single row. Overhead grows with index type, page splits, cache misses, fillfactor, and key randomness.

### When to Build Indexes Afterward

For a fresh import table not yet serving clients:

1. Create the table with its base schema.
2. `COPY` validated data.
3. Build secondary indexes in bulk.
4. Add/validate remaining constraints.
5. Run `ANALYZE`.
6. Verify everything, then expose the table.

Keep uniqueness and FK correctness intact across steps—never drop a unique index if your load pipeline itself needs `ON CONFLICT`.

## 35. Standard CREATE INDEX

Example reporting index:

```sql
CREATE INDEX ix_orders_customer_date
ON lesson_bulk_load.orders (
    tenant_id,
    customer_ref,
    ordered_on DESC
);
```

Standard index creation takes locks that block concurrent writes. On fresh offline tables, this is acceptable and faster than concurrent builds.

### Avoid Redundant Indexes

If a similar index already covers the query pattern, adding another increases storage and write overhead for zero plan gain. Check `pg_indexes`, real queries, and `EXPLAIN` first in production.

## 36. CREATE INDEX CONCURRENTLY on Live Online Tables

On tables actively serving writes:

```sql
-- Top-level command; cannot run inside BEGIN ... COMMIT:
CREATE INDEX CONCURRENTLY ix_orders_status_date
ON lesson_bulk_load.orders (
    tenant_id,
    ordered_on DESC
);
```

`CREATE INDEX CONCURRENTLY` avoids blocking concurrent inserts, updates, and deletes compared to standard builds, though it incurs higher total work and duration.

### Three Important Limits

1. **Cannot run inside an explicit transaction block.**
2. Can take much longer, waiting on older active transactions and adding extra I/O.
3. If it fails, it can leave behind an **invalid index** that must be inspected and cleaned up.

### Why Not Use It on Every Fresh Table?

An offline table with no concurrent writers has no reason to pay concurrent build overhead. Conversely, on live production tables, concurrent builds can be scheduled safely.

## 37. Checking Index Validity After Building

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS index_name,
    i.indisvalid AS valid_for_queries,
    i.indisready AS ready_for_insert_updates,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
  ON c.oid = i.indexrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lesson_bulk_load'
ORDER BY c.relname;
```

An invalid index left by a failed `CREATE INDEX CONCURRENTLY` still consumes disk space and can continue adding write overhead (`indisready=true` while `indisvalid=false`).

### Remediation

Identify the exact invalid index; with appropriate privileges and version, run `REINDEX INDEX CONCURRENTLY` or drop/rebuild it under an approved plan. Never drop arbitrary indexes that constraints or apps depend on.

## 38. Creating a Unique Index on an Already-Loaded Table

When a newly loaded table lacks a unique constraint yet:

1. Search raw/typed rows for duplicates.
2. Clean duplicates or apply a conflict policy.
3. Create the unique index on the true business key.
4. Attach the index as a constraint if needed, or use it as a unique arbiter.

Duplicate detection query:

```sql
SELECT tenant_id, source_key, count(*) AS occurrences
FROM lesson_bulk_load.orders
GROUP BY tenant_id, source_key
HAVING count(*) > 1
ORDER BY occurrences DESC;
```

In the lab, `UNIQUE` already exists, so this returns zero rows.

### Never Use UNIQUE ... NOT VALID

`NOT VALID` applies to constraints like `CHECK` and `FK`—not as a way to create an unvalidated unique constraint over dirty legacy data.

On online tables, you can build a unique index concurrently and attach it with `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` when eligible—checking columns, expressions/partial predicates, ownership, partitioning, and migration locks carefully.

## 39. Indexes Supporting Foreign Keys on Both Sides

PostgreSQL requires referenced parent columns of a foreign key to have a matching PK or unique index/constraint. However, **it does not automatically index referencing columns on the child table**.

For `orders(tenant_id, customer_ref)`:

```sql
CREATE INDEX ix_orders_customer_fk
ON lesson_bulk_load.orders (
    tenant_id,
    customer_ref
);
```

This index helps when:

- Querying orders by customer.
- Parent customer rows are updated or deleted and PostgreSQL must scan referencing child rows.
- Queries join on that key pair.

### Do Not Create Blindly

Every index adds bulk-load write amplification. If workloads never query orders by customer and parent keys rarely update or delete, benchmark and check query plans first. Tailor indexes to real queries and load patterns rather than mechanically indexing every FK.

## 40. Audit Triggers and Row-by-Row Overhead

In our lab, each `INSERT` into `orders` writes an audit row via an `AFTER ROW` trigger.

Loading 1 million orders multiplies writes into:

```text
orders:      1,000,000 rows
order_audit: 1,000,000 events
```

Furthermore, each audit row stores a JSONB snapshot, making total bytes written far larger than `orders` alone.

### Not All Auditing Is Wasteful

When compliance requires proving which batch inserted what, when, and how rows changed, auditing has real business value. Optimize it wisely:

- Data minimization: log only required columns.
- Record `batch_id` and provenance cleanly.
- Keep indexes minimal on the audit table.
- Partition and enforce retention on audit logs.
- Never issue synchronous HTTP or network calls from triggers.

## 41. Statement-Level Triggers and Transition Tables

For bulk workloads, `AFTER ... FOR EACH STATEMENT` paired with **transition tables** processes all changed rows in a single `INSERT ... SELECT` instead of calling PL/pgSQL per row.

To avoid duplicating audit writes on `orders`, create a separate demo table:

```sql
CREATE TABLE lesson_bulk_load.bulk_demo (
    item_id BIGINT PRIMARY KEY,
    qty INTEGER NOT NULL CHECK (qty >= 0)
);

CREATE TABLE lesson_bulk_load.bulk_demo_history (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id BIGINT NOT NULL,
    new_qty INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION lesson_bulk_load.log_bulk_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson_bulk_load.bulk_demo_history (
        item_id, new_qty
    )
    SELECT item_id, qty
    FROM inserted_rows;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_bulk_demo_history
AFTER INSERT
ON lesson_bulk_load.bulk_demo
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION lesson_bulk_load.log_bulk_demo();

INSERT INTO lesson_bulk_load.bulk_demo (item_id, qty)
SELECT g, g % 100
FROM generate_series(1, 10000) AS g;

SELECT count(*) AS logged_rows
FROM lesson_bulk_load.bulk_demo_history;
-- 10000
```

### Key Benefit

One `INSERT` of 10,000 rows fires the statement trigger function **once**, with `inserted_rows` holding all newly inserted rows.

### Limitations

- Transition tables are supported only for specific timing/event/target combinations.
- Statement triggers fire even when 0 rows are affected (with an empty transition table).
- Never swap row-level logic to transition tables without checking trigger ordering, partitioned tables, and `OLD`/`NEW` row pairing needs.
- If `COPY` is chunked across multiple statements, each statement gets its own transition batch—do not expect one file-wide transition table when loaders split chunks.

## 42. BEFORE Triggers Can Alter Data Before Constraints Run

A `BEFORE INSERT` trigger can:

- Normalize strings.
- Compute business defaults.
- Reject bad rows.
- Modify `NEW.column`.

Yet if a trigger silently turns a negative `amount` into `0` instead of rejecting it, that is a **major business decision**: users never learn their input was wrong and silently altered.

### Guidance

Separate clearly:

1. **Lossless normalization:** trim whitespace when allowed by contract.
2. **Validation and rejection:** negative amounts, missing customers.
3. **Auditing actual changes:** log final accepted payloads.

Never use triggers to silently "heal" dirty data in bulk pipelines.

## 43. Triggers Do Not Run as Independent Transactions

A `COPY FROM` or `INSERT ... SELECT` may invoke a trigger thousands of times, all inside the **caller's transaction**.

If an audit trigger fails with an unhandled exception:

- The load statement fails.
- Target rows never partially commit just because earlier row triggers ran.
- An explicit transaction enters an aborted state requiring `ROLLBACK`.

This keeps **data and audit** atomic together, provided auditing runs inside the transaction and isn't bypassed.

### Never Confuse Auditing with External Network Outboxes

Triggers must never fire external HTTP calls expecting PostgreSQL to roll back remote side effects on failure. To publish events externally, use a **transactional outbox** table and an asynchronous publisher.

## 44. Transaction Size: Large or Small?

**One giant transaction:**

- Guarantees all-or-nothing atomicity for the whole batch.
- Few commit boundaries.
- Holds locks and snapshots for long periods, spiking WAL and rollback cost.
- A late failure forces restarting from scratch.

**Many small transactions:**

- Bounds the blast radius of errors.
- Simplifies progress checkpointing and resumption.
- Releases locks per batch.
- Yields only **partial atomicity**, unless paired with shadow tables/cutover.

### Choose by Business Requirement

If a dataset must become visible only as a complete whole, load a **separate staging/shadow table** across multiple transactions, validate fully, and perform an **atomic cutover** where feasible.

For continuous online target updates, use idempotent microbatches, a progress journal, and batch status indicators until reconciliation finishes.

## 45. 10,000-Row Chunking Example

Suppose staging holds millions of rows for `batch_id='B-LARGE'`. A coordinator can slice by `row_no`:

```sql
-- Chunk 1: rows 1 through 10000
SELECT *
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-LARGE'
  AND row_no BETWEEN 1 AND 10000;

-- Chunk 2: rows 10001 through 20000
SELECT *
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-LARGE'
  AND row_no BETWEEN 10001 AND 20000;
```

This illustrates **chunk slicing**, not the complete pipeline. Within each chunk:

1. Cast/validate rows within that `(batch_id, row_no)` slice.
2. Persist rejects.
3. `UPSERT` accepted rows.
4. Record chunk checkpoint/progress.
5. Commit.

### Why Avoid OFFSET Pagination?

On huge tables, high `OFFSET` wastes scan work skipping rows and drifts if data changes. Always slice by **keyset/range** on a stable indexed key or queue/partition ID.

### Choosing Chunk Size

There is no universal "10,000 is always best". Test 1,000, 5,000, 10,000, 50,000 based on row width, index/trigger cost, latency, checkpoint size, and rollback overhead.

## 46. Atomicity and Resumability on Failure

A pipeline processing 100 chunks:

```text
Chunk 1..47 COMMITTED
Chunk 48 FAILED
Chunk 49..100 NOT STARTED
```

If batch metadata only marks `DONE` after all 100 chunks finish, downstream consumers must not treat the target as a complete dataset at chunk 1.

### Two Publishing Models

**Online upsert:** rows become visible chunk by chunk; fits incremental feeds paired with batch status/watermark metadata.

**Offline replacement/cutover:** load into an unpublished table or partition, validate completely, and switch pointers/views/partitions in a controlled cutover.

### Crucial Point

Once 47 chunks commit directly to a live online target, there is no "whole-batch `ROLLBACK`". If full rollback is mandatory, design versioning, shadow tables, or compensating jobs rather than relying on a single SQL `ROLLBACK`.

## 47. Idempotency via Source Keys

If the network drops right after `COMMIT`, the loader misses the ACK. On retry:

```sql
INSERT INTO ... ON CONFLICT (tenant_id, source_key) DO UPDATE ...
```

with a stable unique key can converge on the same **final state** instead of creating duplicates.

### Prerequisites

- Keys come from a trusted source and never mutate after creation.
- Merge logic is semantically idempotent.
- No-op updates are skipped when data has not changed.
- Audit triggers avoid emitting noise events on unchanged replays.
- Checkpoints and side effects stay synchronized.

### Watch Out for Multi-Version Sources

If the same `source_key` arrives twice with different amounts, `UPSERT` overwrites with the newer payload—which might be a valid correction or a source bug. Enforce **latest-wins by version/timestamp** or conflict-rejection rules rather than arbitrary file order.

## 48. Batch Registry and State Tracking

An import management table:

```sql
CREATE TABLE lesson_bulk_load.load_batches (
    batch_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_checksum TEXT,
    status TEXT NOT NULL
        CHECK (status IN (
            'RECEIVED', 'VALIDATING', 'APPLYING',
            'COMPLETED', 'FAILED'
        )),
    total_rows BIGINT,
    rejected_rows BIGINT,
    applied_rows BIGINT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ
);
```

### Purpose

- Detect duplicate submissions of the same file/batch.
- Track active progress.
- Anchor checksums and provenance.
- Keep **accepted**, **applied**, and **rejected** counts distinct.
- Transition to `COMPLETED` only after all validations and checkpoints pass.

### Never Revert Status Arbitrarily

If a client resubmits a different payload under an already-`COMPLETED` `batch_id`, reject it or allocate a new batch version—never overwrite raw history and destroy provenance.

## 49. COPY into UNLOGGED Staging

PostgreSQL supports `UNLOGGED` tables:

```sql
CREATE UNLOGGED TABLE lesson_bulk_load.raw_fast_stage (
    batch_id TEXT NOT NULL,
    row_no BIGINT NOT NULL,
    payload JSONB NOT NULL
);
```

### Potential Benefit

Eliminates WAL writes for the unlogged table's data, speeding up staging loads in suitable workloads.

### Major Trade-Offs

- Unlogged data is **not crash-safe**; PostgreSQL truncates unlogged tables after an unclean crash/recovery.
- Contents are not replicated to physical standbys via streaming replication.
- Requires the ability to **re-read the source** if staging is lost.
- Never use `UNLOGGED` as the sole copy of critical data.

### When It Fits

When raw source files remain safely archived in object storage with checksums so staging can always be rebuilt after a crash. If staging holds the only copy of a partner file, `UNLOGGED` is a serious risk.

## 50. TEMP Staging and Connection Pools

A `TEMP TABLE` lives inside a **single PostgreSQL session**, not shared across pooled connections.

If an app creates a temp table on connection A and later borrows connection B from HikariCP, connection B cannot see the temp table.

Under PgBouncer **transaction pooling**, the very next transaction may land on a different backend process, losing session-level temp table state across commits.

### Safe Practices

- Keep temp table creation, usage, and drop inside one connection/transaction where appropriate.
- Use persistent logged/unlogged staging tables for multi-worker pipelines.
- If a temp table must span transactions, require session pooling or a dedicated connection.
- Never assume an HTTP request gets pinned to the same physical backend across pool checkouts.

### ON COMMIT DROP

The lab temp tables use `ON COMMIT DROP`, auto-dropping on commit. That fits a self-contained single-transaction validate-and-merge flow, not multi-day error review—persist rejects into durable tables before committing.

## 51. COPY FREEZE Is Not a Constraint-Bypass Switch

PostgreSQL offers `COPY ... WITH (FREEZE ...)` for certain fresh-load scenarios. Its purpose is avoiding later tuple freezing work under strict conditions—**not** disabling FKs, `CHECK`s, `UNIQUE`, or transaction semantics.

### Strict Preconditions

It applies under narrow conditions, such as the table being newly created or truncated within the current subtransaction with no conflicting snapshots/portals, and is unsupported on certain targets such as partitioned tables under current PostgreSQL rules.

### Warning

`FREEZE` alters MVCC tuple visibility semantics in special cases. Never enable it blindly thinking "big load = use FREEZE"; read your version's docs and test replication and snapshot visibility thoroughly.

In standard online staging/merge pipelines, `COPY FREEZE` is usually unnecessary.

## 52. WAL Is the Price of Durability

For logged tables, bulk loads generate WAL for crash recovery and replication. WAL sources include:

- Heap `INSERT`/`UPDATE` records.
- Index page writes and splits.
- Trigger writes into audit tables.
- Visibility map and free-space map updates.
- Full-page images after checkpoints per settings.
- DDL and index-build operations.

### Why Monitor WAL?

A 10 GB CSV does not imply only 10 GB of data files or 10 GB of WAL. Multiple indexes, JSONB audit logs, and `UPSERT` updates multiply total write amplification dramatically.

### Never Disable WAL for Business Tables

Lowering cluster `wal_level` or weakening durability just for load speed compromises backups, PITR, and replication. Tune durability around recovery SLAs, not as an ad-hoc import trick.

## 53. synchronous_commit and Durability Trade-Offs

In some setups, `synchronous_commit` is adjusted to alter how long commits wait for local WAL flush or synchronous replica acknowledgment.

Inspect settings only:

```sql
SHOW synchronous_commit;

SELECT name, setting, context
FROM pg_catalog.pg_settings
WHERE name = 'synchronous_commit';
```

### Do Not Disable Unconditionally

`synchronous_commit = off` lowers commit latency for specialized workloads, yet acknowledged transactions can **vanish on a crash** within the durability window. If an import cannot be replayed or `COMPLETED` was already published externally, that data loss may be unacceptable.

Always balance ingest throughput against transaction durability and replayability from checksummed raw sources.

## 54. Checkpoints and Heavy Write Loads

Bulk loads dirty many buffer pages and spike checkpoint activity. Monitor:

- WAL bytes per second.
- Checkpoint duration and writeback latency.
- Disk queue depth and I/O latency.
- Replica lag.
- CPU utilization.
- Burst commit frequency.

### How to Tune?

Never blindly apply "magic numbers" to `shared_buffers`, `max_wal_size`, `checkpoint_timeout`, and pool sizes all at once. Identify whether the bottleneck is disk, checkpoints, index maintenance, or row triggers first, then benchmark one change at a time.

### Staging and Replication

`UNLOGGED` staging cuts WAL for temporary data, yet logged target tables and audit logs still emit full WAL during merge. Eliminating WAL in one stage does not eliminate write amplification across the pipeline.

## 55. VACUUM and ANALYZE After Loading

After bulk loads, planner **statistics** can lag behind the new data distribution, causing poor query plans.

```sql
ANALYZE lesson_bulk_load.orders;

ANALYZE lesson_bulk_load.customers;
```

### Distinguish Both

**ANALYZE** collects statistics for the query planner.

**VACUUM** reclaims/recycles dead tuples, updates visibility maps, and helps prevent transaction ID wraparound.

**VACUUM ANALYZE** combines both when needed:

```sql
VACUUM (ANALYZE) lesson_bulk_load.orders;
```

### Never Run VACUUM Inside a Transaction Block

`VACUUM` cannot execute inside an explicit transaction block. Schedule it post-commit as needed, avoiding heavy I/O windows during peak production traffic.

### Should You VACUUM Immediately After a Clean COPY?

Pure `COPY INSERT`s rarely need `VACUUM FULL`. When few dead tuples exist, `ANALYZE` matters most while autovacuum handles routine cleanup. After failed `COPY`s or heavy `UPSERT` updates, dead tuples accumulate and `VACUUM` helps.

## 56. Autovacuum During Bulk Imports

Autovacuum cleans dead tuples and refreshes statistics based on table-change thresholds. Rapid bulk growth shifts when autoanalyze and autovacuum trigger.

### Mistake

Disabling autovacuum cluster-wide to free I/O for an import and forgetting to re-enable it. That invites bloat, stale plans, and long-term wraparound emergencies.

### Better Options

- Track when autoanalyze fires.
- Run explicit `ANALYZE` after major batches.
- Tune per-table autovacuum parameters only when evidence warrants it.
- Coordinate bulk import windows with maintenance schedules.
- Monitor dead tuples, vacuum progress, and bloat.

## 57. pg_stat_progress_copy

PostgreSQL provides `pg_stat_progress_copy` in supported versions to inspect active `COPY` backends:

```sql
SELECT
    pid,
    datid,
    relid::regclass AS target_relation,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_catalog.pg_stat_progress_copy;
```

### Interpreting Output

- `command` shows the `COPY` direction.
- `type` indicates source/destination mechanism (file, program, pipe, callback per version).
- `bytes_processed` tracks bytes handled so far.
- `bytes_total` may be unknown/0 for streams.
- `tuples_processed` shows processed row progress per view semantics.

**Never treat a counter in this view as committed rows.** A running `COPY` can still roll back, and a quick `COPY` finishes before polling catches it.

### Version Differences

Available columns evolve across releases—for example, newer versions add counters for excluded and skipped tuples. Check `\d pg_stat_progress_copy` in `psql` or view metadata on older servers.

## 58. Monitoring Index Build Progress

For large index builds:

```sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done
FROM pg_catalog.pg_stat_progress_create_index;
```

The view reports phases such as scanning table, sorting tuples, waiting for lockers, and validation depending on index type and version.

### Watch Out During CREATE INDEX CONCURRENTLY

Long waits often reflect waiting on old open transactions rather than slow disks. If the build sits in a waiting phase, raising `maintenance_work_mem` or killing unknown backends blindly will not help.

## 59. Post-Load Table Statistics

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_analyze,
    last_autoanalyze,
    last_vacuum,
    last_autovacuum
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_bulk_load'
ORDER BY relname;
```

### Never Use n_live_tup as an Exact Count

`n_live_tup` is a **statistical estimate**, never a replacement for `SELECT count(*)` in exact reconciliation. Cumulative counters can also be reset; measure deltas across timestamps and check stats reset times.

## 60. Spotting Progress and Bottlenecks in pg_stat_activity

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Key signals:

- `wait_event_type = 'Lock'`: loader is waiting on index, row, or table locks.
- I/O wait events: storage throughput is saturated.
- High `query_age`: long-running `COPY`, index build, or merge.
- `idle in transaction`: worker holding locks/snapshots while stalled between queries.

### Privacy Warning

`query` can expose SQL literals and sensitive data if apps omit bind parameters. Restrict monitoring privileges and never leak full queries or credentials onto public dashboards.

## 61. Replica Lag During Large Loads

Under streaming replication, bulk loads generate WAL that standbys must receive and replay. Effects:

- Read replicas fall behind.
- Read-after-write queries routed to replicas miss newly committed rows.
- Replication slots/retention retain large WAL volumes.
- Failover readiness degrades while lag grows.

### Metrics to Watch

- WAL generation rate.
- WAL sent/write/flush/replay LSN positions.
- Replica replay delay.
- Free disk on primary and standbys.
- Logical replication slot lag if applicable.

### Business Impact

Never declare data "globally visible everywhere" right after primary `COMMIT` if readers query replicas requiring low staleness. Define completion explicitly: **committed on primary**, **replicated to standby**, or **published to analytics**.

## 62. COPY Security and Privileged Roles

Server-side `COPY FROM '/server/file'`, `COPY PROGRAM`, and server-side `COPY TO` require elevated privileges designed for server file and program access.

### Never Grant Them Just for Convenience

Normal ingestion services only need table/staging privileges and client-side `COPY` protocol streaming. Never grant OS program execution or arbitrary DB-host filesystem reads to app roles.

### Additional Hardening

- Require TLS with server identity verification.
- Inject credentials via secret managers.
- Protect inbound CSVs in object storage with tight IAM policies.
- Restrict PII in temporary staging and reject tables.
- Keep secrets out of SQL logs and job metadata.
- Separate importer roles from schema migration/admin roles.
- Never allow importers to disable triggers or FKs.

## 63. COPY and Row-Level Security

PostgreSQL restricts `COPY FROM` on tables protected by RLS. Current PostgreSQL docs state `COPY FROM` does not support loading directly into RLS-enabled tables the way `INSERT` does; use `INSERT` statements or load into staging and enforce policies during the merge step.

### Safe Multi-Tenant Architecture

1. `COPY` from source into restricted staging.
2. Ingestion service authenticates the tenant and source scope.
3. Validate tenant IDs and references.
4. Merge under properly scoped roles/policies inside a transaction.
5. Enforce RLS, FKs, uniqueness, and business constraints on target tables.
6. Audit batches and test cross-tenant isolation.

### SECURITY DEFINER Warning

A `SECURITY DEFINER` merge function runs with the owner's privileges and may bypass caller RLS depending on configuration. Never rely on `WHERE tenant_id = p_tenant_id` with a client-supplied parameter as sufficient authorization.

## 64. Parallelizing Multiple Workers for Higher Throughput

A loader can process chunks concurrently:

```text
Staging 10M rows
 ├── worker A: chunk 1
 ├── worker B: chunk 2
 ├── worker C: chunk 3
 └── worker D: chunk 4
           ↓
     PostgreSQL target
```

Yet excessive concurrency causes:

- Contention on shared unique index pages.
- FK and parent-row lock contention.
- Deadlocks when updating overlapping keys in differing order.
- Disk and WAL saturation.
- Autovacuum and replica lag spikes.
- Connection pool exhaustion.

### How to Test

Benchmark concurrency 1, 2, 4, 8... at fixed chunk sizes, measuring:

```text
committed good rows/s
lock waits / deadlocks
WAL bytes/s
CPU, memory, disk latency
replica lag
error / retry rate
```

Optimize for **committed valid rows/s and correctness**, not raw parsed COPY rows.

## 65. Claiming Chunks with a Queue and SKIP LOCKED

A chunk tracking table can use `FOR UPDATE SKIP LOCKED` so workers claim chunks without blocking each other:

```sql
CREATE TABLE lesson_bulk_load.load_chunks (
    batch_id TEXT NOT NULL,
    chunk_no INTEGER NOT NULL,
    first_row BIGINT NOT NULL,
    last_row BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (batch_id, chunk_no)
);
```

Claim pattern (illustrating the transaction):

```sql
BEGIN;

SELECT batch_id, chunk_no, first_row, last_row
FROM lesson_bulk_load.load_chunks
WHERE status = 'PENDING'
ORDER BY batch_id, chunk_no
FOR UPDATE SKIP LOCKED
LIMIT 1;

-- Mark the selected task RUNNING before COMMIT.
COMMIT;
```

### Caveat

Running `SELECT FOR UPDATE` and committing **does not mark the task**; you must `UPDATE` its status inside the same transaction. If a worker crashes after claiming, you also need lease expiration and requeue policies.

`SKIP LOCKED` coordinates queue consumers, yet does not guarantee fair scheduling or exactly-once execution; target idempotency and progress journals are still essential.

## 66. Atomic Claim with UPDATE ... RETURNING

Atomic claim query:

```sql
WITH next_chunk AS (
    SELECT batch_id, chunk_no
    FROM lesson_bulk_load.load_chunks
    WHERE status = 'PENDING'
    ORDER BY batch_id, chunk_no
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE lesson_bulk_load.load_chunks AS q
SET status = 'RUNNING'
FROM next_chunk AS n
WHERE q.batch_id = n.batch_id
  AND q.chunk_no = n.chunk_no
RETURNING
    q.batch_id,
    q.chunk_no,
    q.first_row,
    q.last_row;
```

### Usage

Inside a short committed transaction, a worker claims one chunk and flips its status to `RUNNING`. After merging and reconciling, it marks the chunk `COMPLETED`.

### Production Additions Needed

- Worker ID and lease deadline.
- Heartbeats.
- Attempt counter and retry backoff.
- Dead-letter / failed state.
- Per-chunk checkpoints and counters.
- Fencing against two workers reclaiming the same chunk after a timeout.

Never hold the queue row lock open across a multi-minute import transaction when you can claim fast and execute under a lease.

## 67. Deduplicating Across Chunks

`ROW_NUMBER() OVER (PARTITION BY tenant_id, source_key ORDER BY row_no)` within one chunk catches duplicates **only inside that chunk**. If the same key appears in chunk 2 and chunk 8, both look unique locally.

### Options

- Pre-deduplicate the **entire batch** before slicing chunks.
- Build a batch-wide canonical key table by source/version.
- Keep the target unique constraint and `ON CONFLICT` as a backstop.
- Define explicit ordering/version rules to pick the winner.
- Fail/reject if cross-chunk duplicates are forbidden.

### Why ON CONFLICT Alone Is Insufficient

`ON CONFLICT` guarantees no two rows share a unique key, yet if two rows disagree on `amount`, it does not know **which one is right**. A "last committer wins" race across parallel workers depends on thread scheduling rather than business logic.

## 68. Version-Aware Merge to Prevent Stale Overwrites

When source data provides a monotonically increasing `source_version` per entity, store it on the target and update only when incoming data is **strictly newer**:

```sql
-- Conceptual pattern once both tables carry source_version:
-- INSERT INTO target AS t (source_key, source_version, ...)
-- SELECT source_key, source_version, ...
-- FROM validated_stage
-- ON CONFLICT (source_key) DO UPDATE
-- SET source_version = EXCLUDED.source_version,
--     ...
-- WHERE t.source_version < EXCLUDED.source_version;
```

### Why?

If chunk 4 commits version 4 before a delayed worker commits chunk 3 with version 3, an unguarded merge would regress state back to version 3.

### Never Assume Timestamps Are Versions

Timestamps from distributed sources suffer clock skew, coarse precision, or non-monotonic ties. Prefer event sequence numbers, LSNs, or source revisions for conflict resolution where available.

## 69. Retrying Whole Transactions on Deadlock / Serialization Failure

During parallel bulk upserts, errors include:

| SQLSTATE | Meaning |
|---|---|
| `40P01` | Deadlock detected |
| `40001` | Serialization failure |
| `23505` | Unique violation |
| `23503` | Foreign key violation |
| `23514` | Check violation |
| `22P02` | Invalid text representation |
| `53300` | Too many connections |
| `57014` | Query canceled (e.g., timeout) |

### Retry Policy

`40P01` and `40001` can safely retry the **entire transaction** with capped attempts and backoff once idempotency is verified.

`23503` usually indicates missing parent data—do not retry blindly forever.

`23505` may indicate unhandled duplicates or concurrency races—classify by key and policy.

`53300` signals connection exhaustion—never respond by spawning more workers.

### Subtle Risk

If a transaction committed right before the connection dropped, the client never learns the outcome from the error alone. Retry safely using batch idempotency keys and reconciliation rather than guessing from exception text.

## 70. Timeouts and Stopping a Batch

Key timeouts to configure:

- `statement_timeout`: bounds single SQL statement duration.
- `lock_timeout`: bounds lock wait time.
- `idle_in_transaction_session_timeout`: prevents abandoned open transactions.
- Pool acquisition timeout: bounds connection wait.
- Client socket/network timeouts: prevents hung I/O.

### Never Use One Fixed Timeout for Every Workload

An HTTP API may use a few-second `statement_timeout`, whereas bulk loads and `CREATE INDEX` need longer windows. Scope timeouts per role or `SET LOCAL` inside authorized batch workers.

### Aborting a COPY

If a client cancels or drops mid-`COPY`, driver and server abort the statement/transaction. Inspect batch status, roll back on error, and decide retries from the batch journal—never assume "80% streamed means 80% committed".

## 71. JDBC CopyManager in pgJDBC

The PostgreSQL JDBC driver (`org.postgresql:postgresql`) exposes streaming `COPY` protocol support without creating millions of row-level `PreparedStatement`s.

Java example:

```java
import org.postgresql.PGConnection;

import javax.sql.DataSource;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;

public final class RawOrderCsvLoader {
    private final DataSource dataSource;

    public RawOrderCsvLoader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long copy(Path csvPath)
            throws SQLException, IOException {
        String copySql = """
            COPY lesson_bulk_load.raw_orders (
                batch_id,
                row_no,
                tenant_raw,
                source_key_raw,
                customer_raw,
                amount_raw,
                ordered_on_raw
            ) FROM STDIN WITH (FORMAT csv, HEADER true)
            """;

        try (Connection conn = dataSource.getConnection();
             InputStream input = Files.newInputStream(csvPath)) {
            conn.setAutoCommit(false);
            try {
                PGConnection pg = conn.unwrap(PGConnection.class);
                long copied = pg.getCopyAPI().copyIn(
                    copySql,
                    input
                );
                conn.commit();
                return copied;
            } catch (SQLException | IOException | RuntimeException ex) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }
}
```

### Key Points

- `FROM STDIN` receives the byte stream from the Java client.
- `CopyManager.copyIn` drives the PostgreSQL COPY protocol.
- `try-with-resources` closes both the pooled connection and input stream.
- Transaction commits only when `COPY` succeeds.
- On any failure, rollback runs on the same connection.

### What Production Still Needs

- Batch registry and duplicate-file checks before `COPY`.
- File checksums, size bounds, and trusted object-storage access.
- Upload/parse progress metrics and cancellation support.
- Idempotent retry policies.
- Network timeouts and dedicated worker pooling.
- Never let clients supply raw `COPY` SQL or server file paths.

## 72. JDBC COPY and Batch Idempotency

In the Java example, `copy` inserts into staging keyed by `(batch_id, row_no)`. If connectivity drops **after `COMMIT`** before the client receives the response, retrying the same CSV hits a duplicate-key error.

### A Stronger Workflow

1. Compute the file's SHA-256 and assign an immutable `batch_id`.
2. Register the batch in `load_batches` with uniqueness constraints.
3. If the same checksum is already `COMPLETED`: return the prior result.
4. If the same `batch_id` arrives with a different checksum: reject or require a new version.
5. If a batch crashed mid-way: inspect committed checkpoints in the registry.
6. Load into clean attempt-scoped staging or resume by row ranges.
7. Reconcile before marking `COMPLETED`.

### Never Rely on a Single Boolean Flag

A single `already_loaded` boolean cannot verify matching checksums or target row completeness. Track explicit states: **received**, **parsed**, **validated**, **applied**, **committed**, and **published**.

## 73. JDBC Batch Insert When Not Using COPY

Not every source is a CSV stream. For typed in-memory objects needing per-row logic, JDBC batching fits well:

```java
String sql = """
    INSERT INTO lesson_bulk_load.orders (
        tenant_id, source_key, customer_ref, amount, ordered_on
    ) VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (tenant_id, source_key)
    DO NOTHING
    """;

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);
    try {
        try (var ps = conn.prepareStatement(sql)) {
            for (OrderRow row : rows) {
                ps.setLong(1, row.tenantId());
                ps.setString(2, row.sourceKey());
                ps.setString(3, row.customerRef());
                ps.setBigDecimal(4, row.amount());
                ps.setObject(5, row.orderedOn());
                ps.addBatch();
            }
            ps.executeBatch();
        }
        conn.commit();
    } catch (SQLException | RuntimeException ex) {
        conn.rollback();
        throw ex;
    }
}
```

This assumes `rows` holds typed `OrderRow` records. `DO NOTHING` fits only when duplicates may be ignored; updating newer versions requires a different conflict clause.

### Sizing Batches

For millions of rows, never buffer all `rows` in JVM memory. Stream in chunks, call `executeBatch` per chunk, and manage memory, commit boundaries, and error reporting cleanly.

### PostgreSQL Driver Optimizations

pgJDBC offers batch `INSERT` optimizations such as `reWriteBatchedInserts` depending on config. Test against your exact SQL shape, `RETURNING`, and conflict clauses rather than assuming every batch rewrites identically.

## 74. Connection Pools for Importers

An importer sharing PostgreSQL with an HTTP API has very different resource patterns:

- Connections held longer during `COPY`.
- Large transactions.
- Bursty I/O and WAL writes.
- Few workers consuming heavy per-worker resources.

### Recommendation

Dedicate a **separate pool/budget** for batch importers with tightly bounded concurrency, and include those connections within total `max_connections`.

### Never Open One Connection per CSV Row

One connection streams an entire `COPY`; opening millions of connections wastes startup overhead and exhausts connection limits.

### Behind PgBouncer

Test `COPY` protocol, temp tables, transactions, and session settings under your exact pooling mode. Under PgBouncer transaction pooling, session-scoped `TEMP TABLE`s cannot span transactions safely.

## 75. Streaming and Java Memory Budgets

For multi-gigabyte files:

```java
byte[] data = Files.readAllBytes(path);
```

is dangerous: it loads the entire file onto the JVM heap, risking `OutOfMemoryError` and severe GC pauses.

### Better

```java
try (InputStream in = Files.newInputStream(path)) {
    // Pass `in` directly to CopyManager.copyIn(...)
}
```

When normalizing CSV before `COPY`, use a streaming parser with bounded buffers instead of loading the file into one giant string.

### Note

Streaming shrinks **client memory footprint**, not server-side WAL, index, or trigger work. When the database server is the bottleneck, enlarging client buffers yields zero speedup.

## 76. CSV Encoding and NULL / Empty Strings

PostgreSQL decodes text according to configured client and server encodings. Ensure UTF-8 files align properly:

```sql
SHOW server_encoding;
SHOW client_encoding;
```

### Distinctions

- SQL `NULL`: absent value.
- Empty string `''`: zero-length text value.
- String `'NULL'`: four characters unless configured as a null token.
- Quoted CSV fields behave differently from unquoted empty fields.

Options like `COPY ... WITH (NULL '...', FORCE_NULL/FORCE_NOT_NULL)` alter mapping rules. Lock down the contract and test with commas, quotes, newlines, Unicode, and NULLs.

### BOM

A UTF-8 BOM can break header/first-field matching in some tools. Strip/normalize BOMs deliberately at the ingestion boundary and add test fixtures rather than silently fixing strings inside the DB.

## 77. Slicing Loads by Partition or Tenant

When target tables are partitioned:

- `COPY` into a partitioned parent routes rows into matching partitions automatically.
- Creating indexes/constraints on partitioned parents vs. child partitions has specific DDL rules.
- `ATTACH PARTITION`/`DETACH PARTITION` carry lock and validation costs.
- You can prepare partitions separately and attach/cutover once schemas and bounds validate.

### Never Blindly Partition per Tenant

Partitioning helps when pruning and lifecycle maintenance align. With tens of thousands of tenants, one partition per tenant bloats catalog metadata severely. Choose partition keys and counts based on query patterns, retention, and volume.

### Constraints and Uniqueness

Unique/primary constraints on partitioned tables must include all partition key columns. Never assume a global unique index across arbitrary columns works identically to unpartitioned tables—design keys to match PostgreSQL partitioning rules.

## 78. Staging Tables and Cutovers

For full-refresh reporting tables:

```text
Existing table (serving reads)
          │
          ├── Build new_table offline
          ├── COPY validated data
          ├── Build indexes / constraints
          ├── ANALYZE and reconcile
          └── Controlled cutover
                  ↓
             New published data
```

### Cutovers Are Never Trivial

Renaming tables via DDL, swapping views, attaching partitions, or flipping pointers interacts with:

- Locks.
- Foreign key dependencies.
- Cached prepared query plans.
- Grants and RLS policies.
- Replication and CDC streams.
- Sequences and triggers.

Never assume `ALTER TABLE ... RENAME` is a universal "zero-downtime atomic swap" across arbitrary schemas—plan around dependencies and active readers/writers.

## 79. Reconciling Batch Row Counts

After loading, reconcile:

```text
raw rows
= accepted rows + rejected rows
```

per your **classification contract**.

In the lab:

```sql
SELECT count(*) AS raw_rows
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-2026-11';

SELECT count(*) AS rejected_rows
FROM lesson_bulk_load.load_rejects
WHERE batch_id = 'B-2026-11';
```

To verify accepted rows/keys, inspect persisted validated data or a durable batch report (since `tmp_orders_checked` drops on `COMMIT`).

### Never Equate Target Row Growth with Accepted Rows

With `UPSERT`:

- An accepted row may `INSERT`.
- An accepted row may `UPDATE`.
- An accepted row may be a no-op.

Therefore `raw = accepted + rejected` partitions the **input**, while target row count growth measures only net-new inserts.

## 80. Checking Source Duplicates

```sql
SELECT
    batch_id,
    tenant_raw,
    source_key_raw,
    count(*) AS duplicates
FROM lesson_bulk_load.raw_orders
WHERE batch_id = 'B-2026-11'
GROUP BY
    batch_id, tenant_raw, source_key_raw
HAVING count(*) > 1
ORDER BY duplicates DESC;
```

This catches raw text duplicates. If `'10'` and `' 10 '` both normalize to bigint `10`, raw grouping treats them as distinct. Always check duplicates on **normalized/cast business keys** before enforcing uniqueness.

### Watch Multi-Version Sources

Two rows sharing a source key with different versions are not necessarily errors—they can represent sequential updates to one entity. Define winner selection using a trusted sequence or version field.

## 81. Reconciling Monetary Sums and Aggregates

Post-merge verification:

```sql
SELECT
    tenant_id,
    count(*) AS orders,
    sum(amount) AS total_amount
FROM lesson_bulk_load.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

With the initial sample data:

```text
tenant 10: 2 orders, 425500.00
tenant 20: 1 order,   92000.00
```

### In Production

Compare these totals against an **independent** aggregate computed from the source under identical duplicate, currency, cutoff, and version rules. Computing both sides with the exact same buggy SQL hides business errors.

Check not only totals, but also row counts, distinct keys, and edge-case samples.

## 82. Checksums and Source Provenance

Recording a SHA-256 checksum of **file bytes** in the batch registry detects duplicate submissions or altered payloads.

### Which Checksum?

- File checksum: catches any byte change, including encoding or line endings.
- Canonical normalized-row checksum: verifies content post-normalization, requiring deterministic ordering, null handling, collation, and casts.
- Per-chunk checksum: enables partial retries and reconciliation.

### Limitations

Matching checksums confirm byte/representation integrity—they do not prove source authorization, semantic validity, or complete application to target tables.

Never treat a hash stored inside the same compromised database as tamper-proof forensic evidence.

## 83. Why Never Validate Using Only count(*)?

Suppose the source holds keys:

```text
SO-001, SO-002, SO-003
```

while the target holds:

```text
SO-001, SO-002, SO-004
```

Both report `count = 3`, yet one key is missing and another is unexpected.

### Better Verification

- Total input, accepted, rejected, and applied counts.
- Distinct business key counts.
- Anti-joins checking for missing or unexpected keys.
- Field-level comparisons or canonicalized aggregate hashes.
- Sum/Min/Max grouped by tenant, currency, and date.
- Transaction and batch version consistency.

For huge tables, verify per partition or chunk to avoid full scans impacting production.

## 84. Finding Target Rows Missing from Valid Staging

While `tmp_orders_checked` still lives inside the transaction:

```sql
SELECT
    t.tenant_id,
    t.source_key
FROM tmp_orders_checked AS t
LEFT JOIN lesson_bulk_load.orders AS o
  ON o.tenant_id = t.tenant_id
 AND o.source_key = t.source_key
WHERE t.reject_reason IS NULL
  AND o.order_id IS NULL;
```

Expect **0 rows** after a successful merge before `COMMIT` when no concurrent writer modifies those keys in the snapshot.

### After COMMIT

`tmp_orders_checked` disappears. For post-commit reconciliation, persist canonical accepted keys or a durable batch manifest rather than relying on a dropped temp table.

## 85. Validating Constraints on the Target Table

Checking for negative amounts (should be impossible while `CHECK` is enforced):

```sql
SELECT order_id, tenant_id, source_key, amount
FROM lesson_bulk_load.orders
WHERE amount < 0;
```

Checking for orphan customers:

```sql
SELECT o.order_id, o.tenant_id, o.customer_ref
FROM lesson_bulk_load.orders AS o
LEFT JOIN lesson_bulk_load.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_ref = o.customer_ref
WHERE c.customer_ref IS NULL;
```

Checking for duplicate keys:

```sql
SELECT tenant_id, source_key, count(*)
FROM lesson_bulk_load.orders
GROUP BY tenant_id, source_key
HAVING count(*) > 1;
```

### Key Point

These queries are supplementary checks. Real data protection comes primarily from **enabled and validated constraints**, not one-off post-load audits.

## 86. Verifying Triggers and Audit Logs Post-Import

```sql
SELECT
    action,
    count(*) AS events
FROM lesson_bulk_load.order_audit
GROUP BY action
ORDER BY action;

SELECT
    event_id,
    action,
    order_id,
    old_row ->> 'amount' AS old_amount,
    new_row ->> 'amount' AS new_amount
FROM lesson_bulk_load.order_audit
ORDER BY event_id DESC
LIMIT 20;
```

### Important Note

Never expect audit `INSERT` counts to equal raw row counts when staging filters rejects, deduplicates rows, or `UPSERT` updates existing targets.

If auditing is compliance-critical, ensure migrations and bulk jobs never disable triggers and monitor `pg_trigger.tgenabled`; fewer audit events than raw rows alone does not indicate a bug.

## 87. Error Rates and Batch Acceptance Policies

Suppose a batch has 1,000,000 rows and 3,000 rejects:

\[
\text{reject rate}
= \frac{3000}{1000000}\times 100\%
= 0.3\%
\]

### Three Common Policies

**Strict:** commit/publish only when `reject rate = 0`.

**Threshold:** tolerate a small error rate while recording rejects and reporting accurately.

**Partial acceptance:** apply valid rows and hold rejects for later repair.

### Match Business Context

Accounting ledgers demand strict validation; marketing enrichment feeds may allow partial acceptance. Never apply a blanket 1% threshold to every domain.

### Reporting Metrics Precisely

Distinguish:

- `total_raw`.
- `valid_rows`.
- `invalid_rows`.
- `inserted_rows`.
- `updated_rows`.
- `unchanged_rows`.
- `published_rows`.

Especially with `UPSERT`, `valid_rows` differs from `inserted_rows`.

## 88. Pre-COMPLETED Reconciliation

Consider a batch complete only when:

1. Raw source is stored and checksum verified.
2. All expected chunks/records were processed.
3. Rejected rows carry reason codes and provenance.
4. Target constraints passed without error.
5. Accepted keys reached their intended final state.
6. Internal side effects (audit/outbox) committed synchronously.
7. Downstream snapshot/watermarks are recorded if needed.
8. Replica and metric SLAs meet contract requirements.
9. Batch status updates atomically with the final checkpoint or safe protocol.

### Never Mark COMPLETED Before Merging

If `load_batches.status = 'COMPLETED'` commits before the target merge transaction commits, downstream readers observe a false completed state.

In multi-transaction pipelines, use explicit intermediate states and final reconciliation.

## 89. When Must Other Writers Be Isolated or Locked?

Full-refresh bulk loads can collide with online writers:

- Batch builds a snapshot state.
- API concurrently updates an order.
- Loader replaces/upserts the table and overwrites the newer API update.

### Design Patterns

- Version-aware merges or optimistic locking.
- Cutover into a new table coordinated with writers.
- Appropriate transaction isolation and locks.
- CDC tailing to replay concurrent changes during load.
- Quiescing writes during maintenance windows where allowed.

Never simply set `SERIALIZABLE` on a massive transaction assuming races vanish without handling retries, contention, and design limits.

## 90. Lock Risks When Changing Indexes or Constraints

Operations such as:

- `ALTER TABLE ADD CONSTRAINT`.
- `VALIDATE CONSTRAINT`.
- `CREATE INDEX`.
- `CREATE INDEX CONCURRENTLY`.
- `ALTER TABLE ATTACH PARTITION`.
- `TRUNCATE`.

take differing lock modes and durations. Fast loads can stall behind DDL locks or cause prolonged migration lock queues.

### Best Practices

- Test lock behavior in staging under representative load.
- Set `lock_timeout` on migrations where appropriate.
- Monitor `pg_locks` and `pg_stat_activity` when blocked.
- Keep schema-altering DDL out of giant data-load transactions.
- Define rollback and cancellation criteria.

`CREATE INDEX CONCURRENTLY` avoids blocking writes yet waits on long-running transactions—never interpret "concurrently" as "zero operational impact".

## 91. Quick Decision Table

| Requirement | Preferred Strategy |
|---|---|
| Clean file, fresh table | Direct `COPY`, build secondary indexes afterward |
| File with many faulty rows | Raw staging + validation + reject log |
| Live online target | Keep constraints/unique arbiters, microbatch `UPSERT` |
| Idempotent retries needed | `batch_id` + checksum + unique source key |
| Heavy triggers on target | Benchmark overhead; consider statement/transition audit |
| FK to parent table | Load parent first, validate references, keep FK |
| Adding FK to large existing table | `NOT VALID` + `VALIDATE CONSTRAINT` where appropriate |
| Indexing a live online table | `CREATE INDEX CONCURRENTLY` with runbook |
| Indexing an offline table | Standard `CREATE INDEX` usually fits |
| Large replayable source | Consider `UNLOGGED` staging |
| Staging shared across connections | Persistent staging; avoid relying solely on `TEMP` |
| Multi-tenant + RLS | Validate tenant, enforce rights at merge, test RLS/`COPY` |
| Load causing replica lag | Throttle throughput, monitor WAL and replay |
| Atomic full refresh needed | Shadow table/cutover or suitable transaction model |
| Incremental online feed | Idempotent chunks + progress journal |

## 92. Runbook: COPY Fails Due to Data

1. Record `batch_id`, source checksum, file location, and failing line if reported.
2. Inspect SQLSTATE: parse (`22P02`), range, FK (`23503`), unique (`23505`), check (`23514`), not-null (`23502`).
3. Separate CSV syntax errors, type conversion errors, and business constraint errors.
4. If the transaction aborted, roll back—never issue further SQL inside an aborted transaction.
5. Never alter source files without updating checksums and versions.
6. Load into raw staging if line-by-line error reporting is needed.
7. Apply reviewed, verified correction rules.
8. Retry via idempotent batches/chunks.
9. Reconcile keys, counts, and sums afterward.
10. Track whether rejects were waived or fixed without erasing error history.

### When Direct COPY Wrote Partial Heap Pages Before Failing

Reclaim space via `VACUUM` or autovacuum after rollback. Never reflexively run `VACUUM FULL` on large production tables—it takes exclusive locks causing downtime.

## 93. Runbook: Slow Import Due to Indexes or FKs

1. Measure **committed** rows/s, not just CSV read throughput.
2. Compare `COPY` into constraint-free staging vs. target merge cost.
3. Review target index count, types, and sizes.
4. Check `pg_stat_activity.wait_event` and lock waits.
5. Confirm referenced parent keys are indexed.
6. Measure trigger function and audit overhead.
7. Check WAL, disk, buffer pressure, and replica lag.
8. Test smaller or tuned batch sizes and concurrency.
9. On fresh offline tables, benchmark post-load index creation.
10. On live online targets, **never drop constraints** just to chase benchmark numbers.

### Helpful Diagnostic Benchmark

Run the same dataset across:

- Raw staging.
- Target with constraints/indexes but without audit (strictly on a **lab clone**).
- Target with full production constraints, indexes, and audit.

Comparing timings isolates where overhead lives under realistic concurrency.

## 94. Runbook: Unexpected Target Row Counts After Load

1. Compare total raw, valid, rejected, and duplicate counts.
2. Check how many `UPSERT`s inserted, updated, or no-opped.
3. Inspect business-key normalization and tenant scoping.
4. Check for source keys spanning multiple chunks.
5. Verify batch versioning and correction policies.
6. Run an anti-join from accepted staging to target.
7. Compare aggregates by tenant, date, and currency.
8. Inspect transaction logs, statuses, and crash retries.
9. Check if concurrent writers deleted or updated rows post-merge.
10. Mark `COMPLETED` only when all reconciliation checks pass.

### Never Try to "Fix" Counts by Blindly Re-Running

If sources contain duplicates or merges lack idempotency, re-running makes things worse. Verify invariants and conflict policies before retrying.

## 95. Runbook: Missing Audit Rows After Bulk Import

1. Verify the audit trigger existed before the load.
2. Inspect `pg_trigger.tgenabled`, migration logs, and audit policies.
3. Confirm the `COPY`/`INSERT` path actually modified the target table.
4. Account for rejects, no-op `UPSERT`s, and actual row modifications.
5. Check whether the trigger function skips certain events by design.
6. Check for `TRUNCATE`, replication apply modes, or disabled triggers.
7. Reconcile audit entries against **committed target effects**, not raw row counts.
8. If a real gap exists, document provenance and remediate transparently via an approved baseline/correction mechanism.

### Never Forge Historical Timestamps

If data loaded before triggers were enabled, never backfill `INSERT` audit events stamped with today's clock claiming they happened at load time. Emit an explicit `BASELINE` record with accurate metadata if compliance permits.

## 96. End-to-End Blueprint for a 100-Million-Row File

Reference architecture:

```text
Immutable upload to object storage
     └─ SHA-256 + batch registry
             └─ Partition files / chunks
                     └─ COPY to staging (bounded workers)
                             ├─ normalize + classify
                             ├─ persist rejects
                             └─ accepted canonical keys
                                     └─ merge into target
                                           ├─ PK/UNIQUE
                                           ├─ CHECK/NOT NULL
                                           ├─ FK
                                           └─ audit/outbox triggers
                                                   └─ COMMIT chunk
     └─ reconcile all chunks + source/version checks
             └─ ANALYZE / monitor replica lag
                     └─ mark batch COMPLETED / publish watermark
```

### Why Not Put 100 Million Rows in One Transaction?

A single massive transaction drives extreme rollback cost, lock/snapshot retention, and disk/WAL pressure. Conversely, chunking sacrifices **whole-batch atomicity**. Decide explicitly between incremental online visibility vs. shadow-table publish/cutover after full validation.

### Failure Drills to Test Before Production

- Failure mid-file.
- Connection drop after `COMMIT` losing ACK.
- Duplicate business keys across two chunks.
- High worker concurrency and deadlocks.
- Heavy replica lag.
- Disk full / WAL pressure.
- Database restart, loader restart, and resume.
- Schema/constraint migration mid-batch.
- Importer role privilege revocation.
- Audit/outbox trigger failure.

## 97. Summary of Bulk-Loading Trade-Offs

| Decision | Benefit | Trade-off |
|---|---|---|
| `COPY` instead of single `INSERT`s | Streaming speed, fewer round trips | Must handle COPY protocol and mid-batch failures |
| Staging before target | Classifies rejects, deduplicates, replays cleanly | Extra I/O, storage, and orchestration |
| Keep target constraints | Engine protects invariants across all writers | Lookup, check, and index overhead |
| Load fresh table then index | Cuts per-row index maintenance | Needs offline window and validation/cutover |
| `CREATE INDEX CONCURRENTLY` | Avoids blocking live writes | Longer runtime/I/O; invalid index if failed |
| FK `NOT VALID` then `VALIDATE` | Separates constraint creation from legacy scan | Validation still costs I/O/locks; new rows checked immediately |
| Row audit trigger | Transactional per-row snapshots | CPU, JSONB, WAL, and audit storage cost |
| Statement transition table | Set-based per-statement handling | Trigger/DDL limits and key-matching constraints |
| One giant transaction | Whole-batch atomicity | Rollback cost, locks, large failure blast radius |
| Chunked commits | Resumable, bounded transactions | Partial visibility; needs progress/reconciliation |
| `UNLOGGED` staging | Cuts WAL for temporary data | Not crash-safe, not replicated |
| Parallel workers | Higher potential throughput | Lock contention, WAL/IO/replica lag, deadlocks |
| `COPY FREEZE` when eligible | Reduces future freeze work | Strict preconditions and MVCC caveats |
| Post-load `ANALYZE` | Fresh planner statistics | Scan cost; needs proper timing |

This table highlights that **every optimization carries conditions and costs**—there is no universal configuration.

## 98. Pre-Production Import Checklist

### Sources and Data

- Are files immutable or versioned with checksums?
- Are encoding, CSV dialect, and NULL semantics verified?
- Are batch, row, and business entity identifiers unique?
- Are rules defined for duplicates, late arrivals, and corrections?
- Is the business-acceptable rejection rate defined?

### Schema and Privileges

- Do target `NOT NULL`/`CHECK`/`UNIQUE`/`FK` constraints protect all invariants?
- Do RLS, triggers, or column defaults affect `COPY`/`UPSERT`?
- Does the importer role follow least privilege?
- Which indexes must exist before loading to preserve correctness?
- If migrations add indexes/constraints, has lock impact been evaluated?

### Resources and Operations

- Is there sufficient disk/WAL headroom on primary and replicas?
- Does importer concurrency fit DB and pool budgets?
- Are transaction/chunk sizes and timeouts defined?
- Are `COPY`/index build progress, lock waits, autovacuum, and replica lag monitored?
- Is there a stop/resume plan for network or DB restarts?

### Verification and Publishing

- Are accepted/rejected rows classified with per-row reasons?
- Are counts, keys, sums, and checksums reconciled?
- Is trigger/audit coverage verified?
- Are error thresholds and rollback criteria defined?
- When exactly does batch status transition to `COMPLETED`?
- Do downstream consumers read partial data or only published batches?

This checklist governs **data pipeline operations**, not documentation QA.

## 99. Practice Exercises

### Exercise 1 — Choosing a Load Method

A verified 5-million-row CSV targets a fresh table with no active users yet. Compare JDBC batch `INSERT` with direct `COPY`. Which criteria govern the choice?

### Exercise 2 — COPY vs. psql \copy

Write examples of `COPY ... FROM '/server/file.csv'` and `\copy ... FROM '/client/file.csv'`. Which machine owns each path, and why shouldn't app roles hold server-file access?

### Exercise 3 — Creating the customers/orders Schema

Create `customers(tenant_id, customer_ref)` and `orders` with `NOT NULL`, `CHECK amount >= 0`, `UNIQUE (tenant_id, source_key)`, and the composite two-column FK.

### Exercise 4 — Cross-Tenant FK

Customer `CUS-01` exists in tenant 20 but not tenant 10. Why shouldn't a tenant 10 order referencing `CUS-01` be accepted just because `customer_ref` exists in another tenant?

### Exercise 5 — Raw Staging

Create `raw_orders` with `TEXT` fields and `(batch_id, row_no)`. Explain why raw staging accepts rows that typed target tables reject.

### Exercise 6 — Preparing CSV

Create a CSV matching the lab headers. Include a quoted comma field, a Unicode name, a thousands-comma amount, and a blank field. Identify the distinct formatting vs. business errors.

### Exercise 7 — pg_input_is_valid

On PostgreSQL 16+, use `pg_input_is_valid` to distinguish valid `bigint`, `bigint` overflow, invalid dates, and unparseable numerics. Why aren't simple regexes sufficient?

### Exercise 8 — CASE Before Cast

Write `CASE WHEN pg_input_is_valid(...) THEN text::numeric END`. Show how `not-a-number` turns into classified `NULL` instead of aborting a direct-cast `SELECT`.

### Exercise 9 — Data Quality Rules

Classify `INVALID_TENANT`, `MISSING_SOURCE_KEY`, `NEGATIVE_AMOUNT`, and `INVALID_DATE`. Choose precedence when one row has multiple errors.

### Exercise 10 — Reject Log

Create `load_rejects(batch_id, row_no, reason, raw_payload)`, insert staging errors, and use `ON CONFLICT` so retries never create duplicate reject keys.

### Exercise 11 — In-File Duplicates

Insert two rows sharing `(tenant_id, source_key)` with different `row_no`. Use `row_number() OVER (PARTITION BY ... ORDER BY row_no)` to keep one and reject the other.

### Exercise 12 — Cross-Chunk Duplicates

A key appears in chunks 2 and 8. Why is per-chunk deduplication insufficient? Propose a batch-wide canonical key set or source-version policy.

### Exercise 13 — Valid UPSERT

Write `INSERT ... SELECT` from validated temp rows with `ON CONFLICT(tenant_id, source_key) DO UPDATE`. Explain the role of the unique arbiter.

### Exercise 14 — No-Op UPSERT

Add `WHERE (target.field1, target.field2) IS DISTINCT FROM (...)`. Re-run the same batch and compare audit events vs. target updates.

### Exercise 15 — One UPSERT Touching the Same Row Twice

Skip deduplication and attempt to `UPSERT` two rows with the same target key in one statement. Explain the cardinality error and how to prevent it.

### Exercise 16 — CHECK Constraints and NULL

Why isn't `CHECK (amount >= 0)` enough to block SQL `NULL`? Define the column with both `NOT NULL` and `CHECK`.

### Exercise 17 — FK Validation

Attempt loading an order referencing a nonexistent customer. Compare the raw target FK error against the structured staging pre-validation reject reason.

### Exercise 18 — FOREIGN KEY NOT VALID

On a separate populated lab table, add an FK `NOT VALID` and then run `VALIDATE CONSTRAINT`. Before validation runs, does a newly `INSERT`ed row get checked by the FK?

### Exercise 19 — CHECK NOT VALID

Add `CHECK (amount <= 1000000000) NOT VALID` to a table with existing rows. Verify new writes are checked immediately, then validate existing data.

### Exercise 20 — UNIQUE Does Not Use NOT VALID

Contrast adding `UNIQUE` vs. `CHECK`/`FK`. Plan building a unique index concurrently and attaching the constraint where eligible instead of trying `UNIQUE ... NOT VALID`.

### Exercise 21 — Index Costs

A table has a PK, a unique source key, and six secondary B-tree indexes. Explain index maintenance costs across 10 million `INSERT`s and when indexes can be built post-load.

### Exercise 22 — CREATE INDEX CONCURRENTLY

On a lab table, run `CREATE INDEX CONCURRENTLY` at top level. Why can't it run inside `BEGIN ... COMMIT`? What must you do if the build fails leaving an invalid index?

### Exercise 23 — Audit Row Trigger

Create an `AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW` trigger logging `OLD`/`NEW` snapshots. Load three valid rows and count events.

### Exercise 24 — Trigger Overhead

Suppose 1 million target inserts create 1 million JSONB audit rows. What resources grow besides `orders` table size alone?

### Exercise 25 — Statement Trigger with Transition Table

Create a demo table and `AFTER INSERT ... REFERENCING NEW TABLE` trigger writing history via `INSERT ... SELECT`. Compare function invocation counts against row triggers on a 10,000-row insert.

### Exercise 26 — Never Use DISABLE TRIGGER ALL Recklessly

Why is `ALTER TABLE ... DISABLE TRIGGER ALL` dangerous for FKs and auditing? Propose staging, `NOT VALID`, and index scheduling instead of dropping constraints.

### Exercise 27 — One Transaction vs. Many Chunks?

Compare loading 50 million rows in one transaction vs. 100 self-committing chunks. Discuss all-or-nothing atomicity, rollback cost, resumption, and partial visibility.

### Exercise 28 — Batch Registry

Design `load_batches` with checksum, status, and total/rejected/applied counts. Distinguish file arrival from merge completion.

### Exercise 29 — Retrying After Lost COMMIT ACK

Connectivity drops right after the loader sends `COMMIT`. Why can't you assume it did not commit? Design a batch ID/checksum lookup and idempotent retry.

### Exercise 30 — UNLOGGED Staging

Create an `UNLOGGED` table in the lab. Explain potential throughput gains, crash data-loss risks, and why raw sources must stay replayable.

### Exercise 31 — TEMP Staging and PgBouncer

A job creates a `TEMP` table in transaction 1, commits, and reads it in transaction 2 through PgBouncer transaction pooling. Why isn't backend session affinity guaranteed?

### Exercise 32 — WAL and Replication Lag

An import spikes WAL and lags a replica by 2 minutes. List metrics to monitor and distinguish "committed on primary" from "visible on read replica".

### Exercise 33 — ANALYZE and VACUUM

After loading millions of rows, the planner picks an unexpected `Seq Scan`. Write the `ANALYZE` command, explain how it differs from `VACUUM`, and note why `VACUUM` runs outside transactions.

### Exercise 34 — pg_stat_progress_copy

While `COPY` runs, query `pg_stat_progress_copy`. Which columns reflect progress, and why isn't `tuples_processed` a count of committed rows?

### Exercise 35 — Parallel Workers and SKIP LOCKED

Design `load_chunks` and an `UPDATE ... FROM (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING` claim query. Add lease timeouts and retry logic.

### Exercise 36 — JDBC CopyManager

Write a Java method streaming CSV via `PGConnection.getCopyAPI().copyIn` using `try-with-resources`, committing on success and rolling back on failure. Why avoid `Files.readAllBytes` on multi-GB files?

### Exercise 37 — COPY and Security

Explain why an importer role should never receive server-side `COPY PROGRAM`, trigger-disabling rights, or superuser. Design least-privilege grants.

### Exercise 38 — RLS and Tenant Scope

A target table enables RLS across multiple tenants. Design tenant-safe staging + merge, explaining why a user-supplied `current_setting` tenant is not proof of authorization.

### Exercise 39 — Reconciliation

A batch has 1 million raw rows, 10,000 rejects, 5,000 accepted duplicate/no-ops, and 985,000 accepted inserts/updates. Identify required counters and why checking target `count(*)` alone is insufficient.

### Exercise 40 — Complete Large-Scale Pipeline Design

A company must load 100 million orders from multiple CSVs:

- Data contains type errors, missing customers, duplicate source keys, and late corrections.
- PostgreSQL serves a 24/7 application.
- Target enforces FK, `UNIQUE`, `CHECK`, and a row audit trigger.
- Read replicas serve reporting continuously.
- Audit history must never be bypassed for load speed.
- Imports run via Java/Spring and PgBouncer.
- Connections can drop after `COMMIT`, workers can restart, or chunks can fail.

Design the solution covering:

1. Protecting inputs with batch IDs, checksums, and least-privilege storage.
2. Choosing logged/`UNLOGGED` staging vs. direct `COPY` with justification.
3. Classifying type/business errors and storing replayable rejects.
4. Deduplicating in-batch and handling source versions.
5. Designing idempotent `INSERT ... ON CONFLICT` avoiding no-op updates.
6. Preserving FK/`UNIQUE`/`CHECK`/audit contracts and index strategies.
7. Using chunk queues, bounded parallel workers, timeouts, and transaction sizes.
8. Handling PostgreSQL/Java errors, lost `COMMIT` ACKs, and whole-transaction retries.
9. Monitoring `COPY`, index builds, WAL, locks, autovacuum, replica lag, and committed good rows/s.
10. Reconciling counts/keys/sums/checksums, publishing data, and marking `COMPLETED`.

## 100. Conclusion

**Bulk loading into PostgreSQL is not simply about running `COPY` as fast as possible.** The goal is landing the right data in the right tables while honoring primary keys, unique constraints, foreign keys, `CHECK` constraints, and triggers—and retaining the ability to stop, repair, replay, and prove results.

**`COPY`** excels on clean feeds or when streaming into staging. **Staging** adds a pass yet preserves raw rows, classifies errors by batch and line, normalizes types, deduplicates keys, and merges only valid records. **Unique constraints and `ON CONFLICT`** enforce business-key idempotency; **`FOREIGN KEY`, `CHECK`, and `NOT NULL`** guard final correctness even when staging faces races or bugs.

**Indexes and triggers carry real costs.** On fresh offline tables, loading before building secondary indexes and constraints can help; on live tables, keep unique/FK/audit safeguards and rely on online index builds, batch sizing, and throttling. **`NOT VALID`/`VALIDATE`** helps when adding supported constraints to huge existing tables without exempting new writes. Disabling internal triggers or weakening durability carelessly merely trades short-term speed for data-loss risk.

Finally, align **transaction boundaries, chunk progress, WAL/replica monitoring, vacuum/analyze, JDBC streaming, and idempotent replay** with your system's recovery requirements. A batch is truly done only when raw/accepted/rejected/applied counts, business keys, constraints, audit trails, and downstream state reconcile against the contract. **Loading speed only matters when the loaded data is accurate, verifiable, and recoverable.**
