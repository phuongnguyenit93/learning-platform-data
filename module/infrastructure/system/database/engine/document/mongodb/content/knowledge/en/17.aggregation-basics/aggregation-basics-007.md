# The $sum, $avg, $min, $max, $push, and $addToSet Accumulators in MongoDB

## 1. What Questions Do Accumulators Answer?

In MongoDB, a document might represent an order, a visit, or a transaction. When you need to answer "how many orders does each customer have?", "what is the total revenue by status?", "what is the minimum/maximum value in the month?", or "what is the list of distinct product types that appeared?", fetching every document to the application to compute in memory is usually not the most efficient approach.

The **Aggregation Pipeline** lets you process data through a sequence of stages directly inside MongoDB. In stages such as **$group**, **accumulators** receive values from multiple documents and produce a single aggregated result.

Simple example:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" },
      averageAmount: { $avg: "$amount" }
    }
  }
]);
~~~

Each document entering **$group** is assigned to a group by status. Accumulators process the documents within each group:

| Accumulator | Common question | Typical result type |
| --- | --- | --- |
| **$sum** | Total amount/quantity; or document count | Number |
| **$avg** | Average value | Number or null |
| **$min** | Minimum value per BSON comparison rules | Minimum value or null |
| **$max** | Maximum value per BSON comparison rules | Maximum value or null |
| **$push** | Store values from each document into a list, allowing duplicates | Array |
| **$addToSet** | Collect distinct values within the group | Array of distinct elements, **no guaranteed order** |

**Important:** an accumulator is not always "a function applied to the entire collection." The result depends on **$group._id**, preceding filter stages, input BSON types, and the order documents enter the stage.

### 1.1. From Individual Documents to Aggregated Documents

Suppose we have:

~~~javascript
{ orderNo: "SO-001", status: "paid", amount: NumberDecimal("100.00") }
{ orderNo: "SO-002", status: "paid", amount: NumberDecimal("250.00") }
{ orderNo: "SO-003", status: "pending", amount: NumberDecimal("80.00") }
~~~

After grouping by status:

~~~text
Input documents
   SO-001 -> paid     amount 100
   SO-002 -> paid     amount 250
   SO-003 -> pending  amount  80
          |
          v
      $group by status
          |
          +-- paid:    count=2, sum=350, avg=175
          |
          +-- pending: count=1, sum= 80, avg= 80
~~~

There is no default reason to compute totals across **all** statuses if the user only needs paid order counts. A proper **$match** placed before $group both expresses business logic accurately and reduces the documents to aggregate.

## 2. Structure of $group and General Syntax

### 2.1. The _id Field in $group Is the Grouping Key

~~~javascript
{
  $group: {
    _id: <grouping-expression>,
    outputField1: { $sum: <expression> },
    outputField2: { $avg: <expression> }
  }
}
~~~

In this syntax:

- **_id: "$status"** creates one group for each status value.
- **_id: { tenantId: "$tenantId", status: "$status" }** creates groups by tenant–status pairs.
- **_id: null** puts all documents entering $group into **a single group**.
- Every output field other than _id contains an accumulator and an input expression.
- **$group does not guarantee the order of output group documents**. To display them in order, add **$sort after $group**.

Example grouping across two dimensions:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenant: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { "_id.tenant": 1, "_id.status": 1 } }
]);
~~~

### 2.2. Different Meanings of the $ Prefix

Read these three examples carefully:

~~~javascript
{ $sum: 1 }          // Each document contributes the number 1.
{ $sum: "$amount" }  // Each document contributes the value of the amount field.
{ $push: "$status" } // Each document contributes a status value to an Array.
~~~

**The number 1** is a literal. **"$amount"** is a field path on the input document. Omitting $ changes the meaning: **{ $sum: "amount" }** uses a literal string rather than a field value; for $sum inside $group, a string is non-numeric and contributes nothing to the total.

### 2.3. Accumulators in $group vs. Expressions in Other Stages

The names **$sum, $avg, $min, $max** also exist in **aggregation expression** form inside stages such as **$project** or **$set**. When used on **a single document**, they evaluate expressions on that document rather than aggregating across multiple documents as in $group. In particular, how they treat Arrays can differ by context.

Conversely, **$push** and **$addToSet** accumulate values across multiple documents in accumulator-supporting stages such as **$group** and **$setWindowFields**, rather than acting as general-purpose functions inside $project.

This lesson uses **$group** as the primary context, then explains notable exceptions when moving to other stages.

## 3. A Re-Runnable Practice Dataset

We simulate an order system with two tenants, multiple customers, statuses, and amounts. The goal is to clarify **$sum/$avg** for numbers, **$min/$max** for extremes, and **$push/$addToSet** for lists.

Database: **mongo_accumulators_lab**.

Collection: **lab_orders_agg**.

Dataset label: **accumulators-v1**.

### 3.1. Seeding 12 Orders via mongosh

Run as one block:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_accumulators_lab");
  const orders = lab.getCollection("lab_orders_agg");
  const tag = "accumulators-v1";

  // Clean up only this lesson's data. Do not drop the collection or database.
  orders.deleteMany({ dataset: tag });

  // Each row: id, tenant, customer, status, amount, units, coupon, tags.
  // undefined indicates the document does NOT have a coupon field.
  const rows = [
    ["agg-o001", "t001", "c01", "paid",     "100.00", 2, null,       ["new", "web"]],
    ["agg-o002", "t001", "c01", "paid",     "250.00", 3, "SAVE10",   ["sale", "app"]],
    ["agg-o003", "t001", "c02", "pending",   "80.00", 1, undefined,  ["web"]],
    ["agg-o004", "t001", "c02", "paid",     "120.00", 2, null,       ["web"]],
    ["agg-o005", "t001", "c03", "refunded",  "60.00", 1, "SAVE10",   ["sale", "app"]],
    ["agg-o006", "t001", "c01", "paid",     "130.00", 2, "SAVE20",   ["web", "vip"]],
    ["agg-o007", "t001", "c03", "paid",      "90.00", 1, "SAVE10",   ["web", "sale"]],
    ["agg-o008", "t001", "c03", "pending",   "40.00", 1, "",         ["app"]],
    ["agg-o009", "t002", "c04", "paid",     "200.00", 4, null,       ["web"]],
    ["agg-o010", "t002", "c04", "paid",     "150.00", 3, "SAVE10",   ["app", "sale"]],
    ["agg-o011", "t002", "c05", "pending",   "75.00", 1, undefined,  ["web"]],
    ["agg-o012", "t002", "c05", "paid",      "50.00", 1, null,       ["web", "new"]]
  ];

  const documents = rows.map((r, i) => {
    const [id, tenantId, customerId, status,
           amount, units, coupon, tags] = r;

    const doc = {
      _id: id,
      dataset: tag,
      tenantId: tenantId,
      customerId: customerId,
      status: status,
      amount: NumberDecimal(amount),
      units: NumberInt(units),
      tags: tags,
      createdAt: new Date(Date.UTC(2026, 0, 1, 0, i + 1, 0))
    };

    if (coupon !== undefined) {
      doc.coupon = coupon;
    }
    return doc;
  });

  orders.insertMany(documents);

  // Supports tenant filtering and ordered traversal examples.
  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: 1, _id: 1 },
    { name: "ix_acc_lab_tenant_time" }
  );

  orders.createIndex(
    { dataset: 1, tenantId: 1, status: 1 },
    { name: "ix_acc_lab_tenant_status" }
  );

  printjson({
    total: orders.countDocuments({ dataset: tag }),
    tenant001: orders.countDocuments({
      dataset: tag,
      tenantId: "t001"
    }),
    tenant002: orders.countDocuments({
      dataset: tag,
      tenantId: "t002"
    })
  });
})();
~~~

**Expected result:** **12 orders** total, tenant t001 has **8**, tenant t002 has **4**. Every amount has BSON type **Decimal128**, and units is Int32.

The script uses fixed _id values and deletes only by the dataset tag. If you alter data in an exercise, re-run this script to restore the baseline dataset. The delete-and-insert sequence is not an atomic transaction, so use it only on a practice database.

### 3.2. Quick Overview of Groups in the Data

| Tenant | Status | Order count | Total amount |
| --- | --- | ---: | ---: |
| t001 | paid | 5 | 690.00 |
| t001 | pending | 2 | 120.00 |
| t001 | refunded | 1 | 60.00 |
| t002 | paid | 3 | 400.00 |
| t002 | pending | 1 | 75.00 |
| **Total** | | **12** | **1345.00** |

Numbers in the table come from summing the fixed dataset to explain expected results. In real systems, explicitly define **which orders count toward revenue**: refunded, cancelled, or pending orders may be excluded from recognized revenue.

## 4. $sum: Summing Values and Counting Documents

### 4.1. Counting with $sum: 1

In $group, counting pattern:

~~~javascript
const orders = db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_orders_agg");

orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  {
    $group: {
      _id: "$status",
      numberOfOrders: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

**$sum: 1** adds one for each document in the group. It does **not** count only non-null values of a field; every document passing $match contributes one unit.

From the dataset:

| status | numberOfOrders |
| --- | ---: |
| paid | 8 |
| pending | 3 |
| refunded | 1 |

**$count** in a pipeline also counts total documents after filtering steps; the **$count accumulator** can be used in supported stages on applicable versions. Still, **$sum: 1** is the universal, easy-to-read pattern when grouping by a key.

### 4.2. Summing Numeric Values of a Field

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      amountTotal: { $sum: "$amount" },
      unitsTotal: { $sum: "$units" }
    }
  }
]).toArray();
~~~

Logical result:

~~~text
_id         = "t001"
count       = 5
amountTotal = NumberDecimal("690.00")
unitsTotal  = 10
~~~

Because amount is stored as Decimal128, total amount preserves exact decimal precision within MongoDB's numeric rules. For money, standardize **Decimal128 and currency/units**. Do not add VND and USD together just because both share an amount field.

### 4.3. Conditional Summing

If you want one pipeline returning both total orders and paid orders per tenant:

~~~javascript
orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  {
    $group: {
      _id: "$tenantId",
      allOrders: { $sum: 1 },
      paidOrders: {
        $sum: {
          $cond: [{ $eq: ["$status", "paid"] }, 1, 0]
        }
      },
      paidAmount: {
        $sum: {
          $cond: [
            { $eq: ["$status", "paid"] },
            "$amount",
            NumberDecimal("0.00")
          ]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

Result:

| Tenant | allOrders | paidOrders | paidAmount |
| --- | ---: | ---: | ---: |
| t001 | 8 | 5 | 690.00 |
| t002 | 4 | 3 | 400.00 |

**$cond** selects the contribution for each document, and $sum adds those values up. This technique is useful for reports with multiple distinct metrics. If you only care about paid orders, placing **$match: {status:"paid"}** before $group reduces the data processed.

### 4.4. Summing a Computed Expression

Suppose you need the total of "units times unit price." If each document had unitPrice instead of amount, you could write:

~~~javascript
{
  $group: {
    _id: "$tenantId",
    totalValue: {
      $sum: {
        $multiply: ["$units", "$unitPrice"]
      }
    }
  }
}
~~~

This illustrates expression syntax rather than a command to run directly on the lab dataset, which lacks unitPrice. On the lab dataset, you can test illustrative operations on amount or add a unitPrice field with its own business meaning. When multiplying and summing financial values, account for rounding, currency, and tax rules.

### 4.5. $sum and Non-Numeric Data

In **$group**, $sum **ignores non-numeric values**. If every input value in a group is non-numeric (null, missing field, String...), the sum result is **0**, rather than concatenating strings or failing just because a String was encountered.

This is a double-edged sword: the pipeline still succeeds, yet can yield a lower total than reality if some amounts were stored as Strings. Check BSON types in your data before trusting financial reports.

## 5. $avg: Average Value and the True Denominator

### 5.1. Syntax

~~~javascript
{
  $group: {
    _id: "$status",
    avgAmount: { $avg: "$amount" }
  }
}
~~~

**$avg** computes the average of numeric values observed in each group. It **ignores** non-numeric, null, or missing values in the $group accumulator context.

### 5.2. Average by Tenant and Status

~~~javascript
orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" },
      averageAmount: { $avg: "$amount" }
    }
  },
  { $sort: { "_id.tenantId": 1, "_id.status": 1 } }
]).toArray();
~~~

Logical result:

| tenantId | status | orderCount | totalAmount | averageAmount |
| --- | --- | ---: | ---: | ---: |
| t001 | paid | 5 | 690.00 | 138.00 |
| t001 | pending | 2 | 120.00 | 60.00 |
| t001 | refunded | 1 | 60.00 | 60.00 |
| t002 | paid | 3 | 400.00 | About 133.33 |
| t002 | pending | 1 | 75.00 | 75.00 |

For the t002 paid group, dividing 400/3 yields a repeating decimal; the exact final representation depends on numeric types and arithmetic rules. Avoid asserting equality via raw string representations in responses. For monetary reports, define a **rounding** policy at display or storage time.

### 5.3. $avg Is Not Total Divided by Document Count When Data Is Dirty

Suppose a group has:

~~~javascript
{ group: "A", value: 10 }
{ group: "A", value: 20 }
{ group: "A", value: null }
{ group: "A" }
~~~

**$sum: "$value" = 30**; **$avg: "$value" = 15**, because only **two** numeric values participate in the average. Meanwhile **$sum: 1 = 4**, because there are four documents.

If you divided **sum / documentCount**, you would get **7.5**, which differs from $avg. This is why you must distinguish:

- **Number of documents in the group**.
- **Number of documents actually holding a valid numeric value**.
- **Number of documents business rules allow into the average**.

If a required field is missing in legacy data, it is best to audit/migrate it first rather than treating $avg's skipping of missing values as a data fix.

### 5.4. When There Are No Numeric Values

If every value seen by $avg is non-numeric or missing, **$avg returns null**. That is a critical difference from **$sum**, which returns 0 when no numeric values are present.

Therefore, when displaying reports:

- **sum = 0** could mean an arithmetic sum of 0 or no valid numeric data.
- **avg = null** means an average could not be computed from the numeric input.
- Do not automatically coerce a null avg to 0 if business needs to distinguish "no data yet" from "actual average is 0."

## 6. $min and $max: Finding Extremes by BSON Comparison

### 6.1. Syntax and Example

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  {
    $group: {
      _id: null,
      minAmount: { $min: "$amount" },
      maxAmount: { $max: "$amount" },
      oldestDate: { $min: "$createdAt" },
      newestDate: { $max: "$createdAt" }
    }
  }
]).toArray();
~~~

Result for the t001 paid group:

~~~text
minAmount  = 90.00
maxAmount  = 250.00
oldestDate = 2026-01-01T00:01:00.000Z
newestDate = 2026-01-01T00:07:00.000Z
~~~

**$min** takes the smallest value and **$max** takes the largest value in the group according to **BSON comparison order**, which is not always the "numerically largest value" if data mixes multiple types.

### 6.2. Do Not Confuse an Extreme Value with Its Full Document

When you write:

~~~javascript
{ $group: { _id: "$tenantId", maxAmount: { $max: "$amount" } } }
~~~

you get the **maxAmount scalar**, not automatically the full document holding that value. If you need "the order with the highest amount" along with orderNo, customerId, and createdAt, options include:

- **$sort by amount descending**, followed by **$group** with **$first** to pick the top document per group, with a tie-breaker field.
- Use suitable accumulators such as **$top/$topN** on supported versions.
- Split the problem into finding the extreme and querying accordingly, accounting for data changes between steps.

Example fetching the orderNo of the t001 paid order with the highest amount:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { amount: -1, _id: 1 } },
  {
    $group: {
      _id: "$tenantId",
      maxOrder: { $first: "$$ROOT" }
    }
  },
  {
    $project: {
      _id: 1,
      maxOrderId: "$maxOrder._id",
      amount: "$maxOrder.amount",
      customerId: "$maxOrder.customerId"
    }
  }
]).toArray();
~~~

Logical result: **agg-o002** with amount 250.00. Here $sort by amount and _id ensures deterministic document selection when values tie. **$first** illustrates retrieving the document accompanying the extreme; the main focus remains the semantics of $max.

### 6.3. Null, Missing, and Mixed Types

In **$group**, if a group has both null/missing values and non-null values, **$min/$max ignore null/missing** when evaluating the remaining values. If all values in the group are null/missing, they return **null**.

However, if a field mixes Number, String, Date, or Array, **$min/$max compare using BSON type order** rather than coercing everything to Number. For example, given numeric amount 100 and String amount "200", max may pick the String because of BSON type precedence, even though it is not the "largest order" numerically.

Practical rule: for min/max monetary reports, ensure the schema uses **Decimal128** (or a normalized numeric type). For timestamps, use BSON Date and never mix Dates with date strings.

### 6.4. $min/$max Differs from Business Ranking Order

**$max: "$status"** picks the highest status under BSON/string comparison; it does **not** mean the highest-priority business status. If you need an order like pending → paid → shipped or severity low → medium → high, map statuses to a business-defined **numeric rank** first, then aggregate on that rank.

## 7. $push: Keeping All Values in a Group

### 7.1. Syntax

~~~javascript
{
  $group: {
    _id: "$customerId",
    orderIds: { $push: "$_id" }
  }
}
~~~

**$push** constructs an Array containing the expression values from the documents entering the group. It **does not deduplicate repeated values**.

### 7.2. Example: Order History per Customer

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: "$customerId",
      paidOrderIds: { $push: "$_id" },
      paidAmounts: { $push: "$amount" },
      paidCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

Result by group:

| customerId | paidOrderIds by createdAt asc | paidCount |
| --- | --- | ---: |
| c01 | [agg-o001, agg-o002, agg-o006] | 3 |
| c02 | [agg-o004] | 1 |
| c03 | [agg-o007] | 1 |

In this example, **$sort comes before $group**, with _id as a tie-breaker to determine full input order within identical createdAt timestamps. The order of **elements inside $push** depends on the order documents enter $group.

**Do not confuse the two kinds of ordering:**

- The order of **values $push-ed into an array** can be controlled with a $sort before $group.
- The order of **output group documents** is still not guaranteed by $group; use **$sort after $group** to sort the groups themselves.

### 7.3. $push Keeps Duplicates

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: null,
      customerSequence: { $push: "$customerId" }
    }
  }
]).toArray();
~~~

Result:

~~~text
["c01", "c01", "c02", "c01", "c03"]
~~~

Customer **c01** appears three times because they have three paid orders. This is expected when you want a raw sequence for auditing or per-record analysis, not a duplicate bug in $push.

### 7.4. $push Can Build Arrays of Objects

You do not have to push only a single scalar field. You can push an object:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      customerId: "c01"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: "$customerId",
      orders: {
        $push: {
          orderId: "$_id",
          amount: "$amount",
          status: "$status",
          date: "$createdAt"
        }
      }
    }
  }
]).toArray();
~~~

The benefit is producing a compact, custom-structured list. The risk is that a group with millions of documents can produce a **massive output Array** and hit BSON size or resource limits. Never use $push to paginate every transaction of a customer with an unbounded history.

## 8. $addToSet: Collecting Distinct Values

### 8.1. Comparing with $push

**$addToSet** accumulates one value per distinct element in the group. It does not guarantee the order of result elements.

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: null,
      allCustomers: { $push: "$customerId" },
      distinctCustomers: { $addToSet: "$customerId" }
    }
  }
]).toArray();
~~~

Conceptual result:

~~~text
allCustomers:
  ["c01", "c01", "c02", "c01", "c03"]

distinctCustomers:
  contains exact values "c01", "c02", "c03"
  but ORDER IS NOT GUARANTEED
~~~

If you need to display customer IDs alphabetically, use **$sortArray** on the $addToSet output (in supported MongoDB versions) or sort afterward in an appropriate step. Do not assume $sort before $group gives **$addToSet** deterministic element ordering.

### 8.2. Distinct Element Count

A common pattern is taking **$size** of an $addToSet result:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      customerIds: { $addToSet: "$customerId" },
      paidOrders: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 1,
      paidOrders: 1,
      distinctCustomerCount: { $size: "$customerIds" },
      customerIds: 1
    }
  }
]).toArray();
~~~

Logical result:

~~~text
tenantId              = "t001"
paidOrders            = 5
distinctCustomerCount = 3
customerIds           = set {"c01", "c02", "c03"}, arbitrary order
~~~

**Performance note:** computing distinct counts via $addToSet must build the entire value set per group. If cardinality is huge, memory usage and output array size can spike; when the goal is solely counting unique values, consider two-stage grouping, indexes, pre-aggregated tables, or another workload-appropriate approach.

### 8.3. $addToSet Can Collect an Array as a Single Element

In the lab, each order's **tags** field is an Array. If you write:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      tagArrays: { $addToSet: "$tags" }
    }
  }
]).toArray();
~~~

each order's tags Array is treated as **a single whole-array value** in the accumulator context. The result is an **Array of Arrays**, not automatically flattened into a list of unique tags.

Example shape:

~~~text
tagArrays = [
  ["new", "web"],
  ["sale", "app"],
  ["web"],
  ["web", "vip"],
  ...
]
~~~

Do not assume **$addToSet: "$tags"** automatically yields unique individual tag elements.

### 8.4. To Collect Each Distinct Tag: $unwind Before Grouping

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tenantId",
      distinctTags: { $addToSet: "$tags" },
      tagOccurrences: { $sum: 1 }
    }
  }
]).toArray();
~~~

The result contains five distinct tags:

~~~text
{"new", "web", "sale", "app", "vip"}
~~~

In t001's data, there are **5** distinct tags: new, web, sale, app, vip. The **tagOccurrences** field counts **tag elements** after $unwind, not orders.

Counting from the lab dataset:

| Order | Number of tags elements |
| --- | ---: |
| agg-o001 | 2 |
| agg-o002 | 2 |
| agg-o003 | 1 |
| agg-o004 | 1 |
| agg-o005 | 2 |
| agg-o006 | 2 |
| agg-o007 | 2 |
| agg-o008 | 1 |
| **Total** | **13** |

Hence **tagOccurrences = 13**, while **t001 order count = 8**. If you place **{ $sum: "$amount" }** after $unwind without care, every order with two tags has its amount summed **twice**. This is a classic aggregation bug.

### 8.5. Document Values and Field Order

With $addToSet, two embedded documents are considered equal when they have **the same fields, values, and field order per document comparison rules**. For example:

~~~javascript
{ sku: "A", qty: 1 }
{ qty: 1, sku: "A" }
~~~

should not be assumed to collapse into a single object in $addToSet merely because the application considers those two key–value pairs equivalent. If uniqueness by a business key is required, use a stable scalar like **sku**, or normalize the object before adding it to the set.

For Strings, comparisons can also be affected by the operation's collation. For case-insensitive uniqueness or normalized business codes, define explicit comparison/normalization rules rather than expecting $addToSet to reconcile differences automatically.

## 9. Building a Report Combining All Six Accumulators

Example report **by tenant and status**, including:

- Order count.
- Total value.
- Average value.
- Minimum and maximum value.
- Chronological list of orderIds.
- Distinct set of customerIds.

~~~javascript
orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      amountTotal: { $sum: "$amount" },
      amountAverage: { $avg: "$amount" },
      amountMinimum: { $min: "$amount" },
      amountMaximum: { $max: "$amount" },
      orderIds: { $push: "$_id" },
      customerIds: { $addToSet: "$customerId" }
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      status: "$_id.status",
      orderCount: 1,
      amountTotal: 1,
      amountAverage: 1,
      amountMinimum: 1,
      amountMaximum: 1,
      orderIds: 1,
      customerIds: 1,
      distinctCustomerCount: { $size: "$customerIds" }
    }
  },
  { $sort: { tenantId: 1, status: 1 } }
]).toArray();
~~~

For tenant **t001** and status **paid**, the logical result is:

~~~text
tenantId             = "t001"
status               = "paid"
orderCount           = 5
amountTotal          = 690.00
amountAverage        = 138.00
amountMinimum        = 90.00
amountMaximum        = 250.00
orderIds             = ["agg-o001", "agg-o002", "agg-o004",
                        "agg-o006", "agg-o007"]
customerIds          = set {"c01", "c02", "c03"}
distinctCustomerCount= 3
~~~

**orderIds** follows the sorted input order; **customerIds** has no guaranteed order. The **final $sort** only sorts the groups, without modifying element ordering inside the two Array accumulators.

In production, add **$push orderIds** only if the number of orders per group has a sensible bound. If you only need sums, averages, and counts, omit Array accumulators to avoid unnecessary accumulation overhead.

## 10. Null, Missing, String, and Array: Accumulators Do Not Treat Them Identically

A clean dataset often hides edge-case accumulator behavior. Let's create a second collection to illustrate **non-numeric values** and **mixed types**. This is for demonstration only, not a recommendation to store business data this way.

### 10.1. Seeding Edge-Case Data

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_accumulators_lab");
  const c = lab.getCollection("lab_measurement_edges");
  const tag = "accumulators-edges-v1";

  c.deleteMany({ dataset: tag });

  c.insertMany([
    { _id: "m01", dataset: tag, group: "A", value: NumberInt(10) },
    { _id: "m02", dataset: tag, group: "A", value: NumberInt(20) },
    { _id: "m03", dataset: tag, group: "A", value: null },
    { _id: "m04", dataset: tag, group: "A" },
    { _id: "m05", dataset: tag, group: "B", value: null },
    { _id: "m06", dataset: tag, group: "B" },
    { _id: "m07", dataset: tag, group: "C", value: "bad" },
    { _id: "m08", dataset: tag, group: "C", value: NumberInt(5) },
    { _id: "m09", dataset: tag, group: "D", value: [4, 6] },
    { _id: "m10", dataset: tag, group: "D", value: NumberInt(5) }
  ]);

  print(c.countDocuments({ dataset: tag }));
})();
~~~

**Expected result:** 10 documents. Anomalous values are intentionally inserted to compare accumulators.

### 10.2. $sum and $avg Ignore Non-Numeric Values in $group

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    {
      $match: {
        dataset: "accumulators-edges-v1",
        group: { $in: ["A", "B", "C", "D"] }
      }
    },
    {
      $group: {
        _id: "$group",
        documentCount: { $sum: 1 },
        total: { $sum: "$value" },
        average: { $avg: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Expected result:

| Group | documentCount | total | average | Explanation |
| --- | ---: | ---: | ---: | --- |
| A | 4 | 30 | 15 | Only 10 and 20 participate in arithmetic |
| B | 2 | 0 | null | Null and missing yield no numeric input |
| C | 2 | 5 | 5 | String "bad" is ignored by sum/avg |
| D | 2 | 5 | 5 | Array [4,6] is not traversed element-wise inside $group |

Group **D** in particular highlights an important distinction: inside **$group**, when a $sum/$avg expression points to **an Array**, that Array is treated as a **non-numeric value**, rather than automatically expanding 4 and 6 to sum them.

Do not mechanically apply this rule to stages like $project: in certain expression contexts, **$sum** and **$avg** can traverse elements of an Array when given a single-operand syntax. Always check **both the stage and the operand form**.

### 10.3. $min/$max Use BSON Comparison Order

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    { $match: { dataset: "accumulators-edges-v1" } },
    {
      $group: {
        _id: "$group",
        minimum: { $min: "$value" },
        maximum: { $max: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

For group **A**, min = 10 and max = 20; for group **B**, both min and max are null. Group **C** mixes Number 5 and String "bad", while group **D** mixes Number 5 and Array [4,6]. Because MongoDB compares by BSON type before value in mixed-type scenarios, extreme results in C/D do not represent a **numerical** ranking.

To ensure min/max reflect numeric extremes, filter/normalize data before grouping:

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    { $match: { dataset: "accumulators-edges-v1" } },
    {
      $match: {
        value: { $type: ["int", "long", "double", "decimal"] }
      }
    },
    {
      $group: {
        _id: "$group",
        minNumeric: { $min: "$value" },
        maxNumeric: { $max: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

In the lab, does this numeric filter exclude null, String, and Arrays containing Numbers? **Watch out:** query-predicate `$type` can match when an Array contains a Number. To guarantee **the entire field is a scalar numeric** and reject Arrays, use an aggregation expression:

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    { $match: { dataset: "accumulators-edges-v1" } },
    {
      $match: {
        $expr: {
          $in: [
            { $type: "$value" },
            ["int", "long", "double", "decimal"]
          ]
        }
      }
    },
    {
      $group: {
        _id: "$group",
        minNumeric: { $min: "$value" },
        maxNumeric: { $max: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

For mixed types in production, apply **schema validation** and intentional migrations rather than relying solely on accumulators to skip malformed records.

### 10.4. Normalizing Null/Missing Coupons with $ifNull

In the order dataset, some documents have coupon as null, some **lack the field**, and one document has an empty string coupon.

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      coupons: {
        $addToSet: {
          $ifNull: ["$coupon", "(none)"]
        }
      },
      couponsAll: {
        $push: {
          $ifNull: ["$coupon", "(none)"]
        }
      }
    }
  }
]).toArray();
~~~

**$ifNull** in this example maps null/missing to "(none)" for explicit handling. The coupons result contains these distinct values:

~~~text
{"(none)", "SAVE10", "SAVE20", ""}
~~~

Order is not guaranteed. An **empty string** remains distinct from "(none)" because $ifNull only handles null/missing/undefined per expression semantics. If an empty string also means "no coupon" in business logic, add a separate conversion rule.

## 11. $unwind and the Risk of Double-Counting Data

Reports over Arrays often suffer from a silent bug: **$unwind turns one document into many documents**, causing accumulators like $sum: 1 or $sum: "$amount" to operate over post-unwind rows rather than original orders.

### 11.1. Semantically Wrong Example When Wanting Order Revenue

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      amountTotal: { $sum: "$amount" }
    }
  }
]).toArray();
~~~

Here **count = 13**, not 8; amountTotal is also summed repeatedly according to each order's tag count. Never label this count as "number of orders" or amountTotal as "total order amount" unless deliberately designed around expanded rows.

### 11.2. Separating the Two Metrics

A cleaner design runs two branches inside **$facet**, one aggregating source orders and one unwinding tags:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  {
    $facet: {
      orderMetrics: [
        {
          $group: {
            _id: null,
            orderCount: { $sum: 1 },
            totalAmount: { $sum: "$amount" }
          }
        }
      ],
      tagMetrics: [
        { $unwind: "$tags" },
        {
          $group: {
            _id: null,
            tagOccurrences: { $sum: 1 },
            distinctTags: { $addToSet: "$tags" }
          }
        }
      ]
    }
  }
]).toArray();
~~~

Logical result:

~~~text
orderMetrics: orderCount=8, totalAmount=870.00
tagMetrics:   tagOccurrences=13, distinctTags has 5 values
~~~

**$facet** is merely one way to structure a pipeline; it still consumes resources and has its own memory/output size limits. Choose an appropriate computation strategy and data model when datasets grow very large.

## 12. Semantic Errors to Avoid

### 12.1. Grouping by the Wrong Key

~~~javascript
{ $group: { _id: "$status", total: { $sum: "$amount" } } }
~~~

merges tenants together. In multi-tenant applications, if per-tenant results are needed, enforce an authorized **$match on tenant** or include **tenantId in `_id`**. This mistake not only breaks statistics but can also leak aggregate data across tenants.

### 12.2. Failing to Filter Status When Calling It Revenue

If you sum every order including pending and refunded ones, the sum is **total record amount**, not necessarily recognized revenue. Define metrics explicitly: paid amount, net revenue after refunds, gross order value, order count, and so on. Accumulators do not know your accounting definitions.

### 12.3. $addToSet Does Not Sort

~~~javascript
{ $group: { _id: null, ids: { $addToSet: "$customerId" } } }
~~~

returns an Array with distinct values in arbitrary order. If the application uses that Array to build cache keys, compare snapshots, or display lists, normalize the order in a subsequent step.

### 12.4. Unbounded $push Length

~~~javascript
{ $group: { _id: "$tenantId", allOrders: { $push: "$$ROOT" } } }
~~~

risks producing a result document holding millions of orders, which is impractical and can breach size limits. Design separate pagination for detailed lists; use accumulators for compact metrics.

### 12.5. Never Assume $group Output Order

MongoDB does not guarantee group ordering after $group. Even with indexes and ascending input documents, if you want sorted group output, add **$sort after $group**.

## 13. Performance: $group, Memory, and Pipeline Order

### 13.1. $group Is an Aggregation Stage That Can Consume Heavy Memory

To execute many forms of $group, MongoDB must maintain state for each group (grouping keys, sums, averages, value sets, accumulated arrays...). In pipelines with many groups or heavy $push/$addToSet usage, memory consumption can climb quickly.

MongoDB provides memory management and the ability to **spill to disk** for certain stages depending on version/configuration (often cited with a **100 MB** threshold for eligible stages). **allowDiskUse** permits supported stages to use temporary disk space when exceeding the limit. Example:

~~~javascript
orders.aggregate(
  [
    { $match: { dataset: "accumulators-v1" } },
    {
      $group: {
        _id: "$tenantId",
        orderCount: { $sum: 1 },
        totalAmount: { $sum: "$amount" }
      }
    }
  ],
  { allowDiskUse: true }
).toArray();
~~~

**allowDiskUse does not disable the 16 MiB limit on a single output BSON document** and does not guarantee arbitrary Array accumulations succeed on unbounded data. In particular, $push-ing millions of objects can hit the output size limit before disk spilling helps.

### 13.2. Put Selective $match Stages First

Do not pass an entire collection through heavy stages before filtering by tenant/time range.

Better:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid",
      createdAt: {
        $gte: ISODate("2026-01-01T00:00:00.000Z"),
        $lt: ISODate("2026-02-01T00:00:00.000Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      count: { $sum: 1 },
      total: { $sum: "$amount" }
    }
  }
]).toArray();
~~~

An index aligned with the filter (and sort when needed) reduces the documents examined. Still, **indexes do not eliminate all grouping cost**: MongoDB must still aggregate the matching documents by grouping key.

### 13.3. Sort Before $group Only When Actually Needed

**$sum, $avg, $min, $max, and $addToSet** do not require ordered input documents to compute their values semantically. **$push** cares about order only if the application relies on the resulting Array's sequence.

Therefore:

- If you only compute sums, averages, extremes, or unordered sets, omit **$sort before $group** unless needed for something else.
- If you need **$push** ordered by createdAt, place **$sort before $group** with an appropriate tie-breaker.
- If you need to sort **output groups**, place **$sort after $group**.

Sorting can become a blocking stage consuming heavy resources on large datasets. Use it only when output semantics truly require it.

### 13.4. Reading explain to Inspect Execution

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_orders_agg")
  .explain("executionStats")
  .aggregate([
    {
      $match: {
        dataset: "accumulators-v1",
        tenantId: "t001"
      }
    },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 },
        amount: { $sum: "$amount" }
      }
    }
  ]);
~~~

In explain, check **IXSCAN/COLLSCAN**, keys/documents examined, presence of SORT, and group-related details. Explain layout varies across MongoDB versions and query engines.

On the 12-document lab set, COLLSCAN can be cheaper than IXSCAN; never use that observation to conclude indexes are useless on multi-million-document production collections.

### 13.5. Avoid Pulling All Data from the Database Just to Sum

Computing sums inside MongoDB usually cuts network traffic compared to pulling millions of documents into an API and looping in application memory. Still, do not assume every aggregation is cheap: if grouping produces huge key counts or large Arrays, the aggregator can still consume heavy CPU, memory, and temporary disk.

For dashboards continuously refreshed over massive datasets, you may need **incremental aggregation**, dedicated summary collections, or materialized read models alongside synchronization and change-handling strategies.

## 14. $sum/$avg/$min/$max Outside $group: Distinguishing Array Operands

Suppose a document looks like:

~~~javascript
{
  _id: "s001",
  values: [4, 6, 10],
  tax: 2
}
~~~

In stages such as **$project**, you can use expressions:

~~~javascript
db.someCollection.aggregate([
  {
    $project: {
      summedValues: { $sum: "$values" },
      averagedValues: { $avg: "$values" },
      totalWithTax: { $sum: ["$tax", 10] }
    }
  }
]);
~~~

With a **single operand** that is an Array, $sum/$avg in expression context can iterate over numeric elements. When given a **multi-operand list**, Array handling differs; an Array may be treated as a non-numeric operand. Inside **$group**, when the expression points directly to an Array, $sum/$avg treats the Array as non-numeric.

For **$min/$max**, Array handling also depends on stage and operand form; do not turn a $project example into a universal rule for $group. When you need to compute across elements inside an Array, use **$unwind** explicitly or an appropriate Array expression, then double-check how many times each document contributes.

In short, always read the **full context of stage + accumulator/expression syntax**, rather than just the operator name.

## 15. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| $sum is 0 despite seeing value "100" | Data is a String, not a Number | Audit BSON types, convert cleanly |
| $avg differs from total divided by document count | $avg skips null/missing/non-numeric | Distinguish documentCount from numericCount |
| $avg is null | No valid numeric values in group | Display missing-data state instead of coercing to 0 |
| $max returns a String instead of a numeric value | Mixed BSON types; BSON comparison order | Normalize schema before aggregating |
| $push has duplicate elements | $push preserves all occurrences | Use $addToSet if distinct values are needed |
| $addToSet returns different order across runs | Set output has no ordering guarantee | Sort the Array after building the set if needed |
| $addToSet: "$tags" returns Array of Arrays | tags is an Array, added whole as one element | $unwind tags first to get unique individual tags |
| Total amount inflates after $unwind | One order contributes amount multiple times | Sum amounts before unwind or split branches in $facet |
| $group outputs a single row | _id: null or grouping expression evaluates identically | Verify grouping key |
| Group merges data across tenants | Missing tenant in $match/_id | Enforce permission-checked tenant constraint |
| $push Array grows too huge | One group holds too many documents | Do not replace pagination with group; keep output compact |
| $group consumes excessive memory | High group cardinality or large set/array accumulators | Filter early, cap data, inspect allowDiskUse and schema |
| Output groups are not in desired order | $group does not guarantee output order | Add $sort after $group |
| Trying to use $push as a $project function | $push is an accumulator for supported stages | Use $group/$setWindowFields or an Array expression |
| Group output is empty when filter matches nothing | Zero input documents means $group emits no groups | Handle empty results in application or pipeline |

## 16. Practice Exercises

### Exercise 1 — Counting Orders by Status

Write a pipeline using only **$match**, **$group**, and **$sort** to count paid/pending/refunded across all tenants. Predict the three counts **8, 3, 1** and explain why $sum: 1 counts documents rather than summing amount.

### Exercise 2 — Computing Sum, Average, Min, and Max

For t001 paid orders, use one $group to compute four metrics: totalAmount, averageAmount, minAmount, maxAmount. Predict the results **690.00**, **138.00**, **90.00**, and **250.00**. Why should you not replace all NumberDecimal values with Strings?

### Exercise 3 — Two Ways to Compute paidAmount

Compare:

1. Pre-$match for status paid only, then $sum: "$amount".
2. $group across all statuses and use $sum with $cond to sum only paid.

How do the two approaches differ if the report also needs pending/refunded order counts?

### Exercise 4 — Duplicates and Ordering

For t001 paid, use **$push** and **$addToSet** on customerId. Explain why $push includes c01 three times while $addToSet includes c01 once. Use $sort before group to control $push ordering and explain why $addToSet ordering cannot be relied upon.

### Exercise 5 — Chronological List of Objects

Create an array of {orderId, amount, createdAt} objects per customer of t001 using $push. Put a deterministic $sort before group. Why should you not push entire $$ROOT documents for millions of orders just to display a history page?

### Exercise 6 — Tags and $unwind

Find distinct tags for t001:

1. Try $addToSet: "$tags" without unwinding.
2. Try $unwind: "$tags" followed by $addToSet: "$tags".

Explain why the first produces an Array of Arrays, while the second has **5 distinct tags** and **13** total tag occurrences.

### Exercise 7 — Avoiding Double-Counted Revenue

Write a pipeline intentionally placing $unwind tags before $sum amount. Compare the result with t001's true total of **870.00** computed from source orders. Fix it using $facet or two independent pipelines, explaining why the two metrics must be computed at different granularities.

### Exercise 8 — Null and Type Mismatches

Run the lab_measurement_edges seed. Predict:

- Group A: sum = 30, avg = 15.
- Group B: sum = 0, avg = null.
- Group C: sum = 5, avg = 5.
- Group D: sum = 5, avg = 5.

Explain why $sum/$avg in $group do not add the numbers inside group D's Array [4,6]. Add a scalar numeric filter before group to exclude invalid types.

### Exercise 9 — Extreme Value and Full Document

Find max amount in t001 paid. Then write a pipeline returning **_id and customerId of the document** with the highest amount, using _id as a tie-breaker. Why does $max: "$amount" alone not return the document?

### Exercise 10 — Designing Business-Accurate Metrics

Product asks for a monthly "net revenue" report. Data includes paid, refunded, and pending orders, some in different currencies. Describe the rules you must define **before** using $sum. For example: currency conversion, taxes, full/partial refunds, recognition timestamp, and eligible statuses.

### Exercise 11 — Observing Performance

Run explain on a pipeline grouping orders by tenant/status. Record IXSCAN/COLLSCAN, totalDocsExamined, nReturned, and any sort/group stages that appear. State why small lab data cannot represent performance on a multi-million-document collection.

### Exercise 12 — Controlling Array Length

Suppose one tenant has two million orders and a pipeline tries to return **unique customerIds** alongside **all orderIds** in one document. State the risks of $push/$addToSet, the difference between memory spilling and the 16 MiB BSON limit, and propose a solution returning **compact stats + paginated detail lists**.

## 17. Official References

- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/).
- MongoDB Manual — [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).
- MongoDB Manual — [$sum](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/).
- MongoDB Manual — [$avg](https://www.mongodb.com/docs/manual/reference/operator/aggregation/avg/).
- MongoDB Manual — [$min](https://www.mongodb.com/docs/manual/reference/operator/aggregation/min/).
- MongoDB Manual — [$max](https://www.mongodb.com/docs/manual/reference/operator/aggregation/max/).
- MongoDB Manual — [$push](https://www.mongodb.com/docs/manual/reference/operator/aggregation/push/).
- MongoDB Manual — [$addToSet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/addToSet/).
- MongoDB Manual — [$unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/).
- MongoDB Manual — [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).

**Key takeaway:** **$sum** adds or counts, **$avg** averages valid numeric values, **$min/$max** find extremes by BSON comparison, **$push** retains values including duplicates, and **$addToSet** keeps only distinct values **without guaranteeing order**. Before aggregating, verify the **grouping key, filters, BSON types, and data granularity after $unwind**. Accumulators shine when producing **compact results with clear business semantics**, rather than constructing unbounded result arrays.