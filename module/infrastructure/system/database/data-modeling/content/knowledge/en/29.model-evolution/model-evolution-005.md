# Historical Data Backfill with Resumability and Reconciliation

When evolving a data model, adding new tables or columns is usually only the first step. The system already holds millions of records created under the old structure: to use the new model, we need to **backfill historical data**. If you run one giant update statement and lose the connection midway, how do you know which portion completed, where to resume from, and which rows were missed? If source data changes while the job is running, how do you guarantee the new table reflects the true state? If row counts match but values were mapped incorrectly, how do you detect it?

**Resumable and reconcilable backfill** is a data migration or population workflow in which:

1. **Inputs and transformation rules are explicitly identified**: source, scope, grain, logic version, and cutoff point.
2. **Work is split into controllable batches (chunks)**: no single transaction spanning the entire history is needed.
3. **Checkpoints reflect what has been committed**, not merely what has been read or dispatched for processing.
4. **Re-runs do not introduce drift or corruption**: idempotency mechanisms, unique keys, and conflict handling are designed upfront.
5. **Source-to-target reconciliation is enforced** by both keys and values, not just total row counts.
6. **Read/write traffic is cut over only after acceptance criteria are met**, with plans for stopping, recovery, and rollback.

This lesson belongs to the **Model Evolution** chapter of the **DATABASE_DATA_MODELING** module. It connects the business domain model with keys, constraints, relational modeling, physical schemas, history, and transactions; implements a **PostgreSQL** example traceable batch-by-batch; and then extends to CDC, late-arriving data, and live active systems.

## 1. What is backfill, and how does it differ from similar operations?

**Backfill** is the process of populating historical data for a past range into **new columns, tables, indexes, or derived models**, based on existing sources. The goal may be filling missing data, schema migration, re-normalizing values, building fact/snapshot tables, or rebuilding a read model.

| Operation | Goal | Example |
| --- | --- | --- |
| **Backfill** | Populate historical data into a new structure or missing data range | Add **order_local_date** for past orders |
| **Data migration** | Move data and read/write contracts to another model | Split the orders table into orders and order_addresses |
| **Replay** | Reprocess recorded events/inputs according to deterministic rules | Replay sales events to build facts |
| **Reconciliation** | Compare two datasets against a shared definition | Find missing orders, wrong dates, or wrong totals |
| **Repair/correction** | Fix data written erroneously or drifted from the source of truth | Fix wrong unit price at order placement time |
| **Catch-up** | Catch up with new changes that arrived during backfill | Apply CDC from the snapshot position up to the present |
| **Cutover** | Switch readers/writers to the new data and processing path | Route dashboard reads to **order_facts_v2** |

These operations often occur in the same project, yet they are **not synonymous**. Finishing a historical snapshot backfill does not mean changes occurring during processing have been ingested. Completing a reconciliation count check does not mean the application can immediately switch all traffic.

### 1.1. Common backfill examples

- Adding a **normalized_phone** column for lookup by normalized phone number.
- Converting prices from **DECIMAL** to **Money + currency** with explicit rounding rules.
- Generating a durable **customer_id** instead of relying on a mutable email address.
- Populating **dimension surrogate keys** for historical facts, handling SCD Type 2 history.
- Separating the current address from the **transaction-time snapshot address**.
- Building **daily_sales_v2** from sales lines recorded before the analytics warehouse existed.
- Populating **tenant_id** or a new partition key on legacy tables prior to sharding.

Each example has a **different grain, source of truth, and risk level**. You should not take an UPDATE script that works for a simple column and assume it suffices for identity changes or multi-table relational decomposition.

### 1.2. Invariants to preserve

Backfill requirements should be written as testable conditions:

~~~text
For each eligible source record in snapshot S:
  -> there exists exactly one corresponding target record,
  -> with the correct key,
  -> with fields transformed accurately according to transform_version V.

For each target record belonging to the backfill:
  -> its source/version and generating rule can be traced.

A batch is considered complete only if:
  -> the target records of the batch have been committed,
  -> the corresponding checkpoint is committed in the same transaction.
~~~

When business filtering applies (for example, **CANCELLED** does not belong in the placed-orders fact), the target row count not equaling the total source row count is **correct by design**. You must reconcile against the **eligible source set**, not compare against every row in the old table.

## 2. Decisions that must be locked down before starting

### 2.1. Grain, keys, and uniqueness scope

Answer these in order:

- **What is one source row?** An order, an order line, an edit revision, a source event?
- **What is one target row?** The same order, a tenant–day aggregate, or a new relation?
- **Which key is stable over time?** Can IDs be reassigned or changed?
- **What is the scope of uniqueness?** Global, per-tenant, per-period, per-source-service, or per-snapshot-version?
- **How many target rows does one source map to?** One-to-one, one-to-many, many-to-one?
- **How are deleted/cancelled states and invalid data handled?**

For a **one-to-one** transformation, **source_record_id** can serve as the natural identifier of the target record. For a **many-to-one** transformation, you need a group key and a mechanism to track contributing sources. For a **one-to-many** transformation, you must have a deterministic derived-element key so retries do not produce duplicates.

### 2.2. Can the source data change?

There are two broad cases:

**Frozen/immutable source:** for example, a completed export or frozen manifest where no rows are inserted or modified. You can scan along a stable key, advance checkpoints incrementally, and re-run against the same snapshot.

**Live/mutable source:** during the scan, records can be inserted, updated, or deleted. Using **MAX(id)** as a boundary on an actively written table **does not create a snapshot**. A transaction might allocate an ID and commit later, causing a row with an ID smaller than the checkpoint to appear after that key range was scanned. Moreover, an UPDATE to an already-scanned row can make the target table stale.

For live sources, you need a **consistent snapshot + change capture/CDC**, or a synchronization pipeline with queues, versioning, and equivalent reconciliation. The walkthrough example in this lesson first uses an **immutable snapshot** to focus on checkpointing; Section 11 then discusses how to apply this to a system still receiving new writes.

### 2.3. Time semantics and transformation versioning

A project must explicitly specify:

| Component | Example |
| --- | --- |
| **Snapshot ID** | 501 |
| **Transform version** | order-fact-v2.1 |
| **Target grain** | One PLACED order in the snapshot |
| **Reporting date** | Local date in **Asia/Ho_Chi_Minh** derived from placed_at |
| **Source boundary** | Frozen export, unchanged during ingestion |
| **Filter policy** | PLACED status only; do not ingest CANCELLED |
| **Duplicate write policy** | Do not create an extra row if the exact source ID already exists |
| **Source correction policy** | Emit a version/correction or re-run with reconciliation |
| **Acceptance criteria** | Matching key sets, matching values, matching group totals |

**Transform version** is not just an arbitrary string: you need to know the calculation formula, timezone, NULL/rounding policies, code version, and reference data if applicable. Running twice under the same version name but with different logic can produce different results without explanation.

## 3. Safe rollout via Expand → Backfill → Cutover → Contract

A common approach for evolving a live system:

~~~mermaid
flowchart LR
    OLD["Existing system"]
    EXPAND["Expand: new schema, nullable/new target"]
    SNAP["Freeze source / snapshot + checkpoint"]
    FILL["Batched backfill + resume"]
    CATCH["Catch-up new changes"]
    VERIFY["Reconcile + shadow read"]
    CUT["Cutover: switch read source"]
    CONTRACT["Contract: drop old path when safe"]
    OLD --> EXPAND --> SNAP --> FILL --> CATCH --> VERIFY --> CUT --> CONTRACT
    FILL -- "recoverable error" --> FILL
    VERIFY -- "mismatch: fix + rerun" --> FILL
~~~

Key steps to note:

1. **Expand:** add the new schema in a way that lets the old application keep running. For new columns, typically add them as nullable or with a safe default first; avoid setting NOT NULL before history is populated.
2. **Input source:** establish the snapshot/cutoff and the mechanism to track ongoing changes, rather than reading point-in-time drifting data across batches.
3. **Backfill:** scan by a stable key, perform repeatable target writes, and checkpoint atomically.
4. **Catch-up:** apply new inserts/updates/deletes that occurred during the backfill phase according to ordering/version rules.
5. **Reconciliation:** compare key sets, values, aggregates, and new application query results.
6. **Cutover:** switch via a monitored feature flag/route/pointer; do not delete the old path immediately.
7. **Contract:** drop old columns, tables, or write paths only once you are certain no consumers remain and the rollback window has closed.

**Not every project needs dual-write.** A simple schema migration on a small table can be executed directly inside a maintenance window. However, with large datasets, multiple services, or continuous SLAs, a phased plan is usually far easier to control than one giant transaction.

## 4. Why must checkpointing and idempotency go together?

Suppose a batch processes order IDs 101, 103, 105:

~~~text
Wrote rows 101, 103 to the target.
Application crashes before writing row 105.
Checkpoint already recorded "last_id = 105".
After restart, the job only reads id > 105.
=> Row 105 may be permanently skipped.
~~~

The mistake here is **marking completion before the target writes are guaranteed committed**.

The reverse case:

~~~text
Committed rows 101, 103, 105.
Application crashes before recording the checkpoint.
Restart re-reads id > 100.
=> Rows 101, 103, 105 are processed again.
~~~

If the target lacks a unique key or the operation is merely **balance = balance + amount**, a retry can double the result.

A reliable approach when the snapshot source and target reside in the same PostgreSQL database:

> **Write the batch rows and update the checkpoint within the same transaction**, combined with unique keys and repeatable write logic.

If source/target/checkpoint live in **separate systems that do not share a transaction**, you must combine idempotency, post-confirmation checkpointing, an outbox/commit protocol, or specialized mechanisms; you cannot assume one SQL transaction spans every system.

## 5. Hands-on scenario: building a new fact table from a legacy order snapshot

Suppose the system has a frozen historical export **legacy_order_snapshot**, where each row is an order at its final state in the exported data version. The new analytics model wants only **orders with status PLACED** to build **reporting_order_fact_v2** for reporting order counts and merchandise value by tenant/day.

**Example boundaries:**

- **order_id** is a positive ID, globally unique across the source dataset; not reused across tenants.
- Snapshot ID **501** contains fixed data only; ensuring it is not updated/deleted/appended after sealing must be enforced by **storage workflows and write permissions**. The DDL below does not by itself prove the snapshot is immutable.
- Each order is written once to the target. Only **PLACED** enters the fact table; **CANCELLED** creates no target row.
- **total_vnd** is the finalized merchandise amount in the source; refunds, returns, taxes, shipping fees, and foreign currencies are not modeled yet.
- **local_placed_date** is the date in the **Asia/Ho_Chi_Minh** timezone, not the UTC date or ingestion date.
- One job holds write ownership to the target in this example; if multiple jobs update the same order concurrently, additional versioning and ownership policies are required.

### 5.1. Source grain, target grain, and transformation

| Dataset | What is one row? | Key | Notes |
| --- | --- | --- | --- |
| **legacy_order_snapshot** | One order in a specific snapshot | (snapshot_id, order_id) | A snapshot contains both PLACED/CANCELLED |
| **reporting_order_fact_v2** | One PLACED order transformed into the reporting model | source_order_id | One row per order |
| **backfill_jobs** | One backfill run on a specific snapshot and transform | job_id | Stores the committed checkpoint |

Transformation rule:

~~~text
SOURCE: legacy_order_snapshot(snapshot_id = 501)

If status = PLACED:
  source_order_id    = order_id
  tenant_id          = tenant_id
  local_placed_date  =
      DATE(placed_at in timezone Asia/Ho_Chi_Minh)
  amount_vnd         = total_vnd
  source_snapshot_id = 501
  transform_version  = order-fact-v2.1

If status = CANCELLED:
  Do not create a target fact row.
  Still must mark the source key as SCANNED in the checkpoint.
~~~

**Common pitfall:** checkpoint by **scanned source rows**, not by **written target rows**. If a batch contains only three CANCELLED orders, there are zero INSERTs; the job **must still advance the checkpoint** past those three keys. Taking MAX(source_order_id) only from INSERT results can trap the job in an infinite loop over a region of filtered-out orders.

### 5.2. DDL of the snapshot and target table

~~~sql
CREATE TABLE legacy_order_snapshot (
    snapshot_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL CHECK (order_id > 0),
    tenant_id TEXT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    order_status TEXT NOT NULL
        CHECK (order_status IN ('PLACED', 'CANCELLED')),
    total_vnd NUMERIC(20, 0) NOT NULL
        CHECK (total_vnd >= 0),
    PRIMARY KEY (snapshot_id, order_id)
);

CREATE TABLE reporting_order_fact_v2 (
    source_order_id BIGINT PRIMARY KEY,
    source_snapshot_id BIGINT NOT NULL,
    tenant_id TEXT NOT NULL,
    local_placed_date DATE NOT NULL,
    amount_vnd NUMERIC(20, 0) NOT NULL
        CHECK (amount_vnd >= 0),
    transform_version TEXT NOT NULL
);
~~~

In production, you can add foreign keys/relations to dimensions, a snapshot manifest table, and appropriate lineage policies. It is **not** mandatory for every fact to use order_id as its primary key; it is chosen here because the target grain is **one row per order**, and order_id is assumed globally unique.

If the source only guarantees order_id uniqueness **within a tenant**, the target key must include **(tenant_id, source_order_id)** or the corresponding source identifier. Choosing an improperly scoped PRIMARY KEY can cause two valid orders from different tenants to collide on the same key.

### 5.3. Job state table

~~~sql
CREATE TABLE backfill_jobs (
    job_id BIGINT PRIMARY KEY,
    snapshot_id BIGINT NOT NULL,
    transform_version TEXT NOT NULL,
    last_order_id BIGINT NOT NULL DEFAULT 0,
    max_order_id BIGINT NOT NULL,
    batch_count INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL
        CHECK (state IN (
            'RUNNING', 'VERIFYING', 'COMPLETED', 'FAILED'
        )),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (last_order_id >= 0),
    CHECK (max_order_id >= 0),
    CHECK (last_order_id <= max_order_id),
    CHECK (batch_count >= 0)
);
~~~

Field meanings:

- **snapshot_id:** the immutable source set assigned to the job.
- **transform_version:** the rule used to compute target data.
- **max_order_id:** the maximum ID boundary of the snapshot at job creation time.
- **last_order_id:** the **largest source key scanned and committed**, not necessarily the key of an INSERTed row.
- **batch_count:** number of batches with at least one source row scanned and committed.
- **state:** operational state; **COMPLETED** is set only after reconciliation passes.

The initial value **last_order_id = 0** relies on the assumption that all order_ids are positive. For UUID or string keys, use a composite-key checkpoint or dedicated state rather than inventing a "smallest UUID".

### 5.4. Sample historical data with ID gaps and filtered rows

~~~sql
INSERT INTO legacy_order_snapshot (
    snapshot_id, order_id, tenant_id,
    placed_at, order_status, total_vnd
) VALUES
    (501, 101, 'T01',
     TIMESTAMPTZ '2026-11-19 23:50:00+07', 'PLACED', 300000),
    (501, 103, 'T01',
     TIMESTAMPTZ '2026-11-20 00:10:00+07', 'PLACED', 200000),
    (501, 105, 'T01',
     TIMESTAMPTZ '2026-11-20 10:00:00+07', 'CANCELLED', 500000),
    (501, 106, 'T02',
     TIMESTAMPTZ '2026-11-20 11:00:00+07', 'PLACED', 400000),
    (501, 110, 'T01',
     TIMESTAMPTZ '2026-11-20 14:00:00+07', 'PLACED', 100000),
    (501, 111, 'T02',
     TIMESTAMPTZ '2026-11-21 09:00:00+07', 'CANCELLED', 800000),
    (501, 114, 'T02',
     TIMESTAMPTZ '2026-11-21 12:00:00+07', 'PLACED', 700000),
    (501, 120, 'T01',
     TIMESTAMPTZ '2026-11-21 15:00:00+07', 'PLACED', 50000),
    (501, 125, 'T02',
     TIMESTAMPTZ '2026-11-21 16:00:00+07', 'PLACED', 150000);
~~~

The snapshot has **9 rows** with non-contiguous keys (101, 103, 105, 106, 110, 111, 114, 120, 125). Only **7 PLACED orders** belong to the new fact table, with a total merchandise value of **1,900,000 VND**.

### 5.5. Lock in scope once and initialize the job

~~~sql
INSERT INTO backfill_jobs (
    job_id, snapshot_id, transform_version,
    last_order_id, max_order_id, state
)
SELECT
    9001,
    501,
    'order-fact-v2.1',
    0,
    COALESCE(MAX(order_id), 0),
    'RUNNING'
FROM legacy_order_snapshot
WHERE snapshot_id = 501;
~~~

After this statement, **max_order_id = 125**. The number 125 is the **ID high-watermark within the frozen snapshot**, not a watermark of a live stream. If tomorrow source ID 130 appears, it must not be pulled into job 9001 automatically; a new snapshot/job or confirmed catch-up mechanism is needed.

## 6. Processing a batch with keyset pagination and atomic checkpointing

### 6.1. Why not use OFFSET on a live source?

A common pagination pattern:

~~~sql
-- Unsuitable as a reliable checkpoint when the source is changing.
SELECT *
FROM legacy_order_snapshot
WHERE snapshot_id = 501
ORDER BY order_id
LIMIT 3 OFFSET 300000;
~~~

A large **OFFSET** can waste work scanning and discarding many rows. If the source has rows inserted or deleted while the job runs, position 300,000 shifts, causing rows to be duplicated or skipped. On an immutable snapshot, OFFSET may still be semantically usable, but **keyset pagination on a stable key** is usually far better for resumability and avoiding skip costs.

Keyset pattern:

~~~sql
SELECT *
FROM legacy_order_snapshot
WHERE snapshot_id = 501
  AND order_id > 105
  AND order_id <= 125
ORDER BY order_id
LIMIT 3;
~~~

This returns 106, 110, 111 — unaffected by gaps between IDs.

### 6.2. One transaction per batch

Run **the entire block below for each batch**, three times total on the sample data. **Do not** run the INSERT separately and commit the checkpoint in another transaction.

~~~sql
BEGIN;

-- Lock the checkpoint: workers sharing the same job_id will wait for each other.
SELECT
    job_id,
    snapshot_id,
    last_order_id,
    max_order_id,
    state
FROM backfill_jobs
WHERE job_id = 9001
FOR UPDATE;

-- If state is not RUNNING, the application must halt the batch.
WITH batch AS MATERIALIZED (
    SELECT
        s.snapshot_id,
        s.order_id,
        s.tenant_id,
        s.placed_at,
        s.order_status,
        s.total_vnd
    FROM legacy_order_snapshot AS s
    JOIN backfill_jobs AS j
      ON j.snapshot_id = s.snapshot_id
    WHERE j.job_id = 9001
      AND j.state = 'RUNNING'
      AND s.order_id > j.last_order_id
      AND s.order_id <= j.max_order_id
    ORDER BY s.order_id
    LIMIT 3
),
written AS (
    INSERT INTO reporting_order_fact_v2 (
        source_order_id,
        source_snapshot_id,
        tenant_id,
        local_placed_date,
        amount_vnd,
        transform_version
    )
    SELECT
        order_id,
        snapshot_id,
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
        total_vnd,
        'order-fact-v2.1'
    FROM batch
    WHERE order_status = 'PLACED'
    ON CONFLICT (source_order_id) DO NOTHING
    RETURNING source_order_id
),
batch_stats AS (
    SELECT
        (SELECT COUNT(*) FROM batch) AS source_rows_scanned,
        (SELECT MAX(order_id) FROM batch) AS max_source_id,
        (SELECT COUNT(*) FROM written) AS target_rows_inserted
)
UPDATE backfill_jobs AS j
SET
    last_order_id = COALESCE(
        batch_stats.max_source_id, j.last_order_id
    ),
    batch_count = j.batch_count + CASE
        WHEN batch_stats.source_rows_scanned > 0 THEN 1 ELSE 0
    END,
    updated_at = clock_timestamp()
FROM batch_stats
WHERE j.job_id = 9001
  AND j.state = 'RUNNING'
RETURNING
    j.job_id,
    j.last_order_id,
    j.batch_count,
    batch_stats.source_rows_scanned,
    batch_stats.target_rows_inserted;

COMMIT;
~~~

In PostgreSQL, **written** is a data-modifying CTE; it and the checkpoint update belong to the **same transaction**. If an operation fails and the transaction rolls back, **no progress is committed**. Referencing **written** inside **batch_stats** forces evaluation of the inserted row count before returning batch status. The write operation creates facts only for PLACED orders, while **MAX(order_id) comes from the full source batch**.

**ON CONFLICT DO NOTHING** only prevents retries from creating extra rows when the key already exists. It **does not verify** that an existing target row has the right values; therefore field-by-field reconciliation in Section 9 is mandatory. In a production workflow, if an erroneous target row is found, you should stop, log the error, and decide on an audited fix/overwrite rather than using DO NOTHING to silently ignore conflicts.

### 6.3. Expected progress

| Committed batch | Source keys scanned | New PLACED orders written | last_order_id | batch_count |
| --- | --- | ---: | ---: | ---: |
| 1 | 101, 103, 105 | 2 | 105 | 1 |
| 2 | 106, 110, 111 | 2 | 111 | 2 |
| 3 | 114, 120, 125 | 3 | 125 | 3 |

Total scanned: **9 source rows**; total written: **7 target rows**. Two orders (**105 and 111**) were excluded per the rule. When **last_order_id = max_order_id = 125**, all rows in the snapshot have been scanned; the next state is **VERIFYING**, not yet COMPLETED.

For an empty snapshot (max_order_id = 0, last_order_id = 0), the job can transition directly to VERIFYING, yet it must still verify that both the eligible source set and corresponding target set are empty. With ID gaps, reaching max remains valid because the job scanned in order and the source did not change.

### 6.4. Why not record the checkpoint before committing?

If you call an external API to save progress and then the database target write fails, the checkpoint can get ahead of the actual data. When the target DB and checkpoint live in the same PostgreSQL instance, placing both in one transaction is the simplest way to prevent state divergence. On other engines supporting transactional batches, an equivalent verified guarantee is needed.

## 7. Resuming after pause, crash, or worker switch

A resumable job needs more than a **last_id** column. It requires rules defining **when a checkpoint is valid, when a retry is permitted, which logic version the progress depends on, and who is allowed to run the job**.

### 7.1. Crash before COMMIT

Suppose batch 2 is processing keys 106, 110, 111. The database has received some INSERT statements, but the process terminates before COMMIT:

~~~text
Checkpoint before batch: last_order_id = 105.
BEGIN;
  INSERT fact for 106, 110;
  UPDATE backfill_jobs last_order_id = 111;
  ... application crashes before COMMIT.

PostgreSQL rolls back the uncommitted transaction.

On restart:
  last_order_id is still = 105;
  batch 2 data was not committed;
  job safely re-runs batch 2.
~~~

This is the payoff of an **atomic commit** between target rows and the checkpoint. There is no need to guess from application logs which statements reached the database before the disconnect.

### 7.2. Lost response after COMMIT

The application sends COMMIT, but the network drops before the response arrives. It **cannot be sure** whether the transaction committed:

~~~text
If COMMIT succeeded:
  checkpoint advanced and target rows were written.

If COMMIT failed/rolled back:
  checkpoint did not advance and target rows were not written.
~~~

Upon reconnecting, the worker **reads the checkpoint from the database**, rather than continuing from a `last_id` variable held in RAM. If the checkpoint has not advanced, it re-runs the batch; unique keys and an idempotent policy prevent duplicate data.

A useful principle:

> The true execution state lives in the committed checkpoint store; worker logs or in-memory state are purely advisory.

### 7.3. Restarting with the exact source and transformation version

A new worker must verify:

- **job_id = 9001** and **state = RUNNING**.
- **snapshot_id = 501** still exists, is unchanged, and has complete data.
- **transform_version = order-fact-v2.1** matches the logic used by earlier batches.
- **max_order_id = 125** still defines the frozen source boundary.
- **last_order_id** is fetched from the database, not from a cache.

If a new worker uses **v2.2** logic for the remainder while the first half was produced by **v2.1**, the same fact table may contain **two different calculation rules** without reports noticing. You must halt and start a **new job/migration policy**, or safely delete/rebuild the owned dataset after reconciliation. Never swap transform_version mid-run on an active job.

### 7.4. Pausing and resuming is not cancellation

In real systems, a **PAUSED** state may be required:

~~~text
PENDING -> RUNNING -> VERIFYING -> COMPLETED
              |
              +-> PAUSED -> RUNNING
              |
              +-> FAILED -> RUNNING after resolving the error
~~~

The sample schema in Section 5 intentionally simplifies states to RUNNING/VERIFYING/COMPLETED/FAILED; supporting full operational pausing requires extending the CHECK constraint and transition rules. Never set **state = COMPLETED** simply because an operator manually stopped the job.

## 8. Idempotency, concurrent writes, and ownership locks

### 8.1. Idempotency must match the transformation type

| Write pattern | Safe to retry? | Protection mechanism |
| --- | --- | --- |
| **INSERT by unique source ID** | Can be safe | PRIMARY KEY/UNIQUE + payload verification on conflict |
| **UPSERT deterministic values from snapshot** | Can be safe | Same source/version/rule updates to the exact same values |
| **UPDATE SET normalized_col = f(source_col)** | Can be safe | Deterministic function f independent of current wall-clock time |
| **UPDATE SET balance = balance + x** | **Not inherently idempotent** | Dedicated event ID/ledger, deduplication, or snapshot-derived SET |
| **Send email / emit external event** | Not inherently safe | Outbox, idempotency key, consumer-side deduplication |
| **Re-allocate sequence or random ID per retry** | Can create different records | Deterministic source-to-target key, unique constraints |

What not to do when backfilling aggregate totals:

~~~sql
-- Anti-pattern: a retry can add the amount a second time.
UPDATE tenant_totals
SET total_vnd = total_vnd + 300000
WHERE tenant_id = 'T01';
~~~

To recompute totals from verified data:

~~~sql
-- Safer pattern once the source set and cutoff are confirmed.
UPDATE tenant_totals AS t
SET total_vnd = x.new_total_vnd
FROM (
    SELECT tenant_id, SUM(amount_vnd) AS new_total_vnd
    FROM reporting_order_fact_v2
    GROUP BY tenant_id
) AS x
WHERE t.tenant_id = x.tenant_id;
~~~

This snippet **only updates tenants present in both sets** and does not insert rows for new tenants or reset missing ones to 0 when no facts remain. Production code must handle missing groups, source versions, and summary table ownership. The core point is to **SET deterministic values**, not accumulate deltas on each retry.

### 8.2. ON CONFLICT DO NOTHING is not a license to ignore drift

Suppose **source_order_id = 103** already exists in the target, but `amount_vnd` was mistakenly recorded as 250000 instead of 200000. `INSERT ... ON CONFLICT DO NOTHING` will neither raise an error nor fix the value. If you only count rows, the report still shows all 7 orders and may falsely assume the job succeeded.

Therefore you need:

- A unique key blocking two target rows for the same source ID.
- A **conflict != silent success** policy: record conflict metrics/logs and check value equivalence.
- Reconciliation of **key sets and values** before publishing.
- An audited remediation workflow for bad data, rather than silently overwriting data someone else corrected.

With an immutable source and deterministic transform, a conditional UPSERT using **IS DISTINCT FROM** can repair target data, provided you confirm the job **owns write rights** to all those rows and every change is logged. This example uses DO NOTHING to demonstrate simple retries and relies on reconciliation to detect discrepancies.

### 8.3. Multiple workers on the same job

The SQL in Section 6 uses:

~~~sql
SELECT ...
FROM backfill_jobs
WHERE job_id = 9001
FOR UPDATE;
~~~

Locking the checkpoint row forces two workers on the same job to **serialize fetching and advancing last_order_id**, as long as **every worker obeys the same transaction protocol**. This is not a way to scale throughput across 10 workers sharing one checkpoint, because workers will wait on each other.

To process in parallel, assign **non-overlapping key ranges** or independent work units:

~~~text
job_id 9001, shard A: order_id 1..100000
job_id 9002, shard B: order_id 100001..200000
job_id 9003, shard C: order_id 200001..300000
~~~

Each range has its own checkpoint; the design must guarantee that ranges **cover everything completely without overlap**, share the same snapshot and transform version, and do not break shared invariants across jobs. For tenant-partitioned source tables, you can shard by tenant/range, while accounting for whale tenants and query costs.

### 8.4. Leases and fencing when workers run outside a transaction

In a distributed system, a worker may hold a job for minutes, and a network partition can cause the coordinator to reassign it. An **expired lease** alone is not enough to stop the old worker from continuing to write. You can use:

- **owner_id** and **lease_until** for job acquisition.
- A **monotonically increasing fencing_token/epoch** on every ownership change, so the write target rejects stale workers.
- **Checkpoints and batch state** stored in the database with conditional updates checking epoch/version.
- **Target-side idempotency** as the final line of defense.

This mechanism fits cases requiring multiple workers or an external target system. The single-job PostgreSQL example in this lesson does not need extra lease machinery because one transaction and a row lock suffice for the simple scenario; avoid introducing distributed machinery where it is not needed.

### 8.5. Transaction boundaries in multi-table backfills

If a source record produces rows in **order_v2**, **order_lines_v2**, and **order_address_snapshot_v2**, you must determine:

- Which rows must appear **atomically together**?
- How must foreign keys be maintained during batching?
- If writing a child table fails, is the checkpoint rolled back together with the other tables?
- If the tables reside in two separate databases, what is the idempotency/compensation strategy?

Never treat a successful write to one table as completion of a source ID if the remaining tables must be consistent at the same time. Staging tables, batch manifests, and transactions per aggregate or per related group of rows may be required.

## 9. Reconciliation: right count, right keys, right values

A checkpoint **reaching the end** only proves the job scanned the source range under the frozen-snapshot assumption. It **does not prove** the output is correct. Reconciliation requires **at least three layers**:

1. **Key set:** every eligible source row has a target row, with no extra target rows.
2. **Values:** transformed attributes match each source record.
3. **Aggregates:** row counts and monetary sums match per tenant, date, status, and overall scope.

### 9.1. Move the job to VERIFYING, do not mark completed yet

After running the three batches in Section 6 and seeing the checkpoint reach 125:

~~~sql
UPDATE backfill_jobs
SET state = 'VERIFYING',
    updated_at = clock_timestamp()
WHERE job_id = 9001
  AND state = 'RUNNING'
  AND last_order_id = max_order_id
RETURNING job_id, snapshot_id, last_order_id, state;
~~~

If zero rows are returned, the transition precondition is not met. Never infer "nothing left to do" from an empty batch log when the source might still contain rows skipped due to a filter or faulty checkpoint.

### 9.2. Key-by-key and value-by-value reconciliation with FULL OUTER JOIN

The query below computes the **expected source set** using exact v2.1 rules and compares it against target rows belonging to snapshot 501:

~~~sql
WITH expected AS (
    SELECT
        order_id,
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS local_placed_date,
        total_vnd AS amount_vnd
    FROM legacy_order_snapshot
    WHERE snapshot_id = 501
      AND order_status = 'PLACED'
),
actual AS (
    SELECT
        source_order_id,
        tenant_id,
        local_placed_date,
        amount_vnd,
        transform_version
    FROM reporting_order_fact_v2
    WHERE source_snapshot_id = 501
)
SELECT
    COALESCE(e.order_id, a.source_order_id) AS order_id,
    CASE
        WHEN e.order_id IS NULL THEN 'EXTRA_TARGET'
        WHEN a.source_order_id IS NULL THEN 'MISSING_TARGET'
        ELSE 'VALUE_MISMATCH'
    END AS discrepancy_type,
    e.tenant_id AS expected_tenant,
    a.tenant_id AS actual_tenant,
    e.local_placed_date AS expected_date,
    a.local_placed_date AS actual_date,
    e.amount_vnd AS expected_amount,
    a.amount_vnd AS actual_amount,
    a.transform_version
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.source_order_id = e.order_id
WHERE e.order_id IS NULL
   OR a.source_order_id IS NULL
   OR e.tenant_id IS DISTINCT FROM a.tenant_id
   OR e.local_placed_date IS DISTINCT FROM a.local_placed_date
   OR e.amount_vnd IS DISTINCT FROM a.amount_vnd
   OR a.transform_version IS DISTINCT FROM 'order-fact-v2.1'
ORDER BY order_id;
~~~

**Expected result: zero rows.**

Benefits of **FULL OUTER JOIN**:

- **MISSING_TARGET:** a PLACED order exists in the source but lacks a corresponding fact.
- **EXTRA_TARGET:** a fact does not belong to the PLACED set of snapshot 501, e.g., a CANCELLED order ingested by mistake.
- **VALUE_MISMATCH:** the key exists in both places, but tenant, date, amount, or version differs.

Use **IS DISTINCT FROM** instead of inequality **<>** to handle NULLs explicitly. Key fields in this example are NOT NULL; in broader systems, this prevents NULLs from masking comparison errors.

**One explicit limitation:** if the target table holds valid data from other snapshots/jobs, you must isolate the scope via **source_snapshot_id/job scope**. Do not compare all rows of a shared table against one small snapshot and conclude that another tenant's rows are "extra".

### 9.3. Aggregate reconciliation by tenant and date

A bug can slip past a system-wide total check: a T01 order misassigned to T02 leaves the grand total identical. Therefore you must reconcile **at the reporting grain**.

~~~sql
WITH expected AS (
    SELECT
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS report_date,
        COUNT(*) AS order_count,
        SUM(total_vnd) AS amount_vnd
    FROM legacy_order_snapshot
    WHERE snapshot_id = 501
      AND order_status = 'PLACED'
    GROUP BY
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
),
actual AS (
    SELECT
        tenant_id,
        local_placed_date AS report_date,
        COUNT(*) AS order_count,
        SUM(amount_vnd) AS amount_vnd
    FROM reporting_order_fact_v2
    WHERE source_snapshot_id = 501
    GROUP BY tenant_id, local_placed_date
)
SELECT
    COALESCE(e.tenant_id, a.tenant_id) AS tenant_id,
    COALESCE(e.report_date, a.report_date) AS report_date,
    e.order_count AS expected_count,
    a.order_count AS actual_count,
    e.amount_vnd AS expected_amount,
    a.amount_vnd AS actual_amount
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.tenant_id = e.tenant_id
 AND a.report_date = e.report_date
WHERE e.tenant_id IS NULL
   OR a.tenant_id IS NULL
   OR e.order_count IS DISTINCT FROM a.order_count
   OR e.amount_vnd IS DISTINCT FROM a.amount_vnd
ORDER BY tenant_id, report_date;
~~~

This query must also return **zero rows** on the sample data.

Expected aggregate results:

| tenant | Local date | PLACED orders | Merchandise total (VND) |
| --- | --- | ---: | ---: |
| T01 | 2026-11-19 | 1 | 300,000 |
| T01 | 2026-11-20 | 2 | 300,000 |
| T01 | 2026-11-21 | 1 | 50,000 |
| T02 | 2026-11-20 | 1 | 400,000 |
| T02 | 2026-11-21 | 2 | 850,000 |
| **Total** | | **7** | **1,900,000** |

A quick global sum check:

~~~sql
SELECT
    COUNT(*) AS fact_rows,
    SUM(amount_vnd) AS total_vnd
FROM reporting_order_fact_v2
WHERE source_snapshot_id = 501;
-- 7 rows, 1900000 VND.
~~~

**Matching row counts and matching total amounts are still not enough.** Two rows could have swapped values, or a positive discrepancy could be offset by a negative one. The key/field reconciliation in Section 9.2 cannot be skipped just because totals match.

### 9.4. What roles do checksums, hashes, and sampling play?

With billions of records, full row-by-row comparison can be expensive. You can use:

- **Counts and sums** per partition/tenant/day as an initial signal.
- **Min/max IDs and date bounds** to spot missing ranges.
- **Bucketed hashes/checksums** to narrow down where differences occur.
- **Targeted sampling** to verify timezones, NULLs, encoding, and edge-case identifiers.
- **Key anti-joins** and field comparisons whenever a bucket looks suspect.

However, checksums can collide, suffer from canonicalization differences, or omit critical metadata. **Sampling does not prove the absence of bugs**, and counts/sums can still match even when rows are wrong. For high-correctness reporting, stronger reconciliation workflows or verified immutable input proofs are required.

### 9.5. Mark COMPLETED only after reconciliation passes

After running the checks and confirming zero discrepancies, the job can transition to **COMPLETED**. Rather than relying solely on manual confirmation, a single statement can verify row equivalence under the sample rules before transitioning state:

~~~sql
BEGIN;

WITH expected AS (
    SELECT
        order_id,
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS local_placed_date,
        total_vnd AS amount_vnd
    FROM legacy_order_snapshot
    WHERE snapshot_id = 501
      AND order_status = 'PLACED'
),
actual AS (
    SELECT
        source_order_id,
        tenant_id,
        local_placed_date,
        amount_vnd,
        transform_version
    FROM reporting_order_fact_v2
    WHERE source_snapshot_id = 501
),
discrepancies AS (
    SELECT 1 AS problem
    FROM expected AS e
    FULL OUTER JOIN actual AS a
      ON a.source_order_id = e.order_id
    WHERE e.order_id IS NULL
       OR a.source_order_id IS NULL
       OR e.tenant_id IS DISTINCT FROM a.tenant_id
       OR e.local_placed_date IS DISTINCT FROM a.local_placed_date
       OR e.amount_vnd IS DISTINCT FROM a.amount_vnd
       OR a.transform_version IS DISTINCT FROM 'order-fact-v2.1'
)
UPDATE backfill_jobs
SET state = 'COMPLETED',
    updated_at = clock_timestamp()
WHERE job_id = 9001
  AND state = 'VERIFYING'
  AND last_order_id = max_order_id
  AND NOT EXISTS (SELECT 1 FROM discrepancies)
RETURNING job_id, state, last_order_id, max_order_id;

COMMIT;
~~~

**If zero rows are returned, completion must not be declared.** This statement checks the sample table data within a transaction; it **does not** verify that the source was truly immutable, prove business logic correctness, validate other downstream consumers, or replace cutover approval workflows. In real systems, reconciliation outputs must be persisted by **job_id, rule version, execution timestamp, and metric suite** for auditing.

### 9.6. Do not confuse COMPLETED with having switched the application

The **COMPLETED** state in this example means the snapshot backfill has been scanned and reconciled. If the operational source is still receiving new writes, **catch-up** is still needed. If users are still reading the old table, **cutover and monitoring** are still required. If old consumers have not been upgraded, the legacy schema cannot yet be dropped.

In large systems, backfill state and rollout state may be **two separate state machines**, avoiding overloading a single status column for all phases.

## 10. When source data is edited: distinguishing corrections from replay

### 10.1. From an immutable snapshot to a source with revisions

Snapshot 501 was assumed unchanging. When reading directly from a live **orders** table, however, this can happen:

~~~text
10:00  Backfill reads order 103: total = 200000.
10:01  Application updates order 103: total = 250000.
10:02  Backfill has already advanced the checkpoint past order 103.
10:03  Target table shows total = 200000, current source = 250000.
~~~

**Continuing from ID > 103 will never automatically fix row 103.** Thus an ID-based checkpoint tracks only **scan progress**, not updates to a mutable source.

Three design approaches:

1. **Snapshotted/frozen source:** every batch reads the same version, explicitly noting it is **as-of snapshot** data; followed by a separate catch-up phase.
2. **Revision-tracked source:** select the exact revision as of the cutoff, then process newer revisions as explicit corrections.
3. **Change stream/CDC:** start capturing changes before or at the snapshot point, catching up after the backfill to a verified source checkpoint.

Simply adding **updated_at** and polling rows with newer timestamps is insufficient: application clocks can skew, multiple edits can share a timestamp, hard deletes leave no row to scan, and a record may change multiple times between polls. A stable version or commit-position mechanism is far more reliable.

### 10.2. A current-state row differs from a financial event

If the live source table changes **order_status** from PLACED to CANCELLED, you must answer:

- Does the target fact represent **"orders that were ever placed"** (an immutable event), or **"orders currently PLACED"** (a state snapshot)?
- Does CANCELLED emit an **adjustment event** or delete the target row from the set?
- Must historical state at placement time be preserved?
- Do reporting metrics use placed date, cancelled date, or updated date?

You cannot simply swap INSERT for UPSERT and assume business semantics are preserved. For an "order placed" event, history may need to keep a separate cancellation event. For a "currently PLACED orders" snapshot, a new revision may require **deleting or marking inactive** in the derived table. **Grain and time semantics dictate correction behavior.**

### 10.3. Applying modifications in the proper order

Suppose two messages for order 103 arrive at a consumer out of order:

~~~text
order 103 @ version 8 -> total = 250000 (arrived first)
order 103 @ version 7 -> total = 200000 (arrived later due to retry)
~~~

If the consumer blindly overwrites with whichever message arrives later, the newer state is replaced by the stale one. You should store **source_version/sequence** and accept updates only when the incoming version is newer than the stored one, or process via a source protocol guaranteeing order.

Conditional pattern example:

~~~sql
-- Simplified example when the target table carries source_version.
INSERT INTO order_projection (order_id, source_version, amount_vnd)
VALUES (103, 8, 250000)
ON CONFLICT (order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    amount_vnd = EXCLUDED.amount_vnd
WHERE order_projection.source_version < EXCLUDED.source_version;
~~~

**This snippet assumes** an **order_projection** table already exists with those three columns and that the source guarantees monotonically increasing versions per order. It is a standalone pattern for mutable sources, **not a continuous executable DDL part** of the snapshot example in Sections 5–9.

If two messages share the same source_version but carry different payloads, treat it as a **source data conflict** and investigate; do not arbitrarily pick the last arrival. For tombstones/deletes, equivalent ordering protection and deletion policies are required.

## 11. When the source still takes new writes: snapshot + CDC + catch-up before cutover

Historical backfill over a frozen snapshot solves **the past**. For applications that cannot halt writes, you also need a mechanism to bring **changes that occurred during the backfill** into the new model.

### 11.1. Two distinct problems to solve together

**Problem A — historical scope:** did the backfill accurately reproduce all data at a specific snapshot point?

**Problem B — post-snapshot mutations:** while the backfill runs, the application continuously INSERTs/UPDATEs/DELETEs; does the new model receive and apply those mutations accurately?

Completing A alone is not enough to switch APIs to read the new table as current state. Conversely, only subscribing to CDC starting now will not populate pre-existing rows.

### 11.2. Canonical timeline

~~~mermaid
sequenceDiagram
    participant S as Source DB
    participant C as CDC / change stream
    participant B as Backfill worker
    participant T as Target V2
    participant R as Read routing
    S->>C: Set checkpoint / start capture
    S-->>B: Consistent snapshot at S0
    B->>T: Backfill rows in S0 by batches
    S->>C: Changes after S0
    B->>T: Complete backfill, reconcile snapshot
    C->>T: Catch-up changes by source version
    T-->>R: Report reconciled and checkpoint S1 reached
    R->>T: Cutover reads to V2
    C->>T: Continue syncing new changes
~~~

This diagram is **a logical architecture**, not specific CDC configuration commands. Depending on the database and tooling, how a snapshot pairs with a log position varies. Correctness depends on **having no gap between snapshot S0 and the change stream**, avoiding indefinite dual sources of truth, and applying versions/order properly.

### 11.3. Invariant for the catch-up phase

Let:

~~~text
S0 = source snapshot at a defined point in time / log position
L0 = log position corresponding to S0
L1 = log position processed and confirmed at target

Target V2 after catching up to L1 must be equivalent
to the source state after applying all changes
from snapshot S0 through position L1,
according to the chosen data contract.
~~~

With multiple independent sources, a **single L1** may not exist; you must maintain checkpoints/watermarks **per source** and rules defining when analytical outputs are eligible for publication.

### 11.4. Why MAX(id) on a live source is insufficient

A particularly subtle bug:

~~~text
T1: Transaction A fetches nextval() = 100.
T2: Transaction B fetches nextval() = 101 and commits.
T3: Backfill sees MAX(id) = 101, scans up to 101.
T4: Transaction A finally commits record id = 100.
T5: Job already checkpointed last_id = 101 and never re-scans <=101.
=> id=100 is missed.
~~~

**Increasing IDs do not guarantee commits in increasing ID order.** This holds even when a single database sequence generates increasing numbers. Using an ID watermark safely requires stronger preconditions (a truly frozen source, a consistent snapshot paired with capture, or a proven specialized algorithm), not merely inspecting MAX(id).

### 11.5. Dual-write is not automatically consistent

Sometimes the application is modified to write to both the old and new tables:

~~~text
write old -> write new
~~~

If both writes happen in the same database and same transaction, atomicity can protect certain invariants. If they span two databases or two independent services, **the old write succeeding while the new write fails** causes drift; retries can also duplicate events.

Valid solutions include **transactional outbox, CDC, ordered change logs with idempotent consumers**, or purpose-built migration protocols. Never call an operation **exactly-once** merely because it passes the same request ID twice.

### 11.6. Practical cutover conditions

A safe strategy typically requires:

- Snapshot S0 backfill complete and reconciled accurately.
- Change consumer from S0 caught up to an acceptable source checkpoint/boundary S1.
- Pending **quarantine**, retry backlog, and error records resolved or explicitly approved.
- Sample queries / shadow reads between the old source and V2 matching per definition.
- Constraints, indexes, and SLOs of the new read path benchmarked.
- Routing/feature flag supporting rollback, without deleting the old source immediately.
- Ongoing detection and remediation for post-cutover drift.

**Zero lag at a single instant** is insufficient if the consumer can drop events or persist faulty checkpoints. Key/version reconciliation and continuous monitoring are needed.

## 12. Backfill when target cardinality is no longer one-to-one

The main example maps one PLACED source row → one fact. Yet many important migrations involve different grains:

### 12.1. One source producing multiple target rows

From an order containing multiple historical addresses, we might transform into:

~~~text
legacy_orders(order_id, shipping_address_json)
    ->
order_addresses(order_id, address_kind, version, ...)
~~~

The checkpoint must advance by **fully processed order_id**. If order 103 yields three address rows and only two were written, you must not checkpoint 103 as complete. Target keys such as **(order_id, address_kind, version)** must be deterministic, not randomly generated on retry.

### 12.2. Many sources producing one aggregate row

Consider a daily sales table with grain **(tenant_id, day)**. One batch scans orders 101–103 and adds to the total; the next scans 105–106 and adds again. If the first batch retries with **total = total + batch_sum**, the aggregate table double-counts unless there is a **batch contribution ledger** and an idempotency key.

An approach usually easier to reconcile:

1. Backfill into a **granular fact table** keyed by unique source ID.
2. Compute the aggregate table via **GROUP BY from the verified fact set**, or record per-batch contributions with a deduplication key.
3. Publish aggregates only once the eligible source set is complete or explicitly tagged as provisional.

### 12.3. SCD Type 2 dimensions and validity intervals

If historical transactions must be linked to the **customer dimension** version effective at transaction time, you cannot JOIN solely on customer_id across all dimension versions. You must specify:

~~~text
customer_id = customer business key
placed_at = timestamp to map
dim_customer.valid_from <= placed_at < valid_to
~~~

where the half-open upper bound **valid_to** is a convention that must be agreed upon. Where required, the dimension must prevent **overlapping validity intervals** for the same business key; otherwise a single fact could JOIN to two versions and multiply rows.

Beyond adding a surrogate key column, backfill may also require **late-arriving dimension rules** and reference-table snapshots. Current dimension data does not automatically represent historical truth on the order date.

### 12.4. Format conversion while preserving domain meaning

Operations such as:

- Timezone conversion.
- Phone number normalization.
- Splitting names/addresses.
- Converting currency from VND to minor units.
- Shredding attribute JSON into relational tables.

require a **transformation contract**, especially for missing values, malformed inputs, encoding, date boundaries, and edge cases. Do not force historical data into a new format using a fabricated value that alters its meaning. For example, do not turn **an old address with unknown district** into **a default district** and treat it as verified.

## 13. Batch sizing and database resource control

A single UPDATE/INSERT across hundreds of millions of records in one transaction can cause **massive WAL volume, replication lag, long lock holds, bloat, and painful rollbacks**. Batching restores control, though batches that are too small increase commit and loop overhead.

### 13.1. Choosing batch size from measurements

The example uses **LIMIT 3** for easy observation. Production may use thousands or more, yet there is no universal "standard batch size" for every schema.

Measure at least:

| Metric | Purpose |
| --- | --- |
| **Batch duration** (p50/p95/p99) | Spot outlier chunks, balance lock hold time |
| **Source rows scanned/second** | True historical scan rate |
| **Target rows written/second** | Actual data fill rate; differs from scan rate when filtering |
| **WAL bytes / replication lag** | Avoid slowing replicas and inflating log storage |
| **CPU, IOPS, network, disk free** | Ensure backfill does not starve serving traffic |
| **Lock wait, deadlock, timeout** | Detect contention with the live application |
| **Index maintenance, vacuum pressure** | Assess physical-schema impact of heavy writes |
| **Backlog and estimated remaining** | Plan cutover, without treating estimates as hard promises |

A common technique is throttling batch size or worker concurrency **based on system pressure**, rather than running flat-out during peak hours. If application p99 latency rises or replica lag crosses an agreed threshold, throttle down or pause cleanly.

### 13.2. Short batches, frequent commits, without giving up atomicity

A batch transaction typically performs:

~~~text
BEGIN
  lock/read checkpoint
  read limited source rows
  transform + write target rows
  advance checkpoint to max scanned source key
COMMIT
~~~

**A transaction spans only one batch**, not a multi-day run. This limits how much work rolls back if a batch fails. However, when one source record produces multiple rows that must appear atomically, the batch must guarantee **all related rows and the checkpoint commit together**.

In PostgreSQL, you can set safe **lock_timeout/statement_timeout** limits and retry with backoff in the orchestrator. Never retry invalid data indefinitely: distinguish transient deadlocks/timeouts that can be retried from immutable data errors requiring quarantine or rule fixes.

### 13.3. Indexing along the backfill read path

The sample source has:

~~~sql
PRIMARY KEY (snapshot_id, order_id)
~~~

which naturally supports the query:

~~~sql
WHERE snapshot_id = 501
  AND order_id > :last_order_id
ORDER BY order_id
LIMIT :batch_size
~~~

because the index key starts with snapshot_id followed by order_id. If a real-world table differs, inspect **EXPLAIN**, table statistics, and index health to avoid full-scanning on every batch.

When designing new indexes for very large tables:

- Weigh index build cost, storage footprint, and elevated write load during backfill.
- Some engines support **concurrent/online** index builds with specific caveats; for instance, PostgreSQL **CREATE INDEX CONCURRENTLY cannot run inside a regular transaction block**.
- **UNIQUE/FK/NOT NULL** constraints need a rollout order that avoids locking the application for too long.
- Never drop indexes needed by production queries merely to speed up batch writes without a replacement plan.

### 13.4. Partitions and processing scopes

If data is organized by month, tenant, or shard, you can split jobs by **partition or separate key range**:

~~~text
run snapshot 501:
  partition 2025-01 -> own checkpoint
  partition 2025-02 -> own checkpoint
  ...
  partition 2026-11 -> own checkpoint
~~~

Each partition needs its own reconciliation and overall coverage reporting; never mark a global job completed when only one partition succeeded. With **whale tenants**, splitting evenly by tenant count does not guarantee even runtimes — measure row counts and per-slice weight.

When backfilling across **multiple shards**, unique constraints and foreign keys may not be enforced globally the same way as on a single PostgreSQL instance. Each shard keeps its own checkpoint, yet the overall system still requires a **scope manifest and gapless, non-overlapping reconciliation**.

### 13.5. Evaluation time can corrupt results worse than slow speed

If each batch calls **CURRENT_DATE** to infer "today" or looks up the **current** price table without pinning a version, the same record can yield a different result after a job restart. For historical backfills, critical transformations must rely on:

- The **record's** business timestamp.
- Locked-in timezone and rounding policy.
- Snapshot/version of dimensions, exchange rates, and reference data.
- Versioned algorithm, configuration, and input contract.

**Speeding up a job cannot compensate for getting time semantics wrong.**

## 14. Observability and error handling by state

### 14.1. Fields to display on a backfill dashboard

~~~text
job_id
snapshot_id / source_manifest_id
transform_version / code digest
state
last_committed_source_key / high_watermark
source_rows_scanned
target_rows_inserted
target_rows_skipped_on_conflict
batch_count
failed_batch_count
batch_duration_p95
source/target errors + quarantine count
last_commit_at
reconciliation_status / diff_count
change_stream_lag (if CDC is used)
published_version (if cutover occurred)
~~~

**Do not treat estimated percentage = last_id / max_id** as an accurate completion ratio if IDs have gaps or skewed distribution. In the sample, `last_id` 111 does not mean 111/125 of orders were processed; in reality, 6/9 rows were scanned. For a row-based percentage, you need a **source count manifest** or reliable cumulative scanned row counts.

Even 100% scan progress only proves **scanning reached the end**, not that **reconciliation succeeded**.

### 14.2. Failure and action matrix

| Scenario | Impact | Appropriate action |
| --- | --- | --- |
| Worker crashes before COMMIT | Batch was not committed | Read checkpoint from DB, re-run |
| Network drops after sending COMMIT | Uncertain whether commit succeeded | Reconnect, inspect checkpoint/target; do not guess |
| Duplicate source ID with differing payload | Inconsistent source | Quarantine, alert source owner; do not pick arbitrarily |
| Target already holds key with different value | Idempotency key matches, payload differs | Halt/reconcile, determine ownership and remediation |
| Batch has only filtered-out rows | Zero target rows INSERTed | Still advance checkpoint by scanned source keys |
| Row contains unconvertible value | Batch fails or row excluded | Explicit rejection/quarantine rule with reason; do not silently NULL |
| Source snapshot modified | Checkpoint no longer reflects a frozen set | Stop, create new snapshot/manifest, reconcile impact |
| CDC lag rising | New model falling behind source | Hold cutover, scale capacity, drain backlog |
| Source/target counts match but amounts differ | Mapping or transform bug | Compare record-by-record and aggregate by group |
| Cutover done but SLO degrades | User impact | Roll back read routing if safe, investigate indexes/queries |
| Retention purges raw data too early | Cannot replay | Halt purge, restore from archive/backup if available, assess evidence |

### 14.3. Marking FAILED is not deleting the checkpoint

When a job hits a business/data error, **preserve the checkpoint and committed batches** for investigation. Before transitioning from FAILED back to RUNNING, verify:

- Snapshot and transform version remain unchanged.
- Discrepancies have been resolved.
- Previously committed target rows remain valid.
- Job state/lease ensures no stale worker is still writing.

If the transform logic changed, resuming from the old checkpoint can mix rules; you typically need a new job version or a plan to rebuild the affected scope rather than merely flipping state to RUNNING.

### 14.4. How to report completion clearly

An acceptance report can take this form:

~~~text
BACKFILL: order-fact-v2.1
SNAPSHOT: 501, immutable, manifest verified
JOB: 9001, state COMPLETED
SOURCE SCANNED: 9 records
SOURCE ELIGIBLE: 7 PLACED records
TARGET: 7 rows
ROW-LEVEL DIFF: 0
TENANT-DATE DIFF: 0
TARGET AMOUNT: 1,900,000 VND
TRANSFORM TIMEZONE: Asia/Ho_Chi_Minh
CDC CATCH-UP: Not applicable to frozen snapshot example
CUTOVER: Not yet executed
QA: structural/readback only until professional QA phase
~~~

**Note:** this is an **expected sample output from the illustrative dataset**, not output actually executed against a database in this article. During real acceptance, you must attach actual query outputs, run IDs, code versions, and approver/scope sign-off. Avoid equating "wrote the script" with "executed and verified the script".

## 15. Designing for rollback and reproducibility

### 15.1. Keep the legacy read path during a controlled window

After reconciliation and catch-up, the application can use a **feature flag** or routing rule to switch:

~~~text
Before:
  GET /reports/orders -> legacy query

During cutover:
  GET /reports/orders -> v2 query
  shadow comparison logged separately (shadow data not returned)

On failure:
  fall back to legacy query per rollback policy
~~~

Rolling back the read path is safe only if **the legacy data path is still kept up to date / continues to meet its contract**. Once writes to the old source stop, toggling a feature flag alone will not bring new data back into the old model. You must plan for **data rollback**, not merely application code rollback.

### 15.2. Do not delete the source immediately after reports match

Point-in-time reconciliation is a necessary condition, not sufficient reason to drop old tables. Other consumers may still read them; historical records may be required for audits; a subtle bug might surface only after days of real load.

The contract plan should list:

- Which consumers have been upgraded and verified?
- Do any legacy batches/jobs/exports still reference the schema?
- What are the appropriate rollback window and retention period?
- Are backups/immutable snapshots and a restore procedure in place?
- Is there a workflow for late events or post-cutover corrections?

### 15.3. Replaying the same input may not yield the same output without versions

For reliable replay, storing just the SQL text is not enough. You must persist:

~~~text
source snapshot / manifest / checksum
source schema and key scope
transform code + config version
timezone, currency, rounding policy
reference data / dimension snapshots
job ID and committed batches
quarantine state and error-handling decisions
~~~

If a step looks up a **live country_codes table** whose values later change, a replay can produce different outputs even when the order snapshot is unchanged. Reference datasets affecting transformations must be versioned or pinned to the appropriate point in time.

### 15.4. Preserve evidence without endlessly duplicating sensitive data

A progress table does not need to copy full customer payloads. It needs source identifiers, snapshot/version metadata, and reconciliation results. Raw backups can live in a separate store with access controls/retention, while lineage metadata points back to the exact source when needed.

When backfilling personal data, the workflow must preserve tenant isolation, source-read/target-write permissions, and protect logs from leaking emails, phone numbers, tokens, or sensitive content. Having a resumable checkpoint **does not authorize** a worker to read across other tenants outside its granted scope.

## 16. Runbook from preparation to acceptance

A runbook must be clear enough for someone else to take over if the original worker goes away. A backfill runbook may include:

### Phase A — Approve model and scope

1. Explicitly document **grain, source key, target key, eligible row set**, and comparison rules.
2. Confirm source of truth, **snapshot/version**, time definitions, timezone, and invalid-data policy.
3. Verify DDL, constraints, indexes, target capacity, WAL, replication lag, and backup/restore readiness.
4. Select initial batch size, concurrency, target throughput, and stop thresholds.
5. Confirm rollback/read-routing capability and legacy data retention window.

### Phase B — Create fixed input and guard progress

1. Create/seal the snapshot or establish a consistent snapshot linked to a source checkpoint.
2. Store the manifest: row count, key range, source, version, checksum if used, and seal timestamp.
3. Create the job with **snapshot_id, transform_version, high-watermark**, starting `last_id`, and state RUNNING.
4. Restrict job/target write permissions, preventing two independent coordinators from claiming the same job.

### Phase C — Controlled execution

1. Worker reads the checkpoint **from the database**.
2. Lock the job's checkpoint update rights.
3. Select a batch using **keyset pagination** from the snapshot.
4. Write eligible target rows using proper keys/idempotency.
5. Update the checkpoint to **scanned source keys**.
6. Commit **in the same transaction**.
7. Record batch metrics and continue until the full range is scanned.
8. On error, preserve committed state and identify the root cause before retrying.

### Phase D — Verify and catch up

1. Transition the job to VERIFYING; **do not publish yet**.
2. Compare **expected vs actual** by ID, every required column, group set, and total amount.
3. Resolve discrepancies; when fixing rules, create a new job/version or rebuild per policy.
4. For live sources, apply post-snapshot CDC/change stream and reconcile at the new checkpoint.
5. Run shadow queries, verify performance and data access permissions on the new read path.

### Phase E — Publish and contract

1. Record acceptance evidence, scope, reconciliation numbers, and sign-off.
2. Gradually shift read routing per plan, monitoring p95/p99 and correctness.
3. Keep the rollback procedure ready if metrics or latency miss targets.
4. Drop the old model only after all consumers are verified and the rollback window expires.
5. Retain checkpoints, manifests, and reconciliation results per approved retention policy.

### 16.1. Completion criteria should never be just a percentage

An acceptance checklist can state:

~~~text
SOURCE:
  snapshot/manifest immutable = verified
  expected eligible keys = 7
  source scope and transform_version = fixed

PROCESSING:
  last_committed_key = high_watermark = 125
  failed/unresolved batches = 0
  retry duplicates with conflicting payload = 0

DATA:
  target keys = expected keys
  row-level diff = 0
  group-level diff = 0
  total amount = 1,900,000 VND

INTEGRATION:
  source changes caught up (or not applicable)
  application shadow reads = pass
  latency and resource thresholds = pass

RELEASE:
  publication approved
  rollback procedure exercised
  legacy retention and consumers checked
~~~

These criteria use the lesson's sample numbers. Real systems must explicitly define acceptance tolerances, including **approved quarantine handling**; never arbitrarily settle for "99.9% rows correct" if the remaining 0.1% could hold critical transactions.

## 17. Practice exercises

### Exercise 1 — Resuming after a crash inside a batch

A snapshot has IDs **101, 103, 105, 106, 110, 111, 114, 120, 125**. The job has **last_order_id = 105**. A worker processes the next batch **106, 110, 111**, writes rows 106 and 110, and loses connection before learning whether COMMIT succeeded.

**Questions:**

1. Can the in-memory checkpoint be updated to 111 to skip the batch?
2. What must the worker do first upon restarting?
3. If the transaction committed, what states are the rows and checkpoint in?
4. If the transaction rolled back, what states are they in?
5. What property is required so retries do not duplicate data?

<details>
<summary>Suggested solution for Exercise 1</summary>

You must never guess the outcome from in-memory variables. The worker must reconnect and **read the committed checkpoint**. If COMMIT succeeded, the batch's target rows and **last_order_id = 111** coexist atomically. If it rolled back, **the checkpoint remains 105**, and the batch was not committed to the target.

When re-running, **source_order_id is the unique key** of the fact table; the INSERT/UPSERT must have an idempotent policy and payload verification. Writing target rows and the checkpoint within **the same transaction** is the key safeguard preventing progress from outrunning data.

</details>

### Exercise 2 — Filtered orders and faulty checkpointing

Suppose a batch contains only two orders:

~~~text
order_id = 205, status = CANCELLED
order_id = 209, status = CANCELLED
~~~

The job saves the checkpoint by taking **MAX(source_order_id)** from rows INSERTed into the fact table.

**Question:** explain the bug, state what the checkpoint after the batch should be, and describe how to compute it properly.

<details>
<summary>Suggested solution for Exercise 2</summary>

Both orders are excluded by the PLACED fact rule, so **zero rows are INSERTed**. Taking MAX from target rows yields **NULL**, the checkpoint fails to advance, and the job can re-read this batch in an infinite loop.

The checkpoint must be based on **MAX(order_id) of the scanned source batch**, equal to **209**, even when target rows written is **0**. Extracting the key from the source batch must occur in the same transaction as the target writes.

</details>

### Exercise 3 — Matching row count but wrong values

The source has three PLACED orders:

| order_id | tenant_id | total_vnd |
| ---: | --- | ---: |
| 1 | T01 | 100000 |
| 2 | T01 | 200000 |
| 3 | T02 | 300000 |

The target has three rows, but **order 1 has 150000, order 2 has 150000, and order 3 keeps 300000**.

**Questions:**

1. Will system-wide COUNT(*) and SUM(amount_vnd) detect the error?
2. Will per-tenant totals detect it?
3. Which reconciliation method reliably catches the two wrong values?
4. If the target has one extra order and lacks one source order with the exact same amount, which check is essential?

<details>
<summary>Suggested solution for Exercise 3</summary>

COUNT still equals **3** and SUM still equals **600000**; T01's total stays **300000** and T02's stays **300000**, so even per-tenant totals **fail to detect** the two altered values.

You must compare **by source_order_id and field-by-field** using a properly scoped FULL OUTER JOIN/EXCEPT. For one extra order and one missing order of equal value, you must compare **key sets** with a bidirectional anti-join; row counts and total amounts alone can still match.

</details>

### Exercise 4 — High-watermark on an actively written table

Transaction A acquires order_id **300** without committing yet. Transaction B acquires **301** and commits. The backfill reads MAX(order_id) = 301, scans up to 301, and sets last_id = 301. Afterwards, A commits order 300.

**Questions:**

1. Why can order 300 be missed?
2. Does increasing batch count or lowering LIMIT fix the root cause?
3. Name two safe approaches for backfilling in a still-active system.
4. With CDC, which boundary must be recorded so there is no gap between snapshot and change stream?

<details>
<summary>Suggested solution for Exercise 4</summary>

IDs are allocated before commit; once the backfill advances past 301, it will never re-read 300. Raising or lowering LIMIT does not fix **commit order differing from ID allocation order**.

Two approaches: (a) **freeze the source or use an immutable snapshot** and backfill that scope; (b) **a consistent snapshot combined with CDC/outbox carrying a source checkpoint**, catching up with changes emitted after the snapshot. You must persist the **source log position/checkpoint tied to the snapshot**, not merely MAX(id), to avoid missing transactions committed after the boundary.

</details>

### Exercise 5 — Choosing a retry-safe aggregate write strategy

A pipeline needs to populate **tenant_daily_sales(tenant_id, report_date, amount_vnd)** from millions of transaction lines. A developer proposes splitting events into batches and for each batch running:

~~~sql
UPDATE tenant_daily_sales
SET amount_vnd = amount_vnd + :batch_total
WHERE tenant_id = :tenant_id
  AND report_date = :report_date;
~~~

**Questions:**

1. Why can re-running a batch corrupt the numbers?
2. Propose a granular model or ledger for idempotent writes.
3. What must be retained if a transaction is corrected after the summary table was published?

<details>
<summary>Suggested solution for Exercise 5</summary>

Addition is **not idempotent**: re-running the same batch adds the amount again. An easily verifiable approach is writing **event/order facts** keyed by a unique source key, then **recomputing SUM** for the groups needing updates; or storing **batch_contributions(batch_id, tenant_id, report_date, amount_vnd)** with a UNIQUE constraint on batch identity and summing from the deduplicated ledger.

When a source record receives a correction, you must retain source ID/version, affected group mapping, transform version, and published run; groups can then be recomputed and change history recorded rather than silently incrementing or decrementing totals without an audit trail.

</details>

### Exercise 6 — Timestamp boundaries and history

An order was placed at **2026-11-20 00:10:00+07**, but the legacy pipeline recorded its date from the **UTC date**. A new reporting application wants to use the Vietnam local date.

**Questions:**

1. What is the local date of this order?
2. What is the corresponding UTC date?
3. Why can switching dates in the fact table shift daily totals between two days even though the overall period total stays unchanged?
4. What metadata ensures replays produce the same result?

<details>
<summary>Suggested solution for Exercise 6</summary>

The Vietnam local date is **2026-11-20**, whereas the corresponding instant in UTC is **2026-11-19 17:10:00Z**, making the UTC date **2026-11-19**. If the old pipeline grouped by UTC date, this order fell into Nov 19; the new pipeline groups by Vietnam date, placing it in Nov 20. Hence daily totals can shift between two days, even though the grand total across the full range remains unchanged when date boundaries are reconciled consistently.

You must store the source timestamp with its proper timezone, **transform_version**, timezone/time configuration, snapshot/cutoff, and reference data versions (if any), rather than relying implicitly on the runner host's timezone.

</details>

### Exercise 7 — Cutover or not?

The historical snapshot backfill reconciled with zero discrepancies. However, Order Service is still creating new orders; the CDC consumer is **25 minutes** behind, and there is no evidence that all quarantined records have been resolved.

**Question:** should the entire dashboard be switched to V2? List at least four conditions that must be checked before publishing.

**Suggested solution:** we cannot yet conclude V2 is fresh and complete. We must check the CDC checkpoint/watermark and confirm lag meets the SLO, clear the quarantine backlog, reconcile changes from the snapshot up to cutover time, shadow-read old vs new results, verify query latency and access permissions, prepare rollback, and record the version/manifest of the dataset to be published.

## 18. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| “Running a single UPDATE is enough for a backfill.” | Large datasets require batching, checkpointing, monitoring, reconciliation, and rollback. |
| “Once a row is read, we can checkpoint past it.” | Checkpoint only when **the corresponding target writes have committed**. |
| “The checkpoint should take MAX ID of INSERTed rows.” | It must take **MAX scanned source key**, including filtered-out rows. |
| “Increasing IDs always commit in order.” | Sequence/ID allocation and commit order can differ. |
| “Adding more shards makes backfill automatically right and fast.” | You must partition ranges properly, protect integrity, and measure actual load. |
| “ON CONFLICT DO NOTHING proves target data is right.” | It only skips duplicate inserts; existing rows can still hold wrong values. |
| “Matching row counts means reconciliation passed.” | Missing and extra rows can cancel out; compare key sets and values. |
| “Matching total money is enough.” | Offsetting errors can cancel out; reconcile per record and per group. |
| “The source has MAX(id), so no snapshot is needed.” | Records with IDs below max can commit late, or scanned rows can be UPDATEd. |
| “Having a checkpoint automatically gives exactly-once.” | You also need transactions or idempotency, unique keys, and ordering guards. |
| “Once snapshot backfill finishes, the data is up to date.” | You must catch up post-snapshot changes when the source is live. |
| “If a batch fails, just retry forever.” | Invalid-data failures may require quarantine and intervention. |
| “We can change transform version while the job is running.” | Doing so risks mixing two formulas in one dataset; version/rebuild cleanly. |
| “Once COMPLETED, drop the old table right away.” | Consumers, rollback windows, retention, and cutover remain. |
| “Rollback just means flipping a feature flag.” | If the legacy path no longer receives new data, you need a data rollback plan. |
| “Just fill NULLs or missing values with defaults to keep all rows.” | That can distort historical truth; define UNKNOWN/N/A or quarantine instead. |

## 19. Checklist before marking complete

| Category | Verifiable condition |
| --- | --- |
| **Domain** | Grain, eligible source set, keys, and time policy confirmed |
| **Source** | Reliable snapshot/manifest or CDC checkpoint, immutable within run scope |
| **Transform** | Transform version, code/config, timezone, and reference snapshot recorded |
| **Target writes** | Proper PK/UNIQUE/FK/CHECK, idempotent insert/upsert |
| **Checkpoint** | Committed with the batch's writes; points to **scanned** keys, not only written keys |
| **Resume** | Tested crash before commit, after commit, and verified retry causes no drift |
| **Concurrency** | Worker ownership, lock/lease/fencing, and non-overlapping batch ranges |
| **Data errors** | Quarantine, handling rules, and documented reasons for excluded rows |
| **Record recon** | Zero missing/extra keys; critical fields equivalent |
| **Aggregate recon** | Matching counts and totals per tenant/day/partition |
| **Live source** | CDC/change stream caught up and freshness verified |
| **Performance** | Batch duration, app p95/p99, WAL, replica lag within thresholds |
| **Cutover** | Shadow reads, permissions, canary/feature flag, and rollback prepared |
| **Post-deploy** | Ongoing drift monitoring, retention, and legacy schema retirement criteria |

## 20. Key takeaways

**Safe historical data backfill** is a workflow that can be **paused, resumed, re-run, and proven correct**, not just an INSERT/UPDATE loop running until rows run out. Start from **data semantics and grain**, lock in a reliable snapshot or source boundary, establish keys and transformation versions, and then ingest via **keyset batches** with **atomically committed checkpoints** and idempotent target writes.

In the 9-order historical example, the job scanned three batches to produce **7 PLACED order facts** totaling **1,900,000 VND**. CANCELLED orders were not written to the fact table yet still advanced the checkpoint. When a job crashes, the committed checkpoint tells it what to re-run; when scanning finishes, **key- and value-level FULL OUTER JOIN** alongside tenant–day reconciliation catches missing, extra, or misvalued rows that aggregate counts/sums can hide.

For systems still taking writes, **MAX(id) is no substitute for a consistent snapshot and change capture**; updates, edits, deletes, and late-arriving data must be caught up before cutover. A reliable design follows the chain: **define source and target models → snapshot/version → checkpointed batches → idempotent replay → two-way reconciliation → catch-up → rollback-ready publish → monitor and retain evidence**. **Resumability** protects progress; **reconcilability** protects the meaning and correctness of the data.
