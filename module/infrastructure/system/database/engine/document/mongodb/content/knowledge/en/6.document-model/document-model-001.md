# Starting from Query Needs, Read/Write Frequency, and Data Lifecycle

## 1. Document Modeling Mindset in MongoDB

When transitioning to MongoDB, a common mistake is immediately listing entities such as Customer, Product, and Order and turning each entity into a collection. That approach may produce valid data, but it fails to answer the most important question: **how will the application read and write that data?**

MongoDB stores data as BSON documents. A single document can contain scalar fields, embedded objects, and arrays, so the design does not have to follow the "one table per entity" model of relational databases. Deciding whether to **embed** or **reference** should follow the operations the application actually performs:

- Which screens are opened frequently? Which data fields does each screen need?
- Does a query need to fetch multiple components together, and with what filter and sort conditions?
- Which data is updated independently, and which data is always written together?
- Is the number of elements in an array bounded? How fast will the data grow?
- How long does a document exist? When is it modified, locked, archived, hidden, anonymized, or deleted?
- Which operations require immediate consistency, and which ones accept eventual updates?

**Core principle:** Design documents around **access patterns**, **read/write workload**, and **data lifecycle**, and only then finalize collections, embedding/referencing structures, and indexes.

In this lesson, we build a model for a medium-scale online ordering system. The workload figures are **assumptions for design practice**, not measured metrics from a production system. The goal is to understand how a product requirement is translated into explainable and verifiable data decisions.

## 2. Start with Business Questions, Not Collections

Suppose an e-commerce system has the following features:

1. Customers browse the product catalog by category and price.
2. Customers add, update, and remove items in their cart.
3. Customers place orders; the system must preserve the price and shipping address at the time of placement.
4. Customers view order details and recent order history.
5. Staff process orders by status: pending, paid, shipped.
6. The system records state transition history for audit and troubleshooting.
7. Abandoned carts or temporary checkout sessions can expire; paid orders must be retained according to retention policies.

Not all requirements have the same priority. Catalog queries may occur hundreds of times per second; loading order details may happen less often; writing status history may be infrequent yet require strict accuracy. A good design **optimizes critical access paths** while preserving business correctness, rather than trying to minimize the number of collections at all costs.

### 2.1. Write the Access Pattern Table First

An access pattern table should include at least: **who calls it**, **what data is retrieved**, **filters/sorting**, **frequency**, **related write paths**, and **consistency requirements**.

| ID | Requirement and Query Pattern | Assumed Load | Key Considerations |
| --- | --- | --- | --- |
| AP1 | Browse products by tenant, category, active; sort by price | 80 reads/sec at peak | Read-heavy, needs index; paginate and return only display fields |
| AP2 | View single order details by tenant and orderId | 30 reads/sec | Needs line items, prices, address, and status returned together |
| AP3 | List customer orders by tenant and customerId, newest first | 20 reads/sec | Needs index matching filter + sort, stable pagination |
| AP4 | Update quantity of an item in the cart | 15 writes/sec | A cart may be edited repeatedly; single-document operation should be atomic |
| AP5 | Create an order from a cart | 5 writes/sec | Needs price snapshot; handle pricing and inventory rules properly |
| AP6 | Staff view pending orders by creation time | 10 reads/sec | Filter by status and sort by date; consider a dedicated index |
| AP7 | Transition order status, record change history | 8 writes/sec | Needs transition guard and audit trail history |
| AP8 | Delete expired checkout sessions | Background job by expiration time | Can use TTL; delayed cleanup is acceptable |

The values above are **illustrative peak figures**, not performance guarantees. Actual metrics must be measured via logs, metrics, and load testing. Beyond requests per second, you should collect **p95/p99 latency**, error rates, result sizes, documents scanned, and query patterns over time.

### 2.2. Express a Query as a Data Contract

For example, AP3 can be described as follows:

~~~yaml
accessPattern: AP3
actor: customer
intent: List recent orders
filter:
  tenantId: equality
  customerId: equality
sort:
  placedAt: descending
  _id: descending
pageSize: 20
fields:
  - orderNo
  - status
  - placedAt
  - total
peakReadRps: 20
consistency: read committed business state
~~~

The contract helps answer several design questions: `customerId` must exist on the order document, a `placedAt` field is required, the list should return an **order summary** rather than loading the entire status history, and the index can start with `tenantId`, `customerId` before the sort order.

Usually it is best to document the 5–15 most important access patterns and identify which ones account for the majority of traffic or have strict latency requirements. Infrequent use cases still need support, but should not force every common read to pay a performance penalty for them.

## 3. Analyze Read/Write Workload to Choose Document Boundaries

### 3.1. Read Together or Updated Independently?

An order screen typically displays these fields together: current status, line items, quantities, purchase prices, total amount, and shipping address at placement time. Those fields form **a natural unit of reading**, making them a good fit inside the Order document when size is kept under control.

Meanwhile:

- Product prices are updated by staff independently of past orders.
- Customer profiles are modified independently of already placed order details.
- Status change history can grow over time and needs separate filtering/retrieval.
- Shopping carts are updated frequently but are usually small and short-lived.

If the entire Product is embedded into every Order, product updates will create inconsistent copies. If Product is only referenced without saving the price at purchase time, historical orders will change meaning whenever product prices change.

The reasonable solution here is a **hybrid approach**:

- Order keeps **productId** so it can trace back to the source product.
- Each Order line item **embeds the item title, SKU, quantity, and unit price at placement time** as a snapshot.
- Product exists independently to support catalog browsing and current price updates.

This decision is based on the lifecycle of the information, not simply on the "Order has many Products" relationship.

### 3.2. Embed, Reference, or Hybrid?

| Criterion | Prefer Embedding | Prefer Referencing |
| --- | --- | --- |
| Read pattern | Always read together with the parent document | Frequently read or queried separately |
| Write pattern | Changes with the parent, low write contention | Updated frequently and independently |
| Element count | Small or strictly bounded | Can grow without bound |
| Lifecycle | Coexists and is deleted/retained with the parent | Independent lifecycle |
| Consistency | Want atomic updates within a single document | Multi-document updates acceptable or transactions needed |
| Size | Kept small with a growth budget | Becomes large, wastes bandwidth when reading the parent |
| Examples | Address snapshot, bounded order line items, small config lists | Product catalog, customer profile, long-term order events |

**Embedding does not mean embedded fields cannot be indexed.** MongoDB supports querying and indexing subdocument paths and arrays; however, an index on an array becomes a multikey index and requires evaluating size, element count, and compatibility with sorting.

**Referencing does not automatically provide foreign keys.** MongoDB does not automatically verify that `customerId` or `productId` exists in another collection when inserting an Order. The application layer must enforce referential integrity according to business rules.

### 3.3. Never Embed Unbounded Arrays

Example of a problematic model:

~~~javascript
{
  _id: "order-001",
  status: "shipped",
  events: [
    // Every status change or system action
    // appends another element to the same document.
  ]
}
~~~

If a document continuously accumulates thousands or millions of events, both document size and update overhead can grow substantially. MongoDB enforces a **16 MiB limit per BSON document**. For data that grows without bound, you should not rely on an embedded array holding everything.

One alternative:

~~~text
orders
  _id
  customerId
  status                 <- current status for fast reads
  items[]                <- bounded count per ordering rules
  placedAt

order_events
  _id
  orderId                <- reference to orders._id
  fromStatus
  toStatus
  occurredAt
  actorId
~~~

When history is needed, query `order_events` by `orderId` and timestamp. During normal order detail loads, only read `orders`. If history is short and strictly capped, embedding may still work; the deciding factor is **actual growth and access patterns**, not default preference.

### 3.4. One-to-Many Relationships Require Cardinality Questions

Before embedding an array, estimate:

1. At most how many child elements can a parent document have today?
2. After one year or five years, will that bound change?
3. Is there a need to paginate, filter, or update a single child element independently?
4. If multiple writers modify the parent document concurrently, could write contention / a hot document occur?
5. Could the document approach the 16 MiB limit or generate too many index entries?

A **shopping cart** is usually a small array with an item-limit policy, so `items` can be embedded in `Cart`. **Event logs**, comments on a popular post, or multi-year transaction histories are usually better separated into their own collection.

## 4. Data Lifecycle Determines Storage Strategy

A design based solely on today's queries will break down as data grows or changes state. You must examine data from creation to expiration.

| Data Type | At Creation | While Active | At Expiration | Design Implication |
| --- | --- | --- | --- | --- |
| Product | Staff adds item | Edit price, stock, description | Discontinued, may stay for lookup | Independent collection with `active`; old orders keep snapshot |
| Customer | Registration | Edit name, contact, address | Account closed/anonymized per policy | Do not make historical orders depend on current profile |
| Order | Successful checkout | Status transitions, delivery | Completed/cancelled and kept per policy | Stable document, transaction snapshot, current status |
| Order event | Significant change occurs | Mostly append and audit queries | Archived or purged per audit policy | Separate event collection if long-term growth |
| Cart | User adds items | Frequent writes, bounded item count | Ordered or abandoned | Embed `items`, define expiration mechanism |
| Checkout session | Payment started | Session status checks | Timeout reached | TTL can fit when delayed deletion is acceptable |

### 4.1. Distinguish Current State from State History

Order needs the current status to quickly answer "where is this order now?". The `order_events` log answers "who changed it from which status to which status and when?". These two questions have different frequencies, lifecycles, and control requirements.

An illustrative state transition rule:

~~~text
pending --> paid --> shipped --> completed
    |         |
    +------> cancelled
~~~

Real-world rules can be more complex, such as refunds or redelivery. The point is not drawing every possible state, but identifying **conditional transitions** that require protection:

- When transitioning from `pending` to `paid`, the write operation must ensure the order is still in `pending`.
- If recording an event and updating Order must **succeed or fail together**, you must design a multi-document transaction where supported by MongoDB, or an equivalent reliable mechanism.
- Simply updating Order and hoping the event is written afterward does not satisfy atomic audit requirements.

### 4.2. TTL Is Only for Data Truly Allowed to Expire

MongoDB provides a **TTL index** to automatically delete documents based on a date field. This is a suitable tool for certain temporary sessions, expired tokens, or log data with a deletion policy. For example:

~~~javascript
const lab = db.getSiblingDB("mongo_access_lab");

lab.getCollection("lab_checkout_sessions").createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_checkout_expires_at" }
);

lab.getCollection("lab_checkout_sessions").insertOne({
  sessionId: "checkout-example-001",
  tenantId: "shop-01",
  expiresAt: new Date(Date.now() + 15 * 60 * 1000)
});
~~~

With `expireAfterSeconds` set to 0, a document becomes eligible for removal once **expiresAt** has passed. TTL runs via a background thread, so it **does not guarantee deletion at the exact expiration timestamp**. The application must still check `expiresAt` when validating whether a session is still valid. TTL does not replace authorization or payment status checks.

A TTL index is normally created on **a single date field**. Documents missing `expiresAt` or storing the wrong type may not be cleaned up as intended. Do not apply TTL to paid orders simply because they are old: retention periods for transactions, warranties, reconciliation, and legal compliance must be decided upfront.

### 4.3. Archiving, Anonymization, and Schema Evolution

The lifecycle does not always end with a delete:

- An Order may be marked `archived` and moved to an appropriate storage tier after a policy-defined period.
- Personal data in a shipping address may need to be anonymized or trimmed, while certain transaction details must be retained.
- A Product may switch `active` from `true` to `false` without deleting the source document.
- The Order structure may evolve from **schemaVersion: 1** to a newer version; application code must be able to read older data or have an appropriate migration plan.

If all of a Customer's personal data is duplicated into every order, deleting/anonymizing the customer can become hard to control. When snapshotting shipping information is necessary, clearly define which fields are allowed to be stored, the purpose, retention period, and deletion/anonymization workflow.

## 5. Proposed Model for the Ordering System

From the query table and lifecycles, an initial design might look like this:

~~~text
customers                 products
  _id                       _id
  tenantId                  tenantId
  displayName               category
  contact...                active
                             price

orders
  _id
  tenantId
  customerId ----------> customers._id
  orderNo
  placedAt, updatedAt
  status
  items[]                 <-- line item snapshot at placement
    productId ----------> products._id
    sku
    title
    quantity
    unitPrice
  shippingAddressSnapshot
  total
  schemaVersion

order_events
  _id
  tenantId
  orderId -------------> orders._id
  fromStatus, toStatus, occurredAt

carts
  _id, tenantId, customerId, items[], updatedAt

checkout_sessions
  sessionId, tenantId, expiresAt
~~~

The arrows represent **logical references by value**, not automatic foreign key constraints. In the practice examples, IDs are fixed strings so repeatable outputs are easy to read. In production, ObjectIds or UUIDs can be used if they satisfy the system's ID contract.

### 5.1. An Order Document Containing Data for the Detail Screen

~~~javascript
{
  _id: "o001",
  dataset: "access-pattern-v1",
  tenantId: "shop-01",
  customerId: "c001",
  orderNo: "SO-2026-001",
  placedAt: ISODate("2026-02-01T09:00:00.000Z"),
  updatedAt: ISODate("2026-02-01T09:15:00.000Z"),
  status: "paid",
  items: [
    {
      productId: "p001",
      sku: "BOOK-A5",
      title: "A5 Notebook",
      quantity: NumberInt(2),
      unitPrice: NumberDecimal("40000.00")
    },
    {
      productId: "p002",
      sku: "PEN-BLUE",
      title: "Blue Pen",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("10000.00")
    }
  ],
  shippingAddressSnapshot: {
    city: "Hanoi",
    district: "Cau Giay"
  },
  total: NumberDecimal("90000.00"),
  schemaVersion: NumberInt(1)
}
~~~

The order detail screen does not need to fetch each Product document to get item titles and unit prices. The **title/sku/unitPrice** fields are snapshots at purchase time, because the Product's current price and title may have changed. If current stock must be displayed, that is different data and may require querying Product separately.

This document does **not** embed the full chronological event history; `order_events` stores it separately. The current status sits directly on Order to serve frequent screens.

### 5.2. Data Constraints Do Not Disappear with Documents

The design must still state rules:

1. `tenantId` is present on all documents requiring tenant isolation.
2. `customerId` and `productId` have the same type as the `_id` of their target collections.
3. `Order.items` has at least one item, positive quantities, and business-defined limits.
4. `UnitPrice` and `total` intentionally use a decimal type; `total` must match pricing calculation rules (including taxes, discounts, and shipping fees if applicable).
5. `OrderNo` is unique per tenant.
6. Status must adhere to valid transitions.
7. Confirmed orders preserve transaction snapshots even if Product or Customer changes.

MongoDB supports **schema validation** to catch certain shape/type errors, but business logic validation is still required in the application layer. An index only enforces uniqueness on indexed keys; it does not automatically police all relationships or pricing rules.

## 6. Building Repeatable Sample Data in mongosh

To test the access patterns, we can create a small, deterministic dataset. The script below only uses the **mongo_access_lab** database, collections prefixed with **lab_**, and documents tagged with **dataset: "access-pattern-v1"**. Run it in an isolated lab environment:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  const tag = "access-pattern-v1";

  const customers = lab.getCollection("lab_customers");
  const products = lab.getCollection("lab_products");
  const orders = lab.getCollection("lab_orders");
  const events = lab.getCollection("lab_order_events");
  const carts = lab.getCollection("lab_carts");

  // Reset the lesson dataset to its initial state.
  events.deleteMany({ dataset: tag });
  orders.deleteMany({ dataset: tag });
  carts.deleteMany({ dataset: tag });
  products.deleteMany({ dataset: tag });
  customers.deleteMany({ dataset: tag });

  customers.insertMany([
    {
      _id: "c001", dataset: tag, tenantId: "shop-01",
      displayName: "Customer A", city: "Hanoi"
    },
    {
      _id: "c002", dataset: tag, tenantId: "shop-01",
      displayName: "Customer B", city: "Da Nang"
    }
  ]);

  products.insertMany([
    {
      _id: "p001", dataset: tag, tenantId: "shop-01",
      sku: "BOOK-A5", title: "A5 Notebook",
      category: "stationery", active: true,
      price: NumberDecimal("40000.00")
    },
    {
      _id: "p002", dataset: tag, tenantId: "shop-01",
      sku: "PEN-BLUE", title: "Blue Pen",
      category: "stationery", active: true,
      price: NumberDecimal("10000.00")
    },
    {
      _id: "p003", dataset: tag, tenantId: "shop-01",
      sku: "CUP-WHITE", title: "Ceramic Mug",
      category: "accessory", active: true,
      price: NumberDecimal("120000.00")
    }
  ]);

  orders.insertMany([
    {
      _id: "o001", dataset: tag, tenantId: "shop-01",
      customerId: "c001", orderNo: "SO-2026-001",
      placedAt: ISODate("2026-02-01T09:00:00.000Z"),
      updatedAt: ISODate("2026-02-01T09:15:00.000Z"),
      status: "paid",
      items: [
        {
          productId: "p001", sku: "BOOK-A5", title: "A5 Notebook",
          quantity: NumberInt(2), unitPrice: NumberDecimal("40000.00")
        },
        {
          productId: "p002", sku: "PEN-BLUE", title: "Blue Pen",
          quantity: NumberInt(1), unitPrice: NumberDecimal("10000.00")
        }
      ],
      shippingAddressSnapshot: { city: "Hanoi", district: "Cau Giay" },
      total: NumberDecimal("90000.00"),
      schemaVersion: NumberInt(1)
    },
    {
      _id: "o002", dataset: tag, tenantId: "shop-01",
      customerId: "c001", orderNo: "SO-2026-002",
      placedAt: ISODate("2026-02-02T10:00:00.000Z"),
      updatedAt: ISODate("2026-02-02T10:00:00.000Z"),
      status: "pending",
      items: [
        {
          productId: "p003", sku: "CUP-WHITE", title: "Ceramic Mug",
          quantity: NumberInt(1), unitPrice: NumberDecimal("120000.00")
        }
      ],
      shippingAddressSnapshot: { city: "Hanoi", district: "Cau Giay" },
      total: NumberDecimal("120000.00"),
      schemaVersion: NumberInt(1)
    },
    {
      _id: "o003", dataset: tag, tenantId: "shop-01",
      customerId: "c002", orderNo: "SO-2026-003",
      placedAt: ISODate("2026-02-03T08:00:00.000Z"),
      updatedAt: ISODate("2026-02-04T09:00:00.000Z"),
      status: "shipped",
      items: [
        {
          productId: "p002", sku: "PEN-BLUE", title: "Blue Pen",
          quantity: NumberInt(3), unitPrice: NumberDecimal("10000.00")
        }
      ],
      shippingAddressSnapshot: { city: "Da Nang", district: "Hai Chau" },
      total: NumberDecimal("30000.00"),
      schemaVersion: NumberInt(1)
    }
  ]);

  events.insertMany([
    {
      _id: "e001", dataset: tag, tenantId: "shop-01",
      orderId: "o001", fromStatus: null, toStatus: "pending",
      occurredAt: ISODate("2026-02-01T09:00:00.000Z")
    },
    {
      _id: "e002", dataset: tag, tenantId: "shop-01",
      orderId: "o001", fromStatus: "pending", toStatus: "paid",
      occurredAt: ISODate("2026-02-01T09:15:00.000Z")
    },
    {
      _id: "e003", dataset: tag, tenantId: "shop-01",
      orderId: "o002", fromStatus: null, toStatus: "pending",
      occurredAt: ISODate("2026-02-02T10:00:00.000Z")
    },
    {
      _id: "e004", dataset: tag, tenantId: "shop-01",
      orderId: "o003", fromStatus: null, toStatus: "paid",
      occurredAt: ISODate("2026-02-03T08:00:00.000Z")
    },
    {
      _id: "e005", dataset: tag, tenantId: "shop-01",
      orderId: "o003", fromStatus: "paid", toStatus: "shipped",
      occurredAt: ISODate("2026-02-04T09:00:00.000Z")
    }
  ]);

  carts.insertOne({
    _id: "cart-c001", dataset: tag, tenantId: "shop-01",
    customerId: "c001",
    items: [
      { productId: "p001", quantity: NumberInt(1) }
    ],
    updatedAt: ISODate("2026-02-03T12:00:00.000Z")
  });

  // Indexes derived from read patterns and business rules.
  orders.createIndex(
    { tenantId: 1, customerId: 1, placedAt: -1, _id: -1 },
    { name: "ix_order_customer_history" }
  );
  orders.createIndex(
    { tenantId: 1, status: 1, placedAt: -1 },
    { name: "ix_order_status_queue" }
  );
  orders.createIndex(
    { tenantId: 1, orderNo: 1 },
    { name: "ux_order_number_per_tenant", unique: true }
  );
  products.createIndex(
    { tenantId: 1, category: 1, active: 1, price: 1 },
    { name: "ix_catalog_category_price" }
  );
  events.createIndex(
    { tenantId: 1, orderId: 1, occurredAt: 1, _id: 1 },
    { name: "ix_order_event_timeline" }
  );
  carts.createIndex(
    { tenantId: 1, customerId: 1 },
    { name: "ux_cart_customer", unique: true }
  );

  printjson({
    customers: customers.countDocuments({ dataset: tag }),
    products: products.countDocuments({ dataset: tag }),
    orders: orders.countDocuments({ dataset: tag }),
    events: events.countDocuments({ dataset: tag }),
    carts: carts.countDocuments({ dataset: tag })
  });
})();
~~~

**Expected result:** 2 customers, 3 products, 3 orders, 5 events, 1 cart. Re-running the entire block resets the lesson data to its initial logical state. The IDs and timestamps are fixed so results are easy to compare. This script cleans and inserts using multiple separate commands rather than a transaction; use only in a dedicated practice database.

## 7. Turning Access Patterns into Queries and Indexes

Indexes incur storage costs and update overhead on every write. Therefore, each index should correspond to one or more important queries. The following table maps the access patterns from Section 2 onto the structure just created:

| Access Pattern | Primary Query | Index to Consider |
| --- | --- | --- |
| AP1 – browse catalog | tenantId, category, active; sort price | tenantId + category + active + price |
| AP2 – order details | _id and tenantId | Default _id index; include tenantId in filter for scope protection |
| AP3 – customer order history | tenantId, customerId; sort placedAt and _id descending | tenantId + customerId + placedAt DESC + _id DESC |
| AP6 – processing queue | tenantId, status; sort placedAt descending | tenantId + status + placedAt DESC |
| Status history | tenantId, orderId; sort occurredAt ascending | tenantId + orderId + occurredAt ASC + _id ASC |
| Find customer cart | tenantId, customerId | Unique index on (tenantId, customerId) if each customer has only one active cart |

### 7.1. AP1: Browse Products

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  printjson(
    lab.getCollection("lab_products")
      .find(
        {
          dataset: "access-pattern-v1",
          tenantId: "shop-01",
          category: "stationery",
          active: true
        },
        { _id: 1, sku: 1, title: 1, price: 1 }
      )
      .sort({ price: 1 })
      .limit(20)
      .toArray()
  );
})();
~~~

The result returns `p002` (10,000 VND) followed by `p001` (40,000 VND). The projection retrieves only the fields needed for product cards; avoid loading every field if the screen does not need it.

### 7.2. AP2: Order Details

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  printjson(lab.getCollection("lab_orders").findOne({
    _id: "o001",
    tenantId: "shop-01",
    dataset: "access-pattern-v1"
  }));
})();
~~~

The result returns line items and snapshot prices along with the current status of `o001`. Using `_id` locates the document directly, but you still need to check `tenantId`/ownership from the authenticated context. A customer guessing an ID does not mean they are authorized to access the order.

### 7.3. AP3: Customer Order List

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  printjson(
    lab.getCollection("lab_orders")
      .find(
        {
          dataset: "access-pattern-v1",
          tenantId: "shop-01",
          customerId: "c001"
        },
        { _id: 1, orderNo: 1, status: 1, placedAt: 1, total: 1 }
      )
      .sort({ placedAt: -1, _id: -1 })
      .limit(20)
      .toArray()
  );
})();
~~~

The result is ordered **o002 then o001**. At large scale, use **cursor-based** pagination on the `(placedAt, _id)` pair to avoid the cost of skipping large numbers of documents with `skip`. For descending sort, the next page fetches records with `placedAt` less than the cursor, or the same `placedAt` with `_id` less than the cursor:

~~~javascript
// Illustrative cursor values taken from the last item of the previous page.
const cursorDate = ISODate("2026-02-02T10:00:00.000Z");
const cursorId = "o002";
const lab = db.getSiblingDB("mongo_access_lab");

lab.getCollection("lab_orders")
  .find({
    dataset: "access-pattern-v1",
    tenantId: "shop-01",
    customerId: "c001",
    $or: [
      { placedAt: { $lt: cursorDate } },
      { placedAt: cursorDate, _id: { $lt: cursorId } }
    ]
  })
  .sort({ placedAt: -1, _id: -1 })
  .limit(20)
  .toArray();
~~~

The result now contains only **o001**. When building a real API, the cursor must be bound to the authenticated filter and follow a clear encoding/decoding convention; this pagination approach does not provide an absolute snapshot if data is continuously inserted or modified.

### 7.4. AP6: Pending Orders Queue

~~~javascript
db.getSiblingDB("mongo_access_lab")
  .getCollection("lab_orders")
  .find(
    {
      dataset: "access-pattern-v1",
      tenantId: "shop-01",
      status: "pending"
    },
    { _id: 1, orderNo: 1, placedAt: 1, status: 1 }
  )
  .sort({ placedAt: -1 })
  .toArray();
~~~

The illustrative result is `o002`. Because `status` sits directly on Order, the list screen does not need to read all of `order_events` to derive the latest status.

### 7.5. View Status History of an Order

~~~javascript
db.getSiblingDB("mongo_access_lab")
  .getCollection("lab_order_events")
  .find(
    {
      dataset: "access-pattern-v1",
      tenantId: "shop-01",
      orderId: "o001"
    },
    { orderId: 1, fromStatus: 1, toStatus: 1, occurredAt: 1 }
  )
  .sort({ occurredAt: 1, _id: 1 })
  .toArray();
~~~

The result shows two events for `o001`: order created as `pending`, then transitioned to `paid`. This query is relatively infrequent compared to viewing order details, so there is no need to embed the full timeline on every Order fetch.

### 7.6. Reading explain to Verify Index Design

~~~javascript
db.getSiblingDB("mongo_access_lab")
  .getCollection("lab_orders")
  .find({
    tenantId: "shop-01",
    customerId: "c001"
  })
  .sort({ placedAt: -1, _id: -1 })
  .explain("executionStats");
~~~

When reading the output, inspect **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, and **nReturned**. With a tiny dataset of only three orders, MongoDB may choose a collection scan; that alone does not prove the index is wrong. You must evaluate with **representative data volume** and latency/resource measurements before drawing conclusions. When adding a new index, also verify its impact on write throughput and index size.

## 8. Write Frequency Shapes Update Patterns

### 8.1. Shopping Cart: Frequent Writes on a Small Document

A cart has few items, is usually accessed by `customerId`, and is updated per item. Embedding `items` makes single-document operations atomic.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  const result = lab.getCollection("lab_carts").updateOne(
    {
      _id: "cart-c001",
      tenantId: "shop-01",
      dataset: "access-pattern-v1",
      "items.productId": "p001"
    },
    {
      $inc: { "items.$.quantity": 1 },
      $currentDate: { updatedAt: true }
    }
  );
  printjson({ matched: result.matchedCount, modified: result.modifiedCount });
})();
~~~

Each execution increments the quantity of `p001` by one. The entire update executes on **a single document**, so it is atomic within that document's boundary. If two clients concurrently edit the same cart, the application still needs an appropriate conflict-handling rule; an atomic increment differs from overwriting the entire `items` array from a client's stale state.

Adding new items, merging two line items with duplicate `productId`, and enforcing a maximum total item count must also be designed to prevent duplicates or policy violations. When a cart becomes an order, prices, inventory, promotions, and product availability must be re-validated in the checkout flow; never blindly trust client-submitted prices.

### 8.2. Conditional Status Updates

To prevent two staff members from transitioning a status on stale data, status updates can use a condition on the previous status:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  const result = lab.getCollection("lab_orders").updateOne(
    {
      _id: "o002",
      tenantId: "shop-01",
      dataset: "access-pattern-v1",
      status: "pending"
    },
    {
      $set: {
        status: "paid",
        updatedAt: ISODate("2026-02-02T10:05:00.000Z")
      }
    }
  );
  printjson({ matched: result.matchedCount, modified: result.modifiedCount });
})();
~~~

On the first run, `matchedCount` is typically 1; on the next run it will be 0 because `status` is no longer `pending`. This is a form of **compare-and-set** on a single document. The result does not automatically write an audit event. If a requirement mandates that updating Order and inserting an OrderEvent document succeed or fail together, you must use a **multi-document transaction** on a supported MongoDB deployment or a purpose-built reliable event-publishing mechanism (such as an outbox). Never claim strict consistency when performing two independent write commands.

### 8.3. Read-Heavy and Write-Heavy Trade-offs Differ

**Read-heavy paths:** It can be worthwhile to keep frequently accessed data together in one document, add appropriate indexes and projections, or maintain a read-optimized summary view if there is a clear update strategy.

**Write-heavy paths:** Duplicating the same value in many places makes synchronization expensive. A document modified concurrently by many tasks can become a contention hotspot. Too many indexes also increase write costs because MongoDB must maintain every index structure.

For instance, adding **customerDisplayName** to every order helps the list screen avoid a lookup, but when a customer changes their name, the system must decide: is the name on an order an immutable snapshot or current information that must be synchronized? Those two meanings differ, and data duplication cannot be treated as an unconditional optimization.

## 9. Estimating Growth and Operational Cost

A model that works well at 10,000 documents can become difficult to operate at hundreds of millions of documents. Before finalizing embedding versus referencing, estimate:

~~~text
New documents/day
  = average creation rate (documents/second) × 86,400

Raw data size/day
  ≈ new documents/day × average BSON size

Actual operational storage
  = data + indexes + storage overhead
    + replication, backups, snapshots, logs...
~~~

Suppose an assumed system **sustains an average of 5 orders/sec all day**, and each Order has an average BSON size of 2 KiB:

- Orders/day: **432,000**.
- Raw Order BSON size/day: **about 844 MiB**.
- Over 30 days: **about 24.7 GiB of raw BSON**, excluding indexes, `order_events`, replication, backups, and other components.

The figure of 5 orders/sec here is a **sustained average**, not the `peakRps` value from the illustrative table. Do not take a short traffic spike and multiply it across the entire day without explicitly stating your assumptions.

If each order generates more events than anticipated, the `order_events` collection may grow faster than `orders`. If carts live only a few days, differing retention periods will yield different collection sizes. Therefore, you should estimate **creation rate**, **average size**, **growth over time**, **retention policy**, and **index footprint** for each collection.

### 9.1. When Size Forces a Model Change

- If an Order is allowed to contain tens of thousands of items, revisit order limits or split the structure to avoid approaching 16 MiB/document.
- If a Product has millions of comments, do not embed all comments into Product.
- If updates hit the same document too frequently, consider splitting write boundaries or redesigning the aggregate.
- If data is retained for many years while only the last 30 days are queried online, separate **hot/cold** storage strategies with clear synchronization and retrieval rules.

### 9.2. Sharding Is a Downstream Decision, Not a Fix for a Poor Model

When scaling out, evaluate the shard key based on **load distribution**, **queries containing the shard key**, **data growth rate**, and **uniqueness**. If all primary queries filter by `tenantId`, that field may play an important role in shard key evaluation, but an unusually large tenant can create imbalance. Do not pick a shard key merely because `tenantId` exists in every document.

Embedding an unbounded array or creating the wrong indexes does not become right just by adding sharding. You must control document size and access paths first, then select a data distribution strategy based on actual workload metrics.

## 10. Design Workflow from Workload to Collections

You can apply the following workflow to another business domain:

**Step 1 — Document critical access patterns.** For each screen, API, or background job, record the actor, filters, sort, projection, page size, frequency, and target latency. Distinguish interactive queries from background reports.

**Step 2 — Map write patterns.** Identify which entities are created/updated/deleted frequently, which fields are updated together, whether concurrent writers exist, and whether version or prior-state conditions are required.

**Step 3 — Sketch the lifecycle.** Define creation, states, growth bounds, retention period, which data requires auditing, and whether anonymization, deletion, or archiving is required.

**Step 4 — Choose document boundaries.** Place data read and updated together in one document when size and concurrency allow; separate independent, unbounded, or differently-lived data. You can combine embedded snapshots with references to the source.

**Step 5 — Finalize correctness rules.** Define IDs, BSON types, validation, unique constraints, transaction boundaries, update policies, and consistency rules for duplicated data.

**Step 6 — Design indexes from queries.** Start with equality filters, then range/sort conditions matching actual patterns, and verify with `explain`. Avoid indexing every field simply because it exists in the schema.

**Step 7 — Estimate growth.** Check document sizes, array bounds, event counts, index costs, retention, and data replicas. State assumptions for average and peak traffic.

**Step 8 — Measure and adjust.** Use production-like data to measure p95/p99, `nReturned`, `totalDocsExamined`, write latency, index size, and contention rates. Refine the model or indexes when evidence warrants it, while keeping a migration plan for legacy data.

There is no need to optimize every rare edge case by creating a giant document. What matters is knowing **which queries are prioritized, which decisions carry write costs, and what changes can occur across the data lifecycle**.

## 11. Common Modeling Mistakes

| Symptom | Root Cause | Recommended Approach |
| --- | --- | --- |
| Creating collections by simply mapping each entity/relational table 1:1 | Access patterns not analyzed | Document queries and fields read/written together first |
| Embedding all related information into one document | Optimizing only for current read count | Estimate size, update frequency, and child lifecycle |
| Storing all events in an array on Order | Unbounded growth not accounted for | Separate an event collection and keep current status on Order |
| Storing only productId in Order without purchase-time price | Failing to distinguish current data from historical snapshot | Embed `unitPrice`, `title`, and transaction fields that must be frozen |
| Copying customer name onto every order without defining semantics | Duplicated data lacks update rules | Choose immutable snapshot or current data with a sync workflow |
| Indexing every field | Write cost and storage footprint unmeasured | Tie indexes to specific queries and verify with `explain` |
| Using deep `skip` on history pages | Growth not considered | Use cursor pagination on a stable sort key where appropriate |
| Applying TTL to orders with retention obligations | Looking only at cleanup convenience | Classify retention, archiving, anonymization, and purging separately |
| Writing Order then writing Event and assuming both are always consistent | Transaction boundary ignored | Design a transaction or an appropriate outbox mechanism |
| Choosing a shard key by intuition | Lacking traffic, tenant skew, and query data | Measure traffic, hot keys, data distribution, and uniqueness |

## 12. Practice Exercises

### Exercise 1 — Designing a Small Social Network

A post can have millions of views, tens of thousands of comments, occasional edits by the author, and comments must be paginated chronologically. Write the access patterns for viewing a post, adding a comment, reading the 20 latest comments, and counting comments. Choose which fields should be embedded in `Post`, which belong in `Comments`, and how to maintain `commentCount` if fast display is required.

**Hint:** Comments grow without bound and have a separate read path; you should not embed all of them in `Post` by default. Storing the comment count on `Post` is aggregated data that requires a synchronization/reconciliation strategy.

### Exercise 2 — Online Learning Platform

A course has rarely changing metadata, many lessons, and each learner generates independent learning progress. Consider the queries: viewing the lesson list, opening lesson details, marking completion, and loading learner progress. If a course has thousands of lessons, how would you store `Lessons` and `LearnerProgress`? Which fields could be snapshots and which should not share a document?

**Hint:** Separate the lifecycle of course content from the lifecycle of per-learner progress; consider lesson list size and pagination needs.

### Exercise 3 — Load and Growth Analysis

Suppose a system creates an average of 20 orders/sec, and each order generates an average of 4 events; an average Order is 1.5 KiB, and an average Event is 0.5 KiB. Estimate the number of documents and raw BSON volume per day, then list additional components needed to estimate operational storage. What happens if all events are stored in an array on `Orders` and the number of events grows over time?

### Exercise 4 — Adapting the Model to a New Requirement

Starting from the lesson's sample dataset, add a requirement to display the "top 10 best-selling products in the last 30 days" every minute. Write the access pattern, identify the source data (`Order.items`), specify which order statuses are counted, and compare **direct aggregation** versus a **summary collection**. If creating a summary collection, describe how to detect stale or missing data and reconcile it.

### Exercise 5 — Choosing Expiration Strategies

Classify login sessions, abandoned carts, paid orders, audit data, and temporary export files under TTL, archive, anonymize, or delete. For each category, state a retention period under an assumed policy and explain why. Explain why a TTL index does not guarantee a session is rejected the instant its expiration time arrives.

### Exercise 6 — Checking Workload Before Adding Indexes

Write queries to view the 20 most recent orders for customer `c001` and all events for `o001` in the sample dataset. Map each query to the created indexes and use `explain("executionStats")` to inspect the plan. If adding a new index, state which query needs it and what write overhead must be accepted.

### Exercise 7 — Controlling Concurrent Writes

Two tasks simultaneously try to transition `o002` from `pending` to `paid`. Use a prior-status filter so only one valid operation can transition the state. Then explain why an additional consistency solution is needed if every state transition must also insert a unique `OrderEvent` in another collection.

---

When designing in MongoDB, keep this order of thinking: **query needs → read/write workload → lifecycle and growth → document boundaries → indexes and consistency rules → real-world measurement**. The same business relationship may warrant embedding, referencing, or a hybrid approach depending on how the data is used. A model's quality is not measured by having fewer or more collections, but by whether it serves critical operations well and remains stable as data evolves over time.
