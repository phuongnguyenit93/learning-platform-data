# EXCLUDE Constraints and Preventing Overlapping Ranges in PostgreSQL

## 1. The Problem: Two Individually Valid Rows That Conflict Side by Side

In a meeting room booking system, a room cannot be booked for two meetings during **overlapping time intervals**. Likewise, a piece of equipment cannot be rented out simultaneously under two contracts, and an effective-dated configuration should not have two versions active at the same moment.

Suppose room 101 has this schedule:

| Booking | Start | End | Status |
|---|---|---|---|
| A | 09:00 | 10:00 | CONFIRMED |
| B | 10:00 | 11:00 | CONFIRMED |
| C | 09:30 | 10:30 | Proposed |

A and B **do not overlap** when times are modeled as half-open intervals `[start, end)`: inclusive start, exclusive end. However, C overlaps both A and B and must be rejected.

A `UNIQUE(room_id, start_at, end_at)` constraint does not solve this problem, because C has different start and end timestamps than A and B. A `CHECK (start_at < end_at)` only verifies that **one row** has a valid interval; it does not compare that row against all other bookings.

PostgreSQL provides **exclusion constraints**, written with `EXCLUDE`, to declare that **no two rows may exist where a specified set of comparisons all evaluate to true**.

Core example:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

This reads as:

> No two records may exist with the **same `room_id`** and **overlapping `during` ranges**.

With the right conditions and setup, PostgreSQL enforces this constraint even under **concurrent transactions**, preventing race conditions when an application simply does “SELECT to check first, INSERT afterward”.

### What You Will Be Able to Do After This Lesson

- Understand the differences among `UNIQUE`, `CHECK`, and `EXCLUDE`.
- Construct and inspect `tstzrange`, `tsrange`, `daterange`, and common range types.
- Understand the overlap operator `&&` and `[)` boundary rules.
- Install the `btree_gist` extension and declare `EXCLUDE USING gist`.
- Use a **partial exclusion constraint** to restrict only active records.
- Handle `NULL`, empty ranges, unbounded ranges, and timezone-aware timestamps.
- Simulate two concurrent sessions trying to book the same room and explain the outcome.
- Use `DEFERRABLE` when adjusting multiple intervals inside one transaction.
- Handle PostgreSQL SQLSTATE `23P01` in applications.
- Inspect generated metadata/indexes and recognize performance and data-modeling limits.

The SQL examples below target a **dedicated PostgreSQL lab**; never run DDL that creates, alters, or drops tables directly in production.

## 2. Expressing Time Intervals with Range Types

PostgreSQL provides **range types** representing continuous or discrete intervals of an element subtype. Common built-in types:

| Range Type | Element Subtype | Typical Use |
|---|---|---|
| `int4range` | `integer` | 32-bit integer intervals |
| `int8range` | `bigint` | ID or 64-bit integer intervals |
| `numrange` | `numeric` | Price/quantity intervals |
| `daterange` | `date` | Effective dates, vacation periods |
| `tsrange` | `timestamp without time zone` | Local wall-clock intervals without timezone |
| `tstzrange` | `timestamp with time zone` | Intervals between **two exact instants in time** |

For room bookings, we choose `tstzrange` because each booking boundary is an absolute instant in time, not a timezone-less “09:00” string.

### 2.1. Creating Ranges with Constructors

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
) AS first_booking;
```

Arguments:

1. **Lower bound:** start point.
2. **Upper bound:** end point.
3. **Bounds notation:** two characters specifying whether each bound is inclusive or exclusive.

You can write this more concisely when inputs already resolve to the right type:

```sql
SELECT tstzrange(
    '2026-11-14 09:00:00+07',
    '2026-11-14 10:00:00+07',
    '[)'
);
```

To keep examples easy to verify, key queries explicitly include `TIMESTAMPTZ` and offsets.

### 2.2. Meaning of the Four Bound Notations

| Notation | Lower Bound | Upper Bound | Interpretation |
|---|---|---|---|
| `[)` | Inclusive | Exclusive | Includes start, excludes end |
| `[]` | Inclusive | Inclusive | Includes both ends |
| `()` | Exclusive | Exclusive | Excludes both ends |
| `(]` | Exclusive | Inclusive | Excludes start, includes end |

For room reservations, `[)` is the standard choice:

```text
A: [09:00, 10:00)
   ██████████████
B:              [10:00, 11:00)
                 ██████████████

A ∩ B = ∅, no overlap.
```

If you used closed intervals `[09:00, 10:00]` and `[10:00, 11:00]`, both would include 10:00 and thus overlap. Therefore, **bound convention is a business rule**, not just formatting.

### 2.3. How Does a Range Differ from Two Separate Timestamp Columns?

Two columns `start_at` and `end_at` can describe an interval, whereas a PostgreSQL range natively carries interval operations:

- Overlap with another range.
- Containment of a specific timestamp.
- Full containment of another range.
- Adjacency between two ranges.
- Lower/upper bounds, empty ranges, and unbounded ranges.

Example:

```sql
SELECT
    tstzrange(
        '2026-11-14 09:00+07',
        '2026-11-14 10:00+07', '[)'
    )
    &&
    tstzrange(
        '2026-11-14 09:30+07',
        '2026-11-14 10:30+07', '[)'
    ) AS overlap_detected;
```

The result is `true` because the two intervals overlap. The `&&` operator is the foundation `EXCLUDE` uses to detect overlapping schedules.

## 3. Range Operators to Understand Before Writing EXCLUDE

| Operator | Reading | Example Meaning |
|---|---|---|
| `a && b` | Ranges overlap | A and B share at least one point |
| `a @> b` | A contains B (range or element) | Validity period contains a timestamp |
| `a <@ b` | A is contained by B | Interval A lies completely inside B |
| `a -\|- b` | Ranges are adjacent | A ends right where B starts per range semantics |
| `a << b` | A is strictly left of B | Disjoint and entirely earlier |
| `a >> b` | A is strictly right of B | Disjoint and entirely later |
| `a = b` | Ranges are equal | Range value equality |

### 3.1. Checking Overlap

```sql
SELECT
    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    &&
    tstzrange('2026-11-14 09:30+07',
              '2026-11-14 10:30+07', '[)')
    AS overlaps;
```

Expected result: `true`.

### 3.2. Checking Adjacent Intervals

```sql
SELECT
    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    &&
    tstzrange('2026-11-14 10:00+07',
              '2026-11-14 11:00+07', '[)')
    AS overlaps,

    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    -|-
    tstzrange('2026-11-14 10:00+07',
              '2026-11-14 11:00+07', '[)')
    AS adjacent;
```

Expected result:

```text
overlaps = false
adjacent = true
```

Back-to-back bookings are valid because the first occupant leaves at the exact instant the next booking begins.

### 3.3. Checking Whether an Instant Falls Inside a Range

```sql
SELECT
    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    @>
    TIMESTAMPTZ '2026-11-14 09:45+07'
    AS contains_time;
```

Result: `true`.

At exactly `10:00+07`, for `[09:00, 10:00)`, containment returns `false` because the upper bound is exclusive.

## 4. What Does EXCLUDE Actually Check?

Conceptually, an exclusion constraint defines a set of comparisons between **any two distinct rows**. PostgreSQL forbids the existence of two rows for which **all** specified comparisons return `TRUE`.

Example:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

Suppose R1 and R2 have:

- `room_id(R1) = room_id(R2)`: TRUE.
- `during(R1) && during(R2)`: TRUE.

Both comparisons being TRUE simultaneously means a **conflict**, so PostgreSQL rejects any change that would allow this pair to exist.

If the two rooms differ:

- The `room_id` comparison is FALSE.
- Even if the time intervals overlap, not **all** conditions are TRUE.

Thus, two different rooms can still be booked at the exact same time.

If the room is the same but intervals are disjoint:

- The `room_id` comparison is TRUE.
- `during && during` is FALSE.

Thus, both bookings are valid.

### 4.1. How EXCLUDE Differs from UNIQUE

A constraint:

```sql
UNIQUE (room_id, start_at, end_at)
```

only forbids rows with exact matching values across the key columns under UNIQUE semantics. It **does not** catch:

```text
A: room 101, [09:00, 10:00)
B: room 101, [09:30, 10:30)
```

because their start/end timestamps differ.

By contrast:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

rejects any two intersecting intervals for the same room, even when their bounds are not identical.

### 4.2. How EXCLUDE Differs from CHECK

`CHECK (start_at < end_at)` validates that a single row's start precedes its end.

`EXCLUDE ... (room_id WITH =, during WITH &&)` enforces that no **two rows conflict** under the specified operators.

The two constraints address **two different layers of validity**, so they are commonly used together.

### 4.3. Special Attention to NULL Semantics

Because `EXCLUDE` rejects a pair of rows only when **every comparison returns TRUE**, if any comparison returns `FALSE` or `NULL`, the pair does not violate the constraint.

For example, if `room_id` allows `NULL`:

```sql
NULL = NULL
```

returns `NULL`, not `TRUE`. Two rows with overlapping intervals and `room_id IS NULL` would not be blocked by `EXCLUDE`.

Therefore, for booking tables, key columns should use:

```sql
room_id bigint NOT NULL,
during tstzrange NOT NULL
```

When the domain forbids overlap, **do not omit `NOT NULL`** just because `EXCLUDE` is present.

## 5. Preparing the Lab Environment with GiST and btree_gist

Here is a complete lab setup moving from empty tables to valid and conflicting cases.

### 5.1. Why Is GiST Needed?

An exclusion constraint requires an **index access method** supporting all conflict operators. For ranges, PostgreSQL typically uses **GiST** (*Generalized Search Tree*).

In our example:

```sql
room_id WITH =
during WITH &&
```

- The range `&&` operator is supported by built-in GiST range operator classes.
- For scalar types like `bigint`, using `=` inside GiST is provided by the `btree_gist` extension.

`btree_gist` does not turn GiST into a B-tree, nor does it magically make every operator on every type supported. It supplies B-tree-like equality/ordering operator classes for common scalar types inside GiST so scalar equality and range overlap can live in one GiST index.

### 5.2. Installing the Extension in the Lab Database

Connect to your target lab database, for example:

```sh
psql -h 127.0.0.1 -p 5432 -U lab_admin -d booking_lab_db
```

Assuming role `lab_admin` and database `booking_lab_db` exist with appropriate privileges, run in SQL:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

This installs the extension objects **in the current database**. Running it in one database does not install it globally across every database in the cluster.

Depending on PostgreSQL version, cloud provider, and privilege policy, creating an extension may require database ownership, `CREATE` privilege, or an administrative role. If denied, ask an administrator to install it in your **lab database**; never grant `SUPERUSER` to an application runtime account just to bypass permission errors.

Verify installation:

```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'btree_gist';
```

To avoid colliding with existing tables, create a dedicated schema:

```sql
CREATE SCHEMA IF NOT EXISTS booking_lab;
```

**Do not run the `CREATE TABLE` statements below if tables with those names already exist containing data you want to keep.** This lab assumes a clean schema.

## 6. Designing a Room Booking Table with EXCLUDE

### 6.1. Rooms Table

```sql
CREATE TABLE booking_lab.rooms (
    room_id bigint PRIMARY KEY,
    room_name text NOT NULL UNIQUE
);

INSERT INTO booking_lab.rooms(room_id, room_name)
VALUES
    (101, 'Meeting Room A'),
    (102, 'Meeting Room B');
```

### 6.2. Reservations Table

```sql
CREATE TABLE booking_lab.reservations (
    reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    room_id bigint NOT NULL
        REFERENCES booking_lab.rooms(room_id),

    during tstzrange NOT NULL,

    status text NOT NULL DEFAULT 'CONFIRMED'
        CHECK (status IN ('HELD', 'CONFIRMED', 'CANCELLED')),

    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT reservation_period_not_empty
        CHECK (NOT isempty(during)),

    CONSTRAINT reservation_no_active_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            during WITH &&
        )
        WHERE (status IN ('HELD', 'CONFIRMED'))
        DEFERRABLE INITIALLY IMMEDIATE
);
```

This demonstrates a **partial exclusion constraint**: only rows with status `HELD` or `CONFIRMED` are included in overlap exclusion. `CANCELLED` rows do not hold the room.

Components:

| Component | Role |
|---|---|
| `room_id bigint NOT NULL` | Identifies the room; cannot be missing |
| `during tstzrange NOT NULL` | Defined booking interval |
| `CHECK (NOT isempty(during))` | Forbids empty intervals |
| `status ... CHECK (...)` | Restricts allowed statuses |
| `EXCLUDE USING gist` | Instructs PostgreSQL to compare rows via GiST |
| `room_id WITH =` | Restricts conflicts to the same room |
| `during WITH &&` | Overlapping intervals conflict |
| `WHERE (status IN (...))` | Applies only to rows still holding a slot |
| `DEFERRABLE INITIALLY IMMEDIATE` | Checks immediately by default, while allowing transactions to defer |

PostgreSQL **creates a supporting index for the exclusion constraint** automatically. Do not create an identical redundant index just to make the constraint work.

### 6.3. Why Include Both `HELD` and `CONFIRMED`?

A system may temporarily hold a room while a user completes payment or confirmation. While `HELD` is active, it must block others from booking the same slot.

When a user cancels or a hold expires and the system transitions the row to `CANCELLED`, the slot is released under the partial constraint predicate.

**Important:** merely having a business expiration deadline on a `HELD` row does not make `EXCLUDE` ignore it automatically once time passes. PostgreSQL does not flip `status` automatically as wall-clock time advances; you need a transaction-safe workflow to expire stale holds per business rules.

Never place volatile time expressions like `now()` directly inside a **partial index predicate** expecting index membership to update automatically over time: index predicates require immutable expressions and are not re-evaluated as the clock ticks.

## 7. Lab 1: Adjacent Bookings Are Accepted

Insert booking A for room 101 from 09:00 to 10:00:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    ),
    'CONFIRMED'
)
RETURNING reservation_id, room_id, during, status;
```

Insert booking B immediately after:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00+07',
        TIMESTAMPTZ '2026-11-14 11:00+07',
        '[)'
    ),
    'CONFIRMED'
)
RETURNING reservation_id, room_id, during, status;
```

Both `INSERT` statements succeed because:

```text
A = [09:00, 10:00)
B = [10:00, 11:00)

A && B = FALSE
```

Using half-open `[)` intervals ensures adjacent back-to-back meetings do not count as overlapping.

If operations require a **15-minute cleanup buffer** between meetings, the business rule is stricter than “no overlap”. Model the buffer explicitly into the occupied interval or use another constraint strategy rather than expecting `EXCLUDE` to infer cleanup time.

## 8. Lab 2: Overlapping Intervals Are Rejected

Try inserting booking C in the same room 101:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ),
    'CONFIRMED'
);
```

Interval `[09:30, 10:30)` overlaps both A and B.

**Expected result:** PostgreSQL rejects the insert with a message like:

```text
ERROR: conflicting key value violates exclusion constraint
       "reservation_no_active_overlap"
SQLSTATE: 23P01
```

This is an illustrative message; exact `DETAIL`, table formatting, and wording depend on version, client, and locale. The critical SQLSTATE code is **`23P01` — `exclusion_violation`**.

### 8.1. When a Statement Fails Inside a Transaction

In a `psql` autocommit session, a failed statement does not leave subsequent standalone statements inside a broken transaction.

However, if running inside:

```sql
BEGIN;

INSERT INTO booking_lab.reservations(room_id, during)
VALUES (
    101,
    tstzrange('2026-11-14 09:30+07',
              '2026-11-14 10:30+07', '[)')
);

-- INSERT fails.
ROLLBACK;
```

the transaction needs `ROLLBACK` to clear its aborted state. Do not keep sending more business statements expecting PostgreSQL to ignore only the failed statement and commit the rest.

### 8.2. Same Time in a Different Room Is Valid

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    102,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ),
    'CONFIRMED'
);
```

This booking is for room 102. Even though its time overlaps room 101's bookings, `room_id =` evaluates to FALSE so it **does not violate** the exclusion constraint.

Summary:

| New Booking | Room | Interval | Outcome |
|---|---:|---|---|
| B | 101 | `[10:00,11:00)` | Allowed — adjacent to A |
| C | 101 | `[09:30,10:30)` | Rejected — overlaps A and B |
| D | 102 | `[09:30,10:30)` | Allowed — different room |
| E | 101 | `[11:00,12:00)` | Allowed — after B |
| F | 101 | `[08:00,09:00)` | Allowed — before A |

## 9. Lab 3: Status-Based Partial Exclusion Constraint

Suppose a customer canceled a 11:30–12:30 booking. The canceled row can remain in the table for history without blocking new bookings.

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 11:30+07',
              '2026-11-14 12:30+07', '[)'),
    'CANCELLED'
);
```

Now insert an active booking for the same room and interval:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 11:30+07',
              '2026-11-14 12:30+07', '[)'),
    'CONFIRMED'
);
```

The second statement succeeds if no other active booking overlaps, because the `CANCELLED` row **is outside the scope** of the partial exclusion constraint.

### 9.1. Updating CANCELLED Back to CONFIRMED Can Be Blocked

Suppose someone updates that canceled booking back to `CONFIRMED`:

```sql
UPDATE booking_lab.reservations
SET status = 'CONFIRMED'
WHERE room_id = 101
  AND status = 'CANCELLED'
  AND during = tstzrange(
      '2026-11-14 11:30+07',
      '2026-11-14 12:30+07',
      '[)'
  );
```

When a row transitions from outside the constraint predicate into the constrained set, PostgreSQL checks the exclusion constraint. Since an overlapping `CONFIRMED` booking already exists, the `UPDATE` is rejected.

This matters for “restore canceled booking”, “confirm hold”, and “extend reservation” workflows: **not only `INSERT`, but `UPDATE` is also enforced by `EXCLUDE`**.

### 9.2. Hold Expiration Does Not Auto-Change Status

Suppose the table has a `hold_expires_at` column. A `HELD` row whose deadline has passed—while its `status` is still `'HELD'`—still blocks new bookings under the current predicate.

A proper workflow typically needs to:

1. Identify expired `HELD` records.
2. Transition them to a released status inside a transaction.
3. Retry or proceed with creating the new booking safely once status is updated.
4. Handle races between a hold-cleanup job and an incoming booking request.

Never put a clock-dependent function into a GiST index predicate expecting rows to “drop out of the index” automatically as time passes.

## 10. Why Does EXCLUDE Prevent Race Conditions in Scheduling?

A common application pattern is:

```text
Step 1: SELECT to check if the room is free.
Step 2: If free, INSERT the new booking.
```

The problem is two concurrent requests:

```text
Time      Transaction A                 Transaction B
-------   ----------------------------- ------------------------------
T1        SELECT: sees no booking X
T2                                      SELECT: sees no booking X
T3        INSERT booking X
T4                                      INSERT booking Y overlapping X
T5        COMMIT
T6                                      COMMIT
```

Relying solely on a plain `SELECT`, both transactions see an empty room in their snapshots and both insert conflicting bookings.

**An exclusion constraint pushes the “no overlap” invariant down into the database engine.** PostgreSQL uses the index and transaction-aware conflict checking so two committed transactions can never leave a violating pair in the table.

This protects every write path consistently:

- HTTP APIs.
- Queue workers.
- Import scripts.
- Admin consoles.
- Other services sharing the database.

Even so, `EXCLUDE` does not check whether the user has **permission to book**, whether the room is under maintenance, or whether payment succeeded. Those remain separate business checks.

## 11. Two-Session Lab: Two Concurrent Transactions Booking the Same Slot

### 11.1. Initial Setup

Pick an unused slot, such as room 101 from 14:00 to 15:00 on 2026-11-14. Open **two independent PostgreSQL connections** to the same database:

- **Session A**.
- **Session B**.

Use two `psql` terminals or two separate client connections. Do not run both blocks sequentially on the same connection if you want to observe concurrency.

### 11.2. Session A

```sql
BEGIN;

INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 14:00+07',
              '2026-11-14 15:00+07', '[)'),
    'CONFIRMED'
);

-- Keep the transaction open here.
-- Do NOT COMMIT or ROLLBACK yet.
```

### 11.3. Session B

While A's transaction is still open:

```sql
BEGIN;

INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 14:30+07',
              '2026-11-14 15:30+07', '[)'),
    'CONFIRMED'
);
```

Because the two bookings overlap, PostgreSQL must wait for A's uncommitted transaction outcome to decide whether the constraint is violated.

Depending on timing and locking, B's `INSERT` will **wait** on A. This is directly observable whenever the constraint arbitrates a conflict between two concurrent transactions.

### 11.4. Finish A and Observe B

**Case 1: A COMMITs**

In Session A:

```sql
COMMIT;
```

Once A commits 14:00–15:00, B cannot commit 14:30–15:30. Once the conflict resolves, B's statement fails with `23P01` per constraint semantics. In Session B, clean up the aborted transaction:

```sql
ROLLBACK;
```

**Case 2: A ROLLBACKs**

If A rolls back before committing:

```sql
ROLLBACK;
```

B can proceed and succeed if no other active booking conflicts; then `COMMIT` in B while its transaction is valid.

**Do not run both scenarios back-to-back on the same committed slot without resetting state.** Once Case 1 commits a booking, a subsequent test on the same slot will collide with it; pick a fresh lab slot or reset test data cleanly.

### 11.5. If a Statement Waits Too Long

In the lab you can configure a session lock timeout so commands do not hang indefinitely:

```sql
SET lock_timeout TO '5s';
```

When `lock_timeout` expires, the statement fails with a lock-timeout error rather than `23P01`. That tells you the operation did not wait long enough to resolve the conflict—it does **not** prove the slot is available.

Applications should handle timeouts and retries per policy rather than treating every timeout as “room available”. After the lab:

```sql
RESET lock_timeout;
```

### 11.6. Why Is a Pre-Check SELECT Still Useful?

An application can run a `SELECT` to display open time slots and give users fast UI feedback. Yet that `SELECT` is only a **point-in-time snapshot**. At write time, the database constraint remains the decisive gatekeeper.

A sound pattern:

1. Application layer validates authorization, input bounds, and shows available slots.
2. Submit the booking transaction.
3. Rely on `EXCLUDE` to block last-millisecond conflicts.
4. If PostgreSQL returns `23P01`, roll back and inform the user the slot was just taken.
5. If a timeout or infrastructure error occurs, handle it separately per retry/idempotency policy.

## 12. Empty Ranges, Unbounded Ranges, and NULL

### 12.1. Empty Ranges

```sql
SELECT
    isempty(tstzrange(
        '2026-11-14 09:00+07',
        '2026-11-14 09:00+07',
        '[)'
    )) AS is_empty;
```

With equal bounds and `[)` notation, the range is **empty**: it contains no instants at all.

An empty range does not overlap any normal range under `&&`. Without a check, the system could store zero-length “bookings” that `EXCLUDE` never flags as overlapping.

That is why the schema includes:

```sql
CHECK (NOT isempty(during))
```

which enforces a separate invariant from `EXCLUDE`.

### 12.2. Ranges with Unbounded Sides

PostgreSQL supports open-ended ranges when a bound is omitted. Example:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00+07',
    NULL,
    '[)'
) AS open_ended_period;
```

In a range constructor, a `NULL` bound argument creates an **unbounded side**, not a range containing NULL. Logically it extends infinitely into the future and will overlap many subsequent bookings.

If your domain allows only finite start and end times, add:

```sql
ALTER TABLE booking_lab.reservations
ADD CONSTRAINT reservation_bounds_required
CHECK (
    NOT lower_inf(during)
    AND NOT upper_inf(during)
);
```

This blocks *unbounded* range bounds. If the domain also forbids special timestamp values like `'infinity'`, check explicitly because an **unbounded range** and a timestamp value of `'infinity'` are not completely identical concepts.

Do not add this constraint when the domain genuinely needs open-ended intervals, such as effective-dated pricing valid indefinitely.

### 12.3. If the Range Column Is NULL

`during tstzrange NOT NULL` guarantees every booking has a range value. Writing only:

```sql
CHECK (NOT isempty(during))
```

is **not enough to replace `NOT NULL`**, because a `CHECK` evaluating to UNKNOWN/NULL is accepted by PostgreSQL. Keep both when required.

### 12.4. Are Adjacent Ranges Always Allowed?

That depends on boundary notation. With `[)`, `[09:00, 10:00)` and `[10:00, 11:00)` do not intersect. With closed `[]` bounds at 10:00, they overlap.

Standardize the API and data contract: every creation, update, CSV import, and query must apply **the exact same boundary convention**.

## 13. Choosing tstzrange, tsrange, or daterange

### 13.1. When to Use tstzrange

`tstzrange` uses two `timestamptz` values. It fits when modeling **real instants in time** that a global system must agree on.

Example:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
);
```

This interval represents the exact same span of physical time whether the PostgreSQL session displays UTC or Vietnam time. `timestamptz` renders according to the session's `TimeZone`, without altering the underlying instant.

### 13.2. When tsrange Fits

`tsrange` uses `timestamp without time zone`. It fits local wall-clock patterns not tied to a global instant—such as “business hours template 09:00–17:00” when timezone is tracked separately.

```sql
SELECT tsrange(
    TIMESTAMP '2026-11-14 09:00:00',
    TIMESTAMP '2026-11-14 10:00:00',
    '[)'
);
```

Using `tsrange` for cross-country meeting bookings without storing timezones risks confusing 09:00 in one city with 09:00 in another.

### 13.3. When to Use daterange

Use `daterange` when rules operate on **calendar dates**, such as leave from Nov 14 through the end of Nov 16.

Half-open representation:

```sql
SELECT daterange(
    DATE '2026-11-14',
    DATE '2026-11-17',
    '[)'
) AS vacation_period;
```

This includes Nov 14, 15, and 16 while excluding Nov 17. If an API receives an **inclusive** end date, convert consistently to half-open representation or use matching bound notation.

For discrete ranges like `daterange`, PostgreSQL applies canonicalization that normalizes equivalent notations into a canonical form. Do not assume `tstzrange` automatically “adds one smallest time unit” the way discrete ranges do.

### 13.4. Daylight Saving Time and Multi-Region Schedules

Regions such as `America/New_York` shift offsets seasonally. “09:00–10:00 New York time” must be resolved using **both the calendar date and IANA timezone name** to produce exact instants.

Never add a fixed offset year-round for international scheduling. For recurring weekly schedules in local time, a single `tstzrange` cannot capture recurrence rules on its own; store the template in its timezone and materialize individual occurrences.

## 14. Variant: Two Columns start_at and end_at Instead of One Range Column

Many existing APIs and schemas have columns like:

```text
booking_id | room_id | start_at | end_at
```

PostgreSQL can still enforce `EXCLUDE` over a **range expression** built from those two columns, without adding a `during` column.

### 14.1. DDL with a tstzrange Expression

```sql
CREATE TABLE booking_lab.reservations_columns (
    reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    room_id bigint NOT NULL
        REFERENCES booking_lab.rooms(room_id),

    start_at timestamptz NOT NULL,
    end_at timestamptz NOT NULL,

    status text NOT NULL DEFAULT 'CONFIRMED'
        CHECK (status IN ('HELD', 'CONFIRMED', 'CANCELLED')),

    CONSTRAINT reservation_start_before_end
        CHECK (start_at < end_at),

    CONSTRAINT reservation_columns_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            (tstzrange(start_at, end_at, '[)')) WITH &&
        )
        WHERE (status IN ('HELD', 'CONFIRMED'))
);
```

Meaning:

- `CHECK (start_at < end_at)` blocks invalid/empty intervals.
- Expression `tstzrange(start_at, end_at, '[)')` is indexed inside `EXCLUDE`.
- Active bookings for the same room cannot have overlapping ranges.

This also blocks `UPDATE start_at` or `UPDATE end_at` operations that would introduce an overlap.

### 14.2. Comparing Storage Approaches

| Design | Pros | Considerations |
|---|---|---|
| Single `during tstzrange` column | Direct range operators; clear interval semantics | Drivers/APIs must handle range types; check empty/unbounded |
| Two `start_at`/`end_at` columns + expression `EXCLUDE` | Familiar to ORMs/APIs; explicit scalar columns | Queries must repeat the same range expression to leverage the index |
| Two columns plus a generated range column | Convenient when both scalar columns and range column are desired | Evaluate constraint interaction and PostgreSQL version support |

In either of the first two designs, stay consistent on timezones, bound rules, and min/max duration limits.

### 14.3. Do Not Use a Subquery Inside CHECK to Scan Other Rows

Do not try to write:

```sql
-- Inappropriate use of CHECK to scan other rows:
-- CHECK (
--     NOT EXISTS (
--         SELECT 1 FROM booking_lab.reservations_columns ...
--     )
-- )
```

PostgreSQL forbids direct subqueries in `CHECK` like this. More importantly, `CHECK` is built for per-row conditions, not concurrency-safe cross-row validation. For interval exclusion, `EXCLUDE` expresses the rule directly and enforces it reliably in the database.

## 15. DEFERRABLE: Deferring Checks Until Transaction End

Sometimes an application needs to modify **multiple bookings in one transaction**—for example, swapping two adjacent time slots.

Initially:

```text
Booking A: [09:00, 10:00)
Booking B: [10:00, 11:00)
```

Goal after swap:

```text
Booking A: [10:00, 11:00)
Booking B: [09:00, 10:00)
```

If you update A first, A temporarily overlaps B. With immediate checking, the first `UPDATE` fails even though the **final state** of the transaction is valid.

### 15.1. DEFERRABLE INITIALLY IMMEDIATE

In DDL:

```sql
CONSTRAINT reservation_no_active_overlap
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
WHERE (status IN ('HELD', 'CONFIRMED'))
DEFERRABLE INITIALLY IMMEDIATE
```

means:

- By default, the constraint is checked in **IMMEDIATE** mode.
- Inside a transaction, you can switch checking to **DEFERRED**.
- When deferred, PostgreSQL checks at requested switch points or before the transaction commits.

Not every PostgreSQL constraint can be deferrable. Exclusion constraints support it; standard `CHECK` and `NOT NULL` constraints cannot be deferred in the same way.

### 15.2. Swapping Two Intervals in One Transaction

Suppose active reservations with IDs 201 and 202 exist for room 101 with the intervals above; these are **illustrative IDs**. In your lab, query `SELECT reservation_id, ...` first to get actual IDs before updating.

```sql
BEGIN;

SET CONSTRAINTS reservation_no_active_overlap DEFERRED;

UPDATE booking_lab.reservations
SET during = tstzrange(
    '2026-11-14 10:00+07',
    '2026-11-14 11:00+07',
    '[)'
)
WHERE reservation_id = 201;

UPDATE booking_lab.reservations
SET during = tstzrange(
    '2026-11-14 09:00+07',
    '2026-11-14 10:00+07',
    '[)'
)
WHERE reservation_id = 202;

COMMIT;
```

If IDs, rooms, and intervals match the assumption, **the final state has no overlap**, so the transaction commits cleanly. If two intervals still overlap at the end, the error surfaces **at `COMMIT`**.

**Note:** switching to deferred does not allow committing violating data. It only allows **temporary conflicts mid-transaction** provided they are resolved before final validation.

### 15.3. Switching Back to IMMEDIATE for Early Verification

Inside a deferred transaction:

```sql
SET CONSTRAINTS reservation_no_active_overlap IMMEDIATE;
```

Switching to `IMMEDIATE` checks pending changes right away; if any violation remains, this statement fails.

### 15.4. When Should You Avoid Deferring?

Not every booking operation needs deferred checking. For an ordinary single `INSERT`:

- Immediate checking reports the conflict right on the offending SQL statement.
- Avoids holding temporarily conflicting states open inside a transaction.
- Makes request tracing and error handling simpler.

Defer only when a transaction workflow **genuinely must** update multiple rows across an intermediate state from valid state A to valid state B.

### 15.5. Deferrable and ON CONFLICT

When using `INSERT ... ON CONFLICT`, keep two limits in mind:

- Not every constraint can serve as an arbiter for `ON CONFLICT DO UPDATE`.
- **Exclusion constraints are not supported as arbiters for `ON CONFLICT DO UPDATE`** in standard usage.
- Deferrable constraints also have restrictions as conflict arbiters.

For scheduling, rather than blindly “updating whichever booking overlapped”, handle `23P01` as a **business conflict** and ask the user to choose another slot. That is much safer than silently overwriting an existing reservation.

## 16. Querying Schedules Using Range Operators

### 16.1. Finding Bookings Overlapping a Proposed Interval

```sql
SELECT
    reservation_id,
    room_id,
    during,
    status
FROM booking_lab.reservations
WHERE room_id = 101
  AND status IN ('HELD', 'CONFIRMED')
  AND during && tstzrange(
      '2026-11-14 09:45+07',
      '2026-11-14 10:15+07',
      '[)'
  )
ORDER BY lower(during);
```

This returns active bookings in the same room overlapping the proposed interval—useful for **explaining why a slot cannot be booked**.

This query assists the UI. Final enforcement still relies on `EXCLUDE` during `INSERT`/`UPDATE`, because another booking could be committed right after your `SELECT`.

### 16.2. Finding the Booking at a Specific Instant

```sql
SELECT
    reservation_id,
    room_id,
    during
FROM booking_lab.reservations
WHERE room_id = 101
  AND status IN ('HELD', 'CONFIRMED')
  AND during @> TIMESTAMPTZ '2026-11-14 09:45+07';
```

The `@>` operator checks whether `during` **contains** 09:45.

### 16.3. Extracting Lower Bounds, Upper Bounds, and Range Properties

```sql
SELECT
    reservation_id,
    lower(during) AS start_at,
    upper(during) AS end_at,
    lower_inc(during) AS start_inclusive,
    upper_inc(during) AS end_inclusive,
    isempty(during) AS period_is_empty
FROM booking_lab.reservations
ORDER BY reservation_id;
```

Functions:

| Function | Role |
|---|---|
| `lower(r)` | Returns lower bound if finite/present |
| `upper(r)` | Returns upper bound if finite/present |
| `lower_inc(r)` | Is the lower bound inclusive? |
| `upper_inc(r)` | Is the upper bound inclusive? |
| `lower_inf(r)` | Is the lower bound unbounded? |
| `upper_inf(r)` | Is the upper bound unbounded? |
| `isempty(r)` | Is the range empty? |

These functions help expose `start_at`/`end_at` fields in APIs. Still, preserve bound semantics in the API contract; always using `[)` keeps inputs and outputs clear.

### 16.4. Inspecting Schedules with TimeZone

```sql
SHOW TimeZone;

SELECT
    lower(during) AS local_start_display,
    upper(during) AS local_end_display
FROM booking_lab.reservations;
```

`tstzrange` stores instants and formats bounds using the session's display timezone. Switching session `TimeZone` from UTC to `Asia/Ho_Chi_Minh` **changes the displayed clock strings**, while overlap detection remains unchanged.

To render wall-clock time in a specific zone regardless of session settings:

```sql
SELECT
    lower(during) AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_start_wall_time,
    upper(during) AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_end_wall_time
FROM booking_lab.reservations;
```

`AT TIME ZONE` here returns local wall-clock time as `timestamp without time zone`; if API consumers need timezone info, send the zone name separately or format timestamps with offsets.

## 17. Does an Exclusion Constraint Auto-Create an Index?

Yes. When you create `EXCLUDE USING gist (...)`, PostgreSQL automatically builds a backing GiST index to enforce exclusion checks.

### 17.1. Inspecting Metadata in psql

In `psql`:

```text
\d+ booking_lab.reservations
```

Typically displays:

- Columns and data types.
- Primary key.
- Check constraints.
- Foreign keys.
- Exclusion constraint, backing index name, and GiST access method.

`\d+` is a **`psql` meta-command**, not standard SQL sent from JDBC.

### 17.2. Inspecting Exclusion Constraints via Catalogs

```sql
SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS constraint_definition
FROM pg_constraint AS c
WHERE c.conrelid = 'booking_lab.reservations'::regclass
  AND c.contype = 'x'
ORDER BY c.conname;
```

`contype = 'x'` identifies an **exclusion constraint**.

List table indexes:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'booking_lab'
  AND tablename = 'reservations'
ORDER BY indexname;
```

You will see the primary key index and the exclusion constraint's GiST index. Never create a duplicate GiST index assuming `EXCLUDE` didn't create one.

### 17.3. The Index Can Also Speed Up Overlap Queries

A query matching the constraint predicate:

```sql
EXPLAIN
SELECT reservation_id
FROM booking_lab.reservations
WHERE room_id = 101
  AND status IN ('HELD', 'CONFIRMED')
  AND during && tstzrange(
      '2026-11-14 09:00+07',
      '2026-11-14 10:00+07',
      '[)'
  );
```

can leverage the GiST index when the planner finds it beneficial.

Because the index is **partial** (`status IN ('HELD', 'CONFIRMED')`), the query must include conditions allowing the planner to prove it only needs rows covered by the predicate. Queries across all statuses cannot rely solely on that partial index.

On a lab table with only a few rows, PostgreSQL may pick a sequential scan—that does not mean the index is broken.

## 18. GiST Cost, Concurrency, and Scalability

### 18.1. Benefits

GiST checks and searches intervals much more efficiently than loading entire schedules into application memory.

Enforcing the constraint in the database guarantees consistency across all write paths: APIs, scripts, background jobs, and bulk imports.

### 18.2. Costs

Every insert or update affecting an active booking must check the constraint and maintain the GiST index. Under continuous write workloads, factor in:

- Index storage size.
- CPU and I/O overhead.
- Lock/transaction wait times when bookings contend for the same resource.
- `VACUUM` and index maintenance overhead as rows churn.
- Long waits if transactions hold locks too long.

There is no single fixed overhead figure. Benchmark on representative data volumes and concurrency levels.

### 18.3. Avoid Long-Running Transactions

A request should **never**:

1. Start a transaction.
2. Insert a held booking.
3. Wait minutes for the user to finish an external payment.
4. Finally commit.

Holding a transaction open across external I/O forces competing bookings to wait and increases lock contention.

Instead, usually:

- Commit a `HELD` status quickly with an expiration timestamp.
- Run payments and external steps outside the database transaction.
- Transition to `CONFIRMED` upon valid completion.
- Release expired `HELD` bookings safely via a background workflow.

### 18.4. Is Manual Locking Still Needed?

When the only goal is preventing two overlapping bookings for the same room, `EXCLUDE` handles the core invariant. Manual locking may still be needed for other rules—such as total seat limits, reserving multiple rooms atomically, or managing hold slots—but never treat `SELECT ... FOR UPDATE` on existing rows as a simple substitute for `EXCLUDE`.

When no conflicting row exists yet, `SELECT FOR UPDATE` does not lock “the absence of an interval” in an intuitive way. `EXCLUDE` states the invariant directly and lets PostgreSQL enforce it safely against concurrent races.

## 19. Advanced: Multiple Resources, Multi-Tenancy, and Grouping

### 19.1. Conflict Scoped to the Same Room

Constraint:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

blocks overlaps within **one room**, while allowing different rooms to book the same slot.

### 19.2. Multi-Tenant Systems

If two tenants can reuse the same `room_id` values inside a shared table, include **`tenant_id`** in the exclusion constraint.

Constraint clause example:

```sql
EXCLUDE USING gist (
    tenant_id WITH =,
    room_id WITH =,
    during WITH &&
)
```

With `tenant_id bigint NOT NULL` and `room_id bigint NOT NULL`, `btree_gist` provides the GiST equality operator classes needed.

Meaning:

> Two rows conflict only when **they share the same tenant, the same room, and overlapping intervals**.

Omitting `tenant_id` when room IDs are only unique per tenant would let tenant A block tenant B's bookings or misrepresent business isolation.

In multi-tenant schemas, also include `tenant_id` in foreign keys where tenant isolation matters, and enforce proper authorization/RLS. An exclusion constraint only prevents **overlaps**—it does not prevent cross-tenant reads.

### 19.3. When Different Dimensions Are Needed

Another example: an equipment item cannot be assigned to two employees simultaneously:

```sql
EXCLUDE USING gist (
    equipment_id WITH =,
    usage_period WITH &&
)
```

Or an organization enforcing non-overlapping effective-dated configurations per entity:

```sql
EXCLUDE USING gist (
    entity_id WITH =,
    valid_period WITH &&
)
```

The shared principle is not the column names, but that **at least one comparison in the list must not be TRUE between any two rows**.

### 19.4. What If a Resource Allows Up to Two Concurrent Bookings?

A simple `EXCLUDE` with `resource_id WITH =` and `period WITH &&` enforces **at most one** booking at any instant.

“At most two” or “total capacity ≤ 30” cannot be expressed directly with this single exclusion constraint alone. Model individual slots, capacity units, or dedicated locking/transactional logic instead—do not try to turn `&&` into an overlap counter.

## 20. EXCLUDE and Partitioned Tables

Partitioning requires careful design. If a reservations table is partitioned by month or by tenant, two conflicting rows might land in **different partitions**.

An exclusion constraint enforced only within individual partitions will not automatically catch conflicts **across partitions**. Support and partition-key rules for constraints on partitioned tables also vary across PostgreSQL versions.

When considering partitioning:

1. Check exact exclusion-constraint capabilities on your **target PostgreSQL version**.
2. Verify whether the constraint can be defined on the partitioned parent and whether all partition-key columns must participate with equality.
3. Choose a partition key so any potentially conflicting bookings always share a partition under the enforced rule.
4. Actually test two overlapping intervals that cross a partition boundary.
5. Never test only same-day/same-month bookings and assume the whole table is protected.

For example, if partitioned by **start date**, a booking from 23:30–00:30 and one from 00:00–01:00 land in different daily partitions while still overlapping. If the constraint does not span partitions, bad data slips through.

For simpler systems, get exclusion constraints working cleanly on a **regular unpartitioned table** before introducing partitioning.

## 21. Adding EXCLUDE to a Table with Existing Data

If a table already contains overlapping intervals, adding an exclusion constraint scans existing rows and **fails** if any conflict exists.

Syntax example:

```sql
ALTER TABLE booking_lab.reservations
ADD CONSTRAINT another_no_overlap_rule
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
WHERE (status IN ('HELD', 'CONFIRMED'));
```

**Do not run this on the lab table that already has the identical rule**: it creates a near-duplicate constraint and an unnecessary extra index.

In real projects, the migration workflow should:

- Query for existing overlapping pairs beforehand.
- Decide how to resolve conflicting historical records per business rules.
- Schedule an appropriate migration window and assess lock/index-build impact.
- Execute the migration with a tested rollback/recovery plan.
- Verify afterward with concurrency tests and boundary edge cases.

### 21.1. Query to Find Existing Conflicts

When preparing to add `EXCLUDE` to an existing schema, a self-join reveals conflicting pairs:

```sql
SELECT
    a.reservation_id AS first_reservation,
    b.reservation_id AS second_reservation,
    a.room_id,
    a.during AS first_period,
    b.during AS second_period
FROM booking_lab.reservations AS a
JOIN booking_lab.reservations AS b
  ON a.room_id = b.room_id
 AND a.reservation_id < b.reservation_id
 AND a.during && b.during
WHERE a.status IN ('HELD', 'CONFIRMED')
  AND b.status IN ('HELD', 'CONFIRMED')
ORDER BY a.room_id, a.reservation_id, b.reservation_id;
```

In our lab schema where the constraint is already active, this returns zero active conflicts. In a legacy database, it pinpoints rows to clean up before enabling the constraint.

The `a.reservation_id < b.reservation_id` predicate avoids self-pairs and prevents reporting each pair twice.

## 22. Handling EXCLUDE Errors in Java/JDBC Applications

When PostgreSQL rejects an overlapping booking, applications should distinguish a **business conflict** from a technical error.

Condensed Java/JDBC example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class ReservationService {
    public void createReservation(
            Connection connection,
            long roomId,
            java.time.OffsetDateTime start,
            java.time.OffsetDateTime end) throws SQLException {

        String sql = """
            INSERT INTO booking_lab.reservations(room_id, during, status)
            VALUES (
                ?,
                tstzrange(?::timestamptz, ?::timestamptz, '[)'),
                'CONFIRMED'
            )
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setLong(1, roomId);
            statement.setObject(2, start);
            statement.setObject(3, end);

            try {
                statement.executeUpdate();
            } catch (SQLException error) {
                if ("23P01".equals(error.getSQLState())) {
                    // Schedule conflict: return an appropriate business error.
                    // The current transaction must be handled/rolled back properly.
                    throw new IllegalStateException(
                        "This time slot already has a conflicting booking",
                        error
                    );
                }
                throw error;
            }
        }
    }
}
```

This illustrates **SQLSTATE handling**, not a full production Java application. A real project needs the PostgreSQL JDBC driver, datasource, validation, and proper transaction management.

Key notes:

- `OffsetDateTime` carries an explicit offset, avoiding timezone ambiguity.
- Start must precede end; validate early in the API while keeping the database constraint.
- When `INSERT` fails inside an open transaction, roll back or let the transaction manager clean up.
- If the constraint is deferred, the error surfaces at **`COMMIT`**, not at `executeUpdate()`. Error handling must wrap commit as well.
- If a table has multiple exclusion constraints, `SQLSTATE 23P01` alone does not tell you which constraint failed; inspect the **constraint name** from structured driver error metadata rather than matching translated message strings.
- Never return raw PostgreSQL `DETAIL` text to end users if it exposes another user's booking times; error details can leak internal data.
- HTTP APIs often map schedule conflicts to `409 Conflict`, aligned with API contracts and retry/idempotency rules.

**Never handle `23P01` by silently shifting the booking to another time without user consent.** The constraint detects conflict; suggesting alternatives belongs in application UX.

## 23. Can EXCLUDE Replace SERIALIZABLE?

Do not treat `EXCLUDE`, row locks, and isolation levels as interchangeable substitutes.

### 23.1. EXCLUDE Is a Data Constraint

It enforces a specific invariant:

> No two rows for the same room have overlapping active intervals.

Under concurrent transactions, PostgreSQL arbitrates conflicts to preserve that invariant.

### 23.2. SERIALIZABLE Is an Isolation Level

`SERIALIZABLE` ensures the outcome of **entire concurrent transactions** matches a serial execution order per PostgreSQL's semantics. It detects serialization anomalies and asks applications to retry transactions on SQLSTATE `40001` (*serialization_failure*).

However, `SERIALIZABLE` alone does not teach the database “two intervals cannot overlap” unless application code executes the right checks and writes. Conversely, even with `EXCLUDE`, your system may still need appropriate isolation levels or locking for other business invariants.

### 23.3. How Should They Work Together?

- Use **`EXCLUDE`** to express the “no overlapping intervals” data invariant.
- Use **`CHECK`** for single-row conditions like non-empty intervals.
- Use **`FOREIGN KEY`** to ensure referenced rooms exist.
- Use **transactions** to group booking creation, status changes, and related tables.
- Choose **isolation levels** and retry strategies based on overall workflow invariants.
- Use explicit locking when coordinating multiple resources or rules that cannot live inside one constraint.

They are complementary defense layers, not mutually exclusive replacements.

## 24. Common Mistakes

### 24.1. Using UNIQUE on start/end Columns

`UNIQUE(room_id, start_at, end_at)` only blocks **identical start/end pairs**, failing to catch partial overlaps. Use `EXCLUDE` with `&&` or another mechanism enforcing the true business invariant.

### 24.2. Checking Availability with SELECT Only Before INSERT

Two concurrent transactions can both observe a free room. `EXCLUDE` lets the database arbitrate concurrency safely.

### 24.3. Forgetting the btree_gist Extension

Declaring `room_id WITH =` on a scalar type like `bigint` inside `USING gist` fails for lack of an operator class if `btree_gist` is not installed in that database.

Check:

```sql
SELECT extname
FROM pg_extension
WHERE extname = 'btree_gist';
```

Install the extension with proper privileges in the right database rather than trying to switch `USING gist` to `USING btree` for range overlap operators.

### 24.4. Allowing room_id or during to Be NULL

When a comparison inside `EXCLUDE` evaluates to `NULL`, the pair does not trigger a violation. Add `NOT NULL` to resource ID and range columns when required.

### 24.5. Forgetting to Check for Empty Ranges

An `empty` range never overlaps any booking. If zero-minute bookings are invalid, add `CHECK (NOT isempty(during))`—or `CHECK (start_at < end_at)` with two columns.

### 24.6. Using [] Bounds Instead of [)

If consecutive bookings both include the boundary instant 10:00, they overlap. Standardize on half-open `[)` intervals when adjacent bookings should be allowed.

### 24.7. Forgetting CANCELLED Rows in the Constraint

If canceled bookings should not block new bookings, use a partial exclusion predicate covering active statuses only. Conversely, include temporary holds like `HELD` if they must reserve the room.

### 24.8. Expecting Hold Expiration to Auto-Update a Partial Index

A `HELD` record stays inside a status-based partial index even after its expiration timestamp passes. Use an explicit workflow to expire holds, never `now()` inside an index predicate.

### 24.9. Assuming EXCLUDE Creates a Standard B-tree Index

`EXCLUDE` builds an index using the specified access method—here **GiST**. GiST handles range operators and conflict checks, not every B-tree equality or sort pattern.

### 24.10. Using DEFERRABLE Without Handling Errors at COMMIT

A deferred constraint can fail at commit time. Catching errors only around `INSERT` can miss the real failure point.

### 24.11. Failing to Distinguish SQLSTATE Codes

`23P01` is exclusion violation; `23505` is unique violation; `40001` is serialization failure; lock timeouts and deadlocks have their own codes. Never map every SQL error to “room already booked”.

### 24.12. Assuming a Partial Index Serves All Queries

The GiST index only includes rows matching the predicate. Queries including `CANCELLED` rows may need a different plan or index; do not expect the planner to use an active-only partial index for full-history scans.

### 24.13. Ignoring Partition Boundaries

When partitioned by month or day, a booking crossing a partition boundary could overlap one in another partition. Verify partitioned exclusion constraint rules for your PostgreSQL version.

### 24.14. Assuming EXCLUDE Covers the Entire Booking System

`EXCLUDE` prevents overlapping slots for a resource in one table. It does not authenticate users, block duplicate payments, sync external calendars, or cap aggregate capacity across multiple rows.

## 25. Exercises with Solutions

### Exercise 1. Which Bookings Overlap?

Given intervals:

```text
A = [09:00, 10:00)
B = [10:00, 11:00)
C = [09:59, 10:01)
D = [08:00, 09:00)
```

**Question:** which pairs overlap?

**Solution:** A and B do not overlap; A and D do not overlap; C overlaps both A and B. D and C do not overlap. Half-open `[)` notation excludes the upper bound from the earlier interval.

### Exercise 2. Why Is UNIQUE Insufficient?

Two bookings:

```text
room_id=101, [09:00,10:00)
room_id=101, [09:30,10:30)
```

**Solution:** their start/end timestamps differ, so `UNIQUE(room_id, start_at, end_at)` misses the conflict. `EXCLUDE` with `room_id WITH =` and `during WITH &&` catches it because the room matches and the intervals overlap.

### Exercise 3. Allowing Simultaneous Bookings in Two Different Rooms

**Requirement:** room 101 and room 102 can both be booked for 09:00–10:00.

**Solution:** `EXCLUDE` includes `room_id WITH =`. When rooms differ, the room comparison is FALSE, so no conflict occurs even though the time overlap is TRUE.

### Exercise 4. Does a Canceled Booking Hold the Room?

A table has partial `EXCLUDE`:

```sql
WHERE (status IN ('HELD', 'CONFIRMED'))
```

**Solution:** a `CANCELLED` row is outside this index/constraint; it does not block a new `CONFIRMED` booking for the same slot unless another active booking overlaps. However, updating that `CANCELLED` row back to `CONFIRMED` triggers constraint validation and will be rejected if an overlap exists.

### Exercise 5. Why Is NULL Dangerous?

If `room_id` permits `NULL`, two rows both have `room_id IS NULL` and overlapping intervals.

**Solution:** `NULL = NULL` is not TRUE, so `EXCLUDE` does not treat the pair as conflicting. Declare `room_id NOT NULL` or choose an appropriate non-null modeling design.

### Exercise 6. Why Is CHECK (NOT isempty(during)) Needed?

**Solution:** an empty range contains no points and never overlaps another booking. If zero-length bookings are invalid, `CHECK` blocks what `EXCLUDE` alone does not forbid.

### Exercise 7. Two Concurrent Requests Booking the Same Slot

Transactions A and B both `SELECT` 14:00–15:00 as free, then both `INSERT` overlapping bookings.

**Solution:** `SELECT` does not prevent races. `EXCLUDE` ensures both conflicting bookings cannot commit; one transaction waits, fails, or rolls back depending on execution order. The application handles `23P01` as a business conflict.

### Exercise 8. Swapping Two Bookings with DEFERRABLE

Given `A = [09:00, 10:00)` and `B = [10:00, 11:00)`, swap A and B in one transaction.

**Solution:** with `EXCLUDE ... DEFERRABLE`, call `SET CONSTRAINTS ... DEFERRED` in the transaction, update both rows, and commit. The final state has no overlaps; if a conflict remained, `COMMIT` would fail.

### Exercise 9. Choosing Between daterange and tstzrange

A system manages leave dates from Nov 14 through the end of Nov 16, ignoring time of day.

**Solution:** `daterange(DATE '2026-11-14', DATE '2026-11-17', '[)')` fits calendar-date rules better than `tstzrange`. For meetings with start/end times and timezones, `tstzrange` is usually right.

### Exercise 10. Can a Partial Predicate Reference now()?

Someone proposes:

```sql
-- Inappropriate idea for a partial index:
-- WHERE hold_expires_at > now()
```

**Solution:** index predicates require immutable expressions and cannot use volatile time functions like `now()` to “auto-expire holds” as the clock advances. Use a status column updated by a workflow in consistent transactions.

### Exercise 11. Can EXCLUDE Enforce “At Most Three Concurrent Meetings Across Rooms”?

**Solution:** not directly. `EXCLUDE` per `room_id` prevents two bookings for **the same room** from overlapping, but does not count concurrent bookings across a pool of rooms. Use a capacity model or extra coordination logic.

### Exercise 12. Which SQL Checks the Constraint Structure?

**Solution:**

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'booking_lab.reservations'::regclass
  AND contype = 'x';
```

You can also view the backing index in `pg_indexes` or run `\d+ booking_lab.reservations` in `psql`.

## 26. Quick Reference Table

| Need | Tool / Syntax | Notes |
|---|---|---|
| Represent exact instant interval | `tstzrange(start, end, '[)')` | From two `timestamptz` instants |
| Local wall-clock interval | `tsrange(start, end, '[)')` | Carries no timezone |
| Calendar date interval | `daterange(start_date, end_date, '[)')` | Discrete date range with canonicalization |
| Do two ranges overlap? | `a && b` | TRUE when intersection is non-empty |
| Are two ranges adjacent? | `a -\|- b` | Not an overlap |
| Does range contain an instant? | `a @> instant` | Useful for active schedule lookups |
| Is range empty? | `isempty(a)` | Add `CHECK` if disallowed |
| Start/end of range | `lower(a)`, `upper(a)` | May be NULL if unbounded |
| Check for unbounded ends | `lower_inf(a)`, `upper_inf(a)` | Use when business requires finite bounds |
| Inclusive start, exclusive end | `'[)'` | Adjacent bookings do not overlap |
| Same room and overlapping time | `EXCLUDE USING gist (room_id WITH =, during WITH &&)` | Needs compatible operator classes |
| `bigint` equality in GiST | `CREATE EXTENSION btree_gist` | Install in target DB with proper privileges |
| Restrict to active rows only | `WHERE (status IN (...))` | Partial exclusion constraint |
| Forbid NULL | `NOT NULL` | Avoids `UNKNOWN` comparisons letting conflicts slip through |
| Allow temporary intermediate state in tx | `DEFERRABLE` + `SET CONSTRAINTS ... DEFERRED` | Must still be valid at commit |
| Exclusion violation error | SQLSTATE `23P01` | Handle as business conflict where appropriate |
| Inspect metadata | `pg_constraint`, `pg_get_constraintdef` | `contype = 'x'` |
| Inspect index | `pg_indexes`, `\d+` | GiST index created alongside constraint |
| Find bookings overlapping proposed slot | `during && tstzrange(...)` | UI query only; does not replace `EXCLUDE` |
| Forbid `start >= end` | `CHECK (start_at < end_at)` | When using separate start/end columns |
| Forbid empty ranges | `CHECK (NOT isempty(during))` | Complements `EXCLUDE` |

## 27. Summary: Putting “No Overlap” into the Database

To prevent a resource from having overlapping time intervals, PostgreSQL provides a strong combination:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Inside CREATE TABLE or ALTER TABLE:
CONSTRAINT no_overlap
EXCLUDE USING gist (
    resource_id WITH =,
    occupied_period WITH &&
)
```

Key takeaways:

1. **`EXCLUDE`** expresses a **cross-row** comparison rule, distinct from `CHECK` (single-row conditions) and `UNIQUE` (exact key collisions).
2. **`&&`** detects intersecting intervals. Use `[)` bounds when back-to-back bookings should be allowed.
3. **GiST + `btree_gist`** is the standard pairing for combining scalar resource equality with range overlap.
4. **`NOT NULL` and empty-range checks** are vital companions; `EXCLUDE` does not block missing or zero-length values on its own.
5. **Partial exclusion** scopes checks to active rows such as `HELD`/`CONFIRMED`; status updates are enforced as well.
6. **`DEFERRABLE`** lets a transaction update multiple rows through temporary conflicts, while final committed state must still be valid.
7. **Concurrency:** two requests may both read an empty slot, but the database constraint acts as the final barrier preventing overlapping commits.
8. **Application design still matters:** enforce authorization, hold expiration workflows, SQLSTATE `23P01` handling, short transactions, proper indexes, and data hygiene.

Whenever a business rule says **“no two rows may share a grouping key and have overlapping intervals”**, `EXCLUDE USING gist` is the PostgreSQL tool built for the job—turning an error-prone, race-vulnerable application check into a **database-enforced integrity invariant**.
