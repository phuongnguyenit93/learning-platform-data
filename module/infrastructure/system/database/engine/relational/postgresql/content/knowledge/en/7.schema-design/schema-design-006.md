# Designing Temporal Data, History, and Change Logs in PostgreSQL

In real-world applications, data does not have only a **current value**. Selling prices can change by date; shipping addresses can be updated after an order is created; a contract is effective over a specific interval; and when a dispute arises, the system needs to know **what the data used to be, when it changed, by whom, and why**. If a table only stores the latest value, those questions become unanswerable.

PostgreSQL offers many tools for modeling time-oriented data: `date`, `timestamp`, `timestamptz`, `interval`, **range types** such as `daterange` and `tstzrange`, `EXCLUDE` constraints, transactions, triggers, `jsonb`, partitioning, and WAL change streaming. Yet no single table pattern solves every historical requirement. First you must determine whether you are storing **business valid time**, **system recorded time**, **when an event occurred**, or an **action audit log**.

This lesson helps you:

- Choose temporal data types and handle time zones consistently.
- Design current-state tables, historical version tables, and **as-of** queries.
- Prevent overlapping validity intervals using `tstzrange` and `EXCLUDE USING gist`.
- Distinguish data history from **audit logs**, event logs, event sourcing, and **outboxes**.
- Record history via applications or triggers within the same transaction.
- Design indexes, partitions, retention policies, and retroactive correction workflows.
- Handle concurrency, late-arriving events, and security risks of change logs.

> The SQL examples are meant for **PostgreSQL in a test database**. Dates, prices, and object names are illustrative, not real data. Constraints, history policies, and deletion rules must be decided according to business, legal, and operational requirements before production deployment.

## 1. Four Temporal Questions to Distinguish

A single row can carry multiple timestamps with distinct meanings:

| Timestamp | Question It Answers | Example |
|---|---|---|
| **Event time** | When did the event actually happen? | Sensor recorded temperature at 09:00. |
| **Ingestion/recorded time** | When did PostgreSQL or the system receive/write the event? | Network delay caused data to reach the server at 09:06. |
| **Valid time** | From when to when is this value effective in the business? | New price takes effect at 00:00 on Dec 1. |
| **System/transaction time** | When did the system learn/record this assertion? | On Nov 14, we learned that a price was effective since Nov 1. |

These may coincide in simple cases, yet **you should never assume they are always identical**.

Example:

```text
Nov 1         Nov 10          Nov 14            Dec 1
  │             │               │                 │
  ├─────────────┴───────────────┼─────────────────┤
  │ Price 100 effective Nov 1   │                 │
  │                             │ Correction recorded:
  │                             │ actual price was 120
  │                             │ starting Nov 1
  │                                               │
  └───────────────────────────────────────────────┘

Valid time of correction: Nov 1
System recorded time of correction: Nov 14
```

With only an `updated_at` column, you cannot distinguish **"the date the price took effect"** from **"the date the company discovered and corrected the price"**.

### Clarify Business Questions Before Choosing a Table Design

Ask:

1. Do we need to know the **state at a past point in time**?
2. Do we need to **schedule future changes**?
3. Do we need to know **who edited it, why, and which request triggered the change**?
4. Are **retroactive corrections** to already-effective decisions allowed?
5. Do we need to reconstruct **what the system believed at an earlier point**, even after later corrections?
6. How long must history be retained, and are there tamper-resistance/non-deletion requirements?

The answers dictate whether to use simple timestamp columns, a unitemporal version table, a **bitemporal** model, or a separate audit/event log.

## 2. PostgreSQL Temporal Data Types

PostgreSQL provides these primary types:

| Type | Meaning | When to Consider |
|---|---|---|
| `date` | Calendar date without time or time zone. | Birthdates, holidays, calendar policy start dates. |
| `time without time zone` | Time of day without time zone. | Local opening hours when region context is stored separately. |
| `timestamp without time zone` | Date and time as **local wall time**, without offset/time zone. | Local wall-clock schedules when zone is tracked separately or data does not represent an absolute instant. |
| `timestamp with time zone` / `timestamptz` | A specific instant on the timeline; PostgreSQL normalizes internally and displays in the session time zone. | `created_at`, `occurred_at`, `valid_from` when exact instants matter. |
| `interval` | Duration consisting of months, days, and time components. | Durations, wait times, calendar arithmetic. |
| `daterange`, `tsrange`, `tstzrange` | Range of date or timestamp values. | Validity periods, booking schedules, overlap checks. |

Example:

```sql
CREATE TABLE temporal_type_examples (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    business_date DATE NOT NULL,
    local_appointment TIMESTAMP WITHOUT TIME ZONE,
    event_instant TIMESTAMPTZ NOT NULL,
    duration INTERVAL
);
```

### TIMESTAMPTZ Does Not Store the Original Time Zone Name

The name `timestamp with time zone` is often misunderstood: PostgreSQL uses the input's offset/time zone to determine an **absolute instant**, then formats output according to the session's `TimeZone`. It **does not store a separate zone string** such as `Asia/Ho_Chi_Minh` per value.

These two literals denote the exact same instant:

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:00:00+07'
      = TIMESTAMPTZ '2026-11-14 02:00:00+00'
      AS same_instant;
-- true
```

If the business needs to know **which geographic time zone the user chose**—for instance `Europe/Berlin` to compute future schedules across DST transitions—store the **IANA time-zone identifier** separately rather than only an offset like `+01:00`.

## 3. Time Zone Design: Absolute Instants vs. Calendar Wall Time

A helpful guideline:

- **Events that occurred at a specific moment:** prefer `timestamptz`.
- **Rules tied to a local calendar date:** store `date` and the business time zone when needed.
- **Appointments tied to a local wall clock:** you may need both local date/time and time zone name, plus rules for non-existent or repeated DST times.

Observe:

```sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 02:00:00+00' AS local_display;

SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 02:00:00+00' AS utc_display;
```

The stored value is **the exact same instant**, while formatting changes. Afterward, reset the session configuration if needed:

```sql
RESET TIME ZONE;
```

### AT TIME ZONE Converts in Two Directions

```sql
-- Timestamptz -> local wall time without time zone.
SELECT
    TIMESTAMPTZ '2026-11-14 02:00:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh' AS local_clock;
-- 2026-11-14 09:00:00

-- Local timestamp in the specified zone -> instant.
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh' AS actual_instant;
```

In the second query, the result has type `timestamptz` and will **display in the session's time zone**, not necessarily with a `+07` suffix.

### Do Not Assume Every "Local Day" Is 24 Hours

In regions with **Daylight Saving Time (DST)**, a calendar day can occasionally be **23 or 25 hours** long. When filtering by a user's local calendar day, construct **both boundaries in the local time zone** and compare against the `timestamptz` column.

Example fetching events on **Nov 14, 2026** in Vietnam time:

```sql
SELECT *
FROM temporal_type_examples
WHERE event_instant >=
      (TIMESTAMP '2026-11-14 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND event_instant <
      (TIMESTAMP '2026-11-15 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh');
```

Using **`>=` start of day and `<` start of next day** is also friendly to a B-tree index on `event_instant`. Casting or formatting the column directly inside `WHERE` can prevent index usage unless a matching expression index exists.

## 4. current_timestamp, now(), statement_timestamp(), and clock_timestamp()

When asking for "now" in PostgreSQL, know **which "now"** you are reading:

| Expression | Primary Meaning |
|---|---|
| `CURRENT_TIMESTAMP` | Start time of the current transaction. |
| `now()` | Equivalent to transaction start time; does not advance inside a long transaction. |
| `transaction_timestamp()` | Start time of the current transaction. |
| `statement_timestamp()` | Time the server received/started the current statement per PostgreSQL mechanics. |
| `clock_timestamp()` | Real wall clock at the moment of call; can change even within one statement. |

Example:

```sql
BEGIN;

SELECT now(), statement_timestamp(), clock_timestamp();

SELECT pg_sleep(1);

SELECT now(), statement_timestamp(), clock_timestamp();

ROLLBACK;
```

Inside the transaction above, `now()` stays fixed at transaction start, whereas `statement_timestamp()` and `clock_timestamp()` reflect the later time.

### Which Function Should Audit Logs Use?

There is no single right answer for every system:

- Want every change in the same transaction to share **one uniform timestamp**: `now()` can fit.
- Want the start time of **each statement**: `statement_timestamp()`.
- Want the wall clock right when the trigger inserts each row: `clock_timestamp()`.
- Want the true event time from a device or partner: usually store the **timestamp carried by the event**, rather than replacing it with server ingestion time.

**Timestamps alone do not prove transaction commit order.** Two transactions can start in order A then B yet commit in order B then A. When strict ordering is needed, use per-entity version numbers, concurrency locks, LSN/CDC, or dedicated constraints and protocols.

## 5. Choosing a History Model Based on the Questions to Answer

Common models:

| Model | What It Stores | Strengths | Limitations |
|---|---|---|---|
| **Current-state table** | Only currently active rows. | Simple, fast queries. | Overwrites old values on `UPDATE`/`DELETE` unless tracked elsewhere. |
| **Periodic snapshots** | Full table or dataset snapshots on a schedule. | Useful for reporting / restore checkpoints. | Misses changes between two snapshots. |
| **Versioned / SCD Type 2** | Each value version and its validity interval. | Answers "what value was effective at time T?". | Requires interval management, concurrency control, and retroactive correction handling. |
| **Bitemporal** | Both business valid time and system recorded time. | Answers "what did the system believe earlier about time T?". | More complex logic and constraints. |
| **Audit log** | Action records: who/what/when/old/new. | Change traceability, investigation support. | Not directly a queryable effective-state history model. |
| **Event log / event sourcing** | Immutable sequence of business events. | Suits systems needing state reconstruction from events. | Requires event schemas, ordering, versioning, and replay. |
| **CDC / logical decoding** | Stream of data changes from DB logs. | Near-real-time synchronization across systems. | Does not inherently capture business actor/reason semantics. |

A system can combine **multiple models simultaneously**. For instance, a versioned price table for date-based lookups, an audit log to trace who changed prices, and an outbox to publish `PriceChanged` events to other services.

## 6. Current-State Table Design: Simple, with Accepted Limits

Example:

```sql
CREATE TABLE catalog_products_current (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Querying the current price:

```sql
SELECT product_id, sku, price
FROM catalog_products_current
WHERE product_id = 42;
```

Strengths: intuitive, one row per product, simple indexing. However, if you run:

```sql
UPDATE catalog_products_current
SET price = 125000,
    updated_at = clock_timestamp()
WHERE product_id = 42;
```

the old price is replaced in the **current logical state of the table**. PostgreSQL uses MVCC and WAL, yet that is **not equivalent to an arbitrarily queryable history store**. Autovacuum can reclaim old tuple versions; WAL has its own retention lifecycle.

If the requirement is "show the price list as of Nov 1", you need an explicit history design—never rely on `updated_at` and MVCC.

## 7. Validity-Interval History Model: SCD Type 2

**Slowly Changing Dimension Type 2 (SCD Type 2)** stores **each value version as its own row**, paired with a validity interval. Instead of overwriting the old price, the system **closes the old interval** and **inserts a new version**.

Example:

| product_id | price | valid_from | valid_to |
|---:|---:|---|---|
| 42 | 100.000 | Nov 1 00:00 | Nov 10 00:00 |
| 42 | 115.000 | Nov 10 00:00 | Nov 14 09:00 |
| 42 | 125.000 | Nov 14 09:00 | Unbounded |

Using **inclusive start, exclusive end** semantics (denoted **`[)`**):

- Nov 9 23:59 belongs to the 100.000 version.
- Exactly Nov 10 00:00 belongs to the 115.000 version.
- Exactly Nov 14 09:00 belongs to the 125.000 version.

Adjacent versions can share the **exact same end/start boundary** without overlapping.

### Why Avoid Inclusive-Both-Ends BETWEEN?

If you write:

```sql
WHERE :instant BETWEEN valid_from AND valid_to
```

then right on the boundary between two versions, both old and new versions risk matching if `valid_to` is inclusive. Moreover, `valid_to IS NULL` is not treated by `BETWEEN` as "infinity".

With `[)`, write:

```sql
WHERE valid_from <= :instant
  AND (valid_to IS NULL OR :instant < valid_to)
```

In this SQL snippet, `:instant` denotes a **named parameter bound by an application or client tool**; raw PostgreSQL SQL does not parse `:name` bind syntax natively.

## 8. Product Price History Schema in PostgreSQL

Separate the **product identity** table from the **price versions** table:

```sql
CREATE TABLE catalog_products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE product_price_versions (
    version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES catalog_products(product_id),
    price NUMERIC(12, 2) NOT NULL
        CHECK (price >= 0),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    changed_by TEXT NOT NULL,
    change_reason TEXT,
    recorded_at TIMESTAMPTZ NOT NULL
        DEFAULT clock_timestamp(),
    CONSTRAINT chk_price_valid_interval
        CHECK (valid_to IS NULL OR valid_to > valid_from)
);
```

Explanation:

- `version_id` uniquely identifies **one version row**, not the product.
- `product_id` groups versions belonging to the same product.
- `valid_from` and `valid_to` define when the price version is **effective**.
- `valid_to IS NULL` indicates an **open-ended** end time.
- `recorded_at` records **when the system saved the version**, which may differ from `valid_from`.
- `changed_by` and `change_reason` provide basic traceability, though not yet a full audit system.

Insert sample data:

```sql
INSERT INTO catalog_products(product_id, sku, name)
VALUES (42, 'SKU-042', 'Demo Product');

INSERT INTO product_price_versions
    (product_id, price, valid_from, valid_to,
     changed_by, change_reason)
VALUES
    (42, 100000, TIMESTAMPTZ '2026-11-01 00:00:00+07',
         TIMESTAMPTZ '2026-11-10 00:00:00+07',
         'pricing_admin', 'Initial price'),
    (42, 115000, TIMESTAMPTZ '2026-11-10 00:00:00+07',
         TIMESTAMPTZ '2026-11-14 09:00:00+07',
         'pricing_admin', 'Adjustment round 1'),
    (42, 125000, TIMESTAMPTZ '2026-11-14 09:00:00+07',
         NULL,
         'pricing_admin', 'Adjustment round 2');
```

**Note:** This script seeds sample data into an empty lab database. The schema above **does not yet enforce non-overlapping intervals**; the next section adds `EXCLUDE` to enforce that invariant at the database layer.

## 9. Querying the Price at Any Point in Time — As-Of Query

To look up the price effective at **Nov 12, 2026 10:00 in Vietnam time**:

```sql
SELECT version_id, product_id, price,
       valid_from, valid_to
FROM product_price_versions
WHERE product_id = 42
  AND valid_from <=
      TIMESTAMPTZ '2026-11-12 10:00:00+07'
  AND (
      valid_to IS NULL
      OR TIMESTAMPTZ '2026-11-12 10:00:00+07' < valid_to
  );
```

The expected result is **115,000**. Without overlapping intervals, a product has **at most one active version** at any instant T.

### Querying the Current Price

If the model allows only one **open-ended future** version:

```sql
SELECT product_id, price
FROM product_price_versions
WHERE product_id = 42
  AND valid_to IS NULL;
```

Watch out for **future-dated versions**: a version with `valid_from` tomorrow and `valid_to IS NULL` is not the price **effective today**. Therefore, a safer current-price query is:

```sql
SELECT product_id, price
FROM product_price_versions
WHERE product_id = 42
  AND valid_from <= now()
  AND (valid_to IS NULL OR now() < valid_to);
```

**"An open-ended interval" does not always mean "currently effective right now".** This matters especially when scheduling price changes days in advance.

### Resolving Prices for Multiple Products at a Point in Time

```sql
SELECT p.product_id, p.sku, v.price
FROM catalog_products AS p
LEFT JOIN product_price_versions AS v
  ON v.product_id = p.product_id
 AND v.valid_from <= TIMESTAMPTZ '2026-11-12 10:00:00+07'
 AND (
       v.valid_to IS NULL
       OR TIMESTAMPTZ '2026-11-12 10:00:00+07' < v.valid_to
     );
```

`LEFT JOIN` preserves products that lack a price version at the chosen instant. If the data contains overlapping intervals, this query can return **multiple rows for one product**, which is why overlap prevention must be enforced on write.

## 10. Range Types: Expressing Time Intervals Cleanly

PostgreSQL provides **range types**: `daterange`, `tsrange`, `tstzrange`, and others. For history using absolute instants, `tstzrange` is usually the right fit.

Example:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-01 00:00:00+07',
    TIMESTAMPTZ '2026-11-10 00:00:00+07',
    '[)'
) AS active_period;
```

`[)` means **lower bound inclusive, upper bound exclusive**.

Key operators and functions:

| Operator / Function | Example | Meaning |
|---|---|---|
| `@>` | `valid_period @> some_timestamp` | Range **contains** instant. |
| `&&` | `period_a && period_b` | Two ranges **overlap**. |
| `<@` | `period_a <@ period_b` | First range is contained in second range. |
| `lower()` | `lower(valid_period)` | Extracts lower bound. |
| `upper()` | `upper(valid_period)` | Extracts upper bound; may be unbounded. |
| `isempty()` | `isempty(valid_period)` | Checks whether the range is empty. |

Example:

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-01 00:00:00+07',
        TIMESTAMPTZ '2026-11-10 00:00:00+07',
        '[)'
    ) @> TIMESTAMPTZ '2026-11-05 10:00:00+07'
    AS contains_fifth_day;
-- true
```

### Using NULL for Unbounded Start or End

When constructing a range:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    NULL,
    '[)'
) AS open_ended;
```

Passing `NULL` as the **upper argument** to the constructor means an **unbounded upper bound**. This differs from setting a `valid_period` column to SQL `NULL`: a `NULL` range column does not mean "open-ended interval".

If storing a `tstzrange` column directly, declare it `NOT NULL` and check `NOT isempty(valid_period)` when empty ranges are invalid.

## 11. Preventing Overlapping Validity Intervals with EXCLUDE USING gist

Two price versions for the same product with intersecting validity intervals represent a data bug if the business requires **at most one price per product at any instant**.

`CHECK (valid_to > valid_from)` alone is insufficient: it validates **each row in isolation**, not across different rows.

PostgreSQL supports **exclusion constraints** backed by a GiST index to guarantee **no two rows for the same product have overlapping intervals**.

First, in your lab database you may need the `btree_gist` extension to provide GiST operator classes for `BIGINT WITH =`:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

Installing extensions requires appropriate privileges and may be restricted by environment policies.

Once existing data has **no overlapping intervals**, add the constraint:

```sql
ALTER TABLE product_price_versions
ADD CONSTRAINT ex_price_no_overlap
EXCLUDE USING gist (
    product_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
```

Meaning:

- **`product_id WITH =`**: compares versions of the same product.
- **`tstzrange(...) WITH &&`**: forbids intersecting time intervals.
- Two versions of **different products** may share the same interval.
- Two versions of **the same product** may sit **adjacent** at a `[)` boundary without overlapping.

For example, the following statement must fail when price 115,000 already covers Nov 10 to Nov 14 09:00:

```sql
INSERT INTO product_price_versions
    (product_id, price, valid_from, valid_to, changed_by)
VALUES
    (42, 119000,
     TIMESTAMPTZ '2026-11-11 00:00:00+07',
     TIMESTAMPTZ '2026-11-13 00:00:00+07',
     'pricing_admin');
```

PostgreSQL rejects it because the two intervals overlap for the same `product_id`. Exclusion constraint errors report SQLSTATE **`23P01`** (`exclusion_violation`).

### Exclusion Constraints Do Not Guarantee "No Gaps"

Suppose a product has a price from Nov 1 to Nov 10 and another from Nov 15 onward. The two intervals **do not overlap**, so `EXCLUDE` accepts them; yet Nov 10–14 **has no price**.

If the business requires continuity, you need write rules, per-entity checks, or processes guaranteeing **no gaps**. `EXCLUDE` only prevents **overlaps**; it does not auto-generate versions to fill gaps.

### Partial Unique Index for the Currently Open Version

Some designs also add:

```sql
CREATE UNIQUE INDEX ux_price_one_open_version
ON product_price_versions(product_id)
WHERE valid_to IS NULL;
```

This index prevents two versions of the same product from having `valid_to IS NULL`. If `EXCLUDE` already forbids overlapping unbounded ranges, the invariant "no two overlapping open intervals" is essentially **already protected**; a partial unique index is an optional addition with write/storage overhead that can aid specific lookup paths. Never add redundant indexes blindly without evaluating the workload.

## 12. Updating a Price Version: One Transaction Must Wrap Both Steps

When a price changes at time T, we want to:

1. Close the old version at **T**.
2. Insert the new version starting at **T**.
3. Have both steps **succeed or roll back together**.

Example in the **lab database**, for product `42` and T = **Nov 15, 2026 09:00 +07**:

```sql
BEGIN;

-- Serialize price changes for the same product
-- when all writers follow this locking protocol.
SELECT product_id
FROM catalog_products
WHERE product_id = 42
FOR UPDATE;

UPDATE product_price_versions
SET valid_to = TIMESTAMPTZ '2026-11-15 09:00:00+07'
WHERE product_id = 42
  AND valid_to IS NULL;

INSERT INTO product_price_versions (
    product_id, price, valid_from, valid_to,
    changed_by, change_reason
)
VALUES (
    42, 129000,
    TIMESTAMPTZ '2026-11-15 09:00:00+07',
    NULL,
    'pricing_admin', 'Price update on Nov 15'
);

COMMIT;
```

**This example assumes T is later than every existing `valid_from` and one open version exists.** If future versions are already scheduled, the logic must inspect the entire timeline rather than filtering solely on `valid_to IS NULL`.

### Why Lock the Parent Row?

If two workers simultaneously update the price of product 42, both might read the old version and try to insert a new one. Locking `catalog_products` with `FOR UPDATE` **serializes updates per product** when all write paths obey the same protocol.

In systems with multiple write paths, `EXCLUDE` remains a vital database safety net: a worker that forgets to lock the parent row will still be rejected if it tries to create an overlap rather than silently corrupting history.

### Use the Exact Same Timestamp T

Do not call `clock_timestamp()` independently in the `UPDATE` and the `INSERT` when both steps must **meet seamlessly** at one boundary. Two calls can differ by microseconds and create an unintended gap.

A clean approach is to **pick T once** in the application or SQL and pass T as the same parameter to both statements in the transaction. For retroactive or future-scheduled changes, T must be the approved **business effective time**, not necessarily the server write time.

### Check Updated Row Counts

If `UPDATE` affects 0 open rows, that might be valid (e.g., a brand-new product) or a sign that the timeline is not in the expected state. Applications should check **row counts**, matching predicates, and final state before `COMMIT`—never assume a succeeding `INSERT` means the price transition was valid.

## 13. Bitemporal Modeling: Two Time Dimensions to Answer "What Did We Know Then?"

A unitemporal model answers "what price was effective at time T?" Sometimes you face a harder question:

> "On Nov 10, what did the system **believe** the price for Nov 1 was, before the correction entered on Nov 14?"

That is a **bitemporal** requirement, combining:

- **Valid time:** the interval when a value is true in the business domain.
- **System/recorded time:** the interval when the system held a given **assertion** about that value.

Example:

```text
Nov 1:  Price 100 is effective per initial record.
Nov 10: System still believes price from Nov 1 is 100.
Nov 14: Discovered true price from Nov 1 should have been 120.

As of recorded Nov 10, valid Nov 5 → 100.
As of recorded Nov 15, valid Nov 5 → 120.
```

Merely overwriting the old row to 120 with `updated_at = Nov 14` **destroys** what the system believed on Nov 10.

### A Simplified Bitemporal Schema

```sql
CREATE TABLE product_price_assertions (
    assertion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES catalog_products(product_id),
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),

    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,

    recorded_from TIMESTAMPTZ NOT NULL,
    recorded_to TIMESTAMPTZ,

    correction_reason TEXT,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (recorded_to IS NULL OR recorded_to > recorded_from)
);
```

Each row represents an **assertion**: a price effective over `valid_from → valid_to`, believed by the system during `recorded_from → recorded_to`.

Query:

```sql
SELECT product_id, price
FROM product_price_assertions
WHERE product_id = 42
  -- Price effective on Nov 5:
  AND valid_from <= TIMESTAMPTZ '2026-11-05 12:00:00+07'
  AND (
       valid_to IS NULL
       OR TIMESTAMPTZ '2026-11-05 12:00:00+07' < valid_to
  )
  -- Assertion known to the system on Nov 10:
  AND recorded_from <= TIMESTAMPTZ '2026-11-10 12:00:00+07'
  AND (
       recorded_to IS NULL
       OR TIMESTAMPTZ '2026-11-10 12:00:00+07' < recorded_to
  );
```

**This schema only illustrates the representation.** It does not yet include multidimensional exclusion constraints guaranteeing exactly one price assertion for any `(valid_time, recorded_time)` pair. A full bitemporal implementation must handle closing old assertions, writing corrected assertions, concurrency, and preventing invalid overlaps across **both time axes**.

### PostgreSQL Does Not Enable System-Versioned Tables Automatically from Column Names

Standard PostgreSQL **does not provide built-in SQL Server-style `FOR SYSTEM_TIME AS OF` syntax or auto-version tables** just because you name columns `valid_from`/`recorded_from`. Bitemporal behavior must be implemented via schemas, triggers, application logic, or suitable extensions whose semantics you verify.

A single `recorded_at DEFAULT now()` column is **not enough** for system-time history. Knowing when a record was superseded requires closing `recorded_to`, preserving the superseded assertion, and writing the new assertion consistently.

## 14. How Does Data History Differ from an Audit Log?

A **version table** models **state versions** to answer what value held at a given time. An **audit log** models **change actions** to answer who/what performed a change and what its impact was.

Comparison:

| Aspect | Version Table | Audit Log |
|---|---|---|
| Primary content | State and validity intervals. | `INSERT`/`UPDATE`/`DELETE` events, old/new, actor, reason, request. |
| Typical question | What price was effective on Nov 10? | Who changed the price on Nov 14? |
| Typical query | `valid_period @> T`. | `WHERE entity_id = ... ORDER BY changed_at`. |
| Reflects retroactive fixes? | Yes, if valid time is modeled properly. | Records the correction action, yet doesn't model valid time directly. |
| Enough for security forensics? | Usually no. | Better, though an in-DB audit log still has tamper-resistance limits. |

Both complement each other. If prices change over time and compliance requires accountability, keep a **version table for state lookups** and an **audit log for action traceability**.

### Event Logs Are Not the Same as Audit Logs

Business events like `OrderPaid` or `PriceApproved` describe **what happened in the domain**. A technical audit log might record "table `orders` row 123 changed column `status` from `PENDING` to `PAID`".

The two serve different purposes. One business event can trigger changes across multiple tables; one raw SQL mutation may lack the full business context of a domain event.

## 15. Designing an Audit Table: Identity, Action, Time, and Payload

A common audit table includes:

| Field | Role |
|---|---|
| `audit_id` | Stable identifier of the audit record. |
| `entity_type`, `entity_id` | Type and identifier of the changed object. |
| `action` | `INSERT`, `UPDATE`, `DELETE`, or a defined business event. |
| `changed_at` | Timestamp when the change was recorded. |
| `actor` | Principal requesting the change, per a trusted authentication mechanism. |
| `request_id` / `correlation_id` | Links the action to an HTTP request or batch job. |
| `old_values` / `new_values` | Before/after snapshots or changed fields only. |
| `reason` | Business justification provided when needed. |
| `source` | Application/job/service that initiated the change. |

`jsonb` suits flexible old/new payloads, yet **never dump sensitive fields into logs indiscriminately**. For financial details, accounts, tokens, and personal data, define strict necessity, access restrictions, and retention rules.

### Example Business Table and Audit Schema

```sql
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE public.demo_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit.demo_order_changes (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_values JSONB,
    new_values JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    actor TEXT NOT NULL,
    request_id TEXT,
    change_reason TEXT
);
```

In this example, `order_id` in the audit table **does not carry a mandatory foreign key** to `demo_orders`. Reason: when an order is deleted, the audit record must **survive** to document which row was deleted. A standard foreign key can conflict with deletion and audit retention unless paired with soft deletion or dedicated archival.

## 16. Writing Audit Records via Same-Transaction Triggers

PostgreSQL **triggers** automatically record audit entries on `INSERT`, `UPDATE`, or `DELETE`. This captures changes across multiple write paths, not just one service.

Example trigger function for `public.demo_orders`:

```sql
CREATE OR REPLACE FUNCTION audit.log_demo_order_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, audit, pg_temp
AS $$
DECLARE
    v_actor TEXT;
    v_request TEXT;
BEGIN
    -- App can set these variables inside the transaction.
    -- Client-supplied values must not automatically be treated as verified identity.
    v_actor := NULLIF(current_setting('app.actor', true), '');
    v_request := NULLIF(current_setting('app.request_id', true), '');

    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit.demo_order_changes (
            order_id, action, old_values, new_values,
            actor, request_id
        )
        VALUES (
            NEW.order_id, 'INSERT', NULL, to_jsonb(NEW),
            COALESCE(v_actor, session_user::TEXT), v_request
        );
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Skip no-op UPDATEs that do not change row contents.
        IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            INSERT INTO audit.demo_order_changes (
                order_id, action, old_values, new_values,
                actor, request_id
            )
            VALUES (
                NEW.order_id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW),
                COALESCE(v_actor, session_user::TEXT), v_request
            );
        END IF;
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit.demo_order_changes (
            order_id, action, old_values, new_values,
            actor, request_id
        )
        VALUES (
            OLD.order_id, 'DELETE', to_jsonb(OLD), NULL,
            COALESCE(v_actor, session_user::TEXT), v_request
        );
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_demo_orders_audit
AFTER INSERT OR UPDATE OR DELETE
ON public.demo_orders
FOR EACH ROW
EXECUTE FUNCTION audit.log_demo_order_change();
```

### Properties to Understand

- An `AFTER ... FOR EACH ROW` trigger fires on the corresponding row operation and runs inside the **same transaction as the mutation**.
- When a transaction **rolls back**, both the row mutation and the audit rows created by the trigger in that transaction **roll back together**.
- For `UPDATE`, `OLD` is the before-image and `NEW` is the after-image.
- For `INSERT`, only `NEW` is meaningful; for `DELETE`, only `OLD`.
- `TG_OP` indicates the operation type.
- `to_jsonb(OLD)`/`to_jsonb(NEW)` easily captures JSONB payloads, yet can copy sensitive fields and inflate log volume.
- The trigger is created in default mode here; permissions and the ability of privileged roles to disable triggers must still be controlled.

### Why Use SECURITY DEFINER?

The example uses `SECURITY DEFINER` to show a pattern where the trigger writes to the audit table using the **function owner's privileges**, even when the application role lacks direct `INSERT` privileges on the audit table. This is **safe only when**:

1. The function and audit schema are owned by a trusted role.
2. `search_path` is locked to trusted schemas; all important relations are schema-qualified.
3. `EXECUTE` privileges on the function, object-creation privileges in the schema, and audit table permissions are audited.
4. Applications cannot arbitrarily alter/delete logs via any other access path.
5. Trigger code never executes dynamic SQL built from untrusted input.

**Never copy a `SECURITY DEFINER` function to production without verifying ownership and privileges.** Code running with elevated privileges can become a security vulnerability if schemas or inputs are misplaced.

### app.actor Is Not Automatically a Trusted Identity

`current_setting('app.actor', true)` reads a **custom configuration parameter** that an application can set, for example:

```sql
BEGIN;

SELECT set_config('app.actor', 'user-123', true);
SELECT set_config('app.request_id', 'req-789', true);

UPDATE public.demo_orders
SET status = 'PAID'
WHERE order_id = 1;

COMMIT;
```

The third argument `true` in `set_config` scopes the setting **to the current transaction only**, preventing state leakage across connection pools. Still, any client with database connectivity can pass arbitrary actor strings, so treat this as **application-supplied context**, not independent proof of an authenticated user.

If compliance/security requires legally trustworthy actor attribution, combine authentication, principal mapping, and protected log pipelines—potentially adding service-tier logs or an external monitoring system.

## 17. Testing Trigger Behavior and Rollback

In the lab database:

```sql
INSERT INTO public.demo_orders(status, total_amount)
VALUES ('PENDING', 300000)
RETURNING order_id;
```

Suppose the returned `order_id` is **1**. Update it:

```sql
UPDATE public.demo_orders
SET status = 'PAID'
WHERE order_id = 1;

SELECT audit_id, action, old_values, new_values, changed_at
FROM audit.demo_order_changes
WHERE order_id = 1
ORDER BY audit_id;
```

You will see matching `INSERT` and `UPDATE` audit records assuming the statements succeeded and the trigger is active.

Test rollback:

```sql
BEGIN;

UPDATE public.demo_orders
SET status = 'CANCELLED'
WHERE order_id = 1;

ROLLBACK;

SELECT status
FROM public.demo_orders
WHERE order_id = 1;
```

The status remains `PAID`, and no audit entry for the `CANCELLED` change **exists as a committed change**. This is expected for an audit table recording **committed mutations**; if you need to log **rejected attempts**, implement auditing at the application layer or an external log—in-transaction triggers retain no evidence of rolled-back work.

### Audit ID Is Not Absolute Commit Order

`audit_id` generated by an identity sequence generally increases, yet PostgreSQL sequences **do not roll back on transaction abort** and can have gaps. Sequence acquisition order is also not guaranteed to match transaction commit order.

Thus `ORDER BY audit_id` is handy for display in simple systems, yet **is not absolute proof of database-wide commit ordering**. When strict per-entity ordering is needed, use a lock/transaction-protected sequential version number or stream checkpoints.

## 18. Limitations of Trigger-Based Auditing

Trigger auditing is powerful, yet does not automatically create a **tamper-proof** system:

1. **High-privilege roles** can alter objects, disable triggers, or directly modify data/logs within their privileges.
2. **DDL** such as `ALTER TABLE` or `DROP TABLE` is not captured by the row-level DML trigger above.
3. Failed SQL statements or rolled-back transactions normally **leave no committed audit rows** in the same database.
4. External actions (files, message brokers, third-party APIs) are not captured automatically by this trigger.
5. Triggers add **write, WAL, index, and I/O overhead** to every tracked change.
6. Full old/new payloads increase storage size and security exposure.
7. For bulk updates across millions of rows, row-level triggers generate massive audit volumes and prolong transactions.

Strict auditing demands may require **independent/append-only external logs**, strict role separation, access monitoring, hash chaining, or immutable storage. None of those exist merely because a table is named `audit_log`.

### Application-Layer and Database-Layer Auditing Can Complement Each Other

The application usually knows the **business actor and intent** better than the database. Database triggers see DML mutations across all write paths. Combining both gives rich business context while catching out-of-band changes that bypass the main service.

Just define a clear **source of truth** so you do not log two unsynchronized audit streams and confuse them as separate events.

## 19. Event Sourcing: Event History as the Source of Truth

In **event sourcing**, instead of treating a current-state table as the sole source of truth, the application stores business events sequentially and derives current state from them.

Example event sequence for an order:

```text
OrderCreated(orderId=101, total=300000)
      │
      ▼
PaymentConfirmed(orderId=101, paymentId=...)
      │
      ▼
OrderPacked(orderId=101)
      │
      ▼
OrderShipped(orderId=101)
```

An event table:

```sql
CREATE TABLE order_domain_events (
    event_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (order_id, sequence_no)
);

CREATE INDEX ix_order_events_replay
ON order_domain_events(order_id, sequence_no);
```

Each event carries:

- **`event_id`** to deduplicate redeliveries.
- **`sequence_no`** to establish ordering per `order_id`.
- **`event_type`** to express business meaning.
- **`payload`** holding data needed to reconstruct state.
- **`occurred_at`** for when the event happened, which may differ from `recorded_at`.

`UNIQUE(order_id, sequence_no)` stops the same position in an order's stream from being written twice, yet **does not safely allocate sequence numbers when two workers append concurrently**. The application needs transactions, locks/optimistic concurrency, or a controlled append protocol.

### Event Sourcing Is Not Just Adding an Audit Table

An audit log might say "status changed from `PENDING` to `PAID`". Event sourcing demands **domain-meaningful events and schemas rich enough to rebuild state**. For instance, `PaymentConfirmed` may require payment ID, amount, and business metadata—it is not merely a dump of changed columns.

Changing event representations requires **event schema versioning** and replay strategies for historical events. A simple system that only needs price-history lookups rarely warrants the full complexity of event sourcing.

## 20. Outbox Pattern: Writing Data and Events in One Transaction

A classic distributed systems problem:

```text
Application:
  1. UPDATE orders SET status = 'PAID'
  2. Publish OrderPaid message to broker
```

If the database commits yet broker publishing fails, downstream systems never learn the order was paid. If the message is sent before commit and the transaction rolls back, downstream systems process an event that never actually happened.

The **transactional outbox** stores **business data and an outbox event row** inside the same PostgreSQL transaction:

```sql
CREATE TABLE app_outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    published_at TIMESTAMPTZ
);
```

Conceptual example:

```sql
BEGIN;

UPDATE public.demo_orders
SET status = 'PAID'
WHERE order_id = 1
  AND status = 'PENDING';

-- Only insert the event if UPDATE actually affected
-- the intended row per business rules.
INSERT INTO app_outbox_events (
    event_id, aggregate_type, aggregate_id, event_type, payload
)
VALUES (
    '11111111-1111-4111-8111-111111111111'::UUID,
    'Order', 1, 'OrderPaid',
    '{"order_id": 1, "new_status": "PAID"}'::JSONB
);

COMMIT;
```

**This snippet focuses on transaction boundaries**, not a complete workflow. In production, the application must verify that `UPDATE` affected exactly one row before inserting the event, or use `UPDATE ... RETURNING` to tie both steps together.

A separate worker reads unpublished outbox rows, pushes them to the broker, and sets `published_at`. If the worker publishes successfully yet crashes before marking `published_at`, the message will be retried. Therefore downstream consumers still need **idempotency**—do not assume end-to-end exactly-once delivery.

### Outbox vs. Audit Log

- **Audit log:** who/what changed data, for inspection and investigation.
- **Outbox:** which events must be delivered to external systems after commit.
- **Event sourcing:** the event stream itself is the primary source for reconstructing state.

All three can coexist, yet never assume a short-lived outbox table satisfies a 7-year compliance audit requirement.

## 21. Change Data Capture (CDC) and Logical Decoding

PostgreSQL provides **logical decoding**, reading committed changes from WAL to stream logical change records to a consumer. Logical replication and CDC pipelines build on this.

Strengths:

- Captures database changes in near real time without forcing every service to emit webhooks.
- Useful for syncing data warehouses, search engines, or downstream read models.
- Decouples change extraction from the application's synchronous request path.

However, CDC has major constraints:

- Row-level changes do not automatically explain **which business actor** approved them or why.
- `wal_level`, publications/slots, replica identity, and permissions must be configured properly.
- Slow or stalled consumers cause **replication slots to retain WAL**, risking disk exhaustion and operational outages.
- Ordering, transaction boundaries, schema changes, and replayability depend on the protocol, plugin, and consumer.
- Do not treat CDC as permanent history storage without dedicated event retention.

**CDC is not a substitute for backups.** If a consumer receives an accidental `DELETE`, it faithfully propagates that erroneous deletion downstream.

### Choosing Between Triggers and CDC

| Need | Trigger Audit | CDC / Logical Decoding |
|---|---|---|
| Capture actor/reason from app | Can record if app passes trusted context. | Needs extra business metadata enrichment. |
| Guarantee audit row commits with mutation | Yes when written in the same transaction. | Stream is emitted post-commit and processed separately by consumers. |
| Push changes to multiple external systems | Never make network calls from triggers; use outbox/workers instead. | Fits stream/consumer architectures with proper operations. |
| Write-path cost | Adds DML work to the transaction. | Adds WAL, slot, decoding, and stream I/O overhead. |
| Store structured history for as-of queries | Requires dedicated history tables. | Requires building materialized history/projections in consumers. |

## 22. Indexing Historical and Audit Data

History tables quickly dwarf current-state tables. Design indexes around **real query patterns**.

### 22.1. Looking Up the Latest Version of an Entity

```sql
CREATE INDEX ix_price_product_start_desc
ON product_price_versions(product_id, valid_from DESC);
```

Query:

```sql
SELECT price, valid_from, valid_to
FROM product_price_versions
WHERE product_id = 42
ORDER BY valid_from DESC, version_id DESC
LIMIT 1;
```

Filtering by `product_id` and sorting by `valid_from` lets the index serve "latest start date" lookups cleanly. Watch out: **the latest start date may lie in the future** if changes are pre-scheduled, so it is not automatically the currently active price.

### 22.2. Looking Up Audit History for an Entity Over Time

```sql
CREATE INDEX ix_audit_order_changed_desc
ON audit.demo_order_changes(
    order_id,
    changed_at DESC,
    audit_id DESC
);
```

```sql
SELECT audit_id, action, changed_at,
       old_values, new_values
FROM audit.demo_order_changes
WHERE order_id = 1
ORDER BY changed_at DESC, audit_id DESC
LIMIT 50;
```

For deep pagination through long audit histories, prefer **keyset pagination** using `(changed_at, audit_id)` to scan stably in deterministic order instead of large `OFFSET`s.

### 22.3. BRIN for Append-Only Time-Ordered Tables

On huge log tables where rows arrive roughly in `changed_at` order, a **BRIN index** can be compact and effective for time-range scans:

```sql
CREATE INDEX ix_audit_changed_brin
ON audit.demo_order_changes
USING brin(changed_at);
```

BRIN stores summary min/max metadata per page range, so it shines when timestamps **correlate closely with physical row order**. Heavy backfills inserting scattered historical timestamps weaken that correlation and reduce BRIN effectiveness.

BRIN does not replace B-tree for selective point queries like `WHERE order_id = ...`. In practice, pair **B-tree on entity/time** with BRIN considered for massive time-range scans.

### 22.4. GiST for Ranges and Exclusions

`EXCLUDE USING gist` in the price model already maintains a GiST index to stop overlaps. If point-in-time queries write:

```sql
WHERE tstzrange(valid_from, valid_to, '[)')
      @> TIMESTAMPTZ '2026-11-12 10:00:00+07'
```

PostgreSQL can leverage the range/GiST operator class when query conditions and planner estimates align. Actual performance depends on product count, selectivity, statistics, and how `product_id` combines in the predicate.

Always verify plans with `EXPLAIN (ANALYZE, BUFFERS)` in a **test environment**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT version_id, price
FROM product_price_versions
WHERE product_id = 42
  AND tstzrange(valid_from, valid_to, '[)')
      @> TIMESTAMPTZ '2026-11-12 10:00:00+07';
```

`EXPLAIN ANALYZE` **actually executes the statement**; use it safely on `SELECT` here or inside controlled transactions when testing writes.

### 22.5. GIN for JSONB

If audit queries filter inside `new_values`:

```sql
SELECT *
FROM audit.demo_order_changes
WHERE new_values @> '{"status": "PAID"}'::jsonb;
```

A **GIN index** on `jsonb` can accelerate suitable workloads:

```sql
CREATE INDEX ix_audit_new_values_gin
ON audit.demo_order_changes
USING gin(new_values);
```

However, GIN indexes on large JSONB columns add noticeable write cost, disk space, and maintenance overhead. Do not create one by default if lookups primarily filter by `order_id` or `changed_at`.

## 23. Time-Based Partitioning and Retention Policies

Audit/event tables can grow by millions of rows per month. **Declarative partitioning** on `occurred_at` or `changed_at` eases time-window management and enables partition pruning for range-filtered queries.

Example monthly partitioned log table:

```sql
CREATE TABLE activity_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE activity_events_2026_11
PARTITION OF activity_events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO ('2026-12-01 00:00:00+00');

CREATE TABLE activity_events_2026_12
PARTITION OF activity_events
FOR VALUES FROM ('2026-12-01 00:00:00+00')
           TO ('2027-01-01 00:00:00+00');
```

In range partitioning, the lower bound is **inclusive** and the upper bound is **exclusive**; exactly Dec 1 00:00 UTC routes into the December partition, not November.

### Why Does the Primary Key Include occurred_at?

In PostgreSQL, a **PRIMARY KEY or UNIQUE constraint on a partitioned table** must include all partition key columns under supported rules, because PostgreSQL does not automatically maintain a single global uniqueness index spanning all partitions.

Consequently, `PRIMARY KEY(event_id, occurred_at)` does not guarantee that **`event_id` alone** is globally unique across the entire table if the same ID appears in two different months. When events need globally unique IDs, rely on:

- A sufficiently collision-free ID generator (such as application-generated UUIDs), **and/or**
- A dedicated deduplication registry with appropriate uniqueness,
- Key and partition key design aligned with requirements.

Never assume an identity sequence on a partitioned table enforces global uniqueness on `event_id`.

### Queries Enabling Partition Pruning

```sql
SELECT event_id, event_type, actor
FROM activity_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
```

With exact bounds, the planner can prune partitions outside the queried window.

### Retention Is a Business and Legal Requirement

Not all logs belong forever:

- Compliance audits may require specific retention durations and tightly gated deletion rights.
- Replayable event logs must not be purged while consumers/projections still depend on them.
- Delivered outbox rows may have shorter retention, yet still need reconciliation checks.
- Personal data may carry deletion/anonymization requests that must be balanced against legitimate audit obligations.

Partitioning makes monthly lifecycle management practical, yet **does not define retention policy by itself**. `DROP`/`DETACH` partition jobs or deletions must follow a runbook covering reconciliation, backup/restore, approvals, and downstream dependencies.

## 24. Late-Arriving Events and Retroactive Corrections

An offline point-of-sale system might see:

```text
09:00  Order created on store terminal.
09:05  Terminal loses network connectivity.
10:30  Terminal uploads order to server.
10:31  PostgreSQL commits the record.
```

If you only store server-side `created_at DEFAULT now()`, a report shows a "09:00 order" as a "10:31 order". Instead, separate the timestamps:

```sql
CREATE TABLE offline_order_events (
    event_id UUID PRIMARY KEY,
    store_id BIGINT NOT NULL,
    device_event_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    payload JSONB NOT NULL
);
```

**Client-supplied `device_event_at` is not always absolute truth**: device clocks can drift or be tampered with. Applications may need skew checks, source signatures, sequence numbers, sync timestamps, and explicit precedence rules for late arrivals.

### A Late Event Can Split Valid-Time History

Suppose price 100 was entered on Nov 1; on Nov 14 a notice arrives that the true price from Nov 5 onward should have been 105. You may need to **split the historical interval**:

```text
Before correction:
[Nov 1, infinity) → 100

After valid business correction:
[Nov 1, Nov 5)    → 100
[Nov 5, infinity) → 105
```

Do not simply overwrite the entire old interval to 105, which would rewrite Nov 3 reports to 105. And if you also need to know **what the system believed on Nov 10**, you need bitemporal modeling rather than rewriting valid-time intervals in place.

For retroactive edits, define explicitly:

1. Are past records rewritten in valid time, or are only new adjustment entries added?
2. Should "as-of valid time" queries reflect the latest corrected version?
3. Must the pre-correction history be preserved for explainability?
4. Do retroactive edits affect already-finalized invoices or settlements?
5. Do corrections require approvals, reason codes, and audit evidence?

## 25. Concurrency, Atomicity, and Temporal Consistency

History designs break when two requests modify the same entity simultaneously. For example, two workers both read `valid_to IS NULL` and both attempt to insert a new price version. Without protection, overlapping intervals or lost updates can occur.

Combine multiple layers of protection:

- **Transactions:** close the old version and insert the new version inside one atomic unit.
- **Per-entity locking:** e.g., `SELECT ... FOR UPDATE` on the parent row to serialize price changes.
- **Database constraints:** `EXCLUDE` for non-overlap, `CHECK` for valid intervals, `FOREIGN KEY` for entity existence.
- **Optimistic concurrency where fitting:** version counters or expected-state predicates on write.
- **Bounded retries:** retry retryable concurrency errors cleanly after rollback without blindly re-sending external side effects.

### Do Not Confuse Clocks with Concurrency Control

Two requests can receive very close `clock_timestamp()` values and race on updates. Timestamps **never replace transaction locks or constraints**.

If the business accepts client-chosen `valid_from` values, two requests can pick the exact same timestamp or out-of-order timestamps. Define explicit acceptance/backdating rules rather than assuming "timestamps always increase".

### Multi-Table Business Units

A contract amendment may require:

1. Inserting a new contract version.
2. Recording an audit entry with reason and approver.
3. Inserting an outbox event to send notifications.

If all steps must succeed together, wrap them in **one PostgreSQL transaction**. Trigger-based auditing joins the transaction automatically. For outboxes, commit the event row first and let an external worker handle delivery afterward.

Avoid making slow external API or broker calls while holding database locks whenever possible: doing so prolongs transactions, increases lock contention, and complicates retries.

## 26. Security, Privileges, and Trustworthiness of History

History data can be **more sensitive than current data** because it retains superseded values or details users expected to be removed.

Key principles:

1. **Least privilege:** reporting roles do not automatically need `SELECT` on all audit payloads; application roles do not automatically need `UPDATE`/`DELETE` on audit logs.
2. **Write separation:** only controlled write paths should append audit records; avoid granting unnecessary history modification privileges.
3. **Actor integrity:** distinguish verified authenticated principals from client-supplied actor strings.
4. **Payload minimization:** store only necessary fields; mask or redact secrets, tokens, and sensitive PII.
5. **Tamper resistance:** when independent evidence is needed, ship logs to a privilege-separated audit system or immutable storage.
6. **Retention and lawful deletion:** enforce concrete retention schedules rather than keeping everything forever just because disk is available.
7. **Recoverability:** backups and restore drills must cover history, audit logs, and key metadata.
8. **Privileged action monitoring:** alert on trigger changes, schema DDL, privilege grants, or bulk imports bypassing audit paths.

### Triggers Do Not Capture All Security Events

Row-level triggers do not log **failed logins**, **`SELECT` queries**, **DDL**, or rolled-back actions. If you need visibility into those events, design observability and auditing at the proper layer—server logs, dedicated audit extensions, or application-level telemetry.

## 27. Monitoring the Health of History and Log Tables

Historical data typically grows monotonically; plan for operations:

| What to Watch | Why |
|---|---|
| Row growth rate and table/index size | Forecast storage and backup/restore impact. |
| `UPDATE`/`DELETE` ratio in history tables | True append-only logs behave differently from heavily updated version tables. |
| Autovacuum, dead tuples, bloat | Version updates and retention purges generate dead tuples. |
| As-of query and audit lookup latency | Keep indexes effective across multi-year histories. |
| Partition coverage and default partition | Prevent insert failures when a new month arrives without a partition. |
| Outbox backlog and publish lag | Detect stalled consumers/brokers; prevent dropped or delayed events. |
| Replication slots and WAL retention | Stalled CDC consumers can cause `pg_wal` to grow rapidly. |
| Non-overlap / gap invariants per entity | Catch write paths that bypassed protocols or legacy anomalies. |
| Audit object privileges and changes | Guard against tampering or disabled triggers. |

Example table size check:

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size('product_price_versions'::regclass)
    ) AS price_history_total_size,
    pg_size_pretty(
        pg_total_relation_size('audit.demo_order_changes'::regclass)
    ) AS audit_total_size;
```

For partitioned tables, make sure you inspect the right parent/leaf partition level: some relation size functions on a parent table do not automatically sum all leaf partitions the way users expect. Monitoring tools should understand partition trees.

## 28. Choosing Designs for Three Concrete Scenarios

### Scenario A — Daily-Changing Selling Prices

Requirements: schedule future prices, query the price on date T, forbid two overlapping prices.

**Suitable design:** `product_price_versions` with `valid_from/valid_to` or a `tstzrange` column, `EXCLUDE` constraint, as-of queries, and controlled update transactions.

If you also need to know when a price was retroactively corrected and what it used to be, extend to **bitemporal** or keep separate assertions/audits.

### Scenario B — Order Status History

Requirements: see when an order moved `PENDING → PAID → SHIPPED` and who approved each step.

**Suitable design:** a current-state table for fast API reads, paired with **append-only status events** carrying entity ID, event type, actor, event time, request ID, and sequence number; optionally add an audit trigger to capture out-of-band edits.

To notify external brokers, add an outbox write inside the same status-transition transaction.

### Scenario C — Sensor / Telemetry Logs

Requirements: high-throughput ingestion per second, late-arriving data possible, filter by device and time window, expire old logs per retention.

**Suitable design:** separate `event_time` and `received_at`, stable deduplication key, partitioning on a chosen timestamp, B-tree on `(device_id, event_time)` if device lookups dominate, and optionally BRIN on time when data correlates physically.

Never replace sensor timestamps with `DEFAULT now()` if analyzing actual event time—yet also validate rather than blindly trusting device clocks.

## 29. Common Mistakes

**"Just having `updated_at` gives us history."** False. `updated_at` only records the last edit time, not prior values or validity intervals of every version.

**"PostgreSQL MVCC lets us read every `UPDATE`d version from months ago."** False. MVCC serves concurrency and transaction snapshots; vacuum reclaims old tuples.

**"`TIMESTAMPTZ` preserves the exact time zone name the user entered."** False. It stores an instant and displays in the session time zone; preserving an IANA zone requires a separate column.

**"Every day is always 24 hours."** False in any DST-observing zone; local-day queries need exact zone-aware boundaries.

**"`now()` advances after every SQL statement."** False inside a transaction; it stays pinned to transaction start.

**"`valid_to IS NULL` always means the price is active today."** False if `valid_from` lies in the future.

**"`CHECK(valid_to > valid_from)` prevents all overlaps."** False. It validates single rows, not relationships across rows of the same entity.

**"If `EXCLUDE` prevents overlaps, the timeline also has no gaps."** False. Overlap constraints do not check continuity.

**"Just keeping the latest row plus old/new audit rows makes as-of queries easy."** Not necessarily. Audit logs may require replay and lack valid-time semantics, especially under retroactive fixes.

**"Bitemporal only needs `created_at` and `updated_at`."** False. It requires versioned assertions across both valid time and recorded/system time.

**"Trigger audits are tamper-proof logs."** False. High privileges, trigger alterations, and non-DML operations sit outside trigger guarantees.

**"If a transaction rolls back, the audit row remains to prove the attempt."** False when auditing inside the same transaction; logging failed attempts requires an external or out-of-transaction mechanism.

**"Audit ID always matches commit order."** False. Sequences can have gaps and are allocated before commit.

**"CDC automatically tells us which business user approved a change."** False. Business actor metadata must be captured at the appropriate layer.

**"Using an outbox guarantees consumers receive messages only once."** False. Outboxes still require idempotent consumers because failures can trigger redelivery.

**"A partitioned table with an identity `event_id` guarantees `event_id` is unique across all partitions."** Global uniqueness is not enforced automatically unless the partition key is part of the unique key.

**"Add every possible index to the audit log so queries are always fast."** Every index adds write, WAL, disk, and maintenance overhead; tune for actual queries.

## 30. Practice Exercises

### Exercise 1 — Choosing Temporal Types

Given these data items:

1. Customer date of birth.
2. Timestamp when the bank confirmed payment.
3. Daily opening time **09:00 every day** for a store in `Europe/Berlin`.
4. A 90-minute reservation hold duration.
5. Sensor measurement time and server packet ingestion time.

Choose `date`, `time`, `timestamptz`, `interval`, or an appropriate combination. Explain when storing a separate IANA time zone name is required.

### Exercise 2 — As-Of Queries

Given the price history of product 42:

```text
[Nov 1 00:00, Nov 10 00:00) -> 100000
[Nov 10 00:00, Nov 14 09:00) -> 115000
[Nov 14 09:00, infinity)     -> 125000
```

Write SQL to look up the price at Nov 9 23:59, exactly Nov 10 00:00, and exactly Nov 14 09:00. Explain why `[)` avoids boundary overlaps.

### Exercise 3 — Overlap Constraint

A room-booking table has `room_id` and `booked_period tstzrange`. Design:

- `CHECK (NOT isempty(booked_period))`.
- `EXCLUDE USING gist` preventing two confirmed bookings for the same room from overlapping.
- Conditions allowing back-to-back bookings where one ends at the exact instant the next begins.

*Hint:* `btree_gist` supplies `=` operators for standard ID types, `&&` checks overlap, and a **partial exclusion constraint** can restrict exclusion to `CONFIRMED` bookings only.

### Exercise 4 — Price Update Transaction

Write a transaction updating product 42's price from 125,000 to 129,000 at a fixed instant T. Explain why closing the old version and inserting the new version must share one transaction, why locking the parent row helps, and why the `EXCLUDE` constraint is still necessary.

### Exercise 5 — Distinguishing Valid Time and Recorded Time

On Nov 14, the system learns that a price effective since Nov 1 should have been 120 instead of 100. Describe how to answer:

1. What price **was effective** on Nov 5 per corrected data.
2. What price the system **believed on Nov 10** for Nov 5.

Explain why an SCD2 table tracking only valid time cannot necessarily answer both questions.

### Exercise 6 — Audit Triggers and Rollback

An `AFTER UPDATE` trigger writes `OLD`/`NEW` into an audit table inside the same transaction. The application updates an order and then runs `ROLLBACK`. Predict the state of both the order and the audit record after rollback. Also describe an approach if the system must log **rejected access attempts**.

### Exercise 7 — Outbox and Lost Acknowledgments

The application commits `OrderPaid` along with an outbox row. A worker delivers the message successfully yet loses its database connection before setting `published_at`. On the next run, the worker publishes it again.

Explain why consumers must rely on `event_id`/idempotency, and why placing the outbox in the same transaction eliminates one class of failures without creating end-to-end exactly-once delivery.

### Exercise 8 — Large History and Indexing

A system stores 200 million events, mostly queried by `device_id` and `event_time`; data arrives mostly in chronological order, though daily backfills also run.

Propose appropriate B-tree, BRIN, or partitioning strategies, state when BRIN loses effectiveness, and explain the uniqueness limitation of partitioned tables.

### Exercise 9 — Is the Log Tamper-Resistant Enough?

An audit table records actor, time, and old/new values, yet the application account holds `UPDATE` and `DELETE` privileges on the audit table itself, and administrators can disable triggers. Identify the risks and propose improvements covering privileges, independent log destinations, payload security, and retention.

### Exercise 10 — Retroactive Correction Workflow

Contract A has a fee of 1,000,000 effective from Oct 1. On Nov 15, operations requests changing the fee to 900,000 effective from Nov 1, yet invoices were already issued during Nov 1–14.

Propose a workflow covering approval, valid-time versioning, recorded time, handling finalized invoices, audit reasons, and issuing adjustment events—rather than silently running `UPDATE` on old rows.

## Conclusion

Designing temporal data in PostgreSQL begins with **choosing the right meaning for each timestamp**: when an event occurred, when the system received it, when a value took effect, and when the system recorded that assertion. **`timestamptz`** stores absolute instants; **`date`**, `time`, and explicit time zone names fit local calendar rules better. Use **`[)` intervals**, `tstzrange`, and `EXCLUDE USING gist` to model consistent non-overlapping version histories.

**Version tables** serve *as-of* state queries, **bitemporal** models serve both valid time and historical system beliefs, **audit logs** trace mutations, and **outbox/CDC/event sourcing** solve event propagation or state reconstruction problems. These patterns can be combined, yet never substitute for one another automatically.

A strong design does more than pass today's queries: it incorporates **transactions and anti-conflict constraints**, indexes tailored to history lookups, controlled partitioning and retention, protected actors and sensitive payloads, disaster recoverability, and transparent retroactive correction workflows. When those needs are designed upfront, PostgreSQL preserves not just "the data right now", but **reliable evidence of how data changed over time**.
