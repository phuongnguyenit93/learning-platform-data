# Tenant Keys and Bounding Oversized Tenants

In a **multi-tenant** system using Apache Cassandra, a single table may serve anywhere from dozens to thousands of tenants. Each tenant can be a company, organization, or customer sharing the same service. Tenants rarely share the same scale: a small customer generates a few hundred events per day, whereas a huge customer can generate millions of events per hour.

When designing distributed wide-column tables, **`tenant_id` is often an essential component of the partition key**, yet using `tenant_id` alone as the partition key for all data of a tenant is a common trap. If a tenant is large, all of their data and traffic can funnel into **a single logical partition**, leading to *large partitions*, *hot partitions*, and the *noisy neighbor* effect impacting other tenants.

This lesson focuses on using tenant keys **at the right scope**, designing partition keys with additional business domains, time buckets, or shards when necessary, and establishing **resource limits and per-tenant load controls**. Those decisions connect directly to replication, consistency levels, compaction, repair, CQL queries, and the Java Driver.

After this lesson, you will be able to:

- Distinguish **tenant identity**, **partition key**, and **authorization boundaries**.
- Explain why a partition key containing only `tenant_id` can become a bottleneck.
- Design tables serving tenant–device–day queries and tenant-wide timelines.
- Estimate partition sizes, load skew, and fan-out when using time buckets or shards.
- Set write, read, storage, and query quotas for large tenants without relying on a mythical built-in Cassandra feature.
- Keep bucket/shard routing stable in Java across retries, backfills, and tenant policy changes.

## 1. What does `tenant_id` represent?

A tenant is a **data ownership and usage domain** within an application. For example:

```text
Tenant acme
  ├── user A
  ├── user B
  ├── device D1
  └── device D2

Tenant beta
  ├── user C
  └── device D3
```

The application must usually ensure that requests from tenant `acme` cannot read or modify data of tenant `beta`. Therefore, every access path must carry clear tenant context.

In Cassandra, three concepts **must not be conflated**:

| Concept | Meaning | What it does not automatically guarantee |
| --- | --- | --- |
| **Tenant identity** | Tenant identifier managed and authenticated by the application. | Does not inherently specify which node holds the data. |
| **Partition key** | Value combination Cassandra hashes into a token to locate a partition. | Does not automatically grant access permissions or cap storage volume. |
| **Tenant access control** | Authentication, authorization, and query-control policies. | Not enforced automatically just because a table has a `tenant_id` column. |

Cassandra provides authentication/authorization mechanisms for supported resources such as keyspaces and tables, yet **putting `tenant_id` in a shared table should not be treated as automatic row-level authorization**. The application layer must derive the tenant from an authenticated context, verify permissions, and **bind `tenant_id` from trusted context** rather than trusting raw client-supplied tenant values.

For instance, an API request arbitrarily passing `tenant_id = 'beta'` must never be allowed to switch the access scope of a user authenticated into `acme`. Partition key design helps organize and route data; security isolation must be designed explicitly.

## 2. Why can `PRIMARY KEY (tenant_id, ...)` be dangerous?

Suppose a service records all events of a tenant over time:

```sql
CREATE TABLE events_by_tenant_all_time (
    tenant_id   text,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (tenant_id, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

The syntax `PRIMARY KEY (tenant_id, occurred_at, event_id)` means:

- The partition key is **only** `tenant_id`.
- Clustering columns are `occurred_at` and `event_id`.
- Every event of tenant `acme` belongs to **one logical partition**, regardless of time or source.

```text
Partition key 'acme'
│
├── (2026-11-21T10:03Z, E3)
├── (2026-11-21T10:02Z, E2)
├── (2026-11-21T10:01Z, E1)
│   ...
└── millions of events across many months

Partition key 'beta'
│
└── far fewer events
```

**Common point of confusion:** high cardinality on `event_id` does not create extra partition keys. Only `tenant_id` is hashed to select the replica set; the two clustering columns merely distinguish rows **within that partition**.

If `acme` generates most of the data and queries, the replica set of partition `acme` must serve most of the work. Adding nodes or increasing the replication factor can add cluster-wide capacity, yet **does not automatically split a single partition key into multiple partition keys**.

### Composite keys are not prefix searches

If modified to:

```sql
PRIMARY KEY ((tenant_id, device_id), occurred_at, event_id)
```

each `(tenant_id, device_id)` pair becomes its own partition key. This separates data across devices, yet a query with only `WHERE tenant_id = 'acme'` **does not identify a complete partition key**.

Cassandra hashes the **entire** composite key tuple; placing `tenant_id` before `device_id` does not create an index range allowing efficient scans of all tenant devices by default. To query tenant-wide, you need a data model or access path built for that goal.

## 3. How do large tenants skew load?

Suppose a platform has **1,000 tenants**:

- 999 standard tenants, each averaging **5 events/second**.
- One large tenant `whale` generating **6,000 events/second**.
- Each event carries an average **600 bytes of logical payload**.

Estimated total write load:

```text
Standard tenants:
  999 × 5 = 4,995 events/second

Tenant whale:
  6,000 events/second

Entire system:
  4,995 + 6,000 = 10,995 events/second

Tenant whale share:
  6,000 / 10,995 ≈ 54.6% of total writes
```

Tenant `whale` makes up around **0.1% of tenants** yet produces **over half** of the write load. If the partition key is only `tenant_id`, all 6,000 writes/second funnel into that tenant's single partition.

In **one minute**, the large tenant creates:

```text
New rows (assuming each event has a distinct full primary key):
  6,000 × 60 = 360,000 rows

Logical payload:
  360,000 × 600 bytes = 216,000,000 bytes
                      = 216 MB ≈ 206 MiB
```

These numbers **exclude** clustering keys, metadata, collections, tombstones, compression, and replica copies. If this rate continues for 24 hours, row and byte counts of an unbucketed partition key grow very rapidly.

### Three limit dimensions to consider separately

| Risk | Manifestation | Why a single tenant key can be the cause |
| --- | --- | --- |
| **Partition size** | One partition holds too many rows/cells/bytes. | Tenant data accumulates into the same key over time. |
| **Write/read hotspot** | p95/p99 latency and timeouts rise on certain replicas. | Large tenant continuously reads/writes to the exact same replica set. |
| **Noisy neighbor** | Small tenants suffer despite having little data. | Large tenant consumes CPU, I/O, network, queues, compaction, and shared node resources. |

A large partition is not necessarily hot, and a hot partition may not yet be large. Monitor both **size and access frequency**, not just total tenant count or table-wide averages.

## 4. Tenant key design starts from queries

Before picking a schema, list the questions the product needs to support:

| Query | Values available to the app at read time | Suggested partition key |
| --- | --- | --- |
| Q1: Fetch 100 latest readings of one device in a day | Tenant, device, day | `(tenant_id, device_id, event_day)` |
| Q2: Fetch latest **tenant-wide** events in one minute | Tenant, minute; configured shards known | `(tenant_id, minute_bucket, shard_id)` |
| Q3: Look up one event by ID | Tenant, event ID | `(tenant_id, event_id)` |
| Q4: List devices of a tenant | Tenant, possibly device shards | `(tenant_id, device_shard)` with `device_id` as clustering key |
| Q5: Report total events for a tenant in a month | Tenant, month | Summary table by tenant/month with appropriate update semantics |

One table rarely serves every query optimally. Cassandra generally favors **query-driven table design**, accepting controlled duplication and defining write/recovery mechanisms when a business flow must update multiple tables.

**Never assume data updates atomically across multiple tables just because they share `tenant_id`.** Operations across different partition keys or tables can succeed or fail independently; the application must handle retries, backfills, and reconciliation.

## 5. Pattern 1: partitioning by tenant–device–day

If the primary query is the history of **one device in one day**, a natural table is:

```sql
CREATE TABLE device_events_by_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

The three columns `(tenant_id, device_id, event_day)` together form a **composite partition key**. Rows for the same tenant but different devices or different days belong to **different logical partitions**.

### Writing CQL to the right bucket

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading',
    'temperature=38.1'
);
```

Convention in this example: `event_day` is the **UTC date** of `occurred_at`. Writers and readers must agree on bucket calculation; local calendar dates do not always match UTC dates.

### Reading a single partition

```sql
SELECT occurred_at, event_id, event_type, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
```

The **full partition key** and a clustering column range are provided. Cassandra can read the exact slice within the partition. `LIMIT 100` bounds **returned rows**, not the physical size of the partition or guaranteeing only 100 cells are read when tombstones exist.

### Does this pattern solve every large tenant?

**No.** If a single device of tenant `whale` accounts for 90% of traffic, partition `(whale, that_device, today)` can still run red-hot. Splitting by entity and day lowers overall concentration, yet does not guarantee moderate load per partition.

If multi-day history is needed, the application must query the relevant buckets and merge chronologically; clustering order is scoped strictly to **one partition**.

## 6. Pattern 2: tenant-wide timeline by minute and shard

Another requirement is **"fetch the 100 latest events of tenant T in minute M, regardless of device."** The per-device table above does not suit direct querying because `device_id` is missing from the partition key.

For large tenants, you can build a **dedicated table**:

```sql
CREATE TABLE tenant_events_by_minute_shard (
    tenant_id     text,
    minute_bucket timestamp,
    shard_id      smallint,
    occurred_at   timestamp,
    event_id      uuid,
    device_id     uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, minute_bucket, shard_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Each tenant has **multiple concurrent partition keys within a minute**:

```text
('whale', 08:30Z, shard 0) -> partition A
('whale', 08:30Z, shard 1) -> partition B
...
('whale', 08:30Z, shard 11) -> partition L

Events are routed to shards via a deterministic algorithm.
```

Suppose there are **12 shards**, and events distribute nearly evenly:

```text
6,000 events/second / 12 shards
  ≈ 500 events/second per shard

Rows per shard/minute:
  500 × 60 = 30,000 rows

Payload per shard/minute:
  30,000 × 600 bytes = 18,000,000 bytes
                     = 18 MB ≈ 17.2 MiB
```

This is an idealized estimate and does **not** mean 12 shards necessarily reside on 12 distinct nodes. Token hashing, topology, replication strategy, and other node workloads still govern actual distribution.

### Choosing a shard based on a stable ID

An example rule:

```text
shard_id = floorMod(stableHash(event_id), 12)

Partition key =
  (tenant_id, minute_bucket, shard_id)
```

`event_id` must represent **a stable identifier for the business event**, kept intact on retries. Never pick a new random shard on each retransmission: if the shard changes, the entire primary key can change and Cassandra will create another row for the same event.

### Writing and reading one shard in CQL

```sql
INSERT INTO tenant_events_by_minute_shard (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, device_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    'reading',
    'temperature=38.1'
);
```

`shard_id = 7` above is merely an **illustrative value**. In production, it must match the defined hash output.

```sql
SELECT occurred_at, event_id, device_id, event_type
FROM tenant_events_by_minute_shard
WHERE tenant_id = 'whale'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

This statement reads **one partition**, not the whole tenant. To get the tenant-wide top 100 within the minute, read all involved shards, **merge results** using the same comparator `occurred_at DESC, event_id ASC`, and take the first 100 rows.

Fetching up to the top 100 rows per shard is sufficient for finding the global top 100 if all streams share the exact ordering and time bounds; however, that can over-read substantial data. At scale, merge page-by-page and bound concurrency.

## 7. Bounding large tenants: buckets do not replace quotas

Increasing partition count helps **distribute data and load**, but does not answer: "How much shared resource is a single tenant allowed to consume?" **Service-layer quotas and load controls** are required.

Never assume Cassandra includes a built-in automatic quota like "at most X bytes/sec per `tenant_id`" when multiple tenants share a table. Having a `tenant_id` column in a schema does not enforce business quotas.

Policies can be defined along several dimensions:

| Quota / Control | Example application policy | Goal |
| --- | --- | --- |
| **Write rate** | Per-tenant token bucket allowing bounded short bursts | Prevent a large tenant from monopolizing write resources. |
| **Concurrent queries** | Limit outstanding requests per tenant | Prevent one tenant from saturating coordinator/replica queues. |
| **Read volume** | Cap time window, page count, and returned bytes | Block overly wide historical scans. |
| **Fan-out** | Cap bucket × shard lookups per API request | Control total partition lookups. |
| **Storage capacity** | Quota on estimated total bytes/rows and retention period | Prevent unbounded growth. |
| **TTL/retention** | Standard tier keeps 7 days, enterprise tier keeps 30 days | Align service tiers with storage cost. |
| **Backfill/burst ingest** | Queueing, throttling, separate budget allocation | Protect interactive queries from degradation. |
| **Alerts and coordination** | Alert on p95/p99, write share, max partition, node skew | Catch oversized tenants before outages occur. |

**Policy numbers must be driven by SLOs and load testing**, as there is no universal row-count or MB limit valid for all Cassandra clusters.

### Per-tenant token bucket for write throttling

Hypothetical policy example:

```text
Standard tenant:
  rate = 50 writes/s
  burst = 200 requests

Enterprise tenant:
  rate = 2,000 writes/s
  burst = 5,000 requests

Special whale tenant:
  rate negotiated for dedicated capacity
  + tailored shards/buckets
  + separate backfill budget
```

This is **not CQL configuration**; it is throttling logic at the API gateway, ingestion service, or traffic-control layer. If multiple instances serve the same tenant, use **shared quota coordination or partitioning**; letting every instance grant the full quota independently can push total load over budget.

When limits are exceeded, the application can return an appropriate error, enqueue, apply backpressure, or request delayed retries. Never use unbounded retries, which amplify incidents.

### Never use a naive static counter to enforce exact quotas

Reading `total_events`, adding 1, and running `UPDATE` on a regular/static column can **lose updates** under concurrent writers. If exact quotas or counters are needed under heavy load, design proper coordination, atomicity, and aggregation mechanisms; do not treat a regular Cassandra cell as a multi-actor atomic counter.

## 8. Distinguishing buckets, shards, and tenant limits

These mechanisms serve different purposes:

| Measure | Primarily solves | Does not automatically solve |
| --- | --- | --- |
| **Domain partition key** `(tenant_id, device_id)` | Separates data across a tenant's entities | One red-hot device. |
| **Time bucket** `(tenant_id, device_id, event_day)` | Bounds historical accumulation over time | Massive traffic during the **current active day**. |
| **Shard** `(tenant_id, minute_bucket, shard_id)` | Creates concurrent partition keys to split active load | Top-N queries without merging; increases read cost. |
| **TTL** | Bounds cell lifetime relative to write time | Splitting an active hot partition or immediately deleting SSTables. |
| **Quota/rate limit** | Caps shared resources consumed by a tenant | Fixing an already-oversized existing partition. |
| **Separate cluster/keyspace** | Improves resource and policy isolation | Fixing a poor partition schema inside that environment. |

An extra-large tenant may require **multiple measures together**: bucketed/sharded schemas, throttled ingestion, fan-out budgets on queries, clear retention, and per-tenant monitoring.

### Changing shard counts requires a versioning policy

If `SHARD_COUNT = 12` changes to `24`, the same `event_id` can map to a different shard. Already-written data **does not automatically move** to new partitions. Readers must know the **configuration applicable to historical data**, or a migration must be executed.

Cases where a large tenant needs a different shard count than standard tenants carry the same risk. Never alter shard counts dynamically based on instantaneous metrics and forget how older buckets are read. A sound design uses a **per-tenant shard policy with effective timestamps/versions**, while keeping read paths defined for data written under prior configurations.

## 9. Querying large tenants: fan-out cost and page management

Suppose `whale` has 12 shards per minute and a dashboard wants to read **24 hours of events**:

```text
24 hours × 60 minutes/hour × 12 shards/minute
= 17,280 partition keys
```

A single API request should never fire 17,280 parallel queries to pull all raw data. When queries have large fan-out, apply:

1. **Narrow the read window** (e.g., max 15 minutes for interactive UI).
2. **Paginate or stream results** with row/byte limits.
3. **Bound concurrency** in the driver and service layer.
4. **Use dedicated summary tables** for daily/monthly reports instead of scanning raw events.
5. **Consider storing data outside Cassandra** for long-range analytics if requirements and volume warrant it.
6. **Return a continuation token/cursor** holding valid query state; multi-shard pagination must track progress per shard or use a stable cursor strategy.

`LIMIT 100` in a shard query only caps results of **that shard**. Cassandra `ORDER BY` does not establish a global order across partitions. To return a tenant-wide top 100, the application must merge by timestamp and ID after receiving streams ordered within each partition.

### Mismatched queries

The `device_events_by_day` table is **not** suitable for running:

```sql
-- Missing device_id and event_day from the composite partition key:
SELECT *
FROM device_events_by_day
WHERE tenant_id = 'whale';
```

Adding `ALLOW FILTERING` may allow Cassandra to accept certain statements, but does not turn them into efficient partition-targeted queries. If an API needs "all events of a tenant," use a dedicated tenant timeline table or aggregation mechanism.

## 10. Tenant isolation: operations and security

There are multiple isolation levels between tenants:

| Model | Advantages | Limitations |
| --- | --- | --- |
| **Shared table/keyspace** with `tenant_id` in primary key | Fewer schemas, easier to manage many tenants, shared resources | Requires application-level tenant authorization; noisy-neighbor risk; service must enforce quotas. |
| **Dedicated keyspace or table per tenant tier/group** | Can separate access permissions and retention/compaction settings at supported resource scopes | Increases schema/metadata count and ops overhead; still shares nodes if on the same cluster. |
| **Dedicated cluster for special tenants** | Clearer isolation of resources, upgrade schedules, and capacity | Higher infrastructure, administration, migration, and monitoring cost. |

No model is universally best. A massive tenant can be **moved to dedicated infrastructure** when shared-cluster quotas and sharding can no longer meet SLOs, though moving to a dedicated cluster will not fix a partition key that creates too much data on that dedicated cluster either.

### Never treat request `tenant_id` as a trusted source

In a Java service receiving a JWT/session:

```text
1. Verify token/session.
2. Determine authorized tenant from trusted claims/relationships.
3. Verify user permissions for the requested device/event.
4. Bind the verified tenant_id into the prepared statement.
5. Enforce per-tenant quotas and query budgets.
6. Emit appropriate audit logs when reading/modifying data.
```

If the system uses one shared Cassandra service account, that account's CQL privileges can be broader than any end user's permissions. Thus, API/service-layer enforcement is mandatory, not optional. When stronger isolation is required, consider separate accounts, keyspaces, or clusters depending on your threat model.

## 11. TTL, compaction, repair, and consistency for large tenants

Buckets and shards address **partition shape**, while storage lifecycle and read/write semantics need their own policies.

### Per-tenant-tier TTL

Example write retaining data for **7 days from write time**:

```sql
INSERT INTO tenant_events_by_minute_shard (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, device_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    'reading',
    'temperature=38.1'
) USING TTL 604800;
```

When tenants have different retention periods, the application can set an appropriate TTL per write operation (if supported by the schema and Cassandra version as needed), rather than assuming the entire table shares one expiration. TTL **does not mean immediate physical deletion**: expired data and tombstones can stay in SSTables until compaction purges them under safety rules.

For **late-arriving events**, a 7-day TTL from write time differs from keeping data until "7 days after event time." If retention policy is anchored to business occurrence time, define TTL calculation and late-event behavior explicitly.

### Compaction and repair

- Time-series data with TTL may be suited for evaluating `TimeWindowCompactionStrategy` when write/TTL patterns fit, though TWCS **never splits** an oversized partition by itself.
- High tombstones, out-of-order historical writes, or updates to old data can raise compaction/read costs.
- Repair synchronizes data state across replicas; it does not move `tenant_id` to another partition or fix skew.
- When deleting data, account for replica repair windows and tombstone safety settings; never shrink `gc_grace_seconds` arbitrarily to purge faster at the risk of deleted data resurrecting.

### Consistency level

Both small and large tenants use the keyspace/query consistency level semantics. Choosing `LOCAL_ONE`, `LOCAL_QUORUM`, or another level affects read/write acknowledgments, latency, and visibility of recent writes; it **does not** alter tokens, partition sizes, or per-tenant throughput limits.

If a large tenant overloads replicas, merely changing consistency level is rarely sufficient. Reduce hotspots, manage concurrency/quotas, inspect topology, and measure in practice.

## 12. Java Driver: tenant-aware routing, buckets, and shards

The Java Driver 4.x example below assumes `CqlSession` is connected to the keyspace containing `tenant_events_by_minute_shard`. `tenantId` has already been **authenticated/authorized at the service layer**, not taken arbitrarily from a caller string.

`eventId` and `occurredAt` must be generated **once per business event**, then preserved across retries.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class TenantEventRepository {
    private static final int SHARD_COUNT = 12;

    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement readOneShard;

    public TenantEventRepository(CqlSession session) {
        this.session = session;

        this.insert = session.prepare(
            "INSERT INTO tenant_events_by_minute_shard " +
            "(tenant_id, minute_bucket, shard_id, occurred_at, " +
            "event_id, device_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        );

        this.readOneShard = session.prepare(
            "SELECT occurred_at, event_id, device_id, event_type " +
            "FROM tenant_events_by_minute_shard " +
            "WHERE tenant_id = ? AND minute_bucket = ? AND shard_id = ? " +
            "AND occurred_at >= ? AND occurred_at < ? LIMIT 100"
        );
    }

    public void writeEvent(
            String verifiedTenantId,
            UUID deviceId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload) {

        // Use UTC event time to determine the bucket.
        Instant minuteBucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);

        // Deterministic hash for the same UUID in Java.
        short shardId = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            verifiedTenantId, minuteBucket, shardId,
            occurredAt, eventId, deviceId, eventType, payload
        ));
    }

    public ResultSet readShard(
            String verifiedTenantId,
            Instant minuteBucket,
            short shardId,
            Instant fromInclusive,
            Instant toExclusive) {

        Instant bucketEnd = minuteBucket.plus(1, ChronoUnit.MINUTES);

        if (shardId < 0 || shardId >= SHARD_COUNT ||
            fromInclusive.isBefore(minuteBucket) ||
            !fromInclusive.isBefore(toExclusive) ||
            toExclusive.isAfter(bucketEnd)) {
            throw new IllegalArgumentException(
                "Invalid read range or shard");
        }

        BoundStatement statement = readOneShard.bind(
            verifiedTenantId, minuteBucket, shardId,
            fromInclusive, toExclusive
        ).setPageSize(50);

        return session.execute(statement);
    }
}
```

In production:

1. **Never take `verifiedTenantId` straight from a URL parameter** without verifying it matches the caller's identity/roles.
2. Always bind full `tenant_id`, `minute_bucket`, and `shard_id` so the query pinpoints one partition key.
3. `UUID.hashCode()` is deterministic in Java for a given UUID, but polyglot systems must specify a uniform byte-level hash algorithm and shard count.
4. `SHARD_COUNT` is part of the storage design. When tenants have distinct shard policies, reads/writes must apply the **policy version** valid for that data.
5. `LIMIT 100` caps results within one shard; `setPageSize(50)` specifies desired rows per driver page. Neither replaces controlling total fan-out queries.
6. Never call `now()` to generate a new clustering `timeuuid` on retries when idempotency is required. Keep the **entire primary key and payload** identical across retries.
7. For high throughput, enforce backpressure, concurrency limits, and tenant budgets outside the repository; never fire unbounded requests just because shards exist.

The example uses synchronous calls for clarity. In large systems, the driver's asynchronous API can improve throughput if concurrency, timeouts, retries, and paging are managed properly.

## 13. Monitoring large tenants and detecting noisy neighbors

You cannot infer an oversized tenant solely from total keyspace bytes. Measure **skew per tenant and per partition**, while tracking node resources:

| Metric | Question to answer |
| --- | --- |
| **Event/write rate per tenant** | Is one tenant taking an abnormal share of total load? |
| **Top read/write partition keys** | Are specific partition keys/tenant buckets receiving excessive traffic? |
| **Partition size/cell count histogram** | Are there outliers in bytes or cell counts per partition? |
| **p95/p99 latency and timeouts by tenant/query** | Is a large tenant dragging up tail latency for small tenants? |
| **Per-node CPU, I/O, GC, network** | Which replicas or coordinators are experiencing hotspots? |
| **SSTables per read, tombstones scanned** | Are slow reads caused by heavy data/tombstones? |
| **Pending compactions, repair/streaming load** | Is background work inflated by a large tenant? |
| **Quota/rate-limit rejects, queue depth** | Are load controls working or getting overwhelmed? |
| **Buckets/shards read per API call** | Is fan-out exceeding the defined read budget? |

Examples of table-level administrative tools, depending on version:

```bash
nodetool tablestats app_ks.tenant_events_by_minute_shard
nodetool tablehistograms app_ks tenant_events_by_minute_shard
```

Those statistics **do not break down by tenant automatically**. To pinpoint the heavy tenant, combine API/ingest telemetry, controlled sampling, and hot-partition statistics supported by your Cassandra version.

Never attach raw tenant/user/event IDs as unbounded metric labels, or the telemetry system itself will hit **high-cardinality label** issues. Monitor tenant tiers, top-N tenants, or controlled aggregations.

Avoid running `SELECT COUNT(*)` on huge partitions or scanning entire tables under load to estimate quotas; counting imposes significant load. Derive size metrics from statistics tools, ingestion pipelines, and controlled reconciliation jobs.

## 14. When a tenant must move off a shared cluster

Not every large tenant needs a dedicated cluster. Base the decision on **resource isolation cost** and product goals.

Consider a dedicated setup when:

- The tenant persistently consumes most CPU, I/O, network, or storage despite bucketing, sharding, and rate limits.
- SLAs, retention, access rules, or data residency differ substantially.
- Repair/backup/restore of one tenant disrupts many other tenants.
- Isolating the tenant costs less than continually scaling the shared cluster and managing noisy-neighbor effects.

### Controlled migration workflow

1. Define the tenant scope, tables, partition keys, and auxiliary data to migrate.
2. Standardize schema, bucket/shard policies, replication strategy, and permissions in the target environment.
3. Migrate historical data with checkpoints, throttled throughput, preserving event IDs, timestamps, and TTL/lifecycle.
4. Use dual-write or replay from an event log if needed, **without assuming atomic transactions across two clusters**.
5. Dual-read verify by key/bucket/shard, checking late data, tombstones, and cutover boundaries.
6. Switch tenant read/write routing, monitoring timeouts, p99, and data completeness.
7. Retire the old path and dispose of legacy data only after confirming zero remaining dependent requests.

Changing shard count, TTL, or consistency settings during migration requires explicit conventions. If readers do not know the legacy policy, they can miss historical data even when it still exists.

## 15. Common mistakes

| Claim | Why is it wrong? | Remediation |
| --- | --- | --- |
| "Adding `tenant_id` to a table provides security isolation." | A column does not enforce end-user access control by itself. | Authenticate/authorize at API layer, use proper roles, consider resource separation. |
| "With many tenants, hashing balances load." | One tenant can dominate requests/bytes. | Measure skew, split by entity/bucket/shard, and throttle load. |
| "`PRIMARY KEY (tenant_id, event_time, event_id)` has three partition keys." | Only `tenant_id` is the partition key; the trailing two are clustering columns. | Check parentheses syntax. |
| "Putting `device_id` in a composite partition key keeps tenant-only queries fast." | Hashing uses the entire tuple; there is no default tenant-prefix scan. | Create a dedicated table/access path. |
| "Daily buckets suffice because each day gets a new partition." | Today's partition can still absorb massive writes. | Use shorter buckets or shards when needed. |
| "12 shards equal 12 nodes, eliminating hotspots." | Replica placements can overlap and load can skew. | Measure nodes/replicas, load-test, and bound concurrency. |
| "Storage quota turns on automatically with `tenant_id`." | Cassandra does not enforce per-column-value business quotas in a shared table. | Enforce quotas at the service/orchestration layer. |
| "Changing `SHARD_COUNT` in code immediately does not affect history." | The same event ID can hash to a different partition. | Versioning and migration policy. |
| "Writing to two tables for the same tenant is an atomic transaction." | Partial failures can occur across tables/partitions. | Idempotent retries, reconciliation, and monitoring. |
| "TTL deletes data physically right at expiration." | Expired data/tombstones still depend on compaction. | Monitor retention and tombstones. |
| "Raising RF/consistency suffices for a hot tenant." | Neither splits the partition key nor enforces quotas. | Fix schema and control workload. |

## 16. Scenario exercise

A SaaS platform has **800 tenants**. One tenant `mega` sends **9,000 events/second**, while the remaining 799 tenants average **4 events/second/tenant**. Each event has a **700-byte payload**. The product supports:

- Q1: fetch the 50 latest events of **one device in a day**.
- Q2: fetch the 100 latest events **across the whole tenant in a minute**.
- Q3: monthly report of total event counts per tenant.
- The large tenant risks raising p99 latency for smaller tenants.

The design team proposes:

```sql
-- A: one partition key for the entire tenant across all time.
PRIMARY KEY (tenant_id, occurred_at, event_id)

-- B: partition by device and day.
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    occurred_at, event_id
)

-- C: partition by tenant, minute, and shard.
PRIMARY KEY (
    (tenant_id, minute_bucket, shard_id),
    occurred_at, event_id
)
```

**Questions:**

1. In A, is `tenant_id` the partition key or a component of the clustering key?
2. Roughly what percentage of total write traffic does tenant `mega` represent?
3. Under A, how many rows and how many MB of logical payload does the large tenant produce in one minute?
4. Does B best suit Q1 or Q2?
5. With C using **18 shards** and ideal distribution, how many writes/sec/shard does it receive?
6. When reading the tenant-wide top 100 using C, can you query only shard 0?
7. Should Q3 scan every minute/shard partition across an entire month on each dashboard open?
8. Why are per-tenant quotas and sharding two solutions with different goals?
9. If the application trusts `tenant_id` sent by the client without checking permissions, what risk arises?
10. How does changing shard count from 18 to 36 without versioning affect already-written data?

**Answers with explanations:**

1. `tenant_id` is a **simple partition key**; `occurred_at` and `event_id` are clustering columns.
2. Total `9,000 + 799 × 4 = 12,196 writes/second`. Tenant `mega` accounts for `9,000/12,196 ≈ 73.8%` of write load.
3. `9,000 × 60 = 540,000 rows/minute`; `540,000 × 700 = 378,000,000 bytes = 378 MB ≈ 360.5 MiB` payload, excluding overhead/replicas.
4. **B suits Q1**; because Q2 does not know a specific `device_id`, another tenant timeline access path is required.
5. `9,000 / 18 = 500 writes/second/shard` under ideal assumptions, not necessarily mapping to 18 distinct nodes or replica sets.
6. **No.** You must read all relevant shards, merge by timestamp/ID order, and take the top 100.
7. Generally **no**. Q3 fits a summary table, analytics engine, or dedicated reporting pipeline with clearly defined accuracy and latency.
8. **Sharding spreads** writes of a bucket across multiple partition keys; **quotas control** total resources a tenant is allowed to consume. Both mechanisms must work together.
9. **Unauthorized cross-tenant data access or manipulation** can occur; a tenant ID column in a schema does not substitute for authorization.
10. Old events stay in shards computed with hash mod 18; readers using 36 can look in the wrong partitions, or retries can write the same event under a new key. Policy versioning/migration is needed.

## 17. Key takeaways

- In multi-tenancy, `tenant_id` is a **business-domain identifier**, yet **should not automatically be used as the sole partition key** for continuously growing data of large tenants.
- Composite partition keys such as `(tenant_id, device_id, event_day)` split data by entity and time; one tenant gets many partitions instead of one giant partition.
- Queries must **supply all partition key components** or use a separate access path. A composite key does not create a default tenant-prefix scan index.
- Very large tenants may simultaneously need **time bucketing, sharding, TTL, and quota/rate-limit policies**; each addresses a distinct root cause.
- Sharding increases read fan-out and requires **deterministic routing algorithms**, policy versioning, and result merging.
- `tenant_id` **does not automatically enforce authorization or resource isolation**. The service layer must enforce tenant-aware authorization, quotas, and backpressure.
- Replication, consistency levels, compaction, and repair affect durability, performance, and operations, yet **do not automatically split a hot partition or cap an oversized tenant**.
- Deciding between keeping a tenant shared or moving to a dedicated cluster must rely on **SLOs, skew, operational cost, and isolation requirements**, backed by real metrics.

Proper tenant key design lets Cassandra serve many customers on a single distributed architecture while controlling partitions, latency, and access boundaries. As tenant count and usage grow, the data model, quota policies, replica operations, and Java applications must all follow one clear routing and bounding discipline.
