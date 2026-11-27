# Hot Keys, Whale Tenants, and Skew Risk

Splitting data into multiple **partitions** or **shards** does not guarantee the system is automatically balanced. If one customer generates the majority of transactions, or thousands of concurrent requests update the same record simultaneously, one partition can overload while others sit idle. This is the problem of **hot keys**, **whale tenants**, and **data/workload skew**.

A common example in multi-tenant SaaS platforms: the system picks **`tenant_id`** as the distribution key so all data for one customer lives close together. That keeps intra-tenant queries and transactions simple. However, when a single tenant accounts for 40% of traffic, **`HASH(tenant_id)`** still routes 100% of that tenant's traffic to the same location. Increasing shard count from 8 to 32 will not resolve the bottleneck if all 40% still land on one shard.

This lesson belongs to the **Distribution and Partitioning** chapter of **DATABASE_DATA_MODELING**. Its goal is to connect business requirements to grain, keys, indexes, physical schemas, and distribution strategies; identify hotspot types; measure skew; and choose among changing distribution keys, bucketing, isolating large tenants, optimizing access paths, or custom routing. These choices must be verified by **data correctness** and **realistic load**, not merely by the number of partitions created.

## 1. Concepts to Distinguish

### 1.1. Partition, Shard, and Partition Key

| Concept | Meaning | Example |
| --- | --- | --- |
| **Partition** | A subset of a table or dataset defined by a partitioning rule | PostgreSQL partitions by month or by hash |
| **Sharding** | Distributing data across independently scalable storage units/nodes or resource pools | Tenant A's orders on shard 1, tenant B's on shard 2 |
| **Partition key / shard key** | Attribute(s) used to determine where data is placed | `tenant_id`, `order_id`, `occurred_at`, or composite keys |
| **Logical shard** | Logical routing unit that can map to physical machines | 64 logical buckets across 8 storage clusters |
| **Physical shard/node** | Where CPU, RAM, I/O, and network resources are actually consumed | A server hosting multiple logical buckets |
| **Rebalancing** | Moving or reassigning data/load between units | Moving a large tenant's bucket to another machine group |

**Critical warning:** creating 8 partitions inside **one** PostgreSQL instance **does not create 8 servers** or multiply hardware capacity by eight. Local partitioning aids data management and can improve some query plans; true sharding requires routing and physical resource distribution.

### 1.2. Hot Key, Hot Partition, and Whale Tenant

- **Hot key:** a single key or record receiving excessive reads/writes. For example, every transaction of tenant A updates row **`tenant_usage(tenant_id = A)`**.
- **Hot partition:** a partition/shard experiencing far higher traffic, storage, CPU, or I/O than others. It can heat up because of **one** huge key or **many** keys that happen to land together.
- **Whale tenant:** a customer whose traffic or data volume far exceeds typical customers. "Too large" is relative to system limits: huge storage, QPS, connection counts, or heavy queries can all cause trouble.
- **Data skew:** uneven distribution of **row counts or storage bytes**.
- **Traffic/workload skew:** uneven distribution of **requests, CPU, IOPS, lock duration, or bandwidth**.

A shard holding 1 TB of rarely read historical data may not be hot, whereas a shard holding 20 GB of active data receiving 50,000 updates/second is saturated. Therefore, **data skew and workload skew are not the same metric**.

### 1.3. A Hot Key Is Not Always a Hot Shard

Consider:

~~~sql
UPDATE tenant_usage
SET events_processed = events_processed + 1
WHERE tenant_id = 42;
~~~

If row **`tenant_id = 42`** is updated concurrently by many transactions, those transactions must wait on row locks or write contention. Even if the table spans many shards, **a single row remains a serialization point**. Splitting the events table into daily partitions will not fix contention on the `tenant_usage` row.

To fix the right problem, pinpoint whether the hotspot sits at the **record**, **query key**, **index page**, **partition**, or **physical machine**; each requires a different remedy.

## 2. Quantitative Example: 8 Shards and One Customer with 40%

Suppose a platform has **100 tenants** and receives **1,000,000 events/day**:

- Tenant **W** generates **400,000 events/day**.
- The **remaining 99 tenants** together generate **600,000 events/day**, averaging roughly **6,061 events/day per tenant**.
- All events are assigned to **8 shards** via **`HASH(tenant_id)`**.

Under ideal uniform balance:

\[
\text{Average load per shard}
= \frac{1,000,000}{8}
= 125,000\ \text{events/day}.
\]

Yet all 400,000 events of W land on **one shard**. Hence:

\[
\text{Load on W's shard} \ge 400,000
\quad \Rightarrow \quad
\frac{\text{hot shard load}}{\text{average load}} \ge 3.2.
\]

That **3.2x** ratio is only a **lower bound**; other tenants hashing to the same shard push it higher. Adding shards lowers the odds of small tenants colliding onto it, but **never splits W's traffic** as long as you hash solely by `tenant_id`.

### 2.1. Data Volume Does Not Equal Processing Load

Spread evenly, 1,000,000 events/day averages only ~11.6 events/second, yet in reality 70% can arrive during peak hours. Tenant W might also run heavy aggregations during that same window. Therefore, **rows/day** does not directly reflect **CPU, I/O, or latency**.

A load model must consider:

~~~text
Write load   ≈ write operations × cost per operation
Read load    ≈ queries × rows scanned × query cost
Lock load    ≈ contention on the same row / resource
Storage load ≈ data bytes + indexes + versions/WAL
~~~

This is a conceptual framework for where load originates, **not an exact capacity formula**. Decisions require measuring real workloads and query plans.

### 2.2. Distribution Diagram

~~~mermaid
flowchart LR
    EVENTS["1,000,000 events/day"]
    ROUTER["Routing HASH(tenant_id)"]
    WHALE["Tenant W: 400,000/day"]
    SMALL["99 tenants: 600,000/day"]
    HOT["W's shard: at least 400,000/day"]
    REST["Remaining 7 shards and other tenants"]
    EVENTS --> ROUTER
    WHALE --> ROUTER
    SMALL --> ROUTER
    ROUTER --> HOT
    ROUTER --> REST
~~~

The diagram illustrates the **distribution principle**, not the exact output of any specific hash function.

## 3. Root Causes of Distribution Skew

### 3.1. Low-Cardinality Keys

If partitioning by **`status`** containing only PENDING, PAID, CANCELLED, data cannot naturally split across dozens of independent parts. In practice, status values also skew heavily toward one state. Picking a low-cardinality field just because it is human-readable routinely creates hotspots.

### 3.2. Time-Range Partitioning with Writes Concentrated on the Present

With monthly partitions:

~~~text
orders_2026_09
orders_2026_10
orders_2026_11  <- nearly all new writes in November
~~~

Time-based partitions are convenient for periodic queries and purging expired data, yet **all current writes can pile into this month's partition**. If partitions share the same host, contention can also hit shared resources or hot index pages, not just partition row counts.

A B-tree index on a monotonically increasing key like **`created_at`** or sequential IDs can also concentrate writes onto one edge of the index. You cannot assume every ascending key bottlenecks; actual impact depends on engine, index structure, write rate, and concurrency control.

### 3.3. One Oversized Tenant

When the key is **`tenant_id`**, queries enjoy locality:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

However, every order, event, or request for tenant 42 funnels to the same shard. One customer onboarding a massive contract, running bulk imports, or firing continuous reports can degrade smaller tenants on the same shard: the **noisy neighbor** effect.

### 3.4. One Heavily Read Key

A trending product or livestream sharing a single **`product_id`** may receive tens of thousands of reads/second. Evenly hashing other `product_id` values does not split requests targeting that **specific `product_id`**.

If the data is cacheable or read-replicable, **caching/read replicas** often solve this much more effectively than changing the key model. Evaluate how fast the data mutates and what consistency the screen requires.

### 3.5. Hotspots from Updating a Shared Aggregate Record

For example, every event increments a counter:

~~~text
tenant_usage(tenant_id, total_events)
~~~

Row **`tenant_id = 42`** is updated continuously regardless of how evenly events are partitioned across the events table. This bottleneck is **row-level write contention**, requiring a different counter design or aggregation pipeline.

### 3.6. Hash Collisions and Imbalance Even Without Whales

A hash function maps **distinct key values** onto a finite number of shards; multiple keys can still land on the same shard. When key count is small, variance across shards is normal. A good hash lowers expected skew across many similarly loaded keys, **but never promises balance** when key weights vary wildly.

## 4. Questions to Answer Before Choosing a Shard Key

A good distribution key needs more than high cardinality. It must support **your most critical queries and transactions**.

| Question | Why It Matters |
| --- | --- |
| What entity/event does one row represent (*grain*)? | Avoid confusing a tenant, an order, an event, and a line item |
| Do writes mostly append new records or update the same record? | Splitting new events does not fix a hot counter row |
| Which columns do primary queries filter on? | Picking a key absent from queries causes scatter-gather |
| Do transactions span multiple rows within one tenant? | Keeping related rows close reduces distributed transactions |
| Does the key have high cardinality and balanced load? | Avoid low cardinality and whale keys |
| Which tenants currently dominate storage or QPS? | Decides which tenants must be sub-split or isolated |
| Are system-wide uniqueness constraints required? | Cross-shard UNIQUE/FK constraints are much harder |
| Must any data stay within specific geographic boundaries? | Residency and compliance may constrain shard placement |
| How does data age and what is its retention policy? | May require time partitioning independent of the shard key |
| How will you rebalance if a tenant suddenly spikes? | Hard-to-change keys cause painful migrations |

**Time partitioning, tenant hashing, and placing tenants onto nodes are three composable decisions**, not mutually exclusive alternatives.

## 5. Detect Skew with Metrics, Not Guesses from Diagrams

Evaluation must combine **row/storage distribution** with **access and latency distribution over time**. Looking only at which table is biggest will miss active bottlenecks.

### 5.1. Metrics to Collect

| Metric | Breakdown Dimension | Risk Signal |
| --- | --- | --- |
| Row count, data bytes, index bytes | By tenant, partition, node | One tenant or partition vastly outweighs others |
| Writes/second and reads/second | By shard, tenant, API, time window | One shard absorbs most load during peak hours |
| CPU, IOPS, bandwidth, queue depth | By physical node | One node runs hot while others sit idle |
| Lock wait time, deadlocks, retries | By table, query key, operation | Contention on the same counter row or index |
| p50/p95/p99 latency | By API and tenant, not just global | One tenant suffers high tail latency or timeouts |
| Query rows scanned vs. returned | By query type | Large-tenant queries scan excessive rows |
| Cache hit/miss, replication lag | By partition/replica | Cache miss storms or lagging read replicas |
| Rebalance backlog, storage growth | By shard | Shard nears capacity while migration falls behind |

**System-wide averages hide problems.** If 99 small tenants are fast and 1 large tenant times out, global p95 may still look healthy. Build dashboards or tracing by tenant, shard, time window, and operation type—while keeping PII and sensitive identifiers out of unrestricted monitoring tools.

### 5.2. Analyzing Data by Tenant

Suppose we have a relational events table:

~~~text
tenant_events(
    tenant_id,
    event_id,
    order_id,
    occurred_at,
    payload
)
~~~

Count rows and date bounds per tenant:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS event_rows,
    MIN(occurred_at) AS first_event_at,
    MAX(occurred_at) AS last_event_at
FROM tenant_events
GROUP BY tenant_id
ORDER BY event_rows DESC
LIMIT 20;
~~~

To see which customers drove recent writes in a time window:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS events_last_day
FROM tenant_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-21 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-22 00:00:00+07'
GROUP BY tenant_id
ORDER BY events_last_day DESC;
~~~

The fixed date interval here **merely illustrates a one-day window in +07**, not an automatic "today" query. In recurring reports, parameterize start/end timestamps using an agreed timezone.

Compute each tenant's share within the dataset:

~~~sql
WITH per_tenant AS (
    SELECT tenant_id, COUNT(*) AS event_count
    FROM tenant_events
    GROUP BY tenant_id
)
SELECT
    tenant_id,
    event_count,
    ROUND(
        100.0 * event_count / NULLIF(SUM(event_count) OVER (), 0),
        2
    ) AS pct_of_total
FROM per_tenant
ORDER BY event_count DESC
LIMIT 20;
~~~

`NULLIF(..., 0)` guards against division by zero if the table is empty; on an empty set, the query returns zero rows. This measures **record share**, not instantaneous QPS, CPU load, or lock contention.

### 5.3. Inspecting Distribution Across PostgreSQL Partitions

For a partitioned PostgreSQL table queried via the parent:

~~~sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS event_rows
FROM tenant_events
GROUP BY tableoid
ORDER BY event_rows DESC;
~~~

**`tableoid`** identifies the actual physical partition table holding each row. On an unpartitioned table, only one table appears. Counting rows **can be expensive on huge tables**; in production, prefer approximate catalog stats, telemetry, or off-peak execution as appropriate.

Skew ratio between the largest partition and the average of non-empty partitions:

~~~sql
WITH partition_rows AS (
    SELECT tableoid, COUNT(*)::numeric AS row_count
    FROM tenant_events
    GROUP BY tableoid
)
SELECT
    MAX(row_count) AS max_rows,
    ROUND(AVG(row_count), 1) AS avg_rows_nonempty,
    ROUND(MAX(row_count) / NULLIF(AVG(row_count), 0), 2)
        AS max_to_avg_nonempty
FROM partition_rows;
~~~

**Limitation:** this query **excludes empty partitions** from the average; to compare against all configured partitions, pull the full partition list from catalog metadata and `LEFT JOIN` counts. It also measures **row count**, not bytes, QPS, or node capacity.

### 5.4. Hotspot Signals Invisible to `COUNT(*)`

A **`tenant_usage`** table with just one row per tenant can still suffer severe contention if every worker updates that single row. Check:

- Which transactions are waiting on row locks, lock wait durations, and retries.
- Number of `UPDATE`s hitting that key within a short window.
- Dedicated p95/p99 latency for counter `UPDATE`s.
- WAL/flush times, CPU, and shared node resources.

**Never infer hot keys solely from per-tenant row counts.** One tenant with hundreds of millions of events may have zero hot counters; another tenant with 100 rows receiving thousands of `UPDATE`s/second on one record can be the primary bottleneck.

## 6. Testing `HASH(tenant_id)` Partitioning in PostgreSQL

The example below illustrates **local partitioning** and the inherent behavior of a tenant key. It **does not build a truly distributed sharded system**.

### 6.1. Creating the Table, Key, and 8 Partitions

~~~sql
CREATE TABLE tenant_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_events_p0 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 0);
CREATE TABLE tenant_events_p1 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 1);
CREATE TABLE tenant_events_p2 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 2);
CREATE TABLE tenant_events_p3 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 3);
CREATE TABLE tenant_events_p4 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 4);
CREATE TABLE tenant_events_p5 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 5);
CREATE TABLE tenant_events_p6 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 6);
CREATE TABLE tenant_events_p7 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 7);

CREATE INDEX idx_tenant_events_tenant_time
ON tenant_events (tenant_id, occurred_at DESC);
~~~

In PostgreSQL, **PRIMARY KEY/UNIQUE constraints on a partitioned table must obey partition-key rules**; here the primary key `(tenant_id, event_id)` includes `tenant_id`. If business rules require **`event_id` to be globally unique regardless of `tenant_id`**, this composite key **does not automatically enforce** global `event_id` uniqueness. Design ID generation and enforcement accordingly.

Indexes declared on the parent partitioned table are maintained across the corresponding child partitions—they are not an independent "global index" enforcing uniqueness across arbitrary non-partition-key columns.

### 6.2. Loading Explicitly Skewed Synthetic Data

To observe results faster than on a multi-million-row table, insert **10,000 events**:

- Tenant 42 accounts for **4,000 events (40%)**.
- 99 tenants numbered 100–198 split **6,000 events**.

~~~sql
INSERT INTO tenant_events
    (tenant_id, event_id, order_id, occurred_at, payload)
SELECT
    CASE
        WHEN i <= 4000 THEN 42
        ELSE 100 + ((i - 4001) % 99)
    END AS tenant_id,
    i::BIGINT AS event_id,
    ((i - 1) / 5 + 1)::BIGINT AS order_id,
    TIMESTAMPTZ '2026-11-21 00:00:00+07'
        + (i * INTERVAL '1 second') AS occurred_at,
    jsonb_build_object('event_type', 'ORDER_EVENT') AS payload
FROM generate_series(1, 10000) AS g(i);
~~~

Verify:

~~~sql
SELECT
    COUNT(*) AS all_events,
    COUNT(*) FILTER (WHERE tenant_id = 42) AS whale_events
FROM tenant_events;
-- all_events = 10000; whale_events = 4000.
~~~

In this dataset, the other tenants have ~60–61 events each. Regardless of which partition the hash function picks for tenant 42, **all 4,000 rows of tenant 42 must reside in one partition** because the partition key is solely `tenant_id`.

Thus the average across 8 partitions is **1,250 rows**, while the whale's partition holds **at least 4,000 rows**—at least **3.2x the average**. Next, run the queries from Section 5 to inspect the **actual** distribution across partitions.

### 6.3. Partition Pruning Helps, But Does Not Rescue the Whale

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, order_id, occurred_at
FROM tenant_events
WHERE tenant_id = 42
ORDER BY occurred_at DESC
LIMIT 20;
~~~

When the planner has sufficient information and matching predicates, PostgreSQL can **prune partitions** to touch only the partition holding tenant 42 rather than all eight. That is the benefit of using `tenant_id` as the partition key.

At the same time, queries for tenant 42 still concentrate on **one partition** and, in this single-host PostgreSQL setup, still share that machine's resources. **Partition pruning** narrows query scope; it **does not automatically distribute a large tenant across machines**.

**Operational note:** `EXPLAIN ANALYZE` actually executes the query. Run it only on test data or with safe limits when queries could impose heavy load.

### 6.4. Adding More Partitions Does Not Split a Whale Key

Scaling from 8 to more hash partitions leaves tenant 42 **bound to one `tenant_id` value**. That tenant's rows may move to a different partition under the new modulus, yet **they are never split apart merely by adding partitions**.

Changing hash partition counts also requires a **data migration plan suited to the DBMS**; never assume altering `MODULUS` on existing partitions scales instantaneously without moving or validating data.

## 7. Diagnose Before Picking a Fix

| Observed Symptom | Likely Cause | First Measures to Try |
| --- | --- | --- |
| One record receives continuous `UPDATE`s, high lock waits | Hot row/counter | Batching, counter buckets, redesign transaction invariants |
| One tenant dominates inserts/queries on a shard | Whale tenant | Isolate tenant or split tenant data by bucket/order |
| Nearly all writes land in current month's partition | Temporal hot partition | Combine time with hash/buckets depending on queries and retention |
| One key is read repetitively at extreme rates | Read hot key | Caching, read replicas, eliminate redundant queries |
| One tenant runs reports scanning millions of events | Query hotspot | Proper indexes, keyset pagination, aggregates/read models |
| Similar tenants yet one shard runs hot | Hash collisions, physical placement, uneven routing | Move virtual shards or rebalance routing |
| p99 spikes during data ingestion windows | Bulk ingestion resource contention | Batching, queuing, rate limiting, workload isolation |
| One machine runs hot while local partitions look even | Shared physical resources | Scale hardware or move to independent nodes/clusters |

You do not necessarily need to **change the shard key** when the culprit is an unindexed SQL query or an API issuing redundant loops. Changing shard keys entails heavy migrations and query impact, so prove lighter fixes are insufficient first.

## 8. Splitting a Whale Tenant with Composite Keys or Buckets

When a tenant outgrows one shard, **`tenant_id` alone can no longer distribute write load**. One approach is choosing a **sub-unit with higher cardinality**, such as:

~~~text
tenant_id + order_id
tenant_id + customer_id
tenant_id + entity_bucket
tenant_id + time_bucket + hash_bucket
~~~

Do not pick the second field arbitrarily: it must align with **which queries and transactions need to stay co-located**.

### 8.1. Keeping One Order's Data Together

Suppose a tenant has hundreds of thousands of orders. Each order emits multiple events; events of the same order must be processed in sequence and queried together.

Choose:

~~~text
bucket = order_id MOD 4

Logical distribution by (tenant_id, bucket).
~~~

Then:

- Different orders land in different buckets, allowing the whale tenant to **spread across up to 4 logical units**.
- Events sharing the **same `order_id`** remain in the **same bucket**, keeping per-order reads/writes local.
- Querying **all orders of the tenant** must gather from all four buckets and merge/sort.
- If a **single order** becomes a hotspot, splitting by `order_id` still keeps all load of that order in one bucket. A hot single order needs a different mitigation.

### 8.2. Verifiable PostgreSQL Bucket Schema

To avoid confusing **single-server partitioning** with multi-machine sharding, this example only models **4 logical partitions** by bucket. A separate distributed routing layer could map `(tenant_id, bucket)` pairs to physical nodes, though this DDL **does not implement that routing**.

~~~sql
CREATE TABLE tenant_order_events_bucketed (
    tenant_id BIGINT NOT NULL,
    bucket SMALLINT NOT NULL CHECK (bucket BETWEEN 0 AND 3),
    order_id BIGINT NOT NULL CHECK (order_id >= 0),
    event_seq INTEGER NOT NULL CHECK (event_seq > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    CHECK (bucket = (order_id % 4)::SMALLINT),
    PRIMARY KEY (tenant_id, bucket, order_id, event_seq)
) PARTITION BY LIST (bucket);

CREATE TABLE tenant_order_events_b0
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (0);
CREATE TABLE tenant_order_events_b1
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (1);
CREATE TABLE tenant_order_events_b2
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (2);
CREATE TABLE tenant_order_events_b3
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (3);

CREATE INDEX idx_bucketed_tenant_time
ON tenant_order_events_bucketed (tenant_id, occurred_at DESC);
~~~

**`event_seq`** is assumed unique **within one order**. Thus `(tenant_id, bucket, order_id, event_seq)` matches the exact grain of **one event of one order**. In production, if events carry an independent **`source_event_id`**, add source-level idempotency and uniqueness rules.

Test two orders of the same tenant falling into different buckets:

~~~sql
INSERT INTO tenant_order_events_bucketed
    (tenant_id, bucket, order_id, event_seq, occurred_at, payload)
VALUES
    (42, 0, 100, 1, TIMESTAMPTZ '2026-11-21 09:00:00+07',
     '{"type":"ORDER_CREATED"}'),
    (42, 1, 101, 1, TIMESTAMPTZ '2026-11-21 09:01:00+07',
     '{"type":"ORDER_CREATED"}'),
    (42, 0, 100, 2, TIMESTAMPTZ '2026-11-21 09:02:00+07',
     '{"type":"ORDER_CONFIRMED"}');
~~~

Attempting to insert **`order_id = 100` with `bucket = 1`** is rejected by the **`CHECK`** constraint. This prevents the application from accidentally routing the same order to inconsistent buckets.

Fetch data for a single order:

~~~sql
SELECT event_seq, occurred_at, payload
FROM tenant_order_events_bucketed
WHERE tenant_id = 42
  AND bucket = (100 % 4)
  AND order_id = 100
ORDER BY event_seq;
~~~

Because the query includes `bucket`, PostgreSQL can prune directly to the right partition. In a distributed system, the router likewise has **`(tenant_id, bucket)`** if both layers share the verified mapping rule.

Fetch the 50 newest events across the whole tenant:

~~~sql
SELECT order_id, event_seq, occurred_at, payload
FROM tenant_order_events_bucketed
WHERE tenant_id = 42
ORDER BY occurred_at DESC, order_id DESC, event_seq DESC
LIMIT 50;
~~~

This query **may have to read all four buckets** and combine results. Across multiple nodes, the distributed system needs **fan-out, result merging, and pagination**. At high traffic, a dedicated read model or summary table may be needed for the "tenant latest activity" screen.

### 8.3. Bucketing by `order_id` vs. Bucketing by `event_id`

| Bucket Calculation | What Stays Co-Located | Drawback |
| --- | --- | --- |
| **`order_id MOD B`** | Events of the same order | A single ultra-hot order is not split |
| **`event_id MOD B`** | Individual events split by ID | Events of one order scatter; reading one order fans out |
| **`HASH(tenant_id, order_id)`** | Different orders can go to different shards | Tenant-wide queries usually scatter |
| **`tenant_id`** | All tenant data stays together | Whale tenant still has only one routing target |
| **`occurred_at` by time** | Period data stays close | Current writes still pile into the open partition |

Using **B buckets** does not mean whale load automatically drops by **B×**: orders may have uneven sizes, buckets may map to the same node, and tenant-wide queries can touch all buckets.

### 8.4. Never Hardcode Physical Shard Counts Into Data

If application code computes **`bucket = hash(key) % 8`** and assumes bucket 0 is node A, scaling to 16 nodes forces changing routing keys or moving large volumes of data.

It is generally far cleaner to decouple:

~~~text
Business key → logical bucket → placement map → physical node
~~~

Logical buckets stay stable while the **placement map** reassigns where buckets live. **Virtual shards/buckets** or consistent hashing reduce rebalancing churn in some systems, yet you still need migration plans, configuration control, and rollback. **Consistent hashing cannot cure a hot key whose load exceeds one unit's capacity** if the entire key remains on one unit.

## 9. Hot Rows: Bucketing Counters and Protecting Correctness

Distributing the events table does not eliminate contention on a shared summary row:

~~~sql
CREATE TABLE tenant_usage (
    tenant_id BIGINT PRIMARY KEY,
    total_events BIGINT NOT NULL DEFAULT 0
);

-- Many concurrent workers run:
UPDATE tenant_usage
SET total_events = total_events + 1
WHERE tenant_id = 42;
~~~

One option for **analytical, telemetry, or aggregatable counters** is splitting the total across multiple **counter buckets**.

### 9.1. Sharded Counter Schema

~~~sql
CREATE TABLE tenant_counter_buckets (
    tenant_id BIGINT NOT NULL,
    bucket SMALLINT NOT NULL CHECK (bucket BETWEEN 0 AND 15),
    event_count BIGINT NOT NULL DEFAULT 0
        CHECK (event_count >= 0),
    PRIMARY KEY (tenant_id, bucket)
);
~~~

Each new event routes to a bucket via a deterministic function of its event ID or controlled allocation, updating a single row:

~~~sql
INSERT INTO tenant_counter_buckets
    (tenant_id, bucket, event_count)
VALUES (42, 7, 1)
ON CONFLICT (tenant_id, bucket)
DO UPDATE SET
    event_count = tenant_counter_buckets.event_count + 1;
~~~

Total:

~~~sql
SELECT
    tenant_id,
    SUM(event_count) AS total_events
FROM tenant_counter_buckets
WHERE tenant_id = 42
GROUP BY tenant_id;
~~~

If the 16 buckets are chosen evenly, updates contend across **multiple rows instead of one row**. In return, reading the total must sum across rows, and you need a deterministic bucket rule and replay policy when jobs fail.

### 9.2. What Counter Buckets Do NOT Guarantee Automatically

- **Idempotency:** retrying the same event twice can increment the counter twice. You need event identifiers and deduplication rules—ideally inserting the event and incrementing the counter inside the same transaction where supported.
- **Instantaneous consistency:** summing buckets while concurrent updates run may require snapshot transactions or appropriate read isolation for a consistent view.
- **Strict hard caps:** if a tenant is capped at **at most 10,000 events**, two concurrent streams reading the sum and writing to two different buckets can **both exceed the quota**. Hard quotas require tightly coordinated reservations or equivalent transactional constraints.
- **Reversals/adjustments:** counters do not explain cancellations, refunds, or historical corrections; define reversal events and compensating flows.
- **Physical shard contention:** 16 counter rows can still live on the same machine if the schema lacks physical distribution; bucketing rows does not magically add hardware.

When **exact auditing and recomputability** are required, store **append-only event facts with unique keys**, then aggregate or build summary tables via batch/streaming. For strict quotas, design explicit resource reservation; never use an eventual counter to enforce hard limits.

## 10. Isolating Whale Tenants: Tenant Placement and Dedicated Shards

Not every whale needs to be split across dozens of buckets. If customer W has **millions of transactions but mostly runs tenant-wide queries**, bucketing forces every dashboard to fan out, increasing complexity and network cost. Another option is **moving W onto a dedicated shard or cluster**.

### 10.1. When Dedicated Shards Help

- A large customer needs predictable CPU/RAM/IOPS and a distinct SLA from the rest.
- Workload is heavy on intra-tenant queries/aggregations requiring locality.
- Customer data has specific geographic residency or isolation mandates.
- You must eliminate **noisy neighbor** interference between large and small tenants.
- Volume is large, yet still **fits within the capacity of one dedicated cluster**.

Dedicated shards **do not** solve internal hotspots within the tenant: a hot counter row still contends, and an unindexed query stays slow. Isolation solely prevents cross-tenant interference and allows dedicated resource sizing.

### 10.2. Tenant Placement Directory

A coordination service can store:

~~~text
tenant_placement(
    tenant_id,
    placement_group,
    routing_version,
    migration_state
)

tenant 42  -> dedicated_group_W
tenant 101 -> shared_group_2
tenant 102 -> shared_group_5
~~~

Applications **look up placement** to route instead of computing an unchangeable static hash on tenant ID. Routing records should be cached with bounded lifetimes and mutated via consistent workflows; **`routing_version`** detects clients holding stale routes.

Topology:

~~~mermaid
flowchart TD
    REQ["Request with tenant_id"]
    DIRECTORY["Tenant placement directory"]
    SHARED1[("Shared group A")]
    SHARED2[("Shared group B")]
    WHALE[("Dedicated group W")]
    REQ --> DIRECTORY
    DIRECTORY -->|"small tenants"| SHARED1
    DIRECTORY -->|"small tenants"| SHARED2
    DIRECTORY -->|"tenant W"| WHALE
~~~

This is a logical architecture diagram. Actual implementation depends on what routing, database, and data-movement mechanisms the platform supports.

### 10.3. Tenant Migration Demands Consistency Control

Moving a tenant across shards typically involves:

1. **Scoping all data:** orders, line items, events, indexes, attachments, caches, reports, and related references.
2. **Preparing the target:** schemas, migration versions, keys, constraints, and settings on the new group.
3. **Initial data copy:** via a consistent snapshot or engine-supported strategy.
4. **Catching up changes:** CDC/log-based replication or coordinated writes so nothing occurring during copy is lost.
5. **Reconciliation:** row counts, keys, transaction totals, checksums, or set comparisons per scope.
6. **Controlled routing switch:** update placement version, drain in-flight requests, and prevent uncoordinated dual authoritative writes.
7. **Monitoring and rollback:** watch error rates, latency, lag, and rollback paths; never purge the source prematurely before verification passes.

**Never describe dual-write ("write to both places") as an automatic guarantee of exactly-once delivery.** If one write fails, the two stores diverge. You need a strict cutover protocol, idempotency, ordering handling, and recovery procedures. Tenant migration is a high-risk data operation—never merely updating one row in a routing table.

## 11. Handling Read Hot Keys Without Distorting the Data Model

Some hot keys are predominantly **read-heavy** rather than write-contended—for instance, a popular product catalog entry or a tenant's public configuration.

### 11.1. Caching, Read Replicas, and Pre-Aggregation

| Measure | Appropriate When | Must Control |
| --- | --- | --- |
| **Application or distributed cache** | Repeated reads tolerating short-lived cached values | TTL, invalidation, stampede, tenant-scoped cache keys |
| **CDN/edge cache** | Public, slowly changing content | Privacy, cache-control, never mix tenant data |
| **Read replicas** | High read load tolerating replication delay | Replication lag, read-after-write consistency, read routing |
| **Materialized views / read models** | Repeated heavy aggregations or dashboards | Refresh cadence, late data, drift from source of truth |
| **Eliminate redundant queries** | Chatty APIs or N+1 queries | Batching, pagination, query plans, data loading |

A cache key missing `tenant_id` can **leak data across tenants** even when the database itself is cleanly partitioned. In multi-tenant systems, cache key scoping, authorization, and data-sharing policies are core parts of the data design.

### 11.2. Cache Stampede Scenarios

If 10,000 requests read the same record, simultaneous cache expiration can slam all 10,000 requests straight into the database. Strategies like **staggered TTLs**, **single-flight/request coalescing**, **stale-while-revalidate**, or proactive cache warming mitigate spikes when consistency requirements permit.

Never rely on **stale** data for critical write decisions like deducting funds or checking remaining quota without validating against the authoritative source via a proper protocol.

## 12. Distribution Design Must Protect Keys, Relationships, and Transactions

### 12.1. Per-Tenant Uniqueness vs. System-Wide Uniqueness

Suppose each tenant issues its own **`order_number = "001"`**. Reasonable schema:

~~~sql
CREATE TABLE orders_multi_tenant (
    tenant_id BIGINT NOT NULL,
    order_number VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_number)
);
~~~

Here **`(tenant_id, order_number)`** is the unique business key; **`order_number` alone is not unique**. When distributed by `tenant_id`, the system can enforce pair uniqueness locally within the tenant's shard.

If business rules require **`external_reference` to be unique across all tenants**, per-shard `UNIQUE` indexes alone **are insufficient** globally. You may need globally partitioned ID generation, a central reference registry service, or an appropriate consistency protocol. UUIDs lower collision probability, **but never replace** explicit uniqueness enforcement or conflict-resolution workflows.

### 12.2. Co-Locating Frequently Co-Transacted Data

In an order system:

~~~text
orders(tenant_id, order_id, ...)
order_lines(tenant_id, order_id, line_no, ...)
payments(tenant_id, order_id, payment_id, ...)
~~~

If a transaction must atomically update an order and its line items, placing related rows on the same distribution unit avoids cross-shard transactions. Using **`HASH(tenant_id, order_id)`** keeps each order's rows co-located while spreading different orders of a tenant.

To achieve co-location, **all related tables must share compatible routing keys**. Merely adding a `tenant_id` column to a table does not force a distributed engine to co-locate rows on the same shard—and single-instance PostgreSQL does not become distributed automatically.

### 12.3. Cross-Shard Foreign Keys and Placement Changes

A foreign key between `order_lines` and `orders` remains a valid business rule even when data is distributed. However, **cross-shard FK enforcement** depends on engine and architecture: some support FKs only when co-located, while others restrict or omit cross-node FKs.

If direct FKs are unavailable, clarify:

- Which write path verifies the order exists and belongs to the right tenant?
- When deleting/canceling an order, how are orphaned lines prevented?
- If a multi-shard write fails midway, what is the compensation/recovery mechanism?
- Which reconciliation jobs detect broken referential integrity?

**Never conclude "because it's a distributed database, we don't need referential integrity."** The business constraint still exists; you must enforce it by other means and accept the cost.

### 12.4. Ordered Events and Late-Arriving Data

When splitting one tenant across multiple buckets, events from different buckets can arrive out of order at consumers. If the business needs **per-order ordering**, routing by `order_id` keeps a single ordering key together; if **tenant-wide ordering** is required, splitting the tenant makes ordering far more expensive.

Never take auto-increment IDs from independent shards and assume they form **a global order**. Event design must distinguish:

- **Event time:** when the business event occurred.
- **Ingestion/commit time:** when the system received and persisted it.
- **Sequence:** the exact scope requiring ordering (e.g., per order).
- **Idempotency key:** how retried events are identified.

If reports or workflows require consistent state across buckets, define ordering merge rules and late-data handling.

### 12.5. Avoiding Unbounded Scatter-Gather

A query:

~~~sql
SELECT *
FROM tenant_order_events_bucketed
WHERE tenant_id = 42
ORDER BY occurred_at DESC
LIMIT 50;
~~~

in a bucketed model can touch multiple locations. With 4 buckets, that may be acceptable; with 1,024 buckets spread across clusters, firing 1,024 sub-queries per API page causes massive latency and network overhead.

Coordinated mitigations typically include:

- **Cap bucket counts per tenant** to real need rather than picking huge defaults.
- **Keyset pagination** with stable ordering and explicit tie-breakers.
- **Push filters and appropriate `LIMIT`s** down to every bucket, then merge accurately globally.
- **Tenant-level read models** for UIs needing a unified timeline.
- **Per-tenant query budgets:** timeouts, scanned row caps, concurrency, and rate limits.

Choosing a shard key balances **data locality** against **load distribution**—it is not a contest to find the key with the most distinct values.

## 13. Combining Time Partitioning with Tenant Distribution

Event systems often need both **time-based retention** and **whale-tenant scalability**. You can combine two axes:

~~~text
logical route = (tenant_id, entity_bucket)
storage partition = month(occurred_at)

Example:
  Tenant 42, bucket 0 -> node A -> events_2026_11
  Tenant 42, bucket 1 -> node B -> events_2026_11
  Tenant 42, bucket 2 -> node C -> events_2026_11
  Tenant 42, bucket 3 -> node D -> events_2026_11
~~~

This is a **hypothetical logical layout**, not an automatic PostgreSQL setup produced by the earlier DDL. The idea is:

- **Buckets** spread events of a large tenant across resource pools.
- **Time** enables pruning for interval queries and partition-level expiration.
- **Routing** requires knowing the tenant/bucket key and mapping.
- **Full-tenant historical queries** may still touch multiple buckets and multiple time partitions.

Partitioning solely by month leaves current writes hot. Hashing solely by tenant leaves whales concentrated. Bucketing without time makes purging expired data require mass row deletes across every bucket. **Multiple distribution axes solve distinct problems while adding operational complexity.**

### 13.1. Never Use Timestamps as a Substitute for Event Identity

Two events can share the exact same timestamp; one order can emit multiple events within a millisecond. Identification requires a **stable `event_id` or sequence** at the right scope; `occurred_at` serves time tracking, filtering, and sorting. Using a timestamp as the entire unique key when concurrent events are valid will silently drop legitimate events.

### 13.2. TTLs and Dropping Whole Partitions

In periodic stores, dropping an old partition is far cheaper than deleting rows one by one; yet you must verify:

- No data remains under legal hold or audit requirements.
- Partitions cleanly **align with expiration boundaries**.
- Related tables, indexes, backups, and derived read models follow cleanup workflows.
- You do not accidentally drop data for another tenant with longer retention requirements.

A whale tenant may require custom retention or storage isolation; **never apply a single table-wide TTL** when customers carry different contractual obligations.

## 14. Validate with Realistic Load and Skew Testing

An architecture with a clean distribution diagram can still collapse under **a heavy burst from a single tenant**. Benchmarks must reproduce actual query shapes, temporal patterns, and business contention rather than generating uniform random keys.

### 14.1. Minimum Load Test Suite

| Scenario | Load Pattern | What to Measure |
| --- | --- | --- |
| **A. Normal** | Many small tenants, fairly even load | QPS, CPU/node, p95/p99, and query counts |
| **B. Whale** | One tenant drives 40–70% of peak requests | Hot shard, whale latency, impact on small tenants |
| **C. Burst** | Large tenant imports a batch over a few minutes | Queue depth, write latency, lag, and backpressure |
| **D. Hot counter** | Many workers concurrently update one `tenant_usage` row | Lock wait, retries, update throughput |
| **E. Hot read key** | Many requests read the exact same record | Cache hit rate, miss storms, replica lag |
| **F. Cross-bucket query** | Whale tenant's latest activity page | Shards touched, bytes transferred, merge latency |
| **G. Rebalance/failover** | Moving buckets or switching routes | Missing/duplicate data, disruption window, route versions |
| **H. Concurrent heavy query** | Whale runs reports alongside live writes | Normal transaction p99, CPU/IO, and timeouts |

Do not measure peak throughput alone. Test **fairness**: when W runs a massive batch, do small tenants still meet normal SLOs? Dedicated shards improve fairness even if total cluster QPS barely changes.

### 14.2. Quantitative Metrics to Track

Define:

\[
\text{Skew ratio} =
\frac{\max(\text{load across shards})}
{\text{average load across all shards}}.
\]

The denominator must include **all active shards**, even shards with zero rows or zero requests. Specify which **load** metric you are computing: requests/second, CPU, bytes written, IOPS, and row counts are distinct axes.

Beyond skew ratio, monitor:

- **Top-1/Top-10 tenant share** of requests, CPU, or rows.
- **p95/p99 latency by tenant and API route**, avoiding hiding slow tenants.
- **Busy/idle ratio** across nodes.
- **Lock wait duration** on hot keys/records.
- **Fan-out count** and cross-shard bytes transferred per query.
- **Recovery time**, pre/post-migration record discrepancies, and idempotent retry counts.

Example **hypothetical** test SLO (not a universal standard):

~~~text
When tenant W generates 40% of total requests:
  order-read API p99 for small tenants < 200 ms;
  system-wide write error rate < 0.1%;
  zero lost or duplicated events during route cutover;
  100% of event keys reconcilable post-migration.
~~~

Concrete thresholds must reflect project contracts, DBMS behavior, and infrastructure capacity. Passing a uniform load test is insufficient to sign off on whale handling.

### 14.3. Before-and-After Optimization Evaluation

| Metric | Before Optimization | After Optimization | Question |
| --- | --- | --- | --- |
| Max-to-avg writes | Measured per shard | Measured in same window | Is load more balanced? |
| Tenant W p99 | On critical requests | On same requests | Is the whale served faster? |
| Small tenants p99 | During W's traffic spike | During W's traffic spike | Did noisy-neighbor interference drop? |
| Shards per tenant-wide query | Typically 1 | Potentially B | How much did fan-out cost increase? |
| Counter update duration | Legacy lock wait | New mechanism | Was the hot row resolved? |
| Count/quota accuracy | Source reconciliation | Source reconciliation | Did duplicates, gaps, or quota overruns occur? |

An optimization succeeds when it **meets business goals at acceptable total cost**, not merely because a partition row-count chart looks flat.

## 15. Decision Matrix by Problem Type

| Context | Candidate Approach | Key Trade-off |
| --- | --- | --- |
| Many small tenants, tenant-scoped queries, no whales | **Hash by `tenant_id`** | Great co-location; monitor growth |
| One large tenant fitting within one dedicated cluster | **Dedicated shard / tenant placement** | Dedicated migration/ops, keeps tenant queries local |
| One tenant with many independent orders exceeding one shard's write QPS | **Hash by `tenant + order/bucket`** | Tenant-wide queries fan out; per-order transactions easier than per-tenant |
| A single order or record itself is ultra-hot | **Hot-key-specific design:** cache, queue, serialized owner, batching, read replicas, counter sharding by type | Cannot be cured merely by bucketing on `order_id` |
| Writes pile into the current monthly partition | **Hash/bucket inside each period, or entity-based sharding** | Requires two distribution axes, more complex routing and plans |
| One event counter row receives continuous updates | **Append events + aggregate** or **counter buckets** | Summing, accuracy, and idempotency require careful design |
| Mostly heavy reads on the same key | **Cache, replicas, eliminate redundant queries** | Invalidation, stale reads, authorization |
| Heavy cross-tenant reporting | **Read models, pre-aggregation, warehouse** | Refresh cadence, reconciliation, separate from source of truth |
| Tenant has strict residency or isolation mandates | **Regional/cluster tenant placement** | Routing, operations, backups, and migration |

You do not need every technique at once. Pick solutions based on **measured hotspots** and which questions the system must answer fastest.

### 15.1. Decision Workflow

1. **Lock grain and keys:** does one row represent an order, an order event, a daily snapshot, or an aggregate counter?
2. **Profile the workload:** tenant distribution, keys, read/write ratio, row sizes, queries, peak hours.
3. **Classify the heat:** hot row, hot read key, hot partition, hot node, or hot query.
4. **Try the smallest effective fix:** indexing/caching/batching/rate limiting before committing to a full shard-key migration.
5. **Assess locality and transactions:** which tables/keys must commit together?
6. **Assess uniqueness and references:** do you need global uniqueness, FKs/cascades, or tenant-wide event ordering?
7. **Pick routing and partitioning:** tenant, composite key, bucket, time, dedicated placement, or controlled combination.
8. **Design skew tests:** simulate tenant W, bursts, hot counters, failovers, and query fan-out.
9. **Plan migration and rollback:** reconcile data, update mappings, handle in-flight requests.
10. **Review periodically:** today's tiny tenant can become a whale in three months.

## 16. Practice Exercises

### Exercise 1. Even Key Hashing Does Not Equal Even Load

A system has **8 shards** handling **2,000,000 writes/day** total. Tenant A accounts for **600,000 writes**; the rest come from many small tenants. Each tenant is assigned intact to one shard via `HASH(tenant_id)`.

**Tasks:**

1. Compute the ideal average load per shard.
2. Prove the lower bound on A's shard load and its ratio to the average.
3. If scaled to **16 shards** while still partitioning by `tenant_id` at constant total load, is A guaranteed to be less hot?
4. Name two suitable fixes if A's writes span many independent orders.

<details>
<summary>Exercise 1 Solution Hints</summary>

Ideal average across 8 shards: **2,000,000 / 8 = 250,000 writes/day/shard**. A's shard holds at least **600,000**, giving a skew ratio of at least **600,000 / 250,000 = 2.4x**.

With 16 shards, the average drops to **125,000** while tenant A still puts at least **600,000** onto one shard, raising the minimum max/avg ratio to **4.8x**. That does not mean A's absolute shard load grew; it shows **adding shards does not split A**.

Two options: **move A to a dedicated cluster** if one cluster handles it, or **bucket by `order_id`** to spread A's independent orders across locations, accepting fan-out for tenant-wide views.

</details>

### Exercise 2. Trade-Offs of Changing the Shard Key

A platform stores three datasets:

~~~text
orders(tenant_id, order_id, created_at)
order_lines(tenant_id, order_id, line_no, product_id)
order_events(tenant_id, order_id, event_seq, occurred_at)
~~~

Requirements:

- Viewing a single order's details must be fast and consistent.
- One large tenant creates huge volumes of independent orders.
- A dashboard showing "the 50 latest activities across all orders of a tenant" is opened frequently.

**Tasks:** compare shard keys **`tenant_id`** and **`(tenant_id, order_id)`** across writes, locality, transactions, and dashboards; propose a solution serving both query types.

<details>
<summary>Exercise 2 Solution Hints</summary>

With **`tenant_id`**, querying all data of a tenant stays in one place, yet the whale concentrates onto one shard. With **`(tenant_id, order_id)`**, rows of one order co-locate and whale orders spread out, yet the tenant-wide dashboard must fan out, merge, and paginate.

You can shard by order to serve writes and order details, while maintaining a **per-tenant activity read model or summary table** for the dashboard—with clear ordering, idempotency, refresh lag, and source of truth.

</details>

### Exercise 3. The Bottleneck Is a Counter Row

Events for tenant B are evenly spread across 8 partitions, yet the API still stalls at:

~~~sql
UPDATE tenant_usage
SET used_events = used_events + 1
WHERE tenant_id = 99;
~~~

Why doesn't changing the events table's partition key help? Propose an improvement when the counter only feeds a dashboard, and explain why that approach does not directly suit a **hard quota of 100,000 events**.

<details>
<summary>Exercise 3 Solution Hints</summary>

The bottleneck is **the single `tenant_usage` row** updated by concurrent transactions; spreading events does not move where the counter row is updated. For analytics/dashboards, you can **append events and aggregate periodically** or split the counter into multiple **`(tenant_id, bucket)`** rows and `SUM` on read.

With a hard quota, two transactions can observe remaining room in the sum and simultaneously increment different buckets, overshooting the limit. Hard quotas require **tightly coordinated reservation/enforcement**, idempotency, and concurrency control—never naive eventual counters.

</details>

### Exercise 4. Choosing a Bucketing Algorithm at the Right Grain

A tenant has 80,000 orders, each emitting 5–20 events. Order 100 produces an event stream that must be processed in ascending **`event_seq`** order.

**Tasks:**

1. Compare **`bucket = order_id MOD 4`** and **`bucket = event_id MOD 4`**.
2. For `order_id = 100`, which bucket does the first scheme choose?
3. What filter predicates should a query fetching all events of order 100 include?
4. If order 100 itself receives 90% of the tenant's events, does the first scheme resolve the hotspot?

<details>
<summary>Exercise 4 Solution Hints</summary>

**Bucketing by `order_id`** keeps all events of an order together, making `event_seq` ordering and per-order consistency straightforward. **Bucketing by `event_id`** scatters an order's events across locations, complicating queries and ordering.

With `100 MOD 4 = 0`, the query should filter **`tenant_id`**, **`bucket = 0`**, **`order_id = 100`**, then `ORDER BY event_seq`. If one order receives 90% of load, bucketing by `order_id` still funnels it into one bucket; handle hot single orders separately via batching, queuing, or caching depending on read/write and ordering requirements.

</details>

### Exercise 5. Monthly Partitioning Does Not Auto-Balance

A system keeps three monthly partitions. All November writes go to **`events_2026_11`**; September and October only serve historical lookups.

**Tasks:** explain why equal row counts across the three partitions do not prove balanced writes; propose how to combine hashing/bucketing with time when high write throughput and periodic purging are both needed.

<details>
<summary>Exercise 5 Solution Hints</summary>

Total rows may look even while **active write load concentrates on the single November partition**. Measure short-window QPS/CPU/IOPS/index contention rather than row counts alone.

You can split data into **multiple entity/tenant buckets inside each month**, or distribute by event/order key across nodes and time-partition within each node. Preserve date pruning and bucket routing; multi-period or tenant-wide queries may require fan-out.

</details>

### Exercise 6. Is Migrating a Whale Tenant Safe?

Tenant W moves from **`shared_group_A`** to **`dedicated_group_W`**. A job copies a snapshot and updates routing, yet new writes keep arriving at `shared_group_A` during the copy.

**Tasks:**

1. Point out the data-loss risk.
2. Describe how to catch up changes before cutover.
3. What must be verified to avoid duplicate or missing events?
4. If two application instances cache different routing versions, how must this be handled?

<details>
<summary>Exercise 6 Solution Hints</summary>

A snapshot omits mutations after snapshot time, so flipping routing immediately without catching up logs risks **missing events** on the target. Use log-position CDC or a migration protocol that fences/redirects writes during a controlled cutover window. Reconcile primary keys, row counts, event versions, aggregate totals, and scoped uniqueness.

Routing needs **versions/epochs** and rules for stale clients; never let both source and target accept writes indefinitely as dual authorities. Plan rollback, idempotent retries, and in-flight request tests.

</details>

### Exercise 7. Row-Count Skew Statistics Are Not Enough

One shard holds only **5% of rows** yet consumes **65% of CPU**, while another shard holds **40% of rows** and sees almost no traffic.

**Tasks:** can you conclude the shard with more rows is the hotspot? Name three other metrics to collect and two potential reasons the small-row shard is running hot.

**Solution guide:** no. Row count reflects **data skew**, while CPU and latency reflect **workload skew**. Collect requests/second, query shapes and rows scanned, IOPS, lock wait times, p99 latency, and cache hit rates. The small-row shard may hold a **hot key read/updated continuously**, or suffer an unindexed query scanning large volumes per request; it could also experience write batches or CPU contention with background jobs.

## 17. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "Uniform `tenant_id` hashing always balances QPS." | Hashing balances key counts when per-key load is comparable; whale tenants still overheat. |
| "Adding shards automatically splits a large tenant." | When routing whole tenants by `tenant_id`, the entire tenant remains on one shard. |
| "PostgreSQL partitioning means multi-machine sharding." | Local partitions do not automatically create independent nodes or hardware resources. |
| "The largest table/partition is always the hot partition." | Inspect read/write QPS, CPU, I/O, lock waits, and latency. |
| "We partitioned events, so counters cannot overheat." | A shared counter row is an independent serialization point. |
| "More buckets is always better." | Excessive buckets inflate fan-out, index overhead, routing, and management cost. |
| "Bucketing by `order_id` splits a hot order." | All events of that order still land in one bucket under that design. |
| "Consistent hashing eliminates hot keys." | Consistent hashing aids routing/rebalancing; it cannot split load for a single key. |
| "Caching solves every hot key." | Caching primarily helps reads; concurrent writes and consistency still need dedicated mechanisms. |
| "`ON CONFLICT` per shard enforces system-wide `UNIQUE`." | Global uniqueness requires mechanisms matching the key scope and distribution. |
| "Summing bucket counts is automatically exact." | Retries, duplicates, late events, and corrections require idempotency and reconciliation. |
| "Moving a tenant is just updating a routing table row." | You must copy data, catch up changes, cut over, verify, and support rollback. |
| "Low system-wide p95 means every tenant is healthy." | Aggregate metrics can mask a whale or subset of slow tenants. |

## 18. Key Takeaways

**Hot keys** occur when read/write traffic concentrates on one key, row, or resource pool. **Whale tenants** are customers whose load or volume dwarfs the rest. **Skew** can manifest in row counts, bytes, CPU, QPS, IOPS, lock waits, or latency; **uniform record counts do not guarantee balanced load**.

Choosing **`HASH(tenant_id)`** favors intra-tenant data locality, but cannot split a whale tenant. Sub-splitting by **`order_id`/buckets** distributes independent orders at the cost of fan-out on tenant-wide queries. **Dedicated shards** isolate noisy neighbors and preserve tenant locality yet demand careful migration; **counter buckets** relieve some hot rows without solving hard quotas; **caching and read models** often fit read bottlenecks better.

A reliable workflow is **define grain and invariants → measure hot keys/tenants/shards/nodes → classify root causes → choose the smallest effective fix → verify keys, integrity, transactions, and routing → test skewed load and migration → monitor continuously per tenant**. A sound distributed model balances resource placement while preserving data meaning and consistency.
