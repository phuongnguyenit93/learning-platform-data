# Querying Nested Fields with Dot Notation and Exact Embedded Document Matching in MongoDB

MongoDB stores data as **BSON documents**, where a field can hold primitive values such as strings, numbers, or booleans, or contain **embedded documents** and **arrays**. For example, a customer can have `profile.address.city` nested inside a `profile` object; orders can live inside an `orders` array, with each element having its own fields.

When querying nested documents, two approaches are frequently confused:

1. **Dot notation**: accessing a nested field inside a document by path, such as `"profile.address.city": "Hà Nội"`.
2. **Whole embedded document comparison**: matching an entire object value, such as `"profile.address": { city: "Hà Nội", district: "Ba Đình", zip: "100000" }`.

These two approaches can produce **different results**. Dot notation checks only the specified field, whereas equality against an entire embedded document requires both the field values/structure and **field order** to match exactly. This lesson explains how to read, write, and choose between these two query styles in the **Query Documents** chapter of MongoDB.

## 1. Understanding Document Structure and Field Paths

An example document:

```javascript
{
  _id: "c101",
  name: "An",
  verified: true,
  profile: {
    address: {
      city: "Hà Nội",
      district: "Ba Đình",
      zip: "100000"
    },
    contact: {
      email: "an@example.test"
    }
  },
  orders: [
    { code: "A", status: "pending", total: 100 },
    { code: "B", status: "paid", total: 300 }
  ]
}
```

Hierarchical structure of the document:

```text
Customer (_id = "c101")
├── name: "An"
├── verified: true
├── profile                             object
│   ├── address                         object
│   │   ├── city: "Hà Nội"
│   │   ├── district: "Ba Đình"
│   │   └── zip: "100000"
│   └── contact                         object
│       └── email: "an@example.test"
└── orders                              array
    ├── [0] {code: "A", status: "pending", total: 100}
    └── [1] {code: "B", status: "paid", total: 300}
```

Here:

| Component | Value type | Dot-notation access |
| --- | --- | --- |
| `name` | Top-level string | `"name"` |
| `profile` | Embedded document | `"profile"` |
| `profile.address` | Embedded document inside `profile` | `"profile.address"` |
| `profile.address.city` | String nested two object levels deep | `"profile.address.city"` |
| `profile.contact.email` | String inside another object | `"profile.contact.email"` |
| `orders` | Array of objects | `"orders"` |
| `orders.code` | `code` values inside array elements | `"orders.code"` |
| `orders.0.code` | `code` of the element at index 0 | `"orders.0.code"` |

**Dot notation** is a path expression with levels separated by dots. In a query filter targeting a nested field, wrap the path in quotes:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
})
```

If you write `profile.address.city` as an unquoted JavaScript expression in the object key position, `mongosh` will not treat it as the intended field name. Use the string `"profile.address.city"` to represent the path accurately.

## 2. Creating a Practice Dataset Covering Edge Cases

Connect to MongoDB via `mongosh` and switch to a dedicated database for this lesson:

```javascript
use document_query_lab
```

Run the following **once** on a new or empty `customers` collection:

```javascript
db.customers.insertMany([
  {
    _id: "c101",
    name: "An",
    verified: true,
    profile: {
      address: {
        city: "Hà Nội",
        district: "Ba Đình",
        zip: "100000"
      },
      contact: { email: "an@example.test" }
    },
    orders: [
      {
        code: "A",
        status: "pending",
        total: 100,
        items: [
          { sku: "P-1", qty: 1 },
          { sku: "P-2", qty: 2 }
        ]
      },
      {
        code: "B",
        status: "paid",
        total: 300,
        items: [{ sku: "P-3", qty: 1 }]
      }
    ]
  },
  {
    _id: "c102",
    name: "Bình",
    verified: false,
    profile: {
      address: {
        city: "Hà Nội",
        district: "Ba Đình",
        zip: "100000",
        note: "Cổng số 2"
      }
    },
    orders: [
      { code: "A", status: "shipped", total: 150 },
      { code: "B", status: "paid", total: 250 }
    ]
  },
  {
    _id: "c103",
    name: "Chi",
    verified: true,
    profile: {
      address: {
        district: "Ba Đình",
        city: "Hà Nội",
        zip: "100000"
      }
    },
    orders: [
      { code: "A", status: "paid", total: 180 }
    ]
  },
  {
    _id: "c104",
    name: "Dũng",
    verified: true,
    profile: {
      address: {
        city: "Đà Nẵng",
        district: "Hải Châu",
        zip: "550000"
      }
    },
    orders: [
      { code: "C", status: "pending", total: 90 }
    ]
  },
  {
    _id: "c105",
    name: "Em",
    verified: false,
    profile: { address: null },
    orders: []
  },
  {
    _id: "c106",
    name: "Giang",
    verified: false,
    profile: {},
    orders: []
  }
])
```

We intentionally created three distinct cases:

- `c101`: `address` has the exact three fields in order `city`, `district`, `zip`.
- `c102`: `address` has the same three fields plus an **extra** `note` field.
- `c103`: `address` has the same field names and values as `c101`, but with `district` placed **before** `city`.

Additionally, `c105` stores `address: null` while `c106` **does not have an `address` field**. This helps distinguish path queries, whole-object equality, `null`, and missing fields.

If you re-run `insertMany()` with the same `_id` values, MongoDB will raise a duplicate key error for existing documents. Do not delete production data just to re-run examples; always use a dedicated practice database or collection.

## 3. Querying a Nested Field with Dot Notation

### 3.1. Comparing a Deeply Nested Field Value

Find customers whose address is in Hà Nội:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
})
```

With the initial dataset, this matches documents with `_id` values **`c101`, `c102`, `c103`**. The query inspects only `city`, so it **does not care** whether the `address` object has additional fields or whether `city` appears before or after `district`.

Query by email:

```javascript
db.customers.find({
  "profile.contact.email": "an@example.test"
})
```

This matches `c101` because `profile` contains a `contact` object with that `email` field.

### 3.2. Comparing Multiple Child Fields

Find customers in Hà Nội, district Ba Đình:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội",
  "profile.address.district": "Ba Đình"
})
```

The result is still **`c101`, `c102`, `c103`**. The two key–value pairs in the filter combine as an **AND** condition: both `city` and `district` must match. They do not require the `address` object to have only those two fields.

You can write it explicitly with `$and`:

```javascript
db.customers.find({
  $and: [
    { "profile.address.city": "Hà Nội" },
    { "profile.address.district": "Ba Đình" }
  ]
})
```

Both filter forms are equivalent in this example. `$and` is useful when organizing complex conditions or avoiding repeated keys in a JavaScript object.

### 3.3. Comparison Operators on Nested Fields

Dot notation works with standard query operators:

```javascript
// String matching in a nested field
db.customers.find({
  "profile.address.zip": { $in: ["100000", "550000"] }
})

// Checking that a value is not in a given set
db.customers.find({
  "profile.address.city": { $nin: ["Đà Nẵng", "Huế"] }
})
```

`$nin` also matches documents **missing** the queried field, so the second condition should not be read simply as "city is known and is neither Đà Nẵng nor Huế". If the field must exist, add `$exists: true` and an appropriate type condition:

```javascript
db.customers.find({
  "profile.address.city": {
    $exists: true,
    $nin: ["Đà Nẵng", "Huế"]
  }
})
```

When a field is numeric, use `$gt`, `$gte`, `$lt`, `$lte` with appropriate numeric values. Do not confuse string postal codes like `"100000"` with numbers used for arithmetic; string and numeric comparisons follow different type rules.

## 4. Comparing an Entire Embedded Document with Equality

In addition to querying child fields, MongoDB lets you compare the **complete object value** of a field:

```javascript
db.customers.find({
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
})
```

On the sample dataset, this query matches only **`c101`**.

That is because equality matching on an embedded document requires:

1. **All and exact fields** being compared.
2. **No extra fields** in the embedded document at that location.
3. **Matching values and data types** for every field.
4. **Field order** in the embedded document matching the order given in the query value.

Comparing the three key documents:

| Document | `profile.address` | Result with the whole-document match above |
| --- | --- | --- |
| `c101` | `{city:"Hà Nội", district:"Ba Đình", zip:"100000"}` | Matches |
| `c102` | Same as `c101` plus `note:"Cổng số 2"` | Does not match due to extra field |
| `c103` | `{district:"Ba Đình", city:"Hà Nội", zip:"100000"}` | Does not match due to different field order |

Crucially, **in MongoDB, embedded document field order is significant for equality matches**, even though programmers often think of objects as unordered key–value maps.

### 4.1. Changing Key Order in the Query Value Changes the Result

```javascript
db.customers.find({
  "profile.address": {
    district: "Ba Đình",
    city: "Hà Nội",
    zip: "100000"
  }
})
```

This query value keeps the same three field/value pairs but puts `district` first; on the sample dataset, it matches **`c103`**, not `c101`.

Whole-document equality is useful when **the entire object is a value that must match verbatim**, such as a configuration block or data template with a fixed structure and field order. When looking up records by specific attributes regardless of other fields, dot notation usually expresses the intent better.

### 4.2. `$eq` with an Object Is Still Exact Equality

The following two queries both perform whole-object comparison:

```javascript
db.customers.find({
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
})

db.customers.find({
  "profile.address": {
    $eq: {
      city: "Hà Nội",
      district: "Ba Đình",
      zip: "100000"
    }
  }
})
```

`$eq` makes explicit that this is a value comparison. It does not turn embedded-document equality into a field-order-independent comparison.

### 4.3. Equality with an Object Containing Other Objects

Suppose you want to match the entire `profile` object; you must supply all fields inside `profile`, including both `address` and `contact` if present:

```javascript
db.customers.find({
  profile: {
    address: {
      city: "Hà Nội",
      district: "Ba Đình",
      zip: "100000"
    },
    contact: { email: "an@example.test" }
  }
})
```

This query matches `c101` in the sample dataset. If the `profile` object gains an additional field such as `preferences`, whole-`profile` equality will stop matching even though address and contact details have not changed.

## 5. Dot Notation vs. Whole-Document Equality: Side-by-Side Comparison

Suppose the goal is "find all customers with city Hà Nội and district Ba Đình, regardless of whether extra delivery notes are stored".

**Intentional query with dot notation:**

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội",
  "profile.address.district": "Ba Đình"
})
```

Result: `c101`, `c102`, `c103`.

**Written with whole-address equality:**

```javascript
db.customers.find({
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
})
```

Result: `c101`.

| Criterion | Field-by-field dot notation | Whole embedded document equality |
| --- | --- | --- |
| Comparison target | Values of one or more child paths | Entire object at a field |
| Other unmentioned fields | Do not prevent a match | Break the match if present in the object |
| Field order in object | Irrelevant for child-field conditions | Significant |
| Adding a new field to object | Existing query usually still matches | May stop matching |
| Best suited when | Filtering by a subset of attributes | Exact object structure must match |
| Example | `"profile.address.city": "Hà Nội"` | `"profile.address": {city:"Hà Nội",district:"Ba Đình",zip:"100000"}` |

Neither is "universally better" in every scenario. Choose the comparison style based on **business requirements**. When requirements describe specific attributes, path queries are generally far more resilient as the schema evolves.

## 6. `null`, Missing Fields, and Empty Objects

In the sample dataset:

```javascript
// c105
{ _id: "c105", profile: { address: null } }

// c106
{ _id: "c106", profile: {} }
```

These two documents differ in data representation:

- `c105` has the `profile.address` field, with BSON `null` as its value.
- `c106` does not have the `profile.address` field.

Equality query with `null`:

```javascript
db.customers.find({
  "profile.address": null
})
```

In MongoDB, an equality filter like this matches both fields whose value is `null` **and** fields that do not exist; therefore, it returns both `c105` and `c106` in the sample set.

To check whether the field exists:

```javascript
db.customers.find({
  "profile.address": { $exists: true }
})
```

`$exists: true` still matches `c105`, because `address` exists even though its value is `null`. By contrast:

```javascript
db.customers.find({
  "profile.address": { $exists: false }
})
```

returns `c106` (assuming no other documents lack that path).

To match only an explicit BSON `null` value:

```javascript
db.customers.find({
  "profile.address": { $type: "null" }
})
```

To select only documents where `address` is of type object:

```javascript
db.customers.find({
  "profile.address": { $type: "object" }
})
```

This example matches `c101`, `c102`, `c103`, `c104`. If you need documents where `city` is specifically a string, check the exact path:

```javascript
db.customers.find({
  "profile.address.city": { $type: "string" }
})
```

Deeply nested queries such as `"profile.address.city": null` also require care: they match when the `city` path does not exist at all. Combine `$exists` or `$type` when you need to distinguish "no address", "empty address", and "city explicitly set to null".

## 7. Dot Notation Traversing Arrays of Objects

Document `c101` has `orders` as an array:

```javascript
{
  orders: [
    {
      code: "A",
      status: "pending",
      total: 100,
      items: [
        { sku: "P-1", qty: 1 },
        { sku: "P-2", qty: 2 }
      ]
    },
    {
      code: "B",
      status: "paid",
      total: 300,
      items: [{ sku: "P-3", qty: 1 }]
    }
  ]
}
```

MongoDB can use dot notation to query fields inside array elements:

```javascript
db.customers.find({
  "orders.code": "A"
})
```

This condition matches a document if **at least one element** in the `orders` array has `code: "A"`. On the sample dataset, the result includes `c101`, `c102`, `c103`.

Querying a field of the first element:

```javascript
db.customers.find({
  "orders.0.code": "A"
})
```

`0` refers to the first element in the array. This is a **positional** condition, which is unsuitable if element order can change and business logic only cares about `code`. In production systems, prefer matching elements by identifier or semantics rather than hardcoding array indices.

Querying across two levels of arrays/objects:

```javascript
db.customers.find({
  "orders.items.sku": "P-2"
})
```

The query engine traverses the elements of `orders`, then the `items` elements inside them, to find a matching `sku`. In the sample dataset, `c101` contains item `P-2`.

## 8. Multiple Conditions on an Array: When Is `$elemMatch` Needed?

This is a key scenario when contrasting dot notation with nested object structures.

Suppose the business requirement is: "Find customers who have an order with code `A` **that is paid**."

If you write:

```javascript
db.customers.find({
  "orders.code": "A",
  "orders.status": "paid"
})
```

MongoDB can satisfy `"orders.code": "A"` with **one element** and `"orders.status": "paid"` with **another element**. On the sample dataset:

- `c101`: order `A` is `pending`, while order `B` is `paid` → **still matches** the query above.
- `c102`: order `A` is `shipped`, while order `B` is `paid` → **still matches**.
- `c103`: order `A` is `paid` → matches.

The result of the separate dot-notation filter is: `c101`, `c102`, `c103`. Yet only **`c103`** satisfies "the same order A is paid".

Use `$elemMatch` to force all conditions to hold on **the same object element**:

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      status: "paid"
    }
  }
})
```

This time the result contains only `c103`.

### 8.1. Single Condition vs. Multiple Conditions on an Array

| Requirement | Recommended filter |
| --- | --- |
| Any order with code A | `{ "orders.code": "A" }` |
| Any order with status paid | `{ "orders.status": "paid" }` |
| Has an order with code A and a paid order (possibly two different orders) | `{ "orders.code": "A", "orders.status": "paid" }` |
| Has **the same order** with code A and status paid | `{ orders: { $elemMatch: { code: "A", status: "paid" } } }` |

Dot notation is **not wrong** here; it simply expresses a different condition. Mistakes happen when it is assumed to enforce that multiple conditions hold simultaneously on the same array element.

### 8.2. Nested `$elemMatch` for Arrays Within Arrays

Suppose you need customers who have **an order with code `A`** containing **an item with SKU `P-2` and quantity 2 or more**:

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      items: {
        $elemMatch: {
          sku: "P-2",
          qty: { $gte: 2 }
        }
      }
    }
  }
})
```

Meaning of the two `$elemMatch` layers:

1. Outer layer: `code` and the `items` condition must apply to **the same order**.
2. Inner layer: `sku` and `qty` must apply to **the same item** inside that order.

In the sample dataset, this query matches `c101`. If you simply wrote `"orders.code": "A"`, `"orders.items.sku": "P-2"`, and `"orders.items.qty": { $gte: 2 }`, each condition could be satisfied by different elements, yielding results that violate the business requirement.

## 9. Distinguishing Equality on Array Elements, Whole Arrays, and Embedded Objects

Suppose a document is:

```javascript
{
  favoriteColors: ["red", "blue"],
  address: {
    city: "Hà Nội",
    zip: "100000"
  }
}
```

Checking whether `"blue"` is in the array:

```javascript
db.preferences.find({
  favoriteColors: "blue"
})
```

This is equality against an **array element value**, so the array only needs to contain `"blue"`.

Checking whether **the entire array** has the exact two elements in order:

```javascript
db.preferences.find({
  favoriteColors: ["red", "blue"]
})
```

This query matches the exact array `["red", "blue"]`, which differs from `["blue", "red"]` or `["red", "blue", "green"]`.

Checking **the entire embedded document `address`**:

```javascript
db.preferences.find({
  address: {
    city: "Hà Nội",
    zip: "100000"
  }
})
```

This is whole-object equality, requiring matching fields and order. Both are whole-value comparisons, except arrays enforce element order while embedded documents enforce field order.

In the example above, `preferences` is just an illustrative collection name. To try it interactively, create documents in that collection first.

## 10. Projection: Returning Only Necessary Nested Fields

The filter decides which documents match; **projection** decides which fields are returned.

```javascript
db.customers.find(
  { "profile.address.city": "Hà Nội" },
  {
    _id: 0,
    name: 1,
    "profile.address.city": 1,
    "profile.address.zip": 1
  }
)
```

On the sample dataset, the query returns `name` along with the selected nested fields for `c101`, `c102`, `c103`. The output structure remains a **nested object**:

```javascript
{
  name: "An",
  profile: {
    address: {
      city: "Hà Nội",
      zip: "100000"
    }
  }
}
```

Dot notation in a projection does not flatten the path into a top-level field literally named `"profile.address.city"`. MongoDB reconstructs the required nested document hierarchy.

For arrays of objects, selecting a child field in projection returns that field across all array elements. If you only want **the first matching array element**, check `$elemMatch` projection for that specific case; if you need structural reshaping or deep filtering of multiple elements, an aggregation pipeline with `$project` and `$filter` is usually clearer.

## 11. Dot Notation in Updates: Same Syntax, Different Purpose

Although this lesson focuses on queries, dot notation also appears when **updating nested fields**. This is easily confused with replacing an entire object.

Updating only `city` inside `profile.address`:

```javascript
db.customers.updateOne(
  { _id: "c101" },
  { $set: { "profile.address.city": "Hải Phòng" } }
)
```

This update preserves `district` and `zip`.

By contrast:

```javascript
db.customers.updateOne(
  { _id: "c101" },
  {
    $set: {
      "profile.address": { city: "Hải Phòng" }
    }
  }
)
```

This command **replaces the entire** `profile.address` value with an object containing only `city`. The previous `district` and `zip` fields are lost. In practice exercises, running these update commands **mutates the sample dataset**, so if you want to test the exercise answers below against the original state, run queries on the initial dataset or recreate a separate dataset.

Similarly, to update a specific order conditionally, use positional operators or `arrayFilters` rather than guessing fixed array indices:

```javascript
db.customers.updateOne(
  { _id: "c101" },
  { $set: { "orders.$[order].status": "paid" } },
  {
    arrayFilters: [
      { "order.code": "A" }
    ]
  }
)
```

`$[order]` applies the change to elements in `orders` matching the filter, avoiding any dependency on whether order `A` sits at index 0 or elsewhere.

## 12. Indexes for Nested Field Queries

MongoDB supports creating **indexes on nested field paths**:

```javascript
db.customers.createIndex(
  { "profile.address.city": 1 },
  { name: "address_city_idx" }
)
```

This index can support queries filtering by:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
})
```

If queries frequently filter by both `city` and `district`, consider a compound index:

```javascript
db.customers.createIndex(
  {
    "profile.address.city": 1,
    "profile.address.district": 1
  },
  { name: "address_city_district_idx" }
)
```

Which index MongoDB actually uses depends on data distribution, selectivity, sort, projection, and the query planner. Inspect the query plan with:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
}).explain("executionStats")
```

An index on a **child path** is built for values at that path; do not assume it executes identically to an index on **the entire embedded document**. When the requirement is whole-object equality, inspect the actual query shape and execution plan.

If a path traverses an array, the index becomes a **multikey index**; multikey and compound-multikey index rules must be evaluated separately. Indexes speed up matching queries, but they cannot fix a semantically wrong filter—for instance, if conditions must apply to the same array element, you still need `$elemMatch`.

## 13. Writing Equivalent Queries with the MongoDB Java Sync Driver

When a Java application accesses MongoDB, the MongoDB Java Sync Driver lets you build filters with helpers such as `Filters.eq()` and `Filters.elemMatch()`. Dot-notation paths remain identical.

Example:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.List;

public class NestedDocumentQueryDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("document_query_lab");
            MongoCollection<Document> customers =
                database.getCollection("customers");

            // 1. Compare a child field value
            System.out.println("Customers in Hà Nội:");
            customers.find(Filters.eq("profile.address.city", "Hà Nội"))
                .forEach(doc -> System.out.println(doc.getString("_id")));

            // 2. Compare an entire embedded document
            Document address = new Document("city", "Hà Nội")
                .append("district", "Ba Đình")
                .append("zip", "100000");

            System.out.println("Exact address match:");
            customers.find(Filters.eq("profile.address", address))
                .forEach(doc -> System.out.println(doc.getString("_id")));

            // 3. Same element in the orders array
            System.out.println("Paid Order A:");
            customers.find(
                Filters.elemMatch(
                    "orders",
                    Filters.and(
                        Filters.eq("code", "A"),
                        Filters.eq("status", "paid")
                    )
                )
            ).forEach(doc -> System.out.println(doc.getString("_id")));
        }
    }
}
```

Ensure an appropriate `mongodb-driver-sync` dependency is configured for your Java environment. The example assumes the sample dataset exists and the `MONGODB_URI` environment variable contains a valid connection string.

On **unmodified** data, the outputs for each section are:

- Dot-notation query on `city`: `c101`, `c102`, `c103`.
- Whole-`address` equality: only `c101`, because the Java `Document` is constructed in order `city` → `district` → `zip`.
- `elemMatch` for order `A` and `paid`: only `c103`.

The program does not enforce print order if the query lacks `sort()`. The expected ID sets are accurate in content, though output line order may vary.

### Note on Field Order When Constructing `Document` in Java

Because MongoDB whole-embedded-document equality is sensitive to field order, the two Java objects below are not equivalent for whole-object equality queries:

```java
Document a = new Document("city", "Hà Nội")
    .append("district", "Ba Đình")
    .append("zip", "100000");

Document b = new Document("district", "Ba Đình")
    .append("city", "Hà Nội")
    .append("zip", "100000");
```

If the goal is simply to check `city` and `district` regardless of field order or other fields, use:

```java
Filters.and(
    Filters.eq("profile.address.city", "Hà Nội"),
    Filters.eq("profile.address.district", "Ba Đình")
)
```

This is also far more resilient if the document schema gains new fields later.

## 14. Common Mistakes When Querying Nested Documents

| Situation | Why an error or unexpected result occurs | How to fix |
| --- | --- | --- |
| Matching `profile.address` with an object missing `zip` | Equality requires the entire embedded document to match | Query child fields with dot notation if only specific fields matter |
| Same values with `city` and `district` swapped stop matching | Embedded document equality is field-order sensitive | Use dot notation, or build the object in exact order when whole-object equality is genuinely needed |
| Adding `note` to `address` breaks an existing query | The stored document has an extra field compared to the filter object | Avoid whole-object equality when filtering only by selected attributes |
| `"orders.code":"A"` and `"orders.status":"paid"` match unpaid orders | Two conditions can be satisfied by two different array elements | Use `$elemMatch` to bind conditions to the same element |
| `"profile.address": null` returns documents without `address` | Equality with `null` matches both null values and missing fields | Use `$type: "null"` or `$exists` |
| Filtering by `"orders.0.code"` misses order A at other positions | The filter depends on array index | Use `"orders.code"` or `$elemMatch` as needed |
| `profile.address.city` fails to run as expected in JavaScript | The path was written as an unquoted expression instead of a string key | Quote `"profile.address.city"` in the filter |
| Projected output contains `profile: { address: {...} }` instead of flat keys | MongoDB preserves nested object structure | Access values using the proper nested path on the result |
| After `$set` on the whole `profile.address`, other fields vanish | The update replaces the entire object value | `$set` the specific child field path when updating only part of the object |
| `find()` order differs across runs or machines | No sort was requested | Add `.sort({_id: 1})` when deterministic order is needed |

One additional note: dots in a **query path** act as object-hierarchy separators. Cases where **actual field names contain literal dots** (in MongoDB versions that allow them) require different access mechanisms, such as `$getField` in aggregation expressions. Never assume `"a.b"` automatically queries a top-level field literally named `a.b`.

## 15. Exercises and Reference Solutions

The following exercises assume the `customers` collection still holds the exact dataset from Section 2.

### Exercise 1. Find Customers by a Deeply Nested Attribute

Requirement: find customers whose `profile.address.district` equals `"Ba Đình"`; return only `name` and `profile.address.city`.

**Reference solution:**

```javascript
db.customers.find(
  { "profile.address.district": "Ba Đình" },
  {
    _id: 0,
    name: 1,
    "profile.address.city": 1
  }
)
```

The matching document set consists of `c101`, `c102`, `c103`.

### Exercise 2. Analyze Why Two Filters Return Different Results

```javascript
// Filter A
{ "profile.address.city": "Hà Nội" }

// Filter B
{
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
}
```

Question: Why does Filter A match `c102` and `c103`, while Filter B does not?

**Answer:** Filter A compares only the `city` value, ignoring all other fields and field ordering. Filter B requires whole-object equality; `c102` has an extra `note` field, while `c103` places `district` before `city`.

### Exercise 3. Distinguish Null and Missing Fields

Requirement: find customers where `profile.address` **exists and has value null**; then find customers **missing** the `profile.address` field.

**Answer:**

```javascript
// Field exists and holds null
db.customers.find({
  "profile.address": { $type: "null" }
})

// Field does not exist
db.customers.find({
  "profile.address": { $exists: false }
})
```

The first query matches `c105`; the second matches `c106`.

### Exercise 4. Same Order or Two Different Orders?

Requirement: find customers who have **an order `A` that is `paid`**. Write the query and explain why two separate dot paths must not be used.

**Answer:**

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      status: "paid"
    }
  }
})
```

The result is `c103`. Two separate dot-notation conditions `"orders.code": "A"` and `"orders.status": "paid"` can be satisfied by two different orders in the same array.

### Exercise 5. Multi-Level Nested Arrays

Requirement: find customers who have an order with code `A` containing an item with SKU `P-2` and `qty >= 2`.

**Answer:**

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      items: {
        $elemMatch: {
          sku: "P-2",
          qty: { $gte: 2 }
        }
      }
    }
  }
})
```

The result includes `c101` in the sample dataset. The outer `$elemMatch` keeps conditions on the same order; the inner `$elemMatch` keeps both conditions on the same item.

### Exercise 6. Choosing the Query Design from Requirements

A delivery system needs to find all customers with `city: "Hà Nội"` and `zip: "100000"`. Later, the `address` object may add `building`, `floor`, and `deliveryNote`. Should it use dot notation or whole-`address` equality?

**Answer:** Use dot notation because business logic only cares about those two attributes:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội",
  "profile.address.zip": "100000"
})
```

This query will not break simply because `address` gains additional fields.

## 16. Rules to Remember

When reading or writing nested-document queries, ask three questions:

1. **Do I only need to check specific child fields, or an exact whole-object match?** If checking attributes, use dot notation. If the entire embedded document is a value that must match verbatim, use whole-object equality and pay attention to field order.
2. **Does the path traverse an array?** For a single condition, dot notation is usually sufficient. When multiple conditions must apply to the same array element, use `$elemMatch`; for nested arrays, nested `$elemMatch` may be needed.
3. **Can the field be missing, null, or change types?** If so, use `$exists`/`$type` to express intent clearly; do not treat `null` equality as a check for "explicitly null only".

Two expressions that look almost identical can carry very different meanings in MongoDB. Mastering **field paths**, **whole-embedded-document equality**, **field order**, and **array semantics** ensures accurate queries even as document structures grow deeper and more complex.
