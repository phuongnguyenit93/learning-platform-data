# Systematizing the Relationship Between Document, Index, Aggregation, and Topology in MongoDB

## 1. One Unified Picture Instead of Four Separate Topics

When designing with MongoDB, the following questions often arise:

- **Document:** Which fields should each record contain? Should an array of rooms be embedded inside a listing, or stored in a separate collection?
- **Index:** What index is needed for queries searching listings by tenant, status, city, and creation time?
- **Aggregation:** How can we count views, calculate revenue, or compute city-level statistics without pulling all documents into the application?
- **Topology:** Can a single replica set handle the traffic? When is sharding required? How do we avoid queries scanning every shard?

These decisions depend on one another. A document model may simplify queries yet cause arrays to grow unboundedly. An index may speed up searches yet slow down writes. An aggregation may compute accurate reports yet consume excessive RAM/disk. A shard key may distribute writes well yet force tenant-scoped queries to run across multiple shards.

End-to-end thinking:

~~~text
Business requirements + SLO + data volume
                   |
                   v
           Access patterns
                   |
         +---------+----------+
         |                    |
         v                    v
   Document model        Read/write shapes
         |                    |
         +----------+---------+
                    |
                    v
             Index design
                    |
                    v
          Query / aggregation
                    |
                    v
         Replica set / sharding
                    |
                    v
     Explain, profiler, metrics, tests
                    |
                    v
           Refine the design
~~~

**There is no optimal document/index/aggregation/topology choice independent of the workload.** A reliable system is designed around how it actually reads and writes data, then verified with execution plans and measured metrics.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the causal relationship between **document shape, access pattern, index, aggregation, and topology**.
2. Choose between **embedding and referencing** based on shared lifecycle, size, update frequency, cardinality, and element count.
3. Design **compound/multikey/partial/unique/TTL indexes** tied to query shapes and write cost.
4. Predict why **$match/$sort/$group/$lookup/$unwind/$facet** increase or decrease cost.
5. Distinguish **index-backed query**, **blocking aggregation**, **application-side join**, and **materialized summary**.
6. Understand the roles of **replica set, primary/secondary, read preference, read/write concern, elections, and rollback**.
7. Select or evaluate a **shard key** in terms of read targeting, write distribution, cardinality, hot spots, and data locality.
8. Build a decision matrix for CRUD, search, analytics, and multi-tenant workloads.
9. Use **mongosh** in a three-collection lab to compare multiple approaches.
10. Build a verification plan with **explain("executionStats"), metrics, tests, rollout, and rollback**.

> **Context:** This lesson belongs to **Database Engine Document MongoDB → Summary and Reference**. It is a synthesis lesson and does not require you to have read previous lessons. Examples use a multi-tenant rental listing application; do not interpret this to mean MongoDB is only for this domain. Features, limits, and optimizations vary by MongoDB version/FCV/topology, so always cross-check official documentation during implementation. The lab only writes to **mongo_system_map_lab_469** with collections suffixed **_469**; do not run topology-manipulation commands or delete production data.

## 2. Four Layers Are Four Different Types of Decisions

| Layer | Central Question | Typical Unit to Optimize | Consequence of Wrong Choice |
| --- | --- | --- | --- |
| **Document** | How is data grouped or split? | A document and relationships between documents | Heavy query joins, unbounded arrays, update contention |
| **Index** | How to access data faster than scanning? | Index keys, sort order, selectivity | COLLSCAN, blocking SORT, write amplification |
| **Aggregation** | How to compute results from a document set? | Stages, group cardinality, join fan-out | RAM/disk spill, oversized output, incorrect results |
| **Topology** | Which nodes handle data and reads/writes? | Replica members, shards, routing | Hot primary/shard, scatter-gather, lag, unavailability |

One layer cannot substitute for all other layers:

- Adding an index does not make a document containing a 20 MiB array valid.
- Sharding does not fix a `$group` query using `$push` that merges all documents into a single output BSON document.
- Embedded documents do not automatically reduce write counts if the parent is continuously updated.
- Choosing a `secondary` read preference does not guarantee newly written data is immediately visible.
- Aggregation `$lookup` does not eliminate the cost of an unindexed join or one distributed across shards.

### 2.1. Quantities to Monitor

~~~text
Document size            | BSON size and growth rate
Read amplification       | How many documents/bytes must be read per request
Write amplification      | How many index/data changes per write
Index selectivity        | How many records are filtered by predicates
Aggregation state        | Number of group keys, sort entries, joined items
Network amplification    | How much data moves between app/nodes/shards
Shard skew               | Data/traffic imbalance across shards
Consistency requirement  | Whether results must see recent writes or a snapshot
SLO                      | p95/p99 latency, throughput, availability, cost
~~~

Good design is not "more indexes make everything faster," but optimizing total costs against prioritized SLOs.

## 3. Start From the Workload, Not From the Collection

Suppose a service has the following operations:

| ID | Behavior | Frequency | Characteristics |
| --- | --- | --- | --- |
| Q1 | View a listing detail by ID and tenant | Very high | Single-document read, low latency |
| Q2 | Search PUBLISHED listings by city and newest first | High | Filter + sort + pagination |
| Q3 | Update price/status of a listing | Medium | Atomic single-document update |
| Q4 | Update rooms or amenities | Medium | Embedded array update |
| Q5 | Record view events | Very high | Append-heavy, many small documents |
| Q6 | Count views/listing in a day | Medium | Range scan + group |
| Q7 | View bookings by tenant and listing | High | One-to-many relationship that can grow |
| Q8 | Monthly revenue report | Low | Data-heavy aggregation |

For each workload, record:

- **Filter fields:** `tenantId`, `listingId`, `status`, `cityCode`, `createdAt`...
- **Sort fields and sort direction:** `createdAt DESC`, `_id DESC`.
- **Projection:** which fields are actually needed.
- **Page/limit:** one record, 20 records, or exporting all records.
- **Cardinality:** how many rooms, bookings, and view events a listing has.
- **Write frequency:** how many updates and inserts occur per day.
- **Consistency:** whether read-your-writes, transactional invariants, or snapshots are required.
- **Growth:** document count, size, retention over time.
- **Tenant isolation:** where permissions are enforced.
- **Latency/cost target:** p99 and resource limits.

This is the **access-pattern inventory**. Skipping the inventory makes it easy to design a schema that looks clean on paper but is slow in production.

## 4. End-to-End Case Study: Three Types of Data

The rental application has:

1. **listings:** property listings, metadata, rooms, status.
2. **view_events:** append-only view events, growing very rapidly.
3. **bookings:** viewing appointment requests, with business workflow states and history.

~~~text
Tenant
  |
  +-- Listings
  |      |
  |      +-- rooms[]        Embedded: usually read together with listing
  |      +-- tags[]         Embedded: bounded count
  |
  +-- View events          References listingId
  |      |
  |      +-- time / event type / device
  |
  +-- Bookings             References listingId, tenantId
         |
         +-- status, requestedAt, revision
~~~

Initial rationale:

- **rooms** are relatively small elements, usually displayed alongside the listing and sharing its lifecycle. They can be embedded if their count is bounded.
- **view_events** grow without bound with traffic; do not embed them in `listing` due to document growth, contention, and the BSON size limit.
- **bookings** have their own workflow, indexes, permissions, and update frequency; they are usually separated into their own collection storing `listingId`/`tenantId` for querying.

This is an assumption for the case study, not a mandatory template. If each room had independent inventory with thousands of updates per second, rooms might need their own collection.

## 5. Document Model: Unit of Read and Unit of Update

### 5.1. A Listing BSON Document

~~~javascript
{
  _id: "l469-001-01",
  labTag: "system469-v1",
  tenantId: "tenant-001",
  title: "Apartment with balcony",
  cityCode: "HCM",
  status: "PUBLISHED",
  monthlyRentVnd: NumberDecimal("9500000.00"),
  rooms: [
    { roomId: "bed-1", type: "BEDROOM", areaSqm: 18 },
    { roomId: "kitchen-1", type: "KITCHEN", areaSqm: 8 }
  ],
  tags: ["FURNISHED", "BALCONY"],
  createdAt: ISODate("2026-01-15T09:00:00Z"),
  revision: NumberLong("1")
}
~~~

MongoDB provides **single-document atomicity** for an update operation. This allows updating multiple fields in a listing together:

~~~javascript
db.listings_469.updateOne(
  { _id: "l469-001-01", tenantId: "tenant-001" },
  {
    $set: { status: "PUBLISHED", monthlyRentVnd: NumberDecimal("9700000.00") },
    $inc: { revision: NumberLong("1") }
  }
);
~~~

In the actual lab, include `labTag` as shown in the commands below. **Single-document atomicity does not automatically prevent lost updates between two concurrent writes**, so you still need revision/CAS or purpose-built atomic operators.

### 5.2. Embedding Reduces Read Joins

For a detail API needing listing + rooms:

~~~text
Embedded:
  1 query -> 1 listing BSON -> rooms[] already present

Referenced:
  query listing
  query rooms by listingId
  or $lookup in aggregation
~~~

Embedding is generally advantageous when related data:

- Is read together.
- Has a bounded size/count.
- Shares the parent's lifecycle.
- Does not have complex differing permissions or retention policies.
- Requires updating multiple fields atomically within a single root document.

### 5.3. Referencing Avoids Unbounded Growth

Do not store:

~~~javascript
{
  _id: "listing-x",
  views: [
    // One element per view across multiple years
  ]
}
~~~

As view rates rise, array bloat, write contention, and the BSON document size limit become bottlenecks. Separate them:

~~~javascript
{
  _id: "evt-1",
  tenantId: "tenant-001",
  listingId: "listing-x",
  createdAt: ISODate("2026-01-15T09:01:00Z"),
  eventType: "VIEW"
}
~~~

When total views need to be displayed, you can aggregate or maintain a controlled summary.

### 5.4. Trade-offs of Embedding Data

| Question | Embedding Tends to Fit | Referencing Tends to Fit |
| --- | --- | --- |
| Maximum element count | Small/bounded | Very large or unbounded |
| Read with parent | Almost always | Rarely |
| Updates per element | Low/moderate | Very high/independent |
| Shared lifecycle | Yes | No |
| Atomic update | Single root document | Multiple documents may require a transaction |
| Metadata duplication | Reduces joins | May need to read multiple sources |
| Querying by element | Multikey index may help | Index child collection independently |
| Shard placement | All embedded data stays with parent | Can be distributed independently by shard key |

### 5.5. 16 MiB Is Not a "Target Size"

The standard BSON document limit is **16 MiB**. However, you should not wait until documents approach that limit before splitting. A document of even a few MiB can already cause:

- Transferring excess data for detail/list APIs.
- Wasting cache/working set memory.
- Increasing update and network overhead.
- Projection/index difficulties and contention.

Choose data thresholds suited to the workload and measure the document-size distribution.

### 5.6. Duplicated Data Can Be Intentional

An event containing **cityCodeAtView** captures a snapshot of the city at the moment the view occurred:

~~~javascript
{
  listingId: "l469-001-01",
  cityCodeAtView: "HCM",
  createdAt: ISODate("2026-01-15T09:01:00Z")
}
~~~

If the listing later changes its city, historical reports remain accurate to the event. However, a snapshot field requires a clear contract regarding timing, source, and migration; do not blindly copy every field just to "denormalize."

## 6. The Document Model Determines Which Indexes Are Needed

### 6.1. Querying Listings by City and Status

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
}).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

A candidate index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  cityCode: 1,
  createdAt: -1,
  _id: -1
}
~~~

The index is designed around **equality predicates before sort keys** for this workload. If the API does not filter by `cityCode`, an index with `cityCode` before `createdAt` may not support the expected sort order. You will need another index for the common query without a city filter, or adjust the requirements.

### 6.2. Indexes Change With the Data Model

If `cityCode` is nested inside:

~~~javascript
{ address: { cityCode: "HCM" } }
~~~

then the query/index path is:

~~~javascript
{ "address.cityCode": 1 }
~~~

You cannot rename Java field names and assume old MongoDB indexes will migrate automatically. Schema migration and index migration are two parts of the same rollout.

### 6.3. The rooms Array Leads to a Multikey Index

~~~javascript
db.listings_469.createIndex({
  tenantId: 1,
  "rooms.type": 1,
  "rooms.areaSqm": 1
});
~~~

MongoDB creates a **multikey index** when an indexed path traverses an array. This helps certain array queries but comes with its own constraints.

Specifically:

- Queries requiring multiple conditions **on the same array element** should consider **$elemMatch**.
- Multikey indexes have restrictions on compound key patterns containing multiple independent arrays; you cannot arbitrarily create a compound index over two array fields.
- A unique multikey index **does not guarantee `roomId` uniqueness within the same listing** as required by typical business invariants.
- Sort behavior and index bounds on array fields must be analyzed using `explain`.

### 6.4. Counting Rooms Using an Array Without a Join Query

If the `rooms` array is small:

~~~javascript
{
  $project: {
    title: 1,
    roomCount: { $size: "$rooms" }
  }
}
~~~

However, if the list API frequently requests `roomCount` and `rooms` is very large, consider a maintained counter field with an invariant, or splitting the data. Adding an aggregate count field introduces **consistency maintenance** whenever `rooms` changes.

## 7. From Predicates to Compound Indexes: Lookup Diagram

~~~text
Business request
  tenant=001, PUBLISHED, HCM
  order newest first
  pageSize=20
         |
         v
Predicate equality:
  tenantId, status, cityCode
         |
         v
Sort:
  createdAt DESC, _id DESC
         |
         v
Index candidate:
  tenantId ASC
  status ASC
  cityCode ASC
  createdAt DESC
  _id DESC
         |
         v
EXPLAIN:
  Does it avoid COLLSCAN/blocking SORT?
  How many keys/docs examined per returned item?
~~~

### 7.1. ESR Heuristic

**Equality–Sort–Range (ESR)** is a useful heuristic when ordering fields in a compound index:

1. Equality predicates narrow down the group of documents.
2. The sort suffix can allow returning ordered data.
3. Range predicates bound or filter additional data.

This is **not an absolute law**. A highly selective range predicate sometimes deserves priority; collation, query shape, multikey rules, and the query optimizer can alter the best plan.

### 7.2. Prefix Matters

An index:

~~~javascript
{ tenantId: 1, status: 1, cityCode: 1, createdAt: -1 }
~~~

typically helps with prefixes `tenantId`, `tenantId+status`, or `tenantId+status+cityCode`. A query filtering only on **cityCode** can rarely use the leading portion of the index as an optimal access path.

Similarly, if a query omits `status` while sorting by `createdAt`, this index does not automatically provide the desired sort order because the middle index keys are not bound by equality.

### 7.3. Stable Sort

If multiple documents share the same `createdAt`, sorting only by **createdAt DESC** does not provide a total ordering. Add **_id DESC** as a tie-breaker:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

This also affects **keyset pagination** and the index suffix, not just display order.

### 7.4. Partial Index

If the system primarily searches active listings:

~~~javascript
db.listings_469.createIndex(
  {
    tenantId: 1,
    cityCode: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "active_published_listings",
    partialFilterExpression: {
      status: "PUBLISHED"
    }
  }
);
~~~

This is a **partial index** candidate for `PUBLISHED` documents. Queries must include matching predicates so the optimizer can use the index without missing records. The index does not contain `DRAFT` documents, so it cannot be arbitrarily used for queries across all statuses.

In the lab, creating this index still does not automatically exclude soft-deleted `PUBLISHED` records: the schema and partial filter predicate must match the exact active condition in use.

### 7.5. Unique Index

Bookings with a per-tenant idempotency key:

~~~javascript
db.bookings_469.createIndex(
  { tenantId: 1, requestKey: 1 },
  { unique: true, name: "uq469_tenant_request_key" }
);
~~~

This protects a key combination on the server. However:

- Documents missing `requestKey` or having `null` follow unique index semantics that must be accounted for.
- On a sharded collection, **unique indexes have requirements tied to the shard key**; do not assume cluster-wide uniqueness for an arbitrary index.
- Do not use a unique index as a substitute for authorization or retry payload validation.

### 7.6. TTL Index

Old events may require a retention limit:

~~~javascript
db.view_events_469.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 60 * 60 * 24 * 90 }
);
~~~

TTL deletion is **asynchronous** and does not occur at the exact millisecond of expiration. For legal retention or audit requirements, you must have exact policies, archiving, and verification. **Do not create a TTL index on lab data before checking retention implications**, because it can wipe practice data whose creation timestamps are old.

### 7.7. Index Cost on the Write Path

Every additional index incurs:

- Disk footprint.
- Memory/cache footprint.
- Write amplification when indexed fields change.
- Build and maintenance overhead.
- Potential impact on replication/lag.

Indexes should derive from real workloads and have their usage monitored, rather than "indexing every field" to feel safe.

## 8. Explain: Connecting Indexes to Actual Execution

Run:

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
}).sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Key metrics to inspect:

| Metric/Indicator | Question |
| --- | --- |
| **winningPlan** | Does it use IXSCAN or COLLSCAN? Is there a SORT stage? |
| **totalKeysExamined** | How many index keys were scanned? |
| **totalDocsExamined** | How many documents were fetched? |
| **nReturned** | How many results were returned? |
| **executionTimeMillis** | Server-side execution time for that measurement? |
| **indexBounds** when present | Are the index ranges as narrow as expected? |
| **usedDisk/spills** when present | Did any stage spill to temporary disk? |

**The ratio of keys/documents examined to `nReturned`** is an indicator for spotting wasted scans, though no single threshold fits all aggregations. For grouped queries, a low `nReturned` is normal even when scanning all qualifying documents.

### 8.1. Index Exists, Yet the Planner Does Not Use It

Possible reasons:

- The collection is very small; COLLSCAN is cheaper.
- The predicate is not selective enough.
- The query lacks the index prefix.
- Collation mismatch.
- Earlier sort or aggregation stages break indexed ordering.
- Multikey constraints.
- Statistics/planner/version differ from expected environment.

Do not force an index hint in production just to make `explain` output look "pretty" without benchmarking and verifying correctness.

### 8.2. Covered Query

If projection, filtering, and sorting can all be served from index keys without fetching documents, read load decreases. However, do not treat this as an absolute goal; an overly wide index designed to cover every field can increase write/disk cost and slow down the overall system.

### 8.3. Explain Does Not Measure Full Application Latency

Explain does not fully capture:

- Connection pool queuing.
- Serialization and network transit to the app.
- HTTP/auth processing.
- Contention with other workloads.
- Cache warm/cold state and peak traffic.

Therefore, measure **query metrics alongside end-to-end p95/p99**.

## 9. Aggregation: Turning Access Paths Into Statistics

Suppose the **view_events** collection stores individual events:

~~~javascript
{
  _id: "ev469-0001",
  tenantId: "tenant-001",
  listingId: "l469-001-01",
  eventType: "VIEW",
  createdAt: ISODate("2026-01-15T09:05:00Z")
}
~~~

Requirement: top listings by `VIEW` count for a single day.

~~~javascript
db.view_events_469.aggregate([
  {
    $match: {
      tenantId: "tenant-001",
      eventType: "VIEW",
      createdAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-16T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$listingId",
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

Notes:

1. **$match** narrows down by tenant/type/time.
2. Indexes help select documents entering the pipeline.
3. **$group** accumulates views per `listingId`.
4. Sorting runs on **computed groups**, not all raw events.
5. Limit takes the top 10 groups after exact counts are calculated.

### 9.1. Why Do Indexes Still Matter for Aggregation?

Aggregation is not a black box running "outside of indexes." Early stages like `$match` and certain `$sort` stages can leverage indexes. When the optimizer pushes down suitable predicates, the number of documents and bytes entering blocking stages drops.

### 9.2. Why Can't Indexes Do Everything?

An index can bound the **input range**, yet exact counts/groups may still require scanning all qualifying events. If there are 20 million `VIEW` events in a month:

- Indexes prevent scanning events outside the target tenant/time window.
- `$group` must still accumulate view counts per listing or rely on supported optimizations.
- Maintaining a **daily summary** can reduce read costs for frequent reports.

### 9.3. $unwind and Multikey

~~~javascript
[
  { $unwind: "$rooms" },
  {
    $group: {
      _id: "$rooms.type",
      n: { $sum: 1 }
    }
  }
]
~~~

After `$unwind`, a listing with two rooms produces two rows. If the goal is **number of listings with a bedroom**, counting after `$unwind` can double-count listings with multiple bedrooms. To get accurate numbers, define the counting unit clearly: **rooms** or **distinct listings**.

### 9.4. $lookup and the Referencing Model

If events only store `listingId`, a report needing listing titles can use `$lookup`:

~~~javascript
{
  $lookup: {
    from: "listings_469",
    localField: "_id",
    foreignField: "_id",
    as: "listing"
  }
}
~~~

The snippet above assumes an earlier stage already grouped by `listingId`. Join cost depends on:

- Foreign key/index.
- Cardinality.
- Projected fields.
- Tenant isolation.
- Sharded topology and routing/placement.

For multi-tenant systems, joining solely on ID can be insufficient if IDs are not globally unique or tenant boundaries require explicit filtering. Real applications must verify both **tenantId** and read permissions.

### 9.5. $facet and Oversized Single Documents

`$facet` returns a single result document containing arrays. If a data branch holds millions of documents, it can exceed:

- **$facet's** own memory limit (facet results cannot spill to disk).
- The final **16 MiB BSON output document** limit.

Do not use `$facet` to pack all paginated listings into one document. Bound every branch or separate detail and summary APIs.

### 9.6. $setWindowFields

Window functions fit rolling metrics or running totals **per row**. However, if you only need totals per day or listing, `$group` is usually simpler. Partition/order/window state can consume significant memory; choose the right semantics before optimizing.

### 9.7. 100 MB Memory Limit and allowDiskUse

Many blocking stages have per-stage memory limits and can spill temporary files when permitted. Since MongoDB 6.0, **allowDiskUseByDefault** governs default behavior; the **allowDiskUse** command option can override it where supported.

However:

- **allowDiskUse does not lift the 16 MiB BSON output limit**.
- Some accumulators such as `$push` have their own memory restrictions.
- `$facet` does not spill its 100 MB facet result document.
- Spilling can increase disk I/O and latency.
- Memory limits may vary across versions (for instance, per-operation memory limits in newer versions).

To fix memory pressure, prioritize changing query shape and indexes rather than merely enabling disk spill.

## 10. Aggregation and Summary / Materialized Views

### 10.1. Computing on Every Request

~~~text
GET /analytics/top-listings
  -> scan qualifying view_events
  -> group
  -> sort
  -> response
~~~

Simple, and data reflects the latest state per read semantics, but it can become prohibitively expensive when the same report runs repeatedly.

### 10.2. Scheduled or Event-Driven Summaries

~~~javascript
{
  _id: "tenant-001|l469-001-01|2026-01-15",
  tenantId: "tenant-001",
  listingId: "l469-001-01",
  dayUtc: ISODate("2026-01-15T00:00:00Z"),
  viewCount: NumberLong("125"),
  updatedAt: ISODate("2026-01-16T00:02:00Z")
}
~~~

~~~text
Raw view_events
      |
 Batch/stream aggregation
      |
 daily_view_summary
      |
 Dashboard reads small number of summaries
~~~

Trade-offs:

- Cheaper reads.
- Additional cost to write/maintain summaries.
- **Freshness lag** and reconciliation requirements.
- Late events require updating existing buckets.
- Duplicate events/retries can double-count if consumers are not idempotent.

### 10.3. $merge Is Not a Side-Effect-Free Optimization

A pipeline ending in **$merge** or **$out** mutates the target collection. Do not append write stages just to "make an aggregation faster" in production. You must verify:

- Write permissions and target namespace.
- Key uniqueness and `on`/`whenMatched` semantics.
- Idempotency on job reruns.
- Overlapping job schedules.
- Memory/disk/concurrency.
- Rollback and reconciliation.

### 10.4. When Summaries Beat Raw Queries

Pre-aggregation helps when:

- Dashboards are read very frequently.
- Raw data is huge and append-heavy.
- The business tolerates several minutes of lag.
- Count reconciliation mechanisms exist.

If decisions require millisecond-level freshness and updates arrive from multiple sources, analyze consistency and transaction semantics rather than assuming async summaries suffice.

## 11. Topology Level 1: Replica Set and Reliability

~~~text
                 Application
                      |
                  Driver URI
                      |
          +-----------+-----------+
          |           |           |
        Primary    Secondary A  Secondary B
        writes       replica      replica
          |             ^           ^
          +----- oplog --+-----------+
~~~

A **replica set** maintains multiple copies of data, typically with one primary accepting writes and secondaries replicating them. When the primary becomes unavailable, an election can select a new primary depending on configuration and cluster conditions.

### 11.1. A Replica Set Does Not Partition Data to Scale Writes

Each data-bearing member of a replica set generally holds a full copy of the replica set's dataset. Adding secondaries:

- Improves high availability and redundancy.
- Can serve suitable read workloads.
- Does not distribute a heavy write workload across multiple independent primaries.

If a single primary hits write throughput limits or data size outgrows a replica set, sharding should be evaluated.

### 11.2. Read Preference

| Read Preference | Characteristics |
| --- | --- |
| **primary** | Reads from the primary, typically matching application consistency expectations |
| **primaryPreferred** | Prefers primary, falls back per semantics |
| **secondary** | Reads from secondaries; may observe stale data |
| **secondaryPreferred** | Prefers secondary, falls back when needed |
| **nearest** | Selects member by latency/driver criteria, not automatically latest data |

Secondary reads can offload the primary for suitable workloads, but **replication lag** means recently written data may not appear immediately. Read concerns, sessions, and causal consistency shape the actual guarantees.

### 11.3. Write Concern

**w:1**: write is acknowledged per single-member semantics (typically the primary).  
**w:"majority"**: waits for acknowledgment by a majority per write concern semantics, offering stronger durability across certain failover/rollback scenarios.

Do not treat `w:"majority"` as a backup or a guarantee against data loss in every disaster. Understand journaling, defaults, timeouts, and backup/restore policies.

### 11.4. Read Concern

Levels such as **local, majority, snapshot, linearizable** carry distinct guarantees and prerequisites. Avoid using the vague term "consistent."

- **local** may observe data not yet majority-committed depending on circumstances.
- **majority** reads majority-committed data per its semantics.
- **snapshot** supports reading a consistent snapshot in supported contexts.
- **linearizable** has specific conditions and costs and is not the default for general reads.

Selection must match the workflow. For instance, reading a booking's status immediately after confirmation requires defining **read-your-writes** expectations, session/causal semantics, and read preference.

### 11.5. Do Not Confuse Replication With Backup

An accidental delete replicates very quickly to all members. A replica set does not replace:

- Scheduled backups and retention.
- Restore drills.
- Point-in-time recovery when required.
- Permission separation.
- Disaster recovery plans.

### 11.6. Indexes on a Replica Set

Indexes must be built and maintained across members per server procedures; index operations impact:

- Disk, CPU, and write amplification.
- Replication and workload capacity.
- Query latency if traffic fails over to a secondary.

Do not build dozens of large indexes during an incident when disk capacity is already strained.

## 12. Topology Level 2: Sharded Cluster

~~~text
                   Application
                        |
                      mongos
                        |
          +-------------+-------------+
          |             |             |
        Shard A       Shard B       Shard C
      (replica set) (replica set) (replica set)
          |             |             |
       Data subset   Data subset    Data subset

        Config server replica set
             (cluster metadata)
~~~

Sharding distributes data across multiple **shards**, where each shard is typically a replica set. **mongos** receives operations and routes them based on the shard key and metadata; the config server replica set stores cluster metadata.

### 12.1. Two Different Scaling Dimensions

| Need | Replica Set | Sharding |
| --- | --- | --- |
| HA/failover | Primary goal | Each shard is usually a replica set |
| Scaling suitable reads | Can use secondaries | Can spread read workload across shards |
| Scaling total data size | Every member holds full replica set data | Data distributed across shards |
| Scaling write throughput | Primary is the write bottleneck | Writes can distribute by shard key |
| Cross-node query complexity | Relatively low | Introduces routing, merge, and scatter-gather |
| Operations | Elections/replication/backups | Adds balancing/shard key/chunks/metadata |

Adding shards will not fix a request that must scan **all** data if the shard key and query do not enable targeting.

### 12.2. Shard Key Is a Long-Term Decision

The shard key determines:

- Which shard holds each document.
- Whether reads/writes target a single shard.
- Data distribution and hot spots.
- Chunk/range management and balancing.
- Certain unique index and update constraints.
- Co-location of related data.

Do not pick a shard key solely because a field has high cardinality while ignoring query patterns.

### 12.3. Range-Based Shard Key

For example, based on `tenantId`:

~~~text
Shard key: { tenantId: 1 }
~~~

Potential benefits:

- Queries with `tenantId` equality can be targeted appropriately.
- Tenant-related documents gain locality under range policies.

Risks:

- An extremely large or hot tenant can cause skew.
- If one tenant generates heavy writes, spreading a single tenant across multiple shards is limited by shard key cardinality and chunks.
- Monotonic keys can create hotspots when inserts concentrate on the newest range.

### 12.4. Hashed Shard Key

~~~text
Shard key: { tenantId: "hashed" }
~~~

Hashing distributes key values more evenly when many distinct values exist, reducing certain sequential hot spots. However:

- A very hot tenant still concentrates many requests on the shard owning its hashed value.
- Range queries on `tenantId` do not benefit as they would from a range-based key.
- It does not automatically co-locate geographic or logically related groups on the same shard as desired.

**Hashing is not a magic splitter for a single hot tenant across multiple shards** if all documents of that tenant share the same hashed key value.

### 12.5. Compound Shard Key

You may consider adding a high-dispersion component such as `listingId` or a bucket, depending on query patterns and transaction/locality needs:

~~~text
{ tenantId: 1, listingId: 1 }
~~~

Do not assume it is universally better than `tenantId` alone; reads specifying only `tenantId` may target multiple chunks/shards, and documents for the same listing may or may not be co-located depending on the actual design.

### 12.6. Targeted vs Scatter-Gather

~~~text
Query with shard key equality
  -> mongos can target the shard holding the key

Query missing shard key
  -> may have to broadcast to multiple shards
  -> merge results across the cluster
~~~

An index on each shard **does not eliminate scatter-gather**. Each shard may execute its index efficiently, yet the overall request still waits on multiple shards, transfers more network results, and merges/sorts them.

### 12.7. The Balancer Does Not Solve Every Hot Key

The balancer moves chunks/ranges to balance data size, but:

- A single highly active key can still cause a hotspot.
- Tenant/traffic skew must be viewed through workload metrics, not just byte counts.
- Chunk migrations incur operational overhead.

Monitor per-shard CPU/IOPS, ops/s, data size, and routing distribution.

### 12.8. Sharding and Uniqueness

Unique constraints on sharded collections carry requirements regarding the shard key and index prefix per the MongoDB manual. A business uniqueness constraint such as **(tenantId, requestKey)** must be designed alongside the shard key/topology or enforced via another architecture; do not just call `createIndex(unique:true)` and assume cluster-wide enforcement under every setup.

## 13. Relationship Between Document and Shard Key

An embedded document always resides with its root document:

~~~text
Listing document
  _id, tenantId, rooms[]
           |
         shard by root key
           |
  rooms[] lives inside the same BSON document
~~~

This makes updating `rooms` atomic within a single root document and avoids cross-shard joins. However, if `rooms` grows too large or faces heavy concurrent updates, all writes contend on the same root document.

Conversely:

~~~text
listings collection: listingId
rooms collection: listingId + roomId
~~~

lets `rooms` grow independently, but requires:

- Lookup indexes on `rooms`.
- Deletion/cascade policies.
- Consistency handling across multi-document changes.
- Shard key alignment if locality or targeted joins are needed.

### 13.1. One-to-Many Has Two Independent Dimensions

Ask both simultaneously:

1. **Relationship size:** 2 rooms or 2 million view events?
2. **Change frequency:** once a month or thousands of updates per second?

This is why two relationships that both look like "a listing has many X" may require very different models.

### 13.2. Tenant Partitioning Is Not Just Schema

`tenantId` must appear consistently across:

- Authorization.
- Query filters.
- Relevant compound indexes.
- Shard key decisions where applicable.
- Aggregation `$match` and `$lookup` joins.
- Backups, restores, and retention policies.
- Logs/metrics with bounded cardinality.

Having `tenantId` in the document while **omitting it from queries** provides neither routing optimization nor isolation.

## 14. Aggregation on a Sharded Cluster

~~~text
           Query from app
                  |
                mongos
                  |
      +-----------+-----------+
      |                       |
   Shard A                 Shard B
  $match/$group           $match/$group
      |                       |
      +-----------+-----------+
                  |
             Merge stage
             sort/limit
                  |
                Client
~~~

MongoDB can split a pipeline between shards and a merging pipeline. Where each stage executes depends on server version, topology, and semantics.

### 14.1. Pushing Filtering to Shards

An early `$match` containing the shard key and selective predicates can reduce:

- Data scanned.
- Documents transferred between nodes.
- Merge-stage memory.

However, if the query lacks the shard key, `mongos` may still route it to multiple shards.

### 14.2. $group Can Compute Partial Results

For associative accumulators, the server can compute partial aggregations on shards and then merge them. For example, view counts per listing:

~~~text
Shard A: listing-1 -> 120 views
Shard B: listing-1 -> 80 views
Merge:   listing-1 -> 200 views
~~~

However, pipelines with order-dependent operations or non-combinable state have their own constraints; do not assume every `$group` automatically optimizes cleanly.

### 14.3. $sort Requires Merging Order

A global sort or top-K may require merging sorted streams or performing a blocking sort at the merge site. Knowing "every shard has an index" does not guarantee the query avoids merge overhead.

### 14.4. Cross-Shard $lookup

`$lookup` efficiency depends on whether the foreign collection is sharded, predicates/indexes, server version, and data placement. Joining sharded foreign collections is supported in modern versions, **but it is not free**. Denormalization or pre-aggregation is sometimes a better choice.

### 14.5. Resharding Is an Operational Campaign

If the current shard key causes hotspots, modern MongoDB versions provide resharding capabilities under specific conditions. This should not be treated like swapping a simple index: evaluate disk, I/O, timeline, application compatibility, and rollback.

## 15. Consistency Across All Four Layers

A booking feature requires:

1. Creating a `REQUESTED` booking.
2. Preventing two conflicting bookings per policy.
3. Saving the `CONFIRMED` status.
4. Reads immediately after confirmation seeing the updated state.
5. A booking statistics dashboard allowed to update with lag.

These expectations are not identical.

### 15.1. Within a Single Document

If a listing stores availability and needs an atomic update on that same document:

~~~javascript
db.listings_469.updateOne(
  {
    _id: listingId,
    tenantId,
    availableSlots: { $gt: 0 }
  },
  {
    $inc: {
      availableSlots: -1,
      revision: NumberLong("1")
    }
  }
);
~~~

This is a conceptual example; **the sample lab listing does not contain `availableSlots`**. An atomic conditional update can protect a simple invariant within one root document.

### 15.2. Across Multiple Documents/Collections

If updating listing availability and inserting a booking must happen **in the same transaction**, use a multi-document transaction on a supported deployment, or design an event/outbox/saga flow when appropriate. Transactions carry overhead and specific semantics, especially cross-shard; do not use them everywhere simply out of habit.

### 15.3. Secondary Reads

After a booking is confirmed on the primary, a secondary may not have replicated that write yet. Thus, a GET immediately after POST/PATCH can observe the old state if the app reads from a secondary without an appropriate consistency policy.

### 15.4. Aggregation Summaries Have Their Own Lag

A materialized daily count refreshed every five minutes is an **eventually consistent view** by design, even if source bookings are majority-committed. Do not describe the dashboard count as real-time if the pipeline or consumer introduces lag.

### 15.5. Each API Should Have an Explicit Consistency Contract

| API | Example Expectation | Design Direction |
| --- | --- | --- |
| Confirm booking | State transition must be accurate | Atomic condition/transaction |
| Read booking right after confirm | Read-your-writes | Session/primary/read concern policy |
| Search listings | Brief update delay acceptable | Index + appropriate read preference |
| Analytics dashboard | 5-minute lag acceptable | Materialized summaries and freshness timestamp |
| Financial export | Auditable snapshot | Read concern/snapshot job/reconciliation |

Do not apply a single `readConcern`/`writeConcern` configuration across every API without knowing the business requirements.

## 16. Keyset Pagination in Relation to Indexes and Topology

### 16.1. Offset Pagination

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED"
}).sort({ createdAt: -1, _id: -1 })
  .skip(100000).limit(20);
~~~

Deep `skip` wastes work scanning discarded keys/records. When inserts or deletes occur near the start of the list between requests, offsets shift and can cause duplicate or missing items.

### 16.2. Keyset Using a Tuple

Sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

After the last returned tuple `(lastAt, lastId)`, the predicate is:

~~~javascript
{
  $or: [
    { createdAt: { $lt: lastAt } },
    {
      createdAt: lastAt,
      _id: { $lt: lastId }
    }
  ]
}
~~~

This logic applies to **DESC/DESC** ordering with matching BSON types. If sort directions change, the comparison operators must change accordingly.

### 16.3. Why pageSize+1?

Query up to **pageSize+1** documents:

- Return the first **pageSize** records.
- If an extra record exists, `hasNext=true`.
- Derive the next cursor from the **last returned record**, not from the extra record.

This is crucial to avoid skipping the record immediately after a page boundary.

### 16.4. Index for Keyset

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

If queries frequently include `cityCode` equality, an index including `cityCode` may be needed. In a sharded cluster, even a good index is insufficient if the cursor query lacks the shard key and has to merge results across shards.

### 16.5. Stable Order Is Not a Snapshot

Keyset pagination using an immutable `createdAt` and unique `_id` provides deterministic ordering. However, between two HTTP requests:

- Deleted documents disappear.
- Newly published `DRAFT`s behind the cursor can appear.
- Backdated inserts can appear.
- If a sort key is mutable, a record can shift positions.

**Keyset pagination does not freeze the dataset.** If a fixed export snapshot is needed, design a snapshot-consistent job/operation bounded by read history and suitable topology.

### 16.6. Cursors Are a Security Boundary

An opaque cursor should contain/bind:

- Tuple values with exact BSON types.
- Sort specification.
- Tenant derived from the authenticated principal.
- Filter fingerprint.
- Page-size policy.
- Expiry and token schema version.
- Integrity protection such as HMAC.

Plain Base64 does not prevent token tampering. Even with a signed token, the backend **must still enforce the tenant filter**.

## 17. Change Streams, Downstream Views, and Topology

MongoDB Change Streams emit events when source documents change on supported deployments (typically replica sets or sharded clusters).

~~~text
Booking write -> MongoDB
                     |
                Change Stream
                     |
              Event consumer
                     |
         Search index / summary / cache
~~~

### 17.1. When Are They Needed?

If a search index or dashboard must reflect changes to bookings/listings, a consumer can listen to change events and update the read model. However:

- Consumers can replay events or retry.
- Idempotency is required.
- Resume tokens, oplog retention, and lag must be monitored.
- Do not assume end-to-end exactly-once semantics.
- Schema evolution impacts event payloads and consumers.

### 17.2. Outbox Pattern

When a business event must be tied to a DB state transition, an outbox document can be written in the same transaction where appropriate, and a consumer publishes it to a broker. This mitigates certain **dual-write** failures between MongoDB and external messaging, at the cost of added complexity and mandatory idempotent consumers.

### 17.3. Should Read Models Share the Same Shard Key?

A summary collection may use a different shard key than its source collection because its access patterns differ. Decisions should examine:

- How summary writes are distributed.
- How dashboard reads filter and target shards.
- Whether cross-shard transactions are required.
- Tenant isolation and retention.

Do not copy the source shard key to every derived collection out of habit.

## 18. Cross-Layer Decision Matrix

| Workload | Document Model | Core Index | Aggregation | Topology/Consistency |
| --- | --- | --- | --- | --- |
| Detail listing + rooms | Embed bounded rooms | `_id`, tenant scope if needed | Little or none | Appropriate primary/read policy |
| Search newest PUBLISHED | Listing root document | tenant/status/city/time/_id | `$match`/`$sort`/`$limit` | Target shard key if sharded |
| High-frequency VIEW writes | Separate event | tenant/listing/time | None on write path | Evaluate write distribution |
| Top listing views/day | Raw events or summary | tenant/type/time/listing | `$group`/`$sort` | Batch/read replicas/shard merge |
| Booking workflow | Separate booking, revision | tenant/listing/status/time | Separate statistics | Atomic transitions/transactions when needed |
| Rapidly changing rooms inventory | Consider splitting rooms | listingId/roomId | `$lookup` if needed | Co-location vs independent writes |
| Large admin export | Cursor/batch | Filter/order keys | Projection/group as needed | Snapshot/read concern/async job |
| View events retention | Time-based events | TTL index if valid | Pre-archive summary | Disk/backup/legal policy |

This matrix is a starting point. Every choice must be validated against real sizes, query frequencies, hot keys, and SLOs.

## 19. Scenario A: Searching Millions of Listings

**Requirement:** Tenants manage millions of listings; users filter `PUBLISHED`, `cityCode=HCM`, and fetch the 20 newest listings.

### 19.1. Document

The listing root holds fields needed for list cards: `title`, `cityCode`, price, `status`, `createdAt`, thumbnail reference. `rooms` may be embedded, yet **the list API projects only needed fields**.

### 19.2. Index

Candidate:

~~~javascript
{
  tenantId: 1,
  status: 1,
  cityCode: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 19.3. Query

~~~javascript
db.listings_469.find({
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
}, {
  _id: 1, title: 1, cityCode: 1,
  monthlyRentVnd: 1, createdAt: 1
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 19.4. Topology

If the dataset fits comfortably within one replica set, sharding is not yet needed. If sharded, evaluate whether the shard key enables tenant filters to target specific shard(s). Scatter-gather across many shards can degrade p99 even when every shard has the index.

### 19.5. Verification

- Explain first and next pages.
- p95/p99 latency across tenant sizes.
- Index bytes and write overhead.
- Pagination consistency under concurrent inserts/deletes.
- Tenant isolation and response projection.

## 20. Scenario B: VIEW Analytics Growing by 100 Million Events/Day

**Requirement:** High-throughput view ingestion; dashboards need daily view counts per listing.

### 20.1. Document

Do not embed 100 million events inside listings. Store separate event documents with tenant/listing/time/type and only genuinely needed snapshot fields. If a time-series workload fits, evaluate a **time-series collection** per server version and constraints rather than assuming every event log must be time-series.

### 20.2. Index

Candidate:

~~~javascript
{ tenantId: 1, eventType: 1, createdAt: -1, listingId: 1 }
~~~

for reports filtering by tenant/type/time. A workload reading by `listingId`/time may need another index. Append-heavy workloads are sensitive to write amplification, so every index must justify its existence.

### 20.3. Aggregation

Group by `listingId`/day rather than `$push`-ing all events. You can use `$dateTrunc` in UTC or the business timezone.

### 20.4. Summary

If dashboards are queried continuously, maintain a daily summary:

~~~text
Raw events -> scheduled/stream group -> daily_view_summary
~~~

Late events and duplicates require dedicated handling and reconciliation; summaries carry a freshness SLA.

### 20.5. Topology

When write throughput exceeds a replica set or single shard, evaluate sharding based on distribution across tenant/listing/time. A shard key consisting solely of a monotonically increasing timestamp easily leads to a hot range. Hashed or compound keys involve trade-offs with range analytics; benchmark on realistic workloads.

## 21. Scenario C: Bookings and Multi-Document Invariants

**Requirement:** A viewing slot cannot be double-booked under policy; each booking transitions through `REQUESTED`/`CONFIRMED`/`CANCELLED`.

### 21.1. Document

Bookings have their own lifecycle, so a separate collection makes sense:

~~~javascript
{
  _id: "b469-001-01",
  tenantId: "tenant-001",
  listingId: "l469-001-01",
  requestedAt: ISODate("2026-01-15T10:00:00Z"),
  status: "REQUESTED",
  revision: NumberLong("1")
}
~~~

### 21.2. Index

Query bookings of a listing:

~~~javascript
{ tenantId: 1, listingId: 1, requestedAt: -1 }
~~~

If a unique booking key is needed, design a dedicated index matching business rules, tenant scope, and sharding constraints.

### 21.3. Concurrency

An `updateOne` filtering on **_id + tenantId + status + revision** can execute an atomic state transition within a single document. If an invariant spans listing availability and a booking insert, consider a transaction or a reservation token modeled in the same document depending on workload.

### 21.4. Read Concern/Preference

Right after confirmation, the UI must display the updated status according to the consistency contract. Do not route the GET to a lagging secondary and mistake stale data for a mapping or index bug.

### 21.5. Analytics

A monthly booking dashboard can tolerate different summary lag than the transactional workflow. Do not conflate the two consistency requirements.

## 22. Scenario D: Small Tenants and One Huge Enterprise Tenant

**Requirement:** 10,000 small tenants, plus one enterprise tenant generating 40% of total traffic.

### 22.1. Document

`tenantId` must always be present and authenticated. Collections can hold multi-tenant documents if isolation, retention, and access policies allow.

### 22.2. Index

Compound indexes leading with `tenantId` support common scoped queries. However, indexes alone do not isolate traffic from a hot tenant.

### 22.3. Topology

Sharding on **tenantId** alone distributes the 10,000 tenants, yet all traffic from the huge tenant remains concentrated. A hashed `tenantId` cannot split a single key value across multiple shards. Consider compound keys, hot-tenant placement, or zone strategies depending on the workload.

### 22.4. Analytics

A query grouping by tenant across all events can incur merge/sort overhead, especially when data spans multiple shards. Enforce quotas or async jobs for heavy enterprise reports.

### 22.5. Capacity

Measure not only data bytes per shard, but also **read/write ops per tenant, p99 latency, working set, and IOPS**.

## 23. Safe Lab: Three Collections, One Cohesive Story

### 23.1. Scope

Practice-only database:

~~~text
mongo_system_map_lab_469
  listings_469       24 listings / 3 tenants
  view_events_469    240 synthetic events
  bookings_469       12 booking requests
~~~

Each document carries **labTag:"system469-v1"**. The seed script can be rerun to **reset the exact fixture set matching those `_id`s** without dropping the DB or collections. If those IDs collide with foreign documents lacking `labTag`, upserts may fail with duplicate key errors instead of overwriting.

### 23.2. mongosh Seed

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_system_map_lab_469");
  const listings = lab.getCollection("listings_469");
  const events = lab.getCollection("view_events_469");
  const bookings = lab.getCollection("bookings_469");
  const tag = "system469-v1";
  const listingOps = [];
  const eventOps = [];
  const bookingOps = [];

  for (let tenantNo = 1; tenantNo <= 3; tenantNo++) {
    const t = String(tenantNo).padStart(3, "0");
    const tenantId = "tenant-" + t;

    for (let i = 1; i <= 8; i++) {
      const j = String(i).padStart(2, "0");
      const id = "l469-" + t + "-" + j;
      const cityCode = ["HCM", "HN", "DN"][
        (tenantNo + i) % 3
      ];
      const createdAt = new Date(Date.UTC(
        2026, 0, 15, 8 + Math.floor((i - 1) / 2), 0, 0
      ));
      const doc = {
        _id: id,
        labTag: tag,
        tenantId,
        title: "Listing " + t + "-" + j,
        cityCode,
        status: i % 3 === 0 ? "DRAFT" : "PUBLISHED",
        monthlyRentVnd: NumberDecimal(
          String(7000000 + tenantNo * 1000000 + i * 250000)
          + ".00"
        ),
        rooms: [
          {
            roomId: "bed-1",
            type: "BEDROOM",
            areaSqm: 15 + i,
            amenities: ["WIFI"]
          },
          {
            roomId: "kitchen-1",
            type: "KITCHEN",
            areaSqm: 8,
            amenities: ["STOVE"]
          }
        ],
        tags: ["FURNISHED", cityCode],
        createdAt,
        updatedAt: createdAt,
        revision: NumberLong("1")
      };
      listingOps.push({
        replaceOne: {
          filter: { _id: id, labTag: tag },
          replacement: doc,
          upsert: true
        }
      });
    }

    for (let k = 1; k <= 4; k++) {
      const id = "b469-" + t + "-" + String(k).padStart(2, "0");
      const listingId = "l469-" + t + "-"
        + String(k).padStart(2, "0");
      bookingOps.push({
        replaceOne: {
          filter: { _id: id, labTag: tag },
          replacement: {
            _id: id,
            labTag: tag,
            tenantId,
            listingId,
            requestKey: "request-" + t + "-" + k,
            requestedAt: new Date(Date.UTC(2026, 0, 15, 9, k, 0)),
            status: k % 2 === 0 ? "CONFIRMED" : "REQUESTED",
            revision: NumberLong("1")
          },
          upsert: true
        }
      });
    }
  }

  const base = Date.UTC(2026, 0, 15, 0, 0, 0);
  for (let i = 0; i < 240; i++) {
    const tenantNo = 1 + (i % 3);
    const t = String(tenantNo).padStart(3, "0");
    const listingNo = 1 + (Math.floor(i / 3) % 8);
    const listingId = "l469-" + t + "-"
      + String(listingNo).padStart(2, "0");
    const id = "e469-" + String(i).padStart(4, "0");
    const doc = {
      _id: id,
      labTag: tag,
      tenantId: "tenant-" + t,
      listingId,
      eventType: i % 5 === 0 ? "CONTACT" : "VIEW",
      createdAt: new Date(base + i * 180000),
      durationMs: 200 + (i % 12000)
    };
    eventOps.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });
  }

  listings.bulkWrite(listingOps, { ordered: false });
  events.bulkWrite(eventOps, { ordered: false });
  bookings.bulkWrite(bookingOps, { ordered: false });

  printjson({
    listings: listings.countDocuments({ labTag: tag }),
    events: events.countDocuments({ labTag: tag }),
    bookings: bookings.countDocuments({ labTag: tag })
  });
})();
~~~

Expected output on a clean lab: **listings:24, events:240, bookings:12**; each tenant has **8 listings, 80 events, 4 bookings**. Two consecutive listings within a tenant share `createdAt` so you can test the sort tie-breaker.

For events, **240 records are 240 total events of all types**, not 240 `VIEW`s; indices divisible by 5 are `CONTACT`. When counting views, you must filter `eventType:"VIEW"`.

## 24. Document + CRUD Lab: Reading a Listing, Updating a Room

### 24.1. Reading by Tenant and ID

~~~javascript
const lab = db.getSiblingDB("mongo_system_map_lab_469");
const listings = lab.getCollection("listings_469");

printjson(listings.findOne({
  _id: "l469-001-01",
  labTag: "system469-v1",
  tenantId: "tenant-001"
}));
~~~

In a real API, `tenantId` must come from the authenticated principal rather than trusting a self-declared header.

### 24.2. Updating a Room With arrayFilters

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l469-001-01",
    labTag: "system469-v1",
    tenantId: "tenant-001",
    revision: NumberLong("1")
  },
  {
    $set: {
      "rooms.$[room].areaSqm": 21
    },
    $inc: {
      revision: NumberLong("1")
    },
    $currentDate: {
      updatedAt: true
    }
  },
  {
    arrayFilters: [
      { "room.roomId": "bed-1" }
    ]
  }
));
~~~

On the first run after seeding, `matchedCount=1`. On the second run, the `revision=1` filter will not match. This demonstrates **optimistic concurrency** at the single-document level.

If `rooms` elements had duplicate `roomId`s, `arrayFilters` would match multiple elements; `roomId` uniqueness is an application invariant that must be enforced separately.

### 24.3. Re-reading the Rooms

~~~javascript
printjson(listings.findOne({
  _id: "l469-001-01",
  labTag: "system469-v1",
  tenantId: "tenant-001"
}, {
  _id: 1,
  rooms: 1,
  revision: 1,
  updatedAt: 1
}));
~~~

Verify that the bedroom area changed while the kitchen area remained unchanged. This illustrates the link between **document modeling** (embedded rooms) and **atomic array updates**.

## 25. Index + Query Lab: Searching Listings

### 25.1. Defining Candidate Indexes

~~~javascript
listings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    status: 1,
    cityCode: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "ix469_tag_tenant_status_city_time_id"
  }
);

listings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "ix469_tag_tenant_status_time_id"
  }
);
~~~

These two indexes model **two query families**: one with `cityCode` equality and one without `cityCode`. In production, measure frequency and write cost before keeping both.

### 25.2. City Filter and Sort

~~~javascript
const cityQuery = {
  labTag: "system469-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED",
  cityCode: "HCM"
};

printjson(listings.find(cityQuery, {
  _id: 1,
  title: 1,
  createdAt: 1,
  monthlyRentVnd: 1
}).sort({
  createdAt: -1,
  _id: -1
}).limit(5).toArray());
~~~

### 25.3. Explain

~~~javascript
printjson(
  listings.find(cityQuery)
    .sort({ createdAt: -1, _id: -1 })
    .limit(5)
    .explain("executionStats")
);
~~~

With only 24 documents in the lab, the optimizer may select a plan other than the expected index because `COLLSCAN` is cheaper. What matters is knowing how to read `explain`, not forcing a fixed plan on a tiny dataset.

### 25.4. Query Without City

~~~javascript
printjson(
  listings.find({
    labTag: "system469-v1",
    tenantId: "tenant-001",
    status: "PUBLISHED"
  }).sort({
    createdAt: -1,
    _id: -1
  }).limit(5).explain("executionStats")
);
~~~

Compare the candidate indexes and observe whether having **cityCode** in an index affects sort support when it is omitted from the equality filter.

## 26. Pagination Lab: Using Tuple Instead of Offset

~~~javascript
function page469(
    listings,
    tenantId,
    pageSize,
    after = null) {
  if (!/^tenant-[0-9]{3}$/.test(tenantId)) {
    throw new Error("Invalid tenantId");
  }
  if (!Number.isInteger(pageSize)
      || pageSize < 1 || pageSize > 10) {
    throw new Error("pageSize must be 1..10");
  }

  const base = {
    labTag: "system469-v1",
    tenantId,
    status: "PUBLISHED"
  };

  let query = base;
  if (after !== null) {
    if (!(after.createdAt instanceof Date)
        || Number.isNaN(after.createdAt.getTime())
        || typeof after.id !== "string"
        || after.id.length === 0) {
      throw new Error("Invalid cursor");
    }
    query = {
      $and: [
        base,
        {
          $or: [
            { createdAt: { $lt: after.createdAt } },
            {
              createdAt: after.createdAt,
              _id: { $lt: after.id }
            }
          ]
        }
      ]
    };
  }

  const rows = listings.find(query, {
    _id: 1, title: 1, tenantId: 1, createdAt: 1
  }).sort({
    createdAt: -1,
    _id: -1
  }).limit(pageSize + 1).toArray();

  const hasNext = rows.length > pageSize;
  const items = rows.slice(0, pageSize);
  const last = items[items.length - 1];
  return {
    items,
    hasNext,
    nextAfter: hasNext && last
      ? { createdAt: last.createdAt, id: last._id }
      : null
  };
}

const p1 = page469(listings, "tenant-001", 2);
printjson(p1);
if (p1.nextAfter) {
  const p2 = page469(
    listings, "tenant-001", 2, p1.nextAfter
  );
  printjson(p2);
  if (p2.nextAfter) {
    printjson(page469(
      listings, "tenant-001", 2, p2.nextAfter
    ));
  }
}
~~~

After seeding, `tenant-001` has **6 PUBLISHED listings**, so three pages with `size=2` return six IDs if statuses have not been modified. The lab simulates the pagination API without implementing signed cursors. Production must sign tokens, bind auth/filter context, and cap page sizes.

### 26.1. Connection to Topology

If `listings` is sharded on a field absent from the filter, this exact keyset query becomes scatter-gather. Indexes help each shard execute locally, yet the overall request must wait on and merge results from all shards. This is an example of **having the right index while topology routing may still be suboptimal**.

## 27. Aggregation Lab: Counting VIEWs per Listing

### 27.1. Event Indexes

~~~javascript
const events = lab.getCollection("view_events_469");

events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    eventType: 1,
    createdAt: -1,
    listingId: 1
  },
  {
    name: "ix469_tag_tenant_type_date_listing"
  }
);

events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    listingId: 1,
    createdAt: -1
  },
  {
    name: "ix469_tag_tenant_listing_date"
  }
);
~~~

The first index serves reports filtering by tenant/type/date; the second serves per-listing history queries. In append-heavy production environments, measure write amplification before retaining both.

### 27.2. Exact Pipeline

~~~javascript
const report = [
  {
    $match: {
      labTag: "system469-v1",
      tenantId: "tenant-001",
      eventType: "VIEW",
      createdAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-16T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$listingId",
      views: { $sum: 1 },
      latestAt: { $max: "$createdAt" }
    }
  },
  { $sort: { views: -1, _id: 1 } },
  { $limit: 10 }
];

printjson(events.aggregate(report, {
  allowDiskUse: true,
  maxTimeMS: 15000,
  comment: "system469-top-views"
}).toArray());
~~~

In the seed dataset, each tenant has **80 events** spread across 8 listings, and every fifth event globally is `CONTACT`. The report counts only `VIEW`, excluding `CONTACT`.

### 27.3. Explain Aggregation

~~~javascript
printjson(
  events.explain("executionStats")
    .aggregate(report, { allowDiskUse: true })
);
~~~

Observe input matching, scan/index usage, group/sort state, and output. Setting `allowDiskUse:true` **does not prove the query spilled to disk**, especially on a small dataset.

### 27.4. Why Put $match Before $group?

If you `$group` across all tenants before filtering by tenant, the server may have to accumulate state over a much larger dataset and lose opportunities to use a selective index. While the optimizer can reorder certain predicates, writing pipelines clearly from the access pattern remains beneficial.

## 28. Aggregation + $lookup Lab: Joining Statistics With Listings

**Goal:** Top views per listing alongside `title` and `cityCode`, without fetching all event documents.

~~~javascript
const enrichedReport = [
  {
    $match: {
      labTag: "system469-v1",
      tenantId: "tenant-001",
      eventType: "VIEW",
      createdAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-16T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        listingId: "$listingId"
      },
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1, "_id.listingId": 1 } },
  { $limit: 10 },
  {
    $lookup: {
      from: "listings_469",
      let: {
        listingKey: "$_id.listingId",
        tenantKey: "$_id.tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$listingKey"] },
                { $eq: ["$tenantId", "$$tenantKey"] }
              ]
            }
          }
        },
        {
          $project: {
            title: 1,
            cityCode: 1,
            status: 1
          }
        }
      ],
      as: "listing"
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      listingId: "$_id.listingId",
      views: 1,
      listing: { $first: "$listing" }
    }
  }
];

printjson(events.aggregate(enrichedReport, {
  maxTimeMS: 15000,
  allowDiskUse: true
}).toArray());
~~~

### 28.1. Why Group Before Looking Up?

Looking up the title for every raw event performs repeated joins and redundant work. Grouping first into 8 listings restricts the join to only the selected top groups. **This reordering is only valid when `title`/`cityCode` represent the listing's current attributes and the report does not require snapshot metadata from the moment each event occurred.**

### 28.2. Tenant Guard Inside $lookup

The `$lookup` pipeline constrains both **listingId and tenantId**. Even though lab `_id` values appear to embed the tenant, never rely on ID naming patterns as an authorization guarantee. Security boundaries must still be enforced by the application API before executing the report.

### 28.3. What If the Listing Was Deleted?

When no foreign match exists, `listing` becomes `null` or missing depending on projection semantics. The business must decide whether to:

- Still return the view count with a title like "Listing no longer exists."
- Store a title snapshot inside the event.
- Exclude the row (if the report is defined that way).

Do not silently drop statistical rows due to missing join matches if the report requires completeness.

## 29. Booking Lab: Indexes, Idempotency, and Atomic State Transitions

### 29.1. Indexes

~~~javascript
const bookings = lab.getCollection("bookings_469");

bookings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    listingId: 1,
    requestedAt: -1
  },
  {
    name: "ix469_tag_tenant_listing_requested"
  }
);

bookings.createIndex(
  { tenantId: 1, requestKey: 1 },
  {
    unique: true,
    name: "uq469_tenant_request_key"
  }
);
~~~

Note: the lab seed populates `requestKey` on every booking. On a legacy production collection with missing keys, inspect duplicates/nulls and consider partial indexes before building a unique index.

### 29.2. Reading Bookings for a Listing

~~~javascript
printjson(bookings.find({
  labTag: "system469-v1",
  tenantId: "tenant-001",
  listingId: "l469-001-01"
}).sort({ requestedAt: -1 }).toArray());
~~~

### 29.3. Confirming When REQUESTED and revision=1

~~~javascript
printjson(bookings.updateOne(
  {
    _id: "b469-001-01",
    labTag: "system469-v1",
    tenantId: "tenant-001",
    status: "REQUESTED",
    revision: NumberLong("1")
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

The first run after seeding matches; the second does not because `status` and `revision` changed. This illustrates an **atomic state transition** on a single booking document. It does not enforce an availability invariant on a separate listing document, which may require a transaction or dedicated synchronization.

### 29.4. Uniqueness Is Both an Index and Topology Concern

If the `bookings` collection is later sharded, you must verify how unique `(tenantId, requestKey)` enforcement interacts with the shard key. This is an example of a **business requirement impacting both indexes and shard keys**, not just Java validation.

## 30. Lab: Inspecting Collection and Index Metrics

Inspection commands in the lab environment:

~~~javascript
printjson(listings.getIndexes());
printjson(events.getIndexes());
printjson(bookings.getIndexes());

printjson(lab.runCommand({
  collStats: "listings_469"
}));

printjson(lab.runCommand({
  collStats: "view_events_469"
}));
~~~

Available metrics vary by MongoDB version, FCV, and privileges. Running `serverStatus` or cluster-admin commands is unnecessary for this lab; such commands may not even be permitted on managed services.

### 30.1. Read Metrics Instead of Guessing

- Collection size and average object size.
- Index counts and sizes.
- Document count per tenant.
- Keys/docs examined vs returned.
- Update frequency and write amplification.
- Working set and cache pressure in a representative environment.

With 276 synthetic documents, **do not extrapolate performance at 100 million documents**. The lab demonstrates semantics and observability, not load testing.

## 31. Index Maintenance and Schema Evolution

### 31.1. Changing a Field Path Changes Queries and Indexes

Suppose v1 stores:

~~~javascript
{ cityCode: "HCM" }
~~~

and v2 stores:

~~~javascript
{ address: { cityCode: "HCM" } }
~~~

While the collection holds both v1 and v2 documents, querying:

~~~javascript
{ "address.cityCode": "HCM" }
~~~

misses v1 records. Queries may need **$or** across both paths or a migration/backfill to a canonical field. Indexes may need to support both paths during the transition.

### 31.2. Expand–Migrate–Contract

~~~text
1. Expand readers to support old+new
2. Roll out to all readers
3. Switch writers to the new schema
4. Backfill legacy data with CAS/checkpoints
5. Verify all data and rollback policy
6. Drop legacy query/index support when safe
~~~

Do not enable the new writer while old readers that do not understand the new BSON shape are still running in a rolling deployment.

### 31.3. Index Cleanup

Once the old schema is gone, legacy indexes become write and disk overhead. Before dropping them:

- Check query usage.
- Verify schema-version distribution across data.
- Verify backup/restore compatibility.
- Measure `explain` assuming index removal.
- Establish a change window and rollback plan.

### 31.4. Shard Key Migration Is Harder Than Renaming a Regular Field

If a field serving as part of the shard key changes name or type, routing and data placement are affected. Do not assume running `$rename` on documents is sufficient to alter the shard key or topology. Plan migrations per the target MongoDB server version and sharding procedures.

## 32. Choosing a Model by Growth Characteristics

| Data | Growth Profile | Recommended Starting Model | Why |
| --- | --- | --- | --- |
| Listing title, city, rent | Few fields/document | Root listing fields | Read and edited together |
| 2–10 rooms/listing | Bounded | Embedded array | Single-query detail read and atomic update |
| Thousands of rooms/listing, frequent updates | Large/independent | Separate room collection | Avoids document growth and contention |
| Continuous view events | Unbounded append | Separate events collection | Write throughput and retention |
| Daily view counts | Finite bucket count | Summary collection | Fast dashboard reads |
| Booking workflow | Independent lifecycle | Separate booking collection | Dedicated indexes, states, permissions |
| Millions of user comments | Unbounded | Separate comments collection | Independent pagination and retention |
| Fixed set of tags | Bounded | Array inside listing | No join required |

These are candidate patterns only. Measure real data and verify access patterns before deciding.

## 33. Troubleshooting Workflow for a Slow Query

### 33.1. Do Not Jump Straight to Sharding

~~~text
Slow query
   |
   v
Correct business result and tenant scope?
   |
   v
Explain shows COLLSCAN or heavy SORT?
   |
   +-- Yes -> Inspect index/filter/sort/order
   |
   v
Aggregation state too large?
   |
   +-- Yes -> Group cardinality, $push, lookup fan-out
   |
   v
Document shape too large / too many joins?
   |
   +-- Yes -> Redesign embed/reference/projection
   |
   v
Read/write contention, disk, cache, CPU?
   |
   +-- Yes -> Concurrency budget, scaling, retention
   |
   v
Data/traffic exceeds replica set capacity?
   |
   +-- Yes -> Evaluate shard key and routing
~~~

### 33.2. First Verify the Query Is Correct

A query that runs 10x faster because `$limit` was placed before `$group` and dropped 90% of the data is **wrong**. Always maintain correctness tests and expected outputs before and after optimization.

### 33.3. Inspect Indexes

- Filter fields and sort directions.
- Equality/range selectivity.
- Index prefixes and collation.
- Multikey behavior.
- Whether covered queries justify their write cost.
- Index sizes and usage stats.

### 33.4. Inspect Aggregation

- Blocking stages.
- Memory/spill behavior.
- Group key cardinality.
- `$push`/`$addToSet` array growth.
- `$lookup` fan-out.
- `$unwind` multiplication.
- `$facet` output bounds.

### 33.5. Inspect Topology

- Whether the query targets a shard key.
- Whether a single shard or tenant is unusually hot.
- Merge-stage cost.
- Secondary lag and read preference.
- Replica set elections and retries.
- Disk/data distribution and backups.

### 33.6. Inspect the Application

- Connection pool saturation.
- Cursor batch sizes and full materialization.
- HTTP/request timeouts.
- N+1 queries from application code.
- Cache invalidation.
- Unbounded pagination or exports.

## 34. Incident Symptoms and Where to Investigate

| Symptom | Likely Root Cause | Primary Layer to Investigate |
| --- | --- | --- |
| Listing detail takes 12 DB calls | Over-normalized model, N+1 | Document/query |
| List API scans millions of docs | Missing index/filter | Index |
| Sort takes a very long time | Blocking SORT | Index/aggregation |
| `$group` hits memory limit | Cardinality/accumulator | Aggregation |
| `$push` array exceeds BSON limit | Unbounded embedding/output | Document/aggregation |
| Slow `$lookup` | Join fan-out/missing foreign index | Document/index/aggregation |
| CRUD writes slow after adding indexes | Write amplification | Index |
| Writes concentrate on one node | Replica-set primary ceiling or shard hot key | Topology |
| Sharded query slow despite IXSCAN | Scatter-gather/merge | Topology/query |
| Secondary reads return stale prices | Replication lag/read preference | Topology/consistency |
| Booking update loses data | Lost update / missing revision guard | Document/transaction |
| Unique key not enforced across shards | Index/shard key constraints | Index/topology |
| Dashboard count takes 2 minutes | Recomputing raw events too often | Aggregation/summary |
| Dashboard count lags by 5 minutes | Async summary freshness | Pipeline/consistency |
| Pagination returns duplicate IDs | Offset shifts or mutable sort key | Query/index/data model |
| Tenant A sees Tenant B's data | Missing authorization predicate | Security/query |
| Server runs out of disk | Data/index/spill/retention | Index/aggregation/topology |
| TTL has not deleted expired docs yet | Asynchronous TTL behavior | Data lifecycle |
| Readers fail after a restore | Incompatible schema evolution | Document/application |

## 35. Observability: Measuring All Four Layers

### 35.1. Document Metrics

- Document counts and size distribution.
- Embedded array lengths.
- Missing/null fields and BSON types.
- Schema-version distribution.
- Growth and retention rates.
- Hot document contention.

### 35.2. Index Metrics

- Index sizes and usage.
- `KeysExamined` vs `DocsExamined` vs `nReturned`.
- Index build durations.
- Write latency and index maintenance cost.
- Presence of blocking sorts.

### 35.3. Aggregation Metrics

- Stage execution stats.
- Group cardinality and joined rows.
- Spill/`usedDisk` when exposed by the server.
- Query duration and returned payload size.
- Materialized view lag and reconciliation drift.

### 35.4. Topology Metrics

- Primary/secondary state and replication lag.
- Elections and failover events.
- Read/write ops per node/shard.
- Free disk, IOPS, and cache pressure.
- Chunk, data, and traffic skew.
- Targeted vs scatter-gather queries where telemetry exists.

### 35.5. Endpoint-Tied SLOs

| API | Example SLO to Define | Evidence |
| --- | --- | --- |
| GET listing detail | p99 latency and error rate | APM + query explain |
| GET listing search | p95/p99 per filter/page | Cursor metrics + index plan |
| PATCH booking | Error/409 rate, write latency | Application logs + database metrics |
| Analytics dashboard | Latency + freshness | Batch/stream metrics + source reconciliation |
| Export | Completion time and completeness | Job metrics + snapshot policy |

Do not pick an arbitrary p99 number as a "MongoDB standard"; SLOs must reflect the workload, infrastructure, and business needs.

## 36. Cross-Layer Testing Matrix

| Test | Document | Index | Aggregation | Topology |
| --- | --- | --- | --- | --- |
| Unit business rule | Validate schema/invariants | Does not prove index usage | Verify pure transforms | Mock errors per policy |
| MongoDB integration | BSON types, atomic updates | Index presence/uniqueness | Pipeline results/edge cases | Single-node replica set has limits |
| API E2E | Tenant isolation/DTO | Observed indirectly | Report JSON/correctness | Real service/data flow |
| Performance | Document size/working set | Query plan under load | Spill/group latency | CPU/IOPS/shard routing |
| Resilience | Retry/idempotency | Index rebuild/deployment | Long-running query behavior | Elections/partitions/failover |
| Migration rehearsal | Old/new schema | Index rollout | Mixed-version reports | Shard key implications |

### 36.1. Unit Tests Do Not Replace Integration Tests

Mocked repositories do not verify:

- Proper BSON `Decimal128` storage.
- Multikey/`arrayFilters` semantics.
- Server-side unique index enforcement.
- Index selection in query plans.
- Transaction rollbacks.

### 36.2. Integration Tests Do Not Replace Capacity Tests

A test with 24 listings and 240 events can verify query correctness, but cannot prove p99 latency with 50 million events across multiple shards. Use representative datasets and traffic for performance testing.

### 36.3. Single-Node Testcontainers Do Not Test Full HA

`MongoDBContainer` supports many integration scenarios and can run with a replica-set URI, yet **does not prove failover behavior of a multi-node replica set**. Separate topology and resilience tests are required whenever the application has HA requirements.

## 37. Workflow for Designing a New Feature

### Step 1 — Write Down the Queries First

Build an access-pattern table: filter/sort fields, read/write ratios, cardinalities, SLOs.

### Step 2 — Choose Document Boundaries

Identify what can be embedded, what grows unboundedly, and which invariants require single-document atomicity.

### Step 3 — Design Minimal Indexes

Every index must correspond to a query family or constraint. Account for write/disk costs and follow naming conventions.

### Step 4 — Build Semantically Accurate Aggregations

Define group keys, timezones, null/missing handling, fan-out, output bounds, and consistency/freshness.

### Step 5 — Pick Topology Based on Capacity

Start with a replica set when sufficient. If sharding, evaluate the shard key and routing against real data and traffic, not collection size alone.

### Step 6 — Design Consistency and Failure Handling

Choose read preference/concern, write concern, transactional boundaries, idempotency/retries, backups, and restore procedures.

### Step 7 — Benchmark, Observe, Iterate

Combine `EXPLAIN`, representative-data testing, p95/p99 checks, resource cost analysis, and security/tenant verification. Document the decision record and rollback plan.

## 38. Quick Decision Map

### Question 1: Should We Embed?

**Lean toward embedding** if related data is small, bounded, read together, shares a lifecycle, and needs atomic updates.  
**Lean toward referencing** if data is unbounded, has many independent readers/writers, or requires separate retention, indexes, or permissions.

### Question 2: Should We Add an Index?

Add one when it serves a **clear query shape or constraint** whose read benefit outweighs write and storage costs. Check `explain` and workload metrics before and after. Do not index every field.

### Question 3: Run Aggregation Online or Materialize It?

Run online when queries are lightweight or require fresh data per semantics. Materialize when large scans/groups repeat frequently and the business accepts freshness lag alongside reconciliation.

### Question 4: Replica Set or Sharding?

Use a replica set when data size and throughput fit alongside HA requirements. Use sharding when scaling out data, writes, or load with a sound shard key; do not use it to mask flawed query or index shapes.

### Question 5: When to Read From Secondaries?

When the business tolerates potential lag and has an explicit consistency policy. Critical read-after-write flows require selecting appropriate session, read preference, and read concern settings.

### Question 6: When Should Transactions Be Used?

When an invariant genuinely spans multiple documents or collections and cannot be modeled cleanly with an atomic single-document operation or alternative pattern. Weigh the overhead, especially cross-shard.

### Question 7: Should We Use $lookup?

When join frequency, size, and indexes permit and the query is well-optimized. If it repeats at high traffic, consider a denormalized snapshot or materialized read model, while managing synchronization.

## 39. Self-Practice Exercises

### Exercise 1 — Four Layers

Trace a request flow from the REST API through document, index, aggregation, and replica set/shards. What does each layer decide?

### Exercise 2 — Access Patterns

For searching listings by tenant, status, city, and newest sort, construct a table of filters, sorts, projections, cardinalities, and SLOs.

### Exercise 3 — Embedded Rooms

Why is embedding a good fit for a listing with 2–5 rooms? What happens if a building has 20,000 rooms with continuous inventory updates?

### Exercise 4 — Unbounded View Events

Why should an unbounded `views[]` array not be stored inside the listing document? List at least four consequences.

### Exercise 5 — Document Atomicity

What atomicity guarantees apply to an update modifying both price and status within the same listing? How are two concurrent requests reading the same stale revision protected?

### Exercise 6 — Decimal128

Explain why `monthlyRentVnd` uses `Decimal128` instead of `Double`. How do you verify the actual BSON type in an integration test?

### Exercise 7 — Multikey

Design a query to find listings having a `BEDROOM` with `areaSqm >= 20`. Why is `$elemMatch` important?

### Exercise 8 — Unique roomId

Why does a unique multikey index not enforce `roomId` uniqueness within a single listing?

### Exercise 9 — Compound Index

Create an index for tenant/status/city equality and `createdAt DESC, _id DESC` sorting. Explain the key order.

### Exercise 10 — Omitting City Filter

A query omits `cityCode`, yet the index places `cityCode` before `createdAt`. What can happen to sorting? Propose an index for the common query.

### Exercise 11 — Explain

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. Why might a 24-document collection choose `COLLSCAN`?

### Exercise 12 — Partial Index

Design a partial index for `PUBLISHED` listings. Is a `DRAFT` query allowed to use it to return complete results?

### Exercise 13 — Unique Booking

Define a unique constraint on `tenantId + requestKey`. When sharding, what shard key condition must be checked?

### Exercise 14 — TTL

Why does TTL fit certain event-retention policies yet fail to guarantee exact-second deletion or replace backups and legal review?

### Exercise 15 — Top Views Aggregation

Write `$match` tenant/type/time, `$group` `listingId`, `$sort` views, and `$limit` top 10. What goes wrong if `$limit` is placed before `$group`?

### Exercise 16 — Group Cardinality

Compare grouping by `tenantId` versus grouping by `eventId`; how does memory state differ?

### Exercise 17 — $push

Why does `$group { $push: "$$ROOT" }` over millions of events risk hitting memory limits and the 16 MiB BSON output limit?

### Exercise 18 — $unwind

A listing has three rooms. After `$unwind`, how do you count documents to count rooms versus counting distinct listings?

### Exercise 19 — $lookup

When is grouping events before `$lookup` on listings better than joining every individual event? If a report needs `cityCode` at the time of the view, what semantic issue arises?

### Exercise 20 — $facet

A facet returns one million rows plus totals. Why does `allowDiskUse` not resolve the output document limit?

### Exercise 21 — Daily Summary

Design a `viewCount` summary per tenant/listing/day. Handle late events, duplicates, and job retries.

### Exercise 22 — Replica Set

Explain primary, secondaries, elections, and replication lag. Does adding a secondary scale write throughput like sharding?

### Exercise 23 — Concerns

Compare `w:1` with `w:"majority"`, and `local` with `majority` read concern. Why does majority not replace backups?

### Exercise 24 — Read-Your-Writes

Right after confirming a booking, the UI reads a secondary and receives `REQUESTED`. Explain the cause and design a consistency policy.

### Exercise 25 — Sharding

Distinguish `mongos`, the config server replica set, and shards. Why can a proper index on every shard still lead to scatter-gather?

### Exercise 26 — Shard Key

Compare a `tenantId` range shard key, a hashed `tenantId`, and a compound `tenantId+listingId` for a workload with 10,000 tenants.

### Exercise 27 — Hot Tenant

One tenant generates 40% of traffic. Does a hashed `tenantId` distribute that tenant's traffic across multiple shards? Why or why not?

### Exercise 28 — Merge Aggregation

Sketch partial `$group` on two shards plus the merge step. Which network and memory costs remain?

### Exercise 29 — Pagination

Write the keyset predicate for `createdAt DESC, _id DESC` and explain `pageSize+1`.

### Exercise 30 — Snapshot

Between page 1 and page 2, a `DRAFT` is published. Why does keyset pagination not guarantee a list snapshot?

### Exercise 31 — Lab Seed

Run the seed script for the three collections. Verify 24 listings, 240 events, 12 bookings, and three tenants.

### Exercise 32 — Lab Room Update

Run `arrayFilters` to update `bed-1` and `revision`. Verify `kitchen-1` stays unchanged and the second run fails to match `revision=1`.

### Exercise 33 — Lab Indexes

Run both query families (with and without `cityCode` equality) and compare `explain` and candidate indexes.

### Exercise 34 — Lab Cursor

Fetch three pages of `size=2` for `PUBLISHED` listings of `tenant-001`. Assert there are no duplicate IDs and that the sort tuple decreases monotonically.

### Exercise 35 — Lab Report

Run the top `VIEW` report. Verify that only `VIEW` is counted and `CONTACT` is excluded.

### Exercise 36 — Lab Join

Run `enrichedReport`; why does `$lookup` filter on both `tenantId` and `listingId`, and why group before joining?

### Exercise 37 — Lab Booking

Run the atomic `REQUESTED→CONFIRMED` update with `revision`, then run it again. Explain `matchedCount=0`.

### Exercise 38 — Schema Migration

Change `cityCode` to `address.cityCode` across multi-version data. Plan the reader/query/index expand–migrate–contract rollout.

### Exercise 39 — Performance

A query scans many documents, sorts in memory, and hits a hot shard. Outline the investigation sequence from query correctness through `explain` to topology.

### Exercise 40 — Capacity Planning

Estimate storage for 100 million events/day retained for 90 days: how should document size, index overhead, replication factor, compression, and retention be accounted for? Do not merely multiply doc count by payload size.

### Exercise 41 — Observability

Design a dashboard covering BSON sizes, index sizes, query examined/returned ratios, disk spills, replication lag, per-shard ops, and API p99.

### Exercise 42 — Security

A listing `_id` is predictable. Why do indexes, shard keys, and signed cursors fail to replace the tenant authorization predicate?

### Exercise 43 — Consistency

Separate consistency requirements for booking confirmation, listing search, dashboard summaries, and financial exports.

### Exercise 44 — Rollback

After deploying a v3 schema and new indexes, what could fail if rolling back application code to v2? Build a compatibility/backup/restore plan.

### Exercise 45 — Architecture Synthesis

Design a multi-tenant application with 5 million listings, 500 million view events, 1 million bookings, low search p99, a maximum 5-minute analytics lag, and high availability. Explain document boundaries, index families, aggregation/summaries, replica set vs sharding, shard keys, consistency, testing matrix, observability, and migration plan. Do not conclude "sharding is mandatory" before evaluating actual workload and capacity data.

## 40. References

- MongoDB Manual — [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/): modeling documents around access patterns.
- MongoDB Manual — [Embedded Data Models](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/): embedding vs referencing.
- MongoDB Manual — [BSON Documents](https://www.mongodb.com/docs/manual/core/document/): document semantics and BSON.
- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/): compound, multikey, partial, unique, and TTL indexes.
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/).
- MongoDB Manual — [Index Optimization](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/).
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/).
- MongoDB Manual — [Aggregation Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).
- MongoDB Manual — [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).
- MongoDB Manual — [$lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/).
- MongoDB Manual — [$facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/).
- MongoDB Manual — [Replica Sets](https://www.mongodb.com/docs/manual/replication/).
- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Sharding](https://www.mongodb.com/docs/manual/sharding/).
- MongoDB Manual — [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/).
- MongoDB Manual — [Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Java Sync Driver — [CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/).
- Spring Data MongoDB Reference — [MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html).
- Spring Data MongoDB Reference — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html).

## 41. Summary: Systems Thinking in MongoDB Design

Do not treat **documents, indexes, aggregations, and topology** as four disconnected API checklists. They are four facets of a single architectural decision:

~~~text
Document shape
    -> determines query/read/write boundaries
        -> determines index keys and write amplification
            -> determines aggregation input/state/output
                -> determines routing and per-node/shard resources
                    -> determines latency, consistency, and cost
~~~

**Document design** defines data boundaries: embed small/co-lifecycle data, and reference large datasets or those with independent lifecycles. **Indexes** are access structures serving query shapes and constraints, at the cost of disk and write budget. **Aggregations** leverage indexes early in the pipeline and may then require substantial group/sort/join state; optimize around semantics and consider summaries for recurring workloads. **Replica sets** primarily address HA, replication, and consistency choices; **sharding** distributes data and load while introducing shard-key, routing, and merge complexity. Every layer must uphold **tenant isolation, type correctness, concurrency control, backups, and observability**.

The most durable principle is to **start from access patterns and business correctness requirements, design the full chain, verify with explain/metrics/tests, and iterate under control**. When a query is slow, do not assume the fault lies solely in indexes or node count. When data grows, do not blindly embed everything or shard prematurely before understanding cardinality. And when results are correct yet latency climbs, inspect **document shape, index count, aggregation state, and topology execution location** together. That is how you design MongoDB systems that scale while preserving data correctness and predictable cost.
