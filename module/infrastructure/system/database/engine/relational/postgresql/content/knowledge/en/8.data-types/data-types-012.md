# Ranges, Multiranges, and Representing Value Intervals

An application often has to store not a single value, but **a range of values**: the time a meeting room is booked, the age bracket of a promotional campaign, the effective period of a selling price, an order quantity tier, or multiple free time slots of an employee. If you only store two columns `start` and `end`, developers have to repeatedly write conditions checking for overlap, containment, adjacency, and boundary handling. These seemingly simple conditions are prone to bugs when two intervals only touch at an endpoint, have an infinite endpoint, or split into multiple segments.

PostgreSQL provides **range types** to represent **an ordered interval over a data type**, and **multirange types** to represent **a normalized set of multiple non-empty, non-overlapping intervals**. Ranges/multiranges come with operators like `@>` (contains), `&&` (overlaps), `-|-` (adjacent), union/intersection/difference operations, GiST indexes, and `EXCLUDE` constraints. They are an essential tool when designing data with temporal or numeric-interval constraints.

This lesson walks from core concepts to practical usage: choosing a range type, `[)` boundary conventions, empty and unbounded values, how PostgreSQL canonicalizes discrete ranges, converting between ranges and multiranges, querying disjoint intervals, designing non-overlapping room booking schedules, and using indexes/constraints to protect data against concurrent writes.

> **Scope:** SQL examples target a PostgreSQL version that supports multiranges (**PostgreSQL 14 or newer**) in a test database. Some features or optimizations may vary by PostgreSQL release; operations such as `CREATE TABLE`, `ALTER TABLE`, and creating extensions require appropriate privileges. Do not deploy booking rules or pricing policies to production before clearly aligning on boundary calculations and concurrent transaction handling.

## 1. How Does a Range Differ from Two Begin/End Columns?

Suppose two meetings take place:

```text
Meeting A: 09:00 ├───────────┤ 10:00
Meeting B:                     10:00 ├───────────┤ 11:00
```

The two meetings **touch at 10:00** without overlapping if the business rule is that one meeting finishes **before** the next starts using the room.

With two `start_at`/`end_at` columns, the condition must be written carefully:

```sql
-- Two half-open intervals [start_at, end_at) overlap when:
a.start_at < b.end_at
AND b.start_at < a.end_at
```

This is an **illustrative expression**, not a complete SQL statement. If someone changes `<` to `<=`, two back-to-back schedules touching at the endpoint are treated as conflicting. If `end_at` can be `NULL` to indicate unbounded, the expression also requires special handling.

With a range:

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ) &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        TIMESTAMPTZ '2026-11-14 11:00:00+07',
        '[)'
    ) AS do_intervals_overlap;
-- false
```

The **`&&`** operator directly expresses the question **"do these two intervals share any point in common?"**. PostgreSQL understands inclusivity/exclusivity of each endpoint, reducing the chance of writing faulty boundary conditions.

### Benefits of Ranges

- **Clear semantics:** one value represents both the interval and its boundary rules.
- **Concise expressions:** `during && requested_period`, `active_period @> timestamp`.
- **Database-level constraints:** combine with `EXCLUDE USING gist` to prevent two bookings for the same room from overlapping.
- **Specialized indexing:** GiST and matching operator classes to support interval lookups.
- **Representing infinity or empty:** no need to invent sentinel values like `9999-12-31` for every case.

Importantly, a range **does not choose business rules on its own**. You still have to decide whether an interval includes its endpoints, whether empty intervals are allowed, and whether adjacent intervals count as conflicting.

## 2. Built-in Range and Multirange Types

PostgreSQL provides the following corresponding pairs of types:

| Range Type | Multirange Type | Element Type (Subtype) | Example Use Cases |
|---|---|---|---|
| `int4range` | `int4multirange` | `integer` (`int4`) | Quantity brackets, small sequence number ranges. |
| `int8range` | `int8multirange` | `bigint` (`int8`) | Large ID/number ranges. |
| `numrange` | `nummultirange` | `numeric` | Price brackets, continuous decimal-exact numeric intervals. |
| `daterange` | `datemultirange` | `date` | Holidays, effective date ranges. |
| `tsrange` | `tsmultirange` | `timestamp without time zone` | Local wall-clock times, not timezone-aware instants. |
| `tstzrange` | `tstzmultirange` | `timestamp with time zone` (`timestamptz`) | Absolute time intervals, instant-based booking schedules. |

**Multiranges were introduced in PostgreSQL 14**. If operating on an older PostgreSQL version, do not assume type names like `int4multirange`, `tstzmultirange`, or multirange operations are available.

### Which Type Should You Choose?

For a meeting room schedule with users booking across multiple time zones, prefer **`tstzrange`** to store intervals of absolute instants. For a recurring schedule like "09:00–17:00 every Monday in Berlin", you also need **time-zone-aware calendar semantics**, not just a single `tstzrange`: concrete instants must be generated from the local schedule and the IANA time zone.

For integer ranges, use `int4range`/`int8range`; for decimal quantities or continuous measurements, use `numrange`. Avoid forcing arbitrary real-number tiers into `int4range` merely for simpler syntax.

## 3. Understanding Interval Brackets

A range has a **lower bound** and an **upper bound**. Brackets indicate whether each bound is included in the interval.

| Notation | Meaning | Real-Number Interval Example |
|---|---|---|
| `[a,b]` | Includes both `a` and `b`. | \(a \le x \le b\) |
| `[a,b)` | Includes `a`, excludes `b`. | \(a \le x < b\) |
| `(a,b]` | Excludes `a`, includes `b`. | \(a < x \le b\) |
| `(a,b)` | Excludes both endpoints. | \(a < x < b\) |

For room bookings, **`[start, end)`** is usually the most convenient convention:

```text
09:00                         10:00                    11:00
  [────────── Booking A ─────────) 
                                 [──────── Booking B ────────)

10:00 belongs to Booking B; it does not belong to Booking A.
=> Two adjacent bookings, with zero overlapping duration.
```

**Do not default to closed intervals `[start,end]` for back-to-back schedules** if business rules allow the next slot to start at the exact moment the previous one ends.

### Two Ways to Create a Range

Using a **literal** with a cast:

```sql
SELECT '[1,10)'::int4range AS integer_period;

SELECT '[2026-11-14 09:00:00+07,2026-11-14 10:00:00+07)'::tstzrange
       AS meeting_period;
```

Or using a **constructor**:

```sql
SELECT int4range(1, 10, '[)') AS integer_period;

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
) AS meeting_period;
```

Constructors take **lower**, **upper**, and an optional bounds parameter; when the bounds parameter is omitted, many constructors default to `[)`. For timestamps, writing an explicit offset avoids depending on the connection's time zone.

### Questions That Must Be Agreed On Upfront

1. Is the end timestamp counted as consuming the resource?
2. Are two bookings `[09:00,10:00)` and `[10:00,11:00)` valid simultaneously?
3. Does a unit price apply up to exactly 00:00 the next day or up to 23:59:59.999?
4. Are lower and upper values allowed to be equal?
5. Can an interval remain open indefinitely or must it have an expiration date?

Ranges help express these rules, but the business team must decide the rules first.

## 4. Discrete Ranges vs. Continuous Ranges

This is a fundamental distinction: PostgreSQL **does not represent all subtypes identically**.

### 4.1. Discrete Ranges

`int4range`, `int8range`, and `daterange` have **discrete consecutive values** in their subtype. For integers, for example, there is no integer between 2 and 3.

Therefore:

```sql
SELECT int4range(1, 4, '[)') AS p1,
       int4range(1, 3, '[]') AS p2,
       int4range(2, 5, '(]') AS p3;
```

Meaning:

- `[1,4)` contains integers 1, 2, 3.
- `[1,3]` also contains 1, 2, 3.
- `(2,5]` contains 3, 4, 5.

PostgreSQL uses a **canonical form** for many discrete range types, typically normalizing to `[)`. Thus `[1,3]::int4range` is displayed identically to `[1,4)`.

```sql
SELECT '[1,3]'::int4range = '[1,4)'::int4range
       AS equal_integer_sets;
-- true
```

### 4.2. Continuous Ranges

For `numrange` or timestamp ranges, between any two values there are generally other values. Therefore:

```sql
SELECT
    '[1,3]'::numrange = '[1,3)'::numrange
        AS equal_numeric_sets;
-- false
```

The number 3 **belongs** to the first interval but **does not belong** to the second, so the two ranges are not equal. You cannot automatically turn `]` into `)` by adding 1 as with integers.

### 4.3. Dates Also Have Canonicalization

`daterange` uses `date` values that are discrete by calendar day:

```sql
SELECT
    daterange(DATE '2026-11-01', DATE '2026-11-03', '[]')
        AS inclusive_dates;
```

The interval includes November 01, 02, and 03; the canonical form is typically displayed as **`[2026-11-01,2026-11-04)`**.

**Do not apply a "plus one day" canonicalization mindset to `tstzrange`.** An instant has no "next value" like a whole day, and a local calendar day can be 23 or 25 hours long in regions observing DST.

## 5. Empty Ranges, Unbounded Ranges, and NULL Values

These three concepts are easily confused:

1. **Empty range:** has a range type but contains zero elements.
2. **Unbounded range:** has no lower bound or no upper bound.
3. **SQL NULL:** has no range value (unknown/missing), distinct from an empty range.

### 5.1. Empty Range

```sql
SELECT 'empty'::int4range AS empty_period;

SELECT isempty('empty'::int4range) AS is_empty;
-- true

SELECT int4range(5, 5, '[)') AS zero_width;
-- empty
```

A range `[5,5)` does not contain 5, so it is empty. However, a closed numeric range `[5,5]` **contains exactly one point** and is not empty:

```sql
SELECT isempty('[5,5]'::numrange) AS numeric_single_point_empty;
-- false
```

This distinction matters if you use ranges to model **exact values**. Not every range with lower = upper is empty; it also depends on the bracket types.

### 5.2. Unbounded Range

```sql
-- Unbounded below.
SELECT int4range(NULL, 10, '()') AS before_ten;

-- Unbounded above.
SELECT int4range(10, NULL, '[)') AS from_ten;

-- Unbounded on both ends.
SELECT '(,)'::numrange AS all_numeric_values;
```

In a **constructor**, passing SQL `NULL` for lower or upper represents an **unbounded end**. That is constructor semantics, distinct from storing **the entire range column as SQL NULL**.

Example:

```sql
SELECT
    int4range(10, NULL, '[)') IS NULL AS range_is_sql_null,
    int4range(10, NULL, '[)') @> 100000 AS contains_large_number;
-- false, true
```

### 5.3. Infinity Is a Different Value from Unbounded

PostgreSQL has special values `infinity` and `-infinity` for types such as `date`/`timestamp`. However, **an infinite bound is a specific subtype value**, not always the same as **a completely omitted bound**.

Example:

```sql
SELECT
    upper_inf(tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        NULL,
        '[)'
    )) AS has_unbounded_upper;
-- true
```

By contrast, an interval with upper set to `'infinity'::timestamptz` represents **a bound at the special value infinity**, and checks like `upper_inf` can behave differently. Do not use the literal `'infinity'` in place of an **unbounded** endpoint when you want SQL logic not to worry about that difference.

### 5.4. Range Columns Can Be NULL

```sql
CREATE TABLE range_null_examples (
    id INTEGER PRIMARY KEY,
    active_period TSTZRANGE
);

INSERT INTO range_null_examples VALUES
    (1, NULL),
    (2, 'empty'::tstzrange),
    (3, tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        NULL,
        '[)'
    ));
```

For row 1, `active_period IS NULL` is true. For row 2, `isempty(active_period)` is true. For row 3, `upper_inf(active_period)` is true. **These are three distinct states**.

## 6. Inspecting Endpoints and Range Properties

PostgreSQL provides helpful functions:

| Function | Purpose |
|---|---|
| `lower(range)` | Lower bound value, if present. |
| `upper(range)` | Upper bound value, if present. |
| `lower_inc(range)` | Whether the lower bound is inclusive. |
| `upper_inc(range)` | Whether the upper bound is inclusive. |
| `lower_inf(range)` | Whether the lower bound is unbounded. |
| `upper_inf(range)` | Whether the upper bound is unbounded. |
| `isempty(range)` | Whether the range is empty. |

Example:

```sql
SELECT
    lower('[2,8)'::int4range) AS min_value,
    upper('[2,8)'::int4range) AS max_bound,
    lower_inc('[2,8)'::int4range) AS include_min,
    upper_inc('[2,8)'::int4range) AS include_max,
    isempty('[2,8)'::int4range) AS empty;
```

In meaning, the result is: lower = 2, upper = 8, lower included, upper excluded, range not empty.

**Note:** `upper(range)` is **the endpoint value**, not necessarily **the largest value contained in the range**. For `int4range '[2,8)'`, upper = 8, yet the largest integer inside the range is 7.

### Why Use upper_inf Instead of Just upper IS NULL?

`upper(range)` can return SQL `NULL` either when the upper end is unbounded or when the range is empty. When you need clean classification, check **`isempty`** and **`upper_inf`** in the appropriate order instead of guessing from `upper() IS NULL`.

```sql
SELECT
    isempty('empty'::int4range) AS is_empty,
    upper_inf(int4range(5, NULL, '[)')) AS no_upper_bound;
```

When analyzing range data from multiple sources, document invariants such as "column is NOT NULL", "non-empty", and "whether upper may be unbounded" in the schema.

## 7. Key Range Operators

For ranges with compatible subtypes, PostgreSQL supports set-theoretic and ordering operators:

| Operator | Meaning | Conceptual Example |
|---|---|---|
| `@>` | Range **contains** a value or another range. | `period @> timestamp` |
| `<@` | Value/range **is contained by** a range. | `timestamp <@ period` |
| `&&` | Two ranges **overlap**. | `booking_a && booking_b` |
| `-|-` | Two ranges are **adjacent**. | `[1,3) -|- [3,6)` |
| `<<` | First range is strictly **left of** the second. | `a << b` |
| `>>` | First range is strictly **right of** the second. | `a >> b` |
| `&<` | First range does not extend to the right of the second. | Requires endpoint order awareness. |
| `&>` | First range does not extend to the left of the second. | Requires endpoint order awareness. |
| `+` | **Union** of two ranges when representable as a single range. | `[1,3) + [3,5)` |
| `*` | **Intersection** of two ranges. | `[1,5) * [3,8)` |
| `-` | **Difference** of two ranges when the result can be represented as one range. | `[1,8) - [1,3)` |

SQL examples:

```sql
SELECT
    '[1,10)'::int4range @> 5 AS contains_five,
    '[1,10)'::int4range @> '[2,5)'::int4range
        AS contains_inner_range,
    '[1,5)'::int4range && '[4,8)'::int4range
        AS overlaps,
    '[1,5)'::int4range -|- '[5,8)'::int4range
        AS adjacent,
    '[1,5)'::int4range && '[5,8)'::int4range
        AS adjacent_but_not_overlapping;
```

Results in order: **true, true, true, true, false**.

### Adjacent Ranges Do Not Mean Overlapping

```text
Range A:   [1,5)
Range B:        [5,8)
                    ▲
              touching point 5

A -|- B  → true
A && B   → false
```

This is why typical booking constraints use `&&` rather than "overlapping **or** adjacent": a schedule B starting at the exact moment schedule A ends remains valid under the `[)` convention.

### Checking That Two Ranges Do Not Overlap

```sql
SELECT NOT (
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ) &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        TIMESTAMPTZ '2026-11-14 11:00:00+07',
        '[)'
    )
) AS no_conflict;
-- true
```

When columns are SQL `NULL`, boolean expressions can also evaluate to `NULL` (unknown), **not true/false**. Therefore, for mandatory booking schedules, declare the range column **`NOT NULL`** and **non-empty**.

## 8. Union, Intersection, Difference: Operations on Single Ranges

Think of a range as the set of values it contains.

### 8.1. Union (+)

```sql
SELECT '[1,5)'::int4range + '[4,8)'::int4range
       AS union_overlapping;
-- [1,8)

SELECT '[1,5)'::int4range + '[5,8)'::int4range
       AS union_adjacent;
-- [1,8)
```

Two **overlapping or adjacent** ranges can form a single contiguous range. However, two ranges separated by a gap cannot always be merged into **one range** while preserving the exact element set:

```sql
-- For the + operator on two ranges:
-- '[1,3)'::int4range + '[6,8)'::int4range
-- can be rejected because the result consists of two disjoint segments.
```

To keep both segments, use a **multirange**; do not stretch the range to `[1,8)`, because that would accidentally include 3, 4, and 5.

### 8.2. Intersection (*)

```sql
SELECT '[1,8)'::int4range * '[5,10)'::int4range
       AS intersection;
-- [5,8)

SELECT '[1,3)'::int4range * '[5,8)'::int4range
       AS empty_intersection;
-- empty
```

Intersection returns the elements belonging to **both** ranges.

### 8.3. Difference (-)

```sql
SELECT '[1,8)'::int4range - '[1,3)'::int4range
       AS difference_contiguous;
-- [3,8)
```

However:

```text
[1,10) minus [4,6) = [1,4) and [6,10)
                     └─ two disjoint segments
```

A **single range** type cannot represent these two segments as one value; range difference raises an error when the result would split into two parts. **Multiranges solve that case**.

## 9. Multirange: A Set of Multiple Disjoint Intervals

A **multirange** stores a finite set of **non-empty, non-overlapping ranges normalized in order**. Overlapping or adjacent ranges are merged whenever they form a contiguous interval covering the same values.

Example of an employee's working hours:

```text
08:00        12:00      13:00           17:00
 [─ morning shift )      [─ afternoon shift ─)
                └─ lunch break ─┘

Cannot be represented accurately by a single tstzrange
if the lunch break in the middle must be preserved.
```

SQL example with integers:

```sql
SELECT '{[1,4),[7,10)}'::int4multirange
       AS available_numbers;
```

The multirange here contains **1,2,3,7,8,9**, and excludes 4,5,6.

### 9.1. Creating via Constructor

```sql
SELECT int4multirange(
    int4range(1,4,'[)'),
    int4range(7,10,'[)')
) AS numbers_in_two_blocks;
```

### 9.2. Empty Multirange

```sql
SELECT '{}'::int4multirange AS no_allowed_values;

SELECT int4multirange() AS no_allowed_values_from_constructor;
```

An empty multirange means **zero intervals**, not SQL `NULL`. A multirange column can be `NULL` if the schema allows it; distinguish the two cases just as with ranges.

### 9.3. Automatic Normalization on Creation

```sql
SELECT int4multirange(
    int4range(7,10),
    int4range(1,4),
    int4range(4,7)
) AS merged_ranges;
-- {[1,10)}
```

The segments `[1,4)`, `[4,7)`, and `[7,10)` are adjacent, so the multirange normalizes into **a single interval `[1,10)`**. Input order does not dictate stored element order.

**Do not rely on a multirange to record "three independent bookings."** If you need to store each booking with its actor, ID, and status, use **one row per booking**. Multiranges fit representing **merged interval sets** for calculations and display.

## 10. Operations on Multiranges

Multiranges support many operators similar to ranges, except results can have **multiple segments**.

### 10.1. Union of Two Disjoint Sets

```sql
SELECT
    '{[1,4)}'::int4multirange
    + '{[7,10)}'::int4multirange
    AS combined;
-- {[1,4),[7,10)}
```

No error occurs just because there is a gap between the two intervals.

### 10.2. Difference Can Split an Interval

```sql
SELECT
    int4multirange(int4range(1,10))
    - int4multirange(int4range(4,6))
    AS without_middle;
-- {[1,4),[6,10)}
```

This is the core example: subtraction on a **single range** cannot represent a disconnected result, whereas a **multirange** preserves both segments accurately.

### 10.3. Intersection

```sql
SELECT
    '{[1,5),[8,12)}'::int4multirange
    * '{[3,9)}'::int4multirange
    AS common_values;
-- {[3,5),[8,9)}
```

### 10.4. Containment and Overlap Checks

```sql
SELECT
    '{[1,4),[7,10)}'::int4multirange @> 2
       AS contains_two,
    '{[1,4),[7,10)}'::int4multirange @> 5
       AS contains_five,
    '{[1,4),[7,10)}'::int4multirange
       && '[3,8)'::int4range
       AS overlaps_range;
```

Results in order: **true, false, true**. Note that PostgreSQL provides operator variants supporting range/multirange combinations across operands; always ensure compatible data types.

## 11. Converting Between Ranges and Multiranges

### Single Range to Multirange

```sql
SELECT int4multirange(int4range(10,20))
       AS a_single_segment_multirange;
-- {[10,20)}
```

### Multirange into Individual Segments

`unnest(multirange)` returns the component ranges:

```sql
SELECT segment
FROM unnest(
    '{[1,4),[7,10)}'::int4multirange
) AS t(segment);
```

The result has **two rows**, `[1,4)` and `[7,10)` respectively. This is useful for turning a set of free intervals into a list of time slots for a UI.

### Taking the Convex Hull: range_merge()

`range_merge(multirange)` produces the **smallest single range spanning all segments**:

```sql
SELECT range_merge(
    '{[1,4),[7,10)}'::int4multirange
) AS bounding_range;
-- [1,10)
```

**Crucial:** `range_merge` **does not preserve gaps**. The result `[1,10)` includes 4, 5, and 6, which **did not belong** to the original multirange. Use this function when you need a **bounding interval**, not to answer "which values are permitted".

### Aggregating Ranges into a Multirange

`range_agg(range)` aggregates multiple ranges into one multirange:

```sql
WITH intervals(period) AS (
    VALUES
      ('[1,4)'::int4range),
      ('[3,6)'::int4range),
      ('[9,12)'::int4range)
)
SELECT range_agg(period) AS merged_periods
FROM intervals;
-- {[1,6),[9,12)}
```

Typical use case: aggregating confirmed bookings into a single **busy time** set after filtering by room/day, then subtracting it from the available time window.

## 12. Working with Time Intervals and Time Zones

When designing temporal data, distinguish **local wall-clock times** from **absolute instants**:

- `tsrange` holds `timestamp without time zone`. It has no inherent knowledge of whether a timestamp is UTC+7 or UTC+1.
- `tstzrange` holds `timestamptz`. PostgreSQL represents specific **instants** and displays them in the session's time zone.
- `daterange` holds **calendar dates**, suitable for date-based effective policies.

### Two Ranges Covering the Same Instants Can Display Differently

```sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
) AS vietnam_display;

SET TIME ZONE 'UTC';

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 02:00:00+00',
    TIMESTAMPTZ '2026-11-14 03:00:00+00',
    '[)'
) AS utc_display;

RESET TIME ZONE;
```

Both values have the exact same absolute start/end instants; their text display varies according to `TimeZone`.

### A "Local Day" Is Not Always 24 Hours

In regions with Daylight Saving Time (DST), a calendar day can be 23 or 25 hours long. When constructing an interval for a local day in a region, **convert each midnight timestamp to an instant** rather than blindly adding 24 hours to the start of the day.

Example creating the interval for November 14 in Vietnam time:

```sql
SELECT tstzrange(
    TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    '[)'
) AS local_calendar_day;
```

If the problem only involves dates (e.g., a contract effective from November 01 through November 14), `daterange` can be clearer than `tstzrange`:

```sql
SELECT daterange(
    DATE '2026-11-01',
    DATE '2026-11-15',
    '[)'
) AS effective_dates;
```

The interval above covers November 01 through November 14. Do not invent `23:59:59.999999` as "end of day" because precision, data types, and time zones can change.

## 13. Designing a Booking Table with tstzrange

A room booking system needs these invariants:

1. A booking has a **non-empty** time interval.
2. Two `CONFIRMED` bookings **for the same room** must not overlap.
3. Bookings for **different rooms** may overlap in time.
4. `CANCELLED` bookings do not occupy the room.
5. Two schedules for the same room can be **adjacent** if the end timestamp is excluded from the earlier booking.

Schema:

```sql
CREATE TABLE meeting_rooms (
    room_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_code TEXT NOT NULL UNIQUE
);

CREATE TABLE room_bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL REFERENCES meeting_rooms(room_id),
    booked_period TSTZRANGE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    booked_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_booking_nonempty
        CHECK (NOT isempty(booked_period)),

    CONSTRAINT chk_booking_bounded
        CHECK (
            NOT lower_inf(booked_period)
            AND NOT upper_inf(booked_period)
        ),

    CONSTRAINT chk_booking_half_open
        CHECK (
            lower_inc(booked_period)
            AND NOT upper_inc(booked_period)
        )
);
```

In this example, the system **does not allow open-ended bookings**, because meeting rooms require concrete start and end times. `lower_inf/upper_inf` reject unbounded endpoints; the `[)` rule indicates a booking ends upon reaching its upper boundary.

**Note:** A different business case such as an open-ended effective price **should not reuse `chk_booking_bounded`**. Good range schemas reflect each domain's invariants rather than copying every constraint across all interval types.

### Insert Two Rooms

```sql
INSERT INTO meeting_rooms(room_code)
VALUES ('A-101'), ('B-201')
RETURNING room_id, room_code;
```

In the following examples, assume room `A-101` has `room_id = 1`; in a database with existing rows or an already-advanced sequence, use **the actual ID returned by RETURNING**.

### Insert the First Booking

```sql
INSERT INTO room_bookings(
    room_id, booked_period, status, booked_by
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ),
    'CONFIRMED',
    'user-100'
);
```

At this point, the schema guarantees non-empty, bounded ranges, but **does not yet have an anti-overlap constraint**. The next section adds that database-level constraint.

## 14. EXCLUDE USING gist: Preventing Overlapping Bookings

Simply running a `SELECT` overlap check before `INSERT` **is not safe** under concurrent requests:

```text
Transaction A                     Transaction B
     │                                 │
     ▼                                 ▼
Check room availability           Check room availability
     │                                 │
Neither sees the other's new row  Neither sees the other's new row
     │                                 │
INSERT booking A                 INSERT booking B
     └─────────────┬───────────────────┘
                   ▼
          Can double-book
          without concurrency protection
```

PostgreSQL provides **exclusion constraints** to prevent two rows from simultaneously satisfying forbidden comparisons.

### 14.1. btree_gist for room_id

To combine `room_id WITH =` with `booked_period WITH &&` inside a GiST index, you typically use an extension:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

`btree_gist` provides GiST operator classes for many scalar types, enabling `=` on `BIGINT` inside an exclusion constraint. Installing extensions requires appropriate privileges, and managed PostgreSQL services may have specific extension policies.

### 14.2. Creating the Anti-Overlap Constraint

```sql
ALTER TABLE room_bookings
ADD CONSTRAINT ex_confirmed_room_time_no_overlap
EXCLUDE USING gist (
    room_id WITH =,
    booked_period WITH &&
)
WHERE (status = 'CONFIRMED');
```

Meaning:

- Two rows with the **same `room_id`** and **overlapping `booked_period`** cannot both satisfy `status = 'CONFIRMED'`.
- Two rows with **different `room_id`** values can share the same time.
- Two **adjacent** bookings do not overlap when both use `[)`.
- Bookings in `PENDING` or `CANCELLED` state are not excluded by this partial constraint under the same rule.

If you add this constraint to a table that already contains **violating data**, the statement will fail. Before deploying, inspect historical data and evaluate GiST index build time and locking during schema changes.

### 14.3. Testing a Rejected Booking

```sql
INSERT INTO room_bookings(
    room_id, booked_period, status, booked_by
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30:00+07',
        TIMESTAMPTZ '2026-11-14 10:30:00+07',
        '[)'
    ),
    'CONFIRMED',
    'user-101'
);
```

If the 09:00–10:00 booking already exists and the constraint is active, PostgreSQL rejects this with **SQLSTATE `23P01` — `exclusion_violation`**.

A Java application can inspect `SQLException.getSQLState()` to translate this error into "The room is already booked during the requested time." However, if the database has multiple exclusion constraints, also inspect the **constraint name** to map to the right business message.

### 14.4. Testing an Adjacent Booking

```sql
INSERT INTO room_bookings(
    room_id, booked_period, status, booked_by
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        TIMESTAMPTZ '2026-11-14 11:00:00+07',
        '[)'
    ),
    'CONFIRMED',
    'user-102'
);
```

The new booking starts at exactly 10:00, so it **does not overlap** with 09:00–10:00. Provided there are no other conflicts, it is permitted.

### 14.5. Status Updates Are Also Protected

If an overlapping `PENDING` booking already exists, changing its status to `CONFIRMED` must also satisfy the exclusion constraint. This is a major advantage: **the constraint protects both INSERT and UPDATE**, not just the creation API path.

### 14.6. Exclusion Constraints Do Not Replace Other Business Logic

The constraint does not automatically know:

- Whether a room requires a break between two schedules.
- Whether staff need 15 minutes to clean the room.
- Whether bookings are restricted to working shifts or blocked on holidays.
- Whether one user is allowed to book two rooms simultaneously.

If a **15-minute buffer** is required, you can design a separate occupied interval including the buffer or expand the constraint expression using deterministic rules. Do not arbitrarily alter `&&` logic before agreeing on how buffers interact with timestamps and time zones.

## 15. Querying Conflicting Schedules and Booking Safely

To find confirmed bookings overlapping a requested interval:

```sql
SELECT
    booking_id,
    room_id,
    booked_period,
    booked_by
FROM room_bookings
WHERE room_id = 1
  AND status = 'CONFIRMED'
  AND booked_period && tstzrange(
      TIMESTAMPTZ '2026-11-14 09:30:00+07',
      TIMESTAMPTZ '2026-11-14 10:30:00+07',
      '[)'
  );
```

This query helps **show why a booking conflicts**, but the application must never treat "SELECT returned zero rows" as an absolute guarantee that the subsequent INSERT will succeed.

### Safe Workflow

1. Client submits start/end times with normalized offsets or time zone.
2. Application validates `start < end`, booking permissions, and business conditions.
3. Application sends `INSERT` to PostgreSQL within an appropriate transaction.
4. PostgreSQL enforces `EXCLUDE`; under contention, one transaction may wait and then be rejected.
5. On receiving `23P01`, the application returns a schedule-conflict response, optionally showing the conflicting booking.
6. Only report booking success after the transaction has actually committed.

**Note:** `ON CONFLICT DO UPDATE` does not support using an exclusion constraint as an arbiter in the same way as a unique constraint. Do not assume schedule conflicts can be resolved with a simple upsert statement.

### Why Is GiST Suitable?

GiST (*Generalized Search Tree*) is an indexing framework supporting many search strategies, including range operator classes. An `EXCLUDE USING gist` constraint leverages fast lookups for intervals satisfying `&&`, whereas a standard B-tree excels at scalar comparisons and cannot directly replace all interval-overlap queries.

When diagnosing query latency, inspect the execution plan:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT booking_id
FROM room_bookings
WHERE room_id = 1
  AND status = 'CONFIRMED'
  AND booked_period && tstzrange(
      TIMESTAMPTZ '2026-11-14 08:00:00+07',
      TIMESTAMPTZ '2026-11-14 12:00:00+07',
      '[)'
  );
```

`EXPLAIN ANALYZE` actually executes the query; a `SELECT` example only reads, though you should consider the impact when applying it to write statements or heavy workloads. PostgreSQL may pick a sequential scan on small tables; that alone is not evidence of a broken index.

## 16. Computing Busy and Free Intervals with Multiranges

A common requirement: **"Within the 08:00–18:00 window, which intervals is the room still free?"**

Suppose there are two bookings:

```text
08:00      09:00       10:00     11:00         13:00      18:00
 [──────────┬───────────┬─────────┬────────────┬───────────)
            [─ booking 1─)       [ booking 2 ─)

Free intervals = [08:00,09:00)
               + [10:00,11:00)
               + [13:00,18:00)
```

In SQL, aggregate the bookings with **`range_agg`**, then **subtract from the search window**.

```sql
WITH requested AS (
    SELECT tstzrange(
        TIMESTAMPTZ '2026-11-14 08:00:00+07',
        TIMESTAMPTZ '2026-11-14 18:00:00+07',
        '[)'
    ) AS search_period
),
busy AS (
    SELECT COALESCE(
        range_agg(b.booked_period * r.search_period),
        '{}'::tstzmultirange
    ) AS occupied
    FROM requested AS r
    LEFT JOIN room_bookings AS b
      ON b.room_id = 1
     AND b.status = 'CONFIRMED'
     AND b.booked_period && r.search_period
)
SELECT
    tstzmultirange(r.search_period) - busy.occupied AS free_periods
FROM requested AS r
CROSS JOIN busy;
```

Explanation:

1. `requested` defines **a search time window**.
2. `booked_period * search_period` takes the intersection, discarding parts of bookings outside the window.
3. `range_agg` merges occupied intervals into a normalized multirange.
4. `COALESCE(..., '{}'::tstzmultirange)` handles the case with no bookings.
5. `tstzmultirange(search_period) - occupied` returns the set of free segments.

Note on `LEFT JOIN`: if there are no matching bookings, `booked_period * search_period` evaluates to SQL `NULL`; aggregates ignore null inputs and `COALESCE` produces an empty multirange.

### Turning the Result into Displayable UI Rows

```sql
WITH requested AS (
    SELECT tstzrange(
        TIMESTAMPTZ '2026-11-14 08:00:00+07',
        TIMESTAMPTZ '2026-11-14 18:00:00+07',
        '[)'
    ) AS search_period
),
busy AS (
    SELECT COALESCE(
        range_agg(b.booked_period * r.search_period),
        '{}'::tstzmultirange
    ) AS occupied
    FROM requested AS r
    LEFT JOIN room_bookings AS b
      ON b.room_id = 1
     AND b.status = 'CONFIRMED'
     AND b.booked_period && r.search_period
),
free AS (
    SELECT tstzmultirange(r.search_period) - b.occupied AS periods
    FROM requested AS r
    CROSS JOIN busy AS b
)
SELECT lower(slot) AS free_from,
       upper(slot) AS free_to
FROM free
CROSS JOIN LATERAL unnest(free.periods) AS t(slot)
ORDER BY free_from;
```

This example illustrates availability calculation. If the business requires a **minimum duration of 30 minutes**, add the filter `upper(slot) - lower(slot) >= INTERVAL '30 minutes'`. Under concurrent booking changes, a read query only sees a **snapshot at query time**; successful booking still depends on write-time constraints.

## 17. Designing Effective Price Periods

Ranges are also very useful for price history and pricing policies. Suppose a product has multiple price periods:

```sql
CREATE TABLE product_prices (
    price_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    valid_period TSTZRANGE NOT NULL,
    CONSTRAINT chk_price_nonempty CHECK (NOT isempty(valid_period))
);
```

Insert two versions:

```sql
INSERT INTO product_prices(product_id, price, valid_period)
VALUES
  (42, 100000, tstzrange(
      TIMESTAMPTZ '2026-11-01 00:00:00+07',
      TIMESTAMPTZ '2026-11-10 00:00:00+07',
      '[)'
  )),
  (42, 115000, tstzrange(
      TIMESTAMPTZ '2026-11-10 00:00:00+07',
      NULL,
      '[)'
  ));
```

Fetch the active price at timestamp T:

```sql
SELECT product_id, price, valid_period
FROM product_prices
WHERE product_id = 42
  AND valid_period @>
      TIMESTAMPTZ '2026-11-12 09:00:00+07';
```

To prohibit two overlapping prices, you can add:

```sql
-- Only use when the btree_gist extension is ready.
ALTER TABLE product_prices
ADD CONSTRAINT ex_price_no_overlap
EXCLUDE USING gist (
    product_id WITH =,
    valid_period WITH &&
);
```

Here there is **no status filter** like in bookings: all price versions for the same product must be non-overlapping. If prices also have `currency`, `region`, or `channel`, the constraint's logical key may need to include those dimensions so that **two prices in different markets are not treated as conflicting**.

### Closing the Old Interval and Opening the New One

When updating a price, pick **a single timestamp T** and use it inside one transaction for both steps:

```sql
BEGIN;

-- Application needs a locking protocol on product_id
-- when multiple writers modify the same timeline.
UPDATE product_prices
SET valid_period = tstzrange(
    lower(valid_period),
    TIMESTAMPTZ '2026-11-15 09:00:00+07',
    '[)'
)
WHERE product_id = 42
  AND upper_inf(valid_period);

INSERT INTO product_prices(product_id, price, valid_period)
VALUES (
    42, 120000,
    tstzrange(
        TIMESTAMPTZ '2026-11-15 09:00:00+07',
        NULL,
        '[)'
    )
);

COMMIT;
```

**This example assumes** there is exactly one open-ended price version, no other future scheduled versions, and T lies after the open version's lower bound. In production, you need:

- Locking per `product_id` or an appropriate serialization/optimistic concurrency mechanism.
- Checking the updated row count; do not accidentally insert a new price when there was no old version to close.
- Guarding against retroactive edits or already scheduled versions.
- Relying on `EXCLUDE` as the final safeguard against overlap.

An exclusion constraint prevents **overlaps**, but **does not automatically guarantee there are no gaps** between price versions. If the business requires continuity, additional checks are necessary.

## 18. Range Column and Schema Naming Should Express Business Meaning

Do not name every column `range` or `period` and force readers to guess what it means:

| Need | Suggested Name | Appropriate Type |
|---|---|---|
| Room booking schedule | `booked_period` | `tstzrange` |
| Contract effective date range | `effective_dates` | `daterange` |
| Discount amount bracket | `discount_amount_range` | `numrange` |
| Item quantity bracket | `quantity_range` | `int4range` or `int8range` |
| Multiple free time slots | `available_periods` | `tstzmultirange` |
| Accepted age brackets | `accepted_ages` | `int4multirange` |

When a multirange represents **currently allowed segments**, name it `allowed_ranges`/`available_periods`; when it represents **blocked segments**, use `blocked_ranges`/`occupied_periods`. Clear naming prevents sign errors when taking complements.

### Range Columns via Generated Expressions

If a legacy schema has two columns `valid_from` and `valid_to`, you can create an **expression index** on `tstzrange(valid_from, valid_to, '[)')` instead of forcing the entire application to migrate immediately to a single range column:

```sql
CREATE TABLE legacy_price_periods (
    price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX ix_legacy_price_period_gist
ON legacy_price_periods
USING gist (
    tstzrange(valid_from, valid_to, '[)')
);
```

Queries using the exact same range expression can take advantage of the matching index:

```sql
SELECT *
FROM legacy_price_periods
WHERE tstzrange(valid_from, valid_to, '[)')
      @> TIMESTAMPTZ '2026-11-14 10:00:00+07';
```

This design enables **incremental migration**, though if multiple applications write to the two legacy columns, boundary conventions must stay consistent and an overlap constraint is still needed if required by business rules.

## 19. GiST, SP-GiST, and Measuring Performance

PostgreSQL supports different index access methods. For ranges, **GiST** is a key choice because it supports many range relation operators, especially for `EXCLUDE`. Some range types and operator classes also support **SP-GiST** to optimize applicable queries. Exact capabilities should be verified against your PostgreSQL version and type.

### GiST Index for Overlap Queries

```sql
CREATE INDEX ix_product_prices_period
ON product_prices
USING gist(valid_period);
```

Query:

```sql
SELECT price_version_id, product_id, price
FROM product_prices
WHERE valid_period &&
      tstzrange(
          TIMESTAMPTZ '2026-11-01 00:00:00+07',
          TIMESTAMPTZ '2026-12-01 00:00:00+07',
          '[)'
      );
```

With `EXCLUDE USING gist`, PostgreSQL also creates an index backing the constraint; **do not blindly add another GiST index on the exact same columns** if it merely duplicates search capability, because every extra index adds storage, WAL volume, and write overhead.

### Is B-tree Still Useful?

Yes. For instance, queries filtering **by product** and **sorting by `lower(valid_period)`** may benefit from a B-tree or corresponding expression index depending on the workload. GiST focuses on interval relation operators and does not replace every B-tree sort/range scan use case.

A table might have:

- A GiST/exclusion index to prevent overlaps.
- A B-tree on `product_id` for joins and ID lookups.
- An additional index on `lower(valid_period)` when historical queries truly demand it.

Only add indexes after measuring cost and selectivity.

### Reading Execution Plans

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT booking_id
FROM room_bookings
WHERE room_id = 1
  AND status = 'CONFIRMED'
  AND booked_period && tstzrange(
      TIMESTAMPTZ '2026-11-14 09:00:00+07',
      TIMESTAMPTZ '2026-11-14 12:00:00+07',
      '[)'
  );
```

When a table is very small, PostgreSQL may prefer a sequential scan; that is not a bug. As the table grows, examine actual row counts, buffer hits/reads, selectivity, and write performance. Statistics from `ANALYZE`/autovacuum give the planner the information it needs to pick plans.

## 20. Multiranges and Availability Are Not Per-Booking History

Suppose an employee has available time slots:

```sql
CREATE TABLE staff_availability (
    staff_id BIGINT PRIMARY KEY,
    free_periods TSTZMULTIRANGE NOT NULL
);
```

A multirange can represent multiple free blocks across a week. However, when a slot is booked:

```sql
UPDATE staff_availability
SET free_periods =
      free_periods
      - tstzmultirange(
          tstzrange(
              TIMESTAMPTZ '2026-11-14 09:00:00+07',
              TIMESTAMPTZ '2026-11-14 10:00:00+07',
              '[)'
          )
        )
WHERE staff_id = 101;
```

Such an `UPDATE` can split one large block into two remaining free segments. Yet **it is not enough to record** who booked, the booking ID, status, edit count, or cancellation reason.

For real-world booking schedules, you should usually:

1. Store **each booking in its own table** with keys and metadata.
2. Use an `EXCLUDE` constraint on bookings to prevent conflicts.
3. Compute multiranges of busy/free time for queries, reporting, and UIs.
4. If storing a free multirange as a cache/materialized state, define a mechanism to synchronize it with the booking table in the same transaction or via a consistent process.

**A multirange is an interval-set representation**; it does not replace event records or relationships between bookings and users.

## 21. Concurrency Control and Transactions with Range Data

Ranges and multiranges do not remove the need for **transaction concurrency** management.

### Check-Then-Write Can Race

Two transactions at `READ COMMITTED` both run `SELECT ... WHERE booked_period && requested` and neither sees the other's uncommitted booking. With only application-level checks, both can insert overlapping rows.

An `EXCLUDE` constraint in PostgreSQL pushes the **no-overlap** invariant down into the database. Under contention, the conflicting operation waits and is ultimately rejected.

### What to Do When Hitting an Exclusion Error?

- Check SQLSTATE **`23P01`**.
- Roll back the failed transaction via JDBC/Spring transaction handling.
- Optionally display the conflicting slot and suggest alternative times.
- Do not infinitely retry the same slot if someone else has already confirmed it.
- If the business genuinely permits multiple bookings in one room up to `capacity > 1`, `EXCLUDE room_id WITH =` is **too strict**; a different capacity model is needed.

### Transactions Creating/Updating Schedules

For operations spanning a booking, invoice, and outbox message, place all database writes that must succeed together inside **one transaction**:

```text
BEGIN
  ├── INSERT booking (range)
  ├── INSERT payment intent / hold record
  ├── INSERT outbox event
COMMIT
```

If the booking fails with `23P01`, all writes in the same transaction must roll back to avoid creating an invoice for an invalid booking.

### When Extra Locking Is Needed

`EXCLUDE` enforces the overlap condition; it **does not automatically manage** rules such as daily booking limits, guest counts, or milestone pricing. You may need row locks on the room/resource or optimistic locking to guard additional invariants, while avoiding holding transactions open across slow network or external API calls.

## 22. Defining Custom Range Types

Beyond built-in types, PostgreSQL lets you define **custom range types** over any suitably ordered subtype using `CREATE TYPE ... AS RANGE`.

A conceptual example:

```sql
CREATE TYPE custom_numeric_range AS RANGE (
    subtype = numeric
);
```

This creates a range type over `numeric`, though in almost all ordinary applications, **the built-in `numrange` is sufficient**. Creating a custom range type should have a clear reason:

- A specialized subtype with no built-in range type.
- Appropriate comparison rules and B-tree operator class.
- Potential need for a canonicalization function, subtype difference function, or collation/opclass configuration for efficiency.
- Compatibility across schema migrations, extensions, and applications must be managed.

### Multiranges for Custom Ranges

When defining a custom range type in PostgreSQL versions supporting multiranges, there is a mechanism that creates an associated multirange name/type. If strict system integration is required, check `multirange_type_name` syntax and the actual type name created on your exact PostgreSQL version rather than guessing a concatenated name.

### Canonical Functions Matter for Discrete Subtypes

For custom discrete types, two intervals written with different brackets can describe **the exact same set of elements**. An appropriate canonicalization function normalizes the representation; designing it improperly can cause subtle bugs when comparing or merging ranges.

This topic belongs to PostgreSQL type extensibility and requires deep understanding of subtype ordering; do not create a custom type merely to store date or integer intervals already covered by built-in types.

## 23. A Multirange Is Not an Array of Ranges

You can store `int4range[]` as an **array of ranges**, but it is **different from** `int4multirange`.

| Aspect | `int4range[]` | `int4multirange` |
|---|---|---|
| Nature | An array storing range elements in array order. | A normalized set of intervals. |
| Overlapping intervals | Two overlapping elements can coexist. | Merged into non-overlapping segments. |
| Adjacent intervals | Can remain two separate elements. | Can be merged into a single segment. |
| Set operations | Usually requires manual per-element processing. | Built-in multirange `+`, `*`, `-` operators and containment/overlap checks. |
| Per-segment metadata | Could structure per element, though does not directly hold actor/ID relations. | Does not preserve booking/source identity of individual segments. |

Example:

```sql
SELECT ARRAY[
    '[1,5)'::int4range,
    '[4,8)'::int4range
] AS range_array;

SELECT int4multirange(
    '[1,5)'::int4range,
    '[4,8)'::int4range
) AS normalized_multirange;
-- {[1,8)}
```

If you need **individual event identity**, store separate rows in a relational table; if you need **a set of values covered by multiple segments**, a multirange is the more direct choice.

## 24. NULL, Empty, and Data Rules in Applications

Design clear API semantics for these cases:

- **No interval supplied:** SQL `NULL` → request is missing information or unspecified.
- **No valid interval exists:** `empty` range or `{}` multirange → truly empty set.
- **Interval has started with unknown end:** upper unbounded.
- **Single-point interval:** only valid for specific bracket/subtype combinations, e.g. `[5,5]::numrange`.
- **Interval ending before it begins:** must be rejected as invalid input.

Example constraints:

```sql
CREATE TABLE promotion_windows (
    promotion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    active_period TSTZRANGE NOT NULL,
    CONSTRAINT chk_promotion_period_nonempty
        CHECK (NOT isempty(active_period)),
    CONSTRAINT chk_promotion_starts_at_a_real_instant
        CHECK (NOT lower_inf(active_period))
);
```

This pattern allows **an unbounded end** because a promotion might not yet have an end date, while requiring a concrete start instant.

### A CHECK Constraint Evaluates to UNKNOWN if the Column Is NULL

In SQL, a standard `CHECK` treats **false** as a violation; **NULL/unknown** does not trigger a violation. Therefore `CHECK (NOT isempty(active_period))` **does not replace** `active_period NOT NULL`.

That is why you should combine them:

```sql
active_period TSTZRANGE NOT NULL,
CHECK (NOT isempty(active_period))
```

These two layers express two distinct invariants.

## 25. Common Pitfalls

### 25.1. Confusing `[)` with `[]` on End Dates

With `daterange('2026-11-01','2026-11-10','[)')`, **November 10 is not included in the range**. If business rules intend to include the 10th, use **November 11** as the upper bound under half-open semantics, or choose the appropriate representation and canonicalization.

### 25.2. Assuming upper() Is the Last Value Actually in the Range

`upper('[1,4)'::int4range) = 4`, yet the range only contains 1, 2, 3. Do not treat `upper` as "max included value" without checking `upper_inc` and the subtype.

### 25.3. Merging Two Disjoint Ranges into One Large Range

`[1,4)` and `[7,10)` cannot be accurately combined into `[1,10)`: values 4, 5, 6 would be added. Use a **multirange** to preserve gaps.

### 25.4. Confusing an Empty Range with NULL

`'empty'::int4range` is still a typed value; `NULL::int4range` is a missing value. Check `isempty` and `IS NULL` separately.

### 25.5. Confusing `infinity` with an Unbounded Bound

`'infinity'::timestamptz` is a special subtype value; an **unbounded** upper via constructor `NULL` means no bound. When logic needs to detect missing bounds, use `upper_inf`.

### 25.6. Checking Overlap Only with SELECT Before INSERT

Two transactions can both read "no conflicting booking" and both insert. Use **`EXCLUDE USING gist`** to enforce the invariant in the database, then handle `23P01`.

### 25.7. Using Timestamp Without Time Zone Ranges for Global Schedules

`tsrange` carries no time zone information. For instant-based schedules spanning multiple regions, `tstzrange` is usually more suitable, alongside geographic region metadata if business rules require local calendar schedules.

### 25.8. Using range_merge as the Set of Free Intervals

`range_merge('{[1,4),[7,10)}'::int4multirange)` yields `[1,10)`, which swallows the gap. It returns the **convex hull**, discarding disjointness.

### 25.9. Assuming an Exclusion Constraint Guarantees No Gaps

A `WITH &&` constraint forbids overlaps, but **does not enforce continuity**. If a pricing timeline must have zero gaps, add write rules and gap checks.

### 25.10. Thinking Individual Bookings Can Be Replaced by One Multirange

A multirange cannot store booking IDs, actors, statuses, or per-segment event details. Transactional data still needs a booking table with one row per booking.

### 25.11. Adding Too Many Indexes Without Measuring Workload

GiST/exclusion indexes and extra B-tree/GIN/BRIN indexes all increase write cost, WAL volume, and storage. Use `EXPLAIN`, metrics, and actual query patterns to decide.

### 25.12. Ignoring Concurrency When Updating Prices

If multiple workers modify price intervals, the two steps "close old version" and "open new version" must share a transaction; apply entity locking or an appropriate concurrency mechanism, combined with `EXCLUDE`.

## 26. Practice Exercises

### Exercise 1 — Reading Bounds

Given the intervals:

```text
[1,5)
(1,5]
[1,5]
(1,5)
```

Determine for **`numrange`** whether 1 and 5 belong to each interval. Then explain why `int4range(1,4,'[)')` and `int4range(1,3,'[]')` represent the exact same set of integers.

### Exercise 2 — Empty, NULL, and Unbounded

Write SQL to construct:

1. An empty `int4range`.
2. An `int4range` from 10 upward, unbounded above.
3. A SQL `NULL` value of type `int4range`.

Write the corresponding `isempty`, `upper_inf`, and `IS NULL` checks, and explain why they differ.

### Exercise 3 — Overlap and Adjacency Checks

Given `A=[1,4)`, `B=[4,7)`, `C=[3,5)` as `int4range`. Predict `A && B`, `A -|- B`, `A && C`, and `A @> 3`. Verify with SQL.

### Exercise 4 — Multirange Difference

Compute with SQL:

```text
Allowed = [1,20)
Blocked = [4,7) ∪ [12,15)
Free = Allowed - Blocked
```

Explain why `Free` requires a **multirange** and how to use `unnest` to return each free segment as a separate row.

### Exercise 5 — daterange Canonicalization

Write two equivalent `daterange` values covering December 01 through December 07, 2026, one using `[]` and one using `[)`. Compare them with `=` and observe the range string displayed by PostgreSQL.

### Exercise 6 — Non-Overlapping Room Bookings

Create `rooms` and `bookings` tables with `room_id` and `during tstzrange`. Add `btree_gist` and an exclusion constraint applying only to bookings with status `CONFIRMED`. Prove that:

- Bookings 09:00–10:00 and 10:00–11:00 can coexist.
- A 09:30–10:30 booking for the same room is rejected with `23P01`.
- Two overlapping bookings for **different rooms** are allowed.

### Exercise 7 — Computing Free Availability

Within the 08:00–18:00 window, existing bookings are 09:00–10:00 and 11:00–13:00. Use `range_agg`, `tstzmultirange`, and subtraction to return free intervals. Use `unnest` to return individual slots, filtering to only slots at least 45 minutes long.

### Exercise 8 — Time-Based Pricing Design

Product A has price 100 until November 10 and price 120 starting November 10. Design `valid_period tstzrange`, write SQL to query the price on November 09 and at the exact price-change timestamp, and specify the mechanism preventing two prices from overlapping.

Also note how to keep **the reason for the change** if auditing is required, because the range itself does not record who changed the price.

### Exercise 9 — Choosing the Data Type

Pick one of `daterange`, `tsrange`, `tstzrange`, `int4range`, `numrange`, `tstzmultirange` for:

- A quantity bracket eligible for discount.
- A valid weight range.
- Contract effective calendar dates.
- A meeting with participants across multiple time zones.
- A set of three non-contiguous free time blocks.

Explain each choice and its boundary convention.

### Exercise 10 — Race Condition When Creating Bookings

Two concurrent Java requests check that a room is free and then insert overlapping bookings. Analyze why a `SELECT` before `INSERT` is insufficient under standard isolation levels. Propose transactions and `EXCLUDE`, how to catch `23P01`, and how to respond to the user.

### Exercise 11 — Indexes and Queries

For a schedule table with millions of bookings, design a query fetching bookings overlapping a time window and explain GiST's role. Explain why PostgreSQL may still choose a sequential scan for very small tables and why you should avoid adding duplicate indexes duplicating the GiST index of an exclusion constraint.

### Exercise 12 — Multirange vs. Multiple Rows?

An employee works three shifts, each approved by a different manager. Contrast using **multiple shift rows** to store metadata with using a **multirange** to compute total approved intervals. If the second shift is cancelled, how do you update the source data and recompute the working-time set?

## Conclusion

**Ranges** represent single intervals with explicit endpoint rules; **multiranges** represent normalized sets of multiple intervals, preserving **gaps** that a single range cannot represent. Built-in types such as `int4range`, `daterange`, `tstzrange`, and their multirange counterparts let you model value brackets, effective periods, booking schedules, and free time windows with concise, expressive operations.

In practice, prioritize understanding **`[)`, discrete/continuous boundaries, empty, SQL NULL, and unbounded bounds** accurately. Use `@>` for containment, `&&` for overlap, `-|-` for adjacency, and `range_agg` / `unnest` to aggregate and split disjoint segments. **`range_merge`** only produces the convex hull and loses gap information, so use it only for its intended purpose.

In real designs, a range column **does not protect against concurrent conflicts on its own** if the application only checks with `SELECT`. Combine **`EXCLUDE USING gist`, transactions, non-empty constraints, suitable indexes, and SQLSTATE `23P01` handling** to keep data accurate under contention. Use multiranges as **interval-set representations**, while keeping separate relational tables when individual bookings or events need identity, status, and history. That is how interval theory translates into clean, efficiently queryable, and operationally safe PostgreSQL designs.
