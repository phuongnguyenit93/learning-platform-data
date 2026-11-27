# Validating Aggregation Expressions on `null`, Wrong-Type, and Missing Fields in MongoDB

Aggregation pipelines are a powerful tool for computing and transforming documents in MongoDB. An expression such as `$multiply`, `$size`, `$trim`, or `$dateToString` is easy to write when every document shares a clean structure. Problems arise when real-world data is inconsistent: one record has `amount: null`, another lacks `amount` altogether, a third stores `amount` as the string `"99.50"` instead of a numeric type, and a fourth contains an invalid array.

These states **do not have the same meaning**, and aggregation expressions **do not handle them under a single uniform rule**. Some operators return `null`, some keep the value unchanged, some compare by BSON type order, and others fail the entire pipeline. Therefore, expression validation must be grounded in **value, BSON type, and field existence**, rather than testing only against a "clean" sample document.

This lesson belongs to the **Aggregation Expressions** chapter and focuses on techniques for building expressions resilient to anomalous data:

- Identifying **missing** fields, BSON **Null** fields, wrong-type values, and valid boundary values such as `0`, `""`, and `[]`.
- Using `$type`, `$isNumber`, `$isArray`, `$ifNull`, `$cond`, and `$switch` to **classify before computing**.
- Using `$convert` with `onError`/`onNull` when controlled type conversion is needed.
- Guarding **numeric, string, array, and date/time** expressions against real-world data errors.
- Designing test suites and verifying outputs via `mongosh` or the MongoDB Java Sync Driver.

## 1. Four Frequently Confused Data States

Consider these documents:

```javascript
{ _id: "a", amount: NumberInt(100) }
{ _id: "b", amount: null }
{ _id: "c" }
{ _id: "d", amount: "100" }
```

On the application side, all four records might get rendered as "100 or blank," yet at the MongoDB level:

| Document | State of `amount` field | BSON Type | Meaning in aggregation |
| --- | --- | --- | --- |
| `a` | Field present, integer value | `int` | Can be used as a numeric operand |
| `b` | Field present, `null` value | `null` | An explicit Null value |
| `c` | Field absent | `missing` when using aggregation `$type` | No value to reference |
| `d` | Field present, digits stored as string | `string` | **Not automatically a number** in every operator |

Several key points:

1. **Missing is not Null**: `{ amount: null }` still has the `amount` field; document `c` does not have this field.
2. **A numeric-looking string is not a BSON number**: `"100"` differs from `NumberInt(100)`; it can be converted when business policy allows.
3. **Boundary values are not automatically errors**: `0`, empty string `""`, and array `[]` are present values with concrete types.
4. **Not every operator accepts every input type**: `$size` requires an array, while `$trim` requires an appropriate string.

A safe workflow is typically:

```text
Input document
       |
       v
Check field existence and BSON type
       |
       +---- Valid -------------> Evaluate expression
       |                              |
       |                              v
       |                         Expected result
       |
       +---- Null / missing ----> Intentional fallback value
       |
       +---- Wrong type --------> Report error, attach error label,
                                  or convert under strict control
```

The crux is **distinguishing data defects from valid business values** before deciding whether to substitute a value.

## 2. Creating a Test Dataset with Both Valid and Anomalous Cases

In `mongosh`, select the practice database:

```javascript
use mongo_expression_lab
```

Run once on a new or empty `expressionCases` collection:

```javascript
db.expressionCases.insertMany([
  {
    _id: "ok",
    amount: NumberDecimal("120.50"),
    quantity: NumberInt(2),
    tags: ["mongodb", "java"],
    title: "  MongoDB Basics  ",
    occurredAt: ISODate("2026-11-10T14:20:00Z")
  },
  {
    _id: "zero",
    amount: NumberInt(0),
    quantity: NumberInt(0),
    tags: [],
    title: "",
    occurredAt: ISODate("2026-11-11T14:20:00Z")
  },
  {
    _id: "null",
    amount: null,
    quantity: null,
    tags: null,
    title: null,
    occurredAt: null
  },
  {
    _id: "missing"
    // Missing amount, quantity, tags, title, occurredAt
  },
  {
    _id: "numericString",
    amount: "99.50",
    quantity: "3",
    tags: ["mongodb"],
    title: 42,
    occurredAt: "2026-11-12T00:00:00Z"
  },
  {
    _id: "badString",
    amount: "N/A",
    quantity: "unknown",
    tags: "mongodb",
    title: ["not", "a", "string"],
    occurredAt: "yesterday"
  },
  {
    _id: "partial",
    amount: NumberInt(10),
    quantity: NumberInt(3),
    tags: [null],
    title: "  Data  ",
    occurredAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "wrongObject",
    amount: [10],
    quantity: [1],
    tags: { first: "mongodb" },
    title: true,
    occurredAt: { year: 2026 }
  },
  {
    _id: "negative",
    amount: NumberInt(-10),
    quantity: NumberInt(-2),
    tags: ["java"],
    title: "   ",
    occurredAt: ISODate("2026-11-13T03:00:00Z")
  },
  {
    _id: "boolean",
    amount: true,
    quantity: false,
    tags: [],
    title: "Article",
    occurredAt: NumberInt(123)
  },
  {
    _id: "mixedTags",
    amount: NumberDecimal("33.25"),
    quantity: NumberInt(2),
    tags: ["mongodb", NumberInt(1)],
    title: "Report",
    occurredAt: ISODate("2026-11-13T10:00:00Z")
  }
])
```

Note:

- `NumberInt(0)` is a valid integer and differs from `null`.
- `NumberDecimal("120.50")` is Decimal128, not a string.
- `ISODate(...)` creates a BSON Date; the string `"2026-11-12T00:00:00Z"` still has type String.
- `tags: []` has type Array and length 0; `tags: [null]` has type Array and length 1.
- `tags: { first: "mongodb" }` has type Object, not Array.

This dataset intentionally contains many anomalous values. It is meant for **testing expressions**, not as a schema acceptable in production systems. The read commands in the following sections do not mutate documents. Do not re-insert duplicate `_id` values into the same collection, as duplicate key errors will occur.

## 3. Using Aggregation `$type` to Identify What a Field Is

In aggregation, `$type` returns a string describing the BSON type of an expression's value:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      quantityType: { $type: "$quantity" },
      tagsType: { $type: "$tags" },
      titleType: { $type: "$title" },
      occurredAtType: { $type: "$occurredAt" }
    }
  },
  { $sort: { _id: 1 } }
])
```

For example, notable values of `amountType` are:

| `_id` | Source `amount` | `{$type: "$amount"}` |
| --- | --- | --- |
| `ok` | `NumberDecimal("120.50")` | `"decimal"` |
| `zero` | `NumberInt(0)` | `"int"` |
| `null` | `null` | `"null"` |
| `missing` | Field absent | `"missing"` |
| `numericString` | `"99.50"` | `"string"` |
| `badString` | `"N/A"` | `"string"` |
| `wrongObject` | `[10]` | `"array"` |
| `boolean` | `true` | `"bool"` |

**Special point:** aggregation `$type` evaluates the **type of the entire referenced value**. If `tags` is `[null]`, `{$type: "$tags"}` returns `"array"`, not `"null"`. If the field does not exist, the expression returns `"missing"`.

### Distinguishing Aggregation `$type` from Query Operator `$type`

```javascript
// Query operator in $match / find:
db.expressionCases.find({
  tags: { $type: "null" }
})

// Aggregation expression in $project:
db.expressionCases.aggregate([
  {
    $project: {
      tagsType: { $type: "$tags" }
    }
  }
])
```

The query operator `$type` can match the **type of an element inside an array**: `tags: [null]` matches `{tags: {$type: "null"}}`. Meanwhile, aggregation `$type` on `"$tags"` reports the type of the **entire field** as Array.

Do not mechanically apply conclusions from `find({field: {$type: ...}})` to `{$type: "$field"}` in `$project` or `$expr`.

### Why Doesn't `$exists` Replace Aggregation `$type`?

`$exists` is a **query operator**, typically used in `find()` or `$match`:

```javascript
db.expressionCases.find({
  amount: { $exists: false }
})
```

It checks whether the key `amount` exists, without distinguishing types when the field is present. Inside `$project` calculation expressions, to detect missing fields use:

```javascript
{
  $eq: [
    { $type: "$amount" },
    "missing"
  ]
}
```

Do not write `{$exists: false}` as an aggregation expression where MongoDB expects a computation; those are two distinct syntactic contexts.

## 4. `$isNumber` and `$isArray`: Checking Types Before Computing

Quick check expressions:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      amountIsNumber: { $isNumber: "$amount" },
      tagsIsArray: { $isArray: "$tags" }
    }
  },
  { $sort: { _id: 1 } }
])
```

`$isNumber` returns `true` when the expression value is a supported BSON numeric type such as Int32, Int64, Double, or Decimal128. It returns `false` for `null`, missing, boolean, array, object, and **strings containing digits**.

`$isArray` returns `true` if the **entire value** is an array, including `[]` or `[null]`. It does not check whether **elements inside** have the expected types.

Notable results:

| Case | `amountIsNumber` | `tagsIsArray` |
| --- | --- | --- |
| `ok` | `true` | `true` |
| `zero` | `true` | `true` |
| `null` | `false` | `false` |
| `missing` | `false` | `false` |
| `numericString` | `false` | `true` |
| `badString` | `false` | `false` |
| `partial` | `true` | `true` |
| `wrongObject` | `false` | `false` |
| `boolean` | `false` | `true` |

If the requirement is not merely "any numeric type" but specifically a **BSON integer**, check:

```javascript
{
  $in: [
    { $type: "$quantity" },
    ["int", "long"]
  ]
}
```

`$isNumber` suits many calculations, yet requiring strictly Int32/Int64 or strictly Decimal128 demands a tighter type policy. Also, `$isNumber: "$amount"` does not guarantee `amount >= 0`.

## 5. `$ifNull`: Replacing Null and Missing Without Fixing Wrong Types

`$ifNull` selects a replacement value when the input is null or missing:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      amountForDisplay: {
        $ifNull: ["$amount", "Not available"]
      },
      titleForDisplay: {
        $ifNull: ["$title", "Untitled"]
      }
    }
  }
])
```

For `null` and `missing`, `amountForDisplay` becomes `"Not available"`. For `amount: 0`, the result remains `0`. For `amount: "N/A"`, the result remains `"N/A"`: **`$ifNull` neither validates nor fixes data types**.

| Input | `$ifNull: ["$amount", 0]` |
| --- | --- |
| `NumberInt(0)` | Keeps `0` |
| `NumberDecimal("25.00")` | Keeps Decimal128 number |
| `null` | Returns `0` |
| Missing | Returns `0` |
| `"99.50"` | Keeps string `"99.50"` |
| `"N/A"` | Keeps string `"N/A"` |
| `[10]` | Keeps array `[10]` |

For reporting, **replacing null with 0 is a business decision**. If `amount: null` means "value not yet confirmed," substituting `0` skews sums and averages. Sometimes you must keep `null`, count missing records separately, or emit an extra status label.

In versions supporting multi-argument `$ifNull`, multiple fallback sources can be checked; the examples here use the two-argument form to keep the core rule clear.

## 6. `$convert`: Controlled Type Conversion Using `onError` and `onNull`

When legacy sources store prices as the string `"99.50"`, a system may wish to convert them to Decimal128 for reports. Using the shorthand conversion:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      amountDecimal: { $toDecimal: "$amount" }
    }
  }
])
```

can make the pipeline **throw an error** upon hitting `amount: "N/A"` or another unconvertible value. A single wrong-type record can fail the entire aggregation command; testing only `"99.50"` is therefore insufficient.

Use `$convert` to control error handling:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      originalType: { $type: "$amount" },
      convertedAmount: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Meaning:

- `input`: expression retrieving the value to convert.
- `to`: target BSON type; `"decimal"` represents Decimal128.
- `onError`: fallback value on conversion errors, such as an invalidly formatted numeric string.
- `onNull`: fallback value when `input` is null or missing.

For `"99.50"`, the result is the corresponding Decimal128. For `"N/A"`, `onError: null` prevents a crash and flags it as unconvertible.

**Important:** successful type conversion **does not equate to business-valid input**. Certain types like booleans have numeric conversion rules in MongoDB, yet if your data contract requires `amount` to be a number or numeric string, you must still **check the source type first**. Never accept every input type blindly just because `$convert` can coerce it to a number.

### 6.1. Allowing Only Specific Source Types

Example ingestion policy: accept BSON numbers and strings convertible to Decimal128; reject booleans and arrays.

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      rawType: { $type: "$amount" },
      safeAmount: {
        $cond: {
          if: {
            $in: [
              { $type: "$amount" },
              ["int", "long", "double", "decimal", "string"]
            ]
          },
          then: {
            $convert: {
              input: "$amount",
              to: "decimal",
              onError: null,
              onNull: null
            }
          },
          else: null
        }
      }
    }
  }
])
```

`true` (`bool`), objects, and arrays are rejected right at the type guard. `"99.50"` converts to Decimal128; `"N/A"` enters the conversion branch and returns `null` via `onError`.

If you need to distinguish **missing**, **null**, **wrong type**, and **unparseable string**, do not return only `safeAmount: null`, because all those causes get collapsed. Retain `rawType` and add validation labels as shown next.

### 6.2. Data Errors Should Not Be Completely Hidden

In some UI pipelines, `onError: null` is acceptable to keep read screens from crashing. However, in financial reports or production ingestion, failed conversions can silently understate totals without anyone noticing.

A better option is returning `sourceType`, `conversionSucceeded`, or counting unconvertible records alongside a plan to repair source data. `$convert` is a conversion tool, **not a substitute for schema validation or data quality monitoring**.

## 7. `$switch`: Classifying Causes of Anomalous Data

`$switch` evaluates multiple cases in order, each with `case` and `then`, plus a `default` branch.

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountStatus: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [{ $type: "$amount" }, "missing"]
              },
              then: "missing"
            },
            {
              case: {
                $eq: [{ $type: "$amount" }, "null"]
              },
              then: "null"
            },
            {
              case: { $isNumber: "$amount" },
              then: "numeric"
            },
            {
              case: {
                $eq: [{ $type: "$amount" }, "string"]
              },
              then: "string"
            }
          ],
          default: "unsupported-type"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Classification of documents:

| Case | `amountStatus` |
| --- | --- |
| `ok`, `zero`, `partial`, `negative`, `mixedTags` | `numeric` |
| `null` | `null` |
| `missing` | `missing` |
| `numericString`, `badString` | `string` |
| `wrongObject`, `boolean` | `unsupported-type` |

`$isNumber` confirms **type**, not sign: `amount: -10` still falls under `numeric`. If business rules disallow negative amounts, add an extra domain constraint.

### Flagging Negative Values Without Cross-Type Comparison

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountIsNonNegative: {
        $cond: {
          if: { $isNumber: "$amount" },
          then: { $gte: ["$amount", 0] },
          else: false
        }
      }
    }
  }
])
```

This expression runs `$gte` only when `amount` is a number. `negative` gets `false`, `zero` gets `true`, and `null`, missing, strings, and booleans get `false`.

**Never write** `{$gte: ["$amount", 0]}` alone assuming every `true` result proves "non-negative number." In aggregation expressions, comparisons between **different BSON types** follow BSON type comparison order rather than numeric coercion. A string can compare against a number by type order, yielding false conclusions about value ranges. Always verify types before numeric comparisons.

## 8. Guarding Numeric Operations: `$multiply`, `$divide`, and Zero

Suppose a document represents a transaction with unit price `amount` and item count `quantity`. The goal is computing `lineTotal = amount * quantity`.

### 8.1. Direct Arithmetic Can Be Unsafe

```javascript
// Suitable only when the source already guarantees valid numeric types
db.expressionCases.aggregate([
  {
    $project: {
      lineTotal: {
        $multiply: ["$amount", "$quantity"]
      }
    }
  }
])
```

The sample collection contains strings, arrays, booleans, and null/missing values, so not every document holds valid operands for multiplication. An operation hitting wrong-type inputs can fail the aggregation command; a `null` policy for one case does not cover every type mismatch.

### 8.2. Checking Types and Bounds Before Multiplying

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      lineTotal: {
        $cond: {
          if: {
            $and: [
              { $isNumber: "$amount" },
              {
                $in: [
                  { $type: "$quantity" },
                  ["int", "long"]
                ]
              },
              {
                $cond: {
                  if: { $isNumber: "$amount" },
                  then: { $gte: ["$amount", 0] },
                  else: false
                }
              },
              {
                $cond: {
                  if: {
                    $in: [
                      { $type: "$quantity" },
                      ["int", "long"]
                    ]
                  },
                  then: { $gte: ["$quantity", 0] },
                  else: false
                }
              }
            ]
          },
          then: { $multiply: ["$amount", "$quantity"] },
          else: null
        }
      }
    }
  }
])
```

In this example:

- `ok`: `120.50 * 2 = 241.00`.
- `zero`: `0 * 0 = 0` — **valid zero**.
- `partial`: `10 * 3 = 30`.
- `mixedTags`: `33.25 * 2 = 66.50`.
- `negative`: returns `null` because negative values are rejected by business policy.
- `numericString`: returns `null` because strings `"99.50"` and `"3"` are not accepted as BSON numbers in this strict expression.
- `null`, `missing`, `badString`, `wrongObject`, `boolean`: return `null` instead of attempting invalid multiplication.

The `$cond` wrappers around comparisons and `$multiply` ensure they run only on validated inputs. Never assume arbitrary `$and` branches always short-circuit in written order to "guard" an error-prone operator. The clean pattern is placing the guarded calculation inside the `then` branch of `$cond`.

### 8.3. Division by Zero: Distinct from Wrong Type

Suppose we need average unit price `amount / quantity`. Even when both are numbers, `quantity = 0` must still be handled:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      averageUnitAmount: {
        $cond: {
          if: {
            $and: [
              { $isNumber: "$amount" },
              { $isNumber: "$quantity" },
              { $ne: ["$quantity", 0] }
            ]
          },
          then: {
            $divide: ["$amount", "$quantity"]
          },
          else: null
        }
      }
    }
  }
])
```

The `zero` case is not treated as "missing data": it is the number `0`, yet **not a valid divisor**. Returning `null` here is a presentation choice for an undefined calculation, not the result of an actual division.

## 9. Guarding String Operations: `$trim`, `$toUpper`, `$strLenCP`

A title-normalization pipeline typically strips whitespace and converts case. However, our sample collection has `title` values that are strings, `null`, missing, numbers, booleans, and arrays.

```javascript
// Unsafe on a collection with wrong-type titles
{
  $project: {
    normalizedTitle: {
      $toUpper: {
        $trim: { input: "$title" }
      }
    }
  }
}
```

`$trim` operates on string values; inputs like `title: 42` or `title: ["x"]` can raise an error. Check the type first:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      titleType: { $type: "$title" },
      normalizedTitle: {
        $cond: {
          if: {
            $eq: [{ $type: "$title" }, "string"]
          },
          then: {
            $toUpper: {
              $trim: { input: "$title" }
            }
          },
          else: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Examples:

- `ok`: trims leading/trailing spaces and converts to `"MONGODB BASICS"` per operator character rules.
- `partial`: from `"  Data  "` becomes a trimmed, uppercased string.
- `zero`: empty string `""` is still a **valid string** and yields `""`, not `null`.
- `negative`: whitespace-only string becomes `""`.
- `numericString`: `title: 42` returns `null` because policy accepts only string inputs.

**Unicode note:** several MongoDB case-conversion operators have limitations on non-ASCII characters depending on operator semantics. When converting Vietnamese letters or performing accurate locale matching, test your server version's behavior and consider collation or normalization in the appropriate layer rather than assuming `$toUpper` is a full Unicode processor.

### Checking Whether a String Is Empty After Trimming

If the requirement is "title must be a non-empty string after removing whitespace":

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      hasNonBlankTitle: {
        $cond: {
          if: {
            $eq: [{ $type: "$title" }, "string"]
          },
          then: {
            $gt: [
              {
                $strLenCP: {
                  $trim: { input: "$title" }
                }
              },
              0
            ]
          },
          else: false
        }
      }
    }
  }
])
```

`$strLenCP` measures length in **Unicode code points**, not raw UTF-8 bytes. `title: ""` and `title: "   "` fail the condition, while strings with non-whitespace content pass.

Never use `$ifNull` alone to check for empty strings: `""` is not Null, and `$ifNull` neither trims nor checks length.

## 10. Guarding Array Expressions: `$size`, `$filter`, `$map`

For `tags`, an application might want to count tags and verify every tag is a string.

### 10.1. `$size` Does Not Accept Every Type

```javascript
// May throw an error when tags is not an array
db.expressionCases.aggregate([
  {
    $project: {
      tagCount: { $size: "$tags" }
    }
  }
])
```

`$size` in aggregation requires an array operand. Missing, null, string, or object fields can fail the pipeline if passed directly into `$size`.

Safe handling:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      tagsType: { $type: "$tags" },
      tagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: { $size: "$tags" },
          else: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Notable results:

| Case | `tags` | `tagCount` |
| --- | --- | --- |
| `ok` | `["mongodb","java"]` | 2 |
| `zero` | `[]` | 0 |
| `partial` | `[null]` | 1 |
| `mixedTags` | `["mongodb",1]` | 2 |
| `null` | `null` | `null` |
| `missing` | Missing | `null` |
| `badString` | `"mongodb"` | `null` |
| `wrongObject` | Object | `null` |

`[null]` has **one element**; `[]` has **zero elements**. `$isArray` separates null/missing from arrays, yet **does not check element types**.

If business rules treat missing fields as empty lists, you could replace `else: null` with `else: 0`. However, that also turns wrong-type strings/objects into `0`, hiding errors. Separate the policy "missing means empty" from "wrong type needs a warning."

### 10.2. Counting Wrong-Type Elements with `$filter`

Requirement: `tags` is an array and **every element is a string**. Checking `$isArray` alone is not enough. Count how many elements are not strings:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      invalidTagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: {
            $size: {
              $filter: {
                input: "$tags",
                as: "tag",
                cond: {
                  $ne: [
                    { $type: "$$tag" },
                    "string"
                  ]
                }
              }
            }
          },
          else: null
        }
      }
    }
  }
])
```

Here:

- `$$tag` is the **element variable** inside `$filter`; `$tags` is the field of the input document.
- `$type: "$$tag"` evaluates the type of the **element currently inspected**.
- `$ne: [..., "string"]` keeps elements whose type is not `"string"`.
- `$size` counts those wrong-type elements.

On the sample data, `partial` has `invalidTagCount = 1` because it contains `null`; `mixedTags` has `invalidTagCount = 1` because it contains the number `1`; `ok` and `zero` have `invalidTagCount = 0`. Non-array fields return `null` so they are **not confused with "valid array with zero invalid elements."**

### 10.3. `$map` Also Requires Input Validation

To transform each tag, `$map` expects `input` to be an array:

```javascript
{
  $map: {
    input: "$tags",
    as: "tag",
    in: "$$tag"
  }
}
```

Per MongoDB semantics, `$map` returns `null` when `input` is null/missing, yet if `input` is a **non-array** (and non-null) value, the operation throws an error. Therefore, when a collection has `tags: "mongodb"` or an object, guard with `$isArray` first.

If applying string functions to each element, guard **both the outer array and each inner element**, rather than checking `$isArray` and assuming `$$tag` is always a string.

### 10.4. Does an Empty Array Satisfy "All Elements Are Valid"?

Under set logic, an empty array contains zero wrong-type elements; "all elements are strings" evaluates to true for an empty array. Yet business logic often also requires **at least one element**. Combine:

```javascript
// A non-empty array
{ $gt: [{ $size: "$tags" }, 0] }
```

with the outer `$isArray` check and the element-type check. **"Valid types"** and **"non-empty"** are two separate constraints.

## 11. Dates: BSON Date Differs from an ISO String

A date in JSON can appear as `"2026-11-12T00:00:00Z"`. In MongoDB, this is still a **BSON String**, not a **BSON Date**. A date-formatting expression like `$dateToString` must not be applied blindly to arbitrary values.

### 11.1. Process Only When the Source Is a Date

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      dateType: { $type: "$occurredAt" },
      dayInVietnam: {
        $cond: {
          if: {
            $eq: [{ $type: "$occurredAt" }, "date"]
          },
          then: {
            $dateToString: {
              format: "%Y-%m-%d",
              date: "$occurredAt",
              timezone: "Asia/Ho_Chi_Minh"
            }
          },
          else: null
        }
      }
    }
  }
])
```

For document `ok`, `occurredAt = 2026-11-10T14:20:00Z` corresponds to **21:20 on 2026-11-10 in Vietnam**, so the date string is `"2026-11-10"`. For `numericString`, the timestamp is a string, so the strict policy returns `null` even though the string looks like an ISO date.

### 11.2. Converting Date Strings Only When Permitted

If system policy permits valid ISO strings, you can try `$convert` to Date:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      originalDateType: { $type: "$occurredAt" },
      convertedDate: {
        $cond: {
          if: {
            $in: [
              { $type: "$occurredAt" },
              ["date", "string"]
            ]
          },
          then: {
            $convert: {
              input: "$occurredAt",
              to: "date",
              onError: null,
              onNull: null
            }
          },
          else: null
        }
      }
    }
  }
])
```

`numericString` has a valid ISO string and converts to a BSON Date; `badString` has `"yesterday"` so conversion fails and returns `null`. Numbers, booleans, and objects are excluded before conversion to prevent unintended date interpretations.

**Do not equate successful conversion with choosing the business timezone.** A timestamp with `Z` denotes UTC; when displaying Vietnam calendar dates, specify the appropriate `timezone` during formatting. For date strings without timezone info, define explicit parsing rules before converting.

## 12. Using `$match` and `$expr` to Filter Wrong-Type Documents

You do not always need to transform every document. Sometimes you want to extract a list of defective records for repair.

### 12.1. Finding Documents Where `amount` Is Not a BSON Number

```javascript
db.expressionCases.aggregate([
  {
    $addFields: {
      amountType: { $type: "$amount" }
    }
  },
  {
    $match: {
      amountType: {
        $nin: ["int", "long", "double", "decimal"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      amountType: 1
    }
  },
  { $sort: { _id: 1 } }
])
```

This query catches missing, null, string, bool, and array entries. Negative numbers are still **numeric types**, so they do not appear in the type-error group; if negatives are disallowed, add a range condition.

### 12.2. Filtering with `$expr` and Aggregation `$type`

```javascript
db.expressionCases.find({
  $expr: {
    $eq: [
      { $type: "$amount" },
      "missing"
    ]
  }
})
```

This selects documents **missing the `amount` field** using an aggregation expression inside a filter. When only checking field absence, the query operator syntax is shorter:

```javascript
db.expressionCases.find({
  amount: { $exists: false }
})
```

### 12.3. Separating Type Errors from Range Errors

Suppose three labels are needed:

- `"invalid-type"`: `amount` is not a BSON number.
- `"negative"`: `amount` is a number, yet less than 0.
- `"valid"`: `amount` is a non-negative number.

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      validationStatus: {
        $cond: {
          if: { $isNumber: "$amount" },
          then: {
            $cond: {
              if: { $gte: ["$amount", 0] },
              then: "valid",
              else: "negative"
            }
          },
          else: "invalid-type"
        }
      }
    }
  }
])
```

This example places missing and null under `invalid-type` because policy requires a numeric field. If missing and null must be reported separately, use `$switch` with `$type` as in section 7.

## 13. Validating Across Multiple Cases, Not Just the Happy Path

An expression is business-verified only when you know **which inputs are accepted, which must be rejected, and the expected output for each group**. A minimal test suite should include:

| Test Category | Sample Value | Question to Answer |
| --- | --- | --- |
| Right type, normal value | `NumberDecimal("120.50")` | Does the calculation return the right value? |
| Zero value | `NumberInt(0)` | Is it confused with null/missing? |
| Negative value | `NumberInt(-10)` | Is it valid per business rules? |
| Null value | `null` | Does the expression return null, fallback, or error? |
| Missing field | Key absent | Is missing distinguished from null? |
| Numeric string | `"99.50"` | Is it converted, and is that permitted? |
| Invalid string | `"N/A"` | Does a conversion error break the pipeline? |
| Boolean | `true` | Is it unintentionally cast to a number? |
| Wrongly typed array | `[10]` instead of number | Is it fed into numeric arithmetic? |
| Empty array | `[]` | Is length 0 considered valid? |
| Array containing Null | `[null]` | Is it confused with a Null field? |
| Array with wrong-type elements | `["mongodb", 1]` | Is each element validated? |
| Empty/whitespace string | `""`, `"   "` | Is "right type" separated from "has content"? |
| Date as string | `"2026-11-12T00:00:00Z"` | Is it converted to a BSON Date or rejected? |

### 13.1. Consolidating Diagnostics into a Single Read Query

You can build a pipeline that only **inspects and labels** every case:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      amountIsNumber: { $isNumber: "$amount" },
      tagsType: { $type: "$tags" },
      tagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: { $size: "$tags" },
          else: null
        }
      },
      titleType: { $type: "$title" },
      dateType: { $type: "$occurredAt" }
    }
  },
  { $sort: { _id: 1 } }
])
```

This test dataset exposes **type errors**, **missing fields**, and **boundary values** side by side. When designing a real pipeline, define the expected output table first and compare it against MongoDB's actual output on the target server version.

### 13.2. Verifying Distributions with Aggregation `$group` by State

Total cases can be summarized by `amount` type:

```javascript
db.expressionCases.aggregate([
  {
    $group: {
      _id: { $type: "$amount" },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

This summarizes inconsistent data distributions without manually inspecting documents one by one. Apply the same pattern to `tags`, `title`, and `occurredAt`.

**Note:** `$group` by `"$amount"` differs from `$group` by `{$type: "$amount"}`. The first groups by **value**; the second groups by **type**. When hunting for schema drift, the second serves the goal directly.

## 14. Java MongoDB Sync Driver: Running Safe Diagnostic Pipelines

The Java Sync Driver can send aggregation pipelines as `Document` objects or `Aggregates` helpers. For nested expressions, `Document.parse()` lets you write syntax closely matching `mongosh`.

Java 15+ example:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public class AggregationTypeDiagnostics {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        List<Bson> pipeline = List.of(
            Document.parse("""
                {
                  "$project": {
                    "_id": 1,
                    "amountType": { "$type": "$amount" },
                    "amountIsNumber": { "$isNumber": "$amount" },
                    "safeAmount": {
                      "$convert": {
                        "input": "$amount",
                        "to": "decimal",
                        "onError": null,
                        "onNull": null
                      }
                    },
                    "tagCount": {
                      "$cond": {
                        "if": { "$isArray": "$tags" },
                        "then": { "$size": "$tags" },
                        "else": null
                      }
                    }
                  }
                }
                """),
            Document.parse("""
                { "$sort": { "_id": 1 } }
                """)
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_expression_lab");
            MongoCollection<Document> collection =
                database.getCollection("expressionCases");

            collection.aggregate(pipeline)
                .forEach(result -> System.out.println(result.toJson()));
        }
    }
}
```

This snippet requires a compatible `mongodb-driver-sync` dependency and the `MONGODB_URI` environment variable. It **does not modify data**. `Document.parse` parses JSON pipeline syntax, not shell JavaScript helpers like `NumberDecimal(...)` or `ISODate(...)`; those values were created earlier when inserting via `mongosh`.

This example uses `$convert` so `"N/A"` does not fail the command, yet as noted earlier, the ability to convert a boolean to a number **does not mean** it passes strict policy. In production pipelines, add a source-type guard as in section 6.1 and retain diagnostic fields to surface bad data.

## 15. When Is Schema Validation Needed Instead of Just Fixing Read Expressions?

Safe expressions keep endpoints from crashing on anomalous data, yet **they do not fix the root cause**. If the system requires:

- `amount` must be non-negative Decimal128;
- `quantity` must be non-negative Int32;
- `tags`, if present, must be an array of strings;
- `occurredAt` must be a BSON Date;

encode those rules in the collection's schema validation:

```javascript
db.createCollection("validatedEvents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["amount", "quantity", "occurredAt"],
      properties: {
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        quantity: {
          bsonType: "int",
          minimum: 0
        },
        tags: {
          bsonType: "array",
          items: { bsonType: "string" }
        },
        occurredAt: {
          bsonType: "date"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

This creates a new `validatedEvents` collection without touching `expressionCases`, which is kept for learning wrong-type cases. It demonstrates **preventing bad types on write** rather than only guarding on read.

When an existing collection already contains mixed data, adding a validator does not automatically migrate or repair legacy documents; prepare a migration strategy and appropriate validation rollout. Alongside database validation, the application should validate payloads, manage BSON types strictly, and never silently coerce invalid strings into `0`.

## 16. Common Mistakes When Validating Aggregation Expressions

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `$size` causes pipeline error | Field is null/missing/string/object instead of array | Use `$isArray` and `$cond` before `$size` |
| `$trim` or `$strLenCP` errors | Field is not a string | Check `{$type: "$field"} = "string"` |
| `$toDecimal` fails the entire query | `"N/A"` string or unconvertible type encountered | Use `$convert` with `onError` and handle data errors |
| `"99.50"` rejected by `$isNumber` | String is not a BSON numeric type | Convert intentionally if business rules permit |
| `amount: 0` treated as missing | Application treats all falsy values as missing | Check type and `null` explicitly; `0` is a valid number |
| `$ifNull` passes through wrong-type string/object | Operator only replaces null/missing | Add `$type`, `$isNumber`, `$isArray` |
| `$gte: ["$amount", 0]` gives confusing results | Cross-type BSON comparison, not numeric validation | Guard with `$isNumber` before comparing |
| ISO date string not formatted as BSON Date | String differs from Date | Convert by policy or enforce storing Dates |
| `tags: [null]` has type `array`, not `null` | Aggregation `$type` evaluates the whole field | Use `$filter`/`$map` to inspect individual elements |
| `$isArray` returns true on array mixing numbers and strings | Checks only the outer array type | Validate elements with `$filter` and `$type` |
| `$ifNull` merges missing with null | Both trigger fallback | Check `$type` beforehand if separate counts are needed |
| `$group` by field value misses type distribution | Distinct values form distinct groups | Group by `{$type: "$field"}` to tally types |
| `onError: null` hides error counts | Conversion errors vanish in output | Add status labels and count records needing repair |
| Expression passes on 1 document, fails on collection | Test set had only clean cases | Build fixtures covering null/missing/wrong-type/boundary |

When an aggregation errors out, inspect the **operator and offending value type** reported, then narrow inputs with `$match` or inspect `$type` via a standalone diagnostic pipeline. Never simply replace all invalid values with `null` without understanding whether they stem from schema drift, serialization bugs, or ingestion pipelines.

## 17. Practice Exercises

Exercises use `expressionCases` from section 2 with read-only pipelines that do not mutate data.

### Exercise 1. Distinguishing Missing from Null

Write an aggregation outputting only `_id` and `amountType` such that `missing` gives `"missing"` and `null` gives `"null"`.

**Answer:**

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" }
    }
  }
])
```

Using `$ifNull` to replace both with a single fallback loses the distinction requested.

### Exercise 2. Counting Tags Without Failing on Strings

Write a `tagCount` expression returning element count only when `tags` is an array, otherwise returning `null`.

**Answer:**

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      tagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: { $size: "$tags" },
          else: null
        }
      }
    }
  }
])
```

`zero` has `tagCount = 0`; `partial` has `tagCount = 1`; `badString` has `tagCount = null`.

### Exercise 3. Converting Numeric Strings Without Breaking the Pipeline

Requirement: convert `amount` to Decimal128 if convertible, returning `null` on conversion error or null/missing.

**Answer:**

```javascript
{
  $convert: {
    input: "$amount",
    to: "decimal",
    onError: null,
    onNull: null
  }
}
```

However, if policy also requires **rejecting booleans and objects based on source type**, combine with `$cond` checking `$type`, since successful numeric conversion alone does not guarantee valid source data.

### Exercise 4. Checking Non-Negative Integers

Write an expression returning `true` when `quantity` is BSON `int` or `long` and non-negative; otherwise `false`.

**Reference answer:**

```javascript
{
  $cond: {
    if: {
      $in: [
        { $type: "$quantity" },
        ["int", "long"]
      ]
    },
    then: { $gte: ["$quantity", 0] },
    else: false
  }
}
```

`zero` passes; `negative`, `null`, `missing`, and `numericString` fail.

### Exercise 5. Finding Arrays with Wrong-Type Elements

Requirement: `tags` is an array of strings; if it is an array, count non-string elements. From the sample data, which documents have `invalidTagCount > 0`?

**Answer:** Use `$filter` with condition:

```javascript
cond: {
  $ne: [
    { $type: "$$tag" },
    "string"
  ]
}
```

then `$size` of the filtered array, guarded outside with `$isArray`. Both `partial` and `mixedTags` have 1 wrong-type element. Array `[]` has 0 wrong-type elements, not `null`.

### Exercise 6. Spotting Cross-Type Comparisons

Someone writes:

```javascript
{
  $project: {
    validAmount: { $gte: ["$amount", 0] }
  }
}
```

and concludes `validAmount: true` always proves `amount` is a non-negative number. Why is this conclusion unsafe?

**Answer:** Aggregation comparisons follow BSON cross-type ordering rules rather than validating numeric types. Use `$isNumber` or `$type` to confirm type before comparing bounds inside `$cond`.

### Exercise 7. Validating Empty and Whitespace Strings

Requirement: `title` must be a string containing at least one code point after `$trim`. Name two test documents that have string type yet still fail validation.

**Answer:** `zero` has `title: ""` and `negative` has `title: "   "`; both have type string, yet trimmed length equals `0`. Use `$cond` to check `$type`, then `$strLenCP` on `$trim` as in section 9.

### Exercise 8. Date Strings vs. BSON Dates

Requirement: format the date in `Asia/Ho_Chi_Minh` only for documents whose `occurredAt` is a BSON Date. For `numericString` containing an ISO string, the result must be `null`.

**Answer:**

```javascript
{
  $cond: {
    if: {
      $eq: [{ $type: "$occurredAt" }, "date"]
    },
    then: {
      $dateToString: {
        format: "%Y-%m-%d",
        date: "$occurredAt",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    else: null
  }
}
```

This is a strict Date-acceptance policy. If ISO strings are allowed, add a `$convert` or `$dateFromString` step with error handling and consistent timezone rules.

## 18. Conclusion: Validate Types First, Transform After

Validating an aggregation expression is more than running a command on one sample document. A reliable pipeline needs an **explicit data contract**:

1. **Identify data** with `$type`: missing, null, string, number, bool, array, object, date.
2. **Classify validity**: `$isNumber`, `$isArray`, value bounds, and element type constraints.
3. **Place calculations in guarded branches**: `$cond` or `$switch` so type-sensitive operators never process bad inputs.
4. **Convert types only by policy**: use `$convert` with `onError`/`onNull` while avoiding turning invalid data into valid-looking numbers unintentionally.
5. **Preserve diagnostics when needed**: never casually collapse missing, null, and wrong-type into a single label or `0`.
6. **Test edge cases**: `0`, `""`, `[]`, `[null]`, numeric strings, invalid strings, booleans, objects, and BSON Dates.
7. **Prevent bad data at the source** with schema validation, payload validation, and proper migrations; resilient read expressions are only one defense layer.

The key takeaway is that **null, wrong-type values, and missing fields can trigger different behaviors depending on the operator**. Once you know exactly what types enter each expression, you can build MongoDB pipelines that remain both resilient on real-world data and transparent about records that violate the data contract.
