# Gaps and Islands, Top N per Group, and Deduplication

In a relational database, standard `GROUP BY` aggregates rows with the same key value into a single group, but many real-world problems also require understanding the **order of rows within each group**. For example:

- A user is active for **three consecutive days**, takes a day off, and then is active for two more days. You need to find each continuous streak of days and its length.
- A device emits states `READY → READY → ERROR → ERROR → READY`. You need to find **three consecutive state runs**, rather than collapsing all `READY` rows into one group.
- Each customer has thousands of orders. You need the **three most recent orders per customer**, not the three most recent orders across the entire system.
- Data ingested multiple times from an API contains duplicate `(tenant_id, event_key)` records. You need to keep the **most recently received** record, with a clear tie-breaking rule, and prevent duplicate recurrence under concurrent writes.

These problems are important applications of **window functions** in PostgreSQL. Unlike `GROUP BY`, window functions can compute row numbers, ranks, previous row values, or running totals **without immediately collapsing the detail rows**. An outer query layer then filters or aggregates over the computed results.

This lesson focuses on three families of techniques:

1. **Gaps and islands:** marking when a sequence breaks using `LAG()`, or turning the difference between a consecutive key and `ROW_NUMBER()` into a group key.
2. **Top N per group:** using `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `DISTINCT ON`, and `LATERAL` to select an exact number of rows or retain ties.
3. **Deduplication:** defining what counts as a "duplicate", choosing a representative record using an explainable ordering, and then handling the data safely and protecting uniqueness.

> **Scope:** The illustrative SQL is written for modern PostgreSQL. Run the table-creation scripts and delete/update statements in a **database lab**, not on production data. This lesson provides both read queries and delete examples to teach design; deletes should only be executed after previewing the affected record set and having a rollback/recovery plan.

## 1. Reviewing Window Functions: PARTITION BY and ORDER BY

A window function is used with the `OVER` clause:

```sql
function_name(...) OVER (
    PARTITION BY partition_key
    ORDER BY sort_key
)
```

Meaning:

| Component | Purpose |
|---|---|
| `PARTITION BY` | Splits input rows into independent **calculation partitions**. |
| `ORDER BY` in `OVER` | Defines the logical ordering of rows within each partition. |
| `ROW_NUMBER()` | Assigns sequential numbers 1, 2, 3, ... to each row within each partition. |
| `RANK()` | Ranks rows with ties receiving the same rank and gaps after tied groups. |
| `DENSE_RANK()` | Ranks rows with ties receiving the same rank and no gaps in rank numbers. |
| `LAG(expression)` | Reads the value of the preceding row in the window's ordering. |
| `LEAD(expression)` | Reads the value of the following row. |
| `SUM(...) OVER (...)` | Can produce a running total to number consecutive segments. |

Example:

```sql
SELECT
    o.customer_id,
    o.order_id,
    o.placed_at,
    ROW_NUMBER() OVER (
        PARTITION BY o.customer_id
        ORDER BY o.placed_at DESC, o.order_id DESC
    ) AS order_position
FROM lesson_window_cases.orders AS o;
```

For each customer, the row with the latest `placed_at` receives `order_position = 1`. If timestamps are equal, `order_id DESC` serves as the **tie-breaker key**. If `PARTITION BY` is omitted, PostgreSQL numbers across the **entire result set**, rather than restarting per customer.

### Window ORDER BY vs. Final Query ORDER BY

```sql
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY placed_at DESC, order_id DESC
    ) AS rn
FROM lesson_window_cases.orders
ORDER BY customer_id, rn;
```

- `ORDER BY` **inside `OVER`** determines which row receives `rn = 1`, `rn = 2`...
- `ORDER BY` **at the end of the query** determines how the output rows are displayed.

The two orderings are often chosen consistently, but they serve **different purposes**. The final output has **no guaranteed order** if `ORDER BY` is omitted at the result layer.

## 2. Preparing Practice Data

We create a dedicated schema and four datasets: customers–orders, daily activity, device state changes, and duplicate ingested events.

```sql
CREATE SCHEMA IF NOT EXISTS lesson_window_cases;

CREATE TABLE lesson_window_cases.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE lesson_window_cases.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lesson_window_cases.customers(customer_id),
    placed_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED'))
);

CREATE TABLE lesson_window_cases.daily_activity (
    activity_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    activity_date DATE NOT NULL,
    action_name TEXT NOT NULL
);

CREATE TABLE lesson_window_cases.device_states (
    state_id BIGINT PRIMARY KEY,
    device_id BIGINT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    state_name TEXT NOT NULL
);

CREATE TABLE lesson_window_cases.raw_events (
    event_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_key TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
```

### 2.1. Customers and Orders

```sql
INSERT INTO lesson_window_cases.customers(customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO lesson_window_cases.orders(
    order_id, customer_id, placed_at, total_amount, status
)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-11-01 09:00:00+07',
        350000, 'PAID'),
    (1002, 1, TIMESTAMPTZ '2026-11-03 10:00:00+07',
        900000, 'PAID'),
    (1003, 1, TIMESTAMPTZ '2026-11-03 10:00:00+07',
        900000, 'PENDING'),
    (1004, 1, TIMESTAMPTZ '2026-11-05 12:00:00+07',
        250000, 'PAID'),
    (2001, 2, TIMESTAMPTZ '2026-11-02 08:00:00+07',
        1000000, 'PAID'),
    (2002, 2, TIMESTAMPTZ '2026-11-04 09:00:00+07',
        1000000, 'PAID'),
    (2003, 2, TIMESTAMPTZ '2026-11-04 14:00:00+07',
        400000, 'PENDING'),
    (3001, 3, TIMESTAMPTZ '2026-11-06 08:00:00+07',
        600000, 'PAID');
```

Characteristics:

- **An:** four orders, including **two orders tied at amount 900,000** and **two orders at the same timestamp** `2026-11-03 10:00+07`.
- **Bình:** three orders, two of which have amount 1,000,000 at different timestamps.
- **Chi:** one order.
- **Dung:** no orders yet, which helps test the difference between `INNER JOIN` and `LEFT JOIN LATERAL`.

### 2.2. Daily Activity Including Same-Day Records

```sql
INSERT INTO lesson_window_cases.daily_activity(
    activity_id, user_id, activity_date, action_name
)
VALUES
    (1, 1, DATE '2026-11-01', 'login'),
    (2, 1, DATE '2026-11-01', 'open_page'),
    (3, 1, DATE '2026-11-02', 'login'),
    (4, 1, DATE '2026-11-03', 'login'),
    (5, 1, DATE '2026-11-05', 'login'),
    (6, 1, DATE '2026-11-06', 'upload'),
    (7, 1, DATE '2026-11-09', 'login'),
    (8, 2, DATE '2026-11-01', 'login'),
    (9, 2, DATE '2026-11-03', 'login'),
    (10, 2, DATE '2026-11-04', 'login'),
    (11, 2, DATE '2026-11-05', 'upload');
```

For user 1:

```text
01  02  03  04  05  06  07  08  09 (Nov)
 ●───●───●    ·   ●───●    ·   ·   ●
 └─ 3 days ─┘      └ 2 days ┘        └1┘
```

Nov 01 has **two events**, but counts as only **one active day** when the goal is counting streaks by day.

### 2.3. Device State Sequence

```sql
INSERT INTO lesson_window_cases.device_states(
    state_id, device_id, changed_at, state_name
)
VALUES
    (1, 10, TIMESTAMPTZ '2026-11-14 09:00:00+07', 'READY'),
    (2, 10, TIMESTAMPTZ '2026-11-14 09:05:00+07', 'READY'),
    (3, 10, TIMESTAMPTZ '2026-11-14 09:10:00+07', 'ERROR'),
    (4, 10, TIMESTAMPTZ '2026-11-14 09:20:00+07', 'ERROR'),
    (5, 10, TIMESTAMPTZ '2026-11-14 09:25:00+07', 'READY'),
    (6, 20, TIMESTAMPTZ '2026-11-14 08:00:00+07', 'OFFLINE'),
    (7, 20, TIMESTAMPTZ '2026-11-14 08:30:00+07', 'READY');
```

### 2.4. Duplicate Received Events

```sql
INSERT INTO lesson_window_cases.raw_events(
    event_id, tenant_id, event_key, received_at, payload
)
VALUES
    (5001, 1, 'evt-A',
        TIMESTAMPTZ '2026-11-10 09:00:00+07',
        '{"version":1}'::jsonb),
    (5002, 1, 'evt-A',
        TIMESTAMPTZ '2026-11-11 09:00:00+07',
        '{"version":2}'::jsonb),
    (5003, 1, 'evt-A',
        TIMESTAMPTZ '2026-11-11 09:00:00+07',
        '{"version":3}'::jsonb),
    (5004, 1, 'evt-B',
        TIMESTAMPTZ '2026-11-12 10:00:00+07',
        '{"version":1}'::jsonb),
    (6001, 2, 'evt-A',
        TIMESTAMPTZ '2026-11-12 11:00:00+07',
        '{"version":1}'::jsonb),
    (6002, 2, 'evt-C',
        TIMESTAMPTZ '2026-11-12 11:10:00+07',
        '{"version":1}'::jsonb),
    (6003, 2, 'evt-C',
        TIMESTAMPTZ '2026-11-13 11:10:00+07',
        '{"version":2}'::jsonb);
```

In `tenant_id = 1`, key `evt-A` has three records; the two latest share the **same `received_at`**, so `event_id` is needed as a tie-breaking criterion. `tenant_id = 2` also has `evt-A`, but that is a **different business key** if the unit of uniqueness is the `(tenant_id, event_key)` pair.

## 3. Why Plain GROUP BY Cannot Find Consecutive Runs

Ask the question: "How many **consecutive READY runs** does device 10 have?"

If you run:

```sql
SELECT
    device_id,
    state_name,
    COUNT(*) AS observations
FROM lesson_window_cases.device_states
GROUP BY device_id, state_name
ORDER BY device_id, state_name;
```

Device 10 has three `READY` observations, but they do not belong to **a single continuous run**:

```text
09:00 READY
09:05 READY
---------------- state transition
09:10 ERROR
09:20 ERROR
---------------- state transition
09:25 READY
```

`GROUP BY (device_id, state_name)` merges all three `READY` observations into one group, losing the fact that an `ERROR` segment occurred in between. To find **runs** accurately, you must know **when the state changes in chronological order**.

The key insight of the consecutive-groups problem:

> Two rows with the same value **do not necessarily belong to the same run** if there is an interruption between them in business order.

That is why you must use `ORDER BY` in a window before assigning group labels.

## 4. Gaps and Islands: Two Foundational Concepts

An **island** is a sequence of rows forming a contiguous run according to a defined rule. A **gap** is an interruption between runs.

For active days:

```text
01 02 03 [04 inactive] 05 06 [07 08 inactive] 09
└ Island A ┘            └ B ┘                  └ C ┘
```

However, "consecutive" can mean several things:

- Adjacent calendar days: `current_date = previous_date + 1`.
- Adjacent business days, skipping weekends and holidays.
- Records whose sequence numbers increment by exactly one.
- Measurements separated by **at most 30 minutes**.
- Adjacent rows with the **same state**.
- Time intervals that **overlap or touch**.

There is no single formula for every case. You must explicitly define the **partition key**, **sort key**, and **gap detection rule**.

## 5. Technique 1: Consecutive Days via ROW_NUMBER and Subtraction

Given a set of **distinct dates per user**, if dates increment by one day at a time and row numbers increment by one unit at a time, then:

```text
Date        ROW_NUMBER   Date - ROW_NUMBER days
Nov 01      1            Oct 31
Nov 02      2            Oct 31
Nov 03      3            Oct 31
Nov 05      4            Nov 01  ← key changes due to gap
Nov 06      5            Nov 01
Nov 09      6            Nov 03  ← key changes again
```

In PostgreSQL, `date - integer` returns the date shifted back by that number of days. This creates an **island key** for each island.

### Step 1 — Deduplicate Same-Day Records

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
)
SELECT user_id, activity_date
FROM active_days
ORDER BY user_id, activity_date;
```

Because user 1 has two actions on Nov 01, `DISTINCT` is necessary when the requirement is a **streak by day**, not a streak by event.

### Step 2 — Number Days per User

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
)
SELECT
    user_id,
    activity_date,
    ROW_NUMBER() OVER (
        PARTITION BY user_id
        ORDER BY activity_date
    ) AS rn
FROM active_days
ORDER BY user_id, activity_date;
```

`PARTITION BY user_id` ensures each user's numbering restarts from 1. Because each user now has at most one row per day, `ORDER BY activity_date` fully determines the order within the partition.

### Step 3 — Build the Island Key

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
numbered AS (
    SELECT
        user_id,
        activity_date,
        ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY activity_date
        ) AS rn
    FROM active_days
)
SELECT
    user_id,
    activity_date,
    rn,
    activity_date - rn::integer AS island_key
FROM numbered
ORDER BY user_id, activity_date;
```

Within a truly consecutive run of dates, both `activity_date` and `rn` increment by one, so their difference stays constant. When a day is skipped, the difference shifts and marks a new island.

### Step 4 — Aggregate the Islands

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
numbered AS (
    SELECT
        user_id,
        activity_date,
        activity_date
          - ROW_NUMBER() OVER (
                PARTITION BY user_id
                ORDER BY activity_date
            )::integer AS island_key
    FROM active_days
)
SELECT
    user_id,
    MIN(activity_date) AS streak_start,
    MAX(activity_date) AS streak_end,
    COUNT(*) AS days_in_streak
FROM numbered
GROUP BY user_id, island_key
ORDER BY user_id, streak_start;
```

Expected output:

| user_id | streak_start | streak_end | days_in_streak |
|---:|---|---|---:|
| 1 | 2026-11-01 | 2026-11-03 | 3 |
| 1 | 2026-11-05 | 2026-11-06 | 2 |
| 1 | 2026-11-09 | 2026-11-09 | 1 |
| 2 | 2026-11-01 | 2026-11-01 | 1 |
| 2 | 2026-11-03 | 2026-11-05 | 3 |

This **row-number difference** pattern is very concise and ideal when consecutive means **incrementing by exactly one unit** of a date or integer.

### Limitations of This Technique

1. You must **deduplicate** on the key being evaluated before numbering. If there are two events on the same day, `rn` increments while the date does not, corrupting the island key.
2. It assumes each consecutive step is **one calendar day** or a key unit with matching arithmetic.
3. `ROW_NUMBER()` returns `bigint`; the example casts to `integer` to use the `date - integer` operator. For extremely large datasets, consider cast overflow limits.
4. Do not use this formula directly for **consecutive business days** if weekends/holidays are skipped.
5. Do not blindly apply it to timestamps with variable intervals or timezone/DST effects.

## 6. Technique 2: Using LAG to Detect Gaps

`LAG(value)` returns the value from the **previous row in the window ordering**.

First:

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
)
SELECT
    user_id,
    activity_date,
    LAG(activity_date) OVER (
        PARTITION BY user_id
        ORDER BY activity_date
    ) AS previous_day
FROM active_days
ORDER BY user_id, activity_date;
```

For user 1:

```text
activity_date  previous_day
2026-11-01     NULL
2026-11-02     2026-11-01
2026-11-03     2026-11-02
2026-11-05     2026-11-03  ← missing Nov 04
2026-11-06     2026-11-05
2026-11-09     2026-11-06  ← missing Nov 07–08
```

### Marking the Start of an Island

A day is the **start of an island** when:

- It is the first row (`previous_day IS NULL`), or
- It is **not equal to** `previous_day + 1`.

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
with_previous AS (
    SELECT
        user_id,
        activity_date,
        LAG(activity_date) OVER (
            PARTITION BY user_id
            ORDER BY activity_date
        ) AS previous_day
    FROM active_days
)
SELECT
    user_id,
    activity_date,
    previous_day,
    CASE
        WHEN previous_day IS NULL
          OR activity_date <> previous_day + 1
        THEN 1
        ELSE 0
    END AS starts_new_island
FROM with_previous
ORDER BY user_id, activity_date;
```

### Generating Island Numbers via Running SUM

Whenever a new start marker is encountered, add 1 to the running sum:

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
with_previous AS (
    SELECT
        user_id,
        activity_date,
        LAG(activity_date) OVER (
            PARTITION BY user_id
            ORDER BY activity_date
        ) AS previous_day
    FROM active_days
),
marked AS (
    SELECT
        user_id,
        activity_date,
        CASE
            WHEN previous_day IS NULL
              OR activity_date <> previous_day + 1
            THEN 1
            ELSE 0
        END AS new_group_flag
    FROM with_previous
),
labeled AS (
    SELECT
        user_id,
        activity_date,
        SUM(new_group_flag) OVER (
            PARTITION BY user_id
            ORDER BY activity_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS island_id
    FROM marked
)
SELECT
    user_id,
    island_id,
    MIN(activity_date) AS streak_start,
    MAX(activity_date) AS streak_end,
    COUNT(*) AS days_in_streak
FROM labeled
GROUP BY user_id, island_id
ORDER BY user_id, streak_start;
```

The resulting consecutive streaks match the `ROW_NUMBER` technique above, but `LAG + SUM` is more flexible: the new-group condition can be replaced with any business rule.

### Why Specify the ROWS Frame Explicitly?

For aggregate window functions with `ORDER BY`, PostgreSQL uses default window frame rules that typically involve **peer rows** (rows equal in the sort key). Writing:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

explicitly expresses **row-by-row accumulation**. In addition, a deterministic sort key is needed to avoid ambiguous ordering among tied rows. In the example, `DISTINCT` by date ensures each user has only one row per date.

## 7. Which Gaps-and-Islands Technique Should You Choose?

| Criterion | `ROW_NUMBER` difference key | `LAG`, flag, and `SUM` |
|---|---|---|
| Consecutive means +1 day/integer | Very concise. | Works well, though more steps. |
| Maximum gap threshold rule | Hard to express directly. | Fits naturally by changing the transition condition. |
| Runs of identical states | Requires specialized double-ranking tricks. | Very natural with `LAG(status)`. |
| Duplicate sort keys present | Must be deduplicated beforehand. | Must define a sort key/tie-breaker. |
| Need to explain why a group started | Difference key implicitly encodes gaps. | `new_group_flag` directly explains transitions. |
| Business-day definition needed | Must map to a business-calendar sequence number. | Can compare current day against previous business day. |

Do not force one technique onto every problem. Choose the **simplest formula that faithfully expresses your definition of "consecutive"**.

## 8. Grouping Consecutive State Runs with LAG

In `device_states`, each device has a chronological sequence of states.

```sql
WITH ordered AS (
    SELECT
        device_id,
        state_id,
        changed_at,
        state_name,
        LAG(state_name) OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
        ) AS previous_state
    FROM lesson_window_cases.device_states
),
marked AS (
    SELECT
        *,
        CASE
            WHEN state_name IS DISTINCT FROM previous_state
            THEN 1
            ELSE 0
        END AS starts_new_run
    FROM ordered
),
labeled AS (
    SELECT
        *,
        SUM(starts_new_run) OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS run_id
    FROM marked
)
SELECT
    device_id,
    run_id,
    state_name,
    MIN(changed_at) AS first_observed_at,
    MAX(changed_at) AS last_observed_at,
    COUNT(*) AS observation_count
FROM labeled
GROUP BY device_id, run_id, state_name
ORDER BY device_id, first_observed_at;
```

For device 10:

| run_id | state_name | observation_count |
|---:|---|---:|
| 1 | READY | 2 |
| 2 | ERROR | 2 |
| 3 | READY | 1 |

**Why include `state_id` in `ORDER BY`?** If two rows have the exact same `changed_at`, the timestamp alone does not determine which row comes first. `state_id` provides a **tie-breaker** in the sample dataset.

### Computing Exact State Duration Is a Separate Problem

`MIN(changed_at)` and `MAX(changed_at)` only give the **first/last observation timestamps of each run**, which does not by itself prove how long the state lasted. If rows represent **state transition events**, the effective interval might end when the **next run's event** arrives.

To compute duration properly, you must clarify:

- What event marks **when a state begins**.
- Whether each row is a **repeated observation** or only a change event.
- When there is no subsequent event, whether the end is `NULL`, `now()`, or the reporting window boundary.
- Whether late-arriving events revise historical states.

Do not take `MAX - MIN` of repeated observations as total active duration without business justification.

## 9. Using LAG with Nullable States

`LAG(state_name)` returns SQL `NULL` on the first row by default. If `state_name` itself can legitimately be `NULL`, you must **distinguish the first row from an actual null state**.

In our lab schema, `state_name TEXT NOT NULL`, so:

```sql
state_name IS DISTINCT FROM previous_state
```

suffices to mark the first row as a change, because `state_name` is non-null while `previous_state` on the first row is null.

If status is nullable, you can add `ROW_NUMBER()` to detect the first row:

```sql
WITH ordered AS (
    SELECT
        device_id,
        state_id,
        changed_at,
        state_name,
        ROW_NUMBER() OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
        ) AS rn,
        LAG(state_name) OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
        ) AS previous_state
    FROM lesson_window_cases.device_states
)
SELECT
    *,
    CASE
        WHEN rn = 1
          OR state_name IS DISTINCT FROM previous_state
        THEN 1
        ELSE 0
    END AS starts_new_run
FROM ordered;
```

With this approach, a sequence `NULL, NULL` is treated as the same state **if the business rules define null as a valid state**. If null means missing data and should break the run, a different condition is required.

## 10. Sessionization: Grouping Events Within N Minutes of Each Other

A very practical use of gaps-and-islands is partitioning **activity sessions**. For example, a user has events at 10:00, 10:10, 10:40, 11:20, and 11:35.

Rule: **start a new session if the gap between two consecutive events exceeds 30 minutes**.

```text
10:00 ──10:10 ──────10:40       11:20 ──11:35
   │       │          │           │       │
   └─ 10m ─┘── 30m ───┘           └─15m ──┘

Session 1                     Session 2
          40m gap > 30
```

Construct an example using a `VALUES` CTE:

```sql
WITH events(event_id, user_id, event_at) AS (
    VALUES
        (1, 7, TIMESTAMPTZ '2026-11-14 10:00:00+07'),
        (2, 7, TIMESTAMPTZ '2026-11-14 10:10:00+07'),
        (3, 7, TIMESTAMPTZ '2026-11-14 10:40:00+07'),
        (4, 7, TIMESTAMPTZ '2026-11-14 11:20:00+07'),
        (5, 7, TIMESTAMPTZ '2026-11-14 11:35:00+07')
),
with_previous AS (
    SELECT
        *,
        LAG(event_at) OVER (
            PARTITION BY user_id
            ORDER BY event_at, event_id
        ) AS previous_event_at
    FROM events
),
marked AS (
    SELECT
        *,
        CASE
            WHEN previous_event_at IS NULL
              OR event_at > previous_event_at + INTERVAL '30 minutes'
            THEN 1
            ELSE 0
        END AS starts_new_session
    FROM with_previous
),
labeled AS (
    SELECT
        *,
        SUM(starts_new_session) OVER (
            PARTITION BY user_id
            ORDER BY event_at, event_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS session_no
    FROM marked
)
SELECT
    user_id,
    session_no,
    MIN(event_at) AS session_start,
    MAX(event_at) AS session_last_event,
    COUNT(*) AS event_count
FROM labeled
GROUP BY user_id, session_no
ORDER BY user_id, session_start;
```

Result: session 1 has **3 events**, and session 2 has **2 events**.

### Comparing Against Session Start Time Violates the Rule

The rule here compares the gap against the **immediately preceding event**, not the first event of the session. For example, 10:00, 10:25, 10:50 can belong to the same session because each gap is 25 minutes, even though the last event is 50 minutes after the first.

### Boundary Exactly at the Threshold

Because the condition is:

```sql
event_at > previous_event_at + INTERVAL '30 minutes'
```

two events separated by **exactly 30 minutes** still stay in the same session. If the business rule specifies a gap of **30 minutes or more** starts a new session, change `>` to `>=`.

## 11. Consecutive Business Days

The statement "a user was active for 5 consecutive days" can mean two things:

1. **5 calendar days:** Friday to Monday has two weekend days in between, so it is not consecutive.
2. **5 business days:** Friday to Monday can count as consecutive if the calendar excludes weekends.

For business-day logic, you need a dedicated calendar table, for example:

```text
business_calendar
calendar_date  is_business_day  business_day_no
2026-11-13    true             101
2026-11-14    false            NULL
2026-11-15    false            NULL
2026-11-16    true             102
```

This is a **conceptual diagram**, not data created in the lab schema. The `business_day_no` column is a sequence incrementing by 1 for each business day.

After joining activity with the calendar and filtering out non-business days, `business_day_no - ROW_NUMBER()` can group consecutive business days. Do not apply `date - row_number` directly and expect PostgreSQL to skip Saturdays, Sundays, or company holidays automatically.

Another solution uses `LAG` to compare the current activity date against the **next business day after the previous activity date** from the calendar, and then marks islands.

## 12. Multiple Rows with the Same Sort Key: Peer Rows and Deterministic Ordering

When you write:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY placed_at DESC
)
```

if two orders have the same `placed_at`, PostgreSQL is **not required** to assign 1 to one order and 2 to the other consistently. They are **peer rows** under that sort key.

To make it deterministic:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY placed_at DESC, order_id DESC
)
```

Because `order_id` is the primary key, every row within the partition is distinguishable.

### Why Does This Affect Deduplication?

When you keep `rn = 1` and delete `rn > 1`, without a tie-breaker, **which record gets kept may not be defined by business rules**. Never delete data using only `ORDER BY received_at DESC` when multiple rows share the same `received_at`.

### Watch Out for NULL in Sort Keys

For nullable columns, decide explicitly beforehand:

```sql
ORDER BY processed_at DESC NULLS LAST, record_id DESC
```

In PostgreSQL, default null placement depends on `ASC`/`DESC` direction; explicitly writing `NULLS FIRST` or `NULLS LAST` prevents a record without a timestamp from being selected as the "latest" record.

## 13. Global Top N vs. Top N per Group

This query:

```sql
SELECT order_id, customer_id, placed_at
FROM lesson_window_cases.orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 2;
```

only returns the **two most recent orders across the entire system**.

If you need the **two most recent orders for each customer**, you must compute ordering **per `customer_id`**:

```sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.placed_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT
    customer_id,
    order_id,
    placed_at,
    total_amount,
    rn
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
```

ID results:

| customer_id | rn | order_id | Explanation |
|---:|---:|---:|---|
| 1 | 1 | 1004 | Nov 05, latest for An. |
| 1 | 2 | 1003 | Same timestamp as 1002, but higher ID. |
| 2 | 1 | 2003 | Nov 04 at 14:00. |
| 2 | 2 | 2002 | Nov 04 at 09:00. |
| 3 | 1 | 3001 | Chi has only one order. |

Customer **Dung** has no orders, so she does not appear in a query sourced solely from `orders`.

### Why Wrap in a CTE or Subquery?

Within the same query block, PostgreSQL does not allow window function results directly in `WHERE`, such as:

```sql
-- Invalid:
SELECT *
FROM lesson_window_cases.orders
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY placed_at DESC
) <= 2;
```

Window functions are evaluated logically after `WHERE`, so you need a **CTE or derived table** to expose `rn` as a source column to the outer query:

```sql
SELECT *
FROM (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
) AS ranked
WHERE ranked.rn <= 2;
```

`QUALIFY` exists in some other SQL dialects, but you should not assume it is usable directly in the PostgreSQL environment for this lesson. The CTE/subquery pattern remains the clear, standard way to express this.

## 14. How Do ROW_NUMBER, RANK, and DENSE_RANK Differ?

Suppose we have values ordered from highest to lowest:

```text
900   900   500   300
```

Ranking results:

| total_amount | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 900 | 1 | 1 | 1 |
| 900 | 2 | 1 | 1 |
| 500 | 3 | 3 | 2 |
| 300 | 4 | 4 | 3 |

- **`ROW_NUMBER()`:** assigns a unique sequential number to every row, even on ties. Requires a tie-breaker to be deterministic.
- **`RANK()`:** tied rows receive the same rank; the next rank leaves a **gap**.
- **`DENSE_RANK()`:** tied rows receive the same rank; the next rank has **no gap**.

Illustration on customer An:

```sql
SELECT
    customer_id,
    order_id,
    total_amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY total_amount DESC, order_id DESC
    ) AS row_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total_amount DESC
    ) AS amount_rank,
    DENSE_RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total_amount DESC
    ) AS amount_dense_rank
FROM lesson_window_cases.orders
WHERE customer_id = 1
ORDER BY total_amount DESC, order_id DESC;
```

**Common pitfall:** `RANK()` and `DENSE_RANK()` determine ties based on the **entire `ORDER BY` clause of that specific function**. If you add unique `order_id` to `RANK()`'s `ORDER BY`, two orders with the same `total_amount` will no longer be tied in that window.

Therefore, when you want to **preserve ties by amount**, use `ORDER BY total_amount DESC` inside `RANK()`, whereas when you want to **pick exactly one row**, use `ROW_NUMBER()` with a secondary key.

## 15. "Top 2" Has at Least Three Meanings

With An's values `900, 900, 350, 250`:

### Option A — Exactly Two Rows

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

Each group has **at most 2 rows**. Ties are still broken to return the exact row count using the tie-breaker.

### Option B — Top Two Rank Positions, Keeping Ties

```sql
WITH ranked AS (
    SELECT
        o.*,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS rnk
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount, rnk
FROM ranked
WHERE rnk <= 2
ORDER BY customer_id, rnk, order_id;
```

An has two orders of 900 both at rank 1; the 350 order has rank 3, so it **does not appear**. This means "top 2 positions with ties", not "two distinct price levels".

### Option C — Top Two Highest Value Levels, Keeping All Tied Rows

```sql
WITH ranked AS (
    SELECT
        o.*,
        DENSE_RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS drnk
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount, drnk
FROM ranked
WHERE drnk <= 2
ORDER BY customer_id, drnk, order_id;
```

An gets **three rows**: two orders of 900 and one order of 350. This means "top two distinct value levels", not "top two orders".

**Do not treat the three functions as interchangeable just because they all rank or number rows.** Always ask whether business requirements allow **returning more than N rows on ties**, and **which columns** define a tie.

## 16. FETCH FIRST ... WITH TIES

Supported PostgreSQL versions allow retaining additional tied rows at the boundary of an `ORDER BY` query using this syntax:

```sql
SELECT
    order_id,
    total_amount
FROM lesson_window_cases.orders
WHERE customer_id = 1
ORDER BY total_amount DESC
FETCH FIRST 2 ROWS WITH TIES;
```

This query selects the **first two positions** ordered by `total_amount DESC` and keeps any rows tied with the last selected row. For values 900, 900, 350, 250, the result returns the two 900 rows.

If you use `FETCH FIRST 1 ROW WITH TIES`, both 900 orders are returned.

### Why Omit ID from ORDER BY When Using WITH TIES on Amount?

If you write:

```sql
ORDER BY total_amount DESC, order_id DESC
FETCH FIRST 1 ROW WITH TIES
```

then differing `order_id` values make the two rows **no longer equal across the full sort key**. You will get only one row, even though the amounts match.

Distinguish between:

- The ordering that defines **ties**, which must use only the business tie key.
- The final display order, which can sort further by ID in an **outer query** if needed.

`FETCH ... WITH TIES` over an entire table does not automatically become **top N per group**; to apply it per customer, you can combine it with `LATERAL`.

## 17. Top N per Group Using LEFT JOIN LATERAL

If each customer needs their **two most recent orders** while keeping customers with zero orders:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.placed_at,
    recent.total_amount
FROM lesson_window_cases.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.placed_at,
        o.total_amount
    FROM lesson_window_cases.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.placed_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.placed_at DESC NULLS LAST,
    recent.order_id DESC NULLS LAST;
```

`LATERAL` allows the right-hand subquery to reference `c.customer_id` from the current customer row. With our sample data:

- An → two orders 1004, 1003.
- Bình → two orders 2003, 2002.
- Chi → one order 3001.
- Dung → **one row** with `recent.* = NULL`.

### CROSS JOIN LATERAL vs. LEFT JOIN LATERAL?

`CROSS JOIN LATERAL` drops customers for whom the right-hand subquery returns 0 rows. `LEFT JOIN LATERAL ... ON TRUE` preserves those customers with null right-hand columns, fitting reports that need **all customers**.

### Using Top N WITH TIES Inside LATERAL

When the requirement is the top two highest-amount positions with ties:

```sql
SELECT
    c.customer_id,
    t.order_id,
    t.total_amount
FROM lesson_window_cases.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.total_amount
    FROM lesson_window_cases.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.total_amount DESC
    FETCH FIRST 2 ROWS WITH TIES
) AS t ON TRUE
ORDER BY c.customer_id, t.total_amount DESC NULLS LAST, t.order_id;
```

If you want **two distinct price levels**, `DENSE_RANK() <= 2` is clearer; `FETCH ... WITH TIES` only extends at the boundary of N **rows**, not N distinct levels.

## 18. ROW_NUMBER or LATERAL for Top N?

Both approaches are valid, but they fit different workload shapes.

| Criterion | `ROW_NUMBER` + CTE | `LATERAL` with `ORDER BY ... LIMIT N` |
|---|---|---|
| Many customers, need top N for **all** customers | Natural, set-based. | Also works, though it may run lookups across very many customers. |
| Only a small subset of customers after filtering | May need to consider how many rows get ranked. | Can leverage an index to read N rows per customer. |
| Need to retain customers with no orders | Requires `LEFT JOIN` of ranked results back to customers. | `LEFT JOIN LATERAL` is direct and explicit. |
| Need additional rank/dense rank columns | Easy to combine multiple window functions. | Possible with other queries, though not always convenient. |
| Supporting index | Helps sort by partition/order key. | Helps fast per-customer lookup and top-N fetch. |
| Performance | Depends on row count, statistics, filters, and planner. | Depends on left-side customer count, N, and indexes. |

**There is no rule that "LATERAL is always faster than window functions"**. Use `EXPLAIN (ANALYZE, BUFFERS)` on real data to decide, especially when customer count is very large.

## 19. Top 1 per Group Using DISTINCT ON

PostgreSQL provides **`DISTINCT ON`** — a concise syntax to keep **the first row according to a specified ordering** for each group of values.

```sql
SELECT DISTINCT ON (o.customer_id)
    o.customer_id,
    o.order_id,
    o.placed_at,
    o.total_amount
FROM lesson_window_cases.orders AS o
ORDER BY
    o.customer_id,
    o.placed_at DESC,
    o.order_id DESC;
```

Each `customer_id` keeps the first row under this order:

1. Grouped by customer_id.
2. Within each group, latest `placed_at` comes first.
3. On equal timestamps, larger `order_id` comes first.

Result: An 1004, Bình 2003, Chi 3001.

### Important Syntax Rule for DISTINCT ON

With `DISTINCT ON (customer_id)`, the leftmost expressions of `ORDER BY` must match the expressions in `DISTINCT ON` according to PostgreSQL's rule.

Do not write:

```sql
-- Violates DISTINCT ON rule:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id
FROM lesson_window_cases.orders
ORDER BY placed_at DESC, customer_id;
```

Fix it with:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, placed_at
FROM lesson_window_cases.orders
ORDER BY customer_id, placed_at DESC, order_id DESC;
```

### Sorting the Final Result Globally by Time

After picking one order per customer, if you want to sort customers by their latest order:

```sql
SELECT *
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id, order_id, placed_at
    FROM lesson_window_cases.orders
    ORDER BY customer_id, placed_at DESC, order_id DESC
) AS latest_per_customer
ORDER BY placed_at DESC, order_id DESC;
```

Distinguish between the **representative-selection ordering in the subquery** and the **display ordering in the outer query**.

### DISTINCT ON Is Not Universal Standard SQL

`DISTINCT ON` is a PostgreSQL-specific feature. If you need SQL portable across multiple database engines, `ROW_NUMBER()` with a CTE/subquery is usually the more portable choice.

## 20. Top 1 and Handling Ties

`DISTINCT ON` and `ROW_NUMBER() = 1` always select **at most one row** per group after applying the ordering, whereas `RANK() = 1` or `DENSE_RANK() = 1` can return **multiple tied rows**.

Example: "each customer's **highest-value** order":

```sql
WITH ranked AS (
    SELECT
        o.*,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_rank
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount
FROM ranked
WHERE amount_rank = 1
ORDER BY customer_id, order_id;
```

An has **two orders tied at 900,000**, so the query returns both 1002 and 1003. If a single representative order is required, add secondary tie-breakers such as `placed_at DESC, order_id DESC` with `ROW_NUMBER` or `DISTINCT ON`.

Do not confuse "the single most expensive order" with "all orders tied for highest value" or "the most recent order". Superlatives like **"most" / "-est"** in business requirements must be translated into one or more exact sort keys.

## 21. Filter Status Before or After Computing Top N?

This is a critical distinction.

### Requirement A — Each Customer's Two Most Recent PAID Orders

You must **filter PAID before** ranking:

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
    WHERE o.status = 'PAID'
)
SELECT customer_id, order_id, status, rn
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

### Requirement B — Two Most Recent Orders Regardless of Status, Then Show Only PAID

You must **rank all rows first, then filter PAID outside**:

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, status, rn
FROM ranked
WHERE rn <= 2
  AND status = 'PAID'
ORDER BY customer_id, rn;
```

These two requirements are **not equivalent**. For An, the two most recent orders are 1004 (PAID) and 1003 (PENDING). Requirement B returns only 1004, whereas Requirement A can return both 1004 and 1002.

This is the difference between **filtering before ranking** and **filtering after ranking**, not merely a matter of SQL style.

## 22. Top N Combined with JSON Aggregation

An API often wants **one row per customer** containing a JSON list of their N most recent orders.

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.placed_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
),
top_orders AS (
    SELECT *
    FROM ranked
    WHERE rn <= 2
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'order_id', t.order_id,
                'total_amount', t.total_amount,
                'status', t.status
            )
            ORDER BY t.rn
        ) FILTER (WHERE t.order_id IS NOT NULL),
        '[]'::jsonb
    ) AS recent_orders
FROM lesson_window_cases.customers AS c
LEFT JOIN top_orders AS t
  ON t.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Notes:

- `ROW_NUMBER` determines **which orders belong to the top N**.
- `jsonb_agg(... ORDER BY t.rn)` determines **the order of elements inside the JSON array**.
- `FILTER` excludes null-extended rows produced by `LEFT JOIN` for customers without orders.
- `COALESCE` returns `[]` instead of SQL `NULL` for customer Dung.

Do not rely on `ORDER BY` inside the window to automatically preserve JSON array element order if `jsonb_agg` lacks its own `ORDER BY`.

## 23. "Deduplication" Requires Defining Duplicates First

Two rows can match on several columns and still be **two distinct valid events**. For example:

- Two orders from An with the same amount 900,000 are **not the same order** if their `order_id` differs.
- Two activities on the same day **can be collapsed into one active day** for streak statistics, but you should not delete the events if they represent two real actions.
- Two records with the same `tenant_id, event_key` from a sync source **may be the same event** delivered multiple times.

Before writing `ROW_NUMBER() OVER (PARTITION BY ...)`, you must answer:

1. **Which business key defines a duplicate?** `(tenant_id,event_key)`, normalized email, external system ID, or a combination of columns?
2. **Does data need normalization** before comparison (trim, lowercase, formatting, timezone)?
3. When two records duplicate, **which one should be kept**: most recently received, most recently updated, highest confidence, or confirmed?
4. If the primary criterion ties, what is the **tie-breaker key**?
5. Should duplicate records be **kept for audit history** or physically deleted?

Without answers to these questions, a "deduplicate" operation can delete valid data.

## 24. Detecting Duplicate Groups

In `raw_events`, the business rule is one unique event per `(tenant_id, event_key)`.

Find groups with multiple records:

```sql
SELECT
    tenant_id,
    event_key,
    COUNT(*) AS duplicate_count
FROM lesson_window_cases.raw_events
GROUP BY tenant_id, event_key
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, tenant_id, event_key;
```

Expected output:

| tenant_id | event_key | duplicate_count |
|---:|---|---:|
| 1 | evt-A | 3 |
| 2 | evt-C | 2 |

`HAVING COUNT(*) > 1` identifies the **duplicated groups**, but does not yet decide **which row to keep**.

### Counting Redundant Rows

```sql
WITH duplicates AS (
    SELECT
        tenant_id,
        event_key,
        COUNT(*) AS cnt
    FROM lesson_window_cases.raw_events
    GROUP BY tenant_id, event_key
    HAVING COUNT(*) > 1
)
SELECT SUM(cnt - 1) AS extra_rows
FROM duplicates;
```

In the lab dataset, there are **3 redundant rows** (two in tenant 1 / evt-A and one in tenant 2 / evt-C). If there are no duplicate groups, `SUM` over an empty set returns SQL `NULL`; wrap in `COALESCE(..., 0)` if a report requires 0.

## 25. Deduplicating with ROW_NUMBER: Keeping the Latest Record

Define the record to keep:

> For each `(tenant_id, event_key)`, keep the row with the largest `received_at`. On ties, keep the row with the largest `event_id`.

Query:

```sql
WITH ranked_events AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.tenant_id, e.event_key
            ORDER BY e.received_at DESC, e.event_id DESC
        ) AS rn
    FROM lesson_window_cases.raw_events AS e
)
SELECT
    tenant_id,
    event_key,
    event_id,
    received_at,
    payload
FROM ranked_events
WHERE rn = 1
ORDER BY tenant_id, event_key;
```

Representative results:

| tenant_id | event_key | retained event_id |
|---:|---|---:|
| 1 | evt-A | 5003 |
| 1 | evt-B | 5004 |
| 2 | evt-A | 6001 |
| 2 | evt-C | 6003 |

**Why 5003 instead of 5002?** They share the same `received_at`, but `event_id = 5003` is larger, establishing a total order under the chosen rule.

### A Tie-Breaker Key Does Not Automatically Prove "Newer" Business-Wise

`event_id DESC` is only a **deterministic** rule in the sample dataset. If IDs are generated by a distributed system, a larger number **does not necessarily mean the event occurred later**. If you must keep the newest data by **source version**, use the source's authoritative version/sequence rather than blindly trusting an auto-increment ID in the target database.

## 26. Deduplicating with DISTINCT ON in PostgreSQL

The same representative output can be written concisely:

```sql
SELECT DISTINCT ON (tenant_id, event_key)
    tenant_id,
    event_key,
    event_id,
    received_at,
    payload
FROM lesson_window_cases.raw_events
ORDER BY
    tenant_id,
    event_key,
    received_at DESC,
    event_id DESC;
```

`DISTINCT ON (tenant_id, event_key)` keeps the **first row** in each group according to the supplied `ORDER BY`.

### Comparing DISTINCT ON vs. ROW_NUMBER

| Characteristic | `DISTINCT ON` | `ROW_NUMBER` |
|---|---|---|
| Picking exactly one row/group | Very concise. | Adds a CTE/subquery, though row numbering is explicit. |
| Picking top N with N > 1 | Not directly supported. | `rn <= N` fits cleanly. |
| Keeping all tied rows | No. | Use `RANK/DENSE_RANK` when needed. |
| Portability across DBMSs | PostgreSQL-specific. | Window functions are more widely supported. |
| Inspecting redundant rows to delete | Does not directly expose all `rn > 1`. | Convenient. |
| Tie-breaking rules | Needs a complete `ORDER BY`. | Needs a complete `ORDER BY` in `OVER`. |

There is no absolute rule that one is always faster than the other; the planner, indexes, and data volume decide.

## 27. Plain DISTINCT Is Not Selecting a Representative Record

`SELECT DISTINCT tenant_id, event_key` only returns **distinct key combinations**:

```sql
SELECT DISTINCT tenant_id, event_key
FROM lesson_window_cases.raw_events
ORDER BY tenant_id, event_key;
```

However, if you include payload or `received_at`:

```sql
SELECT DISTINCT tenant_id, event_key, received_at, payload
FROM lesson_window_cases.raw_events;
```

then multiple rows with the same business key still appear because payload/timestamp differ. `DISTINCT` deduplicates across **all selected expressions**; it does not infer which key represents business identity.

When you want one complete row **by a latest-record rule**, use `ROW_NUMBER`/`DISTINCT ON` or an equivalent ordering-based construct.

### Do Not Use MIN/MAX and Then Pick Unrelated Columns

For example:

```sql
SELECT tenant_id, event_key, MAX(received_at)
FROM lesson_window_cases.raw_events
GROUP BY tenant_id, event_key;
```

returns the latest timestamp, but **does not uniquely identify which row's payload belongs to it** if multiple events share that timestamp. Joining back to the table on `received_at = MAX(...)` can still return multiple rows. `ROW_NUMBER` with a tie-breaker solves representative selection cleanly.

## 28. Previewing Rows to Be Deleted

If the data truly suffers from duplication bugs and cleanup is authorized, the first step is a **verification SELECT**:

```sql
WITH ranked_events AS (
    SELECT
        e.event_id,
        e.tenant_id,
        e.event_key,
        e.received_at,
        ROW_NUMBER() OVER (
            PARTITION BY e.tenant_id, e.event_key
            ORDER BY e.received_at DESC, e.event_id DESC
        ) AS rn
    FROM lesson_window_cases.raw_events AS e
)
SELECT
    event_id,
    tenant_id,
    event_key,
    received_at,
    rn
FROM ranked_events
WHERE rn > 1
ORDER BY tenant_id, event_key, rn;
```

In the lab, this set consists of 5002, 5001, and 6002, while 5003/5004/6001/6003 are retained.

### Checklist Before Deleting

- Is physical deletion allowed, or must **audit/source history** be preserved?
- Are there foreign keys from other tables referencing the `event_id` values to be deleted?
- Is the kept record genuinely the authoritative one?
- Is any live ingestion batch currently writing new data?
- Do you have a backup/rollback capability?
- Should cleanup run in per-tenant or batched chunks to avoid holding table locks too long?

Counting duplicates and previewing candidate deletions are separate steps from running `DELETE`.

## 29. Deleting Duplicates via CTE and DELETE ... USING

Example **for database lab use only**, or after approval with an appropriate transaction plan:

```sql
BEGIN;

WITH ranked_events AS (
    SELECT
        e.event_id,
        ROW_NUMBER() OVER (
            PARTITION BY e.tenant_id, e.event_key
            ORDER BY e.received_at DESC, e.event_id DESC
        ) AS rn
    FROM lesson_window_cases.raw_events AS e
)
DELETE FROM lesson_window_cases.raw_events AS e
USING ranked_events AS r
WHERE e.event_id = r.event_id
  AND r.rn > 1
RETURNING
    e.event_id,
    e.tenant_id,
    e.event_key,
    e.received_at;

-- In lab: use ROLLBACK to avoid modifying sample data,
-- or COMMIT only after authorization and verification of results.
ROLLBACK;
```

How it works:

1. The CTE numbers each row within each business key.
2. Keeping `rn = 1`, it selects IDs where `rn > 1`.
3. `DELETE ... USING` joins back to the target table via the **`event_id` primary key**.
4. `RETURNING` displays the rows affected inside the transaction.
5. `ROLLBACK` in the example reverts the operation so the lab dataset stays intact.

### Why Avoid DELETE WHERE received_at < MAX(...)?

If two records share the **same latest timestamp**, both can survive. If you delete blindly by smaller/larger ID without consistent rules, you can keep the wrong payload. `ROW_NUMBER` with a tie-breaker expresses the "keep exactly one" rule completely.

### Caution: A Snapshot Does Not Lock Out All Races

Running the ranking CTE and `DELETE` inside one transaction does not by itself prevent **another ingestion worker from inserting new duplicates** concurrently or immediately afterward. To prevent recurrence, you must enforce a **unique constraint** and design an idempotent write path.

## 30. Preventing Recurrence with UNIQUE

After cleaning and verifying the source data, if the rule is **one row per tenant and event_key in the canonical table**, you can add:

```sql
ALTER TABLE lesson_window_cases.raw_events
ADD CONSTRAINT uq_raw_events_tenant_key
UNIQUE (tenant_id, event_key);
```

**This command will fail if run before duplicate data is actually removed**. Because the previous section ended with `ROLLBACK`, the lab table still contains duplicates; to test `UNIQUE` succeeding, intentionally clean up in a separate lab first and then run the command.

### Should raw_events Have a UNIQUE Constraint?

The name `raw_events` suggests **raw log data that may intentionally keep every delivery**. When auditing or pipeline replays are needed, **you should not delete raw deliveries**. A common design separates:

```text
raw_events (append-only, stores every delivery)
        │
        │ deduplicate and select canonical record
        ▼
canonical_events (UNIQUE tenant_id, event_key)
        │
        ▼
downstream reporting / business logic
```

In that model, `UNIQUE` lives on the **canonical table**, while `raw_events` is still allowed to hold repeated deliveries for auditability. Choose the model matching your retention requirements before modifying data.

### Nullable Business Keys

`GROUP BY`/`PARTITION BY` groups nulls according to SQL grouping semantics, whereas a standard **`UNIQUE`** constraint in PostgreSQL allows multiple rows containing null in a key column. On supported versions, `UNIQUE NULLS NOT DISTINCT` changes that semantics if nulls should be treated as duplicates.

The lab schema declares `tenant_id NOT NULL` and `event_key NOT NULL`, so the examples do not encounter this case. On other schemas, explicitly decide whether null means "unknown ID" or "a real key value".

## 31. UPSERT / Idempotency for Repeated Event Delivery

When the canonical table has a constraint:

```sql
CREATE TABLE lesson_window_cases.canonical_events (
    tenant_id BIGINT NOT NULL,
    event_key TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, event_key)
);
```

You can write with the rule **"update only if the newly arriving event has a strictly greater received_at"**:

```sql
INSERT INTO lesson_window_cases.canonical_events AS c (
    tenant_id, event_key, received_at, payload
)
VALUES (
    1,
    'evt-A',
    TIMESTAMPTZ '2026-11-13 09:00:00+07',
    '{"version":4}'::jsonb
)
ON CONFLICT (tenant_id, event_key)
DO UPDATE SET
    received_at = EXCLUDED.received_at,
    payload = EXCLUDED.payload
WHERE EXCLUDED.received_at > c.received_at;
```

Meaning:

- If the key does not exist yet, insert the new row.
- If the key already exists and the new timestamp is **greater**, update it.
- If the timestamp is equal or older, do not overwrite due to the `WHERE` clause.

Here **equal timestamps do not trigger an update**, unlike the rule keeping the highest `event_id` in the delete-dedup example. In a real system, align tie-breaking with an **authoritative source ordering**, such as `source_sequence`, `source_version`, or a guaranteed ordered ID.

For concurrent writers, PostgreSQL checks conflicts on the unique index and handles key-level upsert atomically; this is safer than a "SELECT to check existence, then INSERT" pattern, which is prone to race conditions.

**Do not equate "received later" with "occurred later".** `received_at` is when the database/consumer received the data, distinct from `occurred_at` or an event version from the source.

## 32. Deduplication with NULLs, Casing, and Whitespace

Defining duplicates often involves data normalization. For emails:

```text
"An@Example.Com"
"an@example.com"
" an@example.com "
```

Three character-different strings may need to be treated as the same key under your application's email policy.

An illustrative query:

```sql
WITH source(email) AS (
    VALUES
        ('An@Example.Com'),
        ('an@example.com'),
        (' an@example.com ')
),
normalized AS (
    SELECT
        email,
        lower(btrim(email)) AS normalized_email
    FROM source
)
SELECT
    email,
    normalized_email,
    ROW_NUMBER() OVER (
        PARTITION BY normalized_email
        ORDER BY email
    ) AS rn
FROM normalized;
```

This is just one example of **string normalization**. Production email rules can be more complex, subject to collation, Unicode normalization, domain rules, and business policy.

### Avoid Aggressive "Looks Similar" Matching That Corrupts Valid Data

Do not arbitrarily apply `lower`/`trim` to every key:

- Product codes can be case-sensitive.
- External IDs can contain meaningful whitespace.
- Unicode/collation has subtle rules.
- Two records sharing the same name are not necessarily the same entity.

The `PARTITION BY` key must reflect a **verified identity rule**, not just a SQL trick.

## 33. Deduplication and Late-Arriving Records

Event data often has multiple timestamps:

| Field | Meaning |
|---|---|
| `occurred_at` | When the event actually happened at the source. |
| `produced_at` | When the source generated the message. |
| `received_at` | When the target system received the message. |
| `processed_at` | When the pipeline processed the message. |
| `source_version` | Version/sequence order from the source, if available. |

If the goal is the **latest entity state**, `source_version DESC` may be more appropriate than `received_at DESC`. If the goal is the **most recently received payload**, `received_at DESC` fits.

Example with two messages:

```text
source version 10 ── received 10:05
source version  9 ── received 10:10 (late arrival)
```

If you pick `MAX(received_at)`, you keep version 9 even though the source already produced version 10. Define **recency by source semantics** rather than defaulting to receipt time.

### Do Not Rely on "Max Timestamp" as a Unique Duplicate Guard

Two events from multiple producers can share identical timestamps due to clock skew or coarse precision. You need a reliable business key/sequence, plus explicit tie-breaking when values match.

## 34. Window Frames: ROWS vs. RANGE for Consecutive Grouping

Ranking functions such as `ROW_NUMBER`/`RANK`/`DENSE_RANK` use the partition ordering and do not have their ranking semantics altered by window frames the way running aggregates do.

However, with:

```sql
SUM(starts_new_run) OVER (
    PARTITION BY device_id
    ORDER BY changed_at
)
```

PostgreSQL defaults to a **frame** governed by peer-row rules, rather than always summing strictly row by row. When numbering islands per event, write:

```sql
SUM(starts_new_run) OVER (
    PARTITION BY device_id
    ORDER BY changed_at, state_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

This makes two things explicit:

1. There is a **deterministic ordering** for every event using `state_id`.
2. The running sum includes **all preceding rows and the current row** in that exact order.

### Do Not Use RANGE for "Preceding 30 Minutes" Sessionization

`RANGE BETWEEN INTERVAL '30 minutes' PRECEDING AND CURRENT ROW` defines a **value-based window frame around the sort key**, not a way to split sessions where each event is within 30 minutes of the immediately preceding event. Sessionization requires `LAG`, a transition flag, and a running sum (or an equivalent mechanism).

## 35. Using LEAD to Find Segment End Timestamps

`LEAD(value)` returns a value from the **next row** in the window ordering. For state-transition events, it helps find the timestamp of the next event:

```sql
SELECT
    device_id,
    state_id,
    changed_at AS valid_from,
    LEAD(changed_at) OVER (
        PARTITION BY device_id
        ORDER BY changed_at, state_id
    ) AS next_event_at,
    state_name
FROM lesson_window_cases.device_states
ORDER BY device_id, changed_at, state_id;
```

If each row is **an event initiating a state's validity**, you can represent the interval `[valid_from, next_event_at)` for each event (assuming accurate timestamps/ordering).

**However**, the lab data has two consecutive `READY` observations; if each row is merely an **observation** rather than a state transition, validity intervals must be derived differently. Do not infer state duration blindly from two consecutive events with the same label.

### The Last Event Has No Following Timestamp

`LEAD` returns SQL `NULL` on the last row of each partition. If an **unbounded upper endpoint** is needed, you can use `tstzrange(valid_from, NULL, '[)')` in an appropriate historical model, rather than replacing `NULL` with `now()` unless the report explicitly truncates at the current time.

## 36. Indexes Supporting Top-N and Deduplication

Window functions define query logic; performance also depends on **data volume, filtering, ordering, and indexes**.

### Index for Top N Most Recent Orders per Customer

```sql
CREATE INDEX ix_orders_customer_recent
ON lesson_window_cases.orders (
    customer_id,
    placed_at DESC,
    order_id DESC
);
```

This index aligns with:

```sql
WHERE customer_id = ?
ORDER BY placed_at DESC, order_id DESC
LIMIT 2
```

and can support window plans sharing the same partition/order keys. However, **there is no guarantee the planner will always use the index**, especially on small tables or when queries read nearly every row.

### Index for Deduplication by Key and Latest Ordering

```sql
CREATE INDEX ix_events_group_latest
ON lesson_window_cases.raw_events (
    tenant_id,
    event_key,
    received_at DESC,
    event_id DESC
);
```

It can help locate groups and order by the columns used in `ROW_NUMBER`/`DISTINCT ON`.

### Non-Unique Indexes Do Not Replace UNIQUE

A non-unique B-tree index only accelerates lookups; it **does not forbid** two rows with the same `(tenant_id,event_key)`. If uniqueness is an invariant, enforce an appropriate **unique constraint/index** on the canonical table.

### Write Overhead and Storage Cost

Every index adds INSERT/UPDATE/DELETE overhead, WAL volume, and disk usage. Do not create multiple nearly redundant indexes just because they appear in examples. Measure real workloads and inspect existing constraint-backed indexes before adding more.

## 37. EXPLAIN ANALYZE for Window Functions

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH ranked AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.placed_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.placed_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT *
FROM ranked
WHERE rn <= 2;
```

When reading the plan, inspect:

- `WindowAgg` or related window nodes.
- Whether `Sort`/`Incremental Sort` occurs or a matching index scan is used.
- Estimated rows versus actual rows.
- Source row counts before and after filtering `rn <= 2`.
- Buffer hits/reads and execution time.

`EXPLAIN (ANALYZE, BUFFERS)` **actually executes the query**, so use `SELECT` queries in practice. When analyzing `DELETE` statements, wrap them in a transaction with rollback and understand the impact before running explain analyze.

### Window Functions Do Not Automatically Guarantee "Read Only N Rows per Partition"

Some plans can optimize ranking filters, but you must not assume `ROW_NUMBER() <= 2` means PostgreSQL only reads the first two rows of every partition. With millions of rows and huge groups, sorting/scanning costs still matter.

`LATERAL` with `LIMIT N` and an index on `(partition_key, sort_key DESC)` can be advantageous when the left-side group count is small; measure rather than assume.

## 38. Common Pitfalls

### 38.1. Failing to Deduplicate Before Computing Daily Streaks

Two actions on the same day increment `ROW_NUMBER` twice while the date does not advance, causing `date - rn` to shift the island key erroneously. Use `SELECT DISTINCT user_id, activity_date` or aggregate to the right grain first.

### 38.2. Using GROUP BY status and Assuming Consecutive Runs

`READY → ERROR → READY` must yield three runs, not one READY group and one ERROR group. Use `LAG` and a running `SUM`.

### 38.3. Omitting PARTITION BY

Without `PARTITION BY customer_id`, `ROW_NUMBER` returns the **global** top N rather than top N per customer.

### 38.4. Missing a Tie-Breaker Key

Two rows with identical timestamps can swap order depending on the plan. When picking a representative or deleting duplicates, include a unique key in `ORDER BY`.

### 38.5. Using RANK with a Unique Key and Wondering Why There Are No Ties

`RANK() OVER (ORDER BY amount DESC, order_id DESC)` treats two rows with the same amount and different IDs as non-peers. To keep ties by amount, sort only by `amount` in the rank window.

### 38.6. Filtering DENSE_RANK <= N While Expecting Exactly N Rows

`DENSE_RANK` selects N distinct value tiers; one tier may contain many rows. If you want at most N rows, use `ROW_NUMBER`.

### 38.7. Using LIMIT N and Assuming It Means Top N per Customer

An outer `LIMIT N` does not apply separately per `customer_id`. Use a window function or `LATERAL`.

### 38.8. Calling a Window Function in WHERE

Window functions are invalid directly inside `WHERE`/`HAVING` of the same query block. Compute them in a CTE and filter in the outer query.

### 38.9. Filtering at the Wrong Stage

"Top 2 PAID" and "top 2 overall, then keep PAID" are different. Clarify the filtering stage before writing SQL.

### 38.10. Using DISTINCT Over All Columns Instead of Key-Based Deduplication

`SELECT DISTINCT *` only removes rows identical across every column; differing payloads or ingestion timestamps still leave multiple rows. Partition by the business key or use `DISTINCT ON`.

### 38.11. Joining on MAX Timestamp and Still Getting Two Rows

Two rows sharing the maximum timestamp will both match. Use a tie-breaker with `ROW_NUMBER`/`DISTINCT ON`.

### 38.12. Deleting Duplicates Directly Without Previewing

Never run destructive `DELETE` statements before verifying duplicate keys, retention criteria, foreign keys, audit requirements, backups, and concurrency.

### 38.13. Cleaning Up Once Without Blocking Recurrence

If the pipeline continues inserting the same key without a unique constraint or upsert, duplicates will immediately return. Design canonical tables and enforce invariants at the write layer.

### 38.14. Using received_at Instead of source_version

A late-arriving message may carry an older version. Define "latest" by **business semantics**, not by default ingestion clock time.

### 38.15. Using Calendar Dates for Consecutive Business Days

Friday and Monday are not adjacent calendar days; computing business-day streaks requires a business calendar.

### 38.16. Using COUNT(*) After LEFT JOIN and Assuming It Counts Child Rows

A parent row with zero children still produces one null-extended row, so `COUNT(*)` yields 1. Use `COUNT(child.primary_key)` when counting child records.

### 38.17. Relying on Window ORDER BY to Sort a JSON Array

The `jsonb_agg` aggregate needs an `ORDER BY` **inside the aggregate** to guarantee element order. Window ordering only computes `rn`/rank.

### 38.18. Assuming NOW() Provides Per-Row Event Ordering

`now()` typically returns transaction start time, so many rows can share the same value. Use an appropriate tie-breaker or version key when picking one record.

### 38.19. Confusing a READ COMMITTED Snapshot with a Data Invariant

A deduplicating `SELECT` sees only a snapshot under transaction isolation; it does not lock future inserts. Use constraints and proper write protocols.

### 38.20. Optimizing Based on a Few-Row Lab Table

Sequential scans are normal on tiny tables. Never conclude an index is broken just because the planner skips it on a toy example.

## 39. SQL and JDBC: Applying Top N in an API

With Java/JDBC, you can pass N and a customer filter via `PreparedStatement`:

```java
String sql = """
    WITH ranked AS (
        SELECT
            o.order_id,
            o.customer_id,
            o.placed_at,
            o.total_amount,
            ROW_NUMBER() OVER (
                PARTITION BY o.customer_id
                ORDER BY o.placed_at DESC, o.order_id DESC
            ) AS rn
        FROM lesson_window_cases.orders AS o
        WHERE o.customer_id = ?
    )
    SELECT order_id, customer_id, placed_at, total_amount
    FROM ranked
    WHERE rn <= ?
    ORDER BY rn
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    ps.setInt(2, 3);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            long customerId = rs.getLong("customer_id");
            java.sql.Timestamp placedAt = rs.getTimestamp("placed_at");
            java.math.BigDecimal amount = rs.getBigDecimal("total_amount");
            // Map to an appropriate DTO, preserving the requested order.
        }
    }
}
```

This example assumes `connection` exists and sits inside a method handling `SQLException`. When handling `timestamptz` in modern applications, use appropriate mappings such as `OffsetDateTime` as supported by your JDBC driver/framework rather than converting timestamps to arbitrary timezone strings.

### Bounding N from Requests

Do not let clients request arbitrarily large N values. The application should validate `1 <= N <= MAX_ALLOWED` according to API policy. Parameter placeholders `?` bind **values**, not column names in `ORDER BY`; if dynamic sort fields are supported, map them through an internal whitelist.

### Deterministic Ordering for Pagination

An API using `LIMIT/OFFSET` or ranking needs a **deterministic sort order**. Without a tie-breaker, orders sharing a timestamp can appear across multiple pages or be skipped between reads. Under continuous writes, **keyset pagination** or an appropriate snapshot/consistency policy can be more stable than offsets.

## 40. Problem-Solving Workflows

### For Consecutive Groups (Gaps and Islands)

1. Identify the **row grain**: event, unique day, state, or time interval.
2. Identify the **partition key**: user, device, tenant, or entity.
3. Define a **complete ordering**, with a tie-breaker when needed.
4. Define the **boundary rule**: 1-day increment, > 30 minutes, state change, etc.
5. Choose `ROW_NUMBER` difference or `LAG` + group-start flag.
6. Use a running `SUM` to assign group IDs if choosing the `LAG` approach.
7. `GROUP BY` group ID to compute min/max/count.
8. Compute "duration" only when event and time semantics justify it.

### For Top N per Group

1. Clarify whether N means **N rows** or **N rank/value tiers**.
2. Clarify whether filters apply **before or after ranking**.
3. Define sort keys and tie-breakers.
4. Use `ROW_NUMBER` for at most N rows; `RANK`/`DENSE_RANK` if ties are needed.
5. Consider `DISTINCT ON` for top 1 or `LATERAL` for top N with supporting indexes.
6. When joining to a parent table, decide whether parents without child rows must be retained.
7. Measure performance and verify results on datasets containing ties and nulls.

### For Deduplication

1. Identify the **business key** and normalization rules.
2. Define the **representative record** by version/timestamp/priority.
3. Add a unique, business-approved tie-breaker sort key.
4. Run `SELECT` to inspect duplicate groups and rows marked for removal.
5. Decide whether to **retain raw audit history** or delete physically.
6. Use a rollback-capable transaction when executing cleanup.
7. Enforce a unique constraint and idempotent writes on the canonical table.
8. Monitor new duplicates and maintain a late-event handling policy.

## 41. Practice Exercises

### Exercise 1 — Row Number per Customer

Use `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY placed_at DESC, order_id DESC)`. Explain why 1003 comes before 1002 when both share the same timestamp, and why `ROW_NUMBER` cannot be used directly in the `WHERE` clause of the same query block.

### Exercise 2 — Top 2 Orders per Customer

Write a CTE returning at most two latest orders per customer. Compare the result against `ORDER BY placed_at DESC LIMIT 2` applied globally to the table.

### Exercise 3 — Retaining Customers Without Orders

Write a `LEFT JOIN LATERAL` from `customers` to `orders` to fetch the two most recent orders. Verify whether customer Dung appears, and what values her order columns hold.

### Exercise 4 — Top 2 PAID

Write two queries:

1. Top 2 most recent `PAID` orders per customer.
2. Top 2 most recent orders regardless of status, then display only `PAID`.

Explain why the two queries can return different results for customer An.

### Exercise 5 — ROW_NUMBER, RANK, and DENSE_RANK

On An's orders, compute all three ranking functions ordered by `total_amount DESC`. Add `order_id DESC` as a tie-breaker for `ROW_NUMBER`. Record the output for the two orders priced at 900,000 and the order priced at 350,000.

### Exercise 6 — Top Two Positions or Top Two Price Levels?

Write two queries by order amount:

- `RANK() <= 2`.
- `DENSE_RANK() <= 2`.

Explain why customer An receives a different number of rows under the two approaches.

### Exercise 7 — Top 1 with DISTINCT ON

Write `DISTINCT ON (customer_id)` to retrieve each customer's latest order using `ORDER BY customer_id, placed_at DESC, order_id DESC`. Then wrap the query to sort the final rows globally by `placed_at DESC`.

### Exercise 8 — Deduplicated Active Days

From `daily_activity`, build a `DISTINCT (user_id, activity_date)` set. Explain why duplicate Nov 01 rows for user 1 must be removed before calculating consecutive-day streaks.

### Exercise 9 — ROW_NUMBER Difference

Compute `activity_date - rn::integer` and group by `user_id, island_key` to return `MIN(date)`, `MAX(date)`, and `COUNT(*)`. Verify that user 1 has three islands of 3, 2, and 1 days.

### Exercise 10 — LAG and Running SUM

Re-solve Exercise 9 using `LAG(activity_date)`, an island-start flag, and `SUM(flag) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`. Compare extensibility when gap rules change.

### Exercise 11 — State Sequence Runs

Using `device_states`, find each `READY`/`ERROR` run ordered by `device_id, changed_at, state_id`. Why is `GROUP BY device_id, state_name` alone insufficient?

### Exercise 12 — 30-Minute Sessionization

Create user events at 10:00, 10:10, 10:40, 11:20, and 11:35. Use `LAG` to identify sessions when a gap is **strictly greater than** 30 minutes. Try changing the rule to **30 minutes or more** and compare the output.

### Exercise 13 — Consecutive Business Days

Propose a `business_calendar(calendar_date, is_business_day, business_day_no)` table. Use consecutive business-day numbers to compute streaks skipping weekends; explain why calendar-based `date - ROW_NUMBER` is insufficient.

### Exercise 14 — Finding Duplicate Groups in raw_events

Use `GROUP BY tenant_id, event_key HAVING COUNT(*) > 1` to find repeated keys. Predict the number of extra records and explain why `tenant_id` is part of the key.

### Exercise 15 — Selecting a Representative Record

Write `ROW_NUMBER() OVER (PARTITION BY tenant_id, event_key ORDER BY received_at DESC, event_id DESC)`. List the retained IDs for keys `evt-A`/`evt-C`. Why would omitting `event_id` make selection ambiguous for tenant 1 / evt-A?

### Exercise 16 — Comparing DISTINCT and DISTINCT ON

Explain why `SELECT DISTINCT tenant_id,event_key,received_at,payload` does not guarantee one row per key. Rewrite it using `DISTINCT ON (tenant_id,event_key)` with the exact representative-selection ordering.

### Exercise 17 — Previewing Before Deleting

Write a **SELECT-only** query for rows with `rn > 1` from `raw_events`. Then describe how to use `DELETE ... USING` with primary key `event_id`, `RETURNING`, and a rollback-capable transaction. Do not delete data outside a lab.

### Exercise 18 — Preventing Duplicate Recurrence

Propose a `canonical_events` schema with `UNIQUE(tenant_id,event_key)` and an `ON CONFLICT ... DO UPDATE` write pattern that updates only when the source version is newer. Why is a one-time cleanup insufficient?

### Exercise 19 — NULLs and Business Keys

If `event_key` allows `NULL`, compare:

- `PARTITION BY tenant_id,event_key`.
- Default `UNIQUE(tenant_id,event_key)`.
- `UNIQUE NULLS NOT DISTINCT` on supported PostgreSQL versions.

Explain when null should be treated as a duplicate.

### Exercise 20 — Choosing Indexes

Propose an index for querying the top 3 most recent orders per customer and an index supporting deduplication by `tenant_id, event_key, received_at, event_id`. Explain why a non-unique index does not replace a unique constraint.

### Exercise 21 — Ordered Top-N JSON

Return one row per customer with `jsonb_agg` containing their two most recent orders. Orders inside the JSON array must be ordered by `rn`; customer Dung must receive `[]`. Explain the roles of `FILTER` and `COALESCE` with `LEFT JOIN`.

### Exercise 22 — Measuring Execution Plans

Run `EXPLAIN (ANALYZE, BUFFERS)` on top N via window functions and via `LEFT JOIN LATERAL` in the lab. Compare scans/indexes, sorts, row counts, and timings. Why can you not conclude which is faster from a few-row sample table alone?

### Exercise 23 — Late-Arriving Records

Suppose source version 10 arrives at 10:05 and source version 9 arrives at 10:10. If business rules require the latest version, what should the `ORDER BY` key in deduplication be? Why does `received_at DESC` miss the requirement?

### Exercise 24 — Adding Business Conditions

A user has 10 consecutive active days, except Nov 5 is a company holiday. Design rules to merge or split the streak depending on policy: **calendar day streak** versus **business day streak**. Do not return the same result for two different definitions.

## Conclusion

The three problems—**consecutive groups (gaps and islands)**, **top N per group**, and **deduplication**—all rest on a shared principle: **precisely defining partitioning, ordering, and row grain/meaning**. `GROUP BY` answers "which rows share the same key"; window functions add "which row comes first, in what position, with what ties, or where group boundaries fall".

For **gaps-and-islands**, the `ROW_NUMBER` difference technique suits date/integer sequences incrementing by exactly one, while `LAG` with a transition flag and `SUM(...) OVER (ROWS ...)` fits richer rules such as state changes or 30-minute session gaps. Deduplicate first when counting **unique days**, and define time, business-day, or event-order boundaries clearly.

For **top N per group**, use `ROW_NUMBER() <= N` for at most N rows; `RANK` to preserve rank-position ties; `DENSE_RANK` to select N distinct value tiers; `DISTINCT ON` for one representative per group; and `LATERAL` for per-parent top N lookups. Include tie-breakers in `ORDER BY` whenever a single row is picked or deleted deterministically, and align pre-/post-ranking filters with the exact business question.

For **deduplication**, `ROW_NUMBER` and `DISTINCT ON` are merely execution tools. The harder decisions are **which key defines duplicates, which record is authoritative, whether audit history must be preserved, and how to prevent recurrence**. Preview `rn > 1`, delete inside a transaction only when truly warranted, and enforce unique constraints and idempotent write protocols on canonical tables. Combining sound semantics, deterministic ordering, and concurrency safeguards allows PostgreSQL window functions to solve complex analytical and data-hygiene problems clearly, consistently, and efficiently.
