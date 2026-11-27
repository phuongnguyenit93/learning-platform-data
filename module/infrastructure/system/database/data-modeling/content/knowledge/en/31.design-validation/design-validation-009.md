# Schema Migration Testing, Reconciliation, and Recoverability

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, the quality of a design does not lie solely in a clean ERD, proper normalization, or a `CREATE TABLE` statement that executes without errors. When a system is live, a schema change can **break compatibility across application versions, corrupt historical data transformations, duplicate events, or destroy recovery paths**. Therefore, design validation must span across **schema, data, applications, integrations, and operations**.

This lesson in the **Design Validation** chapter focuses on three core capabilities:

1. **Schema migration testing:** can the new structure be deployed while old and new applications run concurrently, do constraints remain valid, and is the impact on transactions within acceptable bounds?
2. **Reconciliation:** do individual entities, values, metrics, and datasets in the new model preserve the exact meaning from the source?
3. **Recoverability:** if a deployment, backfill, or storage system fails, can we resume, switch read/write paths back, rebuild data, or recover to a verified point in time?

After this lesson, you will be able to build a **validation plan with pass/fail criteria**, write SQL to check keys and data discrepancies, design idempotent backfills, test intentional failure scenarios in a safe environment, define RPO/RTO, and make evidence-based **go / no-go** decisions.

## 1. "Migration Ran Successfully" Does Not Mean "Design Is Validated"

Suppose the Orders system migrates from `amount_cents INTEGER` to `amount_minor BIGINT`. The migration might return exit code 0 after running:

~~~sql
ALTER TABLE orders ADD COLUMN amount_minor BIGINT;
~~~

Yet critical questions remain:

- Have all **existing** orders been completely migrated to the new column?
- Do **old writers** still writing `amount_cents` also update `amount_minor`?
- Do all **new readers** avoid reading un-backfilled or stale values?
- Do Java applications, ETL, CDC, APIs/events, and dashboards understand the **new data type and currency unit**?
- If the backfill dies after 30% of the data, will re-running it **duplicate rows or overwrite newer updates**?
- If the DB or a node holding locks fails, do source transactions remain consistent?
- If the old column is dropped and a bug is discovered, will simply redeploying the old binary still work?
- Has **recovery been rehearsed** from backups/transaction logs and has the actual duration been measured?

Therefore, a schema change is only considered complete when **both structure and data have been verified**, consumers have been migrated, and the recovery strategy has been evaluated proportionally to the risk.

> **Migration validation means verifying business invariants while old and new models may coexist—not merely confirming that SQL throws no errors.**

## 2. Identify What to Validate Before Writing Tests

A good test must answer precisely **what it is protecting**.

| Aspect | Invariant to Protect | Example Evidence |
|---|---|---|
| **Grain and keys** | One row represents exactly one business unit | `UNIQUE(tenant_id,order_id)` and duplicate-check query |
| **Values** | Old → new mapping preserves exact meaning | `amount_minor = amount_cents::BIGINT` in the same unit |
| **Relationships** | No cross-tenant references or orphaned FKs | Anti-join and FK validation |
| **Completeness** | No lost records due to filtering, paging, or late arrival | Key counts and key-set comparison |
| **Applications** | Every running version understands the active schema | Compatibility matrix + integration tests |
| **Consistency** | Concurrent writers do not leave two representations out of sync | Concurrency test, row-level mismatch |
| **Latency and load** | DDL/backfill stays within operational limits | Lock wait, WAL, replication lag, latency |
| **Recovery** | Can recover within target RPO/RTO | Restore drill and measured evidence |
| **Integrations** | Events/APIs/CDC do not change meaning unintentionally | Contract tests, dedupe/replay |
| **Security** | Migration does not widen permissions or expose data copies | Tenant checks, masking, retention |

**A single invariant may require multiple checks.** Matching `COUNT(*)` does not prove row-by-row accuracy; matching total amount does not prove two invoices were not swapped; a technical `PRIMARY KEY` does not prove a source event was ingested only once.

### 2.1. Start from the Grain, Not from the ALTER Statement

Source example:

~~~text
orders:
    One row = one current order
    Business key = (tenant_id, order_id)
    Amount = amount_cents in USD cents
    Business owner = Orders domain
~~~

If the target model changes to **one order line item** or **one payment event**, reconciling `COUNT(*)` between the two tables is **no longer an appropriate check**. You must first describe the relationship between the two grains, then choose the appropriate aggregations and checks.

### 2.2. Do Not Treat Sample Data as Complete Proof

A set of 10 orders with all positive amounts, a single tenant, and no concurrent updates only tests the happy path. You must also include:

- Orders without new data yet, null data, and late-arriving data.
- Multiple tenants using identical display order numbers.
- Zero values, values near the `INTEGER` limit, and values exceeding the `INTEGER` limit after contract.
- Replayed events, multiple workers running concurrently, and rolled-back transactions.
- Lock contention, timeouts, lost connections, and jobs stopping mid-batch.
- Historical data across multiple partitions, closed periods, and infrequently run consumers.

**Test data must include counterexamples**, not just records that make the migration look right.

## 3. A Test Plan Tied to Expand–Migrate–Contract

The **expand → migrate → contract** strategy breaks risk down into checkpoints.

~~~mermaid
flowchart TD
    B["Baseline: source and consumers"] --> E["EXPAND: add structures"]
    E --> C1{"Schema + old app compatible?"}
    C1 -->|No| S["Stop / remediate / keep old system"]
    C1 -->|Yes| M["MIGRATE: sync, backfill, shadow read"]
    M --> C2{"Zero data loss, mismatch = 0?"}
    C2 -->|No| F["Pause, fix, and rerun"]
    F --> M
    C2 -->|Yes| R["Canary / cutover readers and writers"]
    R --> C3{"Consumers and SLOs all pass?"}
    C3 -->|No| M
    C3 -->|Yes| D["CONTRACT: drop old structures"]
    D --> V["Validate + recovery drill + monitor"]
~~~

| Phase | Validation Target | Phase Transition Gate |
|---|---|---|
| **Baseline** | Source data, keys, data quality, consumers, SLAs | Baseline metrics captured and semantics to preserve are understood |
| **Expand** | Additive DDL, locks, permissions, old app still running | New structures do not break old writers/readers |
| **Sync** | New writes, old writes, transaction rollback, concurrency | No old–new data drift is introduced |
| **Backfill** | Batch/retry/idempotency, progress, and source | No missing/wrong rows outside approved exceptions |
| **Read cutover** | Shadow read, canary, compatibility, latency | Zero discrepancies, SLOs met |
| **Write cutover** | All writers switched, new type/range | No remaining writers require the old structure |
| **Contract** | No old consumers left, new constraints, backup/recovery | Drop approved; point of no return understood |
| **Post-deploy** | Continuous reconciliation, replay, restore drill | No silent drift after cutover |

**Do not defer all testing to the end of the migration.** If you do not verify sync before backfill, data can start drifting while old writers continue updating. If you do not test recovery before contract, you might discover backups are unusable only after dropping the old column.

## 4. Application and Schema Compatibility Matrix

Assumptions:

- **S0:** only `amount_cents` exists.
- **S1:** both `amount_cents` and `amount_minor` exist, with a synchronization mechanism maintained.
- **S2:** only `amount_minor` remains.

Applications:

- **A0:** old code that only knows `amount_cents`.
- **A1:** transitional code that knows both columns.
- **A2:** new code that only knows `amount_minor`.

| App / Schema | S0 | S1 | S2 |
|---|---|---|---|
| **A0** | Valid | Valid **if the bridge preserves the old contract** | **Invalid** |
| **A1** | Only if it does not reference non-existent columns | Valid if sync/backfill is correct | Depends on whether A1 still uses the old column |
| **A2** | Invalid | Can read new column once data is complete; writes depend on strategy | Valid |

**Trap:** `COALESCE(amount_minor,amount_cents)` still causes a **syntax error on S0** because the new column does not exist yet. Therefore, **apply the schema change before deploying code that references the new schema**, unless the application has a tested capability-detection mechanism or separate SQL path.

### Consumers That Are Easily Overlooked

- API servers undergoing a rolling deploy.
- Java background workers, cron/batch jobs, and admin applications.
- Long-lived mobile/desktop clients, if they depend on a public contract.
- Stored procedures, views, triggers, reporting queries, and the BI semantic layer.
- CDC connectors, schema registries, message producers/consumers, and data lakes.
- Weekly/monthly/quarterly scheduled jobs.
- Backup, restore, data export, and recovery verification procedures.

The migration document must record the **owner, migration verification method, and evidence** for each group; "the main application is deployed" is not sufficient authorization to drop old structures.

## 5. Running Example: Old Amount Column and New Amount Column

We use **PostgreSQL** to build a concrete test suite. These SQL commands are training examples—they must be tested in an isolated environment and adapted to your actual DBMS version, data, and lock behavior; **never run them arbitrarily on production**.

### 5.1. Semantics and Scope Boundaries

~~~text
Source table: orders
Grain: one current row per (tenant_id, order_id)
Old column: amount_cents INTEGER NOT NULL
New column: amount_minor BIGINT
Example currency: USD; both measure in cents
Mapping: amount_minor = amount_cents::BIGINT
Valid values: >= 0 per example business rule
~~~

**This is a column rename and representation domain change, not a unit change.** In a multi-currency system, a *minor unit* may not be cents for every currency; do not use the example cast to solve currency conversion on its own.

Assumed table:

~~~sql
CREATE TABLE orders (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'USD'),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

The **key** used in reconciliation is `(tenant_id,order_id)`, not `order_id` alone if IDs are only unique within a tenant. `updated_at` tracks source state changes, **not necessarily** the business event time.

### 5.2. Expand Schema

~~~sql
ALTER TABLE orders
    ADD COLUMN amount_minor BIGINT;
~~~

Initially the new column is **nullable** so the old app can continue operating and un-backfilled historical data can validly coexist. You should verify actual lock behavior and speed. Adding a nullable column without a default is usually lightweight on modern PostgreSQL, but **that does not mean it acquires no locks**.

### 5.3. Bridge to Sync Old Writers with the New Column

In S1, the old app still writes `amount_cents`. A simple bridge pattern within the **same DB transaction**:

~~~sql
CREATE OR REPLACE FUNCTION sync_order_amount_from_legacy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.amount_minor := NEW.amount_cents::BIGINT;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_orders_amount_legacy
BEFORE INSERT OR UPDATE OF amount_cents ON orders
FOR EACH ROW
EXECUTE FUNCTION sync_order_amount_from_legacy();
~~~

This is a bridge **from the old column to the new column**, not two sources of truth. When A0 continues to `INSERT` or update `amount_cents`, the trigger populates `amount_minor` within the **same transaction**.

In S1, **new writers must still write compatibly with the old column**: for example, writing `amount_cents` (and optionally writing `amount_minor` with the same value) until all old readers/writers have left the system. A writer that only updates `amount_minor` while the old column is still required and read **is not a valid write path**.

Add a guard to block states where the two columns differ for **rows written after the guard is created**:

~~~sql
ALTER TABLE orders
    ADD CONSTRAINT orders_amount_mapping_consistent
    CHECK (
        amount_minor IS NULL
        OR amount_minor = amount_cents::BIGINT
    ) NOT VALID;
~~~

`NOT VALID` in PostgreSQL allows skipping the validation scan over historical rows when adding the constraint, while **subsequent inserts/updates must still satisfy the CHECK**. The trigger ensures the legacy write path satisfies the condition. The guard **does not replace testing concurrent writers, disabled triggers, bulk loads, or special replication setups**.

### 5.4. Rerunnable Batched Backfill

~~~sql
WITH batch AS (
    SELECT tenant_id, order_id
    FROM orders
    WHERE amount_minor IS NULL
    ORDER BY tenant_id, order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET amount_minor = o.amount_cents::BIGINT
FROM batch AS b
WHERE o.tenant_id = b.tenant_id
  AND o.order_id = b.order_id
  AND o.amount_minor IS NULL
RETURNING o.tenant_id, o.order_id, o.amount_minor;
~~~

Explanation:

- Each execution selects at most **500 un-migrated rows** and locks the selected rows.
- `SKIP LOCKED` helps multiple workers avoid waiting on the same locked row, but **does not guarantee fairness or that all rows will be processed if rows remain continuously locked**.
- Updates the new column from the **old column of the locked record**, rather than using an amount snapshot read prior to acquiring the lock.
- If the transaction dies before commit, the rows revert to their old state; rerunning selects rows that are still NULL. If already committed, the `IS NULL` condition prevents overwriting.
- A trigger that only fires on `UPDATE OF amount_cents` does not fire when this statement only sets `amount_minor`; the guard is still checked.
- Pace, timeouts, lag, WAL, and batch size must be tuned to the real system; **500 is an illustrative number**.

**Do not update millions of rows in a single transaction just because the SQL looks short.** Large transactions can hold locks too long, create MVCC/WAL pressure and replication lag, and make stopping or recovering difficult.

## 6. Testing Migration from Structure to Data

### 6.1. Deployment Compatibility Testing

In a test environment with the same migration steps:

1. Run **A0 against S0**, capturing baselines for queries and write operations.
2. Execute **expand S0 → S1**, then rerun all A0 tests.
3. Inspect the schema via DB metadata: the new column exists with the right type, the old column has not been dropped, and permissions were not inadvertently widened.
4. Have the old writer insert/update rows and verify the bridge populates the new column.
5. Have the transitional app read both old and new columns and compare results; do not rush to shift all traffic.
6. Test restarts, rolling deploys, connection pools, and open transactions during DDL execution.
7. Only after all consumers no longer depend on the old column, test **S2 with A2** in an isolated recovery environment.

Do not assume `SELECT *` or automatic ORM reflection is unaffected when adding a column: code that deserializes by column order or count can break even on "additive-only" changes.

### 6.2. Unit Tests for the Mapping Function

For the mapping `amount_minor = amount_cents::BIGINT`, the minimum test cases are:

| Input Value | Expected Output | Purpose |
|---:|---:|---|
| 0 | 0 | Minimum valid boundary value |
| 1 | 1 | Preserves cent unit |
| 1250 | 1250 | No multiplication/division by 100 |
| 2147483647 | 2147483647 | Maximum signed `INTEGER` limit |
| -1 | Rejected | `CHECK (amount_cents >= 0)` per example business rule |
| NULL in old column | Rejected | `amount_cents NOT NULL` |
| 2147483648 into old column | Rejected | Exceeds `INTEGER` range prior to contract |

If real requirements allow refunds or negative amounts, do not force this table onto them: update the business rules and tests—**never silently alter data to pass tests**.

### 6.3. Testing the Trigger in a Rolled-Back Transaction

On a test DB with test data and inside an isolated transaction:

~~~sql
BEGIN;

INSERT INTO orders (
    tenant_id, order_id, amount_cents, currency_code, updated_at
)
VALUES (
    'T01', 'test-order-1', 1250, 'USD', CURRENT_TIMESTAMP
);

SELECT amount_cents, amount_minor
FROM orders
WHERE tenant_id = 'T01' AND order_id = 'test-order-1';

UPDATE orders
SET amount_cents = 1450,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 'T01' AND order_id = 'test-order-1';

SELECT amount_cents, amount_minor
FROM orders
WHERE tenant_id = 'T01' AND order_id = 'test-order-1';

ROLLBACK;
~~~

Expected results:

- After INSERT: old = 1250, new = 1250.
- After UPDATE: old = 1450, new = 1450.
- After ROLLBACK: the test record **does not exist**, assuming it did not exist beforehand.

**Never use test cases with IDs that could collide with real production data.** In a test environment, know the initial state, verify the affected row count, and use an isolated database/schema to avoid interfering with user data.

### 6.4. Testing the Consistency Guard

If a writer attempts to update **only** `amount_minor` to a value different from `amount_cents`, the trigger above does not fire on a new-column-only update; the **CHECK** constraint must reject the inconsistent transaction.

~~~sql
-- Intentional failure example, run only on a test DB:
UPDATE orders
SET amount_minor = amount_cents::BIGINT + 1
WHERE tenant_id = 'T01' AND order_id = 'test-order-2';
~~~

This command only tests the guard if `test-order-2` exists; if no rows match, `UPDATE 0` is **not** proof that the guard works. Automated tests must verify **exactly one row was targeted**, and an intentionally invalid update results in a **constraint violation**.

### 6.5. Testing Backfill Resumption After Failure

Create a dataset containing:

- 3 un-migrated old rows, `amount_minor IS NULL`.
- 2 correctly migrated rows.
- At least one row currently locked by another transaction.

Run the batch under this scenario:

1. Worker A processes one batch and commits.
2. Worker B stops/rolls back mid-batch.
3. Rerun the same batch statement until no NULL rows remain.
4. Verify every row still has a unique business key and no updates were lost.
5. Check that the previously locked row is picked up once the lock is released.

**The condition `WHERE amount_minor IS NULL` only prevents rewriting already-migrated rows; it does not automatically detect when the new column has a non-null but wrong value.** Separate reconciliation tests are required.

## 7. Key-Level, Row-Level, Aggregate, and Historical Reconciliation

Reconciliation has multiple layers. A solid plan never relies on a single `SELECT COUNT(*)` query as its sole proof.

### 7.1. Counting Un-Migrated Data

~~~sql
SELECT COUNT(*) AS missing_new_values
FROM orders
WHERE amount_minor IS NULL;
~~~

Expect **0** before any reader depends on the new column. However, a row with `amount_minor = 500` while `amount_cents = 600` will still go undetected.

### 7.2. Row-Level Reconciliation with `IS DISTINCT FROM`

~~~sql
SELECT
    tenant_id, order_id,
    amount_cents, amount_minor
FROM orders
WHERE amount_minor IS DISTINCT FROM amount_cents::BIGINT
ORDER BY tenant_id, order_id
LIMIT 100;
~~~

`IS DISTINCT FROM` in PostgreSQL compares NULL cases deterministically; unlike `<>`, which evaluates to UNKNOWN when either side is NULL.

If the query returns no rows, the two columns **match according to the defined mapping** in the observed snapshot. However, because they reside in the **same row** and could both have been written incorrectly, that result **does not yet prove** the original business source is correct. You must also reconcile against an independent source or a signed-off dataset.

### 7.3. Scoped Aggregate Reconciliation

~~~sql
SELECT
    tenant_id,
    currency_code,
    COUNT(*) AS orders_count,
    SUM(amount_cents::BIGINT) AS legacy_total,
    SUM(amount_minor) AS new_total
FROM orders
GROUP BY tenant_id, currency_code
ORDER BY tenant_id, currency_code;
~~~

Totals must be reconciled **within the same currency and the same grain**—never sum USD with VND without conversion rules. Although the example only uses USD, `currency_code` is kept to express the semantic constraint.

**Matching totals do not prove every row is correct.** Example:

~~~text
Source:    O1 = 100, O2 = 200  => total 300
Result:    O1 = 150, O2 = 150  => total 300
~~~

The total of 300 still matches, yet **both rows are wrong**. Therefore, you need both **row-level diff** and aggregate reconciliation.

### 7.4. Reconciling Against an Independent Source Snapshot

If there is a `source_orders_snapshot` representing an **approved source snapshot** at the same cutoff time, containing `tenant_id`, `order_id`, and `amount_cents`, you can use:

~~~sql
WITH source AS (
    SELECT tenant_id, order_id,
           amount_cents::BIGINT AS expected_minor
    FROM source_orders_snapshot
),
target AS (
    SELECT tenant_id, order_id,
           amount_minor AS actual_minor
    FROM orders
)
SELECT
    s.tenant_id AS source_tenant,
    s.order_id AS source_order,
    t.tenant_id AS target_tenant,
    t.order_id AS target_order,
    s.expected_minor,
    t.actual_minor
FROM source AS s
FULL OUTER JOIN target AS t
  ON t.tenant_id = s.tenant_id
 AND t.order_id = s.order_id
WHERE s.order_id IS NULL
   OR t.order_id IS NULL
   OR s.expected_minor IS DISTINCT FROM t.actual_minor;
~~~

`source_orders_snapshot` is an **additional illustrative table**, not part of the `orders` DDL above. Both datasets **must be pinned to the same logical point in time** (snapshot or corresponding CDC watermark); if the source keeps changing while the target is scanned, differences will appear **due to measurement timing**, not necessarily a migration bug.

The query above is only reliable if **both sides have been verified unique on `(tenant_id,order_id)`**. If the source has duplicates, a FULL JOIN can multiply the results. Uniqueness must be checked separately.

### 7.5. Key-Set Reconciliation, Not Just Row Counts

~~~sql
-- Present in source but missing in target:
SELECT tenant_id, order_id
FROM source_orders_snapshot
EXCEPT
SELECT tenant_id, order_id
FROM orders;

-- Present in target but absent in source snapshot:
SELECT tenant_id, order_id
FROM orders
EXCEPT
SELECT tenant_id, order_id
FROM source_orders_snapshot;
~~~

The two `EXCEPT` operations here check the **key set**; standard `EXCEPT` deduplicates records, so **duplicates** must still be checked separately. If source and target differ in scope (only active orders in source, all history in target), filter according to the contract before running this check.

### 7.6. Reconciling Historical Data and Effective Times

When a migration involves SCD Type 2, snapshots, or event time, comparing row counts and amounts alone is not enough:

| Model | Invariant to Check |
|---|---|
| **SCD Type 2** | No two effective intervals overlap for the same business key; an as-of join returns exactly one version |
| **Periodic snapshot** | Complete warehouse × product × snapshot date; never sum inventory across days to get ending inventory |
| **Transaction fact** | No duplicate event/business keys; event-time amount/timestamp remains accurate |
| **Analytical ratios** | Numerator and denominator share the same observation set; never sum rates |
| **Event stream** | Event ID is stable across retries; replay produces no duplicate side effects |
| **Reporting timezone change** | The same UTC timestamp may fall on different local dates; confirm restatement policy |

If converting an order-level fact to a line-level fact, `COUNT(*)` **does not need to match**; you must reconcile `SUM(line_amount)` against the **corresponding order-level value component**, classify taxes/shipping/discounts, and verify per `order_id`.

### 7.7. Multiple Verification Layers, Multiple Confidence Levels

~~~text
Schema exists with right types
    ↓
Keys/FKs/grain are valid
    ↓
Complete rows and key sets
    ↓
Row-level mapping is accurate
    ↓
Measures/KPIs by date, tenant, currency match
    ↓
Consumers return correct results
    ↓
Ongoing reconciliation after late data and concurrent changes
~~~

Each layer catches a different class of bugs. Never skip row-level checks just because a monthly summary dashboard "looks right."

## 8. Testing Concurrent Write Paths and Consistency

### 8.1. Race Condition Between Concurrent Backfill and Writer Updates

A dangerous scenario:

~~~text
T1: Backfill reads amount_cents = 1000
T2: Application updates amount_cents = 1200
T3: Backfill writes amount_minor = 1000 from stale cache
~~~

Result: the new column is wrong. The batch statement earlier reads the value under a **row lock within the same UPDATE**, reducing the risk of using a stale application snapshot; the trigger ensures every `amount_cents` update also updates the new column within its transaction.

However, **transaction isolation levels and WHERE clauses still require testing**. If an application performs read–modify–write without optimistic concurrency, two concurrent business requests can overwrite each other **even while both columns stay equal**.

### 8.2. Concurrency Test Cases

| Scenario | Setup | Expected Outcome |
|---|---|---|
| Writer A0 inserts before backfill | New column NULL | Trigger populates new column with the same value |
| Writer A0 updates backfilled row | Both columns initially equal | Both columns remain equal |
| Backfill encounters locked row | Another transaction is running UPDATE | `SKIP LOCKED` skips temporarily, processed later |
| Backfill worker dies mid-transaction | Batch not yet COMMITted | No partial updates within the batch |
| Two backfill workers run concurrently | Overlapping ID ranges | No double-apply or duplicate creation |
| Writer updates only new column | Old column unchanged | Guard rejects the mismatch |
| Two business requests update same order | With version or lock | No lost updates outside business rules |
| Writer tries to write value > INT | Old app still running | Rejected until contract is valid |

### 8.3. Why Cross-System Dual-Write Is More Dangerous

If the new structure resides in a **different database**:

~~~text
Write old_db → success
Write new_db → timeout
~~~

You cannot automatically roll back both using a local transaction alone. You need to design:

- **Transactional outbox** in the owning DB, or CDC from a reliable committed source.
- Stable event/version IDs so consumers are **idempotent**.
- Ordering rules for updates to the same entity and late-arriving events.
- Backfill combining **snapshot + stream from an evidence-backed offset/watermark**, losing no changes between the two steps.
- Reconciliation and a remediation mechanism with clear ownership.

In a distributed system, "both DBs are instantaneously equal" may **not be a valid invariant** if the architecture permits eventual consistency. You must document the **allowable lag, comparison baseline, and definition of a true error**.

## 9. Testing Applications and Contracts During Schema Migration

### 9.1. Shadow Read

In S1, the application still returns results from the old column but **also reads the new column to compare**:

~~~sql
SELECT
    tenant_id, order_id,
    amount_cents::BIGINT AS legacy_value,
    amount_minor AS candidate_value
FROM orders
WHERE tenant_id = :tenant_id AND order_id = :order_id;
~~~

Do not use `COALESCE(amount_minor, amount_cents)` as proof of correctness. If `amount_minor` is **non-NULL yet stale**, it will prefer the wrong value. Compare both values directly.

Shadow reads can increase read load and logging: sample at a bounded rate, emit mismatch metrics **without unnecessary sensitive data**, and monitor latency.

### 9.2. Canary

Gradually shift groups of users/tenants/instances to read the new field, then compare:

- Displayed values and KPI totals.
- p95/p99 latency, query error rates, timeouts, and deadlocks.
- Mismatch counts and un-backfilled row counts.
- Behavior of Java serializers, ORMs, caches, and APIs on boundary values.

No single canary percentage fits every system. Choose a window with a representative workload (including scheduled jobs) and have a tested **kill switch**.

### 9.3. API and Event Contracts Do Not Automatically Change with DB Column Names

If an API currently returns:

~~~json
{ "orderId": "O42", "amountCents": 1250, "currency": "USD" }
~~~

Changing the DB to `amount_minor BIGINT` **does not require** automatically renaming the API's `amountCents` field. You can preserve DTO v1 via projection while the semantics remain compatible. When numbers larger than 32-bit are needed, verify **representation capabilities across JSON clients, Java DTOs, event schemas, and downstream warehouses**; a v2 version or a decimal/integer string type with an explicit contract may be required.

Minimum compatibility tests:

1. Old clients can parse responses from the running API.
2. New producers do not emit events that break old consumer parsing.
3. Stored v1 events remain **replayable** after consumers are upgraded.
4. Currency/time units are not changed merely because a field name changed.
5. Schema registry, CDC connectors, and data contracts have their own phased rollout plans.

**Schema synchronization at the DB layer does not prove network contract compatibility.**

## 10. Transitioning to the New Structure Without Creating a Compatibility "Gap"

In our example, the legacy column `amount_cents` is initially `NOT NULL`. Thus, while S1 remains unchanged, an application writing only `amount_minor` **cannot validly INSERT**: the old column still requires a value. A safe cutover must distinguish among **new readers**, **transitional writers**, and **new-column-only writers**.

### 10.1. Set Pass Criteria Before Reading the New Column

~~~sql
-- Check un-migrated data:
SELECT COUNT(*) AS still_null
FROM orders
WHERE amount_minor IS NULL;

-- Check discrepancies:
SELECT COUNT(*) AS mismatched
FROM orders
WHERE amount_minor IS DISTINCT FROM amount_cents::BIGINT;

-- Validate constraint against historical data after backfill:
ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_mapping_consistent;
~~~

Both counts must be **0**, and `VALIDATE` must pass on a stable data state governed by the designed write mechanism. Before switching readers system-wide, check shadow reads, canary metrics, source reconciliation, and load impact.

### 10.2. Tighten Constraints on the New Column

Once backfilled and all writers are compatible, constraints can be tightened progressively:

~~~sql
ALTER TABLE orders
    ADD CONSTRAINT orders_amount_minor_present
    CHECK (amount_minor IS NOT NULL) NOT VALID;

ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_minor_present;

ALTER TABLE orders
    ALTER COLUMN amount_minor SET NOT NULL;
~~~

PostgreSQL can use a validated `CHECK` constraint to reduce the data scan needed for `SET NOT NULL` depending on version and conditions; **never assert that these operations require no locks**. Test them in an environment near production load.

### 10.3. Intermediate Phase S1b: Allowing New Writers to Run Concurrently

Once **proven that no old reader/writer still requires `amount_cents`**, you can transition through an intermediate phase:

~~~text
S1:
    Old column NOT NULL, new column fully populated
    Transitional writer writes old column / or both
    New reader already reads new column

S1b:
    New column NOT NULL
    Old column allowed NULL and no longer constrained by new column
    Transitional writer writing both still works
    New writer writing only new column also works
    STRICTLY no consumers require the old column to be accurate

S2:
    Old column dropped completely, only new column kept
~~~

Example DDL for **S1 → S1b**, only after the legacy-consumer gate passes:

~~~sql
BEGIN;

DROP TRIGGER IF EXISTS trg_orders_amount_legacy ON orders;
DROP FUNCTION IF EXISTS sync_order_amount_from_legacy();

ALTER TABLE orders
    DROP CONSTRAINT orders_amount_mapping_consistent;

ALTER TABLE orders
    ALTER COLUMN amount_cents DROP NOT NULL;

COMMIT;
~~~

In S1b, the new application can `INSERT` with only `amount_minor`; the transitional application can still write **both**. However, `amount_cents` **may become NULL or stale** from this point forward: **you cannot roll back to reader A0 simply by flipping a feature flag**. If rolling back to A0 after S1b is needed, you must have a plan to rebuild the old column from the new one, check `INTEGER` range bounds, restore the bridge, and assess newly created transactions—a distinct operation carrying explicit risk.

Once all writers and readers use only the new column and old dependencies are removed, execute contract:

~~~sql
ALTER TABLE orders
    DROP COLUMN amount_cents;
~~~

**Key takeaway:** a *rolling rollout* is only possible when there is an **intermediate state where both the previous and next application versions can run together**. Do not expect to drop the old column and rolling-deploy the new-column-only version simultaneously without a compatibility strategy.

### 10.4. Testing the S1b and S2 Gates

| Test | Expected in S1b | Expected in S2 |
|---|---|---|
| A1 writes both columns | Succeeds if new value is valid | **Fails** if SQL still references old column |
| A2 writes new column | Succeeds | Succeeds |
| A2 reads new column | Succeeds | Succeeds |
| A0 writes only old column | **Must not exist**; if attempted, may violate new `NOT NULL` | Incompatible |
| A0 reads old column | Value may be stale/NULL, **unreliable** | Incompatible |
| New record exceeds INT range | Can be stored if policy allows and consumers are upgraded | Can be stored |
| Restore from S0 backup | Must re-run migration and reconcile subsequent data | Needs a rehearsed recovery plan |

**S1b sign-off does not rely on "having the old column means we can roll back."** You must explicitly document when the old column stops being maintained and loses its status as a trusted read source.

## 11. What Layers Make Up Recoverability?

**Recoverability** is the ability to return the system and its data to a state that satisfies agreed invariants after a failure. It is not merely "having a backup file."

| Recovery Level | Example | Preconditions |
|---|---|---|
| **Retry a batch** | Worker dies before commit | Idempotent batch, short transactions, checkpoints |
| **Transaction rollback** | SQL updates wrongly before commit | DB rolls back all changes in the transaction |
| **Read path / feature flag rollback** | New reader displays wrong data | Old column still accurately synced, fallback tested |
| **App/schema roll-forward** | Old structure dropped or new data incompatible with old | Fix ready and valid deploy path available |
| **Rebuild projection** | Read model/data mart corrupted | Historical source, watermark, mapping, and replay |
| **Restore from backup** | Data loss or DB corruption | Readable backup, restorable, integrity checked |
| **Point-in-time recovery (PITR)** | Need to return before a destructive change | Base backup + required WAL/logs and compatible restore path |
| **Region failover / service recovery** | Node/zone failure | Failover, DNS/connections, SLOs, and consistent data |

These options are **not equivalent**:

- `ROLLBACK` only affects uncommitted transactions; it does not undo thousands of completed commits.
- **Rolling back a binary** will not let the old app run if the schema/format has already been removed.
- **Replicas** do not automatically replace backups: accidental deletes or bad writes replicate to replicas too.
- **Backups** do not automatically guarantee recovery to the needed point, especially if unrehearsed or missing logs.
- **Event replay** cannot recreate a field that was never persisted in the original events.

### 11.1. RPO and RTO

- **RPO — Recovery Point Objective:** the **maximum acceptable data loss** measured in time when recovering to a pre-incident state.
- **RTO — Recovery Time Objective:** the **maximum allowed time to restore service** to an acceptable operational state.

Illustrative target example:

~~~text
Target RPO: no more than 5 minutes of data loss accepted
Target RTO: no more than 60 minutes of service disruption
~~~

If an incident occurs at 10:00 and recovery only reaches 09:58, the **two-minute** data loss may fall within the 5-minute RPO—**only if the recovery point/commits have been accurately verified**. But if the system takes 90 minutes to resume serving transactions, the 60-minute RTO **fails**.

RPO/RTO must be **approved by the business owner**; never derive them simply from how long a `pg_restore` command takes. RTO also includes correctness verification, re-enabling writes, reconnecting applications, warming caches, and dependent components.

### 11.2. Which Backup Solves Which Case?

| Mechanism | Best Suited For | Key Limitations |
|---|---|---|
| **Logical dump** | Exporting schema/data; restoring dataset at dump point | Does not carry full WAL to recover to an arbitrary timestamp |
| **Physical/base backup** | Restoring a valid cluster/storage state | Needs exact version, config, and logs if PITR is desired |
| **WAL archive / transaction log** | Recovering to a point within retained log window | Requires intact log chain, compatible timeline, and config |
| **Managed snapshot** | Restoring to supported snapshot points | Consistency and RPO depend on service/configuration |
| **Replica** | Reducing downtime/failover | Bad writes/deletes can replicate; does not replace independent backups |
| **Replayable event log** | Rebuilding projections from events | Depends on retention, historical schemas, ordering, idempotency |

A system can combine multiple mechanisms. **Recoverability must be measured by testing on an independent copy**, not inferred from green backup schedules.

## 12. Rehearsing Restore and PITR Safely

### 12.1. Choosing the Rehearsal Environment

**Never run fault injection or PITR directly on a production DB** just for a learning exercise or test. Prepare an isolated recovery environment:

- Use backups/snapshots created through the official process.
- Isolate network and secrets; prevent test apps from sending real emails/payments.
- Anonymize or restrict access to sensitive data per policy.
- Match essential requirements for PostgreSQL version, extensions, locale/collation, config, and permissions.
- Never accidentally connect to production brokers or sources during replay.

### 12.2. Rehearsal Steps

~~~text
1. Select a backup and a target recovery point.
2. Verify backup and WAL/log chain availability, checksums/integrity.
3. Provision a completely isolated recovery DB/cluster environment.
4. Restore base backup; if PITR is needed, apply WAL/logs to the target point.
5. Start DB in controlled mode and confirm server readiness.
6. Verify schema/version, extensions, permissions, and key constraints.
7. Count keys, compare balances/values, and run business invariants.
8. Deploy the application version compatible with the restored schema.
9. Test simulated reads/writes and dependent consumers.
10. Measure total elapsed time, actual data point recovered,
    discrepancies, and follow-up remediation actions.
~~~

A restore command returning success while **missing extensions, roles, permission configs, or post-cutoff data** does not prove recovery succeeded. You must prove both data at the recovery point and **service behavior** after restore meet the contract.

### 12.3. PITR and Committed Migration Errors

Suppose `DROP COLUMN` committed at 10:05, and at 10:15 an incompatible legacy job is discovered. Options:

- **Roll-forward:** fix the job to use the new schema. Suitable if the data and new system are still sound.
- **Restore into a separate environment** to a point before `DROP COLUMN`, extract/reconcile the needed data, and plan a clean remediation.
- **Restore the entire system to an earlier point** only if valid transactions created after that point—along with integrated systems—can be accepted as lost or reconciled.

PITR rolls a database back in time, which can **lose valid transactions committed after the recovery point** or create inconsistencies with message brokers and other services. Therefore, you must have an owner-approved procedure to reapply or reconcile those changes.

**Do not treat PITR as a "safe undo button" for every migration.** Once new transactions exist, rolling back a single DB in isolation can corrupt the whole system if uncoordinated.

### 12.4. Why Successful Backups Can Still Fail to Restore

Common failure modes:

- Missing or corrupted backup files, or unable to decrypt due to **lost encryption keys**.
- Inconsistent snapshot or missing WAL segments required for recovery.
- Insufficient disk space, bandwidth, or permissions to spin up the new environment.
- Version/extension mismatch, or migrations incompatible with the restored DB version.
- Application accounts and secrets unavailable or unrecoverable.
- Restored schema does not match the currently deployed binary.
- RTO exceeded because downloading a huge dataset or rebuilding indexes takes too long.
- Backup covers primary tables but lacks object storage, attachments, or reference systems needed by the business.

Therefore, the validation plan must cover **restoring the entire relevant dependency chain**, not just the main table.

## 13. Intentional Failure Testing and Resumability

The following fault tests must be conducted in an **authorized and isolated environment**, using fixtures or protected data.

| Injected Fault | What Must Be Proven | Failure Signal |
|---|---|---|
| Backfill worker dies **before commit** | Transaction rolls back, rerun loses no rows | Some rows partially updated |
| Worker dies **after commit, before checkpoint** | Batch replay remains idempotent | Values incremented twice or duplicates created |
| Two workers pick overlapping data ranges | Locks/selectors prevent two records for the same grain | Duplicates or lost updates |
| App A0 writes after a row is backfilled | Bridge keeps the new column accurate | New column stale yet non-NULL |
| DB connection drops between two business steps | Atomic transaction or compensation rule | Order stuck in half-migrated state |
| Slow replica | Reader does not switch if freshness gate fails | Results differ from source without alert |
| CDC consumer stopped for long period | Tracks lag/backlog and resumes from offset | Lost events or incorrect reprocessing |
| Duplicate event delivery | Inbox/idempotency prevents duplicate side effects | Double order count or double charge |
| Out-of-order event arrival | Older version does not overwrite newer one | Read model regresses to past state |
| Record cannot map FK | Controlled quarantine/exception queue | Arbitrary default ID assigned |
| `DROP COLUMN` rejected due to dependency | `CASCADE` not used recklessly | Critical views/queries silently dropped |
| Restore from backup + logs | Can reconstruct schema/data at target point | Missing logs, RPO/RTO missed |

### 13.1. Do Not Claim Exactly-Once Without Proof

A flow using a transactional outbox typically delivers **at least once**. If the publisher sends an event successfully and dies before marking it sent, it may republish. Consumers need:

~~~text
eventId: stable per logical event
consumer inbox: marks processed events
business key: blocks duplicate side effects prohibited by business rules
transaction: updates inbox and read model in the same commit where possible
retry: independent controls for external APIs
~~~

Reconciling received event counts is insufficient: you must compare **logical event counts** and **business side effects** after replay.

### 13.2. Testing Restart and Resumption from Checkpoint

For backfill/CDC:

1. Run up to a defined checkpoint.
2. Abruptly stop the worker in the test environment.
3. Restart from the checkpoint or reselect un-migrated rows.
4. Verify no updates were missed during resumption.
5. Reconcile against the source snapshot and appropriate watermark.

Never rely solely on `MAX(order_id)` as a checkpoint if the source still allows **inserting/updating lower IDs** without sync/CDC protection. A cursor only proves the worker passed a range—it does **not** prove all subsequent changes were processed.

## 14. Testing Performance, Locks, and Operational Impact

A migration that produces accurate data but holds locks long enough to block incoming orders during peak hours **is still a failed migration**.

### 14.1. Measure Before and After Under Representative Workload

| Metric Group | Baseline | During Expand/Backfill/Cutover | Evaluation Criteria |
|---|---|---|---|
| **Transaction latency** | p50/p95/p99 of order writes | Compared to baseline at same load | Within SLO / approved increase bounds |
| **Error rate** | Query timeouts, deadlocks, 5xx | By tenant/endpoint/writer | No sustained abnormal spike |
| **Locks** | Lock waits, lock timeouts | At DDL and batch execution times | Does not block critical transactions past threshold |
| **WAL / I/O** | Log write rate, disk | During backfill | Does not exceed capacity or exhaust storage |
| **Replication lag** | Replica delay | During index creation and batch writes | Does not violate reader freshness gates |
| **Bloat / vacuum** | Storage size, dead tuples | After heavy UPDATEs | Appropriate maintenance plan in place |
| **Per-batch duration** | Pre-test benchmark | Median/p95 and retries | Job finishes within approved window |
| **Progress** | Total rows to migrate | Remaining rows, errors per batch | Not stuck on a specific data subset |
| **Post-cutover read/write** | Baseline from old version | Mismatch count, throughput | No correctness/availability degradation |

Test in an environment with **comparable volume, key distribution, write ratios, and indexes**, rather than just running a script on an empty DB.

### 14.2. DDL May Require Locks Even When Syntax Looks Minor

In PostgreSQL, `ALTER TABLE` can require different lock modes, and waiting for a lock can take far longer than the metadata operation itself. You must:

- Evaluate your PostgreSQL version and the exact DDL statement.
- Set an approved **`lock_timeout`** so it does not wait indefinitely and pile up other queries behind it.
- Monitor long-running transactions, connection pools, and concurrent DDL.
- Test the DDL on data with realistic structure and scale.
- Have a stop/retry plan after timeout; do not retry infinitely under identical load.

Conceptual example in a migration session:

~~~sql
SET lock_timeout = '3s';

-- Execute DDL only after lock evaluation and testing.
-- ALTER TABLE ...;
~~~

`3s` is an **illustrative** threshold, not a universal recommendation. Also consider `statement_timeout`, transaction timeouts, batch retry logic, and monitoring impact.

### 14.3. Indexes and Constraints Have Separate Validation Phases

In PostgreSQL, one way to reduce the impact of creating a large index is:

~~~sql
-- Must run outside a normal transaction block:
CREATE INDEX CONCURRENTLY idx_orders_tenant_updated
    ON orders (tenant_id, updated_at);
~~~

However, `CONCURRENTLY` still consumes CPU and I/O, can run for a long time, and can fail—leaving behind an invalid index that must be inspected before retrying. **Do not** let a migration framework blindly wrap this statement in a transaction or treat an invalid index as success.

For `CHECK` or FK constraints supporting `NOT VALID`/validate:

1. Add the mechanism to block invalid new data.
2. Clean/backfill historical data.
3. **VALIDATE** and record the result.
4. Only then rely on that invariant as a gate for new readers/writers.

The mere existence of a declared constraint that is **not yet validated** does not mean all historical data has been verified.

## 15. Designing an Evidence-Based Go / No-Go Decision

A migration requires **designated approvers and objective criteria**. Never decide "go" just because a release deadline is near or the migration SQL finished running.

### 15.1. Pre-Contract Gate Checklist

| Gate | Required Evidence | Expected Status |
|---|---|---|
| **Source/grain** | Documented business key, units, tenant scope | Signed off by owner |
| **App/schema** | Matrix A0/A1/A2 × S0/S1/S1b/S2 | All running combinations compatible |
| **Data completeness** | `missing_new_values` | 0 before new-only reads |
| **Data correctness** | `mismatched`, source/target diff | 0 or exceptions resolved per policy |
| **Uniqueness** | Duplicate-grain test | No unexplained duplicates |
| **FK/history** | Referential checks, as-of join | No unresolved violations |
| **Performance** | Canary, p95/p99, lock wait, replication lag | Within approved bounds |
| **Consumers** | Inventory of workers, APIs, CDC, BI, scheduled jobs | No remaining dependency on old column |
| **Recovery** | Backup, restore/PITR drill, rehearsed runbook | Meets RPO/RTO; point of no simple rollback known |
| **Data security** | Permission, retention, test dataset checks | No data exposure or unintended privilege grants |
| **Operations** | Owners, dashboards, alerts, rollback/roll-forward | Ready to monitor post-deploy |

**A zero threshold** makes sense for strict invariants such as duplicate keys or mis-mapped monetary amounts in the example. Other metrics may have different business-defined thresholds (e.g., 2 minutes of lag allowed), but every exception must have an **owner, scope, and remediation plan**.

### 15.2. Minimum Evidence Report

A brief template for the release record:

~~~text
Migration ID: orders-amount-v2
Schema baseline: S0
Target: S2
Business owner: Orders
Technical owner: Database / Platform

Scope:
    orders grain = (tenant_id, order_id)
    amount_minor = amount_cents::BIGINT
    currency = USD; unit = cent

Validation:
    row-level mismatch = 0
    null new values = 0
    key duplicates = 0
    source/target reconciliation = PASS at approved watermark
    A0 on S1 = PASS
    A1 on S1 = PASS
    A2 on S1b = PASS
    A2 on S2 = PASS
    canary SLO = PASS

Recovery:
    latest restore rehearsal = PASS
    observed RPO/RTO = recorded values
    fallback available until phase S1
    after phase S1b = roll-forward / planned repair

Approval:
    business + technical + operations
~~~

This is an **evidence template**, not a report from a real deployment. When used, record actual measurements, artifact versions, test timestamps, and links to logs/dashboards with appropriate access controls.

### 15.3. Reasons to Stop Immediately

- New column values **differ from the old column while non-NULL**, with unknown root cause.
- An old writer is found still writing after the bridge was removed.
- The new read path alters KPIs without semantic change approval.
- Backfill causes replication lag or lock waits to exceed thresholds.
- Restore test fails, WAL required for PITR is missing, or the matching app version cannot start.
- Duplicate event tests cause duplicate charges or shipments.
- In a multi-tenant system, the migration omits tenant namespacing from keys or permission checks.

**No-go is a valid validation outcome.** Delaying contract is usually far less risky than prematurely dropping structures that consumers still rely on.

## 16. Different Migration Types Require Different Test Suites

### 16.1. Pure Column Rename

The primary risk is **schema/consumer compatibility**. For a 1:1 mapping, test A0/A1/A2, rename policies, view compatibility, and rarely executed jobs. Prove data is preserved by key and no old structures remain in use before dropping.

### 16.2. Changing Data Type or Currency Unit

Changing `INTEGER` → `BIGINT` differs from changing **cents → dollars**. The latter requires conversion formulas, rounding rules, and tests:

~~~text
125 cents -> 1.25 dollars, not 125 dollars
~~~

If the system uses `NUMERIC`, test precision/scale, multiple currencies, and aggregations; never use `DOUBLE PRECISION` for money requiring exact decimal precision.

### 16.3. Splitting One Field into Multiple Fields

Example:

~~~text
shipping_address_text
    ↓
shipping_street, shipping_ward, shipping_city, shipping_country
~~~

A parser cannot guarantee accurate splitting of every legacy address. Tests need:

- Diverse real-world datasets with whitespace, Vietnamese text, missing components, and international data.
- **Parse success rate** and **mapping confidence**.
- Rows with insufficient information routed to a review queue; never fabricate dummy countries/wards.
- Rules preserving the address at transaction time rather than accidentally mutating it to match the current profile.
- Reversibility: once the original string is dropped, delivery notes that cannot be reconstructed may be lost.

A migration can succeed in row count while suffering **irreversible loss of business information**.

### 16.4. Changing from One-to-Many to Many-to-Many

Source:

~~~text
employees.department_id
~~~

Target:

~~~text
employee_departments(employee_id, department_id, valid_from)
~~~

Tests must prove:

- Each legacy relationship converts into **exactly one new relationship** per policy.
- No duplicates of `(employee_id,department_id,valid_from)` are created.
- If multiple departments are newly allowed, legacy apps reading only one `department_id` **no longer have sufficient semantics**.
- Feature gating is needed, or a validated definition of "primary department" is required.

This is not just a schema change—it is a **business contract change**.

### 16.5. Migrating from Relational to Document or Graph

**Document:** an order may embed `items[]`. When flattening to a line-item fact, never copy the order-level `order_total` onto every item and sum it. Test pre/post grain and nested row counts.

**Graph:** a relationship may be reachable via multiple paths. When converting FKs to edges/nodes, test **unique entity and relationship counts**, not path counts as transaction counts.

**Time series:** moving from an event table to metric+labelset series requires testing cardinality/churn, measurement intervals, and data lost during aggregation. Never treat label timestamps as a substitute for event history.

### 16.6. Migrating Analytical Facts and Dimensions

If the old fact is at order grain and the new fact is at line grain:

- `COUNT(*)` does not need to match.
- Converting `order_total` must accurately decompose taxes, shipping, discounts, and refunds if needed.
- `COUNT(DISTINCT order_id)` may require tenant/source namespacing.
- SCD Type 2 must match dimension versions by **event time**, not ingestion date.
- A one-to-many dimension `JOIN` can fan out facts and inflate totals.

**Reconciliation suites must be grounded in grain and KPIs**, not mechanical row counts of structurally different tables.

## 17. Common Pitfalls in Validation and Recovery

| Pitfall | Why It Is Insufficient | Better Approach |
|---|---|---|
| "DDL returned exit code 0 so it passed" | Data, apps, and recovery remain untested | Multi-layered gates |
| "Both tables have the same COUNT(*) so they match" | Values could be swapped or drifted | Compare key sets, row-level diffs, and totals |
| "Total amount matches so data is accurate" | Errors can cancel each other out | Row-level reconciliation |
| "`COALESCE` always gives the right value" | New column can be stale yet non-NULL | Sync and mismatch detection |
| "One-time backfill is enough" | Old writers still write and late events arrive | Bridge/CDC and continuous checks |
| "Having a surrogate PK prevents duplicates" | Two rows with the same business grain can have different IDs | Unique-grain test |
| "Having a replica means having a backup" | Accidental deletes/writes replicate too | Independent backups, restore drills |
| "Having a dump file means meeting RTO" | Restore and app startup can be slow | Measure end-to-end recovery |
| "PITR can always undo a migration" | Loses newer commits or diverges from brokers | Reconcile/roll-forward plan |
| "We can roll back old app after dropping columns" | Old binaries cannot read the new schema | Identify the point of no simple rollback |
| "`NOT VALID` means constraint is inactive" | New writes may still be checked | Understand unvalidated historical state |
| "`CONCURRENTLY` means zero cost" | Still consumes I/O, CPU, and can fail | Monitor load and index state |
| "Running on a small DB is representative enough" | Misses large lock/index/backfill behavior | Realistic volume/load and monitoring |
| "Deleting test data from prod afterward is fine" | May already have triggered emails, payments, events | Isolated environment and mocked side effects |
| "DB schema changed so API must change immediately" | Consumers have different lifecycles | Independent API/event contracts |
| "Only happy-path testing is needed" | Failures often happen under retries/concurrency | Safe failure injection |
| "All late-arriving events are input errors" | Event time differs from ingestion time | Watermarks and period-close policies |
| "Log all data for easier debugging" | Risks exposing PII/monetary data | Metrics, reference IDs, and access control |

## 18. Practice Exercises with Solutions

### Exercise 1 — Is Renaming a Column in One Step Safe?

A system has two application versions running concurrently. The old version reads `amount_cents`; the new version reads `amount_minor`. The team wants to run `ALTER TABLE ... RENAME COLUMN` directly and rolling-deploy the new app. State the risks and an appropriate plan.

**Solution:** The old app version will fail immediately once the column is renamed, while the new version may fail if it starts before the new schema is applied. Instead, **expand** by adding the new column, maintain a bridge/sync and backfill, verify the app–schema compatibility matrix, transition reads/writes through compatible phases, and **contract** only after no old consumers remain.

### Exercise 2 — Matching Totals, Wrong Data

Source has `O1=100`, `O2=200`; target has `O1=150`, `O2=150`. Both total 300. Is checking `SUM` alone sufficient?

**Solution:** **No.** Both records are wrong, but their errors cancel out. Reconcile **per business key**, then compare key sets, row counts, and totals by tenant/period/unit.

### Exercise 3 — Backfill Finished, Yet Readers Still Return Wrong Values

A row has `amount_cents=1000`, `amount_minor=1000`. The old app updates `amount_cents=1200`, but the bridge is broken. The reader uses `COALESCE(amount_minor,amount_cents)`. What does it read, and how do you fix it?

**Solution:** It reads **1000**, which is **wrong** because the new column is non-NULL yet stale. Fix the writer synchronization mechanism, run mismatch checks, and add tests for old writers **post-backfill**; `COALESCE` does not catch stale values.

### Exercise 4 — Retrying When Backfill Is Killed

A job batches by `WHERE amount_minor IS NULL`, and the transaction is killed while updating the 20th batch. Can it be safely rerun?

**Solution:** If each batch is an atomic transaction and the mapping is idempotent, the uncommitted batch rolls back; rerunning selects rows that are still NULL. Verify concurrency, checkpoints, and row-level mismatches to ensure **no existing non-null values are wrong**.

### Exercise 5 — Checking for NULL Is Not Enough

After backfill, `SELECT COUNT(*) WHERE amount_minor IS NULL` returns 0, but `amount_minor` has 10 values diverging from `amount_cents`. Can reads be switched to the new column?

**Solution:** **No.** The completeness gate passed, but correctness failed. Compare using `IS DISTINCT FROM`, identify which writer/trigger caused the drift, repair from the trusted source, and re-run reconciliation.

### Exercise 6 — Data Type Limits

`amount_cents` is a signed `INTEGER`; `amount_minor` is `BIGINT`. While the old column and old app are still active, the new app wants to write **3,000,000,000**. What happens?

**Solution:** This value exceeds the signed 32-bit maximum of **2,147,483,647**. You cannot preserve the legacy column and old consumers under a 1:1 mapping. All consumers must be upgraded, and a tested S1b/S2 phase must be reached before enabling large values.

### Exercise 7 — New Writer Writes Only the New Column

In S1, `amount_cents` is still `NOT NULL`, and the bridge only copies from the old column. App A2 sends an INSERT containing only `amount_minor`. Will it succeed?

**Solution:** **No.** An INSERT missing `amount_cents` will violate `NOT NULL`. Either the transitional app must write both columns, or you must reach phase S1b when **no old readers/writers remain**, drop the bridge/guard at the right time, and make the old column nullable before running a new-only writer.

### Exercise 8 — Can You Roll Back to A0 After S1b?

The system removed the bridge, made `amount_cents` nullable, and the new app started writing large values to `amount_minor`. Will a "read old" feature flag safely recover?

**Solution:** **No.** The old column may be NULL/stale or unable to hold large numbers. You must use roll-forward or a verified reconstruction procedure—never treat a feature flag as an automatic data rollback.

### Exercise 9 — Does a Replica Replace a Backup?

A team has a synchronous read replica but has never tested restoring from a backup. After an accidental `DELETE`, does having the replica guarantee recovery?

**Solution:** **No.** Valid delete commands replicate to the replica. You need independent backups, logs/PITR if required, retention, verification, and **actual restore drills**.

### Exercise 10 — Evaluating RPO/RTO

An incident happens at 10:00, data is recovered to 09:58, and the service is fully operational at 11:30. Targets are **RPO ≤ 5 minutes**, **RTO ≤ 60 minutes**. Evaluate the result.

**Solution:** Maximum data loss based on the given timestamps is **2 minutes**, which can meet RPO if commits up to that point are verified. Service downtime is **90 minutes**, **missing RTO**. You must account for app startup, reconnections, verification, and reopening service.

### Exercise 11 — Does PITR Erase New Transactions?

At 10:05 the old column is dropped; at 10:15 a job failure is detected; between 10:05 and 10:15 many valid orders were created. The team proposes restoring the whole DB to 10:04. What must be considered?

**Solution:** Full-DB PITR to 10:04 can lose commits made afterward and diverge from payment systems, brokers, and consumers. Prefer **roll-forward** if it is just a consumer bug; if a restore is unavoidable, plan how to preserve/reapply post-cutoff transactions and reconcile across systems.

### Exercise 12 — Snapshot + CDC Without a Watermark

A team copies an old table to a new DB over one hour, then starts reading CDC from the time the copy finishes. What is the risk?

**Solution:** Updates occurring **during the copy** may neither be captured accurately in the copied snapshot nor re-read via CDC. You need a consistent snapshot, a recorded offset/watermark, and replay/idempotency handling; never treat "start CDC after copy finishes" as a complete guarantee.

### Exercise 13 — Comparing Facts at Different Grains

The old fact has 100 orders; the new fact has 420 line items. `COUNT(*)` does not match. Does this prove the migration is wrong?

**Solution:** **No.** The grains differ. Check **order-set completeness**, uniqueness of `(order_id,line_no)`, source-line mapping, per-order aggregation of line values, and currency/fee/discount breakdowns. Never force two different-grain row counts to match.

### Exercise 14 — Overlapping Intervals in SCD Type 2

A transaction on July 15 JOINs two customer dimension records because two effective intervals overlap. The migrated fact reports doubled revenue. What check needs to be added?

**Solution:** Validate **non-overlapping `[valid_from,valid_to)` intervals** per business key and confirm **an as-of join matches exactly one version** per fact. Never patch it with `SUM(DISTINCT amount)`, because genuine transactions can share identical amounts.

### Exercise 15 — Contracting While an Infrequent Job Still Exists

For three weeks no production request reads `amount_cents`, yet a quarterly reconciliation job still uses it. Are conditions met to drop the column?

**Solution:** **No.** Three weeks of runtime monitoring cannot observe a quarterly job. Inventory and update the job, test it against the new schema, verify legacy consumers/restore runbooks, and only then approve contract.

### Exercise 16 — Address Model Without an Inverse Transformation

The source holds `shipping_address_text`; the new system splits `street,ward,city` and drops the original field. Some addresses containing notes like `"deliver at the back gate"` were dropped by the parser. What failed?

**Solution:** **Irreversible information loss.** No SQL rollback can reconstruct lost notes. Retain raw data per policy, test with diverse mapping samples, use review queues, and require risk sign-off before deletion.

### Exercise 17 — Lost ACK in Event Streaming

A publisher successfully sends an event and crashes before marking it published. Upon restart, the event is resent and the consumer creates two shipment orders. What is the root cause and fix?

**Solution:** At-least-once delivery can produce duplicates. Consumers must be idempotent by `eventId` and business invariants, write to an inbox in the same transaction as the read model where applicable, and guard external side effects. Tests must confirm **only one shipment is created** after replay.

## 19. Schema Migration and Recoverability Validation Checklist

- [ ] Defined **grain, business key, namespace, and old–new mapping formula**.
- [ ] Agreed on currency units, business timestamps, statuses, `NULL`s, and edge cases.
- [ ] Built an **app–schema compatibility matrix** covering infrequent consumers, workers, CDC, and BI.
- [ ] Measured baseline latency, error rates, WAL/I/O, replication lag, and data volume.
- [ ] Expand does not break old apps; locking DDL tested under realistic load.
- [ ] Bridge/dual-write/CDC keeps concurrent updates consistent without creating two sources of truth.
- [ ] Backfill is batched, safely retryable, idempotent, and rate-limited.
- [ ] Tested workers stopping before/after commit, concurrent workers, row locks, and restarts.
- [ ] Added checks for **NULLs, row-level mismatches, key sets, duplicates, FKs, and scoped totals**.
- [ ] Reconciled against an independent source at the **same snapshot/watermark**, not just two columns in the same row.
- [ ] For historical data, verified event time, SCD valid-time, late events, replay, and restatements.
- [ ] Shadow reads/canary passed correctness and SLOs before shifting all readers.
- [ ] Switched to new-only writers only after the new column was populated, constraints validated, and no old writers remained.
- [ ] Documented the **point of no simple rollback**, especially when removing sync and dropping columns.
- [ ] Tested API/event/CDC contracts independently of DB schema changes.
- [ ] Verified schemas/roles/extensions/configs when restoring into an isolated environment.
- [ ] Have reliable backups/snapshots/logs and performed **actual restore/PITR rehearsals**.
- [ ] RPO/RTO have approved targets and **measured empirical timings**, not just paper commitments.
- [ ] Have a plan to reapply or reconcile newer transactions if restoring to an earlier point.
- [ ] Enforced PII controls, permissions, retention, and outbound messaging safeguards when testing with restored data.
- [ ] **Go/no-go** gate has evidence, owners, and stop/roll-forward procedures.
- [ ] Never contract while old consumers exist; monitor mismatches and data quality **post-deploy**.

## 20. Summary: Validate Before Cutting Off Your Retreat

Keep four questions in mind before any risky change:

1. **Can it deploy alongside the running system?** — test app–schema compatibility and constraints.
2. **Has the data migrated completely and meaningfully?** — reconcile **by key, row, period, and unit**, not just row counts or sums.
3. **If it fails midway, can it resume safely?** — short transactions, idempotency, checkpoints, CDC offsets, and retryability.
4. **If a major failure occurs, can it recover within acceptable bounds?** — backups, PITR/replay, restore drills, RPO/RTO, and post-cutoff transaction handling.

**Remember:** **Schema migration testing, reconciliation, and recoverability must be designed as an end-to-end evidence system across expand–migrate–contract.** A migration is only trustworthy once **data accuracy, consumer compatibility, and recovery paths** have been verified before removing old structures.



