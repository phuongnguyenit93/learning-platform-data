# Counting Total Records and Accuracy vs. Latency Trade-offs in MongoDB

## 1. Why Does Total Record Count Become a Problem in Pagination?

In MongoDB systems, a list view often needs two kinds of information:

- **Current page data:** e.g., the 20 newest orders.
- **Total matching documents for the filter:** e.g., 125,430 paid orders belonging to the signed-in tenant.

To fetch the first 20 documents, MongoDB can use an index matching the filter and sort order, then stop once `limit(20)` is satisfied. However, to answer **exactly how many total documents match**, the server typically must evaluate a far larger range of data. As a result, an API whose page data returns quickly can still become slow because of the total count query.

This lesson belongs to the **Cursors and Pagination** chapter of **Database Engine Document MongoDB**, answering the following questions:

- When should you use `countDocuments()`, and when should you use `estimatedDocumentCount()`?
- What are the benefits of using `$count` or `$facet` in aggregation?
- How do you count with the page's exact filter instead of accidentally counting the entire collection?
- Does `skip/limit` introduce latency on deep pages, and what does cursor/keyset pagination solve?
- Is an exact count at query time still accurate when the user turns the page a few seconds later?
- Can you skip the exact total and return only `hasNext`?
- How should an estimated or cached total be displayed so users are not misled?

After this lesson, you will be able to design pagination APIs with clear semantics, choose a counting strategy matching your SLA, inspect query plans, and analyze trade-offs among accuracy, latency, and scalability.

## 2. Defining Common Metrics

Suppose a list has 6 orders matching the filter, and each page displays 2 orders:

| Component | Value | Meaning |
|---|---:|---|
| `pageSize` | 2 | Maximum number of documents per page |
| `returnedCount` | 2 | Actual number of documents returned in this response |
| `totalMatching` | 6 | Total documents matching the filter before pagination |
| `totalPages` | 3 | Number of pages based on total and `pageSize` |
| `hasNext` | true for pages 1, 2 | Whether results remain after the current page |

Formula when the total is exact and `pageSize > 0`:

\[
\text{totalPages}=\left\lceil\frac{\text{totalMatching}}{\text{pageSize}}\right\rceil
\]

If there are zero documents, the calculation yields 0 pages. A UI might optionally display "Page 1/1" when empty, but UI conventions must be distinguished from calculated page counts.

**Do not confuse:** `items.length` or `returnedCount` describes only the current page, not the total result count. Having 20 documents on a page does not mean there are only 20 results in total.

### 2.1. Four Confidence Levels for Totals

**Exact:** The count is computed by a filtered count query. It is accurate per query semantics at the moment of observation, though underlying data can still change afterward.

**Estimated:** An approximate count, typically derived from metadata or statistical methods. There is no per-document match guarantee.

**Cached:** A count computed at an earlier time, which may already be stale if data has changed.

**Not computed:** No total is computed; the API only supplies the page results alongside `hasNext` or `nextCursor`.

These levels can be represented via a `totalKind` field in the response. Never label an estimate as exact simply because the numbers happen to match on a small dataset.

## 3. Preparing the Practice Dataset

Open `mongosh` connected to a MongoDB Server or cluster where you have write access, and switch to a dedicated database:

~~~javascript
use pagination_count_lab
~~~

Insert 24 sample documents into the `orders` collection:

~~~javascript
const demoOrders = [];

for (let i = 1; i <= 24; i++) {
  const id = "ord-" + String(i).padStart(3, "0");

  const status =
    i % 3 === 0 ? "PAID" :
    i % 3 === 1 ? "NEW" :
    "SHIPPED";

  demoOrders.push({
    _id: id,
    tenantId: i <= 18 ? "tenant-A" : "tenant-B",
    status: status,
    customerId: "cus-" + String((i % 7) + 1).padStart(2, "0"),
    amount: NumberDecimal(String(10 + i) + ".50"),
    createdAt: new Date(Date.UTC(2026, 9, i + 1, 9, 0, 0)),
    active: i % 4 !== 0
  });
}

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.countDocuments({});
~~~

On an initially empty collection, the result is **24 documents**. Each re-run uses `replaceOne` to reset the 24 documents (`ord-001` through `ord-024`) to sample values without deleting other documents. Thus, the expected numbers below assume no extra records outside this dataset were added.

Distribution:

- `tenant-A` has IDs `ord-001` to `ord-018`, totaling **18** documents.
- `tenant-B` has IDs `ord-019` to `ord-024`, totaling **6** documents.
- Each tenant has `NEW`, `SHIPPED`, and `PAID` statuses evenly distributed.
- `tenant-A` has exactly **6 PAID orders**: `ord-003`, `ord-006`, `ord-009`, `ord-012`, `ord-015`, and `ord-018`.
- `createdAt` is a BSON Date increasing with the ID index, making sort results predictable.
- `active` is false for IDs whose index is divisible by 4.

Create an index supporting the filter and sort:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_status_created_id" }
);
~~~

The main examples will use:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const pageSize = 2;
const sort = { createdAt: -1, _id: -1 };
~~~

Inspect:

~~~javascript
db.orders.find(
  filter,
  { _id: 1, status: 1, createdAt: 1 }
).sort(sort);
~~~

Expected result order:

~~~text
ord-018, ord-015, ord-012, ord-009, ord-006, ord-003
~~~

## 4. Exact Count Using countDocuments()

### 4.1. Syntax

`countDocuments()` counts documents matching a filter:

~~~javascript
db.orders.countDocuments({});
db.orders.countDocuments({ tenantId: "tenant-A" });
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
});
~~~

In the collection with exactly 24 sample documents, the respective results are:

~~~text
24
18
6
~~~

The count command returns a number, not documents. If you need the count of PAID orders for `tenant-A`, pass **that exact filter**—never take the whole-collection total as a filtered total.

### 4.2. Count and Page Query Must Share the Same Business Filter

Example API needing a list of paid orders for `tenant-A`:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const total = db.orders.countDocuments(filter);

const rows = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(2)
  .toArray();

printjson({
  total: total,
  returnedCount: rows.length,
  items: rows
});
~~~

With unchanged sample data, `total = 6` and `returnedCount = 2`.

A common bug:

~~~javascript
// Wrong when the page only displays PAID orders:
const total = db.orders.countDocuments({
  tenantId: "tenant-A"
});
// total = 18 instead of 6.
~~~

In multi-tenant applications, the count query **must also enforce tenant and authorization scopes**, not just the page-fetching query. This is a data security requirement, not merely a statistics concern.

### 4.3. Multi-Condition Filters

~~~javascript
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: { $in: ["PAID", "SHIPPED"] }
});
~~~

Result: **12** documents.

~~~javascript
db.orders.countDocuments({
  tenantId: "tenant-A",
  active: true
});
~~~

Among `tenant-A`'s 18 orders, IDs 4, 8, 12, and 16 have `active: false`, so the result is **14**.

Just like `find()`, filtered counts can use appropriate query operators. Conditions must be designed around the **unit being counted**: orders, customers, products, or an aggregated entity.

### 4.4. Why Can an Exact Count Be Slow?

To report the exact number of documents matching a filter, the server must count across the query's match range. Depending on data and indexes:

- It may only need to scan a range of index keys.
- It may need to read many documents if the filter is not fully covered by indexes.
- With an unselective or empty filter, a very large portion of the collection must be inspected.
- The output is just a single number, yet the work to compute it is not necessarily small.

Therefore, **returning little data does not mean scanning little data**.

Exact counts can still be very fast on small datasets or highly selective, well-indexed filters. There is no blanket rule that "`countDocuments` is always slow"; always measure on real data.

### 4.5. Avoid Accidentally Passing skip and limit to Count

The `skip`/`limit` options of `countDocuments` alter the counted total:

~~~javascript
db.orders.countDocuments(filter, {
  skip: 2,
  limit: 2
});
~~~

With 6 matching documents, this command counts after applying `skip` and `limit`, returning `2` **instead of the total 6**.

For an API returning `totalMatching`, pass only the **business filter** to the count; pagination parameters apply to the query fetching `items`.

## 5. Estimating with estimatedDocumentCount()

### 5.1. Fundamental Difference

~~~javascript
db.orders.estimatedDocumentCount();
~~~

`estimatedDocumentCount()` returns an **estimated count for the entire collection**, using storage statistics/metadata. It typically avoids executing a predicate scan like `countDocuments(filter)`, making it lighter when you only need collection scale.

However, this API **does not accept a filter** to count only PAID orders or `tenant-A`.

Comparison:

~~~javascript
// Exact count with filter:
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
});

// Estimated count of the entire collection:
db.orders.estimatedDocumentCount();
~~~

On the sample data, the first returns **6**. The second may return near or equal to **24**, which is in no way an estimate of the 6 filtered documents.

### 5.2. When Is It Appropriate?

Suitable when:

- A dashboard only needs "roughly N documents" in a collection.
- Charts tracking storage growth over time.
- Data is viewed at the whole-collection level without requiring per-record precision.
- Lower latency matters more than strict accuracy.

Unsuitable when:

- Counting total PAID orders for a tenant.
- Financial reconciliation or regulatory reporting.
- Using counts for business decisions such as remaining quota/transactions.
- A UI needs exact total pages for a filtered view.

### 5.3. Why Can Estimates Drift?

Storage statistics may not reflect exact document counts the way a query scan does, especially during certain operational events, crash recovery, or sharded cluster states.

Understand the difference between:

- **There are 24 documents in the lab and the estimate returns 24:** just one observation.
- **Every estimate is always exact:** an unwarranted conclusion.

If a product displays an estimate, label it clearly as "estimated" or attach measurement metadata.

### 5.4. Do Not Derive Filtered Estimates from Whole-Collection Totals

Suppose a whole collection is estimated at 5 million documents. You cannot use that number to claim `tenant-A` has 5 million, or that `PAID` accounts for 20%, without a sound distribution model.

Estimating **filtered counts** requires dedicated strategies such as statistically sound sampling, per-group maintained counters, or cached computed counts. Those bring their own margins of error and costs, rather than being an automatic feature of `estimatedDocumentCount()`.

## 6. Aggregation $count

The `$count` stage counts documents after filtering and transformation stages:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $count: "total" }
]);
~~~

Output on the sample dataset:

~~~javascript
[{ total: 6 }]
~~~

If zero input documents match:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "not-existing" } },
  { $count: "total" }
]);
~~~

The pipeline returns an **empty array**, rather than synthesizing a `{total:0}` document.

You can normalize this in the application layer:

~~~javascript
const counted = db.orders.aggregate([
  { $match: { tenantId: "not-existing" } },
  { $count: "total" }
]).toArray();

const total = counted.length > 0 ? counted[0].total : 0;
print(total);
~~~

### 6.1. Counting After Transformations: Know What You Are Counting

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $group: { _id: "$customerId" } },
  { $count: "totalCustomers" }
]);
~~~

This pipeline counts distinct `customerId` values after `$group`, not original orders. Similarly, counting after `$unwind` may count **array elements**, no longer the original order documents.

`$count` is flexible, not a "zero-cost shortcut": all documents entering the stage from upstream transformations still have to be processed through the pipeline.

## 7. Offset Pagination: skip and limit

### 7.1. How It Works

With 1-based page numbers:

\[
\text{offset}=(\text{page}-1)\times\text{pageSize}
\]

Querying page 2 with `pageSize` 2:

~~~javascript
const page = 2;
const size = 2;
const offset = (page - 1) * size;

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(offset)
.limit(size);
~~~

Expected results:

| Page | Offset | IDs |
|---|---:|---|
| 1 | 0 | `ord-018`, `ord-015` |
| 2 | 2 | `ord-012`, `ord-009` |
| 3 | 4 | `ord-006`, `ord-003` |
| 4 | 6 | No documents |

### 7.2. Stable Sorting Is Critical

If you sort only by `createdAt` and two documents share the same timestamp, their relative order may be non-deterministic. Appending `_id`, a unique key, to the end of the sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

creates deterministic ordering on timestamp ties. Avoid paginating on "natural" document order when an API must serve consecutive pages reliably.

### 7.3. Fetching Items and Total with Two Commands

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const page = 2;
const size = 2;
const offset = (page - 1) * size;

const items = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .skip(offset)
  .limit(size)
  .toArray();

const total = db.orders.countDocuments(filter);

const result = {
  items: items,
  page: page,
  pageSize: size,
  returnedCount: items.length,
  total: total,
  totalPages: Math.ceil(total / size),
  hasNext: offset + items.length < total
};

printjson(result);
~~~

When data is unchanged, `total = 6`, `totalPages = 3`, `items.length = 2`.

Two commands can run sequentially or concurrently depending on application design, yet **they do not automatically share a single point-in-time snapshot**. An insert or delete between them can make `items` and `total` temporarily inconsistent.

### 7.4. Deep Skip Incurs Cost

`skip(100000)` does not mean MongoDB jumps instantaneously to the 100,001st record. Under many query plans, the server still has to step through preceding results to discard them. Hence, deep pages typically suffer latency growing with offset.

Even with an index aiding the sort, a huge offset may still traverse many index entries. This is one reason to consider **seek/keyset pagination** for large lists with "Load more" navigation.

## 8. Using $facet to Fetch Page and Count in One Command

Aggregation `$facet` processes the same input stream through multiple branches:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const page = 2;
const size = 2;
const offset = (page - 1) * size;

db.orders.aggregate([
  { $match: filter },
  {
    $facet: {
      metadata: [
        { $count: "total" }
      ],
      data: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $skip: offset },
        { $limit: size },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ]
    }
  },
  {
    $project: {
      data: 1,
      total: {
        $ifNull: [
          { $arrayElemAt: ["$metadata.total", 0] },
          0
        ]
      }
    }
  }
]);
~~~

Output shape:

~~~javascript
[
  {
    data: [
      { _id: "ord-012", /* selected fields */ },
      { _id: "ord-009", /* selected fields */ }
    ],
    total: 6
  }
]
~~~

Advantages:

- A single aggregation command returns both data and total.
- Keeps filter logic unified within one pipeline.
- Reduces client–server round trips compared to two separate commands.
- Useful when data already passes through upstream transformations before pagination.

Drawbacks and limits:

- The `metadata` branch still has to **count all** matching documents; `data.limit(2)` does not make the count branch stop after 2 documents.
- `$facet` carries memory overhead and result size limits.
- Sorting inside a facet branch may not leverage indexes the same way a standalone `find().sort()` query does.
- For very broad filters, the count branch still dominates latency.

**Important:** `$facet` is not a "free exact count". Before adopting it by default, compare the plan and latency of the facet pipeline against two independent queries on representative data.

### 8.1. Why Is $ifNull Needed?

When a filter matches nothing, the `$count` branch can produce an empty array. The expression:

~~~javascript
{
  $ifNull: [
    { $arrayElemAt: ["$metadata.total", 0] },
    0
  ]
}
~~~

normalizes that case to `total: 0`. Failing to handle this can leave `total` missing or `null` in the response.

### 8.2. Place $match Before $facet

With filter:

~~~javascript
{ tenantId: "tenant-A", status: "PAID" }
~~~

putting `$match` before `$facet` narrows the document stream entering every branch and gives the filter an opportunity to use indexes. Do not place `$facet` at the start of the pipeline assuming each branch will optimize as well as an independent query.

## 9. Accuracy and Consistency Are Two Different Concerns

A count can return an exact number at one instant, yet while a user switches pages, the underlying data can change.

Example:

~~~text
T0: 6 PAID orders exist
T1: countDocuments(filter) returns total = 6
T2: A new PAID order is inserted
T3: find(filter).sort(...).limit(2) sees the new set of 7 orders
T4: API returns items from the new state alongside total = 6
~~~

Here `countDocuments` did not "miscount". The issue is **two commands observing data at two different instants**.

### 9.1. Types of Consistency Requirements

| Need | Typical guarantee required |
|---|---|
| News feeds, actively changing order lists | Slightly stale total or omitting total is acceptable |
| Admin views with reference counts | Exact count at query time, updates over time acceptable |
| Periodic reconciliation reports | Consistent dataset via period cutoffs or snapshots |
| Transactional quotas / usage limits | Atomic updates, counters/transactions; never rely on pagination counts |

Separate **accuracy of the counting algorithm** from **point-in-time consistency across multiple requests**.

### 9.2. Is a Single Pipeline Always an Absolute Snapshot?

`$facet` runs its branches over the input of a single command, yet you should not claim all reads are locked to a single snapshot against concurrent writes without considering read concern.

MongoDB provides read concern levels and, in supported topologies/contexts, snapshot reads or transactions for stronger guarantees. However, those require evaluating topology, version, resource costs, and snapshot retention time.

**Do not hold a transaction open across multiple paginated HTTP requests** just to keep pages scrolled over several minutes on the same snapshot, unless there is a special requirement and a fitting operational design.

### 9.3. New Inserts and Offsets

Suppose page 1 returns `ord-018`, `ord-015`. Before the user loads page 2, a newer order is inserted at the head of the ordering.

With `skip(2)`, page 2 over the updated dataset may repeat a document already seen on page 1 or skip an older document due to positional shifting. That is an inherent trait of offset pagination on mutating lists.

## 10. Skipping Total: Determining hasNext with limit(pageSize + 1)

In many interfaces, users only need to know whether **more data exists** to show a "Load more" button—`totalPages` is unnecessary.

A common technique:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const size = 2;

const fetched = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(size + 1)
  .toArray();

const items = fetched.slice(0, size);
const hasNext = fetched.length > size;

printjson({
  items: items,
  returnedCount: items.length,
  hasNext: hasNext
});
~~~

On the sample data, `items` includes `ord-018` and `ord-015`. The third record, `ord-012`, is used solely to detect `hasNext = true`; it is not returned in the first page's list.

**Benefit:** the server only needs to find one document past `pageSize`, instead of computing the exact count for the entire filter.

**Limitation:** if you still use `skip(offset)` to reach deep pages, offset cost still grows. To avoid deep skips, combine this with seek pagination.

## 11. Seek/Keyset Pagination by Sort Key

### 11.1. Distinguishing Two Meanings of Cursor

In MongoDB, a cursor is an object returning query results in batches. In web APIs, a **cursor token** is usually an application-layer value encoding the previous page's position. That token does not automatically appear from `find()` as a cross-request pagination ID.

With descending sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

you can use the `createdAt` and `_id` pair of the previous page's last document as the anchor.

### 11.2. Fetching the First Page

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const size = 2;

const fetched = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(size + 1)
  .toArray();

const firstPage = fetched.slice(0, size);
const hasNext = fetched.length > size;
const last = firstPage[firstPage.length - 1];

printjson({
  lastId: last._id,
  hasNext: hasNext
});
~~~

On the sample data, `last._id = "ord-015"`.

### 11.3. Fetching the Next Page with Range Conditions

Under descending order on both keys, a document follows `last` when:

- `createdAt` is less than `last.createdAt`; or
- `createdAt` equals `last.createdAt` and `_id` is less than `last._id`.

~~~javascript
const after = {
  $or: [
    { createdAt: { $lt: last.createdAt } },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
};

const nextFetched = db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  ...after
})
.sort({ createdAt: -1, _id: -1 })
.limit(size + 1)
.toArray();

const secondPage = nextFetched.slice(0, size);
const nextHasNext = nextFetched.length > size;

printjson({
  ids: secondPage.map(x => x._id),
  hasNext: nextHasNext
});
~~~

Page two returns `ord-012` and `ord-009`, and since `ord-006` remains, `nextHasNext = true`.

### 11.4. Why Must a Secondary _id Key Be Included?

If two documents share the same `createdAt`, using only `createdAt < lastCreatedAt` can **drop** unread documents with the same timestamp. Using `createdAt <= lastCreatedAt` can repeat the last document from the previous page.

A unique tie-breaker like `_id` yields deterministic ordering and an exact resumption condition.

### 11.5. Pagination Tokens in APIs

A response may look like:

~~~json
{
  "items": [
    { "_id": "ord-018", "status": "PAID" },
    { "_id": "ord-015", "status": "PAID" }
  ],
  "pageSize": 2,
  "hasNext": true,
  "nextCursor": "<opaque-token>"
}
~~~

`nextCursor` is application-defined and can store the last document's sort key pair along with version, filter, or tenant info. When designing tokens:

- Preserve exact types of `createdAt` and `_id` when decoding.
- Bind the token to the corresponding sort, filter, and tenant.
- Validate the token; consider signing/HMAC to prevent client payload tampering.
- Never treat base64 as security encryption.
- Do not put sensitive data inside readable tokens.
- Define rules for handling expired or invalid tokens.

### 11.6. What Does Seek Solve?

Seek pagination is beneficial when:

- Datasets are large and users browse many consecutive pages.
- Indexes align with the sort order and filter.
- Random jumping to arbitrary page numbers is unnecessary.
- The product accepts `hasNext` instead of exact `totalPages`.

Seek does not automatically keep all pages on a single snapshot. If a document updates its sort key or leaves the filter between requests, users can still observe changes. Choose sort keys that rarely mutate and define behavior under concurrent changes.

## 12. Accuracy, Latency, and System Load Trade-offs

API response time can be modeled as:

\[
T_{\text{response}} \approx T_{\text{page}}
+ T_{\text{count}}
+ T_{\text{network}}
+ T_{\text{serialization}}
+ T_{\text{application}}
\]

This simple model assumes sequential execution. If page and count run in parallel, total duration may approach the slower branch plus overhead, yet the database still performs both workloads.

Illustrative example, **not a benchmark**:

~~~text
Page query:      15 ms
Exact count:    280 ms
Serialization:   10 ms
Network:         20 ms

Total sequential latency can be dominated by the exact count.
~~~

Replacing exact count with `estimatedDocumentCount()` is valid only if the business wants a **whole-collection estimate**. Never shave 280 ms by putting a whole-collection estimate into a tenant/status-filtered total field.

Options to consider:

1. **Optimize filters/indexes** first.
2. **Omit total** when UX only needs `hasNext`.
3. **Cache counts** per filter with clearly labeled staleness.
4. **Maintain dedicated counters** if business rules and traffic justify it.
5. **Split out a count endpoint** so it does not block rendering the first page.
6. **Use `$facet`** if a single pipeline proves beneficial on your dataset.
7. **Eliminate deep skips** via seek pagination.
8. **Use snapshots/transactions** when strict consistency is required, weighing technical costs.

No single option wins for every workload.

## 13. Checking Performance with explain and Indexes

### 13.1. Query Plan for the Data Page

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(2)
.explain("executionStats");
~~~

In the output, inspect:

| Field or stage | Meaning |
|---|---|
| `winningPlan` | Plan selected by optimizer |
| `IXSCAN` | Index scan |
| `COLLSCAN` | Collection scan |
| `SORT` | Explicit sort stage, potentially resource-intensive |
| `totalKeysExamined` | Number of index keys inspected |
| `totalDocsExamined` | Number of documents inspected |
| `nReturned` | Number of documents returned |
| `executionTimeMillis` | Execution time reported by explain |

With 24 documents, the query planner may choose a collection scan; that does not imply the index is ineffective in production.

### 13.2. Query Plan for the Count

Use an equivalent aggregation to inspect the plan:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $count: "total" }
]);
~~~

Depending on the optimizer, the plan may contain `COUNT_SCAN`, `IXSCAN`, or other stages. Do not assume every MongoDB version always shows one fixed stage name.

### 13.3. Index Matching Filter and Sort

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

The two leading equality predicates narrow the range, while the trailing keys support the sort. Still, an exact count must determine how many keys or documents match the filter; an index **does not turn every filtered count into a constant-time metadata lookup**.

If real filters include additional fields such as `active` or date ranges, evaluate selectivity and corresponding query plans. Adding indexes also increases write overhead and storage footprint.

### 13.4. Bounding Count Execution Time

Some drivers/APIs support setting a time limit, such as in `mongosh`:

~~~javascript
db.orders.countDocuments(
  {
    tenantId: "tenant-A",
    status: "PAID"
  },
  { maxTimeMS: 2000 }
);
~~~

`maxTimeMS` caps server execution time per its supported mechanics; **it does not make counting faster**. If a count times out, the application can return the page without a total or fall back to a labeled cached count. Never turn a timeout into `total: 0`, because zero asserts no matching documents exist.

## 14. Controlled Caching of Exact Counts

One way to cut latency when identical filters are queried frequently is caching count results:

~~~text
cache key:
  tenantId + status + search criteria
  + data permissions + filter logic version

cache value:
  total = 12450
  calculatedAt = <timestamp>
  totalKind = "cached"
~~~

Workflow:

1. Request arrives with a normalized filter.
2. Check cache keyed by filter and authorization scope.
3. On a fresh cache hit within acceptable age, return the stored count and timestamp.
4. On a miss, compute the exact count and store it.
5. Design TTL or invalidation when data changes.

### 14.1. Advantages

- Avoids repeating expensive counts in short intervals.
- Suits dashboards or lists where users accept slightly stale numbers.
- Decouples count refreshes from the page-rendering critical path.

### 14.2. Risks

- Counts become stale after inserts, deletes, or updates moving documents into/out of the filter.
- Missing tenant or filter parts in the cache key causes wrong numbers and data leaks.
- High filter cardinality yields low cache hit rates.
- Exact invalidation can be harder than recomputing the count.
- Caching a bare number without `calculatedAt` hides reliability from users.

Prefer representing it as:

~~~json
{
  "total": 12450,
  "totalKind": "cached",
  "totalAsOf": "2026-10-25T09:00:00Z"
}
~~~

This is a data-contract template; the actual timestamp must reflect when the cache entry was computed, not an arbitrary value.

## 15. Maintaining Dedicated Counters

If PAID order counts are read continuously, you can store a separate summary document per tenant/status:

~~~javascript
{
  _id: "tenant-A:PAID",
  tenantId: "tenant-A",
  status: "PAID",
  total: NumberLong("6"),
  updatedAt: ISODate("2026-10-25T09:00:00Z")
}
~~~

This document illustrates **counter structure only**—MongoDB does not maintain it automatically. Application logic must update it:

- Insert PAID order → increment PAID counter.
- Delete PAID order → decrement PAID counter.
- Status transition NEW → PAID → decrement NEW (if tracked) and increment PAID.
- Transition PAID → CANCELLED → decrement PAID, increment CANCELLED if tracked.

Advantage: reading a single counter document can be extremely fast.

Disadvantage: you must synchronize source document mutations with counter updates. Multi-document transactions (on supported topologies) or idempotent event-driven eventual consistency with reconciliation can limit drift as required. However, duplicated or dropped events will make counters inaccurate.

Hot counters updated at high frequency can also become write contention hotspots. Measure your workload and redesign if needed.

## 16. Filtered Estimates: Not estimatedDocumentCount

If you genuinely need an estimate for a filter that is expensive to count exactly, consider:

- Random sampling of sufficient size with statistical error bounds.
- Maintaining histograms/counters for popular search segments.
- Caching previously computed counts for that exact filter.
- Periodic rollups across key dimensions.

Every approach carries assumptions:

| Method | Why it can be inaccurate |
|---|---|
| Sampling | Non-representative samples, small sample size, rare groups |
| Periodic rollup | Writes arriving after rollup timestamp |
| Event-based counter | Duplicate/dropped events or inconsistent updates |
| Cached count | Stale cache or mismatched filter key |
| Collection metadata | Cannot directly represent arbitrary filters |

Never use an estimate lacking defined error bounds as audit figures. Financial, legal, or quota-enforcing applications require dedicated exact/consistent workflows.

## 17. Designing Pagination APIs by Requirement

### 17.1. Exact Total and Page Numbers

~~~json
{
  "items": [
    { "_id": "ord-018", "status": "PAID" },
    { "_id": "ord-015", "status": "PAID" }
  ],
  "page": 1,
  "pageSize": 2,
  "total": 6,
  "totalPages": 3,
  "totalKind": "exact"
}
~~~

Fits admin tables needing direct page jumps or reports requiring exact totals. Remember that an exact total reflects query time and can shift as new documents arrive.

### 17.2. Cached Total

~~~json
{
  "items": [
    { "_id": "ord-018" },
    { "_id": "ord-015" }
  ],
  "page": 1,
  "pageSize": 2,
  "total": 6,
  "totalKind": "cached",
  "totalAsOf": "2026-10-25T09:00:00Z"
}
~~~

If the product tolerates stale counts, expose the timestamp clearly. Never drive sensitive inventory or financial decisions from a cached total.

### 17.3. Omitting Total

~~~json
{
  "items": [
    { "_id": "ord-018" },
    { "_id": "ord-015" }
  ],
  "pageSize": 2,
  "hasNext": true,
  "nextCursor": "<opaque-token>"
}
~~~

Suited for infinite scroll and large feeds. Users know more items exist without waiting on an exact count.

### 17.4. On-Demand Total Calculation

You can return the first page fast while the UI requests the count from a separate endpoint when needed. This cuts initial page-open latency without eliminating count cost; you must handle filter changes, screen exits, or count responses arriving after page data.

## 18. Java Driver: Exact Count and Pagination

Assuming you already have a `MongoDatabase` instance `database` using the MongoDB Java Driver:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.CountOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;

MongoCollection<Document> orders = database.getCollection("orders");

Bson filter = and(
    eq("tenantId", "tenant-A"),
    eq("status", "PAID")
);

int page = 1;
int pageSize = 2;
int offset = (page - 1) * pageSize;

long total = orders.countDocuments(filter);

List<Document> items = orders.find(filter)
    .sort(descending("createdAt", "_id"))
    .skip(offset)
    .limit(pageSize)
    .into(new ArrayList<>());

long totalPages = (total + pageSize - 1L) / pageSize;

System.out.println("Items returned: " + items.size());
System.out.println("Total: " + total);
System.out.println("Total pages: " + totalPages);
~~~

This shows the query logic, not a standalone Java program with `MongoClient` setup. Production applications must bound `pageSize`, validate `page >= 1`, and guard against integer overflow when computing offsets or total pages.

### 18.1. Whole-Collection Estimate

~~~java
long approximateSize = orders.estimatedDocumentCount();
~~~

Never assign `approximateSize` as the total for a tenant/status filter.

### 18.2. CountOptions to Bound Execution Time

~~~java
import java.util.concurrent.TimeUnit;
import com.mongodb.client.model.CountOptions;

CountOptions options = new CountOptions()
    .maxTime(2, TimeUnit.SECONDS);

long total = orders.countDocuments(filter, options);
~~~

Handle timeout exceptions explicitly; never treat a timeout as a total of zero.

### 18.3. Skip Counting, Fetch One Extra Record

~~~java
List<Document> fetched = orders.find(filter)
    .sort(descending("createdAt", "_id"))
    .limit(pageSize + 1)
    .into(new ArrayList<>());

boolean hasNext = fetched.size() > pageSize;

List<Document> items = fetched.subList(
    0,
    Math.min(pageSize, fetched.size())
);
~~~

This illustrates the first page. When paginating across multiple requests, store the last sort anchor and construct a seek filter as shown in Section 11.

### 18.4. Never Drain an Entire Cursor Just to Count

For large result sets, avoid:

~~~java
// Should not be used as a total counting strategy:
List<Document> all = orders.find(filter)
    .into(new ArrayList<>());

long total = all.size();
~~~

This transfers every matching document over the network into application memory solely to check its length, wasting I/O, bandwidth, and RAM. Use `countDocuments(filter)` or a purpose-built counting strategy.

## 19. MongoDB Compass: Inspecting Counts and Data Pages

Compass provides a visual collection browser and may show different count/stat figures depending on version. Do not assume every "Documents" number shown in the UI is an exact post-filter count.

Practice steps:

1. Connect Compass to the same MongoDB Server/cluster as `mongosh`.
2. Open `pagination_count_lab.orders`.
3. In the **Documents** tab, enter the filter:

   ~~~json
   {"tenantId":"tenant-A","status":"PAID"}
   ~~~

4. If a **Sort** box is available, enter:

   ~~~json
   {"createdAt":-1,"_id":-1}
   ~~~

5. Inspect the leading documents and verify `ord-018`, `ord-015`.
6. In `mongosh`, run `countDocuments(filter)` to confirm the exact filtered count of **6**.
7. Run `estimatedDocumentCount()` to compare against the whole-collection estimate.
8. If Compass has **Aggregations**, test `$match` + `$count` or `$facet`.
9. If **Explain Plan** is available, check whether the page query uses an index or has to sort/scan heavily.
10. Switch the filter to `tenant-B` and observe both page data and count change per tenant.

If Compass figures differ from `mongosh`, check the active filter, UI refresh state, whether the metric is estimated/cached, and the time of observation.

## 20. Common Mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| Total always equals `pageSize` | Using `items.length` as total | Use a filtered exact count or state total is not computed |
| Total equals whole collection despite tenant filter | Using `estimatedDocumentCount()` | Never use whole-collection estimates for filtered totals |
| Page shows 2 PAID orders yet total = 18 | Count omitted `status` predicate | Use the exact same business filter for page and count |
| Count returns 0 while page has data | Mismatched filters or data changed between commands | Verify identical filters and consistency policy |
| Aggregation `$count` returns empty array | Zero input documents | Normalize to 0 in application layer |
| `$facet` is still slow | Count branch scans entire match set; sort/memory overhead | Run `explain` and consider dropping exact total |
| High page numbers open slowly | `skip` must step past many results | Switch to seek/keyset pagination |
| Same document appears on two pages | Offset shifted due to inserts/deletes | Sort with a tie-breaker; use seek when appropriate |
| `totalPages` is wrong | Cached/estimated total treated as exact | Label data source and adjust UX |
| Changing filter leaves total unchanged | Cache key missing parameters | Key cache by normalized filter and permission scope |
| Count timeout displayed as 0 | Improper fallback | Report unavailable status, valid cached value, or error |
| Count inflates after `$unwind` | Counting array elements instead of root documents | Verify target unit and `$count` stage placement |
| Added indexes yet count remains slow | Matching range is still huge | Inspect keys/docs examined; reconsider exact total requirement |
| Cursor mistaken for a cross-request snapshot | Token only encodes pagination position | Handle dynamic data and choose stable sort keys |

## 21. Comprehensive Practice Exercises

The exercises below assume the collection holds only the 24 sample documents without extra records or external mutations.

### Exercise 1. Conditional Exact Counts

~~~javascript
db.orders.countDocuments({});
db.orders.countDocuments({ tenantId: "tenant-A" });
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
});
~~~

**Results:** 24, 18, 6. Explain why the first count is not a valid total for `tenant-A`'s PAID view.

### Exercise 2. Exact vs. Estimated Counts

~~~javascript
db.orders.countDocuments({});
db.orders.estimatedDocumentCount();
~~~

Both values may match in this lab. Explain why that does not prove `estimatedDocumentCount()` supports filtering or is always strictly exact.

### Exercise 3. Offset Pagination

Use `pageSize` 2, `tenant-A`/`PAID` filter, and descending sort on `createdAt`, `_id`:

~~~javascript
function getPage(page) {
  return db.orders.find({
    tenantId: "tenant-A",
    status: "PAID"
  })
  .sort({ createdAt: -1, _id: -1 })
  .skip((page - 1) * 2)
  .limit(2)
  .toArray()
  .map(x => x._id);
}

printjson(getPage(1));
printjson(getPage(2));
printjson(getPage(3));
printjson(getPage(4));
~~~

**Results:** page 1 = 018, 015; page 2 = 012, 009; page 3 = 006, 003; page 4 empty.

### Exercise 4. Counting with $count

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $count: "total" }
]);
~~~

Output has `total: 6`. Change tenant to a non-existent value, explain why the result is empty, and show how to convert it to `total = 0`.

### Exercise 5. Single $facet Pipeline

Use the pipeline from Section 8 to retrieve simultaneously:

- `data`: the two documents of page 2.
- `total`: 6.

Explain why `$facet` is a single command yet its count branch still has to traverse the entire counted range.

### Exercise 6. hasNext Without Total

~~~javascript
const fetched = db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();

const items = fetched.slice(0, 2);
const hasNext = fetched.length > 2;
~~~

**Result:** `items` contains `ord-018` and `ord-015`; `hasNext = true` because of the lookahead document.

### Exercise 7. Seek Pagination

Use document `ord-015` as the end anchor of page 1. Construct the filter:

~~~javascript
const last = db.orders.findOne({ _id: "ord-015" });

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: last.createdAt } },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(2);
~~~

**Result:** `ord-012`, `ord-009`. Why must `_id` also be compared on timestamp ties?

### Exercise 8. Two Observation Instants

In the practice database:

1. Count `tenant-A` PAID orders.
2. Insert a new `tenant-A` PAID record with a newer `createdAt`.
3. Fetch the first page and inspect the result.
4. Count again and compare before/after totals.

Example adding one document:

~~~javascript
db.orders.insertOne({
  _id: "ord-999",
  tenantId: "tenant-A",
  status: "PAID",
  createdAt: new Date(Date.UTC(2026, 10, 1, 9, 0, 0)),
  amount: NumberDecimal("99.50"),
  active: true
});
~~~

After the exercise, remove the added test document:

~~~javascript
db.orders.deleteOne({ _id: "ord-999" });
~~~

**Question:** Why can an exact total measured before the insert differ from the total measured after the insert? Did the counting algorithm fail?

### Exercise 9. Explaining Indexes

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $count: "total" }
]);

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(2)
.explain("executionStats");
~~~

Note any index scan/collection scan, `totalKeysExamined`, and `totalDocsExamined`. With 24 documents, do not extrapolate benchmarks for large production systems.

### Exercise 10. Selecting a Strategy from Requirements

| Product requirement | Appropriate starting strategy |
|---|---|
| Small admin table needing exact page numbers | `countDocuments(filter)` + page query |
| Dashboard showing approximate whole-collection document count | `estimatedDocumentCount()` |
| Report counting results after multiple aggregation stages | `$count` |
| API needing page and total from one pipeline | `$facet` after measuring cost |
| Large feed needing only "Load more" | `limit(pageSize + 1)` and seek |
| Expensive filter where UI tolerates slightly stale count | Cached count with timestamp and filter key |
| Counter read very frequently at low latency | Dedicated maintained counter collection with consistency rules |
| Reconciliation report requiring single point-in-time data | Appropriate snapshot/read concern/transaction design |

## 22. Application Design Reminders

- **Filtered exact count:** use `countDocuments(filter)` or an aggregation counting the exact target dataset.
- **Whole-collection estimate:** use `estimatedDocumentCount()` only when no filter is needed and approximation is acceptable.
- **A response containing a total is not timelessly consistent:** data mutates; distinguish exact counting algorithms from snapshot timing.
- **Never confuse page count with total set count:** `items.length` is not `totalMatching`.
- **`$facet` does not make counting free:** it still counts the entire matching set and can increase memory or sorting cost.
- **Deep pagination:** `skip` has traversal cost; seek pagination and stable sort indexes are usually more efficient.
- **Do not force a count when total is unnecessary:** `pageSize + 1` delivers `hasNext`.
- **Enforce tenant security consistently:** page queries, count queries, caches, and cursor tokens must share the exact same permission scope.
- **Classify total provenance:** `exact`, `estimated`, `cached`, and `not_computed` represent distinct API contracts.
- **Measure before optimizing:** inspect `explain`, keys/docs examined, server duration, and end-to-end latency on real workloads.

In MongoDB, **counting total records is not just a query operation—it is a pagination UX and architecture decision**. By defining the exact level of precision actually needed, you can significantly cut latency without misrepresenting the meaning of displayed data.
