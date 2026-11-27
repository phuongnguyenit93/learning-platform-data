# Index Limitations by Collection Type, Version, and Deployment Model in MongoDB

MongoDB provides many index types serving different needs: standard B-tree indexes, **TTL**, **text**, **geospatial (2d/2dsphere)**, **hashed**, **wildcard**, **multikey**, **partial**, **unique**, **clustered indexes**, as well as specialized search index systems like **MongoDB Search** and **MongoDB Vector Search**. Not every index can be created with the same syntax, on every collection type, in every version, or under every deployment model.

For example, `createIndex({ location: "2dsphere" })` is valid on a normal collection, yet cannot serve as a shard key. A **standard view** can leverage indexes on its source collection, yet cannot hold its own B-tree indexes. **Time series collections** store measurements in buckets and restrict many index types. A **unique index** valid on a standalone collection may be rejected once the collection is sharded. And a **Search index** cannot be equated with a B-tree `text` index: their creation mechanisms, hosting architecture, and query capabilities differ.

This lesson provides a systematic decision framework across **three axes**:

1. **Collection type:** normal, capped, time series, clustered, standard view, or materialized result collection.
2. **Version and feature compatibility:** `mongod` binary version, **featureCompatibilityVersion (FCV)**, index version, and Stable API.
3. **Deployment model:** standalone, replica set, sharded cluster, Atlas, or self-managed Community/Enterprise with additional components.

> **Practical rule:** Never extrapolate "MongoDB supports index type X" into "every MongoDB deployment supports X". Before adopting a specialized feature, verify **version + FCV + collection type + topology + service/tier support**. Conditional examples are explicitly noted throughout this lesson.

## 1. Three Layers Determining Index Eligibility

An index can be constrained at different stages:

~~~text
Business Requirement
      |
      v
1. Collection type?
   normal / capped / time series / clustered / view
      |
      v
2. mongod version, FCV, index version, Stable API?
      |
      v
3. Deployment model and service tier?
   standalone / replica set / sharded / Atlas / self-managed
      |
      v
4. Are data types and index configuration valid?
   scalar / array / GeoJSON / Date / null / collation...
      |
      v
5. Sufficient privileges, resources, and successful build?
      |
      v
6. Can queries actually use the index?
   find()/aggregate() + explain()
~~~

**Creating an index successfully does not mean queries will automatically use it.** The query planner also weighs filters, sorts, data distribution, completeness of partial/sparse indexes, collation, and execution cost. Distinguish:

- **Feature support:** the server allows defining the index.
- **Build eligibility:** existing data, privileges, storage, and index rules permit building it.
- **Query usability:** filters, sorts, and query shapes align with the index.
- **Net benefit:** reduction in keys/documents examined outweighs index creation and maintenance overhead.

## 2. Identifying the Environment Before Writing `createIndex()`

### 2.1. Server Version Is Not `mongosh` Version

Run in `mongosh`:

~~~javascript
// Connected server version.
db.version();

// Server build information, if the account has privileges.
db.adminCommand({ buildInfo: 1 });

// Check whether the endpoint is mongod or mongos.
db.hello();
~~~

`db.version()` reflects the server, whereas the `mongosh` binary version is separate. A newer shell can connect to an older server without making the older server support newer index features.

`db.hello()` output helps identify topology. When connected to a `mongos` router on a sharded cluster, `msg: "isdbgrid"` typically appears; connecting to `mongod` reports fields like `setName`/`isWritablePrimary` if part of a replica set. Never infer cluster topology solely from hostnames or connection strings.

### 2.2. Feature Compatibility Version (FCV)

**FCV** gates the use of features and on-disk formats that would be incompatible with older releases during upgrades/downgrades. Running an 8.x binary alone does not guarantee FCV 8.x features are enabled.

On an appropriate `mongod` with privileges:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

**Note:** querying FCV via `getParameter` must be run against an appropriate `mongod`. Do not blindly run it on `mongos`, as access and management mechanics differ. In a sharded cluster, inspect cluster-wide FCV through proper operational procedures.

Never run `setFeatureCompatibilityVersion` casually just to test an index in production. Changing FCV is an administrative change impacting compatibility and downgrade paths.

### 2.3. Identifying Collection Types

~~~javascript
const labDb = db.getSiblingDB("index_limits_lab");

labDb.getCollectionInfos();
~~~

Metadata to inspect:

| Metadata | Meaning |
| --- | --- |
| `type: "collection"` | Physical collection |
| `type: "view"` | Standard view computed from an aggregation pipeline |
| `options.capped` | Capped collection with fixed size bounds |
| `options.timeseries` | Time series collection |
| `options.clusteredIndex` | Clustered index definition when supported |
| `options.viewOn` and `options.pipeline` | Source namespace and pipeline of a view |

Exact structure varies by version and collection type. Never assume every namespace returned shares identical index creation capabilities.

On a standard collection:

~~~javascript
labDb.products.getIndexes();
~~~

`getIndexes()` lists the collection's **general indexes** such as `_id_`, B-tree, TTL, or geospatial. It is **not** a reliable way to list all MongoDB Search / Vector Search indexes; Search indexes have dedicated APIs and lifecycle state.

## 3. Comparison of Index Capabilities by Collection Type

| Object Type | General / B-Tree Indexes | Key Characteristics or Limitations |
| --- | --- | --- |
| **Normal collection** | Supported, including many specialized indexes with specific rules | Typically creates default `_id_`; validate data types and index options |
| **Capped collection** | Can use appropriate standard indexes | Cannot be sharded; size-based eviction differs from TTL |
| **Standard view** | **Cannot create general indexes directly** | Uses source collection indexes; pipeline shapes determine efficiency |
| **Time series collection** | Supports secondary indexes **with restrictions** | Bucket-level indexing; limits on text/unique, multikey/geo, and versions |
| **Clustered collection** | Has a clustered index plus optional secondary indexes | Clustered index must be defined at creation; key is currently `{_id: 1}` |
| **Materialized pipeline collection** | Physical collection, so general indexes are supported | Output data does not auto-refresh when source changes |

This table is a **directional map**, not a blanket guarantee of every option combination. For time series and newer releases, consult the manual for your exact server version.

## 4. Normal Collections: Broad Support, Yet Not Unlimited

Standard collections are the foundation for most index types.

~~~javascript
const lab = db.getSiblingDB("index_limits_lab");

lab.catalog.drop();

lab.catalog.insertMany([
  {
    _id: 1,
    sku: "SKU-001",
    category: "electronics",
    title: "Wireless mouse",
    description: "Wireless mouse with quiet buttons",
    tags: ["office", "sale"],
    attributes: { color: "black", wireless: true },
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    },
    createdAt: ISODate("2026-01-01T00:00:00Z"),
    expiresAt: ISODate("2027-01-01T00:00:00Z")
  },
  {
    _id: 2,
    sku: "SKU-002",
    category: "book",
    title: "MongoDB guide",
    description: "Document database index reference",
    tags: ["reading"],
    attributes: { language: "vi", edition: 2 },
    location: {
      type: "Point",
      coordinates: [105.8342, 21.0278]
    },
    createdAt: ISODate("2026-02-01T00:00:00Z"),
    expiresAt: ISODate("2027-02-01T00:00:00Z")
  }
]);
~~~

This sample dataset is strictly for observing syntax; `expiresAt` is set in the future so TTL does not delete documents right away during practice. If your system clock is past those dates, TTL will purge them periodically; pick a farther future date to keep lab data around.

### 4.1. B-Tree, Compound, and Unique

~~~javascript
lab.catalog.createIndex(
  { category: 1, createdAt: -1 },
  { name: "ix_category_created" }
);

lab.catalog.createIndex(
  { sku: 1 },
  { name: "uq_sku", unique: true }
);
~~~

Core requirements still apply: no duplicate `sku` values may exist before building a unique index; field order matters in compound indexes; and you cannot add unlimited fields or unlimited indexes.

A **standard compound index** supports at most **32 fields**. Beyond structural limits, real performance depends on key sizes, read/write ratios, cache residency, and maintenance cost. Wider indexes are not automatically better.

### 4.2. Partial and Sparse: Result-Set Completeness

~~~javascript
lab.catalog.createIndex(
  { category: 1 },
  {
    name: "ix_electronics_only",
    partialFilterExpression: { category: "electronics" }
  }
);
~~~

A partial index holds only documents matching its filter. Queries wanting to use it safely must include predicates proving their results lie within the indexed subset. Never use `hint()` to force a partial index on a query that needs the whole collection.

**Sparse indexes** likewise skip documents missing the indexed field. This defines **which documents enter the index**, not merely a size reduction.

For explicit filtering criteria, partial indexes are usually more expressive than sparse indexes. Both carry specific restrictions depending on index and collection type.

## 5. TTL Indexes: Time-Based Auto-Deletion, Not General Compound Indexes

A **TTL index** automatically deletes documents once a date/time field expires or passes a specified age.

~~~javascript
lab.catalog.createIndex(
  { expiresAt: 1 },
  {
    name: "ix_expiration",
    expireAfterSeconds: 0
  }
);
~~~

In this example, the expiration timestamp is stored directly in `expiresAt`. MongoDB runs a background TTL monitor to purge eligible documents.

**Limitations to remember:**

1. TTL indexes are **single-field indexes**; adding `expireAfterSeconds` to a compound index does not make it a TTL index.
2. Never create a TTL index on `_id`.
3. The TTL field must hold a BSON Date or an array containing valid BSON Dates; ISO strings are not converted to Dates automatically.
4. TTL deletion is **asynchronous**; documents are not guaranteed to vanish down to the millisecond upon expiration.
5. Never alter TTL duration on an existing index by re-calling `createIndex()` with new options. Use `collMod` per your version's syntax.
6. On **time series** collections, TTL operates per bucket with version-specific variants; do not blindly apply normal-collection syntax.
7. On **capped collections**, size-based eviction differs from TTL. Check your version's limitations before designing; MongoDB 7.0 documentation notes that TTL indexes cannot be created on capped collections.

Inspecting the TTL index after creation:

~~~javascript
lab.catalog.getIndexes().filter(
  idx => idx.name === "ix_expiration"
);
~~~

To change `expireAfterSeconds` on an existing index, use `collMod` specifying the key pattern or index name per MongoDB syntax; lowering TTL can immediately make huge volumes of documents eligible for deletion. Before shortening TTL from days to seconds, estimate operational impact and clean up in batches first.

## 6. Text Indexes, MongoDB Search, and Vector Search Are Three Distinct Concepts

### 6.1. B-Tree Text Indexes on Self-Managed MongoDB

Legacy text indexes are created via `createIndex()`:

~~~javascript
lab.catalog.createIndex(
  { title: "text", description: "text" },
  { name: "text_title_description" }
);

lab.catalog.find({
  $text: { $search: "MongoDB" }
});
~~~

**Core limitations of legacy text indexes:**

- **At most one text index per collection**, though that index may span multiple text fields.
- `$text` queries cannot force a different index via `hint()`.
- Text indexes cannot optimize standard `sort()` operations.
- Compound text indexes have strict key-placement rules; if scalar keys precede the text key, `$text` queries must normally include equality predicates on those prefix keys.
- You cannot freely combine text keys with geospatial or other special index types in the same compound text index.
- Text indexes only support **binary collation**; when a collection has a non-simple default collation, consult specific index declaration rules.
- Text indexes are not supported on **time series collections** per MongoDB documentation.

Legacy text indexes address basic full-text matching and do not match dedicated search engines. Needs such as autocomplete, fuzzy matching, rich ranking, or vector similarity require MongoDB Search or Vector Search.

### 6.2. MongoDB Search and Vector Search Indexes

MongoDB Search and MongoDB Vector Search use dedicated **search indexes**, distinct from B-tree text indexes. They are created and managed via `createSearchIndex()`, search index commands, and `$listSearchIndexes`, and queried with `$search` or `$vectorSearch` where supported.

**Availability depends on environment and version:**

- **MongoDB Atlas:** provides MongoDB Search / Vector Search depending on tier, configuration, and deployment support.
- **Self-managed MongoDB Community 8.2+:** current `db.collection.createSearchIndex()` docs list this environment as compatible, while still requiring the necessary Search components to be configured.
- **Self-managed MongoDB Enterprise 8.2+ with Kubernetes Operator:** also listed as supported under deployment conditions.
- On **older self-managed versions**, never assume Search indexes exist merely because a driver exposes a `createSearchIndex()` method.
- **Compatible views:** Search/Vector Search indexes can be created on eligible views; do not generalize that into allowing direct B-tree indexes on standard views.
- **Time series:** current documentation states MongoDB Search is not supported on time series collections.

Illustrative example **to run only on deployments supporting MongoDB Search**:

~~~javascript
// Run only on deployments with Search configured.
// Exact definitions vary by version and search engine.
db.catalog.createSearchIndex(
  "search_title",
  "search",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" }
      }
    }
  }
);

// Check status: the build may not be ready immediately.
db.catalog.aggregate([{ $listSearchIndexes: {} }]);
~~~

This example illustrates the API and is not required for labs running on older Community `mongod` releases. **Never assume a search index is ready merely because the command returned**; search index builds have an asynchronous lifecycle.

## 7. Hashed Indexes: Key Distribution Rather Than Sorting or Uniqueness

Hashed indexes store the **hash** of a field value to support equality lookups and hashed sharding:

~~~javascript
lab.catalog.createIndex(
  { sku: "hashed" },
  { name: "ix_sku_hash" }
);
~~~

**Limitations to remember:**

- **Never set `unique: true` on a hashed index.** If uniqueness is needed, add a separate appropriate B-tree unique index.
- **Hashed indexes are not multikey:** you cannot index an array field with a hashed index. In compound hashed indexes, no component may make the index multikey.
- **Not suitable for range scans or sorting by original values**, because hashing destroys original ordering.
- **Cannot cover queries** under hashed index constraints.
- Be aware of hashing rules for large numbers and floating-point values; never assume numeric hashing preserves distinctions across all numeric representations unconditionally.

In particular, a **hashed shard key** distributes data across shards, yet **never implies cluster-wide uniqueness**. Uniqueness on sharded collections must be designed around shard key and unique index rules.

## 8. Wildcard Indexes: Indexing Variable Fields, Not "Knowing Everything"

Wildcard indexes support querying non-uniform attributes across documents:

~~~javascript
lab.catalog.createIndex(
  { "attributes.$**": 1 },
  { name: "ix_attributes_wildcard" }
);

lab.catalog.find({ "attributes.color": "black" });
~~~

Ideal when `attributes` holds varied fields across documents (color, material, wattage, dimensions, etc.). However, a wildcard index **is not automatically as fast as a dedicated index** when queried fields are fixed and well known.

**Notable limitations:**

1. Wildcard indexes do not generate entries for absent paths; they are inherently sparse.
2. Wildcard indexes are **not** wildcard text indexes and do not serve `$text`.
3. Wildcard syntax cannot directly create 2d, 2dsphere, hashed, TTL, text, or unique indexes.
4. **Wildcard indexes cannot serve as shard-key indexes.**
5. A **compound wildcard index** allows **at most one wildcard term**, and remaining fields must obey compatibility rules; you cannot combine two wildcard terms arbitrarily.
6. Wildcard indexes do not handle every query against whole embedded documents/arrays—for example, exact equality on a whole nested object is not optimized the same way as scalar subpaths.
7. Covered queries via wildcard indexes have strict rules regarding **single fields**, projections, and non-array values.
8. By default `_id` is excluded from wildcard indexes; indexing `_id` with a wildcard requires explicit `wildcardProjection` configuration.

**Version note:** compound wildcard indexes arrived in MongoDB **7.0+**. Rules for ascending/descending sort directions on the wildcard term and related limits must also be checked against your server version.

Example compound wildcard on supported environments:

~~~javascript
// Use only when server/FCV permits compound wildcard indexes.
lab.catalog.createIndex(
  {
    category: 1,
    "attributes.$**": 1
  },
  { name: "ix_category_attrs" }
);
~~~

This works well when queries consistently filter by a fixed `category` alongside one dynamic attribute. Never use it blindly if your environment lacks support for the feature.

## 9. Geospatial: `2d`, `2dsphere`, and Data Format Limits

MongoDB has two main geospatial index types:

- **`2d`**: suited for planar (flat) coordinates.
- **`2dsphere`**: supports spherical geometry / GeoJSON, typically used for geographic coordinates.

`2dsphere` example:

~~~javascript
lab.catalog.createIndex(
  { location: "2dsphere" },
  { name: "ix_location_2dsphere" }
);

lab.catalog.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 5000
    }
  }
});
~~~

**Important limitations:**

- Never use a **geospatial index as a shard-key index**. A sharded collection can still have geospatial secondary indexes, while the shard key must use another index.
- **Geospatial indexes do not support covered queries** like scalar B-tree indexes.
- Indexed values must conform to **valid geometry formats**; `2dsphere` GeoJSON Points expect **[longitude, latitude]** order. Invalid coordinates can fail index builds or writes.
- `2d` does not support custom collations; if a collection has a non-simple default collation, explicitly specify simple collation for a `2d` index.
- `2dsphere` indexes are sparse: missing, null, or empty-array location fields are not indexed as valid locations.
- `$geoNear` queries on a collection with multiple geospatial indexes must specify **`key`** to select the intended index.
- **Time series** collections impose specific geospatial restrictions—for example, disallowing `$near`/`$nearSphere` query operators per current docs; check rules for `$geoNear` and keys.
- **`2dsphereIndexVersion`** changes across MongoDB releases; consider downgrade compatibility.

### 9.1. Example of a `2dsphere` Index Version Change

Starting in **MongoDB 8.3**, MongoDB documentation introduced **2dsphere index version 4** as the default for newly created indexes. If you later need to downgrade FCV below 8.3, incompatible version-4 indexes must be dropped prior to downgrading.

Do not confuse these three concepts:

| Term | Example | Role |
| --- | --- | --- |
| Binary server version | `8.3.x` | Server executable capabilities |
| FCV | `8.0` / `8.3` | Gates backward-incompatible features |
| Index-specific version | `2dsphereIndexVersion: 3/4` | Geospatial index format and rules |

Only override `2dsphereIndexVersion` when there is a clear compatibility requirement; normally use the default matching your target server.

## 10. Multikey: Array Restrictions Affect Compound Indexes and Sharding

Multikey is not an independent toggle you enable manually; MongoDB automatically marks an index as multikey when an indexed field contains an **array**.

~~~javascript
lab.catalog.createIndex(
  { tags: 1 },
  { name: "ix_tags" }
);
~~~

When building compound indexes involving arrays, observe the **limit of at most one independent array path per document in a compound multikey index**; you cannot freely index two independent parallel arrays in the same compound index.

Example requiring caution:

~~~javascript
// If both tags and relatedSkus are arrays in the same document,
// this compound multikey index violates index restrictions.
db.catalog.createIndex({
  tags: 1,
  relatedSkus: 1
});
~~~

Consequences:

- **Never use a multikey index as a shard-key index.**
- A compound index with a scalar shard-key prefix and an array field in the suffix can exist under specific rules.
- A multikey index **cannot cover** a query returning the array field itself.
- Queries using `$elemMatch` face additional restrictions regarding covered queries.
- If an index contains a hashed term, the compound index must never become multikey.
- Indexing large arrays generates many index entries and raises update costs.

When documents have multiple array fields queried together, consider restructuring the data or creating separate per-query indexes rather than trying to force an all-in-one compound index.

## 11. Time Series Collections: Bucket Indexes and Version Exceptions

Time series collections are built for continuous measurements like temperature, latency, or IoT telemetry. Data has a **`timeField`** and usually a **`metaField`** identifying the source.

Example (requires a server supporting time series):

~~~javascript
lab.createCollection("sensorReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensor",
    granularity: "minutes"
  }
});

lab.sensorReadings.insertMany([
  {
    measuredAt: ISODate("2026-01-01T10:00:00Z"),
    sensor: { id: "S-01", zone: "A" },
    temperature: 29.5
  },
  {
    measuredAt: ISODate("2026-01-01T10:01:00Z"),
    sensor: { id: "S-01", zone: "A" },
    temperature: 29.8
  }
]);
~~~

Differences from normal collections:

- Data is packed into **buckets**; secondary indexes locate matching buckets rather than storing one pure entry per measurement as in normal collections.
- MongoDB **does not create a default `_id_` index** when creating a time series collection. Never assume `hint("_id_")` is always valid.
- **Unique and text indexes are not supported** on time series collections per official documentation.
- Multikey, `2d`, and sparse have **restricted support tied to `metaField`** per the limitations docs; check your exact version for allowed configurations.
- A collection cannot be **both time series and capped**.
- Never copy normal-collection index or geospatial designs onto time series collections verbatim.

### 11.1. Version Milestones Worth Remembering

| Version | Time Series Index Changes |
| --- | --- |
| **6.0+** | Expanded secondary indexes on measurement fields beyond `timeField`/`metaField`, via bucket indexing |
| **6.3+** | MongoDB docs note a default compound index on `metaField` and `timeField` per version rules |
| **7.0+** | Added **partial TTL indexes** on `timeField` with `partialFilterExpression` referencing `metaField` |
| **8.0+** | Using `timeField` in a shard key became **deprecated** for time series |
| **8.3+** | Additional rules around `_id_` index names / hints on time series; review during upgrades |

When moving across versions, **FCV downgrade** may require dropping incompatible time series secondary indexes first. Whenever sparse/geo rules differ in your version's docs, follow the documentation for your **exact deployment version**, not just this summary table.

### 11.2. Time Series TTL Is Not Identical to Normal Collection TTL

Time series collections can specify `expireAfterSeconds` directly on the collection:

~~~javascript
// Example creating a time series collection with 7-day retention.
lab.createCollection("sensorReadings7d", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensor"
  },
  expireAfterSeconds: 7 * 24 * 60 * 60
});
~~~

MongoDB deletes time series data by **eligible buckets**, not guaranteeing an individual measurement disappears the instant its timestamp expires. When different sensors need different retention periods, MongoDB 7.0+ supports **partial TTL indexes on `timeField`, filtered by `metaField`**, per version rules.

~~~javascript
// Use only on versions supporting partial TTL for time series.
// Partial filter may reference only metaField.
lab.sensorReadings.createIndex(
  { measuredAt: 1 },
  {
    expireAfterSeconds: 3600,
    partialFilterExpression: {
      "sensor.zone": "A"
    }
  }
);
~~~

This illustrates a custom policy for zone A sensors; actual removal time depends on bucket boundaries, collection-wide retention, and the TTL monitor. If the collection already has a shorter collection-wide TTL, a longer partial TTL index will not extend retention.

### 11.3. Time Series and Sharding

MongoDB supports sharding time series collections in supported configurations, yet the **shard key cannot be arbitrary**:

- Use `metaField` or its subfields.
- Certain versions allow appending `timeField` at the end of the shard key under specific rules; however, from 8.0 onward, using `timeField` in a shard key is deprecated.
- Never put arbitrary measurement fields or `_id` into a time series shard key unless supported.
- Resharding and zone sharding also carry version-specific limits.

For IoT streams monotonically increasing in time, sharding solely by a monotonic `timeField` concentrates writes on one hot range. Favor `metaField` cardinality and shard keys matching actual write/read distribution.

## 12. Clustered Collections: The Index Is Part of Data Storage Layout

A clustered collection stores documents physically ordered by its **clustered index key**, unlike normal collections that store a separate B-tree `_id_` index.

Per the MongoDB Manual:

- Clustered collections debuted in **MongoDB 5.3**.
- The clustered index key is currently restricted to **`{ _id: 1 }`**.
- A collection can have **at most one clustered index**.
- The clustered index must be specified **at collection creation time**, not added later like a secondary index.
- You can still add **secondary indexes** to a clustered collection.
- You cannot toggle an existing normal collection into a clustered collection (or vice versa) with an option; data migration is required.
- A clustered collection **cannot also be a capped collection**.

Example (only on supported servers):

~~~javascript
lab.createCollection("clusteredEvents", {
  clusteredIndex: {
    key: { _id: 1 },
    unique: true,
    name: "clustered_id"
  }
});
~~~

MongoDB optimizes queries on the clustered key specially. Execution plans can use a **bounded collection scan** rather than displaying a traditional secondary B-tree `IXSCAN`. Therefore, never mechanically apply "no `IXSCAN` means no index used" when analyzing clustered collections.

**Do not confuse** a clustered index with a similarly named compound B-tree index, nor confuse clustered collections with time series collections (even though time series internally cluster by time buckets).

## 13. Standard Views and Materialized Views: Where Do Indexes Live?

### 13.1. Standard Views Have No Separate General Indexes

~~~javascript
lab.createView(
  "electronicsView",
  "catalog",
  [
    { $match: { category: "electronics" } },
    { $project: { sku: 1, title: 1, category: 1 } }
  ]
);

lab.electronicsView.find();
~~~

MongoDB **does not allow creating, dropping, or rebuilding general indexes directly** on a standard view. To improve performance:

1. Inspect `viewOn` and the view's defining pipeline.
2. Create indexes on the **source collection** (here `catalog`).
3. Use `explain()` to verify how the optimizer utilizes source indexes.
4. If the pipeline is heavy and read constantly, consider a materialized collection.

Example:

~~~javascript
// Index is created on the source collection, not the view.
lab.catalog.createIndex(
  { category: 1, title: 1 },
  { name: "ix_category_title" }
);
~~~

On deployments supporting Search, an exception exists for **Search/Vector Search indexes on compatible views**. Those are **search indexes**; they do not mean standard views suddenly support general B-tree indexes.

### 13.2. On-Demand Materialized Views Use Physical Collections

An aggregation using `$merge` or `$out` writes results into a **physical collection**:

~~~javascript
lab.catalog.aggregate([
  {
    $group: {
      _id: "$category",
      itemCount: { $sum: 1 }
    }
  },
  {
    $merge: {
      into: "catalogSummary",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);

lab.catalogSummary.createIndex(
  { itemCount: -1 },
  { name: "ix_summary_count" }
);
~~~

`catalogSummary` is a physical collection and can hold general indexes like any normal collection. However, its data **does not auto-sync** whenever `catalog` changes. You must implement a refresh/cleanup strategy if using it for reporting.

## 14. Capped Collections: Understand Ring Eviction Before Picking Indexes

Capped collections retain data within a fixed byte size and overwrite/evict older documents under specialized storage rules:

~~~javascript
lab.createCollection("shortLogs", {
  capped: true,
  size: 1024 * 1024
});

lab.shortLogs.createIndex(
  { service: 1, createdAt: -1 },
  { name: "ix_service_time" }
);
~~~

Capped collections can have indexes for queries as shown, yet keep in mind:

- Capped collections **cannot be sharded**.
- They are not time series collections; capped and time series cannot be combined.
- Eviction by **size limit** differs from Date-based TTL.
- Transaction and write restrictions mean capped collections are not a drop-in replacement for normal collections + TTL in all logging use cases.
- Before combining capped collections with any specialized index (especially TTL), check your server version docs; certain index types and options are forbidden.

For logs retained for a fixed time window rather than a byte cap, **normal collections + TTL** are usually much easier to reason about operationally.

## 15. Index Limitations in Sharded Clusters

Sharding spreads a collection across multiple shards. **Queries, index support, uniqueness, and index builds** must then be evaluated cluster-wide.

### 15.1. Shard Keys Require a Supporting Index

A sharded collection uses a shard key, e.g.:

~~~javascript
{ tenantId: 1 }
~~~

The supporting index can be that exact key or a compound index with the shard key as its **prefix**:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, createdAt: -1 }
~~~

On populated collections, a supporting index must exist before sharding, per version procedures. Never casually drop or hide **the sole index backing a shard key**.

### 15.2. Unique Indexes Must Have a Shard-Key Prefix

Suppose `accounts.users` is sharded by `regionId`. To make `email` unique **within each region**, use:

~~~javascript
// Apply only after sharding by regionId
// and verifying existing data has no duplicates.
db.users.createIndex(
  { regionId: 1, email: 1 },
  { unique: true }
);
~~~

This index constrains the `(regionId, email)` pair. A unique `{email: 1}` index **without the shard-key prefix** is rejected on ranged sharded collections because MongoDB cannot enforce cluster-wide uniqueness that way.

**Subtlety:** The `_id_` index follows special rules. When `_id` **is not the shard key**, `_id` uniqueness in a sharded collection may only be enforced per shard; the application must generate globally unique `_id` values.

**Hashed shard keys** do not support unique constraints on the hashed index itself.

### 15.3. Special Indexes Cannot Serve as Shard Keys

Do not use **geospatial**, **wildcard**, **text**, or **multikey** indexes directly as shard-key indexes per their restrictions. A sharded collection can still contain specialized secondary indexes **distinct from the shard key index**, provided collection type and configuration permit them.

For instance, a location-based app can shard by `regionId` while maintaining a `2dsphere` index on `location` for proximity searches. The two indexes serve separate roles.

### 15.4. Index Builds in Replica Sets and Sharded Clusters

Building indexes in a cluster involves more than a single host:

- Index builds may run across multiple members and shards holding data.
- Replica sets use **commit quorum** for index builds; quorum choices depend on version and voting member health.
- Slow nodes, low disk space, or network drops can stall or impact index builds.
- Clusters may require verifying index consistency across shards during topology changes or migrations.
- DDL operations on sharded clusters follow specific write concern and admin rules.

Never force `commitQuorum: 0` or abort an index build just to rush a deployment. Weigh availability impacts and follow runbooks.

## 16. Standalone, Replica Set, Sharded, Atlas, Community, and Enterprise

Some limits stem from **topology**, others from **edition/service**, and others from **version**. Keep these axes separate.

| Environment | Accurate Design Perspective |
| --- | --- |
| **Standalone `mongod`** | Supports many general indexes on normal collections, no sharding; Search requires compatible environment/version setup |
| **Replica set** | General index builds/replication add commit quorum and member sync constraints |
| **Sharded cluster** | Requires shard-key backing indexes, unique prefixes, and shard-level index rules |
| **MongoDB Atlas** | Offers Search/Vector Search depending on tier/config, plus managed cluster limits |
| **Self-managed Community** | General indexes built in; Search can be configured separately on supported versions, not enabled by default |
| **Self-managed Enterprise** | Supports general indexes plus enterprise/deployment features; self-managed Search has version/operator requirements |
| **Serverless/free/managed tiers** | May impose resource, config, or API limits; check exact tier capabilities rather than assuming parity with dedicated clusters |

Never treat "Search exists only on Atlas" as a timeless rule: current MongoDB docs list support on certain **self-managed deployments from 8.2+**. Conversely, never claim "every MongoDB 8.2 node creates Search indexes out of the box" without checking Search services, deployment setup, and permissions.

## 17. Version, FCV, Stable API, and Upgrades/Downgrades

### 17.1. Illustrative Version Milestones

| Milestone | Index / Collection Changes |
| --- | --- |
| **5.0** | Updated behaviors around coexisting sparse/non-sparse unique indexes with identical key patterns; see exact version docs |
| **5.1** | Added converting non-TTL single-field indexes to TTL indexes via `collMod` under documented conditions |
| **5.3** | Introduced clustered collections |
| **6.0** | Expanded secondary indexes on time series |
| **6.3** | Documented default compound index for time series meta/time |
| **7.0** | Compound wildcard indexes and partial TTL on time series; Search index management via `mongosh`/db commands on supported deployments |
| **7.1** | Improved index build error reporting and resilience per release notes |
| **8.2** | Self-managed environments listed for creating MongoDB Search/Vector Search indexes |
| **8.3** | `2dsphere` index version 4; additional index/time series constraint updates |

This is **not an exhaustive feature matrix** and never replaces patch-level release notes. Patch and minor releases can adjust behaviors, fix bugs, or introduce constraints.

### 17.2. Stable API Is Another Compatibility Layer

**Stable API V1** defines a stable contract of commands, behaviors, and options for applications. Not every `createIndexes` option belongs to Stable API V1; MongoDB docs list exceptions such as `sparse`, `storageEngine`, and `background`. Legacy text indexes also have restrictions under strict API V1.

Therefore:

- **Server binary support** for an index does not mean the command is part of Stable API V1.
- Drivers passing `apiVersion: "1"` with `apiStrict: true` will reject non-API options.
- Check both Stable API docs and driver behavior when a command works in `mongosh` yet fails from an application.

### 17.3. FCV Downgrades Can Be Blocked by Indexes

Before a version rollback, audit **index formats and features** created after upgrading. For example, `2dsphere` version 4 on MongoDB 8.3 may need to be dropped before downgrading FCV to an older unsupported level. Time series secondary indexes carry similar caveats if the target version lacks support.

Never swap binaries expecting newer indexes to downgrade themselves automatically. A downgrade plan must check:

1. Target binary version.
2. Current and target FCV.
3. Indexes built using newer features.
4. Special namespaces (clustered/time series).
5. Rebuild feasibility and backup/restore plans.
6. Maintenance windows and write latency impact.

## 18. Inspecting and Diagnosing Indexes by Type

### 18.1. Inspecting General Indexes

~~~javascript
const d = db.getSiblingDB("index_limits_lab");

d.catalog.getIndexes();

d.catalog.find(
  { category: "electronics" },
  { _id: 0, category: 1, title: 1 }
).explain("executionStats");
~~~

From `explain`, inspect:

- `winningPlan`: plan selected by the query planner.
- `IXSCAN` and `COLLSCAN`: whether a B-tree index or collection scan ran.
- `FETCH`: whether source documents had to be read after the index scan.
- `totalKeysExamined`, `totalDocsExamined`, `nReturned`: actual work performed.
- `SORT`: whether an extra in-memory sort ran outside index order.

On small collections, `COLLSCAN` is often rational; never call an index "useless" simply because explain skipped it on a few documents.

### 18.2. Inspecting Search Indexes via Their Own Mechanism

On supported deployments:

~~~javascript
// Do not use getIndexes() as the sole source of Search index info.
db.catalog.aggregate([
  { $listSearchIndexes: {} }
]);
~~~

A Search index may still be building or not yet queryable even after creation is accepted. Similarly, Search queries must be inspected via Search explain/metrics rather than looking for B-tree `IXSCAN`.

### 18.3. When an Index Build Fails

A structured diagnostic checklist:

1. **Correct namespace?** Normal collection, view, time series, or capped?
2. **Server version and FCV?** Is the feature enabled and supported in that patch?
3. **Valid index key pattern?** One wildcard term, non-array hashed field, valid `2dsphere` format?
4. **Valid options?** Are `unique`/`expireAfterSeconds`/`collation`/`partialFilterExpression` valid for this index type?
5. **Existing data?** Duplicates, malformed geometries, or arrays violating compound multikey?
6. **Topology?** Shard-key prefix, unique index rules, and routing constraints?
7. **Privileges and resources?** Create-index privileges, disk headroom, commit quorum, member health?
8. **Can queries use it?** Read `explain()`; separate build errors from planner non-selection.

Never hastily lower FCV, grant overly broad roles, or drop unrelated indexes to "make the error go away" before identifying which rule was violated.

## 19. Side-by-Side Comparison: Valid on Normal Collections, Not Automatically Valid Elsewhere

### 19.1. One Text Index on a Normal Collection

~~~javascript
const demo = db.getSiblingDB("index_limits_lab");

demo.articles.drop();
demo.articles.insertMany([
  { _id: 1, title: "MongoDB indexing", body: "Compound indexes" },
  { _id: 2, title: "MongoDB queries", body: "Text search" }
]);

demo.articles.createIndex(
  { title: "text", body: "text" },
  { name: "text_articles" }
);
~~~

This creates **one text index covering two text fields**. Creating a second text index on the same collection violates the legacy text index limit:

~~~javascript
// DO NOT RUN as a routine extra index:
// a collection may have at most one legacy text index.
demo.articles.createIndex({ body: "text" });
~~~

### 19.2. Hashed Indexes Cannot Be Unique

~~~javascript
// INVALID:
demo.articles.createIndex(
  { title: "hashed" },
  { unique: true }
);

// Valid if you only need hashed lookup, not uniqueness.
demo.articles.createIndex(
  { title: "hashed" },
  { name: "ix_title_hashed" }
);
~~~

If uniqueness is needed, add a **separate** B-tree unique index after resolving duplicates and verifying sharding rules:

~~~javascript
demo.articles.createIndex(
  { title: 1 },
  { unique: true, name: "uq_title" }
);
~~~

### 19.3. Views Have No Separate General Indexes

~~~javascript
demo.createView(
  "articleTitles",
  "articles",
  [{ $project: { title: 1 } }]
);

// INVALID: general indexes cannot be created directly on a view.
demo.articleTitles.createIndex({ title: 1 });

// VALID: create the index on the source collection instead.
demo.articles.createIndex(
  { title: 1 },
  { name: "ix_article_title" }
);
~~~

Commands marked **INVALID** are for illustration only and should be read separately; in automated lab scripts, never run them sequentially without error handling.

### 19.4. Restrictions on Time Series

~~~javascript
// This illustrates restrictions only; do not call createIndex for text/unique:
// demo.sensorReadings.createIndex({ temperature: "text" });
// demo.sensorReadings.createIndex({ "sensor.id": 1 }, { unique: true });
~~~

To index measurements or `metaField`, follow the time series documentation for your exact version. Never switch away from a time series collection solely to "force an index" if the workload genuinely needs time series semantics.

## 20. Choosing Indexes by Deployment Requirement

| Need | Common Design Direction | What to Verify |
| --- | --- | --- |
| Lookup by unique ID/code | B-tree unique / compound unique | Duplicates, shard-key prefix, collation |
| Auto-expire logs/sessions by date | TTL on normal collection | BSON Date, single-field, asynchronous background timing |
| Keyword document search | Legacy text or MongoDB Search | 1 text index/collection, Search availability |
| Autocomplete, ranking, fuzzy search | MongoDB Search | Deployment/edition/tier, search index build |
| Similar embedding lookup | MongoDB Vector Search | Version, search index config, deployment support |
| Geospatial lookup | `2dsphere` / `2d` | GeoJSON, coordinates, never as shard key |
| Dynamic fields in `attributes` | Wildcard | Wildcard restrictions, version, sparsity, query patterns |
| Uniformly distributed sharding | Hashed shard key | No unique/multikey, range/sort limitations |
| Time-ordered measurement queries | Time series indexes on meta/time/measurement | Bucket semantics, version/FCV, TTL, unsupported types |
| Reusable filtering pipeline | Standard view + source indexes | No direct general indexes on views |
| Ultra-fast aggregate reporting | Materialized collection + indexes | Refresh pipeline and consistency model |
| Physically ordered ID range scans | Clustered collection | Clustered key, defined at creation, version |

Each specialized index optimizes one query class while adding write overhead, build cost, and compatibility constraints. **Never create every index** just because a collection has many fields.

## 21. Practice Exercises

### Exercise 1 — Identify the Environment

Run `db.version()`, `db.hello()`, and (with privileges) `getParameter featureCompatibilityVersion`. Record:

1. Which server version is running?
2. Are you connected to `mongos`?
3. Is there a replica set name?
4. Does FCV match the features you plan to use?

Explain why the `mongosh` client version does not answer any of these questions.

### Exercise 2 — Normal Collections and Index Type Limits

Using `lab.catalog` from Section 4, create the B-tree compound, TTL, hashed, wildcard, and `2dsphere` indexes from the examples. List them with `getIndexes()`, and explain which query class each index serves.

### Exercise 3 — Multi-Field Text Index

Create a text index spanning `title` and `body` on `articles` and run `$text`. Why can you not create **two independent text indexes** on the same collection? Why does MongoDB Search not share that same limit?

### Exercise 4 — TTL Is Not a Precision Timer

Create a normal collection with documents having varied `expiresAt` values and create a TTL index with `expireAfterSeconds: 0`. Observe when documents disappear. Explain why the TTL monitor is not an exact-second timer and why write load must be evaluated before enabling TTL on large datasets.

### Exercise 5 — Time Series and Default Indexes

Create `sensorReadings` from Section 11 in an environment supporting time series. Compare `getIndexes()` against a newly created normal collection; explain why there is no default `_id_` index like a normal collection. Check your version before attempting measurement secondary indexes.

### Exercise 6 — Clustered Collections

If your environment supports them, create a clustered collection with a `clusteredIndex` on `_id`. Why can there not be two clustered indexes? Why must the clustered index be declared at collection creation rather than added later via `createIndex()`?

### Exercise 7 — Sharding and Unique Indexes

A `users` collection is sharded by `tenantId`. You want emails unique **within a tenant**. Propose a valid unique index.

Guided solution:

~~~javascript
db.users.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
);
~~~

Explain why `{email: 1}, unique: true` fails the shard-key prefix rule. If business rules require emails unique **across all tenants**, you need a different uniqueness architecture rather than simply omitting `tenantId` from the sharded index.

### Exercise 8 — Choosing Search Over Legacy Text

An application needs fuzzy search and vector similarity. Compare legacy text indexes with Search/Vector Search indexes; write out the pre-deployment questions to answer for Atlas or self-managed setups, including **version, tier, search service, index creation API, and query operators**.

### Exercise 9 — Supported Indexes vs. Actually Used Indexes

Create `{category: 1, createdAt: -1}` and run `explain("executionStats")` for a `category` query. Then run another query filtering solely on a field not in the index. Why can you not claim "creating an index makes every query fast"?

### Exercise 10 — Planning a Downgrade

A system running MongoDB 8.3 created a `2dsphere` version-4 index and is preparing to downgrade to a lower FCV. List the checks needed for index formats, backups, feature flags, and index rebuilds before changing FCV. Explain why downgrading binaries without addressing index versions can fail.

## 22. Summary

MongoDB index limitations cannot be determined solely from an index type's name. Sound design evaluates **collection type**, **binary version and FCV**, **topology/edition/service**, and then **key patterns, data types, index options, build feasibility, and query plans**.

Core points:

1. **Normal collections** support many general index types, yet each type carries its own data-type, uniqueness, and syntax rules.
2. **Standard views** hold no direct general indexes; use source-collection indexes. **Materialized results** are physical collections and can hold indexes.
3. **Time series** index by bucket and restrict text, unique, certain multikey/geo, TTL, and sharding configurations by version.
4. **Clustered collections** bind a clustered index to storage layout, must be defined at creation, and differ from B-tree secondary indexes.
5. **Hashed indexes** disallow unique, multikey, and covered queries; **wildcards** cannot be shard keys; **geospatial** indexes cannot be shard keys.
6. **Sharded clusters** require shard-key backing indexes, shard-key prefixes on unique indexes, and multi-shard index build coordination.
7. **Search/Vector Search** are separate index engines; never conflate them with legacy text indexes or assume edition availability blindly.
8. **Versions and FCV** can block index creation or downgrades; consult exact version docs and index formats.
9. **A successful index build is not enough:** use `explain()` and workload metrics to confirm queries truly benefit.

### Official MongoDB Documentation

- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — index types and read/write costs.
- [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — general and sharding limits.
- [Wildcard Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/reference/restrictions/) — incompatible index types, shard keys, compound wildcards.
- [Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/) — one text index/collection and `$text` restrictions.
- [Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/) — unique, multikey, covered query limits.
- [Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/) — collation, shard key, and geometry formats.
- [2dsphere Index Versions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/2dsphere-index-versions/) — version 4 and FCV compatibility.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — single-field, Date, background TTL.
- [Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — time series index and sharding restrictions.
- [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) — bucket indexes, secondary indexes, and versions.
- [Clustered Collections](https://www.mongodb.com/docs/manual/core/clustered-collections/) — clustered indexes and creation limits.
- [Views](https://www.mongodb.com/docs/manual/core/views/) — no general indexes on views, Search-compatible views.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — shard key prefix for unique indexes.
- [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/) — required indexes backing shard keys.
- [createSearchIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createSearchIndex/) — supported Search/Vector Search environments and admin commands.
- [createIndexes()](https://www.mongodb.com/docs/manual/reference/command/createIndexes/) — options, Stable API, commit quorum, and builds.
- [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/) — FCV and compatibility management.
