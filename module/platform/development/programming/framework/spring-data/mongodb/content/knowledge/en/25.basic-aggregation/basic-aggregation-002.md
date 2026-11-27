# Pipeline, Stage, Expression, and Document Flow Across Steps

> **Chapter:** Basic Aggregation  
> **Module:** `SPRING_DATA_MONGODB`

An **aggregation pipeline** is how MongoDB processes data through a sequence of steps (*stages*). Each step receives documents from the previous step, applies a filter, transformation, grouping, or sort, and passes **intermediate results** to the next step. This model is very different from calling a `find` query that merely filters and returns whole documents: in a pipeline, **document shapes can change at every stage**.

In Spring Data MongoDB, you can write pipelines in MongoDB's aggregation language and express stages using the **Aggregation API** with `MongoTemplate`, or use `@Aggregation` on a repository when appropriate. To use those APIs accurately, you need to understand three conceptual layers: **pipeline** (the entire processing flow), **stage** (one operation on the stream), and **expression** (a computation inside a stage).

This lesson belongs to the `SPRING_DATA_MONGODB` module: connecting, mapping documents, and interacting with MongoDB via `MongoTemplate` or repositories; practicing query design, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics. The focus of this lesson is **tracing document flow step by step** before moving on to advanced aggregation patterns.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe a pipeline as a sequence of stages and distinguish stages from expressions used inside them.
2. Track document **count** and **structure** after `$match`, `$project`, `$set`/`$addFields`, `$group`, `$sort`, and `$limit`.
3. Understand how to reference fields with `"$fieldName"`, transform values with `$multiply`, `$cond`, `$ifNull`, and how accumulators such as `$sum` work inside `$group`.
4. Translate a MongoDB pipeline from `mongosh` to Java using `Aggregation`, `Criteria`, and `MongoTemplate.aggregate(...)`.
5. Distinguish source document schemas from result document schemas; explain the meaning of `_id` after grouping.
6. Test intermediate data, handle missing/null fields, enforce tenant scope, and inspect indexes and `explain`.

## 2. Pipeline, Stage, and Expression: Three Concepts Not to Mix Up

A pipeline is an **array of stages**, executed in declared order:

```javascript
db.collection.aggregate([
  { $match: { status: "PAID" } },
  { $project: { status: 1, amount: 1 } },
  { $group: { _id: "$status", total: { $sum: "$amount" } } }
])
```

At the top level of each pipeline element is **a stage** such as `$match`, `$project`, or `$group`. Inside a stage there may be **expressions**:

```javascript
{
  $project: {
    grossMinor: { $multiply: ["$unitPriceMinor", "$quantity"] }
  }
}
```

In this snippet:

- `$project` is the **stage** that decides which fields appear in the output document and their values.
- `$multiply` is an **expression** computing a value from two operands.
- `"$unitPriceMinor"` and `"$quantity"` are **field value references** in the current document.
- `"grossMinor"` is the **output field name**. Writing `grossMinor: ...` does not mean MongoDB is looking up a source field of the same name.

### 2.1. Document Flow Diagram

```text
Collection: sales_lines
       |
       | N documents, all original fields
       v
[$match]   Filter tenant and status
       |
       | Only matching documents; schema virtually unchanged
       v
[$project] Keep status, compute grossMinor = unitPriceMinor × quantity
       |
       | Same document count, new schema
       v
[$group]   Group documents by status, compute count and total
       |
       | Each group becomes one aggregated document
       v
[$sort]    Sort the aggregated documents
       |
       | Document count unchanged, order changed
       v
[$limit]   Take at most the first K documents
       |
       v
Result: report documents, NOT source entities
```

**Key rule:** a later stage may only use fields that still exist in **the output of the preceding stage**. If `$project` removed `unitPriceMinor`, a subsequent stage cannot recompute using `"$unitPriceMinor"` as if the original field were still present.

### 2.2. Classification Table

| Component | Position | Role | Example |
| --- | --- | --- | --- |
| Pipeline | Array of stages | Defines end-to-end processing flow | `[{$match:...}, {$group:...}]` |
| Stage | Element in pipeline | Filter, transform, expand, group, or output data | `$match`, `$project`, `$group` |
| Expression | Inside a stage | Compute values, evaluate logic, reference fields | `$multiply`, `$cond`, `$ifNull` |
| Accumulator | In contexts like `$group` | Combine multiple values into a group result | `$sum`, `$avg`, `$max` |
| Group key | `_id` inside `$group` | Determines which documents share a group | `_id: "$status"` |
| Output document | Result of the final stage | Data returned to the application | `{_id:"PAID", totalMinor:105000}` |

Not every operator prefixed with `$` is a stage. For instance, `$multiply` and `$cond` are placed inside expressions; `$sum` has context-dependent uses; `$sort` is a stage. Always read the **syntactic position** of an operator.

## 3. Running Dataset: Sold Sales Lines

A store needs a report of **gross revenue by line status**. The `sales_lines` collection stores **one document per line item**, not a complete order. Therefore, `count` in the examples below is the **number of line items**, not unique orders.

File `SalesLine.java`:

```java
package com.example.shop.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "sales_lines")
public record SalesLine(
    @Id String id,
    String tenantId,
    String status,
    String channel,
    long unitPriceMinor,
    int quantity
) {}
```

`unitPriceMinor` is the amount in the system's standardized smallest integer currency unit (e.g., Vietnamese dong), `quantity` is the count, and `grossMinor = unitPriceMinor * quantity` is the gross amount. This lesson does not compute taxes, refunds, promotions, or exchange rates; if the business needs **recognized revenue**, you must define the exact sources and adjustments rather than simply multiplying price by quantity.

### 3.1. Sample Data via `mongosh`

**Run only on a MongoDB instance dedicated to practice/testing:**

```javascript
use shop

db.sales_lines.insertMany([
  { _id: "A-01", tenantId: "TENANT-A", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(12000), quantity: 2 },
  { _id: "A-02", tenantId: "TENANT-A", status: "PAID",
    channel: "store", unitPriceMinor: NumberLong(55000), quantity: 1 },
  { _id: "A-03", tenantId: "TENANT-A", status: "NEW",
    channel: "web",   unitPriceMinor: NumberLong(5000),  quantity: 3 },
  { _id: "A-04", tenantId: "TENANT-A", status: "CANCELLED",
    channel: "store", unitPriceMinor: NumberLong(30000), quantity: 1 },
  { _id: "A-05", tenantId: "TENANT-A", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(8000),  quantity: 2 },
  { _id: "A-06", tenantId: "TENANT-A", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(2000),  quantity: 5 },
  { _id: "A-07", tenantId: "TENANT-A", status: "NEW",
    channel: "store", unitPriceMinor: NumberLong(20000), quantity: 1 },
  { _id: "B-01", tenantId: "TENANT-B", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(10000), quantity: 4 }
])
```

### 3.2. Expected Values Table

| ID | Tenant | Status | Channel | Unit Price | Qty | Line Value |
| --- | --- | --- | --- | ---: | ---: | ---: |
| A-01 | A | PAID | web | 12,000 | 2 | 24,000 |
| A-02 | A | PAID | store | 55,000 | 1 | 55,000 |
| A-03 | A | NEW | web | 5,000 | 3 | 15,000 |
| A-04 | A | CANCELLED | store | 30,000 | 1 | 30,000 |
| A-05 | A | PAID | web | 8,000 | 2 | 16,000 |
| A-06 | A | PAID | web | 2,000 | 5 | 10,000 |
| A-07 | A | NEW | store | 20,000 | 1 | 20,000 |
| B-01 | B | PAID | web | 10,000 | 4 | 40,000 |

Report goals:

- Read only **TENANT-A** data; do not include B-01's revenue.
- Consider only `PAID` and `NEW`; exclude `CANCELLED`.
- Compute each line's value, then count and sum by status.
- Return results ordered from largest total to smallest.

Expected outcome: **PAID = 4 lines, total 105,000**; **NEW = 2 lines, total 35,000**.

## 4. Complete Pipeline in MongoDB

Writing the pipeline at the MongoDB layer first helps us see the **target semantics** before moving to Java:

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      _id: 0,
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  {
    $group: {
      _id: "$status",
      lineCount: { $sum: 1 },
      totalMinor: { $sum: "$grossMinor" }
    }
  },
  {
    $sort: {
      totalMinor: -1,
      _id: 1
    }
  },
  { $limit: 2 }
])
```

Output:

```javascript
[
  { _id: "PAID", lineCount: 4, totalMinor: NumberLong(105000) },
  { _id: "NEW",  lineCount: 2, totalMinor: NumberLong(35000) }
]
```

Numeric values in `mongosh` output may appear as different BSON numeric types depending on input types and type-promotion rules; the output above uses `NumberLong` to emphasize monetary amounts stored as long integers. The essential contract is **value, precision, and numeric handling**, not identical string formatting across every shell/driver.

### 4.1. Data Flow After Each Stage

| Step | Stage | Document Count | Document Shape After Step | Key Takeaway |
| --- | --- | ---: | --- | --- |
| Source | Collection `sales_lines` | 8 | `_id, tenantId, status, channel, unitPriceMinor, quantity` | Original line items |
| 1 | `$match` | 6 | Original fields of 6 tenant A lines, PAID/NEW | **Filter**; does not compute gross |
| 2 | `$project` | 6 | `status, grossMinor` | **Schema change**; drops `tenantId`, `channel`, `quantity` |
| 3 | `$group` | 2 | `_id, lineCount, totalMinor` | **Collapses** 6 lines into 2 groups |
| 4 | `$sort` | 2 | Fields unchanged | **Reorders** groups |
| 5 | `$limit` | 2 | Fields unchanged | Keeps at most the top 2 groups |

The `$limit: 2` in the example does not drop any group because there are exactly two statuses. Changing it to `$limit: 1` returns only the `PAID` group. This makes it easy to observe that `$limit` applies **to the stream at that exact position**, not necessarily to the source documents.

## 5. Examining Each Stage Closely

### 5.1. Step 1 — `$match`: Which Documents Proceed?

`$match` uses MongoDB filter syntax similar to `find`:

```javascript
{
  $match: {
    tenantId: "TENANT-A",
    status: { $in: ["PAID", "NEW"] }
  }
}
```

Conditions at the same level are combined with **AND**. Thus:

- `tenantId` must be `TENANT-A`;
- `status` must be in `PAID` or `NEW`.

After `$match`, the six remaining documents are **A-01, A-02, A-03, A-05, A-06, A-07**. A-04 is excluded for `CANCELLED`; B-01 is excluded for belonging to another tenant. The surviving documents retain all original fields because `$match` does not reshape the schema.

You can run just the prefix to verify:

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  }
])
```

**Tenant scope is a security invariant**: never put `tenantId` inside just one branch of an `$or` while letting another branch freely read another tenant's data. In real applications, the tenant must come from or be verified against the authorization context—never trust a raw string sent by the client.

### 5.2. Step 2 — `$project`: What Does Each Document Become?

```javascript
{
  $project: {
    _id: 0,
    status: 1,
    grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
    }
  }
}
```

`status: 1` retains the `status` field; `_id: 0` removes the identifier field from **the intermediate result**; `grossMinor` is created from the calculation expression.

Stream after step 2:

| Source Document | Output `status` | Output `grossMinor` | Calculation |
| --- | --- | ---: | --- |
| A-01 | PAID | 24,000 | 12,000 × 2 |
| A-02 | PAID | 55,000 | 55,000 × 1 |
| A-03 | NEW | 15,000 | 5,000 × 3 |
| A-05 | PAID | 16,000 | 8,000 × 2 |
| A-06 | PAID | 10,000 | 2,000 × 5 |
| A-07 | NEW | 20,000 | 20,000 × 1 |

Example output document:

```javascript
{
  status: "PAID",
  grossMinor: NumberLong(24000)
}
```

At this point, each document **no longer has** `tenantId`, `channel`, `unitPriceMinor`, or `quantity`. Later stages must rely on `status` and `grossMinor`, or the earlier projection must be updated if more fields are needed.

#### Why `_id: 0`?

`$project` preserves `_id` by default unless excluded. In a status-grouped report, the source line item's `_id` is unnecessary after `$project`, because `$group` will create **a new `_id` for the group**. Excluding `_id` in the projection step does not delete the original document ID in the collection.

**Projection rule:** in general, do not mix *include* and *exclude* for regular fields within the same `$project`; the standard exception is excluding `_id` while including other fields. Computed expressions count as inclusions and must be tested against the input schema.

### 5.3. Step 3 — `$group`: Multiple Documents into One Group

```javascript
{
  $group: {
    _id: "$status",
    lineCount: { $sum: 1 },
    totalMinor: { $sum: "$grossMinor" }
  }
}
```

`_id: "$status"` is the **group key**. Every line with the same status enters the same group. `$sum: 1` increments the counter by 1 for each document entering the group; `$sum: "$grossMinor"` sums the value computed in the projection step for each document.

Group contents:

```text
PAID:
  A-01  24.000
  A-02  55.000
  A-05  16.000
  A-06  10.000
  -----------------
  lineCount       4
  totalMinor 105.000

NEW:
  A-03  15.000
  A-07  20.000
  -----------------
  lineCount       2
  totalMinor  35.000
```

Output document from `$group`:

```javascript
{
  _id: "PAID",
  lineCount: 4,
  totalMinor: NumberLong(105000)
}
```

**At this point `_id` is no longer the line item ID.** It is the **group key**. The individual line fields `status` and `grossMinor` no longer exist directly on the result document unless recreated via accumulators or projection.

If you need to rename `_id` to a friendlier name at the end:

```javascript
{
  $project: {
    _id: 0,
    status: "$_id",
    lineCount: 1,
    totalMinor: 1
  }
}
```

This stage must be placed **after `$group`**, because it references the group's new `_id`.

### 5.4. Step 4 — `$sort`: Ordering Current Documents

```javascript
{ $sort: { totalMinor: -1, _id: 1 } }
```

`-1` is descending, `1` is ascending. Here we are sorting **two aggregated documents**, not the six initial line items. `_id` acts as a secondary key so ordering is deterministic when two groups have equal totals.

**Do not assume `$group` output has a stable order.** If Java/API consumers expect a specific order, add `$sort`. Putting `$sort` **before** `$group` generally does not guarantee the output order of the groups.

### 5.5. Step 5 — `$limit`: Capping at the Exact Position Placed

```javascript
{ $limit: 2 }
```

`$limit` keeps at most two documents **after** grouping and sorting. Because there are exactly two groups, the result is unchanged. If you want to report only the single highest-total status, change it to `$limit: 1`.

Do not arbitrarily push `$limit` before `$group`:

```javascript
// COUNTEREXAMPLE: this is not how to calculate the total of ALL lines.
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A", status: "PAID" } },
  { $limit: 2 },
  { $group: {
      _id: "$status",
      totalMinor: {
        $sum: { $multiply: ["$unitPriceMinor", "$quantity"] }
      }
  }}
])
```

The pipeline above sums only **any two initial documents** in the filtered stream, rather than all four PAID lines. Without `$sort`, you cannot even assume the two documents picked are A-01/A-02 across runs. Even with a deterministic sort, the result is still the sum of the **first two lines**, not total revenue.

## 6. How Do `$addFields` / `$set`, `$project`, and `$unset` Differ?

These stages can all reshape schemas, but they have distinct semantics:

| Stage | Purpose | Unmentioned Source Fields |
| --- | --- | --- |
| `$project` | Select/rename/compute fields in the output | Typically **dropped** when using inclusion projection |
| `$addFields` | Add new fields or overwrite existing fields | **Preserved** |
| `$set` (aggregation stage) | Alias for `$addFields` | **Preserved** |
| `$unset` (aggregation stage) | Remove fields from the current stream | Other fields are preserved |

### 6.1. Adding Computed Fields While Preserving Source Data

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $addFields: {
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  }
])
```

For A-01, the output contains `_id`, `tenantId`, `status`, `channel`, `unitPriceMinor`, `quantity` **plus `grossMinor: 24000`**. This is a good choice if subsequent stages still need many original fields.

Equivalently:

```javascript
{
  $set: {
    grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
    }
  }
}
```

**Warning:** `$set` is an aggregation pipeline stage in this example; `$set` is also an **update operator** inside data modification commands. The two contexts have similar syntax but different purposes. A read-only aggregation pipeline with `$set` **does not write back** to the collection.

### 6.2. Removing Fields from Intermediate Results

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $unset: ["channel", "quantity"] }
])
```

The remaining documents no longer contain `channel`/`quantity`, yet the source fields in the database **are not deleted at all**. `$unset` transforms the aggregation stream. If a later stage needs `quantity`, adjust stage order or avoid unsetting too early.

## 7. Expressions Are Computations Inside a Stage

Expressions can use values from the current document, constants, arithmetic, comparison, string, date, or conditional operators. An expression **does not become a standalone stage on its own**.

### 7.1. Field References and Constants

```javascript
{
  $project: {
    unitPrice: "$unitPriceMinor",
    quantity: 1,
    fixedFee: { $literal: 1000 },
    grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
    }
  }
}
```

`"$unitPriceMinor"` reads the source field. `$literal` explicitly represents a constant value. In expressions, a string starting with `$` is usually interpreted as a field path or variable, so if you actually want to output a string starting with `$`, `$literal` may be required.

### 7.2. `$cond`: Choosing a Value Conditionally

Label lines with large quantities (3 or more):

```javascript
{
  $project: {
    _id: 1,
    quantity: 1,
    sizeLabel: {
      $cond: [
        { $gte: ["$quantity", 3] },
        "MULTI",
        "SINGLE"
      ]
    }
  }
}
```

Lines A-03 (quantity 3) and A-06 (quantity 5) get `MULTI`; A-01 (quantity 2) gets `SINGLE`. This expression computes **a new field value**; it does not filter documents. To drop low-quantity lines, add an appropriate `$match`.

### 7.3. `$ifNull`: Assigning a Fallback Value

A legacy document missing `channel`:

```javascript
{
  $project: {
    _id: 1,
    channelLabel: {
      $ifNull: ["$channel", "unknown"]
    }
  }
}
```

`$ifNull` uses the fallback if the first expression evaluates to `null` or missing under MongoDB semantics. This **does not prove** that `unknown` has the same business meaning as a verified channel. In reporting, distinguish "no data recorded" from "identified as a specific channel type."

### 7.4. Accumulators and Expressions Are Not the Same

Inside `$group`:

```javascript
{
  $group: {
    _id: "$status",
    count: { $sum: 1 },
    totalMinor: {
      $sum: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  }
}
```

`$sum` in this position is an **accumulator** summing across **multiple documents in the same group**. The inner `$multiply` computes a value **for each document** before summing.

Notice you can place the multiplication **directly inside `$group`** as shown, without necessarily creating `grossMinor` via `$project` first. However, the separate `$project` pipeline at the start of this lesson is useful for learning and step-by-step debugging.

### 7.5. Safe Numeric Type Design

If `unitPriceMinor` is BSON Int64 and `quantity` is an integer, multiplication and addition must be checked to prevent overflow on large datasets. Do not mix Double with monetary values requiring exact decimal accuracy; if the business needs fractional amounts or multiple currencies, choose an appropriate numeric type (e.g., Decimal128 with explicit rounding rules) rather than assuming `double` is always safe.

For mistyped data such as `unitPriceMinor: "12000"`, `$multiply` may error rather than automatically parsing strings into numbers. Use schema validation, data migration, or conversion expressions like `$convert` with explicit `onError`/`onNull` policies.

## 8. How Does `$unwind` Change *Document Count*?

In our main pipeline, `$match` removes some documents, `$project` keeps the count constant, and `$group` collapses many documents into fewer documents. But some stages **increase document count**, such as `$unwind`.

Suppose we have different data:

```javascript
{
  _id: "ORDER-X",
  tenantId: "TENANT-A",
  tags: ["web", "priority", "campaign"],
  status: "PAID"
}
```

Pipeline:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $unwind: "$tags" },
  { $project: { _id: 1, status: 1, tag: "$tags" } }
])
```

One document `ORDER-X` becomes **three output documents** after `$unwind`:

```javascript
{ _id: "ORDER-X", status: "PAID", tag: "web" }
{ _id: "ORDER-X", status: "PAID", tag: "priority" }
{ _id: "ORDER-X", status: "PAID", tag: "campaign" }
```

These documents carry the same `_id` because they are **temporary records in the stream**, not three new inserts into the collection. If you group/count after unwind, an order with three tags contributes **three counts** instead of one; distinguish between "counting tags" and "counting orders."

### 8.1. Empty Arrays or Missing Fields

By default, `$unwind` drops a document if the array path is null, missing, or an empty array. To retain those documents in the stream, configure:

```javascript
{
  $unwind: {
    path: "$tags",
    preserveNullAndEmptyArrays: true
  }
}
```

When enabled, documents missing/without elements are retained with an appropriate representation of the field. **Do not assume retaining them means they have an actual tag.** When grouping by tag, apply a distinct policy for null/missing.

### 8.2. `$lookup` Does Not Multiply Top-Level Document Count by Itself

A typical `$lookup` adds **an array of joined matches** to each source document. It does not inherently increase the top-level document count. When `$lookup` is combined with `$unwind` on the joined array, a source document can expand into multiple rows. This is why analyzing the **cardinality** of each stage is essential for multi-collection reports.

## 9. `$group` by a Single Key or Multiple Keys

### 9.1. Grouping by Status

```javascript
{
  $group: {
    _id: "$status",
    lineCount: { $sum: 1 }
  }
}
```

After the main pipeline's `$match`, this yields two group documents: `PAID` and `NEW`.

### 9.2. Grouping by `(status, channel)` Pair

If you want to split by **status and sales channel**, group by an object:

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      lineCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.status": 1, "_id.channel": 1 } }
])
```

Result:

```javascript
[
  { _id: { status: "NEW",  channel: "store" }, lineCount: 1 },
  { _id: { status: "NEW",  channel: "web"   }, lineCount: 1 },
  { _id: { status: "PAID", channel: "store" }, lineCount: 1 },
  { _id: { status: "PAID", channel: "web"   }, lineCount: 3 }
]
```

**Key difference:** `_id` in the aggregated document is now a **two-key object**, not a string. A Java DTO declaring only `String id` will not suit this result without proper mapping/conversion.

Do not run `$project` removing `channel` first and then try to group by channel. Once the field disappears from the stream, the group key can no longer distinguish channels as intended.

### 9.3. Grouping All Documents into One Group

If you need a single grand total within the filtered scope:

```javascript
{
  $group: {
    _id: null,
    lineCount: { $sum: 1 },
    totalMinor: {
      $sum: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  }
}
```

With the six tenant A lines in status PAID/NEW, the grand total is `140,000` and `lineCount = 6`. Omitting `tenantId` from the group key can make sense **if tenant scope was already strictly enforced earlier**. If you forget the tenant `$match`, the total mixes data across tenants, corrupting the report and risking data leaks.

### 9.4. Counting Documents vs. Counting Orders

Because `sales_lines` stores one document per line item:

```javascript
lineCount: { $sum: 1 }
```

counts **lines**, not orders. An order containing three lines contributes three to the count. To count **unique orders**, the data must carry a key like `orderId` and the pipeline must group/count distinct values by that key. Never name an accumulator `orderCount` when it actually counts line items.

## 10. Stage Order Affects Both Semantics and Cost

Two pipelines are not equivalent simply because they contain the same stage names.

### 10.1. Early `$match` When Conditions Rely on Source Fields

Usually filter tenant and status **before** multiplying and grouping:

```javascript
[
  { $match: { tenantId: "TENANT-A", status: "PAID" } },
  { $project: { grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
  } } },
  { $group: { _id: null, total: { $sum: "$grossMinor" } } }
]
```

Fewer documents enter the computation stages. The leading `$match` also has an opportunity to leverage an appropriate index on the source collection.

### 10.2. Filtering on a Computed Field Must Come After It Appears

To retrieve lines with `grossMinor >= 20,000`:

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $set: {
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
  }},
  { $match: { grossMinor: { $gte: NumberLong(20000) } } }
])
```

Moving the `grossMinor` condition **before** `$set` on the sample dataset (which does not store this field) matches zero rows. MongoDB's query optimizer can reorder certain stages when predicates are independent, but the application must still design **field-dependent semantics** properly.

### 10.3. `$limit` and `$skip` in Different Positions

```javascript
// A: take at most 2 LINES before grouping.
[
  { $match: { tenantId: "TENANT-A" } },
  { $limit: 2 },
  { $group: { _id: "$status", lines: { $sum: 1 } } }
]

// B: group ALL lines before taking 2 GROUPS.
[
  { $match: { tenantId: "TENANT-A" } },
  { $group: { _id: "$status", lines: { $sum: 1 } } },
  { $sort: { lines: -1, _id: 1 } },
  { $limit: 2 }
]
```

Pipeline A computes on a **two-line sample**; pipeline B computes groups over **all of tenant A**, then keeps two groups. When paginating grouped output, you typically group first, sort deterministically, and then apply `$skip`/`$limit` per the report contract. Deep offsets over many groups remain costly; evaluate paging requirements carefully.

### 10.4. `$sort` Before and After `$group` Serve Different Purposes

- `$sort` **before `$group`** affects the order in which documents enter accumulation. For order-sensitive accumulators such as `$first`, input ordering matters.
- `$sort` **after `$group`** orders the **aggregated documents** the API will receive.

If you need the status with the highest revenue, you must sort by `totalMinor` **after `totalMinor` is computed**; you cannot sort by an aggregated field before it exists.

## 11. Expressing Pipelines with the Spring Data MongoDB Aggregation API

In Java, `Aggregation` is a container of `AggregationOperation` instances. `MongoTemplate.aggregate(...)` sends the pipeline to MongoDB and maps results to `Document` or a DTO. We keep the same data model and expectations as `mongosh` for direct comparison.

Common imports:

```java
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
```

### 11.1. Complete Service Example

File `SalesAnalyticsService.java`:

```java
package com.example.shop.sales;

import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class SalesAnalyticsService {

    private final MongoTemplate template;

    public SalesAnalyticsService(MongoTemplate template) {
        this.template = template;
    }

    public record RevenueByStatus(
        String status, long lineCount, long totalMinor) {}

    public List<RevenueByStatus> summarizeTenant(
            String permittedTenantId) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid tenant");
        }

        Aggregation pipeline = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is(permittedTenantId)
                    .and("status").in("PAID", "NEW")
            ),
            Aggregation.project("status")
                .andExpression("unitPriceMinor * quantity")
                .as("grossMinor")
                .andExclude("_id"),
            Aggregation.group("status")
                .count().as("lineCount")
                .sum("grossMinor").as("totalMinor"),
            Aggregation.sort(
                Sort.by(
                    Sort.Order.desc("totalMinor"),
                    Sort.Order.asc("_id")
                )
            ),
            Aggregation.limit(2)
        );

        AggregationResults<Document> aggregated =
            template.aggregate(
                pipeline, "sales_lines", Document.class);

        return aggregated.getMappedResults().stream()
            .map(doc -> new RevenueByStatus(
                doc.getString("_id"),
                ((Number) doc.get("lineCount")).longValue(),
                ((Number) doc.get("totalMinor")).longValue()
            ))
            .toList();
    }
}
```

**Flow between Java and MongoDB:**

1. `Aggregation.match(...)` expresses `$match` restricting tenant/status.
2. `Aggregation.project("status").andExpression("unitPriceMinor * quantity")` uses Spring Data's SpEL-style arithmetic expression to produce `grossMinor` (equivalent in intent to `$multiply`).
3. `Aggregation.group("status").count().as(...).sum("grossMinor").as(...)` builds the accumulators inside `$group`.
4. `Aggregation.sort(...)` and `Aggregation.limit(2)` sort and limit the **grouped results**.
5. `template.aggregate(...)` executes; `AggregationResults<Document>` contains report documents, not source `SalesLine` entities.

Expected call:

```java
List<SalesAnalyticsService.RevenueByStatus> result =
    service.summarizeTenant("TENANT-A");

// result:
// RevenueByStatus("PAID", 4, 105000)
// RevenueByStatus("NEW",  2, 35000)
```

`service` is an injected `SalesAnalyticsService` instance. The tenant filter must be constructed from a tenant verified for access at the service/controller layer; never allow clients to freely supply another tenant and call this method directly.

### 11.2. Why Doesn't the Output Return `SalesLine`?

After `$group`, each document only has `_id` (holding the status value), `lineCount`, and `totalMinor`. It **no longer has** `tenantId`, `quantity`, `unitPriceMinor`, or line item IDs. Attempting to map the result into `SalesLine` leaves fields missing or populated with misleading defaults.

We have two options:

- **`Document`** to inspect raw BSON output structure, helpful while learning, debugging, or building complex pipelines.
- **DTO/read model** matching the report result, mapping `_id` explicitly or adding a `$project` stage to rename `_id` to `status` before mapping.

In the example above, the service receives `Document` and maps it into an explicit result record. Casting via `Number` avoids assuming `lineCount` is always `Integer` or `Long` in every case. In production, you can configure typed output directly once the schema and converters are aligned.

### 11.3. Remember Field Name Mapping

Suppose a Java entity uses:

```java
@Field("unit_price_minor")
private long unitPriceMinor;
```

The Spring Data Aggregation API can map Java properties to BSON fields via metadata when using typed aggregation / an input type. However, **raw pipelines in `mongosh`** must use the actual BSON field name `unit_price_minor`. When mixing raw JSON stages with typed DSL, inspect the final generated pipeline so you do not cross the two conventions.

The main example intentionally uses matching Java property and BSON field names. Whenever a project introduces `@Field` or custom converters, write integration tests to verify computations on actual BSON rather than relying only on reading Java code.

## 12. How to Debug Pipelines Using Intermediate Results

When a report returns wrong results, do not edit every stage at once. Run **prefix pipelines**: only the first stage; the first two stages; the first three stages; then add sort/limit.

### 12.1. Inspecting the Filter Stage

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  { $count: "matchedLines" }
])
// [{ matchedLines: 6 }]
```

`$count` here is a standalone stage that **counts documents reaching it**. It replaces the entire result stream with a single count document (or produces no document if the input is empty, per stage semantics). Never place `$count` in the middle of the main pipeline and expect source fields to remain available for a later `$project`.

### 12.2. Inspecting Computation Expressions

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

During debugging, **temporarily keep `_id`** to identify which row produced a wrong value. Once the multiplication is confirmed across all six lines, revert to the report projection that can exclude IDs to reduce intermediate data.

### 12.3. Inspecting `$group` Before `$sort`/`$limit`

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  {
    $group: {
      _id: "$status",
      lineCount: { $sum: 1 },
      totalMinor: { $sum: "$grossMinor" }
    }
  }
])
```

At this step there must be **two groups** with accurate totals, even if the return order varies. Only then add `$sort` and `$limit` to finalize presentation.

### 12.4. Checking Data Types and Null/Missing

If a total is 0 or lower than expected:

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      _id: 1,
      priceType: { $type: "$unitPriceMinor" },
      quantityType: { $type: "$quantity" },
      statusType: { $type: "$status" }
    }
  }
])
```

This reveals types such as `long`, `int`, `string`, `null`, and `missing` in real BSON. If a legacy writer stored prices as strings, do not rush to patch `$group`; normalize the data or explicitly define type conversion and error policies.

## 13. Integration Testing Against Real MongoDB

Mocking `MongoTemplate` or writing tests that only compare a JSON string **does not prove** the server executes `$multiply`/`$group` properly on real data. Spin up an isolated test database, insert real BSON, and verify both intermediate document counts and final output.

### 13.1. JUnit 5 and AssertJ Fixture

Example using Spring Boot `@DataMongoTest` (adjust package imports to match your project version). File `SalesAggregationIntegrationTest.java`:

```java
package com.example.shop.sales;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class SalesAggregationIntegrationTest {

    @Autowired
    MongoTemplate template;

    private static Document line(
            String id, String tenant, String status,
            String channel, long price, int quantity) {

        return new Document("_id", id)
            .append("tenantId", tenant)
            .append("status", status)
            .append("channel", channel)
            .append("unitPriceMinor", price)
            .append("quantity", quantity);
    }

    @BeforeEach
    void seed() {
        // Only use an isolated TEST MongoDB, never a shared database.
        var collection = template.getCollection("sales_lines");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            line("A-01", "TENANT-A", "PAID",      "web",   12000L, 2),
            line("A-02", "TENANT-A", "PAID",      "store", 55000L, 1),
            line("A-03", "TENANT-A", "NEW",       "web",    5000L, 3),
            line("A-04", "TENANT-A", "CANCELLED", "store", 30000L, 1),
            line("A-05", "TENANT-A", "PAID",      "web",    8000L, 2),
            line("A-06", "TENANT-A", "PAID",      "web",    2000L, 5),
            line("A-07", "TENANT-A", "NEW",       "store", 20000L, 1),
            line("B-01", "TENANT-B", "PAID",      "web",   10000L, 4)
        ));
    }

    @Test
    void matchKeepsSixAuthorizedLines() {
        Aggregation matchOnly = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is("TENANT-A")
                    .and("status").in("PAID", "NEW")
            )
        );

        List<Document> rows = template.aggregate(
            matchOnly, "sales_lines", Document.class
        ).getMappedResults();

        assertThat(rows).hasSize(6);
        assertThat(rows)
            .extracting(doc -> doc.getString("_id"))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-03", "A-05", "A-06", "A-07");
        assertThat(rows)
            .extracting(doc -> doc.getString("tenantId"))
            .containsOnly("TENANT-A");
    }

    @Test
    void projectProducesGrossAmountsBeforeGrouping() {
        Aggregation matchAndProject = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is("TENANT-A")
                    .and("status").in("PAID", "NEW")
            ),
            Aggregation.project("status")
                .andExpression("unitPriceMinor * quantity")
                .as("grossMinor")
                .andExclude("_id")
        );

        List<Document> rows = template.aggregate(
            matchAndProject, "sales_lines", Document.class
        ).getMappedResults();

        assertThat(rows).hasSize(6);
        assertThat(rows).allSatisfy(row -> {
            assertThat(row).containsKeys("status", "grossMinor");
            assertThat(row).doesNotContainKeys(
                "_id", "unitPriceMinor", "quantity", "tenantId");
        });

        long grandTotal = rows.stream()
            .mapToLong(row -> ((Number) row.get("grossMinor"))
                .longValue())
            .sum();

        assertThat(grandTotal).isEqualTo(140000L);
    }

    @Test
    void completePipelineGroupsAndSortsExactly() {
        var report = new SalesAnalyticsService(template)
            .summarizeTenant("TENANT-A");

        assertThat(report).containsExactly(
            new SalesAnalyticsService.RevenueByStatus(
                "PAID", 4L, 105000L),
            new SalesAnalyticsService.RevenueByStatus(
                "NEW", 2L, 35000L)
        );
    }

    @Test
    void otherTenantCannotChangeAuthorizedTotals() {
        var report = new SalesAnalyticsService(template)
            .summarizeTenant("TENANT-B");

        assertThat(report).containsExactly(
            new SalesAnalyticsService.RevenueByStatus(
                "PAID", 1L, 40000L)
        );
    }
}
```

**Warning:** `collection.deleteMany(new Document())` deletes all of `sales_lines` in whatever database the test connects to. Only run when certain an **isolated** test MongoDB (such as Testcontainers) is used. `@DataMongoTest` alone does not guarantee the server is a safe test database if environment configuration is miswired.

### 13.2. Why Test Stage by Stage?

- `matchKeepsSixAuthorizedLines` catches missing tenant filters or wrong status conditions.
- `projectProducesGrossAmountsBeforeGrouping` catches multiplication bugs or projections dropping needed fields.
- `completePipelineGroupsAndSortsExactly` catches wrong group keys, accumulators, and sorting.
- `otherTenantCannotChangeAuthorizedTotals` verifies data isolation; B-01 must never bleed into tenant A's report.

Do not just assert that the report has two rows. If one PAID line is dropped and another is double-counted, the group row count is still two. Assert **numeric values, source IDs, data types, and order when ordering is part of the API contract**.

### 13.3. Additional Testing Matrix

| Case | Expectation |
| --- | --- |
| No lines match `$match` | `$group` by status produces no fake group |
| Two statuses with equal total | `$sort` has a secondary key for deterministic order |
| Missing `unitPriceMinor` or `quantity` | Explicit validation/null rule, no silent miscalculation |
| Legacy String price | Do not assume `$multiply` auto-converts types |
| Wrong-tenant document with matching status | Never appears in current tenant's total |
| `$project` drops `channel` | Cannot group by channel afterward without retaining the field |
| `$unwind` on a three-element array | One document can generate three temporary documents |
| `$unwind` on empty/missing array | Verify effect of `preserveNullAndEmptyArrays` |
| `$limit` before group | Must reflect sampling intent, never used for full-dataset totals |
| Extremely large values | Verify numeric types and limits/overflow |

## 14. Returning Results via Repository `@Aggregation`

Besides `MongoTemplate`, Spring Data MongoDB supports `@Aggregation` on repository methods in supported versions. The annotation defines a **fixed array of JSON stages**. Compact example counting line items by status:

```java
package com.example.shop.sales;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SalesLineRepository
        extends MongoRepository<SalesLine, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': { '$in': ['PAID','NEW'] } } }",
        "{ '$group': { '_id': '$status', 'lineCount': { '$sum': 1 } } }",
        "{ '$sort': { 'lineCount': -1, '_id': 1 } }"
    })
    List<Document> countLinesByStatus(String tenantId);
}
```

The result here is PAID with 4 lines and NEW with 2 lines; it **does not** compute monetary totals because this annotation pipeline only illustrates `$match` → `$group` → `$sort`.

When choosing an approach:

- `@Aggregation` fits **static** pipelines kept next to the repository contract and easy to manage.
- `MongoTemplate`/Aggregation DSL fits dynamic stages, reusable expression blocks, branching configurations, and intermediate debugging.
- Both run **aggregation on MongoDB**; neither is inherently faster when the resulting BSON pipeline is equivalent.

Note on the annotation name: `org.springframework.data.mongodb.repository.Aggregation` is the **annotation**, while `org.springframework.data.mongodb.core.aggregation.Aggregation` is the **Java pipeline builder class**. If both are used in one file, manage imports or use fully qualified names to avoid confusion.

## 15. Performance: Which Stages Use Indexes and Which Must Compute?

Pipelines run on the MongoDB server and reduce data sent back to Java when summarizing groups. Yet **putting logic into a pipeline does not make it automatically fast**. Cost depends on the number of documents passing through each stage, `$match` selectivity, number of groups, fields processed, and execution plan.

### 15.1. Index for the Leading `$match`

For queries frequently filtering by tenant and status, a candidate index:

```javascript
db.sales_lines.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
)
```

This index can help `$match` reduce documents read when data is large and the filter is selective. It **does not turn a monetary `$group` sum into a pure index operation**; the server still has to sum matching lines depending on the plan.

If reports frequently filter by time, adding a time field / compound index tailored to actual query patterns makes sense. Do not create indexes based solely on stage names; measure with representative data and tenant distributions.

### 15.2. Reading Aggregation `explain`

```javascript
db.sales_lines.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  {
    $group: {
      _id: "$status",
      lineCount: { $sum: 1 },
      totalMinor: { $sum: "$grossMinor" }
    }
  },
  { $sort: { totalMinor: -1, _id: 1 } },
  { $limit: 2 }
])
```

When reading `explain` output, note:

- Collection scan / index usage stages and number of documents scanned.
- `totalKeysExamined`, `totalDocsExamined`, and `nReturned` where displayed by the plan.
- Whether sort/group stages consume substantial memory or spill to disk (visibility depends on server version).
- Number of documents entering computation versus final documents returned.

MongoDB's optimizer may push down certain `$match`/projection operations or merge stages when semantics allow. **The optimized execution pipeline may not match the exact order and structure originally declared.** Do not treat differences between explain and raw JSON as an automatic bug; verify both outputs and statistics.

### 15.3. `$group` and `$sort` Can Be Blocking Stages

`$group` generally must accumulate enough data to compute group results, and an unindexed `$sort` may have to sort many records. They can consume significant memory when:

- Input filters are too broad.
- Group keys have very high cardinality, producing millions of groups.
- Each group accumulates large arrays (e.g., unbounded `$push`).
- Sorting on a **newly computed** post-group field cannot directly leverage an existing source index order.

MongoDB enforces memory limits and supports disk spill options (`allowDiskUse`), depending on server version and settings. Enabling disk spill is a **memory management fallback**, not a way to make a query efficient; prioritize optimizing filters, schemas, indexes, and aggregation granularity first.

### 15.4. Do Not Push Entire Documents Into Groups Unnecessarily

If the goal is summing money, avoid:

```javascript
{
  $group: {
    _id: "$status",
    everyLine: { $push: "$$ROOT" }
  }
}
```

unless the business **truly** requires every individual document in the result. `$push: "$$ROOT"` can produce huge arrays, inflating RAM and network transfer. For summary reports, `$sum`, `$avg`, `$min`, `$max`, and suitable accumulators are much clearer and leaner.

## 16. Reading Large Results, Streaming, and Reactive Access

`AggregationResults<Document>.getMappedResults()` works well when report output is small, such as two groups. If a pipeline returns many documents, collecting them all into a Java `List` can bloat application memory.

### 16.1. `aggregateStream` with `MongoTemplate`

Spring Data MongoDB provides a streaming aggregation path in supported versions:

```java
import java.util.stream.Stream;
import org.bson.Document;

try (Stream<Document> stream = template.aggregateStream(
        pipeline, "sales_lines", Document.class)) {
    stream.forEach(doc -> {
        // Process each result document.
        System.out.println(doc.toJson());
    });
}
```

This snippet lives inside a method/class that already has `MongoTemplate template` and `Aggregation pipeline`. Close the stream with `try-with-resources` to release the cursor/resources; never leave it open across unbounded HTTP requests. Streaming **does not make `$group` compute over less data**; it mainly avoids buffering all results in Java memory.

### 16.2. `ReactiveMongoTemplate`

In reactive applications:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<Document> aggregateReactive(
        ReactiveMongoTemplate template,
        Aggregation pipeline) {

    return template.aggregate(
        pipeline, "sales_lines", Document.class);
}
```

`Flux<Document>` emits result documents when subscribed, while **`$match`/`$project`/`$group` semantics stay the same**. If the application processes large volumes of results, you still need backpressure, timeouts, memory/output caps, and policies to terminate/cancel the pipeline if the client disconnects.

**Do not mix blocking `MongoTemplate` into a reactive event loop** expecting it to become non-blocking. Choose the reactive driver/template and processing model consistently from the start.

### 16.3. Read Aggregation vs. Write Aggregation

The pipelines in this lesson only filter, transform, and return results. MongoDB also has specialized stages like `$out` and `$merge` that **write aggregation output to a collection**. Do not add those stages to read-only report pipelines unless explicitly intended:

| Pipeline Ends With | Meaning |
| --- | --- |
| `$project` / `$group` / `$sort` / `$limit` | Returns result documents; does not modify source collection |
| `$out` or `$merge` | Writes results to a collection; requires dedicated permissions, design, and testing |

Writing aggregated data to a physical collection turns the problem into a *materialized view* with update and consistency constraints, not merely a report formatting change.

## 17. Common Mistakes When Building Pipelines

| Symptom | Cause | Fix |
| --- | --- | --- |
| Tenant A report includes Tenant B revenue | `$match` missing tenant or wrong OR scoping | Put tenant inside mandatory AND and test with other tenant data |
| A stage after `$project` cannot find a field | Source field was dropped during projection | Keep needed fields or move the stage earlier |
| Group output lacks source entity's `status` | `$group` reshapes schema; key is in `_id` | Use a dedicated DTO or `$project` to rename `_id` |
| Counts lines instead of orders | Each source document is a line item | Name it `lineCount` or group distinct by `orderId` |
| Abnormally small total | `$limit` placed before `$group` or overly restrictive filter | Check cardinality after each stage |
| Totals double-counted | `$unwind` turned one document into multiple | Identify the right counting unit; re-group by ID earlier |
| Amounts wrong even though count is right | Mixed BSON String/Number/null; wrong formula | Inspect `$type`, validate, and migrate |
| `$sort` behaves unexpectedly | Sorting on dropped field or sorting before group | Sort on fields existing after the appropriate stage |
| Group results change order randomly | Missing `$sort` after `$group` | Add sort with a tie-breaker |
| Query is slow despite returning 2 groups | Group/sort processes massive row counts | Early `$match`, suitable indexes, check explain and selectivity |
| Null mapped into Java primitive | Output schema mismatches DTO/entity | Use a suitable read model; validate data and mapping |
| Added `$set` in aggregation but DB unchanged | `$set` here transforms stream results, not an update command | Use update APIs if writes are intended |
| Large report spikes Java heap | `getMappedResults()` loads many rows into a `List` | Limit/stream results and bound resources |
| Reading across collections returns no joined data | `$lookup`/`$unwind` not used properly | Design join/array cardinality pipeline separately |

## 18. Checklist for Designing a Correct Aggregation

1. **What is the data source?** Does each document represent an order, a line item, or an event? What counting unit does each document correspond to?
2. **What is the authorization scope?** `tenantId`/storeId must be verified and enforced in the pipeline.
3. **What is each stage's input schema?** List available fields, especially after `$project` and `$group`.
4. **How does this stage affect document count?** Keep unchanged, filter down, multiply via unwind, or collapse via group?
5. **Which fields do expressions use?** Do fields exist with valid BSON types? Is `$ifNull` or validation needed?
6. **Do accumulators match intent?** Is `$sum: 1` counting lines or unique business entities?
7. **Is stage order correct?** Filter source fields early, compute derived fields before using them, group before sorting by totals.
8. **What is the output schema?** Is `_id` a source ID or group key? Which Java DTO should receive it?
9. **Are limits or streaming needed?** Avoid returning unbounded report arrays to clients.
10. **Have pipeline prefixes and raw BSON been tested?** Do not mock only the final output.
11. **Are indexes in place and real plans measured?** Inspect `explain`, latency, memory, and skew on representative data.
12. **Does the pipeline have side effects?** For `$out`/`$merge`, define target write collection and permissions explicitly.

## 19. Applied Exercise

A delivery system stores a `deliveries` collection:

```javascript
{
  _id: "DEL-001",
  tenantId: "TENANT-X",
  state: "DELIVERED",
  zone: "HCM",
  feeMinor: NumberLong(20000),
  packageCount: 2,
  labels: ["fragile", "priority"]
}
```

Goal: summarize delivery fee revenue by `zone` within one tenant, counting only `state=DELIVERED`. The effective fee per document is defined in this exercise as `feeMinor * packageCount` (a simplified convention for practice; confirm against actual business rules).

Complete the following steps:

1. Write `$match` restricting tenant and state. Explain which data could be miscounted if tenant is omitted.
2. Write `$project` creating `grossFeeMinor` with `$multiply` and keeping `zone`.
3. Write `$group` by zone, computing `deliveryCount` and `totalFeeMinor`.
4. Sort total fee descending, add a tie-breaker for deterministic order, and limit to 5 zones.
5. Try placing `$limit: 5` **before** grouping and explain why the report semantics change.
6. Modify the pipeline to aggregate by `(zone + state)` pair; predict the shape of `_id` for each group.
7. Insert `$unwind: "$labels"` before grouping, then explain why `deliveryCount` can be artificially inflated when a delivery has multiple labels.
8. Translate the pipeline to Java using `Aggregation.newAggregation(...)` and `MongoTemplate.aggregate(...)`.
9. Write an integration test with documents from another tenant, matching zones, and a document missing `feeMinor`.
10. Propose an index for `$match`, use `explain("executionStats")`, and compare speed with and without the index on a sufficiently large dataset.

**Suggested pipeline solution:**

```javascript
db.deliveries.aggregate([
  {
    $match: {
      tenantId: "TENANT-X",
      state: "DELIVERED"
    }
  },
  {
    $project: {
      zone: 1,
      grossFeeMinor: {
        $multiply: ["$feeMinor", "$packageCount"]
      }
    }
  },
  {
    $group: {
      _id: "$zone",
      deliveryCount: { $sum: 1 },
      totalFeeMinor: { $sum: "$grossFeeMinor" }
    }
  },
  { $sort: { totalFeeMinor: -1, _id: 1 } },
  { $limit: 5 }
])
```

If `feeMinor` or `packageCount` is missing, decide explicitly: **exclude invalid documents**, **fail the check**, or apply a business-approved fallback rule. Never default missing values to 0 and present that as valid revenue.

## 20. References

- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): `Aggregation`, `AggregationOperation`, SpEL expressions, and aggregation results.
- Spring Data MongoDB — [Aggregation API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/Aggregation.html): builders `match`, `project`, `group`, `sort`, `limit`.
- Spring Data MongoDB — [Aggregation Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): `@Aggregation` annotation.
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): pipeline definition and document flow.
- MongoDB Manual — [Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/): stage catalog and output behavior.
- MongoDB Manual — [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/): expression, conditional, and arithmetic operators.
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): optimizations, filter pushdown, and stage handling.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): reading execution plans and statistics.

## Key Takeaways

A **pipeline** is a sequence of stages; a **stage** receives documents from the previous step and can filter, reshape, multiply, group, or sort them; an **expression** computes values on fields within a stage. In our example, 8 source documents → `$match` leaves 6 → `$project` computes `grossMinor` (still 6) → `$group` yields 2 groups → `$sort` and `$limit` determine order and output count. After `$group`, `_id` is the **group key**, no longer the source document ID. Writing sound pipelines starts with understanding **what each stage takes in and emits**, then translating to `Aggregation`/`MongoTemplate`, testing against real BSON, and tuning with `explain`.
