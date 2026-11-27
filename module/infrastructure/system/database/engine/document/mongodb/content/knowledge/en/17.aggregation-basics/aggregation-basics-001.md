# Document Flow Through a Pipeline and How to Distinguish Stages from Expressions in MongoDB

## 1. Why Understanding Document Flow in the Aggregation Framework Matters

A **find()** query typically focuses on selecting documents that match a condition and returning the desired fields. When an application needs computation, structural transformation, statistics, joining data, or preparing a complex report, MongoDB provides the **Aggregation Framework**.

At the core of the Aggregation Framework is the **pipeline**: a sequence of processing steps where the output of the previous step becomes the input for the next step.

~~~text
Collection orders
      |
      |  Documents from source
      v
  [$match]          Select orders to calculate
      |
      v
  [$unwind]         Split the items array into multiple documents
      |
      v
  [$group]          Group by SKU and sum quantities
      |
      v
  [$sort]           Sort statistical results
      |
      v
 Final result
~~~

Two concepts are often confused by beginners:

1. **Stage:** a **step in the pipeline**, such as **$match**, **$project**, **$group**, or **$sort**. A stage receives a stream of documents and determines how to produce the output stream.
2. **Expression:** a **value-computing expression** inside stages that allow its use, such as **$multiply**, **$add**, **$cond**, **$concat**, or **$toUpper**. An expression takes values and returns a value; by itself, it is **not a pipeline step**.

Example:

~~~javascript
db.orders.aggregate([
  {
    $project: {                    // Stage
      _id: 0,
      customerId: 1,
      totalWithFee: {              // Computed field
        $add: [                   // Expression
          "$subtotal",           // Field-path expression
          "$shippingFee"
        ]
      }
    }
  }
]);
~~~

**$project** is a stage. **$add** is an expression inside that stage. **"$subtotal"** is an expression referencing a field of the current document, not an ordinary string literal when used in an expression position.

Understanding this hierarchy helps you read queries accurately, avoid syntax errors, and predict the **data shape** as well as the **document count** after each step.

## 2. Practice Data: Orders and Order Line Items

The examples use **mongosh** and a dedicated test collection. In practice, do not run lab data writes against production.

~~~javascript
use aggregation_flow_lab

db.orders.insertMany([
  {
    _id: "O101",
    tenantId: "SHOP-A",
    customerId: "C01",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-01T09:00:00Z"),
    shippingFee: NumberDecimal("10.00"),
    items: [
      {
        sku: "SKU-A",
        qty: NumberInt(2),
        unitPrice: NumberDecimal("100.00")
      },
      {
        sku: "SKU-B",
        qty: NumberInt(1),
        unitPrice: NumberDecimal("50.00")
      }
    ]
  },
  {
    _id: "O102",
    tenantId: "SHOP-A",
    customerId: "C02",
    channel: "APP",
    status: "PAID",
    createdAt: ISODate("2026-07-02T09:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-A",
        qty: NumberInt(1),
        unitPrice: NumberDecimal("100.00")
      },
      {
        sku: "SKU-C",
        qty: NumberInt(3),
        unitPrice: NumberDecimal("20.00")
      }
    ]
  },
  {
    _id: "O103",
    tenantId: "SHOP-A",
    customerId: "C01",
    channel: "WEB",
    status: "CANCELLED",
    createdAt: ISODate("2026-07-02T12:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-B",
        qty: NumberInt(2),
        unitPrice: NumberDecimal("50.00")
      }
    ]
  },
  {
    _id: "O104",
    tenantId: "SHOP-B",
    customerId: "C03",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-03T09:00:00Z"),
    shippingFee: NumberDecimal("10.00"),
    items: [
      {
        sku: "SKU-A",
        qty: NumberInt(4),
        unitPrice: NumberDecimal("100.00")
      }
    ]
  },
  {
    _id: "O105",
    tenantId: "SHOP-A",
    customerId: "C03",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-03T13:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-C",
        qty: NumberInt(2),
        unitPrice: NumberDecimal("20.00")
      }
    ]
  },
  {
    _id: "O106",
    tenantId: "SHOP-A",
    customerId: "C04",
    channel: "POS",
    status: "PENDING",
    createdAt: ISODate("2026-07-04T09:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-B",
        qty: NumberInt(1),
        unitPrice: NumberDecimal("50.00")
      }
    ]
  },
  {
    _id: "O107",
    tenantId: "SHOP-A",
    customerId: "C04",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-05T09:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: []
  }
]);
~~~

**Note:** each **_id** is set to a fixed value for easy cross-referencing. Re-running the exact **insertMany()** command will encounter a duplicate key error if the data already exists. Create a new collection or intentionally reset the lab data before practicing again.

The documents above have:

- **Common fields:** _id, tenantId, customerId, channel, status, createdAt, shippingFee.
- **Array field:** items containing objects with sku, qty, and unitPrice.
- **Specific BSON types:** **createdAt** is BSON Date, **qty** is Int32, **unitPrice** and **shippingFee** are Decimal128.
- **Intentional cases:** one CANCELLED order, one order belonging to another tenant, one PENDING order, and one PAID order with an empty items array.

This helps clearly illustrate how **$match selects documents** and **$unwind changes the document count**.

## 3. A Pipeline Is an Array of Stages Executed in Order

### 3.1. General Syntax

~~~javascript
db.collection.aggregate([
  { $stageA: { /* stage A configuration */ } },
  { $stageB: { /* stage B configuration */ } },
  { $stageC: { /* stage C configuration */ } }
]);
~~~

The first argument of **aggregate()** is **an array of stage documents**. Each element in the array represents a processing step.

Example:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $project: {
      _id: 1,
      customerId: 1,
      channel: 1
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

This pipeline:

1. Receives documents from the **orders** collection.
2. **$match:** keeps only PAID orders of SHOP-A.
3. **$project:** keeps only _id, customerId, and channel.
4. **$sort:** sorts by _id ascending.
5. Returns a cursor containing the output documents.

Expected result:

~~~javascript
[
  { _id: "O101", customerId: "C01", channel: "WEB" },
  { _id: "O102", customerId: "C02", channel: "APP" },
  { _id: "O105", customerId: "C03", channel: "WEB" },
  { _id: "O107", customerId: "C04", channel: "WEB" }
]
~~~

**Core point:** a subsequent stage receives the **document shape produced by the preceding stage**, rather than automatically looking back at the original document if a field was removed or altered.

### 3.2. Visualizing Documents Passing Through Each Stage

~~~text
Source (7 orders)
  |
  |  O101, O102, O103, O104, O105, O106, O107
  v
$match (tenantId=SHOP-A, status=PAID)
  |
  |  O101, O102, O105, O107            (4 documents)
  v
$project (_id, customerId, channel)
  |
  |  {O101,C01,WEB}
  |  {O102,C02,APP}
  |  {O105,C03,WEB}
  |  {O107,C04,WEB}                    (4 documents)
  v
$sort (_id ascending)
  |
  |  4 documents in new order
  v
Result cursor
~~~

Not every stage changes the number of documents. Some only alter fields; some can **decrease** or **increase** the document count; some aggregate an entire set into summary documents.

## 4. Distinguishing Stages from Expressions by Syntactic Position

### 4.1. Stage: Operating on the Document Stream

Example with three stages:

~~~javascript
[
  { $match: { status: "PAID" } },
  { $set: { flag: true } },
  { $sort: { createdAt: -1 } }
]
~~~

- **$match** decides which documents are kept.
- **$set** creates/replaces fields in each document.
- **$sort** changes the order of the documents.

Each stage typically has **one stage name at the top level of the stage document**. Do not place two different stages in the same object expecting MongoDB to automatically execute two steps.

### 4.2. Expression: Computing Values Inside a Stage

~~~javascript
db.orders.aggregate([
  {
    $set: {
      channelUpper: {
        $toUpper: "$channel"
      },
      hasItems: {
        $gt: [
          { $size: "$items" },
          0
        ]
      }
    }
  }
]);
~~~

In this command:

- **$set** is a stage.
- **$toUpper**, **$gt**, and **$size** are expressions.
- **"$channel"** and **"$items"** are field-path expressions.
- **0** is a constant.

An expression **evaluates a value**. A stage **controls document flow and shape**.

### 4.3. Incorrect Example: Placing an Expression as a Stage

~~~javascript
// Wrong: $add is not an aggregation pipeline stage.
db.orders.aggregate([
  {
    $add: ["$shippingFee", 10]
  }
]);
~~~

To compute a value, place **$add** inside a stage that supports expressions:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      increasedFee: {
        $add: [
          "$shippingFee",
          NumberDecimal("10.00")
        ]
      }
    }
  }
]);
~~~

### 4.4. Incorrect Example: Using a Stage Inside an Expression

~~~javascript
// Wrong: $match is a stage, not an expression returning a boolean.
db.orders.aggregate([
  {
    $project: {
      isPaid: {
        $match: { status: "PAID" }
      }
    }
  }
]);
~~~

If you want to compute the **isPaid** value for each document, use the **$eq** expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      isPaid: {
        $eq: ["$status", "PAID"]
      }
    }
  }
]);
~~~

If you want to **exclude non-PAID documents**, place a separate **$match stage** instead of computing a boolean.

### 4.5. Several $-Prefixed Names Have Multiple Roles

Not every keyword starting with **$** belongs to the same category:

| Symbol | Common Role | Example |
|---|---|---|
| **$match** | Pipeline stage | **{$match:{status:"PAID"}}** |
| **$project** | Pipeline stage | **{$project:{name:1}}** |
| **$group** | Pipeline stage | **{$group:{_id:"$status",n:{$sum:1}}}** |
| **$add** | Aggregation expression | **{$add:["$a","$b"]}** |
| **$cond** | Aggregation expression | **{$cond:[condition,a,b]}** |
| **$gt** | Has both query operator and expression forms | **{qty:{$gt:2}}** differs from **{$gt:["$qty",2]}** |
| **$sum** | Aggregation accumulator or expression depending on context | Inside **$group** or **$project** |
| **$in** | Query operator or aggregation expression depending on context | **{tags:{$in:["a"]}}** and **{$in:["a","$tags"]}** |
| **$literal** | Aggregation expression | Preserves a value verbatim instead of special interpretation. |
| **$set** | Pipeline stage; also an update operator outside aggregation | **{$set:{x:1}}** in a pipeline or update document. |

The same operator name can sometimes have different syntax depending on **context**. Do not look only at the **$** prefix to deduce that it is a stage.

## 5. How to Read Flow Through Common Stages

### 5.1. $match: Filtering Documents

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  }
]);
~~~

**$match** keeps documents that satisfy the condition. With the sample data, out of 7 input documents, **4 documents** remain: O101, O102, O105, and O107.

Characteristics:

- **Reduces or preserves the document count**; never multiplies documents.
- Does not alter fields in the retained documents on its own.
- Standard condition syntax follows **MongoDB query predicates**, similar to **find()**.
- Usually should be placed early when possible to reduce the data volume for subsequent stages.

If **$match** is at the beginning of the pipeline and the query/index matches, MongoDB can use an index on the source collection. If placed after a stage that transforms fields, the optimizer can only push conditions earlier in cases that preserve semantics.

### 5.2. $project: Selecting, Removing, and Computing Fields

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      customerId: 1,
      status: 1,
      itemCount: {
        $size: "$items"
      }
    }
  }
]);
~~~

**$project** creates the desired output shape:

- **customerId: 1** and **status: 1** retain existing fields.
- **_id: 0** excludes _id from the result.
- **itemCount: {$size:"$items"}** creates a computed field.

Example of O101 after the stage:

~~~javascript
{
  customerId: "C01",
  status: "PAID",
  itemCount: 2
}
~~~

**$project usually preserves the document count**, but can drop fields that later stages need. All expressions inside $project are evaluated in the context of that stage's input document.

**Projection rule:** you cannot arbitrarily mix **include** and **exclude** in the same **$project** (except for _id and certain special expression cases). For example, setting both **customerId:1** and **status:0** is usually an invalid configuration. If you want to drop a few fields while keeping the rest, consider **$unset**.

### 5.3. $set / $addFields: Adding or Replacing Fields

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: "$items"
      },
      channelUpper: {
        $toUpper: "$channel"
      }
    }
  }
]);
~~~

**$set** is an alias for **$addFields** in aggregation. It **keeps unmentioned fields** and adds/replaces the declared fields. If a later stage needs the original document along with the computed fields, **$set** can be more convenient than **$project**.

~~~text
Document before $set:
  {_id, tenantId, status, items, shippingFee, ...}
            |
            v
Document after $set:
  {_id, tenantId, status, items, shippingFee,
   itemCount, channelUpper, ...}
~~~

**Warning:** if **$set** defines a field that already exists, the new value can overwrite the old value in the stage's output. Therefore, you must know the semantics clearly when naming fields.

### 5.4. $unset: Removing Fields

~~~javascript
db.orders.aggregate([
  {
    $unset: [
      "shippingFee",
      "items.unitPrice"
    ]
  }
]);
~~~

**$unset** in aggregation is a stage dedicated to removing fields, often convenient when you want to keep the rest of the document. It **does not delete data in the source collection** when used in a normal read pipeline.

Distinguish between the **$unset stage** and the **$unset update operator** in a regular update command: the name is the same, but the context and storage effect differ.

### 5.5. $sort: Reordering Documents

~~~javascript
db.orders.aggregate([
  {
    $sort: {
      createdAt: -1,
      _id: 1
    }
  }
]);
~~~

**$sort** changes the order of documents without adding or removing fields on its own. With the same input documents, the output document count remains equal.

If documents have the same createdAt and the query only sorts by createdAt, the order among them may not be guaranteed to be stable. Adding a tie-breaker field such as **_id** helps define the order more clearly, especially for pagination.

### 5.6. $limit and $skip: Changing the Number of Retained Documents

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 3 }
]);
~~~

**$skip** skips the first two documents in the post-sort stream, and **$limit** takes at most the next three documents.

The order of **$sort**, **$skip**, and **$limit** matters. If **$limit** is placed before **$sort**, the query will only sort the already limited set instead of finding the three newest documents of the entire set.

### 5.7. $unwind: One Document Can Become Multiple Documents

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $unwind: "$items" },
  {
    $project: {
      _id: 1,
      customerId: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
]);
~~~

After **$match**, there are four orders: O101, O102, O105, O107. The items array of each order:

| Order | Number of items elements | Document count after default $unwind |
|---|---:|---:|
| O101 | 2 | 2 |
| O102 | 2 | 2 |
| O105 | 1 | 1 |
| O107 | 0 | 0 |
| **Total** | **5** | **5** |

After **$unwind**, each output document contains **one** item at the items field instead of the entire array.

For example, O101 turns into two documents:

~~~javascript
{
  _id: "O101",
  customerId: "C01",
  sku: "SKU-A",
  qty: 2
}

{
  _id: "O101",
  customerId: "C01",
  sku: "SKU-B",
  qty: 1
}
~~~

Duplicate **_id: "O101"** in pipeline results is normal. These are **intermediate result documents**, not two new documents inserted into the source collection with the same _id.

**$unwind by default drops documents with an empty array, null, or missing value** at the specified path. To keep them:

~~~javascript
db.orders.aggregate([
  {
    $unwind: {
      path: "$items",
      preserveNullAndEmptyArrays: true,
      includeArrayIndex: "itemIndex"
    }
  }
]);
~~~

With **preserveNullAndEmptyArrays: true**, documents without items can be retained in the result, but the unwound field and **itemIndex** value may have a different shape from documents containing actual array elements. You need to decide how to handle null/missing values when grouping or computing.

### 5.8. $group: Multiple Documents into Grouped Statistics

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: {
        $sum: "$items.qty"
      },
      lineCount: {
        $sum: 1
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Result:

~~~javascript
[
  { _id: "SKU-A", unitsSold: 3, lineCount: 2 },
  { _id: "SKU-B", unitsSold: 1, lineCount: 1 },
  { _id: "SKU-C", unitsSold: 5, lineCount: 2 }
]
~~~

In **$group**:

- **_id** is the **grouping key**, not necessarily the _id of the source document.
- **"$items.sku"** is a field-path expression computing the grouping key.
- **$sum** is an accumulator summing values across the documents belonging to the group.
- **$sum: 1** counts the number of input documents in the group.
- **$sum: "$items.qty"** sums qty.

**$group** can reduce thousands of documents down to a few group documents. It does not guarantee result order by default; if ordering is needed, add **$sort**.

### 5.9. $count: Counting Documents Passing Through the Stage

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $count: "paidOrders"
  }
]);
~~~

Result:

~~~javascript
[
  { paidOrders: 4 }
]
~~~

The **$count stage** returns one document carrying the count result if there are input documents. If the input pipeline is empty, the **$count stage** can return **no documents at all**, rather than always returning **{paidOrders:0}**. The application must account for this case when reading the cursor.

If you need to count **by each status**, use **$group** keyed by status instead of just **$count**.

### 5.10. Table for Identifying Cardinality Changes

| Stage | Role | Document count after stage |
|---|---|---|
| **$match** | Filters by condition. | Does not increase; can decrease to 0. |
| **$project** | Selects/computes fields. | Usually preserved. |
| **$set / $addFields** | Adds/replaces fields. | Usually preserved. |
| **$unset** | Removes fields. | Usually preserved. |
| **$sort** | Sorts order. | Preserved. |
| **$skip** | Skips first n documents. | Decreases or remains 0. |
| **$limit** | Allows at most n documents. | Decreases or preserved. |
| **$unwind** | Splits array. | Can increase or decrease. |
| **$group** | Groups documents. | Depends on number of groups; usually decreases. |
| **$count** | Counts entire stream. | 1 if input exists, 0 if input is empty. |
| **$lookup** | Adds joined data as an array. | Usually preserves document count in default form; can increase after unwind. |
| **$facet** | Processes multiple pipeline branches. | Produces one document containing result arrays when execution is valid. |

**Cardinality** is the number of documents at a step, while **shape** is the set of fields and structure of each document. When reading a pipeline, you must track both.

## 6. Shape Transformation Flow: A Later Stage Only Sees What the Previous Stage Outputs

### 6.1. Example of Losing a Field After $project

~~~javascript
db.orders.aggregate([
  {
    $project: {
      customerId: 1,
      status: 1
    }
  },
  {
    $match: {
      channel: "WEB"
    }
  }
]);
~~~

The **$project** stage does not keep the **channel** field, so in the next stage **channel no longer exists in the intermediate document**. Therefore, **$match: {channel:"WEB"}** cannot filter as intended and may return no documents.

More sensible way to write it:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      channel: "WEB"
    }
  },
  {
    $project: {
      customerId: 1,
      status: 1
    }
  }
]);
~~~

This case shows that **stage order is part of the semantics**, not just a performance concern.

### 6.2. Field Names Change in $group

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orders: { $sum: 1 }
    }
  },
  {
    $sort: {
      status: 1
    }
  }
]);
~~~

After **$group**, the grouping key is stored in **_id**, while the original **status** field is gone. Therefore, **$sort: {status:1}** does not sort by status as a reader might assume.

Sort by _id:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orders: { $sum: 1 }
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

Or rename it back:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orders: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      status: "$_id",
      orders: 1
    }
  },
  {
    $sort: {
      status: 1
    }
  }
]);
~~~

### 6.3. $set Does Not Remove Fields, Making It Easy to Use During Experimentation

When building a multi-step pipeline, you can temporarily use **$set** to create computed fields without dropping original fields yet:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: "$items"
      }
    }
  },
  {
    $match: {
      itemCount: { $gt: 1 }
    }
  }
]);
~~~

The second stage **$match** sees the **itemCount** field because the first stage added it. Once the logic is finalized, you can use **$project** at the end to trim down the result returned to the client.

## 7. Reading and Writing Aggregation Expressions

### 7.1. Constant and Field-Path Expressions

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      originalChannel: "$channel",
      literalChannel: "WEB",
      currentStatus: "$status"
    }
  }
]);
~~~

In an expression context:

- **"$channel"** retrieves the channel field value from the current document.
- **"WEB"** is a constant string literal.
- **"$status"** retrieves status from the current document.

To tell them apart:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      a: "$status",
      b: "status"
    }
  }
]);
~~~

**a** is a value like PAID/PENDING; **b** is always the string **"status"**.

### 7.2. Arithmetic with $add, $multiply, $divide

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      feeWithTax: {
        $multiply: [
          "$shippingFee",
          NumberDecimal("1.10")
        ]
      }
    }
  }
]);
~~~

The **$multiply** expression evaluates the **shippingFee field value** multiplied by a constant. The result is returned in the new field **feeWithTax**.

Expressions can be **nested**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      feePlusFive: {
        $add: [
          {
            $multiply: [
              "$shippingFee",
              NumberDecimal("1.10")
            ]
          },
          NumberDecimal("5.00")
        ]
      }
    }
  }
]);
~~~

MongoDB evaluates the inner expression first and then uses its result for the outer expression. This is still **one $project stage**, not two stages just because there are two operations.

### 7.3. Logic with $cond

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      paymentLabel: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "COMPLETED",
          "NOT_COMPLETED"
        ]
      }
    }
  }
]);
~~~

**$cond** is an expression consisting of:

1. Condition;
2. Value when condition is true;
3. Value when condition is false.

It does not drop documents. To fetch only PAID orders, use **$match**.

### 7.4. $ifNull for Handling Null or Missing Values

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      channel: {
        $ifNull: [
          "$channel",
          "UNKNOWN"
        ]
      }
    }
  }
]);
~~~

**$ifNull** provides a fallback value if the first expression is null or missing (and according to the semantics of the corresponding version). It is useful when data has optional fields.

You should not automatically fill defaults just to patch data if **null has a different business meaning from missing**. First clarify the field's contract.

### 7.5. $concat and $toUpper for String Processing

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      displayKey: {
        $concat: [
          "$tenantId",
          "-",
          { $toUpper: "$channel" }
        ]
      }
    }
  }
]);
~~~

For O101, **displayKey** is **"SHOP-A-WEB"**. If channel can be null/missing, handle it first because string operations have semantics around null and data types.

### 7.6. Type Checking and Conversion Expressions

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      dateType: {
        $type: "$createdAt"
      },
      createdYear: {
        $year: "$createdAt"
      }
    }
  }
]);
~~~

Here **$type** and **$year** are expressions. **$year** requires appropriate date/time data; if createdAt stores an invalid string, the pipeline may error. MongoDB does not automatically parse arbitrary date strings in every expression.

## 8. $match Uses Query Predicates; $expr Bridges to Aggregation Expressions

This is one of the most confusing areas.

### 8.1. Standard $match Condition

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: { $eq: "PAID" },
      tenantId: "SHOP-A"
    }
  }
]);
~~~

In **$match**, **$eq** is a **query operator**: it compares the status field with the value **"PAID"**.

### 8.2. $eq in Expression Form

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      isPaid: {
        $eq: ["$status", "PAID"]
      }
    }
  }
]);
~~~

Here **$eq** is an **aggregation expression** and takes an **array of two operands**. One operand is a field reference, and the other is a constant.

Comparison:

| Context | Syntax | Meaning |
|---|---|---|
| Query predicate in **$match** | **{status: {$eq:"PAID"}}** | Selects documents where status = PAID. |
| Expression in **$project** | **{$eq:["$status","PAID"]}** | Computes boolean true/false. |

### 8.3. $expr Enables Expressions Inside $match

Suppose another collection has two numeric fields **paidAmount** and **expectedAmount**. To filter documents where the two fields are equal:

~~~javascript
db.invoices.aggregate([
  {
    $match: {
      $expr: {
        $eq: [
          "$paidAmount",
          "$expectedAmount"
        ]
      }
    }
  }
]);
~~~

**$expr** is a **query operator** that allows using aggregation expressions to build filter conditions. In this case, **$eq** compares **two fields of the same document**.

If you do not need an expression comparing fields against each other and only want to filter status = PAID, the form **$match: {status:"PAID"}** is usually more concise, easier to read, and friendlier to queries/indexes. Do not use **$expr** just because its syntax looks general.

### 8.4. The $ Sign on a Field Name Is Not an Operation

~~~javascript
{
  $project: {
    total: {
      $add: [
        "$subtotal",
        "$shippingFee"
      ]
    }
  }
}
~~~

In an expression context, **"$subtotal"** is a field path. But in a filter:

~~~javascript
{ status: "PAID" }
~~~

**status** is the field name of a query predicate, while **"PAID"** is a literal. The same string can be interpreted differently depending on position.

## 9. $sum Can Be an Accumulator or an Expression

### 9.1. $sum in $group: Accumulator Across Multiple Documents

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
]);
~~~

Here **$sum** adds 1 for **each document entering the group**. It acts as an **accumulator**, aggregating values across multiple documents.

### 9.2. $sum in $project/$set: Expression on One Document's Data

~~~javascript
db.orders.aggregate([
  {
    $set: {
      quantities: {
        $map: {
          input: "$items",
          as: "line",
          in: "$$line.qty"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      totalUnits: {
        $sum: "$quantities"
      }
    }
  }
]);
~~~

In **$project**, **$sum** in expression form can sum **the numeric values in an array** of **a single document**. For O101, quantities = [2,1], totalUnits = 3. For O102, quantities = [1,3], totalUnits = 4.

Two different operations:

~~~text
$sum in $group:
  many documents -> 1 total value for a group

$sum in $project:
  one document's data -> 1 computed value
~~~

### 9.3. A Sum from an Array of Embedded Objects Using $map + $sum

To calculate each order's subtotal **without unwinding**, use:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      subtotal: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      subtotal: 1
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

Example subtotal values:

| Order | Breakdown | Subtotal |
|---|---|---:|
| O101 | 2 × 100 + 1 × 50 | 250 |
| O102 | 1 × 100 + 3 × 20 | 160 |
| O103 | 2 × 50 | 100 |
| O104 | 4 × 100 | 400 |
| O105 | 2 × 20 | 40 |
| O106 | 1 × 50 | 50 |
| O107 | No items | 0 |

The numbers above illustrate values and do not fully depict the BSON Decimal128 wrapper. In the examples where prices are stored using **NumberDecimal**, calculations execute according to MongoDB's numeric rules; when serializing to JSON/Java DTOs, the corresponding type must be preserved.

**$map** and **$multiply** are expressions nested inside the **$sum expression**, all residing inside the **$set stage**.

### 9.4. $sum on Documents After $unwind

The same requirement for revenue statistics by SKU can be expressed using **$unwind + $group**:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: {
        $sum: "$items.qty"
      },
      grossAmount: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPrice"
          ]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Result based on the sample data:

~~~text
SKU-A: unitsSold = 3, grossAmount = 300
SKU-B: unitsSold = 1, grossAmount = 50
SKU-C: unitsSold = 5, grossAmount = 100
~~~

This result **excludes shippingFee** because gross revenue per item is computed solely from qty × unitPrice. If business logic requires allocating shippingFee per SKU, an allocation rule must be defined rather than blindly adding shippingFee to every line item.

## 10. Variables in Expressions: $, $$, and $$ROOT

### 10.1. Field Path with a Single $

~~~javascript
"$customerId"
"$items.sku"
"$shippingFee"
~~~

In an expression context, **$fieldPath** notation retrieves the value of the field on the current document.

### 10.2. Expression Variables with Double $$

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: {
            $gte: [
              "$$line.unitPrice",
              NumberDecimal("50.00")
            ]
          }
        }
      }
    }
  }
]);
~~~

In **$filter**, **as: "line"** names a variable representing the element currently being evaluated. **"$$line.unitPrice"** references the unitPrice field of the line variable, unlike **"$items.unitPrice"**, which is a field path based on the current document.

Other expressions also use variables, such as **$map**, **$let**, and mechanisms with pipeline-defined variables.

### 10.3. The System Variable $$ROOT

**$$ROOT** generally refers to the root document at the **input of the current stage**, after transformations that occurred in preceding stages.

Example of keeping the entire document in a group:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      orders: {
        $push: "$$ROOT"
      }
    }
  }
]);
~~~

Each group will have **orders** as an array of the selected documents. With large datasets, **$push: "$$ROOT"** can produce very large group documents, exceeding the 16 MiB BSON limit. Only retain the necessary fields when collecting into an array to avoid hitting the limit.

### 10.4. The System Variable $$NOW

MongoDB provides the **$$NOW** system variable to reference the current time in aggregation. It is useful for computing document age, time-related conditions, and consistent reporting within a pipeline.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      ageMilliseconds: {
        $subtract: [
          "$$NOW",
          "$createdAt"
        ]
      }
    }
  }
]);
~~~

Note that **$subtract** between two Dates returns the time difference in milliseconds. Do not treat **$$NOW** as a JavaScript variable in mongosh; it is interpreted by MongoDB during aggregation.

### 10.5. $literal When You Need to Keep a String Starting with $

In an expression context, **"$PAID"** is interpreted as a field path. If you want to return the literal string **"$PAID"**, use **$literal**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      literalValue: {
        $literal: "$PAID"
      }
    }
  }
]);
~~~

When user input or configuration contains strings starting with **$**, be careful not to accidentally turn a literal into an unintended field/expression. Use query builders and validate input in the application.

## 11. A Complete Pipeline: From Orders to a Product Report

Goal: summarize items sold for **SHOP-A**, counting only **PAID** orders, computing total quantity and total line-item value, sorted by total value descending.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $unwind: "$items"
  },
  {
    $set: {
      lineAmount: {
        $multiply: [
          "$items.qty",
          "$items.unitPrice"
        ]
      }
    }
  },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: {
        $sum: "$items.qty"
      },
      grossAmount: {
        $sum: "$lineAmount"
      },
      orderIds: {
        $addToSet: "$_id"
      }
    }
  },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      unitsSold: 1,
      grossAmount: 1,
      distinctOrders: {
        $size: "$orderIds"
      }
    }
  },
  {
    $sort: {
      grossAmount: -1,
      sku: 1
    }
  }
]);
~~~

### 11.1. Stage 1: $match

Input: 7 orders.

Output: **4 orders**, namely O101, O102, O105, O107. O103 is excluded because it is CANCELLED, O104 because its tenant is SHOP-B, and O106 because it is PENDING.

### 11.2. Stage 2: $unwind

Input: 4 orders.

Output: **5 line documents**:

~~~text
O101 / SKU-A / qty 2 / unitPrice 100
O101 / SKU-B / qty 1 / unitPrice  50
O102 / SKU-A / qty 1 / unitPrice 100
O102 / SKU-C / qty 3 / unitPrice  20
O105 / SKU-C / qty 2 / unitPrice  20
~~~

O107 has an empty items array, so it produces no line document with **default $unwind**.

### 11.3. Stage 3: $set

Input: 5 line documents.

Output: still **5 line documents**, but each document has **lineAmount**:

~~~text
O101 / SKU-A / lineAmount 200
O101 / SKU-B / lineAmount  50
O102 / SKU-A / lineAmount 100
O102 / SKU-C / lineAmount  60
O105 / SKU-C / lineAmount  40
~~~

**$multiply is an expression** evaluated inside the **$set stage**.

### 11.4. Stage 4: $group

Input: 5 line documents.

Output: **3 grouped documents** by SKU.

~~~javascript
[
  {
    _id: "SKU-A",
    unitsSold: 3,
    grossAmount: NumberDecimal("300.00"),
    orderIds: ["O101", "O102"]
  },
  {
    _id: "SKU-B",
    unitsSold: 1,
    grossAmount: NumberDecimal("50.00"),
    orderIds: ["O101"]
  },
  {
    _id: "SKU-C",
    unitsSold: 5,
    grossAmount: NumberDecimal("100.00"),
    orderIds: ["O102", "O105"]
  }
]
~~~

**Note:** the order of elements in **orderIds** produced by **$addToSet** is not guaranteed. The snippet above only illustrates the values present in the set and does not promise the actual output order.

### 11.5. Stage 5: $project

Input: 3 grouped documents.

Output: 3 documents with **sku** renamed from **_id**, adding **distinctOrders** = size of the orderIds set, and removing **orderIds** and **_id**.

### 11.6. Stage 6: $sort

Input: 3 documents.

Output:

~~~javascript
[
  {
    sku: "SKU-A",
    unitsSold: 3,
    grossAmount: NumberDecimal("300.00"),
    distinctOrders: 2
  },
  {
    sku: "SKU-C",
    unitsSold: 5,
    grossAmount: NumberDecimal("100.00"),
    distinctOrders: 2
  },
  {
    sku: "SKU-B",
    unitsSold: 1,
    grossAmount: NumberDecimal("50.00"),
    distinctOrders: 1
  }
]
~~~

This is a classic example of two parallel transformation streams:

~~~text
CARDINALITY:
  7 -> 4 -> 5 -> 5 -> 3 -> 3 -> 3

SHAPE:
  Order
    -> Filtered Order
    -> Order + one item
    -> Order + one item + lineAmount
    -> Summary by SKU
    -> Report DTO
    -> Sorted Report DTO
~~~

If you only remember one thing when designing aggregations, track the **document count** and the **remaining fields** after each stage.

## 12. Accumulators and Expressions in $group

### 12.1. $group Uses a Grouping Key and Accumulators

~~~javascript
{
  $group: {
    _id: "$customerId",
    count: { $sum: 1 },
    totalUnits: { $sum: "$items.qty" }
  }
}
~~~

Here **$group** categorizes documents by customerId, and the accumulators compute statistics for each group.

If **items** is an array of objects that has not been unwound, **"$items.qty"** can yield an array value / path traversal across an array. The **$sum accumulator in $group** does not automatically iterate deeply over every element like a per-line total quantity problem, and array operands have their own semantics. To compute per line item, use **$unwind** beforehand or calculate a **per-document sum using a $map/$sum expression** before grouping.

Do not merely swap syntax without identifying **the unit being summed**: an order, a line item, a customer, or a group.

### 12.2. $avg, $min, $max, $push, $addToSet

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      totalOrders: { $sum: 1 },
      firstCreatedAt: { $min: "$createdAt" },
      lastCreatedAt: { $max: "$createdAt" },
      customerIds: { $addToSet: "$customerId" }
    }
  }
]);
~~~

Meaning:

- **$sum:** total number of documents in the group.
- **$min:** smallest value.
- **$max:** largest value.
- **$addToSet:** set of distinct values, **order not guaranteed**.
- **$push:** collects values into an array; order depends on the input stream if ordering is relied upon.

If you need deterministic ordering, proactively design **$sort** in the appropriate position and understand accumulator behavior. Do not rely on incidental ordering of group results.

### 12.3. $group with _id: null

~~~javascript
db.orders.aggregate([
  {
    $match: { tenantId: "SHOP-A" }
  },
  {
    $group: {
      _id: null,
      totalOrders: { $sum: 1 }
    }
  }
]);
~~~

**_id: null** means grouping all input documents into **one single group**, not grouping by a field named null. If the input has no documents, the result depends on stages/accumulators and typically produces no group document.

## 13. $lookup, $facet, and Special Shape-Changing Stages

### 13.1. $lookup Typically Adds a Joined Result Array

Suppose there is a **customers** collection:

~~~javascript
db.customers.insertMany([
  { _id: "C01", displayName: "Alice" },
  { _id: "C02", displayName: "Bob" },
  { _id: "C03", displayName: "Charlie" },
  { _id: "C04", displayName: "Dana" }
]);
~~~

Join customer information into orders:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customerInfo"
    }
  },
  {
    $project: {
      _id: 1,
      customerId: 1,
      customerInfo: 1
    }
  }
]);
~~~

**$lookup** in its basic form places matches into **customerInfo** as an array. If each order matches one customer, the array has one element. If there is no match, the array is usually empty.

~~~javascript
{
  _id: "O101",
  customerId: "C01",
  customerInfo: [
    { _id: "C01", displayName: "Alice" }
  ]
}
~~~

A **$lookup** usually does not increase the document count of the outer stream because it attaches an array to each input document. If followed by **$unwind: "$customerInfo"**, the document count can change according to the number of joined elements.

### 13.2. $facet Creates Multiple Parallel Processing Branches on the Same Input Stream

For example, if you want to return both statistics by status and total order count:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A"
    }
  },
  {
    $facet: {
      byStatus: [
        {
          $group: {
            _id: "$status",
            count: { $sum: 1 }
          }
        }
      ],
      totals: [
        {
          $count: "totalOrders"
        }
      ]
    }
  }
]);
~~~

**$facet** is a **stage**, while **byStatus** and **totals** are branch names. Each branch contains **a sub-pipeline**, meaning its own array of stages.

The result has the shape:

~~~javascript
[
  {
    byStatus: [
      { _id: "PAID", count: 4 },
      { _id: "CANCELLED", count: 1 },
      { _id: "PENDING", count: 1 }
    ],
    totals: [
      { totalOrders: 6 }
    ]
  }
]
~~~

The order of elements in **byStatus** is not guaranteed without a sort. **$facet** is not an expression, even though it contains sub-pipelines with nested stages and expressions.

**Resource note:** $facet has memory and output document size limits; do not assume **allowDiskUse** allows $facet to produce an unbounded result document.

### 13.3. $replaceRoot or $replaceWith Replaces the Current Document

Suppose after **$lookup**, each document has a **customerInfo** field containing an object. If you want to replace the entire current document with another object, you can use **$replaceRoot** or **$replaceWith** with an expression that returns a valid document.

These stages change the **shape** drastically. If the expression returns null or a non-document value in an unsupported case, the pipeline can error. Therefore, you should not put them into a pipeline just to rename a field; **$project/$set** is usually clearer.

## 14. Stages Can Stream, Block, or Increase Intermediate Volume

Conceptually, a pipeline is a stream of documents passing through stages. However, **not every stage processes each document and emits a result immediately**.

### 14.1. Streaming-Like Stages

Stages such as **$match** or **$project** can process one document sequentially and emit the corresponding document, depending on the execution plan and optimizations.

~~~text
Input Doc 1 -> $match -> Output Doc 1 / dropped
Input Doc 2 -> $match -> Output Doc 2 / dropped
...
~~~

### 14.2. Blocking Stages

Stages such as **$group** and **$sort** often have to collect or maintain state across many documents before they can emit the final results:

~~~text
Input: many documents
     |
     v
$group builds groups / accumulators
     |
     v
Output: grouped statistics
~~~

This can consume more memory and time than simple filtering stages. **$sort** can benefit from an index or optimization with **$limit** under appropriate conditions, so actual behavior is determined by the query planner.

### 14.3. $unwind Can Cause Document Explosion

If each order has 1,000 items and there are 100,000 orders, **$unwind** can generate up to **100 million intermediate line documents** if all arrays are populated and unfiltered.

MongoDB does not necessarily materialize all of them simultaneously in every case, but the processing volume can grow enormously.

To reduce cost:

1. **$match early** on indexed source conditions.
2. Only unwind when processing **per element** is needed.
3. Use **$map/$filter/$sum** on arrays within each document if the requirement can be solved without unwinding.
4. Avoid building overly large output arrays with **$push: "$$ROOT"** or **$facet**.
5. Distinguish the statistical unit properly so you do not count the same order multiple times after unwinding.

### 14.4. Memory Limits and allowDiskUse

Some stages can require substantial memory. MongoDB enforces a limit of about **100 MB** for stages with significant memory requirements in common versions/contexts; some stages can **spill temporary data to disk** if permitted.

In mongosh:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "SHOP-A" } },
    { $group: { _id: "$customerId", count: { $sum: 1 } } },
    { $sort: { count: -1 } }
  ],
  {
    allowDiskUse: true
  }
);
~~~

**allowDiskUse: true** allows supported stages to use temporary files when needed instead of being strictly bounded to RAM. Starting in MongoDB 6.0, the server added the **allowDiskUseByDefault** configuration affecting default behavior in corresponding cases.

However:

- Not every stage can spill to disk; **$facet** has its own limits.
- **allowDiskUse** does not remove the **16 MiB limit on a single output BSON document**.
- Temporary files consume disk I/O and storage space.
- A pipeline producing an overly large output can still fail.
- Memory rules vary by stage and version, so check the documentation for the server in use.

### 14.5. Stage Count Limit

MongoDB imposes a limit on the number of stages in a pipeline, commonly **1,000 stages**. Do not split a simple calculation into thousands of stages or construct unbounded pipelines from user input.

When a pipeline becomes too long, review the data model, calculation expressions, number of sub-pipelines, and processing architecture instead of just trying to raise a configuration threshold.

## 15. Stage Ordering and Optimization

### 15.1. Filter Early to Reduce Data Volume

The pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQty: { $sum: "$items.qty" }
    }
  }
]);
~~~

filters down to four orders before unwinding. If **$unwind** occurs first and filtering happens later, the database may have to process additional items from excluded orders, even if the logical result might still be identical in some cases.

### 15.2. You Cannot Arbitrarily Swap Any Stage

For example:

~~~javascript
[
  { $sort: { createdAt: -1 } },
  { $limit: 10 }
]
~~~

means "the 10 newest documents" according to the sort.

Whereas:

~~~javascript
[
  { $limit: 10 },
  { $sort: { createdAt: -1 } }
]
~~~

means "take at most 10 documents from the current stream and then sort them." The two pipelines can return different results.

Similarly, a **$match** on a field computed in **$set** cannot be arbitrarily moved before **$set**, because that field does not yet exist on the source documents.

### 15.3. MongoDB Has a Query Optimizer

MongoDB can automatically reorder or combine steps under certain conditions to optimize performance while preserving semantics; for example, pushing certain **$match** conditions ahead of **$project/$set**, or coalescing **$sort** with **$limit** in some cases.

Therefore:

- **The stage array you write** expresses the intended logic.
- **The actual execution plan** may be transformed by the optimizer.
- Do not deduce the exact number of data materializations solely from the stage array syntax.
- Use **explain()** and actual metrics to understand how MongoDB executes it.

Do not rely on an undocumented internal execution order to write business logic that depends on side effects.

## 16. Using explain to Read a Pipeline's Execution Plan

Example:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      count: { $sum: 1 }
    }
  },
  {
    $sort: {
      count: -1
    }
  }
]);
~~~

**explain** helps observe the query plan and execution metrics. Key information can include:

- **COLLSCAN / IXSCAN** or the corresponding execution stage: how is the data source searched?
- **totalDocsExamined:** number of source documents read/examined.
- **totalKeysExamined:** number of index keys examined.
- **nReturned:** number of documents returned within the scope of the corresponding counter.
- **Pipeline stages:** group, sort, unwind processing, execution timing, and spill activity if reported.

Depending on the MongoDB version and execution engine, the explain response structure may vary. Do not write rigid tools assuming every version has a single JSON path for metrics.

### 16.1. Which Stages Benefit from Indexes?

In many cases:

- An initial **$match at the start of the pipeline** can benefit from an index on the filtered fields.
- **$sort** can benefit from an index if stage order, sort pattern, and query align.
- **$group** has special index optimizations in certain queries, but not every group is directly accelerated by an index by default.
- **$unwind** typically creates many intermediate documents and does not "automatically index" the output.

Example of creating an index to serve finding orders by tenant/status:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "ix_tenant_status" }
);
~~~

Then re-measure explain on a representative dataset. With a collection of only seven documents in the lab, the query planner may choose a scan due to low cost; do not evaluate a production index solely from a small example.

## 17. Aggregation in the MongoDB Java Sync Driver

The MongoDB Java Sync Driver allows building pipelines from **List<Bson>**, using builders such as **Aggregates**, **Filters**, **Accumulators**, and **Sorts**.

### 17.1. Example: Matching and Grouping by SKU

~~~java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public final class OrdersAggregationExample {
    public static void run(MongoDatabase database) {
        MongoCollection<Document> orders =
                database.getCollection("orders");

        List<Bson> pipeline = List.of(
                Aggregates.match(
                        Filters.and(
                                Filters.eq("tenantId", "SHOP-A"),
                                Filters.eq("status", "PAID")
                        )
                ),
                Aggregates.unwind("$items"),
                Aggregates.group(
                        "$items.sku",
                        Accumulators.sum("unitsSold", "$items.qty")
                ),
                Aggregates.sort(
                        Sorts.ascending("_id")
                )
        );

        AggregateIterable<Document> results =
                orders.aggregate(pipeline);

        for (Document row : results) {
            System.out.println(row.toJson());
        }
    }
}
~~~

The code has **four stages**:

1. **Aggregates.match(...)** builds the **$match stage**.
2. **Aggregates.unwind("$items")** builds the **$unwind stage**.
3. **Aggregates.group(...)** builds the **$group stage**, using the accumulator **Accumulators.sum** inside.
4. **Aggregates.sort(...)** builds the **$sort stage**.

**Filters.eq** is a builder for query predicates, while **Accumulators.sum** represents an accumulator inside a group. Having distinct Java builders helps clarify part of the stage/expression difference.

### 17.2. Expressions in Java Using BSON Document

A nested expression can be constructed manually using **Document**:

~~~java
import com.mongodb.client.model.Aggregates;
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

Bson calculatedField = Aggregates.addFields(
        new org.bson.Field<>(
                "lineAmount",
                new Document(
                        "$multiply",
                        List.of("$items.qty", "$items.unitPrice")
                )
        )
);
~~~

**Aggregates.addFields** builds the **$addFields** stage, whereas **new Document("$multiply", ...)** represents the expression assigned to the **lineAmount** field value.

In production systems, builders can be wrapped into reusable functions, but you must clearly distinguish:

~~~text
List<Bson>       -> list of STAGES
Bson stage       -> a single stage
Document expr    -> expression used INSIDE a stage
~~~

### 17.3. Reading a Cursor Instead of Unbounded Result Materialization

~~~java
for (Document row : orders.aggregate(pipeline)) {
    processRow(row);
}
~~~

The application can process each result from the cursor. You should not default to calling **into(new ArrayList<>())** and holding millions of results in RAM if the problem can be streamed.

A MongoDB aggregation cursor does not mean every stage streams right from the start: stages like **$sort/$group** may still have to process large amounts of data before returning results.

### 17.4. allowDiskUse with the Java Driver

~~~java
orders.aggregate(pipeline)
        .allowDiskUse(true)
        .forEach(document -> System.out.println(document.toJson()));
~~~

Depending on the driver/server version, the API allows configuring disk spilling in supported stages. Do not use allowDiskUse as the default workaround for pipelines with unbounded output.

## 18. Aggregation in Spring Data MongoDB

Spring Data provides **Aggregation**, **AggregationOperation**, **AggregationResults**, and builders for many stages. The goal is to represent MongoDB pipelines in Java with entity mapping support.

### 18.1. Example: match, unwind, group, sort

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.bson.Document;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;
import org.springframework.data.domain.Sort.Direction;

public final class OrderReportService {
    private final MongoTemplate mongoTemplate;

    public OrderReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void printUnitsBySku() {
        Aggregation pipeline = newAggregation(
                match(
                        Criteria.where("tenantId").is("SHOP-A")
                                .and("status").is("PAID")
                ),
                unwind("items"),
                group("items.sku")
                        .sum("items.qty").as("unitsSold"),
                sort(Direction.ASC, "_id")
        );

        AggregationResults<Document> result =
                mongoTemplate.aggregate(
                        pipeline,
                        "orders",
                        Document.class
                );

        for (Document row : result.getMappedResults()) {
            System.out.println(row.toJson());
        }
    }
}
~~~

The builders **match**, **unwind**, **group**, and **sort** create **stages**. **Criteria** describes the query predicate inside match, while **sum(...).as(...)** configures the accumulator inside group.

The example calls **getMappedResults()** to simplify the illustration; for large results, consider an appropriate streaming/cursor API instead of holding all documents in a List.

### 18.2. $project Stage with Expressions in Spring Data

~~~java
Aggregation pipeline = newAggregation(
        project("customerId", "status")
                .and("shippingFee")
                .as("fee")
);
~~~

This is a **project/rename field** operation without arithmetic computation. To use complex expressions, Spring Data has various builders grouped by operator categories and supports the corresponding expression forms. When using newer MongoDB expressions not yet supported by the current builder version, consider a **custom AggregationOperation** with a BSON Document.

### 18.3. Mapping and Field Names After Each Stage

In Spring Data, Java property names can map to different BSON names via the **@Field** annotation. However, after **$group**, **$project**, or **$replaceRoot**, the output document no longer has the original entity's shape.

Therefore:

- Choose the right **input collection/entity mapping**.
- Determine the field path at each stage after renames.
- Use a **result DTO** when the output is a report rather than the original entity.
- Note that **_id** after group typically contains the grouping key, not the order ID.
- Check Decimal128 types and conversions to Java **BigDecimal** or the corresponding type.

### 18.4. Do Not Confuse Query Builders and Expression Builders

**Criteria.where("status").is("PAID")** describes a predicate. It is not a boolean expression returning an **isPaid** field in project. To compute isPaid, use an **aggregation comparison expression** or a suitable custom expression.

The mindset is the same as mongosh: **query predicate** to filter, **expression** to compute, **stage** to orchestrate the flow.

## 19. Read Aggregation vs. Write Aggregation

### 19.1. Normal Read Pipelines Do Not Modify the Source Collection

~~~javascript
db.orders.aggregate([
  {
    $set: {
      summaryFlag: true
    }
  }
]);
~~~

This pipeline **only creates the summaryFlag field in the output documents**; it does not save that field to each order in the collection.

The name **$set** can be confusing because MongoDB also has the **$set update operator**:

~~~javascript
db.orders.updateOne(
  { _id: "O101" },
  {
    $set: {
      summaryFlag: true
    }
  }
);
~~~

The **updateOne** command actually writes changes to the collection if matched and valid.

### 19.2. Updating with an Aggregation Pipeline

MongoDB allows certain update operations to use an **aggregation pipeline** as the update specification. For example:

~~~javascript
db.orders.updateOne(
  { _id: "O101" },
  [
    {
      $set: {
        itemCount: {
          $size: "$items"
        }
      }
    }
  ]
);
~~~

In this example, **$set is an aggregation stage allowed in an update pipeline**, and because the entire pipeline is inside **updateOne()**, the result is written back to the matching document.

**Important:** update pipelines only support **a subset of stages**, such as **$set/$addFields**, **$project/$unset**, and **$replaceRoot/$replaceWith** per the documentation. You cannot put arbitrary read stages like **$group** or **$lookup** into an update pipeline and expect MongoDB to accept it.

### 19.3. $out and $merge Write Pipeline Results

The Aggregation Framework provides **$out** and **$merge** to write pipeline results to a target collection according to specific rules. They are **pipeline stages**, not expressions.

Conceptual difference:

- **$out:** writes pipeline results into a target collection according to stage semantics and version/topology rules.
- **$merge:** merges results with a target collection, with configuration for handling matched/unmatched documents.

These stages have write side effects and carry constraints on pipeline placement and execution. Do not use them carelessly in lab exercises because they can affect target data. A pipeline containing only **$match/$project/$group** does not automatically write summary documents to a new collection.

## 20. Using Pipelines for Paginated Reports and Multiple Result Sets

### 20.1. Pagination with sort, skip, limit

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: 1
    }
  },
  { $skip: 2 },
  { $limit: 2 },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      status: 1
    }
  }
]);
~~~

For large datasets, **deep skip** can be expensive because the database has to discard many results. When possible, consider **keyset/range pagination** on appropriately ordered and indexed fields.

### 20.2. Facet for Page Data and Total Count

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A"
    }
  },
  {
    $facet: {
      page: [
        { $sort: { createdAt: -1, _id: 1 } },
        { $skip: 0 },
        { $limit: 3 },
        { $project: { _id: 1, status: 1, createdAt: 1 } }
      ],
      totals: [
        { $count: "count" }
      ]
    }
  }
]);
~~~

The result is **one document** with two fields **page** and **totals**, each containing an array. This is an example of $facet sub-pipelines, which can be convenient for an API returning both page data and total counts.

However, you must control:

- $facet memory limits;
- the 16 MiB output document size limit;
- the impact of sort and skip;
- having an appropriate indexed query before $facet;
- consistency/latency per the API's requirements.

Do not assume $facet is faster than two separate queries in every workload.

## 21. Common Conceptual and Syntax Mistakes

### 21.1. Placing an Expression Directly as a Stage

~~~javascript
// Wrong:
db.orders.aggregate([
  { $multiply: ["$qty", "$price"] }
]);
~~~

**$multiply** is only an expression. Place it inside **$project/$set** or a stage with an appropriate expression position.

### 21.2. Using $match as a Boolean-Returning Expression

~~~javascript
// Wrong:
{
  $project: {
    isPaid: {
      $match: { status: "PAID" }
    }
  }
}
~~~

Compute booleans using **$eq** or **$cond**. Filter documents using a **$match stage**.

### 21.3. Confusing $gt Query Syntax and $gt Expression Syntax

~~~javascript
// Predicate in $match:
{ $match: { qty: { $gt: 5 } } }

// Expression in $project:
{ $project: { aboveFive: { $gt: ["$qty", 5] } } }
~~~

One takes the comparison value as a field operator, while the other takes two operands in an array.

### 21.4. Referencing a Field Removed by $project

~~~javascript
[
  { $project: { status: 1 } },
  { $match: { tenantId: "SHOP-A" } }
]
~~~

If tenantId is not retained after project, the match stage no longer sees that value. Place match before project or keep tenantId until it is no longer needed.

### 21.5. Counting Orders After Unwinding Items

~~~javascript
[
  { $unwind: "$items" },
  { $count: "orders" }
]
~~~

This pipeline counts **line documents**, not the original number of orders. To count orders, use **$count before unwind**, or group by order ID / **$addToSet** and measure distinct counts with the right semantics.

### 21.6. Assuming $group Keeps All Source Fields

~~~javascript
{
  $group: {
    _id: "$customerId",
    totalOrders: { $sum: 1 }
  }
}
~~~

After group, the output only contains **_id** and **totalOrders**; it does not automatically keep **status**, **createdAt**, or **items** from the source documents.

### 21.7. Relying on $group Output Order

**$group does not guarantee output order**. To sort by key or total, add **$sort** after group.

### 21.8. Assuming $unwind Only Transforms Fields

**$unwind** can turn one document into many documents or drop documents with empty arrays. It changes **cardinality**, not just shape.

### 21.9. Using $$line Outside Variable Scope

Variables declared by **$map/$filter/$let** are only valid within the scope of that corresponding expression. Do not use **"$$line.qty"** in another expression without a proper **line** variable.

### 21.10. Assuming the $set Stage Updates the Database Automatically

In **aggregate()**, $set only modifies intermediate documents. If you want to write, use **updateOne/updateMany** with valid updates or intentional output stages.

### 21.11. Allowing Users to Submit Arbitrary Pipelines

A reporting API should not directly accept an unvalidated stage array from clients. It could trigger overly expensive queries or inject write-capable stages if permissions allow. Validate fields, operators, result limits, timeouts, and access permissions.

### 21.12. Reading an Aggregation Cursor as an In-Memory List

Aggregation results are usually returned via a cursor. Applications should choose an appropriate iteration approach; do not load millions of documents into RAM if batches of results can be processed incrementally.

## 22. Step-by-Step Practice Exercises

### Exercise 1 — Observing the Filter Stage

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  }
]);
~~~

Record the number of remaining documents and the list of _id values. Why were O103, O104, and O106 excluded?

### Exercise 2 — Adding an Expression to Count Items

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: "$items"
      }
    }
  },
  {
    $project: {
      _id: 1,
      itemCount: 1
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

Answer: how many stages are there? How many expressions are there? Which stages preserve the document count and which change the shape?

### Exercise 3 — Replacing $set with $project

Rewrite the example so that it only returns **_id**, **customerId**, and **itemCount**. Explain why the **items** field is no longer present in the result.

### Exercise 4 — Counting Orders Before and After Unwind

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $count: "orders" }
]);
~~~

Compared with:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $unwind: "$items" },
  { $count: "lines" }
]);
~~~

The results are **4 orders** and **5 lines**, respectively. Explain the difference using a cardinality diagram.

### Exercise 5 — Computing Subtotal per Order Without Unwinding

Use **$map + $multiply + $sum** inside **$set**, followed by **$project** to return _id/subtotal. For O101 the expected subtotal is 250; O107 has an empty items array so its subtotal is 0.

### Exercise 6 — Quantity Statistics by SKU

Write a pipeline consisting of:

1. **$match:** SHOP-A, PAID;
2. **$unwind:** items;
3. **$group:** by items.sku and sum qty;
4. **$sort:** by _id.

Verify the results: SKU-A = 3, SKU-B = 1, SKU-C = 5.

### Exercise 7 — Distinguishing Predicates and Expressions

Write:

- A **$match** that takes only PAID orders using a query predicate;
- A **$project** that creates an **isPaid** field using the **$eq** expression;
- A **$match using $expr** that compares two numeric fields of a hypothetical same document.

Explain the differences in shape and cardinality.

### Exercise 8 — Analyzing a Stage Ordering Bug

Given the pipeline:

~~~javascript
[
  { $project: { customerId: 1 } },
  { $match: { status: "PAID" } }
]
~~~

Identify the logical bug, fix it, and explain which stage is allowed to move earlier while still preserving semantics.

### Exercise 9 — Multi-Branch Querying with $facet

On SHOP-A orders, write a **$facet** that returns:

- **byStatus:** order count statistics by status;
- **totals:** total number of orders;
- **recent:** the two newest orders by createdAt/_id.

Is the result of $facet one document or multiple documents? What data type does each branch return?

### Exercise 10 — Finding a Performance Issue

Suppose there are one million orders, each averaging 50 items. A pipeline starts by **$unwind**ing everything and only then **$match**ing **tenantId/status**.

Propose a different order and explain why it can reduce the number of line documents that must be processed. Then state how to use **explain** and indexes to evaluate it.

## 23. Review Questions

1. How do a **stage** and an **expression** differ in terms of input/output unit and syntactic position?
2. Why can **$add** not be placed directly as a stage element inside **aggregate([...])**?
3. How does **$match** differ from **$project** in its effect on document count and output fields?
4. When should you use **$set** instead of **$project**?
5. After **$unwind** on a 5-element array, how many intermediate documents does one source document normally become?
6. Why does default **$unwind** drop orders with an empty items array?
7. How does **$group** change **_id** and the remaining fields?
8. How does **$sum** inside **$group** differ from the **$sum** expression inside **$project**?
9. What is the difference between the **$gt** query operator and the **$gt** aggregation expression?
10. When is **$expr** used inside **$match**?
11. How does the notation **"$status"** differ from **"status"** in an expression position?
12. Where is **$$line** defined in **$map**, and what is its valid scope?
13. How does **$$ROOT** help in a group, and why can **$push: "$$ROOT"** cause issues?
14. Why can **$sort** and **$limit** not be arbitrarily swapped?
15. What field type does a standard **$lookup** produce? When does cardinality increase?
16. Which parts of **$facet** are sub-pipelines and which parts are expressions?
17. If a pipeline has a **$set stage**, is the source collection modified?
18. Does **allowDiskUse** remove the 16 MiB limit on a result document?
19. Why does an **aggregation cursor** not imply every stage emits results immediately?
20. How can you observe whether MongoDB uses an index at the start of an aggregation pipeline?

## 24. Mental Model Summary

A MongoDB pipeline is a **sequence of stages**, where each stage receives and passes along a stream of documents:

~~~text
db.collection.aggregate([
  { $stage1: ... },
  { $stage2: ... },
  { $stage3: ... }
])
~~~

Inside stages, MongoDB uses expressions to compute values:

~~~text
STAGE:  $project
    |
    +-- FIELD:  total
           |
           +-- EXPRESSION: $add
                  |
                  +-- FIELD PATH: "$subtotal"
                  +-- FIELD PATH: "$shippingFee"
~~~

Three questions to ask at every step:

1. **How does the document count change?** Filtered down, preserved, multiplied, or grouped?
2. **How does the shape of each document change?** Which fields remain, which are new, and which were renamed?
3. **Is the keyword here a stage or an expression?** Does it control document flow or merely compute a value inside a stage?

Once you clearly distinguish these three questions, complex pipelines involving **$match**, **$project**, **$unwind**, **$group**, **$lookup**, **$facet**, and nested expressions become much easier to read and control.

### MongoDB and Java Documentation for Further Reading

- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — processing flow model and optimization.
- [Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/) — catalog of pipeline stages.
- [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/) — catalog of expressions and accumulators.
- [$match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) and [$expr](https://www.mongodb.com/docs/manual/reference/operator/query/expr/) — query predicates and conditional expressions.
- [$project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) and [$set](https://www.mongodb.com/docs/manual/reference/operator/aggregation/set/) — controlling document shape and field values.
- [$unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) and [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — changing cardinality and grouping.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — memory, stage count, and result limits.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — how the MongoDB optimizer can transform plans.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Aggregates, Accumulators APIs, and aggregate cursors.
- [Spring Data MongoDB Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — building aggregations with Java/Spring Data.

When designing a report or API with the Aggregation Framework, start from the **input data**, define the **information to return**, and write each stage following the data flow. Do not just piece together operators with similar names: **stages create processing steps, expressions compute values, and context determines how an operator is interpreted**.