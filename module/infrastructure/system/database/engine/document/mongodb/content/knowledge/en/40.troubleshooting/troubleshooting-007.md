# Aggregation Out-of-Memory, Disk Spills, and Per-Stage Limits in MongoDB

## 1. When a Report Works Locally Yet Fails in Production

A rental-listing platform stores tens of millions of view events. To generate a report, a developer writes an aggregation:

~~~javascript
db.listingViews.aggregate([
  { $match: { createdAt: { $gte: ISODate("2026-11-01") } } },
  { $sort: { createdAt: -1 } },
  {
    $group: {
      _id: "$tenantId",
      allEvents: { $push: "$$ROOT" }
    }
  }
]);
~~~

Over 1,000 events it runs fine. At production scale, the query hits **`ExceededMemoryLimit`**, **`QueryExceededMemoryLimitNoDiskUseAllowed`**, BSON size limits, timeouts, or severe slowdowns from writing intermediate data to disk. Temporarily slapping on **`allowDiskUse: true`** may help it finish in some cases, yet in others it still fails and puts I/O pressure across the entire cluster.

The problem is not simply a lack of RAM. An aggregation query may:

- Require **blocking state** for sorting, grouping, or windowing.
- Be able to **spill** state to temporary files when permitted.
- Use an **accumulator or stage that does not support spilling**.
- Produce **an oversized BSON output document**.
- Generate too many stages or exceed version-specific total memory limits.
- Spike network/disk usage and push other APIs past their SLOs even if the query succeeds.

This is a troubleshooting lesson: pinpoint the true source of resource pressure, reshape the query when needed, and verify business results remain intact after optimization.

### Objectives

After this lesson, you will be able to:

1. Distinguish streaming stages from blocking stages.
2. Understand the 100 MB per-stage limit, 16 MiB BSON output document limit, 1,000-stage cap, accumulator-specific limits, and per-operation limits by server version.
3. Use `allowDiskUse` and understand `allowDiskUseByDefault` starting in MongoDB 6.0.
4. Analyze the memory behavior of `$sort`, `$group`, `$facet`, `$bucket`, `$bucketAuto`, `$sortByCount`, `$setWindowFields`, `$lookup`, and `$graphLookup`.
5. Diagnose issues via `explain`, `usedDisk`, profiler/logs, `serverStatus`, and disk telemetry.
6. Apply `$match`, projections, indexes, top-K, bounded arrays, and partitioning without altering business semantics.
7. Design appropriate `maxTimeMS`, `batchSize`, and report-job concurrency limits.
8. Practice in `mongosh` with a small synthetic dataset without deliberately exhausting server RAM.
9. Build a complete runbook: detect, isolate, mitigate, fix, verify, and prevent.

> **Scope and warning:** MongoDB adjusts certain limits and execution details across versions. This lesson clearly separates features from **6.0** and **9.0** while relying on official MongoDB Manual documentation. All write examples target only the lab database **`mongo_agg_memory_lab_439`**, collection **`listing_views_439`**. Never inflate production payloads or record counts just to trigger spilling; never alter server parameters prefixed with **`internalQuery`** on your own.

## 2. Thinking in Terms of Pipeline Data Flow

~~~text
             MongoDB collection
                    |
                 $match       Filter
                    |
                $project      Trim fields
                    |
                  $group      Accumulate state
                    |
                   $sort      Order results
                    |
                  $limit      Bound output
                    |
              Result cursor
                    |
                Application
~~~

Each stage receives documents and emits documents to the next stage. The MongoDB optimizer can push down or reorder steps when valid, so **written pipeline order does not always match physical execution order**. Only `explain` shows the chosen execution strategy.

### 2.1. Streaming Stages

A stage that processes input and emits output incrementally:

- **`$match`** filters documents.
- **`$project`/`$unset`** strips unnecessary fields.
- **`$set`/`$addFields`** computes new fields.
- **`$unwind`** expands arrays into multiple documents.
- **`$limit`** stops once enough documents pass per semantics.

Streaming does not mean zero memory. An expression building a huge array still consumes RAM; `$unwind` can dramatically inflate downstream volume.

### 2.2. Blocking Stages

Blocking stages typically must buffer substantial input or state before emitting valid output:

- **`$sort`** without an index providing the sort order.
- **`$group`** accumulating per group key.
- **`$bucketAuto`** analyzing value distributions.
- **`$sortByCount`** combining grouping and sorting.
- **`$setWindowFields`** buffering by partition/order/window.

~~~text
Input 10 million documents
        |
   $sort without index
        |
   Buffer / external sort
        |
  Ordered output cursor
~~~

### 2.3. Input Volume Differs from Memory Usage

Scanning **30 GB of input** does not mean using 30 GB of RAM. A streaming `$match` can read and discard most documents. Conversely, 1 million group keys or a single giant `$push` array can hit memory limits even with smaller input.

Do not equate:

~~~text
Input bytes != peak RAM != spilled disk bytes
            != result BSON size != total operation memory
~~~

## 3. Key Limits and Their Scope

### 3.1. 100 MB Threshold for Many Memory-Intensive Stages

The MongoDB Manual documents memory restrictions typically around **100 MB** for tracked stage state. A spill-capable stage can write temporary files to disk if `allowDiskUse` is active.

**Do not** assume that:

- The entire pipeline shares a single 100 MB cap.
- Every stage uses the exact same mechanism.
- Enabling `allowDiskUse` grants infinite memory.
- Every accumulator inside a spillable stage can spill.

### 3.2. Each Output BSON Document Is Capped at 16 MiB

~~~text
Cursor:
  A: 5 KiB        valid
  B: 8 KiB        valid
  C: 19 MiB       document size error
~~~

Total cursor bytes can exceed 16 MiB because it streams **multiple documents**. The constraint applies **per document**. Documentation notes that certain intermediate aggregation documents may exceed 16 MiB, yet every final returned document must obey the BSON document limit.

If `$group` uses `allRows:{$push:"$$ROOT"}` and produces **one document with a massive array**, it can hit the accumulator limit or BSON output limit. No amount of RAM turns a 19 MiB BSON document into valid output.

### 3.3. Maximum of 1,000 Stages

MongoDB enforces a limit of **1,000 stages** in an aggregation pipeline, evaluated pre/post parsing per documentation. If a code generator emits 1,200 `$set`/`$project` stages, adding RAM or `allowDiskUse` will not fix it.

### 3.4. Accumulator-Specific Limits

Per the MongoDB Manual, **`$push`** has its own memory restriction (default 100 MiB governed by the corresponding parameter) and **cannot spill accumulated arrays** the way other `$group` state can. **`$addToSet`** can likewise build an accumulated object exceeding non-spilling limits.

~~~text
$group:
  hash/group state -> can spill under eligible conditions
  $push huge array -> does not auto-spill; can still fail
~~~

Never raise `internalQueryMaxPushBytes` in production to accommodate an unbounded array.

### 3.5. Per-Operation Limit Starting in MongoDB 9.0

MongoDB documentation **from 9.0 onward** describes a total tracked memory limit for a single query operation, separate from per-stage limits. It covers blocking stages, certain expressions, and buffering execution stages.

The documented default is **the greater of 1 GiB or 20% of memory available to the server process**, set at server startup. This limit is **distinct** from the ~100 MB per-stage restriction and does not alter how individual stages spill. **Do not assume these metrics and server parameters exist on MongoDB 6/7/8.**

### 3.6. Identification Table

| Limit | Target | Does `allowDiskUse` resolve it? |
| --- | --- | --- |
| Memory-intensive stage ~100 MB | Stage state | Possibly, if spill-capable |
| Oversized `$push` and object accumulators | Single accumulator | In some cases, **no** |
| `$facet` creating document >100 MB | Output of facet stage | **No** |
| Single output BSON document >16 MiB | Final document | **No** |
| Pipeline >1,000 stages | Stage count | **No** |
| Per-operation memory from 9.0 | Total tracked memory | Not entirely; separate cap still applies |
| Out of temporary disk space | Physical storage | **No**; flag does not create disk |

## 4. `allowDiskUse` and `allowDiskUseByDefault`

### 4.1. Calling in `mongosh`

~~~javascript
const lab = db.getSiblingDB("mongo_agg_memory_lab_439");
const events = lab.getCollection("listing_views_439");

const pipeline = [
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$tenantId",
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1, _id: 1 } }
];

printjson(events.aggregate(pipeline, {
  allowDiskUse: true,
  maxTimeMS: 15000,
  comment: "lesson439-spill-aware"
}).toArray());
~~~

**`allowDiskUse:true` permits spilling; it does not force spilling.** If a stage stays within memory limits, the query executes entirely in RAM.

### 4.2. Starting in MongoDB 6.0

The **`allowDiskUseByDefault`** parameter sets the default spill behavior for eligible stages. Individual commands can override it:

| Server default | Command | Behavior |
| --- | --- | --- |
| `false` | Omitted | Does not allow spill by default |
| `false` | `allowDiskUse:true` | Allows spill |
| `true` | Omitted | Allows spill by default |
| `true` | `allowDiskUse:false` | Forbids spill for this command |

Never guess a deployment's default. On versions prior to 6.0, check the version-specific option docs rather than applying newer parameters.

### 4.3. Reading the Parameter If Permitted

~~~javascript
// Observe only; do not modify configuration:
printjson(
  db.getSiblingDB("admin").runCommand({
    getParameter: 1,
    allowDiskUseByDefault: 1
  })
);
~~~

On managed MongoDB/Atlas, privileges to view or adjust parameters differ from self-managed clusters.

### 4.4. Temporary Files Have a Cost

When spilling, `mongod` writes and reads temporary files under storage associated with **`dbPath/_tmp`** per deployment. Temp files are normally managed over the operation's lifecycle.

Never manually delete files currently held by the server. One report spilling 3 GB across 10 concurrent runs generates tens of GB of temporary storage and I/O pressure alongside application traffic.

### 4.5. The Flag Is Not an Optimization

~~~text
Spill disallowed:
  stage exceeds memory budget -> error

Spill allowed:
  stage exceeds memory budget -> writes/reads disk
  may finish, yet latency spikes
~~~

With strict API p99 targets, an aggregation spilling gigabytes to disk can still constitute a performance incident even without memory errors.

## 5. Per-Stage Limits: Overview Table

| Stage | Risk | Strategy |
| --- | --- | --- |
| **`$match`** | Scanning too many docs | Use selective predicates and indexes |
| **`$project/$set`** | Heavy expressions or large docs/arrays | Narrow width, avoid building huge arrays |
| **`$unwind`** | Multiplying downstream row count | Control fan-out before `$sort`/`$group` |
| **`$sort`** | Blocking sort state | Index, filter, top-K; can spill |
| **`$group`** | Too many group keys | Lower cardinality, keep accumulators small; state can spill |
| **`$push/$addToSet`** | Single massive accumulated array/set | Do not rely on spill to save it |
| **`$bucket`** | Group/accumulator state | Bounded buckets, sum/count; can spill |
| **`$bucketAuto`** | Automatic bucket distribution | Shrink input, bound buckets; can spill |
| **`$sortByCount`** | Group + frequency sort | Match early, top-K; can spill |
| **`$setWindowFields`** | Partition/order/window buffers | Bounded window/index; can spill |
| **`$facet`** | One document holding large arrays | 100 MB stage limit **non-spilling**, 16 MiB final BSON |
| **`$lookup`** | Fan-out/joined arrays | Foreign index, reduce matches, bound output |
| **`$graphLookup`** | Recursive traversal and result arrays | `maxDepth`/filter; check version and spill rules |
| **`$search`** | Dedicated search engine | Not bound by `mongod` 100 MB stage cap; has its own limits |
| **`$merge/$out`** | Writes to collections, side effects | Never use as an unplanned temp spill trick |

**Note on `$graphLookup`:** Newer MongoDB Manuals note it can write temporary files past 100 MB under eligible conditions; older driver/doc notes stated otherwise. Always verify against the **exact MongoDB server version and manual**, rather than assuming one rule across all releases.

## 6. `$sort`: Memory Error or Missing Index?

### 6.1. Full-Set Sort

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1 } }
]
~~~

Without an index providing the exact ordering, the server must sort a large set. Across millions of docs, sort state and spill I/O grow massive.

### 6.2. Leveraging an Index

~~~javascript
db.listingViews.createIndex({
  tenantId: 1,
  createdAt: -1
});
~~~

With equality on `tenantId` and descending sort on `createdAt`, this compound index can satisfy both filter and ordering. It still depends on optimizer choices, collations, preceding stages, and selectivity. **Verify with `explain`** rather than assuming an index guarantees zero `SORT` stage.

### 6.3. Top-K

When only the 20 latest events are needed:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
]
~~~

MongoDB can **coalesce `$sort` and `$limit`** into a top-K sort when no intervening stage alters cardinality, buffering roughly N items instead of the whole sorted set.

### 6.4. Misplaced `$limit` Breaks Business Logic

If a report needs total views this month, putting **`$limit:20` before `$group`** counts only 20 events. Conversely, putting `$limit` after group+sort is valid when returning the top 20 listings by **total views**.

~~~javascript
[
  { $match: { createdAt: { $gte: start } } },
  { $group: { _id: "$listingId", views: { $sum: 1 } } },
  { $sort: { views: -1, _id: 1 } },
  { $limit: 20 }
]
~~~

### 6.5. `$unwind` Between Sort and Limit

~~~javascript
[
  { $sort: { score: -1 } },
  { $unwind: "$tags" },
  { $limit: 20 }
]
~~~

Do not assume top-K coalescing applies as when sort and limit sit adjacent: `$unwind` expands output cardinality.

### 6.6. Stable Sort for Pagination

Many events share the same `createdAt`; sorting by `createdAt` alone yields unstable ordering. Add an `_id` tie-breaker and design keyset pagination/indexes accordingly. Avoid deep `skip` offsets on large datasets.

## 7. `$group`: Stage State and Accumulators Differ

### 7.1. Group Key Cardinality

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      views: { $sum: 1 }
    }
  }
]
~~~

With only 20 tenants, group state stays tiny even when reading tens of millions of events. Grouping by unique `eventId`, however, creates millions of groups and heavy memory pressure.

### 7.2. Anti-Pattern: `$push $$ROOT`

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      allRows: { $push: "$$ROOT" }
    }
  }
]
~~~

A large tenant builds an unbounded accumulated array. Even if `$group` stage state can spill, **the `$push` array has its own non-spilling limit**, and the output document still hits 16 MiB. `allowDiskUse:true` is not enough.

### 7.3. Keep Only What Is Needed

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      maxCreatedAt: { $max: "$createdAt" },
      totalDurationMs: { $sum: "$durationMs" }
    }
  }
]
~~~

Do not pull every raw document into an array only to measure array length in application code when MongoDB can sum directly.

### 7.4. Top N Per Group

On servers supporting `$topN`:

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      recent: {
        $topN: {
          n: 5,
          sortBy: { createdAt: -1 },
          output: {
            listingId: "$listingId",
            createdAt: "$createdAt"
          }
        }
      }
    }
  }
]
~~~

Retains only 5 entries per tenant instead of `allRows`. Still check memory/output limits if each entry is large or group count is huge.

### 7.5. `$first`/`$last` Optimization

Some pipelines sorting and grouping on the same key with only `$first`/`$last` can leverage an index to find boundary elements. Never replace `$max` with `$first` without guaranteed ordering: `$group` **does not guarantee input/output sort order**.

## 8. `$facet`: `allowDiskUse` Cannot Save It

### 8.1. Why Does Output Grow Huge?

`$facet` returns **one document** containing multiple arrays, one per sub-pipeline:

~~~javascript
[
  {
    $facet: {
      recent: [
        { $sort: { createdAt: -1 } }
      ],
      count: [
        { $count: "n" }
      ]
    }
  }
]
~~~

If `recent` retains all events, the output array balloons.

### 8.2. Two Separate Limits

The MongoDB Manual confirms:

- The document built by **`$facet`** is capped at **100 MB**; **`$facet` does not spill** and `allowDiskUse` does not change this cap.
- The final result BSON document must stay under **16 MiB**. A 30 MiB facet output avoids the 100 MB stage cap yet still fails to return.

### 8.3. Reasonably Bounded Facets

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  {
    $facet: {
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 10 },
        {
          $project: {
            _id: 1,
            listingId: 1,
            createdAt: 1
          }
        }
      ],
      byCity: [
        { $group: { _id: "$cityCode", count: { $sum: 1 } } },
        { $sort: { count: -1 } },
        { $limit: 10 }
      ],
      total: [{ $count: "n" }]
    }
  }
]
~~~

### 8.4. Index Before Facet

If `$facet` is the first stage, documentation notes it cannot use indexes for filtering the way a preceding `$match` does. Place index-friendly filters ahead of `$facet` **when business semantics allow**.

### 8.5. When Many Rows Are Needed, Split the API

An API design can separate:

- `GET /events` using cursor/keyset pagination.
- `GET /events/facets` returning only compact aggregates.

Never cram full row lists and summaries into one facet document. Splitting endpoints adds a round-trip yet avoids output caps and simplifies resource budgeting.

## 9. `$setWindowFields`: Partitions and Windows Can Be Heavy

Example computing running view counts per listing:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  {
    $setWindowFields: {
      partitionBy: "$listingId",
      sortBy: { createdAt: 1 },
      output: {
        runningViews: {
          $sum: 1,
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]
~~~

Sources of pressure:

- Huge partitions.
- High partition counts.
- Sorting by the order key.
- Unbounded windows or heavy accumulators.
- Every input event emits an output row.

Per MongoDB aggregation limits, `$setWindowFields` can spill when policy permits, yet still carries its own restrictions.

If the business only needs total views per listing, use `$group` to emit one row per listing rather than computing `runningViews` on every event and discarding the rest.

### 9.1. Bounded Windows

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$listingId",
    sortBy: { createdAt: 1 },
    output: {
      last10Events: {
        $sum: 1,
        window: { documents: [-9, "current"] }
      }
    }
  }
}
~~~

A window of **10 rows** differs from a window of **10 minutes**. Never alter semantics just to save RAM.

### 9.2. Candidate Index

~~~javascript
{ tenantId: 1, listingId: 1, createdAt: 1 }
~~~

may assist certain partition/sort shapes, though actual index utilization must be verified via `explain` for your version and pipeline.

## 10. `$bucket`, `$bucketAuto`, and `$sortByCount`

### 10.1. Fixed Buckets

~~~javascript
[
  {
    $bucket: {
      groupBy: "$durationMs",
      boundaries: [0, 1000, 5000, 30000, 600000],
      default: "other",
      output: {
        n: { $sum: 1 },
        totalMs: { $sum: "$durationMs" }
      }
    }
  }
]
~~~

With a few buckets and count/sum accumulators, state stays compact. Adding `allRows:{$push:"$$ROOT"}` per bucket reintroduces array growth.

### 10.2. Automatic Buckets

~~~javascript
[
  {
    $bucketAuto: {
      groupBy: "$durationMs",
      buckets: 5,
      output: {
        n: { $sum: 1 }
      }
    }
  }
]
~~~

MongoDB must analyze value distributions to derive bucket boundaries. `$bucketAuto` is listed among stages capable of spilling.

### 10.3. `$sortByCount`

~~~javascript
[
  { $sortByCount: "$cityCode" },
  { $limit: 10 }
]
~~~

Semantically equivalent to:

~~~javascript
[
  { $group: { _id: "$cityCode", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 10 }
]
~~~

Do not place `$limit` before grouping when you need **accurate top counts across the entire input**.

## 11. `$lookup` and `$graphLookup`: Fan-Out and Output Arrays

### 11.1. `$lookup` Fan-Out

~~~javascript
[
  {
    $lookup: {
      from: "listings",
      localField: "listingId",
      foreignField: "_id",
      as: "listing"
    }
  }
]
~~~

If one local row matches thousands of foreign documents, the `as` field becomes a huge array, breaching BSON size limits. Adding `$unwind` afterward dramatically inflates downstream row counts.

Example:

~~~text
1,000 input rows × 100 joined rows
  -> 100,000 rows after unwind
  -> heavier SORT/GROUP
~~~

Check the index on `foreignField`, join cardinality, filters, and data model. Equality joins on `_id` leverage the built-in `_id` index; joining on another field typically requires a dedicated index.

### 11.2. Do Not Arbitrarily `$limit` Foreign Joins

Capping foreign matches saves memory yet alters business semantics when **all** matching records are required. When only one latest record is needed, design explicit join keys/ordering/limits and test.

### 11.3. `$graphLookup`

`$graphLookup` traverses recursive relationships (category trees, hierarchies). Check:

- Is **`maxDepth`** set?
- Does **`restrictSearchWithMatch`** prune branches?
- Is the foreign `connectToField` properly indexed?
- Are there cycles or wide fan-out?
- Could the output array exceed the BSON limit?

~~~javascript
[
  {
    $graphLookup: {
      from: "lab_categories_439",
      startWith: "$parentCategoryId",
      connectFromField: "parentCategoryId",
      connectToField: "_id",
      as: "ancestors",
      maxDepth: 5,
      restrictSearchWithMatch: { active: true }
    }
  }
]
~~~

This snippet illustrates syntax only and needs the matching collection to run. **Memory/spill behavior follows the server manual for your running version**; do not rely on old driver docs to assume uniform behavior.

## 12. Stages with Special Characteristics

**`$unwind`:** not inherently a blocking memory consumer, yet multiplies cardinality for downstream stages. An event with 8 tags expands to 8 rows; a subsequent group count can **count 8×** if semantics are overlooked.

**`$project`/`$set`:** trimming fields shrinks transfer and state, though expressions building huge arrays still consume RAM. The optimizer can push down eligible projections.

**`$search`:** executes in a separate Atlas Search component and is not subject to `mongod`'s 100 MB stage RAM cap like `$sort`. It still has its own quotas, limits, and resource consumption.

**`$merge`/`$out`:** have collection-writing side effects. Never insert them as an ad-hoc "disk spill trick" in production without checking semantics, privileges, indexes, and target-data impact.

## 13. Classify Errors Before Fixing

### 13.1. `QueryExceededMemoryLimitNoDiskUseAllowed`

Investigate:

- Which stage hit the limit?
- What are the server default and command-level `allowDiskUse` settings?
- Can an indexed sort, smaller group state, or top-K solve it?
- If spilling is necessary, does storage have adequate headroom/IOPS?

### 13.2. `ExceededMemoryLimit` Even with `allowDiskUse:true`

Check:

- `$facet` 100 MB non-spilling cap.
- `$push`/`$addToSet` and their dedicated memory caps.
- Version-specific expression/per-operation total memory limits.
- Non-spilling stages.
- Oversized output or join fan-out.

### 13.3. BSON Object Too Large

Change the output shape: multiple cursor documents, pagination, or separate summaries rather than cramming everything into one array. Adding RAM never fixes 16 MiB.

### 13.4. Query Timeouts

Distinguish:

~~~text
MongoDB MaxTimeMSExpired
  != driver socket timeout
  != HTTP gateway timeout
  != memory limit error
~~~

A spilling query may run too slowly without throwing a memory error. Investigate at the exact failing layer.

### 13.5. Disk Full / I/O Contention

Check free disk/latency, active spill count, concurrency, backup/index jobs, and replication lag. Never manually delete `_tmp` while `mongod` is running.

### 13.6. Collect Incident Evidence

Record UTC timestamp, trace/query fingerprint, namespace, MongoDB version/FCV, PII-redacted `codeName`/message, `allowDiskUse`/`maxTimeMS`, `explain`, scan stats, `usedDisk`/spills if present, disk/CPU/RAM metrics, report job concurrency, and affected SLOs.

Never paste raw tenant documents or credentials into tickets.

## 14. `explain`: Pinpointing Which Stage Consumes Resources

In `mongosh`:

~~~javascript
const lab = db.getSiblingDB("mongo_agg_memory_lab_439");
const events = lab.getCollection("listing_views_439");

const pipeline = [
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$tenantId",
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1 } }
];

printjson(
  events.explain("executionStats").aggregate(
    pipeline,
    { allowDiskUse: true }
  )
);
~~~

Alternative syntax if required by a driver/helper:

~~~javascript
printjson(
  lab.runCommand({
    explain: {
      aggregate: "listing_views_439",
      pipeline,
      cursor: {},
      allowDiskUse: true,
      comment: "lesson439-explain"
    },
    verbosity: "executionStats"
  })
);
~~~

### 14.1. What to Look For in `explain`?

- **`winningPlan`**: `COLLSCAN`, `IXSCAN`, `FETCH`, `SORT`, etc.
- **`nReturned`**.
- **`totalDocsExamined`**.
- **`totalKeysExamined`**.
- **`executionTimeMillis`**.
- Indicators like **`usedDisk`, `spills`, `spilledDataStorageSize`, peak memory** when exposed by the version/engine.
- **`splitPipeline`/`merge`** details on sharded clusters.

Output shapes vary across MongoDB versions and classic vs. SBE engines. Never write a parser reading a single key and concluding no spill occurred if that key is absent.

### 14.2. Better Plans

~~~text
Before:
  COLLSCAN -> SORT millions -> GROUP -> LIMIT

After fixing per business requirements:
  MATCH with index -> GROUP by small key
  -> SORT small groups -> LIMIT
~~~

If the query only needs the 20 latest docs, an index-backed sort + limit makes sense. If it needs an accurate total count, never drop input early with `$limit`.

### 14.3. `explain` Is Not HTTP p99

Explain clarifies server execution, not driver pool wait/network, warm/cold cache states, concurrency, or gateway latency. Combine it with application telemetry.

## 15. `usedDisk`, Profiler, and Newer-Version Metrics

### 15.1. `usedDisk` Is an Actual Observation

The MongoDB Manual documents **`usedDisk`** in profiler/diagnostic logs when a stage actually writes temporary files due to memory restrictions. Simply passing **`allowDiskUse:true`** does not prove a spill happened.

If the profiler has been legitimately enabled by an administrator:

~~~javascript
const diagnostic = db.getSiblingDB(
  "mongo_agg_memory_lab_439"
);

printjson(
  diagnostic.getCollection("system.profile")
    .find(
      { "command.comment": "lesson439-spill-aware" },
      {
        ts: 1,
        millis: 1,
        usedDisk: 1,
        planSummary: 1,
        "command.comment": 1
      }
    )
    .sort({ ts: -1 })
    .limit(10)
    .toArray()
);
~~~

The profiler may be off by default; empty results are normal. Never enable high-volume profiling in production solely to capture `usedDisk`: it adds overhead and may log sensitive parameters.

### 15.2. `serverStatus` and MongoDB 9.0

MongoDB 9.0+ documentation lists query memory metrics such as:

~~~text
metrics.query.peakMemoryUsageOperation
metrics.query.operationsFailedDueToMemoryLimit
metrics.query.configuredMaxMemoryUsageBytesPerOperation
~~~

On supported deployments/versions with sufficient privileges:

~~~javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 });
printjson(status.metrics && status.metrics.query);
~~~

Not seeing these metrics on 6.x/7.x/8.x does not mean the server uses zero RAM.

### 15.3. Atlas Monitoring

Track query profiler/slow queries, CPU, free disk, disk IOPS/latency, cache pressure, replication lag, and per-shard hot spots. Atlas restricts server parameter changes differently from self-managed clusters.

### 15.4. `currentOp`

With proper privileges and topology awareness, `currentOp`/`$currentOp` reveals long-running operations. Never run `killOp` indiscriminately without knowing whether an operation is read-only or has side effects like `$merge`/`$out`.

## 16. Optimizing Pipelines at the Source

### 16.1. Filter Early

Prefer writing:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]
~~~

instead of sorting the entire collection and then matching. The optimizer can push `$match` down when valid; `explain` verifies pushdown.

### 16.2. Drop Unneeded Fields

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $project: { tenantId: 1, durationMs: 1 } },
  {
    $group: {
      _id: "$tenantId",
      totalDurationMs: { $sum: "$durationMs" }
    }
  }
]
~~~

Do not push HTML descriptions or huge payloads into `$push` if the report only needs a sum.

### 16.3. Group at the Right Granularity

Grouping by exact `createdAt` timestamps can produce nearly one group per event. If a report needs daily counts:

~~~javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$createdAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    views: { $sum: 1 }
  }
}
~~~

Group count drops sharply, though the business timezone must be confirmed; never alter daily boundary semantics solely to reduce memory.

### 16.4. Move Sort After Group When Only Top Groups Are Needed

Poor:

~~~javascript
[
  { $sort: { createdAt: -1 } },
  { $group: { _id: "$tenantId", views: { $sum: 1 } } },
  { $sort: { views: -1 } }
]
~~~

Better for counting:

~~~javascript
[
  { $group: { _id: "$tenantId", views: { $sum: 1 } } },
  { $sort: { views: -1, _id: 1 } }
]
~~~

If chronological `$first`/`$last` is required, do not remove the initial sort without preserving semantics.

### 16.5. Prevent Fan-Out

Unwinding tags before counting events counts each event multiple times. Check row counts before/after `$unwind`/`$lookup` and clarify whether the business unit is **event**, **tag**, or **listing**.

### 16.6. Never Alter Results Just to Win a Benchmark

A query that is 100× faster yet drops 99% of documents because `$limit` ran too early **is not a valid optimization**. Verify result accuracy and business invariants, not just `executionTimeMillis`.

## 17. Indexes: Avoid Sort Memory Whenever Possible

Example filtering by tenant and sorting by time:

~~~javascript
db.listingViews.createIndex({
  tenantId: 1,
  createdAt: -1,
  _id: 1
});
~~~

In the lab with `labTag`:

~~~javascript
events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "ix439_tag_tenant_date_id" }
);
~~~

An index helps only when aligned with filter/sort/query plan. A common heuristic is equality fields first, then sort, then range—not an absolute rule. Indexes also cost disk and write maintenance, so never build indexes en masse on a cluster already suffering spill-induced disk pressure.

Do not expect indexes to eliminate all memory costs of `$group`, window functions, `$facet`, or `$push`.

## 18. `maxTimeMS`, `batchSize`, and API Limits

### 18.1. `maxTimeMS`

~~~javascript
events.aggregate(pipeline, {
  allowDiskUse: true,
  maxTimeMS: 15000
});
~~~

Sets a server-side deadline per command/cursor semantics; it does not cap RAM and does not guarantee the query finishes within 15 seconds. Driver timeouts and HTTP gateway timeouts are separate layers.

### 18.2. `batchSize` Does Not Fix Blocking Stages

~~~javascript
events.aggregate(pipeline, {
  cursor: { batchSize: 100 }
});
~~~

Batch size governs how results stream to the client; **it does not make server-side `$sort`/`$group` use memory for only 100 records**.

### 18.3. User-Facing Limits

Every reporting endpoint/job should enforce:

- Tenant/security scope.
- Maximum time window.
- Maximum page size.
- Maximum concurrent jobs.
- Allowlisted query types/fields.
- Deadlines, retries, cancellation, and cleanup.
- Thresholds for switching to async reporting.

Never let clients submit arbitrary JSON pipelines with `allowDiskUse:true` and no quotas.

### 18.4. Async Reporting

~~~text
HTTP request -> validate/authenticate
             -> enqueue job
             -> worker with concurrency limit
             -> aggregation + bounded output
             -> status/report artifact
~~~

Background jobs need idempotency, authorization, storage retention, and dead-letter/error handling so retries never trigger an I/O storm.

## 19. Java Driver and Spring Data MongoDB

### 19.1. MongoDB Java Sync Driver

~~~java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;
import java.util.List;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> collection =
    database.getCollection("listing_views_439");

List<Document> stages = List.of(
    new Document("$match",
        new Document("labTag", "agg439-v1")
            .append("tenantId", "tenant-001")
    ),
    new Document("$group",
        new Document("_id", "$listingId")
            .append("views", new Document("$sum", 1))
    ),
    new Document("$sort", new Document("views", -1)),
    new Document("$limit", 10)
);

AggregateIterable<Document> query = collection
    .aggregate(stages)
    .allowDiskUse(true)
    .maxTime(15, TimeUnit.SECONDS)
    .batchSize(100);

try (MongoCursor<Document> cursor = query.iterator()) {
    while (cursor.hasNext()) {
        Document result = cursor.next();
        // Process bounded rows; do not keep unbounded data.
    }
}
~~~

Server success does not prove the Java heap can hold all results. Avoid `cursor.into(new ArrayList<>())` on unbounded streams.

### 19.2. Spring Data `MongoTemplate`

In compatible Spring Data versions, configure `AggregationOptions`:

~~~java
AggregationOptions options =
    AggregationOptions.builder()
        .allowDiskUse(true)
        .maxTime(Duration.ofSeconds(15))
        .build();

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is("tenant-001")
    ),
    Aggregation.group("listingId").count().as("views"),
    Aggregation.sort(Sort.Direction.DESC, "views"),
    Aggregation.limit(10)
).withOptions(options);
~~~

Check exact APIs/overloads for your Spring Data version. **`MongoTemplate` typed queries may map Java property paths to BSON field names; raw `mongosh`/driver calls must use actual stored names.**

### 19.3. Exception Handling

Never catch every `RuntimeException` and return an empty report:

~~~java
try {
    return executeReport();
} catch (Exception error) {
    return List.of();  // Wrong: confuses failure with empty data
}
~~~

Distinguish memory, timeout, network, permission, and invalid pipeline errors; record metrics, follow clear error/partial-result contracts, and bound retries.

## 20. Sharded Clusters: Spills Can Happen in Multiple Places

~~~text
                   mongos
                     |
           +---------+---------+
           |                   |
        Shard A             Shard B
      partial GROUP       partial GROUP
           |                   |
           +---------+---------+
                     |
                 MERGE/SORT
                     |
                   Client
~~~

The planner can split a pipeline between shards and a merging node depending on version and query. Memory pressure, network load, or disk spills can occur on individual shards or the merging node.

Monitor:

- Per-shard CPU/disk/network.
- Logged spill indicators.
- Read/write ops and hot shard keys.
- Query targeting/shard fan-out.
- Merge sort/group costs.
- Replication lag.

Adding shards will not make a **30 MiB BSON facet output** valid, and adding RAM will not fix an unbounded `$push` accumulator.

## 21. Temp Disk and Blast Radius

A spilling report may finish yet contend for disk I/O with CRUD APIs:

~~~text
Report $sort/$group spill
          |
          v
    Temporary disk I/O
          |
    +-----+-----+
    |           |
Report slow   API p99 spikes
~~~

Suppose 10 concurrent reports each spill several GB of temporary data. Even with free disk space remaining, **IOPS/latency** can breach budgets. Monitoring and rate limiting are essential.

Never delete temporary files managed by `mongod`. If a query must be stopped, verify whether it is read-only or `$merge`/`$out` and terminate per runbook and permissions.

## 22. `mongosh` Lab: Preparing 12,000 Synthetic Events

### 22.1. Safe Goal

The lab **does not try to generate >100 MB** to exhaust memory/disk. We use 12,000 documents to illustrate query shape, cardinality, `explain`, and output shape:

~~~text
Database: mongo_agg_memory_lab_439
Collection: listing_views_439
4 tenants × 3,000 events
3 city codes
Multiple listing IDs
eventType, durationMs, score, createdAt
~~~

**`allowDiskUse:true`** in the lab may not trigger `usedDisk`. That is not a lab bug.

### 22.2. Idempotent Seed Script

~~~javascript
(() => {
  const lab = db.getSiblingDB(
    "mongo_agg_memory_lab_439"
  );
  const events = lab.getCollection("listing_views_439");
  const tag = "agg439-v1";
  const n = 12000;
  const batchSize = 200;
  const start = Date.UTC(2026, 0, 1, 0, 0, 0);
  let ops = [];
  let batches = 0;

  function flush() {
    if (!ops.length) return;
    events.bulkWrite(ops, { ordered: false });
    ops = [];
    batches++;
  }

  for (let i = 0; i < n; i++) {
    const id = "agg439-event-"
      + String(i).padStart(6, "0");
    const tenantId = "tenant-"
      + String(1 + (i % 4)).padStart(3, "0");
    const listingId = tenantId + "-listing-"
      + String(1 + (i % 50)).padStart(3, "0");

    const doc = {
      _id: id,
      labTag: tag,
      tenantId,
      listingId,
      cityCode: ["HCM", "HN", "DN"][i % 3],
      eventType: [
        "VIEW", "BOOKMARK", "CONTACT", "VIEW"
      ][i % 4],
      createdAt: new Date(start + i * 216000),
      durationMs: 100 + (i % 18000),
      score: (i * 37) % 1000,
      note: "Synthetic event " + String(i % 100)
    };

    ops.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });
    if (ops.length >= batchSize) flush();
  }
  flush();

  printjson({
    count: events.countDocuments({ labTag: tag }),
    batches,
    sample: events.find(
      { labTag: tag },
      {
        _id: 1,
        tenantId: 1,
        listingId: 1,
        createdAt: 1
      }
    ).sort({ _id: 1 }).limit(3).toArray()
  });
})();
~~~

Expected result on a clean lab: **`count=12,000`**, **`batches=60`**.

The script does not drop the collection. The filter uses `_id + labTag`; if an unrelated document shares `_id` without `labTag`, upsert will hit a duplicate key error instead of overwriting it. Never delete unfamiliar data just to make a lab run.

## 23. Lab A — Small `$group` and Checking Distribution

~~~javascript
const lab = db.getSiblingDB("mongo_agg_memory_lab_439");
const events = lab.getCollection("listing_views_439");

printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$tenantId",
      events: { $sum: 1 },
      totalDurationMs: { $sum: "$durationMs" },
      latestAt: { $max: "$createdAt" }
    }
  },
  { $sort: { _id: 1 } }
], { maxTimeMS: 15000 }).toArray());
~~~

Each tenant has 3,000 records. **`events`** here counts all `eventType` values, not just `VIEW`; to count only `VIEW`, add an appropriate `eventType` match.

### 23.1. Bounded `$push` IDs in the Lab

~~~javascript
printjson(events.aggregate([
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      ids: { $push: "$_id" }
    }
  },
  {
    $project: {
      _id: 1,
      arrayCount: { $size: "$ids" }
    }
  }
], { allowDiskUse: false, maxTimeMS: 15000 }).toArray());
~~~

An array of 3,000 short IDs stays small. Lesson: across millions of documents or full `$$ROOT` objects, `$push` is unbounded and the BSON output will fail.

### 23.2. Better When You Only Need Counts

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $group: { _id: "$tenantId", n: { $sum: 1 } } }
]
~~~

Do not build an array and take `$size` just to count when you do not need the elements themselves.

## 24. Lab B — Full Sort vs. Top-K

~~~javascript
const fullSort = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $project: { _id: 1, listingId: 1, score: 1 } }
];

printjson(
  events.explain("executionStats")
    .aggregate(fullSort, { allowDiskUse: false })
);

const topK = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 20 },
  { $project: { _id: 1, listingId: 1, score: 1 } }
];

printjson(events.aggregate(topK, {
  allowDiskUse: false,
  maxTimeMS: 15000
}).toArray());
~~~

Top-K returns **20 events**; `fullSort` returns 3,000. Do not expect a spill on this small lab dataset.

### 24.1. Adding an Index

~~~javascript
events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    score: -1,
    _id: 1
  },
  { name: "ix439_tag_tenant_score_id" }
);
~~~

Re-run `explain` to see whether the plan uses the index. Depending on dataset/optimizer, never claim `IXSCAN` is guaranteed in every situation.

## 25. Lab C — Bounded Facet Output

~~~javascript
const facetPipeline = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  {
    $facet: {
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 5 },
        {
          $project: {
            _id: 1,
            listingId: 1,
            createdAt: 1
          }
        }
      ],
      byCity: [
        { $sortByCount: "$cityCode" }
      ],
      summary: [
        {
          $group: {
            _id: null,
            total: { $sum: 1 },
            avgDurationMs: { $avg: "$durationMs" }
          }
        }
      ]
    }
  }
];

printjson(events.aggregate(facetPipeline, {
  allowDiskUse: true,
  maxTimeMS: 15000
}).toArray());
~~~

`recent` has at most 5 rows, `byCity` at most 3 city buckets, and `summary` one document. Removing `$limit` and `$project` from `recent` would let output grow unboundedly and hit `$facet`/BSON caps on large datasets.

## 26. Lab D — Cardinality, `$dateTrunc`, and `$unwind`

### 26.1. Grouping by Exact Timestamp

~~~javascript
printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$createdAt",
      n: { $sum: 1 }
    }
  },
  { $count: "timestampGroups" }
], { maxTimeMS: 15000 }).toArray());
~~~

Since the seed assigns a unique timestamp per `i`, the expected group count is 12,000.

### 26.2. Grouping by Day

~~~javascript
printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "UTC"
        }
      },
      events: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
], { maxTimeMS: 15000 }).toArray());
~~~

Daily group count drops sharply. Note that grouping by `UTC` vs. `Asia/Ho_Chi_Minh` shifts day boundaries; follow the reporting contract.

### 26.3. Unwind Multiplies Rows

~~~javascript
printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $project: {
      syntheticTags: ["rental", "event", "analytics"]
    }
  },
  { $unwind: "$syntheticTags" },
  { $count: "rowsAfterUnwind" }
], { maxTimeMS: 15000 }).toArray());
~~~

Expands from 12,000 to **36,000 rows**. Sorting after unwind triples sort input; grouping counts per tenant after unwind counts each event three times.

## 27. Lab E — Bounded Window

~~~javascript
printjson(events.aggregate([
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001",
      listingId: "tenant-001-listing-001"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$listingId",
      sortBy: { createdAt: 1 },
      output: {
        recent10: {
          $sum: 1,
          window: { documents: [-9, "current"] }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      recent10: 1
    }
  },
  { $limit: 20 }
], {
  allowDiskUse: true,
  maxTimeMS: 15000
}).toArray());
~~~

`recent10` grows from 1 to 10 and stays at 10 once enough rows precede it; this represents the **10 most recent events** by sort order, not 10 minutes. You do not need to exhaust memory to observe the behavior.

## 28. Lab F — `explain` with `allowDiskUse`

~~~javascript
const p = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
];

printjson(
  events.explain("executionStats").aggregate(
    p, { allowDiskUse: false }
  )
);

printjson(
  events.explain("executionStats").aggregate(
    p, { allowDiskUse: true }
  )
);
~~~

Compare `winningPlan`, scanned/returned counts, and spill statistics (if exposed). Neither spilling is normal with small data or an index-backed sort. **Never insert millions of records just to force `usedDisk:true`.**

## 29. Production Incident Runbook

### Phase A — Impact

1. Identify failing APIs/reports/jobs and affected tenants.
2. Capture error code/`codeName`, UTC timestamp, and query fingerprint.
3. Measure p95/p99, error rate, and throughput.
4. Check free disk/latency, CPU/memory, and replication lag.
5. Verify MongoDB version/FCV and deployment topology.

### Phase B — Isolate

1. Inspect pipeline stages.
2. Review `explain`, `nReturned`, and `docsExamined`/`keysExamined`.
3. Check `usedDisk`/spills if available.
4. Distinguish memory limits, BSON size, stage count, timeouts, and disk errors.
5. Reproduce in staging with representative cardinality when needed.

### Phase C — Mitigate

- Lower concurrent report jobs.
- Pause non-critical scheduled reports per policy.
- Apply `maxTimeMS` and appropriate deadlines.
- Expand storage headroom if genuinely needed and approved.
- Never infinitely retry heavy timed-out queries.
- Never kill write operations without understanding side effects.

### Phase D — Fix

| Root cause | Remediation direction |
| --- | --- |
| Large in-memory `SORT` | Index, filter, top-K |
| `GROUP` with too many keys | Group at appropriate granularity |
| `GROUP` `$push` too large | Count/sum/top-N, stream details |
| Large `FACET` output | Bound branches, split endpoints |
| `LOOKUP` fan-out | Index foreign field, improve filter/join design |
| Unbounded `WINDOW` | Appropriate partition/window bounds |
| Spill-capable stage | `allowDiskUse` with disk/concurrency guardrails |
| Disk pressure | Rate limiting, query rewrite, capacity |
| 16 MiB output | Reshape into multiple documents |
| 1,000 stages | Simplify pipeline generator |

### Phase E — Verify

- Business results before/after are equivalent.
- `explain` shows reduced scan/sort/spill or cost within budget.
- Disk usage and latency return to safe levels.
- API p95/p99 and error rates meet SLOs.
- Replication/backups are healthy.
- Change record and rollback plan are complete.

### Phase F — Prevent

- Review pipelines whenever `$push`, `$facet`, `$lookup`, or unbounded windows appear.
- Manage index lifecycles.
- Test against production-representative datasets before release.
- Monitor slow queries and `usedDisk` against budgets.
- Enforce job concurrency caps and disk headroom alerts.
- Maintain verified incident ownership and runbooks.

## 30. Three Typical Case Studies

### 30.1. Case A — Sorting 50 Million Events

Query:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1 } }
]
~~~

Without an index, spilling causes high latency. Allowing spills lets it finish yet does not lower I/O. Candidate fixes are **index `{tenantId:1,createdAt:-1}`**, plus **`$limit:N`** if users only need the latest N items. Measure before/after without silently changing report semantics.

### 30.2. Case B — One Tenant with Huge Event Volume

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      allEvents: { $push: "$$ROOT" }
    }
  }
]
~~~

Fails due to an oversized array/output; even `allowDiskUse` can fail. If only count/latest are needed:

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      latest: { $max: "$createdAt" }
    }
  }
]
~~~

If all events are truly needed, use a dedicated cursor/pagination endpoint instead of one document carrying millions of items.

### 30.3. Case C — Facet Combining Summary and Full Data

A `$facet` returns a `recent` array of tens of thousands of full documents alongside a summary. It can exceed the 16 MiB BSON limit before reaching the 100 MB facet cap. Split into a paginated detail endpoint and a compact facet summary endpoint, accounting for consistency expectations if underlying data mutates continuously.

## 31. Monitoring and Guardrails

| Signal | Risk | Mitigation |
| --- | --- | --- |
| Rising `usedDisk`/spill bytes | Heavy external I/O | Query fingerprint, index, top-K |
| API p99 breaches SLO | Reports contending for resources | Throttle jobs |
| Rising memory limit errors | Release altered query shape | Roll back or disable feature |
| Free disk below policy | Temp files + data growth | Shed load and add capacity |
| Rising disk latency | I/O contention | Reduce concurrency |
| High `docsExamined`/`nReturned` | Excessive scanning | Index/filter |
| Single hot shard | Data/query skew | Per-shard analysis |
| Client heap OOM | Buffering entire cursor | Stream results |

An overnight batch report spilling to disk may be acceptable; do not alert merely on `usedDisk=true`. Alert when exceeding **resource budgets, failure rates, or SLOs**.

Keep metric labels bounded: query fingerprint, operation type, stage family, environment, release. Never turn millions of `_id` or `tenantId` values into metric labels.

## 32. Common Errors and Responses Table

| Symptom | What to verify |
| --- | --- |
| OOM with `allowDiskUse` false | Whether stage supports spilling, plus index/query alternatives |
| Still fails with `allowDiskUse` true | `$facet`, `$push`, BSON output, per-op limit |
| Disk usage spikes sharply | Concurrent spills, temp files, I/O |
| Slow sort | Index/limit/collation/query shape |
| `$group` produces millions of keys | Key cardinality/granularity |
| Single huge group | Unbounded array accumulators |
| Large `$facet` output | Whether branch outputs are bounded |
| `$lookup` produces huge row count | Foreign cardinality/index |
| `$graphLookup` too deep | `maxDepth`/cycles/branch fan-out |
| Heavy window stage | Partition/bounded window/index |
| `explain` shows no `usedDisk` | Small dataset, engine/version, no spill occurred |
| Client OOM | `cursor.toArray`/`into` loading all rows |
| Query timeout | Server/client/gateway deadlines |
| 1,000 stages | Generator emitting overly long pipeline |
| 16 MiB output error | Packing all rows into one document |
| Optimization broke report | `$limit`/`$unwind`/`$group` altered semantics |
| Report spikes CRUD p99 | Shared disk/CPU contention |

## 33. Checklist Before Enabling `allowDiskUse` in Production

1. Identified the failing stage.
2. Confirmed the error is not a non-spilling facet/push/BSON limit.
3. Verified server version and `allowDiskUseByDefault`.
4. Evaluated query rewrites, indexes, and top-K first.
5. Confirmed sufficient disk headroom and IOPS budget.
6. Enforced concurrency and rate limits.
7. Configured `maxTimeMS` and application deadlines.
8. Added monitoring for `usedDisk`, latency, errors, and disk.
9. Verified no unintended side effects from `$merge`/`$out`.
10. Prepared canary and rollback plans.

## 34. Practice Exercises

### Exercise 1 — Limit Types

Distinguish 100 MB stage memory, 16 MiB document size, 1,000 stages, and 9.0+ per-operation limits. Why don't they share the same fix?

### Exercise 2 — Streaming vs. Blocking

Compare `$match`/`$project` against `$sort`/`$group`. Why can `$unwind` cause downstream memory problems even though it is not a full blocking stage?

### Exercise 3 — `allowDiskUse`

Starting in MongoDB 6.0, compare `allowDiskUseByDefault` false/true and per-command overrides.

### Exercise 4 — No Spill Despite Being Allowed

A query specifies `allowDiskUse:true`, yet `explain` shows no `usedDisk`. What are valid reasons?

### Exercise 5 — Sort and Index

Design a compound index for equality on `tenantId`, descending `createdAt`, and `_id` tie-breaker.

### Exercise 6 — Top-K

Explain why `$sort+$limit` typically uses less memory than a full sort, and when the optimizer cannot coalesce them.

### Exercise 7 — Limit Semantics

Why does placing `$limit:100` before `$group` for a monthly total count produce wrong reports?

### Exercise 8 — Group Cardinality

Compare grouping by 20 tenants vs. grouping by 10 million `eventId` values.

### Exercise 9 — `$push $$ROOT`

A tenant has 3 million events. Why does `allowDiskUse` not guarantee the `allRows` group succeeds?

### Exercise 10 — Alternative Accumulators

When only total views and latest event are required, replace `$push` with `$sum`/`$max`.

### Exercise 11 — `$topN`

Write a query returning the 5 latest events per tenant. State the business trade-off vs. `allEvents`.

### Exercise 12 — Facet Limits

Distinguish the 100 MB non-spilling facet document limit from the 16 MiB final BSON document limit.

### Exercise 13 — Faceted API

Design a recent page and `byCity` summary without stuffing unbounded rows into one facet document.

### Exercise 14 — Facet Index

Why should `$match` precede `$facet` when possible? When does placing `$limit` before `$facet` distort total counts?

### Exercise 15 — Window

Compare running views per event vs. grouped total views per listing.

### Exercise 16 — Bounded Window

Distinguish the 10 most recent rows from the last 10 minutes in `$setWindowFields`.

### Exercise 17 — Bucket

Design `$bucket` for `durationMs` storing only counts; why not push `$$ROOT` into each bucket?

### Exercise 18 — BucketAuto

When are automatic bins useful? How do bucket count and data distribution affect execution?

### Exercise 19 — SortByCount

Write the `$group+$sort` equivalent. Why is placing `$limit` before counting wrong?

### Exercise 20 — Lookup

If one local row matches 100,000 foreign records, what memory/BSON risks arise?

### Exercise 21 — GraphLookup

Explain how to bound recursion with `maxDepth` and `restrictSearchWithMatch`. Why must you check the manual for your exact version?

### Exercise 22 — MongoDB 9.0

How do per-operation memory metrics/limits differ from stage memory restrictions? What must you not assume when the server is 8.0?

### Exercise 23 — Explain

Find `winningPlan`, `nReturned`, `docsExamined`, `keysExamined`, and `usedDisk`/spills per version. Which numbers reveal excessive scanning?

### Exercise 24 — Profiler

Read `usedDisk` and explain why high profiler levels add overhead and risk logging PII.

### Exercise 25 — Temp Disk

10 concurrent reports each spill an estimated 3 GB. Which monitoring and concurrency guardrails are mandatory?

### Exercise 26 — Client OOM

Why can a Java client calling `cursor.into(ArrayList)` run out of heap even when MongoDB Server completes the query?

### Exercise 27 — Timeouts

Distinguish `maxTimeMS`, socket timeout, and HTTP gateway timeout.

### Exercise 28 — Lab Seed

Run the 12,000-event lab; verify 4 tenants with 3,000 records each. Why does the script filter by `_id + labTag`?

### Exercise 29 — Lab Sort

Compare `fullSort`/`topK` and `explain` before/after indexing. Why shouldn't you demand `usedDisk=true`?

### Exercise 30 — Lab Group

Compare counting vs. `$push` IDs. If data grows from 3,000 to 3 million items, what changes?

### Exercise 31 — Lab Facet

Run the bounded facet and explain the risk if the `recent` branch drops `limit`/`project`.

### Exercise 32 — Lab Cardinality

Compare grouping by exact timestamp vs. grouping by UTC day. How can switching timezone to `Asia/Ho_Chi_Minh` alter results?

### Exercise 33 — Lab Unwind

From 12,000 events, each with three `syntheticTags`, how many rows exist after unwind? Why can counts after unwind be wrong?

### Exercise 34 — Sharded Cluster

One shard spills heavily while two other shards do not. Build a checklist covering shard targeting, hot keys, merges, and per-shard resource metrics.

### Exercise 35 — Read vs. Write

Why shouldn't you add `$out` or `$merge` as a production "spill" workaround without change management?

### Exercise 36 — Runbook

Write the impact/isolate/mitigate/fix/verify/prevent phases for a report tripling API p99.

### Exercise 37 — Comprehensive

A 50-million-event pipeline has `$lookup`, `$unwind`, `$sort`, `$group {$push:"$$ROOT"}`, and `$facet` holding `allRows`/summary. Even `allowDiskUse:true` fails. List every stage creating pressure, non-spilling constraints, how to redesign output/indexes/query, and a verification plan covering business results and p95/p99.

## 35. References

- MongoDB Manual — [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/): 100 MB, 16 MiB, 1,000 stages, `allowDiskUseByDefault`, and per-operation memory by version.
- MongoDB Manual — [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/).
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/).
- MongoDB Manual — [`$sort`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/): top-K and memory.
- MongoDB Manual — [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): blocking stage and accumulator limitations.
- MongoDB Manual — [`$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/): non-spill facet limit.
- MongoDB Manual — [`$bucket`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/).
- MongoDB Manual — [`$bucketAuto`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucketAuto/).
- MongoDB Manual — [`$sortByCount`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortByCount/).
- MongoDB Manual — [`$setWindowFields`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/).
- MongoDB Manual — [`$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/).
- MongoDB Manual — [`$graphLookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/graphLookup/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/).
- MongoDB Manual — [`aggregate` command](https://www.mongodb.com/docs/manual/reference/command/aggregate/).
- MongoDB Manual — [Sort and Index Use](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Java Sync Driver — [Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/).
- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html).

**Conclusion:** To troubleshoot MongoDB aggregation out-of-memory errors, distinguish **blocking-stage memory, temporary disk spills, non-spilling accumulators, and BSON output document limits**. Stages such as **`$sort`, `$group`, `$bucket`, `$bucketAuto`, `$sortByCount`, and `$setWindowFields`** can use temporary files when permitted, whereas **`$facet` does not spill**, **`$push`/`$addToSet`** carry their own accumulation limits, and **each result document remains capped at the 16 MiB BSON limit**. Newer versions also enforce stage-count limits and per-operation memory limits. Sustainable resolution comes from **reading `explain`/`usedDisk`, shrinking input/state, leveraging indexes, applying top-K without altering semantics, avoiding unbounded arrays, capping concurrency, setting deadlines, protecting disk headroom, and monitoring p95/p99**. A report that finishes only by spilling to disk is not necessarily healthy; the goal must be **accurate business results, predictable resource usage, and zero degradation to other services**.
