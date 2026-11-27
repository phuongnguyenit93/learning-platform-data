# Keyset Pagination with Composite Keys and Stable Ordering in MongoDB

When a collection has hundreds of thousands or millions of documents, applications rarely return every record at once. Order lists, activity logs, transaction histories, or feeds require **pagination** to return small slices of data. The familiar approach is `skip() + limit()`, yet as page depth grows, MongoDB may have to traverse many results before reaching the requested page. Documents inserted or deleted while users browse pages can also cause duplicates or skipped items.

**Keyset pagination (also known as seek pagination)** uses the **sort key values of the previous page's boundary record** as an anchor to fetch the next page. To ensure deterministic ordering when multiple documents share the same timestamp or score, we use a **composite key** consisting of the primary sort field and a **unique tie-breaker field**, typically `_id`.

This lesson covers establishing stable ordering, designing lexicographic filters, forward/backward pagination, building API cursor tokens, designing compound indexes, and understanding the limits when data mutates between requests.

## 1. Why Does Pagination Need Stable Ordering?

Suppose an `orders` collection is sorted by `createdAt` descending:

~~~javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1 })
  .limit(3);
~~~

When two orders share the **same `createdAt`**, sorting solely by timestamp **does not determine** which order comes first. MongoDB does not guarantee a fixed ordering among documents with identical sort values. Depending on the execution plan, tied records can change relative positions across queries.

For example, three orders occur in the exact same second:

| orderCode | createdAt |
| --- | --- |
| O-105 | 2026-05-03T10:00:00Z |
| O-106 | 2026-05-03T10:00:00Z |
| O-107 | 2026-05-03T10:00:00Z |

With `sort({ createdAt: -1 })`, all three are equal under the sort key. If a page boundary cuts through this group, an item might appear on two pages or be missed when the application runs two separate queries.

How to standardize the ordering:

~~~javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3);
~~~

The **`(createdAt, _id)`** combination creates a deterministic order when `_id` is unique across the paginated result set:

1. Compare `createdAt` first; **newer** timestamps come first.
2. If two documents share the same `createdAt`, compare `_id`; **larger** values come first.
3. Since no two documents share both keys, each document has an unambiguous position in the ordering.

**Stable ordering does not mean immutable data.** If inserts, deletes, or updates to sort fields occur between two reads, a document's logical position can still shift. Composite keys solve *sort ties*; the later section on mutating data explains the remaining limitations.

## 2. Offset Pagination vs. Keyset Pagination

### 2.1. Offset: skip + limit

~~~javascript
const pageSize = 20;
const pageNumber = 100;

db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .skip((pageNumber - 1) * pageSize)
  .limit(pageSize);
~~~

For page 100, MongoDB must skip **1,980 results** in sorted order before returning at most 20 documents. Indexes can assist sorting and traversal, yet `skip()` at deep offsets still has to walk through the skipped items.

Offset is advantageous when a UI needs direct jumps like "page 5" or "page 100" and the dataset is relatively small and low-churn. Its drawbacks are deep-read costs and positional drift when new data is inserted or old data is deleted.

### 2.2. Keyset: Starting from the Last Item's Key

Instead of "skip 1,980 records", the application passes an anchor:

~~~text
After the record with:
  createdAt = 2026-05-03T10:00:00Z
  _id       = ObjectId("000000000000000000000006")
~~~

MongoDB finds records **located after the anchor** in the same sort order. With **descending** sort on both keys, the next-page predicate is:

~~~text
createdAt < last.createdAt
OR
(createdAt = last.createdAt AND _id < last._id)
~~~

This exact condition ensures we do not drop records with the **same timestamp** but a smaller `_id`.

### 2.3. Quick Comparison

| Criterion | Offset (`skip/limit`) | Keyset (seek/cursor token) |
| --- | --- | --- |
| How pages are identified | Page number and skipped record count | Sort keys of a boundary record |
| Accessing very deep pages | Can incur cost traversing many results | Can seek from the anchor with a proper index |
| Inserts/deletes before current page | Easily causes offset drift | Largely unaffected by changes before the anchor |
| Requires stable sort | Strongly recommended | **Mandatory** for correct pagination |
| Jumping to an arbitrary page N | Easy using page numbers | Not direct; typically sequential via tokens |
| Suitable APIs | Small, low-churn tables | Infinite scroll, activity feeds, orders, logs |
| When sort key is mutated mid-pagination | Can still drift | Can still duplicate/skip; requires data policy |

In this lesson, a keyset "cursor" refers to a **token carrying sort-key position**. It **differs** from a MongoDB driver's **server-side cursor**, which is an internal mechanism for batch-reading query results. A keyset API can run a fresh `find()` query per page without keeping a server-side cursor open across multiple HTTP requests.

## 3. Practice Dataset with Duplicate Sort Keys

Open `mongosh` connected to MongoDB and run in a dedicated database:

~~~javascript
const lab = db.getSiblingDB("keyset_pagination_lab");

lab.orders.drop();

function order(idSuffix, code, date, status = "paid") {
  return {
    _id: ObjectId("0000000000000000000000" + idSuffix),
    tenantId: "T1",
    orderCode: code,
    createdAt: ISODate(date),
    status,
    amount: NumberInt(100 + parseInt(idSuffix, 16) * 10)
  };
}

lab.orders.insertMany([
  order("01", "O-101", "2026-05-01T10:00:00Z"),
  order("02", "O-102", "2026-05-02T10:00:00Z"),
  order("03", "O-103", "2026-05-02T10:00:00Z"),
  order("04", "O-104", "2026-05-03T10:00:00Z"),
  order("05", "O-105", "2026-05-03T10:00:00Z"),
  order("06", "O-106", "2026-05-03T10:00:00Z"),
  order("07", "O-107", "2026-05-04T10:00:00Z"),
  order("08", "O-108", "2026-05-05T10:00:00Z"),
  order("09", "O-109", "2026-05-05T10:00:00Z"),
  order("0a", "O-110", "2026-05-06T10:00:00Z", "pending"),
  order("0b", "O-111", "2026-05-06T10:00:00Z"),
  order("0c", "O-112", "2026-05-07T10:00:00Z")
]);
~~~

These `_id` values are crafted intentionally so ordering can be read by their suffix. This is **illustrative data**, not a pattern for generating `ObjectId`s in production systems. In applications, drivers usually auto-generate `ObjectId`s or use unique identifiers per data contract.

Read all `paid` orders:

~~~javascript
lab.orders.find(
  { tenantId: "T1", status: "paid" },
  { _id: 1, orderCode: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 });
~~~

Expected order:

| Position | orderCode | createdAt | `_id` suffix |
| ---: | --- | --- | --- |
| 1 | O-112 | May 07 10:00 | 0c |
| 2 | O-111 | May 06 10:00 | 0b |
| 3 | O-109 | May 05 10:00 | 09 |
| 4 | O-108 | May 05 10:00 | 08 |
| 5 | O-107 | May 04 10:00 | 07 |
| 6 | O-106 | May 03 10:00 | 06 |
| 7 | O-105 | May 03 10:00 | 05 |
| 8 | O-104 | May 03 10:00 | 04 |
| 9 | O-103 | May 02 10:00 | 03 |
| 10 | O-102 | May 02 10:00 | 02 |
| 11 | O-101 | May 01 10:00 | 01 |

`O-110` is excluded because it has `status: "pending"`. Dates in the table are May 2026 in UTC, matching the `ISODate` strings.

## 4. First Page: Fetching and Saving the Anchor

To read the first three orders, run:

~~~javascript
const pageSize = 3;

const firstPage = lab.orders.find(
  { tenantId: "T1", status: "paid" }
).sort({ createdAt: -1, _id: -1 })
 .limit(pageSize)
 .toArray();

firstPage.map(d => d.orderCode);
// ["O-112", "O-111", "O-109"]
~~~

The **last** item on the page has:

~~~javascript
const last = firstPage[firstPage.length - 1];

printjson({
  orderCode: last.orderCode,
  createdAt: last.createdAt,
  _id: last._id
});
~~~

The anchor for the next page is **`(createdAt of O-109, _id of O-109)`**. Do not take `createdAt` of the first item; and do not send only the date if multiple records can share the same timestamp.

Note: the first page takes no input cursor, yet it **must use the exact same sort** as subsequent pages.

## 5. Next Page with a Composite Key: Lexicographic Condition

### 5.1. Deriving the Correct Condition

Suppose the sort order is:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

To fetch a document that **comes after** `last`, there are exactly two cases:

1. `createdAt` is **smaller** than `last`'s timestamp.
2. `createdAt` **equals** `last`'s timestamp, while `_id` is **smaller** than `last._id`.

Written as a MongoDB filter:

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
~~~

Combined with the business filter:

~~~javascript
const secondPage = lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $lt: last.createdAt } },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
}).sort({ createdAt: -1, _id: -1 })
  .limit(pageSize)
  .toArray();

secondPage.map(d => d.orderCode);
// ["O-108", "O-107", "O-106"]
~~~

`O-108` shares the same `createdAt` as `O-109`, yet has a smaller `_id`, so it must appear at the very start of the next page. If you only filtered `createdAt < last.createdAt`, **O-108 would be skipped**.

### 5.2. Why Must Strict Comparison Be Used?

To paginate after the anchor under descending sort, use `$lt`—**do not use `$lte`** for both keys:

~~~javascript
// Incorrect for next page: the anchor document may reappear.
{
  $or: [
    { createdAt: { $lte: last.createdAt } },
    { createdAt: last.createdAt, _id: { $lte: last._id } }
  ]
}
~~~

With the snippet above, the anchor record itself can match and be returned again on the next page. Always use **strict comparisons** (`<` or `>`) matching the sort direction.

### 5.3. Never Use a Simple OR Across Both Key Conditions

Incorrect example:

~~~javascript
// WRONG: _id smaller than anchor is insufficient, as createdAt could be newer.
{
  $or: [
    { createdAt: { $lt: last.createdAt } },
    { _id: { $lt: last._id } }
  ]
}
~~~

The second branch is not constrained by **createdAt equals the anchor**, so it could wrongly include documents with a newer timestamp and a smaller `_id`. Lexicographic order requires that comparing the secondary key **only applies when the primary key is equal**.

### 5.4. The Page After the Second Page

Take the last item of page 2:

~~~javascript
const lastPage2 = secondPage[secondPage.length - 1];

const thirdPage = lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $lt: lastPage2.createdAt } },
    {
      createdAt: lastPage2.createdAt,
      _id: { $lt: lastPage2._id }
    }
  ]
}).sort({ createdAt: -1, _id: -1 })
  .limit(pageSize)
  .toArray();

thirdPage.map(d => d.orderCode);
// ["O-105", "O-104", "O-103"]
~~~

Page three still includes the two May 03 orders immediately following anchor `O-106`. This directly demonstrates that the **`_id` tie-breaker** walks cleanly through duplicate-key groups rather than jumping over them.

## 6. Reusable Forward Pagination Function

Instead of rewriting the filter on every page, wrap the query in a helper function in `mongosh`:

~~~javascript
const SORT_DESC = { createdAt: -1, _id: -1 };
const BASE_FILTER = { tenantId: "T1", status: "paid" };

function fetchNextPage(after = null, pageSize = 3) {
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw new Error("pageSize must be an integer between 1 and 100");
  }

  const filter = { ...BASE_FILTER };

  if (after) {
    filter.$or = [
      { createdAt: { $lt: after.createdAt } },
      {
        createdAt: after.createdAt,
        _id: { $lt: after._id }
      }
    ];
  }

  // Read 1 extra document to detect whether a next page exists.
  const fetched = lab.orders.find(filter)
    .sort(SORT_DESC)
    .limit(pageSize + 1)
    .toArray();

  const hasNextPage = fetched.length > pageSize;
  const items = fetched.slice(0, pageSize);
  const lastItem = items[items.length - 1];

  return {
    items,
    hasNextPage,
    nextCursor: hasNextPage && lastItem
      ? { createdAt: lastItem.createdAt, _id: lastItem._id }
      : null
  };
}
~~~

Test page by page:

~~~javascript
const p1 = fetchNextPage(null, 3);
printjson(p1.items.map(o => o.orderCode));
// ["O-112", "O-111", "O-109"]

const p2 = fetchNextPage(p1.nextCursor, 3);
printjson(p2.items.map(o => o.orderCode));
// ["O-108", "O-107", "O-106"]

const p3 = fetchNextPage(p2.nextCursor, 3);
printjson(p3.items.map(o => o.orderCode));
// ["O-105", "O-104", "O-103"]

const p4 = fetchNextPage(p3.nextCursor, 3);
printjson(p4.items.map(o => o.orderCode));
// ["O-102", "O-101"]
~~~

With the initial data, pages 1–3 all return `hasNextPage: true` and page 4 returns `hasNextPage: false`. The function only builds `nextCursor` when another page exists, preventing pointless client requests.

### Why Fetch `pageSize + 1` Records?

If you read only three documents, a page of three items **cannot tell you** whether a fourth item exists. Reading one extra:

~~~text
limit(4) -> [A, B, C, D]
returned to client -> [A, B, C]
hasNextPage -> true
nextCursor -> key of C, not D
~~~

**Do not use the lookahead item D's key as the cursor.** Because D was not returned to the client yet, anchoring on D would skip D altogether.

If results contain only 0–3 items, `hasNextPage` is false at query time. When data mutates continuously, this reflects only the state observed during that read.

## 7. Backward Pagination: Reversing Conditions and Reversing Results

APIs often need both "Next" and "Previous". Under the standard display order:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

to find records **preceding** the first item of the current page, the inverted condition is:

~~~text
createdAt > first.createdAt
OR
(createdAt = first.createdAt AND _id > first._id)
~~~

However, to get the **immediately preceding page**, you should read in **ascending order** to get the records closest to the anchor first, and then **reverse the result array** to restore descending display order.

Example going back from page 2:

~~~javascript
const firstPage2 = p2.items[0]; // O-108

const earlier = lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $gt: firstPage2.createdAt } },
    {
      createdAt: firstPage2.createdAt,
      _id: { $gt: firstPage2._id }
    }
  ]
}).sort({ createdAt: 1, _id: 1 })
  .limit(3)
  .toArray();

const previousPage = earlier.reverse();

previousPage.map(o => o.orderCode);
// ["O-112", "O-111", "O-109"]
~~~

Why not keep descending sort when querying previous? If thousands of records precede the anchor, `limit(3)` in descending order would grab **the very first three records of the entire list**, not **the three records closest to the current page**. Flipping the sort to ascending selects the items adjacent to the boundary first, and reversing restores the UI order.

### Backward Pagination Function with Lookahead

~~~javascript
function fetchPreviousPage(before, pageSize = 3) {
  if (!before || !(before.createdAt instanceof Date)) {
    throw new Error("Missing valid cursor of the page's first item");
  }
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw new Error("pageSize must be between 1 and 100");
  }

  const filter = {
    ...BASE_FILTER,
    $or: [
      { createdAt: { $gt: before.createdAt } },
      {
        createdAt: before.createdAt,
        _id: { $gt: before._id }
      }
    ]
  };

  const fetched = lab.orders.find(filter)
    .sort({ createdAt: 1, _id: 1 })
    .limit(pageSize + 1)
    .toArray();

  const hasEarlierPage = fetched.length > pageSize;
  const items = fetched.slice(0, pageSize).reverse();
  const firstItem = items[0];

  return {
    items,
    hasEarlierPage,
    previousCursor: hasEarlierPage && firstItem
      ? { createdAt: firstItem.createdAt, _id: firstItem._id }
      : null
  };
}

const prev = fetchPreviousPage({
  createdAt: p2.items[0].createdAt,
  _id: p2.items[0]._id
}, 3);

printjson(prev.items.map(o => o.orderCode));
// ["O-112", "O-111", "O-109"]
~~~

Here `hasEarlierPage: false` when the returned page is the very first page of the list. To step backward multiple times in a UI, the `before` token must be constructed from the **first item of the currently displayed page**, not the last item. On multi-page lists, each backward step continues using the first item of the newly returned group.

### Distinguishing the Two UI Cursor Types

| Button | Anchor from current page | Condition under descending sort | Sort used when querying |
| --- | --- | --- | --- |
| Next | **Last** item | `(createdAt, _id) < anchor` | `{-1, -1}` |
| Previous | **First** item | `(createdAt, _id) > anchor` | `{1, 1}` then reverse |

Use clear names like `after` and `before`, or `nextCursor` and `previousCursor`. A cursor carrying only key values without directional semantics is easily misused in APIs.

## 8. Generalization: Composite Keys with Two or More Fields

The core idea of keyset pagination is **lexicographic comparison**:

~~~text
sort by (K1, K2, K3):
- compare K1
- if K1 is equal, compare K2
- if K1 and K2 are equal, compare K3
~~~

The final key must guarantee uniqueness across the paginated set, such as a unique `_id`. If all three keys can still tie between two documents, the ordering is not yet fully deterministic.

### 8.1. Both Fields Descending

Sort:

~~~javascript
{ score: -1, _id: -1 }
~~~

Next page after anchor `(scoreLast, idLast)`:

~~~javascript
{
  $or: [
    { score: { $lt: scoreLast } },
    { score: scoreLast, _id: { $lt: idLast } }
  ]
}
~~~

### 8.2. One Field Descending, One Ascending

Sort:

~~~javascript
{ score: -1, _id: 1 }
~~~

Next page:

~~~javascript
{
  $or: [
    { score: { $lt: scoreLast } },
    { score: scoreLast, _id: { $gt: idLast } }
  ]
}
~~~

Because `score` is descending, smaller scores come after. Because `_id` is ascending, when scores tie, larger `_id` values come after. **Do not apply a single `<`/`>` operator blindly to every field**; derive each comparator from that key's actual sort direction.

### 8.3. Three Fields: Three-Branch OR Expression

Sort:

~~~javascript
{ priority: -1, createdAt: -1, _id: -1 }
~~~

Anchor `(p, t, id)`. Next-page condition:

~~~javascript
{
  $or: [
    { priority: { $lt: p } },
    {
      priority: p,
      createdAt: { $lt: t }
    },
    {
      priority: p,
      createdAt: t,
      _id: { $lt: id }
    }
  ]
}
~~~

This is the general extension rule:

1. Branch 1: the primary key is strictly past the anchor.
2. Branch 2: the primary key equals the anchor and the second key is strictly past it.
3. Branch 3: the first two keys equal the anchor and the third key is strictly past it.
4. Continue similarly if more keys exist.

Branch count grows with the number of sort fields; keep the composite key **stable enough without making it unnecessarily long**.

### 8.4. Sorting by Strings and Collation

If sorting by `name` then `_id`:

~~~javascript
.find({})
.sort({ name: 1, _id: 1 })
~~~

then the cursor predicate must compare `name` using the **exact same collation rules** used during sorting. Under different collations, uppercase/lowercase, diacritics, and string comparisons may diverge from expected order.

Example with collation:

~~~javascript
const collation = { locale: "en", strength: 2 };

lab.customers.find({
  $or: [
    { name: { $gt: lastName } },
    { name: lastName, _id: { $gt: lastId } }
  ]
}).collation(collation)
  .sort({ name: 1, _id: 1 })
  .limit(20);
~~~

This example uses a hypothetical `customers` collection. In real implementations, design an index with a **matching collation**, decide how to handle names considered equivalent by the collation, and use an independent secondary key to break ties. When deterministic byte ordering is required for APIs or business keys, you can store a **normalized sortKey** and apply an agreed-upon comparison rule.

## 9. Compound Indexes Supporting Filters and Sorts

Keyset pagination delivers significant advantages only when queries use an index matching both **business filters and sort order**.

With filter:

~~~javascript
{ tenantId: "T1", status: "paid" }
~~~

and sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

you can create a compound index:

~~~javascript
lab.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Index key ordering concept:

~~~text
tenantId  (equality)
  └── status  (equality)
        └── createdAt DESC  (display order)
              └── _id DESC  (tie-breaker)
~~~

When `tenantId` and `status` are constrained by equality predicates, the trailing index keys are already ordered appropriately for querying by `createdAt` and `_id`. MongoDB can use the index to seek near the anchor and scan forward, instead of discarding massive numbers of entries as in deep offset pagination.

**Not every index containing all field names is optimal.** Field order, equality vs. range predicates, sort directions, collation, data distribution, and how the optimizer handles `$or` all influence the execution plan.

### 9.1. Verifying with explain

~~~javascript
const lastDoc = firstPage[firstPage.length - 1];

lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $lt: lastDoc.createdAt } },
    {
      createdAt: lastDoc.createdAt,
      _id: { $lt: lastDoc._id }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(4)
.explain("executionStats");
~~~

Key items to inspect in the output:

- `winningPlan` and execution stages appropriate for your MongoDB version.
- Whether `IXSCAN` or index scan structures are used.
- Whether an in-memory `SORT` stage appears after reading.
- `totalKeysExamined` compared with `nReturned`.
- `totalDocsExamined` versus returned documents.
- Selectivity of `tenantId`, `status`, and the cursor range.

On a lab dataset of only 12 documents, MongoDB might pick `COLLSCAN` because scanning a tiny collection is cheaper. That does not prove the index is useless on production data volumes.

### 9.2. Choosing Indexes by Workload

If you have different screens:

- Orders for a tenant and status: `tenantId, status, createdAt, _id`.
- Orders across all statuses for a tenant: `tenantId, createdAt, _id`.
- Orders for a specific customer: `tenantId, customerId, createdAt, _id`.

Each group may warrant its own index or a carefully considered shared index. Avoid creating every possible combination because indexes consume disk space, RAM, and write maintenance overhead.

### 9.3. Indexes Do Not Make Data Immutable Across Pages

Indexes provide efficient ordered data access, yet they do not lock a result set across multiple requests. If requirements demand "exporting the exact same dataset at a point in time", a dedicated consistency mechanism is needed rather than relying solely on a compound index.

## 10. Cursor Tokens for REST APIs

In `mongosh` we can pass objects containing `Date` and `ObjectId` directly. A REST API, however, typically receives cursors via URLs:

~~~text
GET /orders?limit=20
GET /orders?limit=20&after=<opaque-token>
GET /orders?limit=20&before=<opaque-token>
~~~

The client does not need to know what the token contains; it simply sends back the token returned by the server.

Example response:

~~~json
{
  "items": [
    { "id": "00000000000000000000000c", "orderCode": "O-112" },
    { "id": "00000000000000000000000b", "orderCode": "O-111" },
    { "id": "000000000000000000000009", "orderCode": "O-109" }
  ],
  "pageInfo": {
    "hasNextPage": true,
    "nextCursor": "opaque-string-from-server"
  }
}
~~~

The token string illustrates the API contract; actual values must be generated according to backend specifications.

### 10.1. What Should a Cursor Payload Contain?

An illustrative structure:

~~~json
{
  "version": 1,
  "direction": "after",
  "createdAt": "2026-05-05T10:00:00.000Z",
  "id": "000000000000000000000009",
  "sort": "createdAt_desc_id_desc",
  "filterKey": "tenant=T1;status=paid"
}
~~~

Meaning:

- `version`: token format version to support contract evolution.
- `direction`: distinguishes next/previous if the API uses directional tokens.
- `createdAt`: timestamp in **ISO 8601 UTC** format.
- `id`: `ObjectId` as a **24-character hexadecimal string**.
- `sort`: identifies sort order to prevent using a token from a differently sorted view.
- `filterKey`: binds the cursor to the filter enforced by the server.

Some APIs also include `expiresAt` or user/tenant binding fields. For complex filters, a canonicalized filter fingerprint/hash can be used, though the server must still re-enforce permissions and active filters rather than blindly trusting a client-sent string.

### 10.2. Encoding and Decoding in Node.js

The simple example below encodes the payload as **base64url** (Node.js supports `Buffer`). Base64url is only **encoding**, not cryptographic encryption or signing.

~~~javascript
function encodeCursor(cursor) {
  const payload = {
    version: 1,
    direction: cursor.direction,
    createdAt: cursor.createdAt.toISOString(),
    id: cursor._id.toHexString(),
    sort: "createdAt_desc_id_desc"
  };

  return Buffer.from(JSON.stringify(payload), "utf8")
    .toString("base64url");
}

function decodeCursor(raw) {
  const payload = JSON.parse(
    Buffer.from(raw, "base64url").toString("utf8")
  );

  if (payload.version !== 1 ||
      payload.sort !== "createdAt_desc_id_desc" ||
      !["after", "before"].includes(payload.direction)) {
    throw new Error("Incompatible cursor");
  }

  if (typeof payload.createdAt !== "string" ||
      !Number.isFinite(Date.parse(payload.createdAt)) ||
      !/^[a-f0-9]{24}$/i.test(payload.id)) {
    throw new Error("Invalid cursor");
  }

  return {
    direction: payload.direction,
    createdAt: new Date(payload.createdAt),
    _id: new ObjectId(payload.id)
  };
}
~~~

To use this with the MongoDB Node.js Driver, import `ObjectId` from the `mongodb` package. In the snippet, `ObjectId` is assumed to be in scope. The code above only validates basic format; it **does not verify signatures, TTL, tenant scope, filter values, or token size limits**.

When cursors travel through untrusted environments (browsers, URLs, external clients), backends should consider **HMAC/signatures** to prevent tampering with anchors, enforce length limits, handle malformed base64/JSON safely, and avoid putting sensitive data into decodable tokens. HMAC does not replace **authentication/authorization**: every request must still re-verify document access rights.

### 10.3. Preserve BSON Types When Reconstructing Cursors

For the `createdAt` and `_id` sort example:

- `createdAt` must be reconstructed as a **Date**, not passed as an ISO string against a BSON Date field.
- `_id` must be reconstructed as an **ObjectId**, not passed as a hex string when the collection stores BSON ObjectIds.
- If using `Decimal128`, `Long`, or other key types, the token must preserve exact values and the decoder must restore the exact BSON type.
- Do not pass large 64-bit integers through JavaScript `Number`, as precision can be lost before reconstructing the key.

A seemingly valid cursor containing the **wrong BSON type** can cause `$lt`/`$gt` comparisons to fail to match as expected.

## 11. Java/Spring Data MongoDB Application

In Java, you can construct lexicographic filters using Spring Data MongoDB's `Criteria` and `Query`. The example below illustrates **next page** under descending sort.

Suppose the entity has:

~~~java
@Document("orders")
public class Order {
    @Id
    private ObjectId id;

    private String tenantId;
    private String status;
    private Date createdAt;

    // getters/setters...
}
~~~

Building the `Query`:

~~~java
import java.util.Date;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Query buildNextPageQuery(
        String tenantId,
        String status,
        Date lastCreatedAt,
        ObjectId lastId,
        int pageSize
) {
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize must be 1..100");
    }

    Criteria base = Criteria.where("tenantId").is(tenantId)
        .and("status").is(status);

    Criteria after = new Criteria().orOperator(
        Criteria.where("createdAt").lt(lastCreatedAt),
        new Criteria().andOperator(
            Criteria.where("createdAt").is(lastCreatedAt),
            Criteria.where("_id").lt(lastId)
        )
    );

    return new Query(
        new Criteria().andOperator(base, after)
    )
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    ))
    .limit(pageSize + 1);
}
~~~

Call `mongoTemplate.find(query, Order.class)` to fetch `pageSize + 1` items, strip the lookahead item, and build the cursor from the **last item actually returned to the client**. When no anchor is supplied (first page), query `base` with the same sort, omitting `after`.

This example uses Spring Data MongoDB as the mapping layer; syntax can be adapted to your Spring Data version and entity model. Most importantly, the **filter must match the sort exactly**.

**For multi-tenant applications**, `tenantId` must be resolved from the authenticated context and enforced on every request, even if the cursor token carries tenant metadata. Never read a tenant from a token and treat it as proof of authorization.

## 12. Data Changing Between Pages: Limits to Understand

### 12.1. Inserting New Documents Before the Anchor

The user has received the first page:

~~~text
O-112, O-111, O-109
cursor = (May 05, id 09)
~~~

Then the system inserts a new order dated May 08. Fetching the next page after the old anchor **will not show** the new order at the head of the list, because the keyset predicate only seeks records **after** `(May 05, id 09)`.

This is usually the desired behavior for **infinite scroll**: users continue downward through older records without new arrivals pushing items down. To view newer orders, the UI can offer a **Refresh** button or reload from the first page.

### 12.2. Inserting New Documents After the Anchor

If a new document arrives with a `createdAt` older than the current anchor, it can appear on subsequent pages. Because keyset pagination is **not a fixed snapshot**, the dataset seen during a scroll session can change if the app backdates writes, imports historical records, or edits timestamps.

### 12.3. Deleting Documents Before the Anchor

With offset pagination, deleting a record before the skip position shifts remaining elements upward, causing a record to be skipped. With keyset pagination, continuation relies on **specific key values**, so deleting records ahead of the anchor generally does not shift seek positions in the same way.

Even if the anchor document itself is deleted, **the cursor still works** because the token already carries the key pair; the filter does not need to look up the anchor document in the collection.

### 12.4. Updating the Sort Key Moves Documents

This is a critical limitation of keyset pagination. If sorting by `updatedAt`, every update to an order can move it to the top of the list. An unread document can move **ahead of the anchor**, causing the user to miss it; an already-read document can also move behind the anchor and reappear.

Therefore, when building keyset pagination, prefer keys that are **stable or immutable** over the document's lifecycle, such as:

~~~text
createdAt + _id
sequence + _id
businessDate + uniqueId (if businessDate does not change)
~~~

`updatedAt` fits screens sorted by most recent activity, provided you accept a shifting list or add a snapshot/synchronization mechanism.

### 12.5. Stable Ordering Differs from a Consistent Snapshot

Normal paged queries do not create a **consistent snapshot across multiple HTTP requests**. When business requirements demand exporting an exact dataset "as of 10:00:00", keyset alone is insufficient.

Options depending on requirements:

- Store an **upper bound** (high-water mark) in the token to exclude records with sort keys newer than the initial threshold.
- Make `createdAt` or `sequence` **immutable**, tie to an export session, and fix the set of exportable records.
- Create a dedicated snapshot/materialized export or use point-in-time consistent reads when supported by MongoDB deployment, session, and read concern.
- For histories involving updates/deletes, design a versioning or append-only history model if business rules require reconstructing past state.

A high-water mark limits one kind of churn but **does not freeze the data**: documents inside the bound can still be updated/deleted and new records with backdated timestamps can still appear. Do not market it as a true snapshot replacement.

## 13. Data Types, Nulls, Collation, and Uniqueness

### 13.1. Sort Fields Must Have Consistent Values and Types

If some documents lack `createdAt`, some have `createdAt: null`, and others have BSON Date values, MongoDB sorts according to BSON type comparison rules. Seek predicates using `$lt`/`$gt` may fail to reflect business intent when types are mixed.

For APIs requiring clear ordering, you should:

1. Require `createdAt` as a **mandatory** schema field.
2. Enforce that it is a **BSON Date**.
3. Backfill legacy data before enabling stable pagination.
4. Explicitly decide whether to paginate documents missing the key or exclude them via filter.

You can use collection validation with `$jsonSchema`:

~~~javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["createdAt", "status", "tenantId"],
      properties: {
        createdAt: { bsonType: "date" },
        status: { bsonType: "string" },
        tenantId: { bsonType: "string" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

The `collMod` block above is an **example of a design rule**—you do not need to run it on the lab collection if you want to keep its current validator; it assumes the active database holds the `orders` collection. In real environments, changing validators requires reviewing existing schemas and legacy data before rollout.

### 13.2. The Secondary Field Must Truly Distinguish Records

`_id` is commonly chosen as the tie-breaker because MongoDB requires every document to have an `_id`, and applications typically use unique identifiers. However, in **sharded collection** designs, global uniqueness guarantees for `_id` depend on shard key configuration and unique index constraints. If you are unsure whether a field is unique across the result set, design a composite key that is unique within the query scope or use a system-guaranteed identifier.

### 13.3. ObjectId Does Not Prove Strict Wall-Clock Ordering

MongoDB `ObjectId` includes a timestamp component and generally trends upward over time, yet **it must not be treated as an exact global clock** across an entire system. Clients may have skewed clocks; `ObjectId` has only 1-second timestamp resolution and also includes random/counter bytes.

If you need to sort by **business creation time**, use an explicitly defined `createdAt` field and add `_id` to break ties. Do not replace `createdAt` with `_id` if product requirements genuinely demand an exact timestamp under a specific convention.

### 13.4. Collation Must Match Across Index, Sort, and Cursor

When sorting strings like `customerName`, the API must standardize locale, strength, and normalization. The "comes after" filter must evaluate under the **same ordering used by `sort`**. An index with a different collation may not serve the sort efficiently. Switching collations between requests while keeping an old cursor can produce wrong ordering.

## 14. Common Bugs and How to Fix Them

| Symptom | Typical cause | Resolution |
| --- | --- | --- |
| An order repeats on the next page | Using `$lte`/`$gte`, including the anchor record | Use strict comparisons `$lt`/`$gt` |
| Orders with identical timestamps are skipped | Storing only `createdAt` in cursor | Store both `createdAt` and `_id` |
| Next page returns wrong order | Seek filter does not match `sort` direction | Rewrite lexicographic branches per key |
| Previous page jumps to the top of the list | Querying `before` while keeping descending sort + limit | Reverse sort direction to grab items nearest anchor, then reverse array |
| Query remains slow | Compound index does not match filter/sort | Inspect indexes and `explain("executionStats")` |
| Cursor holds date string while collection stores Date | Wrong BSON type when building filter | Parse ISO string into `Date` |
| Cursor holds hex string instead of `ObjectId` | Type mismatch comparing `_id` | Reconstruct proper `ObjectId` type |
| Client changes `status`/`tenant` between pages | Old cursor belongs to a different result set | Bind token to filter; re-apply current auth and filter |
| Token tampered with or oversized | Missing input validation | Cap length, validate schema, HMAC-sign when needed |
| Documents disappear/repeat while scrolling | Sort field mutated during pagination | Prefer immutable keys; design snapshots if needed |
| New items inserted at top don't appear | Keyset keeps reading past the old anchor | Provide a refresh-from-top action |
| `hasNextPage` is wrong | Using lookahead item's key as cursor or fetching exact `pageSize` | Fetch `pageSize + 1`, return `pageSize`, anchor on last returned item |
| Ordered yet unstable results | Duplicate sort keys with no tie-breaker | Add unique final field to sort and cursor |
| Name ordering varies across collations | Inconsistent string comparison | Keep collation and index on the same contract |
| Need to jump straight to page 500 | Keyset requires that page's anchor | Consider offset, bookmarks, anchor index, or alternative UX |

## 15. Practice Exercises

### Exercise 1 — Where Does Timestamp-Only Pagination Fail?

Using the dataset in Section 3, fetch the first three items with `sort({ createdAt: -1 })`, then write `createdAt < last.createdAt`. Compare results with the query that includes `_id` as a tie-breaker.

Key takeaway to demonstrate: when the first page ends at `O-109` on May 05, document `O-108` with the **same timestamp** gets skipped if the filter only checks `createdAt < May 05`.

### Exercise 2 — Writing the Second Page Manually

Given the ordering:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

and anchor `O-109`, write the two-branch `$or` filter to fetch the next three orders. Expected result:

~~~text
O-108, O-107, O-106
~~~

Explain why `_id < last._id` is required in the equal-timestamp branch.

### Exercise 3 — Reading Continuously to the End of the List

Use `fetchNextPage()` from Section 6 and loop until `nextCursor = null`. With `pageSize = 3` and 11 paid orders, document counts per page are:

~~~text
Page 1: 3
Page 2: 3
Page 3: 3
Page 4: 2
~~~

Print all `orderCode` values in sequence and compare against `find().sort({createdAt:-1,_id:-1})`.

### Exercise 4 — Backward Pagination

From page two, use the **first item O-108** as the `before` anchor, a lexicographic `$gt` condition, and ascending sort. After reversing the result array, the previous page must be:

~~~text
O-112, O-111, O-109
~~~

Intentionally omit the array reversal step and explain why the displayed order will be inverted for the UI.

### Exercise 5 — Mixed-Direction Composite Key

Suppose a leaderboard uses the sort:

~~~javascript
{ score: -1, userId: 1 }
~~~

Write the next-page filter after anchor `(score, userId) = (90, "u07")`.

Solution:

~~~javascript
{
  $or: [
    { score: { $lt: 90 } },
    { score: 90, userId: { $gt: "u07" } }
  ]
}
~~~

A score equal to 90 with `userId` greater than `"u07"` comes **after** under the ascending direction of the second key. Flip only `userId`'s comparator, not `score`'s.

### Exercise 6 — Extending to Three Keys

Sorting:

~~~javascript
{ priority: -1, createdAt: -1, _id: -1 }
~~~

Write the next-page predicate using a three-branch `$or`. Each branch must keep preceding keys equal to the anchor and strictly compare the current key.

### Exercise 7 — Compound Index

Create the index:

~~~javascript
lab.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Run `explain("executionStats")` on the next-page query. Observe scan type, keys/docs examined, and sort stages; explain why a 12-document dataset is insufficient to judge index benefits in production.

### Exercise 8 — Data Changing After the First Page

Simulate a new order arriving at `2026-05-08T10:00:00Z` after fetching the first page. When using `after` from `O-109`, do you see the new order? Why? If the UI wants to surface newest orders, what feature should it offer?

### Exercise 9 — Designing a Cursor API

Design a token schema containing `createdAt`, `id`, `direction`, `sort`, and `version`. Describe how to:

1. Verify signature and expiration if using signed tokens.
2. Convert date strings to `Date` and ID strings to `ObjectId`.
3. Re-apply filters and permissions from the authenticated session.
4. Fetch one extra item to compute `hasNextPage`.
5. Build the new token from the **last returned item**.

Explain why base64 encoding alone does not protect tokens against tampering.

## 16. Design Principles to Remember

Keyset pagination works effectively when **sort order is deterministic and the starting point is exact**. In MongoDB, a widely used pattern is:

~~~javascript
// Fixed sort
{ createdAt: -1, _id: -1 }

// "after" condition for next page
{
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
}
~~~

When implementing:

1. **Always include a unique tie-breaker** in the sort, typically `_id`.
2. **Store all sort keys in the cursor**, preserving BSON types and sort directions.
3. **Seek filters use lexicographic comparison**: preceding keys must equal the anchor before comparing trailing keys.
4. **Use strict comparisons** so the anchor document is never returned twice.
5. **Backward pages invert sort direction and reverse results** to capture records closest to the anchor.
6. **Align compound indexes** with equality filters followed by sort order.
7. **Prefer immutable sort fields** when you want to avoid documents jumping positions on updates.
8. **Bind cursors to filters, sorts, and access control**, validating inputs and tokens server-side.
9. **Do not equate stable ordering with a snapshot**: separate reads can still observe a changing dataset.
10. **Set proper UX expectations**: keyset fits Next/Previous and infinite scroll; arbitrary page jumps require additional design.

### Official MongoDB References

- [cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/) — deep-offset skip cost and notes on unique sort keys.
- [cursor.sort()](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/) — sort syntax and stability with duplicate keys.
- [cursor.limit()](https://www.mongodb.com/docs/manual/reference/method/cursor.limit/) — capping returned document counts.
- [Comparison Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-comparison/) — `$lt`, `$lte`, `$gt`, `$gte`, and `$eq`.
- [`$or` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/or/) — combining predicate branches.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — multi-key indexes and access order.
- [Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/) — relationship between indexes and sorting.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — reading execution plans and query cost.
