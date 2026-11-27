# Combining Conditions with $and, $or, $nor, and $not in MongoDB

In MongoDB, document queries frequently need to evaluate **multiple conditions simultaneously**: finding products that are active **and** in stock; retrieving orders in either of two states; excluding disallowed records; or negating a specific comparison. The four logical query operators—**`$and`**, **`$or`**, **`$nor`**, and **`$not`**—let you express these rules directly in the filter of `find()`, `countDocuments()`, `updateMany()`, and the `$match` aggregation stage.

This lesson shows how to read logical expressions, write valid syntax, nest operators, handle absent fields, avoid JavaScript object-merging bugs when composing filters, and evaluate the impact on indexes and performance.

## 1. Logical Thinking Before Writing a Query

Suppose:

- **A**: product has `category = "laptop"`.
- **B**: product has `stock > 0`.

We want to express different rules:

| Rule | Interpretation | MongoDB Operator |
| --- | --- | --- |
| A **and** B | Return only laptops that are in stock | `$and` or implicit AND conditions |
| A **or** B | Return laptops, or any product that is in stock | `$or` |
| **Not** (A or B) | Exclude all laptops and all products in stock | `$nor` |
| **Not** B | Return documents that do not satisfy `stock > 0` | `$not` placed on the `stock` field; watch out for missing fields |

Two-variable truth table, where **1** is true and **0** is false:

| A | B | A AND B | A OR B | NOR(A, B) | NOT A |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 1 | 1 |
| 0 | 1 | 0 | 1 | 0 | 1 |
| 1 | 0 | 0 | 1 | 0 | 0 |
| 1 | 1 | 1 | 1 | 0 | 0 |

Key points about MongoDB syntax:

- **`$and`, `$or`, `$nor`** accept **an array of filter expressions**. Each element can contain one or more conditions.
- **`$not`** is a **field-level operator**, placed inside a single field's condition to negate the operator expression applied to that field. It is not a top-level operator for negating an entire filter.
- MongoDB **implicitly ANDs** conditions with different keys in the same query object. Therefore, many queries do not need an explicit `$and`.
- Query logic follows MongoDB document-matching semantics; in particular, **a missing field** can cause certain negated conditions to match. Never assume every field is present.

## 2. Creating a Consistent Practice Dataset

Open `mongosh` and run the following command block in a dedicated database:

~~~javascript
var logicDb = db.getSiblingDB("mongo_query_logic_lab");

logicDb.products.drop();
logicDb.products.insertMany([
  {
    _id: "p01",
    name: "Laptop Alpha",
    category: "laptop",
    price: 1500,
    stock: 5,
    status: "active",
    brand: "ACME",
    rating: 4.7,
    tags: ["tech", "featured"]
  },
  {
    _id: "p02",
    name: "Laptop Beta",
    category: "laptop",
    price: 900,
    stock: 0,
    status: "active",
    brand: "Zen",
    rating: 4.3,
    tags: ["tech"]
  },
  {
    _id: "p03",
    name: "Phone Alpha",
    category: "phone",
    price: 700,
    stock: 12,
    status: "active",
    brand: "ACME",
    rating: 4.6,
    tags: ["tech", "sale"]
  },
  {
    _id: "p04",
    name: "Phone Beta",
    category: "phone",
    price: 1200,
    stock: 2,
    status: "draft",
    brand: "Zen",
    rating: 4.8,
    tags: ["premium"]
  },
  {
    _id: "p05",
    name: "MongoDB Handbook",
    category: "book",
    price: 40,
    stock: 30,
    status: "active",
    brand: "Books",
    rating: 4.9,
    tags: ["education"]
  },
  {
    _id: "p06",
    name: "Laptop Pro",
    category: "laptop",
    price: 2200,
    stock: 1,
    status: "archived",
    brand: "ACME",
    rating: 4.5,
    tags: ["premium"]
  },
  {
    _id: "p07",
    name: "USB Cable",
    category: "accessory",
    price: 120,
    stock: 0,
    status: "active",
    brand: "Value",
    rating: 3.8,
    tags: ["sale"]
  },
  {
    _id: "p08",
    name: "Budget Phone",
    category: "phone",
    price: 500,
    stock: 7,
    status: "active",
    // Intentionally omit brand and rating.
    tags: ["budget"]
  },
  {
    _id: "p09",
    name: "Phone Case",
    category: "accessory",
    price: 90,
    stock: 15,
    // Intentionally omit status.
    brand: "Zen",
    rating: 4.0,
    tags: ["sale"]
  }
]);
~~~

The two types of missing fields in `p08` and `p09` help demonstrate negation behavior in MongoDB. Every document still has `_id`, `category`, `price`, and `stock`.

To quickly view the list of `_id` values matching a filter, define a helper function for the examples:

~~~javascript
function ids(filter) {
  return logicDb.products
    .find(filter, { _id: 1 })
    .sort({ _id: 1 })
    .toArray()
    .map(document => document._id);
}

ids({}); // p01 through p09
~~~

To inspect full documents instead of just `_id`, call `logicDb.products.find(filter)` directly. The results listed in this lesson apply to the **initial dataset**, before any update operations are executed.

## 3. The $and Operator: All Conditions Must Be True

### 3.1. Syntax and Interpretation

Syntax:

~~~javascript
{
  $and: [
    { conditionA },
    { conditionB },
    { conditionC }
  ]
}
~~~

Every expression in the array must match for a document to be returned. Example: "laptops priced at 1,000 or more **and** in stock":

~~~javascript
ids({
  $and: [
    { category: "laptop" },
    { price: { $gte: 1000 } },
    { stock: { $gt: 0 } }
  ]
});
// ["p01", "p06"]
~~~

`p02` is a laptop, but it costs 900 and is out of stock. Both `p01` and `p06` satisfy all three conditions even though `p06` has status `archived`; the query **does not require** any specific status, so `p06` is still returned.

To retrieve only active laptops:

~~~javascript
ids({
  $and: [
    { category: "laptop" },
    { price: { $gte: 1000 } },
    { stock: { $gt: 0 } },
    { status: "active" }
  ]
});
// ["p01"]
~~~

### 3.2. Implicit AND in a Single Object

MongoDB applies an **implicit AND** to different fields appearing at the same level in a filter. The query above can be written more concisely:

~~~javascript
ids({
  category: "laptop",
  price: { $gte: 1000 },
  stock: { $gt: 0 },
  status: "active"
});
// ["p01"]
~~~

Both forms express the same rule. When conditions are simple and target different fields, implicit AND is usually easier to read.

### 3.3. Multiple Conditions on the Same Field

To get products priced between 700 and 1,500, both bounds must hold simultaneously:

~~~javascript
ids({
  price: { $gte: 700, $lte: 1500 }
});
// ["p01", "p02", "p03", "p04"]
~~~

This can also be written with explicit `$and`:

~~~javascript
ids({
  $and: [
    { price: { $gte: 700 } },
    { price: { $lte: 1500 } }
  ]
});
// ["p01", "p02", "p03", "p04"]
~~~

The first form is more concise for different operators on the same field. `$and` is useful when combining complex query branches or avoiding duplicate object keys.

### 3.4. Do Not Repeat Keys in a JavaScript Object

The example below **does not express both conditions at once**:

~~~javascript
// WRONG in intent: JavaScript only keeps the value of the last price key.
var wrongFilter = {
  price: { $gte: 700 },
  price: { $lte: 1500 }
};
~~~

In a plain JavaScript object, the `price` key is duplicated; the later property overwrites the earlier one. As a result, only the `$lte: 1500` condition remains.

Correct ways:

~~~javascript
// Combine both operators under the same field.
var correctFilter = {
  price: { $gte: 700, $lte: 1500 }
};

// Or use an $and array.
var anotherCorrectFilter = {
  $and: [
    { price: { $gte: 700 } },
    { price: { $lte: 1500 } }
  ]
};
~~~

The same bug can happen when merging two objects that both contain `$or` or `$and` via object spread: the later condition overwrites the earlier one. The nested conditions section shows how to fix this.

## 4. The $or Operator: At Least One Branch Must Be True

### 4.1. Syntax

~~~javascript
{
  $or: [
    { conditionA },
    { conditionB },
    { conditionC }
  ]
}
~~~

MongoDB returns a document if **at least one** expression in the array matches. `$or` is an inclusive OR: documents satisfying **both branches** are also included.

Example: "phones **or** out-of-stock products":

~~~javascript
ids({
  $or: [
    { category: "phone" },
    { stock: 0 }
  ]
});
// ["p02", "p03", "p04", "p07", "p08"]
~~~

Explanation:

- `p03`, `p04`, and `p08` are phones.
- `p02` and `p07` are not phones, but have `stock: 0`.
- If a document is both a phone and out of stock, it still appears **only once** in the result of `find()`.

### 4.2. Combining a Fixed Condition with $or

Problem: "**active** products in **laptop or phone**". Write:

~~~javascript
ids({
  status: "active",
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});
// ["p01", "p02", "p03", "p08"]
~~~

The `status: "active"` condition combines via implicit AND with the result of the entire `$or`. It reads as:

~~~text
status = active
AND
(category = laptop OR category = phone)
~~~

`p04` is a phone, but `draft`; `p06` is a laptop, but `archived`. Neither matches. `p09` lacks `status`, so it does not match either.

### 4.3. When OR Checks the Same Field: Consider $in

When multiple branches compare **the same field against different values**, `$in` is usually more concise:

~~~javascript
// Written with $or.
ids({
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});

// Written with $in, equivalent in this example.
ids({
  category: { $in: ["laptop", "phone"] }
});
// ["p01", "p02", "p03", "p04", "p06", "p08"]
~~~

Use `$or` when branches involve different fields or each branch has its own structure. Example: "phones priced under 600 **or** laptops priced over 2,000":

~~~javascript
ids({
  $or: [
    { category: "phone", price: { $lt: 600 } },
    { category: "laptop", price: { $gt: 2000 } }
  ]
});
// ["p06", "p08"]
~~~

Each element of the `$or` array is a **complete filter object**. In the first branch, `category: "phone"` and `price: { $lt: 600 }` are joined by implicit AND.

### 4.4. OR Does Not Guarantee Result Order

Logical operators determine **which documents match**, not the order in which they are returned. When deterministic ordering is needed for pagination or testing, use `sort()`:

~~~javascript
logicDb.products
  .find({
    $or: [
      { category: "laptop" },
      { category: "phone" }
    ]
  })
  .sort({ price: 1, _id: 1 })
  .toArray();
~~~

Here `price: 1` sorts ascending and `_id: 1` acts as a tie-breaker when two products have the same price.

## 5. The $nor Operator: No Branch May Be True

### 5.1. Syntax and Negated-OR Meaning

Syntax:

~~~javascript
{
  $nor: [
    { conditionA },
    { conditionB }
  ]
}
~~~

The `$nor` operator matches when **none of the sub-expressions match**, corresponding to:

~~~text
NOR(A, B) = NOT (A OR B)
          = (NOT A) AND (NOT B)
~~~

Example: "neither a phone **nor** out of stock":

~~~javascript
ids({
  $nor: [
    { category: "phone" },
    { stock: 0 }
  ]
});
// ["p01", "p05", "p06", "p09"]
~~~

`p02` and `p07` are excluded for being out of stock; `p03`, `p04`, and `p08` are excluded for being phones. The remaining documents satisfy both negated conditions.

### 5.2. A Single $nor Branch Can Contain Multiple AND Conditions

Problem: "exclude products that are **both active and priced at least 1,000**", while keeping everything else.

~~~javascript
ids({
  $nor: [
    {
      status: "active",
      price: { $gte: 1000 }
    }
  ]
});
// ["p02", "p03", "p04", "p05", "p06", "p07", "p08", "p09"]
~~~

Only `p01` is excluded, because `p01` satisfies **both** conditions inside that single branch.

**Do not confuse** this with the following query:

~~~javascript
ids({
  $nor: [
    { status: "active" },
    { price: { $gte: 1000 } }
  ]
});
~~~

The second query excludes **every active product** **or** **every product priced 1,000 or higher**—a much broader exclusion. Placing conditions inside a single `$nor` element versus separate `$nor` elements changes the meaning completely.

### 5.3. $nor and Missing Fields

Normally, a condition such as `{ rating: { $gte: 4.5 } }` **does not match** documents missing `rating`. When negated with `$nor`, documents missing the field can be retained:

~~~javascript
ids({
  $nor: [
    { rating: { $gte: 4.5 } }
  ]
});
// ["p02", "p07", "p08", "p09"]
~~~

`p08` is missing `rating`, yet it is still returned. If the requirement is "**has a rating** and the rating is **below 4.5**", require the field to exist or use the appropriate comparison directly:

~~~javascript
ids({
  rating: { $lt: 4.5 }
});
// ["p02", "p07", "p09"]
~~~

Here `$lt` with a numeric value does not match documents missing the field. When you need to negate a complex condition while restricting to documents that contain the field, combine `$exists: true` with the negated expression.

**Important exception to understand:** If the element inside `$nor` is itself `{ rating: { $exists: false } }`, then `$nor` returns only documents that **have the rating field**, because it negates the "field does not exist" condition:

~~~javascript
ids({
  $nor: [
    { rating: { $exists: false } }
  ]
});
// ["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p09"]
~~~

Therefore, do not memorize mechanically that "`$nor` always includes documents missing the field." The result depends on the **actual sub-condition being negated**.

## 6. The $not Operator: Negating a Field-Level Condition

### 6.1. Where Is $not Placed?

The `$not` operator has the form:

~~~javascript
{
  fieldName: {
    $not: {
      $someOperator: someValue
    }
  }
}
~~~

Or with a regular expression, `$not` can be used directly with a regex. `$not` applies to **a single field's condition**, unlike `$nor`, which is a filter-level operator taking expression branches.

Example finding products **not priced greater than 1,000**:

~~~javascript
ids({
  price: {
    $not: { $gt: 1000 }
  }
});
// ["p02", "p03", "p05", "p07", "p08", "p09"]
~~~

Every product has `price`, so the result set matches `price <= 1000` in the current dataset. However, the two forms **are not completely equivalent when the field is missing or has another data type**, because `$not` also matches documents lacking the field.

### 6.2. $not with $gte and Missing Fields

Find products **without a rating of 4.5 or higher**:

~~~javascript
ids({
  rating: {
    $not: { $gte: 4.5 }
  }
});
// ["p02", "p07", "p08", "p09"]
~~~

`p08` is returned because it **does not have the rating field**. If you only want products that **have a rating** below 4.5:

~~~javascript
ids({
  $and: [
    { rating: { $exists: true } },
    { rating: { $not: { $gte: 4.5 } } }
  ]
});
// ["p02", "p07", "p09"]
~~~

For simple conditions, writing `rating: { $lt: 4.5 }` is clearer. Separating `$exists` above illustrates negation semantics.

### 6.3. $not with Regular Expressions

Find products whose `brand` **does not start with the letter A**:

~~~javascript
ids({
  brand: {
    $not: /^A/
  }
});
// ["p02", "p04", "p05", "p07", "p08", "p09"]
~~~

Or using `$regex` syntax:

~~~javascript
ids({
  brand: {
    $not: { $regex: "^A" }
  }
});
// ["p02", "p04", "p05", "p07", "p08", "p09"]
~~~

`p01`, `p03`, and `p06` have brand `"ACME"` and are excluded. `p08` **has no brand**, yet still matches the negated condition. If the requirement is "brand is declared and does not start with A", add `{ brand: { $exists: true } }` inside an `$and` clause.

### 6.4. $not Does Not Replace Document-Wide Negation

An **invalid operator placement** example:

~~~javascript
// WRONG: $not is not a root-level filter operator.
{
  $not: {
    status: "active",
    stock: { $gt: 0 }
  }
}
~~~

To negate **a multi-field expression**, use `$nor` with a single branch:

~~~javascript
// NOT (status = active AND stock > 0)
{
  $nor: [
    {
      status: "active",
      stock: { $gt: 0 }
    }
  ]
}
~~~

If you want to negate **each individual condition** and then combine them, express the logical formula accurately. You cannot arbitrarily convert a field-level `$not` into a multi-branch `$nor` without checking the meaning.

### 6.5. Comparing $not, $ne, and $nin

MongoDB provides dedicated operators for simple negations:

~~~javascript
// Status value is not equal to active.
ids({ status: { $ne: "active" } });
// ["p04", "p06", "p09"]

// Status is not one of active or draft.
ids({ status: { $nin: ["active", "draft"] } });
// ["p06", "p09"]

// Another way to express negation of equality on status.
ids({ status: { $not: { $eq: "active" } } });
// ["p04", "p06", "p09"]
~~~

In these examples, `p09` lacks `status`, yet still matches the negated operators. If you want to restrict to documents that **have a status**, explicitly add `status: { $exists: true }` to the query structure.

**Practical rule of thumb:** use `$ne` for "not equal to one value", `$nin` for "not in a list", `$not` when negating a field operator (especially regex), and `$nor` when negating one or more filter branches.

## 7. Nesting Operators to Express Business Rules

Most real-world queries require more than one operator. Start with **logical parentheses in plain words**, then translate them into MongoDB expressions.

### 7.1. A AND (B OR C)

Requirement: retrieve only **active** products with **stock > 0** belonging to **laptop or phone**.

~~~text
(status = active)
AND (stock > 0)
AND (category = laptop OR category = phone)
~~~

MongoDB:

~~~javascript
ids({
  status: "active",
  stock: { $gt: 0 },
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});
// ["p01", "p03", "p08"]
~~~

`p02` is an active laptop but out of stock; `p04` is an in-stock phone but draft; `p06` is an in-stock laptop but archived.

For two values on the same `category` field, this can also be written concisely:

~~~javascript
ids({
  status: "active",
  stock: { $gt: 0 },
  category: { $in: ["laptop", "phone"] }
});
// ["p01", "p03", "p08"]
~~~

### 7.2. (A OR B) AND (C OR D)

Requirement: products in laptop or phone, **and** having brand ACME or more than 5 units in stock.

~~~text
(category = laptop OR category = phone)
AND
(brand = ACME OR stock > 5)
~~~

MongoDB:

~~~javascript
ids({
  $and: [
    {
      $or: [
        { category: "laptop" },
        { category: "phone" }
      ]
    },
    {
      $or: [
        { brand: "ACME" },
        { stock: { $gt: 5 } }
      ]
    }
  ]
});
// ["p01", "p03", "p06", "p08"]
~~~

You must use `$and` containing **two separate `$or` clauses**. The snippet below causes a logic bug in JavaScript because the two `$or` keys collide:

~~~javascript
// WRONG: the second $or overwrites the first.
var wrongNestedFilter = {
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ],
  $or: [
    { brand: "ACME" },
    { stock: { $gt: 5 } }
  ]
};
~~~

Never run this condition in production without noticing the bug: the final filter keeps only the brand/stock branch and can leak documents outside the intended category group.

### 7.3. NOT (A OR B)

Requirement: products that are neither phones **nor** out of stock.

~~~javascript
ids({
  $nor: [
    { category: "phone" },
    { stock: 0 }
  ]
});
// ["p01", "p05", "p06", "p09"]
~~~

`$nor` directly expresses `NOT (A OR B)`. When a field can be absent, decide explicitly whether to keep those documents in the result.

### 7.4. NOT (A AND B)

Requirement: exclude products that are **both active and priced greater than or equal to 1,000**.

~~~javascript
ids({
  $nor: [
    {
      status: "active",
      price: { $gte: 1000 }
    }
  ]
});
// ["p02", "p03", "p04", "p05", "p06", "p07", "p08", "p09"]
~~~

The negation of **A AND B** is equivalent to **NOT A OR NOT B** by De Morgan's laws. Writing a `$nor` clause with a single implicit-AND branch is usually clearer in this example.

### 7.5. Exclusive Conditions Inside $or

Requirement: select **active** laptops priced at most 1,000, or **active** phones with stock of at least 10.

~~~javascript
ids({
  $or: [
    {
      category: "laptop",
      status: "active",
      price: { $lte: 1000 }
    },
    {
      category: "phone",
      status: "active",
      stock: { $gte: 10 }
    }
  ]
});
// ["p02", "p03"]
~~~

Each branch is a set of conditions joined by implicit AND; the entire array is ORed. Each price or stock condition applies only to **its own branch**.

If you move `price` and `stock` outside `$or` without checking the logic, the query changes meaning: it could force **both laptops and phones** to satisfy the same condition.

## 8. $and, $or, $nor, and $not with Arrays

MongoDB can evaluate array fields **element by element** across many query operators. The sample dataset has `tags` as an array of strings:

~~~javascript
// At least one tags element equals "sale".
ids({ tags: "sale" });
// ["p03", "p07", "p09"]
~~~

When negating, distinguish between "no element satisfies" and "another element satisfies". For example:

~~~javascript
// Does not contain the "sale" tag.
ids({
  tags: { $ne: "sale" }
});
// ["p01", "p02", "p04", "p05", "p06", "p08"]

// Negate the condition containing the "sale" tag with $nor.
ids({
  $nor: [
    { tags: "sale" }
  ]
});
// ["p01", "p02", "p04", "p05", "p06", "p08"]
~~~

Both queries produce the same result on the current dataset. If a document later **lacks `tags`**, the negated condition can also match that document. To restrict to documents with a `tags` array, verify field existence and data type.

With **arrays of objects**, when multiple conditions must hold **on the same element**, you must use `$elemMatch`. For example, suppose a document has:

~~~javascript
{
  _id: "example",
  variants: [
    { color: "red", stock: 0 },
    { color: "blue", stock: 5 }
  ]
}
~~~

The following condition can match even when the two criteria appear in **two different elements**:

~~~javascript
{
  "variants.color": "red",
  "variants.stock": { $gt: 0 }
}
~~~

To require a single variant to be **both red and in stock**:

~~~javascript
{
  variants: {
    $elemMatch: {
      color: "red",
      stock: { $gt: 0 }
    }
  }
}
~~~

To find documents that **have no red in-stock variant**, negate the `$elemMatch` expression using `$nor`:

~~~javascript
{
  $nor: [
    {
      variants: {
        $elemMatch: {
          color: "red",
          stock: { $gt: 0 }
        }
      }
    }
  ]
}
~~~

This example illustrates a filter for a collection containing a `variants` field; it is **not** a query against the `products` dataset in Section 2. Documents missing `variants` can also be returned by the negation above; add constraints if business logic rejects missing fields.

## 9. Applying Logical Filters in MongoDB Operations

### 9.1. Counting Documents

You can pass the same filter to `countDocuments()`:

~~~javascript
logicDb.products.countDocuments({
  status: "active",
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});
// 4
~~~

The four documents are `p01`, `p02`, `p03`, and `p08`.

### 9.2. Using in Aggregation $match

Logical conditions inside a `$match` stage share the same syntax as `find()` filters:

~~~javascript
logicDb.products.aggregate([
  {
    $match: {
      status: "active",
      stock: { $gt: 0 },
      $or: [
        { category: "laptop" },
        { category: "phone" }
      ]
    }
  },
  {
    $group: {
      _id: "$category",
      productCount: { $sum: 1 },
      totalStock: { $sum: "$stock" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

The input to `$group` consists of `p01` (laptop, stock 5), `p03` (phone, stock 12), and `p08` (phone, stock 7). Expected result: laptop has **1 product / total stock 5**, phone has **2 products / total stock 19**.

Inside `$match`, `$and`/`$or`/`$nor`/`$not` act as **query language** operators. When you need logic over **computed expressions** inside aggregation, MongoDB also provides aggregation expression operators named `$and`, `$or`, and `$not`, commonly used inside `$expr` or `$project`. The two contexts use different syntax, especially `$not`:

~~~javascript
// Query operator: $not sits under the field name.
logicDb.products.find({
  stock: { $not: { $gt: 0 } }
});

// Aggregation expression: $not takes an array of expressions,
// and $gt is also an expression.
logicDb.products.aggregate([
  {
    $project: {
      _id: 1,
      notInStock: {
        $not: [
          { $gt: ["$stock", 0] }
        ]
      }
    }
  }
]);
~~~

**Do not copy query `$not` syntax directly into a `$project` expression**, or vice versa.

### 9.3. Logical Conditions in updateMany()

For write operations, the filter selects **which documents get updated**. Always review the condition carefully before running it.

For example, marking active products that have run out of stock:

~~~javascript
var outOfStockFilter = {
  status: "active",
  stock: 0
};

// Preview the selected IDs first.
ids(outOfStockFilter);
// ["p02", "p07"]

// Only after confirming, perform the update:
logicDb.products.updateMany(
  outOfStockFilter,
  { $set: { needsRestock: true } }
);
~~~

This example uses only implicit AND. When business logic requires multiple selection groups:

~~~javascript
var reviewFilter = {
  $or: [
    { status: "draft" },
    {
      status: "active",
      stock: { $lte: 0 }
    }
  ]
};

// Expected: p02, p04, p07 in the initial dataset.
ids(reviewFilter);

// The same filter can be passed to updateMany() after verifying results.
~~~

Note that running update commands modifies the data; if you continue practicing examples from earlier sections, keep in mind that results may differ because documents were modified.

## 10. Missing Fields, Null, and Negated Conditions

Queries often encounter three distinct states:

1. **The field does not exist**.
2. **The field exists with value `null`**.
3. **The field exists with a valid value**, such as a number or string.

MongoDB does not always treat these three states identically. For example, in `p09`, the `status` field does not exist:

~~~javascript
// $ne "active" can match documents without status.
ids({
  status: { $ne: "active" }
});
// ["p04", "p06", "p09"]
~~~

If the true intent is "documents that have status and whose status is not active":

~~~javascript
ids({
  $and: [
    { status: { $exists: true } },
    { status: { $ne: "active" } }
  ]
});
// ["p04", "p06"]
~~~

Similarly, negating a rating score:

~~~javascript
// Includes p08 because rating is absent.
ids({ rating: { $not: { $gte: 4.5 } } });

// Excludes p08 because rating is required to exist.
ids({
  $and: [
    { rating: { $exists: true } },
    { rating: { $not: { $gte: 4.5 } } }
  ]
});
~~~

Another crucial detail: in MongoDB, a plain `{ someField: null }` filter matches **both fields with value null and missing fields**. When you need to distinguish them accurately, use the appropriate data-type and existence operators. Do not try to deduce negation outcomes purely from boolean logic while ignoring missing-field and BSON-type semantics.

**Design principle:** for business data, decide upfront how missing fields should be treated. For instance, should a product without a rating count as "below 4.5" or be excluded from rating reports? Those two choices produce two different filters.

## 11. Optimizing Performance of Multi-Condition Queries

Logical operators define true/false conditions, while performance depends on **indexes**, data distribution, individual query branches, and the MongoDB query optimizer. You cannot assume that simply writing `$and` or `$or` makes a query fast.

### 11.1. AND and Compound Indexes

Filters such as:

~~~javascript
{
  status: "active",
  category: "laptop",
  price: { $gte: 1000 }
}
~~~

can benefit from a compound index aligned with the fields used most often by the application:

~~~javascript
logicDb.products.createIndex({
  status: 1,
  category: 1,
  price: 1
});
~~~

Choosing field order in a compound index should be based on actual workload, filter frequency, sorting, and selectivity. The example above has two equality conditions and one range condition—a classic pattern considered when designing indexes.

### 11.2. OR and Per-Branch Indexes

With `$or`, MongoDB can use different indexes to support respective branches when every branch qualifies for index usage. If any branch cannot be supported effectively by an index, the `$or` query may fall back to a collection scan depending on the case.

Example:

~~~javascript
logicDb.products.createIndex({ category: 1 });
logicDb.products.createIndex({ stock: 1 });

var orFilter = {
  $or: [
    { category: "phone" },
    { stock: 0 }
  ]
};
~~~

Two indexes create optimization opportunities for each branch, but do not guarantee every query will use both: the MongoDB optimizer selects a plan based on estimated cost, collection size, and data distribution. On a collection with only nine documents, **COLLSCAN can be more sensible than IXSCAN**.

### 11.3. Negations Can Have Low Selectivity

Conditions such as `$ne`, `$nin`, `$not`, or `$nor` often retain a large portion of the dataset when the excluded subset is small. Indexes may not improve performance much in such cases.

For instance, "all products that are not phones" may return most of the collection. If business rules define the exact categories to display, using a positive `$in` condition can express intent more clearly:

~~~javascript
// Exclusion condition:
{ category: { $ne: "phone" } }

// Explicit inclusion condition when the category list follows a clear rule:
{ category: { $in: ["laptop", "book", "accessory"] } }
~~~

The two forms are **not always equivalent** if new categories are introduced or the `category` field is missing. Only substitute when the business contract allows it.

### 11.4. Read explain Instead of Guessing

Use `explain("executionStats")` to inspect behavior:

~~~javascript
logicDb.products
  .find(orFilter)
  .explain("executionStats");
~~~

Key items to inspect include `winningPlan`, index/collection scan stage types (such as `IXSCAN` or `COLLSCAN`), `totalKeysExamined`, `totalDocsExamined`, and `nReturned` when returned by your version.

For a pipeline:

~~~javascript
logicDb.products.explain("executionStats").aggregate([
  { $match: orFilter },
  { $sort: { price: -1 } },
  { $limit: 10 }
]);
~~~

A single index tailored for both filtering and sorting can outperform multiple separate indexes that cannot support the sort. Always measure on a dataset large enough and close to production distribution before tuning indexes.

## 12. Common Mistakes When Building Filters from Applications

| Mistake | Why it is wrong or risky | How to fix |
| --- | --- | --- |
| Repeating two `$or` keys in the same object | JavaScript keeps the last key, dropping the first group | Use `$and: [{ $or: [...] }, { $or: [...] }]` |
| Placing `$not` at the root filter level | `$not` is a field-level query operator | Use `$nor` to negate filter branches |
| Confusing `$nor: [A, B]` with `NOT (A AND B)` | `$nor` negates **A OR B** | Use `$nor: [{...A..., ...B...}]` when negating an AND group |
| Assuming `$not` matches only existing fields | Negated conditions can match documents missing the field | Add `$exists: true` if needed |
| Using `$or` for multiple equalities on one field | Verbose and harder to maintain | Consider `$in` |
| Not controlling data types | `"0"`, `0`, and `null` have different semantics | Standardize schema/BSON types and use validation |
| Assuming `$or` preserves condition array order | Logic does not dictate result order | Use `sort()` |
| Dropping logical parentheses when moving conditions in/out of `$or` | Alters the scope of individual conditions | Write the A/B/C expression in plain words first |
| Assuming `$or` is always fast when indexes exist | One poorly indexable branch can make the entire query costly | Use `explain` and measure real workloads |
| Running `updateMany()` with an unverified composed filter | May modify too many documents | Run `find()`/`countDocuments()` first with the same filter |
| Relying on condition order to avoid errors | The optimizer may evaluate or rewrite conditions without app-style short-circuiting | Design expressions safe against all input values |

**Note on evaluation errors:** An `$expr` expression containing an invalid operation on certain data can raise an error even if another branch in the same filter was expected to filter out that document. Do not treat element order in `$and` or `$or` arrays as a guaranteed guard against errors like division by zero; validate data types and write expressions that handle edge values safely.

## 13. Practice Exercises with Result Verification

Use the exact nine-product dataset from Section 2 before running the mutating `updateMany()` examples. For each exercise, try writing at least two approaches where appropriate, then run `ids(filter)` to check the output.

### Exercise 1: AND with a Price Range

Find laptops priced from 700 to 1,500 that are in stock. Which products are returned?

Hint:

~~~javascript
ids({
  category: "laptop",
  price: { $gte: 700, $lte: 1500 },
  stock: { $gt: 0 }
});
// ["p01"]
~~~

`p02` falls within the price range but is out of stock, while `p06` exceeds the upper price bound.

### Exercise 2: OR Between Two Condition Groups

Find products with `category: "book"` or products with `category: "phone"` and `price < 600`.

~~~javascript
ids({
  $or: [
    { category: "book" },
    { category: "phone", price: { $lt: 600 } }
  ]
});
// ["p05", "p08"]
~~~

### Exercise 3: NOR Excluding Two Groups

Exclude `archived` products and out-of-stock products:

~~~javascript
ids({
  $nor: [
    { status: "archived" },
    { stock: 0 }
  ]
});
// ["p01", "p03", "p04", "p05", "p08", "p09"]
~~~

`p09` is retained because it does not have `status: "archived"` and its `stock` is greater than 0.

### Exercise 4: NOT and Missing Fields

Find products that do not satisfy `rating >= 4.5`. Then keep only documents where `rating` exists.

~~~javascript
ids({ rating: { $not: { $gte: 4.5 } } });
// ["p02", "p07", "p08", "p09"]

ids({
  $and: [
    { rating: { $exists: true } },
    { rating: { $not: { $gte: 4.5 } } }
  ]
});
// ["p02", "p07", "p09"]
~~~

Explain why `p08` appears in the first query but not in the second.

### Exercise 5: Two ORs Combined with AND

Find products in laptop or phone **and** having brand ACME or more than 5 units in stock:

~~~javascript
ids({
  $and: [
    {
      $or: [
        { category: "laptop" },
        { category: "phone" }
      ]
    },
    {
      $or: [
        { brand: "ACME" },
        { stock: { $gt: 5 } }
      ]
    }
  ]
});
// ["p01", "p03", "p06", "p08"]
~~~

Explain why `p06` still appears in the result even though it is `archived`: the filter never required an active status.

### Exercise 6: Negating an AND Group

Find all documents **except** those that simultaneously have `category = "laptop"` and `stock > 0`:

~~~javascript
ids({
  $nor: [
    { category: "laptop", stock: { $gt: 0 } }
  ]
});
// ["p02", "p03", "p04", "p05", "p07", "p08", "p09"]
~~~

`p01` and `p06` are excluded because they are laptops in stock. `p02` is kept despite being a laptop because `stock: 0`.

### Exercise 7: Reading and Fixing a Broken Filter

A teammate wrote this code:

~~~javascript
var filter = {
  $or: [
    { status: "active" },
    { status: "draft" }
  ],
  $or: [
    { stock: { $gt: 0 } },
    { category: "book" }
  ]
};
~~~

The actual business requirement is:

~~~text
(status = active OR status = draft)
AND
(stock > 0 OR category = book)
~~~

Rewrite it using `$and` containing two `$or` clauses. Answer what happens if the original `filter` object is used in JavaScript.

## 14. Summary of How to Choose Operators

When constructing a filter, start with an **exact description of the business rule**, especially for negations and fields that may be absent:

- **`$and`:** requires all expressions to be true; when targeting distinct fields, implicit AND is usually sufficient.
- **`$or`:** requires at least one expression to be true; for multiple values on a single field, `$in` can be cleaner.
- **`$nor`:** requires none of the sub-expressions to be true; suitable for negating filter groups, including multi-field expressions.
- **`$not`:** negates a **single field's** operator condition; watch out for documents lacking the field.
- **`$exists`:** explicitly decides whether records missing a field fall within the scope of a negated query.

These operators can be nested to represent complex logic. After writing a filter, test it against a small dataset containing **true, false, boundary, and missing-field cases**, then use `explain` to evaluate performance on realistic data volumes.

### Official References

- [MongoDB Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/) — filter syntax and query conditions.
- [`$and` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/and/) — explicit AND and implicit AND.
- [`$or` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/or/) — multiple condition branches and index considerations.
- [`$nor` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/nor/) — negated OR and behavior with missing fields.
- [`$not` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/not/) — negating field-level expressions.
- [`$exists` — Element Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — checking field existence.
- [`$elemMatch` — Array Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — combining conditions on the same array element.
