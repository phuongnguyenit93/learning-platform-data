# Constraining Multiple Conditions on the Same Element with `$elemMatch` in MongoDB

MongoDB allows a document to contain arrays of simple values or arrays of nested objects. When querying an array, the crucial question is often not only “does the document contain this value?” but also **“do those conditions hold together on a single element of the array?”**. That is the primary purpose of the `$elemMatch` query operator.

For example, an order has a line item for product A with quantity 1 and a line item for product B with quantity 5. Both conditions “has product A” and “has quantity at least 3” are true at the document level, yet **no line item is both product A and has quantity at least 3**. If queried incorrectly, the system can return orders that do not satisfy the user's requirement.

This lesson belongs to the **Array Queries** chapter in MongoDB. We will explain the exact semantics of `$elemMatch`, compare it with dot notation, and extend it to numeric arrays, arrays of objects, nested objects, nested arrays, projection, aggregation, element updates, and multikey indexes. The examples run in **mongosh** against the lab database `elem_match_lab`.

## 1. Core Idea: “Same Document” vs. “Same Element”

Consider the document:

~~~javascript
{
  _id: "order-001",
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 5 }
  ]
}
~~~

The query:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
})
~~~

can return the document above because:

- The condition `"items.sku": "A"` matches the first element.
- The condition `"items.qty": { $gte: 3 }` matches the second element.

MongoDB satisfied **both conditions at the document level**, without any constraint forcing them to belong to the same item.

To require that **there exists at least one item** having both `sku = "A"` and `qty >= 3`, use:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
})
~~~

Document `order-001` does not match this query.

Logically:

~~~text
Without $elemMatch:
  there exists an item X with sku = "A"
  AND there exists an item Y with qty >= 3
  X and Y may be different.

With $elemMatch:
  there exists an item X such that
     X.sku = "A"
     AND X.qty >= 3
  All conditions apply to the same element X.
~~~

You can think of this similarly to an `EXISTS` expression in a relational database: finding documents where there exists an array element satisfying all inner conditions.

## 2. Preparing the Practice Dataset

In mongosh, select a dedicated database for the lesson:

~~~javascript
use elem_match_lab
~~~

Insert the sample data once:

~~~javascript
db.orders.insertMany([
  {
    _id: "ord-1",
    customerId: "c-01",
    status: "PAID",
    scores: [50, 98],
    items: [
      {
        sku: "A",
        qty: 1,
        price: 100,
        warehouse: "HCM",
        options: { color: "red", size: "M" },
        promotions: [{ code: "VIP", active: false }]
      },
      {
        sku: "B",
        qty: 5,
        price: 200,
        warehouse: "HN",
        options: { color: "blue", size: "L" },
        promotions: [{ code: "VIP", active: true }]
      }
    ]
  },
  {
    _id: "ord-2",
    customerId: "c-02",
    status: "PAID",
    scores: [82, 95],
    items: [
      {
        sku: "A",
        qty: 4,
        price: 150,
        warehouse: "HCM",
        options: { color: "red", size: "M" },
        promotions: [{ code: "VIP", active: true }]
      },
      {
        sku: "C",
        qty: 1,
        price: 300,
        warehouse: "HN",
        options: { color: "green", size: "S" },
        promotions: []
      }
    ]
  },
  {
    _id: "ord-3",
    customerId: "c-03",
    status: "CREATED",
    scores: [75, 88],
    items: [
      {
        sku: "A",
        qty: 2,
        price: 100,
        warehouse: "HN",
        options: { color: "blue", size: "M" },
        promotions: [{ code: "VIP", active: false }]
      },
      {
        sku: "B",
        qty: 4,
        price: 210,
        warehouse: "HCM",
        options: { color: "red", size: "L" },
        promotions: [{ code: "FLASH", active: true }]
      }
    ]
  },
  {
    _id: "ord-4",
    customerId: "c-04",
    status: "CREATED",
    scores: [],
    items: []
  },
  {
    _id: "ord-5",
    customerId: "c-05",
    status: "PAID",
    scores: [91, 96],
    items: [
      {
        sku: "B",
        qty: 7,
        price: 205,
        warehouse: "HCM",
        options: { color: "red", size: "M" },
        promotions: [{ code: "FLASH", active: false }]
      },
      {
        sku: "A",
        qty: 3,
        price: 155,
        warehouse: "HCM",
        options: { color: "blue", size: "S" },
        promotions: [{ code: "VIP", active: false }]
      }
    ]
  },
  {
    _id: "ord-6",
    customerId: "c-06",
    status: "PAID",
    scores: { midterm: 85 },
    items: {
      sku: "A",
      qty: 10,
      warehouse: "HCM"
    }
  }
])
~~~

**Practice note:** `ord-6` intentionally has `items` as a **single object instead of an array** and `scores` as an object, to illustrate semantic differences when a schema is inconsistent. In a real system, apply schema validation to avoid malformed data. Re-running `insertMany()` with the same `_id` values will trigger a duplicate key error; you can use a fresh lab database if you need to start over, rather than deleting data outside the scope of practice.

Summary table:

| Order | Key items | `scores` | Role in lesson |
|---|---|---|---|
| `ord-1` | A:1 at HCM; B:5 at HN | `[50,98]` | Conditions split across two different items |
| `ord-2` | A:4 at HCM; C:1 at HN | `[82,95]` | Has A with sufficient qty, VIP active on A |
| `ord-3` | A:2 at HN; B:4 at HCM | `[75,88]` | A and high qty belong to two different items |
| `ord-4` | Empty array | `[]` | No elements to match |
| `ord-5` | B:7 at HCM; A:3 at HCM | `[91,96]` | Has A with sufficient qty; multiple items meet qty |
| `ord-6` | Object A:10, not an array | Object | Distinguishes dot notation from `$elemMatch` |

To view a concise list of IDs, use projection and sort:

~~~javascript
db.orders.find(
  { status: "PAID" },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Most examples will use `{_id: 1}` so results are easy to verify without reading the entire document every time.

## 3. Dot Notation Can Combine Conditions Across Multiple Elements

### 3.1. Query Using Only Dot Notation

~~~javascript
db.orders.find(
  {
    "items.sku": "A",
    "items.qty": { $gte: 3 }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

On the sample data, matching IDs include:

~~~text
ord-1
ord-2
ord-3
ord-5
ord-6
~~~

Explanation:

- `ord-1`: A has qty 1, while B has qty 5; the two conditions are met by two different items.
- `ord-2`: A has qty 4; both conditions hold directly on A.
- `ord-3`: A has qty 2, while B has qty 4; again across two items.
- `ord-5`: A has qty 3; same element.
- `ord-6`: `items` is a single object containing `sku: "A"` and `qty: 10`; dot notation still accesses subfields of an object.

The purpose of dot notation is to access nested fields and allow MongoDB to look for matches inside arrays. It **does not by default group all predicates onto a single element**.

### 3.2. Wrapping with an Outer `$and` Does Not Fix the Bug

~~~javascript
db.orders.find({
  $and: [
    { "items.sku": "A" },
    { "items.qty": { $gte: 3 } }
  ]
})
~~~

Both branches of `$and` are still evaluated at the document level; each branch can match a different element. `$and` only requires both conditions to be true, **without adding a same-element constraint**.

### 3.3. Using `$elemMatch` to Constrain Properly

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Result:

~~~text
ord-2
ord-5
~~~

`ord-1` and `ord-3` no longer match because their A items have `qty` less than 3; `ord-6` does not match because `items` is not an array.

### 3.4. General Syntax

~~~javascript
db.collection.find({
  arrayField: {
    $elemMatch: {
      field1: condition1,
      field2: condition2,
      field3: condition3
    }
  }
})
~~~

Meaning: a document is selected when `arrayField` is an array containing **at least one element** that satisfies every predicate inside `$elemMatch` simultaneously. For an array of objects, use field names relative to each element object; for a scalar array, use comparison operators directly.

## 4. `$elemMatch` with Numeric or String Arrays

`$elemMatch` is not just for arrays of objects. It is especially important when applying **multiple value-range conditions** to the same element.

### 4.1. Requiring a Score Within a Range

Problem: find orders with **at least one** score satisfying:

~~~text
80 <= score < 90
~~~

Easy-to-get-wrong query:

~~~javascript
db.orders.find(
  {
    scores: {
      $gte: 80,
      $lt: 90
    }
  },
  { _id: 1, scores: 1 }
).sort({ _id: 1 })
~~~

For an array, `$gte` can match one score and `$lt` can match a different score. For instance, `ord-1` has `[50, 98]`: 98 ≥ 80 and 50 < 90, yet **no score falls inside the interval**.

Correct query:

~~~javascript
db.orders.find(
  {
    scores: {
      $elemMatch: {
        $gte: 80,
        $lt: 90
      }
    }
  },
  { _id: 1, scores: 1 }
).sort({ _id: 1 })
~~~

Result:

~~~text
ord-2  scores: [82, 95]  -> 82 is in the range.
ord-3  scores: [75, 88]  -> 88 is in the range.
~~~

`ord-1` is excluded because no element satisfies both conditions. `ord-5` has `[91, 96]` so no score is less than 90; `ord-4` is empty; `ord-6` is an object rather than an array.

### 4.2. Multiple Conditions on a Primitive Value

~~~javascript
// There exists an element in the ratings array with a value in [4, 5).
db.products.find({
  ratings: {
    $elemMatch: {
      $gte: 4,
      $lt: 5
    }
  }
})
~~~

For a string array:

~~~javascript
// There exists a code element belonging to a specific set.
db.catalog.find({
  codes: {
    $elemMatch: {
      $in: ["A-100", "A-200"]
    }
  }
})
~~~

With a **single condition** on a scalar array, `$elemMatch` is usually unnecessary for same-element binding, since there is only one predicate. However, `$elemMatch` still enforces that the field must be an **array**; that can make a difference when the schema has documents containing a scalar or object instead of an array.

### 4.3. Data Types Still Matter

The value `"85"` is a string, distinct from the number `85`. Range conditions follow MongoDB's BSON comparison and type rules; do not expect MongoDB to automatically convert numeric strings into numbers. When data has mixed types, normalize the schema and use an appropriate validator before trusting query outputs.

## 5. `$elemMatch` with Object Arrays: Three or More Conditions

### 5.1. Same SKU, Quantity, and Warehouse

Problem: find orders with **an item A**, quantity 3 or more, shipped from warehouse HCM.

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 },
        warehouse: "HCM"
      }
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Result:

~~~text
ord-2
ord-5
~~~

`ord-3` has A and has an item with quantity 4 at HCM, but the item with quantity 4 is B, so it does not match.

### 5.2. Combining Equality, Range, and Membership

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $in: ["A", "C"] },
      qty: { $gte: 2, $lte: 5 },
      warehouse: "HCM"
    }
  }
})
~~~

A single item must have SKU in A/C, quantity in `[2, 5]`, and warehouse HCM. `$in`, `$gte`, and `$lte` all apply to **fields of the same item** because they sit inside one `$elemMatch`.

### 5.3. Nested Conditions Inside an Item's Object

Each item has an `options` object. Find item A, qty ≥ 3, color red, size M:

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 },
        "options.color": "red",
        "options.size": "M"
      }
    }
  },
  { _id: 1 }
)
~~~

The result is `ord-2`. Dot notation **inside `$elemMatch`** like `"options.color"` accesses the subobject of the **same item currently being evaluated**.

Do not confuse the two levels:

~~~javascript
// Can match different items: does not guarantee same item.
{
  "items.sku": "A",
  "items.options.color": "red"
}

// Forces the same item to have A and color red.
{
  items: {
    $elemMatch: {
      sku: "A",
      "options.color": "red"
    }
  }
}
~~~

## 6. A Single Condition Inside `$elemMatch` Still Has Meaning

Syntactically, `$elemMatch` does not require at least two predicates. For example:

~~~javascript
db.orders.find(
  { "items.sku": "A" },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Returns `ord-1`, `ord-2`, `ord-3`, `ord-5`, and `ord-6`. Meanwhile:

~~~javascript
db.orders.find(
  { items: { $elemMatch: { sku: "A" } } },
  { _id: 1 }
).sort({ _id: 1 })
~~~

only returns `ord-1`, `ord-2`, `ord-3`, and `ord-5`, because `ord-6.items` is a single object.

Thus `$elemMatch` also has the property of **matching only fields that are arrays**. If data adheres to a schema that is always an array, this difference usually does not affect a single predicate. If data is mixed, the difference can cause an API to return different results.

This also serves as a reminder that **queries do not replace schema validation**. If business logic requires `items` to always be an array, design a validator to prevent cases like `ord-6` from entering production data.

## 7. Nested Arrays: `$elemMatch` at Multiple Levels

An item can contain a `promotions` array. Problem: find orders that have **item A with quantity at least 3**, and **that same item A** has an active VIP promotion.

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 },
        promotions: {
          $elemMatch: {
            code: "VIP",
            active: true
          }
        }
      }
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Result:

~~~text
ord-2
~~~

Explanation:

- `ord-1` has active VIP on item B, while item A only has qty 1 and inactive VIP.
- `ord-2` has item A qty 4 and active VIP.
- `ord-3` has item A qty 2, inactive VIP; item B has FLASH.
- `ord-5` has item A qty 3, but inactive VIP.

**Two levels of `$elemMatch` constrain two different element levels**: an item of `items`, and then a promotion of `promotions` belonging to that exact item.

~~~mermaid
flowchart TD
    O["Order document"] --> I["Exists item in items"]
    I --> S["item.sku = A"]
    I --> Q["item.qty >= 3"]
    I --> P["Exists promotion in item.promotions"]
    P --> C["promotion.code = VIP"]
    P --> A["promotion.active = true"]
~~~

A similar pattern appears in:

- `departments[].employees[]`: same department, same employee with role and status.
- `shipments[].packages[]`: same shipment, same package with type and weight.
- `courses[].lessons[]`: same course, same lesson with type and difficulty level.
- `bookings[].guests[]`: same booking, one guest satisfying related attributes.

### Dedicated Example with Two Nested Arrays

~~~javascript
db.teams.insertOne({
  _id: "team-1",
  groups: [
    {
      name: "operations",
      members: [
        { userId: "u-1", role: "viewer", active: true },
        { userId: "u-2", role: "admin", active: false }
      ]
    },
    {
      name: "engineering",
      members: [
        { userId: "u-3", role: "admin", active: true }
      ]
    }
  ]
})
~~~

This query **does not match** `team-1`:

~~~javascript
db.teams.find({
  groups: {
    $elemMatch: {
      name: "operations",
      members: {
        $elemMatch: {
          role: "admin",
          active: true
        }
      }
    }
  }
})
~~~

Because the operations group does not have **a member** who is both admin and active. The active admin is in engineering. Using only document-level dotted fields makes it very easy to accidentally combine attributes from different groups or members.

## 8. When Two Different Elements Must Satisfy Two Condition Sets

A single `$elemMatch` describes:

> There exists **one element** satisfying **all** conditions.

Some requirements, however, state:

> There exists an item A with qty ≥ 2 **and** there exists an item B with qty ≥ 4 in **the same order**.

These are two potentially distinct elements. You cannot put `sku: "A"` and `sku: "B"` inside the same `$elemMatch`, because a single-valued SKU field cannot equal both A and B at the same time.

### 8.1. Combining `$all` with Multiple `$elemMatch`

~~~javascript
db.orders.find(
  {
    items: {
      $all: [
        { $elemMatch: { sku: "A", qty: { $gte: 2 } } },
        { $elemMatch: { sku: "B", qty: { $gte: 4 } } }
      ]
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Result:

~~~text
ord-3
ord-5
~~~

`ord-3` has A:2 and B:4; `ord-5` has A:3 and B:7. Within each condition group, `$elemMatch` holds onto the same element; `$all` requires both condition groups to be satisfied in the array.

### 8.2. Note on “Two Different Elements”

Two separate `$elemMatch` expressions **do not inherently force two elements at different indices**. If the two condition groups overlap, **the same element can satisfy both**. In the A/B example, since an item has a single-valued SKU, item A and item B naturally must be different.

If a problem requires two distinct elements that could share the same attribute values, you need a model with element identifiers, appropriate aggregation logic, or result-set processing to verify distinctness. Do not infer that `$all + $elemMatch` automatically counts distinct elements.

### 8.3. Placing Two `$elemMatch` Inside `$and`

~~~javascript
db.orders.find({
  $and: [
    { items: { $elemMatch: { sku: "A", qty: { $gte: 2 } } } },
    { items: { $elemMatch: { sku: "B", qty: { $gte: 4 } } } }
  ]
})
~~~

For the business meaning above, this expression also requires two separate existence conditions in the array. `$all` with multiple `$elemMatch` is a direct expression using an array operator; `$and` can be useful when combining multiple other logical branches.

**Do not use a JavaScript object with two duplicate `items` keys**:

~~~javascript
// WRONG: in a JavaScript object, the second key can overwrite the first.
{
  items: { $elemMatch: { sku: "A" } },
  items: { $elemMatch: { sku: "B" } }
}
~~~

An object should never contain duplicate keys to represent two conditions; use `$and` or `$all` with proper syntax.

## 9. Empty Arrays, Missing Fields, and Negation Operators

### 9.1. `$elemMatch` Means “There Exists”

Given:

~~~javascript
{ items: [] }
~~~

no element exists to satisfy the predicate. Therefore, `items: {$elemMatch: {...}}` does not match an empty array.

If `items` is absent or is a single object instead of an array, `$elemMatch` also does not match. In practice, consider the schema: a missing field might be valid for legacy documents, or it might be a data bug that needs fixing.

### 9.2. `$ne` Outside vs. Inside `$elemMatch` Differ

Compare two intents:

**Intent A: there is no item with SKU A.**

~~~javascript
db.orders.find({
  "items.sku": { $ne: "A" }
})
~~~

In MongoDB, `$ne` on an array path typically matches when **there is no SKU A value** (and can match documents missing the relevant field). Do not read it as “there is at least one item other than A”.

**Intent B: there exists at least one item with SKU other than A.**

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $ne: "A" }
    }
  }
})
~~~

Document `ord-1` has A and B:

- Intent A: **does not match** because it has A.
- Intent B: **matches** because it has B which is not A.

In addition, `{sku: {$ne: "A"}}` can match an element **missing the `sku` field**. If business logic requires SKU to exist and differ from A, add an appropriate existence/value-type condition.

### 9.3. Ensuring “No Violating Element Exists”

This can be expressed by negating an existence condition:

~~~javascript
// No item has a negative qty.
db.orders.find({
  $nor: [
    {
      items: {
        $elemMatch: {
          qty: { $lt: 0 }
        }
      }
    }
  ]
})
~~~

This command can also match documents where `items` is missing, empty, or not an array, because no item with negative qty exists in them. If you need **both a valid array and no violating elements**, add data validation or an explicit array-type condition:

~~~javascript
db.orders.find({
  $and: [
    { items: { $type: "array" } },
    {
      $nor: [
        { items: { $elemMatch: { qty: { $lt: 0 } } } }
      ]
    }
  ]
})
~~~

`$elemMatch` represents the quantifier “**there exists**”; a “**for all elements**” condition is typically modeled as “there does not exist a violating element”, while also accounting for empty arrays and schema validity.

### 9.4. `null` and Missing Fields

For conditions like `field: null`, MongoDB's semantics include both `null` fields and, in many contexts, missing fields. Hence:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      discountCode: null
    }
  }
})
~~~

can return A items that lack the `discountCode` field, not only items explicitly assigned BSON null. If you need to distinguish them, design a consistent schema and use `$exists`, `$type`, or other explicit conditions. Do not generalize from one small example to all BSON types.

## 10. `$elemMatch` in Query vs. `$elemMatch` in Projection

This is a distinction very prone to misunderstanding.

### 10.1. `$elemMatch` in Filter Selects **Documents**

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  }
)
~~~

By default, MongoDB returns matching documents with the **entire `items` array**. `$elemMatch` in a filter **does not automatically strip the remaining items** from the returned document.

For example, `ord-5` matches because it has item A:3, yet without a projection, the output still contains both B:7 and A:3.

### 10.2. `$elemMatch` in Projection Returns Only the First Matching Element

~~~javascript
db.orders.find(
  { _id: "ord-5" },
  {
    _id: 1,
    items: {
      $elemMatch: { qty: { $gte: 3 } }
    }
  }
)
~~~

`ord-5` has both B:7 and A:3 qualifying. However, `$elemMatch` in projection puts only the **first element** in array order satisfying `qty >= 3` into the returned array. In the sample data, that is B:7.

If you want to find orders with A:3 and simultaneously display only that A item:

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  },
  {
    _id: 1,
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  }
)
~~~

Here there are **two occurrences** of `$elemMatch` with different roles:

- In the **filter**: selects documents that have at least one matching item.
- In the **projection**: keeps only the first matching element of `items` in the returned document.

Do not assume the projection's condition is automatically applied to the filter; if they differ, the results can also differ.

### 10.3. If You Need All Matching Elements: Use `$filter`

`$elemMatch` projection does not return all matching items. Use aggregation `$filter`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-5" } },
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $gte: ["$$item.qty", 3]
          }
        }
      }
    }
  }
])
~~~

The result `eligibleItems` contains **both B:7 and A:3**, in their original order. You can combine multiple same-element conditions:

~~~javascript
db.orders.aggregate([
  { $match: { _id: { $in: ["ord-2", "ord-5"] } } },
  {
    $project: {
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.sku", "A"] },
              { $gte: ["$$item.qty", 3] }
            ]
          }
        }
      }
    }
  }
])
~~~

Inside `$filter`, the conditions `$$item.sku` and `$$item.qty` both reference the element bound to variable `item`, so they also guarantee the same element. Note that `$filter` expects `input` to be an array (or null/missing per aggregation rules); if the schema contains a mistyped object like `ord-6.items`, the pipeline needs to handle the type first or exclude that document.

A defensive pattern when data has mixed types:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      eligibleItems: {
        $filter: {
          input: {
            $cond: [
              { $isArray: "$items" },
              "$items",
              []
            ]
          },
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.sku", "A"] },
              { $gte: ["$$item.qty", 3] }
            ]
          }
        }
      }
    }
  }
])
~~~

This is a safeguard when reading legacy data; for new systems, address the root cause in the schema and at write time.

## 11. Using `$unwind` When Processing Each Element as a Row

If you need to aggregate statistics, group, or output each item as a separate record, aggregation `$unwind` turns array elements into intermediate documents.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ord-1", "ord-2", "ord-3", "ord-5"] }
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "A",
      "items.qty": { $gte: 3 }
    }
  },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty",
      warehouse: "$items.warehouse"
    }
  }
])
~~~

After `$unwind`, each intermediate document represents **one item**, so the two predicates on `items.sku` and `items.qty` in the subsequent `$match` stage apply to the current item together. The output includes item A:4 from `ord-2` and A:3 from `ord-5`.

### Watch Out for Pipeline Ordering

The following can suffer from a semantic bug:

~~~javascript
// Easy mistake: matching before unwind allows different items to qualify.
db.orders.aggregate([
  {
    $match: {
      "items.sku": "A",
      "items.qty": { $gte: 3 }
    }
  },
  { $unwind: "$items" }
])
~~~

The first `$match` stage selects `ord-1` and `ord-3` by combining two different items. After `$unwind`, the pipeline can also pass non-matching items to subsequent stages if not filtered again.

A better way when early filtering optimization is needed:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      items: {
        $elemMatch: {
          sku: "A",
          qty: { $gte: 3 }
        }
      }
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "A",
      "items.qty": { $gte: 3 }
    }
  }
])
~~~

The first stage selects only documents containing an item that satisfies all conditions; the stage after `$unwind` keeps the exact matching item. When designing a pipeline, explicitly determine whether each stage operates on a **whole-array document** or a **flattened single element**.

## 12. Multikey Indexes and `$elemMatch`

MongoDB can use a **multikey index** when an indexed field contains an array. When indexing fields inside an array of objects, each element can contribute keys to the index. However, a multikey index **does not fix a semantically wrong query**: if predicates are written separately, the query can still allow them to match different elements.

### 12.1. Index for Item Queries

Suppose the workload frequently searches for orders with items by SKU and quantity:

~~~javascript
db.orders.createIndex(
  {
    "items.sku": 1,
    "items.qty": 1
  },
  { name: "idx_items_sku_qty" }
)
~~~

This is a compound multikey index on two fields originating from the same `items` array. Its goal is to support queries filtering by item SKU and qty.

Query:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}).explain("executionStats")
~~~

Under appropriate conditions, `$elemMatch` helps the query planner **compound index bounds** from two predicates on the same array element, reducing scans of unrelated keys. How bounds combine depends on **shared index key paths, query shape, and multikey bound rules**; do not assume every compound index can compound every bound.

### 12.2. Why Does `$elemMatch` Also Matter to the Optimizer?

If you write:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
})
~~~

the query means “two elements may be different”. The engine must preserve that exact semantics, so it cannot arbitrarily narrow the result set by assuming both conditions hold on one element. With `$elemMatch`, the same-element constraint is explicitly declared, giving the planner an opportunity to exploit the compound multikey index more effectively.

**Two separate benefits:**

1. **Correctness:** excludes documents that only combine conditions from different items.
2. **Potential performance:** enables index bound compounding or appropriate early filtering.

Performance gains must be measured; there is no guarantee that every query using `$elemMatch` outperforms another query across every dataset.

### 12.3. Reading `explain` Output

~~~javascript
const plan = db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}).explain("executionStats")

printjson(plan.queryPlanner.winningPlan)
printjson(plan.executionStats)
~~~

Commonly inspected fields:

| Field | Basic Meaning |
|---|---|
| `winningPlan` | Selected query execution plan |
| `IXSCAN` | A stage reading keys from an index |
| `COLLSCAN` | A stage scanning the collection |
| `FETCH` | Retrieves documents and may evaluate further predicates |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of documents returned |

A dataset with only six documents is far too small to evaluate performance: the query planner might pick `COLLSCAN` even with a valid index present. Use representative data with the same filter/sort/projection, collect measurements before and after creating the index, and measure write-time index maintenance costs.

### 12.4. Limitations of Compound Multikey Indexes

You cannot indiscriminately put multiple **independent** array fields into the same compound index; MongoDB restricts compound multikey indexes involving different array paths. Multiple subfields of the **same embedded document array** like `items.sku` and `items.qty` are a distinct pattern from fields originating from two independent arrays, such as `items[]` and `coupons[]`.

Index field order must also be based on equality, range, sort, and data distribution. Do not create indexes wholesale simply because a query has many conditions; every index increases storage footprint and write overhead.

## 13. `$elemMatch` and Element Update Operations

`$elemMatch` is a **query** operator. It selects documents matching conditions; by itself it does not update elements. When you need to modify the matching item itself, combine it with array update operators.

### 13.1. Updating the First Matching Item with Positional `$`

For example, marking item A with qty ≥ 3 on `ord-2`:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-2",
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  },
  {
    $set: { "items.$.reviewed": true }
  }
)
~~~

The positional `$` in the update path references the array element matched by the query condition per this operator's rules. This example has a simple target: one qualifying A item. In queries with multiple arrays or complex constraints, positional `$` has limitations and can be error-prone; consider `arrayFilters` when you need to pinpoint multiple elements accurately.

### 13.2. Using `arrayFilters` to Choose Elements to Update

~~~javascript
db.orders.updateOne(
  { _id: "ord-5" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "A",
        "line.qty": { $gte: 3 }
      }
    ]
  }
)
~~~

Here `line` is an identifier variable representing an element of `items`. Both `line.sku` and `line.qty` inside the same array filter apply to **one item**. The `$[line]` update construct can target every element satisfying the filter, unlike positional `$` which normally targets only the first matching element.

**Distinguish three roles:**

- `$elemMatch` in the filter: which documents qualify to be processed?
- Positional `$` or `$[line]` in the update path: which elements get modified?
- `arrayFilters`: constraints on the element corresponding to the identifier in the update path.

If you query `{items: {$elemMatch: {...}}}` but only run `$set: {status: "UPDATED"}`, you only change the document-level `status` field; the items themselves are not modified.

### 13.3. Ensuring Correctness Under Concurrent Updates

In real order processing, checking `qty >= 3` prior to an update is not enough for operations with competing concurrent requests. If an update touches inventory or monetary amounts, use appropriate atomic conditions, inspect `matchedCount/modifiedCount`, and design transactions when multiple documents must change together. `$elemMatch` solves **same-element semantics**, not concurrency across requests.

## 14. Array Queries in the Java Driver

When writing applications in Java, the MongoDB Java Driver provides equivalent builders. The example below assumes `database` is a `MongoDatabase` created from an appropriate `MongoClient`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

MongoCollection<Document> orders = database.getCollection("orders");

Bson filter = Filters.elemMatch(
    "items",
    Filters.and(
        Filters.eq("sku", "A"),
        Filters.gte("qty", 3),
        Filters.eq("warehouse", "HCM")
    )
);

for (Document order : orders.find(filter)) {
    System.out.println(order.getString("_id"));
}
~~~

Notice that conditions inside `Filters.elemMatch("items", ...)` use the item's field names **`sku`, `qty`, `warehouse`**, rather than prefixing each field with `items.`. This corresponds to:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      warehouse: "HCM"
    }
  }
}
~~~

In Spring Data MongoDB, the query-building API differs from the raw Java Driver, but the goal is identical. Ensure the DSL you use emits a MongoDB filter containing `$elemMatch` at the right array path, rather than assembling two independent dotted-field conditions. You do not need to depend on a specific framework to understand the semantics.

## 15. Designing Schemas So `$elemMatch` Is Easy to Use and Reliable

Even a correct query can be hard to maintain if documents contain oversized arrays, heterogeneous elements, or nested data lacking conventions.

### 15.1. Each Element Should Be a Clear Business Unit

Example order item:

~~~javascript
{
  sku: "A",
  qty: 4,
  price: NumberDecimal("150000.00"),
  warehouse: "HCM"
}
~~~

Since `sku` and `qty` are both attributes of one item, placing them in the **same element object** allows the application to query and update atomically at the document level while making same-element conditions easy to express.

### 15.2. Avoid Parallel Arrays

Anti-pattern:

~~~javascript
{
  skus: ["A", "B"],
  quantities: [1, 5]
}
~~~

The application must implicitly know that index 0 in `skus` corresponds to index 0 in `quantities`. `$elemMatch` on `skus` cannot directly constrain the value at the same position in an independent `quantities` array. When one array has elements added or removed out of sync, the data loses correlation.

Clearer model:

~~~javascript
{
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 5 }
  ]
}
~~~

### 15.3. Cap Array Sizes

A single BSON document has a 16 MiB limit. If `items`, `events`, or `measurements` grow unboundedly, embedding all of them in one document makes queries and updates heavy and risks hitting the size limit. For arrays with high growth, consider splitting into a child collection, using a bounded bucket pattern, or choosing an appropriate time-series model.

### 15.4. Validation Keeps Results Predictable

Example new collection requiring `items` to always be an array, with each item being an object containing a string `sku` and non-negative integer `qty`:

~~~javascript
db.createCollection("orders_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["items"],
      properties: {
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["sku", "qty"],
            properties: {
              sku: { bsonType: "string", minLength: 1 },
              qty: {
                bsonType: ["int", "long"],
                minimum: 0
              }
            }
          }
        }
      }
    }
  },
  validationAction: "error"
})
~~~

This is a **different** collection from `orders` containing the demo data (which intentionally has mistyped `ord-6`). In applications, BSON numeric types must match how the driver writes data. The validator should also consider whether empty arrays are allowed, whether SKU must be unique within the array, and schema migration policies.

## 16. When Is `$elemMatch` Not the Primary Tool?

Do not reach for `$elemMatch` for every array question just because the data contains an array.

| Problem | Primary Tool | Reason |
|---|---|---|
| An item satisfies multiple conditions | Query `$elemMatch` | Guarantees the same element |
| A value exists in an array | Direct equality, `$in`, or `$elemMatch` depending on schema | A single predicate usually does not need same-element grouping |
| Array contains all given values | `$all` | Requires values to coexist, not on the same element |
| Two separate item types coexist | Multiple `$elemMatch` via `$all` / `$and` | Two condition groups may belong to different items |
| Return **one** first matching element | Projection `$elemMatch` | Limits the displayed element |
| Return **all** matching elements | Aggregation `$filter` | Iterates/filters each element |
| Aggregate per item or group by item | `$unwind`, `$match`, `$group` | Turns items into pipeline inputs |
| Update elements matching conditions | `$[identifier]` with `arrayFilters` | Selects elements to modify |
| Compare positions or complex element pairs | Aggregation or data model redesign | Needs logic beyond an existence check |
| Huge arrays queried independently per item | Child collection with indexes | Document limits, update cost, and access patterns |

## 17. Common Mistakes

### Mistake 1 — Assuming Two Dotted Predicates Target the Same Item

~~~javascript
{
  "items.sku": "A",
  "items.qty": { $gte: 3 }
}
~~~

This query can wrongly return `ord-1` and `ord-3` for the requirement “A qty ≥ 3”. Fix it with `items: {$elemMatch: {sku:"A", qty:{$gte:3}}}`.

### Mistake 2 — Using `$and` Still Outside `$elemMatch`

~~~javascript
{
  $and: [
    { "items.sku": "A" },
    { "items.qty": { $gte: 3 } }
  ]
}
~~~

`$and` does not bind the two conditions to the same item.

### Mistake 3 — Using Two Separate `$elemMatch` When One Element Is Intended

~~~javascript
{
  $and: [
    { items: { $elemMatch: { sku: "A" } } },
    { items: { $elemMatch: { qty: { $gte: 3 } } } }
  ]
}
~~~

This can match A and qty from **two different items**. When the same item is required, merge both predicates **into one `$elemMatch`**.

### Mistake 4 — Thinking Query `$elemMatch` Trims the Returned Array

A query with `$elemMatch` only selects documents; to filter returned elements, you need projection or aggregation.

### Mistake 5 — Using Projection `$elemMatch` to Fetch All Qualifying Items

Projection `$elemMatch` returns only the **first element**. If you want all matching items, use `$filter`.

### Mistake 6 — Treating an Empty Array as Having a Satisfying Element

With no items, `$elemMatch` does not match. In particular, a “every item is valid” rule must explicitly specify whether empty arrays are accepted.

### Mistake 7 — Treating Negation Operators Like Positive Existence Operators

`"items.sku": {$ne:"A"}` can mean contains no A, whereas `items:{$elemMatch:{sku:{$ne:"A"}}}` means there exists an item that is not A. Write conditions according to your exact intent.

### Mistake 8 — Writing the Right Query Predicate with the Wrong Index

A single index on `items.sku` may not sufficiently optimize queries that also filter by `qty`, while a compound index adds write overhead. Measure with `explain` on real data instead of guessing from index counts.

### Mistake 9 — Relying Only on a Single-Item Sample Document

If every test order has only one item, dotted predicates and `$elemMatch` can return identical results, masking the bug. Tests must include **two items where each satisfies half the conditions**.

### Mistake 10 — Forgetting Mixed Schemas

A document containing `items` as a single object can match dot notation while failing `$elemMatch`. You need schema validation, migrations, or explicit legacy data handling.

## 18. Practice Exercises: Write Queries and Predict Results

Use `db.orders` created at the beginning of the lesson. Before each command, **predict which IDs will be returned**, then run it in mongosh to observe.

### Exercise 1 — Basic Same-Element Condition

Find orders with an item `sku = "A"` and `qty >= 3`. Write two queries: one using dot notation and one using `$elemMatch`. Explain why the results differ.

**Hint:** `ord-1` has A:1 and B:5; this is the test case distinguishing the two forms.

### Exercise 2 — Three Conditions on the Same Item

Find orders with item B, qty ≥ 4, warehouse HCM. Do not mix SKU from one item with warehouse from another item. Return the order `_id`.

### Exercise 3 — Range Condition on a Scalar Array

Find orders with **one** `scores` value in the range `[80, 90)`. Compare the result with a query that omits `$elemMatch`.

### Exercise 4 — Same Nested Object

Find orders with item A, qty ≥ 3, `options.color = "red"`, and `options.size = "M"`.

### Exercise 5 — Nested Arrays

Find orders with item A qty ≥ 3 and an active VIP promotion **on that same item A**.

### Exercise 6 — Two Element Groups

Find orders with item A qty ≥ 2 **and** item B qty ≥ 4. Explain why two separate existence condition groups are required.

### Exercise 7 — Negation

Write queries for two requirements:

1. Contains no item with `sku = "A"`.
2. Has at least one item with `sku != "A"`.

Check against `ord-1` and explain the difference.

### Exercise 8 — Projection

Query `ord-5` and return only the first item with qty ≥ 3 using projection. Then use `$filter` to return **all** items with qty ≥ 3.

### Exercise 9 — Queries and Indexes

Create the index `{"items.sku":1, "items.qty":1}`, and compare `explain("executionStats")` for the query with `$elemMatch` and the query using dot notation. Do not declare an index winner on a tiny dataset; instead point out `winningPlan` and the numbers of keys/documents examined.

### Exercise 10 — API Design

Suppose you have the API:

~~~http
GET /orders?sku=A&minQty=3&warehouse=HCM
~~~

Write the correct MongoDB query and a test suite covering:

- Has A:1 and B:5 at HCM.
- Has A:3 at HCM.
- Has A:3 at HN and B:5 at HCM.
- Has A:3 at HCM where the item also contains an unrelated options object.
- `items` is empty or the field is missing.

Explain which cases must be returned and why.

## 19. Reference Solutions for the Sample Dataset

### Exercise 1

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}, { _id: 1 })
~~~

Same-element results: `ord-2`, `ord-5`. Dot notation alone can additionally return `ord-1`, `ord-3`, and `ord-6`.

### Exercise 2

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "B",
      qty: { $gte: 4 },
      warehouse: "HCM"
    }
  }
}, { _id: 1 })
~~~

Results: `ord-3`, `ord-5`. `ord-1` has B:5, but at HN.

### Exercise 3

~~~javascript
db.orders.find({
  scores: {
    $elemMatch: {
      $gte: 80,
      $lt: 90
    }
  }
}, { _id: 1 })
~~~

Results: `ord-2`, `ord-3`. Omitting `$elemMatch` can also return `ord-1`.

### Exercise 4

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      "options.color": "red",
      "options.size": "M"
    }
  }
}, { _id: 1 })
~~~

Result: `ord-2`.

### Exercise 5

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      promotions: {
        $elemMatch: {
          code: "VIP",
          active: true
        }
      }
    }
  }
}, { _id: 1 })
~~~

Result: `ord-2`.

### Exercise 6

~~~javascript
db.orders.find({
  items: {
    $all: [
      { $elemMatch: { sku: "A", qty: { $gte: 2 } } },
      { $elemMatch: { sku: "B", qty: { $gte: 4 } } }
    ]
  }
}, { _id: 1 })
~~~

Results: `ord-3`, `ord-5`.

### Exercise 7

~~~javascript
// No item A.
db.orders.find({
  $nor: [
    { items: { $elemMatch: { sku: "A" } } }
  ]
})

// Exists an item with sku other than A.
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $ne: "A" }
    }
  }
})
~~~

`ord-1` fails the first query but satisfies the second query. The first query can include documents missing the array or holding a single object, because no array element carrying SKU A is found; if only valid arrays are permitted, add a type/schema constraint.

### Exercise 8

~~~javascript
db.orders.find(
  { _id: "ord-5" },
  {
    items: {
      $elemMatch: {
        qty: { $gte: 3 }
      }
    }
  }
)
~~~

Projection `$elemMatch` yields only element B:7 (first in the array). Aggregation `$filter` with `qty >= 3` yields both B:7 and A:3.

### Exercise 9

There is no mandatory `IXSCAN`/`COLLSCAN` figure on the demo dataset. Results depend on the query planner and environment; compare `totalKeysExamined`, `totalDocsExamined`, `nReturned`, index definitions, and realistic load levels.

### Exercise 10

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      warehouse: "HCM"
    }
  }
})
~~~

Only orders with **one item A qty ≥ 3 at HCM** are returned. Having another B:5 item at HCM in the same document does not make A:1 or A:3 at HN valid.

## 20. Quick Syntax Reference Summary

| Need | Query / Pipeline Pattern |
|---|---|
| One item has A and qty ≥ 3 | `{items: {$elemMatch: {sku:"A", qty:{$gte:3}}}}` |
| One score in [80, 90) | `{scores: {$elemMatch: {$gte:80, $lt:90}}}` |
| Same item has color red | `{items: {$elemMatch: {sku:"A", "options.color":"red"}}}` |
| Item A has active VIP promotion | `{items: {$elemMatch: {sku:"A", promotions:{$elemMatch:{code:"VIP",active:true}}}}}` |
| Has one item A and one item B under separate conditions | `{items: {$all: [{$elemMatch:{sku:"A"}}, {$elemMatch:{sku:"B"}}]}}` |
| Select documents while keeping full array on return | `find({items: {$elemMatch: {...}}})` |
| Return only the first matching element | `find(filter, {items: {$elemMatch: {...}}})` |
| Return all matching elements | Aggregation `$project` + `$filter` |
| Unpack each element for analysis | Aggregation `$unwind` then `$match` |
| Update matching elements | Positional `$` or `$[identifier]` with `arrayFilters` |
| Optimize item lookup by SKU/qty | Appropriate compound multikey index + measure `explain` |

The key takeaway is: **one condition on an array field may be true due to one element, while another condition may be true due to a different element**. When business semantics require all predicates to hold simultaneously on **a single element**, place them inside **one `$elemMatch`**. Choosing the right operator both protects query correctness and gives MongoDB the opportunity to leverage an appropriate multikey index. Then select projection, aggregation, or arrayFilters depending on whether your goal is **returning elements**, **aggregating elements**, or **updating elements**; do not conflate those tasks with document filtering.
