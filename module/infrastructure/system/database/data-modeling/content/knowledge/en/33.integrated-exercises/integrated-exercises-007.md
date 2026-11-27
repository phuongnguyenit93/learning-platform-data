# Comparing Relational Tables vs. Documents for Representing Orders

## Objectives and how to practice

This lesson belongs to the **Integrated Exercises** chapter of the **DATABASE_DATA_MODELING** module, where we practice turning business requirements into entities, relationships, invariants, normalization, keys, indexes, and physical schemas—then comparing **relational**, **document**, graph, and analytical representations to select structures that are evolvable and verifiable. Here, the same **sales order** domain is modeled using **relational tables** and **a single document embedding order lines**.

After completing this lesson, you should be able to:

1. Accurately state the **grain**, identity, tenant scope, and consistency boundary of Order and OrderLine.
2. Build a PostgreSQL model with header/line tables, primary/foreign keys, `CHECK` constraints, indexes, and transactions.
3. Build a document model embedding OrderLine inside Order using JSON/BSON structures, validation rules, and atomic updates.
4. Run **identical queries** across both representations and reconcile outputs against a shared sample dataset.
5. Identify limits of both approaches: multi-row transactions, concurrent updates, document growth, SKU-level reporting, and schema evolution.
6. Decouple the **Java domain model**, DTOs, and events from storage choices; never let table or document shape dictate business mutation authority.
7. Design grounded experiments, tests, and migration paths instead of claiming one engine is always faster or better.

**How to study:** read the prompt and sketch both models before looking at the solutions; load the sample dataset using the respective scripts; run queries if you have a local environment; then solve the final questions on your own. All monetary values, quantities, and workloads are **hypothetical learning examples**, not benchmarks or industry standards.

## 1. Shared problem: one order source, multiple storage options

The Sales platform receives online purchase orders. An Order contains multiple OrderLines; each line records SKU, quantity, unit price **locked at order time**, and per-unit discount. The application needs to:

- **Create and edit draft orders:** add/remove lines while in `DRAFT` status.
- **Confirm:** only non-empty drafts with validated monetary amounts transition to `CONFIRMED`; afterward, lines and prices cannot be mutated by normal commands.
- **Read details:** fetch an Order with all its lines by `(tenantId, orderId)`.
- **List orders:** retrieve a customer's recent orders, paginated chronologically.
- **Analyze:** compute confirmed quantities and sales totals by SKU and by day.
- **Integrate:** publish `OrderConfirmed` for Inventory/Notification after the source transaction commits.
- **Secure:** never trust `tenantId` or sale prices from unverified client inputs; never let a retried request confirm an order twice.

**Hypothetical scale:** 10,000 orders/day, averaging 8 lines/order; most orders have 1–30 lines, with a few rare larger outliers. Detail lookups by `orderId` are frequent, while SKU-level reporting is also required. These are inputs for **evaluating both models**, not claims about PostgreSQL or MongoDB speed.

### Business boundaries

**Sales owns** the Order and locked price/discount snapshots. **Catalog** owns current list prices; Catalog updates never rewrite past prices on confirmed orders. **Inventory** owns stock/reservations; `OrderConfirmed` does not automatically mean `StockReserved`. **Payment** owns collection outcomes; `OrderConfirmed` does not imply `PaymentCaptured`. **Analytics** may build sales-line facts from source events/states, yet never commands order state transitions.

In this lesson, money uses **integer VND**, excluding taxes, shipping fees, or currency conversion. If the business adds those, extend `Money` and formulas explicitly instead of silently changing what `total` means.

## 2. Locking down grain, identity, and invariants before choosing storage

| Concept | Grain and identity | Who holds decision authority? |
| --- | --- | --- |
| Order | One order within a tenant; `(tenantId, orderId)` | Sales/Order aggregate |
| OrderLine | One line on an Order; `(tenantId, orderId, lineNo)` | Sales/Order aggregate |
| Customer | One customer with an ID in Customer source | Customer context; Order stores reference ID |
| Product/SKU | One product in Catalog | Catalog; Order retains SKU and price snapshot |
| OrderConfirmed | One valid state transition of an Order | Published by Sales post-commit |
| FactConfirmedOrderLine | One line of a confirmed Order, recorded once validly | Analytical pipeline at its own grain |

Codes **`T1`**, **`O100`**, **`C1`**, **`A`**, **`B`** below are readable mock keys. Real apps may use UUID/ULID and proper namespaces; what matters is avoiding ambiguity across tenants and sources.

Monetary definitions for line \(i\):

\[
g_i=q_i p_i,\qquad d_i=q_i r_i,\qquad n_i=g_i-d_i,
\]

where \(q_i\) is quantity, \(p_i\) is locked unit price, and \(r_i\) is **per-unit** discount. Invariants:

\[
q_i>0,\qquad 0\leq r_i\leq p_i,\qquad n_i\geq0.
\]

Order totals:

\[
\mathrm{gross}=\sum_i g_i,\quad
\mathrm{discount}=\sum_i d_i,\quad
\mathrm{payable}=\mathrm{gross}-\mathrm{discount}.
\]

**State rules:**

- `DRAFT` may temporarily have zero lines and allows adding/removing/editing lines via controlled commands.
- `CONFIRMED` must have **at least one line** and valid totals; lines cannot be modified via `DRAFT` commands.
- `CANCELLED` cannot freely re-confirm; post-finalization cancellations/refunds belong to separate workflows with events and reconciliation.
- Any potentially concurrent mutation must **version/lock** on the same Order root rather than trusting stale prior reads.

Multi-row constraints like **header total equals sum of lines** and **non-empty CONFIRMED orders** require write protocols and tests; they do not materialize automatically just from drawing a relationship line.

## 3. Shared reconciliation dataset

Use these exact three orders in tenant **`T1`** with locked prices/discounts:

| Order | Customer | Status | Order lines | Gross VND | Discount VND | Payable VND |
| --- | --- | --- | --- | ---: | ---: | ---: |
| O100 | C1 | CONFIRMED | A: 2 × 120,000, disc 10,000/unit; B: 1 × 90,000, disc 0 | 330,000 | 20,000 | 310,000 |
| O101 | C1 | DRAFT | A: 1 × 120,000, disc 0 | 120,000 | 0 | 120,000 |
| O102 | C2 | CONFIRMED | B: 3 × 90,000, disc 5,000/unit | 270,000 | 15,000 | 255,000 |

**Manual verification:**

\[
\begin{aligned}
O100 &: 2(120000-10000)+1(90000)=310000,\\
O101 &: 1(120000-0)=120000,\\
O102 &: 3(90000-5000)=255000.
\end{aligned}
\]

Expected results to cross-check across both storage models:

| Question | Correct answer |
| --- | --- |
| Details of O100 | Two lines A and B, payable 310,000 VND |
| Order list for C1 | O101 then O100 sorted newest `createdAt` first |
| CONFIRMED Order count | 2 (O100, O102) |
| Total payable of CONFIRMED Orders | **565,000 VND** |
| SKU A in CONFIRMED Orders | 2 units, gross 240,000, discount 20,000, net **220,000 VND** |
| SKU B in CONFIRMED Orders | 4 units, gross 360,000, discount 15,000, net **345,000 VND** |

**Do not include O101 in the confirmed total.** Also do not count O100 as two Orders just because it has two lines. `lineNo` is only meaningful within one Order; the same SKU can appear across multiple Orders with different snapshot unit prices.

## 4. Both representations side by side

~~~mermaid
flowchart LR
    subgraph SQL["Relational: PostgreSQL"]
        H["order_header<br/>PK tenantId + orderId"]
        L["order_line<br/>PK tenantId + orderId + lineNo"]
        H -->|"1 - N, FK"| L
    end
    subgraph DOC["Document: MongoDB"]
        O["Order document<br/>_id + tenantId + orderId"]
        I["lines: [ {lineNo, skuId,<br/>quantity, unitPriceVnd, discount} ]"]
        O -->|"embeds 1 - N"| I
    end
~~~

Both models express **the exact same Order semantics**, differing in **physical write unit**:

- Relational: header and lines are **separate rows**; transactions guarantee consistent multi-row Order updates.
- Document: an Order and its bounded lines reside **in one document**; single-document updates can be atomic per engine guarantees.
- Both must still separate **aggregates**, **transactions**, **cross-context workflows**, **DTOs**, **events**, and **facts**; never let storage shape dictate system-wide contracts.

## 5. Solution A — PostgreSQL relational model

### 5.1. Table design and constraints

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    gross_total_vnd BIGINT NOT NULL CHECK (gross_total_vnd >= 0),
    discount_total_vnd BIGINT NOT NULL CHECK (discount_total_vnd >= 0),
    payable_total_vnd BIGINT NOT NULL CHECK (payable_total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (discount_total_vnd <= gross_total_vnd),
    CHECK (gross_total_vnd - discount_total_vnd = payable_total_vnd),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    discount_per_unit_vnd BIGINT NOT NULL DEFAULT 0
        CHECK (discount_per_unit_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id),
    CHECK (discount_per_unit_vnd <= unit_price_vnd)
);

CREATE INDEX order_by_customer_recent
    ON sales.order_header
        (tenant_id, customer_id, created_at DESC, order_id DESC);

CREATE INDEX order_line_by_sku
    ON sales.order_line (tenant_id, sku_id, order_id);
~~~

**Constraint semantics:**

- Composite PK includes `tenantId` in Order identity, preventing collisions across tenants; composite FK prevents a T2 line from pointing to a T1 header.
- `CHECK` protects **single-row** validity and the total–discount relation on the header. No ordinary `CHECK` on `order_header` can compute the `SUM` across all `order_line` rows.
- For CONFIRMED orders, `confirmedAt` is required. Yet the DDL alone cannot verify at least one line exists or block CONFIRMED → DRAFT transitions; domain/transaction protocols must enforce those.
- Amounts use integer VND `BIGINT`; when summing across many lines, cast multiplication to `NUMERIC` to avoid overflow in large totals; application code must use `Math.*Exact` or matching exact arithmetic.
- **`TEXT` IDs are purely for readability in this example.** Real systems should benchmark ID types, indexes, and namespaces; UUID is a common choice.

### 5.2. Loading the exact dataset

~~~sql
BEGIN;

INSERT INTO sales.order_header (
    tenant_id, order_id, customer_id, status, currency_code,
    gross_total_vnd, discount_total_vnd, payable_total_vnd,
    version, created_at, confirmed_at
) VALUES
('T1','O100','C1','CONFIRMED','VND',
 330000,20000,310000,2,
 TIMESTAMPTZ '2026-11-20 08:00:00+00',
 TIMESTAMPTZ '2026-11-20 09:00:00+00'),
('T1','O101','C1','DRAFT','VND',
 120000,0,120000,1,
 TIMESTAMPTZ '2026-11-21 08:00:00+00',NULL),
('T1','O102','C2','CONFIRMED','VND',
 270000,15000,255000,3,
 TIMESTAMPTZ '2026-11-21 10:00:00+00',
 TIMESTAMPTZ '2026-11-21 11:00:00+00');

INSERT INTO sales.order_line (
    tenant_id, order_id, line_no, sku_id, quantity,
    unit_price_vnd, discount_per_unit_vnd
) VALUES
('T1','O100',1,'A',2,120000,10000),
('T1','O100',2,'B',1, 90000,    0),
('T1','O101',1,'A',1,120000,    0),
('T1','O102',1,'B',3, 90000, 5000);

COMMIT;
~~~

This load script uses precomputed totals for comparison; it is **not an API letting clients freely supply header totals or statuses**. In real write paths, the domain/repository computes totals and guards transactions. It is also non-idempotent; re-running requires a fresh test database or explicit reset.

### 5.3. Detail, listing, and reporting queries

~~~sql
-- Detail for O100: two rows, still one Order.
SELECT h.order_id, h.status, h.payable_total_vnd,
       l.line_no, l.sku_id, l.quantity,
       l.unit_price_vnd, l.discount_per_unit_vnd
FROM sales.order_header AS h
JOIN sales.order_line AS l
  ON l.tenant_id = h.tenant_id AND l.order_id = h.order_id
WHERE h.tenant_id = 'T1' AND h.order_id = 'O100'
ORDER BY l.line_no;

-- Order list for customer C1.
SELECT order_id, status, payable_total_vnd, created_at
FROM sales.order_header
WHERE tenant_id = 'T1' AND customer_id = 'C1'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

-- Confirmed order-line analytics by SKU.
SELECT l.sku_id,
       SUM(l.quantity) AS units,
       SUM(l.quantity::NUMERIC * l.unit_price_vnd) AS gross_vnd,
       SUM(l.quantity::NUMERIC * l.discount_per_unit_vnd)
           AS discount_vnd,
       SUM(l.quantity::NUMERIC *
           (l.unit_price_vnd - l.discount_per_unit_vnd)) AS net_vnd
FROM sales.order_header AS h
JOIN sales.order_line AS l
  ON l.tenant_id = h.tenant_id AND l.order_id = h.order_id
WHERE h.tenant_id = 'T1' AND h.status = 'CONFIRMED'
GROUP BY l.sku_id
ORDER BY l.sku_id;
~~~

Grouped SKU results must be **A: 2 units / net 220,000** and **B: 4 units / net 345,000**, summing to 565,000 VND. If you join multiple `PaymentAttempt` rows per Order and `SUM` directly, totals **multiply by attempt count**; preserve grain or aggregate before joining.

### 5.4. Reconciling header against lines

~~~sql
WITH totals AS (
    SELECT tenant_id, order_id,
           SUM(quantity::NUMERIC * unit_price_vnd) AS gross,
           SUM(quantity::NUMERIC * discount_per_unit_vnd) AS discount
    FROM sales.order_line
    GROUP BY tenant_id, order_id
)
SELECT h.tenant_id, h.order_id,
       h.gross_total_vnd, h.discount_total_vnd,
       h.payable_total_vnd,
       t.gross AS computed_gross,
       t.discount AS computed_discount,
       t.gross - t.discount AS computed_payable
FROM sales.order_header AS h
LEFT JOIN totals AS t
  ON t.tenant_id = h.tenant_id AND t.order_id = h.order_id
WHERE h.tenant_id = 'T1'
  AND (
      t.order_id IS NULL
      OR h.gross_total_vnd IS DISTINCT FROM t.gross
      OR h.discount_total_vnd IS DISTINCT FROM t.discount
      OR h.payable_total_vnd IS DISTINCT FROM (t.gross - t.discount)
  );
~~~

On the three sample Orders, this query **returns zero rows**. In production, `DRAFT` may temporarily be empty, so classify it separately rather than treating every zero-line Order as corrupt. Reconciliation queries **detect** drift; they do not replace guarding active write paths.

## 6. Solution B — Document model embedding OrderLine

For the same problem, we can store **one Order as one document** in an `orders` collection. `OrderLine`s live in an embedded array because they are usually read with the Order and share the Sales/Order aggregate's lifecycle.

### 6.1. Shape of a document

~~~json
{
  "_id": "T1:O100",
  "tenantId": "T1",
  "orderId": "O100",
  "customerId": "C1",
  "status": "CONFIRMED",
  "currency": "VND",
  "grossTotalVnd": 330000,
  "discountTotalVnd": 20000,
  "payableTotalVnd": 310000,
  "version": 2,
  "createdAt": "2026-11-20T08:00:00Z",
  "confirmedAt": "2026-11-20T09:00:00Z",
  "lines": [
    {
      "lineNo": 1,
      "skuId": "A",
      "quantity": 2,
      "unitPriceVnd": 120000,
      "discountPerUnitVnd": 10000
    },
    {
      "lineNo": 2,
      "skuId": "B",
      "quantity": 1,
      "unitPriceVnd": 90000,
      "discountPerUnitVnd": 0
    }
  ]
}
~~~

This is **conceptual JSON** for readability. In real MongoDB storage, timestamps use **BSON Date**, and money uses **BSON Int64/Decimal128** per contract. Identical-looking JSON numbers **do not prove** identical physical numeric types, precision, or bounds. The `mongosh` script below uses `NumberLong` for money to illustrate Int64. Never use float/double casually for monetary fields.

**Identity semantics:** `_id = "T1:O100"` is a composite physical key namespacing tenant/order per exercise convention; `tenantId` and `orderId` fields support queries and business contracts. Even if `_id` is a global UUID, verify tenant isolation on every access path. Never construct composite keys via naive string concatenation if components might contain delimiters; production should use unambiguous encoding or a unique surrogate ID.

### 6.2. Schema validation and collection indexes

MongoDB can use JSON Schema to enforce **structural** constraints on writes:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "orderId", "customerId", "status",
        "currency", "version", "grossTotalVnd",
        "discountTotalVnd", "payableTotalVnd", "lines", "createdAt"
      ],
      properties: {
        _id: { bsonType: "string" },
        tenantId: { bsonType: "string" },
        orderId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        status: { enum: ["DRAFT", "CONFIRMED", "CANCELLED"] },
        currency: { enum: ["VND"] },
        version: { bsonType: "int", minimum: 0 },
        grossTotalVnd: { bsonType: "long", minimum: 0 },
        discountTotalVnd: { bsonType: "long", minimum: 0 },
        payableTotalVnd: { bsonType: "long", minimum: 0 },
        createdAt: { bsonType: "date" },
        confirmedAt: { bsonType: ["date", "null"] },
        lines: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: [
              "lineNo", "skuId", "quantity",
              "unitPriceVnd", "discountPerUnitVnd"
            ],
            properties: {
              lineNo: { bsonType: "int", minimum: 1 },
              skuId: { bsonType: "string" },
              quantity: { bsonType: "int", minimum: 1 },
              unitPriceVnd: { bsonType: "long", minimum: 0 },
              discountPerUnitVnd: { bsonType: "long", minimum: 0 }
            }
          }
        }
      }
    }
  },
  validationAction: "error"
});

db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);

db.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1, orderId: -1 }
);

// Candidate multikey index for SKU queries; weigh write cost.
db.orders.createIndex(
  { tenantId: 1, "lines.skuId": 1, status: 1 }
);
~~~

**What this validator DOES NOT prove automatically:**

- `discountPerUnitVnd ≤ unitPriceVnd` compares **two fields of the same array element**; the schema above only checks each field individually for non-negativity.
- Line sums matching `gross`/`discount`/`payable` header totals are **not enforced by this validator**.
- Valid `DRAFT`/`CONFIRMED` line-count transitions are domain invariants.
- Uniqueness of `lineNo` within the same document is not checked by the array schema above.
- Whether a caller may mutate a status/tenant belongs to **authorization and command handling**, not JSON Schema.

You can add `$expr` validators or application checks depending on engine version, yet never assume JSON Schema replaces all aggregate invariants. **Every write path** must follow the same rules and test suite.

### 6.3. Loading the sample dataset in mongosh

~~~javascript
db.orders.insertMany([
  {
    _id: "T1:O100",
    tenantId: "T1", orderId: "O100", customerId: "C1",
    status: "CONFIRMED", currency: "VND", version: NumberInt(2),
    grossTotalVnd: NumberLong("330000"),
    discountTotalVnd: NumberLong("20000"),
    payableTotalVnd: NumberLong("310000"),
    createdAt: ISODate("2026-11-20T08:00:00Z"),
    confirmedAt: ISODate("2026-11-20T09:00:00Z"),
    lines: [
      {
        lineNo: NumberInt(1), skuId: "A", quantity: NumberInt(2),
        unitPriceVnd: NumberLong("120000"),
        discountPerUnitVnd: NumberLong("10000")
      },
      {
        lineNo: NumberInt(2), skuId: "B", quantity: NumberInt(1),
        unitPriceVnd: NumberLong("90000"),
        discountPerUnitVnd: NumberLong("0")
      }
    ]
  },
  {
    _id: "T1:O101",
    tenantId: "T1", orderId: "O101", customerId: "C1",
    status: "DRAFT", currency: "VND", version: NumberInt(1),
    grossTotalVnd: NumberLong("120000"),
    discountTotalVnd: NumberLong("0"),
    payableTotalVnd: NumberLong("120000"),
    createdAt: ISODate("2026-11-21T08:00:00Z"),
    confirmedAt: null,
    lines: [
      {
        lineNo: NumberInt(1), skuId: "A", quantity: NumberInt(1),
        unitPriceVnd: NumberLong("120000"),
        discountPerUnitVnd: NumberLong("0")
      }
    ]
  },
  {
    _id: "T1:O102",
    tenantId: "T1", orderId: "O102", customerId: "C2",
    status: "CONFIRMED", currency: "VND", version: NumberInt(3),
    grossTotalVnd: NumberLong("270000"),
    discountTotalVnd: NumberLong("15000"),
    payableTotalVnd: NumberLong("255000"),
    createdAt: ISODate("2026-11-21T10:00:00Z"),
    confirmedAt: ISODate("2026-11-21T11:00:00Z"),
    lines: [
      {
        lineNo: NumberInt(1), skuId: "B", quantity: NumberInt(3),
        unitPriceVnd: NumberLong("90000"),
        discountPerUnitVnd: NumberLong("5000")
      }
    ]
  }
]);
~~~

This fixture holds the exact same three Orders, four OrderLines, and amounts as PostgreSQL. The insert is **not idempotent** because `_id` already exists on re-run. Use a dedicated test database, never production. BSON Date fields store exact `Instant`s, not arbitrary strings.

### 6.4. Detail and customer-list queries

~~~javascript
// Detail lookup: one document contains all lines.
db.orders.findOne(
  { tenantId: "T1", orderId: "O100" },
  {
    _id: 0, orderId: 1, status: 1, payableTotalVnd: 1,
    currency: 1, lines: 1
  }
);

// List C1's orders, newest first.
db.orders.find(
  { tenantId: "T1", customerId: "C1" },
  { _id: 0, orderId: 1, status: 1, payableTotalVnd: 1, createdAt: 1 }
).sort({ createdAt: -1, orderId: -1 }).limit(20);
~~~

**Projection note:** project only fields needed by the use case; never return the full document just because querying is easy. If documents later hold addresses, phone numbers, or internal flags, APIs must still enforce **allowlists and authorization**.

### 6.5. Recomputing SKU reports via aggregation

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T1", status: "CONFIRMED" } },
  { $unwind: "$lines" },
  {
    $group: {
      _id: "$lines.skuId",
      units: { $sum: "$lines.quantity" },
      grossVnd: {
        $sum: { $multiply: [
          "$lines.quantity", "$lines.unitPriceVnd"
        ] }
      },
      discountVnd: {
        $sum: { $multiply: [
          "$lines.quantity", "$lines.discountPerUnitVnd"
        ] }
      }
    }
  },
  {
    $project: {
      _id: 0,
      skuId: "$_id",
      units: 1,
      grossVnd: 1,
      discountVnd: 1,
      netVnd: { $subtract: ["$grossVnd", "$discountVnd"] }
    }
  },
  { $sort: { skuId: 1 } }
]);
~~~

Results **must match SQL**: A has 2 units / net 220,000, B has 4 units / net 345,000. **`$unwind` creates one logical row per line in the pipeline**; summing header `payableTotalVnd` afterward would count O100 twice. To sum order-level measures, aggregate **before `$unwind`** or use measures at the right grain.

### 6.6. Reconciling totals inside each document

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T1" } },
  {
    $project: {
      orderId: 1,
      storedGross: "$grossTotalVnd",
      storedDiscount: "$discountTotalVnd",
      storedPayable: "$payableTotalVnd",
      computedGross: {
        $sum: {
          $map: {
            input: "$lines", as: "l",
            in: { $multiply: ["$$l.quantity", "$$l.unitPriceVnd"] }
          }
        }
      },
      computedDiscount: {
        $sum: {
          $map: {
            input: "$lines", as: "l",
            in: { $multiply: [
              "$$l.quantity", "$$l.discountPerUnitVnd"
            ] }
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          { $ne: ["$storedGross", "$computedGross"] },
          { $ne: ["$storedDiscount", "$computedDiscount"] },
          {
            $ne: [
              "$storedPayable",
              { $subtract: ["$computedGross", "$computedDiscount"] }
            ]
          }
        ]
      }
    }
  }
]);
~~~

On clean data, this pipeline also **returns zero documents**. This catches documents whose header totals drifted from embedded lines. As with SQL, post-write checks do not replace atomic write protocols. At large scale, scope checks by tenant or time batch rather than running uncontrolled full scans on hot systems.

## 7. Updating an Order: same aggregate, different physical write protocol

### 7.1. In relational tables: lock root and write multiple rows in one transaction

When a client adds a line to a DRAFT Order, the repository must **lock or check the root version** before touching lines. Transaction pseudocode:

~~~sql
BEGIN;

-- All writers editing lines or confirming must lock the same root first.
SELECT status, version
FROM sales.order_header
WHERE tenant_id = :tenant_id AND order_id = :order_id
FOR UPDATE;

-- Application verifies status='DRAFT', version=:expected_version,
-- and that the new price is valid; otherwise ROLLBACK.

INSERT INTO sales.order_line (
    tenant_id, order_id, line_no, sku_id, quantity,
    unit_price_vnd, discount_per_unit_vnd
) VALUES (
    :tenant_id, :order_id, :line_no, :sku_id, :quantity,
    :unit_price_vnd, :discount_per_unit_vnd
);

UPDATE sales.order_header
SET gross_total_vnd = gross_total_vnd + :gross_delta,
    discount_total_vnd = discount_total_vnd + :discount_delta,
    payable_total_vnd = payable_total_vnd + :payable_delta,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
RETURNING version;

-- COMMIT only if INSERT succeeded, UPDATE touched 1 row,
-- deltas are accurate, and all invariants PASS.
COMMIT;
~~~

**Mandatory assumption:** every `OrderLine` write path—including batch/admin jobs—must follow the same root-locking protocol rather than inserting lines directly against a CONFIRMED header. Using deltas can be efficient yet requires deduplication, overflow checks, line edit/delete handling, and reconciliation; critical commands can recompute totals from lines under the lock.

For `confirm`, the application verifies the root is DRAFT, **reads and sums the locked line set**, updates the header with `expectedVersion`, and writes the outbox row inside the same transaction. The SQL engine does not enforce “confirmed order has >= 1 line” on its own without triggers, procedures, or command protocols.

### 7.2. In a document: single-document atomic mutation

When a document holds both lines and totals, a version-conditioned `updateOne` updates the array and totals **atomically for that document**:

~~~javascript
// Example: add a line to O101 DRAFT version=1.
// New line: SKU B, quantity 1, unit price 90000, discount 5000.
// Run AFTER baseline queries: this mutates O101!
db.orders.updateOne(
  {
    tenantId: "T1", orderId: "O101",
    status: "DRAFT", version: NumberInt(1),
    "lines.lineNo": { $ne: NumberInt(2) }
  },
  {
    $push: {
      lines: {
        lineNo: NumberInt(2),
        skuId: "B", quantity: NumberInt(1),
        unitPriceVnd: NumberLong("90000"),
        discountPerUnitVnd: NumberLong("5000")
      }
    },
    $inc: {
      grossTotalVnd: NumberLong("90000"),
      discountTotalVnd: NumberLong("5000"),
      payableTotalVnd: NumberLong("85000"),
      version: NumberInt(1)
    }
  }
);
~~~

Because `version: 1` and `status: "DRAFT"` sit in the filter, two competing updates against the same version **cannot both succeed** as long as every writer bumps `version`. Verify **`matchedCount=1` and `modifiedCount=1`**; otherwise surface conflict or handle idempotency per command. Server/domain logic computes and validates deltas from a valid line—**never trust deltas straight from client requests**.

Single-document atomicity does **not** solve:

- Retried requests after timeouts: requires an **idempotency key/command ledger**; version conflicts detect contention, not replay results.
- Concurrent writes to separate **inventory** or **payment** documents: requires multi-document transactions where supported, or asynchronous workflows with authoritative owners and compensation.
- Writing **outbox events to a separate collection**: requires multi-document transactions or an explicitly designed durable notification mechanism; a single-document Order update does not atomically commit another collection.
- Cross-document invariants like “total reserved <= on-hand”: still requires an invariant arbitrator in Inventory, regardless of Order embedding lines.

### 7.3. Both paths break if writers bypass the protocol

In PostgreSQL, a script directly inserting `order_line` after CONFIRMED breaks invariants. In MongoDB, a script **replacing the entire document** read seconds earlier overwrites newer versions/prices/lines if it skips conditional updates. Storage engines never replace **write authority, commands, and consistency rules**.

## 8. Aligning APIs, Java, and events: storage must not dictate contracts

Whether choosing relational or document storage, the **Order domain** still enforces controlled behavior:

~~~java
import java.util.*;

record OrderLine(int lineNo, String skuId, int quantity,
                 long unitPriceVnd, long discountPerUnitVnd) {
    OrderLine {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || quantity <= 0 || unitPriceVnd < 0
                || discountPerUnitVnd < 0
                || discountPerUnitVnd > unitPriceVnd) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    long gross() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
    long discount() {
        return Math.multiplyExact((long) quantity, discountPerUnitVnd);
    }
}

record OrderTotals(long gross, long discount, long payable) {}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

final class Order {
    private final String id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private long version;

    Order(String id) { this.id = Objects.requireNonNull(id); }

    void addLine(OrderLine line) {
        if (status != OrderStatus.DRAFT)
            throw new IllegalStateException("Order immutable");
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo()))
            throw new IllegalArgumentException("Duplicate line number");
        // Check overflow before mutating state:
        var now = totals();
        Math.addExact(now.gross(), line.gross());
        Math.addExact(now.discount(), line.discount());
        lines.add(line);
        version++;
    }

    OrderTotals totals() {
        long gross = 0, discount = 0;
        for (OrderLine l : lines) {
            gross = Math.addExact(gross, l.gross());
            discount = Math.addExact(discount, l.discount());
        }
        return new OrderTotals(
            gross, discount, Math.subtractExact(gross, discount));
    }

    void confirm() {
        if (status != OrderStatus.DRAFT || lines.isEmpty())
            throw new IllegalStateException("Cannot confirm");
        totals();
        status = OrderStatus.CONFIRMED;
        version++;
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    OrderStatus status() { return status; }
    long version() { return version; }
    String id() { return id; }
}
~~~

This is **abbreviated** Java 17 illustrating invariants. Repositories need a **rehydration path from persisted state** to restore status, version, and lines accurately without re-running version-bumping commands (omitted here). Sales locks prices from an authoritative source. To guard against overflow across many lines and enforce non-negative policies, real domains can use `Money`/`NUMERIC` with explicit rules.

APIs should not accept a full `Order` from clients and blindly persist it. Instead:

~~~json
{
  "skuId": "B",
  "quantity": 1,
  "expectedVersion": 1,
  "idempotencyKey": "req-add-line-123"
}
~~~

This is an **`AddOrderLine` command DTO**; locked unit price is resolved by application/domain logic, and clients never supply `total` or `status`. An `OrderView` response can expose ID, lines, and amounts while hiding internal versions or sensitive fields unless required.

Post-confirm integration event example:

~~~json
{
  "eventId": "evt-O100-confirmed-v2",
  "eventType": "sales.order-confirmed",
  "schemaVersion": 1,
  "tenantId": "T1",
  "aggregateId": "O100",
  "aggregateVersion": 2,
  "occurredAt": "2026-11-20T09:00:00Z",
  "payload": {
    "orderId": "O100",
    "payableTotalVnd": "310000",
    "currency": "VND"
  }
}
~~~

An event represents a **committed fact** under a contract, not a dump of a row or document. `eventId` stays stable across relay retries; `aggregateVersion` differs from `schemaVersion`. If Sales stores the Order document and events in two collections, **never** claim a single-document update guarantees writing the event; use proper multi-document transactions or outbox mechanics.

## 9. Comparison matrix by business operation

| Requirement | Relational header + line | Document Order embedding lines | What to verify |
| --- | --- | --- | --- |
| Read **one full Order** | JOIN or header then lines, tuned by query | One document if line count and size fit | p95 latency, bytes read, cache, indexes |
| List **Order summaries** | Query header only without loading lines | Projection returning needed fields only | Pagination, deterministic sort |
| Add a DRAFT line | `INSERT` line and `UPDATE` header in transaction | Atomic update of array, totals, and version in one doc | Conflicts, idempotency, validation |
| Confirm an Order | Lock/version root, check lines, update header | Conditional update on root document | Correctness and atomic outbox commit |
| Report by SKU | JOIN header/line, `GROUP BY`, indexes | Aggregation with `$unwind`, `$group` | Grain, line-scanning cost |
| Edit a line | Update matching row and root/version | Positional/array update with version | Blocked after CONFIRMED |
| Cancel/delete Order | Transactions, FKs, retention | Document and copy handling | Business cancellation vs physical delete |
| Orders with thousands of lines | Child rows scale independently | Document size growth and contention | P99, document size limits |
| Schema changes | DDL migrations, backfills | Schema/document versioning, reading legacy docs | Do old writers strip new fields? |
| Long-term historical reports | ETL to facts/dimensions | Export to facts/dimensions | Lineage, late data, retention |

**Never assume one document always equals one I/O, or that a JOIN is always slow.** Indexes, caches, compression, network round-trips, query plans, and read/write strategies decide performance. Reading SQL headers alone can transfer fewer bytes than reading a bulky document; conversely, fetching a whole Order with embedded lines can avoid extra lookups. Measure with representative data.

### Principles for a fair comparison

Both options must run against the same Order set and line counts, identical read/write mixes, identical business constraints, tenant/auth policies, durability guarantees, read consistency, and report freshness. Tune indexes properly on **both**, measure on comparable infrastructure, and inspect p50/p95/p99 instead of just averages.

If MongoDB skips total/version/outbox checks while PostgreSQL runs full transactions, the benchmark **compares different requirements**. If PostgreSQL is forced to read all lines on a summary page while MongoDB projects summaries only, the test is likewise skewed.

## 10. Indexes, queries, and performance testing

### 10.1. Keyed detail lookup

**PostgreSQL:** `PK(tenant_id, order_id)` fetches the header; `order_line`'s PK already starts with `(tenant_id, order_id)` for loading lines. Repositories can JOIN or run two queries under consistent isolation.

**MongoDB:** look up by unique physical `_id`, or via a unique `(tenantId, orderId)` index. If `_id` already encodes the global scoped Order identity and all queries use it, weigh whether a second compound index adds value or pure write cost.

### 10.2. Recent customer orders

Relational uses `(tenant_id, customer_id, created_at DESC, order_id)`, while document uses `(tenantId, customerId, createdAt DESC, orderId DESC)`. Across millions of records, **keyset pagination** on `(createdAt, orderId)` outperforms deep `OFFSET`. All queries must retain the tenant filter; if using DB-level access policies, verify them too.

### 10.3. Reporting by SKU

Relational has dedicated line rows, making JOIN/`GROUP BY` straightforward. Embedded documents use `$unwind` per array element; for heavy reporting workloads, build a **dedicated analytical projection** so OLTP Orders stay focused on commands. Never reject or pick document embedding based solely on one infrequent BI query.

### 10.4. Analyzing execution plans

~~~sql
-- Run only in test or load-controlled environments.
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, payable_total_vnd
FROM sales.order_header
WHERE tenant_id = 'T1' AND customer_id = 'C1'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

~~~javascript
db.orders.find(
  { tenantId: "T1", customerId: "C1" },
  { _id: 0, orderId: 1, payableTotalVnd: 1, createdAt: 1 }
).sort({ createdAt: -1, orderId: -1 }).limit(20)
  .explain("executionStats");
~~~

Metrics to inspect: rows/docs/index keys scanned vs returned; p95/p99 latency; round-trips; bytes and memory footprint; write index cost; write conflict rate; recovery behavior when an Order grows unusually large. An index helping query A can slow writes and add zero value to query B. Never index a field just because it appears in JSON.

## 11. Data sizing, aggregates, and the embedding decision

Assuming **10,000 Orders/day and 8 lines/Order**:

\[
N_{\text{Order/year}}=10.000\times365=3.650.000,\qquad
N_{\text{Line/year}}=3.650.000\times8=29.200.000.
\]

Over one year, relational stores roughly **3.65 million header rows** and **29.2 million line rows**. Document stores roughly **3.65 million Order documents**, averaging eight embedded line elements each. These are **logical unit counts**, not bytes, cost, or speed. Documents grow larger with embedded lines; relational rows have different per-row overhead, indexes, and compression.

### When to embed?

- OrderLine shares Order's lifecycle and is normally read/updated together with the root.
- Line count has realistic bounds and does not grow indefinitely.
- Commands need atomicity across Order status and **that Order's lines**.
- No separate bounded context claims independent write authority over individual lines.
- System-wide SKU queries perform acceptably or offload to a read projection.

### When NOT to embed everything?

- Orders can accumulate thousands or millions of lines, growing unboundedly.
- Multiple workers concurrently mutate different lines of the same Order, creating document hotspots.
- Individual lines have distinct lifecycles, retention, or access policies from the Order.
- Most queries ignore lines while the embedded array is huge.
- Elements need independent updates alongside global invariants; re-evaluate aggregate boundaries and protocols.

MongoDB imposes **document size limits** and costs for updating huge arrays. Check actual limits of your engine/version and never design an infinitely growing document. Splitting OrderLine into a separate collection brings back multi-document transactions and identity constraints—you cannot physically split and still assume single-document atomicity.

### Purposeful snapshots vs blind copying

Locking unit price and discount **at Order creation** is an intentional snapshot: later Catalog price edits never alter CONFIRMED Orders. Conversely, copying full product descriptions, images, all categories, and sensitive customer PII into every Order creates bloat and retention headaches. Snapshot only what is essential for **transaction commitments and historical auditability**; reference or project the rest.

## 12. Transactions, outbox, and cross-context boundaries

The core rule is identical across both stores: **an Order confirms only after domain invariants pass; integration events publish only after source changes commit**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Sales Application
    participant D as Sales Storage
    participant R as Outbox Relay
    participant B as Broker
    participant I as Inventory

    C->>S: ConfirmOrder(orderId, expectedVersion, key)
    S->>S: Verify tenant, idempotency, domain rules
    S->>D: Transaction: Order CONFIRMED + outbox event
    D-->>S: Commit succeeded
    S-->>C: Order CONFIRMED
    R->>D: Poll unpublished outbox
    R->>B: Publish with eventId E1
    B->>I: Deliver E1
    I->>I: Dedup and decide ReserveStock separately
    B->>I: May redeliver E1
    I->>I: Never apply side effect twice
~~~

**Relational:** update header, edit lines if needed, and `INSERT` the outbox row inside **one PostgreSQL transaction**. Transaction commit does not mean the relay already published or consumers already processed it.

**Document:** if using MongoDB with outbox in another collection, use a properly configured **multi-document transaction** or an equivalent durable notification design. Single-document atomic updates **only protect fields inside that document**. Storing pending events inside the Order document itself requires managing size, post-publish cleanup, ordering, relay crashes, and retention—never treat it as automatic end-to-end exactly-once.

**Inventory:** owns its own invariants. It consumes requests/events per contract and reserves stock under Inventory's authority. Sales never mutates inventory in another DB and calls it part of the Order transaction.

### Three common integration bugs

1. **Publishing before commit:** Sales rolls back while Inventory already acted on an unconfirmed Order.
2. **Minting a new `eventId` on retries:** relay retries look like brand-new facts, causing consumers to reserve stock or email twice.
3. **Confusing local atomicity with global ACID:** Order confirmed while Payment declined, with no workflow state or compensation.

Command idempotency keys and `eventId`s are **two distinct identities**. Retrying the same command post-commit returns the stored command result. Republishing the same occurrence retains the original `eventId`. Consumers must deduplicate and commit local side effects atomically with a processed-event record; external HTTP calls also need their own idempotency.

## 13. Security, retention, and traceability

Both models require designing for:

- **Tenant isolation:** tenant-scoped keys, indexes, queries, and authenticated actors. A `tenantId` inside JSON never proves caller authority.
- **Addresses and personal data:** if delivery address snapshots are kept at placement, define read access, retention limits, masking/anonymization, and export rules; never broadcast full PII in generic events.
- **Audit:** who confirmed the order, before/after versions, when, and correction reasons; `createdAt`/`updatedAt` alone are rarely enough for investigations.
- **Deletion/retention:** deleting an Order from primary storage does not automatically purge outbox rows, archives, backups, or analytical facts. Align cleanup with legal obligations and purposes.
- **Price snapshots:** post-purchase Catalog edits never mutate payable amounts on confirmed Orders.
- **Report lineage:** facts record source, `transformVersion`, and business-date policies; never promise line-level replays if source records expired and were purged.

**Document embedding does not exempt field-level exposure control.** If a document contains addresses and internal flags, controllers must return use-case DTOs rather than serializing raw documents to every caller. If field groups differ sharply in lifecycle or permissions, consider splitting storage even if often read together.

## 14. Dedicated analytical model to keep OLTP storage clean

An OLTP structure suited for **reading, editing, and confirming Orders** is rarely optimal for **aggregating tens of millions of lines by SKU/day**. Build a fact table at grain:

> One `FactConfirmedOrderLine` = one `OrderLine` of a valid confirmed Order within a tenant, carrying monetary snapshots and `confirmedAt`.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_confirmed_order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_vnd BIGINT NOT NULL CHECK (gross_vnd >= 0),
    discount_vnd BIGINT NOT NULL CHECK (discount_vnd >= 0),
    net_vnd BIGINT NOT NULL CHECK (net_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (discount_vnd <= gross_vnd),
    CHECK (gross_vnd - discount_vnd = net_vnd)
);
~~~

This fact table can load from **PostgreSQL `order_header` + `order_line`** or from **MongoDB `orders[].lines`**. Source storage shapes differ, yet the target fact **can be identical when business and metric contracts match**.

**Grain caveat:** this works when each `OrderLine` reaches confirmed state exactly once. If partial confirmations, multi-allocations, cancellations/refunds, or post-confirmation edits exist, model **occurrence or adjustment facts** with their own keys. Never overwrite meaningful transaction history just to keep `(Order, lineNo)` unique. Also, `OrderConfirmed` **does not automatically mean** funds were collected; Payment owns capture facts.

When building facts:

1. Keep grain keys stable `(tenant, order, lineNo)` when valid; replays must not `INSERT` duplicates.
2. Read line snapshots from the finalized Order/version, never current Catalog prices.
3. Derive `business_date` from `confirmedAt` using published timezone/cutoff rules, not ETL arrival time.
4. Model versioned corrections/restatements or adjustments for historical fixes.
5. Record source references, schema/transform versions, and watermarks for reconciliation.

Thus choosing relational vs document for **transactions** depends on Order queries and invariants; choosing star schemas, facts/dimensions, or column stores for **analytics** is an independent decision.

## 15. Advanced practice: migrating between both representations

One team may start on PostgreSQL and add a document read model for APIs. Another may start with Order documents and later extract `OrderLine` into a table as reports or line counts grow. **Changing storage must never lose business meaning or silently rewrite history.**

### 15.1. Transforming relational tables into documents

Generating JSON representations from relational sources (run in batches with cutoffs and proper read isolation):

~~~sql
SELECT h.tenant_id, h.order_id, h.customer_id,
       h.status, h.currency_code, h.version,
       h.gross_total_vnd, h.discount_total_vnd,
       h.payable_total_vnd, h.created_at, h.confirmed_at,
       COALESCE(children.lines, '[]'::jsonb) AS lines
FROM sales.order_header AS h
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
        jsonb_build_object(
            'lineNo', l.line_no,
            'skuId', l.sku_id,
            'quantity', l.quantity,
            'unitPriceVnd', l.unit_price_vnd,
            'discountPerUnitVnd', l.discount_per_unit_vnd
        ) ORDER BY l.line_no
    ) AS lines
    FROM sales.order_line AS l
    WHERE l.tenant_id = h.tenant_id
      AND l.order_id = h.order_id
) AS children ON TRUE
WHERE h.tenant_id = :tenant_id
  AND h.order_id > :last_order_id
ORDER BY h.order_id
LIMIT :batch_size;
~~~

**Limitations of this illustrative query:**

- It produces intermediate JSON, **not yet** MongoDB documents converted to proper BSON types, composite `_id`s, validators, timestamps, and permissions. The ETL job must assign `_id`, `NumberLong`/Date types, and schema version.
- If the source mutates across batches, headers and lines might be read at different moments. Use consistent snapshots/cutoffs, proper isolation, or snapshot + CDC for accurate reconciliation.
- Filtering by `orderId` only shows **single-tenant keyset pagination**; across multiple tenants, sort and checkpoint on the full composite key and handle concurrent edits.
- When an order has zero lines, JSON produces an empty array; valid for `DRAFT`, invalid for `CONFIRMED` under our rules.

### 15.2. Safe migration roadmap

~~~mermaid
flowchart TB
    A["1. Define contract<br/>grain, keys, money, states"]
    B["2. Provision new storage<br/>schema, indexes, validator"]
    C["3. Cutoff snapshot/backfill<br/>preserve sourceVersion"]
    D["4. CDC/replay post-cutoff changes<br/>dedup, ordering"]
    E["5. Two-way reconciliation<br/>counts, amounts, lines, status"]
    F["6. Shadow read / canary<br/>measure latency and accuracy"]
    G["7. Cutover write authority<br/>single authoritative source"]
    H["8. Monitor and decommission old<br/>after safety window"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

At each stage:

1. **Authoritative source:** explicitly decide whether PostgreSQL or MongoDB handles Order commands. Two uncoordinated writers mutating the same Order produce split truth.
2. **Snapshot:** preserve tenant, `orderId`, version, status, lines, totals, and timestamps. One header maps to exactly one document; never split or merge Orders accidentally.
3. **Catch-up:** apply changes newer than the snapshot via ordered, idempotent logs/CDC/outbox—**never treat every row `UPDATE` as an `OrderConfirmed`**.
4. **Reconcile:** verify Order counts, total lines, per-Order hashes/values, monetary sums per tenant/cutoff, and null/invalid cases.
5. **Shadow read:** read both stores per request while returning only the authoritative one; compare mapped canonical objects rather than raw JSON strings whose field order or physical types differ.
6. **Canary:** shift traffic/tenants gradually after checking concurrency, read consistency, permissions, and latency.
7. **Cutover:** switch write ownership at a controlled point; prepare rollback plans and rules for commands committed post-cutover.
8. **Cleanup:** retire legacy storage/adapters only after consumers, backups, audits, retention, and restores are verified.

### 15.3. Dual-write hazards

Suppose the app writes **PostgreSQL successfully**, then **MongoDB times out**. If the client retries with a fresh command lacking the same idempotency key, one store ends up with two lines while the other has one. **Two direct client writes to two databases are not a distributed transaction.**

It is usually safer to have **one primary write store** and propagate committed changes via outbox/CDC to replicas/projections with checkpoints and reconciliation. If transitional dual writes are unavoidable, assign an owner and discrepancy arbiter—never call it automatic sync.

### 15.4. Reverse direction: document → tables

If Order documents grow too large, extract `lines` to a separate table/collection. Ensure:

- Preserve `orderId` and `lineNo` within tenant namespace; guard replays against duplicates.
- Enforce FKs or controlled references proving every line belongs to a valid Order.
- Reconcile totals before/after migration and handle malformed legacy documents.
- Prevent `addLine`/`confirm` from running mixed protocols during mixed-version rollouts.
- Prevent old writers from **replacing the entire document** and wiping fields/arrays migrated by new writers.
- Define how un-backfilled legacy Orders and differing document versions are read.

**Rollback is not merely redeploying an old binary.** Once Orders are written under the new schema, an old binary may misread fields or drop versions/totals. In that situation, prefer roll-forward or blocking dangerous writers over destructive rollbacks.

## 16. Equivalence test suite: same truth must yield identical answers

### 16.1. Functional expectations table

| Test case | Relational | Document | Shared criterion |
| --- | --- | --- | --- |
| Load O100 | Header + 2 lines | One doc with 2 lines | Total 310,000, status CONFIRMED |
| Load O101 | Header + 1 line | One doc with 1 line | DRAFT, total 120,000 |
| Load O102 | Header + 1 line | One doc with 1 line | CONFIRMED, total 255,000 |
| List C1 | Header index query | Compound index query | O101 before O100 |
| Report SKU A | Join/filter/group | Match/unwind/group | 2 units, net 220,000 |
| Report SKU B | Join/filter/group | Match/unwind/group | 4 units, net 345,000 |
| Reconcile header/lines | Aggregate SQL | Expression map/reduce | Zero mismatched orders |
| Add line to O101 v1 | Root lock + transaction | Conditional atomic doc update | New version=2, total=205,000 |
| Confirm empty Order | Domain/protocol rejects | Domain/protocol rejects | No event emitted |
| Edit line post-CONFIRMED | Blocked before write | Status filter + domain check | Data unchanged |
| Two requests same version | One succeeds, one conflicts | One matched update, one fails | No lost updates |
| Retried command | Idempotency ledger | Idempotency ledger | Single business effect |
| Outbox write failure | Transaction rollback | Transaction/outbox rollback | No confirmed order lacking event |
| Event redelivery | Consumer dedup | Consumer dedup | No doubled actions/metrics |
| Tenant T2 with same O100 | Tenant-prefixed PK | Namespaced `_id`/compound unique | Never collides with T1 |
| Catalog price changes | OrderLine snapshot intact | Embedded line snapshot intact | Confirmed Order total unchanged |
| Order with 5,000 lines | Measure index/IO/locks | Measure doc size/update contention | Never declare a winner without data |

### 16.2. Deliberate invalid-data tests

Create failing test cases:

- `quantity=0` or negative price;
- `discountPerUnitVnd` greater than `unitPriceVnd`;
- two `lineNo=1` entries in one Order;
- header `payable` off by 1 VND from line sum;
- `CONFIRMED` Order with zero lines;
- tenant T2 caller attempting to read T1's Order;
- duplicate `eventId` processed twice;
- command carrying stale `expectedVersion`.

In relational, `PK`/`CHECK`/`FK` block several of these immediately; multi-row rules need domain/transaction logic, triggers, or reconciliation. In document, the illustrative JSON Schema blocks basic type/range violations yet **does not block duplicate `lineNo`, mismatched totals, or illegal transitions**. Under the same requirements, both systems must enforce or detect **equivalent invariants**, even via different mechanisms.

### 16.3. Concurrency and crash tests

A valuable integration test:

~~~text
Initial: O101 is DRAFT, version=1, payable=120000.
T1 and T2 both read version 1.
T1 adds line B, expected new payable=205000, version=2.
T2 concurrently adds line C against version 1.

PASS:
- Exactly one version=1 command commits;
- The competing command receives conflict/retry per protocol;
- No mismatched header totals or missing/double-counted lines;
- Retrying a command with the same idempotency key creates no extra line;
- No OrderConfirmed event exists if confirm was never run.
~~~

For PostgreSQL, run with real DB transactions, isolation, and locks. For MongoDB, run conditional `updateOne` verifying `matchedCount`; if using multi-document transactions, test transaction/outbox failures too. Sequential mocks cannot prove real concurrency safety.

### 16.4. Property-based checks for money and mapping

Generate valid lines and verify:

\[
\forall\ \text{valid Order}:\quad
\mathrm{gross}\ge\mathrm{discount}\ge0,\quad
\mathrm{payable}=\mathrm{gross}-\mathrm{discount}\ge0.
\]

For each Order, map **PostgreSQL rows → canonical Order** and **MongoDB document → canonical Order**, then assert equality on identity, status, version, lines ordered by `lineNo`, currency, amounts, and timestamps. **Never compare raw JSON strings** since field order and BSON/SQL serialization differ without changing semantics.

Also test **`NULL`/absent** fields, timezones, amounts exceeding JavaScript's safe integer limit, and Orders with many lines. Keep exact integer VND across every serialization boundary rather than casting through floating point.

## 17. Self-study assignment: comparing under changing conditions

Respond with **concise diagrams/notes, illustrative queries, and verifiable reasoning**. There is no requirement to declare one technology “best” universally.

### Part A — Data and calculations

1. **Grain and keys:** state the grain of `order_header`, `order_line`, and the Order document. Why is `lineNo=1` alone insufficient as a global key? Why must `tenant` appear in read paths and links?
2. **Pricing math:** calculate `gross`, `discount`, and `payable` for O100, O101, and O102; total payable of both CONFIRMED Orders; quantities and net amounts for SKU A/B. Why is O101 excluded from the confirmed report?
3. **Detail lookup:** write one SQL query and one `mongosh` query to fetch O100 details; explain physical units read vs number of Orders returned by the API.
4. **Adding a line and confirming:** O101 gets a new line B (`quantity=1`, `unitPriceVnd=90,000`, `discountPerUnitVnd=5,000`), and is then confirmed. Track totals/version step by step and recompute the confirmed report totals.
5. **Invalid data:** if `discountPerUnitVnd=130,000` while `unitPriceVnd=120,000`, where does each model reject it? Are the current SQL `CHECK` or MongoDB JSON Schema alone enough?

### Part B — Consistency and integration

6. **Concurrency:** two requests both read O101 `version=1` and call `addLine`. Describe the protocol ensuring only one succeeds in PostgreSQL and in MongoDB.
7. **Authoritative sources:** `OrderConfirmed` is emitted; Inventory has not responded yet. Can we claim stock is reserved? What happens if Payment declines later?
8. **Outbox writes:** an app saves the Order then crashes before publishing the event. Contrast atomic outbox writes across both models.
9. **Security:** a tenant T2 client guesses T1's `orderId` O100. If documents use `_id = "O100"` or SQL uses a global `orderId` PK, which checks remain mandatory?

### Part C — Architecture and evolution

10. **Growing size:** the product adds custom bundles, an Order reaches 20,000 lines, and multiple workers edit lines. Pick a storage option with justification; if switching from embed to reference, what changes for transactions?
11. **Reporting:** management wants monthly paid order counts and revenue by SKU. Why is `OrderConfirmed` alone insufficient? Propose fact grain and Payment sources.
12. **Migration:** currently on PostgreSQL, you want to add MongoDB as an API read projection. Outline safe backfill, catch-up, shadow reads, cutover, and rollback. Must the Java domain and REST responses change just because read storage changed?
13. **Schema change:** add per-unit discount to legacy data lacking discounts. When is defaulting historical records to `0` valid? What breaks if an old writer replaces a new-schema document?
14. **Technology choice:** compare two workload profiles: (A) small orders mostly read whole; (B) frequent independent line updates plus continuous cross-order reporting. For each, propose a candidate to test first and **three metrics** to measure before deciding.

## 18. Detailed solution guide and self-check points

### 18.1. Grain and arithmetic results

**Q1:** `order_header` represents one Order per `(tenantId, orderId)`; `order_line` represents one line per `(tenantId, orderId, lineNo)`. The document stores **the entire Order aggregate** with its `lines` array under one stable `_id`. `lineNo=1` repeats across millions of Orders; `tenantId` must appear in filters/keys to identify records uniquely and prevent cross-tenant access.

**Q2:** reference table:

| Scope | Gross | Discount | Payable |
| --- | ---: | ---: | ---: |
| O100 | 330,000 | 20,000 | 310,000 |
| O101 (DRAFT) | 120,000 | 0 | 120,000 |
| O102 | 270,000 | 15,000 | 255,000 |
| **CONFIRMED O100 + O102** | **600,000** | **35,000** | **565,000** |
| SKU A in CONFIRMED | 240,000 | 20,000 | 220,000 |
| SKU B in CONFIRMED | 360,000 | 15,000 | 345,000 |

SKU A has two units; SKU B has four. O101 is not yet confirmed so it is excluded from the confirmed cohort; having a line and tentative payable does not change its status.

**Q3:** The tenant/order-scoped SQL JOIN returns **two line rows** for O100, yet the mapper builds **one `OrderView`** containing a two-element `lines` list. The document query returns one Order document when lines are embedded; the API likewise returns **one `OrderView`**. Single query vs two rows does not automatically determine latency; indexes, bytes, and mapping matter too.

### 18.2. Adding a line to O101 and checking cohort changes

**Q4:** before the command, O101 has `version=1` and totals:

~~~text
Gross=120000, Discount=0, Payable=120000, Status=DRAFT.

Add B: q=1, price=90000, discountPerUnit=5000.
DeltaGross=90000, DeltaDiscount=5000, DeltaPayable=85000.

After addLine:
Gross=210000, Discount=5000, Payable=205000,
Status=DRAFT, Version=2.

After confirm (under one version bump per command):
Gross=210000, Discount=5000, Payable=205000,
Status=CONFIRMED, Version=3.
~~~

Post-confirm, the CONFIRMED cohort holds three Orders:

| Measure | Result |
| --- | --- |
| CONFIRMED Order count | 3 |
| Total gross | 810,000 VND |
| Total discount | 40,000 VND |
| Total payable | **770,000 VND** |
| SKU A | 3 units, gross 360,000, discount 20,000, net **340,000 VND** |
| SKU B | 5 units, gross 450,000, discount 20,000, net **430,000 VND** |

Notice that Order counts and OrderLine totals must be **computed at their respective grains**. If you ran Section 7.2's `updateOne` before running baseline queries, results changed: use a clean environment or record exact state checkpoints when comparing.

**Q5:** PostgreSQL `CHECK` rejects `discountPerUnitVnd > unitPriceVnd` within a line. Our **illustrative** MongoDB validator only checks non-negative discount and unit price individually without comparing both fields on the same element. Hence MongoDB relies on command/domain checks (plus optional `$expr` validator additions). Both still need checks for **header totals matching lines**, `CONFIRMED` status rules, and write authority; single-row `CHECK`/simple JSON Schema are insufficient.

### 18.3. Concurrency and business boundaries

**Q6:** PostgreSQL: both commands lock the root in consistent order, verify `DRAFT` and `expectedVersion` under the lock; the winner writes line + header/version in the transaction, while the loser sees the bumped version and conflicts. Never allow SQL batches to bypass the root. MongoDB: `updateOne` filters `DRAFT` and `expectedVersion=1` while incrementing `version` atomically; once the first commits, the second's filter matches nothing. Both also need idempotency for command retries.

**Q7:** no. `OrderConfirmed` is a Sales decision. Inventory independently decides `StockReserved`/`Rejected` from authoritative stock; if Payment declines, the workflow transitions to pending/failed, releases reservations, or compensates per policy. Never equate setting Order to `CONFIRMED` with an ACID transaction across Inventory and Payment.

**Q8:** Relational writes header + outbox inside one PostgreSQL transaction. Document needs a multi-document transaction across Order + outbox collection (or an equivalently durable pattern); a single-document `updateOne` on Order does not insert into another collection. Post-commit relays can still redeliver the same `eventId`, so consumers must deduplicate.

**Q9:** even with globally unique IDs, the app must authenticate the actor, verify the caller belongs to T1 (or holds authorized scope), and enforce tenant filters on every read/write path. A unique `_id` is not an authorization token. A global SQL PK likewise never blocks guessed-ID cross-tenant queries. If PII is involved, enforce field/use-case permissions too.

### 18.4. Scale, analytics, migration, and choice

**Q10:** with 20,000 lines and concurrent line workers, **evaluate referencing/splitting lines** into relational rows or a separate line collection with its own identity, avoiding document size limits and update hotspots. Still do not let lines freely mutate Order status: coordinate via root/version/locks or re-evaluate aggregate boundaries around real invariants. Moving from one document to multiple documents means formerly single-document atomic operations may now need multi-document transactions or coordination protocols.

**Q11:** `OrderConfirmed` does not prove `PaymentCaptured`; use Payment facts with `captureId`/`amount`/`occurredAt` and order–capture reconciliation rules. For SKU-level sales, use eligible `OrderLine` facts or SKU-allocated captures for partial payments. Avoid joining multi-row `PaymentAttempt`s directly (which multiplies amounts) and avoid summing mixed currencies without conversion.

**Q12:** keep PostgreSQL as the write source, build a document **read projection** via snapshot/backfill + CDC/outbox, deduplicate/version, reconcile counts/lines/totals per tenant, shadow-read, and gradually shift read traffic. Rollback simply routes readers back to PostgreSQL while preserving the single write source. **Java domain, API responses, and integration events can stay unchanged** if contracts remain intact. Moving write authority to MongoDB later would require a much more complex cutover and rollback/roll-forward plan.

**Q13:** defaulting historical `discount = 0` is only valid if legacy contracts **truly had zero discounts** and no external voucher/discount systems were omitted. If historical data is missing, mark unknown/quarantine or source elsewhere—never fabricate zero. An old writer reading a v2 document with discounts and replacing it as v1 can drop discount fields and recompute totals under old rules, corrupting money. Use schema versions, conditional updates, and disable unsafe legacy writers before enabling new features.

**Q14:**

- **Workload A:** embedding lines in documents is a strong candidate to test because most queries read a small whole Order updated atomically through one root. Relational also works well if already established with good indexes.
- **Workload B:** separate line tables or referenced models are strong candidates because lines update independently and cross-order reporting is heavy; protect Order invariants without arbitrary split transactions. Documents with aggregations/read projections can still be evaluated if benchmarks support them.
- **Three minimum metrics per profile:** p95 latency of dominant use cases, concurrent write throughput and lock/conflict rate, and total bytes/index/storage or latency/cost of key analytical queries. Add p99 for outlier large Orders and backup/restore times for operational readiness.

**There is no universal rule that “MongoDB is always faster for Orders” or “PostgreSQL is always more correct.”** Both can protect the same invariants when paired with sound protocols and awareness of transaction limits. Base decisions on **workload, correctness, operations, and evolvability**.

## 19. Lab script, reporting template, and grading rubric

### 19.1. Repeatable practice steps

1. Provision **isolated test environments** for PostgreSQL and MongoDB. Never load fixture data into production.
2. Run the Section 5 PostgreSQL DDL, then insert the three Orders and four OrderLines. Verify row counts and manually computed totals.
3. Create the Section 6 MongoDB collection, validator, and indexes, then insert the **same data** via `mongosh`. Never run `insertMany` twice without clearing the test dataset.
4. Run both query groups: O100 detail + C1 listing, and confirmed SKU report. Record outputs **as canonical values** against the reference table rather than raw text comparison.
5. Run the total-reconciliation check on both engines; expect **zero mismatched rows/documents**.
6. On a copy of the dataset (or after capturing baseline results), add line B to O101; verify `version=2` and `payable=205,000`.
7. Execute `confirm` through a **state/version-checked command path** in a test app rather than manually setting status and calling it a domain test. Verify `version=3`, confirmed cohort, and SKU totals.
8. Test invalid, duplicate, and concurrent requests. Record which errors are caught by **validators/schemas**, which by **domain/transactions**, and which only by reconciliation.
9. Use execution plans and a larger representative dataset to measure p95/p99, conflicts, index sizes, and report latency; state configuration and assumptions.
10. Write a **decision report**: workload, constraints, candidates, measurements, selection, open risks, and pre-production exit criteria.

These steps describe a learning lab—**they do not claim benchmarks were executed inside this lesson**. Parameter placeholders like `:tenant_id` illustrate application prepared statements; bind parameters properly rather than pasting colons verbatim into `psql` without variables configured.

### 19.2. Comparison report template

| Item to record | Learner's findings |
| --- | --- |
| Workload (Order count, lines/order, read/write ratio) | ... |
| Business invariants and bounded contexts | ... |
| Relational PK/FK/CHECK, indexes, transactions | ... |
| Document shape, `_id`, validator, indexes, atomic updates | ... |
| SQL and `mongosh` queries with matching answers | ... |
| p95 for Order detail and customer listing | ... |
| p95 and rows/docs scanned for SKU aggregation | ... |
| Version conflict / idempotency tests | ... |
| Outbox and transaction boundaries | ... |
| Backup/restore, retention, PII, and tenant isolation | ... |
| Growth and migration risks | ... |
| Decision and revisit triggers | ... |

Do not invent benchmark numbers without a test environment; **mark “Not measured” and state the experiment needed** instead of fabricating latencies or compression ratios.

### 19.3. Reference rubric — 100 points

| Criterion | Max points | Passing evidence |
| --- | ---: | --- |
| Grain, IDs, invariants, and ownership | 15 | Clear Order/Line, accurate tenant scope, sound totals/transitions |
| Relational model | 20 | Accurate DDL/keys/FK/CHECK/indexes, transactions, and queries |
| Document model | 20 | Justified embedding, BSON/validator/indexes, atomic versioned updates |
| Arithmetic reconciliation | 15 | Matches O100/O101/O102, SKU A/B, and O101 update scenario |
| Concurrency safety and integration | 15 | Idempotency, versioning, outbox, no Inventory/Payment conflation |
| Trade-offs, benchmarks, and migrations | 10 | Workload-driven choice without unverified performance claims |
| Presentation and traceability | 5 | Clear explanations, explicit assumptions, tests, and conclusions |
| **Total** | **100** | |

High scores do not depend on picking PostgreSQL or MongoDB. A submission choosing documents while clearly explaining large-document limits, cross-document transactions, testing, and monitoring can outscore a relational submission chosen merely “because it has FKs.”

## 20. Design checklist and conclusion

Before finalizing an Order representation, verify:

- **Grain:** Order is one aggregate; OrderLine is identified within an Order; line-level analytical facts are a separate model.
- **IDs and tenant:** keys, joins/references, indexes, APIs, and events share one namespace with zero cross-tenant leakage.
- **Price snapshots:** `unitPrice` and `discount` are locked; current catalog prices never rewrite past orders.
- **Money:** gross, discount, and payable compute accurately without floats or untrusted client totals.
- **Status:** `DRAFT` allows edits; `CONFIRMED` blocks normal line mutations; empty/cancel rules have commands and tests.
- **Relational:** header/line use PK/FK/CHECK, transactions protect multi-row invariants, and direct writers cannot bypass the root.
- **Document:** `lines` array stays bounded; schema validation, versions, and atomic updates protect the root without assuming validators enforce every invariant.
- **Outbox:** facts publish post-commit; `eventId` and command idempotency keys stay distinct.
- **Cross-context:** Sales never directly mutates stock or payments; intermediate/reconciliation states handle slow or failed downstream services.
- **Queries:** detail, Order list, and SKU analytics have verified queries and indexes.
- **Analytics:** never count lines as Orders, never sum header totals post-`$unwind`, and never treat `OrderConfirmed` as `PaymentCaptured`.
- **Performance:** fair data and measurements covering p95/p99, bytes scanned, contention, index/storage footprint, and recovery.
- **Evolution:** planned field additions, document versions, mixed-version writers, and backfills; no uncoordinated dual writes.
- **Security:** DTOs never expose raw storage PII/internal flags; tenant permissions never rely on unguessable IDs.
- **Verification:** both representations must return **565,000 VND** on the CONFIRMED baseline and **770,000 VND** after adding a line to O101 and confirming, at their respective checkpoints.

**Conclusion:** The same **Order–OrderLine** domain can be represented as **two relational tables with foreign keys** or **one document embedding a lines array**. Relational provides cross-table key/FK enforcement and multi-row transactions; documents fit bounded aggregates read/written together via document-level atomic updates. Neither automatically solves **total-amount invariants, state transitions, tenant authorization, idempotency, events, or grain-safe reporting**. Start from **requirements and the domain model**, pick physical structures from workloads, write equivalent queries over shared data, test invalid cases, and measure real performance before deciding. That turns the relational-vs-document debate into an **explainable, verifiable, and evolvable data modeling decision**.
