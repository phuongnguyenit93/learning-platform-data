# Value Sets with $in, $nin, and Edge Cases in MongoDB

## 1. When Do You Need to Query by a Set of Values?

In applications using MongoDB, a query may need to find orders in multiple statuses, products with any promotional tag, users belonging to allowed groups, or records not on a blocklist. Instead of writing multiple equality comparisons, MongoDB provides two operators in the **query predicate** group:

- `$in`: finds documents whose field matches **at least one value** in the list.
- `$nin` (*not in*): finds documents whose field **does not match any value** in the list; for many queries, it also matches documents **that do not have the inspected field**.

Syntax:

~~~javascript
db.collection.find({
  field: { $in: [value1, value2] }
});

db.collection.find({
  field: { $nin: [value1, value2] }
});
~~~

Both require their operand to be an **array of values**. They apply to scalar fields, array fields, fields inside nested objects, and properties of elements inside an array of objects.

This lesson belongs to the **Query Documents** chapter of **Database Engine Document MongoDB**. After completing it, you will be able to:

1. Choose `$in`, `$nin`, `$all`, or `$elemMatch` according to the exact requirement.
2. Predict filter results when a field is missing, equals `null`, is an empty array, or contains multiple elements.
3. Handle empty, duplicate, mistyped, and overly large input lists.
4. Distinguish `$in` as a query predicate from `$in` as an aggregation expression.
5. Write queries in `mongosh` and MongoDB Compass, and inspect performance with `explain`.

## 2. Understanding the Exact Semantics of $in and $nin

Suppose status set S = `["PAID", "SHIPPED"]`:

~~~text
status = "PAID"       $in: yes      $nin: no
status = "SHIPPED"    $in: yes      $nin: no
status = "NEW"        $in: no       $nin: yes
status = "CANCELLED"  $in: no       $nin: yes
~~~

| Characteristic | `$in` | `$nin` |
|---|---|---|
| Scalar field | Equals one value in the list | Differs from every value in the list |
| Array field | At least one element is in the list | No element is in the list |
| Missing field | Does not match a normal value list; `null` requires separate consideration | Selected under `$nin` semantics |
| Empty operand `[]` | Matches no documents | Excludes no values; can match the entire collection |
| Selectivity | Can be high if the list is small | Usually low, as it matches many other values and missing fields |

**Note:** `$nin` does not guarantee that the inspected field exists and holds a valid value. If business logic requires "the `status` field exists and is not in the excluded list", add `$exists: true` or a BSON type constraint.

~~~javascript
{
  status: {
    $exists: true,
    $nin: ["CANCELLED", "DRAFT"]
  }
}
~~~

## 3. Practice Dataset

Use a MongoDB Server/cluster where you have read/write permissions and open `mongosh`. All write examples below are intended only for the practice database:

~~~javascript
use query_set_lab
~~~

Load the `orders` collection:

~~~javascript
const demoOrders = [
  {
    _id: 1, status: "NEW", category: "books",
    title: "Sách Java",
    tags: ["sale", "new"], priority: NumberInt(1),
    assignee: null,
    customer: { tier: "silver", city: "Hà Nội" },
    items: [
      { sku: "A", qty: NumberInt(1) },
      { sku: "B", qty: NumberInt(3) }
    ]
  },
  {
    _id: 2, status: "PAID", category: "accessories",
    title: "Balo đi học",
    tags: ["gift"], priority: NumberInt(2),
    assignee: "lan",
    customer: { tier: "gold", city: "Đà Nẵng" },
    items: [
      { sku: "A", qty: NumberInt(4) },
      { sku: "C", qty: NumberInt(1) }
    ]
  },
  {
    _id: 3, status: "SHIPPED", category: "stationery",
    title: "Sổ ghi chú",
    tags: ["sale", "vip"], priority: NumberInt(3),
    assignee: "minh",
    customer: { tier: "gold", city: "Hà Nội" },
    items: [{ sku: "B", qty: NumberInt(2) }]
  },
  {
    _id: 4, status: "CANCELLED", category: "stationery",
    title: "Bút chì",
    tags: [], priority: NumberInt(1),
    assignee: "an",
    customer: { tier: "bronze", city: "Huế" },
    items: []
  },
  {
    _id: 5, status: "PAID", category: "books",
    title: "Tài liệu MongoDB",
    priority: null, assignee: "lan",
    customer: { tier: "silver", city: "Huế" },
    items: [{ sku: "D", qty: NumberInt(2) }]
  },
  {
    _id: 6, status: "PAID", category: "accessories",
    title: "Túi vải",
    tags: ["vip"], priority: NumberInt(2),
    assignee: null,
    customer: { tier: "gold", city: "Hà Nội" },
    items: [
      { sku: "A", qty: NumberInt(1) },
      { sku: "B", qty: NumberInt(7) }
    ]
  },
  {
    _id: 7, status: null, category: "home",
    title: "Ly thủy tinh",
    tags: ["sale"], priority: NumberInt(0),
    assignee: "ha",
    customer: { tier: "silver", city: "Huế" },
    items: []
  },
  {
    _id: 8, category: "home",
    title: "Bình giữ nhiệt",
    tags: ["clearance"], priority: NumberInt(1),
    assignee: "an",
    customer: { tier: "bronze", city: "Hà Nội" },
    items: [{ sku: "C", qty: NumberInt(5) }]
  },
  {
    _id: 9, status: "PAID", category: "books",
    title: "Bộ sách cơ sở dữ liệu",
    tags: ["sale", "gift"], priority: NumberInt(3),
    assignee: "linh",
    customer: { tier: "gold", city: "Đà Nẵng" },
    items: [{ sku: "X", qty: NumberInt(2) }]
  },
  {
    _id: 10, status: "SHIPPED", category: "stationery",
    title: "Hộp bút",
    tags: ["gift"], priority: NumberInt(2),
    assignee: "van",
    customer: { tier: "silver", city: "Huế" },
    items: [{ sku: "B", qty: NumberInt(4) }]
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.countDocuments({});
~~~

On a new collection, the last command returns **10**. `replaceOne` with `upsert: true` lets you re-run the script without duplicating `_id`; however, it **resets the contents of the 10 sample documents** if they were modified earlier. It does not delete other documents that exist in the collection. The expected ID lists below assume the collection contains only these 10 sample records.

Intentional edge cases:

- ID 7 has `status: null`; ID 8 **does not have the status field**.
- ID 4 has `tags: []`; ID 5 **does not have the tags field**.
- The `tags` field is an array of strings; `items` is an array of objects.
- The `priority` field is an Int32 in most records, but equals `null` in ID 5.
- The `customer` field is an object with nested fields `tier` and `city`.

When verifying results, use projection and `sort`:

~~~javascript
db.orders.find(
  { status: { $in: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

## 4. Using $in with a Scalar Field

### 4.1. Status Belongs to One of the Allowed Values

~~~javascript
db.orders.find(
  { status: { $in: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1, title: 1 }
).sort({ _id: 1 });
~~~

Result: IDs **2, 3, 5, 6, 9, 10**.

This query is logically equivalent to:

~~~javascript
db.orders.find({
  $or: [
    { status: "PAID" },
    { status: "SHIPPED" }
  ]
});
~~~

When the alternatives are equality checks on the same field, `$in` is usually easier to read than a long list of `$or` branches. For different conditions across multiple fields, `$or` remains appropriate.

### 4.2. Integer Set

~~~javascript
db.orders.find(
  { priority: { $in: [NumberInt(1), NumberInt(3)] } },
  { _id: 1, priority: 1 }
).sort({ _id: 1 });
~~~

Result: IDs **1, 3, 4, 8, 9**.

The list `[1, 3]` is the set of accepted values. Documents with `priority: 0`, `priority: 2`, and `priority: null` do not match.

### 4.3. Multiple Conditions Joined by AND

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] },
  priority: { $gte: 2 }
});
~~~

MongoDB combines conditions on two different fields with AND by default:

~~~text
status in {"PAID", "SHIPPED"}
AND priority >= 2
~~~

Result on the sample dataset: IDs **2, 3, 6, 9, 10**. ID 5 is excluded because `priority: null`.

Multiple `$in` operators can appear in the same filter:

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] },
  category: { $in: ["books", "stationery"] }
});
~~~

This is an AND between the two selection groups, not an OR between the two fields.

## 5. Using $nin to Exclude a Set

### 5.1. Status Not in an Excluded List

~~~javascript
db.orders.find(
  { status: { $nin: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

Result: IDs **1, 4, 7, 8**.

- ID 1 has status `NEW`.
- ID 4 has status `CANCELLED`.
- ID 7 has the `status` field with value `null`.
- ID 8 does not have the `status` field at all.

**ID 8 is the key takeaway:** `$nin` also selects documents missing the field. Therefore, a filter with only `$nin` is not enough to express "orders with a valid status other than PAID/SHIPPED".

### 5.2. Combining with $exists

~~~javascript
db.orders.find(
  {
    status: {
      $exists: true,
      $nin: ["PAID", "SHIPPED"]
    }
  },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

Result: IDs **1, 4, 7**; ID 8 is excluded. However, ID 7 is still present because `$exists: true` accepts a field whose value is null.

If `status` must be **of type string**:

~~~javascript
db.orders.find({
  status: {
    $type: "string",
    $nin: ["PAID", "SHIPPED"]
  }
});
~~~

Result: IDs **1, 4**.

### 5.3. Prefer a Whitelist Over a Blacklist When Business Logic Demands It

A requirement for "active order statuses" is often better expressed as an allowed set:

~~~javascript
db.orders.find({
  status: { $in: ["NEW", "PAID", "SHIPPED"] }
});
~~~

This avoids matching documents missing `status`, having `status: null`, or holding an unexpected status introduced in the future. Conversely, `$nin: ["CANCELLED"]` lets all of those cases through. For workflows requiring well-defined statuses, define the **valid value set** upfront.

## 6. Array Fields: At Least One Element and No Elements

### 6.1. $in on the tags Array

~~~javascript
db.orders.find(
  { tags: { $in: ["sale", "vip"] } },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Result: IDs **1, 3, 6, 7, 9**. Having **one element** in `tags` appear in the list is enough.

ID 3 has both `sale` and `vip`, yet it still appears **only once** in the `find()` result. MongoDB returns matching documents; it does not duplicate documents per matching element.

### 6.2. $nin on the tags Array

~~~javascript
db.orders.find(
  { tags: { $nin: ["sale", "vip"] } },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Result: IDs **2, 4, 5, 8, 10**.

Here:

- ID 2 has array `["gift"]`, containing no excluded tags.
- ID 4 has an empty array `[]`, containing no excluded tags.
- ID 5 **lacks the tags field**, yet still matches `$nin`.
- ID 8 has array `["clearance"]`, containing no excluded tags.

To match only documents that have an array-typed `tags` field and contain no excluded values:

~~~javascript
db.orders.find({
  tags: {
    $type: "array",
    $nin: ["sale", "vip"]
  }
});
~~~

Result: IDs **2, 4, 8, 10**; ID 5 is excluded. ID 4 is still selected because an empty array satisfies "contains no excluded tags".

### 6.3. $all Differs from $in

~~~javascript
// Has sale OR vip
db.orders.find({
  tags: { $in: ["sale", "vip"] }
});

// Has sale AND vip
db.orders.find({
  tags: { $all: ["sale", "vip"] }
});
~~~

The first query matches IDs `1, 3, 6, 7, 9`. The second matches only ID **3**.

| Requirement | Operator |
|---|---|
| Has at least one value in the set | `$in` |
| Has none of the excluded values | `$nin` |
| Contains every required value | `$all` |
| A single element must satisfy multiple conditions | `$elemMatch` |

`$all` does not require the array to have **exactly** two elements or match the filter list's order. If the array contains additional tags, it still matches.

## 7. Edge Cases: Empty Arrays, Missing Fields, and Null

### 7.1. Empty Comparison List

~~~javascript
db.orders.find({ status: { $in: [] } });
~~~

**Result:** no documents match, because no allowed values exist.

~~~javascript
db.orders.find({ status: { $nin: [] } });
~~~

**Result:** no values are excluded; on the 10-document sample collection, all **10** documents match, including documents missing the field.

If an API receives an empty value list, the application must explicitly define whether that means "return empty" or "apply no filter". Do not let `$in: []` or `$nin: []` accidentally dictate business behavior.

In particular, avoid passing `$nin: []` to `updateMany` or `deleteMany` when the list is dynamically generated without validation, as it can affect the entire collection.

### 7.2. List with Duplicate Elements

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "PAID", "SHIPPED"] }
});
~~~

Semantically, this yields the same result as `["PAID", "SHIPPED"]`. Duplicates can be stripped in the application layer to keep query size smaller and logs cleaner.

### 7.3. The Field Itself Is an Empty Array

~~~javascript
db.orders.find({ tags: { $size: 0 } });
~~~

Result: ID **4**. Meanwhile:

~~~javascript
db.orders.find({ tags: { $exists: false } });
~~~

Result: ID **5**.

These two cases are distinct: `tags: []` has an array-typed field, whereas ID 5 does not have the `tags` field.

To find arrays that have at least a first element:

~~~javascript
db.orders.find({
  tags: { $type: "array" },
  "tags.0": { $exists: true }
});
~~~

This excludes empty arrays and documents missing the field. Do not use `$nin: []` as a substitute for checking non-empty arrays.

### 7.4. Distinguishing Null and Missing

In the dataset:

~~~javascript
// ID 7
{ _id: 7, status: null }

// ID 8
{ _id: 8, /* no status */ }
~~~

Diagnostic queries:

~~~javascript
// Equal to null under equality semantics: null or missing
db.orders.find({ status: null });

// Only missing field
db.orders.find({ status: { $exists: false } });

// Only present field holding BSON Null
db.orders.find({ status: { $type: "null" } });

// Field exists, including null
db.orders.find({ status: { $exists: true } });

// Field has a non-null value
db.orders.find({ status: { $ne: null } });
~~~

On the sample dataset, `{ status: null }` selects IDs **7, 8**; `$exists: false` selects ID **8**; `$type: "null"` selects ID **7**.

`$exists: true` does not mean "not null"; it only checks whether the field is present. A null field is also not equivalent to the string `"null"`.

### 7.5. Null Inside an $in or $nin List

~~~javascript
db.orders.find({
  status: { $in: [null] }
});

db.orders.find({
  status: { $nin: [null] }
});
~~~

MongoDB has specific semantics for null equality and absent fields. When business logic needs to distinguish **true null** from **missing**, write explicit conditions using `$type` or `$exists` instead of relying on simple mathematical assumptions that `$in: [null]` and `$nin: [null]` are always strict complements in all special BSON scenarios.

Clear, intent-revealing filter patterns:

~~~javascript
// Missing field only
{ status: { $exists: false } }

// BSON Null only
{ status: { $type: "null" } }

// Has a non-null value
{ status: { $ne: null } }

// Status must be a string and not in the excluded set
{ status: { $type: "string", $nin: ["CANCELLED"] } }
~~~

For legacy data containing BSON Undefined or arrays containing null, check comparison behavior in your MongoDB version, as those special types have specific rules.

### 7.6. Non-Array Operand

~~~javascript
// Valid
{ status: { $in: ["PAID"] } }

// Invalid: argument to $in is not an array
{ status: { $in: "PAID" } }

// Invalid: argument to $nin is an object
{ status: { $nin: { value: "PAID" } } }
~~~

MongoDB requires the operand of these query predicates to be an array. When accepting input from a form or API, parse and validate the list before passing it to the driver.

## 8. Data Types and Equality Comparisons

MongoDB stores values with BSON types. `$in`/`$nin` do not automatically cast strings to numbers or ObjectIds.

### 8.1. String Differs from Number

~~~javascript
// In the sample dataset, priority is a BSON number
db.orders.find({
  priority: { $in: [NumberInt(1), NumberInt(2)] }
});

// List containing strings "1", "2"
db.orders.find({
  priority: { $in: ["1", "2"] }
});
~~~

The string `"2"` is not automatically converted to the number `2`. Conversely, across **BSON numeric types**, MongoDB compares by numeric value; do not assume Int32 and Int64 with the same value are always treated as unequal under numeric comparison.

When a domain field must have a single type, use schema validation and normalize input data instead of stuffing multiple mismatched types into the same `$in` list.

### 8.2. ObjectId Differs from Hex String

~~~javascript
const id = ObjectId("64a000000000000000000001");

db.someCollection.find({
  _id: { $in: [id] }
});

db.someCollection.find({
  _id: { $in: ["64a000000000000000000001"] }
});
~~~

These two queries are not equivalent if `_id` actually stores an ObjectId. `someCollection` is just an illustrative collection name; the `orders` dataset above uses numeric `_id` values.

### 8.3. Date Differs from ISO String

~~~javascript
{
  createdAt: {
    $in: [
      ISODate("2026-11-01T00:00:00Z"),
      ISODate("2026-11-02T00:00:00Z")
    ]
  }
}
~~~

When `createdAt` is a BSON Date, passing a date-time string does not automatically turn it into a Date. `$in` compares **exact timestamps**; to match all orders within a day, use a `$gte` and `$lt` range.

### 8.4. Case Sensitivity and Collation

~~~javascript
db.orders.find({ status: { $in: ["paid"] } });
~~~

Under default case-sensitive string comparison, `"paid"` differs from `"PAID"`. You can specify an appropriate collation:

~~~javascript
db.orders.find({
  status: { $in: ["paid", "shipped"] }
}).collation({ locale: "en", strength: 2 });
~~~

Ensure indexes supporting the query have a compatible collation. For status enums, it is usually best to enforce canonical casing on write so multiple string variants do not represent the same state.

## 9. Querying Nested Fields and Arrays of Objects

### 9.1. Dot Notation with Objects

~~~javascript
db.orders.find({
  "customer.tier": { $in: ["gold", "silver"] }
});
~~~

The path `customer.tier` compares a field inside an object without needing to match the entire `customer` object.

~~~javascript
db.orders.find({
  "customer.city": { $nin: ["Hà Nội", "Huế"] }
});
~~~

If `customer.city` is missing, `$nin` semantics with absent fields still apply and must be considered.

### 9.2. Dot Notation with Arrays of Objects

~~~javascript
db.orders.find({
  "items.sku": { $in: ["A", "B"] }
});
~~~

Result: IDs **1, 2, 3, 6, 10**. The query selects orders where at least one `items` element has SKU A or B.

### 9.3. When Multiple Conditions Must Hold on the Same Element

Requirement: at least one line item with SKU A/B and quantity ≥ 3.

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $in: ["A", "B"] },
      qty: { $gte: 3 }
    }
  }
});
~~~

Result: IDs **1, 2, 6, 10**. ID 3 has SKU B, but qty = 2.

If you write:

~~~javascript
db.orders.find({
  "items.sku": { $in: ["A", "B"] },
  "items.qty": { $gte: 3 }
});
~~~

the two conditions can match **two different elements** in the array. To observe this yourself, insert into the practice collection:

~~~javascript
db.orders.replaceOne(
  { _id: 11 },
  {
    _id: 11,
    status: "NEW",
    title: "Cross-element case",
    items: [
      { sku: "A", qty: NumberInt(1) },
      { sku: "Z", qty: NumberInt(10) }
    ]
  },
  { upsert: true }
);
~~~

For ID 11, the two-independent-paths query matches because the first element has SKU A and the second has qty 10; the `$elemMatch` query **does not match** because no single element satisfies both conditions.

When finished, you can remove that specific test record:

~~~javascript
db.orders.deleteOne({ _id: 11 });
~~~

### 9.4. $nin on a Property of an Array of Objects

~~~javascript
db.orders.find({
  "items.sku": { $nin: ["A", "B"] }
});
~~~

This means **no element** has SKU A or B; it does not mean "there exists at least one line item with an SKU other than A/B". For the second requirement, require an element to satisfy the condition:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $exists: true, $nin: ["A", "B"] }
    }
  }
});
~~~

The two queries have different semantics, especially when an array contains both an excluded SKU and an allowed SKU.

## 10. Regular Expressions in an $in Set

In the **query predicate** context, `$in` can accept JavaScript regular expression literals:

~~~javascript
db.orders.find({
  title: {
    $in: [/^Sách/, /^Bộ sách/, "Balo đi học"]
  }
});
~~~

The sample dataset has titles such as `Sách Java`, `Bộ sách cơ sở dữ liệu`, and `Balo đi học` matching the expression. The `^` symbol anchors to the start of the string; add the `i` flag for case-insensitive matching.

**Do not place `$regex` objects inside an `$in` array** like this:

~~~javascript
// Incorrect way to write a query $in with regex
{
  title: {
    $in: [
      { $regex: "^Sách" }
    ]
  }
}
~~~

Use a regex literal:

~~~javascript
{ title: { $in: [/^Sách/] } }
~~~

Or use `$regex` outside `$in` when only one pattern is needed:

~~~javascript
db.orders.find({
  title: { $regex: "^sách", $options: "i" }
});
~~~

Overly broad regex patterns can consume significant resources or fail to leverage indexes effectively. If patterns come from users, constrain length, syntax, and execution cost.

## 11. Query $in vs. Aggregation Expression $in

MongoDB uses the same name `$in` across two operator groups.

### 11.1. Query Predicate

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] }
});
~~~

Queries directly against a field. If the field is an array, an element of the array can match.

### 11.2. Aggregation Expression

The syntax inside `$project`, `$set`, and `$expr` is:

~~~javascript
{
  $in: [<expressionOfValue>, <expressionOfArray>]
}
~~~

Example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      isReady: {
        $in: ["$status", ["PAID", "SHIPPED"]]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

The aggregation expression returns a boolean, requires **exactly two arguments**, and the second argument must evaluate to an array. It does not perform regex matching like the query predicate `$in`.

To check for the `"sale"` tag inside the array field `tags`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      hasSaleTag: {
        $in: ["sale", { $ifNull: ["$tags", []] }]
      }
    }
  }
]);
~~~

`$ifNull` turns missing or null fields into `[]`. If data could contain a string instead of an array, check with `$isArray` or normalize beforehand to avoid a non-array argument error.

If the `status` field itself is an array, `$in: ["$status", ["PAID","SHIPPED"]]` compares **the entire array** as a single value; it does not check element intersection like the query predicate on an array field. To intersect two arrays, use `$setIntersection` when both sources are arrays.

### 11.3. Negating the $in Expression

In aggregation, you can combine `$not` with the `$in` expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      isOutsideSet: {
        $not: [
          { $in: ["$status", ["PAID", "SHIPPED"]] }
        ]
      }
    }
  }
]);
~~~

This negates the expression; do not assume all missing/null cases behave identically to the query predicate `$nin`. When type distinction matters, use `$type`, `$ifNull`, or explicit conditions.

## 12. Indexes, Selectivity, and Performance

### 12.1. Running explain for $in

~~~javascript
db.orders.createIndex({ status: 1 });

db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] }
}).explain("executionStats");
~~~

Inspect:

- `winningPlan`: the execution plan selected by MongoDB.
- `IXSCAN`: index scan.
- `COLLSCAN`: full collection scan.
- `totalKeysExamined`: number of index keys scanned.
- `totalDocsExamined`: number of documents inspected.
- `nReturned`: number of documents returned.

With 10 documents, the query planner may choose `COLLSCAN` even when an index exists; do not treat this as a bug. Compare on datasets and workloads representative of production.

### 12.2. Why Can $nin Be Slow?

~~~javascript
db.orders.find({
  status: { $nin: ["PAID", "SHIPPED"] }
}).explain("executionStats");
~~~

`$nin` usually has **low selectivity** because it can match most of the collection as well as missing fields. An index may not make the query faster. If business logic only needs a small set of valid statuses, switching to `$in` with an explicit whitelist can make data selection more targeted; performance should still be measured.

### 12.3. $in Lists with Many Values

When the list grows to hundreds or thousands of elements, the query must process many values, incurring parsing, network transfer, index lookup, and result-merging overhead. You should:

1. Bound and deduplicate lists received from APIs.
2. Monitor filter size and selectivity.
3. Run `explain` on realistic data.
4. Consider batching when appropriate, while accounting for round-trip overhead.
5. Consider an alternative design if the list comes from a separate collection.

Do not pick an arbitrary fixed threshold and claim every query above it is slow; performance depends on indexes, data, and how MongoDB plans execution.

### 12.4. Collation and Indexes

A query using a case-insensitive collation for string comparison may require an index configured with a compatible collation. Otherwise, MongoDB may not use the index as expected for string comparisons. For machine-readable statuses with a finite set of values, normalizing input values usually keeps both data and filters simpler.

## 13. Equivalent Filters in MongoDB Compass

Connect Compass to the same server, select database `query_set_lab` and collection `orders`, open the **Documents** tab, and enter the following filters in the Query Bar:

| Requirement | Filter |
|---|---|
| Paid or shipped orders | `{"status":{"$in":["PAID","SHIPPED"]}}` |
| Exclude PAID and SHIPPED | `{"status":{"$nin":["PAID","SHIPPED"]}}` |
| Status must exist and not be excluded | `{"status":{"$exists":true,"$nin":["PAID","SHIPPED"]}}` |
| Has sale or vip tag | `{"tags":{"$in":["sale","vip"]}}` |
| Has no excluded tags | `{"tags":{"$nin":["sale","vip"]}}` |
| Has both sale and vip | `{"tags":{"$all":["sale","vip"]}}` |
| Gold or silver customer | `{"customer.tier":{"$in":["gold","silver"]}}` |
| SKU A/B and qty ≥ 3 in the same line item | `{"items":{"$elemMatch":{"sku":{"$in":["A","B"]},"qty":{"$gte":3}}}}` |
| Only missing status field | `{"status":{"$exists":false}}` |

Click **Find** or **Apply** (depending on version) and compare results with mongosh. If document counts differ, check that you are connected to the right server/collection, cleared old filters, refreshed the view, and have no extra documents beyond the sample set.

The JSON filter bar in Compass requires double-quoted keys and strings. mongosh syntax uses JavaScript objects, so many examples omit quotes around keys. The **Explain Plan** tab in Compass, when available, helps inspect how the server executes the filter.

## 14. Using in a Java Application

With the MongoDB Java Driver, you can construct `$in` and `$nin` filters using the `Filters` class instead of concatenating JSON strings:

~~~java
import static com.mongodb.client.model.Filters.in;
import static com.mongodb.client.model.Filters.nin;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.exists;

import java.util.List;
import org.bson.conversions.Bson;

List<String> allowed = List.of("PAID", "SHIPPED");

Bson allowedStatuses = in("status", allowed);
Bson excludedStatuses = nin("status", allowed);

Bson excludedButPresent = and(
    exists("status", true),
    nin("status", allowed)
);
~~~

`allowedStatuses` selects statuses in the set; `excludedStatuses` excludes statuses in the set; `excludedButPresent` adds the requirement that the field must exist.

When an API accepts a list:

- Validate each value against an allowed enum set; prevent clients from sending arbitrary operator objects.
- Define case-normalization rules.
- Deduplicate and cap the number of elements.
- Define the exact semantics of an empty list.
- Ensure proper BSON types before building the filter.
- Never build JSON query strings by concatenating untrusted input.

These steps reduce data bugs and NoSQL injection risks when filters are built from external input.

## 15. Caution When Using $nin in Write Operations

Before modifying data based on a list of values, inspect and count documents using the exact same filter:

~~~javascript
const filter = {
  status: { $in: ["NEW", "CANCELLED"] }
};

db.orders.find(filter, { _id: 1, status: 1 });
db.orders.countDocuments(filter);

// Execute only in the practice database after verifying the scope:
db.orders.updateMany(
  filter,
  { $set: { needsReview: true } }
);
~~~

After the update command, `matchedCount` and `modifiedCount` may differ if the field already held the target value.

**Dangerous example to recognize:**

~~~javascript
// Do not run on production data
db.orders.deleteMany({
  status: { $nin: ["PAID"] }
});
~~~

This command can match documents missing `status`, holding `null`, or containing an unanticipated new status. For deletions, whitelisting allowed statuses and adding explicit constraints is usually much safer.

Similarly, `$nin: []` can match the entire collection. If an exclusion list is computed dynamically, validate the input before issuing the command.

## 16. Common Pitfalls and Misconceptions

| Misconception | Accurate interpretation |
|---|---|
| `$in` on an array requires the array to equal the list | Only one matching element is needed |
| `$nin` on an array means an element exists outside the set | It requires no element to be in the excluded set |
| `$nin` skips documents missing the field | It can select documents missing the field |
| `$exists: true` filters out null | It still matches fields that exist with value null |
| `$in: []` means no filter is applied | It matches zero documents |
| `$nin: []` matches zero documents | It excludes nothing and can match everything |
| An empty array field is the same as a missing field | They are two different data states |
| `$in` can replace `$all` | `$in` is OR; `$all` requires all values |
| `items.sku` and `items.qty` automatically check the same element | `$elemMatch` is required to bind the same element |
| Number `2` and string `"2"` compare equal | They have different BSON types |
| ObjectId equals a lookalike hex string | BSON ObjectId differs from string |
| `{$regex: ...}` can be placed inside an `$in` array | Query `$in` uses regex literals `/pattern/` |
| Aggregation `$in` behaves identically to query `$in` | Syntax and array handling differ |
| Adding an index guarantees `$nin` is fast | `$nin` usually has low selectivity |
| Adding many values to a list never hurts performance | Large lists increase query cost depending on workload |

## 17. Comprehensive Practice Exercises

### Exercise 1: Status in a Set

Find orders with status `PAID` or `SHIPPED`, returning only `_id` and `status`, sorted ascending.

~~~javascript
db.orders.find(
  { status: { $in: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

Result IDs: **2, 3, 5, 6, 9, 10**.

### Exercise 2: Exclusion with and without $exists

Compare:

~~~javascript
db.orders.find({
  status: { $nin: ["PAID", "SHIPPED"] }
});

db.orders.find({
  status: {
    $exists: true,
    $nin: ["PAID", "SHIPPED"]
  }
});
~~~

First result: **1, 4, 7, 8**; second: **1, 4, 7**. ID 8 lacks `status`, so it is excluded when `$exists: true` is added. ID 7 has `status: null`, so it still satisfies the existence check.

### Exercise 3: Tags in an Array

Queries:

~~~javascript
db.orders.find({ tags: { $in: ["sale", "vip"] } });
db.orders.find({ tags: { $nin: ["sale", "vip"] } });
db.orders.find({ tags: { $all: ["sale", "vip"] } });
~~~

Corresponding result IDs:

- `$in`: **1, 3, 6, 7, 9**.
- `$nin`: **2, 4, 5, 8, 10**.
- `$all`: **3**.

Explain why ID 4 with an empty array and ID 5 missing the field both match `$nin`.

### Exercise 4: Empty Sets

~~~javascript
db.orders.countDocuments({ status: { $in: [] } });
db.orders.countDocuments({ status: { $nin: [] } });
~~~

On the 10-document collection, the results are **0** and **10**. If the application wants an empty list to mean "no filter", it must handle that in the API layer rather than sending `$in: []`.

### Exercise 5: Finding Null and Missing

~~~javascript
db.orders.find({ status: { $exists: false } });
db.orders.find({ status: { $type: "null" } });
db.orders.find({ status: { $ne: null } });
~~~

The first two queries select ID **8** and ID **7**, respectively. The final query selects documents whose `status` value is non-null, excluding IDs 7 and 8.

### Exercise 6: Combining with Nested Fields

~~~javascript
db.orders.find({
  "customer.tier": { $in: ["gold", "silver"] },
  status: "PAID"
});
~~~

Result IDs: **2, 5, 6, 9**.

### Exercise 7: Elements of an Array of Objects

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $in: ["A", "B"] },
      qty: { $gte: 3 }
    }
  }
});
~~~

Result IDs: **1, 2, 6, 10**. Create ID 11 from Section 9 and explain why a filter using two independent paths can produce a different result.

### Exercise 8: Inspecting Indexes

~~~javascript
db.orders.createIndex({ status: 1 });

db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] }
}).explain("executionStats");

db.orders.find({
  status: { $nin: ["PAID", "SHIPPED"] }
}).explain("executionStats");
~~~

Record `nReturned`, `totalDocsExamined`, and `IXSCAN` or `COLLSCAN`. Explain why a 10-document dataset is insufficient to conclude that an index will be effective in production.

### Exercise 9: Choosing Query Patterns from Requirements

| Requirement | Choice |
|---|---|
| One of three allowed statuses | `$in` |
| Does not contain sale/vip tags | `$nin` |
| Contains both sale and vip | `$all` |
| One element has SKU in set and qty ≥ 3 | `$elemMatch` combined with `$in` |
| Not an excluded status, and field must exist | `$nin` with `$exists: true` |
| Field must be a string and not an excluded status | `$type: "string"` with `$nin` |
| Empty input list means skip filter | Handle before sending query |
| Find every document with an explicit null field | `$type: "null"` |

## 18. Principles for Project Use

Before writing `$in` or `$nin`, determine **whether the field is a scalar or an array**, **whether it can be missing or null**, and **whether the input list can be empty or mistyped**. If the field is an array, distinguish "has at least one", "has none", "has all", and "a single element satisfies multiple conditions". These map to `$in`, `$nin`, `$all`, and `$elemMatch`, and they are not interchangeable.

In business queries with well-defined valid statuses, prefer expressing the allowed list with `$in`; use `$nin` when you genuinely want to exclude a set and understand how missing fields behave. As data grows, evaluate performance using `explain` and realistic workloads, especially for low-selectivity `$nin` filters.

## References

- [MongoDB Manual: $in query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/in/)
- [MongoDB Manual: $nin query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/nin/)
- [MongoDB Manual: $exists](https://www.mongodb.com/docs/manual/reference/operator/query/exists/)
- [MongoDB Manual: $in aggregation expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/in/)
- [MongoDB Manual: $regex query](https://www.mongodb.com/docs/manual/reference/operator/query/regex/)
