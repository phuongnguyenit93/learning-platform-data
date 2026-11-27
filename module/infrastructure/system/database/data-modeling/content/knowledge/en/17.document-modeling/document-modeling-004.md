# Nested Data, Arrays, and the Risk of Unbounded Growth

## 1. The Core Problem: Convenient Structures Today Can Become Bottlenecks Tomorrow

The **document model** allows a single document to hold multiple layers of objects and arrays, typically represented in JSON or a similar format. This maps closely to the structures applications use to render data: an order contains an address and line items; a post contains an author and tags; a course contains lesson summaries.

However, not every piece of data that “belongs to” an entity should be placed directly inside that entity's document. In particular, **arrays can grow continuously**, nested objects can contain huge payloads, and concurrent writes to child elements can pile onto the same document.

This lesson belongs to the **Document Modeling** chapter of **DATABASE_DATA_MODELING**: building the skill to turn business requirements into an explicit data model—choosing entities, relationships, constraints, keys, indexes, and physical structures so data remains evolvable and testable. The focus is on understanding **nested data**, **arrays**, **size bounds**, and the warning signs that call for splitting data.

After studying this lesson, you will be able to:

- Read and design nested objects, scalar arrays, and object arrays with unambiguous semantics.
- Distinguish **bounded** arrays from arrays at risk of **unbounded** growth.
- Estimate document size as well as read, write, and indexing costs before data scales up.
- Spot common query and update mistakes involving nested arrays.
- Choose among embedding, referencing, retaining only a recent subset, bucketing, or storing history separately.
- Validate choices through access paths, business constraints, load testing, and migration plans.

## 2. Common Nested Structures

### 2.1. Nested Objects

Nested objects group semantically related attributes:

```json
{
  "orderId": "ORD-041",
  "shippingAddress": {
    "recipientName": "Nguyen An",
    "city": "Da Nang",
    "district": "Hai Chau",
    "street": "12 Sample Street"
  },
  "currency": "VND",
  "status": "DRAFT"
}
```

`shippingAddress` is a structured value belonging to the order. The address at order placement may need to remain immutable so that changing a customer's default address does not rewrite delivery history.

Nested objects are useful when fields are tightly related, share a lifecycle, or are usually read and written together. However, nesting too deeply complicates field paths, queries, validation, and schema evolution; depth limits and supported data types depend on the database engine.

### 2.2. Arrays of Scalar Values

```json
{
  "productId": "PRD-017",
  "tags": ["database", "backend", "design"],
  "supportedLanguages": ["vi", "en"]
}
```

Arrays are appropriate when an attribute is multi-valued. Specify **whether the array is ordered**, whether duplicates are allowed, and whether element count is bounded.

For example, `supportedLanguages` may behave as a deduplicated set of languages, whereas `imageOrder` has positional significance. If the requirement is “each value appears at most once,” the application needs validation rules or idempotent/set-based write operators; a JSON array does not enforce uniqueness on its own.

### 2.3. Arrays of Objects

```json
{
  "orderId": "ORD-041",
  "items": [
    {
      "lineId": "L-01",
      "productId": "PRD-017",
      "quantity": 2,
      "unitPriceMinor": 125000
    },
    {
      "lineId": "L-02",
      "productId": "PRD-088",
      "quantity": 1,
      "unitPriceMinor": 40000
    }
  ],
  "itemsTotalMinor": 290000
}
```

Each element in `items` groups multiple fields belonging to the same line item. A `lineId` provides stable identity when reordering or updating items. Even though `items` is embedded inside the order, `productId` can still serve as a reference key to the current product catalog.

**Important:** when checking multiple conditions on an array element, ensure those conditions apply to the **same element**; otherwise, queries may produce false matches. Section 6 illustrates this.

### 2.4. Arrays Nested in Objects, Objects Nested in Arrays

Models can span multiple levels:

```json
{
  "courseId": "CRS-011",
  "modules": [
    {
      "moduleId": "M-01",
      "title": "Data Foundations",
      "lessons": [
        { "lessonId": "L-01", "title": "Entities" },
        { "lessonId": "L-02", "title": "Relationships" }
      ]
    }
  ]
}
```

This structure is convenient when module and lesson lists are short, stable, and usually displayed together. But if each lesson has lengthy body content, version history, independent editing permissions, or if a course has thousands of lessons, embedding all content across multiple nested layers may be unsuitable.

Treat nesting layers as **a data-boundary decision**, not merely JSON formatting.

## 3. When Is Embedding Reasonable, and When Do Arrays Become a Risk?

A child component is a good candidate for embedding when most of the following hold:

1. It is a dependent part of the parent document without a significant independent lifecycle.
2. It is usually read together with the parent document.
3. It is usually modified with the parent document or requires atomic updates alongside the parent.
4. Both element count and child size have a **reliable business bound**.
5. Concurrent writes to child elements do not turn the parent document into a hotspot.
6. Paginating, filtering, deleting, or enforcing separate permissions per element is not a primary requirement.

For instance, an order with at most 60 line items, where each item is small metadata and the detail screen always displays all items: `items` is usually a good fit for embedding.

Conversely, if a post can receive hundreds of thousands of comments, each added and moderated independently, this structure is suspect:

```json
{
  "postId": "POST-101",
  "title": "Data Modeling",
  "comments": [
    { "commentId": "C-001", "text": "First comment" }
  ]
}
```

A brand-new post may start with one comment, but over years the `comments` array can grow large enough to degrade performance or exceed document limits. Needing to paginate, sort, and moderate comments further signals that they have their own access path.

### 3.1. Distinguishing “One-to-Many” from “Embeddable Array”

| Business Relationship | Typical Cardinality | Initial Recommendation | Deciding Factor |
| --- | --- | --- | --- |
| Order → finalized shipping address | One | Embed object | Lifecycle tied to order |
| Order → line items | Many, usually bounded | Embed array | Read/written with order, line count cap |
| Post → comments | Grows over time | Reference separate documents | Unbounded, pagination, independent writes |
| Course → lesson content | Potentially large | Reference or hybrid | Content size and independent publishing |
| User → notifications | Continuous growth | Store separately, embed at most a few recent items | Write load, retention, pagination |
| Device → telemetry events | Continuous, high rate | Separate documents or bounded buckets | Volume, write rate, time-range queries |
| Product → 8 images | Few, but large binary payloads | Embed metadata, store files separately | Byte size, file lifecycle |

**One-to-many cardinality alone is not enough to decide.** Always inspect element byte size, growth rate, mutation frequency, business rules, and query patterns.

## 4. Why Do Unbounded Arrays Cause Problems?

### 4.1. Exceeding Document Size Limits

Some document databases enforce explicit limits on maximum document size and nesting depth. These limits depend on the product and version; check the official documentation of your deployed engine. Even before hitting hard limits, an application can suffer excessive latency, memory consumption, or network transfer costs.

A simple estimation formula:

```text
B_document ≈ B_fixed + N × B_element + B_overhead

B_fixed     : bytes for parent-level fields
N           : number of elements in the array
B_element   : average bytes per element
B_overhead  : metadata, field names, encoding tags, padding/slack
```

This formula helps assess trends; it **does not replace measuring real serialized documents**. JSON, BSON, on-disk compression, key names, UTF-8 string lengths, and index formats all incur different overhead.

Suppose a device emits 2,400 events/day. Assume each serialized event takes roughly 600 bytes:

- One day: `2,400 × 600 = 1,440,000 bytes`, roughly **1.37 MiB**.
- Thirty days: `43,200,000 bytes`, roughly **41.2 MiB**.
- Ninety days: `129,600,000 bytes`, roughly **123.6 MiB**.

These are **design assumptions**, before counting overhead, fixed fields, and traffic bursts. If you set an internal operational budget of 2 MiB per document, an ever-growing array crosses that threshold in roughly a day and a half. When 90 days of history are required, a single document is clearly the wrong boundary.

### 4.2. Oversized Documents Waste Resources on Read Paths

Suppose a profile page displays only the username and 10 recent notifications. If `users` embeds all 50,000 notifications, queries must process a massive structure even though the UI needs only a few fields.

Projections can trim the returned payload depending on engine capabilities, but they do not eliminate all storage, processing, cache, and update costs of a bloated document. Furthermore, many APIs accidentally return the entire document if query authors forget to project fields.

### 4.3. Unbounded Arrays Complicate Querying and Pagination

A long array may need multi-condition filtering, date sorting, and pagination. Database engines vary in how well they support this; usually it is much harder to manage than indexing separate child documents.

To fetch page 101 of a post's comments, an API should not have to load or scan the entire comment array just to skip the first 3,000 elements.

### 4.4. The Parent Document Can Become a Write Hotspot

Many users commenting concurrently on the same post all mutate the same `posts` document. Even if each comment is small, concentrated concurrent writes can trigger contention, retries, or throughput drops. The exact risk depends on the engine's write concurrency model and how the application updates arrays.

A dataset with 20,000 updates/minute spread across 20,000 documents behaves completely differently from 20,000 updates/minute concentrated on **one** document. Therefore, measure **write distribution by document key**, not just aggregate write volume.

### 4.5. Migration Gets Harder Once Arrays Grow Large

If comments are initially embedded and later need splitting, the system must handle legacy documents, new comments arriving during migration, duplicate IDs, consistency, and older app versions still reading the old layout. Splitting early along a predictable boundary is usually far easier than fighting an incident when documents hit limits.

## 5. Not Just Arrays: Subtle Growth Patterns

Historical arrays are the most obvious sign, but nested data has other growth patterns:

- **Objects with dynamic keys:** a `countersByUserId` map adding one key per user grows unboundedly even without an array.
- **Dynamic nesting depth:** recursively embedded category trees or comment threads can exceed depth budgets.
- **Accumulating strings:** an `auditText` field appending events to a single string grows continuously.
- **Arrays with wildly varying element sizes:** a 100-character comment and a base64-encoded attachment differ vastly in byte size.
- **Multi-way duplication:** each document embeds bidirectional reference lists, and those lists are copied elsewhere, inflating storage and sync overhead.

Example anti-pattern with dynamic keys:

```json
{
  "postId": "POST-101",
  "likesByUser": {
    "USR-001": true,
    "USR-002": true,
    "USR-003": true
  }
}
```

As the number of likers grows, `likesByUser` develops the same problems as an unbounded array. To track whether a user liked a post alongside total like count, store `likes` as link documents `(postId, userId)` paired with a controlled derived counter.

## 6. Querying Nested Arrays: Right Element, Right Condition

The syntax below **uses MongoDB for illustration**. Other document databases have different query languages and semantics. The goal is to understand the semantics, not memorize one product's syntax.

### 6.1. Path-Based Queries

Given the document:

```json
{
  "orderId": "ORD-041",
  "items": [
    { "lineId": "L-01", "sku": "BOOK", "quantity": 1 },
    { "lineId": "L-02", "sku": "PEN", "quantity": 5 }
  ]
}
```

A query:

```javascript
db.orders.find({
  "items.sku": "BOOK",
  "items.quantity": { $gte: 3 }
});
```

can match the document above, even though the `BOOK` line item only has quantity 1. Why? Because the two array-path predicates can be satisfied by **two different elements**.

If the requirement is “find orders with **a BOOK line item whose quantity is at least 3**,” use an operator that binds predicates to the same element:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK",
      quantity: { $gte: 3 }
    }
  }
});
```

The sample document will **not** match. This distinction is critical when filtering product catalogs, permissions, events, or statuses inside object arrays.

### 6.2. Projection Is Not Child-Element Pagination

```javascript
// Return only required fields at the document level.
db.orders.find(
  { orderId: "ORD-041" },
  { _id: 0, orderId: 1, status: 1, itemsTotalMinor: 1 }
);
```

Projection avoids returning `items` when a list screen does not need them. If thousands of child items need independent filtering, sorting, pagination, and search, **splitting children into separate documents** usually yields a far more manageable query model.

Some engines offer array-slicing or array-aggregation operators, but these should not be treated as a general cure for unbounded arrays.

### 6.3. Indexes on Nested Fields and Arrays

In some document databases, you can create indexes on nested field paths:

```javascript
// Example for filtering orders by line-item SKU.
db.orders.createIndex({ "items.sku": 1 });

// With comments split into separate documents:
db.comments.createIndex({
  postId: 1,
  moderationStatus: 1,
  createdAt: -1,
  _id: -1
});
```

An index on an array may be a **multikey** index or equivalent mechanism; one document generates multiple index entries, increasing index size and write maintenance cost. Engines also impose restrictions on compound indexes spanning multiple arrays.

Inspect execution plans and test queries on large datasets, especially for predicates requiring **same-element** matching, multi-level filters, and low-selectivity fields. Never index every path simply because it appears in the JSON.

## 7. Updating Arrays: Atomicity, Contention, and Invariants

### 7.1. Element-Level Mutations

Example MongoDB syntax:

```javascript
// Append a line item to the order's array.
db.orders.updateOne(
  { orderId: "ORD-041", status: "DRAFT" },
  {
    $push: {
      items: {
        lineId: "L-03",
        sku: "RULER",
        quantity: 1,
        unitPriceMinor: 15000
      }
    }
  }
);

// Remove a line item by its stable identifier.
db.orders.updateOne(
  { orderId: "ORD-041", status: "DRAFT" },
  { $pull: { items: { lineId: "L-03" } } }
);
```

This illustrates array update syntax, **not a complete valid order-editing workflow**. If `itemsTotalMinor` is stored, adding or removing a line item must update the total consistently and enforce business rules; separate uncoordinated updates can corrupt data. Also check duplicate `lineId` values, order status, and edit permissions.

### 7.2. Avoid Read–Modify–Overwrite of the Entire Document

Risky pattern:

1. Process A reads document version 5.
2. Process B reads the same document version 5.
3. A modifies the array and overwrites the entire document.
4. B modifies another element and overwrites using the stale copy it read earlier; A's change may be lost.

Prefer targeted field or element updates, and apply **optimistic concurrency control** when invariants must be protected:

```javascript
const result = db.orders.updateOne(
  {
    orderId: "ORD-041",
    status: "DRAFT",
    version: 5
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 },
    $currentDate: { confirmedAt: true }
  }
);

if (result.matchedCount === 0) {
  // Document changed; re-read and decide business handling.
}
```

Some database engines guarantee document-level atomic writes, though exact guarantees and conflict mechanics vary. **An atomic single-document update does not automatically protect the whole business process** when inventory, payment, or other documents are involved.

### 7.3. Capping Summary Arrays at Write Time

If you only need to keep the 20 most recent notifications for quick display, you can cap the array on write:

```javascript
// The array on the profile is only a preview capped at 20 items.
db.users.updateOne(
  { userId: "USR-042" },
  {
    $push: {
      recentNotifications: {
        $each: [
          {
            notificationId: "N-900",
            type: "COURSE_UPDATE",
            createdAt: "2026-11-22T08:00:00Z"
          }
        ],
        $slice: -20
      }
    }
  }
);
```

In this example, `$slice: -20` keeps the last 20 elements after appending. **This is not a full history store**: older notifications are evicted from the preview. If users need full history, store the primary source in a separate `notifications` collection and treat `recentNotifications` as a bounded copy with sync and reconciliation rules.

If items can arrive late or out of chronological order, do not assume “the last 20 appended elements” equals “the 20 latest events by event time”; specify event-time sorting and an appropriate update strategy.

### 7.4. Never Use an Array as a System-Wide Uniqueness Constraint

Pushing into an array does not inherently prevent two duplicate business requests, especially when elements have multiple attributes or structural changes. For rules like “one user can like a post only once,” separate `likes` documents with a unique index on `(postId, userId)` usually express the invariant much more clearly.

## 8. Alternatives to Unbounded Arrays

### 8.1. Splitting Child Elements into Separate Documents

Instead of a post embedding every comment:

```text
posts
  { postId, title, authorId, commentCount }

comments
  {
    commentId, postId, authorId,
    text, createdAt, moderationStatus
  }
```

Benefits:

- Each comment has its own identity, lifecycle, and authorization rules.
- Comments can be filtered, sorted, and paginated by `postId`.
- Adding a comment does not always force writing to the post document.
- History can be archived or purged under an independent retention policy.

In return, the detail screen retrieves the post and comments via multiple queries or engine-supported joins. If `commentCount` lives on `posts`, define the source of truth and how to handle drift, duplicate writes, or delayed events.

### 8.2. Embedding a Bounded Subset

A document can embed 3 featured reviews or the 20 most recent notifications while storing the full dataset separately:

```json
{
  "postId": "POST-101",
  "title": "Data Modeling",
  "commentPreview": [
    { "commentId": "C-200", "text": "Clear examples" },
    { "commentId": "C-199", "text": "Is there a follow-up article?" }
  ],
  "commentCount": 1248
}
```

Specify:

1. Maximum number of items in the preview.
2. Selection criteria: newest, most helpful, moderated, or another ranking rule.
3. Source of truth and events that trigger preview updates.
4. Acceptable synchronization lag.
5. How deletions or hiding of a previewed comment are handled.

Never let a preview turn into “the complete list” simply because counts are small on day one.

### 8.3. Time-Based and Size-Bounded Bucketing

Time-series data can be grouped into documents by device/day/hour or by event count:

```json
{
  "deviceId": "DEV-018",
  "bucketStart": "2026-11-22T08:00:00Z",
  "part": 0,
  "events": [
    { "at": "2026-11-22T08:00:05Z", "value": 28.5 },
    { "at": "2026-11-22T08:00:10Z", "value": 28.8 }
  ],
  "eventCount": 2
}
```

An hourly bucket is **not guaranteed** to stay bounded in practice: a malfunctioning device can emit millions of events in one hour. Therefore, bound buckets by **both time and element/byte count**, rolling over to a new `part` before exceeding the budget.

Trade-offs: fewer documents read for a time window, but updating the active bucket can become a hotspot; late-arriving data must land in the right bucket; deep per-event filtering can be harder; capping limits under concurrent writers requires care. Always benchmark realistic load before choosing this pattern.

### 8.4. Separating Hot Data from Archival Data

Recent events are queried frequently; older events mainly serve audits or reporting. You can use:

- An operational collection for recent data, indexed for online queries.
- Long-term archive storage or an analytical store for older data.
- Defined retention/deletion policies, export formats, lookup paths, and reconciliation rules.

Time-based archival must obey business and legal requirements; never automatically purge critical logs just because they bloat documents.

### 8.5. Metadata in Documents, Binary Payloads in Appropriate Storage

For large images, videos, or attachments, usually embed only metadata and identifiers:

```json
{
  "productId": "PRD-017",
  "images": [
    {
      "assetId": "ASSET-01",
      "alt": "Front view of product",
      "position": 1
    }
  ]
}
```

The image bytes themselves can live in object storage or a suitable file store. Design access control, file lifecycle, deletion policies, and cleanup of unreferenced assets.

## 9. Schema Design and Constraints for Nested Structures

Flexible documents **do not mean no data contract**. When designing nested arrays and objects, define:

| Area | Example Rule |
| --- | --- |
| Data types | `items` must be an array of objects; `quantity` is a positive integer |
| Required fields | Every line has `lineId`, `productId`, `quantity` |
| Size bounds | `items` array has at most 60 lines per business rules |
| Allowed values | `status` belongs to the defined set of states |
| Uniqueness | No two lines share the same `lineId` within one order |
| Empty states | Distinguish missing field, `null`, and empty array `[]` |
| Invariants | Totals match line items and adjustments |
| Versioning | `schemaVersion` for structure, `version` for concurrent updates |
| Security | Never expose sensitive child fields in public APIs |

### 9.1. Missing Fields, Null, and Empty Arrays

These three representations can carry different meanings:

```jsonc
{ "userId": "U-1" }                        // notifications field does not exist yet
{ "userId": "U-1", "notifications": null } // Field exists with null value
{ "userId": "U-1", "notifications": [] }   // Explicitly known to be an empty list
```

Applications and query engines may treat them differently. Pick a consistent convention so APIs and data migrations never misinterpret them, especially when rolling out new fields.

### 9.2. Nested Elements Need Identifiers for Updates

If an object array can be reordered, positional updates like “the third element” break under concurrent inserts or deletes. Give every significant element a stable `lineId` and use identifier-based filters in updates supported by the database engine.

Even with element identifiers, invariants like “total equals sum of lines” must still be protected within the same atomic operation or through a proper coordination mechanism.

### 9.3. Nesting Depth Limits and Recursive Structures

Data like category trees or deeply nested reply threads can reach unpredictable depths. Structures requiring traversal, search, or independent subtree edits often fit better as separate documents with `parentId`, or a graph model if multi-hop relationship queries dominate. Choose the representation based on actual access paths.

## 10. End-to-End Case Study: Courses, Lessons, and Learner Activity

### 10.1. Business Requirements

An online learning platform has the following assumptions:

- Each course typically has 20–50 lessons; short descriptions, average lesson body 30 KiB.
- Each course can reach 100,000 learners.
- Learners emit events for viewing lessons, pausing video, and completing exercises; events accumulate daily.
- The course landing page only needs title, description, and 5 featured lessons.
- The lesson study screen needs the content of one specific lesson and the learner's progress.
- Instructors can edit a single lesson independently and publish a new version.
- Analytics reports must aggregate millions of events per day.

### 10.2. Problematic Design

If the `course` document embeds all lesson content, all learner progress, and every viewing event, it grows rapidly and funnels heavy writes into one document. Specifically:

- Just 50 lessons × 30 KiB equals roughly **1,500 KiB** of content alone.
- If 100,000 learners have states across 50 lessons, that produces **5,000,000 progress entries**.
- Activity events have no natural upper bound when retained long-term.

Being easy to sketch in JSON at first does not prove a structure works at scale.

### 10.3. Lifecycle-Aligned Boundary Design

```text
courses
  {
    courseId, title, description, authorId,
    featuredLessons: [{ lessonId, title, position }], // max 5
    lessonCount, schemaVersion
  }

lessons
  {
    lessonId, courseId, title, content,
    position, publishedVersion
  }

lessonProgress
  {
    learnerId, lessonId, state,
    completedAt, version
  }

learningEvents
  {
    eventId, learnerId, lessonId, eventType,
    occurredAt, receivedAt, payload
  }
```

Rationale:

- **Embed the 5-lesson preview** because it is tiny and always read with course info. Define an update rule when lesson titles or positions change.
- **Lesson content** lives in `lessons` documents for independent publishing, reading, and editing.
- **Progress** is keyed per learner–lesson pair because many learners write concurrently and queries filter by learner and lesson. A per learner–course progress document may be considered if lesson count is strictly bounded and read patterns justify it.
- **Events** are separate records or bounded buckets due to high growth; analytical data can be synced to a dedicated aggregation engine.
- **Do not embed all progress or activity inside `courses`.**

### 10.4. Keys and Indexes to Verify

| Access Path | Keys / Predicates | Suggested Index or Constraint |
| --- | --- | --- |
| Lessons in a course | `courseId`, sort `position` | `(courseId, position)` |
| Single lesson content | `lessonId` | Unique identifier key |
| Learner's lesson progress | `learnerId, lessonId` | Unique composite key for current progress |
| All progress for a learner | `learnerId` | Index starting with `learnerId` |
| Learner events by day | `learnerId, occurredAt` | Query-aligned index, pagination policy |
| Multi-course / monthly reports | Large time-based event set | Consider analytical dataset or derived summaries |

These are logical suggestions; exact field order and index types must be verified against real queries and the chosen engine. In multi-tenant systems, include `tenantId` in predicates, unique keys, and access boundaries.

### 10.5. Questions That Could Change the Design

- Is reading **all** 50 lesson progress states in a single fetch required? What is the concurrent write rate per learner?
- How long must learning events be retained, and what personal data deletion rules apply?
- When an instructor publishes a course version, must learners see a consistent snapshot across all lessons?
- Do late-arriving or duplicate events skew reports? Do we need event IDs and deduplication?
- Are detailed event lookups as common as aggregate reports?

These requirements determine whether to split further, bucket, or introduce a dedicated read model.

## 11. Migrating from a Large Array to Separate Documents

Suppose a legacy system stored comments in `posts.comments`. When splitting them into a `comments` collection, a principled safe migration plan includes:

1. **Design the target schema:** stable `commentId` key, `postId`, author, status, timestamp; query indexes and appropriate unique constraints.
2. **Define the source of truth during transition:** specify the new write path, new read path, legacy app versions, and how edits arriving mid-migration are handled.
3. **Deploy compatible readers:** manage the window where both shapes coexist without displaying duplicates.
4. **Backfill data in idempotent batches:** preserve stable IDs so retries do not create duplicate comments.
5. **Catch up on ongoing changes:** ensure comments created, edited, or deleted during migration are captured.
6. **Reconcile:** compare counts, IDs, statuses, and missing records; inspect posts with the highest comment counts.
7. **Cut over reads/writes completely and remove the old structure:** only after metrics verify consistency and all relevant app versions are compatible.

If using `schemaVersion` to distinguish shapes, actually support both versions in reader and validation logic; incrementing the version number alone does not migrate payloads.

## 12. Validating Choices with Quantitative Metrics

A trustworthy design states **quantitative assumptions** rather than writing “this array is probably small.” Minimum profiling table:

| Metric | How to Determine | Why It Matters |
| --- | --- | --- |
| Child elements per parent | Median, p95, p99, max, business cap | Spots outlier documents |
| Element size | Actual encoded bytes on sample data, p95/p99 | Forecasts total document size |
| Insert/delete rate | Items/day and peak burst scenarios | Predicts when budgets are hit |
| Concurrent writes on parent | Updates concentrated per key | Identifies hotspots |
| Common queries | Fields, filters, sorts, pagination | Guides embedding/splitting and indexes |
| Storage size / nesting depth | Per engine storage format | Checks product limits |
| Retention period | Business needs and legal policy | Drives archival, deletion, bucketing |
| Invariants & sync lag | What must be immediately consistent | Shapes transactions and replicas |

Then test at least three workload profiles: typical parent, p99 parent, and plausible maximum parent; include long strings, empty arrays, missing fields, and late-arriving events. Apply realistic read/write workloads to measure:

- Median, p95, and p99 latency for reads and writes.
- Bytes read/returned and number of documents touched.
- Largest document size and total index footprint.
- Contention, failure, or update retry rates.
- Invariant preservation under concurrent writes.
- Migration cost and recovery after interruption.

There is no universal optimal number for every system. Final thresholds must come from **SLAs, queries, realistic workloads, and the target database product**.

## 13. Quick Comparison with Other Data Models

| Need | Approach Worth Considering |
| --- | --- |
| Read/write an aggregate with nested structure and bounded children | Document model with controlled embedding |
| Complex relationships requiring foreign keys and flexible joins | Relational, or document with references and appropriate constraints |
| Multi-hop traversal across network-like relationships | Graph |
| Large-scale daily/monthly event aggregation, scanning many records | Analytical warehouse or analytics-oriented structures |
| Both transactional writes and heavy historical analytics | Separate operational and analytical paths with sync and reconciliation |

These are general guidelines, not absolute product boundaries. Many relational databases support JSON; several document databases support transactions and joins. Always verify the capabilities and constraints of your specific engine version.

## 14. Applied Exercise

**Scenario:** An event management app hosts workshops. Each workshop has a title, venue, 10–30 speakers, up to 1,000 registrants, hundreds of thousands of page views, and gate ticket-scan logs. Speaker info changes infrequently; tickets can be scanned concurrently at multiple gates; page-view logs are retained for one year for analytics.

Decide whether to embed or separate: speaker list, registration data, ticket scan state, scan history, and page-view logs.

### Reasoning Guide

| Data Group | Cardinality / Size | Write Frequency | Suggested Approach |
| --- | --- | --- | --- |
| 10–30 speaker summaries | Small, bounded | Low | Embed display metadata or reference if profiles are shared |
| Registrations for 1,000 people | Bounded, but needs search by person/status | Can spike in waves | Separate `registrations` documents; unique key `(eventId, attendeeId)` per rules |
| Ticket scan state | Per registration | Concurrent across multiple gates | Write to individual ticket/registration with duplicate-scan guard |
| Scan history | Grows per business activity | High during check-in | Separate event documents with unique IDs and retention policy |
| Page-view logs | Huge growth | High, continuous | Event store / time-series / bounded buckets; do not embed in `events` |

**Additional constraint:** if speakers are registered users updating their profiles across multiple workshops, store `speakerId` and embed display summaries only if an update mechanism exists. If the event needs to preserve the program “exactly as it occurred,” keep a historical snapshot separate from current speaker profiles.

**Self-check questions:**

1. If a workshop has 30 speakers, but each profile embeds a 10 MiB PDF, is choosing to embed based solely on count 30 valid?
2. If 20,000 page views/minute write into an array on the event document, which risk hits first: storage size or write contention?
3. If the registration list is embedded and the app must find all unpaid attendees, where do filtering and pagination get difficult?
4. If only the 20 most recent scans are embedded in the workshop document, where must the authoritative history live for auditing?
5. When a ticket is scanned simultaneously at two gates at the exact same moment, what invariants and conditional updates are required?

## 15. Nested Data and Array Design Checklist

- [ ] Defined exact semantics for every object/array: ordering, duplicates, empty `[]`, `null`, and missing fields.
- [ ] Identified **business bounds** or unbounded growth risk for every array and dynamic-key object.
- [ ] Measured p50/p95/p99 and worst-case cardinality and byte sizes.
- [ ] Estimated growth rate and time until hitting the document size budget.
- [ ] Analyzed write frequency and concurrency targeting **the same parent document**.
- [ ] Listed queries that filter or paginate child elements independently.
- [ ] Verified array predicates that must apply to **the same array element**.
- [ ] Designed element keys, validation, indexes, and concurrent-update protection.
- [ ] Distinguished primary source data, historical snapshots, and bounded previews.
- [ ] Considered splitting child documents, bounded buckets, archival storage, and externalized binary files.
- [ ] Prepared a compatibility/migration plan if structures must evolve later.
- [ ] Validated with realistic data volumes and workloads, not just small toy samples.

**Key takeaway:** Nested objects and arrays let a document represent a complete business unit. Yet **any subset that grows unboundedly, or is queried or updated independently, must be evaluated as its own data boundary**. Sound decisions depend on actual size, growth rate, concurrent write load, invariants, and access paths—not merely on the initial JSON shape.
