# Choosing a Partition Key from the Primary Access Path

## Lesson Objectives

In Apache Cassandra, the **partition key** determines which logical partition a row belongs to, which in turn determines how Cassandra routes data to replicas in the cluster. A well-chosen partition key lets the application read a single or a small known set of partitions, whereas a poor choice can leave queries missing the key, fan out across too many partitions, or concentrate load on an oversized partition.

This lesson belongs to the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It focuses on moving from the application's **primary access path** to choosing a partition key while simultaneously considering CQL correctness, data distribution, hotness, replication, consistency boundaries, and how a Java service passes keys during queries.

After this lesson, you will be able to:

- Extract the **always-present** input fields of the most critical read path and turn them into candidate partition keys.
- Distinguish **single partition keys**, **composite partition keys**, and **clustering keys**, along with their roles in `PRIMARY KEY`.
- Estimate row counts, storage size, throughput, and partition access counts when choosing a partition key or time bucket.
- Spot large partitions, hot partitions, low-cardinality keys, and cases requiring bucketing/sharding or a table dedicated to another query.
- Write tables and CQL statements with clear access paths; explain the limits of queries using other keys and how to validate assumptions with real data.

## 1. Why Must the Partition Key Start from Queries?

A relational database typically permits arbitrary `WHERE`, `JOIN`, and `ORDER BY` clauses across normalized tables, leveraging indexes and a query optimizer. Cassandra uses a **distributed wide-column** model: each partition is identified by its partition key value, and rows within a partition are sorted by clustering columns. Cassandra favors operations where the application **knows in advance which partition(s) to read**.

For example:

> "A customer views the 50 most recent transactions on a given day for their own account, ordered by time descending."

From this statement, we can extract:

- **Target entity:** a known tenant and a known account.
- **Scope:** a specific day.
- **Order within scope:** occurrence time descending.
- **Limit:** at most 50 transactions for this view.

The candidate partition key is `(tenant_id, account_id, day_bucket)`. `occurred_at` and `event_id` can serve as clustering columns. This choice comes from **the values the application always passes on reads**, rather than merely from entity names or payload attributes.

If the same table is later asked to "find a transaction by `event_id` alone" or "list all failed transactions across a tenant," those two new queries do not naturally know the account/day partition. They require a separate read path or a redesign grounded in actual requirements.

## 2. What Does the Partition Key Actually Determine?

### 2.1. A Partition Is a Logical Routing Unit

Cassandra applies the partitioner to the partition key to compute a **token**. Identical partition key values map to the same token and the same replica set under the current placement/replication configuration. Rows with different clustering keys but the same partition key still belong to **one logical partition**.

Cassandra's `PRIMARY KEY` consists of two parts with distinct responsibilities:

| Component | Determines | Typical Query Usage |
| --- | --- | --- |
| **Partition key** | Partition and token used to route to replicas | Equality predicates on partition key components |
| **Clustering column** | Row order and uniqueness inside the partition | Range/order conditions on eligible clustering keys |
| **Regular column** | Data values stored with the row | Display; not inherently an efficient lookup path |

CQL syntax examples:

```sql
-- Single partition key is account_id; occurred_at is a clustering column.
PRIMARY KEY (account_id, occurred_at)

-- Composite partition key consists of tenant_id, account_id, day_bucket.
-- occurred_at and event_id are clustering columns.
PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)
```

In the second example, **the three components inside the nested parentheses** form one composite partition key. Cassandra uses the entire combination of values to compute the token. They are **not** three independent indexes; thus a query providing only `tenant_id = ?` cannot naturally locate a single partition.

### 2.2. Partition Key Defines Work Scope; Clustering Defines the Internal Read Path

```text
Java Application
  Q: tenant=T1, account=A1, day=2026-11-21
            |
            v
Partition key = (T1, A1, 2026-11-21)
            |
            v
Token and replicas for that partition
            |
            v
Rows ordered by clustering:
  (10:12:31, e8) -> ...
  (10:10:02, e7) -> ...
  (09:58:14, e6) -> ...
            |
            v
Return at most 50 rows in requested order
```

The partitioner distributes **partitions** around the token ring; it does not automatically split one huge partition into many independent small partitions. If a single `account_id` generates disproportionate write volume, other key values may distribute evenly across the cluster while **that account's partition remains hot**.

Replication keeps copies of data on replicas and provides fault tolerance per deployment policy. It does **not** change the mandatory access path of a CQL query, nor does it turn one hot partition into countless independent partitions.

## 3. Identifying the Primary Access Path

The **primary access path** is the read pattern with the greatest impact on system goals—whether due to high call volume, strict latency requirements, business criticality, or lack of alternatives. It is not necessarily the first query written or strictly the query with the highest percentage of calls.

Before designing tables, build a catalog of **query shapes** with the following minimum details:

| Item to Gather | Question | Why It Matters for the Partition Key |
| --- | --- | --- |
| Mandatory inputs | Does the caller always have tenant, account, and day, or only an ID? | Partition key components must be supplied to locate a partition |
| Optional inputs | Can users omit date or account filters? | Omitting a key component creates a different query shape |
| Result scope | One account/day, multiple days, or whole tenant? | Determines partition count per request |
| Order and limit | Read newest first, what `LIMIT`? | Guides clustering and multi-partition handling |
| Load | Average/peak QPS, caller count, tenant skew? | Detects hotspots and fan-out under real load |
| Size | Rows/bytes per account/day, TTL, updates/deletes? | Forecasts partition growth |
| Targets | p95/p99, data freshness, read-after-write? | Prioritizes queries and validates SLAs |

### 3.1. Example Catalog for a Transaction Service

Suppose a multi-tenant system records transaction events for accounts. The frequencies below are **purely illustrative assumptions** to demonstrate the selection process:

| ID | Requirement | Available Inputs | Assumed Read Share | Characteristics |
| --- | --- | --- | --- | --- |
| Q01 | View 50 newest transactions for an account on a day | `tenantId`, `accountId`, `utcDay` | 75% | Single bounded scope, newest first |
| Q02 | View account transactions within an hour range on a day | `tenantId`, `accountId`, `utcDay`, two bounds | 15% | Same scope as Q01, time-filtered |
| Q03 | View account transactions over 7 days | `tenantId`, `accountId`, start date to end date | 8% | Multiple days, requires merging results |
| Q04 | Look up one transaction by event ID | `tenantId`, `eventId` | 2% | Account and day unknown |

If Q01 and Q02 have strict SLAs and represent the majority of requests, the primary access path is:

```text
tenant_id = ?
AND account_id = ?
AND day_bucket = ?
=> read events in this partition ordered by time
```

We can start with the candidate `(tenant_id, account_id, day_bucket)`. Q03 needs a bounded multi-bucket read strategy. Q04 needs an event-ID table or another lookup mechanism. Do not force all four queries into a single partition key.

### 3.2. Prioritize Beyond Raw Query Percentage

Suppose Q04 accounts for only 2% of traffic, yet it powers a dispute-resolution API with a strict SLO. In that case, it still needs a direct access path by ID. Modeling decisions must weigh **importance** and **constraints of each query shape**, never discarding a query simply because its share is small.

At the same time, before locking Q01, verify whether callers **truly always pass a UTC day**. If the UI only has a "50 most recent transactions regardless of date" button, choosing `day_bucket` as a key forces the application to define a strategy for probing recent days until enough rows are found. If that is the dominant requirement, bucketing and read paths must be reconsidered.

## 4. Process for Choosing a Partition Key

### Step 1. Write the Primary Query Contract in Concrete Values

Do not just write "filter by account"; write:

```text
Query ID: Q01
Required inputs:
  tenantId: authorized tenant identifier
  accountId: account identifier
  utcDay: UTC calendar date
Optional inputs: none on preview path
Output: eventId, occurredAt, amount, eventType
Order: occurredAt DESC, eventId DESC
Limit: 50 rows per view
Scope: exactly one account on one UTC day
```

If a value is not available at call time, it is a risky candidate for the partition key. Do not "solve" this by forcing the API to supply a value that cannot be known in the business context.

### Step 2. Choose Key Components That Isolate the Exact Read Scope

Compare candidates:

| Candidate Partition Key | Advantage | Issue to Watch For |
| --- | --- | --- |
| `(tenant_id)` | Tenant-wide queries know the key | Large tenants can create huge, hot partitions |
| `(tenant_id, account_id)` | Simple per-account reads | Historical data grows unboundedly without segmentation |
| `(tenant_id, account_id, day_bucket)` | Exact account/day reads; bounds rows per day | Multi-day reads touch multiple partitions; hot accounts may still grow large per day |
| `(tenant_id, account_id, event_id)` | Locates an event when ID is known | Listing events by account/day hits many partitions |
| `(tenant_id, day_bucket)` | Tenant/day queries have the key | All accounts in the same tenant/day funnel into one huge partition |

In this example, `(tenant_id, account_id, day_bucket)` matches Q01–Q02 **by read path**. However, the choice is only finalized after evaluating size and load.

### Step 3. Select Bucket Granularity and Check Hotspots

Suppose a heavy account sustains **10 events/second** continuously, with each row estimated at **500 bytes of raw data**:

```text
One day: 10 × 60 × 60 × 24 = 864,000 events
Raw size/day: 864,000 × 500 B ≈ 432 MB

One hour: 10 × 60 × 60 = 36,000 events
Raw size/hour: 36,000 × 500 B ≈ 18 MB
```

This is an illustrative calculation, **excluding storage overhead, indexes, tombstones, compaction, or replication**; never treat any number here as a universal safety threshold. Real on-disk usage can be significantly larger. If the largest account reaches this level, an **hourly** bucket may merit consideration over daily. However, reading a full day would then require merging up to 24 hourly partitions instead of one daily partition.

Therefore, balance **multi-bucket read cost** against **per-bucket size and hotness**. When only a few accounts are extreme outliers, explore tiered designs or key adjustments by load tier, while explicitly defining how the application locates the right partition in each case.

### Step 4. Choose Clustering Columns from Intra-Partition Ordering

Only after knowing the partition do we decide internal ordering:

```sql
PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)
```

Here `occurred_at` enables time-range reads and ordering; `event_id` distinguishes events occurring at the same timestamp. If `event_id` is a random UUID, UUID order merely provides a deterministic tie-breaker when timestamps match—it does **not** prove causal execution order between two simultaneous events.

### Step 5. Check Non-Matching Queries

List every query outside Q01/Q02: does it have the full partition key? Does it require global ordering across partitions? Does it filter on regular columns? Decide which queries will:

- Read a bounded set of partitions and merge in the application.
- Use a dedicated denormalized serving table.
- Use another search/analytics engine if arbitrary filtering and sorting dominate.
- Enforce clear product limits instead of exposing an unbounded API.

### Step 6. Validate with Data and Measurements

Collect distributions at **maximum, p95/p99, and peak hours**, not just averages. Inspect partitions/second and rows/bytes in the largest partition, throughput on hot partitions, tombstones, TTL effects, retry counts, read/write latency, and per-node resource usage.

## 5. Complete CQL Example: Partitioning by Account/Day

Assume `tenant_id` is text, `account_id` and `event_id` are UUIDs, and dates are normalized to UTC. We choose the table:

```sql
CREATE TABLE account_events_by_day (
    tenant_id text,
    account_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    description text,
    PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Three key points:

1. Cassandra identifies the partition using the **entire** `(tenant_id, account_id, day_bucket)` tuple.
2. `(occurred_at, event_id)` determines row position and uniqueness **inside** the partition.
3. `event_type`, `amount`, and `description` are only payload columns returned by this table, offering no fast access path by those attributes.

### 5.1. Q01: Fetching the 50 Newest Transactions of the Day

```sql
SELECT occurred_at, event_id, event_type, amount, description
FROM account_events_by_day
WHERE tenant_id = ?
  AND account_id = ?
  AND day_bucket = ?
LIMIT 50;
```

Because the table already defines descending clustering order, rows within the partition are read in the desired order without needing `ORDER BY`. The query supplies **the full partition key** and requires no post-read filtering on regular columns.

### 5.2. Q02: Time Range Within the Same Day

```sql
SELECT occurred_at, event_id, event_type, amount
FROM account_events_by_day
WHERE tenant_id = ?
  AND account_id = ?
  AND day_bucket = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 100;
```

The `[fromInclusive, toExclusive)` interval avoids double-counting at boundaries between adjacent ranges. Both bounds must lie within the day matching `day_bucket`; a range crossing UTC midnight must be split into two reads across two partitions.

### 5.3. Q03: Viewing Data Across Seven Days

Suppose the requirement is "most recent account events across **seven selected UTC calendar days**." With the current key, the application can:

1. Determine up to seven `day_bucket` values covering the range. If the requirement is a **sliding 7 × 24-hour** window rather than seven calendar days, the range can touch **eight** UTC dates and require reading up to eight buckets.
2. Read each partition using the appropriate Q01/Q02 query while bounding fetched rows.
3. Merge the streams by `(occurred_at DESC, event_id DESC)`.
4. Return the business-requested row count while preserving continuation info per partition.

Never assume a single `ORDER BY` across multiple partitions will cheaply produce a correct global order. If seven-day views become the primary read path, daily partitioning may no longer be optimal; re-evaluate bucket granularity, dedicated tables, and fan-out cost.

### 5.4. Q04: Lookup by Event ID

Q04 does **not** have `account_id` or `day_bucket`. To locate an event without scanning accounts/days, use another table:

```sql
CREATE TABLE account_events_by_id (
    tenant_id text,
    event_id uuid,
    account_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, event_id))
);

SELECT account_id, day_bucket, occurred_at, event_type, amount
FROM account_events_by_id
WHERE tenant_id = ? AND event_id = ?;
```

The design assumption is that `event_id` is unique within a tenant. If it is only unique per account, you must change the input contract or key; if `event_id` can repeat, this table will overwrite the same logical row.

The application can store full display data in the ID table or store only **locator** fields `(account_id, day_bucket, occurred_at)` and then read from the daily table. The second approach reduces duplication of some fields but adds a second read and must handle temporary projection lag.

## 6. Common Wrong Choices and Consequences

### 6.1. Using Only Tenant ID Because Every API Has Tenant

```sql
-- Example UNSUITABLE for tenants with large event histories:
PRIMARY KEY (tenant_id, occurred_at, event_id)
```

This puts all events for a tenant into a single partition when `tenant_id` is a single partition key. Even though the app always knows the key, large tenants create rapidly growing, potentially hot partitions. **Always having the key** is only a necessary condition; **size and load distribution** must also be acceptable.

### 6.2. Putting Timestamp or Event ID into the Partition Key When Reading a List

```sql
-- Each event sits in its own partition by event_id:
PRIMARY KEY ((tenant_id, event_id))
```

This works well for ID lookups, but is unsuitable for listing the 50 most recent events for an account if the caller does not know the `event_id` list beforehand. Very high-cardinality keys do not automatically provide an efficient read path for a list view.

### 6.3. Treating a Composite Partition Key as Multiple Skippable Indexes

With `PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)`, a query with only `tenant_id = ?` cannot locate a partition. A query with only `account_id = ?` is likewise missing key components. Do not treat `ALLOW FILTERING` as a design fix; it can cause large, unpredictable data scans or still be rejected depending on query shape.

### 6.4. Believing Token Hashing Solves Every Hotspot

Token hashing distributes **different partition keys**. If a single `(tenant, account, day)` tuple receives most of the traffic, all rows for that tuple still land on the same partition and replica set. This must be addressed through bucket design, access patterns, or even sharding when genuinely needed.

### 6.5. Using Averages as Representative

Suppose most accounts have 100 events/day, but one account has 500,000 events/day. System-wide averages may look small while the largest partition causes failures. When selecting buckets, forecast **peak load per logical key**, not just total rows divided evenly across accounts.

## 7. When Do You Need Time Bucketing or Sharding?

### 7.1. Time Buckets

Including `day_bucket`, `hour_bucket`, or `month_bucket` in the partition key bounds a partition's history over time. Agree upfront on:

- Whether days/hours use **UTC or a business timezone**; lock the rule at write time.
- Whether the bucket derives from `occurred_at` (event time) or `ingested_at` (system ingestion time).
- Handling **late-arriving** events, timestamp corrections, or events near day boundaries.
- Maximum buckets an API may read when users pick wide time ranges.

For example, an event occurs at `2026-11-20 23:59:59 UTC` but reaches the server after midnight: if the key uses the **occurrence date**, the event is still written to the day-20 bucket. This rule must be identical on both write and read paths. Changing bucket calculation mid-stream can make historical events unreachable through older APIs.

Time bucketing prevents unbounded historical accumulation in one partition, but it does little if a **single hour** already generates massive event volume.

### 7.2. Sharding an Overly Hot Logical Key

If an account's write rate is so high that even hourly buckets bottleneck, you can add `shard_id` to the partition key:

```sql
CREATE TABLE account_events_by_day_sharded (
    tenant_id text,
    account_id uuid,
    day_bucket date,
    shard_id int,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, account_id, day_bucket, shard_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

One way to choose a shard on the write path is `hash(event_id) mod N`, where `N` is fixed/managed per schema version. When looking up an event by ID, the application can compute its shard; when listing **all events for an account/day**, the application must read the relevant shards and merge order.

| Approach | Benefit | Trade-Off Cost |
| --- | --- | --- |
| No sharding, daily bucket | Simple single-partition/day reads | Partition can grow large or hot |
| Hourly bucket | Reduces data per partition over time | Multi-hour reads must merge multiple partitions |
| Daily bucket + `N` shards | Spreads one account/day's writes across partitions | Each list page may need fan-out across `N` partitions |
| Hourly bucket + shards | Tighter size bounds and load distribution | Complex key, fan-out, paging, and `N` evolution |

Never arbitrarily increase `N` without preserving readability of historical data: if the shard rule changes, you need a versioning/migration plan or metadata mapping `N` per time period. Sharding adds complexity and is not inherently the better choice.

## 8. Read Path from a Java Application

Choosing a partition key only pays off when the API actually passes all routing values. Example with DataStax Java Driver 4.x against `account_events_by_day`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.LocalDate;
import java.util.UUID;

public final class AccountEventReader {
    private final CqlSession session;
    private final PreparedStatement latestInDay;

    public AccountEventReader(CqlSession session) {
        this.session = session;
        this.latestInDay = session.prepare(
            "SELECT occurred_at, event_id, event_type, amount " +
            "FROM account_events_by_day " +
            "WHERE tenant_id = ? AND account_id = ? AND day_bucket = ? " +
            "LIMIT 50"
        );
    }

    public ResultSet latest(String tenantId, UUID accountId, LocalDate utcDay) {
        BoundStatement bound = latestInDay.bind(tenantId, accountId, utcDay);
        return session.execute(bound);
    }
}
```

`LocalDate` maps to CQL `date`, and `UUID` maps to `uuid`. The application must compute `utcDay` consistently with the write-path rule and verify that the caller is authorized for that tenant/account. Including `tenant_id` in the partition key **does not replace** application-layer authorization.

Prepared statements avoid string concatenation of input values and create a consistent call path. The driver can leverage routing key/token metadata when selecting suitable replicas, depending on topology configuration and load-balancing policy. Share one `CqlSession` managed by the service lifecycle rather than creating a new session per request.

If a screen loads multiple pages, distinguish `LIMIT 50` (maximum rows for the query) from driver **page size** (target rows per page). For deep pagination, typically use a prepared statement without a hardcoded `LIMIT 50`, configure page size, continue with opaque **paging state**, and bind tokens to the same query shape and parameters. Do not assume pages form an immutable snapshot under concurrent updates.

## 9. Relationship to Replication, Consistency, and Maintenance

A sound partition key gives queries a clear target; **replication factor**, placement, and **consistency level** govern how replicas satisfy requests. For example, `LOCAL_QUORUM` may suit certain intra-datacenter read/write needs given an appropriate replication configuration; the exact choice depends on SLAs and topology. Changing consistency level does **not** turn a query missing its partition key into a single-partition read.

When the same event also lives in `account_events_by_id`, the application must update all required representations. Cassandra does not provide a `JOIN` to synchronize two tables automatically. Multi-table writes can temporarily diverge if one write fails; you need safe retries, reconciliation, and designs that tolerate duplicates or late arrivals.

Operations such as compaction, repair, and TTL directly interact with large-partition maintenance:

- **Compaction** affects SSTable layout and read/write amplification, but cannot fix a bad partition key.
- **TTLs/deletes** can generate tombstones; a `LIMIT 50` query may still scan many tombstones before returning enough rows.
- **Repair** maintains replica consistency within Cassandra, but does not logically synchronize application-managed denormalized tables.

Therefore, control large partitions, tombstones, write rates, and read patterns during key selection before tuning compaction or consistency levels.

## 10. Verification Checklist Before Finalizing a Partition Key

| Verification Question | Passing Signal | Redesign Needed When |
| --- | --- | --- |
| Does the caller have all partition key components? | Q01/Q02 always receive tenant, account, day | Most requests lack account/day |
| Do any queries look up by a different key? | Q04 has an event-ID table/read path | API silently scans many accounts to find an ID |
| Is partition growth bounded? | Bucket matches data rate and retention | One account can grow unboundedly in one partition |
| How is load distributed? | Hottest partition meets measured targets | Based only on averages or guesses |
| Are partitions per request bounded? | 1 day = 1 partition; 7-day queries capped | API can fan out across thousands of buckets |
| Does clustering match read order? | `occurred_at DESC, event_id DESC` fits | UI demands tenant-wide `ORDER BY amount` |
| Are bucketing rules consistent? | Standardized UTC and event time | Writing by ingest time while reading by event time |
| Is the multi-table write path managed? | Retries/idempotency and reconciliation exist | One projection succeeds while another loses data |
| Was it tested with representative data? | Tested extremes, p95/p99, tombstones, and peaks | Only ran a few `SELECT`s on tiny sample rows |

In an appropriate test environment, use `cqlsh` to verify CQL syntax; populate representative partitions including both typical and very large accounts; and use metrics/tracing to observe latency, bytes/rows read, and tombstone impact. Test UTC boundaries, empty ranges, late events, and multi-bucket queries. A single query succeeding in isolation is **not enough** to prove a partition key performs well under load.

## 11. Practice Exercise

A Java application tracks status-transition logs for delivery parcels. Each record contains:

```text
tenant_id, parcel_id, changed_at, change_id, status, actor_id, note
```

APIs:

1. **R1:** View the 20 most recent status changes for a parcel on a UTC day.
2. **R2:** View status changes for a parcel from 08:00 to before 10:00 on the same day.
3. **R3:** View the 100 most recent changes for a parcel across 30 selected UTC calendar days.
4. **R4:** Look up a single change by `change_id`, knowing only the tenant.
5. **R5:** Staff views all changes with `status = FAILED` for a tenant on a given day.

Tasks:

1. Identify the primary access path if R1/R2 make up 90% of reads and have the strictest SLAs.
2. Propose a partition key, clustering key, and write the `CREATE TABLE` for R1/R2.
3. Explain how many buckets R3 must read if daily buckets are chosen; propose API limits and how to merge results.
4. Explain why R4/R5 lack an access path on the R1/R2 table and sketch the tables/projections to investigate.
5. If a single parcel receives up to 1 million updates/day, what additional metrics must you collect before deciding among daily buckets, hourly buckets, or sharding?

**Reference guidance:** For R1/R2, a candidate is partition key `(tenant_id, parcel_id, day_bucket)` and clustering `(changed_at DESC, change_id DESC)`. R3 touches 30 daily partitions for one parcel if the range covers 30 UTC calendar days; a strict sliding 30 × 24-hour window can touch **31** daily partitions. Both require bounding fan-out and merging. R4 needs a lookup path via `(tenant_id, change_id)` if the ID is unique within the tenant. R5 is a tenant-wide status query shape requiring a dedicated table/projection with measured bucketing and load distribution. One million updates/day is a signal to inspect row size, peak write rate, tombstone counts, and partition load before committing.

## Conclusion

A sound partition key is derived from **values the application always knows on the primary read path**, then validated against **partition scale and real workload**. A key that routes cleanly can still create oversized or hot partitions; a key that distributes evenly yet lacks required read-time values cannot serve the API. Effective Cassandra design therefore locks down the query contract, partition key, bucketing, clustering, alternative read paths, and fan-out bounds together, then proves them with representative data and measurements on the target cluster.
