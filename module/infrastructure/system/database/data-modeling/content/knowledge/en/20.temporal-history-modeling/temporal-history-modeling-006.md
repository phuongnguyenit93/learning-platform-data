# Bitemporal Data Modeling for Handling Retroactive Adjustments

## 1. The Problem: A New Decision Changes How We Understand the Past

In **DATABASE_DATA_MODELING**, translating business requirements into a data model requires clarifying not only **entities, relationships, keys, and constraints**, but also **two temporal questions**: when is a value effective in the business, and since when did the system know or accept that value?

Consider service contract number **9001** with a monthly subscription unit rate:

- Initially, the system knows the rate is **100,000 VND/month**, effective from **2026-01-01**.
- On **2026-03-10**, the system receives a decision stating a new rate of **120,000 VND/month** effective retroactively from **2026-02-01**.
- On **2026-03-20**, business operations issues a correction: the March 10 decision had **the wrong effective date**. The 120,000 rate should actually apply starting **2026-02-15**, meaning from Feb 1 until before Feb 15 it must remain 100,000.

On March 15, the system believed the rate for **Feb 10** was **120,000**. After the March 20 adjustment, the effective rate for **Feb 10** per latest information is **100,000**. Both results matter for different questions:

> “Which price is considered right for Feb 10 according to currently confirmed information?”

> “When issuing an invoice on Mar 15, which price had the system recorded for Feb 10 at that time?”

If a single current-price row is overwritten, the second question has no answer. If only an update log is recorded without storing effective dates, the first question can return the wrong answer. To preserve **the history of interpretations of the past themselves**, we need **bitemporal data modeling**.

This lesson belongs to the **Time and History** chapter and focuses on how to represent, update, and verify data when a decision arrives late, has its effective date corrected, or is retroactively superseded. It applies modeling techniques in relational databases while showing how to translate the ideas to document, graph, and analytical stores.

### Learning Objectives

After this lesson, learners can:

1. Distinguish **business effective time** from **system recording time**, and explain why retroactive adjustments can change the answer for the same business date.
2. Design a bitemporal table with two time intervals, business keys, and non-overlap rules enforced along **both dimensions**.
3. Execute a retroactive adjustment by **closing the old knowledge period, re-partitioning effective intervals, and opening a new knowledge period**.
4. Write queries parameterized by two timestamps, verify pre/post-edit results, and separate them from finalized transactional records.
5. Identify limitations around concurrency, commit timing, late-arriving events, incomplete history, retention, and operational cost.

## 2. Two Time Axes with Different Meanings

### 2.1. Valid Time: When Is Information True in the Business?

**Valid time** is the time during which a value is regarded by the business as effective. For example, the 120,000 VND rate only takes effect on 2026-02-15, even though the decision was recorded by the system in March.

For date-scoped values, we commonly use intervals:

~~~text
valid_period = [valid_from, valid_to)
~~~

The interval **[Feb 15, unbounded)** begins on Feb 15 and has no determined end date yet. The interval **[Jan 1, Feb 15)** covers Jan 1 through the end of Feb 14, excluding Feb 15.

**Valid time is not necessarily when a staff member clicked Save**, nor necessarily when a customer signed a decision. A decision might be signed on March 5 yet specify an effective date of Feb 1.

### 2.2. Known/System Time: When Did the System Accept the Information?

**Known time**, also called **recorded/system time** when appropriately defined, represents the period during which the system treated a version as accepted knowledge. Use the interval:

~~~text
known_period = [known_from, known_to)
~~~

If a version is recorded on March 10 and superseded on March 20:

~~~text
known_period = [2026-03-10, 2026-03-20)
~~~

That version **still exists in history**, but is no longer regarded by the system as the latest interpretation from March 20 onward. This enables querying **“what did the system believe on March 15?”**

You must define precisely what **“the system knows”** means. In an application-managed bitemporal solution, it may be when information was accepted into the authoritative data store. That is **not automatically the database transaction commit time**. Proving exact committed state at every absolute instant requires DBMS system-versioning or commit-ordering guarantees rather than a single timestamp column captured prior to COMMIT.

### 2.3. Do Not Confuse With Event Time or Pipeline Time

| Timestamp | Question Resolved | Example |
|---|---|---|
| **Valid time** | Since when is the price effective in the business? | Feb 15 |
| **Decision/occurred time** | When did the real-world decision or action happen? | Decision signed Mar 9 |
| **Received time** | When did the system receive the document/message? | API received Mar 10 |
| **Known time** | When did the system accept this version of truth? | Information recorded Mar 10 |
| **Processing time** | When did a worker process the data? | Worker reprocessed Mar 11 |
| **Commit time** | When did the transaction become durable/visible per DBMS rules? | Transaction commit point |

These timestamps may sit close together in simple apps yet diverge when events arrive late, are replayed, or are retroactively amended. Having six timestamp columns does not guarantee correct modeling; you must know which question each column answers and which source supplies it.

## 3. Tracking One Contract Across Three Changes of Knowledge

We choose **business calendar dates** for valid time and **UTC instants** for known time. Every interval uses the **closed-start, open-end** convention: `[from, to)`.

### 3.1. Initial Recording: Jan 1

On Jan 1 at 08:00 UTC, the system learns contract 9001 has a price of 100,000 starting Jan 1:

~~~text
Version V1
Price:        100,000
Valid:        [Jan 1, +∞)
Known:        [Jan 1 08:00 UTC, +∞)
~~~

If queried in February under the system's knowledge then, every day from Jan 1 onward has a price of 100,000.

### 3.2. First Change: Mar 10, Retroactively Effective Feb 1

On Mar 10 at 09:00 UTC, the system receives a decision setting 120,000 effective Feb 1. We must preserve what the system previously believed before Mar 10 while creating the new effective timeline:

~~~text
V1 (old knowledge):
  100,000, valid [Jan 1, +∞)
           known [Jan 1 08:00, Mar 10 09:00)

V2 (new knowledge):
  100,000, valid [Jan 1, Feb 1)
           known [Mar 10 09:00, +∞)

V3 (new knowledge):
  120,000, valid [Feb 1, +∞)
           known [Mar 10 09:00, +∞)
~~~

**Never delete V1**: it is proof that before Mar 10 the system believed 100,000 applied continuously.

### 3.3. Second Correction: Mar 20, True Effective Date Is Feb 15

On Mar 20 at 09:00 UTC, the business confirms that the Feb 1 effective date in the previous decision was entered by mistake. The 120,000 price must begin on Feb 15.

We close **known_period** on V2 and V3 at Mar 20, then insert two new effective segments:

~~~text
V2 (knowledge from Mar 10 until before Mar 20):
  100,000, valid [Jan 1, Feb 1)
           known [Mar 10 09:00, Mar 20 09:00)

V3 (knowledge from Mar 10 until before Mar 20):
  120,000, valid [Feb 1, +∞)
           known [Mar 10 09:00, Mar 20 09:00)

V4 (knowledge from Mar 20):
  100,000, valid [Jan 1, Feb 15)
           known [Mar 20 09:00, +∞)

V5 (knowledge from Mar 20):
  120,000, valid [Feb 15, +∞)
           known [Mar 20 09:00, +∞)
~~~

All versions V1 through V5 remain stored, because each proves **an interpretation held effective during a specific system recording window**.

### 3.4. State Table After Two Adjustments

| Version | Amount | Business Effective Interval | System-Accepted Knowledge Interval |
|---|---:|---|---|
| V1 | 100,000 | [Jan 1, +∞) | [Jan 1 08:00, Mar 10 09:00) |
| V2 | 100,000 | [Jan 1, Feb 1) | [Mar 10 09:00, Mar 20 09:00) |
| V3 | 120,000 | [Feb 1, +∞) | [Mar 10 09:00, Mar 20 09:00) |
| V4 | 100,000 | [Jan 1, Feb 15) | [Mar 20 09:00, +∞) |
| V5 | 120,000 | [Feb 15, +∞) | [Mar 20 09:00, +∞) |

All **known time** timestamps here are in 2026 in UTC. In the compact table, **valid time** dates are also in 2026.

The conceptual diagram below depicts the two knowledge shifts:

~~~mermaid
flowchart TD
    A["Jan 1: Known price 100,000<br/>for full period from Jan 1"] --> B["Mar 10: Decision 120,000<br/>effective from Feb 1"]
    B --> C["Close V1<br/>Create V2 + V3"]
    C --> D["Mar 20: Correction<br/>true date is Feb 15"]
    D --> E["Close V2 + V3<br/>Create V4 + V5"]
~~~

This is a chain of **versions of system knowledge**. The business price for a given day can change when you shift the knowledge evaluation instant, even though the queried business date itself has not changed.

## 4. Bitemporal Queries Essentially Take Two Parameters

Let:

- **B** (*business time*): the business date for which to determine the effective price.
- **K** (*knowledge time*): the point in time from which to inspect **what information the system had accepted**.

A row is selected when both hold simultaneously:

~~~text
valid_from <= B < valid_to
known_from <= K < known_to
~~~

With an unbounded upper limit, any instant at or after the lower bound falls inside the interval.

### 4.1. Same Business Date, Results Change with K

| B: Date to Price | K: Known by System On | Expected Price | Version |
|---|---|---:|---|
| Feb 10 | Mar 1 at 12:00 | 100,000 | V1 |
| Feb 10 | Mar 15 at 12:00 | 120,000 | V3 |
| Feb 10 | Mar 21 at 12:00 | 100,000 | V4 |
| Feb 20 | Mar 15 at 12:00 | 120,000 | V3 |
| Feb 20 | Mar 21 at 12:00 | 120,000 | V5 |
| Feb 15 | Mar 21 at 12:00 | 120,000 | V5 |
| Feb 14 | Mar 21 at 12:00 | 100,000 | V4 |

Specifically, the rows **B = Feb 10, K = Mar 15** and **B = Feb 10, K = Mar 21** differ. That is the exact reason bitemporal modeling exists for handling retroactive adjustments.

If **K** predates the system's first recording instant, the query returns no rows. That means **no recorded information exists in retained history at K**, not automatically that the contract did not exist.

### 4.2. Why Using Only updated_at Is Wrong

A row holding 100,000 for February with **updated_at = Mar 20** cannot tell you that on March 15 the system believed February's price was 120,000. Even with an audit log saying “March 20 edited price,” you also need to know **which valid-time slice was modified** and **which slices the system previously accepted**.

A bitemporal model directly expresses both time predicates, sparing queries from ambiguous inference over scattered UPDATE logs.

## 5. Designing Keys and Constraints for Two Time Dimensions

A bitemporal record can be viewed as **an assertion by the system about a value over business dates**.

For service contracts, choose:

- **Parent entity:** contract, identified by **contract_id**.
- **Rate type:** **rate_kind**, e.g., BASE or ADDON. Each kind has its own rate timeline.
- **Version value:** **monthly_amount**.
- **Two intervals:** **valid_period** by business date and **known_period** by timestamp.
- **Evidence:** **decision_ref**, **correction_reason**, and reference to the amended decision.
- **Technical key:** **version_id**, identifying the row only, not effective order.

Core invariant:

> For any **(contract_id, rate_kind)** pair and any **(B, K)** time pair, **at most one** system-accepted rate is effective.

To enforce this, **two versions conflict only if they share the same business key and overlap simultaneously in both valid time and known time**.

### 5.1. Why Not Forbid All Overlapping Valid Intervals?

V1 and V3 both have valid periods containing Feb 10. Yet V1 was accepted only before Mar 10, whereas V3 began being accepted on Mar 10. They **are never true at the same (B, K)**.

If you add a constraint forbidding valid-time overlap across all rows regardless of known period, the database rejects storing V3—making retroactive adjustment history impossible.

Conversely, without checking known time, two rows with identical valid and known periods could both be returned, yielding two rates for one (B, K).

### 5.2. Two-Dimensional Intersection Condition

For two rows A and B sharing the same business key:

~~~text
conflict(A, B) =
    overlaps(A.valid_period, B.valid_period)
    AND overlaps(A.known_period, B.known_period)
~~~

This is a **two-dimensional** constraint, unlike a system managing only the latest effective schedule. It must be enforced safely under concurrent writes rather than relying on an unlocked pre-INSERT check query.

## 6. Illustrative PostgreSQL Schema

PostgreSQL provides **daterange** for date intervals and **tstzrange** for time-zone-aware timestamp intervals. The **@>** operator tests whether a range contains a point; **&&** tests whether two ranges overlap.

Below is an **application-managed bitemporal** schema, not PostgreSQL automatic system-versioning:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE service_contract (
    contract_id   bigint PRIMARY KEY,
    contract_code text NOT NULL UNIQUE
);

CREATE TABLE contract_rate_bitemporal (
    version_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contract_id       bigint NOT NULL
                      REFERENCES service_contract(contract_id),
    rate_kind         text NOT NULL,
    monthly_amount    numeric(14, 2) NOT NULL
                      CHECK (monthly_amount >= 0),
    valid_period      daterange NOT NULL,
    known_period      tstzrange NOT NULL,
    decision_ref      text NOT NULL,
    correction_of     text,
    correction_reason text,

    CONSTRAINT ck_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),
    CONSTRAINT ck_known_period
        CHECK (
            NOT isempty(known_period)
            AND NOT lower_inf(known_period)
            AND lower_inc(known_period)
            AND NOT upper_inc(known_period)
        ),

    CONSTRAINT ex_one_rate_for_each_business_and_known_time
        EXCLUDE USING gist (
            contract_id WITH =,
            rate_kind WITH =,
            valid_period WITH &&,
            known_period WITH &&
        )
);
~~~

Meaning of the constraints:

| Component | Responsibility |
|---|---|
| **PRIMARY KEY(version_id)** | Distinguishes each stored version |
| **FOREIGN KEY(contract_id)** | Version belongs to an existing contract |
| **NOT NULL** | Prevents keys and intervals from becoming NULL and bypassing checks |
| **CHECK NOT isempty** | Forbids empty intervals |
| **CHECK NOT lower_inf** | Forces every version to have an explicit start point |
| **CHECK lower_inc AND NOT upper_inc** | Standardizes half-open **[from, to)** bounds |
| **EXCLUDE USING gist** | Forbids two rows with the same contract_id and rate_kind from overlapping **on both axes** |

**btree_gist** allows combining equality comparisons on scalar keys with range overlap operators inside GiST. The **EXCLUDE** structure protects **uniqueness at (B, K)**, yet does not automatically guarantee **every day has a price**. If business rules require exactly one rate on every active day, also check for **gaps** across the latest known slice and the contract's active dates.

An attribute like **currency_code** is omitted from the sample table on the assumption that currency is fixed per contract or all examples use VND. If one contract holds multiple currencies concurrently, add currency to the **business key and constraint**—otherwise two independent rates would be wrongly blocked.

### 6.1. Auto-Incrementing Keys Are Not a Time Axis

**version_id = 5** only means a different row from **version_id = 4**. It does not mean V5 takes effect later in valid time than all other rows. A retroactive decision effective in February can be inserted in March after a future-dated decision effective in July.

Therefore, queries asking “effective rate at B given knowledge K” must filter **both ranges**, never pick **MAX(version_id)**.

### 6.2. Using Half-Open Intervals to Keep Transition Boundaries Clean

~~~text
Price 100,000: valid [Jan 1, Feb 15)
Price 120,000: valid [Feb 15, +∞)
~~~

**Feb 15** belongs exclusively to 120,000. If both intervals were closed on both ends, the transition day would match both prices; using “end of Feb 14 23:59:59” risks creating gaps when timestamp granularity supports sub-second units.

With **daterange** by day, Feb 15 is **the first included day of the next version**. With **tstzrange** by instant, the right bound is excluded by the exact same logic.

## 7. Initial Recording: Creating Version V1

Run the sample data in a test database:

~~~sql
INSERT INTO service_contract (contract_id, contract_code)
VALUES (9001, 'CONTRACT-9001');

INSERT INTO contract_rate_bitemporal (
    contract_id,
    rate_kind,
    monthly_amount,
    valid_period,
    known_period,
    decision_ref
)
VALUES (
    9001,
    'BASE',
    100000,
    daterange(DATE '2026-01-01', NULL, '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-01-01 08:00:00+00',
        NULL, '[)'
    ),
    'RATE-INITIAL'
);
~~~

The recording timestamps in the example are **fixed literals for learning and verification**. Production applications must never assign arbitrary known timestamps; adopt a consistent time-acquisition policy and ensure the decision source is verified.

Before adjustment, querying B = Feb 10, K = Mar 1 returns 100,000.

## 8. First Retroactive Adjustment: Mar 10

Decision **RATE-MAR10** sets 120,000 effective Feb 1. The system must close the initial knowledge period and create two valid-time segments accepted as of Mar 10.

General workflow:

1. Lock the contract scope to prevent two competing rate edits.
2. Read currently **known-open** versions and determine the currently accepted effective timeline.
3. Verify the knowledge cutover timestamp **K1**, decision source, and affected intervals.
4. Close `known_period` on superseded records at K1.
5. Insert the new valid-time segments, all starting `known_period` at K1.
6. Verify results and commit atomically.

For data containing only V1, illustrative SQL operations:

~~~sql
BEGIN;

SELECT contract_id
FROM service_contract
WHERE contract_id = 9001
FOR UPDATE;

UPDATE contract_rate_bitemporal
SET known_period = tstzrange(
    lower(known_period),
    TIMESTAMPTZ '2026-03-10 09:00:00+00',
    '[)'
)
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND upper_inf(known_period)
RETURNING version_id;

-- Exactly 1 row (V1) must be closed.
-- Otherwise, application/stored procedure must ROLLBACK,
-- re-evaluate the timeline, and handle conflict.

INSERT INTO contract_rate_bitemporal (
    contract_id, rate_kind, monthly_amount,
    valid_period, known_period,
    decision_ref, correction_reason
)
VALUES
(
    9001, 'BASE', 100000,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-10 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR10', 'Keep old price before new effective date'
),
(
    9001, 'BASE', 120000,
    daterange(DATE '2026-02-01', NULL, '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-10 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR10', 'Retroactive price change'
);

COMMIT;
~~~

**Never commit if UPDATE affects the wrong number of rows.** The SQL illustrates the operation sequence; production code must verify **RETURNING** counts, approval authority, idempotency, and all invariants **before allowing COMMIT**.

Updating V1's **known_period** closes the old knowledge window; it does not delete V1. V1's valid bounds remain intact as proof of what the system previously believed. If audit mandates require every stored record to be **physically append-only**, add an immutable event/audit log or dedicated DBMS system-versioning, since updating `known_period` is still an UPDATE.

## 9. Second Retroactive Correction: Mar 20

On Mar 20, the business confirms the new effective date was **not Feb 1 but Feb 15**. The new cutover is **K2 = 2026-03-20 09:00 UTC**.

The system currently holds two known-open versions, V2 and V3. They must be closed at K2 and replaced with V4 and V5. Even though the 100,000 rate before Feb 1 did not change, V2 can still be closed and replaced by V4 to form a **complete snapshot of the effective timeline** for the new knowledge period.

~~~sql
BEGIN;

SELECT contract_id
FROM service_contract
WHERE contract_id = 9001
FOR UPDATE;

UPDATE contract_rate_bitemporal
SET known_period = tstzrange(
    lower(known_period),
    TIMESTAMPTZ '2026-03-20 09:00:00+00',
    '[)'
)
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND upper_inf(known_period)
RETURNING version_id;

-- Exactly 2 rows (V2, V3) must be closed.
-- Otherwise, ROLLBACK and re-read currently open versions.

INSERT INTO contract_rate_bitemporal (
    contract_id, rate_kind, monthly_amount,
    valid_period, known_period,
    decision_ref, correction_of, correction_reason
)
VALUES
(
    9001, 'BASE', 100000,
    daterange(DATE '2026-01-01', DATE '2026-02-15', '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-20 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR20', 'RATE-MAR10',
    'Corrected start date of new price'
),
(
    9001, 'BASE', 120000,
    daterange(DATE '2026-02-15', NULL, '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-20 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR20', 'RATE-MAR10',
    'New price effective only from Feb 15'
);

COMMIT;
~~~

**Why close V2 even though the pre-February rate stayed the same?** Under this illustrative strategy, each adjustment writes **a full set of valid segments for the entire rate schedule**, making “timeline as of K” queries simple to inspect and reconcile. An alternative strategy closes/opens **only affected segments** while leaving unchanged segments open-known; that requires careful calculation so no gap or overlap appears in any K slice.

Both strategies can be valid. What matters is consistent conventions, retaining old knowledge, querying accurately at any K within retention, and executing atomically.

### 9.1. Do Not Hardcode Closed Row Counts in a Generic UPDATE

The example had only two known-open versions before Mar 20. In reality, a contract may have multiple rate periods, future-scheduled decisions, or earlier valid corrections. An UPDATE closing all known-open rows while inserting only two replacement rows would **wipe out the other periods**.

Therefore, a general algorithm must **read the actual timeline**, recompute either the complete segment set or only affected segments, and validate coverage and integrity before writing.

### 9.2. Corrections Must Identify Source and Reason

**decision_ref = RATE-MAR20** states which decision confirmed the new timeline. **correction_of = RATE-MAR10** states which prior decision is being amended. **correction_reason** explains the effective-date error.

For granular accountability, extract a **rate_decision** table holding approver, supporting document, receipt time, approval time, and processing status. The bitemporal table links to it via foreign key rather than stuffing full document payloads and personal data into every version row when a reference suffices.

## 10. “As-Of” Queries Across Both Business Date and Knowledge Time

Once V1–V5 are stored, query in PostgreSQL:

~~~sql
SELECT
    version_id,
    monthly_amount,
    valid_period,
    known_period,
    decision_ref
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND valid_period @> DATE '2026-02-10'
  AND known_period @>
      TIMESTAMPTZ '2026-03-15 12:00:00+00';
~~~

**Expected result: 120,000 (V3)**, because on Mar 15 the system accepted 120,000 for Feb 10.

Keep business date Feb 10 and change the system knowledge time:

~~~sql
SELECT monthly_amount, decision_ref
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND valid_period @> DATE '2026-02-10'
  AND known_period @>
      TIMESTAMPTZ '2026-03-21 12:00:00+00';
~~~

**Expected result: 100,000 (V4)**. The two queries differ **only in K**, not **B**.

### 10.1. Querying the Full Timeline at a Knowledge Instant

To view **the entire price schedule the system had accepted on Mar 15**, leave B unconstrained and filter only K:

~~~sql
SELECT
    monthly_amount,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to,
    decision_ref
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND known_period @>
      TIMESTAMPTZ '2026-03-15 12:00:00+00'
ORDER BY lower(valid_period), version_id;
~~~

Returns V2 and V3. Changing K to Mar 21 returns V4 and V5.

### 10.2. Querying the Currently Known Effective Schedule

~~~sql
SELECT
    monthly_amount,
    valid_period
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND upper_inf(known_period)
ORDER BY lower(valid_period);
~~~

**upper_inf(known_period)** selects records whose knowledge interval is **still open**. This works cleanly when the application consistently maintains a known-open version set representing latest knowledge.

To find **today's** price under a specific market calendar, combine this with filtering **valid_period contains current business date**. A known-open row may also take effect **in the future**.

### 10.3. No Rows Does Not Mean Price Equals Zero

If B precedes the contract's recorded start date, or K precedes the system's first recorded knowledge, the query returns zero rows. Distinguish **“no data in retained range,”** **“not yet approved,”** **“contract not yet effective,”** and **“not yet recorded by system.”** Never silently convert an empty result into price 0, the first price, or the current price.

## 11. Retroactive Adjustment Algorithm for Multi-Version Timelines

Example V1–V5 was simple because there was only one rate type and few segments. In production, a single retroactive edit can intersect many existing versions:

~~~text
According to current knowledge:
[Jan 1, Mar 1)  → A
[Mar 1, Jun 1)  → B
[Jun 1, Sep 1)  → C
[Sep 1, +∞)     → D

Correction:
[Feb 15, Jul 15) must apply price X

Valid result may be:
[Jan 1, Feb 15)  → A
[Feb 15, Jul 15) → X
[Jul 15, Sep 1)  → C
[Sep 1, +∞)      → D
~~~

You cannot simply edit row B's price, because the correction cuts across **the end of A, all of B, and the start of C**.

### 11.1. Steps to Compute the New Timeline

1. **Identify the business key** — e.g., contract 9001, rate kind BASE.
2. **Lock the update scope** — to process competing decisions sequentially.
3. **Read the current known-open slice** — the list of accepted valid-time versions.
4. **Normalize the retroactive decision** — validate start/end dates, currency, rate amount, approval source, and interval rules.
5. **Compute cut points** — collect all start/end bounds of old and new intervals; sort them to form disjoint elementary sub-intervals.
6. **Assign values per sub-interval** — follow decision precedence rules; preserve untouched intervals.
7. **Validate invariants before writing** — no two competing rates at the same B; gaps either allowed or flagged.
8. **Close/open known-periods using one shared K for the decision** — produce the new bitemporal version set.
9. **Commit atomically** — if any step fails, roll back everything.
10. **Publish events with retry and reconciliation support** — when downstream read projections or warehouses must stay updated.

If domain rules forbid **overriding a higher-authority decision**, the algorithm must reject the edit or route it for approval review. Never treat a later timestamp as automatically more authoritative.

### 11.2. Invariants to Verify Before and After Writing

| Invariant | Verification Method |
|---|---|
| Every version has non-empty valid/known periods | CHECK constraints, input validation |
| No two rates accepted simultaneously at any (B, K) | Exclusion constraint across both ranges |
| If continuous pricing is required, no gaps exist | Timeline checks at each relevant K slice |
| Every edit has source and reason | Foreign key references / approval workflow |
| Segments outside the correction scope remain intact | Pre/post timeline diff outside the edited range |
| Replayed events do not create spurious amendments | Decision idempotency key |
| Previously known states remain queryable | As-of tests with K before and after correction |
| Finalized transactions preserve original values | Pre/post snapshot comparison on finalized records |

## 12. Concurrency, Recording Order, and Atomicity

Two analysts can simultaneously edit the same rate schedule:

- A approves a rate change effective Mar 1.
- B amends an earlier decision effective Feb 15.

If both read the same timeline, compute segments independently, and write, one person's change may be lost or overlaps may occur. Having two time axes in a bitemporal model **does not by itself resolve transaction races**.

### 12.1. Locking by Business Entity

In PostgreSQL, lock the **service_contract** row when editing a contract's rates:

~~~sql
BEGIN;

SELECT contract_id
FROM service_contract
WHERE contract_id = 9001
FOR UPDATE;

-- After acquiring lock:
-- 1. Read known-open versions.
-- 2. Compute new timeline.
-- 3. Close old known-period and create new known-period.
-- 4. Verify row counts, constraints, decision source.
-- 5. COMMIT or ROLLBACK.
~~~

This serializes edits touching the same contract, provided all write paths obey the protocol. If a contract has multiple independent rate kinds, introduce a **rate_scope** row per `contract_id + rate_kind` for finer-grained locking.

Alongside locking, use an **optimistic revision** when a command was approved against a previously viewed timeline. If the revision changed, require re-confirmation instead of silently merging potentially conflicting decisions.

### 12.2. One Cutover Timestamp for the Whole Adjustment

When closing old versions and inserting new ones for a single decision, use **one unified K timestamp** across all affected rows. Generating separate timestamps per INSERT/UPDATE can leave a micro-gap between known periods or cause unintended overlaps.

K must exceed the start timestamp of the versions being superseded under your recording policy. On retries, identify which decision is being retried and whether it may generate **a new recording event**.

An application-level recording timestamp **does not by itself prove exact commit time**. If microsecond-level queries must reflect exact transaction visibility order, evaluate DBMS temporal features, transaction sequences, commit metadata, and clock reliability.

### 12.3. Propagating Data to Other Services

If the bitemporal rate table lives in database A while read projections, message brokers, or analytical warehouses live elsewhere, they do not share a single transaction.

Use a **transactional outbox**: persist both the bitemporal state and outbound event in the same transaction at A, then have a worker publish with retries. Consumers must be idempotent because redelivery can produce duplicates. Also monitor projection lag and run reconciliation on failures.

An event like “RATE-MAR20 accepted” should carry **decision ID, revision, affected intervals, and authoritative source DB**, not merely a new dollar amount, if consumers need to reconstruct or audit retroactive impacts.

## 13. Preserving Evidence When History Affecting Finalized Transactions Changes

Suppose on **Mar 15** the company issues an invoice for usage on **Feb 10**, based on the knowledge then that the rate was **120,000**. On Mar 20, data is corrected back to 100,000 for Feb 10.

Three truths must coexist simultaneously:

1. For Feb 10, per **currently accepted** information, the effective unit rate is **100,000**.
2. On Mar 15, the system **knew** the unit rate for Feb 10 as **120,000**.
3. The invoice issued on Mar 15 **actually billed** 120,000; finalized amounts must never mutate when re-joining bitemporal data.

Therefore, invoices or invoice lines should store **the actual applied price/amount**, currency, service period, finalization timestamp, and pricing reference:

~~~text
invoice_line
  invoice_line_id
  invoice_id
  contract_id
  service_date
  charged_unit_price
  charged_amount
  currency_code
  finalized_at
  rate_decision_ref
  rate_version_id (if helpful)
~~~

**rate_version_id** can point to V3, which the system had accepted when calculating the invoice. Because V3 remains in the bitemporal table with a closed `known_period`, historical justification stays traceable. Yet the invoice line should also store the finalized monetary amounts to avoid depending on historical re-interpretation after schema migrations.

If a retroactive adjustment creates a discrepancy, the business needs **credit/debit memos, refunds, or compensating ledger entries** per financial rules. Bitemporal modeling answers “what is deemed true and what was known,” without automatically deciding cash movements, tax effects, or accounting periods.

## 14. Erroneous Entries, Decision Changes, and Late-Arriving Information

Not every retroactive event belongs to the same category:

| Situation | Semantics | How the Model Should Reflect It |
|---|---|---|
| **Data-entry mistake** | True effective date was known from the start, but typed wrong | Keep the erroneous knowledge slice; record correction decision and recording date |
| **New retroactive decision** | Business approves past application only today | Store new decision, backdated valid time, known time starting at acceptance |
| **Late-arriving message** | Event already happened, received by system later | Separate occurred/valid time from received/known time |
| **Decision revocation** | Prior decision is withdrawn | Close old interpretation, open new interpretation; store revocation basis |
| **Unresolved dispute** | Two sources assert conflicting values | Store dispute/unapproved state; do not treat both as accepted truth |
| **Report re-issuance timing** | Report already closed while source data changes | Report versions/snapshots and formal re-issuance workflows if needed |

Bitemporal storage records **assertions accepted by the system**; it is not an oracle of objective reality. When input sources conflict, domain teams must define approval rules, precedence, dispute handling, and stakeholder notifications.

### 14.1. Never Fill Missing Dates with Fabricated Dates

If a decision only says “effective mid-February” without an exact date, never invent **Feb 15** as verified fact. Store a pending status, timestamp precision, confirmation source, or uncertainty interval and await approval before promoting it to the official timeline.

**A cleanly formatted interval** does not mean **the source of the interval is trustworthy**. Separate structural validation from business-evidence verification.

## 15. Indexing, Large Queries, and History Retention

Bitemporal row counts can grow faster than single-axis history: each amendment may close and recreate multiple valid-time segments. The more retroactive edits occur, the more known-time layers accumulate.

Common query patterns:

| Need | Predicates | Design Hint |
|---|---|---|
| Price at (B, K) | Business key + valid contains B + known contains K | GiST supporting ranges; measure real selectivity |
| Timeline per current knowledge | Business key + open `known_period` | Partial index or projection |
| Timeline at historical K | Business key + known contains K | Appropriate range/key indexes |
| All decisions recorded on a day | `known_from` within day, `decision_ref` | Indexes on decision source and recording time |
| Count of contracts retroactively amended | Filter by decision and impacted intervals | Decision table, event stream, and analytical warehouse |
| High-volume current-price API | B = current business date; K = current knowledge | Synchronized and reconciled projection |

Never build indexes on intuition alone. Use **EXPLAIN (ANALYZE, BUFFERS)** on realistic data sizes to verify query plans. The GiST index backing the exclusion constraint enforces the invariant and can assist some queries, yet may not be optimal for every date/key reporting pattern.

An optional workload-driven index:

~~~sql
CREATE INDEX ix_contract_rate_current_known
ON contract_rate_bitemporal
USING gist (contract_id, rate_kind, valid_period)
WHERE upper_inf(known_period);
~~~

This targets **open known-period** records when querying currently accepted price schedules. It does not enforce the bitemporal invariant on its own; keep the exclusion constraint in place.

### 15.1. Partitioning and Global Constraints

If you partition the table by `known_from`, two rows for the same contract can land in different partitions while still violating **overlapping valid and known periods**. Never assume per-partition constraints automatically block cross-partition conflicts across every PostgreSQL version or configuration.

Before partitioning, verify actual DBMS support, partition keys, and how **global business-key uniqueness/non-overlap** is guaranteed. Otherwise, consider dedicated locking/coordination or another physical layout.

### 15.2. Retention and Personal Data

Bitemporal tables can only answer for periods still retained. If V1 is purged under a retention policy, a February K query can no longer return the right answer; APIs must expose **the reliable retained history horizon** instead of returning empty results that look like “no price existed.”

Historical records may also contain personal or sensitive data. Separate evidentiary fields from identifying payloads, enforce access controls, encrypt, anonymize/delete per policy, and store the minimum evidence required.

## 16. Bitemporal in Document, Graph, and Analytical Stores

In **DATABASE_DATA_MODELING**, the same “value at B as known at K” requirement can be implemented across data paradigms. Preserve **the semantics of both axes**, not merely the storage format.

| System Type | Viable Representation | What to Control |
|---|---|---|
| **Relational** | Version rows; valid/known ranges; exclusion constraints | Atomic writes, two-dimensional constraints, as-of queries |
| **Document** | Version collection; each document holds `validFrom`/`To` and `knownFrom`/`To` | Document size, multi-document transactions, overlap prevention under concurrency |
| **Graph** | Versioned nodes and edges carrying both intervals | Path queries at (B, K), historical relationship consistency |
| **Analytical warehouse** | Effective-dated dimensions + load/edit history; persisted report versions | Late-arriving dimensions, fact joins, knowledge-history definition |
| **Event store** | Immutable decision events + bitemporal projections | Replay, schema evolution, idempotency, ordering, and retroactive edits |

### 16.1. Document: Two Axes Do Not Fit in One Current Document

A rate version can be represented as:

~~~json
{
  "contractId": 9001,
  "rateKind": "BASE",
  "monthlyAmount": 120000,
  "validFrom": "2026-02-01",
  "validTo": null,
  "knownFrom": "2026-03-10T09:00:00Z",
  "knownTo": "2026-03-20T09:00:00Z",
  "decisionRef": "RATE-MAR10"
}
~~~

That is V3. After correction, document V3 **must remain queryable** for K = Mar 15. If the system only updates a single “current price” document without keeping versioned documents, knowledge history is lost.

Avoid embedding unbounded history inside a single contract document if it risks hitting size limits or rewriting large payloads. A separate version collection is usually better, paired with transactions or conditional writes to stop two decisions from overwriting timelines concurrently.

### 16.2. Graph: Relationship History Also Has Two Axes

Suppose employee 42 belonged to Department A under initial knowledge, and later the system learns the employee transferred to Department B last week. Store versions of the **MEMBER_OF edge** carrying both valid time and known time; versioning only Employee nodes is insufficient.

When querying the org chart at **(B, K)**, every traversed edge and attribute affecting the result must filter by the same two time parameters. On a path Employee → Team → Department, you cannot apply valid time to the first edge and “current state” to the second edge and call that the org chart at B.

### 16.3. Analytical Warehouses: SCD Type 2 Is Not Automatically Bitemporal

**Slowly Changing Dimension Type 2** commonly stores attribute versions by effective interval, which is valuable for historical reporting. Yet a table with **effective_from/effective_to** and a load timestamp does not automatically answer “what did the system know at K?” if old rows are overwritten or lack when they ceased to be accepted knowledge.

If an organization must reproduce reports published prior to a correction, you may need **known time**, **report snapshots/versions**, or a sufficiently complete event log. Clarify the requirement: recomputing figures using current truth differs from explaining why an earlier report showed old figures.

## 17. Test Matrix for Retroactive Adjustments

Use timeline V1–V5 from earlier sections. Each query specifies **B = business date** and **K = system knowledge time**.

| B | K (UTC) | Expected Rate | Explanation |
|---|---|---:|---|
| 2025-12-31 | 2026-03-21 12:00 | None | Before first `valid_from` |
| 2026-02-10 | 2026-03-01 12:00 | 100,000 | V1 |
| 2026-02-10 | 2026-03-15 12:00 | 120,000 | V3 |
| 2026-02-10 | 2026-03-21 12:00 | 100,000 | V4 |
| 2026-02-20 | 2026-03-15 12:00 | 120,000 | V3 |
| 2026-02-20 | 2026-03-21 12:00 | 120,000 | V5 |
| 2026-02-14 | 2026-03-21 12:00 | 100,000 | Before rate switch boundary |
| 2026-02-15 | 2026-03-21 12:00 | 120,000 | Exact rate switch boundary |
| 2026-02-10 | 2026-03-10 09:00 | 120,000 | Exact new `known_period` bound |
| 2026-02-10 | 2026-03-20 09:00 | 100,000 | Exact post-correction `known_period` bound |
| 2026-02-10 | 2026-01-01 07:00 | None | Before first recorded knowledge |

Additional tests should cover:

1. **Closing `known_period` without new INSERT:** transaction must roll back without leaving a knowledge blackout after cutover.
2. **Overlap on both axes:** inserting two rows for the same contract/rate_kind overlapping in both valid and known periods; exclusion constraint must reject it.
3. **Overlap on one axis, disjoint on the other:** old and new versions may overlap in valid time if their `known_period` intervals are disjoint.
4. **Concurrent writes:** two edits to the same contract must never produce two simultaneously accepted timelines at any K.
5. **Idempotency:** re-submitting RATE-MAR20 creates neither a spurious new known layer nor duplicate segments.
6. **Untouched segments:** after correction, prices outside the edited window stay consistent with business decisions.
7. **Multi-segment impact:** a correction intersecting three effective versions cleanly splits leading, middle, and trailing portions.
8. **Finalized documents:** the Mar 15 invoice still proves the rate actually billed even after Feb 10's latest rate changed.
9. **Late-arriving events:** occurred time, received time, and known time are recorded from proper sources, never conflated to guess order.
10. **Time zones and granularity:** market-calendar valid dates and `known_period` `timestamptz` values never drift across day boundaries.
11. **Retention:** querying K outside retained history returns an explicit history-limit indicator.

The **(B, K)** test matrix serves as a data contract: even if storage shifts to document, graph, or event store, business answers must remain equivalent given the same source inputs and rules.

## 18. Practice Exercise: Retroactive Access Entitlement Adjustments

A contract-based entitlement system states:

> “Customers receive PREMIUM access from the contract effective date. Upgrade decisions may arrive late or have their effective date amended. Support must know what access the customer **should have had** on date D per current information, and at time K what access the system had **recorded** for the customer.”

Scenario:

- May 1: system records BASIC entitlement effective May 1.
- June 10: sales submits a PREMIUM decision effective retroactively from May 20.
- June 15: contract review reveals PREMIUM takes effect only on June 1; the June 10 decision must be corrected.

Tasks:

1. Define **customer_entitlement**, entitlement tiers, and two time axes. Use business calendar date for valid time and timestamp for known time.
2. Model bitemporal snapshots after each write. Preserve prior knowledge versions so queries at K before the correction still work.
3. State the invariant: if each customer holds only one tier (BASIC/PREMIUM) at any (B, K), competing rows must not overlap simultaneously across both ranges.
4. Determine access at **B = May 25, K = June 12** and **B = May 25, K = June 16**. Expected answers are **PREMIUM** and **BASIC** respectively.
5. Check access at **B = June 2, K = June 16**. Expected answer is **PREMIUM**.
6. Describe the transaction closing old `known_period` values, splitting `valid_period`, and opening new `known_period` values at one unified K timestamp.
7. Explain why history of access **actually granted on servers** can differ from history of **contractually entitled access**. Proving who accessed a resource when still requires an independent audit/access log.
8. Propose how to handle customer sessions denied access prior to the correction; that is a business and operational remediation process, not something fixed merely by updating history.

**Evaluation criteria:** clear two-interval schema; known axis never overwritten to lose history; appropriate business keys and constraints; accurate as-of queries for both K values; atomic write protocol and preserved actual access evidence.

## 19. Design Sign-Off Checklist

Before choosing bitemporal modeling for retroactive adjustments, engineering should agree on:

- **Questions:** does the system only need the currently accepted effective value, or must it reconstruct what the system **believed at K**?
- **Time definitions:** what do valid date/timestamp mean; which component supplies known time; are exact commit timestamps required?
- **Business keys:** which attributes cause two versions to compete at a (B, K) pair?
- **Bounds:** do both intervals consistently use **[from, to)**, including representation of infinity and unknown values?
- **Constraints:** are simultaneous overlaps across both valid and known prevented; are gaps detected if continuous coverage is required?
- **Correction workflow:** does one transaction read and lock the timeline, recompute affected segments, preserve untouched ones, close old versions, and open new ones?
- **Evidence:** does every edit record source, approver, reason, and prior decision reference; is an append-only event log needed?
- **Finalized records:** do invoices, granted entitlements, or published reports persist independent evidence so effective-history edits do not silently recalculate them?
- **Operations:** are retries, idempotency, concurrency, projection lag, retention, and queryable horizon defined?
- **Performance:** have indexes and partitions been validated against realistic workloads while preserving invariants across storage structures?

**Concluding principle:** a retroactive adjustment may change **what is considered right for date B**, yet must never erase **what the system had accepted at instant K**. Bitemporal modeling preserves both answers by storing each value with a **business effective interval** and a **system knowledge interval**, handling edits through proper transactions, locks, and constraints. Only when both time axes are consistently defined and queryable do past decisions have clear, verifiable grounding that can evolve with the business.
