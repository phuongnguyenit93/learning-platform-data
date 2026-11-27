# Adding Attributes, Changing Types, Tightening Constraints, and Assessing Existing Data

A data model rarely stays identical from day one until system retirement. Initially, a store might store order totals as strings for quick ingestion from a legacy source. A few years later, the system needs accurate revenue aggregation, sales channels, tenant-scoped Customer links, and prevention of invalid order statuses. Seemingly simple changes—adding a column, changing `TEXT` to `BIGINT`, adding `NOT NULL` or `UNIQUE`—can cause **existing data to become invalid**, **running applications to fail**, or **concurrent writes to conflict during migration**.

This lesson in the **Model Evolution** chapter of the **DATABASE_DATA_MODELING** module focuses on four tightly coupled skills:

1. **Adding attributes** while remaining compatible with existing data and applications.
2. **Changing data types** without losing values, corrupting units, or overflowing representation limits.
3. **Tightening constraints** along a verifiable rollout path: `CHECK`, `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, and business rules.
4. **Assessing existing data** before, during, and after migration to decide whether constraints can be applied immediately, or whether data must be cleaned, backfilled, or redesigned.

The focus is turning change requirements into **verifiable schemas and migration workflows** across relational, document, graph, and analytical models. Technical examples use PostgreSQL; locking behavior, online DDL mechanisms, and syntax depend on the DBMS and version, so do not apply them mechanically across every system.

> **Principle:** Do not start from an `ALTER TABLE` statement. Start from the **new invariant**, the **real data currently violating it**, the **application versions still running**, and the **ability to recover if the change is interrupted**.

## 1. How Does Model Evolution Differ from Designing a New Table?

When creating a brand-new table, you can choose ideal data types and constraints before inserting the first row. When altering an existing table, at least four concerns must be weighed together:

- **Historical data:** millions of rows with `NULL`s, malformed strings, reused codes, orphan references, or values violating the new rules.
- **Running applications:** multiple versions of APIs/workers/batches may read or write concurrently without deploying simultaneously.
- **Data contracts:** APIs, events, reports, CDC, ETL, and partners may depend on legacy column names, types, and semantics.
- **System operations:** long migrations can lock tables, generate WAL, impact replication, consume storage, and complicate backups and rollbacks.

A "correct" change must satisfy three distinct layers:

| Verification Layer | Question | Example |
| --- | --- | --- |
| **Schema** | Can new data be stored and queried? | `total_amount_vnd` is `BIGINT` |
| **Data** | Do all existing rows satisfy the new type/rules? | No `amount_text` that fails numeric conversion |
| **Operations / compatibility** | Do running readers/writers continue working properly? | Legacy workers still write `amount_text` during transition |

A syntactically successful SQL migration does not prove the other two layers are satisfied.

### 1.1. Three Types of Changes and Their Impacts

| Change | Example | Easily Overlooked Risk |
| --- | --- | --- |
| **Additive** | Add `order_channel` | Legacy data is `NULL`; old writers do not populate the new column |
| **Transformative** | `TEXT` money to `BIGINT` VND | Parse errors, overflow, wrong units, drift during dual-write |
| **Restrictive** | `NOT NULL`, `CHECK`, `UNIQUE`, `FK` | Old rows violate it; new writes from legacy app versions keep violating it |

Do not equate **syntactic compatibility** with **semantic compatibility**. Adding a column may not break an explicit `SELECT`, yet a consumer using `SELECT *` and decoding by positional column order can still break. Renaming fields in documents or events also affects contracts outside the database.

## 2. Running Case Study: Orders in a Sales System

Suppose the database currently has:

~~~sql
-- Legacy schema used to simulate the lesson on a test database.
CREATE TABLE customer_accounts (
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    customer_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE legacy_orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT,
    amount_text TEXT,
    currency_code TEXT,
    status TEXT,
    external_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Characteristics of the legacy source:

- **amount_text** is a string representing money in **whole VND**, sometimes containing spaces, `NULL`, separators, or non-numeric characters.
- **currency_code** can be `NULL` even though the business operates in VND; some rows may record another currency due to source bugs.
- **status** is free-form `TEXT`: `PAID`, `paid`, `DONE`, `CANCELLED`, `UNKNOWN`, `NULL`, etc.
- **customer_id** can be `NULL` and lacks a composite FK enforcing the matching tenant.
- **external_reference** can be duplicated due to re-ingested events, yet can also be `NULL` for manually created orders.
- The new API, old API, and file-import jobs may all `INSERT` into `legacy_orders`.

New targets must be written as invariants, not just a list of columns:

1. **total_amount_vnd:** non-negative integer representing **whole VND**, no mixed currencies, no `BIGINT` overflow.
2. **order_channel:** one of `WEB`, `STORE`, `PARTNER`, `UNKNOWN`; `UNKNOWN` is used only when the source truly did not specify it.
3. **status:** in `PENDING`, `PAID`, `CANCELLED` per a business-approved workflow.
4. **Customer:** when required by rules, Customer must exist in the **same tenant**; the final goal is `customer_id NOT NULL` for in-scope orders.
5. **external_reference:** must be unique within a tenant for orders with a reference; decide separately whether `NULL` remains allowed.
6. **Compatibility:** do not halt writes when adding fields; upgrade batches and applications in stages.
7. **Reconciliation:** after migration, row counts and cleaned totals must be explainable from source data.

Some invariants may **not apply to every order type**. For example, walk-in orders may have no customer account, or migrated historical orders may reference deleted customer IDs. Before enforcing `NOT NULL`, the business must decide whether to create an Unknown Customer, allow guest orders with alternative attributes, separate record types, or exclude out-of-scope data. Never replace `NULL` with an arbitrary ID just to make a constraint pass.

## 3. Profiling Actual Data Before Designing ALTER TABLE

Altering a large table requires a **data profile** to quantify exception counts and types rather than running `ALTER` and waiting for failures.

### 3.1. Scale, NULLs, and Distribution

~~~sql
SELECT COUNT(*) AS total_orders,
       COUNT(*) FILTER (WHERE amount_text IS NULL) AS amount_null,
       COUNT(*) FILTER (WHERE customer_id IS NULL) AS customer_null,
       COUNT(*) FILTER (WHERE currency_code IS NULL) AS currency_null,
       COUNT(*) FILTER (WHERE status IS NULL) AS status_null,
       COUNT(*) FILTER (WHERE external_reference IS NULL) AS reference_null,
       MIN(created_at) AS first_created,
       MAX(created_at) AS last_created
FROM legacy_orders;

SELECT status, COUNT(*) AS rows
FROM legacy_orders
GROUP BY status
ORDER BY rows DESC, status;

SELECT currency_code, COUNT(*) AS rows
FROM legacy_orders
GROUP BY currency_code
ORDER BY rows DESC, currency_code;
~~~

Also measure distributions by **tenant, time, and data source**, since a rare global exception can be heavily concentrated in one large tenant or one historical import batch.

### 3.2. Classifying Convertible Money Strings

In this example, VND has **no fractional part**; accept only non-negative integer representations, possibly with leading/trailing spaces.

~~~sql
SELECT order_id, amount_text
FROM legacy_orders
WHERE amount_text IS NULL
   OR btrim(amount_text) !~ '^[0-9]+$'
ORDER BY order_id
LIMIT 100;
~~~

Do not blindly strip all non-digit characters. The string **`1,200`** could mean one thousand two hundred or `1.2` depending on locale; **`-500`** could be a refund entry rather than a typo. Normalization rules require **documented explanation and business approval**.

Check for `BIGINT` overflow risk by casting valid-format strings through `NUMERIC` first:

~~~sql
WITH parsed AS (
    SELECT order_id,
           CASE
               WHEN amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS amount_numeric
    FROM legacy_orders
)
SELECT COUNT(*) FILTER (
           WHERE amount_numeric > 9223372036854775807
       ) AS values_exceeding_bigint,
       COUNT(*) FILTER (
           WHERE amount_numeric IS NOT NULL
             AND amount_numeric <= 9223372036854775807
       ) AS parseable_in_range
FROM parsed;
~~~

Do not treat `COUNT = 0` from this query as sufficient proof without also checking `NULL`s, malformed strings, and data written **after the profile timestamp**.

### 3.3. Checking Rule Violations and References

~~~sql
-- Statuses outside the new domain, distinguishing NULL from garbage values.
SELECT status, COUNT(*) AS rows
FROM legacy_orders
WHERE status IS NULL
   OR status NOT IN ('PENDING', 'PAID', 'CANCELLED')
GROUP BY status
ORDER BY rows DESC;

-- Customers missing in the matching tenant.
SELECT o.tenant_id, o.order_id, o.customer_id
FROM legacy_orders AS o
LEFT JOIN customer_accounts AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
ORDER BY o.order_id
LIMIT 100;

-- Duplicate references per tenant; NULL is not treated as participating in uniqueness yet.
SELECT tenant_id, external_reference, COUNT(*) AS duplicates
FROM legacy_orders
WHERE external_reference IS NOT NULL
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1
ORDER BY duplicates DESC, tenant_id;
~~~

**`CHECK`, `FK`, `UNIQUE`, and `NOT NULL` each handle `NULL` differently**; measure them separately. In PostgreSQL, standard `UNIQUE` allows multiple `NULL`s, and `FK` allows null foreign keys without `NOT NULL` (under default matching). `CHECK` evaluating to `UNKNOWN` on `NULL` is still satisfied and does not force the column to be populated.

### 3.4. Assessing Impact Scope

The profile should document:

| Dimension | Data to Collect |
| --- | --- |
| **Scale** | Row count, row width, table/index size, growth rate |
| **Quality** | `NULL` counts, malformed formats, overflows, orphan FKs, duplicates |
| **Skew** | Tenants/sources/dates with concentrated exceptions |
| **Semantics** | Currencies, timezones, status mappings, guest accounts |
| **Applications** | Number of writers/readers, active versions, SQL/ORM dependencies |
| **Operations** | Read/write SLOs, replication lag, backups, lock timeouts |
| **Exception handling** | Auto-convertible, requires source fix, requires business sign-off |
| **Acceptance** | Allowed residual errors, deadlines, and owners |

Small sample datasets are insufficient for production profiling. On hundreds of millions of rows, a full scan can be I/O-heavy; plan controlled scans, use representative samples for initial estimates, and then **verify every required row** before enforcing invariants. Never treat a random sample as proof that all data is clean.

## 4. The Expand → Backfill → Validate → Contract Roadmap

A safe change is normally split into phases rather than one monolithic migration:

~~~mermaid
flowchart LR
    A["Profile + design invariants"] --> B["Expand schema"]
    B --> C["Reader/writer compatibility"]
    C --> D["Backfill legacy data"]
    D --> E["Validate + reconcile"]
    E --> F["Tighten constraints"]
    F --> G["Contract old schema"]
~~~

### 4.1. Expand: Support Both Representations in Parallel

- Add the new column as **nullable** or with a safe default.
- Add indexes/constraints in a progressively deployable mode.
- Bring applications to a state that can **read both old and new**.
- Stop introducing new bad data via write-path validation.

### 4.2. Backfill: Migrate Historical Data

- Convert only records meeting valid rules.
- Use small batches, checkpointable/restartable, controlling locks and WAL.
- Do not overwrite concurrent application updates.
- Record an exception list for separate resolution.

### 4.3. Validate: Verify the Entire Protected Dataset

- Count `NULL`s, orphans, duplicates, out-of-domain values, and mismatches between representations.
- Reconcile by tenant/date/source and verify invariants.
- Observe newly written data after readers/writers have upgraded.

### 4.4. Contract: Remove the Legacy Representation

- Switch all readers to the new field and block legacy writers.
- Apply final constraints and maintain monitoring.
- Drop old columns/tables only after the compatibility/rollback window closes, with backups and recovery readiness.
- Update events/APIs/schema registries, documentation, and dashboards to match the contract.

**Contract is the riskiest phase for rollback.** After dropping old columns or introducing incompatible semantics, reverting to an old application version may require reverse data migration, which may be impossible if new values unrepresentable in the old model have been accepted.

## 5. Adding Attributes Without Fabricating Meaning

Suppose we need to add **`order_channel`** for all orders.

### 5.1. Expand Step

~~~sql
ALTER TABLE legacy_orders
ADD COLUMN order_channel TEXT;
~~~

A nullable new column lets older application versions continue inserting (assuming they do not rely on fragile assumptions like columnless `INSERT`s). `NULL` on historical records is a **known state**, not an immediate failure.

If a default is desired for new orders, apply it only when that default is valid for every write path that omits the column:

~~~sql
ALTER TABLE legacy_orders
ALTER COLUMN order_channel SET DEFAULT 'UNKNOWN';
~~~

**`UNKNOWN`** is an "undetermined" label and must not be silently interpreted as `WEB`, `STORE`, or `PARTNER`. If existing sources lack enough information to infer the channel, keep `UNKNOWN` and report the undetermined count.

### 5.2. Backfill Only With Evidence

~~~sql
-- Example: only if the business confirms references starting with WEB- identify WEB orders.
UPDATE legacy_orders
SET order_channel = 'WEB'
WHERE order_channel IS NULL
  AND external_reference LIKE 'WEB-%';
~~~

No rule justifies assuming all orders before 2026 came from `STORE`. Guessing and filling a wrong default makes historical dashboards "look complete" while destroying trustworthiness.

### 5.3. Keep Transition State Observable

~~~sql
SELECT COALESCE(order_channel, '<NULL>') AS channel,
       COUNT(*) AS rows
FROM legacy_orders
GROUP BY COALESCE(order_channel, '<NULL>')
ORDER BY rows DESC;
~~~

When the business permits `UNKNOWN` as a meaningful value, you can add a `CHECK` constraint restricting the domain without forcing all `UNKNOWN` values away yet:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_channel
CHECK (order_channel IN ('WEB', 'STORE', 'PARTNER', 'UNKNOWN'))
NOT VALID;
~~~

**`CHECK` does not enforce non-null.** Enforcing `NOT NULL` requires a separate step after verifying new writers never send `NULL` and existing data has been cleaned.

## 6. Changing Data Types: Bugs Often Lie in Semantics, Not Syntax

Changing **`amount_text TEXT → total_amount_vnd BIGINT`** is not just changing a storage type:

- Strings may be malformed, contain separators, or have whitespace.
- Numbers may exceed `BIGINT` bounds.
- Not all rows share the same currency.
- Negative refunds/credits might reside in the legacy column even though the new rule allows only positive sales orders.
- Some values may be in **VND** while others are in **thousands of VND** if ingested from different sources.
- Old clients may write `amount_text` while new clients write `total_amount_vnd`.

Ignoring semantics and running `CAST` can yield a column with the right type and **wrong money**.

### 6.1. Direct `ALTER TYPE`: When to Avoid It?

Direct SQL example:

~~~sql
-- Illustrative only; DO NOT run in production without profiling.
ALTER TABLE legacy_orders
ALTER COLUMN amount_text TYPE BIGINT
USING btrim(amount_text)::BIGINT;
~~~

Conversion fails if any string is unparseable or overflows. Depending on the type, DBMS, and version, `ALTER TYPE` can require heavy locks, table/index rewrites, heavy WAL, and long execution time. It also breaks **legacy readers/writers** expecting `TEXT`.

It may fit small tables, ample maintenance windows, clean data, and compatible apps. For hot tables, multi-version writers, and zero-downtime requirements, favor **shadow column + gradual transition**.

### 6.2. Add a New Column to Avoid Breaking Legacy Readers

~~~sql
ALTER TABLE legacy_orders
ADD COLUMN total_amount_vnd BIGINT;
~~~

Keep `amount_text` during transition. The next step is not immediate backfill and drop, but defining **one canonical form for new data** and ensuring active writers do not keep creating drift.

A rollout strategy:

1. Deploy readers able to handle both new and old columns, preferring the new column **only when validated**.
2. Upgrade all writers or introduce a single compatibility layer that writes **both columns in the same transaction**.
3. While any legacy writer updates only `amount_text`, do not treat the new column as synced; use a bridge/trigger/procedure or retire legacy writers before cutover.
4. Backfill historical rows using approved conversion rules.
5. Compare both columns to catch concurrent edits or newly arrived rows.
6. Switch all readers/consumers to the numeric column and enforce constraints.
7. Only after the approved compatibility window, drop `amount_text`.

**Dual-writes across two separate services/databases are not automatically atomic.** When both columns live in the same row of one database, updating both values in the **same statement/transaction** is simpler and safer.

### 6.3. Batched Backfill Accepting Only Valid Values

PostgreSQL example using a CTE to select up to 500 unmigrated rows, lock rows per batch, and skip rows locked by other workers:

~~~sql
WITH batch AS (
    SELECT order_id,
           CASE
               WHEN amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS parsed_amount
    FROM legacy_orders
    WHERE total_amount_vnd IS NULL
      AND currency_code = 'VND'
    ORDER BY order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE legacy_orders AS o
SET total_amount_vnd = b.parsed_amount::BIGINT
FROM batch AS b
WHERE o.order_id = b.order_id
  AND b.parsed_amount BETWEEN 0 AND 9223372036854775807
  AND o.total_amount_vnd IS NULL
RETURNING o.order_id, o.total_amount_vnd;
~~~

This snippet is **one batch**, intended to run repeatedly under controlled transactions and orchestration. Notes:

- Rows that are null, malformed, overflowing, or lacking `currency_code = 'VND'` are **skipped**, never turned into `0` or assumed to be VND.
- Unconvertible rows require an **exception table/output** and an assigned owner.
- `SKIP LOCKED` avoids blocking on locked rows, but does not mean they can be skipped forever; subsequent passes must revisit them.
- Keep batches short; monitor row counts, lock duration, WAL, and replication lag.
- Checking `o.total_amount_vnd IS NULL` reduces overwriting newer values, **but does not guarantee consistency on its own** if a concurrent writer modifies `amount_text` without updating the new column.
- If all remaining rows are exceptions, looping indefinitely makes no progress; classify and fix the source.

Do not treat this illustrative query as a production-tested migration tool. You need execution/retry/logging logic, transaction boundaries, rate limiting, and a dual-write contract before using it.

### 6.4. Reconciling After Type Conversion

~~~sql
-- Valid strings missing the new number or differing from the new number.
WITH candidates AS (
    SELECT order_id, amount_text, total_amount_vnd, currency_code,
           CASE
               WHEN currency_code = 'VND'
                AND amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS parsed
    FROM legacy_orders
)
SELECT order_id, amount_text, total_amount_vnd, parsed
FROM candidates
WHERE parsed BETWEEN 0 AND 9223372036854775807
  AND (
      total_amount_vnd IS NULL
      OR total_amount_vnd::NUMERIC <> parsed
  )
ORDER BY order_id
LIMIT 100;
~~~

This reconciliation query compares only rows **confirmed to be VND**; rows with `NULL` or non-VND `currency_code` must be classified separately per business policy. Also verify:

- Counts of backfilled / unbackfilled / unconvertible rows.
- Discrepancies by tenant, source, month, and status.
- Negative values if refunds need separate handling.
- Monetary totals under **original and new definitions**, without comparing groups of differing scope.
- Records modified after backfill began.

If a legacy version still writes `amount_text` alone, a single "0 errors" reconciliation check does not guarantee the state will hold one minute later. Declare cutover readiness only once **the new write path truly enforces the new contract**.

## 7. Two-Phase CHECK Tightening

A simple `CHECK` on the amount:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_amount_nonnegative
CHECK (total_amount_vnd >= 0)
NOT VALID;
~~~

In PostgreSQL, **`NOT VALID` on `CHECK`** adds the constraint without immediately scanning all existing data. Rows inserted or updated afterward must satisfy the `CHECK`, while unvalidated legacy rows may still violate it.

Once data has been cleaned:

~~~sql
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT ck_orders_amount_nonnegative;
~~~

`VALIDATE` verifies remaining rows; if it fails, fix violating rows and re-run. It consumes I/O and acquires locks, though it typically avoids some blocking inherent to direct validation; **it is not synonymous with lock-free or zero operational impact**.

### 7.1. CHECK Does Not Replace NOT NULL

With:

~~~sql
CHECK (total_amount_vnd >= 0)
~~~

a row with `total_amount_vnd = NULL` is not necessarily rejected because the `CHECK` expression does not evaluate to `FALSE`. If the amount must be present, enforce **presence**:

~~~sql
-- Run only after existing data and all writers comply.
ALTER TABLE legacy_orders
ALTER COLUMN total_amount_vnd SET NOT NULL;
~~~

On large tables, `SET NOT NULL` may require locks and a scan to prove no `NULL`s exist, depending on the DBMS/version and validated constraints. Some PostgreSQL versions can leverage a validated `CHECK` to reduce the cost of proving `NOT NULL`, but actual locking/DDL behavior must still be evaluated.

You can stage cleanup as:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_amount_present
CHECK (total_amount_vnd IS NOT NULL)
NOT VALID;

-- Only after NULLs are resolved:
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT ck_orders_amount_present;

-- Execute within an approved window:
ALTER TABLE legacy_orders
ALTER COLUMN total_amount_vnd SET NOT NULL;
~~~

This is a **preparatory technique**, not a guarantee that `SET NOT NULL` runs lock-free in every version.

### 7.2. Domain Tightening Requires Exact Mapping

For example, new statuses must belong to three values:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_status_allowed
CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
NOT VALID;
~~~

`NULL` statuses still require separate handling. Before bulk updating **`DONE → PAID`**, verify whether `DONE` meant "paid" or merely "order entry completed". A wrong mapping can cause the system to report paid revenue that was never collected.

Maintain a mapping table versioned by **source and business version**, plus logs of unclassifiable rows. Whether to use `UNKNOWN` or quarantine must be approved; never use defaults to mask invalid data.

## 8. Tenant-Scoped FOREIGN KEY Tightening

When Order and Customer belong to a tenant, a `FK` on `customer_id` alone is wrong if `customer_id` can repeat across tenants. The correct key in the case study is:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT fk_orders_customer_same_tenant
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customer_accounts(tenant_id, customer_id)
NOT VALID;
~~~

Table `customer_accounts` has `PRIMARY KEY (tenant_id, customer_id)`, so it can serve as the parent of the composite FK.

Proper sequence:

1. Profile the count of Order rows with `customer_id IS NULL`.
2. Detect Orders with non-null `customer_id` that have **no Customer in the same tenant**.
3. Define rules for deleted Customers, guest accounts, and migrated records.
4. Ensure new writers create Customer prior to or in the same transaction as needed.
5. `ADD FK ... NOT VALID` to avoid validating all legacy rows immediately.
6. Clean/backfill; run `VALIDATE`.
7. If `customer_id` is mandatory, apply `NOT NULL` **after a separate business decision**.

~~~sql
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT fk_orders_customer_same_tenant;
~~~

**`FK` does not enforce `customer_id NOT NULL`.** For a composite key `(tenant_id, customer_id)`, when `tenant_id` is non-null and `customer_id` is `NULL`, a `MATCH SIMPLE` FK skips the reference check. `NOT NULL` enforces required presence, but cannot by itself decide whether guest orders are allowed.

### 8.1. FK Does Not Automatically Create a Child-Side Index

PostgreSQL does not automatically index FK columns on the child table. If queries join Orders by Customer and Customer deletes/updates perform referential checks, consider:

~~~sql
-- On active tables, choose timing carefully and monitor resources.
CREATE INDEX CONCURRENTLY idx_orders_customer_tenant
ON legacy_orders (tenant_id, customer_id);
~~~

Measure query plans and write overhead; do not add indexes merely because an FK exists. **`CREATE INDEX CONCURRENTLY` cannot run inside a PostgreSQL transaction block**; migration tooling must schedule an appropriate DDL phase.

## 9. Tightening UNIQUE Without Losing Valid Records

Suppose `external_reference` must now be unique **within a tenant**. Before adding `UNIQUE`, distinguish:

- One order **ingested twice** with the same `external_reference`: may be merged after reconciling order lines and payments.
- Two valid orders sharing a reference from different source systems: may need key **`(tenant_id, source_system, external_reference)`** instead of a two-column key.
- `NULL` references: allow manual orders without a reference, or require every order to have one?
- References differing only in casing or whitespace: should they be normalized, and could that collapse two distinct business IDs?

### 9.1. Do Not Blindly Delete Duplicates

~~~sql
SELECT tenant_id, external_reference,
       COUNT(*) AS row_count,
       ARRAY_AGG(order_id ORDER BY order_id) AS order_ids
FROM legacy_orders
WHERE external_reference IS NOT NULL
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1;
~~~

Never run a `DELETE` keeping `MIN(order_id)` if duplicate Orders carry different Payments, Shipments, or Refunds. Determine source identity, merge/alias rules, FK re-parenting, history, and traceability.

### 9.2. Creating a Unique Index With Less Write Blocking

Once data is clean and new writers cannot produce duplicates:

~~~sql
-- Run outside a transaction block in a dedicated migration step.
CREATE UNIQUE INDEX CONCURRENTLY idx_orders_tenant_external_ref
ON legacy_orders (tenant_id, external_reference);
~~~

Standard PostgreSQL `UNIQUE` allows multiple `NULL`s for `external_reference`; if `NULL` must be disallowed, add `NOT NULL` separately. Once built successfully, the index can back a constraint if eligible:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT uq_orders_tenant_external_ref
UNIQUE USING INDEX idx_orders_tenant_external_ref;
~~~

**Do not create a partial or expression index and expect to attach it as a `UNIQUE` constraint via `USING INDEX`**; indexes and constraints have different requirements. **`CREATE UNIQUE INDEX CONCURRENTLY`** can fail on concurrent duplicates and leave behind an invalid index; inspect the catalog and plan cleanup/retries. It does not solve all transaction/locking issues by itself.

### 9.3. Point-in-Time vs. Full-Lifecycle Uniqueness

A coupon might allow "only one active at a time" while permitting multiple failed attempts in history. A username might or might not be reusable after soft deletion. An email may be unique per tenant rather than globally.

If uniqueness applies only to `active` records, specify the **predicate**, state-transition permissions, and concurrent transition handling. A partial unique index may fit, but the invariant must be stated accurately before choosing the mechanism. Never conflate "currently unique" with "never duplicated in history".

## 10. Comparing Four Constraint Types Under Gradual Tightening

| Constraint | Protects | Legacy Data Checks Required | PostgreSQL & Notes |
| --- | --- | --- | --- |
| **NOT NULL** | Column must have a value | `COUNT` of `NULL`s | `SET NOT NULL` after backfill; assess scan/lock impact |
| **CHECK** | Row-local condition | Violating rows; `NULL` under 3-valued logic | Supports `NOT VALID` and `VALIDATE` |
| **FOREIGN KEY** | Reference to parent key | Orphans, tenant scope, and `NULL`s | Supports `NOT VALID`/`VALIDATE`; child index is not automatic |
| **UNIQUE** | No two equal keys in scope | Duplicates and `NULL` rules | Use `CREATE UNIQUE INDEX CONCURRENTLY` as eligible; no `NOT VALID` path like `CHECK`/`FK` |
| **PRIMARY KEY** | Unique, non-null row identifier | Duplicates/`NULL`s | Pick business/surrogate key matching grain; consider partitioning |

**Common mistake:** assuming adding `NOT VALID` makes a background process automatically validate the constraint later. In PostgreSQL, you must explicitly run **`VALIDATE CONSTRAINT`** per plan. Tables with unvalidated constraints must still be monitored with migration status clearly communicated.

**Another mistake:** believing `UNIQUE (tenant_id, external_reference)` enforces global uniqueness. It enforces uniqueness only within a tenant. Global uniqueness in a truly sharded multi-database system requires a global owner/registry or cross-shard coordination; per-shard `UNIQUE` is insufficient.

## 11. Application Compatibility During Transition

A successful schema migration is not enough if running application versions are incompatible.

| Phase | Old Reader | Old Writer | New Reader | New Writer |
| --- | --- | --- | --- | --- |
| Expand nullable new column | Continues reading old column | Continues working if schema permits | May try reading new with controlled fallback | Can dual-write |
| Backfill | Continues operating | **Risk of drift** if writing only old column | Must verify consistency | Writes both per contract |
| Cutover | Must be retired or upgraded | **Must no longer write inconsistently** | Reads new canonical column | Writes new canonical column |
| Contract drops old column | May break | May break | Works if independent of old column | Works if contract is complete |

### 11.1. Schema Versions and API Contracts

An attribute can live in many places:

- Database column.
- JSON field in an API.
- Field in Kafka/CDC events.
- ORM model.
- Avro/Protobuf schema or organization schema registry.
- Data warehouse tables and dashboards.
- Batch import/export scripts.

**Adding a database column does not automatically add an API field.** Conversely, an API reader requiring a non-null new field can fail even while the database column is nullable and backfilling is in progress. Document compatibility at every layer.

### 11.2. Do Not Treat `COALESCE` as a Permanent Solution

During transition, a query might read:

~~~sql
-- ILLUSTRATIVE bridge when both values follow an agreed policy.
SELECT order_id,
       COALESCE(total_amount_vnd,
                CASE
                    WHEN currency_code = 'VND'
                     AND amount_text IS NOT NULL
                     AND btrim(amount_text) ~ '^[0-9]+$'
                    THEN btrim(amount_text)::NUMERIC
                    ELSE NULL
                END) AS amount_value
FROM legacy_orders;
~~~

Yet this example returns `NUMERIC` and does not guard overflow. It is **not** the final type contract; moreover, fallbacks can hide backfill bugs and produce differing results across readers. For published KPIs, use **verified canonical tables/views**; use controlled fallbacks only during the compatibility window.

### 11.3. Single Source of Truth and Write-Authority Handover

During dual-write, know which column is **authoritative**:

- While the legacy source is authoritative, `total_amount_vnd` is a refreshed projection.
- Once the new source is authoritative, `amount_text` is merely a representation for old clients.
- At cutover, write authority must transfer cleanly so two writers do not mutate two columns under conflicting rules.

If using triggers to sync, define update direction, parse-error handling, recursion prevention, and conflict resolution. Never add triggers that blindly "overwrite whichever changed least recently" without an authority rule.

## 12. Data Transformations With Semantic Impact: Beyond `TEXT → BIGINT`

Some changes look like type changes but are actually **business model changes**.

### 12.1. Currency, Exchange Rates, and Minor Units

In the Orders case, `total_amount_vnd` is `BIGINT` but only valid when amounts are genuinely whole VND. If an old row has `currency_code = 'USD'`, never turn `amount_text = '100'` into `100` VND.

Valid business approaches:

- Keep **`amount_minor_units BIGINT + currency_code`** using each currency's minor unit against a currency catalog.
- Use **`NUMERIC(p, s)`** when fixed-precision decimals are required.
- If a converted VND metric is needed, store **exchange rate, rate source, and effective timestamp**, keeping original and converted amounts distinct.
- Quarantine records with unknown units rather than converting arbitrarily.

A multi-currency transaction table cannot be "normalized" simply by appending `_vnd` to a column without a conversion process.

### 12.2. Changing Status Definitions

Suppose legacy `DONE` meant "processing finished" while new `PAID` means "payment settled". This is not a 1–1 mapping. Fixing it requires Payment data or historical events.

~~~text
OLD: DONE
     /    \
   paid   unpaid
     \    /
NEW: PAID or PENDING/COMPLETED_UNPAID depending on domain
~~~

A `CHECK` allowing `PENDING/PAID/CANCELLED` does not fix this semantic gap. You may need to **separate `payment_status` from `fulfillment_status`** rather than cramming two lifecycles into one `status` column.

### 12.3. Converting Timestamps and Timezones

A `TEXT` column storing `2026-11-22 08:00` does not identify an instant without knowing the source timezone. Casting directly to `TIMESTAMPTZ` under the session timezone can produce different instants across environments.

Determine:

- Did legacy data store UTC, store-local time, or server-local time?
- Was the original offset or IANA timezone recorded?
- Are there events during DST ambiguous/non-existent local hours?
- Does business date use the Store's timezone or the organization's timezone?
- When an instant cannot be deduced, is a conservative rule or an unknown marker allowed?

Write conversion migrations only after conventions are explicit. For instance, for a legacy timestamp **confirmed** to be Vietnam local time:

~~~sql
-- Illustrative interpretation of a TIMESTAMP WITHOUT TIME ZONE.
SELECT TIMESTAMP '2026-11-22 08:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh'
       AS observed_instant;
~~~

This is a **temporal semantics change**, not just a SQL type cast.

### 12.4. Composite Fields Into Child Relations

If the old schema stored a list of product IDs in `TEXT`/`JSON` and the new schema requires `OrderLine` with an FK to `Product`, split elements, define grain, and avoid false deduplication. A JSON array with two entries for the same SKU may represent **two valid purchase lines**, not duplicates.

The migration must define **line identity**, quantity, historical unit price, keys, and relationships, then verify completeness before dropping the legacy structure.

## 13. Concurrent Write Paths and Drift Risks During Backfill

A batch job running for hours will encounter rows modified concurrently. Small batches alone are **not enough** without a concurrency contract.

### 13.1. Race Schedule That Causes Drift

~~~text
T1: Job reads amount_text = "100000"
T2: API updates amount_text to "120000" and COMMITs
T1: Job writes total_amount_vnd = 100000
Result: old column 120000, new column 100000
~~~

`T1` may filter `total_amount_vnd IS NULL` and still write the stale value unless rows are properly locked/rechecked. A `FOR UPDATE` CTE locks rows inside the batch transaction, yet **after `COMMIT`**, a legacy writer can still update the old column without updating the new one. Therefore:

1. Ensure writers already update **both representations together** or write only the new canonical form per rules.
2. Use transactions and row locking in batches, or optimistic checks on version/source columns.
3. Have detection/remediation mechanisms for drift before cutover.
4. Reconcile continuously during backfill and gradual rollout.

### 13.2. Batches Need Checkpoints and Idempotency

A batch is safe when re-running produces no new errors. Backfilling `NULL` with a deterministic value can be idempotent when conditions hold; updating an amount by **incrementing** instead of assigning will double-count on retry.

Record run metadata in existing deployment systems or approved migration logs, including:

- Migration/version and processed key range.
- Counts of succeeded, skipped, and failed rows plus error codes.
- Timestamps, batch size, and commit duration.
- PK range or cursor if partitioned, accounting for late-arriving/updated rows behind the cursor.
- Checkpoints and re-scan strategy for previously ineligible rows.

When running multiple backfill workers concurrently, **`SKIP LOCKED`** avoids lock waits but does not replace verifying completed rows or revisiting skipped rows.

### 13.3. Do Not Hold Long Table Locks for Coding Convenience

A single-transaction `UPDATE` across millions of rows can:

- Hold row locks for a long time and spike contention.
- Generate huge WAL volume and replication lag.
- Increase vacuum pressure and bloat.
- Complicate pause/resume and rollback.
- Time out critical API requests.

Size batches from **measurements**, rather than hardcoding 500 everywhere. Start small, measure latency/lag, tune against SLOs, and pause if load spikes.

### 13.4. Handling Stuck Batches

If 100 rows remain `NULL` because they cannot be parsed, re-scanning them endlessly wastes resources with zero progress. Route them to an exception table/list with reason codes like `INVALID_FORMAT`, `OVERFLOW`, `UNKNOWN_CURRENCY`, `MISSING_CUSTOMER`, or `SOURCE_CONFLICT`.

Data remediation must define who can approve corrected values. If a money column holds invalid values, never substitute `0` or meaningless defaults just to pass `NOT NULL` and declare completion.

## 14. Zero-Downtime Is a Measured Goal, Not a Syntax Property

Even short-looking DDL statements can wait on locks. Separate:

- **Statement execution time** on a test DB.
- **Lock acquisition wait time** when production has long transactions.
- **Impact on active writers/readers**.
- **Scan/rewrite volume**, disk space, and WAL.
- **Rollback mechanism** if migration fails midway.

In PostgreSQL, timeouts let DDL fail fast instead of queuing indefinitely behind locks:

~~~sql
-- Illustrative only inside an approved migration session.
SET lock_timeout = '2s';
SET statement_timeout = '30s';

ALTER TABLE legacy_orders
ADD COLUMN order_channel_note TEXT;
~~~

A simple `ADD COLUMN` usually completes quickly, yet still requires metadata locks. The snippet above **does not prove zero downtime**, and `order_channel_note` is merely an operational example, not a required column of the Orders case.

### 14.1. DEFAULT and PostgreSQL Versions

Adding a column with a constant `DEFAULT` and how the DBMS materializes values for existing rows may be metadata-optimized in some PostgreSQL versions. A volatile `DEFAULT` expression or different type change can incur much higher cost.

Crucial semantics:

~~~sql
ALTER TABLE legacy_orders
ALTER COLUMN order_channel SET DEFAULT 'UNKNOWN';
~~~

**`SET DEFAULT` applies only to subsequent `INSERT`s that omit the column**; it does not clean up existing `NULL`s. Moreover, an `INSERT` explicitly passing `NULL` does not receive the `DEFAULT`. Distinguish application policy, `DEFAULT`, and `NOT NULL`.

### 14.2. Sequencing DDL Appropriately

A reference rollout schedule:

| Phase | Change | Gate to Proceed |
| --- | --- | --- |
| A | Nullable new column, read old/new code | Zero read/write errors |
| B | Dual-write or compatibility writer | No new drift introduced |
| C | Checkpointed backfill with exception tracking | All eligible rows converted |
| D | `CHECK`/`FK NOT VALID` and validation | Zero violations in committed scope |
| E | `CREATE UNIQUE INDEX CONCURRENTLY` | No duplicates; index valid |
| F | `SET NOT NULL`, switch all readers | Zero `NULL`s and no legacy writers |
| G | Drop legacy column after soak window | Approved recovery plan in place |

This is not a single-transaction schedule. **`CREATE INDEX CONCURRENTLY`** in PostgreSQL cannot run inside a transaction block, while some `ALTER TABLE` steps may be grouped differently. Never wrap everything in one `BEGIN/COMMIT` SQL file without checking each statement's semantics.

## 15. Three-Level Migration Testing

### 15.1. Schema and Constraint Testing

At minimum test:

- Are valid row `INSERT`s accepted?
- Are `NULL` `INSERT`s into `NOT NULL` columns rejected?
- Are negative amounts or out-of-domain statuses rejected?
- Are Orders referencing a Customer from another tenant rejected?
- Are two Orders in the same tenant with the same `external_reference` rejected?
- Are two different tenants with the same `external_reference` accepted per tenant scope?
- How do `DELETE`/`UPDATE` on a referenced Customer behave per policy?
- Do legacy writers using columnless `INSERT`s break?

Do not rely on tests that merely prove "`ALTER` returned exit code 0".

### 15.2. Existing-Data Testing

Build a test dataset covering edge cases:

| Case | Expectation |
| --- | --- |
| Amount `"100000"` and currency `VND` | Converts to `100000` `BIGINT` |
| Amount `" 100000 "` and currency `VND` | Trims and converts per policy |
| Amount `"1,000"` | Not auto-interpreted without locale rule |
| Amount `NULL` | Reported missing, not turned into `0` |
| Amount exceeding `BIGINT` | Quarantined / type adjusted / source fixed |
| Currency `USD` when target is `VND` | Not copied as VND |
| Customer `NULL` | Handled per guest policy or fixed |
| Customer from different tenant | Detected and resolved before FK |
| Duplicate `external_reference` | Source investigated, not blindly deleted |
| Status `DONE`/`NULL` | Evidenced mapping or exception |
| Row edited by writer during backfill | No post-commit divergence |
| Retry of same batch | Does not inflate totals or duplicate rows |

### 15.3. Compatibility and Concurrent Load Testing

A complete test should simulate:

1. Old app reading `amount_text`.
2. New app reading `total_amount_vnd`.
3. Upgraded writer updating both fields.
4. Concurrent backfill job running.
5. Some tenants holding unresolved bad data.
6. Constraints starting `NOT VALID` then `VALIDATE`d.
7. A row updated mid-backfill.
8. Rolling back the application one version before `contract`.
9. A long transaction holding locks when migration attempts `ALTER`.
10. Replication/CDC absorbing high change volume and recovering on pause/resume.

Acceptance criteria should measure **p95/p99 request latency**, lock waits, throughput, replication lag, exception counts, divergent rows, and KPI accuracy. "It ran fast on staging" does not prove production has identical resources or data skew.

## 16. Reconciliation and Cutover Gate

Row-count checks alone cannot prove a migration is correct. Opposite monetary errors can cancel out in a global sum.

### 16.1. Checking NULLs and Out-of-Domain Values

~~~sql
SELECT COUNT(*) AS total_orders,
       COUNT(*) FILTER (WHERE total_amount_vnd IS NULL) AS missing_amount,
       COUNT(*) FILTER (WHERE total_amount_vnd < 0) AS negative_amount,
       COUNT(*) FILTER (WHERE order_channel IS NULL) AS missing_channel,
       COUNT(*) FILTER (
           WHERE status IS NULL
              OR status NOT IN ('PENDING','PAID','CANCELLED')
       ) AS status_invalid
FROM legacy_orders;
~~~

If a historical subset is **permitted to remain `NULL`** while new data must be non-null, assess whether a global constraint reflects the actual rule. A date- or order-type-conditional `CHECK` is another option, provided users are not misled into assuming all rows are complete.

### 16.2. Checking Monetary Discrepancies by Tenant

~~~sql
WITH parsed AS (
    SELECT tenant_id, order_id, amount_text, total_amount_vnd,
           CASE
               WHEN currency_code = 'VND'
                AND amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS source_amount
    FROM legacy_orders
)
SELECT tenant_id,
       COUNT(*) AS total_rows,
       COUNT(*) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
             AND total_amount_vnd IS NULL
       ) AS not_migrated,
       COUNT(*) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
             AND total_amount_vnd::NUMERIC <> source_amount
       ) AS mismatched,
       SUM(source_amount) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
       ) AS source_total,
       SUM(total_amount_vnd) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
       ) AS migrated_total
FROM parsed
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

This reconciles **eligible rows confirmed to be VND**. It does not replace handling `USD`/`NULL`/malformed rows; those must appear in separate exception reports rather than vanishing behind a filter.

### 16.3. Business-Key Integrity Checks

~~~sql
SELECT tenant_id, external_reference,
       COUNT(*) AS cnt
FROM legacy_orders
WHERE external_reference IS NOT NULL
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1;

SELECT o.tenant_id, o.order_id
FROM legacy_orders AS o
LEFT JOIN customer_accounts AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
~~~

Both result sets should be **empty** before applying `UNIQUE`/`FK` within mandatory scope. If non-empty, log counts, causes, and remediation decisions rather than blindly applying constraints and blaming the database.

### 16.4. Go / No-Go Gate

Approve cutover when:

- Old writers are no longer allowed to mutate the legacy representation alone.
- In-scope data is migrated or covered by approved exceptions with explicit scope.
- All constraint tests pass; existing data complies with enforced invariants.
- Zero dual-column divergence in the published scope.
- Dashboards and ETL share identical money/status/customer definitions post-migration.
- Schema operations stay within lock-time and replication-lag budgets.
- A realistic rollback plan exists and the **irreversible point** is signed off.
- Business owners sign off on mapping rules and exception lists.

**Never substitute a 99.9% completion rate for a business decision.** The remaining 0.1% might be high-value orders, wrong-currency rows, or legal contracts worth more than the other 99.9%.

## 17. Rollback and Forward-Fix When Migrations Fail

A migration can break at several stages:

| Detected Failure | What Can Be Done? | What to Avoid |
| --- | --- | --- |
| `ADD COLUMN` fails before use | Retry after resolving lock/config issues | Holding locks indefinitely |
| Backfill stalls mid-run | Resume from checkpoint idempotently | Re-running additive math that duplicates totals |
| Mis-mapped records found | Quarantine, fix source, selectively re-backfill | Writing meaningless defaults |
| `VALIDATE FK/CHECK` fails | Clean violating rows, re-validate | Dropping the constraint and calling it done |
| `CREATE UNIQUE INDEX CONCURRENTLY` fails | Check valid/invalid index state, dedup, controlled retry | Leaving invalid indexes unmonitored |
| New reader has bug before contract | Point reader back to legacy column while kept in sync | Assuming code rollback reverts row data |
| Legacy column already `DROP`ped | Forward-fix, backup restore, or potentially lossy reverse migration | Promising a trivial rollback |
| Reports wrong post-cutover | Halt publishing, reconcile, version reports | Silently patching published figures |

### 17.1. Application Rollback Differs From Data Rollback

Reverting to a previous build does **not** recreate `amount_text` if that column was dropped. Conversely, rolling back an `ALTER` script in a transaction undoes DDL before `COMMIT`, but does not revert external side effects or previously committed steps.

Explicitly document:

- **Safe rollback window:** both columns exist and writers keep them synced.
- **Cutover point:** canonical writes move to the new column.
- **Irreversible/contract point:** legacy representation dropped or new values allowed that cannot fit the old type.
- **Restore strategy:** backups, snapshots, logical replay, forward migration, and realistic recovery time.

Never rely on a rollback plan targeting an old column that has stopped receiving updates for days.

### 17.2. A Down Migration Might Not Exist

When moving from `BIGINT` to `INT`, new values exceeding `INT` cannot reverse losslessly. When normalizing `status` into multiple tables, collapsing back into a single `TEXT` loses semantics. When duplicate rows are merged, undoing requires preserved mappings and historical payloads.

Thus, "every migration must have `down.sql`" is not enough. What is needed is a **practical recovery plan** covering data created after cutover.

## 18. Partitioned or Distributed Data

Schema evolution in partitioned/sharded systems adds constraints:

- `UNIQUE` on a partitioned table may require including the partition key; global uniqueness is not automatic.
- Backfills across tenant/time partitions may finish unevenly.
- Shards running different schema versions can fail when routing changes.
- CDC events may carry mixed old/new schemas; consumers must handle both.
- Cross-database FKs do not enforce automatically like local FKs.
- Dual-read/dual-write between old and new models may be needed, requiring clear ownership and fencing against split-brain.

When adding a column across shards, track **available schema version per shard**. Do not route traffic assuming retries will paper over un-migrated shards. A rollout can proceed **read compatibility first, expand schema, new writers, backfill, tighten constraints, and contract** cluster by cluster, with explicit rules for cross-cluster requests.

If tenant-level `UNIQUE` spans shards, ensure all records for the same tenant/key route to the same enforcement boundary or use a global registry. Never assume per-shard `UNIQUE` guarantees a global invariant.

## 19. Document, Graph, and Warehouse Systems Also Evolve Schemas

### 19.1. Document: Missing Fields and Mixed Shapes

Legacy document:

~~~json
{
  "orderId": "O-901",
  "amount": "200000",
  "status": "DONE"
}
~~~

New document:

~~~json
{
  "orderId": "O-901",
  "totalAmountVnd": 200000,
  "currencyCode": "VND",
  "paymentStatus": "PAID",
  "fulfillmentStatus": "SHIPPED",
  "schemaVersion": 2
}
~~~

Adding document fields does not require a relational `ALTER TABLE`, yet old documents still lack the new fields. Queries, indexes, validators, consumers, and application logic must handle **versions** and transformation rules.

Do not assume `DONE` equals `PAID` and `SHIPPED` as in the illustrative JSON; convert only with source evidence. New document validators may reject old documents upon update unless compatibility/backfill paths are in place.

### 19.2. Graph: Changing Edge Types or Hierarchy Constraints

Suppose a legacy system used edges:

~~~text
Employee -[REPORTS_TO]-> Manager
~~~

Later adding role-based permissions and effective times:

~~~text
Employee -[REPORTS_TO {valid_from, valid_to}]-> Manager
Employee -[ACTS_AS   {role, valid_from, valid_to}]-> Organization
~~~

When evolving, determine:

- Can an Employee have multiple Managers at the same instant?
- Can `REPORTS_TO` intervals overlap?
- Are cycles allowed in the organizational graph?
- When edge types change, do legacy traversal queries remain valid?
- In partitioned graphs, do constraints hold globally or only per subgraph?

Graph schema evolution is not merely relabeling; inventory old edges, missing temporal attributes, and path-multiplication risks when multiple valid paths exist.

### 19.3. Warehouse: New Columns Do Not Mean New KPIs Are Complete

Adding an `OrderChannel` dimension to `FactSales` leaves pre-2026 facts without a channel. Dashboards must not lump all historical revenue into `WEB`; display **`UNKNOWN`**, coverage, and the date when complete tracking began.

If redefining the `NetSales` measure, decide whether to **restate** past periods or introduce a new measure/version. Where materialized views or summary tables store old figures, backfill/refresh affected scopes rather than changing only a dashboard SQL formula and forgetting derived tables.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `ALTER` before profiling | DDL fails or corrupts data | Measure `NULL`s, duplicates, overflows, orphans, skew |
| Adding `NOT NULL` immediately on hot table | Old writers and old rows fail | Nullable → writers → backfill → validate → `NOT NULL` |
| Replacing `NULL` with `0` | Hides missing data, skews money/KPIs | Unknown/quarantine and business sign-off |
| Converting `TEXT` to `BIGINT` without checking currency | `USD` stored as `VND` | Define units, conversion, and sources |
| Mapping `DONE` to `PAID` without evidence | Reports overstate collected revenue | Split statuses or map with verification |
| Single backfill then drop old column | Legacy writers keep mutating old column | Coordinate writers/triggers/dual-write and reconcile |
| Believing `CHECK` enforces `NOT NULL` | `NULL` satisfies `CHECK` under 3-valued logic | Separate `CHECK IS NOT NULL` / `NOT NULL` |
| Believing composite `FK` checks when one part is `NULL` | `MATCH SIMPLE` skips check | Add `NOT NULL` per business scope |
| Believing per-shard `UNIQUE` is global `UNIQUE` | Cross-shard duplicates | Adjust routing / registry / global owner |
| Using `NOT VALID` on `UNIQUE`/`PK` like `CHECK` | Invalid DDL plan | `CREATE UNIQUE INDEX CONCURRENTLY` and verify |
| Running `CREATE INDEX CONCURRENTLY` inside `BEGIN` | Rejected by PostgreSQL | Separate independent migration phase |
| Ignoring invalid indexes after failure | Wastes resources or blocks retries | Inspect catalog and clean up safely |
| Huge `UPDATE` in one transaction | High locks / WAL / replication lag | Batch, checkpoint, and rate limit |
| Not testing hot/edge data | Production fails despite staging pass | Representative datasets and load |
| Matching row counts implies correctness | Offsetting errors cancel out | Reconcile by business key and slices |
| Relying only on `down.sql` without backups | Post-contract data loss | Restore / forward-fix and mark irreversible point |
| Dropping column right after deploying new reader | Legacy batches/CDC/workers still use it | Inventory all consumers and compatibility window |

## 21. Guided Case Exercises

### Exercise 1. Adding a Mandatory Attribute

**Prompt:** Table `Orders` has 10 million rows. Product wants `order_channel NOT NULL` for all rows. Legacy sources never stored channel. What should you do?

**Solution hint:** Add nullable first, confirm whether `UNKNOWN` is business-acceptable, update writers, backfill rows with evidence, measure coverage. Apply `NOT NULL` only once all in-scope rows have valid values and writers never emit `NULL`. Do not default all history to `WEB`.

### Exercise 2. Validating Money Strings

**Prompt:** `amount_text` contains `"1000"`, `" 1000 "`, `"1,000"`, `"-50"`, `NULL`. Can you `CAST` directly to `BIGINT`?

**Solution hint:** No. Profile first and define rules for commas, minus signs, units, and `NULL`. Convert only policy-valid strings and route the rest to an exception list for resolution.

### Exercise 3. Tightening `CHECK` Without `NOT NULL`

**Prompt:** You added `CHECK (total_amount_vnd >= 0)` and still found `NULL` rows. Is PostgreSQL buggy?

**Solution hint:** No. `CHECK` does not require the expression to be `TRUE` under three-valued `NULL` logic; `NULL` is not rejected. Add `NOT NULL` after cleaning data or stage `CHECK (... IS NOT NULL)` and validate.

### Exercise 4. Tenant-Scoped `FOREIGN KEY`

**Prompt:** Customer ID `101` exists in both tenant 1 and tenant 2. Tenant 1 orders store `customer_id = 101`. Does an FK on `customer_id` alone protect tenant isolation?

**Solution hint:** No. Use a composite FK `(tenant_id, customer_id)` referencing the matching unique key on Customer; handle `NULL`s/orphans and guest-order policies.

### Exercise 5. `UNIQUE` on References

**Prompt:** Two orders share `external_reference = "R001"` in different tenants. Business requires uniqueness only within a tenant. What key should you choose?

**Solution hint:** `UNIQUE (tenant_id, external_reference)`. Do not enforce table-wide `UNIQUE (external_reference)` if tenants can reuse references. Define handling for `NULL`s and ID generation.

### Exercise 6. Duplicate Appears During `CREATE INDEX`

**Prompt:** Profiling showed zero duplicates, yet `CREATE UNIQUE INDEX CONCURRENTLY` failed later. Why?

**Solution hint:** Active writers may have inserted duplicates between profiling and index build, or unprofiled data existed. Guard the write path, investigate duplicates, inspect invalid indexes, and retry cleanly.

### Exercise 7. Legacy Writer Still Running

**Prompt:** New readers use `total_amount_vnd`. An old batch still updates only `amount_text`. Backfill hit 100% yesterday. Can you drop `amount_text` now?

**Solution hint:** Not yet. The old batch introduces new drift. Update writers/compatibility, reconcile after stopping legacy-only writes, then cut over; contract only once no consumers depend on it.

### Exercise 8. Re-running Backfill

**Prompt:** A job ran `UPDATE amount = amount + parsed_amount`, crashed midway, and restarted. What is the risk?

**Solution hint:** Processed rows get double-counted. Backfills must be idempotent (deterministic assignment with version/condition guards), checkpointed, and verified against source payloads for safe restarts.

### Exercise 9. Foreign-Currency Data

**Prompt:** `amount_text = "100"` has `currency_code = 'USD'`. The new column is `total_amount_vnd BIGINT`. Should you write `100`?

**Solution hint:** No. Decide whether to store original currency or convert using recorded exchange rates, timestamps, and rounding policy; 100 USD is not 100 VND.

### Exercise 10. Status Semantic Shift

**Prompt:** Legacy `DONE` could mean delivery completed, whereas `PAID` means payment settled. Can you `UPDATE` all `DONE` to `PAID`?

**Solution hint:** No. They represent two distinct workflows. Check Payment/fulfillment facts, potentially split into separate columns/statuses, and migrate using evidence.

### Exercise 11. `VALIDATE CONSTRAINT` Fails

**Prompt:** `ADD FK ... NOT VALID` succeeded, but `VALIDATE` failed due to deleted Customers. Should you drop the FK to finish the migration?

**Solution hint:** No. Decide how to handle orphans—fix references/mappings/guest policies or exclude out-of-scope data per business decision—then re-validate; while unvalidated, disclose the state clearly.

### Exercise 12. Time-Based `PARTITION`

**Prompt:** `Events` is partitioned by `occurred_at` with `PK (occurred_at, source_event_id)`, yet the same event arrived with mismatched timestamps across two months. Is `source_event_id` guaranteed unique?

**Solution hint:** No. Because `occurred_at` differs in the composite key, both rows can coexist. You need a scoped deduplication owner/registry by event ID or a suitable distributed uniqueness mechanism.

### Exercise 13. Rollback After `DROP`

**Prompt:** You `DROP`ped `amount_text` and ingested a week of new `BIGINT` data. Does rolling back the app code restore the schema and data?

**Solution hint:** Not automatically. You may need reverse migrations, backup/replay, or forward-fix, and some new values may not fit the old model. Mark the irreversible point explicitly.

### Exercise 14. Performance Testing

**Prompt:** Migration took 2 seconds on 5,000 Orders in staging. Production has 100 million Orders and long transactions. Can you promise zero downtime?

**Solution hint:** No. Measure lock acquisition, scan/rewrite, WAL, replication lag, batch throughput, and API performance under representative skew and load rather than extrapolating linearly from small tables.

### Exercise 15. Converting JSON to Child Table

**Prompt:** An Order document contains two lines with the same SKU at different unit prices. When creating relational `OrderLine`, should you deduplicate by `(order_id, sku_id)`?

**Solution hint:** Not automatically. Both lines may be valid purchases. Define line grain and `source_line_id`/`line_no`, preserve historical prices and quantities, and verify before/after totals.

## 22. Acceptance Checklist for a Model Change

- [ ] **New invariants and semantics** approved by business owners: currency, statuses, key scopes, guest policies.
- [ ] **Legacy data profile** covers row counts, `NULL`s, duplicates, orphans, overflows, and skew by tenant/source/time.
- [ ] **Exceptions** have explicit decisions—never masked with zeros/defaults or blind deletes.
- [ ] **Expand** does not break running readers/writers outside defined assumptions.
- [ ] **Canonical source and dual-write** defined; legacy writers cannot cause undetected drift.
- [ ] **Backfill** is batched, checkpointed, idempotent on retry, and bounds transactions/locks.
- [ ] **Constraints** applied in order; `CHECK`/`FK NOT VALID` are `VALIDATE`d; `UNIQUE`/`PK` use appropriate mechanisms.
- [ ] **Compatibility** verified across APIs, ORMs, batches, CDC, event schemas, warehouse, and dashboards.
- [ ] **Reconciliation** passes by business key, currency, tenant, period, and source.
- [ ] **Concurrency** tested under simultaneous writes and backfill.
- [ ] **Performance** (locks/WAL/replication lag/p95) measured at representative scale.
- [ ] **Cutover** has Go/No-Go gates, error monitoring, and named approvers.
- [ ] **Rollback/forward-fix** boundaries defined before/after contract with verified backup/restore.
- [ ] **Model documentation** reflects keys, types, constraints, history rules, derived data, and contract versions.

## 23. Key Takeaways

- **Schema evolution changes both data and contracts**, not just DDL.
- **Adding a column does not populate historical data.** Never invent default values without business evidence.
- **Changing a type changes interpretation:** verify units, precision, overflow, time semantics, and relationships before `CAST`.
- **Tightening constraints requires empirical proof:** `COUNT NULL`, orphans, duplicates, domain values, and active writers.
- **Expand → backfill → validate → contract** enables phased rollout and compatibility windows; not every step fits in one transaction.
- **`NOT VALID` works for PostgreSQL `CHECK`/`FK`**, while `UNIQUE`/`PK` need different steps; `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block.
- **Dual-writes require one source of truth and continuous reconciliation.** A one-time backfill does not stop legacy writers from reintroducing drift.
- **Application rollback differs from data rollback**; after dropping legacy representations or accepting new values, forward-fix or restore may be the only path.
- **Keys, constraints, and derived datasets must evolve consistently in semantics** across relational, document, graph, and warehouse systems.

A reliable migration does not end when `ALTER TABLE` succeeds. It ends when **historical and new data both satisfy approved invariants, all active readers and writers interpret data consistently, reconciliations pass, and the system can operate or recover within declared boundaries**.
