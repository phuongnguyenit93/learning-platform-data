# The Relationship Between BSON, Queries, Indexes, and Aggregation in MongoDB

## 1. The Big Picture

When working with MongoDB, four concepts—**BSON**, **queries**, **indexes**, and the **aggregation pipeline**—do not operate in isolation. They connect into a unified data-processing flow:

1. **BSON** determines which fields a document contains, what data types the values have, and how nested structures are organized.
2. **Queries** use those fields and data types to express which documents to find.
3. **Indexes** store keys extracted from documents, helping MongoDB locate or sort data more efficiently when the query shape fits.
4. **Aggregation** transforms a stream of documents into analytical results; some stages can still use indexes, whereas calculations and grouping typically process data after it is read.

```text
Application sends find / aggregate command
                   |
                   v
      Filter conditions + query operators
                   |
                   v
           Query planner
          /             \
   Index scan         Collection scan
  (IXSCAN, ...)          (COLLSCAN)
          \             /
           v           v
       Matching BSON documents
                   |
           Aggregation stages
     ($match, $unwind, $group, ...)
                   |
                   v
              BSON results
```

This diagram is a conceptual model. MongoDB may combine steps, choose different plans, or push certain filter conditions down to the data-reading phase. **Having an index does not mean every query or every aggregation stage can use it.**

### Running Example: Orders

Suppose the system stores an `orders` collection. The examples below use **mongosh** (MongoDB Shell) syntax; `ISODate(...)` and `NumberDecimal(...)` are BSON constructor helpers in the shell, not standard JSON syntax.

```javascript
db.orders.insertMany([
  {
    _id: 1001,
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-10-01T08:00:00Z"),
    shipping: { city: "Hanoi" },
    items: [
      { sku: "BOOK-01", category: "BOOK",
        quantity: 2, unitPrice: NumberDecimal("150000") },
      { sku: "PEN-01", category: "STATIONERY",
        quantity: 1, unitPrice: NumberDecimal("20000") }
    ]
  },
  {
    _id: 1002,
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-10-05T08:00:00Z"),
    shipping: { city: "Da Nang" },
    items: [
      { sku: "BOOK-01", category: "BOOK",
        quantity: 1, unitPrice: NumberDecimal("150000") },
      { sku: "PEN-01", category: "STATIONERY",
        quantity: 3, unitPrice: NumberDecimal("20000") }
    ]
  },
  {
    _id: 1003,
    customerId: "C02",
    status: "PENDING",
    createdAt: ISODate("2026-10-06T08:00:00Z"),
    shipping: { city: "Hanoi" },
    items: [
      { sku: "BOOK-01", category: "BOOK",
        quantity: 1, unitPrice: NumberDecimal("150000") }
    ]
  }
]);
```

Here, `createdAt` has a date-time type, `unitPrice` is a Decimal128 decimal number, `shipping` is a nested document, and `items` is an array of documents. These BSON characteristics directly influence filter expressions, index types, and how pipelines are written.

## 2. BSON Is the Foundation of Data and Query Expressions

### 2.1. What Is BSON?

**BSON (Binary JSON)** is the binary format representing MongoDB documents. Conceptually, a document resembles a JSON object made of `field: value` pairs, but BSON supports a richer set of data types than plain JSON:

| BSON Type | Example in mongosh | Significance When Querying |
|---|---|---|
| String | `"PAID"` | Distinct from numbers and values of other types |
| Integer / floating-point | `42`, `NumberInt(42)`, `NumberLong("42")` | Used with comparison and arithmetic operators; watch precision and numeric type |
| Decimal128 | `NumberDecimal("150000")` | Suitable for monetary amounts requiring exact decimal representation |
| Date | `ISODate("2026-10-01T08:00:00Z")` | Filtering date ranges and sorting chronologically |
| ObjectId | `ObjectId("507f1f77bcf86cd799439011")` | Common for `_id`, distinct from a string with the same character representation |
| Boolean | `true` | Filtering true/false states |
| Array | `["BOOK", "PEN"]` | Can generate multiple keys in a multikey index |
| Embedded document | `{ city: "Hanoi" }` | Queried via dot paths such as `shipping.city` |
| Null | `null` | Must distinguish a null value from a missing field |

MongoDB transmits, stores, and returns documents in BSON format across drivers and the server. Rendering them as JSON or mongosh syntax is merely a **human-readable representation** of the data. For example, Extended JSON may display a date and decimal as:

```json
{
  "createdAt": { "$date": "2026-10-01T08:00:00Z" },
  "unitPrice": { "$numberDecimal": "150000" }
}
```

Applications using a driver should pass Date, Decimal128, ObjectId, and other objects using the proper types supported by the driver; do not convert everything into strings.

### 2.2. Data Types Determine Matching Behavior

Consider two filter conditions:

```javascript
// Correct when createdAt is stored as a BSON Date.
db.orders.find({
  createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
});

// Not equivalent: this is a string.
db.orders.find({
  createdAt: { $gte: "2026-10-01T00:00:00Z" }
});
```

The second condition is not a date-time filter like the first; for many comparison operators, MongoDB applies BSON type bracketing rules. Similarly, `ObjectId("...")` is not equal to `"..."`, and storing prices sometimes as strings and sometimes as numbers makes filtering and aggregation unpredictable.

Some BSON numeric types can be compared by numeric value even when their storage types differ, but that **does not guarantee identical precision** during arithmetic. For monetary values, using Decimal128 consistently is generally safer than using binary floating-point numbers and expecting exact decimal results.

### 2.3. Nested Structures and Arrays Change Query Semantics

```javascript
// Read a field inside a nested document.
db.orders.find({ "shipping.city": "Hanoi" });

// Find orders where at least one element of items has this SKU.
db.orders.find({ "items.sku": "BOOK-01" });

// Both conditions must hold on the SAME array element.
db.orders.find({
  items: {
    $elemMatch: {
      category: "BOOK",
      quantity: { $gte: 2 }
    }
  }
});
```

If you only use `{ "items.category": "BOOK", "items.quantity": { $gte: 2 } }`, the two conditions could be satisfied by **two different array elements**. `$elemMatch` solves this. When indexing a path that traverses an array, MongoDB typically creates a **multikey index**, which has its own limitations and planning rules.

Another common source of confusion:

```javascript
db.orders.find({ couponCode: null });                // null OR missing field
db.orders.find({ couponCode: { $exists: false } });  // missing field
db.orders.find({
  couponCode: { $type: "null" }                        // actual BSON Null
});
```

Thus, before optimizing a query or index, you must know **which type** the actual data holds, **whether a field can be missing**, and **whether a field is an array or an object**.

## 3. Query: Expressing Which Documents to Find

### 3.1. A Filter Condition Is Not a Scan Algorithm

`find()` expresses the desired result, without dictating how the server searches for it:

```javascript
db.orders.find(
  {
    customerId: "C01",
    status: "PAID",
    createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
  },
  { _id: 0, customerId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(10);
```

The command above consists of four distinct parts:

- **Filter:** `customerId` and `status` equal specific values; `createdAt` falls within a time range.
- **Projection:** returns only the three specified fields; `_id: 0` hides the default `_id` field.
- **Sort:** orders by newest date first.
- **Limit:** returns at most 10 documents.

The query planner can read via an index, scan the collection, perform additional filtering on documents, or combine multiple stages. The logical result of the statement does not change when an index is added; **execution cost** can change dramatically.

### 3.2. Common Filter Operations

```javascript
// Equality match.
db.orders.find({ status: "PAID" });

// Range condition.
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-10-01T00:00:00Z"),
    $lt: ISODate("2026-11-01T00:00:00Z")
  }
});

// One of several values.
db.orders.find({ status: { $in: ["PAID", "PENDING"] } });

// Explicit logical combination when needed.
db.orders.find({
  $or: [{ customerId: "C01" }, { "shipping.city": "Hanoi" }]
});
```

Equality conditions, range conditions, array operators, and `$or` conditions can lead to different index usage strategies. For a query that returns almost the entire collection, a direct collection scan is sometimes more sensible than traversing an index and then fetching many documents.

## 4. Index: A Structure to Accelerate Certain Queries

### 4.1. What Does an Index Store?

You can picture a standard index as an ordered tree structure storing **keys extracted from BSON fields**, along with references to locate the documents. Instead of inspecting every order sequentially, the server can look up matching keys and retrieve the corresponding documents.

```javascript
db.orders.createIndex({ status: 1 });
```

The index above does not contain the full document contents; it focuses on the `status` field and document locations. By default, MongoDB also creates a unique index on `_id` when creating a standard collection.

Indexes have a **cost**: they consume storage space and add work when inserting, updating, and deleting documents. Creating an index on every field is not a good strategy.

### 4.2. Compound Index: Field Order Matters Greatly

For the requirement "view the 10 most recent paid orders of customer C01":

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});

db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(10);
```

With fixed values for `customerId` and `status`, the keys by `createdAt` in the index are already ordered in descending order. MongoDB **has the ability** to both narrow the read range and satisfy `sort` directly from the index, avoiding a separate sort step. This is an intuitive example of the **Equality → Sort → Range (ESR)** design guideline; ESR is a design guide, not a rule that is always optimal for every dataset size.

Field order is determined by **commonly used query shapes**, not simply by the order fields appear in BSON. The index `{ customerId: 1, status: 1, createdAt: -1 }` can also help queries using the `customerId` prefix, or `customerId + status`; however, it is not automatically optimal for a query filtering only on `createdAt`.

Note that the same index may not support a sort if the query lacks appropriate conditions on preceding fields, or if the collation does not match. The server always evaluates the actual execution plan.

### 4.3. Indexes on Nested Fields and Arrays

```javascript
db.orders.createIndex({ "shipping.city": 1 });
db.orders.createIndex({ "items.sku": 1 });
```

The path `shipping.city` is used identically in filters and in index definitions. For `items.sku`, because `items` is an array, MongoDB creates a multikey index: an order with multiple `sku` values can contribute multiple index keys. Consequently:

- **One index entry does not always correspond to a unique document**; the scan mechanism must handle multiple keys pointing to the same document.
- Having a condition on an array alone does not mean matches occur on the same element; `$elemMatch` is still required when business logic demands it.
- Compound multikey indexes have specific restrictions, especially when a document contains multiple indexed array fields simultaneously.
- An index on an array path does not automatically turn every array-related query or projection into a covered query.

### 4.4. Covered Query: Sometimes Reading Full BSON Is Unnecessary

If all fields required for filtering and returning are present in the index, and the conditions for the index to cover the query are met, the server may not need to fetch the original document:

```javascript
db.orders.createIndex({ customerId: 1, status: 1 });

db.orders.find(
  { customerId: "C01" },
  { _id: 0, customerId: 1, status: 1 }
);
```

The projection excludes `_id` because by default MongoDB returns it, whereas the example index does not include `_id`. You can check with `explain` to see whether the actual query is covered. Covered queries also depend on operators, index types, and data (especially array fields).

### 4.5. Read `explain()` Instead of Guessing

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .explain("executionStats");
```

Useful indicators in the output:

| Component / Metric | Practical Interpretation |
|---|---|
| `COLLSCAN` | Scanning the collection |
| `IXSCAN` | Scanning index keys |
| `FETCH` | Needs to read documents from the collection after finding keys |
| `SORT` | A sort stage is present in the plan; check whether the index already satisfies the sort |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of results returned |

Stage names and detailed `explain` structure may vary by MongoDB version and execution engine. Do not draw conclusions solely from seeing `IXSCAN`: an index that scans too many keys can still be costly. Compare actual data, filters, number of documents read, and measured latency.

## 5. Aggregation: Querying Combined with Data Transformation

### 5.1. A Pipeline Is a Sequence of Stages

`aggregate()` accepts an array of stages. Each stage receives documents from the previous stage and passes along filtered, transformed, or aggregated documents:

```text
orders (BSON documents)
  -> $match  (select only PAID orders)
  -> $unwind (each item becomes a processing record)
  -> $group  (sum revenue by category)
  -> $sort   (order categories by revenue)
  -> results
```

Common stages:

| Stage | Role |
|---|---|
| `$match` | Filter documents using MongoDB query expressions |
| `$project` / `$set` | Select, compute, or create fields |
| `$unwind` | Deconstruct each array element into a stream of documents |
| `$group` | Group documents and compute `$sum`, `$avg`, `$count`, etc. |
| `$sort` | Sort order |
| `$limit` / `$skip` | Limit or skip a number of results |
| `$lookup` | Join data from another collection based on matching conditions |

### 5.2. A Complete Pipeline

Requirement: **calculate revenue by product category for paid orders in October 2026**. The price of each line item is stored as Decimal128.

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-10-01T00:00:00Z"),
        $lt: ISODate("2026-11-01T00:00:00Z")
      }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.category",
      revenue: {
        $sum: {
          $multiply: ["$items.quantity", "$items.unitPrice"]
        }
      }
    }
  },
  { $sort: { revenue: -1 } }
]);
```

With the three sample orders, order `1003` is excluded because it is `PENDING`; the resulting values are:

```javascript
[
  { _id: "BOOK", revenue: NumberDecimal("450000") },
  { _id: "STATIONERY", revenue: NumberDecimal("80000") }
]
```

Step-by-step explanation:

1. `$match` selects orders `1001` and `1002` based on the BSON String `status` and BSON Date `createdAt`.
2. `$unwind` expands the two `items` arrays into four line items to calculate each product individually.
3. `$group` groups by `items.category`; `$multiply` calculates each line item total, and `$sum` totals the revenue.
4. `$sort` orders the two groups by the newly computed `revenue` field.

Important point: `revenue` **does not exist in the original documents or in a standard index**. It is a derived result produced after `$group`, so indexes on `createdAt` or `status` cannot directly sort by `revenue` in place of the final stage.

### 5.3. When Can Aggregation Use an Index?

MongoDB can optimize stages depending on the pipeline. A `$match` at the beginning of a pipeline usually has the same opportunity to use an index as `find()`:

```javascript
db.orders.createIndex({ status: 1, createdAt: -1 });
```

This index can narrow down `PAID` orders by the `createdAt` range **before** executing `$unwind` and `$group`. If only a small fraction of orders fall in the target month, aggregation cost will be significantly lower than scanning and processing all orders.

Conversely:

- `$group` may still have to process many input documents; an index does not automatically turn summation into an instant lookup.
- `$sort` **before transformations** can leverage index ordering when conditions align; `$sort` on a computed field after `$group` typically requires sorting results inside the pipeline.
- A `$match` after a stage that alters field values may not be pushed down to the data-reading phase. The optimizer only moves filters when semantics are preserved.
- `$lookup` can benefit from indexes on the joined collection, depending on join key fields and pipeline structure. Speed cannot be inferred merely from having created an index on the input collection.

Inspecting an aggregation execution plan:

```javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
    }
  },
  { $group: { _id: "$customerId", orderCount: { $sum: 1 } } }
]);
```

Information about index scans may appear under `queryPlanner`, `executionStats`, or stage structures depending on the version and engine. The goal is to verify **whether the input document set is read efficiently**, and then examine how much data subsequent stages process.

## 6. Combining the Four Concepts When Designing Features

Consider three different requirements on the same collection:

| Requirement | Related BSON | Query / Aggregation | Index Direction |
|---|---|---|---|
| List most recent PAID orders for customer C01 | `customerId`, `status` as String; `createdAt` as Date | `find` + filter + `sort` + `limit` | Compound index `{ customerId: 1, status: 1, createdAt: -1 }` |
| Count PAID orders per customer | String and Date if filtering by period | `$match` → `$group` | Index for `$match` filter; no guarantee the entire `$group` is handled by index |
| Calculate revenue per product category | `items` as array; `unitPrice` as Decimal128 | `$match` → `$unwind` → `$group` → `$sort` | Index to filter initial orders; revenue aggregation is subsequent work |

### 6.1. A Fast Query Does Not Mean a Fast Pipeline

Suppose an index helps `$match` find 100,000 orders quite quickly. If each order has 20 `items` lines, `$unwind` can produce a stream of roughly 2,000,000 documents to compute over. Therefore, distinguish between:

- **Document reading efficiency**: does the index reduce the number of documents examined?
- **Intermediate document volume**: does `$unwind` amplify the data?
- **Grouping and sorting cost**: are there too many groups, computed fields, or data that must be held in memory?
- **Numeric type accuracy**: are addition/multiplication operations using Decimal128 or an inappropriate numeric type?

These are distinct questions that must be measured at different layers.

### 6.2. Designing Schemas Around How Data Is Read and Processed

MongoDB is flexible in document structure, but that does not mean a field should arbitrarily change types. For example:

```javascript
// Avoid inconsistent data:
{ createdAt: "2026-10-01", unitPrice: "150000" }
{ createdAt: ISODate("2026-10-01T00:00:00Z"),
  unitPrice: NumberDecimal("150000") }
```

The two documents above may look similar on screen, but date filters and revenue calculations will behave differently. A good design typically:

1. Chooses a consistent BSON type for each business field.
2. Structures arrays and nested documents according to the queries that will actually be used.
3. Writes a few representative queries/pipelines before deciding on indexes.
4. Inspects `explain()` and real data volumes to validate choices.
5. Weighs write and storage overhead before adding indexes.

### 6.3. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| BSON is just JSON converted to binary | BSON has its own data types; types affect matching and computation |
| Having an index on a field makes every command using that field fast | Depends on operators, index field order, selectivity, sort, projection, and execution plan |
| Fields in a compound index can be reordered arbitrarily | Key order affects prefixes, range scans, and ability to satisfy sorts |
| Every pipeline leverages indexes end-to-end | Indexes are usually helpful at the filter/read stage; `$unwind`, `$group`, and computed fields incur their own costs |
| `$match` must always be written first regardless of content | Placing filters that narrow early is generally good, but conditions depending on newly computed fields must follow the stage that creates them |
| `"42"` and `42` are the same data | One value is a String, the other is a number; do not mix types |
| Conditions on two paths of the same array automatically match the same element | `$elemMatch` is required when multiple conditions must apply to the same element |

## 7. Self-Verification Practice

After creating the `orders` collection as shown at the beginning, you can run three experiments:

**Experiment A – With and without a compound index.** Run `explain("executionStats")` for a query filtering on `customerId` and `status`, then sorting by `createdAt`. Create the corresponding compound index and re-run to observe the plan. With only three sample documents, MongoDB may choose a collection scan because the dataset is too small; do not use timings from a tiny dataset to conclude an index is useless.

**Experiment B – Reordering stages.** Compare a pipeline filtering `status: "PAID"` before `$unwind` with a pipeline that can only filter a condition on an `items` line after `$unwind`. Identify which stage reduces order count, which stage increases intermediate line count, and why conditions tied to line items cannot be moved arbitrarily.

**Experiment C – Changing data types.** In a separate test collection, store the same date as both String and Date; compare querying with `ISODate`. Then compare monetary calculations on Decimal128 against prices stored as strings. The goal is to understand that a syntactically valid pipeline still depends on the BSON schema to produce correct results.

### Review Questions

1. Why cannot an index on `createdAt` fix the bug of storing dates sometimes as String and sometimes as Date?
2. Why is the `{ customerId: 1, status: 1, createdAt: -1 }` index better suited for querying a customer's most recent orders than an index on `status` alone?
3. If `$match` selects only 100 orders but `$unwind` generates 5,000 lines, at which step should further optimization be applied?
4. Why does `$sort` on newly computed revenue after `$group` usually not benefit from an index on the source collection?
5. When checking two attributes belonging to the same `items` element, why should `$elemMatch` be used?

**Key takeaway:** *BSON defines the nature of the data; queries describe the set to retrieve; indexes support access paths; aggregation processes and transforms the retrieved dataset.* To make MongoDB both **accurate** and **efficient**, view all four as part of a single flow.
