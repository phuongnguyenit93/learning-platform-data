# Document Too Large Errors, Unbounded Arrays, and Pipeline Limits in MongoDB

## Lesson Objectives

In MongoDB, many operational failures do not stem from lost connections or syntax errors. A system may run steadily for months and then suddenly encounter:

- `BSONObjectTooLarge` when appending another element to an array inside a document.
- `Document exceeds maximum size` as an order, user profile, or audit record keeps growing.
- `ExceededMemoryLimit` inside a pipeline containing `$group`, `$sort`, or `$facet`.
- Aggregation failures because **one result document** exceeds the BSON limit, even when the query returns only a single document.
- Queries becoming extremely slow after adding `$lookup`, `$unwind`, or a `$push` accumulator.
- Commands failing even with `allowDiskUse: true` enabled.
- A worker continuously running `$push` on the same document, causing hotspots, index maintenance overhead, and high replication load.

This lesson belongs to **Database Engine Document MongoDB → Troubleshooting → Document Too Large Errors, Unbounded Arrays, and Pipeline Limits**.

After this lesson, you will be able to:

1. Identify the **16 MiB limit for a single BSON document**, including byte counting, BSON overhead, and intermediate sizes.
2. Distinguish BSON document limits from aggregation memory limits, pipeline stage counts, execution time, and response sizes.
3. Use `$bsonSize`, `$size`, `collStats`, `explain`, and server logs to isolate issues.
4. Diagnose failures occurring during `insertOne`, `updateOne`, `findOneAndUpdate`, `aggregate`, `$lookup`, `$group`, or `$facet`.
5. Explain why `$push`, `$addToSet`, and embedded event logs create **unbounded arrays**.
6. Bound arrays using `$push + $each + $slice` properly per business rules, without treating it as long-term historical storage.
7. Refactor data models from unbounded embedding to **referenced collections**, **bounded buckets**, or **GridFS** where appropriate.
8. Understand which stages can spill to disk, how `allowDiskUse` interacts, and cases that cannot spill.
9. Reduce fan-out, intermediate size, and output size in `$lookup`, `$unwind`, `$group`, and `$facet`.
10. Design pipelines returning **many small documents via a cursor** instead of packing everything into one giant document.
11. Execute large-scale data migrations safely with batching, idempotent writes, checkpoints, reconciliation, and rollback plans.
12. Add guardrails in Java/Spring Data applications, validate inputs, and monitor predictive incident metrics.
13. Write a production recovery runbook without data loss and without amplifying the incident.

> **Core rule:** `allowDiskUse` can relieve memory pressure for **certain aggregation stages**, yet **it does not increase the 16 MiB limit of a BSON document** and does not eliminate all internal memory limits.

---

## 1. Map of Easily Confused Limits

| Scope | Typical milestone/limit | Characteristics |
|---|---|---|
| Single stored/returned BSON document | **16 MiB = 16,777,216 bytes** | Hard document size limit |
| BSON nesting depth | **100 levels** | Not solved by nesting arrays deeper |
| Aggregation pipeline stages | **1,000 stages** | Checked pre/post parse/optimization per docs |
| Memory for certain aggregation stages | **100 MB** milestone per docs, depending on server/settings | Some stages spill when permitted |
| `$facet` stage output | Up to **100 MB** per intermediate document in facet | `allowDiskUse` **does not** let `$facet` spill |
| Final output of `$facet` | Still subject to **16 MiB** per BSON document | Output document limit |
| `$group` `$push`/`$addToSet` accumulator | Memory limit per **accumulator value** | Does not auto-spill even when group state spills |
| MongoDB cursor returning many documents | Not limited to **16 MiB for the entire result set** | Yet each individual result document must still be ≤16 MiB |
| Embedded array | No single fixed element count across all arrays | Constrained by document size and other limits |
| Large files/images/videos | Can be stored with GridFS | Not by enlarging a single BSON document |

**Version note:** Limits and semantics may vary slightly across MongoDB Server releases. The 16 MiB document limit and 1,000-stage limit are widely documented MongoDB limits. Starting in MongoDB 6.0, `allowDiskUseByDefault` affects how stages spill. Newer versions also enforce **per-operation** total memory limits separate from per-stage limits. During incident response, verify `db.version()`, FCV where relevant, and documentation for your exact version.

References: [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) and [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).

---

## 2. Understanding 16 MiB: Limit of a Single BSON Document

MongoDB stores and exchanges documents in **BSON**, not plain JSON text. Document limit:

~~~text
16 × 1024 × 1024 = 16,777,216 bytes
~~~

BSON includes field names, types, string/binary lengths, values, array elements, and encoding overhead. Thus, a 15 MiB JSON string is not guaranteed to stay under 16 MiB after BSON encoding.

### 2.1. What Does the Limit Apply To?

- Documents passed to `insertOne` or `insertMany`.
- Document state **after** `updateOne`, `updateMany`, `findOneAndUpdate`, `$push`, `$set`.
- Any document returned from an aggregation.
- An oversized output document generated by `$group`/`$lookup`/`$facet`.

### 2.2. What 16 MiB Does Not Mean

- It does not mean a collection is capped at 16 MiB.
- It does not mean a query can return at most 16 MiB **in total**.
- It does not equate the size of an entire batch/cursor to one document.
- It is not a per-array limit independent of other fields in the document.
- Increasing `batchSize` does not allow returning a single larger document.
- Enabling `allowDiskUse` does not allow the server to accept arbitrary oversized payloads.

### 2.3. Real-World Example

~~~javascript
{
  _id: "ORDER-101",
  tenant_id: "tenant-a",
  status: "PAID",
  items: [
    // Originally 5 elements;
    // after several app versions, 300,000 elements.
  ],
  audit_events: [
    // Every update appends another event.
  ]
}
~~~

Even if `status` and `tenant_id` are tiny, the two arrays push the overall document past the threshold.

### 2.4. The 100-Level Nesting Limit

Nesting objects deeper neither avoids the 16 MiB limit nor helps; it risks hitting the nesting depth limit as well. Choose a structure reflecting queries and data lifecycle rather than "re-packing layers to dodge limits."

### 2.5. Measure Bytes, Not Character Count

Multibyte UTF-8 Unicode strings consume more bytes than character count suggests. Measure actual BSON size with dedicated tools rather than relying solely on `JSON.stringify(doc).length`.

---

## 3. Failure Model by Location

~~~text
Request / Job / Query
         |
         +-- INSERT / UPDATE
         |      |
         |      +-- BSON object too large
         |      +-- Array grows without bound
         |      +-- Invalid array type
         |
         +-- AGGREGATE
         |      |
         |      +-- One result doc > 16 MiB
         |      +-- $facet internal doc > 100 MB
         |      +-- $group accumulator too large
         |      +-- $sort/$group memory no spill
         |      +-- > 1000 pipeline stages
         |      +-- Join/unwind cardinality explosion
         |
         +-- APPLICATION / NETWORK
                |
                +-- Driver/client encoding error
                +-- Timeouts
                +-- API gateway response size
                +-- JVM heap / GC pressure
~~~

A million small documents in a cursor **differ** from a single document holding a million-element array. Both can consume heavy resources, but their fixes are completely different.

---

## 4. Recognizing Error Messages

Specific messages vary by server version, driver, and where the failure happens.

| Clue in exception/log | Likely cause | What to verify |
|---|---|---|
| `BSONObjectTooLarge` | A BSON object exceeded permitted size | Which document and which stage produced it? |
| `object to insert too large` | Insert/update creates an oversized document | `$bsonSize` of the current doc and new payload |
| `Document exceeds maximum size` | Document size limit | Output or persisted document? |
| `ExceededMemoryLimit` | A stage/accumulator ran out of memory | Stage, `allowDiskUse`, per-operation cap |
| `QueryExceededMemoryLimitNoDiskUseAllowed` | Stage can spill, yet disk use is disallowed | Can disk spill be enabled safely? |
| `Sort exceeded memory limit` | Sort had to buffer too much data | Missing index, match/limit placement? |
| `$facet` ~100 MB error | Facet intermediate doc too large | Collecting unbounded data into arrays? |
| Exceeded max pipeline stages error | Pipeline has too many stages | 1,000+ stages after parsing? |
| `ExceededTimeLimit`/timeout | Time/resource or topology | Do not automatically assume BSON size |
| Java `OutOfMemoryError` | Client holds too much data | Cursor streaming, buffering, heap dump |
| HTTP 413 / gateway limit | API/gateway limit, not necessarily MongoDB | Response size, proxy config |

### 4.1. Do Not Hardcode a Single Error Code

A "document too large" error can be caught client-side before sending, server-side on update, or during aggregation output assembly. Error codes and exception classes vary across MongoDB Driver and Spring Data versions.

### 4.2. Capture Full Context

Record operation type, collection, request ID, **redacted/authorized** tenant ID, document ID and pipeline stage, server version, driver version, timestamp, stack trace, duration, and input payload size. Never dump PII, secrets, or entire huge documents into logs.

---

## 5. Diagnosing Document Size with `$bsonSize`

MongoDB provides the `$bsonSize` expression, returning a BSON document's byte size.

### 5.1. Finding the Top 20 Largest Documents

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      bson_bytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  {
    $sort: {
      bson_bytes: -1,
      _id: 1
    }
  },
  { $limit: 20 }
], {
  allowDiskUse: true
});
~~~

**Explanation:** `$$ROOT` refers to the current document. `$bsonSize` measures its BSON-encoded byte size. `$project` shrinks the output before `$sort`. It still reads full source documents to compute sizes, so it can be a heavy scan on large collections.

### 5.2. Finding Documents Above an Alert Threshold

Example using an operational threshold of **8 MiB** (not the MongoDB hard limit):

~~~javascript
const alertBytes = 8 * 1024 * 1024;

db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      bytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  {
    $match: {
      bytes: { $gte: alertBytes }
    }
  },
  { $sort: { bytes: -1 } },
  { $limit: 100 }
], {
  allowDiskUse: true
});
~~~

Set early-warning quotas like 2/4/8 MiB based on business record norms and growth rate; do not wait until 16 MiB to react.

### 5.3. Measuring a Specific Document

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: "ORDER-101"
    }
  },
  {
    $project: {
      _id: 1,
      bytes: { $bsonSize: "$$ROOT" }
    }
  }
]);
~~~

### 5.4. `$bsonSize` of a Nested Field

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ORDER-101" } },
  {
    $project: {
      _id: 1,
      total_bytes: { $bsonSize: "$$ROOT" },
      metadata_bytes: {
        $bsonSize: {
          $ifNull: ["$metadata", {}]
        }
      }
    }
  }
]);
~~~

`$bsonSize` requires an argument that resolves to a BSON object or null—it does not directly measure strings or numbers. Use `$binarySize` for strings/binary where appropriate; for arrays, wrap in an object or inspect element counts, types, and overall document size.

### 5.5. Note on Newer Versions

`$bsonSize` documentation notes changes in MongoDB 9.0 regarding intermediate documents larger than 16 MiB. For inspecting **persisted documents**, `$bsonSize:"$$ROOT"` at the start of a pipeline is straightforward; when measuring **intermediate output >16 MiB**, verify semantics for your server version.

Documentation: [`$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/).

---

## 6. Detecting Large Arrays and Unbounded Growth

### 6.1. Counting Elements

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      event_count: {
        $cond: [
          { $isArray: "$audit_events" },
          { $size: "$audit_events" },
          null
        ]
      },
      bytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { event_count: -1 } },
  { $limit: 20 }
], { allowDiskUse: true });
~~~

Use `$isArray` to avoid errors if a field was mistakenly written as a string/object or is missing.

### 6.2. The Array with the Most Elements Is Not Always the Largest

- 100,000 small integers may take fewer bytes than 1,000 objects containing long strings.
- `audit_events` embedding nested payloads or raw HTTP bodies can grow huge with only a few thousand events.
- Metadata, comments, embedded images, and history snapshots also add up.

Measure **element count, BSON bytes, and distribution**.

### 6.3. Querying Top Documents by Ratio

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $project: {
      _id: 1,
      bytes: { $bsonSize: "$$ROOT" },
      audit_count: {
        $cond: [
          { $isArray: "$audit_events" },
          { $size: "$audit_events" },
          0
        ]
      }
    }
  },
  { $sort: { bytes: -1 } },
  { $limit: 30 }
]);
~~~

Without an index supporting sorting on computed `bytes`, the query must scan and sort; run scoped by shard key, tenant cohort, or off-peak hours on large datasets.

### 6.4. Histograms Help Forecasting

Bucket sizes in 1 MiB bands:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      size_mib: {
        $divide: [
          { $bsonSize: "$$ROOT" },
          1024 * 1024
        ]
      }
    }
  },
  {
    $bucket: {
      groupBy: "$size_mib",
      boundaries: [0, 1, 2, 4, 8, 12, 16],
      default: "outside",
      output: {
        documents: { $sum: 1 }
      }
    }
  }
], { allowDiskUse: true });
~~~

These results aid distribution analysis, though the scan is not cheap on very large collections.

---

## 7. `collStats`, `avgObjSize`, and the Limits of Averages

### 7.1. Collection Statistics

~~~javascript
db.orders.stats();
~~~

Output may include:

- `count`.
- `size` (logical data size).
- `avgObjSize`.
- `storageSize`.
- `totalIndexSize` or index statistics.
- Other storage engine/scale metrics depending on server/version.

### 7.2. Averages Hide the Tail

A collection of 1 million documents averaging 3 KiB can still contain several 15 MiB documents. `avgObjSize` **does not** replace measuring p95/p99/max or top large documents.

### 7.3. Logical Size Differs from Allocated Storage

`size` and `storageSize` have different semantics: compression, fragmentation, and free space cause allocated storage not to match single-document byte counts. Never divide `storageSize/count` to claim how far a document is from 16 MiB.

### 7.4. Sharded Clusters

`stats` on a sharded collection may aggregate per-shard figures; inspect distribution/hot shards when skew exists. Avoid full collection scans from `mongos` during peak hours just to locate top records.

---

## 8. Common Cause: Continuous `$push`

Suppose a service records audit events directly inside the order:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORDER-101",
    tenant_id: "tenant-a"
  },
  {
    $push: {
      audit_events: {
        event_id: "evt-0001",
        type: "ORDER_VIEWED",
        at: new Date(),
        details: {
          ip: "192.0.2.1"
        }
      }
    }
  }
);
~~~

If every request appends, the array grows monotonically. At 100 events/day of 1 KiB each, it grows ~100 KiB/day before BSON overhead; over months, it still breaches the threshold.

### 8.1. `$push` Does Not Cap Element Count

`$push` appends an element. If the field does not exist, MongoDB creates an array; if the field exists and is not an array, the operation errors.

### 8.2. Why Does the Error Only Affect Certain Customers?

- Some accounts generate far more activity.
- Bots trigger high volumes of view/tracking events.
- High-load tenants accumulate many invoices/comments.
- A retry loop appends repeatedly.
- A non-idempotent message consumer creates duplicate events.
- Arrays embed externally supplied payloads that keep growing.

### 8.3. Do Not Keep Appending Errors to the Failing Document

When a document nears the limit, retrying the same payload fixes nothing. Raising retry counts or logging error events onto **the failing document itself** makes things worse.

---

## 9. `$addToSet` Does Not Prevent Unbounded Array Growth

A misguided reaction is switching every `$push` to `$addToSet`:

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-101" },
  {
    $addToSet: {
      audit_events: {
        event_id: "evt-1001",
        at: new Date(),
        type: "STATUS_CHECK"
      }
    }
  }
);
~~~

`$addToSet` only prevents adding **exact duplicate values by full-element equality**. If the timestamp changes each time, every event is distinct and the array still grows.

### 9.1. It Is Not Unique by a Subfield

~~~javascript
{ event_id: "evt-1001", at: ISODate("2026-11-14T01:00:00Z") }
{ event_id: "evt-1001", at: ISODate("2026-11-14T01:00:01Z") }
~~~

These are two different objects. `$addToSet` has no subfield uniqueness constraint like "only one element with `event_id=evt-1001`."

### 9.2. Does Not Clean Up Existing Duplicates

If the array already contains duplicate values, `$addToSet` does not remove existing duplicates.

### 9.3. Choose the Right Mechanism

- Very small tag set with a finite domain: `$addToSet` may work well.
- Unbounded event logs: move to a separate events collection.
- Keeping the N most recent notifications: bounded array.
- Business ledger: records collection with unique event ID/sequence, never unbounded embedding.

---

## 10. Using `$push + $each + $slice` for Bounded Arrays

If the business **only needs the 100 most recent events**, storing them in `recent_events` makes sense.

~~~javascript
db.orders.updateOne(
  {
    _id: "ORDER-101",
    tenant_id: "tenant-a"
  },
  {
    $push: {
      recent_events: {
        $each: [
          {
            event_id: "evt-2001",
            at: ISODate("2026-11-14T07:00:00Z"),
            type: "ORDER_UPDATED"
          }
        ],
        $sort: {
          at: -1,
          event_id: -1
        },
        $slice: 100
      }
    }
  }
);
~~~

### 10.1. Processing Order

When modifiers are combined, MongoDB appends elements, applies `$sort` if present, applies `$slice`, and stores the resulting array. `$slice: 100` keeps the first 100 elements after sorting.

### 10.2. `$slice: -100`

Without sorting, when appending chronologically, `$slice: -100` keeps the **last 100 elements of the array** after appending.

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-101" },
  {
    $push: {
      recent_events: {
        $each: [
          { event_id: "evt-2002", at: new Date() }
        ],
        $slice: -100
      }
    }
  }
);
~~~

### 10.3. Insufficient for Long-Term Auditing

Any event beyond the 100 kept elements is discarded. If compliance/traceability history is required, write all events to a separate collection or event log system; a bounded array is strictly a **recent cache/summary**.

### 10.4. Each Element Must Still Be Size-Bounded

100 events × 200 KiB each still exceeds 16 MiB. Bounding **element count** alone is not enough; bound event payloads, strings, and nested documents too.

### 10.5. Idempotency

`$push` on retry can insert duplicate events. If deduplication is required, use a collection with a unique index on a stable event ID or a dedicated dedup mechanism.

Documentation: [`$push` and Modifiers](https://www.mongodb.com/docs/manual/reference/operator/update/push/).

---

## 11. Short-Term Mitigations When a Document Approaches 16 MiB

### 11.1. Stop the Write Path Bloating the Document

For instance, disable the feature flag writing to the audit array, **without halting the entire order workflow if only an auxiliary feature is failing**. Decisions must reflect business criticality and data retention requirements.

### 11.2. Filter Logged Payloads

Stop storing raw request bodies, images, base64 strings, large diagnostics, or repeated snapshots inside the document. Store pointers, hashes, or summaries instead of raw data per security policy.

### 11.3. Enforce Thresholds in the Application

Reject or offload event payloads exceeding the domain byte limit to external storage. Do not wait for MongoDB to fail before arbitrarily truncating data.

### 11.4. Do Not Arbitrarily Delete Data to "Shrink Size"

`$pop`, `$pull`, or `$set: {audit_events: []}` can destroy audit/ledger records. Only trim data after copying and verifying it, or where domain retention explicitly permits.

### 11.5. Documents Near Max May Reject Migration Markers

If a document is already near 16 MiB, setting `migration_status: "MIGRATING"` on that same document may fail. Store checkpoints/migration metadata in a **separate control collection**.

### 11.6. Size-Reducing Updates

Once data is backed up/extracted and approved, `$unset` on an oversized field reduces size. With concurrent writers, use appropriate leases/CAS/feature flags to prevent losing events written between extraction and unset.

---

## 12. How Data Modeling Causes Unbounded Growth

### 12.1. High-Risk Arrays

- Audit events, clickstreams, page views.
- All comments/likes/views for a product.
- Every bank transaction for a user.
- All messages in a chat room.
- Every push notification for an account.
- Every job execution history entry for a workflow.
- Per-minute price/inventory ticks across years.
- Every order ID a customer has ever created.
- Embedded base64 files or large thumbnails.
- Retry attempts storing full request/response bodies.

### 12.2. Cardinality Must Be Evaluated Over the Full Lifecycle

An array with 10 items today can have 1 million items in 5 years. Ask:

- What is the **business** maximum number of children per parent?
- What is the daily/monthly growth rate?
- Is each child bounded in bytes?
- Are children queried/written independently?
- Must all children be loaded whenever the parent is loaded?
- Are there retention/TTL/legal hold rules?
- Is there multi-writer contention?

### 12.3. When to Embed?

Generally suitable for **small, bounded child sets typically read and updated alongside the parent**, such as 2–5 billing addresses or 10 UI settings.

### 12.4. When to Reference?

Suitable for **unbounded one-to-many relationships with independent lifecycles and access patterns**, such as order events, comments, notifications, and ledger entries.

---

## 13. Migrating from an Unbounded Array to a Referenced Collection

### 13.1. Old Model

~~~javascript
{
  _id: "ORDER-101",
  status: "PAID",
  events: [
    { id: "E1", type: "CREATED", at: ISODate("2026-11-10T10:00:00Z") },
    { id: "E2", type: "PAID", at: ISODate("2026-11-10T10:05:00Z") }
  ]
}
~~~

### 13.2. New Model

`orders`:

~~~javascript
{
  _id: "ORDER-101",
  tenant_id: "tenant-a",
  status: "PAID",
  event_count: NumberLong("2"),
  latest_event_at: ISODate("2026-11-10T10:05:00Z")
}
~~~

`order_events`:

~~~javascript
{
  _id: "E2",
  tenant_id: "tenant-a",
  order_id: "ORDER-101",
  type: "PAID",
  at: ISODate("2026-11-10T10:05:00Z"),
  schema_version: 1
}
~~~

### 13.3. Recommended Indexes

~~~javascript
db.order_events.createIndex({
  tenant_id: 1,
  order_id: 1,
  at: -1,
  _id: -1
});
~~~

The event's `_id` has a default unique index. If per-order event sequence uniqueness is needed:

~~~javascript
db.order_events.createIndex(
  { tenant_id: 1, order_id: 1, sequence: 1 },
  { unique: true }
);
~~~

### 13.4. Paginated Reads

~~~javascript
db.order_events.find({
  tenant_id: "tenant-a",
  order_id: "ORDER-101"
}).sort({
  at: -1,
  _id: -1
}).limit(50);
~~~

The result is 50 separate documents rather than one giant embedded array inside a single document.

### 13.5. Trade-offs

- Fetching an order + all events requires multiple operations or `$lookup`.
- There is no longer a single-document atomic update spanning both order and every event; transactions/outboxes may be needed.
- Distributed event writes reduce parent-document hotspots.
- Per-event retention/TTL becomes easier.
- Pagination and indexing per event become natural.

---

## 14. Bounded Buckets: Middle Ground Between Embedding and Referencing

Instead of placing every event in one parent document, split them into multiple bucket documents, each capped at e.g. 100 or 500 events.

~~~javascript
{
  _id: "ORDER-101:2026-11:part-01",
  tenant_id: "tenant-a",
  order_id: "ORDER-101",
  bucket: "2026-11",
  part: 1,
  count: 100,
  events: [
    // At most 100 events,
    // with each event bounded in size.
  ]
}
~~~

### 14.1. Benefits

- Reduces document count compared to one document per event.
- Eliminates an endlessly growing parent array.
- Easy retrieval by time/order partition.
- Lets applications read in bounded chunks.

### 14.2. Risks

- A count-bounded bucket can still exceed 16 MiB if payloads are huge.
- Creating new buckets concurrently requires a protocol to prevent duplicate inserts or lost events.
- If many writers append to the same active bucket, contention can be high.
- TTL on a bucket deletes the whole bucket, which may not match per-event retention.

### 14.3. Avoid Naive Race-Prone Bucket IDs

If workers independently compute `part = floor(count/100)` without atomic counters/unique keys, two writers can pick the same part or create gaps. Design bucket allocation and idempotency from the source data.

### 14.4. When Are Buckets Unnecessary?

If event logs are large, require independent queries, per-event retention, or simple correctness guarantees, **one document per event** is usually easier to manage.

---

## 15. GridFS for Large Files/Blobs

When storing PDFs, images, videos, or binary payloads exceeding 16 MiB, MongoDB supports **GridFS**.

GridFS splits files into chunks and stores metadata and chunks in related collections. It does not allow any single BSON document to exceed 16 MiB.

### 15.1. Distinguishing GridFS from Unbounded Arrays

| Data | Modeling direction |
|---|---|
| Single 50 MiB file | GridFS or object storage |
| Millions of small events | Separate events collection |
| 100 most recent notifications | Bounded embedded array |
| Invoice with 5 line items | Embed |
| User with 300,000 orders | References; do not embed all |
| 3 GB of audit attachments | GridFS/object storage per policy |
| Cumulative statistics | Materialized counters/aggregations, not raw event arrays |

### 15.2. Java Sync Driver GridFS

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.MongoDatabase;
import java.io.InputStream;

GridFSBucket bucket =
    GridFSBuckets.create(mongoDatabase, "files");

try (InputStream stream = fileInputStream) {
    var fileId = bucket.uploadFromStream(
        "attachment.pdf",
        stream
    );

    System.out.println(fileId);
}
~~~

This snippet assumes `mongoDatabase` and `fileInputStream` exist. Production files require auth, tenant ownership metadata, MIME validation, checksums, retention, and mid-upload failure handling.

### 15.3. Do Not Blindly Store Unbounded Business Data as a File

Dumping millions of events into one GridFS file avoids 16 MiB, yet makes querying, filtering, indexing, updating, and deduplicating painful. GridFS is for file-like data, not a blanket fix for schema problems.

Documentation: [GridFS](https://www.mongodb.com/docs/manual/core/gridfs/).

---

## 16. Adding Application-Side Size Guardrails

### 16.1. Bounding Event Payloads

For externally received events, enforce:

- Maximum JSON/BSON payload bytes.
- Maximum string length.
- Maximum nesting depth.
- Allowed fields.
- Maximum labels/tags.
- Maximum retained recent events.
- Retry/dedup semantics.

Measure actual bytes rather than character counts alone.

### 16.2. Deliberate Payload Truncation

Never silently truncate payment events or legal audit records. If the purpose is purely diagnostic, store a subset/hash and link to a blob with policy-based TTL.

### 16.3. Using Validators for Array Structure

You can use `$jsonSchema` with `maxItems` where appropriate for the domain:

~~~javascript
db.createCollection("notification_summaries", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        recent_notifications: {
          bsonType: "array",
          maxItems: 100,
          items: {
            bsonType: "object",
            required: ["event_id", "at"]
          }
        }
      }
    }
  }
});
~~~

This only bounds element count and shape appropriately; **it does not replace total document size protection** and does not convert legacy data automatically. Enable validators in a staged rollout after auditing current data.

### 16.4. Conditional Atomic Updates Checking Count?

In some cases, you can check array size in the predicate before pushing, but that **does not replace** `$slice` or payload size caps. Concurrency still needs control and the filter must include exact document/tenant keys.

### 16.5. Application Quotas Should Sit Well Below 16 MiB

16 MiB is the hard ceiling, not a target. Set business quotas low enough to leave headroom for metadata, schema evolution, future fields, and operations.

---

## 17. Why Large Documents Slow Down Systems Even Below 16 MiB

### 17.1. Bandwidth and Latency

A request needing only `status` that reads a multi-MiB document wastes network bandwidth and CPU decoding. Projections shrink client payloads, yet do not turn a hot-document schema into an optimal design for every workload.

### 17.2. Cache Working Set

Large documents consume significant cache space, reducing how many hot records fit in memory. This increases disk I/O and p99 latency.

### 17.3. Write Contention

Multiple writers appending events to the same parent document create hotspots. `mongod` guarantees single-document atomicity, yet concurrent requests contend over the same document.

### 17.4. Index Maintenance

Indexes on nested arrays are multikey indexes; each update can touch numerous index entries, increasing write and replication overhead. Avoid indexing every array field without an actual query workload requiring it.

### 17.5. Replication and Backups

Large writes increase network traffic, oplog/replication load, and recovery complexity. Monitor individual hot-document growth rates, not just total collection size.

### 17.6. Driver Heap

If a Java service calls `findOne` on a large document and maps it into a POJO containing 500,000 nested objects, JVM heap/GC pressure spikes even before the server errors.

---

## 18. Aggregation Pipelines Have Three Independent Limit Categories

~~~text
Input collection
       |
       v
[$match] -> [$project] -> [$group] -> [$sort] -> [$facet]
                            |           |         |
                            |           |         +-- Facet 100 MB cap
                            |           +-- Memory/spill rules
                            +-- Accumulator memory cap
       |
       v
Output docs
       |
       +-- Each BSON result document <= 16 MiB
~~~

### 18.1. Result Size

Every aggregation result document must fit within **16 MiB**. A pipeline may handle **intermediate documents** larger than 16 MiB in certain versions/contexts, yet cannot emit a result document exceeding the limit.

### 18.2. Stage Count

A pipeline allows up to **1,000 stages** per MongoDB docs. The limit applies pre- or post-parsing; dynamic pipeline builders generating thousands of `$project`/`$addFields` stages can exceed it.

### 18.3. Memory

Blocking stages such as `$sort`, `$group`, `$bucket`, `$bucketAuto`, `$setWindowFields`, and `$sortByCount` consume memory. Depending on settings/server version, some can spill to disk above the threshold; some accumulators cannot spill.

### 18.4. Not Fixed the Same Way

- Result >16 MiB → **shrink per-document output** or change the output shape.
- Memory >limit → **reduce state**, use indexes/filters/limits, or spill where supported.
- Stage count >1,000 → **simplify the pipeline/architecture**.
- Timeout → optimize query/data model, indexes, cardinality; do not assume memory limit.
- Client OOM → streaming, projections, batched iteration; never collect an entire cursor into a `List`.

---

## 19. 1,000 Pipeline Stages: Errors from Dynamic Builders

A Java report generator might append a `$project` stage per rule, failing once rules hit 1,001.

### 19.1. Example Generating Unnecessary Stages

~~~javascript
const pipeline = [];

for (let i = 0; i < 1001; i++) {
  pipeline.push({
    $addFields: {
      last_rule: i
    }
  });
}

// Do not run in production:
print(pipeline.length);
~~~

All 1,001 consecutive stages merely overwrite one field with a new rule; this design is flawed.

### 19.2. Diagnostics

- Print the generated pipeline's stage count before sending.
- Log the name/type of each stage without logging sensitive data.
- Inspect stage expansion, nested pipeline builders, and views.
- Check the server release, since parsing/optimization affects effective stage counts.

### 19.3. Remediation

- Combine independent transformations into a single `$project`/`$set` where semantics allow.
- Use `$map`/`$reduce` for array transformations instead of one stage per element.
- Move certain transformations to application code or batch jobs if appropriate.
- Materialize heavy intermediate steps into an intermediate collection via `$merge`, then continue in a shorter pipeline.
- Do not arbitrarily split 1,001 stages across two pipelines if doing so breaks atomic/consistent snapshot assumptions.

### 19.4. Do Not "Raise the Limit" as a Default Workaround

This is a documented engine limit. Fix the pipeline design rather than hunting for unsupported server flags to disable the limit.

---

## 20. Understanding `allowDiskUse`

Starting in MongoDB 6.0, the server parameter `allowDiskUseByDefault` controls whether eligible stages write temporary files to disk by default when memory usage grows high.

### 20.1. Enabling for a Single Aggregate

~~~javascript
db.sales.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $group: {
      _id: "$customer_id",
      total_minor: { $sum: "$amount_minor" }
    }
  },
  {
    $sort: {
      total_minor: -1
    }
  },
  { $limit: 100 }
], {
  allowDiskUse: true
});
~~~

### 20.2. Disabling Spill for Control

~~~javascript
db.sales.aggregate(
  [
    { $sort: { amount_minor: -1 } },
    { $limit: 100 }
  ],
  {
    allowDiskUse: false
  }
);
~~~

If an unindexed sort exceeds the threshold, a memory error is returned. This does not indicate data corruption; it is a resource limit signaling a need for optimization.

### 20.3. Disk Spill Is Not Free

Disk spills can cause:

- Sharp temporary I/O spikes.
- Slower queries.
- Storage contention.
- Quota/ephemeral storage pressure.
- Unstable performance under concurrency.

### 20.4. What `allowDiskUse` Does Not Fix

- BSON documents >16 MiB.
- `$facet` documents >100 MB, because `$facet` does not spill.
- `$group` accumulator arrays exceeding their own limit.
- Pipelines >1,000 stages.
- Missing indexes causing slow joins regardless.
- Client heap OOM from `toArray()`/collecting an entire cursor.

### 20.5. Per-Operation Total Memory Limits

Newer MongoDB versions enforce a **per-operation memory limit** separate from per-stage limits. If an operation exceeds it, spilling alone may not suffice. Check error messages, server version, config, and metrics like `metrics.query.peakMemoryUsageOperation` or `metrics.query.operationsFailedDueToMemoryLimit` when exposed by the server. Never alter internal server parameters in production by default.

---

## 21. `$sort` Exceeding Memory Limits

### 21.1. Error-Prone Pipeline

~~~javascript
db.events.aggregate([
  { $sort: { created_at: -1 } }
], {
  allowDiskUse: false
});
~~~

Without a supporting index on a very large dataset, MongoDB must buffer large sort state.

### 21.2. Creating a Supporting Index

~~~javascript
db.events.createIndex({
  tenant_id: 1,
  created_at: -1,
  _id: -1
});
~~~

Query:

~~~javascript
db.events.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $sort: {
      created_at: -1,
      _id: -1
    }
  },
  { $limit: 50 },
  {
    $project: {
      _id: 1,
      type: 1,
      created_at: 1
    }
  }
]);
~~~

The index can satisfy both filter and sort depending on the actual query plan. Confirm with `explain`.

### 21.3. Match Early, Place Limit Properly

- Early `$match` shrinks the input set when semantics allow.
- `$sort` followed by `$limit` can optimize into a top-k sort.
- Placing `$limit` before `$sort` **changes the result**, sorting only a subset.
- `$project` shrinks payloads, yet does not magically create an index sort.

### 21.4. Sorting on Missing or Mistyped Fields

If `created_at` mixes strings and BSON Dates, ordering will differ from business expectations. Fix schema/migrations rather than just enabling disk spill.

---

## 22. `$group` with `$push:"$$ROOT"` Creating Giant Arrays

A common failing pipeline:

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      events: {
        $push: "$$ROOT"
      }
    }
  }
], {
  allowDiskUse: true
});
~~~

If an order has 500,000 events, the `events` accumulator holds every document, easily hitting memory limits or the 16 MiB result limit.

### 22.1. Why `allowDiskUse` Is Insufficient

`$group` can spill certain **group state**, yet accumulator values such as `$push`/`$addToSet` cannot spill arbitrarily. If a single array accumulator grows too large, the stage fails even with `allowDiskUse:true`.

### 22.2. When You Only Need Counts

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      event_count: { $sum: 1 }
    }
  }
]);
~~~

Return scalar counts rather than collecting every raw event into an array.

### 22.3. When You Need Totals

~~~javascript
db.order_events.aggregate([
  {
    $match: {
      type: "PAYMENT_APPLIED"
    }
  },
  {
    $group: {
      _id: "$order_id",
      total_minor: {
        $sum: "$amount_minor"
      }
    }
  }
]);
~~~

### 22.4. When You Need Top N Recent Items Per Group

Use `$topN`/`$firstN` on supported server versions, or `$setWindowFields` with partition ranking, while bounding N and checking memory/indexes. If full history is required, **return documents via a paginated cursor** instead of cramming them into one result document.

### 22.5. `$addToSet` Does Not Solve the Fundamental Issue

An array of millions of **unique** IDs is still huge. Deduplication does not equal bounded size.

Documentation: [`$group` Memory Restrictions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).

---

## 23. `$facet`: 100 MB Limit and 16 MiB Result Limit

`$facet` executes multiple sub-pipelines over the same input and returns a single result document containing arrays:

~~~javascript
db.products.aggregate([
  {
    $facet: {
      byCategory: [
        {
          $group: {
            _id: "$category",
            count: { $sum: 1 }
          }
        }
      ],
      byBrand: [
        {
          $group: {
            _id: "$brand",
            count: { $sum: 1 }
          }
        }
      ]
    }
  }
]);
~~~

### 23.1. Two Separate Thresholds

- Inside `$facet`, each resulting document has a **100 MB** limit.
- `$facet` **does not spill to disk**, so `allowDiskUse:true` does not raise that cap.
- The final output remains subject to the **16 MiB BSON document limit**.

### 23.2. Misusing Facets

~~~javascript
db.events.aggregate([
  {
    $facet: {
      allEvents: [
        { $sort: { at: -1 } }
      ],
      counts: [
        { $count: "n" }
      ]
    }
  }
], {
  allowDiskUse: true
});
~~~

Unbounded `allEvents` can grow into a massive array.

### 23.3. Bounded Facets

~~~javascript
db.events.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $facet: {
      page: [
        { $sort: { at: -1, _id: -1 } },
        { $limit: 20 },
        {
          $project: {
            _id: 1,
            type: 1,
            at: 1
          }
        }
      ],
      total: [
        { $count: "value" }
      ]
    }
  }
]);
~~~

`page` holds only 20 documents and `total` returns a small count. Still, `$facet` can incur heavy scan/count costs; for large workloads, split pagination and counting into two requests.

### 23.4. When Do Indexes Help?

`$facet` at the very start of a pipeline can force a collection scan. Place `$match` (and index-friendly stages) before `$facet` when semantics allow.

### 23.5. Do Not "Fix Facets" by Raising `batchSize`

Batch size controls how many result documents sit in a cursor batch; it does not shrink a single facet output document carrying huge arrays.

Documentation: [`$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/).

---

## 24. `$lookup` and Join Fan-Out Creating Large Outputs

Example:

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "order_events",
      localField: "_id",
      foreignField: "order_id",
      as: "all_events"
    }
  }
]);
~~~

If an order has 500,000 events, `all_events` becomes a massive array.

### 24.1. Why Is Join Fan-Out Dangerous?

One input order gets "inflated" with all matching foreign documents. A tiny input document can balloon into a huge document/intermediate, pushing the pipeline toward BSON output and memory limits.

### 24.2. Filter, Project, and Limit Inside Lookup Pipelines

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      _id: "ORDER-101"
    }
  },
  {
    $lookup: {
      from: "order_events",
      localField: "_id",
      foreignField: "order_id",
      pipeline: [
        { $sort: { at: -1, _id: -1 } },
        { $limit: 10 },
        {
          $project: {
            _id: 1,
            type: 1,
            at: 1
          }
        }
      ],
      as: "recent_events"
    }
  }
]);
~~~

This intentionally retrieves only the 10 latest events rather than full history. Create an appropriate foreign index:

~~~javascript
db.order_events.createIndex({
  order_id: 1,
  at: -1,
  _id: -1
});
~~~

In multi-tenant data, also ensure the foreign join cannot cross tenants (e.g., composite keys, `let` + `$expr`, or modeled event ownership)—do not filter tenant only on the parent.

### 24.3. `$lookup` vs. `$unwind`

`$lookup` produces an array. `$unwind` turns array elements into separate documents. If the final goal is a stream of rows, use `$unwind`/`$project` without packing all rows back into an array afterward.

### 24.4. Unindexed Joins

`$lookup` without an index on the foreign field can be terribly slow. Inspect execution plans and index selectivity, especially for correlated subqueries. Never enable `allowDiskUse` merely to mask an unindexed join.

### 24.5. When Full History Is Needed

Query `order_events` directly by `order_id` with pagination. Do not force-join all events into the order document simply because an API endpoint takes an order ID.

---

## 25. `$unwind`: Row Explosion

An input document with 50,000 array elements becomes 50,000 pipeline documents after `$unwind`:

~~~javascript
db.orders.aggregate([
  { $unwind: "$items" }
]);
~~~

If followed by `$lookup` per item, total work grows multiplicatively across fan-out factors.

### 25.1. Document Count vs. Document Size

`$unwind` increases row count, memory, CPU, disk, and runtime, even though each unwound document may be smaller than the input. The failure is not necessarily 16 MiB per document.

### 25.2. Match Before and After Unwind

To filter orders by tenant and items by SKU:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      "items.sku": "SKU-1"
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "SKU-1"
    }
  },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.quantity"
    }
  }
]);
~~~

The first `$match` narrows parent docs; the post-unwind `$match` retains only matching elements.

### 25.3. Use `$filter` When You Only Need a Small Subarray

For documents with reasonably sized arrays, `$filter` selects elements without emitting a separate row per element. Still, the resulting array must remain bounded; never use `$filter` to accumulate unbounded data.

### 25.4. Do Not Re-Group into Unbounded `$push:"$$ROOT"`

If a pipeline unwinds 1 million elements and groups them back into a 1-million-object array, you land right back on the original error with higher resource cost.

---

## 26. Cursors and Pagination: Avoiding One Giant Document

If an API needs event history:

~~~javascript
db.order_events.find({
  tenant_id: "tenant-a",
  order_id: "ORDER-101"
}).sort({
  at: -1,
  _id: -1
}).limit(50);
~~~

### 26.1. Cursors Return Multiple BSON Documents

A MongoDB cursor streams multiple batches. The 16 MiB limit applies to **each document**, not the entire history read through the cursor.

### 26.2. Keyset Pagination

When sorting by `at DESC, _id DESC`, fetch the next page using the last item's values:

~~~javascript
const lastAt = ISODate("2026-11-13T10:00:00Z");
const lastId = "evt-900";

db.order_events.find({
  tenant_id: "tenant-a",
  order_id: "ORDER-101",
  $or: [
    { at: { $lt: lastAt } },
    {
      at: lastAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  at: -1,
  _id: -1
}).limit(50);
~~~

This example assumes `_id` is a stably ordered string. If `_id` is an `ObjectId` or mixed types, pagination tokens must preserve exact BSON types and sort semantics.

### 26.3. Why Is Large `skip` Suboptimal?

`skip(1000000)` forces the server to scan and discard huge numbers of results. Keyset pagination using a matching index performs far better for deep histories.

### 26.4. Pagination Tokens Must Bind Tenant/Filter/Sort Identity

Never let a client reuse a token belonging to another tenant. Sign/validate tokens or store state appropriately, checking sort order and required snapshot consistency.

---

## 27. 16 MiB Pipeline Output: When `$group` Builds an Array

Suppose a pipeline intends to return statistics yet builds:

~~~javascript
db.sales.aggregate([
  {
    $group: {
      _id: "$customer_id",
      invoices: {
        $push: "$$ROOT"
      }
    }
  }
]);
~~~

Each `customer_id` yields one document holding all invoices for that customer. A large customer exceeds 16 MiB.

### 27.1. Fix According to Requirements

If the API only needs total amount and invoice count:

~~~javascript
db.sales.aggregate([
  {
    $group: {
      _id: "$customer_id",
      invoice_count: {
        $sum: 1
      },
      total_minor: {
        $sum: "$amount_minor"
      }
    }
  }
]);
~~~

If the 20 latest invoices are needed, query `sales` directly using a `customer_id` index and `limit`, or use a bounded top-N strategy.

### 27.2. Output Documents Need Not Match Source Document Sizes

Even if no document in a collection exceeds 1 MiB, an aggregation can produce an output document >16 MiB via `$group` or `$lookup`.

### 27.3. `$merge`/`$out` Do Not Make a >16 MiB Document Valid

Writing aggregation results to a collection does not lift the per-document BSON limit. `$merge` works well for **many small documents with clear keys**—such as one scalar summary per customer—not a giant array.

---

## 28. Materialized Summaries Instead of Raw History

If a dashboard needs "revenue per customer," build a small summary:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $group: {
      _id: {
        tenant_id: "$tenant_id",
        customer_id: "$customer_id"
      },
      paid_count: { $sum: 1 },
      total_minor: { $sum: "$amount_minor" }
    }
  },
  {
    $merge: {
      into: "customer_sales_summary",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
], {
  allowDiskUse: true
});
~~~

### 28.1. Why Is This Better Than Pushing All Invoices?

A summary stores counts and totals rather than growing linearly with invoice volume. Raw invoices remain in the source collection for historical queries.

### 28.2. Freshness

Summaries become stale if updated only by a daily job. Define a freshness SLA, incremental updates/change streams, reconciliation, and handling for deletes/late events.

### 28.3. Numeric Overflow

`$sum` behavior depends on BSON numeric types; for money, use `NumberLong` minor units or `Decimal128` per business contract and check for overflow/precision.

### 28.4. Do Not Delete Source Data Prematurely

`$merge` creates a summary, not a backup or transaction ledger. Retain raw data per retention and audit policies.

---

## 29. Java Sync Driver: Analyzing Document Size

Java example using `$bsonSize` aggregation to list top documents:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;
import java.util.concurrent.TimeUnit;

public class LargeDocumentDiagnostic {

    public static void inspect(MongoDatabase database) {

        MongoCollection<Document> orders =
            database.getCollection("orders");

        List<Document> pipeline = List.of(
            new Document("$project",
                new Document("_id", 1)
                    .append("tenant_id", 1)
                    .append("bson_bytes",
                        new Document(
                            "$bsonSize",
                            "$$ROOT"
                        )
                    )
            ),
            new Document("$sort",
                new Document("bson_bytes", -1)
            ),
            new Document("$limit", 20)
        );

        orders.aggregate(pipeline)
            .allowDiskUse(true)
            .maxTime(20, TimeUnit.SECONDS)
            .forEach(doc -> {
                System.out.println(
                    doc.get("_id")
                    + " bytes="
                    + doc.get("bson_bytes")
                );
            });
    }
}
~~~

### 29.1. Never Call `into(new ArrayList<>())` on Unbounded Data

If an aggregation returns 5 million records, collecting all of them into a `List` can OOM the JVM. Iterate the cursor in batches and stream/process bounded outputs.

### 29.2. `maxTime` Protects the Resource Budget

`maxTime` bounds operation duration under supported conditions; it does not fix data modeling issues and does not guarantee a query will complete.

### 29.3. Diagnostic Queries Also Need Authorization and Scope

Run on staging, a sampled tenant, or off-peak—never scan an entire massive collection when the server is already overloaded. Never log raw sensitive document contents.

---

## 30. Spring Data MongoDB: Bounded Array Updates

To retain only N event previews on an entity, you can use `MongoTemplate`:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import java.util.Date;

public class RecentEventWriter {

    private final MongoTemplate template;

    public RecentEventWriter(MongoTemplate template) {
        this.template = template;
    }

    public void addPreview(
            String orderId,
            String tenantId,
            String eventId,
            String type) {

        Document preview = new Document()
            .append("event_id", eventId)
            .append("type", type)
            .append("at", new Date());

        Query query = Query.query(
            Criteria.where("_id").is(orderId)
                .and("tenant_id").is(tenantId)
        );

        Update update = new Update()
            .push("recent_events")
            .each(preview)
            .sort(
                org.springframework.data.domain
                    .Sort.by(
                        org.springframework.data.domain
                            .Sort.Direction.DESC,
                        "at"
                    )
            )
            .slice(100);

        template.updateFirst(
            query,
            update,
            "orders"
        );
    }
}
~~~

This example uses collection names and physical BSON field names to avoid confusion with Java property mapping. `PushOperatorBuilder` API signatures depend on Spring Data version; verify against your project's Javadoc.

### 30.1. Why Not Embed Raw Events?

The recent preview stores only `event_id`, `type`, and `at`. Raw payloads live in `order_events`, while the preview acts as a small cache.

### 30.2. Failure Semantics

If the preview update fails after the raw event is saved, data is not necessarily lost; the preview can be rebuilt from the source of truth. Establish the source of truth clearly from the start.

### 30.3. `$slice` Does Not Replace Deduplication

Two events with the same ID can coexist in the preview upon retry. If uniqueness is needed, rebuild the projection from source events/idempotency keys or use `$addToSet` when element equality suffices.

---

## 31. Java Driver: Handling Errors Instead of Infinite Retries

Pseudo-service:

~~~java
public void appendEvent(Event event) {

    try {
        // Insert event into order_events using a stable event ID.
        eventRepository.insertIfAbsent(event);

        // Update recent preview (best effort).
        orderPreviewRepository.appendBounded(event);

    } catch (RuntimeException ex) {

        // Do not blindly retry $push:
        // it can create duplicates and bloat the document further.
        // Record metrics and request/event ID for reconciliation.
        throw ex;
    }
}
~~~

`Event`, `eventRepository`, and `orderPreviewRepository` are illustrative abstractions, not MongoDB Driver classes.

### 31.1. Classifying Exceptions

- **Permanent/schema:** document too large, invalid type, bad field name → fix model/payload; do not retry unchanged.
- **Transient network/topology:** evaluate retryable semantics per driver/operation.
- **Unknown write outcome:** re-query using the stable event ID/operation ID.
- **Insufficient permission:** fix privilege/config; do not hammer retries.
- **Aggregation memory:** optimize pipeline or spill if appropriate.

### 31.2. Never Silently Drop Required Data

If a payment event fails to save, do not strip `details` and return success when mandatory data was lost. Tailor error handling to criticality and retention policy.

---

## 32. Runbook When Insert/Update Reports BSON Document Too Large

### Step 1 — Assess Severity

- Does it affect all requests or one tenant/document?
- Is source data lost, or still queued?
- Is the application in a retry storm amplifying load?
- Since which release/schema did the error begin?
- Which feature is appending heavily?

### Step 2 — Stabilize the System

- Throttle or pause the risky append writer via feature flag if permitted.
- Enforce retry backoff and dead-letter/quarantine queues.
- Do not increase worker concurrency to "push through errors."
- Do not delete historical data before backing it up/copying it.

### Step 3 — Identify the Document

- Capture authorized ID/tenant.
- Measure `$bsonSize` of the document.
- Check `$size` of key arrays.
- Identify the fast-growing component: events, attachments, snapshots, comments.
- Compare against baselines/other records.

### Step 4 — Choose the Fix Category

- File/blob → GridFS/object storage.
- Unbounded one-to-many → referenced collection.
- Recent items → bounded array.
- Summary/report → scalar materialization.
- Retry duplicates → idempotency.
- Oversized raw payload → validate/reject/store externally.

### Step 5 — Validate in Staging

Copy a representative document, run the migration, and execute read/write tests. Ensure old/new app versions do not break new fields/arrays.

### Step 6 — Controlled Migration

Backfill child documents, verify counts/values, switch writer ownership, trim legacy arrays only after approval, and verify rollback.

### Step 7 — Monitor

Track p95/p99 document size, error counts, write latency, replication lag, CPU/IO, queue backlog, and failure recovery.

---

## 33. Runbook When Aggregation Exceeds Memory

### Step 1 — Find the Failing Stage

Read the stack trace, server profiler logs, and pipeline execution context. Check:

- Unindexed `$sort`?
- `$group` with `$push:"$$ROOT"`?
- `$facet` collecting unbounded arrays?
- High-cardinality `$lookup`?
- `$unwind` multiplying rows?
- `$setWindowFields` holding large state?
- Thousands of dynamically generated pipeline stages?

### Step 2 — Identify the Limit Type

- `BSONObjectTooLarge` → single result document size.
- `ExceededMemoryLimit` → stage/accumulator/per-op.
- `$facet` output limit → facet cannot spill.
- `sort no disk` → solvable via index/top-k/spill.
- `1000 stages` → structural pipeline issue.

### Step 3 — Apply Low-Risk Changes

- Move `$match` earlier.
- Add indexes supporting filter/sort/join.
- Project only needed fields.
- Place `$limit` **preserving semantics**.
- Reduce join cardinality/foreign projection.
- Use pagination/cursors instead of huge arrays.
- Enable `allowDiskUse` only when the stage supports it and disk budget suffices.

### Step 4 — Change the Output Shape

If the API truly needs history, return paginated rows. If it only needs statistics, return counts/sums/top-N. If dashboards need precomputed values, use materialized views.

### Step 5 — Load Test Realistic Cardinality

Small lab datasets fail to reproduce large-group cardinality or p99 memory. Test in production-like staging and measure peak memory, spills, disk I/O, latency, and error rates.

---

## 34. Observing with `explain`, Profiler, and Logs

### 34.1. Explaining a Pipeline

~~~javascript
db.order_events.explain("executionStats").aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      order_id: "ORDER-101"
    }
  },
  {
    $sort: {
      at: -1
    }
  },
  { $limit: 50 }
]);
~~~

Inspect plan/index selection, documents examined, keys examined, and stage behavior. Explain output formats evolve across server versions.

### 34.2. `usedDisk`

MongoDB profiler/diagnostic logs may report `usedDisk` when a stage writes temporary files due to memory pressure. Monitor spill frequency and magnitude under heavy workloads.

### 34.3. Do Not Enable High-Level Profiling Indiscriminately

Profiling adds overhead and logs sensitive query parameters. Enable only per SRE procedure with explicit duration/scope, respecting Atlas/managed constraints.

### 34.4. `serverStatus` (When Available and Authorized)

Newer server versions expose query memory metrics such as:

~~~text
metrics.query.peakMemoryUsageOperation
metrics.query.operationsFailedDueToMemoryLimit
metrics.query.configuredMaxMemoryUsageBytesPerOperation
~~~

Do not assume every version exposes all these fields. Run `db.serverStatus()` with appropriate privileges and consult release docs.

### 34.5. App Metrics

| Metric | Meaning |
|---|---|
| `bson_document_size_bytes_p95` | High-percentile document size |
| `bson_document_size_bytes_max` | Tail risk |
| `unbounded_array_length_p99` | How large arrays are growing |
| `bson_too_large_errors_total` | Failed writes/aggregates |
| `aggregation_memory_errors_total` | Stage memory errors |
| `aggregation_spill_queries_total` | Queries forced to spill |
| `aggregation_timeout_total` | Unfinished queries |
| `bulk_retry_count` | Retry storms |
| `large_document_migration_backlog` | Records awaiting migration |
| `event_ingest_lag_seconds` | Pending source data |
| `orders_update_latency_p99` | Write contention |
| `replica_lag_seconds` | Replication pressure |

Metric names are illustrative for instrumentation, not MongoDB built-in names.

---

## 35. Distinguishing Result Size from API Response Size

### 35.1. Scenario 1: MongoDB Result Valid, HTTP Returns 413

If an API bundles 10,000 small documents into one huge JSON response, MongoDB streams the cursor cleanly, yet the reverse proxy/API gateway rejects the response size.

### 35.2. Scenario 2: MongoDB Result Document Already Exceeded 16 MiB

A `$group` packing 10,000 records into an array inside **one document** fails inside MongoDB before an HTTP response is even constructed.

### 35.3. Scenario 3: Java Client OOM

The application calls:

~~~java
List<Document> all = collection.find()
    .into(new ArrayList<>());
~~~

Even if every document is valid, loading the entire cursor into a `List` exhausts JVM heap. Use cursor streaming and pagination instead of eager materialization.

### 35.4. Scenario 4: GUI/Shell Display Truncated

A MongoDB GUI or `mongosh` may truncate printed output. That **does not prove the database truncated the data**. Inspect raw BSON/query results and client logs.

### 35.5. Fix the Right Layer

Do not raise gateway limits to cure a single-document `BSONObjectTooLarge`; do not enable `allowDiskUse` to cure a Java heap OOM caused by `List`.

---

## 36. Migrating from a Giant Array to a Collection: Safe Plan

Suppose `orders.events` has swelled to 14 MiB.

### Phase 0 — Inventory and Source of Truth

- Identify all writers appending events.
- Identify all readers consuming `orders.events`.
- Verify unique event IDs exist or how stable IDs can be derived.
- Take a backup/snapshot and test restoring it.
- Confirm retention/legal hold requirements.
- Verify MongoDB version/topology.

### Phase 1 — Expand Code

- New writers write events to `order_events`.
- New readers read both legacy embedded arrays and the new collection.
- Prevent double-counting when an event exists in both places.
- If old writers still append to the array, maintain a compatibility window + catch-up strategy.
- Do not delete legacy events early.

### Phase 2 — Backfill Per Order

- Read orders with a focused projection.
- Enumerate legacy events.
- Derive stable `event_id` values—never generate random IDs on retry.
- Upsert by `event_id`/business identity.
- Record checkpoints per order/batch; never embed markers inside documents near 16 MiB.
- Apply throttling, checkpoints, and metrics.

### Phase 3 — Catch-Up

- Stop/retire old writers.
- Copy events appended after initial backfill.
- Reconcile event IDs, counts, and fields—not just total counts.
- Use Change Streams/outboxes if online sync is needed, handling lag, duplicates, and restarts.

### Phase 4 — Cutover

- API reads from `order_events` with pagination.
- Bounded `recent_events` can be rebuilt from the collection.
- Verify latency, consistency, permissions, and search/indexes.

### Phase 5 — Contract

- Remove legacy arrays only after business sign-off.
- Ensure audit copies satisfy retention requirements.
- Remove old indexes/code/flags per procedure.
- Keep a rollback path for the agreed window.

---

## 37. Idempotent Event Backfill: `mongosh` Example

Assume legacy array elements have a stable `id` field. For a single small order in a lab:

~~~javascript
const order = db.orders.findOne(
  { _id: "ORDER-101", tenant_id: "tenant-a" },
  { events: 1, tenant_id: 1 }
);

if (order && Array.isArray(order.events)) {
  for (const event of order.events) {
    if (!event.id) {
      throw new Error("Legacy event missing stable id");
    }

    db.order_events.updateOne(
      {
        _id: event.id
      },
      {
        $setOnInsert: {
          tenant_id: order.tenant_id,
          order_id: order._id,
          type: event.type,
          at: event.at,
          payload: event.payload
        }
      },
      {
        upsert: true
      }
    );
  }
}
~~~

### 37.1. Limitations of This Example

- Illustrates only idempotency via a stable event ID.
- Does not process an entire collection or hundreds of thousands of events in one call.
- Does not handle event ID collisions across tenants; composite/stable `_id` and unique indexes may be required.
- If source events lack IDs, derive deterministic identities from source ordering/payloads and check for collisions—never blindly hash payloads assuming identical-looking events are duplicates.
- Does not catch up concurrent updates.
- Lacks bulk error classification/checkpointing.
- `$setOnInsert` does not update an event if the source mutates; define an event immutability/repair contract.

### 37.2. Production Should Use Batches

Read by order/tenant, write in bounded bulk chunks, track operation IDs and checkpoints, and monitor failures. Retrying an entire batch is safe only when operations are idempotent and uniqueness is protected.

### 37.3. Never `$unset events` Before Reconciliation

If you drop the legacy array and later discover an event failed to copy, history can be lost. Always verify completeness and consistency before removing legacy fields.

---

## 38. When a Document Can No Longer Be Updated Because It Is Too Large

### 38.1. Adding Another Field Is Not a Fix

If a document is already near 16 MiB, adding `needs_migration:true` may fail. Use a separate migration-control collection rather than enlarging the document you are trying to rescue.

### 38.2. Embedded Data Must Be Reduced

You can drop a field or truncate an array **after** backing up/migrating the data that must be retained. Never delete data just to bring a service back up without understanding business/audit consequences.

### 38.3. Concurrency When Removing the Old Field

~~~text
T1 Backfill reads events=[E1..E100]
T2 Old writer appends E101
T3 Migration unsets events
-> E101 can be lost.
~~~

Fix: stop/drain old writers, capture deltas and run final reconciliation, or use CAS/version/transaction patterns appropriate to your topology. Do not rely purely on "backfill finished" timing.

### 38.4. Do Not Restore a Full Database Snapshot Because One Document Failed

Restoring the entire deployment risks losing recent valid writes in unrelated collections. Only restore per an incident/backup plan with approved RPO/RTO.

### 38.5. Immutable Source History

If raw events form a critical ledger, preserve source copies/chunk checksums and verify readability before deletion. Maintain a migration audit log.

---

## 39. Sharded Cluster Warnings

### 39.1. Sharding Does Not Increase the 16 MiB Per-Document Limit

Sharding distributes **multiple documents** across shards. A 20 MiB document does not become valid simply because a collection is sharded.

### 39.2. A Hot Single Document Remains a Hotspot

An order with millions of events still lives in one document on one shard. Adding shards does not split writes targeting a single document.

### 39.3. Referenced Collections Distribute More Easily

When extracting events into separate documents, choose shard keys/indexes suited to queries and tenant isolation. Never pick a random shard key just to avoid hotspots if it forces scatter-gather queries across the whole cluster.

### 39.4. Cross-Shard `$lookup` and Aggregations

Joins/aggregations may fan out across `mongos` and shards, increasing network overhead. Check `explain`, data placement, and server version. Never assume local replica set performance matches sharded production.

### 39.5. Backup and Migration Consistency

Copying data between collections on a sharded cluster requires controlling ongoing writes, using transactions, or CDC/reconciliation; multiple independent cursors without a protocol do not guarantee a cluster-wide consistent snapshot.

---

## 40. Security, Reliability, and Operations

### 40.1. Unbounded Client Payloads

An API accepting arbitrary arrays from clients can be abused to cause document bloat/DoS. Enforce request size, element count, nesting depth, and allowed-field limits.

### 40.2. Never Log Entire Giant Documents

Printing `Document.toJson()` to application logs can emit multi-MiB log lines, leak PII/tokens, and overwhelm the logging pipeline. Log IDs, sizes, counts, statuses, and bounded redacted samples.

### 40.3. Do Not Blindly Raise Memory or Internal Server Parameters

Raising memory caps can let concurrent pipelines compete cluster-wide and OOM nodes. Prioritize reducing cardinality, adding indexes, pagination, and materialization.

### 40.4. Tenant Guardrails

Diagnostic and migration queries must enforce tenant authorization. In production, never export sample documents into public logs or tickets.

### 40.5. Backpressure

If an append job fails due to document size, route to a durable dead-letter queue, bound retries, and enable repair. Never let an infinite loop trigger a retry storm.

### 40.6. Version Compatibility

Features like update pipelines, `$bsonSize`, GridFS driver APIs, and newer aggregation accumulators carry server/driver version requirements. Verify support before deploying examples to production.

---

## 41. Checklist for Document-Too-Large Incidents

### 41.1. Incident Classification

- [ ] Identified error class/message/stack trace.
- [ ] Identified operation: insert/update/aggregate/read/client.
- [ ] Recorded server/driver versions.
- [ ] Recorded authorized request/tenant/document IDs.
- [ ] Ruled out gateway/Java heap limits.
- [ ] Identified data source and business criticality.

### 41.2. Size Diagnostics

- [ ] Measured `$bsonSize:"$$ROOT"` for suspect documents/groups.
- [ ] Measured array counts with `$isArray` guard.
- [ ] Measured p95/p99/max or top-N samples.
- [ ] Verified `avgObjSize` is not hiding tail outliers.
- [ ] Identified fast-growing fields/arrays/payloads.
- [ ] Checked for retry duplicates and write rate spikes.
- [ ] Avoided overloading production with full scans during the incident.

### 41.3. Remediation

- [ ] Stopped further bloating appends.
- [ ] Secured backups and verified retention.
- [ ] Selected bounded array/references/buckets/GridFS per use case.
- [ ] Designed idempotency and unique IDs.
- [ ] Established migration, checkpointing, catch-up, and reconciliation.
- [ ] Avoided deleting legacy fields prior to verification.
- [ ] Avoided breaking older app versions during rollout.
- [ ] Set application quotas below 16 MiB with alerting metrics.

---

## 42. Checklist for Pipeline Limit Incidents

- [ ] Distinguished result doc >16 MiB, stage memory, facet, accumulator, or stage count.
- [ ] Captured full pipeline and appropriate `explain`.
- [ ] Excluded secrets/raw PII from pipeline logs.
- [ ] Placed `$match` early without altering semantics.
- [ ] Added indexes for filters/sorts/joins.
- [ ] Placed `$sort + $limit` properly.
- [ ] Bounded `$lookup` fan-out and foreign projections.
- [ ] Avoided `$group` pushing all `$$ROOT` into arrays when only counts/sums are needed.
- [ ] Avoided `$facet` collecting unlimited arrays.
- [ ] Used `allowDiskUse` only when stages support it and disk budget suffices.
- [ ] Monitored `usedDisk`/per-operation memory where supported.
- [ ] Enforced `maxTimeMS` and query timeout policies.
- [ ] Used cursors/pagination for large result sets.
- [ ] Avoided materializing entire cursors into JVM heap.
- [ ] Kept stage count under 1,000.
- [ ] Tested against production-representative workload/cardinality.

---

## 43. Common Misconceptions

**Misconception 1:** "A MongoDB collection is capped at 16 MiB."  
No. 16 MiB applies **per BSON document**.

**Misconception 2:** "A MongoDB query returns at most 16 MiB total."  
A cursor can stream many documents across multiple batches; each individual document is subject to the limit.

**Misconception 3:** "Increasing `batchSize` lets MongoDB return a 20 MiB document."  
No; `batchSize` does not alter the per-document limit.

**Misconception 4:** "Enabling `allowDiskUse` raises the BSON limit to 100 MB."  
No. Disk spill is separate from document size.

**Misconception 5:** "`$facet` will spill if `allowDiskUse` is enabled."  
No; `$facet` has its own non-spilling limit.

**Misconception 6:** "If `$group` spills, the `$push` accumulator spills indefinitely too."  
No; array accumulators have their own limits.

**Misconception 7:** "If no document in the collection is large, an aggregation cannot produce a large document."  
`$group` and `$lookup` can assemble huge output documents.

**Misconception 8:** "`$addToSet` stops arrays from growing."  
It only skips exact duplicate values; distinct values remain unbounded.

**Misconception 9:** "Capping element count guarantees staying under 16 MiB."  
A single oversized element can still push the document over.

**Misconception 10:** "Sharding makes a 20 MiB document valid."  
No; sharding distributes multiple documents across shards.

**Misconception 11:** "GridFS can replace any embedded document."  
GridFS is designed for file-like binary data, not arbitrary schemas.

**Misconception 12:** "One parent document can serve as an audit log forever."  
Unbounded appends cause size failures and hotspots.

**Misconception 13:** "`$slice` acts like a backup log."  
It discards older entries from the bounded array.

**Misconception 14:** "`$pull` removing events can be run arbitrarily to fix size errors."  
Doing so risks losing audit/business data.

**Misconception 15:** "Small `avgObjSize` means there are no outliers."  
Averages easily mask huge tail documents.

**Misconception 16:** "`$unwind` only shrinks output."  
It can multiply row counts dramatically, consuming heavy resources.

**Misconception 17:** "`$lookup` needs no index if disk spill is enabled."  
Unindexed joins remain severely slow.

**Misconception 18:** "`$limit` produces the same result anywhere in the pipeline."  
Placing it before `$sort`/`$group` alters semantics.

**Misconception 19:** "`$group` always has to retain all raw records."  
Many reports only need `$sum`/`$count`/scalars.

**Misconception 20:** "`$facet` is safe for unbounded pagination."  
Facet arrays are still bounded.

**Misconception 21:** "A MongoDB server memory error means Java ran out of heap."  
Those are two separate layers.

**Misconception 22:** "Client OOM proves the server BSON limit is too low."  
Often caused by collecting an entire cursor in the JVM.

**Misconception 23:** "HTTP 413 means MongoDB could not store the document."  
Often a proxy/API gateway limit.

**Misconception 24:** "Retrying the same `$push` will self-heal."  
It can add duplicates, increase load, and worsen the failure.

**Misconception 25:** "Right after backfill finishes, the legacy array can be deleted immediately."  
You must drain old writers and perform final reconciliation first.

**Misconception 26:** "A document near max can still accept migration metadata."  
There may not be enough bytes left.

**Misconception 27:** "`$addToSet` enforces unique event IDs inside subdocuments."  
It does not enforce uniqueness by subfield.

**Misconception 28:** "`maxTimeMS` fixes out-of-memory queries."  
It bounds time, not data shape.

**Misconception 29:** "Enabling the profiler cluster-wide during an incident is free."  
It adds overhead and risks logging sensitive data.

**Misconception 30:** "No errors after the fix means we are done."  
Continue monitoring sizes, backlogs, correctness, and data loss.

---

## 44. Practice Exercises

### Exercise 1 — Measuring BSON Bytes

Create three documents of different sizes and use `$bsonSize:"$$ROOT"` to measure each document's byte size.

### Exercise 2 — JSON vs. BSON

Create a document with a Vietnamese Unicode string and an ObjectId; explain why `JSON.stringify().length` does not equal BSON bytes.

### Exercise 3 — Finding Top-20

Find the 20 largest documents in the lab, projecting `_id` and `bson_bytes`, sorted descending.

### Exercise 4 — Array Length

Some documents omit `audit_events`, some have an array, and one has a mistyped field. Use `$isArray` and `$size` to diagnose without throwing errors.

### Exercise 5 — Simulating Growth

Append 1,000 events to an order in the lab in small batches; measure size/count after each batch. Never generate 16+ MiB blobs in production.

### Exercise 6 — Bounded Push

Keep the 100 latest events with `$push + $each + $sort + $slice`. Test appending 120 events.

### Exercise 7 — Duplicate Events

Use `$addToSet` with two events sharing the same `event_id` but different timestamps; explain why both remain in the array.

### Exercise 8 — Data Model

Refactor an order model holding 100,000 events into `orders` + `order_events`. Define indexes for list/history queries.

### Exercise 9 — Pagination

Fetch the 50 latest events, then fetch the next keyset page using `at + _id`.

### Exercise 10 — GridFS

Create a synthetic 20 MiB file in the lab and upload it via GridFS. Explain why a single BSON document cannot be used.

### Exercise 11 — 1,000 Stages

Generate a pipeline with many `$addFields` stages in a test program, count the stages, and propose how to consolidate them instead of exceeding the limit.

### Exercise 12 — Sort Memory

Compare aggregation `$sort` on an unindexed field vs. an indexed field using `explain`.

### Exercise 13 — Sort + Limit

Fetch a tenant's top 50 events. Analyze why `$sort → $limit` differs from `$limit → $sort`.

### Exercise 14 — Group Accumulator

Create a group with many events. Compare `$push:"$$ROOT"` against `$sum:1` in state/output size.

### Exercise 15 — Facet

Build a facet with unbounded arrays, then refactor it into a 20-item page + scalar count. Explain the 100 MB and 16 MiB limits.

### Exercise 16 — Lookup Fan-Out

An order has many foreign events. Write a `$lookup` pipeline fetching at most 10 events, projecting minimal fields, and create an index.

### Exercise 17 — Unwind

A document has 100 elements. How many rows does `$unwind` emit? Add `$match` before and after to retain only the desired SKU.

### Exercise 18 — Cursors in Java

Iterate 100,000 documents using `forEach`/cursor streaming without calling `into(new ArrayList<>())`.

### Exercise 19 — BSON 16 MiB vs. Response Limit

Design two failure modes: one MongoDB aggregation producing an oversized result doc; one API returning many small docs rejected by the gateway. State their distinct fixes.

### Exercise 20 — Retention

Design storage for recent notifications (latest 100) and full notification logs (30 days), using bounded arrays and an events collection with TTL per domain rules.

### Exercise 21 — Migration Idempotency

Backfill embedded events into a collection using stable event IDs and `$setOnInsert`, ensuring re-runs create no duplicates.

### Exercise 22 — Migration Race

During backfill, an old writer appends a new event. Propose drain + catch-up + final reconciliation before `$unset` on the legacy field.

### Exercise 23 — Data Quality

An embedded event lacks an ID, stores timestamp as a string, or has a mistyped payload. Route it to an error/review queue instead of assigning arbitrary IDs.

### Exercise 24 — Monitoring

Design a dashboard for p95/p99/max BSON bytes, array length, memory errors, spills, p99 write latency, and migration backlog.

### Exercise 25 — Security

An API accepts user input as an events array. Design max elements, max bytes, allowed fields, tenant filtering, and redacted logging.

### Exercise 26 — Transactions/Outbox

After extracting events from the parent, design a transactional outbox or idempotent eventual consistency so events are never lost on crash.

### Exercise 27 — Materialized View

Replace `$group + $push all invoices` with a per-customer summary holding count and total.

### Exercise 28 — Sharded Cluster

Explain why adding shards does not make a 20 MiB order document valid; design a shard key for the `events` collection.

### Exercise 29 — Incident Drill

Simulate MongoDB returning document-too-large on event write. Write a runbook covering evidence collection, stabilization, classification, recovery, and preventing recurrence.

### Exercise 30 — Pipeline Triage

A pipeline containing `$lookup`, `$unwind`, `$group`, and `$facet` fails. Measure cardinality/bytes after each stage and propose a bounded pipeline.

---

## 45. Review Questions

1. What is the maximum BSON document size in MiB and in bytes?
2. Why shouldn't JSON string length be used as BSON size?
3. How does the per-document limit differ from a collection limit?
4. Does MongoDB enforce a nesting depth limit?
5. Why is there no single fixed maximum element count for all arrays?
6. What unit does `$bsonSize` return?
7. How does `$bsonSize:"$$ROOT"` differ from `$size:"$events"`?
8. Why is `$isArray` needed before `$size` on dirty data?
9. Why does `avgObjSize` not prove there are no outliers?
10. Which errors typically indicate `BSONObjectTooLarge`?
11. How can insert/update and aggregate both throw size errors from different root causes?
12. Does `$push` create a new field when missing?
13. If a field is a string, does `$push` automatically convert it to an array?
14. What does `$addToSet` deduplicate by?
15. Why doesn't `$addToSet` stop an audit array from growing?
16. How does `$slice:100` differ from `$slice:-100`?
17. What is the role of `$sort` inside `$push`?
18. Why does bounding element count not guarantee staying under 16 MiB?
19. When should you embed?
20. When should child documents be extracted to a separate collection?
21. How does a bounded bucket differ from an unbounded parent array?
22. What kind of problem is GridFS built to solve?
23. Does GridFS make an arbitrary 100 MiB BSON document valid?
24. Does sharding raise the document size limit?
25. Why can a hot document cause contention?
26. How does the 16 MiB aggregation result limit differ from the 100 MB stage memory limit?
27. What is the maximum stage count for an aggregation pipeline?
28. Why should a builder generating 1,001 stages be refactored?
29. What role does `allowDiskUseByDefault` play starting in MongoDB 6.0?
30. Which stages benefit from `allowDiskUse:true`?
31. Why doesn't `allowDiskUse` fix `$facet`?
32. What are the two limits governing `$facet`?
33. Why can `$group` spill yet a `$push` accumulator still fail?
34. When should `$sum` be used instead of `$push:"$$ROOT"`?
35. What kind of field does `$lookup` produce semantically?
36. Why does lookup fan-out risk creating oversized outputs?
37. Why does a foreign index matter for `$lookup`?
38. How does `$unwind` affect pipeline document count?
39. Why does matching early usually reduce resource consumption?
40. Why can placing `$limit` before `$sort` yield wrong results?
41. Is a multi-document cursor bounded to 16 MiB total?
42. What advantage does keyset pagination have over large `skip`?
43. Why can't `$merge` save an output document larger than 16 MiB?
44. What error can Java `into(new ArrayList<>())` trigger?
45. Does `maxTimeMS` raise memory limits?
46. Why is enabling the profiler without controls risky?
47. How should an unknown write outcome be retried?
48. Why do `$push` retries easily produce duplicates?
49. Why do event migrations require stable event IDs?
50. Why shouldn't legacy arrays be deleted immediately after initial backfill?
51. Why should migration markers live outside a document near 16 MiB?
52. How do you handle new events written by old writers during migration?
53. Which metrics predict a document-size incident?
54. When should materialized counters replace aggregating raw history?
55. Distinguish MongoDB BSON errors, client heap OOM, and HTTP gateway 413.
56. What should be tested on staging to verify a pipeline fix?
57. Why can excessive indexes slow down writes?
58. How can a retention plan curb document growth?
59. Which kinds of data must never be arbitrarily truncated?
60. When is an incident considered fully resolved?

---

## 46. Summary

The three limit categories in this lesson have distinct causes and fixes:

1. **Document too large (16 MiB):** inspect `$bsonSize`, identify growing fields/arrays, cap payloads, use bounded arrays strictly for recent items, or refactor to referenced collections/buckets/GridFS as appropriate for the data.
2. **Unbounded arrays:** solve at the **data modeling and data lifecycle** level, not simply by swapping `$push` for `$addToSet`. Establish event IDs, uniqueness, pagination, retention, and idempotent migrations.
3. **Aggregation pipeline limits:** distinguish the 1,000-stage cap, memory/spill, non-spilling `$facet`, `$group` accumulator growth, and the 16 MiB BSON result limit. Reduce cardinality, leverage indexes, apply filters/projections/limits properly, and avoid packing all raw documents into one output array.

A responsible recovery strategy must:

- Halt retry/write paths that amplify the incident.
- Measure **actual sizes and cardinality**.
- Never delete audit/ledger data to dodge errors without backing up and reconciling.
- Move long-lived unbounded data to scalable models.
- Use `allowDiskUse` only where it matches the **actual limit encountered**.
- Test migration/cutover/rollback in staging.
- Monitor p95/p99/max sizes, spills, latencies, backlogs, and application correctness post-fix.

**Operational takeaway:** MongoDB supports massive collections and workloads, yet **no single document should be designed to grow without bound**, and **no aggregation result should pack an entire history into one BSON object**.

## Official MongoDB Documentation

- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Documents — Document Size Limit](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB `$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/)
- [MongoDB `$binarySize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/binarysize/)
- [MongoDB `$push` Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/push/)
- [MongoDB `$addToSet` Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Array Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update-array/)
- [MongoDB `$group` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB `$facet` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB `$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB `$unwind` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB `$sort` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB `$limit` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/limit/)
- [MongoDB Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB `$merge` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
- [MongoDB Java Sync Driver — GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
