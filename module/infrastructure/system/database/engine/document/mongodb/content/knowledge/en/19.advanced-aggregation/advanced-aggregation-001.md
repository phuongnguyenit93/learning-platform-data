# Combining Collections with $lookup and Subquery Pipelines in MongoDB

## 1. When a Screen Needs Data from Multiple Collections

MongoDB often encourages document design oriented around read patterns: data with tightly coupled lifecycles that are frequently read together can be embedded in a single document. However, not every relationship is suitable for embedding. A customer may have thousands of orders; orders have different lifecycles, access permissions, and update frequencies than the customer profile. In such cases, storing **customers** and **orders** as two separate collections may make more sense.

Suppose an application needs to display:

- Customer name.
- Number of paid orders for the customer.
- Total value of paid orders.
- Two most recent paid orders.

If we only read the customers collection, we do not have order data. If we only read orders, we do not have the customer name. **$lookup** in the aggregation pipeline helps retrieve data from another collection and attach the results to each document passing through the pipeline.

Basic example:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  }
]);
~~~

Conceptually, MongoDB takes **customerCode** from each customer, finds orders with a matching **customerCode**, and adds an **orders Array** to the customer document.

However, if customerCode is unique only **within each tenant**, a simple join on customerCode could pull data from another tenant. Additionally, fetching **all** orders just to count or sum them wastes resources and easily produces overly large result arrays. These scenarios are why we need **$lookup with a subquery pipeline**.

### After This Lesson, You Will Be Able To

1. Write an equality join **$lookup** using **localField/foreignField**.
2. Understand **left outer join** semantics, Array results, and documents with no related records.
3. Write a **correlated subquery** using **let**, **$$variable**, **$match**, and **$expr**.
4. Combine equality, range, status, and sort conditions inside the $lookup **pipeline**.
5. Return only the needed fields or aggregate inside the subquery using **$group**.
6. Use **$unwind**, **$size**, **$arrayElemAt**, and **$ifNull** properly with join results.
7. Read **explain** output and design indexes for the lookup target collection.
8. Avoid multi-tenant security bugs, data duplication, cardinality inflation, and document size limit overflows.

> Examples run in **mongosh**, using a dedicated lab database **mongo_lookup_lab**. The lesson clearly distinguishes between simple joins and multi-field conditional joins; it does not assume MongoDB always optimizes equivalently to a relational database with SQL JOIN.

## 2. How Does $lookup Work?

### 2.1. Input Collection and Joined Collection

In the pipeline:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "matchedOrders"
    }
  }
]);
~~~

**customers** is the input collection to aggregate; **orders** is the collection queried by $lookup.

| Property | Role |
| --- | --- |
| **from** | Name of the collection to retrieve related data from, in the same database as the aggregation under standard syntax |
| **localField** | Field in the document currently passing through the pipeline |
| **foreignField** | Field in documents belonging to the collection specified in **from** |
| **as** | Name of the Array field used to store the matched documents |

Each customer result looks like:

~~~javascript
{
  _id: "cust-001",
  customerCode: "C001",
  name: "An",
  matchedOrders: [
    { _id: "ord-001", customerCode: "C001", amount: NumberDecimal("100.00") },
    { _id: "ord-002", customerCode: "C001", amount: NumberDecimal("50.00") }
  ]
}
~~~

Order fields in the illustrative example have been shortened for readability. When using a simple $lookup without an inner projection, the join result is typically **all matching order documents in full**.

### 2.2. Why Is It Called a Left Outer Join?

$lookup preserves the input document **even when no matching documents are found in the target collection**. When there are no matches, the field in **as** is an empty Array.

~~~javascript
{
  _id: "cust-003",
  customerCode: "C003",
  name: "Chi",
  matchedOrders: []
}
~~~

This behavior is close to a SQL **left outer join**, except that MongoDB results are **embedded as an Array**, rather than automatically multiplying each parent record into multiple output rows like a typical SELECT JOIN.

If you want to represent each customer–order pair as a separate document, you can use **$unwind** after $lookup. When unwinding without preserving empty arrays, customers with no orders disappear from the output. This is similar to switching from a join that retains every left-side record to one that only keeps matched pairs.

### 2.3. Two Forms of $lookup

**Form 1 — Simple equality join**:

~~~javascript
{
  $lookup: {
    from: "orders",
    localField: "customerCode",
    foreignField: "customerCode",
    as: "orders"
  }
}
~~~

**Form 2 — Join with subpipeline and correlated variables**:

~~~javascript
{
  $lookup: {
    from: "orders",
    let: {
      outerCode: "$customerCode",
      outerTenant: "$tenantId"
    },
    pipeline: [
      {
        $match: {
          $expr: {
            $and: [
              { $eq: ["$customerCode", "$$outerCode"] },
              { $eq: ["$tenantId", "$$outerTenant"] }
            ]
          }
        }
      }
    ],
    as: "orders"
  }
}
~~~

A subpipeline is an aggregation pipeline **that runs on the lookup target collection** in the context of the input document. Variables from the outer document are declared in **let** and referenced with a double dollar sign **$$** inside the inner pipeline expressions.

## 3. Preparing a Reproducible Lab Dataset

The dataset intentionally has **customerCode C001 appearing in two different tenants**, so that a simple join on customerCode exposes the bug of joining across tenants.

### 3.1. Data Design

Collection **lab_customers**:

| _id | tenantId | customerCode | name | Notes |
| --- | --- | --- | --- | --- |
| cust-001 | t001 | C001 | An | Has orders |
| cust-002 | t001 | C002 | Bình | Has orders |
| cust-003 | t001 | C003 | Chi | No orders |
| cust-004 | t002 | C001 | Dung | **Shares customerCode with tenant t001** |
| cust-005 | t002 | C004 | Em | Has one pending order |
| cust-006 | t001 | C005 | Hà | No orders |

Collection **lab_orders** has 12 orders. Documents join to a customer by the **tenantId/customerCode pair**, not by customerCode alone.

### 3.2. mongosh Data Seed Script

Run as a single block:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_lookup_lab");
  const customers = lab.getCollection("lab_customers");
  const orders = lab.getCollection("lab_orders");
  const tag = "lookup-join-v1";

  // Clean up only the lesson dataset, do not drop collection/database.
  customers.deleteMany({ dataset: tag });
  orders.deleteMany({ dataset: tag });

  customers.insertMany([
    {
      _id: "cust-001", dataset: tag, tenantId: "t001",
      customerCode: "C001", name: "An", tier: "bronze"
    },
    {
      _id: "cust-002", dataset: tag, tenantId: "t001",
      customerCode: "C002", name: "Bình", tier: "gold"
    },
    {
      _id: "cust-003", dataset: tag, tenantId: "t001",
      customerCode: "C003", name: "Chi", tier: "silver"
    },
    {
      _id: "cust-004", dataset: tag, tenantId: "t002",
      customerCode: "C001", name: "Dung", tier: "gold"
    },
    {
      _id: "cust-005", dataset: tag, tenantId: "t002",
      customerCode: "C004", name: "Em", tier: "bronze"
    },
    {
      _id: "cust-006", dataset: tag, tenantId: "t001",
      customerCode: "C005", name: "Hà", tier: "silver"
    }
  ]);

  const orderRows = [
    // id, tenant, customerCode, status, amount, day, items
    ["ord-001", "t001", "C001", "paid",      "100.00",  1, ["A"]],
    ["ord-002", "t001", "C001", "pending",    "50.00",  2, ["B"]],
    ["ord-003", "t001", "C002", "paid",      "200.00",  3, ["A", "C"]],
    ["ord-004", "t001", "C002", "refunded",   "75.00",  4, ["D"]],
    ["ord-005", "t002", "C001", "paid",      "300.00",  5, ["E"]],
    ["ord-006", "t002", "C004", "pending",   "125.00",  6, ["A"]],
    ["ord-007", "t002", "C001", "paid",       "25.00",  7, ["B"]],
    // An order with no matching customer: intentional orphan data.
    ["ord-008", "t001", "MISSING", "paid",    "30.00",  8, ["Z"]],
    ["ord-009", "t001", "C001", "paid",      "150.00",  9, ["A"]],
    ["ord-010", "t001", "C002", "paid",      "150.00", 10, ["C"]],
    ["ord-011", "t002", "C001", "cancelled",  "90.00", 11, ["E"]],
    ["ord-012", "t001", "C002", "pending",    "20.00", 12, ["B"]]
  ];

  orders.insertMany(
    orderRows.map(([id, tenant, code, status, amount, day, skus]) => ({
      _id: id,
      dataset: tag,
      tenantId: tenant,
      customerCode: code,
      status: status,
      amount: NumberDecimal(amount),
      createdAt: new Date(Date.UTC(2026, 0, day, 8, 0, 0)),
      items: skus.map(sku => ({
        sku: sku,
        quantity: NumberInt(1)
      }))
    }))
  );

  // Index to support finding customers by tenant and business code.
  customers.createIndex(
    { dataset: 1, tenantId: 1, customerCode: 1 },
    { name: "ux_lab_customer_code_per_tenant", unique: true }
  );

  // Index on the target collection for $lookup examples.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, customerCode: 1,
      status: 1, createdAt: -1, _id: 1
    },
    { name: "ix_lab_order_join_status_time" }
  );

  // Single-field index for the customerCode-only join example.
  orders.createIndex(
    { customerCode: 1 },
    { name: "ix_lab_order_code_only" }
  );

  printjson({
    customers: customers.countDocuments({ dataset: tag }),
    orders: orders.countDocuments({ dataset: tag }),
    t001Orders: orders.countDocuments({
      dataset: tag, tenantId: "t001"
    }),
    t002Orders: orders.countDocuments({
      dataset: tag, tenantId: "t002"
    })
  });
})();
~~~

**Expected result:** **6 customers**, **12 orders**, of which **8 orders belong to t001** and **4 orders belong to t002**. Documents have fixed IDs. After practicing document modifications, re-run the seed script to restore state.

**Note:** the script deletes and re-inserts by dataset tag, but is not inside a transaction; use only in a dedicated lab environment. The unique index in the lab is defined to enforce uniqueness of **(dataset, tenantId, customerCode)** and will affect all corresponding documents in the same collection.

### 3.3. Reference Results

| Customer | Tenant | Total tenant-matched orders | Paid orders | Paid total |
| --- | --- | ---: | ---: | ---: |
| An / C001 | t001 | 3 | 2 | 250.00 |
| Bình / C002 | t001 | 4 | 2 | 350.00 |
| Chi / C003 | t001 | 0 | 0 | 0.00 |
| Dung / C001 | t002 | 3 | 2 | 325.00 |
| Em / C004 | t002 | 1 | 0 | 0.00 |
| Hà / C005 | t001 | 0 | 0 | 0.00 |

Order **ord-008** does not join to any customer because customerCode MISSING does not exist in t001. It remains a valid document in the orders collection per the lab dataset and can be detected via a $lookup in the orders → customers direction.

## 4. Simple Equality Join: localField and foreignField

### 4.1. Basic Join

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        localField: "customerCode",
        foreignField: "customerCode",
        as: "joinedOrders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        customerCode: 1,
        joinedCount: { $size: "$joinedOrders" },
        orderIds: "$joinedOrders._id"
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Key result:

| Customer t001 | joinedCount with **customerCode alone** | Correct count per tenant |
| --- | ---: | ---: |
| An / C001 | **6** | **3** |
| Bình / C002 | 4 | 4 |
| Chi / C003 | 0 | 0 |
| Hà / C005 | 0 | 0 |

An receives **6** orders because C001 appears in both t001 (ord-001, ord-002, ord-009) and t002 (ord-005, ord-007, ord-011). This is a **join logic bug and potentially a security bug**: filtering the input collection to tenant t001 does not mean the lookup target collection is automatically restricted to tenant t001.

### 4.2. When Is an Equality Join Sufficient?

The **localField/foreignField** form is appropriate when:

- The join key is sufficiently unique or accurate across the entire target dataset under consideration.
- You do not need to apply multiple combined conditions from the outer document.
- The related document set is reasonably sized.
- Returning the full target documents is necessary and does not create overly large results.

For example, if orders store **customerId** which is the **globally unique _id** of customers, the join:

~~~javascript
{
  $lookup: {
    from: "lab_customers",
    localField: "customerId",
    foreignField: "_id",
    as: "customer"
  }
}
~~~

is generally clearer than joining on a display code that may collide across tenants. In the lab, orders use customerCode to demonstrate the necessity of a composite join key.

### 4.3. Missing or Null Fields in an Equality Join

With equality joins, MongoDB treats a **missing localField** as null when matching, and a **missing foreignField** can also be treated as null. This can cause documents missing the join key to link with other documents that are also missing the key or have null, producing unexpected results.

Do not use an equality $lookup on fields that may be null/missing without analyzing the data. If the relationship is only valid when the code exists and has the right type, add appropriate filter conditions and validation on both the input data and the target collection.

## 5. Correlated Subquery: let, $$variable, and $expr

### 5.1. What Is a Correlated Variable?

A **correlated subquery** uses values from the outer document to filter data in the target collection. Inside $lookup:

- **let** declares variables from the input document.
- **$$variableName** references that variable inside the subpipeline.
- **$expr** allows $match to compare **aggregation expressions**, including fields of the order and correlated variables.

Correct example for a multi-tenant system:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          { $project: { _id: 1, status: 1, amount: 1 } }
        ],
        as: "orders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        customerCode: 1,
        orderCount: { $size: "$orders" },
        orderIds: "$orders._id"
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

**Expected result:** An **3** orders, Bình **4**, Chi **0**, Hà **0**. Customers in t001 do not receive orders from t002 even though customerCode matches.

### 5.2. How to Read Each Part

~~~javascript
let: {
  code: "$customerCode",
  tenant: "$tenantId"
}
~~~

Here **"$customerCode"** and **"$tenantId"** are field paths in the current customer document; **code** and **tenant** are variable names for the subpipeline.

Inside the pipeline:

~~~javascript
{
  $eq: ["$customerCode", "$$code"]
}
~~~

The left operand **"$customerCode"** is the field of the **order**. The right operand **"$$code"** is the value coming from the **customer currently being processed**.

Similarly:

~~~javascript
{
  $eq: ["$tenantId", "$$tenant"]
}
~~~

compares the order's tenant with the customer's tenant.

**A single $** denotes a field path in an expression; **a double $$** denotes an aggregation variable. Mixing them up causes wrong query semantics or syntax errors.

### 5.3. Why Must $expr Be Used Inside $match?

In a subpipeline, a standard query filter:

~~~javascript
{ $match: { status: "paid" } }
~~~

can compare against the constant **"paid"** without $expr.

However, when comparing against an outer variable:

~~~javascript
{
  $match: {
    $expr: {
      $eq: ["$customerCode", "$$code"]
    }
  }
}
~~~

$expr is required to evaluate both operands as expressions. Writing **{customerCode: "$$code"}** in a normal query predicate does not compare against the variable as intended.

A useful rule of thumb: **use regular query predicates for constant conditions whenever possible; use $expr for conditions that depend on let variables**. This also helps the optimizer apply indexes more favorably for those parts of the filter.

## 6. Combining Equality Join with a Pipeline

### 6.1. Why Use Both localField/foreignField and pipeline?

Starting in MongoDB 5.0, the **concise correlated subquery** syntax allows using **localField/foreignField** together with **pipeline** to express the basic equality join part and then add additional conditions.

Example:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        localField: "customerCode",
        foreignField: "customerCode",
        let: { tenant: "$tenantId" },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $eq: ["$tenantId", "$$tenant"]
              }
            }
          },
          { $project: { _id: 1, amount: 1, createdAt: 1 } }
        ],
        as: "paidOrders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        paidCount: { $size: "$paidOrders" },
        paidOrderIds: "$paidOrders._id"
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Results for t001:

| Customer | paidCount |
| --- | ---: |
| An | 2 |
| Bình | 2 |
| Chi | 0 |
| Hà | 0 |

In this query:

- localField/foreignField joins on customerCode.
- The tenant variable in **let** prevents cross-tenant joins.
- **status: "paid"** is a constant filter inside the subpipeline.
- **$project** keeps only the fields needed for the report.

**Version note:** If compatibility with an older MongoDB version that does not support combining localField/foreignField with pipeline is needed, use the full **let + pipeline + $expr** form from Section 5. Check the deployed server version before using newer syntax in an application.

### 6.2. When to Use Which Form?

| Scenario | Appropriate Choice |
| --- | --- |
| Joining on a stable key with no extra filtering | localField/foreignField |
| Joining on one key plus status, range, projection | Equality join + pipeline if server supports it |
| Joining on multiple correlated fields such as tenant + code | let + $expr; or equality join + pipeline for extra conditions |
| Need to aggregate inside the target collection | $lookup with a pipeline containing $group |
| Need a few most recent documents | $lookup pipeline with $sort + $limit + $project |
| Need to detect missing related records | $lookup followed by $size/$match or reverse-direction join |

**There is no need to pick the most complex syntax** when an equality join on _id is sufficient. Conversely, never use an overly simple form when the join key is not unique or when security/isolation requirements apply.

## 7. Fetching Only Paid Orders and the Two Most Recent Orders

A customer screen typically does not need all orders; it only needs the **two most recent orders** and a few concise fields. A $lookup pipeline can filter, sort, limit, and project directly in the target collection.

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          { $sort: { createdAt: -1, _id: 1 } },
          { $limit: 2 },
          {
            $project: {
              _id: 1,
              amount: 1,
              createdAt: 1
            }
          }
        ],
        as: "recentPaidOrders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        recentPaidOrders: 1
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Expected results:

- **An:** ord-009 (150.00) then ord-001 (100.00).
- **Bình:** ord-010 (150.00) then ord-003 (200.00).
- **Chi and Hà:** empty recentPaidOrders Array.

**$sort before $limit** is necessary so that "two most recent orders" has deterministic semantics. Here, descending createdAt and ascending _id act as a tie-breaker when multiple orders share the same timestamp; limiting without sorting offers no guarantee that the two chosen orders are the latest.

### 7.1. Distinguishing Limit Inside Subpipeline vs. Limit Outside

Placing:

~~~javascript
{ $limit: 2 }
~~~

**inside $lookup.pipeline** means **at most two orders per customer** when the subquery executes in each outer document's context.

Placing:

~~~javascript
{ $limit: 2 }
~~~

**after $lookup in the main pipeline** means returning at most two **customers** (or two documents currently in the main pipeline), without separately limiting the number of orders inside each Array.

These two positions produce very different semantics and workloads.

### 7.2. Do Not Limit Before Defining the Correct Set

If a subpipeline does:

~~~javascript
{ $limit: 2 },
{ $match: { status: "paid" } }
~~~

then you inspect only two arbitrary first orders and then filter for paid; valid paid orders appearing after them may be excluded. The standard order to get the two most recent paid orders is:

~~~text
$match by tenant, customer, status
    ->
$sort createdAt DESC
    ->
$limit 2
    ->
$project required fields
~~~

In practice, the optimizer may reorder certain transformations when safe; however, pipeline authors must ensure the **intended semantics** first rather than relying on server optimizations.

## 8. Aggregating Inside the Subpipeline: Avoid Pulling the Whole Orders Array Out

### 8.1. When Only Counts and Totals Are Needed

If the requirement is "number of paid orders and total paid amount per customer", pulling all orders out and running $size/$sum on the Array consumes memory and can produce huge documents.

We can place **$group directly inside $lookup.pipeline**:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          {
            $group: {
              _id: null,
              paidCount: { $sum: 1 },
              paidTotal: { $sum: "$amount" },
              newestPaidAt: { $max: "$createdAt" }
            }
          },
          { $project: { _id: 0 } }
        ],
        as: "paidSummaryArray"
      }
    },
    {
      $set: {
        paidSummary: {
          $ifNull: [
            { $arrayElemAt: ["$paidSummaryArray", 0] },
            {
              paidCount: 0,
              paidTotal: NumberDecimal("0.00"),
              newestPaidAt: null
            }
          ]
        }
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        paidSummary: 1
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Explanation:

1. Each customer triggers matching the exact paid orders within the same tenant.
2. **$group: {_id:null}** produces at most **one summary document** per customer.
3. The **as** field of $lookup **is always an Array**, so paidSummaryArray either contains one summary object or is an empty Array.
4. **$arrayElemAt(..., 0)** extracts the first element; if none exists, **$ifNull** supplies a default object.
5. **$project** drops the intermediate array and returns only the needed statistics.

Logical result:

| Customer | paidCount | paidTotal | newestPaidAt |
| --- | ---: | ---: | --- |
| An | 2 | 250.00 | 2026-01-09 |
| Bình | 2 | 350.00 | 2026-01-10 |
| Chi | 0 | 0.00 | null |
| Hà | 0 | 0.00 | null |

For table readability, dates are shown as YYYY-MM-DD; actual BSON Date values retain full time and timezone info. In real applications, the definition of **revenue** must be explicit: whether paid is included, whether refunded is subtracted, and whether currencies are converted.

### 8.2. Why Doesn't $group Return a count=0 Row When There Is No Data?

When the subpipeline has no matching orders, **$group receives no input documents and therefore produces no output document**. Thus paidSummaryArray is **[]**, not **[{paidCount:0}]**. If the application always expects a statistics object, you must handle the empty Array as shown using $arrayElemAt + $ifNull or an equivalent construct.

### 8.3. Comparing Pulling Data Out vs. Aggregating at the Source

| Approach | Benefits | Risks |
| --- | --- | --- |
| Lookup all orders, compute in app | Simple to prototype, full details available | Large data transfer; result array can be very long |
| Lookup with $project | Shrinks size of each returned order | Can still have thousands of orders in the Array |
| Lookup with $sort + $limit | Suits screens needing only a few latest records | Cannot compute totals across all orders if only a few records are kept |
| Lookup with $group | Returns compact counts/sums/min/max | Has grouping cost; must handle empty groups |
| Build a pre-aggregated read model | Efficient if dashboard is accessed very frequently | Must stay in sync when orders change; latency/consistency trade-offs to design |

Do not fetch the 2 most recent orders and compute "total amount of all orders": **limit changes the dataset being summed**. If the UI needs both a 2-order list and the total across all orders, use two separate purpose-built $lookup stages, or a single subpipeline using **$facet** when appropriate.

## 9. Multiple Calculations in One Subpipeline with $facet

Suppose each customer needs both **paid totals** and the **two most recent paid orders**:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001",
        customerCode: "C001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          {
            $facet: {
              totals: [
                {
                  $group: {
                    _id: null,
                    count: { $sum: 1 },
                    amount: { $sum: "$amount" }
                  }
                },
                { $project: { _id: 0 } }
              ],
              latest: [
                { $sort: { createdAt: -1, _id: 1 } },
                { $limit: 2 },
                { $project: { _id: 1, amount: 1, createdAt: 1 } }
              ]
            }
          }
        ],
        as: "details"
      }
    },
    {
      $project: {
        _id: 0,
        name: 1,
        details: 1
      }
    }
  ]).toArray();
~~~

For An, details contains one document holding:

~~~text
totals = [{count: 2, amount: Decimal128(250.00)}]
latest = [ord-009, ord-001] with the selected fields
~~~

Note that **$facet** outputs a single document containing Arrays for each branch, so $lookup still places that document inside the **details** Array. You can add $set/$project to reshape it into an API-friendly object.

Use $facet when you need multiple kinds of statistics from the same filtered order set, keeping in mind aggregation resource limits and output document size. Do not assume $facet is faster than two independent $lookup stages in every version or workload; measure it.

## 10. $unwind After $lookup: Turning Linked Arrays into Rows

### 10.1. Each Customer–Order Pair as One Output Document

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: { tenant: "$tenantId", code: "$customerCode" },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              $expr: {
                $and: [
                  { $eq: ["$tenantId", "$$tenant"] },
                  { $eq: ["$customerCode", "$$code"] }
                ]
              }
            }
          },
          { $project: { _id: 1, status: 1, amount: 1 } }
        ],
        as: "orders"
      }
    },
    { $unwind: "$orders" },
    {
      $project: {
        _id: 0,
        customer: "$name",
        orderId: "$orders._id",
        status: "$orders.status",
        amount: "$orders.amount"
      }
    },
    { $sort: { customer: 1, orderId: 1 } }
  ]).toArray();
~~~

From t001, there are **7 orders attached to existing customers**: 3 for An and 4 for Bình. Chi and Hà have no orders so they are dropped by default $unwind. Order ord-008 has code MISSING so it also does not appear when joining from customers.

### 10.2. Preserving Customers Without Orders

Specify:

~~~javascript
{
  $unwind: {
    path: "$orders",
    preserveNullAndEmptyArrays: true
  }
}
~~~

With this option, customers with an empty orders Array **are preserved** in the pipeline output. The **orders** field on those documents will be missing after unwind; use **$ifNull** when building the display projection:

~~~javascript
{
  $project: {
    name: 1,
    orderId: {
      $ifNull: ["$orders._id", null]
    }
  }
}
~~~

If you replace the default $unwind in the previous example with preserveNullAndEmptyArrays, there will be **9 output documents**: 7 customer–order pairs and 2 customers without orders.

### 10.3. $unwind Can Multiply Rows and Corrupt Totals

If a customer has 100 orders, after $unwind it becomes 100 documents. Subsequently:

~~~javascript
{ $group: { _id: "$tenantId", count: { $sum: 1 } } }
~~~

counts **rows after unwind**, no longer the number of customers. To count distinct customers, group by customer first or use **$addToSet** on customer IDs and then take the size, considering set size and optimization behavior.

Similarly, if each customer has a **creditLimit** field, summing creditLimit after unwind will add it repeatedly per order. This is a common **data granularity** bug when joining and then grouping.

### 10.4. Filter Inside the Subpipeline or After $unwind?

Example:

~~~text
Approach A:
  $lookup all orders -> $unwind -> $match status paid

Approach B:
  $lookup only paid orders -> $unwind
~~~

Both approaches can return the same customer–paid order pairs when customers without orders are not preserved, but **cost and semantics when preserving empty rows differ**. B generally shrinks the intermediate array and gives the foreign index an opportunity to filter early.

If you need to display customers without paid orders as well, put the **paid status condition inside $lookup.pipeline**, then use **preserveNullAndEmptyArrays:true**. If you filter status paid **after unwind** using $match, customers with no paid orders will disappear.

## 11. Reversing $lookup to Find Orphan Orders

From customers → orders, orders without a referenced customer do not appear. To detect missing linked documents, start from **orders** and $lookup into customers.

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_orders")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_customers",
        let: {
          tenant: "$tenantId",
          code: "$customerCode"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              $expr: {
                $and: [
                  { $eq: ["$tenantId", "$$tenant"] },
                  { $eq: ["$customerCode", "$$code"] }
                ]
              }
            }
          },
          { $project: { _id: 1, name: 1 } }
        ],
        as: "matchingCustomers"
      }
    },
    {
      $match: {
        matchingCustomers: { $size: 0 }
      }
    },
    {
      $project: {
        _id: 1,
        tenantId: 1,
        customerCode: 1,
        amount: 1
      }
    }
  ]).toArray();
~~~

**Expected result:** only **ord-008**, belonging to t001 and having customerCode **MISSING**.

This is a form of **anti-join**: keeping left-side documents that find no matching document on the right side.

### 11.1. $lookup Does Not Enforce Foreign Keys

MongoDB does not automatically reject inserting an order with a non-existent customerCode merely because the application uses $lookup to read customer details. If referential integrity must be guaranteed, you need application-layer workflows, appropriate transactions, or an alternative data model.

Finding an orphan order does not mean it should be deleted: the customer may have been anonymized, migrated across systems, or had a bad reference. Investigate the root cause and data retention policy before fixing it.

## 12. Variable Scope in Subpipelines and Syntax Pitfalls

### 12.1. Variables Are Meaningful Only in Their Declared Context

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    let: { outerCode: "$customerCode" },
    pipeline: [
      {
        $match: {
          $expr: {
            $eq: ["$customerCode", "$$outerCode"]
          }
        }
      }
    ],
    as: "orders"
  }
}
~~~

**$$outerCode** is the customer value from the outer pipeline, not a field named outerCode on the order.

If you do not need to declare variables, use localField/foreignField for a simpler join. Avoid creating unused variables because they make queries harder to read.

### 12.2. $expr Is Not Required for Every Stage in a Subpipeline

Inside a subpipeline, you can use $$ variables anywhere an aggregation expression is accepted. For example:

~~~javascript
{
  $project: {
    _id: 1,
    amount: 1,
    sourceCustomerCode: "$$outerCode"
  }
}
~~~

In **$project**, new field values are evaluated as expressions, so **$$outerCode** can be used directly. However, inside **$match** query predicates, use **$expr** to compare against variables.

### 12.3. Multiple Levels of Nested $lookup

A subpipeline can contain other supported stages, including nested $lookup stages depending on server capabilities. However, each nesting level increases lookup count and query plan complexity. When three or four relationships must be read sequentially, consider:

- Reversing the query direction to start from a small, selective set.
- Using projections to reduce intermediate data.
- Embedding stable data or denormalizing frequently read fields.
- Building a dedicated read model/aggregation for critical pages.
- Checking outer/inner variable semantics and version limitations before using.

Do not recreate a multi-level JOIN tree just because every component can technically be joined with $lookup.

## 13. Indexes and $lookup Performance

### 13.1. Indexes on the Foreign Collection Matter

An equality $lookup:

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    localField: "customerCode",
    foreignField: "customerCode",
    as: "orders"
  }
}
~~~

may need to look up orders by customerCode for **each input customer**. An index on **foreignField** typically avoids scanning the entire orders collection on every lookup. The lab includes **ix_lab_order_code_only** to illustrate this case.

For the tenant-safe correlated subquery:

~~~javascript
{
  $match: {
    dataset: "lookup-join-v1",
    status: "paid",
    $expr: {
      $and: [
        { $eq: ["$tenantId", "$$tenant"] },
        { $eq: ["$customerCode", "$$code"] }
      ]
    }
  }
}
~~~

a candidate compound index on orders is:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  customerCode: 1,
  status: 1,
  createdAt: -1,
  _id: 1
}
~~~

This order puts commonly used equality conditions first, followed by createdAt to support time-based filtering/sorting. However, **you cannot assume every $expr comparison will always use an index**. Verify on your actual server version and dataset.

### 13.2. When Can $expr Use an Index?

Inside a $lookup pipeline, **$eq, $lt, $lte, $gt, $gte** operators inside **$expr** can leverage an index on the target collection in supported cases, especially when comparing a **field to a value that is constant within the subquery context**.

Variables **$$code/$$tenant** resolved from the outer document can be treated as bound values for that subquery execution, but you should not infer that every complex expression form is sargable.

Key limitations to note:

- Comparing **two fields from the same target document** generally does not get the same index benefit as comparing a field to a constant.
- If a **let** variable resolves to an empty or missing value, index usage may be restricted.
- For $expr comparisons noted in the $lookup documentation, **multikey indexes** are not used for those comparisons in the same way as standard scalar B-tree indexes.
- Some conditions also have restrictions with **partial/sparse indexes**, server versions, and pipeline shapes.
- Stage order, filters, sorts, and data distribution affect the actual plan.

If customerCode is simply a non-null scalar String, indexing the foreign field on the appropriate key is usually simpler than building complex conversion expressions inside $expr. Do not wrap the foreign field key path in **$toString** arbitrarily if doing so prevents index usage.

### 13.3. $match Before $lookup Reduces Join Invocations

Compare two pipelines:

~~~javascript
// A: join all customers then filter to one tenant.
[
  { $lookup: { from: "lab_orders", localField: "customerCode",
               foreignField: "customerCode", as: "orders" } },
  { $match: { tenantId: "t001" } }
]

// B: filter customers before joining.
[
  { $match: { tenantId: "t001" } },
  { $lookup: { from: "lab_orders", localField: "customerCode",
               foreignField: "customerCode", as: "orders" } }
]
~~~

With large workloads, pattern B reduces the number of input documents reaching $lookup. MongoDB can optimize and safely reorder certain stages, but **writing the input $match explicitly before $lookup** makes the scope clear to readers and avoids relying on the optimizer to "guess" security filters.

**However**, an outer tenant $match **does not replace** the tenant condition **inside the join**. The two-tenant C001 scenario in the lab shows why both are required.

### 13.4. Use Projection/Limit, but Understand Their Cost

A $lookup that matches thousands of orders and returns full documents can incur:

- Many index key and document reads.
- Large result arrays inside each customer.
- High network/serialization cost when returning the entire array to an API.
- Exceeding the output BSON document limit if the Array grows too large.

Therefore:

- **$match** precisely to exclude unneeded orders.
- **$project** only the fields actually used.
- **$sort + $limit** when only a few latest orders are needed.
- **$group** when only count/sum/avg/min/max are needed.
- **Paginate the orders collection directly** when users need to browse long histories.

Do not use $lookup to load an entire one-to-many relationship just because the application needs a **paidCount**.

## 14. Reading explain Output for Pipelines with $lookup

### 14.1. Hands-On Example

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .explain("executionStats")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: { tenant: "$tenantId", code: "$customerCode" },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$tenantId", "$$tenant"] },
                  { $eq: ["$customerCode", "$$code"] }
                ]
              }
            }
          },
          { $project: { _id: 1, amount: 1 } }
        ],
        as: "paidOrders"
      }
    },
    {
      $project: {
        name: 1,
        paidCount: { $size: "$paidOrders" }
      }
    }
  ]);
~~~

Displayed numbers/stages may vary by MongoDB version and query engine. When the output provides statistics for $lookup, inspect:

| Metric / Concept | Question to Answer |
| --- | --- |
| **nReturned** | How many outer documents are returned after the stages? |
| **totalDocsExamined** | Are too many documents being read on the source or target? |
| **totalKeysExamined** | Are many index keys being scanned? |
| **indexesUsed** | Which index did the foreign collection use, when reported? |
| **collectionScans** | Is a collection scan happening inside the lookup? |
| **IXSCAN / COLLSCAN** | Is the data source accessed via an index or a scan? |
| **executionTimeMillisEstimate** | Per-stage time estimate if provided by explain |
| **FETCH, SORT** | Is it fetching documents or sorting outside an index? |

Do not declare a $lookup "indexed" just because the outer collection shows IXSCAN; the **foreign collection** must also be checked. Likewise, an index on orders does not guarantee a fast query if the outer pipeline feeds millions of customers into the join.

### 14.2. MongoDB Can Optimize $lookup with $unwind

In certain cases, the optimizer can optimize the sequence:

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    localField: "customerCode",
    foreignField: "customerCode",
    as: "orders"
  }
},
{ $unwind: "$orders" },
{ $match: { "orders.status": "paid" } }
~~~

by coalescing operations into the lookup execution to reduce intermediate data. Optimizer details vary by version and pipeline conditions. **Do not use this optimization as an excuse to omit the tenant condition in the join**, and still write clear pipelines to preserve semantics, especially when using preserveNullAndEmptyArrays.

### 14.3. SBE Mode and Version Changes

Some MongoDB versions can execute certain equality $lookup operations using the **slot-based execution engine (SBE)** with corresponding stages/plans, though not all subpipeline shapes are supported the same way. When a query involves subpipelines, sharding, or other characteristics, the optimizer may pick a different mechanism.

When upgrading MongoDB, compare **query plans, actual latency, and keys/docs examined**, rather than relying on matching a fixed stage name to judge performance.

## 15. Boundaries, Limits, and Differences from SQL JOIN

### 15.1. $lookup Always Produces an Array

Even when foreignField is unique and at most one document matches, **as** is still an Array containing at most one object. If the application expects an object:

~~~javascript
{
  $set: {
    customer: { $arrayElemAt: ["$customerMatches", 0] }
  }
}
~~~

handle the empty Array with $ifNull if an explicit object/null is required. Do not assume a unique index causes $lookup to automatically return an object.

### 15.2. $lookup Is Not a Full Outer Join

$lookup preserves documents from the input collection and attaches matching info from the target collection. It does not automatically return documents that **exist only in the target collection** without a corresponding outer document.

To find orphan orders, reverse the direction as in Section 11. If a full-outer-join-style report across two sources is needed, design a different pipeline (e.g., combining an additional appropriate data branch); do not treat a single $lookup as a full outer join.

### 15.3. Both Collections Must Be in the Appropriate Database Scope

In standard $lookup syntax, **from** is a collection name in the same database where the aggregation runs. You cannot simply put a string **"otherDatabase.collection"** in from and expect a supported SQL-like cross-database join.

If data lives in another database/cluster, consider changing the access pattern, integrating at the application layer, replicating a read model, or using a dedicated solution rather than assuming $lookup directly handles every relationship.

### 15.4. Sharding and MongoDB Versions

Starting in **MongoDB 5.1**, $lookup supports a sharded **from** collection under the deployment conditions described in the documentation. A cross-shard $lookup may have to read data across multiple shards if conditions do not allow efficient routing. For production designs, check:

- Server version and support for $lookup on sharded foreign collections.
- Shard key and routing conditions / selectivity.
- Whether same-tenant data is distributed favorably.
- Inter-shard network load, merger resources, and latency.
- Specific limitations when using transactions and complex pipelines.

Do not assume lab results on a standalone/replica set match performance on a sharded cluster.

### 15.5. Do Not Use $out or $merge Inside $lookup.pipeline

The $lookup subpipeline **cannot contain $out or $merge**. A $lookup is for **reading and combining data**, not for writing subpipeline results directly to another collection.

In certain versions/features, a subpipeline may start with **$search** or **$searchMeta** as the first stage under supported conditions; this is a special case and does not change the rule against $out/$merge inside $lookup.

If you need to build a materialized view/read model, design an aggregation/job at the appropriate level and plan data synchronization.

### 15.6. Result Size Limits

MongoDB has a **16 MiB limit per BSON document**. $lookup attaches a potentially large Array to each input document; if the result array grows too large, intermediate or final pipeline documents can exceed the limit or consume excessive memory.

**allowDiskUse** in aggregation allows certain stages to spill to disk under supported conditions, but **it does not make a 30 MiB BSON document valid**. This is why you should group/project/limit inside the subquery and paginate when a one-to-many relationship has many elements.

## 16. Designing Around Real Query Patterns

### 16.1. When to Embed Instead of $lookup?

Suppose a customer always displays **contact name** and **default shipping address**, two attributes that change rarely and share the customer lifecycle. Embedding them in customer can eliminate joins on read.

Conversely, orders typically:

- Can grow without bound over time.
- Have independent status and frequent updates.
- Need separate searching/sorting/pagination.
- Have different retention and audit rules from customers.

Therefore, separating orders and using a separate query or $lookup when statistics are needed may be a better fit. There is no "always use $lookup" or "always embed" rule; choose based on **cardinality, access patterns, data lifecycle, and update frequency**.

### 16.2. If a Screen Only Needs a Customer's Order List

Instead of starting from customers and running $lookup to fetch hundreds of orders, once the customer is authenticated:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_orders")
  .find({
    dataset: "lookup-join-v1",
    tenantId: "t001",
    customerCode: "C001"
  })
  .sort({ createdAt: -1, _id: 1 })
  .limit(10)
  .toArray();
~~~

Querying orders directly is usually simpler and easier to paginate when a long list is needed. Customer metadata can be read with a separate query by _id/key pair, or a relevant customer name snapshot can be stored on the order if auditing requires it.

### 16.3. If a Dashboard Needs Metrics Updated Every Second

A dashboard displaying paidCount and paidTotal across millions of customers on every load can trigger a huge number of subqueries. Options to consider:

- Filter/paginate customers before lookup if displaying only one page and ranking does not depend on joined data.
- Aggregate orders by customer in a pipeline **starting from orders** and then join customer metadata.
- Maintain a **summary collection** per tenant/customer with a reliable update mechanism.
- Precompute via batch jobs if real-time data is not required.

If the screen ranks by **paidTotal**, you must not limit customers before computing paidTotal and treat that as the system-wide top customers. The semantically correct order is to compute the ranking metric across the appropriate full set, then sort and limit.

## 17. Common Errors and How to Handle Them

| Error / Symptom | Cause | Resolution |
| --- | --- | --- |
| Customer t001 receives orders from t002 | Join only uses customerCode without constraining tenant | Join on the tenant/customerCode pair; validate tenant on both sides |
| $lookup returns an empty Array | No matching target documents or mismatched key types | Check keys, tenant, orphan data, and filter conditions |
| $lookup returns an array even with only one customer | $lookup semantics always produce an Array | Use $arrayElemAt + $ifNull or $unwind as appropriate |
| Cannot read outer variable in $match | Used $code instead of $$code, or missing $expr | Declare let and compare inside $expr |
| Wrong two most recent orders returned | $limit before $sort or no deterministic order | Place $match, $sort, then $limit inside the subpipeline |
| Total amount only sums the two latest orders | $limit shrank the set before $group | Group over the full paid set or split into two branches |
| All customers without orders disappear | Default $unwind drops empty Arrays | Use preserveNullAndEmptyArrays if they should be kept |
| Customer count is multiplied after $unwind | Each order produces an extra output document | Identify granularity before $group |
| $lookup is slow despite outer index | Foreign collection lacks an appropriate index | Inspect plan and add indexes on foreign keys/filters |
| $expr does not use index as expected | Complex expression, field-to-field, multikey, or null variable | Check $expr limitations and explain; normalize keys |
| Orders array exceeds size limit | Unbounded one-to-many join | Filter, group, project, limit, or paginate orders directly |
| Incorrect business meaning of paidTotal | Includes pending/refunded or mixed currencies | Define business metrics before joining/grouping |
| Query joining String to ObjectId does not match | Different BSON types on join keys | Store keys with matching types, migrate if needed |
| Missing/null data joins unexpectedly | Equality join treats missing keys like null in matching cases | Validate keys before joining |
| Trying to $lookup another database via qualified name | Standard from does not accept cross-database namespaces | Redesign data access/aggregation strategy |
| Using $out/$merge in subpipeline throws error | Write stages are disallowed inside $lookup.pipeline | Move write pipeline to a separate operation |
| Index works well in lab but is slow in production | Different cardinality, distribution, and workload | Measure explain, load, and indexes on representative data |

## 18. Practice Exercises

### Exercise 1 — Recognizing Left Outer Join Behavior

From the lab, use a simple $lookup joining customers with orders on customerCode. Count the orders for t001 customers. Why does **An** have **6 results** instead of **3**? How does two tenants sharing the same customerCode affect data correctness and security?

### Exercise 2 — Writing a Safe Correlated Subquery

Write a $lookup using **let** containing tenantId and customerCode, combined with **$expr/$and/$eq** to retrieve only orders from the same tenant and customer. Place $project in the subpipeline to return only _id/status/amount. What are the correct order counts for An, Bình, Chi, and Hà?

### Exercise 3 — Comparing the Two Syntaxes

Rewrite Exercise 2 using **localField/foreignField + let + pipeline**. Distinguish the equality join part from the tenant condition in the pipeline. State the MongoDB version requirement when using concise correlated subqueries.

### Exercise 4 — Two Most Recent Paid Orders

For each customer in t001, retrieve at most two latest paid orders, sorted by descending createdAt with _id as a tie-breaker. Predict the IDs for An and Bình. Why does placing limit before match/sort produce wrong results?

### Exercise 5 — Aggregating Directly in the Subpipeline

Write a $lookup that computes paidCount, paidTotal, and newestPaidAt using $group, then converts the result Array into a single paidSummary object. Handle customers with no orders using paidCount=0, paidTotal=0.00, and newestPaidAt=null.

### Exercise 6 — Combining Summary and List

Use $facet inside $lookup to obtain:

1. Total paid order count and total paid amount.
2. Two most recent paid orders.

Why do $lookup.as and $facet create nested Array layers? Write a clean projection for API consumption.

### Exercise 7 — $unwind and Cardinality

Perform the tenant-safe join on t001 and then $unwind. Count total documents before and after unwind. Enable preserveNullAndEmptyArrays and explain the difference. When should documents without orders be preserved?

### Exercise 8 — Anti-join

Starting from t001 orders, $lookup into customers by tenant/customerCode, then use $match on an empty Array to find orphan orders. Why is the result **ord-008**, and why shouldn't that order be deleted immediately?

### Exercise 9 — Reading explain for the Foreign Collection

Try the query:

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    let: { tenant: "$tenantId", code: "$customerCode" },
    pipeline: [
      {
        $match: {
          dataset: "lookup-join-v1",
          status: "paid",
          $expr: {
            $and: [
              { $eq: ["$tenantId", "$$tenant"] },
              { $eq: ["$customerCode", "$$code"] }
            ]
          }
        }
      }
    ],
    as: "paidOrders"
  }
}
~~~

Place this stage in a complete pipeline and run explain("executionStats"). Inspect fields related to IXSCAN/COLLSCAN, indexesUsed (if present), totalKeysExamined, totalDocsExamined, and nReturned. Explain why seeing IXSCAN on the outer collection alone does not prove the foreign collection has a suitable index.

### Exercise 10 — Choosing Between Lookup and Direct Query

A customer has 500,000 orders, and the screen displays only the 20 latest orders. Propose a query structure; explain why you should not $lookup all 500,000 orders just to grab the first page. Specify the corresponding index and pagination criteria.

### Exercise 11 — Designing Top Customers

A screen needs the **top 10 customers with the highest paidTotal** in tenant t001. Why can't you limit to 10 customers first and then compute paidTotal to guarantee the true top 10? Propose a pipeline starting from orders, grouping by tenant/customerCode, sorting paidTotal, and joining customer metadata at the appropriate stage.

### Exercise 12 — Access Control Design

An API receives tenantId from a request and performs a lookup based on customerCode. Describe how to bind tenant from the authenticated context rather than trusting a client-supplied tenantId directly, and how to ensure the foreign pipeline also enforces the correct tenant.

### Exercise 13 — Preventing Oversized Payloads

Suppose you look up a customer with 300,000 orders and return the full Array in the response. Analyze the risks regarding the 16 MiB BSON document limit, RAM, network, and latency. Write an alternative design consisting of a compact summary and a paginated detail endpoint.

### Exercise 14 — Heterogeneous Key Types

Collection A stores customerId as ObjectId, while collection B stores customerId as String. Predict what happens with an equality $lookup. Propose a schema/migration fix and describe the risks of inserting $toString/$toObjectId into the join condition instead of normalizing the data.

## 19. MongoDB References

- MongoDB Manual — [$lookup Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/).
- MongoDB Manual — [$expr Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/query/expr/).
- MongoDB Manual — [$match Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/).
- MongoDB Manual — [$project Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/).
- MongoDB Manual — [$group Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).
- MongoDB Manual — [$unwind Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/).
- MongoDB Manual — [$facet Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/).
- MongoDB Manual — [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).

**Key takeaway:** **$lookup** attaches results from another collection as an **Array** and by default retains input documents that have no matching records. The **localField/foreignField** form fits simple equality joins; **let + pipeline + $expr** lets you write correlated subqueries with multiple conditions, which is especially critical when keys are unique only within a tenant. Always **filter the right tenant on both sides, fetch only needed fields/records, group when only metrics are required, and verify indexes on the foreign collection**. Every $lookup should serve a clear read requirement rather than becoming a way to pull unbounded relational data into a single output document.
