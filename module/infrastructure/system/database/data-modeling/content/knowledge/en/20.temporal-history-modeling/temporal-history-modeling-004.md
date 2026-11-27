# Closed Bounds, Open Bounds, and Rules for Preventing Overlapping Effective Intervals

## 1. When Two Versions Touch the Same Timestamp, Which Value Is Right?

In the **DATABASE_DATA_MODELING** module, a critical part of translating business requirements into a data model is determining **when** a relationship or value is effective. The **Time and History** chapter raises a question that primary keys and updated-date columns alone cannot resolve: if two consecutive versions share a transition boundary on July 1, which version is allowed to apply on July 1 itself?

Consider a service with the following price table:

| Version | Price | Business Interpretation |
|---|---:|---|
| A | 100,000 VND | From Jan 1 through the end of June |
| B | 120,000 VND | Starting from July 1 |
| C | 125,000 VND | Planned to apply from July 15 |

If inconsistent conditions such as **valid_from <= query_date <= valid_to** are used, July 1 can match both A and B. If start or end dates are omitted in another branch, the system may find no version at all. Both bugs are severe when the data governs pricing, contracts, access permissions, staff assignments, or effective statuses.

This lesson addresses three questions:

1. **What do closed and open bounds mean?** Why does the half-open interval convention **[from, to)** usually eliminate disputes at transition boundaries?
2. **When do two intervals overlap?** How do you distinguish overlap from mere adjacency, gaps, containment, and unbounded intervals?
3. **How do you turn rules into data constraints?** How to use business keys, range types, exclusion constraints, transactions, and testing to prevent conflicting data even under concurrent writes.

The goal is to read a requirement such as **“a service plan has only one active VND price per day”**, design the right schema, and prove that the schema preserves that invariant. The same principles apply when moving from relational databases to document, graph, or analytical stores, even though the technical mechanisms differ.

## 2. A Simple Mathematical Model of Time Intervals

Given two instants **a** and **b**, with **a < b**, an interval can include or exclude each endpoint:

| Notation | Includes a? | Includes b? | Spoken Form |
|---|---|---|---|
| **[a, b]** | Yes | Yes | Closed on both ends |
| **[a, b)** | Yes | No | Closed-left, open-right |
| **(a, b]** | No | Yes | Open-left, closed-right |
| **(a, b)** | No | No | Open on both ends |

Example using working hours:

~~~text
A = [09:00, 10:00)
B = [10:00, 11:00)

09:00 belongs to A.
09:59:59 belongs to A.
10:00 does not belong to A, but belongs to B.
11:00 does not belong to B.
~~~

Intervals **A** and **B** meet at 10:00, yet **do not both contain 10:00**. Thus a resource can be assigned to A until before 10:00 and to B starting at 10:00 without any instant being double-assigned.

Conversely, if A is **[09:00, 10:00]** and B is **[10:00, 11:00]**, both include 10:00, creating a single point of overlap. The difference is just a bracket character, yet it completely changes query results and constraints.

### 2.1. Intervals and Instants Are Not the Same

An **interval** represents sustained validity. An **instant** represents a single event or milestone.

- “Customer belongs to the VIP tier from March 1 until before June 1”: use an interval.
- “Customer submitted a request at 09:20:13”: use an event instant.
- “Payment voucher was recorded at 09:20:15”: a recording instant, not an entitlement interval on its own.
- “VIP privilege revoked at June 1 00:00”: this is an **interval end bound**, meaning the privilege no longer holds at that exact instant.

Real-world data often needs both event instants and effective intervals. Never substitute one for the other simply because column names sound similar.

### 2.2. Empty Intervals and Invalid Intervals

With the half-open interval **[a, a)**, no point satisfies both greater-than-or-equal-to a and strictly-less-than a. That is an **empty interval**—not an interval “valid for a split second.”

If you need to record an event at exact instant a, store an event at a. If you need to store a version effective over a duration, choose an end bound **after** the start bound, or use an unbounded upper limit.

A value like **[Jul 20, Jul 10)** also has reversed bounds: start after end. APIs must never treat this as valid or silently swap the two bounds.

## 3. Why Use the [from, to) Convention?

A widely adopted convention for effective time is:

~~~text
[valid_from, valid_to)

Condition for instant t to be inside the interval:
valid_from <= t AND t < valid_to
~~~

The strength of this representation is that **the end of the previous version can equal the start of the next version**. There is no need to invent a “buffer gap,” or subtract one second or one microsecond to avoid boundary collisions.

### 3.1. Price Schedule Timeline

~~~text
          Jan 1                 Jul 1               Oct 1
            |                     |                   |
  [--------- A -------------------)
                                  [-------- B --------)
                                                      [--- C --->

A: [2026-01-01, 2026-07-01) = 100,000 VND
B: [2026-07-01, 2026-10-01) = 120,000 VND
C: [2026-10-01, unbounded)  = 130,000 VND
~~~

| Query Date | Matching Version | Why |
|---|---|---|
| 2025-12-31 | None | Before A's start bound |
| 2026-01-01 | A | Left bound of A is inclusive |
| 2026-06-30 | A | Still before right bound Jul 1 |
| 2026-07-01 | B | A excludes right bound; B includes left bound |
| 2026-09-30 | B | Still before right bound Oct 1 |
| 2026-10-01 | C | B has ended; C begins |
| 2026-11-15 | C | C has no end bound yet |

When designing with two columns **valid_from** and **valid_to**, the lookup predicate is typically:

~~~sql
SELECT monthly_fee
FROM plan_price_version_columns
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_from <= DATE '2026-07-01'
  AND (
      valid_to IS NULL
      OR DATE '2026-07-01' < valid_to
  );
~~~

**plan_price_version_columns** is an illustrative table name for a two-column model, not the table created in the range-based PostgreSQL example in section 7.

### 3.2. Why the “Until 23:59:59” Trick Easily Breaks

Suppose price A applies “through the end of June 30.” An unsafe shortcut is storing **2026-06-30 23:59:59** as the end bound. However, if the system supports milliseconds or microseconds, instants between 23:59:59 and 00:00 on July 1 fall outside A. Whenever clock precision changes, code develops silent gaps.

In a date-based model, store **valid_to = 2026-07-01** and compare **t < valid_to**. In a timestamp-based model, likewise use the start instant of the next version as the exclusive right bound. This avoids depending on any system's “smallest time unit.”

### 3.3. [from, to) Is a Convention, Not an Absolute Law

Some domains describe ranges as **closed on both ends**; for example, “guest occupies the room from July 1 through July 3” in **whole calendar days**. This can be normalized to half-open **[Jul 1, Jul 4)**, provided July 4 is understood as **no longer effective**.

However, that conversion only holds when the granularity is known to be **calendar days**. Never blindly add one day to flip brackets on continuous timestamp intervals or when end semantics are unclear. Business meaning must be agreed upon before normalizing data.

## 4. Preventing Overlaps: Defining Exactly What Is Forbidden

Two intervals **overlap** if they share **at least one instant belonging to both intervals**. For **non-empty, half-open, finite-bound** intervals:

~~~text
A = [a_start, a_end)
B = [b_start, b_end)

A and B overlap when:
a_start < b_end AND b_start < a_end

A ends exactly when B begins:
a_end = b_start  =>  no overlap
~~~

The condition above uses **strict less-than (<)**, not **<=**. Using **<=** would misclassify two intervals merely touching at a boundary as overlapping despite both following the half-open convention.

### 4.1. Relationships to Distinguish

| Interval A | Interval B | Relationship | Overlap? |
|---|---|---|---|
| [Jan 1, Mar 1) | [Mar 1, Jun 1) | Adjacent | No |
| [Jan 1, Apr 1) | [Mar 1, Jun 1) | Partial intersection | Yes |
| [Jan 1, Jul 1) | [Mar 1, May 1) | A contains B | Yes |
| [Mar 1, May 1) | [Jan 1, Jul 1) | A inside B | Yes |
| [Jan 1, Mar 1) | [May 1, Jul 1) | Separated by a gap | No |
| [Jan 1, May 1) | [Jan 1, May 1) | Exact duplicate | Yes |
| [Jan 1, infinity) | [Jul 1, Aug 1) | A contains B | Yes |

A common mistake is checking only **“does B's start date fall inside A?”** That check misses the case where **B starts before A and ends after A**, meaning B completely encloses A. To catch all overlap shapes, use the general interval-intersection condition or native DBMS range operators.

### 4.2. “Non-Overlapping” Must Be Scoped to the Business Key

Suppose a system prices by **plan** and **currency**. VND and USD prices can both take effect on July 1; that is not a conflict because they belong to distinct pricing scopes.

State the invariant explicitly:

> For a given **(plan_id, currency_code)** pair, at most one effective price version may exist on any business date.

Logically:

~~~text
For any two rows A, B:
If A.plan_id = B.plan_id
   and A.currency_code = B.currency_code
   and A.id <> B.id
then A.valid_period and B.valid_period must NOT intersect.
~~~

If pricing also distinguishes **region** or **customer segment**, the business key must include those dimensions. If one entity can simultaneously hold multiple valid relationship types, do not apply a single-version rule across all of them.

Conversely, **a primary key on version_id alone cannot prevent overlaps**: two rows with different IDs can still claim the same plan has two different prices on July 1.

## 5. Time Boundaries: Calendar Dates, Instants, and Time Zones

An interval with mathematically sound bounds can still be wrong in business terms if the data type does not fit.

### 5.1. Calendar-Date Time — date

Use dates when requirements say “price takes effect on July 1 per the business calendar,” “contract takes effect at the start of the month,” or “member receives benefits for a number of days.”

~~~text
[2026-07-01, 2026-08-01)
= all calendar days from Jul 1 through Jul 31.
~~~

The bounds are **calendar dates**, not 00:00 UTC timestamps. If the business calendar uses Vietnam local dates, converting that date into a timestamp must use an agreed time zone—never silently use the server's local time zone.

### 5.2. Point-in-Time Precision — timestamp with time zone

When requirements are exact to the minute or second—for example, “meeting room booked from 09:00 to 10:00”—use timestamps with absolute-instant semantics. PostgreSQL supports **timestamptz** and **tstzrange**.

~~~sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-22 09:00:00+07',
    TIMESTAMPTZ '2026-11-22 10:00:00+07',
    '[)'
) AS reservation_period;
~~~

**09:00+07** and **02:00+00** represent the same absolute instant. Display formatting may vary by time zone, while interval intersection always compares along the same absolute timeline.

If a business schedules by **recurring local wall-clock time on specific dates**, store time zone rules as well. In regions observing Daylight Saving Time (DST), a local wall-clock time may not exist or may occur twice; timestamp generation must explicitly handle ambiguity. Storing only the string “01:30” does not identify an absolute instant.

### 5.3. Never Mix date and timestamp Through Implicit Rules

For example, “VND price effective July 1” and “transaction occurred at 2026-07-01 00:30+07” require mapping to the **business date in the designated time zone** before choosing a price version. If the application converts 00:30+07 to UTC and extracts the UTC date June 30, a join on UTC date would wrongly pick the old price.

An explicit rule could be:

~~~text
business_date =
    calendar date of the transaction instant
    in the time zone of the pricing market
~~~

Only after determining **business_date** do you query the **daterange** interval.

## 6. Unbounded Limits, NULL, and Unknown States

Many version histories have a currently active record whose **end date is not yet known**. Two common patterns exist:

- Two columns **valid_from**, **valid_to**, with the convention **valid_to IS NULL** meaning the end bound is undetermined.
- A single range column, such as **daterange**, with an **unbounded upper limit**.

Example:

~~~sql
SELECT daterange(
    DATE '2026-10-01',
    NULL,
    '[)'
) AS open_ended_period;
~~~

This is a **non-NULL daterange value** with an unbounded upper limit. Distinguish it from setting the entire **valid_period = NULL** column, because a NULL range column discards all interval information.

In PostgreSQL, you can inspect it with:

~~~sql
SELECT
    lower(daterange(DATE '2026-10-01', NULL, '[)')) AS begins_on,
    upper_inf(daterange(DATE '2026-10-01', NULL, '[)')) AS no_upper_bound;
-- begins_on = 2026-10-01; no_upper_bound = true
~~~

**An unbounded range limit** and **the special timestamp/date value infinity** are two different concepts in PostgreSQL. An *unbounded* range endpoint is not identical to a finite endpoint set far in the future, nor is it necessarily identical to using the special **infinity** date/timestamp value.

For APIs or data imported from other systems, agree explicitly on how “not yet ended” is represented; never let NULL, 9999-12-31, infinity, and empty strings carry the same meaning without normalization rules.

### 6.1. What If the Start Bound Is Unknown?

If a legacy file only states “effective around the end of Q2,” do not invent an exact date just to satisfy NOT NULL. You may need **date_precision**, **source_confidence**, or an uncertainty window, plus a verification workflow before treating the version as officially active.

A one-sided infinite range must not be used to mask missing data. **“Effective since before the system existed”** and **“start date unknown”** are two different business statements.

## 7. Translating Rules into PostgreSQL Constraints

PostgreSQL provides range types and overlap operators, enabling non-overlap invariants to be enforced directly in the database. The next example assumes **each plan and currency has at most one active price on any given day**.

### 7.1. Schema with Explicit Pricing Scope

We introduce a **price_scope** entity to uniquely identify each plan + currency combination. Every price effective period references that scope.

~~~sql
-- Provides = comparison for bigint in EXCLUDE GiST index.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE price_scope (
    scope_id      bigint PRIMARY KEY,
    plan_id       bigint NOT NULL,
    currency_code text NOT NULL
                  CHECK (currency_code ~ '^[A-Z]{3}$'),
    UNIQUE (plan_id, currency_code)
);

CREATE TABLE plan_price_period (
    period_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope_id       bigint NOT NULL REFERENCES price_scope(scope_id),
    monthly_fee    numeric(14, 2) NOT NULL CHECK (monthly_fee >= 0),
    valid_period   daterange NOT NULL,
    decision_ref   text NOT NULL,
    recorded_at    timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_price_period_bounds
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_one_price_at_a_time
        EXCLUDE USING gist (
            scope_id WITH =,
            valid_period WITH &&
        )
);
~~~

Each constraint serves a distinct responsibility:

| Mechanism | What It Protects |
|---|---|
| **PRIMARY KEY(period_id)** | Every version record has its own unique ID |
| **FOREIGN KEY(scope_id)** | Version belongs to an existing pricing scope |
| **UNIQUE(plan_id, currency_code)** | No duplicate scope identifiers for the same plan and currency |
| **NOT NULL** on scope and period | Prevents NULL values from making overlap checks indeterminate |
| **CHECK NOT isempty(valid_period)** | Rejects empty intervals |
| **CHECK lower_inc and NOT upper_inc** | Ensures boundary interpretation is **[from, to)** |
| **CHECK NOT lower_inf** | Every version must have a concrete start date |
| **EXCLUDE USING gist** | Within the same scope, two effective intervals cannot intersect |

In PostgreSQL, **daterange** is a discrete range type canonicalized into standard form (normally **[)**); the boundary checks are still stated explicitly to document the design invariant. For other range types or when porting to another DBMS, do not assume identical canonicalization behavior.

**CREATE EXTENSION** requires appropriate privileges and deployment policies; in production, it belongs in migrations managed by database operations.

### 7.2. Sample Data and Boundary Checks

~~~sql
INSERT INTO price_scope (scope_id, plan_id, currency_code)
VALUES (17, 7, 'VND');

INSERT INTO plan_price_period (
    scope_id, monthly_fee, valid_period, decision_ref
)
VALUES
(
    17, 100000,
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)'),
    'PRICE-2026-H1'
),
(
    17, 120000,
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)'),
    'PRICE-2026-Q3'
),
(
    17, 130000,
    daterange(DATE '2026-10-01', NULL, '[)'),
    'PRICE-2026-Q4'
);
~~~

Verify the price on the transition date:

~~~sql
SELECT monthly_fee
FROM plan_price_period
WHERE scope_id = 17
  AND valid_period @> DATE '2026-07-01';
-- 120000.00, exactly one row
~~~

The **@>** operator tests whether the range on the left **contains** the date on the right. PostgreSQL honors the defined bounds automatically; there is no need to repeat manual **>=** and **<** predicates in every query.

Verify overlap rejection:

~~~sql
INSERT INTO plan_price_period (
    scope_id, monthly_fee, valid_period, decision_ref
)
VALUES (
    17, 125000,
    daterange(DATE '2026-09-15', DATE '2026-10-15', '[)'),
    'BAD-OVERLAPPING-DECISION'
);
-- Rejected because the interval intersects existing versions.
~~~

In application code, constraint violations must be caught and translated into conflict responses or clean retry handling. Never swallow the error and report “saved successfully.”

### 7.3. Checking Duplicate Start Dates Is Not Enough

If you only define:

~~~sql
UNIQUE (scope_id, valid_from)
~~~

then **[Jul 1, Oct 1)** and **[Aug 15, Sep 15)** have different start dates yet overlap across an entire month. Unique indexes only prevent **duplicate point values**, whereas this problem requires forbidding **interval intersection**.

In a DBMS without native range/exclusion types, you can store two boundary columns and enforce overlap checks via transactions with appropriate locking. However, a **SELECT-then-INSERT** check under default isolation is unsafe under concurrency; you need scope locking, appropriate Serializable isolation, or another database-enforced invariant mechanism.

## 8. Non-Overlapping, Adjacent, and Gapless Are Three Separate Rules

Suppose scope 17 has three versions:

~~~text
P1: [Jan 1, Jul 1)
P2: [Jul 1, Oct 1)
P3: [Oct 1, infinity)
~~~

**Non-overlapping:** No date belongs to two or more versions.

**Adjacent:** P1's right bound equals P2's left bound; the two versions connect seamlessly without overlapping.

**Gapless:** Across the entire period during which the service requires a price, at least one valid version always exists.

The **EXCLUDE** constraint in section 7 guarantees **non-overlapping**, yet **does not guarantee gaplessness**. For example, **[Jan 1, Jul 1)** and **[Jul 3, Oct 1)** do not overlap, even though July 1 and July 2 have no price.

### 8.1. When Is a Gap Valid?

A commerce platform might intentionally suspend sales of a product on July 1–2. In that case, unpriced days are a valid business state. Conversely, a continuous subscription billing engine may require a valid price for **every active day of a contract**.

Distinguish two invariants:

- **At most one:** non-overlapping; zero versions allowed.
- **Exactly one:** non-overlapping **and** fully covering the required horizon.

If the business says “exactly one,” the definition must also specify the **mandatory coverage horizon**, such as from launch date to retirement date. You cannot prove “exactly one price on every day” without defining the domain of relevant days.

### 8.2. Finding Gaps Between Records

Assuming intervals are already non-overlapping, **internal** gaps can be found using window functions:

~~~sql
WITH timeline AS (
    SELECT
        scope_id,
        upper(valid_period) AS end_of_current,
        LEAD(lower(valid_period)) OVER (
            PARTITION BY scope_id
            ORDER BY lower(valid_period)
        ) AS start_of_next
    FROM plan_price_period
)
SELECT
    scope_id,
    end_of_current AS gap_from,
    start_of_next AS gap_to
FROM timeline
WHERE end_of_current IS NOT NULL
  AND start_of_next IS NOT NULL
  AND end_of_current < start_of_next;
~~~

The output lists gaps of the form **[gap_from, gap_to)** between consecutive versions.

This query **does not detect** missing coverage before the first version or after the last version. To check full coverage, compare against the plan's active period and service launch/end rules.

### 8.3. Merging Adjacent Intervals with Equal Values

Suppose:

~~~text
[Jan 1, Apr 1) → 100000
[Apr 1, Jul 1) → 100000
~~~

For price lookup alone, they could be merged into **[Jan 1, Jul 1)**. However, if the two intervals originated from two distinct pricing decisions, merging them can erase traceability to separate approval documents. Coalescing rules must consider **business lineage and audit needs**, not merely value equality.

## 9. Preventing Overlaps Under Concurrent Updates

Suppose analyst A schedules a price increase from July 1, while analyst B simultaneously schedules a discount from June 15 to July 15. Both may read the same initial timeline and generate conflicting schedules.

A common bug is:

~~~text
1. SELECT checks that no intersecting interval exists.
2. If none, INSERT the new record.
~~~

When A and B run concurrently, both can observe “no conflicting rows” before either transaction commits. Without tight constraints or locking, two overlapping rows can both be persisted.

### 9.1. Combining Transactions, Locks, and Constraints

The design in section 7 includes **price_scope** with one stable row per pricing scope. That row can be locked while modifying the schedule:

~~~sql
BEGIN;

SELECT scope_id
FROM price_scope
WHERE scope_id = 17
FOR UPDATE;

-- Read current timeline of scope 17.
-- Validate decision and recompute affected intervals.
-- UPDATE/INSERT/DELETE per business rules and verify results.

COMMIT;
~~~

The **price_scope** row acts as a serialization point for requests targeting the same scope. When all write paths follow this locking protocol, concurrent edits to the same scope execute sequentially. The **EXCLUDE** constraint remains essential as a safeguard against bugs or write paths that bypass application checks.

Restrict direct write privileges on the history table or encapsulate edits inside a service/stored procedure so all update paths follow the same rules. Never rely solely on UI-level checks.

### 9.2. Modifying an Open-Ended Version

Before applying a new price from December 1, the active version is:

~~~text
[Oct 1, infinity) → 130,000 VND
~~~

To add the new version:

~~~text
[Dec 1, infinity) → 140,000 VND
~~~

we must shorten the existing interval:

~~~text
[Oct 1, Dec 1)    → 130,000 VND
[Dec 1, infinity) → 140,000 VND
~~~

An illustrative transaction with known data:

~~~sql
BEGIN;

SELECT scope_id
FROM price_scope
WHERE scope_id = 17
FOR UPDATE;

UPDATE plan_price_period
SET valid_period = daterange(
    DATE '2026-10-01',
    DATE '2026-12-01',
    '[)'
)
WHERE scope_id = 17
  AND valid_period =
      daterange(DATE '2026-10-01', NULL, '[)')
RETURNING period_id;

-- Application/stored procedure must verify exactly 1 row was updated.
-- Otherwise, ROLLBACK and re-read timeline instead of continuing.

INSERT INTO plan_price_period (
    scope_id, monthly_fee, valid_period, decision_ref
)
VALUES (
    17, 140000,
    daterange(DATE '2026-12-01', NULL, '[)'),
    'PRICE-2026-DEC'
);

COMMIT;
~~~

If the INSERT fails due to a constraint, the transaction must **roll back** so it never leaves a shortened old row without the new row. Putting UPDATE and INSERT in one transaction does not automatically verify **affected row counts**, so the business protocol must check that before committing.

### 9.3. When Is a DEFERRABLE Constraint Needed?

Certain multi-interval restructurings can create **transient intra-transaction** overlaps even when the final state is valid—for instance, shifting two adjacent intervals without a simple update order. PostgreSQL allows declaring an **exclusion constraint** as **DEFERRABLE**, deferring enforcement until transaction end when specifically justified:

~~~sql
-- Illustrates the attribute on a newly created constraint:
CONSTRAINT ex_one_price_at_a_time
    EXCLUDE USING gist (
        scope_id WITH =,
        valid_period WITH &&
    )
    DEFERRABLE INITIALLY IMMEDIATE
~~~

With that attribute defined, a transaction can execute:

~~~sql
SET CONSTRAINTS ex_one_price_at_a_time DEFERRED;
~~~

However, **the final state at COMMIT must still be valid**. Deferring checks does not disable the constraint or replace concurrency control. It also affects when the database checks errors and when the application surfaces them; use it only when an update workflow genuinely requires it.

The full DDL in section 7 creates an immediate constraint; to practice with DEFERRABLE, declare it at constraint creation time or recreate it via an appropriate migration. The two snippets above do not imply that `SET CONSTRAINTS` turns a non-DEFERRABLE constraint into a DEFERRABLE one.

## 10. Hard Cases: Retroactivity, Late Data, and Recording History

### 10.1. Inserting a Segment Inside an Existing Version

Suppose 120,000 applies over **[Jul 1, Oct 1)**, and in September a decision approves 115,000 solely for **[Aug 1, Sep 1)**. Non-overlap rules reject inserting the new segment until the old record is adjusted. The design must split it:

~~~text
Before:
[Jul 1, Oct 1) → 120000

After:
[Jul 1, Aug 1) → 120000
[Aug 1, Sep 1) → 115000
[Sep 1, Oct 1) → 120000
~~~

The split must preserve unmodified portions under the same boundary convention without dropping any day. If the edit spans multiple existing records, recompute **all intersecting segments**, not merely the row with the closest start date.

### 10.2. Valid Time Alone Cannot Answer “What Did the System Know Back Then?”

A table storing only effective intervals represents **the effective schedule currently accepted by the system**. Once a historical interval is edited, post-edit data may no longer reveal what the system **previously stored** before the amendment.

Distinguish:

- **Valid time:** for which business dates a value is considered true.
- **Recorded/system time:** during which period the system recorded that version as current.
- **Event time:** when the decision or real-world action occurred.

If you must answer both **“what price was effective on August 15?”** and **“on August 16, what did the system believe August 15's price was?”**, add a recorded/system time axis or store events rich enough to reconstruct prior knowledge. A pair of versions can then overlap in **valid time** while remaining **disjoint in recorded time**.

**Crucial distinction:** in bitemporal modeling, non-overlap rules must span **both dimensions**. You must not forbid valid-time intersections across versions belonging to **different knowledge states**, as doing so would make retroactive corrections impossible.

Conceptual example of a bitemporal exclusion constraint:

~~~sql
EXCLUDE USING gist (
    entity_id WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

This states that for the same entity, two rows may not simultaneously overlap in **both valid time and known time**. A complete table design also requires rules for opening/closing known intervals, source attribution, and transactions.

### 10.3. Finalized Records Need Independent Evidence

Suppose an invoice issued on August 16 billed 120,000 VND, while a retroactive correction later changes the current price schedule for August 15 to 115,000 VND. The invoice must not automatically alter its total whenever queried against the latest price table.

Persist **the actual charged amount**, applicable period, and pricing decision/version reference captured when finalizing the invoice; issue separate compensating adjustments if needed. A foreign key to a mutable row does not by itself substitute for immutable proof of the billed amount.

## 11. Boundary Testing with Sample Data and Range Intersection

In PostgreSQL, the **&&** operator checks whether two ranges overlap:

~~~sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)')
    &&
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
    AS adjacent_overlap;
-- false
~~~

~~~sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-07-02', '[)')
    &&
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
    AS real_overlap;
-- true
~~~

**@>** checks point containment; **&&** checks interval intersection. When validating **non-overlap**, use the operator matching your data types and normalized bounds rather than comparing start dates alone.

### 11.1. Boundary Test Matrix

| Case | Interval A | Interval B / Point t | Expectation |
|---|---|---|---|
| Touching endpoints | [Jan 1, Jul 1) | [Jul 1, Oct 1) | No overlap |
| 1-day intersection | [Jan 1, Jul 2) | [Jul 1, Oct 1) | Overlap |
| B inside A | [Jan 1, Oct 1) | [Apr 1, Jun 1) | Overlap |
| B encloses A | [Apr 1, Jun 1) | [Jan 1, Oct 1) | Overlap |
| Exact duplicate | [Jan 1, Jul 1) | [Jan 1, Jul 1) | Overlap |
| Separated by 2 days | [Jan 1, Jul 1) | [Jul 3, Oct 1) | No overlap; gap exists |
| Unbounded upper limit | [Oct 1, infinity) | [Dec 1, Jan 1 next year) | Overlap |
| Left-bound check | [Jul 1, Oct 1) | t = Jul 1 | Contained |
| Right-bound check | [Jul 1, Oct 1) | t = Oct 1 | Not contained |
| Empty interval | [Jul 1, Jul 1) | Any point t | Must be rejected |

Add operational tests:

1. **Concurrent writes:** two transactions insert intersecting intervals for the same scope. Never allow two conflicting committed rows.
2. **Mid-transaction failure:** shorten an existing interval and force the new insert to fail; rollback must restore the old interval.
3. **Future-dated write:** version entered today starting next month; today's queries must not select it prematurely.
4. **Retroactive effective edit:** split leading and trailing segments properly while preserving finalized transaction data.
5. **Distinct scopes:** two rows with identical intervals in different scopes can coexist.
6. **Time zones:** timestamps representing the same instant with different offsets must compare equal in absolute time.
7. **Legacy data:** check for NULL ranges, empty ranges, reversed bounds, missing scope keys, and mixed sentinel conventions prior to migration.
8. **Retention:** when purging old history per policy, as-of queries must indicate the retained coverage horizon.

**Non-overlapping** is an automatically verifiable invariant. Yet “no overlap” is only meaningful when the business key scope and time conventions have been confirmed by domain stakeholders.

## 12. Migrating from Two Time Columns to a Range Type

Suppose an existing table has:

~~~text
plan_id | currency_code | valid_from | valid_to | price
~~~

Before converting to a single **valid_period daterange** column, clarify:

- **Is the current valid_to the last included day or the first excluded day?** If legacy data meant “through June 30,” shifting to half-open **July 1** is valid only if granularity is whole days and inclusive semantics were confirmed.
- **What does NULL mean?** “Infinity,” “unverified,” and “missing” often get mixed into the same column; classify them first.
- **Do existing intervals overlap?** Clean up conflicting data before enabling constraints.
- **Do gaps exist?** Gaps may represent intentional sales pauses; do not fill them automatically unless required.
- **Must pre-migration query answers be preserved?** When changing boundary semantics, prove historical period queries return the exact same answers.

If source **valid_to** is already an **exclusive bound** and NULL means unbounded, construct the range via:

~~~sql
SELECT daterange(valid_from, valid_to, '[)')
FROM legacy_price;
~~~

This is an **illustrative representation conversion** from a hypothetical **legacy_price** table; never run it blindly without verifying boundary conventions in the source data.

### 12.1. Detecting Conflicts Before Enabling Constraints

On a staged range table, run a self-join to find overlapping pairs:

~~~sql
SELECT
    a.scope_id,
    a.period_id AS first_period_id,
    b.period_id AS second_period_id,
    a.valid_period AS first_range,
    b.valid_period AS second_range
FROM plan_price_period a
JOIN plan_price_period b
  ON a.scope_id = b.scope_id
 AND a.period_id < b.period_id
 AND a.valid_period && b.valid_period;
~~~

Once the table has an exclusion constraint, this query finds zero violating pairs in valid data. It is especially valuable **on staging/migration tables before constraints are enabled** to uncover dirty source data prior to cutover.

Never automatically pick one of two overlapping records just because its **recorded_at** is newer. Determine which decision is authoritative, who holds retroactive edit rights, and which transactions already referenced each version.

## 13. Applying the Same Rules in Document, Graph, and Analytical Stores

Effective-interval principles stay constant across storage engines; only the enforcement mechanism changes.

| Model | Common Representation | Overlap Control Mechanism |
|---|---|---|
| **Relational** | Boundary pair or range type; version key, foreign keys | Exclusion constraint if supported, transactions, locking |
| **Document** | Version documents with validFrom and validTo, linked by entityId | Entity-level transactions/locks or conditional single-document writes |
| **Graph** | Versioned nodes/edges with interval properties | Validate relationships and competing active edges |
| **Analytical warehouse** | SCD Type 2 dimensions with effectiveFrom/effectiveTo | Pipeline testing, data quality checks, interval checks per dimension key |
| **Event store** | Decision events and effective-version projections | Timeline reconstruction rules, idempotency, replay conflict checks |

### 13.1. Document: Do Not Rely on First-Match Sorting

Example price document:

~~~json
{
  "planId": 7,
  "currencyCode": "VND",
  "monthlyFee": 120000,
  "validFrom": "2026-07-01",
  "validTo": "2026-10-01",
  "boundaryConvention": "[)"
}
~~~

If a query merely picks the document with the largest **validFrom** not exceeding date D, it still picks the wrong record when a **gap** exists or when that document expired before D. You must add **D < validTo** or **unbounded validTo**, and guard against conflicts under concurrent writes.

### 13.2. Graph: Relationships Also Have Effective Intervals

An employee may belong to team A from January 1 until before April 1, then team B from April 1 onward. Both **MEMBER_OF edges** must carry effective intervals. If the rule states “at most one primary team at a time,” prevent overlaps across **primary-assignment edges**, not merely across employee node property versions.

### 13.3. Analytical Warehouse: SCD Type 2 Needs Clear Bounds

An **SCD Type 2** customer dimension might look like:

~~~text
customer_sk | customer_id | segment | effective_from | effective_to
     101    |    501      | SILVER  | 2026-01-01     | 2026-07-01
     102    |    501      | GOLD    | 2026-07-01     | NULL
~~~

When joining facts at date D, apply the **[from, to)** convention consistently. If a pipeline produces two versions both active at D, the join duplicates fact rows and corrupts reports. A unique surrogate key does not prevent this; verify the non-overlap invariant per **customer_id** and effective interval.

## 14. Practice Exercise: Designing Meeting Room Reservations

A company is building a meeting room booking feature. Requirement:

> “Each room may have at most one meeting at any given time. The next meeting is allowed to start at the exact moment the previous meeting ends.”

Consider two reservations:

~~~text
R1: room 3, [2026-11-22 09:00+07, 10:00+07)
R2: room 3, [2026-11-22 10:00+07, 11:00+07)
~~~

R1 and R2 **do not overlap**. If someone attempts to add R3:

~~~text
R3: room 3, [2026-11-22 09:30+07, 10:30+07)
~~~

R3 **overlaps both R1 and R2**, so it must be rejected or require picking another room/slot.

A suitable PostgreSQL sketch:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_booking (
    booking_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id    bigint NOT NULL,
    time_slot  tstzrange NOT NULL,
    title      text NOT NULL,

    CONSTRAINT ck_room_booking_time
        CHECK (
            NOT isempty(time_slot)
            AND NOT lower_inf(time_slot)
            AND NOT upper_inf(time_slot)
            AND lower_inc(time_slot)
            AND NOT upper_inc(time_slot)
        ),

    CONSTRAINT ex_room_booking_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            time_slot WITH &&
        )
);
~~~

Here, **unbounded booking slots are forbidden**, unlike the pricing table. This reflects the business requirement: every room reservation must have both a start instant and an end instant. **CHECK** and **EXCLUDE** work together to enforce the rules in the database.

Test two cases:

~~~sql
INSERT INTO room_booking (room_id, time_slot, title)
VALUES
(
    3,
    tstzrange(
        TIMESTAMPTZ '2026-11-22 09:00+07',
        TIMESTAMPTZ '2026-11-22 10:00+07',
        '[)'
    ),
    'Team A meeting'
),
(
    3,
    tstzrange(
        TIMESTAMPTZ '2026-11-22 10:00+07',
        TIMESTAMPTZ '2026-11-22 11:00+07',
        '[)'
    ),
    'Team B meeting'
);
-- Both valid because they only touch at 10:00.
~~~

~~~sql
INSERT INTO room_booking (room_id, time_slot, title)
VALUES (
    3,
    tstzrange(
        TIMESTAMPTZ '2026-11-22 09:30+07',
        TIMESTAMPTZ '2026-11-22 10:30+07',
        '[)'
    ),
    'Team C meeting'
);
-- Rejected because it overlaps room 3's schedule.
~~~

To complete the exercise, answer:

1. If room 3 is booked **[10:00, 11:00)** while **[09:00, 10:00)** just ended, why is there no conflict?
2. If room 4 has a booking **[09:30, 10:30)**, does it conflict with room 3? What does the business key govern?
3. If the company requires **15 minutes of room cleaning between meetings**, is simple non-overlap sufficient? Model the buffer interval or effective occupancy slot.
4. If a meeting is cancelled, should the row be deleted or kept with a cancelled status as evidence? Does a “cancelled” version still reserve the room? Constraints must reflect only statuses that actively hold a reservation.
5. If two people book simultaneously, how should the transaction protocol and exclusion constraint errors be handled?

Question 3 shows that **non-overlap guarantees only that no two intervals contain the same instant**—it does not automatically enforce minimum turnaround buffers. Question 4 shows that effective validity may depend on additional attributes, such as active vs. cancelled booking status. The schema must scope constraints precisely to active rows.

## 15. Design Sign-Off Checklist and Core Principles

Before putting an effective-interval version table into production, verify:

- **Semantics:** is valid time a calendar date or an absolute instant; where is the business time zone defined?
- **Bounds:** is **[from, to)** or another convention standardized across APIs, reports, and migrations?
- **Precision:** are “23:59:59” hacks and fake sentinel timestamps avoided under microsecond precision or time zone shifts?
- **Valid intervals:** are empty ranges, reversed bounds, and unclassified unknown values rejected?
- **Business key:** which versions compete, and which dimensions are allowed to coexist simultaneously?
- **Overlap:** does the database enforce the invariant under concurrent writes rather than relying solely on application SELECT checks?
- **Adjacency/gaps:** does the business require “at most one” or “exactly one” value; to what extent are gaps valid?
- **Transactions:** are open-interval updates, mid-history splits, rollbacks, and retries handled atomically?
- **History:** do we need to know what the system believed before retroactive edits; are decision sources and finalized transaction evidence preserved?
- **Testing:** have left/right bounds, partial intersections, containment, unbounded limits, separate scopes, time zones, and concurrent writes been tested?
- **Evolution:** can the chosen range types, indexes, constraints, and retention policies sustain real queries at projected scale?

**Rule to remember:** an interval **[from, to)** includes its left bound and excludes its right bound; two intervals are **adjacent** without overlapping when the first's end equals the next's start. **Non-overlap** rules are only meaningful when tied to the **right business key** and enforced safely in the database under concurrency. When requirements go beyond a single effective timeline, add explicit recording history so the model can still explain past decisions.
