# Processing Arrays with filter, map, reduce, and Set Operators

> **Chapter:** Advanced Aggregation  
> **Module:** `SPRING_DATA_MONGODB`

Arrays are one of the defining traits of MongoDB documents: an order holds line items, an article holds tags, a device records sensor readings, or an account holds a list of permissions. When computing directly over those arrays, you do not always need to load entire documents into Java and write nested `for` loops. The **MongoDB Aggregation Framework** provides *array expressions* to filter elements (`$filter`), transform each element (`$map`), accumulate a result (`$reduce`), and compute set semantics (`$setUnion`, `$setIntersection`, `$setDifference`, `$setEquals`, `$setIsSubset`).

The real challenge goes beyond memorizing operator names. You must know **which array each expression accepts, what type it returns, whether order and duplicates are preserved, and how empty arrays, `null`, or missing fields behave**. A pipeline that looks right at a glance can double-count elements, choke on legacy records, or miscalculate totals when transformations are ordered incorrectly.

This lesson belongs to the `SPRING_DATA_MONGODB` module—covering connection, document mapping, `MongoTemplate` and repositories, query and aggregation design, indexing, transactions, reactive access, testing, and performance diagnostics. We start with MongoDB aggregation and then implement the corresponding code in Spring Data MongoDB.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish *aggregation stages* (`$match`, `$set`, `$project`, `$unwind`) from *array expressions* (`$filter`, `$map`, `$reduce`, and set operators).
2. Use `$filter` to retain matching elements, `$map` to transform elements, and `$reduce` to fold into an accumulated value, including arrays or objects.
3. Scope `$$this`, `$$value`, and custom `as` variables accurately.
4. Apply `$setUnion`, `$setIntersection`, `$setDifference`, `$setEquals`, and `$setIsSubset` without confusing ordered/duplicated arrays with mathematical sets.
5. Handle empty/`null`/missing/wrong-type arrays using `$isArray`, `$cond`, and `$ifNull`, distinguishing element filtering from document filtering.
6. Integrate pipelines with `Aggregation`/`MongoTemplate` or `@Aggregation`, verify BSON types, and test against a real MongoDB server.

## 2. Quick Operator Map

| Operator | Primary input | Output | Characteristics |
| --- | --- | --- | --- |
| `$filter` | Array + `cond` predicate | Sub-array | Preserves relative order of kept elements; does not deduplicate |
| `$map` | Array + `in` expression | Same-length array | Transforms every element in order; does not filter |
| `$reduce` | Array + `initialValue` + `in` expression | Any single value | Iterates left-to-right; accumulator can be number, string, object, or array |
| `$setUnion` | Arrays | Union set | Deduplicates; element order is not guaranteed |
| `$setIntersection` | Arrays | Intersection set | Keeps shared elements only; deduplicates |
| `$setDifference` | Two arrays | Set difference | Directional: A minus B differs from B minus A |
| `$setEquals` | Arrays | Boolean | Compares as sets, ignoring order and duplicates |
| `$setIsSubset` | Two arrays | Boolean | Checks whether every element of first set appears in second |
| `$size` | Array | Integer | Counts **array elements**, including duplicates |
| `$concatArrays` | Arrays | Concatenated array | Keeps duplicates; for list concatenation, not set union |
| `$arrayElemAt` | Array and index | Single element | Positional lookup; not set semantics |

These expressions live **inside** `$set`/`$addFields`, `$project`, or `$group`, rather than acting as top-level pipeline stages. `$set` inside aggregation creates or overwrites fields on **documents flowing through the stream**—it is not an update command against stored data.

### 2.1. Flow Model

```text
Collection orders (documents with items[] and labels[])
            |
            v
[$match]  Authorized tenant documents only
            |
            v
[$set]    Normalize inputs into safeItems[], safeLabels[]
            |
            v
[$set]    eligibleItems[] = $filter(safeItems[])
          lineTotals[] = $map(safeItems[])
          allItemTags[] = $reduce(...$setUnion...)
          union/intersection/difference of labels[]
            |
            v
[$set]    totalMinor = $reduce(lineTotals[])
          eligibleSubtotal = $reduce(eligibleItems[])
            |
            v
[$project] Emit API response fields only
            |
            v
Result documents; one document per order
```

In this pipeline, array expressions operate **without `$unwind`**. Therefore, each order continues to map 1-to-1 to an output document. By contrast, `$unwind` **multiplies document count** by array length, whereas `$map` and `$filter` keep the array structure inside each document.

## 3. Running Dataset

We use an `orders` collection. Each order has an `items` array of line items (`sku`, `qty`, `unitPriceMinor`, `tags`), current `labels`, and `incomingLabels` from a sync source.

**Run only on an isolated test MongoDB database:**

```javascript
use shop

db.orders.insertMany([
  {
    _id: "A-101",
    tenantId: "TENANT-A",
    status: "PAID",
    items: [
      { sku: "SKU-A", qty: 2,
        unitPriceMinor: NumberLong(12000),
        tags: ["fragile", "promotion"] },
      { sku: "SKU-B", qty: 1,
        unitPriceMinor: NumberLong(5000),
        tags: ["gift"] },
      { sku: "SKU-C", qty: 3,
        unitPriceMinor: NumberLong(7000),
        tags: ["promotion", "priority"] }
    ],
    labels: ["web", "priority", "web"],
    incomingLabels: ["priority", "express", "priority"]
  },
  {
    _id: "A-102",
    tenantId: "TENANT-A",
    status: "NEW",
    items: [],
    labels: [],
    incomingLabels: ["web"]
  },
  {
    _id: "A-103",
    tenantId: "TENANT-A",
    status: "PAID",
    items: [
      { sku: "SKU-D", qty: 1,
        unitPriceMinor: NumberLong(9000),
        tags: ["express"] },
      { sku: "SKU-E", qty: 4,
        unitPriceMinor: NumberLong(2000),
        tags: ["priority", "express"] }
    ],
    labels: ["app", "express"],
    incomingLabels: ["express", "priority"]
  },
  {
    _id: "A-104",
    tenantId: "TENANT-A",
    status: "NEW",
    items: null,
    labels: null,
    incomingLabels: ["web"]
  },
  {
    _id: "B-201",
    tenantId: "TENANT-B",
    status: "PAID",
    items: [
      { sku: "SKU-Z", qty: 100,
        unitPriceMinor: NumberLong(100000),
        tags: ["private"] }
    ],
    labels: ["private"],
    incomingLabels: ["private", "priority"]
  }
])
```

`TENANT-B` is included to catch missing authorization filters. SKU-Z must never be added to tenant A's report. `A-102` and `A-104` distinguish an **empty array** from **BSON null**; production data can also omit fields completely or store wrong types.

### 3.1. Expected Calculations

| Order | Line items and subtotals | All-items total | Lines with `qty >= 2` | Eligible lines subtotal |
| --- | --- | ---: | --- | ---: |
| A-101 | 24,000 + 5,000 + 21,000 | 50,000 | SKU-A, SKU-C | 45,000 |
| A-102 | No line items | 0 | None | 0 |
| A-103 | 9,000 + 8,000 | 17,000 | SKU-E | 8,000 |
| A-104 | `items: null` | 0 by illustrative normalization rule | None | 0 |
| B-201 | 100 × 100,000 | 10,000,000 | SKU-Z | 10,000,000 |

Treating A-104 as 0 is an **illustrative fallback rule chosen for this lesson**; it does not imply null in real payment data should always equal zero. If schema rules require `items`, production code should reject or quarantine invalid documents rather than reporting 0.

## 4. $filter: Filtering *Elements* Inside an Array

Requirement: for each tenant A order, retain only line items with `qty >= 2`:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A", _id: "A-101" } },
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $gte: ["$$item.qty", 2] }
        }
      }
    }
  }
])
```

`eligibleItems` returns **SKU-A** and **SKU-C**, in original order; SKU-B is omitted because `qty=1`.

### 4.1. Syntax Breakdown

| Component | Meaning |
| --- | --- |
| `input: "$items"` | Reads the array field from the current document |
| `as: "item"` | Names the local element variable (without `$$`) |
| `cond: {...}` | Predicate expression; element is kept when true |
| `"$$item.qty"` | Accesses `qty` on variable `item`, not `item.qty` on the root document |
| `limit` (if used) | Caps the number of matching elements, where supported by MongoDB version |

If `as` is omitted, `$filter`'s default element variable is `$$this`. Equivalent syntax:

```javascript
{
  $filter: {
    input: "$items",
    cond: { $gte: ["$$this.qty", 2] }
  }
}
```

**Do not confuse `$filter` with `$match`:** `$match` decides **which documents** flow down the pipeline; `$filter` decides **which elements inside an array** are retained. On a single document's array, `$filter` never splits the document into multiple rows.

### 4.2. Combining Multiple Conditions

Keep lines where both `qty >= 2` and `unitPriceMinor >= 5000`:

```javascript
{
  $filter: {
    input: "$items",
    as: "i",
    cond: {
      $and: [
        { $gte: ["$$i.qty", 2] },
        { $gte: ["$$i.unitPriceMinor", NumberLong(5000)] }
      ]
    }
  }
}
```

In A-101, both SKU-A (12,000, qty 2) and SKU-C (7,000, qty 3) match. Place `$and` **inside `cond`** so both predicates evaluate on **the same element**.

### 4.3. $filter.limit Is Not the $limit Stage

Example keeping at most **one matching element** from the array:

```javascript
{
  $filter: {
    input: "$items",
    as: "i",
    cond: { $gte: ["$$i.qty", 2] },
    limit: 1
  }
}
```

`limit` here bounds **elements in the resulting array**, not documents across the pipeline. `{ $limit: 1 }` is a stage capping the pipeline to **one document**. Check your MongoDB server version before relying on newer operator options.

## 5. $map: Transforming Each Element into a New Value

Requirement: for each line item, compute **line total** `qty × unitPriceMinor`:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A", _id: "A-101" } },
  {
    $project: {
      _id: 1,
      lineTotals: {
        $map: {
          input: "$items",
          as: "i",
          in: { $multiply: ["$$i.qty", "$$i.unitPriceMinor"] }
        }
      }
    }
  }
])
// A-101: lineTotals = [24000, 5000, 21000]
```

`$map` produces an array of the **exact same length and order** as the input array, except when input is null/missing (see data-safety section). It is not a filter: every element yields one value from `in`.

### 5.1. Mapping to Objects Instead of Numbers

```javascript
{
  $map: {
    input: "$items",
    as: "item",
    in: {
      sku: "$$item.sku",
      qty: "$$item.qty",
      subtotalMinor: {
        $multiply: [
          "$$item.qty",
          "$$item.unitPriceMinor"
        ]
      }
    }
  }
}
```

For A-101, this produces three objects (SKU-A, SKU-B, SKU-C), each carrying `subtotalMinor`. The aim is building an **API read model** without mutating stored collection data.

### 5.2. Map After Filter vs. Filter After Map

If you only need line totals for `qty >= 2`:

```javascript
{
  $map: {
    input: {
      $filter: {
        input: "$items",
        as: "item",
        cond: { $gte: ["$$item.qty", 2] }
      }
    },
    as: "selected",
    in: {
      $multiply: [
        "$$selected.qty",
        "$$selected.unitPriceMinor"
      ]
    }
  }
}
// A-101: [24000, 21000]
```

**Filter then map** is cleaner because multiplication runs only on kept elements. If you **map first** to plain numbers, later expressions no longer have `qty` to filter on unless the mapped objects keep `qty`. Define intermediate schemas clearly when composing array expressions.

### 5.3. $map Does Not Update the Source Array

```javascript
db.orders.aggregate([
  { $match: { _id: "A-101" } },
  {
    $project: {
      _id: 1,
      transformed: {
        $map: {
          input: "$items",
          as: "i",
          in: { sku: "$$i.sku" }
        }
      }
    }
  }
])
```

MongoDB returns `transformed` only in the **aggregation result**. Stored documents keep all original line items. Modifying stored arrays requires update APIs or intentional write stages (`$merge`/`$out`); `$map` never writes back by itself.

## 6. $reduce: Folding an Array into a Single Value

`$reduce` is ideal when elements contribute to an **accumulator** (`$$value`), such as a monetary sum, concatenated string, multi-metric summary object, or tag set. Unlike `$map`, output is no longer 1-to-1 with elements: it returns **one single value**.

Syntax:

```javascript
{
  $reduce: {
    input: <array-expression>,
    initialValue: <initial-expression>,
    in: <expression-using-$$value-and-$$this>
  }
}
```

Inside `in`:

- `$$value` is the accumulated value before processing the current element; on the first step, it equals `initialValue`.
- `$$this` is the **current array element**.
- The `in` expression computes the **new accumulator**, which becomes `$$value` on the next iteration.
- MongoDB iterates left-to-right. To iterate in reverse, wrap `input` with `$reverseArray` first.

### 6.1. Reducing lineTotals into a Sum

Suppose `$map` produced:

```javascript
lineTotals: [NumberLong(24000), NumberLong(5000), NumberLong(21000)]
```

Expression:

```javascript
{
  $reduce: {
    input: "$lineTotals",
    initialValue: NumberLong(0),
    in: { $add: ["$$value", "$$this"] }
  }
}
```

Trace:

| Step | `$$value` before step | `$$this` | `$$value` after step |
| --- | ---: | ---: | ---: |
| Init | — | — | 0 |
| 1 | 0 | 24,000 | 24,000 |
| 2 | 24,000 | 5,000 | 29,000 |
| 3 | 29,000 | 21,000 | 50,000 |

A-101 total = **50,000**. On an empty array `[]`, `$reduce` returns **`initialValue`** (here 0). On `null`/missing input, `$reduce` returns `null` per operator semantics; do not conflate those two cases when inputs are unnormalized.

### 6.2. Reducing an Array of Objects Directly

You do not have to run `$map` before summing:

```javascript
{
  $reduce: {
    input: "$items",
    initialValue: NumberLong(0),
    in: {
      $add: [
        "$$value",
        {
          $multiply: [
            "$$this.qty",
            "$$this.unitPriceMinor"
          ]
        }
      ]
    }
  }
}
```

Here `$$this` is the **line-item object**, giving direct access to `$$this.qty` and `$$this.unitPriceMinor`. This is concise when you only want the sum; splitting `$map` + `$reduce` is easier to debug when you also need per-line totals.

### 6.3. Reduce After Filter: Subtotal of Eligible Lines

```javascript
{
  $reduce: {
    input: {
      $filter: {
        input: "$items",
        as: "i",
        cond: { $gte: ["$$i.qty", 2] }
      }
    },
    initialValue: NumberLong(0),
    in: {
      $add: [
        "$$value",
        { $multiply: ["$$this.qty", "$$this.unitPriceMinor"] }
      ]
    }
  }
}
```

A-101 gets 45,000 and A-103 gets 8,000. This folds **only the filtered lines**, not every line in the order.

### 6.4. Reducing into a Multi-Field Summary Object

`initialValue` can be an object, not just a scalar number:

```javascript
{
  $reduce: {
    input: "$items",
    initialValue: {
      lineCount: 0,
      quantityTotal: 0,
      amountMinor: NumberLong(0)
    },
    in: {
      lineCount: { $add: ["$$value.lineCount", 1] },
      quantityTotal: {
        $add: ["$$value.quantityTotal", "$$this.qty"]
      },
      amountMinor: {
        $add: [
          "$$value.amountMinor",
          { $multiply: ["$$this.qty", "$$this.unitPriceMinor"] }
        ]
      }
    }
  }
}
```

Output for A-101:

```javascript
{
  lineCount: 3,
  quantityTotal: 6,
  amountMinor: NumberLong(50000)
}
```

This is a *fold*: every line updates all three accumulator fields. When accumulating multiple metrics, verify units, BSON types, and overflow limits; syntactically valid expressions alone do not guarantee financial correctness.

### 6.5. Reducing Strings in Order

```javascript
{
  $reduce: {
    input: ["A", "B", "C"],
    initialValue: "",
    in: { $concat: ["$$value", "$$this"] }
  }
}
// "ABC"
```

Ordered folding differs completely from set operations. Never use `$setUnion` to preserve string ordering when inputs may repeat.

## 7. Set Operations on Arrays: Deduplicating Without Order Guarantees

MongoDB arrays are **ordered and allow duplicates**. By contrast, set expressions treat arrays as **sets**, discarding positional order and duplicate counts.

For A-101:

```javascript
labels         = ["web", "priority", "web"]
incomingLabels = ["priority", "express", "priority"]
```

### 7.1. $setUnion: Union

```javascript
{
  $setUnion: ["$labels", "$incomingLabels"]
}
```

The resulting set contains **web**, **priority**, and **express**—each once. Never assert that the order must be `["web","priority","express"]`: set operators **do not guarantee element order**.

If an API needs deterministic output order, sort the array afterward with `$sortArray` where supported by your MongoDB version, or sort in an appropriate stage/layer.

### 7.2. $setIntersection: Intersection

```javascript
{
  $setIntersection: ["$labels", "$incomingLabels"]
}
```

Result contains only **priority**. It appears in both arrays; repeating `priority` in the inputs does not duplicate it in the output set.

### 7.3. $setDifference: Directional Difference

```javascript
{
  $setDifference: ["$labels", "$incomingLabels"]
}
// Resulting set: { "web" }
```

Elements in old `labels` missing from `incomingLabels` equal `web`.

Swap the two arguments:

```javascript
{
  $setDifference: ["$incomingLabels", "$labels"]
}
// Resulting set: { "express" }
```

**`A \ B` differs from `B \ A`**. When syncing labels, clearly distinguish **to remove from current** vs. **to add from incoming**.

### 7.4. $setEquals: Same Set of Elements?

```javascript
{
  $setEquals: [
    ["web", "priority", "web"],
    ["priority", "web"]
  ]
}
// true
```

Both arrays differ in order and frequency yet represent `{web, priority}`, so `$setEquals` returns `true`.

If business rules require checking **positional array equality**, do not use `$setEquals`. Compare arrays with order-aware expressions or in application code.

### 7.5. $setIsSubset: Subset Check

```javascript
{
  $setIsSubset: [
    ["priority"],
    ["web", "priority"]
  ]
}
// true
```

Swap arguments:

```javascript
{
  $setIsSubset: [
    ["web", "priority"],
    ["priority"]
  ]
}
// false
```

This checks **set inclusion**, not ordered subsequences. The empty set is a subset of every set by definition; if an empty input means “no permissions granted,” handle that in validation rather than assuming subset `true` proves valid authorization.

### 7.6. $concatArrays Is Not $setUnion

```javascript
{
  $concatArrays: ["$labels", "$incomingLabels"]
}
// ["web","priority","web","priority","express","priority"]
```

`$concatArrays` preserves duplicates and concatenation order. Use concatenation when event/label order and multiplicity matter; use `$setUnion` when you want unique elements regardless of order.

### 7.7. Nested Arrays Are Not Automatically Flattened

Example:

```javascript
{
  $setUnion: [
    [["A", "B"], "C"],
    [["A", "B"], "D"]
  ]
}
```

The sub-array `["A","B"]` is treated as **a single element** by set operators; they do not recursively flatten into `A` and `B`. For 2D arrays or arrays of objects, decide explicitly at **which array depth** set operations apply and normalize elements beforehand.

Equality also follows active BSON/collation comparison rules; for text labels, enforce consistent casing, Unicode normalization, and matching rules. Never assume `$setUnion` collapses `"Web"`, `"web"`, and `"WEB"` into one label automatically.

## 8. Combining $reduce and $setUnion: Collecting Tags Across Elements

Each `items[]` element contains its own `tags[]` array. Requirement: build a **deduplicated order-level tag list** without `$unwind`-ing line items.

```javascript
{
  $reduce: {
    input: "$items",
    initialValue: [],
    in: {
      $setUnion: [
        "$$value",
        { $ifNull: ["$$this.tags", []] }
      ]
    }
  }
}
```

Trace for A-101:

| Step | Tags on current line | Accumulated set (unordered) |
| --- | --- | --- |
| Init | — | `{}` |
| SKU-A | fragile, promotion | `{fragile, promotion}` |
| SKU-B | gift | `{fragile, promotion, gift}` |
| SKU-C | promotion, priority | `{fragile, promotion, gift, priority}` |

The output is an **array representing a set** of four distinct tags. Its BSON/JSON element order is **not part of the contract**.

Here `$ifNull` supplies `[]` when `tags` is null or missing. However, if a malformed document stores `tags` as a String, `$ifNull` **does not** turn a String into an array, and `$setUnion` will fail. Guard against wrong types with `$isArray` + `$cond` (next section), or reject invalid records per application policy.

### 8.1. Can You Use $map Followed by $reduce?

Yes. For instance, `$map` extracts each item's `tags` array, and `$reduce` unions them:

```javascript
{
  $reduce: {
    input: {
      $map: {
        input: "$items",
        as: "i",
        in: { $ifNull: ["$$i.tags", []] }
      }
    },
    initialValue: [],
    in: { $setUnion: ["$$value", "$$this"] }
  }
}
```

This separates **extraction** from **folding**, which helps when inspecting intermediate fields. The direct `$reduce` above is shorter and usually cleaner when you only need the unique tag list.

### 8.2. What If You Must Preserve First-Seen Order While Deduplicating?

Set operators do not guarantee order. If requirements ask to “keep elements in order of first appearance,” use a conditional fold such as `$reduce` with `$in` and `$concatArrays`:

```javascript
{
  $reduce: {
    input: ["web", "priority", "web", "express"],
    initialValue: [],
    in: {
      $cond: [
        { $in: ["$$this", "$$value"] },
        "$$value",
        { $concatArrays: ["$$value", ["$$this"]] }
      ]
    }
  }
}
// ["web", "priority", "express"]
```

This preserves **first-seen order**, at the cost of checking `$in` against the growing accumulator on each step. On huge arrays, measure performance or choose another structure/approach. It is a different contract from an unordered set union.

## 9. Handling Empty Arrays, null, missing, and Wrong Types

A classic legacy-data bug: testing a pipeline on `items: []`, seeing `$reduce` return 0, and assuming `items: null` or **a missing `items` field** also returns 0. Without explicit normalization, that assumption fails.

### 9.1. Behavior Matrix

| Expression input | `$filter` | `$map` | `$reduce` |
| --- | --- | --- | --- |
| Valid non-empty array | Sub-array | Transformed array | Accumulated value |
| Empty array `[]` | `[]` | `[]` | `initialValue` |
| `null` or missing field | `null` | `null` | `null` |
| Non-array and non-null/missing (e.g., String) | Error | Error | Error |

Set operators also require array inputs; never pass Strings, numbers, or objects expecting automatic coercion. Null/missing semantics can differ across set operators, `$group` accumulators, and versions—**normalize inputs explicitly** instead of relying on untested null behavior.

### 9.2. Guarding Only null/missing with $ifNull

```javascript
{
  $filter: {
    input: { $ifNull: ["$items", []] },
    as: "item",
    cond: { $gte: ["$$item.qty", 2] }
  }
}
```

`$ifNull` substitutes `[]` when `items` is null or missing. Yet if `items` holds the String `"bad"`, `$ifNull` returns `"bad"` and `$filter` still errors because the input is not an array.

### 9.3. Type-Safe Normalization with $isArray and $cond

```javascript
{
  $cond: [
    { $isArray: "$items" },
    "$items",
    []
  ]
}
```

This keeps the value only if it is an array; null, missing, and wrong types all become `[]`. Normalize into `safeItems` in an early `$set`:

```javascript
{
  $set: {
    safeItems: {
      $cond: [
        { $isArray: "$items" },
        "$items",
        []
      ]
    }
  }
}
```

Subsequent `$filter`, `$map`, and `$reduce` expressions then reference `"$safeItems"`, avoiding repetitive checks throughout the pipeline.

**Trade-off to keep explicit:** falling back to `[]` keeps the pipeline from crashing, yet can **hide bad data**. For financial totals, item counts, or permissions, you may need an `invalidItems` flag to count and quarantine corrupt records. Never equate `items: null` with `items: []` if business rules prohibit missing data.

### 9.4. Guarding Nested Arrays Inside Elements

```javascript
{
  $reduce: {
    input: "$safeItems",
    initialValue: [],
    in: {
      $setUnion: [
        "$$value",
        {
          $cond: [
            { $isArray: "$$this.tags" },
            "$$this.tags",
            []
          ]
        }
      ]
    }
  }
}
```

This also handles line items where `tags` is null, missing, or wrong-typed. Still, `qty` and `unitPriceMinor` require their own type/domain validation; guarding the outer array does not protect arithmetic inside `$multiply`.

### 9.5. Do Not Confuse missing/null Field with a null Array Element

For example, `[null, "A"]` is **an array containing a null element**, unlike `labels: null`. Set operators can keep `null` as a member of the set, and `$size` counts it as an element. If null elements must be stripped from tag arrays, do so explicitly:

```javascript
{
  $filter: {
    input: "$safeLabels",
    as: "label",
    cond: { $ne: ["$$label", null] }
  }
}
```

If the goal is strictly valid non-empty Strings, also check data types, whitespace, casing, and label formatting rules.

## 10. Complete Pipeline: filter + map + reduce + Set Operators

On the dataset from Section 3, this pipeline scopes to tenant A, normalizes arrays, derives intermediate arrays, and shapes the API response:

```javascript
db.orders.aggregate([
  // 1. Keep only the target tenant.
  {
    $match: {
      tenantId: "TENANT-A"
    }
  },

  // 2. Normalize missing/null/wrong-type fields into empty arrays.
  {
    $set: {
      safeItems: {
        $cond: [
          { $isArray: "$items" },
          "$items",
          []
        ]
      },
      safeLabels: {
        $cond: [
          { $isArray: "$labels" },
          "$labels",
          []
        ]
      },
      safeIncomingLabels: {
        $cond: [
          { $isArray: "$incomingLabels" },
          "$incomingLabels",
          []
        ]
      }
    }
  },

  // 3. Build intermediate arrays and sets.
  {
    $set: {
      eligibleItems: {
        $filter: {
          input: "$safeItems",
          as: "item",
          cond: { $gte: ["$$item.qty", 2] }
        }
      },
      lineTotals: {
        $map: {
          input: "$safeItems",
          as: "item",
          in: {
            $multiply: [
              "$$item.qty",
              "$$item.unitPriceMinor"
            ]
          }
        }
      },
      itemTags: {
        $reduce: {
          input: "$safeItems",
          initialValue: [],
          in: {
            $setUnion: [
              "$$value",
              {
                $cond: [
                  { $isArray: "$$this.tags" },
                  "$$this.tags",
                  []
                ]
              }
            ]
          }
        }
      },
      unionLabels: {
        $setUnion: ["$safeLabels", "$safeIncomingLabels"]
      },
      sharedLabels: {
        $setIntersection: ["$safeLabels", "$safeIncomingLabels"]
      },
      removedLabels: {
        $setDifference: ["$safeLabels", "$safeIncomingLabels"]
      },
      labelSetsEqual: {
        $setEquals: ["$safeLabels", "$safeIncomingLabels"]
      },
      labelsAllIncluded: {
        $setIsSubset: ["$safeLabels", "$safeIncomingLabels"]
      }
    }
  },

  // 4. Use the derived arrays to compute totals.
  {
    $set: {
      totalMinor: {
        $reduce: {
          input: "$lineTotals",
          initialValue: { $toLong: 0 },
          in: { $add: ["$$value", "$$this"] }
        }
      },
      eligibleSubtotalMinor: {
        $reduce: {
          input: "$eligibleItems",
          initialValue: { $toLong: 0 },
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.qty",
                  "$$this.unitPriceMinor"
                ]
              }
            ]
          }
        }
      }
    }
  },

  // 5. Return only API-facing fields.
  {
    $project: {
      _id: 1,
      status: 1,
      eligibleSkus: {
        $map: {
          input: "$eligibleItems",
          as: "i",
          in: "$$i.sku"
        }
      },
      lineTotals: 1,
      totalMinor: 1,
      eligibleSubtotalMinor: 1,
      itemTags: 1,
      unionLabels: 1,
      sharedLabels: 1,
      removedLabels: 1,
      labelSetsEqual: 1,
      labelsAllIncluded: 1
    }
  },
  { $sort: { _id: 1 } }
])
```

### 10.1. Expected Results

Arrays emitted by set operators are shown below **as unordered sets**:

| Document | `eligibleSkus` | `lineTotals` | `totalMinor` | `eligibleSubtotalMinor` |
| --- | --- | --- | ---: | ---: |
| A-101 | [SKU-A, SKU-C] | [24000, 5000, 21000] | 50000 | 45000 |
| A-102 | [] | [] | 0 | 0 |
| A-103 | [SKU-E] | [9000, 8000] | 17000 | 8000 |
| A-104 | [] | [] | 0 | 0 |

| Document | `itemTags` | `unionLabels` | `sharedLabels` | `removedLabels` |
| --- | --- | --- | --- | --- |
| A-101 | {fragile, promotion, gift, priority} | {web, priority, express} | {priority} | {web} |
| A-102 | {} | {web} | {} | {} |
| A-103 | {express, priority} | {app, express, priority} | {express} | {app} |
| A-104 | {} | {web} | {} | {} |

`labelSetsEqual` is `false` for all four documents under this seed. `labelsAllIncluded` is: A-101=`false` (`web` is not in incoming); A-102=`true` (empty set); A-103=`false` (`app` is not in incoming); A-104=`true`.

B-201 **does not appear** thanks to the opening `$match`. This invariant must be tested; computing sets and reduces accurately while missing the tenant filter is still a critical security bug.

### 10.2. Tracking Schema and Document Count

| Stage | Tenant A document count | Key fields introduced |
| --- | ---: | --- |
| Collection | 5 docs across all tenants | `items`, `labels`, `incomingLabels` |
| `$match` | 4 | Source schema; drops B-201 |
| `$set` normalize | 4 | `safeItems`, `safeLabels`, `safeIncomingLabels` |
| `$set` array operators | 4 | `eligibleItems`, `lineTotals`, `itemTags`, label sets |
| `$set` reduce totals | 4 | `totalMinor`, `eligibleSubtotalMinor` |
| `$project`/`$sort` | 4 | Report DTO; leaves source docs untouched |

Each `$map`/`$filter` works inside one document, so **document count does not expand with item count**. Switching to `$unwind: "$items"` would expand A-101 into three documents, A-103 into two, and drop A-102/A-104 without special handling; subsequent `$group` would need care to avoid overcounting.

### 10.3. Why Shouldn't Stage Four Be Arbitrarily Merged into Stage Three?

Here `totalMinor` reads `"$lineTotals"` and `eligibleSubtotalMinor` reads `"$eligibleItems"`, both created **in stage three**. Never write them in the same `$set` assuming a newly added field can be referenced by name within that very same stage as though it had already completed. Splitting into two `$set` stages makes **inter-stage dependencies** explicit, debuggable, and testable.

## 11. Implementing in Spring Data MongoDB

Spring Data MongoDB offers `Aggregation` and builders alongside `ArrayOperators`, `ConditionalOperators`, `ArithmeticOperators`, etc., for expressions. Exact builder names and overloads vary across Spring Data versions. When pipelines use deeply nested expressions, a clear learning approach is **keeping the exact BSON structure** in explicit `AggregationOperation` stages, then refactoring to DSL once the contract is tested.

### 11.1. Source Entity

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String status,
    List<OrderItem> items,
    List<String> labels,
    List<String> incomingLabels
) {
    public record OrderItem(
        String sku,
        int qty,
        long unitPriceMinor,
        List<String> tags
    ) {}
}
```

Because `A-104` has `items: null`, `items` can deserialize as null; declaring `List<OrderItem>` in Java **does not make MongoDB treat null as an empty array**. The pipeline handles null via `$isArray`/`$cond` before running array expressions.

### 11.2. MongoTemplate Combining Typed Match and BSON Stages

File `OrderArrayAnalyticsService.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class OrderArrayAnalyticsService {

    private final MongoTemplate template;

    public OrderArrayAnalyticsService(MongoTemplate template) {
        this.template = template;
    }

    // Use only with static, trusted JSON stages authored by the application.
    private static AggregationOperation stage(String json) {
        return context -> Document.parse(json);
    }

    public List<Document> summaries(String permittedTenantId) {
        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid tenant");
        }

        Aggregation aggregation = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is(permittedTenantId)
            ),

            stage("""
                {
                  "$set": {
                    "safeItems": {
                      "$cond": [
                        { "$isArray": "$items" }, "$items", []
                      ]
                    },
                    "safeLabels": {
                      "$cond": [
                        { "$isArray": "$labels" }, "$labels", []
                      ]
                    },
                    "safeIncomingLabels": {
                      "$cond": [
                        { "$isArray": "$incomingLabels" },
                        "$incomingLabels", []
                      ]
                    }
                  }
                }
                """),

            stage("""
                {
                  "$set": {
                    "eligibleItems": {
                      "$filter": {
                        "input": "$safeItems",
                        "as": "i",
                        "cond": { "$gte": ["$$i.qty", 2] }
                      }
                    },
                    "lineTotals": {
                      "$map": {
                        "input": "$safeItems",
                        "as": "i",
                        "in": {
                          "$multiply": [
                            "$$i.qty", "$$i.unitPriceMinor"
                          ]
                        }
                      }
                    },
                    "itemTags": {
                      "$reduce": {
                        "input": "$safeItems",
                        "initialValue": [],
                        "in": {
                          "$setUnion": [
                            "$$value",
                            {
                              "$cond": [
                                { "$isArray": "$$this.tags" },
                                "$$this.tags", []
                              ]
                            }
                          ]
                        }
                      }
                    },
                    "unionLabels": {
                      "$setUnion": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "sharedLabels": {
                      "$setIntersection": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "removedLabels": {
                      "$setDifference": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "labelSetsEqual": {
                      "$setEquals": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "labelsAllIncluded": {
                      "$setIsSubset": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    }
                  }
                }
                """),

            stage("""
                {
                  "$set": {
                    "totalMinor": {
                      "$reduce": {
                        "input": "$lineTotals",
                        "initialValue": { "$toLong": 0 },
                        "in": { "$add": ["$$value", "$$this"] }
                      }
                    },
                    "eligibleSubtotalMinor": {
                      "$reduce": {
                        "input": "$eligibleItems",
                        "initialValue": { "$toLong": 0 },
                        "in": {
                          "$add": [
                            "$$value",
                            {
                              "$multiply": [
                                "$$this.qty",
                                "$$this.unitPriceMinor"
                              ]
                            }
                          ]
                        }
                      }
                    }
                  }
                }
                """),

            stage("""
                {
                  "$project": {
                    "_id": 1,
                    "status": 1,
                    "eligibleSkus": {
                      "$map": {
                        "input": "$eligibleItems",
                        "as": "i",
                        "in": "$$i.sku"
                      }
                    },
                    "lineTotals": 1,
                    "totalMinor": 1,
                    "eligibleSubtotalMinor": 1,
                    "itemTags": 1,
                    "unionLabels": 1,
                    "sharedLabels": 1,
                    "removedLabels": 1,
                    "labelSetsEqual": 1,
                    "labelsAllIncluded": 1
                  }
                }
                """),

            Aggregation.sort(Sort.by("_id"))
        );

        AggregationResults<Document> results = template.aggregate(
            aggregation, "orders", Document.class);

        return results.getMappedResults();
    }
}
```

This example uses Java 17+ and Spring Data MongoDB with `AggregationOperation`/`MongoTemplate.aggregate(...)`. `Document.parse(...)` parses **strict JSON** (not shell JavaScript with `NumberLong(...)`), which is why the initial value uses `"$toLong": 0` instead of `mongosh`'s `NumberLong(0)`.

**Limitations of raw stages:**

- Stage strings are **static application constants**, never concatenated JSON or field names from requests. `permittedTenantId` is bound safely via `Criteria`, not string concatenation.
- `Document.parse` emits literal **BSON field names**. If the Java entity uses `@Field("unit_price_minor")` or custom converters, `"unitPriceMinor"` inside raw JSON **will not auto-map from the Java property**. Update BSON names manually or use a metadata-aware DSL.
- Raw stages do not automatically benefit from all typed-builder mapping/validation features. Verify the actual BSON pipeline on the server and when upgrading Spring Data.
- `AggregationResults<Document>` is an **output read model**, not an `OrderDocument` to pass to `save`. After `$project`, many entity fields are gone and computed fields are present.

### 11.3. Output DTO Once the Contract Is Settled

You can convert result `Document`s into a DTO:

```java
import java.util.List;
import org.bson.Document;

public record OrderArraySummary(
    String id,
    String status,
    List<String> eligibleSkus,
    long totalMinor,
    long eligibleSubtotalMinor,
    List<String> itemTags,
    List<String> unionLabels
) {
    public static OrderArraySummary from(Document doc) {
        return new OrderArraySummary(
            doc.getString("_id"),
            doc.getString("status"),
            doc.getList("eligibleSkus", String.class),
            ((Number) doc.get("totalMinor")).longValue(),
            ((Number) doc.get("eligibleSubtotalMinor")).longValue(),
            doc.getList("itemTags", String.class),
            doc.getList("unionLabels", String.class)
        );
    }
}
```

For financial outputs, this is a minimal conversion for the lesson; production code needs field presence validation, overflow checks, and consistent currency/BSON typing. If the API needs deterministic label ordering, **sort arrays before returning** instead of relying on `$setUnion` output order.

### 11.4. Repository @Aggregation for Static Pipelines

`@Aggregation` fits **shorter, static** JSON pipelines, such as returning eligible SKUs for a tenant:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        """
        {
          '$project': {
            '_id': 1,
            'eligibleSkus': {
              '$map': {
                'input': {
                  '$filter': {
                    'input': { '$ifNull': ['$items', []] },
                    'as': 'i',
                    'cond': { '$gte': ['$$i.qty', 2] }
                  }
                },
                'as': 'selected',
                'in': '$$selected.sku'
              }
            }
          }
        }
        """
    })
    List<Document> findEligibleSkus(String tenantId);
}
```

`?0` binds the positional tenant parameter; `$$i`/`$$selected` are MongoDB aggregation variables and **not** Java placeholders. `$ifNull` guards only null/missing here; if malformed schemas can store a String instead of an array, use `$isArray` as in the main pipeline.

**Distinguish the two `Aggregation` types in Java:** `org.springframework.data.mongodb.repository.Aggregation` is the repository annotation; `org.springframework.data.mongodb.core.aggregation.Aggregation` is the pipeline builder class. Avoid importing the wrong one.

### 11.5. Not Every Array Query Needs Aggregation

If you only want to find orders **having at least one item** matching a predicate, a regular query with `Criteria.elemMatch(...)` is simpler:

```java
Query query = Query.query(
    Criteria.where("tenantId").is(permittedTenantId)
        .and("items")
        .elemMatch(Criteria.where("qty").gte(2)));
```

This **selects documents**, without returning a filtered `eligibleItems` sub-array. Use `$filter` when you want to **keep and return only matching elements**; use `$elemMatch` when you want to **decide whether a document matches**. They solve different tasks.

## 12. Integration Testing Against Real BSON

Mocking `MongoTemplate` does not prove MongoDB evaluates `$$this`, `$reduce`, `$setUnion`, or nulls accurately. Test against an **isolated MongoDB server** with real nested BSON arrays. `@DataMongoTest` paired with Testcontainers is a clean setup once test connections are configured.

### 12.1. Creating a Fixture with Order, Duplicates, Nulls, and Another Tenant

File `OrderArrayAggregationTest.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderArrayAggregationTest {

    @Autowired
    MongoTemplate template;

    private static Document item(
            String sku, int qty, long price, String... tags) {
        return new Document("sku", sku)
            .append("qty", qty)
            .append("unitPriceMinor", price)
            .append("tags", List.of(tags));
    }

    private static Document order(
            String id,
            String tenantId,
            Object items,
            Object labels,
            List<String> incomingLabels) {
        return new Document("_id", id)
            .append("tenantId", tenantId)
            .append("status", "PAID")
            .append("items", items)
            .append("labels", labels)
            .append("incomingLabels", incomingLabels);
    }

    private OrderArrayAnalyticsService service() {
        return new OrderArrayAnalyticsService(template);
    }

    private Document summary(String tenantId, String id) {
        return service().summaries(tenantId).stream()
            .filter(row -> id.equals(row.getString("_id")))
            .findFirst()
            .orElseThrow();
    }

    @BeforeEach
    void seed() {
        // STRICTLY run only on an isolated test database.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("A-101", "TENANT-A", List.of(
                    item("SKU-A", 2, 12000L,
                        "fragile", "promotion"),
                    item("SKU-B", 1, 5000L, "gift"),
                    item("SKU-C", 3, 7000L,
                        "promotion", "priority")),
                List.of("web", "priority", "web"),
                List.of("priority", "express", "priority")),

            order("A-102", "TENANT-A",
                List.of(), List.of(), List.of("web")),

            order("A-103", "TENANT-A", List.of(
                    item("SKU-D", 1, 9000L, "express"),
                    item("SKU-E", 4, 2000L,
                        "priority", "express")),
                List.of("app", "express"),
                List.of("express", "priority")),

            order("A-104", "TENANT-A",
                null, null, List.of("web")),

            order("B-201", "TENANT-B", List.of(
                    item("SKU-Z", 100, 100000L, "private")),
                List.of("private"),
                List.of("private", "priority"))
        ));
    }

    @Test
    void filterAndMapKeepOrderButRemoveIneligibleItems() {
        Document a = summary("TENANT-A", "A-101");

        assertThat(a.getList("eligibleSkus", String.class))
            .containsExactly("SKU-A", "SKU-C");

        List<Number> lineTotals =
            a.getList("lineTotals", Number.class);

        assertThat(lineTotals.stream()
                .mapToLong(Number::longValue)
                .toArray())
            .containsExactly(24000L, 5000L, 21000L);

        assertThat(a.get("totalMinor", Number.class)
                .longValue())
            .isEqualTo(50000L);
        assertThat(a.get("eligibleSubtotalMinor", Number.class)
                .longValue())
            .isEqualTo(45000L);
    }

    @Test
    void reduceWorksForAnotherOrder() {
        Document a = summary("TENANT-A", "A-103");

        assertThat(a.getList("eligibleSkus", String.class))
            .containsExactly("SKU-E");
        assertThat(a.get("totalMinor", Number.class)
                .longValue())
            .isEqualTo(17000L);
        assertThat(a.get("eligibleSubtotalMinor", Number.class)
                .longValue())
            .isEqualTo(8000L);
    }

    @Test
    void setOperatorsIgnoreDuplicatesAndNotPromiseOrder() {
        Document a = summary("TENANT-A", "A-101");

        assertThat(a.getList("itemTags", String.class))
            .containsExactlyInAnyOrder(
                "fragile", "promotion", "gift", "priority");
        assertThat(a.getList("unionLabels", String.class))
            .containsExactlyInAnyOrder(
                "web", "priority", "express");
        assertThat(a.getList("sharedLabels", String.class))
            .containsExactlyInAnyOrder("priority");
        assertThat(a.getList("removedLabels", String.class))
            .containsExactlyInAnyOrder("web");
        assertThat(a.getBoolean("labelSetsEqual")).isFalse();
        assertThat(a.getBoolean("labelsAllIncluded")).isFalse();
    }

    @Test
    void emptyAndNullInputAreNormalizedByContract() {
        for (String id : List.of("A-102", "A-104")) {
            Document row = summary("TENANT-A", id);

            assertThat(row.getList("eligibleSkus", String.class))
                .isEmpty();
            assertThat(row.getList("lineTotals", Number.class))
                .isEmpty();
            assertThat(row.getList("itemTags", String.class))
                .isEmpty();
            assertThat(row.get("totalMinor", Number.class)
                    .longValue())
                .isZero();
            assertThat(row.getBoolean("labelsAllIncluded")).isTrue();
        }
    }

    @Test
    void aggregationMustNotIncludeOtherTenant() {
        List<Document> a = service().summaries("TENANT-A");

        assertThat(a).hasSize(4);
        assertThat(a)
            .extracting(row -> row.getString("_id"))
            .containsExactly("A-101", "A-102", "A-103", "A-104");

        List<Document> b = service().summaries("TENANT-B");
        assertThat(b).hasSize(1);
        assertThat(b.get(0).getString("_id")).isEqualTo("B-201");
        assertThat(b.get(0).get("totalMinor", Number.class)
                .longValue())
            .isEqualTo(10000000L);
    }

    @Test
    void aggregationDoesNotModifyStoredOrder() {
        service().summaries("TENANT-A");

        Document stored = template.getCollection("orders")
            .find(new Document("_id", "A-101"))
            .first();

        assertThat(stored).isNotNull();
        assertThat(stored.getList("labels", String.class))
            .containsExactly("web", "priority", "web");
        assertThat(stored.containsKey("totalMinor")).isFalse();
        assertThat(stored.containsKey("eligibleItems")).isFalse();
    }
}
```

`containsExactly(...)` assertions apply only to arrays whose **order is guaranteed by contract**, such as `$filter` and `$map`. For `$setUnion`, `$setIntersection`, and `$setDifference`, tests use `containsExactlyInAnyOrder(...)` since MongoDB does not promise set ordering.

**Execution warning:** `deleteMany(new Document())` wipes the entire `orders` collection on the connected database. Configure a **dedicated isolated test MongoDB**, never production or a shared database. `@DataMongoTest` uses the standard Spring Boot slice package; verify imports across major Spring Boot upgrades. Gradle/tests were not executed while writing this guide; verify compilation and execution in your project environment.

### 12.2. Testing Malformed Data Cases

Consider adding this fixture:

```javascript
{
  _id: "A-BAD",
  tenantId: "TENANT-A",
  items: "not-an-array",
  labels: ["web", null, "web"],
  incomingLabels: ["app"]
}
```

The main pipeline with `$isArray` turns the String `items` into `[]`. Yet if business rules forbid an order with invalid items, tests **should not simply assert total = 0 and pass**: enforce validation flags or reject bad writes at ingestion.

If an element inside `items` contains `qty: "2"` or `unitPriceMinor: "12000"`, guarding **the outer array type** still does not guarantee `$multiply` succeeds. Test element types separately, apply schema validation, normalize BSON, or use `$convert` with explicit `onError`/`onNull` policies.

### 12.3. Additional Test Matrix

| Scenario | What to verify |
| --- | --- |
| Array with duplicates | `$filter`/`$map` preserve duplicates; set operators deduplicate |
| Empty array | `$reduce` returns `initialValue` |
| Null/missing field | `$isArray` + `$cond` yields `[]` per contract |
| Non-array field | Pipeline fails if unnormalized; does not silently swallow business errors |
| Items missing `tags` | `itemTags` succeeds when guarded by `$isArray` |
| Items missing price/qty | Explicit validation, exclusion, or error policy; no synthetic revenue |
| Nested arrays | Set operators do not auto-flatten multi-level arrays |
| Tag casing | Matches chosen collation/normalization rules |
| Tenant isolation | B-201 excluded when querying tenant A |
| API requiring ordered tags | Never assert `$setUnion` order; sort explicitly |
| Large data | Measure memory, docs examined, duration, output size |
| Read-only aggregation | No temporary fields persisted to source BSON |

## 13. $filter/$map/$reduce vs. $unwind + $group?

The same array problem can often be solved multiple ways, with no single winner across all scenarios:

| Requirement | Array expressions fit well | `$unwind`/`$group` fits well |
| --- | --- | --- |
| Compute order total **per order document** | `$map` + `$reduce`, or direct `$reduce` | Possible, but requires re-grouping by order |
| Extract high-qty items inside each order | `$filter` | `$unwind` + `$match` + `$group` for complex transforms |
| Build unique tag list per order | `$reduce` + `$setUnion` | Multi-level `$unwind` + group for deep tag analytics |
| Count SKU occurrences across **all orders** | Partial per-order prep possible | `$unwind` + `$group` by SKU is most natural |
| Group items by attribute for tenant-wide revenue | Awkward across documents | `$unwind` → `$group` fits naturally |
| Keep one output document per order | Preserves cardinality easily | Must re-group after unwind |
| Huge arrays or very wide output documents | Must watch memory and doc size | Streams into separate documents, though group/sort costs apply |

### 13.1. Comparison Example: Per-Order Total via unwind

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$_id",
      totalMinor: {
        $sum: {
          $multiply: ["$items.qty", "$items.unitPriceMinor"]
        }
      }
    }
  }
])
```

With this approach, A-101 and A-103 sum accurately; **A-102 (empty array) and A-104 (null)** disappear because default `$unwind` drops them. If the contract requires keeping itemless orders with total 0, you need `preserveNullAndEmptyArrays` plus null/numeric handling—or `$reduce` over a normalized array as in the main pipeline.

### 13.2. When Grouping Across Items of Many Orders

Example summing quantity sold by SKU across all paid orders:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      quantitySold: { $sum: "$items.qty" },
      grossMinor: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceMinor"
          ]
        }
      }
    }
  },
  { $sort: { quantitySold: -1, _id: 1 } }
])
```

This is **cross-document analysis by SKU**, unlike `$reduce` operating **per order document**. Never confuse the two problems and pick an operator by name alone.

### 13.3. $size and Counting Elements After Filtering

To count matching lines while keeping one document per order:

```javascript
{
  $size: {
    $filter: {
      input: "$safeItems",
      as: "item",
      cond: { $gte: ["$$item.qty", 2] }
    }
  }
}
```

A-101 has 2 eligible lines; A-103 has 1. `$size` counts **array elements**, not summed `qty`. To sum total unit quantities, use `$reduce` over `qty` on the filtered lines.

## 14. Performance Diagnostics and Execution Plans

For array expressions, MongoDB evaluates elements on **documents passing `$match`**. An index speeds up selecting matching documents, yet `$map`/`$reduce` do not gain a special index for intermediate array elements.

### 14.1. Filter Early on Document Fields

Candidate index for frequent tenant + status queries:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_order_tenant_status" }
)
```

If a report counts only PAID orders, start with:

```javascript
{
  $match: {
    tenantId: "TENANT-A",
    status: "PAID"
  }
}
```

This shrinks how many documents run array expressions. Never add a `PAID` filter solely for speed if business rules require both `NEW` and `PAID` as in our example.

### 14.2. $filter Does Not Replace an Indexed $match

This pipeline:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "i",
          cond: { $gte: ["$$i.qty", 2] }
        }
      }
    }
  }
])
```

still passes A-102 and A-104 through the pipeline, yielding empty arrays or nulls. If you only want **documents that have at least one qualifying item**, move that predicate into `$match` first:

```javascript
{
  $match: {
    tenantId: "TENANT-A",
    items: { $elemMatch: { qty: { $gte: 2 } } }
  }
}
```

You can still follow with `$filter` to return **only the matching items**. With a matching multikey index on `items.qty` alongside `tenantId`, the initial filter can use the index. Remember: `$elemMatch` selects **documents**, while `$filter` builds **sub-arrays**; they are not interchangeable.

### 14.3. Running explain on the Actual Pipeline

Abbreviated cost-check example:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      totalMinor: {
        $reduce: {
          input: {
            $cond: [
              { $isArray: "$items" },
              "$items",
              []
            ]
          },
          initialValue: { $toLong: 0 },
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.qty",
                  "$$this.unitPriceMinor"
                ]
              }
            ]
          }
        }
      }
    }
  }
])
```

Watch keys/docs examined, index vs. collection scans, execution time, output size, and server load. Explain structures evolve across MongoDB versions; never assume an unprinted stage name was skipped—the optimizer can merge or push down stages when semantics allow.

### 14.4. Large Arrays and Iteration Cost

- `$map`/`$filter` inspect every element in the input array for each matched document.
- `$reduce` using an array accumulator with repeated `$concatArrays` creates many intermediate copies; avoid on huge arrays without benchmarking.
- Preserving order while deduplicating via `$in` on a growing array scales poorly on long lists; consider alternative structures or processing when arrays grow large.
- `$setUnion` deduplicates at set-processing cost; avoid materializing dozens of intermediate fields if the client only needs two summary numbers.
- If arrays or outputs grow large, mind BSON document limits, pipeline memory, and multi-document alternatives. Never enable `allowDiskUse` assuming array expressions automatically become cheap.

### 14.5. When an API Needs Ordered Results from Set Operations

Set operations do not guarantee order. On MongoDB servers supporting `$sortArray` (introduced in MongoDB 5.2), you can sort set outputs:

```javascript
{
  $sortArray: {
    input: "$unionLabels",
    sortBy: 1
  }
}
```

Place this **after the stage that creates `unionLabels`**, such as in a new `$set`. If supporting older servers lacking `$sortArray`, sort via another pipeline approach or in Java. Never write tests asserting arbitrary `$setUnion` output order as a contract.

## 15. Security, Consistency, and Sensitive Data

Arrays often hold **permissions, sensitive labels, or business keys**. Set operators are convenient for intersections and shared rights, yet they never replace security enforcement:

### 15.1. Empty Set Is a Subset of Every Set

```javascript
{
  $setIsSubset: [[], ["read", "write"]]
}
// true
```

That is mathematically true in set theory, yet treating “empty required permissions array” as “user authorized” opens a security hole. **Design authorization in the service/security layer**—never equate every `true` from `$setIsSubset` with an access grant.

### 15.2. Modifying Labels Must Not Erase Audit History

`$setUnion` drops duplicate tags/labels and `$setDifference` computes removals. If `labels` tracks insertion order or duplicate counts for auditing, never overwrite the source array with a `$setUnion` output. Keep read-only reporting models separate from data updates and migrations.

### 15.3. Read Aggregations Are Not Cross-Call Transaction Snapshots

The read pipelines shown here do not modify collections. If a different pipeline writes via `$merge`/`$out`, that requires explicit write permissions and consistency design. When running multiple separate queries/aggregations under concurrent writes, do not assume they observe one shared snapshot without proper read concern or transaction design.

### 15.4. Never Interpolate Raw Pipelines from Input

In the Java service, JSON stage strings are **internal constants** and tenant is bound via `Criteria`. Never let clients supply `$...` operators, JSON fragments, or expressions passed to `Document.parse(...)`. If an API lets users choose fields or conditions, enforce a strict **allowlist** of application-controlled fields and branches.

## 16. Common Array-Processing Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| `$map` returns `null` instead of `[]` | Input array is `null` or missing | Normalize with `$ifNull` or `$isArray` + `$cond` |
| Aggregation errors with `input must be an array` | Field contains a String/object instead of an array | Validate BSON or normalize explicitly |
| `$reduce` returns `null` for itemless orders | Input is `null`/missing, not `[]` | Coerce to `[]` per contract or flag error record |
| Total is always 0 or abnormally low | Missing/wrong-typed qty/price or earlier filter dropped rows | Check `$type`, intermediate fields, step by step |
| `$$item.qty` evaluates to nothing | Typo in `as` or wrote `"$item.qty"` instead of `"$$item.qty"` | Distinguish `$` field path from `$$` local variable |
| Newly added field unreadable inside the same stage | Referenced derived field in the same `$set` | Split dependent calculations into sequential stages |
| `$filter` still returns documents with zero matching items | `$filter` trims arrays, not documents | Use `$match`/`$elemMatch` to filter documents |
| `$map` outputs fewer elements than expected | Preceded by `$filter` or missing input | Track array cardinality across each expression |
| `$unwind` causes double counting in reports | Document duplicated per array element | Re-group by proper key or use array expressions |
| `$setUnion` output order changes across runs | Set operators guarantee no order | Sort explicitly when API requires ordered output |
| `$concatArrays` keeps duplicate labels | Concatenation does not deduplicate | Use `$setUnion` when unique sets are intended |
| `$setDifference` returns opposite direction | Swapped A and B arguments | Define explicitly: “removed” = current minus incoming |
| `$setIsSubset` returns `true` for empty input | Empty set is subset of all sets | Never use as an access decision on unvalidated input |
| Nested tag arrays stay unflattened after union | Set operators treat sub-arrays as single elements | Flatten/normalize to the target depth first |
| Reading report output into source entity fails | `$project` changed the output schema | Use `Document`/DTOs; never save partial entities |
| Works in `mongosh` yet fails in Java | Raw BSON stage uses Java property instead of `@Field` BSON name | Check mapped BSON and converters on real data |
| Index exists yet pipeline is slow | `$filter`/`$reduce` scans huge arrays or filter is unselective | Run `explain`, shrink input, review schema/indexes |
| Another tenant's data appears in report | Missing tenant in `$match` or mis-scoped `$or` | Enforce tenant upfront and write anti-leak integration tests |

## 17. Checklist for Designing an Array-Processing Pipeline

1. **What does each source document represent?** Order, line item, shipment, permission record? Should output keep one document per source or aggregate across documents?
2. **Can input arrays be null, missing, or wrong-typed?** Enforce schema validation or explicit fallbacks; never assume empty array and null mean the same thing.
3. **Filtering documents or filtering elements?** `$match`/`$elemMatch` selects documents; `$filter` selects elements inside each document's array.
4. **Do order and multiplicity matter?** `$map`/`$filter` preserve relative order; set operators deduplicate and offer no order guarantee.
5. **Are variables scoped properly?** `"$items"` reads a document field; `"$$item.qty"` reads a local variable; `$$value`/`$$this` belong to `$reduce`.
6. **Need a scalar/object or an array?** `$map` yields an array; `$reduce` yields any single value.
7. **Which fields does each stage introduce?** Split into sequential stages whenever a later expression reads a newly derived field.
8. **Are element fields consistently typed?** Especially quantities, money, timestamps, and nested tags; validate or convert with explicit error policies.
9. **Are tenant/authorization constraints enforced?** Place an authenticated `$match` early and test cross-tenant isolation.
10. **What DTO receives the output?** Never map partial aggregation outputs back into full entities for persistence.
11. **Tested empty arrays, nulls, duplicates, nested arrays, and set order?**
12. **Benchmarked on realistic scale?** Filter indexes, array lengths, memory/result size, and `explain` plans.

## 18. Practice Exercise

A shipping system stores documents like:

```javascript
{
  _id: "SHIP-001",
  tenantId: "TENANT-X",
  state: "READY",
  packages: [
    {
      code: "PK-A",
      weightGram: 1200,
      feePerKgMinor: NumberLong(15000),
      labels: ["fragile", "cold"]
    },
    {
      code: "PK-B",
      weightGram: 500,
      feePerKgMinor: NumberLong(20000),
      labels: ["cold", "priority"]
    },
    {
      code: "PK-C",
      weightGram: 2000,
      feePerKgMinor: NumberLong(10000),
      labels: ["fragile"]
    }
  ],
  currentLabels: ["cold", "priority", "cold"],
  desiredLabels: ["priority", "insured"]
}
```

Exercise convention: for each package, the fee is `weightGram / 1000 × feePerKgMinor`; the exercise uses integer grams and assumes division/multiplication follow system currency rules. In production, specify rounding and `Decimal128` for fractional amounts; never feed raw `Double` arithmetic straight into billing.

Tasks:

1. Use `$match` to restrict `tenantId=TENANT-X` and `state=READY`.
2. Use `$filter` to keep packages with `weightGram >= 1000`; predict the surviving package codes.
3. Use `$map` to emit objects containing `code` and `feeMinor` for each package.
4. Use `$reduce` to sum `feeMinor`, stating the rounding rule before summing.
5. Use `$reduce` combined with `$setUnion` to collect labels appearing on **any package**.
6. Use `$setUnion`, `$setIntersection`, and `$setDifference` to compare `currentLabels` with `desiredLabels`; distinguish “to add” vs. “to remove.”
7. Use `$setIsSubset` to check whether all `currentLabels` appear in `desiredLabels`. Explain why an empty array returns `true`.
8. Handle a shipment missing `packages`, one with `packages: []`, and one with `packages: "bad"`; choose fallback vs. error contract.
9. Port the pipeline to `MongoTemplate.aggregate(...)` or `@Aggregation`, and write a test including another tenant's document.
10. Measure pipeline cost when a shipment contains 50,000 elements and consider alternative schema/processing strategies if output grows too large.

### 18.1. Solution Guide: Filtering and Fee Calculation

Keep packages weighing at least 1000 grams:

```javascript
{
  $filter: {
    input: {
      $cond: [
        { $isArray: "$packages" },
        "$packages",
        []
      ]
    },
    as: "p",
    cond: { $gte: ["$$p.weightGram", 1000] }
  }
}
// PK-A and PK-C
```

Compute per-package fee with `$map`:

```javascript
{
  $map: {
    input: "$packages",
    as: "p",
    in: {
      code: "$$p.code",
      feeMinor: {
        $multiply: [
          { $divide: ["$$p.weightGram", 1000] },
          "$$p.feePerKgMinor"
        ]
      }
    }
  }
}
```

In the sample data, computed fees are **PK-A = 18,000**, **PK-B = 10,000**, **PK-C = 20,000**, totaling **48,000**. This is a simulated formula; apply `Decimal128` and rounding rules for real monetary requirements. If you normalize into `safePackages` in an earlier stage, reference `"$safePackages"` in both `$map` and `$reduce` so legacy records do not error.

### 18.2. Solution Guide: Label Sets

- Union of labels across all packages: `{fragile, cold, priority}`.
- `currentLabels` union `desiredLabels`: `{cold, priority, insured}`.
- Intersection of current and desired: `{priority}`.
- Current minus desired (to remove): `{cold}`.
- Desired minus current (to add): `{insured}`.

Element order in set results is not guaranteed. In tests, assert set membership or sort explicitly.

## 19. References

- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): pipelines and mapping in Spring Data.
- Spring Data MongoDB — [Aggregation API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/Aggregation.html): building stages via `MongoTemplate`.
- Spring Data MongoDB — [ArrayOperators API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/ArrayOperators.html): Spring Data builders for array expressions.
- MongoDB Manual — [`$filter`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/), [`$map`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/), [`$reduce`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/reduce/): syntax, variables, and array behavior.
- MongoDB Manual — [Set Expression Operators](https://www.mongodb.com/docs/manual/reference/operator/aggregation/set/): union, intersection, difference, equality, subset.
- MongoDB Manual — [`$isArray`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/isArray/), [`$cond`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/cond/): type checking and fallback selection.
- MongoDB Manual — [`$unwind`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/): flattening array elements into documents.
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): execution plans and stage ordering.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): query statistics and performance diagnostics.

## Key Takeaways

**`$filter` keeps matching elements; `$map` transforms each element; `$reduce` folds into a single value; set operators unite/intersect/subtract/compare arrays with set semantics, deduplicating without ordering guarantees.** On real MongoDB documents, always distinguish `[]`, `null`, missing fields, wrong BSON types, and nested arrays. When implementing in Spring Data MongoDB, preserve stage order, check `$$this`/`$$value` scoping, map outputs to DTOs, enforce tenant boundaries, test against real BSON, and measure performance before deploying to production.
