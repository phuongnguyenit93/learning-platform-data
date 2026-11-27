# Counting with `$count` and Frequency Summarization with `$sortByCount` in MongoDB

## 1. Document Counting and Frequency Counting Are Two Different Questions

In an e-commerce application, an administrator might want to know:

1. **How many orders have been paid?**
2. **How many times does each order status appear?**
3. **Which tags are used the most?**
4. **How many countries generate orders, and what is each country's share?**

Two MongoDB **aggregation pipeline stages** commonly answer the first requirements quickly:

- **`$count`** counts **the number of documents reaching that stage** and returns one document holding the total count.
- **`$sortByCount`** groups documents by the value of **an expression**, counts the documents in each group, and **sorts by frequency descending**.

Example:

```javascript
// A single number: count of orders with status PAID.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "paidOrders" }
]);

// Multiple groups: how many times does each status appear?
db.orders.aggregate([
  { $sortByCount: "$status" }
]);
```

**Both count documents in the aggregation stream**, yet differ in output shape:

| Component | Question | Result shape |
|---|---|---|
| `$count` | How many documents total reached this point? | One document like `{ total: 8 }` if input is non-empty |
| `$sortByCount` | Which group values exist and how often does each appear? | Multiple documents like `{ _id: "PAID", count: 4 }` |
| `$group` + `$sum: 1` | Custom grouping key and counting/aggregation | Flexible: one or many groups, multiple accumulators |

These are **stages**, not operators placed directly inside a `find()` query filter. Syntax, position, and meaning depend on where they appear in the pipeline.

## 2. Practice Dataset

Examples use **mongosh** and the `salesOrdersLesson` collection in a test database. Insert the data once into a collection that does not yet contain these `_id` values:

```javascript
db.salesOrdersLesson.insertMany([
  {
    _id: "O01",
    customerId: "C01",
    status: "PAID",
    country: "VN",
    channel: "web",
    tags: ["new", "vip"],
    amount: 340000,
    items: [
      { sku: "P01", quantity: 1 },
      { sku: "P02", quantity: 2 }
    ],
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: "O02",
    customerId: "C02",
    status: "PAID",
    country: "VN",
    channel: "app",
    tags: ["sale"],
    amount: 90000,
    items: [{ sku: "P02", quantity: 1 }],
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: "O03",
    customerId: "C03",
    status: "PENDING",
    country: "SG",
    channel: "web",
    tags: [],
    amount: 250000,
    items: [{ sku: "P03", quantity: 1 }],
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: "O04",
    customerId: "C04",
    status: "CANCELLED",
    country: "VN",
    channel: "web",
    tags: ["sale", "vip"],
    amount: 120000,
    items: [
      { sku: "P02", quantity: 1 },
      { sku: "P04", quantity: 1 }
    ],
    createdAt: ISODate("2026-11-04T09:00:00Z")
  },
  {
    _id: "O05",
    customerId: "C05",
    status: "PAID",
    country: "TH",
    channel: "app",
    tags: ["new"],
    amount: 180000,
    items: [{ sku: "P05", quantity: 1 }],
    createdAt: ISODate("2026-11-05T09:00:00Z")
  },
  {
    _id: "O06",
    customerId: "C01",
    status: "PAID",
    country: "VN",
    channel: "web",
    tags: ["vip"],
    amount: 450000,
    items: [
      { sku: "P01", quantity: 1 },
      { sku: "P03", quantity: 1 },
      { sku: "P05", quantity: 1 }
    ],
    createdAt: ISODate("2026-11-06T09:00:00Z")
  },
  {
    _id: "O07",
    customerId: "C06",
    status: null,
    country: "TH",
    channel: "app",
    tags: [],
    amount: 0,
    items: [],
    createdAt: ISODate("2026-11-07T09:00:00Z")
  },
  {
    _id: "O08",
    customerId: "C07",
    // Intentionally missing the status field.
    country: "VN",
    channel: "partner",
    tags: ["sale"],
    amount: 110000,
    items: [{ sku: "P04", quantity: 1 }],
    createdAt: ISODate("2026-11-08T09:00:00Z")
  }
]);
```

The dataset has **8 documents**. Among them are 4 `PAID` orders, 1 `PENDING`, 1 `CANCELLED`, 1 order with `status: null`, and 1 order **missing the `status` field**. The last two cases are included to examine how missing/null data is grouped.

| `_id` | `status` | `country` | `channel` | `tags` |
|---|---|---|---|---|
| O01 | PAID | VN | web | new, vip |
| O02 | PAID | VN | app | sale |
| O03 | PENDING | SG | web | empty array |
| O04 | CANCELLED | VN | web | sale, vip |
| O05 | PAID | TH | app | new |
| O06 | PAID | VN | web | vip |
| O07 | null | TH | app | empty array |
| O08 | Missing | VN | partner | sale |

All numeric results in this lesson assume the collection holds only these eight documents and **no updates have been made** after insertion.

## 3. How to Write `$count`

### 3.1. Syntax

```javascript
db.collection.aggregate([
  { $count: "resultFieldName" }
]);
```

`$count` accepts **a string** naming the field that will hold the count result. The name must be valid: non-empty, not starting with `$`, and containing no dots `.`.

Example:

```javascript
db.salesOrdersLesson.aggregate([
  { $count: "totalOrders" }
]);
```

Result:

```javascript
{ totalOrders: 8 }
```

The `$count` stage does not return an array of eight documents, nor does it add `totalOrders` to each source document. It **consumes the input stream** and produces **one summary document** if at least one input document arrives.

### 3.2. Counting After `$match`

To count paid orders:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "PAID" } },
  { $count: "paidOrders" }
]);
```

Result:

```javascript
{ paidOrders: 4 }
```

Data flow:

```text
8 documents in salesOrdersLesson
              |
              v
  $match: status = "PAID"
              |
              v
      4 remaining documents
              |
              v
    $count: "paidOrders"
              |
              v
       { paidOrders: 4 }
```

**The position of `$count` determines what it counts.** It does not automatically count the entire collection if earlier `$match`, `$unwind`, `$group`, `$limit`, or other stages changed the document count.

### 3.3. Counting with Multiple Conditions

```javascript
db.salesOrdersLesson.aggregate([
  {
    $match: {
      status: "PAID",
      country: "VN"
    }
  },
  { $count: "paidOrdersInVN" }
]);
```

Result:

```javascript
{ paidOrdersInVN: 3 }
```

The three orders are O01, O02, and O06. For total orders in VN regardless of status, drop the `status` condition and the result is **5**.

### 3.4. Counting over a Time Range

```javascript
db.salesOrdersLesson.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-11-06T00:00:00Z")
      }
    }
  },
  { $count: "ordersInPeriod" }
]);
```

The result is `{ ordersInPeriod: 5 }`, corresponding to O01 through O05. For daily/monthly reports, define the **timezone and half-open interval** `[start, end)` explicitly. Do not assume every timestamp in the application is already in UTC unless the system enforces that contract.

## 4. Often Overlooked: `$count` with Empty Input Does Not Return `{ total: 0 }`

Suppose no order has status `"REFUNDED"` in the sample set:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "REFUNDED" } },
  { $count: "total" }
]);
```

**The pipeline output is zero documents**:

```javascript
// When represented as an array:
[]
```

Not:

```javascript
// NOT the default result of $count on empty input.
{ total: 0 }
```

This matters when writing application code:

```javascript
const result = db.salesOrdersLesson.aggregate([
  { $match: { status: "REFUNDED" } },
  { $count: "total" }
]).toArray();

const total = result.length === 0 ? 0 : result[0].total;
print(total); // 0
```

At the application layer, you must usually **convert "no result documents" into 0** if the API contract always expects `{ total: 0 }`. Never access `result[0].total` when `result` can be empty.

### 4.1. Why Does This Happen?

Semantically, `$count` is equivalent to grouping all input documents into a single group and counting elements:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: null,
      total: { $sum: 1 }
    }
  },
  { $project: { _id: 0, total: 1 } }
]);
```

With empty input, that group **is never created**, so no output document is emitted. Understanding this prevents confusing `$count` with an application function that always returns integer 0.

### 4.2. Producing a Total Field in a Fixed Result Shape

If a dashboard needs both totals and breakdowns simultaneously, you can use `$facet` and map an empty count result to 0:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "REFUNDED" } },
  {
    $facet: {
      totals: [{ $count: "value" }],
      byCountry: [{ $sortByCount: "$country" }]
    }
  },
  {
    $project: {
      total: {
        $ifNull: [
          { $arrayElemAt: ["$totals.value", 0] },
          0
        ]
      },
      byCountry: 1
    }
  }
]);
```

On the sample data, the output shape is:

```javascript
{
  total: 0,
  byCountry: []
}
```

Here `$facet` produces one document containing the branch result arrays. `totals` is an empty array, so the `$ifNull` expression applies the fallback 0. This is a solution **for multi-metric aggregation needs**, not a reason to use `$facet` for every simple count.

## 5. How Does `$count` Differ from `countDocuments()` and `estimatedDocumentCount()`?

MongoDB has several counting APIs with different shapes and semantics:

| Counting method | Syntax | Best suited when |
|---|---|---|
| Aggregation `$count` | `aggregate([{ $match: ... }, { $count: "total" }])` | Counting **after pipeline steps**, potentially combined with data transformations |
| `countDocuments()` | `db.orders.countDocuments({ status: "PAID" })` | Counting documents matching a standard filter |
| `estimatedDocumentCount()` | `db.orders.estimatedDocumentCount()` | Needing an estimated collection document count without a filter |

Example:

```javascript
db.salesOrdersLesson.countDocuments({ status: "PAID" });
// 4

db.salesOrdersLesson.estimatedDocumentCount();
// Estimated collection count, around 8 on the sample dataset.

db.salesOrdersLesson.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
// { total: 4 }
```

`countDocuments()` returns **a scalar number** directly from the API, convenient when you only need a filtered document count. `estimatedDocumentCount()` relies on collection metadata/statistics and accepts no filter, so it cannot answer "how many PAID orders exist?".

**Do not treat these three methods as always equivalent in performance or output.** Transaction context, concurrent writes, deployment version, and accuracy/statistics requirements affect the choice. If you already have a data-processing pipeline, `$count` is usually the most direct expression.

## 6. `$sortByCount`: Grouping and Ranking Frequencies

### 6.1. Syntax

```javascript
db.collection.aggregate([
  { $sortByCount: <expression> }
]);
```

**`<expression>` is an aggregation expression**, such as:

- `"$status"`: reads the `status` field value.
- `"$country"`: reads the `country` field value.
- `{ $toLower: "$channel" }`: computes the lowercased string.
- `{ $cond: [condition, valueIfTrue, valueIfFalse] }`: determines the group conditionally.

Each distinct value of the expression creates a group. The stage counts **how many documents fall into each group** and sorts groups by `count` descending.

### 6.2. Order Status Frequency

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$status" }
]);
```

Output shape:

```javascript
{ _id: "PAID", count: 4 }
{ _id: null, count: 2 }
{ _id: "PENDING", count: 1 }
{ _id: "CANCELLED", count: 1 }
```

**The relative order of the two groups with `count: 1` is not guaranteed** when sorting solely by frequency. In the sample set, `null` represents O07 with `status: null` and O08 missing `status`; both states merge together when directly using `"$status"` as the grouping key.

Shape of each output document:

| Output field | Meaning |
|---|---|
| `_id` | Group value evaluated from the expression |
| `count` | Number of documents entering that group |

These are **not** original order documents: fields like `customerId`, `amount`, and `createdAt` no longer exist in the grouped results.

### 6.3. Country Frequency

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" }
]);
```

Result:

```javascript
{ _id: "VN", count: 5 }
{ _id: "TH", count: 2 }
{ _id: "SG", count: 1 }
```

This answers a different question from `$count`: we do not just want **8 orders**, we want **5 orders in VN, 2 in TH, and 1 in SG**.

### 6.4. Channel Frequency

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$channel" }
]);
```

Result:

```javascript
{ _id: "web", count: 4 }
{ _id: "app", count: 3 }
{ _id: "partner", count: 1 }
```

Note: the numbers are **order counts**, not revenue. `$sortByCount` counts one unit per document by default and does not weight by `amount`.

## 7. Why Is `$sortByCount` Equivalent to `$group` Followed by `$sort`?

This is the most important principle for understanding this stage:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" }
]);
```

has the same purpose as:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: "$country",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Processing flow:

```text
        8 order documents
                |
                v
    Evaluate $country per order
                |
                v
     $group by country value
       VN: 5, TH: 2, SG: 1
                |
                v
       $sort count descending
                |
                v
    { _id: "VN", count: 5 }
    { _id: "TH", count: 2 }
    { _id: "SG", count: 1 }
```

`$sortByCount` is shorthand for **`$group` by an expression + `$sum: 1` + `$sort` descending by count**.

### 7.1. When to Use the Shorthand?

Choose `$sortByCount` when the question is simply:

> "How many times does each group value appear, and which groups are most common?"

For example: frequencies of statuses, countries, order channels, or tag codes after unwinding an array.

### 7.2. When Do You Need Full `$group`?

If you also need total amount, average value, or latest timestamp:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: "$country",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" },
      averageAmount: { $avg: "$amount" },
      latestOrderAt: { $max: "$createdAt" }
    }
  },
  { $sort: { orderCount: -1, _id: 1 } }
]);
```

Here `$group` is better because `$sortByCount` only produces `_id` and `count`; it **has no syntax for adding extra accumulators** in the same stage.

Similarly, if you need multi-field sorting or a renamed count field, use `$group` + `$sort` / `$project` for clearer intent.

### 7.3. Stabilizing Order When Groups Tie in Frequency

`$sortByCount` sorts by `count` descending, **without guaranteeing order among groups sharing the same count**. For pagination or reports requiring deterministic ordering:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
]);
```

This adds `_id` ascending as a tie-breaker. If `_id` values span different data types, MongoDB sorts according to BSON comparison order; consider normalizing group keys if the report specifies a custom order.

## 8. Stage Placement Changes the Meaning of Counting

A MongoDB pipeline processes documents **in stage order**. Therefore, placing `$match`, `$limit`, `$unwind`, or `$group` before `$count` or `$sortByCount` changes the input set being counted.

### 8.1. `$match` Before `$sortByCount`: Frequencies Within a Subset

Count country frequencies **only among paid orders**:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "PAID" } },
  { $sortByCount: "$country" }
]);
```

Result:

```javascript
{ _id: "VN", count: 3 }
{ _id: "TH", count: 1 }
```

The `$match` stage removes the four non-`PAID` orders before grouping; countries with zero matching orders do not appear in the result.

### 8.2. `$limit` Before `$count` Does Not Count the Whole Collection

```javascript
db.salesOrdersLesson.aggregate([
  { $limit: 3 },
  { $count: "total" }
]);
```

Result is `{ total: 3 }` because `$count` receives at most the three documents allowed past `$limit`.

Reverse the order:

```javascript
db.salesOrdersLesson.aggregate([
  { $count: "total" },
  { $limit: 3 }
]);
```

Result is `{ total: 8 }`, because `$count` already collapsed all inputs into **one total document**. `$limit: 3` afterward does not change the number inside that summary document.

**Never count a single page to infer the total result count**:

```javascript
// Counts only the documents on one page.
[
  { $skip: 20 },
  { $limit: 10 },
  { $count: "total" }
]
```

This is not a formula for total documents matching the initial filter. Total matching count and page item count are two different metrics.

### 8.3. `$count` After `$sortByCount` Counts the Number of Groups

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" },
  { $count: "countryGroupCount" }
]);
```

Result:

```javascript
{ countryGroupCount: 3 }
```

Because `$sortByCount` collapsed eight orders into **three country groups**, the trailing `$count` counts the three group documents, not the eight orders.

This is a simple way to count **distinct country values** in a dataset:

```javascript
db.salesOrdersLesson.aggregate([
  { $group: { _id: "$country" } },
  { $count: "distinctCountries" }
]);
```

Same result: `{ distinctCountries: 3 }`. When you only need the number of groups without sorting them, `$group` followed by `$count` avoids expressing an unnecessary sort step.

### 8.4. `$sortByCount` After `$limit` Counts Frequencies in a Limited Sample

```javascript
db.salesOrdersLesson.aggregate([
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $sortByCount: "$country" }
]);
```

The three newest orders are O08, O07, and O06. Frequency result:

```javascript
{ _id: "VN", count: 2 }
{ _id: "TH", count: 1 }
```

This is the country frequency **within the three newest orders**, not across all eight orders. When asked for "top k countries of the month," avoid accidentally `$limit`ing orders before grouping if business wants statistics over the **entire month**.

## 9. Counting Array Element Frequencies: Understanding `$unwind`

This is a critical trap when working with document databases.

Each order has an **array** field `tags`:

```javascript
{ _id: "O01", tags: ["new", "vip"] }
{ _id: "O02", tags: ["sale"] }
{ _id: "O03", tags: [] }
```

### 9.1. Using `$sortByCount: "$tags"` Directly Groups by the Whole Array

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$tags" }
]);
```

Here the aggregation expression `"$tags"` evaluates to the **document's entire array value**, so the grouping key `_id` can be an array like `["new", "vip"]`, `["sale"]`, or `[]`.

This answers:

> "Which **whole-array tag combinations** appear on orders, and how many times does each combination appear?"

It does **not** answer:

> "How many orders does each **individual tag** appear in?"

Two arrays containing the same elements in **different orders** can also form two separate grouping keys under array comparison semantics. Never rely on `$sortByCount: "$tags"` to count individual tags.

### 9.2. `$unwind` Turns Array Elements into Stream Documents

To count each tag, flatten the array with `$unwind`:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  { $sortByCount: "$tags" }
]);
```

Result:

```javascript
{ _id: "vip", count: 3 }
{ _id: "sale", count: 3 }
{ _id: "new", count: 2 }
```

The two groups with count 3 have no guaranteed order relative to each other. They correspond to:

- `vip`: appears in O01, O04, O06.
- `sale`: appears in O02, O04, O08.
- `new`: appears in O01, O05.

### 9.3. Why Does Total Tag Frequency Equal 8 While Only 6 Orders Have Tags?

Each document with a non-empty `tags` array produces **one output document per element** when passing through `$unwind`. Both O03 and O07 have empty arrays and are dropped by default `$unwind` behavior.

```text
O01: ["new", "vip"]     -> 2 documents after $unwind
O02: ["sale"]           -> 1 document
O03: []                 -> 0 documents
O04: ["sale", "vip"]     -> 2 documents
O05: ["new"]            -> 1 document
O06: ["vip"]            -> 1 document
O07: []                 -> 0 documents
O08: ["sale"]           -> 1 document
-----------------------------------------
Total                    8 documents
```

Thus:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  { $count: "tagOccurrences" }
]);
// { tagOccurrences: 8 }
```

This is **8 tag occurrences**, not eight distinct orders with tags.

To count **orders that have at least one tag**, on the sample dataset you can use:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { "tags.0": { $exists: true } } },
  { $count: "ordersWithTags" }
]);
// { ordersWithTags: 6 }
```

This filter fits a schema where `tags` is always an array and checks index 0. If the collection has mixed types or nested arrays, apply schema validation and matching query rules.

### 9.4. The `preserveNullAndEmptyArrays` Option

`$unwind` skips missing, null, or empty array fields by default. You can retain documents without elements using:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $unwind: {
      path: "$tags",
      preserveNullAndEmptyArrays: true
    }
  },
  { $sortByCount: "$tags" }
]);
```

Then orders with empty arrays stay in the stream after `$unwind` and contribute to a group representing untagged data. The result may include an `_id: null` group for post-unwind null/missing values.

**Clarify the requirement:** are you counting "frequencies of tags that actually appear" or do you need a separate bucket for "untagged orders"? For the first question, default `$unwind` is usually simpler and clearer.

### 9.5. Duplicate Tags Within the Same Order

Suppose an order has:

```javascript
{ _id: "O09", tags: ["vip", "vip", "sale"] }
```

`$unwind` produces **two `vip` entries** from O09. Therefore `$sortByCount` counts **element occurrences**, not necessarily **distinct** orders containing the tag.

If business rules require "each tag counts at most once per order," you can either:

- Normalize `tags` into a deduplicated set on write.
- Or deduplicate `(orderId, tag)` pairs before counting.

Example pipeline deduplicating at the pair level:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  {
    $group: {
      _id: {
        orderId: "$_id",
        tag: "$tags"
      }
    }
  },
  { $sortByCount: "$_id.tag" }
]);
```

After `$group`, each order-tag pair appears at most once in the stream. `$sortByCount` now represents **distinct orders containing each tag**. This illustrates why you must define the counting unit before choosing stages.

## 10. Grouping by Computed Expressions, Not Only Existing Fields

`$sortByCount` accepts an **aggregation expression**, so expressions can construct groups dynamically.

### 10.1. Bucketing by Amount Range with `$switch`

Suppose you want to group orders by amount:

- `LOW`: under 100,000.
- `MID`: from 100,000 up to under 300,000.
- `HIGH`: 300,000 and above.

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      $switch: {
        branches: [
          {
            case: { $lt: ["$amount", 100000] },
            then: "LOW"
          },
          {
            case: { $lt: ["$amount", 300000] },
            then: "MID"
          }
        ],
        default: "HIGH"
      }
    }
  }
]);
```

With the eight orders:

- `LOW`: O02 (90,000) and O07 (0) → **2**.
- `MID`: O03, O04, O05, O08 → **4**.
- `HIGH`: O01, O06 → **2**.

Result:

```javascript
{ _id: "MID", count: 4 }
{ _id: "LOW", count: 2 }
{ _id: "HIGH", count: 2 }
```

In this example, every `amount` is numeric. If documents can have missing, null, or string `amount`, decide how to handle them before comparing to prevent misgrouping under BSON type comparison rules.

### 10.2. Normalizing Letter Case

Suppose some orders record `"web"` and others `"WEB"`. If business treats them as the same channel, normalize before grouping:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      $toLower: {
        $ifNull: ["$channel", "(unknown)"]
      }
    }
  }
]);
```

`$ifNull` replaces null or missing fields with a fallback string, then `$toLower` converts the string to lowercase. If `channel` might hold **non-string types**, add type checks or normalize on input; do not treat `$toLower` as understanding arbitrary BSON types.

Note on Unicode and locales: operator lowercasing has specific rules and limits. If business needs locale-aware case-insensitive comparisons, consider **collation** or normalizing outside the database, and verify against actual data.

### 10.3. Daily Frequency with `$dateToString`

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      $dateToString: {
        format: "%Y-%m-%d",
        date: "$createdAt",
        timezone: "Asia/Ho_Chi_Minh"
      }
    }
  }
]);
```

The expression computes a date string in the specified timezone and groups orders by day. Since the sample documents are spaced one day apart, each day has one order; the result has eight groups of count 1 (their tie order is not guaranteed by `$sortByCount`).

In production reporting, align UTC timestamps stored in BSON Date with the business timezone when splitting days/months. Never group by strings sliced from UTC dates if the product defines calendar days in another timezone.

### 10.4. Grouping by Multiple Fields Using a Document Expression

To get frequencies for each `(country, channel)` pair, use an object expression:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      country: "$country",
      channel: "$channel"
    }
  }
]);
```

Each `_id` grouping key is a document such as:

```javascript
{
  _id: { country: "VN", channel: "web" },
  count: 3
}
```

On the sample dataset, VN-web includes O01, O04, O06 (count 3); VN-app includes O02 (count 1); VN-partner includes O08 (count 1); TH-app includes O05, O07 (count 2); SG-web includes O03 (count 1).

When grouping by objects or arrays, pay attention to **data types and key structure**. If you just need a clean composite key, writing full `$group` can be just as readable:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: {
        country: "$country",
        channel: "$channel"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

## 11. Distinguishing `null` and Missing Fields When Summarizing

In the sample dataset:

```javascript
{ _id: "O07", status: null, /* ... */ }
{ _id: "O08", /* missing status */ }
```

When running `$sortByCount: "$status"`, these two documents merge into one `_id: null` group. Yet in data-quality governance, the two states can mean different things:

- **Missing:** the application never wrote the field, possibly indicating a migration gap or legacy record.
- **Null:** the application explicitly wrote the field with value null.

To separate them, classify using `$type` in aggregation:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $set: {
      statusGroup: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [{ $type: "$status" }, "missing"]
              },
              then: "(missing)"
            },
            {
              case: {
                $eq: [{ $type: "$status" }, "null"]
              },
              then: "(null)"
            }
          ],
          default: "$status"
        }
      }
    }
  },
  { $sortByCount: "$statusGroup" }
]);
```

Now the groups are no longer merged accidentally:

```javascript
{ _id: "PAID", count: 4 }
{ _id: "PENDING", count: 1 }
{ _id: "CANCELLED", count: 1 }
{ _id: "(null)", count: 1 }
{ _id: "(missing)", count: 1 }
```

Groups tied at count 1 may appear in different orders. This works when real status values never collide with `"(null)"` and `"(missing)"`; in production systems, you can use an object containing both `type` and `value` to prevent label collisions.

**Do not "clean" null into a default value before verifying whether business rules need to distinguish null from missing.**

## 12. Combining Multiple Dashboard Statistics Using `$facet`

A dashboard often needs all of:

- Total order count.
- Paid order count.
- Status frequencies.
- Country frequencies.
- Top three most-used channels.

Running multiple separate queries can be simple, while `$facet` allows multiple processing branches **from the same input stream**:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $facet: {
      allOrders: [
        { $count: "value" }
      ],
      paidOrders: [
        { $match: { status: "PAID" } },
        { $count: "value" }
      ],
      byStatus: [
        { $sortByCount: "$status" }
      ],
      byCountry: [
        { $sortByCount: "$country" }
      ],
      topChannels: [
        { $sortByCount: "$channel" },
        { $limit: 3 }
      ]
    }
  },
  {
    $project: {
      total: {
        $ifNull: [
          { $arrayElemAt: ["$allOrders.value", 0] },
          0
        ]
      },
      paid: {
        $ifNull: [
          { $arrayElemAt: ["$paidOrders.value", 0] },
          0
        ]
      },
      byStatus: 1,
      byCountry: 1,
      topChannels: 1
    }
  }
]);
```

Output structure:

```javascript
{
  total: 8,
  paid: 4,
  byStatus: [
    { _id: "PAID", count: 4 },
    { _id: null, count: 2 },
    // Groups with frequency 1...
  ],
  byCountry: [
    { _id: "VN", count: 5 },
    { _id: "TH", count: 2 },
    { _id: "SG", count: 1 }
  ],
  topChannels: [
    { _id: "web", count: 4 },
    { _id: "app", count: 3 },
    { _id: "partner", count: 1 }
  ]
}
```

### 12.1. `$facet` Is Not "Free Queries"

`$facet` is helpful when several statistics share the same base dataset and the application wants a single structured response. However, it **does not make every aggregation cheaper**:

- Every branch still must group, count, or sort its data.
- `$facet` has its own memory and output document size limits.
- Placing `$facet` right at the start of a pipeline can restrict initial index usage; placing a selective `$match` beforehand can help.
- Many heavy branches in one pipeline can demand more resources than well-separated individual queries.

For example, if a dashboard covers only one month, place the date `$match` before `$facet` so every branch aggregates over the **same target month**.

### 12.2. Do Not Put `$count` After `$facet` to Get Total Orders

`$facet` normally returns **one document** holding arrays of statistics. Thus:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $facet: {
      byCountry: [{ $sortByCount: "$country" }]
    }
  },
  { $count: "outputDocuments" }
]);
```

counts **output documents emitted by `$facet`**, not source orders. To include total orders in the same dashboard, add an `allOrders: [{ $count: "value" }]` branch as in the pipeline above.

## 13. Getting the Most Popular Groups: Top N and Ties

`$sortByCount` already sorts frequencies descending, so taking the top three groups only requires adding `$limit`:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" },
  { $limit: 3 }
]);
```

The sample dataset has exactly three countries, so the output includes all three groups.

If a report only needs the **two most-used channels**, use:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$channel" },
  { $limit: 2 }
]);
```

Result:

```javascript
{ _id: "web", count: 4 }
{ _id: "app", count: 3 }
```

### 13.1. `$limit` After `$sortByCount` Does Not Reduce Source Documents Grouped

If you want the "top 3 countries across all 10 million orders," MongoDB must still compute frequencies across all eligible documents before knowing which three groups rank highest. `$limit: 3` **does not mean only reading three source documents**.

To shrink input data cleanly per business rules, place `$match` by time range, tenant, or appropriate filters before grouping.

### 13.2. Ties: Two Groups with Equal Frequency

In the sample dataset's tag statistics, both `vip` and `sale` appear three times. With the pipeline:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  { $sortByCount: "$tags" },
  { $limit: 1 }
]);
```

do not expect top 1 to always be `vip` or always be `sale`. Because the two groups tie in count, `$sortByCount` does not define a secondary order.

If the product needs deterministic results and wants to break ties by tag name:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tags",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } },
  { $limit: 1 }
]);
```

Under the sample dataset's default collation, ascending `_id` places `"sale"` before `"vip"` when counts tie. Under a different collation, string comparison order may differ.

### 13.3. Top N Including Tied Groups

"Top 3 groups" differs from "all groups whose frequency equals or exceeds the third group." When ties occur, `$limit: 3` returns **at most three group documents**, potentially dropping groups tied for third place.

If business requires keeping all tied groups, design a different pipeline (e.g., ranking with supported window stages) or determine the frequency cutoff explicitly. Do not assume `$sortByCount + $limit` provides "with ties" semantics.

## 14. Counting Orders, Line Items, and Product Quantities

Another example showing how the **counting unit** determines correctness.

In the sample dataset, `items` is an array of order line items:

```javascript
{
  _id: "O01",
  items: [
    { sku: "P01", quantity: 1 },
    { sku: "P02", quantity: 2 }
  ]
}
```

### 14.1. Counting Orders

```javascript
db.salesOrdersLesson.aggregate([
  { $count: "orders" }
]);
// { orders: 8 }
```

### 14.2. Counting Line Items

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$items" },
  { $count: "itemLines" }
]);
```

Total line items across the eight orders is **11**:

```text
O01: 2
O02: 1
O03: 1
O04: 2
O05: 1
O06: 3
O07: 0
O08: 1
-----------
Total: 11
```

### 14.3. Counting SKU Frequency by Line Items

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$items" },
  { $sortByCount: "$items.sku" }
]);
```

Here each SKU's `count` is **how many line items** carry that SKU, **not how many units of the product were sold**.

### 14.4. Total Product Quantity Uses `$sum`, Not `$sortByCount`

If a line item has `quantity: 5`, you must add five units, not count one occurrence. Use `$group`:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      lines: { $sum: 1 },
      units: { $sum: "$items.quantity" }
    }
  },
  { $sort: { units: -1, _id: 1 } }
]);
```

Here:

- `lines` counts line items.
- `units` sums `quantity`.
- The two numbers are equal only when every line item has quantity 1.

**`$sortByCount` cannot replace `$sum: "$items.quantity"`** when weighted sums or quantities are needed. Always check this before using frequencies to report revenue, unit counts, or loyalty points.

## 15. Performance and Execution Plans

`$count` and `$sortByCount` are frequently used in reports and dashboards where collections can be huge. To improve performance, distinguish **finding input documents** from **grouping/sorting work**.

### 15.1. `$match` Before Aggregation Can Leverage Indexes

Example filtering paid orders in Vietnam:

```javascript
db.salesOrdersLesson.createIndex({
  country: 1,
  status: 1
});

db.salesOrdersLesson.aggregate([
  {
    $match: {
      country: "VN",
      status: "PAID"
    }
  },
  { $count: "total" }
]);
```

An index can help narrow down examined documents, depending on the planner, data, and execution strategy. Creating an index does not guarantee every query or pipeline will pick it.

### 15.2. Grouping and Sorting Can Consume Heavy Memory

`$sortByCount` is equivalent to `$group` followed by `$sort`. If the grouping key has high cardinality (e.g., grouping by `userId` across tens of millions of users), the pipeline must maintain many groups and sort the results.

Certain aggregation stages can consume significant memory and hit resource caps; depending on version/configuration, eligible stages can spill temporary data to disk when enabled or allowed by default:

```javascript
db.salesOrdersLesson.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sortByCount: "$customerId" },
    { $limit: 20 }
  ],
  { allowDiskUse: true }
);
```

`allowDiskUse` does not make grouping/sorting free; it reduces the risk of hitting memory-limit errors for supported stages at the cost of disk I/O and resources. Not every performance bottleneck is solved by this option.

### 15.3. `$limit` After Grouping Does Not Reduce Source Documents Read

For:

```javascript
[
  { $match: { status: "PAID" } },
  { $sortByCount: "$customerId" },
  { $limit: 10 }
]
```

MongoDB must compute frequencies across **all matching PAID orders** before knowing the top 10 customers. The main optimizations are adding selective filters, designing matching indexes/query patterns, or maintaining pre-aggregated summaries if the report runs very frequently.

### 15.4. `explain()` for Aggregation

```javascript
db.salesOrdersLesson.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $sortByCount: "$country" }
]);
```

Depending on the MongoDB version, `explain` may show the pipeline lowered/optimized into stages including `$group` and `$sort` or equivalent execution nodes.

When reading it, check:

- `COLLSCAN` vs. `IXSCAN` for the input document set.
- `totalDocsExamined` and `totalKeysExamined` in the data-access section.
- Number of documents entering the grouping step.
- Sort cost, disk spill activity, and timing stats if reported.
- Final `nReturned`, which can be far smaller than scanned documents because each group emits only one document.

Do not read `$sortByCount`'s `nReturned` (the group count) and conclude the query "only read a few documents." Input document count drives grouping work.

### 15.5. Pre-Aggregated Summaries

For a dashboard needing status frequencies every minute over hundreds of millions of documents, running `$sortByCount` across the entire collection on every page load can be too costly. You can:

- Store summaries by day or tenant.
- Maintain counters on order write events.
- Update periodically via batch/stream jobs.
- Implement recomputation and reconciliation to handle duplicate events, retries, or order status transitions.

Example of a summary document:

```javascript
{
  _id: "2026-11-08:VN:PAID",
  day: "2026-11-08",
  country: "VN",
  status: "PAID",
  orderCount: 1250
}
```

This is **derived data**, not a count automatically kept accurate by MongoDB unless the application maintains it. Whenever figures affect billing or financial reporting, define consistency boundaries and drift-recovery procedures before adopting pre-aggregation.

## 16. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| `$count` counts the whole collection regardless of prior stages | It counts documents **reaching the `$count` stage** |
| `$count` on empty input returns `{ total: 0 }` | It returns zero documents; the application may need to default to 0 |
| `$count` returns a raw number directly from `aggregate()` | Aggregation returns a cursor, normally yielding one summary document if input exists |
| `$sortByCount` counts total documents in the collection | It groups by an expression and emits one document per group value |
| `$sortByCount` always sorts deterministically on tied counts | It only sorts by count descending; add a tie-breaker key if deterministic order is needed |
| `$sortByCount: "$tags"` counts each tag in the array | It groups by the **entire array value**; use `$unwind` first to count individual elements |
| `$unwind` does not change document counts | One document can expand into many; empty arrays are dropped by default |
| Counting tags after unwind gives the number of orders containing the tag | It counts **occurrences**; deduplicating order-tag pairs may be needed |
| `$sortByCount` can replace total units sold | It adds **1 per document**; use `$sum` to sum quantities |
| `$count` after `$group` still counts source documents | It counts **the number of groups** produced by `$group` |
| `$limit` before `$sortByCount` gets the top groups across all data | It only groups the already limited subset of documents |
| `$limit` after `$sortByCount` only reads N source documents | All input groups must be counted before the top N are known |
| `countDocuments()` and `estimatedDocumentCount()` are always equivalent | One counts by filter, the other estimates total collection size |
| `$sortByCount` cannot group by computed values | It accepts an aggregation expression such as `$switch`, `$toLower`, objects, etc. |
| Having an index guarantees frequency counts over millions of groups are fast | Grouping and sorting still incur memory/CPU/I/O costs |

## 17. Practice Exercises

### Exercise 1 — Conditional Counting

On the `salesOrdersLesson` collection:

1. Count all documents in the collection using `$count`.
2. Count `PAID` orders.
3. Count orders with `country: "VN"`.
4. Count orders that are both `PAID` and in `VN`.
5. Count orders with status `"REFUNDED"` and explain the result shape.

Predict outputs before running. Pay attention to the fifth case, which **does not return a document containing 0**.

### Exercise 2 — Computing Frequencies

Write pipelines using `$sortByCount` to return:

- `status` frequency.
- `country` frequency.
- `channel` frequency.
- `country` frequency among `PAID` orders only.

For each pipeline, identify `_id` and `count` of the groups. Explain why the output can contain an `_id: null` group.

### Exercise 3 — Converting `$sortByCount` to `$group`

Convert the pipeline:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$channel" }
]);
```

into `$group` with `$sum: 1` followed by `$sort`. Then add a secondary `_id: 1` key for tied counts. Explain why the expanded form is more flexible.

### Exercise 4 — Counting Tags

Given:

```javascript
{
  _id: "X1",
  tags: ["mongo", "java"]
}
{
  _id: "X2",
  tags: ["mongo", "mongo"]
}
{
  _id: "X3",
  tags: []
}
```

Distinguish between:

1. Direct `$sortByCount: "$tags"`.
2. `$unwind: "$tags"` followed by `$sortByCount: "$tags"`.
3. `$unwind`, deduplicating `(order, tag)` pairs, then `$sortByCount`.

Which approach counts **array combinations**, **occurrences**, or **distinct documents containing a tag**?

### Exercise 5 — Counting Distinct Groups

Write a pipeline to find the number of distinct `country` values using:

```javascript
{ $group: { _id: "$country" } }
{ $count: "distinctCountries" }
```

Then try using `$sortByCount` before `$count` and explain why the count is identical, while the first approach avoids an unnecessary sort step.

### Exercise 6 — Total Units Differs from SKU Line Frequency

Using `items` in the sample dataset:

1. Count orders.
2. Count item lines after `$unwind`.
3. Count item lines per SKU using `$sortByCount`.
4. Sum `quantity` per SKU using `$group` + `$sum`.

Explain why "SKU appeared in 3 lines" does not tell you how many **units** of that SKU were sold.

### Exercise 7 — Multi-Metric Dashboard with `$facet`

Design a pipeline returning:

```javascript
{
  totalOrders: 8,
  paidOrders: 4,
  byStatus: [ /* groups and counts */ ],
  byChannel: [ /* groups and counts */ ]
}
```

Note that `$count` branches emit either a single-element array or an empty array. Use `$arrayElemAt` and `$ifNull` to produce 0 where appropriate.

### Exercise 8 — Top N and Ties

Get the **top 1 most popular tag** from the sample dataset after `$unwind`. Explain why the result could be either `sale` or `vip`. Rewrite using `$group` and `$sort: { count: -1, _id: 1 }` to add a tie-breaking rule.

If the product requirement is "return all tags tied for first place," is `$limit: 1` enough? Propose how to find the highest count threshold so all groups reaching that threshold are kept.

### Exercise 9 — Bucketing by Price Tier

Write `$sortByCount` with `$switch` to divide `amount` into three tiers:

- Under 100,000.
- From 100,000 to under 300,000.
- 300,000 and above.

Predict the order count per tier, then adjust the thresholds and observe the frequency distribution. If `amount` is missing/null, where would business rules be added?

### Exercise 10 — Practicing with Execution Plans

Create a test index on `{ status: 1, country: 1 }`, then explain:

```javascript
db.salesOrdersLesson.explain("executionStats").aggregate([
  {
    $match: {
      status: "PAID",
      country: "VN"
    }
  },
  { $count: "total" }
]);
```

Observe the chosen index, `totalDocsExamined`, `totalKeysExamined`, and output. Because the sample dataset is tiny, if MongoDB selects `COLLSCAN`, can you conclude the index would be useless in production? Why or why not?

## 18. Key Takeaways

**`$count` produces one summary result** from the documents reaching it through prior stages. If input is empty, the pipeline emits no count document; the application must convert that to 0 when the API contract requires it.

**`$sortByCount` produces a frequency table** by grouping on an aggregation expression and sorting descending by `count`. It is equivalent to `$group` with `$sum: 1` and `$sort`, yet more concise when you only need the most frequent groups.

**The counting unit depends on pipeline position.** `$count` before `$unwind` counts orders; `$count` after `$unwind` counts array elements; `$count` after `$group` counts groups. Running `$sortByCount` on an entire array differs completely from `$unwind` followed by counting individual elements.

**Frequency counting is not weighted summing.** When you need revenue, unit quantities, scores, or other aggregations, use `$group` with the appropriate accumulators.

**Performance and correctness must be designed together.** Filter accurately with `$match`, handle missing/null explicitly, define tie-breaking rules for rankings, and optimize indexes or summaries only after clarifying both the dataset and the exact quantity being counted.