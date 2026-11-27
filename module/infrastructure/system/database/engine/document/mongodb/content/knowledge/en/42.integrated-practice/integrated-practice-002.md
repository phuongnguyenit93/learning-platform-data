# Designing Documents, Validators, and Key Business Queries in MongoDB

## 1. Integrated Practice Assignment

This lesson builds a **multi-tenant order management** database. Each tenant is a store; customers, product catalogs, and orders must be queried strictly within the appropriate tenant scope. The application needs to store items and locked-in prices inside each order, look up orders by order number, list orders by status, view customer history, find orders containing a SKU, generate revenue reports, update statuses, and safely reserve inventory.

Components to complete:

1. Design three collections: `customers`, `products`, and `orders`.
2. Choose to **embed** line-item information and price snapshots, and **reference** the catalog/customer.
3. Create `$jsonSchema` validators to check BSON types, required fields, enums, and array bounds.
4. Create a sample dataset with **7 orders** belonging to tenants A/B with clear expected results.
5. Design unique/compound/multikey indexes according to the query matrix.
6. Write queries using `find`, `countDocuments`, `distinct`, aggregation, `$lookup`, paging, and `explain`.
7. Protect concurrent writes with unique indexes, atomic conditional updates, versioning, and transactions when needed.
8. Verify schema validation and distinguish conditions the DB can enforce from domain logic.
9. Write test cases, performance/security checklists, and a migration plan.

**Rule:** all `drop()`, `collMod`, schema changes, seed data, and update commands in this lesson must only be run on an **authorized lab**. Never use a production URI or a database containing real data.

### 1.1. Business Requirements

| Use Case | Primary Filter | Result | Characteristics |
| --- | --- | --- | --- |
| Open order by number | tenantId + orderNo | Single order | Unique |
| PAID list | tenantId + status | Latest page | Stable sort |
| Customer history | tenantId + customerId | Multiple orders | No tenant leak |
| Orders with SKU | tenantId + items.sku | Multiple orders | Multikey |
| Orders by date | tenantId + createdAt range | Multiple orders | UTC boundary |
| Revenue | tenantId + paid statuses | Decimal128 number | Aggregation |
| Top SKU | tenantId + status | Units/amount | Unwind/group |
| Status transition | tenant + ID + version | Modified count | Atomicity |
| Reserve stock | tenantId + sku + stock | Modified count | Non-negative |
| Place order | Code/stock/price | New order | Idempotency |

### 1.2. Invariants to Protect

- `(tenantId, orderNo)` must not be duplicated.
- Each order must have at least one line item; quantity must be a positive integer.
- Money must be stored as Decimal128, without mixing `double`/`string`.
- `total` must equal the sum of `lineTotal` (the lab model has no tax/shipping/discount).
- `lineTotal = unitPrice × quantity`.
- `status` must belong to `DRAFT`, `PLACED`, `PAID`, `SHIPPED`, `CANCELLED`.
- Workflow must not jump between invalid statuses.
- Orders must store the price **at the time of purchase**, independent of the current catalog price.
- Deducting stock must never drive inventory counts negative.
- Requests from user A must never read, modify, or delete data belonging to B.
- Client retries must not create multiple orders for the same business request.

No single feature solves everything: `$jsonSchema` validates structure, unique indexes prevent duplicates, atomic updates/transactions handle concurrency, and **service/authorization logic** enforces business workflows.

---

## 2. Data Model and Embed/Reference Decisions

```text
order_design_lab
│
├── customers
│     _id, tenantId, displayName, email, createdAt
│
├── products
│     _id, tenantId, sku, name, currentPrice, stock, active
│
└── orders
      _id, tenantId, orderNo, schemaVersion, version
      status, currency, total, createdAt, updatedAt
      customer { customerId, displayName }  <-- snapshot
      items [
          { sku, name, quantity, unitPrice, lineTotal }
      ]                                     <-- snapshot
      shipping { city }
      payment { method, paidAt }             <-- optional
      tags, note                             <-- optional
```

### 2.1. Why Embed Items?

When opening an order, the application must display the **item name, quantity, and price at the time the customer placed it**. If it only kept `productId`, every read would need to fetch the current price or join, risking displaying inaccurate historical data.

By embedding, a single order read retrieves all details, and updating multiple fields within the **same document** has document-level atomicity.

Limitation: unboundedly growing arrays cause document growth and can hit the **16 MiB** BSON document limit. Therefore, the lab caps `items` at 20 items/order; production should adjust based on business needs and actual profiles.

### 2.2. Why Reference Product/Customer?

The `products` catalog is the source of truth for current price and inventory. `customers` stores current customer info. The order stores only the fields needed for a historical snapshot/record.

For example, if tenant A's HEAD price changes from 89.90 to 95.00:

- `products.currentPrice`: 95.00.
- `orders.items.unitPrice` on older orders: **remains 89.90**.

This is **intentional** denormalization, not arbitrary duplication.

### 2.3. When Should You Not Embed?

- Arrays grow unboundedly and sub-elements need pagination.
- Sub-elements are updated independently at high frequency.
- Complex many-to-many relationships require multi-directional lookups.
- Referenced objects are too large or contain PII that should not be copied.
- Analytics needs differ substantially from OLTP.

`$lookup` can be used for admin/reporting without forcing joins on the hot path.

---

## 3. Choosing BSON Types

| Field | BSON Type | In Java | Notes |
| --- | --- | --- | --- |
| `_id`, `tenantId`, `orderNo`, `sku` | `string` | `String` | Business identifier |
| `schemaVersion`, `version`, `quantity`, `stock` | `int` | `int`/`Integer` | 32-bit integer |
| `unitPrice`, `lineTotal`, `total`, `currentPrice` | `decimal` | `BigDecimal` | Exact currency |
| `createdAt`, `updatedAt`, `paidAt` | `date` | `Instant`/`Date` | UTC timestamp |
| `active` | `bool` | `boolean` | Flag |
| `items`, `tags` | `array` | `List` | Elements with schema |
| `customer`, `shipping`, `payment` | `object` | Embedded classes/records | Field groups |

Correct example:

```javascript
{
  quantity: NumberInt(2),
  unitPrice: NumberDecimal("89.90"),
  createdAt: ISODate("2026-10-20T08:00:00Z")
}
```

Do not replace `NumberDecimal("89.90")` with JavaScript `89.90`, because subsequent monetary calculations may suffer binary floating-point rounding errors. In Java, use `new BigDecimal("89.90")` with an explicit rounding policy.

`Date` in BSON stores UTC milliseconds; to filter a day in `Asia/Ho_Chi_Minh`, convert the local day boundaries to UTC **before** querying.

---

## 4. Creating Lab Database and Collections

Run the following snippets in **mongosh**. Never run `drop()` outside a lab environment.

```javascript
var lab = db.getSiblingDB("order_design_lab");

lab.orders.drop();
lab.products.drop();
lab.customers.drop();
```

`drop()` may return `false` if a collection does not exist yet, which does not mean an error occurred. What matters is verifying that the **MongoDB URI/host is a test instance**.

### 4.1. Primary Validator: orders

```javascript
lab.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "schemaVersion", "version",
        "tenantId", "orderNo", "customer", "items",
        "total", "currency", "status",
        "createdAt", "updatedAt", "shipping"
      ],
      additionalProperties: false,
      properties: {
        _id: {
          bsonType: "string",
          minLength: 1
        },
        _class: {
          bsonType: "string"
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 1,
          maximum: 1
        },
        version: {
          bsonType: "int",
          minimum: 1
        },
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        orderNo: {
          bsonType: "string",
          minLength: 1
        },
        customer: {
          bsonType: "object",
          required: ["customerId", "displayName"],
          additionalProperties: false,
          properties: {
            customerId: { bsonType: "string", minLength: 1 },
            displayName: { bsonType: "string", minLength: 1 }
          }
        },
        items: {
          bsonType: "array",
          minItems: 1,
          maxItems: 20,
          items: {
            bsonType: "object",
            required: [
              "sku", "name", "quantity",
              "unitPrice", "lineTotal"
            ],
            additionalProperties: false,
            properties: {
              sku: { bsonType: "string", minLength: 1 },
              name: { bsonType: "string", minLength: 1 },
              quantity: {
                bsonType: "int",
                minimum: 1
              },
              unitPrice: {
                bsonType: "decimal",
                minimum: NumberDecimal("0")
              },
              lineTotal: {
                bsonType: "decimal",
                minimum: NumberDecimal("0")
              }
            }
          }
        },
        total: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        currency: {
          enum: ["USD"]
        },
        status: {
          enum: [
            "DRAFT", "PLACED", "PAID",
            "SHIPPED", "CANCELLED"
          ]
        },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
        shipping: {
          bsonType: "object",
          required: ["city"],
          additionalProperties: false,
          properties: {
            city: { bsonType: "string", minLength: 1 }
          }
        },
        payment: {
          bsonType: "object",
          required: ["method", "paidAt"],
          additionalProperties: false,
          properties: {
            method: {
              enum: ["CARD", "CASH", "BANK_TRANSFER"]
            },
            paidAt: { bsonType: "date" }
          }
        },
        tags: {
          bsonType: "array",
          maxItems: 10,
          items: { bsonType: "string" }
        },
        note: {
          bsonType: ["string", "null"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

### 4.2. Explaining the Validator

| Keyword | Condition |
| --- | --- |
| `required` | Field must be present |
| `bsonType` | BSON type must match |
| `enum` | Only a fixed set of values is allowed |
| `minItems`/`maxItems` | Array length bounds |
| `minimum` | Number cannot be less than threshold |
| `additionalProperties:false` | Rejects fields outside the schema |
| `validationLevel:"strict"` | All checked writes are validated |
| `validationAction:"error"` | Rejects invalid writes |

A few notes:

- `_id` must be listed in `properties` when using `additionalProperties:false`.
- `_class` is permitted as a string to accommodate default Spring Data type mapping. If the framework writes `_class` inside **embedded objects**, nested validators must allow it as well; teams can use a custom type mapper or configure aliases and integration tests.
- `schemaVersion` describes the **schema's version**, while `version` guards concurrent updates.
- `items` is an array of **documents**, each requiring `sku/name/quantity/unitPrice/lineTotal`.
- `payment` is optional, but if present it requires `method` and `paidAt`.
- The `currency=["USD"]` enum intentionally scopes the lab. Multi-currency production systems need expansion and clear accounting policies.

**Limitation:** `$jsonSchema` here **does not validate** `total == sum(lineTotal)`, `lineTotal == price × quantity`, customer/product reference existence, tenant authorization, or valid state transitions. Those are domain/transaction logic, not schema shape.

---

## 5. Validators for Products and Customers

### 5.1. Products

```javascript
lab.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "sku", "name",
        "currentPrice", "stock", "active"
      ],
      additionalProperties: false,
      properties: {
        _id: { bsonType: "string" },
        _class: { bsonType: "string" },
        tenantId: { bsonType: "string", minLength: 1 },
        sku: { bsonType: "string", minLength: 1 },
        name: { bsonType: "string", minLength: 1 },
        currentPrice: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        stock: {
          bsonType: "int",
          minimum: 0
        },
        active: { bsonType: "bool" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

`stock` is non-negative per the validator, but preventing two concurrent requests from overselling requires an **atomic stock update** with a predicate.

### 5.2. Customers

```javascript
lab.createCollection("customers", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "displayName",
        "email", "createdAt"
      ],
      additionalProperties: false,
      properties: {
        _id: { bsonType: "string" },
        _class: { bsonType: "string" },
        tenantId: { bsonType: "string", minLength: 1 },
        displayName: { bsonType: "string", minLength: 1 },
        email: { bsonType: "string", minLength: 3 },
        createdAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Emails should be normalized/lowercased and validated by the application. `minLength:3` is not proper email validation. If case-insensitive uniqueness is required, design a collation or canonical field with a matching index.

### 5.3. Confirming the Server Stored the Validators

```javascript
lab.getCollectionInfos({ name: "orders" });
lab.getCollectionInfos({ name: "products" });
lab.getCollectionInfos({ name: "customers" });
```

The output reveals the actual collection options. Simply seeing `createCollection` in source code does not prove the validator exists on the target database.

---

## 6. Seeding Catalogs

Run after creating the collections.

### 6.1. Products: Different Prices Across Tenants

```javascript
lab.products.insertMany([
  {
    _id: "A-PHEAD", tenantId: "A", sku: "HEAD",
    name: "Headphones",
    currentPrice: NumberDecimal("89.90"),
    stock: NumberInt(12),
    active: true
  },
  {
    _id: "A-PCABLE", tenantId: "A", sku: "CABLE",
    name: "Cable",
    currentPrice: NumberDecimal("9.50"),
    stock: NumberInt(50),
    active: true
  },
  {
    _id: "A-PMOUSE", tenantId: "A", sku: "MOUSE",
    name: "Mouse",
    currentPrice: NumberDecimal("24.00"),
    stock: NumberInt(30),
    active: true
  },
  {
    _id: "B-PHEAD", tenantId: "B", sku: "HEAD",
    name: "Headphones",
    currentPrice: NumberDecimal("99.90"),
    stock: NumberInt(20),
    active: true
  },
  {
    _id: "B-PCABLE", tenantId: "B", sku: "CABLE",
    name: "Cable",
    currentPrice: NumberDecimal("11.50"),
    stock: NumberInt(25),
    active: true
  }
]);
```

Having `sku="HEAD"` in both tenants is valid; the business catalog identifier is `(tenantId,sku)`.

### 6.2. Customers

```javascript
lab.customers.insertMany([
  {
    _id: "A-C01", tenantId: "A",
    displayName: "Ngoc", email: "ngoc@example.test",
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "A-C02", tenantId: "A",
    displayName: "Minh", email: "minh@example.test",
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "B-C01", tenantId: "B",
    displayName: "Lan", email: "lan@example.test",
    createdAt: ISODate("2026-10-01T09:00:00Z")
  },
  {
    _id: "B-C02", tenantId: "B",
    displayName: "Hai", email: "hai@example.test",
    createdAt: ISODate("2026-10-03T09:00:00Z")
  }
]);

lab.products.countDocuments({});  // 5
lab.customers.countDocuments({}); // 4
```

Use the `.test` domain so synthetic addresses are never confused with real emails.

---

## 7. Seeding 7 Orders

### 7.1. Tenant A Orders

```javascript
lab.orders.insertMany([
  {
    _id: "A-O1001",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-001",
    customer: { customerId: "A-C01", displayName: "Ngoc" },
    items: [
      {
        sku: "HEAD", name: "Headphones",
        quantity: NumberInt(2),
        unitPrice: NumberDecimal("89.90"),
        lineTotal: NumberDecimal("179.80")
      },
      {
        sku: "CABLE", name: "Cable",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("9.50")
      }
    ],
    total: NumberDecimal("189.30"),
    currency: "USD",
    status: "PLACED",
    createdAt: ISODate("2026-10-20T08:00:00Z"),
    updatedAt: ISODate("2026-10-20T08:00:00Z"),
    shipping: { city: "Hanoi" },
    tags: ["priority"]
  },
  {
    _id: "A-O1002",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-002",
    customer: { customerId: "A-C02", displayName: "Minh" },
    items: [
      {
        sku: "MOUSE", name: "Mouse",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("24.00"),
        lineTotal: NumberDecimal("24.00")
      },
      {
        sku: "CABLE", name: "Cable",
        quantity: NumberInt(2),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("19.00")
      }
    ],
    total: NumberDecimal("43.00"),
    currency: "USD",
    status: "PAID",
    createdAt: ISODate("2026-10-21T08:00:00Z"),
    updatedAt: ISODate("2026-10-21T10:00:00Z"),
    shipping: { city: "Da Nang" },
    payment: {
      method: "CARD",
      paidAt: ISODate("2026-10-21T10:00:00Z")
    }
  },
  {
    _id: "A-O1003",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-003",
    customer: { customerId: "A-C01", displayName: "Ngoc" },
    items: [
      {
        sku: "HEAD", name: "Headphones",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("89.90"),
        lineTotal: NumberDecimal("89.90")
      }
    ],
    total: NumberDecimal("89.90"),
    currency: "USD",
    status: "SHIPPED",
    createdAt: ISODate("2026-10-23T08:00:00Z"),
    updatedAt: ISODate("2026-10-24T11:00:00Z"),
    shipping: { city: "Hanoi" },
    payment: {
      method: "BANK_TRANSFER",
      paidAt: ISODate("2026-10-23T10:00:00Z")
    }
  },
  {
    _id: "A-O1004",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-004",
    customer: { customerId: "A-C02", displayName: "Minh" },
    items: [
      {
        sku: "CABLE", name: "Cable",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("9.50")
      }
    ],
    total: NumberDecimal("9.50"),
    currency: "USD",
    status: "CANCELLED",
    createdAt: ISODate("2026-10-24T08:00:00Z"),
    updatedAt: ISODate("2026-10-24T10:00:00Z"),
    shipping: { city: "Hai Phong" },
    note: "Customer cancelled before payment"
  },
  {
    _id: "A-O1005",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-005",
    customer: { customerId: "A-C01", displayName: "Ngoc" },
    items: [
      {
        sku: "CABLE", name: "Cable",
        quantity: NumberInt(3),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("28.50")
      }
    ],
    total: NumberDecimal("28.50"),
    currency: "USD",
    status: "PAID",
    createdAt: ISODate("2026-10-25T08:00:00Z"),
    updatedAt: ISODate("2026-10-25T09:00:00Z"),
    shipping: { city: "Hanoi" },
    payment: {
      method: "CASH",
      paidAt: ISODate("2026-10-25T09:00:00Z")
    }
  }
]);
```

### 7.2. Tenant B Orders

```javascript
lab.orders.insertMany([
  {
    _id: "B-O2001",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "B",
    orderNo: "BO-001",
    customer: { customerId: "B-C01", displayName: "Lan" },
    items: [
      {
        sku: "HEAD", name: "Headphones",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("99.90"),
        lineTotal: NumberDecimal("99.90")
      }
    ],
    total: NumberDecimal("99.90"),
    currency: "USD",
    status: "PAID",
    createdAt: ISODate("2026-10-22T08:00:00Z"),
    updatedAt: ISODate("2026-10-22T11:00:00Z"),
    shipping: { city: "Ho Chi Minh City" },
    payment: {
      method: "CARD",
      paidAt: ISODate("2026-10-22T11:00:00Z")
    }
  },
  {
    _id: "B-O2002",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "B",
    orderNo: "BO-002",
    customer: { customerId: "B-C02", displayName: "Hai" },
    items: [
      {
        sku: "CABLE", name: "Cable",
        quantity: NumberInt(2),
        unitPrice: NumberDecimal("11.50"),
        lineTotal: NumberDecimal("23.00")
      }
    ],
    total: NumberDecimal("23.00"),
    currency: "USD",
    status: "PLACED",
    createdAt: ISODate("2026-10-26T08:00:00Z"),
    updatedAt: ISODate("2026-10-26T08:00:00Z"),
    shipping: { city: "Can Tho" }
  }
]);
```

### 7.3. Baseline Table

| ID | Tenant | Status | Customer | Total USD |
| --- | --- | --- | --- | ---: |
| A-O1001 | A | PLACED | A-C01 | 189.30 |
| A-O1002 | A | PAID | A-C02 | 43.00 |
| A-O1003 | A | SHIPPED | A-C01 | 89.90 |
| A-O1004 | A | CANCELLED | A-C02 | 9.50 |
| A-O1005 | A | PAID | A-C01 | 28.50 |
| B-O2001 | B | PAID | B-C01 | 99.90 |
| B-O2002 | B | PLACED | B-C02 | 23.00 |

```javascript
lab.orders.countDocuments({});                // 7
lab.orders.countDocuments({ tenantId: "A" }); // 5
lab.orders.countDocuments({ tenantId: "B" }); // 2
lab.orders.countDocuments({
  tenantId: "A",
  status: "PAID"
}); // 2
```

Running the update, insert, or transaction exercises below **will alter this baseline**. When re-verifying against the original expectations, reset/reseed the lab collections.

---

## 8. Indexes for Key Workloads

### 8.1. Unique Order Lookup

```javascript
lab.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    name: "uq_tenant_orderNo",
    unique: true
  }
);
```

### 8.2. List by Status/Time

```javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "ix_tenant_status_time_id" }
);
```

### 8.3. Customer History

```javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    "customer.customerId": 1,
    createdAt: -1,
    _id: -1
  },
  { name: "ix_tenant_customer_time_id" }
);
```

### 8.4. SKU Inside Array

```javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    "items.sku": 1,
    createdAt: -1
  },
  { name: "ix_tenant_items_sku_time" }
);
```

This is a **multikey index** because `items` is an array. One document can generate multiple index entries; there are restrictions when a compound index includes multiple array paths. Measure write amplification and actual sort plans.

### 8.5. Catalog Uniqueness

```javascript
lab.products.createIndex(
  { tenantId: 1, sku: 1 },
  { name: "uq_tenant_sku", unique: true }
);

lab.customers.createIndex(
  { tenantId: 1, email: 1 },
  { name: "uq_tenant_email", unique: true }
);
```

In the lab, emails are lowercase. For case-insensitive requirements, use a canonical key or matching collation/unique index; MongoDB does not normalize emails automatically.

### 8.6. Inspecting Actual Indexes

```javascript
lab.orders.getIndexes();
lab.products.getIndexes();
lab.customers.getIndexes();
```

**Declaring an index does not mean it was created successfully**: a unique index can fail due to existing duplicate data. Nor is an index automatically chosen for every query; inspect `explain`.

---

## 9. Query 1: Finding a Single Order by Number

```javascript
lab.orders.findOne({
  tenantId: "A",
  orderNo: "AO-001"
});
```

Expected `_id="A-O1001"`.

Because the unique business key is only unique **within a tenant**, never query `{orderNo:"AO-001"}` from an API without scoping by tenant. The tenant must come from the authenticated principal/authorization layer, never trusted directly from client input.

Lookups by `_id` should also enforce tenant scope at the business layer:

```javascript
lab.orders.findOne({
  _id: "A-O1001",
  tenantId: "A"
});
```

---

## 10. Query 2: PAID List with Projection

```javascript
lab.orders.find(
  {
    tenantId: "A",
    status: "PAID"
  },
  {
    _id: 1,
    orderNo: 1,
    status: 1,
    total: 1,
    "customer.displayName": 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.toArray();
```

Expected:

1. A-O1005, total 28.50.
2. A-O1002, total 43.00.

Why projection? The list view does not need full items, payment, or shipping; this reduces network and memory usage. **Never save a partial entity back** as if it contained all fields.

Add `_id` to the sort as a tie-breaker when multiple orders share the same `createdAt`.

Matching index: `ix_tenant_status_time_id`.

---

## 11. Query 3: History of a Single Customer

```javascript
lab.orders.find({
  tenantId: "A",
  "customer.customerId": "A-C01"
})
.sort({ createdAt: -1, _id: -1 })
.toArray();
```

Expected newest-first order:

1. A-O1005.
2. A-O1003.
3. A-O1001.

`customer.displayName` inside the order is a historical snapshot. If the customer's current name changes, older orders do not update automatically; UX chooses between snapshot or current name based on requirements.

Index: `{tenantId:1,"customer.customerId":1,createdAt:-1,_id:-1}`.

---

## 12. Query 4: Time Range

Find tenant A orders from 21/10/2026 to **before** 25/10/2026 in UTC:

```javascript
lab.orders.find({
  tenantId: "A",
  createdAt: {
    $gte: ISODate("2026-10-21T00:00:00Z"),
    $lt: ISODate("2026-10-25T00:00:00Z")
  }
})
.sort({ createdAt: 1, _id: 1 })
.toArray();
```

Expected: A-O1002, A-O1003, A-O1004.

Use a half-open `[from, to)` interval for clear boundaries without relying on `"23:59:59.999"`. For Vietnam business timezones, convert local day boundaries to UTC before querying.

**Index note:** `{tenantId:1,status:1,createdAt:-1}` does not always serve date-only queries efficiently because `status` is missing from the predicate. If date-only queries are a hot path, consider `{tenantId:1,createdAt:-1,_id:-1}` and verify with Explain.

---

## 13. Query 5: Finding Orders Containing a SKU

```javascript
lab.orders.find({
  tenantId: "A",
  "items.sku": "CABLE"
}, {
  _id: 1,
  orderNo: 1,
  items: 1
})
.sort({ createdAt: -1 })
.toArray();
```

Expected ID set: A-O1001, A-O1002, A-O1004, A-O1005.

### 13.1. `$elemMatch` When Matching the Same Element

Find an order with a single line item where `sku="CABLE"` and `quantity>=3`:

```javascript
lab.orders.find({
  tenantId: "A",
  items: {
    $elemMatch: {
      sku: "CABLE",
      quantity: { $gte: NumberInt(3) }
    }
  }
}).toArray();
```

Expected: **A-O1005**.

Two separate conditions `"items.sku":"CABLE"` and `"items.quantity":{$gte:3}` **can match two different elements** within the same array. `$elemMatch` ensures both apply to the same element.

---

## 14. Query 6: Counts and Status Distribution

### 14.1. Fast Count for a Filter

```javascript
lab.orders.countDocuments({
  tenantId: "A",
  status: "PAID"
});
// 2
```

No need to load the full list into Java and call `size()`.

### 14.2. Order Count Distribution by Status

```javascript
lab.orders.aggregate([
  { $match: { tenantId: "A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
]).toArray();
```

Expected for tenant A:

| Status | Count |
| --- | ---: |
| PAID | 2 |
| CANCELLED | 1 |
| PLACED | 1 |
| SHIPPED | 1 |

### 14.3. Distinct Statuses

```javascript
lab.orders.distinct("status", {
  tenantId: "A"
});
```

The list contains the four statuses above, though return order is not a business contract.

---

## 15. Query 7: Revenue by Tenant

**Lab definition:** orders in `PAID` or `SHIPPED` status count toward "paid revenue." This is not automatically how production accounting works when refunds/chargebacks/taxes exist.

### 15.1. Tenant A

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      orders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  }
]).toArray();
```

Expected:

- 3 orders: A-O1002, A-O1003, A-O1005.
- `revenue = NumberDecimal("161.40")`.
- Calculation: 43.00 + 89.90 + 28.50 = 161.40.

### 15.2. All Tenants, Strictly for Authorized Admins

```javascript
lab.orders.aggregate([
  {
    $match: {
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      orders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

| Tenant | Orders | Revenue USD |
| --- | ---: | ---: |
| A | 3 | 161.40 |
| B | 1 | 99.90 |

Total is **261.30**. Normal multi-tenant users must never query global data without explicit authorization.

---

## 16. Query 8: Top Sold SKUs

Use `$unwind` to turn each line item into a pipeline record, then group by SKU:

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      units: { $sum: "$items.quantity" },
      grossLineValue: { $sum: "$items.lineTotal" }
    }
  },
  { $sort: { units: -1, _id: 1 } }
]).toArray();
```

Expected:

| SKU | Units | Gross Line USD |
| --- | ---: | ---: |
| CABLE | 5 | 47.50 |
| HEAD | 1 | 89.90 |
| MOUSE | 1 | 24.00 |

CABLE: A-O1002 has 2, A-O1005 has 3. A-O1001 is still PLACED and A-O1004 is CANCELLED, so they are excluded.

### 16.1. At Very Large Scale

`$unwind` produces many intermediate records. Continuously refreshing dashboards over millions of orders may require pre-aggregation or materialized reports instead of full scans per request. Test correctness against refunds, cancellations, and updates.

---

## 17. Query 9: Revenue by Payment Date

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      status: { $in: ["PAID", "SHIPPED"] },
      "payment.paidAt": { $type: "date" }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$payment.paidAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      revenue: { $sum: "$total" },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

`$dateTrunc` is supported from MongoDB 5.0 onward. Specify the business timezone so payments near 00:00 Vietnam time are not bucketed into the wrong day.

Production accounting revenue must model **payment events/refunds/settlements**; order status is a simple lab proxy, not a financial ledger.

---

## 18. Query 10: `$lookup` Current Customer

The order holds a snapshot customer name; an admin wants to view the current email:

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      _id: "A-O1001"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        cid: "$customer.customerId",
        tid: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            displayName: 1,
            email: 1
          }
        }
      ],
      as: "currentCustomer"
    }
  },
  {
    $project: {
      orderNo: 1,
      customer: 1,
      currentCustomer: 1,
      total: 1
    }
  }
]).toArray();
```

Never join solely by customer ID while omitting `tenantId` if IDs can collide across tenants or security policy requires isolation. Only expose `currentCustomer` on endpoints authorized to view emails.

The snapshot `customer.displayName` and `currentCustomer.displayName` **do not have to match**.

---

## 19. Pagination: skip/limit and Keyset

### 19.1. Offset Paging

```javascript
lab.orders.find({ tenantId: "A" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0)
  .limit(2)
  .toArray();
```

First page: A-O1005, A-O1004.

```javascript
lab.orders.find({ tenantId: "A" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(2)
  .limit(2)
  .toArray();
```

Second page: A-O1003, A-O1002.

### 19.2. Why Not Use Deep Offset Forever?

`skip(100000)` may have to scan through many records. Inserts/deletes during paging can cause a document to appear twice or be skipped.

### 19.3. Keyset Paging

After the first page, the last order is A-O1004 (`2026-10-24T08:00:00Z`). Next query:

```javascript
var lastTime = ISODate("2026-10-24T08:00:00Z");
var lastId = "A-O1004";

lab.orders.find({
  tenantId: "A",
  $or: [
    { createdAt: { $lt: lastTime } },
    {
      createdAt: lastTime,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(2)
.toArray();
```

Expected: A-O1003, A-O1002.

In an API, cursors should be **signed/validated against tenant/filter/sort** so clients cannot tamper with them to access unauthorized data.

### 19.4. Index for tenant + createdAt

You may need:

```javascript
lab.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "ix_tenant_time_id" }
);
```

Do not add it blindly to production without measuring the workload; every index increases write overhead.

---

## 20. Verifying the Validator with Invalid Data

Run the following examples **in the lab**, after seeding data. Use copies and change `_id`/`orderNo` so duplicate errors do not mask validation failures.

### 20.1. Wrong BSON Type for Quantity

```javascript
var badQty = lab.orders.findOne({ _id: "A-O1001" });
badQty._id = "BAD-QTY";
badQty.orderNo = "BAD-QTY";
badQty.items[0].quantity = "2"; // string, not int32

try {
  lab.orders.insertOne(badQty);
  print("Unexpected: invalid document accepted");
} catch (e) {
  print("Expected validation error: " + e.message);
}
```

### 20.2. Total Using Double Instead of Decimal128

```javascript
var badTotal = lab.orders.findOne({ _id: "A-O1001" });
badTotal._id = "BAD-TOTAL";
badTotal.orderNo = "BAD-TOTAL";
badTotal.total = 189.30;

try {
  lab.orders.insertOne(badTotal);
  print("Unexpected: double accepted");
} catch (e) {
  print("Expected decimal type error: " + e.message);
}
```

### 20.3. Missing Required Fields

```javascript
try {
  lab.orders.insertOne({
    _id: "BAD-MISSING",
    tenantId: "A",
    orderNo: "BAD-003"
  });
} catch (e) {
  print("Expected required-fields error: " + e.message);
}
```

### 20.4. Status Outside Enum

```javascript
var badStatus = lab.orders.findOne({ _id: "A-O1001" });
badStatus._id = "BAD-STATUS";
badStatus.orderNo = "BAD-STATUS";
badStatus.status = "UNKNOWN";

try {
  lab.orders.insertOne(badStatus);
} catch (e) {
  print("Expected enum error: " + e.message);
}
```

MongoDB typically reports `DocumentValidationFailure` (code 121), with details varying by version. Never write raw invalid documents containing PII to public logs.

### 20.5. Confirming No BAD Documents Exist

```javascript
lab.orders.countDocuments({ _id: /^BAD-/ });
// 0 if all invalid writes were rejected
```

---

## 21. JSON Schema Limitation: Total Could Have Wrong Arithmetic

Copy:

```javascript
var wrongMath = lab.orders.findOne({ _id: "A-O1001" });
wrongMath._id = "MATH-WRONG";
wrongMath.orderNo = "MATH-WRONG";
wrongMath.total = NumberDecimal("1.00");
```

Even though the amount is wrong, the validator in this lesson will still **accept** this document because `total` is a non-negative Decimal128.

**Do not insert it into the main fixture** if you want to preserve expected revenues.

### 21.1. Checking in the Domain Service

Java pseudo-code:

```java
BigDecimal sum = items.stream()
    .map(item ->
        item.unitPrice()
            .multiply(BigDecimal.valueOf(item.quantity()))
    )
    .reduce(BigDecimal.ZERO, BigDecimal::add);

if (sum.compareTo(order.total()) != 0) {
    throw new IllegalArgumentException("Order total mismatch");
}
```

With taxes/discounts/shipping, formulas and rounding must be defined per business/currency rules.

### 21.2. Auditing Stored Data with Aggregation

```javascript
lab.orders.aggregate([
  {
    $project: {
      total: 1,
      recomputed: {
        $reduce: {
          input: "$items",
          initialValue: NumberDecimal("0"),
          in: {
            $add: ["$$value", "$$this.lineTotal"]
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$total", "$recomputed"] }
    }
  }
]).toArray();
```

With the original 7 orders, expect an **empty array**. This is a resource-intensive data audit on large collections, not an OLTP endpoint to call on every request.

---

## 22. Unique Indexes and Idempotency

### 22.1. Testing Duplicate orderNo

```javascript
var dup = lab.orders.findOne({ _id: "A-O1001" });
dup._id = "A-O-DUP";
// orderNo is still "AO-001" in tenant A.

try {
  lab.orders.insertOne(dup);
  print("Unexpected: duplicate accepted");
} catch (e) {
  print("Expected duplicate error: " + e.code);
}
```

Expected `E11000 duplicate key` due to the `uq_tenant_orderNo` index.

### 22.2. Exists Precheck Is Not Enough

Two concurrent requests can both observe `exists=false` and proceed to insert. Only a unique index serves as the final constraint at the database layer.

Idempotency also requires a business key/request ID, especially when a client retries after a network timeout. On duplicate, the application must determine whether it is a valid retry or a separate request reusing a code, avoiding returning another user's data.

### 22.3. `$setOnInsert` and Upsert

One idempotent creation approach uses `upsert` with `$setOnInsert`, but the filter must be scoped to tenant/business key and `upsertedId`/`matchedCount` must be inspected. Never use an upsert that allows a retry to overwrite an already-placed order.

---

## 23. Updating Status with Filter and Version

**This command alters the baseline.** Run it only after read queries, or reset/reseed when comparing against original expected revenues.

```javascript
var result = lab.orders.updateOne(
  {
    _id: "A-O1001",
    tenantId: "A",
    status: "PLACED",
    version: NumberInt(1)
  },
  {
    $set: {
      status: "PAID",
      payment: {
        method: "CARD",
        paidAt: ISODate("2026-10-27T10:00:00Z")
      },
      updatedAt: ISODate("2026-10-27T10:00:00Z")
    },
    $inc: { version: NumberInt(1) }
  }
);

printjson({
  matched: result.matchedCount,
  modified: result.modifiedCount
});
```

First run expects `matched=1, modified=1`. A second run with `version=1` expects `matched=0`.

- `_id` identifies the order.
- `tenantId` enforces tenant scope.
- `status` blocks transitions from any other status.
- `version` reduces the risk of lost updates.

The validator knows `"PAID"` is valid in the enum, but **does not know** whether `CANCELLED → PAID` is forbidden; the state machine/domain service must enforce the workflow.

---

## 24. Updating Inventory Atomically

Reserve 2 units of HEAD for tenant A if sufficient stock remains:

```javascript
var stockResult = lab.products.updateOne(
  {
    tenantId: "A",
    sku: "HEAD",
    active: true,
    stock: { $gte: NumberInt(2) }
  },
  {
    $inc: { stock: NumberInt(-2) }
  }
);

printjson({
  matched: stockResult.matchedCount,
  modified: stockResult.modifiedCount
});
```

When stock is below 2, the update matches nothing. The predicate and `$inc` are atomic on a **single product document**.

**Do not perform a non-atomic two-step read-check-write**: two clients can both read `stock=1` and both decide to sell.

### 24.1. Single-Document Atomicity Limitation

An order with multiple SKUs requires deducting multiple product documents and inserting an order. Those are multiple writes and are not automatically atomic together. This requires a transaction on a supported MongoDB topology, or a reservation/saga/compensation strategy when eventual consistency is acceptable.

---

## 25. Transaction: Deducting Stock and Creating an Order

The following `mongosh` snippet **works only on a replica set or sharded deployment supporting transactions**, not on standalone MongoDB when multi-document atomicity is required.

Run in the lab on the original dataset:

```javascript
var session = db.getMongo().startSession();
var txDb = session.getDatabase("order_design_lab");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  var stock = txDb.products.updateOne(
    {
      tenantId: "A",
      sku: "HEAD",
      active: true,
      stock: { $gte: NumberInt(1) }
    },
    { $inc: { stock: NumberInt(-1) } }
  );

  if (stock.modifiedCount !== 1) {
    throw new Error("Insufficient stock");
  }

  var now = new Date();

  txDb.orders.insertOne({
    _id: "A-O1006",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-006",
    customer: {
      customerId: "A-C01",
      displayName: "Ngoc"
    },
    items: [
      {
        sku: "HEAD",
        name: "Headphones",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("89.90"),
        lineTotal: NumberDecimal("89.90")
      }
    ],
    total: NumberDecimal("89.90"),
    currency: "USD",
    status: "PLACED",
    createdAt: now,
    updatedAt: now,
    shipping: { city: "Hanoi" }
  });

  session.commitTransaction();
  print("Transaction committed");
} catch (e) {
  try {
    session.abortTransaction();
  } catch (abortError) {
    print("Transaction outcome needs investigation");
  }
  print("Transaction failed: " + e.message);
} finally {
  session.endSession();
}
```

### 25.1. Why Does `modifiedCount` Matter?

If the stock update matches nothing due to insufficient inventory, it does not automatically throw an exception. If the code proceeds to insert the order, it creates an unreserved order. Therefore, `modifiedCount` must be checked.

### 25.2. Transactions Do Not Cover External Payments

A MongoDB transaction does not encompass an external payment gateway. External payments require idempotent external calls, outbox/saga patterns, and handling retries/ambiguous commit outcomes according to business policy.

### 25.3. Do Not Re-run Blindly

Re-running with the same `AO-006` may throw a duplicate key error. Design retry/idempotency properly and never deduct stock a second time.

---

## 26. Validation Modes and `collMod`

### 26.1. `validationAction`

- `error`: invalid documents are rejected.
- `warn`: logs a warning while still allowing the write per MongoDB semantics.
- Certain MongoDB releases/editions also provide `errorAndLog`; check documentation before using.

### 26.2. `validationLevel`

- `strict`: validates all inserts and updates within validation scope.
- `moderate`: supports legacy migrations with special semantics for existing invalid documents.

Never turn on `warn`/`moderate` in production merely to hide schema errors.

### 26.3. Testing in the Lab

```javascript
lab.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "warn"
});
```

Restore blocking mode:

```javascript
lab.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
});
```

These two commands keep the existing validator and only change the policy. To alter the schema when adding fields or statuses, `collMod` needs a compatible new validator and a migration plan.

### 26.4. `bypassDocumentValidation` Is Not a Long-Term Solution

Drivers may support bypassing validation with sufficient privileges, which removes a layer of protection. Only use it in controlled migrations, logging exceptions and auditing changes.

---

## 27. `explain("executionStats")`: Is the Index Used?

### 27.1. Lookup by Order Number

```javascript
lab.orders.find({
  tenantId: "A",
  orderNo: "AO-001"
}).explain("executionStats");
```

### 27.2. PAID List

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.explain("executionStats");
```

### 27.3. Customer History

```javascript
lab.orders.find({
  tenantId: "A",
  "customer.customerId": "A-C01"
})
.sort({ createdAt: -1, _id: -1 })
.explain("executionStats");
```

### 27.4. SKU

```javascript
lab.orders.find({
  tenantId: "A",
  "items.sku": "CABLE"
}).explain("executionStats");
```

### 27.5. Reading the Output

| Metric/Stage | Meaning |
| --- | --- |
| `winningPlan` | Execution plan chosen by the optimizer |
| `IXSCAN` | Index scan used |
| `COLLSCAN` | Full collection scan |
| `FETCH` | Needs to fetch document after index lookup |
| `SORT` | Dedicated in-memory sort stage present |
| `nReturned` | Number of records returned |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `executionTimeMillis` | Duration of a single Explain run |

**Do not assert IXSCAN strictly on 7 documents.** The planner may choose COLLSCAN because the dataset is tiny. Index existence (`getIndexes`) and index usage (`explain`) are two separate pieces of evidence.

### 27.6. Query Targeting and Overhead

For example, a query scanning 200,000 documents to return 20 orders has a 10,000 docs examined/result ratio—warranting investigation of query, index, and projection.

Also measure write overhead because every additional index must be updated on inserts/updates, especially multikey indexes on `items`.

---

## 28. Auditing BSON Types and Legacy Data

### 28.1. `$type` Audit

```javascript
lab.orders.aggregate([
  {
    $project: {
      orderNo: 1,
      totalType: { $type: "$total" },
      createdType: { $type: "$createdAt" },
      itemsType: { $type: "$items" },
      versionType: { $type: "$version" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

Expect `decimal`, `date`, `array`, and `int` types across the fixture.

### 28.2. Finding Missing Required Fields

```javascript
lab.orders.find({
  $or: [
    { tenantId: { $exists: false } },
    { orderNo: { $exists: false } },
    { items: { $exists: false } },
    { total: { $exists: false } }
  ]
}).toArray();
```

Expect empty results on a valid fixture. Data written **before the validator took effect** or with bypass privileges may contain different legacy fields/types.

### 28.3. Null vs. Missing

```javascript
lab.orders.find({ note: null });
```

MongoDB equality with `null` typically matches both documents missing the `note` field and documents with explicit `null`. Use:

```javascript
lab.orders.find({ note: { $exists: false } });

lab.orders.find({ note: { $type: "null" } });
```

when business logic must distinguish them.

---

## 29. Multi-Tenancy: Do Not Confuse Filters with Authorization

A validator requiring `tenantId` to be a string **does not mean** a user is authorized to read that tenant. The service must authenticate the principal and derive `tenantId` from verified permissions.

### 29.1. Incorrect OR Can Leak Data

Wrong:

```javascript
{
  $or: [
    { tenantId: "A", status: "PAID" },
    { total: { $gte: NumberDecimal("100") } }
  ]
}
```

The second branch can match tenant B's data.

Right:

```javascript
{
  tenantId: "A",
  $or: [
    { status: "PAID" },
    { total: { $gte: NumberDecimal("100") } }
  ]
}
```

### 29.2. Tenant Scope Is Also Needed on Writes and Lookups

Include tenant in filters for `updateOne`, `deleteOne`, queries, aggregations, and `$lookup`. Do not rely on tenant-prefixed ID conventions as your sole authorization mechanism.

### 29.3. API Data Minimization

Do not return full shipping/payment/email fields from list endpoints. Projections and DTOs minimize payloads; authorization determines who can see which fields.

---

## 30. Java/Spring Data MongoDB Mapping

An entity can be declared as:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public class OrderEntity {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String orderNo;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal total;

    private String status;
    private Instant createdAt;
    private Instant updatedAt;

    private Integer version;
    private Integer schemaVersion;

    private CustomerSnapshot customer;
    private List<LineItem> items;

    // Shipping/payment fields and constructors,
    // getters/setters added per actual model.
}
```

**Important:** embedded `LineItem.unitPrice` and `LineItem.lineTotal` also require Decimal128 mapping. Because of `additionalProperties:false` in the validator, verify `_class` at both root and nested types from Spring Data; custom conversions/type mappers must be schema-compatible.

### 30.1. Repository Methods

```java
public interface OrderRepository
        extends MongoRepository<OrderEntity, String> {

    Optional<OrderEntity> findByTenantIdAndOrderNo(
        String tenantId,
        String orderNo
    );

    Page<OrderEntity> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    List<OrderEntity>
    findByTenantIdAndCustomer_CustomerIdOrderByCreatedAtDesc(
        String tenantId,
        String customerId
    );
}
```

Embedded classes/properties and imports must be completely defined according to the project.

### 30.2. `@Version` and Optimistic Locking

Spring Data provides `@Version`, but do not mix manual raw `$inc` version bumps with repository `save()` without understanding the semantics. Use an acknowledged write concern and write integration tests for stale updates.

### 30.3. `Page` Can Trigger an Extra Count Query

If the UI only needs "Load more," `Slice` or keyset pagination can avoid the total count query. On large collections, avoid unbounded `findAll()`.

### 30.4. Reading Raw BSON in Integration Tests

`MongoTemplate.findById` returns a mapped object but can hide the underlying BSON type. To verify Decimal128:

```java
var raw = mongoTemplate.getDb()
    .getCollection("orders")
    .find(new Document("_id", "A-O1001"))
    .first();

assertThat(raw.get("total"))
    .isInstanceOf(org.bson.types.Decimal128.class);
```

This is an example inside a test with `mongoTemplate`, AssertJ, and appropriate `org.bson.Document` imports. Mock repositories do not verify `$jsonSchema`, unique indexes, or raw BSON.

---

## 31. Sound Order Placement Business Flow

```text
POST /orders
     |
     v
Authenticate user -> determine tenantId
     |
     v
Validate request, item limit, quantity
     |
     v
Read catalog by tenantId + SKU
     |
     v
Check active, stock, currency
     |
     v
Calculate price snapshots and line totals with BigDecimal
     |
     v
Generate idempotency key/orderNo
     |
     v
Transaction / reservation workflow
  - atomic stock decrement
  - insert order
     |
     v
Return order ID and status
```

Never trust client-submitted `unitPrice=0.01` or `total=0.01` by bypassing pricing policy. **The server calculates the total** based on the catalog and valid negotiated pricing.

### 31.1. External Payment Gateways

A MongoDB transaction does not make an external payment gateway atomic. Use idempotent payment operations, event/outbox patterns, and reconciliation according to the project design.

### 31.2. Sold Data Requires Snapshots

Updating catalog price/name must never alter order history. This is why line items embed `sku`, `name`, and `unitPrice`.

---

## 32. Schema v2 Upgrade Plan

Business wants to add `discount`, `refunds`, status `RETURNED`, and multiple currencies.

**Expand–migrate–contract** workflow:

1. Measure v1 data, BSON types, and document counts.
2. Design v2 with clear fields/types/defaults.
3. Deploy code capable of reading both v1 and v2.
4. Relax the validator with a compatibility plan; do not immediately invalidate all legacy documents.
5. Deploy v2 writers.
6. Backfill in batches with checkpoints and idempotency.
7. Verify monetary calculations and query outputs.
8. Create/rebuild indexes for the new workload.
9. Tighten the validator once migration completes.
10. Monitor validation failures, latency, and rollback readiness.

`schemaVersion` does not migrate data automatically. Never run `collMod` in production as an unmonitored experiment.

---

## 33. Test Matrix

| Contract | Condition | Expected |
| --- | --- | --- |
| Fixtures | Baseline | 7 orders |
| Tenants | A/B | 5 / 2 |
| OrderNo | A/AO-001 | A-O1001 |
| PAID list | A | A-O1005, A-O1002 |
| Customer history | A-C01 | A-O1005,1003,1001 |
| Date range | A, 21/10–25/10 UTC | A-O1002,1003,1004 |
| SKU CABLE | A | A-O1001,1002,1004,1005 |
| `$elemMatch` qty≥3 | A, CABLE | A-O1005 |
| Completed orders | A PAID+SHIPPED | 3 |
| Revenue | A | 161.40 |
| Revenue | B | 99.90 |
| Units CABLE | A completed | 5 |
| Quantity string | BAD-QTY | Validation failure |
| Total double | BAD-TOTAL | Validation failure |
| Missing fields | BAD-MISSING | Validation failure |
| Status UNKNOWN | BAD-STATUS | Validation failure |
| Duplicate orderNo | A/AO-001 | Duplicate key |
| Versioned update | A-O1001 version 1 | First update 1, retry 0 |
| Insufficient stock | stock below quantity | matchedCount 0 |
| Cross-tenant read | User A/record B | Forbidden/no result |
| Index definitions | Catalog | Correct key order/options |
| Explain | List/detail queries | Plan/scan metrics recorded |

### 33.1. Why Test Against Real MongoDB?

Mock repositories do not execute BSON conversion, `$jsonSchema`, unique indexes, atomic updates, or transactions. Use integration tests on a MongoDB test instance or Testcontainers/MongoDB replica set when testing transactions.

### 33.2. Do Not Hard-Assert IXSCAN on 7 Orders

On a tiny dataset, the optimizer may legitimately choose COLLSCAN. Tests must separate correctness, index existence, and performance benchmarks on a sufficiently large corpus.

---

## 34. Common Errors

| Error | Cause | Resolution |
| --- | --- | --- |
| Insert fails with code 121 | Wrong BSON type/required/enum | Inspect validator, raw BSON, fix data |
| `additionalProperties:false` rejects `_id` | Forgot `_id` in properties | Allow `_id` |
| Java insert rejected due to `_class` | Type mapper adds metadata | Align mapping/validator |
| BigDecimal becomes double | Wrong converter or passed via JS Number | Decimal128 mapping, raw `$type` check |
| Duplicate `orderNo` | Missing/hit unique index | Unique index and idempotency |
| Wrong total passes validation | Schema lacks cross-field math check | Domain validation and audits |
| Negative stock/race condition | Non-atomic read-check-write | Atomic predicate + `$inc` |
| Order created without deducting stock | Non-atomic multi-write | Transaction/reservation workflow |
| Invalid status jump | Enum unaware of state machine | Guarded update + service |
| Tenant A reads B | Missing authorization/tenant scope | Principal-derived tenant + tests |
| Indexed query still slow | Index mismatches filter/sort, huge data | Explain, selectivity, projection |
| `findAll()` returns too many docs | No pagination | Limit/keyset/streaming |
| `$lookup` leaks email | No permission/tenant scope | Tenant-scoped join, auth |
| Revenue bucketed to wrong day | Grouped by UTC instead of business TZ | `$dateTrunc` timezone |
| New schema breaks legacy updates | Tightened `required` too early | Expand–migrate–contract |
| Mock tests pass but writes fail | Mocks don't run the database | Integration tests |

---

## 35. Practice Exercises

### Exercise 1 — Embed vs. Reference

Why are line items embedded in the order while the product catalog is in a separate collection? State two benefits and two limitations.

### Exercise 2 — Historical Price

Tenant A's catalog HEAD price increases from 89.90 → 95.00. Does `A-O1001.items[0].unitPrice` change?

**Answer:** No; it is a snapshot.

### Exercise 3 — Decimal128

Why use `NumberDecimal("19.99")` instead of JavaScript number `19.99` when storing money?

### Exercise 4 — BSON Date

An order has a UTC timestamp. How do you filter for "yesterday in Vietnam" without getting the day boundary wrong?

### Exercise 5 — Required

List five required fields of `orders` and explain why each is required.

### Exercise 6 — `additionalProperties`

What happens if a validator specifies `additionalProperties:false` without declaring `_id`?

### Exercise 7 — `_class`

Why might Spring Data be blocked by the validator even when the Java object is valid?

### Exercise 8 — Item Count

How do you reject `items:[]` and an `items` array with 21 elements?

**Answer:** `minItems:1` and `maxItems:20`.

### Exercise 9 — Quantity

Is a string quantity `"2"` valid against `bsonType:"int"`?

**Answer:** No.

### Exercise 10 — Status Enum

Create a document with status `"REFUNDED"` and explain the validation failure.

### Exercise 11 — Math Invariant

Why might the lab validator accept `total:NumberDecimal("1")` even though the items sum to 189.30?

### Exercise 12 — Unique Business Key

Write an index preventing duplicate `(tenantId,orderNo)`.

### Exercise 13 — Race Condition

Why does `existsByTenantIdAndOrderNo` fail to protect uniqueness under concurrent requests?

### Exercise 14 — Order Lookup

Write a query to retrieve tenant A, orderNo `"AO-002"`.

### Exercise 15 — Status List

Find PAID orders for tenant A, sorted `createdAt DESC, _id DESC`, limit 20; what are the expected order IDs?

**Answer:** A-O1005, A-O1002.

### Exercise 16 — Customer History

Find tenant A orders for customer A-C01, newest first.

### Exercise 17 — Time Range

Use `$gte`/`$lt` to fetch tenant A orders between 21/10–25/10 UTC.

### Exercise 18 — Array SKU

Find tenant A orders containing SKU CABLE.

### Exercise 19 — `$elemMatch`

Find the same array element having CABLE and quantity >=3. Explain how this differs from two independent dot-notation conditions.

### Exercise 20 — Count

How many PAID orders does tenant A have?

**Answer:** 2.

### Exercise 21 — Revenue

Calculate tenant A's revenue for PAID/SHIPPED statuses.

**Answer:** 161.40 USD.

### Exercise 22 — Global Reporting

Calculate A/B revenue and explain why a tenant user must not run unauthorized global aggregations.

### Exercise 23 — Top SKU

Which SKU has the highest units sold among tenant A's paid orders?

**Answer:** CABLE, 5 units.

### Exercise 24 — `$lookup`

Write a `$lookup` to fetch the current customer, matching both customer ID and `tenantId`.

### Exercise 25 — Projection

Why should a list endpoint avoid loading `items`, shipping, and payment?

### Exercise 26 — Keyset Pagination

Write a query to fetch the next page after A-O1004 sorted descending by `(createdAt,_id)`.

### Exercise 27 — Stock

If stock is 1 and a customer requests 2, what does an atomic update with predicate `$gte:2` return?

**Answer:** `matchedCount=0`.

### Exercise 28 — Version

Why should a status update filter on both the old status and the old version?

### Exercise 29 — Transaction

If the stock update succeeds but the order insert fails with a duplicate key, what must the transaction do?

### Exercise 30 — `collMod`

Write the commands to switch the validation action to `warn` in the lab and then restore `error`.

### Exercise 31 — Explain

Inspect `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and the winning plan for an `orderNo` lookup.

### Exercise 32 — Index Prefix

Why might the index `(tenantId,status,createdAt)` be suboptimal for date-only queries?

### Exercise 33 — Tiny Dataset

Why might MongoDB choose COLLSCAN even when an index exists on 7 orders?

### Exercise 34 — Tenant OR

Move the tenant filter outside the two `$or` branches to prevent data leaks.

### Exercise 35 — Spring Data

Choose the annotation so Java `BigDecimal total` is stored as BSON Decimal128 and verify it with raw `Document`.

### Exercise 36 — Schema Drift

Legacy products stored price as double, while the new schema requires decimal. Plan a safe data migration.

### Exercise 37 — Partial Entity

Why shouldn't you load a partial projection missing fields and then call repository `save()`?

### Exercise 38 — Idempotency

Design a mechanism to avoid deducting stock twice when a client retries after missing the commit response.

### Exercise 39 — Large-Scale Dashboard

The SKU report runs very slowly over 100 million orders. Outline strategies for indexes, benchmarking, and pre-aggregation.

### Exercise 40 — Final Project

Design four APIs: `POST /orders`, `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/pay`. Deliver a full report: document model, validators, unique/indexes, tenant authorization, state machine, transaction/idempotency, query matrix, integration tests, Explain, and migration plan.

---

## 36. Pre-Production Checklist

### Data Model

- [ ] Embed/reference chosen according to query patterns.
- [ ] Line-item price/name snapshots are an explicit contract.
- [ ] Arrays are bounded; BSON documents stay under 16 MiB.
- [ ] Money uses Decimal128/BigDecimal with clear currency/rounding.
- [ ] Dates use BSON Date with standardized timezone boundaries.
- [ ] Schema version and optimistic version serve distinct purposes.

### Validation

- [ ] `$jsonSchema` is present in collection options.
- [ ] Required fields, enums, nested objects, and int/decimal/date types are validated.
- [ ] `_id`/`_class` align with `additionalProperties`.
- [ ] Domain service recomputes totals rather than trusting clients.
- [ ] State transitions/referential integrity are checked outside the validator.
- [ ] A migration plan exists before tightening the schema.

### Indexes/Queries

- [ ] Unique `(tenantId,orderNo)`, `(tenantId,sku)`, `(tenantId,email)`.
- [ ] Suitable indexes for status/time lists and customer history.
- [ ] Multikey indexes created only when required by the workload.
- [ ] Pagination/sorts include a tie-breaker.
- [ ] List endpoints use projections.
- [ ] Explain output reviewed to verify query plans.
- [ ] Index write overhead measured.

### Concurrency/Security

- [ ] Tenant scope derived from authenticated principal.
- [ ] Queries, updates, deletes, and lookups enforce tenant guards.
- [ ] Unique violations/idempotency handled cleanly.
- [ ] Stock updates use atomic predicates.
- [ ] Multi-document operations use transactions or compensation.
- [ ] Payments outside MongoDB transactions have dedicated workflows.
- [ ] Raw PII/payment details are never exposed in APIs/logs.

### Operations

- [ ] Integration tests run against real MongoDB.
- [ ] Backups, migrations, rollbacks, and monitoring are in place.
- [ ] Lab `drop`/`collMod` commands are never run in production.
- [ ] p95/p99 latency, CPU/IOPS, pool waits, and slow queries measured.
- [ ] Audit/reconciliation exists for payments/refunds/cancellations.
- [ ] Production performance conclusions are not drawn from a 7-order dataset.

---

## 37. Summary

A good MongoDB document design must serve **real business queries**, not just look like pretty JSON:

1. **Embed** information frequently read with the order and historical prices; **reference** current products/customers.
2. Use **explicit BSON types**: Decimal128 for money, Date for timestamps, and int for quantity/stock.
3. Use **`$jsonSchema` validators** to enforce shape, required fields, enums, nested arrays, and types.
4. Do not mistake the validator for all invariants: **total calculation, state transitions, authorization, and referential integrity** belong in the domain service.
5. Use **unique indexes** to protect business keys under concurrent requests.
6. Design **compound indexes matching filters and sorts**, rather than adding indexes arbitrarily.
7. Write **tenant-scoped OLTP queries** with projections and stable pagination.
8. Use aggregation for revenue/SKU reporting with transparent business definitions.
9. Use **atomic conditional updates or transactions** to maintain stock/order consistency.
10. Inspect **raw BSON, the index catalog, and Explain**, write integration tests, and prepare schema migrations.

**Expected outcome:** a set of collections, validators, sample data, queries, and test contracts that are reproducible, verifiable, and safe to evolve into a real-world system.

### Official MongoDB Documentation

- [MongoDB Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — access-pattern-driven design.
- [Embedded Data vs References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/) — embed/reference trade-offs.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — validators and database contracts.
- [Specify JSON Schema](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `$jsonSchema` examples.
- [JSON Schema Operator](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/) — BSON types/keywords.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — `collMod` and migrations.
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Decimal128/Date/int.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — indexes and operational trade-offs.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — key order.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — arrays.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness.
- [Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query/) — filters, `$elemMatch`, `$exists`, `$type`.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — group/unwind/lookup/dateTrunc.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — execution statistics.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document behavior.
- [Spring Data MongoDB Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — Java/BSON mapping.
- [Spring Data Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — repositories and paging.
