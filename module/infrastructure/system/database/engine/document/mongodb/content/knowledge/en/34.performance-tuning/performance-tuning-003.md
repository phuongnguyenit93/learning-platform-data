# Optimizing Document Models by Access Patterns and Update Frequency in MongoDB

## 1. From a "Pretty" Data Structure to a High-Performing Data Structure

An engineering team builds an e-commerce platform using MongoDB. Each product has a name, description, brand, price, inventory, multiple variants, thousands of reviews, and stock adjustment history.

Initially, they store everything in a single document:

```javascript
{
  _id: "P1001",
  name: "Bluetooth Headphones",
  description: "Product description...",
  price: 890000,
  inventory: {
    available: 127,
    reserved: 12
  },
  reviews: [
    /* thousands of reviews */
  ],
  stockMovements: [
    /* stock-in, stock-out, adjustment history */
  ]
}
```

Reading the product page is convenient: a single `findOne()` retrieves a lot of information. However, as traffic grows, problems emerge:

- Inventory updates hundreds of times per hour, whereas name and description rarely change.
- Every new review grows the `reviews` array; the document risks hitting the 16 MiB limit.
- Inventory updates, product content edits, and new reviews all contend on the same document.
- Listing pages only need name, price, and thumbnail, yet queries or processing accidentally pull in heavy detail data.
- Indexes on frequently updated fields increase write overhead.
- Rating statistics must be aggregated from many reviews, yet do not necessarily need recomputation on every request.

The engineering team splits the data into several collections according to access needs. Reading the product page may take more steps, yet **write throughput increases, document sizes remain stable, and large datasets have independent lifecycles**.

**Lesson:** Document modeling in MongoDB is not just choosing `embed` vs. `reference` from entity relationships. You must design for the **actual workload**, especially **hot read paths, update frequency, array growth, data size, and required consistency**.

### 1.1. Objectives

After this lesson, you will be able to:

1. Gather and express access patterns as concrete queries and updates.
2. Separate data groups that are frequently read together from data groups that are frequently updated together.
3. Choose **embedding**, **referencing**, or **hybrid** designs for 1–1, 1–N, N–N relationships, and unbounded growth data.
4. Explain trade-offs among **read amplification**, **write amplification**, document contention, working set, and round-trip counts.
5. Separate hot fields from cold fields, bound unbounded arrays, and apply the **subset, outlier, extended reference, computed, and bucket patterns** appropriately.
6. Design indexes and projections aligned with query shapes without creating excessive write overhead.
7. Maintain correctness when data is duplicated using atomic updates, optimistic concurrency, and transactions only when truly required.
8. Measure effectiveness using `explain("executionStats")`, the profiler, metrics, and benchmarks on representative workloads.
9. Build a safe schema migration plan with rollback and clear success criteria.

## 2. The Right Question Is Not "Does MongoDB Support This Relationship?"

MongoDB stores BSON documents capable of representing nested objects and arrays. Two collections can still relate via keys and be combined with `$lookup`.

The question to answer is:

> **How often is one piece of data read with another, how often do they change together, how large can they grow, and how consistent must they be?**

### 2.1. Four Critical Dimensions

| Dimension | Question | Impact on Schema |
|---|---|---|
| **Read locality** | Which fields are read together? | Prefer colocating/embedding frequently co-read data |
| **Update locality** | Which fields change together? | Group fields updated in the same business operation |
| **Growth/cardinality** | How many child items can one entity generate? | Decides bounded array vs. separate collection |
| **Consistency/lifecycle** | How consistent must data be and how is it retained/deleted? | Choose snapshot, reference, transaction, or event history |

### 2.2. A Schema That Works Today Can Fail in Six Months

A product with 4 reviews is fine with an embedded reviews array. The exact same design becomes very expensive when a popular product reaches 300,000 reviews.

Do not evaluate a model solely on a small development dataset. Examine:

- Actual size distribution (p50, p95, p99, max).
- Monthly growth rate.
- Outliers—products or tenants with abnormally high cardinality.
- Shifts in the read/write ratio over the entity lifecycle.

### 2.3. A Valid Answer Can Be "Hybrid"

Product example:

```text
products
  - name, thumbnail, description, category
  - ratingSummary
  - 3 featured reviews

productInventory
  - quantity/reserved/version (written frequently)

productReviews
  - each review is an independent document (large growth)

stockMovements
  - historical log as independent documents
```

This keeps listing reads fast from `products` while hot data and large datasets maintain independent update lifecycles.

## 3. Understanding Limits and Data Mechanics Related to Performance

### 3.1. 16 MiB Maximum BSON Document Size

MongoDB enforces a **16 MiB BSON document size limit**. The limit applies to the stored document, including nested objects and arrays.

If each embedded review averages 2 KiB, 8,000 reviews alone reach roughly 16 MiB, before field names, BSON overhead, and product fields:

```text
8,000 * 2 KiB = 16,000 KiB ≈ 15.625 MiB
```

This is a rough estimate; **do not design close to the limit** using simple multiplication. Real review and document sizes vary widely.

### 3.2. Single-Document Write Atomicity

MongoDB guarantees **single-document atomicity** for an individual write operation, even when updating multiple fields within that document.

Example:

```javascript
db.productInventory.updateOne(
  { _id: "P1001" },
  {
    $inc: {
      available: -1,
      reserved: 1
    }
  }
);
```

Both changes on the same document occur within one atomic single-document update, though business logic must still guard stock conditions and check matched/modified counts.

### 3.3. Multi-Document Transactions Exist but Are Not Free

When splitting data across collections, MongoDB supports **multi-document transactions** on compatible deployments. However, transactions incur session, locking/conflict, latency, and operational costs. Do not use transactions to mask an unthoughtful schema when the data fits cleanly in one small document and updates together.

### 3.4. Splitting Documents Is Not Automatically Faster

Adding collections means you may need:

- One or more extra queries.
- `$lookup` or application-level composition.
- Indexes on foreign keys.
- Consistency coordination.
- Extra writes if denormalizing.

Therefore **split data only when measurable benefits or clear growth risks outweigh cross-collection access costs**.

## 4. Start from Workload: Building an Access-Pattern Matrix

Before picking a schema, document **the operations the application actually executes**, rather than modeling entities directly from Java classes.

### 4.1. Example Catalog Workload

| ID | Operation | Input | Required Fields | Illustrative Frequency | Target Latency |
|---|---|---|---|---|---|
| R1 | Product listing | category, sort | name, price, thumbnail, ratingSummary | 4,000/min | p95 under 100 ms |
| R2 | Product detail | productId | description, images, variants, top 3 reviews | 800/min | p95 under 150 ms |
| R3 | View reviews | productId, cursor | 20 reviews/page | 120/min | p95 under 200 ms |
| R4 | Check inventory | productId | available, reserved | 6,000/min | p95 under 50 ms |
| W1 | Deduct/reserve stock | productId, delta | available, reserved, version | 1,500/min | p95 under 50 ms |
| W2 | Edit description | productId | description | 5/day | Can be slower |
| W3 | Add review | productId | review content, rating | 150/min | Durable write |
| W4 | Update rating summary | productId | ratingCount, ratingSum | per W3 | Eventual or transactional |

**These frequencies and SLOs are hypothetical.** A real system must gather them from metrics, logs, and traces, separating peak from normal load.

### 4.2. Hot Read Path

R1 needs:

```javascript
{
  _id: "P1001",
  name: "Bluetooth Headphones",
  price: 890000,
  thumbnail: "/img/p1001.jpg",
  ratingSummary: {
    count: 824,
    average: 4.7
  }
}
```

R1 **does not need** 3,000 reviews, stock movement history, or a 20 KiB description.

### 4.3. Hot Write Path

W1 modifies `available`/`reserved` thousands of times per hour. If inventory is merged with product content, every hot write touches a document carrying relatively cold data.

This is a prime candidate for extracting a separate **inventory document** to reduce concurrent write pressure and keep the product read model stable.

### 4.4. Frequency Is Not the Only Factor

Two fields updated at similar rates may still warrant separation if they:

- Are owned and updated by different services.
- Have different access permissions.
- Have different contention/hot-key profiles.
- Have different TTL/retention policies.
- Have different consistency requirements.

Conversely, a rarely changing field that is **small and always needed in the same response** can be embedded.

## 5. Gathering Evidence-Based Access Patterns

### 5.1. Data Sources

- Application traces: endpoint, duration, DB call counts.
- MongoDB profiler / slow query logs: query shape, plan, runtime.
- `explain()`: index usage, documents/keys examined.
- Metrics: operation rates, WiredTiger cache, disk IOPS, CPU.
- Change streams / business events: update types and frequencies.
- Product analytics: whether users actually open reviews.
- Batch/ETL calendars: periodic write bursts.

### 5.2. Grouping Queries by Shape

Two requests:

```javascript
db.products.findOne({ _id: "P1001" });
db.products.findOne({ _id: "P1002" });
```

share the **same query shape** despite different literal IDs.

Aggregate statistics such as:

```text
operation=findOne
collection=products
predicate=_id_eq
projection=summary-fields
frequency/min=...
p95Ms=...
```

You do not need to log PII or raw query literals in observability pipelines to evaluate schemas.

### 5.3. Do Not Look Only at the Average

Example:

```text
Product reviews array size:
  median: 6
  p95:    200
  p99:    3,000
  max:    190,000
```

Looking only at `median=6`, embedding all reviews seems reasonable. Yet large outliers expose the design to 16 MiB limits and write contention.

Always inspect the full distribution, not just the average.

## 6. Embed or Reference?

### 6.1. Embedding

Example order document:

```javascript
{
  _id: "O1001",
  customerId: "C20",
  status: "PAID",
  shippingAddressSnapshot: {
    city: "Da Nang",
    district: "Hai Chau",
    street: "123 Example"
  },
  items: [
    {
      sku: "P1001",
      nameSnapshot: "Bluetooth Headphones",
      unitPrice: 890000,
      quantity: 2
    }
  ],
  total: 1780000
}
```

Pros:

- Reading one order retrieves shipping details and items with no join.
- Order fields can update atomically in the same document.
- Snapshots preserve price, name, and address at purchase time.

Cons:

- An order with an enormous number of line items can grow too large.
- Product details are duplicated and must be distinguished from live catalog data.
- If an embedded field ever required bulk updates across all historical orders, write amplification would be massive.

### 6.2. Referencing

Example:

```javascript
// products
{ _id: "P1001", name: "Bluetooth Headphones" }

// productReviews
{
  _id: "REV5001",
  productId: "P1001",
  rating: 5,
  comment: "Works great",
  createdAt: ISODate("2026-09-01T10:00:00Z")
}
```

Pros:

- Numerous and unbounded items are stored as independent documents.
- Each review has its own lifecycle, updates, indexes, and retention.
- Paginating reviews avoids loading the entire array.

Cons:

- The product page needs a second query or `$lookup` to display reviews.
- Needs indexes on `productId` + sort keys.
- May require syncing a rating summary on the product.
- Atomicity between product and review is not automatic across documents.

### 6.3. Decision Guidelines

**Lean toward embedding when:**

- Data is **read together most of the time**.
- The array/subdocument has a **strictly bounded size**.
- Fields change together as **one business unit**.
- Atomic updates across those fields are needed.
- Child data lacks an independent lifecycle.

**Lean toward referencing when:**

- Item count can grow large or unbounded.
- Child data is rarely read alongside the parent.
- Items need independent search, pagination, or updates.
- Concurrent updates, different permissions, or distinct TTLs exist.
- An entity is shared and updated from multiple parents.

### 6.4. Not Immutable Laws

A 20-element array should not automatically be embedded, nor must a 500-element array automatically be referenced: element size, growth rate, read access, indexes, and update patterns are the real criteria.

## 7. One-to-One: Separating Hot and Cold Fields

Suppose an account has:

```javascript
{
  _id: "U100",
  displayName: "Customer A",
  profile: {
    biography: "...",
    avatar: "/a.png"
  },
  sessionStats: {
    lastSeenAt: ISODate("2026-11-14T04:00:00Z"),
    requestCount: 100000
  }
}
```

`profile` changes rarely; `sessionStats` updates continuously.

### 7.1. When to Keep in One Document?

If per-request writes are infrequent, contention is low, and atomicity with `profile` is needed, keeping them together can be simpler.

### 7.2. When to Split into Two Documents?

If thousands of events per second update a celebrity user or bot account, you can split:

```javascript
// users
{
  _id: "U100",
  displayName: "Customer A",
  profile: { biography: "...", avatar: "/a.png" }
}

// userSessionStats
{
  _id: "U100",
  lastSeenAt: ISODate("2026-11-14T04:00:00Z"),
  requestCount: 100000
}
```

For metrics where eventual consistency is acceptable, writing to **time-bucket counters** can even outperform incrementing a single hot document continuously.

### 7.3. Splitting One-to-One Has Costs

The profile page needs an extra query if it displays `sessionStats`. If accounts are frequently read with both and rarely written, splitting can raise latency without solving any real bottleneck.

## 8. One-to-Few: Bounded Embedding

A product has at most 5 primary images:

```javascript
{
  _id: "P1001",
  images: [
    { url: "/img/a.jpg", position: 1 },
    { url: "/img/b.jpg", position: 2 }
  ]
}
```

If business rules truly cap the maximum number of images, embedding makes sense:

- Data is small.
- Read alongside the product.
- Updated alongside the product during catalog management.
- Single read, no `$lookup` needed.

**The crucial requirement is bounded growth.** If users can upload unlimited photos or videos, do not treat "currently only 5" as a permanent guarantee.

### 8.1. Do Not Store Large Image Files Directly Inside Each Document

Typically store metadata/URLs in the document; large blobs belong in object storage or a dedicated file-storage system. Do not force huge binary payloads into product BSON just because MongoDB supports BSON binary data.

## 9. Large One-to-Many: Referencing and Indexing on the Child Side

For reviews:

```javascript
{
  _id: "REV5001",
  productId: "P1001",
  rating: 5,
  comment: "Great headphones",
  createdAt: ISODate("2026-10-01T10:00:00Z"),
  authorId: "U200"
}
```

### 9.1. Querying Latest Reviews

```javascript
db.productReviews.createIndex({
  productId: 1,
  createdAt: -1,
  _id: -1
});

db.productReviews.find(
  { productId: "P1001" },
  { rating: 1, comment: 1, createdAt: 1, authorId: 1 }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

The index supports equality on `productId` and sorting by `createdAt`, `_id`.

### 9.2. Why Not Embed All 100,000 Reviews?

- Parent document grows without bound.
- Each review page needs 20 items, not the whole array.
- Individual reviews are edited or deleted independently.
- Indexing large arrays generates large multikey index entries.
- The parent becomes a hot write point whenever new reviews arrive.

### 9.3. Do Not Replace the Reviews Array with an Unbounded `reviewIds` Array

For example:

```javascript
{
  _id: "P1001",
  reviewIds: ["R1", "R2", /* ... 200000 IDs ... */]
}
```

An ID array still grows without bound and creates similar size/update problems. For large relationships, keeping the **foreign key in the child** scales far better.

## 10. Many-to-Many: True Relationships vs. Snapshot Data

Suppose users favorite many products, and each product is favorited by many users.

A one-document-per-relationship model:

```javascript
// favorites
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  userId: "U100",
  productId: "P1001",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 10.1. Unique Index Prevents Duplicates

```javascript
db.favorites.createIndex(
  { userId: 1, productId: 1 },
  { unique: true }
);
```

Querying a user's favorites list:

```javascript
db.favorites.find({ userId: "U100" })
  .sort({ productId: 1 })
  .limit(50);
```

If sorting by `createdAt` is needed, add an index tailored to that specific query shape.

### 10.2. Do Not Stuff a Users Array Inside the Product

A viral product with 2 million favorites would create an enormous `userIds` array. Separating relationship documents ensures adding/removing favorites never contends on the hot product document.

### 10.3. Counting Favorites

If the UI constantly displays `favoriteCount`, you can maintain an aggregate counter alongside relationship writes; however, define consistency and duplicate handling so retries do not drift the count.

## 11. Historical Data vs. Live Data: Do Not Mis-Update Snapshots

In an order, `nameSnapshot` and `unitPrice` should reflect **the price/name at purchase time**, not automatically mutate when the product catalog changes.

```javascript
{
  _id: "O1001",
  items: [
    {
      productId: "P1001",
      nameSnapshot: "Bluetooth Headphones",
      unitPriceSnapshot: 890000,
      quantity: 2
    }
  ]
}
```

### 11.1. Why Is Denormalization Intentional Here?

An old order must display the historical invoice, not today's catalog price. Duplicating name/price here is **a business requirement**, not inconsistent data needing synchronization.

### 11.2. Distinguishing Historical Copies from Live Copies

| Copy Type | Example | Should Update When Source Changes? |
|---|---|---|
| Historical snapshot | Price at time of purchase | **No**, unless governed document amendment workflow |
| Live denormalized field | Product name in search card | **Possibly yes**, per consistency contract |
| Cached summary | Rating average | **Yes**, per refresh policy |
| External immutable event | Stock movement | Typically append-only; do not mutate history arbitrarily |

Never claim "denormalization always makes data inconsistent"; the real task is **defining which copies may diverge and which must stay synchronized**.

## 12. Update Frequency: Why Even a Small Field Can Be a Big Problem

Suppose:

```text
Product description:
  20 KiB, updated once/month.

Inventory available:
  8 bytes, updated 5,000 times/minute.
```

The inventory field is tiny, yet its write rate is high. Impacts include:

- Heavy concurrent updates to the same document.
- Resources consumed by writes, journaling/oplog, and index maintenance.
- Potential document-level write conflicts under concurrency.
- Increased replication volume secondaries must apply.
- Throughput bottlenecks on hot keys.

### 12.1. Do Not Assume Every `$set` Rewrites the Entire Document

WiredTiger and MongoDB use update, storage, replication, and oplog encoding mechanisms that depend on version and workload.

**Do not state "changing one integer always rewrites the entire 1 MiB document" as an absolute rule.** The real issues are write workload, contention, index/working-set pressure, and document growth, which must be measured on the target deployment.

### 12.2. Splitting Hot Fields Is Only Worth It When Reducing Contention or Working Set

A 2 KiB product whose inventory updates once every 10 minutes may not need splitting. A product with large arrays whose inventory updates hundreds of times per second is a strong candidate for splitting.

### 12.3. Hot Fields Inside Compound Indexes

If `available` appears in many indexes, every inventory change may need to update the corresponding index entries.

Example:

```javascript
db.products.createIndex({ category: 1, available: 1 });
db.products.createIndex({ brand: 1, available: 1 });
db.products.createIndex({ available: -1, price: 1 });
```

If the application only queries inventory directly by `_id`, those three indexes can be unnecessary write baggage. **Choose indexes based on actual query patterns**, not "one index per field."

## 13. Example: Separating Inventory from Product Content

### 13.1. Before Optimization

```javascript
// products
{
  _id: "P1001",
  name: "Bluetooth Headphones",
  description: "...",
  price: 890000,
  variants: [ /* many variants */ ],
  inventory: {
    available: 127,
    reserved: 12
  }
}
```

### 13.2. After Optimization

```javascript
// products
{
  _id: "P1001",
  name: "Bluetooth Headphones",
  description: "...",
  price: 890000,
  category: "audio",
  thumbnail: "/img/p1001.jpg"
}

// productInventory
{
  _id: "P1001",
  available: 127,
  reserved: 12,
  version: NumberLong("42"),
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 13.3. Reading the Catalog

```javascript
db.products.find(
  { category: "audio" },
  {
    _id: 1,
    name: 1,
    price: 1,
    thumbnail: 1
  }
).limit(20);
```

The query does not need to touch inventory documents if the listing UI does not display live stock counts.

### 13.4. Reading the Detail Page

You can:

1. Fetch the product by ID.
2. Fetch inventory by the same ID.
3. Merge in the application.

Or use `$lookup` if a single pipeline is preferred.

### 13.5. Why Can't You Split Infinitely?

If the detail page always needs 50 subdocuments spread across 50 collections, the cost of multiple queries or aggregations can outweigh the benefits. Optimization must balance **read locality and update isolation**.

## 14. Atomic Reservation: Stock Preconditions Matter More Than Pretty Schemas

### 14.1. Unsynchronized Read-Then-Write Mistake

Do not write:

```javascript
const inv = db.productInventory.findOne({ _id: "P1001" });

if (inv.available > 0) {
  db.productInventory.updateOne(
    { _id: "P1001" },
    { $inc: { available: -1 } }
  );
}
```

Two concurrent requests can read the same `available` value and both believe stock remains.

### 14.2. Conditional Atomic Update

```javascript
const result = db.productInventory.updateOne(
  {
    _id: "P1001",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1,
      reserved: 1,
      version: 1
    },
    $currentDate: { updatedAt: true }
  }
);

if (result.modifiedCount === 1) {
  print("Reserved one item");
} else {
  print("No inventory available or item not found");
}
```

**Combining `available: {$gte:1}` with `$inc`** evaluates the check and mutation inside one atomic single-document update, avoiding the naive read-then-write race.

### 14.3. When One Order Reserves Multiple SKUs

If an order must reserve inventory across **multiple product documents** as a single business unit, single-document atomicity is insufficient. You may need a multi-document transaction checking every SKU, or an explicit reservation/saga workflow with clear states and compensation.

Never fire multiple independent `updateOne()` calls and claim the overall order reservation is atomic.

## 15. Optimistic Concurrency for Low-Write Updates

Suppose two admins edit a product description concurrently. You can use a `version` field:

```javascript
// Previous document:
// { _id:"P1001", description:"Old", version:7 }

const result = db.products.updateOne(
  {
    _id: "P1001",
    version: 7
  },
  {
    $set: {
      description: "New approved description"
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount === 0) {
  print("Conflict: reload document and resolve");
}
```

### 15.1. Why Is Version Needed?

If two admins both read version 7, only the first request succeeds and bumps to version 8. The second request matches nothing, preventing silent overwrites.

### 15.2. Success Checks Should Not Rely Only on modifiedCount

In operations setting the exact same value as before, `matchedCount` and `modifiedCount` can differ. For optimistic checks, evaluate results against the version filter and business state.

### 15.3. Version Fields Do Not Eliminate All Conflicts

You still need merge rules and application retry handling. For multi-document workflows, transactions or state machines may still be necessary.

## 16. Subset Pattern: Keep Frequently Read Data, Separate the Rest

A product has thousands of reviews, yet the detail page shows only **3 featured reviews**.

### 16.1. Hybrid Document

```javascript
// products
{
  _id: "P1001",
  name: "Bluetooth Headphones",
  ratingSummary: {
    count: 824,
    sum: 3884,
    average: 4.7136
  },
  featuredReviews: [
    {
      reviewId: "REV1",
      rating: 5,
      excerpt: "Great sound"
    },
    {
      reviewId: "REV2",
      rating: 4,
      excerpt: "Decent battery"
    }
  ]
}

// productReviews
{
  _id: "REV1",
  productId: "P1001",
  rating: 5,
  comment: "Great sound when listening to music..."
}
```

### 16.2. Benefits

- The detail page avoids a join to display ratings and a few reviews.
- All reviews remain stored and paginated separately.
- Product document size stays controlled.

### 16.3. Trade-Offs

- Editing a review may require updating the `featuredReviews` snapshot.
- Requires defining the featured policy: newest, most liked, editorial?
- If a review is removed for policy violations, the snapshot must be updated/purged within required deadlines.
- The UI must tolerate propagation delay if updated by an asynchronous worker.

### 16.4. Bounding the Subset Array

To always keep at most three reviews:

```javascript
db.products.updateOne(
  { _id: "P1001" },
  {
    $push: {
      featuredReviews: {
        $each: [{
          reviewId: "REV3",
          rating: 5,
          excerpt: "Very easy to use"
        }],
        $position: 0,
        $slice: 3
      }
    }
  }
);
```

This example only demonstrates a bounded array. "Featured by popularity" requires selection logic, duplicate prevention, and dedicated concurrency handling; `$push` alone does not enforce that policy.

## 17. Outlier Pattern: Do Not Let Edge Cases Dictate the Entire Schema

A product catalog:

```text
95% of products:   at most 30 reviews
4.9% of products:  30–2,000 reviews
0.1% of products:  over 100,000 reviews
```

If embedding a small preview of reviews helps for most products, you can apply the **Outlier Pattern**:

```javascript
// products
{
  _id: "P1001",
  reviewPreview: [ /* max 3 */ ],
  hasMoreReviews: true,
  reviewCount: 100234
}
```

All reviews reside in a separate collection; the rare outliers can use dedicated handling paths (partitioning, pagination, or caching).

### 17.1. Key Takeaway

The Outlier Pattern does not strictly mean "embed all for 99%, store outside for 1%." The key is **designing with explicit outlier handling** so a handful of massive documents do not degrade performance for the entire system.

### 17.2. Test the Outlier Read Path

If `hasMoreReviews=true`, the API must know where to fetch the rest. Never let the application read only the embedded array and silently return incomplete data for outliers.

### 17.3. When to Use a Uniform Schema?

If the size gap is not extreme or branching logic becomes too error-prone, **referencing all reviews uniformly** can be simpler and more reliable than an overly branched hybrid model.

## 18. Extended Reference Pattern: Copy Selected Fields to Avoid Frequent Joins

An `orderItems` collection contains many order lines. Reporting APIs often need `productName`, `category`, and `brand` alongside `productId`.

### 18.1. Keeping Only the Reference Key

```javascript
{
  orderId: "O1001",
  productId: "P1001",
  quantity: 2
}
```

Displaying name/category requires a join or separate query.

### 18.2. Extended Reference

```javascript
{
  orderId: "O1001",
  productId: "P1001",
  productSnapshot: {
    name: "Bluetooth Headphones",
    category: "audio"
  },
  quantity: 2
}
```

Benefit: reporting read paths already have frequently used fields, cutting lookup counts.

### 18.3. Define Clear Semantics

If `productSnapshot` is **historical at purchase time**: do not propagate later catalog changes.

If it is a **"live" copy for read optimization**: implement synchronization/cache invalidation and document acceptable staleness or consistency requirements.

Do not reuse the same field name `nameSnapshot` for both purposes and confuse readers.

## 19. Computed Pattern: Precompute Frequently Read Aggregates

Computing average rating:

```javascript
db.productReviews.aggregate([
  { $match: { productId: "P1001" } },
  {
    $group: {
      _id: "$productId",
      count: { $sum: 1 },
      sum: { $sum: "$rating" },
      average: { $avg: "$rating" }
    }
  }
]);
```

If a listing API runs this aggregation for every product on every page load, cost becomes prohibitive.

### 19.1. Keep Summary Updated on Writes

```javascript
{
  _id: "P1001",
  ratingSummary: {
    count: 824,
    sum: 3884
  }
}
```

Frontend calculates:

```text
average = sum / count
```

or the backend projects the normalized value.

### 19.2. Incremental Update Pattern

When adding a 5-star review, conceptually:

```javascript
db.products.updateOne(
  { _id: "P1001" },
  {
    $inc: {
      "ratingSummary.count": 1,
      "ratingSummary.sum": 5
    }
  }
);
```

### 19.3. Two-Document Consistency Issue

If inserting the review succeeds but updating the summary fails, the count becomes wrong.

Options:

- Multi-document transaction when strict consistency is required and workload permits.
- Outbox / event-driven worker with **idempotency keys**, retries, and reconciliation.
- Periodic recomputation of summaries from the source of truth.
- Documented eventual consistency exposed to the UI where acceptable.

### 19.4. Do Not Double-Count on Retries

`$inc` is atomic on one document but **not idempotent** if the same business operation is reprocessed.

```text
Event REV1005 processed twice
-> count +2 despite only 1 review
```

To stay accurate under retries, use unique review identities, processed-event deduplication, or appropriate transactions/protocols.

### 19.5. When Is the Computed Pattern Worth It?

When **summary reads far outnumber updates** and raw computation is expensive. If a summary updates 100,000 times/second while the UI is viewed once a day, per-write precomputation makes little sense; consider batch recomputation instead.

## 20. Bucket Pattern: Grouping Events into Bounded Batches

Sensor, click, or stock movement events can be massive in volume. One document per event offers independent updates and indexing, yet carries heavy overhead when reading contiguous time ranges.

### 20.1. Illustrative Bucket Document

```javascript
{
  _id: "sensor-1:2026-11-14T10",
  sensorId: "sensor-1",
  bucketStart: ISODate("2026-11-14T10:00:00Z"),
  count: 3,
  measurements: [
    { ts: ISODate("2026-11-14T10:00:01Z"), value: 25.0 },
    { ts: ISODate("2026-11-14T10:00:02Z"), value: 25.2 },
    { ts: ISODate("2026-11-14T10:00:03Z"), value: 25.4 }
  ]
}
```

### 20.2. Goals

- Reduce total document count compared to one document per event.
- Improve data locality for queries reading consecutive events.
- Consolidate repeated metadata at the bucket level.

### 20.3. Bounded Buckets Are Mandatory

Do not stuff 10 years of a sensor's measurements into a single bucket. Bound buckets by:

- Time window (hour/day).
- Entry count.
- BSON document size.
- Query and reporting patterns.

### 20.4. Hot Bucket Risk

Many writers appending to the same sensor bucket contend on one document. Larger buckets are not always better. Shard/hash buckets or shrink the time window if the write workload demands it.

### 20.5. MongoDB Time Series Collections

MongoDB provides **native time series collections** for timestamped measurements with internal bucketing; they carry specific rules for writes, updates, deletes, indexes, and server versions.

If your domain is time series, **evaluate native time series collections** before implementing a manual bucket pattern. Never assume custom buckets automatically beat MongoDB's built-in optimization.

## 21. Working Set: Does the "Hot" Data Fit in Memory?

### 21.1. What Is the Working Set?

The working set is the portion of data and indexes actively accessed over a given interval. If it exceeds effective memory/cache, queries must frequently read from disk.

Example:

```text
Hot catalog fields = 2 GiB
Hot indexes        = 1 GiB
Review full bodies = 80 GiB but rarely read
```

Keeping product summaries and hot indexes compact helps the working set fit in RAM far better than repeatedly fetching large documents stuffed with cold reviews.

### 21.2. How Does Projection Help?

```javascript
db.products.find(
  { category: "audio" },
  { name: 1, price: 1, thumbnail: 1 }
);
```

Projection limits returned fields and reduces **network payload**, yet does not automatically guarantee MongoDB reads only those field bytes from storage.

Specifically, if a query is not **covered by an index**, the storage engine still needs to FETCH the document. To verify disk/cache savings, inspect the query plan and real working-set metrics.

### 21.3. Document Splitting and Network

Splitting out reviews keeps catalog queries from touching review documents, isolating working sets. The detail page must fetch reviews separately when needed—an intentional trade-off aligned with access patterns.

### 21.4. Compression Does Not Remove Logical Document Limits

WiredTiger compression shrinks physical storage on disk, yet the **16 MiB BSON limit** and document access/update costs remain. Never use compression ratios to justify unbounded arrays.

## 22. Read Amplification and Write Amplification

### 22.1. Read Amplification

When a UI request asks for one product summary yet the database must:

- Read many documents.
- Scan many index entries.
- Join multiple collections.
- Sort large sets.
- Fetch unnecessary fields.

read amplification increases.

### 22.2. Write Amplification

When one small business change requires:

- Updating multiple denormalized copies.
- Modifying many index entries.
- Writing multiple events/snapshots.
- Running multi-document transactions.
- Emitting cascading writes to caches/summaries.

write amplification increases.

### 22.3. A Simple Mental Model

```text
Total work ≈
  readFrequency  * costPerRead
  +
  writeFrequency * costPerWrite
  +
  consistency/maintenance cost
```

This is **not an exact cost formula**. It helps prioritize measurements:

- If `readFrequency` vastly exceeds `writeFrequency`, denormalization/computed fields often pay off.
- If writes dominate, excessive copies or indexes create heavy pressure.
- If strict consistency is required, write coordination costs must be accounted for.

### 22.4. Do Not Optimize for Just One Endpoint

A schema that shaves 5 ms off `GET /products` while slowing `POST /orders` by 200 ms may be a net regression if orders are the critical path. Business SLOs and priorities matter more than isolated microbenchmarks.

## 23. Designing Indexes Alongside Query Shapes

### 23.1. Indexes Serving Read Paths

Example listing active products by category sorted by price:

```javascript
db.products.createIndex({
  category: 1,
  active: 1,
  price: 1,
  _id: 1
});

db.products.find(
  { category: "audio", active: true },
  { name: 1, price: 1, thumbnail: 1 }
).sort({
  price: 1,
  _id: 1
}).limit(20);
```

Do not claim this index is optimal for every dataset: evaluate selectivity, distributions, sort orders, optional filters, and index size.

### 23.2. Index for the Child Collection

```javascript
db.productReviews.createIndex({
  productId: 1,
  createdAt: -1,
  _id: -1
});
```

Without a `productId` index, querying reviews for one product may scan a huge review collection.

### 23.3. Indexes on Frequently Updated Fields

Updating an indexed field requires updating its index entries. If `available` changes constantly, do not put `available` into 10 indexes simply because it exists in the schema.

### 23.4. Targeted Partial Indexes and TTL

If most `archived=true` products never appear in search UI, consider a partial index for active products:

```javascript
db.products.createIndex(
  { category: 1, price: 1 },
  {
    partialFilterExpression: { active: true }
  }
);
```

Queries must include predicates matching the partial filter so the planner can safely select the index.

If child records have time-based retention, a TTL index may fit **when business rules permit automatic deletion**. TTL deletion is **asynchronous**, not exact to the millisecond; design retention explicitly.

### 23.5. Covered Queries

If all filter, sort, and projection fields can be satisfied from an index under covered query rules, document `FETCH`es are avoided. Still, wide indexes cost storage and write maintenance.

Do not chase "covered at all costs" by creating bloated compound indexes for every endpoint variation.

## 24. Verifying with `explain("executionStats")`

### 24.1. Listing Query

```javascript
db.products.find(
  { category: "audio", active: true },
  { _id: 1, name: 1, price: 1 }
).sort({
  price: 1,
  _id: 1
}).limit(20).explain("executionStats");
```

### 24.2. Signals

| Metric/Plan | Question |
|---|---|
| `nReturned` | How many result documents were returned? |
| `totalKeysExamined` | How many index entries were scanned? |
| `totalDocsExamined` | How many documents were inspected? |
| `IXSCAN` | Was an index scan used? |
| `COLLSCAN` | Was the entire collection scanned? |
| `FETCH` | Did MongoDB fetch documents after the index lookup? |
| `SORT` or sort stage | Was an in-memory sort needed outside the index? |
| `executionTimeMillis` | Estimated server execution time for this test run |

### 24.3. Quantitative Comparison

Example of two query plans both with `nReturned=20`:

```text
Plan A:
  keysExamined = 20
  docsExamined = 20

Plan B:
  keysExamined = 150000
  docsExamined = 100000
```

Plan B performs far more work for that query shape. However, that **alone cannot prove Schema B is always slower** if conditions, data, cache state, or index versions differ.

### 24.4. `explain()` Does Not Replace Application Benchmarks

`explain` can alter execution/plan-cache behavior and misses network effects, driver decoding, application merging, concurrency, and GC. Measure **end-to-end p95/p99 latency and throughput** under a representative workload.

## 25. Arrays and Multikey Indexes: Cost Goes Beyond Bytes

Array:

```javascript
{
  _id: "P1001",
  tags: ["audio", "bluetooth", "wireless"]
}
```

Index:

```javascript
db.products.createIndex({ tags: 1 });
```

MongoDB builds a **multikey index** when an indexed field holds an array, creating index keys per element. Longer arrays inflate index size and write maintenance.

### 25.1. Continuously Growing Arrays

Do not do:

```javascript
db.products.updateOne(
  { _id: "P1001" },
  { $push: { allReviewIds: newReviewId } }
);
```

unboundedly when a product can accumulate hundreds of thousands of reviews.

### 25.2. Compound Multikey Index Constraints

MongoDB restricts **compound multikey indexes** when documents contain multiple indexed array fields. Never assume you can freely create a compound index spanning two array fields in the same document.

When a schema uses large arrays, verify both **query patterns and index restrictions**, not just the 16 MiB limit.

### 25.3. Bounded Arrays Remain Useful

For `tags` capped at a couple dozen short strings, embedding can be completely sensible. Evaluate data size, update frequency, and query requirements.

## 26. Subset Pagination: Do Not Load the Entire Array and Slice in Java

If reviews live in a separate collection:

```javascript
db.productReviews.find(
  { productId: "P1001" },
  { rating: 1, comment: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .limit(20);
```

Do not:

```javascript
// Performance anti-pattern if loading a huge set of reviews.
const allReviews = db.productReviews.find({
  productId: "P1001"
}).toArray();

const page = allReviews.slice(0, 20);
```

### 26.1. Offset vs. Keyset

For deep pages, large `skip` values are expensive. Keyset pagination:

```javascript
const lastCreatedAt = ISODate("2026-10-01T10:00:00Z");
const lastId = "REV5001";

db.productReviews.find({
  productId: "P1001",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Page tokens/cursors must bind to the exact same filter and sort. Snapshot isolation across changing data is not automatically guaranteed if filters change or rows mutate.

### 26.2. Deterministic Ordering

Sorting solely by `createdAt` allows ties when multiple reviews share the same timestamp. Including `_id` breaks ties deterministically.

### 26.3. When Review Edits Affect Order

Choose sort keys matching business semantics: `createdAt` is normally immutable, whereas `updatedAt` shifts when edited and can cause items to jump across pages.

## 27. Projection, `$slice`, and Embedded Bounded Subsets

If a document contains a small array and the UI only needs a few elements:

```javascript
db.products.findOne(
  { _id: "P1001" },
  {
    name: 1,
    ratingSummary: 1,
    featuredReviews: { $slice: 3 }
  }
);
```

`$slice` in projection limits the returned array elements; it reduces network payload, yet **does not fix an underlying array that grows without bound**.

### 27.1. When to Use `$slice`?

- The array is bounded and only a small subset is needed.
- You want to minimize network transfer.
- You want to avoid querying another collection for just a few items.

### 27.2. When Is It Not Enough?

An array with hundreds of thousands of elements updated continuously, nearing 16 MiB and bloating indexes: adding `$slice: 3` does not fix the root cause.

## 28. Computed Values: Precompute for Heavy Reads, Batch for Heavy Writes

A `weeklySales` metric:

```javascript
{
  productId: "P1001",
  weekStart: ISODate("2026-11-09T00:00:00Z"),
  unitsSold: 583,
  revenue: NumberLong("519000000")
}
```

### 28.1. Real-Time Updates

Fits when:

- The UI needs near-real-time freshness.
- Write rate is manageable for aggregate updates.
- Idempotency prevents double counting.

### 28.2. Batch Recomputation

Fits when:

- Dashboards are viewed hourly or daily.
- Raw event volume is huge.
- Updating aggregates on every event is too costly.

### 28.3. Hybrid

```text
Baseline snapshot at 00:00
  + incremental events since 00:00
  = displayed near-real-time metric
```

This limits long-term recomputation while meeting freshness targets, though it adds complexity for handling duplicate and late events.

### 28.4. Aggregation Materialization

MongoDB `$merge`/`$out` can write aggregation outputs into a read-serving collection, but:

- `$out` and `$merge` have different write semantics.
- With `$merge`, documents no longer matching the source **do not disappear automatically**.
- Consistency, refresh schedules, and retries must be handled.

Do not swap summaries to batch materialization while ignoring stale rows.

## 29. Denormalization and the Consistency Problem

### 29.1. One Value Copied Across Many Documents

For example, brand name:

```text
brands:
  B1 -> "Nova Audio"

products:
  P1 -> brandName="Nova Audio"
  P2 -> brandName="Nova Audio"
  P3 -> brandName="Nova Audio"
```

When the brand name changes, updating one `brands` document does not automatically update the three `products` documents.

### 29.2. Synchronization Strategies

**Synchronous updates:** inside a transaction or controlled workflow. Reasonable when affected document counts are small and invariants are strict, though write latency and cost rise.

**Asynchronous events:** update the source of truth and emit an event; workers update copies under eventual consistency.

**Periodic reconciliation:** run a job comparing copies to source, useful for repairing drift after retries or infrastructure errors.

**Read-time join:** avoid copying the field and look it up from the source whenever fresh data is required.

### 29.3. Updating Millions of Denormalized Copies

If a field changes often and lives in 10 million documents, every edit causes massive fan-out writes. Avoid duplicating fields with:

- High change frequency.
- High fan-out.
- Strict synchronous consistency requirements.

Duplicated fields should ideally be **stable**, **small**, **heavily read**, or able to tolerate temporary staleness.

### 29.4. Versioning and Reconciliation

One approach:

```javascript
{
  productId: "P1001",
  brandNameCache: "Nova Audio",
  brandVersion: 13
}
```

When an event arrives, the worker compares versions so stale events do not overwrite newer ones. However, versions must be issued consistently by the source of truth; never rely on `Date.now()` across nodes assuming wall clocks are strictly ordered.

## 30. Update Frequency Changing Over the Lifecycle

A document can pass through phases:

```text
Order created     -> frequent state transitions
Order completed   -> rare changes
Order archived    -> read-only audit/analytics
```

### 30.1. Active vs. Historical Collections

In some systems, you can separate:

```text
activeOrders:
  in-flight orders, frequent queries/writes

completedOrders:
  finalized orders, rarely updated, different retention
```

### 30.2. Trade-Offs

Pros: smaller active working set, workload-specific indexes.

Cons:

- Queries spanning both collections are more complex.
- Moving documents between collections is not automatically atomic.
- Identity, audit trails, and references must be preserved.
- Archival job retries must avoid duplicates or missing records.

Do not archive an order merely because of its age; base the split on lifecycle and access requirements.

### 30.3. TTL Does Not Mean Archive

TTL **deletes** expired documents asynchronously. If audit records must be retained, do not attach a TTL index and call it "archiving."

## 31. Attribute Pattern and Polymorphic Fields

A catalog with diverse product types:

```javascript
// Headphones
{ driverSizeMm: 40, batteryHours: 25 }

// Keyboard
{ layout: "US", switchType: "mechanical" }

// Monitor
{ resolution: "4K", refreshHz: 144 }
```

### 31.1. Dynamic Fields

MongoDB allows each product to store different fields. However, filtering and sorting across hundreds of dynamic attributes makes managing individual indexes cumbersome.

### 31.2. Attribute Pattern

```javascript
{
  _id: "P1001",
  category: "audio",
  attributes: [
    { key: "batteryHours", valueNum: 25 },
    { key: "driverSizeMm", valueNum: 40 },
    { key: "color", valueStr: "black" }
  ]
}
```

Helpful when the UI filters on flexible attributes, yet:

- The `attributes` array introduces multikey indexing costs.
- Key/value filters require proper `$elemMatch` usage.
- Numbers and strings have distinct comparison semantics.
- Do not turn every stable core field into key/value pairs merely for flexibility.

### 31.3. Querying Array Elements Properly

```javascript
db.products.find({
  attributes: {
    $elemMatch: {
      key: "batteryHours",
      valueNum: { $gte: 20 }
    }
  }
});
```

`$elemMatch` ensures both `key` and `valueNum` match **the same array element**. Using separate uncoordinated dot-path predicates can match two different elements in the array.

## 32. Polymorphic Pattern: Multiple Document Shapes in One Collection

An `activities` collection containing:

```javascript
{
  _id: "ACT1",
  kind: "PURCHASE",
  userId: "U1",
  amount: 890000
}

{
  _id: "ACT2",
  kind: "REVIEW",
  userId: "U1",
  productId: "P1001",
  rating: 5
}
```

Pros: a unified activity feed can query cleanly by user and time.

Cons:

- Subtypes require different queries and indexes.
- Schema validation becomes more complex.
- One high-volume subtype can dominate the collection and indexes.
- TTL/retention policies may differ.

### 32.1. When to Split Collections?

If purchases and reviews have radically different lifecycles, retention, security rules, hot indexes, and throughput, splitting collections may be better. Neither "one collection for everything" nor "one collection per subtype" is mandatory for every workload.

## 33. Time Series vs. Standard Collections

MongoDB provides **time series collections** tailored for timestamped measurements and metadata (e.g., `deviceId`). They use time-based internal storage and carry different capabilities and index constraints from standard collections.

### 33.1. Example: Creating a Time Series Collection

```javascript
db.createCollection("deviceReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "device",
    granularity: "minutes"
  }
});
```

Example document:

```javascript
{
  measuredAt: ISODate("2026-11-14T04:00:00Z"),
  device: { id: "SENSOR1", site: "HN-A" },
  temperature: 24.5
}
```

### 33.2. Must Match Update Patterns

If business logic frequently updates old measurements by ID, a time series collection has different update/delete constraints than a standard collection. Do not choose time series just because a document "has a timestamp"; verify version features and real query/update patterns.

### 33.3. Time-Range Query Fit

A workload like:

```text
Find the last 6 hours of sensor S1
Compute average per 5 minutes
Delete data after 90 days
```

is a great fit to evaluate native time series + retention. A workload requiring mutable stateful business events likely belongs in a standard collection.

## 34. Hotspot: One Document Updated Concurrently by Many Writers

Example global counter:

```javascript
{
  _id: "GLOBAL",
  totalPageViews: NumberLong("900000000")
}
```

Every page view executes:

```javascript
db.counters.updateOne(
  { _id: "GLOBAL" },
  { $inc: { totalPageViews: 1 } }
);
```

`$inc` is atomic, yet all requests hitting a single document create a hot key and contention.

### 34.1. Sharded/Striped Counters

An approach if business rules allow:

```javascript
// counters
{ _id: "views:00", count: NumberLong("1000") }
{ _id: "views:01", count: NumberLong("1001") }
{ _id: "views:02", count: NumberLong("999") }
```

Each write picks a counter stripe; reads sum the stripes for the total.

### 34.2. Trade-Offs

- Write contention drops as writes spread out.
- Reads must aggregate multiple documents.
- Complexity increases if an exact transactional total is required on every immediate read.
- With random stripe selection, ensure retries do not double-count.
- In sharded MongoDB deployments, examine **shard key distribution** and balancing; sharding alone will not fix hot documents sharing the same shard key.

### 34.3. Do Not Micro-Optimize Prematurely

If a counter increments 10 times/minute, a single-document `$inc` is clean and sufficient. Stripe only when throughput or latency evidence proves contention.

## 35. Sharding and Document Modeling

### 35.1. Align Shard Key with Access Patterns

An orders collection queried primarily by `tenantId` and `orderId`:

```javascript
{ tenantId: "T01", orderId: "O1001" }
```

Choosing a shard key requires evaluating:

- Query routing: do queries include the shard key?
- Cardinality, skew, and monotonically increasing patterns.
- Write distribution.
- Hot tenants and jumbo chunks.
- Unique indexes and constraints.
- Resharding cost.

### 35.2. Design Schema and Shard Key Together

If `tenantId` sits only on the parent document while child reviews omit `tenantId` and queries filter by tenant, consider storing `tenantId` on child documents to aid routing and authorization.

Example:

```javascript
{
  _id: "REV5001",
  tenantId: "T01",
  productId: "P1001",
  rating: 5
}
```

Note that this is **denormalizing tenant identity**; ensure it is set from an authenticated/authoritative server context rather than trusting client-supplied values.

### 35.3. Do Not Assume `$lookup` Always Stays Local to One Shard

In sharded clusters, `$lookup` capabilities and costs depend on topology, shard keys, indexes, and MongoDB version. Benchmark in reality rather than assuming joins are free.

### 35.4. One Document Cannot Be "Split Across Shards" Automatically

Sharding distributes **documents**, not halves of a 20 MiB document to bypass the BSON limit. If documents grow oversized due to unbounded arrays, redesign the schema—do not just add shards.

## 36. Data Models and Application-Layer Caching

A product summary read tens of thousands of times per minute and rarely modified can be cached in the application, CDN, or Redis depending on architecture.

### 36.1. A Cache Is a Denormalized Copy

```text
MongoDB products (source of truth)
             |
             v
         API cache
             |
             v
           Client
```

Cache hits cut database reads, yet introduce:

- TTL and staleness.
- Invalidation when products change.
- Cache stampedes.
- Authorization and tenant isolation concerns.
- Risk of stale prices or inventory.

### 36.2. Do Not Rely on Cached Inventory for Transaction Decisions

Listing pages can display approximate "in stock" badges, but order reservation must check **authoritative inventory** at write time. Never decrement `available` in a client cache and assume stock is secured.

### 36.3. Data Model and Cache Must Share a Consistency Policy

When product price changes, track all layers:

- MongoDB authoritative value.
- Denormalized search card.
- API/cache layer.
- CDN/edge snapshot.

Lag in any layer can show wrong prices in the UI. Schema design cannot be separated from replica/cache lifecycles.

## 37. Complete Catalog Model Design

### 37.1. Product Document

```javascript
{
  _id: "P1001",
  tenantId: "T01",
  sku: "SKU-1001",
  name: "Bluetooth Headphones",
  category: "audio",
  brandId: "B1",
  price: 890000,
  currency: "VND",
  thumbnail: "/images/p1001.jpg",
  description: "Detailed description",
  featuredReviews: [
    { reviewId: "R1", rating: 5, excerpt: "Very good" }
  ],
  ratingSummary: {
    count: 824,
    sum: 3884,
    computedAt: ISODate("2026-11-14T04:00:00Z")
  },
  contentVersion: NumberLong("17"),
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 37.2. Inventory Document

```javascript
{
  _id: "P1001",
  tenantId: "T01",
  available: 127,
  reserved: 12,
  version: NumberLong("42"),
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 37.3. Review Documents

```javascript
{
  _id: "R1",
  tenantId: "T01",
  productId: "P1001",
  userId: "U20",
  rating: 5,
  comment: "Very good when listening to music",
  createdAt: ISODate("2026-11-01T09:00:00Z")
}
```

### 37.4. Stock Movement Documents

```javascript
{
  _id: "M100001",
  tenantId: "T01",
  productId: "P1001",
  operationId: "OP90001",
  delta: -1,
  reason: "ORDER_RESERVATION",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

This is an **event/history log**, not a replacement for atomic checks when reserving inventory.

### 37.5. Proposed Query-Aligned Indexes

```javascript
db.products.createIndex(
  { tenantId: 1, category: 1, price: 1, _id: 1 }
);

db.productReviews.createIndex(
  { tenantId: 1, productId: 1, createdAt: -1, _id: -1 }
);

db.stockMovements.createIndex(
  { tenantId: 1, productId: 1, createdAt: -1 }
);

db.stockMovements.createIndex(
  { tenantId: 1, operationId: 1 },
  { unique: true }
);
```

These indexes are **suggestions for the queries described**, not a blanket configuration to copy into every project. Review selectivity, existing indexes, sharding, unique constraints, and write overhead.

### 37.6. Querying the Detail Page

```javascript
const tenantId = "T01";
const productId = "P1001";

const product = db.products.findOne(
  { _id: productId, tenantId },
  {
    name: 1,
    price: 1,
    description: 1,
    featuredReviews: 1,
    ratingSummary: 1
  }
);

const inventory = db.productInventory.findOne(
  { _id: productId, tenantId },
  { available: 1, reserved: 1 }
);

printjson({ product, inventory });
```

In real applications, `tenantId` must come from an authenticated context, not an arbitrary client-supplied literal.

### 37.7. Do Not Expect Two Separate Reads to Share a Snapshot

Two separate `findOne` calls can observe `product` and `inventory` at slightly different points in time. If business logic demands a consistent cross-document snapshot, use a transaction/session/read concern as required.

For catalog UI display, eventual consistency is often fine; for inventory reservation decisions, enforce atomic business checks on the write path.

## 38. `$lookup` When In-Database Composition Is Needed

```javascript
db.products.aggregate([
  {
    $match: {
      _id: "P1001",
      tenantId: "T01"
    }
  },
  {
    $lookup: {
      from: "productInventory",
      localField: "_id",
      foreignField: "_id",
      as: "inventory"
    }
  },
  {
    $set: {
      inventory: { $first: "$inventory" }
    }
  },
  {
    $project: {
      name: 1,
      price: 1,
      inventory: 1
    }
  }
]);
```

### 38.1. Security and Tenant Isolation

This `$lookup` joins on `_id`, which is unique in the target collection; if IDs are not globally unique or a multi-tenant schema uses composite keys, join on **both `tenantId` and the key** to prevent cross-tenant data leaks. Never assume an outer `$match tenantId` automatically protects arbitrary joins.

### 38.2. Performance

`$lookup` is not "always slow," but its cost depends on:

- Number of left-side documents.
- Indexes on the foreign field.
- Result cardinality.
- Pipeline filters and shard topology.
- Memory and working set.

Measure aggregation `explain` and end-to-end latency. For a screen showing 20 products, a batched `$in` query for inventory by IDs can replace 20 independent round trips.

## 39. Batch Reads to Avoid N+1 Queries

An anti-pattern:

```javascript
const products = db.products.find({ category: "audio" })
  .limit(20).toArray();

for (const product of products) {
  const inventory = db.productInventory.findOne({
    _id: product._id
  });
  // 20 separate round trips if executed sequentially.
}
```

Replace with a batched query:

```javascript
const productIds = products.map(p => p._id);

const inventories = db.productInventory.find({
  _id: { $in: productIds }
}).toArray();

const inventoryByProductId = new Map(
  inventories.map(inv => [inv._id, inv])
);

const cards = products.map(p => ({
  product: p,
  inventory: inventoryByProductId.get(p._id) ?? null
}));

printjson(cards);
```

### 39.1. Enforce Tenant Protection

In a multi-tenant application, batched queries must also filter by `tenantId` from the authenticated context and validate IDs; never let client-supplied `$in` IDs bypass authorization.

### 39.2. Very Large ID Lists

`$in` with tens of thousands of values can become expensive; benchmark batch pagination, server-side joins, or alternative patterns.

## 40. Java Sync Driver: Safe Hot Inventory Updates

Java example using the MongoDB Sync Driver; URI is loaded from environment/secret store. The snippet assumes the collection exists and products have been seeded.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.currentDate;

public class InventoryReservation364 {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> inventory = client
                .getDatabase("catalog_lab_364")
                .getCollection("productInventory");

            String productId = "P1001";
            String tenantId = "T01";
            long qty = 1;

            Bson filter = and(
                eq("_id", productId),
                eq("tenantId", tenantId),
                gte("available", qty)
            );

            Bson update = combine(
                inc("available", -qty),
                inc("reserved", qty),
                inc("version", 1L),
                currentDate("updatedAt")
            );

            UpdateResult result = inventory.updateOne(filter, update);

            if (result.getModifiedCount() == 1L) {
                System.out.println("Reserved successfully");
            } else {
                System.out.println("Not enough inventory or not found");
            }
        }
    }
}
```

### 40.1. Validate Domain Logic When `qty` Is Invalid

Production code must validate `qty > 0`, upper bounds, tenant/product authorization, and order idempotency/retry rules. If `qty` were negative, this example logic would erroneously add stock.

### 40.2. Business Retries Differ from Driver Retryable Writes

Even when the driver supports retryable writes for transient network failures, a retried business checkout request can still create a **duplicate reservation** if the API lacks an idempotency key.

To prevent double reservations, use unique request/operation IDs with a state machine, transaction, or idempotent protocol—not just repeated `updateOne()` calls.

### 40.3. Isolating Inventory Helps Writes

The inventory document is tiny and holds only required counters; updates avoid touching product descriptions or reviews. Still, reading product + inventory requires composition, and this split schema **does not automatically provide multi-document snapshots**.

## 41. Java: Batch Fetching Two Collections

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;

// Assumes two MongoCollection<Document> instances: products and inventory.
// IDs and tenantId come from a valid query/authorization context.
String tenantId = "T01";

List<Document> productPage = products
    .find(Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.eq("category", "audio")
    ))
    .limit(20)
    .into(new ArrayList<>());

List<String> ids = new ArrayList<>();
for (Document p : productPage) {
    ids.add(p.getString("_id"));
}

List<Document> inventoryRows = ids.isEmpty()
    ? new ArrayList<>()
    : inventory.find(Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.in("_id", ids)
    )).into(new ArrayList<>());

Map<String, Document> byId = new HashMap<>();
for (Document inv : inventoryRows) {
    byId.put(inv.getString("_id"), inv);
}

for (Document p : productPage) {
    Document inv = byId.get(p.getString("_id"));
    System.out.println(
        p.getString("name") + ": " +
        (inv == null ? "unknown" : inv.get("available"))
    );
}
```

This snippet illustrates batch composition using pre-initialized collection variables. Real endpoints need sorting/pagination, projections, timeouts, exception handling, and consistency checks.

## 42. Migration: From One Monolithic Document to a Hybrid Model

Suppose the old schema is:

```javascript
{
  _id: "P1001",
  name: "...",
  inventory: { available: 100 },
  reviews: [ /* all reviews */ ]
}
```

New schema:

```text
products
productInventory
productReviews
```

### 42.1. Do Not Migrate by Dropping and Recreating Production Immediately

Do not do:

```javascript
db.products.drop();
// Recreate from an unverified script.
```

This is dangerous and usually unnecessary for online schema migrations.

### 42.2. Expand–Migrate–Contract Plan

**Phase 1 — Expand:** create new collections and indexes; update application readers to support both old and new schemas.

**Phase 2 — Backfill:** extract inventory and reviews from existing documents into the new collections using idempotent upserts and deterministic IDs.

**Phase 3 — Dual-write or change capture:** during transition, ensure new updates apply to both old source and new targets via a defined protocol.

**Phase 4 — Verify:** compare counts, samples, invariants, retry gaps, and business reads.

**Phase 5 — Switch reads:** shift traffic gradually to the new schema while monitoring latency, errors, and reconciliation drift.

**Phase 6 — Contract:** once stability criteria are met and a rollback path exists, remove legacy fields/copies through an approved process.

### 42.3. Dual-Write Is Not Automatically Atomic

Two commands:

```javascript
db.products.updateOne(...);
db.productInventory.updateOne(...);
```

can succeed or fail independently. If atomicity is needed, use a transaction or transition via an outbox/event protocol with idempotency and reconciliation.

### 42.4. Backfill with Deterministic IDs

For instance, review IDs should come from existing source identities or a deterministic mapping so re-running backfill never creates duplicate copies.

If legacy data stored reviews in an array without IDs, define a one-time ID assignment strategy, record mappings, and handle concurrent modifications during backfill.

### 42.5. Do Not Forget Deletes

During migrations, it is easy to backfill creates and updates while missing deletes, leaving deleted reviews in the new collection. Define delete propagation and retention across both models.

## 43. Schema Versioning and Compatibility

Some systems store:

```javascript
{
  _id: "P1001",
  schemaVersion: 2,
  name: "Bluetooth Headphones",
  inventoryRef: "P1001"
}
```

### 43.1. Purpose

- Distinguish documents already backfilled.
- Support dual-schema readers during rolling deployments.
- Simplify migration progress tracking.

### 43.2. Do Not Bump Version Before Data Is Ready

If you mark `schemaVersion: 2` before inventory has been migrated successfully, new readers will miss data. The version marker must reflect **verified migration state**, or else use granular migration status fields.

### 43.3. Schema Validation

MongoDB provides `$jsonSchema` to enforce document shapes:

```javascript
db.createCollection("productInventory", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "available", "reserved"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        available: {
          bsonType: ["int", "long"],
          minimum: 0
        },
        reserved: {
          bsonType: ["int", "long"],
          minimum: 0
        }
      }
    }
  }
});
```

Validation prevents type/range corruption but does not replace transactions, optimistic concurrency, or authorization.

## 44. Preparing Before/After Benchmarks

### 44.1. Do Not Benchmark on 10 Products

A tiny dataset fails to reflect:

- Working sets larger than RAM/cache.
- Hot products with 100,000 reviews.
- Peak read/write distributions.
- Disk/cache pressure.
- Multi-tenant skew.
- Replication lag during write bursts.

### 44.2. Benchmarks Need Representative Workloads

Example:

```text
60% GET product list
15% GET product detail
10% GET reviews page
10% inventory updates
 5% create/update reviews
```

This is an illustrative mix. Derive real ratios from production and test steady-state, peak, and burst scenarios.

### 44.3. Before/After Metrics

| Metric | Before | After | Goal |
|---|---:|---:|---|
| p95 catalog query | measure | measure | Lower / within SLO |
| p95 product detail | measure | measure | No excessive regression |
| p95 inventory write | measure | measure | Lower |
| Write throughput | measure | measure | Higher |
| CPU / disk IOPS | measure | measure | No saturation |
| WiredTiger cache pressure | measure | measure | Lower or stable |
| MongoDB read/write ops | measure | measure | Within capacity |
| Avg/p99 document BSON size | measure | measure | Bounded |
| Index size/growth | measure | measure | Controlled |
| Replication lag | measure | measure | Within SLO |
| Consistency drift | measure | measure | Within bounds |

### 44.4. Define Success by Business SLOs

If an optimization improves inventory write p95 while increasing stale product prices, that can be a **business regression**. Benchmarks must cover latency, correctness, and consistency.

### 44.5. Rollback

A failed migration needs a path back even after new writes have landed on the new schema. A pre-migration backup is insufficient once new orders have been accepted.

Design back-sync, event replay, or compatibility layers as needed.

## 45. Diagnosing Performance by Symptom

| Symptom | Hypothesis | Checks |
|---|---|---|
| Product detail slow | Oversized document or heavy join | Document size, projection, `explain` |
| High inventory update p99 | Hot key, write contention, indexes | Per-ID write rate, conflicts, profiler |
| High disk reads | Working set exceeds cache | Cache eviction, IOPS, pages read |
| Review page slow | Missing compound index, deep skip | `explain`, scan counts |
| Product document keeps growing | Unbounded array | BSON size distribution |
| Wrong rating summary | Double counting, missed events | Reconciliation, idempotency |
| Writes cause replication lag | Write/index/oplog amplification | Oplog GB/hour, lag, disk |
| CPU rises after adding index | Index maintenance and plan changes | Index stats / write metrics |
| Large multi-tenant customer slow | Skew / hot tenant | Per-tenant cardinality/throughput |
| Migration causes missing reads | Unsynced backfill/deletes/version | Compare old/new source data |

**Do not infer root cause from symptoms alone.** Inspect query plans, application traces, metrics, and historical data before altering schemas.

## 46. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Embedding unbounded arrays | Hits 16 MiB, costly updates/indexes | Child collection with pagination |
| Splitting every field into separate collections | Too many round trips, complexity | Embed bounded co-read data |
| Embedding hot inventory in large products | Hot document / working-set pressure | Evaluate splitting hot data |
| Storing 200,000 review IDs in product | Parent still grows unboundedly | Foreign key on reviews |
| Caching product price with no invalidation | Displays stale prices | Version/event/cache policy |
| Recomputing rating from all reviews per read | Expensive aggregation | Computed summary |
| Incrementing summary blindly on retry | Double counting | Idempotency + reconciliation |
| Copying live fields into millions of docs | Fan-out writes | Reference or controlled denormalization |
| Storing only product ID in orders without snapshot price | Invoices change with catalog | Embed immutable snapshot |
| Avoiding all references because "MongoDB has no joins" | Hard-to-manage schemas | Indexed `$lookup`, benchmarked |
| Many indexes on frequently updated fields | Write amplification | Index strictly for real queries |
| Assuming projection guarantees fewer disk reads | May still FETCH full document | Check `explain` and metrics |
| Loading all reviews with `toArray()` | Huge bandwidth/memory usage | Server-side pagination |
| Using very deep `skip` | Scans and discards many entries | Keyset pagination |
| Splitting data across docs while expecting free atomicity | Inconsistent writes | Transactions / coordination |
| Treating `$inc` as naturally idempotent | Retries double-increment | Unique operation IDs |
| Putting TTL on audit data | Unintended data deletion | Proper retention/lifecycle design |
| Minimizing doc size while ignoring update frequency | Hot key still slow | Measure workload and contention |
| Optimizing only average, ignoring p99 outliers | Tail latency / size risks | Distribution analysis |
| Sharding to bypass 16 MiB document limit | Does not work | Split logical document |
| Building custom time-series buckets without checking native feature | Unnecessary complexity | Evaluate time series collections |
| Migrating live via drop/recreate | Data loss / downtime risk | Expand–migrate–contract |
| Skipping delete propagation in backfill | Stale deleted data persists | Delete propagation |
| Measuring only `explain` on one query | Misses application behavior | Full-workload load testing |
| Speeding up reads while severely hurting writes | System-wide regression | Weighted SLO/throughput review |

## 47. Practice Exercises

### Exercise 1 — Building an Access-Pattern Matrix

For a bookstore system with `books`, `authors`, `inventory`, `reviews`, and `orders`, describe at least eight read/write operations with frequencies, required fields, target latencies, and consistency requirements.

### Exercise 2 — Embed or Reference?

A user has up to 3 shipping addresses that are usually read with their profile. Propose a schema and state what conditions would push you to move them into a separate `userAddresses` collection.

### Exercise 3 — High-Growth Reviews

Products average 8 reviews but peak at 250,000. Compare full embedding, full referencing, and hybrid featured subsets. Evaluate the 16 MiB limit and update patterns.

### Exercise 4 — Hot Fields vs. Cold Fields

Product description updates once/month, inventory updates 20,000 times/hour, and ratings update 200 times/hour. Propose boundaries and list the measurements needed before splitting.

### Exercise 5 — Atomic Reservation

Write an `updateOne()` that decrements `available` only when enough stock exists while incrementing `reserved`. Why is read-then-update prone to races?

### Exercise 6 — Many-to-Many

Design a `favorites` collection for many users and products with a unique index preventing duplicates and an ordered per-user list query.

### Exercise 7 — Historical Snapshots

An order is placed when a product costs 890,000; next month the price rises to 990,000. Which price should the order display? Contrast historical snapshots with live denormalized caches.

### Exercise 8 — Extended Reference

Order lists need product name/brand, and product metadata rarely changes. Design the read model and synchronization plan for when a brand is renamed.

### Exercise 9 — Computed Pattern

Compute rating `count`/`sum`/`average` from reviews. Compare recomputing on read, updating summaries per event, and batch recomputation. Explain duplicate/retry handling.

### Exercise 10 — Outlier Pattern

A few users have 100,000 activities while most have under 20. Design a schema preventing outliers from creating huge arrays, and explain how the API handles edge cases.

### Exercise 11 — Bucket Pattern

Sensors emit 5 events/second. Propose minute/hour buckets with bounded entry counts. If one sensor has 100 concurrent writers, what risks arise?

### Exercise 12 — Time Series

Compare native time series collections against manual buckets for time-range sensor queries, 90-day retention, and late writes.

### Exercise 13 — Indexes and Updates

You have 5 indexes containing `available`, while inventory queries primarily filter by `_id`. Assess the costs and propose how to cut write amplification without breaking required queries.

### Exercise 14 — `explain`

Query A returns 20 docs after examining 25 keys / 20 docs. Query B returns 20 docs after examining 100,000 keys / 70,000 docs. List the signals to investigate and why this alone does not decide system-wide performance.

### Exercise 15 — Projection

A document is 1 MiB, and a query projects only `name` and `price`. Why does projection not guarantee reading only a few bytes from storage? When do covered queries help?

### Exercise 16 — Keyset Pagination

Write the next-page query for reviews sorted by `createdAt desc, _id desc`. Explain the tie-breaker and what happens if data changes between pages.

### Exercise 17 — Schema Polymorphism

One collection stores purchase and review events. State when to keep them together vs. split them based on indexes, retention, permissions, and write volume.

### Exercise 18 — Shard Key

A multi-tenant app queries orders primarily by `tenantId`, and one tenant generates 50% of writes. What skew/hotspot risks must be evaluated when selecting a shard key?

### Exercise 19 — Hot Counter

A global counter updates 10,000 times/second. Compare single-document `$inc`, striped counters, and batch aggregation. Explain the trade-off between write throughput and exact reads.

### Exercise 20 — Cache Consistency

Catalog data is cached in the API and CDN while inventory is authoritative in MongoDB. Design flows for price changes and order placement so transactions never rely on stale cache data.

### Exercise 21 — Migration

The legacy schema embeds all reviews inside `products`. Draft an expand–migrate–contract plan covering backfill, dual-write, version markers, delete propagation, monitoring, and rollback.

### Exercise 22 — Java Sync Driver

Write Java code using `Filters.and`, `gte`, and `Updates.combine` to reserve inventory atomically. Add `qty` validation and request idempotency handling.

### Exercise 23 — Benchmark

Design a load test with 60% reads, 30% writes, and 10% reports; report p95/p99, throughput, disk, cache, document size distributions, and replication lag.

### Exercise 24 — Consistency

Review insertion succeeds while the rating summary update fails. Propose two solutions: transactions vs. eventual consistency + reconciliation. Compare pros/cons and retry rules.

### Exercise 25 — Capstone Design

Design a marketplace schema covering products, inventory, carts, reviews, orders, and change history. Present the access-pattern matrix, boundaries, embeddings, references, indexes, write paths, consistency policy, and benchmark plan.

## 48. Access-Pattern-Driven Decision Process

### Step 1 — List Concrete Queries

Do not start with an ERD and mechanically map every table to a collection. List:

```text
Endpoint /products
Endpoint /products/{id}
Endpoint /products/{id}/reviews
POST /orders
PATCH /inventory/reserve
GET /reports/sales
```

Specify fields, filters, sorts, limits, frequencies, latency targets, and consistency needs.

### Step 2 — Classify Fields

```text
Hot read + cold update:   product name, price, thumbnail
Hot write:                inventory counters
Large & growing:          reviews, stock movements
Historical snapshot:      order line price/name
Computed/derived:         rating summary, sales report
```

### Step 3 — Define Ownership and Consistency

Identify sources of truth, which copies tolerate lag, which workflows require transactions, which events need idempotency, and which historical records are immutable.

### Step 4 — Choose Embed / Reference / Hybrid

Embed bounded co-read/co-updated data; reference large, fast-growing, or independent-lifecycle data; use hybrid patterns for subsets and computed summaries serving hot reads.

### Step 5 — Design Query-Aligned Indexes

Build compound indexes matching equality/sort/range query shapes while balancing selectivity against index maintenance cost on writes.

### Step 6 — Define Growth Bounds

Cap array element counts, target document sizes, outlier handling, and storage/retention. Never wait for a 16 MiB error before redesigning arrays.

### Step 7 — Measure Empirically

Run `explain` and load tests on production-like data, measuring read/write latency, throughput, document sizes, cache, indexes, oplog, and replication.

### Step 8 — Migration and Rollback

Follow expand–backfill–dual-write/CDC–verify–switch–contract, retaining reconciliation and rollback paths even after new writes hit the new schema.

### Step 9 — Post-Deployment Monitoring

Set alerts for document growth, p99 latency, write conflicts, disk/cache pressure, and data drift between sources and copies.

### Step 10 — Adapt to Evolving Workloads

Access patterns shift as features launch, tenants grow, new reports appear, or write volume rises. Schema design is **an evolvable engineering decision**, not an immutable truth.

## 49. Summary

**MongoDB document model optimization must start from the workload.** Which fields are read together, which update together, how many elements can accumulate, and how strict consistency must be all matter far more than translating a relational diagram verbatim into JSON.

**Embedding** excels when data is small, bounded, and accessed as one unit. **Referencing** fits high-cardinality relationships, unbounded growth, independent updates, or distinct lifecycles. **Hybrid patterns**—Subset, Outlier, Extended Reference, Computed, and Bucket—balance fast reads against write and maintenance costs.

**Update frequency drives hidden trade-offs.** A tiny inventory field written thousands of times per minute can create a hot document; denormalized copies or indexes on volatile fields amplify writes. Large arrays bloat indexes, cache, and document sizes even when the UI displays only a few items. Conversely, over-splitting introduces N+1 queries, extra joins, and coordination overhead.

**Never optimize on intuition alone.** Use `explain("executionStats")` to inspect query shapes; use metrics and representative benchmarks to measure p95/p99, throughput, working set, index maintenance, and replication lag. Define sources of truth, idempotency, consistency, and migration/rollback plans before changing production schemas.

A good document model is not the one with the fewest collections or the least duplication. It is the model that **serves critical access paths with predictable cost, safe updates, and sustainable growth**.

## 50. References

- [MongoDB — Data Modeling Introduction](https://www.mongodb.com/docs/manual/data-modeling/): thinking about data design around how applications access it.
- [MongoDB — Data Modeling Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/): patterns including embedding, referencing, subset, bucket, computed, and extended reference.
- [MongoDB — Embedding vs References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/): weighing relationships and data lifecycles.
- [MongoDB — Schema Design Process](https://www.mongodb.com/docs/manual/data-modeling/schema-design-process/): designing around workload, constraints, and growth.
- [MongoDB — BSON Document Size Limit](https://www.mongodb.com/docs/manual/reference/limits/): the 16 MiB limit and related constraints.
- [MongoDB — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document atomic updates and multi-document transactions.
- [MongoDB — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): indexing arrays and related constraints.
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): query execution statistics.
- [MongoDB — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/): native time series collections and limitations.
- [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): observing changes to synchronize appropriate copies.
- [MongoDB — $lookup Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): joining collections and costs to measure.
- [MongoDB — $merge Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/): materializing computed data and update semantics.
