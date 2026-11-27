# Examples: Modeling Orders, User Activity, or Device Data

## Lesson Objectives

In Apache Cassandra, the first question is not "how many columns does an entity have?" but **"which keys will the application use to read data, in what order, and how many rows at most?"**. That is the essence of **query-driven design** in a distributed wide-column model.

The three business domains below all involve time-stamped data, yet they call for different designs:

- **Orders:** needs current-state lookups alongside customer lists or processing queues.
- **User activity:** needs per-user/day timelines and occasionally single-session progression.
- **Device data:** needs continuous writes, recent time-range reads, hot-device handling, and late-arriving events.

This lesson belongs to the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Through three self-contained examples, we combine partition keys, clustering keys, CQL, replication, read/write consistency levels, TTLs, compaction, repair, failure handling, and Java application integration.

After this lesson, you will be able to:

1. Write a **query contract** before choosing a table structure, and justify every table's keys.
2. Design ID lookup tables, bucketed history tables, and projection tables for alternate read paths.
3. Anticipate large/hot partitions, multi-bucket reads, and data duplication costs.
4. Handle status updates, duplicate or out-of-order events without confusing replica consistency with cross-table business consistency.
5. Write and invoke CQL prepared statements from Java, including `uuid`, `timestamp`, and `date` types.
6. Choose TTLs, paging bounds, reconciliation inputs, and benchmarks to validate schemas before production.

## 1. All Three Have Timestamps—Why Not Use One Table Template?

Start with a comparison table of **primary read paths**, not Java entity definitions:

| Domain | What Caller Usually Knows | Primary Question | Candidate Partition Key | Clustering Key |
| --- | --- | --- | --- | --- |
| Orders | Tenant and order ID | What status is this order in? | `(tenant_id, order_id)` | Not needed when one order is one row |
| Orders | Tenant, customer ID, month | Customer's 50 newest orders? | `(tenant_id, customer_id, month_bucket)` | `created_at DESC, order_id DESC` |
| User activity | Tenant, user ID, day | Most recent activity on that day? | `(tenant_id, user_id, day_bucket)` | `occurred_at DESC, event_id DESC` |
| User activity | Tenant and session ID | Activity within one short session? | `(tenant_id, session_id)` | `occurred_at ASC, event_id ASC` if UI views sequentially |
| Device data | Tenant, device ID, hour | Read telemetry within one hour? | `(tenant_id, device_id, hour_bucket)` | `event_time DESC, event_id DESC` |
| Device alerts | Tenant, site ID, day, shard | Critical alerts at a site? | `(tenant_id, site_id, day_bucket, shard_id)` | `event_time DESC, event_id DESC` |

These are **illustrative candidates for the stated requirements**, not mandatory schemas for every system. In Cassandra:

- **Partition keys** determine the logical partition, affecting token/replica distribution and request routing. A composite key like `PRIMARY KEY ((a, b, c), d, e)` means **`(a,b,c)` together form one partition key**, while `d,e` are clustering columns.
- **Clustering columns** determine intra-partition ordering and prefix/range filtering. They do not make Cassandra sort globally across all partitions.
- **Regular columns** hold returned payload data without automatically offering an efficient path for arbitrary filters.
- **Denormalization** means storing the same business facts in separate tables to serve distinct read paths. It is not Cassandra's replication factor.

**Common workflow across all three examples:**

1. List the APIs and inputs guaranteed to be present.
2. Specify row counts, ordering, time windows, freshness, and SLAs.
3. From the highest-priority API, pick partition/clustering keys that route directly.
4. Calculate rows/bytes and write rate of the **busiest partition**, not just averages.
5. For remaining APIs, pick bounded fan-out, projection tables, or another system if needed.
6. Design write flows, error handling, and reconciliation; only then benchmark and finalize the schema.

## 2. Example A: Multi-Tenant Order Model

### 2.1. Query Contract

Suppose an online store has the following requests:

| Code | API | Mandatory Inputs | Result |
| --- | --- | --- | --- |
| O01 | Details of one order | `tenant_id`, `order_id` | One current order |
| O02 | Customer's orders in a month | Tenant, customer ID, UTC month | Newest first, max 50 |
| O03 | `PENDING` queue created on a day | Tenant, status, UTC creation day | Newest first, max 50 |
| O04 | Customer's list across three calendar months | Tenant, customer ID, three months | Multi-partition with bounded merge |
| O05 | Search by notes/full-text and amount | Tenant, flexible filters | Evaluate search rather than forcing schema |

O01, O02, and O03 have **three distinct lookup key sets**. Do not expect a single orders table with `PRIMARY KEY ((tenant_id, order_id))` to simultaneously serve customer lists and status queues.

### 2.2. Order Lookup Table by ID

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    current_status text,
    total_amount decimal,
    last_changed_at timestamp,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, current_status,
       total_amount, last_changed_at, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

One `(tenant_id, order_id)` pair locates one partition containing one summary row. No clustering column is needed because O01 does not ask for multiple versions of the same order. `revision` is a business version **assigned and enforced by the application**, not auto-incremented by Cassandra.

Note: putting tenant in the key expresses the request's data scope, yet **does not replace authentication/authorization**. The service must verify the caller is permitted to access the target tenant.

### 2.3. Order List Table by Customer/Month

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    current_status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, created_at, current_status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

`month_bucket` uses `YYYY-MM`, computed from `created_at` after converting to UTC, e.g., `2026-11`. `created_at` comes first in the clustering key to read newest first; `order_id` distinguishes orders created at the exact same timestamp.

When O04 asks for three months, the API computes the list of **three allowed calendar-month buckets**, reads each partition, and merges by `(created_at DESC, order_id DESC)`. A single O02 query returns data for only **one month**. If product defines "sliding 90 days" instead of three calendar months, the number of monthly buckets read can reach **up to four** at boundaries; compute from the actual `[from, to)` half-open interval.

### 2.4. Queue Table by Status and Creation Day

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    current_status text,
    created_day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, current_status, created_day),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT created_at, order_id, customer_id, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = 'PENDING'
  AND created_day = ?
LIMIT 50;
```

`created_day` is the **UTC date the order was created**, not the date it transitioned to `PENDING`. O03 means "orders **created on day X** that are currently PENDING." If product asks for "orders that moved to PENDING on day X," that is a different query shape requiring transition-timestamp data.

In this table, status is **part of the partition key**, unlike the regular `current_status` column in the customer table. When status changes, you cannot simply `UPDATE` a primary key component in place to move the row.

### 2.5. Write Path and Failures on Status Transitions

When a new order is created, the system must write all chosen projections. For example:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    current_status, total_amount, last_changed_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, current_status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

Suppose an accepted transition moves the order from `PENDING` to `PAID`. The business flow:

1. Validate the transition and update **the source state** with the new revision.
2. Update regular columns `current_status`/`revision` in the customer/month table.
3. Delete the `PENDING` row using its **full old key** in the status/day table.
4. Insert the `PAID` row using its **full new key** in the status/day table.

```sql
-- Delete the existing row from the old status partition.
DELETE FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;

-- Create the projection row in the new status partition.
INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

**Event ordering is a separate problem:** if revision 12 (`PAID`) applies first and a retry of revision 11 (`PENDING`) arrives late, an unconditional consumer can recreate the wrong PENDING row. Simply having a `revision` column on the table does not make Cassandra reject older versions.

Use an explicit authoritative state source, per-order sequential processing, or **LWT/CAS** when business logic needs conditional updates on the source row:

```sql
-- Illustrative conditional update on an existing source row.
UPDATE orders_by_id
SET current_status = ?, last_changed_at = ?, revision = ?
WHERE tenant_id = ? AND order_id = ?
IF revision = ?;
```

Callers must inspect `[applied]` and ensure `nextRevision` is valid. LWTs incur extra cost; they do **not** automatically create an isolated transaction across all three tables. Projection mutations should flow from **accepted transitions** with durable events, retries, ordering controls, and reconciliation.

A **logged batch** helps a group of mutations eventually apply together under batch recovery semantics, yet it **does not provide observational isolation like a cross-partition SQL transaction**. Never use batches to replace revision control or as a throughput trick across many partitions.

### 2.6. Hot Partitions in the Status/Day Table

Suppose a tenant creates **300,000 orders/day** and at a given moment 40% of orders in that bucket are `PENDING`:

```text
PENDING rows ≈ 300,000 × 40% = 120,000 rows
Assuming 350 B/row of raw business data:
    120,000 × 350 = 42,000,000 B ≈ 42 MB
```

This is an assumption **excluding overhead, tombstones, compression, replication, and update churn**—not a safe partition threshold. Measure the largest tenant's size and QPS, transition counts, and p95/p99 latency.

If a `(tenant, PENDING, created_day)` partition grows too hot, consider adding a deterministic `shard_id` from `order_id` and reading/merging a bounded set of shards. Sharding lowers per-partition load while increasing fan-out; it does not shrink total data.

## 3. Example B: Time-Ordered User Activity

### 3.1. How Does It Differ from Orders?

An activity event (page view, button click, session start, authentication, settings change) is **an observation of something that happened**, not merely an entity's latest state field. To trace a user's journey, multiple events must be stored as multiple rows.

Example event:

```text
tenant_id      = "tenant-A"
user_id        = user-42
session_id     = session-007
event_id       = event-e1
occurred_at    = 2026-11-21T09:15:20Z
received_at    = 2026-11-21T09:15:23Z
event_type     = "PAGE_VIEW"
page_name      = "checkout"
```

IDs in this diagram are descriptive labels, not UUID literals to paste into CQL.

| Code | Action | Inputs | Requirement |
| --- | --- | --- | --- |
| U01 | 100 most recent user events in one day | Tenant, user ID, UTC day | `occurred_at DESC` |
| U02 | Events within an hour window on the same day | Tenant, user ID, day, `from/to` | Clustering range filter |
| U03 | Journey of one session | Tenant, session ID | `occurred_at ASC` order |
| U04 | User activity across seven calendar days | Tenant, user ID, days | Bounded multi-bucket reads |
| U05 | Funnel statistics across one million users in a month | Tenant, cohort, month | Analytics path, not reading every user's timeline |

U01 and U03 have **different partition keys**. U04 can read multiple daily partitions and merge; U05 should usually go to an analytics pipeline or precomputed aggregates.

### 3.2. Timeline Table by User/Day

```sql
CREATE TABLE user_activity_by_day (
    tenant_id text,
    user_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_id uuid,
    session_id uuid,
    received_at timestamp,
    event_type text,
    page_name text,
    payload text,
    PRIMARY KEY ((tenant_id, user_id, day_bucket),
                 occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Why this design?

- `(tenant_id, user_id, day_bucket)` locates one person's timeline on one day.
- `occurred_at DESC` serves "newest first" screens.
- `event_id` distinguishes events with identical timestamps. UUID order on timestamp ties is key order, not a causal guarantee.
- `session_id`, `event_type`, and `page_name` are regular columns, not automatic lookup paths for arbitrary sessions or event types.

U01:

```sql
SELECT occurred_at, event_id, session_id, event_type, page_name
FROM user_activity_by_day
WHERE tenant_id = ?
  AND user_id = ?
  AND day_bucket = ?
LIMIT 100;
```

U02 with a half-open range:

```sql
SELECT occurred_at, event_id, event_type, page_name
FROM user_activity_by_day
WHERE tenant_id = ?
  AND user_id = ?
  AND day_bucket = ?
  AND occurred_at >= ?
  AND occurred_at < ?;
```

The service layer must verify whether `[fromInclusive, toExclusive)` falls inside the requested day. If the window crosses 00:00 UTC, compute the next day's bucket and read both corresponding partitions—never pass one `day_bucket` for both days.

### 3.3. Session Table When U03 Is a Primary Read Path

If the application has short sessions with a bounded maximum event count and support routinely inspects full session journeys, add:

```sql
CREATE TABLE user_activity_by_session (
    tenant_id text,
    session_id uuid,
    occurred_at timestamp,
    event_id uuid,
    user_id uuid,
    event_type text,
    page_name text,
    PRIMARY KEY ((tenant_id, session_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);

SELECT occurred_at, event_id, user_id, event_type, page_name
FROM user_activity_by_session
WHERE tenant_id = ? AND session_id = ?;
```

U03 routes by session ID, with **ascending** clustering to replay the journey from start to finish. However, if sessions last weeks or accumulate huge event counts, `(tenant_id, session_id)` risks becoming an unbounded partition. In that case, bucket by session and/or time with an explicit read contract.

Creating a session table means **another write per event** and another data lifecycle to maintain. If U03 is very rare and callers already know user ID and day, evaluate reading a few known buckets and filtering/merging within bounds before adding a projection.

### 3.4. Retention, Late Events, and Privacy

Suppose policy retains behavior for **30 days from event occurrence**, yet mobile clients can stay offline and upload late. An `INSERT` into the user/day table can use an application-computed TTL:

```sql
INSERT INTO user_activity_by_day (
    tenant_id, user_id, day_bucket, occurred_at, event_id,
    session_id, received_at, event_type, page_name, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

Cassandra's `TTL` is **seconds from write time**, not computed from `occurred_at`. If an event occurred 5 days ago and just arrived, remaining TTL is roughly 25 days under a 30-day event-time contract. If remaining TTL is `<= 0`, never pass `TTL 0` assuming immediate deletion; handle expired data per policy, such as skipping writes or routing to an approved audit/reconciliation flow.

If the session table also stores the same event, align its retention policy and propagate deletes/masking as required. When personal data is present, minimize `payload`; adding projections, backups, or exports creates additional copies needing permission and retention governance.

**TTL is not instant physical erasure.** Expired cells leave tombstones and old SSTables awaiting compaction. Repair syncs replicas via Cassandra's mechanisms; it cannot restore an event that failed to write to the session table because a consumer crashed.

### 3.5. Evaluating the Hottest User's Load

Suppose an automated account emits **12 events/second continuously**, averaging **500 B of raw data**:

```text
One hour: 12 × 3,600 = 43,200 events
          43,200 × 500 B = 21.6 MB raw data

One day:  12 × 86,400 = 1,036,800 events
          1,036,800 × 500 B = 518.4 MB raw data
```

For such an account, **daily buckets** may need re-evaluation toward hourly buckets, though reading a full day in U01 would then probe up to 24 hourly partitions. Measure largest partition, tombstones scanned, and p95/p99; there is no universal MB threshold declaring a model safe.

Additionally, a strict 24-hour sliding window can touch **25 hourly buckets** if endpoints do not align on hour boundaries. Compute intersected buckets from `[from, to)` rather than assuming hours equal partition count.

## 4. Example C: Device Telemetry and Alerts

### 4.1. How Does It Differ from Activity Logs?

Device data typically exhibits:

- Continuous ingestion, potentially with massive spikes on a **single device**.
- Late-arriving events when gateways lose connectivity, or burst replays after reconnection.
- Different retention for standard telemetry versus critical alerts.
- Two very different screens: charts for **one device** and alert lists for **one site**.

Example inputs:

```text
tenant_id, site_id, device_id, event_id,
event_time, received_at, metric_name, metric_value,
severity, payload
```

| Code | Query | Inputs | Read Path |
| --- | --- | --- | --- |
| D01 | 50 most recent device events in an hour | Tenant, device ID, UTC hour | One partition by device/hour |
| D02 | Values in `[09:10,09:40)` of that hour | Tenant, device ID, hour, from/to | Clustering range |
| D03 | Device events across six sliding hours | Tenant, device ID, range | Bounded multiple buckets |
| D04 | `CRITICAL` alerts at a site on one day | Tenant, site ID, day | Separate projection or monitoring tool |
| D05 | Compare trends across all sites over two years | Tenant, multiple dimensions | Analytics/OLAP store |

### 4.2. Telemetry Table by Device/Hour

```sql
CREATE TABLE device_events_by_hour (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    event_time timestamp,
    event_id uuid,
    site_id uuid,
    received_at timestamp,
    metric_name text,
    metric_value double,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

`hour_bucket` is the **UTC start-of-hour timestamp of `event_time`**, e.g., `2026-11-21T09:00:00Z` for `[09:00,10:00)`. It must be computed identically by all writers and readers.

Two CQL queries for D01–D02:

```sql
SELECT event_time, event_id, metric_name, metric_value, severity
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 50;

SELECT event_time, event_id, metric_name, metric_value
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

D02 reads a range inside one hourly partition; if the range crosses an hour boundary, the application layer splits it into per-bucket queries. `LIMIT 50` bounds rows **returned**, not physical cells scanned—especially when tombstones/TTLs exist.

### 4.3. Hot Telemetry: Checking Hourly Buckets and Sharding

Suppose the hottest device writes **40 events/second** continuously, averaging **650 B/event of raw data**:

| Window | Events | Estimated Raw Data |
| --- | ---: | ---: |
| One minute | 2,400 | 1.56 MB |
| One hour | 144,000 | 93.6 MB |
| One day | 3,456,000 | 2,246.4 MB (~2.25 GB) |

These are not SSTable byte counts. Compression, metadata, partitions/indexes, tombstones, compaction, and replication change actual disk usage. Hourly buckets are merely a **candidate to benchmark**. An ultra-hot device can still create a hotspot on one hourly partition; if benchmarks miss SLAs, split into shorter buckets or add shards:

```sql
CREATE TABLE device_events_by_hour_sharded (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    metric_name text,
    metric_value double,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

A rule like `shard_id = hash(event_id) mod N` must use consistent hash function, `N`, and versioning across writers. With `N=8`, D01 reads **eight partitions** and merges by `(event_time DESC, event_id DESC)` to return the 50 newest rows. One shard's paging state does not represent pagination progress across all eight shards.

Never shard preemptively before data proves a hotspot, because fan-out and paging overhead can outweigh the benefit.

### 4.4. Site Projection for Displaying Alerts

D04 asks for "all `CRITICAL` alerts at a site on a day." `device_events_by_hour` is organized by **device ID**; knowing only the site does not identify each device's partitions.

If D04 is a critical screen, create a projection storing only **CRITICAL** events, split across 8 shards for busy sites:

```sql
CREATE TABLE critical_device_events_by_site_day (
    tenant_id text,
    site_id uuid,
    day_bucket date,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    device_id uuid,
    metric_name text,
    metric_value double,
    PRIMARY KEY ((tenant_id, site_id, day_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

When a CRITICAL event arrives, the application/pipeline writes it to the device/hour table **and** the site/day table with `shard_id` deterministically derived from `event_id`. D04 reads up to eight shards for that site/day and merges; for smaller sites, an unsharded design can be evaluated.

Requirements to lock down:

1. Is `site_id` in the event the **device's site at event time** or its current site? When a device moves sites, does history move?
2. If severity is downgraded from `CRITICAL` to `WARN`, must the CRITICAL projection row be deleted?
3. If the projection write fails after the device/hour write succeeded, how do **retries and reconciliation** recover?
4. Do alerts retain longer than standard telemetry? If so, manage each representation's TTL independently.
5. What is the peak events/s per site, and do fan-out bounds meet SLAs?

**Duplicate event IDs across a site/day** are not automatically blocked by Cassandra when clustering includes `event_time` and another key; preserve stable keys on retries or deduplicate at the source.

### 4.5. Event-Time TTL

Suppose standard telemetry is kept **7 days from `event_time`**. For offline devices, a fixed `USING TTL 604800` at receipt time **retains late events longer than 7 days from occurrence**.

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket,
    event_time, event_id, site_id, received_at,
    metric_name, metric_value, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

Application rule:

```text
expires_at = event_time + 7 days
seconds_left = expires_at - current_write_time

seconds_left > 0  -> INSERT USING TTL seconds_left
seconds_left <= 0 -> apply expired-event policy
```

For instance, an event arriving two days late has roughly **five days of TTL** left. TTL is measured in seconds with Cassandra bounds and clock skew; validate acceptable ranges, never pass zero or negative values, and never treat TTL as guaranteed instant physical deletion.

`CRITICAL` events may be kept 30 days in their dedicated projection per policy, yet if the device/hour table keeps only 7 days, after day 7 you **cannot rely on reading old details back from the telemetry table**. The CRITICAL projection must carry the display fields it needs or link to an appropriate archive.

## 5. Side-by-Side Comparison: Differences in Reads and Writes

| Criterion | Orders | User Activity | Device Data |
| --- | --- | --- | --- |
| Core value | Current state and work lists | Event series per user/session | Event series per device/site |
| Primary routing keys | `(tenant,order_id)` or `(tenant,customer,month)` | `(tenant,user,day)` | `(tenant,device,hour)` |
| Clustering | `created_at` for lists | `occurred_at` for events | `event_time` for telemetry |
| Projection needed when | Reading by status/day | Reading by session without user/day | Reading alerts by site instead of device |
| Hard mutations | Status changes move projection keys | Duplicates, late arrivals, privacy deletes | Peak ingest, offline replays, differing table TTLs |
| Main risks | Hot status/day partition, cross-table drift | Automated user's timeline grows huge | Hot device/hour partition, site alert fan-out |
| Retention | Tied to order/record lifecycle | Tied to activity/user privacy policy | Typically varies by telemetry/alert tier |
| Broad tenant-wide reads | May need search | Funnels/cohorts need analytics | Long-term trends need analytics/OLAP |

There is no rule saying "every time-stamped entity uses daily buckets." Choose **buckets** from the intersection of query shapes and peak loads; choose **projections** for valuable queries; choose **retention** from business requirements. A schema sound in one domain cannot be copied blindly into another without re-checking assumptions.

## 6. Evaluating Costs Across All Three Models

### 6.1. Rows/Bytes of the Largest Partition

Rough estimate:

```text
rows_per_bucket ≈ max_events_per_second_for_key × bucket_seconds
raw_bytes_per_bucket ≈ rows_per_bucket × average_raw_row_bytes
```

For orders, `max_events_per_second_for_key` may be new orders for a **tenant in one status/day**. For user activity, it is the **busiest user**. For telemetry, it is the hottest **device** or **site**.

Cluster-wide averages miss outlier tenants, automated users, or bursting devices. Meanwhile, smaller buckets increase partition counts read for longer windows; always measure **both write hotspots and read fan-out**.

### 6.2. Multi-Table Write Cost

Suppose a new order writes three tables: at least three logical mutations. If one status change updates source and list rows, deletes the old status, and inserts the new status, that scenario takes four logical mutations—**excluding retries, audit/event logs, or indexes**.

A user event written to both user/day and session tables takes at least two mutations. A CRITICAL telemetry event written to device/hour and site/day takes at least two mutations. These are **counts for the illustrative diagrams**, not universal Cassandra benchmarks.

With `RF=3`, each mutation replicates to three replicas in a DC per topology. Yet `logical mutations × 3` is only a rough count of replica applications, **not total disk I/O**: commit logs, memtables, SSTables, compaction, batchlogs, repair, retries, and compression all contribute.

### 6.3. On-Disk Bytes Do Not Equal Raw JSON

```text
logical_payload_bytes ≈ live_rows × raw_bytes_per_row
base_table_one_replica ≈ live_rows × measured_disk_bytes_per_live_row
replicated_base ≈ base_table_one_replica × RF
cluster_provisioned ≈ modeled_used_bytes / target_utilization
```

`measured_disk_bytes_per_live_row` must be measured under representative schema, data distribution, compaction, and TTLs; never apply one universal overhead multiplier to every table. For secondary indexes, SAI, or projections, measure each structure's scope accurately and avoid double-counting bytes already included in measurements.

TTL expiration is also **not** the instant SSTables reclaim space. Tombstones, overwritten older cells, and compaction backlogs can keep transient disk usage above live data size. Clusters need headroom for compaction, repair, rebuilds/streaming, snapshots, and backfills.

### 6.4. When to Keep Fan-Out Instead of Adding a Table?

| Secondary Query | Approach Worth Evaluating |
| --- | --- |
| Customer history across 2–3 known months | Read 2–3 customer/month partitions and merge within bounds |
| User activity across 2 known days | Read 2 user/day partitions with byte and paging caps |
| Device telemetry over 6 hours | Read intersecting hourly buckets—up to 7 across boundaries |
| Search orders by keyword and arbitrary filters | Indexed search engine, not probing all customer partitions |
| Multi-year aggregations across tenant or site | OLAP/warehouse or aggregation pipeline |

**Seven hourly buckets for a six-hour sliding window** commonly happens when endpoints do not align on hour boundaries. APIs must count buckets from the half-open `[from, to)` interval rather than hardcoding a fixed constant ignoring timestamps.

## 7. Java Driver 4.x: Three Query Types, Three Prepared Statements

This Java snippet illustrates the **read** paths for all three domains. It assumes the application created the CQL tables above and shares one service-scoped `CqlSession` (never created per HTTP request).

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class QueryDrivenExamples {
    private final CqlSession session;
    private final PreparedStatement orderById;
    private final PreparedStatement activityByDay;
    private final PreparedStatement deviceByHourRange;

    public QueryDrivenExamples(CqlSession session) {
        this.session = session;
        this.orderById = session.prepare(
            "SELECT customer_id, created_at, current_status, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.activityByDay = session.prepare(
            "SELECT occurred_at, event_id, session_id, event_type, page_name " +
            "FROM user_activity_by_day " +
            "WHERE tenant_id = ? AND user_id = ? AND day_bucket = ? " +
            "LIMIT 100"
        );
        this.deviceByHourRange = session.prepare(
            "SELECT event_time, event_id, metric_name, metric_value " +
            "FROM device_events_by_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public Row findOrder(String tenantId, UUID orderId) {
        return session.execute(orderById.bind(tenantId, orderId)).one();
    }

    public ResultSet latestUserActivity(
        String tenantId, UUID userId, LocalDate utcDay
    ) {
        return session.execute(
            activityByDay.bind(tenantId, userId, utcDay)
        );
    }

    public ResultSet deviceRangeInsideHour(
        String tenantId, UUID deviceId,
        Instant fromInclusive, Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }
        Instant hour = fromInclusive.truncatedTo(ChronoUnit.HOURS);
        if (toExclusive.isAfter(hour.plus(1, ChronoUnit.HOURS))) {
            throw new IllegalArgumentException("Split into hourly buckets");
        }
        BoundStatement bound = deviceByHourRange
            .bind(tenantId, deviceId, hour, fromInclusive, toExclusive)
            .setPageSize(50);
        return session.execute(bound);
    }

    public static LocalDate utcDay(Instant timestamp) {
        return timestamp.atZone(ZoneOffset.UTC).toLocalDate();
    }

    public static String utcMonth(Instant timestamp) {
        return YearMonth.from(timestamp.atZone(ZoneOffset.UTC)).toString();
    }
}
```

Checks required when turning this into production APIs:

1. `tenantId` must be authenticated and authorized; composite keys containing tenant **do not enforce authorization**.
2. `UUID` maps to `uuid`, `Instant` maps to `timestamp`, and `LocalDate` maps to `date` in the driver. `YearMonth` must build `YYYY-MM` buckets **only after converting to UTC**.
3. Every prepared statement binds the full **partition key**; `deviceRangeInsideHour` rejects cross-hour ranges instead of silently returning incomplete data.
4. `LIMIT 100` in the activity query caps **total rows of the query**. `setPageSize(50)` on device ranges is the target page size, not `LIMIT 50`. The driver can automatically fetch more pages when iterating a `ResultSet`.
5. For multi-page APIs, use a query without a fixed preview `LIMIT`, manage consumed rows, and tie opaque paging state to the exact query shape/bound values; never reuse cursors across tenants/buckets.
6. For multi-bucket or sharded fan-outs, the service must track per-stream cursors and merge order; a single query's paging state cannot capture overall progress.
7. Configure timeouts, consistency levels, concurrency caps, backpressure, payload size checks, and safe retry classification for reads and writes.

## 8. Failures, Replication, Consistency, and Operations

### 8.1. Replica Consistency Differs from Cross-Projection Sync

Cassandra maintains replicas per keyspace replication factor and placement. In an appropriate topology, `LOCAL_QUORUM` for reads/writes can satisfy certain read-your-writes requirements on **the same data**, depending on RF, datacenters, and tolerated failures.

However, if the application wrote `orders_by_id` without updating `orders_by_status_day`, or wrote `device_events_by_hour` before the consumer wrote the alert projection, raising the consistency level on secondary-table reads **cannot conjure the missing mutation**. That is drift **across business tables**, requiring retries, event logs, and reconciliation.

### 8.2. Time-Series Tables, TTLs, and Tombstones

For user activity and telemetry:

- Write-time TTL fits retention measured from receipt/write; event-time TTL requires computing **remaining lifetime** at write time.
- Late-arriving events must land in the bucket derived from **the contract's chosen timestamp**, never arbitrarily using current server time.
- Rewriting an event with a new TTL can shift cell expiration times; idempotency must consider keys, payload, timestamps, and policy.
- Tombstones and older SSTables can linger after values stop being returned; `LIMIT` does not bound physical cells read.

For largely append-only time-series tables with fairly uniform TTLs, **TimeWindowCompactionStrategy (TWCS)** merits benchmarking. Yet TWCS windows rely on storage write timestamps, **not automatically on `day_bucket` or `hour_bucket`**. Backfills, historical edits, or mixed TTLs can prevent compaction from dropping windows as hoped.

**Repair** synchronizes replicas via Cassandra's mechanisms; it does not fix broken partition keys or detect missed business projections. Never shrink `gc_grace_seconds` arbitrarily just to purge tombstones faster, as deletion safety depends on disconnected-node windows and repair schedules.

### 8.3. Failure Matrix Across All Three Domains

| Domain | Failure Scenario | Symptom | Design Fix |
| --- | --- | --- | --- |
| Orders | Source updated to PAID, PENDING delete fails | Order lingers in old queue | Retry with old key, durable events, reconcile |
| Orders | Older revision arrives after newer revision | Status may regress | Per-order CAS/sequence; ignore stale updates |
| User activity | Timeout causes client to retry with new event ID | Two rows for the same action | Stable event IDs, dedupe, key checks |
| User activity | Late event crosses day boundary | Written to wrong bucket; missing from timeline | Bucket consistently by UTC `occurred_at` |
| Device data | Gateway offline then massive backfill | Write burst and compaction/backpressure | Quotas, bounded batch ingest, remaining TTL |
| Device data | Telemetry succeeds, CRITICAL projection fails | Alert missing at site view | Durable retries, reconcile by event ID |
| All three | Replica temporarily unreachable | Data needs convergence once node returns | Replication/CL/repair and monitoring |
| All three | Multi-bucket read during active TTL expirations | Result pages shift | Explicit cursor contract; never promise immutable snapshots |

## 9. Checklist for Real-World Projects

| Question | Required Evidence |
| --- | --- |
| Which queries actually matter? | Query-shape catalog with inputs, sort, QPS, SLAs, and bounds |
| Does the caller know full partition keys? | Every hot-path CQL has exact predicates on keys |
| Does clustering serve ordering and ranges? | Tested latest/range queries with duplicate timestamps |
| Which timestamp defines buckets? | UTC rules distinguishing event, created, and received times |
| Is the largest partition safe? | Measured rows/bytes, peak writes, tombstones, and p95/p99 on hot keys |
| Is fan-out bounded upfront? | API caps days/hours/shards, bytes, and concurrency |
| Is data duplicated? | Projection map, source of truth, and update mutations documented |
| Are partial failures handled? | Event ID/revisions, retries, ordering, reconciliation/rebuild |
| Is retention accurate? | Business-aligned TTLs, late-arrival handling, and deletes |
| Are replication/consistency suitable? | Per-DC RF, SLA-matched CL, and node-failure tests |
| Are disk/compaction costs accounted for? | Measured SSTables, tombstones, headroom, indexes/projections |
| Does Java control paging? | No unbounded reads; tokens bound to query shape and tenant auth |
| Are broad search/analytics separated? | Queries unsuitable for Cassandra offloaded or bounded |

## 10. Capstone Exercise: Choosing Tables for a Delivery System

A Java application manages delivery orders and barcode scanners. Data includes:

```text
Order:
  tenant_id, order_id, customer_id, created_at, status, revision

Scan event:
  tenant_id, parcel_id, scanner_id, site_id,
  scan_id, scanned_at, received_at, scan_status

Activity event:
  tenant_id, user_id, session_id, event_id,
  occurred_at, action_type
```

Requirements:

1. **R1:** Look up current status of an order by ID.
2. **R2:** View 50 newest orders for a customer in a month.
3. **R3:** View 100 newest scans for a parcel in a UTC hour.
4. **R4:** View a user's activity for a day, newest first.
5. **R5:** View `FAILED` scans at a site/day across multiple parcels.
6. **R6:** Report weekly total failed deliveries per site over two years.

Additional constraints:

- A single parcel can be scanned **25 times/second** at peak hours; one scan is roughly **800 B of raw data**.
- Scans can arrive two days late; retain **7 days from `scanned_at`**.
- User activity is retained **30 days from `occurred_at`**.
- List APIs return at most 100 rows/request and must enforce time-range caps.

**Questions:**

1. Choose partition keys and clustering keys for R1–R4; write at least two `CREATE TABLE` statements and three matching `SELECT` queries.
2. Propose a projection for R5 and explain why the parcel/hour scan table cannot directly list across an entire site. When should you add shards?
3. Calculate scan counts and raw bytes for the hottest parcel in **one hour** and **one day** at sustained peak load. Explain why those are not SSTable byte counts.
4. A scan occurs at 12:00 on Nov 01 and reaches the server at 12:00 on Nov 03. With 7-day retention from `scanned_at`, what remaining TTL is written?
5. If an API views scans in a 6-hour sliding window, up to how many hourly buckets can be touched? How should pagination and merging work?
6. A `FAILED` scan succeeded in the parcel/hour table but failed to write to the site/day table. Describe how to detect, retry, and prevent duplicate rows.
7. For R6, why should you not scan all parcel/hour partitions on the transactional Cassandra cluster for every report? Choose an analytical data approach and state reconciliation needs.

**Reference guidance:**

- R1: `orders_by_id` with `PRIMARY KEY ((tenant_id, order_id))`.
- R2: keyed by `(tenant_id, customer_id, month_bucket)` and clustered `created_at DESC, order_id DESC`.
- R3: keyed by `(tenant_id, parcel_id, hour_bucket)` and clustered `scanned_at DESC, scan_id DESC`.
- R4: keyed by `(tenant_id, user_id, day_bucket)` and clustered `occurred_at DESC, event_id DESC`.
- R5: projection keyed by `(tenant_id, site_id, day_bucket, shard_id)` clustered `scanned_at DESC, scan_id DESC` storing only FAILED scans, with shard/fan-out limits.
- At 25 scans/s: **90,000 scans/hour**, roughly **72 MB raw/hour**; **2,160,000 scans/day**, roughly **1,728 MB raw/day** (~1.73 GB). That excludes keys, metadata, indexes, compression, TTLs, tombstones, and RF.
- A scan arriving two days late has roughly **five days of TTL** left from event time; a 6-hour sliding window can touch **seven hourly buckets**.
- R6 is a long-term aggregation problem; stream accepted events through a durable pipeline into a dedicated OLAP/aggregate store, handling duplicates and reconciling counts per site/week.

## Conclusion

These three examples—orders, user activity, and device data—show that **with the same Cassandra engine, no single primary key fits every read path**. Orders distinguish current state from customer/status lists; activity requires per-user or per-session timelines; telemetry requires small buckets to control load plus separate projections for site-level alerts. Sound design begins with **query contracts, routing keys, clustering order, and growth bounds**, before deciding table counts, TTLs, consistency levels, and operational strategies. Verify with concrete CQL, fault testing, and measurements on the hottest partitions before declaring a model production-ready.
