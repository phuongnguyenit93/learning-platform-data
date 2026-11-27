# Combining Datasets with $unionWith in MongoDB

## 1. Problem: One Result Set from Multiple Document Sources

An order management application stores active data in the `orders_current` collection and historical data in `orders_archive`. Users want to see **all of their orders on a single page**, regardless of which collection a record resides in. The two collections may have different structures:

```javascript
// Collection orders_current
{
  _id: ObjectId("66a000000000000000000001"),
  tenantId: "TENANT-A",
  externalOrderId: "A-101",
  status: "PAID",
  createdAt: ISODate("2026-11-12T09:00:00Z"),
  totalCents: NumberLong("120000")
}

// Collection orders_archive: legacy system schema
{
  _id: ObjectId("66a000000000000000000002"),
  clientTenant: "TENANT-A",
  reference: "A-099",
  legacyState: "PAID",
  dateText: "2026-10-15T08:00:00Z",
  amountText: "90000"
}
```

A historical report needs to read from both collections, normalize common fields such as `externalOrderId`, `status`, `createdAt`, and `amountCents`, and sort chronologically. Within the aggregation framework, MongoDB provides the **`$unionWith`** stage for this kind of union.

Similar scenarios include:

- Merging events from `app_events` and `legacy_events` to build a timeline.
- Aggregating transactions across multiple collections with similar schemas.
- Combining results from two distinct filter branches and then computing shared statistics.
- Reading active and archived data together during a migration phase.
- Combining data from three or more collections in the same database into one document stream for downstream pipeline stages.

After this lesson, you will understand `$unionWith` syntax, the difference between **UNION ALL** and deduplication, how to normalize schemas per source, how to filter, sort, and paginate properly after unioning, stage limitations, and how to inspect performance with `explain()`.

## 2. What Does `$unionWith` Actually Do?

### 2.1. Combining Two Document Streams

An aggregation pipeline usually starts from one collection and processes documents sequentially:

```text
orders_current
      |
      v
    $match
      |
      v
   $project
      |
      +------------------------------+
      |                              |
      v                              v
 Result stream A                $unionWith
                                     |
                             orders_archive
                                     |
                             inner pipeline
                                     |
                                     v
                               Result stream B
      |                              |
      +---------------+--------------+
                      |
                      v
             Combined stream A + B
                      |
                 $sort / $group
                      |
                      v
                   Output
```

Conceptually, `$unionWith` takes **documents reaching this stage from the main pipeline** and combines them with **the result of a pipeline run on the specified collection**. Stages placed afterward process the combined stream.

There is no key-based join between two documents at this step. Every document from each branch remains **its own separate document** in the output unless a subsequent stage explicitly transforms or groups them.

### 2.2. Analogous to SQL `UNION ALL`

In SQL, `UNION ALL` concatenates rows from two result sets and **retains duplicates**. `$unionWith` has similar semantics.

```sql
SELECT order_id, status, created_at FROM current_orders
UNION ALL
SELECT order_id, status, created_at FROM archive_orders;
```

However, MongoDB operates on **documents**, not tables with fixed columns. Two branches can emit documents with different field names and BSON types. `$unionWith` **does not automatically rename fields, cast types, or align schemas**.

| Question | `$unionWith` Behavior |
| --- | --- |
| Can it combine results from two collections? | Yes |
| Can you specify a separate pipeline for the second collection? | Yes |
| Can multiple `$unionWith` stages be chained sequentially? | Yes |
| Does it automatically remove duplicates? | No |
| Does it merge documents sharing `_id` into one document? | No |
| Does it require both collections to share a schema? | No |
| Does it guarantee which branch's documents appear first? | No |
| Does it automatically write results to a new collection? | No |

In particular, **document order after union is not guaranteed**. If an application requires ordering, add a `$sort` stage over the combined result.

### 2.3. How Does It Differ from `$lookup`?

The two stages serve completely different purposes:

```text
$unionWith: CONCATENATES result streams

Collection A --> doc A1
             --> doc A2  ----+
                             +--> [A1, A2, B1, B2]
Collection B --> doc B1  ----+
             --> doc B2

$lookup: ATTACHES related information

Order A1 --customerId--> Customer C1
                   |
                   v
Order A1 + customer: [C1]
```

`$lookup` performs a form of **left outer join**, typically adding an array of related documents to each input document. `$unionWith` does not join by key; it appends documents from the second branch into the result set.

When you want **one row per transaction from two sources**, reach for `$unionWith`. When you want **an order enriched with customer details**, reach for `$lookup`.

## 3. `$unionWith` Syntax

### 3.1. Shorthand Form: Taking All Documents from a Second Collection

```javascript
db.orders_current.aggregate([
  { $unionWith: "orders_archive" }
]);
```

This returns results from the primary collection `orders_current` combined with all documents in `orders_archive`. It is the simplest syntax when no filtering or schema adjustment is needed on the second branch.

### 3.2. Full Form: `coll` and `pipeline`

```javascript
db.orders_current.aggregate([
  {
    $match: { status: "PAID" }
  },
  {
    $unionWith: {
      coll: "orders_archive",
      pipeline: [
        { $match: { legacyState: "PAID" } },
        {
          $project: {
            _id: 0,
            externalOrderId: "$reference",
            status: "$legacyState"
          }
        }
      ]
    }
  }
]);
```

Meaning:

- `coll` is the collection or view name used as the source for the union branch, normally in the **same database** as the primary collection.
- `pipeline` contains stages executed on documents from the source specified in `coll`.
- Stages **before** `$unionWith` process only the main data stream.
- Stages **after** `$unionWith` process results from **both** branches.

In this example, the main pipeline only filters `status` on the current collection. The archive collection is filtered by `legacyState` in its own pipeline. However, the main branch still retains extra original fields because it hasn't been projected yet; to make both branches produce a uniform shape, normalize both as shown in the practice section.

### 3.3. Handling More Than Two Sources

Multiple stages can be chained consecutively:

```javascript
db.app_events.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $unionWith: {
      coll: "legacy_events",
      pipeline: [
        { $match: { tenantId: "TENANT-A" } }
      ]
    }
  },
  {
    $unionWith: {
      coll: "imported_events",
      pipeline: [
        { $match: { tenantId: "TENANT-A" } }
      ]
    }
  },
  { $sort: { occurredAt: -1 } }
]);
```

This example assumes all three collections store `occurredAt` as a BSON Date. If any source uses a different type, normalize the timestamp field **before the shared sort**.

### 3.4. Unioning with Inline Documents Using `$documents`

In versions supporting `$documents` inside a subpipeline, `coll` can be omitted **when** the pipeline starts with `$documents`:

```javascript
db.app_events.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $unionWith: {
      pipeline: [
        {
          $documents: [
            {
              tenantId: "TENANT-A",
              type: "SYSTEM",
              message: "Reconciliation cycle started"
            }
          ]
        }
      ]
    }
  }
]);
```

This branch injects a document that does not come from a stored collection. Starting in MongoDB 8.0, subpipeline namespace validation requires specifying a valid `coll` when the pipeline starts from a collection, and **omitting `coll`** when the pipeline starts from a standalone source such as `$documents`. For production compatibility, always check feature and syntax rules for your exact server version.

## 4. Preparing Practice Data in `mongosh`

The examples below use the test database `mongo_union_row203_lab` and two separate collections. Operate only on a MongoDB instance where you are authorized to write; never insert or delete documents in real business collections.

Connect with `mongosh`, for instance in a local environment:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Adjust the URI for your practice environment's server, authentication, and TLS settings. Inside `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_union_row203_lab");
const current = lab.getCollection("orders_current_demo");
const archive = lab.getCollection("orders_archive_demo");

// Each practice run gets its own data namespace.
const runId = "row203-" + new ObjectId().toHexString();
const tenantId = runId;

print("database=" + lab.getName());
print("runId=" + runId);

current.insertMany([
  {
    runId,
    tenantId,
    externalOrderId: "A-101",
    status: "PAID",
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    totalCents: NumberLong("120000")
  },
  {
    runId,
    tenantId,
    externalOrderId: "A-102",
    status: "NEW",
    createdAt: ISODate("2026-11-13T10:00:00Z"),
    totalCents: NumberLong("75000")
  },
  {
    runId,
    tenantId,
    externalOrderId: "A-103",
    status: "PAID",
    createdAt: ISODate("2026-11-14T02:00:00Z"),
    totalCents: NumberLong("200000")
  }
]);

archive.insertMany([
  {
    runId,
    clientTenant: tenantId,
    reference: "A-098",
    legacyState: "PAID",
    dateText: "2026-09-10T08:00:00Z",
    amountText: "55000"
  },
  {
    runId,
    clientTenant: tenantId,
    reference: "A-099",
    legacyState: "PAID",
    dateText: "2026-10-15T08:00:00Z",
    amountText: "90000"
  },
  {
    runId,
    clientTenant: tenantId,
    reference: "A-101",
    legacyState: "PAID",
    dateText: "2026-11-12T09:00:00Z",
    amountText: "120000"
  }
]);

print("current=" + current.countDocuments({ runId }));
print("archive=" + archive.countDocuments({ runId }));
```

We now have:

- **3 current documents** with `createdAt` as BSON Date and `totalCents` as BSON Int64.
- **3 archive documents** with date and amount stored as strings.
- Business key `A-101` appears in **both collections**. This overlap is intentional for demonstration.
- `runId` lets us clean up cleanly without affecting other test runs.

Never delete documents based solely on generic `externalOrderId` or `reference` values. In multi-tenant applications, order codes can be reused across tenants.

## 5. Simple Union and Observing Duplicate Records

### 5.1. Union Does Not Automatically Align Schemas

```javascript
const rawUnion = current.aggregate([
  { $match: { runId } },
  {
    $unionWith: {
      coll: "orders_archive_demo",
      pipeline: [
        { $match: { runId } }
      ]
    }
  }
]).toArray();

print("rawCount=" + rawUnion.length);
printjson(rawUnion);
```

With the sample data, `rawCount` equals **6**. We get three current documents and three archive documents. The result contains **two different document shapes** because no normalization step was performed.

The two `A-101` records remain two separate documents. `$unionWith` does not compare business keys, check `_id` collisions, or automatically merge matching records.

### 5.2. Why Can't You Assume "current first, archive second"?

Even though the pipeline starts from `current`, MongoDB documentation specifies that **output order after `$unionWith` is not guaranteed**. Never write application code assuming:

```text
First 3 documents = current
Last 3 documents  = archive
```

If you need to know the origin, add a **source marker field** such as `origin: "current"` and `origin: "archive"` in each branch. If you need newest-first ordering, add `$sort` after normalizing the combined result.

### 5.3. Unioning a Collection with Itself

```javascript
const twice = current.aggregate([
  { $match: { runId } },
  {
    $unionWith: {
      coll: "orders_current_demo",
      pipeline: [
        { $match: { runId } }
      ]
    }
  }
]).toArray();

print("count=" + twice.length);
```

The expected count is **6** because each document in `current` enters through both branches. This directly demonstrates **UNION ALL** behavior: even when both branches read the exact same collection and return the same documents, MongoDB does not deduplicate them automatically.

## 6. Normalizing Documents Before Unioning

### 6.1. Goal: One Unified Result Contract

Both collections store data differently, yet the API expects a uniform document shape:

```javascript
{
  sourceId: ObjectId("..."),
  tenantId: "row203-...",
  externalOrderId: "A-101",
  status: "PAID",
  createdAt: ISODate("2026-11-12T09:00:00Z"),
  amountCents: NumberLong("120000"),
  origin: "current",
  originPriority: 2
}
```

Key principles:

1. **Identical field names**: archive's `reference` maps to `externalOrderId`; `legacyState` maps to `status`.
2. **Uniform BSON types**: `dateText` is parsed into a Date; `amountText` is converted to Long.
3. **Preserve provenance**: `origin` identifies which collection the record came from.
4. **Do not rely on `_id` as a system-wide deduplication key**: documents across two collections can have different `_id` values while representing the same order.
5. **Separate priority rules**: `originPriority` is a helper field used when picking one record among duplicates.

### 6.2. Building a Normalized Union Pipeline

In the same `mongosh` session where `runId` and `tenantId` are defined, create a reusable pipeline array:

```javascript
const normalizedUnion = [
  // Branch 1: active orders.
  {
    $match: { runId, tenantId }
  },
  {
    $project: {
      _id: 0,
      sourceId: "$_id",
      tenantId: "$tenantId",
      externalOrderId: "$externalOrderId",
      status: "$status",
      createdAt: "$createdAt",
      amountCents: "$totalCents",
      origin: { $literal: "current" },
      originPriority: { $literal: 2 }
    }
  },
  // Branch 2: legacy archived orders.
  {
    $unionWith: {
      coll: "orders_archive_demo",
      pipeline: [
        {
          $match: {
            runId,
            clientTenant: tenantId
          }
        },
        {
          $project: {
            _id: 0,
            sourceId: "$_id",
            tenantId: "$clientTenant",
            externalOrderId: "$reference",
            status: "$legacyState",
            createdAt: {
              $dateFromString: {
                dateString: "$dateText",
                onError: null,
                onNull: null
              }
            },
            amountCents: {
              $convert: {
                input: "$amountText",
                to: "long",
                onError: null,
                onNull: null
              }
            },
            origin: { $literal: "archive" },
            originPriority: { $literal: 1 }
          }
        }
      ]
    }
  }
];

printjson(current.aggregate(normalizedUnion).toArray());
```

Here:

- `$project` on the **main branch** produces the exact same field names as `$project` in the subpipeline.
- `$dateFromString` parses ISO 8601 strings ending in `Z` into BSON Date. `onError: null` prevents the entire pipeline from aborting if legacy data contains an invalid date string; always inspect records that convert to null.
- `$convert` with `to: "long"` turns integer strings into BSON Int64; `onError`/`onNull` returns null when conversion fails.
- `$literal` makes explicit that `origin` and `originPriority` are **constants**, not field paths.
- `_id: 0` drops the original top-level `_id`; instead `sourceId: "$_id"` retains the source document's ID.

When legacy data has invalid types, "coercing to null" can keep reports running yet also mask data quality bugs. In real systems, count malformed records or route them to an audit queue; never default failed amount conversions to 0 without an explicit business rule.

### 6.3. Sorting After Both Branches Share Types

```javascript
const sorted = current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      createdAt: -1,
      externalOrderId: 1,
      origin: 1,
      sourceId: 1
    }
  },
  {
    $project: {
      originPriority: 0
    }
  }
]).toArray();

printjson(sorted);
```

`createdAt` is now a BSON Date on both branches, so comparisons reflect **actual timestamps** rather than lexicographical string order. Extra fields in `$sort` provide deterministic tie-breaking when records share the same timestamp.

**Never sort only before `$unionWith` and expect the final output to stay globally sorted.** To order the combined set, place an appropriate `$sort` **after** the union.

## 7. Handling Duplicates: Union Does Not Mean Deduplication

### 7.1. Document Duplicates vs. Business Duplicates

There are at least three notions of "duplicate":

1. **The same source document** enters the pipeline twice, e.g., unioning a collection with itself.
2. **The same `_id`** appearing across two different collections.
3. **The same business key**, such as `(tenantId, externalOrderId)`, even when `_id` and other fields differ.

MongoDB does not decide which definition is right for your domain. If an API shows each order once, define the key from business rules; for example:

```text
unique business key = (tenantId, externalOrderId)
```

With the sample data, 6 documents are unioned yet only **5 order keys** exist because `A-101` appears in both current and archive.

### 7.2. Counting Distinct Business Keys

```javascript
const distinctCounts = current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      }
    }
  },
  { $count: "distinctOrders" }
]).toArray();

printjson(distinctCounts);
```

Expected output:

```javascript
[{ distinctOrders: 5 }]
```

`$group` on the composite key forms one group per pair, and `$count` counts the groups. This differs from placing `$count` right after union, which counts all 6 documents including duplicates.

### 7.3. Keeping One Record Using a Source Priority Policy

If each key should appear only once in the API, decide which copy wins. Here, **current takes precedence over archive** when both have the same order ID. We assigned `originPriority: 2` to current and `1` to archive.

```javascript
const deduplicated = current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      tenantId: 1,
      externalOrderId: 1,
      originPriority: -1,
      createdAt: -1,
      sourceId: 1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      chosen: { $first: "$$ROOT" },
      duplicateCount: { $sum: 1 }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$chosen",
        { duplicateCount: "$duplicateCount" }
      ]
    }
  },
  { $project: { originPriority: 0 } },
  {
    $sort: {
      createdAt: -1,
      externalOrderId: 1,
      sourceId: 1
    }
  }
]).toArray();

printjson(deduplicated);
```

Explanation:

1. `$sort` orders by business key, placing current before archive within each group. Within the same origin, `createdAt` and `sourceId` break ties.
2. `$group` groups by business key, picking the first document in each group via `$first: "$$ROOT"` and counting matching records.
3. `$replaceWith` and `$mergeObjects` restore the chosen document as root while adding `duplicateCount` for visibility.
4. `$project` removes the internal `originPriority` field if the API does not need it.
5. The final `$sort` orders the **deduplicated order list** chronologically.

On the sample data, `A-101` is picked from `current`; `duplicateCount: 2` shows two records shared that key.

**Data warning:** "current wins" is an **example policy**, not a MongoDB rule. A real system might pick the event with the highest `version`, trust one authoritative source per state, or retain full change history. Never use `$first` without an explicit sort order to pick the "right" record.

### 7.4. Is `$group` Alone Enough?

The snippet below deduplicates **key values**:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      }
    }
  }
]);
```

However, it **drops fields** like `status`, `createdAt`, and `amountCents`. If you only need a list of distinct IDs, this suffices. If you need full documents, define how fields are selected or merged.

Also, `$group: {_id: "$_id"}` produces business-incorrect results when the same order exists in two collections with two different `_id` values. The true key here is **tenant + external order ID**.

### 7.5. Duplicates May Signal Issues to Investigate

Duplicates should not always be silently discarded. If `A-101` has `amountCents: 120000` in current but `amountText: "125000"` in archive, two records share a key while disagreeing on amount.

You can build a discrepancy report:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 },
      amounts: { $addToSet: "$amountCents" },
      origins: { $addToSet: "$origin" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
```

The output reveals which keys repeated and what amount values appeared. On large datasets, `$addToSet` over many fields can consume substantial memory; select only the fields you need to compare and scope the report. A duplicate record is not necessarily a bug—it can happen intentionally during a migration window holding dual copies in current and archive.

## 8. Filtering and Paginating After Union

### 8.1. Filter Inside Each Branch to Shrink Input Data

In `normalizedUnion`, each branch already filters by its own `runId` and tenant. This is crucial: instead of pushing every document from both collections through the pipeline before filtering, narrow the data right at each source whenever possible.

```javascript
// Applies only to current when placed before $unionWith.
{
  $match: {
    runId,
    tenantId,
    status: "PAID"
  }
}

// Condition for archive must go inside its own subpipeline:
{
  $match: {
    runId,
    clientTenant: tenantId,
    legacyState: "PAID"
  }
}
```

Adding `$match: {status: "PAID"}` only to the main branch without filtering archive leaves non-PAID archive records in the result. Conversely, if you want a single shared filter after normalization:

```javascript
current.aggregate([
  ...normalizedUnion,
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, externalOrderId: 1 } }
]);
```

A post-union `$match` uses unified field names across both branches, making it concise and consistent. Yet it can force the database to process more documents before filtering. A good design **pushes equivalent predicates down into both branches** while keeping a shared filter afterward if needed to enforce the output contract.

### 8.2. Filtering by Date Range

After normalizing `createdAt` to Date:

```javascript
const start = ISODate("2026-11-01T00:00:00Z");
const end = ISODate("2026-12-01T00:00:00Z");

current.aggregate([
  ...normalizedUnion,
  {
    $match: {
      createdAt: { $gte: start, $lt: end }
    }
  },
  { $sort: { createdAt: -1, externalOrderId: 1 } }
]);
```

The half-open interval `[start, end)` avoids missing end-of-period milliseconds and prevents double-counting across adjacent periods. These bounds are **UTC**; if reporting by Vietnam local days or another timezone, convert **local day boundaries** into exact UTC instants before querying.

On the archive branch, parsing `dateText` into a Date inside the pipeline can be costly and prevent date-index filtering. If legacy data is queried by date frequently, consider migrating to BSON Date or adding a normalized indexed field.

### 8.3. `$sort`, `$skip`, and `$limit` Must Operate on the Combined Set

To return page 2 with page size 2:

```javascript
const page = 2;
const pageSize = 2;

current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      createdAt: -1,
      externalOrderId: 1,
      origin: 1,
      sourceId: 1
    }
  },
  { $skip: (page - 1) * pageSize },
  { $limit: pageSize }
]);
```

Notes:

- Pagination **after union** paginates across combined results from both sources, not one page from current plus one page from archive.
- Sorting must be deterministic, especially when documents share timestamps. Include tie-breakers like `externalOrderId`, `origin`, and `sourceId` for stable ordering.
- If the API expects **each order once**, **deduplicate before `$skip`/`$limit`**. Paginating before deduplication can display the same order across multiple pages or distort total order counts.
- If data mutates continuously, offset pagination via `$skip` can shift items between pages; at scale, consider cursor/keyset pagination along a deterministic sort key with an appropriate consistency policy.

### 8.4. Counting Totals Accurately

```javascript
// Total documents after union: includes duplicates.
printjson(
  current.aggregate([
    ...normalizedUnion,
    { $count: "rowsIncludingDuplicates" }
  ]).toArray()
);

// Total distinct order keys: excludes business duplicates.
printjson(
  current.aggregate([
    ...normalizedUnion,
    {
      $group: {
        _id: {
          tenantId: "$tenantId",
          externalOrderId: "$externalOrderId"
        }
      }
    },
    { $count: "distinctOrders" }
  ]).toArray()
);
```

On the sample data, these return **6** and **5**. They answer **two different questions** rather than contradicting each other.

## 9. Aggregating Statistics After Union

### 9.1. Aggregating by Status

If you want document counts per status (counting copies from multiple sources):

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: "$status",
      documents: { $sum: 1 },
      amountCents: { $sum: "$amountCents" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

This example **double-counts the amount** for `A-101` since it exists in both current and archive. It is valid only if the business definition literally means "summarize all records across all sources."

If you want **total revenue across unique orders**, deduplicate by business key **before** `$group` by status:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      tenantId: 1,
      externalOrderId: 1,
      originPriority: -1,
      createdAt: -1,
      sourceId: 1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      chosen: { $first: "$$ROOT" }
    }
  },
  { $replaceWith: "$chosen" },
  {
    $group: {
      _id: "$status",
      uniqueOrders: { $sum: 1 },
      amountCents: { $sum: "$amountCents" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

In financial systems, always define **which record is the source of truth**. Conflicting duplicates should not automatically be resolved by "latest copy" if accounting workflows require verifying version, status, or originating system.

### 9.2. Statistics by Source

To measure how much data each collection contributes:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: "$origin",
      documents: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

The `origin` field added in each pre-union `$project` lets you trace data lineage. Keeping provenance aids observability, debugging, migrations, and format-error tracing.

## 10. Reusing One Collection Across Multiple Branches

`$unionWith` does not have to read a different collection. You can process one collection through two independent branches and union them.

For example, finding `NEW` orders and orders exceeding 100000 while tagging the matching reason:

```javascript
current.aggregate([
  {
    $match: {
      runId,
      status: "NEW"
    }
  },
  {
    $project: {
      _id: 1,
      externalOrderId: 1,
      reason: { $literal: "NEW_STATUS" }
    }
  },
  {
    $unionWith: {
      coll: "orders_current_demo",
      pipeline: [
        {
          $match: {
            runId,
            totalCents: { $gt: NumberLong("100000") }
          }
        },
        {
          $project: {
            _id: 1,
            externalOrderId: 1,
            reason: { $literal: "HIGH_AMOUNT" }
          }
        }
      ]
    }
  }
]);
```

If an order is both `NEW` and high-amount, it appears **twice with two different `reason` values**, because both independent branches return it. That may be intentional for an "alert reasons" feed; if you want a list of unique **orders**, group by ID and use `$addToSet` to collect multiple reasons:

```javascript
// Applied after the two branches in the example above:
{
  $group: {
    _id: "$_id",
    externalOrderId: { $first: "$externalOrderId" },
    reasons: { $addToSet: "$reason" }
  }
}
```

When you only need the boolean condition `NEW OR totalCents > 100000`, a single `$match` with `$or` is usually simpler and faster. Use `$unionWith` only when branches genuinely require separate pipelines, sources, or independent transformations.

## 11. Limitations and Caveats of `$unionWith`

### 11.1. Cannot Be Used Inside Transactions

Per MongoDB documentation, an aggregation pipeline containing `$unionWith` **cannot run inside a transaction**. Do not design a workflow that "opens a transaction and runs `$unionWith` to get an atomic report."

If a report needs specific consistency guarantees while data changes, evaluate read concerns, supported snapshot/read semantics, materialization strategies, or alternative data architectures. **By default, a union across two collections carries no business guarantee that records reflect a single transactional snapshot.**

### 11.2. No `$out` or `$merge` Inside a Union Subpipeline

The `pipeline` nested inside `$unionWith` **cannot contain `$out` or `$merge`**. Those stages write aggregation output and are invalid inside a union branch.

```javascript
// Invalid: $merge is inside $unionWith's pipeline.
{
  $unionWith: {
    coll: "orders_archive_demo",
    pipeline: [
      { $match: { status: "PAID" } },
      { $merge: "some_report_collection" }
    ]
  }
}
```

If you want to materialize the **final combined output**, consider placing `$merge` or `$out` at the **end of the outer pipeline**, if supported by your version, topology, privileges, and write semantics. That is a write operation distinct from `$unionWith` itself; carefully manage overwrites, unique keys, and idempotent re-runs.

### 11.3. Collation Across Multiple Sources

Collation governs how strings are compared and sorted. With `$unionWith`:

- If `aggregate()` specifies a `collation`, the entire operation uses that collation.
- Otherwise, the operation inherits the collation of the primary collection/view.
- The default collation of the **unioned collection** does not automatically override the main pipeline's collation.
- If the union source is a **view**, its collation must be compatible per MongoDB rules; a view whose collation differs from the main collection/view can cause the command to fail.

Example specifying an operation-level collation:

```javascript
current.aggregate(
  [
    ...normalizedUnion,
    { $sort: { externalOrderId: 1 } }
  ],
  {
    collation: { locale: "vi", strength: 2 }
  }
);
```

Collation also affects `$group` when grouping on string keys. If case or diacritics distinguish business keys, define comparison rules explicitly; never pick a display-friendly collation that accidentally merges two distinct technical IDs.

### 11.4. MongoDB Search Inside Union Subpipelines

In deployments with MongoDB Search on supported versions, `$unionWith` can start a subpipeline with `$search` or `$searchMeta` per documentation rules. This is an advanced mechanism relying on Search indexes and capabilities rather than standard B-tree `$match`.

Do not insert `$search` arbitrarily mid-subpipeline or expect a local `mongod` without Search configured to run such examples.

### 11.5. Namespaces and Deployment Versions

`coll` normally names a collection or view in the same database. Do not treat `"otherDatabase.collection"` as standard syntax for cross-database unions; check version-specific capabilities or use ETL/materialized collections when cross-database aggregation is truly required.

MongoDB updated namespace validation for `$unionWith` subpipelines starting in version 8.0; when using `$documents` instead of a collection, omit `coll`. For stages starting from a collection, declare `coll` explicitly.

Restrictions can change across server versions, topologies, collection/view types, and nested stages. For production deployments, check MongoDB documentation **for your exact running version** before combining multiple advanced features.

## 12. Performance and Indexing per Branch

### 12.1. Union Cost Depends on Both Sources

A union pipeline must process documents emitted by every branch. If current has one million records and archive has ten million records, an unfiltered pipeline normalizing millions of documents and sorting everything can consume massive CPU, I/O, RAM, and time.

Never expect `$unionWith` to shrink data or remove duplicates automatically. Downstream `$sort` and `$group` stages over large combined sets can dominate cost.

### 12.2. Place Indexable `$match` Filters on Each Collection

For the example's query pattern:

```javascript
// Index on the current branch.
current.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "tenant_createdAt" }
);

// Index on the archive branch.
archive.createIndex(
  { clientTenant: 1 },
  { name: "clientTenant" }
);
```

The two indexes serve filters on **two distinct collections**. An index on `current` cannot locate documents in `archive`. Likewise, if the archive branch filters by `clientTenant`, the index must exist on `archive` itself.

An index on the string field `dateText` is not equivalent to a BSON Date range index after `$dateFromString`. Parsing strings during aggregation makes time-range index scans difficult. If reports run frequently by date, consider migrating legacy dates to BSON Date or adding a normalized indexed field.

### 12.3. Filter Early While Preserving Semantics

Suppose you need tenant T's orders for November:

- The current branch can `$match` directly on `tenantId` and `createdAt` if indexed.
- The archive branch can `$match` on `clientTenant` before parsing; if a normalized date field exists, apply the range there too.
- Keep a final `$match` on normalized `createdAt` if you want uniform enforcement across both sources.

Never push a filter down into a branch in a way that **changes semantics**. For instance, if legacy date strings lack timezones, direct string comparisons can disagree with Date comparisons. Pushdown is valid only when semantics match.

### 12.4. Monitoring with `explain("executionStats")`

```javascript
printjson(
  current.explain("executionStats").aggregate([
    ...normalizedUnion,
    { $sort: { createdAt: -1 } }
  ])
);
```

Plans and output shapes vary across MongoDB versions and engines. When inspecting, look for:

- `COLLSCAN` vs. `IXSCAN` on each source;
- which indexes are used in the main branch and the union branch;
- keys and documents examined where reported by the plan;
- resource-heavy sort or group steps;
- document counts processed before and after filtering.

Never assume a query is fast just because it returns few documents. A union can return 20 records while scanning millions of documents if filters or indexes are suboptimal.

On a tiny 6-document demo dataset, the optimizer may pick a collection scan simply because it is cheaper; do not draw production speed conclusions from tiny lab counts.

### 12.5. Create Only Indexes That Earn Their Keep

Every index consumes disk, cache, and write throughput. Do not create every conceivable index on every union branch. Start from the workload:

1. Does the API typically filter by tenant, status, or date range?
2. Does it frequently paginate newest-first?
3. Is archive data queried often or only in monthly reports?
4. Can heavy reports query a materialized combined dataset instead?
5. Do `explain()` and realistic load tests confirm the new index delivers clear gains?

Splitting current and archive collections can help data lifecycle management, yet screens reading both pay extra union and normalization costs compared to a single unified-schema collection.

## 13. When to Use `$unionWith` and When Not To

| Goal | Usually Appropriate Tool | Reason |
| --- | --- | --- |
| Combine records from two collections into one list | `$unionWith` | Concatenates two document streams |
| Combine records from one collection across two processing branches | `$unionWith` or `$match $or` | Choose based on how differently each branch transforms data |
| Enrich an order with customer data via `customerId` | `$lookup` | Relational join |
| Reshape or rename fields | `$project`, `$set`, `$replaceWith` | Shape normalization |
| Remove business-key duplicates after union | `$group` with record-selection policy | `$unionWith` keeps duplicates |
| Compute revenue across both sources | `$unionWith` then `$group` | Aggregates combined stream; watch business duplicates |
| Persist a durable reporting collection | `$merge` or `$out` after an appropriate pipeline | Dedicated write stages |
| Sync data across services/databases outside union scope | Designed ETL / streaming / sync | Do not assume `$unionWith` bridges arbitrary systems |
| Enforce uniqueness on write | Unique indexes and concurrency handling | `$unionWith` is read/transform only, not insert validation |

A common confusion: **deduplicating on read** only cleans up display output. It does not remove duplicate documents in storage and never replaces unique indexes or write-path validation.

## 14. Design Mistakes and How to Avoid Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Thinking `$unionWith` equals SQL deduplicating `UNION` | Double-counts revenue/orders | Treat as **UNION ALL**; use `$group` when needed |
| Thinking both collections must share a schema | Overcomplicated queries or avoiding useful stages | Use `$project`/`$convert`/`$dateFromString` to normalize |
| Not normalizing fields before `$sort` | Dates and strings compare with different semantics | Convert to identical BSON types |
| Using `_id` to deduplicate across collections | Same order may have two distinct `_id` values | Group by the full business key |
| Using `$first` without sorting | Non-deterministic record selection | Define priority, sort order, and tie-breakers |
| Sorting inside each branch without sorting after union | Final order is not guaranteed | `$sort` after union |
| Applying `$limit` per branch for global pagination | May omit records belonging on the page | Paginate on the combined set |
| Deduplicating after `$skip/$limit` | Duplicates occupy page slots | Deduplicate before paginating |
| Filtering tenant only in the main branch | Reads other tenants' archive records | `$match` per branch or filter after normalization |
| Using `$dateFromString` without handling bad legacy input | One bad date aborts the pipeline | Use `onError`, monitor, and fix source data |
| Converting errors to null then silently summing as 0 | Hides monetary discrepancies | Flag bad records and define reconciliation rules |
| Assuming each branch uses its own collation | Unexpected grouping/sorting results | Understand operation-level and view collation |
| Using `$unionWith` inside a transaction | Command is unsupported | Design alternative read semantics/architecture |
| Putting `$merge`/`$out` inside a union subpipeline | Violates stage restrictions | Write only from the outer pipeline when valid |
| Merging multiple sources without provenance | Hard to debug or trace duplicates | Keep `origin` and `sourceId` |
| Ignoring indexes on the unioned collection | Subpipeline scans huge data volumes | Design indexes for **every source** |

## 15. Comprehensive Practice Exercises

### 15.1. Exercise A: Latest Timeline Across Both Sources

Requirement: return all records, including duplicates, sorted descending by time while preserving source origin.

```javascript
current.aggregate([
  ...normalizedUnion,
  { $sort: { createdAt: -1, externalOrderId: 1, sourceId: 1 } },
  {
    $project: {
      _id: 0,
      externalOrderId: 1,
      status: 1,
      createdAt: 1,
      origin: 1,
      amountCents: 1
    }
  }
]);
```

Question: Why can `A-101` appear twice? Why must sorting occur after the union?

### 15.2. Exercise B: Revenue Statistics for Unique Orders

Requirement: count each `(tenantId, externalOrderId)` once; when duplicated, prefer current.

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      tenantId: 1,
      externalOrderId: 1,
      originPriority: -1,
      createdAt: -1,
      sourceId: 1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      chosen: { $first: "$$ROOT" }
    }
  },
  { $replaceWith: "$chosen" },
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: null,
      paidOrders: { $sum: 1 },
      paidAmountCents: { $sum: "$amountCents" }
    }
  }
]);
```

Question: If you omit deduplication, how will total revenue be skewed? If archive has a different amount from current, where is the precedence rule encoded?

### 15.3. Exercise C: Detecting Missing/Unparseable Legacy Data

Requirement: inspect archive documents whose date or amount failed to parse:

```javascript
current.aggregate([
  ...normalizedUnion,
  { $match: { origin: "archive" } },
  {
    $match: {
      $or: [
        { createdAt: null },
        { amountCents: null }
      ]
    }
  },
  {
    $project: {
      tenantId: 1,
      externalOrderId: 1,
      createdAt: 1,
      amountCents: 1,
      origin: 1
    }
  }
]);
```

With clean sample data, the result should be empty. To observe errors, insert a **demo archive document** with the same `runId` and an invalid `dateText`; you will see `createdAt: null` in the output. Never alter production validators or data to test this.

### 15.4. Exercise D: Comparing Two Questions

Run:

```javascript
// How many documents are unioned?
current.aggregate([
  ...normalizedUnion,
  { $count: "allRows" }
]);

// How many unique orders exist by business key?
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      }
    }
  },
  { $count: "uniqueOrders" }
]);
```

Explain why the exact same dataset yields two different counts. Why can't you simply add the document counts of both collections and treat that as unique order count?

## 16. Safely Cleaning Up Practice Data

The `aggregate()` operations in this lesson are read-only; demo documents were created in Section 4. Before deleting, confirm the exact database, collections, `runId`, and document list:

```javascript
print("database=" + lab.getName());
print("current collection=" + current.getName());
print("archive collection=" + archive.getName());
print("runId=" + runId);

const ownedCurrent = current.find(
  { runId },
  { _id: 1, runId: 1, externalOrderId: 1 }
).toArray();

const ownedArchive = archive.find(
  { runId },
  { _id: 1, runId: 1, reference: 1 }
).toArray();

printjson(ownedCurrent);
printjson(ownedArchive);
```

Only after verifying these are **documents created by your own practice run**, delete by `_id` **together with `runId`**:

```javascript
for (const doc of ownedCurrent) {
  printjson(current.deleteOne({ _id: doc._id, runId }));
}

for (const doc of ownedArchive) {
  printjson(archive.deleteOne({ _id: doc._id, runId }));
}

print("current remaining=" + current.countDocuments({ runId }));
print("archive remaining=" + archive.countDocuments({ runId }));
```

If the `runId` variable is lost, rely on the logged value from setup or a verified ID list; never guess IDs to delete. Never run `deleteMany({})`, `drop()`, or `dropDatabase()` in a shared environment. Indexes created during practice remain after deleting documents; manage them only with proper authorization and procedures.

## 17. Review Questions

1. How does `$unionWith` differ from `$lookup` in purpose and output shape?
2. Why is `$unionWith` compared to SQL `UNION ALL` rather than `UNION`?
3. Do two collections need identical schemas to be unioned?
4. What do `coll` and `pipeline` mean inside `$unionWith`?
5. If a `$match` is placed only before `$unionWith`, which source does it filter?
6. Why isn't sorting inside each branch enough to guarantee final output order?
7. In the current/archive example, why does `A-101` appear twice?
8. To count unique orders, why group by `(tenantId, externalOrderId)` instead of `_id`?
9. Why can `$first` without a sort rule select an unstable record?
10. When should you preserve both `origin` and `sourceId`?
11. Why must string dates be normalized into BSON Date before time comparisons?
12. If `dateText` fails to parse and `$dateFromString` uses `onError: null`, how can downstream results be affected?
13. Why is paginating after union but before deduplication business-incorrect?
14. Can `$merge` be placed inside a `$unionWith` subpipeline?
15. Can `$unionWith` be used inside a transaction?
16. When each source has its own indexes, why doesn't an index on `current` automatically optimize the `archive` subpipeline?
17. When should reading current/archive via union be replaced by a materialized reporting collection?
18. Does the unioned collection's collation automatically override the main operation's collation?

## 18. References

In production, consult syntax, limits, and features for your exact running MongoDB version:

- [`$unionWith` (aggregation stage) — MongoDB Database Manual](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unionWith/)
- [`$group` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [`$project` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [`$dateFromString` (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateFromString/)
- [`$convert` (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [`$lookup` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [`$merge` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)

## 19. Conclusion

`$unionWith` is a MongoDB aggregation stage for **combining documents from multiple result streams**, analogous to **UNION ALL**: it preserves duplicates and **does not guarantee output order**. It does not join by key, does not require identical schemas across sources, and does not automatically write results to a collection.

To use unions effectively in applications, **filter each source properly**, **normalize field names and BSON types**, and **define an explicit duplicate-handling policy** before aggregating or paginating. When ordered results are required, `$sort` after unioning; when each business entity must appear once, `$group` on the **full business key** with deterministic winner-selection rules. Performance and consistency depend on data volume, indexes, downstream stages, and MongoDB's operational limits—not `$unionWith` syntax alone.
