# Conditional Operators $cond, $switch, $ifNull, and Handling Missing Data in MongoDB Aggregation

## Lesson Objectives

In the **MongoDB Aggregation Framework**, conditional expressions allow you to transform documents based on available data instead of reading documents and writing all `if/else` branches in application code. Three especially important expressions are:

- **`$cond`**: selects **one of two** results based on a true/false condition.
- **`$switch`**: selects the **first matching branch** from a set of multiple conditions.
- **`$ifNull`**: returns a fallback value when an expression evaluates to `null`, **missing**, or an undefined value treated as equivalent to null.

A common problem: an order document has a `discount` field, but older records may lack the field, other records have `discount: null`, or have a valid value `discount: 0`. If designed improperly, the pipeline might treat `0` as missing, miscalculate the net amount, or lose the ability to distinguish data states.

After this lesson, learners will be able to:

1. Write both `$cond` syntaxes (object and array) and select branches based on boolean expressions.
2. Write `$switch` with multiple `branches`, `case`, `then`, and `default`, understanding evaluation priority order.
3. Use `$ifNull` for two-argument fallbacks and multi-source fallbacks according to supported server versions.
4. Distinguish between a **missing field**, **BSON null**, **false**, **0**, **empty string**, and **empty array**.
5. Combine `$type`, `$convert`, `$isNumber`, `$isArray`, and `$$REMOVE` to handle malformed or missing data.
6. Apply expressions in `$project`, `$addFields`/`$set`, `$group`, `$match` with `$expr`, and updates using aggregation pipelines.
7. Design clear pipelines with consistent output data types, bounded computation cost, and an understanding of index impact.
8. Practice using `mongosh`, read outputs, and build test cases for edge cases.

> **Core rule:** `$ifNull` handles **nullish**; `$cond` handles **true/false**; `$switch` handles **multiple ordered branches**. These are three distinct mechanisms and are not interchangeable in every situation.

---

## 1. How Do Aggregation Expressions Differ from Direct Field Reads?

An aggregation pipeline consists of multiple stages. Example:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      discount: 1,
      netAmount: {
        $subtract: [
          "$amount",
          { $ifNull: ["$discount", 0] }
        ]
      }
    }
  }
]);
~~~

In `$project`:

- `"_id": 1`, `"amount": 1`, `"discount": 1` are instructions to include those fields.
- `"$amount"` is a **field path expression**, meaning retrieve the value of the `amount` field from the current document.
- `{ $ifNull: ["$discount", 0] }` is an **aggregation expression**, selecting the existing `discount` or `0` when `discount` is nullish.
- `$subtract` performs subtraction on the expression values.

These two strings have different meanings:

~~~javascript
// Access the amount field:
"$amount"

// Literal string with content "$amount":
{ $literal: "$amount" }
~~~

Aggregation interprets a string starting with `$` in an expression position as a field/variable reference, not an ordinary text string. When you want a literal string that actually starts with `$`, use `$literal`.

### 1.1. Three Conditional Operators Perform Three Different Jobs

| Requirement | Tool | Example |
|---|---|---|
| Check one condition and choose between two results | `$cond` | High amount -> "HIGH", otherwise "NORMAL" |
| Classify across multiple statuses | `$switch` | NEW, PAID, CANCELLED, otherwise UNKNOWN |
| Use a preferred value, otherwise fall back | `$ifNull` | nickname → fullName → "Customer" |
| Distinguish missing field from null field | `$type` combined with condition | "missing" differs from "null" |
| Conditionally omit an output field | `$$REMOVE` combined with `$cond` | Omit the `warning` field when there is no warning |
| Convert error-prone string-number data to number | `$convert` | "1200" → 1200, error → null/fallback |

### 1.2. `$cond` Is Not an Update Operator

`$cond`, `$switch`, and `$ifNull` are typically used as **expressions** inside aggregation stages such as `$project`, `$addFields`, and `$set`. They are not standalone database write commands.

A read pipeline:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      label: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "Paid",
          "Unpaid"
        ]
      }
    }
  }
]);
~~~

does not automatically save `label` back to the documents. To persist results to the database, you need a supported update with an aggregation pipeline or another intentional write design.

---

## 2. Preparing Practice Data

The examples use `mongosh` and the **`aggregation_condition_lab`** database. Run only on a test database. If data exists from a previous session, use another collection or clean up according to lab procedures to avoid duplicate `_id` errors.

~~~javascript
use aggregation_condition_lab

db.orders.insertMany([
  {
    _id: "ORD-101",
    status: "PAID",
    amount: 1200000,
    discount: 100000,
    shippingFee: 30000,
    customer: {
      nickname: "An",
      fullName: "Nguyễn Văn An",
      email: "an@example.test"
    },
    items: [
      { sku: "A-01", quantity: 2 },
      { sku: "B-01", quantity: 1 }
    ]
  },
  {
    _id: "ORD-102",
    status: "PAID",
    amount: 850000,
    discount: 0,
    shippingFee: null,
    estimatedShippingFee: 25000,
    customer: {
      nickname: "",
      fullName: "Trần Bình",
      email: null
    }
  },
  {
    _id: "ORD-103",
    status: "NEW",
    amount: 500000,
    customer: {
      fullName: "Lê Chi"
    }
  },
  {
    _id: "ORD-104",
    status: "CANCELLED",
    amount: 200000,
    discount: null,
    shippingFee: 0,
    customer: {
      nickname: "Dung",
      fullName: "Phạm Dung"
    }
  },
  {
    _id: "ORD-105",
    status: "PAID",
    amount: "900000",
    discount: "50000",
    shippingFee: 15000,
    customer: {
      fullName: "Hà"
    }
  },
  {
    _id: "ORD-106",
    status: "PAID",
    amount: null,
    discount: null,
    customer: null
  },
  {
    _id: "ORD-107",
    amount: 0,
    discount: false,
    customer: {
      nickname: null,
      fullName: "Khánh"
    },
    items: []
  },
  {
    _id: "ORD-108",
    status: "REFUNDED",
    amount: 300000,
    discount: 10000,
    shippingFee: 0,
    customer: {
      fullName: "Lan",
      email: "lan@example.test"
    }
  },
  {
    _id: "ORD-109",
    status: "NEW",
    customer: {
      fullName: "Minh"
    }
  }
]);
~~~

Verify:

~~~javascript
db.orders.countDocuments({});
db.orders.find({}, {
  _id: 1,
  status: 1,
  amount: 1,
  discount: 1,
  shippingFee: 1
}).sort({ _id: 1 });
~~~

If the data was inserted cleanly once, the document count is **9**.

### 2.1. Intentionally Created Edge Cases

| Document | `discount` | `amount` | Characteristics |
|---|---|---|---|
| ORD-101 | 100000 | 1200000 | Normal numeric data |
| ORD-102 | **0** | 850000 | 0 is a valid value, not null |
| ORD-103 | **Missing** | 500000 | `discount` field does not exist |
| ORD-104 | **null** | 200000 | Field exists but is null |
| ORD-105 | **"50000"** | **"900000"** | Numeric data stored as wrong string type |
| ORD-106 | **null** | **null** | Nullish data |
| ORD-107 | **false** | **0** | Wrong-type boolean discount, valid 0 amount |
| ORD-108 | 10000 | 300000 | Status outside common branches |
| ORD-109 | **Missing** | **Missing** | Multiple missing fields |

This variety clearly shows when conditional operators work properly and when data-type checks are needed.

---

## 3. Understanding Missing, null, and Easily Confused Values

### 3.1. Missing Differs from null

Two documents:

~~~javascript
{ _id: "X", discount: null }
{ _id: "Y" }
~~~

do not have the same structure.

- X **has the `discount` field** with a BSON null value.
- Y **does not have the `discount` field**.

To check existence at the query level:

~~~javascript
db.orders.find({
  discount: { $exists: true }
});

db.orders.find({
  discount: { $exists: false }
});
~~~

Here `$exists` is a **query operator**, used in a `find()` or standard `$match` filter, not an aggregation expression placed directly as a `$cond` condition.

To detect this inside an aggregation expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountType: {
        $type: "$discount"
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

The output can show:

~~~text
ORD-101 -> int
ORD-102 -> int
ORD-103 -> missing
ORD-104 -> null
ORD-105 -> string
ORD-106 -> null
ORD-107 -> bool
ORD-108 -> int
ORD-109 -> missing
~~~

`$type` as an aggregation expression can return the string `"missing"` if the referenced field does not exist. For `NumberInt`/`NumberLong`/`Decimal128` data, type names may vary; in the lab above, numbers written directly in `mongosh` are usually stored in an appropriate BSON numeric type, so do not turn this illustrative table into a rigid assumption about every numeric type.

### 3.2. A Nullish Value Is Not the Same as a Falsy Value

Many programming languages have concepts such as nullish and truthy/falsy. MongoDB also has rules for evaluating expressions as booleans.

Several key values:

| Value | Nullish for `$ifNull`? | Boolean in `$cond` condition |
|---|---|---|
| Missing field | **Yes** | Falsy in contexts evaluated as undefined/nullish |
| BSON `null` | **Yes** | False |
| Undefined (legacy) | **Yes** | False |
| `false` | **No** | False |
| `0` | **No** | False |
| `""` | **No** | Usually treated as truthy under aggregation boolean rules; do not assume JavaScript behavior |
| `[]` | **No** | Truthy |
| `{}` | **No** | Truthy |
| Non-zero number | **No** | True |
| Non-empty string | **No** | True |

**Key point:** `$ifNull` does not mean "use a default if falsy." It only checks cases treated as equivalent to null. In payment data, a discount of **0** must be preserved and must not be treated as missing.

### 3.3. Null Equality Queries Can Match Missing Fields

~~~javascript
db.orders.find({
  discount: null
});
~~~

In MongoDB, a query equality check against `null` can match both documents with `discount: null` **and documents missing `discount`**.

If you only want fields with a BSON null value:

~~~javascript
db.orders.find({
  discount: { $type: "null" }
});
~~~

If you only want missing fields:

~~~javascript
db.orders.find({
  discount: { $exists: false }
});
~~~

At the aggregation expression level, use `$type` to handle each state explicitly rather than inferring via `$eq` against null.

---

## 4. `$cond`: Selecting One of Two Branches

### 4.1. Two Syntax Forms

MongoDB supports the object form:

~~~javascript
{
  $cond: {
    if: <boolean-expression>,
    then: <true-case-expression>,
    else: <false-case-expression>
  }
}
~~~

and the array form:

~~~javascript
{
  $cond: [
    <boolean-expression>,
    <true-case-expression>,
    <false-case-expression>
  ]
}
~~~

In real code, replace the placeholders with concrete expressions or values. **All three components are required**; do not omit `else` assuming MongoDB will automatically default to null.

Equivalent examples:

~~~javascript
// Object form
{
  $cond: {
    if: { $gte: ["$amount", 1000000] },
    then: "HIGH_VALUE",
    else: "NORMAL"
  }
}

// Array form
{
  $cond: [
    { $gte: ["$amount", 1000000] },
    "HIGH_VALUE",
    "NORMAL"
  ]
}
~~~

Prefer the object form when expressions are long because the `if`, `then`, and `else` keys prevent positional confusion. The array form is suitable when the condition and values are short.

### 4.2. A Practice Pipeline

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ORD-101", "ORD-102"] }
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      amountLevel: {
        $cond: {
          if: {
            $gte: ["$amount", 1000000]
          },
          then: "HIGH_VALUE",
          else: "NORMAL"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

For these two documents with numeric amounts:

| `_id` | Amount | Amount level |
|---|---:|---|
| ORD-101 | 1,200,000 | HIGH_VALUE |
| ORD-102 | 850,000 | NORMAL |

**Do not extend this example to all documents without checking the `amount` type.** ORD-105 stores `amount` as a string and ORD-106 has `amount: null`; comparisons may use BSON type comparison order instead of business arithmetic semantics.

### 4.3. Combining `$and` and `$or`

Requirement: only allow a shipping fee discount if the order is `PAID` and the total amount is large enough.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ORD-101", "ORD-102"] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1,
      shippingDiscountEligible: {
        $cond: {
          if: {
            $and: [
              { $eq: ["$status", "PAID"] },
              { $gte: ["$amount", 1000000] }
            ]
          },
          then: true,
          else: false
        }
      }
    }
  }
]);
~~~

Results:

- ORD-101: `PAID` and amount 1,200,000 → `true`.
- ORD-102: `PAID` but amount 850,000 → `false`.

With data that might have wrong types, normalize/validate `amount` before comparing. Do not rely on `$and` as a guaranteed short-circuit mechanism to block invalid operations; design expressions and type conversions with explicit control.

### 4.4. Do Not Use a Field as a Boolean Ambiguously

If you write:

~~~javascript
{
  $cond: [
    "$discount",
    "HAS_DISCOUNT",
    "NO_DISCOUNT"
  ]
}
~~~

then both `discount: 0` and `discount: null` lead to the false branch, even though their business meanings differ:

- `0`: a valid discount of zero.
- `null`: an unspecified value.
- `missing`: the field does not exist yet.
- non-empty string: may be treated as true even though it is not a number.

A clearer condition is:

~~~javascript
{
  $cond: {
    if: {
      $and: [
        { $isNumber: "$discount" },
        { $gt: ["$discount", 0] }
      ]
    },
    then: "POSITIVE_DISCOUNT",
    else: "NO_POSITIVE_DISCOUNT"
  }
}
~~~

However, `"NO_POSITIVE_DISCOUNT"` still lumps together `0`, `null`, `missing`, and wrong-type values into one group. If the application needs to separate these groups, use `$switch` or add a data-error reporting field.

### 4.5. Nested `$cond`

A three-tier classification can be written with nested `$cond` expressions:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ORD-101", "ORD-102", "ORD-103"] }
    }
  },
  {
    $project: {
      amount: 1,
      amountBand: {
        $cond: {
          if: { $gte: ["$amount", 1000000] },
          then: "HIGH",
          else: {
            $cond: {
              if: { $gte: ["$amount", 500000] },
              then: "MEDIUM",
              else: "LOW"
            }
          }
        }
      }
    }
  }
]);
~~~

For the three documents with numeric amounts, the results are `HIGH`, `MEDIUM`, `MEDIUM`. However, as the number of branches grows, nested `$cond` becomes hard to read and easy to misorder. `$switch` is usually clearer.

---

## 5. `$switch`: Selecting the First Matching Branch

### 5.1. Syntax

~~~javascript
{
  $switch: {
    branches: [
      {
        case: <condition-expression-1>,
        then: <result-expression-1>
      },
      {
        case: <condition-expression-2>,
        then: <result-expression-2>
      }
    ],
    default: <fallback-expression>
  }
}
~~~

Rules:

1. MongoDB evaluates `branches` in **declared order**.
2. The first branch whose `case` evaluates to true is selected.
3. The result is the `then` expression of that branch.
4. If no branch matches, `default` is used if present.
5. If no branch matches **and `default` is omitted**, the aggregation may throw an error instead of automatically returning null.

### 5.2. Classifying Order Statuses

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      statusLabel: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "NEW"] },
              then: "Pending"
            },
            {
              case: { $eq: ["$status", "PAID"] },
              then: "Paid"
            },
            {
              case: { $eq: ["$status", "CANCELLED"] },
              then: "Cancelled"
            },
            {
              case: { $eq: ["$status", "REFUNDED"] },
              then: "Refunded"
            }
          ],
          default: "Unknown"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

With the lab data:

| Status | Label |
|---|---|
| NEW | Pending |
| PAID | Paid |
| CANCELLED | Cancelled |
| REFUNDED | Refunded |
| Missing or unsupported status | Unknown |

Thanks to `default`, documents like ORD-107 that are missing `status` still produce an appropriate output value rather than causing the pipeline to fail due to no matching branch.

### 5.3. Branch Order Is Part of the Logic

Suppose you want to classify orders based on numeric `amount`:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: { $gte: ["$amount", 500000] },
        then: "MEDIUM_OR_MORE"
      },
      {
        case: { $gte: ["$amount", 1000000] },
        then: "HIGH"
      }
    ],
    default: "LOW"
  }
}
~~~

**Problem:** Every `amount ≥ 1,000,000` is also `≥ 500,000`. The first branch already matches, so the `HIGH` branch never has a chance to be selected for those amounts.

Better:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: { $gte: ["$amount", 1000000] },
        then: "HIGH"
      },
      {
        case: { $gte: ["$amount", 500000] },
        then: "MEDIUM"
      }
    ],
    default: "LOW"
  }
}
~~~

For wrong-type data, `amount` must be checked/normalized; the example above only illustrates condition ordering for valid numeric values.

### 5.4. Multiple Conditions Can Be True Simultaneously

`$switch` does **not** automatically find the "most specific" branch. It picks the **first true branch**.

Example:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: {
          $and: [
            { $eq: ["$status", "PAID"] },
            { $gte: ["$amount", 1000000] }
          ]
        },
        then: "PAID_HIGH_VALUE"
      },
      {
        case: { $eq: ["$status", "PAID"] },
        then: "PAID_OTHER"
      }
    ],
    default: "OTHER"
  }
}
~~~

Both cases can be true for a high-value `PAID` order. The more specific branch must be placed first.

### 5.5. Do Not Omit `default` If New Statuses Can Appear

Suppose currently only `NEW`/`PAID` exist, so the development team omits `default`. Later, a `REFUNDED` status is introduced; the pipeline may fail when encountering a document where no branch matches.

An appropriate `default` helps forward compatibility:

~~~javascript
default: "UNKNOWN_STATUS"
~~~

However, do not use `default` to **hide** critical data errors. If business logic requires handling every published status, you still need to log/monitor counts of `UNKNOWN_STATUS` to detect schema drift.

---

## 6. `$ifNull`: Getting a Fallback Value When Nullish

### 6.1. Basic Syntax

~~~javascript
{
  $ifNull: [
    <input-expression>,
    <replacement-expression>
  ]
}
~~~

If the input has a **non-nullish** value, `$ifNull` returns that value itself. If the input is null, missing, or an undefined value treated as equivalent to null, it returns the replacement.

Example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discount: 1,
      effectiveDiscount: {
        $ifNull: [
          "$discount",
          0
        ]
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Notable results:

| Document | Original value | `effectiveDiscount` |
|---|---|---|
| ORD-101 | 100000 | 100000 |
| ORD-102 | 0 | **0**, does not fall back |
| ORD-103 | Missing | 0 |
| ORD-104 | null | 0 |
| ORD-105 | "50000" | **"50000"**, remains a string |
| ORD-106 | null | 0 |
| ORD-107 | false | **false**, remains a bool |
| ORD-108 | 10000 | 10000 |
| ORD-109 | Missing | 0 |

**Lesson:** `$ifNull` solves **missing/null**, not **wrong type**. If `discount` is a string or `false`, providing a fallback of `0` does not convert them into numbers.

### 6.2. The Fallback Does Not Have to Be a Literal

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      shippingFee: 1,
      estimatedShippingFee: 1,
      chargeableShippingFee: {
        $ifNull: [
          "$shippingFee",
          "$estimatedShippingFee"
        ]
      }
    }
  }
]);
~~~

If `shippingFee` is nullish, `estimatedShippingFee` is used. If both are nullish, the result can also be nullish, which depending on stage/output semantics may not yield a useful value. Provide an explicit final fallback when business logic requires a value to always exist.

### 6.3. `$ifNull` with Multiple Sources — MongoDB 5.0+

Starting in MongoDB **5.0**, `$ifNull` supports multiple input expressions in priority order, with the **replacement at the end**.

Example:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      chargeableShippingFee: {
        $ifNull: [
          "$shippingFee",
          "$estimatedShippingFee",
          0
        ]
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Meaning:

1. If `shippingFee` is not nullish → use `shippingFee`.
2. If `shippingFee` is nullish and `estimatedShippingFee` is not nullish → use `estimatedShippingFee`.
3. If both are nullish → use `0`.

ORD-102 has `shippingFee: null` and `estimatedShippingFee: 25000`, so the result is 25,000. ORD-104 has `shippingFee: 0`, so the result is **0**, without falling back to another source.

If you must support MongoDB prior to 5.0, use nested two-argument `$ifNull` instead of multi-input syntax:

~~~javascript
{
  $ifNull: [
    "$shippingFee",
    {
      $ifNull: [
        "$estimatedShippingFee",
        0
      ]
    }
  ]
}
~~~

When using code with multiple inputs, document the minimum supported server version clearly.

### 6.4. Fallback for Display Name

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      displayName: {
        $ifNull: [
          "$customer.nickname",
          "$customer.fullName",
          "Customer"
        ]
      }
    }
  }
]);
~~~

Notable point: ORD-102 has `nickname: ""`. An empty string is **not nullish**, so `$ifNull` preserves the empty string and does **not** automatically fall back to `"Trần Bình"`. If the application wants empty strings treated as missing, an explicit check must be added.

### 6.5. Handling Empty Strings

When `nickname` can be `""`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      displayName: {
        $let: {
          vars: {
            nickname: {
              $ifNull: ["$customer.nickname", ""]
            }
          },
          in: {
            $cond: {
              if: {
                $ne: ["$$nickname", ""]
              },
              then: "$$nickname",
              else: {
                $ifNull: [
                  "$customer.fullName",
                  "Customer"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

`$let` defines a temporary variable to avoid repeating logic. The approach above treats null/missing/empty string as having no nickname, though it does not yet handle whitespace-only nicknames or wrong types like arrays. If whitespace normalization is needed, combine `$trim` with a `$type` check before processing.

---

## 7. When to Use Which Operator?

| Problem | Prefer | Reason |
|---|---|---|
| One true/false condition | `$cond` | Two clear branches |
| Multiple statuses or ranges | `$switch` | Easier to read than nested `$cond` |
| Default value when field is missing/null | `$ifNull` | Directly expresses nullish fallback |
| Priority order across multiple data sources | Multi-input `$ifNull` | Returns first non-nullish source |
| Must distinguish missing from explicit null | `$type` + `$cond`/`$switch` | `$ifNull` merges both states |
| `0` and `false` are valid values | `$ifNull` if only handling nullish | Does not conflate `0`/`false` with missing |
| Empty string must also use fallback | `$cond` or `$switch` with empty check | `$ifNull` does not replace empty strings |
| Need to verify numeric type before calculation | `$isNumber`/`$convert` + conditional expression | Avoids relying on BSON comparison on wrong-type data |
| Need to omit output field when no value applies | `$$REMOVE` + condition | Produces appropriate document structure |

### 7.1. Equivalent Example Between `$cond` and `$switch`

A two-branch case:

~~~javascript
{
  $cond: [
    { $eq: ["$status", "PAID"] },
    "Paid",
    "Other"
  ]
}
~~~

Can use `$switch`:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: { $eq: ["$status", "PAID"] },
        then: "Paid"
      }
    ],
    default: "Other"
  }
}
~~~

Both express similar logic, but `$cond` is shorter and clearer when there is only one condition. `$switch` fits when there are multiple ordered cases.

### 7.2. `$ifNull` Is Not a Replacement for a True/False Condition

Example:

~~~javascript
{
  $ifNull: [
    "$isVerified",
    false
  ]
}
~~~

If `isVerified` is `false`, the result remains `false`. This is correct because a fallback is needed **only when nullish**.

Meanwhile:

~~~javascript
{
  $cond: [
    "$isVerified",
    "VERIFIED",
    "NOT_VERIFIED"
  ]
}
~~~

turns the condition into a label. These two expressions **do not produce the same output type**.

---

## 8. Distinguishing Missing Fields from Null Fields with `$type`

In many business domains, missing and null have different meanings:

- Missing: an old record that has not been migrated yet.
- Null: the field is defined, but the user has not provided a value.
- Zero: a meaningful value, not "absent."
- Wrong type: schema-drifted data that needs fixing.

### 8.1. Using `$switch` to Classify

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountState: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$discount" },
                  "missing"
                ]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: [
                  { $type: "$discount" },
                  "null"
                ]
              },
              then: "EXPLICIT_NULL"
            },
            {
              case: {
                $isNumber: "$discount"
              },
              then: "NUMERIC"
            }
          ],
          default: "INVALID_TYPE"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Expected output:

| Document | `discountState` |
|---|---|
| ORD-101 | NUMERIC |
| ORD-102 | NUMERIC |
| ORD-103 | MISSING |
| ORD-104 | EXPLICIT_NULL |
| ORD-105 | INVALID_TYPE |
| ORD-106 | EXPLICIT_NULL |
| ORD-107 | INVALID_TYPE |
| ORD-108 | NUMERIC |
| ORD-109 | MISSING |

In this classification, `0` is still `NUMERIC`; `false` is `INVALID_TYPE`.

### 8.2. Using `$cond` When Only Checking for Missing

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      hasDiscountField: {
        $cond: {
          if: {
            $eq: [
              { $type: "$discount" },
              "missing"
            ]
          },
          then: false,
          else: true
        }
      }
    }
  }
]);
~~~

With `discount: null`, `hasDiscountField` returns `true` because **the field exists**. If you only used `$ifNull`, missing and null would be merged together, making it impossible to reliably distinguish them from the fallback result.

### 8.3. Checking Missing Inside an Embedded Document

If a nested field is:

~~~javascript
{
  customer: {
    email: null
  }
}
~~~

then:

~~~javascript
{ $type: "$customer.email" }
~~~

returns `"null"`.

If `email` is absent:

~~~javascript
{
  customer: {
    fullName: "An"
  }
}
~~~

then `$type` on `"$customer.email"` can return `"missing"`.

If `customer` itself is null or missing, accessing `customer.email` will not yield a valid email either. When you need to distinguish a parent structural error from a missing child field, check them separately:

~~~javascript
{
  parentType: { $type: "$customer" },
  emailType: { $type: "$customer.email" }
}
~~~

Do not use a single `"MISSING_EMAIL"` label to mask cases where `customer` is stored as the wrong type if the business domain needs to address schema drift.

---

## 9. `$$REMOVE`: Omitting a Field When a Condition Is Not Met

A common requirement: add a `warning` field only if an order has a status requiring attention. Otherwise, the `warning` field must be **absent**, not `null` or an empty string.

MongoDB provides the system variable **`$$REMOVE`** to exclude a field in stages that construct or reshape documents such as `$project` and `$addFields`.

### 9.1. Example with `$cond`

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      warning: {
        $cond: {
          if: {
            $eq: ["$status", "CANCELLED"]
          },
          then: "Cancelled order",
          else: "$$REMOVE"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

For ORD-104, the output has `warning: "Cancelled order"`. For other orders, the `warning` field **is not present in the output document**.

Compare:

~~~javascript
else: null
~~~

This creates the field with a `null` value, unlike `$$REMOVE`.

### 9.2. Omitting Fields Based on Data State

Suppose you want to output `customerEmail` only if `email` exists and is not null:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerEmail: {
        $cond: {
          if: {
            $in: [
              { $type: "$customer.email" },
              ["missing", "null"]
            ]
          },
          then: "$$REMOVE",
          else: "$customer.email"
        }
      }
    }
  }
]);
~~~

This excludes missing/null, but still lets wrong-type emails such as numbers or arrays pass through. If the requirement is to output only string emails, use `$type` and an explicit branch:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerEmail: {
        $cond: {
          if: {
            $eq: [
              { $type: "$customer.email" },
              "string"
            ]
          },
          then: "$customer.email",
          else: "$$REMOVE"
        }
      }
    }
  }
]);
~~~

### 9.3. Do Not Mistake `$$REMOVE` in a Read `aggregate` for Modifying Source Data

In a regular `aggregate()`, `$$REMOVE` only shapes the returned output. It **does not delete fields from the collection**. When updating with an aggregation pipeline, `$$REMOVE` in a `$set` stage can affect the stored document; distinguish the contexts clearly.

---

## 10. BSON Types and Comparisons: Do Not Rely on Type Ordering When Arithmetic Is Needed

Data with:

~~~javascript
{ amount: 900000 }
~~~

differs from:

~~~javascript
{ amount: "900000" }
~~~

In aggregation, comparing different BSON types under MongoDB's rules can produce an ordering that does not match arithmetic expectations. For instance, comparing a string with a number does not necessarily coerce the string to a number.

If you use:

~~~javascript
{
  $gte: ["$amount", 1000000]
}
~~~

when `amount` is a string, the result must not be interpreted as "comparing monetary amounts." For monetary values that might be stored with wrong types, it is better to use `$convert`.

### 10.1. `$convert` with `onError` and `onNull`

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      amount: 1,
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

Meaning:

- `amount` is a valid number → converted to the appropriate Decimal128.
- `amount` is a numeric string such as `"900000"` → can be converted to decimal.
- `amount` is an unconvertible string such as `"unknown"` → `onError: null` prevents the entire pipeline from failing at the conversion step.
- `amount` is missing or null → `onNull: null`.
- Here both `onError` and `onNull` produce null; you can choose different sentinel values if you need to distinguish the causes.

Without `onError`, type conversion errors can fail the entire pipeline. `$ifNull` does not replace `onError` handling, because a wrong-type string is **non-nullish**.

### 10.2. Normalize First, Then Classify

A two-stage pipeline:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      amountBand: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$amountDecimal" },
                  "null"
                ]
              },
              then: "UNKNOWN_AMOUNT"
            },
            {
              case: {
                $gte: [
                  "$amountDecimal",
                  NumberDecimal("1000000")
                ]
              },
              then: "HIGH"
            },
            {
              case: {
                $gte: [
                  "$amountDecimal",
                  NumberDecimal("500000")
                ]
              },
              then: "MEDIUM"
            }
          ],
          default: "LOW"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      amountDecimal: 1,
      amountBand: 1
    }
  }
]);
~~~

The first stage converts `amount` to an appropriate type. The second stage puts missing/null/unconvertible documents into `UNKNOWN_AMOUNT`, and compares monetary ranges on valid Decimal128 values.

**Note:** If the first stage sets both `onError: null` and `onNull: null`, the output no longer indicates whether the specific cause was missing data or a parse error. If auditing is needed, preserve an additional field such as `amountOriginalType` or `amountConversionState` before merging.

### 10.3. Choose Monetary Types Carefully

For money:

- Avoid mixing strings, doubles, and decimals arbitrarily.
- Store integer minor units (e.g., VND or cents) according to the business model, or Decimal128 if decimal precision is required.
- Validate/normalize input at the API boundary.
- Perform arithmetic using compatible types.
- Define rounding, currency, and negative/large-number bounds per business rules.
- Do not let an arbitrary `0` fallback mask invalid monetary data.

---

## 11. Combining `$ifNull` with Safe Numeric Conversion

Suppose we are calculating `effectiveDiscount`.

### 11.1. Fallback Missing/Null Only, Without Handling Wrong Types

~~~javascript
{
  effectiveDiscount: {
    $ifNull: [
      "$discount",
      0
    ]
  }
}
~~~

This still lets the string `"50000"` and boolean `false` pass through. It is unsuitable if the next step subtracts money with `$subtract`.

### 11.2. Convert First, Then Fall Back

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discount: 1,
      effectiveDiscount: {
        $ifNull: [
          {
            $convert: {
              input: "$discount",
              to: "decimal",
              onError: null,
              onNull: null
            }
          },
          NumberDecimal("0")
        ]
      }
    }
  }
]);
~~~

For numeric or numeric-string discounts, the result is Decimal128. For missing/null or unconvertible data, the result is Decimal128 `0`.

**Trade-off:** Collapsing parse errors into `0` can mask corrupted data. If discounts are critical financial data, emit a data-quality error or block the transaction instead of silently reducing to `0`.

### 11.3. Preserving Separate Error States

A clearer approach:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      discountOriginalType: {
        $type: "$discount"
      },
      discountDecimal: {
        $convert: {
          input: "$discount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      discountState: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$discountOriginalType", "missing"]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: ["$discountOriginalType", "null"]
              },
              then: "EXPLICIT_NULL"
            },
            {
              case: {
                $eq: [
                  { $type: "$discountDecimal" },
                  "null"
                ]
              },
              then: "INVALID_OR_UNCONVERTIBLE"
            }
          ],
          default: "VALID"
        }
      },
      effectiveDiscount: {
        $ifNull: [
          "$discountDecimal",
          NumberDecimal("0")
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      discount: 1,
      discountOriginalType: 1,
      discountState: 1,
      effectiveDiscount: 1
    }
  }
]);
~~~

For ORD-107, which has boolean `discount: false`, extra care is needed: `$convert` between BSON types has specific rules, and booleans can have valid conversions to numeric types. If the goal is to **accept only values that are originally numbers or allowed numeric strings**, add a check on the **original type** before conversion rather than only checking whether conversion succeeded.

Example business-rule decision:

~~~javascript
{
  $cond: {
    if: {
      $in: [
        { $type: "$discount" },
        ["int", "long", "double", "decimal", "string"]
      ]
    },
    then: {
      $convert: {
        input: "$discount",
        to: "decimal",
        onError: null,
        onNull: null
      }
    },
    else: null
  }
}
~~~

Here `bool` is rejected by design. For `string`, conversion is still attempted and may produce a parse error; `onError: null` handles that case. Note that a policy accepting numeric strings should also be reviewed at the API layer when writing new data.

---

## 12. A Complete Business Pipeline: Orders and Data Warnings

### 12.1. Requirements

For the `orders` collection:

1. Label `status` according to business mapping.
2. Normalize `amount` and `discount` to Decimal128 when valid.
3. Compute `netAmount` only when `amount` is valid.
4. Missing/null `discount` is treated as `0` per the demo rule.
5. If `amount` cannot be converted, do not output `netAmount`.
6. Display customer name by `nickname` if present and non-empty; otherwise use `fullName` or a placeholder.
7. Attach a warning if `amount` data is invalid.

### 12.2. Pipeline

~~~javascript
db.orders.aggregate([
  // Step 1: Normalize source fields.
  {
    $set: {
      amountOriginalType: {
        $type: "$amount"
      },
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      discountDecimal: {
        $convert: {
          input: "$discount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      customerNickname: {
        $ifNull: [
          "$customer.nickname",
          ""
        ]
      }
    }
  },

  // Step 2: Compute based on fields normalized in the previous stage.
  {
    $set: {
      statusLabel: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "NEW"] },
              then: "Pending"
            },
            {
              case: { $eq: ["$status", "PAID"] },
              then: "Paid"
            },
            {
              case: { $eq: ["$status", "CANCELLED"] },
              then: "Cancelled"
            },
            {
              case: { $eq: ["$status", "REFUNDED"] },
              then: "Refunded"
            }
          ],
          default: "Unknown status"
        }
      },
      displayName: {
        $cond: {
          if: {
            $and: [
              {
                $eq: [
                  { $type: "$customerNickname" },
                  "string"
                ]
              },
              { $ne: ["$customerNickname", ""] }
            ]
          },
          then: "$customerNickname",
          else: {
            $ifNull: [
              "$customer.fullName",
              "Customer"
            ]
          }
        }
      },
      effectiveDiscount: {
        $ifNull: [
          "$discountDecimal",
          NumberDecimal("0")
        ]
      }
    }
  },

  // Step 3: Calculate amounts and output warning only when needed.
  {
    $set: {
      netAmount: {
        $cond: {
          if: {
            $isNumber: "$amountDecimal"
          },
          then: {
            $subtract: [
              "$amountDecimal",
              "$effectiveDiscount"
            ]
          },
          else: "$$REMOVE"
        }
      },
      amountWarning: {
        $cond: {
          if: {
            $isNumber: "$amountDecimal"
          },
          then: "$$REMOVE",
          else: "AMOUNT_MISSING_OR_INVALID"
        }
      }
    }
  },

  // Step 4: Build the output read model.
  {
    $project: {
      _id: 1,
      status: 1,
      statusLabel: 1,
      displayName: 1,
      amount: 1,
      discount: 1,
      amountOriginalType: 1,
      amountDecimal: 1,
      effectiveDiscount: 1,
      netAmount: 1,
      amountWarning: 1
    }
  },

  { $sort: { _id: 1 } }
]);
~~~

**Design explanation:**

- The first stage uses `$convert` with `onError`/`onNull`, preventing wrong-type `amount` values from breaking the whole pipeline.
- `$switch` maps `status` to a label with a fallback.
- `$cond` picks the customer name and decides whether to emit `netAmount`.
- `$ifNull` provides a fallback for nullish `discount`.
- `$$REMOVE` avoids adding `netAmount`/`amountWarning` when inapplicable.
- `$project` drops unnecessary intermediate fields such as `customerNickname` from the output.
- Separating into two/three `$set` stages avoids depending on a newly computed field being referenced immediately inside the **same stage**; this split keeps the logic clear.

### 12.3. Why Not Silently Compute netAmount When amount Is Missing?

If an order has no `amount`, returning `netAmount: 0` could mislead the application into treating it as a valid zero-value order. Instead, the pipeline uses `$$REMOVE` to omit `netAmount` while creating `amountWarning`. This is a clearer modeling decision for invalid data.

In production, you may need to flag defective records, support remediation, or block payment. Aggregation expressions are only one part of a data quality strategy.

### 12.4. Limitations of the Demo Conversion Approach

The pipeline above converts numeric strings to decimal and defaults to `0` when `discount` fails conversion. This is an illustrative policy, not an automatic recommendation for all financial data.

If `discount` is negative or greater than `amount`, `netAmount` could become negative. If that is disallowed, add conditions such as:

~~~javascript
{
  $and: [
    { $gte: ["$discountDecimal", NumberDecimal("0")] },
    { $lte: ["$discountDecimal", "$amountDecimal"] }
  ]
}
~~~

but only run them after confirming the values have valid numeric types. A proper billing system must also handle currency, taxes, rounding, and other business constraints.

---

## 13. `$project`, `$addFields`, and `$set`: Where to Use Conditionals?

### 13.1. `$project`: Shaping the Output

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      isPaid: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          true,
          false
        ]
      }
    }
  }
]);
~~~

`$project` produces an output containing only the requested fields and computed fields (aside from `_id`'s default inclusion rule). Suitable for building DTOs/read models for APIs.

### 13.2. `$addFields` and `$set`: Adding or Overwriting Fields in the Aggregation Stream

~~~javascript
db.orders.aggregate([
  {
    $addFields: {
      effectiveDiscount: {
        $ifNull: ["$discount", 0]
      }
    }
  }
]);
~~~

`$set` is an alias for `$addFields` in aggregation:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      effectiveDiscount: {
        $ifNull: ["$discount", 0]
      }
    }
  }
]);
~~~

These stages retain other fields and add or overwrite the specified fields. If a new field has the same name as an existing field, the output value replaces that field's value within the pipeline.

### 13.3. `$set` Aggregation Stage vs. `$set` Update Operator

Two syntaxes in different contexts:

~~~javascript
// Aggregation expression: "$legacyStatus" is a field reference.
db.orders.aggregate([
  {
    $set: {
      normalizedStatus: "$legacyStatus"
    }
  }
]);
~~~

~~~javascript
// Standard update operator:
// "$legacyStatus" is a literal string to assign.
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      normalizedStatus: "$legacyStatus"
    }
  }
);
~~~

When you want to **update based on an expression**, use an update with an aggregation pipeline if supported by your version, for example:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  [
    {
      $set: {
        normalizedStatus: {
          $ifNull: [
            "$status",
            "UNKNOWN"
          ]
        }
      }
    }
  ]
);
~~~

Here `"$status"` is interpreted as a field expression because it sits inside an aggregation pipeline update.

---

## 14. Using `$match` with Expression Conditions and `$expr`

### 14.1. Query Predicate Comparisons

A normal query:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  }
]);
~~~

can leverage an index on `status` when the query planner determines it is appropriate.

If you need to compare two fields within the same document, use `$expr`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      $expr: {
        $gt: [
          "$amount",
          "$discount"
        ]
      }
    }
  }
]);
~~~

However, with lab data containing null, string, or missing `amount`/`discount`, this example does not guarantee accurate arithmetic comparisons. Data normalization or type filtering is needed.

### 14.2. Complex Conditions Inside `$expr`

~~~javascript
db.orders.aggregate([
  {
    $match: {
      $expr: {
        $cond: {
          if: {
            $eq: ["$status", "PAID"]
          },
          then: {
            $gte: [
              "$amount",
              500000
            ]
          },
          else: false
        }
      }
    }
  }
]);
~~~

This is how logic can be expressed inside `$expr`; however, if the predicate can be written directly in query form:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      amount: { $gte: 500000 }
    }
  }
]);
~~~

then the direct form is usually clearer and more likely to get suitable index bounds for basic query workloads. There is no need to put `$cond` inside `$expr` in every situation.

### 14.3. Combining Early `$match` with Late `$project`

Whenever possible, filter down the document count before running heavy conversions or calculations:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $set: {
      effectiveDiscount: {
        $ifNull: ["$discount", 0]
      }
    }
  },
  {
    $project: {
      status: 1,
      effectiveDiscount: 1
    }
  }
]);
~~~

MongoDB has an optimizer that can reorder certain stages under specific conditions, but do not assume every dynamic expression gets indexed or pushed down automatically. Inspect `explain` for large workloads.

---

## 15. Updating Documents via Aggregation Pipeline with Conditional Expressions

When you want to **persist** computed values into the collection, MongoDB supports updates using aggregation pipelines in supported versions.

### 15.1. Backfilling a Default Field

For example, setting a default `shippingFee` only when the field is missing/null:

~~~javascript
db.orders.updateMany(
  {
    _id: {
      $in: [
        "ORD-103",
        "ORD-106"
      ]
    }
  },
  [
    {
      $set: {
        shippingFee: {
          $ifNull: [
            "$shippingFee",
            0
          ]
        }
      }
    }
  ]
);
~~~

This is an actual update, unlike `aggregate()`. On subsequent runs, `shippingFee` is already `0`, and `$ifNull` keeps `0`, so the operation may make no further modifications.

### 15.2. Creating a Field Only When Status Matches

~~~javascript
db.orders.updateMany(
  {
    _id: {
      $in: ["ORD-101", "ORD-102", "ORD-103"]
    }
  },
  [
    {
      $set: {
        accountingLabel: {
          $cond: {
            if: {
              $eq: ["$status", "PAID"]
            },
            then: "BOOKED",
            else: "$$REMOVE"
          }
        }
      }
    }
  ]
);
~~~

For `PAID`, the accounting field is set. For other statuses, `$$REMOVE` causes the field to be absent from the stage output. If an older document already had `accountingLabel`, this approach can remove the field when the condition is false; recognize that this mutates stored data rather than merely filtering output.

### 15.3. Combining Multiple Stages to Use Intermediate Fields

~~~javascript
db.orders.updateMany(
  {
    status: "PAID"
  },
  [
    {
      $set: {
        amountDecimal: {
          $convert: {
            input: "$amount",
            to: "decimal",
            onError: null,
            onNull: null
          }
        }
      }
    },
    {
      $set: {
        amountBand: {
          $cond: {
            if: {
              $isNumber: "$amountDecimal"
            },
            then: {
              $cond: [
                {
                  $gte: [
                    "$amountDecimal",
                    NumberDecimal("1000000")
                  ]
                },
                "HIGH",
                "NORMAL"
              ]
            },
            else: "UNKNOWN"
          }
        }
      }
    }
  ]
);
~~~

This backfill can change types or add fields across many documents; in production, evaluate schema validators, write load, index maintenance, idempotency, and expected document counts before running.

### 15.4. Do Not Enable upsert Automatically When Only Updating Existing Records

Update pipelines can also be used in `updateOne` with `upsert`, but if the business logic should only update existing documents, do not add `upsert: true` casually. A mismatched filter can insert a new document missing required fields.

---

## 16. Conditionals Inside Arrays: `$map`, `$ifNull`, and `$cond`

A document may contain an array of line items. Requirement: each item has `quantity`; if missing/null, default to `1`; if `quantity ≥ 10`, classify as `BULK`.

### 16.1. With a Valid Array

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: "ORD-101"
    }
  },
  {
    $project: {
      _id: 1,
      normalizedItems: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            quantity: {
              $ifNull: [
                "$$line.quantity",
                1
              ]
            },
            lineType: {
              $cond: {
                if: {
                  $gte: [
                    "$$line.quantity",
                    10
                  ]
                },
                then: "BULK",
                else: "STANDARD"
              }
            }
          }
        }
      }
    }
  }
]);
~~~

`$$line` is the `$map` variable, not a top-level field. `$$line.quantity` accesses the field inside each element being processed.

### 16.2. If items Is Missing or null

`$map` handles nullish input according to its own rules and may return null. If the application always wants an array output, combine with `$ifNull`:

~~~javascript
{
  $map: {
    input: {
      $ifNull: [
        "$items",
        []
      ]
    },
    as: "line",
    in: {
      sku: "$$line.sku"
    }
  }
}
~~~

### 16.3. If items Can Have the Wrong Type

If `items` is an object or a string instead of an array, `$map` may raise an error. `$ifNull` does not replace wrong-type values, so check with `$isArray`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      normalizedItems: {
        $map: {
          input: {
            $cond: {
              if: {
                $isArray: "$items"
              },
              then: "$items",
              else: []
            }
          },
          as: "line",
          in: {
            sku: "$$line.sku",
            quantity: {
              $ifNull: [
                "$$line.quantity",
                1
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

This avoids non-array input type errors, but **hides wrong-type data** behind an empty array. For important data, emit an additional warning field or reject schema-invalid data at the source.

### 16.4. Nested Conditionals Per Element

If `quantity` can be a string, boolean, or null, avoid plain comparisons:

~~~javascript
{
  $cond: {
    if: {
      $isNumber: "$$line.quantity"
    },
    then: {
      $cond: [
        { $gte: ["$$line.quantity", 10] },
        "BULK",
        "STANDARD"
      ]
    },
    else: "INVALID_QUANTITY"
  }
}
~~~

If you decide to allow numeric strings, you can add `$convert` with `onError`, provided you define the output data type and validation policy.

---

## 17. `$group` After Classification and Handling Missing Data

Once a label is created with `$switch` or `$cond`, results can be grouped by that label.

### 17.1. Grouping by Status Label

~~~javascript
db.orders.aggregate([
  {
    $set: {
      statusGroup: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "PAID"] },
              then: "PAID"
            },
            {
              case: { $eq: ["$status", "NEW"] },
              then: "OPEN"
            },
            {
              case: { $eq: ["$status", "CANCELLED"] },
              then: "CLOSED"
            },
            {
              case: { $eq: ["$status", "REFUNDED"] },
              then: "CLOSED"
            }
          ],
          default: "UNKNOWN"
        }
      }
    }
  },
  {
    $group: {
      _id: "$statusGroup",
      orderCount: { $sum: 1 }
    }
  },
  {
    $sort: {
      orderCount: -1,
      _id: 1
    }
  }
]);
~~~

Because `default` is `UNKNOWN`, documents missing `status` are still counted in a clear group instead of failing the pipeline. Sorting by count and `_id` provides a tie-breaker when groups have equal counts.

### 17.2. Summing amount Only for Valid Numbers

~~~javascript
db.orders.aggregate([
  {
    $set: {
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: {
        $sum: 1
      },
      totalKnownAmount: {
        $sum: {
          $ifNull: [
            "$amountDecimal",
            NumberDecimal("0")
          ]
        }
      },
      unknownAmountCount: {
        $sum: {
          $cond: [
            {
              $isNumber: "$amountDecimal"
            },
            0,
            1
          ]
        }
      }
    }
  }
]);
~~~

The output contains both the sum of successfully converted amounts and the count of records with invalid or nullish amounts. This is better reporting than treating all missing amounts as `0` without recording data errors.

### 17.3. Do Not Forget Type and Rounding When Aggregating

If `amount` represents money, use Decimal128 consistently along with appropriate rounding rules. Before running a collection-wide grouping pipeline on large datasets, evaluate aggregation cost, memory usage, and index utilization in `$match`.

---

## 18. Performance: Where Should Conditionals Be Placed in a Pipeline?

### 18.1. Prefer Index-Eligible Filters First

If a query only needs `PAID` orders:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $set: {
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $project: {
      amountDecimal: 1
    }
  }
]);
~~~

It is usually better when conversion expressions run only on documents that already passed the filter. An index on `status` can assist `$match` if the planner chooses it.

### 18.2. Dynamically Computed Expressions Usually Cannot Directly Use Standard Indexes

Example:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      isHigh: {
        $cond: [
          { $gte: ["$amount", 1000000] },
          true,
          false
        ]
      }
    }
  },
  {
    $match: {
      isHigh: true
    }
  }
]);
~~~

If `isHigh` is a newly computed field in the pipeline, you cannot assume a B-tree index on `isHigh` in the source data—that field did not exist before the pipeline. Depending on the optimizer and expression shape, MongoDB may perform certain optimizations, but do not rely on that as a guarantee.

If the query only needs `amount ≥ 1,000,000` on a normalized numeric field, writing:

~~~javascript
db.orders.find({
  amount: { $gte: 1000000 }
});
~~~

is typically clearer and has a chance to use an index directly on `amount`, whereas querying string-typed `amount` data requires separate data rules.

### 18.3. When to Materialize a Computed Field?

If the API continuously filters and sorts by a computed classification, consider storing a derived field in the document:

~~~javascript
{
  _id: "ORD-101",
  status: "PAID",
  amount: NumberDecimal("1200000"),
  amountBand: "HIGH"
}
~~~

and creating an index for the query:

~~~javascript
db.orders.createIndex({
  status: 1,
  amountBand: 1,
  _id: 1
});
~~~

Trade-off: whenever `amount` changes, the application must update `amountBand` consistently. Materialized fields reduce read cost at the expense of higher complexity and write maintenance. Decide based on workload rather than assuming every `$cond` needs pre-storage.

### 18.4. Separate Conversion and Conditional Branching Clearly

A long expression deeply nesting `$convert`, `$ifNull`, and `$switch` can be hard to read and maintain. Splitting into stages that compute intermediate fields and projecting them away at the end is often clearer, though benchmarking is needed to verify cost.

However, do not create dozens of tiny stages just for aesthetics; balance readability, optimizer behavior, and expression reuse.

### 18.5. Do Not Use Fallbacks to Hide Bad Data

If a financial endpoint returns `0` when `amount` is invalid, revenue reports may become inaccurate. Often it is better to:

- Set `amountState` = `INVALID`.
- Exclude the record from sums and count the errors.
- Send a data quality alert.
- Perform migration or validation at the source.
- Never display guessed monetary amounts.

Aggregation does not decide business policy for missing data; the designer must do so.

---

## 19. Data Type and Truthiness Notes

### 19.1. 0 Is Not null

~~~javascript
{
  $ifNull: [
    0,
    100
  ]
}
~~~

produces **0**, not 100. Similarly:

~~~javascript
{
  $ifNull: [
    false,
    true
  ]
}
~~~

produces **false**.

### 19.2. Empty String Is Not null

~~~javascript
{
  $ifNull: [
    "",
    "UNKNOWN"
  ]
}
~~~

produces an **empty string**. If you want to replace empty strings, use `$cond` with `$eq`, or combine with trimming when the data type allows.

### 19.3. Empty Array Is Not null

~~~javascript
{
  $ifNull: [
    [],
    ["fallback"]
  ]
}
~~~

produces an **empty array**, not the fallback array.

If the application wants "when an array has no elements, replace with a default array," use a condition on `$size` after confirming the input is an array.

### 19.4. Do Not Use Boolean Coercion Instead of Validation

MongoDB has boolean evaluation rules for conditions; a string, array, or object can evaluate to true even if business rules require a proper boolean. If `isEnabled` must be a boolean, store a boolean and enforce schema validation; do not assume a string `"false"` will be interpreted as false.

### 19.5. If Wrong-Type Fields Must Be Treated as Missing, State It Explicitly

`$ifNull` does not automatically discard wrong-type values. For example, a document has `phone: 12345` while the API only accepts string phone numbers. To fall back to `alternatePhone`, combine with `$type`:

~~~javascript
{
  $cond: {
    if: {
      $eq: [
        { $type: "$phone" },
        "string"
      ]
    },
    then: "$phone",
    else: {
      $ifNull: [
        "$alternatePhone",
        "UNKNOWN"
      ]
    }
  }
}
~~~

Here if `alternatePhone` also has the wrong type, it could still be accepted. For critical applications, check the type of both sources or normalize the schema before applying fallbacks.

---

## 20. Java Sync Driver: Building Conditional Aggregations

The MongoDB Java Driver allows building pipelines using BSON `Document` objects or helpers in `Aggregates`. The example uses `Document` so the mapping from MQL is easy to see.

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class ConditionalAggregationExample {

    public static void run(MongoCollection<Document> collection) {

        Document statusLabel = new Document(
            "$switch",
            new Document("branches", Arrays.asList(
                new Document("case",
                    new Document("$eq",
                        Arrays.asList("$status", "PAID")
                    )
                ).append("then", "Paid"),

                new Document("case",
                    new Document("$eq",
                        Arrays.asList("$status", "NEW")
                    )
                ).append("then", "Pending")
            )).append("default", "Other")
        );

        Document discountFallback = new Document(
            "$ifNull",
            Arrays.asList("$discount", 0)
        );

        Document project = new Document("$project",
            new Document("_id", 1)
                .append("status", 1)
                .append("statusLabel", statusLabel)
                .append("effectiveDiscount", discountFallback)
        );

        List<Bson> pipeline = Arrays.asList(project);

        collection.aggregate(pipeline)
            .forEach(System.out::println);
    }
}
~~~

This snippet assumes `collection` has been obtained from a properly configured `MongoClient`. If using Spring Data MongoDB, you can also express `$cond`/`$switch`/`$ifNull` via the aggregation DSL or BSON pipeline depending on version capabilities.

**Important:** The Java API does not automatically fix document type errors. If `discount` holds a string or boolean, `$ifNull` still preserves that type just like in `mongosh`. Java DTO classes should declare expected types clearly and handle missing/null cases.

### 20.1. Keep Expressions and API Contracts Consistent

Suppose an endpoint returns:

~~~json
{
  "orderId": "ORD-101",
  "statusLabel": "Paid",
  "effectiveDiscount": 100000
}
~~~

If the aggregation sometimes returns a number and sometimes a string, the Java deserializer may fail or force unsafe use of `Object`. Standardize output types using `$convert` and validators instead of only handling null.

### 20.2. Test Both Values and Field Presence

When using `$$REMOVE`, tests should not only check value equality:

~~~text
expected warning == null
~~~

because a **non-existent field** differs from a field present with a `null` value. Tests should verify whether the document contains the key, such as `containsKey("warning")` on the appropriate object type.

---

## 21. Common Mistakes and How to Handle Them

### Mistake 1 — Using `$cond` Without else

Incorrect:

~~~javascript
{
  $cond: {
    if: { $eq: ["$status", "PAID"] },
    then: "PAID"
  }
}
~~~

`$cond` requires all three: `if`, `then`, `else`. Write completely:

~~~javascript
{
  $cond: {
    if: { $eq: ["$status", "PAID"] },
    then: "PAID",
    else: "OTHER"
  }
}
~~~

### Mistake 2 — `$switch` Without default Encountering a New Status

When no branch matches and there is no `default`, the pipeline may error. Add a `default` according to policy and monitor unknown statuses.

### Mistake 3 — Placing a Broad Branch Before a Narrow Branch

For example, checking `amount ≥ 500,000` before `amount ≥ 1,000,000` causes the `HIGH` group to never receive large records. Place specific/higher-priority branches first.

### Mistake 4 — Assuming `$ifNull` Replaces 0, false, and Empty Strings

`$ifNull` only replaces nullish values, so `0`/`false`/`""`/`[]` are preserved. If empty strings must be treated as missing, write an explicit condition.

### Mistake 5 — Using `$ifNull` to Fix Wrong-Type Strings

`$ifNull` does not convert `"900000"` into the number 900,000. Use `$convert` with `onError` and `onNull`, and define how wrong-type data should be handled.

### Mistake 6 — Not Distinguishing Missing from null

`$ifNull` merges missing and null. If you need to distinguish older records lacking the field from explicit nulls, use `$type` and check `"missing"`/`"null"`.

### Mistake 7 — Using `$exists` as an Aggregation Expression

`$exists` is a query predicate, not an expression operator you can place directly in the `if` slot of `$cond`. Inside aggregation expressions, use `$type` and compare against `"missing"` when checking field existence.

### Mistake 8 — Confusing a Field Path with a Literal String Starting with `$`

`"$amount"` in an expression is a field reference. To get that literal string, use `{ $literal: "$amount" }`.

### Mistake 9 — Using a Newly Computed Field in the Same Stage as If It Were Already Available

A `$set` stage computing `amountDecimal` and `amountBand` and referencing `"$amountDecimal"` in the same stage may not read the new value as intended. Split into two stages to ensure `amountBand` is calculated from the previous stage's output.

### Mistake 10 — Using `$$REMOVE` and Assuming the Database Was Updated

`$$REMOVE` inside `aggregate()` shapes output and does not write back to the collection. Only when used inside a write operation like an update pipeline can it modify stored documents.

### Mistake 11 — Using `$map` on a Wrong-Type Field

`$map` requires its input to be an array or nullish per its semantics; string/object input can cause an error. Check `$isArray` or enforce schema validation.

### Mistake 12 — Using `$gte` on String-Numbers and Assuming Monetary Comparison

`$gte` across differing BSON types follows type-comparison rules. Normalize fields to Decimal128/integer before financial classification.

### Mistake 13 — Having No Label for Invalid Data

If a missing `amount` falls back to `0`, a report might treat an order with missing data as a zero-dollar order. Add a status/warning field or exclude it from sums according to policy.

### Mistake 14 — Running Dynamic Computations Before Index-Eligible Filters

If you have to process millions of documents with `$convert` and `$switch` only to filter a small subset, check whether you can `$match` early on normalized, indexed fields.

### Mistake 15 — Using `$project`/`$set` Without Understanding Output Differences

`$project` can drop unlisted fields. `$set`/`$addFields` keeps existing fields and adds/overwrites specified ones. Choose the stage according to the output contract rather than swapping them arbitrarily.

---

## 22. Process for Designing Conditional Expressions for APIs and Reports

### Step 1 — Define Business Semantics

For example, what does "no discount" mean?

- Are both missing and null treated as `0`?
- Is `discount: false` invalid data?
- Should the string `"50000"` be accepted and converted?
- Are negative discounts allowed?
- Do we need to know which records deviate from the schema?

Do not write fallbacks before answering these questions.

### Step 2 — Categorize Input Data

Sample documents across states:

~~~text
missing | null | 0 | false | "" | number | numeric string | object | array
~~~

Especially with legacy data, check the type distribution instead of assuming all fields are uniform.

### Step 3 — Choose the Minimal Sufficient Expression

- Two outcomes: `$cond`.
- Multiple prioritized branches: `$switch`.
- Nullish fallback: `$ifNull`.
- Distinguish missing from null: `$type` + condition.
- Type check/conversion: `$isNumber`/`$convert`.
- Omit field when inapplicable: `$$REMOVE`.

### Step 4 — Specify Output Types

If `netAmount` is Decimal128, do not let one branch return the string `"unknown"` while another returns a decimal if the DTO requires numeric values. Separate numeric fields from warning fields.

### Step 5 — Use Early `$match` Whenever Possible

Filter on indexed source fields before heavy expression evaluation. If you can only filter on a computed field, measure cost with `explain` and consider materialization.

### Step 6 — Test Edge Cases

Use a dataset containing missing, null, `0`, `false`, empty string, invalid type, unknown status, empty array, absent nested field, and numeric string.

### Step 7 — Distinguish Read Projections from Write Migrations

If you only need response fallbacks, use read aggregation. If you want to persist new fields, plan the update pipeline, auditing, schema validator, and rollback strategy.

### Step 8 — Monitor Unusual Data

A `default` branch such as `"UNKNOWN"` should have counting or reporting when triggered so data errors are not silently masked for months.

---

## 23. Practice Exercises

### Exercise 1 — Two `$cond` Syntaxes

Using documents ORD-101 and ORD-102:

1. Write object-form `$cond` producing `amountLevel` = `HIGH` if `amount ≥ 1,000,000`, else `NORMAL`.
2. Rewrite in array form.
3. Compare the results of both queries.
4. Extend to ORD-105 (which has a string `amount`) and analyze why normalization is required before applying in production.

### Exercise 2 — Status Classification with `$switch`

Create `statusLabel`:

- NEW → CHO_XU_LY.
- PAID → DA_THANH_TOAN.
- CANCELLED → DA_HUY.
- REFUNDED → HOAN_TIEN.
- All other cases → UNKNOWN.

Try reordering branches and removing `default`; explain priority order and behavior when `status` is missing.

### Exercise 3 — `$ifNull` and the Value 0

On the lab data, compute `effectiveDiscount` using `$ifNull: ["$discount", 0]`. List the results for ORD-102, ORD-103, ORD-104, ORD-105, and ORD-107. Why does `0` not trigger the fallback? Why are the string and `false` preserved?

### Exercise 4 — Multi-Source Fallback (MongoDB 5.0+)

Create `chargeableShippingFee` prioritizing:

1. `shippingFee`.
2. `estimatedShippingFee`.
3. `0`.

Compare ORD-102, ORD-104, and ORD-103. Also write a nested `$ifNull` version compatible with two-argument syntax.

### Exercise 5 — Missing vs. null

Use `$type` and `$switch` to produce `discountState` with the values:

- MISSING
- EXPLICIT_NULL
- NUMERIC
- INVALID_TYPE

Explain ORD-103, ORD-104, ORD-102, and ORD-107.

### Exercise 6 — Omitting a Field

Create a `warning` field using `$cond`:

- If status is CANCELLED → `"Cancelled order"`.
- Otherwise → `$$REMOVE`.

Compare against an `else` returning `null`. Check for the presence of the `warning` key in the output.

### Exercise 7 — Fixing Wrong-Type Numeric Data

Create `amountDecimal` using `$convert`, handling `onError`/`onNull`. Create `amountBand`:

- UNKNOWN if unconvertible.
- HIGH if `≥ 1,000,000`.
- MEDIUM if `≥ 500,000`.
- LOW otherwise.

Verify ORD-101, ORD-102, ORD-105, ORD-106, and ORD-109. Do not perform direct comparisons on string `amount` values.

### Exercise 8 — Empty String as Business-Missing

ORD-102 has `nickname: ""` and `fullName: "Trần Bình"`. Construct `displayName` so that:

- Non-empty string `nickname` takes priority.
- If `nickname` is missing/null/empty, use `fullName`.
- If `fullName` is also missing/null, use `"Customer"`.

Why does plain `$ifNull` fail to handle an empty `nickname`?

### Exercise 9 — Missing or Wrong-Type items Array

Create three lab documents with:

- `items` as a valid array.
- `items` missing.
- `items` as a schema-invalid string.

Use `$isArray`, `$cond`, and `$map` to avoid input type errors while emitting `itemsWarning` when the field is not an array. Do not mask bad data with an empty array without reporting it.

### Exercise 10 — Group Report and Invalid Metrics

Group orders by `status` and compute:

- `orderCount`.
- `totalKnownAmount` converted to decimal.
- `unknownAmountCount`.
- `paidOrderCount` using `$cond` inside `$sum`.

Explain how to distinguish a valid order with `amount: 0` from an order missing `amount`.

### Exercise 11 — Update Pipeline

In the lab collection, use `updateMany` with a pipeline to:

- Backfill `shippingFee = 0` for documents with nullish `shippingFee`.
- Store `accountingLabel` only when `status` is `PAID`; otherwise `$$REMOVE`.
- Check records before/after and verify idempotency when re-run.

Do not run update commands in production.

### Exercise 12 — Performance and Indexes

On a sufficiently large dataset:

1. Compare filtering `status: "PAID"` first and then converting `amount` versus converting all `amount` values before matching.
2. Create an index on `status` if appropriate for the workload.
3. Use `explain` to inspect the query plan and `docsExamined`.
4. Discuss when `amountBand` should be materialized and indexed.
5. Evaluate the write cost when `amountBand` must be kept in sync with `amount`.

---

## 24. Review Questions

1. What syntax forms does `$cond` have? What components are required?
2. Which branch does `$switch` select if multiple cases are true?
3. When does `$switch` throw an error if `default` is omitted?
4. How does `$ifNull` differ from `$cond` in how it chooses a result?
5. From which version does `$ifNull` support multiple inputs?
6. Does `$ifNull` treat `0` as null?
7. Does `$ifNull` treat `false` as null?
8. Does `$ifNull` replace an empty string with the fallback?
9. How do missing and BSON null differ?
10. What value can `$type` return on a missing field?
11. Why can the query `{ field: null }` match documents missing the field?
12. When checking for a missing field inside an expression, why can't `$exists` be used directly?
13. When should `$$REMOVE` be used instead of `null`?
14. Does `$$REMOVE` in `aggregate` automatically modify the database?
15. How should string-number data be handled before arithmetic comparisons?
16. How do `$convert.onError` and `$convert.onNull` differ?
17. Why should a pipeline retain a data-error status field instead of always falling back to `0`?
18. When should nested `$cond` be used versus `$switch`?
19. Why does the order of branches in `$switch` matter?
20. Does using `$ifNull` inside an array avoid all type errors?
21. How does `$isArray` assist `$map`?
22. Why should a field newly created in a previous stage be used in the next stage?
23. When should a computed field be materialized?
24. How does `$match` with a query predicate differ in index usage from a computed expression inside `$expr`?
25. What safety measures are needed when modifying data via an update pipeline?

---

## 25. Summary

In MongoDB aggregation, **`$cond`**, **`$switch`**, and **`$ifNull`** solve three common decision patterns:

- **`$cond`**: chooses between two branches based on a boolean condition, supports object and array forms, and requires both true and false branches.
- **`$switch`**: describes multiple ordered branches, selects the **first true case**, and should include a `default` to handle unrecognized data.
- **`$ifNull`**: selects a replacement value when an input is nullish; in MongoDB 5.0+, it can check multiple sources in priority order.

Missing data is the most common source of bugs:

- **Missing** differs from **null**, and both differ from **0**, **false**, **`""`**, or **`[]`**.
- `$ifNull` does not automatically fix wrong-type data.
- `$type` helps distinguish missing, null, and BSON types.
- `$convert`, `$isNumber`, and `$isArray` help control calculations and array transformations.
- `$$REMOVE` is used to omit an output field when needed instead of keeping a `null` value.
- In critical calculations, avoid converting all data errors to `0` and erasing the audit trail.

A good pipeline has **clear business semantics, handles edge cases, returns consistent data types, preserves error visibility, and uses indexes and compute resources reasonably**.

## Official MongoDB Reference Documentation

- [MongoDB Manual — $cond](https://www.mongodb.com/docs/manual/reference/operator/aggregation/cond/)
- [MongoDB Manual — $switch](https://www.mongodb.com/docs/manual/reference/operator/aggregation/switch/)
- [MongoDB Manual — $ifNull](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ifNull/)
- [MongoDB Manual — $type (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [MongoDB Manual — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB Manual — $isNumber](https://www.mongodb.com/docs/manual/reference/operator/aggregation/isNumber/)
- [MongoDB Manual — $isArray](https://www.mongodb.com/docs/manual/reference/operator/aggregation/isArray/)
- [MongoDB Manual — $map](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/)
- [MongoDB Manual — $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [MongoDB Manual — $addFields / $set](https://www.mongodb.com/docs/manual/reference/operator/aggregation/addFields/)
- [MongoDB Manual — Aggregation Variables / $$REMOVE](https://www.mongodb.com/docs/manual/reference/aggregation-variables/)
- [MongoDB Manual — Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
