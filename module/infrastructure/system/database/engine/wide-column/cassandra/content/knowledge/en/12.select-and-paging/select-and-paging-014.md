# Verifying Queries with Tracing and Edge-Case Datasets

## Learning Objectives

After this lesson, you will be able to:

1. Use **query tracing** to observe the execution path of a `SELECT` statement in Apache Cassandra rather than guessing from syntax alone.
2. Distinguish **a query returning the right results**, **a query having a sound read path**, and **a query meeting performance SLOs**—three things that must be verified separately.
3. Build a CQL dataset containing **empty partitions, single-row/multi-row partitions, duplicate clustering timestamps, missing columns, range boundaries, and multiple partitions**.
4. Write test cases with explicit expectations for `WHERE`, `ORDER BY`, `LIMIT`, `PER PARTITION LIMIT`, `ALLOW FILTERING`, and pagination.
5. Read `TRACING ON` output in `cqlsh`, query tracing sessions, and understand what a trace **can** and **cannot** prove.
6. Enable tracing selectively in **Java Driver 4.x**, capture tracing IDs, and distinguish the current page from subsequent pages.
7. Test **`INSERT`, `DELETE`, `UPDATE`, TTL, and paging** scenarios without assuming a multi-read sequence forms an immutable snapshot.
8. Build a verification checklist before releasing a Cassandra API to production: correctness, scan scope, consistency, load, and security.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. The overarching goal of the module is understanding distributed wide-column databases: partition keys, query-driven table design, read/write replication and consistency, CQL, compaction, repair, error handling, and Java integration. Tracing is an observational aid for those components, yet **cannot replace an edge-case test dataset or benchmarks under representative load**.

## 1. Three Questions That Must Be Verified Independently

Suppose an API wants "the three newest events in a day for an account." A query looks deceptively short:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

To conclude the query is production-ready, you need three types of evidence:

| Question | Appropriate evidence | Insufficient to conclude |
| --- | --- | --- |
| **Are results correct?** | Dataset with expected values; asserting primary keys, values, and order | "Ran without errors" |
| **Is the read scope sound?** | Partition key and clustering range analysis; traces and metrics | "Only returned three rows" |
| **Is it fast and stable enough?** | p50/p95/p99, throughput, timeouts, replica load on representative data | "A single lab run took a few ms" |

A query using `ALLOW FILTERING` can return the **exact two right rows** while scanning a massive partition. Conversely, a `SELECT` with a tight read path can still return the **wrong order** if the author omitted the tie-breaking second clustering column for duplicate timestamps.

Therefore, the workflow of this lesson is:

```text
Define query contract
      |
      v
Create baseline + edge-case dataset
      |
      v
Run CQL, verify row keys and order
      |
      v
Enable tracing selectively to inspect read path
      |
      v
Compare trace + metrics, test paging and mutating data
      |
      v
Evaluate on production-like workload before release
```

**Principle:** A trace does not by itself tell you whether business logic is right; a test suite passing functional assertions does not by itself prove the query is cheap to operate.

## 2. Factors to Fix Before Running Tests

Results and cost for the exact same CQL statement vary with cluster configuration and data state. Record:

| Category | What to record | Why |
| --- | --- | --- |
| Schema | Partition key, clustering columns, clustering order, column types, indexes | Determines which predicates locate data. |
| CQL | Query string, bind values, projection, `ORDER BY`, `LIMIT` | Defines the exact result contract. |
| Data | Partition count, large/small partitions, duplicate timestamps, nulls, TTLs, tombstones | Exercises edge cases that clean synthetic data misses. |
| Versions | Cassandra, Java Driver, native protocol | Some behaviors and trace events vary by version. |
| Distribution | Replication strategy/factor, datacenters, consistency level | Affects contacted replicas and observed freshness. |
| Operations | Caches, compaction, repair, QPS, concurrent queries | Affects read amplification and tail latency. |

This lesson uses a **single-node Cassandra lab** to verify CQL results reproducibly. It **cannot fully simulate** unconverged replicas, node failures, or `LOCAL_QUORUM` on multi-node clusters. Distributed properties must be verified separately in a multi-node topology.

## 3. Baseline Dataset: Ten Rows, Three Partitions, and Edge Cases

### 3.1. Creating the Keyspace and Table

Use a **keyspace dedicated strictly to practice**. Never run the statements below on a production table holding real data.

```sql
-- Single-node lab: RF=1/SimpleStrategy is for practice only.
CREATE KEYSPACE IF NOT EXISTS cassandra_trace_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_trace_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Table keys:

| Column | Role | Consequence for `SELECT` |
| --- | --- | --- |
| `account_id`, `event_day` | **Composite partition key** | Both are required to pinpoint one partition. |
| `occurred_at` | First clustering column | Supports range predicates within a partition. |
| `event_id` | Second clustering column | Disambiguates two events sharing `occurred_at`. |
| `event_type`, `summary` | Regular columns | Do not automatically create indexes or read paths. |

With this schema, rows sharing `(account_id,event_day)` default to `occurred_at DESC, event_id DESC`.

### 3.2. Resetting the Lab Table to Initial State

If this is a **dedicated practice table and you have confirmed no data needs to be kept**, reset it before each test round:

```sql
-- DANGEROUS if applied to real data.
-- ONLY use on a dedicated lab table after confirming the target.
TRUNCATE events_by_account_day;
```

`TRUNCATE` wipes all data in the table; never put it in migrations or application endpoints. If you lack permission to truncate, create a fresh practice keyspace/table and ensure old runs do not contaminate initial data.

### 3.3. Inserting Seven Rows for Account A / Day 20

```sql
-- Single partition: (A, 2026-11-20), fixed event_id values.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed list'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Opened details'
);

-- Same timestamp 10:00, different primary key.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Paid'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'VIEW', 'Viewed invoice'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'SHIP', 'Handed to carrier'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 13:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGOUT', 'Logged out'
);
```

### 3.4. Adding a Sparse Partition and Missing Column

```sql
-- Account A, day 21: second partition, two rows.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'New day'
);

-- Intentionally OMIT summary: regular column with missing value.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 08:00:00+0000',
    00000000-0000-4000-8000-000000000009,
    'VIEW'
);

-- Account B, day 20: third partition, one row.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 06:00:00+0000',
    00000000-0000-4000-8000-000000000010,
    'LOGIN', 'Account B'
);
```

**Baseline data after this step:**

| Partition key | Rows | Edge case tested |
| --- | ---: | --- |
| Account A, Nov 20 | 7 | Duplicate 10:00 timestamp; two `VIEW` rows |
| Account A, Nov 21 | 2 | One `summary` without a value |
| Account B, Nov 20 | 1 | Single-row partition |
| Account A, Nov 22 | 0 | Non-existent partition / empty result |
| **Total rows present** | **10** | **3 populated partitions** |

Expected order of partition A / day 20:

| Position | UTC Time | `event_id` (suffix) | Event type |
| ---: | --- | --- | --- |
| 1 | 13:00 | `...0007` | `LOGOUT` |
| 2 | 12:00 | `...0006` | `SHIP` |
| 3 | 11:00 | `...0005` | `VIEW` |
| 4 | 10:00 | `...0004` | `PAY` |
| 5 | 10:00 | `...0003` | `CLICK` |
| 6 | 09:00 | `...0002` | `VIEW` |
| 7 | 08:00 | `...0001` | `LOGIN` |

Because primary keys are fixed, re-running `INSERT` on those exact keys performs an **upsert** rather than adding duplicate rows. However, for tests to stay truly reproducible after DELETE/TTL steps, reset the **dedicated lab table** and reload the baseline data before the next round.

## 4. Before Tracing: Define a Result Verification Matrix

Do not turn on tracing first and wonder afterward what "correct" looks like. Build a **test matrix** beforehand:

| ID | Scenario | Expectation on baseline data |
| --- | --- | --- |
| T01 | Single partition, `LIMIT 3` | `0007, 0006, 0005` in order |
| T02 | Range `[10:00,12:00)` | `0005, 0004, 0003` |
| T03 | Two rows at `10:00` | `0004` before `0003` |
| T04 | Empty day-22 partition | 0 rows, no error |
| T05 | Account B / day 20 | 1 row `0010` |
| T06 | Account A / day 21 selecting `summary` | 2 rows, one `summary = null` |
| T07 | Two partitions days 20–21 + `PER PARTITION LIMIT 2` | 4 rows total, 2 per day |
| T08 | Filter `event_type = 'VIEW'` in partition A / day 20 | 2 rows, typically requires `ALLOW FILTERING` |
| T09 | Keyset after `11:00/0005`, `LIMIT 3` | `0004, 0003, 0002` |
| T10 | Fetch size 2, drain partition A / day 20 | 7 rows overall; potentially multiple protocol pages |

**ID notation note:** `0010` in the table above is shorthand for the UUID ending in digits `0010`; always write the full UUID in CQL.

All expectations here assume the **unmodified baseline table**. Never run the write/delete mutations in Section 10 and then use this table to misdiagnose a query.

## 5. Verifying Key-Based and Clustering-Range SELECTs

### 5.1. T01 — Right Partition, Right Order, and LIMIT

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

**Expected:** `LOGOUT/0007`, `SHIP/0006`, `VIEW/0005`.

Verification checks:

- `WHERE` provides the **complete composite partition key**; the query targets one partition.
- `ORDER BY` uses both clustering columns in the schema-supported direction.
- `LIMIT 3` caps total results at three rows, not three rows per protocol page.
- `SELECT` projects only needed columns, omitting unneeded `summary`.

### 5.2. T02 — Checking Inclusive/Exclusive Time Bounds

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 10:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
ORDER BY occurred_at DESC, event_id DESC;
```

**Expected:** `VIEW/0005` (11:00), `PAY/0004` (10:00), and `CLICK/0003` (10:00).

| Boundary | Sample values | Included? |
| --- | --- | --- |
| Lower bound `>= 10:00` | `10:00/0004` and `10:00/0003` | **Yes** |
| Inside range | `11:00/0005` | **Yes** |
| Upper bound `< 12:00` | `12:00/0006` | **No** |

Using `<= 12:00` would also pull in `SHIP/0006`. Testing with rows **sitting right on the boundaries** catches off-by-one bugs that random datasets miss.

### 5.3. T03 — Same Timestamp, Different Clustering Key

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
ORDER BY occurred_at DESC, event_id DESC;
```

**Expected:** two rows, `PAY/0004` before `CLICK/0003`.

Because both share `occurred_at`, `event_id` enforces deterministic ordering. A keyset-paginating app storing only the timestamp without `event_id` can **skip** one of the two rows. Tracing cannot "catch" this cursor contract bug; only an edge-case dataset catches it.

### 5.4. T04 and T05 — Empty Partition, Single-Row Partition

```sql
-- Partition requested, but no data exists on day 22.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-22';

-- Account B's partition has only one row.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-20'
LIMIT 3;
```

**Expected:** first query returns **0 rows**; second query returns **1 row** (`LOGIN/0010`). `LIMIT 3` is an upper bound, not a requirement to return three rows.

Never treat "0 rows" as "zero cost": Cassandra may still locate replicas and check whether the partition holds any live data. Tracing shows that read journey, though you should not infer exact disk byte counts from a single trace event alone.

### 5.5. T06 — Regular Column Without a Value

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
ORDER BY occurred_at DESC, event_id DESC;
```

There are **2 rows**. `VIEW/0009` at 08:00 has `summary = null` because no value was written for that column; `LOGIN/0008` at 07:00 has `summary = 'New day'`.

What to check in Java:

- `getString("summary")` can return `null`; never call `summary.length()` without a null check.
- The two rows are **not merged or omitted** simply because a regular column lacks a value.
- If using `COUNT(summary)`, its value differs from `COUNT(*)`; do not misinterpret that as missing rows.

## 6. Enabling Tracing in cqlsh and Reading Output

### 6.1. TRACING Is a cqlsh Command

In the **lab**, run:

```sql
USE cassandra_trace_lab;

-- cqlsh display/execution setting, not a SELECT clause.
PAGING OFF;
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;

TRACING OFF;
```

When tracing is on, `cqlsh` displays a **tracing session ID** and the events recorded across nodes participating in the query. Exact event names and order vary by Cassandra version, cache state, and read path. Never write brittle tests asserting "the trace must contain exactly 12 events in this exact order," as execution steps can vary.

`TRACING ON` applies to queries in the **current `cqlsh` session** until disabled; it does not permanently alter schemas, partition keys, or cluster-wide default tracing.

### 6.2. Fields to Inspect in a Trace

Trace output typically lets you inspect:

| Field | How to read it | What NOT to infer |
| --- | --- | --- |
| **Tracing session ID** | Identifier linking events of this execution | Neither a paging state nor a business transaction ID. |
| **Coordinator** | Node receiving and coordinating the query | Not necessarily the only node doing work. |
| **Source/node** of event | Node emitting the execution step | Does not equal logical partition count or all existing replicas. |
| **Elapsed/duration** | Microseconds from query/trace start | Not a workload p99 benchmark. |
| **Activity/message** | Execution/read/messaging step description | Not an exhaustive inventory of every disk block/cell. |
| **Replica messages** | Coordinator-replica exchanges, if any | Does not mean each replica yields duplicate result rows. |

**Conceptual** interpretation example:

```text
Query received at coordinator
  -> identify replicas responsible for token of (A, 2026-11-20)
  -> send/receive read messages per consistency
  -> scan clustering slice, process matching rows
  -> build result page returned to client
```

This is **not verbatim trace output**; real systems may emit more or fewer events depending on version.

### 6.3. Reviewing a Tracing Session Later

If you noted the tracing session UUID printed by `cqlsh`, reopen it with:

```text
SHOW SESSION <tracing-session-uuid>;
```

Replace `<tracing-session-uuid>` with an actual UUID from prior output. This is **template syntax requiring parameter substitution**, not a literal runnable command.

Trace data is stored in the `system_traces` system keyspace. Where read permissions allow, inspect a **real** session ID via:

```sql
-- Syntax illustration only: replace UUID below with an actual tracing ID.
SELECT session_id, request, duration
FROM system_traces.sessions
WHERE session_id = 00000000-0000-0000-0000-000000000000;

SELECT activity, source, source_elapsed
FROM system_traces.events
WHERE session_id = 00000000-0000-0000-0000-000000000000;
```

The all-zero UUID above is a **placeholder** and will not find any experiment trace. Trace writes are asynchronous and subject to a TTL; querying immediately after a request finishes may momentarily show incomplete events. Do not treat that as a `SELECT` query failure.

**Operations:** Tracing generates extra work and writes into `system_traces`, which can affect latency. Enable it **selectively** during investigation; never leave `TRACING ON` across load tests or all production traffic.

## 7. Comparing Traces of Two Read Paths

### 7.1. Key-Based Read of One Partition

```sql
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 10:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000';

TRACING OFF;
```

Here we have the **full partition key** and a clustering slice. Expect **3 logical rows** in the interval. When reading the trace, confirm successful execution and inspect coordinator/replica steps; a trace is **not required** to contain a literal line named "Read 3 rows" for the query to be valid.

### 7.2. Reading a Partition and Filtering a Regular Column

```sql
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;

TRACING OFF;
```

On baseline data, only **2 rows** match `VIEW`: `0005` and `0002`. However, `event_type` is an unindexed **regular column** in the lab schema, so Cassandra may inspect many candidate rows in the partition before discarding non-matches.

Compare:

| Criterion | Clustering range | `ALLOW FILTERING` on `event_type` |
| --- | --- | --- |
| Partition key | One known partition | One known partition |
| How rows are narrowed | By clustering order | Regular-column check after reading candidates |
| Matching rows in lab | 3 | 2 |
| Inferring I/O from output row count | Insufficient | Even more insufficient |
| What to measure at scale | Clustering slice, partition size, tombstones, latency | Candidate set, match rate, tombstones, latency |

**Never compare a single run and declare one query X times faster than another.** On a ten-row lab, timing differences are tiny and dominated by caches, scheduling, and tracing overhead.

### 7.3. A Full-Table SELECT in the Lab

```sql
-- ONLY in a small lab: never run arbitrarily in production.
SELECT account_id, event_day, occurred_at, event_id
FROM events_by_account_day;
```

On baseline data, this returns **10 rows across 3 partitions**. Because the query specifies no partition key, on a large production table it can touch many token ranges and nodes. A tiny lab trace cannot reveal the operational risk when partitions and rows scale by orders of magnitude.

**Never confuse** "10 rows in the lab" with "10 rows in production": a trace is a single sample under specific data and load conditions.

## 8. T07–T09: Multiple Partitions, Filtering, and Cursors

### 8.1. T07 — PER PARTITION LIMIT

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2;
```

On baseline data:

| Partition | Rows contributed |
| --- | --- |
| A / day 20 | `0007`, `0006` |
| A / day 21 | `0009`, `0008` |
| **Total** | **4 rows** |

This targets two candidate partitions. Do not claim the four rows follow a **global chronological timeline**, because clustering order is defined **within each partition**, not across partitions.

Test adding `LIMIT 3` **after** `PER PARTITION LIMIT 2`:

```sql
SELECT event_day, occurred_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2
LIMIT 3;
```

Then the overall query returns at most **3 rows**, with no partition contributing more than **2 rows**. Never guess which day the third row comes from purely from list order in `IN`.

### 8.2. T08 — ALLOW FILTERING Is Not an Index

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

Logical result: two rows `VIEW/0005` and `VIEW/0002`. If a Cassandra version or guardrail rejects a filtering shape, **record the error, version, and schema** rather than blindly tweaking predicates until it runs without understanding the read plan.

To support frequent `event_type` queries at scale, use a **query-driven table** or an **index** suited to your version and selectivity—never treat `ALLOW FILTERING` as a default optimization.

### 8.3. T09 — Keyset Must Use the Full Clustering Key

Suppose page 1 is:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

It ends at `11:00/0005`. To fetch the next three rows:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 11:00:00+0000',
      00000000-0000-4000-8000-000000000005
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Expect `0004, 0003, 0002`. Testing one more page with boundary `(09:00,0002)` yields `0001`.

**Bug to deliberately test:** if page 1 ended at `10:00/0004` and the next query used only `occurred_at < 10:00`, it would **drop `10:00/0003`**. Including duplicate timestamps in the test dataset is specifically designed to catch that defect.

## 9. T10: Verifying Pagination and Per-Fetch Traces

### 9.1. cqlsh with Page Size 2

```sql
PAGING 2;
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC;

TRACING OFF;
PAGING OFF;
```

Target fetch size is two rows/page, while **actual** rows per page are decided by the server at execution time. With seven static rows, exhausting all pages must total **seven**, regardless of how many pages were returned.

When tracing a paginated query:

- Distinguish the trace of the **initial fetch** from subsequent fetches if the protocol/driver generates separate traces.
- Capture each fetch's tracing ID when analyzing multi-page behavior.
- Never equate **page count** with partition count.
- Never assume page size 2 always produces exactly four fetches across every version and execution path.

### 9.2. Paging State Is Not a Snapshot

Suppose you have read the first three rows: `0007,0006,0005`. If a new record with `occurred_at = 14:00` is inserted before the next fetch, it sits **ahead** of the already-traversed cursor. Resuming via paging state offers **no guarantee** of returning to the head to pick up that event.

Conversely, a late-arriving record timestamped `10:30` may appear in the **unread** portion, depending on timing and replica visibility. `DELETE`s or TTL expirations can likewise alter later pages.

A trace shows what occurred during **a single read**, never proving that an entire page chain shares one immutable data snapshot.

### 9.3. Trap When Consuming Only Half a Page

```text
Current protocol page: A, B, C
Paging state S_next: position after C, for next page

API processes A, B but drops C
API returns S_next
Next request uses S_next  --> C is skipped
```

Always **process or buffer every row** in a protocol page before emitting the state for the next fetch. If an API requires strictly N items regardless of protocol page size, use application-level buffering/cursors or keyset pagination.

## 10. Edge Cases with Mutating Data

**Important:** Operations in this section mutate the lab table. Run each scenario **after resetting to the baseline dataset** via Section 3; do not stack them together and expect Section 4's baseline expectations to hold.

### 10.1. Deleting an Unread Row

```sql
-- Test on a dedicated lab table.
DELETE FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000004;
```

Once the delete is observed, querying `occurred_at = 10:00` returns only `CLICK/0003`. The whole partition drops from 7 to **6 live rows**. Trace duration/latency need not drop: deleting creates a tombstone, and Cassandra must still process deletion markers to determine which rows remain live.

To restore the lab to baseline, reset the dedicated lab table and reload all ten rows, or re-insert the row via a valid write. Never infer from "6 live rows remain" that only six physical records exist on disk.

### 10.2. New INSERT at the Head of the Order

```sql
-- Event newer than all baseline events on day 20.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 14:00:00+0000',
    00000000-0000-4000-8000-000000000011,
    'REVIEW', 'Newly arrived'
);
```

A **fresh** `SELECT` from the start puts `REVIEW/0011` first. An active paging sequence already past the newest rows **may never return it** on remaining pages. That is expected if the contract is merely "resume over mutating data"; if the product must never miss newly arriving events, add notifications, refresh triggers, or a dedicated live stream.

### 10.3. Late INSERT Falling Inside the Unread Window

```sql
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:30:00+0000',
    00000000-0000-4000-8000-000000000012,
    'BACKFILL', 'Written later with older timestamp'
);
```

This is a **late-written event with an older clustering key**. It can surface in the remaining portion of an active scan, depending on boundaries/state and replica data. Hence pinning `occurred_at < :asOf` only filters out timestamps after `asOf`—it **does not create a write/commit-time snapshot**.

### 10.4. UPDATE on a Regular Column

```sql
UPDATE events_by_account_day
SET summary = 'Updated'
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

The key of `VIEW/0002` does not change, yet a page read **after the update** can return the new `summary`. Keeping query and paging state identical **does not guarantee** regular-column values match the previous page's point in time.

To "change" a clustering key, you cannot update the key in place like a regular column; you must model deleting the old-key row and inserting the new-key row, which shifts pagination position.

### 10.5. Temporary Rows with TTL

```sql
-- Run on reset lab data; do not treat as a strict wall-clock assertion.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 14:30:00+0000',
    00000000-0000-4000-8000-000000000013,
    'TEMP', 'Will expire'
) USING TTL 120;

SELECT occurred_at, event_id, event_type, TTL(summary)
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 14:30:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000013;
```

While the TTL is active, `TEMP/0013` appears; once values expire and expiration is observed, it ceases to exist as a live row with regular data. Do not test "exactly 120 seconds" via an uncontrolled delayed call; elapsed time, system clocks, and replica states all play a role.

Fewer returned rows does **not** prove tombstones or read work vanish immediately. Compaction, TTLs, and repair follow separate lifecycles; a trace only reflects one point-in-time read signal.

### 10.6. What to Expect vs. What Not to Claim

| Mutation between two pages | Observable behavior | Must NOT claim |
| --- | --- | --- |
| New write ahead of traversed position | New row absent from remaining pages | "Continuing sees every new insert." |
| Late write inside unread region | Next page results can shift | "Paging preserves a T0 snapshot." |
| Unread row deleted | Row absent from subsequent pages | "Next page always holds old IDs." |
| Regular column updated | Newer content can appear | "Same paging state implies same cell versions." |
| TTL expired | Fewer live rows, potentially more tombstone work | "Fewer rows means fewer physical cells read." |
| Unconverged replicas | Separate reads can observe different states | "Consistency level creates cross-page snapshots." |

## 11. Java Driver 4.x: Selective Tracing and Page-by-Page Checks

Examples use **Java 17** and **Apache Cassandra Java Driver 4.x**. Assume an active `CqlSession session` connected to keyspace `cassandra_trace_lab`. **Never enable tracing on all production requests.**

### 11.1. Enabling Tracing for One Prepared Statement

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

// Assumes session is already configured and connected to cassandra_trace_lab.
PreparedStatement prepared = session.prepare("""
    SELECT occurred_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT ?
    """);

UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

BoundStatement request = prepared.bind(accountId, day, 3)
    .setPageSize(2)
    .setTracing(true); // Enable only for controlled diagnostics.

ResultSet result = session.execute(request);
ExecutionInfo executionInfo = result.getExecutionInfo();

// Java Driver 4.17: getTracingId() returns UUID or null.
UUID traceId = executionInfo.getTracingId();
System.out.println("Trace ID: " + traceId);

for (Row row : result) {
    System.out.printf("%s | %s | %s%n",
        row.getInstant("occurred_at"),
        row.getUuid("event_id"),
        row.getString("event_type"));
}
```

On baseline data, the loop reads **3 rows total** due to `LIMIT 3`, despite page size `2`. A synchronous `ResultSet` can **auto-fetch the next page** when iterated to completion; it does not stop after two rows.

**Important API detail:** In Java Driver 4.17, `ExecutionInfo.getTracingId()` returns a nullable `UUID` (**`null`** when tracing is off), not `Optional<UUID>`. Statement setters return a new/updated statement instance, so always capture the **return value** of `setTracing(true)`.

### 11.2. Fetching Detailed Trace Events When Needed

In Java Driver 4.17, `ExecutionInfo` exposes query trace retrieval:

```java
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.QueryTrace;
import com.datastax.oss.driver.api.core.cql.TraceEvent;

ExecutionInfo info = result.getExecutionInfo();
if (info.getTracingId() != null) {
    QueryTrace trace = info.getQueryTrace();
    System.out.printf("Coordinator: %s, duration: %d us%n",
        trace.getCoordinatorAddress(),
        trace.getDurationMicros());

    for (TraceEvent event : trace.getEvents()) {
        System.out.printf("%d us | %s | %s%n",
            event.getSourceElapsedMicros(),
            event.getSource(),
            event.getActivity());
    }
}
```

Calling `getQueryTrace()` issues extra queries against `system_traces`; because traces are persisted **asynchronously**, the driver may retry reads. Never call this on every production request—it adds load, and trace objects may be unavailable or incomplete on errors, permission limits, or TTL expiration. When correlating logs with traces, recording just the **UUID trace ID** is far lighter.

### 11.3. Inspecting Asynchronous Pages Individually

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

BoundStatement paged = prepared.bind(accountId, day, 7)
    .setPageSize(2)
    .setTracing(true);

CompletionStage<AsyncResultSet> firstFuture =
    session.executeAsync(paged);

firstFuture.thenAccept(first -> {
    int actualRows = 0;
    for (Row row : first.currentPage()) {
        actualRows++;
        System.out.println(row.getUuid("event_id"));
    }

    UUID firstTraceId = first.getExecutionInfo().getTracingId();
    System.out.println("First page rows: " + actualRows);
    System.out.println("First trace ID: " + firstTraceId);
    System.out.println("More pages: " + first.hasMorePages());

    // Do not fetch next page here: demonstrates first page only.
});
```

`AsyncResultSet.currentPage()` contains only the **current page**. To fetch the next page, call `fetchNextPage()` when `hasMorePages()` is true; inspect each fetch's trace via that response's `getExecutionInfo()`, rather than assuming all pages share the same ID or execution time.

This example **does not call `join()` or block**; async code processes only the first page. In production, avoid blocking threads unnecessarily and configure sensible timeouts and backpressure.

### 11.4. Asserting Results in Java by Full Primary Key

For an API ordered by `(occurred_at DESC,event_id DESC)`, tests should not merely assert:

```text
result.size() == 3
```

Assert the **exact key values and order**:

```java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.List;
import java.util.UUID;

// A FRESH run dedicated to assertions, with tracing disabled.
ResultSet resultForAssertion = session.execute(
    request.setTracing(false)
);
List<UUID> actualIds = resultForAssertion.all().stream()
    .map(row -> row.getUuid("event_id"))
    .toList();

List<UUID> expectedIds = List.of(
    UUID.fromString("00000000-0000-4000-8000-000000000007"),
    UUID.fromString("00000000-0000-4000-8000-000000000006"),
    UUID.fromString("00000000-0000-4000-8000-000000000005")
);

if (!actualIds.equals(expectedIds)) {
    throw new AssertionError("Unexpected SELECT order or result");
}
```

**Note:** Because `ResultSet` was already iterated in Section `11.1`, the assertion snippet runs a **new query** with tracing off. Never call `all()` on an already-exhausted result set expecting three rows again. In real tests, collect rows from a single run when avoiding duplicate queries.

## 12. Distinguishing Tracing from Benchmarks, Metrics, and Application Logs

### 12.1. Traces Explain One Run; Benchmarks Reveal Distributions

| Tool | What question it answers well | Limitation |
| --- | --- | --- |
| **CQL assertions** | Which rows, order, and columns appear? | Does not measure read amplification. |
| **Query tracing** | Which steps/nodes did this specific request hit? | Overhead and detail vary by version; not a p99 statistic. |
| **Driver metrics** | App-side latency, requests, retries, timeouts, in-flight? | Does not reveal internal storage steps. |
| **Node/JMX/monitoring metrics** | Read latency, tombstones, SSTables, compaction, repair, CPU/disk? | Must be correlated with workload/time. |
| **Controlled load test** | p50/p95/p99/throughput as QPS and data scale? | Requires representative workload and environment. |
| **Application logs** | Which users hit which query shapes, timeouts, or errors? | Must scrub PII and avoid logging sensitive params/tokens. |

One fast trace does not prove a query meets p99 at high QPS. Conversely, a slow p99 alone does not explain root cause without correlating traces, metrics, and key design.

### 12.2. Fair Comparisons

When comparing two query shapes, such as `SELECT *` vs. explicit projection:

1. Use the **same cluster/topology, consistency, partition keys, and dataset**.
2. Hold page size/`LIMIT`, concurrency, and timeout policies constant.
3. Measure both **warm caches** and cold reads if relevant to the business case.
4. Repeat across many iterations and inspect the **distribution**, not a single timing.
5. Record row/byte counts and correctness; smaller payloads do not eliminate all disk reads.
6. Trace only a **small sample** of requests—never across an entire load test.
7. Monitor compaction, repair, tombstones, node saturation, and retries.

When comparing full-partition-key `WHERE` against regular-column filtering, returned row counts may differ. State clearly whether two queries serve **different goals** or the same goal; never compare raw latencies without context.

### 12.3. Experiment Log Template

| Test ID | Query shape | Expected keys | Actual keys | Tracing ID | Latency | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | Full PK + `LIMIT 3` | `0007,0006,0005` | Record on run | Real UUID | Record on measure | Pass/fail |
| T02 | PK + clustering `[10,12)` | `0005,0004,0003` | Record on run | Real UUID | Record on measure | Pass/fail |
| T04 | Empty-day PK | Empty | Record on run | Real UUID | Record on measure | Pass/fail |
| T08 | PK + `VIEW ALLOW FILTERING` | `0005,0002` | Record on run | Real UUID | Record on measure | Pass/fail |

**Never fabricate latencies or tracing IDs.** Cells marked "Record on run" must be filled solely from actual cluster runs. A guide can predict **logical results** from sample data, never exact trace IDs or machine-specific timings/events.

## 13. Differences Between a Single-Node Lab and Multi-Replica Clusters

In a `SimpleStrategy`/RF=1 lab:

- You cannot test two replicas returning divergent versions.
- You cannot verify `LOCAL_QUORUM` guarantees in a multi-replica topology.
- You do not observe full network costs, speculative execution, coordinator overload, or repair behavior under node failures.

When validating production systems:

| Scenario | Suitable environment | What to verify |
| --- | --- | --- |
| Valid CQL, clustering order | Single-node lab | Exact results and edge cases. |
| Paging state, page size, duplicate-timestamp cursors | Single-node lab + Java Driver | Zero dropped/repeated rows when data is static. |
| Impact of writes/deletes/TTLs across pages | Lab with controlled mutations | Never promise snapshots; align with API contract. |
| `LOCAL_ONE` / `LOCAL_QUORUM` reads | Multi-replica cluster | Freshness, latency/availability trade-offs per RF. |
| Unconverged replicas, node down, timeouts/retries | Fault-injection environment | Error behavior and recovery. |
| Wide scans, hot partitions, tombstones | Production-like data/load | p95/p99, read amplification, rate limits. |

In multi-datacenter clusters, distinguish `ONE`/`QUORUM` from `LOCAL_ONE`/`LOCAL_QUORUM` per replication strategy. A trace hitting multiple nodes does not by itself prove consistency is "business-correct"—cross-check consistency level, topology, and write policies.

## 14. Common Mistakes When Verifying Cassandra SELECTs

| Misconception or test practice | Why it is flawed/incomplete | Better approach |
| --- | --- | --- |
| "Query ran without error, so it is right." | Ordering, interval bounds, or duplicate-timestamp rows may be wrong. | Assert full primary keys and edge cases. |
| "Returned 3 rows, so only 3 rows were read." | Tombstones/filtering may scan far more. | Combine traces, metrics, and read-path analysis. |
| "One fast trace proves p99 is fast." | A trace is one sample and adds overhead. | Benchmark many requests under representative load. |
| "Enable `TRACING ON` for all production traffic." | Adds overhead and `system_traces` writes. | Enable on a tiny sample or diagnostic requests only. |
| "Every trace must emit identical activity lines." | Events depend on version, caches, and execution path. | Interpret semantics; never hardcode trace event strings. |
| "No trace events means the query failed." | Traces write asynchronously with TTL/permission limits. | Check tracing ID, retry read appropriately, and verify state. |
| "Trace reports exact physical bytes on disk." | Not a per-block/cell counter in all versions. | Combine with node metrics and benchmarks. |
| "`LIMIT 3` means 3 rows per page." | Caps total query output, not page size. | Separate `LIMIT` from driver `setPageSize`. |
| "`PER PARTITION LIMIT 2` means 2 partitions." | Caps at 2 rows **per partition**. | Count full partition-key candidates from `WHERE`. |
| "`IN` lists provide global ordering." | Clustering order applies inside each partition. | Define merge/cursor logic for global timelines. |
| "Timestamp alone works for keyset pagination." | Same-timestamp rows get skipped or repeated. | Use full clustering tuple `(occurred_at,event_id)`. |
| "An empty page means the query is done." | Continuation state can remain after filtering/tombstones. | Check `hasMorePages()`. |
| "Reuse paging state after changing day/tenant." | State is tied to specific query/bind values. | Keep query identical; protect and scope tokens. |
| "Paging state is a snapshot." | Writes/deletes/TTLs and replicas mutate data. | Define dynamic-data policies or separate snapshots. |
| "RF=1 lab proves quorum behavior." | Lacks multiple replicas to test. | Use a multi-node topology with realistic RF. |
| "`ALLOW FILTERING` was traced, so it's safe." | Permitting a scan does not optimize it. | Bound candidates, design tables/indexes, measure p99. |
| "Read `getTracingId()` as an `Optional`." | Driver 4.17 returns nullable `UUID`. | Check for `null` before using. |
| "Insert/delete test rows then reuse baseline expectations." | Table contents have changed. | Reset the dedicated lab table between experiments. |

## 15. Practice Exercises with Answers

### Exercise 1. Verifying TOP 3

**Task:** Using the baseline table, fetch the three newest events for account A / day 20. List exact IDs, not just row counts.

**Answer:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Returns **`0007, 0006, 0005`** in order. Verify row count, IDs, and descending time order.

### Exercise 2. Upper and Lower Bounds

**Task:** Query events in `[10:00, 12:00)`. Are both 10:00 rows included? Is the 12:00 row included?

**Answer:** Both `PAY/0004` and `CLICK/0003` are included because the lower bound **includes** 10:00. `VIEW/0005` at 11:00 is also included. `SHIP/0006` at 12:00 is excluded because the upper bound is **exclusive**. In `DESC` order, results are `0005, 0004, 0003`.

### Exercise 3. Empty Partition

**Task:** Account A / day 22 has no events yet. How many rows does `SELECT ... LIMIT 10` return? Can we assume I/O cost is zero?

**Answer:** Returns **0 rows**. Never assume zero read cost, since Cassandra may still locate replicas and inspect data. Use metrics/tracing to evaluate cost without requiring traces to report exact physical row numbers.

### Exercise 4. IN and PER PARTITION LIMIT

**Task:** Account A queries days 20 and 21 with `PER PARTITION LIMIT 2` and no overall `LIMIT`. What is the maximum number of rows from baseline data?

**Answer:** **4 rows**: day 20 contributes `0007, 0006` and day 21 contributes `0009, 0008`. Do not assert a global chronological order across the two partitions.

### Exercise 5. Reading Traces Properly

**Task:** A lab trace shows a few events and tiny latency. Can we conclude `ALLOW FILTERING` will hit good p99 on a 100-million-row table?

**Answer:** **No.** A trace reflects one request on tiny data/load. `ALLOW FILTERING` on a regular column may inspect a huge candidate set. Test with representative data, multi-request benchmarks, and checks on fan-out, tombstones, and replica saturation.

### Exercise 6. Duplicate Timestamps in Keyset Paging

**Task:** A page ends at `10:00/0004`. Why does a cursor using only `occurred_at < 10:00` lose data?

**Answer:** `10:00/0003` shares the same timestamp with a smaller `event_id` and must appear on the next page in `DESC` order. A correct cursor uses the tuple `(occurred_at,event_id) < (10:00,0004)`.

### Exercise 7. TTLs and Baseline Tests

**Task:** After inserting a `TEMP` row with a TTL, a `COUNT(*)` test on day 20 sees 8 rows initially and 7 rows a few minutes later. What should you check?

**Answer:** The TTL row may have expired, reducing **live row count**. Do not mistake this for unintended data loss; check write timing, TTL, consistency, and mutating test data. Never run TTL tests concurrently while expecting a static 7-row baseline.

### Exercise 8. Tracing Each Page

**Task:** Java Driver sets `setPageSize(2)` and `LIMIT 7`. Will `for (Row row : resultSet)` print only two rows? Does the initial trace ID automatically cover every subsequent fetch?

**Answer:** **No.** The synchronous loop auto-fetches subsequent pages and prints up to **7 rows**. To trace individual fetches, inspect `ExecutionInfo` on each corresponding response/page rather than assuming one trace ID or timing covers all fetches.

### Exercise 9. Data Mutations and Snapshots

**Task:** A client reads page 1, then the app inserts an event at 14:00 ordered ahead of already-seen rows. Does paging state guarantee returning the new event on later pages?

**Answer:** **No.** State continues from the already-scanned position and does not loop back to rows newly inserted ahead of the cursor. Paging neither snapshots data nor notifies clients of new events; use explicit refreshes or dedicated update feeds.

### Exercise 10. When Are Multiple Replicas Required?

**Task:** A `SimpleStrategy`/RF=1 lab passes all tests. Is that enough to guarantee `LOCAL_QUORUM` in multi-replica production reads identical data across all pages?

**Answer:** **No.** A single-node lab cannot simulate multi-replica replication/consistency. Even on a properly replicated cluster, higher consistency does not create a cross-read snapshot when data mutates.

## 16. Checklist Before Accepting a SELECT Query

1. **Contract:** How many rows, which columns, which key order, and open vs. closed time bounds are required?
2. **Schema:** Are the full partition key, clustering columns, and key directions clear?
3. **Dataset:** Does it cover empty partitions, 1 row, many rows, duplicate timestamps, missing regular columns, multiple partitions, and exact boundary values?
4. **Assertions:** Do tests assert **full primary keys and ordering**, not merely row counts?
5. **Scope:** Does the query target a clear partition/range? If using `IN`, how many partitions? Is `ALLOW FILTERING` present?
6. **Tracing:** Is tracing enabled selectively, trace IDs recorded, and coordinator/replica events interpreted accurately?
7. **Metrics:** Do you distinguish a single trace from p95/p99, benchmarks, tombstones, bytes, and read amplification?
8. **Paging:** Have you verified `LIMIT` vs. page size, `hasMorePages()`, duplicate-timestamp cursors, and full protocol-page consumption?
9. **Mutating data:** Have you tested `INSERT`/`DELETE`/`UPDATE`/TTL across pages without claiming snapshot semantics?
10. **Consistency:** Have you tested on realistic RF/consistency topologies when business guarantees require it?
11. **Java:** Are prepared statements, typed getters, nullable fields, trace APIs, and error handling matched to the driver version?
12. **Security:** Do traces, query logs, and paging tokens avoid leaking tenant IDs, PII, sensitive session IDs, or unauthenticated tokens?
13. **Operability:** Are request budgets, timeouts/retries, monitoring, and schema rollback/evolution plans ready if queries slow down?
14. **Reproducibility:** Was the **dedicated lab table** properly reset before each experiment so prior writes/deletes do not skew results?

**Remember:** In Cassandra, verifying a `SELECT` query requires **two pillars of evidence**: (1) an edge-case dataset verifying **result correctness**, and (2) tracing paired with metrics/benchmarks evaluating **the actual read path and cost**. `TRACING` does not replace business-logic tests, and a passing 10-row test suite never replaces performance testing on a distributed system with replicas, TTLs, and mutating data.

## References

- [Apache Cassandra Documentation — cqlsh: TRACING, PAGING, and SHOW SESSION](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html)
- [Apache Cassandra Documentation — CQL SELECT, WHERE, ORDER BY, LIMIT, PER PARTITION LIMIT, and ALLOW FILTERING](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [DataStax Java Driver 4.17 — Query Tracing](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/tracing/index.html)
- [Java Driver 4.17 — ExecutionInfo API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html)
- [DataStax Java Driver 4.17 — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
