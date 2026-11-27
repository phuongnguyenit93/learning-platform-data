# Processing Arrays with `$map`, `$filter`, `$reduce`, and Set Operators in MongoDB

## 1. Why Process Arrays Directly in Aggregation?

In the MongoDB document model, arrays are often used to store data tightly coupled to a parent document: order line items, article tags, user roles, measurement readings, or short event histories.

For example, an order:

```javascript
{
  _id: "O01",
  customerId: "C01",
  status: "PAID",
  tags: ["vip", "sale", "vip"],
  items: [
    { sku: "A", qty: 2, unitPrice: 100, active: true },
    { sku: "B", qty: 1, unitPrice: 200, active: false }
  ]
}
```

From this document, an application may need to:

- **Transform each line item** into an object containing `sku` and `lineTotal = qty × unitPrice`.
- **Filter** only active line items (`active: true`).
- **Accumulate** a total amount or count of line items directly inside a single document.
- **Deduplicate** `tags` or compare tags against a target tag set.
- **Combine** multiple tag arrays, find intersections or differences, and check set equality or subset relationships.

MongoDB provides **aggregation expressions** for these tasks:

| Group | Operator | Role |
|---|---|---|
| Element transformation | `$map` | Maps each element to a new value |
| Element selection | `$filter` | Keeps elements satisfying a Boolean condition |
| Folding / accumulation | `$reduce` | Iterates an array left-to-right, carrying an accumulated value |
| Set operations | `$setUnion`, `$setIntersection`, `$setDifference` | Union, intersection, and difference treating arrays as sets |
| Set comparisons | `$setEquals`, `$setIsSubset` | Compares value sets, ignoring order and duplicates |
| Set truthiness checks | `$anyElementTrue`, `$allElementsTrue` | Checks whether any or all elements are truthy |

**Key point:** `$map`, `$filter`, `$reduce`, and the set operators here are **value-computing expressions**, not pipeline stages. They are typically placed inside `$project`, `$set`, or other contexts accepting aggregation expressions.

```text
                  A document containing items[]
                               |
             +-----------------+------------------+
             |                 |                  |
           $map              $filter           $reduce
             |                 |                  |
    array of new values  filtered elements   one accumulated value
             |                 |                  |
             +-----------------+------------------+
                               |
                     $project / $set
                               |
                     output document

       tags[] + marketingTags[] --> $setUnion / $setIntersection / ...
```

The rest of the lesson progresses from basic syntax to combining multiple operators, along with correctness, performance, and data-type considerations.

## 2. Preparing the Practice Dataset

The examples use **mongosh** and the test collection `aggArrayLesson`. Insert only once into a collection that does not already contain the `_id` values below:

```javascript
db.aggArrayLesson.insertMany([
  {
    _id: "O01",
    customerId: "C01",
    status: "PAID",
    tags: ["vip", "sale", "vip"],
    coupons: ["WELCOME", "SALE"],
    points: [5, 7, 9],
    items: [
      { sku: "A", qty: 2, unitPrice: 100, active: true },
      { sku: "B", qty: 1, unitPrice: 200, active: false }
    ]
  },
  {
    _id: "O02",
    customerId: "C02",
    status: "PAID",
    tags: ["sale", "new"],
    coupons: ["SALE", "FREESHIP"],
    points: [10, 8],
    items: [
      { sku: "C", qty: 3, unitPrice: 50, active: true }
    ]
  },
  {
    _id: "O03",
    customerId: "C03",
    status: "PENDING",
    tags: [],
    coupons: [],
    points: [],
    items: []
  },
  {
    _id: "O04",
    customerId: "C04",
    status: "PAID",
    tags: ["vip", "new"],
    coupons: ["WELCOME"],
    points: [3],
    items: [
      { sku: "A", qty: 1, unitPrice: 100, active: true },
      { sku: "D", qty: 2, unitPrice: 80, active: true }
    ]
  },
  {
    _id: "O05",
    customerId: "C05",
    status: "PENDING",
    tags: null,
    items: null
    // coupons and points are intentionally omitted.
  },
  {
    _id: "O06",
    customerId: "C06",
    status: "PAID",
    coupons: ["SALE", "WELCOME", "SALE"],
    points: [2, 4],
    items: [
      { sku: "B", qty: 1, unitPrice: 200, active: false }
    ]
    // tags is intentionally omitted.
  }
]);
```

Monetary values are represented as **small integers** so calculations are easy to follow. In real commercial applications, choose an appropriate monetary representation such as integer minor units or BSON Decimal128 along with rounding rules.

| Order | `tags` | Line item count | Total `qty × unitPrice` | Line items with `active: true` |
|---|---|---:|---:|---:|
| O01 | vip, sale, vip | 2 | 400 | A |
| O02 | sale, new | 1 | 150 | C |
| O03 | empty array | 0 | 0 | None |
| O04 | vip, new | 2 | 260 | A, D |
| O05 | null | No valid array | Undefined without normalization | None |
| O06 | Missing field | 1 | 200 | None |

For examples requiring a valid array, we commonly use `$ifNull` to normalize null/missing to `[]`. If a document holds a **String, Number, or Object instead of an Array**, `$ifNull` does not fix the wrong type; section 7 shows how to check with `$isArray`.

## 3. `$map`: Transforming Each Element While Preserving Array Structure

`$map` applies an expression to **each element** of an input array and returns a **result array** with the corresponding outputs.

### 3.1. Syntax

```javascript
{
  $map: {
    input: <arrayExpression>,
    as: "element",
    in: <expressionUsingElement>
  }
}
```

Field meanings:

- `input`: expression returning the array to iterate over.
- `as`: variable name for each element; optional—if omitted, you can use the default variable `$$this`.
- `in`: expression computing the **output value for each element**; reference the variable using `$$variableName` syntax.

Example on a numeric array:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      _id: 1,
      doubledPoints: {
        $map: {
          input: "$points",
          as: "point",
          in: { $multiply: ["$$point", 2] }
        }
      }
    }
  }
]);
```

Result:

```javascript
{
  _id: "O01",
  doubledPoints: [10, 14, 18]
}
```

`$map` does not modify the `points` array stored in the database; here `$project` only **produces a query result field**.

### 3.2. Transforming an Array of Embedded Documents

A more common case is producing a projection of each line item:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            sku: "$$item.sku",
            quantity: "$$item.qty",
            lineTotal: {
              $multiply: [
                "$$item.qty",
                "$$item.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
```

Result:

```javascript
{
  _id: "O01",
  lines: [
    { sku: "A", quantity: 2, lineTotal: 200 },
    { sku: "B", quantity: 1, lineTotal: 200 }
  ]
}
```

When using `as: "item"`, the path `"$$item.sku"` means read the `sku` field of the **current element**. It differs from `"$item.sku"`, which references a field path on the document in the aggregation context.

### 3.3. `$map` Does Not Remove Elements Automatically

If the input has three elements, `$map` normally outputs three elements; if the `in` expression evaluates to `null` for an element, **`null` remains an element of the result array**. To exclude elements that fail a condition, use `$filter`.

```text
input  = [2, 3, 4]
map x*10
output = [20, 30, 40]

map does not mean "filter elements":
input  = [2, 3, 4]
map x%2 == 0 ? x : null
output = [2, null, 4]
```

### 3.4. Default Variable `$$this`

If `as` is omitted, the current element defaults to the name `this`:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O02" } },
  {
    $project: {
      plusOne: {
        $map: {
          input: "$points",
          in: { $add: ["$$this", 1] }
        }
      }
    }
  }
]);
```

O02's `points` is `[10, 8]`, so `plusOne` equals `[11, 9]`. When nesting multiple expressions, explicit variable names via `as` are usually much easier to read than multiple levels of `$$this`.

## 4. `$filter`: Keeping Elements That Satisfy a Condition

If `$map` answers "**what should each element become?**", `$filter` answers "**which elements should be kept?**".

### 4.1. Syntax

```javascript
{
  $filter: {
    input: <arrayExpression>,
    as: "element",
    cond: <booleanExpression>,
    limit: <optionalLimitExpression>
  }
}
```

Where:

- `input`: source array.
- `as`: variable name for the element.
- `cond`: expression determining whether the element is retained.
- `limit`: optional cap on the number of **matching** elements returned, in MongoDB versions supporting this modifier; valid limits must be `1` or greater, or `null` for unlimited.

`$filter` **preserves the relative order** of selected elements from the source array. It does not sort them.

### 4.2. Filtering Active Line Items

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      _id: 1,
      activeItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $eq: ["$$item.active", true]
          }
        }
      }
    }
  }
]);
```

Result:

```javascript
{
  _id: "O01",
  activeItems: [
    { sku: "A", qty: 2, unitPrice: 100, active: true }
  ]
}
```

Line B is excluded because `active: false`. By contrast, `$map` in the previous section transformed **both A and B** because there was no filter.

### 4.3. Multiple Conditions with `$and`

Find line items that are both active and have quantity at least 2:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.active", true] },
              { $gte: ["$$item.qty", 2] }
            ]
          }
        }
      }
    }
  }
]);
```

With the sample data, O01 keeps line A, O02 keeps line C, and O04 keeps line D; O03, O05, and O06 return empty arrays. The conditions here are **aggregation expressions** taking values and variables, not query filter documents of the form `{ qty: { $gte: 2 } }`.

### 4.4. Using `limit` When Only the First Few Matches Are Needed

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O04" } },
  {
    $project: {
      firstActiveItem: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $eq: ["$$item.active", true] },
          limit: 1
        }
      }
    }
  }
]);
```

The resulting array contains only **line A** because A is O04's first active element. The result is still an **array**, not automatically an embedded document. If you want just the first value, wrap `$arrayElemAt` around it:

```javascript
{
  $arrayElemAt: [
    {
      $filter: {
        input: "$items",
        as: "item",
        cond: { $eq: ["$$item.active", true] },
        limit: 1
      }
    },
    0
  ]
}
```

When no element matches, clearly decide how `null`/missing results should be handled in the consumer layer or wrap fallback logic around it.

### 4.5. `$filter` Is Not `$match`

```javascript
// $match filters entire DOCUMENTS.
db.aggArrayLesson.aggregate([
  { $match: { "items.active": true } }
]);

// $filter keeps the DOCUMENT, but produces a filtered items array.
db.aggArrayLesson.aggregate([
  {
    $project: {
      activeItems: {
        $filter: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          cond: { $eq: ["$$item.active", true] }
        }
      }
    }
  }
]);
```

The first `$match` keeps orders containing at least one active item. It **does not trim the `items` array** inside the retained documents. `$filter` in the second example processes the array **within each document**; by default all documents entering `$project` remain present.

This is why when returning data to a UI, you sometimes need **both `$match` to select orders and `$filter` to select which items are displayed inside each order**.

## 5. `$reduce`: Accumulating Left to Right

`$reduce` steps through each element of an array and uses an **accumulator value** to produce a single final result.

It answers the question:

> "Given the intermediate result after prior elements, how should it be combined with the next element?"

### 5.1. Syntax

```javascript
{
  $reduce: {
    input: <arrayExpression>,
    initialValue: <initialExpression>,
    in: <expressionUsingValueAndThis>
  }
}
```

Two special variables inside `in`:

- **`$$value`:** the accumulated value from previous steps; initially equal to `initialValue`.
- **`$$this`:** the array element currently being processed.

By default, MongoDB traverses `input` **from left to right**. The `in` expression produces the new value for `$$value` on the next step.

### 5.2. Summing Numbers in an Array

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      sumPoints: {
        $reduce: {
          input: "$points",
          initialValue: 0,
          in: { $add: ["$$value", "$$this"] }
        }
      }
    }
  }
]);
```

O01's array is `[5, 7, 9]`. Steps:

| Pass | `$$this` | `$$value` before pass | New value |
|---|---:|---:|---:|
| Initial | — | 0 | 0 |
| 1 | 5 | 0 | 5 |
| 2 | 7 | 5 | 12 |
| 3 | 9 | 12 | 21 |

Result: `{ _id: "O01", sumPoints: 21 }`.

For simple addition, MongoDB also provides aggregation expressions like `$sum` to sum arrays in appropriate contexts. `$reduce` is especially useful when **each step requires a custom folding rule** rather than plain summation.

### 5.3. Calculating the Total Amount of Line Items

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      orderTotal: {
        $reduce: {
          input: { $ifNull: ["$items", []] },
          initialValue: 0,
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.qty",
                  "$$this.unitPrice"
                ]
              }
            ]
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Results on the sample data:

| `_id` | `orderTotal` |
|---|---:|
| O01 | 400 |
| O02 | 150 |
| O03 | 0 |
| O04 | 260 |
| O05 | 0 |
| O06 | 200 |

`$ifNull` turns `items: null` or a missing field into `[]`. When `input` is an empty array, `$reduce` returns **`initialValue`**, which is `0` here.

Treating an order missing its item list as total `0` is an **example business decision**; in a real system, unexpectedly missing data may need to be flagged as an error rather than silently treated as an empty order.

### 5.4. The Accumulator Can Be a Document, Not Just a Number

A single pass can compute both the line count and total amount simultaneously:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      statistics: {
        $reduce: {
          input: "$items",
          initialValue: {
            lineCount: 0,
            grossAmount: 0
          },
          in: {
            lineCount: {
              $add: ["$$value.lineCount", 1]
            },
            grossAmount: {
              $add: [
                "$$value.grossAmount",
                {
                  $multiply: [
                    "$$this.qty",
                    "$$this.unitPrice"
                  ]
                }
              ]
            }
          }
        }
      }
    }
  }
]);
```

Result:

```javascript
{
  _id: "O01",
  statistics: {
    lineCount: 2,
    grossAmount: 400
  }
}
```

On each iteration, `in` constructs a **new accumulator document** from the previous `$$value` and the element `$$this`. The shape and types of `initialValue` should match the structure returned by `in`.

### 5.5. Traversal Order Matters for Some Folding Operations

With ordinary addition, reordering elements does not change the mathematical sum. However, with string concatenation, chained subtraction, or order-dependent algorithms, the result can differ.

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      skuList: {
        $reduce: {
          input: {
            $map: {
              input: "$items",
              as: "item",
              in: "$$item.sku"
            }
          },
          initialValue: "",
          in: {
            $cond: [
              { $eq: ["$$value", ""] },
              "$$this",
              { $concat: ["$$value", ",", "$$this"] }
            ]
          }
        }
      }
    }
  }
]);
```

O01's `skuList` result is `"A,B"`. Reversing the input array produces `"B,A"`.

To process right-to-left, pass the array through `$reverseArray` into `$reduce`'s `input`. Never assume `$reduce` automatically sorts elements.

### 5.6. Using `$reduce` to Concatenate Subarrays

Suppose a document holds an array of tag groups:

```javascript
{
  _id: "GROUPS",
  tagGroups: [
    ["mongodb", "database"],
    ["java"],
    ["backend", "mongodb"]
  ]
}
```

We can flatten it into one array:

```javascript
db.tagGroupDemo.aggregate([
  {
    $project: {
      allTags: {
        $reduce: {
          input: "$tagGroups",
          initialValue: [],
          in: {
            $concatArrays: [
              "$$value",
              "$$this"
            ]
          }
        }
      }
    }
  }
]);
```

This assumes the `GROUPS` document is stored in `tagGroupDemo` before running the pipeline. `$concatArrays` joins arrays in order, so the result is:

```javascript
["mongodb", "database", "java", "backend", "mongodb"]
```

`$concatArrays` **preserves duplicate elements**. To produce a set of unique tags instead, additionally apply `$setUnion`; "concatenate lists" and "set union" are two different intents.

## 6. Combining `$filter`, `$map`, and `$reduce`

The three operators often chain together:

```text
initial items
      |
      v
$filter: select valid line items
      |
      v
$map: transform each line into an amount
      |
      v
$reduce: sum the amounts
      |
      v
total amount of matching lines
```

### 6.1. Example: Total Amount of Active Line Items

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      activeAmount: {
        $reduce: {
          input: {
            $map: {
              input: {
                $filter: {
                  input: { $ifNull: ["$items", []] },
                  as: "item",
                  cond: {
                    $eq: ["$$item.active", true]
                  }
                }
              },
              as: "selected",
              in: {
                $multiply: [
                  "$$selected.qty",
                  "$$selected.unitPrice"
                ]
              }
            }
          },
          initialValue: 0,
          in: { $add: ["$$value", "$$this"] }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

With the sample data:

| Order | Active line items | `activeAmount` |
|---|---|---:|
| O01 | A: 2 × 100 | 200 |
| O02 | C: 3 × 50 | 150 |
| O03 | None | 0 |
| O04 | A: 1 × 100, D: 2 × 80 | 260 |
| O05 | No valid array (replaced with []) | 0 |
| O06 | None (B inactive) | 0 |

The pipeline above intentionally uses **all three operators** to show each step. When only summing money, you can compute directly inside `$reduce` over the filtered array to eliminate the `$map` layer; choose based on readability and whether intermediate values are reused.

### 6.2. Using `$let` to Name Intermediate Expressions

When multiple branches of an expression need to reuse a filtered array, `$let` names a variable within the current scope:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O04" } },
  {
    $project: {
      summary: {
        $let: {
          vars: {
            selected: {
              $filter: {
                input: "$items",
                as: "item",
                cond: { $eq: ["$$item.active", true] }
              }
            }
          },
          in: {
            selectedCount: { $size: "$$selected" },
            selectedTotal: {
              $reduce: {
                input: "$$selected",
                initialValue: 0,
                in: {
                  $add: [
                    "$$value",
                    {
                      $multiply: [
                        "$$this.qty",
                        "$$this.unitPrice"
                      ]
                    }
                  ]
                }
              }
            }
          }
        }
      }
    }
  }
]);
```

For O04, the result is `selectedCount: 2` and `selectedTotal: 260`.

`$let` creates an **expression variable** like `$$selected`; it does not alter the stored document schema. It is helpful when a large computation has several nested levels.

## 7. Null, Missing, Empty Arrays, and Wrong Types

`$map`, `$filter`, and `$reduce` have important input rules.

| Value of `input` | `$map` | `$filter` | `$reduce` |
|---|---|---|---|
| Non-empty array | Array of new values | Array of matching elements | Accumulated value |
| Empty array `[]` | `[]` | `[]` | `initialValue` |
| Null | `null` | `null` | `null` |
| Missing field | `null` | `null` | `null` |
| Non-array and non-null value | Input type error | Input type error | Input type error |

For example, if used directly:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      itemsAsSku: {
        $map: {
          input: "$items",
          as: "item",
          in: "$$item.sku"
        }
      }
    }
  }
]);
```

Document O05 has `items: null`, so `itemsAsSku` for O05 is `null`, **not an empty array**.

### 7.1. Normalizing null/missing to an Empty Array with `$ifNull`

```javascript
{
  $map: {
    input: { $ifNull: ["$items", []] },
    as: "item",
    in: "$$item.sku"
  }
}
```

For O05, `$ifNull` replaces `null` with `[]`, so `$map` returns `[]`.

This works well when business rules specify that "no array" is treated as an empty list. However, if missing/null is a **data error** that needs reporting, do not silently hide it behind a fallback value.

### 7.2. `$ifNull` Does Not Fix Wrong-Type Data

If:

```javascript
{
  _id: "BROKEN",
  items: "A,B,C"
}
```

then `{ $ifNull: ["$items", []] }` still returns the String `"A,B,C"`, and `$map`/`$filter`/`$reduce` receiving a String will fail.

When a collection has mixed schemas, check the type first:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      safeSkus: {
        $map: {
          input: {
            $cond: [
              { $isArray: "$items" },
              "$items",
              []
            ]
          },
          as: "item",
          in: "$$item.sku"
        }
      }
    }
  }
]);
```

`$isArray` returns a Boolean indicating whether a value is an array. This example deliberately coerces any non-array value to `[]`; in production, replace that with validation checks and error handling so data is not silently dropped.

### 7.3. Distinguishing Empty Arrays from Missing Fields

To audit inconsistent data, use `$type`:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      itemsType: { $type: "$items" },
      itemsIsArray: { $isArray: "$items" }
    }
  }
]);
```

For O03, `itemsType` is `"array"`; for O05 it is `"null"`. When a field does not exist, the aggregation expression `$type` returns `"missing"`.

This is useful before deciding whether a calculation should return `0`, `null`, or flag invalid data.

## 8. Lists vs. Sets: Why Do We Need Set Operators?

An **array** in MongoDB preserves order and can contain identical elements:

```javascript
["vip", "sale", "vip"]
```

A mathematical **set** cares only whether a value **belongs to the set**, ignoring position and duplicate counts.

When using set operators, MongoDB treats input arrays as sets of values:

```text
Array:  ["vip", "sale", "vip"]
Set:    {"vip", "sale"}

Array:  ["sale", "vip"]
Set:    {"vip", "sale"}

Both arrays differ in order/repetition,
yet represent the exact same value set.
```

Set operators return an **array** representing the resulting set, but **do not guarantee the order of elements in the output array**. If an API requires a specific order, apply an explicit sorting step afterward; never write positional assertions against example order.

### 8.1. Set Operators Differ from `$concatArrays`

```javascript
// Concatenate lists, preserving order and duplicates:
{ $concatArrays: [["vip", "sale"], ["sale", "new"]] }

// Set union, removing duplicates, unspecified order:
{ $setUnion: [["vip", "sale"], ["sale", "new"]] }
```

Conceptual outputs:

```javascript
// $concatArrays
["vip", "sale", "sale", "new"]

// $setUnion: set of values, order may vary
["vip", "sale", "new"]
```

**Never use `$setUnion` in place of `$concatArrays`** when element repetition and ordering carry business meaning, such as event histories or workflow steps.

## 9. `$setUnion`: Union of Multiple Sets

`$setUnion` produces a set containing **every distinct element** appearing in at least one input array.

### 9.1. Basic Syntax

```javascript
{
  $setUnion: [
    <arrayExpression1>,
    <arrayExpression2>,
    ...
  ]
}
```

Example with O01:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      unifiedTags: {
        $setUnion: [
          "$tags",
          ["sale", "new"]
        ]
      }
    }
  }
]);
```

Since O01's `tags` is `["vip", "sale", "vip"]`, the resulting set contains **vip, sale, and new**, each once:

```javascript
{
  _id: "O01",
  unifiedTags: ["vip", "sale", "new"]
  // Element order is illustrative only.
}
```

### 9.2. Deduplicating a Single Array

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      uniqueTags: {
        $setUnion: [
          { $ifNull: ["$tags", []] },
          []
        ]
      }
    }
  }
]);
```

Taking the union of an array with an empty set is a concise way to **extract unique values from an array** under set semantics. For O01, `uniqueTags` has two values, `vip` and `sale`, without the duplicate `vip`.

Normalizing `tags` with `$ifNull` here avoids passing `null`/missing where an array is expected. Do not confuse this with mutating stored data: `$project` only builds read results.

### 9.3. Using with Multiple Arrays

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O02" } },
  {
    $project: {
      allLabels: {
        $setUnion: [
          "$tags",
          "$coupons",
          ["new"]
        ]
      }
    }
  }
]);
```

O02 has tags `sale, new` and coupons `SALE, FREESHIP`. Under default String comparison, `"sale"` and `"SALE"` are **two distinct values**; uppercase and lowercase are not merged automatically. If business rules treat them as the same, normalize data or apply appropriate transformations before passing to set operators.

## 10. `$setIntersection`: Intersection of Sets

`$setIntersection` keeps only elements present in **all input arrays**.

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      commonTags: {
        $setIntersection: [
          "$tags",
          ["sale", "new", "popular"]
        ]
      }
    }
  }
]);
```

The result contains one value, `"sale"`, because:

```text
O01's tags  = {vip, sale}
target tags = {sale, new, popular}
intersection = {sale}
```

Example querying orders **having at least one tag in the target set**:

```javascript
db.aggArrayLesson.aggregate([
  {
    $match: {
      $expr: {
        $gt: [
          {
            $size: {
              $setIntersection: [
                { $ifNull: ["$tags", []] },
                ["vip", "new"]
              ]
            }
          },
          0
        ]
      }
    }
  },
  { $project: { _id: 1, tags: 1 } }
]);
```

Orders having at least one of `vip` or `new` are **O01, O02, and O04**. This demonstrates using a set expression inside `$expr` to filter documents.

When simply checking whether an array field contains a value from a list, a standard query filter `{ tags: { $in: ["vip", "new"] } }` is shorter and can leverage a suitable multikey index. Avoid overcomplicating array filters with aggregation expressions when simple predicates suffice.

## 11. `$setDifference`: Elements in A That Are Not in B

`$setDifference` performs a **directed set difference**: elements in the first array that are **not** in the second array.

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      tagsNotInCampaign: {
        $setDifference: [
          "$tags",
          ["sale", "new"]
        ]
      }
    }
  }
]);
```

The result represents the set `{"vip"}`.

If the two arrays are swapped:

```javascript
{
  $setDifference: [
    ["sale", "new"],
    "$tags"
  ]
}
```

the result is the set `{"new"}`.

**Set difference is not commutative:** `A − B` differs from `B − A`. Clearly distinguish whether the business goal is "order tags **not yet in the campaign**" or "campaign tags **the order lacks**."

### 11.1. Example Suggesting Missing Tags to Add

The application wants to find which default tags from `["sale", "new"]` are missing on O01:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      missingRecommendedTags: {
        $setDifference: [
          ["sale", "new"],
          { $ifNull: ["$tags", []] }
        ]
      }
    }
  }
]);
```

The result contains only `"new"`. This is a read calculation; to **persist** the new tag, the application needs a separate update operation with appropriate business constraints.

## 12. `$setEquals` and `$setIsSubset`: Comparing Sets

These two operators return a **Boolean** rather than a result array.

### 12.1. `$setEquals`: Do Two Sets Have the Exact Same Elements?

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      tagsEquivalent: {
        $setEquals: [
          "$tags",
          ["sale", "vip"]
        ]
      }
    }
  }
]);
```

O01 has `["vip", "sale", "vip"]`; the comparison array is `["sale", "vip"]`. The result is `tagsEquivalent: true` because both arrays represent the same **value set**, despite differing in element count and order.

This is a key distinction from comparing two arrays as **ordered lists**.

### 12.2. `$setIsSubset`: Is Every Element of A in B?

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      hasRequiredTags: {
        $setIsSubset: [
          ["vip"],
          "$tags"
        ]
      },
      allTagsAllowed: {
        $setIsSubset: [
          "$tags",
          ["vip", "sale", "new"]
        ]
      }
    }
  }
]);
```

Both conditions evaluate to `true`:

- `{"vip"} ⊆ {"vip", "sale"}`.
- `{"vip", "sale"} ⊆ {"vip", "sale", "new"}`.

**Operand order matters greatly.** To check "does the order have **all required tags**," place the required tags on the **left** and the order's current tags on the **right**.

### 12.3. The Empty Set and Inclusion

Several useful mathematical rules:

- The empty set is a subset of **every set**.
- Two empty sets are equal.
- The intersection with the empty set is the empty set.
- The union with the empty set preserves the other operand's value set.

Consequently, `$setIsSubset: [[], "$tags"]` returns `true` even when `tags` contains no labels (provided `tags` is a valid array). If business rules require **at least one required tag**, verify the required array is non-empty before concluding "requirements met."

## 13. `$anyElementTrue` and `$allElementsTrue`

This group of set operators tests the **truthiness** of input elements. They do not understand object business logic or nested fields on their own, so they are usually applied after `$map` converts an array into Boolean values.

### 13.1. Does at Least One Line Item Have Quantity Greater Than 2?

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      hasLargeLine: {
        $anyElementTrue: [
          {
            $map: {
              input: { $ifNull: ["$items", []] },
              as: "item",
              in: { $gt: ["$$item.qty", 2] }
            }
          }
        ]
      }
    }
  }
]);
```

O02 has line C with `qty: 3`, so `hasLargeLine` is `true`. The other orders in the sample set have no line items with `qty > 2`.

`$anyElementTrue` accepts **a single array expression** (wrapped inside an argument array) and returns `true` if any evaluated element is truthy.

### 13.2. Are All Line Items Active?

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      allLinesActive: {
        $allElementsTrue: [
          {
            $map: {
              input: { $ifNull: ["$items", []] },
              as: "item",
              in: { $eq: ["$$item.active", true] }
            }
          }
        ]
      }
    }
  }
]);
```

O02 and O04 return `true` because all their line items are active. O01 and O06 return `false` because they contain an inactive line.

**Important trap:** `$allElementsTrue` on an empty array returns **true** (vacuous truth: "all elements satisfy" over an empty set). Thus O03 or O05 returns `true` after normalizing to `[]`, even though **there is not a single active line item**.

If business logic means "**has at least one line** and every line is active," check the array length as well:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      hasItemsAndAllActive: {
        $let: {
          vars: {
            safeItems: { $ifNull: ["$items", []] }
          },
          in: {
            $and: [
              { $gt: [{ $size: "$$safeItems" }, 0] },
              {
                $allElementsTrue: [
                  {
                    $map: {
                      input: "$$safeItems",
                      as: "item",
                      in: {
                        $eq: ["$$item.active", true]
                      }
                    }
                  }
                ]
              }
            ]
          }
        }
      }
    }
  }
]);
```

In this example, O02 and O04 are the orders satisfying the revised condition.

### 13.3. Nested Arrays Are Treated as Elements, Not Recursively Traversed

Set operators do not automatically flatten nested arrays. An array element inside an outer array is still treated as **a single element at the current level** when evaluated by these operators. Therefore, if your intent is to check Booleans across multiple levels of nested arrays, flatten or transform the data explicitly first.

Do not use `$anyElementTrue` in place of a deep traversal without verifying the input structure.

## 14. Set Operators Treat Nested Arrays as Intact Elements

Given:

```javascript
const first = ["mongodb", ["java", "spring"]];
const second = [["java", "spring"], "backend"];
```

Because set operators process arrays at the current level, the subarray `["java", "spring"]` is treated as **a single set element**, not split into two elements `java` and `spring`.

Consequently, the union contains the conceptual values:

```text
{
  "mongodb",
  ["java", "spring"],
  "backend"
}
```

This is why when a document contains an **array of arrays**, you must decide:

1. Do you want to treat each subarray as **one distinct object**?
2. Or do you want to analyze and merge the **elements inside**?

In the second case, use `$reduce + $concatArrays` to flatten one level before calling `$setUnion`. Note that single-level flattening is **not** unbounded recursion; if arrays have arbitrary nesting depth, define the depth and handling explicitly.

## 15. Using Set Operators in a Summary Pipeline

Suppose an application wants to return each order's unique tags, tags belonging to a marketing campaign, and distinct tag count.

```javascript
db.aggArrayLesson.aggregate([
  {
    $set: {
      safeTags: {
        $ifNull: ["$tags", []]
      }
    }
  },
  {
    $project: {
      _id: 1,
      uniqueTags: {
        $setUnion: ["$safeTags", []]
      },
      campaignTags: {
        $setIntersection: [
          "$safeTags",
          ["vip", "sale"]
        ]
      },
      missingRecommendedTags: {
        $setDifference: [
          ["vip", "new"],
          "$safeTags"
        ]
      },
      distinctTagCount: {
        $size: {
          $setUnion: ["$safeTags", []]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Example for O01:

```javascript
{
  _id: "O01",
  uniqueTags: ["vip", "sale"],
  campaignTags: ["vip", "sale"],
  missingRecommendedTags: ["new"],
  distinctTagCount: 2
}
```

**Element order in the output arrays of set operators is illustrative only**, whereas the distinct element count is deterministic given the data and comparison rules.

### 15.1. Comparing Total Elements vs. Distinct Values

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      tagCount: {
        $size: { $ifNull: ["$tags", []] }
      },
      distinctTagCount: {
        $size: {
          $setUnion: [
            { $ifNull: ["$tags", []] },
            []
          ]
        }
      }
    }
  }
]);
```

O01 has `tagCount = 3` yet `distinctTagCount = 2` because `vip` is duplicated. These are two different quantities:

- **`$size`:** total array elements, including duplicates.
- **`$size` of `$setUnion` result:** count of distinct values in the array.

Do not swap the two calculations when occurrence counts carry business meaning.

## 16. Updating Arrays: Expressions vs. Update Operators

The examples above mainly use `aggregate()` to **read** and compute values. MongoDB also supports **updates with aggregation pipelines**, where expressions can construct a new array state.

### 16.1. `$addToSet` Is an Update Operator, Different from `$setUnion`

```javascript
// Traditional update: add "new" if it does not exist yet.
db.aggArrayLesson.updateOne(
  { _id: "O01" },
  {
    $addToSet: {
      tags: "new"
    }
  }
);
```

`$addToSet` adds a value not already present in the array, yet **does not automatically remove pre-existing duplicates**. O01 can still retain both old copies of `vip`.

By contrast, using `$setUnion` in an **update pipeline**:

```javascript
db.aggArrayLesson.updateOne(
  { _id: "O01" },
  [
    {
      $set: {
        tags: {
          $setUnion: [
            { $ifNull: ["$tags", []] },
            ["new"]
          ]
        }
      }
    }
  ]
);
```

Here `$setUnion` produces a **new deduplicated array under set semantics**, and `$set` is the **aggregation stage** assigning that array back to `tags`. New element order is not guaranteed.

**The two approaches have different semantics**:

| Requirement | Potentially Suitable Tool |
|---|---|
| Add a tag if absent, preserving existing array order/structure as much as possible | Update `$addToSet` |
| Create a new set from multiple arrays, removing existing duplicates | Aggregation expression `$setUnion` |
| Append history while keeping repeated events | `$concatArrays` or update `$push` |
| Keep at most N most recent events by criteria | Design preview with `$push` and modifiers, or recompute pipeline |

### 16.2. `$filter` in an Update Pipeline Modifies Stored Data

Example removing inactive line items:

```javascript
db.aggArrayLesson.updateOne(
  { _id: "O01" },
  [
    {
      $set: {
        items: {
          $filter: {
            input: { $ifNull: ["$items", []] },
            as: "item",
            cond: { $eq: ["$$item.active", true] }
          }
        }
      }
    }
  ]
);
```

Unlike `$project` in a read query, this command **overwrites the stored `items` array** with the filtered result. O01's line B will be deleted from the stored array, not merely hidden from a response. Only do this if it is genuinely a business update requirement.

For practice exercises where you want to keep the initial dataset intact, **run read examples before update examples**, or use a separate collection to experiment with update pipelines.

## 17. Comparing `$map`, `$filter`, `$reduce`, `$unwind`, and `$group`

All of these names appear in aggregation, yet they operate at different scopes:

| Tool | Kind | Primary Input | Result |
|---|---|---|---|
| `$map` | Expression | One array | One transformed array |
| `$filter` | Expression | One array + condition | One subarray |
| `$reduce` | Expression | One array + accumulator | One value |
| `$setUnion` | Expression | Two or more arrays | Array of distinct elements |
| `$unwind` | Pipeline stage | Document stream with array field | Potentially multiple documents per element |
| `$group` | Pipeline stage | Stream of multiple documents | One document per group key |

### 17.1. Summing Within One Order Using `$reduce`

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      total: {
        $reduce: {
          input: { $ifNull: ["$items", []] },
          initialValue: 0,
          in: {
            $add: [
              "$$value",
              { $multiply: ["$$this.qty", "$$this.unitPrice"] }
            ]
          }
        }
      }
    }
  }
]);
```

Each order document produces one total computed from **the `items` array inside that same document**.

### 17.2. Summing by SKU Across the Collection Using `$unwind + $group`

```javascript
db.aggArrayLesson.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      lineCount: { $sum: 1 },
      units: { $sum: "$items.qty" },
      revenue: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPrice"
          ]
        }
      }
    }
  },
  { $sort: { units: -1, _id: 1 } }
]);
```

Results on the sample data (without filtering `active`):

| SKU | `lineCount` | `units` | `revenue` |
|---|---:|---:|---:|
| A | 2 | 3 | 300 |
| C | 1 | 3 | 150 |
| B | 2 | 2 | 400 |
| D | 1 | 2 | 160 |

`$unwind` flattens each line item into a document in the stream, after which `$group` aggregates **across multiple orders**. `$reduce`, on the other hand, is typically used to compute **within a single document's array**.

### 17.3. Why Not Always Use `$unwind`?

Suppose you only want to return active line items **within each order**, keeping each order as one document. Using `$filter` is direct and usually much clearer than `$unwind`-ing lines, `$match`-ing, and `$group`-ing them back into an array.

Conversely, when you need a revenue report **by SKU across the entire collection**, `$unwind + $group` is far more natural than running separate `$reduce` passes and trying to merge results across orders.

Choose the tool according to the **transformation scope**: inside one document's array or across a stream of multiple documents.

## 18. Set Operators vs. Array Queries: Avoid Overcomplicating

If you only want to find orders with the `vip` tag, a query filter is usually sufficient:

```javascript
db.aggArrayLesson.find({ tags: "vip" });
```

To find orders having at least one tag in a list:

```javascript
db.aggArrayLesson.find({
  tags: { $in: ["vip", "new"] }
});
```

To require all mandatory tags to appear together:

```javascript
db.aggArrayLesson.find({
  tags: { $all: ["vip", "sale"] }
});
```

These are **query operators** inside a filter, not aggregation set expressions. When the goal is filtering directly on array elements, query operators are concise and have the opportunity to use a **multikey index**.

By contrast, use set expressions when you need to:

- **Compute a new set** to return in a response.
- **Compare two dynamic arrays** within the same document or expression sources.
- **Count distinct elements**.
- **Construct derived arrays** in an aggregation or update pipeline.
- **Test subset relationships** between a required array and a current array via expressions.

Example with two arrays inside the same document:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      tagCouponOverlap: {
        $setIntersection: [
          { $ifNull: ["$tags", []] },
          { $ifNull: ["$coupons", []] }
        ]
      }
    }
  }
]);
```

Here we are **computing the intersection of two stored array fields**, not merely checking one field against a constant list.

## 19. Data Type, Ordering, and Comparison Issues

### 19.1. Set Operators Do Not Automatically Sort Output

Do not write tests assuming that:

```javascript
{ $setUnion: [["b", "a"], ["c", "a"]] }
```

**must** return `["a", "b", "c"]` alphabetically. Set operators do not guarantee output array order. If a UI or API requires a specific order, use an array-sorting operator supported by your server version and deployment, or sort in the application layer.

### 19.2. BSON Types Affect Equality Semantics

In real data, visually similar values may carry different types, such as:

```javascript
"42"    // String
42      // Number
```

Do not treat those two values as the same label and expect set operators to normalize them automatically. Likewise, differently cased strings can differ under the active comparison rules. If normalization is needed, enforce rules in the **schema** or normalize in expressions before calling set operators.

### 19.3. Null Inside an Array Differs from a Null Array

```javascript
["a", null]    // Valid array containing one null element.
null           // Null value, not an array.
```

Set operators can treat a **null element inside an array** as a member value of the set. Conversely, if an entire operand is `null` or missing, array operations must follow operator rules and must not be assumed equivalent to `[]`.

A safe pattern when business logic treats null/missing as an empty array:

```javascript
{
  $setIntersection: [
    { $ifNull: ["$tags", []] },
    ["vip", "sale"]
  ]
}
```

### 19.4. Embedded Documents Are Composite Values

Given:

```javascript
[
  { sku: "A", qty: 1 },
  { sku: "A", qty: 2 }
]
```

two embedded documents with the same `sku` yet **different `qty`** are not identical values. Set operators **do not automatically use `sku` alone as a uniqueness key**.

If you want a set of distinct SKUs, use `$map` to create an **array of scalars** first, and then apply `$setUnion`:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      uniqueSkus: {
        $setUnion: [
          {
            $map: {
              input: { $ifNull: ["$items", []] },
              as: "item",
              in: "$$item.sku"
            }
          },
          []
        ]
      }
    }
  }
]);
```

This expresses "unique by SKU" explicitly. Applying set union directly to `items` compares **full embedded document values**, not an implicitly selected subfield.

## 20. Performance: Processing Large Arrays Can Be Expensive

The operators in this lesson are generally evaluated **per document** passing through the pipeline. A document with a 10-element array is very different from a document with a 100,000-element array.

### 20.1. Per-Element Cost

Intuitively:

- `$map`: must process input elements to construct a new array.
- `$filter`: must evaluate the condition for relevant elements.
- `$reduce`: must iterate elements and update the accumulator.
- Set operations: must inspect values to identify duplicates, intersections, differences, or equality.

Actual runtime and memory depend on array length, element size, complexity of nested expressions, query plan, and execution environment. Never assume invoking an expression always has constant cost.

### 20.2. Filter Documents Before Computing Array Expressions

If you only need `PAID` orders:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      activeItems: {
        $filter: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          cond: { $eq: ["$$item.active", true] }
        }
      }
    }
  }
]);
```

`$match` narrows the number of documents needing expression evaluation. When an index exists on `status` and data is large enough, this reduces overall cost. However, **query indexes do not automatically speed up `$map`/`$filter` running over elements inside each array**; indexes primarily help locate the documents to process.

### 20.3. Return Only Necessary Fields

For instance, if an API only needs `sku` and line total, `$map` constructing smaller objects than the full embedded documents can reduce network payload size:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          in: {
            sku: "$$item.sku",
            total: {
              $multiply: [
                "$$item.qty",
                "$$item.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
```

`$project` clarifies the output contract, though you should not assume every projection prevents the database from reading the source document. Index usage and covered-query eligibility must be verified from execution plans.

### 20.4. Avoid Unbounded Array Growth

MongoDB has a **16 MiB limit per BSON document**. If an order or user document contains an unbounded history array, both storing it and running expressions over it become unsuitable.

For data with an independent lifecycle or huge cardinality, consider moving items to a dedicated collection and using `$unwind`/`$group` or appropriate relational queries rather than forcing everything into one document's array.

### 20.5. When Should Computed Results Be Materialized?

If the UI constantly requests an order's total amount or distinct tag count, the application can consider storing derived fields such as `totalAmount` or `distinctTagCount` and updating them alongside source data.

In return, derived fields require a consistency mechanism: adding, removing, or editing `items` or `tags` must recalculate the values accurately. Only do this when actual query cost and read/write ratios justify the synchronization risk.

## 21. Common Errors and Misconceptions

| Thought or Pattern | Problem | How to Handle |
|---|---|---|
| `$map` automatically drops non-matching elements | It transforms every element, usually keeping the same length | Use `$filter` before or after mapping |
| `$filter` filters out parent documents | It returns a subarray and does not drop documents from the pipeline | Use `$match` to filter documents |
| `$reduce` always returns an array | It returns the **accumulated value**, which may be a number, string, object, or array | Pick matching `initialValue` and `in` |
| `$$value` is the current element | `$$value` is the accumulator; `$$this` is the element | Keep variable roles distinct |
| `"$item.sku"` and `"$$item.sku"` are the same | One is a document field path, the other is an `as` variable | Use double `$$` for variables |
| Empty array and null are always identical | `$reduce` on `[]` returns `initialValue`; null input returns `null` | Define normalization policy explicitly |
| `$ifNull` fixes every wrong type | Strings or Numbers are not null, pass through, and trigger errors | Check `$isArray` or enforce validation |
| `$setUnion` concatenates lists and keeps duplicates | It performs set union, removes duplicates, and does not guarantee order | Use `$concatArrays` if a list is needed |
| `$setDifference` operands can be freely swapped | Set difference is directional | Order as `A − B` correctly |
| `$setEquals` compares arrays positionally | It compares value sets, ignoring order and duplicates | Use positional comparisons when order matters |
| `$setIsSubset` returns false if the required array is empty | The empty set is a subset of every set | Check "must have elements" separately |
| `$allElementsTrue` on `[]` returns false | It returns `true` on an empty array | Check `$size > 0` if required |
| `$map` on an object array deduplicates by `sku` automatically | Full objects are compared by value | Map to an array of `sku` strings first, then `$setUnion` |
| `$setUnion` always returns alphabetically sorted results | Output element order is not guaranteed | Sort explicitly |
| Set operators are pipeline stages | They are expressions used inside stages like `$project`/`$set` | Place in the right context |
| `$reduce` on one document replaces `$group` across the collection | Scopes differ: internal array vs. multiple documents | Use `$unwind + $group` for cross-document aggregation |
| All array expressions use indexes | Expressions are typically evaluated after locating documents | Use `$match` and inspect `explain()` |

## 22. Practice Exercises

### Exercise 1 — Transforming a Numeric Array with `$map`

Given document:

```javascript
{ _id: "X01", values: [2, 5, 8] }
```

Write `$project` with `$map` to produce the array:

```javascript
[4, 10, 16]
```

Then produce a Boolean array indicating whether each number is greater than 5. Explain why `$map` still returns all three elements even when the expression evaluates to `false`.

### Exercise 2 — Filtering Embedded Documents

Using `items` in O01, use `$filter` to select lines with:

- `active: true`.
- `qty >= 2`.

Then use `$map` to return `sku` and `lineTotal`. Predict the result before running and explain the role of `$$item`.

### Exercise 3 — Summing Amounts with `$reduce`

Given the array:

```javascript
[
  { sku: "A", qty: 2, unitPrice: 100 },
  { sku: "B", qty: 1, unitPrice: 200 }
]
```

Write `$reduce` returning total amount `400`. Trace `$$value` and `$$this` at each step. Then test on an empty array and on `null`: how do the two results differ?

### Exercise 4 — Creating a Multi-Field Accumulator

Write `$reduce` so the output contains:

```javascript
{
  lineCount: 2,
  totalUnits: 3,
  grossAmount: 400
}
```

for O01's two line items. Hint: use an `initialValue` object with three fields and construct a new object in `in` using `$$value.lineCount`, `$$value.totalUnits`, and `$$value.grossAmount`.

### Exercise 5 — Union, Intersection, and Difference

Given:

```javascript
const A = ["mongodb", "java", "mongodb", "backend"];
const B = ["java", "cloud"];
```

Predict the element sets of:

- `$setUnion: [A, B]`.
- `$setIntersection: [A, B]`.
- `$setDifference: [A, B]`.
- `$setDifference: [B, A]`.

Why shouldn't set operator outputs be tested by asserting element positions in the array?

### Exercise 6 — Subsets and Set Equality

With tags `["vip", "sale", "vip"]`, explain the results of:

```javascript
{ $setEquals: [
    ["vip", "sale", "vip"],
    ["sale", "vip"]
] }

{ $setIsSubset: [
    ["vip"],
    ["vip", "sale", "vip"]
] }

{ $setIsSubset: [
    [],
    ["vip", "sale"]
] }
```

What extra condition should be added if business rules state "the required tag set must be **non-empty**"?

### Exercise 7 — Counting Distinct Tags

Create two fields from each order's `tags` array:

- `tagCount`: total element count, including duplicates.
- `distinctTagCount`: count of unique values.

Use `$size` and `$setUnion`. For O01, explain why the two numbers are **3 and 2**. For O05 with `null`, decide on a default value policy.

### Exercise 8 — Checking Existence and Universal Conditions

For line items in `items`:

1. Check whether at least one line has `qty > 2`.
2. Check whether all lines have `active: true`.
3. Check simultaneously whether there is **at least one line** and **every line is active**.

Use `$map`, `$anyElementTrue`, `$allElementsTrue`, and `$size`. State the results for O02 and O03, explaining the empty-array trap.

### Exercise 9 — Distinguishing Sets from Lists

Given an event array:

```javascript
["LOGIN", "VIEW", "LOGIN"]
```

Why can `$setUnion` lose information about the number of `LOGIN` occurrences? When should `$concatArrays` be used versus `$setUnion`? If you need to count the frequency of each event type across the whole collection, how can `$unwind` and `$group` be used?

### Exercise 10 — Designing an API Returning Processed Orders

An endpoint requires:

- Returning only `PAID` orders.
- Inside each order, keeping only active line items.
- Displaying `sku` and `lineTotal` for each line.
- Also returning `totalActiveAmount`.
- Returning a list of distinct tags for filter display.

Design an aggregation pipeline with `$match`, `$project` or `$set`, and the expressions `$filter`, `$map`, `$reduce`, and `$setUnion`. Explain which fields are source data and which are derived response values.

### Exercise 11 — Choosing a Storage Structure

A user has a history of 2 million activities. Compare:

- Storing all activities in `user.events[]` and using `$filter + $reduce`.
- Storing activities as separate documents in `events` and using `$match`, `$group`, `$sort`, and `$limit`.

Evaluate BSON document limits, array update cost, time-range queryability, and batch processing. Why do powerful array operators not imply that one document should hold every event?

## 23. Summary

**`$map` transforms each element**, **`$filter` selects elements matching a condition**, and **`$reduce` folds elements into a single accumulated value**. All three operate on arrays within a single document and can be combined to process nested BSON structures without pulling entire arrays into the application layer.

**Set operators treat arrays as sets of values.** `$setUnion` computes unions, `$setIntersection` computes intersections, `$setDifference` computes differences, and `$setEquals`/`$setIsSubset` check set relationships. They ignore order and duplicates per set semantics; never use them in place of list concatenation when order or multiplicity matters.

**Null, missing, empty arrays, and wrong-type data are not synonymous.** `$map`, `$filter`, and `$reduce` behave distinctly on empty arrays and `null`; `$ifNull` or `$isArray` should be applied intentionally according to schema and business invariants.

**Choose the right processing scope.** Array expressions fit per-document output shaping; `$unwind` and `$group` fit aggregating elements across multiple documents. When data grows large or requires independent querying, collection modeling and indexes remain just as critical as expression syntax.
