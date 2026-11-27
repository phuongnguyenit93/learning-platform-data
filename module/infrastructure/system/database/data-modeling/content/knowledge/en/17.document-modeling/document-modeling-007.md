# Choosing Document Keys, Indexes, and Queryable Fields

## 1. From Business Requirements to Keys and Access Paths

In the **document model**, a readable JSON structure alone is not enough to prove a good data design. A document may neatly describe a course, order, or product, yet if the application cannot look up the right document, filter by common predicates, or sort lists at reasonable cost, that model will struggle at scale.

Three decisions must be designed **together**:

1. **Document keys:** how is each document identified, and is the key stable and unique within the required scope?
2. **Queryable fields:** which fields do business workflows use for lookup, filtering, sorting, pagination, aggregation, and updates?
3. **Indexes:** which auxiliary access structures does the storage engine need to serve those operations within acceptable latency and cost?

This lesson belongs to the **Document Modeling** chapter within **DATABASE_DATA_MODELING**. The module builds the skill to translate business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while weighing relational, document, graph, or analytical models against real requirements.

After this lesson, you will be able to:

- Distinguish storage keys, business keys, reference keys, and partition keys.
- Design stable identifiers, uniqueness scopes, and appropriate update/deletion rules.
- Build a **query shape** inventory from business features.
- Select single-field indexes, compound indexes, and indexes on nested fields or arrays according to dominant queries.
- Apply **projections**, stable sort orders, and cursor-based pagination where appropriate.
- Evaluate index cost via execution plans, latency, examined documents, and write overhead.
- Recognize when to change document boundaries or pick another storage model instead of adding more indexes.

## 2. Understanding Keys in the Document Model

### 2.1. Document Identifier Key

Every document needs a stable way to be identified. Some engines auto-generate an internal field or identifier; MongoDB, for example, uses `_id` as the unique identifier within each collection.

Example course document:

```json
{
  "_id": "CRS-0042",
  "tenantId": "ORG-07",
  "courseCode": "DATA-101",
  "title": "Data Design",
  "status": "PUBLISHED"
}
```

In this example, `_id` is the storage identifier; `courseCode` is a code recognizable by the business or users. These two fields may share the same value, but they **do not have to be the same**.

A good key should be:

- **Stable:** never changes simply because a title, email, display name, or list position changes.
- **Sufficiently unique:** avoids collisions within the defined business scope.
- **Reference-friendly:** child documents, APIs, and events can rely on a durable identifier.
- **Clearly governed:** specifies which service issues IDs, how duplicate requests are handled, and format constraints.
- **Free of unnecessary sensitive data:** avoid exposing emails, phone numbers, or national IDs as public keys.
- **Friendly to load distribution:** avoids creating a write hotspot if the storage engine range-partitions by key value.

### 2.2. Natural Keys vs. Surrogate Keys

A **natural key** is a business fact inherently unique by rule, such as an organization-assigned course code. A **surrogate key** is an identifier generated solely to identify a record, such as a random string or database-generated ID.

| Criterion | Natural Key | Surrogate Key |
| --- | --- | --- |
| Meaning | Meaningful to the business | Used primarily for identification |
| Mutability | May change if business rules change | Typically designed as immutable |
| Uniqueness enforcement | Requires defining scope, normalization, and uniqueness rules | Requires collision-resistant generation or uniqueness check |
| API / references | Convenient if the code is genuinely immutable | Decoupled from business code changes |
| Example | `(tenantId, courseCode)` | `courseId = "CRS-0042"` |

**Example:** `courseCode` might change from `DATA-101` to `DB-101` during a curriculum revision. If that code serves as the unique identifier across thousands of `enrollments` documents, renaming it ripples across many references. It is usually cleaner to use an immutable `courseId` and enforce a separate unique constraint on the business code.

There is no blanket rule that “every document must use UUIDs” or “every document must use natural keys.” Evaluate domain characteristics, ID generation, uniqueness, client-side ID creation, storage overhead, and write distribution.

### 2.3. Reference Keys

When two entities have independent lifecycles, a document can hold one or more reference fields:

```json
{
  "_id": "ENR-0102",
  "tenantId": "ORG-07",
  "learnerId": "USR-0045",
  "courseId": "CRS-0042",
  "status": "ACTIVE",
  "createdAt": "2026-11-18T09:00:00Z"
}
```

`learnerId` and `courseId` reference the learner and the course. In many document databases, an ID field **does not automatically enforce a foreign key** as in a relational database. Define who validates references, how target deletions are handled, how orphan references are detected, and what historical retention rules apply.

For child data, choosing between embedding and referencing still rests on **read/write units, size, cardinality, and consistency**. Key design follows from document boundary decisions.

### 2.4. Partition Keys or Shard Keys

Some engines use a key to distribute data and route queries. A partition key can differ from the document's identifier key.

For example, a multi-tenant model uses `tenantId` to isolate access. That **does not automatically guarantee** `tenantId` is a good physical partition key: one huge tenant may dominate traffic, and cross-tenant operations may fall outside convenient transaction boundaries.

When designing, ask:

- Do most queries include `tenantId` or the chosen partition key?
- Could a single key value funnel excessive reads/writes onto one partition?
- Are there business transactions spanning partitions?
- How does the engine support uniqueness constraints alongside that partition key?
- As tenants and traffic grow, will key distribution stay balanced?

**You cannot infer partitioning behavior from field names alone.** Routing capabilities and unique index rules depend on the specific product, version, and configuration.

## 3. Uniqueness Must Have a Business Scope

A common mistake is declaring “`courseCode` must be unique” without stating **unique within what scope**.

Suppose two different organizations both use code `DB-101`:

```json
{
  "tenantId": "ORG-07",
  "courseId": "CRS-0042",
  "courseCode": "DB-101"
}
```

```json
{
  "tenantId": "ORG-12",
  "courseId": "CRS-0911",
  "courseCode": "DB-101"
}
```

If business rules permit the same code in two organizations, the constraint must be **unique per `(tenantId, courseCode)` pair**, not on `courseCode` alone.

MongoDB example:

```javascript
db.courses.createIndex(
  { tenantId: 1, courseCode: 1 },
  { unique: true }
);
```

This index enforces uniqueness **within the collection and subject to the deployment configuration's capabilities**. If sharding is enabled, separately verify rules for unique indexes and shard keys.

Additional questions to specify:

- Are codes case-sensitive? Are `db-101` and `DB-101` the same or distinct?
- Are leading/trailing spaces allowed?
- Can a code be reused after a course is hidden or soft-deleted?
- How should missing or `null` fields behave in a unique index?
- When a code changes, must APIs and referencing documents update too?

If case normalization applies, enforce the rule at the write source along with appropriate *collation*. Never leave inconsistent normalization rules to individual clients.

### 3.1. Composite Keys for Business Relationships

A learner can hold at most **one active enrollment record** for the same course within the same organization:

```javascript
db.enrollments.createIndex(
  { tenantId: 1, learnerId: 1, courseId: 1 },
  { unique: true }
);
```

This constraint holds cleanly when each learner–course pair has one document and `status` tracks state transitions over time. If the domain requires recording multiple enroll/drop/re-enroll cycles as **separate historical records**, a pair-wise unique key no longer fits. In that case, use one current-state document plus historical event records, or a conditional/partial unique constraint if the engine supports the exact semantics.

Never add `status` to the unique key merely to “allow re-enrollment” if weak update guards could accidentally allow two `ACTIVE` records for the same pair.

## 4. Document Queries Before Creating Indexes

**Indexes serve queries, not field diagrams.** The first step is cataloging actual access paths from APIs, screens, and background jobs.

Sample table for a learning platform:

| ID | Business Need | Primary Filters | Sort / Pagination | Returned Fields |
| --- | --- | --- | --- | --- |
| Q1 | Open details of a course | `tenantId`, `courseId` | None | Title, description, status |
| Q2 | List published courses | `tenantId`, `status=PUBLISHED` | `publishedAt` newest first, paginated | `courseId`, `title`, `summary` |
| Q3 | List lessons in a course | `tenantId`, `courseId` | `position` ascending | `lessonId`, `title` |
| Q4 | Learner's enrollment list | `tenantId`, `learnerId` | `createdAt` newest first, paginated | `courseId`, `status` |
| Q5 | Check enrollment status | `tenantId`, `learnerId`, `courseId` | None | Enrollment status |
| Q6 | Active learner stats for a course | `tenantId`, `courseId`, `status=ACTIVE` | Optionally by time | Count or learner list |
| Q7 | Search courses by keyword | `tenantId`, status, and keywords | By relevance or date | Search results |
| Q8 | Monthly completion report | Time window, grouped by course | Multi-record aggregation | Aggregate metrics |

For each query, note **frequency**, result size, data growth rate, target latency, priority, and authorized callers. Q2 may run thousands of times per minute, whereas Q8 runs once a night; do not make the same trade-offs for both.

### 4.1. What Does a Query Shape Include?

A query shape should describe:

- **Equality filters:** `tenantId = X`, `status = PUBLISHED`.
- **Range filters:** `createdAt >= T`, `priceMinor` within bounds.
- **Sort:** `publishedAt DESC` then `_id DESC`.
- **Projection:** required return fields rather than defaulting to the whole document.
- **Limit / page:** page size and pagination strategy.
- **Aggregation:** grouping, counting, summing, or joining data.
- **Scope / security:** mandatory filters such as `tenantId` and visibility rules.

Two differently named APIs sharing the same filters, sort order, and projection can share one index. Conversely, one API with query branches that alter sort order may require evaluating separate indexes.

### 4.2. Queryable Fields Differ from Stored Fields

A lesson document may store tens of KiB of `content`, yet Q3 needs only the title. You still store `content` for the study screen; that **does not mean** putting long content fields into every index or returning them in every list endpoint.

Classify fields by role:

| Role | Example | Design Impact |
| --- | --- | --- |
| Identifier | `courseId`, `lessonId` | Keys, uniqueness, references |
| Partitioning / auth scope | `tenantId`, `visibility` | Mandatory in scoped query predicates |
| Equality filter | `status`, `learnerId` | Common candidates for index prefixes |
| Range filter | `createdAt`, `priceMinor` | Check ordering relative to equality and sort |
| Sort | `publishedAt`, `position` | Check whether index supports sort direction |
| Display | `title`, `summary` | Use projection; consider covered queries when beneficial |
| Text search | `title`, `description` | Evaluate text/search indexes or dedicated search engine |
| Aggregation | `priceMinor`, `rating` | Evaluate index, aggregation pipeline, or analytical store |
| Concurrency / state | `version`, `status` | Protects concurrent updates and state transitions |

Never add an index just because a field exists in the JSON. An index pays off only when serving an access path with concrete frequency, load, and latency requirements.

## 5. What Work Does an Index Do, and What Does It Cost?

An auxiliary index builds an access path ordered by the values of one or more fields. With the right index, the engine avoids scanning many documents or running expensive in-memory sorts. However, indexes are not free:

- Consume disk storage and memory cache.
- Must be updated whenever documents or indexed fields mutate.
- Add work to inserts, updates, and deletes.
- Require maintenance, index builds, and monitoring over the data lifecycle.
- Can cause the query planner to pick a suboptimal plan under certain data distributions.

A system with **many indexes** is not automatically faster than one with **fewer, query-aligned indexes**.

### 5.1. Single-Field Indexes

Example looking up a course by `courseId`:

```javascript
db.courses.createIndex(
  { tenantId: 1, courseId: 1 },
  { unique: true }
);

db.courses.findOne({
  tenantId: "ORG-07",
  courseId: "CRS-0042"
});
```

In an environment where `_id` holds `courseId` and is known to be globally unique across the collection, you can read directly by `_id`. Still, if business rules scope every operation to `tenantId`, enforce authorization at the application layer or in query predicates; merely knowing `_id` must never allow reading another tenant's document.

### 5.2. Compound Indexes for Filtering and Sorting

Q2: list published courses for an organization, newest first.

```javascript
db.courses.createIndex({
  tenantId: 1,
  status: 1,
  publishedAt: -1,
  _id: -1
});

db.courses.find(
  { tenantId: "ORG-07", status: "PUBLISHED" },
  { _id: 1, courseId: 1, title: 1, summary: 1, publishedAt: 1 }
).sort({ publishedAt: -1, _id: -1 }).limit(20);
```

Two equality predicates precede the sort fields. The pair `(publishedAt, _id)` establishes deterministic ordering even when multiple courses share the same publication timestamp.

**Rule of thumb:** often consider equality → sort → range when designing compound indexes, though this is not an immutable law. Actual effectiveness depends on selectivity, data skew, query shape, and the engine's query optimizer.

If Q2 has an “all statuses” branch without a `status` filter, the index above may no longer support sorting as efficiently as expected. Evaluate that query shape separately rather than assuming “having the `tenantId` prefix is enough.”

### 5.3. Field Order in Compound Indexes

These two indexes differ:

```javascript
{ tenantId: 1, learnerId: 1, createdAt: -1 }
{ createdAt: -1, learnerId: 1, tenantId: 1 }
```

They are not equivalent ways of writing the same index. For “all enrollments of learner X in organization Y, newest first,” the first index is usually the clearer candidate because it matches the equality filters before the chronological sort.

A compound index can often serve queries matching a **leading prefix**, but cannot be assumed efficient for arbitrary subsets of its fields. Always verify via execution plans.

### 5.4. Compound Indexes and Uniqueness Constraints Serve Different Goals

```javascript
// Protects one enrollment record per learner per course.
db.enrollments.createIndex(
  { tenantId: 1, learnerId: 1, courseId: 1 },
  { unique: true }
);

// Serves chronological enrollment history, newest first.
db.enrollments.createIndex({
  tenantId: 1,
  learnerId: 1,
  createdAt: -1,
  _id: -1
});
```

The first index targets **correctness**; the second targets **filtering/sorting**. Never drop a uniqueness constraint just because a list-query index exists. Conversely, do not expect a unique business-key index to magically optimize chronological queries.

## 6. Nested Fields and Arrays: Query Semantics Matter More Than Syntax

Documents allow nested objects and arrays; many engines allow path-based indexing. Yet querying an array of objects carries a trap regarding **which element satisfies each condition**.

Suppose a quiz attempt stores answers:

```json
{
  "attemptId": "ATT-017",
  "answers": [
    { "questionId": "Q-01", "isCorrect": false },
    { "questionId": "Q-02", "isCorrect": true }
  ]
}
```

This MongoDB query can match the document even though question Q-01 was answered incorrectly:

```javascript
db.attempts.find({
  "answers.questionId": "Q-01",
  "answers.isCorrect": true
});
```

Why? Because the two array conditions can be satisfied by **two different elements**. If you need “Q-01 is correct,” bind both predicates to the same element:

```javascript
db.attempts.find({
  answers: {
    $elemMatch: {
      questionId: "Q-01",
      isCorrect: true
    }
  }
});
```

The sample document will not match. This is a **query semantics** requirement, not merely index tuning.

### 6.1. Multikey Indexes and Growing Arrays

MongoDB can index array element values via **multikey** indexes. Example:

```javascript
db.attempts.createIndex({
  "answers.questionId": 1
});
```

Keep in mind:

- One document with many array elements generates many index entries.
- The larger and more frequently mutated the array, the higher the index maintenance cost.
- Compound indexes spanning multiple array paths face product-specific restrictions.
- Queries require `$elemMatch` or an equivalent construct when conditions must match the same element.
- A large, continuously growing array needing independent pagination may belong in separate child documents rather than trying to fix everything with indexes.

Before indexing, ask whether **access paths truly operate at the parent-document level or at the individual child-element level**. If you need to search attempts per question, filter on multiple attributes, and paginate individual answers, a separate `attemptAnswers` collection often offers a cleaner access model.

### 6.2. Path Indexes Do Not Replace Validation

If `answers.questionId` is sometimes a string, sometimes a number, or missing in many documents, queries yield unpredictable results. Enforce a data contract covering field types, required vs. optional fields, array size caps, and duplicate semantics.

## 7. Specialized Indexes: Use When Requirements Fit

The index types and properties below can be useful, though **exact capabilities depend on the database engine**. Syntax examples use MongoDB.

### 7.1. Partial (Conditional) Indexes

Suppose Q6 frequently fetches learners with `ACTIVE` enrollment in a course:

```javascript
db.enrollments.createIndex(
  { tenantId: 1, courseId: 1, createdAt: -1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    }
  }
);

db.enrollments.find({
  tenantId: "ORG-07",
  courseId: "CRS-0042",
  status: "ACTIVE"
}).sort({ createdAt: -1 }).limit(30);
```

The index stores entries only for documents matching `partialFilterExpression`, reducing index footprint and write overhead compared to indexing every status. However, queries lacking predicates strong enough to imply `status = ACTIVE` cannot use that index to return complete results.

Never treat a partial index as a way to “hide” non-ACTIVE data: **authorization and access control must still be enforced explicitly**.

### 7.2. TTL Indexes and Expiring Data

If supported by the engine, TTL indexes can expire ephemeral data or login sessions with a valid `expiresAt` timestamp.

```javascript
// MongoDB: expiresAt must be stored using an appropriate Date type.
db.ephemeralSessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

TTL typically deletes via a background sweep and **does not guarantee deletion at the exact millisecond of expiration**. If session usage must stop immediately after `expiresAt`, authentication logic must check expiration on the read/write path rather than relying solely on background cleanup.

Never apply TTL to orders, financial records, or legally mandated history merely because storage grows.

### 7.3. Full-Text Search

Searching courses by phrase, fuzzy matching, typos, or relevance ranking is a different problem from filtering `status = PUBLISHED`. Consider your database's built-in text/search indexes or a dedicated search engine.

Account for language rules, Vietnamese tokenization and diacritics, relevance scoring, index update lag, and result-level permissions. A B-tree index on `title` does not automatically solve full-text search.

### 7.4. Wildcard, Hashed, and Other Specialized Indexes

Some engines offer indexes for dynamic fields (*wildcard*), *hashed* keys, *geospatial* data, or specialized types. These help when matched to specific access paths, but carry constraints around sorting, uniqueness, query coverage, and storage cost.

Do not pick them simply because the engine “supports lots of features”; document the mandatory query, applicability rules, and benchmark results.

## 8. Projection: Fetch Only the Fields You Need

A `lessons` document may hold tens of KiB of body text:

```json
{
  "lessonId": "LES-101",
  "tenantId": "ORG-07",
  "courseId": "CRS-0042",
  "position": 3,
  "title": "Keys and Indexes",
  "content": "Very long lesson content...",
  "attachments": ["ASSET-1", "ASSET-2"]
}
```

The table of contents screen usually needs only `lessonId`, `position`, and `title`. Example:

```javascript
db.lessons.createIndex({
  tenantId: 1,
  courseId: 1,
  position: 1,
  _id: 1
});

db.lessons.find(
  { tenantId: "ORG-07", courseId: "CRS-0042" },
  { _id: 1, lessonId: 1, position: 1, title: 1 }
).sort({ position: 1, _id: 1 });
```

**Projection** shrinks response payloads and clarifies API contracts. Yet projection does not automatically guarantee an index-only scan. If `title` and `lessonId` are not inside a suitable index, the engine still fetches the underlying documents to read those fields.

### 8.1. Covered Queries

A query is *covered* when the engine can satisfy both filter predicates and projected return fields directly from the index without reading base documents, subject to engine semantics and capabilities.

For example, if a list needs only `courseId` and `publishedAt`, an index containing all filter/sort/projected fields is a candidate:

```javascript
db.courses.createIndex({
  tenantId: 1,
  status: 1,
  publishedAt: -1,
  courseId: 1
});

db.courses.find(
  { tenantId: "ORG-07", status: "PUBLISHED" },
  { _id: 0, courseId: 1, publishedAt: 1 }
).sort({ publishedAt: -1 }).limit(20);
```

This is a **candidate**—verify with `explain`. Packing lots of fields into indexes just to “cover” every query bloats indexes, lowers cache hit ratios, and slows writes. Measure how many document fetches are actually saved before widening indexes.

### 8.2. Sensitive Data and Projection

Projection is not a substitute for authorization. If an application layer has broad access to documents containing sensitive fields, telling the client “don't render them” is insecure. Restrict returned fields on the backend, enforce tenant/role permissions, and consider separating sensitive fields into a storage boundary with stricter access policies.

## 9. Pagination: Why Does Stable Ordering Matter?

### 9.1. Problems with Deep Skip / Offset

A newest-first list is often implemented as:

```javascript
db.enrollments.find({
  tenantId: "ORG-07",
  learnerId: "USR-0045"
}).sort({ createdAt: -1 }).skip(10000).limit(20);
```

When skipping a large number of results, the engine may have to scan through many entries to reach deep pages. If records are inserted or deleted concurrently, users may see duplicate items or skipped items across page boundaries.

Offset remains reasonable for small lists, shallow pages, or jumping to arbitrary page numbers. For large histories using “load more,” **cursor / keyset pagination** is usually worth considering.

### 9.2. Paginating with a Key Pair

`createdAt` values can collide; include a stable tie-breaker such as `_id` to guarantee a total ordering.

Index:

```javascript
db.enrollments.createIndex({
  tenantId: 1,
  learnerId: 1,
  createdAt: -1,
  _id: -1
});
```

First page:

```javascript
db.enrollments.find(
  { tenantId: "ORG-07", learnerId: "USR-0045" },
  { _id: 1, courseId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
```

Next page using the last item's keys from the previous page, assuming `cursorTime` is a real Date value and `cursorId` matches the `_id` type in the collection:

```javascript
db.enrollments.find(
  {
    tenantId: "ORG-07",
    learnerId: "USR-0045",
    $or: [
      { createdAt: { $lt: cursorTime } },
      { createdAt: cursorTime, _id: { $lt: cursorId } }
    ]
  },
  { _id: 1, courseId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
```

This resumes from **key values**, avoiding scanning past all preceding pages. Note:

- `createdAt` should remain immutable after creation when used as a cursor; if the sort key changes, records jump across pages.
- The cursor must encode all sort keys and stay bound to the query filters/session.
- Newly inserted records during pagination appear ahead of the cursor; this provides “continue browsing” semantics, **not a static snapshot**.
- If an immutable result set across an entire pagination session is required, design a snapshot or cutoff watermark per engine capabilities.
- Inspect the execution plan for `$or`; choose an alternative expression or index if data is large and the planner optimizes poorly.

### 9.3. Sort Order Is Part of the API Contract

If orders are listed by `createdAt` and two orders share the exact same timestamp, results without a tie-breaker can reorder arbitrarily between reads. A stable identifier field prevents ambiguous ordering and enables accurate cursors.

## 10. Inspect Execution Plans Before Declaring an Index Good

An index that looks right on paper can still underperform under real data skew or filter combinations. In MongoDB, inspect execution plans via:

```javascript
db.enrollments.find({
  tenantId: "ORG-07",
  learnerId: "USR-0045"
}).sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Signals to examine:

| Signal | Question to Ask |
| --- | --- |
| `nReturned` | How many documents did the query actually return? |
| `totalKeysExamined` | Did it scan far more index keys than results returned? |
| `totalDocsExamined` | Did it fetch many base documents? |
| Index scan vs. collection scan | Did the query use the intended access path? |
| Sort stage | Is there an in-memory sort outside the index? |
| Execution time | Does latency meet targets on representative data? |
| Plan selection | Do plans differ between small tenants and massive tenants? |

A `COLLSCAN` is not always a bug: on tiny datasets or queries returning nearly every document, a collection scan can be the optimal choice. Likewise, an `IXSCAN` is not automatically good if it scans millions of index entries to return a handful of documents.

Metrics from `explain` do not replace end-to-end application benchmarks. Also measure network latency, serialization, concurrent load, and p95/p99 latency per API route.

### 10.1. Test Skewed Distributions

Suppose most learners take 3 courses, while an administrator views hundreds of thousands of enrollments. If tests only simulate typical learners, indexes may look great while admin paths suffer severe latency.

Test datasets should include:

- Small, medium, and very large tenants.
- Courses with few learners and courses with huge enrollments.
- Common vs. rare statuses, and narrow vs. wide time ranges.
- First pages and deep pages.
- Concurrent writes during active reads.
- Unusually long array elements and schema-allowed missing/`null` fields.

## 11. Write Cost, Storage Footprint, and Index Maintenance

### 11.1. Every Index Is a Structure That Must Be Maintained

Suppose `enrollments` has a unique index per learner–course pair, a chronological history index, an admin course-filter index, and a status-analytics index. A single enrollment write updates multiple indexes.

Avoid “index every field just to be safe.” That causes:

- **Write amplification:** one logical write mutates multiple physical structures.
- Larger index footprint and memory cache pressure.
- Slower index builds and rebuilds, especially on large datasets.
- Competing query plans that are harder to monitor and prune.

Conversely, dropping an index that enforces a **unique constraint** just to save write cost can break invariants and corrupt data. Correctness indexes and performance indexes follow different priorities.

### 11.2. Field Mutation Frequency Affects Cost

An index on `createdAt` is relatively stable because the field is set only once at creation. An index on `updatedAt` may require updating on every single modification.

If `status` flips frequently or indexed array fields mutate continuously, maintenance cost for those indexes climbs. Choose indexes by looking at **both read paths and write paths**, never just one side.

### 11.3. Redundant Indexes and Prefix Overlap

Suppose a collection has:

```javascript
{ tenantId: 1, learnerId: 1 }
{ tenantId: 1, learnerId: 1, createdAt: -1 }
```

The second index can serve some queries using the `(tenantId, learnerId)` prefix. Yet before dropping the first index, check:

- Does the first index carry `unique`, `partial`, or special options?
- Does the engine efficiently use the wider index for every relevant query shape?
- Does the wider index impose noticeable memory/write overhead?
- Are there differences in sort order, collation, or uniqueness?

Never drop an index solely because field names look similar.

## 12. Key and Index Design Must Account for Updates and Migrations

### 12.1. Avoid Keys That Change with Business Attributes

A learner changes email, a course changes code, or a seller changes display name. If document identifiers are tied to those mutable values, references and caches require broad cascading updates.

A more durable design:

```text
users
  { userId: "USR-0045", email: "an@example.com" }

enrollments
  { enrollmentId: "ENR-0102", learnerId: "USR-0045", courseId: "CRS-0042" }
```

When email changes, `learnerId` stays constant. If email must be unique per tenant, add a separate constraint with normalization rules and deletion/reuse handling.

### 12.2. Adding Indexes to Populated Collections

Standard workflow:

1. List required query shapes, latency targets, and candidate indexes.
2. Check existing data for duplicates or missing values before creating a unique index.
3. Evaluate storage overhead, build duration, and operational impact on your live engine.
4. Build/roll out indexes using the safe online mechanism supported by your engine; monitor errors and load.
5. Verify `explain` plans and application metrics before and after.
6. Drop legacy access paths or redundant indexes only after confirming dependent queries are served properly.

When adding a unique constraint to existing data that already contains duplicates, resolve **those duplicate records** at the business level first. Never let an index build arbitrarily “pick” which record wins.

### 12.3. Moving Nested Fields to Separate Documents

Version 1 embedded reviews inside `courses.reviews`, and version 2 splits them into `reviews` for pagination. You must design a stable `reviewId`, a `courseId` reference, indexes by course/time, and a deduplicated migration workflow.

This shows why picking **child keys early** makes schema evolution smoother. Still, do not invent dozens of pointless IDs for every nested attribute; IDs are only needed when a child component has identity, is referenced, or updates independently.

## 13. Integrated Example: Access Design for a Learning Platform

### 13.1. Business and Data Requirements

A platform serves multiple training organizations, each managing courses, lessons, and learners. Learners can enroll in multiple courses, view their history, and open lessons. The course listing screen needs only brief metadata; lesson bodies can be large.

Suggested logical schema:

```text
courses
  {
    _id, tenantId, courseId, courseCode,
    title, summary, status, publishedAt, schemaVersion
  }

lessons
  {
    _id, tenantId, lessonId, courseId,
    position, title, content, publishedVersion
  }

enrollments
  {
    _id, tenantId, learnerId, courseId,
    status, createdAt, updatedAt, version
  }
```

Here `courseId` and `lessonId` are immutable IDs; `courseCode` is a mutable business key; `tenantId` scopes organization data. Timestamp fields use the engine's native date/time type with consistent time-zone conventions.

### 13.2. Keys and Invariants Table

| Collection | Document Identifier | Business Key / Constraint |
| --- | --- | --- |
| `courses` | `_id` or stable `courseId` | `(tenantId, courseCode)` unique per organization |
| `lessons` | `_id` or stable `lessonId` | References `(tenantId, courseId)`; position per course governed by rules |
| `enrollments` | `_id` or `enrollmentId` | `(tenantId, learnerId, courseId)` unique for current enrollment state |

If each course requires a unique lesson `position`, add an appropriate constraint on `(tenantId, courseId, position)`. However, design how **swapping two lesson positions** avoids transient unique-constraint violations, using transactions or an appropriate positioning scheme.

### 13.3. Candidate Indexes Tied to Access Paths

```javascript
// Look up course by business code within an organization.
db.courses.createIndex(
  { tenantId: 1, courseCode: 1 },
  { unique: true }
);

// List published courses, newest first.
db.courses.createIndex({
  tenantId: 1, status: 1, publishedAt: -1, _id: -1
});

// Ordered table of contents for lessons.
db.lessons.createIndex({
  tenantId: 1, courseId: 1, position: 1, _id: 1
});

// One active enrollment record per learner-course pair.
db.enrollments.createIndex(
  { tenantId: 1, learnerId: 1, courseId: 1 },
  { unique: true }
);

// Learner's enrollment history.
db.enrollments.createIndex({
  tenantId: 1, learnerId: 1, createdAt: -1, _id: -1
});

// Admin view of enrollments by course and status.
db.enrollments.createIndex({
  tenantId: 1, courseId: 1, status: 1, createdAt: -1
});
```

This is a **candidate set for an illustrative workload**, not a mandate to create all these indexes in every project. If Q6 uses only a pre-aggregated counter, the detailed index for Q6 may be unnecessary; if lists sort by `updatedAt` instead of `createdAt`, re-evaluate.

### 13.4. Optimizing Each Read Path

- **Course listing page:** filter `tenantId` + `status`, sort `publishedAt` and `_id`, project only `title`, `summary`, and course code. Do not return lesson content.
- **Table of contents:** query `lessons` by `tenantId, courseId`, sort by `position`, project only title and ID.
- **Open lesson:** fetch one lesson by ID and tenant scope, returning `content` to authorized users. Never load every lesson in the course.
- **Learner history:** query `enrollments` by `tenantId, learnerId`, sort chronologically with cursor pagination.
- **Check enrollment before study:** look up by composite business key; verify status, expiration, and permissions.
- **Large reports:** consider aggregation pipelines or an analytical model if scanning millions of records impacts transactional paths.

### 13.5. Verifying via Measurements

For each query shape, run against sufficiently large datasets skewed toward high-traffic tenants and courses. Collect:

- Documents returned vs. keys/documents examined.
- Presence of non-indexed (in-memory) sort stages.
- p95/p99 latency.
- Insert and status-update cost as index count grows.
- Index size and cache hit impact.
- Concurrent write conflicts and unique constraint errors.
- Pagination accuracy when new records arrive.

The design document should include **these empirical observations**, not just a list of index names.

## 14. Cases Where Indexes Cannot Solve Modeling Flaws

### 14.1. Unbounded Child Arrays

A course document embeds hundreds of thousands of `reviews` or `learnerProgress` entries. Even if the engine indexes array paths, the document still risks size limits, painful pagination, and write hotspots. Split child lifecycles into separate documents or use bounded summaries.

### 14.2. Heavy Multi-Document Aggregations at High Load

Monthly revenue, engagement, or score reports may scan millions of documents. Indexes help somewhat, yet may fail heavy reporting SLAs. You may need derived data, materialized views, or an analytical store—always defining authoritative source, lag, and reconciliation.

### 14.3. Multi-Hop Relationship Traversals

If business queries frequently ask “who is indirectly connected to this person within 5 hops,” a graph model may fit better. Indexing reference keys does not turn deep graph traversals into simple queries.

### 14.4. Cross-Entity Invariants

A unique index protects key uniqueness within its supported scope, yet **cannot guarantee** cross-document rules like “inventory remains non-negative across order creation and payment.” Use transactions, conditional writes, or proper coordination workflows.

## 15. Exercise: Clinic Appointment Scheduling System

**Requirements:** An app manages multiple clinics. Each clinic has doctors and appointments. Users need to:

1. Open appointment details by ID.
2. View **one doctor's appointments for a single day**, sorted by start time.
3. View a patient's recent appointments, paginated.
4. Find `CONFIRMED` appointments for a clinic within a time window.
5. Prevent two appointments from sharing the same **booking code** within one clinic.
6. Prevent two appointments for the same doctor from overlapping in time if required by business rules.

Design the keys, queryable fields, and candidate indexes, and explain which constraint cannot be enforced by indexes alone.

### 15.1. Suggested Schema

```json
{
  "_id": "APT-0911",
  "clinicId": "CLN-03",
  "appointmentCode": "A-20261122-001",
  "doctorId": "DOC-07",
  "patientId": "PAT-042",
  "startsAt": "2026-11-22T02:30:00Z",
  "endsAt": "2026-11-22T03:00:00Z",
  "status": "CONFIRMED",
  "createdAt": "2026-11-20T08:00:00Z",
  "version": 1
}
```

Store both timestamps using the engine's native Date type in production; ISO strings in JSON are illustrative only. Convert to the clinic's local time zone on display and enforce business-hour rules per local policy.

### 15.2. Candidate Indexes

```javascript
// Booking code unique within a clinic.
db.appointments.createIndex(
  { clinicId: 1, appointmentCode: 1 },
  { unique: true }
);

// View a doctor's appointments within a day/time range.
db.appointments.createIndex({
  clinicId: 1, doctorId: 1, startsAt: 1
});

// Patient history, newest first.
db.appointments.createIndex({
  clinicId: 1, patientId: 1, createdAt: -1, _id: -1
});

// Appointments by status within a time window.
db.appointments.createIndex({
  clinicId: 1, status: 1, startsAt: 1
});
```

Note that `clinicId` acts both as an access-control boundary and as the leading field in query indexes. If patients can book across multiple clinics and the app needs a **cross-clinic** list, that is a separate query shape requiring dedicated access policies and indexes.

### 15.3. Why Can't an Index Alone Prevent Overlapping Appointments?

Two appointments can have different `startsAt` values yet still overlap in time:

```text
A: 09:00–09:30
B: 09:15–09:45
```

A unique index on `(doctorId, startsAt)` only prevents **identical start times**, not overlapping intervals.

An overlap check can use the condition:

```text
existing.startsAt < requested.endsAt
AND existing.endsAt > requested.startsAt
```

However, “check for no overlap then insert” across two separate statements still suffers race conditions when two users book simultaneously. You need an appropriate transaction/isolation mechanism, engine-supported exclusion/interval constraints, or discrete slot documents with unique keys if appointment durations are cleanly quantized. Exact design depends on booking rules and engine limits.

### 15.4. Self-Check Questions

- If a doctor works at multiple clinics, is `doctorId` unique system-wide or per `clinicId`?
- If a patient changes email, do the document key and appointment history need to change?
- If an appointment moves from `CONFIRMED` to `CANCELLED`, should the document be deleted or merely transition status?
- If admins search appointments with 6 different sort orders, which indexes would you prioritize based on metrics?
- If appointment lists must include sensitive doctor notes, where must authorization and projection be enforced?
- If monthly system-wide reports are required, is adding an index on `startsAt` alone sufficient?

## 16. Common Mistakes and How to Fix Them

**Mistake 1: Using email or display name as the document key.**  
Business attributes can change or expose sensitive information. Prefer immutable IDs and keep email/name as separate attributes with constraints where needed.

**Mistake 2: Omitting uniqueness scope.**  
Course codes may legitimately repeat across tenants. Define explicit scopes like `(tenantId, courseCode)`.

**Mistake 3: Indexing every field present in the document.**  
Wastes storage and slows writes. Start from a query shape inventory and benchmark impact.

**Mistake 4: Assuming any compound index accelerates every subset query.**  
Field order, predicates, and sort directions matter. Verify with execution plans.

**Mistake 5: Omitting a tie-breaker key when sorting.**  
Tied `createdAt` timestamps cause unstable pagination. Use a unique tie-breaker and complete cursor keys.

**Mistake 6: Assuming projection always produces a covered query.**  
Projection only specifies returned fields; covered queries require aligned index structures and semantics, verified via `explain`.

**Mistake 7: Filtering object arrays without binding conditions to the same element.**  
Queries can match false positives across different elements. Use `$elemMatch` or equivalent when needed.

**Mistake 8: Using TTL as an exact real-time expiration enforcer.**  
TTL sweeps can lag. Enforce expiration checks directly on critical business read/write paths.

**Mistake 9: Forgetting `tenantId` in an API or unique index.**  
Risks cross-tenant data leaks or overly broad uniqueness errors. Design and test every access path with tenant scoping.

**Mistake 10: Testing only with small sample datasets.**  
Indexes that look fast on 100 documents do not prove performance with millions of documents, skewed tenants, and concurrent writes.

**Mistake 11: Expecting indexes to enforce every business invariant.**  
Unique indexes alone cannot handle cross-document transactions, overlapping time intervals, inventory reservations, or payments.

**Mistake 12: Picking a shard key simply because it is the primary key.**  
Query routing, write distribution, and transaction scope require separate analysis.

## 17. Design Process and Checklist

Apply this sequence when designing a new collection:

1. **Define entities and document boundaries:** what is embedded vs. referenced; are child arrays bounded?
2. **Choose immutable IDs:** format, issuing service, uniqueness scope, and reference paths.
3. **Choose business keys / constraints:** composite keys, normalization, null/deletion/reuse rules.
4. **Define partition / tenant scope:** do access paths always supply partition keys and authorization filters?
5. **Catalog query shapes:** equality/range filters, sorts, projections, pagination, aggregations, and frequencies.
6. **Propose minimal indexes:** protect uniqueness constraints first, then optimize critical queries.
7. **Design projections and cursors:** return only needed fields, and add tie-breakers for deterministic sorting.
8. **Review arrays and nested fields:** same-element semantics, multikey limits, and growth bounds.
9. **Generate realistic test data:** p50/p95/p99 counts, sizes, and key skew.
10. **Measure and refine:** `explain`, keys/docs examined, latency, index size, retries, and write impact.
11. **Plan evolution:** adding indexes, changing business keys, schema migrations, and pruning unused indexes.
12. **Document evidence:** query–index–rationale–metrics–limits table for peer review.

### Pre-Review Short Checklist

- [ ] Document IDs are immutable, unique within scope, and decoupled from volatile fields.
- [ ] Reference keys define validation, deletion behavior, and orphan handling.
- [ ] `tenantId`/partition scope is enforced across queries, constraints, and permissions.
- [ ] Query shapes are cataloged from real business workflows, not just JSON field lists.
- [ ] Indexes align with critical equality, range, sort, and pagination needs.
- [ ] Every unique index has been checked against legacy data, collation, and null/missing semantics.
- [ ] Array queries enforce same-element matching where business logic requires it.
- [ ] Projections omit oversized payloads and unnecessary sensitive fields.
- [ ] Cursors guarantee deterministic order and explicit behavior under concurrent mutations.
- [ ] Collected `explain`, p95/p99 latency, index footprint, and write overhead on representative data.
- [ ] Specialized indexes (partial, TTL, text) respect product capabilities and limits.
- [ ] Indexes are not misused in place of transactions or coordinated business workflows.
- [ ] A safe strategy exists for adding/removing indexes and migrating keys without corrupting data.

**Key takeaway:** Document keys answer **“which record is this?”**; queryable fields answer **“how does the business find and use this data?”**; indexes answer **“at what cost will the storage engine locate it?”**. Good design begins with real constraints and access paths, chooses stable keys and purposeful indexes, and verifies every assumption with execution plans and realistic workloads.
