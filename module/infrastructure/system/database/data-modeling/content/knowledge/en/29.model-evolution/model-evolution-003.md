# Schema Versioning and Managing Intermediate Deployment States

## Learning Objectives

A database schema change is rarely just a single **`ALTER TABLE`** statement. In a live system serving users, **multiple application versions**, unmigrated legacy data, sync jobs still reading legacy structures, and messages emitted prior to deployment can all coexist. Consequently, a data model must be designed to **evolve through valid intermediate states**, not merely describe the before and after states.

This lesson belongs to the **Model Evolution** chapter of the **DATABASE_DATA_MODELING** module. The module's goal is to turn business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical structures to produce evolvable and verifiable designs. The specific topic here is **schema versioning and managing intermediate deployment states**.

After this lesson, you will be able to:

1. Distinguish **schema version**, **application version**, **API/event contract version**, and **data migration state**.
2. Explain why a **migration running successfully** is not enough to prove a release is compatible.
3. Design an **expand → migrate/backfill → switch → contract** sequence with intermediate states, phase-gate criteria, and recovery capability.
4. Build a **compatibility matrix** across old/new application versions and pre-/post-expand schemas.
5. Use PostgreSQL to demonstrate safely renaming a column during a **rolling deployment**, including **dual-column synchronization**, backfill, verification, and timely removal of the legacy column.
6. Analyze risks from **dual-writes, concurrency, late-arriving data, indexes, new constraints, DDL locks, and long-running migrations**.
7. Distinguish **application rollback**, **schema rollback**, **forward fix**, and **data recovery**; understand why not every change is reversible.
8. Propose tests, telemetry, checklists, and **go/no-go** criteria for each phase of data model rollout.

> **Scope:** Examples use PostgreSQL and Java/JDBC illustratively. This is a design and migration-process guide, **not an automated deployment tool**. Every SQL statement must be reviewed against your PostgreSQL version, permissions, data size, workload, and operational mechanics before running in production.

## 1. Why Must Data Models Evolve in Phases?

### 1.1. Envisioning a Small Change

Suppose an orders table previously stored contact email in column **`customer_email`**. After business clarification, the team wants to rename it to **`buyer_email`** because it is **a snapshot of the buyer's email at order placement time**, not the current email on the customer profile.

The assumption approved by both teams in this example is:

> Legacy `customer_email` and new `buyer_email` share the **same value semantics for existing records**; this change only makes the field name more accurate and does **not** alter the contact person, access permissions, or snapshot timing.

If the actual change were from "customer's email" to "recipient's email", it would **no longer be a pure rename**. You could not mechanically backfill from the old column without verifying source data.

A direct statement:

~~~~sql
-- DO NOT run this immediately if any application still reads customer_email.
ALTER TABLE sales_order RENAME COLUMN customer_email TO buyer_email;
~~~~

may execute very quickly in the database, yet cause old applications sending:

~~~~sql
SELECT customer_email FROM sales_order;
~~~~

to fail with **column does not exist**. The problem is not invalid migration SQL, but unmanaged **coupling between the timing of schema changes and application changes**.

### 1.2. Versions That Can Coexist Concurrently

During rollout, there may be:

- **A0 — Old application:** reads/writes `customer_email`.
- **A1 — Transitional compatible application:** knows both fields and follows agreed read/write rules.
- **A2 — New application:** needs only `buyer_email`.
- **S0 — Old schema:** only `customer_email`.
- **S1 — Expanded schema:** has both `customer_email` and `buyer_email`.
- **S2 — Reconciled schema:** both fields hold matching data, all write paths stay in sync.
- **S3 — Contracted schema:** only `buyer_email`.

**A0, A1, A2** are running code versions, while **S0–S3** are schema and data states. They are not interchangeable version numbers. An app deploy may not change the schema; a backfill may change data state without altering any table definition.

### 1.3. "Zero-Downtime Deployment" Does Not Mean Zero Locks or Zero Risk

The concept of **zero-downtime migration** aims to **avoid stopping the whole service to change the schema**. However:

- Some DDL statements still take table locks, even if execution itself is brief.
- Lock waits can block other incoming requests.
- Backfills can raise I/O load, WAL volume, replication lag, and bloat.
- Multiple app versions can write inconsistent data without a synchronization mechanism.
- Infrequent consumers or scheduled jobs may still depend on the old column.

Thus, "safe to deploy" is a **set of verifiable criteria**, not a label attached to one SQL statement.

## 2. Different Kinds of Versions

### 2.1. Physical Schema Version

A schema version tracks which DDL migrations have been applied, for example:

~~~~text
V001__create_sales_order.sql
V002__add_buyer_email.sql
V003__add_email_constraint.sql
V004__drop_customer_email.sql
~~~~

These are **illustrative migration filenames**, not a requirement to use any specific tool. Tools like Flyway or Liquibase track migration history; if used, follow the exact conventions of that tool and version.

A migration history record typically captures:

| Component | Meaning |
| --- | --- |
| **Migration identifier** | Uniquely identifies the change step |
| **Order/dependencies** | Which step must precede another |
| **Checksum/content** | Detects edits to previously applied scripts |
| **Applied timestamp** | Audits which environments ran which steps |
| **Outcome** | Succeeded, failed, or requires manual recovery |
| **Actor/pipeline** | Change ownership and auditability |

**Never arbitrarily edit a released migration** expecting the database to infer a new version. For follow-up changes, create a new migration with explicit ordering and rationale, unless the team has a formal process for unapplied history.

### 2.2. Logical and Semantic Contract Version

A schema might keep column **`amount NUMERIC(18,2)`** while the team changes its interpretation from **VND** to **minor currency units**. DDL did not change, yet **the data contract changed drastically**.

Components needing versioning or compatibility governance:

- Column semantics, units of measure, nullability, and value domains.
- Fact grain or business keys.
- Status and lifecycle rules.
- API requests/responses.
- Event payloads, event types, `schemaVersion`, and event semantics.
- Projections/read models, reports, and out-of-band database jobs.

**Physical schema versioning does not replace contract versioning.** A system may be at migration `V004` yet still need to handle event schema v1 when older messages are replayed.

### 2.3. Data Version

Data can sit at various transition stages:

~~~~text
Unmigrated:
  customer_email populated, buyer_email = NULL

Migrating:
  some rows have buyer_email, some do not

Migrated:
  buyer_email populated and matches mapping rules

Cutting over:
  app reads the new field while still guarding updates from old versions
~~~~

A successful `ALTER TABLE ADD COLUMN` does **not** mean all rows are backfilled. A completed backfill script also does **not** prove new and old values stay aligned while apps keep writing.

### 2.4. Application Versions and Write Flows

A rolling-update system may simultaneously run:

~~~~text
3 instances of A0 (read/write customer_email)
2 instances of A1 (read/write buyer_email, old-column compatible)
1 legacy reporting worker (scheduled SELECT customer_email)
1 event v1 consumer (reads payload field customerEmail)
~~~~

Healthy new containers or a passing API request are insufficient to conclude **every legacy read/write path is gone**. Before `contract`, inventory **scheduled jobs, internal CLIs, exports, BI, stream consumers, replica readers, and partner integrations**.

## 3. Compatibility Matrix Before Changing Schema

For the column-rename example, build a matrix:

| Application / Schema | S0: `customer_email` only | S1: both columns, synced | S3: `buyer_email` only |
| --- | --- | --- | --- |
| **A0: `customer_email` only** | **Compatible** | **Compatible** if sync and constraints still serve A0 | **Incompatible** |
| **A1: reads new with fallback, transitional writes** | **Only if fallback and write path are designed for S0** | **Target compatible** | **Only if A1 code no longer references old column** |
| **A2: `buyer_email` only** | **Incompatible** | **Compatible** once new column and data are ready | **Compatible** |

A "fallback reader" app that **always INSERTs `buyer_email`** cannot run on S0 because S0 lacks that column. An app that "reads new with fallback" yet `UPDATE`s both columns in every transaction is **incompatible with S3** once `customer_email` is dropped. **The matrix must reflect the actual SQL of each build**, not just team-assigned version names.

### 3.1. Rules to Avoid Breaking Running Versions

A safe schema transition typically ensures:

1. **Expand the schema first** before releasing code that requires the new structure.
2. Run a compatibility phase whenever **A0 and A1/A2 coexist**.
3. Drop the old field only when **no consumer still needs it**.
4. If code rollback to A0 may be needed, **do not drop the old column yet**.

This deployment sequence has **logical dependencies**. It cannot be bypassed by bundling all SQL into one transaction.

### 3.2. Backward and Forward Compatibility

In data systems:

- **Backward compatibility:** the new version accepts data/schemas or contracts produced by the old version within the committed scope.
- **Forward compatibility:** the old version still tolerates changes produced by the new side within the designed scope.

For instance, adding a **nullable column** rarely breaks old apps using explicit column lists. Yet an app using **`SELECT *`** with positional column binding or column-count serialization can still break. Adding an enum value to a table can also break a consumer using a switch without a default branch. **Never assume compatibility solely because DDL "only adds a column".**

## 4. Expand – Migrate – Switch – Contract

The **expand–contract** pattern splits an incompatible change into stages. For existing data, it is usually clearest to distinguish **migrate/backfill** and **switch/cutover**.

### 4.1. Four Phases and Intermediate States

| Phase | Schema/Data | Application | Completion Criteria |
| --- | --- | --- | --- |
| **1. Expand** | Add new structure; keep old structure intact | A0 still operates | Change does not break A0; sync path exists if dual-writing |
| **2. Migrate** | Backfill, verify historical and new data | A0/A1 may coexist | Zero unmigrated rows or contract mismatches |
| **3. Switch** | Both old and new structures remain guarded | Shift primary reads/writes to A2 | Metrics, errors, accuracy, and legacy write paths controlled |
| **4. Contract** | Remove old column/constraints/sync path | Only new-compatible code/consumers remain | Rollback window closed; zero legacy dependencies |

**Expand is not "done before data arrives":** if writes occur during backfill, design how **both representations stay in sync** or establish a verifiable write-cutover boundary.

### 4.2. Deployment State Diagram

~~~~mermaid
stateDiagram-v2
    [*] --> S0: Legacy schema and code
    S0 --> S1: Expand + compatibility guard
    S1 --> S2: Backfill + reconcile
    S2 --> S2: Retry batch / re-verify
    S2 --> S3: Switch readers/writers
    S3 --> S3: Monitor + wait for rollback window end
    S3 --> S4: Contract drop old column
    S4 --> [*]

    S1 --> S0: Only if no data depends on new structure
    S3 --> S2: Roll back app while old column still exists
~~~~

Return arrows are **conditional capabilities**, not promises that a `DOWN` migration is always safe. If the new phase produced data the old version cannot interpret, rolling back may require a **forward fix, compatibility adapter, or extra data cleanup**, even while the old column still exists.

### 4.3. Per-Phase Invariants

| Phase | Invariant to Maintain |
| --- | --- |
| S0 | Every A0 write/read is valid on legacy schema |
| S1 | A0 continues working; if both columns accept writes, they must never silently diverge |
| S2 | Every in-scope record has a verifiable old–new mapping |
| S3 | A2 fully reads/writes new data; old data remains ready throughout the rollback window |
| S4 | Zero A0 consumers remain; all target constraints and data are enforced |

**No undefined "in-between state":** every phase needs **entry criteria, exit criteria, an owner, and observable data**. If a step fails, the team must know which phase the system is in and which operations are safe to retry.

### 4.4. Not All Migration Paths Look Alike

Under the same "expand–contract" umbrella, tactics vary by transformation:

- **Adding a column:** add nullable or meaningful default, backfill, update code, tighten `NOT NULL`.
- **Renaming a column:** keep both columns, sync, switch reads/writes, drop old column.
- **Splitting one column into many:** not all new values may be inferable; define policy for ambiguous cases.
- **Merging tables:** reconcile keys, cardinality, duplicates, and ownership.
- **Splitting a table:** dual-read/dual-write or projections with a clear source of truth to prevent unsynced edits on both sides.
- **Changing money type/unit:** define exact conversion and prevent precision/range loss.
- **Adding `UNIQUE`/`FK`/`NOT NULL`:** clean legacy data and prevent new violations during validation.

An `ALTER TABLE` statement alone does not define **how data and application versions coexist** during transition.

## 5. End-to-End PostgreSQL Example: Renaming a Column in a Live Write System

We walk through a **self-contained scenario on a test database**. Table/function names use the **`_demo`** suffix to emphasize this is an educational sample. Assumptions:

- Legacy **`customer_email`** and new **`buyer_email`** share the meaning **buyer email at order creation time**.
- Each order row stores one required email per example policy; input format is validated at the application layer.
- **Application A0 writing only `customer_email`** and **A2 writing only `buyer_email`** may coexist during transition.
- Applications stay online; we want gradual rollout without requiring all instances to upgrade simultaneously.

### 5.1. S0 — Legacy Schema and Data

~~~~sql
CREATE TABLE sales_order_demo (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO sales_order_demo (customer_email)
VALUES
    ('an@example.org'),
    ('binh@example.org'),
    ('chi@example.org');

SELECT order_id, customer_email
FROM sales_order_demo
ORDER BY order_id;
~~~~

At S0, legacy apps read/write `customer_email`; `buyer_email` does not exist. The goal is changing **field name and contract**, not altering historical snapshotted emails. If source values contain bad data, that is a separate cleanup task with its own criteria—never mask it under a rename.

### 5.2. S1 — Expand: Add New Column Without Dropping Old

~~~~sql
ALTER TABLE sales_order_demo
ADD COLUMN buyer_email TEXT;
~~~~

**Why allow `NULL` initially?** Existing rows do not yet have values in the new column; enforcing `NOT NULL` immediately without valid values for every row and write path would block legacy data or A0.

After this step, the normal state is:

| order_id | customer_email | buyer_email |
| ---: | --- | --- |
| 1 | an@example.org | NULL |
| 2 | binh@example.org | NULL |
| 3 | chi@example.org | NULL |

**`NULL` in a transitional state does not mean `NULL` is allowed in the target model.** We temporarily widen the schema to migrate data, then tighten invariants.

### 5.3. Why Asking Only the New App to Dual-Write Fails

Suppose A2 writes **both `customer_email` and `buyer_email`**, while A0 still writes only `customer_email`. After backfill, A0 might update `customer_email` leaving `buyer_email` stale. If A2 reads `buyer_email`, the two versions observe **different values**.

That is why **"one-time backfill + dual-write in new app"** is insufficient when **legacy writers remain**. You need one of:

- **Database-level synchronization** during transition, such as a carefully designed and tested trigger.
- **Upgrading all writers to a compatible version** before writing to the new field, with verification that no A0 remains.
- **Coordinating/blocking write-authority switchover** in a bounded window if that disruption is acceptable.

This example uses a **transitional trigger** so A0 and A2 can coexist. Triggers are not mandatory everywhere; they add complexity, write overhead, and monitoring duties, so they must be removed at `contract`.

### 5.4. Setting Up a Two-Column Sync Bridge

First, create the PostgreSQL trigger function handling:

- **INSERT:** if only one email is provided, copy to the other; if both differ, reject.
- **UPDATE old column:** new column follows the updated value.
- **UPDATE new column:** old column follows the updated value.
- **UPDATE both with conflicting values:** reject.
- **UPDATE an unbackfilled row on unrelated columns:** fill the new column from the old value if still missing.

~~~~sql
CREATE OR REPLACE FUNCTION sync_sales_order_email_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.customer_email IS NOT NULL
           AND NEW.buyer_email IS NOT NULL
           AND NEW.customer_email IS DISTINCT FROM NEW.buyer_email THEN
            RAISE EXCEPTION
                'Conflicting old/new email on INSERT';
        END IF;

        NEW.customer_email :=
            COALESCE(NEW.customer_email, NEW.buyer_email);
        NEW.buyer_email := NEW.customer_email;

    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.customer_email IS DISTINCT FROM OLD.customer_email
           AND NEW.buyer_email IS DISTINCT FROM OLD.buyer_email
           AND NEW.customer_email IS DISTINCT FROM NEW.buyer_email THEN
            RAISE EXCEPTION
                'Conflicting old/new email on UPDATE';

        ELSIF NEW.customer_email IS DISTINCT FROM OLD.customer_email THEN
            -- Legacy writer modified the old field.
            NEW.buyer_email := NEW.customer_email;

        ELSIF NEW.buyer_email IS DISTINCT FROM OLD.buyer_email THEN
            -- New writer modified the new field.
            NEW.customer_email := NEW.buyer_email;

        ELSIF NEW.buyer_email IS NULL THEN
            -- An unbackfilled legacy row is being updated.
            NEW.buyer_email := NEW.customer_email;

        ELSIF NEW.customer_email IS DISTINCT FROM NEW.buyer_email THEN
            RAISE EXCEPTION
                'Inconsistent old/new email in an existing row';
        END IF;
    END IF;

    IF NEW.customer_email IS NULL OR NEW.buyer_email IS NULL THEN
        RAISE EXCEPTION
            'Both old and new email must be present after synchronization';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_sync_sales_order_email_demo
BEFORE INSERT OR UPDATE
ON sales_order_demo
FOR EACH ROW
EXECUTE FUNCTION sync_sales_order_email_demo();
~~~~

**Why is a `BEFORE` trigger essential?** On an A2 `INSERT` providing only `buyer_email`, the trigger runs before PostgreSQL checks `NOT NULL` on `customer_email`, allowing it to populate a valid `customer_email`. An `AFTER` trigger would fail the `NOT NULL` constraint before sync could run.

**Technical warning:** This trigger illustrates **two columns with identical semantics**. It does not resolve all business conflicts. Two transactions editing different emails from stale reads can still cause a **lost update** under last-write-wins; preventing that requires **optimistic locking with a version column**, conditional updates, or conflict resolution protocols. Privileged writers bypassing triggers, special replication modes, and admin operations must also be governed. Never use a trigger to "sync two different meanings" like list price and locked order price.

### 5.5. S2 — Backfill Legacy Data Without Blocking All Writes

On a small test set:

~~~~sql
UPDATE sales_order_demo
SET buyer_email = customer_email
WHERE buyer_email IS NULL;
~~~~

In production on millions of rows, a **single `UPDATE`** holds long transactions, generates heavy WAL, causes bloat, adds replica lag, or triggers lock contention. Prefer **small-batch backfills**, rate limiting, progress checkpoints, and load observation.

A batch selection query can use:

~~~~sql
WITH batch AS (
    SELECT order_id
    FROM sales_order_demo
    WHERE buyer_email IS NULL
    ORDER BY order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE sales_order_demo AS o
SET buyer_email = o.customer_email
FROM batch
WHERE o.order_id = batch.order_id
RETURNING o.order_id;
~~~~

A real worker executes batches in **controlled transactions**, pauses/throttles under load, logs progress, and stops when no rows remain. This SQL is **one batch**; it does not provide scheduling, retries, checkpoints, or operational dashboards by itself.

**Idempotency:** Filtering `buyer_email IS NULL` prevents re-runs from overwriting completed rows. However, if **non-null conflicting values** exist, you must **detect and resolve conflicts** rather than assuming completion just because both columns are populated.

### 5.6. Testing Old and New Writers While Sync Bridge Is Active

After installing the trigger and backfilling, run:

~~~~sql
-- A0: writes via legacy interface.
UPDATE sales_order_demo
SET customer_email = 'an.new@example.org'
WHERE order_id = 1;

-- A2: writes via new interface.
UPDATE sales_order_demo
SET buyer_email = 'binh.new@example.org'
WHERE order_id = 2;

-- A2: INSERT using only the new field.
INSERT INTO sales_order_demo (buyer_email)
VALUES ('dung@example.org');

SELECT order_id, customer_email, buyer_email
FROM sales_order_demo
ORDER BY order_id;
~~~~

Expected result (`order_id` assigned by identity):

| order_id | customer_email | buyer_email |
| ---: | --- | --- |
| 1 | an.new@example.org | an.new@example.org |
| 2 | binh.new@example.org | binh.new@example.org |
| 3 | chi@example.org | chi@example.org |
| 4 | dung@example.org | dung@example.org |

**Intentional negative test** confirming conflicting values are rejected:

~~~~sql
-- Expected RAISE EXCEPTION from trigger; run separately in a test environment.
UPDATE sales_order_demo
SET customer_email = 'one@example.org',
    buyer_email = 'two@example.org'
WHERE order_id = 1;
~~~~

Exact behavior depends on both columns actually changing relative to `OLD`; on the sample data both changed to different values so the trigger rejects it. Never put an intentional error statement inside a migration that must commit cleanly.

### 5.7. Verifying Target Data Before Switching Readers

~~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE buyer_email IS NULL) AS missing_new,
    COUNT(*) FILTER (
        WHERE buyer_email IS DISTINCT FROM customer_email
    ) AS mismatched
FROM sales_order_demo;
~~~~

**Minimum pre-cutover condition** in this example: `missing_new = 0` and `mismatched = 0` across the entire scope while active write traffic remains in sync. Re-verify after live write load, not only right after backfill finishes.

A quality check must never **equate row counts with correctness**. Two columns with identical non-null counts holding different emails still violate the contract.

### 5.8. Tightening New Constraints Step by Step

Once data is consistent, add a `buyer_email` non-null check:

~~~~sql
ALTER TABLE sales_order_demo
ADD CONSTRAINT ck_buyer_email_present_demo
CHECK (buyer_email IS NOT NULL) NOT VALID;

ALTER TABLE sales_order_demo
VALIDATE CONSTRAINT ck_buyer_email_present_demo;

ALTER TABLE sales_order_demo
ALTER COLUMN buyer_email SET NOT NULL;
~~~~

**Step explanation:**

- Adding `CHECK ... NOT VALID` avoids scanning all existing rows at creation time, while PostgreSQL enforces the constraint on subsequent `INSERT`/`UPDATE`s.
- **`VALIDATE CONSTRAINT`** verifies existing rows; if any `NULL` remains, validation fails and must be resolved first.
- **`SET NOT NULL`** turns the requirement into an explicit schema property. On modern PostgreSQL versions, a validated `CHECK` can sometimes skip a full table scan, but **still evaluate DDL locks and DBMS version** rather than assuming non-blocking execution.

After `NOT NULL` is set, the redundant `CHECK` constraint can be removed in **a separate controlled migration** so duplicate constraints do not linger forever:

~~~~sql
ALTER TABLE sales_order_demo
DROP CONSTRAINT ck_buyer_email_present_demo;
~~~~

**Ordering note:** Run these steps only once running applications **cannot set `buyer_email` to `NULL`**. The example sync bridge rejects `INSERT`/`UPDATE` lacking both emails, yet production must also check special write paths, load jobs, and bypass privileges.

### 5.9. S3 — Switch Applications, Do Not Rush Dropping the Old Field

The new application can read:

~~~~sql
SELECT buyer_email
FROM sales_order_demo
WHERE order_id = 1;
~~~~

and write `buyer_email`. Throughout the **rollback window**, retain **`customer_email` and the trigger** so A0 can roll back if needed, provided new data semantics remain intelligible to A0.

Phase-gate criteria:

1. All required records migrated and reconciled.
2. New application code needs no legacy reader for normal operations.
3. Request error rates/latency, lock waits, DB CPU/WAL/replication lag stay within limits.
4. No unapproved legacy write paths remain, or they remain protected by the sync bridge.
5. Application rollback has been tested under realistic data conditions.

**Never use a feature flag to hide an unready schema.** A flag toggling read/write paths is safe only if **every runnable combination of flag + code + schema** has been evaluated.

### 5.10. S4 — Contract: Drop Old Structures Once Dependencies Are Gone

Only after confirming **zero remaining A0 instances, workers, jobs, or consumers read/write `customer_email`** and the rollback window has closed, execute:

~~~~sql
BEGIN;

DROP TRIGGER trg_sync_sales_order_email_demo
ON sales_order_demo;

DROP FUNCTION sync_sales_order_email_demo();

ALTER TABLE sales_order_demo
DROP COLUMN customer_email;

COMMIT;
~~~~

At this point **A0 is no longer compatible**. Redeploying A0 will fail because `customer_email` no longer exists. That is why `contract` must be a **separate release milestone**, never bundled with `expand` before proving legacy consumers have retired.

**Trade-offs of `DROP COLUMN`:** PostgreSQL may not immediately reclaim all physical space from dropped column data, and DDL still acquires locks. On large tables, file size, vacuum/rewrite needs, and view/function/BI dependencies must be assessed separately. Never assume `DROP COLUMN` is zero-cost.

### 5.11. Transition Summary

~~~~mermaid
flowchart LR
    A["S0: customer_email"] --> B["S1: add buyer_email"]
    B --> C["2-column sync bridge"]
    C --> D["Backfill + reconcile"]
    D --> E["Enable read/write buyer_email"]
    E --> F{"Any A0/old consumers left?"}
    F -- "Yes" --> G["Keep both columns + monitor"]
    G --> F
    F -- "No" --> H["Drop sync + drop old column"]
    H --> I["S4: buyer_email"]
~~~~

**Lesson:** The target model contains only `buyer_email`, yet reaching it safely requires **guarded and measured intermediate states**. Those states are part of model evolution design, not "throwaway columns we don't need to think about".

## 6. Migrations That Cannot Follow a Mechanical Rule

### 6.1. Adding a New Column With Mandatory Values

Suppose we begin storing **`sales_channel`** per order. Target model:

~~~~text
sales_channel ∈ {WEB, MOBILE, STORE}
sales_channel NOT NULL
~~~~

If historical data lacks channel info, setting all old rows to `WEB` **fabricates data**. You may need an explicit **`UNKNOWN`** value or reconciliation from trustworthy logs.

A sound progression:

~~~~sql
ALTER TABLE sales_order_demo
ADD COLUMN sales_channel VARCHAR(20);

-- Only after source-classification policy and verified values are established:
UPDATE sales_order_demo
SET sales_channel = 'UNKNOWN'
WHERE sales_channel IS NULL;
~~~~

This SQL is valid only if the business approved **`UNKNOWN`** as a valid historical state and records whose true `WEB`/`MOBILE`/`STORE` channel is knowable are not carelessly stamped `UNKNOWN`.

Before adding `NOT NULL` and `CHECK`:

- Update all `INSERT` paths so no new `NULL`s are produced.
- Run backfill using verified source rules.
- Inspect missing and out-of-domain values.
- Stage new constraints so legacy writers are not broken prematurely.

**`DEFAULT` is only for semantically valid defaults:** a default makes sense when legacy rows genuinely share that meaning—for example, currency in a **VND-only** system. A default cannot substitute for data the source system never captured.

### 6.2. Splitting a String Address Into Structured Fields

Suppose the old source has:

~~~~text
shipping_address = "12 Nguyễn Trãi, P. Bến Thành, TP.HCM"
~~~~

The new model requires:

~~~~text
street_address
ward_code
district_code
province_code
country_code
~~~~

Not every legacy string contains enough information for exact parsing. Ward/district names change, locations share names, and some addresses are incomplete or foreign.

A sound plan:

1. **Expand:** add new nullable columns and specify geographic code standards.
2. **Verify sources:** classify rows into sufficient info, insufficient info, and needing confirmation.
3. **Confidence-tiered backfill:** assign `province_code` only with reliable mapping; record source and reconciliation results.
4. **Update new input flows:** capture structured codes from users or an address validation service.
5. **Switch reads:** during transition, fall back to displaying the original string for incomplete rows.
6. **Conditional contract:** retain the original string if history reconstruction or retention policies require it.

This is a **semantic and data-quality change**, not renaming five columns. Where conversion cannot be proven, record an **undetermined state** rather than declaring migration complete.

### 6.3. Changing Data Types and Units of Measure

Suppose legacy product prices use **`NUMERIC(18,2)`** in VND and we want **`BIGINT` representing minor currency units**:

~~~~text
old_amount = 125000.00 VND
new_amount_minor = 125000 (minor unit per VND policy)
~~~~

Before converting:

- Identify currency and decimal scale per row.
- Define **rounding** vs. rejecting non-standard fractions.
- Verify values fit within `BIGINT` without arithmetic overflow.
- Confirm the new column preserves **point-in-transaction** price semantics.
- Test negative values, discounts, refunds, and multi-currency cases if applicable.

A `NUMERIC` to `BIGINT` change **cannot be verified** by `CAST` alone; ignoring precision and currency silently changes value meaning. When publishing external events, version them or emit explicit fields like **`amountMinor + currency`** rather than silently altering the unit of an existing `amount` field.

### 6.4. Changing Primary Key From Auto-Increment to UUID

When moving from **`customer_id BIGINT`** to **`customer_uuid UUID`**:

- Each legacy customer needs **one stable UUID**, not a new UUID per backfill run.
- Internal FKs and external references require an old-to-new key mapping.
- Never switch parents and drop the old key while children still reference it.
- CDC, events, caches, and APIs may still carry numeric IDs.
- Operations may need to maintain **old–new key pairs** for an extended period.

Example mapping table:

~~~~text
CUSTOMER_ID_MAPPING(
    old_customer_id BIGINT UNIQUE,
    new_customer_uuid UUID UNIQUE,
    mapping_version,
    created_at
)
~~~~

If the mapping is 1–1 by business rule, verify no two old keys map to the same new key or vice versa. **A type-valid new key does not prove it identifies the same customer**; preserving identity and referential relationships is the core invariant.

### 6.5. Splitting One Table Into Multiple Tables

An old **`orders`** table held order details plus payment fields. After separating bounded contexts, Billing moves to its own table/store. Clarify:

- Does Sales still own **`Order`** while Billing owns **`Payment/Invoice`**?
- Is Sales' locked price the initial financial obligation while settled amounts live in Billing?
- An order may have multiple captures/refunds, so do not retain a false 1:1 assumption.
- Are **`external_order_ref`** references and idempotency governed?
- Is a projection needed for overview screens?

Across two separate databases, local DDL/SQL transactions cannot guarantee simultaneous atomic commits. Separate **data ownership and integration contracts** before migrating tables.

## 7. Adding Constraints While the System Still Accepts Writes

Changes to **`PRIMARY KEY`**, **`UNIQUE`**, **`FOREIGN KEY`**, **`CHECK`**, and **`NOT NULL`** do more than alter metadata: they expose **invalid historical data** or block un-upgraded writers.

### 7.1. Phased Foreign Key Addition in PostgreSQL

Suppose two local tables:

~~~~sql
CREATE TABLE customer_demo (
    customer_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE order_customer_demo (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT
);
~~~~

Before adding the FK:

~~~~sql
SELECT o.order_id, o.customer_id
FROM order_customer_demo AS o
LEFT JOIN customer_demo AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
-- Expect 0 orphan rows.
~~~~

In PostgreSQL, split into two steps:

~~~~sql
ALTER TABLE order_customer_demo
ADD CONSTRAINT fk_order_customer_demo
FOREIGN KEY (customer_id)
REFERENCES customer_demo(customer_id)
NOT VALID;

-- After cleaning legacy data and verifying write paths:
ALTER TABLE order_customer_demo
VALIDATE CONSTRAINT fk_order_customer_demo;
~~~~

Meaning:

- **`NOT VALID`** creates the constraint without scanning all existing rows upfront; new writes are still checked against the FK.
- **`VALIDATE`** verifies existing rows and succeeds only when all comply.
- A nullable FK still permits `customer_id NULL` under SQL semantics. If business rules forbid `NULL`, enforce **`NOT NULL`** in a separate phase.

**Do not misunderstand:** `NOT VALID` does **not** disable FK checks for new `INSERT`/`UPDATE`s. Nor is `NOT VALID` available identically for every `UNIQUE` form.

### 7.2. Adding `UNIQUE` When Legacy Data Has Duplicates

Before adding `UNIQUE(email)`, confirm **whether email is truly globally unique**. Multiple people may share an email or addresses may be recycled; the business may only require uniqueness per tenant or among active accounts.

Suppose the rule is **`external_code` unique per tenant**. Check duplicates:

~~~~sql
-- Assumes an example table already exists with tenant_id and external_code.
SELECT tenant_id, external_code, COUNT(*) AS duplicates
FROM customer_external_demo
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
~~~~

This query is a **template check on a hypothetical table**, not a standalone script for the `sales_order_demo` dataset. When duplicates exist, determine **which records represent the same entity** rather than blindly keeping `MIN(id)` and deleting the rest.

Once clean, PostgreSQL supports concurrent unique index builds:

~~~~sql
-- Run separately outside BEGIN...COMMIT.
CREATE UNIQUE INDEX CONCURRENTLY ux_customer_external_demo
ON customer_external_demo(tenant_id, external_code);
~~~~

**Key facts:**

- **`CREATE INDEX CONCURRENTLY`** cannot run inside an explicit transaction block.
- It still consumes resources and can fail if duplicates remain or concurrent transactions insert duplicates.
- A failed build can leave an **`INVALID`** index that must be inspected and safely cleaned up before retrying.
- Afterward, if a schema-level **`UNIQUE` constraint** is needed rather than just a unique index, attaching the index must satisfy DBMS eligibility rules.
- `NULL` columns carry special uniqueness semantics; if `NULL` is disallowed, add `NOT NULL` and verify.

Never label a migration suite "atomic rollback" if it includes `CREATE INDEX CONCURRENTLY`; migration tooling must be configured **without wrapping that step in a transaction**.

### 7.3. Enforcing `NOT NULL` Is More Than One `ALTER`

To turn an optional column into mandatory:

1. Define **truly valid values** at the business level.
2. Stop all write paths—including legacy batches/consumers—from producing `NULL`.
3. Backfill historical rows from trustworthy sources.
4. Inspect remaining `NULL`s and undetermined cases.
5. Add/validate constraints, assess locks, then apply `NOT NULL`.
6. Monitor write errors and keep forward-fix readiness if incompatible writers persist.

A `DEFAULT` value helps only when it is **genuinely meaningful**. Never use SQL convenience to claim every historical order came from `WEB` or every legacy customer has `country_code = 'VN'`.

### 7.4. Which Constraints Belong to Intermediate States?

Some constraints are **temporarily looser** than the target model:

- `buyer_email` nullable in S1, mandatory in S4.
- Two column names coexist while constrained to **equal values** during transition.
- Old and new keys co-stored in a mapping table.
- New tables carrying `source_version` or `migration_status` for reconciliation.

For every temporary constraint/artifact, record **when it will be removed, proof of safety, and who approves removal**. Never let temporary columns, indexes, or triggers fossilize into untouchable legacy baggage.

## 8. DDL Locks, Runtime, and Large-Migration Strategies

### 8.1. DDL Is Not Always "Metadata Only"

In PostgreSQL, many **`ALTER TABLE`** operations acquire locks—sometimes blocking reads and writes while executing or waiting in the lock queue. Statement runtime is only part of the risk: if DDL **queues behind a long transaction**, subsequent normal requests pile up behind it.

Before running on large tables:

- Identify long-running transactions and heavy read/write queries.
- Evaluate **lock levels**, wait times, and whether the specific DDL scans or rewrites the table.
- Set **`lock_timeout`**, **`statement_timeout`**, and retry policies per operations standards.
- Estimate WAL, replica lag, I/O, free disk space, and vacuum impact.
- Test on production-like scale and skew when possible.
- Define a deployment window and abort thresholds if lock waits spike.

**Never** set an unbounded `lock_timeout` just to force a migration through; users pay for it in service latency.

### 8.2. Batched Backfills and Restartability

A solid backfill typically has:

- **Stable key ranges:** chunked by PK or partition.
- **Batch size** tuned to write capacity, traffic, and replication.
- **Idempotency:** re-runs neither duplicate rows nor overwrite newer updates.
- **Checkpoints or progress tracking:** knowing which rows completed and which failed.
- **Bounded retries:** separating transient errors from data errors.
- **Throttling:** backing off when DB/replica metrics cross thresholds.
- **Final reconciliation:** verifying content, not just `COUNT`.

In the email example, `WHERE buyer_email IS NULL` identifies unmigrated rows. For complex price conversions, an `is_migrated` flag alone may be insufficient: track **conversion version, source info, and checksums/reconciliation** when silent errors are possible.

### 8.3. Never Read a Snapshot and Assume Data Stands Still

If you run:

~~~~text
10:00:00  Count mismatch = 0
10:00:01  Writer A0 updates customer_email
10:00:02  Enable reader A2
~~~~

the 10:00 check does not prove the 10:02 state. Therefore:

1. Maintain a **sync bridge** or verifiably block legacy writers during transition.
2. Re-check under normal live write traffic.
3. Monitor mismatches continuously or periodically before `contract`.
4. Tie the **cutover** milestone to proof that all writers/consumers have shifted.

Migration correctness is a **property of a live transitioning system**, not a static scan.

### 8.4. Sharding, Partitioning, and Multi-Tenancy

When an application operates across multiple tenant databases or shards, you may see:

~~~~text
Shard 1: S2 - backfilled
Shard 2: S1 - dual-column writes active
Shard 3: S0 - not yet expanded
~~~~

Deploying an app requiring `buyer_email` across **all shards** will fail when hitting Shard 3.

Clarify:

- Does migration run **per shard**, per tenant, or concurrently?
- Is each shard's version/state independently verified?
- Does routing or feature flagging know which shards are ready?
- Is there a guard preventing new tenants from provisioning with the old schema after migration starts?
- Can a release be marked complete while one shard/tenant lags?

Never use a single cluster-wide `"schema_version = 4"` flag to hide shards sitting on different versions. Phased rollouts require **scoped readiness**.

## 9. Rollback, Forward Fix, and Recoverability

### 9.1. Four Non-Synonymous Concepts

| Concept | Meaning | Limitation |
| --- | --- | --- |
| **Application rollback** | Redeploy build A0 after A2 fails | Safe only if schema and data remain A0-compatible |
| **Schema rollback** | Run reverse migration or restore DDL | May lose new columns/data or be unsafe to execute |
| **Forward fix** | Ship a new version fixing the bug while keeping written data | Requires planning, testing, and fast deployment capability |
| **Data restore** | Restore from backup or PITR to a point in time | May lose valid changes after restore point; requires scope/reconciliation |

A **`DROP COLUMN`** can be reversed in **schema shape** via `ADD COLUMN`, yet that does not restore deleted values. Likewise, converting strings to numbers can discard unparseable formats/values; a simple `DOWN` migration cannot reconstruct what was lost.

### 9.2. A Rollback Window Is an Evidenced Commitment

During S3 in our example:

~~~~text
Schema: customer_email + buyer_email + trigger
New app: reads/writes buyer_email
Old app: can revert to reading/writing customer_email
~~~~

Absent semantic changes incomprehensible to A0, rolling back A2 → A0 **can work** because the trigger kept `customer_email` synced. Once S4 drops the old column, this rollback path disappears.

Therefore:

- **Rollback window** must be sized to operational needs and failure-detection speed.
- Do not run `contract` minutes after A2 turns "green" before observing typical load or scheduled jobs.
- Retaining the old structure across one extra app release is often reasonable within clear write-cost and governance bounds.
- After `contract`, code rollback requires a **different recovery plan**, not redeploying an old build.

### 9.3. Never Run `DOWN` Blindly on Live Data

Many frameworks order migrations with `DOWN` steps. Yet `DOWN` is safe only when:

1. New data can be represented losslessly in the old schema.
2. No writer still writes to the new fields/model.
3. Constraints, indexes, views, and external references remain unbroken.
4. Backups/recovery and reconciliation plans exist.
5. The team agrees on **which data state** is acceptable on revert.

For example, splitting `full_name` into `first_name` and `last_name` may not reverse cleanly once users edit the parts separately and original spacing/formatting is lost. Rejoining into `full_name` is a **new business rule**, not exact restoration of the prior state.

### 9.4. Backup Restore Is Not Selective Rollback

Restoring the entire database to before the migration loses **valid orders or payments created afterward**—a severe business impact.

Before major changes:

- Know operational **RPO/RTO**: tolerable data loss and recovery time.
- Verify backups/PITR/snapshots actually restore cleanly.
- Rehearse recovery in a suitable environment rather than trusting "backup succeeded".
- Plan how to reconcile or replay transactions written after the backup timestamp.
- Distinguish **metadata** failures from **corrupted-data** failures to choose the right recovery action.

**Forward fix** is often lower-risk once new data has been committed and can be repaired by a subsequent migration. Never invoke "roll forward" as an excuse to skip testing, audits, or data protection.

## 10. Java Applications and ORMs Must Tolerate Multiple States

The schema may be expanded, yet Java/JDBC/JPA will still break if application SQL assumes a single rigid structure.

### 10.1. Java Signatures Do Not Prove SQL Compatibility

Consider two DTOs:

~~~~java
record OldOrderView(long id, String customerEmail) {}
record NewOrderView(long id, String buyerEmail) {}
~~~~

The Java compiler checks field names, yet if the old repository still executes:

~~~~java
String oldSql = """
    SELECT order_id, customer_email
    FROM sales_order_demo
    WHERE order_id = ?
    """;
~~~~

it **will fail once `customer_email` is dropped**. Conversely, new code:

~~~~java
String newSql = """
    SELECT order_id, buyer_email
    FROM sales_order_demo
    WHERE order_id = ?
    """;
~~~~

fails on S0. Thus, Java compilation and unit tests with mocked repositories **do not replace integration tests against real schema states**.

### 10.2. Read Fallback Helps, but Is Not Enough for Writes

In S1 when `buyer_email` can be `NULL`:

~~~~sql
SELECT
    order_id,
    COALESCE(buyer_email, customer_email) AS buyer_email
FROM sales_order_demo;
~~~~

This works during transition. However:

- If `buyer_email` is **non-null yet stale**, `COALESCE` still returns the wrong value.
- If a legacy writer edits `customer_email` without sync, fallback does **not** fix `buyer_email`.
- On S3 with only `buyer_email`, this query **breaks** because it still references `customer_email`.

Thus distinguish:

1. **A1 — transitional code** using both columns, valid only in specific states.
2. **A2 — target code** using only the new column, valid post-contract.

Never leave fallback SQL in place indefinitely and drop the column without searching for every reference to the old name.

### 10.3. ORM Entities and Schema Migration

With JPA/Hibernate or other ORMs, watch out for:

- Column mapping annotations altering generated SQL.
- New entity versions failing **at startup**, before serving any request.
- Auto-DDL on runtime startup racing across instances, breaking deploy ordering and bypassing backfill plans.
- Converters/listeners writing new semantics before legacy consumers adapt.
- Offline jobs scanning entity models that still reference dropped columns.

Where strict evolution control is required, enforce **explicit migration review and deployment orchestration**, rather than letting instances auto-`ALTER TABLE` on boot. Exact choices depend on tooling, architecture, and operational requirements.

### 10.4. Feature Flags and Schema Readiness

A flag pattern:

~~~~text
Feature flag: READ_BUYER_EMAIL

OFF: A1 reads via compatibility path
ON : A1/A2 read buyer_email as primary source
~~~~

Preconditions to enable the flag:

- Schemas S1/S2 have `buyer_email` on every relevant database/shard.
- Backfill and live writes are verified.
- Instances containing the new read code are actually deployed.
- A rollback plan exists for bad figures, not just HTTP 500 spikes.

**Feature flags do not replace migrations:** flipping a flag on an S0 shard triggers SQL errors; flipping it off does not heal rows backfilled with wrong semantics.

### 10.5. Producers/Consumers and External Data Contracts

If an application emits:

~~~~json
{
  "eventType": "order-created",
  "schemaVersion": 1,
  "payload": {
    "customerEmail": "an@example.org"
  }
}
~~~~

and immediately switches to:

~~~~json
{
  "eventType": "order-created",
  "schemaVersion": 2,
  "payload": {
    "buyerEmail": "an@example.org"
  }
}
~~~~

old consumers reading **`customerEmail`** will break or drop data. Renaming a PostgreSQL column **does not safely update** event contracts.

A sound plan:

- Keep emitting **event v1** while old consumers still depend on it.
- Publish **event v2** with confirmed semantics.
- Have consumers support both v1 and v2 during transition, or use a transformation adapter.
- Test **replay** of legacy events after the database reaches S3.
- Define retirement of v1 based on proof that consumers have migrated.

If both fields share the same meaning, v2 can be a rename. If meaning differs, design an explicit transformation or compatibility boundary rather than silently altering historical payloads.

## 11. Synchronizing Multiple Write Paths and Asynchronous Data

### 11.1. Application Dual-Write vs. Transactional Outbox

**Dual-writing two columns in one database transaction** is one way to maintain old/new representations. It can be safe if all authorized writers follow the protocol and errors roll back atomically.

**Dual-writing two independent systems**—such as writing PostgreSQL and publishing to a broker or writing two separate databases in separate transactions—**lacks built-in atomicity**. If one succeeds and the other fails, systems diverge.

For broker integration, a **transactional outbox** stores state changes and event intent in one source transaction, then relays events out. Outbox prevents **committing state without an event record**, though idempotent consumers are still needed because delivery may retry.

**Do not confuse two distinct concepts sharing the name dual-write:**

- Writing **two columns of one row** in a single transaction.
- Writing **two independent systems**, which needs reliability protocols and reconciliation/compensation.

### 11.2. Late-Arriving Data

When moving from event v1 to v2, a v1 event may arrive **after** the application starts using v2. New consumers must define:

- How long v1 continues to be accepted?
- Does a meaningful mapping to the new model exist?
- When did the event occur, and must data carry historical version tags?
- Are **`occurredAt`** and **`processedAt`** distinguished?
- Can a replayed event duplicate records or regress a newer state?

A message's schema version does not establish **business ordering**; use `eventId`, aggregate versions, or stream-specific ordering rules.

### 11.3. CDC and Downstream Readers Coupled to Physical Schemas

A CDC tool may capture changes from `customer_email` on the source table. Adding `buyer_email` and later dropping `customer_email` changes **CDC event shapes**, snapshots, and connector configs.

Before `contract`:

- Inventory connectors/subscriptions reading the old table/columns.
- Verify downstream handles the new column or has a compatibility transform.
- Ensure snapshots/backfills do not produce duplicate downstream records.
- Monitor offsets/lag and processing progress before dropping columns.
- Define a strategy for replaying historical data shaped under older schemas.

Never conclude "no app reads `customer_email`" merely because a code search in one Java repo finds nothing; **BI, CDC, ETL, warehouse, exports, and external tools** may still depend on it.

### 11.4. Document and Analytical Models Also Need Intermediate States

The same principles apply outside SQL:

- **Document databases:** for a period, collections hold v1, v2, or mixed documents; readers must be version-aware and handle missing fields before cleanup.
- **Event streams:** older events remain in retention or replay logs; consumers must support contracted versions across the committed window.
- **Warehouses:** new facts/dimensions may backfill per partition; reconcile KPIs before switching dashboards or semantic layers.
- **Graph databases:** changing edge types/labels may require keeping old and new relationships during transition while verifying paths are not duplicated.

**The common thread is semantic contracts and mixed-version reading**, not one engine's DDL syntax.

## 12. Testing Intermediate States

### 12.1. Unit Tests Do Not Adequately Verify Compatibility

A unit suite mocking repositories can pass even when new code queries `buyer_email` against an S0 database. Migration testing must cover **real combinations of app versions and schema states**, including transitions.

Example test matrix:

| State | Apps to Test | Minimum Scenarios |
| --- | --- | --- |
| **S0** | A0 | Read/write old orders without new column |
| **S1 partial backfill** | A0, transitional A1 | Read old rows lacking `buyer_email`, create new orders, edit old emails |
| **S1 with trigger** | A0, A2 | Both writer versions update columns; values stay synced |
| **S2 backfilled** | A0, A2 | Read full history, check counts/mismatches, concurrent writes |
| **S3 cutover** | A2, plus A0 if in rollback window | New reader independent of old column; conditional rollback |
| **S4 contracted** | Only A2 and compatible consumers | Zero SQL references to `customer_email` remain |

**Do not run A0 against S4 expecting it to pass**: that combination is intentionally retired by the plan. Instead, verify **no A0 instance or job can reach S4**.

### 12.2. Testing Old and New Data

A useful fixture set:

~~~~text
R1: legacy row, customer_email present, buyer_email NULL.
R2: backfilled legacy row, both fields equal.
R3: new row created by A0 during transition.
R4: new row created by A2 during transition.
R5: same row updated by A0 then updated by A2.
R6: attempt to write two conflicting emails.
R7: empty/malformed email per domain rules.
R8: legacy reporting job executed right before contract.
~~~~

Checks:

- **R1:** transitional reader falls back cleanly and backfill completes the row.
- **R2:** values match and new column is readable.
- **R3/R4:** trigger or sync protocol preserves both fields.
- **R5:** verify update conflicts and versioning if two writers race.
- **R6:** conflicting values rejected.
- **R7:** semantic validation enforced, not just `NOT NULL`.
- **R8:** detect un-migrated consumers before dropping columns.

### 12.3. Concurrency Testing

When two app versions update the same row:

1. Transaction T1 reads email and order version.
2. Transaction T2 updates email and commits.
3. T1 attempts to write using the stale version.

If business rules forbid overwriting newer edits, use **optimistic locking** via a version column or `WHERE` version predicate:

~~~~sql
-- Standalone example: assumes row_version BIGINT NOT NULL was added
-- to sales_order_demo and backfilled with initial value 0.
UPDATE sales_order_demo
SET buyer_email = 'new@example.org',
    row_version = row_version + 1
WHERE order_id = 1
  AND row_version = 7
RETURNING order_id, row_version;
~~~~

If T2 bumped version from 7 to 8, T1's `UPDATE` returns zero rows. The application must handle the **conflict**—for instance re-reading and prompting confirmation. Every writer participating in concurrency control must follow the same protocol; if A0 ignores `row_version`, optimistic locking **no longer protects fully**.

**Warning:** The two-column sync trigger in Section 5 does not solve general lost updates. It only keeps both representations of the **same field** equal on each successful write.

### 12.4. Testing Restart and Replay Outcomes

Never test a migration only as one uninterrupted run. Simulate:

- Backfill reaches 40% and crashes.
- Restart resumes cleanly without overwriting newer updates.
- A batch encounters invalid data rows.
- Outbox relay delivers duplicates; consumers do not double-apply side effects.
- App rollout stalls partway; A0 and A2 run simultaneously.
- Schema expanded, yet one tenant/shard has not updated.
- Rare scheduled legacy report runs hours later.

**Fault-tolerance testing is part of model evolvability.** Testing only the happy path (`S4` + `A2`) does not prove the system traverses `S1`/`S2`/`S3` safely.

### 12.5. Testing External Contracts

For versioned APIs/events:

| Producer | Consumer | What to Verify |
| --- | --- | --- |
| Event v1 | Consumer v1 | Legacy contract works during support window |
| Event v1 | Transitional consumer | Reads and maps old field cleanly |
| Event v2 | Transitional consumer | New field carries right semantics; no duplicate records |
| Event v2 | Consumer v2 | Meets new contract |
| Replay v1 post-cutover | Consumer v2 or adapter | Explicit read/migrate plan or controlled rejection |

Consumers need not support every version **forever**, but support windows, contract retirement, and historical handling must be published and tested.

## 13. Monitoring Progress and Phase-Gate Criteria

### 13.1. Metrics Go Beyond "Migration Succeeded"

A migration command can exit **0** while data is wrong, APIs fail, and replicas lag. Track at least:

| Category | Metrics or Evidence |
| --- | --- |
| **Schema readiness** | Actual migration version per database/shard/tenant |
| **Data completeness** | Rows pending backfill, remaining `NULL`s, or unmigrated rows |
| **Data equivalence** | Mismatch counts between representations; periodic reconciliation results |
| **Write compatibility** | `INSERT`/`UPDATE` failure rates by app version and SQL error type |
| **Reader compatibility** | Queries still hitting legacy column, column-not-found errors, mapping errors |
| **DB health** | Lock waits, transaction durations, CPU, I/O, WAL, deadlocks |
| **Replication** | Replica replay lag and replica read health |
| **Backfill execution** | Rows/batch, failed batches, retries, wait times, checkpoints |
| **Event/CDC** | Consumer lag, schema errors, dead-letter queues, duplicate handling |
| **Business correctness** | Order totals, revenue, orphan rates, domain-specific invariants |

Metrics need **baselines and realistic load thresholds**. "`COUNT` mismatch = 0" is helpful, yet insufficient if both old and new columns share the same wrong data. When changing semantics or splitting tables, reconcile against authoritative business sources—not just two copies of a bug.

### 13.2. SQL Verification Suite for the Email Example

~~~~sql
-- Pending and inconsistent row counts.
SELECT
    COUNT(*) AS all_rows,
    COUNT(*) FILTER (WHERE buyer_email IS NULL) AS pending_rows,
    COUNT(*) FILTER (
        WHERE buyer_email IS DISTINCT FROM customer_email
    ) AS inconsistent_rows
FROM sales_order_demo;
~~~~

To inspect mismatched rows for remediation:

~~~~sql
SELECT order_id, customer_email, buyer_email
FROM sales_order_demo
WHERE buyer_email IS DISTINCT FROM customer_email
ORDER BY order_id
LIMIT 100;
~~~~

Run these queries **only before S4**, while both columns exist. After `contract`, drop or update monitoring jobs referencing `customer_email`; reconciliation scripts themselves are **consumers of the old schema**.

### 13.3. Per-Phase Go / No-Go Gates

**Before Expand:**

- Migration reviewed with lock-risk and app/consumer impact notes.
- Database, shard, and tenant scope known.
- Error monitoring and rollback plans prepared.
- Rehearsed on production-like environment if possible.

**Before Backfill:**

- New structures exist.
- Sync bridge / compatible write paths active.
- Data mapping rules and unconvertible-row handling defined.
- Rate limits and restart mechanisms ready.

**Before Switch:**

- Reconciliation passes per contract; live writes populate accurately.
- Writer/reader error rates within threshold.
- Mixed A0/A2 states tested.
- Plan to pause or revert read paths ready.

**Before Contract:**

- Zero A0 read/write paths or legacy-schema consumers remain.
- Approved rollback window has ended.
- Backup/restore or forward-fix plan reviewed.
- Views, triggers, CDC, reports, jobs, and permissions inventoried.
- Target constraints and A2 behavior verified on S4.

Never turn gates into rubber stamps: if a month-end batch still selects `customer_email`, **do not drop the column just because web instances upgraded**.

### 13.4. What a Dashboard Alone Cannot Prove

Even if a dashboard shows:

~~~~text
Backfill: 100%
Schema version: V004
App instances upgraded: 100%
Error rate: low
~~~~

still ask:

- Does "100%" cover **every tenant and all historical data**?
- Can event replay produce **v1** data after cutover?
- Do BI tools query outside web deployment paths?
- Are new values **semantically accurate**, not merely non-null?
- Who verified the migration did not distort reports or financial amounts?

Good observability provides **evidence for decisions**, not a substitute for verifying semantic contracts.

## 14. Common Failure Patterns

### 14.1. Direct Rename While Legacy Code Still Runs

**Symptom:** `ALTER TABLE RENAME COLUMN` succeeds, yet A0 fails on `SELECT`/`INSERT`.

**Cause:** Incompatible physical change shipped before managing application lifecycles.

**Fix:** Expand both columns, sync/reconcile, switch writers/readers, then contract.

### 14.2. Dual-Writing Only in New Code, Forgetting Old Writers

**Symptom:** `buyer_email` matches right after backfill, then drifts from `customer_email` minutes later.

**Cause:** A0 still updates only the old column without updating the new one.

**Fix:** Manage mixed writes via DB sync or upgrade all writers before relying on the new field; monitor mismatches.

### 14.3. Backfilling and Ignoring Late-Arriving Data

**Symptom:** A legacy import batch ingests rows lacking the new field after backfill finishes.

**Cause:** Migration scope omitted late-arriving data/replay.

**Fix:** Compatibility adapters, sync bridge across the needed window, verify replay handling, contract only on consumer evidence.

### 14.4. Using a Semantically Wrong Default

**Symptom:** All pre-2026 orders get `sales_channel = 'WEB'` even though many were placed in stores.

**Cause:** Treating a convenient default as valid historical truth.

**Fix:** Backfill from trustworthy sources, or use approved `UNKNOWN` status and disclose historical gaps.

### 14.5. Tightening Constraints Before Writers Are Ready

**Symptom:** `NOT NULL` added while old app still inserts missing the new field, causing continuous errors.

**Cause:** Enforcing target invariants before write paths satisfy them.

**Fix:** Stage constraints, deploy compatible writers, validate data, then enforce.

### 14.6. Dropping Columns Before Scheduled Jobs Upgrade

**Symptom:** Web traffic works, then weekend batch report fails selecting `customer_email`.

**Cause:** Consumer inventory included only always-on services.

**Fix:** Inventory batches, BI, exports, CDC, stored procedures, views, and partner tools; run contract tests before `DROP`.

### 14.7. Rolling Back Code After Data Semantics Changed

**Symptom:** A0 reads the old column but misinterprets new currency units or new enum states.

**Cause:** Retaining the old column does not guarantee **semantic compatibility**.

**Fix:** Test rollback against real new data, maintain adapters or forward-fix; never assume a `DOWN` migration is automatically safe.

### 14.8. Oversized Backfill in a Single Transaction

**Symptom:** High WAL, replica lag, lock waits, long-running transactions.

**Cause:** Unbounded `UPDATE` over millions of rows in one transaction.

**Fix:** Small batches with checkpoints/idempotency, benchmark performance, throttle, and bound run windows.

### 14.9. Divergent Migration Histories Across Environments

**Symptom:** Staging is on `V005`, production is on `V003`, yet the same app build deploys.

**Cause:** Release pipeline does not couple schema readiness to code version.

**Fix:** Track migration state per environment, enforce deployment prerequisites/gates, and check compatibility matrices.

### 14.10. Treating Migration History Table as Complete Business State

**Symptom:** Version table records `V004` succeeded while 15% of rows remain unbackfilled.

**Cause:** Treating DDL completion as total data-migration completion.

**Fix:** Track **schema state and data migration progress separately**, with quality checks before switch/contract.

## 15. Sample Runbook for a Schema Change

A **migration runbook** should be concise enough for operators to execute yet explicitly state **entry conditions, actions, verification evidence, abort criteria, and recovery plans**—never just bare SQL without context.

### 15.1. Change Decision Record

~~~~text
CHANGE: Rename sales_order.customer_email → buyer_email
BUSINESS MEANING:
  Same semantics: buyer's email at order creation time.
  Does not change to recipient email or current profile email.

OLD WRITERS:
  Web API A0, admin batch A0.

OLD READERS:
  Web API A0, customer support export, weekly BI job.

NEW WRITERS:
  Web API A2 using buyer_email only.

TARGET:
  sales_order.buyer_email NOT NULL.
  customer_email removed.

DATA RULE:
  During dual-column phase, buyer_email = customer_email.

ROLLBACK WINDOW:
  Bounded per release policy; do not drop old field during window.

CONTRACT GATE:
  All old writers/readers retired or adapted compatibly.
  Pending/mismatch = 0, migration history matches scope.
  Monitoring, backup/forward-fix, and sign-off confirmed.
~~~~

In real documentation, replace service names and milestones with **specifically inventoried deployment targets**. Never mark "all migrated" from metrics of only one web cluster.

### 15.2. Phased Runbook Table

| Phase | Action | Success Evidence | Stop / Response |
| --- | --- | --- | --- |
| **Preflight** | Inventory writers/readers, data, locks, timeouts | Owners, mapping, compatibility matrix ready | Missing consumer or unclear semantics: halt deploy |
| **Expand** | Add nullable `buyer_email`, install sync bridge | A0 keeps running, zero `INSERT`/`UPDATE` errors | Write/lock errors rise: pause rollout, investigate |
| **Backfill** | Run batched, checkpointed, throttled | Pending drops, `mismatch = 0` | Invalid data found: quarantine rows, never guess values |
| **Switch** | Deploy A2, enable new read/write paths | Requests & reports accurate; rollback viable in window | Errors rise: toggle flag / revert code if data compatible |
| **Observe** | Monitor load and any lingering consumers | Zero legacy queries; data stays accurate under load | Legacy consumer found: extend compatibility window |
| **Contract** | Drop trigger, drop column, clean up docs | A2/new consumers running on target schema | Simple A0 rollback no longer possible; use new recovery plan |

### 15.3. Who Is Accountable?

| Role | Decision or Evidence |
| --- | --- |
| **Business / Data Owner** | Confirms semantic equivalence and legacy-row policies |
| **Data Modeler / DBA** | DDL, locks, constraints, mappings, indexing, and backfill design |
| **Application Team** | SQL/JPA mappings per version, feature flags, compatible write paths |
| **Integration Team** | API/event versions, CDC, exports, batches, consumer contracts |
| **SRE / Platform** | Load, locks, replica lag, monitoring, backup/restore, rollout |
| **QA / Data Quality** | Matrix test results, reconciliations, fault/concurrency testing |
| **Release Owner** | Go/no-go for switch, closing rollback window, and contract |

In smaller teams, one person may wear several hats. **Accountability must still stay explicit** regardless of job titles.

### 15.4. Versioning Rules and Reproducibility

Record:

- **Schema migration sequence**: applied steps and checksums.
- **App build/version**: which builds run safely on each schema state.
- **Data migration state**: progress, checkpoints, errors, reconciliation timestamps.
- **Contract version**: API/event versions supported by producers/consumers.
- **Rollout state**: feature flags, canary cohorts, migrated shards/tenants.

These states answer **different questions** and must not be collapsed into `migrated = true`. Example:

~~~~text
schema_migration = V004
data_backfill = 99.95%
app_rollout = 100% A2
event_consumer = v1 still active for partner X
contract_ready = false
~~~~

Here schema reached `V004`, yet **it is not ready to drop the old field** because unmigrated data and a v1 consumer remain.

### 15.5. Concluding After a Successful Migration

Consider a change complete only when:

1. **Target schema** exists across the entire declared scope.
2. **Target data** satisfies constraints and approved reconciliations.
3. **Apps and consumers** no longer depend on legacy paths.
4. **New write paths** prove long-term invariant enforcement.
5. **Telemetry** shows zero lingering migration errors and closed rollback window.
6. **Documentation and ownership** updated; temporary triggers/columns/indexes cleaned up cleanly.

Closing a ticket just because `ALTER` finished leaves **technical debt and inconsistent data** for future releases.

## 16. Design and Verification Checklist

Before promoting a migration to production:

- [ ] Verified **before and after field semantics**, not confusing rename with semantic change.
- [ ] Inventoried relevant **writers, readers, APIs, events, CDC, BI, batches, and scheduled jobs**.
- [ ] Built **app × schema × data state** matrix with allowed and forbidden combinations.
- [ ] Planned **expand before new code depends on new schema**.
- [ ] Defined rule keeping **both representations** synced while old/new writers coexist.
- [ ] Backfill is **idempotent**, appropriately batched, checkpointed, retriable, and throttled.
- [ ] Unconvertible rows have **business rules**; never fabricated values.
- [ ] Tracked **pending, mismatch, error, lock waits, replica lag** with abort thresholds.
- [ ] New constraints enforced only once writers and data are ready.
- [ ] Assessed **transaction/DDL locks**, PostgreSQL version, and concurrent indexing where appropriate.
- [ ] Checked **event versions/replays**, late-arriving consumers, and external services.
- [ ] Tested **mixed old/new code** in intermediate states.
- [ ] Tested **application rollback** against new data and documented rollback boundaries.
- [ ] Prepared **forward-fix/restore plan** for data-corruption incidents.
- [ ] Per-shard/tenant rollout tracks **scoped readiness**, not inferred from one global version.
- [ ] Assigned **go/no-go** owner, abort criteria, and failure handling.
- [ ] **Contract separated from expand** and executed only after legacy consumers retire.
- [ ] Reviewed views, triggers, stored procedures, permissions, temporary indexes, and cleanup.
- [ ] Post-migration, updated **schema docs, API/event contracts, and reports**.
- [ ] Never treated technical deploy success as **domain/business QA** without verifying formulas, states, and real data.

## 17. Practice Exercises With Answers

Exercises use **S0** (old schema), **S1** (expanded schema), **S2** (data migrated), **S3** (switched to new app), and **S4** (contracted). Unless stated otherwise, assume old and new email columns **share business semantics**, multiple writers may exist, and PostgreSQL is the database.

### Exercise 1 — Why Can Direct `RENAME COLUMN` Break Apps?

App A0 runs `SELECT customer_email`. The team runs `ALTER TABLE RENAME COLUMN customer_email TO buyer_email` before deploying A2.

**Question:** Which step is risky, and what does the compatibility matrix say?

**Answer:** Immediately after the rename, A0 loses `customer_email` for `SELECT`/`INSERT`/`UPDATE`; errors occur before A2 deploys. The matrix states **A0 is incompatible with a `buyer_email`-only schema**. Expand to keep both columns, transition code in phases, and contract only after A0 is retired.

### Exercise 2 — Can S0 Run an App Writing Only the New Field?

A2 always executes `INSERT INTO sales_order_demo(buyer_email) VALUES (...)`. S0 has only `customer_email`.

**Question:** Can A2 run on S0?

**Answer:** **No.** The database reports column `buyer_email` does not exist. Even if A2 has fallback logic on **reads**, it is still incompatible with S0 on the **write path**. Schema expand must precede deploying new write paths in that scope.

### Exercise 3 — Is a One-Time Backfill Enough While A0 Still Writes?

The team adds `buyer_email`, backfills everything, and deploys A2 writing both columns. A0 still runs on a few instances updating only `customer_email`.

**Question:** What can happen?

**Answer:** A0 updates the old column post-backfill while the new column stays unchanged; A2 reads stale `buyer_email`. You need **DB-level synchronization** or a protocol upgrading all writers / coordinating write handover. Dual-writing in A2 alone is **insufficient** while A0 remains.

### Exercise 4 — Are `NULL`s Allowed in the Expanded State?

Target model requires `buyer_email NOT NULL`, yet when adding `buyer_email` to a table with three million existing rows, all `buyer_email` values start as `NULL`.

**Question:** Why is leaving it nullable in S1 intentional?

**Answer:** It is a **valid intermediate state** allowing existing rows and A0 to keep operating. Only after establishing mappings, guarding writes, backfilling, and confirming zero `NULL`s do we tighten `CHECK`/`NOT NULL`. It does not mean the target model permits missing emails.

### Exercise 5 — Does a Two-Column Sync Trigger Prevent Lost Updates?

T1 and T2 both read an old email. T2 saves a new email, then T1 writes a different email based on its stale read. The trigger keeps both columns equal after each `UPDATE`.

**Question:** Is data guaranteed to preserve both T1 and T2's intentions?

**Answer:** **No.** The trigger keeps both representations equal per write, but does not prevent T1 from **overwriting a newer commit**. Preventing lost updates requires optimistic locking/versioning or appropriate concurrency rules followed by every writer.

### Exercise 6 — Why Is `COUNT(*)` Not Enough?

After backfill, `buyer_email` is populated on every row and before/after `COUNT(*)` match.

**Question:** Can we conclude the migration is correct?

**Answer:** Not yet. `buyer_email` could hold the **wrong email**. Check mismatches against the old column when semantics match, and reconcile against authoritative business sources/contracts when semantics change. Matching counts only measure **completeness**, not **correctness**.

### Exercise 7 — Backfill Stops Midway

A migration job reaches 60% and the server crashes. The job restarts filtering `WHERE buyer_email IS NULL`.

**Question:** What does this condition help with? Is it enough?

**Answer:** It provides **basic idempotency**: rows already having `buyer_email` are not overwritten on restart. You still need checks for **non-null conflicting rows**, progress tracking, batch error handling, late-arriving data, and bounded `UPDATE` sizes. For complex mappings, store transformation versions or source signatures to know if previous outputs remain valid.

### Exercise 8 — Adding `DEFAULT` for Unknown Data

A system adds `sales_channel NOT NULL DEFAULT 'WEB'` to all old orders. Historical orders actually came from `MOBILE` or `STORE`.

**Question:** Is the model valid?

**Answer:** No, unless `WEB` is a known true value. `DEFAULT` creates **valid-looking but semantically false** data. Backfill from reliable sources, or use an approved `UNKNOWN` status and disclose missing historical coverage.

### Exercise 9 — `NOT VALID` on a `FOREIGN KEY`

A team adds a new FK with `NOT VALID` and claims new `INSERT`s may violate the FK until `VALIDATE` runs.

**Question:** Is that true?

**Answer:** **No.** In PostgreSQL, an FK added `NOT VALID` **skips immediate validation of existing rows**, yet new writes must obey the constraint. `VALIDATE` checks remaining historical rows. `NOT VALID` is not a toggle disabling FK checks on new writes.

### Exercise 10 — Where to Create a `UNIQUE` Index Concurrently?

A team writes a migration: `BEGIN; CREATE UNIQUE INDEX CONCURRENTLY ...; COMMIT;`.

**Question:** What is the issue?

**Answer:** PostgreSQL forbids **`CREATE INDEX CONCURRENTLY` inside an explicit transaction block**. Configure the index step separately per your migration tool, check duplicates, and inspect index state on failure. "Concurrently" does not mean zero load or no monitoring needed.

### Exercise 11 — App Rollback vs. Data Rollback

Schema at S3 retains `customer_email`, `buyer_email`, and the trigger. The team wants to roll A2 back to A0 due to an app bug. During two days on A2, no data changed semantics and the trigger kept the old column synced.

**Question:** Is rolling back A2 → A0 likely safe? Is it guaranteed safe in all cases?

**Answer:** **Likely safe** under these assumptions because A0 still sees synced `customer_email`. Still verify read/write paths, enums/statuses, currencies, events, and newly created data. The mere existence of the old column **does not guarantee semantic compatibility**. After S4 drops `customer_email`, simple rollback to A0 will not work.

### Exercise 12 — Why Does `DOWN` Not Restore Lost Data?

A migration merged old address fields and dropped the original address. A `DOWN` script merely executes `ADD COLUMN original_address TEXT`.

**Question:** Has the pre-migration state been restored?

**Answer:** **No.** `ADD COLUMN` restores only **shape**, not the deleted values. You need backups or historical records, and even then reverse mapping of newly edited records may be ambiguous. Distinguish DDL rollback from **data restoration**.

### Exercise 13 — Changing Units While Keeping the Same Type

An `amount` column remains `BIGINT`, previously measuring **VND**, post-migration measuring **thousands of VND**. The team claims it is compatible because the column type did not change.

**Question:** True or false?

**Answer:** **False.** This is a **breaking semantic change**: numeric values shift meaning by 1,000x. Establish explicit contracts/versions, clear naming or unit fields, conversion/reconciliation, and consumer updates. Type checks verify shape, not meaning.

### Exercise 14 — One Shard Still Has the Old Schema

App A2 deploys cluster-wide; Shards 1 and 2 are at S2, Shard 3 is still S0.

**Question:** What requirement is violated, and what is missing?

**Answer:** A2 requires `buyer_email`, which Shard 3 lacks, breaking reads/writes on that shard. You need **per-shard schema readiness**, controlled rollout ordering, or version-aware routing/feature flags. A cluster-wide `schema_version` variable is inadequate when actual shard states differ.

### Exercise 15 — Event v1 Arrives After Database Contract

Sales DB reached S4 (`buyer_email` only). A consumer must replay a v1 event containing `customerEmail`.

**Question:** Must we restore `customer_email` in the database?

**Answer:** Not necessarily. Use a **consumer/adapter supporting v1 and mapping per known contract** to the current model. If semantics match, mapping is straightforward; if they differ, verify or reject cleanly. **Event versions and table versions are distinct version axes.**

### Exercise 16 — Consumer Outside the Main App Repo

Web switched to `buyer_email`, yet a monthly BI job on the 1st still selects `customer_email`. The team wants to `DROP` the old column on day 2 post-deploy.

**Question:** Is it ready for `contract`?

**Answer:** No. The BI job is a **legacy reader** and will fail after `DROP`. Inventory, migrate, and test the job—or maintain an explicit compatibility view/adapter—before removing old structures. Checking only the web service version is incomplete.

### Exercise 17 — Splitting Addresses by Guessing Ward Codes

Many text addresses lack district/ward details, so the backfill defaults every unmatched `ward_code` to a placeholder code.

**Question:** Why is this dangerous? What state should the model support?

**Answer:** Data becomes **complete in columns yet wrong in meaning**, causing misrouted deliveries or skewed geographic reports. Distinguish **unknown, unmigrated, not applicable, and verified**, keep original text where needed, and route ambiguous rows to manual review or trusted enrichment.

### Exercise 18 — Migration History Reports `V004`

Migration `V004` shows "success", yet 1% of `buyer_email` values are `NULL`. Someone claims deployment is done because all migration files ran.

**Question:** Can we switch to `buyer_email`-only A2 and set `NOT NULL`?

**Answer:** No. **Schema history shows only that structural steps ran**, not that data backfill completed. Investigate the 1%, guard write paths, reconcile data, handle late-arriving events, and tighten constraints only when ready.

### Exercise 19 — Changing `customer_id` From `BIGINT` to `UUID`

Two tables hold FKs to old `customer_id`. The team wants to generate new UUIDs, immediately drop the integer column, and migrate order rows later.

**Question:** What is missing in this design?

**Answer:** You need a **stable 1–1 mapping**, migrated FK relationships, referential integrity checks, support for consumers/APIs/events carrying old IDs, and intermediate states supporting joins/reconciliation. Generating UUIDs and dropping old integers before updating references creates orphans and breaks lookups.

### Exercise 20 — Can a Release Be Considered Complete While Multiple Versions Coexist?

After expand, part of the fleet runs A0 and part runs A2. The sync trigger works, `mismatch = 0`, errors are low; however, 3 days remain in the rollback window and a legacy BI consumer has not migrated.

**Question:** Can the expand/switch phase be considered successful? Can we mark the whole migration done and `DROP` the old column?

**Answer:** You may conclude the **current compatibility phase meets technical criteria** given evidence. However, **do not mark `contract` complete** or `DROP customer_email` while legacy consumers and the rollback window remain active. Phase-based state management enables accurate conclusions.

### Exercise 21 — Sync Trigger Receives Two Conflicting Values

A request sets `customer_email = a@example.org` and `buyer_email = b@example.org` in one `UPDATE`.

**Question:** How does the example trigger react, and why not pick one side arbitrarily?

**Answer:** Because both columns changed relative to old values and disagree, the trigger executes **`RAISE EXCEPTION`** so conflicting data cannot commit. Picking one silently masks **mapping bugs or business conflicts**; during a transition asserting equal meaning, disagreement must error or follow an explicit ownership rule.

### Exercise 22 — When Is Forward Fix Better Than Schema Reversal?

App A2 discovers a `buyer_email` formatting bug after 8 hours in production, during which many valid new orders arrived. The schema already uses `buyer_email` and sufficient source data remains to repair values.

**Question:** Should restoring the entire database to 8 hours ago be the first move?

**Answer:** Not by default, as that loses **8 hours of valid orders**. Triage the bug, affected scope, **forward fix** via reconciled script, code rollback if compatible, or planned restore protecting new data. Backup/PITR is powerful, yet RPO/RTO and business impact must be weighed.

### Exercise 23 — DDL Lock Contention

`ALTER TABLE` ran fast in staging, yet in production it queued behind a long transaction and spiked latency for other requests.

**Question:** Can we assume `ALTER` is harmless because its own runtime is short?

**Answer:** No. **Lock wait time** and the queue of blocked requests behind it often matter more than DDL execution time once acquired. Check lock levels, long-running transactions, `lock_timeout`, retry plans, and deployment windows rather than extrapolating directly from staging.

### Exercise 24 — Migration Results and Acceptance Criteria

A team declares "column rename complete" because:

~~~~text
DDL success = true
Deployment A2 = 100%
Backfill pending = 0
~~~~

**Question:** Name at least four additional pieces of evidence needed before `contract`.

**Reference answer:**

1. **`Mismatch = 0`** and semantic reconciliation against real data.
2. Zero remaining **old readers/writers** (batches, BI, CDC, event consumers, partners).
3. Tested **mixed app/schema versions**, replays, and concurrent write errors.
4. Rollback window ended with a **forward-fix/restore plan** ready.
5. Measured **lock waits, replication lag, write errors, and read errors** under realistic load.
6. Audited **views, triggers, indexes, constraints, and permissions** depending on the old column.
7. Named owner signed off **go/no-go** gates and cleanup plan.

Those three numbers reveal only **part of the state**, not that dropping the old column is safe.

## 18. Quick Reference Table

| Concept | Meaning and Reminder |
| --- | --- |
| **Schema version** | Structural changes applied; not synonymous with data migration progress |
| **App version** | Running code and the columns/APIs it actually reads/writes |
| **Contract version** | API/event semantics and shape; may evolve on a different cadence from the DB |
| **Data migration state** | Which rows are unmigrated, migrated, conflicting, or unconvertible |
| **Expand** | Add new structure without breaking legacy versions |
| **Migrate/backfill** | Verifiable, idempotent data conversion resilient to restarts |
| **Switch/cutover** | Shift primary read/write paths to the new representation |
| **Contract** | Drop old structures after dependencies and rollback window end |
| **Rolling deployment** | A0 and A2 may run concurrently; must design for compatibility |
| **Read fallback** | Helps with unmigrated rows; does not sync writes and breaks post-contract if unremoved |
| **Dual-write** | Needs a consistency protocol; distinguish two columns in one DB vs. two systems |
| **Trigger bridge** | One transitional sync option; adds operational responsibility and must be removed |
| **Constraint validation** | Backfill and verify before tightening; understand `NOT VALID` per DBMS |
| **`CREATE INDEX CONCURRENTLY`** | Cannot run inside a transaction block; still carries cost and failure states to handle |
| **Rollback window** | Bounded window preserving old contract for app rollback |
| **Forward fix** | Repairing forward when new data exists and reversal is unsafe |
| **Reconcile** | Verifying semantic and referential accuracy, not just row counts |
| **Go/no-go gates** | Criteria proving safety before advancing phases |
| **Version matrix** | Supported combinations of app × schema × data × contract |
| **Ownership** | Who owns data, migration, rollback, and contract decisions |

**Conclusion:** A data schema evolves successfully not because someone wrote the final DDL command, but because **every state along the transition path has clear meaning, stays compatible with running code, and can be verified**. Govern schema, application, contract, and data states independently; apply **expand–migrate–switch–contract**, test mixed writers/readers, reconcile data, and enforce invariants in every phase. Remove old structures only once dependencies are proven gone and rollback limits are accepted. Doing so lets data models evolve with the business while preserving **correctness, recoverability, and reliability in live systems**.
