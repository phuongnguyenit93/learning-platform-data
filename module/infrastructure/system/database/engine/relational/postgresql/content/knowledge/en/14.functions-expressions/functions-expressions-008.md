# Range Operators and Functions in PostgreSQL

A room-booking system needs to know whether two reservations **overlap in time**. A pricing system must find which price rule **is active on a transaction date**. A warehouse system stores lot number intervals, and an authorization service checks whether an instant falls within a permission grant window.

If you only store two separate columns `start_at` and `end_at`, applications have to write multiple comparison conditions manually and agree on **closed bounds** (inclusive of boundary values) versus **open bounds** (exclusive). PostgreSQL provides **range types** along with dedicated operators and functions to express this directly:

- `@>`: range **contains** a value or another range.
- `<@`: value/range **is contained by** another range.
- `&&`: two ranges **overlap** (share at least one element).
- `-|-`: two ranges are **adjacent** without overlapping.
- `+`, `*`, `-`: **union, intersection, and difference** of ranges, with important limitations to understand.
- `lower()`, `upper()`, `lower_inc()`, `upper_inc()`, `lower_inf()`, `upper_inf()`, `isempty()`: inspect **both bounds** and empty/unbounded state.
- **Multiranges** (PostgreSQL 14+) to represent **multiple non-contiguous ranges** in one value, along with `range_agg()`, `range_intersect_agg()`, and `range_merge()` for aggregation.

This lesson belongs to the **Functions and Expressions** chapter in the *Database Engine Relational PostgreSQL* module. It covers basic syntax through booking-schedule query design, non-overlapping constraints, GiST indexes, boundary pitfalls, multirange functions, and practice exercises.

> **Practice prerequisites:** SQL examples use standard modern PostgreSQL. **Multiranges** and related aggregates require PostgreSQL **14 or higher**. Running `CREATE EXTENSION btree_gist` to demonstrate exclusion constraints with room IDs may require appropriate privileges. Run `SHOW server_version;` before trying them.

## 1. What Is a Range Value and How Does It Differ from INTERVAL?

A **range** describes a set of values between a **lower bound** and an **upper bound**.

Example:

```text
Range [10, 20) :

10 ●──────────────────○ 20
   includes 10     excludes 20

Range (10, 20] :

10 ○──────────────────● 20
   excludes 10     includes 20
```

Notation:

| Symbol | Meaning |
|---|---|
| `[` at lower bound | Includes lower bound |
| `(` at lower bound | Excludes lower bound |
| `]` at upper bound | Includes upper bound |
| `)` at upper bound | Excludes upper bound |
| `[a,b]` | Includes both a and b |
| `[a,b)` | Includes a, excludes b |
| `(a,b]` | Excludes a, includes b |
| `(a,b)` | Excludes both |

**`[10,20)`** is commonly called the **half-open interval** convention. If one reservation ends at 10:00 and the next starts at 10:00, they do not overlap when both use `[)`.

### 1.1. Range Differs from INTERVAL

In PostgreSQL:

- **`INTERVAL`** represents a **duration**, such as `INTERVAL '90 minutes'` or `INTERVAL '2 days'`.
- **`tstzrange`** represents a **set of instants** from start to end, such as `[09:00,10:30)` on a specific date.

```sql
SELECT
    INTERVAL '90 minutes' AS duration,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:30:00+07',
        '[)'
    ) AS period;
```

A 90-minute duration alone does not say **when it starts**. A `tstzrange` stores **two timestamp boundaries** and their inclusion rules. Never substitute `INTERVAL` for a range when checking schedule overlaps.

### 1.2. A Range Is a Typed Value, Not an Arbitrary String

The string `'[1,5)'` can be cast to `int4range`, after which it is a **PostgreSQL range value** with overlap/containment semantics, bound canonicalization, and dedicated storage.

```sql
SELECT
    '[1,5)'::int4range AS range_from_literal,
    int4range(1, 5, '[)') AS range_from_constructor;
```

Both expressions represent the same set of integers. In applications, prefer constructors, bind parameters, and explicit casts rather than building range strings from untrusted input via SQL concatenation.

## 2. Built-In Range Types in PostgreSQL

| Range Type | Element Data Type | Example |
|---|---|---|
| `int4range` | `integer` / `int4` | `int4range(1, 10)` |
| `int8range` | `bigint` / `int8` | `int8range(10000000000, 20000000000)` |
| `numrange` | `numeric` | `numrange(1.5, 2.75)` |
| `daterange` | `date` | `daterange(DATE '2026-01-01', DATE '2026-02-01')` |
| `tsrange` | `timestamp without time zone` | `tsrange(TIMESTAMP '2026-11-14 09:00', TIMESTAMP '2026-11-14 10:00')` |
| `tstzrange` | `timestamp with time zone` / `timestamptz` | `tstzrange(TIMESTAMPTZ '2026-11-14 09:00+07', TIMESTAMPTZ '2026-11-14 10:00+07')` |

**Choosing the right element type** matters more than a shorter type name:

- Integer ID ranges use `int4range` or `int8range` matching the ID domain.
- Exact decimal prices or weights use `numrange`.
- Effective date spans (without times of day) use `daterange`.
- Zone-less "wall-clock" local times can use `tsrange` if the domain truly requires it.
- Room bookings, meetings, or global real-time windows generally suit **`tstzrange`**, because instants are compared with offsets/time zones accounted for.

PostgreSQL also lets you define **custom range types** when an element type has a total order and supporting functions/operator classes. This lesson uses built-in types to focus on operators and functions.

### 2.1. Corresponding Multirange Types

Available since PostgreSQL 14:

| Range | Multirange |
|---|---|
| `int4range` | `int4multirange` |
| `int8range` | `int8multirange` |
| `numrange` | `nummultirange` |
| `daterange` | `datemultirange` |
| `tsrange` | `tsmultirange` |
| `tstzrange` | `tstzmultirange` |

A multirange represents a set of **zero, one, or more non-overlapping range segments**. Overlapping or adjacent segments are automatically merged into a canonical representation. This is especially useful when subtracting two ranges yields **two disjoint segments**, which a single range value cannot represent.

## 3. Creating Ranges with Constructors and Literals

### 3.1. Constructors with Lower and Upper Bounds

```sql
SELECT
    int4range(1, 5) AS default_bounds,
    int4range(1, 5, '[)') AS half_open,
    int4range(1, 5, '[]') AS both_inclusive,
    int4range(1, 5, '()') AS both_exclusive;
```

Constructors accept an optional third parameter choosing `[)`, `[]`, `()`, or `(]`. When omitted, the default is **`[)`**.

**Important note:** For **discrete** types such as integers, PostgreSQL may **canonicalize bounds**; thus displayed output does not always keep the exact brackets passed on input.

### 3.2. Range Literals

```sql
SELECT
    '[1,5)'::int4range AS a,
    '(1,5]'::int4range AS b,
    '[2026-01-01,2026-02-01)'::daterange AS c;
```

In SQL, a range literal is a specially formatted string cast to a range type. For timestamps with offsets, constructors with explicit `TIMESTAMPTZ` values are usually easier to read.

### 3.3. Open/Closed Bounds Are Not Just Formatting

```sql
SELECT
    numrange(1, 5, '[)') @> 1::numeric AS includes_one,
    numrange(1, 5, '[)') @> 5::numeric AS includes_five,
    numrange(1, 5, '(]') @> 1::numeric AS excludes_one,
    numrange(1, 5, '(]') @> 5::numeric AS includes_five_in_other_range;
```

Expected output: `true`, `false`, `false`, `true`.

The **`@>`** operator checks whether an element is inside a range. Changing the bound bracket immediately changes the result right at the boundary value.

### 3.4. Bound Ordering

A **non-empty** range requires valid bounds: the lower bound cannot exceed the upper bound under the element type's ordering. For example, reversed bounds `int4range(10, 2)` do not create a "backward" range; PostgreSQL rejects invalid bounds.

If business input has swapped "start" and "end," the application must **reject or intentionally swap them** per contract rather than expecting a range to infer reverse time.

## 4. Discrete Ranges vs. Continuous Ranges: Bound Canonicalization

A subtle feature of PostgreSQL is that **the same set of elements can be written in multiple ways**. For **discrete** types like `integer` and `date`, PostgreSQL applies a *canonicalization* function to normalize ranges into a standard form.

### 4.1. int4range Example

These ranges describe **the exact same set of integers**:

```text
[1,5)   = {1,2,3,4}
(0,4]   = {1,2,3,4}
[1,4]   = {1,2,3,4}
```

Test:

```sql
SELECT
    int4range(1, 5, '[)') AS a,
    int4range(0, 4, '(]') AS b,
    int4range(1, 4, '[]') AS c,
    int4range(1, 5, '[)') = int4range(0, 4, '(]') AS same_set;
```

Result: `same_set=true`. All these `int4range` forms canonicalize to **`[1,5)`**.

**Why?** Between integers 4 and 5, **there is no other integer**. Rewriting upper bound `4]` as `5)` preserves the exact set of elements.

### 4.2. daterange Example

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-01-31', '[]')
        AS january_inclusive,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        AS january_half_open;
```

Both display identically as `[2026-01-01,2026-02-01)` because dates are discrete day steps. The half-open form is very convenient for contiguous date spans.

### 4.3. numrange and tsrange Have No Simple "Next Day" or "Next Number"

For `numeric` and timestamps, there is no fixed discrete step analogous to `integer + 1` or `date + 1 day`:

```sql
SELECT
    numrange(1, 5, '[)') AS a,
    numrange(1, 5, '(]') AS b,
    numrange(1, 5, '[)') = numrange(1, 5, '(]') AS same_set;
```

Result: `same_set=false`. The first range includes 1 and excludes 5; the second does the opposite. Do not expect PostgreSQL to rewrite bounds into identical strings as it does for `int4range`.

### 4.4. Why Does Canonicalization Matter?

- A range's **printed form** can change upon storage.
- `=` on ranges compares their normalized/canonical set semantics, not raw input literal strings.
- A `UNIQUE` index on a range does not prevent overlapping ranges: two distinct ranges can still **overlap** even when `=` is false.
- When displaying the end of a `daterange` under `[)`, `upper(range)` is **the first day no longer in effect**, not the "last included day."

## 5. Empty Ranges and Unbounded Ranges

Not every range contains elements, and not every range has two finite bounds.

### 5.1. Empty Ranges

```sql
SELECT
    'empty'::int4range AS empty_literal,
    isempty('empty'::int4range) AS literal_is_empty,
    int4range(5, 5, '[)') AS empty_by_bounds,
    isempty(int4range(5, 5, '[)')) AS computed_is_empty;
```

Both `isempty` checks return `true`.

Because `[5,5)` includes lower bound 5 yet excludes upper bound 5, the set has zero elements. PostgreSQL displays empty ranges as **`empty`**.

### 5.2. Equal Bounds with Closed Brackets

```sql
SELECT
    int4range(5, 5, '[]') AS one_integer,
    isempty(int4range(5, 5, '[]')) AS is_empty,
    int4range(5, 5, '[]') @> 5 AS contains_five;
```

This range contains **the single element 5**, and is not empty. For `int4range`, its canonical form displays as `[5,6)`.

**Compare:** `[5,5]` over integers contains 5; `[5,5)` is empty.

### 5.3. Ranges Missing a Lower or Upper Bound

A bound omitted as `NULL` in the constructor becomes **unbounded**:

```sql
SELECT
    int4range(NULL, 10, '[)') AS less_than_ten,
    int4range(10, NULL, '[)') AS from_ten_onward,
    int4range(NULL, NULL) AS all_integers;
```

These represent integers **less than 10**, **10 and above**, and **all integers**, respectively.

Note that omitted bounds are **not** `NULL` values stored inside the range. A range represents a set of **non-NULL values from the element domain**; an omitted bound simply means the range extends without limit in that direction.

### 5.4. Unbounded Differs from Element Value Infinity

Types like `date`, `timestamp`, and `timestamptz` support special element values `infinity` and `-infinity`. However:

- **An unbounded endpoint** (`NULL` in constructor) means the range has no bound on that side.
- **A bound set to `infinity`** is a concrete **bound value** from the temporal type's representation, with its own inclusive/exclusive rules.

In data design, do not treat `upper_inf(range)` as asking "is the upper bound the literal `infinity`?" It asks whether the upper side is **unbounded**, which is not identical to a bound set to the special timestamp value `infinity`.

Clear example:

```sql
SELECT
    upper_inf(tstzrange(
        TIMESTAMPTZ '2026-01-01 00:00:00+00',
        NULL,
        '[)'
    )) AS is_unbounded_upper,
    upper_inf(tstzrange(
        TIMESTAMPTZ '2026-01-01 00:00:00+00',
        'infinity'::timestamptz,
        '[)'
    )) AS uses_infinity_value_as_bound;
```

Semantically, the first expression is `true` and the second is `false`. If temporal `infinity` values must be handled, account for bound type, inclusivity, and business rules.

## 6. Functions for Inspecting Range Bounds

PostgreSQL provides a useful group of functions to inspect a range's actual boundaries.

| Function | Question Answered | Notes |
|---|---|---|
| `lower(r)` | What is the lower bound? | Returns NULL if unbounded or empty |
| `upper(r)` | What is the upper bound? | Returns NULL if unbounded or empty |
| `lower_inc(r)` | Is the lower bound inclusive? | Returns false for non-existent/unbounded lower bound |
| `upper_inc(r)` | Is the upper bound inclusive? | Returns false for non-existent/unbounded upper bound |
| `lower_inf(r)` | Is the lower bound unbounded? | Not identical to literal `-infinity` |
| `upper_inf(r)` | Is the upper bound unbounded? | Not identical to literal `infinity` |
| `isempty(r)` | Is the range empty? | Checks whether the set has zero elements |

### 6.1. Reading Both Bounds from a daterange

```sql
WITH periods AS (
    SELECT
        daterange(DATE '2026-02-01',
                  DATE '2026-03-01', '[)') AS r
)
SELECT
    r,
    lower(r) AS start_date,
    upper(r) AS end_exclusive,
    lower_inc(r) AS includes_start,
    upper_inc(r) AS includes_end,
    lower_inf(r) AS has_no_start_bound,
    upper_inf(r) AS has_no_end_bound,
    isempty(r) AS is_empty
FROM periods;
```

Meaningful results:

- `start_date = 2026-02-01`.
- `end_exclusive = 2026-03-01`.
- `includes_start = true`.
- `includes_end = false`.
- Both `lower_inf` and `upper_inf` are `false`.
- `is_empty = false`.

The alias `end_exclusive` reminds readers that March 1 is **not** included—it is the first boundary **outside** the range.

### 6.2. Inspecting a Range with a Missing Bound

```sql
SELECT
    lower_inf(int4range(NULL, 20)) AS no_lower,
    upper_inf(int4range(NULL, 20)) AS no_upper,
    upper(int4range(NULL, 20)) AS upper_bound;
```

Result: `no_lower=true`, `no_upper=false`, `upper_bound=20`.

Whenever `lower()` or `upper()` returns NULL, also check `isempty()`, `lower_inf()`, or `upper_inf()` to distinguish **unbounded** from **empty**. Inspecting `lower`/`upper` alone is not enough.

### 6.3. Applying Ranges in Table Data

```sql
CREATE SCHEMA IF NOT EXISTS range_lab;

CREATE TABLE range_lab.price_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code TEXT NOT NULL,
    valid_days DATERANGE NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT chk_price_rule_not_empty
        CHECK (NOT isempty(valid_days))
);

INSERT INTO range_lab.price_rules
    (product_code, valid_days, unit_price)
VALUES
    ('SKU-A', daterange(DATE '2026-01-01', DATE '2026-02-01', '[)'), 120),
    ('SKU-A', daterange(DATE '2026-02-01', DATE '2026-03-01', '[)'), 135),
    ('SKU-B', daterange(DATE '2026-01-15', DATE '2026-02-15', '[)'),  80);
```

Verify:

```sql
SELECT
    rule_id,
    product_code,
    valid_days,
    lower(valid_days) AS starts_on,
    upper(valid_days) AS stops_before,
    unit_price
FROM range_lab.price_rules
ORDER BY product_code, lower(valid_days);
```

Each row represents **one price rule active over a date range**. The two periods for `SKU-A` meet cleanly on Feb 1 without overlapping thanks to `[)`.

## 7. The @> Operator: Range Contains Element or Another Range

### 7.1. Checking Whether a Date Falls Within an Effective Period

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        @> DATE '2026-01-01' AS includes_first_day,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        @> DATE '2026-01-31' AS includes_last_day,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        @> DATE '2026-02-01' AS includes_next_month;
```

Results: **`true`, `true`, `false`**.

This answers the common question: **"Does the transaction date fall within the price rule's validity period?"**

```sql
SELECT product_code, unit_price
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days @> DATE '2026-01-20';
```

Result: unit price 120 for January.

### 7.2. Checking Whether One Range Contains Another

```sql
SELECT
    int4range(1, 10) @> int4range(3, 7)
        AS inner_fits,
    int4range(3, 7) @> int4range(1, 10)
        AS reverse_fits;
```

Results: `true` and `false`.

Here `@>` accepts a **range on the right**, not only a single scalar element.

### 7.3. The <@ Operator in the Reverse Direction

```sql
SELECT
    5 <@ int4range(1, 10) AS point_inside,
    int4range(3, 7) <@ int4range(1, 10) AS range_inside,
    int4range(1, 10) <@ int4range(3, 7) AS large_inside_small;
```

Results: `true`, `true`, `false`.

Equivalent semantic pairs:

```text
range @> element   <=> element <@ range
rangeA @> rangeB   <=> rangeB <@ rangeA
```

These express business rules cleanly instead of repeating `start <= x AND x < end` in every query.

### 7.4. Match the Element Type Properly

With `tstzrange`, compare against **`TIMESTAMPTZ`**, not a zone-less timestamp string:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00+07',
    TIMESTAMPTZ '2026-11-14 10:00+07',
    '[)'
) @> TIMESTAMPTZ '2026-11-14 09:30+07' AS is_within;
```

Result: `true`.

## 8. The && Operator: Two Ranges Overlap

`&&` returns `true` when two ranges **share at least one common element**.

```sql
SELECT
    int4range(1, 5) && int4range(3, 8)
        AS overlaps,
    int4range(1, 5) && int4range(5, 8)
        AS touching_at_boundary,
    int4range(1, 5) && int4range(8, 10)
        AS separated;
```

Results: `true`, `false`, `false`.

### 8.1. Why Do [1,5) and [5,8) Not Overlap?

```text
[1,5): 1 ●────────────○ 5
[5,8):                 5 ●──────────○ 8

Point 5:
 - Not in the first range.
 - In the second range.

No shared element  =>  && returns false.
```

In room bookings, this lets one guest **check out at 10:00** and the next guest **check in at 10:00** without being flagged as a conflict.

### 8.2. Boundaries Do Overlap When Both Bounds Are Closed

With `numrange`:

```sql
SELECT
    numrange(1, 5, '[]') &&
    numrange(5, 8, '[)') AS both_include_five;
```

Result `true` because 5 belongs to both ranges.

Never assume "two ranges meeting at the same endpoint never overlap." Always check **the brackets and range-type canonicalization**.

### 8.3. Checking Two Date Ranges

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        &&
    daterange(DATE '2026-01-20', DATE '2026-02-20', '[)')
        AS overlap_january_february;
```

Result `true`: the second range includes Jan 20–31, which also lie in the first range.

### 8.4. Finding Records Whose Periods Overlap a Requested Window

```sql
SELECT rule_id, product_code, valid_days
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days &&
      daterange(DATE '2026-01-25', DATE '2026-02-10', '[)')
ORDER BY lower(valid_days);
```

Both January and February rules for `SKU-A` overlap the window Jan 25–Feb 10. This implements "find every period active at least partially during the reporting window."

## 9. The -|- Operator: Two Adjacent Ranges

`-|-` checks whether two ranges are **adjacent**, meaning they can merge into one contiguous range **with no gap** and no shared elements.

```sql
SELECT
    int4range(1, 5) -|- int4range(5, 8)
        AS adjacent,
    int4range(1, 5) -|- int4range(6, 8)
        AS gap_between,
    int4range(1, 5) -|- int4range(4, 8)
        AS overlaps_instead;
```

Results: `true`, `false`, `false`.

### 9.1. Overlap and Adjacency Are Different Concepts

| Two Ranges | `&&` (overlap) | `-|-` (adjacent) |
|---|---|---|
| `[1,5)` and `[3,8)` | true | false |
| `[1,5)` and `[5,8)` | false | true |
| `[1,5)` and `[6,8)` | false | false |

In meeting-room scheduling:

- **Overlap** must normally be rejected for the same room.
- **Adjacent** is normally allowed: the new booking starts right when the old one ends.
- **Separated** is also allowed because there is idle time between bookings.

### 9.2. Difference from `=`

Two ranges can be **equal**, **overlapping without being equal**, **adjacent**, or **disjoint**. If the goal is preventing overlapping bookings, `UNIQUE(period)` only rejects **completely identical ranges**; it does **not** reject `[09:00,10:00)` alongside `[09:30,10:30)`. You need **`&&`** in queries or an exclusion constraint.

## 10. Other Relative Position Operators

Beyond containment, overlap, and adjacency, PostgreSQL offers operators comparing the relative position of two ranges.

| Operator | Intuitive Meaning |
|---|---|
| `<<` | Left range lies **strictly before** right range |
| `>>` | Left range lies **strictly after** right range |
| `&<` | Left range **does not extend to the right of** right range |
| `&>` | Left range **does not extend to the left of** right range |
| `-|-` | Two ranges are adjacent |
| `&&` | Two ranges overlap |
| `@>` | Left contains right |
| `<@` | Left is contained by right |

Clear examples:

```sql
SELECT
    int4range(1, 4) << int4range(6, 9)
        AS strictly_left,
    int4range(9, 12) >> int4range(6, 9)
        AS strictly_right,
    int4range(1, 5) &< int4range(3, 8)
        AS does_not_extend_right,
    int4range(3, 8) &> int4range(1, 5)
        AS does_not_extend_left;
```

For these values and bounds, all four return `true`.

**Warning:** `&<` and `&>` do not simply mean "A comes before B" or "A is inside B." They express **not extending past one boundary**, so they can be true even when two ranges overlap. When you only mean overlap or containment, prefer `&&` or `@>` for clarity.

### 10.1. Testing Relative Positions of Three Ranges

```sql
WITH demo AS (
    SELECT
        int4range(1, 5) AS a,
        int4range(3, 8) AS b,
        int4range(10, 12) AS c
)
SELECT
    a && b AS a_overlaps_b,
    a << c AS a_before_c,
    c >> b AS c_after_b,
    a -|- b AS a_adjacent_b
FROM demo;
```

Corresponding results: `true`, `true`, `true`, `false`.

## 11. Union (+), Intersection (*), and Difference (-) of Two Ranges

These three operators look like set operations, but share a key constraint: **a single range can only represent one contiguous interval**. If an operation yields two disconnected pieces, a single-range return type cannot represent the full result.

### 11.1. Union of Overlapping or Adjacent Ranges

```sql
SELECT
    int4range(1, 5) + int4range(3, 8)
        AS union_overlapping,
    int4range(1, 5) + int4range(5, 8)
        AS union_adjacent;
```

Both produce the integer range `[1,8)`.

`+` on two **single ranges** works when the union forms **one contiguous range**. If two ranges have a gap between them, direct range addition **cannot return a single range representing both pieces**, and PostgreSQL raises an error.

```sql
-- Intentionally demonstrates a union that cannot be represented by one range:
-- SELECT int4range(1, 3) + int4range(5, 8);
-- ERROR: result of range union would not be contiguous
```

Never use single-range `+` to "merge any two schedules" when gaps can exist between them. Use **multiranges** instead.

### 11.2. Intersection of Two Ranges

```sql
SELECT
    int4range(1, 7) * int4range(5, 10)
        AS common_part,
    int4range(1, 5) * int4range(5, 10)
        AS no_common_part;
```

Results:

- `common_part = [5,7)`.
- `no_common_part = empty`.

When two ranges share no elements, **the intersection is an empty range**, not NULL. Test with `isempty(result)`.

### 11.3. Difference When the Result Remains Contiguous

```sql
SELECT
    int4range(1, 10) - int4range(1, 4)
        AS remove_prefix,
    int4range(1, 10) - int4range(8, 12)
        AS remove_suffix;
```

Results:

- Removing prefix `[1,4)` from `[1,10)` leaves `[4,10)`.
- Removing suffix `[8,12)` leaves `[1,8)`.

However, when cutting out a **middle** piece:

```text
[1,10) minus [4,7)

[1,4)       [7,10)
     (gap)
```

the result consists of two separate pieces and **cannot fit in a single `int4range`**.

```sql
-- Do not run expecting a single int4range result:
-- SELECT int4range(1, 10) - int4range(4, 7);
-- PostgreSQL cannot represent two disjoint segments in one range.
```

The proper solution is **multirange** on PostgreSQL 14+.

### 11.4. Matching Operations to Business Questions

| Question | Appropriate Operator/Function |
|---|---|
| Do two schedules overlap? | `&&` |
| Does date X fall in the price period? | `@>` |
| Is a sub-window completely inside a larger window? | `@>` or `<@` |
| Can two segments join seamlessly? | `-|-` or `&&` to check |
| What is the shared time span? | `*` |
| Join two overlapping/adjacent segments? | `+` |
| Subtract a middle segment that may split the result? | **multirange subtraction** |
| Aggregate all ranges per entity? | `range_agg()` |

## 12. Multiranges: Multiple Disjoint Ranges in One Value

A single range:

```text
[1,10)
```

has one contiguous segment.

A multirange:

```text
{[1,4),[7,10)}
```

represents two disjoint segments with a gap in between.

### 12.1. Creating a Multirange

```sql
SELECT
    '{[1,4),[7,10)}'::int4multirange AS from_literal,
    int4multirange(
        int4range(1, 4),
        int4range(7, 10)
    ) AS from_constructor;
```

Both represent the same set of integers as an `int4multirange`.

### 12.2. Difference Producing Two Pieces

```sql
SELECT
    int4multirange(int4range(1, 10))
    -
    int4multirange(int4range(4, 7))
    AS remaining_segments;
```

Expected output:

```text
{[1,4),[7,10)}
```

This is a primary reason to choose multiranges rather than forcing every time set into a single start/end pair.

### 12.3. Union of Two Multiranges

```sql
SELECT
    int4multirange(int4range(1, 3), int4range(6, 8))
    +
    int4multirange(int4range(3, 6))
    AS merged_set;
```

The result is one contiguous segment stored as a multirange:

```text
{[1,8)}
```

Because `[1,3)` touches `[3,6)`, which touches `[6,8)`, the entire set merges into a single range.

### 12.4. Multiranges Also Support Containment and Overlap

```sql
SELECT
    '{[1,4),[7,10)}'::int4multirange @> 2
        AS contains_two,
    '{[1,4),[7,10)}'::int4multirange @> 5
        AS contains_five,
    '{[1,4),[7,10)}'::int4multirange &&
    '{[3,5),[12,15)}'::int4multirange
        AS overlaps_other_set;
```

Results: `true`, `false`, `true`.

### 12.5. Unnesting a Multirange into Individual Ranges

To emit one row per contiguous segment:

```sql
SELECT part
FROM unnest('{[1,4),[7,10)}'::int4multirange) AS t(part)
ORDER BY lower(part);
```

The result contains two ranges: `[1,4)` and `[7,10)`.

This is very handy when a UI expects **one row per contiguous availability slot**, while aggregated data is computed or stored as a multirange.

## 13. range_agg(), range_intersect_agg(), and range_merge()

### 13.1. range_agg(): Unioning Multiple Ranges into One Multirange

Example with three slots:

```sql
WITH periods(period) AS (
    VALUES
        (int4range(1, 4)),
        (int4range(3, 6)),
        (int4range(8, 10))
)
SELECT range_agg(period) AS combined
FROM periods;
```

Result:

```text
{[1,6),[8,10)}
```

The first two overlap and merge into `[1,6)`; `[8,10)` is separate so it remains distinct in the multirange.

### 13.2. range_agg() Is Set Union, Not SUM

`range_agg` operates on sets of ranges and produces **their union**, not the sum of their individual durations. Two bookings 09:00–10:00 and 09:30–10:30 have individual lengths totaling 120 minutes, yet their **occupied union** is only 90 minutes.

To compute total occupied time **without double-counting**, union the ranges first and then sum the duration of **each segment**, using consistent units and time zones.

### 13.3. range_intersect_agg(): Intersection Across All Ranges in a Group

```sql
WITH periods(period) AS (
    VALUES
        (int4range(1, 10)),
        (int4range(3, 8)),
        (int4range(5, 12))
)
SELECT range_intersect_agg(period) AS common_to_all
FROM periods;
```

Result `[5,8)`: every input range contains 5, 6, and 7.

If the ranges have no common elements, the intersection is an empty range. When there are zero input rows/non-null values, aggregates return `NULL`; distinguish **no input data** from **input data with an empty intersection**.

### 13.4. range_merge(): A Single Bounding Range Including Gaps

This function is easy to misunderstand. Given a multirange with two disjoint segments:

```sql
SELECT
    range_merge(
        '{[1,4),[7,10)}'::int4multirange
    ) AS bounding_range;
```

Result: `[1,10)`.

**Warning:** `range_merge` computes the **smallest enclosing range** (*bounding range*), so it **fills in the gap** between 4 and 7 in the returned range. It does **not** preserve the exact original element set like a multirange does.

If you need to know whether a moment falls inside actual booked slots, **never** replace a multirange with `range_merge` and test `@>`, because that treats idle gaps as booked.

### 13.5. Aggregating Ranges by Group

```sql
WITH events(room_id, slot) AS (
    VALUES
        (101, int4range(9, 10)),
        (101, int4range(10, 11)),
        (101, int4range(13, 14)),
        (102, int4range(9, 12))
)
SELECT
    room_id,
    range_agg(slot) AS busy_segments
FROM events
GROUP BY room_id
ORDER BY room_id;
```

Result:

| room_id | busy_segments |
|---:|---|
| 101 | `{[9,11),[13,14)}` |
| 102 | `{[9,12)}` |

Slots `[9,10)` and `[10,11)` for room 101 are **adjacent**, so their union merges into `[9,11)`. Slot `[13,14)` remains separate.

## 14. Room Booking Problem: Using tstzrange and &&

This section illustrates a multi-room booking application.

### 14.1. Table Design

```sql
CREATE TABLE range_lab.bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    occupied_at TSTZRANGE NOT NULL,
    CONSTRAINT chk_booking_nonempty
        CHECK (NOT isempty(occupied_at)),
    CONSTRAINT chk_booking_bounded
        CHECK (
            NOT lower_inf(occupied_at)
            AND NOT upper_inf(occupied_at)
        ),
    CONSTRAINT chk_booking_half_open
        CHECK (
            lower_inc(occupied_at)
            AND NOT upper_inc(occupied_at)
        )
);
```

Three `CHECK` constraints enforce the lab rules:

- Disallow **empty** booking ranges.
- Every booking must have finite **start and end bounds** (not unbounded).
- Enforce the **`[)`** convention: inclusive start, exclusive end.

**Note:** `NOT lower_inf / NOT upper_inf` check for unbounded endpoints; they do not automatically reject special element values like `infinity`. If business rules strictly forbid `infinity`/`-infinity` timestamps, add extra constraints and input validation.

### 14.2. Insert Data

```sql
INSERT INTO range_lab.bookings
    (room_id, guest_name, occupied_at)
VALUES
    (
        101, 'Lan',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 09:00+07',
            TIMESTAMPTZ '2026-11-14 10:00+07',
            '[)'
        )
    ),
    (
        101, 'Minh',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 10:00+07',
            TIMESTAMPTZ '2026-11-14 11:00+07',
            '[)'
        )
    ),
    (
        101, 'Ngọc',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 13:00+07',
            TIMESTAMPTZ '2026-11-14 14:00+07',
            '[)'
        )
    ),
    (
        102, 'Phúc',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 09:30+07',
            TIMESTAMPTZ '2026-11-14 10:30+07',
            '[)'
        )
    );
```

Room 101 has bookings 09–10, 10–11, and 13–14; room 102 has 09:30–10:30. All coexist cleanly because they are either in different rooms or non-overlapping spans in the same room.

### 14.3. Querying for Conflicting Bookings

Request to book room 101 from **09:45 to 10:15**:

```sql
SELECT
    booking_id,
    room_id,
    guest_name,
    lower(occupied_at) AS starts_at,
    upper(occupied_at) AS ends_before
FROM range_lab.bookings
WHERE room_id = 101
  AND occupied_at &&
      tstzrange(
          TIMESTAMPTZ '2026-11-14 09:45+07',
          TIMESTAMPTZ '2026-11-14 10:15+07',
          '[)'
      )
ORDER BY lower(occupied_at);
```

The query returns **two bookings** for room 101: Lan (09–10) and Minh (10–11). The requested window overlaps both.

### 14.4. Request Starting Exactly When the Previous Booking Ends

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    ) &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00+07',
        TIMESTAMPTZ '2026-11-14 11:00+07',
        '[)'
    ) AS overlaps,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    ) -|-
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00+07',
        TIMESTAMPTZ '2026-11-14 11:00+07',
        '[)'
    ) AS adjacent;
```

Results: `overlaps=false` and `adjacent=true`.

### 14.5. Is Checking Before INSERT Enough to Prevent Double-Booking?

An application flow might do:

```text
Transaction A: SELECT ... WHERE occupied_at && requested_range -> 0 rows
Transaction B: SELECT ... WHERE occupied_at && requested_range -> 0 rows
Transaction A: INSERT requested_range
Transaction B: INSERT requested_range
```

Without database-level concurrency protection, both transactions observe no conflicts and **both succeed**, creating a double booking.

Therefore, `SELECT ... WHERE &&` is great for **displaying conflicts**, yet **does not replace integrity constraints** when same-room overlaps must never happen.

## 15. EXCLUDE USING gist: Preventing Overlapping Bookings in the Same Room

PostgreSQL supports **exclusion constraints** backed by index-supported operators. We can declare:

> "No two rows may exist where **`room_id` is equal** and **`occupied_at` overlaps**."

### 15.1. Why Is UNIQUE Not Enough?

The constraint:

```sql
UNIQUE (room_id, occupied_at)
```

only forbids two rows with **identical `room_id` and identical `occupied_at`**. It still allows `[09:00,10:00)` and `[09:30,10:30)` in the same room because those two ranges are not equal.

You must check **overlap** with `&&`, not just **equality** with `=`.

### 15.2. btree_gist Is Needed for Equality on Integer room_id

To combine `room_id WITH =` and `occupied_at WITH &&` in a single GiST exclusion constraint, PostgreSQL needs the **`btree_gist`** extension, which supplies GiST operator classes for scalar types like `integer`.

```sql
-- Run in a controlled environment with extension creation privileges.
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

Extensions are installed **per database** and involve administrative/privilege configuration, so never run this casually in production without approval.

### 15.3. Adding the Exclusion Constraint

On our lab table with no overlapping bookings in the same room:

```sql
ALTER TABLE range_lab.bookings
ADD CONSTRAINT no_room_overlap
EXCLUDE USING gist (
    room_id WITH =,
    occupied_at WITH &&
);
```

Logical meaning:

For **any two distinct rows**, both of the following comparisons must not simultaneously evaluate to `true`:

```text
old.room_id = new.room_id
AND
old.occupied_at && new.occupied_at
```

When rooms differ, `room_id = ...` is false, so there is no conflict. When times do not overlap, `&&` is false, so there is no conflict. When both room and time overlap, PostgreSQL rejects the write.

For exclusion constraints, the resource identifier column should be **`NOT NULL`** if "unknown room ID" must not slip past three-valued comparisons. Here the table already declares `room_id INTEGER NOT NULL`.

### 15.4. Adjacent Bookings Are Permitted

Because the ranges use `[)`, `[09:00,10:00)` and `[10:00,11:00)` do not overlap, so the constraint permits back-to-back bookings in room 101.

For example, another booking from 11–12 can be inserted:

```sql
INSERT INTO range_lab.bookings
    (room_id, guest_name, occupied_at)
VALUES (
    101,
    'Quỳnh',
    tstzrange(
        TIMESTAMPTZ '2026-11-14 11:00+07',
        TIMESTAMPTZ '2026-11-14 12:00+07',
        '[)'
    )
);
```

### 15.5. Overlapping Insert Fails

```sql
-- Intentionally commented out: would violate no_room_overlap.
-- INSERT INTO range_lab.bookings (room_id, guest_name, occupied_at)
-- VALUES (
--     101,
--     'Overlapping Guest',
--     tstzrange(
--         TIMESTAMPTZ '2026-11-14 09:45+07',
--         TIMESTAMPTZ '2026-11-14 10:15+07',
--         '[)'
--     )
-- );
```

The typical error is **SQLSTATE `23P01` – `exclusion_violation`**, distinct from `23505` (`unique_violation`).

### 15.6. Excluding Certain Statuses from the Constraint Scope

In practice, `cancelled` bookings may overlap because they no longer occupy the room. On a table with a `status` column, an exclusion constraint can include a `WHERE` clause:

```sql
-- Illustrative syntax for a schema with an appropriate status column:
-- ALTER TABLE reservation_table
-- ADD CONSTRAINT no_active_overlap
-- EXCLUDE USING gist (
--     room_id WITH =,
--     occupied_at WITH &&
-- )
-- WHERE (status IN ('confirmed', 'in_use'));
```

Note that `range_lab.bookings` currently **has no `status` column**, so this only illustrates extending the model. The exclusion predicate must match your status lifecycle, and transitioning from `cancelled` back to `confirmed` will still trigger the conflict check in PostgreSQL.

### 15.7. Concurrency and Transactions

Unlike a standalone `SELECT` pre-check, PostgreSQL enforces exclusion constraints on write and coordinates concurrent writers safely at the constraint level. If two concurrent transactions attempt to insert conflicting bookings, PostgreSQL prevents both violating rows from committing.

Applications should:

- Catch SQLSTATE `23P01` and return a friendly "room is already booked for that time" message.
- Re-query conflicting slots if suggesting alternative times.
- Evaluate whether `DEFERRABLE` constraints are needed if workflows adjust multiple bookings within one transaction.
- Never rely solely on a pre-insert `SELECT` to guarantee a slot is free.

**Do not confuse** exclusion constraints with foreign keys or ordinary indexes: it is a rule **forbidding any two rows from simultaneously satisfying the prohibited comparisons**.

## 16. GiST Indexes and Optimizing Range Queries

### 16.1. Why Are Separate B-Tree Indexes on Start and End Not Enough?

An overlap query on two separate columns:

```sql
-- Equivalent logic when intervals are [start_at, end_at):
-- WHERE start_at < :requested_end
--   AND end_at > :requested_start
```

can only be partially helped by B-trees; B-tree indexes on `start_at` or `end_at` do not accelerate overlap queries well across all data distributions. Ranges and **GiST** provide operator classes built specifically for containment, overlap, and adjacency.

### 16.2. Creating a GiST Index on a Range Column

```sql
CREATE INDEX price_rules_valid_days_gist_idx
ON range_lab.price_rules
USING gist (valid_days);
```

This index can support queries like:

```sql
SELECT *
FROM range_lab.price_rules
WHERE valid_days @> DATE '2026-02-10';

SELECT *
FROM range_lab.price_rules
WHERE valid_days &&
      daterange(DATE '2026-02-01', DATE '2026-03-01', '[)');
```

PostgreSQL chooses the GiST index depending on statistics, table size, and cost estimates; having an index does not force an Index Scan on every `SELECT`.

### 16.3. An Exclusion Constraint Already Creates an Index

`EXCLUDE USING gist (...)` builds an underlying GiST index to enforce the constraint. Therefore, when a table already has a matching exclusion constraint, think carefully before creating a duplicate GiST index.

Extra indexes may serve different read patterns, yet also add write overhead, I/O, and storage. Inspect `EXPLAIN` and real queries before deciding.

### 16.4. GiST, SP-GiST, and B-Tree

- **GiST**: widely used for range operators `&&`, `@>`, `<@`, and positional operators; supports exclusion constraints.
- **SP-GiST**: PostgreSQL includes SP-GiST operator classes for certain range types/operators, worth evaluating depending on query pattern and version.
- **B-tree**: supports sorting and ordering comparisons (`=`, `<`, `>`) on ranges, **not** GiST-style overlap/containment searches in most scenarios.

Never assume an overlap index is always optimal alone; workloads may also filter by tenant, scalar keys, status, or time, affecting index design and update cost.

### 16.5. EXPLAIN on Overlap Queries

```sql
EXPLAIN
SELECT rule_id, product_code, valid_days
FROM range_lab.price_rules
WHERE valid_days &&
      daterange(DATE '2026-01-15', DATE '2026-02-15', '[)');
```

On a tiny lab table, PostgreSQL will likely choose **Sequential Scan** because it is cheaper than index lookups. That does not mean `&&` or the index is wrong. To evaluate performance, test with realistic data volume, fresh statistics, and representative workloads.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT rule_id
FROM range_lab.price_rules
WHERE valid_days @> DATE '2026-02-10';
```

`EXPLAIN ANALYZE` **executes the query** to measure runtime; safe for small read queries in a lab, whereas write statements must be controlled since they actually run before returning statistics.

## 17. Effective Dating and Historical Data

Ranges fit **effective dating** models naturally: each record applies over a span of time.

### 17.1. Querying Price on a Specific Date

```sql
SELECT
    product_code,
    unit_price
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days @> DATE '2026-02-05';
```

Result: unit price 135.

### 17.2. Distinguish Valid Time from Record Time

Two distinct concepts:

- **Valid time:** during which date range is the price rule effective for transactions?
- **System/record time:** when did the system learn about or record that rule?

`daterange` models **valid time** cleanly, yet **does not automatically track edit history**. If someone updates an existing row in place, you lose the fact that "previously the system recorded a different price." Full temporal auditing may require system-time columns, history tables, event logs, or bitemporal modeling.

### 17.3. Preventing Overlapping Prices for the Same SKU

In a price table, if one SKU cannot have **two simultaneous prices**, you can define an exclusion constraint:

```sql
-- Requires btree_gist for = on TEXT inside GiST.
-- CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Illustrative syntax: run only once existing data is valid
-- and one-price-per-day per SKU is the desired rule:
-- ALTER TABLE range_lab.price_rules
-- ADD CONSTRAINT no_overlapping_price_per_sku
-- EXCLUDE USING gist (
--     product_code WITH =,
--     valid_days WITH &&
-- );
```

This is the same pattern as meeting rooms: the resource key is `product_code`, and the span is `valid_days`.

If the business has multiple **price lists**, **currencies**, or **sales channels** active simultaneously, include those columns in the exclusivity key; otherwise the constraint will reject valid records.

## 18. Time Zones and Time Boundaries

### 18.1. Why Prefer tstzrange for Real-World Schedules?

`tstzrange` stores `timestamptz`. Two timestamps with different offsets representing the same instant compare equal.

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:00:00+07'
        = TIMESTAMPTZ '2026-11-14 02:00:00+00'
        AS same_instant;
```

Result: `true`.

If a customer books 09–10 Vietnam time and a partner sends 02–03 UTC, they represent **the exact same real-time interval** when using `tstzrange` with properly offset timestamps.

### 18.2. tsrange Carries No Time Zone

`tsrange` holds `timestamp without time zone`. It describes local wall-clock values **without offsets**. That can work for certain local recurring schedules, but cannot reliably identify global instants—especially across DST transitions.

Do not convert `tsrange` to `tstzrange` by blindly casting without a time-zone policy and expect historical schedules to line up. Always know which time zone the source values belong to.

### 18.3. The [) Convention Avoids "23:59:59.999999"

To filter orders occurring in November 2026 in Vietnam time:

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-01 00:00:00+07',
        TIMESTAMPTZ '2026-12-01 00:00:00+07',
        '[)'
    ) AS november_period;
```

There is no need to calculate "the last second of Nov 30" or worry about microsecond precision. The upper bound `2026-12-01 00:00` is **excluded**, stopping right before December begins.

### 18.4. Midnight Spans and DST Transitions

In DST zones, a "local calendar day" is not always 24 real hours long. When business logic requires **local calendar days in a specific time zone**, construct bounds from **local dates** converted to `timestamptz` in that zone, rather than adding 24 hours per day.

Example illustrating named time zones:

```sql
SELECT
    tstzrange(
        TIMESTAMP '2026-03-01 00:00:00'
            AT TIME ZONE 'America/New_York',
        TIMESTAMP '2026-04-01 00:00:00'
            AT TIME ZONE 'America/New_York',
        '[)'
    ) AS march_local_calendar_period;
```

Both bounds are constructed in **local wall-clock time** at month start and converted into instants. The elapsed duration between them automatically reflects any DST shift during the month.

## 19. NULL, Empty, Unbounded, and Missing Records

These four states are easily confused in applications:

| State | Meaning | Check |
|---|---|---|
| Range column is `NULL` | No range value provided | `period IS NULL` |
| Range is `empty` | A defined range containing zero elements | `isempty(period)` |
| Range has an unbounded endpoint | Extends infinitely on one side | `lower_inf(period)` / `upper_inf(period)` |
| No row in table | No record exists to evaluate | `NOT EXISTS (...)` |

### 19.1. Example Distinguishing NULL and Empty

```sql
SELECT
    NULL::int4range IS NULL AS null_value,
    isempty('empty'::int4range) AS empty_range,
    isempty(NULL::int4range) AS empty_check_on_null;
```

Results:

- `null_value=true`.
- `empty_range=true`.
- `empty_check_on_null=NULL` (neither `true` nor `false`).

When adding constraints:

```sql
period TSTZRANGE NOT NULL,
CHECK (NOT isempty(period))
```

the two clauses play distinct roles: `NOT NULL` forbids missing values, while `CHECK` forbids empty ranges.

### 19.2. When Is Empty Valid?

Some applications use an empty range to represent "no longer active" or "no matching elements." For **room bookings**, however, a zero-length booking usually makes no sense and should be rejected.

Do not forbid `empty` on every range column automatically; it is a **business choice**, not a universal PostgreSQL rule.

### 19.3. Operators and NULL

`NULL` in SQL follows three-valued logic. Example:

```sql
SELECT
    NULL::int4range && int4range(1, 5) AS unknown_overlap;
```

Result `NULL`, not `false`.

In `WHERE`, NULL evaluates as not true, so rows with NULL ranges are excluded by `WHERE range_col && wanted_range`. If missing ranges need special handling, add an explicit `IS NULL` branch.

## 20. Filtering, Aggregating, and Finding "Free Gaps"

A classic real-world task is finding **available time slots** inside a working window.

### 20.1. Aggregating Occupied Time into a Multirange

For room 101 on Nov 14, 2026:

```sql
SELECT
    room_id,
    range_agg(occupied_at) AS all_busy_periods
FROM range_lab.bookings
WHERE room_id = 101
GROUP BY room_id;
```

Room 101's 09–10 and 10–11 bookings merge into **09–11**. The 11–12 booking added after creating the exclusion constraint also touches them, so if you ran the full lab, the morning occupied block becomes **09–12**. The 13–14 slot remains separate.

### 20.2. Finding Gaps in a Window Using Multirange Subtraction

Suppose the target window is **08:00–18:00**:

```sql
WITH requested AS (
    SELECT
        tstzmultirange(
            tstzrange(
                TIMESTAMPTZ '2026-11-14 08:00+07',
                TIMESTAMPTZ '2026-11-14 18:00+07',
                '[)'
            )
        ) AS full_window
),
busy AS (
    SELECT
        COALESCE(
            range_agg(occupied_at),
            '{}'::tstzmultirange
        ) AS occupied
    FROM range_lab.bookings
    WHERE room_id = 101
)
SELECT
    requested.full_window - busy.occupied
        AS available_segments
FROM requested
CROSS JOIN busy;
```

If all booking inserts ran, room 101 is busy during **09–12** and **13–14**, leaving free gaps in 08–18 of:

```text
[08:00,09:00)
[12:00,13:00)
[14:00,18:00)
```

Notice `COALESCE(range_agg(...), '{}'::tstzmultirange)`: if a room has zero bookings, the aggregate returns `NULL`, so we substitute an **empty multirange**. Subtracting empty from `full_window` then returns `full_window` intact.

### 20.3. Why Not Use range_merge on Busy Periods?

Calling `range_merge(range_agg(occupied_at))` over busy slots 09–12 and 13–14 yields **09–14**, swallowing the **genuinely free** 12–13 slot. Therefore, keep a **multirange** when computing availability rather than collapsing into a gap-filling bounding range.

### 20.4. Filtering by Minimum Slot Duration

A 5-minute gap cannot host a 45-minute meeting. After finding free segments, unnest and filter them:

```sql
WITH window AS (
    SELECT tstzmultirange(
        tstzrange(
            TIMESTAMPTZ '2026-11-14 08:00+07',
            TIMESTAMPTZ '2026-11-14 18:00+07',
            '[)'
        )
    ) AS all_time
),
busy AS (
    SELECT COALESCE(
        range_agg(occupied_at),
        '{}'::tstzmultirange
    ) AS used_time
    FROM range_lab.bookings
    WHERE room_id = 101
),
free AS (
    SELECT all_time - used_time AS periods
    FROM window CROSS JOIN busy
)
SELECT part AS free_period,
       upper(part) - lower(part) AS duration
FROM free
CROSS JOIN LATERAL unnest(periods) AS p(part)
WHERE upper(part) - lower(part) >= INTERVAL '45 minutes'
ORDER BY lower(part);
```

Here **`upper(tstzrange) - lower(tstzrange)`** returns an `interval` measuring the exact duration between the two timestamps. This query applies to segments with **both bounds finite**, such as the lab's fixed 08–18 window.

## 21. Handling Ranges in Applications and APIs

### 21.1. Why Not Concatenate Range Strings in SQL?

Never build SQL like:

```text
"... WHERE occupied_at && '[" + start + "," + end + ")'::tstzrange"
```

from unvalidated client data. Temporal inputs must be parsed, assigned proper time zones, and bound as typed parameters to avoid syntax bugs and SQL injection.

### 21.2. Prepared Statement with Timestamp Bounds

In PostgreSQL:

```sql
PREPARE find_conflicts(
    INTEGER, TIMESTAMPTZ, TIMESTAMPTZ
) AS
SELECT booking_id, room_id, occupied_at
FROM range_lab.bookings
WHERE room_id = $1
  AND occupied_at && tstzrange($2, $3, '[)')
ORDER BY lower(occupied_at);

EXECUTE find_conflicts(
    101,
    TIMESTAMPTZ '2026-11-14 09:45+07',
    TIMESTAMPTZ '2026-11-14 10:15+07'
);

DEALLOCATE find_conflicts;
```

`$1`, `$2`, and `$3` are strongly typed parameters. `tstzrange` is constructed **in SQL via the constructor**, not by concatenating bracket characters around input strings.

### 21.3. Java/JDBC: Passing Each Bound as a Parameter

Example passing `OffsetDateTime` via JDBC 4.2+ and building `tstzrange` in SQL:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;

public final class BookingQueries {
    public boolean hasConflict(
            Connection connection,
            int roomId,
            OffsetDateTime start,
            OffsetDateTime end
    ) throws SQLException {
        if (start == null || end == null ||
                !start.toInstant().isBefore(end.toInstant())) {
            throw new IllegalArgumentException(
                "start must be earlier than end and non-null"
            );
        }

        String sql = """
            SELECT EXISTS (
                SELECT 1
                FROM range_lab.bookings
                WHERE room_id = ?
                  AND occupied_at &&
                      tstzrange(
                          CAST(? AS timestamptz),
                          CAST(? AS timestamptz),
                          '[)'
                      )
            )
            """;

        try (PreparedStatement stmt =
                 connection.prepareStatement(sql)) {
            stmt.setInt(1, roomId);
            stmt.setObject(2, start);
            stmt.setObject(3, end);

            try (ResultSet rs = stmt.executeQuery()) {
                rs.next();
                return rs.getBoolean(1);
            }
        }
    }
}
```

This uses Java text blocks (Java 15+) and a PostgreSQL JDBC driver supporting `OffsetDateTime` binding. Ensure application input is parsed with its true time zone/offset before passing; a local datetime string without an offset does not specify a unique instant.

`hasConflict` is useful for **showing an upfront warning**; on write, the **exclusion constraint** is the authoritative safeguard against concurrent double-booking.

### 21.4. APIs Should Define Boundaries Explicitly

If an API accepts:

```json
{
  "roomId": 101,
  "start": "2026-11-14T09:00:00+07:00",
  "end": "2026-11-14T10:00:00+07:00"
}
```

the API documentation should state clearly:

- `start` is **inclusive**.
- `end` is **exclusive**.
- Both must carry offsets or be resolved in an explicit time zone.
- `start < end` as **real instants**.
- Two bookings for the same room cannot overlap, though they may be adjacent.
- Business error mapping from SQLSTATE `23P01` when the exclusion constraint triggers.

When frontend, backend, and database share this contract, boundary cases like "exactly 10:00" never rely on guesswork.

## 22. Managing Range Length and Element Counts

### 22.1. Ranges Have No Single Universal length() Function

Do not assume `length(anyrange)` returns "range length" across all range types. Length means different things:

- Integers: number of **integer elements** in a finite range.
- `numeric`: numeric difference between bounds, if meaningful.
- Dates: number of **calendar days** or day steps.
- Timestamps: **elapsed duration** between two instants.

Compute with the appropriate element-type arithmetic after verifying the range is non-empty, bounded on both sides, and interpreted with the right bound rules.

### 22.2. int4range in Canonical [) Form

For `int4range(3,8)` containing `3,4,5,6,7`, the element count is `upper(r)-lower(r)=5`.

```sql
WITH demo AS (
    SELECT int4range(3, 8) AS r
)
SELECT
    r,
    upper(r) - lower(r) AS integer_count
FROM demo;
```

This holds specifically for **discrete integer ranges in canonical `[)` form** with finite bounds; do not apply it blindly to `numrange`, `tstzrange`, or unbounded ranges.

### 22.3. Finite Time Intervals

```sql
WITH demo AS (
    SELECT tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ) AS r
)
SELECT
    r,
    upper(r) - lower(r) AS duration
FROM demo;
```

The duration result is `01:30:00`. This is the difference between **two real instants**, distinct from calendar day/month counts often wanted in summary reports.

## 23. Common Mistakes with Ranges and Multiranges

**1. "`[a,b)` and `[a,b]` only differ in how they print."** Wrong. They can differ at the upper boundary element.

**2. "Two bookings with `end = start` always overlap."** Not under `[)`: they are **adjacent**, not overlapping.

**3. "`UNIQUE (room_id, period)` prevents all overlapping bookings."** Wrong. `UNIQUE` only forbids identical keys, not two distinct yet overlapping ranges.

**4. "`EXCLUDE ... WITH &&` is a per-row CHECK constraint."** No. It forbids a relationship **between distinct rows**.

**5. "SELECTing for conflicts before INSERT is safe under concurrency."** No. A race condition exists without database-level concurrency protection.

**6. "`int4range(1,4,'[]')` always prints back as `[1,4]`."** No. PostgreSQL canonicalizes discrete integer ranges to `[1,5)`.

**7. "`numrange` also adds 1 automatically to canonicalize like `int4range`."** No. `numeric` has no discrete next step.

**8. "`empty` is SQL `NULL`."** Wrong. An empty range is a valid value representing the empty set; `NULL` means no range value.

**9. "`upper_inf()` tells whether the bound equals literal `infinity`."** No. It checks whether the bound is unbounded.

**10. "`lower()` returning NULL proves the range has no lower bound."** Not necessarily: an empty range also returns NULL for `lower()`.

**11. "`&&` means two ranges are equal."** Wrong. They only need to share at least one element.

**12. "`-|-` means the same as `&&`."** No. Adjacency and overlap are mutually exclusive relations.

**13. "Single-range `+` can merge two disconnected segments."** No. Disjoint results cannot be represented as a single range.

**14. "Single-range `-` always returns a single range."** No. Cutting out a middle piece requires a multirange.

**15. "`range_merge(multirange)` preserves all gaps."** No. It returns a single bounding range and fills in gaps.

**16. "`range_agg` sums the lengths of ranges."** Wrong. It returns their set union as a multirange.

**17. "Multiranges work in every PostgreSQL version."** No. They require PostgreSQL 14+.

**18. "Storing `tsrange` without offsets suffices for international schedules."** Not on its own. You need explicit time zones or `tstzrange`.

**19. "A calendar day is always 24 real hours in every time zone."** Not across DST transitions.

**20. "`DATERANGE` `[01/01,31/01]` and `[01/01,01/02)` contain different dates."** No. Over discrete dates, both canonicalize to the exact same range.

**21. "Adding a GiST index guarantees PostgreSQL always uses Index Scan."** No. The planner decides from cost, statistics, and table size.

**22. "`btree_gist` is installed automatically when creating a table with integer `room_id`."** No. The extension must be explicitly installed with appropriate privileges when combining scalar equality in GiST.

**23. "A nullable `room_id` doesn't affect exclusion constraints."** Wrong. If a comparison yields NULL/unknown, the constraint won't reject the pair; enforce `NOT NULL`.

**24. "An empty booking range is always valid."** Not if start must precede end; add `CHECK (NOT isempty(...))` and validation.

**25. "Any datetime text string is interpreted in the user's time zone."** No. Manage types, session/zone settings, and explicit offsets properly.

**26. "A multi-segment busy schedule can be stored as min/max columns without losing meaning."** No. Min/max fills in all idle gaps between busy periods.

## 24. Practice Exercises with Answers

### Exercise 1 — Distinguishing the Four Bound Types

**Question:** In the `numeric` domain, does `[1,5)` contain 1 and 5?

**Answer:** Contains 1, excludes 5.

```sql
SELECT
    numrange(1, 5, '[)') @> 1::numeric AS has_one,
    numrange(1, 5, '[)') @> 5::numeric AS has_five;
```

Results: `true` and `false`.

### Exercise 2 — Canonicalizing int4range

**Question:** Do `int4range(1,4,'[]')` and `int4range(1,5,'[)')` represent the same set of integers?

**Answer:** Yes. Both contain 1, 2, 3, 4.

```sql
SELECT
    int4range(1, 4, '[]') =
    int4range(1, 5, '[)') AS same_set;
```

### Exercise 3 — Empty Ranges

**Task:** Check whether `int4range(7,7,'[)')` is empty.

```sql
SELECT isempty(int4range(7, 7, '[)')) AS is_empty;
```

**Answer:** `true`.

### Exercise 4 — Date Containment

An effective period is `[2026-01-01,2026-02-01)`. Are Jan 31 and Feb 1 included?

**Answer:** Jan 31 is included; Feb 1 is excluded.

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01')
        @> DATE '2026-01-31' AS jan31,
    daterange(DATE '2026-01-01', DATE '2026-02-01')
        @> DATE '2026-02-01' AS feb01;
```

### Exercise 5 — Overlap or Adjacent?

Consider `[9,10)` and `[10,11)`.

**Answer:** `&&` is false, `-|-` is true.

```sql
SELECT
    int4range(9, 10) && int4range(10, 11) AS overlaps,
    int4range(9, 10) -|- int4range(10, 11) AS adjacent;
```

### Exercise 6 — Finding the Price Rule on a Date

**Task:** Get the price of `SKU-A` on `2026-02-05`.

**Answer:**

```sql
SELECT unit_price
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days @> DATE '2026-02-05';
```

Result: `135`.

### Exercise 7 — Finding Conflicting Bookings

**Task:** Find bookings in room 101 overlapping `[09:45,10:15)` on 2026-11-14 at offset `+07`.

**Answer:**

```sql
SELECT booking_id, guest_name, occupied_at
FROM range_lab.bookings
WHERE room_id = 101
  AND occupied_at && tstzrange(
      TIMESTAMPTZ '2026-11-14 09:45+07',
      TIMESTAMPTZ '2026-11-14 10:15+07',
      '[)'
  )
ORDER BY lower(occupied_at);
```

Returns Lan and Minh.

### Exercise 8 — Preventing Race Conditions

**Question:** Why can `SELECT ... WHERE occupied_at && new_period` before inserting still create overlaps?

**Answer:** Two concurrent transactions can both observe "no conflicting rows" before either commits. Use an exclusion constraint `EXCLUDE USING gist (room_id WITH =, occupied_at WITH &&)` so the database enforces consistency across concurrent writes.

### Exercise 9 — Union of Two Adjacent Ranges

```sql
SELECT int4range(1, 4) + int4range(4, 9) AS result;
```

**Answer:** `[1,9)`.

### Exercise 10 — Intersection

```sql
SELECT int4range(1, 8) * int4range(5, 12) AS result;
```

**Answer:** `[5,8)`.

### Exercise 11 — Difference Producing Two Segments

**Task:** Compute `[1,10) - [4,7)` without losing elements.

**Answer (PostgreSQL 14+):**

```sql
SELECT
    int4multirange(int4range(1, 10))
    -
    int4multirange(int4range(4, 7))
    AS result;
```

Result: `{[1,4),[7,10)}`.

### Exercise 12 — range_agg

**Question:** Why is `range_agg` of `[1,5)`, `[4,7)`, and `[9,10)` not `[1,10)`?

**Answer:** The union of the three ranges contains `[1,7)` and `[9,10)`, **excluding** the gap `[7,9)`. Therefore the multirange result is `{[1,7),[9,10)}`.

```sql
WITH data(r) AS (
    VALUES
        (int4range(1,5)),
        (int4range(4,7)),
        (int4range(9,10))
)
SELECT range_agg(r) AS result
FROM data;
```

### Exercise 13 — Does range_merge Fill Gaps?

```sql
SELECT range_merge(
    '{[1,4),[7,10)}'::int4multirange
) AS result;
```

**Answer:** `[1,10)`, filling the gap 4–7. Use only when a **bounding range** is desired, not as the actual set of busy slots.

### Exercise 14 — An Open-Ended Effective Period

**Task:** Store an effective period starting 2026-01-01 with no upper bound.

```sql
SELECT daterange(
    DATE '2026-01-01',
    NULL,
    '[)'
) AS open_ended;
```

**Answer:** This represents the span from the start of 2026-01-01 onward with no upper bound. `upper_inf(...)` returns `true`.

### Exercise 15 — Designing an Index for Overlaps

**Task:** Frequently search for price rules overlapping a date window.

**Suggested Answer:**

```sql
CREATE INDEX price_rules_window_lookup_idx
ON range_lab.price_rules
USING gist (valid_days);
```

Then verify with `EXPLAIN` on real data. The lab table already has `price_rules_valid_days_gist_idx` serving the same purpose; **avoid creating both** on the same table without a specific reason. The statement above illustrates syntax only.

### Exercise 16 — NULL or Empty?

```sql
SELECT
    NULL::daterange IS NULL AS a,
    isempty('empty'::daterange) AS b;
```

**Answer:** `a=true` and `b=true`, representing two distinct states. Combine `NOT NULL` with `CHECK (NOT isempty(...))` when business rules require both a provided value and at least one element.

### Exercise 17 — Time Zones

**Question:** Do a booking starting at 09:00 +07 and one starting at 02:00 UTC on the same day start at the same instant?

**Answer:** Yes. Two representations of the same instant. `tstzrange` is the right type when comparing real-time schedules across time zones.

### Exercise 18 — Finding Free Slots

A room is busy during `[09,11)` and `[13,14)`. The working window is `[08,18)`.

**Answer:** Free segments are `[08,09)`, `[11,13)`, and `[14,18)`. Compute by casting both sides to multiranges and subtracting with `-`.

Note that this scenario **differs** from the lab dataset after adding the 11–12 booking; in the full lab dataset, the middle gap between the morning and afternoon bookings is `[12,13)`.

## 25. Design Workflow When Using Ranges in Real Projects

1. **Identify element domain:** integers, dates, decimals, or real-time instants?
2. **Choose the type:** `int4range`/`int8range`/`numrange`/`daterange`/`tsrange`/`tstzrange`.
3. **Standardize bounds:** half-open `[)` is convenient for schedules and effective periods; document it in APIs.
4. **Define empty/edge states:** are `NULL`, `empty`, unbounded bounds, and `infinity` permitted?
5. **Use operators accurately:** `@>` for containment, `&&` for overlap, `-|-` for adjacency; never use `=` instead of overlap.
6. **Choose range vs. multirange:** single contiguous span or set of disjoint spans?
7. **When unioning/subtracting multiple segments:** do not force single-range `+`/`-` when results can split; use multiranges.
8. **When aggregating ranges:** `range_agg` produces the exact union, whereas `range_merge` produces only a bounding range.
9. **When forbidding overlapping schedules:** use an exclusion constraint with the exact resource key and status filter; never rely on pre-write `SELECT` checks alone.
10. **Choose indexes:** GiST for overlap/containment, `btree_gist` when combining scalar equality inside GiST; verify plans.
11. **Specify time zones:** for real-time schedules, prefer `tstzrange` and inputs with explicit offsets/time zones.
12. **Define scope:** tenant, room, currency/channel pricing, active status, and access control.
13. **Test boundaries:** touching segments, closed bounds, empty, unbounded, month-ends, DST, and differences producing two pieces.
14. **Plan migrations:** if existing rows already overlap, adding an exclusion constraint will fail; clean legacy conflicts deliberately first.
15. **Test write concurrency:** verify two concurrent transactions cannot commit conflicting rows.
16. **Check versions:** multiranges require PostgreSQL 14+, and extensions/privileges must match your environment.
17. **Set operational limits:** watch query latency, multirange size, index bloat, and write overhead.

## 26. Summary

PostgreSQL **range types** represent sets of values between two bounds as first-class typed values with explicit **open/closed bound** syntax. Comparisons that are error-prone when written manually over separate start/end columns become direct and expressive:

- **`@>` and `<@`:** check whether an element or range falls inside another range.
- **`&&`:** check whether two ranges overlap.
- **`-|-`:** check whether two ranges are adjacent.
- **`+`, `*`, `-`:** union, intersection, and difference, keeping in mind that a single range cannot represent disconnected pieces.
- **`lower`, `upper`, `lower_inc`, `upper_inc`, `lower_inf`, `upper_inf`, `isempty`:** inspect bounds and range state.
- **Multiranges** and **`range_agg`** represent and aggregate multiple disjoint segments without filling gaps; **`range_merge`** returns a single bounding range.
- **GiST** accelerates overlap/containment queries, while **exclusion constraints** enforce "no two overlapping ranges for the same resource" safely at the database layer.

The **`[start,end)`** convention is especially effective for bookings and effective periods: consecutive slots sharing a boundary timestamp **do not overlap**. Still, that convention must be enforced consistently from API to SQL alongside the right temporal types and time zones.

**Final principle:** before picking an operator, answer **"what set of values am I storing, are the boundaries inclusive, can there be multiple disjoint pieces, and are overlapping records forbidden by business rules?"** Answering those clearly is the foundation for using ranges and multiranges accurately, maintainably, and safely under concurrent writes.

### Official PostgreSQL Documentation

- [Range Types and Multirange Types](https://www.postgresql.org/docs/current/rangetypes.html).
- [Range/Multirange Functions and Operators](https://www.postgresql.org/docs/current/functions-range.html).
- [CREATE TABLE — EXCLUDE Constraint](https://www.postgresql.org/docs/current/sql-createtable.html).
- [Indexes, Operator Classes and GiST](https://www.postgresql.org/docs/current/indexes-types.html).
- [Date/Time Types and Time Zones](https://www.postgresql.org/docs/current/datatype-datetime.html).
