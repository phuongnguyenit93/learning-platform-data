# Roles of mongos, Config Server Replica Set, and Shards in MongoDB Sharding

## 1. Why does a MongoDB database need sharding?

A rental housing application may store millions of listings, contracts, searches, and payment histories. Initially, a single **replica set** can meet demand: the primary handles writes, while secondaries replicate data for fault tolerance and to support certain reads. However, when data and query load exceed the capacity of one replica set, simply adding RAM/CPU/disk to each machine may no longer be economical or scalable enough.

**Sharding** divides a collection’s data into portions placed across **multiple shards**, distributing storage capacity and part of the read/write load. Yet the application should not have to remember “which machine has contract 1001, and which machine has contract 1002.” MongoDB uses an architecture with components that have distinct responsibilities:

1. **mongos (query router):** the application entry point, routing requests to the appropriate shards and combining results.
2. **Config server replica set (CSRS):** maintains cluster coordination metadata, such as shard information, sharded collections, and the placement of shard key ranges.
3. **Shard:** stores and processes application data; in production, each shard is typically an independent **replica set**.

Overview diagram:

~~~text
                     API / Worker / BI Client
                               |
                         MongoDB Driver
                               |
                   +-----------+-----------+
                   |                       |
                mongos A                mongos B
                   |                       |
                   +-----------+-----------+
                               |
           Look up / refresh routing metadata
                               |
                  +------------v------------+
                  | Config Server Replica  |
                  | Set: cfg1, cfg2, cfg3  |
                  | Cluster-wide metadata  |
                  +-------------------------+
                               ^
                               | metadata about data location
                               |
                   +-----------+-----------+
                   |                       |
          +--------v--------+     +--------v--------+
          | Shard 01 (RS)   |     | Shard 02 (RS)   |
          | P, S1, S2       |     | P, S1, S2       |
          | Tenant data     |     | Tenant data     |
          | by ranges       |     | by ranges       |
          +-----------------+     +-----------------+
~~~

The lines in the diagram represent a **logical diagram**, not that every request always goes through the config server before reaching a shard. **mongos caches routing metadata in memory**, so in many situations it already knows which shard to query without contacting the config servers on every request.

### Learning objectives

After this lesson, you will be able to:

- Clearly describe **what mongos does and does not do**.
- Explain that **CSRS stores metadata rather than being the central store of all application data**.
- State the role of **shard replica sets** and primaries/secondaries within each shard.
- Diagram the flow of a **targeted query** versus a **scatter-gather query**.
- Understand **shard keys**, ranges/chunks, placement metadata, and the **balancer/chunk migration**.
- Analyze the impact when a **mongos**, **CSRS**, or **shard** becomes unavailable.
- Use **read-only mongosh commands** to inspect a sharded cluster.
- Choose appropriate connection, indexing, and observability strategies while avoiding false assumptions about consistency or performance.

> This lesson focuses on the sharded cluster architecture with a **dedicated config server replica set**. Some newer MongoDB versions also offer integrated config server and shard deployments; metadata/routing functions still need to be distinguished, though specific deployment procedures must follow the exact server version in use.

## 2. Distinguishing horizontal sharding from replica sets

Both mechanisms commonly appear together in a sharded cluster, yet they **solve two different goals**.

| Criterion | Replica set | Sharding |
| --- | --- | --- |
| Primary goal | Replicate the same dataset, fault tolerance, and failover | Partition data/load across multiple shards |
| Data across members | Primary and secondaries maintain copies of the same logical dataset | Each shard holds a subset of the sharded collection’s data |
| Determining data location | Does not use a shard key to split data across members | Routing is based on the shard key and placement metadata |
| When adding members | Adds copies; does not automatically increase horizontal logical data capacity | Adding shards can increase capacity and load distribution |
| Primary role | Receives writes within each replica set | Each shard replica set has its own primary |
| Failover handling | Election within the replica set | Failover occurs independently inside the respective shard/CSRS |

Two-shard example:

~~~text
Shard A: Replica Set A
  A-primary:    range A data
  A-secondary1: replica of range A
  A-secondary2: replica of range A

Shard B: Replica Set B
  B-primary:    range B data
  B-secondary1: replica of range B
  B-secondary2: replica of range B
~~~

**Common misconception:** thinking three secondaries of one shard are “three shards.” They are not. They are **three members of the same replica set**, all maintaining the logical data of that single shard.

With shards A and B, a document belonging to shard A does not automatically exist on shard B simply because replication is enabled. **Replication within a shard** and **partitioning across shards** are two separate dimensions.

## 3. mongos: query router, not a data server

### 3.1. Where does mongos sit?

Applications use the MongoDB driver to connect through one or more **mongos** instances. mongos receives commands such as **find**, **insert**, **update**, **delete**, and **aggregate**, then decides which shards must process them.

~~~text
App
 |
 | find({tenantId:"t001", orderNo:"SO-001"})
 v
mongos
 |
 | Based on shard key and routing metadata
 v
Shard owning the range containing that key
 |
 | executes on MongoDB data-bearing nodes
 v
mongos gathers/returns results
 |
 v
App
~~~

mongos does **not** store application orders like a shard. It may hold **routing metadata in memory**, session/connection state, and intermediate data needed for query processing, but it is not a replica of application data.

### 3.2. Main responsibilities of mongos

**1. Selecting target shards.** With a filter containing a sufficiently useful shard key, mongos can send requests to a single shard or a small group of shards.

**2. Fan-out when narrow routing is not possible.** If the filter lacks suitable shard key information, mongos may have to query many or all shards.

**3. Combining results.** For queries involving multiple shards, mongos can merge cursors and perform result post-processing such as merge sort/aggregation according to the execution plan.

**4. Coordinating certain cluster-level operations.** For example, some sharding administrative commands or DDLs are invoked through mongos and require consistent metadata; actual execution may involve other coordinating components depending on version.

**5. Managing routing when metadata changes.** When data ranges move between shards or metadata becomes stale, mongos must refresh its information and re-route according to server mechanisms.

**6. Forwarding appropriate concern/preference settings.** When the driver sends write concern, read concern, and read preference, mongos selects target nodes and forwards operations with the corresponding semantics; it does not replace each shard’s replication mechanism.

### 3.3. What does mongos not do?

- Does not persist user documents like a shard.
- Does not itself decide majority commits for writes inside a shard replica set.
- Is not a primary/secondary node in a shard’s replica set.
- Does not hold all cluster metadata as the ultimate source of truth; authoritative metadata belongs to the config server structure.
- Is not a mechanism guaranteeing every query touches only **one** shard.
- Does not automatically turn a multi-document, multi-shard write into an all-or-nothing transaction.
- Is not a Redis-style application query-result cache.

**mongos abstracts away data location; it does not eliminate the physical constraints of distributed data.**

### 3.4. Is mongos stateful or stateless?

mongos is often called a **stateless query router** with respect to **persistent application data**: if a mongos dies, no exclusive set of application documents on that mongos is lost.

However, at runtime, mongos still maintains:

- Connection pools and authentication/session state.
- Routing metadata cache.
- Cursor/aggregation state needed for active requests.
- Short-lived request coordination state.

Therefore, “stateless” does not mean an in-flight query will not be interrupted if that mongos fails. The driver must be able to select another router and handle retries for eligible operations.

### 3.5. Multiple mongos routers for availability

An architecture typically runs **more than one mongos**, placed close to API servers or behind an appropriate connection-balancing mechanism:

~~~text
API instance A ------ mongos A -----+
                                    +---- Sharded cluster
API instance B ------ mongos B -----+
~~~

When one router becomes unavailable, the application can continue through another router if the driver and connections are properly configured. **Having multiple mongos instances does not directly increase data storage capacity**; storage capacity depends on shards.

### 3.6. mongos and read preference

With **readPreference: primary**, corresponding reads select the replica set primary on each target shard. With **secondaryPreferred**, reads can be served by eligible secondaries on targeted shards, depending on topology and per-operation constraints.

Do not assume “all reads execute inside mongos itself.” mongos **routes and merges**, while application data is read from the shards.

## 4. Config server replica set: the cluster’s map and metadata brain

### 4.1. What is the CSRS?

The **Config server replica set (CSRS)** is a replica set dedicated to **sharded cluster metadata**. Instead of storing all listings/contracts, it stores the metadata that enables MongoDB to identify **shards, sharded collections, and how shard key ranges are distributed**.

Conceptual example:

~~~text
Config metadata:
  collection: shop.orders
  shard key: {tenantId:1, orderNo:1}

  range R1: [MinKey ... "t020") -> shard01
  range R2: ["t020" ... "t050")   -> shard02
  range R3: ["t050" ... MaxKey)   -> shard03

  placement metadata version: V...
~~~

This is a simplified illustrative model, not the actual schema of internal `config` database documents. In practice, range partitioning follows the **full shard key**, which can be compound and includes version/collection UUID details.

### 4.2. What types of metadata does the CSRS store?

Typical groups of information include:

- List of **shards** participating in the cluster along with identifiers/connection info.
- List of databases and collections involved in sharding.
- The **shard key** chosen for each sharded collection.
- **Chunk/range placement**: which shard key ranges currently belong to which shard.
- Version/epoch/UUID metadata used to detect stale routing information.
- **Zone** settings/boundaries and placement rules when used.
- Administrative metadata supporting balancing and other cluster-level operations.

Do not write directly to the **config database** or modify these metadata collections via regular CRUD. Changes to sharding metadata must go through **MongoDB-supported commands and procedures**.

### 4.3. Why must config servers be a replica set?

Metadata determines where data lives. If a single process held that map and failed, the entire cluster could lose the ability to coordinate certain routing/metadata operations. Thus, the CSRS uses **replication** to maintain the availability and durability of cluster metadata.

In a common dedicated CSRS model:

~~~text
                   Config Server Replica Set

                   cfg-primary (metadata)
                       /          \
                      v            v
               cfg-secondary1  cfg-secondary2

                      Consistent metadata,
                election/failover when appropriate
~~~

Production deployments typically use **at least three config server members** per MongoDB guidelines and appropriate configuration. Special requirements regarding voting members, arbiters, delayed members, write concern, and CSRS configuration must be verified against the server version; do not pick a configuration merely because “another replica set used it.”

### 4.4. CSRS is not a data warehouse or direct business query target

A request fetching an Order can be routed by mongos based on the map in the CSRS, but **the actual Order document resides on a shard**.

~~~text
mongos --> look up/refresh metadata --> CSRS
mongos --> read Order document -------> Shard
~~~

Applications do not send **db.orders.find()** to a config server to read orders. Business CRUD operations go through mongos and then to the corresponding shard. Access to and operations on the config database are high-risk administrative tasks.

### 4.5. Config server primary and metadata changes

In a dedicated CSRS, the primary plays a critical role for operations that modify metadata. During an election or when unable to perform required metadata writes, operations such as adding shards, changing placement, sharding DDL, and certain migration steps can be impacted.

**Do not equate a CSRS outage with every data query stopping immediately.** `mongos` instances and shards retain cached metadata and can continue some reads/writes in a steady state. However, operations requiring metadata refreshes or placement commits may fail, and prolonged outage impacts cluster serviceability.

### 4.6. Config shards in newer versions

Some modern MongoDB releases support a **config shard** topology, where config server functionality and storage for part of the application data can co-reside on a set of members as specified by the product documentation. This **does not eliminate the metadata role**: routers still need a consistent metadata source, and shards remain responsible for serving data.

Because these exercises focus on the three components in an easy-to-learn architecture, all diagrams below assume a **dedicated CSRS** unless noted otherwise. When operating a real cluster, verify the topology/version and corresponding documentation.

## 5. Shard: where documents are stored and data operations execute

### 5.1. A shard is typically a replica set

A shard is the unit that stores a portion of a sharded collection’s dataset. In production, each shard is usually deployed as an independent **replica set** to prevent a single machine failure from making that data subset unavailable.

~~~text
Shard 01 / RS shard01:
  shard01-primary
  shard01-secondaryA
  shard01-secondaryB

Shard 02 / RS shard02:
  shard02-primary
  shard02-secondaryA
  shard02-secondaryB
~~~

The replica sets of **each shard are independent** regarding elections and local replication. A primary change on shard01 does not force shard02 to change primary. mongos is responsible for sending requests to the appropriate node according to topology and read preference.

### 5.2. What does a shard actually do?

- Stores documents/ranges assigned to that shard.
- Maintains **indexes** for the documents currently residing on that shard.
- Executes filters, sorts, aggregations, and CRUD operations forwarded by mongos.
- Runs **oplog/replication** within the shard’s replica set.
- Participates in **chunk/range migration** when data moves between shards.
- Returns data or partial results for mongos to merge/coordinate further.

A shard does **not** inherently know what data every user request needs across all other shards. It primarily processes its assigned slice of work according to the cluster’s metadata/routing.

### 5.3. Which shard does a document belong to?

For a sharded collection, MongoDB uses the **shard key** to determine where a document is placed within **ranges/chunks** owned by shards.

Example **orders** collection with shard key:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

Documents:

~~~javascript
{ _id: "o001", tenantId: "t001", orderNo: "SO-001", amount: 100 }
{ _id: "o002", tenantId: "t001", orderNo: "SO-002", amount: 250 }
{ _id: "o003", tenantId: "t002", orderNo: "SO-001", amount: 130 }
~~~

are ordered by the value of the **compound key**. All orders of `t001` do not permanently stay on one single shard in every case; a large tenant can span multiple ranges across different shards if the shard key and placement allow.

### 5.4. Replicas within a shard vs. copies across shards

If `o001` resides on `shard01`, it can exist on the primary and secondaries of `shard01`’s replica set. It does **not** automatically exist on `shard02` merely because `shard02` is another shard.

mongos must route to the right shard instead of sending a read to `shard02` and hoping a “cluster secondary” will have the same document.

### 5.5. Do not connect directly to a shard to query the sharded dataset

An application connecting directly to a `mongod` of `shard01` may see only the portion of data on `shard01`, missing documents on `shard02`. More importantly, direct access can bypass routing/metadata rules and is not a valid application interface for sharded collections.

**Operational principle:** applications access a sharded cluster **through mongos / a driver configured to use mongos**, rather than replacing mongos by listing shard `mongod` nodes and picking manually.

Direct connections to a shard may be used for specific diagnostic/administrative tasks per MongoDB guidance, not for normal application CRUD.

## 6. How the three roles interact when reading a document

Consider the **shop.orders** collection with shard key:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

The application sends the query:

~~~javascript
db.orders.findOne({
  tenantId: "t001",
  orderNo: "SO-001"
});
~~~

Conceptual flow:

~~~text
   [1] App -> mongos: findOne(t001, SO-001)
                       |
                       v
   [2] mongos inspects shard key and routing metadata
                       |
                       v
   [3] Range for (t001, SO-001) belongs to shard01
                       |
                       v
   [4] mongos -> shard01 replica set
                       |
                       v
   [5] Shard01 uses index/plan to locate document
                       |
                       v
   [6] Shard01 -> mongos -> App
~~~

There is **no mandatory requirement** for mongos to query the CSRS at step [2] on every request. It can use its cached routing metadata. If routing metadata is no longer valid, mongos uses a detection and refresh mechanism.

### 6.1. What enables a query to hit just one shard?

With the compound shard key **{tenantId:1, orderNo:1}**, an equality filter on the **entire shard key** can pinpoint the exact range holding the document, so it is typically a **targeted query**.

~~~javascript
// Contains both shard key components:
db.orders.find({
  tenantId: "t001",
  orderNo: "SO-001"
});
~~~

If the query only filters:

~~~javascript
db.orders.find({ tenantId: "t001" });
~~~

then mongos can identify a set of **ranges matching the `tenantId` prefix**, but those ranges may reside on **multiple shards**. Never claim that a shard-key-prefix query always hits only a single shard.

If the query only filters:

~~~javascript
db.orders.find({ status: "paid" });
~~~

and `status` does not aid shard key routing, mongos typically must query **many or all shards** of the collection.

## 7. Targeted queries and scatter-gather

### 7.1. Targeted query

A **targeted query** means mongos can narrow down the target to a single shard or a smaller subset of shards based on query predicates and placement metadata.

~~~text
find({tenantId:"t001", orderNo:"SO-001"})
                |
              mongos
                |
              shard01
~~~

Potential benefits include:

- Fewer shards execute the request.
- Reduced network fan-out and result merging.
- More predictable latency for explicit key lookups.
- Enables scaling when workload is distributed across appropriate shards.

**However, targeted does not mean automatically fast.** If the target shard lacks a suitable index or scans huge documents, the query can still scan many keys/documents inside that shard.

### 7.2. Scatter-gather

**Scatter-gather** occurs when mongos cannot narrow down the target shard set well enough:

~~~text
find({status:"paid"})
          |
        mongos
      /    |     \
     v     v      v
  shard01 shard02 shard03
     \     |      /
      \    |     /
        mongos
           |
      final result
~~~

mongos or related pipeline stages must collect and merge results from the targeted shards. This is not inherently wrong: cluster-wide reporting may need to read all shards. However, for an API fetching individual Orders by ID, constant scatter-gather usually signals a mismatch between the shard key and query patterns.

### 7.3. Cost of scatter-gather

- One user request multiplies into many internal requests.
- Latency can be dictated by the slowest shard.
- CPU/index scans are multiplied across many shards.
- Results requiring merge sort/group can consume RAM and network bandwidth.
- One unavailable shard can impact cluster-wide queries.

You cannot fix all of this simply by adding more `mongos` routers, because the cost lies in the **number of target shards and the work performed on each shard**.

### 7.4. When readConcern/readPreference are involved

If a request hits three shards, mongos must coordinate reads according to **read preference** (primary or eligible secondary) and **read concern** (local/majority/snapshot depending on command) on each shard. The consistency of a cross-shard query involves additional limits and coordination mechanisms, especially for transactions/snapshots.

Do not look at one slow secondary and assume mongos automatically waits for every other shard to catch up under all readConcerns; exact behavior depends on the operation and requested concern level.

## 8. Write flow through mongos

### 8.1. Insert with a full shard key

Example:

~~~javascript
db.orders.insertOne({
  _id: "o1001",
  tenantId: "t001",
  orderNo: "SO-1001",
  amount: NumberDecimal("100.00"),
  status: "created"
});
~~~

In a sharded collection, mongos inspects the document’s shard key to route the insert to the shard owning the corresponding range.

~~~text
App --> mongos --> inspect shard key
                     |
                     v
                 shard02 primary
                     |
             write + local replication
                     |
                     v
             ACK per write concern
                     |
             mongos --> App
~~~

mongos **does not store the authoritative copy of the Order**. Acknowledgment conditions depend on write concern and the mechanisms within the target shard replica set.

### 8.2. Update with shard key predicates

If an API updates using the full shard key:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "t001",
    orderNo: "SO-1001",
    status: "created"
  },
  {
    $set: { status: "paid" },
    $currentDate: { paidAt: true }
  }
);
~~~

mongos has much better routing information than an update with only:

~~~javascript
db.orders.updateOne(
  { status: "created" },
  { $set: { status: "paid" } }
);
~~~

Do not write ambiguous `updateOne` filters and expect mongos to “magically find the right order” when the filter can match multiple documents. Requirements around **targeting, shard keys, upserts, and multi-shard operations** vary across MongoDB versions; check the documentation for your exact version when using operations that omit parts of the shard key.

### 8.3. Write concern still belongs to the persisted data

~~~javascript
db.orders.updateOne(
  {
    tenantId: "t001",
    orderNo: "SO-1001"
  },
  {
    $set: { status: "paid" }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

On the target shard’s replica set, **w:"majority"** requires acknowledgment from a majority of eligible data-bearing members in that replica set. mongos forwards/coordinates the acknowledgment back to the client; it does not count as a majority vote for the shard.

### 8.4. Multi-document writes across multiple shards

An `updateMany` command or a sequence of two `updateOne` calls may touch multiple documents on different shards. **Do not treat them as automatically forming an all-or-nothing transaction.**

If business logic needs to atomically update Order, Payment, and Audit across multiple shards, MongoDB provides **distributed transactions** on supported topologies/versions. However, cross-shard transactions require extra coordination and resources and can incur write conflicts or timeouts. Do not use multi-shard transactions as a substitute for choosing an appropriate data model and shard key.

## 9. Shard key: the foundation of routing

### 9.1. Role of the shard key

The shard key is the field or combination of fields MongoDB uses to divide a sharded collection into routing ranges. Choosing the shard key affects:

- Which shard stores a document.
- Whether a query is targeted or must scatter-gather.
- Whether data and throughput are distributed evenly.
- Whether **hot** shards or key ranges form.
- Whether common equality/range predicates are supported.
- How difficult it is to change the sharding strategy later.

A poor shard key can leave a cluster with many shards while concentrating all load onto one shard.

### 9.2. Cardinality and distribution

Suppose you use:

~~~javascript
{ status: 1 }
~~~

in an `orders` collection with only three states (`created`/`paid`/`cancelled`). **Low cardinality** makes the group of documents sharing a value overly large, easily creating skewed distribution and offering poor targeting for queries that do not filter on `status`.

If you use:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

and `tenantId`/`orderNo` distribute well, requests knowing `tenantId + orderNo` can target precisely. However, a huge tenant can still generate hot load; measure per-tenant size, write frequency, and query patterns.

### 9.3. Range sharding

With **range-based sharding**, shard key values in BSON order are divided into **ranges/chunks** owned by shards.

~~~text
Ascending key ------------------------------------->
   [R1]          [R2]          [R3]           [R4]
   shard01       shard02       shard01        shard03
~~~

Advantage: queries over a contiguous range of the shard key can target the relevant chunks.

Risk: **monotonically increasing** keys such as write timestamps can funnel many new writes into the trailing range, creating a **hot shard/hot chunk** if distribution is unsuitable.

### 9.4. Hashed sharding

With a hashed shard key, MongoDB uses the hash value of the field for distribution. Example:

~~~javascript
{ tenantId: "hashed" }
~~~

Equality queries specifying `tenantId` can be routed by the corresponding hash value. Hashed sharding can improve distribution when the field has suitable cardinality.

**In return:** range locality by original value (such as a time window) no longer behaves like range sharding on that field. If one tenant is huge and all its documents share one hashed `tenantId` value, hashed `tenantId` alone **still does not split that single tenant’s load across multiple hash values**.

### 9.5. Compound shard key prefix

With:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

a query with only `tenantId` can target **a set of ranges** for that tenant. However, if the tenant spans multiple chunks across multiple shards, multiple shards still must be contacted. Queries with both `tenantId` and `orderNo` typically route more narrowly.

Do not confuse an **index prefix** with a **targeting guarantee**: a compound index supporting a filter does not guarantee targeting a single shard if the filter lacks the remaining shard key fields needed.

### 9.6. Shard key and indexes

Each shard still has its own local query planner and indexes to execute queries. In many cases, a sharded collection requires an appropriate index supporting the shard key, along with rules regarding unique indexes. A query routed to the right shard without a good index can still be slow.

Shard key selection and **workload index design** must be evaluated together, not as two independent tasks.

### 9.7. Changing the shard key is not a one-line config edit

MongoDB offers features such as **refine shard key** or **reshard collection** on supported versions, but changing keys carries real operational costs and constraints. You should not assume you can arbitrarily change a shard key without disruption like renaming a document field.

Therefore, before sharding in production, build a matrix of **query shapes, data distribution, write load, tenant sizes, and growth plans**.

## 10. Chunk/range: the unit of placement metadata

### 10.1. What is a chunk?

In a sharded collection, MongoDB represents data placement using **shard key ranges** (often called **chunks**). Each chunk has:

- Lower and upper key boundaries as defined in metadata.
- An owning shard.
- Associated version/placement metadata.

~~~text
Collection: orders
Shard key: {tenantId:1, orderNo:1}

  Chunk C1: [MinKey, key-A)   -> shard01
  Chunk C2: [key-A, key-B)    -> shard02
  Chunk C3: [key-B, MaxKey)   -> shard01
~~~

A single shard can own **multiple non-contiguous chunks**. A cluster does not always assign one single contiguous interval per shard.

### 10.2. A chunk is not a collection

A chunk is a **routing/placement** unit for part of a sharded collection’s data—not a separate user database and not a replica set.

If a document’s shard key falls into `C2`, it belongs to the shard owning `C2` according to current metadata. Inside that shard, the document is stored as a normal MongoDB document with its associated indexes.

### 10.3. Metadata can change via migration

During data balancing or placement changes, a chunk/range may move from `shard01` to `shard02`. Thus, the application must never store a static map saying “tenant `t001` lives on `shard01`.”

**mongos uses cluster metadata**, not a hardcoded lookup table in the API. When a key range moves, the router updates its routing via a refresh mechanism to keep sending requests to the right shard.

## 11. Balancer and chunk migration: who decides, who moves?

### 11.1. Goal of the balancer

A sharded cluster can become unevenly distributed due to:

- Adding a new shard.
- Rapid growth of a particular group of tenants.
- Some ranges accumulating more data than others.
- Applying zones or changing placement rules.
- Differences in workload distribution across shard keys.

The **Balancer** helps adjust placement to distribute data according to cluster rules. In the traditional dedicated CSRS architecture of modern MongoDB versions, the balancing coordinator resides with the **config server primary**; exact execution details and coordinator mechanics can vary by version.

Do not describe the balancer as “a random mongos moving documents” or “the app moving data whenever a query is slow.”

### 11.2. Component roles during migration

~~~text
      CSRS / Balancer / Cluster coordinators
               |
               | determine range to move,
               | manage coordination/metadata
               v
       Donor shard -----------> Recipient shard
           |                       |
       current data             receives/copies data
       + changes during move    and syncs changes
           |                       |
           +-----------+-----------+
                       |
             completes per protocol
             updates placement metadata
                       |
                    mongos
             refreshes routing when needed
~~~

Terminology:

- **Donor shard:** the shard currently owning the chunk/range being moved.
- **Recipient shard:** the shard receiving the range after migration.
- **CSRS/coordinator:** maintains metadata and coordinates ownership transfer per MongoDB’s protocol.
- **mongos:** routes requests using the active metadata version.

Data transfer is coordinated by the **shard nodes**, not by `mongos` loading every document into RAM and manually inserting it into another shard.

### 11.3. Migration does not allow applications to see duplicated data

During migration, temporary copies or documents in transition may exist according to protocol. MongoDB uses metadata versioning, range ownership rules, and **orphan cleanup** to ensure normal requests are served according to authoritative ownership.

Do not bypass `mongos` to query donor and recipient shards directly during a migration and conclude there is logical duplicate data just because the same document appears on both during transition.

### 11.4. Stale routing metadata

Suppose `mongos A` caches:

~~~text
range R -> shard01
~~~

After migration, the CSRS commits placement:

~~~text
range R -> shard02
~~~

When `mongos A` sends a request to `shard01` using stale metadata, the nodes detect the invalid routing version and trigger a refresh. `mongos` updates its route and retries the operation according to the protocol.

**Not every stale metadata event results in a user-visible error.** MongoDB handles and retries certain cases internally. Still, migrations, DDL, and cache refreshes can affect latency, and some requests can fail if limits or operational errors are exceeded.

### 11.5. Balancing does not equal absolute CPU balance

The balancer primarily addresses **placement/data distribution** per server policies. One shard can hold roughly the same data volume as another yet run much hotter because traffic concentrates on one tenant or one range.

Even storage distribution does not guarantee:

- Equal QPS across shards.
- Equal p99 latency.
- Identical disk I/O or cache hit ratios.
- Absence of hot chunks/hot shards.

**Shard keys and query patterns** remain the foundation of load distribution, while the balancer manages data placement within those bounds.

## 12. Zones: directing data to specific groups of shards

### 12.1. When location constraints are needed

Some systems require placing data by geographic region, tenant group, or storage tier. **Zones** (tag-aware sharding) allow associating shard key ranges with designated shard groups by policy.

Conceptual example:

~~~text
Zone APAC:
  APAC tenant ranges -> shard01, shard02

Zone EU:
  EU tenant ranges   -> shard03, shard04
~~~

The CSRS manages zone/placement metadata; the balancer/placement machinery executes adjustments within its capabilities and constraints. **mongos still uses routing metadata to find the shard that actually owns a range.**

### 12.2. Zones do not replace security policies

Zone placement does not automatically create tenant authorization rules in your API. Data residing on shards in the desired region still requires:

- Authentication/authorization.
- Accurate tenant filtering.
- Encryption/TLS and key management.
- Region-compliant backup/restore rules.
- Monitoring of placement compliance and migrations.

Never use zones as an excuse to omit `tenantId` conditions in queries.

## 13. Sharded and unsharded collections in the same database

### 13.1. Not every collection is automatically sharded

Within a sharded cluster, both can coexist:

- **Sharded collection:** documents are distributed according to a shard key.
- **Unsharded collection:** data is not automatically partitioned by a shard key even though the database lives in a sharded cluster.

Logical example:

~~~text
Database: shop
  orders          -> sharded by tenantId/orderNo
  eventLogs       -> sharded by tenantId/eventId
  appSettings     -> unsharded (small dataset)
~~~

For unsharded collections, placement/coordination rules depend on version; the traditional architecture assigns a **database primary shard** to hold unsharded collections. Modern versions add mechanisms to move unsharded collections; check server documentation.

### 13.2. Database primary shard vs. replica set primary node

Two easily confused concepts:

- **Primary shard of a database:** a database-level placement concept in a sharded cluster, important for unsharded collections in the traditional model.
- **PRIMARY member of a shard replica set:** the `mongod` process accepting writes for one shard replica set.

“Database primary shard = shard02” **does not mean shard02 is the only PRIMARY node in the entire cluster**. Each shard replica set has its own elections and primary.

### 13.3. Why must we distinguish them?

A request reading an unsharded collection goes to the shard holding that collection, whereas a request reading sharded `orders` is routed by shard key/range. Merely residing in the same database does **not** mean their documents sit on the same shard.

In particular, `$lookup` or aggregations involving multiple collections have constraints regarding sharding, join placement, and server versions; do not assume joins always run on a single server.

## 14. Component failures: what happens?

### 14.1. One mongos fails

If `mongos A` stops working:

- Requests attached to `mongos A` may fail or need to be retried.
- Shards and CSRS can continue operating normally.
- Clients configured with multiple `mongos` instances can pick another router.
- An in-flight query/cursor is not guaranteed to resume seamlessly on another router.

Key takeaway: **mongos scales with router count**, but clients still need proper error handling and conditional retries.

### 14.2. One config server member fails

In a 3-member dedicated CSRS, if one member fails while the CSRS retains quorum and a valid primary, metadata operations can continue, albeit with reduced fault tolerance.

If the CSRS loses quorum/primary:

- Metadata-modifying operations such as migrations, adding shards, or sharding DDL may be unable to execute.
- Some CRUD queries on existing data with valid cached routing metadata **may continue**.
- Requests needing fresh metadata/refreshes or corresponding administrative operations may fail.
- Exact impact depends on version, cache state, topology, and duration of quorum loss.

Do not claim either “if CSRS fails, all data disappears” or “CSRS doesn’t matter because mongos has a cache.”

### 14.3. One shard secondary fails

If `shard01` is a replica set and one secondary fails:

- `shard01`’s primary can continue accepting writes if election/acknowledgment conditions permit.
- Read preferences targeting secondaries may be affected.
- `writeConcern: majority` can slow down or time out if insufficient members remain.
- The shard’s fault tolerance is reduced.

`shard02` may not be directly affected, though scatter-gather queries spanning both `shard01` and `shard02` can be impacted if `shard01` becomes unresponsive.

### 14.4. A shard primary fails

The shard’s replica set can elect a new primary if quorum/eligibility holds. During election:

- Writes to that shard may temporarily fail or await retry.
- Drivers/`mongos` must update topology.
- In-flight requests may be interrupted.
- Write concern and retryable writes/idempotency remain essential.

**Failover in one shard does not automatically force other shards to change primary**, though queries touching the affected shard are still impacted.

### 14.5. An entire shard becomes unavailable

For a sharded collection, documents living on the unavailable shard **do not automatically appear on other shards**. Queries targeting only healthy shards may continue in some cases; queries needing data from the failed shard will fail.

Do not treat a multi-shard cluster as full replication of all data across all shards. **Each shard’s own replication** is responsible for the fault tolerance of that shard’s slice of data.

### 14.6. Losing a mongos vs. losing a shard

| Failed component | Where is application data? | Common impact | Risk mitigation |
| --- | --- | --- | --- |
| **One mongos** | Still on shards | Connection/router errors; in-flight requests may fail | Multiple `mongos`, driver selection/retries |
| **One shard secondary** | Remains on primary/other secondaries | Reduced replica redundancy, affects read preference | Sufficient members, lag/health monitoring |
| **Shard primary** | Shard’s replica set | Failover/election, brief write interruption | Properly configured replica set, retries |
| **Entire shard lost** | Data belonging to that shard is unavailable | Queries needing those ranges fail | Shard replication/backup/DR |
| **One CSRS secondary** | User data remains on shards | Reduced metadata redundancy | CSRS quorum, monitoring |
| **CSRS loses quorum** | User data remains on shards | Metadata changes/refreshes may fail; CRUD depends on cache/state | Restore CSRS quorum following procedure |
| **Network between mongos and shard** | Data not necessarily lost | Targeted requests cannot reach shard, timeouts | Network monitoring, controlled retries |

## 15. Consistency: three separate replica sets are not a single transaction

### 15.1. Shard replica sets and CSRS have independent replication

In the illustrative topology:

~~~text
CSRS:     cfg1/cfg2/cfg3           (metadata replication)
Shard01:  s01p/s01s1/s01s2        (shard01 data replication)
Shard02:  s02p/s02s1/s02s2        (shard02 data replication)
~~~

Each replica set has its own elections, oplog, and write concern/quorum within its own scope. You cannot satisfy a majority write on `shard01` by counting votes from `cfg1` or `shard02`.

### 15.2. WriteConcern majority when writing a document

Application sends:

~~~javascript
db.orders.insertOne(
  {
    _id: "o1002",
    tenantId: "t001",
    orderNo: "SO-1002"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

The write is routed to the shard owning the key; majority acknowledgment pertains to replication and write concern on that target shard. Metadata writes on the CSRS are a separate coordination mechanism and do not mean `mongos` replicates the document to all CSRS members.

### 15.3. Transactions across multiple shards

For example, a transfer between Wallets on `shard01` and `shard02` requiring all-or-nothing guarantees:

~~~text
Transaction
  Update wallet A (shard01)
  Update wallet B (shard02)
  Insert transfer audit (possibly another shard)
Commit transaction
~~~

MongoDB supports distributed transaction coordination on appropriate versions/topologies; **mongos participates in routing and coordinating the involved operations**, without storing every record. Distributed transactions carry higher cost than single-document updates and require retries/idempotency.

You cannot replace a transaction simply by sending three independent `updateOne` commands through the same `mongos`.

### 15.4. Read preference per shard

A scatter-gather query reading from multiple shards selects eligible nodes within each shard according to `readPreference`. With `secondaryPreferred`, data across shards may have different replication lags. For use cases requiring a consistent snapshot across multiple collections/shards, check **readConcern snapshot/transaction** support rather than assuming secondaries naturally sit at the same point in time.

## 16. Safely observing topology with mongosh

The following commands are meant for an **existing lab sharded cluster**, with `mongosh` connected through **mongos**. They primarily **read metadata/status**, without creating shards, altering config servers, or triggering migrations.

### 16.1. Verify you are connected to mongos

~~~javascript
const hello = db.hello();

printjson({
  msg: hello.msg,
  isWritablePrimary: hello.isWritablePrimary,
  maxWireVersion: hello.maxWireVersion
});

if (hello.msg !== "isdbgrid") {
  throw new Error(
    "This is not a connection to mongos; please use a sharded cluster URI."
  );
}
~~~

On `mongos`, **hello** typically reports **msg: "isdbgrid"** to distinguish it from `mongod`. Do not use **isWritablePrimary** alone to prove it is `mongos`, since a `mongod` primary is also writable.

### 16.2. sh.status()

~~~javascript
sh.status();
~~~

This command displays an overview of the sharded cluster depending on `mongosh` and server version, potentially including:

- List of shards.
- Active `mongos`/cluster metadata details.
- Database/collection sharding metadata.
- Shard keys and chunk/range distribution info.
- Balancer or zone details if configured.

**Output format is not fixed** across versions. Never write production application parsers relying on exact line positions in `sh.status()` output.

### 16.3. listShards command

~~~javascript
const result = db.getSiblingDB("admin").runCommand({
  listShards: 1
});

if (result.ok !== 1) {
  throw new Error(tojson(result));
}

printjson(
  result.shards.map(s => ({
    id: s._id,
    host: s.host,
    tags: s.tags
  }))
);
~~~

Typical output includes entries like:

~~~javascript
{
  _id: "shard01",
  host: "shard01-rs/s01a.example:27018,s01b.example:27018,..."
}
~~~

This is an **illustrative shape**, not real node names in the learner’s environment. The **host** field shows that a shard is typically a **replica set** with a set name and member addresses.

The command may require appropriate administrative/monitoring privileges. If unauthorized, request legitimate read-only privileges instead of modifying metadata yourself.

### 16.4. How to see each component’s role

Combined view:

~~~text
db.hello().msg = "isdbgrid"
  -> talking to mongos

listShards.shards[].host
  -> replica sets participating as shards

sh.status()
  -> overview of routing, collections, and placement metadata
~~~

There is no simple single field in `listShards` showing where every document lives. To understand per-collection placement, inspect appropriate sharding metadata/commands rather than inferring from replica set member counts.

### 16.5. Balancer status

On supported `mongosh` versions:

~~~javascript
printjson({
  balancerEnabled: sh.getBalancerState()
});
~~~

With sufficient privileges and supported versions, you can run the status command:

~~~javascript
const result = db.getSiblingDB("admin").runCommand({
  balancerStatus: 1
});

printjson(result);
~~~

This is **observing state**, not toggling the balancer. Do not proactively run **sh.stopBalancer()**, **sh.startBalancer()**, **moveChunk**, **removeShard**, or change shard keys on a shared cluster just for practice.

### 16.6. Explain for a query run through mongos

Suppose the cluster already has **shop.orders** sharded with shard key:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

Run a read-only query plan:

~~~javascript
const orders = db.getSiblingDB("shop")
  .getCollection("orders");

const targeted = orders.find({
  tenantId: "t001",
  orderNo: "SO-001"
}).explain("queryPlanner");

const broad = orders.find({
  status: "paid"
}).explain("queryPlanner");

printjson(targeted);
printjson(broad);
~~~

**Do not run this snippet if no corresponding lab `shop.orders` collection exists**; it is an example to adapt to a collection you are authorized to query on a practice cluster.

When analyzing explain output:

- Check which shards are targeted in the plan/output.
- Check whether each shard uses **IXSCAN** or **COLLSCAN**.
- Check whether there is a cross-shard merge/sort step.
- Account for differences between query shape and real data.

Explain output may contain stages such as **SHARD_MERGE**, **SHARDING_FILTER**, or **shards** details depending on version/query engine. **Do not write rigid checks** assuming one specific stage name must appear for a query to be considered sharded.

### 16.7. Read-only does not mean all output is public

Hostnames, shard IDs, zones, and config metadata can reveal infrastructure architecture. Do not share raw outputs in public issues, open docs, or application logs without redacting sensitive details. Use least-privilege read-only access and handle configuration secrets per organizational policy.

## 17. Standalone lab: creating a small sharded collection (optional)

This section is **only for an isolated practice sharded cluster** where you are permitted to create databases, indexes, and sharded collections. Do not run on production or shared clusters. Creating collections, sharding DDL, and indexes modifies metadata/placement, so this lab is **optional**, not mandatory to understand the three roles.

### 17.1. Prerequisites

- Connected to **mongos**.
- At least one shard available, preferably multiple shards to observe routing.
- Privileges to create collections/indexes and enable sharding on a dedicated database.
- Use **mongo_sharding_lab**; do not collide with real databases.
- Do not modify config server topology, add/remove shards, or run manual data-move commands.
- **mongosh** and MongoDB version support the helpers used; if different, verify official syntax before running.

### 17.2. Create sample data

~~~javascript
(() => {
  const hello = db.hello();
  if (hello.msg !== "isdbgrid") {
    throw new Error("This example only runs when connected via mongos.");
  }

  const lab = db.getSiblingDB("mongo_sharding_lab");
  const coll = lab.getCollection("lab_orders");
  const tag = "sharding-v1";

  coll.deleteMany({ dataset: tag });

  const documents = [];
  const tenants = ["t001", "t002", "t003", "t004"];
  for (let t = 0; t < tenants.length; t++) {
    for (let n = 1; n <= 5; n++) {
      const orderNo = "SO-" + String(n).padStart(3, "0");
      documents.push({
        _id: "lab-" + tenants[t] + "-" + orderNo,
        dataset: tag,
        tenantId: tenants[t],
        orderNo: orderNo,
        status: n % 2 === 0 ? "paid" : "created",
        amount: NumberDecimal(String(100 + t * 20 + n))
      });
    }
  }

  coll.insertMany(documents);
  coll.createIndex(
    { tenantId: 1, orderNo: 1 },
    { name: "ix_lab_shard_key" }
  );

  printjson({
    total: coll.countDocuments({ dataset: tag }),
    indexes: coll.getIndexes().map(i => i.name)
  });
})();
~~~

**Expected result:** 20 orders across 4 tenants, 5 orders each. The script only deletes documents tagged for the exercise; if re-run after the collection is sharded, it still operates only on the lab documents.

### 17.3. Enable sharding on the lab collection

In **an isolated sharded cluster**, once the shard key index exists:

~~~javascript
sh.shardCollection(
  "mongo_sharding_lab.lab_orders",
  { tenantId: 1, orderNo: 1 }
);
~~~

Different versions have varying database preparation rules/commands; consult your server version’s documentation. Do not blindly run **sh.enableSharding()** with unclear arguments just to “activate” sharding; in modern MongoDB releases, sharding a collection may not require a separate enable step as in older docs.

**Important note:** a set of 20 documents is tiny, so after `shardCollection`, **all data may still reside on a single shard**. That does not mean sharding failed. MongoDB does not immediately create multiple chunks and evenly scatter 20 records simply because the cluster has multiple shards.

### 17.4. Compare targeted and broad queries

~~~javascript
const coll = db.getSiblingDB("mongo_sharding_lab")
  .getCollection("lab_orders");

print("Query with full shard key:");
printjson(
  coll.find({
    dataset: "sharding-v1",
    tenantId: "t001",
    orderNo: "SO-001"
  }).explain("queryPlanner")
);

print("Query without shard key:");
printjson(
  coll.find({
    dataset: "sharding-v1",
    status: "paid"
  }).explain("queryPlanner")
);
~~~

Purpose of this exercise:

- The first query includes equality on the shard key **{tenantId,orderNo}**, giving `mongos` grounds to route to the range holding that key.
- The second query filters only on **status**, which may require scatter-gather across relevant shards.
- Because the dataset is small and current placement may be on a single shard, **the shard count shown in explain does not yet reflect production cost differences**.

### 17.5. Do not try to “force” data onto another shard via admin commands

To observe metadata only, you can run:

~~~javascript
sh.status();
~~~

Do not run **moveChunk**, **moveRange**, **reshardCollection**, **removeShard**, **balancerStart/Stop**, or directly touch `config` collections just to make a tiny example look “balanced.” Those operations alter cluster state and should only be performed in dedicated operational or lab procedures.

### 17.6. Expected outcomes

Learners should be able to explain:

1. Why the API connects to `mongos` rather than sending CRUD directly to config servers.
2. Why `listShards` shows replica set endpoints rather than listing documents.
3. Why a query with the full shard key is easier to target.
4. Why broad queries risk being sent to multiple shards.
5. Why 20 documents do not automatically distribute evenly after `shardCollection`.
6. Why a shard replica set with multiple `mongod` members is still only **one logical shard**.

## 18. Example architecture for a multi-tenant application

### 18.1. Context

A multi-tenant platform stores:

- **tenants**: tenant configuration and status.
- **orders**: rapidly growing orders.
- **events**: large event stream, queried by tenant and time.
- **payments**: transactions with strict audit requirements.

The application has two primary query shapes:

~~~javascript
// Q1: fetch one order by code within a tenant.
db.orders.findOne({
  tenantId: "t001",
  orderNo: "SO-1001"
});

// Q2: dashboard counting paid orders over time across all tenants.
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
~~~

Q1 aligns with a shard key containing `tenantId + orderNo` if distribution and constraints permit. Q2 may need to read across multiple shards since it is a cluster-wide report. No shard key can automatically guarantee both queries target a single shard without trade-offs.

### 18.2. Separating responsibilities by service

~~~text
                 Order API
                    |
              MongoDB Driver
                    |
          mongos-A / mongos-B
                    |
      +-------------+-------------+
      |             |             |
   Shard01        Shard02        Shard03
  (own RS)       (own RS)       (own RS)
      |             |             |
      +-------------+-------------+
            Routing metadata
                    |
                  CSRS
        (config server replica set)
~~~

**Order API** is responsible for authentication, authorization, idempotency, and business rules. **mongos** handles routing, shards **execute and store data**, and CSRS **holds the metadata map**.

Do not delegate tenant authorization checks to `mongos`. `mongos` can pick the right shard for a **client-supplied `tenantId`**, but if the API trusts an unverified `tenantId`, unauthorized data access can still occur.

### 18.3. Read/write strategy

For critical orders:

- Majority write concern per policy.
- Targeted writes where filters/shard key support it.
- Conditional updates/transactions when enforcing invariants.
- Read preferences matching needs for read-your-writes or stale-tolerant reporting.
- Monitor **p95/p99 latency**, scatter-gather rate, shard balance, and replication lag.

For dashboards:

- Cross-shard aggregations can run when truly necessary.
- Consider summary/read models if cluster-wide queries run too frequently.
- Do not try to cram the entire dashboard onto one shard just to cut fan-out if doing so makes that shard hot.

## 19. Choosing the number of mongos, shards, and replica set members

### 19.1. mongos scales with routing demand

The number of `mongos` instances depends on connection count, request/aggregation volume, failover needs, and network proximity to applications. An overloaded `mongos` can become a routing/merge bottleneck; adding `mongos` helps distribute router load.

However, if a query scatter-gathers across 50 shards and each shard lacks an index, adding `mongos` **will not reduce the total work across the 50 shards**.

### 19.2. Add shards when data/load must be split

Adding shards increases logical capacity and can help distribute load when:

- The shard key can distribute documents/workloads.
- The balancer/placement actually moves appropriate ranges.
- Query shapes allow targeted queries.
- New shards have sufficient CPU/RAM/IOPS and replication.

If one massive tenant heats up a single shard key value, adding shards may not relieve the hotspot when the shard key does not allow splitting that load.

### 19.3. Replica set members provide fault tolerance, not shard capacity

Adding a secondary to `shard01` increases replicas of `shard01`’s data and may expand read-serving options; it does not split `shard01`’s logical documents into parts the way adding `shard02` does.

Therefore, scaling decisions must distinguish:

| Goal | Change to consider |
| --- | --- |
| Router CPU/network overloaded | Add `mongos` or optimize query merges |
| Data capacity/load exceeds one shard | Add shards, review shard key/placement |
| Shard lacks redundancy | Improve that shard’s replica set |
| CSRS lost quorum | Restore config server quorum/config procedurally |
| One tenant heats up one range | Review shard key, key cardinality, query offloading |
| Queries frequently scatter-gather | Review filters/shard key and reporting model |

## 20. Important limitations and misconceptions

### 20.1. Sharding does not raise the single-document size limit

MongoDB still enforces the **16 MiB BSON document** limit for regular documents. Splitting a collection across 10 shards does not mean a single document can grow to 160 MiB. Sharding distributes **many documents**, rather than slicing one document across shards as if it were a giant document.

### 20.2. Sharding does not automatically make every query faster

For a small database, sharding can **add coordination, network, and operational overhead**. If the workload has a complex query that cannot be narrowly targeted, scatter-gather may be slower than a well-indexed query on a well-resourced replica set.

Sharding is a tool to **scale horizontally when demand and data model fit**, not a default toggle for every collection.

### 20.3. Sharding is not a backup

Replica sets inside shards tolerate certain member failures. However, accidental `deleteMany`, application bugs, or logical corruption will still replicate. Config metadata also needs an appropriate backup/restore strategy.

A disaster recovery strategy for a sharded cluster must account for **consistency between config metadata and shard data**, not just backing up one random shard.

### 20.4. Multiple shards does not mean data is copied to all shards

This is the core difference from a replica set. `shard01` stores only the portion of data routed to it; if all of `shard01` is lost, you cannot ask `shard02` to “return a full copy of `shard01`” unless a separate recovery mechanism exists.

### 20.5. One router not seeing a shard does not prove the shard was deleted

It could be a connectivity issue, permissions, metadata cache, or topology change. Investigate through commands/metrics rather than directly editing config metadata.

### 20.6. Reading from secondaries does not mean bypassing mongos

An application can connect to `mongos` with `readPreference: secondaryPreferred`. `mongos` selects eligible secondaries inside **each target shard replica set**. It does not require applications to connect directly to secondaries to “read faster.”

### 20.7. A shard key does not automatically enforce cluster-wide uniqueness

In a sharded collection, **unique indexes** have constraints around the shard key/prefix and how uniqueness is enforced across shards, depending on version and index type. Do not assume a unique index on an arbitrary field (without the shard key) guarantees cluster-wide uniqueness as in an unsharded collection.

If a business key like `orderNo` is unique only within a tenant, design **`tenantId + orderNo`**, the shard key, and the unique constraint together. Do not rely on shards automatically coordinating cluster-wide duplicate checks for arbitrary fields.

## 21. Responsibility summary table

| Responsibility | mongos | CSRS | Shard |
| --- | --- | --- | --- |
| Accept app CRUD connections | **Yes** | Not a business CRUD target | Not directly for normal sharded CRUD |
| Store user documents | No | No in traditional dedicated CSRS model | **Yes** |
| Hold chunk placement metadata | Caches for routing | **Authoritative cluster metadata** | Holds version/info needed for execution |
| Select shard to handle request | **Yes** | Provides routing metadata | Receives routed requests |
| Execute index scans/CRUD on documents | Distributes/merges results | Does not execute for shards | **Yes** |
| Shard replica set elections | No | No | **Yes, within shard RS** |
| CSRS replica set elections | No | **Yes** | No |
| Balancing/migration | Routes and joins related coordination steps | Metadata and coordinator/balancer mechanism | Donor/recipient transfer data |
| Majority write of a document | Forwards/coordinates acknowledgment | Does not replace shard RS | **Shard RS members** |
| Scale query routing | Add routers | Not its primary purpose | Not directly |
| Scale data capacity | No | Not a data store in dedicated model | Add shards/distribute data |

## 22. Common misconceptions

| Misconception | Why it is wrong | Correct mindset |
| --- | --- | --- |
| `mongos` holds all documents | `mongos` is a query router | Data resides on shards |
| Config servers store every Order for `mongos` to query | CSRS holds metadata | `mongos` queries shards to read Orders |
| Every secondary is a shard | A secondary is a replica within the same replica set | A shard is a distinct logical data unit |
| Three shards means every document has three copies | Sharding splits data; it does not replicate across shards | Each shard RS handles replicas of its own slice |
| Having a shard key means every query targets one shard | Filters may lack shard key fields or ranges may span shards | Evaluate targeting by query shape and placement |
| Just adding a `status` index avoids scatter-gather on `status` queries | Per-shard indexes differ from shard-key routing | Consider shard key and indexes together |
| Adding `mongos` automatically balances data | `mongos` is not a storage balancer | CSRS/placement + donor/recipient shards handle it |
| The balancer equalizes CPU across all shards | The balancer primarily manages placement | Measure workloads and hot keys separately |
| One config server failing stops all CRUD immediately | Impact depends on quorum, cache, metadata needs | Understand CSRS failover and operation conditions |
| CSRS is unimportant because `mongos` has a cache | Cache can go stale and cannot replace metadata source | CSRS needs proper HA/quorum |
| Can query `shard01` directly to get the whole collection | `shard01` holds only a subset | Application CRUD goes through `mongos` |
| Seeing a document on two shards during migration means business duplicate | Temporary/orphan data exists per protocol | Rely on routing metadata and queries via `mongos` |
| Adding a shard immediately spreads 20 documents evenly | Small datasets may live in a single chunk/shard | Check thresholds and actual placement |
| Database primary shard is the primary `mongod` | Different concepts: placement vs. election | Distinguish database primary shard vs. shard RS primary |
| Config metadata is just a cache and can be hand-edited | Has consistency/versioning/ownership invariants | Only use supported sharding commands |
| Sharding makes multi-document operations transactional | Independent writes still have separate scopes | Use transactions when truly required |
| Shard keys make any field globally unique | Unique indexes have sharding constraints | Design key and constraints together |

## 23. Hands-on and systems-thinking exercises

### Exercise 1 — Draw the architecture

A cluster has two `mongos` routers, a three-member CSRS, and three shards; each shard is a three-member replica set. Draw the diagram and label **router**, **metadata**, and **data** roles accurately. How many independent replica sets exist in total? Does a `mongos` count as a member of a shard RS?

### Exercise 2 — Investigate a query missing Order context

The application searches for **orderNo = SO-1001** without supplying `tenantId`. The shard key is **{tenantId:1,orderNo:1}**. How many shards might the query need to visit? Why does adding an `{orderNo:1}` index on each shard not guarantee single-shard targeting?

### Exercise 3 — Reading with the full shard key

Suppose the shard key is **{tenantId:1,orderNo:1}**. Trace the path of **find({tenantId:"t001",orderNo:"SO-1001"})** from the API through `mongos`, metadata, and the shard. What is each component responsible for?

### Exercise 4 — Scatter-gather and merge

A pipeline counts **paid** orders across all tenants without filtering on the shard key. Why can it touch multiple shards? What merging work must `mongos`/the cluster perform, and when should you consider a separate read model?

### Exercise 5 — Distinguish shard RS and CSRS

`shard01-primary` fails while the CSRS stays healthy. Explain which replica set runs an election, which operations are impacted, and why other shards do not necessarily elect new primaries.

### Exercise 6 — mongos failure

The API is using `mongos A`, and `A` dies mid-aggregation. Is data on the shards lost? Is the current request guaranteed to finish? What must the application configure to continue via `mongos B`?

### Exercise 7 — CSRS loses quorum

A three-member CSRS loses two members; shard replica sets remain healthy. Which metadata operations risk being blocked? Does every CRUD operation definitely stop immediately? Explain the role of metadata caching and refresh cases.

### Exercise 8 — Arbiters and data

A shard replica set has a primary, a secondary, and an arbiter. Does the arbiter hold shard documents? What does it contribute to elections, and why can’t it be counted as a data-bearing copy when analyzing majority write capacity?

### Exercise 9 — Migration

A chunk moves from `shard01` to `shard02`. Label the roles **donor**, **recipient**, **CSRS/coordinator**, and **mongos**. Why can `mongos` temporarily hold stale routing metadata and need a refresh? Should a user connect directly to the donor to search for a document after migration?

### Exercise 10 — Choosing a shard key

Compare three candidates for `orders`:

1. **{status:1}**
2. **{tenantId:1,orderNo:1}**
3. **{tenantId:"hashed"}**

Given a workload consisting of fetching an order by `tenant+orderNo`, listing all orders for one tenant, and reporting `paid` orders system-wide, analyze cardinality, targeting, locality, large tenants, and hot shards.

### Exercise 11 — Shard key prefix

A query filters only on `tenantId`, while the shard key is `{tenantId:1,orderNo:1}`. Does it always target a single shard? If a tenant spans multiple chunks on different shards, what will `mongos` do?

### Exercise 12 — Safe inspection

Connect to a lab sharded cluster with `mongosh`, run **db.hello()**, **sh.status()**, and **listShards**. Point out the evidence that you are talking to `mongos` and identify the number of shard replica sets. Why must you not edit the `config` database to “test routing”?

### Exercise 13 — Explain

On a lab sharded collection with an appropriate shard key, compare the explain output of a query with **full shard key equality** against a query filtering only on a non-shard-key field. Read the targeted shards, `IXSCAN`/`COLLSCAN`, and merge step; do not assume fixed stage names across versions.

### Exercise 14 — Small collection after sharding

You create 20 Orders and run `sh.shardCollection`, yet `sh.status` shows all data still on one shard. Is this necessarily a bug? Explain the roles of chunk size, data distribution, and balancer behavior; why should you not force `moveChunk` on a shared cluster?

### Exercise 15 — Scaling routers vs. scaling data

A cluster has 50 `mongos` instances, yet one shard is at 95% CPU while another is at 20%. Will adding more `mongos` resolve the hot shard? Propose an investigation plan covering query patterns, shard key, data placement, indexes, and workloads.

### Exercise 16 — Global uniqueness

The application requires `orderNo` to be unique **within a tenant**, while two different tenants can use the same `SO-001` code. Which shard key and unique index would you choose? Why shouldn’t you assume a unique index on `orderNo` alone will be enforced cluster-wide in every sharded configuration?

### Exercise 17 — Read preference

The application connects to `mongos` with `readPreference: secondaryPreferred`. A query targets `shard01` and `shard02`. Who picks the secondary node inside each shard? If `shard02`’s secondary is lagging with stale data, how does that affect report results? Explain how to use read concern/sessions when a consistent point-in-time view is required.

### Exercise 18 — Cross-shard invariant

Transfer 500 units between two Wallets with different shard keys: wallet A on `shard01`, wallet B on `shard02`. Do two independent `updateOne` calls automatically become all-or-nothing just because both are sent through `mongos`? Propose transaction/idempotency handling and explain why you should not call a payment gateway inside a transaction callback.

### Exercise 19 — Zones and compliance

A tenant requires data residency in the EU. How can zones support placement? What obligations must still be handled by the application and operational processes (tenant authorization, backups, encryption, migration verification)?

### Exercise 20 — Role-based incident analysis

Three separate incidents occur: (a) `mongos A` crashes; (b) CSRS loses majority; (c) all of `shard02` loses connectivity. For each incident, state:

- Which application-data-bearing components risk becoming inaccessible?
- Which operations can continue?
- Which metadata operations are impacted?
- How should clients and drivers retry?
- Which monitoring signals must be checked before changing infrastructure?

### Exercise 21 — Operational design

Propose a dashboard covering: **mongos request rate**, **routing targets per query**, **shard CPU/IOPS**, **replication lag**, **balancer/migration activity**, **config server health**, and **scatter-gather percentage**. Explain why measuring only total cluster QPS is insufficient.

### Exercise 22 — Connecting to the right place

A developer uses a direct URI to **shard01-primary** to run `countDocuments` on the sharded `orders` collection and gets a smaller count than the dashboard. Explain the cause, the risks of direct shard access, and the fix by connecting to `mongos`.

## 24. MongoDB references

- MongoDB Manual — [Sharding](https://www.mongodb.com/docs/manual/sharding/).
- MongoDB Manual — [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/).
- MongoDB Manual — [mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/).
- MongoDB Manual — [Config Servers](https://www.mongodb.com/docs/manual/core/sharded-cluster-config-servers/).
- MongoDB Manual — [Shards](https://www.mongodb.com/docs/manual/core/sharded-cluster-shards/).
- MongoDB Manual — [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/).
- MongoDB Manual — [Targeted Operations versus Broadcast Operations](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/).
- MongoDB Manual — [Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/).
- MongoDB Manual — [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/).
- MongoDB Manual — [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/).
- MongoDB Manual — [listShards](https://www.mongodb.com/docs/manual/reference/command/listShards/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Distributed Transactions](https://www.mongodb.com/docs/manual/core/transactions-sharded-clusters/).

**Conclusion:** In a MongoDB sharded cluster, **mongos is the entry point and router**, the **config server replica set holds the cluster’s metadata map**, and **shards store and process user data**. Each shard typically has its own replica set for fault tolerance; that is distinct from partitioning a collection by shard key. A query containing full shard key information can be narrowly targeted, while queries lacking sufficient predicates often must **scatter-gather**. The balancer and chunk migrations change **placement**, so `mongos` must maintain accurate routing metadata. Good design starts from **query patterns, shard keys, indexes, topology, and failure models**, not server count; clearly understanding these three roles is the foundation for scaling MongoDB while controlling latency, consistency, and resilience.
