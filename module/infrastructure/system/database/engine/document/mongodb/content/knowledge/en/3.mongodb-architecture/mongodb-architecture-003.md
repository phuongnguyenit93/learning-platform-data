# WiredTiger: Documents, Indexes, and Storage Organization

When an application executes `db.orders.findOne({ _id: ... })`, MongoDB does not simply open a JSON file and search for a text string. MongoDB receives the query, chooses a data access strategy, uses indexes when appropriate, and instructs the **storage engine** to read or write the corresponding records. **WiredTiger** is the default storage engine in modern MongoDB versions, taking primary responsibility for organizing records, storing indexes, managing the cache, compressing data pages, and supporting durability and crash recovery mechanisms.

Understanding how WiredTiger handles documents and indexes helps explain many real-world phenomena: why a query looking for a few documents may still read a lot of data, why adding indexes improves reads while making writes more expensive, why deleting documents does not immediately shrink data files, and why memory capacity noticeably affects query speed.

## 1. WiredTiger's Place in MongoDB Architecture

**MongoDB** is the complete database management system, whereas **WiredTiger** is a component inside `mongod` responsible for low-level data storage and access. These layers have distinct responsibilities:

| Component | Primary Responsibility |
|---|---|
| Client/driver | Sends commands, receives results, manages connections, retries per configuration |
| MongoDB query layer | Parses queries, selects query plans, executes filters, sorts, aggregations, and database-level operations |
| Collection/index catalog | Manages metadata for collections, indexes, options, and internal identifiers |
| WiredTiger storage engine | Organizes record stores and indexes in storage structures, cache, pages, compression, concurrency, checkpoints, and journal |
| Operating system, filesystem, storage device | Allocates files and data blocks, filesystem cache, I/O, and physical durability of write operations |

High-level flow:

```text
          Application / MongoDB Driver
                      |
                      v
            mongod: query layer
                      |
           Query planner / executor
                      |
            +---------+---------+
            |                   |
            v                   v
      Collection data        Index access
       (record store)       (index B-tree)
            |                   |
            +---------+---------+
                      v
                WiredTiger
             Cache / Pages / I/O
                      |
                      v
       Data and index files on disk
```

This is a **conceptual diagram**. The query planner does not necessarily read the collection before reading the index: for an index-backed query, the typical flow is locating keys in the index, obtaining record identifiers, and reading only the necessary documents; some queries can be answered entirely from the index.

**Distinguishing three terms:**

- **Document** is the logical data unit seen by applications through the MongoDB API. A document can nest objects, arrays, and has `_id`.
- **Record** is the storage representation unit corresponding to a document in the collection record store; MongoDB/WiredTiger uses an internal record identifier (`RecordId`) when linking data with indexes.
- **Page** is the internal organizational unit inside WiredTiger's storage trees, containing multiple keys/values and metadata. A page is not synonymous with a document; one page may hold data related to multiple documents, depending on size and layout.

## 2. BSON Documents: Logical Layer and Storage Representation

MongoDB displays data using JSON-like syntax, but the canonical representation of a document is **BSON (Binary JSON)**. BSON supports types that plain JSON cannot directly express, such as `ObjectId`, `Date`, `Decimal128`, binary data, and multiple numeric types.

Example in `mongosh`:

```javascript
db.orders.insertOne({
  _id: ObjectId("65a12f010000000000000001"),
  customerId: "CUS-001",
  status: "PAID",
  createdAt: ISODate("2026-03-15T10:30:00Z"),
  amount: NumberDecimal("125000.50"),
  shipping: {
    city: "Hanoi",
    method: "EXPRESS"
  },
  items: [
    { sku: "BK-01", quantity: 2, unitPrice: NumberDecimal("50000.00") },
    { sku: "PN-02", quantity: 1, unitPrice: NumberDecimal("25000.50") }
  ]
});
```

At the API level, the data is **one document** even with multiple nested objects and array elements. At the storage engine level, WiredTiger stores records in an internal key–value structure and places them into pages of a storage tree. You can picture the collection record store as a mapping:

```text
RecordId (internal key)  --->  BSON document (value)
```

`RecordId` is an internal implementation detail, **not the application's `_id`**. `_id` is a field inside the document and usually has an automatic unique index; a record can be located by `RecordId` after MongoDB traverses an index. Therefore, do not treat `_id` as proof that all documents in a collection are always physically ordered by `_id`.

In a standard collection, physical order on disk is not a guaranteed contract for applications. If you want a stable result order, you must specify `sort()`. A **clustered collection** is a special mechanism that organizes data by a clustered key; do not use this exception to generalize the default organization of all collections.

### 2.1. Document Size and Cost

Each BSON document has a **16 MiB** size limit. Embedding objects and arrays is convenient for reading a single business unit together, but has three consequences:

1. Large documents force queries to transfer and process more bytes if appropriate projections are not used.
2. Unbounded array growth can bloat documents and cause update contention on a single record.
3. When a document changes size, the storage engine may need to adjust page representation and rewrite data regions; do not assume updates always modify just a few bytes in place.

A document embedding a list of five shipping addresses can be reasonable; a document embedding millions of events from a single device is usually unreasonable. MongoDB offers patterns like referencing, bucketing, or time-series collections to handle different data shapes.

## 3. On-Disk Data Organization: B-Trees and WiredTiger Files

WiredTiger organizes many data structures using variants of **B-trees**. Pages inside the tree help locate a range of keys without reading every record from start to finish.

```text
                      Root page
                    /           \
                   /             \
          Internal page       Internal page
          /     |    \         /     |    \
         v      v     v       v      v     v
       Leaf   Leaf   Leaf   Leaf   Leaf   Leaf
       page   page   page   page   page   page
         |      |      |      |      |      |
       Key/value entries (records or index keys)
```

Internal pages store routing information to child pages; leaf pages hold data entries or index entries. When searching for a key, the system traverses the tree levels to reach the right region. Pages are kept in cache when needed; unavailable pages may need to be read from disk. Depending on the operation, WiredTiger can create updated versions in memory and write processed pages to disk at appropriate times.

**The B-tree here is an internal storage engine structure**, not a promise about tree depth, fixed page size, or `find()` scan order. Details can change across versions, compression methods, and configurations.

### 3.1. Collections and Indexes Typically Have Separate Storage Structures

A MongoDB database can have many collections; a collection can have many indexes. With typical WiredTiger configurations, collection data and each index are stored in files named like:

```text
<dbPath>/
  WiredTiger.wt
  WiredTiger.turtle
  collection-<internal-id>.wt
  index-<internal-id>.wt
  index-<another-id>.wt
  journal/
    WiredTigerLog.<number>
  ...
```

The diagram above is **illustrative only**, not a mandatory file list for every version or configuration. MongoDB also has separate catalog, metadata, and state files; file locations may vary when using other path options or storage management mechanisms. Nor is `WiredTiger.wt` a single monolithic file containing every JSON document.

Names like `collection-...` or `index-...` use internal identifiers rather than directly using names like `orders` or `customers`. MongoDB manages the mapping from logical collections/indexes to storage structures. **Do not manually edit `.wt` files** to modify documents or indexes: valid operations must go through the MongoDB protocol and supported backup/restore procedures.

### 3.2. Deleted Data May Still Occupy File Space

When deleting documents, do not expect `.wt` file sizes on the filesystem to shrink immediately. WiredTiger may retain free space to reuse for subsequent writes. Metrics such as **logical data size**, **allocated storage size**, **free/reusable space**, and actual filesystem usage measure different aspects.

If you need to reclaim space for the operating system, you must evaluate `compact`, resync, or rebuild approaches suited to your version, workload, replication setup, and environment; do not treat `deleteMany()` as an immediate file-shrinking operation.

## 4. What Indexes Store and Why They Speed Up Queries

An index is a structure that helps MongoDB locate documents by query keys without always scanning the entire collection. For a **standard B-tree index**, an index entry can be pictured as:

```text
Index key value  --->  RecordId of corresponding document

"CUS-001"        ->    R101
"CUS-002"        ->    R208
"CUS-003"        ->    R315
```

This illustration omits key encoding details, ordering, uniqueness, and internal implementation details. Indexes are maintained **separately from the collection record store**. If a document modifies an indexed field, MongoDB must maintain the corresponding indexes alongside writing the document.

Every standard collection has a unique index on `_id` created by MongoDB by default. Applications can create additional indexes for specific queries:

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find(
  { customerId: "CUS-001" },
  { status: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(10);
```

With the `{ customerId: 1, createdAt: -1 }` index, MongoDB can jump to the `customerId = "CUS-001"` region and read in descending `createdAt` order. This is typically more efficient than scanning all orders, filtering, and then sorting, especially when the dataset is large and the query is selective. However, the query planner is the component that decides whether to use that index.

### 4.1. Collection Scan, Index Scan, and Document Fetch

Suppose a collection has millions of orders, but only a few dozen belong to a single customer:

```text
Without an index:
  COLLECTION SCAN -> read/inspect many records -> filter -> sort -> result

With a suitable index:
  INDEX SCAN -> obtain matching RecordIds -> FETCH documents -> result

Covered by index:
  INDEX SCAN -> obtain all returned fields from index -> result
```

In `explain()`, common stage names include `COLLSCAN`, `IXSCAN`, and `FETCH`; exact representations depend on the query engine and version. **An index scan does not mean every byte of the document is already inside the index.** If the projection requests `status` while the index only contains `customerId` and `createdAt`, MongoDB normally needs to fetch the document to retrieve `status`.

### 4.2. Covered Query: When Reading Only the Index Suffices

A query may request only fields already present in an index:

```javascript
db.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });

db.orders.find(
  { customerId: "CUS-001", status: "PAID" },
  { _id: 0, customerId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1 });
```

The index contains the filter, sort, and projection fields; `_id: 0` avoids requesting `_id`, which is not in the newly created index. Under suitable conditions, the query planner can return data directly from the index without fetching documents. **Coverability** depends on index type, query predicates, arrays/multikey behavior, projection syntax, and the actual plan; you must check `explain()` rather than assuming that listing matching field names guarantees a covered query.

### 4.3. Compound Indexes and Key Order

With the compound index `{ customerId: 1, status: 1, createdAt: -1 }`, physical key ordering is first by `customerId`, then `status`, then `createdAt`. Thus, field order significantly affects which queries can be served efficiently.

A useful design guideline is **Equality → Sort → Range (ESR)**: prioritize fields compared for equality, followed by fields used for sorting, then fields used for range predicates. This is a heuristic for proposing initial indexes, not a substitute for real measurement; sometimes a highly selective range should appear earlier.

Example:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});

db.orders.find({
  customerId: "CUS-001",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-01-01T00:00:00Z") }
}).sort({ createdAt: -1 });
```

**Prefix rule:** a compound index can support queries based on a leading prefix of the keys, whereas efficiency when filtering solely on a trailing field in the index may be low. For instance, an index starting with `customerId` is usually not the first choice for a report filtering only by `status` across all customers.

### 4.4. Multikey Indexes for Arrays

Because BSON documents support arrays, MongoDB can use a **multikey index** to query individual values within an array:

```javascript
db.orders.createIndex({ "items.sku": 1 });

db.orders.find({ "items.sku": "BK-01" });
```

With an array of objects, the index can create key entries associated with each `sku` in `items`. One document remains one logical document; the index simply adds entries to support lookups. Consequently, large arrays can bloat indexes, increase update costs, and introduce stricter compound multikey rules (such as restrictions when multiple indexed fields are arrays). When needing to match multiple conditions on **the same array element**, consider `$elemMatch` instead of mechanically chaining independent conditions.

### 4.5. Other Index Types

MongoDB also supports specialized index types and query methods such as TTL, partial, sparse, unique, text, geospatial, hashed, and additional options depending on version/edition. Not every type has identical query semantics to a standard single-field B-tree index. In particular, a **TTL index** relies on a background deletion thread and does not guarantee documents disappear at the exact millisecond of expiration; a **unique index** enforces uniqueness at the database level for the indexed key combination.

## 5. Cache: What Happens Between RAM and Disk?

WiredTiger maintains an **internal cache** holding actively used data and index pages. Simultaneously, the operating system may maintain a **filesystem cache** for data read/written through the filesystem. These two cache layers serve different purposes and are managed differently; do not sum their capacities as though both were completely free memory or directly controlled by the application.

```text
Query / Update
      |
      v
WiredTiger cache (active pages)
      |                 ^
      | cache miss      | page load / decompression
      v                 |
Filesystem cache / I/O layer
      |                 ^
      v                 |
Compressed on-disk pages (.wt)
```

When a query uses an index:

1. MongoDB needs the index pages to locate the key range.
2. If documents must be fetched, it additionally needs the collection pages.
3. Pages already in the WiredTiger cache avoid part of the I/O and decompression cost.
4. On a cache miss, the system must fetch data from lower layers; depending on filesystem cache state, accessing the physical storage device may be required.

The **working set** is the subset of data and indexes frequently accessed during a practical time window. When the working set fits in memory and query patterns are stable, read performance is generally better. When the working set exceeds cache capacity, pages must be continually loaded/evicted, potentially causing heavy I/O and high latency.

### 5.1. Eviction and Dirty Pages

Newly read or recently modified pages can reside in the WiredTiger cache. A **dirty page** is a page with modifications not yet fully reflected in the corresponding durable on-disk state. WiredTiger needs an **eviction** mechanism to free cache space and manage old/infrequently used pages; this process can involve reconciliation or writing pages to the storage layer depending on state.

Heavy writes to the same data region or too many indexes create cache/I/O pressure. Therefore, a system with plenty of overall RAM can still face WiredTiger cache pressure, while a system using lots of RAM is not necessarily suffering from a memory leak.

### 5.2. Data and Index Compression

WiredTiger uses compression techniques to reduce on-disk space. Common mechanisms include:

- **Block/page compression for collections:** MongoDB commonly uses Snappy by default with WiredTiger, though options can be configured such as `zlib`, `zstd`, or uncompressed where supported.
- **Prefix compression for index keys:** keys sharing a common prefix can be represented more compactly, especially in indexes with many repeated leading key values.
- **Journal compression:** journal compression has separate options and configuration; do not assume the journal compressor matches the collection compressor.

Compression reduces disk bytes read/written, at the cost of CPU for compression/decompression. For repetitive data and slower disks, compression is usually beneficial; for already-compressed data or CPU-bound workloads, benefits vary. **Compression ratios cannot be inferred from document count alone**, as they depend on field types, repeated values, indexes, and page sizes.

## 6. Write Mechanism: From Update to Journal and Checkpoint

Suppose the application updates an order status:

```javascript
db.orders.updateOne(
  { _id: ObjectId("65a12f010000000000000001") },
  { $set: { status: "SHIPPED" } }
);
```

Conceptually, the operation locates the document (typically via the `_id` index), checks conditions, and modifies the record. If the updated field belongs to one or more indexes, the corresponding index entries must also be updated. WiredTiger manages versioning/concurrency of changes, dirty pages, recovery logs, and flushing changes to long-term storage state.

```text
Write document
     |
     +--> Modify record / index in versioned state and cache
     |
     +--> Journal / recovery log per mode and write timing
     |
     +--> Periodic checkpoint creating a recovery point on disk
     |
     +--> Replication is an independent mechanism at the MongoDB level
```

The diagram illustrates responsibilities, **not a guarantee about the exact order of every byte written**. When a client receives a success acknowledgment depends on `writeConcern`, journaling, and replication state; you cannot infer "safe from every failure" merely from a command returning success under arbitrary default settings.

### 6.1. Journal: Crash Recovery

The **journal** is a recovery log mechanism associated with written changes. It enables WiredTiger to recover eligible operations after a sudden `mongod` or host crash, based on the corresponding checkpoint state and log entries. The basic idea resembles write-ahead logging: recovery data must be durably persisted under appropriate rules before an update is considered durable.

Example write command requesting journaling:

```javascript
db.runCommand({
  update: "orders",
  updates: [{
    q: { _id: ObjectId("65a12f010000000000000001") },
    u: { $set: { status: "SHIPPED" } }
  }],
  writeConcern: { w: 1, j: true }
});
```

With `j: true`, the client requests acknowledgment tied to durable journal persistence per MongoDB/WiredTiger semantics. However, `w: 1` **does not require a majority of replicas to have received the data**. Durability requirements and node fault tolerance must be evaluated across `w`, `j`, replica sets, and backup policies; defaults may depend on configuration/version.

### 6.2. Checkpoint: Starting Point for Recovery

A **checkpoint** brings storage state to a consistent point usable for on-disk recovery. WiredTiger creates checkpoints periodically or based on events/configuration; it does not wait for all dirty pages to become clean before every client read of new data.

After a crash, the storage engine can recover from a valid checkpoint and then apply necessary logs. Thus, checkpoints and the journal **complement each other**:

| Concept | Purpose | What It Cannot Replace |
|---|---|---|
| WiredTiger checkpoint | Consistent point for storage and recovery | Standalone backups, replication, recovery if the entire disk fails |
| WiredTiger journal | Records changes for crash recovery | Historical backups, replicas on other machines |
| MongoDB replication / oplog | Replicates changes to other members and supports synchronization | Automatic backup against accidental deletion or ransomware |
| Proper backup/PITR | On-demand restoration from backups, potentially to a point in time | Query optimization or direct replacement for transactions |

Do not simply copy a few `.wt` files while `mongod` is running and treat that as a consistent backup. Use snapshot/backup mechanisms supported by MongoDB that account for the journal, metadata, and deployment architecture.

### 6.3. Concurrent Updates and Transactions

WiredTiger uses **optimistic concurrency** techniques for document data; MongoDB also enforces higher-level locking/coordination layers. Many operations on different documents can proceed concurrently. When two operations contend on a modification, MongoDB may detect a write conflict and retry in appropriate contexts or return an error for the application to handle.

**A write operation on a single document is atomic** under MongoDB's contract. If business logic requires updating multiple documents/collections together—such as creating an order + deducting inventory—consider multi-document transactions taking into account supported deployment topologies, transaction overhead, and retry handling. This is a MongoDB feature working in coordination with the storage engine, not a property of a single B-tree file.

## 7. Real-World Path of a Query and a Write

Let's place the concepts just learned into two scenarios:

### 7.1. Query by Customer and Time

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({
  customerId: "CUS-001",
  createdAt: { $gte: ISODate("2026-03-01T00:00:00Z") }
}).sort({ createdAt: -1 }).limit(20);
```

1. The query layer receives the filter, `sort`, and `limit`.
2. The planner may choose the compound index when estimated cost is better than a collection scan.
3. WiredTiger supplies the index pages containing keys in the `CUS-001` range.
4. Index entries indicate which records to fetch; if fields outside the index are needed, the engine accesses the pages containing the documents.
5. Results are decoded from BSON and returned to the driver; `limit(20)` caps the returned documents, though it does not always cap the index entries examined to exactly 20.

Latency increases when many scattered documents must be fetched from cold pages, when sorting is unsupported by an index, or when an index is insufficiently selective. Therefore, **index optimization** must examine keys scanned, documents fetched, and bytes returned.

### 7.2. Inserting an Order with Multiple Indexes

Suppose `orders` has indexes on `_id`, `{ customerId, createdAt }`, `status`, and `items.sku`. When inserting an order containing three line items:

1. MongoDB prepares the BSON record for the document.
2. The record store writes the new logical record.
3. Associated indexes must create new keys; a multikey index may generate multiple entries from the `items` array.
4. WiredTiger manages changes in cache, logs, and appropriate checkpoint/recovery mechanisms.
5. MongoDB acknowledges the client per the operation's write concern.

Adding indexes enables faster reads across multiple query patterns, **but every insert/update/delete operation must maintain them**. An index no longer used by the workload still consumes disk space, RAM, and write I/O. Hence, "more indexes always means faster" is a false conclusion.

## 8. Observing and Explaining WiredTiger Behavior

MongoDB tools help connect architecture to real data. The commands below illustrate usage in `mongosh`; available privileges, field names, and statistics may vary by version/edition.

### 8.1. Checking Existing Indexes

```javascript
db.orders.getIndexes();
```

Output shows index keys, names, uniqueness, and related options. Use this information to explain why a query can or cannot use an expected index.

### 8.2. Viewing the Query Plan and Scanned Data Volume

```javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Key metrics/stages to note:

| Metric / Stage | Question to Answer |
|---|---|
| `winningPlan` | Which query execution strategy did the planner choose? |
| `IXSCAN` | Was an appropriate index used, and which index is being scanned? |
| `COLLSCAN` | Did it have to scan the collection sequentially? |
| `FETCH` | Did it need to read full documents after traversing the index? |
| `totalKeysExamined` | How many index key entries were examined? |
| `totalDocsExamined` | How many documents were examined? |
| `nReturned` | How many documents were returned? |
| `executionTimeMillis` | Recorded execution time in stats; repeat measurements and account for environmental factors |

Cases worth investigating include `totalKeysExamined` or `totalDocsExamined` being much higher than `nReturned`, or queries requiring `COLLSCAN` and costly sorts. Do not force every query to use an index: collection scans can be reasonable for very small collections or queries returning most of the data.

### 8.3. Observing Collection and Index Size

```javascript
db.orders.stats();
db.orders.totalIndexSize();
db.orders.dataSize();
db.orders.storageSize();
```

`dataSize` reflects logical data size as tracked by MongoDB; `storageSize` relates to allocated storage space for the collection; `totalIndexSize` reflects space used by indexes. These **do not necessarily add up to the exact on-disk footprint** because of metadata, journal, reusable free space, compression, snapshots, and other overhead.

### 8.4. Observing Cache and Server Status

```javascript
const status = db.serverStatus();
status.wiredTiger?.cache;
```

In environments with privileges to view `serverStatus`, WiredTiger statistics can provide data on cache, pages, eviction, and related I/O. Do not rely on a single counter name across every version without checking the current schema. When diagnosing incidents, examine cache metrics alongside CPU, disk read/write latency, write throughput, query latency, index sizes, and checkpoint timing.

## 9. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "Each document is stored as a separate JSON file." | A BSON document is a logical record; WiredTiger stores many records within pages/data structures inside storage files. |
| "`_id` is the physical address of the record." | `_id` is an application/index key; the storage engine has internal record identifiers and can change physical layout. |
| "Indexes store a full copy of every document." | Standard B-tree indexes hold keys and record locators; only eligible queries are covered by an index. |
| "MongoDB always returns documents in insertion or `_id` order." | If you need a guaranteed stable order, use `sort()`; storage order does not guarantee default result ordering. |
| "Indexes only speed up reads with zero cost." | Indexes consume storage space and must be updated on every relevant write operation. |
| "Adding RAM to the host means all data is in the WiredTiger cache." | The cache has its own limits/policies, filesystem cache is a separate layer, and working set plus eviction govern effectiveness. |
| "Deleting documents immediately reduces file size." | Free space may be retained for reuse; reclaiming space back to the OS depends on storage mechanisms. |
| "Checkpoints, journal, replicas, and backups are all the same." | These are distinct protection layers with different goals; they cannot fully replace one another. |
| "Every `IXSCAN` query is fast." | Poorly selective indexes, scanning many keys, or fetching many documents can still be expensive. |

## 10. Design Guidelines to Leverage WiredTiger

When designing MongoDB collections, start from queries and data lifecycles before thinking about file structures:

1. **Choose document boundaries by business domain.** Embed components read/updated together in bounded numbers; reference components that grow unboundedly or have independent lifecycles.
2. **Design indexes around real queries.** List frequent filters, sorts, ranges, and projections; test compound indexes with proper key ordering and observe via `explain()`.
3. **Control index count.** Unique, TTL, multikey, and compound indexes all have costs; avoid redundant or unused indexes.
4. **Monitor the working set.** Track active data, indexes, and cache under rising load; measure disk I/O and eviction before blaming CPU or RAM shortages.
5. **Account for compression and data shapes.** BSON has field and value overhead; compression efficiency varies between repetitive data, random data, and pre-compressed data.
6. **Distinguish durability from replication.** Define `writeConcern`, journaling, backups, and recovery objectives according to the business value of the data.
7. **Re-measure after schema changes.** Any change to embedding, arrays, compound indexes, or write workloads can shift I/O, cache pressure, and execution time.

## 11. Practice Exercises

### Exercise 1: Comparing a Query Before and After Indexing

Create a test collection with many orders containing `customerId`, `createdAt`, and `status`. Execute:

```javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");

db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

Record `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. Explain why the new index can reduce documents examined and avoid an extra sort stage; if results do not change or the collection is too small, explain why the planner might not choose the index.

### Exercise 2: Covered Query

Create index `{ customerId: 1, status: 1, createdAt: -1 }`. Compare two projections: one projection containing only the fields above (excluding `_id`), and another adding `shipping.city`. Use `explain("executionStats")` to see whether the plan needs to fetch documents.

### Exercise 3: Multikey Indexes and Large Documents

Design a collection for articles that could have hundreds of thousands of comments. Explain why you should not embed them all in a single array. Propose a separate `comments` collection with fields `postId`, `createdAt`, `authorId`, and `content`, along with an index supporting fetching the 20 newest comments per post.

### Exercise 4: Deleting Data and Disk Usage

In a test environment, insert a sufficiently large dataset and observe `stats()`, `dataSize()`, `storageSize()`, and file sizes before/after deleting many documents. Explain why logical size may decrease while allocated storage space does not drop proportionally. Do not run compact or manually modify WiredTiger files in production.

### Exercise 5: Crash Recovery

Distinguish the following four questions: "Has the write reached cache?", "Has the write met journal durability?", "Have a majority of replicas acknowledged?", and "Can an order accidentally deleted yesterday be restored?". Map each question to WiredTiger cache, journal/write concern, replication, and backup/PITR; explain why each mechanism addresses only part of the requirements.

## Conclusion

MongoDB provides a **BSON document and collection** abstraction for developers; WiredTiger manages the physical representation of **record stores, indexes, and B-tree pages**, along with cache, compression, concurrency, journaling, and checkpoints. Indexes locate documents more efficiently when keys align with filters/sorts; the cache reduces disk accesses; compression reduces storage footprint; journaling and checkpoints support recovery. Each mechanism carries its own cost and guarantee scope.

Understanding the boundary between **logical documents**, **lookup indexes**, and **storage pages** helps you design data models, select indexes, and investigate MongoDB performance based on measured data rather than assumptions about `.wt` files sitting under `dbPath`.
