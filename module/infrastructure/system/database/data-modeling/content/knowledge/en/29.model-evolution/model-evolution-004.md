# Expand First, Migrate Gradually, Then Contract Legacy Structures

## Learning Objectives

In **DATABASE_DATA_MODELING**, data design is not just creating a sound initial model—it is ensuring the model **evolves safely as business requirements, traffic, and integrated systems change**. A seemingly minor column change can break old application versions, corrupt ETL jobs, drop fields from downstream services, or leave old and new data inconsistent.

This topic in the **Model Evolution** chapter introduces the **expand → migrate → contract** strategy (*expand–migrate–contract*, also called *expand-and-contract*):

1. **Expand:** add new structures without breaking consumers of the old structures.
2. **Migrate/Transition:** shift data and read/write paths in stages with monitoring and reconciliation.
3. **Contract:** remove old structures only once **no dependencies remain** and safety criteria are met.

After this lesson, you will be able to:

- Build a **compatibility matrix** across schema, application, API, event, and pipeline versions.
- Identify when an **additive** change can ship safely and when it must be split across phases.
- Design **dual-writes**, fallback reads, triggers/CDC, or workflows without creating two conflicting sources of truth.
- Run batched, idempotent backfills on large datasets with watermarks and without losing concurrent updates.
- Gradually tighten `NOT NULL`, foreign keys, and indexes using verifiable rollout steps.
- Define phase-gate criteria, rollback/roll-forward plans, and data quality measurements.
- Distinguish internal database schema changes from external API/event contract changes.

## 1. Why Can't Schemas Always Be Changed in One Shot?

Suppose the Orders service currently stores amounts in column `amount_cents INTEGER`. The engineering team wants to move to `amount_minor BIGINT` for clearer naming and wider numeric range. A risky plan is:

~~~sql
ALTER TABLE orders RENAME COLUMN amount_cents TO amount_minor;
ALTER TABLE orders ALTER COLUMN amount_minor TYPE BIGINT;
~~~

At the data level, the change looks reasonable. In a live environment, however:

- **Application v1** querying `SELECT amount_cents FROM orders` breaks immediately after the rename.
- Some **workers, cron jobs, ETL pipelines, and mobile apps** may not yet be upgraded.
- During rolling deployments, some instances still write to the old schema while new instances use the new schema.
- A snapshot job or CDC stream may read the old shape and fail to decode change records.
- If semantics shifted from **cents** to **major currency units**, data becomes **100x wrong** even though SQL succeeds.

Direct renames or type changes may still be acceptable for small systems with an approved write freeze, fully controlled consumers, and clear recovery plans. For systems requiring **continuous availability or serving many consumers**, you must design a **phase where versions coexist**.

> Principle: **Never remove a structure while any valid application version or consumer still relies on it.**

## 2. The Expand–Migrate–Contract Mindset

~~~mermaid
flowchart LR
    A["Old Schema + Old App"] --> B["EXPAND\nOld and new coexist"]
    B --> C["MIGRATE\nCompatible writes + backfill + read switch"]
    C --> D["CONTRACT\nDrop old structure when safe"]
    D --> E["New Schema + New App"]
~~~

### Phase 1 — Expand: Add Without Breaking

Goal: introduce storage for the new model **while legacy clients keep operating**.

Examples:

- Add column `amount_minor BIGINT NULL`.
- Create a new table without dropping the old table.
- Add indexes supporting new query patterns.
- Prepare mappings and consistent write logic.
- Do not force old apps onto the new field yet; do not drop or rename old fields yet.

**Syntactically additive does not guarantee behavioral compatibility.** Adding a column with an expensive default, a buggy trigger, an ill-timed constraint, or higher write latency can still cause outages. Evaluate the actual DBMS, version, load, and rollout mechanics.

### Phase 2 — Migrate: Shift Data and Traffic Step by Step

Goal: ensure **new writes stay synchronized**, **historical data is backfilled**, and consumers transition in a controlled way.

Tasks may overlap but follow dependency order:

- Ensure every active writer **maintains the new structure**.
- Backfill historical rows in batches.
- Monitor old–new reconciliation, resource usage, and sync errors.
- Shift a subset of readers to the new column/table.
- Expand coverage until **all readers and writers** use the new model.

### Phase 3 — Contract: Remove Old Structures

Goal: drop old write paths, obsolete constraints, unneeded indexes, and legacy columns/tables **once zero dependencies are confirmed**.

Contract **is not casual cleanup**. It is a change capable of breaking old apps, infrequent jobs, rarely viewed dashboards, or restores from older backups.

## 3. Four Invariants to Preserve During Transition

| Invariant | Verification Question | If Violated |
|---|---|---|
| **Compatibility** | Does every running version understand the deployed schema? | Application read/write failures |
| **Correctness** | Do old and new values share semantics and update consistently? | Corrupted reports/orders |
| **Progress** | Can backfill and cutover resume cleanly across retries, restarts, and network faults? | Partial stall, hard to resume |
| **Observability & Recoverability** | Can we see unmigrated rows, and is there a safe path back or forward? | Silent bugs, dangerous rollbacks |

In practice, also weigh **security, retention, foreign keys, latency, write amplification, and storage costs**. A migration whose SQL exits 0 while degrading production or corrupting data **is not a success**.

### Clear Decision Ownership

Business owners must confirm **field semantics and conversion rules**. Engineering/DBAs own rollout, locks/constraints, backfills, and DB health. Consumers confirm contract compatibility. Never let a migration job unilaterally decide that unparseable values become `0` or `NULL`.

## 4. Compatibility Matrix Between Schema and Application Versions

Suppose three schema states:

- **S0:** `amount_cents` only.
- **S1:** both `amount_cents` and `amount_minor`, with synchronization.
- **S2:** `amount_minor` only.

Applications:

- **A0 (legacy):** reads/writes `amount_cents` only.
- **A1 (transition):** knows both columns, reads safely, and writes per transition strategy.
- **A2 (new):** reads/writes `amount_minor` only.

| Application / Schema | S0 — old | S1 — dual columns | S2 — new |
|---|---|---|---|
| **A0** | Works | **Can work**, if legacy column semantics and sync remain intact | **No** |
| **A1** | **Design-dependent**; fails if SQL references the new column | Works when sync/backfill logic is right | **Design-dependent**; fails if it still references the old column |
| **A2** | **No** | Works once new column has data, semantics, and right write path | Works |

General rollout sequence:

~~~text
S0 + A0
    ↓ Expand schema
S1 + A0
    ↓ Deploy compatible logic, backfill
S1 + A1
    ↓ Switch reads/writes and monitor
S1 + A2
    ↓ Confirm zero A0/A1 dependencies remain
S2 + A2
~~~

**Build the matrix for your real system**, not just two illustrative columns. A single change can affect external APIs, mobile apps surviving for months, background workers, CDC, BI, and snapshot restores.

### Never Assume A1 Runs on S0

An app issuing `SELECT COALESCE(amount_minor, amount_cents)` **still fails** on S0 because `amount_minor` does not exist yet. Fallback queries help **only after schema expansion**, unless the app uses separate query paths or explicit feature detection.

## 5. End-to-End Example: Legacy `INT` Column to New `BIGINT`

We use PostgreSQL to illustrate a **verifiable migration**. Do not assume every environment requires these exact column names or syntax.

### 5.1. Context and Semantics

Initial source table:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL
);
~~~

New requirement:

~~~text
Old name: amount_cents INTEGER
New name: amount_minor BIGINT
Unit in example: USD cents for both fields
Grain: one row = one order
Conversion rule: amount_minor = amount_cents::BIGINT
~~~

**Important:** widening `INTEGER` to `BIGINT` and renaming **does not automatically change units**. Here *minor unit* stays cents because only USD is modeled. Expanding to multiple currencies with different minor scales requires `currency_code`, conversion/rounding rules, and a **separate** business migration—never inferred from this cast.

Why choose this example? It illustrates **structural evolution preserving semantics**, avoiding brittle automated splitting of free-text addresses or names where old records lack sufficient detail.

### 5.2. Expand: Add the New Column First

~~~sql
ALTER TABLE orders
    ADD COLUMN amount_minor BIGINT;

ALTER TABLE orders
    ADD CONSTRAINT orders_amount_minor_nonnegative
    CHECK (amount_minor IS NULL OR amount_minor >= 0)
    NOT VALID;
~~~

After this step:

- `amount_cents` stays intact so **A0** keeps working.
- `amount_minor` starts **nullable**, avoiding forcing immediate backfill of historical rows.
- PostgreSQL `CHECK ... NOT VALID` enforces the rule on **new/updated writes** without scanning all historical rows at creation time; still inspect lock impact in production.
- Do not add `NOT NULL` immediately while millions of legacy rows remain unbackfilled.

**DDL performance note:** adding a nullable column without a default is typically a lightweight metadata operation in modern PostgreSQL versions, yet `ALTER TABLE` can still wait on locks. Never treat it as "lock-free" or "always instantaneous".

### 5.3. Sync Problem When Old and New Apps Write Concurrently

Suppose after adding the column, we backfill `order_id = 42`:

~~~text
amount_cents = 1000
amount_minor = 1000
~~~

Then A0 updates:

~~~sql
UPDATE orders
SET amount_cents = 1200
WHERE order_id = 42;
~~~

Without synchronization, the row becomes:

~~~text
amount_cents = 1200   -- new
amount_minor = 1000   -- stale, wrong
~~~

Reads using `COALESCE(amount_minor, amount_cents::BIGINT)` return **1000**, causing a **silent monetary error**. A one-time backfill is **not enough** while older app versions can still write.

**Prerequisite:** before or during backfill, ensure **every write path** affecting migrated data stays synced via a deliberate mechanism. Depending on the system:

1. **Application dual-write**: the application updates both columns in the **same transaction/statement**, once all legacy-only writers are replaced; or
2. **Compatible DB trigger**: the database syncs both columns even when A0 knows only the old column; or
3. A migration workflow using **write freezes/coordination**, CDC, and robust reconciliation with clear consistency windows.

Never execute two writes across **two separate databases** and call that an atomic dual-write. Without distributed transactions, you need outbox/CDC, retries/idempotency, and reconciliation.

### 5.4. Illustrative PostgreSQL Trigger Bridge

In this example, if A0 keeps writing `amount_cents` while A1/A2 may write `amount_minor` during **S1**, a bidirectional sync trigger can bridge them. This is an **educational pattern**; test transaction concurrency, load, and bulk-load paths before production use.

~~~sql
CREATE OR REPLACE FUNCTION sync_orders_amount()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.amount_minor IS NULL THEN
            NEW.amount_minor := NEW.amount_cents::BIGINT;
        ELSIF NEW.amount_cents IS NULL THEN
            IF NEW.amount_minor < 0
               OR NEW.amount_minor > 2147483647 THEN
                RAISE EXCEPTION 'amount_minor outside legacy INTEGER range';
            END IF;
            NEW.amount_cents := NEW.amount_minor::INTEGER;
        ELSIF NEW.amount_minor IS DISTINCT
              FROM NEW.amount_cents::BIGINT THEN
            RAISE EXCEPTION 'inconsistent order amounts';
        END IF;
    ELSE
        IF NEW.amount_cents IS DISTINCT FROM OLD.amount_cents
           AND NEW.amount_minor IS NOT DISTINCT FROM OLD.amount_minor THEN
            -- Legacy writer updated only the old field.
            NEW.amount_minor := NEW.amount_cents::BIGINT;
        ELSIF NEW.amount_minor IS DISTINCT FROM OLD.amount_minor
              AND NEW.amount_cents IS NOT DISTINCT FROM OLD.amount_cents THEN
            -- New writer updated only the new field.
            IF NEW.amount_minor < 0
               OR NEW.amount_minor > 2147483647 THEN
                RAISE EXCEPTION 'amount_minor outside legacy INTEGER range';
            END IF;
            NEW.amount_cents := NEW.amount_minor::INTEGER;
        ELSIF NEW.amount_minor IS DISTINCT FROM OLD.amount_minor
              AND NEW.amount_cents IS DISTINCT FROM OLD.amount_cents
              AND NEW.amount_minor IS DISTINCT
                  FROM NEW.amount_cents::BIGINT THEN
            RAISE EXCEPTION 'inconsistent order amounts';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_sync_orders_amount
BEFORE INSERT OR UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION sync_orders_amount();
~~~

Explanation and limitations:

- On `INSERT`, if only the old value is supplied, the trigger populates the new value; if only a new value within legacy bounds is supplied, it populates the old column **before** `NOT NULL` checks fire.
- On `UPDATE`, changing one side syncs the other; changing both to disagreeing values rejects the transaction.
- During compatibility, **values beyond the old `INTEGER` limit are rejected** even though the new column is `BIGINT`, because legacy writers/readers cannot handle larger numbers.
- This pattern assumes **one non-negative amount per order** and unchanged units; if negative adjustments exist, revise invariants.
- Updating unrelated columns on an unbackfilled row may leave the new column `NULL`; **fallback reads** and backfill cover that state.
- Any path bypassing triggers—special bulk loads, replication, or direct admin writes—must be accounted for; never assume a trigger protects the entire system unconditionally.

**Simpler option:** if all compatible writers can deploy before switching reads and zero A0 instances remain, the application can write both columns in one `UPDATE`/transaction with no trigger needed. Choose **one clear source-of-truth rule** so two mechanisms never overwrite each other.

## 6. Batched, Restartable Historical Backfill

Once new write paths are safe, backfill historical rows still having `amount_minor IS NULL`.

### 6.1. Never Update Millions of Rows in One Giant Transaction

A single statement:

~~~sql
UPDATE orders
SET amount_minor = amount_cents::BIGINT
WHERE amount_minor IS NULL;
~~~

is mathematically valid, yet on large tables it can:

- Generate massive WAL/redo logs, MVCC row versions, and I/O.
- Spike replication lag, lock contention, or request latency.
- Create long transactions that resist progress tracking and retries.
- Cause table bloat and vacuum/compaction pressure.

Tune batch size and pacing to the actual workload.

### 6.2. PostgreSQL Row-Locking Batch Example

~~~sql
WITH batch AS (
    SELECT order_id
    FROM orders
    WHERE amount_minor IS NULL
    ORDER BY order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET amount_minor = o.amount_cents::BIGINT
FROM batch AS b
WHERE o.order_id = b.order_id
  AND o.amount_minor IS NULL
RETURNING o.order_id, o.amount_minor;
~~~

Execute each batch in a **short transaction** with rate control, monitoring, and stop conditions. Locating unmigrated rows needs proper selectivity/indexing on large tables; never assume repeated full-table scans are cheap.

**Why is this batch idempotent?** After a successful batch, updated rows are no longer `NULL`, so re-running **does not overwrite them**. If a worker crashes before commit, the batch rolls back and rows are re-selected. Combined with the sync trigger on updates, the new value is computed from the **old value in the locked row version**, reducing stale overwrites.

**Why `SKIP LOCKED`?** Multiple workers divide unlocked rows instead of blocking on one another. It does **not** guarantee fairness or immediate selection of every row; workers must keep running, handle errors, and watch the remaining backlog.

### 6.3. Tracking Progress and Discrepancies

~~~sql
-- Unbackfilled row count:
SELECT COUNT(*) AS missing_new_amount
FROM orders
WHERE amount_minor IS NULL;

-- Discrepancies (including NULLs):
SELECT order_id, amount_cents, amount_minor
FROM orders
WHERE amount_minor IS DISTINCT FROM amount_cents::BIGINT
ORDER BY order_id
LIMIT 100;

-- Reconciling totals over the target scope:
SELECT
    COUNT(*) AS row_count,
    SUM(amount_cents::BIGINT) AS old_sum,
    SUM(amount_minor) AS new_sum
FROM orders;
~~~

PostgreSQL's `IS DISTINCT FROM` handles `NULL`s properly, avoiding the pitfall of `amount_minor <> amount_cents`, which evaluates to `UNKNOWN` when the new column is `NULL`. **Matching sums alone do not prove every row matches**: opposite errors can cancel out. Check totals, row counts, keys, and row-level diffs together.

In massive systems, full-table reconciliation scans can be expensive. Slice by **partition / ID range / tenant**, compute batch checksums or stats, and schedule full checks off-peak—explicitly noting each check's scope limits.

## 7. Phased Read and Write Cutover

After expand and synchronization are active, avoid switching all consumers at once if risk is hard to bound. One rollout plan:

| Phase | Write Path | Read Path | Gate Before Next Phase |
|---|---|---|---|
| **P0 — legacy** | Old field only | Old field only | Consumers inventoried; conversion defined |
| **P1 — expand** | Legacy active; sync populates new field | Legacy | New schema present; A0 unbroken |
| **P2 — backfill** | Old/new synced in source transaction | Legacy; shadow-read new field | Backlog and mismatches within approved threshold |
| **P3 — canary** | Sync continues | Small subset reads new with fallback | Reconciliation, errors, and latency meet SLOs |
| **P4 — cutover** | Write new field, reverse-sync if A0 still runs | All consumers permitted to read new | Zero legacy read paths; legacy writers retired |
| **P5 — contract** | New field only | New field only | Soak window passed; recovery plan verified |

Separate **read paths** from **write paths**: switching reads does not prove all writers upgraded; switching writers does not prove old read jobs retired.

### 7.1. Conditional Fallback Reads

In S1, a transitional query:

~~~sql
SELECT
    order_id,
    COALESCE(amount_minor, amount_cents::BIGINT) AS amount_for_read
FROM orders
WHERE order_id = :order_id;
~~~

is **safe only** once you eliminate the risk of **stale non-null values in the new column**. If the sync trigger was disabled or a writer bypassed sync, `COALESCE` **prefers the stale value**. Measure mismatches continuously, not just `NULL` counts.

### 7.2. Shadow Reads and Canaries

Early on, the app can read both and **compare** while still returning the legacy value to callers, then gradually shift live traffic:

~~~text
Phase shadow:
    user sees old_amount
    application compares old_amount vs new_amount
    metrics record mismatches (never log PII/sensitive data)

Phase canary:
    1% requests read new_amount
    compare business results, latency, errors

Phase rollout:
    10% → 50% → 100% if defined thresholds hold
~~~

These are **illustrative percentages**, not rigid targets for every system. When canarying by **tenant, app group, or instance**, avoid letting a cohort write via the old path while reading via the new path without active sync.

### 7.3. When Can Values Exceed the Legacy Limit?

Here `BIGINT` is meant to hold values larger than `INTEGER`. During S1 while A0 still operates, the example trigger **rejects** values above `2,147,483,647` so reverse sync to the old column stays valid.

Lift the old range limit only after:

1. All read/write paths handle `BIGINT` with no 32-bit assumptions.
2. APIs, protobuf/JSON schemas, ETL jobs, ORMs/Java DTOs, and reports accept the wider type.
3. Reverse synchronization to `INTEGER` is removed per plan.
4. Boundary values at and above the old limit are tested.

**Widening a DB column does not guarantee the entire stack accepts wider values.** For instance, a Java `int` overflows large `BIGINT`s; serializers, consumers, and warehouses may enforce their own limits.

## 8. Tightening New Constraints After Data Is Clean

A common mistake is adding `NOT NULL` before backfill finishes. Instead, tighten constraints incrementally once **zero `NULL`s remain and all writers supply the new field**.

PostgreSQL example:

~~~sql
-- Run only after verifying backfill and all writers.
ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_minor_nonnegative;

ALTER TABLE orders
    ADD CONSTRAINT orders_amount_minor_present
    CHECK (amount_minor IS NOT NULL) NOT VALID;

ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_minor_present;

ALTER TABLE orders
    ALTER COLUMN amount_minor SET NOT NULL;
~~~

Key behaviors:

- `CHECK ... NOT VALID` enforces rules on new writes before scanning the whole table, while `VALIDATE CONSTRAINT` verifies historical rows under PostgreSQL's locking rules.
- If any `NULL` remains, `VALIDATE` fails; **never fix it by substituting `0` without an approved business rule**.
- On some PostgreSQL versions, a validated `CHECK` allows `SET NOT NULL` to **skip a full rescan**; verify your DB version and lock behavior.
- Once `amount_minor` is `NOT NULL`, any writer or trigger path must guarantee a valid non-null value.

### Foreign-Key Tightening Also Requires Phased Rollout

For example, migrating text `orders.customer_ref` to `customer_id BIGINT` referencing `customers`:

1. Add nullable `customer_id` without removing `customer_ref`.
2. Build a **verified mapping** from old refs to target customers; never map unmatched refs to an arbitrary ID.
3. Sync new writes during transition.
4. Backfill in batches; route **unmappable/ambiguous** cases to a review queue.
5. Create supporting indexes and add the FK with minimal impact; PostgreSQL supports `ADD CONSTRAINT ... NOT VALID` followed by `VALIDATE CONSTRAINT` for FKs.
6. Switch queries/consumers; drop the legacy ref only once invariants hold.

In multi-tenant systems, an FK must never accidentally link a `customer_id` from another tenant. Key design may need **`(tenant_id, customer_id)`** or a proven globally unique identifier strategy.

## 9. Contract: Drop Legacy Structures Only After Proving Zero Usage

A checklist item saying "new app deployed" is **not enough** to drop `amount_cents`.

Before `contract`, verify:

- Every **app instance**, background worker, batch/cron, and ops tool no longer reads/writes the old field.
- No **mobile/desktop clients** directly depend on the old representation or endpoints returning it.
- ETL/CDC, BI, infrequent reports, views, stored procedures, triggers, and support tools are upgraded.
- No low-frequency jobs (weekly/monthly/quarterly) touch the old column.
- `amount_minor` is complete and semantically accurate; old–new diffs are **0 or policy-explained**.
- Restore/backfill procedures from older snapshots have been tested.
- Stop criteria, rollout timing, and incident ownership are established.

### 9.1. Removing the Bridge and Dropping the Old Column

Once **only the new app runs**, reverse sync to `amount_cents` is no longer needed:

~~~sql
BEGIN;

DROP TRIGGER IF EXISTS trg_sync_orders_amount ON orders;
DROP FUNCTION IF EXISTS sync_orders_amount();

ALTER TABLE orders
    DROP COLUMN amount_cents;

COMMIT;
~~~

This **breaks compatibility with A0**. Never run it while old writers/readers remain. In production, check dependencies in functions/triggers, views, constraints, permissions, and long-running transactions holding locks. PostgreSQL may require strong locks for `DROP COLUMN`; weigh lock waits and migration rollback limits.

**Dropping a column does not always reclaim disk space immediately.** On some engines, dropping column metadata does not rewrite physical pages right away; space reclamation is a separate operational plan.

### 9.2. Do Not Confuse Rollback With Restoring Legacy Data

Before `contract`, rollback can often just **point reads back to the old field** and halt rollout, provided sync stayed accurate.

After `DROP COLUMN amount_cents`, restarting the A0 binary will **likely fail**. If new values exceed `INTEGER` bounds, no lossless 1-to-1 reverse mapping to the old column exists. Therefore:

- Before `contract`, mark the **point of no simple rollback**.
- Past that point, recovery is **roll-forward** (patch A2/S2) or an approved restore from backup/snapshot plus post-snapshot transaction recovery.
- Never promise quick reversal via `ALTER TABLE ADD COLUMN amount_cents INTEGER`: re-adding a column does not restore lost data or contracts.

## 10. Deployment Ordering in Rolling and Multi-Version Systems

Under autoscaling or rolling deploys, **A0, A1, and A2** can coexist for minutes or hours. One release flow:

~~~mermaid
flowchart TD
    A["S0 + A0"] --> B["DB expands to S1"]
    B --> C["Sync mechanism compatible with legacy writers"]
    C --> D["Backfill and reconcile"]
    D --> E["A1 shadow-read / canary"]
    E --> F{"Gates passed?"}
    F -->|No| G["Halt rollout, fix and retry"]
    G --> D
    F -->|Yes| H["A2 reads/writes new"]
    H --> I["Observe all consumers and rollback window"]
    I --> J{"Zero old dependencies?"}
    J -->|No| I
    J -->|Yes| K["S2 contract old column"]
~~~

**Do not rely on informal pod-startup ordering.** Use explicit migration states, feature/capability flags if helpful, startup compatibility checks, and guards blocking incompatible deploys.

### Minimal Release Plan

| Release | Schema | Application | Expected Outcome |
|---|---|---|---|
| R0 | S0 | A0 | Baseline measured |
| R1 | S1 | A0 | New column exists; legacy app keeps running |
| R2 | S1 | A0/A1 | Sync and backfill; zero rising mismatches |
| R3 | S1 | A1/A2 | Reading new; rollback to old tested |
| R4 | S1 | A2 | Zero legacy dependencies remain |
| R5 | S2 | A2 | Approved cleanup of old structures |

The gap between R4 and R5 may span **days or longer** to cover periodic jobs, external consumers, and confirmed recovery windows. There is no universal "always drop columns after 24 hours" rule.

## 11. Renames, Splits, and Merges: Not Everything Maps Cleanly

### 11.1. Pure Rename

If `old_name` and `new_name` represent **the exact same concept**, expand–migrate–contract works as shown. The challenge is rarely the SQL rename—it is consumers bound to the old name.

**However:** if DB compatibility views or stable API serializers decouple contracts from physical column names, impact may be smaller. Avoid unnecessary bridges if existing abstraction layers already protect contracts.

### 11.2. Splitting a Free-Text Address

Source:

~~~text
shipping_address_text = "12 X Street, Ward Y, City Z"
~~~

New model:

~~~text
shipping_street
shipping_ward
shipping_city
shipping_country
~~~

**Never assume** every historical address parses accurately. Records lack components, use abbreviations, reflect renamed jurisdictions, include delivery notes, or follow mixed formats.

Proper plan:

1. Expand with new fields/tables carrying **`unverified` / `needs_review`** states as needed.
2. Confirm **intent**: shipping address at order time or customer's current address? Historical orders must not mutate with profile updates.
3. Backfill using a parser with measured confidence, storing mapping status and a review queue.
4. Never default missing `country` values or drop original strings when info is incomplete.
5. Tighten `NOT NULL`/FKs and drop old columns only once required data is verified or covered by exception policy.

This is a **semantic and structural** change, not a column rename.

### 11.3. Merging Two Fields Into One

If two fields store `first_name` and `last_name`, merging into `display_name` works for presentation, yet you cannot always **split it back accurately**. Rolling back from merged form to two fields can lose information. Identify **loss of invertibility** before `contract`.

### 11.4. Changing One-to-Many to Many-to-Many

Suppose `employees.department_id` allowed one department, and new rules allow multiple departments:

~~~text
employees(employee_id, department_id)  -- old

employee_departments(
    employee_id, department_id, effective_from, role
) -- new
~~~

During `expand`, create the join table and copy existing links. However, **reverse sync back into a single `department_id` cannot represent multiple departments**. You need a **feature-gating phase**: prevent users from assigning multiple departments until legacy readers/writers retire, or define an explicit "primary department" policy while noting nuances lost to the old column.

**A 1:N to M:N shift is usually a business-contract change**, not just a physical migration.

## 12. Evolving Tables and Analytical Models by the Same Principles

Expand–migrate–contract extends well beyond a single OLTP column.

### 12.1. Splitting One Large Table Into Two

Suppose `customers` holds core profile data plus unrelated notification preferences. To extract `customer_notification_preferences`:

- **Expand:** create the new table with proper keys/FKs while keeping old columns.
- **Migrate:** copy historical rows, sync changes, handle customers with no preferences yet.
- **Read cutover:** new queries/apps read the new table, handling `0/1` row semantics properly.
- **Contract:** drop old columns after consumers migrate.

Note: one customer may have multiple notification channels/purposes; define the new table's grain explicitly rather than turning a boolean column into rows lacking a `(customer_id, channel, purpose)` key when business requires it.

### 12.2. Moving From an Old Fact to a Different-Grain Fact

A data warehouse has order-level `fact_orders` and now needs line-level `fact_order_lines` for product analysis:

- **Never** backfill line items by evenly dividing `order_total` if source line data is missing.
- Pull from `order_items`, point-in-time unit prices, discounts, tax/shipping, and historical mappings.
- Both facts may **coexist**, serving KPIs at different grains; there is no need to "contract the order-level fact" if still used.
- Reconciling \(\sum\text{lineAmount}\) against order-level totals must account for **which components each KPI includes**.

**Changing grain is not a table rename.** Redefine keys, measures, and valid analytical questions.

### 12.3. SCD Type 2 and Dimension History

When evolving a current-state (Type 1) dimension to SCD Type 2:

1. Expand with `valid_from`, `valid_to`, and surrogate key/version.
2. Reconstruct history **from reliable event sources** if available; otherwise never fabricate non-existent history.
3. Point facts to the version key effective at business time.
4. Verify no two validity intervals overlap for the same business key.
5. Shift reports from "current attribute" to "attribute at event time" **only when the KPI definition truly changes**.

You do not always drop the Type 1 view; it can remain useful for "by current classification" questions.

## 13. APIs and Events: The DB Schema Is Not the Only Contract

A common mistake is finishing a DB migration and immediately renaming JSON responses or event payloads to match new column names.

~~~text
Internal DB changes
     |
     +--> API DTO / GraphQL schema
     +--> Integration event schema
     +--> CDC / ETL contract
     +--> BI semantic layer
     +--> Cache / search document
~~~

Each layer may have **different release cycles and owners**. If a public API still requires `amountCents`, the app can map DB `amount_minor` to the old API field until consumers migrate. Never force an API rename merely because a DB column was renamed.

### 13.1. Expand Contract for APIs

Example:

~~~json
{
  "orderId": "ord_42",
  "amountCents": 1200,
  "amountMinor": "1200",
  "currency": "USD"
}
~~~

This is **one transitional option**: old API consumers keep `amountCents`; new consumers read `amountMinor` as a string to avoid JSON numeric precision limits. Do not adopt it if security or complexity policies object. Contracts must specify **units, bounds, and field precedence** so consumers never sum both fields as separate amounts.

Often it is cleaner to **keep API v1 unchanged** and introduce explicit v2 rather than overloading one response with duplicate-meaning fields without strict rules.

### 13.2. Expand Contract for Integration Events

If `OrderConfirmed v1` carries an `INTEGER` amount, changing it to `BIGINT` or altering units can break consumers. Approaches:

- Publish **event schema v2** with new fields/types and documented mapping.
- Emit v1 during transition if required, ensuring consumers **do not process v1 and v2 as two separate business events**.
- Design consumers/upcasters to decode **historical v1 events** during replay.
- Distinguish event `schemaVersion` from order `aggregateVersion`.

**Never assume adding an optional field is always safe.** Strict consumers, protobuf schema registries, generated models, and exhaustive enums obey different rules. Verify via **consumer-driven contract tests** and actual compatibility direction.

### 13.3. CDC and Read Models

CDC tracking `orders` sees new columns appear and old columns vanish. When consumers depend on row-level schemas, physical column changes become **integration contract changes** even if APIs stayed flat.

Mitigations:

- Stable mapping layer translating CDC records into published events.
- Transactional outbox carrying explicitly versioned payloads.
- Upgrading schema registries/connectors in the right order.
- Backfilling new read models from a consistent snapshot, then applying CDC from a reliable **offset/watermark** so updates between snapshot and stream are not lost.

Never just "copy the table once and start CDC" without **time/offset boundary control**; in-flight writes during the copy can be missed or double-applied.

## 14. Backfilling Large Data in Live Systems

### 14.1. Throttling Load and Transactions

A safe backfill includes:

- Batch size tuned via measurements of I/O, CPU, WAL/redo, locks, and replication lag.
- **Rate limiting** and off-peak throttling windows when needed.
- Appropriate PostgreSQL `lock_timeout` / `statement_timeout`; avoid arbitrary timeouts that kill jobs without retry handling.
- Progress checkpoints or idempotent selectors for resuming.
- Monitoring dead tuples/bloat, vacuum/compaction, and backup impact.
- Ability to pause automatically when **latency or lag breaches thresholds**.

Never assume "500 rows per batch is always safe". Rows with huge payloads, multi-table triggers, or heavy indexes can cost far more than hundreds of small rows.

### 14.2. Cursor vs. Unmigrated Predicate?

Two common strategies:

| Strategy | Benefit | Risk |
|---|---|---|
| Scan by `order_id > last_id` | Simple progression, easy checkpoint | Low-ID rows inserted/updated behind the cursor can be missed without sync |
| Filter `WHERE new_column IS NULL` | Finds unmigrated rows directly; natural retry | Can scan expensively without a tailored index; misses **populated but wrong** values |
| Snapshot + CDC | Lowers impact when migrating between stores | Must track offsets, handle duplicates/out-of-order, and preserve consistency |

For `WHERE amount_minor IS NULL` at high scale, consider a temporary partial index:

~~~sql
-- PostgreSQL: must run outside a transaction block.
CREATE INDEX CONCURRENTLY idx_orders_amount_missing
    ON orders (order_id)
    WHERE amount_minor IS NULL;
~~~

Once backfill completes, this index is typically unneeded; clean it up separately:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_amount_missing;
~~~

**Never run `CREATE INDEX CONCURRENTLY` or `DROP INDEX CONCURRENTLY` inside a normal transaction block** in PostgreSQL. Concurrent index builds can fail and leave invalid indexes; inspect catalog state before retrying. Small tables or partitioned scans may not need a temporary index.

### 14.3. Late-Arriving Data and Concurrent Updates

In event- or outbox-driven systems:

- A row updated **after being backfilled** must update the new structure.
- Late-arriving old events must respect **versions/sequences/temporal semantics**, never unconditionally overwriting newer state.
- Concurrent edits on one row need locking, optimistic versioning, or appropriate transactions.
- Replay jobs must be **idempotent**: re-running must not inflate order counts or amounts.

`UPDATE ... WHERE amount_minor IS NULL` handles only **missing values**; it **cannot** fix rows already holding wrong values. Plan two distinct checks: **migrating missing rows** and **reconciling/repairing evidenced mismatches**.

## 15. Migrations Involving Constraints, Indexes, and Locks

Different changes demand specific engineering steps:

| Operation | Risk | Mitigation |
|---|---|---|
| Add nullable column | DDL locks; `SELECT *` shape changes | Deploy expand first; measure locks and clients |
| Add column with default/generated value | Possible table rewrite/locks depending on engine/version/expression | Verify DB version and physical execution plan |
| Create index on large table | I/O, locks, replication lag | Use online/concurrent index creation |
| Add `NOT NULL` | Table scan; fails on `NULL` rows | Backfill and validate beforehand |
| Add FK | Checks all links, locks, orphan rows | Index first and use `NOT VALID`/validate if supported |
| Change primary key type | FKs, indexes, replication, app IDs | Coexist old/new keys, mapping table, phased rollout |
| Change partition key | Large data movement | New table/partitions and controlled backfill/CDC |
| Drop column/table | Breaks old apps; hard rollback | Contract only after inventory and gates |

**"Online" DDL does not mean "zero locks, zero I/O, and zero downtime in every scenario".** Measure on the actual DBMS/version, transaction profile, indexes, and production-like load.

### Sequencing Constraints

When adding foreign keys or uniqueness:

1. Clean historical data and confirm business rules.
2. Build supporting indexes if needed.
3. Start enforcing on new writes.
4. Validate historical data.
5. Expand enforcement scope and finally retire old logic.

If users can submit invalid data during backfill, block bad writes **before** verification completes—otherwise migration chases a moving target forever.

## 16. Phase Gates: What to Measure Before Proceeding?

A migration plan should define **pass/fail criteria**, not just a target date to drop a column.

| Gate | Evidence / Metric | If Not Met |
|---|---|---|
| **Expand compatible** | A0 reads/writes cleanly on S1; schema deployed cleanly | Halt new app rollout |
| **Writer sync** | Zero writer bypasses; new drift not rising | Fix bridge / app writer |
| **Backfill** | `NULL` count dropping; checkpoints advancing | Tune batch/index; triage errors |
| **Correctness** | Row-level mismatches = 0 or exceptions explained | Do not switch reads |
| **Canary** | Business outputs, latency, error rates within SLO | Revert reads to old; investigate |
| **New-only** | All consumers use new model; zero legacy accesses | Hold contract |
| **Recovery** | Restore/replay/backfill rehearsed; rollback/roll-forward clear | Delay contract |

### Sample Operational Metrics

~~~text
migration_rows_total
migration_rows_remaining
migration_rows_processed_per_minute
migration_mismatch_rows
migration_backfill_errors_total
migration_batch_duration_seconds
migration_db_lock_wait_seconds
migration_replication_lag_seconds
migration_old_column_reads
migration_old_column_writes
migration_new_read_errors
migration_cutover_rollback_count
~~~

Not every engine can count individual column reads directly in the DB layer. You may need **app instrumentation, query log analysis, metadata dependency checks, or selective logging**. Seeing `old_column_reads = 0` for a few minutes does not prove a monthly job has migrated.

### Meaningful Scope Reconciliation

Beyond row-by-row diffs:

- Reconcile `COUNT(*)` by tenant/date/partition.
- Reconcile monetary sums in matching currencies and KPI definitions.
- Verify keys, FKs, uniqueness, and `NULL` handling.
- Test edge values: `0`, huge numbers, ancient rows, rows edited mid-backfill.
- Verify infrequent consumers: month-end exports, restores, admin tools, email jobs.

Require **recorded test evidence**, not merely a ticked "done" checkbox.

## 17. Rollback, Roll-Forward, and Points of No Easy Return

### Before Contract

While the old column stays accurately synced, if a canary fails you can:

- Flip the read feature flag back to `amount_cents`.
- Halt A2 rollout, stay on S1, and fix mapping logic.
- Resolve mismatches/backfill while users continue reading the legacy structure.

**Never roll back the `expand` DDL** once new app instances reference the new column; that makes failures worse.

### After Contract

Once `amount_cents` is dropped:

- A0 binaries no longer work against S2.
- New values may exceed `INTEGER`, preventing lossless reversal into the old column.
- Full DB restore risks losing **transactions committed after the snapshot** without replay/recovery tooling.

Thus recovery is typically **roll-forward**: patch A2/S2. If reverting to the old model is truly required, prepare an approved **reversible migration with sufficient source data**, downtime window, snapshots, and post-snapshot reconciliation **before `contract`**, never improvised after an incident.

### Irreversible Data Migrations

Suppose `free_text_address` is parsed into structured fields and the raw text is dropped, discarding `"near back gate, call before delivery"`. No SQL rename can recreate that text. That is **information loss**, fundamentally different from widening `INTEGER` to `BIGINT`.

Every `contract` decision must evaluate:

\[
\text{Can the old representation be reconstructed from the new representation?}
\]

If not, **retain originals per policy**, obtain explicit sign-off on data loss, or redesign the plan.

## 18. Comparison Across Data Models

| Model | Expand | Migrate | Contract | Special Considerations |
|---|---|---|---|---|
| **Relational** | Add columns/tables/FKs/indexes | Dual-write, backfill, switch JOINs | Drop old columns/tables | DDL locks, constraints, MVCC, transactions |
| **Document** | Add new fields/schema version | Dual-read/mapping, backfill docs | Drop old fields after readers switch | Old/new docs coexist long-term |
| **Graph** | Add node/edge types/properties | Migrate old relations to new types | Delete old edges/properties | Lost/multiplied paths, shifting relation semantics |
| **Analytics** | Build new facts/dimensions, version metrics | Backfill by grain/time, switch dashboards | Retire old marts/views | History, SCDs, distinct counts, fanout, period close |
| **Event streaming** | Publish v2 schema/events alongside v1 | Consumers/upcasters, replay, offset cutover | Retire v1 per policy | v1 events persist in logs/backups for years |

### Document Databases

If an old document is:

~~~json
{ "orderId": "O1", "amountCents": 1200 }
~~~

and the new document is:

~~~json
{ "orderId": "O1", "amountMinor": "1200", "schemaVersion": 2 }
~~~

readers during transition must understand **both versions**, or a backfill must finish before readers switch to v2-only. Never assume every document updates at once. Without version checks, stale cached/restored documents can overwrite migrated ones.

### Graph Databases

Moving from `(User)-[:MEMBER_OF]->(Team)` to a temporal `Membership` model requires checking:

- How many membership records correspond to one legacy edge?
- Can `effective_from`/roles be derived from legacy data?
- While both representations coexist, do queries **double-count relationships**?
- Before deleting old edges, have all path queries and authorization checks updated?

Expanding a graph without updating traversal queries corrupts answers even when every node and edge is valid.

### Analytics

A dashboard metric `totalRevenue` built on an old fact must not silently switch to a new fact with a **different revenue definition** under the same KPI label. Run both metrics in parallel, reconcile by date/tenant, and announce the cutover date. When grain shifts, redesign `SUM`, `COUNT(DISTINCT)`, and dimension joins.

## 19. Common Misconceptions

| Misconception | Why It Is Dangerous | Better Approach |
|---|---|---|
| "Column rename is fast so it's always safe" | Old apps, ETL, or views still use the old name | Expand first; inventory consumers |
| "Nullable new column needs no sync" | Post-backfill, A0 writes only to the old column | Sync bridge/dual-write before read cutover |
| "`COALESCE` prevents all read errors" | New column can hold **stale non-null** values | Reconcile mismatches and sync properly |
| "Dual-write to two DBs is atomic" | One succeeds while the other fails | Outbox/CDC, idempotency, reconciliation |
| "Changing `INTEGER` to `BIGINT` finishes the job" | DTOs/JSON/clients may still clamp to 32-bit `int` | End-to-end compatibility matrix |
| "One backfill pass is enough" | Concurrent updates and late events arrive | Sync, replay, and post-backfill checks |
| "Matching totals prove every row matches" | Offsetting errors cancel out | Check row-level diffs and partitions |
| "Add `NOT NULL` first, update rows later" | Historical `NULL`s fail immediately | Migrate data first, validate, then enforce |
| "`CREATE INDEX CONCURRENTLY` has zero impact" | Still consumes CPU/I/O and can fail | Monitor progress, load, and index state |
| "Drop old column once new app deploys" | Crons/BI/mobile/restores still rely on it | Inventory and pass contract gate |
| "Toggling off the feature flag rolls back schema" | Column already dropped or info lost | Track irreversible point |
| "Free-text splitting is 100% automatic" | Legacy text is ambiguous or incomplete | Mapping, confidence tiers, manual review |
| "New column is source of truth right after `ADD COLUMN`" | Not yet backfilled or synced | Cut over only after correctness gate |
| "DB schema change forces API/event rename" | Breaks consumer contracts | Map and version layers independently |
| "Shadow-read logs need no data protection" | Comparison logs can leak PII | Log only minimal metrics/reference IDs |
| "Every migration requires triggers" | Triggers add overhead and complexity | Prefer app dual-write when viable |

## 20. Practice Exercises With Solutions

### Exercise 1 — Identify the Phases

A system has `orders.amount_cents`; the team wants `amount_minor`. Assign adding the column, backfilling, and dropping the old column to the three phases.

**Solution:** **Expand:** add nullable `amount_minor`, keep the old column and sync mechanism. **Migrate:** backfill, reconcile, gradually roll out new reads/writes. **Contract:** remove sync and drop `amount_cents` once zero legacy consumers remain.

### Exercise 2 — Why Does `COALESCE` Still Return Wrong Data?

Before backfill: `amount_cents = 1000`, `amount_minor = NULL`. After backfill, both equal `1000`. Legacy app updates `amount_cents = 1200` without updating the new column. What does `COALESCE(amount_minor, amount_cents)` return?

**Solution:** It returns **`1000`**, which is **wrong**, because `amount_minor` is non-null yet stale. Sync every writer before switching reads; `NULL` fallback does not fix stale values.

### Exercise 3 — Compatibility Matrix

A0 reads only `amount_cents`, A2 reads only `amount_minor`. S0 has only the old column, S2 has only the new column. Can A0 run on S2? Can A2 run on S0?

**Solution:** **No** in both cases under these assumptions. You need intermediate state S1 with both columns, ordered deployment, and `contract` only after A0 stops.

### Exercise 4 — Interrupted Backfill

A job updates 500 rows per transaction using `WHERE amount_minor IS NULL`. One transaction is killed before commit. How do you resume?

**Solution:** Uncommitted transactions roll back; re-running the batch re-selects rows still `NULL`. Monitor backlog, retries, and throttling. Idempotency does not replace checking for **populated but wrong** values.

### Exercise 5 — Enabling `BIGINT` Values Too Early

A0 still uses 32-bit `int`; A2 wants to write `amount_minor = 3,000,000,000`. Sync to `amount_cents INTEGER` is still active. Is this allowed?

**Solution:** **No** while syncing with A0; the value exceeds the signed 32-bit max `2,147,483,647`. Retire legacy dependencies and upgrade DTOs/APIs/ETL before lifting the bound.

### Exercise 6 — Verifying `NULL`s and Mismatches

After backfill, `COUNT(*) WHERE amount_minor IS NULL` returns `0`, yet 10 rows have `amount_minor <> amount_cents`. Has the correctness gate passed?

**Solution:** **No.** Zero `NULL`s proves only completeness, not accuracy. Reconcile row-by-row with `IS DISTINCT FROM` and fix root causes before read cutover.

### Exercise 7 — Address Splitting

From free-text addresses, the team wants `street, ward, city, country` and `NOT NULL` right after parsing. 5% of addresses fail reliable parsing. What should you do?

**Solution:** Preserve original text per policy, mark unverified records, and route to review/enrichment. Never invent fake defaults or force `NOT NULL` when required fields lack evidence.

### Exercise 8 — From One Department to Many

Legacy `employees.department_id` holds one value. The new model supports multiple departments via a join table. Can you enable multi-department creation while old apps still read a single `department_id`?

**Solution:** Not unconditionally. One column cannot represent many-to-many; gate the multi-department feature until old clients upgrade, or define an explicit "primary department" with clear boundaries and no silent semantic loss.

### Exercise 9 — Joining Two Facts

Line-item fact has 3 rows/order; payment fact has 2 transactions/order. A team directly joins both facts to reconcile before contracting the old fact. What happens?

**Solution:** The join produces **6 rows**, multiplying monetary amounts. Aggregate each fact to **order grain** first, then join. Analytics migrations must preserve grain and measure definitions, not just column names.

### Exercise 10 — API Contracts and DB Refactoring

DB renamed `amount_cents` to `amount_minor`, yet partners still read JSON `amountCents`. Must JSON change immediately?

**Solution:** No. The API layer can keep mapping to the valid v1 contract while values, units, and bounds remain compatible. When widening ranges or changing types, publish v2 with a verified compatibility plan.

### Exercise 11 — Infrequent Consumers

No production web requests read the old column for a week. However, a quarterly reconciliation report still uses `amount_cents`. Can you run `contract`?

**Solution:** **No** if the report still needs to run. Runtime request metrics miss rare batch jobs. Inventory consumers, upgrade and test the report, and prove zero dependencies remain.

### Exercise 12 — Rollback After `DROP`

`amount_cents` was dropped; the new column now holds values exceeding `INTEGER`. An operator wants to restart A0 and re-add `amount_cents` to roll back.

**Solution:** Not a safe rollback. A0 does not understand the new schema, and values exceeding old bounds cannot restore cleanly. Use roll-forward or an approved restore plan accounting for post-snapshot data.

## 21. Pre-Execution Checklist for Expand–Migrate–Contract

- [ ] Verified **business semantics** of old and new fields/tables, money units, time semantics, and grain.
- [ ] Mapped **compatibility matrix** across schema/app/API/event/ETL/BI and deployment order.
- [ ] Inventoried infrequent consumers, mobile clients, batches, backup/restore, and CDC.
- [ ] **Expand** does not break old apps; no premature drop/rename or unsafe `NOT NULL`.
- [ ] Selected one explicit write-sync mechanism: **app dual-write, DB trigger, or reconciled outbox/CDC**.
- [ ] Proved **no stale non-null** values when using fallback reads.
- [ ] New and old data preserve keys, namespaces, constraints, and scoped history.
- [ ] Batched backfill has retries/idempotency, throttling, checkpoints, and late-data handling.
- [ ] Checks cover `NULL`s, row-level diffs, row counts, scoped sums, and edge values.
- [ ] Planned gradual tightening of `CHECK`, `NOT NULL`, FKs, and indexes per actual DBMS behavior.
- [ ] Canary/shadow reads track correctness, latency, errors, and log privacy.
- [ ] Monitored replication lag, WAL/redo, lock waits, CPU/I/O, and bloat during migration.
- [ ] API/event contracts governed **independently of DB column names**, with schema versions and consumer tests.
- [ ] Confirmed zero old writers/readers before **contract**.
- [ ] Identified the **point of no simple rollback**, roll-forward strategy, and rehearsed restore/replay.
- [ ] Defined explicit gates per phase; never proceed merely because a cleanup calendar date arrived.
- [ ] Lossy or unmappable transformations have exception workflows and business sign-off.

**Key takeaway:** **Expand first to allow coexistence, migrate in verifiable batches to shift data and traffic, and contract only once zero legacy dependencies remain.** A migration is never just `ALTER TABLE`—it is a coordinated transition across **schema, applications, data, APIs/events, operations, and recoverability**. Good designs preserve semantics and keys while both representations coexist, requiring **reconciliation proof and a compatibility matrix** before retiring old structures.
