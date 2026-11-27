# Integrated Practice: Designing an Activity History Table by Tenant and Time Bucket

## 1. Context and Objectives

A multi-tenant SaaS application needs to store activity history: logins, order creations, configuration changes, permission updates, and audit actions. Each record belongs to exactly one `tenant_id`; the API typically returns the newest activities first and supports filtering by time range. The system uses **Apache Cassandra** because it requires continuous writes, horizontal scaling across multiple nodes, and supports well-defined query patterns.

This lab combines **distributed architecture, wide-column modeling, partition keys, query-driven table design, CQL, replication, consistency, compaction, repair, failure handling, and the Java Driver**. The goal is a design that can be explained, tested, and operated in practice, rather than just creating a table.

**Problem assumptions** (adjust these numbers for real environments):

- Primary API: `GET /tenants/{tenantId}/activities?from=...&to=...&limit=50&cursor=...`.
- Data is read strictly within the scope of a single tenant; by default, results are returned in descending order of `occurred_at`.
- Retain records for **90 days from the time they are written to Cassandra**; no updates to individual events are needed after emission.
- Both event timestamps and buckets are normalized to **UTC**; the API accepts a half-open interval `[from, to)`.
- A tenant can generate anywhere from a few hundred to millions of events per day; large tenants may experience traffic spikes.
- The API does not need global aggregations or searching all events by `action` without a tenant and time range.

**Acceptance criteria:** common queries run by partition key without `ALLOW FILTERING`; one tenant's data never leaks into another's; a single partition never grows unboundedly; the API traverses multiple days in the correct order; the implementer can explain consistency, TTL, compaction, and how replica failures are handled.

## 2. Translating Read Requirements into a Wide-Column Model

In Cassandra, the **partition key** determines data placement across replicas by token; **clustering columns** order rows *within the same partition*. You should not copy a relational schema verbatim (one table per entity with ad-hoc queries) into Cassandra.

| Query to serve | Access path | Design implication |
| --- | --- | --- |
| 50 most recent activities for tenant A | Most recent time buckets of A, newest to oldest | Put tenant and bucket into the partition key; sort events descending |
| Activities of A over 3 days | Read buckets intersecting `[from, to)` sequentially | Each CQL query targets a single partition; merge results in the application |
| Next page of A's history | Continue current partition and paging state; then move to the next bucket | API cursor stores the current bucket and paging state |
| Find all `LOGIN` events across all tenants | **Not in the required API** | Requires a separate query model/table if needed later |

Each event carries at least these fields:

| Field | Role |
| --- | --- |
| `tenant_id` | Tenant identifier; must come from the authenticated context |
| `bucket_day` | UTC date derived from `occurred_at`, used to split partitions |
| `occurred_at` | Time the activity occurred, used for sorting and filtering |
| `event_id` | Stable UUID from the emitter; disambiguates simultaneous events and enables safe retries |
| `actor_id`, `action`, `object_type`, `object_id` | Information displayed in the activity feed |
| `details_json` | Small, size-bounded payload; must not hold arbitrary large documents |

Primary key for the baseline version:

~~~sql
PRIMARY KEY ((tenant_id, bucket_day), occurred_at, event_id)
~~~

The pair `(tenant_id, bucket_day)` is a **composite partition key**. The two columns `occurred_at` and `event_id` are **clustering columns**. Each tenant has multiple partitions, one partition per day. Events from two tenants on the same day still reside in separate partitions. Including `event_id` in the key ensures two events occurring in the same millisecond do not overwrite each other.

**Limitation to remember:** Cassandra does not automatically stitch buckets together into a globally sorted result. A query omitting `bucket_day` cannot use this key to fetch "all activities of tenant A". Bucket iteration logic belongs in the application.

## 3. Choosing Bucket Size and Estimating Partition Size

There is no single best bucket size for every tenant. Rough estimate:

~~~text
partition_size ≈
  tenant_events_per_day × bytes_per_event
  / buckets_per_day
  / shards_per_bucket
~~~

For example, suppose a tenant writes **2,400,000 events/day**, with each row averaging about **1 KiB** (an initial estimate including payload, before full storage overhead). A daily bucket yields roughly **2,344 MiB/partition**; an hourly bucket yields roughly **98 MiB/partition**; an hourly bucket with **4 shards** drops to roughly **24.4 MiB/partition** assuming even distribution. You must measure actual sizes and account for peak hours because load is uneven.

To start the lab, choose a **daily bucket** because fewer partitions need to be read and it is easier to inspect. When measurements show certain tenants creating oversized partitions or a single partition receiving excessive write traffic, move hot tenants to **hourly buckets** and/or **sharding**. Practical operational thresholds depend on row shape, workload, and Cassandra version; you can use a few tens of MiB per partition as an exploratory target and calibrate with metrics rather than treating it as a hard Cassandra limit.

| Approach | Pros | Cost |
| --- | --- | --- |
| Daily, no shard | Reading 7 days hits only ~7 partitions/tenant | Large tenants can create huge partitions and hotspots |
| Hourly, no shard | Smaller partitions, distributes load over time | Reading 7 days may require 168 partitions |
| Hourly + shard | Splits write load within the same hour for large tenants | Must read multiple shards and merge results chronologically |

If sharding is added, the key can become:

~~~sql
PRIMARY KEY ((tenant_id, bucket_hour, shard_id), occurred_at, event_id)
~~~

`bucket_hour` is the start of the UTC hour; `shard_id` is computed with a deterministic hash on `event_id`, e.g., `hash(event_id) mod 4` normalized to a non-negative integer. The shard count must be governed by a schema/design version with a lookup mechanism when changed. To fetch an hour's history, the application must read **all shards that could contain data** and merge them in `(occurred_at DESC, event_id DESC)` order. Never pick a single random shard for a read request. **The CQL lab below intentionally uses daily buckets without shards** so you can clearly observe partitions and row ordering before scaling out.

## 4. Creating the Keyspace and Table with CQL

First, check the datacenter name returned by the node:

~~~sql
SELECT data_center FROM system.local;
~~~

The following example assumes a cluster with **3 replicas in datacenter `datacenter1`**. Replace `datacenter1` with your cluster's actual datacenter name. The `LOCAL_QUORUM` command below will only succeed when enough replicas are up.

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS activity_lab.activities_by_tenant_day (
    tenant_id     text,
    bucket_day    date,
    occurred_at   timestamp,
    event_id      uuid,
    actor_id      text,
    action        text,
    object_type   text,
    object_id     text,
    details_json  text,
    PRIMARY KEY ((tenant_id, bucket_day), occurred_at, event_id)
)
WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC)
 AND default_time_to_live = 7776000
 AND compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
 };
~~~

**Design choices explained:**

1. `NetworkTopologyStrategy` distributes replicas according to datacenter topology; RF=3 is configured per DC, which does not mean the cluster must have exactly three nodes. In a **single-node** lab, you can use RF=1 and `CONSISTENCY ONE` to practice the syntax, but you cannot use that setup as evidence of `LOCAL_QUORUM` behavior under replica failure.
2. `CLUSTERING ORDER BY` retrieves newest activities first within **each** day for **each** tenant.
3. `default_time_to_live = 7776000` equals 90 × 24 × 60 × 60 seconds. TTL is measured from **write time**, not from `occurred_at`. Late-arriving events would still be retained for 90 days after ingest; if the policy is "delete exactly 90 days after the event occurred," the write layer must compute the remaining TTL per record.
4. `TimeWindowCompactionStrategy` (TWCS) is generally well suited for time-series writes with relatively uniform TTLs. **TWCS windows are based on cell/SSTable write timestamps**, not directly on the `bucket_day` column value. Very late writes, frequent updates to old rows, or mixing heterogeneous TTLs can degrade cleanup efficiency.
5. The table uses a `text` column `details_json` to keep the lab simple. In a real application, store only fields you actually read, bound payload sizes, and avoid turning a row into a large blob store.

## 5. Writing Sample Data and Verifying Results

In a cluster with RF=3 in the local DC, set the consistency level for the `cqlsh` session:

~~~sql
CONSISTENCY LOCAL_QUORUM;
~~~

Insert four activities into three partitions: two days for `tenant-a` and one day for `tenant-b`.

~~~sql
INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-a', '2026-11-19', '2026-11-19T09:10:00Z',
 11111111-1111-4111-8111-111111111111,
 'u-1', 'LOGIN', 'session', 's-1', '{"ip":"192.0.2.10"}');

INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-a', '2026-11-19', '2026-11-19T10:15:00Z',
 22222222-2222-4222-8222-222222222222,
 'u-1', 'UPDATE', 'order', 'o-9', '{"field":"status"}');

INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-a', '2026-11-18', '2026-11-18T23:58:00Z',
 33333333-3333-4333-8333-333333333333,
 'u-2', 'CREATE', 'order', 'o-9', '{}');

INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-b', '2026-11-19', '2026-11-19T11:00:00Z',
 44444444-4444-4444-8444-444444444444,
 'u-3', 'LOGIN', 'session', 's-2', '{}');
~~~

Read activities for `tenant-a` on November 19:

~~~sql
SELECT occurred_at, event_id, actor_id, action, object_id
FROM activity_lab.activities_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND bucket_day = '2026-11-19'
LIMIT 50;
~~~

**Expected result:** the `10:15 UPDATE` row appears before `09:10 LOGIN`; no rows from `tenant-b` or November 18 appear. Test range filtering within a bucket:

~~~sql
SELECT occurred_at, action, object_id
FROM activity_lab.activities_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND bucket_day = '2026-11-19'
  AND occurred_at >= '2026-11-19T09:30:00Z'
  AND occurred_at <  '2026-11-20T00:00:00Z'
LIMIT 50;
~~~

**Expected result:** only `10:15 UPDATE`. With real data, `bucket_day` **must** be derived from the exact same `occurred_at` value after normalizing to UTC. Never compute the date using the Java server's local timezone or the user's timezone, as that puts records into the wrong bucket and causes queries near midnight to miss rows.

Try reading without part of the partition key:

~~~sql
-- Not a query supported by this table model:
-- SELECT * FROM activity_lab.activities_by_tenant_day
-- WHERE tenant_id = 'tenant-a';
~~~

Keep the example above commented out to avoid errors when running the script. Never "fix" it by adding `ALLOW FILTERING`: scanning across many partitions scales poorly with data volume and fails to produce the global order the API expects.

## 6. Reading Across Multiple Buckets and Pagination Design

### 6.1. What steps does a single request take?

Suppose the API needs 50 activities for tenant A over `[2026-11-18T00:00:00Z, 2026-11-20T00:00:00Z)`:

1. Authenticate the tenant from the token/permissions; verify that the tenant in the URL matches the authorized tenant. Cap the time window width and `limit` to prevent unbounded scans.
2. Walk bucket **Nov 19 then Nov 18**. For each bucket, query by `(tenant_id, bucket_day)`, constraining `occurred_at` to the intersection with the requested range.
3. Iterate rows in descending clustering order, appending to the result up to `limit`; once a day is exhausted, move to the previous day.
4. If more data may exist, return a **cursor** containing the current day and continuation state; if the range is exhausted, return `nextCursor = null`.

Each query targets **a single partition**. Overall ordering holds because every timestamp on Nov 19 UTC is newer than every timestamp on Nov 18 UTC. If the API later shards an hour across multiple partitions, order can no longer be obtained by concatenating arrays: you must **merge sorted streams** across shards.

Pseudocode for the daily-bucket design:

~~~text
getPage(authorizedTenant, fromUtc, toUtc, limit, cursor):
    validate(fromUtc < toUtc, 1 <= limit <= configuredMax)
    state = verifyCursorOrStart(cursor, authorizedTenant, fromUtc, toUtc)
    result = []

    while result.size < limit and state.day >= fromUtc.dateUTC:
        begin = max(fromUtc, startOfDayUTC(state.day))
        end   = min(toUtc, startOfNextDayUTC(state.day))

        if begin >= end:
            state = previousDay(state.day)
            continue

        page = readOnePartition(
            tenantId=authorizedTenant,
            day=state.day,
            occurredAtFrom=begin,
            occurredAtTo=end,
            pagingState=state.driverPagingState
        )
        appendUpToLimit(result, page.rows)

        if page.hasMoreInSamePartition:
            state.driverPagingState = page.nextPagingState
        else:
            state.day = state.day - 1 day
            state.driverPagingState = null

    return result, signAndEncode(state) if moreDataPossible else null
~~~

This snippet illustrates **the overall structure**, not a complete program: when a driver fetch returns more rows than remaining space in the API page, you must retain the unused rows or configure fetch/limit appropriately so rows are never dropped. CQL's `LIMIT 50` caps the total rows returned by *one query*, whereas **driver page size** controls how many rows are fetched per protocol page. These two concepts are not interchangeable.

### 6.2. Secure and Consistent Cursors

A cursor should include the current bucket, driver paging state (if any), `tenantId`, `from`, `to`, `limit` (or a hash of the parameter set), schema version, and expiration timestamp. Sign or authenticated-encrypt the token to prevent tampering with the tenant or time bounds; **never accept an arbitrary paging state directly from the client and attach it to a different query**. Paging state must remain bound to the exact CQL statement and parameters.

Cassandra does not provide a cross-partition snapshot for this feed. Concurrent or late writes during pagination can alter results; the API should document **near-real-time history** semantics, consider pinning a fixed `to` timestamp on the first page, and use `event_id` for client-side deduplication when needed. Pinning `to` only excludes new events with `occurred_at` after that cutoff; it does **not** turn pages into a transactional snapshot if older events arrive late.

## 7. Reading from a Java Application

This example uses the **DataStax/Apache Cassandra Java Driver 4.x** with `CqlSession`. The snippet reads only **the first protocol page of a single bucket**; the API layer applies the algorithm from section 6 to traverse multiple days and persist the cursor.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PagingState;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;

public class ActivityHistoryExample {
    public static void main(String[] args) {
        // Configure contact points, auth, and local DC for your real cluster.
        try (CqlSession session = CqlSession.builder()
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT occurred_at, event_id, actor_id, action, object_id " +
                "FROM activity_lab.activities_by_tenant_day " +
                "WHERE tenant_id = ? AND bucket_day = ? " +
                "AND occurred_at >= ? AND occurred_at < ?");

            String tenantId = "tenant-a"; // Obtained from authenticated context.
            LocalDate dayUtc = LocalDate.parse("2026-11-19");
            Instant from = Instant.parse("2026-11-19T00:00:00Z");
            Instant to = Instant.parse("2026-11-20T00:00:00Z");

            BoundStatement bound = query.bind(tenantId, dayUtc, from, to)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(50);

            ResultSet rows = session.execute(bound);
            int available = rows.getAvailableWithoutFetching();

            for (int i = 0; i < available; i++) {
                Row row = rows.one();
                System.out.printf("%s | %s | %s%n",
                    row.getInstant("occurred_at"),
                    row.getString("action"),
                    row.getUuid("event_id"));
            }

            PagingState nextPage = rows.getExecutionInfo().getPagingState();
            // When nextPage != null, store it inside an authenticated cursor
            // and reuse it with the exact same query/parameters on the next request.
        }
    }
}
~~~

**Java checkpoints:** `LocalDate` maps to CQL `date`, `Instant` maps to `timestamp`, and `UUID` maps to `uuid`. Use prepared statements and bind parameters; never concatenate `tenantId` into CQL strings. In web applications, keep `CqlSession` alive and reuse it (managed as an application-scoped resource), rather than creating a new session per request. Only return data for the authorized tenant, even if a caller attempts to alter `tenantId` in the URL or cursor.

For the Java write path, generate `event_id` **once at the emitter** and reuse it across all retries; compute `bucket_day = occurredAt.atZone(UTC).toLocalDate()`. With the same primary key, retries upsert the same row; generating a new UUID on each retry creates duplicate rows. Updating `occurred_at` on an event mutates the primary key: this design is better suited for immutable (append-only) events.

## 8. Consistency, Replication, and Failure Testing

With **RF=3** per DC, a common configuration is writing at `LOCAL_QUORUM` and reading at `LOCAL_QUORUM`. Each operation requires acknowledgments from **2 of 3 local replicas**; `R + W > RF` (2 + 2 > 3) guarantees overlap between the replicas that acknowledged the write and the replicas serving the read, under proper operating conditions. This does **not** turn Cassandra into a general-purpose ACID transactional database: concurrent operations on the same cell are reconciled by timestamp (last-write-wins), and clock skew or coordination failures can affect outcomes. `LOCAL_QUORUM` also guarantees quorum **only within the local datacenter**, not simultaneously in remote DCs.

| Test with RF=3, LOCAL_QUORUM | Expectation | What to observe |
| --- | --- | --- |
| All three replicas up | Writes/reads succeed barring other faults | p95 latency, timeouts, and responding replica count |
| One replica temporarily down | Writes/reads generally still succeed with the two remaining replicas | Latency and how the recovered replica catches up |
| Two replicas temporarily down | Local quorum cannot be reached; requests may fail | Application returns controlled errors, retries with backoff |
| Resending event with same key | Single logical row under the same primary key | No duplicate records caused by a fresh UUID |

In the lab, only simulate replica outages on a **test cluster designated for fault injection**. Never lower `CONSISTENCY` in production just to mask a quorum error without evaluating read/write correctness requirements. On a write timeout, the client **cannot know** whether the write succeeded on some replicas; retrying with the same `event_id` and payload reduces the risk of duplicates. Never treat a timeout as proof that data was not persisted.

When a read API request fails due to unavailability, return a clear error (such as HTTP 503) and apply bounded retries with exponential backoff and jitter at the appropriate layer. Never fall back automatically to full-table scans or return another tenant's data.

## 9. TTL, TWCS, Tombstones, and Repair

**TTL** enables automatic history expiration, but expired rows do not vanish from disk immediately. Cassandra represents deletions/expirations using **tombstones**; only subsequent compactions can physically reclaim space once safety conditions are met. Therefore, monitor tombstones, disk utilization, and long-term read latency, especially when the API queries buckets whose data has mostly expired.

**TWCS** groups SSTables by write-time windows, which works well when workloads are mostly append-only and data within a window shares similar TTLs. Continuously updating old activities or backfilling large volumes of historical events causes multiple windows to hold related data, reducing cleanup efficiency. Tune window width based on observed write rate, retention, SSTable counts, and compaction behavior.

**Repair** synchronizes divergent replicas; replication and `LOCAL_QUORUM` **do not eliminate the need for repair**. Schedule repairs in alignment with `gc_grace_seconds`, maximum replica downtime windows, and maintenance policies; never lower `gc_grace_seconds` arbitrarily, because a replica missing a tombstone can cause **data resurrection** (deleted data reappearing). TTL expiration and tombstone purging must be validated under your real cluster's repair and compaction policies.

Metrics to include on your dashboard:

- Partition size by tenant/bucket, hot-tenant skew, read/write throughput, and p95/p99 latency.
- Timeouts, unavailable errors, retries, pending compactions, SSTable counts, and disk usage.
- Tombstone warnings/scans, completed or overdue repairs, driver latency and errors.
- Bucket depth scanned per request, number of partitions read per request, cursor size, and empty-page ratio.

Avoid running `SELECT COUNT(*)` across multiple partitions or scanning all tenants to populate dashboard counters. If analytics are required, build an aggregation pipeline or summary table tailored to that query and accept its consistency semantics.

## 10. Extension Exercises and Self-Check Questions

**Exercise A — Partitioning and ordering check:** write two additional events for `tenant-a` with the exact same `occurred_at` but two distinct `event_id` values. Verify both exist and maintain a deterministic order within the partition. Write an event at `2026-11-20T00:01:00Z` and verify it lands in the Nov 20 bucket and does not appear when querying Nov 19.

**Exercise B — Multi-day pagination:** implement an API returning 2 records per page over the sample data and Exercise A's data. Verify subsequent pages do not drop activities at day boundaries and that `tenant-a`'s cursor cannot be reused for `tenant-b`. Add a test with `to` set to exactly 00:00 UTC to ensure it does not accidentally read into the next day.

**Exercise C — Hot tenant:** suppose tenant X generates 2.4 million events/day, with an average row size of 1 KiB and 90-day retention. Calculate partition sizes for daily buckets, hourly buckets, and hourly × 4 shards; explain the trade-off in number of partitions read for a 24-hour API query. Then use measured row sizes and peak-hour load to size parameters rather than relying solely on averages.

**Exercise D — Consistency and failures:** on an RF=3 test cluster using `LOCAL_QUORUM`, write with a fixed `event_id`, stop one replica and read, then evaluate the impact of stopping a second replica. Document the results and inspect driver logs/metrics. Never induce faults intentionally on a production system serving live users.

**Exercise E — Operations:** explain why a record with a 90-day TTL can still occupy disk space after 90 days, which timestamp TWCS uses, and why lowering `gc_grace_seconds` without reliable repairs is dangerous. Propose at least three metrics to detect oversized partitions and tombstone scans.

**Decision questions:**

1. Why can `PRIMARY KEY (tenant_id, occurred_at)` cause unbounded partition growth? Why does adding a secondary index on `occurred_at` fail to solve reading by tenant and bucket?
2. If the API adds a feature for "all activities of actor U in tenant A over 30 days," do you need a new table `activities_by_tenant_actor_day`? Describe its primary key and the write-amplification cost.
3. If a tenant using daily buckets is migrated to hourly buckets, how does the application read older data during the transition period? You need versioned bucket rules, controlled backfills, or dual-schema reads during the transition window.
4. If an activity occurs at 23:59 UTC but reaches the system at 00:10 the next day, which daily bucket should it be written into? Under this design: **the date of `occurred_at`**, whereas the 90-day TTL starts at write time.

## 11. Acceptance Checklist

- [ ] Partition key contains **both tenant and bucket**; two events with identical `occurred_at` remain distinct via `event_id`.
- [ ] API queries restrict tenant, time range, and row limit and use the exact partition key; **no** `ALLOW FILTERING` or full-cluster scans.
- [ ] Results are returned newest-first within each bucket; buckets are traversed newest-to-oldest; if sharded, streams are properly merge-sorted.
- [ ] Timestamps and `[from, to)` intervals are handled in UTC, including midnight boundaries and late-arriving events.
- [ ] Cursors are bound to tenant/parameters, authenticated, and resume cleanly without skipping rows.
- [ ] Write retries reuse a stable `event_id`; the Java Driver uses prepared statements, paging, explicit consistency, and a reused session.
- [ ] Partition size is calculated from real traffic, with an hourly/sharded plan for hot tenants.
- [ ] RF, consistency levels, replica-failure behavior, TTL, TWCS, tombstones, and repair are verified in an appropriate test environment.
- [ ] Limitations are documented: no cross-bucket joins, no cross-partition transactional snapshots, and new query patterns may require new tables.

**Outcome of this lab** is a Cassandra table serving an activity history feed **by tenant and time**, complete with a multi-partition read algorithm, Java driver integration, and operational decisions grounded in Cassandra's distributed architecture.
