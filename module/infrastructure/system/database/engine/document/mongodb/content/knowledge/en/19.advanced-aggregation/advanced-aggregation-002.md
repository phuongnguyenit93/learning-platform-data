# Impact of Indexes, Match Count, and Result Size When Joining in MongoDB

In MongoDB, `$lookup` enables an aggregation pipeline to fetch data from another collection and attach the results to each document being processed. It is a useful tool for displaying customers alongside their orders, products alongside inventory, employees alongside departments, or reports spanning multiple data entities. However, a syntactically valid `$lookup` pipeline can still be **very slow, memory-intensive, produce oversized documents, or join incorrect data** if three core factors are not evaluated:

1. **Indexes on the looked-up collection (foreign collection):** do they help locate matching records quickly for each input document?
2. **Number of input documents and matched records per document:** a customer with 2 orders behaves completely differently from a customer with 200,000 orders.
3. **Data size after the join:** `$lookup` builds a result array, while `$unwind` can multiply the number of pipeline documents; both impact CPU, I/O, RAM, network, and BSON size limits.

This lesson belongs to the **Advanced Aggregation** chapter of the *Database Engine Document MongoDB* module. The focus is on understanding join performance in MongoDB quantitatively—from cost models, indexes, and selectivity to cardinality, output size, `explain`, and designing pipelines that remain safe under increasing load. Examples run in **mongosh** in the lab database `lookup_performance_lab`. Certain optimizations and `explain` shapes depend on the MongoDB version, execution engine, data sharding, and index type; always measure in a realistic deployment before inferring production behavior.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish a `$lookup` **left outer join** from a join that multiplies rows after `$unwind`.
- Write `$lookup` using `localField/foreignField` and using `pipeline`, `let`, and `$expr`.
- Explain why indexes on the **foreignField** are usually more critical than indexing only localField.
- Count input documents, matches per document, total joined items, and **fan-out**.
- Recognize how one or two documents with an extreme match count can cause **cardinality explosion** and oversized documents.
- Distinguish the **16 MiB BSON document** limit from memory limits of individual aggregation stages.
- Choose the right placement for `$match`, `$project`, `$sort`, `$limit`, and `$unwind` to reduce resource usage while preserving semantics.
- Read index/scan metrics in `explain("executionStats")`, noting `EQ_LOOKUP` plans and version-dependent statistics fields.
- Design joins with **tenant isolation**, consistent key types, and guarantees against leaking data across tenants.
- Decide when to use `$lookup` versus pre-aggregating, materializing, embedding data, or changing the data model.

## 2. How Does `$lookup` Produce Results?

### 2.1. Basic Equality Join Form

Suppose there are two collections:

~~~javascript
// customers
{ _id: "c-01", customerCode: "U100", name: "An" }

// orders
{ _id: "o-101", customerCode: "U100", amount: 100 }
{ _id: "o-102", customerCode: "U100", amount: 250 }
~~~

Pipeline:

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
])
~~~

A customer document gets an attached array of matching orders:

~~~javascript
{
  _id: "c-01",
  customerCode: "U100",
  name: "An",
  orders: [
    { _id: "o-101", customerCode: "U100", amount: 100 },
    { _id: "o-102", customerCode: "U100", amount: 250 }
  ]
}
~~~

This is a **left outer join**: if a customer has no orders, the customer stays in the output with an empty `orders: []` array. `$lookup` **does not** automatically turn one customer with 100 orders into 100 independent documents. It returns **one customer document with a 100-element array**.

### 2.2. `$unwind` Is What Increases Document Count

When you follow up with:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  { $unwind: "$orders" }
])
~~~

a customer with two orders produces **two pipeline documents**, each carrying one order. Customers with no orders are dropped unless `preserveNullAndEmptyArrays` is specified.

~~~mermaid
flowchart LR
    A["1 customer"] --> L["$lookup"]
    L --> B["1 document + array of 3 orders"]
    B --> U["$unwind"]
    U --> C["3 output documents"]
~~~

This is a crucial distinction when estimating sizes:

| Step | Document Count | Size per Document |
|---|---:|---|
| Before join | One document/customer | Customer fields only |
| After `$lookup` | Still one document/customer | **Grows with total size of attached orders** |
| After `$unwind` | One document per matched order | Usually smaller than a document with a large array, but repeats customer fields multiple times |

**Do not equate "number of documents after `$lookup`" with "number of elements inside the joined arrays."** Both metrics must be measured.

## 3. Cost Model: Input × Matches × Data Size

Let:

- `N`: number of documents **entering `$lookup`** after preceding stages.
- `m_i`: number of foreign documents matching the `i`-th input document.
- `M = m_1 + m_2 + ... + m_N`: total number of joined elements.
- `S_i`: bytes required to store/serialize the `i`-th foreign element after projection.
- `B`: size of local fields and other overhead.

Then:

~~~text
Documents after $lookup:               N
Total joined foreign elements:         M = Σ m_i

Documents after default $unwind:       M
Documents after preserved $unwind:     M + number of local documents with m_i = 0

Document size after $lookup:
  approx. local size + sum of matched element sizes + array/BSON overhead
~~~

If each customer averages 20 orders across 10,000 customers:

~~~text
N = 10,000 customers
Avg matches = 20 orders/customer
M ≈ 200,000 matched orders
~~~

With `$unwind`, the pipeline turns 10,000 documents into 200,000 documents. If one projected order is around 1 KiB, the foreign payload alone is conceptually around **200 MiB** of data read and attached to intermediate documents, excluding local fields, BSON overhead, index work, and subsequent stages.

**This is only a design estimate, not a runtime formula.** Actual performance also depends on indexes, cache, key duplication, data distribution, shard count, sorting, projection, and data transferred between server and client.

### 3.1. Skewed Distribution Matters More Than the Average

If 9,999 customers each have one order, but one customer has 250,000 orders, the overall average still hides **one massive local document**. Even when the average match count is small, that outlier customer's document can hit the 16 MiB BSON limit when `$lookup` attaches all 250,000 orders into a single array.

When evaluating cardinality, look at:

- Average foreign matches.
- **P95/P99/max matches per local key**.
- Average/P95 size of a foreign document.
- Local document size before the join.
- Number of documents remaining after `$match`.

Measure not only total M, but also **max m_i**.

## 4. Preparing a Lab Dataset with Skewed Cardinality and Duplicate Keys Across Tenants

Select the lab database:

~~~javascript
use lookup_performance_lab
~~~

Two illustrative collections:

- `customers`: one document per customer; `customerCode` is unique only **within a tenant**, not system-wide.
- `orders`: multiple orders per customer; also includes an order without a corresponding customer.

### 4.1. Creating customers

~~~javascript
db.customers.insertMany([
  {
    _id: "c-01", tenantId: "t-01",
    customerCode: "U100", name: "An", segment: "VIP"
  },
  {
    _id: "c-02", tenantId: "t-01",
    customerCode: "U200", name: "Bình", segment: "REGULAR"
  },
  {
    _id: "c-03", tenantId: "t-01",
    customerCode: "U300", name: "Chi", segment: "VIP"
  },
  {
    _id: "c-04", tenantId: "t-02",
    customerCode: "U100", name: "Dung", segment: "REGULAR"
  },
  {
    _id: "c-05", tenantId: "t-02",
    customerCode: "U400", name: "Hà", segment: "VIP"
  },
  {
    _id: "c-06", tenantId: "t-01",
    customerCode: "U999", name: "Lan", segment: "REGULAR"
  }
])
~~~

`c-01` of tenant `t-01` and `c-04` of tenant `t-02` **share the same `customerCode = "U100"`**. This is valid data if the code is only required to be unique per tenant, but it causes a **cross-tenant join** if filters rely solely on customerCode.

### 4.2. Creating orders

~~~javascript
db.orders.insertMany([
  {
    _id: "o-101", tenantId: "t-01", customerCode: "U100",
    status: "PAID", amount: NumberDecimal("100"),
    createdAt: ISODate("2026-09-01T08:00:00Z"),
    payload: { note: "An's first order", channel: "WEB" }
  },
  {
    _id: "o-102", tenantId: "t-01", customerCode: "U100",
    status: "PAID", amount: NumberDecimal("250"),
    createdAt: ISODate("2026-09-03T08:00:00Z"),
    payload: { note: "An's second order", channel: "APP" }
  },
  {
    _id: "o-103", tenantId: "t-01", customerCode: "U100",
    status: "REFUNDED", amount: NumberDecimal("80"),
    createdAt: ISODate("2026-09-04T08:00:00Z"),
    payload: { note: "Refunded order", channel: "WEB" }
  },
  {
    _id: "o-104", tenantId: "t-01", customerCode: "U200",
    status: "PAID", amount: NumberDecimal("400"),
    createdAt: ISODate("2026-09-02T08:00:00Z"),
    payload: { note: "Bình's order", channel: "APP" }
  },
  {
    _id: "o-105", tenantId: "t-01", customerCode: "U200",
    status: "CREATED", amount: NumberDecimal("100"),
    createdAt: ISODate("2026-09-05T08:00:00Z"),
    payload: { note: "Unpaid order", channel: "WEB" }
  },
  {
    _id: "o-106", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("100"),
    createdAt: ISODate("2026-09-01T09:00:00Z"),
    payload: { note: "Chi 1", channel: "WEB" }
  },
  {
    _id: "o-107", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("110"),
    createdAt: ISODate("2026-09-02T09:00:00Z"),
    payload: { note: "Chi 2", channel: "APP" }
  },
  {
    _id: "o-108", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("120"),
    createdAt: ISODate("2026-09-03T09:00:00Z"),
    payload: { note: "Chi 3", channel: "APP" }
  },
  {
    _id: "o-109", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("130"),
    createdAt: ISODate("2026-09-04T09:00:00Z"),
    payload: { note: "Chi 4", channel: "WEB" }
  },
  {
    _id: "o-110", tenantId: "t-01", customerCode: "U300",
    status: "CREATED", amount: NumberDecimal("140"),
    createdAt: ISODate("2026-09-05T09:00:00Z"),
    payload: { note: "Chi 5", channel: "WEB" }
  },
  {
    _id: "o-111", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("150"),
    createdAt: ISODate("2026-09-06T09:00:00Z"),
    payload: { note: "Chi 6", channel: "APP" }
  },
  {
    _id: "o-112", tenantId: "t-02", customerCode: "U100",
    status: "PAID", amount: NumberDecimal("200"),
    createdAt: ISODate("2026-09-03T10:00:00Z"),
    payload: { note: "Dung 1", channel: "APP" }
  },
  {
    _id: "o-113", tenantId: "t-02", customerCode: "U100",
    status: "CANCELLED", amount: NumberDecimal("300"),
    createdAt: ISODate("2026-09-05T10:00:00Z"),
    payload: { note: "Dung 2", channel: "WEB" }
  },
  {
    _id: "o-114", tenantId: "t-02", customerCode: "U400",
    status: "PAID", amount: NumberDecimal("200"),
    createdAt: ISODate("2026-09-01T11:00:00Z"),
    payload: { note: "Hà 1", channel: "WEB" }
  },
  {
    _id: "o-115", tenantId: "t-02", customerCode: "U400",
    status: "CREATED", amount: NumberDecimal("210"),
    createdAt: ISODate("2026-09-02T11:00:00Z"),
    payload: { note: "Hà 2", channel: "APP" }
  },
  {
    _id: "o-116", tenantId: "t-02", customerCode: "U400",
    status: "PAID", amount: NumberDecimal("220"),
    createdAt: ISODate("2026-09-04T11:00:00Z"),
    payload: { note: "Hà 3", channel: "WEB" }
  },
  {
    _id: "o-117", tenantId: "t-02", customerCode: "U400",
    status: "PAID", amount: NumberDecimal("230"),
    createdAt: ISODate("2026-09-06T11:00:00Z"),
    payload: { note: "Hà 4", channel: "APP" }
  },
  {
    _id: "o-118", tenantId: "t-01", customerCode: "U500",
    status: "PAID", amount: NumberDecimal("999"),
    createdAt: ISODate("2026-09-07T11:00:00Z"),
    payload: { note: "Order without customer", channel: "WEB" }
  }
])
~~~

Run these insert statements only on an **empty lab database**. Re-running with the same `_id` causes a duplicate key error; do not delete data outside the lesson scope to retry. Check counts:

~~~javascript
db.customers.countDocuments({}) // 6
db.orders.countDocuments({})    // 18
~~~

### 4.3. Tenant-Accurate Order Distribution Table

| Customer | Tenant | Code | Correct Order Count | Notes |
|---|---|---|---:|---|
| `c-01` | `t-01` | `U100` | 3 | Shares customerCode with `c-04` in another tenant |
| `c-02` | `t-01` | `U200` | 2 | Has PAID and CREATED |
| `c-03` | `t-01` | `U300` | 6 | Highest match count in the lab |
| `c-04` | `t-02` | `U100` | 2 | Duplicate key across tenants |
| `c-05` | `t-02` | `U400` | 4 | Has three PAID |
| `c-06` | `t-01` | `U999` | 0 | No orders |
| **Total** | | | **17** | One order `o-118` has no customer |

This serves as the baseline to verify **cardinality and correctness** of pipelines. The valid total of foreign matches is **17**, not 18, because `o-118` has no matching customer. The total can exceed 18 if the join key is wrong and an order attaches to multiple customers—a bug to watch out for.

## 5. Simple Join: Syntactically Valid but Potentially Wrong Tenant

Run:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      matchCount: { $size: "$orders" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Match count results:

| Customer | `matchCount` joining only `customerCode` | Correct Count |
|---|---:|---:|
| `c-01` (t-01/U100) | 5 | 3 |
| `c-02` (t-01/U200) | 2 | 2 |
| `c-03` (t-01/U300) | 6 | 6 |
| `c-04` (t-02/U100) | 5 | 2 |
| `c-05` (t-02/U400) | 4 | 4 |
| `c-06` (t-01/U999) | 0 | 0 |
| **Total** | **22** | **17** |

**Issue:** `U100` appears in both t-01 and t-02. `c-01` receives two extra orders from `c-04`, and `c-04` receives three extra orders from `c-01`. Not only is this join slower, it is **business-incorrect and can leak data across tenants**.

### Dual Impact of an Under-Specified Join Key

An incomplete join condition causes two simultaneous consequences:

1. **Correctness/security:** attaches another tenant's data to the document.
2. **Performance:** match count rises from 17 to 22, reading more foreign docs, enlarging arrays, and amplifying rows after `$unwind`.

Performance tuning must not be divorced from **proper join key design**. Even a perfect index on `customerCode` does not make cross-tenant data valid.

## 6. Tenant-Safe Join Using `pipeline` and `let`

When a join requires multiple conditions, use `$lookup` with a subpipeline (*foreign pipeline*) and `let` variables.

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: {
        cCode: "$customerCode",
        cTenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$customerCode", "$$cCode"] },
                { $eq: ["$tenantId", "$$cTenant"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      matchCount: { $size: "$orders" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

`let` captures values from each local customer; `$$cCode` and `$$cTenant` are variables inside the foreign pipeline. `$expr` allows comparing fields in `orders` against those variables.

The resulting `matchCount` values are:

~~~text
c-01 -> 3
c-02 -> 2
c-03 -> 6
c-04 -> 2
c-05 -> 4
c-06 -> 0
Total -> 17
~~~

### 6.1. Combining Equality Join with an Extra Pipeline

On MongoDB versions that support combining `localField/foreignField` with `pipeline`, you can use an explicit equality join for `customerCode` and add the tenant condition:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      let: {
        cTenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: ["$tenantId", "$$cTenant"]
            }
          }
        },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "orders"
    }
  }
])
~~~

This expresses a fixed equality key alongside an extra condition. However, whether a **compound index covers both conditions** must be verified via `explain`; do not assume every `$expr` expression is translated into optimal index bounds by the optimizer.

### 6.2. Why Not Just `$match` by Tenant Outside?

The following pipeline **does not fix the wrong join**:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  }
])
~~~

The first `$match` only filters **customers** of t-01; it does not enforce `tenantId = "t-01"` on the joined **orders**. `c-01` can still receive U100 orders from t-02. The tenant constraint must be applied **inside the join condition**.

## 7. Index on the Foreign Collection: The Biggest Performance Lever

With an equality join:

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

the field looked up for each customer is **`orders.customerCode`**, on the `orders` collection. An index on the foreign side usually determines whether the query can pinpoint matching orders quickly or must examine a large volume of documents.

### 7.1. Basic foreignField Index

~~~javascript
db.orders.createIndex(
  { customerCode: 1 },
  { name: "idx_orders_customer_code" }
)
~~~

When `$lookup` processes customer `U300`, the index can locate the key range for U300 orders instead of scanning all orders. On large datasets with many local documents, the difference can be dramatic.

**Note:** this index accelerates join execution; **it does not fix U100 colliding across two tenants**. The join still needs the tenant condition for business correctness.

### 7.2. Compound Index for Multi-Field Conditions

For joins on `tenantId + customerCode`:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1
  },
  { name: "idx_orders_tenant_customer" }
)
~~~

Or if queries also sort by date within a customer:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_orders_tenant_customer_date" }
)
~~~

The first two fields serve equality on tenant/customer; the trailing two fields can serve fetching the latest orders for a customer when the planner can utilize those conditions and sort order.

Choose index key ordering based on **the queries actually executed**. If many queries filter globally by `customerCode` alone, an index starting with tenant lacks a matching prefix for them. If most queries strictly scope by tenant, placing tenant first is usually a sound candidate. Do not create every candidate index just to "have everything covered": each index adds overhead to inserts, updates, and deletes.

### 7.3. Does an Index on the Local Collection Help the Join?

~~~javascript
db.customers.createIndex(
  { tenantId: 1, segment: 1 },
  { name: "idx_customers_tenant_segment" }
)
~~~

This index can support **filtering local documents**:

~~~javascript
{ $match: { tenantId: "t-01", segment: "VIP" } }
~~~

thereby reducing how many customers enter `$lookup`. It does not replace the index on **`orders.customerCode/tenantId`** used to look up foreign matches.

Distinguish clearly:

| Index | Potential Effect |
|---|---|
| `customers.{tenantId, segment}` | Reduces local document count before the join |
| `orders.{customerCode}` | Supports equality lookup by customerCode |
| `orders.{tenantId, customerCode}` | Supports tenant-safe joins when query shape and indexability allow |
| `orders.{tenantId, customerCode, createdAt}` | Supports joins with date sort/top-N when supported |

**Rule of thumb:** identify which collection is being read at each stage; do not see the name `localField`, create an index on the local collection, and assume you have optimized the foreign lookup.

## 8. `$expr` in Correlated Lookups and Index Usage

An important question: "If there is an index on the foreign field, can a `pipeline`-style `$lookup` use it?"

**There is no universal 'always' answer.** MongoDB can use indexes for certain comparison expressions inside a foreign pipeline `$match` with `$expr`, subject to server version and query shape constraints.

Example:

~~~javascript
{
  $match: {
    $expr: {
      $eq: ["$customerCode", "$$cCode"]
    }
  }
}
~~~

`$eq` between a **foreign field** and a **`let` variable** can be considered for index usage when the variable resolves to a constant for that lookup iteration and other conditions permit. Comparison operators such as `$eq`, `$lt`, `$lte`, `$gt`, and `$gte` have supported cases for index usage inside `$expr`.

### 8.1. Limitations to Remember

- Comparing a **field to a constant** has a chance to use an index; comparing **field to field** generally lacks the same indexability.
- If a `let` variable resolves to a **missing/empty value** on a join iteration, index usage may be restricted.
- Certain `$expr` rules inside `$lookup` cannot use **multikey indexes**, and also have limitations with **sparse/partial indexes** per version documentation.
- Computed expressions applied to the foreign field such as `$toString`, `$concat`, or arbitrary type conversions can prevent range/index bounds compared to direct field comparisons.
- Other stages inside the foreign pipeline can affect filter pushdown and sort index usage.

Do not write:

~~~javascript
// Potentially very expensive due to computing on the foreign field inside the condition.
{
  $match: {
    $expr: {
      $eq: [
        { $toString: "$customerCode" },
        "$$cCode"
      ]
    }
  }
}
~~~

if you can store `customerCode` consistently as a string and compare directly. Do not use query-time conversion to patch a long-term schema type mismatch; normalizing at write time and migrating data is a more sustainable fix.

### 8.2. Why Must You Check `explain`?

The exact same index can be used very differently between:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  customerCode: "U300"
})
~~~

and:

~~~javascript
{
  $lookup: {
    from: "orders",
    let: { tenant: "$tenantId", code: "$customerCode" },
    pipeline: [
      {
        $match: {
          $expr: {
            $and: [
              { $eq: ["$tenantId", "$$tenant"] },
              { $eq: ["$customerCode", "$$code"] }
            ]
          }
        }
      }
    ],
    as: "orders"
  }
}
~~~

A standalone `find()` query is a good baseline check for whether an index suits equality on two fields, **but it does not prove** that a nested `$lookup` will use the index identically. Inspect the actual join pipeline in `explain("executionStats")`.

## 9. Local Document Count: Filtering Before Joining Can Cut Cost Dramatically

Suppose the collections contain:

~~~text
1,000,000 customers
30,000,000 orders
~~~

An API only needs VIP customers of tenant t-01, say 800 customers. If you join first and filter afterward:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  { $match: { tenantId: "t-01", segment: "VIP" } }
])
~~~

in terms of **logical flow**, `$lookup` sits ahead of the local filter. If the engine cannot safely push the filter earlier across stages, it may perform many unnecessary lookups. Do not rely on the optimizer to "automatically fix everything."

### 9.1. Move the Local Filter Up Front

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01", segment: "VIP" } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  }
])
~~~

Now only 800 local documents need joining instead of 1 million. The `customers.{tenantId,segment}` index can quickly isolate those 800 documents, and the index on `orders` serves each corresponding lookup.

### 9.2. Lab: Reducing Local Input from 6 to 2

In the sample dataset, the VIPs of t-01 are `c-01` and `c-03`:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "t-01",
      segment: "VIP"
    }
  },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      joined: { $size: "$orders" }
    }
  }
])
~~~

Result:

~~~text
c-01 => joined 3
c-03 => joined 6
~~~

Total matches passing through the join for this API are **9**, rather than 17 across all six customers.

### 9.3. When `$match` Cannot Be Moved Up Front

If a filter depends on **joined data** such as:

~~~javascript
{ $match: { "orders.status": "PAID" } }
~~~

it cannot simply be moved before `$lookup` because `orders` does not exist on local documents yet. Re-examine the intent:

- Keep only customers with **at least one** PAID order?
- Or include **only PAID orders** inside the array?
- Or fetch the **top 2 latest PAID orders per customer**?

Three different requirements lead to three different pipelines. Optimization must preserve exact semantics.

## 10. Filtering in the Foreign Pipeline: Reducing Matches and Array Size

### 10.1. Filtering After `$lookup` Does Not Prune Non-Matching Orders from the Array

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  {
    $match: {
      "orders.status": "PAID"
    }
  }
])
~~~

The outer `$match` selects customers with **at least one** PAID order, but the `orders` array still contains CREATED, REFUNDED, or CANCELLED orders for that customer. The query still pulls orders that do not need to be displayed into the post-join document.

### 10.2. Filtering PAID on the Foreign Side

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        { $match: { status: "PAID" } },
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "paidOrders"
    }
  }
])
~~~

In the lab dataset, `c-01` has only two PAID orders out of three; `c-03` has five PAID orders out of six. The `paidOrders` array is smaller and accurately satisfies "include paid orders in the result."

### 10.3. Is an Inner `$match` Always Faster?

Not automatically. A `status = PAID` filter may have low selectivity if 95% of orders are PAID, and the index must match to avoid unnecessary scans. Still, pushing filter conditions onto **the collection being queried** gives the engine a chance to discard documents early and shrink the payload.

Candidate index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1,
    status: 1,
    createdAt: -1
  },
  { name: "idx_order_customer_status_date" }
)
~~~

Evaluate against actual queries: if PAID is almost always requested, placing status before createdAt can be beneficial. If the API needs all statuses sorted by createdAt, a different index may fit better. Do not build a giant "catch-all" index without analyzing query shapes.

## 11. Projection: Smaller Elements Mean a Smaller Joined Array

Suppose an order document contains:

~~~javascript
{
  _id: "o-101",
  customerCode: "U100",
  tenantId: "t-01",
  status: "PAID",
  amount: NumberDecimal("100"),
  createdAt: ISODate("2026-09-01T08:00:00Z"),
  items: [ /* hundreds of items */ ],
  shippingDetails: { /* shipping payload */ },
  auditTrail: [ /* large history */ ],
  externalRawResponse: { /* large JSON */ }
}
~~~

If the API only needs to display the **two most recent orders with ID, amount, and date**, pulling all of `items`, `auditTrail`, and raw responses into `$lookup` is wasteful.

### 11.1. Projection Inside the Foreign Pipeline

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "orderSummaries"
    }
  }
])
~~~

Each foreign element in `orderSummaries` carries only the selected fields. This reduces output size and intermediate data volume.

### 11.2. Projecting After the Join Can Be Too Late for Some Costs

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  {
    $project: {
      name: 1,
      "orders._id": 1,
      "orders.amount": 1
    }
  }
])
~~~

The logical output is smaller due to the final projection, yet conceptually `$lookup` is asked to attach full order documents before the projection trims fields. Some optimizers may push down or prune operations when valid; **do not rely on that as a guarantee**.

Putting `$project` inside the foreign pipeline explicitly states which fields are needed. However, projection does not guarantee avoiding base document reads if the index does not cover them; check `totalDocsExamined`.

### 11.3. Do Not Drop Fields Needed by Business Logic

Overly narrow projections can strip data needed for reconciliation or aggregation. Specifically:

- If auditing is required, preserve necessary IDs/metadata.
- If the API must verify tenant boundaries, do not strip relevant identifiers without verifying correctness first.
- When sorting by a field, place `$sort` before projecting that field away.

Byte optimization must preserve the API contract.

## 12. `$limit` in the Foreign Pipeline: Capping Elements per Customer

In many UIs, users do not need **every order ever placed**; they only want the **two most recent orders**.

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $sort: {
            createdAt: -1,
            _id: 1
          }
        },
        { $limit: 2 },
        {
          $project: {
            _id: 1,
            amount: 1,
            status: 1,
            createdAt: 1
          }
        }
      ],
      as: "recentOrders"
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      recentOrders: 1,
      recentCount: { $size: "$recentOrders" }
    }
  }
])
~~~

Here `$limit: 2` is **inside the foreign pipeline**, so each customer receives at most **two orders**. For customer `c-03` with six orders, the `recentOrders` array contains only two: `o-111` and `o-110` (including CREATED status since this example has no status filter).

### 12.1. Why Sort Before Limit?

If you only write:

~~~javascript
pipeline: [
  { $limit: 2 }
]
~~~

then "two orders" does not mean **the two most recent orders**; MongoDB does not guarantee ordering without an explicit sort. Use `createdAt: -1` and `_id: 1` as a tie-breaker to get a deterministic order on a stable dataset.

### 12.2. `$limit` Outside `$lookup` Is a Different Problem

~~~javascript
db.customers.aggregate([
  { $limit: 2 },
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  }
])
~~~

The outer `$limit: 2` lets only **two customers** enter the join. It **does not** limit each customer to at most two orders.

Similarly, `{ $limit: 2 }` **after `$lookup`** limits the number of local output documents, not the elements inside each `orders` array.

### 12.3. Should Results Be Limited Just to Avoid Exceeding 16 MiB?

Limiting element counts and projecting fields helps keep documents small. Still, verify the **business contract**: if a user asks for *all* orders, silently returning at most two is a bug. When datasets can grow very large, provide a **separate detail API to paginate orders**, instead of returning every child inside a single customer document.

## 13. Match Count: Average, P95/P99, and Fan-Out

In the lab:

~~~text
6 customers
17 tenant-matched order matches
Avg = 17 / 6 ≈ 2.83 orders/customer
Max = 6 (c-03)
Min = 0 (c-06)
~~~

This is a tiny set used purely to illustrate concepts. In production, measure the distribution of `m_i` by tenant, customer tier, and time window—never rely solely on the average.

### 13.1. Counting Matches After Join

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $project: { _id: 1 } }
      ],
      as: "matchedOrderIds"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      matchCount: { $size: "$matchedOrderIds" }
    }
  },
  { $sort: { matchCount: -1, _id: 1 } }
])
~~~

In the lab, the highest result is `c-03` with 6; second is `c-05` with 4. However, **do not do this in production just to measure cardinality if each customer can match hundreds of thousands of orders**: this still materializes an array of all matched IDs before calling `$size`, risking large memory/document size issues. Later sections show how to compute aggregates on the foreign side without building a large array.

### 13.2. Counting Directly from the Foreign Collection

With the sample schema, you can group orders by business key:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        customerCode: "$customerCode"
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1, "_id.tenantId": 1 } }
])
~~~

This pipeline is not a join; it reveals the distribution of order counts per key. The output helps spot customers with huge match counts before deciding to embed all orders into customer documents.

In the lab dataset, there is also the `(t-01, U500)` group with one order that matches no customer. Measuring cardinality from the foreign collection is therefore a **reference statistic**, not automatically equal to matched orders after joining against a filtered local set.

### 13.3. Computing the Distribution via Two-Level Grouping

To see how many foreign keys have 1, 2, 3, ... orders:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        customerCode: "$customerCode"
      },
      ordersPerKey: { $sum: 1 }
    }
  },
  {
    $group: {
      _id: "$ordersPerKey",
      numberOfKeys: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

This inspects fan-out without attaching full order documents to every customer. On truly large datasets, `$group` can consume significant memory and require proper indexing, batching, or execution tuning.

## 14. Why Can a Foreign Index Save Join Cost?

Consider a simple estimate:

~~~text
N = 10,000 customers after local $match
Foreign collection = 5,000,000 orders
Each customer averages 12 orders
~~~

If each foreign lookup had to scan nearly all 5 million orders, read work would be enormous. This is **not a claim that MongoDB always executes a naive nested loop**, as the engine has multiple execution strategies, but it highlights the risk of an unindexed join.

When the foreign key has a proper index, the engine can seek the customer's key range and read matching candidates, sharply reducing examined foreign data. Still:

- There is index setup/read overhead for each lookup.
- If a customer has 100,000 orders, an index only helps **find all 100,000 accurately**; it does not make 100,000 documents vanish.
- If foreign projection needs fields outside the index, document FETCHes may be needed.
- If extra filters are not supported by the index, the engine may have to scan many keys within the customer's range.
- Cache locality and sharding heavily affect latency.

**Indexes solve finding foreign matches; cardinality and payload size determine how much data must flow onward.** Optimizing one dimension does not replace the other two.

### 14.1. Ask Three Quantitative Questions

For every critical `$lookup` query, gather:

| Metric Group | Example Observation | Problem If High |
|---|---|---|
| Local input | 50,000 customers entering lookup | Too many iterations/inputs to process |
| Foreign scan | 3,000,000 docsExamined | Foreign index or filter is ineffective |
| Match/output | 500,000 order matches, 500 MiB payload | Large arrays, unwind explosion, network and memory pressure |

A query with **few foreign docs examined but a huge result set** can still be slow. Conversely, a query returning very little data while **scanning millions of foreign documents** is not optimal either.

## 15. Document Size After `$lookup` and the 16 MiB Limit

MongoDB enforces a standard BSON document size limit of **16 MiB**. When `$lookup` embeds an orders array into a customer document, the resulting document can exceed this limit if the order count or order size is too large. Key points to remember:

- `$lookup` does not create a free virtual relationship; it **attaches actual data to the pipeline document**.
- Even if the final output only keeps a few fields, a design that attaches an entire child collection into one large array can fail or strain resources at intermediate stages.
- The 16 MiB single-document limit is **distinct** from individual aggregation stage memory limits and distinct from total response size across multiple documents.
- MongoDB has internal rules for intermediate pipeline document sizes, but you should never rely on internal exceptions to construct oversized joined documents; final BSON output remains bounded.

### 15.1. Payload Estimation Exercise

Suppose:

~~~text
Customer document size:                     2 KiB
Order after join (no projection):           8 KiB
Matched orders for one customer:            3,000

Approx. order payload: 3,000 × 8 KiB = 24,000 KiB ≈ 23.4 MiB
~~~

The orders portion alone exceeds 16 MiB. Adding array overhead, field names, and the customer document pushes it well past the limit. At this scale, do not use `$lookup` to return all orders inside a customer document.

### 15.2. Three Priority Mitigations

1. **Reduce match count:** place proper `$match` and `$limit` inside the foreign pipeline, if the contract allows.
2. **Reduce bytes per match:** `$project` only required fields.
3. **Change the data interface:** return customer metadata separately and expose a paginated orders endpoint; or return only a count/summary.

### 15.3. Do Not Confuse `allowDiskUse` with Bypassing 16 MiB

`allowDiskUse: true` lets certain aggregation stages spill temporary data to disk when exceeding their respective memory limits, depending on version/configuration. It **does not** raise the 16 MiB limit on a returned BSON document. If a pipeline builds a customer document with an oversized orders array, enabling `allowDiskUse` will not make that document valid.

## 16. `$unwind` and Document Inflation After Joining

With a tenant-safe join, we have:

~~~text
Customer c-01 -> 3 orders
Customer c-02 -> 2 orders
Customer c-03 -> 6 orders
Customer c-04 -> 2 orders
Customer c-05 -> 4 orders
Customer c-06 -> 0 orders
~~~

`$lookup` retains **6 customers**. If we `$unwind` without `preserveNullAndEmptyArrays`:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  { $unwind: "$orders" },
  { $count: "rows" }
])
~~~

Result:

~~~javascript
[{ rows: 17 }]
~~~

### 16.1. Preserving Customers Without Orders

~~~javascript
{
  $unwind: {
    path: "$orders",
    preserveNullAndEmptyArrays: true
  }
}
~~~

Replacing `$unwind` above with the preserve option gives **18 documents** in the lab set after unwind: 17 rows for matched orders, plus **one row** for `c-06` which has no orders.

### 16.2. Why Distinguish Output Count from Output Size?

After unwind, each document typically carries a single order, avoiding a huge array in one document, yet **all customer fields are repeated on every row**. If a customer carries a large profile object, total bytes after unwind can surge due to repeated local metadata.

The pipeline:

~~~javascript
db.customers.aggregate([
  /* tenant-safe lookup */,
  { $unwind: "$orders" },
  {
    $project: {
      _id: 1,
      customerCode: 1,
      orderId: "$orders._id",
      amount: "$orders.amount"
    }
  }
])
~~~

keeps each output row compact by projecting only needed fields. Do not carry the entire local profile and full order payload across multiple stages when you only need a `customerCode + amount` report.

## 17. Multiple Joins Can Multiply Fan-Out

Suppose each customer has:

~~~text
10 orders
5 support tickets
3 subscriptions
~~~

If you use three `$lookup` stages and keep the results as **three separate arrays**, the local document count stays at one per customer, while document size grows by all three arrays.

If you then run:

~~~javascript
{ $unwind: "$orders" },
{ $unwind: "$tickets" },
{ $unwind: "$subscriptions" }
~~~

a single customer explodes into:

~~~text
10 × 5 × 3 = 150 documents
~~~

This is **Cartesian-like multiplication** caused by unwinding independent arrays sequentially. If you want total orders and total tickets, multiplying rows like this is usually semantically wrong for statistics: each order appears 15 times, inflating `$sum` by 15x.

### 17.1. Wrong Revenue Total Example

~~~text
Customer A:
  Orders: 2 orders, amounts 100 and 200
  Tickets: 3 tickets

Correct: totalRevenue = 300

After unwinding orders then unwinding tickets:
  2 × 3 = 6 rows
  Summing orders.amount: 100×3 + 200×3 = 900 (WRONG)
~~~

### 17.2. Better Approaches

- Compute revenue inside the foreign `$lookup` pipeline and return a single summary.
- Compute ticket counts in a separate join branch.
- Keep arrays separate if needed for display, avoiding simultaneous unwinds unless necessary.
- Or re-group at the proper granularity, deduplicating by order ID when business logic genuinely requires processing complex cross-relations.

**Rule:** before adding a second `$unwind`, estimate the **product of element counts** across independent arrays, not just their sum.

## 18. When Only Counts Are Needed: Count on the Foreign Side, Do Not Pull the Whole Array

A UI might only need:

~~~javascript
{
  customerId: "c-03",
  name: "Chi",
  orderCount: 6
}
~~~

Fetching all orders and then taking `$size` is inefficient:

~~~javascript
// Unsuitable for customers with hundreds of thousands of orders.
[
  { $lookup: { /* returns all orders */, as: "orders" } },
  { $project: { orderCount: { $size: "$orders" } } }
]
~~~

### 18.1. `$count` Directly Inside the Foreign Pipeline

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: {
        t: "$tenantId",
        code: "$customerCode"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $count: "total" }
      ],
      as: "orderStats"
    }
  },
  {
    $set: {
      orderCount: {
        $ifNull: [
          { $first: "$orderStats.total" },
          0
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      tenantId: 1,
      customerCode: 1,
      orderCount: 1
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Instead of building an array of full order documents, `orderStats` contains at most one document `{total: N}` or an empty array when there are no matches.

In the lab:

~~~text
c-01 -> 3
c-02 -> 2
c-03 -> 6
c-04 -> 2
c-05 -> 4
c-06 -> 0
~~~

### 18.2. Counting on the Foreign Side Still Has a Cost

`$count` reduces **returned data size and join array memory**, but the server still has to scan/evaluate matching orders to count them unless specific optimizations apply. If an API requires counts very frequently across millions of customers, you may need:

- Pre-aggregated counters.
- Materialized view / summary collection.
- A counter in the customer document updated synchronously with the order lifecycle.
- Reconciliation jobs to fix drift.

Do not claim `$count` is free just because it outputs a single document.

### 18.3. When Totals Are Needed Instead of Counts

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            status: "PAID",
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $group: {
            _id: null,
            paidOrderCount: { $sum: 1 },
            paidRevenue: { $sum: "$amount" }
          }
        },
        {
          $project: {
            _id: 0,
            paidOrderCount: 1,
            paidRevenue: 1
          }
        }
      ],
      as: "paidStats"
    }
  }
])
~~~

`paidStats` is just one summary element (if paid orders exist) instead of many full orders. When there are no paid orders, the array is empty; the API can normalize count/revenue to 0 using `$ifNull` and `$first` or handle it in application code.

## 19. Top-N per Customer: Replace "All" with Display-Ready Data

For dashboards, screens often need:

~~~text
Customer
  name
  lastTwoPaidOrders
  paidOrderCount
~~~

Design should separate:

- **Top-N detail**: fetch at most 2 PAID orders by createdAt.
- **Count**: total PAID orders, via a separate summary query/join or pre-aggregation.

### 19.1. Fetching Top 2 PAID in the Foreign Pipeline

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            status: "PAID",
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $sort: { createdAt: -1, _id: 1 } },
        { $limit: 2 },
        { $project: { _id: 1, amount: 1, createdAt: 1 } }
      ],
      as: "lastTwoPaidOrders"
    }
  }
])
~~~

For `t-01`:

~~~text
c-01: o-102, o-101       (o-103 REFUNDED does not match)
c-02: o-104              (o-105 CREATED does not match)
c-03: o-111, o-109       (two latest PAID)
c-06: []                 (no orders)
~~~

### 19.2. Candidate Index for Top-N

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_paid_orders_by_customer_date" }
)
~~~

The query has equality on tenant/customer/status, and the subsequent sort fields are createdAt and ID. However, whether the sort index is used inside a correlated foreign pipeline depends on how the planner indexes `$expr` predicates. Inspect the plan and keys examined rather than assuming the index definitely "reads just two keys."

### 19.3. Does Total Count Get Capped at 2?

If you compute:

~~~javascript
{ $size: "$lastTwoPaidOrders" }
~~~

the maximum result is 2, **not the total number of paid orders**. For `c-03` with 5 paid orders, the count from the top-2 array is only 2. If the API needs the true total, run a separate count or use a materialized counter.

This is a very common correctness bug when optimizing `$lookup` with `$limit` while forgetting that the meaning of `$size` changed.

## 20. Paginate Local Documents Before or After Joining?

Suppose a customer list API returns pages of 20 customers, each with their two latest orders. A pipeline can be written as:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  { $sort: { name: 1, _id: 1 } },
  { $skip: 0 },
  { $limit: 20 },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $sort: { createdAt: -1, _id: 1 } },
        { $limit: 2 },
        { $project: { _id: 1, amount: 1, createdAt: 1 } }
      ],
      as: "recentOrders"
    }
  }
])
~~~

Meaning: select 20 customers on **one customer page**, and join orders only for those customers. If `$lookup` ran before `$skip/$limit`, it might join many customers that never appear on the page.

### 20.1. When Can You Paginate Before Joining?

When ordering and pagination depend solely on **local fields**, and the join **is not used to decide which customers are kept or how they are ordered**, paginating locally first preserves exact results while reducing N.

### 20.2. When Can You Not?

If the requirement is:

> Return the 20 customers with the **highest total PAID amount**.

you cannot take 20 customers by name first and then join/sum: you would only rank those 20 selected customers, missing high-revenue customers outside that slice. You must compute or know revenue across the entire candidate set before sorting and limiting—or use precomputed summaries.

Similarly, if the filter is:

> Only customers with at least 3 PAID orders.

limiting locally before counting orders can leave the page short of results and miss qualifying customers further down.

**Early optimization must never alter the candidate set the user intends to paginate.**

## 21. `$match` After `$unwind` and Conditions on Joined Data

A common way to fetch each PAID order with its customer:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  { $unwind: "$orders" },
  { $match: { "orders.status": "PAID" } },
  {
    $project: {
      _id: 1,
      customerCode: 1,
      orderId: "$orders._id",
      amount: "$orders.amount"
    }
  }
])
~~~

Semantically, the output includes only rows for PAID orders, yet the pipeline may have joined and unwound non-PAID orders before filtering.

### Pushing the Foreign Filter into `$lookup`

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            status: "PAID",
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $project: { _id: 1, status: 1, amount: 1 } }
      ],
      as: "paidOrders"
    }
  },
  { $unwind: "$paidOrders" }
])
~~~

This directly expresses "join only PAID orders." In some pipelines, the MongoDB optimizer can **coalesce `$lookup + $unwind`, and even push `$match` on joined fields into the lookup** when proven safe; inspect `explain` to see the actual plan. Avoid writing obscure pipelines just to look concise when optimizer behavior hasn't been verified.

## 22. Reading `explain("executionStats")` for `$lookup`

Instead of only watching application timings, inspect the plan:

~~~javascript
db.customers.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $project: { _id: 1, amount: 1 } }
      ],
      as: "orders"
    }
  }
])
~~~

### 22.1. Key Statistics Fields

Depending on the MongoDB version/engine, lookup `explain` output may include:

| Field / Stage | What to Understand |
|---|---|
| `$cursor` | How the local collection is read |
| `IXSCAN` | Reading index keys in the corresponding plan |
| `COLLSCAN` | Collection scan |
| `FETCH` | Fetching documents after an index scan |
| `EQ_LOOKUP` | Represents an equality lookup in eligible Slot-Based Execution plans |
| `indexesUsed` | Foreign index name(s) used, when reported |
| `totalKeysExamined` | Total index keys examined at the corresponding stage |
| `totalDocsExamined` | Total documents examined at the corresponding stage |
| `collectionScans` | Number of collection scans associated with the lookup, when reported |
| `nReturned` | Number of documents returned at the corresponding stage |
| `executionTimeMillisEstimate` | Stage time estimate, if provided |

**Do not assume** every MongoDB version prints `EQ_LOOKUP` or `indexesUsed` at the same JSON path. Plans using the classic engine, SBE, with or without a foreign pipeline, or on sharded collections can have different shapes.

### 22.2. What Is `EQ_LOOKUP`?

When eligible, MongoDB can execute an equality `$lookup` using the Slot-Based Execution engine, and the plan may show an `EQ_LOOKUP` stage. Factors such as a lookup with a foreign pipeline, numeric path components, or special `from` collection types can affect whether this execution mode is used depending on version. Do not treat the absence of the string `EQ_LOOKUP` as sole proof that a join is slow.

For `$lookup` with `pipeline/let/$expr`, index usage and execution behavior can differ from a simple equality lookup. Focus on **keys/docs examined, actual index usage, and cardinality/output**, rather than stage names alone.

### 22.3. Analyzing Local and Foreign Parts Separately

For a pipeline with:

~~~text
$match local -> $lookup foreign -> $unwind -> $sort
~~~

ask:

1. How many customers are read before `$lookup`?
2. How many customers actually enter `$lookup`?
3. Does the foreign side have an appropriate index?
4. Across the entire lookup, how many keys and docs are examined?
5. How many order matches get attached to arrays?
6. After `$unwind`, how many documents proceed?
7. How many documents must the subsequent sort handle, and does it spill?

A query with a clean local IXSCAN **can still execute a very expensive join** if the foreign side performs repeated collection scans.

### 22.4. Testing the Foreign Access Path with an Equivalent Query

~~~javascript
db.orders.find({
  tenantId: "t-01",
  customerCode: "U300"
}).sort({
  createdAt: -1,
  _id: 1
}).limit(2).explain("executionStats")
~~~

This command checks whether the `orders` index is helpful for the specific access pattern. However, a correlated foreign pipeline with `$expr` may differ in indexability; **always check `explain` on the real join pipeline as well**.

### 22.5. You Cannot Benchmark Performance on 6 Customers / 18 Orders

MongoDB may pick COLLSCAN simply because the collection is tiny; differences of a few microseconds or milliseconds are noisy. The lab demonstrates **cardinality and query semantics**. Benchmarking indexes requires larger datasets, production-like skew, concurrent requests, realistic cache state, replica/shard topology, and measurable SLOs.

## 23. Stage Ordering and Plan Optimization

A query showing a list of customers with order counts:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  { $project: { _id: 1, tenantId: 1, customerCode: 1, name: 1 } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $count: "total" }
      ],
      as: "stats"
    }
  },
  { $set: { totalOrders: { $ifNull: [{ $first: "$stats.total" }, 0] } } },
  { $project: { stats: 0 } },
  { $sort: { name: 1, _id: 1 } }
])
~~~

Stages before lookup narrow local inputs and local fields; lookup returns only the count; trailing stages shape the required output. However, if the API wants customers sorted by descending `totalOrders`, the sort must come **after** `totalOrders` is computed:

~~~javascript
{ $sort: { totalOrders: -1, _id: 1 } }
~~~

You cannot apply a small `$limit` before lookup and claim it yields the "top customers by totalOrders" across the whole set.

### 23.1. Input `$sort` and Local Indexes

If the API only needs 20 customers alphabetically by name:

~~~javascript
{ $match: { tenantId: "t-01" } },
{ $sort: { name: 1, _id: 1 } },
{ $limit: 20 },
{ $lookup: { /* foreign pipeline */ } }
~~~

the index:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, name: 1, _id: 1 },
  { name: "idx_customers_tenant_name_id" }
)
~~~

can select the top 20 local docs early. This reduces N **if selection does not depend on foreign data**.

### 23.2. When the Optimizer Coalesces Stages

MongoDB can apply optimizations such as:

- Pushing `$match` ahead of stages that do not alter the referenced fields.
- Coalescing `$sort` + `$limit` into a top-k sort where eligible.
- Coalescing adjacent `$lookup` and `$unwind`, sometimes including `$match` on joined fields.

Still, the optimizer **cannot rewrite a pipeline in a way that changes its semantics**. Never assume "the optimizer handles any stage order." A `$limit` before a join and a `$limit` after unwind typically solve two different problems.

## 24. Joins with Many Matches and `$facet`: Watch Output Size

An API returning:

~~~javascript
{
  totalCustomers: 10000,
  customers: [ /* 20 customers + order summaries */ ]
}
~~~

can use `$facet`:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $facet: {
      metadata: [{ $count: "totalCustomers" }],
      customers: [
        { $sort: { name: 1, _id: 1 } },
        { $limit: 20 },
        {
          $lookup: {
            from: "orders",
            let: { t: "$tenantId", code: "$customerCode" },
            pipeline: [
              {
                $match: {
                  $expr: {
                    $and: [
                      { $eq: ["$tenantId", "$$t"] },
                      { $eq: ["$customerCode", "$$code"] }
                    ]
                  }
                }
              },
              { $sort: { createdAt: -1, _id: 1 } },
              { $limit: 2 },
              { $project: { _id: 1, amount: 1, createdAt: 1 } }
            ],
            as: "recentOrders"
          }
        }
      ]
    }
  }
])
~~~

`$facet` is handy when branches compute totals and a page from the same input set, but it has its own memory and result-size limits. Because facet outputs **a single document containing arrays**, placing a huge customers array inside a facet can hit the BSON limit. Never build a facet with hundreds of thousands of customer records just because the inner join had a `$limit` elsewhere.

### 24.1. Total Customers Differs from Total Orders

The `metadata` branch in the example counts **customers after the local match**, not order matches. If the API needs the count of PAID orders, calculate it from the foreign collection or an appropriate summary—do not confuse a local-level count with a joined-row count.

## 25. Null, Missing, and Join Key Types

### 25.1. Missing / Null Join Fields

In the equality `localField/foreignField` form, MongoDB treats missing fields similarly to null values for matching in certain cases. If many documents lack the join field, a careless join can produce **a huge number of unintended matches**.

Conceptual example:

~~~javascript
// Local missing customerCode
{ _id: "c-missing", tenantId: "t-01" }

// Foreign missing customerCode
{ _id: "o-missing", tenantId: "t-01" }
~~~

Do not design critical joins relying on "if the key is missing it surely won't match." When business rules require valid keys, enforce schema validation, filtering, and canonicalization.

### 25.2. Mismatched Data Types

~~~javascript
// Local
{ customerCode: 123 }

// Foreign
{ customerCode: "123" }
~~~

These two values have different BSON types. Do not assume MongoDB treats them as the same code. Type conversions inside a foreign `$expr` can defeat index usage, so normalize keys at write time.

### 25.3. Array Keys

When `localField` is an array, equality `$lookup` can match foreign documents based on array elements according to MongoDB semantics, leading to higher-than-expected fan-out. If `foreignField` is an array or a compound index becomes multikey, indexability limitations must also be checked, especially in correlated `$expr`. Before designing array-based joins:

- Clarify whether you need to match **any element** or **the same element object**.
- Estimate array lengths and match counts.
- Use `$elemMatch` when multiple conditions must apply to the same array element.
- Check indexes and `explain` for actual array data.

### 25.4. Collation

String equality joins can be affected by collation configured at the operation or collection level. If a foreign index was created with a collation incompatible with the query, the optimizer may not use it for string comparisons as expected. Keep ID keys in a stable canonical format rather than building identity around locale-dependent display name comparisons.

## 26. Sharded Collections and Distributed Cost

In a sharded cluster, `$lookup` may need to read foreign data across multiple shards. MongoDB supports `$lookup` against a sharded `from` collection in modern versions (e.g., MongoDB 5.1 onward), though detailed routing and query plan behavior varies by version and topology.

### 26.1. Same Join Key Does Not Guarantee Same Shard

If `orders` is sharded on a field unrelated to the foreign lookup condition, finding a customer's orders may require fanning out to multiple shards. Having good secondary indexes on every shard does not eliminate routing and network overhead.

Conversely, filters containing an appropriate shard key can enable targeted routing under supported conditions. Do not assume that simply adding `tenantId` to an index automatically routes every lookup to a single shard; **shard key and index key are related but distinct designs**.

### 26.2. Specific Factors to Measure

- Number of shards queried per lookup.
- Data volume transferred between shards and the merger.
- Network latency, shard skew, and hot tenants.
- Foreign key selectivity on each shard.
- Whether sort/limit can be pushed near the data or must be merged centrally.
- Spill, memory, and result size limits.

If one customer has millions of orders, well-sharded data still does not make "join all orders into a single document" compatible with the 16 MiB limit.

## 27. When Should `$lookup` Be Replaced by Another Data Model?

### 27.1. Embed Documents When Relationships Are Small and Bounded

If each order always has a small number of line items that are always read together with the order, embedding `items` in the order document may fit better than a separate join. However, for **customer → orders** which grows unboundedly over time, embedding all orders in the customer document causes unbounded document growth.

**Guideline:** 1:N relationships with **bounded** N and tightly coupled lifecycles can be embedded; unbounded N requiring independent pagination/search usually fits better in a referenced separate collection.

### 27.2. Partially Denormalize Stable Fields

If an order list API needs the customer name for display, you can store:

~~~javascript
{
  _id: "o-101",
  customerId: "c-01",
  customerNameSnapshot: "An",
  amount: NumberDecimal("100")
}
~~~

This avoids joining customers for every order list item. Trade-off: the snapshot name can become stale if the customer renames, so define explicitly whether it represents **name at order placement** or current name.

### 27.3. Pre-Aggregation for Dashboards

For dashboards needing revenue and order counts per customer, a materialized summary:

~~~javascript
{
  _id: { tenantId: "t-01", customerCode: "U300" },
  paidOrderCount: 5,
  paidRevenue: NumberDecimal("610"),
  lastPaidOrderAt: ISODate("2026-09-06T09:00:00Z")
}
~~~

allows reading a single summary document instead of scanning/aggregating many orders on every request.

Trade-offs:

- Must update when orders transition CREATED → PAID, PAID → REFUNDED, or are deleted.
- May require transactions, outbox pattern, or event consumers to stay synchronized.
- Needs reconciliation because retries and failures can cause summary drift.
- Must define whether dashboard freshness is near-real-time or eventual.

### 27.4. Dedicated API to Paginate Children

Instead of:

~~~http
GET /customers/c-03?includeAllOrders=true
~~~

design:

~~~http
GET /customers/c-03
GET /customers/c-03/orders?limit=20&cursor=...
~~~

Query orders by tenant/customer key and sort/paginate with a matching index. This avoids giant join arrays and scales cleanly as a customer's order history grows.

### 27.5. Application-Side Join vs. `$lookup`

Application-side joining with **N separate queries** for N customers creates the **N+1 query problem** and many network round-trips. `$lookup` can reduce round-trips and leverage server-side execution.

Conversely, when batching a set of keys, querying orders with a tenant-scoped `$in` and grouping results in the application is also worth evaluating:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  customerCode: { $in: ["U100", "U200", "U300"] }
})
~~~

Do not turn N+1 queries into one giant `$lookup` solely to "save round-trips" while ignoring cardinality and document size. Compare server cost, network bytes, and consistency complexity.

## 28. A Decision Matrix for Join Performance

| Symptom | Possible Cause | Remediation |
|---|---|---|
| High foreign `totalDocsExamined`, small output | Missing index or non-indexable `$expr` | Add suitable foreign index, normalize keys, check explain |
| High local `nReturned`, few matches per doc | Too many local documents entering lookup | Place local `$match` / local pagination before join when semantically valid |
| Each customer returns thousands of orders | High fan-out, joining full history | Filter/limit foreign, separate children API, pre-aggregate |
| A customer hits 16 MiB | Excessive max cardinality/payload | Stop embedding all matches, trim fields/matches |
| Pipeline slows down after `$unwind` | Cardinality explosion | Avoid unnecessary unwind, compute summary inside lookup |
| Totals are multiplied after two `$unwind` stages | Cartesian product across independent arrays | Aggregate each branch separately, avoid chained unwinds |
| More matches than valid data | Join key missing tenant or non-unique | Join on full composite key, enforce unique constraints and authorization |
| PAID filter outside lookup but array stays large | Outer filter selects customer, does not filter array elements | Move filter into foreign pipeline |
| Wrong Top-N because `$limit` is outside lookup | Limits local docs rather than each foreign array | Sort/limit inside foreign pipeline |
| Wrong count after foreign `$limit` | Counting top N instead of all records | Count separately or maintain precomputed counter |
| Sort spills to disk | Sort not backed by index or large result set | Index sort order, shrink input, top-k, monitor disk spill |
| Slow join on sharded cluster | Scatter-gather, network/shard skew | Evaluate shard key/filters and routing |
| Good local index yet join remains slow | Heavy foreign scanning | Optimize foreign access, not just local |
| `$lookup` is readable but server load is high | Too many joins on the hot request path | Materialized read models, appropriate caching, API redesign |

## 29. Practice Exercises: Measuring Indexes, Cardinality, and Output

Use the `customers` and `orders` dataset from Section 4. Practice **in a lab**; do not run experimental index creations/drops in production.

### Exercise 1 — Basic Join and Cross-Tenant Bug

Run:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      count: { $size: "$orders" }
    }
  }
])
~~~

Sum the counts and explain why the total is 22 instead of 17.

### Exercise 2 — Tenant-Safe Join

Write a `$lookup` using `let` + `$expr` comparing both `tenantId` and `customerCode`. Predict the match count for each customer and verify that `c-06` still appears with an empty array.

### Exercise 3 — Foreign Index

Create:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, customerCode: 1 },
  { name: "idx_orders_tenant_customer" }
)
~~~

Run `explain("executionStats")` for the tenant-safe pipeline before and after creating the index across different lab environments if the dataset is large enough. Report `indexesUsed`, `totalKeysExamined`, and `totalDocsExamined` if the engine outputs those fields. **Do not fabricate metrics** if the planner on a small dataset chooses COLLSCAN.

### Exercise 4 — Local Filter

Select only VIPs of `t-01` and then join. Predict:

~~~text
Customers entering lookup: 2
Total tenant-matched orders: 9
~~~

Explain the distinct roles played by the local index and the foreign index.

### Exercise 5 — Filtering PAID Inside Lookup

Write a join that attaches only PAID orders; compare `count` for `c-01` and `c-03`:

~~~text
c-01 PAID: 2
c-03 PAID: 5
~~~

Compare with `$match:{"orders.status":"PAID"}` **outside** the lookup. Do both approaches return the same arrays?

### Exercise 6 — Foreign Projection

Write a join returning only `_id`, `amount`, and `createdAt` of orders. Explain the impact on output bytes and why projection does not automatically guarantee a covered query.

### Exercise 7 — Top 2 per Customer

Inside the foreign pipeline:

~~~javascript
{ $sort: { createdAt: -1, _id: 1 } },
{ $limit: 2 }
~~~

For `c-03`, predict the two returned orders when **not** filtering by status; then add `status:"PAID"` and predict the new result.

### Exercise 8 — Counting Instead of Embedding

Replace the full orders array with `$count:"total"` inside the foreign pipeline. Use `$ifNull` and `$first` to display `orderCount:0` for `c-06`.

### Exercise 9 — Unwind

After the tenant-safe join, run:

~~~javascript
{ $unwind: "$orders" }
~~~

Explain why there are 17 output documents. Then try `preserveNullAndEmptyArrays:true` and explain the number 18.

### Exercise 10 — Two Independent Arrays

A customer has two orders and three tickets. If you unwind both arrays, how many rows are produced? Why can `$sum:"$orders.amount"` be tripled?

### Exercise 11 — Size Limits

Suppose one customer has 4,000 orders, each about 5 KiB after join. Estimate the foreign payload before overhead. Why can't `allowDiskUse:true` be relied upon to embed all of them into a single BSON document?

### Exercise 12 — Local Pagination Before Joining

Design a pipeline fetching 20 customers by name, each with their two latest orders. Where do `$match`, `$sort`, `$skip`, and `$limit` go if filtering and paging rely only on local fields?

### Exercise 13 — When Pre-Limiting Is Invalid

The requirement is "20 customers with the highest PAID revenue." Explain why picking 20 customers first and then calculating revenue is wrong. Propose using a summary view or aggregating over the full candidate set.

### Exercise 14 — Production Indexes and Deployment

You have two queries:

1. Dashboard by tenant + customer, fetching only the two latest orders.
2. Tenant-wide report filtering orders by date.

Propose distinct candidate indexes and explain why `{tenantId,customerCode,createdAt}` does not automatically optimize a query with only tenant + date.

### Exercise 15 — Monitoring Skew

Propose metrics/alerts for:

- P95/P99/max matched orders per customer.
- Foreign docs examined per local document.
- Total API output bytes.
- Rate of queries hitting disk spill or BSON size errors.
- Latency p95/p99 and CPU/I/O.

Why can an average of 10 orders/customer hide a customer with 500,000 orders?

## 30. Practice Answer Hints

### Exercise 1

Joining only on `customerCode` causes both `c-01` and `c-04` to receive all five orders with code U100 across both tenants. The total count is **22**, consisting of 17 valid matches and 5 erroneous cross-tenant attachments.

### Exercise 2

Adding tenant equality yields counts `3, 2, 6, 2, 4, 0`. `$lookup` still preserves `c-06` with an empty `[]` array; total matched elements = 17.

### Exercise 3

An index on `orders` can help locate records by foreign keys. `explain` output must be inspected per version/plan; there are no fixed keys/docs examined numbers for a tiny lab dataset.

### Exercise 4

Only `c-01` and `c-03` are VIPs in t-01, with 3 and 6 orders respectively, totaling 9. The local index supports the local `$match`; the foreign index serves order lookups.

### Exercise 5

`c-01` has 2 PAID, `c-03` has 5 PAID. An outer `$match` `{"orders.status":"PAID"}` only checks whether the customer has at least one PAID order; it does not strip other orders out of the array.

### Exercise 6

Projection in the foreign pipeline reduces the fields per matched order, shrinking bytes in the joined array. However, if the index does not include all returned fields, MongoDB may still need to FETCH documents.

### Exercise 7

`c-03`'s two latest orders are `o-111` (2026-09-06) and `o-110` (2026-09-05). When filtering to PAID only, `o-110` is excluded and the two orders are `o-111` and `o-109`.

### Exercise 8

Foreign `$count` creates a summary rather than a full orders array. When there are no matches, use `$ifNull:[{$first:"$orderStats.total"},0]` to return 0.

### Exercise 9

Default `$unwind` produces 17 matched order rows, dropping `c-06`. Setting preserve true keeps an extra row for the customer with no orders → 18.

### Exercise 10

Two independent arrays of 2 and 3 elements produce 2 × 3 = 6 rows. Each order is repeated 3 times; summing amount directly across the 6 rows triples the true total.

### Exercise 11

`4000 × 5 KiB = 20,000 KiB ≈ 19.5 MiB`, excluding local fields and overhead. This exceeds the 16 MiB BSON document limit. `allowDiskUse` does not raise the single-document limit.

### Exercise 12

When paging relies solely on local fields: `$match(local) → $sort(local) → $skip → $limit → $lookup(foreign top 2)`. The goal is to execute lookups only for customers appearing on the page.

### Exercise 13

Total revenue is a field **derived from orders**, unknown when picking the first 20 customers. You must compute or read summary revenue across all candidates before sorting and taking the top 20.

### Exercise 14

Dashboard: candidate `{tenantId:1,customerCode:1,createdAt:-1,_id:1}`; tenant + date report: candidate `{tenantId:1,createdAt:-1}`. The intervening `customerCode` key prevents the first index from efficiently supporting tenant-wide date ranges/sorts.

## 31. Review Questions

**1. Which collection should be indexed for an equality `$lookup`?**

An index on the foreign collection—specifically `foreignField` and foreign pipeline filter fields—is typically essential to locate matches quickly. Local indexes filter/sort local inputs and do not replace foreign indexes.

**2. Does `$lookup` multiply the pipeline document count by the match count?**

Not by default. It attaches an **array of foreign matches** to each local document. `$unwind` is what expands array elements into multiple documents.

**3. What is fan-out?**

The number of foreign documents matching each local document. Total matched elements equal the sum of fan-out across local documents; after unwind, this can become the output row count.

**4. Why measure max matches in addition to the average?**

A single local key with an extreme number of matches can push a joined document past 16 MiB even when the average is very low.

**5. Does adding a foreign index shrink the result array?**

No. An index helps locate matches faster, whereas match count depends on data and join conditions. To shrink the array, filter, limit, project, or redesign the API.

**6. How does a local `$match` before `$lookup` help?**

It reduces the number of local documents needing lookup when the filter does not depend on foreign data. Reducing N can substantially cut total work.

**7. Why doesn't a post-`$lookup` `$match` on order status trim the array?**

It selects local documents matching an array predicate while leaving non-matching elements inside the joined array. Foreign filters belong in the foreign pipeline when only matching elements should be kept.

**8. How does `$limit` inside a foreign pipeline differ from `$limit` outside lookup?**

Inside the foreign pipeline, it caps foreign matches **per local document**; outside, it caps the number of local documents/rows at that stage.

**9. What does `$project` inside a foreign pipeline accomplish?**

It trims fields of each matched foreign document, reducing array and output size. It does not by itself guarantee a covered query.

**10. Why can two `$unwind` stages corrupt sums?**

Unwinding two independent arrays multiplies rows by the product of their lengths; values from the first array are duplicated for every element of the second array.

**11. Does `$count` on the foreign side eliminate all lookup cost?**

No. It shrinks returned data size, but the server still generally evaluates matching foreign documents to count them.

**12. How do the 16 MiB limit and `allowDiskUse` relate?**

16 MiB caps the size of a standard BSON document; `allowDiskUse` only lets eligible stages spill working memory to disk when needed and does not raise the document size limit.

**13. Does `$expr` inside a lookup always use an index?**

No. Certain field-to-constant comparisons can use indexes under supported conditions; field-to-field comparisons, missing variables, multikey/sparse/partial indexes, or field-transforming expressions can restrict indexability.

**14. When should you look for `EQ_LOOKUP`?**

When reading `explain` for an equality lookup on versions supporting Slot-Based Execution. Not every lookup uses that stage, so always check keys/docs examined and index usage as well.

**15. Why is joining solely on `customerCode` dangerous in multi-tenant systems?**

Because customerCode can collide across tenants; an under-scoped join leaks cross-tenant data and inflates match counts. Always include tenant scope in the join or use a verified globally unique key.

**16. Can you paginate customers before joining?**

Yes, when paging, filtering, and sorting depend only on local fields. No, if page ordering or filtering depends on joined data.

**17. When is pre-aggregation better than looking up all orders?**

When dashboards frequently read counts/sums/top summaries over a large order history, reliably updated summaries remove heavy joins from the request path.

**18. Does sharding data automatically make lookups cheaper?**

No. If conditions do not route to specific shards, joins can fan out across many shards and incur heavy network overhead. Shard keys, routing, and plans must be evaluated.

## 32. Controlled Join Implementation Checklist

- [ ] Is the **output unit** defined: local document with array, or rows after unwind?
- [ ] Does the join key enforce proper **tenant/owner/business identity** and data types?
- [ ] Could local documents have missing/null keys causing unintended matches?
- [ ] Have you counted N local documents actually entering the lookup?
- [ ] Have you measured avg/P95/P99/max foreign matches per local key?
- [ ] Does the foreign collection have an index serving the equality/pipeline filters?
- [ ] Can the correlated `$expr` use an index on the target server version?
- [ ] Are there large foreign fields that should be trimmed via projection?
- [ ] Can foreign records be filtered early to reduce matches?
- [ ] Can foreign `$sort + $limit` be used when only top-N records need display?
- [ ] Have you distinguished total count from the length of a top-N array?
- [ ] Is there any risk of the joined array pushing a BSON document over 16 MiB?
- [ ] Are there multiple independent arrays and chained `$unwind` stages multiplying rows?
- [ ] If paginating locally before joining, is business ordering/filtering preserved?
- [ ] Have you inspected `explain("executionStats")` for both local and foreign sides and checked `indexesUsed` when available?
- [ ] Have you measured keys/docs examined, p95/p99 latency, output bytes, and spill on a sufficiently large dataset?
- [ ] If sharded, do lookup conditions support efficient shard routing?
- [ ] Have you considered materialized summaries or a paginated children API for large 1:N relationships?
- [ ] Are monitoring and rollback plans in place for index/join query changes in production?

## 33. Summary

`$lookup` performance cannot be judged solely by asking **"is there an index?"**. You must examine **three axes** together:

1. **Index / foreign access:** how many index keys and foreign documents must MongoDB inspect to find matches?
2. **Cardinality / fan-out:** how many local documents exist, how many foreign documents match each one, and what happens after `$unwind`?
3. **Payload / output:** how large is each joined element, how many total bytes flow through the pipeline, and is there a risk of hitting the 16 MiB BSON limit or triggering heavy memory/disk usage in later stages?

In practice, the priority order is usually: **get the join key right first**, filter local inputs early when semantics allow, build appropriate foreign indexes, push filters/projections/top-N into the foreign pipeline when only a subset is needed, avoid unwinding independent arrays into Cartesian products, and switch to precomputed summaries or paginated APIs for unbounded 1:N relationships. Finally, validate with `explain("executionStats")`, cardinality metrics, and result sizes **on a representative workload** rather than relying on syntax alone or small-lab timings.
