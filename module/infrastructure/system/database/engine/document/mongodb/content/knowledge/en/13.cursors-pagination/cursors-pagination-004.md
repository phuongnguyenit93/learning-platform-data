# Pagination with `skip`, `limit`, and Deep-Page Costs in MongoDB

A MongoDB collection can contain millions of documents, while a list screen only displays a few dozen records at a time. **Pagination** helps applications break query results into smaller chunks for users to view sequentially. The most common and intuitive approach is **offset pagination**, combining `skip` to bypass documents preceding the requested page and `limit` to cap the number of returned documents.

For example, with 20 posts per page: page 1 starts at position 0, page 2 starts at position 20, and page 500 starts at position 9,980. This approach is convenient for UIs with page numbers and "go to page N" controls. However, **the deeper the page, the more elements MongoDB must traverse before returning results**. `limit(20)` does not eliminate the cost of skipping the preceding 9,980 elements.

This lesson belongs to the **Cursors and Pagination** chapter. We will practice with `mongosh`, examine cursor behavior, use `sort` to stabilize ordering, observe costs via `explain("executionStats")`, apply appropriate indexes, and recognize when to switch to key-based pagination (keyset/seek pagination).

## 1. How Do `skip` and `limit` Work?

Picture a filtered and sorted result set:

```text
Ordered result list:

Position:  0    1    2    3    4    5    6    7    8    9   ...
Document: A0   A1   A2   A3   A4   A5   A6   A7   A8   A9  ...

Page 1: skip(0)  + limit(3)  -> A0, A1, A2
Page 2: skip(3)  + limit(3)  -> A3, A4, A5
Page 3: skip(6)  + limit(3)  -> A6, A7, A8
```

In MongoDB:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

The query above is interpreted as:

1. Select documents with `status: "published"`.
2. Sort newest first by `createdAt`; on timestamp ties, sort by `_id` descending.
3. Skip the first 3 documents in the **filtered and sorted result set**.
4. Return at most the next 3 documents.

| Component | Role | Note |
| --- | --- | --- |
| `find(filter)` | Determines which documents belong to the result set | `skip` counts over the filtered set, not the whole collection |
| `sort(specification)` | Defines document ordering | Reliable pagination requires a deterministic order |
| `skip(n)` | Skips `n` preceding results | `n = 0` means skip none |
| `limit(k)` | Returns at most `k` results | If fewer than `k` remain at the end, the page returns fewer |

`skip()` and `limit()` are methods on the **cursor** returned by `find()`. The cursor represents the process of reading results; calling `find()` in `mongosh` does not mean all documents are preloaded into client memory. Reading only needed batches is a cursor benefit, but it **does not eliminate the server-side cost of large offsets**.

## 2. Creating Sample Data with Verifiable Ordering

Open `mongosh` and select the practice database:

```javascript
use mongo_pagination_lab
```

Insert ten posts into a new or empty `posts` collection:

```javascript
db.posts.insertMany([
  {
    _id: 101, title: "Post 101", status: "published",
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: 102, title: "Post 102", status: "published",
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: 103, title: "Post 103", status: "published",
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: 104, title: "Post 104", status: "published",
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: 105, title: "Post 105", status: "published",
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: 106, title: "Post 106", status: "published",
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: 107, title: "Post 107", status: "published",
    createdAt: ISODate("2026-11-09T08:00:00Z")
  },
  {
    _id: 108, title: "Post 108", status: "published",
    createdAt: ISODate("2026-11-09T08:00:00Z")
  },
  {
    _id: 109, title: "Post 109", status: "published",
    createdAt: ISODate("2026-11-08T08:00:00Z")
  },
  {
    _id: 110, title: "Post 110", status: "published",
    createdAt: ISODate("2026-11-08T08:00:00Z")
  }
])
```

Fixed `_id` values are used to clarify ordering when multiple posts share the same `createdAt`. `_id` does not have to be numeric in real applications; it can be an `ObjectId` or another unique key.

If you re-insert into a collection containing these `_id` values, MongoDB will report duplicate key errors. Create this dataset in a separate lab environment and avoid dropping collections with data you need to keep.

Retrieve the ordered list:

```javascript
db.posts.find(
  { status: "published" },
  { _id: 1, title: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
```

The expected order of IDs is:

```text
102, 101, 104, 103, 106, 105, 108, 107, 110, 109
```

In the sample data, `102` precedes `101` even though both documents share the same timestamp, because we use `_id: -1` as the secondary criterion.

## 3. Computing Offset from Page Number

Many APIs use **1-based page numbers**. If `page` is the page number and `pageSize` is the number of documents per page, we have:

\[
\text{skip} = (\text{page} - 1) \times \text{pageSize}
\]

Example with `pageSize = 3`:

| Page | Calculation | `skip` | Resulting IDs on sample data |
| --- | --- | --- | --- |
| 1 | `(1 - 1) * 3` | 0 | `102, 101, 104` |
| 2 | `(2 - 1) * 3` | 3 | `103, 106, 105` |
| 3 | `(3 - 1) * 3` | 6 | `108, 107, 110` |
| 4 | `(4 - 1) * 3` | 9 | `109` |
| 5 | `(5 - 1) * 3` | 12 | No documents |

Querying each page in `mongosh`:

```javascript
// Page 1
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0)
  .limit(3)

// Page 2
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)

// Page 3
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(6)
  .limit(3)
```

A snippet using variables:

```javascript
const page = 2;      // 1-based
const pageSize = 3;  // Documents per page

if (!Number.isSafeInteger(page) || page < 1) {
  throw new Error("page must be an integer >= 1");
}
if (!Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 100) {
  throw new Error("pageSize must be in range 1..100");
}

const offset = (page - 1) * pageSize;
if (!Number.isSafeInteger(offset)) {
  throw new Error("Offset exceeds safe integer range");
}

db.posts.find(
  { status: "published" },
  { title: 1, createdAt: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .skip(offset)
  .limit(pageSize)
```

This structure fits an API like `GET /posts?page=2&pageSize=3`. The server must **validate** `page`, `pageSize`, and `offset` itself; never pass unvalidated user parameters directly into the query.

If the UI uses 0-based page indexing, the formula is `skip = pageIndex * pageSize`. Pick one clear convention and apply it consistently across both frontend and backend.

## 4. Why Must You Use a Stable `sort`?

Without `sort`, MongoDB **does not guarantee result ordering**. Observed order can depend on access paths, indexes, the query planner, or data mutations. Therefore:

```javascript
// Should not be used for stable pagination
db.posts.find({ status: "published" })
  .skip(3)
  .limit(3)
```

has no stable meaning for "page 2" if the application expects a specific ordering.

Adding `sort({ createdAt: -1 })` defines the time direction, yet documents with the **same timestamp** can still swap relative positions. In our sample dataset, every pair of documents shares the same `createdAt`, so a unique tie-breaker key is needed:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

Here `_id` is unique within the collection, so the `(createdAt, _id)` pair establishes a deterministic order among documents. When two items share the same timestamp, MongoDB uses `_id` to break ties.

**Deterministic ordering does not mean an immutable data snapshot.** Even with a complete `sort`, pages requested at different times can still shift if documents are inserted, deleted, or sorted fields are updated. Section 9 explains this limitation clearly.

### Filter First, Then Determine Position

If paginating only published posts:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

then offset 3 is calculated over **posts with status published**, not across the whole collection before dropping draft posts. Therefore, every page of the same list must use **the same filter and sort**, unless the user intentionally changes search criteria.

## 5. Interaction Between `skip`, `limit`, Cursor, and Projection

`skip(n)` controls where results start returning; `limit(k)` controls the maximum count. Neither modifies stored documents.

```javascript
db.posts.find(
  { status: "published" },
  { title: 1, createdAt: 1, _id: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

`projection` is the second argument to `find()`. It only decides **which fields are returned**, such as `title`, `createdAt`, and `_id`; it does not turn a deep page into a shallow page or avoid the cost of skipping preceding results.

### Returned Count Is an Upper Bound

If the last page has only one document left, `limit(3)` still returns only one document. Once the offset exceeds the number of matching documents, the cursor returns no documents. This is a normal state, not necessarily a query error.

```javascript
// There are 10 documents in the sample dataset:
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(9)
  .limit(3) // Only 1 document remains
```

### `batchSize` Differs from `limit`

The driver and server exchange cursor data in **batches**. `batchSize()` tunes the desired document count per batch, whereas `limit()` caps the **total documents returned by the query**.

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
  .batchSize(2)
```

With this configuration, total results still will not exceed 3, even though the driver may need multiple batch fetches. `batchSize(2)` does not mean the query may return at most two documents.

For UI pagination, use `limit` to cap items per page; adjust `batchSize` only when there are specific data-transfer or cursor-streaming requirements.

### When Using an Aggregation Pipeline

If the query requires `aggregate()`, stage order is semantically significant:

```javascript
db.posts.aggregate([
  { $match: { status: "published" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $skip: 3 },
  { $limit: 3 },
  { $project: { title: 1, createdAt: 1 } }
])
```

The goal is **match → sort → skip → limit**. If you write `$limit: 3` before `$skip: 3`, you truncate the stream to three items before skipping three items; the output will not be page 2 as intended. The MongoDB optimizer may reorder certain operations for execution efficiency, but the pipeline author must still express the correct logical order.

## 6. Deep-Page Cost: Why Large `skip` Becomes Expensive

Suppose a collection has 2 million matching posts; each page displays 20 posts:

| Page | `skip` | `limit` | Elements before the page that must be traversed |
| --- | ---: | ---: | ---: |
| 1 | 0 | 20 | 0 |
| 10 | 180 | 20 | 180 |
| 100 | 1,980 | 20 | 1,980 |
| 1,000 | 19,980 | 20 | 19,980 |
| 10,000 | 199,980 | 20 | 199,980 |

To reach elements at a deep position, MongoDB typically has to **walk through the preceding elements in result order** and discard them. `skip(199980).limit(20)` returns at most 20 documents to the client, yet it does not mean the server only processes 20 items.

When the query already has an index supporting filtering and ordering, an intuitive cost model is:

\[
\text{Items to traverse} \approx \text{skip} + \text{limit}
\]

This is an **intuition for traversal work**, not a rigid formula for runtime or decoded document count: execution plans, selectivity, indexes, cache, and filters still affect results. MongoDB cannot jump directly to "the 200,000th record" solely from B-tree ordering as if there were an exact lookup table mapping page numbers to offsets.

### How Do Page 1 and Page 10,000 Differ?

```text
Page 1:
[20 items to read] --> Return 20 items

Page 10,000:
[199,980 items traversed/skipped] [20 items to read] --> Return 20 items
                                        ^
                                 Small returned payload
                                 does not erase skip cost
```

Therefore, an API having `limit: 20` is not enough to guarantee fast responses on every page. Requests with very large offsets can raise latency and system load, especially when many users jump to deep pages concurrently.

### Cost Without an Index Supporting `sort`

When MongoDB lacks a suitable index, the server may have to read many documents to filter, sort, or maintain buffers for the sort and offset operations. Some plans use a bounded sort keyed to `skip + limit` to reduce intermediate memory, yet **the larger the offset, the larger the output window that still must be processed**.

Costs can include:

- Reading many index entries or documents to find enough records matching the filter.
- Sorting the result set or maintaining intermediate state when an index does not satisfy the sort order.
- CPU, memory, I/O, and query resource hold time.
- Cumulative latency when many concurrent requests perform deep pagination.

Do not assume an indexed query is always fast or an unindexed query is always slow; inspect the actual plan for the **exact filter, sort, skip, and limit**.

## 7. Using Indexes to Reduce Filtering and Sorting Work

For a frequent query:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(1000)
  .limit(20)
```

you can create a compound index:

```javascript
db.posts.createIndex(
  { status: 1, createdAt: -1, _id: -1 },
  { name: "status_createdAt_id_desc" }
)
```

This index is designed for the equality predicate on `status` and descending order on `createdAt`, `_id`. If the query planner picks the right index, MongoDB can avoid sorting the entire result set in memory just to satisfy `sort`.

However, **an index does not eliminate walking past the offset**. To return the page starting at position 1,000, the server still needs to step through items preceding that page in the chosen order, even though scanning index entries is typically far cheaper than scanning the collection and sorting.

### Choosing Indexes Based on Actual Filters and Sorts

| Query shape | Index to consider | Notes |
| --- | --- | --- |
| `find({status:"published"}).sort({createdAt:-1,_id:-1})` | `{status:1,createdAt:-1,_id:-1}` | Equality on `status`, then sort |
| `find({authorId:"u1"}).sort({createdAt:-1,_id:-1})` | `{authorId:1,createdAt:-1,_id:-1}` | For author-scoped lists |
| `find({}).sort({_id:1})` | Default index on `_id` | Can read in `_id` order |
| `find({category:"tech",status:"published"}).sort({createdAt:-1,_id:-1})` | `{category:1,status:1,createdAt:-1,_id:-1}` | Evaluate selectivity and primary query patterns |

Do not create dozens of indexes just because there are many UI screens. Indexes consume storage and add overhead to inserts, updates, and deletes. Choose indexes for critical queries, measure effectiveness, and manage indexes in your operational plan.

### Indexes Also Do Not Fix Unstable Ordering

```javascript
db.posts.find({ status: "published" }).skip(100).limit(20)
```

still has no guaranteed ordering even if the collection has indexes. The application must **explicitly specify `sort`**, and when sort keys contain duplicate values, add a unique key to break ties.

## 8. Measuring Cost with `explain("executionStats")`

MongoDB provides `explain()` to inspect how the query planner plans and executes a query. With small lab data, do not draw production performance conclusions; the goal is learning how to read the statistics fields. You can use a larger collection in a test environment if permitted.

```javascript
const filter = { status: "published" };
const order = { createdAt: -1, _id: -1 };

db.posts.find(filter)
  .sort(order)
  .skip(0)
  .limit(3)
  .explain("executionStats")
```

Compare with a larger offset:

```javascript
db.posts.find(filter)
  .sort(order)
  .skip(6)
  .limit(3)
  .explain("executionStats")
```

When reading the output, focus on:

| Statistic field / signal | What to observe |
| --- | --- |
| `nReturned` | Number of documents returned by the explained query |
| `totalKeysExamined` | Number of index entries examined during execution |
| `totalDocsExamined` | Number of documents examined in stages requiring document reads |
| `executionTimeMillis` | Reported execution time, influenced by measurement environment |
| Stages such as `IXSCAN`, `COLLSCAN`, `SORT`, `SKIP`, `LIMIT` | Indicates index usage, collection scan, sorting, skipping, and limiting in the plan |

With a good index, `totalKeysExamined` can rise substantially as `skip` increases, even while `nReturned` stays close to `limit`. `totalDocsExamined` may grow much less if the query is well supported or covered by an index; do not infer that examined documents **always** equal `skip + limit`.

Plans and `explain` structures can differ across MongoDB versions and execution engines. Runtime can fluctuate due to cache, machine resources, competing load, and dataset size. Therefore, compare **a set of measurements under identical conditions**, rather than relying on a single timing number from one run.

### Testing Index Changes

After creating the index:

```javascript
db.posts.getIndexes()
```

Re-run the two `explain` queries with different offsets. Observe whether the query planner uses the index matching filter/sort, whether an extra `SORT` stage appears, and how `totalKeysExamined` varies.

Running `explain` is a diagnostic observation; it does not magically make offset pagination suitable when users routinely browse hundreds of thousands of positions deep.

## 9. Data Changing Between Pages: Duplicates and Skipped Documents

**A stable `sort` is necessary but not sufficient** if each page is fetched in a separate request at different times. The essence of offset pagination is "skip the leading N items **at the moment the current query runs**". When the result set changes, document positions shift.

### 9.1. Inserting New Documents Can Cause Duplicates

Initially, with `pageSize = 3` and sort `{createdAt:-1,_id:-1}`:

```text
Page 1 read:              [102, 101, 104]
Unread portion:            103, 106, 105, 108, ...
```

After the user reads page 1, a new post `111` arrives with a `createdAt` newer than all older posts:

```text
New list:                 111, 102, 101, 104, 103, 106, 105, ...
Page 2 using skip(3):                   [104, 103, 106]
```

Document `104` appeared at the end of page 1 and now appears at the start of page 2. This is a **cross-page duplicate** caused by positional shift; adding `_id` to the sort cannot prevent it because the dataset itself changed.

### 9.2. Deleting Documents Can Cause Skips

If `102` is deleted after page 1 returns:

```text
Initial list:              102, 101, 104, 103, 106, 105, ...
Page 1 read:              [102, 101, 104]

List after deletion:       101, 104, 103, 106, 105, 108, ...
Page 2 using skip(3):                [106, 105, 108]
```

Document `103` is **skipped** for someone moving from page 1 to page 2 because a preceding item was removed. Updating `status` so a document no longer matches the filter, or modifying the `createdAt` sort field, can cause the same effect.

### 9.3. When Does This Issue Matter?

- Low-churn admin lists where users want to jump to arbitrary pages: offset pagination can be a reasonable choice.
- News feeds or rapidly changing task lists: offset pagination easily causes users to see duplicates or missed items.
- Data export streams requiring a consistent result set: require a dedicated strategy for snapshots/read sessions, checkpoints, or sort keys; multiple standard page requests do not automatically create an immutable snapshot.

**Never promise that merely adding `sort` guarantees users see every document once across multiple requests.** Sort only defines ordering at each individual point in time.

## 10. Key-Based Pagination (Keyset/Seek) for Deep Traversal

When a UI primarily uses **"Load more"**, **"Next page"**, or infinite scroll, you can avoid large offsets by remembering the **sort key of the last document from the previous page**.

With sort:

```javascript
{ createdAt: -1, _id: -1 }
```

the next page needs documents whose key pair is **smaller than** the previous page's last document in descending order:

- `createdAt` is older than `last.createdAt`, or
- `createdAt` equals `last.createdAt` while `_id` is smaller than `last._id`.

### 10.1. Fetching the First Page

```javascript
const pageSize = 3;
const order = { createdAt: -1, _id: -1 };

const firstPage = db.posts.find(
  { status: "published" },
  { _id: 1, title: 1, createdAt: 1 }
)
  .sort(order)
  .limit(pageSize)
  .toArray();

printjson(firstPage);
```

On the sample data, the first page contains `102, 101, 104`. The last document has `_id = 104` and `createdAt = 2026-11-11T08:00:00Z`.

### 10.2. Querying the Next Page by Key

```javascript
if (firstPage.length > 0) {
  const last = firstPage[firstPage.length - 1];

  const secondPage = db.posts.find(
    {
      status: "published",
      $or: [
        { createdAt: { $lt: last.createdAt } },
        {
          createdAt: last.createdAt,
          _id: { $lt: last._id }
        }
      ]
    },
    { _id: 1, title: 1, createdAt: 1 }
  )
    .sort({ createdAt: -1, _id: -1 })
    .limit(pageSize)
    .toArray();

  printjson(secondPage);
}
```

Page two contains `103, 106, 105` when data is unchanged. No `skip(3)` is needed: the filter sets the **starting position by key value**. With an appropriate index, the query can locate the target key range much more efficiently at deep positions.

### 10.3. Comparing Offset and Keyset

| Criterion | Offset: `skip + limit` | Keyset: last key + `limit` |
| --- | --- | --- |
| Jumping directly to page 500 | Easy to express via offset | Usually requires a token for that position |
| "Load more" button | Works, though offset grows linearly | Fits naturally |
| Deep-page cost | Usually grows with items skipped | Can seek by key range if indexed |
| New records inserted ahead of read position | Prone to duplicates or skips | Usually avoids shifting caused by head inserts |
| Deterministic ordering required | Yes | Yes, and sort keys must be preserved in token |
| Total page count | Can pair with `countDocuments` | Optional; commonly uses `hasNext` |
| Mutating sort key of existing document | Can affect results | Can also affect results; not a snapshot |

Keyset does not completely replace offset in every UI: if jumping to an arbitrary numbered page is required, offset remains more convenient. Conversely, for infinite-scroll feeds that can go very deep, keyset is usually a better fit.

**Practical pagination tokens** should encode the fields needed to reconstruct the predicate: `createdAt`, `_id`, plus filter/sort context if the API needs to prevent token misuse. Tokens can be packaged and signed at the application layer; when filters or ordering change, reset back to the first page. Never trust a client-supplied token without validating its structure and access rights.

## 11. Counting Total Items and Computing `hasNext`

A numbered-page UI often also needs the total record count. MongoDB provides:

```javascript
const total = db.posts.countDocuments({
  status: "published"
});

const pageSize = 3;
const totalPages = Math.ceil(total / pageSize);

print("Total records: " + total);
print("Total pages: " + totalPages);
```

On the sample data, `total = 10`, `totalPages = 4`. `countDocuments(filter)` applies the **same filter** as the list; if `status` or search conditions change, the total must reflect the new filter.

However, exact counting can be resource-intensive on large datasets or complex filters. Do not automatically run an expensive count on **every** page request if the UI only needs to know whether a next page exists.

### Determining `hasNext` with One Extra Item

You can fetch up to `pageSize + 1` documents at the current page position:

```javascript
const page = 2;
const pageSize = 3;
const offset = (page - 1) * pageSize;

const fetched = db.posts.find(
  { status: "published" },
  { _id: 1, title: 1, createdAt: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .skip(offset)
  .limit(pageSize + 1)
  .toArray();

const hasNext = fetched.length > pageSize;
const items = fetched.slice(0, pageSize);

printjson({ page, pageSize, hasNext, items });
```

`hasNext` indicates whether **at least one subsequent item exists at query time**. No full collection count is needed, though deep offsets still pay the `skip` cost. If data changes between requests, `hasNext` and total pages can change.

`estimatedDocumentCount()` is a fast estimate based on collection-level metadata and does not accept the same `filter` as `countDocuments()`; hence, it cannot substitute for an exact count of documents matching `status: "published"`.

## 12. Implementing Offset Pagination with the MongoDB Java Sync Driver

In Java, `find()` returns `FindIterable<Document>`; you can chain `.sort()`, `.skip()`, and `.limit()`. The snippet below illustrates a page-fetching helper that validates parameters, enforces stable ordering, and returns a `hasNext` flag.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class PostsPaginationExample {
    record Page(List<Document> items, boolean hasNext) {}

    static Page getPage(
            MongoCollection<Document> posts,
            int pageNumber,
            int pageSize) {

        if (pageNumber < 1) {
            throw new IllegalArgumentException("pageNumber must be >= 1");
        }
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize must be in 1..100");
        }

        long offset = ((long) pageNumber - 1L) * pageSize;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Offset exceeds Java Driver skip range"
            );
        }

        List<Document> fetched = posts.find(
                Filters.eq("status", "published"))
            .sort(Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
            ))
            .projection(Projections.include("_id", "title", "createdAt"))
            .skip((int) offset)
            .limit(pageSize + 1)
            .into(new ArrayList<>());

        boolean hasNext = fetched.size() > pageSize;
        if (hasNext) {
            fetched.remove(pageSize); // Remove the item used only for probing
        }
        return new Page(fetched, hasNext);
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_pagination_lab");
            MongoCollection<Document> posts =
                database.getCollection("posts");

            Page page2 = getPage(posts, 2, 3);
            for (Document post : page2.items()) {
                System.out.println(post.toJson());
            }
            System.out.println("hasNext = " + page2.hasNext());
        }
    }
}
```

The snippet uses Java `record` (Java 16+) and the appropriate MongoDB Java Sync Driver. It assumes sample data was created and the `MONGODB_URI` environment variable is set. With the initial dataset, page 2 contains IDs `103, 106, 105`; `hasNext` is `true` because more posts follow page 2.

**Why cast `offset` to `long` first?** Multiplying two large `int` values can overflow before being passed to the driver. Here, the Java Sync Driver's `skip(int)` takes an `int`, so we validate bounds before casting. Capping `pageSize` prevents clients from requesting an oversized page, though a huge type-valid `pageNumber` can still make an offset query expensive; production APIs should enforce a depth limit policy or use another pagination approach.

### Returning Results via a REST API

A response may be structured as:

```json
{
  "page": 2,
  "pageSize": 3,
  "hasNext": true,
  "items": [
    { "_id": 103, "title": "Post 103" },
    { "_id": 106, "title": "Post 106" },
    { "_id": 105, "title": "Post 105" }
  ]
}
```

This is an example API shape; `createdAt` can also be included as needed. The backend should keep the same filter, sort, and parameter bounds across all pages. If the UI needs "total pages", a `totalCount` field can be added from a count query after weighing its cost.

## 13. Common Mistakes

| Situation | Why is it wrong or inefficient? | How to handle |
| --- | --- | --- |
| Using `skip`/`limit` without `sort` | No guaranteed result ordering | Specify `sort` explicitly |
| Sorting only by `createdAt` when timestamps tie | Same-timestamp documents have unstable positions | Add `_id` or a unique key to `sort` |
| Page 1 computes `skip = page * size` | Skips the first page if pages are 1-based | Use `(page - 1) * pageSize` |
| `page = 0`, `pageSize = -10`, or huge `pageSize` | Invalid parameters or unnecessary load | Validate and enforce bounds before querying |
| Believing `limit(20)` guarantees page 50,000 is fast | Server still traverses the offset before returning 20 items | Evaluate cost and use keyset when appropriate |
| Thinking an index jumps straight to the Nth result | Indexes aid order/search but don't map directly to ordinal N | Filter by sort key conditions when going deep |
| Changing filter between requests while keeping `page`/`offset` | Page no longer corresponds to the same result set | Reset page to 1 when filters change |
| Inserting new posts causes duplicates across pages | Offset recounts from the head of the mutated list | Consider keyset/seek or snapshot mechanisms |
| Using `estimatedDocumentCount()` for a filtered total | Collection-level estimate, not an exact filtered count | Use `countDocuments(filter)` when exact count is truly needed |
| Running `countDocuments()` on every infinite-scroll request | Counting adds load while UI only needs to know if more items exist | Fetch `pageSize + 1` to compute `hasNext` |
| Putting `$limit` before `$skip` in aggregation | Caps stream first then skips, yielding wrong page | Order stages as `$sort` → `$skip` → `$limit` |
| Judging speed from a single run | Cache, machine load, and query planner affect timing | Inspect execution stats and measure repeatedly under same conditions |

## 14. Practice Exercises

### Exercise 1. Calculating Offsets

A UI displays 25 documents per page, numbered starting at 1. Calculate the offset for pages 1, 4, 20, and 200.

**Answer:**

| Page | Formula | Offset |
| --- | --- | ---: |
| 1 | `(1 - 1) * 25` | 0 |
| 4 | `(4 - 1) * 25` | 75 |
| 20 | `(20 - 1) * 25` | 475 |
| 200 | `(200 - 1) * 25` | 4,975 |

### Exercise 2. Writing the Query for Page 3

Collection `orders` has fields `state`, `createdAt`, and `_id`. Requirement: find orders with `state: "paid"`, newest first, paginated at 15 orders/page; fetch page 3.

**Answer:**

```javascript
db.orders.find({ state: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(30)
  .limit(15)
```

The offset is `(3 - 1) * 15 = 30`. Including `_id` prevents ambiguous ordering when orders share identical creation timestamps.

### Exercise 3. Comparing First Page and Deep Page

A list has 1 million matching documents and an index supporting the filter/sort. One request uses `skip(0).limit(20)`, and another uses `skip(200000).limit(20)`. Both return only 20 documents. Why can the second request be much slower?

**Answer:** An offset of 200,000 forces MongoDB to step through many entries before the slice to return. An index can reduce filter/sort work, but it cannot jump straight to the 200,001st result from an offset alone. Inspect `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, and the winning plan using `explain("executionStats")`.

### Exercise 4. Spotting Cross-Page Duplicates

Page 1 returned `[102, 101, 104]`. Next, a new document `111` enters at the top of the list. Page 2 still calls `skip(3).limit(3)`. What issue can occur in the result?

**Answer:** In the updated list `[111, 102, 101, 104, 103, 106, ...]`, page 2 starts at `104`, so `104` is duplicated. This is a positional shift caused by an insert between two requests, not a missing `sort`.

### Exercise 5. Building a Keyset Filter for Descending Sort

Suppose the previous page ended with the document:

```javascript
{
  _id: 104,
  createdAt: ISODate("2026-11-11T08:00:00Z")
}
```

Fetch up to the next three documents in `createdAt` descending, `_id` descending order.

**Answer:**

```javascript
db.posts.find({
  status: "published",
  $or: [
    {
      createdAt: {
        $lt: ISODate("2026-11-11T08:00:00Z")
      }
    },
    {
      createdAt: ISODate("2026-11-11T08:00:00Z"),
      _id: { $lt: 104 }
    }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
```

The result on the sample data is `103, 106, 105`. The filter uses **the last key values from the previous page**, not an offset.

### Exercise 6. Choosing Between Offset and Keyset

Two screens have different requirements:

- **Screen A:** an administrator wants to jump directly to page 75 of a nearly static list.
- **Screen B:** a frequently updated feed where users scroll continuously via a "Load more" button.

**Suggested answer:** Screen A fits offset pagination if access depth stays within acceptable performance bounds with proper filtering, sorting, and indexing. Screen B usually fits keyset because it only advances from the current position, avoiding the cost of skipping many items and reducing duplicates when new posts appear at the head of the list.

## 15. Practical Rules to Remember

Before shipping a MongoDB pagination API, determine: which **filter** defines the result set, which **sort** establishes a complete ordering, what the maximum **pageSize** is, whether **total pages** are needed or only `hasNext`, and whether users truly need to jump directly to **deep pages**.

For small or medium lists, `find().sort().skip().limit()` is clear and easy to integrate with page numbers. As offsets grow large, **the data the server must traverse increases even when the returned count stays constant**; compound indexes help reduce filtering and sorting costs but cannot eliminate the inherent nature of offsets. For very deep sequential reads, consider persisting the last page key and using **keyset pagination**. Whichever approach you pick, deterministic sorting and understanding the impact of data mutations between requests remain the foundation of a reliable pagination API.
