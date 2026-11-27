# Periodic Snapshots and Point-in-Time Data Queries

## 1. When a Question About the Past Cannot Be Answered from the Latest State

In the **DATABASE_DATA_MODELING** module, data design must begin with the business question before translating into entities, relationships, keys, constraints, indexes, and physical schemas. In the **Time and History** chapter, a common question is:

> “At 10:30 on June 10, how many units of product A remained in warehouse 1?”

Suppose the system stores only a single current-inventory row. By 17:00, the quantity has changed many times; reading the current row no longer reveals the quantity at 10:30. To look up the past, you can store **periodic snapshots** of state. Yet if snapshots are only taken at 00:00 and 12:00, the snapshots alone cannot tell what happened between those two checkpoints.

This lesson distinguishes three outcomes that are frequently conflated:

1. **Value at a snapshot point:** “What inventory did the 12:00 snapshot record?”
2. **Most recently observed value before time T:** “If we only have snapshots, what latest recorded value can I display at T?” This is typically **lagging data**, with no guarantee it reflects the true state at T.
3. **Exact value at a point in time or version:** “What inventory had the system confirmed at 10:30?” Answering accurately between snapshots requires a **complete change history** or an appropriate temporal version source to reconstruct state.

A snapshot is a **storage strategy for fast reads and lower reconstruction cost**. It does not automatically replace change history, audit logs, transaction logs, or a bitemporal model.

After this lesson, learners should be able to design snapshot schedules, define consistency boundaries, combine snapshots with incremental changes, write version-based or point-in-time queries, and validate limitations around precision, storage, retention, and database technology.

## 2. What Is a Data Snapshot?

A **snapshot** is a record or set of records representing **state captured at a consistent cutoff**. That cutoff may be defined by:

- **An entity version**, such as change sequence **state_version = 103** for product A's inventory in warehouse 1.
- **A position in an event stream or log**, such as an offset, sequence number, or commit position guaranteed by the source store.
- **A consistent database read**, such as a transaction reading an entire set of rows under a single MVCC snapshot.
- **A closed business milestone**, such as end-of-day closing balances after all transactions for the period have been posted.

Simply adding a **snapshot_at** column to a table does not produce a consistent snapshot. If a job scans rows over several minutes while data keeps changing, different rows can come from different source points in time. The result is merely **a table scan**, not necessarily a coherent “whole-system state at T.”

### 2.1. Three Timestamp Concepts That Must Be Kept Separate

| Field / Milestone | Question Answered | Can They Differ? |
|---|---|---|
| **source_cutoff** or **as_of_version** | Which source changes are included in this snapshot? | Yes; this is the true data boundary |
| **capture_started_at** | When did the capture job start? | Yes; before completion |
| **capture_finished_at** | When did persisting the snapshot finish? | Yes; after reading and writing data |

A label like **snapshot_day = 2026-06-10** describes the reporting period, not necessarily proving every row reflects 00:00 on that day. Specify whether it denotes a labeling date, business date, closing milestone, or source cutoff.

**Principle:** when a snapshot is *created* differs from the data point in time it *represents*. When these timestamps differ, historical queries must rely on the **source cutoff** rather than picking the latest snapshot by upload time.

### 2.2. Data Snapshots Differ from Database Backups

**Application snapshots** typically store readable attributes or aggregates, such as balances, stock on hand, loyalty points, workflow states, or daily active customers.

**Backups / PITR** exist to recover an entire database after failure; they can combine base backups with transaction logs to restore up to a point in time when DBMS configuration permits. A physical backup does not expose a business API like “order 42's price at T”; conversely, an inventory snapshot table does not replace backups.

**Audit logs** record who did what, where, and when. Some audit logs carry enough payload to reconstruct state, but many capture only action names or messages lacking full semantics; never assume every log is a complete change source.

## 3. Running Example: Inventory Changing Between Two Snapshots

Consider **warehouse_id = 1**, **sku_id = 100** on **2026-06-10**. Units are individual items. All timestamps below are **UTC**, changes are processed successfully, and they are ordered sequentially within this inventory item's stream.

| Time | Activity | Qty Change | Qty After Change | Version |
|---|---|---:|---:|---:|
| 00:00 | Start-of-day snapshot | — | **30** | 100 |
| 08:00 | Stock receipt | +5 | **35** | 101 |
| 10:00 | Stock issue | -4 | **31** | 102 |
| 11:00 | Damage write-off | -2 | **29** | 103 |
| 12:00 | Midday snapshot | — | **29** | 103 |
| 14:00 | Stock receipt | +6 | **35** | 104 |
| 16:00 | Stock issue | -3 | **32** | 105 |
| 00:00 on Jun 11 | End-of-period snapshot | — | **32** | 105 |

The start-of-day snapshot records **30, version 100**; the midday snapshot records **29, version 103**. When asked for inventory at **10:30**:

- **Snapshots only:** we know the closest prior snapshot recorded 30, yet **we cannot claim** actual inventory at 10:30 was 30.
- **With full change history:** after version 100 came **+5 at version 101** and **-4 at version 102**. Thus inventory at version 102 is **30 + 5 - 4 = 31**.
- **With the 12:00 snapshot when querying 10:30:** the 12:00 snapshot already includes the 11:00 change, so it cannot be used directly as the 10:30 state.

By the same calculation, at version 104 we start from snapshot version 103 and apply **+6** to get **35**. At version 105 we apply **-3** to get **32**.

### 3.1. Visualizing Snapshots and Intermediate Changes

~~~mermaid
flowchart LR
    S0["Snapshot V100<br/>00:00 = 30"] --> E1["+5<br/>V101"]
    E1 --> E2["-4<br/>V102"]
    E2 --> E3["-2<br/>V103"]
    E3 --> S1["Snapshot V103<br/>12:00 = 29"]
    S1 --> E4["+6<br/>V104"]
    E4 --> E5["-3<br/>V105"]
    E5 --> S2["Snapshot V105<br/>Jun 11 = 32"]
~~~

A snapshot at version 103 has already accumulated all changes up through version 103. When reconstructing from it, replay must begin **after version 103**, never re-applying event 103.

### 3.2. Two Precision Levels That Must Not Be Equated

**Version-based query:** “What is the state after applying all changes up through version 102?” — answered accurately whenever snapshots and change history are complete and ordered.

**Wall-clock query:** “What was the system state at 10:30:00 UTC?” — answered accurately only if the system has a reliable rule mapping **instant T** to **the set of changes effective/committed by T**.

An **event_at** column set by the application before transaction commit is not sufficient to guarantee committed state at T. Systems with strict audit requirements may need commit positions, transaction ordering, or database temporal features. If events can have retroactive validity, you must also separate business effective time from system recording time; a recording-ordered stream alone cannot automatically answer that.

## 4. Snapshot Types and Use Cases

| Type | Contents | Benefits | Limitations or Requirements |
|---|---|---|---|
| **Full snapshot** | Complete state set within a defined scope at one cutoff | Independent reads, straightforward reconciliation | High storage and I/O cost per capture |
| **Per-entity snapshot** | State of each order, account, or SKU every N changes | Short replay, fast single-entity loading | Does not guarantee global consistency if entities are captured at different times |
| **Incremental/delta snapshot** | Only data changed since a baseline checkpoint | Reduces write volume when few entities change | Needs intact baseline + delta chain; losing one delta breaks recovery |
| **Aggregate snapshot** | Period-closed totals: revenue, stock, balances | Fast reporting, avoids scanning detail sources | Cannot drill down into unretained details |
| **Snapshot + event log** | Baseline state plus ordered changes after baseline | Exact per-version reconstruction without replaying from genesis | Must preserve complete events, source boundaries, and deterministic replay |

A **full snapshot** is complete within a defined business scope, such as all SKUs in one warehouse—not necessarily the entire database. If a snapshot includes active products while excluding discontinued ones, document the inclusion criteria clearly so “not found” is not misread as zero inventory.

A **delta snapshot** also differs from an **event log**: a delta may simply state “column X changed from 10 to 12” or “row 42 updated,” whereas a business event states “received 2 units under receipt Y.” Each supports different replay, audit, and root-cause explanation capabilities.

## 5. Choosing a Snapshot Cadence from Query Needs and Change Frequency

No single “daily” cadence fits every domain. Ask:

- Do users need **end-of-day** state or state at **any arbitrary second**?
- What lag is acceptable? Can a dashboard show numbers from 15 minutes ago, or must it reflect the latest transaction?
- What are the average and peak change rates between snapshots?
- Does replaying one change consume significant CPU/I/O?
- How long must snapshots be retained; are there published-figure, period-close, or regulatory audit obligations?
- Is the snapshot scoped to one entity, one warehouse, one service, or multiple databases?
- Are there late-arriving changes, retroactive adjustments, or unconfirmed source states?

A simple estimate for a steady change stream:

~~~text
Max events to replay ≈
change rate (events / hour) × hours between two snapshots

Average events replayed ≈ half the max
if query instants are distributed evenly across the period.
~~~

For example, 2,000 changes/hour with 6-hour snapshots yields up to roughly 12,000 events to replay for a single stream without intermediate checkpoints. This is a volume estimate, not a latency promise; CPU also depends on per-event complexity and index layout.

Snapshot frequency also determines **information loss when only snapshots are kept**. Capturing every 5 minutes still cannot reconstruct an intermediate value between two snapshots unless intermediate changes are stored. Higher cadence shrinks unobservable windows, yet never turns sampled data into continuous history.

## 6. Relational Data Model: Current State, Events, and Snapshots

The PostgreSQL example below uses **sequential versions per (warehouse_id, sku_id) pair**. The version increments on each inventory update; snapshots record the included version. The goal is a durable change source capable of reconstructing **exact state at version N**.

### 6.1. Current-State Table

~~~sql
CREATE TABLE inventory_balance (
    warehouse_id bigint NOT NULL,
    sku_id       bigint NOT NULL,
    qty_on_hand  bigint NOT NULL CHECK (qty_on_hand >= 0),
    state_version bigint NOT NULL CHECK (state_version >= 0),
    PRIMARY KEY (warehouse_id, sku_id)
);
~~~

The composite key enforces **one current balance per SKU per warehouse**. If inventory is tracked by lot, expiration date, or owner, add those dimensions to the key or create a dedicated stock entity. Avoid merging non-fungible lots and hoping snapshots can recover lost granularity later.

**qty_on_hand** represents physical stock in this model. “Available to promise” may equal on-hand minus reserved or locked quantities; store or compute reservations and other components separately if that is the actual business question.

### 6.2. Entity-Ordered Change Table

~~~sql
CREATE TABLE inventory_movement (
    warehouse_id   bigint NOT NULL,
    sku_id         bigint NOT NULL,
    stream_version bigint NOT NULL CHECK (stream_version >= 1),
    qty_delta      bigint NOT NULL CHECK (qty_delta <> 0),
    operation_id   uuid NOT NULL UNIQUE,
    accepted_at    timestamptz NOT NULL,
    reason_code    text NOT NULL,
    PRIMARY KEY (warehouse_id, sku_id, stream_version)
);

CREATE INDEX ix_inventory_movement_time
    ON inventory_movement
       (warehouse_id, sku_id, accepted_at, stream_version);
~~~

**stream_version** establishes change application order for a SKU at a warehouse. **operation_id** identifies the business command and prevents duplication on retries. **accepted_at** aids time-based investigation, yet is not automatically exact commit time or retroactive business effective time.

To prevent state and change tables from drifting, all updates to a given SKU must execute inside **a single transaction**. When bootstrapping from a legacy system, define initial values and baseline versions explicitly; never assume every SKU starts at 0 unless verified by the source.

### 6.3. A Minimal Update Protocol

Suppose the application has validated an inbound/outbound stock movement with a unique **operation_id** for an existing SKU:

~~~sql
BEGIN;

UPDATE inventory_balance
SET qty_on_hand = qty_on_hand + :delta,
    state_version = state_version + 1
WHERE warehouse_id = :warehouse_id
  AND sku_id = :sku_id
  AND qty_on_hand + :delta >= 0
RETURNING state_version;

-- Application must confirm exactly 1 row was updated
-- and take the RETURNING version as stream_version.

INSERT INTO inventory_movement (
    warehouse_id, sku_id, stream_version,
    qty_delta, operation_id, accepted_at, reason_code
)
VALUES (
    :warehouse_id, :sku_id, :returned_version,
    :delta, :operation_id, clock_timestamp(), :reason_code
);

COMMIT;
~~~

The **:parameter** placeholders are application-bound parameters, not direct PostgreSQL SQL variable syntax in all runners. This snippet expresses the protocol rather than a complete stored procedure.

If INSERT fails due to a duplicate **operation_id** or version, the entire transaction—including the UPDATE—must roll back. Retries must look up the existing `operation_id` outcome and return the appropriate status rather than incrementing the version again. When two transactions update the same row, UPDATE row locking serializes version increments, though the service must still handle rollbacks and business checks.

If events can drive quantities negative or change multiple asset dimensions, reconsider the **qty_on_hand >= 0** constraint according to domain rules. Do not force a “non-negative” rule onto accounting ledgers or warehouses permitting planned backorders when invalid for that domain.

## 7. Schema for Storing Snapshots

There are two levels of information:

1. **Snapshot run:** metadata for a capture batch, completion status, start/finish times, and scope.
2. **Snapshot row:** each SKU's state at the exact **state_version** reflected by the source at capture time.

~~~sql
CREATE TABLE inventory_snapshot_run (
    run_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at  timestamptz,
    run_status   text NOT NULL
                 CHECK (run_status IN ('BUILDING', 'COMPLETE', 'FAILED')),
    row_count    bigint CHECK (row_count IS NULL OR row_count >= 0)
);

CREATE TABLE inventory_snapshot (
    run_id        bigint NOT NULL
                  REFERENCES inventory_snapshot_run(run_id),
    warehouse_id  bigint NOT NULL,
    sku_id        bigint NOT NULL,
    qty_on_hand   bigint NOT NULL,
    state_version bigint NOT NULL CHECK (state_version >= 0),
    PRIMARY KEY (run_id, warehouse_id, sku_id)
);

CREATE INDEX ix_snapshot_lookup_by_version
    ON inventory_snapshot
       (warehouse_id, sku_id, state_version DESC, run_id DESC);
~~~

**run_id** identifies a capture run; **state_version** is the boundary included by the snapshot **within each SKU's own stream**. Because each SKU has its own version sequence, never treat version 103 of SKU A and version 103 of SKU B as the same global instant.

**run_status = COMPLETE** is required before a snapshot may be used. If a capture fails or writes only a partial batch, the system must never treat it as a valid snapshot.

**row_count** verifies the captured row total within the defined scope. Production schemas should also include **scope**, snapshot format schema/version, checksum, source metadata, job ID, and confidence metadata. If soft-deleted entities are captured, define rules for deleted records so snapshots preserve existence semantics.

### 7.1. Creating a Consistent Snapshot Within One Database

One illustrative pattern captures all of **inventory_balance** inside a PostgreSQL **REPEATABLE READ** transaction:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

INSERT INTO inventory_snapshot_run (run_status)
VALUES ('BUILDING')
RETURNING run_id;

-- Application reads run_id above and passes it to the next INSERT.

INSERT INTO inventory_snapshot (
    run_id, warehouse_id, sku_id, qty_on_hand, state_version
)
SELECT
    :run_id, warehouse_id, sku_id, qty_on_hand, state_version
FROM inventory_balance;

UPDATE inventory_snapshot_run
SET run_status = 'COMPLETE',
    finished_at = clock_timestamp(),
    row_count = (
        SELECT COUNT(*)
        FROM inventory_snapshot
        WHERE run_id = :run_id
    )
WHERE run_id = :run_id;

COMMIT;
~~~

Under **REPEATABLE READ**, SELECT statements inside the transaction read the same consistent MVCC snapshot of the source data. Hence rows written from **inventory_balance** reflect a coherent cut within that database and transaction, provided all write paths update **inventory_balance** and **inventory_movement** atomically.

Notes:

- **started_at** and **finished_at** reflect job execution time, **not automatically the exact source commit timestamp of the snapshot**.
- Across multiple databases or independent services, a single PostgreSQL transaction cannot create a system-wide consistent cut. You need coordinated snapshots/watermarks or an explicitly bounded eventual-consistency model.
- Structure runs and snapshot rows so readers see only committed **COMPLETE** snapshots. With the transaction above, success or failure is atomic.
- Capturing full state in one long transaction can consume significant resources and hold MVCC snapshots open; measure operational impact. If switching to chunked batch snapshots, redesign consistency boundaries and completion criteria.

### 7.2. Per-Entity Snapshots Carry Different Guarantees

If each SKU is snapshotted independently every 100 versions, each snapshot states only **“this SKU at version 100.”** That works well for accelerating single-SKU lookups.

If a report asks for **“total stock across all SKUs at exact time T,”** stitching together SKU A's snapshot at 09:00 and SKU B's snapshot at 09:07 will not produce a consistent warehouse-wide state at T. You need a scope-wide consistent capture or a well-defined global checkpoint/watermark.

## 8. Reconstructing State at a Version Using Snapshot + Events

Suppose an API needs the inventory balance after **target_version = 102** for warehouse 1, SKU 100. We must:

1. Select the **COMPLETE** snapshot with the highest version **not exceeding 102**.
2. Read movements with version **strictly greater than the snapshot's version** and **less than or equal to 102**.
3. Apply each change in exact order, once.
4. Return the final value along with baseline snapshot and target version metadata.

Illustrative SQL summing **qty_delta**:

~~~sql
WITH selected_snapshot AS (
    SELECT
        s.run_id,
        s.qty_on_hand AS base_qty,
        s.state_version AS base_version
    FROM inventory_snapshot s
    JOIN inventory_snapshot_run r
      ON r.run_id = s.run_id
    WHERE r.run_status = 'COMPLETE'
      AND s.warehouse_id = 1
      AND s.sku_id = 100
      AND s.state_version <= 102
    ORDER BY s.state_version DESC, s.run_id DESC
    LIMIT 1
)
SELECT
    s.run_id,
    s.base_version,
    102 AS target_version,
    s.base_qty + COALESCE(SUM(m.qty_delta), 0) AS qty_as_of_version
FROM selected_snapshot s
LEFT JOIN inventory_movement m
  ON m.warehouse_id = 1
 AND m.sku_id = 100
 AND m.stream_version > s.base_version
 AND m.stream_version <= 102
GROUP BY s.run_id, s.base_version, s.base_qty;
~~~

Using the section 3 example, baseline version 100 has **30**, and replaying movements 101 (+5) and 102 (-4) yields **31**.

**Boundary conditions are critical:** the movement at **base_version** is already included in the snapshot, so filter **stream_version > base_version** to avoid double-counting. The movement at target_version must be included, so use **<= target_version**.

**If no sufficiently early snapshot exists**, the CTE returns zero rows and the query returns zero rows. The application must report missing baseline history or fall back to a **verified** replay from genesis rather than silently returning 0.

### 8.1. Versions Are Logical Cutoffs; Wall-Clock Time Is a Separate Problem

To find **target_version for instant T**, the data source must provide a trustworthy mapping:

~~~text
T = 10:30 UTC
Changes effective under query semantics up to T:
V101 (+5), V102 (-4)
=> target_version = 102
~~~

If only **accepted_at** captured before commit exists, filtering `accepted_at <= T` reflects **processing time** rather than exact transactions committed and visible at T. A transaction stamped `accepted_at` at 10:29 that commits at 10:31 was not yet committed state at 10:30.

To guarantee “what had the system committed at T?”, define proper commit/ordering tracking at the source layer. For “data **effective in business** at T,” use valid time and handle retroactive changes; a recording-ordered stream alone cannot automatically answer that.

### 8.2. Is It Safe to Walk Backward from a Snapshot After T?

When data consists strictly of invertible deltas, arithmetic lets you take a snapshot after T and subtract post-T changes. However, this is valid only when **every transformation is invertible, history is complete, and ordering is guaranteed**. For workflow states, non-additive rules, or external side effects, backward replay is unreliable.

Default design should select **a snapshot at or before the target cutoff** and replay forward. This keeps semantics clear, simplifies replay logic, and makes missing events easier to detect.

## 9. What Can You Query If You Have Only Periodic Snapshots?

Suppose movements are not stored—only the 00:00 snapshot = 30 and 12:00 snapshot = 29 remain.

| Question | Can It Be Answered With Certainty? | Explanation |
|---|---|---|
| What did the 00:00 snapshot record? | Yes: 30 | Captured at a verified source cutoff |
| What did the 12:00 snapshot record? | Yes: 29 | Captured at a verified source cutoff |
| What was actual stock at 10:30? | **No** | Receipts or issues may have occurred between snapshots |
| What was the latest observed reading before 10:30? | Yes, if source cutoff is known | Latest observed value is 30, with lag |
| Through what steps did stock rise and fall? | **No** | Summary snapshots omit intermediate steps |
| Can 10:30 stock be deduced from endpoints 30 and 29? | **No** | Many different event sequences share the same endpoints |
| How much stock exists after the last snapshot up to now? | Only if post-snapshot data is captured | Old snapshots know nothing of subsequent changes |

A snapshot-only API should use clear names: **latest_snapshot_before**, **sampled_value**, **last_observed_at**, **data_freshness**. Never name the output **exact_balance_at(T)** without a mechanism to reconstruct state at T.

### 9.1. Do Not Interpolate Discrete State

Averaging 30 and 29 to report 29.5 at 06:00 is meaningless for discrete item counts, order statuses, or access permissions. Interpolation suits only certain continuous physical quantities under validated statistical models, never general business state history.

If the requirement is merely **trend reporting**, hourly/daily sampled snapshots may suffice. If every transaction must be reconciled, detailed business movements must be stored.

## 10. Consistency of a Single Capture Matters More Than Its Timestamp Label

A multi-table snapshot can suffer **time skew** if source data keeps changing while the capture job reads.

Suppose the system transfers 100 units from warehouse A to warehouse B in one transaction:

- Before transaction: A = 500, B = 300, total = 800.
- After transaction: A = 400, B = 400, total = 800.

If the snapshot job reads A **before** the transaction and B **after** the transaction, it captures A = 500 and B = 400 (total = 900)—a total that never existed in any consistent state of the system.

### 10.1. Approach for a Single Transactional Database

For tables within **one database** with proper transactions and MVCC, read inside a single consistent transaction (such as `REPEATABLE READ` in PostgreSQL). All scanned rows reflect the same source MVCC snapshot.

If a job reads pages across separate transactions, **each page can reflect a different cutoff**. Merely ensuring “every SELECT reads committed data” (`READ COMMITTED`) does not guarantee the entire capture represents one consistent state.

### 10.2. Approach for Multi-Service Systems

When state spans multiple microservices or databases, choose an explicit data contract:

- Accept **eventual consistency** and expose each source's watermark/lag.
- Coordinate a **snapshot barrier**: sources pause or mark changes reaching a shared logical cut.
- Consume an offset/checkpointed event stream to materialize a consistent projection under defined ordering rules.
- Capture each source independently and **reconcile** cross-source invariants, acknowledging timing differences in reports.

Stamping multiple files with a **shared wall-clock timestamp** does not create causal synchronization across services. If global atomic capture is impossible, report consistency at the **provable** guarantee level rather than overstating precision.

## 11. Late-Arriving Data, Retroactive Edits, and Published Snapshots

Suppose on June 12 warehouse ops receives an adjustment stating spoilage **occurred on June 10**. Two distinct questions arise:

- “According to current knowledge, what was the business-effective inventory at 11:30 on June 10?”
- “At 11:30 on June 10, what inventory had the system **recorded** at that time?”

If the June 10 12:00 snapshot was taken **before the system knew** about the spoilage, retroactive edits make business-correct figures differ from the captured and published snapshot.

### 11.1. Never Silently Rewrite Closed Snapshots

An inventory report already sent to finance may need to preserve the **published snapshot** even after data is later amended. Common options:

- Keep the old snapshot immutable and create a new **amended snapshot version** linked to the prior one.
- Store **decision_ref**, reason, and amendment timestamp; mark which version is currently latest.
- Issue a restated report if business rules require it, without mutating closed reports untraced.
- When needing to answer **“what did the system know back then?”**, model known/system time or maintain an event log sufficient to reconstruct knowledge history.

A table with **snapshot_at** and **updated_at** does not automatically become bitemporal. To answer both temporal questions, design explicit support for both effective values at **B** and system knowledge at **K**.

### 11.2. Two Strategies for Late-Arriving Events

**Strategy A — post an adjustment entry at acceptance time:** keep the recorded movement ledger intact and append a compensating movement with a reason. This suits accounting and warehouse systems that audit recorded movements.

**Strategy B — recompute business valid-time history:** insert late data into the valid-time timeline, recompute affected segments, and publish revised snapshots/projections. Preserve prior knowledge slices whenever investigations ask “what did the system previously believe?”

Never pick a strategy solely for coding convenience. Downstream consequences for invoices, ledgers, refunds, and statutory reports must be governed by business rules.

## 12. Verifying Event Completeness After Each Snapshot

Snapshot + events reconstruct state accurately only when events have **no gaps, no duplicate effects, and clear application order**.

For a SKU with snapshot version 100 and target_version 103, movements must include **101, 102, 103**. If 101 and 103 exist while 102 was lost, summing deltas yields a plausible-looking yet wrong number.

### 12.1. Data Invariants to Verify

| Invariant | Meaning |
|---|---|
| **Unique `stream_version` per entity** | Never apply two movements at the same version |
| **Each `operation_id` processed at most once** | Retries never duplicate changes |
| **Contiguous version range for replay** | Can recover cleanly from baseline snapshot |
| **Snapshot version includes all events up to that version** | No omissions or double-counting during replay |
| **Only COMPLETE snapshots are used** | Never read partially written captures |
| **Snapshot and movements share quantity semantics** | Never mix deltas from different units or rules |
| **Replay schema versions are compatible** | Old events still interpret accurately after upgrades |
| **Authoritative change source is defined** | Never mix duplicate CDC, test events, and real ledger entries |

A primary key prevents **duplicate versions**, but does not prevent **missing versions**. During recovery, check contiguity or verify movement counts and checkpoints. Depending on architecture, use per-entity sequences, cumulative checksums, or ordered emission from the authoritative source.

### 12.2. Idempotency During Replay and Business Application

If movements are **deltas**:

~~~text
+5, -4, -2
~~~

applying +5 twice corrupts the result. Thus every event must be applied **effectively once**, even over at-least-once messaging transport.

If events carry **absolute values** (“set quantity = 35”), replay still requires ordering and idempotency; applying 35 after 31 can regress state. Different payload styles dictate different replay logic.

### 12.3. Replay Must Be Deterministic

An old event must yield the same outcome when replayed months later. Avoid replay logic depending on:

- **Current** price tables instead of prices effective when the event closed.
- **now()** or live external API calls at replay time.
- New business configuration without versioned rules/schemas.
- Unstable message arrival order.

When rules evolve, version events, snapshots, or legacy event translators (*upcasters*), and validate replay outputs against finalized historical records.

## 13. Indexes, Partitioning, and Storage Cost

Design for two distinct query families:

- **Fetch the latest snapshot at or before an entity's version**, indexed by entity key and descending version.
- **Fetch all movements across a version span**, using the ordered primary key `(warehouse_id, sku_id, stream_version)`.

The examples in sections 6–7 created both keys. When reports scan many SKUs within one run, primary key `(run_id, warehouse_id, sku_id)` accelerates per-run scans. For wall-clock lookups, an index on `accepted_at` can help while honoring that column's actual semantics rather than mistaking it for commit time.

### 13.1. Estimating Storage Capacity

For full snapshots:

~~~text
Approximate capacity =
captured entities
× size of one state record
× number of retained snapshots
+ indexes, replicas, and metadata
~~~

Suppose there are **5 million warehouse-SKUs**, averaging **100 useful bytes** per state record, captured hourly. Theoretical payload per snapshot is roughly **500 MB** before indexes, row overhead, compression, WAL, replication, and backups. Over 30 days, 720 runs produce around **360 GB of raw payload** before overhead. Treat this as rough sizing only; benchmark on your target engine.

Common optimizations: capture low-churn streams less frequently; trigger per-entity snapshots every N events; use incremental snapshots off baselines; compress cold data; archive older snapshots; or keep only closed aggregates when detail is unnecessary.

### 13.2. Partitioning and Retention

Partitioning by **run_id**, capture time, or organizational scope simplifies period queries and drops, provided indexes, keys, and DBMS partitioning behavior are verified.

Retention policies must coordinate **both snapshots and events**. Deleting events 101–103 while keeping only snapshots at versions 100 and 105 makes version 102 impossible to reconstruct accurately. A sound policy retains a **baseline snapshot no later than the earliest supported PIT horizon**, plus contiguous events from that baseline through all queryable versions.

Dropping old snapshots alone is acceptable if genesis events remain and replay cost is tolerable. Dropping events is acceptable if requirements need only confirmed snapshot milestones. Never advertise arbitrary point-in-time queries once retention has trimmed the required chain.

## 14. Operational Snapshots vs. Analytical Snapshots

In **OLTP** systems, snapshots typically accelerate reads or state recovery for an order, account, or SKU. Data must preserve transactional invariants and version-level querying.

In **OLAP** systems, a snapshot often takes the form of a daily/monthly **fact_snapshot** table, such as:

~~~text
inventory_daily_snapshot
  business_date
  warehouse_id
  sku_id
  closing_qty
  snapshot_revision
  source_cutoff
  published_at
~~~

The business key is not simply **business_date + warehouse_id + sku_id** if **multiple restatements** are permitted for the same date. With revisions, distinguish the originally published release from subsequent restated versions.

### 14.1. Snapshot Facts Differ from Transaction Facts

| Analytical Fact Type | Grain | Best-Suited Question |
|---|---|---|
| **Transaction fact** | One movement / order / event | “Which transactions occurred during the period?” |
| **Periodic snapshot fact** | One entity or dimension slice per period | “What was inventory at the end of each day?” |
| **Accumulating snapshot fact** | One process row updated with milestone timestamps | “How long did orders take from placement to delivery?” |

A **periodic snapshot fact** powers end-of-day stock charts cleanly, yet hides intraday receipts and issues. An **accumulating snapshot** updates as a workflow progresses and requires separate history capture if prior milestone states must be reconstructed.

### 14.2. Combining with Versioned Dimensions

If a SKU belongs to Category A at the start of the month and moves to Category B mid-month, reporting “end-of-day inventory by category effective on that day” requires a **temporal join** against category history.

Suppose the June 10 snapshot contains SKU 100, and the category dimension is versioned by **[valid_from, valid_to)**. Reports must join the dimension row containing the fact's **business_date** or use the captured version surrogate key. Joining to current categories rewrites historical groupings and distorts period-over-period comparisons.

If a dimension is amended retroactively, decide whether reports must **restate using new information** or **preserve published figures**. Analytical snapshots and dimension knowledge history are related concerns, not substitutes for one another.

## 15. Applying the Concepts in Document and Graph Databases

### 15.1. Document Databases

Each inventory balance or product snapshot can be stored as a document:

~~~json
{
  "entityType": "inventory-balance",
  "warehouseId": 1,
  "skuId": 100,
  "snapshotVersion": 103,
  "qtyOnHand": 29,
  "captureRunId": "run-2026-06-10-noon",
  "schemaVersion": 1
}
~~~

To retrieve state at version 104, select the document with the highest **snapshotVersion <= 104** and replay subsequent movements. Updates and event writes must maintain consistent ordering and semantics.

Embedding the entire snapshot history inside **one current document** risks unbounded document growth and high write cost. A separate snapshot collection is usually easier to partition, index, and expire via retention.

### 15.2. Graph Databases

In an organizational graph, a snapshot can capture nodes and edges at a period cutoff. However, if the goal is answering **“on March 15, which department did employee 42 belong to and who managed that department?”**, ensure **MEMBER_OF and MANAGED_BY relationships** are evaluated at the same instant.

Capturing nodes on Monday and edges on Wednesday does not produce a consistent Tuesday historical graph. Store effective intervals on edges and build as-of subgraphs, or capture the full graph at a consistent cut when scale allows.

In bitemporal graphs, you need both relationships effective at **B** and what the system knew at **K**. Periodic graph snapshots do not automatically yield bitemporality unless prior knowledge states are retained.

## 16. Validation with Query Matrices and Common Pitfalls

### 16.1. Result Matrix on the Inventory Example

| Request | Source Used | Expected Result |
|---|---|---|
| After version 100 | Start-of-day snapshot | 30 |
| After version 101 | Snapshot V100 + event 101 | 35 |
| After version 102 | Snapshot V100 + events 101–102 | 31 |
| After version 103 | Midday snapshot V103 or replay from V100 | 29 |
| After version 104 | Snapshot V103 + event 104 | 35 |
| After version 105 | Snapshot V103 + events 104–105 | 32 |
| Query 10:30 with only 00:00 and 12:00 snapshots | Insufficient movement history | Cannot determine accurately |
| Query 10:30 with trusted time mapping to version 102 | Snapshot + events 101–102 | 31 |
| Query version 99 with no prior snapshot or genesis log | Missing baseline data | Report insufficient history |

Distinguish **a query returning 0** from **a query having no answer**. If baseline snapshots are missing, never default inventory to 0. If a SKU truly did not exist yet at that time, creation metadata or initialization rules must prove it.

### 16.2. Operational Test Cases

1. **Off-by-one:** snapshot version 103 must never replay movement 103 again.
2. **Missing event:** movements 101 and 103 exist while 102 is missing; system detects the gap and refuses to claim an exact answer.
3. **Retry:** duplicate `operation_id` is recognized and never adds `qty_delta` again.
4. **Incomplete snapshot:** a run in `BUILDING` status is ignored even if some snapshot rows already exist.
5. **Mid-run failure:** partially written capture rows never appear as `COMPLETE`.
6. **Version bump and event write:** if any part of INSERT fails, both balance update and event insert roll back.
7. **Concurrent writes:** two movements for the same SKU receive distinct ordered versions with zero lost updates.
8. **Multi-SKU consistency:** a warehouse-wide snapshot never produces impossible totals by reading rows from mixed source states.
9. **Pre-commit timestamp:** an event stamped 10:29 that commits at 10:31 must not be claimed as committed state at 10:30.
10. **Late-arriving events:** clearly classify whether they are recording-time adjustments or retroactive valid-time edits.
11. **Schema migration:** legacy events replay cleanly under rules compatible with earlier schema/versions.
12. **Retention:** purging snapshots/logs never breaks queries inside the committed retention window.
13. **Reconciliation:** replaying up to the current version must equal current `inventory_balance`; any drift triggers an alert.
14. **Time zones:** end-of-day market snapshots follow business time zones rather than implicitly slicing by UTC day.

### 16.3. Mistakes to Avoid

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Picking latest snapshot before T and calling it exact state at T | Changes may have occurred after the snapshot | Label as sampled data or replay complete logs |
| Using a snapshot after T to answer T | Already includes events future relative to T | Choose cutoff at or before target; replay forward |
| Assuming `snapshot_at` alone is enough | Fails to prove source cutoff or capture lag | Store version/watermark and scope metadata |
| Paged snapshot under `READ COMMITTED` treated as one instant | Each page may see a different committed state | Single MVCC snapshot or coordinated barrier |
| Keeping only delta events with no baseline | Unknown starting quantity breaks replay | Verified baseline snapshot or complete genesis events |
| Snapshots and events out of sync across transactions | Snapshot may reflect changes missing from the log | Update state and movements atomically |
| Deleting logs right after the latest snapshot | Destroys ability to query versions between older snapshots | Base retention on committed PIT window |
| Treating `accepted_at` as guaranteed commit time | Timestamp captured before commit can misreport T | Use source commit ordering or explicit semantic bounds |
| Editing closed snapshots without revisions | Destroys proof of published numbers | Snapshot revisions, adjustment sources, restatement reports |

## 17. Practice Exercise: Computing Order State via Snapshots and Events

An order processing system has the sequence:

~~~text
Version 1: CREATED
Version 2: PAID
Version 3: PICKING
Version 4: PACKED
Version 5: SHIPPED
Version 6: DELIVERED
~~~

After version 3, the system captures a state snapshot **PICKING**, tagged **order_id = 42, snapshot_version = 3**. A subsequent snapshot is created after version 6.

Business requirement:

> “Customer support must look up what status an order held after each processing step. Looking up version 5 must be fast even if an order has thousands of auxiliary events.”

Solve step by step:

1. **Define the source of truth:** ordered business events with payloads sufficient to build order status; separate state-transition events from audit or auxiliary noise events.
2. **Define the snapshot:** store `order_id`, `snapshot_version`, materialized state, `schema_version`, and capture milestone; never assume snapshot version 6 can answer version 5.
3. **Query version 5:** select snapshot version 3 and replay events 4 and 5. Result must be **SHIPPED**.
4. **Verify completeness:** if event 4 is missing, never skip straight to version 5 unless event 5 carries an absolute state guaranteed by source rules.
5. **Design capture cadence:** e.g., every 100 changes or at key workflow milestones; explain the trade-off between replay length and storage.
6. **Set concurrency rules:** update state and append events in one transaction with monotonically increasing per-order versions; use `operation_id` on retries to avoid duplicate transitions.
7. **Handle wall-clock questions:** if a customer asks “where was the order at 10:15?”, identify which timestamps are stored and whether enough evidence exists to map time to version.
8. **Handle retroactive updates:** if a carrier delivers a milestone late, separate “when did it actually happen?” from “when did the system record it?”; decide whether valid/known time modeling is needed.
9. **Test retention:** if snapshot version 3 and events 1–3 are deleted, can version 5 still be answered from another baseline?

**Passing criteria:** identify the data source, baseline version, replay event range, timestamp query limits, and expected state at each version. Never pick the “most recently written snapshot file” when the actual target is a business-stream version.

## 18. Checklist Before Adopting Periodic Snapshots

Before approving the design, answer clearly:

- **Business question:** do users need captured milestone figures, latest observed figures, or exact state at T?
- **Cutoff:** which version, offset, or MVCC snapshot does a capture represent; how do `started_at` and `finished_at` differ from `source_cutoff`?
- **Scope:** which entity types are included, and are deleted or inactive entities excluded?
- **Capture mechanism:** single consistent transaction or multi-source watermarks; can global invariants be guaranteed?
- **Change source:** are events/CDC complete, ordered, idempotent, and sufficient for replay?
- **Query logic:** does lookup pick a baseline at or before `target_version`, apply bounds **(base_version, target_version]**, and detect missing logs?
- **Time axes:** are event time, valid time, accepted time, and commit time separated per actual requirements?
- **Frequency:** what snapshot interval balances read latency, replay length, and storage cost?
- **Closed figures and retroactivity:** do published snapshots have revisions; do retroactive changes leave audit trails and proper compensating workflows?
- **Constraints and operations:** are entity locking, transactions, run status, checksums, monitoring, rollbacks, and retries covered?
- **Retention:** does retention for both snapshots and events still cover every committed historical horizon?
- **Evolution:** across schema changes, relational-to-document/graph shifts, or analytical exports, do version/T query answers preserve their meaning?

**Core principle:** a periodic snapshot captures **state at a defined cutoff**. It speeds up reads and shrinks reconstruction steps, yet a series of discrete snapshots cannot by itself explain what happened between checkpoints. To query historical state accurately, pair snapshots with a complete, reliably ordered change history—or use an equivalent temporal model. A design is complete only when **source of truth, cutoff, precision, and query boundaries** are explicit and verifiable.
