# Setting Up the Environment and Sales Application Dataset with MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Integrated Practice  
> **Lesson:** Setting up the environment and sales application dataset

## 1. Context and Target Outcomes

We will build a MongoDB practice environment for a small sales application, including customers, product categories, products, inventory, orders, payments, and an outbox collection to prepare for transaction or event-processing exercises.

This is a **practice foundation setup** lesson, not a complete website. The final outcome is a database with sample data, essential indexes, verification queries, and a Java connection that can be used for subsequent CRUD, aggregation, transaction, and performance exercises.

### 1.1. What you will have after this lesson

- A dedicated MongoDB instance running for the lab, with a single-node replica set recommended when you want to try transactions and change streams.
- Database `sales_lab` with seven collections: `categories`, `customers`, `products`, `inventory`, `orders`, `payments`, and `outbox`.
- **Synthetic data containing no real customer information**, seeded with fixed IDs.
- Prices stored as **integer VND** in BSON Int64 format, without using floating-point numbers to represent monetary amounts in the examples.
- Timestamps using BSON Date in UTC.
- Indexes suited for common queries, including unique indexes for email, request ID, and payment/order association.
- Scenarios to verify counts, data types, references, query plans, and the Java connection.
- A checkout transaction example that decrements inventory, creates an order, and writes an outbox record in a single commit.
- Directions for extending into integration tests, APIs, and revenue reports.

### 1.2. Scope and Limitations

The environment is designed for **development on a personal machine**. Docker MongoDB in the example only publishes its port to `127.0.0.1` on the host machine, has authentication disabled, and **must not be used as-is on a production machine or a machine accessible by others**.

The seeded order data represents **simulated history**; inventory is an independent snapshot for lab exercises. Do not deduce:

```text
inventory.available
  = stock received - total quantity of the 120 simulated orders
```

because the seed script does not model an inbound/outbound stock ledger from the beginning. When testing transactions later, we start from the current snapshot.

### 1.3. Target Diagram

```text
                      sales_lab
                         │
    ┌────────────────────┼─────────────────────┐
    │                    │                     │
 categories           customers             products
    │                    │                     │
    └── categoryId ◄─────┼─────────────────────┤
                         │                     │
                  customerId                 sku/_id
                         │                     │
                         ▼                     ▼
                       orders                inventory
                         │
                  embedded items[]
                         │
                         ├───────► payments
                         │           orderId
                         │
                         └───────► outbox
                                     orderId
```

MongoDB does not automatically enforce foreign-key constraints like an RDBMS. The `customerId`, `categoryId`, `sku`, and `orderId` strings are **application-level references**; consistency must be maintained through service logic, transactions where needed, and data testing.

---

## 2. Data Architecture: Embedding or Referencing?

The application has several relationships:

- One category has many products.
- One customer has many orders.
- One order has many line items.
- One product has one current inventory record for the demo.
- One order has one payment record in the lab, though a real system may have multiple payment attempts.
- One order can produce one or more outbox events.

### 2.1. Decisions for the Lab

| Collection | `_id` | Key Attributes | Relationships |
|---|---|---|---|
| `categories` | `CAT-01` | code, name | Referenced by products |
| `customers` | `CUS-001` | fullName, email, tier | Referenced by orders |
| `products` | `SKU-001` | categoryId, name, unitPriceVnd, active | Inventory and order items use SKU |
| `inventory` | `SKU-001` | available, reserved, updatedAt | Same key as product |
| `orders` | `ORD-0001` | requestId, customerId, items, totalVnd, status | Embeds item snapshots |
| `payments` | `PAY-0001` | orderId, amountVnd, method, status | References order |
| `outbox` | `EVT-...` | eventType, aggregateId, payload, processed | Event emitted after commit |

### 2.2. Why embed items in orders?

An order line item needs a snapshot of the **name and price at the time of purchase**. If a product's price changes tomorrow, the order history must still record the old price.

Example:

```json
{
  "_id": "ORD-0001",
  "customerId": "CUS-002",
  "items": [
    {
      "sku": "SKU-001",
      "name": "Sample Product 001",
      "quantity": 2,
      "unitPriceVnd": {"$numberLong": "80000"},
      "lineTotalVnd": {"$numberLong": "160000"}
    }
  ],
  "totalVnd": {"$numberLong": "160000"}
}
```

`items[]` are embedded because they are typically accessed and updated together with the order, with a bounded size in normal sales transactions. You should not embed the entire order history into a customer document because the array would grow unboundedly.

### 2.3. Why separate inventory from products?

This creates a clear transaction practice scenario: during checkout, inventory must be updated and the order created in the same commit. A real model could place stock directly inside the product document if the access patterns and invariants fit; the lab choice is intended to illustrate multi-collection operations.

### 2.4. Why separate payment?

Payments have different state lifecycles and access permissions from orders. Production systems usually require payment attempts, gateway IDs, and reconciliation; the example here simplifies to one payment per PAID/SHIPPED order, storing no card numbers, CVVs, or sensitive data.

---

## 3. Tools and Prerequisites

### 3.1. Software

Required:

- Docker Engine or Docker Desktop capable of running containers.
- Terminal: PowerShell, Command Prompt, or bash.
- `mongosh` via the Docker container (host installation is not required).
- Java 17+ and Maven/Gradle if doing the Java exercises.
- Optional IDE.
- Free disk space for the MongoDB image, volume, and test data.

### 3.2. Version

Example commands use the image:

```text
mongo:8.0
```

This is a **major-version tag for the learning environment**, not a claim of being the latest version. If a project requires strict reproducibility, pin the image patch release/digest and driver version. Check MongoDB Server/Java Driver compatibility before running in a real stack.

### 3.3. Checking Docker

```bash
docker version
docker info
```

If Docker is not running, start Docker Desktop/daemon and try again. If port 27017 is already used by another MongoDB instance, use a different host port and update the URI accordingly.

### 3.4. No Google Cloud or MongoDB Atlas Required

A local lab is sufficient for most exercises. If you cannot run Docker, you can use a MongoDB development deployment/Atlas sandbox that you own and have permission to create databases/collections in, but you must replace the URI and restrict permissions appropriately.

---

## 4. Running MongoDB with Docker

### 4.1. Command to Start a Local Replica Set

Use a terminal on the host machine:

```bash
docker run -d --name sales-mongo \
  -p 127.0.0.1:27017:27017 \
  -v sales-mongo-data:/data/db \
  mongo:8.0 \
  --replSet rs0 --bind_ip_all
```

On Windows PowerShell 5.1, to avoid bash line-continuation characters, enter it on **one line**:

```powershell
docker run -d --name sales-mongo -p 127.0.0.1:27017:27017 -v sales-mongo-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all
```

Explanation:

| Component | Meaning |
|---|---|
| `--name sales-mongo` | Container name |
| `-p 127.0.0.1:27017:27017` | Publish port only on host localhost |
| `-v sales-mongo-data:/data/db` | Named volume to persist data across container restarts |
| `mongo:8.0` | MongoDB Docker image |
| `--replSet rs0` | Enables replica set initialization |
| `--bind_ip_all` | Mongod listens on all interfaces inside the container |

**Security note:** Even though the host port only binds to loopback, this is still a lab configuration with **authentication disabled**. Do not use it on untrusted hosts or share the Docker socket/volume with others; production requires auth, TLS, network policy, RBAC, backups, and a multi-node replica set configuration.

### 4.2. If Port 27017 Is Busy

You can map host port 27018:

```powershell
docker run -d --name sales-mongo -p 127.0.0.1:27018:27017 -v sales-mongo-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all
```

However, the replica set member will advertise host `localhost:27017` if configured as in the next step. With a **different host-port mapping**, connection string discovery via the replica set can encounter a mismatch. For simplicity, the lab recommends using a free host port 27017; if you must change the port, configure the replica set host names/port mapping accordingly or use `directConnection=true` for development under appropriate conditions. Do not blindly copy the example URI.

### 4.3. Checking the Container

```bash
docker ps --filter name=sales-mongo
docker logs --tail 30 sales-mongo
```

A short natural startup delay may be needed before `mongosh` can connect. There is no need to write an infinite sleep; if an error occurs, check logs/port/volume.

---

## 5. Initializing a Single-Node Replica Set

### 5.1. Opening mongosh Inside the Container

```bash
docker exec -it sales-mongo mongosh
```

At the mongosh prompt, run:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

This command should only be run **once for a new replica set**; do not run it again on an already-configured replica set.

### 5.2. Confirming PRIMARY

```javascript
rs.status();
db.adminCommand({ hello: 1 });
```

Wait until the member becomes PRIMARY:

```javascript
db.adminCommand({ hello: 1 }).isWritablePrimary;
```

The value `true` confirms the member can accept writes in its current state.

### 5.3. Why Is a Replica Set Needed?

MongoDB multi-document transactions and change streams have topology requirements and are not fully supported on a standalone `mongod`. A single-node replica set allows practicing many features, but **provides no failover capability** and is not equivalent to a production multi-node replica set.

### 5.4. Limitations of the localhost Hostname

In this example, the replica set member is `localhost:27017`, which works for clients running **on the same host machine** and `mongosh` inside the container itself.

If a Java app runs in **another container**, `localhost` inside that container does **not** point to MongoDB. When moving to multi-service Docker Compose or a cluster with other nodes, you must use valid DNS/network hostnames, along with matching MongoDB replica set member configuration and appropriate TLS/security.

---

## 6. Connection URI and Initial Verification

### 6.1. URI from the Host

```text
mongodb://127.0.0.1:27017/?replicaSet=rs0
```

If the MongoDB server advertises member hostname `localhost:27017`, the host machine must resolve that hostname to the right instance. In a default local environment, this condition is normally satisfied.

### 6.2. Verifying with mongosh from the Container

```bash
docker exec -it sales-mongo mongosh
```

In mongosh:

```javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ hello: 1 });
rs.status();
```

### 6.3. Do Not Hardcode Production URIs in Source Code

In Java:

```java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is missing");
}
```

Credential URIs must live in configuration/secrets, never committed to Git or pasted into documentation.

---

## 7. Schema and ID Conventions of the Dataset

To make seeding code and queries easy to follow, the lab uses **prefixed String IDs**:

| Collection | Example ID |
|---|---|
| categories | `CAT-01` |
| customers | `CUS-001` |
| products | `SKU-001` |
| inventory | `SKU-001` |
| orders | `ORD-0001` |
| payments | `PAY-0001` |
| outbox | `EVT-ORD-DEMO-001` |

**Do not convert these IDs to ObjectId.** The BSON String `"SKU-001"` is completely different from an ObjectId; queries must use the same type. In another application, using ObjectId or UUID might be more appropriate, but it must be consistent.

### 7.1. Key BSON Types

- `unitPriceVnd`, `lineTotalVnd`, `totalVnd`, `amountVnd`: BSON Int64 (via `NumberLong`).
- `quantity`, `available`, `reserved`: small integers, encoded by mongosh using the appropriate numeric BSON type.
- `createdAt`, `updatedAt`, `paidAt`: BSON Date.
- `active`, `processed`: boolean.
- `status`, `tier`, `method`: String with a defined set of values.
- `items[]`: array of embedded documents.

### 7.2. Why Use Integer VND?

For example, ₫159,000 can be stored as:

```javascript
unitPriceVnd: NumberLong("159000")
```

Do not casually use `159000.00` as a floating-point number when business logic requires exact amounts. You must standardize the money unit and overflow policy; in Java practice, you can use `long` for VND minor units or `BigDecimal/Decimal128` when decimals are needed.

### 7.3. Synthetic Data and Fixed Dates

All seeded `createdAt` values start from:

```text
2026-01-01T00:00:00Z
```

Fixed dates keep queries, assertions, and aggregations reproducible. Do not use `new Date()` for seeding if you want every test run to produce the same expected result.

---

## 8. Detailed Data Model for Categories and Products

### 8.1. Category Document

```javascript
{
  _id: "CAT-01",
  code: "ELECTRONICS",
  name: "Electronics",
  createdAt: ISODate("2026-01-01T00:00:00Z")
}
```

### 8.2. Product Document

```javascript
{
  _id: "SKU-001",
  categoryId: "CAT-01",
  name: "Sample Product 001",
  description: "Practice item 001",
  unitPriceVnd: NumberLong("80000"),
  active: true,
  tags: ["demo", "online"],
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  updatedAt: ISODate("2026-01-01T00:00:00Z")
}
```

### 8.3. Why Not Embed the Entire Category in Product?

A category is an entity shared across many products, and its name/attributes can change. The lab uses a `categoryId` reference to demonstrate lookups and consistency management. For queries displaying category details, you can use aggregation `$lookup` or application caching.

### 8.4. Product Price and Order Item Price Have Different Responsibilities

- `products.unitPriceVnd`: the **current** price.
- `orders.items[].unitPriceVnd`: the snapshot price **when the order was placed**.

Do not automatically update historical orders when an admin edits a product price.

---

## 9. Data Model for Customer and Inventory

### 9.1. Customer Document

```javascript
{
  _id: "CUS-001",
  fullName: "Sample Customer 001",
  email: "customer001@example.test",
  tier: "STANDARD",
  active: true,
  createdAt: ISODate("2026-01-01T00:00:00Z")
}
```

The `example.test` domain is strictly for synthetic data; do not send real emails.

### 9.2. Inventory Document

```javascript
{
  _id: "SKU-001",
  available: 24,
  reserved: 0,
  updatedAt: ISODate("2026-01-01T00:00:00Z")
}
```

### 9.3. Inventory Invariants

For every SKU:

```text
available >= 0
reserved >= 0
```

During checkout:

```javascript
db.inventory.updateOne(
  { _id: "SKU-001", available: { $gte: 2 } },
  {
    $inc: { available: -2 },
    $currentDate: { updatedAt: true }
  }
);
```

This is an atomic conditional update on a **single document**. However, if you also need to create an order in another collection, use a transaction so the steps commit together.

### 9.4. Not Simulating an Inventory Ledger

This seed dataset has no stock movements and does not compute `available` from historical orders. If you need to audit stock quantities, extend the model with a `stockMovements` collection or event ledger and design invariants/reconciliation.

---

## 10. Data Model for Orders, Payments, and Outbox

### 10.1. Order

```javascript
{
  _id: "ORD-0001",
  requestId: "SEED-0001",
  customerId: "CUS-002",
  status: "CREATED",
  items: [
    {
      sku: "SKU-001",
      name: "Sample Product 001",
      quantity: 2,
      unitPriceVnd: NumberLong("80000"),
      lineTotalVnd: NumberLong("160000")
    }
  ],
  totalVnd: NumberLong("160000"),
  createdAt: ISODate("2026-01-01T01:00:00Z"),
  updatedAt: ISODate("2026-01-01T01:00:00Z")
}
```

### 10.2. Payment

```javascript
{
  _id: "PAY-0002",
  orderId: "ORD-0002",
  amountVnd: NumberLong("192000"),
  method: "CARD",
  status: "CAPTURED",
  paidAt: ISODate("2026-01-01T03:00:00Z")
}
```

Amounts are illustrative examples only and do not represent a real payment transaction. Never store card numbers, CVVs, authentication secrets, or real banking information.

### 10.3. Outbox

```javascript
{
  _id: "EVT-ORD-DEMO-001",
  aggregateType: "Order",
  aggregateId: "ORD-DEMO-001",
  eventType: "OrderCreated",
  payload: { orderId: "ORD-DEMO-001", customerId: "CUS-001" },
  processed: false,
  createdAt: ISODate("2026-01-05T00:00:00Z")
}
```

The outbox supports the exercise of "saving the order + the intent to emit an event in the same transaction." Downstream workers still require idempotency/deduplication because publishing outside the database is not part of the MongoDB transaction.

### 10.4. Status List for the Lab

```text
orders.status:
  CREATED
  PAID
  SHIPPED
  CANCELLED

payments.status:
  CAPTURED

outbox.processed:
  false | true
```

In a real application, a state machine is required—do not allow arbitrary transitions (for example, CANCELLED → SHIPPED) without corresponding business rules.

---

## 11. Seeding the Entire Dataset with mongosh

This is the core part of the lesson. The script runs in mongosh connected to the lab MongoDB instance, initializing:

- 5 categories.
- 24 customers.
- 30 products.
- 30 inventory records.
- 120 orders.
- 60 payments (for PAID or SHIPPED orders).
- An outbox collection initially empty; used in the transaction lesson.

### 11.1. Safety Rules Before Running

**Run only on the lab MongoDB instance.** The script uses `updateOne(..., {$setOnInsert:...}, {upsert:true})`, does not drop the database, does not delete documents, and sends no outbound network requests. Re-running the script with the same IDs **does not duplicate seeded data**.

However, `$setOnInsert` only applies to documents that **do not yet exist**. If you modified stock/status during exercises, re-seeding will **not reset** those documents. This is intentional to avoid silently overwriting data you have worked with.

### 11.2. Opening mongosh

```bash
docker exec -it sales-mongo mongosh
```

### 11.3. Script

```javascript
const lab = db.getSiblingDB("sales_lab");

const categories = lab.getCollection("categories");
const customers = lab.getCollection("customers");
const products = lab.getCollection("products");
const inventory = lab.getCollection("inventory");
const orders = lab.getCollection("orders");
const payments = lab.getCollection("payments");
const outbox = lab.getCollection("outbox");

const seedTag = "sales-lab-v1";
const baseMs = ISODate("2026-01-01T00:00:00Z").getTime();

function pad(value, width) {
  return String(value).padStart(width, "0");
}

function dateAtHours(hours) {
  return new Date(baseMs + hours * 3600000);
}

function priceOf(productNumber) {
  // All prices are small integer VND values.
  return 69000 + productNumber * 11000;
}

function longOf(value) {
  return NumberLong(String(value));
}

function insertIfMissing(collection, doc) {
  return collection.updateOne(
    { _id: doc._id },
    { $setOnInsert: doc },
    { upsert: true }
  );
}

// 1. Categories
const categoryNames = [
  ["ELECTRONICS", "Electronics"],
  ["HOME", "Home Appliances"],
  ["OFFICE", "Office"],
  ["SPORT", "Sports"],
  ["BOOK", "Books and Learning"]
];

for (let i = 0; i < categoryNames.length; i++) {
  const n = i + 1;

  insertIfMissing(categories, {
    _id: "CAT-" + pad(n, 2),
    code: categoryNames[i][0],
    name: categoryNames[i][1],
    seedTag,
    createdAt: dateAtHours(0)
  });
}

// 2. Customers
for (let i = 1; i <= 24; i++) {
  const id = "CUS-" + pad(i, 3);

  insertIfMissing(customers, {
    _id: id,
    fullName: "Sample Customer " + pad(i, 3),
    email: "customer" + pad(i, 3) + "@example.test",
    tier: i % 4 === 0 ? "GOLD" : "STANDARD",
    active: true,
    seedTag,
    createdAt: dateAtHours(i)
  });
}

// 3. Products and inventory
for (let i = 1; i <= 30; i++) {
  const sku = "SKU-" + pad(i, 3);
  const name = "Sample Product " + pad(i, 3);
  const categoryNumber = ((i - 1) % 5) + 1;

  insertIfMissing(products, {
    _id: sku,
    categoryId: "CAT-" + pad(categoryNumber, 2),
    name,
    description: "Practice item " + pad(i, 3),
    unitPriceVnd: longOf(priceOf(i)),
    active: i % 6 !== 0,
    tags: ["demo", i % 2 === 0 ? "online" : "store"],
    seedTag,
    createdAt: dateAtHours(i),
    updatedAt: dateAtHours(i)
  });

  insertIfMissing(inventory, {
    _id: sku,
    available: 20 + i * 4,
    reserved: 0,
    seedTag,
    updatedAt: dateAtHours(0)
  });
}

// 4. Historical orders, with price snapshots
const orderStatuses = [
  "CREATED", "PAID", "SHIPPED", "CANCELLED"
];

for (let i = 1; i <= 120; i++) {
  const orderId = "ORD-" + pad(i, 4);
  const customerNumber = ((i - 1) % 24) + 1;
  const customerId = "CUS-" + pad(customerNumber, 3);

  const firstProductNumber = ((i - 1) % 30) + 1;
  const firstSku = "SKU-" + pad(firstProductNumber, 3);
  const firstQuantity = 1 + (i % 3);
  const firstPrice = priceOf(firstProductNumber);

  const items = [{
    sku: firstSku,
    name: "Sample Product " + pad(firstProductNumber, 3),
    quantity: firstQuantity,
    unitPriceVnd: longOf(firstPrice),
    lineTotalVnd: longOf(firstPrice * firstQuantity)
  }];

  let total = firstPrice * firstQuantity;

  // Every even order has an additional line item.
  if (i % 2 === 0) {
    const secondProductNumber = ((i + 6) % 30) + 1;
    const secondQuantity = 1;
    const secondPrice = priceOf(secondProductNumber);

    items.push({
      sku: "SKU-" + pad(secondProductNumber, 3),
      name: "Sample Product " + pad(secondProductNumber, 3),
      quantity: secondQuantity,
      unitPriceVnd: longOf(secondPrice),
      lineTotalVnd: longOf(secondPrice * secondQuantity)
    });

    total += secondPrice * secondQuantity;
  }

  const status = orderStatuses[(i - 1) % 4];
  const createdAt = dateAtHours(i);
  const updatedAt =
    status === "CREATED" ? createdAt : dateAtHours(i + 1);

  insertIfMissing(orders, {
    _id: orderId,
    requestId: "SEED-" + pad(i, 4),
    customerId,
    status,
    items,
    totalVnd: longOf(total),
    currency: "VND",
    seedTag,
    createdAt,
    updatedAt
  });

  // Lab: only PAID/SHIPPED have CAPTURED payments.
  if (status === "PAID" || status === "SHIPPED") {
    insertIfMissing(payments, {
      _id: "PAY-" + pad(i, 4),
      orderId,
      amountVnd: longOf(total),
      currency: "VND",
      method: i % 2 === 0 ? "CARD" : "BANK_TRANSFER",
      status: "CAPTURED",
      seedTag,
      paidAt: dateAtHours(i + 1)
    });
  }
}

// 5. The outbox collection will be used in the transaction lesson.
// Do not seed fake events as already-published events.

printjson({
  categories: categories.countDocuments({ seedTag }),
  customers: customers.countDocuments({ seedTag }),
  products: products.countDocuments({ seedTag }),
  inventory: inventory.countDocuments({ seedTag }),
  orders: orders.countDocuments({ seedTag }),
  payments: payments.countDocuments({ seedTag }),
  outbox: outbox.countDocuments({})
});
```

### 11.4. Expected Counts

| Collection | Number of Seeded Documents |
|---|---:|
| `categories` | 5 |
| `customers` | 24 |
| `products` | 30 |
| `inventory` | 30 |
| `orders` | 120 |
| `payments` | 60 |
| `outbox` | 0 at initialization |

If the counts differ, check whether you ran the script on collections that already contained documents or whether the script stopped midway. The seed script can be re-run to fill in missing IDs.

### 11.5. Why Doesn't the Script Reset Data?

After practicing checkout, you may have reduced stock for SKU-001. Re-running `$setOnInsert` preserves that inventory value. If you want to reset to the exact initial state, there must be an **intentional** lab refresh procedure, rather than turning the seed script into a command that overwrites all business changes.

---

## 12. Verifying Document Counts and Distribution

After seeding, run in mongosh:

```javascript
const lab = db.getSiblingDB("sales_lab");

printjson({
  categories: lab.categories.countDocuments({ seedTag: "sales-lab-v1" }),
  customers: lab.customers.countDocuments({ seedTag: "sales-lab-v1" }),
  products: lab.products.countDocuments({ seedTag: "sales-lab-v1" }),
  inventory: lab.inventory.countDocuments({ seedTag: "sales-lab-v1" }),
  orders: lab.orders.countDocuments({ seedTag: "sales-lab-v1" }),
  payments: lab.payments.countDocuments({ seedTag: "sales-lab-v1" })
});
```

### 12.1. Counting Order Statuses

```javascript
lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Expected: `CREATED`, `PAID`, `SHIPPED`, `CANCELLED`, 30 documents per status.

### 12.2. Total Number of Line Items

```javascript
lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  { $unwind: "$items" },
  { $count: "lineItems" }
]);
```

Expected:

```text
120 orders
60 orders with 1 item
60 orders with 2 items
=> 180 line items
```

### 12.3. Checking Inactive Products

```javascript
lab.products.countDocuments({
  seedTag: "sales-lab-v1",
  active: false
});
```

Expected: 5 inactive products (SKU-006, SKU-012, SKU-018, SKU-024, SKU-030).

### 12.4. Do Not Treat "Correct Counts" as Checking All Relationships

Counts are a smoke test. Later sections verify order/customer references, payment/order references, and totals. If there are duplicate/missing reference bugs, counts can still look normal.

---

## 13. Creating Indexes for Key Queries

Run in `mongosh` on the seeded lab:

```javascript
const lab = db.getSiblingDB("sales_lab");

// Category code must be unique.
lab.categories.createIndex(
  { code: 1 },
  { unique: true, name: "uq_category_code" }
);

// Customer email must be unique.
lab.customers.createIndex(
  { email: 1 },
  { unique: true, name: "uq_customer_email" }
);

// Product listing by category, active, and name.
lab.products.createIndex(
  { categoryId: 1, active: 1, name: 1 },
  { name: "idx_product_category_active_name" }
);

// Order listing for a customer.
lab.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_order_customer_created" }
);

// Dashboard by status.
lab.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_order_status_created" }
);

// Idempotency key for order placement requests.
lab.orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_order_request" }
);

// Find orders containing an item by SKU.
lab.orders.createIndex(
  { "items.sku": 1, status: 1 },
  { name: "idx_order_items_sku_status" }
);

// Lab has only one payment record per order.
lab.payments.createIndex(
  { orderId: 1 },
  { unique: true, name: "uq_payment_order" }
);

// Outbox worker reads unprocessed records.
lab.outbox.createIndex(
  { processed: 1, createdAt: 1 },
  { name: "idx_outbox_pending" }
);

// Inspect catalog.
printjson(lab.orders.getIndexes());
```

### 13.1. Why Doesn't _id Need a Manual Index?

MongoDB automatically creates a unique index on `_id` for standard collections. `SKU-001` is looked up via `products._id` or `inventory._id` using the default index.

### 13.2. Why Index customerId + createdAt?

A query like:

```javascript
lab.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10);
```

has equality on `customerId` and sorts by `createdAt`; a compound index narrows the range by customer and traverses entries in the right order.

### 13.3. Why Have a Unique requestId?

An HTTP request may be retried due to a timeout. A unique index prevents creating two orders with the same idempotency key. However, the HTTP API must still verify the matching payload and handle duplicates as "already processed" or conflict, rather than simply returning a 500 error.

### 13.4. Why Not Index Every Field?

Every index adds storage and write overhead. Do not create an index on every field just because it appears in the schema. Add indexes after identifying query patterns and reviewing explain output.

---

## 14. Index Structure and Performance Questions

### 14.1. A Compound Index Is Not Just Multiple Single Indexes

```javascript
{ customerId: 1, createdAt: -1 }
```

differs from:

```javascript
{ customerId: 1 }
{ createdAt: -1 }
```

A compound index filters by customer and returns results in `createdAt` order within the matching range.

### 14.2. ESR

Guideline rule:

- Equality fields first.
- Sort fields next when avoiding a blocking sort is an important goal.
- Range fields after that, though there are cases where ERS is better if the range is highly selective.

### 14.3. Checking with explain

```javascript
const lab = db.getSiblingDB("sales_lab");

const plan = lab.orders
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");

printjson({
  returned: plan.executionStats.nReturned,
  docsExamined: plan.executionStats.totalDocsExamined,
  keysExamined: plan.executionStats.totalKeysExamined,
  winningPlan: plan.queryPlanner.winningPlan
});
```

With a small seed dataset, the planner may choose a different access path than the index and still be reasonable. Do not assert the exact stage across all MongoDB versions.

### 14.4. Do Not Use executionTimeMillis as a CI Standard

A single `explain` run can be affected by CPU, I/O/cache, and the query planner. When testing query efficiency, verify result correctness and scan budgets on a sufficiently large fixture; benchmark p95/p99 latency in a separate stable environment.

---

## 15. Setting Up Schema Validation After Standardizing Data Types

MongoDB's flexible schema does not automatically guarantee that `createdAt` is always a BSON Date or `totalVnd` is always Int64. A buggy importer might write:

```javascript
{
  createdAt: "2026-01-01",
  totalVnd: "199000"
}
```

after which Date/numeric filters will not behave properly.

### 15.1. Validator Example for Products

In a **lab environment where the current validator is known**, you can design:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.runCommand({
  collMod: "products",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "categoryId", "name",
        "unitPriceVnd", "active"
      ],
      properties: {
        _id: { bsonType: "string" },
        categoryId: { bsonType: "string" },
        name: { bsonType: "string" },
        unitPriceVnd: { bsonType: "long" },
        active: { bsonType: "bool" },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

**Do not run `collMod` arbitrarily on a real database**, because this command can replace an existing validator and break incompatible writers. In the lab, ensure product prices are already stored as `NumberLong` per the seed before enabling.

### 15.2. Validator Example for Orders

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "requestId", "customerId", "status",
        "items", "totalVnd", "currency", "createdAt"
      ],
      properties: {
        _id: { bsonType: "string" },
        requestId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        status: {
          enum: [
            "CREATED", "PAID", "SHIPPED", "CANCELLED"
          ]
        },
        items: { bsonType: "array" },
        totalVnd: { bsonType: "long" },
        currency: { enum: ["VND"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

This is an **optional** extension step and is not required for seeding to run. A minimal validator does not check every business rule, such as whether `total` equals the sum of lines or each item quantity is positive.

### 15.3. Checking Type Distribution

```javascript
lab.orders.aggregate([
  {
    $group: {
      _id: { $type: "$totalVnd" },
      count: { $sum: 1 }
    }
  }
]);
```

Expected is the `long` group for seeded documents.

### 15.4. Schema Validation Does Not Create Foreign Keys

Even a validator enforcing `customerId` as String does not prove that the corresponding customer exists. For cross-collection relationships, application logic or consistency tests are needed.

---

## 16. Query 1: Fetching Active Products by Category

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.products.find(
  { categoryId: "CAT-01", active: true },
  { _id: 1, name: 1, unitPriceVnd: 1 }
)
.sort({ name: 1 })
.limit(10);
```

### 16.1. Matching Index

```javascript
{ categoryId: 1, active: 1, name: 1 }
```

Two equality fields first, followed by product name to support sorting.

### 16.2. Projection

If only displaying a product table, there is no need to load every field. Projection reduces payload/decoding cost. If a query is covered by an index under suitable conditions, fetching full documents can be avoided; do not assume every projection is covered.

### 16.3. Trying explain

```javascript
lab.products.find({
  categoryId: "CAT-01",
  active: true
})
.sort({ name: 1 })
.explain("executionStats");
```

Do not evaluate production performance based on just 30 products. A small lab is for learning plan structure; efficiency regression tests require larger fixtures.

---

## 17. Query 2: Customer Orders Over Time

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.find(
  { customerId: "CUS-001" },
  { _id: 1, status: 1, totalVnd: 1, createdAt: 1 }
)
.sort({ createdAt: -1 })
.limit(10);
```

Index:

```javascript
{ customerId: 1, createdAt: -1 }
```

### 17.1. Querying by Status

```javascript
lab.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
```

Index:

```javascript
{ status: 1, createdAt: -1 }
```

### 17.2. A Note on Pagination

```javascript
.skip(100000).limit(20)
```

on a real collection can incur a heavy index scan even with an index. For deep pagination, consider keyset pagination and a stable sort key.

### 17.3. Sort Tie-Breaker

If multiple orders share the same `createdAt`, add `_id` as a tie-breaker and consider a matching index. This seed has distinct timestamps, but production should not rely on that assumption.

---

## 18. Query 3: Filtering by Date and Data Types

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.find({
  createdAt: {
    $gte: ISODate("2026-01-02T00:00:00Z"),
    $lt: ISODate("2026-01-04T00:00:00Z")
  }
}).sort({ createdAt: 1 });
```

### 18.1. Why Must ISODate Be Used?

Seeded `createdAt` is a BSON Date. Querying with an ISO string:

```javascript
{ createdAt: { $gte: "2026-01-02" } }
```

is not automatically parsed into a BSON Date; range comparisons use type-bracketing semantics.

### 18.2. Checking Types

```javascript
lab.orders.aggregate([
  {
    $group: {
      _id: { $type: "$createdAt" },
      count: { $sum: 1 }
    }
  }
]);
```

### 18.3. Distinguishing UTC and Local Dates

If a user selects "January 2" in Vietnam time, the application must convert the local date range into two proper UTC instants. Do not assume a local day automatically starts at 00:00Z.

---

## 19. Query 4: Revenue Summary by Status

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  {
    $match: {
      seedTag: "sales-lab-v1",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$totalVnd" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

### 19.1. What Metric Is This?

This is the **total value of orders with status PAID or SHIPPED in the synthetic dataset**. It is not accounting revenue and does not handle refunds, discounts, taxes, or shipping fees.

### 19.2. Numeric Type

`totalVnd` is BSON Int64. MongoDB aggregation sums using numeric semantics; for very large monetary values, check your system's overflow/Decimal128 policy.

### 19.3. Indexes and Aggregation

The `{status:1,createdAt:-1}` index can assist with status filtering, but `$group` still has to inspect all matching documents. Do not assume `nReturned=2` means the database only read 2 orders.

---

## 20. Query 5: Top Products by Quantity Sold

Using embedded items:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  {
    $match: {
      seedTag: "sales-lab-v1",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.quantity" },
      totalLineValueVnd: { $sum: "$items.lineTotalVnd" }
    }
  },
  { $sort: { totalQuantity: -1, _id: 1 } },
  { $limit: 10 }
]);
```

### 20.1. Why $unwind?

Each order has an `items[]` array. `$unwind` produces one pipeline row per line item, and `$group` then aggregates totals by SKU.

### 20.2. Snapshot Price

Total line value is taken from order items at placement time, not from the current `products.unitPriceVnd`. This preserves simulated history when product prices change.

### 20.3. On Performance

On large datasets, `$unwind/$group/$sort` can consume significant CPU/memory. This query is suitable for demonstrating aggregation; production analytics may use materialized views, caching, or dedicated batch/reporting pipelines.

---

## 21. Query 6: $lookup Customer and Product

### 21.1. Order + Customer

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { _id: "ORD-0001" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      status: 1,
      totalVnd: 1,
      "customer.fullName": 1,
      "customer.tier": 1
    }
  }
]);
```

### 21.2. Foreign Index

`customers._id` has a default index, aiding equality lookup joins when optimized by the planner/version. For a custom `foreignField`, verify the corresponding index.

### 21.3. Do Not Assume $lookup Enforces Foreign Keys

If a customer is deleted, `$lookup` can return an empty array. MongoDB does not automatically prevent order documents from referencing a nonexistent customer.

### 21.4. Do Not Add $lookup to Every Request

Orders embed price/name snapshots to render history without frequently joining products. Join only when current product/customer data is needed.

---

## 22. Query 7: Verifying Missing References

Example checking for orders without a matching customer:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "foundCustomer"
    }
  },
  { $match: { foundCustomer: { $size: 0 } } },
  { $project: { _id: 1, customerId: 1 } }
]);
```

Expect empty results for the untouched seed dataset.

### 22.1. Checking Payments Without an Order

```javascript
lab.payments.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "orders",
      localField: "orderId",
      foreignField: "_id",
      as: "foundOrder"
    }
  },
  { $match: { foundOrder: { $size: 0 } } },
  { $project: { orderId: 1, amountVnd: 1 } }
]);
```

### 22.2. Missing Results Are Not Always Caused by the Seed

If you modified or deleted data during exercises, these checks will reflect the new state. Do not blindly let the seed overwrite data to "make errors disappear"; investigate what the business operation did.

---

## 23. Query 8: Reconciling Total Amount with Line Items

An invariant:

```text
orders.totalVnd
  = SUM(items[].lineTotalVnd)
```

For seeded orders:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $project: {
      _id: 1,
      totalVnd: 1,
      calculatedVnd: { $sum: "$items.lineTotalVnd" }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$totalVnd", "$calculatedVnd"] }
    }
  }
]);
```

Expected: empty result for untouched seed data.

### 23.1. Checking Quantity and Unit Price

Similarly, you can use `$map` + `$multiply` to verify `lineTotal` against quantity and unit price. Calculations in the service should use numeric types free of floating-point rounding when monetary workflows require exact precision.

### 23.2. Why Is Reconciliation Needed?

An order document intentionally stores redundant snapshot totals. Consistency checks are necessary to catch updates to one field that omit updating related fields.

---

## 24. Connecting with the Java Sync Driver

### 24.1. Dependency

Maven:

```xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>5.5.0</version>
</dependency>
```

This version is an **example**, not a claim of being the latest; use the dependency/version managed by your project and verify compatibility with MongoDB Server.

Gradle:

```groovy
dependencies {
  implementation "org.mongodb:mongodb-driver-sync:5.5.0"
}
```

### 24.2. Java Connection Smoke Test

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class SalesLabPing {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase lab = client.getDatabase("sales_lab");

            Document ping = lab.runCommand(new Document("ping", 1));
            System.out.println("ping=" + ping.toJson());

            long productCount = lab.getCollection("products")
                    .countDocuments(new Document("seedTag", "sales-lab-v1"));

            long orderCount = lab.getCollection("orders")
                    .countDocuments(new Document("seedTag", "sales-lab-v1"));

            System.out.printf(
                    "products=%d orders=%d%n",
                    productCount, orderCount);
        }
    }
}
```

### 24.3. MONGODB_URI on Windows PowerShell

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27017/?replicaSet=rs0"
```

In bash:

```bash
export MONGODB_URI="mongodb://127.0.0.1:27017/?replicaSet=rs0"
```

Do not put passwords into shell history when working with real deployments; use appropriate secrets management.

### 24.4. MongoClient Lifecycle

`MongoClient` is thread-safe and maintains a connection pool, so it should be reused across the application rather than created and closed per HTTP request. The `try-with-resources` in `main` is only appropriate for short-lived programs.

---

## 25. Java: Reading Products, Orders, and Arrays

### 25.1. Products by Category

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.ascending;

MongoCollection<Document> products =
        client.getDatabase("sales_lab")
              .getCollection("products");

for (Document product : products.find(and(
        eq("categoryId", "CAT-01"),
        eq("active", true)))
        .sort(ascending("name"))
        .limit(10)) {

    System.out.printf(
            "%s | %s | %s%n",
            product.getString("_id"),
            product.getString("name"),
            product.get("unitPriceVnd"));
}
```

### 25.2. Orders by Customer

```java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

MongoCollection<Document> orders =
        client.getDatabase("sales_lab")
              .getCollection("orders");

for (Document order : orders
        .find(eq("customerId", "CUS-001"))
        .sort(descending("createdAt"))
        .limit(10)) {

    System.out.println(order.toJson());
}
```

### 25.3. Nested Item Query

```java
for (Document order : orders.find(
        eq("items.sku", "SKU-001"))) {
    System.out.println(order.getString("_id"));
}
```

MongoDB dot notation can match any element in an embedded array. When multiple predicates must apply to the **same** array element, consider `$elemMatch` so they do not accidentally match across different elements.

### 25.4. Numeric Reading

`unitPriceVnd` and `totalVnd` are Int64. `Document.getLong("totalVnd")` works if the decoder returns `Long` matching the seeded BSON type. If code handles legacy data with mixed types, validation or a typed mapper is needed rather than silently casting incorrectly.

---

## 26. Java: Checkout Transaction Deducting Inventory

Because the lab is a replica set, you can try **multi-document transactions**. Example using the Java Sync Driver:

1. Decrement `inventory.available` when sufficient stock remains.
2. Create the order.
3. Create the outbox event.
4. Commit all three together.

### 26.1. Service Example

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.currentDate;
import static com.mongodb.client.model.Updates.inc;

public final class CheckoutDemo {

    public static String checkout(MongoClient client) {
        MongoDatabase db = client.getDatabase("sales_lab");

        MongoCollection<Document> stock =
                db.getCollection("inventory");
        MongoCollection<Document> orders =
                db.getCollection("orders");
        MongoCollection<Document> outbox =
                db.getCollection("outbox");

        // Fixed IDs so the example is easy to observe.
        // A real API needs a request-scoped idempotency key.
        String requestId = "DEMO-CHECKOUT-001";
        String orderId = "ORD-DEMO-001";
        String eventId = "EVT-ORD-DEMO-001";

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {

                UpdateResult result = stock.updateOne(
                        session,
                        and(
                                eq("_id", "SKU-001"),
                                gte("available", 1)
                        ),
                        combine(
                                inc("available", -1),
                                currentDate("updatedAt")
                        )
                );

                if (result.getModifiedCount() != 1) {
                    throw new IllegalStateException(
                            "Insufficient inventory");
                }

                long priceVnd = 80000L;

                Document item = new Document("sku", "SKU-001")
                        .append("name", "Sample Product 001")
                        .append("quantity", 1)
                        .append("unitPriceVnd", priceVnd)
                        .append("lineTotalVnd", priceVnd);

                orders.insertOne(
                        session,
                        new Document("_id", orderId)
                                .append("requestId", requestId)
                                .append("customerId", "CUS-001")
                                .append("status", "CREATED")
                                .append("items", java.util.List.of(item))
                                .append("totalVnd", priceVnd)
                                .append("currency", "VND")
                                .append("createdAt", new Date())
                                .append("updatedAt", new Date())
                );

                outbox.insertOne(
                        session,
                        new Document("_id", eventId)
                                .append("aggregateType", "Order")
                                .append("aggregateId", orderId)
                                .append("eventType", "OrderCreated")
                                .append("payload",
                                        new Document("orderId", orderId)
                                          .append("customerId", "CUS-001"))
                                .append("processed", false)
                                .append("createdAt", new Date())
                );

                return orderId;
            }, options);
        }
    }
}
```

### 26.2. Reading Back the Result

```javascript
const lab = db.getSiblingDB("sales_lab");

printjson(lab.inventory.findOne({ _id: "SKU-001" }));
printjson(lab.orders.findOne({ _id: "ORD-DEMO-001" }));
printjson(lab.outbox.findOne({ _id: "EVT-ORD-DEMO-001" }));
```

### 26.3. Warning When Re-running the Example

Re-running with the same `requestId`/`orderId` will hit the unique index or duplicate `_id`. Because the stock deduction is inside the same transaction, a duplicate-key failure prevents the transaction attempt from committing, avoiding deducting extra stock on a failed attempt. However, a real service must handle **idempotency lookup and unknown commit outcomes** rather than just throwing an exception.

### 26.4. withTransaction Callback May Re-run

The driver may retry the callback upon transient transaction errors. Therefore, do not perform HTTP payments, send emails, or publish to Kafka inside the callback. The outbox event is written in the same transaction, and a worker publishes it after commit.

### 26.5. Not Equivalent to End-to-End Exactly-Once

MongoDB transactions are atomic within the scope of MongoDB writes; external brokers still require idempotency. A worker that publishes successfully but crashes before marking `processed` can emit the event again.

---

## 27. Schema Validation and Transactions: Testing Rollback

### 27.1. Testing Transaction Abort

In Java:

```java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            session,
            new Document("_id", "ORD-ABORT-LAB")
                    .append("requestId", "REQ-ABORT-LAB")
                    .append("customerId", "CUS-001")
                    .append("status", "CREATED")
                    .append("items", java.util.List.of())
                    .append("totalVnd", 0L)
                    .append("currency", "VND")
                    .append("createdAt", new Date())
    );

    session.abortTransaction();
}
```

### 27.2. Verification

```javascript
db.getSiblingDB("sales_lab")
  .orders.findOne({ _id: "ORD-ABORT-LAB" });
```

Expected `null` if the document did not previously exist.

### 27.3. Forgetting to Pass the Session Is a Serious Bug

Wrong:

```java
session.startTransaction();
orders.insertOne(document); // Session not passed.
session.abortTransaction();
```

The insert command is not attached to the active transaction. To participate, use `orders.insertOne(session, document)`.

---

## 28. Verifying Seed Idempotency Without Duplicating Data

### 28.1. Idempotent Upsert

The script uses:

```javascript
collection.updateOne(
  { _id: fixedId },
  { $setOnInsert: document },
  { upsert: true }
);
```

When the ID already exists, the document is not overwritten; when missing, MongoDB inserts it.

### 28.2. Why Must Fixed _ids Be Used?

If seeding uses `insertOne({_id:new ObjectId()})` every time, re-running the script creates extra records and breaks expected counts.

### 28.3. Unique Indexes Provide Additional Protection

Beyond `_id`, `orders.requestId` and `customers.email` have unique indexes. They prevent certain business-key duplicates even if the application has a bug.

### 28.4. Seed Version and Lab State

`seedTag:"sales-lab-v1"` distinguishes synthetic seed records from records created by exercises. Query counts should filter by `seedTag` once you start creating additional records.

### 28.5. Seeding Is Not a Reset Tool

If you updated a record, re-running does not restore the old value. To refresh everything, you need a **disposable lab instance or a reset procedure with explicit confirmation**—never accidentally drop a production database.

---

## 29. Stopping and Restarting the Environment

### 29.1. Stopping the Container

```bash
docker stop sales-mongo
```

### 29.2. Starting the Existing Container Again

```bash
docker start sales-mongo
```

The named volume `sales-mongo-data` preserves the data. The replica set configuration is also stored inside the data directory.

### 29.3. Do Not Re-run rs.initiate

When restarting an existing volume, the replica set is already initialized. Check `rs.status()` instead of trying to recreate the config.

### 29.4. Removing the Container Does Not Necessarily Delete the Volume

```bash
docker rm sales-mongo
```

removes the stopped container, while the named volume typically remains. This is not a data reset. Do not remove the volume if you want to keep your lab.

### 29.5. Full Cleanup Only Intentionally

If you want to wipe the lab on your personal machine, verify the exact container/volume names before performing destructive steps. Do not automate `docker volume rm` in seed scripts or shared terminals. You can create a **newly named volume** to start an independent lab instead of deleting old state.

---

## 30. Troubleshooting Docker and Replica Set

### 30.1. "port is already allocated"

Another process/container is using host port 27017.

- Check `docker ps` and OS port listeners.
- Do not shut down a real MongoDB service serving another application.
- Choose a separate lab port/config and fix the replica set hostname mapping accordingly.

### 30.2. "not primary" or Not Accepting Writes Yet

Check:

```javascript
rs.status();
db.adminCommand({ hello: 1 });
```

In the first few seconds after `rs.initiate()`, the node is not PRIMARY yet. If it takes unusually long, inspect the replica set hostname, logs, and system resources.

### 30.3. "Transaction numbers are only allowed ..."

Commonly occurs when the server is not running a topology that supports retryable writes/transactions. Verify `--replSet`, `rs.initiate()`, PRIMARY member state, and the driver URI. Do not just add `retryWrites=true` and expect standalone mode to support transactions.

### 30.4. "Server selection timed out"

Possible causes:

- Container is not running.
- Incorrect host port mapping.
- Replica set member advertises a hostname the client cannot resolve.
- Different Docker network configuration.
- Firewall/TLS/auth mismatch.
- Java app running in another container while the URI uses `localhost`.

Read full diagnostics safely without logging credentials.

### 30.5. "not authorized"

The lab has no auth per the configuration above; if using Atlas or an authenticated cluster, valid user/roles are required. Do not disable auth in production "to make the lab run."

### 30.6. Missing Data After Restart

Verify the container uses the right named volume rather than creating a new container with a fresh volume. Inspect mounts via `docker inspect` and volumes through the Docker CLI with proper permissions instead of guessing from container names.

---

## 31. Troubleshooting Seed and BSON Types

### 31.1. Partially Executed Script

If the script was interrupted midway, you may have categories/customers/products but incomplete orders.

- Check counts by `seedTag`.
- Inspect the actual error in mongosh.
- Re-run the idempotent seed to fill in documents with missing IDs.
- Do not wipe all data just because a run was incomplete.

### 31.2. DuplicateKeyException

Possible causes:

- Another seed used the same `_id`.
- Duplicate unique email/requestId.
- Old lab data from a different seed version.
- Inconsistency between IDs and business keys.

Do not drop unique indexes just to make seeding pass. Identify which lab the data belongs to.

### 31.3. Dates Stored as Strings

If a writer uses:

```javascript
createdAt: "2026-01-01T00:00:00Z"
```

instead of `ISODate(...)`, Date range filters may miss that document. Use `$type` to detect, fix the writer, and migrate rather than wrapping every query in `$toDate`.

### 31.4. Prices Stored as Strings

If `unitPriceVnd:"80000"`, numeric comparisons/sums will not behave as intended. Avoid relying on ICU `numericOrdering` for money. Use numeric BSON types and schema validation.

### 31.5. Java BigDecimal/Long Mapping

If the Java application model differs from the seed, verify BSON representation via round-trip tests. `BigDecimal` may require explicit Decimal128 mapping; `long` fits the integer VND values of the lab.

---

## 32. Checking Linked Data After Practice

### 32.1. Orders/Customer

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $match: { customer: { $size: 0 } } },
  { $count: "missingCustomers" }
]);
```

If the pipeline returns no output row, the count is 0, meaning there are no missing references.

### 32.2. Product References in Items

```javascript
lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  { $unwind: "$items" },
  {
    $lookup: {
      from: "products",
      localField: "items.sku",
      foreignField: "_id",
      as: "product"
    }
  },
  { $match: { product: { $size: 0 } } },
  {
    $project: {
      _id: 1,
      sku: "$items.sku"
    }
  }
]);
```

### 32.3. Payment Order References

```javascript
lab.payments.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "orders",
      localField: "orderId",
      foreignField: "_id",
      as: "order"
    }
  },
  { $match: { order: { $size: 0 } } }
]);
```

### 32.4. Payment Amount Equals Order Total

You can extend `$lookup` to compare `payments.amountVnd` against `orders.totalVnd` using `$expr`; the seed expects equality. In real systems with refunds, partial captures, and multiple attempts, the invariant will be more complex.

---

## 33. Designing a More Realistic Order Placement Flow

A checkout API does more than run three MongoDB commands:

```text
Validate request / principal
         │
         ▼
Check idempotency key
         │
         ▼
MongoDB transaction
    ├── conditional inventory decrement
    ├── insert order + price snapshot
    └── insert outbox OrderCreated
         │
         ▼
Commit
         │
         ├── return order response
         └── outbox worker publishes event
```

### 33.1. Price Snapshots Must Come from a Trusted Source

Do not trust `unitPriceVnd` submitted by the client in checkout. The service must read product price/availability from an authoritative source and enforce concurrent-update/price-change policies.

### 33.2. Business Idempotency

A `requestId` must be bound to the canonical request payload (customer, items, quantity, currency). If a client sends the same key with a different payload, return a conflict instead of treating it as the same order.

### 33.3. External Payment Does Not Belong Inside a MongoDB Transaction

Do not call a payment gateway inside a `withTransaction` callback; the callback may be retried. Use a payment provider idempotency key, saga, or reconciliation workflow.

### 33.4. Transactions Do Not Replace Validation

Inside the transaction, you must still verify `available >= quantity`, active product status, positive quantities, pricing policies, and valid business states.

---

## 34. Automated Testing with JUnit/Testcontainers

### 34.1. Why Are Integration Tests Needed?

Unit tests mocking `MongoRepository` do not verify:

- BSON date/number mapping.
- Index creation.
- Aggregation results.
- Unique index behavior.
- Transaction rollback.
- Query plans.
- Replica set topology.

Integration tests should run against real MongoDB, preferably in an isolated container/cluster.

### 34.2. Test Sample

In JUnit 5:

```java
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

@Test
void salesSeedHasExpectedCounts() {
    var db = client.getDatabase("sales_lab");

    assertEquals(
            30L,
            db.getCollection("products")
              .countDocuments(new Document(
                      "seedTag", "sales-lab-v1")));

    assertEquals(
            120L,
            db.getCollection("orders")
              .countDocuments(new Document(
                      "seedTag", "sales-lab-v1")));
}
```

This example is a test body inside a test class with a configured `MongoClient client`, not a standalone Java source file.

### 34.3. Testcontainers

Pin the image/server version for integration tests. To test transactions, the container must be configured as a replica set according to your Testcontainers version's API; do not assume a standalone `mongod` is sufficient.

### 34.4. Never Use a Production URI in CI

Create a disposable test database/environment with explicit guards and restricted permissions. Never run `dropDatabase()` against an arbitrary URI.

### 34.5. Testing Idempotent Seeding

Seed twice and assert counts remain unchanged; then modify one seeded record, re-seed, and assert `$setOnInsert` does not reset the record. This test verifies the "insert missing data only" design.

### 34.6. Testing Consistency

Verify:

- 5 categories, 24 customers, 30 products, 30 inventory, 120 orders, 60 payments.
- 30 orders per status.
- 180 line items.
- Payment references point to existing orders.
- Order total = sum of line totals.
- All seeded dates are BSON Date, prices are Int64.
- No negative stock at seed time.

---

## 35. Observing Queries and Distinguishing Slow-Query Tests

### 35.1. Explain

```javascript
db.getSiblingDB("sales_lab")
  .orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

### 35.2. Counters Worth Reading

- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- Chosen index/stage.
- Sort stage if present.

### 35.3. Small Datasets Are Not for Production Benchmarks

120 orders are enough to learn CRUD and aggregation, but the planner may pick `COLLSCAN` because the collection is tiny. Do not treat that as proof of a wrong index or slow MongoDB. For performance regression testing, use a sufficiently large fixture with a representative distribution.

### 35.4. Do Not Assert Arbitrary Milliseconds

A test like:

```java
assertTrue(explainMillis < 5);
```

is highly prone to flakiness from CPU/cache/CI noise. Prefer correctness/index contract/work budgets on controlled datasets, and measure p95/p99 SLAs separately in a benchmark environment.

---

## 36. Security Considerations for a Real Sales Application

The lab uses synthetic data, but good habits should be formed early:

- Never commit database passwords.
- Never use the MongoDB root user for the web application.
- Restrict roles to specific databases/collections.
- Enable authentication, TLS, and network isolation in shared environments.
- Never store card numbers/CVVs or credentials in payment documents.
- Never use real customer emails in fixtures.
- Keep immutable order snapshots for business audits.
- Manage retention and backups.
- Control logs/traces containing PII.
- Enforce tenant isolation in queries and index design.

### 36.1. Tenant Isolation

The dataset illustrates `customerId` and category, without `tenantId`. In multi-tenant SaaS, every business query must be scoped to the authenticated tenant, and indexes may need `tenantId` as a prefix. Never trust an arbitrary client-supplied `tenantId`.

### 36.2. Protecting the Outbox

The outbox may contain customer IDs and business payloads. Workers/analysts should not have full read access to all PII unless needed.

### 36.3. Seeding Without Real Data

The `example.test` domain and fake names keep the lab safe. If you want to simulate production distributions, generate synthetic data with matching structure rather than copying customer records without authorization.

---

## 37. Exercise 1: Extending the Seed Dataset

Add:

- 10 customers.
- 20 products.
- 100 new orders with deterministic IDs.
- 2–3 items/order.
- No duplication when re-seeded.

Requirements:

1. Do not use random IDs for a re-runnable seed.
2. Unique `requestId`.
3. Price snapshots.
4. Valid dates/long amounts.
5. Aggregate counts and line items after adding.

---

## 38. Exercise 2: Adding Shopping Carts

Design a `carts` collection:

```javascript
{
  _id: "CART-CUS-001",
  customerId: "CUS-001",
  items: [
    { sku: "SKU-001", quantity: 2 },
    { sku: "SKU-005", quantity: 1 }
  ],
  updatedAt: ISODate("2026-01-05T00:00:00Z")
}
```

Questions:

1. Why don't cart items necessarily store fixed price snapshots like orders?
2. Should you index `customerId` or use a deterministic `_id`?
3. When the customer checks out, how should inventory and prices be validated?
4. Can a cart grow unboundedly inside a single document?

---

## 39. Exercise 3: Finding Orders by Product

Requirements:

1. Find all orders with `items.sku="SKU-001"`.
2. Include only `PAID`/`SHIPPED`.
3. Project `orderId`, `customerId`, `createdAt`.
4. Read explain and verify the `items.sku,status` index.
5. Compare behavior when the index is missing.
6. Explain why `items[]` creates a multikey index.

---

## 40. Exercise 4: Monthly Revenue Report

Design an aggregation:

1. Match status `PAID`/`SHIPPED`.
2. Group by month of `createdAt`.
3. Sum `totalVnd`.
4. Count orders.
5. Sort by month.
6. Explain why the result represents simulated revenue only, excluding refunds and taxes.

Use `$dateTrunc`/`$dateToString` according to your MongoDB version, specifying the exact timezone.

---

## 41. Exercise 5: Testing Transactions

Write a Java service:

1. Accept `requestId`, `customerId`, `SKU`, `quantity`.
2. Validate that `quantity` is positive.
3. Conditionally update inventory.
4. Insert the order.
5. Insert the outbox record.
6. Commit.
7. Intentionally trigger a duplicate `requestId` and observe abort/reconciliation.

Do not make external payment/email calls inside the callback.

---

## 42. Exercise 6: Race Condition

Set the inventory of one SKU in a disposable lab to `available=1` via a controlled update.

Two concurrent requests each purchase `quantity=1`:

1. Use separate sessions; never share a `ClientSession` across threads.
2. Use a conditional update.
3. Only one transaction may commit without a restock.
4. Prevent negative `available`.
5. Explain transient write conflicts and retry policy.

Perform this only in the lab; restore data from a snapshot/new lab if needed.

---

## 43. Exercise 7: Detecting Wrong Data Types

Try inserting a lab document with:

```javascript
{
  _id: "ORD-WRONG-TYPE",
  requestId: "TEST-TYPE",
  customerId: "CUS-001",
  status: "CREATED",
  items: [],
  totalVnd: "100000",
  currency: "VND",
  createdAt: "2026-01-01T00:00:00Z"
}
```

Compare:

- Does a Date range query match it?
- What does `$type` return?
- If the schema validator is enabled, is the insert rejected?
- How do you fix existing bad data and new writers?

Test only on a disposable lab; do not add invalid records to the standard seed dataset.

---

## 44. Exercise 8: Indexes and Query Plans

1. Query the 10 most recent orders of `CUS-001`.
2. Inspect explain with the `customerId,createdAt` index.
3. Compare against a forced natural scan using `hint({$natural:1})` in the lab.
4. Identify `docsExamined`/`keysExamined`.
5. Explain why 120 documents are insufficient for performance benchmarking.
6. Expand the fixture sufficiently if you need regression tests.

---

## 45. Exercise 9: Unique Email and Idempotency

1. Try inserting a customer with a duplicate email.
2. Observe the duplicate-key error.
3. Try creating an order with a duplicate `requestId` but a different `_id`.
4. Explain why `requestId` must be tied to the payload.
5. Design the API response when retrying an HTTP request after commit when the original response was lost.
6. Do not infinitely retry `DuplicateKey`.

---

## 46. Exercise 10: Revenue and Payment Auditing

1. List orders with status `PAID`/`SHIPPED` that have no payment.
2. List payments that have no matching order.
3. Compare `payment.amountVnd` and `order.totalVnd`.
4. Extend the schema for refunds/partial captures.
5. Explain why a unique payment-per-order index may not fit when multiple payment attempts are needed.

---

## 47. Exercise 11: Designing Local/CI/Prod Environments

Analyze the differences:

| Environment | Purpose |
|---|---|
| Local Docker | Learning and development |
| CI/Testcontainers | Isolated, disposable integration tests |
| Staging | Deployment configuration close to production |
| Production | Security, HA, backups, monitoring, and SLOs |

Propose a dedicated deployment configuration for each environment. Never reuse unauthenticated single-node localhost Docker as a production architecture.

---

## 48. Exercise 12: Extending into a Java API

Design endpoints:

```text
GET    /products?categoryId=CAT-01
GET    /products/{sku}
GET    /customers/{id}/orders
GET    /orders/{id}
POST   /orders
GET    /reports/top-products
GET    /reports/revenue
```

Requirements:

- Input validation.
- Typed BSON mapping.
- Actor/tenant authorization.
- Pagination and stable sorting.
- Idempotency key on `POST /orders`.
- Transaction for checkout.
- No MongoDB URI hardcoded in code.
- Logging/tracing without leaking PII.

---

## 49. Lab Completion Checklist

### 49.1. Environment

- [ ] MongoDB container running with host port bound to localhost.
- [ ] Replica set `rs0` initialized.
- [ ] `hello.isWritablePrimary == true`.
- [ ] Mongosh connects successfully.
- [ ] Java URI points to the right host/replica set.
- [ ] No production secrets used.

### 49.2. Data

- [ ] 5 categories.
- [ ] 24 customers.
- [ ] 30 products.
- [ ] 30 inventory snapshots.
- [ ] 120 orders.
- [ ] 60 payments.
- [ ] Outbox initially empty.
- [ ] 30 orders in each status.
- [ ] 180 line items.
- [ ] IDs and `requestIds` are unique.
- [ ] Money fields are BSON Int64.
- [ ] Timestamp fields are BSON Date.

### 49.3. Indexes

- [ ] Customer email unique.
- [ ] Category code unique.
- [ ] Order `requestId` unique.
- [ ] Payment `orderId` unique per lab design.
- [ ] Product listing compound index.
- [ ] Order customer/date compound index.
- [ ] Order status/date compound index.
- [ ] Items SKU index.
- [ ] Outbox pending index.
- [ ] Explain output and index catalog inspected.

### 49.4. Business Logic

- [ ] Order line prices are snapshots.
- [ ] Order total equals sum of `lineTotal`.
- [ ] Payment references exist.
- [ ] Product references exist.
- [ ] Inventory is non-negative.
- [ ] Demo transaction commits cleanly or aborts without partial state.
- [ ] No external side effects inside `withTransaction` callback.
- [ ] Re-running seed does not duplicate records.

### 49.5. Safety

- [ ] Data is completely synthetic.
- [ ] Unsecured lab is not used in shared/production environments.
- [ ] No automated `dropDatabase`/volume removal scripts.
- [ ] Intentional strategy for keeping or removing named volumes.
- [ ] No raw credentials in logs/Markdown.
- [ ] Schema/uniqueness assumptions clearly documented.

---

## 50. Common Errors and Root-Cause Diagnosis

| Error | Possible Cause | Resolution |
|---|---|---|
| `docker: command not found` | Docker not installed or missing from PATH | Install/start Docker |
| Docker daemon unavailable | Docker Desktop/daemon not running | Check `docker info` |
| Port 27017 already in use | Another service/container occupies the port | Adjust lab network appropriately |
| `rs.initiate()` reports already initialized | Volume retained replica set config | Use `rs.status()` |
| Mongo not PRIMARY yet | Election/init not yet complete | Check hello/status/logs |
| Java server selection timeout | URI/hostname/port mismatch | Check advertised member address |
| Transaction unsupported | Standalone mode or wrong topology | Initiate replica set |
| Low seed counts | Script stopped midway | Inspect error, rerun idempotently |
| Duplicate key during seed | Duplicate ID/business key | Inspect old lab data |
| `createdAt` filter misses docs | String vs BSON Date | Check `$type`/migration |
| Incorrect total price | Snapshot/calculation bug | Run reconciliation |
| Empty customer lookup | Nonexistent referential ID or type mismatch | Check `_id` and query |
| Slow product lookup | Missing/wrong index or different dataset | Inspect explain/index catalog |
| Retried transaction causes duplicate | Fixed IDs/HTTP retry | Idempotency lookup/policy |
| Data persists after removing container | Named volume still exists | Understand volume lifecycle |
| Data lost when switching containers | Changed volume or filesystem path | Verify mounts |
| Unique index creation failed | Existing duplicates | Audit/clean data per policy |
| Java codec error | BSON type mismatch with POJO | Check schema/converter/typing |
| `COLLSCAN` on 120 records | Planner considers scan cheaper | Do not conclude it's a performance bug |
| Outbox message delivered twice | Worker crashed before checkpoint | Consumer deduplication |

---

## 51. References

- [MongoDB Manual — Install with Docker](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-community-with-docker/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Connection Strings](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [MongoDB Manual — Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedded Data](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Get Started](https://www.mongodb.com/docs/drivers/java/sync/current/get-started/)
- [MongoDB Java Sync Driver — CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)

These links are documentation for checking the **server/driver version in use**. Some API/link paths may be reorganized across versions. Prioritize documentation for your project's release line, and do not treat the lab configuration as a production runbook.

---

## 52. Summary

1. This practice lesson defined a relatively safe local MongoDB environment for learning, using a **single-node replica set** to support subsequent transaction and change stream lessons; this environment has no high availability and has authentication disabled.
2. The `sales_lab` database models 7 business entities. We chose to embed line-item snapshots inside orders, reference customers/products, and separate inventory/payment/outbox by responsibility.
3. The seed script uses deterministic IDs and `$setOnInsert` so it **does not duplicate data when re-run**. It does not reset modified documents.
4. Data is consistently typed: IDs are BSON Strings, amounts are BSON Int64 VND, timestamps are BSON Date UTC, and statuses follow defined conventions.
5. Indexes are created for key query shapes: unique business keys, category listings, orders by customer/date, dashboards by status/date, finding SKUs in embedded items, and pending outbox records.
6. Practice queries cover CRUD, filtering, sorting, aggregation, `$unwind`, `$group`, `$lookup`, reference validation, and total amount reconciliation.
7. The Java Sync Driver connects via an environment-provided URI; the transaction example updates inventory, creates an order, and writes an outbox record in the same commit.
8. Real-world deployment still requires authentication, RBAC, TLS, production topology, retries/idempotency, monitoring, migrations, backups, and performance tests on representative data.

**Expected outcome:** A reproducible MongoDB database with consistent structure and data at the lab level, ready for subsequent integrated practice lessons without starting from empty collections or ad-hoc data creation for every question.
