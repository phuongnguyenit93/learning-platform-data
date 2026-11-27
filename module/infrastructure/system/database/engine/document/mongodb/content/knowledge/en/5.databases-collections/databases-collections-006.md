# Reading Metadata, Storage Statistics, and Collection Info in MongoDB

## 1. Learning Objectives and Context

When working with MongoDB, reading data with `find()` only tells you the contents of documents. To administer databases and optimize applications, we also need to answer questions such as:

- Which databases exist on the server, and which ones can the current account see?
- Which collections, views, or specialized structures does a database contain?
- With what options was a collection created: validator, collation, capped collection, or time series?
- How many documents does a collection have, and what are its logical data size, allocated physical storage, and index sizes?
- Which fields are in an index, does it enforce unique or TTL constraints, and how much storage does it consume?
- Why does deleting many documents not immediately shrink disk usage by the same amount?

Within the **Databases and Collections** chapter of **Database Engine Document MongoDB**, this lesson focuses on **reading metadata and statistics** using `mongosh`, and then inspecting the corresponding information in MongoDB Compass. The primary operations are read-only; the beginning includes a small dataset for hands-on practice.

> **Important distinction:** Metadata describes structure and configuration; statistics describe counts and resource usage; application documents are the contents of individual records. These three categories serve different purposes.

After this lesson, you will be able to inspect a database or collection without opening individual documents, interpret storage units, compare statistics across points in time, and avoid common false conclusions.

## 2. What Is Metadata in MongoDB?

**Metadata** is information describing objects managed by MongoDB. It can include:

| Level | Example Information | How to Inspect |
|---|---|---|
| Database | Database name, collection count, object count, data and index sizes | `show dbs`, `listDatabases`, `dbStats` |
| Collection | Name, object type, creation options, validator, collation, internal UUID, time series or capped definition | `listCollections`, `db.getCollectionInfos()` |
| Index | Index name, key fields and sort direction, unique, TTL, partial filter, collation | `db.collection.getIndexes()` |
| Collection stats | Document count, logical size, allocated storage, index sizes, per-index size | `$collStats` or `collStats` command |
| Index access stats | Index access counts recorded since collection of stats began | `$indexStats` |

Key terminology:

- **Database:** container for collections and related objects.
- **Collection:** set of BSON documents, which can contain documents with differing structures.
- **View:** read-only query defined over another collection/view; normally has no separate document storage like a real collection.
- **Index:** data structure accelerating searches and sorts; carries storage and write-maintenance overhead.
- **Namespace:** fully qualified name in `database.collection` form, such as `metadata_lab.demoOrders`.
- **Collection UUID:** internal identifier of a collection that may appear in metadata; should not be used as a stable business key across drop/recreate cycles.

MongoDB differs from relational databases in that it does not require all documents in the same collection to share an identical schema. Even so, a collection still has **its own metadata** and can enforce a **validator** to control data on write.

### 2.1. Metadata Is Not Statistics

For example:

~~~javascript
db.getCollectionInfos({ name: "demoOrders" })
~~~

This returns a description of the collection, such as `name`, `type`, `options`, and certain `info` fields. It is **not** a storage-measurement command.

Conversely:

~~~javascript
db.runCommand({ collStats: "demoOrders", scale: 1024 })
~~~

This returns collection statistics, including fields such as `count`, `size`, `storageSize`, and `totalIndexSize` when supported by the server. It **does not replace** listing collection creation options.

Meanwhile:

~~~javascript
db.demoOrders.findOne()
~~~

This returns a single application document and cannot be used to infer overall collection configuration or storage usage.

### 2.2. Why Care About Access Permissions?

MongoDB enforces role-based access control. A user may only be permitted to view a single database or a subset of collections. Object listing results depend on **the permissions of the current account**, so "not appearing in the list" does not always mean the object does not exist.

Server-wide statistics or operational monitoring commands may require dedicated privileges. For practice accounts, only appropriate permissions to read the target practice database and collections are needed. If you encounter `not authorized`, verify roles with your administrator instead of guessing credentials or granting excessive privileges.

## 3. Preparing Practice Data

This lesson uses the `metadata_lab` database and the `demoOrders` collection. Open `mongosh` connected to a local MongoDB Server or a practice environment where you have access, then run in the shell:

~~~javascript
use metadata_lab

const sampleOrders = [
  {
    _id: "order-001",
    customer: "Lan",
    status: "PAID",
    amount: NumberDecimal("120.50"),
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    items: [{ sku: "BK-001", quantity: 2 }]
  },
  {
    _id: "order-002",
    customer: "Minh",
    status: "PENDING",
    amount: NumberDecimal("75.00"),
    createdAt: ISODate("2026-11-02T09:30:00Z"),
    items: [{ sku: "BK-002", quantity: 1 }]
  },
  {
    _id: "order-003",
    customer: "An",
    status: "PAID",
    amount: NumberDecimal("230.00"),
    createdAt: ISODate("2026-11-03T12:10:00Z"),
    items: [{ sku: "BK-003", quantity: 4 }]
  },
  {
    _id: "order-004",
    customer: "Ha",
    status: "CANCELLED",
    amount: NumberDecimal("42.25"),
    createdAt: ISODate("2026-11-04T07:15:00Z"),
    items: [{ sku: "BK-004", quantity: 1 }]
  },
  {
    _id: "order-005",
    customer: "Linh",
    status: "PENDING",
    amount: NumberDecimal("99.99"),
    createdAt: ISODate("2026-11-05T18:20:00Z"),
    items: [{ sku: "BK-005", quantity: 3 }]
  }
];

sampleOrders.forEach(order => {
  db.demoOrders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.demoOrders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_createdAt" }
);

db.demoOrders.countDocuments({});
~~~

If `metadata_lab` initially held no data, the expected count is **5 documents**. If the database already held other documents, the total may be higher. Using `replaceOne(..., { upsert: true })` avoids duplicate `_id` errors, though it **resets the contents of these five sample documents** when re-run.

The `demoOrders` collection has the default index on `_id` plus a compound index on `status` and `createdAt`. Re-running `createIndex` with the exact same definition and name normally does not create duplicate indexes.

To have another collection configuration example, create a collection with a validator; the snippet creates it only if absent:

~~~javascript
if (db.getCollectionInfos({ name: "validatedOrders" }).length === 0) {
  db.createCollection("validatedOrders", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["orderCode", "status"],
        properties: {
          orderCode: { bsonType: "string" },
          status: { bsonType: "string" }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}
~~~

This lesson does not need to insert documents into `validatedOrders`; the purpose is inspecting its validator metadata.

## 4. Listing and Identifying Databases

### 4.1. Quick Commands in mongosh

~~~javascript
show dbs
db.getName()
~~~

- `show dbs` lists databases visible to the account; output may include storage estimates.
- `db.getName()` shows the currently selected database, such as `metadata_lab`.

Switching context:

~~~javascript
use metadata_lab
db.getName()
~~~

The `use` command does not by itself create the database on the server. A new database may only appear in listings after a collection or data is created.

### 4.2. Using the `listDatabases` Command

You can invoke the admin command directly:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  authorizedDatabases: true
});
~~~

Options in the example:

- `listDatabases: 1` requests a list of databases.
- `nameOnly: true` returns only names and omits size statistics.
- `authorizedDatabases: true` restricts results to databases the account is authorized to view under access control.

To also retrieve size statistics from the listing command, omit `nameOnly`:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  authorizedDatabases: true
});
~~~

The response typically contains a `databases` array with `name` and potentially `sizeOnDisk` and `empty`, depending on permissions, options, and server version. These numbers reflect state at execution time; never use them as an exact full-infrastructure capacity report.

**Scope of results:** On managed services such as MongoDB Atlas, certain administrative commands are restricted. If `listDatabases` reports insufficient privileges, you can still inspect authorized databases via `db.getName()` and collection-listing commands.

### 4.3. Avoid Confusing Database Name with Namespace

Example:

~~~text
Database: metadata_lab
Collection: demoOrders
Namespace: metadata_lab.demoOrders
~~~

`metadata_lab.demoOrders` is the full namespace; the dot separates the database and collection. When applications create identically named collections across different databases, referencing only `demoOrders` can cause ambiguity in logs or monitoring scripts.

## 5. Reading the Collection and View List

### 5.1. Simple Listing Commands

~~~javascript
use metadata_lab

show collections
db.getCollectionNames()
~~~

`show collections` is convenient interactively, while `db.getCollectionNames()` returns a JavaScript array you can filter, print, or process. Depending on the database, the list can contain **views** alongside standard collections.

Example filtering names starting with `demo`:

~~~javascript
db.getCollectionNames().filter(name => name.startsWith("demo"));
~~~

Knowing only the name does not tell you whether an object is a physical collection or a view; inspect the `type` metadata.

### 5.2. Retrieving Metadata with `db.getCollectionInfos()`

~~~javascript
db.getCollectionInfos()
~~~

The result is an array of objects. Part of the metadata may look like this (actual displayed fields depend on collection type and MongoDB version):

~~~javascript
[
  {
    name: "demoOrders",
    type: "collection",
    options: {},
    info: { /* internal info */ },
    idIndex: { /* _id index definition */ }
  },
  {
    name: "validatedOrders",
    type: "collection",
    options: {
      validator: { /* JSON Schema */ },
      validationLevel: "strict",
      validationAction: "error"
    }
  }
]
~~~

Filter for a specific collection:

~~~javascript
db.getCollectionInfos({ name: "demoOrders" });
db.getCollectionInfos({ name: "validatedOrders" });
~~~

Extract only creation options:

~~~javascript
const infos = db.getCollectionInfos({ name: "validatedOrders" });
printjson(infos.length > 0 ? infos[0].options : null);
~~~

Useful fields in `options` can include:

| Option | Meaning |
|---|---|
| `validator` | Document validation expression applied on writes, typically `$jsonSchema` |
| `validationLevel` | Scope of validator enforcement, such as `strict` or `moderate` |
| `validationAction` | Action on violation, such as `error` or warning mode if configured |
| `collation` | String comparison, locale, and sorting rules |
| `capped`, `size`, `max` | Indicates a size/count-bounded collection if configured as a capped collection |
| `timeseries` | Time series collection settings, such as time field and metadata field |
| `changeStreamPreAndPostImages` | Enables storing pre/post update images when configured and supported by version |

Not every field exists on every collection. For a standard collection created with defaults, `options` may simply be an empty object.

### 5.3. Database-Level `listCollections` Command

Command-level equivalent:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: { name: "demoOrders" },
  nameOnly: false
});
~~~

The response can include `cursor.firstBatch` and metadata similar to `getCollectionInfos()`. When there are many collections, the command uses a **cursor**; `firstBatch` does not necessarily hold every entry. In practice, `db.getCollectionInfos()` is usually more convenient because the helper handles cursor iteration automatically.

To list by object type:

~~~javascript
db.getCollectionInfos({ type: "collection" });
db.getCollectionInfos({ type: "view" });
~~~

If you only want names and types without printing verbose metadata:

~~~javascript
db.getCollectionInfos().map(info => ({
  name: info.name,
  type: info.type
}));
~~~

### 5.4. Distinguishing Collections from Views

Try creating a view, if it does not yet exist and the account has permission:

~~~javascript
if (db.getCollectionInfos({ name: "paidOrdersView" }).length === 0) {
  db.createView("paidOrdersView", "demoOrders", [
    { $match: { status: "PAID" } }
  ]);
}

db.getCollectionInfos({ name: "paidOrdersView" });
db.paidOrdersView.find();
~~~

View metadata normally has `type: "view"` along with `viewOn` and `pipeline` inside `options`. A view computes query results from source data; it is not counted as an independent physical collection with its own stored documents.

**Note:** Do not call `collStats` to infer standalone storage size of a view as if it were a collection. To measure storage, identify the underlying physical collection behind the view.

## 6. Reading Database-Level Statistics with `dbStats`

### 6.1. Statistics Commands

In `mongosh`:

~~~javascript
use metadata_lab

db.runCommand({ dbStats: 1 });
~~~

You can request size values in KiB using a scale factor of `1024`:

~~~javascript
db.runCommand({
  dbStats: 1,
  scale: 1024
});
~~~

The helper syntax `db.stats()` is also common in documentation and shell work:

~~~javascript
db.stats();
~~~

These belong to database statistics commands. When you need explicit control over the `scale` factor or want to invoke the server command directly, use `db.runCommand({ dbStats: 1, scale: 1024 })`.

### 6.2. Interpreting Returned Fields

Depending on version and storage engine, the response may include:

| Field | Common Meaning | Important Note |
|---|---|---|
| `db` | Name of the database being measured | Confirm you are not reading the wrong database |
| `collections` | Number of physical collections | Not the same as the number of views |
| `views` | Number of views, if reported | Views do not store their own document data like collections |
| `objects` | Total number of documents across collections | Can differ across runs when concurrent writes/deletes occur |
| `avgObjSize` | Average document size | Check exact output to confirm meaning and scaling |
| `dataSize` | Logical size of data | Not the total bytes of MongoDB files on disk |
| `storageSize` | Storage space allocated for collection data | Affected by compression, allocation, and fragmentation |
| `indexes` | Total number of indexes | Every standard collection has a default `_id` index |
| `indexSize` | Storage size of indexes | Different from index count |
| `totalSize` | Sum of data and index storage per command definition | Not total host disk usage |
| `scaleFactor` | Active scale factor, if returned | Useful when interpreting units |
| `fsUsedSize`, `fsTotalSize` | Filesystem capacity info, if provided | Does not equal the storage size of one MongoDB database alone |

**A helpful rule of thumb:** When `scale: 1024`, **size fields supported by command scaling** are reported in **KiB (1024 bytes)**. When `scale: 1048576`, those fields are in **MiB**. Count fields such as `collections`, `objects`, and `indexes` do not turn into KiB; never assume every number in the same response shares a single unit.

Hypothetical example:

~~~text
dataSize: 2048
storageSize: 1536
indexSize: 512
scaleFactor: 1024
~~~

This can be read as roughly 2048 KiB of logical data, 1536 KiB of data storage, and 512 KiB of index storage as reported by the command. These numbers are **purely illustrative**, not the exact output you will see in the practice database.

### 6.3. Logical Size Differs from Physical Storage

MongoDB stores BSON and typically uses the WiredTiger storage engine with compression, block allocation, and free-space reuse. Consequently:

- `dataSize`/`size` reflects the **logical size** of documents within the statistics scope.
- `storageSize` reflects the size of **allocated/recorded storage space** for collection data; it can be smaller or larger than logical size depending on data and overhead.
- `indexSize`/`totalIndexSize` reflects storage used by indexes and must be considered separately.
- Data files, journal, oplog, server metadata, replica set copies, and other disk artifacts **cannot be fully inferred from `dbStats` alone**.

Do not compute an "exact cluster-wide compression ratio" simply by dividing `dataSize / storageSize` in all cases. Account for measurement purpose, storage engine, replica/sharding topology, and collection timing.

## 7. Collection Statistics with `collStats`

### 7.1. Reading Directly via Database Command

~~~javascript
use metadata_lab

db.runCommand({
  collStats: "demoOrders",
  scale: 1024
});
~~~

The `demoOrders` collection must exist in the current database. A successful result usually contains `ok: 1`. The full namespace appears in the `ns` field, e.g., `metadata_lab.demoOrders`.

Common fields:

| Field | Description | Usage |
|---|---|---|
| `ns` | Collection namespace | Verify the exact database and collection |
| `count` | Number of documents counted in stats | Do not treat as a transactionally consistent snapshot across commands |
| `size` | Logical size of documents | Estimate actual payload volume |
| `avgObjSize` | Average document size | Watch for growth from added fields or arrays |
| `storageSize` | Data storage allocation size | Track allocation and compression overhead |
| `nindexes` | Number of indexes | Cross-check against index definitions |
| `totalIndexSize` | Total storage size of indexes | Measure storage impact of adding indexes |
| `indexSizes` | Storage size per index by name | Identify resource-heavy indexes |
| `totalSize` | Sum of reported data and index storage | Distinguish from full-server disk usage |
| `wiredTiger` | Internal storage engine details, if present | Varies significantly by version and deployment |

Reference snippet for concise output:

~~~javascript
{
  const stats = db.runCommand({
    collStats: "demoOrders",
    scale: 1024
  });

  if (stats.ok !== 1) {
    printjson(stats);
  } else {
    printjson({
      namespace: stats.ns,
      documentCount: stats.count,
      logicalSizeKiB: stats.size,
      storageSizeKiB: stats.storageSize,
      indexCount: stats.nindexes,
      totalIndexKiB: stats.totalIndexSize,
      indexSizesKiB: stats.indexSizes
    });
  }
}
~~~

This is a **read-only command**. A result of `0` or very small values when only 5 documents exist does not prove the collection uses zero resources. Minimum allocations, metadata, rounding, and sample size all affect displayed values.

### 7.2. Using the `$collStats` Aggregation Stage

MongoDB also provides the `$collStats` stage to feed collection metrics into an aggregation pipeline. Example requesting document counts and storage stats in KiB:

~~~javascript
db.demoOrders.aggregate([
  {
    $collStats: {
      count: {},
      storageStats: { scale: 1024 }
    }
  },
  {
    $project: {
      _id: 0,
      ns: 1,
      host: 1,
      shard: 1,
      count: 1,
      logicalSizeKiB: "$storageStats.size",
      storageSizeKiB: "$storageStats.storageSize",
      indexesKiB: "$storageStats.totalIndexSize"
    }
  }
]);
~~~

`$collStats` must appear as the **first stage in the pipeline**. In a sharded cluster, the number of output documents and scope per document differ from a single-server deployment; do not assume there is always a single document or blindly sum all numbers as if measured on a single node.

When working through the Java driver API or monitoring pipelines that transform results via aggregation, `$collStats` is often more flexible than printing raw command responses.

### 7.3. Special Cases

- **Empty collection:** `count` can be `0` while index metadata or pre-allocated extents still exist.
- **Collection with heavy writes/deletes:** `storageSize` does not necessarily shrink in proportion to reduced document count because freed blocks may be retained for reuse.
- **Compressed collection:** logical `size` can exceed `storageSize`; on tiny datasets, overhead can cause the reverse.
- **View:** inspect the `type` metadata and identify the source collection; do not compare a view directly with a physical collection.
- **Time series:** MongoDB uses underlying bucket collections; logical and physical statistics may require different interpretation than standard collections.
- **Sharded collection:** check response scope, router output, and per-shard figures; never sum replica set copies into logical size.
- **Managed service:** certain stat fields or command privileges may be restricted; report missing permissions to your administrator.

## 8. Reading Index Definitions and Index Sizes

### 8.1. Viewing Existing Indexes

~~~javascript
db.demoOrders.getIndexes();
~~~

With the dataset from Section 3, you will see at least:

~~~javascript
[
  {
    name: "_id_",
    key: { _id: 1 }
  },
  {
    name: "idx_status_createdAt",
    key: { status: 1, createdAt: -1 }
  }
]
~~~

The snippet above omits extra fields for readability. Real output can include fields such as `v`, `unique`, `expireAfterSeconds`, `partialFilterExpression`, `collation`, and `hidden`.

Meaning of common metadata fields:

| Field | Meaning |
|---|---|
| `name` | Index name used in administration and monitoring |
| `key` | Indexed fields and sort directions `1` / `-1` |
| `unique` | Enforces key uniqueness per index rules |
| `sparse` | Indexes only a subset of documents per sparse rules |
| `partialFilterExpression` | Indexes only documents matching the filter expression |
| `expireAfterSeconds` | Sets TTL, enabling background deletion of expired documents |
| `collation` | String comparison rules for the index |
| `hidden` | Hides the index from the query planner where supported |

**Reading an index definition does not tell you whether the index is frequently used.** Nor does it tell you how many bytes the index occupies; both questions require statistical tools.

### 8.2. Per-Index Storage Statistics

~~~javascript
{
  const info = db.runCommand({
    collStats: "demoOrders",
    scale: 1024
  });

  printjson(info.indexSizes);
  print("Total index size (KiB): " + info.totalIndexSize);
}
~~~

`indexSizes` is typically an object mapping each index name to its size, such as `_id_` and `idx_status_createdAt`. These are storage sizes reported by the storage engine—not counts of indexed documents or query hits.

For a tiny collection, indexes can have relatively noticeable minimum overhead compared to data size. For large collections, evaluate index size alongside query benefits and write amplification.

### 8.3. Access Statistics with `$indexStats`

~~~javascript
db.demoOrders.aggregate([
  { $indexStats: {} }
]);
~~~

Output can include the index name, key, host, and `accesses.ops`/`accesses.since` depending on MongoDB version. This helps identify indexes that have or have not recorded usage during the tracking window.

**Do not declare an index "unused" solely because `accesses.ops = 0`.** Stats reset upon server restart, index rebuilds, or other operational events; some queries run rarely yet remain business-critical. An index can also exist to enforce a unique constraint or support periodic batch jobs.

Beyond `$indexStats`, combine sample queries with `explain("executionStats")`:

~~~javascript
db.demoOrders
  .find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Distinguishing `IXSCAN` from `COLLSCAN` clarifies the query plan. With only 5 sample documents, the query planner may pick a collection scan; that is not proof that the index definition is wrong.

## 9. Counting Documents: Exact vs. Estimated

A collection can be counted in several ways:

~~~javascript
db.demoOrders.countDocuments({});
db.demoOrders.estimatedDocumentCount();
~~~

| Method | Characteristics | When to Use |
|---|---|---|
| `countDocuments({})` | Counts documents matching a filter; use when conditional counts are needed | Pagination UIs, verifying business record counts |
| `estimatedDocumentCount()` | Uses collection metadata/storage stats to estimate total document count | Dashboards or monitoring needing fast results at large scale |
| `collStats.count` | Count reported within collection statistics | Tracking resource consumption and collection state |
| `dbStats.objects` | Total objects/documents across the database per stats | Observing database scale, not a substitute for per-collection counts |

Example counting by status:

~~~javascript
db.demoOrders.countDocuments({ status: "PAID" });
~~~

With the five sample documents, the result is `2`. `estimatedDocumentCount()` does not accept a filter to count `status: "PAID"` alone.

Even when running exact count commands, data can change between calling `countDocuments` and reading `collStats` if concurrent writes occur. Strict reconciliation requires appropriate consistency or snapshot isolation rather than assuming two commands run at different instants must match down to the exact unit.

## 10. Inspecting Metadata and Storage with MongoDB Compass

MongoDB Compass is a graphical client. UI layout varies by Compass version and MongoDB Server/Atlas configuration, but the basic workflow is:

1. Open Compass and connect to the same MongoDB Server used in `mongosh`.
2. Select the `metadata_lab` database in the navigation pane.
3. View the collection list and confirm `demoOrders` and `validatedOrders` (if created).
4. Open `demoOrders`; tabs such as **Documents**, **Aggregations**, **Schema**, and **Indexes** inspect data and indexes.
5. Open **Indexes** to cross-check `_id_` and `idx_status_createdAt` against `db.demoOrders.getIndexes()`.
6. If your Compass version shows count, size, average document size, or index size under **Collections/Collection Overview**, note the units and refresh timestamp.
7. Open `validatedOrders` to inspect configuration/validation if your Compass version displays it. When exact `validator` details are needed, run `db.getCollectionInfos({name:"validatedOrders"})` in mongosh.

Compass may display only a subset of metadata, and storage metrics do not always appear in the exact same place across versions. When measuring with a consistent `scale` or capturing repeatable reports, mongosh commands are clearer.

### 10.1. Distinguishing Tabs in Compass

| Common Area | Question It Answers | What Not to Infer |
|---|---|---|
| **Documents** | Which fields and values do documents currently hold? | Do not infer total physical collection size from a few documents |
| **Schema** | How are fields and data types distributed in the sampled documents? | Do not assume the sample represents 100% of the collection |
| **Indexes** | Which indexes exist and how are they defined? | Do not assume an index helps every query |
| **Aggregations** | What output does a pipeline produce and how does it transform data? | Not equivalent to metadata or storage stats |
| **Collection overview/metrics**, if present | Counts/sizes at the time collected | Do not assume real-time precision or identical units to mongosh |

A Compass window and a mongosh session see the same data only if connected to **the exact same host/cluster, database, and collection**. If numbers diverge, check connection targets, permissions, active filters, and refresh timing first.

## 11. Tracking Storage Growth Over Time

Some metrics only become meaningful when compared side by side across well-defined timestamps:

- From what count to what count did document volume grow?
- By how many MiB did logical data size change in a single day?
- Did index size grow because a new index was added, or because document count increased?
- Why did `storageSize` stay flat even after the application deleted data: is previously allocated space being held for reuse?
- Were stats collected on a primary, secondary, `mongos` router, or managed console? Are the scopes comparable?

### 11.1. Printing a Simple Statistics Snapshot

In `mongosh`, you can run a read-only snippet to capture a snapshot:

~~~javascript
{
  const snapshotTime = new Date();
  const databaseStats = db.runCommand({
    dbStats: 1,
    scale: 1048576
  });
  const collectionStats = db.runCommand({
    collStats: "demoOrders",
    scale: 1048576
  });

  printjson({
    collectedAt: snapshotTime,
    database: db.getName(),
    namespace: collectionStats.ns,
    dbCollections: databaseStats.collections,
    dbObjects: databaseStats.objects,
    dbLogicalMiB: databaseStats.dataSize,
    dbStorageMiB: databaseStats.storageSize,
    dbIndexMiB: databaseStats.indexSize,
    collectionCount: collectionStats.count,
    collectionLogicalMiB: collectionStats.size,
    collectionStorageMiB: collectionStats.storageSize,
    collectionIndexMiB: collectionStats.totalIndexSize
  });
}
~~~

This snippet only **prints the output**; it does not save it to a collection or file. With tiny lab datasets, MiB values can appear as very small decimals or `0` depending on server rounding and formatting.

When using snapshots for operational reporting:

1. Keep the `scale` factor and metric names identical across runs.
2. Record timestamp, server/cluster, database, collection, and server version as needed.
3. Log events that affect stats such as index builds/drops, migrations, compaction, or sharding changes.
4. Avoid summing identical data across replica set members.
5. Clearly document limitations: metadata/storage stats do not measure total OS disk usage or backup sizes.

### 11.2. Computing Storage Ratios

Suppose a collection reports:

~~~text
logical data size: 100 MiB
allocated data storage: 65 MiB
index storage: 20 MiB
~~~

You can note that total reported **allocated data storage + index storage** is about `85 MiB`. Never call this the backup file size or claim `85 MiB` of disk space will immediately become free if you drop the collection. Other storage engine and infrastructure components also exist.

If you want to compute a ratio:

\[
\text{index-to-data-storage ratio}
= \frac{\text{totalIndexSize}}{\text{storageSize}}
\]

In the example above, `20 / 65 ≈ 0.308`, or roughly **30.8%**. Compare ratios only across snapshots using the same units, scope, and collection method.

## 12. Why Does Disk Usage Not Drop Immediately After Deleting Documents?

Try deleting one document in the practice database:

~~~javascript
db.demoOrders.deleteOne({ _id: "order-005" });

db.demoOrders.countDocuments({});

db.runCommand({
  collStats: "demoOrders",
  scale: 1024
});
~~~

The document count drops by one, yet `storageSize` or filesystem usage may not shrink as expected. Common reasons:

- MongoDB can retain previously allocated space for reuse by subsequent writes.
- The storage engine organizes data into pages and compresses blocks; allocated space does not scale linearly with a single document.
- Indexes also hold their own allocated space and do not necessarily shrink immediately.
- Actual disk usage is also influenced by the journal, oplog, replica set members, backups, and managed service components.

Thus:

~~~text
Delete 1,000 documents
    ↓
Document count / logical data size generally decreases
    ↓
Allocated storage / file size may stay the same
    ↓
Free blocks can be reused for future writes
~~~

Operations like `compact`, `repairDatabase`, or rebuilding a collection carry operational costs and constraints depending on version and topology. **Do not run those maintenance commands just to test a statistics lesson.** In production, follow dedicated operational runbooks and maintenance plans.

### 12.1. If You Want to Reset the Sample Dataset

To restore `order-005` as in the initial example, simply re-run the `sampleOrders` load snippet from Section 3. That will also reset the contents of the other four sample documents. There is no need to drop the whole database to complete the lesson.

## 13. Notes on Sharding, Replication, and Managed Environments

### 13.1. Replica Sets

A replica set maintains multiple data copies for high availability. If a collection has three replicas, you cannot multiply one copy's logical size by three and call it business data volume; replication multipliers reflect infrastructure footprint under the chosen topology.

A primary and its secondaries can temporarily differ in operational stats, replication apply timing, allocated space, and maintenance state. When comparing numbers, record which node or endpoint was queried.

### 13.2. Sharded Clusters

In a sharded cluster, data can be split across multiple shards. Running stats commands via `mongos` and `$collStats` can yield metrics or document shapes with different scopes. Depending on version, fields like `shard` and `host` may appear.

Therefore:

- Confirm whether a metric is **cluster-wide aggregated** or **per-shard**.
- Do not accidentally sum aggregated totals together with per-shard entries.
- Do not multiply replica set copies to estimate logical size.
- Right after chunk migrations or resharding, stats can fluctuate depending on measurement timing.

### 13.3. MongoDB Atlas and Managed Services

Atlas provides dedicated monitoring dashboards for storage, CPU, RAM, connections, IOPS, and data growth rate per service tier and cluster. Charts may use different aggregation intervals and scopes than point-in-time `dbStats` or `collStats` results.

In some environments, stats commands require higher privileges than standard reads. Report permission errors along with the account, database/collection, and needed metric types so an administrator can grant appropriate least-privilege roles.

## 14. Common Errors and Misconceptions

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| `show dbs` does not show the database just selected with `use` | Database has no collections/data yet, or permissions are insufficient | Confirm data was written; verify permissions |
| `getCollectionInfos()` returns an empty array | Typo, wrong database, object does not exist, or restricted permissions | Run `db.getName()`, `show collections`, verify exact name |
| `collStats` says namespace does not exist | Collection has not been created or a different database is selected | Check `db.getCollectionInfos({name:"..."})` |
| `not authorized` when calling `dbStats` / `listCollections` | Role lacks metadata or statistics privileges | Use an account with appropriate privileges or ask an administrator |
| `indexSize` differs from `totalIndexSize` | One comes from database-level stats and the other from collection-level stats | Compare within the same scope and unit |
| `storageSize` is smaller than `size` | Data compression and storage layout | Do not treat as an error; distinguish logical vs. physical |
| Deleting data does not shrink `storageSize` | Storage engine keeps allocated blocks for reuse | Monitor across periods; do not infer reclaimed disk from document counts |
| Count in Compass differs from `countDocuments` | Estimated display, caching, active filters, or timing differences | Refresh, verify filter query, and confirm scope |
| Missing `wiredTiger` or secondary fields | Different storage engine, server version, or permissions | Rely only on fields actually present in output |
| `getIndexes()` shows many indexes yet `$indexStats` shows few hits | Index serves rare workloads, hasn't been hit yet, or stats were reset | Observe longer and combine with `explain`/query workloads |
| A view is treated like a storage collection | Forgot to check `type: "view"` | Use `getCollectionInfos` and inspect the source collection |
| Total size across nodes exceeds logical data | Replication/sharding copies and storage overhead | Distinguish replicated physical storage from logical collection size |

## 15. Comprehensive Hands-On Lab

Run sequentially inside `metadata_lab`:

1. Use `db.getName()` to confirm the selected database; use `show dbs` and `listDatabases` to identify visible databases.
2. List `show collections` and `db.getCollectionNames()`, then use `db.getCollectionInfos()` to distinguish regular collections, validated collections, and views (if created).
3. Extract `options` for `validatedOrders`. Explain `validator`, `validationLevel`, and `validationAction`.
4. Run `dbStats` with `scale: 1024`; record `collections`, `objects`, `dataSize`, `storageSize`, and `indexSize`.
5. Run `collStats` on `demoOrders`; record `count`, `size`, `storageSize`, `nindexes`, and `totalIndexSize`.
6. Call `db.demoOrders.getIndexes()`, distinguishing the default `_id_` index from the compound `idx_status_createdAt` index.
7. Run `$indexStats`; explain why `accesses.ops = 0` alone is not enough to justify dropping an index.
8. Compare `countDocuments({})` and `estimatedDocumentCount()`; state the meaning and limitations of each.
9. Open Compass, inspect `demoOrders` and its **Indexes** list, and cross-check against mongosh.
10. Delete one sample document with `deleteOne`, re-measure count and `storageSize`, and explain why the two numbers do not drop in equal proportion.

Quick reference commands:

~~~javascript
use metadata_lab

db.getName();
db.getCollectionNames();

db.getCollectionInfos({ name: "demoOrders" });
db.getCollectionInfos({ name: "validatedOrders" });

db.runCommand({ dbStats: 1, scale: 1024 });
db.runCommand({ collStats: "demoOrders", scale: 1024 });

db.demoOrders.getIndexes();
db.demoOrders.aggregate([{ $indexStats: {} }]);

db.demoOrders.countDocuments({});
db.demoOrders.estimatedDocumentCount();
~~~

### Comprehension Check Questions

**Question 1.** How do `db.getCollectionInfos({name:"demoOrders"})` and `db.runCommand({collStats:"demoOrders"})` differ?

*Answer:* The first reads object metadata and configuration options; the second reads collection statistics for counts, storage sizes, and indexes.

**Question 2.** Does `dataSize = 100 MiB` and `storageSize = 60 MiB` mean 40 MiB of data was lost?

*Answer:* No. The two metrics measure different things: logical document size versus allocated/recorded storage space, which is affected by compression and overhead.

**Question 3.** Can you sum primary and secondary storage to determine the logical size of a collection?

*Answer:* No. Replica nodes store redundant copies of the data; when computing logical business size, never count replicas as independent data.

**Question 4.** Can `estimatedDocumentCount()` accurately count documents with `status: "PAID"`?

*Answer:* No. That method does not accept a filter for conditional counting. Use `countDocuments({status:"PAID"})` or an appropriate aggregation.

**Question 5.** Why is `show collections` insufficient to tell whether an object has its own physical storage?

*Answer:* The name list can include views. Check `type` in metadata; views do not maintain their own stored document set like regular collections.

## 16. Practical Lessons for Inspecting Database Info in Projects

- **Verify context:** Check host/cluster, `db.getName()`, namespace, and permissions before drawing conclusions from stats.
- **Right tool for the right question:** `getCollectionInfos` reads options; `getIndexes` reads index definitions; `dbStats`/`collStats` read storage metrics; `countDocuments` counts with filters.
- **Keep units consistent:** Always state bytes, KiB, or MiB; `1024` bytes = `1 KiB` and `1,048,576` bytes = `1 MiB`.
- **Separate logical from physical sizes:** BSON data, indexes, allocated storage, and total host disk usage are distinct measurements.
- **Be careful with point-in-time snapshots:** Outputs depend on timing, privileges, server version, storage engine, and topology.
- **Do not poke storage "just to test":** This lesson only reads and interprets; compaction, repair, or drops require dedicated operational procedures.
- **Pair metrics with workloads:** Large index sizes or low hit counters do not prove an index is unnecessary; inspect actual queries and business requirements.

Once you understand metadata structure and what each statistical field represents, you can evaluate MongoDB databases systematically: which collections exist, how they are configured, how data and indexes consume resources, and what caveats apply when comparing figures.
