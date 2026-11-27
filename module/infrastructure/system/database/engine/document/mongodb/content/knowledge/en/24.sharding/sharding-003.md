# Data Distribution, Routing Metadata, Chunks, and the Balancer in MongoDB Sharding

When a collection grows to the point where placing all its data and access load on a single group of machines is no longer suitable, **sharding** allows MongoDB to distribute the collection’s documents across multiple **shards**. The goal may be to expand storage capacity, spread write load, increase query throughput, or place subsets of data on specific infrastructure regions.

However, MongoDB does not simply “split documents evenly by machine count.” Which shard owns a document is determined by the **shard key**, **value ranges (ranges/chunks)**, **routing metadata**, and **distribution rules**. The **mongos** router uses metadata to direct queries to the appropriate shards; the **balancer** handles migrating needed data ranges to achieve balance according to the version’s mechanism.

Four core concepts in this lesson:

1. **Data distribution:** the shard key and how shard key values map to shards.
2. **Routing metadata:** information MongoDB stores about databases, collections, chunks/ranges, and owning shards to select query targets.
3. **Chunk:** a contiguous interval in the shard key value space, serving as a key logical unit for data placement management.
4. **Balancer:** the background mechanism coordinating chunk or range distribution/migration across shards when needed.

A key takeaway right from the start:

> **Sharding does not automatically turn a query into a fast query.** To gain the benefits of load distribution, you must choose an appropriate shard key, route properly, maintain indexes serving queries on each shard, and operate metadata/balancer with clear observability.

This lesson uses examples in **mongosh** and **Java Sync Driver**, along with techniques for reading results, skew scenarios, migration issues, and hands-on exercises. Administrative syntax varies across MongoDB versions: operations that alter cluster configuration must be checked against your exact version and executed only in a lab or via an approved procedure.

## 1. Overall architecture of a sharded cluster

A MongoDB sharded cluster has three main components:

| Component | Role |
| --- | --- |
| **Shard** | Stores a subset of data; in production, typically a replica set |
| **mongos** | Router receiving client commands, using metadata to route to shards |
| **Config server replica set (CSRS)** | Stores sharded cluster configuration metadata, including routing info |

Diagram:

~~~text
                      APPLICATION / DRIVER
                              |
                              v
                       +-------------+
                       |    mongos   |
                       | Query router|
                       +-------------+
                          |       ^
          Routing request |       | Metadata cache / refresh
                          v       |
                 +----------------------+
                 | Config Server RS     |
                 | Sharding metadata    |
                 +----------------------+
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
       +---------+   +---------+   +---------+
       | Shard A |   | Shard B |   | Shard C |
       |Replica  |   |Replica  |   |Replica  |
       |   set   |   |   set   |   |   set   |
       +---------+   +---------+   +---------+
~~~

Simplified diagram: in practice, `mongos` retrieves/refreshes required metadata from config servers, sends requests directly to shards, and receives results; not every request passes through config servers on the data path.

### 1.1. A shard does not mean a single mongod process

In production, each shard is typically a **replica set** with a primary and secondaries.

~~~text
Shard A:
  A1 PRIMARY
  A2 SECONDARY
  A3 SECONDARY

Shard B:
  B1 PRIMARY
  B2 SECONDARY
  B3 SECONDARY
~~~

As a result:

- **Sharding** partitions data between shards A and B.
- **Replication** creates copies of data inside each shard.

These two mechanisms solve two distinct problems: **horizontal partitioning** and **high availability**. Adding a secondary does not increase the number of shards to spread capacity; adding a shard does not replace replication within each shard.

### 1.2. Does mongos store business data?

`mongos` is a router; it does not store a full collection copy like a shard. It uses metadata and forwards operations, sometimes merging results from multiple shards.

If a query lacks sufficient information to identify the target shard, `mongos` may have to send the query to many shards. This is the **scatter-gather** pattern.

### 1.3. What do config servers hold?

Config servers hold sharding control information, such as:

- List of shards and related attributes.
- Sharded database/collection information.
- Collection shard key configurations.
- Locations and boundaries of chunks/ranges.
- Tags/zones used to constrain distribution.
- Metadata versioning and information supporting migration coordination.

**Do not directly modify internal collections in the `config` database** using regular CRUD operations. MongoDB has dedicated administrative sharding commands and its own metadata consistency mechanism.

## 2. Data is distributed using a shard key

A **shard key** is a field or combination of fields MongoDB uses to partition documents in a sharded collection.

Example order document:

~~~javascript
{
  _id: "ORD-1001",
  tenantId: "TENANT-A",
  orderId: "ORD-1001",
  customerId: "C-01",
  orderDate: ISODate("2026-11-01T09:00:00Z"),
  totalCents: NumberLong(250000),
  status: "PAID"
}
~~~

One possible shard key choice:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

This is a **compound ranged shard key**. A document’s shard key value is the pair **(tenantId, orderId)**, compared in key order.

Example ordering:

~~~text
("TENANT-A", "ORD-1001")
("TENANT-A", "ORD-1002")
("TENANT-A", "ORD-1003")
("TENANT-B", "ORD-0001")
("TENANT-C", "ORD-9001")
~~~

MongoDB distributes ranges of this key space across shards.

### 2.1. A shard key is not an ordinary index

An index helps queries filter/sort quickly within one shard; a shard key also determines **how data is split and routed across the entire cluster**.

A query still needs an appropriate index on the receiving shard. Having the right shard key does not automatically ensure every filter or sort is optimized.

### 2.2. A shard key must serve both reads and writes

Important criteria:

- **Cardinality:** whether there are enough distinct values to split the data.
- **Frequency distribution:** whether any value occurs overwhelmingly often.
- **Monotonicity:** whether values increase continuously, leading to write hotspots.
- **Query patterns:** whether queries include the shard key for routing.
- **Write throughput:** whether writes spread across shards or concentrate on one region.
- **Chunk/range mobility:** whether data can be split into reasonable intervals for migration.
- **Business requirements:** tenant isolation, region affinity, data placement, and access control.

### 2.3. Example of an unbalanced shard key

Choosing:

~~~javascript
{ status: 1 }
~~~

in an `orders` collection where most documents have `status = "PAID"` is risky:

- Low cardinality.
- Many documents share the same value.
- Hard to split hot data by status.
- Frequent writes hitting the same key region can cause hotspots.

Do not assume a shard key is good just because the field appears in many filters.

### 2.4. Example of a monotonically increasing shard key over time

Choosing a ranged key:

~~~javascript
{ createdAt: 1 }
~~~

When most inserts have ever-increasing `createdAt`, writes tend to concentrate on the **newest value range**, which may reside on a single shard at that moment.

This is the **monotonically increasing shard key hotspot** phenomenon. Hashing or choosing a key with better spread can help, but you must evaluate the impact on range queries and locality requirements.

## 3. Range sharding and hashed sharding

MongoDB supports shard-key-based distribution approaches commonly discussed through two main styles:

| Style | Idea | Strengths | Trade-offs |
| --- | --- | --- | --- |
| **Ranged shard key** | Splits key ranges in BSON order | Range routing can be efficient; clearer locality | Prone to hotspots with monotonic keys or skewed distribution |
| **Hashed shard key** | Hashes shard key values to spread across hash space | Decouples value order from storage location; spreads many key types | Range queries on original values struggle to target few shards |

### 3.1. Ranged key

Example:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Chunks may cover ranges such as:

~~~text
Chunk 1: [MinKey, ("TENANT-A", "ORD-5000"))
Chunk 2: [("TENANT-A", "ORD-5000"), ("TENANT-B", "ORD-0000"))
Chunk 3: [("TENANT-B", "ORD-0000"), MaxKey)
~~~

This is a logical example; in a compound key, actual boundaries are tuples following BSON ordering.

### 3.2. Hashed key

Example:

~~~javascript
{ customerId: "hashed" }
~~~

MongoDB maps `customerId` values onto a hash space for distribution. Alphabetically adjacent `customerId` values are not necessarily adjacent in the hash space.

Equality filters on `customerId` can still be converted to a hash value for routing. However, a query like:

~~~javascript
{
  customerId: {
    $gte: "C-1000",
    $lt: "C-2000"
  }
}
~~~

does not form a small contiguous interval in hash space, so it may need to inspect multiple shards.

### 3.3. Hashing does not cure every hotspot

If one tenant or a single shard key value receives heavy writes, **the same hash value maps to the same logical location**. Hashing does not split a single shard key value into multiple keys.

You may need a suitable compound key, bucketing, or another distribution model if a single logical key is too hot.

### 3.4. Do not pick a shard key before analyzing the workload

A key that balances inserts well yet turns every analytical query into scatter-gather can impose huge costs.

Before choosing, gather:

- Common query filters.
- Updates/deletes and fields used to locate documents.
- Primary sorts and range queries.
- Read/write ratio and document sizes.
- Value distribution, large tenants vs. small tenants.
- Cross-tenant queries, summary reports, and joins.
- Data residency requirements and future changes.

## 4. What is a chunk?

In sharding, a **chunk** is a **contiguous interval in a collection’s shard key value space**. MongoDB manages and distributes these intervals across shards.

Example with ranged key **{ tenantId: 1, orderId: 1 }**:

~~~text
Key space (ordered by shard key)
MinKey ------------------------------------------------ MaxKey

  [Range A)       [Range B)        [Range C)       [Range D)
      |               |                |               |
    Shard 1         Shard 2          Shard 1          Shard 3
~~~

A chunk contains documents whose shard key values fall within its interval.

### 4.1. Half-open boundaries

Chunks are usually described as:

\[
[\text{min}, \text{max})
\]

Meaning:

- **min** is inclusive.
- **max** is exclusive.
- Adjacent chunks share a boundary without overlapping.
- Each shard key value belongs to one matching logical interval.

Example:

~~~text
Chunk A: [100, 200)
Chunk B: [200, 300)

key = 199 belongs to Chunk A
key = 200 belongs to Chunk B
~~~

### 4.2. A chunk is not a file on disk

A chunk is a **logical unit of distribution**, not a separate physical file or standalone partition file users can open in the filesystem.

A shard still stores documents via its storage engine and indexes. Metadata maps **shard key intervals** to the owning shard.

### 4.3. Chunks and documents are not one-to-one

A chunk typically contains many documents. MongoDB does not create a new chunk for every document.

Document counts in two chunks can differ widely even with similar byte sizes, because documents vary in size.

### 4.4. Target chunk size is not a hard limit

MongoDB has a target chunk/range size setting to assist balancing. Default numbers and splitting/merging behavior have evolved across versions; for example, many modern releases have a default target chunk size of **128 MiB**.

**This is not a guarantee that every chunk is always smaller than 128 MiB.** Chunks can exceed the target due to data growth, splitting behavior, repeated key values, or migration state.

Do not use chunk count as an exact proxy for data size in bytes.

## 5. From shard key to chunk to shard

A document has key:

~~~text
tenantId = TENANT-B
orderId  = ORD-1010
~~~

`mongos` must know:

1. Is the collection sharded?
2. What is the collection’s shard key pattern?
3. Which chunk/range contains this key value?
4. Which shard currently owns that chunk?
5. Which shard should receive the operation?

Simulated metadata table example:

| Key range | Owning shard |
| --- | --- |
| [MinKey, ("TENANT-A","ORD-5000")) | shard-a |
| [("TENANT-A","ORD-5000"), ("TENANT-B","ORD-5000")) | shard-b |
| [("TENANT-B","ORD-5000"), MaxKey) | shard-c |

A document with **("TENANT-B", "ORD-1010")** falls in the second range by tuple ordering, so `mongos` can route it to **shard-b**.

This table is illustrative: actual boundaries depend on keys, BSON ordering, and cluster metadata.

### 5.1. One shard can own multiple chunks

~~~text
Shard A:
  Chunk 1
  Chunk 4
  Chunk 7

Shard B:
  Chunk 2
  Chunk 6

Shard C:
  Chunk 3
  Chunk 5
~~~

A shard does not necessarily own one single large contiguous interval. As balancer migrations or splits change distribution, a shard can own multiple non-adjacent ranges in the key space.

### 5.2. Documents sharing the same shard key value

Documents can share the same shard key value. Importantly, MongoDB cannot split **an indivisible shard key value** into separate chunks simply by placing a boundary between identical values.

If too many documents share the same key value, it can produce ranges/chunks that are hard to split or move efficiently. Choosing a shard key with adequate cardinality and distribution from the outset is critical.

## 6. Distinguishing chunk split, merge, and migration

These three actions have distinct semantics:

| Action | Meaning | Automatically changes owning shard? |
| --- | --- | --- |
| **Split** | Divides a shard key range into smaller ranges | Usually no; new ranges start on the same shard |
| **Merge** | Combines adjacent ranges meeting criteria | Does not necessarily change owning shard |
| **Migration / Move** | Transfers ownership of a range/chunk from source shard to destination shard | **Yes** |

### 6.1. Split does not mean data was moved elsewhere

Example:

~~~text
Before:
Shard A owns [0, 1000)

After split:
Shard A owns [0, 500)
Shard A owns [500, 1000)
~~~

The chunk count increases from one to two, yet all data remains on Shard A.

### 6.2. Migration can change distribution

~~~text
Before:
Shard A: [0, 500), [500, 1000)
Shard B: [1000, 1500)

After move chunk:
Shard A: [0, 500)
Shard B: [500, 1000), [1000, 1500)
~~~

Data with shard keys in **[500, 1000)** transfers logical ownership from A to B following the migration procedure.

### 6.3. Split/merge mechanics vary by version

Do not hard-memorize “whenever a chunk exceeds a threshold, MongoDB splits it immediately.” **Automatic splitting, auto-merging, and range management** mechanisms have changed substantially across MongoDB versions.

When operating a cluster, read the documentation for your exact release. This lesson focuses on **the nature of logical ranges and balancing**, rather than treating an old split command name as universal behavior across all versions.

## 7. Where is routing metadata stored?

The **Config server replica set** holds sharded cluster configuration metadata.

Types of logical metadata:

| Information | Purpose |
| --- | --- |
| Database metadata | Databases in the cluster and related placement info |
| Collection metadata | Namespace, UUID, shard key, sharding configuration |
| Chunk/range metadata | Min to max bounds, owning shard, version info |
| Shard registry | Cluster shards, connection addresses |
| Zone/tag metadata | Shard key ranges constrained to specific shard groups |
| Migration state / coordination | Information supporting data movement coordination |

In some versions, these metadata types are visible through internal collections in the **config** database, but **the internal schema is not a stable API for applications to edit directly**.

### 7.1. Why is metadata critical?

If `mongos` does not know which shard holds the chunk containing key **K**, it cannot route accurately under the sharding model.

Especially when a migration completes, **range ownership changes**. Metadata must reflect the new state so routers continue sending requests to the right shard.

### 7.2. Config servers are not on the data path of every request

A misconception:

~~~text
Client -> mongos -> config servers -> shard -> config servers -> client
~~~

This is not the normal processing chain for every CRUD request.

`mongos` **caches** necessary routing metadata. When receiving an operation, the router usually uses cached info to pick the shard. When metadata changes or becomes stale, it refreshes from the authoritative metadata source.

### 7.3. Metadata differs from collection data

Config servers are not a shard storing every order. They store **location, structure, and coordination metadata**.

Therefore, do not use config servers to run business queries on the `orders` collection, or attempt to build business indexes there.

## 8. mongos routes using cached metadata

Logical workflow:

~~~text
Application -> mongos
                |
                v
         Parse operation
                |
                v
       Identify namespace
                |
                v
     Fetch shard key / ranges
        from routing cache
                |
                v
   Target one/multiple matching shards
                |
                v
       Shards execute query
                |
                v
      mongos merges results
                |
                v
            Application
~~~

### 8.1. Routing cache reduces overhead

If every query had to read config servers before running, config servers would quickly become a bottleneck. Thus, `mongos` caches routing metadata and uses appropriate refresh/invalidation mechanisms.

### 8.2. Cached metadata can become stale

For instance, a chunk previously lived on Shard A and migrated to Shard B. `mongos M1` has not yet updated to the new location and sends a request using stale cache.

MongoDB uses **metadata versioning** and stale-routing responses so routers refresh and re-route under supported conditions. Error names or internal details vary by version.

Normal applications should not maintain their own chunk-location table to route directly to shards; let `mongos`/the driver handle the supported routing mechanism.

### 8.3. Does mongos need a restart after migration?

No. The system is designed to refresh routing metadata without requiring a full restart of all `mongos` instances on every chunk move.

If an application only works after restarting routers, that signals a metadata, connectivity, or compatibility issue to investigate—not normal operational procedure.

## 9. Targeted queries and scatter-gather

This is the clearest consequence of routing metadata for applications.

### 9.1. Targeted query

Suppose the `orders` collection is sharded on:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
});
~~~

provides the document’s full key, giving `mongos` enough information to route to the range holding that key.

### 9.2. Targeting multiple chunks does not guarantee a single shard

Query:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A"
});
~~~

with a compound shard key prefixed by `tenantId` can narrow down the **key ranges associated with `TENANT-A`**. However, if one tenant spans multiple chunks across multiple shards, the query still must be sent to multiple shards.

Therefore, “a query contains the shard key” **does not automatically mean only one shard**. You must check whether the predicates identify a specific range/point and how metadata is distributed.

### 9.3. Scatter-gather

Query:

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

does not contain the `tenantId`/`orderId` shard key. If `mongos` cannot infer target shards from other predicates, it may send the query to **many or all relevant shards**, then merge the results.

~~~text
                    mongos
                  /   |    \
                 v    v     v
              Shard A B     C
                 \    |    /
                  \   |   /
                 Merge results
~~~

### 9.4. Scatter-gather is not always wrong

Cross-tenant reporting queries or cluster-wide analytics reasonably need to scan multiple shards.

However, if a frequent query on a latency-sensitive API always scatter-gathers, the shard key may not fit the access patterns.

### 9.5. Indexes are still needed on shards

A query routed accurately to a single shard but lacking an index can still perform a **COLLSCAN** on that shard.

Conversely, a scatter-gather query with good indexes on every shard still incurs the overhead of dispatching requests and merging results.

Two layers must be optimized in parallel:

1. **Routing:** how many shards are targeted.
2. **Local execution:** which plan/index each shard uses.

## 10. Explain in a sharded cluster

Over a **mongos** connection, run:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
}).explain("executionStats");
~~~

Compare with:

~~~javascript
db.orders.find({
  status: "PAID"
}).explain("executionStats");
~~~

What to observe:

- Which shards participate.
- Whether it is one shard or multiple shards.
- Stages and plans within each shard.
- Total documents/keys examined, if `executionStats` provides them.
- Execution time and the merge phase.

Explain structure and stage names can vary across query engines/MongoDB versions. Some plans display dedicated sharded query or merge structures; do not rely rigidly on one exact stage name.

### 10.1. Do not compare timings between queries on different data

For a meaningful comparison between targeted and scatter-gather, consider:

- Equivalent predicate selectivity.
- Corresponding indexes.
- Warm/cold cache state.
- Document count.
- Shard count.
- Result shape and sort/limit.
- Network latency.

Concluding “targeted is always N times faster” from a single isolated explain run is unreliable.

## 11. Sort, limit, and aggregation across multiple shards

`mongos` may need to **merge** results from multiple shards.

Example:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({ orderDate: -1 })
.limit(20);
~~~

If the query touches multiple shards, execution may involve:

- Shards filtering and producing intermediate results.
- Shards or `mongos` participating in sorting per the plan.
- `mongos` merging the received streams.
- Applying the limit according to whole-query semantics.

The ability to push down certain stages to shards depends on the pipeline and optimizer.

### 11.1. Cross-shard $group

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      totalCents: { $sum: "$totalCents" }
    }
  }
]);
~~~

This pipeline may need to perform local partial aggregation on multiple shards and then merge results according to `$group` semantics.

### 11.2. Good routing alone is not enough for large joins

`$lookup`, `$graphLookup`, large sorts, and large groups can generate heavy workloads when collections are distributed. Check version-specific support conditions, indexes on joined collections, and explain plans rather than assuming every aggregation automatically scales linearly in parallel when shards are added.

## 12. What does the balancer do?

The **Balancer** is the background data distribution management mechanism of a sharded cluster. It evaluates range/chunk locations and policies, then coordinates migrations between shards when needed.

Initial example:

~~~text
Shard A: 8 chunks
Shard B: 2 chunks
Shard C: 2 chunks
~~~

If consistent with the version’s balancing logic and not blocked by other constraints, MongoDB can migrate some chunks/ranges from A to B/C over time.

**Do not assume the balancer always tries to make chunk counts strictly equal on all shards.** Modern algorithms may use other criteria such as data size and related thresholds; zones, oversized ranges, and operational limits also affect balancing.

### 12.1. The balancer does not mean every shard will have the same document count

Documents differ in size. A chunk with 10,000 tiny documents may have fewer bytes than a chunk with 100 huge documents.

The balancer cannot guarantee every shard has **equal row counts, byte sizes, CPU, IOPS, and query latency**. Those are distinct quantities.

### 12.2. The balancer cannot fix a bad shard key

If many writes hit **one single shard key value**, migrating surrounding ranges will not distribute writes for that value.

Storage balance and **workload** balance are not synonymous. A shard with low storage usage that receives most writes can still be the bottleneck.

### 12.3. When does balancing happen?

Whether a migration runs depends on:

- Balancer state.
- Current distribution under the version’s algorithm.
- Whether a chunk/range is movable.
- Sizes and migration thresholds.
- Zones and tags.
- Source/destination shard health.
- Other maintenance or active migrations.
- Cluster compatibility.

Never say every insert triggers a balancing round or that adding a shard immediately distributes data evenly.

## 13. Logical phases of chunk migration

A migration must transfer data and update range ownership consistently.

At a conceptual level:

~~~text
1. Select range/chunk to move
2. Select donor shard and recipient shard
3. Recipient receives/copies required data
4. Synchronize changes occurring during the copy
5. Coordinate commit of range ownership
6. Routing metadata is updated
7. Clean up old/orphaned data when eligible
~~~

This is a logical model, not a step-by-step API for applications to invoke. Internal sequences and actual phases can change across MongoDB releases.

### 13.1. Donor and recipient

- **Donor:** the shard owning the data before migration.
- **Recipient:** the shard receiving the data and ownership after migration.

During migration, MongoDB must handle ongoing data changes while copying, while ensuring no two shards are simultaneously considered valid owners of the same range after the metadata commit.

### 13.2. Metadata commit is the critical boundary

It is not enough for the recipient to finish copying files/documents. Routers must also know **which shard now owns the range**.

That is why chunk migration is tied to metadata versioning and `mongos` refreshes.

### 13.3. Orphaned documents

After migration, old physical data on the donor may linger temporarily during cleanup. In sharding terminology, these are commonly called **orphaned documents**.

The temporary existence of stale physical data does not mean two shards are allowed to both return the document as valid owners. MongoDB uses metadata-based filtering/ownership checks to reconcile the difference between physical data awaiting cleanup and logical ownership.

### 13.4. Migration can affect latency

Copying data, syncing ongoing changes, and transferring ownership add I/O, network, and CPU load, which can impact workloads. Some stages can cause brief pauses or latency spikes depending on version, scenario, and contention.

**“Online migration” does not mean zero impact on request latency.**

## 14. Oversized ranges and jumbo chunks

A chunk can become too large or hard to split when many documents lack distinguishable shard key values.

Example shard key:

~~~javascript
{ tenantId: 1 }
~~~

and **TENANT-LARGE** has millions of documents:

~~~text
tenantId = "TENANT-LARGE"
tenantId = "TENANT-LARGE"
tenantId = "TENANT-LARGE"
...
~~~

If all share the same key value, no shard key boundary can be drawn between those documents solely by splitting on `tenantId`.

Some versions/mechanisms use the term **jumbo** or **oversized chunk/range** for situations that impede migration.

### 14.1. Why can’t the balancer fix it on its own?

The balancer moves **ranges defined by the shard key**. It cannot break an indivisible key value into multiple distinct values.

If all hot documents share one key value, moving the range merely shifts the hotspot to another shard rather than spreading the hotspot across multiple shards.

### 14.2. Prevention

- Choose a shard key with sufficient cardinality.
- Use a compound shard key when matching query and write patterns.
- Evaluate huge tenants before choosing `tenantId` alone.
- Avoid widespread missing/null key fields.
- Monitor range/chunk sizes and stalled migrations.
- Consider resharding/refining the shard key per version capabilities and approved procedures.

Never directly delete chunk metadata or bulk-modify key values in production to “fix jumbo chunks” without a migration and data-consistency plan.

## 15. Balancer vs. shard key hotspot: two different problems

Two types of imbalance must be distinguished.

**Storage imbalance:**

~~~text
Shard A: 800 GB
Shard B: 200 GB
Shard C: 180 GB
~~~

**Write throughput imbalance:**

~~~text
Shard A: 20,000 writes/s
Shard B: 1,000 writes/s
Shard C: 900 writes/s
~~~

A shard with low storage usage can still hold the key region receiving continuous writes.

### 15.1. The balancer prioritizes data distribution, not QPS balance

When evaluating scaling effectiveness, monitor all of:

- Data size and document count per shard.
- Number/ranges/chunks ownership.
- Write/read operations per shard.
- CPU, IOPS, cache pressure.
- Query latency per shard.
- Migrations and replication lag.
- Ratio of targeted vs. scatter-gather queries.

### 15.2. The monotonic key case

If all inserts carry a continuously increasing shard key, writes go to the tail chunk of the key space. The balancer can move older chunks away, yet **new writes still target the tail of the key space**.

Solutions may involve choosing a different key, hashed/compound keys, or changing the data model—simply turning on the balancer is not enough.

## 16. Zones: constraining data placement

MongoDB supports **zones** to associate shard key ranges with designated groups of shards.

Scenarios:

- APAC regional data should reside on shards in APAC infrastructure.
- Sensitive tenant groups require policy-based placement.
- Certain data ranges need shards with different hardware profiles.

Diagram:

~~~text
Zone APAC -> shard-a, shard-b
Zone EMEA -> shard-c, shard-d

Shard key ranges:
  APAC tenants -> Zone APAC
  EMEA tenants -> Zone EMEA
~~~

### 16.1. Zones do not replace the shard key

Zone ranges are expressed in the collection’s **shard key space**. If the shard key cannot represent the placement criterion, zones cannot inspect an application field outside the shard key to route accurately.

### 16.2. Lab zone configuration example

Suppose the collection is already sharded on:

~~~javascript
{ region: 1, accountId: 1 }
~~~

Assign zone names to shards:

~~~javascript
sh.addShardToZone("shard-a", "ZONE_APAC");
sh.addShardToZone("shard-b", "ZONE_APAC");
~~~

Create a zone range for `region = "APAC"`:

~~~javascript
sh.updateZoneKeyRange(
  "sharding_lab.accounts",
  {
    region: "APAC",
    accountId: MinKey()
  },
  {
    region: "APAC",
    accountId: MaxKey()
  },
  "ZONE_APAC"
);
~~~

This example illustrates syntax and intent only. Shard names, shard keys, BSON boundaries, and versions must match your environment; verify against the MongoDB Manual before executing. If shards in a zone lack capacity or are unavailable, achieving the desired placement may be delayed or blocked.

### 16.3. How do zones affect balancing?

The balancer must respect zone constraints when assigning ranges to shards. A migration violating zone rules is not a valid balanced state that administrators should force.

### 16.4. Zones are not a complete security or compliance control

Zones help **guide placement** by shard key, but they do not replace:

- IAM/role-based access.
- Encryption.
- Network isolation.
- Backup/replication/cross-region rules.
- Data controls in logs and analytics.
- Specific legal compliance obligations.

Do not look at a zone name alone and conclude that no copies or related data ever leave a jurisdiction; inspect the entire topology, backups, and policies.

## 17. Creating a sharded collection in a lab environment

The following example assumes an active lab sharded cluster and `mongosh` connected to **mongos**, not a standalone `mongod`.

### 17.1. Create database and sample data

~~~javascript
use sharding_lab

db.orders.insertMany([
  {
    _id: "ORD-1001",
    tenantId: "TENANT-A",
    orderId: "ORD-1001",
    status: "PAID",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    totalCents: NumberLong(200000)
  },
  {
    _id: "ORD-1002",
    tenantId: "TENANT-A",
    orderId: "ORD-1002",
    status: "PENDING",
    createdAt: ISODate("2026-11-02T09:00:00Z"),
    totalCents: NumberLong(150000)
  },
  {
    _id: "ORD-2001",
    tenantId: "TENANT-B",
    orderId: "ORD-2001",
    status: "PAID",
    createdAt: ISODate("2026-11-03T09:00:00Z"),
    totalCents: NumberLong(300000)
  }
]);
~~~

### 17.2. Create an index supporting the shard key

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  orderId: 1
});
~~~

### 17.3. Shard the collection

~~~javascript
sh.shardCollection(
  "sharding_lab.orders",
  {
    tenantId: 1,
    orderId: 1
  }
);
~~~

Requirements for indexes, uniqueness, existing collections, key restrictions, and database sharding preparation vary by version. Some versions no longer require calling **sh.enableSharding** on the database beforehand as described in older documentation. Always read the server’s responses in your lab.

### 17.4. Creating a few documents is not enough to observe balancing

With three small documents, many setups create only one or very few chunks and place them on a single shard. Do not conclude the balancer is broken just because a handful of documents are not spread across all shards.

Chunk/range distribution depends on data volume, sharding configuration, and the version’s algorithm/mode.

### 17.5. Do not follow lab examples verbatim on production

Sharding a collection with live data has specific requirements around indexes, operational preconditions, timing, and workload impact. You must have a migration/rollback plan and verify application compatibility.

## 18. Observing distribution and balancer from mongosh

On a `mongos` connection:

~~~javascript
sh.status();
~~~

This command gives an overview of topology and sharding state by version, typically including:

- List of shards.
- Sharded databases/collections.
- Key patterns.
- Chunk/range counts and zone info where applicable.
- Available balancer/migration status details.

### 18.1. Balancer state

Depending on `mongosh` and server version, helpers and commands can be used:

~~~javascript
sh.getBalancerState();
~~~

And:

~~~javascript
db.adminCommand({
  balancerStatus: 1
});
~~~

Exact fields and helpers vary by version. **Balancer enabled** does not mean a migration is actively running right now; a balanced cluster may have nothing to move.

### 18.2. Distribution of a collection

In supported versions, a helper can display distribution statistics:

~~~javascript
db.orders.getShardDistribution();
~~~

The output helps visualize the relative distribution of data/chunks across shards. Do not assume this helper exists in every client/version; if unsupported, consult the operational docs and available cluster metrics.

### 18.3. Query explain

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
}).explain("executionStats");
~~~

Compare with:

~~~javascript
db.orders.find({
  status: "PAID"
}).explain("executionStats");
~~~

What to record: **number of shards targeted**, plan on each shard, and total execution cost.

### 18.4. Do not directly modify config metadata

Commands exist to let operators read cluster state. However, **never run update/insert/delete directly on internal config metadata structures to move chunks**. Use MongoDB-supported APIs and controlled procedures.

## 19. Enabling/disabling the balancer in a test environment

In supported versions, `mongosh` provides administrative helpers:

~~~javascript
sh.stopBalancer();
~~~

and:

~~~javascript
sh.startBalancer();
~~~

**These operations change cluster state**; do not run them casually on production. Leaving the balancer disabled for long periods can let data distribution drift unevenly as workloads/collections grow.

### 19.1. When to consider pausing?

Certain maintenance or troubleshooting windows may call for pausing migrations after evaluation and approval.

Do not stop the balancer merely because a query is slow without proving migrations are the cause. Measure CPU, I/O, network, lock/latency, migration timing, and query plans first.

### 19.2. Do not force migrations just to “even things out nicely”

Moving a chunk can:

- Worsen query locality.
- Violate zone constraints.
- Increase network traffic.
- Hit oversized range issues.
- Create churn while the workload is unstable.

Do not manually balance chunk counts without understanding your operational target and your version’s balancing algorithm.

### 19.3. What to monitor after re-enabling

- Can the balancer run needed migrations?
- Are any ranges blocked by zones/capacity?
- Are there migration errors/retries?
- Are storage and workload moving toward targets?
- Is p95/p99 latency fluctuating abnormally?

## 20. Adding a new shard and rebalancing

Suppose a cluster has two shards:

~~~text
Shard A: 1.2 TB
Shard B: 1.1 TB
~~~

Adding an empty Shard C with free capacity does not mean every collection immediately rebalances to **0.77 TB / shard** right after `addShard`.

Depending on collections, chunks/ranges, balancer, zones, and data volume:

1. The new shard joins the cluster.
2. Metadata registers the new shard.
3. Eligible ranges are gradually selected for transfer.
4. Migrations move data and ownership.
5. Balance converges over time.

### 20.1. Factors causing slow rebalancing

- Balancer is stopped or paused.
- Zones prohibit placing ranges on the new shard.
- Chunks are oversized/hard to move.
- Low disk/network throughput.
- One shard is overloaded.
- Migration conflicts or retries.
- Collection is too small to require distributing many ranges.

### 20.2. Expanding storage does not automatically distribute every query

Adding shards will not help queries reading a single hot tenant if all those queries still target the same shard.

You must align topology, shard key, and query patterns together.

## 21. Good and bad shard keys through workload examples

Suppose a SaaS system has:

~~~text
100,000 tenants
95% small tenants
5% large tenants
Top 10 tenants generate 60% of writes
Queries:
  - 65% fetch order by tenantId + orderId
  - 20% fetch orders by tenantId + date range
  - 10% search by customerId
  - 5% system-wide reports
~~~

Candidate options:

### 21.1. Choosing { tenantId: 1 }

Strength: many queries include `tenantId` and can target by key.

Risk: overly large or hot tenants become single-value shard key sets that cannot be split by `tenantId` alone.

### 21.2. Choosing { tenantId: 1, orderId: 1 }

Strength: adds granularity within each tenant, allowing targeted queries when both `tenantId` and `orderId` are present.

Trade-off: queries with only `tenantId` may touch multiple chunks/shards if a tenant spans widely. If `orderId` increases monotonically within a tenant, writes may hotspot at that tenant’s tail range.

### 21.3. Choosing { orderId: "hashed" }

Strength: spreads writes by hashing `orderId`.

Trade-off: queries filtering only by `tenantId` may scatter-gather. Must weigh the requirement to read across a single tenant’s orders and the query cost.

### 21.4. Do not choose by intuition

To decide, analyze:

- Field cardinality and frequency distribution.
- Actual query templates.
- Per-tenant distribution.
- Indexes and explain plans.
- Peak-hour load.
- Storage/latency limits.
- Feasibility of changing the shard key later.

A field appearing in 80% of queries is not necessarily a good key if its value distribution is heavily skewed.

## 22. Compound shard keys and field ordering

Shard key:

~~~javascript
{ tenantId: 1, orderDate: 1 }
~~~

differs from:

~~~javascript
{ orderDate: 1, tenantId: 1 }
~~~

For the query:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderDate: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
~~~

Putting `tenantId` first helps group ranges by tenant, though final targeting depends on chunk boundaries and distribution.

For a query filtering only on `orderDate`, putting `tenantId` first prevents narrowing a tight prefix range, leading to hitting more shards.

### 22.1. Equality prefix is usually valuable

Queries with equality on the leading prefix of a shard key generally give clearer routing predicates than filtering only on trailing fields of a compound key.

Still, `mongos` may target **multiple shards** if matching ranges span multiple chunks.

### 22.2. Unique indexes in sharded collections

Unique constraints on sharded collections have restrictions tied to the shard key. Do not assume you can create arbitrary cluster-wide unique indexes without checking shard key prefix, mechanisms, and version rules.

If `orderId` must be globally unique across the system, shard key, index, and ID generation design must satisfy uniqueness constraints.

### 22.3. Missing/null shard keys

Documents with missing or null shard key fields follow MongoDB’s specific handling rules depending on key and operation. Many documents with missing/null keys can pile into one region of the key space and degrade distribution.

Thus, use schema validation and data planning upfront rather than expecting sharding to paper over schema inconsistencies.

## 23. Metadata lifecycle during a migration

Suppose chunk **[K1, K2)** starts on Shard A and migrates to Shard B.

~~~text
T0: config metadata => [K1, K2) belongs to Shard A
T1: mongos M1 caches location A
T2: migration starts (A -> B)
T3: recipient syncs required data
T4: metadata commits ownership to B
T5: mongos M1 may briefly retain stale cache
T6: router hits stale condition, refreshes metadata
T7: queries for [K1, K2) target Shard B
T8: orphaned data on donor cleaned up per mechanism
~~~

This is a conceptual timeline; all milestones are logical phases rather than identically named public events across every MongoDB release.

### 23.1. Why must clients not route using their own static map?

If an application hardcodes rules like tenant A -> Shard 1 and tenant B -> Shard 2 and connects directly, the mapping breaks after migration.

Let **mongos and routing metadata** pick the target shard, unless you are deliberately running an entirely different application-managed partitioning architecture rather than MongoDB native sharding.

### 23.2. Stale metadata does not equal data corruption

A router using stale cache may need to refresh. That alone does not prove data loss; check server errors, migration state, routing versions, and query results via `mongos`.

However, prolonged or recurring stale errors seriously affecting requests still warrant investigation—do not dismiss every error as normal.

## 24. Balancer and zone placement during a region loss

Suppose:

~~~text
Zone APAC: Shard A, Shard B
Zone EMEA: Shard C, Shard D
~~~

If Shard A goes down, the balancer may look at whether Zone APAC ranges can live on Shard B. However, one remaining valid shard may lack capacity, or migrations may be impossible under current conditions.

### 24.1. The balancer is not replica set failover

If one `mongod` member in Shard A’s replica set fails, replication/elections handle **Shard A**’s availability. The balancer is not a tool for replacing a primary inside a replica set.

If an **entire shard** becomes unavailable, cluster behavior is affected depending on which collections and ranges reside on that shard. Moving chunks between shards is a placement concern; it does not substitute for reading data from an entirely lost shard.

### 24.2. Zones can constrain options

Data restricted to Zone APAC must not automatically migrate to Zone EMEA for general balancing if doing so violates policy.

Before designing zones, ensure sufficient shards and capacity exist to survive expected failure scenarios.

## 25. Config server, mongos, and shard failures

The three component types have different failure impacts:

| Failed component | General consequence |
| --- | --- |
| One `mongos` | Clients can switch to another router if configured and infrastructure permits |
| Config server member | Metadata availability depends on CSRS quorum and conditions; config/metadata ops may be affected |
| One member in a shard replica set | That shard’s replica set handles failover if quorum holds |
| Entire shard unavailable | Data/ranges on that shard may not be served normally |
| Network between `mongos` and a shard fails | Operations targeting that shard may fail/time out |
| Network between shards | Migrations/coordination and some distributed operations may be affected |

### 25.1. Config servers are the critical metadata plane

It is not true that config servers are only needed for rare admin tasks. Sharding metadata and configuration changes depend on CSRS availability.

Deploy the CSRS per HA guidelines with proper backups; do not place all config server members in a single failure domain if zone/region fault tolerance is required.

### 25.2. Do not equate mongos with a shard

`mongos` is a router. It has no full copy of data to “rescue” you when a data shard is lost.

Deploying more `mongos` routers increases routing availability/capacity, but does not increase data replicas per shard.

## 26. How do sharding and replication interact?

A sharded collection can span Shard A and Shard B, each being its own replica set.

~~~text
Collection orders:
  Range X -> Shard A replica set
  Range Y -> Shard B replica set

Shard A:
  primary A1
  secondary A2
  secondary A3

Shard B:
  primary B1
  secondary B2
  secondary B3
~~~

A write into Range X is routed to Shard A and replicated according to Shard A’s mechanism.

### 26.1. Migration does not replace replication

Moving Range X from Shard A to B differs from adding secondary A4 to Shard A. Migration changes **which shard owns** the range; replication maintains copies **within the same shard replica set**.

### 26.2. Balancing and replica elections can concurrently affect latency

If a shard is undergoing an election, or recipient/donor is under heavy load, migrations may fail, stall, or retry. When diagnosing latency spikes, inspect all of:

- Balancer/migrations.
- Replica set primary changes.
- Replication lag.
- Disk I/O and cache pressure.
- Network congestion.
- Query plans and indexes.

Do not blame every latency increase on the balancer without observational data.

## 27. Indexes on a sharded collection

A shard key requires a supporting index per MongoDB rules. However, other business queries also need indexes.

Example collection sharded on:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

The API frequently filters:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
}).sort({
  createdAt: -1
});
~~~

Consider an index supporting both predicate and sort:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

This is a **query-serving index**; it does not mean changing the current shard key.

### 27.1. Routing vs. indexes

- The shard key tells the router **which shard(s) to send to**.
- Secondary indexes tell each shard **how to locate documents**.

A query may need optimization at both layers.

### 27.2. Explain per shard

When a query hits multiple shards, `executionStats` should be read per shard. One shard may finish quickly while another executes a huge `COLLSCAN` due to skewed data distribution or a different index/plan.

Never look only at total duration and ignore the slowest shard.

## 28. Update, delete, and upsert on a sharded collection

Write commands also require routing.

Example update with the full shard key:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    orderId: "ORD-1001"
  },
  {
    $set: {
      status: "SHIPPED"
    }
  }
);
~~~

`mongos` has enough information to determine the range containing the key, given appropriate configuration and query structure.

### 28.1. Writes missing the shard key

Example:

~~~javascript
db.orders.updateOne(
  {
    status: "PENDING",
    customerId: "C-01"
  },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

Routing capability, requirements for `updateOne`/`upsert`, and supported behaviors have evolved across MongoDB versions. Do not assert that every `updateOne` lacking a shard key is always allowed or always rejected across all versions.

General design principle: **include the appropriate shard key in the filter whenever possible**, giving the server a clear target and lowering document lookup cost.

### 28.2. Upserts have specific rules

When an operation specifies **upsert: true**, the server may need to determine where to insert a new document. Rules around shard keys, equality predicates, and upserts depend on server version and operation type.

Before production use, verify documentation for your running MongoDB version.

### 28.3. Do not change the shard key casually

Shard keys have constraints on value updates and key design changes. MongoDB supports mechanisms such as refining the shard key or resharding a collection in versions that provide them.

Do not treat changing a shard key like dropping and recreating an index. It can affect the placement and routing of all data.

## 29. Resharding and refining the shard key

When a shard key no longer fits, you may need one of:

- **Refine shard key:** append suffix fields to the key pattern under permitted rules to increase key granularity within ranges.
- **Reshard collection:** reorganize data under a different shard key when supported by your MongoDB version/topology.
- **Change the data model:** e.g., partition by tenant/bucket or adjust queries for better distribution.

### 29.1. Refining is not resharding

Refining typically extends a key by adding suffix fields per MongoDB’s rules. Resharding reorganizes data distribution broadly.

Both are architectural decisions requiring evaluation of compatibility, indexes, workloads, disk headroom, migration/resharding capacity, and rollback.

### 29.2. Choosing right from the start still matters

Even with resharding available, changing keys on a large collection incurs operational cost and risk. Never pick an arbitrary key assuming you can swap it effortlessly later.

## 30. Monitoring distribution and migration health

A sharding dashboard should track:

| Metric group | What to know |
| --- | --- |
| Data | Storage size and document count per shard |
| Chunks/ranges | Count and ownership distribution |
| Balancer | Enabled, current activity, migration successes/failures |
| Zones | Whether ranges reside in the right shard groups |
| Routing | Targeted vs. scatter-gather, shards per query |
| Query execution | CPU, p95/p99, keys/documents examined |
| Replication | Primary changes, replication lag per shard |
| Capacity | Disk utilization, IOPS, cache, network |
| Metadata plane | Config server health, routing errors |
| App | Server selection errors, timeouts, duplicate retries |

### 30.1. Signs of data skew

- One shard has significantly higher storage usage.
- Chunk/range counts or sizes remain skewed across multiple balancing rounds.
- Repeated migration failures.
- A zone lacks enough valid shards.
- Large chunks cannot be split/moved.
- A new shard is added, yet ranges do not move onto it.

### 30.2. Signs of workload skew

- One shard has far higher CPU/IOPS than the rest.
- Write latency for one tenant is very high.
- Most queries hit all shards.
- Adding shards does not improve API p95 latency.
- One prefix/key value generates most writes.

Investigate the shard key, access patterns, and indexes before merely tweaking the balancer.

## 31. Controlled balancer testing

An illustrative lab test:

**Goal:** after adding a shard or altering distribution, verify that MongoDB can move ranges as needed and routing stays accurate.

### 31.1. Preflight

1. Confirm each shard’s replica set is healthy.
2. CSRS and `mongos` are operating normally.
3. Capture `sh.status` and collection distribution.
4. Record balancer state.
5. Record zones, special chunks/ranges, and disk headroom.
6. Run a read/write workload tagged with request IDs.
7. Define stop thresholds if latency spikes or errors appear.

### 31.2. During the test

Observe:

- Does the balancer schedule migrations when real imbalance exists?
- Do donor and recipient have sufficient resources?
- Does query routing remain accurate?
- Are there abnormal stale metadata refresh errors?
- Does query latency spike?
- Does application data remain consistent?

### 31.3. Post-test

- Confirm distribution moved toward the goal.
- No lingering migration errors.
- Targeted and scatter-gather queries return accurate results.
- p95/p99 metrics return within thresholds.
- Verify zone placement.
- No business duplicates caused by retries.
- Close the test with a report of actual measurements, not just a single `sh.status` snapshot.

### 31.4. Do not force migrations in production

Manual helpers for moving chunks/ranges vary in detail by release and can impact storage and routing. This lesson intentionally does not ask learners to force chunk moves in production; use a lab topology and commands supported by your version’s documentation.

## 32. Java Sync Driver: targeted query via mongos

Java applications should connect using the sharded cluster’s connection string (typically pointing to `mongos` routers or the platform-provided seed endpoint).

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ShardedOrdersQuery {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing sharded cluster MONGODB_URI"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {

            MongoDatabase database =
                    client.getDatabase("sharding_lab");

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            Bson filter = Filters.and(
                    Filters.eq("tenantId", "TENANT-A"),
                    Filters.eq("orderId", "ORD-1001")
            );

            FindIterable<Document> result =
                    orders.find(filter);

            for (Document order : result) {
                System.out.println(order.toJson());
            }
        }
    }
}
~~~

With shard key **{ tenantId: 1, orderId: 1 }**, the filter provides the full key so `mongos` can route to the matching range.

### 32.1. Example query that may scatter-gather

~~~java
Bson filter = Filters.eq("status", "PAID");

orders.find(filter).forEach(
        order -> System.out.println(order.toJson())
);
~~~

The query above lacks the shard key in this example. `mongos` may need to dispatch it to multiple shards. The driver cannot infer `tenantId` if the application does not provide it.

### 32.2. Do not cache a tenant-to-shard list on the client

Applications should send valid queries through `mongos`. Maintaining a custom `tenant -> shard` map in Java goes stale whenever chunk migration or resharding occurs.

### 32.3. Errors during migration

For transient errors such as network hiccups, topology changes, and write concern timeouts, applications should retry appropriately by operation type, using `requestId`/idempotency when needed.

Never blindly retry non-idempotent side-effecting commands indefinitely; a write may already have been applied even though the client never received the response.

## 33. Java Sync Driver: aggregate and explain to understand routing

A summary aggregation may hit multiple shards:

~~~java
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import org.bson.Document;

import java.util.Arrays;

orders.aggregate(Arrays.asList(
        Aggregates.group(
                "$status",
                Accumulators.sum("count", 1)
        )
)).forEach(
        row -> System.out.println(row.toJson())
);
~~~

To analyze routing from `mongosh`, it is often easiest to start with:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
], {
  explain: true
});
~~~

Or use `explain` on `find` as in section 10. Specific Java Driver `explain` invocation methods and output shapes depend on driver/server documentation. Focus not on line count, but on **shard participation and execution cost**.

## 34. Case study: uneven growth of a SaaS tenant

Suppose initially:

~~~text
Shard A: 400 GB, 1,500 writes/s
Shard B: 380 GB, 1,400 writes/s
Shard C: 390 GB, 1,450 writes/s
~~~

One year later:

~~~text
Shard A: 700 GB, 20,000 writes/s
Shard B: 450 GB, 1,800 writes/s
Shard C: 460 GB, 1,900 writes/s
~~~

One large tenant grew rapidly and now accounts for most writes.

### 34.1. Hypotheses

1. The tenant has a single shard key value creating a hotspot.
2. Writes hit the tail of a monotonically ascending ranged key.
3. The tenant’s chunk is oversized or cannot be split.
4. The balancer is disabled or constrained by zones.
5. Migrations are failing due to capacity/replication/network.
6. Byte sizes are not heavily skewed, yet query workload concentrates on one shard.

### 34.2. Investigation steps

- Confirm the shard key pattern and key distribution.
- Check `sh.status` and migration/balancer metrics.
- Check whether query filters target properly.
- Measure QPS/latency per shard.
- Inspect chunk/range sizes and hot key values.
- Check zone rules.
- Inspect explain plans of top queries.
- Re-evaluate the key, bucketing, or resharding if necessary.

### 34.3. Why might adding shards not solve it?

If 20,000 writes/s all target a single shard key value, moving the chunk holding that value to Shard D only turns Shard D into the hot shard.

The root problem is the ability to **split workload by key**, not shard count alone.

## 35. Case study: geographic distribution and zones

A system has APAC and EMEA tenants and prefers storing each group’s documents on shards in the corresponding regional infrastructure.

### 35.1. Shard key design

Example:

~~~javascript
{ region: 1, tenantId: 1, documentId: 1 }
~~~

With `region` as the prefix, per-region ranges can be expressed with zones. However, if many queries specify only `tenantId` without `region`, routing becomes less selective.

The application must ensure `region` is supplied in latency-sensitive operations or have a reliable mechanism to resolve the region.

### 35.2. Placement policy

~~~text
ZONE_APAC:
  shard-apac-1
  shard-apac-2

ZONE_EMEA:
  shard-emea-1
  shard-emea-2
~~~

### 35.3. Items to verify

- Queries actually supply `region`/`tenantId`.
- Data is distributed into the correct zones.
- Sufficient capacity remains if one shard in a zone fails.
- Replication members of each shard also comply with locality constraints.
- Backups and logs do not inadvertently violate residency.
- A tenant region-migration mechanism is clearly designed.

Zone placement alone does not satisfy all data compliance requirements.

## 36. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| Adding shards makes every query faster | Query routing and workload determine performance |
| Sharding is replication | Sharding splits data; replication copies within a shard |
| `mongos` stores the full collection | `mongos` is a router, not a data-bearing shard |
| Config servers process every CRUD request | `mongos` caches metadata and routes to shards |
| A chunk is a file on disk | A chunk is a logical shard key interval |
| Each shard holds only one chunk | A shard can own many ranges |
| Every chunk has the same document count | Document sizes and distributions vary |
| Target chunk size is a hard ceiling | Ranges can exceed the target |
| Splitting moves data to another shard | Split divides a range, usually without changing owner |
| The balancer only equalizes chunk count | Criteria vary by version, including size and zones |
| The balancer fixes a bad shard key | One hot key value can still overload one shard |
| Having the shard key in a query guarantees one shard | Predicates may match multiple chunks/shards |
| Having an index means the query is targeted | Indexes are local execution; routing needs shard key metadata |
| Hashed keys help range queries on original values | Hashing breaks range locality on original values |
| Hashed keys split a single hot tenant | A single hash value still maps to one location |
| Routers must restart after migration | Routing metadata has refresh mechanisms |
| Orphaned data means the app sees duplicates | Ownership/routing enforces proper semantics |
| Zones replace the shard key | Zone ranges are defined over the shard key |
| Zones are a complete ACL control | Separate security and compliance controls are needed |
| Config metadata can be updated like business data | Never edit internal metadata directly |
| Adding a shard distributes data instantaneously | Balancing/migrations depend on data and policies |
| The balancer performs primary failover | Elections belong to each shard’s replica set |
| `w:majority` means every shard saved every write | Write concern applies per operation/target semantics, not all shards |
| Updates without the shard key work in every version | Rules depend on operation and server version |
| Resharding is just swapping an index | It can involve large-scale data and metadata movement |

## 37. Hands-on exercises: shard keys and targeting

### Exercise 1 – Identify shard key ranges

A collection is sharded on:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Given these values:

~~~text
TENANT-A / ORD-1001
TENANT-A / ORD-9999
TENANT-B / ORD-1001
TENANT-C / ORD-0001
~~~

Sort them by shard key and sketch three contiguous intervals covering the key space. Explain why boundaries are tuples rather than `orderId` alone.

### Exercise 2 – Targeted or scatter-gather?

With the key above, analyze:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
});
~~~

~~~javascript
db.orders.find({
  tenantId: "TENANT-A"
});
~~~

~~~javascript
db.orders.find({
  orderId: "ORD-1001"
});
~~~

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Identify which query supplies the full shard key, which queries may hit multiple chunks/shards, and why exact conclusions require real placement metadata.

### Exercise 3 – Explain targeted vs. scatter

In the lab:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
}).explain("executionStats");
~~~

Compare with a query filtering on `status`. Record the number of shards involved and the stage/index on each shard. Do not compare only `executionTimeMillis`.

### Exercise 4 – Hashed shard key

A collection is sharded on hashed `customerId`. Explain why equality queries on `customerId` can be targeted whereas range queries on the original `customerId` may need to be sent to multiple shards.

### Exercise 5 – Monotonically increasing key

An `events` collection is ranged-sharded on `createdAt`, with continuously increasing `createdAt` values. Predict insert hotspots and propose two ways to adjust the shard key model, along with range-query trade-offs.

## 38. Hands-on exercises: chunks and the balancer

### Exercise 6 – Split and migration

Initially:

~~~text
Shard A owns [0, 1000)
Shard B owns [1000, 2000)
~~~

Perform a logical split of `[0, 1000)` into `[0, 500)` and `[500, 1000)`. After the split, which shard owns the two ranges?

Next, simulate migrating `[500, 1000)` to Shard B. Draw the updated ownership table.

### Exercise 7 – Stale metadata

`mongos M1` caches `[500, 1000)` on Shard A. The balancer migrates the range to Shard B. Describe the role of metadata versioning/refresh and why applications should not route directly using their own cached map.

### Exercise 8 – Adding a shard

A cluster has Shard A at 700 GB and Shard B at 680 GB, and adds an empty Shard C. What conditions determine whether data can move to C? Why should you not expect sizes to equalize immediately right after `addShard`?

### Exercise 9 – Oversized range

One tenant accounts for 40% of data and the shard key is only `tenantId`. Explain why the balancer struggles to split that tenant’s hotspot and propose a suitable compound key or alternative model.

### Exercise 10 – Balancer state

In an authorized lab:

~~~javascript
sh.status();
sh.getBalancerState();
db.adminCommand({ balancerStatus: 1 });
~~~

Record: how many shards exist, which collections are sharded, whether the balancer is enabled, and whether anything blocks migrations. Distinguish **enabled** from **actively migrating**.

## 39. Hands-on exercises: zones, operations, and troubleshooting

### Exercise 11 – Zone placement

A collection has shard key:

~~~javascript
{ region: 1, tenantId: 1 }
~~~

Design zones for APAC and EMEA. List the checks required before running `sh.addShardToZone` and `sh.updateZoneKeyRange`. Explain why queries providing only `tenantId` can be hard to target accurately.

### Exercise 12 – Storage imbalance vs. write imbalance

Given the metrics:

~~~text
Shard A: 500 GB, 18,000 writes/s
Shard B: 500 GB, 2,000 writes/s
Shard C: 500 GB, 2,100 writes/s
~~~

Storage is already even in bytes. Will the balancer necessarily improve throughput? Analyze hot keys, query targeting, and the shard key.

### Exercise 13 – Zone vs. region failure

A zone has only one valid shard. If that shard is lost, can the balancer automatically move its ranges onto shards in another zone? Explain the conflict between placement restrictions and availability.

### Exercise 14 – Indexed but slow query

A query filtering by `status` uses an index on each shard, yet hits 12 shards and returns a huge number of documents. Analyze fan-out, merge, and network costs, and propose solutions aligned with query patterns.

### Exercise 15 – Diagnosing migrations

After adding a shard, the balancer does not move ranges. Build a checklist covering: balancer state, zone rules, size/capacity, oversized chunks, errors, source/destination health, resources, and version features.

### Exercise 16 – Java queries

From the Java Sync Driver example, write two methods:

- `findOrder(tenantId, orderId)` using the full compound shard key.
- `findPaidOrders()` filtering only on `status`.

Explain why the two methods have different routing behavior despite sharing the same `MongoClient` and collection.

### Exercise 17 – Evaluating shard keys before production

Suppose there are 50,000 tenants and 10 large tenants generate 70% of writes. Compare these keys:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, orderId: 1 }
{ orderId: "hashed" }
~~~

For each key, evaluate cardinality, hotspots, per-tenant query targeting, and cross-tenant reporting cost. No key is universally optimal without knowing the workload.

### Exercise 18 – Resharding decision

A cluster currently uses ranged `createdAt` and has a write hotspot on the tail chunk. Create a plan to evaluate whether resharding is needed: metrics to collect, candidate keys, query impact, temporary headroom, version support, maintenance window, rollback, and pass/fail criteria.

## 40. Sharding design checklist

Before moving a collection onto a sharded cluster:

1. **Workload:** real read/write metrics and top query patterns are documented.
2. **Shard key:** sufficient cardinality and non-extreme frequency skew.
3. **Hotspots:** evaluated monotonic, hashed, and large-tenant behavior.
4. **Targeting:** latency-sensitive queries supply sufficient key predicates.
5. **Indexes:** shards have indexes supporting local execution.
6. **Chunks:** ranges, target size, and oversized cases are understood.
7. **Metadata:** config server RS is healthy with backups and monitoring.
8. **mongos:** applications connect properly to routers with failover support.
9. **Balancer:** state, migration policy, and metrics are known.
10. **Zones:** placement reflects the shard key and has spare capacity.
11. **Capacity:** new shards have disk/network/IOPS headroom for migrations.
12. **Reliability:** every shard is a replica set with proper quorum and fault domains.
13. **Operations:** admin commands follow change control; never edit config metadata directly.
14. **Observability:** measure scatter-gather rate, imbalance, migrations, and replication.
15. **Future evolution:** plan exists to refine/reshard if the workload shifts.
16. **Data correctness:** updates/upserts/unique constraints match version rules.
17. **Retries:** handle ambiguous errors and idempotency safely.
18. **Backups:** replica sets and sharding do not replace backup/restore.

## 41. Conclusion

MongoDB Sharding distributes data based on a **shard key** and **chunks/ranges** across the key space. **Config servers** store configuration metadata, **mongos** uses routing metadata (typically cached) to forward requests to appropriate shards, and the **balancer** coordinates moving data ranges between shards according to version policies and algorithms.

A query containing the full shard key has a strong chance of targeting fewer shards. Queries missing the shard key can become scatter-gather even when every shard has indexes. A chunk is a logical interval **[min, max)**, not a file on disk; splitting only changes boundaries, whereas migration changes the owning shard. The balancer helps equalize storage, but **cannot by itself fix workload hotspots caused by a poor shard key**.

For sharding to pay off, design must align across all three layers:

- **Data model:** shard key, cardinality, ranges, zones.
- **Execution:** `mongos` routing, query patterns, indexes, explain plans.
- **Operations:** balancer/migrations, metadata health, replication, capacity, observability, and safe retries.

Scalability comes not just from shard count, but from **whether data and operations can actually be partitioned, routed, and operated safely**.

## References

- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/)
- [MongoDB Manual — Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- [MongoDB Manual — Range Based Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/)
- [MongoDB Manual — Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [MongoDB Manual — Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/)
- [MongoDB Manual — Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/)
- [MongoDB Manual — Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/)
- [MongoDB Manual — Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/)
- [MongoDB Manual — sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
