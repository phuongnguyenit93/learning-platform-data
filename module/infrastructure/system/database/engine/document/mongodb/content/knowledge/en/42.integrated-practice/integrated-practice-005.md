# Building Aggregation Reports and Verifying Results in MongoDB

## 1. Integrated Practice Problem

An e-commerce system stores orders in MongoDB. Operations wants a **monthly sales report by tenant**, including:

- Count of eligible orders for sales reporting.
- Merchandise value before discounts.
- Total discount amount.
- Sales after discounts but before refunds.
- Total refunded amount.
- **Net realized revenue per this lesson's definition**: order value after discounts minus refunded amount.
- Average order value.

A requirement more important than simply writing a pipeline is **proving the numbers are right**. A report that runs very fast with a nice table—yet counts `CANCELLED` orders or inflates revenue via a broken `$unwind`—is still an untrustworthy report.

### 1.1. Lesson Objectives

After this lesson, you can:

1. Translate business requirements into **testable KPI definitions**.
2. Design order documents containing currency, quantity, price, discount, refund, and status.
3. Use aggregation stages such as **$match**, **$project**, **$set**, **$group**, **$sort**, **$facet**, **$unwind**, and **$lookup** appropriately.
4. Define time ranges using **start-inclusive / end-exclusive** bounds and explicit timezones.
5. Compute sales using integer currency units or Decimal128, avoiding `double` precision errors.
6. Build reports by tenant, month, product, and category without duplicating rows.
7. Cross-verify using **hand-calculated results**, arithmetic invariants, and an independent query.
8. Test boundary conditions: cancelled, pending, refunded, partially refunded, and month boundaries.
9. Use `explain`/indexes to optimize and identify aggregation resource constraints.
10. Invoke pipelines from the Java Sync Driver or Spring Data MongoDB.
11. Design repeatable reports, CSV/JSON exports, data-quality monitoring, and regression detection.
12. Distinguish **correct calculation logic**, **correct input dataset**, **correct observation time**, and **proper access control**.

### 1.2. Overview Diagram

~~~text
Business question + KPI contract
             |
             v
   Data types / sample fixtures
             |
             v
    $match scope + time + status
             |
             v
   $project / $set derived fields
             |
             v
   $group tenant + calendar month
             |
             v
     $sort / format / export
             |
             v
   Independent verification
     |        |         |
  Hand math  Invariants  Data quality
             |
             v
    explain / index / monitoring
~~~

**Principle:** Never write an aggregation before knowing exactly **which data is included, which formula applies, which unit is used, and when a figure is considered valid**.

## 2. Locking Down the Report's Business Contract

### 2.1. Data Scope

In this lesson, each document represents **one order**. Each order belongs to a **tenantId** and has **createdAt** as a BSON Date.

The primary report covers the range:

~~~text
2026-01-01T00:00:00.000Z
           <= createdAt <
2026-03-01T00:00:00.000Z
~~~

That is, all of January and February 2026 **in UTC**. March 1st is excluded.

Included statuses:

~~~text
PAID
PARTIALLY_REFUNDED
REFUNDED
~~~

Excluded statuses:

~~~text
PENDING
CANCELLED
~~~

A fully refunded order is **still counted in `orderCount`** because it was a recorded order, while its net realized amount after refund is 0. This is a **convention of this practice report**, not a universal rule for all accounting systems.

### 2.2. KPI Formulas for a Single Order

Order documents have these fields:

| Field | Meaning | Stored Type in Lesson |
|---|---|---|
| **subtotalUnits** | Sum of quantity × unit price across line items, before discount | BSON Int64 |
| **discountUnits** | Total order discount, non-negative | BSON Int64 |
| **totalUnits** | Order value after discount, before refund | BSON Int64 |
| **refundUnits** | Refunded amount on the order | BSON Int64 |
| **realizedUnits** | Net amount after refund, computed in the pipeline | BSON numeric |

Formulas:

\[
\text{subtotal}=\sum_{i=1}^{n}(\text{quantity}_i\times\text{unitPrice}_i)
\]

\[
\text{total}=\text{subtotal}-\text{discount}
\]

\[
\text{realized}=\text{total}-\text{refund}
\]

Valid data assumptions:

~~~text
0 <= discountUnits <= subtotalUnits
0 <= refundUnits <= totalUnits
quantity > 0
unitPriceUnits >= 0
~~~

Do not use negative numbers to represent a refund in these examples: `refundUnits` is a **non-negative number subtracted from `total`**. A real ledger model may use signed entries, settlements, and fees; in that case, adjust formulas to match the official contract.

### 2.3. KPI Definitions for a Report Group

For a selected set of orders \(O\):

| KPI | Definition |
|---|---|
| **orderCount** | \(\lvert O\rvert\) |
| **grossUnits** | Sum of `subtotalUnits` |
| **discountUnits** | Sum of `discountUnits` |
| **netUnits** | Sum of `totalUnits` |
| **refundedUnits** | Sum of `refundUnits` |
| **realizedUnits** | Sum of `(totalUnits − refundUnits)` |
| **averageOrderValueUnits** | `netUnits / orderCount` |

Two group invariants:

\[
\text{grossUnits}-\text{discountUnits}=\text{netUnits}
\]

\[
\text{netUnits}-\text{refundedUnits}=\text{realizedUnits}
\]

**Average order value** in this lesson is calculated on **`netUnits`**, not `realizedUnits`; therefore, name and document definitions explicitly. When division yields decimals, AOV can be an approximate display metric; never use floating-point results for exact financial posting.

### 2.4. Currency and Tenant Authorization

The fixture uses **VND**, with all values as integers in a consistently defined currency unit. Never sum USD, EUR, and VND together without defined exchange rates and conversion timestamps.

In a multi-tenant application, **`tenantId` is a data access boundary**. Regular clients must receive their allowed tenant scope from the service layer; never trust a caller-supplied `tenantId` to access another tenant's data. Global multi-tenant reports in this lesson are intended only for appropriately authorized analytics accounts.

### 2.5. createdAt Is Not Always the Revenue Recognition Time

Real businesses may want to group by:

- **createdAt**: order creation date.
- **paidAt**: payment confirmation date.
- **fulfilledAt**: delivery date.
- **refundAt**: refund date.
- Accounting/settlement date per accounting period.

This practice lesson intentionally groups by **createdAt**. When revenue and refunds are recognized in different periods, you need an event/ledger model keyed by posting date rather than treating a `createdAt` report as a standard accounting statement.

## 3. Document Design and BSON Types

### 3.1. A Sample Order

~~~javascript
{
  _id: "A-001",
  tenantId: "tA",
  customerId: "c1",
  createdAt: ISODate("2026-01-05T10:00:00Z"),
  currency: "VND",
  status: "PAID",
  items: [
    {
      sku: "P1",
      category: "Accessories",
      qty: 2,
      unitPriceUnits: NumberLong("10000")
    },
    {
      sku: "P2",
      category: "Hardware",
      qty: 1,
      unitPriceUnits: NumberLong("20000")
    }
  ],
  subtotalUnits: NumberLong("40000"),
  discountUnits: NumberLong("0"),
  totalUnits: NumberLong("40000"),
  refundUnits: NumberLong("0")
}
~~~

Here:

~~~text
subtotal = 2 * 10000 + 1 * 20000 = 40000
total    = 40000 - 0            = 40000
realized = 40000 - 0            = 40000
~~~

### 3.2. Why Store Int64?

Sample monetary amounts are stored as **BSON Int64 / NumberLong** to avoid summing money via binary `double`. In Java, you can use **`long`** if domain totals fit within 64 bits with overflow checks.

For decimal currencies or multiple currencies with varying scales, **`BigDecimal` in Java and BSON Decimal128** is another option, with explicit precision/exponent control. Never convert Decimal128 to `double` to produce financial reports and treat the result as exact.

### 3.3. Source Values vs. Derived Values

In this schema, **subtotalUnits** and **totalUnits** are stored fields. During reporting, we can also recompute subtotal from `items`, and total from `subtotal − discount`.

Never assume stored data is infallibly consistent: legacy writer bugs, direct `mongosh` edits, or migrations can leave documents violating the formula.

### 3.4. Avoid Unwinding items in Ways That Double-Count

An order has two items. Using **`$unwind: "$items"`** turns that order into two pipeline documents. Grouping afterward and summing **`"$totalUnits"`** counts the entire order total **twice**.

~~~text
Order A-001: totalUnits=40000, 2 items

After $unwind:
  row P1 carries totalUnits=40000
  row P2 carries totalUnits=40000

Wrong $sum(totalUnits)=80000
Correct order total=40000
~~~

Therefore: **order-level reports do not need `$unwind` on `items`**. SKU/category reports can `$unwind`, but must sum only **line value**, or allocate discounts/refunds according to a clearly defined business rule.

## 4. Preparing a Fixed Dataset for Verification

All examples use database **reporting_lab_460**. This is an illustrative name for use strictly in an authorized lab MongoDB environment. **Never run write, drop, delete, or migration commands on a production database.**

### 4.1. Helper to Build Sample Documents

In `mongosh`, select an empty test database:

~~~javascript
const lab = db.getSiblingDB("reporting_lab_460");

function makeOrder(
  id, tenantId, isoDate, status, customerId,
  lines, subtotal, discount, refund
) {
  return {
    _id: id,
    tenantId,
    customerId,
    createdAt: ISODate(isoDate),
    currency: "VND",
    status,
    items: lines.map(([sku, category, qty, price]) => ({
      sku,
      category,
      qty,
      unitPriceUnits: NumberLong(String(price))
    })),
    subtotalUnits: NumberLong(String(subtotal)),
    discountUnits: NumberLong(String(discount)),
    totalUnits: NumberLong(String(subtotal - discount)),
    refundUnits: NumberLong(String(refund))
  };
}
~~~

In this helper, **subtotal/discount/refund** are small JavaScript integers, safe within the example's range. If seeding monetary values beyond JavaScript `Number`'s exact integer range, do not compute them with `Number` as in this helper; use **`Long`/Decimal128** and appropriate arithmetic.

### 4.2. Twelve Illustrative Orders

~~~javascript
lab.orders.insertMany([
  makeOrder(
    "A-001", "tA", "2026-01-05T10:00:00Z", "PAID", "c1",
    [
      ["P1", "Accessories", 2, 10000],
      ["P2", "Hardware", 1, 20000]
    ], 40000, 0, 0
  ),
  makeOrder(
    "A-002", "tA", "2026-01-12T11:00:00Z", "PAID", "c2",
    [
      ["P1", "Accessories", 1, 10000],
      ["P3", "Software", 1, 30000]
    ], 40000, 5000, 0
  ),
  makeOrder(
    "A-003", "tA", "2026-01-20T15:00:00Z", "REFUNDED", "c1",
    [
      ["P2", "Hardware", 1, 20000]
    ], 20000, 0, 20000
  ),
  makeOrder(
    "A-004", "tA", "2026-01-25T10:00:00Z", "CANCELLED", "c3",
    [
      ["P1", "Accessories", 1, 10000]
    ], 10000, 0, 0
  ),
  makeOrder(
    "A-005", "tA", "2026-02-03T08:00:00Z", "PAID", "c2",
    [
      ["P3", "Software", 2, 30000]
    ], 60000, 10000, 0
  ),
  makeOrder(
    "A-006", "tA", "2026-02-16T09:00:00Z",
    "PARTIALLY_REFUNDED", "c1",
    [
      ["P1", "Accessories", 3, 10000],
      ["P2", "Hardware", 1, 20000]
    ], 50000, 0, 10000
  ),
  makeOrder(
    "A-007", "tA", "2026-02-28T12:00:00Z", "PENDING", "c4",
    [
      ["P1", "Accessories", 1, 10000]
    ], 10000, 0, 0
  ),
  makeOrder(
    "A-008", "tA", "2026-03-01T00:00:00Z", "PAID", "c4",
    [
      ["P1", "Accessories", 1, 10000]
    ], 10000, 0, 0
  ),
  makeOrder(
    "B-001", "tB", "2026-01-09T10:00:00Z", "PAID", "c5",
    [
      ["P1", "Accessories", 4, 10000]
    ], 40000, 0, 0
  ),
  makeOrder(
    "B-002", "tB", "2026-01-23T11:00:00Z", "PAID", "c6",
    [
      ["P2", "Hardware", 2, 20000]
    ], 40000, 5000, 0
  ),
  makeOrder(
    "B-003", "tB", "2026-02-11T14:00:00Z", "REFUNDED", "c5",
    [
      ["P3", "Software", 1, 30000]
    ], 30000, 0, 30000
  ),
  makeOrder(
    "B-004", "tB", "2026-02-19T08:00:00Z", "PAID", "c6",
    [
      ["P2", "Hardware", 1, 20000],
      ["P3", "Software", 1, 30000]
    ], 50000, 0, 0
  )
]);
~~~

**Run `insertMany` only once on an empty fixture.** Re-running with the same IDs will hit duplicate-key errors; to repeat the exercise, create a new test database or clean up only the test IDs you own through a dedicated procedure. Never drop a shared database automatically.

### 4.3. Why Intentionally Include Excluded Orders?

| Order | Scenario | Expected in Jan–Feb Report |
|---|---|---|
| **A-004** | `CANCELLED` in Jan | Excluded due to status. |
| **A-007** | `PENDING` in Feb | Excluded due to status. |
| **A-008** | `PAID` at exact `00:00:00Z` on Mar 01 | Excluded by end-exclusive boundary. |
| **A-003** | Fully `REFUNDED` in Jan | Included in `orderCount`, `realized=0`. |
| **A-006** | `PARTIALLY_REFUNDED` in Feb | Included in `orderCount`, `realized=40000`. |
| **B-003** | Fully `REFUNDED` in Feb | Included in `orderCount`, `realized=0`. |

These records are **intentional test cases**, not stray data.

### 4.4. Checking Seed Count

~~~javascript
lab.orders.countDocuments({});
~~~

Expected fixture count is **12 documents**. When the report filters range and statuses accurately, only **9 orders** enter aggregation.

Counting documents **is not enough to prove KPIs are right**. We will reconcile counts, monetary totals, and order identities in later sections.

## 5. Building a Hand-Calculated Verification Table Before Writing the Pipeline

### 5.1. Eligible Orders

| Tenant | UTC Month | Order | Subtotal | Discount | Total | Refund | Realized |
|---|---|---|---:|---:|---:|---:|---:|
| tA | 2026-01 | A-001 | 40.000 | 0 | 40.000 | 0 | 40.000 |
| tA | 2026-01 | A-002 | 40.000 | 5.000 | 35.000 | 0 | 35.000 |
| tA | 2026-01 | A-003 | 20.000 | 0 | 20.000 | 20.000 | 0 |
| tA | 2026-02 | A-005 | 60.000 | 10.000 | 50.000 | 0 | 50.000 |
| tA | 2026-02 | A-006 | 50.000 | 0 | 50.000 | 10.000 | 40.000 |
| tB | 2026-01 | B-001 | 40.000 | 0 | 40.000 | 0 | 40.000 |
| tB | 2026-01 | B-002 | 40.000 | 5.000 | 35.000 | 0 | 35.000 |
| tB | 2026-02 | B-003 | 30.000 | 0 | 30.000 | 30.000 | 0 |
| tB | 2026-02 | B-004 | 50.000 | 0 | 50.000 | 0 | 50.000 |

### 5.2. Aggregated Oracle by Tenant and Month

<text>Unit: VND per fixture; dots in the table are thousand separators.</text>

| Tenant | Month | Order Count | Gross | Discount | Net | Refunded | Realized |
|---|---|---:|---:|---:|---:|---:|---:|
| **tA** | 2026-01 | 3 | 100.000 | 5.000 | 95.000 | 20.000 | **75.000** |
| **tA** | 2026-02 | 2 | 110.000 | 10.000 | 100.000 | 10.000 | **90.000** |
| **tB** | 2026-01 | 2 | 80.000 | 5.000 | 75.000 | 0 | **75.000** |
| **tB** | 2026-02 | 2 | 80.000 | 0 | 80.000 | 30.000 | **50.000** |

This is the lesson's **oracle**: expected outputs defined before running the pipeline. If output differs, investigate the root cause rather than altering the oracle to match the output.

### 5.3. Monthly and Overall Totals Oracle

| Period | Orders | Gross | Discount | Net | Refund | Realized |
|---|---:|---:|---:|---:|---:|---:|
| Month 1 | 5 | 180.000 | 10.000 | 170.000 | 20.000 | **150.000** |
| Month 2 | 4 | 190.000 | 10.000 | 180.000 | 40.000 | **140.000** |
| **Full Period** | **9** | **370.000** | **20.000** | **350.000** | **60.000** | **290.000** |

Cross-check:

~~~text
Gross - Discount = Net
370000 - 20000  = 350000

Net - Refund = Realized
350000 - 60000 = 290000

Monthly realized
150000 + 140000 = 290000

Tenant realized
(75000 + 90000) + (75000 + 50000) = 290000
~~~

**Satisfying an invariant does not guarantee the entire report is correct.** For example, if every field were double-counted by a buggy `$unwind`, both equations would still hold while the totals are wrong. Therefore, an **independent oracle plus order count/ID checks** are required.

## 6. Building the First Aggregation: by Tenant and Month

### 6.1. Step 1 — Define Date Range and Statuses

~~~javascript
const start = ISODate("2026-01-01T00:00:00.000Z");
const end = ISODate("2026-03-01T00:00:00.000Z");

const eligibleStates = [
  "PAID",
  "PARTIALLY_REFUNDED",
  "REFUNDED"
];
~~~

Note that MongoDB compares **BSON Dates as instants**, not display date strings. The `Date` objects here represent UTC instants.

### 6.2. Step 2 — Filter Data with $match

~~~javascript
{
  $match: {
    createdAt: { $gte: start, $lt: end },
    status: { $in: eligibleStates },
    currency: "VND"
  }
}
~~~

Explanation:

- **`$gte`** includes the exact start of the period.
- **`$lt`** excludes the start of the next period.
- **`$in`** specifies the exact three eligible statuses.
- **`currency`** prevents accidentally summing different currencies together.

For a tenant-scoped report, add **`tenantId: authorizedTenantId`** derived from the authentication/authorization layer. Never accept an arbitrary `tenantId` from a caller and treat it as sufficient security.

### 6.3. Step 3 — Project Fields and Compute realizedUnits

~~~javascript
{
  $project: {
    tenantId: 1,
    month: {
      $dateToString: {
        format: "%Y-%m",
        date: "$createdAt",
        timezone: "UTC"
      }
    },
    subtotalUnits: 1,
    discountUnits: 1,
    totalUnits: 1,
    refundUnits: 1,
    realizedUnits: {
      $subtract: ["$totalUnits", "$refundUnits"]
    }
  }
}
~~~

**`$dateToString`** builds a month key such as **`"2026-01"`** in UTC. Always specify a consistent timezone so an order near midnight isn't bucketed into a different month when run in another environment.

**`$subtract`** computes `realizedUnits` per order before grouping. Do not subtract refunds twice if upstream already stored **`totalUnits` net of refunds**; that is why the data contract must be explicit.

### 6.4. Step 4 — Group and Compute KPIs

~~~javascript
{
  $group: {
    _id: {
      tenantId: "$tenantId",
      month: "$month"
    },
    orderCount: { $sum: 1 },
    grossUnits: { $sum: "$subtotalUnits" },
    discountUnits: { $sum: "$discountUnits" },
    netUnits: { $sum: "$totalUnits" },
    refundedUnits: { $sum: "$refundUnits" },
    realizedUnits: { $sum: "$realizedUnits" }
  }
}
~~~

**`$group`** aggregates documents by **two keys**: `tenantId` and `month`. Each order contributes exactly once because this pipeline **does not unwind `items`**.

### 6.5. Step 5 — Compute AOV and Sort

~~~javascript
{
  $set: {
    averageOrderValueUnits: {
      $cond: [
        { $gt: ["$orderCount", 0] },
        { $divide: ["$netUnits", "$orderCount"] },
        null
      ]
    }
  }
}
~~~

In this pipeline, all actual groups have `orderCount ≥ 1`; **`$cond`** demonstrates guarding against division by zero if logic changes.

Because **`$divide`** can yield non-integer results, AOV is an average metric that may need display rounding. Primary sums should retain exact numeric types. Define rounding and scale policies at the reporting/presentation layer; never use floating-point results to drive monetary transactions.

### 6.6. Complete Runnable Pipeline

~~~javascript
const pipeline = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  {
    $project: {
      tenantId: 1,
      month: {
        $dateToString: {
          format: "%Y-%m",
          date: "$createdAt",
          timezone: "UTC"
        }
      },
      subtotalUnits: 1,
      discountUnits: 1,
      totalUnits: 1,
      refundUnits: 1,
      realizedUnits: {
        $subtract: ["$totalUnits", "$refundUnits"]
      }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        month: "$month"
      },
      orderCount: { $sum: 1 },
      grossUnits: { $sum: "$subtotalUnits" },
      discountUnits: { $sum: "$discountUnits" },
      netUnits: { $sum: "$totalUnits" },
      refundedUnits: { $sum: "$refundUnits" },
      realizedUnits: { $sum: "$realizedUnits" }
    }
  },
  {
    $set: {
      averageOrderValueUnits: {
        $cond: [
          { $gt: ["$orderCount", 0] },
          { $divide: ["$netUnits", "$orderCount"] },
          null
        ]
      }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.month": 1
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      month: "$_id.month",
      orderCount: 1,
      grossUnits: 1,
      discountUnits: 1,
      netUnits: 1,
      refundedUnits: 1,
      realizedUnits: 1,
      averageOrderValueUnits: 1
    }
  }
];

lab.orders.aggregate(pipeline).toArray();
~~~

When running in a new `mongosh` block, ensure **`lab`, `start`, `end`, `eligibleStates`** were declared earlier in the same session, or redeclare them.

### 6.7. Expected Output

Omitting `averageOrderValueUnits` for concise display, the pipeline returns **four groups**:

~~~javascript
[
  {
    tenantId: "tA",
    month: "2026-01",
    orderCount: 3,
    grossUnits: NumberLong("100000"),
    discountUnits: NumberLong("5000"),
    netUnits: NumberLong("95000"),
    refundedUnits: NumberLong("20000"),
    realizedUnits: NumberLong("75000")
  },
  {
    tenantId: "tA",
    month: "2026-02",
    orderCount: 2,
    grossUnits: NumberLong("110000"),
    discountUnits: NumberLong("10000"),
    netUnits: NumberLong("100000"),
    refundedUnits: NumberLong("10000"),
    realizedUnits: NumberLong("90000")
  },
  {
    tenantId: "tB",
    month: "2026-01",
    orderCount: 2,
    grossUnits: NumberLong("80000"),
    discountUnits: NumberLong("5000"),
    netUnits: NumberLong("75000"),
    refundedUnits: NumberLong("0"),
    realizedUnits: NumberLong("75000")
  },
  {
    tenantId: "tB",
    month: "2026-02",
    orderCount: 2,
    grossUnits: NumberLong("80000"),
    discountUnits: NumberLong("0"),
    netUnits: NumberLong("80000"),
    refundedUnits: NumberLong("30000"),
    realizedUnits: NumberLong("50000")
  }
]
~~~

This is an **illustrative representation of the main KPI fields**, not a literal dump: actual output also includes `averageOrderValueUnits`, and how `mongosh` renders BSON `Long` depends on the shell/version.

### 6.8. Expected AOV

| Tenant | Month | AOV = net / orders |
|---|---|---:|
| tA | 2026-01 | 95.000 / 3 ≈ **31.666,67** |
| tA | 2026-02 | 100.000 / 2 = **50.000** |
| tB | 2026-01 | 75.000 / 2 = **37.500** |
| tB | 2026-02 | 80.000 / 2 = **40.000** |

If a dashboard needs AOV **after refunds**, assign a distinct name such as `realizedAverageUnits = realizedUnits / orderCount` rather than changing the formula under the old name.

### 6.9. $dateTrunc as an Alternative Grouping Method

On supported server versions (e.g., MongoDB 5.0+), you can use:

~~~javascript
{
  $dateTrunc: {
    date: "$createdAt",
    unit: "month",
    timezone: "UTC"
  }
}
~~~

Unlike the string **`"2026-01"`**, `$dateTrunc` returns a **Date instant** representing the month bucket. This is useful for time-series APIs and range operations. Pick one output contract and keep it consistent; never mix `Date` and `String` month keys in the same grouping without converting.

## 7. Using $facet for Multiple Perspectives from the Same Dataset

Operations often wants a single response containing:

- Report by **tenant + month**.
- Report across **all tenants grouped by month**.
- Overall period totals.

You can run three separate aggregations, but when all views share the exact same filters and KPI definitions, **`$facet`** organizes them within one pipeline.

### 7.1. $facet Structure

~~~text
orders
  |
  +-- $match date / states / currency
  |
  +-- $project month + derived values
  |
  +-- $facet
        |
        +-- byTenantMonth -> $group tenant/month
        |
        +-- byMonth       -> $group month
        |
        +-- overall       -> $group all
~~~

Placing **`$match` before `$facet`** shrinks the input set and allows MongoDB to leverage indexes during filtering where applicable.

### 7.2. Writing a Pipeline That Reuses KPI Definitions

~~~javascript
const baseStages = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  {
    $project: {
      tenantId: 1,
      month: {
        $dateToString: {
          format: "%Y-%m",
          date: "$createdAt",
          timezone: "UTC"
        }
      },
      subtotalUnits: 1,
      discountUnits: 1,
      totalUnits: 1,
      refundUnits: 1,
      realizedUnits: {
        $subtract: ["$totalUnits", "$refundUnits"]
      }
    }
  }
];

const metricAccumulators = {
  orderCount: { $sum: 1 },
  grossUnits: { $sum: "$subtotalUnits" },
  discountUnits: { $sum: "$discountUnits" },
  netUnits: { $sum: "$totalUnits" },
  refundedUnits: { $sum: "$refundUnits" },
  realizedUnits: { $sum: "$realizedUnits" }
};

function groupMetrics(idExpression) {
  return {
    $group: {
      _id: idExpression,
      ...metricAccumulators
    }
  };
}

const facetPipeline = [
  ...baseStages,
  {
    $facet: {
      byTenantMonth: [
        groupMetrics({
          tenantId: "$tenantId",
          month: "$month"
        }),
        { $sort: { "_id.tenantId": 1, "_id.month": 1 } }
      ],
      byMonth: [
        groupMetrics("$month"),
        { $sort: { _id: 1 } }
      ],
      overall: [
        groupMetrics(null)
      ]
    }
  }
];

const report = lab.orders.aggregate(facetPipeline).toArray()[0];
printjson(report);
~~~

This snippet assumes **`start`, `end`, `eligibleStates`** are already declared. Each `$facet` branch processes the documents produced by `baseStages`; each branch does not re-scan the entire collection.

### 7.3. Expected byMonth Branch

~~~javascript
[
  {
    _id: "2026-01",
    orderCount: 5,
    grossUnits: NumberLong("180000"),
    discountUnits: NumberLong("10000"),
    netUnits: NumberLong("170000"),
    refundedUnits: NumberLong("20000"),
    realizedUnits: NumberLong("150000")
  },
  {
    _id: "2026-02",
    orderCount: 4,
    grossUnits: NumberLong("190000"),
    discountUnits: NumberLong("10000"),
    netUnits: NumberLong("180000"),
    refundedUnits: NumberLong("40000"),
    realizedUnits: NumberLong("140000")
  }
]
~~~

### 7.4. Expected overall Branch

~~~javascript
[
  {
    _id: null,
    orderCount: 9,
    grossUnits: NumberLong("370000"),
    discountUnits: NumberLong("20000"),
    netUnits: NumberLong("350000"),
    refundedUnits: NumberLong("60000"),
    realizedUnits: NumberLong("290000")
  }
]
~~~

### 7.5. Checking Relationships Across Report Levels

~~~text
sum(byTenantMonth.orderCount)
  = sum(byMonth.orderCount)
  = overall.orderCount
  = 9

sum(byTenantMonth.realizedUnits)
  = sum(byMonth.realizedUnits)
  = overall.realizedUnits
  = 290000
~~~

If two branches had differing filters or an `$unwind` stage sat before `$facet`, these reconciliations would fail. Sharing `baseStages` minimizes filter drift.

### 7.6. Mind the Limits of $facet

`$facet` is convenient for moderately sized reports, but do not return hundreds of thousands of groups in a single BSON response:

- Each branch consumes memory and CPU.
- The resulting document must fit within the BSON document size limit.
- `$facet` has dedicated memory limits; `allowDiskUse` does not make `$facet` limits infinite.
- `$sort`/`$group` may require optimization before running on large sets.
- For large reports, use separate pipelines, pagination, or materialized results.

**Do not use `$facet` merely to write one command instead of three** if the report size or resource footprint exceeds safe limits.

## 8. Category Reporting: When to Use $unwind?

If the question is **which product category sold the highest merchandise value before discounts**, you must inspect each **`items`** element in the orders.

### 8.1. Unwinding Each Line Item

~~~javascript
{
  $unwind: "$items"
}
~~~

After this stage, an order with two items yields **two pipeline rows**. That is right for line-item reporting, but wrong if you sum the full order total on each row.

### 8.2. Category Gross Sales Pipeline

~~~javascript
const categoryPipeline = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.category",
      unitsSold: { $sum: "$items.qty" },
      lineGrossUnits: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceUnits"
          ]
        }
      },
      uniqueOrders: { $addToSet: "$_id" }
    }
  },
  {
    $project: {
      _id: 0,
      category: "$_id",
      unitsSold: 1,
      lineGrossUnits: 1,
      orderCount: { $size: "$uniqueOrders" }
    }
  },
  { $sort: { lineGrossUnits: -1, category: 1 } }
];

lab.orders.aggregate(categoryPipeline).toArray();
~~~

Here **`$multiply`** computes `qty × unitPriceUnits` for each item's gross amount; **`$addToSet`** and **`$size`** count distinct orders per category rather than line-item rows.

### 8.3. Expected Results by Category

| Category | Units Sold | Distinct Orders | Gross Line Value |
|---|---:|---:|---:|
| **Software** | 5 | 4 | **150.000** |
| **Hardware** | 6 | 5 | **120.000** |
| **Accessories** | 10 | 4 | **100.000** |
| **Total** | **21** | *Do not sum category `orderCount`* | **370.000** |

Total category gross:

~~~text
150000 + 120000 + 100000 = 370000
~~~

This must equal **`overall.grossUnits`** because the fixture assigns exactly one category to each line item and every line is included.

**Never sum `orderCount` across categories to infer total orders**: an order spanning multiple categories appears in multiple groups. For instance, `A-001` belongs to both `Accessories` and `Hardware`.

### 8.4. Never Attribute Whole-Order Discounts/Refunds to Each Item

Wrong approach:

~~~javascript
[
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.category",
      wrongRefund: { $sum: "$refundUnits" }
    }
  }
]
~~~

Order `A-006` has two items and `refundUnits=10000`; summing the full order refund per line counts 20000 instead of 10000.

To report **net/realized by category**, you need a **discount/refund allocation rule** (actual line-level refunds, proportional allocation with explicit rounding/remainder handling, or an event-level ledger). Without that rule, name the metric accurately as **category gross line value**, never "category net revenue."

### 8.5. SKU Report

Group by SKU instead of category:

~~~javascript
{
  $group: {
    _id: "$items.sku",
    unitsSold: { $sum: "$items.qty" },
    grossUnits: {
      $sum: {
        $multiply: ["$items.qty", "$items.unitPriceUnits"]
      }
    }
  }
}
~~~

In the fixture, SKUs `P1`/`P2`/`P3` map one-to-one to the three categories, so total SKU gross also equals **370000**. In production, a SKU can move between categories over time; decide whether to group by the **order-time category snapshot** or the current catalog.

## 9. $lookup: Enriching Reports with Product Names

A SKU report may need **`displayName`** from the **`products`** collection. `$lookup` fits when reference data is small or indexed with an appropriate query shape.

### 9.1. Seeding the Lab Catalog

~~~javascript
lab.products.insertMany([
  { _id: "P1", displayName: "Travel pouch" },
  { _id: "P2", displayName: "USB hub" },
  { _id: "P3", displayName: "Software license" }
]);
~~~

Insert only into an empty lab catalog; do not rerun with duplicate IDs.

### 9.2. Join After Grouping to Minimize Lookups

~~~javascript
const skuPipeline = [
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: eligibleStates },
      currency: "VND"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: { $sum: "$items.qty" },
      grossUnits: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceUnits"
          ]
        }
      }
    }
  },
  {
    $lookup: {
      from: "products",
      localField: "_id",
      foreignField: "_id",
      as: "product"
    }
  },
  {
    $set: {
      displayName: { $arrayElemAt: ["$product.displayName", 0] }
    }
  },
  {
    $project: {
      product: 0
    }
  },
  { $sort: { grossUnits: -1, _id: 1 } }
];

lab.orders.aggregate(skuPipeline).toArray();
~~~

After `$group`, there are only three SKU keys, so `$lookup` enriches just three groups instead of joining every line item prior to aggregation.

### 9.3. Do Not Drop Sales When a Lookup Misses

If a SKU is missing from `products`, **`$lookup`** returns an empty array; `displayName` becomes null/missing, yet the gross sales row should still be preserved.

If you add **`$unwind: "$product"`** without **`preserveNullAndEmptyArrays`**, SKU groups missing from the catalog silently vanish from the report—causing silent revenue loss without any error.

### 9.4. Historical Category vs. Current Catalog

Product `P1` might change category today. If the report requires the category at the time of sale, use **`items.category`** from the order snapshot. If the report requires the current category, `$lookup` the product and group by catalog. Both reports can yield different numbers without either being wrong; **the business definition decides**.

## 10. Verification Layer 1 — Right Input Dataset

Before checking `$sum` arithmetic, verify **which orders** are allowed into the report.

### 10.1. Counting Eligible Orders

~~~javascript
const scope = {
  createdAt: { $gte: start, $lt: end },
  status: { $in: eligibleStates },
  currency: "VND"
};

lab.orders.countDocuments(scope);
~~~

Expected: **9**.

### 10.2. Comparing the ID List Rather Than Count Alone

~~~javascript
const expectedIds = [
  "A-001", "A-002", "A-003",
  "A-005", "A-006",
  "B-001", "B-002", "B-003", "B-004"
].sort();

const actualIds = lab.orders
  .find(scope, { _id: 1 })
  .sort({ _id: 1 })
  .toArray()
  .map(order => order._id);

if (JSON.stringify(actualIds) !== JSON.stringify(expectedIds)) {
  throw new Error(
    "Selected order IDs differ from the fixture contract"
  );
}

print("Selected order IDs: PASS");
~~~

This check is critical: a buggy filter might still count 9 orders by accidentally dropping one valid order and including one invalid order. Comparing IDs catches that.

### 10.3. Inspecting Excluded Orders Individually

~~~javascript
lab.orders.find(
  { _id: { $in: ["A-004", "A-007", "A-008"] } },
  { _id: 1, createdAt: 1, status: 1 }
).sort({ _id: 1 });
~~~

Expected reasons:

- `A-004` excluded due to **`CANCELLED`**.
- `A-007` excluded due to **`PENDING`**.
- `A-008` excluded due to **`createdAt = end`**, not its status.

**Never patch a filter by adding ID-based exclusion rules.** IDs here serve solely as the test oracle.

### 10.4. Checking Per Tenant

~~~javascript
lab.orders.countDocuments({
  ...scope,
  tenantId: "tA"
});

lab.orders.countDocuments({
  ...scope,
  tenantId: "tB"
});
~~~

Expected: **`tA = 5`**, **`tB = 4`**.

## 11. Verification Layer 2 — Comparing Aggregation Output Against a Fixed Oracle

### 11.1. Oracle Table as Test Data

In this lesson, amounts are small enough to express with exact integer literals:

~~~javascript
const expectedGroups = new Map([
  ["tA|2026-01", {
    orders: 3, gross: 100000, discount: 5000,
    net: 95000, refund: 20000, realized: 75000
  }],
  ["tA|2026-02", {
    orders: 2, gross: 110000, discount: 10000,
    net: 100000, refund: 10000, realized: 90000
  }],
  ["tB|2026-01", {
    orders: 2, gross: 80000, discount: 5000,
    net: 75000, refund: 0, realized: 75000
  }],
  ["tB|2026-02", {
    orders: 2, gross: 80000, discount: 0,
    net: 80000, refund: 30000, realized: 50000
  }]
]);
~~~

### 11.2. Assertions Without Converting BSON Long Through Double

~~~javascript
function asBigInt(value) {
  return BigInt(value.toString());
}

const actualGroups = lab.orders.aggregate(pipeline).toArray();

if (actualGroups.length !== expectedGroups.size) {
  throw new Error("Unexpected number of report groups");
}

for (const row of actualGroups) {
  const key = row.tenantId + "|" + row.month;
  const expected = expectedGroups.get(key);

  if (!expected) {
    throw new Error("Unexpected report group: " + key);
  }

  if (row.orderCount !== expected.orders
      || asBigInt(row.grossUnits) !== BigInt(expected.gross)
      || asBigInt(row.discountUnits) !== BigInt(expected.discount)
      || asBigInt(row.netUnits) !== BigInt(expected.net)
      || asBigInt(row.refundedUnits) !== BigInt(expected.refund)
      || asBigInt(row.realizedUnits) !== BigInt(expected.realized)) {
    throw new Error("KPI mismatch for " + key);
  }
}

print("Tenant/month report: PASS");
~~~

JavaScript **`BigInt`** compares integer values converted from BSON `Long` accurately; never use **`Number(...)`** on values that may exceed **`Number.MAX_SAFE_INTEGER`**.

In the lab, expected integer literals are well within safe limits. For production-scale oracles, use expected strings/`BigInt` or explicitly handled Decimal128.

### 11.3. Why Not Check Only realizedUnits?

Two bugs can cancel each other out:

~~~text
Gross report too high by 10000
Discount report too high by 10000
Net appears correct
~~~

Checking only `net` misses bugs in `gross` and `discount`. Always assert **every key KPI**, order counts, and group keys.

### 11.4. Checking Per-Group Invariants

~~~javascript
for (const row of actualGroups) {
  const gross = asBigInt(row.grossUnits);
  const discount = asBigInt(row.discountUnits);
  const net = asBigInt(row.netUnits);
  const refunded = asBigInt(row.refundedUnits);
  const realized = asBigInt(row.realizedUnits);

  if (gross - discount !== net) {
    throw new Error("Gross-discount != net");
  }
  if (net - refunded !== realized) {
    throw new Error("Net-refund != realized");
  }
}

print("Report invariants: PASS");
~~~

This is a supplementary check, **not a substitute for the oracle**. If all fields were doubled, arithmetic invariants would still pass.

## 12. Verification Layer 3 — Independent Computation Outside Aggregation

One way to reduce the risk of writing the same buggy expression in two places is **reconciling with an independent algorithm**. For illustration, we iterate a regular cursor and sum directly in `mongosh` instead of `$group`.

### 12.1. Independent Fold via find()

~~~javascript
const folded = new Map();

lab.orders.find(scope).forEach(order => {
  const month = order.createdAt.toISOString().slice(0, 7);
  const key = order.tenantId + "|" + month;

  if (!folded.has(key)) {
    folded.set(key, {
      count: 0,
      gross: 0n,
      discount: 0n,
      net: 0n,
      refund: 0n,
      realized: 0n
    });
  }

  const row = folded.get(key);
  const subtotal = asBigInt(order.subtotalUnits);
  const discount = asBigInt(order.discountUnits);
  const total = asBigInt(order.totalUnits);
  const refund = asBigInt(order.refundUnits);

  row.count += 1;
  row.gross += subtotal;
  row.discount += discount;
  row.net += total;
  row.refund += refund;
  row.realized += total - refund;
});

printjson(
  [...folded.entries()].map(([key, row]) => ({
    key,
    count: row.count,
    gross: row.gross.toString(),
    discount: row.discount.toString(),
    net: row.net.toString(),
    refund: row.refund.toString(),
    realized: row.realized.toString()
  }))
);
~~~

Benefits:

- Month buckets are derived via **`Date.toISOString().slice(0,7)`**, not `$dateToString`.
- Sums are computed client-side with **`BigInt`**, not `$group`.
- Individual documents can be inspected when mismatches occur.

Limitations:

- Still relies on the **same source data and filter scope**. If the business contract is wrong from the start, both methods can agree on the wrong answer.
- Streaming all matching documents to the client does not scale to millions of orders.
- Client-side folding in `mongosh` here is strictly for **small deterministic fixtures / debugging**. Production validation uses sampled batches, reconciliation pipelines, or a source-of-truth ledger.

### 12.2. Comparing the Independent Fold Against Aggregation

~~~javascript
for (const row of actualGroups) {
  const key = row.tenantId + "|" + row.month;
  const independent = folded.get(key);

  if (!independent
      || independent.count !== row.orderCount
      || independent.gross !== asBigInt(row.grossUnits)
      || independent.discount !== asBigInt(row.discountUnits)
      || independent.net !== asBigInt(row.netUnits)
      || independent.refund !== asBigInt(row.refundedUnits)
      || independent.realized !== asBigInt(row.realizedUnits)) {
    throw new Error("Independent reconciliation failed: " + key);
  }
}

print("Independent fold reconciliation: PASS");
~~~

When comparing groups, verify both **group count and keys** so no extra group in `folded` goes unchecked by the loop.

### 12.3. Comparing Three Sources of Evidence

| Source | Proves | Does Not Prove Alone |
|---|---|---|
| **Hand-calculated table** | Independent oracle for the fixture. | Correctness across all live production data. |
| **Aggregation pipeline** | Output of the calculation deployed on MongoDB. | That the business contract itself is right. |
| **Client-side fold** | An independent implementation over the same records. | Uncorrupted source data or valid filter scope. |

Combining all three is far stronger than trusting a single output.

## 13. Verification Layer 4 — Source Data Quality

An aggregation can be written flawlessly and still output wrong numbers if a document has an invalid **`totalUnits`**, **`refundUnits`** exceeding `total`, or monetary fields stored as Strings.

### 13.1. Checking Formulas on Every Order

An audit independent of reporting groups:

~~~javascript
const inconsistentTotals = lab.orders.aggregate([
  {
    $project: {
      _id: 1,
      subtotalUnits: 1,
      discountUnits: 1,
      totalUnits: 1,
      refundUnits: 1,
      recomputedTotalUnits: {
        $subtract: ["$subtotalUnits", "$discountUnits"]
      }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          {
            $ne: [
              "$totalUnits",
              "$recomputedTotalUnits"
            ]
          },
          { $lt: ["$discountUnits", 0] },
          { $gt: ["$discountUnits", "$subtotalUnits"] },
          { $lt: ["$refundUnits", 0] },
          { $gt: ["$refundUnits", "$totalUnits"] }
        ]
      }
    }
  }
]).toArray();

printjson(inconsistentTotals);
~~~

Expected on the standard fixture: **empty array**. If records appear, never "patch the report math" to hide bad data. Investigate the writer/migration source and execute an approved data remediation plan.

### 13.2. Recomputing Subtotal from Items

~~~javascript
const badSubtotals = lab.orders.aggregate([
  {
    $project: {
      _id: 1,
      storedSubtotal: "$subtotalUnits",
      recomputedSubtotal: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.unitPriceUnits"
              ]
            }
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: {
        $ne: ["$storedSubtotal", "$recomputedSubtotal"]
      }
    }
  }
]).toArray();

printjson(badSubtotals);
~~~

For valid documents where `items` is an array, **`$map`** produces line subtotals and **`$sum`** adds them. Expected: **no mismatches**.

If `items` is null/missing or not an array, the pipeline may error or produce different semantics. Treat that as a separate schema error rather than silently assuming null/empty `items` means a valid 0-subtotal order.

### 13.3. Checking BSON Types

In `mongosh`:

~~~javascript
lab.orders.aggregate([
  {
    $project: {
      _id: 1,
      createdAtType: { $type: "$createdAt" },
      subtotalType: { $type: "$subtotalUnits" },
      discountType: { $type: "$discountUnits" },
      totalType: { $type: "$totalUnits" },
      refundType: { $type: "$refundUnits" },
      itemsType: { $type: "$items" }
    }
  },
  {
    $match: {
      $or: [
        { createdAtType: { $ne: "date" } },
        { subtotalType: { $ne: "long" } },
        { discountType: { $ne: "long" } },
        { totalType: { $ne: "long" } },
        { refundType: { $ne: "long" } },
        { itemsType: { $ne: "array" } }
      ]
    }
  }
]);
~~~

The fixture requires **`date`**, **`long`**, and **`array`** per the schema table. A document with `"40000"` as a String can be skipped or handled unexpectedly by `$sum`, skewing reports without always throwing an error.

### 13.4. Out-of-Contract Status Values

~~~javascript
lab.orders.find(
  {
    status: {
      $nin: [
        "PAID",
        "PARTIALLY_REFUNDED",
        "REFUNDED",
        "PENDING",
        "CANCELLED"
      ]
    }
  },
  { _id: 1, status: 1 }
);
~~~

If a writer introduces **`PAID_SUCCESS`** while the report still filters the old status list, orders silently drop out of the report without exceptions. Data-quality monitoring must alert on unknown values.

### 13.5. Auditing Refund Rules by Status

In the fixture:

| Status | Lesson Refund Policy |
|---|---|
| `PAID` | `refundUnits = 0` |
| `PARTIALLY_REFUNDED` | `0 < refundUnits < totalUnits` |
| `REFUNDED` | `refundUnits = totalUnits` |
| `PENDING` / `CANCELLED` | Excluded from report |

In production, refunds may be tracked via separate events where order status does not capture the entire history. **Never apply the fixture's status policy to mutate real data if the domain contract differs.**

### 13.6. Example Query Finding Status Policy Violations

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      $or: [
        {
          status: "PAID",
          $expr: { $ne: ["$refundUnits", 0] }
        },
        {
          status: "REFUNDED",
          $expr: { $ne: ["$refundUnits", "$totalUnits"] }
        },
        {
          status: "PARTIALLY_REFUNDED",
          $expr: {
            $or: [
              { $lte: ["$refundUnits", 0] },
              { $gte: ["$refundUnits", "$totalUnits"] }
            ]
          }
        }
      ]
    }
  },
  { $project: { _id: 1, status: 1, totalUnits: 1, refundUnits: 1 } }
]);
~~~

Expected to return zero records in the fixture. In production, validation policies should be versioned and reviewed with the business team.

### 13.7. Checking Referential Integrity

A document contains **`items.sku`**, yet the product catalog lacks that SKU. MongoDB does not enforce RDBMS-equivalent foreign-key constraints across all schemas.

If the report needs `displayName`:

- Detect missing products via `$lookup`.
- Never drop orders/items from revenue merely because a catalog entry is missing.
- Provide a fallback label such as **`Unknown SKU`** if allowed by the reporting contract.
- Log data-quality issues to fix at the source.

### 13.8. Validation at Write Time

Consider combining:

- Schema validation (**`$jsonSchema`**) for BSON types and required fields.
- Application/domain validation for formulas and business rules.
- Unique indexes for IDs and expressible constraints.
- Periodic data-quality audits.
- Audited migrations/backfills when schemas evolve.

Do not rely solely on a MongoDB collection validator to enforce **`sum(items) − discount = total`** or authorization; complex invariants still require application logic and verification.

## 14. Verifying Time Ranges, Timezones, and Reporting Periods

### 14.1. Why Use [start, end)?

Suppose January's report is:

~~~text
2026-01-01T00:00:00Z <= createdAt
createdAt < 2026-02-01T00:00:00Z
~~~

February's report is:

~~~text
2026-02-01T00:00:00Z <= createdAt
createdAt < 2026-03-01T00:00:00Z
~~~

There are no gaps or overlaps between consecutive periods. Using **`$lte end`** risks counting an order at exact `00:00` on the first of the next month **twice**.

### 14.2. Why Not Use 23:59:59.999?

An error-prone pattern:

~~~javascript
{
  createdAt: {
    $gte: ISODate("2026-01-01T00:00:00Z"),
    $lte: ISODate("2026-01-31T23:59:59Z")
  }
}
~~~

This query drops nearly a full second at month-end (and breaks with timestamp precision nuances). Using **`$lt` start of next period** is cleaner and safer.

### 14.3. Reporting in Asia/Ho_Chi_Minh

Suppose the business calendar uses UTC+07:00. Jan–Feb 2026 in local time maps to these UTC bounds:

~~~text
Start local: 2026-01-01 00:00:00 +07
Start UTC:   2025-12-31 17:00:00Z

End local:   2026-03-01 00:00:00 +07
End UTC:     2026-02-28 17:00:00Z
~~~

In `$match`, pass **those two exact UTC instants**. In `$dateToString`, use:

~~~javascript
{
  $dateToString: {
    format: "%Y-%m",
    date: "$createdAt",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

**Never** keep the original example's UTC bounds while changing only the timezone in `$dateToString`: the input set will miss or include extra orders at period boundaries.

### 14.4. An Order Near Midnight

~~~text
createdAt = 2026-02-28T18:00:00Z
UTC calendar month = 2026-02
Ho Chi Minh City local = 2026-03-01 01:00
Local calendar month = 2026-03
~~~

The two month groupings differ, and both are correct under their respective declared timezones. A report that omits its timezone has an **ambiguous contract**.

### 14.5. Do Not Rely Solely on createdAt for Refund Recognition

An order created on Jan 20 is refunded on Feb 10. With the current data model, re-running the **`createdAt`-based** report in March lowers **January's** realized revenue because `refundUnits` on that order changed.

If business requires **February refunds to affect only February**, model timestamped refund events or ledger entries and aggregate by posting date.

### 14.6. As-of Snapshots

To keep reports reconcilable weeks later, record metadata:

~~~text
reportPeriodStart
reportPeriodEnd
timezone
statusPolicyVersion
metricDefinitionVersion
computedAt
dataWatermark / snapshot reference
sourceCollection
generationId
~~~

**`computedAt` does not automatically give every query a consistent snapshot.** When data mutates continuously, select a read concern/snapshot strategy or immutable data-cut/watermark matching your deployment capabilities and business requirements.

## 15. Checking Aggregation Performance with explain

A correct aggregation is not enough if six months later the collection hits 300 million orders and the pipeline breaches SLOs. Inspect **documents scanned, indexes, execution time, and memory**.

### 15.1. Push $match to the Front

Good:

~~~text
$match(date, status, tenant, currency)
  -> $project
  -> $group
  -> $sort
~~~

Suboptimal if:

~~~text
$unwind(items of all orders)
  -> $lookup(products for all rows)
  -> $group
  -> $match(date, status)
~~~

In the second pattern, generating millions of intermediate rows before filtering can be very expensive. MongoDB's optimizer can push certain predicates past stages in supported cases, but **never rely on guesswork**—run `explain`.

### 15.2. Index for a Single-Tenant Report

Candidate index example:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    currency: 1,
    status: 1,
    createdAt: 1
  },
  { name: "ix_tenant_currency_status_date" }
);
~~~

Worth **evaluating** when queries always filter `tenantId/currency/status` and a `createdAt` range. Do not assume this is universally best: key order depends on selectivity, `$in` cardinality, actual queries, and write overhead.

### 15.3. Index for Cross-Tenant Date-Range Reports

Another candidate:

~~~javascript
lab.orders.createIndex(
  {
    currency: 1,
    status: 1,
    createdAt: 1,
    tenantId: 1
  },
  { name: "ix_currency_status_date_tenant" }
);
~~~

Create additional indexes only when justified by workload demand and acceptable maintenance cost. Every index consumes disk, memory/cache, and slows down inserts/updates.

### 15.4. Using explain

~~~javascript
lab.orders.explain("executionStats").aggregate(pipeline);
~~~

What to inspect:

- Does the winning query plan use **`IXSCAN`** or **`COLLSCAN`** on input?
- How do **`totalKeysExamined`** and **`totalDocsExamined`** compare to matched orders?
- Are there large blocking group/sort stages or disk spills?
- Which stage consumes the time in the aggregation?
- Does `$lookup` hit an indexed field on the target collection?
- How many groups are returned, and how long did execution take?

Explain output shapes vary by MongoDB version and query engine; never assume every field lives at a fixed JSON path. On 12 lab documents, **`COLLSCAN` may be a reasonable plan** and low execution time does not prove production scalability.

### 15.5. allowDiskUse and Limits

~~~javascript
lab.orders.aggregate(
  pipeline,
  {
    allowDiskUse: true,
    maxTimeMS: 30000
  }
).toArray();
~~~

**`allowDiskUse`** allows supported blocking stages to spill to temporary disk when needed per server/version configuration. It **does not** fix a flawed data model, unindexed queries, or all `$facet` memory limits.

**`maxTimeMS`** sets a server-side command execution time limit, which does not replace client/network/request deadlines. Choose timeouts per SLO rather than blindly copying `30000` ms everywhere.

### 15.6. Memory Risks of $group and $addToSet on Large Sets

In the category report, we used:

~~~javascript
uniqueOrders: { $addToSet: "$_id" }
~~~

to count distinct orders. With millions of order IDs in one category, the set array can consume excessive memory.

An alternative is **two-stage grouping**:

~~~javascript
[
  { $match: scope },
  { $unwind: "$items" },
  {
    $group: {
      _id: {
        category: "$items.category",
        orderId: "$_id"
      },
      unitsPerOrder: { $sum: "$items.qty" },
      grossPerOrder: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceUnits"
          ]
        }
      }
    }
  },
  {
    $group: {
      _id: "$_id.category",
      orderCount: { $sum: 1 },
      unitsSold: { $sum: "$unitsPerOrder" },
      grossUnits: { $sum: "$grossPerOrder" }
    }
  }
]
~~~

The first stage emits one row per **order/category**, and the second counts those rows. This avoids holding an `$addToSet` array of all order IDs inside one output group, though it still creates many intermediate groups; benchmark on realistic datasets.

### 15.7. $lookup on Large Collections

When joining products:

- Join on **`products._id`**, which already has a unique index.
- Prefer **group first, then lookup** when metadata is needed only for distinct SKUs.
- Use projection to trim returned fields.
- Handle missing SKUs without dropping gross values.
- Check sharding/`$lookup` limitations for your deployment/version.

Never run a one-to-many join and then sum order totals without controlling row multiplication.

### 15.8. Bounding Report Time Range and Size

A production report should define:

~~~text
Max requested date range
Authorized tenant scope
Query timeout and retry policy
Expected number of groups
Pagination/materialization strategy
Resource budget
Observability
~~~

Never expose a public endpoint allowing arbitrary aggregations across 10 years of all tenants' data without access controls and load limits.

## 16. Materializing Reports for Repeated Queries

A dashboard opened thousands of times per day should not re-aggregate the entire orders collection every time. Use a **materialized reporting collection**.

### 16.1. Result Schema

~~~javascript
{
  tenantId: "tA",
  month: "2026-01",
  reportVersion: "v1",
  orderCount: 3,
  grossUnits: NumberLong("100000"),
  discountUnits: NumberLong("5000"),
  netUnits: NumberLong("95000"),
  refundedUnits: NumberLong("20000"),
  realizedUnits: NumberLong("75000"),
  computedAt: ISODate("2026-03-02T00:00:00Z")
}
~~~

Record `reportVersion`, period, and `computedAt` so consumers know which formula produced the numbers and when.

### 16.2. Creating a Unique Key for $merge

In the test database:

~~~javascript
lab.monthly_order_reports.createIndex(
  { tenantId: 1, month: 1, reportVersion: 1 },
  {
    name: "uq_tenant_month_report_version",
    unique: true
  }
);
~~~

Fields listed in `$merge`'s **`on`** array require a matching unique index and must satisfy version/deployment constraints. Never create a unique index on a production collection with unaudited duplicates.

### 16.3. Writing Reports with $merge

~~~javascript
const reportGeneratedAt = new Date();

const materializePipeline = [
  ...pipeline,
  {
    $set: {
      reportVersion: "v1",
      computedAt: reportGeneratedAt
    }
  },
  {
    $merge: {
      into: "monthly_order_reports",
      on: ["tenantId", "month", "reportVersion"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
];

lab.orders.aggregate(materializePipeline).toArray();
~~~

The base pipeline already projected **`tenantId`** and **`month`** as top-level fields, giving `$merge` the keys it needs. `$merge` is a **write stage**: unlike read-only reports, it requires write permissions and should run as a controlled scheduled/reporting job.

### 16.4. $merge Does Not Automatically Remove Disappeared Groups

Suppose `tA` previously had two groups, but after a business filter change, January has zero eligible orders. `$merge` writes only current output documents; the stale January report document for `tA` will **remain**.

Therefore, a refresh strategy needs:

- Full definition of the **refresh scope**.
- Cleanup or obsolete-marking for groups that no longer exist.
- A **`generationId`/staging collection** when atomic report version switching is needed at the application layer.
- Report job state tracking: `RUNNING`, `VALIDATED`, `PUBLISHED`, `FAILED`.
- Publishing only after reconciling totals and group counts.

### 16.5. Idempotency for Reporting Jobs

A job may retry after a timeout. Using **`$merge whenMatched:"replace"`** with the same `(tenantId, month, reportVersion)` replaces the result with the latest calculation rather than inserting duplicate groups. However:

- `computedAt` may shift across runs.
- Results may change if source orders changed.
- Groups that vanished still require separate cleanup.
- `$merge` does not create an atomic snapshot across all report groups.

For immutable generations, tag every output row with **`generationId`**, reconcile, and then flip the active generation pointer cleanly.

### 16.6. $merge and Transactions

Pipelines using `$merge` or `$out` have restrictions inside transactions depending on MongoDB version; never assume you can wrap an entire materialization run in a multi-document transaction for atomic whole-report replacement.

When readers require atomic publication, design **staging generation + published pointer** or a deployment-appropriate snapshot mechanism.

### 16.7. Full Refresh vs. Incremental

| Strategy | Pros | Risks |
|---|---|---|
| Full period recompute | Easy to understand and reconcile. | Heavy scans, high compute cost. |
| Incremental by order changes | Can reduce cost. | Complex when status/refunds change, event replays, duplicates. |
| Daily-partitioned batch | Balances cost and reconciliation. | Must handle late-arriving/corrected data. |
| Ledger/event-based accounting | Tracks posting dates and audits cleanly. | Requires specialized schema and reconciliation. |

Especially with **refunds occurring months later**, summing only today's new orders will fail to update older monthly reports. Implement late-update handling, affected-period reprocessing, or an event model.

## 17. Making Reports Reproducible

Running the same aggregation today and tomorrow can yield different answers if orders/refunds change after the first run. Report metadata should answer:

1. **Data cut:** up to what point in time was data included?
2. **Timezone:** which timezone defined the period boundaries?
3. **KPI definitions:** which version defined `PAID`/`REFUNDED`?
4. **Currency:** are all values in the same unit?
5. **Schema version:** were field/type migrations accounted for?
6. **Inputs:** which collection/snapshot/event ledger was read?
7. **Computation:** driver/server version, pipeline version, and `generationId`?
8. **Verification:** did the output reconcile against oracle/ledger/period totals?

### 17.1. Snapshots and Consistency

While an aggregation runs, orders may be modified concurrently. **A standard `aggregate` command should not be described as an immutable accounting snapshot by default**; read concern, deployment topology, and mutation timing matter.

When strong reproducibility/auditing is required:

- Evaluate **`readConcern: snapshot`** / snapshot reads where supported for the operation, topology, and version.
- Or use an immutable ledger/event dataset with a **watermark/closing period**.
- Or stage data in a dedicated reporting snapshot.
- Clearly state whether a period is closed or still open to restatement.

Do not hold open a massive transaction just to scan hundreds of millions of records; mind snapshot/resource/lifetime limits.

### 17.2. Retaining Report Generation Metadata

~~~javascript
{
  generationId: "sales-v1-2026-03-02-run-001",
  reportName: "monthly-sales",
  timezone: "UTC",
  periodStart: ISODate("2026-01-01T00:00:00Z"),
  periodEnd: ISODate("2026-03-01T00:00:00Z"),
  metricVersion: "v1",
  statusPolicy: [
    "PAID", "PARTIALLY_REFUNDED", "REFUNDED"
  ],
  currency: "VND",
  status: "VALIDATED",
  computedAt: ISODate("2026-03-02T00:00:00Z")
}
~~~

This metadata is illustrative, not a MongoDB built-in report format.

### 17.3. Recording Validation Outcomes

~~~text
sourceDocumentCount = 12
eligibleOrderCount = 9
tenantMonthGroupCount = 4
overallNetUnits = 350000
overallRefundedUnits = 60000
overallRealizedUnits = 290000
validationStatus = PASS
~~~

Never equate "pipeline exited without error" with `validationStatus=PASS`. Validation must be **an explicit step** checking the report contract.

### 17.4. Versioning Report Schemas

Suppose v2 adds platform fees and defines:

~~~text
realized = total - refund - platformFee
~~~

That changes the KPI definition, not just adding a column. Set **`metricVersion: "v2"`**, document the change, and never silently overwrite v1 figures if downstream dashboards/auditors need historical comparisons.

### 17.5. Backfills and Late Data

If an upstream system updates a prior month's order after period close:

- Clarify whether restating closed periods is permitted.
- Emit **adjustment events** if accounting prohibits mutating history.
- Assign a new version/generation to the updated report.
- Provide a diff between the old and new reports.

Never delete old report numbers without an audit trail simply because a re-run produced different totals.

## 18. Calling Aggregation from the Java Sync Driver

In Java services, never concatenate raw JSON strings from user input to build pipelines. Use **`Filters`/`Aggregates`** or `Document` stages built from **validated parameters**, enforcing tenant scope from the authorization layer.

### 18.1. Java 17+ Example Running a Single-Tenant Report

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public final class TenantSalesReport {

    private final MongoCollection<Document> orders;

    public TenantSalesReport(MongoClient client) {
        this.orders = client.getDatabase("reporting_lab_460")
                .getCollection("orders");
    }

    public List<Document> run(String authorizedTenantId) {
        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Authorized tenant is required");
        }

        Date start = Date.from(
                Instant.parse("2026-01-01T00:00:00Z"));
        Date end = Date.from(
                Instant.parse("2026-03-01T00:00:00Z"));

        Bson filter = Filters.and(
                Filters.eq("tenantId", authorizedTenantId),
                Filters.eq("currency", "VND"),
                Filters.in("status",
                        "PAID", "PARTIALLY_REFUNDED", "REFUNDED"),
                Filters.gte("createdAt", start),
                Filters.lt("createdAt", end)
        );

        Document month = new Document("$dateToString",
                new Document("format", "%Y-%m")
                        .append("date", "$createdAt")
                        .append("timezone", "UTC"));

        Document projected = new Document("tenantId", 1)
                .append("month", month)
                .append("subtotalUnits", 1)
                .append("discountUnits", 1)
                .append("totalUnits", 1)
                .append("refundUnits", 1)
                .append("realizedUnits",
                        new Document("$subtract",
                                List.of(
                                        "$totalUnits",
                                        "$refundUnits")));

        Document groupId = new Document(
                "tenantId", "$tenantId")
                .append("month", "$month");

        Document grouped = new Document("_id", groupId)
                .append("orderCount", new Document("$sum", 1))
                .append("grossUnits",
                        new Document("$sum", "$subtotalUnits"))
                .append("discountUnits",
                        new Document("$sum", "$discountUnits"))
                .append("netUnits",
                        new Document("$sum", "$totalUnits"))
                .append("refundedUnits",
                        new Document("$sum", "$refundUnits"))
                .append("realizedUnits",
                        new Document("$sum", "$realizedUnits"));

        List<Bson> stages = List.of(
                Aggregates.match(filter),
                new Document("$project", projected),
                new Document("$group", grouped),
                new Document("$sort",
                        new Document("_id.month", 1))
        );

        return orders.aggregate(stages)
                .into(new ArrayList<>());
    }
}
~~~

This **illustrative snippet** expects `authorizedTenantId` to already be verified at the service layer. If a caller can pass any arbitrary `authorizedTenantId` unchecked, **cross-tenant data exposure** remains a risk.

### 18.2. Reading Monetary Values from Document

~~~java
Document row = reportRows.get(0);

Object amount = row.get("realizedUnits");
if (!(amount instanceof Number number)) {
    throw new IllegalStateException(
            "Expected integer monetary report field");
}

long realizedUnits = number.longValue();
~~~

For this report, the expected type is an integer numeric within **`long`** range. If the schema moves to Decimal128 or sums exceed `long`, update the data contract and adapter accordingly; never implicitly call `doubleValue()` to generate financial reports.

### 18.3. Checking Group Counts by Tenant

In the lab:

~~~text
run("tA") -> 2 groups:
  2026-01: realized 75000
  2026-02: realized 90000

run("tB") -> 2 groups:
  2026-01: realized 75000
  2026-02: realized 50000
~~~

An integration test should assert group keys and every KPI, not merely `results.size()`.

### 18.4. Do Not Create MongoClient per Execution

`MongoClient` is designed to be reused and manages a connection pool. Creating and closing `MongoClient` per request incurs connection discovery, TLS, and pool initialization overhead. Scope `MongoClient` to the application lifecycle.

### 18.5. Java Driver Must Use the Same Metric Contract

~~~text
mongosh pipeline:
  status IN ["PAID","PARTIALLY_REFUNDED","REFUNDED"]

Java endpoint accidentally:
  status == "PAID"
~~~

Results will diverge even though both code paths execute cleanly. Maintain a **metric definition registry** or integration tests verifying contracts across all entry points.

## 19. Spring Data MongoDB Integration

Spring Data MongoDB provides **`MongoTemplate`**, **`Aggregation`**, **`AggregationOperation`**, and typed aggregation APIs. When you need raw BSON stages matching `mongosh` examples, you can construct stages from **`Document`**.

### 19.1. Concise Example with AggregationOperation

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;

import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class SpringMonthlyReport {
    private final MongoTemplate template;

    public SpringMonthlyReport(MongoTemplate template) {
        this.template = template;
    }

    public List<Document> byTenant(String authorizedTenantId) {
        Date start = Date.from(
                Instant.parse("2026-01-01T00:00:00Z"));
        Date end = Date.from(
                Instant.parse("2026-03-01T00:00:00Z"));

        AggregationOperation matchStage = context ->
                new Document("$match",
                        new Document("tenantId", authorizedTenantId)
                                .append("currency", "VND")
                                .append("status",
                                        new Document("$in", List.of(
                                                "PAID",
                                                "PARTIALLY_REFUNDED",
                                                "REFUNDED")))
                                .append("createdAt",
                                        new Document("$gte", start)
                                                .append("$lt", end)));

        AggregationOperation projectStage = context ->
                new Document("$project",
                        new Document("tenantId", 1)
                                .append("month",
                                        new Document("$dateToString",
                                                new Document("format", "%Y-%m")
                                                        .append("date", "$createdAt")
                                                        .append("timezone", "UTC")))
                                .append("totalUnits", 1)
                                .append("refundUnits", 1)
                                .append("realizedUnits",
                                        new Document("$subtract",
                                                List.of(
                                                        "$totalUnits",
                                                        "$refundUnits"))));

        AggregationOperation groupStage = context ->
                new Document("$group",
                        new Document("_id",
                                new Document("tenantId", "$tenantId")
                                        .append("month", "$month"))
                                .append("orderCount", new Document("$sum", 1))
                                .append("netUnits",
                                        new Document("$sum", "$totalUnits"))
                                .append("refundedUnits",
                                        new Document("$sum", "$refundUnits"))
                                .append("realizedUnits",
                                        new Document("$sum", "$realizedUnits")));

        Aggregation aggregation = Aggregation.newAggregation(
                matchStage,
                projectStage,
                groupStage
        );

        AggregationResults<Document> results = template.aggregate(
                aggregation,
                "orders",
                Document.class
        );
        return results.getMappedResults();
    }
}
~~~

This is a **condensed KPI version** focusing on how stages are registered in Spring; if the dashboard needs gross/discount/AOV, add them to project/group just like the main pipeline.

With **raw `Document` stages**, field names must match stored BSON names. If the entity uses **`@Field`** aliases or custom converters, make sure the pipeline uses the persisted field paths. Spring Data's typed Aggregation APIs offer mapping helpers depending on version, but never assume raw stages automatically rename fields from the entity.

### 19.2. Spring Data Projection/DTO

Never return raw aggregation `Document`s containing **composite `_id`s** and raw numeric types directly from a REST API without an output contract.

~~~java
public record MonthlySalesDto(
        String tenantId,
        String month,
        long orderCount,
        long netUnits,
        long refundedUnits,
        long realizedUnits
) {}
~~~

Build a mapper that checks types, missing fields, and overflow. For Decimal128 or optional groups, adjust the DTO/schema intentionally. Never silently map null monetary fields to `0` if `null` indicates corrupt data.

### 19.3. Repository find Followed by Summing in Java

A **`findByTenantIdAndStatusIn`** method that loads all orders into Java to sum works on tiny datasets, but at scale transfers excessive documents and spikes memory/GC.

Aggregation pushes filtering and grouping to MongoDB. Conversely, application-side folding is very useful for **independent verification on small fixtures**.

### 19.4. Reactive MongoDB

With `ReactiveMongoTemplate`, aggregation returns a reactive publisher. Avoid collecting millions of groups into an unbounded list and avoid blocking calls inside Reactor pipelines. Consider materialization, backpressure, and timeouts.

## 20. Exporting Reports for Dashboards or CSV

### 20.1. Standardizing the Output Schema

A complete output should state currency, timezone, and version:

~~~json
{
  "tenantId": "tA",
  "month": "2026-01",
  "timezone": "UTC",
  "currency": "VND",
  "orderCount": 3,
  "grossUnits": "100000",
  "discountUnits": "5000",
  "netUnits": "95000",
  "refundedUnits": "20000",
  "realizedUnits": "75000",
  "metricVersion": "v1"
}
~~~

Monetary values appear as **decimal strings** in this JSON example to avoid JavaScript client safe-integer limits. If the frontend supports safe integers and the API contract specifies bounds, JSON numbers may be used within controlled ranges.

### 20.2. CSV with Deterministic Ordering

~~~csv
tenantId,month,currency,orderCount,grossUnits,discountUnits,netUnits,refundedUnits,realizedUnits
tA,2026-01,VND,3,100000,5000,95000,20000,75000
tA,2026-02,VND,2,110000,10000,100000,10000,90000
tB,2026-01,VND,2,80000,5000,75000,0,75000
tB,2026-02,VND,2,80000,0,80000,30000,50000
~~~

When exporting CSV in production:

- Use UTF-8, fixed column order, and explicit delimiters.
- Escape commas, quotes, and newlines in text fields.
- Preserve exact integers or canonical decimal strings.
- Attach timezone, currency, `metricVersion`, and `generationId`.
- Do not mix locale-formatted numbers with canonical numeric data.
- Never treat a CSV file as an audit trail without snapshot/version metadata.

### 20.3. JSON Precision Loss

BSON `Long` can store values larger than JavaScript's **`Number.MAX_SAFE_INTEGER`**. If a serializer converts `Long` to `Number` before emitting JSON, monetary amounts can lose precision.

When BSON round-tripping is needed, consider **canonical Extended JSON**; for APIs, use monetary integer/decimal strings or an exact decimal library per your data contract.

### 20.4. Multi-Tenant Safety

Reports can expose sensitive sales figures. The API must:

1. Authenticate the caller.
2. Derive tenant scope from permissions, not just query parameters.
3. Apply `$match` on `tenantId` early.
4. Never let callers inject `$lookup` targeting another tenant's collection.
5. Include `tenantId`, `currency`, `period`, and `metricVersion` in report cache keys.
6. Audit report access and exports where required.

If the `products` catalog is tenant-specific, `$lookup` must join on **`sku + tenantId`**, not `sku` alone, unless SKUs are globally unique and permitted to be shared.

## 21. Extension: Month-over-Month Growth with $setWindowFields

Beyond totals, dashboards often want **month-over-month growth**. First decide which metric is compared: `netUnits` or `realizedUnits`. This example uses **`realizedUnits`** per the lesson contract.

### 21.1. Formula

\[
\text{MoM growth \%}
=
\frac{\text{realized}_{t}-\text{realized}_{t-1}}
{\text{realized}_{t-1}}\times100
\]

If the prior month is 0 or absent, do not divide by 0. Return **`null` / `N/A`** per the reporting contract rather than outputting `+100%`.

### 21.2. Window Function

On MongoDB versions supporting **`$setWindowFields`** and **`$shift`** (available since MongoDB 5.0):

~~~javascript
const growthPipeline = [
  ...pipeline,
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: { month: 1 },
      output: {
        previousRealizedUnits: {
          $shift: {
            output: "$realizedUnits",
            by: -1,
            default: null
          }
        }
      }
    }
  },
  {
    $set: {
      monthOverMonthPercent: {
        $cond: [
          {
            $or: [
              { $eq: ["$previousRealizedUnits", null] },
              { $eq: ["$previousRealizedUnits", 0] }
            ]
          },
          null,
          {
            $multiply: [
              {
                $divide: [
                  {
                    $subtract: [
                      "$realizedUnits",
                      "$previousRealizedUnits"
                    ]
                  },
                  "$previousRealizedUnits"
                ]
              },
              100
            ]
          }
        ]
      }
    }
  },
  { $sort: { tenantId: 1, month: 1 } }
];

lab.orders.aggregate(growthPipeline).toArray();
~~~

### 21.3. Expected Output

| Tenant | Month | Realized | Prior Month | Growth |
|---|---|---:|---:|---:|
| tA | 2026-01 | 75.000 | N/A | N/A |
| tA | 2026-02 | 90.000 | 75.000 | **+20%** |
| tB | 2026-01 | 75.000 | N/A | N/A |
| tB | 2026-02 | 50.000 | 75.000 | **−33,33%** |

**Note:** `$shift` reads the preceding row in the sorted output, which is not necessarily the **immediately preceding calendar month** if a month had zero orders. Over multi-period datasets, generate calendar buckets or check month gaps rather than labeling a comparison against the most recent active period as "month-over-month."

### 21.4. Overall AOV Is Not the Average of Group AOVs

Full period:

~~~text
Net = 350000
Orders = 9
Overall AOV = 350000 / 9 ≈ 38888.89
~~~

Do not take the unweighted mean of the four group AOVs:

~~~text
(31666.67 + 50000 + 37500 + 40000) / 4
~~~

because each group has a different order count. Overall AOV must be **`total net / total orders`**, or the `orderCount`-weighted average.

## 22. Regression Testing for Reports

A regression test executed when aggregation code changes must verify **results and contracts**, not merely that the pipeline has no syntax errors.

### 22.1. Test Matrix

| Test | Data/Condition | Expected |
|---|---|---|
| Happy path | 12 fixture orders | 9 eligible, 4 tenant/month groups. |
| Cancelled | `A-004` | Excluded from KPIs. |
| Pending | `A-007` | Excluded from KPIs. |
| End-exclusive | `A-008` at exact `01/03 00:00Z` | Excluded from Jan–Feb. |
| Full refund | `A-003`, `B-003` | Included in `orderCount`, `realized=0`. |
| Partial refund | `A-006` | `realized=40000`. |
| Tenant isolation | Scope `tA` | Zero `tB` rows. |
| Scope `tB` | Query `tB` alone | Two groups, period `realized=125000`. |
| Gross/net/refund | Full period | 370000/350000/60000. |
| Totals invariant | Every group | `gross−discount=net`; `net−refund=realized`. |
| Category gross | Eligible items | Total category gross = 370000. |
| Unique category order count | `A-001` has two categories | Never sum category `orderCount` into total orders. |
| Missing catalog | One SKU fails lookup | Does not drop line gross. |
| Wrong amount type | `subtotalUnits` String | Caught by data-quality check. |
| Wrong total | `total != subtotal−discount` | Caught by data-quality check. |
| Refund over total | `refund > total` | Caught by data-quality check. |
| Unknown status | Order has new status | Flags data-contract/schema issue. |
| Local timezone | Boundary near UTC midnight | Bucketed accurately per local policy. |
| No eligible orders | Empty period | No fake zero-sales group emitted. |
| Retry report job | Same generation/key | No duplicate groups created. |
| Report version | KPI formula changes | Separates v1/v2 without silent overwrites. |

### 22.2. Empty Results Must Have a Defined Contract

When selecting a month with zero orders:

~~~javascript
lab.orders.aggregate([
  { $match: { createdAt: {
      $gte: ISODate("2030-01-01T00:00:00Z"),
      $lt: ISODate("2030-02-01T00:00:00Z")
  } } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
~~~

With no matching groups, the output is an **empty array**, not automatic zero-filled rows per tenant. If the UI needs zero-sales months displayed as `0`, add a **calendar/tenant dimension** and explicitly distinguish zero sales from missing data.

### 22.3. Golden Dataset

The lesson fixture is a **golden dataset**:

- Input documents are fixed and explicitly defined.
- Oracle outputs are hand-calculated.
- The report engine must preserve exact outputs unless the KPI version changes.
- Tests run in an isolated database without random data.
- Schema/status policy changes must update the test contract under review.

Golden tests excel at catching `$unwind` multiplication bugs, timezone shifts, dropped refunds, or missing tenant scopes.

### 22.4. Property-Based or Metamorphic Tests

Beyond fixed fixtures, you can assert general properties:

1. Adding a `CANCELLED` order leaves all KPIs unchanged.
2. Adding a valid `PAID` order increments `orderCount` by 1 and increases KPI totals by its exact amounts.
3. Changing an order from `PAID` to `REFUNDED` with `refund=total` decreases `realized` by `total` while leaving `orderCount` unchanged.
4. Splitting an item into two lines with identical SKU/category and unchanged total quantity leaves `gross` unchanged.
5. Permuting order insertion sequence leaves grouped results unchanged.
6. Adding a new tenant leaves `tA` KPIs unchanged.
7. Changing report timezone can shift month buckets without losing orders when filter bounds convert accordingly.

These properties catch defects across inputs far broader than the four fixture groups.

### 22.5. Automating KPI Assertions

When internal QA builds a test suite, expected outputs can be stored as fixtures and verified via a test framework (JUnit/Testcontainers or equivalent). For numeric BSON types, assert **numeric semantics and expected types**, never relying on shell `NumberLong` formatting strings.

**This lesson provides guidance and test patterns only**; do not assume the snippets were executed or validated against a live MongoDB instance here.

## 23. Common Mistakes When Writing Aggregation Reports

### 23.1. Counting Orders by Line Items After $unwind

Wrong:

~~~javascript
[
  { $unwind: "$items" },
  {
    $group: {
      _id: "$tenantId",
      orderCount: { $sum: 1 }
    }
  }
]
~~~

This counts **line-item rows**, not orders. An order with 3 lines gets counted 3 times. For order-level reports, group before unwinding; when distinct order counts are needed after unwinding, use **unique order IDs** or two-stage grouping.

### 23.2. Summing totalUnits After $unwind

~~~text
Order with 2 items:
  totalUnits = 40000

After unwind:
  row 1 has totalUnits = 40000
  row 2 has totalUnits = 40000

Wrong sum = 80000
~~~

Sum only line values at item grain; never allocate discounts/refunds without a documented rule.

### 23.3. Using $avg Over Group AOVs

When groups have differing order counts, the unweighted average of group AOVs does not equal overall AOV. Right:

~~~text
Overall AOV = overall netUnits / overall orderCount
~~~

### 23.4. Including PENDING and CANCELLED

Filtering only by `createdAt` without filtering `status` pulls in orders that generated no valid sales under the contract. The fixture intentionally includes `A-004` and `A-007` to catch this mistake.

### 23.5. Omitting REFUNDED

Some reports include only `PAID`, undercounting historical `orderCount` or hiding paid-then-refunded orders. This lesson's contract **includes `REFUNDED`** with `realized=0`; if business wants a separate `refundedOrderCount`, define an explicit additional metric.

### 23.6. Subtracting Refunds Twice

If `totalUnits` already had refunds deducted upstream while the pipeline computes `total − refund`, `realized` is reduced twice. Check the schema contract and upstream writers.

### 23.7. Refunds Occurring in a Later Period

A January order refunded in February alters January's `createdAt`-grouped report. If accounting requires refunds to hit February, use timestamped refund events/ledgers rather than reading cumulative `refundUnits` on the order.

### 23.8. Mixing Currencies

~~~text
100 USD + 100 VND = 200 (meaningless as financial amount)
~~~

Reports must group/filter by currency or convert using defined exchange rates with timestamps, sources, and audit trails.

### 23.9. Using Double for Monetary Totals

`double` introduces binary rounding errors. Use integer units/Int64 or Decimal128 appropriately, and guard against overflow/precision loss at scale.

### 23.10. Amounts Stored as Strings

A writer migration might change:

~~~javascript
totalUnits: NumberLong("35000")
~~~

to:

~~~javascript
totalUnits: "35000"
~~~

`$sum` will not behave as expected when non-numeric types appear. Catch this with **`$type`** checks rather than masking data-contract drift with automatic `$toDouble`.

### 23.11. Arbitrarily Defaulting $ifNull to 0

~~~javascript
{ $ifNull: ["$refundUnits", 0] }
~~~

is valid only if a **legacy schema contract officially defines missing `refundUnits` as 0**. If missing indicates data corruption, defaulting to 0 hides errors behind plausible-looking reports. Default only when documented in the metric/data contract.

### 23.12. Wrong Timezone

Grouping by `Asia/Ho_Chi_Minh` while `$match` uses UTC month bounds assigns midnight-adjacent orders inconsistently. Convert both filter bounds and bucket timezones to the same business calendar.

### 23.13. Using $lte at Period End

Using `$lte startOfNextMonth` double-counts a document landing on the exact boundary across two periods. Prefer **start-inclusive, end-exclusive**.

### 23.14. Joining Products Before Filtering

Running `$lookup` across the whole collection before `$match` creates heavy load, especially with large catalogs or unindexed joins. Filter first, group when possible, and then enrich metadata.

### 23.15. $lookup Dropping SKUs Missing from Catalog

Using `$unwind` after `$lookup` without preserving empty arrays drops SKUs absent from the catalog—silently reducing totals without raising an error.

### 23.16. Grouping by Current Catalog Category Instead of Snapshot

When a product changes category, historical reports shift unexpectedly. Decide upfront whether to use the order-time category snapshot or the current catalog category.

### 23.17. Failing to Assert Against Group Keys

Comparing only the grand total `290000` misses bugs that misattribute `tA` sales to `tB` or January to February. Assert **`tenant/month` keys** and every KPI.

### 23.18. Invariants Still Pass When All Values Are Doubled

If gross, discount, net, and refund are all doubled, `gross − discount = net` still holds. Always validate against an independent oracle, IDs, and order counts.

### 23.19. Dropping Empty-Item Orders After $unwind

A line-item pipeline drops orders with `items:[]` under default `$unwind`. If the schema forbids empty items, treat them as data-quality errors; if permitted, define how they should be counted/represented.

### 23.20. Scanning Too Much Data in Production

Never conclude an aggregation will perform well on hundreds of millions of documents just because it ran on 12 lab records. Review `explain`, working set, indexes, memory/disk spill, and peak read load.

### 23.21. Stale Materialized Reports

`$merge` does not remove old groups when a period no longer has eligible documents. Implement full-generation refresh/cleanup or obsolete-group markers.

### 23.22. Cross-Tenant Cache Pollution

If a cache key contains only `month`, `tA`'s response can be served to `tB`. Cache keys must include tenant scope, metric version, currency, period/timezone, and authorization context.

### 23.23. Letting Callers Construct Arbitrary Aggregation Pipelines

Never accept raw caller pipelines containing arbitrary `$lookup`/`$merge` stages without controls, as they can scan unauthorized data or trigger dangerous writes. Use approved report templates and whitelisted parameters.

### 23.24. Emitting JSON Numbers Beyond Safe Integer Bounds

Large BSON `Long` values lose precision if converted to JavaScript `Number`. Use strings or decimal-safe types with explicit type assertions.

### 23.25. Omitting Period Close or Snapshots

A January report run on March 1 and March 10 can differ if refunds or late data arrive. Attach as-of/watermark metadata and define a restatement policy.

## 24. Runbook When Report Numbers Do Not Match

### 24.1. Step 1 — Check Scope

If 9 orders were expected but the pipeline counted 8:

~~~javascript
lab.orders.find(
  scope,
  { _id: 1, tenantId: 1, createdAt: 1, status: 1 }
).sort({ _id: 1 });
~~~

Compare the ID list against the oracle. Check date bounds, status list, currency, tenant scope, and timezone.

### 24.2. Step 2 — Check Per-Order Data

If IDs match but net/refund differs:

~~~javascript
lab.orders.find(
  scope,
  {
    _id: 1,
    tenantId: 1,
    subtotalUnits: 1,
    discountUnits: 1,
    totalUnits: 1,
    refundUnits: 1
  }
).sort({ _id: 1 });
~~~

Verify BSON types and per-order arithmetic. Never tweak `$group` before confirming individual orders are valid.

### 24.3. Step 3 — Inspect Row-Multiplying Stages

If counts and monetary sums are abnormally high:

- Is there an `$unwind` on `items`?
- Is there a one-to-many `$lookup`?
- Was there a re-group by order ID before grouping by tenant/month?
- Was an order-level total summed at item grain?

Run debug slices stopping after each stage to count rows and inspect shape. Perform this on fixtures or representative samples; never dump sensitive production data.

### 24.4. Step 4 — Verify Timezones

If the full-period total matches while monthly totals disagree, check `createdAt` types and time boundaries. Compare UTC against business timezone, especially orders near `00:00` on the first of the month.

### 24.5. Step 5 — Compare Using the Independent Fold

If MongoDB output still differs from the oracle table, run the `BigInt` algorithm from Section 12 to compare document-by-document and group-by-group, isolating whether the defect is in filtering, data, or grouping logic.

### 24.6. Step 6 — Distinguish Stale Reports from Changed Source Data

If direct aggregation matches while `monthly_order_reports` disagrees:

- Are `generation`/`reportVersion` correct?
- Did the scheduled refresh job succeed?
- Are there stale groups awaiting cleanup?
- Did late refunds or order corrections arrive?
- Does materialization use the exact same scope/timezone/status policy?

### 24.7. Step 7 — Optimize Only After Correctness

If numbers are right but performance is slow:

1. Inspect `explain`.
2. Check keys/docs examined.
3. Check `$match` pushdown and indexes.
4. Inspect `$group`/`$sort` memory/spill and `$lookup`.
5. Measure client-side materialization and network overhead.
6. Measure p95/p99, CPU, I/O, and concurrency.

Never skip verification simply because an index or extra hardware was added.

## 25. Practice Exercises from Basic to Advanced

All exercises below target **database `reporting_lab_460` on a lab MongoDB instance**—never run in production. To test corrupt-data cases, create a **separate fixture copy** rather than altering the base dataset.

### Exercise 1 — Reading the Schema

List the fields and BSON types of an order. Distinguish order-level fields from `items[]`. Explain why prices and totals are stored as integer units.

### Exercise 2 — Seeding Data

Use `makeOrder` to insert 12 documents. Why does a second `insertMany` with the same IDs fail with duplicate keys? How do you re-run safely on a fresh fixture?

### Exercise 3 — Filtering Eligible Orders

Write `$match` for Jan–Feb 2026 in UTC, currency `VND`, and statuses `PAID`, `PARTIALLY_REFUNDED`, `REFUNDED`.

### Exercise 4 — Date Boundaries

Compare `$lt end` with `$lte end`. Using `A-008` with `createdAt` at exact `01/03 00:00Z`, how could it be double-counted across two periods?

### Exercise 5 — ID List

Write `countDocuments` for eligible orders (expected **9**), then compare the `_id` list against `expectedIds`. Why isn't a matching count alone sufficient?

### Exercise 6 — Per-Order Formulas

Compute gross/discount/net/refund/realized for `A-002`, `A-003`, and `A-006` by hand. Explain why `A-003` is counted even though `realized=0`.

### Exercise 7 — Month Bucketing

Build a `YYYY-MM` `month` field with `$dateToString` in UTC. Compare its string type with the BSON Date returned by `$dateTrunc`.

### Exercise 8 — $group

Write a `$group` whose `_id` combines `tenantId` and `month`. Compute `orderCount`, `grossUnits`, `discountUnits`, `netUnits`, `refundedUnits`, and `realizedUnits`.

### Exercise 9 — Output Schema

Use a final `$project` to promote fields out of `_id` to top-level `tenantId`/`month`; `$sort` by `tenantId, month` for deterministic output.

### Exercise 10 — Reconciling Against the Oracle

Compare all four groups against expected: `tA` Jan `75000`; `tA` Feb `90000`; `tB` Jan `75000`; `tB` Feb `50000` `realizedUnits`. If one group mismatches, what should you check first?

### Exercise 11 — Period Totals

Compute `orderCount=9`, `gross=370000`, `discount=20000`, `net=350000`, `refunded=60000`, `realized=290000` using `$group` with `_id:null`.

### Exercise 12 — $facet

Build three branches: `byTenantMonth`, `byMonth`, and `overall`. Reconcile total `realized` and `orderCount` across branches.

### Exercise 13 — AOV

Compute group and overall AOV. Why shouldn't you take the unweighted average of the four group AOVs to obtain overall AOV?

### Exercise 14 — $unwind Error

Intentionally `$unwind` `items` and sum `totalUnits` per row. Inspect `A-001` with its two items. Explain the wrong sum and fix the pipeline.

### Exercise 15 — Gross by Category

Write `$unwind + $group` by `items.category`. Expected: `Software=150000`, `Hardware=120000`, `Accessories=100000`.

### Exercise 16 — Units Sold

Sum `qty` by category. Expected: `Software=5`, `Hardware=6`, `Accessories=10`. Why shouldn't you infer order count from `unitsSold`?

### Exercise 17 — Unique Orders

Use `$addToSet` on order `_id` and `$size`. Why does summing `orderCount` across the three categories equal 13 instead of 9?

### Exercise 18 — Two-Stage Grouping

Replace `$addToSet` with grouping by `category+orderId` and then re-grouping by `category`. Discuss memory and intermediate-group trade-offs.

### Exercise 19 — Item-Level Refunds

Using `A-006` (two items, `refund=10000`), demonstrate that summing full order refund after unwinding yields `20000`. Propose an allocation rule or keep reporting at gross grain.

### Exercise 20 — $lookup Products

Create catalog `P1/P2/P3`, joining `displayName` into the SKU report after grouping. If the catalog is missing a SKU, how do you avoid dropping that SKU's gross sales?

### Exercise 21 — Recomputing Subtotal

Use `$map` and `$sum` to recompute subtotal from `qty × unitPriceUnits`. Compare against stored `subtotalUnits` and list mismatched IDs.

### Exercise 22 — Monetary Invariants

Write checks for `total=subtotal−discount` and `realized=total−refund`. Why can doubled KPIs still pass invariant checks?

### Exercise 23 — BSON Type Mismatch

In a fixture copy, change `totalUnits` to a String. Detect it with `$type`. Why shouldn't you silently convert String to double without a migration policy?

### Exercise 24 — Refund Exceeding Total

Create a separate test document with `refundUnits > totalUnits`. Write a data-quality aggregation to detect the violation.

### Exercise 25 — Unknown Status

Insert status `"PAYMENT_CONFIRMED"` in a fixture copy. Does the current report include it? What should data-quality monitoring alert on?

### Exercise 26 — Local Timezone

Switch the report to `Asia/Ho_Chi_Minh`. Compute UTC start/end from local boundaries and update `timezone` in `$dateToString`. When does an order switch months?

### Exercise 27 — Empty Period

Run the aggregation for Jan 2030. Does the pipeline emit a 0-count group or an empty array? If the UI needs `0` displayed per tenant, what dimension must be added?

### Exercise 28 — Month-over-Month

Use `$setWindowFields`/`$shift` to calculate realized growth by tenant. Expect `tA +20%` and `tB` around `−33.33%` in Feb.

### Exercise 29 — Missing Month

Suppose tenant `tC` only has orders in Jan and Apr. `$shift` grabs the prior row with data, not necessarily the prior calendar month. Propose a calendar dimension to avoid mislabeling the MoM metric.

### Exercise 30 — explain/Index

Propose an index for a tenant-scoped report. Use `explain("executionStats")` to inspect scan counts and query plans. Why can `COLLSCAN` be reasonable on 12 records?

### Exercise 31 — $facet Memory

A report spans 300,000 tenants × 120 months. Estimate maximum group count under a simple model, explain the BSON size limit risk, and propose materialization.

### Exercise 32 — Java Sync Driver

Write a Java service using `MongoCollection.aggregate`, `Filters`, and `Document` stages with authorization-derived `tenantId` filtering. Add integration assertions for `tA` Jan/Feb.

### Exercise 33 — Spring Data MongoDB

Write a `MongoTemplate` aggregation using `AggregationOperation`. What must you watch out for when an entity uses `@Field` aliases while raw stages reference BSON field names?

### Exercise 34 — JSON Export Precision

Explain why large BSON `Long` values get rounded if serialized as JavaScript `Number`. Propose a DTO/API encoding amounts as strings or decimal-safe types.

### Exercise 35 — CSV with Metadata

Export the four tenant/month groups in deterministic order, including currency, timezone, and `metricVersion` in an export manifest. Why must display number formatting be kept separate from canonical numeric data?

### Exercise 36 — Materializing with $merge

Create `monthly_order_reports` and a unique index on `tenantId/month/reportVersion`. Write results using `whenMatched: "replace"`, then read back the four groups.

### Exercise 37 — Stale Reports

If a prior month had sales but after a filter change has zero eligible orders, why doesn't `$merge` delete the old group automatically? Design `generationId` or cleanup.

### Exercise 38 — Late Refunds

Order created in Jan, refunded in Feb. Compare `createdAt`-based reporting against posting-date refund reporting. What data model/events are needed for historical audits?

### Exercise 39 — Multi-Tenant Authorization

Caller requests `tB`'s report while their token authorizes only `tA`. Is a `tenantId` query parameter sufficient for authorization? Design proper auth checks and cache keys.

### Exercise 40 — Production Report Design

Draft a design note covering:

~~~text
Business questions and stakeholders
KPI definitions and status rules
Currency and timezone contract
Input BSON schema and data quality assumptions
Aggregation pipeline and result contract
Hand-calculated golden fixtures
Independent reconciliation and invariants
Index/explain and resource budget
Materialization, snapshots, late data
Access control, observability and export formats
Incident runbook and ownership
~~~

A satisfactory report must be **accurate, explainable, verifiable, and reproducible**—not merely a pretty table.

## 26. Review Questions

1. Why must KPIs be defined before writing an aggregation?
2. Which factors determine whether an order is included in the report?
3. Why must currency be explicit when summing sales?
4. Why does this lesson store money as BSON Int64 instead of `double`?
5. How do `grossUnits`, `netUnits`, and `realizedUnits` differ?
6. Why might a `REFUNDED` order be counted in `orderCount` while having `realized = 0`?
7. Does AOV in this lesson use `net` or `realized` as the numerator?
8. Which formula checks `gross − discount = net`?
9. Which formula checks `net − refund = realized`?
10. Why doesn't a passing arithmetic invariant prove totals are right?
11. Why does start-inclusive/end-exclusive prevent boundary double-counting?
12. How do MongoDB BSON Date and a `YYYY-MM` string differ?
13. What problem does specifying `timezone` in `$dateToString` solve?
14. Why does changing bucket timezone without adjusting bounds corrupt a period?
15. How does `$dateTrunc` differ from `$dateToString` in result type?
16. Where should `$match` sit in the main pipeline and why?
17. How does `$project` trim fields and compute `realizedUnits`?
18. How is a composite `_id` in `$group` used to group by tenant and month?
19. Why should you `$sort` before outputting a report?
20. Why doesn't order-level `$group` need `$unwind` on `items`?
21. How many rows does `$unwind` produce for an order with two items?
22. What bug occurs if you sum order totals after `$unwind`?
23. How can `$addToSet` count distinct orders per category?
24. Why shouldn't you sum category `orderCount`s to obtain overall `orderCount`?
25. How do category gross and category realized differ in data requirements?
26. How can a missing product in `$lookup` drop rows if `$unwind` does not preserve empty arrays?
27. Why does joining SKUs after grouping reduce cost?
28. How does `$facet` help multi-perspective reports?
29. What memory and BSON result-size limits apply to `$facet`?
30. How does a hand-calculated oracle differ from invariant checks?
31. Why compare the list of order IDs rather than only the count?
32. What advantage does an independent `BigInt` fold have over re-running the same aggregation?
33. Why can't an independent fold prove the business contract if the scope is wrong?
34. Which BSON numeric defects should data-quality checks catch?
35. Why shouldn't missing refunds be defaulted to 0 unless specified by the schema?
36. When a refund happens next month, how can a `createdAt`-grouped report change?
37. When is a ledger/posting-date data model required?
38. Which part of idempotent refresh does `$merge` `whenMatched: "replace"` solve?
39. Does `$merge` automatically delete groups absent from new output?
40. Why are `generationId` and `metricVersion` needed when publishing reports?
41. Which resources does `explain("executionStats")` help evaluate?
42. Why doesn't `COLLSCAN` on 12 records reflect performance on millions of records?
43. How do indexes for tenant-scoped reports differ from global reports?
44. Does `allowDiskUse` overcome all `$facet` limits?
45. When does converting BSON `Long` to JSON `Number` lose precision?
46. Why must tenant scope be enforced before running aggregations?
47. How might reports over live orders require snapshots/watermarks?
48. Why must overall AOV divide total net by total orders rather than averaging group AOVs?
49. What caveat applies to `$setWindowFields`/`$shift` when a month is missing from data?
50. What evidence does a trustworthy production report need beyond running without errors?

## 27. Checklist for Completing a MongoDB Report

### 27.1. Requirements and Definitions

- [ ] Report purpose and stakeholders identified.
- [ ] KPI formulas, units, and semantics approved.
- [ ] Status inclusion/exclusion rules documented.
- [ ] Currency/denomination standardized.
- [ ] Date field, timezone, and period bounds defined.
- [ ] Refund/return/discount semantics confirmed.
- [ ] Tenant/authorization scope explicit and enforced.
- [ ] Period close and restatement rules defined.

### 27.2. Source Data

- [ ] BSON field types audited.
- [ ] No missing required fields, or explicit handling policy exists.
- [ ] Quantities and unit prices validated.
- [ ] Subtotal matches sum of line values.
- [ ] Total matches `subtotal − discount`.
- [ ] Refund does not exceed total per business rules.
- [ ] No unhandled unknown statuses or currencies.
- [ ] Missing product catalog entries do not silently drop sales data.
- [ ] Legacy schema versions migrated or covered by compatibility policy.

### 27.3. Aggregation

- [ ] `$match` filters tenant, dates, statuses, and currency accurately.
- [ ] Uses start-inclusive / end-exclusive bounds.
- [ ] Month grouping uses the right timezone.
- [ ] KPIs sum at the correct document grain.
- [ ] `$unwind` used only when item-level data is needed.
- [ ] Full order totals never summed multiple times after unwinding.
- [ ] `$lookup` neither duplicates nor drops rows.
- [ ] `$group`, `$facet`, and `$sort` follow expected output schema.
- [ ] Empty-period and missing-group behavior defined.
- [ ] Output has deterministic sorting.

### 27.4. Numeric Verification

- [ ] Deterministic fixture and hand-calculated oracle exist.
- [ ] Eligible document count matches.
- [ ] Eligible order IDs match.
- [ ] Group count and group keys match.
- [ ] Every KPI checked against the oracle, not just one grand total.
- [ ] `gross − discount = net` and `net − refund = realized`.
- [ ] Tenant/month sums equal overall sums.
- [ ] Total category line gross equals order gross.
- [ ] Independent calculation exists to reconcile mismatches.
- [ ] Boundaries, refunds, cancelled, and partially refunded cases tested.
- [ ] Tests guard against `$unwind` row multiplication.

### 27.5. Performance and Operations

- [ ] `explain` reviewed on a representative dataset.
- [ ] Candidate indexes benchmarked under realistic workloads.
- [ ] Reasonable timeouts and resource limits configured.
- [ ] `$facet` and `$group` memory usage evaluated.
- [ ] `$lookup`/cross-collection joins stay within budget.
- [ ] Latency, success/failure, and data freshness monitored.
- [ ] Plan in place for large reports, pagination, or materialization.
- [ ] Backfills and late refunds handled.
- [ ] Report refresh is idempotent and cleans up stale outputs.

### 27.6. Publishing and Security

- [ ] Output contract states tenant, period, currency, timezone, and `metricVersion`.
- [ ] Numeric values do not lose precision in JSON/CSV exports.
- [ ] Cache keys include tenant scope and report version.
- [ ] Users cannot execute arbitrary aggregation stages.
- [ ] Report exports/access audited when required.
- [ ] Each generation records `computedAt` and a data watermark/snapshot reference.
- [ ] Validation status verified prior to publishing.
- [ ] Runbook and clear ownership exist for data discrepancies.

## 28. Summary

Building an aggregation report has two equally critical halves: **computing** and **proving the results**.

### 28.1. A Sound Pipeline Lifecycle

~~~text
Define KPI / scope / timezone / currency
                |
                v
       Verify source data contract
                |
                v
            $match
                |
                v
        $project / $set
                |
                v
             $group
                |
                v
        $sort / $facet
                |
                v
      Validate IDs and totals
                |
                v
   Independent fold / golden oracle
                |
                v
        explain / optimize
                |
                v
   Export or materialize versioned report
~~~

### 28.2. Most Important Principles

1. **Write the KPI contract before coding**: a report accurate to the wrong definition is still wrong for the business.
2. **Keep grain explicit**: order-level totals differ from item-level totals; `$unwind` can multiply rows.
3. **Filter scope before grouping**: status, tenant, currency, and time range.
4. **Use exact timezones and `[start, end)`**, never hardcode day-end as `23:59:59`.
5. **Preserve numeric precision** with Int64/Decimal128 as appropriate, never silently converting to `double`.
6. **Maintain a hand-calculated oracle** simple enough to stay independent of the pipeline.
7. **Verify IDs, group counts, and all KPIs**, not only grand totals.
8. **Run dedicated data-quality checks**, because `$sum` does not catch all corrupt data.
9. **Reconcile via a second method**: an independent fold on the fixture catches expression bugs.
10. **Never use `$lookup`/`$facet`/`$unwind` unconditionally**; check output cardinality and resource limits.
11. **Use `explain` and representative workloads** before tuning indexes or capacity.
12. **Materialization must handle stale groups, late data, and generations**.
13. **Maintain traceability**: `metricVersion`, timezone, `computedAt`, and data watermarks.
14. **Protect tenant data** in both application authorization and report queries.
15. **A production report is not just a final number**; it is a calculation with provenance, assumptions, proof, and reproducibility.

### 28.3. Core Summary Numbers to Remember

| Check | Fixture Expected |
|---|---:|
| Total seeded documents | 12 |
| Eligible documents Jan–Feb | 9 |
| Tenant/month groups | 4 |
| GrossUnits | 370.000 |
| DiscountUnits | 20.000 |
| NetUnits | 350.000 |
| RefundedUnits | 60.000 |
| RealizedUnits | **290.000** |
| Total category gross | 370.000 |
| `tA` full-period realized | 165.000 |
| `tB` full-period realized | 125.000 |

If re-running the report on the defined fixture yields different numbers, inspect **schema, filters, timezone, `$unwind`/`$lookup`, KPI formulas, or mutated data**—never accept new numbers simply because the aggregation ran without errors.

### 28.4. Official References

- [MongoDB Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — pipeline concepts, stages, and optimization.
- [MongoDB Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/) — stage reference catalog.
- [MongoDB $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) — filtering documents.
- [MongoDB $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) — selecting and transforming fields.
- [MongoDB $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — grouping aggregations.
- [MongoDB $unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — expanding arrays into rows.
- [MongoDB $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/) — multi-branch aggregations.
- [MongoDB $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — joining collections.
- [MongoDB $dateToString](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateToString/) — formatting dates with timezones.
- [MongoDB $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/) — bucketing by calendar/time units.
- [MongoDB $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/) — window computations.
- [MongoDB $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — materializing results.
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query planner/execution stats.
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Long, Decimal128, Date, and storage types.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — driver APIs and aggregation.
- [Spring Data MongoDB Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — Aggregation API in Spring.

APIs, optimizations, and limits of `$facet`/`$group`/`$merge` can change across MongoDB server, driver, and Spring Data versions. Outside the lab, verify documentation for your exact version and test on representative datasets.

**Conclusion:** A trustworthy MongoDB report answers not only **"how much revenue?"**, but also **"which orders were counted, what formulas applied, why the numbers are right, and whether they can be reproduced?"**. Aggregation provides powerful tools for summarizing data; **golden fixtures, independent reconciliation, source data audits, timezone control, and snapshots/report versioning** make those numbers reliable for business decisions.
