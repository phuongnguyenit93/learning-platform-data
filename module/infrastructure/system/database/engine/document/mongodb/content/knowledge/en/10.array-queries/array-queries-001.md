# Whole-Array Matching and Element-Level Matching in MongoDB

## 1. Why Are Array Queries Prone to Confusion?

A MongoDB document can contain an *array* field with simple elements such as strings, numbers, or nested documents. Arrays are useful for representing product tag lists, test scores across multiple attempts, line items of an order, or additional attributes of an entity.

However, a query asking to “find documents with a matching array” has at least three different meanings:

1. **The entire array equals a given list:** exact number of elements, exact values, and exact order.
2. **The array contains one or more specific values:** additional elements may exist, and order does not matter.
3. **A single element satisfies multiple conditions simultaneously:** the conditions must apply to the **same element**, rather than combining results from two different elements.

MongoDB provides different syntax forms to express each meaning. Choosing the wrong operator not only makes a query slow, but can also return data that is **business-logically incorrect**.

For example, a product has:

~~~javascript
{
  _id: "P100",
  tags: ["sale", "laptop"],
  scores: [72, 91],
  variants: [
    { color: "black", stock: 0 },
    { color: "white", stock: 8 }
  ]
}
~~~

The following requirements are distinct:

- “The tags are **exactly** `["sale", "laptop"]`.”
- “Has the tag `"sale"`.”
- “Has **both** `"sale"` and `"laptop"` tags, regardless of order.”
- “Has at least one score in the range 80–90.”
- “Has a variant that is **black and in stock**.”

For the last requirement, the example document **does not qualify**: the black variant is out of stock, while only the white variant is in stock. A query that merely checks “has color=black” and “has stock>0” across two different elements will produce the wrong result. This is why understanding `$elemMatch` is essential.

### Quick Reference Table

| Query Intent | Typical Syntax | Meaning |
| --- | --- | --- |
| Array is exactly `["red", "blue"]`, in order | `{ tags: ["red", "blue"] }` | Matches the whole array in the case of a flat array. |
| Contains element `"red"` | `{ tags: "red" }` | Array element equals the given value; can also match a scalar field. |
| Contains an element in a set of values | `{ tags: { $in: ["red", "blue"] } }` | **OR** logic across values. |
| Array contains both values | `{ tags: { $all: ["red", "blue"] } }` | **AND** logic for the presence of values. |
| Array has exactly two elements | `{ tags: { $size: 2 } }` | Checks element count, not content. |
| One element satisfies multiple conditions simultaneously | `{ scores: { $elemMatch: { $gte: 80, $lt: 90 } } }` | Conditions apply to the same element. |
| One object in the array has `sku=A` and `qty>=2` | `{ items: { $elemMatch: { sku: "A", qty: { $gte: 2 } } } }` | Fields must belong to the same subdocument. |

The examples below use `mongosh`, a dedicated collection name, and a fixed dataset to distinguish cases that look very similar syntactically.

---

## 2. Preparing Sample Data

Assume the `arrayQueryLesson` collection is **empty** before running the examples. Each document describes an item with tags, trial evaluation scores, and inventory lines:

~~~javascript
db.arrayQueryLesson.insertMany([
  {
    _id: 1,
    name: "A",
    tags: ["red", "blue"],
    scores: [65, 85, 94],
    items: [
      { sku: "A", qty: 1 },
      { sku: "B", qty: 3 }
    ]
  },
  {
    _id: 2,
    name: "B",
    tags: ["blue", "red"],
    scores: [75, 92],
    items: [
      { sku: "A", qty: 3 }
    ]
  },
  {
    _id: 3,
    name: "C",
    tags: ["red", "blue", "green"],
    scores: [82],
    items: [
      { sku: "B", qty: 1 }
    ]
  },
  {
    _id: 4,
    name: "D",
    tags: ["red"],
    scores: [88, 90],
    items: []
  },
  {
    _id: 5,
    name: "E",
    tags: [],
    scores: [],
    items: []
  },
  {
    _id: 6,
    name: "F",
    // No tags field.
    scores: [70],
    items: [
      { sku: "A", qty: 1 },
      { sku: "B", qty: 2 }
    ]
  },
  {
    _id: 7,
    name: "G",
    // Intentionally uses scalars to illustrate the impact of an inconsistent schema.
    tags: "red",
    scores: 88,
    items: { sku: "A", qty: 2 }
  },
  {
    _id: 8,
    name: "H",
    tags: ["red", "red"],
    scores: [50],
    items: []
  }
]);
~~~

Summary of key fields:

| `_id` | `tags` | `scores` | `items` |
| --- | --- | --- | --- |
| 1 | `["red", "blue"]` | `[65, 85, 94]` | A:1, B:3 |
| 2 | `["blue", "red"]` | `[75, 92]` | A:3 |
| 3 | `["red", "blue", "green"]` | `[82]` | B:1 |
| 4 | `["red"]` | `[88, 90]` | Empty |
| 5 | `[]` | `[]` | Empty |
| 6 | Does not exist | `[70]` | A:1, B:2 |
| 7 | Scalar `"red"` | Scalar `88` | Single object A:2 |
| 8 | `["red", "red"]` | `[50]` | Empty |

Document 7 is intentionally **schema-divergent**; the goal is to make clear that some operators can also match scalars, whereas operators that strictly require an array do not. In real applications, schema validation should be used to prevent this inconsistency if a field is defined to always be an array.

To display results in ID order, you can append `.sort({ _id: 1 })` to the `find()` statement. Without `sort()`, **do not rely on the returned order** as a query contract.

---

## 3. Whole-Array Matching: Equals the Exact Given List

### 3.1. Array Equality

When passing an array as the comparison value:

~~~javascript
db.arrayQueryLesson.find(
  { tags: ["red", "blue"] },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

In the flat-array dataset above, the result is **`_id: 1`**.

- `_id: 1` has exactly the two elements `"red"` and `"blue"` in this order.
- `_id: 2` has the same two elements but in **reverse order**, so it does not match.
- `_id: 3` has an additional `"green"`, so it does not match.
- `_id: 8` has two elements that are both `"red"`, so it does not match.

**Size, values, and order** all matter for matching an entire array. This is the choice when business logic requires an exact ordered list, such as a well-defined sequence of processing steps.

Explicit form with `$eq`:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $eq: ["red", "blue"] }
});
~~~

In one-dimensional array examples, the two forms express the same intent. Note that with **nested arrays**, MongoDB's equality semantics may also match a subarray element equal to the queried array; Section 10 covers how to avoid confusion in that case. Therefore, array equality should not be treated as an absolute recursive BSON structure verification tool.

### 3.2. Same Values in Reverse Order Still Differ

~~~javascript
db.arrayQueryLesson.find({ tags: ["blue", "red"] });
~~~

The result on the sample data is **`_id: 2`**, not `_id: 1`. MongoDB does not automatically sort elements before comparing for array equality.

If the business domain treats tags as an **unordered set**, an exact order-sensitive comparison may not be appropriate. In that case, consider `$all` or establish an ordering normalization rule before saving.

### 3.3. A Subarray Does Not Equal a Larger Array

~~~javascript
db.arrayQueryLesson.find({
  tags: ["red"]
});
~~~

The result is **`_id: 4`**, because this document's field is literally the single-element array `["red"]`. The condition does not mean “the array contains the value red”. To query by **element**, you must write it differently as shown in the next section.

In systems storing tags, this is a common mistake:

~~~javascript
// Incorrect for the intent "has tag red":
db.products.find({ tags: ["red"] });

// Correct for the intent "has tag red":
db.products.find({ tags: "red" });
~~~

### 3.4. Array of Documents: Equality Also Depends on Object Structure

For arrays of embedded documents, equality requires the document element to have matching contents; comparing against an embedded document can be sensitive to **field order within the document**, as well as the order of array elements.

~~~javascript
db.arrayQueryLesson.find({
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 3 }
  ]
});
~~~

In the sample set, this query finds `_id: 1`. However, if you only need “has a line with SKU A and quantity at least 1”, comparing the entire array is overly strict and breaks easily when documents gain new fields like `unit` or `warehouse`.

Typically, for arrays of objects, you should query by **element attributes**, using dotted paths or `$elemMatch`, rather than constraining the structure of the whole array.

---

## 4. Matching an Element by Scalar Value

The simplest query to find documents where `tags` **contains** the value `"red"` is:

~~~javascript
db.arrayQueryLesson.find(
  { tags: "red" },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Result on the dataset: **`_id: 1, 2, 3, 4, 7, 8`**.

Why?

- For documents 1, 2, 3, 4, and 8, `tags` is an array containing at least one `"red"` element.
- For document 7, `tags` is a **scalar** equal to `"red"`, so equality still matches.
- Document 5 has an empty array and document 6 is missing the field, so neither matches.

This is an important distinction: **`{ tags: "red" }` does not assert that the field must have an array type.** It can match either a scalar value or an element of an array.

If the schema dictates that `tags` is always an array and enforces it via a validator, this flexibility causes no issue. If legacy data mixes scalars and arrays, the query may return unintended extra documents.

### 4.1. Using `$elemMatch` to Enforce an Array Element

~~~javascript
db.arrayQueryLesson.find({
  tags: { $elemMatch: { $eq: "red" } }
});
~~~

This condition requires `tags` to be an array with **at least one element** equal to `"red"`; document 7 with scalar `"red"` does not match. The result is **`_id: 1, 2, 3, 4, 8`**.

For a simple membership check, `$elemMatch` can be more verbose than necessary. However, it is useful if you need to enforce array semantics and especially useful when multiple conditions must apply to the same element.

### 4.2. Element at a Specific Position

If the question is “the first element must equal red”, use array position:

~~~javascript
db.arrayQueryLesson.find({
  "tags.0": "red"
});
~~~

The result is **`_id: 1, 3, 4, 8`**. Document 2 has red at the second position and is excluded. Array indices start at **0**.

In MongoDB, the path `"tags.0"` accesses the first element of the `tags` field. This condition is neither equivalent to a membership check nor a whole-array match.

**When is position needed?** When element order carries clear business meaning: the first step of a workflow, a priority item, recipient order, or fixed slots. For tags without business ordering, querying by index is usually a sign that the data model or API is attaching unnecessary positional semantics.

---

## 5. `$in`: Array Has at Least One Value in a Selection Set

Suppose you need to find documents that have the tag `"green"` **or** `"blue"`:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $in: ["green", "blue"] }
});
~~~

The result is **`_id: 1, 2, 3`**.

Here `$in` expresses **OR** logic:

~~~text
tags contains "green"
        OR
tags contains "blue"
~~~

Because document 1 contains blue, it is selected even though it does not contain green. Document 3, which contains both green and blue, is also selected.

You can write the longer OR condition:

~~~javascript
db.arrayQueryLesson.find({
  $or: [
    { tags: "green" },
    { tags: "blue" }
  ]
});
~~~

For simple equality values, `$in` is usually easier to read. When the OR branches contain complex conditions, `$or` may be more appropriate.

### 5.1. `$in` Does Not Require All Values to Be Present

~~~javascript
db.arrayQueryLesson.find({
  tags: { $in: ["red", "blue"] }
});
~~~

The condition above finds **at least one** of the two colors, so even a document with only `["red"]` is selected. It does not satisfy the requirement “has both red and blue”.

To express AND for membership, use `$all`.

---

## 6. `$all`: Contains All Values, Regardless of Order

~~~javascript
db.arrayQueryLesson.find({
  tags: { $all: ["red", "blue"] }
});
~~~

Result: **`_id: 1, 2, 3`**.

- Document 1 has red and blue in the listed order.
- Document 2 has both even though the order is reversed.
- Document 3 has both red and blue, plus green.
- Document 4 only has red, so it is insufficient.
- Document 7 is a scalar `"red"` and not an array containing both elements.

Differences between the operators:

~~~text
tags = ["blue", "red", "green"]

Match ["red", "blue"]          -> NO (differs in both order and size)
$in   ["red", "blue"]          -> YES (at least one value)
$all  ["red", "blue"]          -> YES (contains both values)
$size 2                        -> NO (array has 3 elements)
~~~

### 6.1. `$all` Does Not Check Repetition Count of a Value

~~~javascript
db.arrayQueryLesson.find({
  tags: { $all: ["red", "red"] }
});
~~~

Using the same value twice in `$all` **does not force the array to have two red elements**. An array `["red"]` also satisfies the presence condition for red. If business logic requires **two occurrences** of the same value, you need to design an array counting check or an appropriate schema.

This also means `$all` should be understood as “contains all required values”, **not a comparison of two multisets with duplicate counts**.

### 6.2. Combining `$all` with `$size`

Suppose you need exactly **two elements**, containing both red and blue, regardless of order:

~~~javascript
db.arrayQueryLesson.find({
  tags: {
    $all: ["red", "blue"],
    $size: 2
  }
});
~~~

In this flat dataset, the result is **`_id: 1, 2`**. The `$all` condition requires two distinct values; `$size: 2` excludes document 3 which has an extra green.

However, if the actual requirement is a specifically ordered list, use array equality. Do not combine multiple operators unnecessarily to simulate a comparison that already has a clear syntax.

---

## 7. `$size`: Element Count, Not a Value Condition

Query all documents with exactly two tags:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $size: 2 }
});
~~~

Result: **`_id: 1, 2, 8`**.

Document 8 has two identical tags `["red", "red"]`, so it is still valid for `$size: 2`. This operator **does not care about values or uniqueness**.

Query empty arrays:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $size: 0 }
});
~~~

Result: **`_id: 5`**. Document 6 is missing `tags` and document 7 has `tags` as a scalar, so neither is an empty array.

### 7.1. `$size` Is Not a Range Comparison Operator

Do not write:

~~~javascript
// Not valid $size syntax to express "at least 2 elements":
db.arrayQueryLesson.find({
  tags: { $size: { $gte: 2 } }
});
~~~

`$size` in a query accepts an **exact integer**, not a `$gte` expression like this.

If the schema guarantees the field is always an array, you can use an aggregation expression to compute the size and compare:

~~~javascript
db.arrayQueryLesson.find({
  $expr: {
    $gte: [
      {
        $size: {
          $cond: [
            { $isArray: "$tags" },
            "$tags",
            []
          ]
        }
      },
      2
    ]
  }
});
~~~

In the example, `$isArray` and `$cond` guard against documents missing the field or containing a scalar. If you omit the guard and call `$size` on a non-array value, the query can throw an error.

For applications that frequently filter by array size, consider storing a `tagCount` field updated synchronously. In that case, however, you must handle all element add/remove paths, retries, and migrations so the counter never drifts from the actual data.

### 7.2. Performance of `$size`

A standard multikey index **does not directly optimize the `$size` condition itself**. MongoDB can use other conditions in the same query to narrow down the document set, and then check the array length. If most requests only search for “arrays with at least N elements”, measure the query plan and consider a materialized count or an alternative storage structure when truly needed.

---

## 8. Multiple Conditions on a Numeric Array: Same Element or Different Elements?

This is the most important example for understanding `$elemMatch`.

Requirement: **“Has at least one score both greater than 80 and less than 90.”**

### 8.1. Syntax That Can Match Two Different Elements

~~~javascript
db.arrayQueryLesson.find({
  scores: {
    $gt: 80,
    $lt: 90
  }
});
~~~

For an array field, MongoDB can evaluate `$gt: 80` on **one element** and `$lt: 90` on **another element**. Therefore, this query can match document 2:

~~~javascript
{ _id: 2, scores: [75, 92] }
~~~

Where:

- `92 > 80` is true.
- `75 < 90` is true.
- **No single score** is simultaneously greater than 80 and less than 90.

Document 2 **does not meet the business intent**, even though a query expression lacking `$elemMatch` can find it.

The query above can also match document 7, where `scores` is scalar `88`, because the value 88 itself satisfies both comparisons.

### 8.2. Correct Syntax When Requiring the Same Element

~~~javascript
db.arrayQueryLesson.find({
  scores: {
    $elemMatch: {
      $gt: 80,
      $lt: 90
    }
  }
});
~~~

Result on the sample data: **`_id: 1, 3, 4`**.

| `_id` | `scores` | Has a score in (80,90)? | With `$elemMatch` |
| --- | --- | --- | --- |
| 1 | `[65, 85, 94]` | 85 | Matches |
| 2 | `[75, 92]` | None | Does not match |
| 3 | `[82]` | 82 | Matches |
| 4 | `[88, 90]` | 88 | Matches |
| 5 | `[]` | No | Does not match |
| 6 | `[70]` | No | Does not match |
| 7 | Scalar `88` | Not an array | Does not match |
| 8 | `[50]` | No | Does not match |

`$elemMatch` requires **at least one element in the array** to satisfy all conditions inside it simultaneously. That element can be at any position.

### 8.3. Range Boundaries

Comparison operators:

| Operator | Meaning |
| --- | --- |
| `$gt: 80` | Greater than 80, **excluding** 80. |
| `$gte: 80` | Greater than or equal to 80. |
| `$lt: 90` | Less than 90, **excluding** 90. |
| `$lte: 90` | Less than or equal to 90. |

If the requirement is “from 80 to 90, inclusive”, you must write:

~~~javascript
db.arrayQueryLesson.find({
  scores: {
    $elemMatch: {
      $gte: 80,
      $lte: 90
    }
  }
});
~~~

Do not let a range-boundary mistake be masked by whether the array query uses `$elemMatch` or not.

---

## 9. Array of Embedded Documents: Dotted Path and `$elemMatch`

Each element of `items` in the example is an object with `sku` and `qty`. A common requirement is:

> “Find documents that have **the same line item** carrying `sku = "A"` and `qty >= 2`.”

### 9.1. Dotted Path Syntax Can Combine Different Elements

~~~javascript
db.arrayQueryLesson.find({
  "items.sku": "A",
  "items.qty": { $gte: 2 }
});
~~~

This query can match **`_id: 1, 2, 6, 7`**.

Consider document 1:

~~~javascript
{
  _id: 1,
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 3 }
  ]
}
~~~

- The condition `"items.sku": "A"` is true for the **first element**.
- The condition `"items.qty": { $gte: 2 }` is true for the **second element**.
- There is no line item for SKU A with qty at least 2.

Similarly, document 6 has A:1 and B:2; it can still match the two dotted-path conditions without meeting the requirement on the same line.

Document 7 also shows that a dotted path can traverse into a **scalar object**, not only array elements.

### 9.2. Grouping Conditions with `$elemMatch`

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
});
~~~

The correct result for this requirement: **`_id: 2`**.

- Document 2 has the element `{ sku: "A", qty: 3 }`.
- Documents 1 and 6 have SKU A, but the quantity on that A line itself is only 1.
- Document 7 stores `items` as a scalar object rather than an array, so `$elemMatch` does not match.

This is the exact semantics:

~~~text
There exists an element x in items such that:
    x.sku == "A"
        AND
    x.qty >= 2
~~~

`$elemMatch` does not require all elements to match; only **one element** needs to satisfy both conditions.

### 9.3. For a Single Condition, Dotted Path Is Usually Enough

If you only need “has a line item with SKU A”:

~~~javascript
db.arrayQueryLesson.find({
  "items.sku": "A"
});
~~~

This is concise and appropriate when there is no need to enforce multiple conditions on the same element, provided the schema is well understood. If you want to match only when `items` is an array, you can use:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $elemMatch: { sku: "A" }
  }
});
~~~

On the dataset, the second query excludes document 7 because `items` is not an array. MongoDB does not automatically fix an inconsistent schema; applications should define field types right from design time.

### 9.4. Querying Objects with Multiple Fields

Suppose a line item has the structure:

~~~javascript
{
  sku: "A",
  qty: 2,
  warehouse: { city: "HCM", zone: "A1" },
  status: "READY"
}
~~~

You can combine fields inside the same element:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 },
      status: "READY",
      "warehouse.city": "HCM"
    }
  }
});
~~~

The dotted path `"warehouse.city"` is now interpreted relative to the **subobject being checked** inside `$elemMatch`. All conditions must hold for the same line item.

---

## 10. When Two Different Elements Must Coexist

`$elemMatch` requires **one element to satisfy multiple conditions**. But there are other requirements:

> “An order must have at least one SKU A line item, and at least one SKU B line item with quantity 2 or more.”

The two conditions are allowed to belong to **two different elements**. You can write this using `$and` containing two `$elemMatch` expressions:

~~~javascript
db.arrayQueryLesson.find({
  $and: [
    {
      items: {
        $elemMatch: { sku: "A" }
      }
    },
    {
      items: {
        $elemMatch: {
          sku: "B",
          qty: { $gte: 2 }
        }
      }
    }
  ]
});
~~~

Result: **`_id: 1, 6`**.

- Document 1 has A:1 and B:3.
- Document 6 has A:1 and B:2.
- Document 2 only has A:3, no B.
- Document 7 contains a scalar object, not an array.

Where appropriate, `$all` also accepts multiple `$elemMatch` expressions:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $all: [
      { $elemMatch: { sku: "A" } },
      { $elemMatch: { sku: "B", qty: { $gte: 2 } } }
    ]
  }
});
~~~

Both forms express the existence of two condition groups. The element satisfying the first condition and the element satisfying the second condition may be different elements. If a single element satisfies both condition groups simultaneously, MongoDB does not force picking two distinct elements either; when business logic requires **two distinct objects by ID**, add an identifier constraint or use an appropriate data model.

### 10.1. Do Not Mix Up the Two Requirements

Compare:

~~~javascript
// One line item must be both A and have qty >= 2:
{
  items: {
    $elemMatch: { sku: "A", qty: { $gte: 2 } }
  }
}

// Has a line item A and a line item B with qty >= 2:
{
  $and: [
    { items: { $elemMatch: { sku: "A" } } },
    { items: { $elemMatch: { sku: "B", qty: { $gte: 2 } } } }
  ]
}
~~~

Business intent determines the query structure. Just because all conditions appear in one JSON expression does not mean they all apply to the same element.

---

## 11. Nested Arrays and Access Paths

Sometimes a field holds an **array of arrays**, such as score rows per class or coordinate groups. In that case, distinguish between:

- **Outer array:** list of groups.
- **Inner array:** element that also has array type.
- **Scalar element:** numeric/string value inside the innermost array.

Example:

~~~javascript
db.matrixExamples.insertMany([
  {
    _id: "M1",
    matrix: [
      [1, 2],
      [3, 4]
    ]
  },
  {
    _id: "M2",
    matrix: [
      [1, 3],
      [2, 4]
    ]
  }
]);
~~~

If you need to check whether the first row equals `[1, 2]`, you can use an element index:

~~~javascript
db.matrixExamples.find({
  "matrix.0": [1, 2]
});
~~~

This query finds documents whose **subarray at position 0** matches the given array value under equality semantics.

If you need to check the **entire two-dimensional structure**, comparing the array at the root level can be useful:

~~~javascript
db.matrixExamples.find({
  matrix: [
    [1, 2],
    [3, 4]
  ]
});
~~~

However, MongoDB has array equality rules that can also match a **subarray element** equal to the queried array value. When designing a schema for deeply nested arrays or when exact structural verification is required, place conditions at the exact path, or use aggregation expressions that explicitly check type, length, and structure. Do not extrapolate from flat-array examples to every kind of nested array.

### 11.1. Arrays of Documents Inside Documents

For example, an order has multiple shipments, and each shipment has product packages:

~~~javascript
{
  _id: "ORDER-1",
  shipments: [
    {
      carrier: "FAST",
      packages: [
        { sku: "A", qty: 1 },
        { sku: "B", qty: 2 }
      ]
    },
    {
      carrier: "SLOW",
      packages: [
        { sku: "A", qty: 3 }
      ]
    }
  ]
}
~~~

The requirement “has a shipment by carrier FAST **containing within that same shipment** a package with SKU A” needs to preserve per-shipment boundaries:

~~~javascript
db.orders.find({
  shipments: {
    $elemMatch: {
      carrier: "FAST",
      packages: {
        $elemMatch: {
          sku: "A"
        }
      }
    }
  }
});
~~~

If `"shipments.carrier": "FAST"` and `"shipments.packages.sku": "A"` are split into two independent conditions, they can be satisfied by **two different shipments**, producing wrong results for the same-shipment constraint.

---

## 12. Empty Arrays, Missing Fields, `null`, and Scalar Values

One subtle source of bugs is when an application conflates distinct states:

~~~javascript
{ _id: 1, tags: [] }
{ _id: 2, tags: null }
{ _id: 3 }                  // missing tags
{ _id: 4, tags: "red" }      // scalar
{ _id: 5, tags: ["red"] }    // array
~~~

These representations are **not synonymous**.

### 12.1. Empty Arrays

To find fields with an empty array:

~~~javascript
db.collection.find({
  tags: { $size: 0 }
});
~~~

In the sample data, the result is `_id: 5`. Do not use `{ tags: null }` to mean “array with no elements”: MongoDB has specific rules when matching `null` and missing fields.

### 12.2. Field Existence

~~~javascript
db.arrayQueryLesson.find({
  tags: { $exists: true }
});
~~~

Returns documents that have the `tags` field, including empty arrays or scalars. On the sample dataset, this includes **`_id: 1, 2, 3, 4, 5, 7, 8`**, excluding document 6.

`$exists` only states that the field is present; it **does not assert that the field is an array, has elements, or has a non-null value**.

### 12.3. Negating Membership

~~~javascript
db.arrayQueryLesson.find({
  tags: { $ne: "red" }
});
~~~

On the sample data, this finds **`_id: 5, 6`**. It matches documents where `tags` **does not contain** the red element, and also includes documents **missing the tags field**.

Similarly:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $nin: ["red", "blue"] }
});
~~~

`$nin` typically matches documents that contain none of the values in the list, **including missing fields**. This may not be the intent of a “products with tags other than red/blue” filter. If the field actually needs to exist, combine it with an appropriate presence or field-type condition.

### 12.4. Selecting Only Documents Where the Field Is an Array

When the schema is unstable, you need to distinguish arrays from scalars:

~~~javascript
db.arrayQueryLesson.find({
  tags: { $type: "array" }
});
~~~

In the dataset, this condition finds documents **`_id: 1, 2, 3, 4, 5, 8`**. Document 7 has `tags` as a string so it is not selected. In applications where inputs can be controlled, using a schema validator to guarantee data types simplifies all downstream queries.

### 12.5. Negation on Arrays of Documents Must Be Expressed Carefully

The requirement “no line item has `sku=A` and `qty>=2`” can use `$not` wrapping `$elemMatch`:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $not: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 2 }
      }
    }
  }
});
~~~

This condition finds documents where **no array element exists** that satisfies the constraint pair. It can also match documents missing `items` or containing a non-array value. If business rules require `items` to be a valid array, add schema constraints or an appropriate field-type condition.

---

## 13. Exact Embedded Document Match or Partial Field Match?

Consider:

~~~javascript
{
  _id: "ORDER-2",
  items: [
    {
      sku: "A",
      qty: 2,
      unitPriceMinor: 120000
    }
  ]
}
~~~

If searching for an object element using direct equality:

~~~javascript
db.orders.find({
  items: {
    sku: "A",
    qty: 2
  }
});
~~~

Object equality requires the element to have an **exact matching embedded document**, so an object containing an extra `unitPriceMinor` field may not match. Field order inside the embedded document can also matter in exact comparisons.

If you only care about SKU and quantity, write:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: 2
    }
  }
});
~~~

With `$elemMatch`, the element can have extra `unitPriceMinor`, `discount`, or `warehouse` fields and still match. This query tracks **business conditions** closely and is less coupled to schema expansion.

Dotted path syntax:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": 2
});
~~~

still risks combining two different elements if the order has multiple items. Only when the intent is “has SKU A somewhere and has a line with qty 2 somewhere” do two independent dotted paths express it accurately.

### 13.1. Elements with Multiple Data Types

MongoDB allows arrays to hold different BSON types unless prohibited by a schema:

~~~javascript
{
  _id: "MIXED-1",
  values: [10, "10", null, { number: 10 }]
}
~~~

`{ values: 10 }` and `{ values: "10" }` are not equivalent representations. For range queries, BSON types and *type bracketing* affect results; do not expect MongoDB to coerce numeric strings into numbers automatically.

If the domain requires an all-numeric array, validate inputs and define a consistent schema. An array mixing strings and numbers easily causes bugs in filtering, sorting, and aggregation.

---

## 14. Multikey Indexes for Array Queries

When creating an index on a field containing an array, MongoDB uses a **multikey index**, creating index keys from array elements according to indexing rules. This prevents membership queries from necessarily scanning the entire collection.

Example:

~~~javascript
db.arrayQueryLesson.createIndex({ tags: 1 });

db.arrayQueryLesson.find({
  tags: "red"
}).explain("executionStats");
~~~

A query planner can choose the index to find documents containing red. However, an index does not automatically make every array query performant: element count, selectivity, number of documents to fetch, and sort criteria all have an impact.

### 14.1. Compound Multikey Index for Arrays of Documents

~~~javascript
db.arrayQueryLesson.createIndex({
  "items.sku": 1,
  "items.qty": 1
});
~~~

This is a compound index on **two subfields of the same `items` array** in the sample schema. It can support conditions on SKU and quantity:

~~~javascript
db.arrayQueryLesson.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
}).explain("executionStats");
~~~

`$elemMatch` not only expresses the business constraint, but under appropriate conditions also allows MongoDB to **compound index bounds** for predicates that must belong to the same array element. With independent dotted-path conditions, the query planner may not be permitted to intersect index bounds that way because the conditions could match on different elements.

Do not assume that creating this index guarantees the query will never read documents: multikey constraints, projections, and the actual query plan determine whether a FETCH stage is needed.

### 14.2. Metrics and Aspects to Monitor

| Metric/Aspect | Question to Answer |
| --- | --- |
| `nReturned` | How many documents were actually returned? |
| `totalKeysExamined` | How many index entries were scanned? |
| `totalDocsExamined` | How many documents were read/examined? |
| `IXSCAN` / `COLLSCAN` | Did it use an index or fall back to a collection scan? |
| Index size | With many elements per document, how much does the index bloat? |
| Insert/update throughput | How does the cost of maintaining the multikey index affect writes? |
| p95/p99 latency | Is the query fast on real data or only on small samples? |

Multikey indexes have limitations, such as **a compound multikey index cannot contain multiple independent array fields in a way that creates parallel arrays within a single document**. Specific constraints depend on field structure and data. Index design should be based on the actual schema and query plans, rather than mechanically “adding every array field to an index”.

### 14.3. Do `$size`, `$all`, and `$elemMatch` Interact the Same Way with Indexes?

No. They have different semantics and index utilization capabilities:

- Membership checks like `{tags:"red"}` are usually good candidates for an index on `tags`.
- `$all` requires multiple values to be present; effectiveness depends on how the query planner combines conditions/indexes.
- `$size` is not directly optimized by an index for the element-count condition itself.
- `$elemMatch` is critical when grouping multiple conditions on the **same** element and can support compounding/intersection of bounds in appropriate situations.

Before deciding to add an index, run `explain("executionStats")` on a representative dataset. On a collection with only eight sample documents, the planner may reasonably choose `COLLSCAN`; do not treat that as a performance conclusion for a large system.

---

## 15. Applying This with the Java MongoDB Sync Driver

When using Java, you can use `Filters` to express semantics identical to `mongosh`. Example with the MongoDB Java Sync Driver:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public class ArrayQueries {

    public static void examples(MongoCollection<Document> collection) {
        // Exact array ["red", "blue"] in order.
        Bson exactArray = Filters.eq(
            "tags", List.of("red", "blue")
        );

        // Array contains element "red" (can also match scalar).
        Bson containsRed = Filters.eq("tags", "red");

        // Contains at least one of the two values.
        Bson containsEither = Filters.in(
            "tags", "red", "blue"
        );

        // Contains both values, regardless of order.
        Bson containsBoth = Filters.all(
            "tags", "red", "blue"
        );

        // Has an items line with sku=A and qty>=2.
        Bson sameItem = Filters.elemMatch(
            "items",
            Filters.and(
                Filters.eq("sku", "A"),
                Filters.gte("qty", 2)
            )
        );

        // Each filter represents a different requirement.
        System.out.println(collection.countDocuments(exactArray));
        System.out.println(collection.countDocuments(containsRed));
        System.out.println(collection.countDocuments(containsEither));
        System.out.println(collection.countDocuments(containsBoth));
        System.out.println(collection.countDocuments(sameItem));
    }
}
~~~

With a real schema, use appropriate POJOs/codecs and check data-type consistency. In particular, `Filters.eq("tags", List.of(...))` and `Filters.eq("tags", "red")` are **two different questions**, even though both call the `eq` method.

If you need comparison conditions for **the same element in a scalar array**, you can express it explicitly:

~~~java
Bson oneScoreBetween80And90 = new Document(
    "scores",
    new Document(
        "$elemMatch",
        new Document("$gt", 80).append("$lt", 90)
    )
);
~~~

Do not write two separate `gte`/`lt` conditions and assume MongoDB automatically forces them onto the same element.

### 15.1. When Using Spring Data MongoDB

With `MongoTemplate`, you can use `Criteria.elemMatch(...)`:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("items").elemMatch(
        Criteria.where("sku").is("A")
            .and("qty").gte(2)
    )
);
~~~

The logic remains equivalent to the BSON query:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
}
~~~

When encountering incorrect result bugs, inspect the **actual BSON query** generated by the abstraction in use, not just the Java method names.

---

## 16. Four Business Scenarios and How to Choose Operators

### 16.1. Product Tag Filter

Requirement: the customer selects two tags `"sale"` and `"outdoor"`.

- Mode “has **at least one** selected tag”: use `$in`.
- Mode “must have **all** selected tags”: use `$all`.
- Mode “tag list **equals** the two tags in stored order”: use array equality if order is part of the requirement.
- Mode “only those two tags, no other tags, order irrelevant”: consider `$all` combined with `$size` when the tags are two distinct values.

Do not pick an operator before the UI/API defines “any” versus “all”.

### 16.2. Student Test Scores

A student has `scores: [70, 95]`. The requirement “has at least one test in the range 80–90” **must not** be expressed as:

~~~javascript
{ scores: { $gte: 80, $lte: 90 } }
~~~

Because the two comparisons can rely on different elements. Use:

~~~javascript
{
  scores: {
    $elemMatch: {
      $gte: 80,
      $lte: 90
    }
  }
}
~~~

If the actual requirement is “has **a score >= 80** and has **a score <= 90**, possibly from two different attempts”, the syntax without `$elemMatch` can be right. Semantics must come from business requirements.

### 16.3. Orders with Product Variants

An order has:

~~~javascript
{
  orderId: "O-1",
  lines: [
    { color: "black", available: false },
    { color: "white", available: true }
  ]
}
~~~

Requirement “has a black variant in stock”:

~~~javascript
{
  lines: {
    $elemMatch: {
      color: "black",
      available: true
    }
  }
}
~~~

The document above **does not match**. Writing `"lines.color":"black"` and `"lines.available":true` independently would be wrong because it combines two different variants.

### 16.4. Finding Events by an Attribute Pair

Suppose `events` contains:

~~~javascript
[
  { type: "LOGIN", success: false, at: ISODate("2026-11-14T08:00:00Z") },
  { type: "PAYMENT", success: true, at: ISODate("2026-11-14T08:05:00Z") }
]
~~~

Requirement “has a successful LOGIN event” requires:

~~~javascript
{
  events: {
    $elemMatch: {
      type: "LOGIN",
      success: true
    }
  }
}
~~~

If you only write `"events.type":"LOGIN"` and `"events.success":true`, the two conditions could come from two different events, generating a false security alert.

---

## 17. Self-Check Exercises with Sample Data

### Exercise 1: Whole-Array Matching

Predict the returned ID:

~~~javascript
db.arrayQueryLesson.find({
  tags: ["blue", "red"]
});
~~~

**Answer:** `_id: 2`. Document 1's array has the same values but in reverse order.

### Exercise 2: Element vs. Whole Array

Two queries:

~~~javascript
// A
db.arrayQueryLesson.find({ tags: "red" });

// B
db.arrayQueryLesson.find({ tags: ["red"] });
~~~

**Answer:** A matches IDs 1, 2, 3, 4, 7, 8; B matches ID 4 in the flat-array dataset. A is a membership/scalar equality check, whereas B requires a specific array.

### Exercise 3: AND or OR?

~~~javascript
// A
db.arrayQueryLesson.find({
  tags: { $in: ["red", "green"] }
});

// B
db.arrayQueryLesson.find({
  tags: { $all: ["red", "green"] }
});
~~~

**Answer:** A matches IDs 1, 2, 3, 4, 7, 8 because they have red or green; B only matches ID 3 because it has both.

### Exercise 4: Counting Elements

~~~javascript
db.arrayQueryLesson.find({
  tags: { $size: 2 }
});
~~~

**Answer:** IDs 1, 2, 8. Two elements can have duplicate values.

### Exercise 5: Numeric Range

~~~javascript
// A
db.arrayQueryLesson.find({
  scores: { $gt: 80, $lt: 90 }
});

// B
db.arrayQueryLesson.find({
  scores: {
    $elemMatch: { $gt: 80, $lt: 90 }
  }
});
~~~

**Answer:** A can match IDs 1, 2, 3, 4, 7; B only matches IDs 1, 3, 4. ID 2 has no score satisfying both bounds simultaneously; ID 7 contains a scalar.

### Exercise 6: Array of Documents

~~~javascript
// A
db.arrayQueryLesson.find({
  "items.sku": "A",
  "items.qty": { $gte: 2 }
});

// B
db.arrayQueryLesson.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
});
~~~

**Answer:** A can match IDs 1, 2, 6, 7; B only matches ID 2. This is the difference between “both conditions exist somewhere” and “one element satisfies both”.

### Exercise 7: Empty Arrays and Missing Fields

~~~javascript
// A
db.arrayQueryLesson.find({
  tags: { $size: 0 }
});

// B
db.arrayQueryLesson.find({
  tags: { $ne: "red" }
});
~~~

**Answer:** A matches ID 5; B matches IDs 5 and 6. With B, missing fields are also included.

### Exercise 8: Choosing a Structure for New Requirements

Suppose you have an `orders` collection with `items` containing `sku`, `warehouseId`, and `qty`. Write queries to:

1. Find orders with **any** item belonging to warehouse `W1` or `W2`.
2. Find orders with **one item** that has `sku = "P1"` and `qty >= 5`.
3. Find orders with **one item P1** and **one item P2**, not required to be the same element.
4. Find orders with **exactly three items**.

**Hint:** (1) use dotted path + `$in`; (2) use a single `$elemMatch`; (3) use two `$elemMatch` combined with `$and`; (4) use `$size: 3`.

---

## 18. Common Conceptual Pitfalls

| Misconception | Correct Understanding |
| --- | --- |
| “`{ tags: ["a", "b"] }` means contains a and b.” | For flat arrays, this is array equality: size and order must match. |
| “`{ tags: "a" }` only matches array fields.” | It can also match a scalar field equal to `"a"`. |
| “`$in` requires all values.” | `$in` is OR; `$all` is used when all values must be present. |
| “`$all` guarantees exact order.” | It does not enforce order and allows extra elements. |
| “`$all: ["a", "a"]` requires two occurrences of a.” | No; it does not count repetitions of the same value. |
| “`$size` checks array contents.” | It only checks the number of elements. |
| “`$size` works with `$gte`.” | As a query operator, `$size` takes an exact length. |
| “Two predicates on an array always apply to one element.” | They can be satisfied by different elements. |
| “A dotted path is enough to constrain `sku` and `qty` on the same item.” | `$elemMatch` is required when conditions must apply to the same element. |
| “`$elemMatch` requires every element to match.” | Only **at least one** element needs to satisfy all predicates. |
| “A scalar object can be treated as a one-element array.” | `$elemMatch` requires an array field; scalars do not match. |
| “Empty array, `null`, and missing field are the same.” | They have different semantics and query behaviors. |
| “`$ne`/`$nin` automatically exclude missing fields.” | They can match documents that lack the field. |
| “Having a multikey index makes every array query fast.” | You must check index bounds, index size, fetch, and query plan. |

## 19. Approach to Writing Array Queries in Projects

1. **Write the question in business terms.** Is it “equals exactly”, “contains any”, “contains all”, “has at least one element satisfying multiple conditions”, or “has two elements satisfying two separate conditions”?
2. **Confirm the schema.** Is the field always an array, or can it be a scalar, `null`, or missing? Does the array contain scalars or embedded documents? Are there arrays nested inside arrays?
3. **Choose the minimal operator that accurately expresses intent.** Use array equality, scalar equality, `$in`, `$all`, `$size`, `$elemMatch`, or dotted paths in the right case.
4. **Test adversarial cases.** Reverse element order, add extra elements, split conditions across two different elements, use empty arrays, missing fields, and mismatched data types.
5. **Review indexes against access paths.** For arrays with many elements, measure cardinality, multikey indexes, `keysExamined`, and `docsExamined`.
6. **Watch for schema drift.** When a field changes from scalar to array or a subobject adds new fields, equality queries can change behavior. Use migrations/validation to keep data consistent.
7. **Verify results on representative data.** Measure both **business correctness** and latency; a fast query that mixes data from different elements is still a wrong query.

## 20. Further Official Reading

- [MongoDB — Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/): matching arrays, elements, and array conditions.
- [MongoDB — Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/): dotted paths and `$elemMatch` with objects in arrays.
- [MongoDB — `$elemMatch`](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/): semantics where a single element must satisfy all conditions.
- [MongoDB — `$all`](https://www.mongodb.com/docs/manual/reference/operator/query/all/): requiring all listed values to be present.
- [MongoDB — `$size`](https://www.mongodb.com/docs/manual/reference/operator/query/size/): checking array length and index-related limitations.
- [MongoDB — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): indexing arrays and using `$elemMatch` with compound bounds.
- [MongoDB — Java Sync Driver, Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): building BSON filters in Java.

The core takeaway of this lesson is **scoping conditions accurately**:

- **Whole array**: comparing list to list, usually caring about size and order.
- **Element existence**: comparing against a scalar value, using `$in`, or corresponding membership operators.
- **Same element**: grouping all constraints that must hold together inside one `$elemMatch`.
- **Multiple elements with multiple roles**: explicitly writing independent existence conditions without accidentally forcing them onto one element or splitting them apart.

Once you distinguish those four interpretations, choosing `$eq`, `$in`, `$all`, `$size`, dotted paths, and `$elemMatch` becomes a reasoned decision rather than trying syntax until the query happens to return data.
