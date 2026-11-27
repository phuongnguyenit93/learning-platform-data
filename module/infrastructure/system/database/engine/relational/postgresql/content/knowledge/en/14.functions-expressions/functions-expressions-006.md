# Transaction Time, Statement Time, and Wall-Clock Time in PostgreSQL

When recording an order creation timestamp, checking whether a token has expired, or measuring how long a query runs, we often think we can simply call "the current time." Yet PostgreSQL distinguishes **several concepts of current time**, depending on which moment you want to observe:

- **Transaction start time**.
- **SQL statement start time**.
- **Wall-clock time read at the exact moment a function is called**.

These three points can look nearly identical when a fast `SELECT` runs in autocommit mode. They diverge sharply when a transaction stays open for a long time, runs multiple SQL statements, waits on locks, performs expensive computations, or invokes functions repeatedly.

For instance, an application opens a transaction, spends 10 seconds validating data, and then inserts an order. If `created_at` has `DEFAULT now()`, the timestamp stored in that column reflects **when the transaction started**, not necessarily the actual second when `INSERT` ran. That is by design in PostgreSQL, yet it often surprises beginners who think the database recorded the wrong time.

This lesson distinguishes these time functions, explains how they interact with MVCC and transactions, explores the impact of `timestamp` types and time zones, and shows how to pick the right reference point for logs, audits, expiration checks, reports, and Java applications.

## 1. Three Clocks: Meaning Before Syntax

Imagine a transaction containing multiple statements:

```text
Real timeline

10:00:00       10:00:03       10:00:07       10:00:09
    |              |              |              |
   BEGIN          SELECT          INSERT         COMMIT
    |              |              |              |
    +------------ transaction -------------------+
                   ^              ^
             statement 1     statement 2

transaction_timestamp()  -> around 10:00:00 throughout transaction
statement_timestamp()    -> around 10:00:03 at SELECT,
                            around 10:00:07 at INSERT
clock_timestamp()        -> exact wall clock at each function call
```

This is an illustrative diagram: "10:00:00" represents transaction start time, while PostgreSQL's actual transaction timestamp depends on when the server receives/processes command messages. Do not treat the numbers in this diagram as exact microsecond predictions.

### 1.1. Transaction Timestamp

The `transaction_timestamp()` function returns the **start time of the current transaction**. It retains that exact value from the moment the transaction starts until it ends, regardless of how many statements execute inside it.

Common expressions that are equivalent for this reference point:

```sql
SELECT
    transaction_timestamp() AS transaction_started,
    now()                  AS now_value,
    CURRENT_TIMESTAMP      AS current_timestamp_value;
```

Within a single transaction, all three values reflect the same transaction start time. `CURRENT_TIMESTAMP` is standard SQL syntax; `now()` is the familiar PostgreSQL function.

### 1.2. Statement Timestamp

`statement_timestamp()` returns the start time of the **current SQL statement**. More precisely, PostgreSQL documentation defines it as the time the server received the latest command message from the client.

In a transaction with three statements sent at different times, `statement_timestamp()` advances between the three statements while staying constant during each statement's own execution.

### 1.3. Clock Timestamp

`clock_timestamp()` reads the **current wall-clock time at the moment the call executes**. Its value can change even **within the same statement**, including across rows of a long-running query.

This is the biggest difference from the two functions above: PostgreSQL does not "freeze" `clock_timestamp()` per transaction or per statement.

### 1.4. Quick Comparison Table

| Expression | Reference Moment | Changes Within Same Statement? | Changes Across Statements in Same Transaction? | Return Type |
| --- | --- | --- | --- | --- |
| `transaction_timestamp()` | Start of transaction | No | No | `timestamp with time zone` (`timestamptz`) |
| `now()` | Start of transaction | No | No | `timestamptz` |
| `CURRENT_TIMESTAMP` | Start of transaction | No | No | `timestamptz` |
| `statement_timestamp()` | Start of statement | No, fixed for the statement | Yes, can advance | `timestamptz` |
| `clock_timestamp()` | Wall clock at call time | Yes, can advance | Yes, can advance | `timestamptz` |
| `timeofday()` | Wall clock at call time | Yes, can advance | Yes, can advance | `text` |

"Can advance" does not guarantee **every call** produces a distinct value: two calls very close together can return the same value due to clock resolution, and the system clock can also be adjusted. Never use `clock_timestamp()` as a source of unique IDs.

## 2. Opening Example: Inside a Single SELECT

Run:

```sql
SELECT
    transaction_timestamp() AS tx_time,
    now() AS now_time,
    CURRENT_TIMESTAMP AS sql_current_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_time;
```

In a simple `SELECT`, the five values may differ by very little; `transaction_timestamp()`, `now()`, and `CURRENT_TIMESTAMP` must match the same transaction start. If the server is inside a transaction opened earlier, `statement_timestamp()` can be noticeably newer than `transaction_timestamp()`.

Do not rely on tiny differences in this quick test to conclude the functions behave the same. You must test **multiple statements inside one transaction** or let time elapse within one statement.

### 2.1. Checking Data Types

```sql
SELECT
    pg_typeof(now()) AS now_type,
    pg_typeof(statement_timestamp()) AS statement_type,
    pg_typeof(clock_timestamp()) AS clock_type,
    pg_typeof(timeofday()) AS legacy_text_type;
```

The first three timestamp functions return `timestamp with time zone`. `timeofday()` returns `text`: it is retained for historical compatibility and is less convenient than typed temporal values for arithmetic or comparisons.

### 2.2. Relationship Between the Values

`now()` and `CURRENT_TIMESTAMP` are not two independent "machine clock reads." Inside the same transaction, they share the same transaction start value. If they ever appear different across two checks, verify first whether you are comparing **two separate transactions** or whether time zone/formatting settings changed.

## 3. Experiment 1: Multiple Statements in One Transaction

Run these **sequentially on the same PostgreSQL connection**, such as a single `psql` session. Do not execute each line through a tool that opens a fresh session per query.

```sql
BEGIN;

SELECT
    transaction_timestamp() AS tx_at_step_1,
    statement_timestamp() AS stmt_at_step_1,
    clock_timestamp() AS wall_at_step_1;

SELECT pg_sleep(1.5);

SELECT
    transaction_timestamp() AS tx_at_step_2,
    statement_timestamp() AS stmt_at_step_2,
    clock_timestamp() AS wall_at_step_2;

COMMIT;
```

`pg_sleep(1.5)` tells PostgreSQL to wait roughly 1.5 seconds. On a lab machine, actual sleep time can be slightly longer depending on OS scheduling.

**What to observe:**

- `tx_at_step_1` and `tx_at_step_2` are equal because both `SELECT` statements belong to the same transaction.
- `stmt_at_step_2` is later than `stmt_at_step_1` because the second `SELECT` was sent after sleeping.
- `wall_at_step_2` is later than `wall_at_step_1` assuming the system clock was not stepped backward significantly.
- Within each `SELECT`, `statement_timestamp()` is a fixed boundary, not a clock updating per expression.

### 3.1. A Final SELECT Before Commit Does Not Return "Commit Time"

`transaction_timestamp()` remains the transaction **start** time right before `COMMIT`. `clock_timestamp()` in the last `SELECT` is when the clock was read during that statement, **not** the final commit time.

If an application needs the real commit time for transaction reconciliation, do not casually label `now()` as `committed_at`. Timestamps written during a transaction are computed **before** commit succeeds; the transaction can still roll back.

### 3.2. The BEGIN Boundary and Server Command Receipt Time

In an explicit transaction, `BEGIN` opens the transaction before subsequent `SELECT` statements. Thus `transaction_timestamp()` can be earlier than `statement_timestamp()` even on the very first `SELECT` if there is a delay between `BEGIN` and `SELECT`.

That does not contradict the rule: transaction start is one moment, and each command's statement start is another.

## 4. Experiment 2: Clock Advancing Within a Single Statement

To demonstrate `clock_timestamp()`, use a PL/pgSQL `DO` block with two `RAISE NOTICE` statements and a pause in between:

```sql
DO $$
BEGIN
    RAISE NOTICE 'At start: tx=%, stmt=%, wall=%',
        transaction_timestamp(),
        statement_timestamp(),
        clock_timestamp();

    PERFORM pg_sleep(1.5);

    RAISE NOTICE 'After wait: tx=%, stmt=%, wall=%',
        transaction_timestamp(),
        statement_timestamp(),
        clock_timestamp();
END;
$$;
```

`DO ...` is a single statement sent by the client, even though it executes multiple PL/pgSQL statements internally. Therefore:

- `transaction_timestamp()` stays unchanged throughout the block.
- `statement_timestamp()` stays unchanged because it is still the same client-level statement.
- `clock_timestamp()` is re-read after the wait, so it is typically around 1.5 seconds later.

**Advantage of this example:** the sequence `RAISE NOTICE -> pg_sleep -> RAISE NOTICE` is enforced by sequential PL/pgSQL statements. It avoids falsely inferring that PostgreSQL guarantees left-to-right evaluation order for expressions in a `SELECT` list.

### 4.1. Why Not Use SELECT clock_timestamp(), pg_sleep(), clock_timestamp() to Prove Order?

A query like:

```sql
SELECT
    clock_timestamp() AS first_clock,
    pg_sleep(1) AS pause,
    clock_timestamp() AS second_clock;
```

looks intuitive. However, SQL in general does not treat **the order of independent expressions in a select list** as a guaranteed contract for ordering side effects. When you need deterministic temporal sequencing, use sequential PL/pgSQL statements as shown above, or measure from the client side appropriately.

## 5. Autocommit: Why the Functions Sometimes Look Identical

In many PostgreSQL clients, each standalone SQL statement runs in its own transaction unless you explicitly begin one.

Example:

```sql
SELECT transaction_timestamp(), statement_timestamp(), clock_timestamp();

SELECT pg_sleep(2);

SELECT transaction_timestamp(), statement_timestamp(), clock_timestamp();
```

When each `SELECT` runs in its own implicit transaction:

- `transaction_timestamp()` in the first query differs from the last query because a new transaction started.
- `statement_timestamp()` also differs because a new command arrived.
- `clock_timestamp()` reads the live clock in each query.

Seeing all three increase **does not prove** they behave identically. To compare boundaries, open `BEGIN ... COMMIT` in the same session or use a `DO` block.

### 5.1. Interaction with Connection Pooling

A Java application using HikariCP or another pool may pick different connections for two requests or two transactions. If time queries execute on different sessions, never assume they share a transaction just because they were called from the same application method.

Conversely, when a service opens a transaction on a single connection, multiple queries share the same `transaction_timestamp()` even if invoked across different Java methods.

## 6. CURRENT_TIMESTAMP and Standard SQL Time Expressions

PostgreSQL supports standard SQL expressions providing time values:

| Expression | Return Type | Reference Moment in PostgreSQL |
| --- | --- | --- |
| `CURRENT_TIMESTAMP` | `timestamp with time zone` | Start of transaction. |
| `CURRENT_TIMESTAMP(3)` | `timestamp(3) with time zone` | Start of transaction with specified fractional-second precision. |
| `CURRENT_DATE` | `date` | Calendar date at transaction start in the session time zone. |
| `CURRENT_TIME` | `time with time zone` | Time of day at transaction start in the session time zone. |
| `CURRENT_TIME(3)` | `time(3) with time zone` | Same as above with specified fractional-second precision. |
| `LOCALTIME` | `time without time zone` | Local time of day at transaction start. |
| `LOCALTIMESTAMP` | `timestamp without time zone` | Local date and time at transaction start. |

Try:

```sql
SELECT
    CURRENT_DATE AS today_in_session_zone,
    CURRENT_TIME AS local_clock_with_offset,
    LOCALTIME AS local_clock_without_zone,
    CURRENT_TIMESTAMP AS current_timestamp_with_zone,
    LOCALTIMESTAMP AS local_timestamp_without_zone;
```

### 6.1. "CURRENT" Does Not Necessarily Mean the Time Right Now

The name `CURRENT_TIMESTAMP` sounds like "the live clock right now," yet in PostgreSQL it is **frozen at transaction start**.

This matters especially if a transaction spans midnight. `CURRENT_DATE` can still reflect the date when the transaction began even after the wall clock crosses into a new day under the same time zone configuration.

### 6.2. Fractional-Second Precision

`CURRENT_TIMESTAMP(0)`, `CURRENT_TIMESTAMP(3)`, and `CURRENT_TIMESTAMP(6)` express different fractional-second precisions, where `3` corresponds to milliseconds. PostgreSQL supports sub-second timestamp precision depending on the type and system capabilities; increasing digits does not make the underlying OS clock more accurate.

```sql
SELECT
    CURRENT_TIMESTAMP(0) AS seconds_precision,
    CURRENT_TIMESTAMP(3) AS milliseconds_precision,
    CURRENT_TIMESTAMP(6) AS microseconds_precision;
```

Declared precision also affects how values are rounded and stored. A `timestamptz(0)` column is unsuitable if you need milliseconds or microseconds for auditing.

## 7. now(), transaction_timestamp(), and Easy-to-Misuse Syntax

In PostgreSQL:

```sql
SELECT
    now() = transaction_timestamp() AS same_tx_time,
    now() = CURRENT_TIMESTAMP AS same_sql_current_time;
```

Expected output is two boolean columns returning `true`.

### 7.1. The Trap of Using Literal 'now' in DEFAULT

PostgreSQL recognizes special date/time string literals such as `'now'` during type conversion. However, a **literal cast at parse time** can be frozen earlier than the evaluation time you intended.

Example **not recommended** as a dynamic default:

```sql
-- Not recommended:
-- CREATE TABLE bad_time_defaults (
--     id bigint PRIMARY KEY,
--     created_at timestamptz DEFAULT 'now'::timestamptz
-- );
```

A literal `'now'::timestamptz` can be folded into a constant timestamp when PostgreSQL parses the definition, leaving the default fixed to that moment. To have PostgreSQL evaluate the timestamp at statement/transaction execution according to your policy, use a function:

```sql
CREATE TABLE IF NOT EXISTS clock_lab_example (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

This is a standalone example table. `DEFAULT now()` **is not the wall-clock time of the INSERT if the transaction began much earlier**; it returns transaction start. If you need statement receipt time or wall-clock time, pick the corresponding function.

### 7.2. now() Is Not Commit Time

The name `now()` is simply a convenient alias for transaction start. It does not represent:

- When the transaction successfully committed.
- When the row became visible to other sessions.
- When the message was received by an external application.
- When an event was published to a message broker.

If business logic needs those moments, design explicit write/commit/event-publishing workflows rather than renaming `now()` to `committed_at` and assuming the problem is solved.

## 8. timeofday(): A Historical Function Returning Text

PostgreSQL provides:

```sql
SELECT
    timeofday() AS formatted_wall_clock,
    pg_typeof(timeofday()) AS result_type;
```

`timeofday()` reads wall-clock time like `clock_timestamp()`, but returns a **formatted text string** rather than a `timestamptz` value.

Therefore:

- Do not use `timeofday()` as a default for properly typed timestamp columns.
- Do not compare or sort `timeofday()` strings as if they were timestamps.
- To compute durations, use `clock_timestamp()` and timestamp subtraction.
- This function exists primarily for historical compatibility; new systems rarely need it.

Example:

```sql
SELECT
    clock_timestamp() AS wall_as_timestamptz,
    timeofday() AS wall_as_text;
```

The two calls happen very close together, not necessarily matching down to the last digit. `timeofday()` is not recommended for structured datetime input/output.

## 9. Distinguishing timestamptz and timestamp without time zone

All three primary functions return `timestamptz` — written in full as `timestamp with time zone`.

### 9.1. timestamptz Represents an Absolute Instant

PostgreSQL stores `timestamptz` conceptually as an **instant** on the timeline. When displaying it, PostgreSQL converts that instant into the session's time zone. It **does not store the original input time zone name** (such as `Asia/Ho_Chi_Minh`) as per-row metadata.

```sql
SHOW TIME ZONE;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS actual_wall_time;
```

Two sessions with different `TimeZone` settings can display **two different date-time strings** for the very same instant.

### 9.2. timestamp without time zone Does Not State Where the Time Applies

`timestamp without time zone` stores calendar date and clock time without offset/timezone information to pinpoint an absolute instant.

Example:

```sql
SELECT
    TIMESTAMP '2026-07-01 19:00:00'
        AS local_datetime_without_zone,
    TIMESTAMPTZ '2026-07-01 12:00:00+00'
        AS instant_with_zone;
```

These two values can describe the same moment **if** the zone-less timestamp is understood to be Vietnam time (UTC+7). Yet PostgreSQL does not automatically know which zone a `timestamp without time zone` belongs to.

### 9.3. Changing Display Format with SET TIME ZONE

Run in a single session:

```sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-07-01 12:00:00+00' AS visible_time;

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-07-01 12:00:00+00' AS visible_time;
```

Meaningful results:

```text
TimeZone = UTC:
  2026-07-01 12:00:00+00

TimeZone = Asia/Ho_Chi_Minh:
  2026-07-01 19:00:00+07
```

This is the **same instant**, displayed differently. `SET TIME ZONE` alters session configuration; afterward you can run `RESET TIME ZONE;` to return to the default.

### 9.4. AT TIME ZONE: Two Conversion Directions

Given a `timestamptz`, `AT TIME ZONE` produces a local time of type `timestamp without time zone`:

```sql
SELECT
    TIMESTAMPTZ '2026-07-01 12:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_local_time;
```

The result is `2026-07-01 19:00:00` (with no offset because the output type carries no time zone).

Conversely, given a `timestamp without time zone`, `AT TIME ZONE` interprets that date-time as belonging to the specified zone to produce a `timestamptz`:

```sql
SELECT
    TIMESTAMP '2026-07-01 19:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS interpreted_instant;
```

The resulting instant corresponds to 12:00 UTC, though its display still follows the session's `TimeZone`.

### 9.5. Current Date Must Be Interpreted by Time Zone

`CURRENT_DATE` reflects the date from transaction timestamp in the session's time zone. When aggregating by "Vietnam calendar day," state the time zone explicitly:

```sql
SELECT
    (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS vietnam_wall_date,
    (statement_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS vietnam_statement_date,
    (transaction_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS vietnam_transaction_date;
```

These three dates can differ when a transaction spans midnight or when statement start sits right across a date boundary.

Time zones observing DST (daylight saving time) also make certain local hours repeat or vanish. When storing events that require an absolute point in time, prefer `timestamptz` and convert zones on display rather than hardcoding "+7 hours" across regions.

## 10. Creating a Test Table: Three DEFAULTs for Three Moments

To observe effects on actual persisted rows, create a separate schema and table:

```sql
CREATE SCHEMA IF NOT EXISTS clock_lab;

CREATE TABLE clock_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note text NOT NULL,
    tx_started_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    statement_started_at timestamptz NOT NULL
        DEFAULT statement_timestamp(),
    recorded_wall_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
```

The table has three timestamp columns to compare **purpose**, not as a recommendation that every production table store all three.

### 10.1. Inserting Two Rows Across Two Statements in One Transaction

```sql
BEGIN;

INSERT INTO clock_lab.events (note)
VALUES ('first-in-transaction');

SELECT pg_sleep(1.5);

INSERT INTO clock_lab.events (note)
VALUES ('second-in-transaction');

SELECT
    event_id,
    note,
    tx_started_at,
    statement_started_at,
    recorded_wall_at
FROM clock_lab.events
ORDER BY event_id;

ROLLBACK;
```

In the lab, the two new rows show:

- Identical `tx_started_at` because the transaction has not changed.
- Different `statement_started_at` values separated by roughly 1.5 seconds between the two `INSERT` statements.
- `recorded_wall_at` reflecting when each row's default evaluated, so typically also different.

`ROLLBACK` discards the two inserted rows. If `clock_lab.events` already had prior rows, the full-table `SELECT` displays them too; add `WHERE note IN (...)` when inspecting only the two test rows.

**Note:** sequences/identities in PostgreSQL can still advance even if a transaction rolls back. Never judge timestamp correctness by whether `event_id` values are gapless.

### 10.2. If Two INSERTs Share a Transaction, Is DEFAULT now() "Wrong"?

No. `tx_started_at` intentionally records **when the transaction started**. If a field means "all actions within the same transaction share a batch timestamp," that is the desired behavior.

If you need "when the server received the statement," use `statement_timestamp()`. If you need "when the expression ran on the system clock," use `clock_timestamp()`.

No single choice fits every table; column names should match their **temporal semantics**.

## 11. Single Multi-Row INSERT: Which Values Stay Uniform?

Suppose you insert multiple rows in one statement:

```sql
BEGIN;

INSERT INTO clock_lab.events (note)
SELECT 'bulk-' || g::text
FROM generate_series(1, 5) AS g;

SELECT
    event_id,
    note,
    tx_started_at,
    statement_started_at,
    recorded_wall_at
FROM clock_lab.events
WHERE note LIKE 'bulk-%'
ORDER BY event_id;

ROLLBACK;
```

Within that single `INSERT`:

- `tx_started_at` is identical across all rows because they share a transaction.
- `statement_started_at` is identical across all rows because they share a statement.
- `recorded_wall_at` comes from `clock_timestamp()` evaluated as each row is processed; values **can** differ, though in very fast inserts they may still match due to clock resolution.

If business rules require all rows in a batch to have **one identical timestamp**, explicitly choose transaction/statement time or pass a single batch timestamp from the service. Never rely on wall-clock reads happening to match.

### 11.1. Statement Timestamp Is Useful for Batches

If an `INSERT ... SELECT` processes 500,000 rows over several seconds, `statement_timestamp()` remains the start time of the statement. That is convenient for stamping when **batch processing began**, rather than when each row finished.

If you need batch completion time, measure it explicitly, since statement timestamp is not an end time.

## 12. Measuring Transaction and Statement Duration

You can measure elapsed time from transaction start or statement start up to wall clock:

```sql
SELECT
    clock_timestamp() - transaction_timestamp()
        AS elapsed_since_transaction_start,
    clock_timestamp() - statement_timestamp()
        AS elapsed_since_statement_start;
```

The result has type `interval`. Two separate `clock_timestamp()` calls may occur very close together yet not at the exact same instant.

### 12.1. Sampling the Wall Clock Once for Fair Comparison

If you want both subtractions to use the **exact same wall-clock sample**:

```sql
WITH sampled AS MATERIALIZED (
    SELECT clock_timestamp() AS observed_at
)
SELECT
    observed_at,
    observed_at - transaction_timestamp() AS tx_age,
    observed_at - statement_timestamp() AS statement_age
FROM sampled;
```

Since PostgreSQL 12, `AS MATERIALIZED` explicitly tells the planner to materialize `observed_at` in the CTE. For a single-row CTE containing a volatile function, PostgreSQL also has anti-inlining rules; this example mainly illustrates the intent of **sampling one timestamp**.

Estimated durations remain subject to OS clock adjustments. For high-reliability latency metrics, use dedicated monitoring tools or monotonic clocks at the application tier where appropriate.

### 12.2. Converting an Interval to Seconds

```sql
WITH sample AS MATERIALIZED (
    SELECT clock_timestamp() AS observed_at
)
SELECT
    EXTRACT(EPOCH FROM
        (observed_at - transaction_timestamp())
    ) AS seconds_since_tx_start,
    EXTRACT(EPOCH FROM
        (observed_at - statement_timestamp())
    ) AS seconds_since_statement_start
FROM sample;
```

`EXTRACT(EPOCH FROM interval)` gives the interval's length in seconds, possibly with a fractional part.

**Do not confuse these two operations:**

- `EXTRACT(EPOCH FROM some_timestamptz)` extracts an instant as Unix epoch seconds.
- `EXTRACT(EPOCH FROM some_interval)` extracts **elapsed duration** in seconds.

### 12.3. Measuring a Long SQL Statement

During `SELECT pg_sleep(1.5)`, the wait happens inside that statement. Calling `statement_timestamp()` in the **next statement** reflects the new statement's start time, not the previous statement's start. To measure executed statements, use client timing, database/statement logging, or monitoring statistics.

Never take `clock_timestamp() - statement_timestamp()` in a short `SELECT` after a long query finishes and mistake it for the long query's runtime—those are two separate statements.

## 13. Viewing Session and Running Query Times via pg_stat_activity

PostgreSQL's system view `pg_stat_activity` typically includes:

- `backend_start`: when the backend process started.
- `xact_start`: when the current transaction began, or NULL if no transaction is active.
- `query_start`: when the current query started while the backend is active; when inactive, it reflects the most recent query per state semantics.
- `state_change`: when the backend last changed state.
- `state`: state such as `active`, `idle`, or `idle in transaction`.

Inspect your own current session:

```sql
SELECT
    pid,
    state,
    backend_start,
    xact_start,
    query_start,
    state_change,
    clock_timestamp() AS observed_at
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
```

Note that `pg_stat_activity` is a system monitoring view governed by privilege rules; inspecting full details of other sessions requires appropriate permissions. Never grant broad monitoring privileges to application accounts just to run exercises.

### 13.1. Age of Open Transactions

```sql
SELECT
    pid,
    state,
    clock_timestamp() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY transaction_age DESC;
```

This query helps spot long-running transactions or `idle in transaction` sessions, which can hold snapshots and locks that block `VACUUM` or other writers.

A long transaction is not automatically a bug: it could be a legitimate batch job. Still, you should understand why it is open, set operational limits, and alert when durations exceed SLAs.

### 13.2. Elapsed Time of an Active Query

```sql
SELECT
    pid,
    state,
    clock_timestamp() - query_start AS query_age
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start IS NOT NULL
ORDER BY query_age DESC;
```

For `active` sessions, `query_start` works well to compute query age at sample time. Do not interpret `query_start` on an `idle` session as meaning "a query is still running since then."

### 13.3. Wall Clock and MVCC Are Not the Same

`transaction_timestamp()` stays fixed at transaction start, whereas the MVCC snapshot determines **which row versions a query can see** according to isolation level. They both relate to transactions, yet are distinct mechanisms:

- Under `READ COMMITTED`, successive statements can see newer data snapshots within the same transaction.
- `transaction_timestamp()` still stays unchanged.
- Under `REPEATABLE READ`, multiple statements share the transaction's snapshot per isolation rules, which does not stop `clock_timestamp()` from advancing.

Do not conclude a query's data snapshot equals "the `now()` timestamp" and use timestamps to deduce which committed rows are visible. MVCC manages visibility through its own transaction/snapshot mechanism.

## 14. Use Case 1: created_at, updated_at, and Auditing

Common column names include:

```text
created_at
updated_at
processed_at
statement_received_at
transaction_started_at
sent_at
committed_at
```

Different names reflect potentially different semantics. Before choosing a function, ask: **which event's timestamp do we want?**

### 14.1. created_at DEFAULT now()

A common pattern:

```sql
CREATE TABLE clock_lab.notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

For short transactions, `now()` is usually a clean, consistent timestamp for rows created together. However, if a transaction started long before inserting rows, `created_at` can be noticeably earlier than when the database actually ran `INSERT`.

### 14.2. updated_at Does Not Change Automatically on UPDATE

PostgreSQL does not automatically refresh a column named `updated_at` on `UPDATE` just because it has an insert default. To update it automatically, you must:

- Write `SET updated_at = ...` in each update statement; or
- Use a trigger; or
- Use an explicit application/ORM mechanism.

DML example:

```sql
UPDATE clock_lab.notes
SET
    body = 'New content',
    updated_at = statement_timestamp()
WHERE note_id = 1;
```

This uses `statement_timestamp()` when you want every row touched by one `UPDATE` to share the same timestamp. Ensure `WHERE` is properly scoped so you do not update unintended rows.

### 14.3. updated_at Trigger with Wall-Clock Time

```sql
CREATE OR REPLACE FUNCTION clock_lab.set_note_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_note_updated_at
BEFORE UPDATE ON clock_lab.notes
FOR EACH ROW
EXECUTE FUNCTION clock_lab.set_note_updated_at();
```

This example picks `clock_timestamp()` to capture the live clock as the trigger processes each row. In a multi-row `UPDATE`, timestamps across rows **can differ**, and PostgreSQL does not guarantee they are unique identifiers.

If policy requires **all rows modified by one statement to share the same timestamp**, use `statement_timestamp()` inside the trigger. If all changes across a transaction should share a timestamp, use `transaction_timestamp()` or `now()`.

### 14.4. A Trigger Firing Does Not Mean the Update Committed

A trigger runs inside a transaction that may still roll back. An `updated_at` set via `clock_timestamp()` is **not proof that the transaction committed**.

For strong auditing, systems also need transaction/event IDs, actor identity, change reasons, commit/rollback status at the appropriate logging layer, and retention controls. A timestamp alone does not guarantee durability of the event trail.

## 15. Use Case 2: Expiration and TTL

Consider an `expires_at timestamptz` column storing an absolute expiration instant:

```sql
CREATE TABLE clock_lab.tokens (
    token_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL
);
```

Insert a token with a 15-minute lifetime computed from **one sampled wall-clock timestamp**:

```sql
WITH sampled AS MATERIALIZED (
    SELECT clock_timestamp() AS issued_at
)
INSERT INTO clock_lab.tokens (token_id, created_at, expires_at)
SELECT
    1001,
    issued_at,
    issued_at + INTERVAL '15 minutes'
FROM sampled;
```

Benefit: `created_at` and `expires_at` share the exact same `issued_at` value, avoiding tiny skew between two separate clock reads.

### 15.1. Checking Token Validity

When evaluating against statement start:

```sql
SELECT token_id
FROM clock_lab.tokens
WHERE expires_at > statement_timestamp();
```

When checking the live clock as expressions evaluate:

```sql
SELECT token_id
FROM clock_lab.tokens
WHERE expires_at > clock_timestamp();
```

On large tables, these two approaches have **different semantics and optimization characteristics**. `statement_timestamp()` gives a stable cutoff across the statement, making it easier to match index bounds; `clock_timestamp()` is volatile, meaning the cutoff can shift mid-scan and restrict certain optimizations.

### 15.2. Long Transactions Can Evaluate TTL Against a Stale Reference

```sql
BEGIN;

SELECT pg_sleep(5);

SELECT token_id
FROM clock_lab.tokens
WHERE expires_at > now();

ROLLBACK;
```

In the final query, `now()` is **when the transaction began**, not 5 seconds later. A token that expired during those 5 seconds can still pass `expires_at > now()`.

This is not a PostgreSQL bug; it simply means **transaction-start semantics are wrong** if expiration must be evaluated at statement start or live clock time.

### 15.3. Choosing the Function Based on Product Policy

| Requirement | Usually Suitable Reference |
| --- | --- |
| Every check within a transaction uses one shared reference time | `transaction_timestamp()` |
| One statement evaluates all tokens against a single consistent cutoff | `statement_timestamp()` |
| Must read the live clock during an active check | `clock_timestamp()` |

For token security, expiration policies also involve clock skew between hosts, network latency, and validation order. Simply picking a SQL function does not solve every security concern.

## 16. Use Case 3: Dashboards and "Today"

"Today" depends on both **time zone and observation moment**.

For example, a user views a report by Vietnam calendar day while `ordered_at` is stored as `timestamptz`:

```sql
SELECT
    (transaction_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS transaction_local_date,
    (statement_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS statement_local_date,
    (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS wall_local_date;
```

If a transaction crosses midnight, `transaction_local_date` can still be yesterday while `wall_local_date` is today.

### 16.1. Example Filtering by Business Date

Suppose a table has a `timestamptz` column. For a specific date range:

```sql
-- Example on clock_lab.events, filtering 2026-11-14 in Vietnam.
SELECT
    event_id,
    note,
    recorded_wall_at
FROM clock_lab.events
WHERE recorded_wall_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND recorded_wall_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY recorded_wall_at, event_id;
```

The condition uses a **half-open interval** `[day_start, next_day_start)`. This avoids end-of-day bugs compared to constructing `23:59:59.999999`, and lets PostgreSQL use a B-tree index on `recorded_wall_at` as a range scan.

If the report needs a dynamic "today," compute the local date from `statement_timestamp()` in a CTE and derive the two boundary instants:

```sql
WITH report_day AS (
    SELECT
        (statement_timestamp()
            AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_date
)
SELECT
    e.event_id,
    e.recorded_wall_at
FROM clock_lab.events AS e
CROSS JOIN report_day AS d
WHERE e.recorded_wall_at >=
        (d.local_date::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND e.recorded_wall_at <
        ((d.local_date + 1)::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh')
ORDER BY e.recorded_wall_at, e.event_id;
```

In DST regions, two consecutive local midnights can be 23, 24, or 25 real hours apart. Constructing boundaries from **local calendar dates and time zones** is therefore more accurate than adding 24 hours to the start instant.

## 17. STABLE vs. VOLATILE Functions: Why Does the Optimizer Care?

PostgreSQL classifies functions by how their values can vary and affect query planning:

- `IMMUTABLE`: given the same inputs, guarantees the same result forever, independent of external state.
- `STABLE`: within a single statement, considered constant for optimization purposes, though it may differ across statements.
- `VOLATILE`: result or side effects can change even within the same statement.

Among the time functions studied here:

- `now()` and `transaction_timestamp()` provide stable transaction-level timestamps.
- `statement_timestamp()` is stable within a statement.
- `clock_timestamp()` is **VOLATILE** because its value can change across calls within the same statement.
- `timeofday()` carries volatile wall-clock semantics as text and should never be treated as immutable.

### 17.1. Difference in WHERE

Compare:

```sql
-- Fixed cutoff for the statement per function semantics.
SELECT event_id
FROM clock_lab.events
WHERE recorded_wall_at >=
      statement_timestamp() - INTERVAL '1 hour';
```

And:

```sql
-- Wall clock can advance while scanning rows.
SELECT event_id
FROM clock_lab.events
WHERE recorded_wall_at >=
      clock_timestamp() - INTERVAL '1 hour';
```

In the second query, the "one hour ago" threshold drifts forward as time is sampled, so a row near the boundary could evaluate differently if reached later in the scan.

Predicates containing volatile functions are harder for the planner to turn into a **fixed index scan bound** compared to stable functions. Still, do not conclude PostgreSQL **always** forces a full table scan; plans depend on query shape, indexes, data, and expression structure.

### 17.2. Indexing Timestamp Columns

```sql
CREATE INDEX idx_clock_events_recorded_wall
ON clock_lab.events (recorded_wall_at);
```

A range query can leverage this index when the filter is selective enough:

```sql
EXPLAIN
SELECT event_id, note
FROM clock_lab.events
WHERE recorded_wall_at >= statement_timestamp() - INTERVAL '1 day'
ORDER BY recorded_wall_at DESC
LIMIT 100;
```

In a tiny lab table, PostgreSQL will likely still choose a sequential scan. That is a rational cost-based decision, not evidence of a broken index.

### 17.3. Do Not Use clock_timestamp in Expression Indexes

An index expression must meet PostgreSQL's immutability requirements. You cannot build a meaningful static index over a continuously ticking wall clock:

```sql
-- Invalid due to index expression immutability rules:
-- CREATE INDEX idx_bad_clock
-- ON clock_lab.events ((clock_timestamp()));
```

To find recent rows from the last hour, index the **stored timestamp column** and supply the cutoff expression at query runtime, rather than expecting an index to update itself every second.

### 17.4. Generated Columns Are Also Not for Live Clocks

Generated columns enforce expression restrictions, and stored generated columns disallow volatile functions like `clock_timestamp()`.

To record creation/update times, use `DEFAULT` or explicit DML/triggers, never a generated column acting as an independent clock.

## 18. Wall-Clock Time Is Not a Monotonic Counter

`clock_timestamp()` reads the OS **wall clock**. Wall clocks can be adjusted by time synchronization services, configuration changes, or rare operational events.

Therefore:

- Do not assume two `clock_timestamp()` readings are guaranteed to increase strictly across every call.
- Do not use timestamps alone to generate unique IDs or decide global ordering in distributed systems.
- Do not treat wall-clock differences as absolute durations immune to clock adjustments.

### 18.1. Measuring Duration in Java

When a Java application measures latency of a method or request, a monotonic clock like `System.nanoTime()` is usually better than calling `LocalDateTime.now()` twice and subtracting.

Example:

```java
long started = System.nanoTime();
try {
    callDatabase();
} finally {
    long elapsed = System.nanoTime() - started;
    double milliseconds = elapsed / 1_000_000.0;
    recordMetric(milliseconds);
}
```

`System.nanoTime()` measures **elapsed time within a single JVM/process context**, not an absolute wall-clock date-time for database storage. `callDatabase()` and `recordMetric(...)` here represent application methods defined separately.

### 18.2. Event Ordering in Distributed Systems

When two services on different machines write events, timestamps can be skewed by:

- Clock drift between hosts.
- Network latency.
- Differences between event creation, send, receipt, and commit times.
- Timestamp resolution and multiple events sharing the same timestamp.

When causal order or strict stream sequence is needed, also use sequences, offsets, versions, structured IDs, or appropriate transaction/message-log ordering. Timestamps are observational attributes, not always sufficient proof of total order.

## 19. Temporal Correctness in Long Transactions

Suppose a batch job opens a transaction at 09:00 and finishes at 09:30.

Throughout the transaction:

```sql
SELECT now();
```

still returns transaction start around 09:00. This affects:

- `created_at DEFAULT now()` on a row inserted at 09:28.
- `expires_at > now()` for a token checked at 09:29.
- "Recent data in the last 5 minutes" filters using `now() - interval '5 minutes'`.
- Reports using `CURRENT_DATE` if the transaction crosses midnight.

### 19.1. Why Did PostgreSQL Choose Transaction Start?

A stable transaction timestamp brings clear benefits:

1. SQL statements inside the same transaction share **one consistent reference time** when calling `now()`.
2. A batch writing across multiple tables is stamped uniformly by transaction.
3. Repeated time comparisons inside a transaction do not drift due to wall-clock ticks.

It is an intentional design choice, not a PostgreSQL flaw.

### 19.2. When Should You Switch to statement_timestamp?

When requirements specify "when the server started processing this statement," such as:

- A report statement evaluating one uniform expiration cutoff.
- A multi-row `UPDATE` stamping all updated rows with the same statement start time.
- Recording command receipt time for operational analysis.

`statement_timestamp()` advances per statement while staying uniform within each statement.

### 19.3. When Should You Use clock_timestamp?

When you need the live wall clock read after a specific step, for example:

- Capturing the real instant a trigger actually executes.
- Observing wall-clock progress before and after `pg_sleep` inside a PL/pgSQL block.
- Sampling instantaneous time in an intentional verification step.
- Measuring wall-clock progress inside a long statement or transaction.

Do not choose `clock_timestamp()` merely because "real time" sounds nicer than `now()`; volatility adds planning/runtime constraints and changes query semantics.

## 20. The Three Timestamps vs. MVCC Snapshots

Three concepts are often conflated:

| Concept | Question It Answers |
| --- | --- |
| Transaction timestamp | When did the transaction begin? |
| Statement timestamp | When did the current statement begin? |
| MVCC snapshot | **Which row versions is this statement/transaction allowed to see**? |

Under `READ COMMITTED` (the default), each statement takes a fresh snapshot as the statement starts. Under `REPEATABLE READ`, read statements within the transaction share the transaction's snapshot under PostgreSQL's isolation rules.

However:

- `now()` is not a snapshot ID.
- `statement_timestamp()` does not prove a specific row is visible.
- `clock_timestamp()` does not change visibility of uncommitted data from other transactions.
- Row creation timestamps are not the "commit order" implied by MVCC.

For example, two concurrent transactions can commit in the opposite order from how they began. With `created_at DEFAULT now()`, the row from the earlier transaction **can commit later** than the row from the newer transaction.

Never rely on `ORDER BY created_at` as absolute proof of commit order when strict transaction ordering matters.

## 21. Can PostgreSQL Measure Commit Timestamps?

`transaction_timestamp()` is **not** a commit timestamp function. Calling `clock_timestamp()` right before `COMMIT` is not the actual commit instant either.

PostgreSQL offers optional/internal tracking features such as `track_commit_timestamp` and specialized system functions when enabled and supported, but that is a **separate administrative feature with retention and availability limits**. Never assume every database can look up exact historical commit times for arbitrary transactions.

If a system genuinely needs to know when a workflow completed, emit events after commit succeeds, track confirmation state at the service layer, and use reliable outbox/logging patterns. A `committed_at DEFAULT now()` column cannot replace that.

## 22. Storing Time with Time Zones in Java Applications

In Java, you encounter:

- `Instant`: an absolute instant on the timeline.
- `OffsetDateTime`: date and time with a UTC offset.
- `ZonedDateTime`: date and time in a rule-based time zone such as `Asia/Ho_Chi_Minh`.
- `LocalDateTime`: local date and time **with no time zone information**.
- `LocalDate`: calendar date.

When persisting real-world event instants, PostgreSQL's `timestamptz` aligns naturally with an instant model. The PostgreSQL JDBC driver supports mappings such as `OffsetDateTime` for `timestamptz` in compatible versions, and many applications convert to `Instant` in the domain layer.

### 22.1. Avoid Losing Time Zone Context During Mapping

If a service reads a `timestamptz` and converts it to `LocalDateTime` without specifying a zone, the value can be misinterpreted on machines in other time zones.

Java example:

```java
Instant instant = Instant.parse("2026-07-01T12:00:00Z");
ZoneId vietnamZone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime vietnamTime = instant.atZone(vietnamZone);
// 2026-07-01T19:00+07:00[Asia/Ho_Chi_Minh]
```

The `Instant` remains `12:00Z`; `ZonedDateTime` expresses it in Vietnam time. This mirrors how PostgreSQL displays the same `timestamptz` across different session time zones.

### 22.2. Database Clock or Application Clock?

| Option | Benefit | Trade-off |
| --- | --- | --- |
| Database `now()`/`statement_timestamp()` | Gives PostgreSQL's transaction/statement reference time. | Requires understanding transaction length and time zones. |
| Database `clock_timestamp()` | Wall-clock time as read by PostgreSQL. | Volatile; not uniform across a batch. |
| Java service passes `Instant.now()` | Consistent with service/domain event logic. | Depends on app host clock, which may skew from DB/other hosts. |

When multiple hosts write data concurrently, choose an **authoritative clock source** and maintain time synchronization policies. Never mix database and application timestamps casually while assuming they follow a strict total order.

### 22.3. PreparedStatement Does Not Change Temporal Semantics

SQL using `DEFAULT now()`, `statement_timestamp()`, or `clock_timestamp()` is still evaluated by PostgreSQL when the statement executes under each function's semantics. Using a Java `PreparedStatement` does not freeze `now()` at statement preparation time.

Still, never pass date-time expressions via unvalidated string concatenation. Bind properly typed timestamp parameters and manage time zones consistently.

## 23. Choosing Timestamps for Batch Jobs and ETL

In ETL pipelines, several distinct timestamps often exist:

```text
source_event_time      -- when the event happened at the source
source_created_at      -- when the source system stored the event
ingested_at            -- when the pipeline received the event
processed_at           -- when the worker processed it
loaded_at              -- when the row was written to PostgreSQL
batch_started_at       -- when the batch began
batch_completed_at     -- when the batch actually finished
```

These columns **cannot all be replaced by a single `now()`** without losing meaning.

### 23.1. One Transaction for an Entire Batch

If an ETL job runs `BEGIN`, loads millions of rows over 20 minutes, and sets `loaded_at DEFAULT now()`, every row gets the **batch transaction start** time.

That is desirable if `loaded_at` means "batch start." If you want latency analysis down to when each chunk landed, consider `statement_timestamp()` or per-chunk processing times.

### 23.2. Multiple Statements in One Transaction

`statement_timestamp()` fits when each `INSERT`/`COPY`/`UPDATE` represents its own processing unit. Each statement receives a distinct timestamp even inside a shared transaction.

If you need one uniform timestamp across multiple transactions in a batch, do not expect `transaction_timestamp()` to match across transactions; generate `batch_id` and `batch_started_at` once and pass them explicitly across operations.

### 23.3. Never Use Timestamps as Idempotency Keys

Two valid events can share the same timestamp. A retried event can be processed a second time with a different timestamp. Using a timestamp alone as a "processed?" key risks double-counting or dropping records.

Use event IDs, sequence numbers, or proper business keys backed by transactions and constraints.

## 24. Time in DEFAULT, Triggers, and SELECT: Use-Case Comparison

| Need | Suggestion | Explanation |
| --- | --- | --- |
| Multiple rows in one transaction need a shared timestamp | `DEFAULT now()` | All receive transaction start. |
| Each statement needs one uniform timestamp | `DEFAULT statement_timestamp()` | Same statement shares one timestamp. |
| Need wall-clock time as each row is processed | `DEFAULT clock_timestamp()` | Values can differ per evaluation. |
| Audit when an update statement began | `updated_at = statement_timestamp()` | Reflects statement start. |
| Measure elapsed time between PL/pgSQL steps | `clock_timestamp()` twice sequentially | Live clock at each step. |
| Check TTL as of statement start | `expires_at > statement_timestamp()` | Single stable cutoff for the whole SQL query. |
| Check TTL per transaction | `expires_at > now()` | Constant cutoff within transaction; watch long transactions. |
| Report by "Vietnam calendar day" | Time-zoned timestamp + convert to `Asia/Ho_Chi_Minh` | Avoids implicit session time zone dependency. |
| Legacy wall-clock debug logging | `timeofday()` may appear | Returns text; prefer `clock_timestamp()` in new code. |
| Prove successful commit | Transaction outcome + proper event/logging | No column default guarantees commit semantics. |

Every choice is a **semantic decision**. Never switch an entire system from `now()` to `clock_timestamp()` just because "closer to real time sounds better" without checking requirements.

## 25. Common Misconceptions

### Mistake 1. Thinking now() Reads a Fresh Clock Every Call

Within one transaction, `now()` always reflects transaction start. Test with `BEGIN; ... pg_sleep(...) ... COMMIT;`, not two autocommit `SELECT`s.

### Mistake 2. Thinking statement_timestamp() Never Changes Between Statements

It stays constant **within one statement**, while the next statement gets its own timestamp even inside the same transaction.

### Mistake 3. Thinking clock_timestamp() Always Increases

OS clocks can be adjusted and resolution is finite. Never substitute wall-clock timestamps for sequences or monotonic timers.

### Mistake 4. Confusing now() with Commit Time

`now()` is transaction start; rows can be written inside a transaction that later rolls back. Never treat it as proof of commit.

### Mistake 5. Using CURRENT_DATE for Live Date Inside Long Transactions

`CURRENT_DATE` derives from transaction start and session time zone. Across midnight, "today in the real world" may already have changed.

### Mistake 6. Dropping Time Zones for Cross-Region Events

`timestamp without time zone` does not identify an absolute instant. For real events, consider `timestamptz` and convert time zones on display.

### Mistake 7. Assuming timestamptz Stores the Original Zone Name

It stores an instant, not `Asia/Ho_Chi_Minh` as per-row metadata. If business logic needs the user's chosen time zone, store a separate zone ID column.

### Mistake 8. Using Literal 'now' as a Dynamic DEFAULT

A literal cast to timestamp at parse/definition time can freeze to a constant. Use `DEFAULT now()`, `DEFAULT CURRENT_TIMESTAMP`, or another function.

### Mistake 9. Thinking DEFAULT updated_at Runs Automatically on UPDATE

Defaults apply on insert or explicit `DEFAULT` usage; they do not automatically update `updated_at` on every `UPDATE`. Use explicit DML or a trigger.

### Mistake 10. Using clock_timestamp() in WHERE Without Considering the Optimizer

A volatile value can change mid-scan; index bounds and query semantics differ from stable functions. If a uniform cutoff suffices, consider `statement_timestamp()`.

### Mistake 11. Using timeofday() for Time Arithmetic

`timeofday()` returns `text`. Subtract and compare timestamps using genuine temporal types rather than formatted strings.

### Mistake 12. Putting Timing Tests in One SELECT and Inferring Evaluation Order

Do not treat select-list expression order as a guarantee for side-effect ordering. Use `DO` blocks or sequential statements to measure between steps.

### Mistake 13. Confusing Timestamps with MVCC Snapshots

Clocks and transactional data visibility are separate mechanisms. Transaction start time is not commit order.

### Mistake 14. Generating IDs from Timestamps

Two records can share the same microsecond or clocks can jump. Use primary keys, identity/sequence columns, UUIDs, or dedicated ID schemes.

### Mistake 15. Comparing Times Across Hosts Without a Sync Policy

App servers and database servers can have skewed clocks. When reconciling events, record timestamp sources and maintain explicit clock/timezone policies.

### Mistake 16. Measuring Request Latency Solely with Two Wall Timestamps

Wall clocks can step backward or forward. In Java, prefer `System.nanoTime()` for in-process durations; in PostgreSQL, use proper query monitoring tools and understand timestamp limits.

### Mistake 17. Assuming Different clock_timestamp Values Imply Distinct Events

Resolution and sampling timing do not guarantee uniqueness. Separate event identity from event timestamp.

### Mistake 18. Naming a Column created_at While Using the Wrong Reference Time

If a column truly means "when `INSERT` executed," `now()` inside a long transaction may not fit. Rename the policy or choose the right function intentionally.

## 26. Combined Session Lab

These exercises can be run in `psql` or a GUI keeping a single persistent connection. Actual readings depend on the PostgreSQL server's clock.

### 26.1. Testing Without an Explicit Transaction

```sql
SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;

SELECT pg_sleep(1);

SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;
```

Observation: in autocommit mode, both transaction and statement times advance between SQL statements.

### 26.2. Testing Inside an Explicit Transaction

```sql
BEGIN;

SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;

SELECT pg_sleep(1);

SELECT
    now() AS tx,
    statement_timestamp() AS stmt,
    clock_timestamp() AS wall;

ROLLBACK;
```

Observation: transaction time stays constant; statement and wall times advance.

### 26.3. Testing Inside a Single Statement

```sql
DO $$
DECLARE
    tx_1 timestamptz;
    tx_2 timestamptz;
    stmt_1 timestamptz;
    stmt_2 timestamptz;
    wall_1 timestamptz;
    wall_2 timestamptz;
BEGIN
    tx_1 := transaction_timestamp();
    stmt_1 := statement_timestamp();
    wall_1 := clock_timestamp();

    PERFORM pg_sleep(1);

    tx_2 := transaction_timestamp();
    stmt_2 := statement_timestamp();
    wall_2 := clock_timestamp();

    RAISE NOTICE
        'transaction_same=%, statement_same=%, wall_diff_seconds=%',
        tx_1 = tx_2,
        stmt_1 = stmt_2,
        EXTRACT(EPOCH FROM wall_2 - wall_1);
END;
$$;
```

Under normal conditions, the notice output shows:

```text
transaction_same = true
statement_same   = true
wall_diff_seconds around >= 1
```

Actual values can vary slightly due to OS scheduling; wall clocks can also be adjusted, so exact intervals are never guaranteed.

## 27. Practice Exercises

The exercises use the PostgreSQL statements learned above. Some examples operate on `clock_lab` and `clock_lab_example`; run them in a test environment, never deleting production data.

### Exercise 1. Classifying the Three Functions

State the reference point for `now()`, `statement_timestamp()`, and `clock_timestamp()`, and explain which one can change within a single statement.

### Exercise 2. Choosing Time for INSERT

An application wants a single batch `INSERT` of 10,000 rows to share the statement's start time, even if it takes 5 seconds to complete. Which default should you pick?

### Exercise 3. Long Transaction

Inside a transaction, `BEGIN` runs at 10:00 and the second statement runs at 10:05. Predict `now()` and `statement_timestamp()` at the second statement.

### Exercise 4. Clock Inside DO

Write a `DO` block containing two `clock_timestamp()` calls with `pg_sleep(2)` in between. Contrast with two reads of `statement_timestamp()`.

### Exercise 5. CURRENT_DATE Across Midnight

Suppose a transaction starts before 00:00 Vietnam time and finishes after 00:00. With the time zone setting unchanged, does `CURRENT_DATE` necessarily roll over to the new date? Why?

### Exercise 6. Transaction Identity

Write a query verifying `now() = transaction_timestamp()` and `now() = CURRENT_TIMESTAMP`. What result do you expect?

### Exercise 7. Time Zone

Convert `TIMESTAMPTZ '2026-07-01 12:00:00+00'` to local time in `Asia/Ho_Chi_Minh` using `AT TIME ZONE`.

### Exercise 8. Date in Vietnam

Write an expression getting the Vietnam calendar `date` of `statement_timestamp()`, independent of session time zone.

### Exercise 9. Measuring Duration

Compute elapsed seconds from transaction start to a `clock_timestamp()` call. State the limitations of wall-clock measurement.

### Exercise 10. timeofday

What type does `timeofday()` return, and why should you not use it to compute durations?

### Exercise 11. created_at in a Long Transaction

A table has `created_at timestamptz DEFAULT now()`. The transaction opens at 09:00 and `INSERT` runs at 09:10. Which moment does `created_at` normally reflect?

### Exercise 12. TTL

An application wants a single statement to check all tokens against **one uniform expiration cutoff at statement start**. Choose `now()`, `statement_timestamp()`, or `clock_timestamp()`? Why?

### Exercise 13. Index and Volatility

Why is `occurred_at >= statement_timestamp() - interval '1 hour'` easier to optimize with a B-tree index than the same condition using `clock_timestamp()`?

### Exercise 14. updated_at

Write a PostgreSQL trigger updating `updated_at` to `statement_timestamp()` on every `UPDATE` of `clock_lab.notes`. Contrast with a trigger using `clock_timestamp()`.

### Exercise 15. SQL NULL and Time Zones

Explain the difference between `timestamptz` and `timestamp without time zone`. If business rules need **the customer's chosen time zone name**, is storing `timestamptz` alone sufficient?

### Exercise 16. Commit Timestamp

Why should you not name a column `committed_at` with `DEFAULT now()` and claim it records commit time?

### Exercise 17. Consistent Token Timestamps

Write an `INSERT` creating a token with `created_at` set to wall clock and `expires_at = created_at + interval '15 minutes'`, using **a single wall-clock sample**.

### Exercise 18. Comparing Columns for Query Monitoring

In `pg_stat_activity`, which fields show transaction start, query start, and last state change? Which field helps compute the age of an `active` query?

### Exercise 19. Two Hosts with Skewed Clocks

Service A records `2026-11-14T10:00:00Z`, and Service B records `2026-11-14T09:59:59Z`. Can you conclude event A occurred after B? What additional evidence is needed?

### Exercise 20. Choosing Reference Times for ETL

An ETL job has a 20-minute transaction running 50 statements. You want:

1. One shared timestamp for the whole transaction.
2. Separate timestamps per statement.
3. Live wall-clock time as each row is processed.

Pick the corresponding functions and note their cost and semantic differences.

## 28. Solution Hints

### Answer 1

`now()` is transaction start, `statement_timestamp()` is statement start, and `clock_timestamp()` is live wall clock at call time. Only the wall-clock function can advance within the same statement under these semantics.

### Answer 2

`DEFAULT statement_timestamp()`. All rows in the same statement get the statement start time; across multiple statements in a batch, each statement gets its own timestamp.

### Answer 3

`now()` reflects around 10:00; `statement_timestamp()` reflects around 10:05. Exact fractional seconds and offsets depend on session and server settings.

### Answer 4

```sql
DO $$
DECLARE
    before_clock timestamptz;
    after_clock timestamptz;
    before_stmt timestamptz;
    after_stmt timestamptz;
BEGIN
    before_stmt := statement_timestamp();
    before_clock := clock_timestamp();
    PERFORM pg_sleep(2);
    after_clock := clock_timestamp();
    after_stmt := statement_timestamp();

    RAISE NOTICE 'stmt_same=%, wall_elapsed=%',
        before_stmt = after_stmt,
        after_clock - before_clock;
END;
$$;
```

Statement timestamps match; wall-clock timestamps are typically separated by at least roughly 2 seconds depending on system conditions.

### Answer 5

No. `CURRENT_DATE` reflects the date from transaction start in the session time zone. With the time zone unchanged, transaction start does not move across midnight, so the date remains pinned to transaction start.

### Answer 6

```sql
SELECT
    now() = transaction_timestamp() AS same_tx,
    now() = CURRENT_TIMESTAMP AS same_current;
```

Both expressions evaluate to `true` inside the same transaction.

### Answer 7

```sql
SELECT
    TIMESTAMPTZ '2026-07-01 12:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_local_time;
```

Result: `2026-07-01 19:00:00`, type `timestamp without time zone`.

### Answer 8

```sql
SELECT
    (statement_timestamp()
        AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS statement_day_vietnam;
```

### Answer 9

```sql
SELECT
    EXTRACT(
        EPOCH FROM
        (clock_timestamp() - transaction_timestamp())
    ) AS elapsed_seconds;
```

Wall-clock differences can be skewed if the OS clock is adjusted; it is not an absolute monotonic counter.

### Answer 10

`timeofday()` returns `text`. To compute durations, use `timestamptz` or `interval` values; using strings invites type, format, and time zone bugs.

### Answer 11

Within that transaction, `DEFAULT now()` reflects transaction start around 09:00, not 09:10.

### Answer 12

`statement_timestamp()`, because the statement needs a single uniform cutoff evaluated at statement start. `now()` can be stale if the transaction has been open long; `clock_timestamp()` can drift while scanning rows.

### Answer 13

`statement_timestamp()` is stable within a statement, so the planner can treat it as a consistent cutoff for an appropriate index range scan. `clock_timestamp()` is volatile, can change across evaluations, and restricts fixed scan bounds. Still, final index selection rests with the optimizer based on query and data.

### Answer 14

```sql
CREATE OR REPLACE FUNCTION clock_lab.set_note_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := statement_timestamp();
    RETURN NEW;
END;
$$;

-- If a trigger from earlier in the lesson already exists, avoid creating
-- a duplicate second trigger updating updated_at.
-- CREATE TRIGGER trg_note_updated_at
-- BEFORE UPDATE ON clock_lab.notes
-- FOR EACH ROW
-- EXECUTE FUNCTION clock_lab.set_note_updated_at();
```

With one trigger on `clock_lab.notes` calling the replaced function, all rows in the same `UPDATE` receive the same statement start time. Using `clock_timestamp()` allows them to differ per row processed.

### Answer 15

`timestamptz` represents an instant displayed per session time zone; `timestamp without time zone` carries no zone info to identify an instant. If you need the user's chosen time zone name, store a separate column such as `user_timezone text` with valid IANA names; `timestamptz` does not retain per-row zone names.

### Answer 16

`now()` is transaction start, and the transaction might commit seconds later or roll back. Thus it is not proof of actual commit time.

### Answer 17

```sql
WITH sampled AS MATERIALIZED (
    SELECT clock_timestamp() AS issued_at
)
INSERT INTO clock_lab.tokens (token_id, created_at, expires_at)
SELECT
    1002,
    issued_at,
    issued_at + INTERVAL '15 minutes'
FROM sampled;
```

Run when token 1002 does not already exist so it does not violate the primary key.

### Answer 18

`xact_start` is transaction start, `query_start` is query start, and `state_change` is the most recent state change. For `active` queries, use `clock_timestamp() - query_start` to check query age.

### Answer 19

No. Host clocks can be skewed and events travel over the network. You also need IDs, sequences/offsets, transaction/commit order, or causal relationships suited to your system.

### Answer 20

1. `transaction_timestamp()` or `now()`: shared across the transaction.
2. `statement_timestamp()`: uniform within each statement, advances between statements.
3. `clock_timestamp()`: reads wall clock on every evaluation, can differ per row, and carries volatility overhead.

## 29. Checklist Before Adopting Time Functions in a System

Before selecting a temporal expression for a schema or SQL query, answer:

1. **What is the business moment?** Transaction start, statement start, row processing time, event occurrence time, or commit time?
2. **Are there long transactions?** If so, could `now()` be too stale for TTL or "today"?
3. **Do multiple rows need the exact same timestamp?** If so, pick a stable reference or pass an explicit batch timestamp.
4. **Is strict total ordering needed?** Timestamps do not guarantee uniqueness or commit order.
5. **What is the column type?** `timestamptz` for instants; `timestamp without time zone` only for intentionally zone-less local date-times.
6. **What is the reporting time zone?** Never depend implicitly on session time zones when regional accuracy is required.
7. **Is Java mapping involved?** Pick `Instant`, `OffsetDateTime`, `ZonedDateTime`, or `LocalDateTime` matching the semantics.
8. **Are there time-range filters?** Function volatility can affect index eligibility and plans.
9. **Is logging/monitoring involved?** Distinguish `xact_start`, `query_start`, `statement_timestamp()`, and wall clock.
10. **Is commit auditing required?** Never use `now()` as proof of commit.
11. **Could clock skew or clock steps occur?** Distinguish wall-clock timestamps from monotonic durations.
12. **Do unit/integration tests cover long transactions and midnight crossings?** Those edge cases expose differences among the three clocks.

## 30. Summary

In PostgreSQL, "current time" is not a single concept:

- **`transaction_timestamp()`, `now()`, and `CURRENT_TIMESTAMP`** reflect **transaction start time**, remaining constant across all statements in a transaction.
- **`statement_timestamp()`** reflects **current statement start time**, stable within a statement while advancing across statements in the same transaction.
- **`clock_timestamp()`** reads the **live wall clock when called**, can change even within one statement, and is volatile.
- **`timeofday()`** also reads wall clock but returns `text`; it is rarely the right choice for calculations or typed timestamp storage.
- **`CURRENT_DATE`, `CURRENT_TIME`, `LOCALTIME`, and `LOCALTIMESTAMP`** follow transaction time and session time zone conversion/display rules.
- **`timestamptz`** represents an instant, whereas `timestamp without time zone` is a zone-less date-time. If the original zone name is needed, store it separately.
- **`DEFAULT`, triggers, TTL, batch loads, and auditing** must choose the reference matching the actual business event. A timestamp written mid-transaction is not commit time.
- **Measuring duration and optimizing queries** require understanding volatility and wall-clock limitations; use `EXPLAIN`, system views, or monotonic timers where appropriate.

One simple question guides the choice: **"Do I want one timestamp shared by the whole transaction, one shared by the statement, or the live clock as each calculation runs?"** Answering that clearly prevents subtle bugs in historical data, expirations, logs, and PostgreSQL reports.
