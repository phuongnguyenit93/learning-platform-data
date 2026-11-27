# `find`, `findOne`, and Query Filter Structure in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Query Documents

## 1. Objectives

When an application needs to retrieve data from MongoDB, the first question is: **which documents match the search criteria?** Two familiar methods in the MongoDB Shell are `find()` and `findOne()`. Both accept a **query filter** written as a document. The filter specifies the matching conditions; other options such as projection, sort, and limit specify how the data is returned.

After this lesson, you will be able to distinguish between `find()` and `findOne()`, write filters ranging from simple to nested, use comparison and logical operators, query embedded documents and arrays, properly handle `null` and missing fields, use projection and cursors, and implement equivalent filters using the MongoDB Java Sync Driver.

This lesson focuses on **document read** queries. For update and delete operations, filters share a similar structure, but the consequences are very different: an empty filter in a write or delete command can affect data across the collection, so it must be controlled carefully.

## 2. Preparing the Sample Dataset

Connect to the MongoDB Server using `mongosh`, for example:

```bash
mongosh "mongodb://127.0.0.1:27017"
```

In `mongosh`, run the following snippet. The data is inserted into the **`query_filter_lab`** database; six orders use fixed `_id` values. Using `replaceOne` with `upsert: true` lets you re-run the setup script without duplicating sample records:

```javascript
const lab = db.getSiblingDB("query_filter_lab");
const orders = lab.getCollection("orders");

const samples = [
  {
    _id: "O1001",
    status: "PAID",
    total: NumberDecimal("125.00"),
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    customer: { name: "Lan", city: "Hà Nội" },
    tags: ["priority", "online"],
    items: [
      { sku: "A", qty: 1, price: NumberDecimal("90.00") },
      { sku: "B", qty: 2, price: NumberDecimal("17.50") }
    ],
    shipped: true,
    coupon: null
  },
  {
    _id: "O1002",
    status: "NEW",
    total: NumberDecimal("45.00"),
    createdAt: ISODate("2026-11-02T10:30:00Z"),
    customer: { name: "Minh", city: "Đà Nẵng" },
    tags: ["online"],
    items: [{ sku: "A", qty: 1, price: NumberDecimal("45.00") }],
    shipped: false
  },
  {
    _id: "O1003",
    status: "PAID",
    total: NumberDecimal("210.00"),
    createdAt: ISODate("2026-11-03T11:00:00Z"),
    customer: { name: "Hòa", city: "TP Hồ Chí Minh" },
    tags: ["priority"],
    items: [
      { sku: "C", qty: 3, price: NumberDecimal("60.00") },
      { sku: "D", qty: 1, price: NumberDecimal("30.00") }
    ],
    shipped: true,
    coupon: "WELCOME"
  },
  {
    _id: "O1004",
    status: "CANCELLED",
    total: NumberDecimal("60.00"),
    createdAt: ISODate("2026-11-04T08:15:00Z"),
    customer: { name: "An", city: "Hà Nội" },
    tags: [],
    items: [{ sku: "D", qty: 2, price: NumberDecimal("30.00") }],
    shipped: false,
    coupon: null
  },
  {
    _id: "O1005",
    status: "PAID",
    total: NumberDecimal("80.00"),
    createdAt: ISODate("2026-11-05T14:00:00Z"),
    customer: { name: "Linh", city: "Hà Nội" },
    tags: ["online", "gift"],
    items: [
      { sku: "A", qty: 2, price: NumberDecimal("25.00") },
      { sku: "B", qty: 3, price: NumberDecimal("10.00") }
    ],
    shipped: false
  },
  {
    _id: "O1006",
    status: "PAID",
    total: NumberDecimal("140.00"),
    createdAt: ISODate("2026-11-06T16:45:00Z"),
    customer: { name: "Mai", city: "TP Hồ Chí Minh" },
    tags: ["priority", "online"],
    items: [{ sku: "A", qty: 4, price: NumberDecimal("35.00") }],
    shipped: true,
    coupon: "VIP"
  }
];

for (const document of samples) {
  orders.replaceOne({ _id: document._id }, document, { upsert: true });
}

print("Document count:", orders.countDocuments({
  _id: { $in: samples.map(document => document._id) }
}));
```

After running this, you will have the following data types to practice with:

| Field | BSON Type | Example |
|---|---|---|
| `_id` | String | `"O1001"` |
| `status` | String | `"PAID"` |
| `total` | Decimal128 | `NumberDecimal("125.00")` |
| `createdAt` | Date | `ISODate("2026-11-01T09:00:00Z")` |
| `customer` | Embedded document | `{ name: "Lan", city: "Hà Nội" }` |
| `tags` | Array of strings | `["priority", "online"]` |
| `items` | Array of documents | `[{ sku: "A", qty: 1, ... }]` |
| `coupon` | String, null, or missing | `"VIP"`, `null`, field omitted |

The result examples in this lesson assume the collection contains only these six sample orders. If there is already other data in the lab database, the total result count may vary.

## 3. Distinguishing `find()` and `findOne()`

### 3.1. `find()` Returns a Cursor

Syntax in the MongoDB Shell:

```javascript
db.collection.find(query, projection, options)
```

Where:

- **`query`:** document describing the filter condition; omitting it is equivalent to the filter `{}`.
- **`projection`:** document selecting which fields to return; optional.
- **`options`:** extended options when needed.

Examples:

```javascript
orders.find();                   // All documents
orders.find({});                 // All documents
orders.find({ status: "PAID" }); // Only documents with status = "PAID"
```

The return value is a **cursor**, used to iterate over 0 to many documents. The MongoDB Shell may display a batch of results, but that does not mean all documents have been loaded into client RAM.

```javascript
const cursor = orders.find({ status: "PAID" });

for (const document of cursor) {
  print(document._id, document.status);
}
```

When the result set is small, you can convert it to an array:

```javascript
const paidOrders = orders.find({ status: "PAID" }).toArray();
print("Order count:", paidOrders.length);
```

Avoid calling `toArray()` indiscriminately on millions of documents; cursors, projections, and limits help manage returned data.

### 3.2. `findOne()` Returns a Single Document or `null`

Common syntax:

```javascript
db.collection.findOne(query, projection, options)
```

Example lookup by `_id`:

```javascript
const order = orders.findOne({ _id: "O1001" });
if (order === null) {
  print("Not found");
} else {
  printjson(order);
}
```

If no document matches, `findOne()` returns `null`; whereas `find()` returns an empty cursor.

| Criterion | `find()` | `findOne()` |
|---|---|---|
| Returns | Cursor (0..N documents) | One document or `null` |
| Used for | Lists, searches, batch iteration | Looking up a single record |
| When no match | Empty cursor | `null` |
| Chained sort/limit | `.sort().limit()` | Does not return a cursor to chain |
| Projection | Yes | Yes |

### 3.3. One Document Does Not Mean "Newest"

If you write:

```javascript
orders.findOne({ status: "PAID" });
```

multiple `PAID` orders satisfy the condition. Do not assume MongoDB will return the newest order, the order with the smallest `_id`, or the first record chronologically. If you need the newest order, use explicit sort and limit:

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(1);
```

`-1` means descending; `1` means ascending. The `_id` tie-breaker makes the ordering deterministic when multiple documents share the same `createdAt`. If you need the document itself instead of a cursor, you can use `.sort(...).limit(1).next()` after checking that the cursor has a result, or in the Java driver use `.sort(...).first()`.

### 3.4. An Empty Filter Does Not Mean "Empty Document"

```javascript
orders.find({});
```

`{}` means **no filter constraints**. When an API accidentally passes an empty filter due to a programming bug, the query may return broader data than expected. Mandatory conditions and access scopes must be enforced at the application layer.

## 4. Query Filter Structure

A filter is a **document** whose keys describe fields or MongoDB operators. Common form:

```javascript
{
  status: "PAID",
  total: { $gte: NumberDecimal("100.00") }
}
```

Read as: find documents with `status` equal to `PAID` **and** `total` greater than or equal to 100.

```text
Query filter
{
  <field-name>: <literal-value | operator-document>,
  <another-field>: <literal-value | operator-document>,
  ...
}
```

**Short-form equality:**

```javascript
{ status: "PAID" }
```

**Operator-based equality:**

```javascript
{ status: { $eq: "PAID" } }
```

For the scalar string in this example, both filters are equivalent.

### 4.1. Implicit AND

Conditions inside the same filter on different fields are combined with AND:

```javascript
orders.find({
  status: "PAID",
  shipped: true
});
```

A document must satisfy **both** conditions.

### 4.2. Multiple Operators on One Field

```javascript
orders.find({
  total: {
    $gte: NumberDecimal("80"),
    $lt: NumberDecimal("150")
  }
});
```

This condition means `80 ≤ total < 150`. Group operators for the same field into one object, and avoid repeating the key `total` twice in the same JavaScript object.

### 4.3. Field Names vs. Operators

| Component | Example | Meaning |
|---|---|---|
| Top-level field | `status` | Field name in the document |
| Nested field | `"customer.city"` | Path to the city field |
| Comparison operator | `$gte` | Greater than or equal to |
| Logical operator | `$or` | One of the filter branches |
| Value | `"PAID"` | BSON string to compare against |
| Properly typed numeric value | `NumberDecimal("100")` | Decimal128 value |

MongoDB is case-sensitive for **field names**. The filter `{ Status: "PAID" }` is not equivalent to `{ status: "PAID" }`.

## 5. Comparison Operators

| Operator | Meaning | Example |
|---|---|---|
| `$eq` | Equal to | `{ status: { $eq: "PAID" } }` |
| `$ne` | Not equal to | `{ status: { $ne: "CANCELLED" } }` |
| `$gt` | Greater than | `{ total: { $gt: NumberDecimal("100") } }` |
| `$gte` | Greater than or equal to | `{ total: { $gte: NumberDecimal("100") } }` |
| `$lt` | Less than | `{ total: { $lt: NumberDecimal("100") } }` |
| `$lte` | Less than or equal to | `{ total: { $lte: NumberDecimal("100") } }` |
| `$in` | In a set of values | `{ status: { $in: ["NEW", "PAID"] } }` |
| `$nin` | Not in a set of values | `{ status: { $nin: ["NEW", "PAID"] } }` |

### 5.1. Filtering by Total Amount

```javascript
orders.find({
  total: { $gte: NumberDecimal("100.00") }
});
```

With the sample data, `O1001`, `O1003`, and `O1006` match.

### 5.2. Filtering Time Ranges with BSON Date

```javascript
orders.find({
  createdAt: {
    $gte: ISODate("2026-11-02T00:00:00Z"),
    $lt: ISODate("2026-11-05T00:00:00Z")
  }
});
```

This is a **lower-inclusive, upper-exclusive** range: from the start of November 2 to before the start of November 5 in UTC. This pattern is useful when filtering date ranges without relying on assumptions about the number of hours in a day in a local time zone.

Do not confuse BSON Date with a string:

```javascript
// Not equivalent: the value below is a string.
orders.find({ createdAt: { $gte: "2026-11-02" } });
```

MongoDB follows BSON type comparison rules and type bracketing. Always send filter values matching the stored data types, especially for dates, ObjectIds, Decimal128, and integers.

### 5.3. Not-Equal `$ne` Can Include Missing Fields

```javascript
orders.find({
  status: { $ne: "PAID" }
});
```

`$ne` can match documents that do not have the `status` field. If you require the field to exist:

```javascript
orders.find({
  status: { $exists: true, $ne: "PAID" }
});
```

Distinguish `"is not PAID"` from `"has a status other than PAID"` when the schema allows missing fields.

### 5.4. Using `$in` and `$nin`

```javascript
orders.find({ status: { $in: ["NEW", "PAID"] } });

orders.find({ status: { $nin: ["NEW", "CANCELLED"] } });
```

On the same field, `$in` is more concise than multiple OR branches. `$nin` can match documents missing the compared field, so consider adding `$exists` or specifying an allowed set of statuses if the data may be incomplete. Overly long `$in` lists can also incur query overhead; keep them bounded to business requirements.

## 6. Logical Operators `$and`, `$or`, `$nor`, `$not`

### 6.1. Using `$and` to Combine Filters

The following condition is equivalent to an implicit AND between two fields:

```javascript
orders.find({
  $and: [
    { status: "PAID" },
    { shipped: true }
  ]
});
```

`$and` is useful when composing filters from multiple components that cannot be expressed cleanly in a single object, or when applying multiple complex expressions to the same field.

### 6.2. Using `$or` for Multiple Branches

Find orders that are:

- Paid and have total 200 or more; **or**
- Newly created and have total less than 50.

```javascript
orders.find({
  $or: [
    {
      status: "PAID",
      total: { $gte: NumberDecimal("200") }
    },
    {
      status: "NEW",
      total: { $lt: NumberDecimal("50") }
    }
  ]
});
```

With the sample data, `O1003` and `O1002` satisfy the two respective branches.

### 6.3. Combining AND with OR

Find paid orders in Hà Nội or TP Hồ Chí Minh:

```javascript
orders.find({
  status: "PAID",
  $or: [
    { "customer.city": "Hà Nội" },
    { "customer.city": "TP Hồ Chí Minh" }
  ]
});
```

Equivalent condition: `status = PAID AND (city = Hà Nội OR city = TP Hồ Chí Minh)`. When two branches differ only in the value of the same field, you can replace them with `$in`:

```javascript
orders.find({
  status: "PAID",
  "customer.city": {
    $in: ["Hà Nội", "TP Hồ Chí Minh"]
  }
});
```

### 6.4. Using `$nor` and `$not`

```javascript
orders.find({
  $nor: [
    { status: "CANCELLED" },
    { total: { $gt: NumberDecimal("200") } }
  ]
});
```

`$nor` selects documents that **do not match any branch** in the list.

```javascript
orders.find({
  total: { $not: { $gte: NumberDecimal("100") } }
});
```

`$not` negates an expression on **a single field**. Depending on the case, `$not` can also match documents missing that field. Do not treat `$not` as an arbitrary top-level replacement for `$nor`.

### 6.5. Do Not Repeat the Same Key in a JavaScript Object

Writing it this way causes a logic bug:

```javascript
// Do not use: the same key status appears twice.
{
  status: { $ne: "NEW" },
  status: { $ne: "CANCELLED" }
}
```

A duplicate key overwrites the earlier condition. Use:

```javascript
{ status: { $nin: ["NEW", "CANCELLED"] } }
```

Or use `$and` to keep sub-filters separate if there is a clear reason to do so.

## 7. Querying Embedded Documents with Dot Notation

Given the data:

```javascript
customer: {
  name: "Lan",
  city: "Hà Nội"
}
```

query a nested field using dot notation:

```javascript
orders.find({
  "customer.city": "Hà Nội"
});
```

The dot in the string `"customer.city"` denotes the field path. It does not create a separate collection and is unrelated to namespace names.

You can combine nested fields:

```javascript
orders.find({
  "customer.name": "Lan",
  "customer.city": "Hà Nội"
});
```

### 7.1. Matching an Entire Embedded Document

```javascript
orders.find({
  customer: { name: "Lan", city: "Hà Nội" }
});
```

Equality comparison on an embedded document requires the object to match both the structure and **field order**. If the object stored in MongoDB has extra fields or a different field order, the equality filter may not match as expected. When you only need specific attributes, dot notation is usually easier to read and less coupled to exact structure.

### 7.2. Nested Paths Can Be Missing

```javascript
orders.find({
  "customer.phone": { $exists: false }
});
```

This condition finds documents that do not have the path `customer.phone`. In real data, missing the parent object `customer` versus missing only `phone` can have different business meanings; the query should reflect the exact data contract.

## 8. Querying Arrays and `$elemMatch`

### 8.1. Finding an Element in a String Array

With `tags` as an array:

```javascript
orders.find({ tags: "priority" });
```

In MongoDB, equality with a scalar matches when the array contains that element. This differs from equality on the entire array:

```javascript
orders.find({ tags: ["priority", "online"] });
```

The second query requires the array to match the exact elements **and order**.

If you want the array to contain both values regardless of position:

```javascript
orders.find({
  tags: { $all: ["priority", "online"] }
});
```

With the sample data, `O1001` and `O1006` satisfy the `$all` condition.

### 8.2. Checking Array Element Count

```javascript
orders.find({
  tags: { $size: 0 }
});
```

`$size: 0` finds empty arrays (`O1004` in the example). `$size` matches an exact element count; you cannot directly pass `$gte` into `$size` to check for "at least N elements".

### 8.3. Fields of an Array Containing Objects

Find orders with item SKU `A`:

```javascript
orders.find({
  "items.sku": "A"
});
```

You can add a quantity condition:

```javascript
orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
});
```

**Common pitfall:** the two conditions can match **two different elements** in the array. `O1005` has an item with SKU `A` and `qty = 2` and an item with SKU `B` and `qty = 3`, so the document still matches the filter above.

### 8.4. Using `$elemMatch` to Require the Same Element to Match

```javascript
orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
});
```

In the sample data, `O1006` matches because it has `{ sku: "A", qty: 4, ... }`, whereas `O1005` does not. Compare:

```text
"items.sku" = "A" AND "items.qty" >= 3
→ Can be two different elements.

items: { $elemMatch: { sku: "A", qty: { $gte: 3 } } }
→ The same element satisfies both conditions.
```

This is a critical distinction when filtering order items, event attributes, or any array of embedded documents.

## 9. `null`, Missing Fields, `$exists`, and `$type`

The sample dataset has three states for `coupon`:

- `O1001` and `O1004` have `coupon: null`.
- `O1002` and `O1005` do not have the `coupon` field.
- `O1003` and `O1006` have `coupon` as a string.

### 9.1. `{ coupon: null }` Matches Both `null` and Missing

```javascript
orders.find({ coupon: null });
```

The results in the lab include `O1001`, `O1002`, `O1004`, and `O1005`. This is MongoDB's null-equality semantics, not MongoDB automatically adding `coupon` to documents missing the field.

### 9.2. Matching Only Explicit `null` or Missing

```javascript
// Field exists and holds BSON null:
orders.find({ coupon: { $type: "null" } });

// Field does not exist:
orders.find({ coupon: { $exists: false } });

// Field exists, even if its value is null:
orders.find({ coupon: { $exists: true } });

// Field is a BSON string:
orders.find({ coupon: { $type: "string" } });
```

| Filter | Meaning |
|---|---|
| `{ coupon: null }` | Null **or** missing |
| `{ coupon: { $type: "null" } }` | Explicit null |
| `{ coupon: { $exists: false } }` | Missing |
| `{ coupon: { $exists: true } }` | Field is present, including null |
| `{ coupon: { $ne: null } }` | Field is present and not null |
| `{ coupon: { $type: "string" } }` | Has a string value |

### 9.3. Querying by Data Type

```javascript
orders.find({ total: { $type: "decimal" } });
orders.find({ createdAt: { $type: "date" } });
orders.find({ shipped: { $type: "bool" } });
```

In flexible-schema data, multiple BSON types can exist for the same field; verify the type before writing numeric or date comparisons. For arrays, `$type` also has special rules when inspecting array elements; consult the documentation to avoid incorrect assumptions.

## 10. Filtering Strings with Collation and Regular Expressions

### 10.1. Default Equality Is Typically Case-Sensitive

```javascript
orders.find({ status: "PAID" });
orders.find({ status: "paid" });
```

If the collection does not define another collation, default comparison uses binary simple collation, making `"PAID"` different from `"paid"`.

### 10.2. Collation Controls String Comparison

```javascript
orders.find({ status: "paid" })
  .collation({ locale: "en", strength: 2 });
```

Collation can enable case-insensitive string comparison. `strength: 2` preserves certain accent/diacritic differences, while `strength: 1` is a more basic comparison level; exact behavior depends on the locale. Collation only affects **string values**; it does not make field names `Status` and `status` equivalent.

For a query to leverage an index on a string field with collation, the index and the query must have compatible collations.

### 10.3. Filters Using `$regex`

Find customer names starting with `L`:

```javascript
orders.find({
  "customer.name": { $regex: /^L/ }
});
```

Or case-insensitive:

```javascript
orders.find({
  "customer.name": { $regex: "^l", $options: "i" }
});
```

Regular expressions should be bounded in length and complexity. Unanchored regexes or regexes with the `i` option are generally harder for indexes to optimize compared to proper equality or prefix queries. An index with a collation does not automatically make `$regex` case-insensitive through the same mechanism. Do not pass arbitrary user-supplied regexes directly into a search API without designing resource controls and metacharacter escaping.

## 11. Projection: Selecting Fields to Return

The **filter** determines which documents match; the **projection** determines which fields from those documents are returned.

```javascript
orders.find(
  { status: "PAID" },
  { status: 1, total: 1, "customer.name": 1 }
);
```

A value of `1` in a projection includes the field in the result. MongoDB returns `_id` by default unless explicitly excluded:

```javascript
orders.find(
  { status: "PAID" },
  { _id: 0, status: 1, total: 1, "customer.name": 1 }
);
```

Exclusion projection:

```javascript
orders.find(
  { status: "PAID" },
  { items: 0, tags: 0 }
);
```

In a standard projection, do not mix inclusion and exclusion for different fields, **except for `_id`**. Projection does not modify the data stored in the database.

### 11.1. Filter and Projection Are Different

```javascript
orders.find({ status: "PAID" });
// Only documents with status PAID, returning all fields.

orders.find({}, { status: 1 });
// All documents, returning only status and _id.

orders.find(
  { status: "PAID" },
  { _id: 0, status: 1, total: 1 }
);
// Only PAID, returning only status and total.
```

`findOne()` also accepts a projection:

```javascript
orders.findOne(
  { _id: "O1001" },
  { _id: 0, status: 1, total: 1 }
);
```

Projection is useful for reducing response size. However, for sensitive data, **authorization, identity verification, and API contracts** are still required; a projection in a single function is not a comprehensive security control.

## 12. Cursor, Sort, Limit, and Pagination

### 12.1. Sorting and Limiting

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(3);
```

The `status` condition selects records; `sort` specifies the order; `limit` returns at most three documents.

Without a sort, result order is not guaranteed to remain stable across executions. This can cause bugs in pagination, snapshot comparisons, and list rendering.

### 12.2. Pagination Using `skip()`

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .skip(2)
  .limit(2);
```

This approach is simple for small datasets. For deep pages, the server still has to process the skipped records; data changes between two requests can cause duplicate or missing records across pages.

### 12.3. Keyset Pagination

With `{ createdAt: 1, _id: 1 }` ordering, a query for the next page can find records after the last key pair of the previous page:

```javascript
const lastCreatedAt = ISODate("2026-11-03T11:00:00Z");
const lastId = "O1003";

orders.find({
  status: "PAID",
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $gt: lastId } }
  ]
})
  .sort({ createdAt: 1, _id: 1 })
  .limit(2);
```

This is called keyset or seek pagination. It is well-suited when deep pagination is needed and a stable sort key exists. The application must keep the filter, sort, collation, and desired data state consistent while the user navigates pages.

### 12.4. `find()` Does Not Load All Results Automatically

Cursors receive data in batches. On very large result sets, `toArray()` consumes more client memory than iterating the cursor; projection and limit help reduce transferred data. In the Java driver, close cursors and resource references according to the application lifecycle.

## 13. Filters and Indexes: Inspecting Query Plans

A correct filter can run fast on six documents but slow on millions of documents. Indexes help selective filters and sorts run efficiently.

In the lab, you can create an index to serve queries on status and date:

```javascript
orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_createdAt_desc" }
);
```

Query:

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(5);
```

Inspect the execution plan:

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(5)
  .explain("executionStats");
```

Common fields:

| Component | Meaning |
|---|---|
| `COLLSCAN` | Scans documents in the collection |
| `IXSCAN` | Scans an index |
| `nReturned` | Number of documents returned |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |

Plans can vary by MongoDB version and dataset. On a small lab dataset, a collection scan may be a reasonable choice by the query planner. Do not add indexes indiscriminately: indexes consume storage and memory and increase write overhead. Choose indexes based on real queries and measure their effectiveness with `explain`.

## 14. Java Sync Driver Example

In a Java project using the MongoDB Sync Driver, filters can be built using builders such as `Filters`, `Projections`, and `Sorts`.

Example Maven dependency:

```xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>5.5.0</version>
</dependency>
```

Version `5.5.0` is only an **illustrative reference**, not a claim of the latest release. Choose the actual version based on your dependency management, JDK, and the MongoDB Driver compatibility matrix.

### 14.1. Using `Filters` to Build Conditions

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

public class FindOrders {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            uri = "mongodb://127.0.0.1:27017";
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("query_filter_lab")
                    .getCollection("orders");

            Bson filter = Filters.and(
                    Filters.eq("status", "PAID"),
                    Filters.gte(
                            "total",
                            new Decimal128(new BigDecimal("100.00"))
                    )
            );

            FindIterable<Document> results = orders.find(filter)
                    .projection(Projections.fields(
                            Projections.include(
                                    "status", "total", "customer.name"
                            ),
                            Projections.excludeId()
                    ))
                    .sort(Sorts.descending("createdAt"))
                    .limit(10);

            for (Document order : results) {
                System.out.println(order.toJson());
            }
        }
    }
}
```

In the code above:

- `Filters.eq("status", "PAID")` corresponds to `{ status: "PAID" }`.
- `Filters.gte("total", ...)` corresponds to `{ total: { $gte: ... } }`.
- `Filters.and(...)` combines the two conditions.
- `Decimal128` matches the BSON Decimal128 type of the sample data.
- `Projections`, `Sorts`, and `limit` control the returned data.

### 14.2. `findOne` Equivalent in Java

With the Java Sync Driver, the standard way to retrieve a single document is `find(filter).first()`:

```java
Document first = orders.find(
        Filters.eq("_id", "O1001")
).first();

if (first == null) {
    System.out.println("Not found");
} else {
    System.out.println(first.toJson());
}
```

If you need the newest document, add `sort` before `first()`:

```java
Document newest = orders
        .find(Filters.eq("status", "PAID"))
        .sort(Sorts.descending("createdAt", "_id"))
        .first();
```

### 14.3. Using `elemMatch` in Java

```java
Bson filter = Filters.elemMatch(
        "items",
        Filters.and(
                Filters.eq("sku", "A"),
                Filters.gte("qty", 3)
        )
);

orders.find(filter).forEach(doc ->
        System.out.println(doc.getString("_id"))
);
```

Builders help organize queries clearly, but they do not automatically verify whether a field exists in the schema. A small typo like `customer.City` instead of `customer.city` can still produce wrong results. Define a consistent data contract and test against an appropriate database during application development.

## 15. Building Safe Filters from API Requests

APIs often expose parameters such as `status`, `minTotal`, and `fromDate`. You should not accept an arbitrary MongoDB filter document from the Internet and pass it straight into `find()`.

Example building a filter from validated values:

```javascript
const allowedStatuses = ["NEW", "PAID", "CANCELLED"];
const requestedStatus = "PAID";

if (!allowedStatuses.includes(requestedStatus)) {
  throw new Error("Invalid status");
}

const query = {
  status: requestedStatus,
  total: { $gte: NumberDecimal("100.00") }
};

printjson(orders.find(query).limit(20).toArray());
```

Key requirements:

1. **Allow only documented fields and operators** in the API; prevent clients from injecting `$where`, complex expressions, or unbounded filters.
2. **Parse and validate types** before constructing the BSON filter: monetary amounts as Decimal128 per contract, dates as BSON Date, identifiers in their proper types.
3. **Limit results** and enforce pagination to prevent accidentally dumping the entire collection.
4. **Inject authorization conditions** from a trusted server-side identity. For example, a `tenantId` filter must be combined via AND with the user's filter, never taken from a `tenantId` in the request body.
5. **Do not assemble JSON queries by string concatenation**, which risks escaping bugs, logic errors, and NoSQL injection vulnerabilities.
6. **Measure query execution time** and apply appropriate resource limits to search endpoints.

Query protection does not stop at the `find` statement: authentication, authorization, projection of sensitive fields, and result limits must all be enforced consistently.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `find()` returns more data than expected | Filter `{}` or omitted condition | Verify the filter and access-control constraints |
| `findOne()` returns an "out-of-order" record | Multiple records match without a sort | Look up by unique ID or use sort/limit |
| Date field does not match | String used instead of BSON Date | Use `ISODate` or the driver's date type |
| Numeric field does not match | Mixed decimal, double, and string data | Verify BSON types and standardize the schema |
| `Status` does not match `status` | Field names are case-sensitive | Use the exact field name |
| Filter `{ coupon: null }` also returns missing fields | Null equality matches null/missing | Use `$type: "null"` or `$exists: false` |
| `$ne` / `$nin` returns missing fields | Negation semantics | Combine with an existence check if needed |
| Array filter produces unexpected results | Conditions match different elements | Use `$elemMatch` |
| Array equality does not match | Element order or contents differ | Use `$all` if only containment of both values is needed |
| Duplicate key in filter object | Earlier key is overwritten | Merge operators or use `$and` |
| Regex is too slow | Low-selectivity pattern, unsuitable index | Constrain the pattern and inspect `explain()` |
| Pagination duplicates or misses records | Missing sort, deep skip, or changing data | Sort with a tie-breaker; consider keyset pagination |
| API returns unnecessary fields | Missing projection and access checks | Return only contracted fields and enforce authorization |

## 17. Comprehensive Exercises

The following exercises use the `orders` collection created in Section 2.

### Exercise 1: Find Orders with Simple Conditions

Write queries to:

- Retrieve `PAID` orders.
- Retrieve the exact order `O1003`.
- Retrieve orders with a total amount from 80 to less than 150.
- Retrieve orders created from the start of November 3 to before the start of November 6 in UTC.

Hints:

```javascript
orders.find({ status: "PAID" });
orders.findOne({ _id: "O1003" });

orders.find({
  total: {
    $gte: NumberDecimal("80"),
    $lt: NumberDecimal("150")
  }
});

orders.find({
  createdAt: {
    $gte: ISODate("2026-11-03T00:00:00Z"),
    $lt: ISODate("2026-11-06T00:00:00Z")
  }
});
```

### Exercise 2: Combining AND and OR

Find orders that are `PAID` and also satisfy either condition: total amount of 200 or more, or customer in Hà Nội.

```javascript
orders.find({
  status: "PAID",
  $or: [
    { total: { $gte: NumberDecimal("200") } },
    { "customer.city": "Hà Nội" }
  ]
});
```

In the sample data, orders `O1001`, `O1003`, and `O1005` match. Identify which OR branch each order satisfies.

### Exercise 3: Comparing Array Queries and `$elemMatch`

```javascript
const separate = orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
}).toArray();

const sameItem = orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}).toArray();

printjson(separate.map(doc => doc._id));
printjson(sameItem.map(doc => doc._id));
```

Why does `O1005` appear in the first query but not in the second? Because the item with `sku = "A"` and the item with `qty ≥ 3` are **two different elements**.

### Exercise 4: Distinguishing `null` from Missing

```javascript
print("Null or missing:");
printjson(orders.find(
  { coupon: null },
  { _id: 1 }
).toArray());

print("Explicit null:");
printjson(orders.find(
  { coupon: { $type: "null" } },
  { _id: 1 }
).toArray());

print("Missing:");
printjson(orders.find(
  { coupon: { $exists: false } },
  { _id: 1 }
).toArray());
```

Compare the three lists and explain the differences.

### Exercise 5: Projection, Sort, and Limit

Retrieve the three newest `PAID` orders, returning only `_id`, `status`, and `total`:

```javascript
orders.find(
  { status: "PAID" },
  { _id: 1, status: 1, total: 1 }
)
  .sort({ createdAt: -1, _id: 1 })
  .limit(3);
```

Change the projection to `{ _id: 0, status: 1, total: 1 }` to observe `_id` being excluded from the results; the filter condition remains unchanged.

### Exercise 6: Converting a Query to the Java Driver

Shell filter:

```javascript
{
  status: "PAID",
  "customer.city": "Hà Nội",
  total: { $gte: NumberDecimal("80") }
}
```

Equivalent filter in Java:

```java
Bson filter = Filters.and(
        Filters.eq("status", "PAID"),
        Filters.eq("customer.city", "Hà Nội"),
        Filters.gte("total", new Decimal128(new BigDecimal("80.00")))
);
```

Verify that both sides connect to the same `query_filter_lab` database and `orders` collection, and use the proper Decimal128 type.

## 18. Official Documentation

- [Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/)
- [db.collection.find()](https://www.mongodb.com/docs/manual/reference/method/db.collection.find/)
- [db.collection.findOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOne/)
- [Query and Projection Operators](https://www.mongodb.com/docs/manual/reference/operator/query/)
- [Comparison Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-comparison/)
- [Logical Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-logical/)
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/)
- [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/)
- [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver – Read Data](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)

A MongoDB filter is a document describing **logical conditions**. Mastering filter structure, BSON types, field paths, and array/`null` semantics ensures both `find()` and `findOne()` return the right documents; projection, sort, limit, and indexes then determine how well the query serves a real application.
