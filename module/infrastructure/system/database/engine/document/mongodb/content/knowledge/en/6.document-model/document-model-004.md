# Document Boundaries, Data Cohesion, and Atomic Operations in MongoDB

In MongoDB, a **document** is not only the unit of BSON data storage, but also the **critical boundary of atomic write operations**. When designing a data model, deciding which fields belong in the same document directly impacts how the application reads data, preserves business invariants, handles concurrent updates, and scales.

For example, an order consists of a shipping address, line items, and a total amount. If all of this data resides in a single document, the application can update multiple order fields using **a single atomic write operation**. However, product inventory counts typically live in a separate document. Updating both the order and inventory concurrently therefore requires a different coordination mechanism, such as a transaction, a reservation model, or a resilient business workflow.

Three guiding questions run throughout MongoDB modeling:

1. **Document boundary:** Which data must be stored and updated as a single unit?
2. **Data cohesion:** Which information truly belongs to the same business entity and is usually used together?
3. **Atomicity:** Which changes must succeed or fail together, and do they fit completely inside a single document?

## 1. What Is a Document Boundary?

A document is a BSON value made up of field-value pairs, which may contain nested documents and arrays:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  status: "DRAFT",
  shippingAddress: {
    recipient: "Nguyen An",
    city: "Da Nang",
    street: "12 Nguyen Van Linh"
  },
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPrice: NumberDecimal("150000.00")
    }
  ],
  totalAmount: NumberDecimal("300000.00"),
  version: 1
}
~~~

Here, **shippingAddress** is a nested document inside the order document; **items** is an array of subdocuments. They are **not independent documents** in the collection when stored in this structure.

You can visualize it as:

~~~text
Database shop
└── Collection orders
    └── Document _id = "ORD-1001"       ← Atomic write boundary
        ├── customerId
        ├── status
        ├── shippingAddress
        │   ├── recipient
        │   ├── city
        │   └── street
        ├── items[]
        │   └── { sku, quantity, unitPrice }
        ├── totalAmount
        └── version

Collection products
└── Document _id = "BOOK-01"          ← Separate write boundary
    ├── title
    ├── price
    └── stock
~~~

A **document boundary** is the dividing line between data inside the same BSON document and data in another document. Whether two documents live in the same collection or two different collections, they still have separate atomic write boundaries.

### 1.1. Why Not Treat a Collection as an Atomic Unit?

A collection groups many documents and supports indexes, validation, and queries. However, a multi-document update command such as **updateMany** does not automatically become a single atomic transaction for the entire collection.

For example:

~~~javascript
db.products.updateMany(
  { category: "BOOK" },
  { $set: { featured: true } }
);
~~~

MongoDB guarantees atomicity **per individual document** updated by this command. There is no guarantee that all documents are modified simultaneously as one indivisible block. While the command is running, other operations may observe or interleave across multiple documents depending on the applicable isolation level.

Therefore, putting two pieces of data in **the same collection** does not give them a shared atomic boundary; to achieve atomicity in a single regular write, they must belong to **the same document**.

### 1.2. Logical Boundaries Are Not Physical Boundaries

Applications often refer to an object such as **Order**, **Customer**, or **ShoppingCart** as a business entity. MongoDB does not force each entity to correspond to exactly one document, nor does it automatically understand the business constraints of that entity.

For instance, one customer may have:

- One customer profile document.
- Many order documents.
- Many login activity documents.
- One or more session cart documents.

All of these relate to one customer, yet they should not necessarily all be crammed into the customer document. The decision must rest on business relationships, access patterns, data growth rates, and update needs.

## 2. Data Cohesion: Which Data Belongs Together?

**Data cohesion** in the document model is the degree to which related fields and data segments form **a meaningful unit of information**: describing the same concept, frequently read together, sharing a lifecycle, or needing to change uniformly.

High cohesion is usually a good signal for **embedding** (nesting data into a parent document). Low cohesion leans toward **referencing** (storing separately and linking by reference).

### 2.1. Semantic Cohesion

The shipping address at the time a customer places an order belongs to the **order** record, even though the customer also has an address in their profile.

If the customer updates their default address after ordering, the address on a confirmed order usually **must not change automatically**. Thus, storing a **shippingAddress snapshot** inside the order document makes semantic sense:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  shippingAddress: {
    recipient: "Nguyen An",
    city: "Da Nang",
    street: "12 Nguyen Van Linh"
  }
}
~~~

Meanwhile, the product catalog can change independently:

~~~javascript
{
  _id: "BOOK-01",
  title: "Introduction to MongoDB",
  currentPrice: NumberDecimal("180000.00"),
  stock: 20
}
~~~

The order can embed **title and price at purchase time** inside each line item to preserve history, while the product in the catalog remains a separate document. This is **intentional data duplication** driven by business semantics, not necessarily a design flaw.

### 2.2. Cohesion by Read Pattern

If a screen always needs an article title, author display name, and a few category tags, embedding a small subset of fields allows a single document read to suffice.

Conversely, if the application frequently displays a product list with only ID, name, and price, yet embeds the entire review history inside each product document, reads can drag along unnecessary data.

Two practical questions:

- **Does the application usually read these fields together?**
- **When returning a subset of data, does the parent document become too large or too hot because of the remaining parts?**

Keep in mind that MongoDB has projections to select only returned fields. However, projection alone does not make embedding an unbounded array a good design; document size, updates, and memory usage must still be weighed.

### 2.3. Cohesion by Lifecycle

An order's shipping address is usually created and retained along with the order. Line items in an order are also typically managed according to order status.

Conversely:

- **Product** exists before and after many orders.
- **Customer** exists independently of individual orders.
- **Payment** may have its own lifecycle, audit logs, and access policies.
- **Event log** may continue growing long after the main entity stops changing.

Data with an independent lifecycle fits separate documents more naturally, especially when it needs different search, permission, archiving, or deletion rules.

### 2.4. Cohesion by Consistency Conditions

Sometimes the need for **atomic updates** dictates document boundaries even more strongly than co-read patterns.

For example, order status and **totalAmount** must stay consistent with line items. If the application updates line items and total amount in a single document update operation, there is never a point where the stored document reflects only half of that write.

This does not mean MongoDB calculates the total accurately on its own: **atomicity guarantees all changes in a single write are applied as one unit; correctness of the calculation remains the responsibility of application logic**.

## 3. Embedded Documents and References: Two Ways to Draw Boundaries

MongoDB lets you model relationships by embedding data or referencing between documents. Both are valid; what matters is choosing based on how the data is used.

### 3.1. Embedding: Data Lives in the Same Document

~~~javascript
{
  _id: "ORD-1001",
  status: "DRAFT",
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 150000 },
    { sku: "PEN-02", quantity: 1, unitPrice: 10000 }
  ],
  totalAmount: 310000
}
~~~

Advantages:

- Can read the order and line items from one document.
- Can update multiple fields and array elements of the document in **one atomic write**.
- No join across two collections needed to assemble basic order details.
- Clear ownership boundary when child data only has meaning inside the parent document.

Costs and limits:

- Document grows as elements are added to arrays.
- Concurrent writers updating different parts of the same document may contend on the same resource.
- Duplicated data across documents may need business-driven maintenance.
- Regular BSON documents are capped at **16 MiB**.

**Embedding does not mean embedding every relationship.** An unbounded event history array will eventually become a burden even though semantically all events relate to the same object.

### 3.2. Referencing: Data Lives in Separate Documents

~~~javascript
// Collection orders
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  status: "DRAFT"
}

// Collection orderItems
{
  _id: "LINE-1",
  orderId: "ORD-1001",
  sku: "BOOK-01",
  quantity: 2,
  unitPrice: 150000
}

// Collection products
{
  _id: "BOOK-01",
  title: "Introduction to MongoDB",
  stock: 20
}
~~~

Advantages:

- Each entity can grow or be updated independently.
- Documents stay smaller when related element counts are large.
- Convenient when one object is referenced from many places.
- Indexes, permissions, and retention policies can be tailored per collection.

Costs:

- To display an order with all line items, the application needs multiple queries or an aggregation like **$lookup**.
- A business change spanning multiple documents is not automatically atomic.
- References and orphan data must be managed by design; MongoDB does not automatically turn an **orderId** field into a SQL-enforced foreign key.

### 3.3. Model Selection Table

| Criterion | Favors Embedding | Favors Referencing |
| --- | --- | --- |
| Read frequency | Parts are usually read together | Parts are usually read separately |
| Lifecycle | Child data is owned by the parent document | Child data lives and changes independently |
| Element count | Small or reasonably bounded | Very large, no clear upper bound |
| Atomicity needs | Multiple fields must update in one write | Multi-document coordination is acceptable |
| Write frequency | Updated as one business entity | Parts are written independently and frequently |
| Duplication | Embedded data is stable or a snapshot | Shared data must stay currently synchronized |
| Independent queries | Child data rarely queried alone | Need to filter, paginate, or aggregate children independently |

A system often combines both: embedding **items** and **shippingAddress** inside the order, while referencing **customerId**, **productId**, or **paymentId**.

## 4. Atomicity of a Single-Document Write Operation

**Atomicity** means a write operation is applied **completely or not at all** with respect to the atomic unit supported by the system. MongoDB provides atomicity for **a single write operation on a single document**, even when that operation modifies multiple fields or nested components.

Initial document example:

~~~javascript
{
  _id: "ORD-1001",
  status: "DRAFT",
  totalAmount: NumberDecimal("300000.00"),
  itemCount: 2,
  version: 1
}
~~~

A single update operation can modify all three fields:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $inc: {
      totalAmount: NumberDecimal("15000.00"),
      itemCount: 1,
      version: 1
    },
    $set: {
      updatedAt: new Date()
    }
  }
);
~~~

If the operation applies to the matching document, all changes in that operation execute atomically at the document level. There is no intermediate stored state where **itemCount** has increased while **totalAmount** has not from that update.

However, if the application miscalculates the increment amount or forgets to update the corresponding line item, MongoDB will still atomically apply a **business-incorrect** change. Atomicity and logical correctness are two distinct properties.

### 4.1. One Operation Can Modify Multiple Fields

A single **updateOne** command can combine appropriate operators such as:

| Operator | Purpose | Example |
| --- | --- | --- |
| **$set** | Assign or create a field | Change order status |
| **$inc** | Increment/decrement numeric value | Decrement stock, increment version |
| **$unset** | Remove a field | Clear temporary data |
| **$push** | Append element to an array | Add a line item |
| **$pull** | Remove matching elements from an array | Remove a product from cart |
| **$addToSet** | Add value if not already present in array | Add label/tag |
| **$setOnInsert** | Assign field only when upsert inserts | Set initial metadata |

Example adding an item and updating total amount in one write:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $push: {
      items: {
        sku: "PEN-02",
        quantity: 1,
        unitPrice: NumberDecimal("15000.00")
      }
    },
    $inc: {
      totalAmount: NumberDecimal("15000.00"),
      version: 1
    }
  }
);
~~~

Both **items** and **totalAmount** belong to the order document, so the changes execute atomically. This assumes **items** is already an array, **totalAmount** is an appropriate number, and pricing has been validated by the application.

### 4.2. Atomicity Does Not Make Multiple Commands Indivisible

Two separate update operations, even targeting the same document, remain **two separate atomic operations**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  { $set: { status: "CONFIRMED" } }
);

db.orders.updateOne(
  { _id: "ORD-1001" },
  { $set: { confirmedAt: new Date() } }
);
~~~

If the first operation succeeds and the second fails, the document can end up in state **CONFIRMED** without **confirmedAt**.

When two fields must change together, place them in **a single write**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);
~~~

The second command includes **status: "DRAFT"** to prevent re-confirming an order that has already transitioned. The application must still check the matched count before assuming confirmation occurred.

### 4.3. One Write, Many Documents: Each Document Is Atomic Individually

~~~javascript
db.orders.updateMany(
  { status: "EXPIRED" },
  { $set: { archived: true } }
);
~~~

MongoDB can update multiple documents, yet the operation has **no collective all-or-nothing atomicity** when run outside a multi-document transaction. Mid-execution, some orders may already be updated while others are not yet updated.

Similarly:

- **insertMany** is not automatically a multi-document transaction.
- **bulkWrite** does not automatically turn every operation in a batch into a single atomic block.
- A loop calling **updateOne** repeatedly is not atomic like a single write.

If an entire group of documents must commit or roll back together, evaluate **multi-document transactions** and compatible deployment requirements.

## 5. Concurrent Updates: Atomic Yet Potentially Business-Incorrect

Single-document atomicity does not automatically solve every bug caused by concurrent users or services updating data.

### 5.1. Lost Update Case with $set

Suppose current inventory is 10. Two requests both read 10, compute 9 locally, and both write:

~~~javascript
db.products.updateOne(
  { _id: "BOOK-01" },
  { $set: { stock: 9 } }
);
~~~

Each write is atomic. Yet the final result can be **9** instead of **8**, because both requests wrote an absolute value derived from the same stale state.

This demonstrates that **atomic writes do not prevent lost updates when the application reads and writes back based on stale values**.

### 5.2. Use $inc for Relative Changes

If business logic only needs to subtract one unit of inventory, use a relative increment/decrement operator directly:

~~~javascript
db.products.updateOne(
  { _id: "BOOK-01" },
  { $inc: { stock: -1 } }
);
~~~

Two successful decrements on the same document apply each operation's relative change, rather than overwriting with a precomputed 9.

However, if inventory could drop below zero, **$inc** alone is insufficient. You must put the business constraint in the update filter.

### 5.3. Conditional Update Prevents Overselling

~~~javascript
const result = db.products.updateOne(
  {
    _id: "BOOK-01",
    stock: { $gte: 2 }
  },
  {
    $inc: { stock: -2 }
  }
);

if (result.modifiedCount === 1) {
  print("Reserved/deducted 2 units in inventory document");
} else {
  print("Not updated: document not found or insufficient stock");
}
~~~

The **stock >= 2** condition is evaluated atomically with the document update. Competing requests trying to deduct inventory cannot simultaneously rely on the same stale count and drive stock negative from client-side math.

This protects the **non-negative inventory invariant of a single product document** when all write paths obey the same rule. It does not guarantee that creating an order document in another collection succeeds alongside deducting inventory.

### 5.4. Optimistic Concurrency with a Version Field

When updates depend on previously read data and conflicts must be detected, store a **version** field.

Initial document:

~~~javascript
{
  _id: "ORD-1001",
  status: "DRAFT",
  shippingAddress: { city: "Hanoi" },
  version: 7
}
~~~

Client A reads **version = 7**. Client B may have modified the document before A writes. Client A updates only if `version` is still 7:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ORD-1001",
    version: 7
  },
  {
    $set: {
      "shippingAddress.city": "Da Nang"
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  print("Data has changed or document no longer exists");
}
~~~

If another valid update has already bumped `version` to 8, the filter fails to match. The application must reload, merge changes, or report a conflict instead of blindly overwriting.

The version strategy works when **all relevant writers update the version**. Any service modifying data while skipping `version` breaks the safeguard.

### 5.5. Atomicity Does Not Replace Write Concern and Read Concern

Three distinct concepts:

- **Atomicity:** a write operation on a document is never applied halfway.
- **Write concern:** the level of write acknowledgment the client requests from the deployment, affecting durability/recovery expectations.
- **Read concern:** the consistency and data visibility guarantees for read operations.

An atomic write does not automatically mean every client immediately sees it on any secondary, or that the write was acknowledged by a majority. Those depend on read/write concern configuration, replication, and read timing.

## 6. Business Invariants and Atomic Boundaries

A **business invariant** is a condition that must hold true whenever the system requires it, for example:

- Product inventory is never negative.
- Order total matches line items per the chosen calculation rules.
- An order transitions from **DRAFT** to **CONFIRMED** at most once.
- An account cannot withdraw more than its available balance.
- Both ledger entries of a funds transfer must be recorded together.

If all data needed to enforce an invariant lives in **one document**, MongoDB lets you check conditions and modify the document with a single atomic update.

Order status example:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "DRAFT"
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);
~~~

Atomicity ensures status and timestamp change together; the **status: "DRAFT"** predicate protects the state transition rule.

If an invariant spans **two documents**, a single-document atomic update cannot guarantee both update together. For example:

~~~text
Product document:
  stock must decrease by 2

Order document:
  order must be created exactly once
~~~

Deducting stock successfully while failing to insert the order causes discrepancy. Conversely, creating the order first and failing to deduct stock creates an unfulfillable order.

Depending on business needs, you can use transactions, shift to a reservation model, use stateful workflows with compensation, or redesign storage boundaries so critical invariants live within one document. No single choice fits every system.

## 7. Design Example: Orders, Carts, and Inventory

### 7.1. A Highly Cohesive Order Document

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  status: "DRAFT",
  items: [
    {
      sku: "BOOK-01",
      titleSnapshot: "Introduction to MongoDB",
      quantity: 2,
      unitPrice: NumberDecimal("150000.00"),
      lineTotal: NumberDecimal("300000.00")
    },
    {
      sku: "PEN-02",
      titleSnapshot: "Note Pen",
      quantity: 1,
      unitPrice: NumberDecimal("10000.00"),
      lineTotal: NumberDecimal("10000.00")
    }
  ],
  shippingAddress: {
    recipient: "Nguyen An",
    city: "Da Nang",
    street: "12 Nguyen Van Linh"
  },
  totalAmount: NumberDecimal("310000.00"),
  version: 1,
  createdAt: ISODate("2025-01-15T10:00:00Z")
}
~~~

These parts are highly cohesive:

- **items** describes the order contents at transaction time.
- **titleSnapshot** and **unitPrice** are historical data preserved even if the catalog changes.
- **shippingAddress** is the delivery destination for this specific order.
- **status**, **totalAmount**, and **version** represent the consistent state of the order.

Changes across multiple order fields can be applied in one atomic update. A single order document with a reasonable number of line items is usually easy to operate.

### 7.2. Inventory Lives in a Separate Document

~~~javascript
{
  _id: "BOOK-01",
  title: "Introduction to MongoDB",
  stock: 20,
  currentPrice: NumberDecimal("180000.00")
}
~~~

A product is bought by many customers and has a lifecycle independent of any individual order. Hence inventory cannot be treated as a field "belonging solely" to any single order.

You can deduct stock using a conditional update, but simultaneously creating an order document modifies **two documents**. If the system requires both changes to commit or roll back together, you need a transaction or an alternative business design offering equivalent guarantees.

### 7.3. Shopping Carts and Growth Order

An active shopping cart usually holds a small number of items and has a limited lifespan; embedding enables updating cart contents in a single document.

However, the history of **every product addition and removal by a customer over many years** is unbounded. Storing that entire history in an array inside the cart document bloats the document and creates write contention. Activity history usually belongs in a separate events collection with TTL/retention and indexes aligned with usage.

The distinction is not "the cart relates to the customer while logs do not." Both relate to the customer; however, **an active cart has high cohesion and bounded size**, while **logs have a distinct lifecycle and growth rate**.

## 8. When Do You Need Multi-Document Transactions?

MongoDB supports **multi-document transactions** on supported deployments, such as replica sets and sharded clusters. Inside a transaction, operations across multiple documents can commit or abort together.

Order creation and inventory deduction example:

~~~text
BEGIN TRANSACTION
  1. Deduct 2 units of BOOK-01 if stock >= 2.
  2. Create a new order referencing BOOK-01.
COMMIT
~~~

If any step fails and aborts the transaction, changes within the transaction are not partially committed.

### 8.1. Node.js Driver Example

The example below illustrates a transaction across two documents in the same database on a MongoDB deployment supporting transactions:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function createOrder() {
  await client.connect();

  const session = client.startSession();

  try {
    const db = client.db("shop");
    const products = db.collection("products");
    const orders = db.collection("orders");

    await session.withTransaction(async () => {
      const stockResult = await products.updateOne(
        {
          _id: "BOOK-01",
          stock: { $gte: 2 }
        },
        {
          $inc: { stock: -2 }
        },
        { session }
      );

      if (stockResult.modifiedCount !== 1) {
        throw new Error("Insufficient stock or product does not exist");
      }

      await orders.insertOne(
        {
          _id: "ORD-1001",
          productId: "BOOK-01",
          quantity: 2,
          status: "CONFIRMED",
          createdAt: new Date()
        },
        { session }
      );
    });

    console.log("Committed order and inventory update");
  } finally {
    await session.endSession();
    await client.close();
  }
}

createOrder().catch(console.error);
~~~

Prerequisites for this example:

- The driver connects to a **replica set or sharded cluster** supporting transactions; a standalone `mongod` is not suitable for running this transaction example.
- The **products** document has **_id: "BOOK-01"** and a numeric **stock** field.
- The **orders** document does not yet contain **_id: "ORD-1001"**.
- The example uses a fixed ID for illustration; re-running requires idempotency handling and real ordering workflows.

The **withTransaction** callback may be retried by the driver on certain transient errors. Do not place non-rollbackable side effects, such as sending notification emails or calling payment gateways, inside the callback without deduplication protection. Transaction commits only cover database operations participating in the transaction.

### 8.2. Do Transactions Replace Good Document Modeling?

Transactions are useful, yet they introduce coordination overhead, resource consumption, retry logic, timeouts, and potential write conflicts. Nor do they automatically fix poor storage, query, or growth designs.

If an invariant naturally belongs to **one small, cohesive entity**, placing the data in the same document and using a single atomic update is usually simpler. When business logic genuinely spans multiple independent objects, transactions are an appropriate tool.

Large-scale systems may also opt for asynchronous flows, outboxes, and compensating actions. These approaches require explicitly defining **eventual consistency**, intermediate states, and recovery mechanisms—never try to replace transactions simply by running multiple commands and hoping all succeed.

### 8.3. Distinguish Transactions from Read/Write Concern

Transactions have their own snapshot and commit semantics; durability and result visibility are still influenced by read concern, write concern, and cluster configuration. Do not assume that merely using a transaction guarantees all non-transactional reads immediately observe the exact same state across every secondary.

## 9. Document Size Limits and Growth Rate

MongoDB caps a regular BSON document at **16 MiB**. However, a document being under 16 MiB does not mean an embedded model is good.

### 9.1. Unbounded Arrays Are a Warning Sign

Example embedding every login event:

~~~javascript
{
  _id: "CUS-101",
  fullName: "Nguyen An",
  loginEvents: [
    { at: ISODate("2025-01-01T10:00:00Z"), ip: "192.0.2.10" },
    { at: ISODate("2025-01-02T10:00:00Z"), ip: "192.0.2.11" }
    // Keeps growing over time...
  ]
}
~~~

If the application appends on every login, this array has no natural bound. Over years, the document can grow huge, update and transfer costs climb, and concurrent writers contend on the customer document.

An alternative storage layout:

~~~javascript
// Collection customers
{
  _id: "CUS-101",
  fullName: "Nguyen An"
}

// Collection loginEvents
{
  _id: ObjectId(),
  customerId: "CUS-101",
  at: new Date(),
  ip: "192.0.2.10"
}
~~~

You can create an index on **customerId, at** to filter and paginate history. Event lifecycles can then be managed separately from the customer profile document.

### 9.2. Bounded Arrays and the Subset Pattern

If you only need to keep **the three most recent addresses** or **the ten latest activities**, you can embed a bounded subset:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $push: {
      recentActivities: {
        $each: [
          { type: "LOGIN", at: new Date() }
        ],
        $slice: -10
      }
    }
  }
);
~~~

The example above keeps the **last 10 elements** in **recentActivities**, assuming insertion order matches the desired order. Full history, if needed, can live in another collection.

Bounded arrays fit well when limits are explicit and updating a single document meets requirements. However, **$slice** does not make external standalone activity documents part of an atomic operation with the customer document.

### 9.3. Write Hotspots and Single-Document Contention

A document holding a shared counter can become a **hot document** if thousands of requests update it concurrently. Each update remains atomic, yet write contention can degrade throughput and latency.

Example of a system-wide counter:

~~~javascript
db.counters.updateOne(
  { _id: "global-page-views" },
  { $inc: { value: 1 } }
);
~~~

This design is simple but creates a single write bottleneck. Depending on requirements, the application can shard the counter, batch increments, or compute totals from an event stream. Once split, accept that **totals across multiple documents are no longer updated by a single atomic write**.

## 10. Reading Data, Updating Data, and Consistency Scope

Document boundaries determine write atomicity, while queries may span multiple documents.

### 10.1. Reading One Document

~~~javascript
db.orders.findOne(
  { _id: "ORD-1001" },
  { _id: 1, status: 1, items: 1, totalAmount: 1 }
);
~~~

If **items** and **totalAmount** are in the same document, the application retrieves those fields from the same queried document.

However, if the application executes **two separate read commands** at two points in time, data may have changed between the two commands. Atomicity does not create a snapshot spanning multiple independent queries.

### 10.2. Updating a Nested Field with Dot Notation

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      "shippingAddress.city": "Hue"
    }
  }
);
~~~

This command updates the nested **city** field while preserving other fields inside **shippingAddress**.

By contrast:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      shippingAddress: { city: "Hue" }
    }
  }
);
~~~

The latter **replaces the entire shippingAddress field** with a document containing only **city**. It is still an atomic update, yet it wipes out **recipient** and **street**. Therefore, atomicity does not mean "preserving fields the developer forgot about"; the exact behavior of operators must be understood.

### 10.3. Arrays and Positional Updates

Suppose an order contains:

~~~javascript
{
  _id: "ORD-1001",
  items: [
    { sku: "BOOK-01", quantity: 2 },
    { sku: "PEN-02", quantity: 1 }
  ]
}
~~~

You can update the quantity of matching elements using an array filter:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $inc: {
      "items.$[item].quantity": 1
    }
  },
  {
    arrayFilters: [
      { "item.sku": "BOOK-01" }
    ]
  }
);
~~~

Even though a field inside an array element is modified, the operation still writes to **the single document ORD-1001**. If both **quantity** and **totalAmount** need updating, combine the appropriate operators in one update, provided total calculation logic is sound.

Note that if the array contains multiple elements with the same **sku**, `arrayFilters` can affect multiple elements in that document. The invariant "each sku appears at most once in items" must still be enforced by schema and business logic.

## 11. Aggregate-Driven Design and Consistency

In Domain-Driven Design, an **aggregate** is a cluster of objects with a boundary that enforces business invariants and acts as a single change-coordination point. A MongoDB document can store a small aggregate, though the two concepts are **not strictly identical**.

For example, an **Order aggregate** has:

~~~text
Order
├── orderId
├── customerId
├── status
├── shippingAddress
├── items[]
└── totalAmount
~~~

If Order's rules can be validated and updated completely inside one document, a document is a reasonable boundary.

However, an overly large aggregate may be unsuitable for embedding due to size limits or write contention. Conversely, two independent business aggregates should not be merged into one document just to avoid transactions if doing so distorts data lifecycles or access patterns.

### 11.1. Distinguish Local Invariants from Cross-Entity Invariants

| Invariant Type | Example | Appropriate Boundary |
| --- | --- | --- |
| Local to one order | Status and confirmedAt must change together | One Order document |
| Local to one product | Stock never goes negative | One Product document with conditional update |
| Cross-entity | Create Order and decrement Product stock together | Multi-document transaction or coordinated workflow |
| Cross-system | Charge payment gateway and confirm order | Idempotent workflow, state machine, and recovery beyond a single MongoDB transaction |
| Event history | Every event must be stored and queried by time | Separate event collection or appropriate log architecture |

This table helps avoid a common mistake: demanding "every change must be atomic" without specifying **which invariant must be protected**. Not all related data has to change inside the same transaction.

### 11.2. Snapshots vs. Live Referenced Data

An order should preserve **unitPrice at purchase time**. This is a snapshot cohesive with the order. When catalog product prices change, the snapshot should not be updated along with them.

By contrast, if an admin screen needs to show **current product availability**, referencing the product document is appropriate rather than expecting an order snapshot to reflect live data.

Distinguishing **historical snapshots** from **live data** clarifies whether a value should be copied into a document.

## 12. Contrasting Two Design Models

Suppose you are building a classroom management feature. A class has a name, teacher, student roster, attendance records, assignments, and all submissions.

### Model A: Embed Everything in One Document

~~~javascript
{
  _id: "CLASS-01",
  name: "MongoDB Basics",
  teacherId: "T-01",
  students: [ /* hundreds of students */ ],
  attendances: [ /* thousands of records */ ],
  submissions: [ /* tens of thousands of submissions */ ]
}
~~~

This model groups topically related parts into one document, but easily causes problems:

- Arrays grow continuously and can hit the 16 MiB limit.
- Many students submitting simultaneously create write contention on the single class document.
- Querying attendance per student or submissions by date is awkward.
- Updating one submission should not create hotspot contention on the entire class document.

Even though keeping many fields in one document gives atomic updates, **business cohesion is weaker than the breadth of the chosen boundary**.

### Model B: Separate Independent Lifecycles

~~~text
classes
  { _id, name, teacherId, settings }

enrollments
  { _id, classId, studentId, enrolledAt, status }

attendances
  { _id, classId, studentId, sessionDate, present }

submissions
  { _id, classId, assignmentId, studentId, submittedAt, grade }
~~~

With Model B:

- Class metadata stays compact and changes rarely.
- Each attendance/submission can be updated independently.
- Indexes can be created on **classId, studentId, sessionDate** and independent query paths.
- When a workflow modifies multiple documents, the system chooses an appropriate consistency mechanism.

You can embed a **small summary** in the class document, such as current student count, if accessed frequently. That embedded count needs a strategy to stay consistent with `enrollments`, either via transactions or an accepted aggregation workflow.

Key point: **draw boundaries by ownership, lifecycle, access patterns, and invariants**, not simply because data shares a topic.

## 13. Process for Deciding Document Boundaries

When designing a new MongoDB model, follow this sequence.

### Step 1: Identify Real Business Operations

For an ordering system:

- View details of an order.
- Add/remove line items before confirmation.
- Confirm an order.
- Deduct product stock.
- Record payment.
- Filter orders by customer and date range.

Do not merely list entities; understand **the most frequent read/write paths**.

### Step 2: State Invariants Explicitly

For example:

- Confirmed orders cannot have line items edited via the regular cart API.
- Order total must match the calculation rule over `items`.
- Stock cannot go negative.
- A placement request with an idempotency key must not create two orders.

Invariants confined to one order document are prime candidates for atomic updates. Invariants spanning products, payments, or multiple orders require broader boundaries.

### Step 3: Group Cohesive Data

Group by:

- Co-read together.
- Shared lifecycle.
- Clear ownership.
- Modified together in one operation.
- Bounded growth.

Shipping address snapshot, line items, and order status are typically cohesive. Customer profiles, catalogs, and independent transaction logs usually belong in references.

### Step 4: Check Size and Write Contention

Estimate current and peak array element counts; check for unbounded growth. Check whether a document could become a hotspot under concurrent writers.

MongoDB caps documents at 16 MiB, yet applications should design with a **safety margin** rather than waiting until hitting the limit to split data.

### Step 5: Choose Consistency Mechanisms

| Requirement | Common Approach |
| --- | --- |
| Modify multiple fields in one document | A single **updateOne/findOneAndUpdate** with appropriate filter |
| Increment/decrement without read-modify-write | **$inc** |
| Prevent overwriting stale versions | Filter on **version** and increment version |
| Keep stock non-negative | Filter **stock: { $gte: n }** with **$inc** |
| Update multiple documents atomically together | **Multi-document transaction** |
| Coordinate with external services | Stateful workflow, idempotency, and failure handling |
| Unbounded data history | Separate collection or bounded subset design |

### Step 6: Re-evaluate as Workload Evolves

An initial design may work at a few thousand documents yet break down when an array reaches millions of elements or one document takes thousands of writes per second. Measure and adjust the model when access patterns, scale, or invariants change.

## 14. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| All documents in the same collection update atomically together | MongoDB by default guarantees atomicity **per document**, not per collection |
| Putting data in the same database ensures consistency | A database is a logical namespace, not an atomic write boundary |
| An embedded document is an independent document | It is a nested structure inside the parent BSON document, sharing its atomic boundary |
| A single write updating multiple fields can save half the changes | A single-document write is applied atomically |
| Two consecutive `updateOne` calls automatically form a transaction | Each update is an independent operation outside a transaction |
| `$set` is atomic so lost updates cannot happen | Two writers can overwrite values computed from stale reads; use `$inc` or version/condition filters |
| `updateMany` is a transaction because it is one API call | Each document is atomic individually; there is no all-or-nothing guarantee across the set outside a transaction |
| Embedding every relationship makes the system faster | Unbounded arrays, hotspots, and oversized documents cause serious issues |
| Separating collections always forces using transactions | Transactions are only needed when business rules require changes to commit/roll back together |
| MongoDB transactions cover external payments or emails | Transactions only govern database operations participating in them |
| Any document under 16 MiB is automatically well designed | You must also evaluate growth rate, queries, contention, and lifecycle |
| Atomicity means MongoDB enforces all business rules automatically | Calculation logic, update predicates, and validation must still be designed properly |
| Embedding purchase-time price is bad data duplication | Historical snapshots are usually an intentional choice |

## 15. Practice Lab: Building an Order Model with Atomic Updates

This section uses **mongosh** and the lab database **document_boundary_lab**. Independent commands can be run in order. Numbers and IDs are illustrative only.

### Exercise 1: Create an Order Document

~~~javascript
use document_boundary_lab

db.orders.insertOne({
  _id: "ORD-1001",
  status: "DRAFT",
  items: [
    {
      sku: "BOOK-01",
      quantity: 1,
      unitPrice: NumberDecimal("100000.00")
    }
  ],
  totalAmount: NumberDecimal("100000.00"),
  version: 1
});
~~~

Identify:

- Where is the atomic boundary?
- Is **items[0]** an independent document in another collection?
- Which fields can change together in one update operation?

### Exercise 2: Add an Item and Increment Total Atomically

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $push: {
      items: {
        sku: "PEN-02",
        quantity: 2,
        unitPrice: NumberDecimal("10000.00")
      }
    },
    $inc: {
      totalAmount: NumberDecimal("20000.00"),
      version: 1
    }
  }
);

db.orders.findOne({ _id: "ORD-1001" });
~~~

Expected result after a successful update on the document from Exercise 1:

~~~text
items has 2 line items
totalAmount = 120000.00
version = 2
~~~

Explain why changes on the same document belong to one atomic write, and in what scenario the total amount could still be wrong even though the write executed atomically.

### Exercise 3: Conditional Order Confirmation

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "DRAFT",
    version: 2
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);

printjson(result);
~~~

Re-run the exact same update command with filter **status: "DRAFT", version: 2**. The second run will no longer match the confirmed document. Use **matchedCount** to distinguish "no matching document" from "confirmed successfully."

### Exercise 4: Inventory Is a Separate Boundary

~~~javascript
db.products.insertOne({
  _id: "BOOK-01",
  title: "Introduction to MongoDB",
  stock: 3
});

db.products.updateOne(
  { _id: "BOOK-01", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
);
~~~

Now answer:

1. Why are **Product** and **Order** two documents with two separate atomicity boundaries?
2. If deducting stock succeeds while confirming the order fails, what state can the system end up in?
3. When should you consider a transaction, and when is a reservation plus asynchronous processing more appropriate?
4. If the application reads inventory and uses **$set** with a precomputed value, what lost update can occur?
5. If every stock change history entry is appended to an array on Product, what growth risks can arise?

### Exercise 5: Make Your Own Modeling Decision

Consider a chat application:

~~~text
Conversation
  ├── title
  ├── participants
  ├── messages (continuously growing)
  └── lastMessagePreview
~~~

Decide which parts should be embedded and which should live in a separate collection:

- **participants**: is the count bounded or unbounded, and does it change with the conversation or independently?
- **messages**: does it grow without bound, and does it need chronological pagination?
- **lastMessagePreview**: does it need fast display in the conversation list, and how is it maintained?
- **unreadCount**: counted per conversation or per participant; is the atomic boundary sufficient to update it?

One viable option is storing **messages** in a separate collection, keeping conversation metadata compact, and designing preview/counter updates to match the required consistency level. The final decision depends on real scale and usage behavior.

## References

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Embedded Data versus References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — BSON Document Size Limit](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
