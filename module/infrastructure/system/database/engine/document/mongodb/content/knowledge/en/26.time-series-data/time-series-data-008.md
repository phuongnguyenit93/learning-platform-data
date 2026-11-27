# Update, Transaction, and Sharding Limitations by Supported MongoDB Version

**Time series collections** in MongoDB are optimized for sequences of timestamped **measurements**: IoT sensor telemetry, server metrics, market ticks, performance counters, and timestamped events. From the application's perspective, you still call `insertOne()`, `find()`, or `aggregate()` on documents; under the hood, MongoDB packs measurements sharing metadata and nearby timestamps into **buckets** for efficient compression and querying.

That very optimization creates **constraints different from regular collections**, especially in the three areas covered by this lesson:

1. **Updates and deletes:** Across common server releases, you cannot arbitrarily edit `temperature`, `observedAt`, or a single measurement via `updateOne()` as on a regular collection. Time-series updates are tightly restricted, and **delete** restrictions also changed significantly starting in MongoDB 7.0.
2. **Transactions:** MongoDB **forbids writing to a time series collection inside a multi-document transaction** per the Database Manual; **reading** from a time series collection inside a transaction is supported, with caveats around snapshots and namespace changes.
3. **Sharding:** Time series collections permit only specific shard key fields; `timeField` carries hotspot risks and is **deprecated in shard keys starting in MongoDB 8.0**. **Resharding** time series collections gained major support in **8.0.10**; not all regular-collection sharding admin commands apply.

Therefore, "Does time series support updates, deletes, transactions, or sharding?" **cannot be answered with a simple yes or no**. You must specify **server version, Feature Compatibility Version (FCV), topology, operation type, filter, modified fields**, and business requirements.

This lesson belongs to the **Time Series Data** chapter of the *Database Engine Document MongoDB* module. Examples use `mongosh` and the MongoDB Java Sync Driver; illustrative DDL and sharding commands should run only in a **lab cluster**, never in production.

## Learning Objectives

After this lesson, you will be able to:

- Explain how `timeField`, `metaField`, `granularity`, and buckets drive write limitations.
- Read compatibility milestones from **5.0 → 5.1 → 6.0/6.3 → 7.0 → 8.0/8.0.10 → newer releases** without confusing update rules with delete rules.
- Write valid `updateMany()` commands that **filter and modify only `metaField`**, and identify rejected `updateOne()`, `upsert`, measurement/`timeField` updates, or replacement updates.
- Distinguish time-series deletes in **5.1–6.x** from relaxed behavior **from 7.0 onward**, alongside bucket-based TTL.
- Explain accurately why **write transactions are disallowed** on time series collections and design alternative workflows when cross-collection atomicity or corrections are needed.
- Choose shard keys from `metaField`/subfields, mitigate monotonic `timeField` risks, and recognize **zone sharding** limits and **reshard** prerequisites.
- Diagnose compatibility via `buildInfo`, `getParameter`/FCV, `listCollections`, and version-specific documentation.
- Organize ingestion, corrections, retention, analytics/read models, and application-level consistency guards.

> **Source of truth:** This lesson references the official MongoDB Database Manual and release notes. Capabilities vary by **patch release**, version branch, and **FCV**, especially during rolling upgrades. Never assume a driver's `updateOne` or `startTransaction` method implies server support for time series collections. Version reference links appear at the end.

## 1. Time-Series Documents and Bucket Structure

A measurement might look like:

~~~javascript
{
  observedAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    deviceId: "sensor-01",
    site: "HCM",
    kind: "temperature"
  },
  temperatureC: 28.4,
  humidityPct: 73,
  quality: "raw"
}
~~~

Components:

| Component | Purpose | Updatable? |
|---|---|---|
| `observedAt` (`timeField`) | **BSON Date** of the measurement; supports grouping/sorting/range scans. | Cannot be modified via standard time-series updates per Manual limits. |
| `meta` (`metaField`) | Series identifier: device, site, source type; typically stable. | **Metadata** can be updated via `updateMany` under specific constraints since 5.1. |
| `temperatureC`, `humidityPct` | Measured values changing per timestamp. | Cannot be updated via `updateMany` under metadata-only limits. |
| `quality` | Per-measurement status/classification if outside `metaField`. | Cannot be updated directly under metadata-only rules. |
| `_id` (if present) | Logical measurement ID. | No default `_id` index like regular collections; do not treat it as a DB-enforced collection-wide unique key. |

### 1.1. How Data Is Optimized

~~~text
Application sees:
  measurement 1: meta={deviceId:S1}, 08:00, temp=28.4
  measurement 2: meta={deviceId:S1}, 08:01, temp=28.6
  measurement 3: meta={deviceId:S1}, 08:02, temp=28.7

MongoDB stores efficiently:
  bucket for S1 + nearby time span
     shared metadata
     packed timestamps
     columnar/bucket-compressed values
~~~

MongoDB packs measurements sharing `metaField` and nearby timestamps. Storage is optimized for **high-volume inserts, source/time-range reads, and rare edits**, which is why per-measurement updates lack regular-collection semantics. See [About Time Series Data](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/).

### 1.2. Logical Collection Name vs. Internal Bucket Namespace

Applications read and write through the declared `timeseries` collection, e.g., `db.telemetry`. Never read or modify `system.buckets.telemetry` directly to "bypass" update limits—bucket layout is an internal implementation detail that changes across versions, and direct writes risk corrupting data, compression, or metadata.

Starting in **MongoDB 9.0**, documentation describes a different internal namespace layout than versions using a view + bucket collection pair—another reason **never to hardcode internal storage paths**. Always use the logical time-series collection API and verify against your server version.

### 1.3. Time-Series Is Not an Infinitely Mutable Event Store

Business requirements:

- Every 10 seconds write a new temperature reading → fits time-series well.
- Occasionally fix `meta.site` labels for a group of devices → metadata updates can work.
- Edit thousands of stored `temperatureC` values or shift `observedAt` after a timezone bug → **not** supported as standard updates in the Manual releases discussed.
- Commit two measurements and a billing record atomically together → **cannot** wrap time-series writes inside a MongoDB multi-document transaction.

If your application must mutate individual measurements frequently, re-evaluate your **data model** instead of forcing a time-series collection to act like a full OLTP table.

## 2. Creating the Lab Collection and Data

Examples run in a dedicated `ts288_lab` database on MongoDB **5.1+** (so metadata update examples work). Creation and inserts also work on **MongoDB 5.0** if you skip 5.1+ operations.

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

// Run once in a practice environment where the collection does not yet exist.
lab.createCollection("telemetry", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

lab.telemetry.insertMany([
  {
    observedAt: ISODate("2026-11-14T08:00:00Z"),
    meta: { deviceId: "sensor-01", site: "HCM", kind: "temperature" },
    temperatureC: 28.4, humidityPct: 73, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:01:00Z"),
    meta: { deviceId: "sensor-01", site: "HCM", kind: "temperature" },
    temperatureC: 28.7, humidityPct: 72, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:02:00Z"),
    meta: { deviceId: "sensor-02", site: "HN", kind: "temperature" },
    temperatureC: 23.1, humidityPct: 68, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:03:00Z"),
    meta: { deviceId: "sensor-02", site: "HN", kind: "temperature" },
    temperatureC: 23.4, humidityPct: 66, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:04:00Z"),
    meta: { deviceId: "sensor-03", site: "HCM", kind: "humidity" },
    humidityPct: 76, quality: "raw"
  }
])
~~~

**Practice note:** Re-running `createCollection` or `insertMany` is not idempotent; it errors on existing collections or creates duplicate readings. To retry, use a new lab database/collection or a **lab-only** reset procedure—never copy `drop()` commands to production. Timestamps in this fixture are fixed points; do not attach a short TTL to this collection or data will expire depending on when you run the lab.

### 2.1. Querying by Source and Time Range

~~~javascript
lab.telemetry.find({
  "meta.deviceId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:05:00Z")
  }
}).sort({ observedAt: 1 })
~~~

In the fixture, `sensor-01` has **two** measurements. Combining `meta` + time range aligns well with bucket organization; favor stable metadata and bounded time filters over full-history scans.

### 2.2. Aggregating Data Over Time

~~~javascript
lab.telemetry.aggregate([
  { $match: {
      "meta.deviceId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T08:05:00Z")
      }
  } },
  { $group: {
      _id: "$meta.deviceId",
      samples: { $sum: 1 },
      avgTemperatureC: { $avg: "$temperatureC" }
  } }
])
~~~

The mean is **28.55 °C** (from 28.4 and 28.7), `samples: 2`. This read pipeline requires no transaction and performs no time-series writes.

## 3. Version Compatibility Matrix: Key Milestones

| MongoDB Server | Time-series updates / deletes | Transactions | Sharding and related features |
|---|---|---|---|
| **5.0** | **Introduces** time-series. Primarily insert/read; **no manual updates/deletes** under initial limits. | No time-series writes in multi-document transactions. | Sharded time-series collections not supported. |
| **5.1** | Supports **metadata-only multi-updates** and **restricted deletes**: filter only on `metaField`; multi-doc deletes only. | No time-series writes in transactions. | **Initial sharded time-series support**. |
| **5.2** | 5.1 update/delete restrictions continue. | No time-series writes in transactions. | Adds **column compression** for time-series. |
| **6.0** | Metadata-only updates; 5.1–6.x delete limits remain. | No time-series writes in transactions. | Supports **secondary indexes on measurement fields** and related admin operations per version. |
| **6.3** | Metadata update limits do not allow arbitrary measurement edits. | No time-series writes in transactions. | Newly created time-series get **default compound `metaField + timeField` index**; custom bucket spans supported. |
| **7.0** | **Deletes significantly relaxed**: `deleteOne`/`deleteMany` with flexible filters outside transactions; **updates remain metadata-only multi-updates**. | Still no time-series writes in transactions; reads allowed. | **Partial TTL index on `metaField`** supported; shard key limits remain; no reshard in 7.0. |
| **8.0** | Do not infer measurement updates became valid just because deletes relaxed; check Manual Updates. | No time-series writes in transactions. | **`timeField` in shard keys deprecated**; prefer metadata-based keys. |
| **8.0.10+** | Branch update restrictions still apply. | No time-series writes in transactions. | **Time-series resharding supported**, requiring **all shards on at least 8.0.10**. |
| **8.3 / 9.x and newer** | Check branch-specific docs as storage namespaces, indexes, and execution evolve. | Never assume write transactions became valid unless documented in the Manual. | Check release notes/FCV and Limitations for your exact branch rather than relying on old examples. |

Verify milestones in [Release Notes 7.0](https://www.mongodb.com/docs/v7.0/release-notes/7.0/), [Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/), [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/), and [Shard a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-shard-collection/).

### 3.1. Distinguish Three Versions That Can Differ

An application stack involves:

- **Server binary version:** e.g., `8.0.10` on `mongod`.
- **FCV:** compatibility gate controlling enabled features across upgrades/rolling upgrades.
- **Driver version:** e.g., Java Sync Driver 5.x; a newer driver exposes newer APIs but cannot make a 5.0 server run 7.0 features.

In sharded clusters, you also have **`mongos`, config servers, and every shard replica set**; when a requirement says **"all shards ≥ 8.0.10"**, checking only one router's version is insufficient.

### 3.2. Do Not Confuse the "Current" Manual with Your Running Server

If you run MongoDB 6.0 while reading the **current Database Manual**, `deleteOne()` with a measurement predicate appears valid (for 7.0+) yet fails on 6.0. Conversely, reading 7.0 docs and concluding time-series **can never be resharded** became outdated as of 8.0.10.

**Always qualify capability claims with the exact version.**

## 4. Update Restrictions: Filter and Modify Only `metaField`, Multi-Update Only

On time-series collections from **MongoDB 5.1** per the Database Manual, an update must satisfy **all five rules simultaneously**:

1. **Filter** references only `metaField` values (including metadata subfields where applicable).
2. **Update** modifies only **`metaField` values**; never modify `timeField` or measurement fields like `temperatureC`.
3. **Update document** uses only **update operators** (such as `$set`, `$unset`), never a replacement document or an aggregation update pipeline.
4. Must not limit updated document count: use `updateMany()` or `update` with `multi: true`.
5. **Never use `upsert: true`.**

Violating even one of these five rules causes an update that works on regular collections to **be rejected** on time-series collections.

### 4.1. Valid Metadata Update Example

The `telemetry` fixture has two measurements from `sensor-01` at site `HCM`. To standardize the site code, update metadata on **all matching measurements**:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

const result = lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.site": "SGN" } }
)

printjson(result)
~~~

This filters on `meta` and modifies only `meta.site`—a valid metadata-only multi-update supported since 5.1. Afterward, both `sensor-01` measurements display `meta.site: "SGN"`.

**Do not mistake this for a regular document update.** Time-series collections organize buckets by metadata; modifying `meta` affects bucket grouping/processing and can be costly. By design, metadata **should change rarely**.

### 4.2. How Many Measurements Did `updateMany` Actually Affect?

If the filter matches 2 measurements, `updateMany()` modifies both. Always read `matchedCount` and `modifiedCount` **from the server response** instead of assuming success because the driver threw no exception.

If many sensors share site `HCM`, running:

~~~javascript
lab.telemetry.updateMany(
  { "meta.site": "HCM" },
  { $set: { "meta.region": "SOUTH" } }
)
~~~

modifies **every measurement** matching `HCM`, not just one device. In a collection holding billions of measurements, an overly broad metadata update is expensive. Narrow filters by **`deviceId` or series-identifying metadata** whenever possible.

### 4.3. Invalid: Modifying Measurement Value `temperatureC`

~~~javascript
// Invalid under metadata-only update restrictions.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { temperatureC: 30.0 } }
)
~~~

`temperatureC` is a measurement value, **not `metaField`**. Using `updateMany` does not make editing measurement fields legal.

A common mistake is trying to "correct `temperatureC` at 08:01 from 28.7 to 29.0" with:

~~~javascript
// Violates both rules: filtering on measurement/timeField and updating a measurement.
lab.telemetry.updateMany(
  {
    "meta.deviceId": "sensor-01",
    observedAt: ISODate("2026-11-14T08:01:00Z")
  },
  { $set: { temperatureC: 29.0 } }
)
~~~

Never treat this like a regular-collection upsert. Time-series is built for **append-only / insert-first** workloads; corrections require a dedicated workflow as covered in Section 11 / Section 17.

### 4.4. Invalid: `updateOne()`

~~~javascript
// Invalid: an update limiting the number of measurements.
lab.telemetry.updateOne(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.site": "SGN" } }
)
~~~

Even when editing only `meta`, `updateOne()` enforces **single-update** semantics, violating `multi: true`. Switch to `updateMany()`:

~~~javascript
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.site": "SGN" } }
)
~~~

Do not assume `updateOne()` becomes valid just because only one measurement currently matches; the restriction applies to **operation type**, not runtime match count.

### 4.5. Invalid: `upsert: true`

~~~javascript
// Invalid for time-series updates.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-99" },
  { $set: { "meta.site": "HCM" } },
  { upsert: true }
)
~~~

To create new measurements, use `insertOne()`/`insertMany()` with a **valid BSON Date `timeField`** and appropriate metadata. `upsert` on time-series lacks regular-entity semantics; if you need "create device if missing", keep device profiles in a **regular collection** with a unique `deviceId` and idempotent workflow.

### 4.6. Invalid: Full-Document Replacement or Update Pipeline

~~~javascript
// Wrong: replacement document is not an update operator expression.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { meta: { deviceId: "sensor-01", site: "SGN" } }
)

// Wrong: aggregation update pipeline is not an allowed update operator expression.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  [
    { $set: { "meta.site": "SGN" } }
  ]
)
~~~

Use an operator update document with `$set`/`$unset` touching only `metaField`. A pipeline `[{$set: {...}}]` looks similar to modifier `{$set: {...}}`, yet is a **different update form** rejected by time-series updates.

### 4.7. Can the Filter Include `observedAt` to Narrow Scope?

No, not under metadata-only update restrictions:

~~~javascript
// Invalid: filter contains timeField, outside metaField.
lab.telemetry.updateMany(
  {
    "meta.deviceId": "sensor-01",
    observedAt: { $gte: ISODate("2026-11-14T08:00:00Z") }
  },
  { $set: { "meta.site": "SGN" } }
)
~~~

This boundary is critical: even if the update changes only `meta.site`, **filtering by timestamp** violates the metadata-only filter rule. To relabel "only measurements from last week", a single time-series metadata update cannot express it; use a correction or migration strategy instead.

### 4.8. When `metaField` Is an Object

`metaField` can be an object:

~~~javascript
meta: {
  deviceId: "sensor-01",
  site: "HCM",
  kind: "temperature"
}
~~~

You can add a subfield:

~~~javascript
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-02" },
  { $set: { "meta.ownerTeam": "observability" } }
)
~~~

Remember that **bucket identification** keys off metadata: changing or adding subfields alters metadata groups. Never put per-second changing fields like `currentTemperature`, `lastHeartbeatAt`, or retry counters inside `meta`—they inflate distinct metadata values and hurt bucket compression.

### 4.9. Metadata Fields Used in a Shard Key Have Routing Constraints

In **sharded** time-series collections, updating `meta` can touch a **shard key component**. Modifying shard key values and routing updates follow version- and topology-specific rules. Updating `meta.site` is simpler when `meta.site` is not part of the shard key; if it is in the shard key, verify support and routing/migration costs rather than treating it like a plain metadata update.

**Good design:** keep series-identifying metadata **stable**; if a device relocation represents a new series segment, record new measurements under the updated metadata rather than rewriting history.

## 5. Business Update Needs: Which Alternatives Work?

| Requirement | Use time-series `updateMany`? | Recommended approach |
|---|---|---|
| Standardize `meta.site` across all `sensor-01` readings | Yes, under metadata-only multi-update and version limits. | `updateMany({"meta.deviceId": ...}, {$set: {"meta.site": ...}})`. |
| Rename `meta.ownerTeam` across a device group | Possibly, if filtering strictly on metadata. | Controlled metadata update. |
| Fix `temperatureC` at timestamp `08:01` | No under current update limits. | Correction workflow, 7.0+ delete+reinsert, or overlay. |
| Shift `observedAt` due to wrong timezone | No. | Write corrected readings and handle bad records per policy. |
| Upsert measurement if absent | No. | Ingest via `insert` + external logical `eventId`/dedup. |
| Mark `quality: "corrected"` outside `meta` | No. | Correction overlay or new revision—do not mutate measurement. |
| Remove old measurements by retention | Not an update; use TTL. | `expireAfterSeconds` / partial TTL per version. |
| Commit measurement and payment atomically | Cannot wrap time-series writes in a MongoDB transaction. | Outbox/async ingestion or shift source of truth where atomicity is required. |

### 5.1. Do Not Use `bulkWrite` to "Bypass" Limits

~~~javascript
// Does not make a prohibited measurement update valid.
lab.telemetry.bulkWrite([
  {
    updateMany: {
      filter: { "meta.deviceId": "sensor-01" },
      update: { $set: { temperatureC: 30.0 } }
    }
  }
])
~~~

`bulkWrite` simply batches operations; MongoDB still enforces **time-series restrictions** on each inner operation. Passing `ordered: false` or `bypassDocumentValidation: true` likewise never turns a measurement update into a valid operation.

### 5.2. Never Write Directly to `system.buckets`

Some tools and metadata views expose bucket collections. **Never update bucket documents directly** to edit `temperatureC`: internal formats encode compression, ordering, indexes, and metadata invariants, and direct CRUD risks blocking or corrupting storage.

Applications must interact strictly with the **logical time-series collection**. If corrections occur frequently, consider a regular collection or an explicit append-only correction log.

### 5.3. Not Every Timestamped Dataset Belongs in Time-Series

Examples:

- Per-minute sensor readings queried by source/hour with rare edits → great fit for time-series.
- Latest device state updated continuously with CAS/version checks → **regular collection** `deviceState` fits better.
- Events needing unique `eventId` and frequent atomic updates/cancellations → regular collection or ledger/outbox depending on invariants.
- Measurement streams + editable annotations → time-series for raw measurements, **regular collection** for annotations/corrections, joined or projected on read.

Compression and time-range benefits must never override genuine **OLTP mutation and transactional** requirements.

## 6. Delete Restrictions: Major Changes Starting in MongoDB 7.0

Older guides say "time-series cannot delete documents", whereas newer guides show `deleteOne()` with arbitrary filters. The difference comes down to **server version milestones**.

### 6.1. MongoDB 5.0: No Manual Deletes

In the initial **5.0** release, time-series focused on **inserts and reads**; manual updates and manual deletes were unsupported. To bound retention, configure **TTL** at collection creation. Dropping a lab collection with `drop()` has completely different semantics and must be handled with extreme caution.

### 6.2. MongoDB 5.1 to 6.x: Multi-Document Deletes Filtered by Metadata

Under **5.1–6.x** restrictions:

- Delete predicates may reference only **`metaField`**.
- Must not limit deleted document count; use `deleteMany()` or `delete` with `justOne: false`.
- Cannot use `deleteOne()` to delete a single measurement.

Example on MongoDB 6.0:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

// Run only in the lab on data no longer needed.
// Delete all measurements for sensor-03:
lab.telemetry.deleteMany({
  "meta.deviceId": "sensor-03"
})
~~~

Contrast with:

~~~javascript
// Invalid under 5.1–6.x restrictions because the filter references timeField.
lab.telemetry.deleteMany({
  observedAt: {
    $lt: ISODate("2026-11-14T08:02:00Z")
  }
})
~~~

Thus, on MongoDB 6.0, **do not** assume `deleteMany({observedAt: {$lt: cutoff}})` works for purging data before a cutoff. Use TTL, retention/migration workflows, or a planned upgrade.

### 6.3. MongoDB 7.0+: Most `delete` Restrictions Relaxed

MongoDB 7.0 Release Notes confirm removing **most time-series constraints** on `delete`-based operations:

- `delete`
- `deleteOne()`
- `deleteMany()`
- `Bulk.find.delete()` / `deleteOne()` variants

In supporting deployments and **outside multi-document transactions**, you can delete by metadata, timestamp, or measurement values. Example:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

// MongoDB 7.0+: delete one measurement matching logical criteria.
lab.telemetry.deleteOne({
  "meta.deviceId": "sensor-02",
  observedAt: ISODate("2026-11-14T08:02:00Z")
})

// MongoDB 7.0+: delete measurements prior to a cutoff.
lab.telemetry.deleteMany({
  observedAt: {
    $lt: ISODate("2026-11-14T08:03:00Z")
  }
})

// MongoDB 7.0+: filter on measurement value.
lab.telemetry.deleteMany({
  temperatureC: { $gt: 100 }
})
~~~

**These commands are destructive examples**: do not run them sequentially if you want to preserve the fixture for other exercises. Test only on a fresh or backed-up lab collection. `deleteOne` does not guarantee business uniqueness if two readings share `sensorId`/timestamp; time-series does not create a default unique index on measurement IDs.

### 6.4. Remaining Restriction: No Deletes Inside Transactions

MongoDB 7.0+ relaxing delete predicates **does not** permit time-series writes/deletes inside a multi-document transaction. That remains prohibited per the current Time Series Collection Limitations page.

| Delete operation | 5.0 | 5.1–6.x | 7.0+ |
|---|---|---|---|
| `deleteMany({"meta.deviceId": "S1"})` | Unsupported | **Yes**, metadata filter. | Yes, outside transactions. |
| `deleteMany({observedAt: {$lt: cutoff}})` | Unsupported | **No**, `timeField` filter invalid. | **Yes**, outside transactions. |
| `deleteMany({temperatureC: {$gt: 100}})` | Unsupported | No, measurement filter invalid. | Yes, outside transactions. |
| `deleteOne({ ... })` | Unsupported | No, singleton deletes restricted. | Yes, outside transactions. |
| Delete inside multi-document transaction | No | No | **No**, despite relaxed delete syntax. |
| Automatic time-based TTL | Yes | Yes | Yes. |

**Note:** Some legacy helpers like `remove()` retain dedicated restrictions on time-series even after `deleteOne`/`deleteMany` relaxed in 7.0. Stick to modern documented APIs. See [MongoDB 7.0 Release Notes — Time Series](https://www.mongodb.com/docs/v7.0/release-notes/7.0/).

### 6.5. Deletes May Reorganize / Repack Buckets

Do not expect `deleteOne` on a measurement to carry the same cost as deleting one row in a regular collection. A measurement lives inside a bucket alongside many sibling samples. Deleting selective samples can force the storage engine to rewrite buckets; dropping whole buckets via matching predicates has a different cost profile from selective deletes.

For periodic cleanup, **TTL** is usually preferable to a cron job deleting millions of measurements continuously. For **immediate privacy deletions**, evaluate SLAs, authorization, data age, and version-specific delete performance; TTL never guarantees instant deletion.

### 6.6. When Measurements Stream Continuously During Deletes

`deleteMany()` is not an all-or-nothing transaction over an evolving dataset; if writers keep inserting matching readings concurrently, the final state changes. For "purge all data for a decommissioned device":

1. Block or drain **new ingestion** for that device.
2. Execute the version-appropriate delete.
3. Verify zero matches via `find`/`countDocuments` over the target scope.
4. Retry idempotently until no matching readings remain, if required.
5. Record audit/retention/authorization state in an appropriate **regular collection**.

Never run a single `deleteMany` and assume no data remains while live ingestion continues feeding the same series.

## 7. TTL and Retention: Replacing Most Manual Deletes

MongoDB time-series supports **automatic data expiration** via `expireAfterSeconds`. For append-only telemetry, this is typically far cleaner than a scheduled `deleteMany` cron job.

### 7.1. Creating a Collection with TTL

Example retaining data for **7 days**:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.createCollection("telemetry7d", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 7 * 24 * 60 * 60
})
~~~

MongoDB automatically removes **buckets** once all measurements inside them expire. The logical threshold is `timestamp + retention`, though physical deletion **does not happen at the exact second**.

### 7.2. Bucket-Level TTL, Not Per-Sample Timers

~~~text
Bucket sharing device/metadata:

  10:01  sample A
  10:02  sample B
  10:59  sample C

Retention = 7 days

10:01 + 7d: A individually past threshold
10:02 + 7d: B individually past threshold
10:59 + 7d: entire bucket becomes eligible for cleanup
         |
         v
Background TTL monitor runs periodically; actual deletion may lag further.
~~~

The MongoDB Manual notes the background TTL task runs periodically (typically roughly every **60 seconds**) and removes a bucket only once **all samples inside it** expire; actual delay also depends on load. Therefore:

- TTL is not a **hard real-time deadline** guaranteeing zero data after exactly 7 × 24 hours.
- Legal mandates requiring "erasure at exact time T" need dedicated purge workflows and verification rather than relying solely on TTL.
- Changing `granularity`/bucket spans affects when buckets become eligible for deletion.

### 7.3. Enabling or Updating TTL on an Existing Collection

Per MongoDB docs, use `collMod`:

~~~javascript
// Example updating retention on an existing time-series collection.
const lab = db.getSiblingDB("ts288_lab")

lab.runCommand({
  collMod: "telemetry7d",
  expireAfterSeconds: 14 * 24 * 60 * 60
})
~~~

Shortening retention can qualify **many buckets at once**, spiking I/O and changing storage rapidly. Plan rollouts, backups/permissions, and monitoring—never run this carelessly in production.

### 7.4. Metadata-Scoped Partial TTL Since MongoDB 7.0

Starting in **MongoDB 7.0**, you can create **partial TTL indexes** using `partialFilterExpression` **referencing only `metaField`**, allowing distinct retentions per series group.

~~~javascript
// Run only on a MongoDB 7.0+ lab.
// Create a separate collection without collection-level TTL:
lab.createCollection("telemetry_tiered", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

lab.telemetry_tiered.createIndex(
  { observedAt: 1 },
  {
    name: "ttl_temp_short",
    expireAfterSeconds: 7 * 24 * 60 * 60,
    partialFilterExpression: {
      "meta.kind": "temperature"
    }
  }
)
~~~

This expires `meta.kind: "temperature"` readings per policy. If the collection also sets collection-level `expireAfterSeconds`, partial TTL can apply a **shorter retention** for matching subsets—never expect partial TTL to extend lifetime past a shorter collection-level TTL covering all measurements.

Never write a partial TTL filter referencing `temperatureC` or `observedAt` when rules restrict filters to **metadata only**. See [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) and [Automatic Removal (TTL)](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/).

### 7.5. TTL vs. Timestamp `deleteOne`

| Goal | Mechanism | Characteristics |
|---|---|---|
| Periodic cleanup of old data | Time-series `expireAfterSeconds` | Efficient by bucket; non-instant. |
| VIP devices kept 30 days, standard 7 days | 7.0+ metadata partial TTL / policy | Verify interaction between collection-level TTL and partial indexes. |
| Immediate deletion of one bad sample | 7.0+ `deleteOne` | Needs selective filter; may repack bucket; outside transactions. |
| Delete all data for a decommissioned device | Metadata `deleteMany` | 5.1+ with conditions; block ingestion and verify afterward. |
| Delete all data before an arbitrary cutoff | 7.0+ `deleteMany` or TTL/migration | 5.1–6.x forbids `timeField` predicates in manual deletes. |

### 7.6. Timestamps Far Outside Normal Ranges

The MongoDB Manual notes special indexing/optimization considerations for timestamps before `1970-01-01` or after `2038-01-19T03:14:07Z`; review Limitations and index designs accordingly. Never let decades-skewed timestamps enter unchecked without inspecting source data and TTL behavior.

## 8. Transactions: Time-Series **Reads** Allowed, **Writes** Forbidden

MongoDB supports multi-document transactions on regular collections across replica sets and sharded clusters. Time-series collections carry a **specific restriction**:

> **You cannot write to a time-series collection inside a transaction. MongoDB supports reading from a time-series collection inside a transaction.**

This rule holds whether the write is a measurement `insertOne`, a metadata `updateMany`, or a `deleteOne` that works outside transactions. **Passing a `session` never makes a prohibited write valid.**

### 8.1. Scenario Comparison

| Operation | Outside transaction | Inside multi-document transaction |
|---|---|---|
| `telemetry.insertOne(measurement)` | Valid per format/version. | **Unsupported**. |
| `telemetry.insertMany([...])` | Valid per format/version. | **Unsupported**. |
| `telemetry.updateMany(metaFilter, metaUpdate)` | Restricted, 5.1+. | **Unsupported**. |
| `telemetry.deleteMany(metaFilter)` | Version-dependent: 5.1+ meta-only, 7.0+ broader. | **Unsupported**. |
| `telemetry.deleteOne(measurementFilter)` | 7.0+ outside transactions. | **Unsupported**. |
| `telemetry.find(...)` | Valid. | **Readable** in transactions where deployment supports it. |
| `telemetry.aggregate([...read stages...])` | Valid within stage limits. | Readable in transactions subject to stage/readConcern limits. |
| Write to `deviceCatalog` (regular collection) | Valid. | Writable in standard transactions when eligible. |
| Commit `deviceCatalog` and `telemetry` **atomically together** | Two independent operations. | **Not directly possible** via a transaction containing a time-series write. |

### 8.2. Unsupported Transaction Write Example

~~~javascript
// DO NOT USE AS A SOLUTION: anti-pattern shown for recognition.
const session = db.getMongo().startSession()
const sdb = session.getDatabase("ts288_lab")

try {
  session.startTransaction()

  // Writing to a time-series collection inside a transaction is rejected.
  sdb.telemetry.insertOne({
    observedAt: new Date(),
    meta: { deviceId: "sensor-04", site: "HCM" },
    temperatureC: 29.0
  })

  // Even alongside a regular collection update, this transaction is invalid.
  sdb.deviceCatalog.updateOne(
    { _id: "sensor-04" },
    { $set: { lastSeenAt: new Date() } }
  )

  session.commitTransaction()
} catch (err) {
  try { session.abortTransaction() } catch (_) {}
  print("Time-series write in transaction is not supported")
} finally {
  session.endSession()
}
~~~

This snippet **illustrates what is unsupported**, not a pattern to run. Never catch the error and continue `commitTransaction`, nor execute the time-series write **outside the session mid-callback** while claiming all-or-nothing atomicity.

### 8.3. Reading Time-Series Inside a Transaction

On replica sets or sharded deployments supporting transactions, a read-only transaction can read both time-series and regular collections consistently:

~~~javascript
const session = db.getMongo().startSession()
const sdb = session.getDatabase("ts288_lab")

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const samples = sdb.telemetry.find({
    "meta.deviceId": "sensor-01",
    observedAt: {
      $gte: ISODate("2026-11-14T08:00:00Z"),
      $lt: ISODate("2026-11-14T08:05:00Z")
    }
  }).sort({ observedAt: 1 }).toArray()

  printjson(samples)

  session.commitTransaction()
} catch (err) {
  try { session.abortTransaction() } catch (_) {}
  throw err
} finally {
  session.endSession()
}
~~~

This only **reads** time-series without mutating measurements. Do not open read-only transactions for every dashboard query; reserve them for cases genuinely requiring snapshot consistency.

### 8.4. Snapshot Caveat During Drop / Rename / Re-Create

The current Limitations page notes that time-series reads with read concern `"snapshot"` preserve snapshot isolation **provided no concurrent drop or rename occurs** on the target collections. Re-creating the same namespace with a different `granularity` can also affect snapshot guarantees.

Never build a workflow that "holds a long-running read transaction while another job drops and re-creates the time-series collection" expecting unchanging snapshot semantics. Coordinate **schema migrations/DDL windows** with snapshot lifetimes.

### 8.5. Read Concern and Write Concern Do Not Unlock Transactional Writes

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
~~~

These options govern snapshot and acknowledgment semantics—**they never grant permission to write time-series inside a transaction**. Similarly, `retryWrites: true` or `w: "majority"` never turn multiple time-series inserts into an all-or-nothing transaction.

### 8.6. Is a Single `insertMany` Outside a Transaction All-or-Nothing Atomic?

Never assume sending multiple measurements in one `insertMany` makes the batch an atomic transaction. When partial failures occur (validation errors, duplicate IDs in other contexts, network/size limits, `writeConcern` errors), examine **partial success, acknowledged counts, and driver/server retry semantics**.

Time-series uses internal bucketing; never infer application-level batch atomicity from internal bucket behavior. If telemetry batches require a business state of "unpublished until complete", maintain a **batch manifest / ingest ledger** in a regular collection and flip visibility only after verification.

## 9. Transactions with Business Systems: Alternative Designs

An IoT service receives a sample and wants to simultaneously:

1. Insert the measurement into `telemetry` (time-series).
2. Update `deviceCatalog.lastSeenAt` (regular collection).
3. Emit an event for downstream processing.

Because time-series writes **cannot join a transaction**, you cannot wrap all three in one MongoDB transaction. Choose an architecture matching your consistency tolerance.

### 9.1. If Telemetry Tolerates Eventual Consistency

~~~text
Ingest sample
    |
    +-- insert telemetry (time-series)
    |
    +-- update deviceCatalog.lastSeenAt (regular collection)
    |
    +-- publish event
         |
         +-- on failure: retry/reconcile via stable eventId
~~~

These are **independent writes**. Acceptable only when the product **tolerates intermediate states** or runs repair workers. Document failure modes explicitly: sample stored while catalog lags, or catalog updated without sample stored.

### 9.2. Transactional Outbox on **Regular Collections**

A more controlled pattern:

~~~text
1. MongoDB transaction (regular collections only):
     Insert ingestLedger(eventId, payload, status="PENDING")
     Update deviceCatalog ingestStatus
     Insert outbox(eventId, type="INGEST_SAMPLE")
   Commit
         |
         v
2. Worker reads committed outbox/ledger:
     Insert measurement into time-series (outside transaction)
     Mark ingestLedger state="WRITTEN"
         |
         v
3. Reconcile/repair on worker timeouts or duplicates
~~~

The MongoDB transaction guarantees ledger, catalog, and outbox **commit atomically**. `telemetry`, however, is still written **outside the transaction**. Thus the overall workflow is **eventually consistent** and must not be advertised as "atomically committing telemetry too".

### 9.3. Challenge: Deduplicating Measurements in Time-Series

Time-series **does not support unique indexes** like regular collections per the Manual. If a worker inserts a measurement successfully and crashes before marking the ledger `WRITTEN`, retrying can create a **duplicate measurement**.

A reliable workflow needs:

- Stable `eventId` stored alongside each measurement for traceability.
- Unique `eventId` in a **regular collection** to handle repeated ingest requests.
- State machine (`PENDING` / `PROCESSING` / `WRITTEN` / `FAILED`), leased retries, and reconciliation.
- When retry outcomes are ambiguous, **query measurements by `eventId + meta/time`** to decide whether to skip or reconcile—noting this is not an atomic unique constraint on time-series.
- When **strictly guaranteed exactly-once** measurement storage is mandatory, consider keeping the **source of truth in a regular collection** and projecting asynchronously to time-series for analytics, or choosing storage with native idempotent constraints.

**Never claim a ledger transaction guarantees exactly-once time-series inserts**—the two writes do not share a transaction.

### 9.4. Store Corrections with Separate History and Auditability

A faulty device reading may need "correction" while keeping the raw record for auditing:

~~~javascript
// Regular collection, unique logical correctionId:
{
  _id: "CORR-1001",
  eventId: "MEAS-123",
  deviceId: "sensor-01",
  observedAt: ISODate("2026-11-14T08:01:00Z"),
  correctedTemperatureC: 29.0,
  reason: "recalibration",
  createdAt: new Date()
}
~~~

Storing corrections in a **regular collection** enables status updates, versioning, unique keys, and transactions alongside other business records. Readers apply corrections during aggregation or read-model materialization, with **no physical mutation of time-series measurements required**.

### 9.5. When Atomic Business Records Are Mandatory, Move the Storage Boundary

For a financial ledger where every event requires a unique ID and atomic commits with account balances or invoices, **time-series should not be the source of truth**, even though entries have timestamps. Use a regular collection with transactions and unique indexes as the source of truth, and project to time-series purely for **time-based analytics**.

**Choose storage by your strictest invariant, not compression ratios alone.**

## 10. Sharding Time-Series: Supported Since MongoDB 5.1, with Dedicated Shard Keys

A time-series collection can grow to billions of measurements, exceeding a single replica set's capacity or throughput. Starting in **MongoDB 5.1**, you can **shard time-series collections** on a sharded cluster.

However, **you cannot pick arbitrary shard keys**. Allowed fields per the Manual are:

- **`metaField`** — e.g., `meta`.
- **Subfields of `metaField`** — e.g., `meta.deviceId`, `meta.site`.
- **`timeField`** — e.g., `observedAt`, restricted to **ranged** and **trailing position in the shard key pattern**; also **deprecated starting in 8.0** if included.

Never shard directly on `temperatureC`, `humidityPct`, `quality`, or `_id` unless explicitly permitted.

### 10.1. Valid Shard Key Candidates by Field Eligibility

For a collection with:

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "meta"
}
~~~

eligible candidates include:

~~~javascript
// Ranged metadata subfield:
{ "meta.deviceId": 1 }

// Hashed metadata subfield:
{ "meta.deviceId": "hashed" }

// Compound metadata:
{ "meta.site": 1, "meta.deviceId": 1 }

// Metadata + trailing ranged timeField:
{ "meta.deviceId": 1, observedAt: 1 }
// Note: contains timeField => deprecated starting in MongoDB 8.0.
~~~

Do not assume every key above works unconditionally regardless of dataset or index state; you still need supporting indexes, matching collation, proper sharding timing, version compatibility, and balancer capacity. This list illustrates **field eligibility** only.

### 10.2. Invalid Shard Key Examples

~~~javascript
// Invalid: measurement field.
{ temperatureC: 1 }

// Invalid: _id is not an eligible field.
{ _id: "hashed" }

// Invalid: timeField cannot be hashed.
{ observedAt: "hashed" }

// Invalid: timeField precedes another field.
{ observedAt: 1, "meta.deviceId": 1 }
~~~

On time-series collections, `timeField` must be **ranged** and **trailing** when used. From 8.0 onward, even where legacy configs remain accepted for compatibility, keys containing `timeField` are **deprecated**—avoid them in new designs when a metadata-based key works well.

### 10.3. Connecting Through `mongos`

On a sharded cluster, applications and `mongosh` connect to the **`mongos` query router**. Check topology per your version:

~~~javascript
db.adminCommand({ hello: 1 })
// On mongos, the response typically includes msg: "isdbgrid".

sh.status()
~~~

Never run `sh.shardCollection()` against a standalone `mongod` and conclude time-series sharding is unsupported when the topology itself is not a sharded cluster. **Sharding requires a cluster**, whereas unsharded time-series collections work on standalone or replica sets.

### 10.4. Creating and Sharding a Time-Series Collection on a Lab Cluster

**Run only on a lab sharded cluster** (≥ 5.1, with prerequisites satisfied):

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.createCollection("telemetry_sharded", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

// Create supporting index, e.g., hashed index on metadata deviceId.
lab.telemetry_sharded.createIndex({
  "meta.deviceId": "hashed"
})

// Admin command enabling sharding on the lab collection:
sh.shardCollection(
  "ts288_lab.telemetry_sharded",
  { "meta.deviceId": "hashed" }
)
~~~

The MongoDB Manual shows sharding an existing time-series collection on a metadata subfield; once declared `timeseries`, `shardCollection()` uses the existing metadata configuration. When sharding populated collections, ensure the supporting index exists per server rules. These steps are **lab DDL**, never per-request application commands.

### 10.5. Choosing Metadata with Suitable Cardinality and Frequency

Suppose devices distribute as:

~~~text
site=HCM:    90% measurements
site=HN:      7% measurements
site=DN:      3% measurements

deviceId:    200,000 distinct values
~~~

If the shard key is `{"meta.site": 1}`, cardinality is tiny; all `HCM` traffic shares **one key**, risking a hot range/chunk. Sharding on `{"meta.deviceId": "hashed"}` across 200,000 well-distributed devices spreads writes across shards.

**However:** if a single sensor emits 80% of all measurements, `hash(deviceId)` still maps to one constant value. Hashing cannot split **a single metadata value** across multiple shard keys. Investigate **hot devices**, series design, bucket cardinality, or alternative partitioning models.

### 10.6. Why Sharding by Time Is Risky

~~~text
observedAt ranges:
  Shard A: before August
  Shard B: August to October
  Shard C: October onward

Every new sample carries current timestamp:
  -> lands in newest range
  -> concentrates inserts onto a single shard/chunk.
~~~

Ingested timestamps typically **increase monotonically**. A ranged shard key on `observedAt` funnels almost all fresh inserts into one range. Chunk balancing can **relocate the hotspot** but cannot scatter identical live timestamps across multiple shards automatically. That is why MongoDB recommends metadata-based keys and **deprecated `timeField`-containing shard keys in 8.0**.

### 10.7. How Are Compound Shard Keys with `timeField` Viewed?

~~~javascript
{ "meta.deviceId": 1, observedAt: 1 }
~~~

In versions permitting it, this can target by device and time range, yet **every `timeField`-containing shard key**—including compound keys—falls under the MongoDB 8.0 deprecation warning. It is not limited to standalone `{observedAt: 1}`.

For legacy systems running such keys, plan upgrades and **metadata-only resharding** once running on a supporting version rather than trying to strip `timeField` directly from the config catalog.

### 10.8. Targeted Reads via Shard Keys

With shard key:

~~~javascript
{ "meta.deviceId": "hashed" }
~~~

the query:

~~~javascript
lab.telemetry_sharded.find({
  "meta.deviceId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
})
~~~

lets `mongos` hash `deviceId` and route directly to the owning shard. Filtering solely on `observedAt` without `deviceId` fans out across many or all shards, even though local `timeField` indexes still accelerate scans within each shard.

**Local indexes and shard routing are separate layers.** Having a `timeField` index does not let `mongos` target shards when the shard key is metadata.

## 11. Zone Sharding and the Balancer on Time-Series

The current MongoDB Manual states that **zone sharding is not supported for time-series collections**. The cluster balancer distributes sharded time-series data via cluster mechanisms; **you cannot use regular-collection zone rules to pin `EU` series strictly onto `EU` shards**.

### 11.1. A Data Residency Anti-Pattern

~~~text
Requirement:
  EU sensor data must reside solely on EU shards.

Developer:
  Creates time-series + zone ranges on meta.region = EU.

Problem:
  Time-series does not support zone sharding like regular sharded collections.
~~~

When data residency is a strict legal mandate, design **separate regional clusters**, ingestion-tier routing, compliant replication/retention policies, or a supported regular-collection model. Never rely on time-series zone sharding for legal compliance when the Manual states it is unsupported.

### 11.2. The Balancer Distributes Data, Not Single-Key Write Spikes

Even with hashed `meta.deviceId`, one hyper-active device concentrates write load on the shard owning its hash value. The balancer moves chunks/ranges to balance size/load across keys, but cannot split one shard key value into multiple keys.

When auditing balance:

- Inspect chunk and data distribution, not just total GB.
- Track write QPS/CPU/IOPS per shard, not merely whether the balancer is enabled.
- Identify any `deviceId` or metadata group dominating ingestion.
- Check whether queries include enough metadata keys for targeted routing.
- Measure distribution **at peak hours**, not just daily averages.

### 11.3. Never Touch `system.buckets` to Rebalance

Bucket storage has internal namespaces and invariants. Never edit metadata or move buckets via direct writes to `system.buckets.*`. Use supported sharding/resharding commands on the **logical time-series collection** for your version, avoiding unsupported admin commands.

### 11.4. Why Do Docs Say "Sharding Supported" Yet "Certain Sharding Commands Unsupported"?

Both statements are consistent:

- **Sharding the collection is supported since 5.1** for valid shard keys.
- **Specific low-level admin commands** may be unsupported on sharded time-series, and **resharding** became supported conditionally only in 8.0.10.

Never misread "sharding administration commands unsupported" as "time-series cannot be sharded" or "8.0.10 cannot reshard". Check the exact command and Limitations page for your version.

## 12. Resharding Time-Series: 7.0 vs. 8.0.10+

### 12.1. MongoDB 7.0: Time-Series Cannot Be Resharded

The **Time Series Collection Limitations v7.0** page states: **you cannot reshard a sharded time-series collection**, although you can **refine the shard key** under supported conditions.

This differs sharply from regular sharded collections, which have supported `reshardCollection` since MongoDB 5.0.

Example current key:

~~~javascript
{ "meta.site": 1 }
~~~

To **append a suffix**:

~~~javascript
{ "meta.site": 1, "meta.deviceId": 1 }
~~~

you can evaluate `refineCollectionShardKey` if version, indexes, and data model qualify; refining only **adds trailing fields**—it cannot switch to `{"meta.deviceId": "hashed"}`.

### 12.2. MongoDB 8.0.10+: Time-Series Resharding Supported

The current Manual and official tutorials state that **starting in 8.0.10**, you can reshard a time-series collection provided **all shards hosting the collection run 8.0.10 or newer**.

Illustrative key change:

~~~javascript
// Currently using site metadata key:
{ "meta.site": 1 }

// Switching to device metadata key:
{ "meta.deviceId": "hashed" }
~~~

Admin command shape:

~~~javascript
// SAMPLE DDL - RUN ONLY IN A LAB CLUSTER MEETING ALL PREREQUISITES.
db.adminCommand({
  reshardCollection: "ts288_lab.telemetry_sharded",
  key: { "meta.deviceId": "hashed" }
})
~~~

**Never execute this solely because one router's version string starts with `8.`.** Releases 8.0.0–8.0.9 do not meet the **8.0.10** requirement, and **all shards** must meet the patch floor. Resharding also depends on hashed-key eligibility, supporting indexes, shard capacity/distribution, and version-specific limits.

### 12.3. Changing the Shard Key Changes the Query Contract

Before resharding:

~~~javascript
// Key { "meta.site": 1 }:
lab.telemetry_sharded.find({ "meta.site": "HCM" })
// Targeted by site.
~~~

After resharding to `{"meta.deviceId": "hashed"}`:

~~~javascript
lab.telemetry_sharded.find({ "meta.site": "HCM" })
// Missing deviceId -> broadcasts across shards.

lab.telemetry_sharded.find({
  "meta.deviceId": "sensor-01",
  observedAt: { $gte: start, $lt: end }
})
// Equality on deviceId -> targeted.
~~~

This trades off **sensor-specific queries** against **site-wide queries**. Never reshard purely to balance writes while overlooking site-wide dashboards and global analytics.

### 12.4. Controlled Resharding Runbook

1. Verify **server versions and FCV** across the cluster; confirm all shards are **8.0.10+**.
2. Inventory API query shapes: device+time, site+time, global time, metadata updates/deletes.
3. Measure metadata cardinality/frequency; watch for hot devices or low-cardinality sites.
4. Verify indexes, metadata field presence, uniqueness rules, and `mongos` targeting.
5. Estimate **storage headroom**, I/O/network load, replication lag, cutover impact, and batch jobs.
6. Test resharding on staging with representative data/workload; observe latency and duration.
7. Prepare monitoring, maintenance windows, and a **version-appropriate rollback/recovery plan**.
8. Run in production per approved change management; never touch bucket internals directly.
9. Compare before/after metrics: ingest QPS per shard, p95/p99, range scans, storage balance, error rates, and app compatibility.

Never assume resharding is **zero-impact**: official docs detail clone, catch-up, and critical-section phases that consume resources and can affect writes depending on version.

### 12.5. `reshardCollection` Cannot Rename `timeField` or `metaField`

`reshardCollection` changes the **shard key**, not the time-series definition:

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "meta"
}
~~~

cannot become `timeField: "eventTime"`, `metaField: "tags"`. `timeField` and `metaField` are fixed **at collection creation**; changing their names or semantics requires creating a new collection and migrating data, not resharding.

## 13. Verifying Exact Version, FCV, and Collection Type Before Running Operations

A reliable workflow starts with an **environment inventory**, not testing `updateOne` blindly on live data.

### 13.1. Server Version

In `mongosh`:

~~~javascript
db.version()

db.adminCommand({ buildInfo: 1 })
~~~

`buildInfo.version` reflects the binary handling that command. On a sharded cluster, `mongos` reports its own version; to verify **"all shards ≥ 8.0.10"**, inspect **every shard replica set**, not just one router.

### 13.2. FCV During Upgrades

During upgrades, **`featureCompatibilityVersion`** may still sit at the older version. On a supporting node/endpoint with privileges:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

This command may require connecting directly to `mongod` with appropriate privileges rather than `mongos`, depending on branch; if your endpoint restricts it, verify FCV via your deployment's admin console or management API.

**Record:** binary version of every component, current FCV, connection path (`mongos` vs. standalone/replica set), and Java Driver version. A single `db.version()` line does not prove cluster-wide readiness.

### 13.3. Verify the Collection Is Truly Time-Series

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.getCollectionInfos({ name: "telemetry" })

lab.runCommand({
  listCollections: 1,
  filter: { name: "telemetry" }
})
~~~

Output typically includes `type: "timeseries"` alongside `options.timeseries.timeField`, `options.timeseries.metaField`, `granularity`, and `expireAfterSeconds` if collection-level TTL is enabled.

Never assume a collection named `telemetry` is time-series; a regular collection can hold identical timestamp and metadata fields. **Limitations follow collection `type`**, not field names.

### 13.4. Verify Shard Key and Topology

On a lab cluster via `mongos`:

~~~javascript
db.adminCommand({ hello: 1 })
sh.status()
~~~

Read the **actual shard key** from sharding metadata rather than guessing from secondary indexes:

~~~javascript
lab.telemetry_sharded.getIndexes()
~~~

`getIndexes()` lists defined indexes; **which key is the shard key** must be verified from sharding metadata. Having an index `{"meta.deviceId": "hashed"}` does not prove the collection is sharded on it.

### 13.5. Pre-Flight Checklist by Feature

| Feature | Minimum checks |
|---|---|
| Create time-series | MongoDB ≥ 5.0, `timeField` is BSON Date, metadata/retention defined. |
| Metadata `updateMany` | ≥ 5.1, filter/update metadata-only, no upsert, `multi`. |
| `deleteOne` or timestamp-based delete | ≥ 7.0, executed outside transactions. |
| Secondary index on measurement field | ≥ 6.0 and supported index type. |
| Metadata partial TTL | ≥ 7.0, metadata-only filter, index on `timeField`. |
| Shard time-series | ≥ 5.1, `mongos`, eligible shard key fields, supporting index. |
| Shard key with `timeField` | **Deprecated since 8.0**; avoid in new designs. |
| Reshard time-series | **All shards ≥ 8.0.10**, FCV and DDL prerequisites verified. |
| Transactional telemetry writes | **Unsupported** per Manual. |
| Transactional telemetry reads | Supported on eligible deployments; watch snapshot/DDL caveats. |

## 14. Indexes and Collection Options Also Have Version Milestones

A common mistake when discussing updates and sharding is assuming regular-collection indexes behave identically on time-series collections. In reality, time-series indexes optimize around buckets and carry dedicated constraints.

### 14.1. No Default `_id` Index

The MongoDB Manual states time-series collections **do not automatically create an `_id` index** like regular collections. Consequently:

- `find({_id: id})` does not automatically use an `_id_` index.
- Do not rely on `_id` to enforce **unique measurement identity**.
- Do not carry over "every collection has a default unique `_id`" assumptions to time-series.
- If strict `eventId` deduplication is required, maintain a regular collection with a unique index or an event ledger.

In MongoDB **8.3**, docs also note changes around `"_id_"` index naming/hinting; check branch-specific limitations when upgrading or downgrading with custom indexes.

### 14.2. Indexing Measurement Fields Since MongoDB 6.0

Starting in **6.0**, you can add supported **secondary indexes on measurement fields**:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.telemetry.createIndex({
  temperatureC: 1
})
~~~

This accelerates queries filtering by measured values. It **does not grant permission to update `temperatureC`**. Indexes accelerate reads; updates remain metadata-only.

MongoDB indexes time-series at the **bucket level**, leveraging measurement min/max bounds where applicable. Thus `explain` and index semantics differ from per-document regular indexes—measure real query plans rather than assuming "indexing `temperatureC` gives every sample a regular B-tree entry".

### 14.3. Default Compound Index Since MongoDB 6.3

Starting in **6.3**, MongoDB automatically creates a **default compound index on `metaField` and `timeField`** for eligible newly created time-series collections.

~~~javascript
lab.telemetry.getIndexes()
~~~

Inspect actual indexes. When collections created on older versions are upgraded, **do not assume new default indexes appear retroactively**. Collections without `metaField` also receive different default indexes.

### 14.4. Restricted Index Types

Per the Database Manual:

- **Unique indexes are unsupported** on time-series collections.
- Text indexes are unsupported.
- Multikey, sparse, and 2d indexes are restricted **to `metaField`**; do not assume any measurement field accepts any index type.
- TTL indexes follow dedicated rules: metadata partial TTL since 7.0, retention on `timeField`.

Therefore, never store data requiring a strict unique constraint on `(deviceId, observedAt)` in time-series assuming a unique compound index works like a regular collection.

### 14.5. Choosing Metadata to Optimize Buckets

Core rules:

1. `metaField` should **rarely or never change**.
2. Place frequently filtered identifiers in metadata when business semantics align.
3. Keep per-sample volatile fields (`lastHeartbeatAt`, `temperatureC`, `eventCounter`) out of metadata.
4. Avoid excessive distinct metadata combinations that leave buckets nearly empty.
5. When sharding on metadata, evaluate distribution/hot series alongside query routing together.

Decide this before creating the collection, because **`metaField` and `timeField` cannot be renamed after creation**.

### 14.6. `granularity` and Custom Bucket Size

`granularity` guides MongoDB's bucket time spans:

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "meta",
  granularity: "minutes"
}
~~~

Starting in **6.3**, `bucketMaxSpanSeconds` and `bucketRoundingSeconds` allow custom intervals; both must be **equal** and replace `granularity` per Manual rules.

When modifying granularity later, `collMod` permits **increasing bucket span**, not arbitrarily decreasing it on an existing collection. Never schedule a job to "shrink granularity from `hours` to `seconds`" without checking support; narrowing bucket spans typically requires creating a new collection and migrating.

### 14.7. Collection Type Cannot Be Converted In Place

A regular collection containing documents like:

~~~javascript
{ observedAt: new Date(), meta: { deviceId: "S1" }, temperatureC: 25 }
~~~

cannot become time-series by passing `timeseries` to `collMod`. Likewise, a time-series collection cannot convert directly into a regular collection via an option update. You must **create a new target collection of the desired type**, migrate data, and cut over clients.

### 14.8. Document and Bucket Limits

Current Limitations specify a **4 MB maximum document size in time-series** (unlike 16 MiB for regular documents). For buckets, the Manual documents maximum measurement counts/sizes and automatic sizing adjustments under high cardinality.

Never design **a single measurement** carrying multi-megabyte payloads assuming "MongoDB allows 16 MB documents". Store large images, videos, or raw logs externally and keep compact URIs/references or metrics/tags in time-series.

## 15. `$merge`, `$out`, and Migration / Correction

Time-series collections do not support all aggregation output stages the same way regular collections do—a frequent pitfall when **rebuilding** mis-ingested data.

### 15.1. `$merge` Cannot Write **Into** Time-Series

Per the current Manual, `$merge` cannot write documents from another collection **into a time-series collection**:

~~~javascript
// Not a valid output pipeline into a time-series collection.
db.source.aggregate([
  { $match: { sourceType: "sensor" } },
  {
    $merge: {
      into: "telemetry",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
~~~

Conceptually, `whenMatched: "replace"` relies on document upserts/replacements, whereas time-series prohibits arbitrary measurement updates.

### 15.2. `$merge` **From** Time-Series **Into a Regular Collection**

To materialize reports:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.telemetry.aggregate([
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        day: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 },
      avgTemperatureC: { $avg: "$temperatureC" }
    }
  },
  {
    $merge: {
      into: "daily_sensor_rollups",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
~~~

`daily_sensor_rollups` is a **regular collection**, not time-series; it maintains unique identity per `(deviceId, day)` via `_id`. This cleanly builds a **read model** for dashboards without mutating measurements.

At scale, avoid scanning full history every run: use incremental windows, checkpoints, and proper ingestion tracking. Because time-series **does not support change streams** per the current Manual, never design a time-series change stream as your sole mechanism for syncing read models.

### 15.3. `$out` Into Time-Series in Supporting Versions

The current Manual documents that `$out` can output **into a time-series collection** under specific conditions, whereas `$merge` cannot target time-series. This capability is **version-gated**; do not try it on 5.0/6.0 just because current docs list it.

`$out` replaces **the entire output collection** and touches DDL/indexes; never use it as a per-measurement update or small production correction job. For migrations, populate a fresh collection and verify measurement counts, indexes, TTL, and sharding/ownership before cutover.

### 15.4. Plan for Rebuilding a Collection with Proper Configuration

If you must change `timeField` or `metaField`:

~~~text
1. Define the new schema / timeField / metaField.
2. Create a NEW time-series collection with proper options.
3. Extract and transform data via controlled batch / aggregation tooling.
4. Insert in batches while verifying counts and retention.
5. Reconcile counts, min/max timestamps, per-device counts, and aggregates.
6. Build appropriate indexes, shard key, and TTL.
7. Cut over application reads and writes per plan.
8. Retain the old collection per rollback/retention policy; drop only when approved.
~~~

Never write directly to bucket internals or hack config-server metadata as a migration shortcut.

## 16. Java Sync Driver: Version-Aware Operations

The MongoDB Java Sync Driver exposes `createCollection()`, `insertOne()`, `updateOne()`, `updateMany()`, `deleteOne()`, `deleteMany()`, and `startSession()` identically to regular collections. **Those are client-side APIs**, not a guarantee that every server accepts every operation on time-series.

Examples below use a modern Java Sync Driver against `ts288_lab.telemetry`. Check exact class/package/API signatures in your driver version's documentation.

### 16.1. Creating a Time-Series Collection from Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.TimeSeriesOptions;
import org.bson.Document;

// mongoClient configured against MongoDB 5.0+.
MongoDatabase database = mongoClient.getDatabase("ts288_lab");

TimeSeriesOptions tsOptions = new TimeSeriesOptions("observedAt")
    .metaField("meta");

database.createCollection(
    "telemetry_java",
    new CreateCollectionOptions().timeSeriesOptions(tsOptions)
);

MongoCollection<Document> readings =
    database.getCollection("telemetry_java");
~~~

This is a **one-time collection creation** step; never call it per request. To configure `granularity` or `expireAfterSeconds`, check your driver's builder API; the server still validates options against your FCV and server version.

### 16.2. Inserting a Valid Measurement

~~~java
import java.util.Date;

Document measurement = new Document("observedAt", new Date())
    .append("meta", new Document("deviceId", "sensor-java-01")
        .append("site", "HCM")
        .append("kind", "temperature"))
    .append("temperatureC", 27.8)
    .append("humidityPct", 70);

readings.insertOne(measurement);
~~~

`observedAt` is persisted as a BSON Date (via Java `Date`), not a raw ISO string. Keep metadata stable rather than generating fresh metadata combinations on every heartbeat unnecessarily.

### 16.3. Querying by Metadata and Time Range

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import java.time.Instant;
import java.util.Date;

Date start = Date.from(Instant.parse("2026-11-14T08:00:00Z"));
Date end = Date.from(Instant.parse("2026-11-14T09:00:00Z"));

readings.find(Filters.and(
    Filters.eq("meta.deviceId", "sensor-java-01"),
    Filters.gte("observedAt", start),
    Filters.lt("observedAt", end)
))
.sort(Sorts.ascending("observedAt"))
.forEach(doc -> System.out.println(doc.toJson()));
~~~

This query is valid because filtering on `observedAt` is a restriction on **metadata updates**, not on **reads**. Developers often confuse "updates can only match `meta`" with "`find` cannot filter by timestamp"—they are completely separate operations.

### 16.4. Metadata-Only `updateMany()` Since 5.1

~~~java
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Updates;

MongoCollection<Document> telemetry =
    database.getCollection("telemetry");

UpdateResult result = telemetry.updateMany(
    Filters.eq("meta.deviceId", "sensor-01"),
    Updates.set("meta.ownerTeam", "iot-ops")
);

System.out.println("matched = " + result.getMatchedCount());
System.out.println("modified = " + result.getModifiedCount());
~~~

This is a **metadata-only multi-update**; never pass `upsert(true)`. If the filter is:

~~~java
// INVALID for metadata-only updates:
Filters.and(
    Filters.eq("meta.deviceId", "sensor-01"),
    Filters.gte("observedAt", start)
);
~~~

the timestamp predicate violates update rules. Likewise, `Updates.set("temperatureC", 29.0)` is rejected because it modifies a measurement field.

### 16.5. Timestamp-Based `deleteOne` Since 7.0

~~~java
import com.mongodb.client.result.DeleteResult;

// Use on MongoDB 7.0+ and strictly in the LAB.
DeleteResult deletion = telemetry.deleteOne(
    Filters.and(
        Filters.eq("meta.deviceId", "sensor-02"),
        Filters.eq(
            "observedAt",
            Date.from(Instant.parse("2026-11-14T08:02:00Z"))
        )
    )
);

System.out.println("deleted = " + deletion.getDeletedCount());
~~~

On 5.1–6.x, singleton deletes are unsupported; on 7.0+, this must still **run outside transactions**. If multiple measurements share `deviceId`/timestamp, `deleteOne` deletes **one matching document** without guaranteeing a specific `eventId` unless explicitly disambiguated.

### 16.6. Do Not Use Driver Transactions for Time-Series Writes

~~~java
import com.mongodb.client.ClientSession;

// NOT a valid write pattern:
try (ClientSession session = mongoClient.startSession()) {
    session.startTransaction();

    // Even though the Java Driver provides a session overload,
    // MongoDB server forbids time-series writes inside transactions.
    telemetry.insertOne(session, measurement);

    session.commitTransaction();
}
~~~

This is an **illustrative anti-pattern**, not runnable production code. When your application needs transactional guarantees between an ingestion record and a business document, write only to **regular collections** inside the transaction and route time-series writes asynchronously, or choose a different source-of-truth collection type.

### 16.7. Reading Time-Series Within a Session

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import java.util.ArrayList;
import java.util.List;

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

try (ClientSession session = mongoClient.startSession()) {
    List<Document> resultDocs = session.withTransaction(() -> {
        List<Document> docs = new ArrayList<>();
        telemetry.find(session,
            Filters.eq("meta.deviceId", "sensor-01")
        ).into(docs);
        return docs;
    }, options);

    resultDocs.forEach(doc -> System.out.println(doc.toJson()));
}
~~~

This **read-only** pattern requires a transaction-capable deployment and compatible Java Driver. Remember the snapshot isolation caveat regarding **concurrent drop/rename/re-create** noted in Section 8.4. Never open transactions just to read simple time ranges where standard read concerns suffice.

### 16.8. Never Handle Version Restriction Errors with Blind Retries

If the server returns "time-series only supports multi updates":

- **Do not** retry `updateOne` 10 times.
- **Do not** tweak `writeConcern` or pass `bypassDocumentValidation`.
- **Do not** cast collections to different Java types.
- **Fix the write** to use a valid `updateMany` if the change is genuinely metadata-only.
- If the business need is editing measurements, switch to a supported correction/migration workflow rather than swapping driver methods.

If a timestamp-based delete fails on server 6.0, having `deleteMany()` in Java Driver 5.x will never make server 6.0 accept that predicate.

## 17. When Data Is Wrong: Versioned Correction Designs

A real-world case: `sensor-01` reported `temperatureC: 28.7` at `08:01`, but post-calibration shows the true value was `29.0`. The application wants the corrected reading while preserving history.

### 17.1. Option 1 — Append-Only Correction Overlay

Keep raw measurements untouched in time-series. Create a **regular collection** `measurementCorrections`:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.measurementCorrections.createIndex(
  { logicalEventId: 1 },
  { unique: true }
)

lab.measurementCorrections.insertOne({
  _id: "CORR-01",
  logicalEventId: "sensor-01@2026-11-14T08:01:00Z",
  deviceId: "sensor-01",
  observedAt: ISODate("2026-11-14T08:01:00Z"),
  correctedTemperatureC: 29.0,
  correctedAt: new Date(),
  reason: "calibration",
  status: "APPROVED"
})
~~~

When reporting, join/merge raw measurements with overlays by `logicalEventId` to select the effective value. For multiple revisions, track `version`/`revision` and enforce a single active `APPROVED` record via transactions or CAS on the **regular collection**.

**Pros:** preserves raw time-series immutability, keeps full audit/rollback trails, and leverages unique indexes on regular collections. **Cons:** more complex readers/projections; requires overlay consistency and cache invalidation policies.

### 17.2. Option 2 — Delete + Insert Corrected Measurement (7.0+)

On MongoDB **7.0+**, outside transactions, you can delete the faulty measurement and insert the corrected one:

~~~javascript
// Illustrates intent only; do not run directly in production.
const target = {
  "meta.deviceId": "sensor-01",
  observedAt: ISODate("2026-11-14T08:01:00Z")
}

// Step A: deleteOne using 7.0+-supported filter.
lab.telemetry.deleteOne(target)

// Step B: insert corrected reading.
lab.telemetry.insertOne({
  observedAt: ISODate("2026-11-14T08:01:00Z"),
  meta: { deviceId: "sensor-01", site: "HCM", kind: "temperature" },
  temperatureC: 29.0,
  humidityPct: 72,
  quality: "corrected"
})
~~~

**Warning:** These are **two independent, non-atomic writes**, because time-series writes cannot run inside a multi-document transaction. If insert B fails after delete A, the sample is lost; if you insert before deleting, duplicates appear temporarily. Production therefore needs staging/backups, operation IDs, reconciliation, cutover controls, or preferably an overlay. Never present delete+insert as an atomic `updateOne`.

Furthermore, if two readings share `deviceId`/timestamp, `deleteOne` may remove the wrong copy. You need a distinguishing business identity or a more deterministic workflow.

### 17.3. Option 3 — Rebuild a New Time-Series Collection

When millions of samples carry wrong timezones or you need to change `timeField`, a safer migration workflow is:

~~~text
Source time-series, read-only snapshot/report
       |
       v
Transform & validate (UTC, meta, measurement format)
       |
       v
Destination time-series NEW
       |
       v
Validate counts / per-device time ranges / checksums / aggregates
       |
       v
Switch app reads/writes per cutover plan
       |
       v
Retain source per rollback/retention; drop only when approved
~~~

Account for **incoming writes** during migration via dual-write, buffering/queuing, ingestion pause, or controlled replay with deduplication. Never assume no new samples arrive while copying.

### 17.4. When Privacy Deletion Is Mandatory

When deleting data for a device or user upon request:

- On **5.1–6.x**, metadata-only filters can delete entire series, not arbitrary timestamps or measurement values.
- On **7.0+**, finer-grained filters work outside transactions.
- **TTL is not immediate**—it fits periodic retention only.
- Block further ingestion if an identity is revoked, purge derived read models, indexes, and backups per policy, and record PII-free audit trails.

Because physical cleanup and backup retention differ from logical deletion, never claim "`deleteMany` returned success so every copy/backup worldwide is erased".

## 18. Sharding and Metadata Updates: An Easy-to-Miss Intersection

A time-series collection sharded on:

~~~javascript
{ "meta.deviceId": "hashed" }
~~~

routes by `meta.deviceId`. If the application runs:

~~~javascript
lab.telemetry_sharded.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.ownerTeam": "iot-ops" } }
)
~~~

the filter includes shard-key equality and `ownerTeam` is outside the shard key—making this a much safer **metadata update** than changing `deviceId` itself. Still verify:

- **Server ≥ 5.1** and metadata-only `multi: true` semantics.
- Shard targeting via `explain`/metrics rather than assuming every `updateMany` hits one shard regardless of distribution.
- Matched measurement count—one series may span millions of samples.
- Impact of metadata edits on bucket layout and index writes.
- Never wrap metadata updates and `deviceCatalog` updates in a transaction.

### 18.1. Invalid: Modifying the Shard Key Value Like a Normal Field

~~~javascript
// Particularly risky because meta.deviceId is the shard key.
lab.telemetry_sharded.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.deviceId": "sensor-99" } }
)
~~~

Changing series identity and shard key simultaneously may be unsupported or require complex version-specific semantics. Moreover, historical queries on `deviceId` shift retroactively. Never rewrite `deviceId` on historical telemetry just to match a "new profile" if policy requires preserving original measurement provenance.

### 18.2. Can You Add Timestamp to the Update Query to Target a Chunk?

No:

~~~javascript
// Invalid under update restrictions:
lab.telemetry_sharded.updateMany(
  {
    "meta.deviceId": "sensor-01",
    observedAt: { $gte: start, $lt: end }
  },
  { $set: { "meta.site": "SGN" } }
)
~~~

Do not confuse **read routing** with **metadata update predicates**. In `find()`, `meta` + time range is optimal. In `updateMany()`, adding `timeField` to the filter violates metadata-only rules. When business logic requires changing metadata for **a specific time window**, use a correction overlay or migration—not an unsupported update query.

### 18.3. Queries Omitting Metadata Shard Keys Scatter-Gather

~~~javascript
lab.telemetry_sharded.find({
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
})
~~~

This queries all devices across a window, fanning out to **many or all shards** because `meta.deviceId` is absent. That is expected for global analytics, yet very expensive for single-device APIs.

To target a shard, include the validated metadata key:

~~~javascript
lab.telemetry_sharded.find({
  "meta.deviceId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
})
~~~

**A local timestamp index on each shard does not tell `mongos` which shard owns a device** when the metadata key is omitted from the filter.

## 19. Time-Series Verification Runbook for MongoDB Upgrades

A team upgrading **6.0 → 7.0 → 8.0/8.0.10+** may plan to adopt `deleteOne`, secondary indexes, resharding, or updated retention. Before changing anything, follow a verification runbook that protects data integrity.

### Step 1 — Inventory Features

Document:

| Item | Details to collect |
|---|---|
| Server binary versions | `mongos`, config servers, every shard replica set, secondaries. |
| FCV | State before and after rolling upgrades. |
| Time-series collections | Name, `timeField`, `metaField`, `granularity`, TTL, custom bucket options. |
| Shard keys | Key pattern, hashed/ranged, whether `timeField` is present. |
| Query shapes | Metadata/time filters, cluster-wide aggregations, singleton lookups. |
| Write shapes | Inserts, metadata updates, deletes, retry patterns, batches. |
| Indexes | Meta/time compound, measurement indexes, TTL, restricted index types. |
| Retention | Data age, partial TTL, privacy deletion deadlines. |
| Transactions | Any code attempting insert/update/delete on time-series inside a session transaction? |
| Integrations | Outboxes/queues, dashboards, rollups, correction ledgers, monitoring. |

### Step 2 — Cross-Check Compatibility Against Target Version

Example:

~~~text
Source 6.0:
  updateMany(meta-only)   -> yes
  deleteMany(meta-only)   -> yes
  deleteOne(sample)       -> no
  measurement index       -> yes
  sharded time-series     -> yes
  reshard time-series     -> no
  write transactions      -> no

Target 7.0:
  deleteOne(sample)       -> newly available
  deleteMany(time/value)  -> relaxed
  partial TTL metadata    -> yes
  write transactions      -> still no
  reshard time-series     -> still no

Target 8.0.10+:
  reshard time-series     -> conditional on all shards >= 8.0.10
  timeField shard key     -> deprecated since 8.0
  write transactions      -> still no
~~~

This is an **illustrative verification matrix**, never a substitute for patch/FCV release notes. During rolling upgrades with mixed versions, do not enable new features on live traffic until topology and FCV qualify.

### Step 3 — Verify Schema via `listCollections`

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

const collections = lab.getCollectionInfos({ name: "telemetry" })
printjson(collections)
~~~

Confirm the target is genuinely a time-series collection. Never run metadata updates or resharding against a regular collection or view sharing a similar name.

### Step 4 — Audit Counts and Time Ranges

~~~javascript
lab.telemetry.aggregate([
  {
    $group: {
      _id: "$meta.deviceId",
      sampleCount: { $sum: 1 },
      firstAt: { $min: "$observedAt" },
      lastAt: { $max: "$observedAt" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Record per-device or per-partition counts and min/max bounds before migration, then compare afterward using identical logic. On huge datasets, run during maintenance windows or use sampling/rollups to avoid overloading production.

### Step 5 — Verify Queries and Indexes

~~~javascript
lab.telemetry.getIndexes()

lab.telemetry.explain("executionStats").aggregate([
  {
    $match: {
      "meta.deviceId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T09:00:00Z")
      }
    }
  },
  { $sort: { observedAt: 1 } }
])
~~~

Inspect the plan for your version, paying attention to bucket filtering, unpack stages, and used indexes. Never confuse "update limits" with "timestamp `find` queries"—those are unrelated.

### Step 6 — Audit Write Logic Against Server Version

Search the codebase for:

~~~text
updateOne(timeSeries)
replaceOne(timeSeries)
updateMany(timeSeries with timeField filter)
upsert(timeSeries)
deleteOne(timeSeries)
deleteMany(timeSeries by value/time)
session.withTransaction(...timeSeries.insert/update/delete...)
bulkWrite(timeSeries with invalid operations)
$merge into timeSeries
~~~

Verify server version and data model for each call site. If one application release must support both 6.0 and 7.0 clusters, **never call `deleteOne` unconditionally** expecting 6.0 to accept it; gate by version, provide fallbacks, or upgrade uniformly first.

### Step 7 — Verify Sharding

If sharded:

- Confirm shard keys use only eligible **`metaField`/subfield/`timeField`** fields.
- If `timeField` is present, log the 8.0 deprecation warning and future migration plan.
- For resharding, confirm **all shards ≥ 8.0.10** plus FCV and DDL readiness.
- Inspect per-shard throughput to catch hot devices or low-cardinality keys.
- Never apply regular-collection zones to time-series, as the Manual states they are unsupported.
- Connect via `mongos` and official metadata; never touch bucket internals.

### Step 8 — Test Failure Cases in Staging

Verify in automated/staging tests:

- Valid metadata-only `updateMany` succeeds on supporting servers.
- Metadata-only `updateOne` is rejected.
- `updateMany` filtering on `timeField` is rejected.
- `updateMany` modifying measurement fields is rejected.
- `upsert: true` is rejected.
- Timestamp-based deletes run only on 7.0+.
- Transactional time-series writes are rejected; read-only transactions work on supported topologies.
- TTL expires with bucket-level lag rather than exact-second guarantees.
- Invalid shard keys are rejected in the lab cluster.

This is a **staging verification checklist**, not destructive commands to run on production. This lesson does not simulate live cluster telemetry.

### Step 9 — Roll Out and Monitor

Monitor:

- Ingestion rate, failed inserts, retries, and document sizes.
- Bucket catalog memory, WiredTiger cache, IOPS, and compression/storage ratios.
- Query latency p50/p95/p99 by device + time range.
- Metadata update matched/modified counts and latency.
- Delete/TTL throughput, backlogs, and retention lag.
- Per-shard data/write distribution, balancer health, and migrations if sharded.
- Invalid timestamps and missing meta identifiers.
- Corrections and duplicate event IDs in ledgers.

If errors spike post-upgrade, verify server versions, FCV, and driver behavior before altering schemas. Never downgrade blindly without respecting **time-series compatibility constraints** across branches.

## 20. Common Pitfalls

| Misconception | Consequence | Accurate understanding |
|---|---|---|
| "Time-series is a collection so `updateOne` works on any field." | Unsupported operation. | Metadata-only `updateMany` with strict rules since 5.1. |
| "If editing only `meta`, `updateOne` works." | Singleton updates remain prohibited. | Use `updateMany` with no document count limit. |
| "Filtering `timeField` is fine if updating only `meta`." | Violates metadata-only filter rule. | Match metadata only, or use a correction workflow. |
| "`$set: {temperatureC: ...}` works with multi-update." | Measurement updates are rejected. | Never edit measurements via time-series updates. |
| "Update pipelines behave like `$set` modifiers." | Unsupported update form. | Use standard update operator documents per Manual. |
| "Pass `upsert: true` to insert missing measurements." | Upserts are disallowed on time-series. | Use `insertOne`/`insertMany` with valid timestamps. |
| "`bulkWrite` bypasses time-series limits." | Inner operations are still validated. | Restrictions apply per individual write operation. |
| "MongoDB 5.0 can delete measurements by time." | Manual deletes are unsupported in 5.0. | Use TTL, range migrations, or upgrade. |
| "`deleteMany({observedAt: ...})` works on 6.0." | Filter references fields outside `metaField`. | Time-based deletes relaxed in 7.0. |
| "7.0 only allows `deleteMany`, not `deleteOne`." | Misses 7.0 improvements. | `deleteOne` is supported in 7.0+ outside transactions. |
| "7.0 allows deletes, so deletes work inside transactions." | Transactional time-series writes remain forbidden. | Separate delete predicate rules from transaction rules. |
| "TTL deletes each sample at exact expiration time." | Ignores buckets, granularity, and TTL monitor. | TTL lags and purges buckets once all samples expire. |
| "Partial TTL filters on `temperatureC`." | Partial TTL filters must use metadata. | Filter on `metaField` since 7.0. |
| "Time should always be the shard key." | Monotonic insert hotspot. | Prefer metadata keys; `timeField` deprecated since 8.0. |
| "Sharding works on `_id` or `temperatureC`." | Invalid shard key fields. | Only `metaField`, subfields, or `timeField`. |
| "Hashed `timeField` spreads timestamps evenly." | `timeField` cannot be hashed. | Hashing applies only to metadata. |
| "Only `timeField`-only keys are deprecated." | Overlooks compound keys. | Every shard key **containing** `timeField` warns since 8.0. |
| "Time-series supports zone sharding like regular collections." | Zone sharding is unsupported. | Use separate regional clusters/models for residency. |
| "Every 8.0 release can reshard time-series." | 8.0.0–8.0.9 lack support. | **8.0.10+ on all shards** required. |
| "7.0 has `refine` so it must have `reshard`." | Confuses two different operations. | 7.0 cannot reshard time-series; added in 8.0.10+. |
| "Resharding can rename `metaField`/`timeField`." | Confuses shard key with collection options. | Create a new collection and migrate to change them. |
| "New drivers unlock features on old servers." | Server rejects calls despite client APIs. | Gate features by server binary + FCV. |
| "Indexing `temperatureC` permits updating `temperatureC`." | Indexes do not alter write limits. | Indexes serve reads only. |
| "`_id` is unique like regular collections." | Logical measurement duplicates can occur. | Time-series lacks default `_id` / unique index support. |
| "Writing telemetry + `deviceCatalog` in a transaction is atomic." | Time-series writes forbidden in transactions. | Regular outbox/ledger + eventual ingestion. |
| "An outbox guarantees exactly-once time-series inserts." | Retries after dropped responses create duplicates. | Use stable `eventId` and reconciliation, or regular source of truth. |
| "Change streams work directly on time-series." | Unsupported per Manual. | Stream from outbox/ingestion or regular source collection. |
| "`$merge` can write into time-series." | Cannot target time-series with `$merge`. | `$merge` to regular collection; `$out` per version rules. |
| "Edit bucket internals to bypass limits." | Risks storage corruption. | Use logical APIs, migrations, or overlays only. |
| "`collMod` converts regular collections into time-series." | Collection type cannot convert in place. | Create a new collection and migrate. |

### 20.1. Five Operation Groups with Distinct Rules

This query:

~~~javascript
lab.telemetry.find({
  observedAt: { $gte: ISODate("2026-11-14T08:00:00Z") }
})
~~~

can **read** by `observedAt`. Switching `find` to `updateMany` with the exact same filter hits a **different rule set**—the metadata-only predicate requirement. Likewise, `deleteMany` by timestamp works in 7.0+ outside transactions, while `updateMany` by timestamp remains invalid.

**Reads / updates / deletes / transactions / shard DDL are five separate feature groups with independent version gates.**

### 20.2. Four Pre-Merge Code Review Questions

1. **Which server version and FCV are running?**
2. **Is the operation an update, delete, read, transaction, or sharding command?** Never cross-apply rules between groups.
3. **Do filters and modified fields touch metadata, `timeField`, or measurements?**
4. **On failure or timeout, do retries, idempotency, and reconciliation work cleanly without time-series transactions?**

## 21. Design Decision Matrix for Real-World Needs

| Requirement | Minimum version / conditions | Recommended solution |
|---|---|---|
| Record temperature every minute | Time-series since 5.0 | `insertOne`/`insertMany`, stable metadata. |
| Standardize site label across one device's samples | 5.1+, metadata-only update, multi, no upsert | `updateMany` on `meta.deviceId`. |
| Fix a single temperature sample | Time-series updates do not support directly | Correction overlay, or 7.0+ delete+insert (**non-atomic**). |
| Delete all samples of a sensor | 5.1+, metadata filter, multi | `deleteMany({"meta.deviceId": ...})`; block ingestion if permanent. |
| Delete one sample by device and timestamp | 7.0+, outside transactions | Selective `deleteOne`; verify logical identity. |
| 7-day retention | Time-series TTL | `expireAfterSeconds`, accounting for bucket lag. |
| Different retention per device class | 7.0+, partial TTL filter on `metaField` | Partial TTL index aligned with retention policy. |
| Atomic commit of raw telemetry and billing | Not directly supported | Change source of truth or use saga/outbox/ledger. |
| Consistent snapshot across multiple time-series reads | Transaction-capable deployment, no concurrent DDL | Read-only snapshot transaction when truly required. |
| Scale sensor writes across shards | Sharded time-series since 5.1 | Shard on `meta`/subfields with suitable cardinality and cadence. |
| Shard by measurement value | Unsupported | Choose metadata key or regular collection. |
| Shard key containing `timeField` | Older versions permit; deprecated 8.0+ | Avoid in new designs; plan resharding. |
| Strict zone-based data residency | Time-series zone sharding unsupported | Region-dedicated clusters/routing or alternative model. |
| Change a time-series shard key | 8.0.10+, all shards on version | Follow resharding runbook. |
| Append suffix to existing shard key | Version allowing `refine` | Use `refineCollectionShardKey` when prerequisites fit. |
| Rename `timeField` / `metaField` | Immutable after creation | Create a new collection and migrate. |
| Deduplicate by unique `eventId` | Unique indexes unsupported on time-series | Regular ingest ledger or regular source of truth. |
| Stream per-measurement changes to a queue | Time-series change streams unsupported | CDC from regular source or outbox ingestion stream. |
| Compute daily aggregates | Aggregate reads time-series; `$merge` into regular collection | Materialized read model with checkpoints and reconciliation. |

### 21.1. 30-Second Decision Flowchart

~~~text
Need to edit an already-stored measurement?
  -> Never call updateOne(timeSeries).
  -> Choose a correction overlay, or controlled delete+insert (7.0+).

Need to update metadata across a group?
  -> Server >= 5.1?
  -> Filter metadata-only? Update metadata-only?
  -> multi=true, no upsert? => updateMany.

Need to delete a measurement?
  -> 7.0+ and outside transactions => deleteOne.
  -> 5.1–6.x => metadata-only deleteMany only.
  -> Periodic age-out => TTL is usually better.

Need atomic writes of time-series + business document?
  -> Not directly supported.
  -> Use regular source of truth/outbox + eventual ingestion.

Need to shard or reshard?
  -> Shard since 5.1 on meta/subfield (or restricted timeField).
  -> timeField keys deprecated since 8.0.
  -> Reshard time-series from 8.0.10 when all shards qualify.
~~~

## 22. Practice Exercises and Answers

Exercises below assume a **time-series collection** with `timeField: "observedAt"`, `metaField: "meta"`, and metadata `{deviceId, site, kind}`; target MongoDB Server versions are specified per exercise. Destructive examples must run strictly in a **lab database** isolated from other fixtures.

### Exercise 1 — Earliest Version for Native Time-Series

**Prompt:** Can MongoDB 4.4 create a native time-series collection with `timeseries: {timeField: "observedAt"}`?

**Answer:** No. Native time-series collections were introduced in **MongoDB 5.0**. On 4.4 you can store timestamped measurements in a regular collection, without native bucketed time-series features.

### Exercise 2 — What Makes a Valid Measurement?

**Prompt:** In a time-series collection with `timeField: "observedAt"`, is this document valid?

~~~javascript
{
  observedAt: "2026-11-14T08:00:00Z",
  meta: { deviceId: "S1" },
  temperatureC: 25
}
~~~

**Answer:** `observedAt` is a **string**, not a **BSON Date**. It must be:

~~~javascript
{
  observedAt: ISODate("2026-11-14T08:00:00Z"),
  meta: { deviceId: "S1" },
  temperatureC: 25
}
~~~

`metaField` is optional in collection config, whereas `timeField` is mandatory and every measurement needs a valid Date timestamp.

### Exercise 3 — Metadata Update Since MongoDB 5.1

**Prompt:** On MongoDB 6.0, change `meta.site` for **all measurements of S1**. Write a valid update.

**Answer:**

~~~javascript
db.telemetry.updateMany(
  { "meta.deviceId": "S1" },
  { $set: { "meta.site": "SGN" } }
)
~~~

Metadata-only filter, metadata-only update, `multi: true`, no upsert. This updates metadata across all matching measurements, not just one sample.

### Exercise 4 — Why Is `updateOne` Still Forbidden?

**Prompt:** A sensor has only one measurement; can you run `updateOne({"meta.deviceId": "S1"}, {$set: {"meta.site": "SGN"}})`?

**Answer:** **No** under time-series update restrictions: the command must not cap updated document count. Having only 1 matching measurement at runtime **does not make `updateOne` valid**. Use `updateMany` when updating series metadata.

### Exercise 5 — Filtering `timeField` in an Update

**Prompt:** Since only metadata is modified, is the following valid?

~~~javascript
db.telemetry.updateMany(
  {
    "meta.deviceId": "S1",
    observedAt: { $gte: ISODate("2026-11-14T00:00:00Z") }
  },
  { $set: { "meta.site": "HN" } }
)
~~~

**Answer:** No. Time-series update filters may **match only `metaField`**, never timestamps—even when modifying metadata. Relabeling only a specific time window requires a controlled correction overlay or migration.

### Exercise 6 — Editing `temperatureC`

**Prompt:** On MongoDB 8.0, is `updateMany({"meta.deviceId": "S1"}, {$set: {temperatureC: 30}})` valid?

**Answer:** No under metadata-only update limits in the 8.0 Manual. Relaxed deletes in newer versions do not grant free-form measurement updates. Store corrections in a regular collection, or use a guarded 7.0+ delete+insert workflow.

### Exercise 7 — Upserting a Measurement

**Prompt:** On MongoDB 7.0, can you run `updateMany({meta...}, {$set: {...}}, {upsert: true})` to insert a missing sample?

**Answer:** No. Time-series updates do not support `upsert: true`. Use `insertOne`/`insertMany` for new measurements and handle `eventId`/dedup in the ingestion tier rather than regular-style upserts.

### Exercise 8 — Update Pipelines and Replacements

**Prompt:** Is passing pipeline `[{$set: {"meta.site": "SGN"}}]` or a replacement document to `updateMany` equivalent to a modifier update?

**Answer:** No. Current time-series update restrictions require **update operator expressions only**; update pipelines and replacements are invalid. Pass `{$set: {"meta.site": "SGN"}}` directly.

### Exercise 9 — Deleting on MongoDB 5.0

**Prompt:** Can you run `deleteMany({"meta.deviceId": "S1"})` on a time-series collection in MongoDB 5.0 to purge an old series?

**Answer:** No under initial 5.0 limits. 5.0 focused on inserts and reads; restricted manual updates/deletes arrived in **5.1**. Use TTL for retention, or plan an upgrade/migration for selective deletes.

### Exercise 10 — Deleting on MongoDB 6.0

**Prompt:** A MongoDB 6.0 collection needs to delete all of `S1` or delete measurements before `08:00`. Which of these two commands is allowed?

**Answer:**

~~~javascript
// Metadata-only filter: allowed on 6.0.
db.telemetry.deleteMany({ "meta.deviceId": "S1" })

// timeField filter: disallowed on 6.0.
db.telemetry.deleteMany({
  observedAt: { $lt: ISODate("2026-11-14T08:00:00Z") }
})
~~~

For time-based expiration, use TTL or upgrade to 7.0+ for flexible delete predicates.

### Exercise 11 — `deleteOne` Since MongoDB 7.0

**Prompt:** On MongoDB 7.0, delete one sample for `S2` at `08:02`. Write the query.

**Answer:**

~~~javascript
db.telemetry.deleteOne({
  "meta.deviceId": "sensor-02",
  observedAt: ISODate("2026-11-14T08:02:00Z")
})
~~~

Run **outside transactions**. If `deviceId`/timestamp alone does not uniquely identify one sample, add a logical discriminator or reconciliation—`deleteOne` removes one matching measurement.

### Exercise 12 — Deleting Inside a Transaction in 7.0+

**Prompt:** Since 7.0 relaxed deletes, can you run `session.startTransaction(); ts.deleteOne(...); session.commitTransaction()`?

**Answer:** No. **Time-series writes inside transactions remain unsupported**. Relaxed delete predicates apply **outside transactions** and do not change transaction boundaries.

### Exercise 13 — TTL and "Exact Midnight Deletion"

**Prompt:** A collection sets `expireAfterSeconds: 86400`; will a `00:00` sample vanish at exactly `00:00` the next day?

**Answer:** No. Time-series TTL operates by **bucket**; once every sample in a bucket expires, the background TTL monitor sweeps it in a subsequent pass (further delayed by load). TTL is not a hard real-time deletion deadline.

### Exercise 14 — Metadata Partial TTL

**Prompt:** On MongoDB 7.0, expire `meta.kind: "heartbeat"` after 1 day while keeping all other groups non-expiring. How?

**Answer:** Create a **partial TTL index** on `timeField` with a metadata-only `partialFilterExpression`:

~~~javascript
db.telemetry.createIndex(
  { observedAt: 1 },
  {
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "meta.kind": "heartbeat"
    }
  }
)
~~~

Works when collection/index setup qualifies; before production, verify interaction with any collection-level TTL and existing indexes.

### Exercise 15 — Transactional Read/Write Matrix

**Prompt:** On MongoDB 8.0, can you read time-series via `find` inside a snapshot transaction? Can you insert into time-series inside that transaction?

**Answer:** **Reads work** on transaction-capable deployments, subject to concurrent drop/rename snapshot caveats. **Writes fail**, including `insertOne`, `updateMany`, and `deleteOne`.

### Exercise 16 — Transaction with a Billing Record

**Prompt:** A telemetry sample and a billing record must commit/abort together. A developer wraps both inserts inside `session.withTransaction`. Is this valid?

**Answer:** No, time-series inserts cannot join multi-document transactions. If all-or-nothing atomicity is mandatory, persist **source-of-truth events in a regular collection** alongside billing inside the transaction, then build an asynchronous time-series projection with verification/dedup. If eventual consistency suffices, use an outbox/state machine/repair worker—never claim the sample committed atomically with billing.

### Exercise 17 — Deduplicating via `_id`

**Prompt:** Ingestion assigns `_id = "sensor-01@2026-11-14T08:00Z"` and inserts twice. Can you rely on MongoDB time-series creating a unique `_id_` index to block duplicates?

**Answer:** No. Time-series **lacks a default unique `_id` index and does not support unique indexes** per the Manual. Use an event ledger/unique key in a regular collection or an alternative source of truth when strict exactly-once is required.

### Exercise 18 — Sharding on `temperatureC`

**Prompt:** Can you shard time-series on `{temperatureC: 1}` because queries often scan readings above 40 °C?

**Answer:** No. Time-series shard keys may include only eligible **`metaField`/subfields/`timeField`**. You can add a secondary index on `temperatureC` from 6.0+ for read selectivity, yet it cannot serve as the shard key.

### Exercise 19 — Sharding on Hashed `timeField`

**Prompt:** Is `{observedAt: "hashed"}` valid on a 7.0 time-series collection?

**Answer:** No. When `timeField` appears in a shard key, it must be **ranged** and **trailing**. Only `metaField` or its subfields may be hashed where eligible.

### Exercise 20 — When Does a Key with `timeField` Become Deprecated?

**Prompt:** `{"meta.deviceId": 1, observedAt: 1}` is a compound key. Does MongoDB 8.0 mark it deprecated, or only standalone `{observedAt: 1}`?

**Answer:** It is deprecated. Since **MongoDB 8.0**, all shard keys **containing `timeField`**—even compound keys led by `metaField`—are deprecated. Prefer metadata-based keys and plan resharding once on 8.0.10+.

### Exercise 21 — Minimum Version for Time-Series Sharding

**Prompt:** A team on MongoDB 5.0 wants to run `sh.shardCollection("db.telemetry", {"meta.deviceId": "hashed"})` on a native time-series collection. Will it work?

**Answer:** No; **sharded time-series requires MongoDB 5.1+**, alongside a sharded cluster and required prerequisites—not just creating an index.

### Exercise 22 — MongoDB 7.0 and Resharding

**Prompt:** A collection sharded on `{"meta.site": 1}` must switch completely to `{"meta.deviceId": "hashed"}`. Can MongoDB 7.0 run `reshardCollection` on time-series?

**Answer:** No. Time-series v7.0 docs state **resharding** is unsupported, though **refining** a shard key works under conditions. Switching key structure requires upgrading to 8.0.10+ or migrating.

### Exercise 23 — 8.0.9 vs. 8.0.10

**Prompt:** `mongos` is 8.0.10, while one shard remains on 8.0.9. Can you reshard time-series right away?

**Answer:** No—it fails the requirement that **all shards run 8.0.10+**. Finish upgrading all components and FCV per docs, verify topology, and prepare capacity/rollback before resharding.

### Exercise 24 — Zone Sharding

**Prompt:** Every sample has `meta.country: "DE"`; compliance mandates keeping all `DE` data on `EU` shards. Can time-series zone sharding enforce this like regular collections?

**Answer:** The MongoDB Manual states **time-series does not support zone sharding**. Use region-dedicated clusters, ingestion routing, or another architecture satisfying data residency rather than an unsupported zone policy.

### Exercise 25 — Hot Device on Hashed Key

**Prompt:** Sharded on `{"meta.deviceId": "hashed"}`, yet 70% of measurements come from `S1`, creating a hot shard. Why?

**Answer:** A single `deviceId: "S1"` hashes deterministically to one value; all writes for `S1` hit the shard owning that range. Hashing distributes **across many `deviceId`s**, never splitting one hot device across multiple keys. Revisit workload, metadata design, partitioning, or scaling strategy.

### Exercise 26 — Time-Range Reads on Sharded Time-Series

**Prompt:** Shard key is `{"meta.deviceId": "hashed"}`. Does `find({observedAt: {$gte: start, $lt: end}})` target a single shard?

**Answer:** Unlikely—it normally scatters across many or all shards because `meta.deviceId` is absent. Include `deviceId` equality for single-device APIs; for all-device dashboards, multi-shard reads are natural and should be backed by appropriate queries or rollups.

### Exercise 27 — Metadata Update Over a Time Range

**Prompt:** `sensor-01` moved from `HCM` to `DN` at `10:00`. A developer wants `updateMany({"meta.deviceId": "sensor-01", observedAt: {$lt: changeAt}}, {$set: {"meta.site": "HCM"}})` on 8.0. Valid?

**Answer:** No, because including `timeField` in a metadata update filter is invalid. Record **point-in-time site** via stable staged metadata, emit new samples with updated metadata, or use a correction/snapshot policy to preserve history instead of bulk-editing time ranges.

### Exercise 28 — Choosing Where to Store Device State

**Prompt:** A service constantly updates `device.currentStatus`, `lastHeartbeatAt`, and `version` with CAS. Should these fields live inside every measurement's `metaField` and be updated via `updateMany` every second?

**Answer:** Poor design. `metaField` should remain stable; running `updateMany` across many measurements causes massive churn. Keep current state in a **regular `deviceState` collection** using `updateOne`/CAS, and keep append-only history in time-series.

### Exercise 29 — Do Secondary Indexes Unlock Updates?

**Prompt:** On MongoDB 6.0 after creating `{temperatureC: 1}`, a developer claims `updateMany` can now modify `temperatureC`. Correct?

**Answer:** False. Secondary indexes accelerate **queries** on measurement fields; updates remain restricted to filtering and modifying **`metaField`**. Indexes do not expand CRUD capabilities.

### Exercise 30 — Converting Regular Collection to Time-Series

**Prompt:** Can you run `collMod` to enable `timeseries: {...}` on an existing regular collection holding 10 million measurements?

**Answer:** No—collection types cannot convert in place. Create a new time-series collection with proper `timeField`/`metaField`/retention, migrate in batches, verify counts and aggregates, and coordinate cutover/concurrent writes.

### Exercise 31 — Shrinking `granularity` from `hours` to `seconds`

**Prompt:** A time-series collection uses `granularity: "hours"`. Can `collMod` switch it to `"seconds"` immediately to shrink bucket spans?

**Answer:** Per the Manual, you may **increase** bucket time span under supported rules, not **arbitrarily decrease** it on an existing collection. Narrowing bucket spans requires creating a new collection and migrating.

### Exercise 32 — Tiered TTL Retention

**Prompt:** Standard sensors need 7 days, critical sensors 30 days. Collection-level `expireAfterSeconds: 604800` is active; can partial TTL extend critical sensors to 30 days?

**Answer:** Never rely on partial TTL to override a shorter collection-level TTL that expires everything after 7 days. Partial TTL can only **shorten** retention for a subset; set collection-level TTL to 30 days (with shorter partial TTLs), split collections per tier, or adjust your model.

### Exercise 33 — Snapshot Reads During Drop / Re-Create

**Prompt:** A long-running read transaction reads time-series while another job drops and re-creates the same namespace with different granularity. Is full snapshot isolation guaranteed?

**Answer:** No. The MongoDB Manual explicitly warns about **concurrent drop/rename and re-create with different granularity**. Coordinate DDL/migration windows, snapshots, and reader lifetimes rather than assuming invariance across namespace replacement.

### Exercise 34 — Deduplication Worker Crashing Mid-Step

**Prompt:** A worker inserts into time-series successfully, crashes before setting `ingestLedger.state = WRITTEN`, and retries on restart. Does a unique `eventId` on the regular ledger prevent duplicate measurements in time-series?

**Answer:** No. Unique `eventId` on the **regular ledger** guards only the ledger row; the time-series insert happens outside that transaction with no matching unique constraint. You need detection/reconciliation and an appropriate source of truth—where strict exactly-once is mandatory, keep unique event identity in a regular collection and project to time-series.

### Exercise 35 — Complete Upgrade Plan

**Prompt:** A MongoDB 6.0 system uses time-series shard key `{"meta.site": 1, observedAt: 1}`. The team wants to delete bad readings by timestamp, eliminate the 8.0 deprecated key, reshard to `{"meta.deviceId": "hashed"}`, and keep 14-day retention. Outline the major steps.

**Suggested Answer:**

1. Inventory binary/FCV versions across **all shards**, `mongos`/config nodes, data, indexes, TTL, and query shapes.
2. Upgrade systematically across supported releases, gating `deleteOne`/timestamp deletes until 7.0+.
3. Validate 7.0+ deletes in staging, **outside transactions**, with backups and reconciliation.
4. Note the 8.0 deprecation warning for shard keys containing `timeField`.
5. Evaluate `deviceId` cardinality/cadence, hot devices, and metadata+time query targeting.
6. Verify **all shards ≥ 8.0.10** and FCV/DDL readiness; dry-run resharding in staging and budget I/O, capacity, and cutover.
7. Configure `expireAfterSeconds = 14 days` accounting for bucket lag (not a hard deadline).
8. Cut over production per runbook, monitoring counts, query latency, write balance, error rates, and backups/rollbacks.

A complete answer distinguishes **7.0 deletes** from **8.0.10 resharding** while keeping in mind that **time-series write transactions remain unsupported**.

## 23. Developer Quick Reference

### 23.1. Debugging Update Errors

| Symptom | First check |
|---|---|
| `updateOne` rejected | Time-series requires **multi-update**; use valid `updateMany` (5.1+). |
| `updateMany` rejected despite modifying only `meta` | Does the filter accidentally include `observedAt`, `_id`, or measurement fields? |
| `updateMany` reports invalid update | Does the update touch fields outside `metaField`, or use a pipeline/replacement? |
| `upsert: true` fails | Upserts are unsupported on time-series updates; insert measurements explicitly. |
| `bulkWrite` reports unsupported update | Inner operations remain bound by time-series restrictions. |
| `updateMany` runs very slowly | Overly broad metadata filter touching many buckets/samples? Hot meta or routing issue? |

### 23.2. Debugging Delete Errors

| Symptom | First check |
|---|---|
| `deleteOne` fails on 6.0 | Singleton time-series deletes require 7.0+. |
| Timestamp `deleteMany` fails on 6.0 | 5.1–6.x matches `metaField` only. |
| Metadata `deleteMany` works on 6.0 | Valid under filter/multi rules; verify data scope. |
| Timestamp `deleteOne` works on 7.0 | Supported outside transactions; does not imply uniqueness. |
| Delete in transaction fails on 8.x | Transactional time-series writes remain unsupported. |
| TTL has not removed newly expired sample | Wait for the full bucket to expire and TTL monitor pass; not necessarily a bug. |

### 23.3. Debugging Sharding Errors

| Symptom | First check |
|---|---|
| `shardCollection` fails on 5.0 time-series | Sharded time-series starts in 5.1. |
| `{observedAt: "hashed"}` rejected | `timeField` must be ranged and trailing when used. |
| `{temperatureC: 1}` rejected | Measurement fields are ineligible as shard keys. |
| Deprecation warning in 8.0 | Shard key contains `timeField` (even compound). |
| `reshardCollection` fails on 7.0 | Time-series resharding is unsupported in 7.0. |
| Reshard fails with one shard on 8.0.9 | Requires all shards hosting the collection ≥ 8.0.10. |
| Zone policy has no effect | Zone sharding is unsupported for time-series. |
| Time-range queries scatter-gather | Shard key is metadata-based; query omitted metadata key. |

### 23.4. A Generally Sound Architecture Pattern

~~~text
              IoT device
                  |
                  v
            Ingestion API
                  |
           +------+------+
           |             |
           v             v
    Regular ledger    Queue / outbox
    unique eventId        |
    ingest status         v
           |         Async worker
           |             |
           +-------------+
                         v
                 Time-series collection
                 - timeField
                 - stable metaField
                 - TTL retention
                 - shard by meta if needed
                         |
                         v
                 Aggregation / read model
                         |
                   +-----+------+
                   |            |
                Dashboard   Corrections overlay
                            (regular collection)
~~~

This is an **optional architectural pattern**, not a MongoDB requirement forcing every app to build queues/ledgers. It fits when separating a **strong-ID/idempotent source** from a **time-series analytics tier** where eventual projection is acceptable. Simpler metrics pipelines tolerant of occasional packet loss can be much leaner.

## 24. Official MongoDB Documentation by Version

Consult the links below for exact syntax, constraints, and branch-level changes. Whenever a `/manual/` link points to **current**, select your exact older MongoDB version if applicable.

### Core Time-Series and Limitations

1. [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — native time-series introduced in 5.0, bucketed storage, and data characteristics.
2. [About Time Series Data / Bucketing](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/) — metadata grouping, buckets, insert/read patterns, and compression.
3. [Time Series Collection Limitations — Current Manual](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — metadata-only updates, transactions, indexes, sharding, unsupported features.
4. [Time Series Collection Limitations — MongoDB 7.0](https://www.mongodb.com/docs/v7.0/core/timeseries/timeseries-limitations/) — explicit 7.0 reshard and transaction limits.
5. [Time Series Collection Limitations — MongoDB 8.0](https://www.mongodb.com/docs/v8.0/core/timeseries/timeseries-limitations/) — update rules, shard key deprecation, and patch-release prerequisites.
6. [Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/) — `timeField`/`metaField`/`granularity` and examples.
7. [Time Series Collection Considerations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-considerations/) — stable metadata selection and modeling.
8. [Best Practices for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/) — metadata sharding and query patterns.

### CRUD, TTL, Indexes, and Aggregation

9. [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — time-series `updateMany` since 5.1, metadata-only restrictions.
10. [MongoDB 7.0 Release Notes — Time Series Deletes](https://www.mongodb.com/docs/v7.0/release-notes/7.0/) — relaxed `delete`/`deleteOne`/`deleteMany` in 7.0.
11. [`db.collection.deleteOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteOne/) — single-document delete semantics and version constraints.
12. [`db.collection.deleteMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/) — multi-document delete semantics.
13. [Set up Automatic Removal (TTL) for Time Series](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — retention, bucket expiration, and TTL lag.
14. [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) — secondary indexes from 6.0, default compound index from 6.3, partial TTL from 7.0.
15. [Time Series Change Streams — Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — unsupported change streams and related features.
16. [`$merge` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — time-series disallowed as `$merge` target.
17. [`$out` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/out/) — output collection semantics and version-dependent time-series target support.
18. [MongoDB Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot read behavior and caveats.

### Sharding, Versioning, and Java Driver

19. [Shard a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-shard-collection/) — sharding from 5.1, supporting indexes, 8.0.10+ resharding rules.
20. [`shardCollection` Command](https://www.mongodb.com/docs/manual/reference/command/shardCollection/) — eligible time-series shard key fields and deprecation timeline.
21. [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — requirements, costs, and resharding workflow.
22. [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/) — appending suffixes under supported conditions.
23. [Sharded Cluster Query Router](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/) — targeted vs. broadcast routing.
24. [MongoDB Java Sync Driver — Time Series Collections](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/time-series/) — `TimeSeriesOptions`, `CreateCollectionOptions`, and queries.
25. [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — `updateMany`/`UpdateResult` and builders.
26. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession` and regular-collection transactions; time-series write limits.
27. [Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/) — upgrade/FCV feature gates.
28. [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/manual/reference/versioning/) — branch selection and patch-level compatibility.

## 25. Conclusion

**A time-series collection is not a regular collection with a special timestamp index.** It optimizes storage via buckets and carries distinct support boundaries. When designing applications, clearly separate **measurements**, **metadata**, and **timestamps**, then verify **server version, FCV, operation type, and topology**.

Three takeaways to remember:

1. **Updates:** Since **5.1**, supported updates take the form **`updateMany` matching and modifying `metaField` only**, using update operators, with **no upsert**. Never try editing measurements or `timeField` via `updateOne` or `updateMany` like a regular collection. **Deletes** follow a different timeline: 5.1–6.x allows metadata-only multi-deletes, whereas **7.0+** relaxes delete predicates and singleton deletes.
2. **Transactions:** MongoDB **forbids writing to time-series inside multi-document transactions**, though reads inside transactions work with snapshot caveats. When telemetry must coordinate with business state, design **regular sources of truth/ledgers, outboxes, correction overlays, and reconciliation** rather than expecting non-existent atomic time-series guarantees.
3. **Sharding:** Since **5.1**, time-series collections can be sharded on `metaField`/subfields (or restricted `timeField`); `timeField` shard keys are **deprecated since 8.0**, zone sharding is unsupported, and **time-series resharding requires 8.0.10+ across all shards**.

In production, far more valuable than hunting for "tricks" around constraints is **picking the right collection type for your business invariants**, building idempotent ingestion, correction, and retention pipelines, validating shard keys against real access patterns, and consulting documentation for the **exact MongoDB version you actually run**.
