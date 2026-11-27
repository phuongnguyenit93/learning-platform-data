# Querying Arrays of Documents and Nested Paths

MongoDB allows a document to contain an **embedded document**, an **array**, and an **array of documents** across multiple levels. As a result, a single order can store its line items directly, and each line item can store attributes, tags, and warehouse allocations. However, query conditions must be expressed with precision: a query can match because **two different elements** in an array satisfy two conditions individually, even when no single element satisfies both.

This lesson belongs to MongoDB's **Array Queries** chapter and focuses on finding and processing **arrays of documents** using **dot notation**, **`$elemMatch`**, paths spanning multiple nested levels, projections, aggregations, along with index limitations and array element updates. Examples run in **`mongosh`** against the practice dataset `array_query_lab.orders`.

After this lesson, you will be able to:

- Write filters on fields of nested documents and elements of arrays of documents.
- Distinguish conditions where **each condition may match a different element** from conditions where **the same element must match all of them**.
- Use `$elemMatch` for arrays of documents, numeric arrays, and multi-level nested arrays.
- Query fields at an array index, missing/null fields, empty arrays, and multiple conditions on arrays.
- Distinguish **filtering parent documents** from **selecting returned array elements** via projection/aggregation.
- Understand the impact of **multikey indexes**, index bounds on arrays, and update conditions using `$`, `$[]`, and `$[identifier]`.
- Avoid common pitfalls such as cross-element false matches, whole-embedded-document comparisons, misusing `$ne`, and unbounded array queries.

> **Syntax scope:** Examples use MongoDB Server's query language in `mongosh`. When translating to the Java Driver, Spring Data MongoDB, or another driver, client API syntax may differ, yet **server-side filter semantics** must be preserved accurately. Version-dependent options should be checked against the Database Manual for your actual server version.

## 1. Distinguishing Three Data Structures

MongoDB can store the following structure types within the same collection:

| Structure | Example | Typical Query Pattern |
|---|---|---|
| **Embedded document** | `customer: { name, address: { city } }` | `"customer.address.city": "Hà Nội"` |
| **Array of scalars** | `tags: ["book", "gift"]` | `tags: "gift"` or `tags: { $all: [...] }` |
| **Array of documents** | `items: [{sku, qty}, {sku, qty}]` | `"items.sku": "BK-01"` or `items: { $elemMatch: {...} }` |
| **Nested arrays inside documents** | `items[].allocations[]` | Combine `$elemMatch` at each boundary requiring the same element. |

Example of multiple nesting levels:

~~~javascript
{
  _id: "O-100",
  customer: {
    id: "C-1",
    location: { city: "Hà Nội", district: "Ba Đình" }
  },
  items: [
    {
      sku: "BK-01",
      qty: 1,
      tags: ["book", "sale"],
      allocations: [
        { warehouse: "HN", qty: 1 }
      ]
    },
    {
      sku: "PN-02",
      qty: 3,
      tags: ["office"],
      allocations: [
        { warehouse: "SG", qty: 3 }
      ]
    }
  ]
}
~~~

Access diagram:

~~~text
Order
├── customer                         (embedded document)
│   └── location                     (embedded document)
│       ├── city
│       └── district
└── items                             (array)
    ├── [0]                          (document)
    │   ├── sku
    │   ├── qty
    │   ├── tags                     (array of strings)
    │   └── allocations              (array of documents)
    │       └── [0].warehouse
    └── [1]                          (document)
        └── allocations              (array of documents)
~~~

**Dot notation** is a path string consisting of dot-separated segments, such as `"customer.location.city"`, `"items.sku"`, or `"items.allocations.warehouse"`. Its behavior differs slightly depending on whether it traverses an **object** or an **array**: through an object it selects a field, while through an array it searches across elements that may contain the corresponding field.

## 2. Reproducible Practice Dataset

Each order contains an `items` array; each item has `sku`, `qty`, `tags`, and an `allocations` array of warehouse allocations. We intentionally create orders where **SKU and high quantity appear on two different items** to distinguish filter outcomes.

Run in a dedicated test database. The `replaceOne` commands below intentionally overwrite four demo documents with fixed `_id` values; do not run against production data.

~~~javascript
const lab = db.getSiblingDB("array_query_lab")
const sampleOrders = [
  {
    _id: "O-100",
    status: "PAID",
    customer: {
      id: "C-1",
      location: { city: "Hà Nội", district: "Ba Đình" }
    },
    items: [
      {
        sku: "BK-01", qty: 1, price: 120000,
        tags: ["book", "sale"],
        attributes: { color: "blue" },
        allocations: [{ warehouse: "HN", qty: 1 }]
      },
      {
        sku: "PN-02", qty: 3, price: 10000,
        tags: ["office"],
        attributes: { color: "red" },
        allocations: [{ warehouse: "SG", qty: 3 }]
      },
      {
        sku: "BK-03", qty: 4, price: 75000,
        tags: ["book", "gift"],
        attributes: { color: "green" },
        allocations: [{ warehouse: "HN", qty: 4 }]
      }
    ],
    shipping: {
      events: [
        { code: "CREATED", at: ISODate("2026-11-01T02:00:00Z") },
        { code: "PICKED", at: ISODate("2026-11-02T03:00:00Z") }
      ]
    },
    createdAt: ISODate("2026-11-01T02:00:00Z")
  },
  {
    _id: "O-200",
    status: "NEW",
    customer: {
      id: "C-2",
      location: { city: "Đà Nẵng", district: "Hải Châu" }
    },
    items: [
      {
        sku: "BK-01", qty: 3, price: 120000,
        tags: ["book"],
        attributes: { color: "blue" },
        allocations: [
          { warehouse: "SG", qty: 1 },
          { warehouse: "HN", qty: 2 }
        ]
      },
      {
        sku: "PN-02", qty: 1, price: 10000,
        tags: ["office"],
        attributes: { color: "red" },
        allocations: [{ warehouse: "HN", qty: 1 }]
      }
    ],
    createdAt: ISODate("2026-11-03T05:00:00Z")
  },
  {
    _id: "O-300",
    status: "PAID",
    customer: {
      id: "C-3",
      location: { city: "Hồ Chí Minh", district: "Quận 1" }
    },
    items: [
      {
        sku: "BK-01", qty: 1, price: 120000,
        tags: ["book"],
        allocations: [{ warehouse: "HN", qty: 1 }]
      },
      {
        sku: "PN-02", qty: 3, price: 10000,
        tags: ["office"],
        allocations: [{ warehouse: "SG", qty: 3 }]
      }
    ],
    createdAt: ISODate("2026-11-04T06:00:00Z")
  },
  {
    _id: "O-400",
    status: "DRAFT",
    customer: {
      id: "C-4",
      location: { city: "Hà Nội", district: "Cầu Giấy" }
    },
    items: [],
    createdAt: ISODate("2026-11-05T07:00:00Z")
  }
]

for (const order of sampleOrders) {
  lab.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  )
}

lab.orders.find({}, { _id: 1, status: 1, "items.sku": 1 })
~~~

This is an illustrative dataset; each `sku` appears at most once per order **in this sample**, though MongoDB does not enforce that rule on its own. If an application permits multiple line items with the same SKU, updates must explicitly choose whether to modify one or all matching elements.

## 3. Querying Embedded Document Fields with Dot Notation

When the path traverses only nested **objects**, use dots to specify the field:

~~~javascript
// Orders whose customer is in Hà Nội.
lab.orders.find(
  { "customer.location.city": "Hà Nội" },
  { _id: 1, "customer.location.city": 1 }
)
// Sample data: O-100, O-400.
~~~

This syntax means: enter `customer`, then `location`, then compare `city`. Because the dot is inside the **filter field name**, you must wrap the path in double or single quotes:

~~~javascript
// Correct:
{ "customer.location.city": "Hà Nội" }

// Invalid JavaScript syntax:
// { customer.location.city: "Hà Nội" }
~~~

### 3.1. Whole Embedded Document Comparison Accounts for Field Order

Example:

~~~javascript
// Only valid if the object is stored with the exact fields,
// values, and matching field order:
lab.orders.find({
  "customer.location": {
    city: "Hà Nội",
    district: "Ba Đình"
  }
})
~~~

With **equality on a whole embedded document**, MongoDB considers both **field order** and document structure. If the object stores `district` before `city`, or has an extra field, whole-object comparison may not match. When you only care about one or a few attributes, **dot notation** is usually clearer:

~~~javascript
lab.orders.find({
  "customer.location.city": "Hà Nội",
  "customer.location.district": "Ba Đình"
})
~~~

Both conditions above traverse the `customer.location` object (not an array), so they describe the same embedded location in the document. The **same-object vs. different-element** distinction becomes crucial when the path traverses an array.

### 3.2. Checking Field Existence and Data Type

~~~javascript
// Has the city field at this path.
lab.orders.find({
  "customer.location.city": { $exists: true }
})

// City must be a string.
lab.orders.find({
  "customer.location.city": { $type: "string" }
})

// City contains 'Hà' (illustrative regex).
lab.orders.find({
  "customer.location.city": { $regex: "Hà" }
})
~~~

`$exists: true` does not require the field to be non-null; it only checks presence. `$type` is useful when a flexible schema has inconsistent data across documents.

## 4. Dot Notation Traversing an Array of Documents

Suppose we want to find orders that have **at least one item carrying SKU `BK-01`**:

~~~javascript
lab.orders.find(
  { "items.sku": "BK-01" },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

Because `items` is an array of documents, the path `"items.sku"` can traverse into **any element** of the array and matches whenever a suitable `sku` is found. It **does not require** the item to be at the first position.

Other comparisons work similarly:

~~~javascript
// Has at least one item with qty >= 3.
lab.orders.find(
  { "items.qty": { $gte: 3 } },
  { _id: 1 }
)
// O-100, O-200, O-300.

// Has at least one blue item.
lab.orders.find(
  { "items.attributes.color": "blue" },
  { _id: 1 }
)
// O-100, O-200.

// At least one item has the 'gift' tag.
lab.orders.find(
  { "items.tags": "gift" },
  { _id: 1 }
)
// O-100.
~~~

### 4.1. Most Common Trap: Conditions Can Match **Different Elements**

Consider the filter:

~~~javascript
lab.orders.find(
  {
    "items.sku": "BK-01",
    "items.qty": { $gte: 3 }
  },
  { _id: 1 }
)
~~~

Result on the sample data: **`O-100`, `O-200`, and `O-300`**.

Why does `O-100` still match even though its `BK-01` item has `qty: 1`?

~~~text
O-100.items
  [0] { sku: "BK-01", qty: 1 }  -> satisfies sku = BK-01
  [1] { sku: "PN-02", qty: 3 }  -> satisfies qty >= 3
  [2] { sku: "BK-03", qty: 4 }  -> also satisfies qty >= 3
~~~

MongoDB interprets the two dot-notation predicates as: **the document contains some item with SKU BK-01** *and* **the document contains some item with quantity at least 3**. It **does not implicitly require both predicates to match on the same item**.

This is not a MongoDB bug; it is the defined query semantics. If business logic requires the **same element**, use `$elemMatch`.

## 5. `$elemMatch`: Forcing Multiple Conditions onto the Same Element

The query operator **`$elemMatch`** selects documents that have **at least one array element** satisfying **all conditions placed inside it**.

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        qty: { $gte: 3 }
      }
    }
  },
  { _id: 1 }
)
// Only O-200.
~~~

Read the query as: “Find orders where **there exists an element `items[i]`** with `sku = BK-01` **and** `qty >= 3`”.

~~~text
O-100: BK-01 qty 1, PN-02 qty 3, BK-03 qty 4 -> NO
O-200: BK-01 qty 3                            -> YES
O-300: BK-01 qty 1, PN-02 qty 3               -> NO
O-400: items = []                             -> NO
~~~

### 5.1. Comparing Dot Notation and `$elemMatch`

| Filter | Interpretation | Sample Result |
|---|---|---|
| `{"items.sku": "BK-01"}` | Has at least one element with SKU BK-01. | O-100, O-200, O-300 |
| `{"items.qty": {$gte: 3}}` | Has at least one element with qty >= 3. | O-100, O-200, O-300 |
| Two separate dot-notation conditions | One element has the matching SKU **and possibly another element** has qty >= 3. | O-100, O-200, O-300 |
| `{items: {$elemMatch: {sku:"BK-01",qty:{$gte:3}}}}` | **The same** item must satisfy both. | **O-200** |
| `{"items.0.sku": "BK-01"}` | The first element has SKU BK-01. | O-100, O-200, O-300 |

Rule of thumb: **whenever two or more predicates describe “the same element of an array”, consider `$elemMatch` right when designing the filter.**

### 5.2. `$elemMatch` on Arrays of Scalars

For a numeric array:

~~~javascript
db.getSiblingDB("array_query_lab").scores.insertOne({
  _id: "S-1",
  points: [72, 95]
})

// Two conditions can match on two different elements:
db.getSiblingDB("array_query_lab").scores.find({
  points: { $gte: 80, $lt: 90 }
})
// S-1 can match: 95 >= 80 and 72 < 90.

// The same element must fall in [80, 90):
db.getSiblingDB("array_query_lab").scores.find({
  points: {
    $elemMatch: { $gte: 80, $lt: 90 }
  }
})
// S-1 does not match because no score is from 80 to under 90.
~~~

This example shows `$elemMatch` is useful not only for subdocuments, but also for **multiple conditions on a single numeric element**. For a **single condition** like `"items.sku": "BK-01"`, `$elemMatch` is not strictly required.

### 5.3. `$elemMatch` and Non-Array Documents

A document where `items` was mistakenly stored as an object:

~~~javascript
{
  _id: "BAD-SHAPE",
  items: { sku: "BK-01", qty: 3 }
}
~~~

A dot-notation filter `{"items.sku":"BK-01"}` can match both an **object** and an **element inside an array**, because it queries by path. By contrast, `{items: {$elemMatch: {sku:"BK-01", qty:{$gte:3}}}}` requires `items` to be an array with a matching element, so it **does not match a single object** like the one above.

When schemas are flexible or legacy data exists, check the **data type** if the application strictly requires an array:

~~~javascript
lab.orders.find({
  items: { $type: "array" }
})
~~~

## 6. `$elemMatch` for Nested Fields Inside an Item

Conditions placed inside `$elemMatch` can continue traversing **embedded documents inside each element**. For example, wanting item `BK-01` in blue:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        "attributes.color": "blue"
      }
    }
  },
  { _id: 1 }
)
// O-100 and O-200.
~~~

Here `attributes` is an object belonging to **one item** being evaluated by `$elemMatch`; dot notation `"attributes.color"` steps from that item into its subobject and cannot jump to another item.

An example adding an order-level status condition outside:

~~~javascript
lab.orders.find(
  {
    status: "PAID",
    items: {
      $elemMatch: {
        sku: "BK-01",
        "attributes.color": "blue"
      }
    }
  },
  { _id: 1 }
)
// O-100.
~~~

`status` belongs to the parent document, so it sits outside `$elemMatch`. If you accidentally put `status` inside, MongoDB will look for a `status` field **inside each item**, not `orders.status`.

## 7. Multi-Level Nested Arrays: Preserving Each Element Boundary

Each item has an `allocations` array containing multiple warehouse allocation documents. Path:

~~~text
orders.items[].allocations[].warehouse
       ^       ^
       |       +-- second array
       +---------- first array
~~~

### 7.1. Dot Notation Across Two Arrays

~~~javascript
lab.orders.find(
  { "items.allocations.warehouse": "SG" },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

Meaning: some **allocation** inside some **item** has `warehouse = "SG"`. If you add `"items.allocations.qty": {$gte:2}` as a separate predicate, `warehouse` and `qty` can still be satisfied by **two different allocations**, or even across **two different items**.

### 7.2. A Single `$elemMatch` at the Items Level Is Not Enough

Look at the first item of `O-200`:

~~~javascript
{
  sku: "BK-01",
  qty: 3,
  allocations: [
    { warehouse: "SG", qty: 1 },
    { warehouse: "HN", qty: 2 }
  ]
}
~~~

The following filter **matches `O-200`**:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        "allocations.warehouse": "SG",
        "allocations.qty": { $gte: 2 }
      }
    }
  },
  { _id: 1 }
)
~~~

Because `$elemMatch` here only guarantees the **same BK-01 item**; inside that item, `allocations.warehouse = SG` matches the first allocation while `allocations.qty >= 2` matches the second allocation.

To require the **same allocation**, use **nested `$elemMatch`**:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        allocations: {
          $elemMatch: {
            warehouse: "SG",
            qty: { $gte: 2 }
          }
        }
      }
    }
  },
  { _id: 1 }
)
// No order in the sample dataset matches.
~~~

Changing warehouse to `HN`:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        allocations: {
          $elemMatch: {
            warehouse: "HN",
            qty: { $gte: 2 }
          }
        }
      }
    }
  },
  { _id: 1 }
)
// O-200.
~~~

Read the condition as:

> There exists an **item** with `sku = "BK-01"`, and inside **that exact item** there exists an **allocation** with `warehouse = "HN"` and `qty >= 2`.

This is the general rule for structures like **`orders[].lines[].allocations[]`**: every array boundary where business logic requires element-level consistency must be represented in the filter.

### 7.3. Multiple Nested Objects but Only One Array

Not every dot requires `$elemMatch`. For instance, `items[].attributes.color` only crosses **one array `items`**, while `attributes` is an ordinary object. When checking the same item:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      "attributes.color": "blue"
    }
  }
}
~~~

No separate `$elemMatch` is needed for `attributes` because it is not an array.

## 8. Useful Operators When Querying Arrays of Documents

### 8.1. `$in`: A Field Matches One of Multiple Values

Find orders with **at least one item** carrying one of the selected SKUs:

~~~javascript
lab.orders.find(
  { "items.sku": { $in: ["BK-01", "BK-03"] } },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

Here `$in` acts as a “SKU belongs to set” condition and **does not require** the order to contain **both** SKUs. To require both SKUs across any items, you can use `$all` on the value path:

~~~javascript
lab.orders.find(
  { "items.sku": { $all: ["BK-01", "BK-03"] } },
  { _id: 1 }
)
// O-100 has both BK-01 and BK-03.
~~~

Distinguish:

- **`$in`**: at least one value matches an element of the requested set.
- **`$all`**: all listed values must appear in the array values at the matching path.
- **`$elemMatch`**: multiple conditions must match **on the same array element**.

When combining complex conditions, choose operators by **business semantics**, not just by the number of conditions.

### 8.2. `$all` on an Array Inside Each Item

Find orders that have an item tagged with **both "book" and "gift"**:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        tags: { $all: ["book", "gift"] }
      }
    }
  },
  { _id: 1 }
)
// O-100: item BK-03 has tags ["book", "gift"].
~~~

Here `$elemMatch` ensures we inspect **a single item**, and `$all` ensures **that exact item's tags array** contains both tags. Writing two predicates on `items.tags` at the order level requires extreme caution, because array conditions could be satisfied across different elements.

If the business rule is “an order has both item SKU A and item SKU B”, the two items **do not have to be the same element**. In that case you can use two `$elemMatch` conditions inside `$all` on the document array:

~~~javascript
lab.orders.find({
  items: {
    $all: [
      { $elemMatch: { sku: "BK-01", qty: { $gte: 1 } } },
      { $elemMatch: { sku: "BK-03", qty: { $gte: 1 } } }
    ]
  }
})
// O-100.
~~~

Each `$elemMatch` describes a requirement for **one item**. The two requirements can be met by **two different items**, matching the “order contains both products” requirement.

### 8.3. `$size` and Empty Arrays

~~~javascript
// Orders with no items yet.
lab.orders.find(
  { items: { $size: 0 } },
  { _id: 1 }
)
// O-400.

// Orders with exactly two items.
lab.orders.find(
  { items: { $size: 2 } },
  { _id: 1 }
)
// O-200, O-300.
~~~

`$size` compares **array length** against a specific integer. Do not write `{items:{$size:{$gte:2}}}` to find arrays with at least two elements; `$size` does not accept a range query like that. For “has at least N elements”, you can check an indexed path:

~~~javascript
// Has a 3rd element (index 2), meaning at least three elements.
lab.orders.find({
  "items.2": { $exists: true }
})
// O-100.
~~~

This is a query trick when the array is properly typed and positionally indexed, not a mechanism for enforcing schema cardinality constraints. `$size` cannot directly use a multikey index to optimize the size check itself; inspect `explain()` if the query runs frequently.

### 8.4. `$exists` on Nested Array Paths

~~~javascript
// Has at least one item with an attributes.color field.
lab.orders.find(
  { "items.attributes.color": { $exists: true } },
  { _id: 1 }
)
// O-100, O-200.

// items exists, even when it is an empty array.
lab.orders.find(
  { items: { $exists: true } },
  { _id: 1 }
)
// In the sample set: all four orders.
~~~

Field **existence** is not synonymous with **having a non-null value**. An empty array is still an existing field. To distinguish:

| Filter | Question Asked |
|---|---|
| `{items: {$exists: false}}` | Missing the `items` field. |
| `{items: {$size: 0}}` | `items` is an array with 0 elements. |
| `{"items.0": {$exists: true}}` | Element at index 0 exists (array has at least one element). |
| `{items: {$type: "array"}}` | `items` has BSON type array. |
| `{"items.price": {$type: "number"}}` | Has a numeric value at the price path inside elements. |

In real schemas with legacy data, you may need to combine `$type` with other conditions to avoid treating a single object as an array.

### 8.5. Null, Missing Fields, and `$ne`

MongoDB has special semantics for `null`. For example:

~~~javascript
lab.orders.find({
  "items.attributes.color": null
})
~~~

An equality condition with `null` can match when the path does not exist **or** has value null; across multi-level arrays, missing fields on elements make misinterpretation even easier. Do not use `= null` as a reliable way to state that **every item has color null**.

If you want “there exists an item whose color is a string”, write it explicitly:

~~~javascript
lab.orders.find({
  "items.attributes.color": { $type: "string" }
})
~~~

Another trap:

~~~javascript
lab.orders.find({
  "items.sku": { $ne: "BK-01" }
})
// In the sample set: O-400 (no BK-01 item).
~~~

`$ne` on an array path here means **no matching BK-01 value exists along the path**, even when the path is absent. It does **not** mean “there is at least one item with a SKU other than BK-01”. An order containing both BK-01 and PN-02 is **not** selected just because PN-02 differs from BK-01.

To ask **whether there exists an item with a SKU other than BK-01**, explicitly use the element-existence operator:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: { sku: { $ne: "BK-01" } }
  }
})
// O-100, O-200, O-300 because they have an item other than BK-01.
~~~

For fields that may be absent, `$ne` inside `$elemMatch` can also match an element missing `sku`. If you want **SKU exists and differs**, add `sku: {$exists:true, $ne:"BK-01"}` in the same predicate. The syntax below illustrates this clearly:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: { $exists: true, $ne: "BK-01" }
    }
  }
})
~~~

If the business rule is “**no item exists** with SKU BK-01”, you can use:

~~~javascript
lab.orders.find({
  items: {
    $not: { $elemMatch: { sku: "BK-01" } }
  }
})
// O-400.
~~~

The negated condition can also match documents **without an `items` field**. If the requirement strictly expects `items` to be an array, add a data-type condition. Negating an existential statement and the existence of a negated element are **two different problems**.

## 9. Querying by Positional Index in an Array

Arrays in MongoDB are ordered. Use **0-based indices** in dot notation:

~~~javascript
// The first element's SKU is BK-01.
lab.orders.find(
  { "items.0.sku": "BK-01" },
  { _id: 1 }
)
// O-100, O-200, O-300.

// The second element has qty >= 3.
lab.orders.find(
  { "items.1.qty": { $gte: 3 } },
  { _id: 1 }
)
// O-100 and O-300.
~~~

Distinguish:

- `"items.sku": "BK-01"` — **any** item.
- `"items.0.sku": "BK-01"` — **only the first item**.
- `items: {$elemMatch:{...}}` — **any single item**, with all inner conditions applying to **that same item**.

Querying by index makes sense when position carries stable business meaning, such as identifying the “first milestone” in an ordered sequence. For shopping carts or line-item lists, however, order can change due to additions, removals, or sorting; hardcoding indices is usually more fragile than querying by **item identifier**.

### 9.1. Element at a Non-Existent Position

If an array has only one element, `"items.1"` does not exist. A query `"items.1.qty": {$exists: true}` does not match. This differs from the case where a second item exists but `qty` is missing. Use `"items.1": {$exists: true}` to ask about the element itself, or `"items.1.qty": {$exists: true}` to ask about the inner field.

### 9.2. Querying by Index Differs from Projection/Update Index Operations

In a filter `"items.0.sku"`, the `0` is part of the **query path**. In an update `"items.$.status"`, the `$` symbol is the **positional update operator** determined by the match. In a projection `"items.$"`, `$` is the **positional projection operator**. Each has its own usage rules and they cannot be swapped arbitrarily.

## 10. Filtering Parent Documents vs. Projecting Array Elements

An important point: the following query selects **orders** with SKU BK-01, yet by default MongoDB returns the **entire `items` array** of each selected order:

~~~javascript
lab.orders.find({
  "items.sku": "BK-01"
})
~~~

The filter checks **whether the document qualifies to be returned**; it does not automatically strip array elements that did not satisfy the filter. To return only relevant fields or elements, use **projection** or **aggregation**.

### 10.1. Field Path Projection

~~~javascript
lab.orders.find(
  { status: "PAID" },
  {
    _id: 1,
    status: 1,
    "items.sku": 1
  }
)
~~~

MongoDB preserves the `items` structure, but displays only `sku` inside each element instead of all of `qty`, `price`, and `tags`. This projection **does not filter out items**; it only restricts which **fields** are returned.

### 10.2. `$elemMatch` in the Projection Position

MongoDB has both **query `$elemMatch`** and **projection `$elemMatch`**. They sit in two different positions in `find(filter, projection)`:

~~~javascript
lab.orders.find(
  { _id: "O-100" },
  {
    _id: 1,
    status: 1,
    items: {
      $elemMatch: {
        sku: "BK-01"
      }
    }
  }
)
~~~

Projection `$elemMatch` returns only the **first element of the array** satisfying the projection condition, wrapped in an array (if a matching element exists). It **does not return all matching elements**. For `O-100`, the returned `items` array contains only item BK-01; the filter `{_id:"O-100"}` still only selects the order.

The condition in the **query** and the condition in the **projection** can also differ. Be careful when using filter and projection conditions with mismatched meanings: a document might be selected because of one element, while the projection returns a different element or omits the field.

### 10.3. Positional Projection `$`

When a filter selects documents via a condition on an array, you can use positional projection to retrieve the first matching element:

~~~javascript
lab.orders.find(
  { "items.sku": "BK-01" },
  {
    _id: 1,
    "items.$": 1
  }
)
~~~

`"items.$": 1` returns the **first element matched by the array condition in the query**. Positional projection has limits on the number of array fields, query shapes, and operator placement; when complex conditions across multiple arrays are needed, prefer **aggregation `$filter`** to explicitly express which elements are returned.

### 10.4. `$slice` in Projection

If you only need the first N elements to limit returned payload size:

~~~javascript
lab.orders.find(
  { _id: "O-100" },
  {
    _id: 1,
    items: { $slice: 2 }
  }
)
// Takes only the first two items; does not select by SKU/qty condition.
~~~

`$slice` in projection extracts a slice of the array by **position**, unlike `$elemMatch` (which filters by condition). Do not use it as a business filter if the requirement is “get the two items with the highest qty”; that case requires appropriate sorting/aggregation.

## 11. Filtering All Elements with Aggregation `$filter`

If you want to return **all items** meeting a condition (rather than just the first element), the aggregation operator **`$filter`** processes the array contents in the returned document.

Example: for every order considered, keep only items with SKU BK-01 and qty >= 3:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      matchingItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: {
            $and: [
              { $eq: ["$$line.sku", "BK-01"] },
              { $gte: ["$$line.qty", 3] }
            ]
          }
        }
      }
    }
  },
  {
    $match: {
      "matchingItems.0": { $exists: true }
    }
  }
])
// O-200 with matchingItems containing item BK-01 qty=3.
~~~

Here:

- **`$match`** is a *pipeline stage* used to select orders.
- **`$project`** is a *pipeline stage* that shapes the output.
- **`$filter`** is an *aggregation expression* that processes the `items` array and keeps elements matching the condition.
- **`$$line`** is the variable representing **one element** of the array being evaluated, defined via `as: "line"`.
- The final `$match` drops orders that have no elements kept by `$filter`.

`$filter` retains **all** matching elements and preserves their relative order in the array. Do not confuse `$filter` with `$elemMatch` projection, which selects only the first element. MongoDB also offers `$map` to transform each element and `$reduce` to fold an array with an accumulator; choose based on the desired output shape.

### 11.1. Returning a Subset of Items While Keeping Some Order Fields

~~~javascript
lab.orders.aggregate([
  { $match: { _id: "O-100" } },
  {
    $project: {
      status: 1,
      createdAt: 1,
      bookItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $in: ["$$item.sku", ["BK-01", "BK-03"]]
          }
        }
      }
    }
  }
])
~~~

The output for `O-100` contains `bookItems` with BK-01 and BK-03, keeping `status` and `createdAt`. This is a **computed query output**, without modifying `items` in the collection.

### 11.2. `$unwind`: Turning Each Element into a Row in the Pipeline

To build a sales quantity report by SKU, use `$unwind`:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQty: { $sum: "$items.qty" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { totalQty: -1 } }
])
~~~

Each PAID order with 3 items becomes 3 pipeline documents after `$unwind`. At that point, `items.sku` and `items.qty` refer to the **exact item unpacked into the current row**. `$group` then sums quantities by SKU.

In this example, `orderCount: {$sum:1}` counts the **number of item rows** after unwind, **not necessarily the number of unique orders** if an order has multiple lines with the same SKU. To count unique orders, design a separate aggregation step (for instance, grouping by order/SKU pair first).

For an empty array like `O-400`, `$unwind: "$items"` by default **produces no output row**. If you need to preserve documents with empty or missing arrays, use the object form with `preserveNullAndEmptyArrays: true` and handle downstream conditions appropriately.

### 11.3. When to Use `find` vs. Aggregation?

| Need | Usually Appropriate Approach |
|---|---|
| Filter orders having an item matching conditions | `find` + `$elemMatch` query. |
| Return all items as in the original document | `find`, with field projection if needed. |
| Return only the first item matching conditions | `$elemMatch` projection / positional projection when appropriate. |
| Return **all items** matching conditions | Aggregation `$filter`. |
| Turn each item into a row for grouping/sorting | Aggregation `$unwind`. |
| Recompute fields based on items | Aggregation `$map`, `$reduce`, `$sum`, or related stages. |

There is no need to build a long pipeline for a simple filter. Conversely, do not try to force an `$elemMatch` projection into filtering **all** elements, because its semantics do not support that.

## 12. From Querying to Updating Array Elements

The `$elemMatch` query operator **only selects documents**. If you want to update one or more specific elements inside an array, the path in the **update document** must use appropriate positional update operators. These are two related yet **distinct** concerns:

~~~text
Filter:
  which documents qualify to run the update?

Update path:
  which array elements inside those documents will be modified?
~~~

### 12.1. Positional Operator `$`: First Matching Element

To mark item BK-01 in order O-100:

~~~javascript
lab.orders.updateOne(
  {
    _id: "O-100",
    "items.sku": "BK-01"
  },
  {
    $set: {
      "items.$.picked": true
    }
  }
)
~~~

`items.$` represents the **first element of the `items` array matched by the filter**. You cannot arbitrarily place `$` in an update path unless the filter identifies an array element properly. This operator has limitations when queries involve multiple array fields or traverse multiple nested arrays; element identification can become ambiguous.

If an order has two items with the same SKU and you want to update **both**, positional `$` will not meet the requirement because it picks only the first matching element; use `$[identifier]`.

### 12.2. Filtered Positional Operator `$[identifier]`: Every Element Matching `arrayFilters`

~~~javascript
lab.orders.updateOne(
  { _id: "O-100" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BK-01" }
    ]
  }
)
~~~

`$[line]` represents **every element of `items`** satisfying the condition on variable `line` in `arrayFilters`. General syntax:

~~~javascript
db.collection.updateOne(
  { /* filter to select parent document */ },
  {
    $set: {
      "arrayField.$[element].someField": someValue
    }
  },
  {
    arrayFilters: [
      { "element.someCondition": expectedValue }
    ]
  }
)
~~~

Names like `element`/`line` are user-chosen identifiers that must obey MongoDB identifier naming rules. `arrayFilters` is an **update option**, not an arbitrary field inside the document. If multiple elements share the SKU, every element matching the filter is updated.

Example incrementing `qty` on BK-01 lines if still under a limit:

~~~javascript
lab.orders.updateOne(
  { _id: "O-200" },
  { $inc: { "items.$[line].qty": 1 } },
  {
    arrayFilters: [
      {
        "line.sku": "BK-01",
        "line.qty": { $lt: 5 }
      }
    ]
  }
)
~~~

The conditions `line.sku` and `line.qty` in the **same arrayFilters entry** describe the same `line` element; that is the same logic as requiring the same element in an `$elemMatch` query. Afterward, any order-level summary/total quantities or amounts are **not updated automatically**; the application must maintain related invariants atomically when required.

### 12.3. All Positional Operator `$[]`: Modifying Every Element

~~~javascript
lab.orders.updateOne(
  { _id: "O-100" },
  {
    $set: {
      "items.$[].inspected": false
    }
  }
)
~~~

`$[]` applies to **every element** of `items` in the selected document. On an empty array, there are no elements to modify. Do not use `$[]` if business logic only intends to update items of one SKU; it can modify far more data than intended.

### 12.4. Two Array Levels in `arrayFilters`

To update the `warehouse = "HN"` allocation of **specifically item BK-01**, use two identifiers:

~~~javascript
lab.orders.updateOne(
  { _id: "O-200" },
  {
    $inc: {
      "items.$[line].allocations.$[allocation].qty": 1
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BK-01" },
      { "allocation.warehouse": "HN" }
    ]
  }
)
~~~

In the sample set, this increments the HN allocation quantity of item BK-01 in order O-200. `line` selects matching items; `allocation` selects matching allocations inside **those selected items**. If multiple HN allocations exist under the same item, all matching elements are updated.

This is a classic case where combining `$[line]` and `$[allocation]` is far clearer than positional `$`, which has restrictions when paths cross multiple arrays.

**Note:** Positional update operations have specific syntax restrictions for **upsert** when the document does not yet exist; for instance, some updates using `$[]`/`$[identifier]` require an exact equality match on the array in the query if the upsert inserts a new document. Do not take an update example for an existing document and assume the exact same structure works for upserts.

### 12.5. `$pull`: Removing Elements by Condition

To remove all lines with SKU PN-02 from an order:

~~~javascript
lab.orders.updateOne(
  { _id: "O-300" },
  {
    $pull: {
      items: { sku: "PN-02" }
    }
  }
)
~~~

`$pull` removes **every element matching** the condition in the array, not just the first one. Once a line item is removed, revisit `total`, inventory, or other business rules; mutating the array alone does not automatically keep derived summary values consistent across every domain.

### 12.6. Watch Out for Atomicity and Update Contention

An update on a **single document** is atomic, even when modifying multiple fields or array elements within that document. However:

- Two clients reading an array and both calling `$set` on the **entire array** with stale copies can cause **lost updates** in application logic.
- Updating an element by positional index can break when indices shift after `$pull`/`$push`; never treat array indices as durable IDs.
- Use a **stable element identifier**, such as `lineId`, if two items can share the same SKU or if ordering changes.
- For rules like “update value only if still at the previous version”, include a **comparison condition** in the filter/arrayFilters when appropriate.
- Writing across multiple independent documents requires transactions or corresponding consistency workflows; single-document atomicity does not span across documents.

## 13. Indexes for Paths in Arrays of Documents

MongoDB supports **multikey indexes** when an indexed field contains an array. If you create an index on `items.sku`, MongoDB maintains index keys corresponding to values from the array elements:

~~~javascript
lab.orders.createIndex({
  "items.sku": 1
})
~~~

This index can assist the query:

~~~javascript
lab.orders.find({
  "items.sku": "BK-01"
})
~~~

Yet **having an index** does not mean every array-related query will be fast; the query planner also evaluates selectivity, numbers of documents/index entries, sorts, projections, and data size.

### 13.1. Compound Multikey Indexes and `$elemMatch`

For queries frequently looking up items by SKU and a quantity threshold:

~~~javascript
lab.orders.createIndex({
  "items.sku": 1,
  "items.qty": 1
})
~~~

Both fields belong to the **same `items` array of subdocuments**, so this is a valid case for a compound multikey index. When multiple predicates on the same array must match the **same item**, `$elemMatch` lets MongoDB understand that relationship and potentially **compound index bounds** accordingly:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
})
~~~

If written as two separate dot-notation conditions:

~~~javascript
lab.orders.find({
  "items.sku": "BK-01",
  "items.qty": { $gte: 3 }
})
~~~

then **the semantics have changed** (two different items can match). Consequently, the engine cannot automatically enforce a “same-element” restriction just because a compound index exists. Beyond correctness, `$elemMatch` can also affect how compound bounds are utilized. Use `explain()` to compare on real data rather than deducing optimization solely from the index definition.

### 13.2. Limitations of Compound Multikey Indexes

MongoDB has restrictions on **parallel arrays**: you cannot arbitrarily create a compound multikey index when multiple indexed fields are **independent arrays** in the same document. For example, two separate array fields can render a compound index invalid depending on the data structure.

This does not preclude `"items.sku"` and `"items.qty"`, which both come from **one array of documents**. Consult the **Compound Multikey Indexes** documentation to see which structures are permitted and how index bounds are combined.

A multikey index on a large array also carries costs: many index entries, extra index updates whenever the array changes, and larger index and working-set footprints. Do not embed unbounded arrays simply because MongoDB provides multikey indexes.

### 13.3. Inspecting Plans with `explain()`

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
}).explain("executionStats")
~~~

Observe fields such as:

| Field / Concept | How to Read |
|---|---|
| `IXSCAN` | Indicates an index scan stage in the execution plan. |
| `COLLSCAN` | Indicates a collection scan stage. |
| `totalKeysExamined` | Number of index entries scanned during the observed run. |
| `totalDocsExamined` | Number of documents examined. |
| `nReturned` | Number of result documents returned. |
| Index bounds | Key value ranges chosen by the planner, evaluated alongside compound index structure. |

`explain` output structure can vary by MongoDB version, execution engine, and plan shape. A query showing `IXSCAN` is not guaranteed to be optimal if it scans too many keys or fetches too many documents. The four-order sample set is too small to judge index efficiency; measure on production-representative data.

### 13.4. A Unique Multikey Index Does Not Mean “No Duplicate SKUs Within One Order”

Suppose you want to guarantee that each SKU appears **only once within the same order**. Do not create a `unique index` on `"items.sku"` and assume it enforces this invariant:

- A unique multikey index checks uniqueness across **different documents** by index key; duplicate elements within the same document have distinct semantics.
- A SKU can legitimately appear across **multiple orders**, so a unique index on `items.sku` alone would even block other orders from containing the same product.
- To prevent duplicate `sku` entries inside each order's array, design an appropriate identity/business constraint, or model line items as separate documents with a compound unique index on `orderId` and `sku` if that fits the domain.

Do not mechanically use an index to replace invariants over **elements within the same array**.

### 13.5. Sort, Projection, and Array Limitations

Sorting documents by an indexed array field follows special rules (MongoDB may evaluate array values according to sort order). Do not think `sort({"items.qty": -1})` means **sorting the elements of `items` inside each order**.

- `sort` at the `find` level orders **documents** in the result set.
- To sort **items inside an order**, use aggregation `$sortArray` on supported versions or process with an appropriate pipeline.
- To filter/sort/extract each item into an independent row, `$unwind` is a clear option.
- If you must process millions of items independently, a reference-based model may fit better than a huge array in one document.

## 14. Writing Accurate Queries in Java Applications

In a Java project, the same MongoDB condition can be built using the MongoDB Java Sync Driver builders. Example equivalent to:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
}
~~~

In Java (with the Java Sync Driver):

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.elemMatch;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;

// Assume collection has been retrieved from MongoDatabase:
MongoCollection<Document> orders = database.getCollection("orders");

var filter = elemMatch(
    "items",
    and(
        eq("sku", "BK-01"),
        gte("qty", 3)
    )
);

orders.find(filter).forEach(System.out::println);
~~~

The key point is that **`elemMatch("items", ...)`** represents the **single-item** boundary. If you write:

~~~java
var filterWithoutElemMatch = and(
    eq("items.sku", "BK-01"),
    gte("items.qty", 3)
);
~~~

then it carries the semantics of **potentially matching different items**, just like a dot-notation filter in `mongosh`. The builder API does not fix business semantics for the application automatically.

With two array levels:

~~~java
var nestedFilter = elemMatch(
    "items",
    and(
        eq("sku", "BK-01"),
        elemMatch(
            "allocations",
            and(
                eq("warehouse", "HN"),
                gte("qty", 2)
            )
        )
    )
);
~~~

Some applications use Spring Data MongoDB:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("items").elemMatch(
        Criteria.where("sku").is("BK-01")
            .and("qty").gte(3)
    )
);
~~~

Here Spring Data constructs a query with **same-item** semantics. However, APIs, overloads, and serialization behavior can vary across Java Driver/Spring Data versions; always verify your project dependencies and corresponding official documentation.

## 15. Translating Business Requirements into Accurate Filters

To avoid false matches across multiple array levels, turn the question into an **explicit “there exists” or “for all” proposition** before writing the query.

### 15.1. An Order Contains **Any Item** with SKU BK-01

~~~text
There exists i in orders.items:
  items[i].sku = BK-01
~~~

Filter:

~~~javascript
{ "items.sku": "BK-01" }
~~~

### 15.2. An Order Contains Item BK-01 with Qty at Least 3

~~~text
There exists i in orders.items:
  items[i].sku = BK-01
  AND items[i].qty >= 3
~~~

Filter:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
}
~~~

### 15.3. An Order Has Item BK-01 and Has Item PN-02

~~~text
There exists i in orders.items: items[i].sku = BK-01
AND there exists j in orders.items: items[j].sku = PN-02
Does not require i = j.
~~~

The filter can use `$all` on SKUs or two `$elemMatch` conditions inside `$and`:

~~~javascript
{
  $and: [
    { items: { $elemMatch: { sku: "BK-01" } } },
    { items: { $elemMatch: { sku: "PN-02" } } }
  ]
}
~~~

This filter differs from writing **one** `$elemMatch` containing two contradictory equality conditions on the same `sku` field. A single-valued `sku` on one item cannot equal both BK-01 and PN-02; a requirement for **two items** must be expressed as two existence checks or an appropriate condition set.

### 15.4. An Item BK-01 Has an HN Allocation with Qty at Least 2

~~~text
There exists i in orders.items:
  items[i].sku = BK-01
  AND there exists j in items[i].allocations:
      allocations[j].warehouse = HN
      AND allocations[j].qty >= 2
~~~

Filter:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      allocations: {
        $elemMatch: {
          warehouse: "HN",
          qty: { $gte: 2 }
        }
      }
    }
  }
}
~~~

### 15.5. No Item Carries SKU BK-01

~~~text
THERE DOES NOT EXIST i in orders.items:
  items[i].sku = BK-01
~~~

Filter:

~~~javascript
{
  items: {
    $not: { $elemMatch: { sku: "BK-01" } }
  }
}
~~~

This condition can also hold for documents **lacking `items`**. If business logic only wants orders that have an `items` field and that field is an array, combine with `$type: "array"`.

### 15.6. All Items Have Qty at Least 1

“Every element meets the condition” is equivalent to “**there does not exist** a violating element”:

~~~javascript
{
  items: {
    $not: {
      $elemMatch: {
        qty: { $lt: 1 }
      }
    }
  }
}
~~~

However, this filter **does not block items missing `qty` or having a wrong `qty` type**, and also matches empty arrays under “no violating element”. If the requirement is “a non-empty array where every item has qty as a positive integer”, combine existence/type checks and preferably configure appropriate **schema validation** on the data. Do not try to use a simple negated query as a full-schema validator when data can be mistyped.

## 16. Common Mistakes

| Error-Prone Syntax / Reasoning | Problem | Intent-Aligned Approach |
|---|---|---|
| Two separate `"items.sku"` and `"items.qty"` conditions intending **same item** | Can match **two different items**. | Use `items: {$elemMatch:{sku:..., qty:...}}`. |
| One `$elemMatch` at item level, with multiple conditions on `allocations` inside | Can match **two different allocations**. | Nest `$elemMatch` inside `allocations`. |
| Filtering by item SKU and expecting only that item in the result | `find` selects the **parent document**; the array stays intact. | Projection `$elemMatch` for first element or aggregation `$filter` for all. |
| Using projection `$elemMatch` and expecting all matching elements | Projection keeps only the **first matching element**. | Use `$filter`. |
| Using `"items.0.sku"` to find a SKU in any item | Checks **only position 0**. | Use `"items.sku"` or `$elemMatch`. |
| Using `$ne` on `items.sku` to find at least one different SKU | `$ne` generally expresses **no excluded value** on the path, including missing fields. | Use `$elemMatch` with `$ne` and `$exists` if needed. |
| Using equality with `null` to detect missing fields | `null` can match missing fields **or** null. | Use `$exists`/`$type` appropriately. |
| Using `$size` with `$gte` | `$size` requires an exact size. | Use an index existence check or an application-maintained count field with strict rules. |
| Comparing an entire embedded document to check one field | Whole-document equality depends on full structure and **field order**. | Use dot notation for the target field. |
| Using `items.$` to update every item with the same SKU | `$` modifies only the first matching element. | Use `$[line]` + `arrayFilters`. |
| Using `items.$[]` when intending to modify only one item | `$[]` applies to every element. | Use `$[line]` or positional `$` with proper conditions. |
| Having a multikey index means every array query is fast | Performance also depends on selectivity, index bounds, and document fetches. | Measure `explain("executionStats")` on representative data. |
| A unique index on `items.sku` ensures no duplicate SKUs per order | Unique multikey enforces uniqueness **across documents** and can block the same SKU in other orders. | Enforce the constraint in aggregation or model line items separately. |
| Keeping all child elements in one array forever | Can become an **unbounded array**, making documents large/hot and hitting 16 MiB. | Split into a separate collection or use bounded subsets/buckets. |

### 16.1. Practice Reading Logic Before Running a Query

Before submitting a filter for code review, answer three questions:

1. **Does the condition apply to the parent document or an array element?** For example, `status` belongs to the order, `qty` belongs to an item.
2. **If there are multiple conditions, must they hold on the same element?** If yes, place `$elemMatch` at the exact array boundary.
3. **Does the result need the whole document, one element, or all matching elements?** Distinguish query filters, projections, and aggregations.

Stating a query's meaning aloud in plain words makes logic reviews much easier than staring at a chain of MongoDB operators.

### 16.2. Boundary Between Schema Choices and Query Choices

An array of embedded documents usually makes sense when the number of elements is **bounded** and they are typically read/updated together with the parent document. For unbounded arrays like millions of comments or event logs, even syntactically correct `$elemMatch` queries will not solve the underlying data-modeling problem.

If you frequently need to filter, sort, and paginate individual elements independently over a massive dataset, consider splitting elements into **separate documents** with a reference key `orderId`/`parentId`. Then queries on items become independent collection queries with clearer indexing, sorting, and pagination. This decision is driven by **access patterns and cardinality**, not by a limitation specific to `$elemMatch`.

## 17. Hands-On Exercises

Use the `array_query_lab.orders` dataset from Section 2. Before update exercises, you can re-run the `replaceOne` loop from Section 2 to restore the demo data to its initial state.

### Exercise 1 — Find Orders with BK-01

Write a filter that retrieves orders with **at least one item** having `sku = "BK-01"`. Predict the returned `_id` values.

**Answer:**

~~~javascript
lab.orders.find(
  { "items.sku": "BK-01" },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

### Exercise 2 — Do Two Predicates Match the Same Item?

Compare two queries:

~~~javascript
// A:
lab.orders.find({
  "items.sku": "BK-01",
  "items.qty": { $gte: 3 }
})

// B:
lab.orders.find({
  items: {
    $elemMatch: { sku: "BK-01", qty: { $gte: 3 } }
  }
})
~~~

**Answer:** A selects **O-100, O-200, O-300** because each predicate can match a different element. B selects only **O-200** because the same BK-01 item has qty 3.

### Exercise 3 — Querying Nested Arrays Properly

Find orders that have item BK-01 and **inside that item** an allocation with `warehouse = "HN"` and `qty >= 2`.

**Answer:**

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: "BK-01",
      allocations: {
        $elemMatch: {
          warehouse: "HN",
          qty: { $gte: 2 }
        }
      }
    }
  }
})
// O-200.
~~~

### Exercise 4 — Querying by Position

Find orders whose second element (`index 1`) has qty at least 3.

**Answer:**

~~~javascript
lab.orders.find(
  { "items.1.qty": { $gte: 3 } },
  { _id: 1 }
)
// O-100 and O-300.
~~~

### Exercise 5 — Finding Orders with No Items

Select only documents where `items` **is an empty array**, excluding documents missing `items` or having `items: null`.

**Answer:**

~~~javascript
lab.orders.find(
  { items: { $size: 0 } },
  { _id: 1 }
)
// O-400.
~~~

### Exercise 6 — Having Both Different SKUs

Find orders containing **BK-01 and PN-02**, without requiring them to be the same element.

**Suggested answer:**

~~~javascript
lab.orders.find({
  "items.sku": { $all: ["BK-01", "PN-02"] }
})
// O-100, O-200, O-300.
~~~

### Exercise 7 — Projecting One Item

Select only order O-100, returning `status` and the **first item** with SKU BK-03 instead of all items.

**Answer:**

~~~javascript
lab.orders.find(
  { _id: "O-100" },
  {
    status: 1,
    items: { $elemMatch: { sku: "BK-03" } }
  }
)
~~~

### Exercise 8 — Filtering Multiple Items with Aggregation

For O-100, return a new field `bookItems` containing only items whose SKU is in `["BK-01", "BK-03"]`.

**Answer:**

~~~javascript
lab.orders.aggregate([
  { $match: { _id: "O-100" } },
  {
    $project: {
      bookItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $in: ["$$item.sku", ["BK-01", "BK-03"]]
          }
        }
      }
    }
  }
])
~~~

`bookItems` contains the two items BK-01 and BK-03. This is a transient aggregation output and **does not modify the stored document**.

### Exercise 9 — Updating an Item with `arrayFilters`

For O-100, mark `picked: true` on every item with SKU BK-01.

**Answer:**

~~~javascript
lab.orders.updateOne(
  { _id: "O-100" },
  { $set: { "items.$[line].picked": true } },
  { arrayFilters: [{ "line.sku": "BK-01" }] }
)
~~~

### Exercise 10 — Updating an Allocation at Two Array Levels

For O-200, increment `qty` by one on the HN warehouse allocation inside item BK-01.

**Answer:**

~~~javascript
lab.orders.updateOne(
  { _id: "O-200" },
  {
    $inc: {
      "items.$[line].allocations.$[alloc].qty": 1
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BK-01" },
      { "alloc.warehouse": "HN" }
    ]
  }
)
~~~

### Exercise 11 — Does Negation Mean Another Element Exists?

Suppose an order contains `items: [{sku:"BK-01"},{sku:"PN-02"}]`. Does the filter `{"items.sku":{$ne:"BK-01"}}` select this order just because PN-02 differs from BK-01?

**Answer:** **No.** That filter expresses that no matching BK-01 value exists along the path. To ask for “there exists an item other than BK-01”, use `items: {$elemMatch:{sku:{$ne:"BK-01"}}}`, and add `$exists` if you do not want to match items missing SKU.

### Exercise 12 — Choosing a Data Model

An article can have millions of comments, and each comment needs to be queried by author, sorted by timestamp, and paginated. Should you embed all of them in a single array on the article so you can use `$elemMatch`?

**Suggested answer:** You should avoid an **unbounded array** inside the parent document. It is usually better to put comments in a separate collection with `articleId`, `authorId`, `createdAt`, and indexes tailored to access patterns. You can embed a **small bounded subset** for quick display if needed.

## 18. Official MongoDB Documentation

When looking up references, always pick the **MongoDB Database Manual matching your server version**, because certain method syntaxes, index/aggregation stages, and execution limits can change. `/docs/manual/` links generally point to the current release; for example, pinning version 8.0 uses `/docs/v8.0/`.

- [Query an Array of Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/) — dot notation and `$elemMatch` on arrays of documents.
- [Query Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-embedded-documents/) — nested object paths and embedded document equality.
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/) — equality, `$all`, conditions on arrays and elements.
- [`$elemMatch` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — same-element rules in filters.
- [`$all` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/all/) — multiple values/conditions on arrays.
- [`$size` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/size/) — array size conditions.
- [`$exists` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — whether a field exists.
- [`$ne` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/ne/) — inequality semantics with arrays and missing fields.
- [`$elemMatch` Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/elemMatch/) — returning the first matching element.
- [Positional `$` Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/positional/) — selecting the first array element matching the query condition.
- [`$slice` Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/slice/) — extracting a slice of an array.
- [Aggregation `$filter`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — filtering elements inside an array to produce output.
- [Aggregation `$unwind`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — emitting each array element as a pipeline document.
- [Filtered Positional Update `$[identifier]`](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/) — `arrayFilters` when updating elements.
- [Positional Update `$`](https://www.mongodb.com/docs/manual/reference/operator/update/positional/) and [All Positional Update `$[]`](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/) — updating the first matching element or all elements.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — indexing arrays, compound bounds, and index limitations.
- [MongoDB 8.0 — Query an Array of Documents](https://www.mongodb.com/docs/v8.0/tutorial/query-array-of-documents/) — example of a version-pinned documentation path.
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/) — builders like `Filters.elemMatch`; pick the version matching your project's driver.

When writing queries on arrays of documents, the deciding question is: **do these conditions need to hold on the same element?** If yes, place `$elemMatch` at the exact array boundary; if the path crosses multiple arrays, nested `$elemMatch` may be required. Only then decide whether to **return the whole document, a single element, or all matching elements**, and choose the corresponding filter, projection, or aggregation. That clear formulation prevents subtle false matches on real data.
