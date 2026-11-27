# Using TOKEN for Controlled Scan Range Splitting in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Explain how `token()` operates on the **entire partition key** and how it relates to the partitioner, token ring, vnodes, and replicas.
2. Write `SELECT ... WHERE token(partition_key) ...` to scan a **token range** instead of scanning an entire table in one large query.
3. Partition the token space into **non-overlapping, gap-free** intervals, handling both boundary endpoints and ring wrap-around correctly.
4. Distinguish **token range count**, **actual partition count**, and **row count**; explain why splitting token values evenly does not guarantee even workload distribution.
5. Design batch scans with **paging, checkpointing, concurrency limits, retries, and idempotency** without treating paging state as an immutable snapshot.
6. Recognize **improper** uses of `TOKEN`, such as querying a single customer/day or paginating chronological history.
7. Connect from the Java Driver, verify coverage on lab data, and establish safety boundaries for distributed operational jobs.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Apache Cassandra is a distributed wide-column database: the partition key governs data placement across the cluster, clustering columns govern row order within each partition, and replication/consistency govern how reads are served. `TOKEN` is useful for **controlled batch exports, audits, or bulk data processing**, not as a substitute for query-driven table design in real-time Java APIs.

## 1. Why Should Full-Table Scans Be Split?

Consider the query:

```sql
-- Illustrates a very broad query; never run arbitrarily in production.
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day;
```

On a table with millions of partitions, this statement may need to:

- Read data spanning **many token ranges** across multiple nodes.
- Coordinate many replicas, subject to consistency levels and cluster health.
- Encounter skewed partition sizes, many SSTables/tombstones, or TTL-expired data.
- Hold open a long-running operation that easily times out, is hard to checkpoint, and risks impacting transactional requests.

Adding `LIMIT 100` only asks for at most 100 result rows; it **does not create a piecewise full-scan plan where the next run can resume the remaining portion**. For a job scanning all data, design **small, trackable, resumable work units**.

One approach is splitting by token:

```text
Entire token space
       |
       +-- Task A: scan range 1   --> pages --> checkpoint
       +-- Task B: scan range 2   --> pages --> checkpoint
       +-- Task C: scan range 3   --> pages --> checkpoint
       +-- ...

Coordinate concurrency, retries, read rate, and sink writes at the application layer.
```

**Note:** Combined across all tasks, this is still a **broad scan**. Splitting provides control and recoverability—it **does not turn a full-table scan into a cheap point lookup**.

## 2. What Is TOKEN and How Does It Differ from Business Keys?

### 2.1. Partition Keys Are Mapped to Tokens

Suppose a table has:

```sql
PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
```

Components:

| Key part | Role | Relationship to token |
| --- | --- | --- |
| `tenant_id` + `event_day` | **Composite partition key** | Both values are serialized together and passed to the partitioner to compute **one token for the partition**. |
| `occurred_at` | First clustering column | Does not participate in computing the partition token. |
| `event_id` | Second clustering column | Does not participate in the token; disambiguates same-timestamp events. |
| `event_type`, `detail` | Regular columns | Do not participate in the token. |

Conceptually:

```text
  tenant_id = A       event_day = 2026-11-20
       |                        |
       +-----------+------------+
                   |
          composite partition key
                   |
            partitioner/hash
                   |
                TOKEN = T
                   |
             token ring / vnode
                   |
       replicas owning partition
                   |
         +---------+---------+
         |         |         |
        row 1     row 2     row 3
       (distinct clustering keys)
```

**Every row in the same partition shares the exact same token.** If a single partition holds one million rows, those rows cannot be split into separate token ranges by looking at `event_id` or `occurred_at`. To split work inside a huge partition, use a separate clustering-range strategy or redesign smaller buckets.

### 2.2. Tokens Do Not Preserve Date, UUID, or Tenant Order

With the standard **Murmur3Partitioner**, a token is a hashed value ordered within the token space. Never assume:

```text
event_day 2026-11-20 -> token 20
event_day 2026-11-21 -> token 21
```

Consecutive days for the same tenant usually produce unrelated numeric tokens. Therefore:

- `WHERE token(tenant_id, event_day) >= X` does **not** mean "read days from X onward."
- Scanning by token splits **storage distribution**, not business date intervals.
- For daily/chronological logs, use the full partition key and clustering ranges; for batch scanning across many partitions, token ranges can fit.

### 2.3. The Partitioner Determines the Token Type

Every cluster uses a configured partitioner. Examples:

| Partitioner | Typical token type | Operational implication |
| --- | --- | --- |
| `Murmur3Partitioner` | 64-bit signed integer (CQL `bigint`) | Standard; the half-domain splitting examples below apply here. |
| `RandomPartitioner` | Different token type involving arbitrary-precision integers | Do not mechanically reuse `Long.MIN_VALUE`/`0`/`Long.MAX_VALUE` bounds. |
| Other partitioners | Configuration-dependent | Must inspect actual metadata/token ranges to build boundaries. |

Check the cluster's partitioner and token map before designing a scan job. In environments permitting system-table reads, inspect metadata:

```sql
-- Check on a cluster/lab with permission to read system tables.
SELECT partitioner FROM system.local;
```

The 64-bit bounds in the hands-on section **apply only to clusters using `Murmur3Partitioner`**. Never change the partitioner or partition key serialization mid-job and expect old checkpoints to remain valid.

## 3. CQL Lab: Multiple Rows Within the Same Partition

### 3.1. Creating the Table

```sql
-- SimpleStrategy and RF=1 are for a single-node lab only.
CREATE KEYSPACE IF NOT EXISTS cassandra_token_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_token_lab;

CREATE TABLE IF NOT EXISTS events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    detail text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

### 3.2. Inserting Eight Events Across Four Partitions

```sql
-- Partition (tenant A, Nov 20): three rows.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed product'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Added to cart'
);

-- Partition (tenant A, Nov 21): two rows.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'LOGIN', 'Logged in next day'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGOUT', 'Logged out'
);

-- Partition (tenant B, Nov 20): one row.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGIN', 'Account B'
);

-- Partition (tenant C, Nov 19): two rows.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2026-11-19', '2026-11-19 18:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'VIEW', 'Account C'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2026-11-19', '2026-11-19 18:30:00+0000',
    00000000-0000-4000-8000-000000000008,
    'CLICK', 'Account C'
);
```

From the sample data:

| Partition key | Rows |
| --- | ---: |
| (A, 2026-11-20) | 3 |
| (A, 2026-11-21) | 2 |
| (B, 2026-11-20) | 1 |
| (C, 2026-11-19) | 2 |
| **Total** | **8 rows across 4 partitions** |

Because `INSERT` uses fixed keys, re-running on the same table performs upserts without creating duplicate primary keys. Expected row counts hold only on a clean table without concurrent writes or deletes.

## 4. Inspecting Each Partition's Token

In a table with a composite partition key, call `token()` with the **exact partition key components in exact schema order**:

```sql
SELECT tenant_id,
       event_day,
       token(tenant_id, event_day) AS partition_token,
       occurred_at,
       event_id,
       event_type
FROM events_by_tenant_day;
```

In a tiny lab, this query lets you inspect tokens. **Never run a full-table scan like this just to list tokens in a production cluster with many partitions.**

What to verify:

1. All three events for `(A, 2026-11-20)` share the **exact same `partition_token`**.
2. Both events for `(A, 2026-11-21)` also share the **same token**, not necessarily near day 20's token.
3. The token does not encode `occurred_at`, `event_id`, or event type.
4. Concrete token values depend on the partitioner and serialization; **never guess tokens from dates or UUIDs**.

Do not confuse the syntax:

```sql
-- Valid: complete composite partition key.
token(tenant_id, event_day)

-- Invalid for the table's token path:
-- missing event_day from the composite partition key.
token(tenant_id)

-- Wrong purpose: this is a clustering column, not a partition key.
token(occurred_at)
```

The three lines above merely illustrate expressions, **not a standalone executable CQL query**. To look up a known partition, write `tenant_id = ... AND event_day = ...`; do not switch to a token range just because `token()` exists.

## 5. Scanning a TOKEN Range with CQL

### 5.1. Conditions on token() Differ from Direct Partition Key Conditions

A range predicate on a partition key component:

```sql
-- Not a valid date-range query with a composite partition key.
SELECT tenant_id, event_day, event_id
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20';
```

is not equivalent to a predicate on `token()`:

```sql
-- CQL token range example: only use after confirming Murmur3Partitioner.
SELECT tenant_id, event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;
```

The second query scans partitions whose **tokens fall in the negative half of the signed integer range**, not "tenants or days smaller than a business threshold." With the lab data, you cannot tell which partitions fall into this range without computing their actual tokens.

### 5.2. Splitting the Murmur3 Domain into Two Non-Overlapping Ranges

For Murmur3 over the 64-bit signed integer domain, you can split as:

```text
Minimum value                0                     Maximum value
-9223372036854775808        |                     9223372036854775807
           [----------------) [------------------------------]
             Range A                    Range B

Range A: token >= MIN AND token < 0
Range B: token >= 0
```

Corresponding CQL queries:

```sql
-- Range A: from MIN (inclusive) up to 0 (exclusive).
SELECT tenant_id, event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;

-- Range B: from 0 (inclusive) through the end of the signed range.
SELECT tenant_id, event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0;
```

Properties of **these two custom-defined numeric intervals**:

- Negative tokens belong **strictly to Range A**.
- Token 0 belongs **strictly to Range B**.
- Positive tokens belong **strictly to Range B**.
- No gap at 0 and no overlap between the two ranges.

Here **we do not use an upper bound larger than `Long.MAX_VALUE`** because such a value cannot be represented as a normal `bigint` token. The final range uses `>= 0` with no upper bound.

**Important:** Cassandra has special rules at the minimum token and ring wrap-around; when using the driver's `TokenRange` metadata, its boundary convention **differs** from the `[start, end)` intervals we constructed here. Section 7 explains how to avoid mixing conventions.

### 5.3. Checking Coverage on Lab Data

Since there are 8 rows across 4 partitions in total, the combined output of **Range A plus Range B** must equal **8 rows** when there are no concurrent writes/deletes and the cluster uses the assumed partitioner.

You can count rows in each range in the small lab:

```sql
SELECT count(*) AS rows_in_negative_range
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;

SELECT count(*) AS rows_in_nonnegative_range
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0;
```

What to verify:

```text
rows_in_negative_range + rows_in_nonnegative_range = 8
```

**There is no fixed split per half** in this lesson: counts depend on the hashed tokens of the composite partition keys, and two halves are not guaranteed to hold equal partition counts on a tiny sample. `COUNT(*)` over a token range **is still a data scan**, so avoid running count queries as routine checks in large production clusters.

## 6. Splitting into Many Token Ranges: Gap-Free, Overlap-Free

### 6.1. Self-Managed Half-Open Interval Rule

Suppose an application constructs strictly increasing token boundaries:

```text
B0 < B1 < B2 < ... < Bn
```

Then you can form the intervals:

```text
[B0, B1)
[B1, B2)
...
[B(n-1), Bn)
```

Every interval uses `token >= lower AND token < upper`. A point equal to boundary `Bi` belongs to the **interval starting at Bi**, not the preceding one. If `B0` is the domain minimum and you want to scan the entire domain, the final interval must cover through the domain maximum; with 64-bit signed integers, use a **lower-bound-only final range** to cover the remainder.

Example splitting Murmur3 into three numeric ranges:

```text
Range 1: [Long.MIN_VALUE, -1000)
Range 2: [-1000, 1000)
Range 3: [1000, Long.MAX_VALUE]
```

CQL:

```sql
-- Range 1
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < -1000;

-- Range 2
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -1000
  AND token(tenant_id, event_day) < 1000;

-- Range 3 (do not use a value greater than Long.MAX_VALUE).
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 1000;
```

This **illustrates non-overlapping boundaries**, not optimal load balancing: the three ranges have vastly different token widths and are unsuited for distributing work evenly.

### 6.2. Avoiding Overflow When Computing Boundaries

When splitting the 64-bit space into `N` parts, never compute the midpoint with:

```java
// DO NOT use: full domain width overflows long.
long width = Long.MAX_VALUE - Long.MIN_VALUE;
long midpoint = Long.MIN_VALUE + width / 2; // produces wrong result
```

Use `BigInteger` or the driver's token range API to calculate boundaries. For covering the full signed domain, represent the **exclusive** upper endpoint internally as `2^63`, then emit the final range in CQL **without an upper bound**. Ensure boundaries are distinct, produce no empty ranges, and never cast `2^63` directly to `long` where it would overflow.

### 6.3. Do Not Try to Split One Partition by Token

For instance, partition `(A, 2026-11-20)` has three rows. If that partition's token falls in Range A, **all three rows** fall in Range A. Increasing the number of token ranges from 2 to 20 **never** splits those three rows across workers.

When a single partition is too large and slows down a task:

- Scan **clustering ranges** inside that specific partition via a secondary strategy if the schema allows.
- Or design smaller buckets in the next iteration of the data model.
- Never assume token scanning solves hot partitions merely by adding range workers.

## 7. Java Driver TokenRange Conventions and the Token Ring

### 7.1. TokenRange in Metadata Is Typically (start, end]

The token ring is **circular**. When reading ranges from Java Driver 4.x token metadata, `TokenRange` represents the interval:

```text
(start, end]
```

meaning **start-exclusive, end-inclusive**. This is the convention of ring metadata and ownership ranges, differing from the `[start, end)` intervals we constructed manually in Sections 5–6.

Example:

```text
Metadata range A: (10, 20]  => token > 10 and token <= 20
Metadata range B: (20, 30]  => token > 20 and token <= 30

Token = 20 belongs only to A, not B.
```

If you use `TokenRange` directly from the driver, keep **one consistent boundary convention** throughout the job:

```sql
-- CQL representing a non-wrapping TokenRange: (start, end].
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) > 10
  AND token(tenant_id, event_day) <= 20;
```

Never convert metadata `(10, 20]` into `>= 10 AND < 20`; doing so misassigns boundary tokens when combining ranges.

### 7.2. Ring Wrap-Around and unwrap()

On the ring, a range can **wrap past the end of the token domain**. Conceptually:

```text
Ring: ... 80 -> 90 -> MAX -> MIN -> ... -> -50 -> -40 ...

TokenRange (80, -40] wraps around the ring boundary.
```

**Standard CQL token range predicates do not automatically handle wrap-around intervals as linear numeric ranges.** With Java Driver `TokenRange`, call `unwrap()` to split into one or two non-wrapping ranges before building CQL with proper bounds. When handling minimum tokens, full-ring ranges, and empty ranges, rely on the token range API rather than inferring from positive/negative signs on bounds.

In Java Driver 4.x:

- `TokenMap.getTokenRanges()` retrieves the ranges describing the ring.
- `TokenRange.unwrap()` splits a wrap-around range.
- `TokenRange.splitEvenly(k)` splits by **token-space width**, **not** by partition count or actual byte volume.
- Refresh `TokenMap` and topology/schema metadata from the active session as needed when topology changes.

**Important:** `getTokenRanges(keyspace, replica)` reports ranges replicated on a specific node. If a job scans the entire dataset **once**, do not merge per-node replica range lists into a non-overlapping task list: due to replication, they overlap. Build a single **disjoint** set of token intervals covering the logical token space and assign those to workers.

### 7.3. Equal Token Width Does Not Mean Equal Data Volume

Token hashing distributes partition keys, yet individual partitions vary wildly in size. Example:

| Range | Partitions | Total rows | Note |
| --- | ---: | ---: | --- |
| R1 | 10,000 | 100,000 | Many small partitions. |
| R2 | 9,000 | 900,000 | A few huge partitions. |
| R3 | 11,000 | 120,000 | Many partitions, few rows. |

Three ranges can have equal token width yet vastly different scan times. For load balancing, measure:

- Actual partition counts and partition sizes.
- Bytes read/processed, SSTables, and tombstones scanned.
- Per-range duration, throughput, and replica/coordinator load.
- Long-running tail ranges; consider subdividing them further unless a single giant partition dominates.

Never assume "100 concurrent ranges = 100x faster" on a cluster: excessive concurrency can saturate I/O, grow compaction backlogs, and trigger timeouts and tail-latency spikes for foreground traffic.

## 8. Comparing TOKEN Scans with Key-Based WHERE Queries

| Need | Suitable query pattern | Why |
| --- | --- | --- |
| History for tenant A on day 20 | `tenant_id = A AND event_day = D` | Point-partition read targeting one partition. |
| A time window within that day | Full partition key + range on `occurred_at` | Selects a slice in clustering order. |
| Three known days for a tenant | `event_day IN (D1,D2,D3)` after `tenant_id = A` | Reads a specific list of partitions. |
| Controlled full-table batch export | `token(tenant_id,event_day)` across ranges | Splits bulk work across partitions/token ranges. |
| Paginating newest events for a tenant | Clustering order + paging state/keyset cursor | Tokens do not sort events chronologically. |
| Finding all `VIEW` events cluster-wide | Query-driven table / index / summary | Token ranges still scan broadly and filter if no access path exists. |

A token-range query is not a "partition-key point lookup." It can span vast numbers of partitions, making frequent execution from synchronous HTTP handlers risky unless carefully measured.

## 9. LIMIT, Page Size, and Checkpoints Do Not Substitute for One Another

### 9.1. LIMIT Does Not Complete a Scan

```sql
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0
LIMIT 2;
```

This returns **at most two rows**; it does not mean "finished scanning non-negative token partitions." In a batch export, if a task must process the **entire range**, iterate through all pages or use a proper resume/checkpoint mechanism—never treat `LIMIT 2` as an automatic chunk you can advance via `OFFSET`.

### 9.2. Page Size and Paging State

Driver `setPageSize(n)` requests fetching in pages of a target size, while **paging state** represents the continuation cursor of the *exact same query*.

| Concept | Purpose | Does not guarantee |
| --- | --- | --- |
| **Token range** | Unit dividing partition space among tasks. | Exact cap on rows or bytes per task. |
| **Page size** | Throttles rows returned per fetch round trip. | Total row limit or one partition per page. |
| **Paging state** | Resumes read position of the exact same CQL and bind values. | Immutable snapshot or reuse across modified queries. |
| **Application checkpoint** | Persists task/range/page progress. | Exactly-once processing if the sink is not idempotent. |

Never reuse a paging state on a query with different token bounds, or edit it to guess a new position. Likewise, `token(pk)` **contains no clustering offset**: if a partition has many rows, checkpointing only the last token can skip remaining unprocessed rows in that partition upon resume.

### 9.3. Task Recovery After Failure

A straightforward, verifiable strategy:

1. Record task `range_id`, lower/upper bounds, status, and config version.
2. Execute the query **for that exact range** with a bounded page size.
3. Process each record with a sink that is **idempotent** on the **full primary key** (and version/event ID when applicable).
4. Checkpoint continuation state only **after confirming the sink persisted** the completed page's records.
5. On error/timeout or untrusted paging state, **re-scan the range** from the beginning and deduplicate at the sink.
6. Mark the range complete only after exhausting all pages per the protocol.

Store bounds and paging state with integrity checks, protect any client-exposed tokens, and bind them to the specific query, keyspace, table, and parameters. Never assume a checkpoint holding only "last token" suffices when a job processes individual rows inside a partition.

**At-least-once vs. exactly-once:** The most reliable operational design is **at-least-once processing** on retries backed by idempotency/deduplication at the sink. Do not claim exactly-once semantics solely from driver paging state.

### 9.4. Data Changing During a Scan

Token ranges and paging **do not provide a table-wide snapshot**. While a job runs:

- New writes into an already-scanned range may be missed.
- Deletes/TTLs may remove records before their range is scanned.
- Unconverged replicas may yield varying results depending on consistency level.
- Topology changes alter placement/replica ownership, though partition key hashing remains fixed if the partitioner does not change.

If you need a "point-in-time" export, use a dedicated mechanism: snapshots/backups, locked time windows, CDC, or reconciliation—never assume token-range `SELECT` provides cluster-wide transactional snapshots.

## 10. Strategy for Running Safe Batch Scans

### 10.1. Orchestrating by Range Instead of Unbounded Single Requests

An execution schedule can be structured as:

```text
Planner
  |
  +--> R01 [lower, upper) --> worker #1 --> sink
  +--> R02 [lower, upper) --> worker #2 --> sink
  +--> R03 [lower, upper) --> pending
  +--> ...
  |
  +--> checkpoint store: status, attempt, page, offset, error
  |
  +--> limiter: max K active ranges, max Q requests/sec
```

Operational recommendations:

- **Bound concurrency:** start small and scale based on measured latency and resource usage.
- **Rate limiting/throttling:** protect the cluster so batch jobs do not starve foreground traffic.
- **Backoff:** on timeouts/`Unavailable`, use bounded retries with jitter; avoid retry storms.
- **Scope-aligned timeouts:** if one range runs too long, narrow the range or inspect giant partitions instead of raising timeouts indefinitely.
- **Skew handling:** watch lagging ranges and evaluate whether subdividing remaining subranges is safe.
- **Scheduling:** run off-peak when business rules allow, and split large jobs into phases.

### 10.2. Which Metrics to Monitor?

| Metric group | Purpose |
| --- | --- |
| Range progress: `scheduled/running/completed/failed` | Tracks coverage and retry state. |
| Rows and bytes processed per range/page | Identifies skewed ranges and large partitions. |
| p50/p95/p99 latency, throughput | Evaluates batch impact on normal read traffic. |
| Read timeouts, `Unavailable`, retries, speculative executions | Surfaces overload and replica health. |
| Tombstone warnings, SSTable read amplification, compaction backlog | Explains why low-output ranges are still slow. |
| Selective tracing, node CPU/disk/network | Pinpoints real bottlenecks beyond token width guesses. |

Token-range scanning is a broad-read workload. Higher replication factors do not increase logical partition counts, but consistency and replica coordination affect latency. Similarly, repair and compaction compete for I/O with batch scans; schedule and monitor them together.

### 10.3. Choosing Ranges from Token Ring Metadata Instead of Arbitrary Splits

When a cluster has vnodes and multiple nodes, a production-grade planner:

1. Fetches token map/topology via the driver, checking the partitioner and ring token ranges.
2. Selects a **disjoint set of ranges** covering the entire logical token space.
3. Uses `splitEvenly` or historical metrics to balance work, **never** confusing equal token split with equal byte volume.
4. Unwraps wrap-around intervals and emits CQL with matching bounds and token types.
5. Executes under a concurrency cap and checkpoints every range.

Never take every replica range from every node and run each as an independent task—replication causes massive redundant scanning. Token metadata identifies owners/replicas, while the scanner needs **one unique coverage plan** over logical data.

## 11. Java Driver: Scanning the Two Murmur3 Halves

The example below uses **Apache Cassandra Java Driver 4.x** and Java 15+ (text blocks). It assumes an active `CqlSession session` connected to keyspace `cassandra_token_lab` on a cluster using **`Murmur3Partitioner`**. The code illustrates a **synchronous sequential scan** suitable for labs; production jobs need the scheduler, checkpoints, and idempotent sink from Sections 9–10.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

// Assumes session is already initialized and connected to the right keyspace.
PreparedStatement negativeHalf = session.prepare("""
    SELECT tenant_id, event_day, occurred_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE token(tenant_id, event_day) >= ?
      AND token(tenant_id, event_day) < ?
    """);

PreparedStatement nonnegativeHalf = session.prepare("""
    SELECT tenant_id, event_day, occurred_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE token(tenant_id, event_day) >= ?
    """);

BoundStatement first = negativeHalf.bind(Long.MIN_VALUE, 0L)
    .setPageSize(128);
BoundStatement second = nonnegativeHalf.bind(0L)
    .setPageSize(128);

long scannedRows = 0;
for (BoundStatement task : new BoundStatement[] { first, second }) {
    ResultSet result = session.execute(task);
    for (Row row : result) {
        UUID tenantId = row.getUuid("tenant_id");
        LocalDate day = row.getLocalDate("event_day");
        UUID eventId = row.getUuid("event_id");

        // Lab: print; production: replace with an idempotent sink,
        // checkpoint management, and backpressure.
        System.out.printf("%s %s %s%n", tenantId, day, eventId);
        scannedRows++;
    }
}
System.out.println("Rows scanned: " + scannedRows); // 8 on lab data
```

**What this code does:**

- `Long.MIN_VALUE` and `0L` are `bigint` bind values for Murmur3 tokens; **do not** reuse this code on another partitioner.
- The first query selects `[MIN, 0)`, and the second selects `[0, MAX]`. The two queries cover disjoint token sets under this partitioner.
- `setPageSize(128)` only throttles fetching; iterating over `ResultSet` fetches subsequent pages until exhausted. It does **not** cap the batch at 128 rows.
- `scannedRows = 8` is expected on the static lab dataset, not guaranteed in production or under concurrent writes/deletes.
- In production code, never print millions of rows to the console or buffer an entire `ResultSet` in one giant collection; manage timeouts, retries, and paging explicitly.

### 11.1. Using TokenMap Instead of Hardcoding Two Halves

In driver 4.x, you can inspect ring metadata as follows:

```java
import com.datastax.oss.driver.api.core.metadata.TokenMap;
import com.datastax.oss.driver.api.core.metadata.token.TokenRange;
import java.util.Optional;

Optional<TokenMap> maybeTokenMap = session.getMetadata().getTokenMap();
if (maybeTokenMap.isEmpty()) {
    throw new IllegalStateException("Token metadata not ready");
}

TokenMap tokenMap = maybeTokenMap.get();
for (TokenRange ringRange : tokenMap.getTokenRanges()) {
    for (TokenRange linear : ringRange.unwrap()) {
        // Each linear range uses TokenRange's (start, end] convention.
        // Build CQL with token(pk) > start AND token(pk) <= end,
        // bind the partitioner's token type, and handle MIN/full-ring.
        // Enqueue tasks into a scheduler instead of unbounded concurrent scans.
        System.out.println(linear);
    }
}
```

This is a **metadata inspection pattern**, not a complete scanner: you still must ensure disjoint intervals, handle full-ring/minimum edge cases, bound parallelism, maintain checkpoints, and match query bounds to the actual token type. API names may vary slightly across driver versions; verify against your driver's documentation.

## 12. Common Mistakes When Using TOKEN

| Misconception or query | Issue | How to handle it |
| --- | --- | --- |
| "`TOKEN` returns data in ascending date order." | Tokens hash the partition key and do not preserve business date order. | Use clustering columns/date buckets per read pattern. |
| `token(tenant_id)` on a table keyed by `(tenant_id,event_day)` | Missing component of the composite partition key. | Use `token(tenant_id,event_day)`. |
| Splitting one huge partition into many token ranges | Every row in a partition shares the exact same token. | Split by clustering ranges or redesign smaller buckets. |
| Using `>= start AND <= end` on two adjacent ranges | A token on the shared boundary matches both ranges. | Use consistent half-open intervals or driver `(start,end]`. |
| Using `> start AND < end` on two adjacent ranges | Boundary tokens can be missed entirely. | Explicitly make one side closed and the other open. |
| Mixing `TokenRange (start,end]` with CQL `[start,end)` | Mismatched bounds cause duplicates or gaps. | Stick to one boundary convention per scan plan. |
| Writing a wrap-around range as a plain linear interval | CQL does not unroll ring wrap-arounds automatically. | Call `unwrap()` or split into linear intervals. |
| `splitEvenly(16)` creates 16 tasks with equal row counts | Splits token-space width only, not data volume. | Monitor skew/bytes and adjust scheduling. |
| `LIMIT 100` means all 100 rows of a range are scanned and done | It caps output rows while leaving the rest of the range unread. | Exhaust paging or resume properly. |
| Checkpoint stores only the last token | Loses track of clustering rows inside a multi-row partition. | Store matching paging state or re-scan the range into an idempotent sink. |
| Running all replica ranges of every node as separate tasks | Replica ranges overlap due to replication. | Build a single disjoint coverage plan over the logical ring. |
| Token scans provide a cluster-wide consistent snapshot | Writes/deletes/TTLs/repairs can change data mid-scan. | Use snapshots, CDC, or reconciliation mechanisms. |

## 13. Practice Exercises and Answers

### Exercise 1. Counting Partitions and Rows by Token

**Question:** The lab table has 4 partitions and 8 rows. If one partition contains three rows and its token falls in Range A, how many of its rows fall in Range A? Could any fall in Range B?

**Answer:** **All three rows** fall in Range A because the token is computed from the shared full partition key; if the two ranges are disjoint, that partition **cannot** have any rows in Range B. Tokens do not depend on clustering columns.

### Exercise 2. Finding a Boundary Bug

**Question:** A job defines two ranges:

```text
R1: token >= -1000 AND token <= 0
R2: token >= 0 AND token <= 1000
```

What is wrong?

**Answer:** Token `0` falls in **both** ranges. Fix it as:

```text
R1: token >= -1000 AND token < 0
R2: token >= 0 AND token <= 1000
```

To scan the **entire numeric domain**, you must also cover the intervals outside `[-1000,1000]`; fixing the overlap alone does not create full-ring coverage.

### Exercise 3. Two Token Halves

**Question:** Write two queries splitting the entire signed 64-bit Murmur3 domain into negative and non-negative halves.

**Answer:**

```sql
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;

SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0;
```

With static data, the sum of rows from both queries equals the entire lab table's row count (**8**).

### Exercise 4. Why Equal Token Splits Still Skew Duration

**Question:** Two token ranges have equal token width. Range A holds 10,000 small partitions; Range B holds one partition with 5 million rows. Why won't A and B necessarily finish at the same time?

**Answer:** Scan cost depends on row/byte counts, tombstones, SSTables, replicas, and I/O. `splitEvenly` balances **token-space width**, not actual data volume. A giant partition still resides inside **one range** and cannot be split by token.

### Exercise 5. Safer Checkpointing

**Question:** A worker sends 500 rows to the sink and times out. Why can saving only "last token" and resuming with `token(pk) > lastToken` lose data?

**Answer:** One token represents an **entire partition**, which may still have unsent clustering rows. Skipping that token drops the rest of the partition. Instead, persist the query's paging state after sink confirmation, or **re-scan the entire range** into an idempotent sink so retries never drop rows.

### Exercise 6. Can Token Ranges Replace Business Queries?

**Question:** An endpoint needs "the 20 most recent events for tenant A on day 20." Should it use `WHERE token(tenant_id,event_day) >= X LIMIT 20`?

**Answer:** **No.** Token ranges neither isolate a specific tenant/day nor preserve chronological order, and they can touch many partitions. Use `WHERE tenant_id = A AND event_day = D ORDER BY occurred_at DESC LIMIT 20` with a compatible clustering order, or a read table designed for that requirement.

## 14. Checklist Before Deploying a Token-Range Scan

1. **Right use case:** Is this a multi-partition batch scan rather than a single-partition or timeline API?
2. **Right key:** Does `token()` pass the **entire partition key** in exact column order?
3. **Right partitioner:** Have you confirmed Murmur3 vs. another partitioner and matched token types/bounds?
4. **Coverage:** Do ranges cover the entire target space with no overlaps, no dropped boundaries, and proper wrap-around/min-token handling?
5. **Skew:** Do you understand that a single partition always stays in one token range and equal token width does not mean equal bytes?
6. **Load control:** Are concurrency caps, throttling, backoff, timeouts, metrics, and giant-range handling in place?
7. **Paging/checkpointing:** Do you distinguish `LIMIT`, page size, paging state, and checkpoints? Is the sink idempotent on retries?
8. **Mutable data:** Do you have policies for concurrent writes/deletes/TTLs during scans, freshness expectations, and reconciliation/replay?
9. **Replication/consistency:** Is read pressure on coordinators/replicas bounded, and are duplicate replica-range scans avoided?
10. **Java application:** Are token types bound properly, driver token map APIs used accurately, authorization enforced, and batch scans isolated from hot APIs?

**Remember:** `TOKEN` splits a scan job **by partition placement on the token ring**. Job correctness depends on **gap-free, overlap-free coverage** and proper resumption; performance depends on **actual data volume, concurrency, and replica health**. Token ranges do not replace partition keys in business queries, do not subdivide large partitions, and do not create a cluster-wide consistent snapshot.

## References

- [Apache Cassandra Documentation — CQL Data Manipulation: WHERE with TOKEN](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Changes: TOKEN in Partition Key Conditions](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/changes.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [DataStax Java Driver 4.x — Token Metadata and TokenMap](https://docs.datastax.com/en/developer/java-driver/4.2/manual/core/metadata/token/index.html)
- [DataStax Java Driver 4.x — TokenRange API: Range Boundaries and unwrap](https://docs.datastax.com/en/drivers/java/4.6/com/datastax/oss/driver/api/core/metadata/token/TokenRange.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
