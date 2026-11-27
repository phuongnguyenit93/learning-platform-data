# Subset, Computed, Bucket, and Attribute Patterns in the MongoDB Document Model

## 1. Why Do We Need Document Design Patterns?

MongoDB stores data as **BSON documents**, allowing fields that are commonly read or updated together to reside in one business unit. However, a document model that works well at a few thousand records can become slow and hard to maintain as data grows: documents keep expanding, queries pull back unneeded data, reports repeatedly recompute the same totals, or every product carries a different set of attributes.

Four common *schema design patterns* used to address those challenges are:

| Pattern | Primary Problem Addressed | Core Idea |
| --- | --- | --- |
| **Subset** | Common queries only need a small slice of a large entity. | Keep the hot portion inside the main document; store the rest separately. |
| **Computed** | An aggregated or calculated value is queried repeatedly at high cost. | Precompute and store the result, updating it under a defined consistency policy. |
| **Bucket** | Very many small records naturally group by time, device, or entity. | Group related events into documents with clear bounds. |
| **Attribute** | Entities of the same kind have custom attributes, making per-field indexing impractical. | Represent dynamic attributes as uniformly structured elements for querying and indexing. |

These are **data design patterns**, not collection types or mandatory MongoDB switches. A system may combine multiple patterns, or need none at all if a simple document already satisfies query and consistency requirements.

The starting point is always the **access pattern**: which fields the application reads/writes, over what span, at what frequency, and with what latency. Picking patterns by name without describing the workload easily leads to duplicated data, heavier write amplification, and hard-to-optimize queries.

### Running Example

Consider an e-commerce platform with these requirements:

- The listing page needs product name, price, thumbnail, and rating score.
- The detail page needs a few most recent reviews; older reviews appear only when the user clicks "View more."
- Filters use different specifications for laptops, shirts, books, and phones.
- The dashboard needs daily order count and revenue, though not necessarily accurate to the millisecond.
- The system ingests high volumes of view events or telemetry measurements daily.

These requirements correspond to four distinct needs. We will use them to distinguish Subset, Computed, Bucket, and Attribute.

## 2. Before Applying Patterns: Document Boundaries and Sources of Truth

MongoDB guarantees atomicity for writes on **a single document**. When splitting an entity across multiple documents or copying data for reads, the application must decide how to keep those copies consistent.

For example, saving a new review in `reviews` while updating the average score on `products` involves two operations on two different documents. Never assume both always succeed together; choose transactions, asynchronous updates, retry logic, or reconciliation depending on requirements.

Key terms to align on:

- **Source of truth:** the place holding the authoritative value from which other views can be rebuilt—for instance, approved reviews are the source for computing rating statistics.
- **Derived data:** data computed from a source, such as `reviewCount`, `averageRating`, or a list of the three newest reviews.
- **Bounded data:** a dataset capped in element count/size, such as the first five displayed comments.
- **Write amplification:** one business action triggering multiple writes to maintain read-optimized views.

Every pattern below trades off read cost, write cost, storage, and complexity. The comparison table at the end shows when those trade-offs pay off.

---

## 3. Subset Pattern: Keep Frequently Read Data Close

### 3.1. Problem

A product has thousands of reviews. The product listing page only needs name, price, thumbnail, star rating, and basic fields. The detail page wants to show the three latest reviews; remaining reviews load only when the user opens "View more."

If all reviews are embedded in `products.reviews`, the product document grows with every comment. Each listing fetch may process large documents, while every new review contends on the same document.

MongoDB caps **a single BSON document at 16 MiB**. Even well below that limit, a large array strains cache memory, read/write I/O, and write contention.

The **Subset pattern** solves this by storing inside the main document **the small slice useful for the common access path**, while keeping the full dataset in another collection.

### 3.2. Example Model

~~~javascript
// products: core data for list and detail views
{
  _id: "P100",
  name: "Laptop 14 inch",
  priceMinor: 19500000,
  thumbnailUrl: "/images/p100-small.webp",
  latestReviewPreview: [
    { reviewId: "R920", rating: 5, text: "Great battery" },
    { reviewId: "R918", rating: 4, text: "Lightweight" },
    { reviewId: "R915", rating: 5, text: "Nice screen" }
  ],
  reviewPreviewUpdatedAt: ISODate("2026-11-14T02:00:00Z")
}

// reviews: full dataset, growing independently
{
  _id: "R920",
  productId: "P100",
  authorId: "U21",
  rating: 5,
  text: "Great battery",
  createdAt: ISODate("2026-11-14T01:58:00Z"),
  moderationStatus: "PUBLISHED"
}
~~~

Here:

1. Listing pages read `products` without scanning all reviews.
2. Detail pages get the three latest reviews directly from `latestReviewPreview`.
3. Paginating all reviews queries the separate `reviews` collection.
4. Only selected review fields are copied into the preview; full details live in `reviews`.

Querying all published reviews:

~~~javascript
db.reviews.createIndex({
  productId: 1,
  moderationStatus: 1,
  createdAt: -1,
  _id: -1
});

db.reviews.find({
  productId: "P100",
  moderationStatus: "PUBLISHED"
}).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Adding `_id` to the sort provides a deterministic tie-breaker when multiple reviews share the same `createdAt`. In production, pagination should use a continuation key (*cursor/keyset*) to avoid deep `skip`.

### 3.3. Subset vs. Projection

~~~javascript
// Projection selects only the fields returned
db.products.find(
  { _id: "P100" },
  { name: 1, priceMinor: 1, thumbnailUrl: 1 }
);
~~~

Projection is a helpful query technique. However, projection **does not turn a document holding a giant array into a compact storage model**; in many cases the storage engine still reads pages containing the document before filtering returned fields. A *covered query* served entirely by an index is a notable exception.

The Subset pattern changes **how data is stored**: rarely used data does not live inside the main document. Thus, when a model currently has hundreds of cold fields, evaluate projection, indexes, and splitting data together; do not assume splitting collections is automatically superior.

### 3.4. How Is a Subset Updated?

Suppose a new review has just been approved for publication. The workflow could be:

~~~text
Review approved
      |
      v
Write review status to reviews (source of truth)
      |
      +--> Emit event / job to refresh preview
                    |
                    v
             Recompute 3 newest reviews
                    |
                    v
             Update products.latestReviewPreview
~~~

A straightforward implementation queries the latest published reviews and `$set`s the preview:

~~~javascript
const latest = db.reviews.find(
  { productId: "P100", moderationStatus: "PUBLISHED" },
  { _id: 1, rating: 1, text: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(3).toArray();

const preview = latest.map(r => ({
  reviewId: r._id,
  rating: r.rating,
  text: r.text
}));

db.products.updateOne(
  { _id: "P100" },
  {
    $set: {
      latestReviewPreview: preview,
      reviewPreviewUpdatedAt: new Date()
    }
  }
);
~~~

This illustrates the concept; if multiple workers update concurrently, a result computed from a stale snapshot can overwrite a newer preview. Production systems need event ordering, revision checks, or a suitable sync/rebuild mechanism. If strict immediate consistency is required, design an appropriate transactional flow instead of accepting asynchronous updates.

Deleting or hiding a review during moderation must also refresh the preview. Handling only **inserts** while forgetting **edits/deletes** produces persistent stale data.

### 3.5. When to Use and When to Avoid?

**Suitable when:**

- A small, bounded subset of data serves most requests.
- The remainder is large, grows continuously, or has an independent update lifecycle.
- Common read paths speed up meaningfully by avoiding cold data.
- The team accepts maintaining a small copy along with update/recovery mechanisms.

**Consider avoiding when:**

- Almost every request needs the entire dataset.
- Child data is small, bounded, and usually updated with the parent document.
- Keeping the subset synchronized outweighs the performance gain.
- Goals can be achieved with proper indexes, projections, and a simpler schema.

Subset is not a rule saying "split whenever a document gets big." Measure access patterns, sizes, write overhead, and staleness tolerance first.

---

## 4. Computed Pattern: Store Precalculated Results to Avoid Repeated Computation

### 4.1. Problem

A product has 200,000 reviews. Every time the product page loads, the application runs an aggregation to compute:

- Published review count.
- Total star sum.
- Average rating.
- Star rating breakdown.

If page traffic is huge while new reviews arrive infrequently, recomputing everything on every read wastes CPU and I/O.

The **Computed pattern** stores precalculated values directly in the document so common reads simply fetch the result:

~~~javascript
{
  _id: "P100",
  name: "Laptop 14 inch",
  reviewStats: {
    count: 1200,
    ratingSum: 5490,
    averageRating: 4.575
  },
  reviewStatsUpdatedAt: ISODate("2026-11-14T02:00:00Z")
}
~~~

Values in `reviewStats` are **derived data**. The `reviews` collection or a valid event log remains the source to recompute from if counters ever drift.

### 4.2. Precomputing vs. Reading Back

From `reviews`, an illustrative aggregation:

~~~javascript
db.reviews.aggregate([
  {
    $match: {
      productId: "P100",
      moderationStatus: "PUBLISHED"
    }
  },
  {
    $group: {
      _id: "$productId",
      reviewCount: { $sum: 1 },
      ratingSum: { $sum: "$rating" },
      averageRating: { $avg: "$rating" }
    }
  }
]);
~~~

Running this pipeline on a huge review set for every page load can be costly. Once stats are stored, the API reads only the needed fields:

~~~javascript
db.products.find(
  { _id: "P100" },
  { name: 1, reviewStats: 1, reviewStatsUpdatedAt: 1 }
);
~~~

Computed's value does not imply aggregation is "bad"; aggregation remains ideal for ad-hoc or flexible reporting. The core idea is **avoiding repeating the exact same computation** when read frequency far exceeds source mutation frequency.

### 4.3. Three Strategies for Maintaining Computed Data

| Strategy | Approach | Strengths | Trade-offs |
| --- | --- | --- | --- |
| **Write-time sync** | When a valid review is added/edited/deleted, update counters in the same workflow. | Fresh values appear quickly; easier to meet strict freshness needs. | More writes; requires cross-document atomicity, retries, and conflict handling. |
| **Event-driven async** | After source mutation, emit an event for a worker to update stats. | Decouples source write load from computation; flexible throughput. | Introduces lag; requires idempotency, ordering, and error tracking. |
| **Periodic batch** | Recompute stats from source hourly/daily. | Simple for dashboards not needing real-time updates. | Stale until next run; batch jobs can consume significant resources. |

Strategies can be combined: increment counters in near real-time and run periodic reconciliation jobs to fix drift from bugs or dropped events.

### 4.4. Updating with `$inc` Does Not Automatically Solve Idempotency

Example incrementing totals after a new review is **accepted exactly once**:

~~~javascript
db.products.updateOne(
  { _id: "P100" },
  {
    $inc: {
      "reviewStats.count": 1,
      "reviewStats.ratingSum": 5
    },
    $set: { reviewStatsUpdatedAt: new Date() }
  }
);
~~~

`$inc` is atomic on a single document, yet if the same event is processed twice, the counters increase twice. In systems with retries, worker restarts, or at-least-once message delivery, you must use an **idempotency key**, a deduplicated event-processing log, or a transaction/update design ensuring an event is applied at most once.

Furthermore, if a review is edited from 5 stars to 3 stars, `ratingSum` must decrease by 2 without incrementing `count`. If a review is deleted or hidden, both score and count may need decrementing. Derived calculations need explicit state transition tables, not just an insert branch.

For averages, one way to avoid cumulative rounding errors is storing **count and sum** as intermediate figures and computing the average on read or during controlled updates:

~~~javascript
const stats = db.products.findOne(
  { _id: "P100" },
  { _id: 0, reviewStats: 1 }
).reviewStats;

const averageRating = stats.count > 0
  ? stats.ratingSum / stats.count
  : null;
~~~

When handling currency or values requiring exact decimal precision, use an appropriate BSON type and rounding rules, such as `Decimal128` or integer minor units, avoiding unchecked floating-point arithmetic for revenue totals.

### 4.5. Computed Pattern for Revenue Dashboards

Another example: daily successful order count and total revenue. You should not scan the entire transaction history on every dashboard load when you primarily need daily/monthly KPIs.

~~~javascript
// dailySales: one document per day and seller
{
  _id: { sellerId: "S42", date: "2026-11-14" },
  paidOrderCount: 183,
  revenueMinor: NumberLong("72650000"),
  computedAt: ISODate("2026-11-14T10:15:00Z"),
  sourceWatermark: ISODate("2026-11-14T10:10:00Z")
}
~~~

`computedAt` records when the result was written, while `sourceWatermark` (if present) shows up to which timestamp source data has been processed. Those two timestamps can differ due to late-arriving events.

Business rules must be settled upfront: is revenue gross paid amount or net after refunds? How are cancelled orders counted? Which timezone defines a day? Can late transactions update closed days? The Computed pattern optimizes performance, yet **cannot replace KPI definitions**.

### 4.6. Distinguishing Computed Values from Plain Caches

A computed value is usually persisted as part of the queryable data model with defined update and freshness policies. An application cache or Redis can also hold results, typically with different eviction and lifecycle rules. A system may store computed stats in MongoDB and cache read responses at the API layer; those two layers solve distinct concerns.

**Use Computed when** calculations are expensive, results are read very frequently, and lag can be tolerated or managed cleanly. **Be cautious** with payment balances, available inventory, or invariants demanding absolute accuracy: storing computed values is still possible, but requires matching transactional consistency rather than defaulting to eventual consistency.

---

## 5. Bucket Pattern: Group Many Small Records into Bounded Units

### 5.1. Problem

A sensor emits one reading per second. If each reading is a separate document, one day generates 86,400 documents per device. Across many devices, document counts and index entries grow rapidly. When APIs mainly render hourly charts for a device, grouping consecutive readings helps.

The **Bucket pattern** groups closely related small records into one document by criteria such as device and time window.

~~~javascript
// sensorBuckets
{
  _id: "sensor-7|2026-11-14T09:00Z|0",
  sensorId: "sensor-7",
  windowStart: ISODate("2026-11-14T09:00:00Z"),
  windowEnd: ISODate("2026-11-14T10:00:00Z"),
  sequence: 0,
  count: 3,
  measurements: [
    { at: ISODate("2026-11-14T09:00:01Z"), value: 23.4 },
    { at: ISODate("2026-11-14T09:00:02Z"), value: 23.5 },
    { at: ISODate("2026-11-14T09:00:03Z"), value: 23.5 }
  ]
}
~~~

One document holds shared metadata (`sensorId`, time range), multiple measurements, and the item count. Querying a device over a time range reads a handful of buckets instead of thousands of individual documents.

### 5.2. Choosing Bucket Criteria

A bucket can be bounded by:

- **Time:** one minute, one hour, one day.
- **Element count:** at most 500 or 1,000 measurements.
- **BSON size:** close the bucket well before approaching 16 MiB.
- **Grouping key:** e.g., `sensorId`, `tenantId`, `customerId`, event type.
- **Combination:** `sensorId` + one hour + max 1,000 items + safe byte threshold.

No "one bucket per hour" rule fits every device. If a device emits 10,000 readings/sec, one hour is far too big; if a device emits only a few records per month, hourly buckets create sparse fragmentation.

The **16 MiB BSON limit still applies to each bucket**. Bucketing is not a trick to bypass document limits by renaming an array; it is a way to **partition data into multiple bounded documents**.

### 5.3. Example Updating an Existing Bucket

Suppose the system initialized a bucket with `count: 0`, capped at 1,000 readings per bucket:

~~~javascript
const measurement = {
  at: ISODate("2026-11-14T09:12:00Z"),
  value: 24.1
};

const result = db.sensorBuckets.updateOne(
  {
    _id: "sensor-7|2026-11-14T09:00Z|0",
    count: { $lt: 1000 }
  },
  {
    $push: { measurements: measurement },
    $inc: { count: 1 }
  }
);
~~~

The `$push` and `$inc` pair inside one document update is atomic. The condition `count: { $lt: 1000 }` stops writes once the bucket is full **assuming the counter is maintained accurately**. If `matchedCount === 0`, the application must distinguish a missing bucket from a full bucket and allocate the next bucket according to rollover rules.

This example **does not fully handle** bucket creation, duplicate writes, concurrent producers, or byte caps; production systems need a protocol for allocating `sequence`, unique keys, idempotency, and retries. With variable-sized elements, fewer than 1,000 items can still exceed byte thresholds, so guarding on `count` alone is insufficient.

### 5.4. Queries and Indexes

~~~javascript
db.sensorBuckets.createIndex({
  sensorId: 1,
  windowStart: 1,
  sequence: 1
});

db.sensorBuckets.find({
  sensorId: "sensor-7",
  windowStart: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T12:00:00Z")
  }
}).sort({ windowStart: 1, sequence: 1 });
~~~

This query finds buckets whose window starts inside the given range. For a query asking for "exact readings from 08:15 to 11:45," you must also include buckets that **overlap** the range even if they started earlier, and filter elements inside `measurements`. Filtering strictly on `windowStart >= 08:15` would miss the 08:00 bucket even if it holds a reading at 08:20.

An overlap condition using half-open intervals `[windowStart, windowEnd)`:

~~~javascript
db.sensorBuckets.find({
  sensorId: "sensor-7",
  windowStart: { $lt: ISODate("2026-11-14T11:45:00Z") },
  windowEnd: { $gt: ISODate("2026-11-14T08:15:00Z") }
});
~~~

The API must filter out measurements falling outside the requested range after fetching buckets, or use an aggregation pipeline to do so. If you frequently need to query individual points independently, storing all points inside bucket arrays can become a hindrance.

### 5.5. Trade-offs of the Bucket Pattern

**Benefits:**

- Reduces document counts and repeated metadata when many small samples group together.
- Convenient for reads grouped by time window, device, or session.
- Can store bucket-level summaries such as `min`, `max`, and `count` to cut processing work.
- Creates natural units for retention, cold tiering, or group pagination.

**Costs and risks:**

- Multiple producers updating the same active bucket can create a **hot document** and write contention.
- Editing/deleting a single array element is more complex than updating an independent document.
- Must handle full buckets, late-arriving data, duplicates, and window boundaries.
- Indexes on array elements and document sizes can grow; single-event lookups are not necessarily faster.
- If TTL or deletion runs at the bucket level, decide whether deleting the entire bucket when only some readings have expired is acceptable.

### 5.6. Custom Buckets vs. Time Series Collections

MongoDB provides **time series collections** to support time-ordered workloads and store measurements efficiently. This is a native database feature with specific rules for `timeField`, `metaField`, storage layout, indexing, and version-dependent update/delete constraints.

~~~javascript
db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "timestamp",
    metaField: "metadata",
    granularity: "minutes"
  }
});

db.sensorReadings.insertOne({
  timestamp: ISODate("2026-11-14T09:12:00Z"),
  metadata: { sensorId: "sensor-7", siteId: "HCM-01" },
  value: 24.1
});
~~~

Here the application inserts **each reading as a logical document**, and MongoDB manages internal time series storage automatically. There is no need to manually maintain `measurements` arrays and `sequence` numbers as in custom buckets above.

Evaluate time series collections first if your workload genuinely consists of time-stamped measurements and your MongoDB version/constraints align. Custom buckets remain valuable for transaction groups, events, or custom bucketing rules that time series collections do not fit.

---

## 6. Attribute Pattern: Standardize Diverse Attributes

### 6.1. Problem

A catalog includes laptops, shirts, and books. Using fixed top-level fields for every variant:

~~~javascript
// Laptop
{ _id: "P-L1", category: "laptop", ramGb: 16, storageGb: 512 }

// Clothing
{ _id: "P-C1", category: "clothing", size: "M", fabric: "cotton" }

// Book
{ _id: "P-B1", category: "book", author: "Author A", pageCount: 320 }
~~~

MongoDB's flexible schema allows storing these fields. However, if the system lets users filter across hundreds of category-specific attributes and new attributes are added regularly, designing and maintaining separate indexes for every dynamic field becomes costly.

The **Attribute pattern** moves queryable attributes into a uniform structure, typically **an array of objects holding attribute name and value**.

~~~javascript
{
  _id: "P-L1",
  category: "laptop",
  name: "Laptop 14 inch",
  attributes: [
    { key: "ramGb", numberValue: 16 },
    { key: "storageGb", numberValue: 512 },
    { key: "color", stringValue: "silver" },
    { key: "touchscreen", booleanValue: false }
  ]
}
~~~

Note that this is **one implementation** of the Attribute pattern, not a mandatory standard schema. Some systems use `k`/`v`, others use `name`/`value`, or objects with `type`/`unit`/`displayName`. The goal is a consistent structure for filterable attributes.

### 6.2. Why Separate Value Types?

A seemingly simpler implementation is:

~~~javascript
attributes: [
  { key: "ramGb", value: "16" },
  { key: "storageGb", value: "512" },
  { key: "color", value: "silver" }
]
~~~

Yet storing everything as strings breaks numeric range filtering. Lexicographical comparison between `"16"` and `"8"` does not match numeric comparison between 16 and 8. A schema can use typed fields like `numberValue`, `stringValue`, `dateValue`, `booleanValue`, or declare explicit type metadata.

~~~javascript
{
  _id: "P-L2",
  category: "laptop",
  attributes: [
    { key: "ramGb", type: "number", numberValue: 32, unit: "GB" },
    { key: "weightKg", type: "number", numberValue: 1.35, unit: "kg" },
    { key: "color", type: "string", stringValue: "black" }
  ]
}
~~~

If data comes from multiple sources, **normalize units** before filtering: 1,500 g and 1.5 kg represent the same weight, yet filtering directly on `1500` vs. `1.5` fails without unit normalization. Attribute keys must also follow a business glossary: `memory`, `ram`, and `ramGb` will not match as the same key just because humans understand them similarly.

### 6.3. Indexing with the Attribute Pattern

Suppose we need to filter laptops with at least 16 GB of RAM:

~~~javascript
db.products.createIndex({
  category: 1,
  "attributes.key": 1,
  "attributes.numberValue": 1
});

db.products.find({
  category: "laptop",
  attributes: {
    $elemMatch: {
      key: "ramGb",
      numberValue: { $gte: 16 }
    }
  }
});
~~~

`attributes` is an array, so indexes on its subfields are **multikey indexes**. How fields inside the same array combine and the limitations of compound multikey indexes must be evaluated against the real structure.

**Why use `$elemMatch`?** If you write:

~~~javascript
// Can match two DIFFERENT elements in the same array:
db.products.find({
  "attributes.key": "ramGb",
  "attributes.numberValue": { $gte: 16 }
});
~~~

A document with `ramGb = 8` and `storageGb = 512` satisfies that query because `key` matches the RAM element while `>= 16` matches the storage element. `$elemMatch` requires **all conditions to hold on the same array element**, preventing wrong matches and helping MongoDB apply tighter index bounds.

Logic bug example:

~~~javascript
{
  _id: "P-L3",
  category: "laptop",
  attributes: [
    { key: "ramGb", numberValue: 8 },
    { key: "storageGb", numberValue: 512 }
  ]
}
~~~

A query using two separate dotted paths matches this document, whereas an `$elemMatch` query for `ramGb >= 16` correctly rejects it.

### 6.4. Filtering Multiple Attributes

To find laptops with at least 16 GB RAM **and** at least 512 GB storage (with normalized units), each condition targets its own array element:

~~~javascript
db.products.find({
  category: "laptop",
  $and: [
    {
      attributes: {
        $elemMatch: {
          key: "ramGb",
          numberValue: { $gte: 16 }
        }
      }
    },
    {
      attributes: {
        $elemMatch: {
          key: "storageGb",
          numberValue: { $gte: 512 }
        }
      }
    }
  ]
});
~~~

MongoDB must evaluate conditions across different attribute elements. A single index will not optimize every possible filter combination; when attribute counts, filters, and combinations explode, evaluate query plans, multikey index overhead, and dedicated search engines.

### 6.5. When Should Fields Remain Fixed?

The Attribute pattern does not force converting **every field** into an array element.

Fields like `_id`, `sellerId`, `category`, `status`, `createdAt`, or `priceMinor` appear on almost every product and participate in primary queries. Keeping them at the top level keeps the schema clear and avoids scanning `attributes` for common business predicates.

~~~javascript
{
  _id: "P-L1",
  sellerId: "S42",
  category: "laptop",
  status: "ACTIVE",
  priceMinor: 19500000,
  attributes: [
    { key: "ramGb", numberValue: 16 },
    { key: "storageGb", numberValue: 512 }
  ]
}
~~~

A **hybrid model** (fixed core fields + flexible attributes) is generally far easier to operate than forcing every field into a key–value array.

### 6.6. Trade-offs of the Attribute Pattern

**Benefits:** the model handles diverse attribute types, unifies dynamic filtering, and avoids creating separate indexes for every varying field name.

**Costs:** each attribute repeats key/type names, growing document size; queries require `$elemMatch`; validation and indexing are trickier; sorting by a specific attribute or combining many filters can be hard to optimize. If a document holds two elements with the same `key` but different values, the application must define whether that is an error, a multi-value list, or has precedence rules.

**Never adopt it just because "MongoDB is schema-less."** If a domain only has 5–10 stable attributes, top-level fields are simpler, easier to index, and easier to maintain. If dynamic attributes are vast and search is central, compare against wildcard indexes and dedicated search solutions; measure rather than assuming Attribute is always fast.

---

## 7. Comparing the Four Patterns by Data Organization

| Question | Subset | Computed | Bucket | Attribute |
| --- | --- | --- | --- | --- |
| Primary unit changed | Hot read slice vs. full dataset. | Precalculated result from source data. | Group of related records. | Representation of varying attributes. |
| Reads optimized | Reading hot portion without touching cold data. | Reading precomputed aggregate values. | Reading many grouped events together. | Filtering by dynamic attribute name and value. |
| Writes added | Syncing preview with source. | Updating/reconciling derived values. | Appending events; managing full buckets. | Maintaining attribute array and indexes. |
| Core risk | Stale or mismatched preview. | Duplicate/wrong counters, lagged data. | Oversized buckets, hot documents. | Unstandardized types, wrong array element matching. |
| Selection criterion | Highly skewed data access. | Expensive repeated calculations. | Small, numerous events usually read in groups. | Diverse attributes needing flexible filters. |

You can remember them with four verbs:

- **Subset:** *trim* less-used data out of frequently read documents.
- **Computed:** *precalculate* frequently requested results.
- **Bucket:** *group* many records under a bounded rule.
- **Attribute:** *standardize* how dynamic attributes are represented.

These four patterns do not replace indexes, schema validation, unique constraints, transactions, or backups. They operate at the data modeling layer, while other database mechanisms ensure correctness and operational performance.

## 8. Combining Multiple Patterns in One Application

Returning to the e-commerce platform, a combined design could look like:

~~~text
products
  - _id, category, name, priceMinor, status
  - attributes[]               <-- Attribute: RAM, size, color, ...
  - latestReviewPreview[]      <-- Subset: a few newest reviews
  - reviewStats                <-- Computed: count, sum, average
             |
             +---- reviews
                       - full reviews, unbounded growth

dailySales
  - sellerId, day, totals      <-- Computed: daily order count / revenue

viewEventBuckets
  - productId, timeWindow
  - events[]                   <-- Bucket: grouped view events

orders
  - individual orders and canonical payment details
~~~

Each piece serves a specific purpose:

1. Listing pages query `products`, fetching regular fields and `reviewStats`.
2. Detail pages display `latestReviewPreview` immediately; full pagination hits `reviews`.
3. Filters by RAM or size use `attributes` with matching schema/indexes.
4. Revenue dashboards query `dailySales`, including freshness timestamps.
5. View analytics read buckets or process retained event sources.

A critical question: **which data is allowed to lag?** Review scores can lag by a few seconds, whereas payment status cannot arbitrarily lag if it affects fulfillment. Each data class needs its own consistency policy.

## 9. Updates via Transactions or Events?

When using Subset and Computed, updates often span multiple documents. There are three ways to organize them, with no single universal answer.

### 9.1. Multi-Document Transactions

If updating the source and derived values must succeed or abort together, MongoDB supports multi-document transactions in suitable configurations.

~~~text
Begin transaction
  -> write valid review
  -> update stats/preview
Commit
~~~

Transactions give a crisp consistency boundary, yet add operational overhead and conflict/retry exposure. Keep transactions short and never place network calls or long work inside them. Additionally, creating a review may require once-only deduplication by `reviewId` before updating stats.

### 9.2. Event-Driven and Eventual Consistency

When brief display lag is acceptable:

~~~text
Write review -> emit event -> worker processes -> update products
                                          |
                                          +-> error -> retry / dead letter / reconcile
~~~

Requirements include unique event IDs, idempotency, queue monitoring, replay capability, and handling out-of-order updates. Derived data must be recomputable from the source to repair drift.

### 9.3. Batch / Rebuild

A periodic job can aggregate the source and rewrite computed or subset fields. Batching is simple for non-real-time metrics, though it can be I/O-heavy. During rebuilds, never allow stale batch results to overwrite newer values just updated by an event stream; use watermarks, versions, or controlled swap/reconciliation logic.

### 9.4. Example: Handling an Edited Review

Suppose a review with `rating = 5` is edited to `rating = 3`:

- `reviews` records the new value or edit history per policy.
- `reviewStats.count` stays unchanged if the review remains valid.
- `reviewStats.ratingSum` decreases by 2.
- `latestReviewPreview` updates if the review is currently in the displayed subset.
- If the review transitions to `HIDDEN`, remove it from both stats and preview.
- If the same message is redelivered, never subtract 2 a second time.

Every pattern requires defining **old state, new state, and transition events**; never blindly increment counters on every notification.

## 10. Choosing Patterns with Concrete Questions

| Practical Question | Pattern to Evaluate | Why |
| --- | --- | --- |
| User profile has 10,000 login sessions, profile screen needs only 3 latest? | Subset | Full history in separate collection, bounded hot slice in profile. |
| Product page gets 10,000 hits/hr, new reviews arrive only a few times/hr? | Computed | Read precalculated stats instead of grouping reviews per request. |
| Sensor emits 500,000 small records/day, API reads hourly windows? | Bucket or time series collection | Group or organize data by time to improve reads and storage. |
| Products have hundreds of varied specs and filter by attribute name? | Attribute | Unified query structure for dynamic attributes. |
| Collection has few fields, small docs, queries already well-indexed? | Probably no pattern needed | Adding modeling layers may only add complexity. |
| All fields are used together on every request and change together? | Simple embedding | No clear benefit from splitting a subset. |
| Computed value is a balance requiring accuracy right after a transaction? | Design consistency first | Never assume eventual consistency just because Computed is used. |
| Individual events update at very high frequency? | Consider separate documents | Buckets could turn into write hotspots. |

## 11. Evaluating Query Plans and Before/After Performance

Never adopt a pattern simply because a guide claims it is "faster." Measure your workload on representative data.

~~~javascript
db.products.find({
  category: "laptop",
  status: "ACTIVE",
  attributes: {
    $elemMatch: {
      key: "ramGb",
      numberValue: { $gte: 16 }
    }
  }
}).explain("executionStats");
~~~

Metrics to inspect include returned document count, keys/documents examined, `IXSCAN`/`COLLSCAN` plans, test query duration, and resource consumption. In production, also monitor p95/p99 latency, CPU, cache usage, read/write IOPS, index size, and write throughput.

Evaluation examples:

| Before Change | After Change | Base Conclusions On |
| --- | --- | --- |
| Loading product embedding thousands of reviews | Reading preview + paginated separate reviews | Product detail p95, document size, read I/O, sync cost. |
| Computing rating via aggregation per request | Reading `reviewStats` | How much p95 and CPU drop, whether update lag is acceptable. |
| One document per measurement | Grouping into bounded buckets | Storage/index size, write throughput, range queries, contention. |
| Hundreds of dynamic fields, many separate indexes | Attribute + key/value pair index | Query plan quality, index size, concurrent filters, ingest cost. |

**Better read performance paired with wrong writes or stale data** is not a win. Evaluate correctness and freshness alongside latency.

## 12. Common Limits and Risks

### 12.1. 16 MiB Document Maximum

Subset shrinks the main document; Buckets still need bounds; Attribute arrays can grow heavy if attribute counts explode. Never use any of these patterns assuming MongoDB has lifted the 16 MiB limit.

### 12.2. Duplicated Data and Reconcilability

Computed and Subset duplicate or store derived values. Define the source of truth, rebuild mechanism, and drift detection; never allow two copies to update independently without an arbitration rule.

### 12.3. Indexes Have Costs

Attribute and Bucket may need multikey or compound indexes; Subset needs indexes on the child collection; Computed needs indexes matching dashboard reads. Every index consumes storage and slows writes. Periodically audit unused indexes against real workloads.

### 12.4. Hot Documents and Update Contention

Computed counters on a wildly popular product or a bucket taking thousands of concurrent updates can become hotspots. Atomic single-document updates do not mean throughput scales infinitely. You may need counter partitions, batching, bucket splitting, or redesigned write paths—each adding aggregation and consistency complexity.

### 12.5. Schema Versioning and Migration

When migrating from embedded reviews to Subset, or from `ramGb` to `attributes`, old and new formats coexist during rollout. Applications need backward-compatible reads, backfills, controlled dual-writes if needed, and a cutoff to retire legacy paths. Migrations must verify record counts, detect missing records, and support planned rollback or recovery.

### 12.6. Idempotency and Event Ordering

Event-driven systems typically provide **at-least-once delivery**, without guaranteeing exact-once delivery or business-order delivery across every path. Incrementing with `$inc` or `$push` without idempotency controls causes duplicate data. Enforce event IDs, ordering/version checks, or recompute from the source when needed.

## 13. Common Design Mistakes and Fixes

### Mistake 1: Subset Turns into a Full Copy

The `products` document starts holding the 3 latest reviews at launch, grows to 20, then 100, and eventually holds every review. Subset loses its working-set benefit. Fix by enforcing a **hard bound**, using `reviews` for full data, and maintaining a strict preview update policy.

### Mistake 2: Computed Count Increments Twice on Retry

A review-added event delivered twice increments `reviewCount` by 2. Fix with idempotency keys, a transaction recording processed event status, or a verifiable update model paired with reconciliation.

### Mistake 3: Daily Buckets Without Byte Limits

One device spikes in traffic and the bucket hits 16 MiB before the day ends. Fix with combined limits on time, element count, and bytes, plus clear rules for closing and rolling over to the next bucket.

### Mistake 4: Attribute Query Matches Across Different Elements

The query uses two separate dotted paths and pairs `ramGb` with `storageGb`'s value, returning 8 GB RAM laptops for a RAM >= 16 GB filter. Fix with `$elemMatch` for conditions that must apply to the same element, and index according to access patterns.

### Mistake 5: Moving Every Field into Attribute

Even `priceMinor`, `status`, and `sellerId` become key–value array items, complicating basic queries and hurting index efficiency. Fix by keeping common, stable fields at the document root and moving only dynamic attributes with clear justification.

### Mistake 6: Treating Computed Results as Source Data

When computed stats go wrong, no event data remains to rebuild them. Fix by defining the source of truth and retention before introducing computed projections. If source data must be purged for compliance, establish an audit/archival workflow compatible with those rules.

## 14. Design Exercise: An Online Learning Platform

Suppose an online learning platform has:

- Each course can have thousands of reviews; the landing page only needs the five newest reviews.
- The home page displays completion count and average rating.
- Each learner generates many minute-by-minute video playback events.
- Each course has subject-specific metadata: level, language, certificate, practice tools.

**Suggested organization:**

~~~javascript
// courses
{
  _id: "COURSE-JAVA-01",
  title: "Java Fundamentals",
  category: "programming",
  stats: {
    completionCount: 1800,
    ratingCount: 430,
    ratingSum: 1910
  },                              // Computed
  latestReviewPreview: [
    { reviewId: "RV1", rating: 5, excerpt: "Easy to follow" }
  ],                              // Subset
  attributes: [
    { key: "level", stringValue: "beginner" },
    { key: "language", stringValue: "vi" }
  ]                               // Attribute
}

// courseReviews: full reviews keyed by courseId
// playbackBuckets: bounded playback events per learner and hourly window
~~~

Questions to answer before implementation:

1. If a review is hidden, how are preview and stats updated?
2. Is `completionCount` per unique learner or per completion event? How do you prevent double-counting on event retries?
3. If a learner seeks through a video 1,000 times in an hour, could the bucket exceed element or document size limits?
4. Do we need to search courses by two different attributes simultaneously? How will `$elemMatch` queries and indexes be designed?
5. Which metadata should be fixed fields and which truly belong as flexible attributes?
6. How much lag is acceptable for stats? Do the public catalog page and the certificate-issuing service share the same consistency requirements?

This exercise highlights that pattern selection must tie to **business definitions**, not merely JSON shape.

## 15. A Practical Decision Workflow

1. **List critical queries and writes.** Record filters, sorts, returned doc/field counts, frequencies, target latencies, and consistency needs.
2. **Flag growing data.** Spot unbounded arrays, events, large files, expanding metadata, and costly aggregations.
3. **Prioritize top read paths.** If 95% of requests need only a small slice, evaluate Subset; if repeating the same aggregate, evaluate Computed.
4. **Examine small record groups.** If queries read by device/time window, evaluate Bucket and time series collections; watch out for hot documents.
5. **Evaluate attribute flexibility.** If many dynamic fields need filtering, test Attribute and indexes; keep stable fields directly at the root.
6. **Define sources of truth and update rules.** Every copy/derived value needs an owner, staleness policy, rebuild path, retry logic, and validation.
7. **Test with realistic data volume.** Measure query plans, p95/p99, storage, index size, write throughput, and errors under concurrency.
8. **Test edge cases.** Deleted reviews, late/duplicate events, full buckets, items with thousands of attributes, concurrent workers.
9. **Deploy with observability.** Monitor computed/subset age, sync errors, near-full buckets, and new query performance.
10. **Re-evaluate after growth.** A schema that shines at 10,000 documents may need adjustment as workload and data distributions evolve.

## 16. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "Subset is just projection." | Projection filters returned fields; Subset reorganizes stored data and full sources. |
| "Subset means never storing duplicates." | Previews are typically controlled copies of data living in another collection. |
| "Computed is automatically always accurate." | You must design updates, retries, idempotency, late events, and reconciliation. |
| "Using `$inc` guarantees once-only event processing." | `$inc` is atomic per document, yet repeated calls increment repeatedly. |
| "Buckets bypass the 16 MiB limit." | Each bucket is still a BSON document subject to the 16 MiB cap. |
| "Bigger buckets always save more." | Oversized buckets increase update costs, cause contention, and hinder point queries. |
| "The Bucket pattern is time series collections." | One is an application modeling pattern; the other is a native MongoDB storage feature. |
| "Attribute requires moving all fields into an array." | Stable, frequently used fields usually belong at the top level. |
| "Dotted paths on arrays suffice to match conditions on the same element." | Use `$elemMatch` when constraints must match the exact same element. |
| "One attribute index solves every filter combination." | Multikey indexes have limits and costs; verify actual query plans. |
| "Read-optimizing patterns always cut total cost." | They often increase write count, storage, index size, or sync complexity. |

## 17. Selection Summary

- Choose **Subset** when many requests need only a small, bounded hot slice of an entity whose full data is much larger.
- Choose **Computed** when the same calculation is read very frequently and you have reliable update, freshness monitoring, and recomputation workflows.
- Choose **Bucket** when many small records are naturally accessed in groups, while still enforcing time, count, and size bounds plus hot-document mitigation.
- Choose **Attribute** when varying attributes must be searched through a uniform structure, with controlled data types, units, and array queries.

A good design pattern is one that makes critical access paths **simpler and measurably effective**, while preserving correctness, document limits, and operational clarity. An effective document model does not start with "how much JSON can we stuff together," but with how the system reads, writes, reconciles, and scales data.
