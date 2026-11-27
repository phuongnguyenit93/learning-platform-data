# Subset, Bucket, and Computed Patterns

> **Chapter:** Document Design  
> **Module:** `SPRING_DATA_MONGODB`

In MongoDB, document design should start from **what the application reads, write frequency, how many elements can accumulate, and what consistency level must be guaranteed**. Three common patterns solve distinct problems:

- **Subset pattern:** keep a frequently viewed slice inside the main document while storing the full dataset in a separate collection.
- **Bucket pattern:** group many small records sharing a key or time window into a size-bounded document.
- **Computed pattern:** store pre-aggregated or pre-calculated results to avoid scanning raw source data on every read.

These are **data modeling patterns**, not three toggles in MongoDB configuration. They can be combined, and each carries maintenance costs. Within the `SPRING_DATA_MONGODB` module, choosing a pattern directly shapes Java mapping, `MongoTemplate` or repository queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the purpose, structure, and trade-offs of the subset, bucket, and computed patterns.
2. Design collections and documents around common queries while identifying the authoritative *source of truth*.
3. Read and write `mongosh` examples with explicit data bounds and update paths.
4. Use Spring Data MongoDB `@Document` mappings, repositories, and `MongoTemplate` to work with these models.
5. Evaluate consistency, scalability, indexes, and practical effectiveness before adopting a pattern in production.

## 2. Choosing a Pattern from the Problem

| Real-world scenario | Suitable pattern | Primary benefit | Cost to manage |
| --- | --- | --- | --- |
| Product listing cards only need a few recent reviews, while each product has thousands | **Subset** | Render product card from one small document | Duplicated slice must be refreshed |
| Devices emit frequent small measurements; app queries by time windows | **Bucket** | Reduces document count and groups data by interval | Size bounds, write contention, queries crossing bucket boundaries |
| Daily revenue dashboard is called far more often than orders change | **Computed** | Returns precomputed totals instead of re-aggregating everything | Result lag or needing exact incremental updates |

A helpful question before creating collections: **on each read, how much data does the app need, and does it have to recompute it from scratch?** If the main cost is loading excess data, consider subset; if tiny documents multiply rapidly, consider bucket; if aggregations repeat constantly, consider computed.

Do not apply these patterns just to "reduce the number of collections". Document size, update frequency, query fan-out, and accuracy requirements can make an overly clever pattern perform worse than simple storage.

## 3. Subset Pattern: Keep Frequently Used Data Near the Main Document

### 3.1. The Problem

An e-commerce app shows product listing cards with name, price, and the **three latest reviews**. Only when opening the full reviews view do users paginate through thousands of reviews.

Embedding *all* reviews inside the product document causes unbounded growth and risks transferring massive payloads on every card read. Keeping reviews solely in a separate collection can force extra queries just to render a few reviews per card. The subset pattern combines both needs: **embed the small frequently viewed slice** and **store full records separately**.

### 3.2. Proposed Model

```text
products
└── P-100
    ├── name, priceMinor, currency
    ├── reviewCount
    └── recentReviews: [3 newest summaries]

reviews
├── R-901: productId=P-100, stars, body, createdAt
├── R-902: productId=P-100, stars, body, createdAt
└── ...    (complete, paginated)
```

Product document:

```javascript
db.products.insertOne({
  _id: "P-100",
  name: "Mechanical Keyboard",
  priceMinor: NumberLong(1290000),
  currency: "VND",
  reviewCount: 2,
  recentReviews: [
    {
      reviewId: "R-902",
      stars: 5,
      summary: "Smooth typing, solid build",
      createdAt: ISODate("2026-11-19T09:00:00Z")
    },
    {
      reviewId: "R-901",
      stars: 4,
      summary: "Matches description",
      createdAt: ISODate("2026-11-18T09:00:00Z")
    }
  ]
})
```

Full review documents stored in a separate collection:

```javascript
db.reviews.insertMany([
  {
    _id: "R-901",
    productId: "P-100",
    stars: 4,
    body: "Matches description, well packaged, used for a week.",
    createdAt: ISODate("2026-11-18T09:00:00Z")
  },
  {
    _id: "R-902",
    productId: "P-100",
    stars: 5,
    body: "Smooth typing, solid build.",
    createdAt: ISODate("2026-11-19T09:00:00Z")
  }
])
```

To fetch the product card, project only the fields needed for display:

```javascript
db.products.find(
  { _id: "P-100" },
  { name: 1, priceMinor: 1, currency: 1, reviewCount: 1, recentReviews: 1 }
)
```

To load the reviews page:

```javascript
db.reviews
  .find({ productId: "P-100" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)

db.reviews.createIndex({ productId: 1, createdAt: -1, _id: -1 })
```

The index on `reviews` aligns with filtering by product and sorting newest first. For deep pagination on large datasets, consider keyset pagination (using `createdAt` and `_id`) instead of large `skip` values.

### 3.3. Updating the Subset

Once a new review is saved in `reviews`, the app updates the summary on `products`:

```javascript
db.reviews.insertOne({
  _id: "R-903",
  productId: "P-100",
  stars: 5,
  body: "Keys feel steady after two days of use.",
  createdAt: ISODate("2026-11-20T07:00:00Z")
})

db.products.updateOne(
  { _id: "P-100" },
  {
    $push: {
      recentReviews: {
        $each: [{
          reviewId: "R-903",
          stars: 5,
          summary: "Keys feel steady",
          createdAt: ISODate("2026-11-20T07:00:00Z")
        }],
        $sort: { createdAt: -1, reviewId: 1 },
        $slice: 3
      }
    },
    $inc: { reviewCount: 1 }
  }
)
```

`$push` with `$each`, `$sort`, and `$slice` keeps **at most three** reviews on the product document; `$inc` increments the counter. Updating fields on the **single** product document is atomic. However, inserting into `reviews` and updating `products` are **two writes to two separate documents**; they do not automatically form an atomic transaction.

In production, pick an update policy:

- **Tolerate lag:** `reviews` is the authoritative source, and a worker/event updates `recentReviews`; guard against duplicate event processing using an event ID or `reviewId`.
- **Need immediate visibility together:** consider multi-document transactions on a supported MongoDB deployment, while still handling retries and ensuring counters never double-increment.
- **Edit/delete reviews:** update the counter and potentially **recompute the top 3** from `reviews`, because the next qualifying item might sit outside the current subset.

A subset is never the canonical list for browsing **all** reviews. If strict synchronization is mandatory under high write load, evaluate whether storing only `reviews` and issuing an extra query is simpler and more reliable.

### 3.4. When to Use and When to Avoid

Consider the subset pattern when child data can grow very large while the most-read portion is small and relatively stable (such as a few recent addresses, latest notifications, or image thumbnails). Avoid embedding subsets when child records churn so rapidly that syncing copies costs more than querying directly, or when business rules forbid stale results even briefly.

## 4. Bucket Pattern: Group Small Records into Bounded Documents

### 4.1. The Problem

A sensor emits temperature readings every few seconds. Storing each reading in its own document creates vast numbers of tiny documents that the app usually reads by time range. The bucket pattern groups readings sharing a device and time window into one document.

**Bucket boundaries must be finite.** Array element counts, document byte size, and concurrent writers hitting one document are the main constraints. MongoDB enforces a **16 MiB limit per standard BSON document**; in practice, design buckets well below that ceiling.

### 4.2. Minute-Bucket Example

```javascript
db.readingBuckets.insertOne({
  _id: "S-01|2026-11-20T09:00:00Z|0",
  deviceId: "S-01",
  bucketStart: ISODate("2026-11-20T09:00:00Z"),
  bucketEnd: ISODate("2026-11-20T09:01:00Z"),
  segmentNo: 0,
  sampleCount: 3,
  sumValue: 75.2,
  minValue: 24.8,
  maxValue: 25.3,
  samples: [
    { at: ISODate("2026-11-20T09:00:05Z"), value: 24.8 },
    { at: ISODate("2026-11-20T09:00:15Z"), value: 25.1 },
    { at: ISODate("2026-11-20T09:00:25Z"), value: 25.3 }
  ]
})
```

- `deviceId` is the grouping key. `bucketStart` and `bucketEnd` define the UTC interval **[start, end)**.
- `segmentNo` splits one time window across multiple documents if too many samples arrive; `_id` concatenates those parts to form a deterministic identifier.
- `samples` holds the raw readings for the bucket; `sampleCount`, `sumValue`, `minValue`, and `maxValue` are pre-maintained statistics for the bucket.
- With this layout, the bucket's mean temperature is `sumValue / sampleCount`; averaging precomputed bucket averages equally would be inaccurate when buckets hold different sample counts.

Create an index matching the query pattern:

```javascript
db.readingBuckets.createIndex({
  deviceId: 1,
  bucketStart: 1,
  segmentNo: 1
})

db.readingBuckets
  .find({
    deviceId: "S-01",
    bucketStart: {
      $gte: ISODate("2026-11-20T09:00:00Z"),
      $lt: ISODate("2026-11-20T10:00:00Z")
    }
  })
  .sort({ bucketStart: 1, segmentNo: 1 })
```

This query fetches buckets **starting** inside the given range. If a filter asks for readings in an arbitrary interval *not aligned with bucket boundaries*, fetch every bucket overlapping that interval and filter individual `samples.at` values; otherwise readings from a bucket starting earlier will be missed.

### 4.3. Appending Readings and Enforcing Capacity

Suppose the system caps each segment at **100 readings**. When the bucket already exists:

```javascript
db.readingBuckets.updateOne(
  {
    _id: "S-01|2026-11-20T09:00:00Z|0",
    sampleCount: { $lt: 100 }
  },
  {
    $push: {
      samples: {
        at: ISODate("2026-11-20T09:00:35Z"),
        value: 25.0
      }
    },
    $inc: { sampleCount: 1, sumValue: 25.0 },
    $min: { minValue: 25.0 },
    $max: { maxValue: 25.0 }
  }
)
```

The `sampleCount < 100` filter and all field updates run atomically on **one** document. If `matchedCount = 0`, the app must distinguish between a missing bucket and a full bucket. When full, allocate the next segment according to an explicit rollover rule and handle concurrent segment creation races; when missing, initialize the bucket cleanly.

This snippet **does not automatically create a new segment**, nor does it guarantee exactly-once writes if a client retries. In production you need:

1. A reading identifier or deduplication strategy to prevent double-appends on retries or redeliveries.
2. Both an element cap **and a byte-size cap** per bucket (element count alone is insufficient when sample payloads vary in size).
3. Concurrency-safe segment creation/selection handling unique-key conflicts.
4. Contention monitoring if many producers write to one "hot" bucket; use independent segments or partitioned keys if needed.

Do not assume packing more events into one document automatically increases write throughput. Oversized or hot buckets can become bottlenecks.

### 4.4. Aggregating Directly Across Buckets

Because each bucket tracks `sumValue` and `sampleCount`, you can compute a device's mean temperature over full bucket intervals:

```javascript
db.readingBuckets.aggregate([
  {
    $match: {
      deviceId: "S-01",
      bucketStart: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$deviceId",
      sum: { $sum: "$sumValue" },
      count: { $sum: "$sampleCount" },
      min: { $min: "$minValue" },
      max: { $max: "$maxValue" }
    }
  },
  {
    $project: {
      _id: 0,
      deviceId: "$_id",
      count: 1,
      min: 1,
      max: 1,
      average: {
        $cond: [
          { $gt: ["$count", 0] },
          { $divide: ["$sum", "$count"] },
          null
        ]
      }
    }
  }
])
```

This result is only accurate when `sumValue`, `sampleCount`, `minValue`, and `maxValue` are maintained properly and **each reading belongs to exactly one bucket**. For queries slicing across partial buckets, recompute from matching `samples` within the range or use finer-grained rollups.

### 4.5. Manual Buckets vs. Time-Series Collections

MongoDB provides **time-series collections** optimized for timestamped measurements, where the server manages internal bucket storage automatically. Before building array buckets by hand, evaluate time-series collections if your data consists primarily of time-ordered measurements. Manual buckets are helpful when business rules require explicit control over grouping layout, items per history page, group-level aggregates, or custom segmentation.

The two approaches differ conceptually: time-series collections are still queried by the application as individual measurements, whereas `readingBuckets` in the example is an **application-defined** schema.

## 5. Computed Pattern: Store Precomputed Results for Fast Reads

### 5.1. The Problem

A dashboard displays **daily revenue per store**. Running an aggregation over millions of orders every time someone opens the page repeats vastly more compute than orders change.

The computed pattern stores calculated outputs in a separate document or precomputed fields. The source remains the `orders` collection; `dailyRevenue` acts as a **rebuildable summary table**.

```text
orders (authoritative source)
    │
    └── filter paid orders + group by store/day/currency
           │
           ▼
dailyRevenue (precomputed results)
    └── { storeId, day, currency, orderCount, amountMinor }
           │
           ▼
    Dashboard reads a handful of summary documents
```

### 5.2. Define the Calculation Before Storing It

Suppose business rules count an order when `status = "PAID"`; `totalMinor` is in the **smallest currency unit** (VND can use whole dong), and `paidAt` is the payment timestamp.

```javascript
db.orders.insertMany([
  {
    _id: "O-001",
    storeId: "STORE-01",
    status: "PAID",
    paidAt: ISODate("2026-11-19T02:00:00Z"),
    currency: "VND",
    totalMinor: NumberLong(150000)
  },
  {
    _id: "O-002",
    storeId: "STORE-01",
    status: "PAID",
    paidAt: ISODate("2026-11-19T05:00:00Z"),
    currency: "VND",
    totalMinor: NumberLong(250000)
  }
])
```

In this example, local-day revenue for November 19 is **400,000 VND across 2 orders**. Clarify explicitly whether refunds, canceled orders, taxes, shipping fees, and status reversals add to or subtract from the metric. A field name like `revenue` alone is not enough to guarantee business accuracy.

### 5.3. Building and Updating the Summary Collection via Aggregation

This example requires MongoDB support for `$dateTrunc` (MongoDB 5.0 or later). Before using `$merge` with custom `on` keys, the target collection must have a compatible unique index on those fields.

```javascript
db.dailyRevenue.createIndex(
  { storeId: 1, day: 1, currency: 1 },
  { unique: true }
)

db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: {
        storeId: "$storeId",
        day: {
          $dateTrunc: {
            date: "$paidAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        currency: "$currency"
      },
      orderCount: { $sum: 1 },
      amountMinor: { $sum: "$totalMinor" }
    }
  },
  {
    $project: {
      _id: 0,
      storeId: "$_id.storeId",
      day: "$_id.day",
      currency: "$_id.currency",
      orderCount: 1,
      amountMinor: 1
    }
  },
  {
    $merge: {
      into: "dailyRevenue",
      on: ["storeId", "day", "currency"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
```

`$dateTrunc` groups by day in the `Asia/Ho_Chi_Minh` timezone; the resulting BSON Date still stores the UTC instant corresponding to local midnight. Grouping by `currency` avoids **summing incompatible currencies together**. `$merge` writes results to the target collection; re-running on the same input and keys replaces each group instead of double-counting.

Reading the result:

```javascript
db.dailyRevenue.find({
  storeId: "STORE-01",
  currency: "VND",
  day: {
    $gte: ISODate("2026-11-18T17:00:00Z"),
    $lt: ISODate("2026-11-19T17:00:00Z")
  }
})
```

**Correctness caveat on refresh:** `$merge` only touches groups present in the aggregation output. If a previous day had `PAID` orders and later **none remain eligible**, the stale summary group can stay behind in `dailyRevenue`. When implementing rebuilds, handle **deleting vanished groups** or rebuild into a staging set and swap; never treat `$merge` as a deletion sync command.

### 5.4. Scheduled Recomputation vs. Update on Write?

| Maintenance approach | Suitable when | Issues to solve |
| --- | --- | --- |
| Periodic batch recomputation from `orders` | Dashboard tolerates minutes/hours of lag | Scheduling, scan cost, pruning vanished groups, safe re-runs |
| Incremental when order becomes `PAID` | Near-immediate updates desired | Exactly-once add/subtract, status reversals, duplicate events, partial write failures |
| Multi-document transaction | Strict consistency between source and summary required | Transaction topology support, conflict retries, transaction overhead |
| Direct aggregation on every read | Small data or live source calculation required | Query latency and aggregation CPU/I/O cost |

For example, when handling **a payment event verified to be new**, the system can update the summary document with `$inc` and `upsert`:

```javascript
db.dailyRevenue.updateOne(
  {
    storeId: "STORE-01",
    day: ISODate("2026-11-18T17:00:00Z"),
    currency: "VND"
  },
  {
    $inc: {
      orderCount: 1,
      amountMinor: NumberLong(150000)
    }
  },
  { upsert: true }
)
```

This command is **not automatically idempotent against duplicate events**: reprocessing the same order increments twice. Maintain applied-event tracking for idempotency (such as a ledger unique key updated within an appropriate transaction, or periodic source recomputation). Refunds and status changes also require explicit reversing adjustments.

If precomputed fields sit directly on the primary document—such as `ratingCount` and `ratingSum` on a product—they can update atomically with `$inc` on that document, computing `ratingAverage = ratingSum / ratingCount` on read. That is also the computed pattern. Still, if full reviews live in another collection, cross-document synchronization remains a design question.

## 6. Applying the Patterns in Spring Data MongoDB

Spring Data MongoDB does not prescribe subset, bucket, or computed patterns. You map your **designed schema** to Java, then pick repositories or `MongoTemplate` to match your read/write paths.

### 6.1. Mapping a Bucket

Example using Java records; place the code in `ReadingBucket.java`:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "readingBuckets")
public record ReadingBucket(
    @Id String id,
    String deviceId,
    Instant bucketStart,
    Instant bucketEnd,
    int segmentNo,
    int sampleCount,
    double sumValue,
    double minValue,
    double maxValue,
    List<Sample> samples
) {
    public record Sample(Instant at, double value) {}
}
```

Java property names map directly to the corresponding BSON fields in the earlier example. Because `_id` is an application-composed string, `String id` matches the chosen storage type.

Reading buckets with `MongoTemplate` in a service:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ReadingBucketQueryService {
    private final MongoTemplate mongoTemplate;

    public ReadingBucketQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<ReadingBucket> findBuckets(
            String deviceId, Instant from, Instant to) {
        Query query = Query.query(
                Criteria.where("deviceId").is(deviceId)
                    .and("bucketStart").gte(from).lt(to))
            .with(Sort.by(
                Sort.Direction.ASC, "bucketStart", "segmentNo"));

        return mongoTemplate.find(query, ReadingBucket.class);
    }
}
```

This method works when `from` and `to` align with bucket boundaries. If querying readings across arbitrary timestamps, the service must fetch **overlapping** buckets and filter by `Sample.at` before returning results.

**Precision note:** `double` works for many physical measurements with acceptable tolerance, but never for money. For monetary totals, use integer minor units or `Decimal128` with explicit rules.

### 6.2. Mapping Precomputed Results via Repository

File `DailyRevenue.java`:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "dailyRevenue")
public record DailyRevenue(
    @Id String id,
    String storeId,
    Instant day,
    String currency,
    long orderCount,
    long amountMinor
) {}
```

File `DailyRevenueRepository.java`:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface DailyRevenueRepository
        extends MongoRepository<DailyRevenue, String> {

    List<DailyRevenue>
    findByStoreIdAndCurrencyAndDayGreaterThanEqualAndDayLessThan(
        String storeId,
        String currency,
        Instant fromInclusive,
        Instant toExclusive
    );
}
```

Spring Data derives filter criteria from the Java property names of `DailyRevenue`. If stored BSON field names differ from Java names, add `@Field` accordingly and verify indexes against the **stored field names**. In this setup, the repository serves *reads*, while the aggregation rebuild must still be implemented explicitly via scheduled jobs, aggregations, or event handlers.

For complex computations, `MongoTemplate` provides the Aggregation API; in Java code, prefer `Aggregation` and `AggregationOperation` over fragile JSON-string pipelines. `ReactiveMongoTemplate` and reactive repositories change the asynchronous execution model, but **do not automatically solve consistency for precomputed data**.

### 6.3. Update from Source or from Copy?

Establish data ownership rules directly in your services:

- `reviews` holds complete review text; `products.recentReviews` is a rebuildable display summary.
- With manual buckets, `readingBuckets.samples` can serve as the authoritative measurement record **when** ingestion guarantees zero drops or duplicates; `sumValue` and `sampleCount` are derived fields.
- `orders` holds order facts; `dailyRevenue` is a rebuildable aggregate of qualifying orders.

Maintaining derived data requires plans for **retries, reconciliation, rebuilds, and lag monitoring**. Mapping annotations cannot replace those business rules.

## 7. Indexes, Storage Limits, and Performance

Patterns do not make an app faster by default. Evaluate them against real queries and write costs:

| Pattern | Typical index | Metrics to watch | Common risks |
| --- | --- | --- | --- |
| Subset | `reviews(productId, createdAt, _id)` | Docs read per card; `products` document size; query counts | Stale subset, duplicated data, oversized docs from over-embedding |
| Bucket | `readingBuckets(deviceId, bucketStart, segmentNo)` | Bucket size and sample count; write latency; contention; buckets per window | Hot bucket, unbounded arrays, duplicate samples, boundary bugs |
| Computed | Unique `dailyRevenue(storeId, day, currency)` | Dashboard read latency; job runtime; source lag; total drift | Stale totals, double-counting, lingering vanished groups |

Example running `explain("executionStats")` to inspect a query plan:

```javascript
db.reviews
  .find({ productId: "P-100" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Inspect `totalDocsExamined`, `totalKeysExamined`, execution duration, document sizes, and system metrics on representative data. For bucket documents, measure **write** cost just as closely as read speed.

Key principles:

1. Indexes locate documents, but do not fix loading unnecessary fields or oversized arrays. Use projections where appropriate.
2. Choose indexes from actual filter and sort conditions. Every extra index consumes memory, disk space, and write maintenance work.
3. Both source data and precomputed data need explicit retention and refresh lifecycles; TTL or deletion policies must align with reporting and audit needs.
4. Document boundaries dictate atomicity. A single-document update is atomic; multi-document operations need application protocols or transactions when required.

## 8. Testing and Reconciliation

Testing only "the insert succeeded" never proves a pattern behaves correctly.

**Subset**

- Insert more than three reviews and verify `recentReviews` always keeps at most three entries in the right order.
- Create reviews with identical timestamps and verify deterministic tie-breaking.
- Simulate duplicate updates from retries, review edits/deletions, and consumer disconnects; reconcile `reviewCount` and latest reviews against `reviews`.

**Bucket**

- Write up to the exact 100-item limit, then write item 101; verify segment rollover creates a new segment without losing records.
- Test concurrent producers, retried writes of the same sample, late-arriving samples, and out-of-order arrivals.
- Test queries whose start/end timestamps fall mid-bucket, empty-bucket intervals, and sudden payload-size spikes.

**Computed**

- Compare totals from `dailyRevenue` against a direct aggregation over `orders` with identical filters, timezone, and currency.
- Simulate an order transitioning out of `PAID`, refunds, and groups dropping to zero orders; verify decrements and pruning.
- Run rebuild jobs repeatedly to verify idempotency; simulate failed jobs, concurrent updates, and duplicate events.

In Spring Data, write integration tests against a real MongoDB instance in an isolated environment (such as Testcontainers when project infrastructure allows) to validate BSON types, mappings, update operators, indexes, and transactions under realistic settings. Unit tests mocking repositories cannot catch malformed aggregations or BSON type mismatches.

## 9. Three Common Design Pitfalls

### "A subset is just a cache, so update it casually"

A subset is a copy with an **explicit contract**: how many items, which sort key, when it refreshes, and how much lag is acceptable. Without an authoritative source and rebuild job, duplicated fields lead to contradictory data.

### "Bigger buckets are always better"

Larger buckets reduce document count, but increase read/update overhead, bloat arrays, and amplify producer contention. Optimal bucket size depends on data distribution, query windows, byte limits, and concurrent write load; there is no single universal item count.

### "Precomputed numbers are always as accurate as the source"

Precomputed metrics can lag, double-count, or retain deleted/changed groups. High accuracy requires explicit state rules, idempotent updates, transactions when warranted, and source-based reconciliation/rebuilds.

## 10. Practice Exercise

A logistics service manages 50,000 parcels; each parcel accumulates thousands of location and status events. The list screen displays **latest status**, the detail screen opens the **50 most recent events**, and a dashboard shows **successful deliveries per day and region**.

Determine:

1. Which source data must be stored in full and paginated?
2. Should `latestStatus` and the 50 latest events live on the parcel document? What bounds and update mechanisms apply?
3. When location pings arrive continuously, should you use manual buckets, a time-series collection, or one document per event?
4. Should daily successful deliveries be computed via direct aggregation or a maintained summary collection? How should order status corrections be handled?

**Reference approach:** keep the full event history as the authoritative source; store `latestStatus` and a bounded subset on the parcel when list/detail screens are read-heavy. Choose event stream storage based on ingestion rate, query/TTL needs, and write load; pure timestamped location streams may fit a time-series collection. The dashboard can use the computed pattern under heavy read traffic, with an unambiguous definition of "successful delivery" and a correction flow when statuses change. Validate every choice with real queries, update rates, and benchmarks.

## Key Takeaway

**Subset** optimizes payload size on hot read paths; **bucket** organizes vast numbers of tiny events into bounded groups; **computed** shifts repeated aggregation cost into updates or scheduled jobs. Across all three patterns, keep the authoritative source, document boundaries, update paths, recovery procedures, and required consistency level crystal clear. Spring Data MongoDB gives you mapping, queries, aggregations, and transactions to implement the choice, while data design and operational rigor determine the final result.
