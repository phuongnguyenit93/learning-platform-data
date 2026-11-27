# Unbounded Arrays, Oversized Documents, and Hot Documents

MongoDB allows embedding objects and arrays inside **BSON documents**, so applications can store an entire business unit and retrieve it in a single query. However, a document is neither an infinite container nor a write unit that can scale endlessly simply by adding servers. When document boundaries do not fit real-world data, three problems often appear together:

1. **Unbounded arrays:** continuously appending elements with `$push` or `$addToSet` without a capping policy.
2. **Oversized documents:** embedded data bloats, driving up read/write overhead and eventually hitting the **16 MiB BSON document limit**.
3. **Hot documents:** many requests concurrently modify the same document, creating resource contention and bottlenecking throughput even if the collection holds millions of other documents.

In the document model, deciding whether to embed or reference must be driven by **maximum element count, read pattern, write pattern, data lifecycle, and concurrency**, not merely by whether two entities have a parent–child relationship.

## 1. A Document Is Both a Data Boundary and an Update Boundary

Consider an order with a few product line items:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  customerId: "C100",
  status: "PAID",
  items: [
    { sku: "B01", quantity: 2, unitPrice: NumberDecimal("15.00") },
    { sku: "P02", quantity: 1, unitPrice: NumberDecimal("5.00") }
  ]
}
```

This is a favorable case for **embedding**: line items are usually read alongside the order, are reasonably bounded, share the order's lifecycle, and freeze product prices at purchase time.

By contrast, an article may receive millions of comments:

```javascript
{
  _id: ObjectId("65a12f010000000000000002"),
  title: "Introduction to MongoDB",
  comments: [
    { userId: "u1", text: "...", createdAt: ISODate("2026-01-01") },
    { userId: "u2", text: "...", createdAt: ISODate("2026-01-02") }
    // New comments will continue to be appended to the array.
  ]
}
```

Every new comment inflates the parent document. Editing, deleting, or moderating comments also hits that same document; fetching page 1,000 of comments is harder to optimize than when each comment is a separately indexed document.

Three questions to distinguish the cases:

- **Does cardinality have a true ceiling?** Five shipping addresses differ fundamentally from millions of comments, logs, or reactions.
- **Are child elements read together with the parent in most operations?** An order's items array differs from comments loaded 20 records per page.
- **Do writes concentrate on one parent?** Each user updating their own profile differs from a viral post with thousands of concurrent writers.

MongoDB guarantees **atomicity for single-document updates**, even when modifying multiple fields or array elements within that document. Atomicity is useful, yet it does not make every embedded model sound at every scale.

## 2. Unbounded Arrays: A Common Anti-Pattern

An **unbounded array** is an array whose element count grows continuously with application activity without a cap or explicit data-splitting policy.

```javascript
db.posts.updateOne(
  { _id: postId },
  {
    $push: {
      comments: {
        authorId: "u42",
        text: "Helpful article!",
        createdAt: new Date()
      }
    }
  }
);
```

The command is valid. Risk arises when 10, 10,000, and then 1,000,000 elements are all pushed into **one document**.

| Consequence | Impact |
|---|---|
| Size growth | Each new element adds BSON data, field names, array framing, and overhead |
| Document limit | Can exceed the 16 MiB BSON maximum, causing new writes to fail |
| Over-fetching | Clients transfer too many elements if queries lack proper projections |
| Multikey indexes | Indexing array fields generates many index keys and maintenance cost |
| Unscalable writes | Many writers contend on one document instead of independent documents |
| Complex pagination | Hard to index, sort, and filter individual elements at large scale |
| Entangled lifecycles | Deleting or cold-archiving old slices requires rewriting a huge document |

**Do not assume every `$push` always rewrites 16 MiB directly to disk.** WiredTiger has its own caching, page management, and internal update mechanisms. The lasting model issue is unbounded element counts, data/index maintenance costs, payload bloat, and write contention.

### 2.1. Why Doesn't `$addToSet` Solve the Problem?

```javascript
db.posts.updateOne(
  { _id: postId },
  { $addToSet: { likedUserIds: userId } }
);
```

`$addToSet` avoids inserting duplicate values according to MongoDB's array comparison rules, yet the array still grows with the number of **distinct `userId` values**. One million likes from one million accounts produces one million elements. "Unique" does not mean "bounded."

If you need to enforce that each user likes a post at most once, use a `postLikes` association collection storing one document per `(postId, userId)` pair with a unique index.

### 2.2. When Are Embedded Arrays Still Appropriate?

Embedding works well for arrays that are **bounded and share the parent's lifecycle**:

- A user's few addresses or contact methods.
- Line items of a purchase order with a business cap on item count.
- Fixed steps of a small workflow.
- A handful of rarely changing tags or attributes.
- The ten latest activities stored as a display cache.

There is no rigid rule like "arrays over 100 elements are always bad." Ten massive elements can weigh down a document, while a few hundred tiny, rarely updated values may be acceptable. Evaluate **element count × element size × read/write frequency**.

## 3. Oversized Documents: The 16 MiB Limit and Performance Impact

A regular BSON document in MongoDB is limited to **16 MiB** (16 × 1,048,576 bytes). The limit applies to the entire BSON document, including field names, values, nested objects/arrays, and BSON framing overhead—not merely the JSON string length printed on screen.

```text
Collection posts:
  post A: metadata + 8 comments         -> small
  post B: metadata + 90,000 comments    -> grows very large
  post C: metadata + 5,000,000 comments -> impossible to keep embedding

The 16 MiB limit applies PER document,
not to total collection size.
```

Adding RAM, disk, or shards does not allow a single BSON document to exceed 16 MiB. **Sharding distributes documents**, it does not split one oversized document across multiple shards.

If you need to store **large binary files** such as PDFs or videos, consider GridFS (which chunks content) or object storage. GridFS is not the right default for millions of comments that need individual querying, sorting, and updating; those should be independent child documents.

### 3.1. Measuring BSON Size

In `mongosh`, you can measure a single document's size:

```javascript
const post = db.posts.findOne({ _id: postId });

if (post) {
  const bytes = Object.bsonsize(post);
  print("Document bytes: " + bytes);
  print("Document MiB: " + (bytes / (1024 * 1024)).toFixed(2));
}
```

MongoDB aggregation provides the `$bsonSize` expression, useful for locating large documents:

```javascript
db.posts.aggregate([
  {
    $project: {
      title: 1,
      bsonBytes: { $bsonSize: "$$ROOT" },
      commentsCount: {
        $cond: [
          { $isArray: "$comments" },
          { $size: "$comments" },
          0
        ]
      }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 10 }
]);
```

This pipeline may scan many documents, so run it in an appropriate environment or with throttling on large collections. `$bsonSize` measures logical BSON data, not compressed bytes allocated on disk by WiredTiger.

Overview statistics:

```javascript
db.posts.stats();
db.posts.dataSize();
db.posts.storageSize();
db.posts.totalIndexSize();
```

`dataSize`, `storageSize`, and `totalIndexSize` reflect different metrics. They cannot replace checking the BSON size of individual documents.

### 3.2. Projections Shrink Payloads, Not Stored Arrays

```javascript
db.posts.findOne(
  { _id: postId },
  { title: 1, authorId: 1, createdAt: 1 }
);
```

Projections keep the entire array from being returned to the application. You can also use `$slice` to return only a few elements:

```javascript
db.posts.findOne(
  { _id: postId },
  { title: 1, comments: { $slice: -10 } }
);
```

However, **projections only change query output**; they do not delete old data in the document, raise the 16 MiB limit, or reduce write contention on the document. If you have an unbounded array, you must fix the **storage model**, not just the query.

## 4. Reference Pattern: Each Child Element Is a Separate Document

For unbounded one-to-many relationships, replace the embedded array with a separate collection:

```javascript
// posts
{
  _id: ObjectId("65a12f010000000000000002"),
  authorId: "u1",
  title: "Introduction to MongoDB",
  createdAt: ISODate("2026-03-01T10:00:00Z")
}

// comments
{
  _id: ObjectId("65a12f020000000000000001"),
  postId: ObjectId("65a12f010000000000000002"),
  authorId: "u42",
  text: "Helpful article!",
  createdAt: ISODate("2026-03-02T09:00:00Z"),
  status: "VISIBLE"
}
```

Each new comment creates an independent document:

```javascript
db.comments.insertOne({
  postId,
  authorId: "u42",
  text: "Helpful article!",
  createdAt: new Date(),
  status: "VISIBLE"
});
```

Comment growth does not inflate the BSON size of the `posts` document. Each comment also gets its own lifecycle, permissions, and edit/hide operations.

### 4.1. Indexes for Comment Pagination

```javascript
db.comments.createIndex({
  postId: 1,
  createdAt: -1,
  _id: -1
});

db.comments.find({ postId })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

The compound index starts with `postId` for the equality filter, followed by `createdAt` and `_id` to support newest-first sorting. `_id` acts as a tie-breaker if multiple comments share the same timestamp.

When fetching the next page, use a cursor from the last record of the previous page:

```javascript
const lastCreatedAt = ISODate("2026-03-02T09:00:00Z");
const lastId = ObjectId("65a12f020000000000000001");

db.comments.find({
  postId,
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

This example assumes `lastCreatedAt` and `lastId` come from the last record of the previous page. **Keyset pagination** avoids the cost of scanning past many records like deep `skip()`. Still verify `explain()` and real indexes, especially when combining `status` filters or authorization checks.

### 4.2. Costs and Responsibilities of Referencing

Referencing may require multiple queries to load parent and children, or occasionally `$lookup` when a join is genuinely needed. When deleting a parent, MongoDB does not automatically enforce foreign keys or cascades like a typical RDBMS: the application must handle deleting/hiding children. If multi-document updates must be atomic, consider transactions on supported deployments.

This is a worthwhile trade-off for comments, activity logs, unbounded transaction details, and independently lived data.

## 5. Bounded Arrays: Keeping a Small Display Set

If the UI only needs the 10 most recent activities, you can use a **bounded array**. The `$push` modifier with `$each`, `$sort`, and `$slice` caps the number of retained elements:

```javascript
db.userDashboards.updateOne(
  { _id: userId },
  {
    $push: {
      recentActivities: {
        $each: [
          {
            eventId: new ObjectId(),
            label: "Logged in",
            createdAt: new Date()
          }
        ],
        $sort: { createdAt: -1 },
        $slice: 10
      }
    }
  }
);
```

Here `$sort: { createdAt: -1 }` puts newest items first, and `$slice: 10` retains the first ten elements. Alternatively, if appending in arrival order without sorting by timestamp, keep the last 20 elements:

```javascript
db.userDashboards.updateOne(
  { _id: userId },
  {
    $push: {
      recentActions: {
        $each: [newAction],
        $slice: -20
      }
    }
  }
);
```

**Note:** bounded arrays protect against unbounded size growth, yet **do not automatically solve hot documents**. If thousands of requests per second still modify `userDashboards[_id=...]`, contention can still occur.

### 5.1. Small Snapshots and Historical Sources of Truth

You can store all activities in `activities` and maintain the 10 latest in `userDashboards.recentActivities` as a snapshot:

```text
activities               ← canonical historical data
   |
   +--> Paginated API by userId / createdAt
   |
   +--> userDashboards.recentActivities
        (snapshot of up to 10 items for overview screen)
```

If writes to the two collections are not inside a transaction, the snapshot can lag or temporarily differ from the source. Define the **source of truth**, snapshot rebuild capability, retries, and acceptable consistency level.

## 6. Bucket Pattern: Capping Each Storage Unit

The **bucket pattern** stores a group of events per document, partitioned by device and time or another grouping key. Rather than one device document holding its entire history:

```javascript
{ _id: deviceId, events: [ /* millions of events */ ] }
```

you can create multiple buckets:

```javascript
{
  _id: "sensor-101/2026-03-01T10",
  deviceId: "sensor-101",
  hourStart: ISODate("2026-03-01T10:00:00Z"),
  events: [
    { at: ISODate("2026-03-01T10:00:05Z"), temperature: 24.1 },
    { at: ISODate("2026-03-01T10:00:10Z"), temperature: 24.3 }
  ],
  eventCount: 2
}
```

The next bucket corresponds to another hour or starts once a bucket hits an element/size threshold. Benefits: fewer documents than one-per-event, data organized by access window, and bounded per-document size.

However, do not treat bucketing as a silver bullet: if thousands of writers simultaneously insert events into **the current active bucket** of one device, that bucket itself becomes a hot document. Choose time windows, partition counts, or standalone event documents according to workload.

### 6.1. Enforcing Bucket Capacity with Atomic Conditions

Example updating an existing bucket with fewer than 500 events:

```javascript
const result = db.buckets.updateOne(
  {
    _id: bucketId,
    eventCount: { $lt: 500 }
  },
  {
    $push: { events: event },
    $inc: { eventCount: 1 }
  }
);

if (result.modifiedCount === 0) {
  // Bucket may be full, missing, or condition no longer holds.
  // Verify state and select/create another bucket.
}
```

The filter and update run atomically on the document. Still, this is only an **illustration**: a complete design needs safe bucket creation/rollover under concurrent writers, unique keys, retry/idempotency handling, and size bounds on **each event**. A 500-element cap does not guarantee staying under 16 MiB if each event is large.

### 6.2. Time-Series Collections for Timestamped Telemetry

MongoDB offers **time-series collections** optimized for telemetry data with timestamps and metadata:

```javascript
db.createCollection("measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "deviceId",
    granularity: "seconds"
  }
});

db.measurements.insertOne({
  deviceId: "sensor-101",
  measuredAt: new Date(),
  temperature: 24.3
});
```

Time-series collections have internal bucketing and specific constraints around updates/deletes, indexes, sharding, and server versions. They fit time-stamped measurements well; they are not automatically suitable for comments that require per-record moderation or edits.

## 7. Outlier Pattern: Handling Extreme Cases

Many applications have skewed distributions: most articles have few comments, yet a few viral ones have millions. The **outlier pattern** flags exceptional cases for specialized storage, or pairs a small embedded snapshot with full child data in a separate collection:

```javascript
// posts: metadata + small snapshot
{
  _id: postId,
  title: "Article",
  recentComments: [ /* up to 10 items */ ],
  commentCountApprox: 1500000
}

// comments: full historical source
{
  _id: commentId,
  postId,
  authorId: "u42",
  text: "...",
  createdAt: ISODate("2026-03-10T12:00:00Z")
}
```

If you maintain two schemas (small posts embed, large posts reference), you must handle threshold crossing, migration, and dual read paths. Often, storing all comments in the child collection from day one while keeping `recentComments` as a cache is simpler. Choose after weighing read frequency against operational complexity.

## 8. Hot Documents: Atomicity Does Not Mean Unlimited Parallel Writes

MongoDB supports atomic updates on a single document, yet many writers modifying the same document must coordinate so they do not corrupt or bottleneck data. For example, likes on a viral post:

```javascript
db.posts.updateOne(
  { _id: viralPostId },
  { $inc: { likeCount: 1 } }
);
```

`$inc` makes each increment atomic. Even so, if every request increments `likeCount` on **one single document**, the system still has a contention bottleneck; adding more nodes will not split writes targeting that one document.

### 8.1. Prevent Lost Updates Before Optimizing Throughput

Error-prone pattern:

```javascript
// Two requests both read likeCount = 100.
const current = db.posts.findOne({ _id: postId }).likeCount;

// Both set it to 101: one increment is lost.
db.posts.updateOne(
  { _id: postId },
  { $set: { likeCount: current + 1 } }
);
```

Atomic operator pattern:

```javascript
db.posts.updateOne(
  { _id: postId },
  { $inc: { likeCount: 1 } }
);
```

The second approach handles simple arithmetic accurately, yet still creates **a single write point**. Write conflicts, retries, rising latency, and throughput limits can appear under heavy load.

### 8.2. A Hot Document Does Not Have to Be Large

| Example | Source of Contention |
|---|---|
| Viral post | Many requests incrementing views/likes or adding comments |
| System-wide counter | Every event incrementing one shared field |
| Current hour sensor bucket | Many writers `$push`ing into one array |
| High-traffic account status | Many jobs updating one object |
| Shared cart edited by multiple actors | Concurrent writes on the same document |
| Config doc used as a distributed lock | Multiple processes competing to acquire/renew lease |

A document of just a few bytes can be extremely hot. Conversely, a document of hundreds of kilobytes that is mostly read and rarely written may cause negligible contention.

### 8.3. When to Keep Single-Document Atomic Updates

Inventory stock example:

```javascript
const result = db.inventory.updateOne(
  {
    _id: sku,
    available: { $gte: quantity }
  },
  { $inc: { available: -quantity } }
);

if (result.modifiedCount !== 1) {
  // Insufficient stock, missing SKU, or condition changed.
}
```

The filter and update protect the `available >= 0` invariant on that document. If business logic also creates an order and updates other states, use a multi-document transaction or an appropriate business workflow. **Never sacrifice inventory correctness** to scatter writes without an equivalent mechanism protecting the invariant.

## 9. Reducing Write Contention: Intentional Data Distribution

### 9.1. Do Not Update the Parent Document Unnecessarily

When comments live separately, adding a comment does not have to update `posts` immediately:

```javascript
db.comments.insertOne({
  _id: new ObjectId(),
  postId,
  authorId,
  text,
  createdAt: new Date()
});
```

Counts can be queried on demand:

```javascript
db.comments.countDocuments({ postId });
```

`countDocuments` has a cost depending on indexes and matching count, so it is unsuitable at extreme frequency on huge datasets. However, a batched cache/materialized count avoids hammering the parent on every write. Distinguish **exact canonical figures** from **approximate display counts**.

### 9.2. Counter Partitions: Split Counters Across Multiple Documents

Instead of a single `post.likeCount`, split into N documents each holding a partial count:

```javascript
{
  _id: "post-123/07",
  postId: "post-123",
  partition: 7,
  count: NumberLong("1200")
}
```

Create a unique index and distribute updates:

```javascript
db.counterPartitions.createIndex(
  { postId: 1, partition: 1 },
  { unique: true }
);

const partition = Math.floor(Math.random() * 32);

db.counterPartitions.updateOne(
  { postId: "post-123", partition },
  { $inc: { count: NumberLong("1") } },
  { upsert: true }
);
```

Compute the total:

```javascript
db.counterPartitions.aggregate([
  { $match: { postId: "post-123" } },
  { $group: { _id: "$postId", total: { $sum: "$count" } } }
]);
```

Production implementations also require:

- Pre-initializing partitions or handling duplicate-key retries when concurrent writers upsert for the first time.
- Choosing N large enough to spread writes, yet small enough to keep total aggregation cheap.
- Ensuring retried requests do not double-increment if **idempotency** is needed.
- Recognizing that summing multiple partitions is not automatically an atomic snapshot across all contexts.
- If the collection is sharded, choosing a shard key so partitions can actually land on different shards.

This **splits a counter across multiple documents**, which does not automatically mean MongoDB places all of them on distinct physical shards.

### 9.3. Event Logs and Materialized Views

You can record each interaction as an event document with a stable ID:

```javascript
db.likeEvents.insertOne({
  _id: eventId,
  postId,
  userId,
  createdAt: new Date(),
  action: "LIKE"
});
```

A background consumer or change stream can derive counts from events. Event logs aid auditing, reconciliation, and metric recomputation. However, retries between writing the event and updating the projection require deduplication; a unique event ID at the source **does not automatically guarantee** downstream side effects execute only once.

If the invariant is that each user likes a post at most once, extract an association document with a unique index:

```javascript
db.postLikes.createIndex(
  { postId: 1, userId: 1 },
  { unique: true }
);

db.postLikes.insertOne({
  postId,
  userId,
  createdAt: new Date()
});
```

The index ensures no two identical `(postId, userId)` pairs exist in the collection per index rules. On sharded collections, unique indexes have shard-key constraints that must be checked before deployment.

### 9.4. Queues and Batching When Eventual Consistency Is Acceptable

For view counts, telemetry, or metrics that do not require instant consistency, you can ingest raw events, group them by time windows, flush aggregated increments in batches, and build retry/reconciliation jobs. The trade-off is display lag. Explicitly state the acceptable consistency level rather than using this pattern for balances or inventory without proper safeguards.

## 10. Sharding Does Not Split One Large or Hot Document

MongoDB sharding distributes **documents of a collection** by shard key; it does not split a single oversized BSON document into pieces to bypass the 16 MiB limit.

```text
Single-document concentrated design:
  posts[_id = viralPostId]
    ├─ massive comments array
    ├─ likeCount
    └─ every request modifies the same document
       └─ one write point, one document on one shard

Distributed data design:
  posts[_id = viralPostId]         (metadata)
  comments[commentId1]           (separate record)
  comments[commentId2]
  counterPartitions[postId, 0]
  counterPartitions[postId, 1]
  ...
```

Splitting into multiple documents creates the opportunity to distribute load, yet the shard key still governs physical placement:

- A shard key on `postId` alone can concentrate every comment of a viral post into the same key range.
- A hashed shard key on `postId` spreads **different posts**, but one single `postId` still hashes to one value and does not split that post's load.
- Including a bucket/partition in the key model can spread a single large entity, at the cost of query and uniqueness complexity.
- A poorly distributed or monotonically increasing shard key can create a **hot shard** even without a single hot document.

A **hot document** is contention on one document; a **hot shard** is imbalanced load across shards. They can happen together, but they are not the same thing.

## 11. Design Pattern Selection Table

| Workload | Pattern to Evaluate | Conditions to Watch |
|---|---|---|
| Order with few line items | Embedded array | Bounded item count, shared lifecycle |
| Article with millions of comments | Reference: `comments` collection | Indexes, pagination, cascade hide/delete |
| UI needing only 10 latest activities | Bounded array | `$slice`, source of truth, and snapshots |
| Sensor streaming continuous events | Separate events, buckets, or time-series | Ingest rate, retention, bucket cap |
| A few extreme outlier records | Outlier pattern | Threshold crossing and migration |
| Viral video with massive views/likes | Counter partitions or event log | Idempotency, lag, total reads |
| Each user likes a post at most once | Link document + unique index | Uniqueness and shard key |
| Inventory must stay non-negative | Conditional atomic update | Never sacrifice invariants for speed |
| Storing binary files > 16 MiB | GridFS or object storage | Streaming, lifecycle, backups |
| Array of at most 3 items, rare updates | Embedding | Co-read together, reasonable total bytes |

Final choices must be grounded in workload. An array of 200 short, rarely updated strings may pose no problem; an array of 20 large objects updated thousands of times per second can be a poor design.

## 12. Diagnosing Issues in Production Systems

### 12.1. Spotting Bloating Data

- BSON sizes of the largest documents grow steadily over time.
- Array lengths correlate with account/post/device age.
- API payload sizes grow even though screens show only a few items.
- Multikey index sizes on arrays expand rapidly.
- Updates begin failing as documents approach 16 MiB.

Measure BSON sizes and array length distributions alongside collection stats. File sizes on disk reflect compression and reusable free space, so they do not directly mirror individual document sizes.

### 12.2. Spotting Contention / Hot Documents

- Many updates targeting the same `_id` slow down as traffic climbs.
- Profiler/monitoring shows writes concentrated on a single key.
- Write conflicts/retries and write latency spike during concurrency bursts.
- A single shard absorbs most write traffic.
- Scaling hardware fails to lift throughput proportionally because updates funnel into one target.

One slow operation is **not enough** to diagnose a hot document: it could stem from missing indexes, disk latency, cache pressure, network issues, or long transactions. Measure those factors together.

### 12.3. Analyzing Queries Before and After Splitting Data

```javascript
db.posts.find(
  { _id: postId },
  { title: 1, createdAt: 1 }
).explain("executionStats");

db.comments.find({ postId })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned` to evaluate read queries. To analyze write throughput, add telemetry for update latency, contention, write conflicts, per-key write rates, and shard distribution; `explain()` on read queries does not tell the whole write story.

## 13. Migration Workflow from Unbounded Array to Reference

Initial state:

```javascript
{
  _id: postId,
  title: "MongoDB Patterns",
  comments: [
    { authorId: "u1", text: "Great!", createdAt: ISODate("2026-01-01") },
    { authorId: "u2", text: "Clear", createdAt: ISODate("2026-01-02") }
  ]
}
```

Goal: `posts` holds metadata, and each comment becomes a document in `comments`. Handle continuous live writes carefully:

1. **Define target schema:** `postId`, stable `commentId`, `createdAt`, `status`, indexes, uniqueness rules, and source of truth.
2. **Shift new writes:** insert new comments into the child collection. If a dual-write phase exists, handle duplicates and reconciliation.
3. **Backfill in batches:** migrate older comments into child documents using deterministic IDs so retries on failure are idempotent; never assume array positions are permanent IDs.
4. **Reconcile data:** compare counts, detect duplicates, verify permissions, fields, and pagination.
5. **Switch read paths:** update APIs to query `comments` with proper filters/sorts/indexes instead of loading the embedded array.
6. **Remove the old array or shrink to a bounded snapshot:** only after confirming no writers still use the old schema.
7. **Measure post-migration:** check document sizes, read/write latency, index footprint, and access distribution.

Removing the old array from documents does not guarantee WiredTiger disk files shrink immediately; the storage engine may retain free blocks for reuse. That is a storage compaction topic distinct from fixing the model.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Embedding every child record in parent | Unbounded arrays and oversized documents | Child collection referencing parent |
| Adding only `$slice` to projections | Shrinks payload, yet DB keeps bloating | Cap at write time or split data |
| Using `$addToSet` for millions of user IDs | Deduplicated, yet still unbounded | Association collection + unique index |
| Putting comments, `likedUserIds`, and `likeCount` all in `post` | Both oversized document and hot writes | Separate links, counters, and snapshots |
| Using `$set` after reading current count | Lost updates | Use `$inc` or conditional updates |
| Assuming `$inc` atomicity prevents contention | Single document remains a write hotspot | Shard across documents when business rules allow |
| Partitioning counters without handling retries | Double counting / inaccurate totals | Idempotency and reconciliation |
| Thinking sharding splits a 20 MiB document | Still hits 16 MiB limit | Split into multiple documents |
| Using hashed shard key on an entity when one entity is super hot | Same hash still hotspots | Logical partitioning across multiple keys |
| Using eventual counts for inventory without safeguards | Can oversell stock | Conditional atomic updates / transactions |

## 15. Practice Exercises

### Exercise 1 — Article Comments

An article can have from 0 to 5 million comments, and users load pages of 20 newest comments. Design the collections, indexes, and keyset pagination. Explain why a single `comments: []` array is unsuitable and why `_id` serves as a tie-breaker for comments sharing the same `createdAt`.

### Exercise 2 — Login History

A `users` document currently stores all login history inside `loginHistory`. Write a `$push` statement keeping only the 10 most recent entries, then add a `loginEvents` collection for full auditing. State clearly which data is the source of truth, which is the snapshot, and how to repair the snapshot if it drifts out of sync.

### Exercise 3 — Like Counter

A viral post receives 100,000 views per second. Explain why `$inc` ensures accurate increments on one document yet still suffers contention. Propose 32 counter partitions, describe how totals are read, how double-counting occurs on retries, and an idempotency strategy.

### Exercise 4 — Telemetry and Buckets

A device emits 1,000 events/second; each event is a few hundred bytes and must be retained for 12 months. Analyze why a one-hour bucket risks becoming too large or too hot. Compare separate event documents, small capped buckets, and time-series collections, accounting for retention and time-range queries.

### Exercise 5 — Inventory

Only one unit remains in stock, and two shoppers place orders at the same time. Write an `updateOne` with `available >= 1` and `$inc` decrementing by one. Explain why it should not be replaced by an eventually consistent counter without an equivalent mechanism protecting the invariant.

## Conclusion

**Unbounded arrays** are a data modeling risk; **oversized documents** inflate read/write costs and hit the 16 MiB BSON limit; **hot documents** are a write-distribution and concurrency contention risk. All three often appear together, yet each must be addressed at its root cause.

Move unbounded one-to-many data to a **referenced collection**, embed only a **bounded array** for snapshots, use **buckets/time-series** for time-ordered data, or distribute **counters/events** under heavy write concentration. Every choice carries implications for indexing, consistency, idempotency, and reconciliation. Effective document design keeps BSON boundaries aligned with business boundaries and real-world load.
