# duration and Semantic Limits on Supported Operations in Apache Cassandra

In Apache Cassandra, **`duration` is not simply a number of seconds**. It is a CQL type representing an interval across three components: **months, days, and nanoseconds**. This separation matters because months vary in length, and a calendar day can be 23 or 25 hours long in time zones with daylight saving time (DST). Consequently, not every duration can be converted into a fixed number of milliseconds, ordered by magnitude, or used as a sorting key.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The module covers distributed architecture and the wide-column model, partition keys, query-driven table design, read/write consistency levels, practical CQL, replication, compaction, repair, error handling, and the Java Driver. In that context, `duration` is suited for **storing policies or intervals**; **finding due events**, **sorting**, and **distributing data** still require comparable key columns such as `date`, `timestamp`, `bigint`, or `uuid`.

## 1. How Does duration Differ from timestamp, date, time, and bigint?

| CQL Type | Meaning | Java Driver 4.x | Use When |
|---|---|---|---|
| **`duration`** | Time span of months, days, and nanoseconds | `CqlDuration` | 1-month renewal cycle, 7-day grace period, 30-minute wait interval |
| **`timestamp`** | An absolute point in time, millisecond resolution | `Instant` | Activation time, expiration time, next retry instant |
| **`date`** | A calendar date, without time or time zone | `LocalDate` | Effective date, daily bucket for queries |
| **`time`** | Time of day up to nanoseconds, without date | `LocalTime` | Opening hours, daily scheduled job window |
| **`bigint`** | 64-bit integer | `long` | Fixed elapsed duration in ms/ns, sequence number, or byte count |

For example, suppose a subscription has a policy "renew **every 1 month**" and started at `2026-01-31T10:00:00Z`. **`duration = 1mo`** captures the meaning "add one calendar month." Semantically, this differs from **`30d`** and **`720h`**. The actual due date must be computed against a concrete reference date/time and calendar rule.

A real renewal record often needs **two columns with distinct roles**:

- `billing_interval duration`: the "every 1 month" policy.
- `next_billing_at timestamp`: the computed absolute instant for the scheduler to query and process.

Never convert `duration` into seconds before clarifying whether it represents "elapsed time" or a "calendar interval."

## 2. The Three Components of CQL duration

A `duration` value is encoded as three variable-length signed integers:

\[
(\text{months},\ \text{days},\ \text{nanoseconds})
\]

| Component | Decoded Value Type | Meaning |
|---|---|---|
| **months** | 32-bit signed `int` | Calendar months; years convert to 12 months |
| **days** | 32-bit signed `int` | Calendar days; weeks convert to 7 days |
| **nanoseconds** | 64-bit signed `long` | Nanoseconds for hours/minutes/seconds/subseconds |

Examples converted to the three components:

| CQL Duration | months | days | nanoseconds |
|---|---:|---:|---:|
| `1y` | 12 | 0 | 0 |
| `2mo` | 2 | 0 | 0 |
| `3w4d` | 0 | 25 | 0 |
| `1d` | 0 | 1 | 0 |
| `24h` | 0 | 0 | 86,400,000,000,000 |
| `1h30m` | 0 | 0 | 5,400,000,000,000 |
| `1mo2d3h` | 1 | 2 | 10,800,000,000,000 |
| `250ms` | 0 | 0 | 250,000,000 |

**Sign rule:** all non-zero components must share the **same sign** (either all non-negative or all non-positive). For instance, a duration with `months=1, days=-2` is invalid. If business logic requires "add one month then subtract two days," express it as **two calendar calculation steps** or precompute the target instant; do not force opposite signs into a single CQL duration.

**Storage limits:** although each component uses variable-length encoding on the wire, `months` and `days` are still bounded by 32-bit signed integers and `nanoseconds` by a 64-bit signed integer. Do not treat a duration as unbounded or multiply blindly across units.

### 2.1. Why Is `1d` Not the Same as `24h`?

`1d` sets `days = 1`, whereas `24h` sets `nanoseconds = 86,400,000,000,000`. The two values **differ in representation itself**.

When applied to a calendar in a DST-observing zone, they also yield different target instants. For instance, in `America/New_York`, clocks spring forward on **2026-03-08**:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
    2026, 3, 7, 12, 0, 0, 0, zone
);

ZonedDateTime calendarDayLater = start.plusDays(1);
ZonedDateTime elapsed24HoursLater = start.plusHours(24);

System.out.println(calendarDayLater);
// 2026-03-08T12:00-04:00[America/New_York]
System.out.println(elapsed24HoursLater);
// 2026-03-08T13:00-04:00[America/New_York]
~~~

From the exact same starting point, "tomorrow at 12:00 local time" and "exactly 24 hours later" differ by **1 hour**. If business rules expire at a local clock time, **also store the time zone and calendar definition**; a duration alone has no time zone.

### 2.2. Why Is `1mo` Not the Same as `30d`?

Example with Java `LocalDate`:

~~~java
import java.time.LocalDate;

LocalDate start = LocalDate.of(2026, 1, 31);

System.out.println(start.plusMonths(1)); // 2026-02-28
System.out.println(start.plusDays(30));  // 2026-03-02
~~~

One calendar month from month-end may land on the end of the next month under the library's month-addition rules. Thirty days steps across 30 calendar days, giving a different date. Clarify monthly subscription rules explicitly: **if a user signs up on the 31st, which day renews in February?** That is a business policy, not something CQL `duration` decides on its own.

## 3. CQL duration Literal Syntax

CQL lets you write durations directly such as `1mo2d3h`. The easiest suffixes to confuse are **`mo`** (month) and **`m`** (minute). **`ms`** is millisecond, **`us`** or **`µs`** is microsecond, and **`ns`** is nanosecond.

| Suffix | Meaning | Component Mapping |
|---|---|---|
| `y` | Year | 12 months |
| `mo` | Month | 1 month |
| `w` | Week | 7 days |
| `d` | Day | 1 day |
| `h` | Hour | 3,600,000,000,000 ns |
| `m` | Minute | 60,000,000,000 ns |
| `s` | Second | 1,000,000,000 ns |
| `ms` | Millisecond | 1,000,000 ns |
| `us`, `µs` | Microsecond | 1,000 ns |
| `ns` | Nanosecond | 1 ns |

Three common formats supported by Cassandra:

~~~text
CQL unit notation:        1y2mo3d4h5m6s
ISO 8601:                 P1Y2M3DT4H5M6S
ISO 8601 alternative:     P0001-02-03T04:05:06
~~~

In CQL, duration literals like `1mo`, `7d`, and `12h30m` are written **without quotes**, unlike the `text` string literal `'1mo'`. When using prepared statements, bind a Java `CqlDuration` object with the matching codec.

### 3.1. CQL to Create a Subscription Policy Table

~~~cql
CREATE TABLE billing_policies_by_plan (
    plan_code text PRIMARY KEY,
    billing_every duration,
    grace_period duration,
    retry_after duration,
    billing_zone text,
    effective_at timestamp
);

INSERT INTO billing_policies_by_plan (
    plan_code, billing_every, grace_period,
    retry_after, billing_zone, effective_at
) VALUES (
    'MONTHLY_VN', 1mo, 5d,
    30m, 'Asia/Ho_Chi_Minh',
    '2026-11-21T00:00:00Z'
);

SELECT billing_every, grace_period, retry_after, billing_zone
FROM billing_policies_by_plan
WHERE plan_code = 'MONTHLY_VN';
~~~

This is a **policy lookup table by `plan_code`**. Durations are used as **regular data columns**, while `plan_code` is the partition key. Breakdown:

- `billing_every = 1mo`: billing cycle in calendar months.
- `grace_period = 5d`: calendar days of grace period.
- `retry_after = 30m`: fixed 30-minute wait before retrying.
- `billing_zone`: time zone used to interpret cycle dates and hours.
- `effective_at timestamp`: when the policy takes effect. This is an absolute point in time, not a duration.

Policies may need versioning or time-bounded effective periods. If you frequently look up "the policy active at time T," design a history table keyed by plan and effective time; a single `PRIMARY KEY(plan_code)` row keeps only the current version.

### 3.2. Common Literal Mistakes

~~~text
1m     -> one minute, not one month.
1mo    -> one month.
1ms    -> one millisecond, not one minute.
24h    -> 24 hours in the nanoseconds component.
1d     -> one day in the calendar days component.
1mo-2d -> tries to mix opposite signs; invalid as a single duration.
~~~

Enforce validation at the API layer instead of accepting arbitrary user-typed duration strings straight into Cassandra. A UI form restricting choices to "month/week/day/hour" is far clearer than allowing `1mo` to be mistyped as `1m`.

## 4. Supported vs. Unsupported Operations

The core theme of `duration` is **semantic limits on operations**, because it has no total ordering independent of a reference point in time.

| Operation | Supported / Approach | Reason and Limits |
|---|---|---|
| Declaring a `duration` column, `INSERT`, `UPDATE`, `SELECT` | **Yes** | Data column for policies and spans |
| Binding/reading via Java Driver `CqlDuration` | **Yes** | Preserves all three components |
| Using `duration` in `PRIMARY KEY` | **No** | Lacks a total ordering for Cassandra key organization |
| Using `duration` as a clustering key or in `ORDER BY` | **No** | Clustering keys must be orderable |
| Comparing "`1mo > 30d`" without a reference date | **Semantically undefined** | A month can be 28–31 days |
| Range scan `WHERE interval > 7d` on a duration column | **Not a valid query pattern** | No natural total order and not a clustering column |
| Adding/subtracting duration to `date` or `timestamp` via CQL operators | **Yes, since Cassandra 4.0** | Result is `date` or `timestamp`; verify cluster version |
| Adding duration to `time` to produce a timestamp | **Do not use** | `time` lacks date and time zone |
| `USING TTL 1h` instead of seconds | **No** | TTL takes an integer duration in **seconds**, not `duration` |
| Using duration to increment a `counter` | **No** | Counters are a distinct type with integer increment rules |
| Converting `1mo` into a fixed nanosecond count | **Unsafe** | Requires a calendar anchor and time zone rules |

Cassandra provides **arithmetic operators** on numeric types; that does not make `duration` a number you can freely add, subtract, multiply, or divide like `bigint` or `decimal`. For complex calendar math, implement and test it in the application where the start instant, `ZoneId`, and business rules are all available.

### 4.1. Why Does duration Lack a Total Ordering?

A `<` or `>` operator requires a consistent result for every pair of values. For durations:

- `1mo` can be 28, 29, 30, or 31 days depending on month and year.
- `1d` is a calendar day step; `24h` is 24 elapsed hours. In DST zones, they can land on different instants.
- `1y` and `365d` differ in leap years.

Thus, no universal rule can decide whether `1mo` is larger or smaller than `30d` for every reference point. That is why Cassandra **forbids duration in primary keys**; this restriction is fundamental to the data model, not merely a performance toggle.

**Design consequence:** if a dashboard needs to "filter runs lasting longer than 500 ms," store a **measured fixed-unit value** like `elapsed_ms bigint` (in an appropriate query table) instead of a calendar `duration`.

### 4.2. Limits in Collections

Collections impose rules on types that require comparison or element identity. Because `duration` has no ordering, it is **unsuitable as a `set<duration>` element or `map<duration, ...>` key** in CQL; those usages are restricted. You can model a small list of intervals within collection bounds or use scalar duration columns, but never stuff an unbounded interval history into a collection inside a single row.

If you need to look up a list of policies by ID, an operationally clean pattern is a table keyed by `policy_id uuid` or `policy_code text` with `interval duration` as a **value column**. One row per policy provides keyed access and controls partition growth.

## 5. Datetime Arithmetic with duration in CQL 4.0+

In Cassandra versions supporting date/time arithmetic (from **4.0** onward), CQL can add or subtract a duration from a `date` or `timestamp`. Example:

~~~cql
CREATE TABLE daily_runs_by_day (
    run_day date PRIMARY KEY,
    completed_jobs int
);

INSERT INTO daily_runs_by_day (run_day, completed_jobs)
VALUES ('2026-11-20', 100);

-- Fetch the day before 2026-11-21:
SELECT completed_jobs
FROM daily_runs_by_day
WHERE run_day = '2026-11-21' - 1d;
~~~

This evaluates an expression on a **date literal** to produce a **date value** matching the primary key. It is entirely different from making a `duration` column a clustering key.

These combinations make sense:

~~~text
timestamp + duration -> timestamp
timestamp - duration -> timestamp
date      + duration -> date
date      - duration -> date
~~~

**Limitations:**

- Verify your **running Cassandra/CQL version**; never assume older clusters support datetime arithmetic.
- Cassandra `timestamp` holds **milliseconds** only. If a duration has sub-millisecond nanoseconds, writing the result to a timestamp drops that sub-millisecond fraction.
- `date` has no time-of-day component; do not expect it to preserve hours, minutes, or nanoseconds.
- CQL does not store a user's business time zone alongside `timestamp`. Arithmetic on `timestamp` cannot replace a policy like "renew at 09:00 local time," which requires `ZoneId` and calendar rules.
- Time arithmetic in a `WHERE` clause does not turn non-key columns into efficient query paths.

For logic deciding **when to bill, lock an account, or send an email**, it is usually better to compute the **exact absolute deadline in the Java application** and store `next_due_at timestamp`, preventing clients from interpreting time zones or calendar rules differently.

## 6. Java Driver 4.x: CqlDuration and Binding

CQL `duration` is mapped by Java Driver 4.x to **`com.datastax.oss.driver.api.core.data.CqlDuration`**, not directly to `java.time.Duration`.

Common APIs:

| Purpose | Java |
|---|---|
| Construct from three components | `CqlDuration.newInstance(months, days, nanoseconds)` |
| Parse a literal like `1mo2d3h` | `CqlDuration.from("1mo2d3h")` |
| Read components | `getMonths()`, `getDays()`, `getNanoseconds()` |
| Bind in a prepared statement | `setCqlDuration(index, value)` or `setCqlDuration(name, value)` |
| Read from a row | `getCqlDuration("billing_every")` |
| Compute with Java time types | Apply calendar/time-zone rules with `Period`, `Duration`, `ZonedDateTime` |

Example constructing durations:

~~~java
import com.datastax.oss.driver.api.core.data.CqlDuration;
import java.time.Duration;

CqlDuration monthly = CqlDuration.newInstance(1, 0, 0);
CqlDuration grace = CqlDuration.from("5d");
CqlDuration retry = CqlDuration.newInstance(
    0, 0, Duration.ofMinutes(30).toNanos()
);

System.out.println(monthly.getMonths());      // 1
System.out.println(grace.getDays());          // 5
System.out.println(retry.getNanoseconds());   // 1800000000000
~~~

`Duration.ofMinutes(30).toNanos()` is valid only because it represents **30 elapsed minutes**. Never turn `1mo` into `nanoseconds` by assuming a month equals 30 days.

### 6.1. INSERT and SELECT with Prepared Statements

Assume `session` is a `CqlSession` configured with the application's contact points, local datacenter, keyspace, and credentials:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlDuration;
import java.time.Instant;

// CqlSession session = ...;  // Initialized and lifecycle-managed externally.

PreparedStatement insert = session.prepare(
    "INSERT INTO billing_policies_by_plan "
  + "(plan_code, billing_every, grace_period, "
  + " retry_after, billing_zone, effective_at) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

CqlDuration interval = CqlDuration.from("1mo");
CqlDuration grace = CqlDuration.from("5d");
CqlDuration retry = CqlDuration.from("30m");

BoundStatement statement = insert.boundStatementBuilder()
    .setString(0, "MONTHLY_VN")
    .setCqlDuration(1, interval)
    .setCqlDuration(2, grace)
    .setCqlDuration(3, retry)
    .setString(4, "Asia/Ho_Chi_Minh")
    .setInstant(5, Instant.parse("2026-11-21T00:00:00Z"))
    .build();

session.execute(statement);

PreparedStatement find = session.prepare(
    "SELECT billing_every, grace_period, retry_after, billing_zone "
  + "FROM billing_policies_by_plan WHERE plan_code = ?");

Row row = session.execute(find.bind("MONTHLY_VN")).one();

if (row != null) {
    CqlDuration stored = row.getCqlDuration("billing_every");
    if (stored != null) {
        int months = stored.getMonths();
        int days = stored.getDays();
        long nanos = stored.getNanoseconds();
    }
}
~~~

**Prepared statements** bind the exact type, avoiding `m`/`mo` ambiguity from string-concatenated CQL and eliminating manual escaping. Still validate at the API boundary before constructing `CqlDuration`: malformed strings, oversized values, or mixed signs must be rejected per contract.

### 6.2. Comparing with java.time.Duration and java.time.Period

The two standard Java types also have distinct roles:

| Java Type | Representation | Scenario |
|---|---|---|
| `Duration` | Seconds + nanoseconds, elapsed time | 30-second timeout, 250-ms latency |
| `Period` | Years + months + calendar days | 1-month renewal, add 7 calendar days |
| `CqlDuration` | Months + days + nanoseconds | Exact mapping for CQL duration covering calendar and elapsed parts |

Never convert `CqlDuration` into `java.time.Duration` when `getMonths()` or `getDays()` is non-zero without a calendar anchor and time-zone rule. `CqlDuration` implements `TemporalAmount`, so check which **target temporal type** and calendar/time rules it is applied to—not every `Temporal` supports the same set of units.

### 6.3. Converting a Calendar Cycle into a Due Timestamp

If the plan contract states "renew at the same local time next month," a controlled calculation looks like:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId billingZone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant activatedAt = Instant.parse("2026-01-31T03:00:00Z");
// 10:00 Vietnam time on 2026-01-31.

ZonedDateTime localActivation = activatedAt.atZone(billingZone);
ZonedDateTime localNext = localActivation.plusMonths(1);
Instant nextBillingAt = localNext.toInstant();

System.out.println(localNext);
// 2026-02-28T10:00+07:00[Asia/Ho_Chi_Minh]
System.out.println(nextBillingAt);
// 2026-02-28T03:00:00Z
~~~

Here the **end-of-month** rule follows `plusMonths` behavior; the application must confirm that matches the billing policy. If the policy says "always anchor to the 31st and clamp shorter months to month-end," do not blindly add one month sequentially from the previous deadline without tracking the **original billing anchor day**, or the billing day will drift permanently to the 28th.

In DST zones, also define policies for nonexistent or overlapping local hours. CQL duration only stores the interval; **interpretation logic** belongs in the application's calendar layer.

## 7. How Do You Design Tables to Query Due Jobs?

A scheduler often needs: **"Fetch renewals due today, ordered ascending by due time, processed per shard."** Using `duration` as a clustering key is invalid; instead, **precompute an absolute timestamp** and place that timestamp in a query-aligned key.

Example:

~~~cql
CREATE TABLE renewal_tasks_by_day_shard (
    due_day date,
    shard smallint,
    due_at timestamp,
    subscription_id uuid,
    customer_id uuid,
    plan_code text,
    PRIMARY KEY ((due_day, shard), due_at, subscription_id)
) WITH CLUSTERING ORDER BY (due_at ASC, subscription_id ASC);
~~~

- `(due_day, shard)` is the **partition key**, distributing processing load by day and shard.
- `due_at timestamp` is the **clustering column** ordered by absolute deadline.
- `subscription_id uuid` disambiguates tasks sharing the same millisecond `due_at`.
- `plan_code` references the policy table containing `billing_every duration`, though duration is **not a sorting key** on the task queue.

Sample query for shard 3:

~~~cql
SELECT due_at, subscription_id, customer_id, plan_code
FROM renewal_tasks_by_day_shard
WHERE due_day = '2026-11-21'
  AND shard = 3
  AND due_at <= '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

The query provides the full partition key and bounds the clustering column. If the system has 32 shards, each worker must know which shards it owns or poll its assigned shards; there is no cheap query that globally merges all partitions by time.

Because **the deadline is a clustering key**, deferring a job from 09:00 to 09:30 **changes its key**: the system must insert the new row and delete/retire the old row idempotently so both do not execute. Cassandra does not support `UPDATE` to change a row's primary key in place.

### 7.1. Duration Does Not Replace TTL

Suppose a policy requires "retain data for 1 month." Cassandra `USING TTL` accepts **integer seconds**, not the calendar duration `1mo`.

~~~cql
-- TTL in seconds: e.g., retain for roughly 7*24 hours.
INSERT INTO some_events_by_id (event_id, event_type)
VALUES (11111111-1111-4111-8111-111111111111, 'LOGIN')
USING TTL 604800;
~~~

This snippet only illustrates TTL syntax; it assumes `some_events_by_id` exists with `event_id` and `event_type`. TTL is not a user-facing calendar "expiration date." If business logic requires expiration **after one calendar month** or at a specific local hour, compute **`expires_at`** using calendar rules in the application, then choose deletion and TTL mechanisms accordingly.

**Never treat 1 month = 30 days for TTL** unless that matches the exact business definition. When using TTL, account for expiration state, tombstones, and compaction/repair policies, and never rely on TTL as a second-accurate job timer.

### 7.2. Duration Is Not a Counter

Operations like:

~~~cql
-- NOT supported counter-style increment syntax for duration:
-- UPDATE billing_policies_by_plan
-- SET billing_every = billing_every + 1mo
-- WHERE plan_code = 'MONTHLY_VN';
~~~

are not a valid incremental update model. To change a policy from 1 month to 2 months, write **the entire new duration value** via a prepared statement and define when the change takes effect. For concurrent modifications requiring conflict control, evaluate LWT or explicit versioning; Cassandra does not accumulate durations like counters.

## 8. Retries and Consistency: duration Is Policy, timestamp Is Computed Output

Suppose a worker reads `billing_every = 1mo`, computes `next_billing_at`, and writes history and task rows. If the worker times out, some replicas or partial writes may have already succeeded.

To handle this reliably:

1. Use **stable `subscription_id` and `billing_cycle_id`** as business identifiers; retries for the same cycle must reuse the exact same keys.
2. Record the **policy version**, `ZoneId`, anchor date, and month-end/DST rules used to compute the deadline.
3. Persist the **computed `next_billing_at timestamp`** so every worker sees the exact same instant rather than re-deriving due dates from duration in separate time zones.
4. When writing across multiple query tables, implement recovery/reconciliation rather than assuming a series of INSERTs across partitions is atomic.
5. On retries, keep the core payload of an already computed request fixed. Recomputing due dates from `now()` on every retry causes deadlines to drift.

Consistency levels (such as `LOCAL_QUORUM`) control how many replicas acknowledge reads/writes. They **do not resolve** `1mo` vs. `30d` differences or turn separate writes into a cluster-wide scheduling transaction.

## 9. Impact on Replication, Compaction, and Repair

**Replication** copies written CQL values, including all three duration components. Replicas never convert durations into a "canonical number of seconds" for comparison. **Repair** converges replica state, but cannot fix month-end dates miscalculated by the application. **Compaction** merges SSTables and purges expired/tombstoned data per storage rules; it does not compute renewal schedules from a `duration` column.

In operations:

- Define **retention** for policies and change histories to avoid losing reconciliation records.
- If policies change frequently, consider **versioning** with `effective_at timestamp`; `duration` is simply an attribute of each version.
- When scheduler rows move across due buckets, manage legacy rows and tombstones under real load.
- Measure **partition size**, rows per day/shard, read/write latency, due rows, and retry counts; optimize only with real workload profiles.
- When deadlines are computed in the application, monitor time-zone databases and host clocks; clock skew between nodes does not corrupt duration bytes, though it can trigger scheduler runs early or late.

## 10. Common Mistakes and Solutions

| Mistake | Consequence | Solution |
|---|---|---|
| Using `1m` for a 1-month cycle | Actually means **1 minute** | Use `1mo` and validate input |
| Treating `1mo = 30d = 720h` | Wrong across varying month lengths and DST | Explicitly separate calendar intervals from elapsed time |
| Using `duration` in `PRIMARY KEY` | Invalid schema | Use an ordered key column like `timestamp`, `bigint`, or `date` |
| Querying `WHERE policy_duration > 7d` for long policies | No global duration ordering exists | Normalize to a clear numeric metric and design a query table |
| Passing `duration` to `USING TTL` | TTL does not accept calendar durations | Specify TTL in seconds; track calendar deadlines separately |
| Mixing `months=1` and `days=-2` | Violates duration same-sign rule | Split into two calendar steps or precompute target |
| Converting `CqlDuration` to `java.time.Duration` with assumed days/months | Loses calendar semantics | Use `Period`, `ZonedDateTime`, `ZoneId`, and policy |
| Adding 1 month repeatedly from month-end without keeping the anchor day | Renewal day drifts permanently | Define cycle rules and preserve the original anchor |
| Computing deadlines using each worker's local time zone | Different workers derive different deadlines | Persist `billing_zone`, policy version, and computed deadline |
| Expecting `date` or `timestamp` to keep all duration nanoseconds | Sub-millisecond precision is lost | Pick matching storage types/units upfront |
| Rewriting tasks with a new ID after timeout | Same cycle can execute twice | Reuse idempotent IDs/keys and reconcile |
| Updating duration without policy versioning | Cannot reconstruct historical calculations | Store `version`/`effective_at` and the applied policy |

## 11. Practice Exercises

### Exercise 1 — Choosing Types

A system has four requirements:

- Billing cycle **every 1 month**.
- HTTP retry delay of **150 milliseconds**.
- Storing the **computed expiration date/time** as an absolute instant.
- Measuring API latency **to nanoseconds**.

**Hint:** 1-month cycle uses `duration = 1mo`; 150-ms retry config can use `duration = 150ms`, though runtime code usually uses `java.time.Duration`; absolute expiration deadline uses `timestamp`; nanosecond latency should be stored as `bigint elapsed_ns` or a matching measurement column, **not** `timestamp` which stops at milliseconds.

### Exercise 2 — Month-End Dates

A customer subscribes on 2026-01-31 with cycle `1mo`.

**Question:** What date does `LocalDate.plusMonths(1)` produce? Does it match `plusDays(30)`?

**Answer:** `2026-02-28`, whereas `plusDays(30)` yields `2026-03-02`. The renewal policy must state explicitly whether month-end clamping or another rule applies.

### Exercise 3 — DST

In New York, a recurring schedule "12:00 tomorrow" starts at 12:00 on 2026-03-07. Compared to "24 hours later," do both land on the same instant?

**Answer:** no. `plusDays(1)` lands at 12:00 on 03/08; `plusHours(24)` lands at 13:00 on 03/08 due to the DST transition.

### Exercise 4 — Is This Schema Valid?

~~~cql
-- Invalid: duration cannot be a clustering key.
CREATE TABLE wrong_jobs (
    tenant_id uuid,
    delay duration,
    job_id uuid,
    PRIMARY KEY ((tenant_id), delay, job_id)
);
~~~

**Question:** How should you redesign this to fetch due jobs?

**Answer:** compute `due_at timestamp` and cluster by deadline with `job_id uuid` as a tie-breaker; keep `delay duration` as a non-key data column for the policy or job definition.

### Exercise 5 — Java Driver

~~~java
CqlDuration policy = CqlDuration.from("1mo2d3h");
~~~

**Question:** What do `getMonths()`, `getDays()`, and `getNanoseconds()` return? Can it be compared with `33d3h` without knowing a start date?

**Answer:** months = 1, days = 2, nanoseconds = `10_800_000_000_000L`; no less-than/greater-than ordering against `33d3h` holds across all calendar dates.

## 12. Checklist Before Using duration

- [ ] Have **calendar intervals** (months/days) been distinguished from **elapsed durations** (hours/minutes/seconds/nanoseconds)?
- [ ] Are suffixes accurate: `mo` for months, `m` for minutes, `ms` for milliseconds?
- [ ] Do the three components (months/days/nanoseconds) share the same sign and fit within `int/int/long` bounds?
- [ ] Are `ZoneId`, month-end rules, DST policies, or an anchor start date needed to resolve deadlines?
- [ ] Is `duration` used **only as a data column**, never in `PRIMARY KEY` or comparison keys?
- [ ] Do range/ordering queries use `timestamp`, `date`, `bigint`, or another comparable key?
- [ ] If using `date/timestamp ± duration` arithmetic, does the running Cassandra version support those operators?
- [ ] Are `CqlDuration`, `java.time.Duration`, and `java.time.Period` clearly separated?
- [ ] Does the Java Driver bind/read via `setCqlDuration`/`getCqlDuration` in prepared statements?
- [ ] Is `duration` never passed directly as TTL, with TTL defined in **seconds**?
- [ ] For scheduler workloads, are **absolute deadlines**, buckets, and deduplication keys persisted?
- [ ] Are retries, policy versioning, consistency levels, and multi-table synchronization handled per business requirements?
- [ ] Have partition sizes, tombstones/compaction, retention, and repair requirements been evaluated under real load?

## References

- [Apache Cassandra — CQL Data Types, Duration section](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — Arithmetic Operators, Datetime Arithmetic](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/operators.html).
- [Apache Cassandra Java Driver 4.x — CqlDuration](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/data/CqlDuration.html).

**Remember:** `duration` is **a time span with calendar semantics**, stored as **months + days + nanoseconds**. Because months and days do not map to a constant elapsed duration everywhere, Cassandra **does not order durations** and **forbids duration in primary keys**. Use it for **policies**, compute due instants using an explicit calendar and time zone, and store **`timestamp`/query keys** for efficient processing in distributed Cassandra.
