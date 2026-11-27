# Distinguishing Query Operators, `$expr`, and Aggregation Expressions in MongoDB

## 1. Three Concepts Sharing the `$` Prefix with Different Roles

When learning to query MongoDB documents, beginners often encounter snippets that look remarkably similar:

```javascript
// (A) Query operator inside a filter condition.
db.orders.find({
  quantity: { $gte: 2 }
});

// (B) $expr allows using an aggregation expression as a filter condition.
db.orders.find({
  $expr: { $gte: ["$quantity", 2] }
});

// (C) Aggregation expression computes a value.
db.orders.aggregate([
  {
    $project: {
      quantity: 1,
      hasAtLeastTwo: { $gte: ["$quantity", 2] }
    }
  }
]);
```

All three examples evaluate "quantity is 2 or more", yet **they differ in syntax, placement, and role**:

- **Query operators** express which documents match a filter. They appear inside `find()`, `countDocuments()`, `updateOne()`, or a `$match` stage.
- **`$expr` is a special query operator**: it lets you place an **aggregation expression** inside a filter context and uses the expression's result to decide whether a document matches.
- **Aggregation expressions** take fields, constants, or sub-expressions and compute **a value**. That value can be used in `$project`, `$set`, `$group`, `$match` via `$expr`, and many other stages.

One more distinction: an **aggregation pipeline stage** (such as `$match`, `$project`, `$group`) is a step processing the entire document stream, whereas an **aggregation expression** (such as `$add`, `$multiply`, `$eq`, `$cond`) computes a value within a stage's context. Both stages and expressions usually start with `$`, yet they cannot be swapped arbitrarily.

```text
                Application needs to filter documents
                             |
                             v
                   Query filter context
                    /                \
        Query operator               $expr
        field: { $gt: 5 }              |
                    \                v
                     \       Aggregation expression
                      \      $gt: ["$field", 5]
                       \             /
                        v           v
                    True / false per document
                             |
                             v
                    Matching document set

      aggregate([ ... ]) has STAGES processing a document stream:
           $match -> $project -> $group -> $sort
                        |
                        +-- value-computing expressions
                            $multiply / $eq / $ifNull ...
```

**Guiding principle:** before writing an operator starting with `$`, identify whether you are inside a **query filter**, an **aggregation expression**, or a **pipeline stage**.

## 2. Sample Dataset

Examples use **mongosh** and a test collection `orders`. Monetary amounts are stored as BSON Decimal128 to avoid floating-point representation issues; `quantity` is the item count, and `minEligibleTotal` is the threshold for checking whether an order qualifies for a promotion.

```javascript
db.orders.insertMany([
  {
    _id: "O1",
    customerId: "C01",
    status: "PAID",
    quantity: 3,
    unitPrice: NumberDecimal("120000"),
    discount: NumberDecimal("20000"),
    minEligibleTotal: NumberDecimal("300000"),
    tags: ["vip", "bulk"],
    createdAt: ISODate("2026-10-01T09:00:00Z")
  },
  {
    _id: "O2",
    customerId: "C02",
    status: "PAID",
    quantity: 1,
    unitPrice: NumberDecimal("250000"),
    discount: NumberDecimal("0"),
    minEligibleTotal: NumberDecimal("300000"),
    tags: [],
    createdAt: ISODate("2026-10-03T09:00:00Z")
  },
  {
    _id: "O3",
    customerId: "C03",
    status: "PENDING",
    quantity: 4,
    unitPrice: NumberDecimal("90000"),
    discount: NumberDecimal("0"),
    minEligibleTotal: NumberDecimal("300000"),
    tags: ["web"],
    createdAt: ISODate("2026-10-05T09:00:00Z")
  },
  {
    _id: "O4",
    customerId: "C01",
    status: "PAID",
    quantity: 2,
    unitPrice: NumberDecimal("120000"),
    discount: null,
    minEligibleTotal: NumberDecimal("200000"),
    tags: ["vip"],
    createdAt: ISODate("2026-10-07T09:00:00Z")
  }
]);
```

With this dataset:

| Order | Status | Quantity | Unit Price | Pre-discount Subtotal (`quantity × unitPrice`) | Threshold |
|---|---|---:|---:|---:|---:|
| O1 | PAID | 3 | 120,000 | 360,000 | 300,000 |
| O2 | PAID | 1 | 250,000 | 250,000 | 300,000 |
| O3 | PENDING | 4 | 90,000 | 360,000 | 300,000 |
| O4 | PAID | 2 | 120,000 | 240,000 | 200,000 |

In this lesson, **pre-discount subtotal** is `quantity × unitPrice`. When net revenue after discount is needed, we also subtract `discount` with explicit handling for `null`; those calculations appear below.

## 3. Query Operators: Describing Field Conditions

A `find()` filter typically has the form **field name → condition to satisfy**:

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 }
});
```

The query above returns O1 and O4: both are paid and have quantity 2 or more.

In this context:

- `status: "PAID"` is shorthand equality matching.
- `quantity: { $gte: 2 }` places the query operator `$gte` under the `quantity` field.
- Conditions on two keys combine via implicit **AND** logic.
- The output of `find()` is **matching documents**, not a Boolean column holding the result of `$gte`.

### 3.1. Common Query Operator Groups

| Group | Example operators | Usage |
|---|---|---|
| Comparison | `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin` | Compare a field's value against a condition |
| Logical | `$and`, `$or`, `$nor`, `$not` | Combine or negate filter conditions |
| Element/Type | `$exists`, `$type` | Check field presence or matching BSON type |
| Array | `$all`, `$elemMatch`, `$size` | Inspect array contents or length |
| String/Regex | `$regex`, `$options` | Pattern-match strings |
| Computed expression | `$expr` | Embed an aggregation expression inside a filter |

Some examples:

```javascript
// O1, O2, O4
db.orders.find({ status: { $eq: "PAID" } });

// O1, O3
db.orders.find({ quantity: { $gt: 2 } });

// O1, O4
db.orders.find({ tags: "vip" });

// O2
db.orders.find({ tags: { $size: 0 } });

// O1, O4: both filter conditions must hold.
db.orders.find({
  $and: [
    { status: "PAID" },
    { quantity: { $gte: 2 } }
  ]
});
```

Query operators live **inside the filter document**. For simple conditions, this is usually the most direct, readable, and index-friendly form.

### 3.2. Comparing One Field Against a Constant Value

```javascript
db.orders.find({
  unitPrice: { $gte: NumberDecimal("120000") }
});
```

This is a **field-to-constant** comparison. MongoDB knows the comparison value ahead of time and can consider an index on `unitPrice` during query planning.

```javascript
db.orders.createIndex({ unitPrice: 1 });
```

This differs fundamentally from asking "is this order's price greater than **another field in the same order**?". The second field is known only when evaluating each document, and standard query syntax does not automatically turn a `$`-prefixed string into a field reference.

### 3.3. A `"$otherField"` String in a Regular Filter Is Not a Field Reference

Example of broken intent:

```javascript
// Does NOT compare quantity against the minQuantity field!
db.orders.find({
  quantity: { $gt: "$minQuantity" }
});
```

In the operand position of query operator `$gt`, `"$minQuantity"` is not interpreted as a field path in an aggregation expression. It is a literal String passed into comparison; results follow BSON type comparison rules and **do not evaluate** the intended `quantity > minQuantity` check.

To compare **field against field**, use `$expr`.

## 4. `$expr`: Using the Aggregation Expression Language Inside a Filter

`$expr` is a **top-level query operator**: it accepts an aggregation expression, evaluates it per candidate document, and uses the result as the filter condition.

```javascript
db.orders.find({
  $expr: {
    $gt: ["$quantity", 2]
  }
});
```

This example finds O1 and O3, matching `{ quantity: { $gt: 2 } }` on the sample dataset. Inside `$expr`, however, `$gt` is an **aggregation expression operator**, taking **an array of two operands**.

Shapes to remember:

```javascript
// Standard query operator:
{ quantity: { $gt: 2 } }

// $expr wrapping an aggregation expression:
{ $expr: { $gt: ["$quantity", 2] } }
```

In the second expression:

- `"$quantity"` is a **field path**, not a literal string to compare.
- `2` is a constant numeric value.
- `$gt` evaluates both expressions and returns a Boolean.
- `$expr` uses the expression's value in the match context.

### 4.1. When Is `$expr` Truly Needed?

Suppose you want orders whose **pre-discount subtotal exceeds the threshold stored inside each order**:

```javascript
db.orders.find({
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Result on the sample dataset: **O1, O3, and O4**.

Document-by-document evaluation:

1. Read `quantity` and `unitPrice` from the current document.
2. Evaluate `$multiply` to obtain the pre-discount subtotal.
3. Read `minEligibleTotal` from that same document.
4. Compare both values using the aggregation expression `$gt`.
5. Keep the document if the result is true.

This calculation cannot be written as `{ unitPrice: { $gt: SOME_CONSTANT } }`, because the threshold comes from another field and the subtotal is a computed value.

### 4.2. Combining Regular Query Filters with `$expr`

It is not an all-or-nothing choice between query operators and `$expr`. Place simple conditions outside `$expr`, and use expressions only for the computed part:

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 },
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Result: **O1 and O4**. This structure is usually very clear:

- `status` and `quantity` are direct field predicates.
- `$expr` handles only the computed comparison.
- All conditions participate in the filter together.

When a suitable index exists, regular query predicates also let the planner narrow candidate documents before running more expensive calculations.

### 4.3. `$expr` Does Not Require `aggregate()`

Some learners assume "using aggregation expressions requires calling `aggregate()`." That is false: `$expr` works inside regular query filters such as `find()`, and can also appear in update/delete filters where supported.

```javascript
// Count orders whose pre-discount subtotal exceeds the threshold.
db.orders.countDocuments({
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Inside `$expr` **is the aggregation expression language**, while outside it remains a **document filter**.

### 4.4. Boolean-Returning vs. Value-Returning Operators

Aggregation expressions like `$eq`, `$gte`, `$and`, `$or`, and `$not` produce Boolean conditions directly. Expressions like `$add`, `$multiply`, `$concat`, and `$ifNull` produce numbers, strings, or other values; nest them inside an explicit comparison:

```javascript
db.orders.find({
  $expr: {
    $gte: [
      {
        $subtract: [
          { $multiply: ["$quantity", "$unitPrice"] },
          { $ifNull: ["$discount", NumberDecimal("0")] }
        ]
      },
      NumberDecimal("300000")
    ]
  }
});
```

Here `$ifNull` substitutes Decimal128 `0` when `discount` is `null` or missing before subtracting. The query finds orders with post-discount total of 300,000 or more; on the sample dataset, **O1** matches.

**Do not rely on implicit truthiness rules** to express business logic. Explicit comparisons make it clear why a document is retained.

## 5. Aggregation Expressions: Computing Values in a Pipeline

An aggregation pipeline is written with `db.collection.aggregate([...])`. Each element of the pipeline array is a **stage**.

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      customerId: 1,
      gross: {
        $multiply: ["$quantity", "$unitPrice"]
      },
      net: {
        $subtract: [
          { $multiply: ["$quantity", "$unitPrice"] },
          { $ifNull: ["$discount", NumberDecimal("0")] }
        ]
      }
    }
  },
  { $sort: { net: -1 } }
]);
```

This pipeline:

1. `$match` keeps only `PAID` orders.
2. `$project` computes two derived values `gross` and `net` for each document.
3. `$sort` orders by `net` **created in the preceding stage**.

Inside `$project`, `$multiply` returns **a number**, not a set of documents. `$subtract` returns a numeric value, and `$ifNull` returns a fallback value on null/missing. That is why these computations cannot sit directly as top-level pipeline stages.

### 5.1. Distinguishing Stages and Expressions by Inputs and Outputs

| Component | Takes what? | Returns what? | Example |
|---|---|---|---|
| Query operator `$gt` | Field value and condition under a filter key | Match / no-match condition | `{ quantity: { $gt: 2 } }` |
| Query operator `$expr` | One aggregation expression in a filter | Match / no-match condition | `{ $expr: { $gt: ["$quantity", 2] } }` |
| Expression `$gt` | Two expressions/operands | Boolean | `{ $gt: ["$quantity", 2] }` |
| Expression `$multiply` | Numeric expressions | Numeric value | `{ $multiply: ["$quantity", "$unitPrice"] }` |
| Expression `$ifNull` | Source expression and fallback value | Value based on null/missing | `{ $ifNull: ["$discount", 0] }` |
| Stage `$match` | Document stream + filter | Filtered document stream | `{ $match: { status: "PAID" } }` |
| Stage `$project` | Document stream + field specs/expressions | Reshaped document stream | `{ $project: { gross: { $multiply: [...] } } }` |
| Stage `$group` | Document stream + group key and accumulators | One document per group | `{ $group: { _id: "$status", count: { $sum: 1 } } }` |

**A `$`-prefixed name alone does not reveal the role.** Look at where the operator sits in the command.

### 5.2. Same Comparison Expression Used to Filter or Compute a Column

```javascript
// Keep only documents with quantity >= 2.
db.orders.find({
  $expr: { $gte: ["$quantity", 2] }
});

// Keep all documents, adding a computed Boolean field.
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      quantity: 1,
      enoughQuantity: { $gte: ["$quantity", 2] }
    }
  }
]);
```

The expression `{ $gte: ["$quantity", 2] }` is identical, yet the **filter** decides which documents appear, whereas the **projection** adds `true` or `false` to output documents.

### 5.3. Using Expressions Inside `$match` via `$expr`

The `$match` stage uses **query filter** syntax:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      $expr: { $gte: ["$quantity", 2] }
    }
  },
  { $project: { _id: 1, status: 1, quantity: 1 } }
]);
```

Do not write:

```javascript
// Wrong context: $gte at the top level of $match is not
// a valid query filter for comparing two expression operands.
db.orders.aggregate([
  { $match: { $gte: ["$quantity", 2] } }
]);
```

Inside `$match`, `$expr` is required to bridge into aggregation expressions. Conversely, inside `$project`, you do not wrap comparison operators in `$expr`, because `$project` is already an expression context.

## 6. Same Operator Name, Different Syntax

This is the most frequent source of bugs when moving between `find()`, `$expr`, and `$project`.

### 6.1. `$eq`, `$gt`, and Comparison Operators

**In a query filter**:

```javascript
{ status: { $eq: "PAID" } }
{ quantity: { $gt: 2 } }
```

**In an aggregation expression**:

```javascript
{ $eq: ["$status", "PAID"] }
{ $gt: ["$quantity", 2] }
```

You cannot place `{ $gt: ["$quantity", 2] }` directly as the value of `quantity` in a filter and expect it to act as an aggregation expression.

### 6.2. `$in`: Value List vs. Two-Operand Array

**Query operator `$in`**: is field `status` in the allowed list of values?

```javascript
db.orders.find({
  status: { $in: ["PAID", "PENDING"] }
});
```

**Aggregation expression `$in`**: is the first expression in the array produced by the second expression?

```javascript
db.orders.find({
  $expr: {
    $in: ["$status", ["PAID", "PENDING"]]
  }
});
```

Both produce the same results on this simple dataset, yet their operands cannot be swapped. If the second argument to the `$in` expression does not evaluate to an array, the expression errors.

### 6.3. `$and` / `$or`: Combining Filter Conditions vs. Expressions

**Query logic** takes an array of **filter documents**:

```javascript
db.orders.find({
  $and: [
    { status: "PAID" },
    { quantity: { $gte: 2 } }
  ]
});
```

**Aggregation expression logic** takes an array of **expressions**:

```javascript
db.orders.find({
  $expr: {
    $and: [
      { $eq: ["$status", "PAID"] },
      { $gte: ["$quantity", 2] }
    ]
  }
});
```

Inside `$project`, the same `$and` expression can compute an `eligible` field:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      eligible: {
        $and: [
          { $eq: ["$status", "PAID"] },
          { $gte: ["$quantity", 2] }
        ]
      }
    }
  }
]);
```

### 6.4. `$not` in Two Different Contexts

The negation operator also has two forms:

```javascript
// Query operator $not: negates a condition on a field.
db.orders.find({
  quantity: { $not: { $gte: 2 } }
});

// Aggregation expression $not: takes a Boolean expression argument.
db.orders.find({
  $expr: {
    $not: [{ $gte: ["$quantity", 2] }]
  }
});
```

Both exclude O2 on the sample dataset because `quantity` always exists and is numeric, but **do not assume they are equivalent across all datasets**. When a field is missing, has another type, or is an array, filter semantics and expression semantics can diverge.

### 6.5. `$size`: Array Length Predicate vs. Length-Computing Expression

**Query operator `$size`** checks whether an array field has an exact element count:

```javascript
// O2 has an empty tags array.
db.orders.find({ tags: { $size: 0 } });
```

**Aggregation expression `$size`** returns the **number of elements** in an array:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tagCount: { $size: "$tags" }
    }
  }
]);
```

On the sample dataset, `tagCount` values are 2, 0, 1, and 1. Note: the aggregation expression `$size` requires its operand to be an array; if a field is missing, null, or another type, the expression can fail. Guard it first:

```javascript
db.orders.aggregate([
  {
    $project: {
      tagCount: {
        $cond: [
          { $isArray: "$tags" },
          { $size: "$tags" },
          0
        ]
      }
    }
  }
]);
```

`$isArray` is an **aggregation expression**, not a query operator usable as `{ tags: { $isArray: true } }`.

### 6.6. Query `$regex` vs. Expression `$regexMatch`

To filter customer IDs starting with `C0`:

```javascript
// Query operator.
db.orders.find({
  customerId: { $regex: "^C0" }
});
```

When you need an expression that evaluates to a Boolean, use `$regexMatch`:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerId: 1,
      codeStartsWithC0: {
        $regexMatch: {
          input: "$customerId",
          regex: "^C0"
        }
      }
    }
  }
]);
```

The two regex forms do not always share the same index usability or collation behavior. Inspect query shapes and execution plans; when an expression reads fields that may be null or missing, apply type conversions or default values as required by the operator.

### 6.7. `$exists` Is a Query Operator; `$type` Works in Expressions

In a filter:

```javascript
db.orders.find({
  discount: { $exists: false }
});
```

This checks whether the field **exists**. Do not use `$exists` as an aggregation expression inside `$project`.

Inside an aggregation expression, to detect missing fields, use `$type`:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountType: { $type: "$discount" },
      discountIsMissing: {
        $eq: [{ $type: "$discount" }, "missing"]
      }
    }
  }
]);
```

On the sample dataset, `discount` is always present: three documents have type `decimal` and O4 has type `null`; none return `"missing"`.

**Do not confuse** `{ discount: null }` in a filter with an exact BSON Null check: query null equality also matches missing fields. Missing/null semantics in aggregation expressions differ and should be controlled explicitly with `$type`, `$ifNull`, or domain-appropriate checks.

## 7. Syntax Rules Specific to Aggregation Expressions

### 7.1. `"$field"` Is a Field Reference; `"text"` Is a String Literal

In an aggregation expression:

```javascript
{ $eq: ["$status", "PAID"] }
```

- `"$status"`: reads the `status` field from the current document.
- `"PAID"`: a literal string.

Consequently, a literal string **starting with `$`** needs special handling:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      sample: { $literal: "$PROMO" }
    }
  }
]);
```

`$literal` instructs MongoDB to use the string `"$PROMO"` as a **literal value** instead of interpreting it as a reference to a field named `PROMO`.

To compare a `coupon` field against the literal string `"$PROMO"`:

```javascript
{
  $expr: {
    $eq: ["$coupon", { $literal: "$PROMO" }]
  }
}
```

### 7.2. Distinguishing Field Paths from `$$variable` Variables

`"$quantity"` references a field in the current document. By contrast, `"$$NOW"` is a **system variable** in the aggregation expression language:

```javascript
db.orders.find({
  $expr: {
    $lte: ["$createdAt", "$$NOW"]
  }
});
```

This example filters orders whose creation time is no later than the current timestamp supplied by the system variable.

In variable-scoping expressions such as `$map`, `$filter`, or `$let`, use `$$varName` to reference user-defined variables:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      upperCaseTags: {
        $map: {
          input: "$tags",
          as: "tag",
          in: { $toUpper: "$$tag" }
        }
      }
    }
  }
]);
```

`$map` iterates over each element of `tags`; `$$tag` refers to the current element. Writing `"$tag"` instead would reference a field on the outer document rather than the loop variable.

### 7.3. Expressions Can Usually Be Nested

```javascript
{
  $subtract: [
    { $multiply: ["$quantity", "$unitPrice"] },
    { $ifNull: ["$discount", NumberDecimal("0")] }
  ]
}
```

The outer operator receives the **output** of inner operators. This is a key mental model when writing business formulas in MongoDB. An operator in a query filter context has different syntax and constraints; never assume "any `$` operator can be nested anywhere."

## 8. Why Does `$match` Still Use Query Operators?

A common misconception is that entering `aggregate()` switches all syntax to aggregation expressions. In reality, each stage defines **its own input language**.

The `$match` stage accepts a **query-style filter**:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      quantity: { $gte: 2 }
    }
  }
]);
```

If a condition must compare field to field or perform calculations, wrap the expression in `$expr`:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      $expr: {
        $gte: [
          { $multiply: ["$quantity", "$unitPrice"] },
          "$minEligibleTotal"
        ]
      }
    }
  }
]);
```

Result: O1 and O4. `$match` still filters documents, except part of the condition is evaluated by an aggregation expression.

### 8.1. When to Place `$match` Early

When a filter depends only on fields already present in source documents, place `$match` early to reduce the number of documents flowing into expensive stages like `$unwind` or `$group`:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 }
    }
  }
]);
```

MongoDB's pipeline optimizer can also push down certain predicates when semantics are preserved. Do not rewrite simple filters into `$expr` unnecessarily, because plain query operators both express intent clearly and integrate smoothly with indexes.

### 8.2. When `$match` Must Follow `$project` or `$set`

If the filter depends on a **newly computed field**, that field must exist at the point where the filter runs:

```javascript
db.orders.aggregate([
  {
    $set: {
      netAmount: {
        $subtract: [
          { $multiply: ["$quantity", "$unitPrice"] },
          { $ifNull: ["$discount", NumberDecimal("0")] }
        ]
      }
    }
  },
  { $match: { netAmount: { $gte: NumberDecimal("300000") } } },
  { $project: { _id: 1, netAmount: 1 } }
]);
```

Here `netAmount` does not exist in source documents; placing the `netAmount` condition before `$set` would find no computed value. For simple pipelines, you can write `$match + $expr` directly over source fields to avoid creating an intermediate field; which option is better depends on readability and the execution plan.

## 9. Differences in Index Usage and Execution Cost

MongoDB uses a query planner to decide how to read data. A simple filter:

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 }
});
```

can benefit from a compound index:

```javascript
db.orders.createIndex({ status: 1, quantity: 1 });
```

The planner can use the equality predicate on `status` and the range predicate on `quantity` to reduce keys and documents examined.

By contrast, a computed filter:

```javascript
db.orders.find({
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

must compute a value from **multiple fields** of each document. Standard indexes on `quantity` or `unitPrice` do not precompute the per-document product, so you cannot assume MongoDB can evaluate that comparison via an index without reading the underlying documents.

A widely used pattern is **keeping indexable predicates in the regular query filter and putting only the computed part in `$expr`**:

```javascript
db.orders.find({
  status: "PAID",
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Avoid the absolute claim that "`$expr` can never use an index." Certain comparisons in suitable forms and contexts (notably `$lookup` pipelines binding fields and constants) can use indexes depending on MongoDB version, index type, and exact conditions. Conversely, having an index does not mean any arbitrary expression can use it.

### 9.1. Observe Instead of Guessing

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 }
}).explain("executionStats");

db.orders.find({
  status: "PAID",
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
}).explain("executionStats");
```

When reading `explain()`, look at:

| Indicator | Meaning |
|---|---|
| `IXSCAN` | Index key scan step |
| `COLLSCAN` | Full collection scan step |
| `FETCH` | Document fetch step after scanning index keys |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of documents returned |
| `executionTimeMillis` | Execution time reported in stats; interpret in test context |

Explain output formats vary across MongoDB versions and execution engines. With only four sample orders, MongoDB may choose a collection scan simply because the data is tiny; the first goal is understanding **execution paths**, not extrapolating production latency from four documents.

### 9.2. When Should Computed Fields Be Stored?

If business logic frequently filters on `netAmount` or `grossAmount` across millions of documents, consider **persisting a derived field** directly in the document and indexing it:

```javascript
{
  _id: "O1",
  quantity: 3,
  unitPrice: NumberDecimal("120000"),
  discount: NumberDecimal("20000"),
  grossAmount: NumberDecimal("360000"),
  netAmount: NumberDecimal("340000")
}
```

`grossAmount` and `netAmount` are **computed and maintained consistently by the application on write**. If quantity, unit price, or discount changes and the application forgets to update those derived fields, queries using the `netAmount` index will run fast while returning **wrong business results**.

Therefore, query optimization via derived fields must be paired with update discipline, atomic boundaries, and derived-data controls; never store redundant fields solely to avoid writing `$expr` everywhere.

## 10. Comparing Array Operations: `$elemMatch` vs. Array Expressions

When documents contain arrays, distinguish whether you are **filtering documents based on elements** or **computing over elements**.

Suppose we have a `carts` collection:

```javascript
db.carts.insertMany([
  {
    _id: "CART1",
    items: [
      { sku: "BOOK", quantity: 1, price: 100000 },
      { sku: "PEN", quantity: 5, price: 10000 }
    ]
  },
  {
    _id: "CART2",
    items: [
      { sku: "BOOK", quantity: 3, price: 100000 },
      { sku: "PEN", quantity: 1, price: 10000 }
    ]
  }
]);
```

### 10.1. Query Operator `$elemMatch`

Find carts having at least one line item that is **both BOOK and has quantity 2 or more**:

```javascript
db.carts.find({
  items: {
    $elemMatch: {
      sku: "BOOK",
      quantity: { $gte: 2 }
    }
  }
});
```

Only CART2 matches. If you wrote:

```javascript
db.carts.find({
  "items.sku": "BOOK",
  "items.quantity": { $gte: 2 }
});
```

CART1 would also match because the `sku` and `quantity` conditions can be satisfied by **two different elements**. Here `$elemMatch` is a query operator enforcing same-element semantics.

### 10.2. Aggregation Expression `$filter`

If you want to **return only the BOOK line items with quantity 2 or more**, use `$filter` inside `$project`:

```javascript
db.carts.aggregate([
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.sku", "BOOK"] },
              { $gte: ["$$item.quantity", 2] }
            ]
          }
        }
      }
    }
  }
]);
```

This pipeline returns **both carts**, with `eligibleItems` as `[]` for CART1 and the BOOK item with quantity 3 for CART2.

Summary:

- `$elemMatch` in a query: **filters documents** based on an element satisfying conditions.
- `$filter` in aggregation: **produces a new array** containing elements matching a Boolean expression.
- You can combine `$expr`, `$size`, and `$filter` to filter documents by the count of elements matching a computed condition, though this does not match the indexability of a simple predicate.

Example keeping only carts with at least one BOOK item with quantity 2 or more via an aggregation expression:

```javascript
db.carts.find({
  $expr: {
    $gt: [
      {
        $size: {
          $filter: {
            input: "$items",
            as: "item",
            cond: {
              $and: [
                { $eq: ["$$item.sku", "BOOK"] },
                { $gte: ["$$item.quantity", 2] }
              ]
            }
          }
        }
      },
      0
    ]
  }
});
```

The logical result is also CART2, but when filtering on simple array conditions, `$elemMatch` is shorter and clearer.

## 11. Expressions in Update Pipelines vs. Traditional Update Operators

MongoDB has two update forms that are easily confused:

### 11.1. Traditional Update with the `$set` Operator

```javascript
db.orders.updateOne(
  { _id: "O1" },
  {
    $set: {
      status: "SHIPPED"
    }
  }
);
```

Here the second argument is an **update document**, and `$set` is an update operator, not an aggregation stage. Field values are assigned directly rather than evaluated as pipeline formulas.

### 11.2. Update with an Aggregation Pipeline

```javascript
db.orders.updateOne(
  { _id: "O1" },
  [
    {
      $set: {
        netAmount: {
          $subtract: [
            { $multiply: ["$quantity", "$unitPrice"] },
            { $ifNull: ["$discount", NumberDecimal("0")] }
          ]
        }
      }
    }
  ]
);
```

Here the second argument is an **array of supported update stages**, and `$set` acts as an **aggregation stage**, computing `netAmount` from existing fields in the document.

This is a classic example where the same `$set` name takes two different forms. The distinction is determined by **whether the update argument is an object or an array of stages**. An update pipeline accepts only the subset of stages supported for updates—not every `aggregate()` stage is valid.

**Note:** the update examples in this section modify test data. If you need to compare query outputs against the initial table, run read examples first or re-seed the collection.

## 12. `$expr` Inside `$lookup`: Comparing Fields Across Two Contexts

In an aggregation pipeline, `$lookup` joins documents from another collection. With the `pipeline` and `let` form, `$expr` lets you compare fields of the joined collection against variables bound from the outer document.

Suppose:

```javascript
// Collection customers
{ _id: "C01", tier: "GOLD" }
{ _id: "C02", tier: "STANDARD" }
{ _id: "C03", tier: "STANDARD" }
```

Joining orders with customers:

```javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      let: { wantedCustomerId: "$customerId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: ["$_id", "$$wantedCustomerId"]
            }
          }
        },
        { $project: { _id: 1, tier: 1 } }
      ],
      as: "customer"
    }
  }
]);
```

Explanation:

1. `let` binds `wantedCustomerId` from each outer order's `customerId` field.
2. Inside `$lookup`'s `pipeline`, `"$_id"` refers to `_id` of documents from the `customers` collection.
3. `"$$wantedCustomerId"` references the variable declared in `let`, not a field in `customers`.
4. `$expr` brings the field-to-variable comparison into the `$match` filter.

Under certain conditions, `$eq`, `$lt`, `$lte`, `$gt`, and `$gte` inside a `$lookup` pipeline's `$expr` can leverage an index on the `from` collection when the relevant operand acts as a lookup-constant value; arrays, missing values, and index types can limit this optimization. Never assume every `$lookup` pipeline with `$expr` uses an index automatically.

When a simple equality join between two fields suffices, `$lookup` with `localField` / `foreignField` is usually simpler. The `let` / `pipeline` form is helpful when join conditions or transformations need greater flexibility.

## 13. Common Syntax and Semantic Pitfalls

| Mistake or misconception | Why is it problematic? | Correct approach |
|---|---|---|
| `{ quantity: { $gt: "$minimum" } }` | A string in a query operand is not an expression field reference | Use `{ $expr: { $gt: ["$quantity", "$minimum"] } }` |
| `{ $match: { $gt: ["$quantity", 2] } }` | `$match` expects a query filter; `$gt` expression is in the wrong context | Wrap with `$expr` |
| `{ $project: { valid: { $expr: ... } } }` | `$project` already takes expressions; `$expr` is for query contexts | Write the Boolean expression directly |
| `{ $expr: { quantity: { $gte: 2 } } }` | Inside `$expr` requires an aggregation expression, not a field filter | `{ $expr: { $gte: ["$quantity", 2] } }` |
| Using `$size: 0` to count elements in `$project` | Query `$size` checks length; expression `$size` takes an array expression | `{ $size: "$tags" }` |
| Using `{ $exists: true }` in `$project` as an expression | `$exists` is a query operator | Use `$type` or another suitable condition |
| Assuming `"$field"` is always a literal string | In aggregation expressions, it is a field reference | Use `$literal` for strings starting with `$` |
| Writing `"$tag"` for a `$map` variable | Variables bound by `as` require a double `$$` prefix | Use `"$$tag"` |
| Assuming `$expr` never uses indexes | Index usage depends on structure, context, and version | Check `explain()` and keep simple filters outside `$expr` |
| Assuming aggregation pipelines only use expressions | Stages have their own syntax; `$match` takes a query filter | Distinguish stage, query, and expression |
| Treating every `$set` as an update operator | `$set` is also an aggregation stage | Check whether the update argument is an object or stage array |
| Assuming `{ field: null }` matches only explicit null | Query equality with null also matches missing fields | Use type or existence predicates as required |

## 14. Method for Choosing the Right Tool

Ask three questions in order:

**Question 1: Do I only need to decide which documents to keep?**

If yes, start with a **query filter**. Conditions like `status = "PAID"`, `quantity >= 2`, or `tags` containing `"vip"` are straightforward with query operators.

**Question 2: Does the condition require multi-field computation or field-to-field comparison?**

If yes, use **`$expr` inside a query filter**, or compute the value in an aggregation pipeline and filter on it afterward. Keep simple predicates outside `$expr` where appropriate.

**Question 3: Do I need to return computed fields, reshape documents, or group multiple documents?**

If yes, use an **aggregation pipeline**, placing expressions inside appropriate stages such as `$project`, `$set`, or `$group`. `$expr` can sit inside `$match` if that stage needs computed filtering.

Decision table:

| Requirement | Appropriate tool | Example |
|---|---|---|
| Filter orders with `quantity >= 2` | Query operator | `{ quantity: { $gte: 2 } }` |
| Filter orders with `quantity > minimumQuantity` in the same document | `$expr` | `{ $expr: { $gt: ["$quantity", "$minimumQuantity"] } }` |
| Filter orders with `quantity × unitPrice > minEligibleTotal` | `$expr` + aggregation expressions | `$gt` nesting `$multiply` |
| Return an extra `grossAmount` column | `$project` / `$set` stage + `$multiply` expression | `{ grossAmount: { $multiply: [...] } }` |
| Count orders by `status` | `$group` pipeline + accumulator | `{ $group: { _id: "$status", count: { $sum: 1 } } }` |
| Match arrays containing an element satisfying multiple conditions | Query `$elemMatch` | `{ items: { $elemMatch: {...} } }` |
| Return a filtered array | Aggregation expression `$filter` | `{ eligibleItems: { $filter: {...} } }` |
| Reference outer fields inside a `$lookup` pipeline | `let` + `$expr` | `$eq: ["$_id", "$$wantedId"]` |

## 15. Self-Check Practice Exercises

### Exercise 1 — Three Ways to Express One Condition

Using the `orders` collection from Section 2, express **quantity 2 or more** in three ways:

1. A query operator in `find()`.
2. `$expr` in `find()`.
3. Aggregation `$project` returning a Boolean field `enoughQuantity` without filtering out any orders.

Explain why the first two return a matching subset of documents while the third returns a Boolean value on every document.

### Exercise 2 — Computing Subtotal and Filtering Against Another Field

Write a `find()` query to find orders where `quantity × unitPrice > minEligibleTotal`, combined with `status: "PAID"`. On the sample dataset, predict which `_id` values appear.

Hint: use `$multiply` and `$gt` **inside `$expr`**, while keeping `status` in the outer filter.

### Exercise 3 — Comparing `$size` in Two Contexts

For documents with `tags`:

- Use the query operator to retrieve orders with an **empty `tags` array**.
- Use the aggregation expression to compute a `tagCount` field.
- Investigate how the pipeline behaves if a document lacks `tags`; add a type guard using `$isArray`.

### Exercise 4 — Fixing Invalid Syntax

Given three snippets:

```javascript
// a
db.orders.find({ quantity: { $gt: "$minimum" } });

// b
db.orders.aggregate([
  { $match: { $eq: ["$status", "PAID"] } }
]);

// c
db.orders.aggregate([
  { $project: { valid: { $expr: { $gte: ["$quantity", 2] } } } }
]);
```

Fix each snippet to match the proper query or expression context, and explain the difference between "comparing a field to a constant" and "comparing two fields".

### Exercise 5 — Choosing Filters Over Computed Expressions

Suppose the collection has index `{ status: 1, quantity: 1 }`. Propose how to express **status = PAID and quantity >= 2**, then compare it against a version written entirely with `$expr`. Run `explain("executionStats")` on a sufficiently large test dataset to inspect plans without jumping to rigid assumptions about which is always faster.

### Exercise 6 — Separating Filter, Computation, and Grouping

Write a pipeline returning **post-discount** revenue by `customerId`, counting only `PAID` orders:

1. `$match` filters `status`.
2. `$project` computes `netAmount = quantity × unitPrice − discount`; if `discount` is null, use 0.
3. `$group` by `customerId` with an accumulator summing `netAmount`.
4. `$sort` by total revenue descending.

Then try a variant keeping only orders with `netAmount >= 300000` before grouping, and explain when `$expr` avoids creating an intermediate field.

### Exercise 7 — Variable Scope in `$lookup`

Write a `$lookup` from `orders` to `customers` matching `orders.customerId` with `customers._id`. Try both approaches:

- `localField` / `foreignField`.
- `let` / `pipeline` / `$match` / `$expr`.

Explain the difference between `"$_id"` and `"$$wantedCustomerId"` inside the inner pipeline.

## 16. Key Takeaways

**Query operators** express document-matching criteria, typically using `field: { $operator: value }`. They are the natural starting point for simple filters and index-optimized queries.

**`$expr` bridges into the aggregation expression language right inside a query filter**. It enables field-to-field comparisons and computations like `$multiply`, `$subtract`, and `$ifNull` before deciding whether to keep a document.

**Aggregation expressions compute a value; pipeline stages process a stream of documents.** Inside `$project`, `$set`, or `$group`, expressions compute output values; inside `$match`, place an expression under `$expr` to use it as a filter.

When reading MongoDB code, do not look solely at `$`-prefixed operator names. Identify **which context you are in**, **whether an operand is a literal value or a field path**, and **whether the goal is filtering documents or computing a value**. Answering those three questions prevents most errors when switching between query operators, `$expr`, and aggregation expressions.
