# Denormalization, Data Duplication, and Maintaining Consistency in the MongoDB Document Model

## 1. Why Does MongoDB Often Store Partially Duplicated Data?

MongoDB stores data in **BSON documents**. A single document can contain scalar fields, nested objects, and arrays; documents within the same collection do not have to share an identical structure. Consequently, when designing a data model, you have more options than splitting every entity into a separate table and joining them at read time.

For example, an order list screen often needs the order ID, customer name, and product name together. If stored using pure referencing:

```javascript
// customers
{ _id: "C01", name: "Nguyen An", loyaltyTier: "GOLD" }

// products
{ _id: "P01", name: "Mechanical Keyboard", price: NumberDecimal("1200000") }

// orders
{
  _id: "O1001",
  customerId: "C01",
  items: [{ productId: "P01", quantity: 2 }],
  placedAt: ISODate("2026-10-01T09:00:00Z")
}
```

To display the customer's name and product name, the application must issue extra queries or use the `$lookup` aggregation stage to fetch data from other collections. Another option is to **intentionally store a copy** of selected fields right inside the order document:

```javascript
{
  _id: "O1001",
  customer: {
    id: "C01",
    nameAtPurchase: "Nguyen An"
  },
  items: [{
    productId: "P01",
    productNameAtPurchase: "Mechanical Keyboard",
    unitPriceAtPurchase: NumberDecimal("1200000"),
    quantity: 2
  }],
  placedAt: ISODate("2026-10-01T09:00:00Z")
}
```

In the second document, the customer name and product details were **copied** from other sources at the time of ordering. As a result, the order detail page can read most required data with a single query against `orders`, without depending on the current state of `products`.

This is an example of **denormalization**: deliberately duplicating or organizing data to match real access patterns, rather than trying to separate every shared attribute into independent entities.

Denormalization does not mean "ignoring data quality." It shifts part of the workload from **read time** to **write time and data maintenance**.

## 2. Distinguish Three Concepts Commonly Lumped Together as "Copying"

| Concept | What Is Duplicated / Replicated? | Goal | Who Handles Consistency? |
|---|---|---|---|
| **Data denormalization** | The same business attribute appears in multiple documents or locations | Fast reads, accurate snapshots, fewer joins | Application design, transactions, async processing, reconciliation workflows |
| **Data embedding** | Child entity or related fields sit inside a parent document | Read/update co-used data together | Single-document atomic boundary and business logic |
| **MongoDB Replication** | Replica set members store copies of data and apply the oplog | Availability, redundancy, secondary reads | MongoDB replication mechanism and read/write concern levels |

**Key takeaway:** Having a product name appear in `products` and in thousands of `orders` documents is **business data duplication**. It is different from MongoDB replicating the `orders` document across replica set members. `writeConcern: "majority"` requests replication acknowledgment across members; it **does not automatically synchronize** a product name duplicated across different collections.

## 3. Three Ways to Organize Data Relationships

Suppose an article platform has authors. The list screen needs the article title, author display name, and author avatar.

### 3.1. Referencing Only

```javascript
// authors
{
  _id: "A01",
  displayName: "Mai",
  avatarUrl: "/avatars/mai.png",
  biography: "Database specialist author"
}

// posts
{
  _id: "POST01",
  authorId: "A01",
  title: "MongoDB document model",
  publishedAt: ISODate("2026-10-01T09:00:00Z")
}
```

The advantage is that the author's name, avatar, and bio have **one single source of truth**. When changing an avatar, only `authors` needs updating. The drawback is that if the screen needs author details, reads may require additional queries or `$lookup`:

```javascript
db.posts.aggregate([
  { $match: { _id: "POST01" } },
  {
    $lookup: {
      from: "authors",
      localField: "authorId",
      foreignField: "_id",
      as: "author"
    }
  },
  { $unwind: "$author" },
  {
    $project: {
      title: 1,
      "author.displayName": 1,
      "author.avatarUrl": 1
    }
  }
]);
```

MongoDB supports `$lookup`, but that does not mean every join is cheap. Performance depends on data volume, pipeline shape, indexes on the target collection, and the number of documents processed.

### 3.2. Embedding All Related Information

```javascript
{
  _id: "POST01",
  title: "MongoDB document model",
  author: {
    id: "A01",
    displayName: "Mai",
    avatarUrl: "/avatars/mai.png",
    biography: "Database specialist author"
  }
}
```

A single read of the article retrieves all author information. However, if an author has 100,000 posts, each holding the full bio and author metadata, total storage balloons significantly. When the author updates their bio, the application must decide whether to update 100,000 documents.

Full embedding generally fits data **owned by a single parent document** and co-read/updated with that parent, such as small line items of an order. It fits poorly for shared entities with independent lifecycles referenced by large numbers of documents, such as a full author profile.

### 3.3. Copy Only the Fields Needed for Reading

```javascript
{
  _id: "POST01",
  authorId: "A01",
  authorPreview: {
    displayName: "Mai",
    avatarUrl: "/avatars/mai.png"
  },
  title: "MongoDB document model",
  publishedAt: ISODate("2026-10-01T09:00:00Z")
}
```

`authorId` still links to the canonical author. `authorPreview` is a small copy that speeds up rendering post lists. When opening the detailed author page, the application still queries `authors`. This approach is commonly called the **extended reference pattern**: keeping the reference key while copying a few frequently read fields.

The hard part is not the `find` command, but the **update contract**: when the display name changes, must `authorPreview.displayName` in posts change too? If so, how much propagation delay does the system tolerate?

### 3.4. Comparison by Access Pattern

| Storage Approach | Dependent Data Accesses | Write Cost on Shared Data Change | When to Consider |
|---|---|---|---|
| Referencing only | May require `$lookup` / multiple reads | Usually updates only canonical source | Shared entities, frequent updates, large fan-out |
| Full embedding | Usually read in one document | May require updating many copies | Child data with tight ownership and bounded size |
| Reference + small copy | Fast common screen reads, source still accessible | Must sync copied fields if freshness is required | Lists, display cards, read-heavy views |

A MongoDB collection does not have to follow only one strategy. You can embed the shipping address as a snapshot in `orders`, reference `customers`, and maintain an `authorPreview` copy in `posts`.

## 4. Before Copying: Distinguish Historical Snapshots from Live Copies

Not every "diverged" value is a bug. You must decide **the semantics of a copy** before writing synchronization code.

### 4.1. Historical Snapshot: Intentionally Unsynchronized

A customer places an order when a product costs 1,200,000 VND. A month later the store raises the price to 1,350,000 VND. The old order **must not change its price automatically**:

```javascript
// products: current selling price
{
  _id: "P01",
  name: "Mechanical Keyboard",
  currentPrice: NumberDecimal("1350000")
}

// orders: details at transaction lock-in time
{
  _id: "O1001",
  items: [{
    productId: "P01",
    productNameAtPurchase: "Mechanical Keyboard",
    unitPriceAtPurchase: NumberDecimal("1200000"),
    quantity: 2
  }]
}
```

`currentPrice` and `unitPriceAtPurchase` are **two distinct business concepts**, even though the second was created by copying the price from the first at a specific moment. The same applies to invoice product names, tax rates, shipping addresses at checkout, or accepted terms.

Blindly "syncing all copies" would corrupt transaction history.

### 4.2. Current Display Copies: May Require Synchronization

In a social network, the post UI might require always showing the author's current name and avatar. When the author changes their name, existing `posts.authorPreview.displayName` fields become **stale**. The application must define one of these expectations:

- **Immediate consistency after operation (strong/atomic requirement within business scope):** users must never observe conflicting versions across related reads.
- **Eventual consistency:** tolerate stale copies briefly, then converge to the same value.
- **No synchronization:** the copy intentionally captures details as of post creation time.

Avoid generic field names like `author.name` that obscure this decision. Names such as `authorNameAtPublish`, `currentAuthorName`, or `authorPreviewVersion` clarify the contract.

### 4.3. Initial Decision Matrix

| Copied Data | Must Preserve Historical Value? | Must Track Current Source? | Suggested Strategy |
|---|:---:|:---:|---|
| Price on an order | Yes | No | Store snapshot; do not sync when price list changes |
| Confirmed delivery address | Yes | No | Snapshot on the order |
| Author display name on posts | Product-dependent | Usually yes | Direct reference or copy with update mechanism |
| Displayed like count | No | Yes, lag acceptable | Clear counter source, atomic increments or aggregation |
| Daily revenue report | Finalized periods must stay stable | Yes for open periods | Pre-aggregated data, watermarks, and recomputation job |
| User roles / permissions | No | Usually requires latest | Avoid relying on lagged copies for authorization decisions |

For data governing access control, payments, credit limits, or inventory, required consistency must come from **business invariants**, not merely from the desire to reduce queries.

## 5. The Cost of Denormalization

### 5.1. Faster Reads, Potentially More Expensive Writes

Suppose an author has 50,000 posts. Copying `displayName` into every post lets the list view skip joining with `authors` on reads, yet renaming the author can trigger 50,000 document updates. That is **write amplification**: a single business change generates many write operations.

Other costs to weigh:

- **Storage:** duplicated values consume extra disk space and cache memory.
- **Indexes:** if copied fields are indexed, every update also modifies index keys.
- **Operations:** requires handling partial update failures, retries, progress tracking, and reconciliation.
- **Concurrent load:** the same group of documents may be modified concurrently by multiple jobs.
- **Read staleness:** with asynchronous copies, the UI can briefly display outdated values.
- **Data governance:** updating or erasing sensitive personal data must cover every duplicated location.

Never assume "MongoDB prefers denormalizing everything." MongoDB supports both embedded and referenced models; the right design depends on read/write patterns.

### 5.2. Document Size and Unbounded Arrays

MongoDB imposes a **16 MiB limit per BSON document**. If you embed every comment on an article into one document:

```javascript
{
  _id: "POST01",
  title: "A very popular article",
  comments: [ /* millions of comments */ ]
}
```

the `comments` array will grow without bound, making the document huge, writes and network transfers heavy, and eventually impossible to extend. A better option is moving `comments` to a separate collection with `postId` and a proper index, keeping only a few recent comments if the screen needs them:

```javascript
// posts
{
  _id: "POST01",
  title: "A very popular article",
  recentComments: [
    { id: "CM09", content: "Very helpful!" }
  ],
  commentCount: 54201
}

// comments
{
  _id: "CM09",
  postId: "POST01",
  content: "Very helpful!",
  createdAt: ISODate("2026-10-20T08:30:00Z")
}
```

This example uses the **subset pattern**: keeping a tiny subset for fast display while storing the full dataset in a separate collection. Here `recentComments` and `commentCount` require a synchronization or recomputation strategy.

### 5.3. The "Hot" Document Problem

If thousands of users simultaneously increment `likesCount` on a viral post, the single document holding that counter can become a write contention hotspot. `$inc` updates the value atomically and accurately, but it does not eliminate the throughput ceiling of a single hot write target. When truly high write volume is required, systems may batch updates, buffer events, or use distributed counters; since those add complexity, measure before adopting them.

## 6. Atomicity Levels: Single Document vs. Multi-Document

### 6.1. Single-Document Updates Are Protected by Atomicity

MongoDB guarantees that a write operation on **one document** is atomic, even when modifying multiple fields or nested elements inside that document.

```javascript
// Seed test document first.
db.carts.insertOne({
  _id: "CART01",
  totalQuantity: 2,
  items: [{ productId: "P01", quantity: 2 }]
});

// Add one unit of the same product and increment total quantity.
db.carts.updateOne(
  { _id: "CART01", "items.productId": "P01" },
  {
    $inc: {
      totalQuantity: 1,
      "items.$.quantity": 1
    }
  }
);
```

Both changes—`totalQuantity` and `items.$.quantity`—sit **within the same document**, so either both appear after a successful operation or neither is observed as a half-written document state. The positional `$` operator here targets **the first array element matching the query predicate**; the model must ensure appropriate array structure and predicates.

This is why tightly coupled child data that is frequently updated together and bounded in size is a strong candidate for embedding.

### 6.2. An `updateMany()` Is Not a Collection-Wide Transaction

Suppose copied author names appear in many posts:

```javascript
db.posts.updateMany(
  { authorId: "A01" },
  { $set: { "authorPreview.displayName": "Mai Nguyen" } }
);
```

Each post document updates atomically, yet **the overall command is not atomic across the set of documents**. If an error happens mid-execution, some posts may already carry the new name while others still show the old name. A concurrent reader can observe mixed states.

Simply re-running the same `$set` may be safe in trivial cases, but when multiple renames and async tasks overlap, replaying an older event can **overwrite newer data**. A versioning order mechanism is needed.

### 6.3. Transactions When a Group of Writes Must Succeed Together

MongoDB supports **multi-document transactions** on replica sets and sharded clusters that meet deployment requirements. If one change must write atomically across several related documents, a transaction is the right tool.

Node.js MongoDB driver example, where `users` is the canonical source and `userCards` is a display copy:

```javascript
// Abbreviated example: client is an already-connected MongoClient.
const database = client.db("social");

await client.withSession(async (session) => {
  await session.withTransaction(async () => {
    await database.collection("users").updateOne(
      { _id: "U01" },
      { $set: { displayName: "Mai Nguyen" } },
      { session }
    );

    await database.collection("userCards").updateOne(
      { _id: "U01" },
      { $set: { displayName: "Mai Nguyen" } },
      { session }
    );
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });
});
```

A transaction can commit both updates or abort both under transaction semantics. This works well when the document set is small and business invariants require them to change as a unit.

However, transactions are **not a free way to update millions of copies**:

- Long-running transactions add resource overhead and lock/conflict risk.
- Retriable errors or uncertain commit outcomes can occur due to network issues or failovers.
- Reads do not automatically gain cross-command consistency just because writes used a transaction; `readConcern` and sessions still matter.
- If a change has massive fan-out, choose another pattern rather than stuffing every document into a giant transaction.

**Core distinction:** single-document atomicity is the default for single-document writes; multi-document atomicity requires an explicit transaction boundary.

## 7. Source of Truth and Synchronization Contracts

To make synchronizing duplicated data predictable, define upfront:

1. **Source of truth:** which field is edited directly, and which collection holds final authority?
2. **Copies:** which fields are derived values allowed to update automatically?
3. **Read behavior:** while a copy lags, may screens show stale data or must they read from the source?
4. **Consistency boundary:** is single-document, multi-document, or eventual consistency required?
5. **Error recovery:** how are events emitted, retried, lag-monitored, and reconciled periodically?

Example contract for `users.displayName` and `posts.authorPreview.displayName`:

```text
users.displayName
  = source of truth, only the profile service may modify it
                  |
                  | UserNameChanged(userId, version, displayName)
                  v
posts.authorPreview.displayName
  = display copy, updated by worker; max lag bounded by system SLO
                  |
                  v
periodic reconciliation: detect copies lagging behind source version
```

Enforcing "only the profile service edits the source of truth" avoids having two independent writers competing to overwrite each other.

### 7.1. A Copy Must Never Become a Second Source of Truth

Suppose service A edits `users.displayName` and service B edits `posts.authorPreview.displayName` directly. When they diverge, the system cannot tell which name is right. Therefore:

- User actions normally modify the **source of truth** first.
- Copies are updated from the source state or events emitted by the source.
- If a copy must change independently for a distinct requirement, treat it as a **different business field** and name it accordingly, such as `displayNameAtPublish`.

This design decision carries greater impact than picking any specific MongoDB operator.

## 8. Synchronous vs. Asynchronous Synchronization

### 8.1. Synchronous Update on the Write Path

If only a few copies need updating and strong consistency is required, the service can update them inside a transaction as in Section 6.3. This fits when the document set is small, known, affordable, and the transaction genuinely covers every piece of data that must stay consistent.

Advantage: clear commit boundary. Drawback: overall latency and failure rate rise as step count grows; two collections do not stay consistent outside the transaction boundary.

### 8.2. Eventual Sync via Events

When very many posts duplicate author details, applications avoid updating every post inside the rename request itself. A sound flow:

```text
User changes name
        |
        v
Write users.displayName + increment users.version
        |
        v
Emit UserNameChanged(version=N) event
        |
        v
Worker consumes event, finds author's posts
        |
        v
Update authorPreview if current version < N
        |
        v
Reconcile / retry any remaining un-updated posts
```

Between steps, some posts still show the old name. This is **intentional eventual consistency**, not necessarily a bug, provided the product defines an acceptable lag threshold and recovery mechanism.

### 8.3. Use Versions to Prevent Old Events from Overwriting Newer Ones

Suppose an author renames twice:

```text
version 41: "Mai"
version 42: "Mai Nguyen"
```

If a worker processes version 42 first, and later due to a retry processes version 41, the copy could **regress** to the old name. The solution is attaching a monotonically increasing version at the source:

```javascript
// A document already initialized with a version.
{
  _id: "U01",
  displayName: "Mai",
  version: NumberLong(41)
}

// Atomically update name and increment version on the source of truth.
db.users.updateOne(
  { _id: "U01" },
  {
    $set: { displayName: "Mai Nguyen" },
    $inc: { version: NumberLong(1) }
  }
);
```

Workers can propagate `sourceVersion` to each copy:

```javascript
// Each post already has numeric authorPreview.version.
// Latest event: userId=U01, version=42, displayName="Mai Nguyen".
db.posts.updateMany(
  {
    authorId: "U01",
    "authorPreview.version": { $lt: NumberLong(42) }
  },
  {
    $set: {
      "authorPreview.displayName": "Mai Nguyen",
      "authorPreview.version": NumberLong(42)
    }
  }
);
```

Both fields inside **a single post** update atomically. An event with `version <= 42` will no longer match posts already at version 42, preventing stale names from overwriting newer copies through this update.

This is only **part** of the design:

- Newly created copies must initialize `version` explicitly; documents missing `version` will not match the `$lt` predicate shown above.
- New events may require batched updates; the workflow must track unfinished documents and retry.
- If a worker crashes mid-run, replaying the event is necessary; the version predicate makes replays safer.
- When incrementing `version` at the source, the event must carry **the exact version written**, rather than reading the version separately in a racy step.

### 8.4. How to Emit Events Without Losing Notifications

A common bug:

```text
1. Update users succeeds.
2. Process crashes before publishing event to queue.
3. Copies never receive the rename notification.
```

The **transactional outbox** pattern addresses this: write the source change and a pending outbox event record within **the same atomic boundary** (same document if the model allows, or a transaction when multiple documents are needed). A separate relay process publishes the event, marks/tracks it as sent, and retries on failure.

If the outbox lives in another collection, use an appropriate transaction to avoid a gap between writing the source and writing the outbox. Publishing a message only after the transaction commits still leaves a crash window where the notification can be lost.

Event delivery pipelines can emit duplicates. Design consumers for **at-least-once delivery** with idempotent updates and version comparisons; never rely on assuming "messages always arrive exactly once."

### 8.5. Change Streams as a Change-Tracking Option

MongoDB provides **change streams** on supported topologies (such as replica sets and sharded clusters), allowing applications to observe changes occurring in a collection or database:

```javascript
// Observation example in mongosh on a topology supporting change streams.
const stream = db.users.watch([
  { $match: { operationType: "update" } }
]);

while (stream.hasNext()) {
  const change = stream.next();
  printjson(change);
}
```

Change streams support **resume tokens** to continue after disconnects under suitable conditions. They do not automatically update copies for you, apply business logic, or eliminate deduplication, lag handling, or reconciliation. When a source document changes across many fields, the consumer still must identify precisely which copied fields need syncing.

In addition, you must manage token lifecycle, watch scope, permissions, lag, and oplog retention window. If a consumer stops long enough that resuming fails, the application needs a **full resync workflow from the source of truth**.

## 9. Reconciliation: An Essential Step Under Eventual Consistency

Even a healthy queue can miss copies due to bugs, newly inserted documents lacking proper versions, expired events, or interrupted update batches. Therefore, synchronized data needs **reconciliation**:

1. Scan copies whose `sourceVersion` is lower than the source of truth's version.
2. Read the current value from the source.
3. Update copies with a version condition to avoid overwriting newer data.
4. Record drift count, maximum lag, and processing errors.
5. Repeat until the committed consistency target is met.

Example checking drift between the source and a copy in another collection using aggregation:

```javascript
db.posts.aggregate([
  {
    $lookup: {
      from: "users",
      localField: "authorId",
      foreignField: "_id",
      as: "sourceUser"
    }
  },
  { $unwind: "$sourceUser" },
  {
    $match: {
      $expr: {
        $lt: [
          "$authorPreview.version",
          "$sourceUser.version"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      authorId: 1,
      previewVersion: "$authorPreview.version",
      sourceVersion: "$sourceUser.version"
    }
  }
]);
```

The pipeline above demonstrates **identifying copies whose version is behind the source**, assuming the schema initializes version fields. In large production systems, design batching, indexes, pagination, and resource throttling rather than scanning two full collections frequently. Also handle copies missing `version`, deleted source documents, or mismatched types separately.

Reconciliation differs from "replaying every event from the beginning": it compares **current state** and repairs drift even when event history is incomplete.

## 10. Consistency Between Business Copies and Replica Set Replication

Two consistency dimensions often interact simultaneously:

**Dimension A: across business documents.** Are `users.displayName` and `posts.authorPreview.displayName` in agreement?

**Dimension B: across MongoDB nodes.** Has a secondary applied the write just committed on the primary? Do reads observe majority-committed data?

Example:

```text
users.displayName = "Mai Nguyen"  [source of truth]
        |
        | unprocessed event
        v
posts.authorPreview.displayName = "Mai"  [stale business copy]

Replica set for users collection:
    PRIMARY  ---> SECONDARY A ---> SECONDARY B
         (node data replication mechanism)
```

Even after the `users` record is majority-acknowledged on the replica set, `posts.authorPreview` can still be stale because the consumer hasn't updated it yet. Conversely, a business copy may be up to date while a read routed to a lagging secondary returns older data.

### 10.1. What Does `writeConcern` Confirm?

```javascript
db.runCommand({
  update: "users",
  updates: [{
    q: { _id: "U01" },
    u: { $set: { displayName: "Mai Nguyen" } }
  }],
  writeConcern: { w: "majority" }
});
```

`w: "majority"` requires acknowledgment from a majority of data-bearing replica set members. It protects writes against failover loss, yet **does not mean every document holding a copy of that name has been updated**.

### 10.2. `readConcern` and `readPreference` Do Not Replace Business Sync

`readPreference` chooses where reads go, such as primary or secondary. `readConcern` controls data visibility guarantees (`local`, `majority`, and other modes depending on context). Even with `readConcern: "majority"`, you will still see a stale `posts.authorPreview` if the business sync job hasn't run.

If business logic requires "immediately after a rename, every article page must display the new name," options include:

- Reading the name directly from `users` on freshness-sensitive read paths.
- Bounding within a transaction if copy count is small.
- Or adjusting the product requirement to accept eventual consistency with a quantified lag SLO.

You cannot solve this boundary solely by tweaking `readConcern` or `writeConcern`.

## 11. Alternatives to Duplication and When to Use Them

### 11.1. Use `$lookup` Instead of Maintaining Heavily Updated Copies

If an author's name changes frequently while post count is huge, a `$lookup` query using an indexed author key can be simpler than massive fan-out updates. Accept read cost to reduce staleness risk and write fan-out.

```javascript
db.posts.aggregate([
  { $match: { published: true } },
  { $sort: { publishedAt: -1 } },
  { $limit: 20 },
  {
    $lookup: {
      from: "users",
      localField: "authorId",
      foreignField: "_id",
      as: "author"
    }
  },
  { $unwind: "$author" }
]);
```

In this example, filtering, sorting, and limiting reduce the number of posts enriched with author info, and `$lookup` can use the `_id` index on `users`. However, validate the pipeline against real access patterns, data, and indexes; placing `$limit` before joining is only valid when screen logic truly wants the top 20 posts first before enriching author details.

### 11.2. Storing Pre-Computed Summaries

A dashboard might need daily revenue totals. Computing them across the entire orders collection on every view can be expensive, so the system maintains a summary document:

```javascript
{
  _id: "2026-10-20",
  paidOrderCount: 1520,
  revenue: NumberDecimal("248000000"),
  calculatedAt: ISODate("2026-10-20T23:59:00Z")
}
```

This is the **computed pattern / materialized result**: derived totals from orders stored separately for fast reads. Maintaining it requires careful handling of cancellations/refunds, late-arriving order updates, error recomputation, and period close cutoffs. For incremental additions, `$inc` provides single-document atomicity, but does not prevent **double-counting duplicate events**. Track event IDs, versions, or run periodic recomputation.

### 11.3. Copying Only a Small Subset

An article screen only needs the three most recent comments. You can store a bounded `recentComments` array along with `commentCount`, while full comments live in `comments`. When a comment is edited or deleted, define a policy for updating the preview and count; never let the preview array grow unbounded.

Example using `$push` with `$slice` to cap stored elements when input ordering is explicitly designed:

```javascript
db.posts.updateOne(
  { _id: "POST01" },
  {
    $push: {
      recentComments: {
        $each: [{ id: "CM10", content: "Easy-to-understand example" }],
        $position: 0,
        $slice: 3
      }
    }
  }
);
```

This command only manages the **preview**; it does not automatically insert the comment document into `comments`. If business rules require both writes as one unit, use a transaction or a suitable recovery mechanism.

## 12. Failure Patterns and Prevention

| Scenario | Common Cause | Design Countermeasure |
|---|---|---|
| Author name fails to update on some posts | Partial `updateMany` or consumer crash | Idempotent retries, progress tracking, reconciliation |
| Old name overwrites new name | Out-of-order event processing | Monotonic version, apply only newer versions |
| Rename succeeds but no event is emitted | Process crashes after writing source | Outbox inside the same atomic boundary |
| Event processed twice | At-least-once delivery or retries | Deduplicate by event ID/version; idempotent writes |
| Like total drifts | Concurrent read-modify-write without conditions | Use `$inc`, source constraints, deduplicate events |
| Old orders change price when catalog updates | Confusing historical snapshot with synced copy | Use `unitPriceAtPurchase` and never sync with `currentPrice` |
| Access control screen shows stale permissions | Security decision relying on eventual copy | Check canonical source or use a strongly consistent read path |
| Document grows too large | Unbounded embedded array | Separate collection, reference, or bounded subset |
| Rename triggers tens of thousands of updates | High fan-out on a shared attribute | Consider reference + `$lookup` instead of copying |
| Secondary does not yet show new data | Replication lag | Understand `readPreference`, `readConcern`, sessions, and consistency needs |

## 13. Designing Denormalization from Real Requirements

Never pre-decide that "one screen must map to one document." Instead, follow these steps:

**Step 1: List common read operations.** Which fields does each screen need, at what frequency, with what pagination/sorting, and how fresh must they be?

**Step 2: List write operations.** Which fields change frequently? How many documents does one change affect? Should historical data change when the source changes?

**Step 3: Identify atomic boundaries.** Which fields must update together? If confined to one bounded-size document, embedding can work. If touching very many independent documents, evaluate copying carefully.

**Step 4: Designate the source of truth.** Which data is canonical, which is a snapshot, which is a display copy, and which is a computed result? Name fields to reflect their true meaning.

**Step 5: Choose maintenance strategies.** No updates for snapshots; single-document atomic updates; transactions for small sets of related documents; or event-driven + versioning + reconciliation when lag is acceptable.

**Step 6: Design recovery paths.** If a request times out, a transaction needs retrying, a consumer receives duplicate events, or events are dropped, how does data return to a valid state?

**Step 7: Measure on realistic data.** Track read latency, `explain` plans, document/index sizes, fan-out update counts, sync lag, and unreconciled record counts.

### 13.1. Decision Example for an E-Commerce Application

| Attribute | Source of Truth | Copied? | Synced After Order Creation? |
|---|---|---|---|
| Current price | `products.currentPrice` | May be cached for display | Per cache refresh policy |
| Price at purchase | Price locked during checkout | Stored in `orders.items.unitPriceAtPurchase` | **No**, this is a snapshot |
| Shipping address | Address chosen at confirmation | Stored in `orders.shippingAddress` | Does not auto-change with customer profile |
| Current inventory status | Inventory system | Read/write at inventory authority | Never rely on lagged snapshots to ship stock |
| Product name on order | Info at purchase time | `productNameAtPurchase` | Not necessarily, per invoice/history rules |
| Order total | Line prices and rules at purchase | Stored in order document | Must match locked transaction, never recompute from new prices |
| Current customer info on dashboard | `customers` | May copy select fields | Yes, if UI requires freshness; quantify lag |

A sound model can use both **references** and **snapshots** in the same order:

```javascript
{
  _id: "O1001",
  customerId: "C01",
  customerNameAtPurchase: "Nguyen An",
  items: [{
    productId: "P01",
    productNameAtPurchase: "Mechanical Keyboard",
    unitPriceAtPurchase: NumberDecimal("1200000"),
    quantity: 2
  }],
  grandTotalAtPurchase: NumberDecimal("2400000"),
  placedAt: ISODate("2026-10-01T09:00:00Z")
}
```

`customerId` and `productId` preserve lookup capability to current entities; the `AtPurchase` fields preserve transaction state. **Keeping both references and explicit snapshots** is far clearer than copying fields without defining update rules.

## 14. Self-Practice Exercises

### Exercise 1 — Choose Embed, Reference, or Partial Copy

Design MongoDB models for these entities:

- A `course` has many `lessons`, and each lesson has a moderate number of sections.
- A `video` has millions of `comments`.
- A `user` has hundreds of thousands of `posts`, and each post card needs the author's avatar and name.

For each entity, analyze document growth potential, read frequency, shared-data update frequency, and atomic update boundaries before choosing a representation.

### Exercise 2 — Predict State After an Update

Suppose:

```javascript
// authors
{ _id: "A01", displayName: "Mai" }

// posts
{ _id: "P01", authorId: "A01", authorPreview: { displayName: "Mai" } }
{ _id: "P02", authorId: "A01", authorPreview: { displayName: "Mai" } }
```

The application runs:

```javascript
db.authors.updateOne(
  { _id: "A01" },
  { $set: { displayName: "Mai Nguyen" } }
);
```

Explain why `posts.P01` and `posts.P02` can still display `"Mai"`. If all three documents must update as one atomic group, what boundary is needed? If there were one million posts, what alternative approach would you take?

### Exercise 3 — Late Events and Versioning

Two events:

```text
UserNameChanged(U01, version=101, name="Mai A")
UserNameChanged(U01, version=102, name="Mai B")
```

The consumer receives `102` before `101`. Design an update filter that applies an event only if `incomingVersion > storedVersion`. Explain why using only `$set: { displayName: ... }` can go wrong, and how copies missing `version` should be initialized or reconciled.

### Exercise 4 — Distinguish Two Types of Consistency

A new order is confirmed with `writeConcern: "majority"`. However, the daily order stats dashboard still shows the old count. Determine:

1. What guarantee did majority write concern provide?
2. Why can the denormalized summary document still lag?
3. When should eventual consistency be accepted for a dashboard?
4. If lag cannot be tolerated, how must the operation boundary or read path change?

### Exercise 5 — Design a Recovery Workflow

Propose a mechanism allowing a system that syncs author names across thousands of post copies to recover when:

1. Source write succeeds, but the process crashes before emitting the event.
2. The consumer updates half the posts and then loses connection.
3. An older version event arrives after a newer version event.
4. The consumer is down long enough that the change stream resume token expires.
5. A new post is created while the sync job is running.

Describe the source of truth, versioning, replay mechanism, idempotent writes, and reconciliation. You do not need to build an entire queue system to explain the recovery path accurately.

## 15. Design Principles to Remember

**Denormalization is a conditional choice driven by access patterns.** It can reduce joins and speed up reads, at the cost of higher write overhead and stale copy risks.

**Historical copies are not live copies.** Prices on an order are snapshots meant to stay fixed; a user's current display name may need synchronization. Field names and update contracts must distinguish the two.

**Atomicity has boundaries.** Updating one document is atomic; an `updateMany()` does not form a cross-document transaction; multi-document transactions must be used deliberately.

**Asynchronous sync requires a recovery path.** Only a clear source of truth, versioning, idempotent retries, outbox/change streams where appropriate, and reconciliation bring the system back to a valid state after failures.

**MongoDB replication does not solve business denormalization.** A replica set copies data across members; the application still decides how to keep duplicated fields synchronized across distinct documents. Understanding both layers lets you design MongoDB models that achieve fast reads while preserving data invariants.
