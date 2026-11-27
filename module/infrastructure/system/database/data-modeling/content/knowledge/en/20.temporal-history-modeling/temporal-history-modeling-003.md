# Versioned Records with Explicit Effective Intervals

## 1. Why Version Records by Effective Interval?

In data modeling, storing only the latest value of an entity is usually straightforward: a single row with a primary key, attributes, and an `updated_at` column. Yet when the business asks **“which value applied on date X?”**, the latest row is no longer enough. An attribute can change multiple times, with each value holding true only over a defined period.

For example, a subscription platform has a `STANDARD` service plan and needs to store monthly fees by effective date:

| Price Version | Effective Interval | Monthly Fee |
|---|---|---:|
| P1 | From 2026-01-01 until before 2026-07-01 | 100,000 VND |
| P2 | From 2026-07-01 until before 2026-10-01 | 120,000 VND |
| P3 | From 2026-10-01 onward | 130,000 VND |

When invoicing for August 2026, the system must use **120,000 VND**; when displaying the fee applicable on November 15, 2026, the result is **130,000 VND**. If `monthly_fee` were simply overwritten on the service plan record, the 100,000 and 120,000 fees would vanish from the business model.

The lesson **“Versioned Records with Explicit Effective Intervals”**, in the **Time and History** chapter of the **DATABASE_DATA_MODELING** module, focuses on turning that requirement into a verifiable model: identifying business keys, partitioning time intervals, enforcing non-overlap constraints, handling edits, and designing queries. This is a core skill for translating business requirements into clear, evolvable data schemas.

After this lesson, learners should be able to do four things:

1. Distinguish the **logical entity** from **versions of the entity** and determine the effective interval for each version.
2. Select boundary conventions, precision, start/end semantics, and gap rules.
3. Design keys, constraints, indexes, and transactions so two valid versions never unintentionally coexist at the same time.
4. Answer **as-of** queries and test transitions, corrections, future-dated changes, and retroactive data.

## 2. Entity, Version, and Effective Interval Are Three Distinct Concepts

A **logical entity** is an object recognized by the business across time, such as the `STANDARD` subscription plan, a contract, an employee, or a shipping route. The entity identifier must remain stable even as its attributes change.

A **version record** is a set of values bound to an effective period. One entity can have many versions. Each version needs its own identifier so it can be referenced, tracked, and corrected through a controlled workflow.

An **effective interval** (*validity interval* or *valid-time period*) states from when until when the attributes in that version hold true under business rules. In the subscription pricing example, each version carries a fee and an effective date range. Not every column needs versioning: a plan name may remain stable while its fee changes over time; version boundaries depend on attributes that share the same change lifecycle.

The relationship can be visualized as:

~~~mermaid
erDiagram
    SERVICE_PLAN ||--o{ PLAN_PRICE_VERSION : "has price versions"
    SERVICE_PLAN {
        bigint plan_id PK
        text plan_name
    }
    PLAN_PRICE_VERSION {
        bigint version_id PK
        bigint plan_id FK
        text currency_code
        decimal monthly_fee
        daterange valid_period
        text source_decision_id
    }
~~~

`plan_id` identifies the service plan; `version_id` identifies each price version. **A new version is not necessarily a new entity.** When calculating charges, the business first identifies the plan, currency, and applicable date, then selects the matching version.

### 2.1. The Version Business Key Must Have Sufficient Scope

Suppose the `STANDARD` plan has fees in both VND and USD. If a constraint forbids overlapping intervals on `plan_id` alone, the system would block two fees in different currencies from existing concurrently, even though that data is completely valid.

The scope of a price version might be:

~~~text
(plan_id, currency_code) + valid_period
~~~

If fees also vary by **region**, **customer segment**, **sales channel**, or **price type**, those attributes may need to join the business key and uniqueness/non-overlap constraints. Do not add attributes to keys mechanically: ask **“are two values allowed to coexist at the same point in time?”**

### 2.2. Version ID Is Not Effective-Time Order

An auto-incrementing `version_id` usually reflects the order **records were created**, not necessarily **effective-date order**. The system might enter a December price in advance and then add a retroactive August decision the next day.

Therefore:

- Use `version_id` to **identify** and reference a version.
- Use `valid_from` or `lower(valid_period)` to **order by business validity**.
- Use a **separate** recording timestamp or change sequence if you need to know which version was entered into the system first.

Never infer “latest currently effective price” using `MAX(version_id)`.

## 3. Effective Interval Convention: `[from, to)`

A widely used convention is the **half-open (closed-start, open-end)** interval:

~~~text
[valid_from, valid_to)
~~~

Meaning:

~~~text
valid_from <= query_time < valid_to
~~~

Example:

~~~text
P1: [2026-01-01, 2026-07-01) → 100,000 VND
P2: [2026-07-01, 2026-10-01) → 120,000 VND
P3: [2026-10-01, +∞)          → 130,000 VND
~~~

**July 1** belongs to P2 and no longer belongs to P1. **October 1** belongs to P3 and no longer belongs to P2. Adjacent versions can have **`valid_to` of the prior version equal to `valid_from` of the next version** without overlapping.

| Query Date | Matching Version | Explanation |
|---|---|---|
| 2025-12-31 | None | Before P1's `valid_from` |
| 2026-01-01 | P1 | Start boundary is inclusive |
| 2026-06-30 | P1 | Prior to end boundary |
| 2026-07-01 | P2 | P1 has expired |
| 2026-09-30 | P2 | Last day before October 1 |
| 2026-10-01 | P3 | P3's start boundary is inclusive |

### 3.1. Why Not Make Both Bounds Inclusive?

If P1 ends on **July 1** and P2 also starts on **July 1**, both versions would hold true on that same day. Some teams try to work around this by ending P1 at **23:59:59** on June 30, but that depends on second, millisecond, or microsecond precision and easily breaks when the system upgrades timestamp granularity.

Half-open intervals avoid subtracting a smallest time unit. With a **date** column (`date`), `[2026-07-01, 2026-10-01)` covers every day from July 1 through September 30. With a **timestamp** column (`timestamptz`), it covers every instant from the start bound up to before the end bound.

### 3.2. Open-Ended Upper Bounds

For a version currently effective indefinitely based on existing information, use an **unbounded upper limit**:

~~~text
[2026-10-01, +∞)
~~~

In a two-column model, one convention is `valid_to IS NULL` meaning “no end date yet.” In PostgreSQL, `daterange` natively represents an *unbounded* upper bound. Avoid picking an arbitrary sentinel date like `9999-12-31` unless the entire system explicitly defines and enforces it as a sentinel value.

**An unbounded upper limit** does not mean the business guarantees the price will last forever; it only means no termination decision exists in the current data.

### 3.3. Choosing `date` vs. Timestamp

If a requirement says **“the fee applies per calendar day in Vietnam”**, a local date type may fit best. If it says **“access takes effect at exactly 14:30 UTC”**, a time-zone-aware timestamp is needed.

| Business Semantics | Appropriate Representation | What Must Be Agreed Upon |
|---|---|---|
| Contract takes effect on **date** July 1 | `date` or `daterange` | Which calendar/region defines the day |
| Access opens at **instant** 14:30 | `timestamptz` or `tstzrange` | Instant precision, display time zone |
| Recurring weekly Monday slot | Schedule rule model, often with time zone | DST, exceptions, holidays |
| “Start of next quarter” not yet finalized | Rule or separate draft status | Never fabricate a timestamp before it is known |

An infinite recurring schedule cannot be fully modeled by pre-generating one row per occurrence when the business truly defines a **recurrence rule**. For those cases, model the recurrence rule and exceptions—or materialize occurrence rows only when genuinely required.

## 4. Business Invariants to Clarify

A sound versioning model must first answer these questions:

1. **At most one or multiple?** On date X, for the same `plan_id` and `currency_code`, are two fees allowed to be effective simultaneously?
2. **Must coverage be continuous?** Must every day from plan launch onward have a fee, or can there be off-sale gaps?
3. **Are future records allowed?** Can a December version be added while August is still using the current fee?
4. **Are retroactive edits allowed?** If May's price was entered wrong and discovered in September, can effective history be amended?
5. **Do we need to know what the system previously recorded?** Must we answer “on August 10, what did the system then believe July's fee was?”
6. **Must finalized transaction evidence be preserved?** May prices on already-issued invoices change when pricing rules are adjusted?
7. **Should adjacent versions with identical values be merged?** If two separate decisions both set 120,000 VND, do we need two rows to preserve business justification?

The answers lead to common invariants:

| Invariant | Verification Mechanism |
|---|---|
| Every version has a valid, non-empty effective interval | `CHECK` constraint or validator |
| Within the same business key, no two effective intervals illegally overlap | Exclusion constraint or transaction-protected check |
| If continuity is required, the new interval abuts the old one | Date continuity, gap, and launch-rule checks |
| Every version has a decision source | Required column and reference/decision ID key |
| All multi-row edits are atomic | Transaction |
| Concurrent writes cannot produce conflicting timelines | Locking or optimistic versioning combined with data constraints |
| Finalized invoices retain proof of the price actually applied | Store charged amount and pricing decision reference/snapshot |

**Non-overlapping** and **gapless** are two separate conditions. A constraint preventing overlaps does not guarantee every day has a version. Whether **full time coverage is required** is a business decision.

## 5. Physical Schema Design in PostgreSQL

This section builds a versioned price table with a single **effective time** (*valid time*) axis. It serves as a hands-on PostgreSQL example; other DBMSs may require different structures and overlap-prevention mechanisms.

### 5.1. Two Tables: Parent Entity and Price Versions

~~~sql
-- Provides equality operators for bigint/text in GiST indexes.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE service_plan (
    plan_id    bigint PRIMARY KEY,
    plan_name  text NOT NULL
);

CREATE TABLE plan_price_version (
    version_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id            bigint NOT NULL
                       REFERENCES service_plan(plan_id),
    currency_code      text NOT NULL
                       CHECK (currency_code ~ '^[A-Z]{3}$'),
    monthly_fee        numeric(14, 2) NOT NULL
                       CHECK (monthly_fee >= 0),
    valid_period       daterange NOT NULL,
    source_decision_id text NOT NULL,
    recorded_at        timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_plan_price_nonoverlap
        EXCLUDE USING gist (
            plan_id WITH =,
            currency_code WITH =,
            valid_period WITH &&
        )
);

CREATE INDEX ix_plan_price_start
    ON plan_price_version (
        plan_id, currency_code, lower(valid_period)
    );
~~~

Explanation of key decisions:

- **`service_plan.plan_id`** identifies the plan stably over time; **`plan_price_version.version_id`** identifies each version record.
- **`monthly_fee numeric(14,2)`** avoids binary floating-point rounding errors common when using `float` for money. For currencies without decimals, data types and rounding rules may be chosen differently.
- **`valid_period daterange`** stores an entire date interval; `@>` tests whether it contains a date, and `&&` tests whether two intervals overlap.
- **`source_decision_id`** links the fee to an authoritative decision. In production, a foreign key to a pricing decisions table may be warranted.
- **`recorded_at`** gives an observational timestamp of row insertion. It **does not automatically make the table bitemporal** and is insufficient to recover every past interpretation once intervals are edited.
- **`ck_valid_period`** requires a non-empty range with a finite inclusive start bound and an exclusive upper bound.
- **`ex_plan_price_nonoverlap`** prevents two rows for the same plan and currency from having overlapping effective dates. PostgreSQL enforces this via a GiST index; the `btree_gist` extension enables equality comparisons on scalar columns inside the same constraint.

The exclusion constraint works even with unbounded upper intervals: a new version cannot start while an existing version extends to infinity. You must close the current interval before inserting the next one within the same transaction.

**Limitation:** a price may vary by customer tier, region, or sales channel. If an entity needs concurrent prices along those dimensions, include those exact dimensions in the table and constraint. Conversely, if a plan has only one valid price across all currencies, the business key must reflect that rule instead. The DDL here represents a concrete business contract, not a template to copy verbatim for every system.

### 5.2. Initializing Three Consecutive Effective Versions

~~~sql
INSERT INTO service_plan (plan_id, plan_name)
VALUES (7, 'STANDARD');

INSERT INTO plan_price_version (
    plan_id, currency_code, monthly_fee,
    valid_period, source_decision_id
)
VALUES
(
    7, 'VND', 100000,
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)'),
    'PRICING-2026-Q1'
),
(
    7, 'VND', 120000,
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)'),
    'PRICING-2026-Q3'
),
(
    7, 'VND', 130000,
    daterange(DATE '2026-10-01', NULL, '[)'),
    'PRICING-2026-Q4'
);
~~~

`NULL` is passed as the upper bound of `daterange` to represent an unbounded interval; this differs from setting the entire `valid_period` column to SQL `NULL`—the range column itself remains **NOT NULL**.

With these rows, the exclusion constraint accepts all pairs because the effective intervals are disjoint. If someone accidentally inserts a 125,000 VND fee effective `[2026-09-01, 2026-11-01)`, PostgreSQL rejects it because that range overlaps both P2 and P3.

## 6. Querying the Right Version by Business Date

### 6.1. Single-Date *As-Of* Query

~~~sql
SELECT
    version_id,
    plan_id,
    currency_code,
    monthly_fee,
    valid_period,
    source_decision_id
FROM plan_price_version
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_period @> DATE '2026-08-15';
~~~

On the sample data, the result is **120,000 VND**. The `@>` operator means “the range on the left contains the date on the right.”

When business rules dictate at most one fee on the queried date, valid results contain **0 or 1 row**. One row means a price was found; zero rows means **no price exists in the data for that date**. Never fall back to picking the row with the closest `valid_from` when an as-of query finds no match.

Equivalent SQL using separate `valid_from`/`valid_to` columns:

~~~sql
SELECT monthly_fee
FROM plan_price_version_columns
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_from <= DATE '2026-08-15'
  AND (
      valid_to IS NULL
      OR DATE '2026-08-15' < valid_to
  );
~~~

This snippet illustrates **an alternative schema** with two separate columns, not a query against the `daterange`-based `plan_price_version` table from section 5. The half-open semantics remain identical when changing storage layout.

### 6.2. Viewing the Full Timeline

~~~sql
SELECT
    version_id,
    monthly_fee,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to
FROM plan_price_version
WHERE plan_id = 7
  AND currency_code = 'VND'
ORDER BY lower(valid_period), version_id;
~~~

In PostgreSQL, `lower()` and `upper()` extract the range bounds. For an unbounded upper limit, `upper(valid_period)` returns `NULL`, so the UI can display **“no end date yet”** rather than showing raw `NULL`.

Do not sort the timeline by `recorded_at` when the goal is presenting **business effective order**: a version effective in the past may be entered or edited after future versions.

### 6.3. Finding Versions Overlapping a Reporting Period

~~~sql
SELECT
    version_id,
    monthly_fee,
    valid_period
FROM plan_price_version
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_period
      && daterange(DATE '2026-06-15', DATE '2026-07-15', '[)')
ORDER BY lower(valid_period);
~~~

The reporting period **June 15 to before July 15** intersects both P1 and P2. If billing charges by date range, this signals that the **billing period must be split** into effective sub-segments, then prorated or charged using approved business rules. Picking a single price based solely on the period start date can be wrong.

**Splitting intervals** and **computing charges** are separate responsibilities: the version model only identifies which prices intersect the period; charge formulas, conversion dates, rounding, and taxes must be defined separately.

## 7. Adding a Future Version Without Losing the Current Interval

In November 2026, pricing approves **140,000 VND** starting **December 1, 2026**. Because P3 currently extends from October 1 onward, you cannot simply insert `[Dec 1, +∞)`: the two ranges would overlap.

We need to transform:

~~~text
Before:
P3: [2026-10-01, +∞) → 130,000 VND

After:
P3: [2026-10-01, 2026-12-01) → 130,000 VND
P4: [2026-12-01, +∞)         → 140,000 VND
~~~

Assuming the existing data matches the example, the operations can run in one transaction:

~~~sql
BEGIN;

UPDATE plan_price_version
SET valid_period = daterange(
    lower(valid_period),
    DATE '2026-12-01',
    '[)'
)
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND lower(valid_period) < DATE '2026-12-01'
  AND upper_inf(valid_period)
RETURNING version_id, valid_period;

-- The application must verify UPDATE returns exactly one row.
-- Otherwise, ROLLBACK and re-read data before deciding.

INSERT INTO plan_price_version (
    plan_id, currency_code, monthly_fee,
    valid_period, source_decision_id
)
VALUES (
    7, 'VND', 140000,
    daterange(DATE '2026-12-01', NULL, '[)'),
    'PRICING-2026-DEC'
);

COMMIT;
~~~

`RETURNING` lets the application verify the shortened row. If `UPDATE` affects **0 rows**, the application must **ROLLBACK** rather than blindly proceeding as if the old price had been closed. This snippet illustrates the coordinated steps; so the application controls the check between UPDATE and INSERT, production code should run the transaction inside a service or stored procedure that verifies affected row counts.

The transaction must be protected from concurrent requests modifying the same price schedule. You can lock the parent `service_plan` row for plan 7, use an optimistic version on the parent row, or apply a consistent transaction/isolation strategy. The `EXCLUDE` constraint is the last line of defense against overlapping intervals; it does not resolve every business conflict on its own.

### 7.1. Pre-Recording Multiple Future Changes

In November, the business might already decide:

- From Dec 1 until before Mar 1 next year: 140,000 VND.
- From Mar 1 next year onward: 150,000 VND.

Both versions can be **written to the database before taking effect**, provided the effective intervals do not overlap and every current-price query filters by business date.

This demonstrates that **the most recently recorded version** is not necessarily **today's effective version**. The current-price API must filter with `valid_period @> CURRENT_DATE` per the business calendar, not simply `ORDER BY recorded_at DESC LIMIT 1`.

If business dates follow a branch time zone, the database's `CURRENT_DATE` is only safe when session time zones and date rules are aligned. A multi-time-zone application should explicitly pass the computed business date into the query.

## 8. Inserting a Mid-History Version and Handling Retroactive Adjustments

Suppose after storing P2 `[2026-07-01, 2026-10-01)` at 120,000 VND, finance discovers an approved decision requiring **125,000 VND for August**, while July and September remain 120,000 VND.

We must **split the existing interval** into three segments:

~~~text
Before:
[2026-07-01, 2026-10-01) → 120,000

After:
[2026-07-01, 2026-08-01) → 120,000
[2026-08-01, 2026-09-01) → 125,000
[2026-09-01, 2026-10-01) → 120,000
~~~

An illustrative transformation:

~~~sql
BEGIN;

UPDATE plan_price_version
SET valid_period =
    daterange(DATE '2026-07-01', DATE '2026-08-01', '[)')
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_period =
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
RETURNING version_id;

-- Require exactly one version to be split; otherwise ROLLBACK.

INSERT INTO plan_price_version (
    plan_id, currency_code, monthly_fee,
    valid_period, source_decision_id
)
VALUES
(
    7, 'VND', 125000,
    daterange(DATE '2026-08-01', DATE '2026-09-01', '[)'),
    'CORRECTION-2026-AUG'
),
(
    7, 'VND', 120000,
    daterange(DATE '2026-09-01', DATE '2026-10-01', '[)'),
    'CORRECTION-2026-AUG'
);

COMMIT;
~~~

This is an **interval-splitting problem**, not merely updating a price column. In real systems, the target segment may intersect multiple versions, land on a boundary, or extend outside currently stored ranges. The service must compute remaining fragments from existing data, discard empty segments, and apply the new decision in business-permitted order.

### 8.1. Why Modifying Effective History Demands Caution

A table with only `valid_period` reflects **the effective schedule currently accepted by the system**. After editing P2, the original `[2026-07-01, 2026-10-01)` interval no longer exists intact in the table. Even with `recorded_at`, you cannot reliably reconstruct what the system answered **before the correction was recorded**.

Distinguish clearly between:

- **Effective history (valid-time versions):** which value is currently deemed true for a given business date.
- **System-knowledge history (recorded/system-time versions):** what the system believed at a past recording point in time.
- **Event/adjustment history:** who made the decision, based on which document, and why the edit occurred.

If the business must answer both **“which price applied on August 15?”** and **“before the September 20 correction, what did the system believe August 15's price was?”**, design a **bitemporal** model or store a complete event sequence capable of reconstructing knowledge evolution. Keeping a single `recorded_at` timestamp on the row after an UPDATE cannot replace that model.

### 8.2. Finalized Invoices Must Not Silently Change Amounts

An invoice issued on August 15 may have billed 120,000 VND. After amending the effective schedule, querying the price for August 15 returns 125,000 VND. If the invoice UI recalculates amounts by joining the current version table, old invoices will display the wrong billed total.

Invoice schemas should persist the values actually applied at finalization, for example:

~~~text
invoice_line
  invoice_line_id
  invoice_id
  service_period
  plan_id
  charged_amount
  currency_code
  pricing_decision_ref
  price_version_ref (if any)
  finalized_at
~~~

**`charged_amount`** is the finalized amount billed under pricing rules; **`pricing_decision_ref`** links to the authority. If `price_version_ref` points to a row whose effective interval can be retroactively updated, do not treat that foreign key alone as immutable proof of the original calculation. Store a snapshot of pricing parameters or frozen version records for reconciliation.

Retroactive corrections typically trigger a separate business operation: refunds, debit/credit memos, or adjustment documents. They do not automatically authorize overwriting finalized financial transactions.

## 9. Detecting Gaps, Overlaps, and Invalid Versions

### 9.1. Overlap

Two intervals `A` and `B` overlap if they share at least one day. For half-open intervals with finite bounds, the equivalent condition is:

~~~text
A.from < B.to AND B.from < A.to
~~~

Unbounded limits require special handling; in PostgreSQL, use the `daterange` `&&` operator instead of hand-writing every branch.

~~~sql
SELECT
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
    &&
    daterange(DATE '2026-09-01', DATE '2026-12-01', '[)')
    AS overlaps;
-- true
~~~

In the DDL we built, `ex_plan_price_nonoverlap` prevents overlapping ranges for the same `plan_id` and `currency_code`. It cannot be replaced by `UNIQUE(plan_id, currency_code, lower(valid_period))`: two ranges with different start dates can still intersect.

### 9.2. Gap

Suppose P1 expires July 1, while P2 begins July 3. July 1 and July 2 have no valid price. This could be a bug or an intentional pause in sales.

A query to detect gaps **between consecutive versions**:

~~~sql
WITH ordered_prices AS (
    SELECT
        plan_id,
        currency_code,
        upper(valid_period) AS current_end,
        LEAD(lower(valid_period)) OVER (
            PARTITION BY plan_id, currency_code
            ORDER BY lower(valid_period)
        ) AS next_start
    FROM plan_price_version
)
SELECT
    plan_id, currency_code, current_end, next_start
FROM ordered_prices
WHERE current_end IS NOT NULL
  AND next_start IS NOT NULL
  AND current_end < next_start;
~~~

This finds only **gaps between existing rows**. It cannot tell whether prices are missing before the first version or after the last version without separate rules defining **when the plan began/ended being offered**. If the business requires continuous coverage across the entire offering window, tests must compare the price timeline against the plan's active lifecycle.

### 9.3. Adjacent Intervals with Equal Values

Two adjacent versions satisfy `previous.valid_to = next.valid_from`. If their values are equal, from a price-lookup perspective they could be **coalesced**. However, do not merge them when you need to preserve separate decision sources, contracts, scopes, or adjustment reasons.

For example, two separate approvals both set 120,000 VND across two consecutive quarters: merging them into one row destroys proof that two distinct pricing decisions were made. Coalescing is a semantic and audit decision, not merely a storage optimization.

### 9.4. Other Invalid Intervals

Explicitly reject or handle:

- **Empty interval:** `[2026-07-01, 2026-07-01)` contains zero days.
- **Start after end:** `[2026-10-01, 2026-07-01)`; range constructors may raise an error or produce a meaningless interval and must never be accepted as valid versions.
- **Unknown start date:** never invent a far-past sentinel date when legacy records lack evidence.
- **Wrong granularity:** representing minute-level access rights with `date` loses precision.
- **Time zone mismatch:** local effective dates shifting to another calendar day when converted to UTC without an agreed convention.

## 10. Constraints and Transactions Under Concurrent Updates

A clean history table schema is insufficient if two concurrent requests can alter the same plan's price schedule simultaneously.

Suppose analyst A schedules a price increase starting December 1 while analyst B simultaneously adds a discount campaign from November 15 to December 15. Both read the same initial timeline and compute new ranges from stale data. Without concurrency control, one transaction may lose the other's change, or one may fail due to an overlap.

### 10.1. Coordinated Layers of Protection

- **Database constraints:** `EXCLUDE` blocks illegal overlapping intervals even if a write path bypasses the application layer.
- **Transactions:** close old versions and insert new versions as an atomic unit.
- **Entity-level locking:** lock the parent `service_plan` row or a resource representing `plan_id + currency_code` while computing splits. If a plan updates multiple currencies independently, scope the lock accordingly to avoid unnecessary contention.
- **Optimistic concurrency control:** use a schedule revision counter to reject commands built from a stale timeline.
- **Idempotency:** retrying the same decision must not create duplicate versions or repeat an interval split indefinitely.
- **Explicit failure handling:** when an update does not affect the expected row count, roll back and re-read rather than forcing inserts based on stale assumptions.

Exclusion constraints protect data invariants, yet they do not decide **which decision wins** when two requests compete. Approval precedence, retroactive edit rights, and conflict resolution are business rules that must be defined separately.

### 10.2. Late-Arriving Data and Record Ordering

Pricing might pre-enter December's fee in August, then receive a decision in September effective back in July. You cannot use `MAX(version_id)` or `ORDER BY recorded_at DESC` to determine the “current price.”

Clearly distinguish:

- **System entry order:** which version was entered first.
- **Effective order:** which interval precedes another on the business timeline.
- **Decision precedence:** in a conflict, which approved decision carries authority.

Late-arriving data is not necessarily wrong, but it must go through a review process covering affected intervals and already-finalized transactions.

## 11. Indexing and Querying at Scale

Version tables can grow rapidly when an entity changes frequently, especially across multiple regions, currencies, or customer segments.

### 11.1. Optimizing by Query Pattern

| Query Pattern | Key Filter Columns/Types | Optimization Direction |
|---|---|---|
| Price of plan X on date D | `plan_id`, `currency_code`, `valid_period @> D` | Composite key + range index; inspect execution plan |
| Full price timeline of plan X | `plan_id`, `currency_code`, ordered by start date | B-tree on `lower(valid_period)` if beneficial |
| Prices intersecting month M across plans | `valid_period && month_period` | Range index; consider additional selective filters |
| Historical reports over millions of versions | Multiple plans, dates, joins to invoices | Partitioning / analytical warehouse depending on workload |
| Prices effective today across all plans | `valid_period @> today_date` | Synchronized projection or current table if measurements warrant |

The GiST index backing `EXCLUDE` can assist range queries, though actual benefit depends on selectivity and data distribution. Do not index every column “just in case”: every index adds insert, update, and storage overhead.

### 11.2. When a Current Table or Cache Is Needed

If a catalog page frequently renders millions of active prices, maintaining a `current_price` table or projection can speed up reads. When doing so, designate which table is the **source of truth**; scheduled transitions, retroactive edits, and concurrent writes must update the projection according to clear rules.

A reconciliation job can query `valid_period @> business_date` from the version table and compare against the projection. Never equate “current” with the row having the highest start date, because future-dated rows may already exist.

### 11.3. Partitioning and Retention

Partitioning helps when tables reach tens of millions of versions, but partition keys must match both query patterns and constraint enforcement. If two intervals for the same plan land in different partitions, overlap constraints **are not automatically enforced across partitions** in every PostgreSQL version/configuration. Verify the exact partitioning strategy or enforce business-key overlap protection globally.

Retention must balance historical lookup needs, audit obligations, personal data rules, and storage cost. When purging old versions, as-of APIs must expose the retained horizon rather than returning “no version” as though the business never existed.

## 12. Adapting the Pattern to Document, Graph, and Analytical Stores

The semantics of **one entity with multiple versions, each carrying an effective interval** do not depend on a relational DBMS.

| Model | Version Storage Approach | Main Challenges |
|---|---|---|
| **Relational** | Version table, foreign keys, range or start/end columns | Non-overlap constraints, interval-splitting transactions, indexing |
| **Document** | Multiple documents per `entityId` with `validFrom`/`validTo` | Avoiding unbounded embedded history arrays; multi-document update consistency |
| **Graph** | Versioned nodes or edges with effective intervals | Relationship queries at D must filter both vertices and edges by D |
| **Analytical warehouse** | **SCD Type 2** dimensions, surrogate keys, and effective intervals | Point-in-time fact joins, late-arriving data, load history |
| **Event store** | Decision/event stream plus effective-version projections | Reconstructing accurately under late arrivals, retroactive edits, and replay |

Example of a price version document:

~~~json
{
  "versionId": "price-7-2026-07",
  "planId": 7,
  "currencyCode": "VND",
  "monthlyFee": 120000,
  "validFrom": "2026-07-01",
  "validTo": "2026-10-01",
  "sourceDecisionId": "PRICING-2026-Q3"
}
~~~

`validTo` remains an **exclusive bound** even when stored as a date string instead of a native range type. Multiple documents can share `planId`; you must define how overlaps are prevented under concurrent writes. A unique index on `validFrom` alone does not solve this.

In a **graph**, if an employee belongs to team A `[2026-01-01, 2026-04-01)` and then team B `[2026-04-01, +∞)`, the **membership edges** must carry effective intervals. Versioning only properties on the employee node cannot answer “which team did the employee belong to on March 15?”

In **SCD Type 2**, each dimension row stores one value version and effective interval, usually with a surrogate key. When joining transactional facts, decide whether to use the **version key captured at transaction time** or perform a date-based temporal join. If already-published facts are affected by retroactive dimension corrections, protect original records and run explicit compensating adjustments.

## 13. Required Test Suite for Effective-Interval Records

Use versions P1, P2, and P3 from section 1 as baseline data. The table below tests version selection:

| Case | Query Input | Expected Result |
|---|---|---|
| Before first effective date | 2025-12-31 | No version |
| Exact start bound of P1 | 2026-01-01 | P1, 100,000 |
| Immediately before P1 end bound | 2026-06-30 | P1, 100,000 |
| Exact P1 → P2 transition bound | 2026-07-01 | P2, 120,000 |
| Immediately before P2 → P3 transition | 2026-09-30 | P2, 120,000 |
| Exact P2 → P3 transition bound | 2026-10-01 | P3, 130,000 |
| After P3 with unbounded upper limit | 2026-12-15 | P3, 130,000 unless a newer version is scheduled |
| Period spanning two versions | Jun 15 to before Jul 15 | Intersects P1 and P2 |
| Attempt to insert overlapping interval | Sep 1 to before Nov 1 | Database must reject for same plan/currency |
| Two adjacent intervals | P1 ends Jul 1, P2 starts Jul 1 | Must not be treated as overlapping |

The following tests cover subtler operational bugs:

1. **Future write:** add P4 starting December 1; verify November 30 still returns P3 and December 1 returns P4.
2. **Interval split:** insert an adjusted price for August; verify July, August, and September return correct prices without losing the leading/trailing portions of the old interval.
3. **Rollback:** deliberately force the new-version INSERT to fail; verify the UPDATE closing the prior interval also rolls back.
4. **Concurrency:** two sessions editing the same plan must never both commit overlapping intervals; the application responds or retries per rules.
5. **Idempotency:** resending the same pricing decision neither creates duplicate versions nor splits intervals twice.
6. **Gaps:** verify business rules either allow or reject unpriced dates rather than silently inferring a price.
7. **Time and time zones:** for timestamps, test midnight rollovers and time zones; for dates, verify local calendar alignment.
8. **Finalized records:** editing past effective price schedules must not silently alter amounts on old invoices.
9. **Decision source:** every row traces back to an authoritative decision; no ungrounded versions are created.

**Boundary testing** is especially critical: a single `<=` vs. `<` mistake at a boundary causes the system to pick the wrong price on the exact day of a rate change even while all mid-period queries pass.

## 14. Practice Exercise: Modeling Staged Staff Assignments

An organization states:

> “We need to look up which department an employee belonged to on any given day, allow planning future department transfers, and ensure an employee never has two active primary departments simultaneously.”

Turn this requirement into a design:

1. Identify **employee** as the stable entity and **department_assignment_version** as the versioned relationship. Each version carries `employee_id`, `department_id`, `valid_period`, and `decision_ref`.
2. State the invariant: for the same `employee_id`, **primary department** intervals must not overlap; if secondary/acting roles are permitted, add `assignment_type` and separate rules.
3. Represent employee 42 in department A from January 1 until before April 1, then in department B from April 1 onward.
4. Write as-of queries for March 31 and April 1; expected outputs are A and B respectively.
5. Describe the transaction when scheduling a transfer to department C starting June 1: close B at June 1, then insert C starting June 1.
6. Decide whether gaps between assignments are allowed. If an employee takes unpaid leave while still belonging to department A, “employment status” and “department” should be separate attributes/relationships rather than overloading an ambiguous gap.
7. If you also need to answer “in March, which department did the system expect the employee to be in during June?”, explain why recorded history or bitemporal modeling must be added.

This exercise highlights that **interval versioning** applies both to entity attributes (prices) and **relationships between entities** (employee–department assignments). Depending on relational or graph storage, where the interval lives may differ, yet the rule “one valid value at time D” must remain consistent.

## 15. Design Sign-Off Checklist

Before approving the design:

- **Keys:** are the logical entity, version key, and deduplication business scope cleanly separated?
- **Time:** are `date` vs. timestamp, `[from, to)` convention, time zone, and open-ended bounds agreed upon?
- **Integrity:** are empty intervals and overlaps prevented, and are gaps checked when required by the business?
- **Queries:** are single-day as-of, timeline, period-intersection, and missing-version cases defined?
- **Writes:** are future versions, retroactive edits, interval splits, rollbacks, and concurrent writes handled?
- **Evidence:** does every record have a decision source, and do finalized transactions persist applied values?
- **System history:** if you must know what the system previously recorded, does the model include recorded time or event history sufficient to reconstruct it?
- **Performance and evolution:** have indexes, partitioning, data lifecycle, and schema upgrade rules been tested against realistic queries?

A versioned record is only truly useful when **its effective interval is unambiguous and enforced by verifiable constraints**. Start from the business question “which value is true on date D?”, then design the entity, versions, half-open intervals, keys, and transactions. When requirements expand to “what did the system know at time K?”, add the corresponding recorded-history axis rather than overloading a single `updated_at` column to play both roles.
