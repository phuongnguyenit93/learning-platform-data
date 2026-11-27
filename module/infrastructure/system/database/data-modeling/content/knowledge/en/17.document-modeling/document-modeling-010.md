# Translating a Relational Order Model to a Document Model and Comparing Trade-offs

## Learning Objectives

After this lesson, you will be able to:

- Identify the **aggregate boundary** of an order before deciding whether to embed or reference data in a document model.
- Translate a relational schema containing orders, line items, products, customers, and shipping into a document structure serving **concrete access patterns**.
- Distinguish **facts locked in at transaction time** from current product catalog or customer profile attributes.
- Design identifier keys, indexes, versioning, single-document atomic updates, and consistency contracts across multiple documents or services.
- Evaluate read cost, write cost, document growth, multi-dimensional search, correctness controls, schema changes, and migration.
- Write an evidence-backed comparison across relational, document, and hybrid options instead of claiming one model is always superior.

This lesson belongs to the **Document Modeling** chapter of **DATABASE_DATA_MODELING**. The module's goal is turning business requirements into clear data models—from entities, relationships, and constraints to keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical data organizations. Examples use **PostgreSQL** for the relational model and **MongoDB/mongosh** syntax to illustrate the document model. Specific choices must be verified against your target database version and real workload.

## 1. Start from Business Behavior, Not from JSON

Suppose an e-commerce platform must support:

1. Customers build a cart and confirm an order containing multiple product lines.
2. On confirmation, the system **locks in product names, unit prices, quantities, and the shipping address**.
3. Customers open an order detail view and retrieve all line items in **a single API call**.
4. Customers browse their 20 most recent orders, needing only date, status, and grand total.
5. Fulfillment may split an order into multiple shipments; shipment statuses and tracking events change continuously.
6. Payment processing records multiple payment attempts, refunds, and provider webhooks.
7. Analytics queries revenue by product, category, date, and status.

Looking only at requirement 3 makes embedding everything into the **order** document tempting. Yet requirements 5–7 indicate that several subsets have completely different lifecycles, growth rates, write ownership, and query shapes.

**The most important design question:** which data must be **read and mutated together with a single order**, which data belongs to **shared entities**, and which data must be **managed independently**?

### 1.1. Access Pattern Table Before Choosing a Model

| Operation | Access Keys / Filters | Data Needed | Consistency Requirement |
| --- | --- | --- | --- |
| Order details | **order_id** | Status, locked address, line items, totals | Confirmed amounts must be internally consistent |
| Customer order list | **customer_id**, descending time | ID, timestamp, status, total | Tolerates freshness per screen SLA |
| Confirm cart | Cart/customer, products, quote | Multiple lines, verified prices, address | Never confirm an order with wrong prices/totals |
| Cancel order | ID and current status | Order status, reason | Prevent two flows from making conflicting state transitions |
| Update shipment tracking | **shipment_id** | Delivery events | Can grow over time; owned by fulfillment |
| Confirm payment | **payment_attempt_id**, provider events | Payment status/ledger | Deduplicate writes; never record wrong amounts |
| Revenue report | Date, product, currency, status | Many orders and line items | Explicit formula, cutoff time, and grain |

Base embed/reference decisions on this table alongside **actual size distributions**: median/p95/p99 line counts, shipment counts, tracking event counts, read frequency, and mutation rates. Never design around a tiny sample order and assume it works for orders with tens of thousands of lines.

## 2. Starting Point: A Normalized Relational Model

In the relational model, entities and relationships can be represented as follows:

~~~text
customers 1 ─── N orders 1 ─── N order_items N ─── 1 catalog_products
                     |
                     + ─── N payment_attempts
                     |
                     + ─── N shipments 1 ─── N shipment_events
~~~

The link **order_items → catalog_products** identifies which product was purchased; it does **not** mean the product's current price is the purchase price. The actual price locked on the line item must still be stored per transaction semantics.

A compact PostgreSQL schema:

~~~sql
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE catalog_products (
    product_id TEXT PRIMARY KEY,
    current_name TEXT NOT NULL,
    current_unit_price NUMERIC(18, 2) NOT NULL
        CHECK (current_unit_price >= 0),
    currency CHAR(3) NOT NULL
);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    client_request_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('CONFIRMED', 'SHIPPED', 'CANCELLED')),
    currency CHAR(3) NOT NULL,
    ship_to_name_at_confirmation TEXT NOT NULL,
    ship_to_line1_at_confirmation TEXT NOT NULL,
    ship_to_city_at_confirmation TEXT NOT NULL,
    total_at_confirmation NUMERIC(20, 2) NOT NULL,
    UNIQUE (customer_id, client_request_id)
);

CREATE TABLE order_items (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id TEXT REFERENCES catalog_products(product_id),
    product_name_at_confirmation TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE INDEX idx_orders_customer_recent
    ON orders (customer_id, confirmed_at DESC, order_id DESC);
~~~

This schema omits **payment_attempts**, **shipments**, and **shipment_events** so the core translation problem stays clear. In a real system, those tables need their own keys, state constraints, and deduplication rules; you cannot assume they are simple attributes of the order.

**Strengths of this organization:** primary and foreign keys clearly identify relationships, and line items can be queried directly and joined in sets. Renaming a product does not touch confirmed order lines. Analytical queries can leverage normalized relations and tailored indexes.

**Costs to measure:** order detail views may require JOINs, batched queries, or multiple round-trips. Multi-table queries are **not automatically slow**; PostgreSQL executes JOINs efficiently when result sets are small and proper indexes exist.

### 2.1. Relational Query to Assemble Order Details

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    o.confirmed_at,
    o.status,
    o.currency,
    o.ship_to_name_at_confirmation,
    o.ship_to_line1_at_confirmation,
    o.total_at_confirmation,
    i.line_no,
    i.product_id,
    i.product_name_at_confirmation,
    i.quantity,
    i.unit_price_at_confirmation
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
WHERE o.order_id = $1
ORDER BY i.line_no;
~~~

The result returns one row per **order_item**, meaning **orders** attributes repeat across rows in the result set. Applications typically group those rows into a single DTO containing an array of line items. For an order with few lines, this overhead is often tiny; evaluate by measuring the entire API, serialization, and actual query count.

## 3. Choose the Aggregate Boundary Before Embedding

In document-oriented design, an **aggregate** is a cluster of data with a consistency boundary whose mutations are managed as one unit. The **Order** aggregate is typically a natural fit because:

- An order holds the line items approved at confirmation.
- The detail screen usually returns **order + line items**.
- Totals and line-item quantities must agree under business rules.
- After confirmation, each line's name/price is historical data rather than tracking the live catalog.

However, other entities often belong **outside** the Order aggregate:

- **Customer**: shared across many orders with an independent profile lifecycle.
- **CatalogProduct**: shared, with mutable current price/name; only the **ID** and locked snapshot live inside the order.
- **PaymentAttempt / PaymentEvent**: has its own idempotency keys, state machine, and financial reconciliation needs.
- **Shipment / TrackingEvent**: can involve multiple parcels, split deliveries, and long event histories.
- **InventoryReservation**: enforces cross-order stock invariants and cannot be treated as a child field of a single order without handling resource contention.

A useful litmus test:

> If creating, reading, updating, and deleting a group of data follows its own lifecycle without needing to touch the whole order, that group is likely an independent entity/document linked by ID.

### 3.1. Embed or Reference?

| Data | Initial Suggestion | Rationale | Exceptions to Watch |
| --- | --- | --- | --- |
| Confirmed line items | **Embed in order** | Read together, bounded by business rules, must match order total | Wholesale B2B orders with massive line counts or per-line workflows |
| Confirmed shipping address | **Embed snapshot** | Must preserve the address accepted at confirmation | Multi-shipment orders with distinct addresses need snapshots per shipment |
| **customerId** | **Reference** | Shared customer whose profile evolves over time | May embed locked recipient name, never the whole customer profile |
| **productId** | **Reference + name/price snapshot** | ID links to catalog; historical price preserves transaction truth | Personalized quotes or complex taxes require detailed pricing records |
| Multiple payment attempts | **Separate documents** | Independent idempotency and payment lifecycle | A summary status snapshot can sit on Order if freshness rules are explicit |
| Many tracking events | **Separate documents/collection** | Can grow unboundedly; queried by shipment and time | A few brief milestone markers can be embedded for display |
| Fixed order notes | **Can embed** | Rarely changes, read with order | Sensitive notes needing separate access control should be split |

These are **starting points**, not rigid laws. Final choices depend on access patterns, cardinality, document size, atomicity needs, access control, and update frequency.

## 4. Translating to the Order Document: A Concrete Model

Example document in MongoDB's **orders** collection. The snippet uses **MongoDB Extended JSON** to represent Decimal128 amounts and timestamps:

~~~json
{
  "_id": "ord-9001",
  "customerId": "cus-42",
  "clientRequestId": "checkout-42-001",
  "confirmedAt": {"$date": "2026-11-22T01:00:00Z"},
  "status": "CONFIRMED",
  "currency": "VND",
  "shippingAddressAtConfirmation": {
    "recipientName": "Nguyen An",
    "line1": "12 Hoa Street",
    "city": "Ho Chi Minh City",
    "countryCode": "VN"
  },
  "items": [
    {
      "lineId": "line-1",
      "productId": "prod-501",
      "productNameAtConfirmation": "A5 Notebook",
      "quantity": 2,
      "unitPriceAtConfirmation": {"$numberDecimal": "150000.00"},
      "lineSubtotal": {"$numberDecimal": "300000.00"}
    }
  ],
  "totals": {
    "itemsSubtotal": {"$numberDecimal": "300000.00"},
    "discountTotal": {"$numberDecimal": "10000.00"},
    "shippingAmount": {"$numberDecimal": "20000.00"},
    "taxTotal": {"$numberDecimal": "0.00"},
    "grandTotal": {"$numberDecimal": "310000.00"}
  },
  "version": 1,
  "createdAt": {"$date": "2026-11-22T01:00:00Z"},
  "updatedAt": {"$date": "2026-11-22T01:00:00Z"}
}
~~~

In this example: **300,000 − 10,000 + 20,000 + 0 = 310,000 VND**. This arithmetic is illustrative, **not a complete tax/discount model**. Production systems must define tax calculation, discount allocation, rounding policies, currency handling, and linkage to payment capture/refunds.

**Extended JSON** is purely a display/interchange notation. In MongoDB, **$numberDecimal** values map to BSON **Decimal128** when parsed properly. In mongosh, create monetary values with **NumberDecimal("150000.00")**. Never convert money through standard JavaScript floating-point numbers and expect exact financial math; another clean option is storing **integer minor units** with explicit currency rules.

### 4.1. Key Decisions in This Structure

1. **_id = orderId**: globally identifies the order; one document represents one order.
2. **customerId**: references the live customer profile rather than embedding the full customer record.
3. **clientRequestId**: prevents duplicate order creation on API retries; requires a scoped uniqueness constraint.
4. **items[]**: embeds line items sharing the confirmation lifecycle with the order, each carrying a distinct **lineId**.
5. **productId + productNameAtConfirmation + unitPriceAtConfirmation**: supports product lookup while preserving transaction history.
6. **shippingAddressAtConfirmation**: snapshot confirmed by customer and system; changing the customer's default address later **must not alter** this field.
7. **totals**: derived from confirmed terms; requires explicit formulas and invariants so it never drifts from **items[]**.
8. **version**: Order document revision used for optimistic concurrency control.
9. **createdAt / updatedAt**: technical audit timestamps, never replacing the business **confirmedAt** timestamp.

**Do not copy arbitrary live product attributes** like current warehouse, available stock, or lengthy descriptions just because they live in Catalog. Those live attributes are not historical facts required by the order line and create unnecessary sync obligations.

### 4.2. Never Confuse a Price Snapshot with a Read-Optimization Copy

Inside the Order document, **unitPriceAtConfirmation** is a **point-in-time fact at confirmation**. If catalog prices rise, past orders retain their locked price.

Conversely, in **productCards.currentPriceDisplay**, the price is duplicated to serve fast reads. When the live price source changes, the product card must refresh under its agreed consistency SLA.

Even if both hold 150,000 on the day of purchase, they **do not share the same update rule**. Auto-syncing historical order prices to track catalog updates would **rewrite history**.

## 5. Controlled Mapping from Relational to Document

| Relational Source | Document / New System Target | Transformation | Pitfall to Avoid |
| --- | --- | --- | --- |
| **orders.order_id** | **orders._id** | Preserve stable ID, enforce uniqueness | Never assign random new IDs and lose reconciliation lineage |
| **orders.customer_id** | **orders.customerId** | Store reference ID | Never copy the entire customer profile |
| **orders.confirmed_at** | **orders.confirmedAt** | Normalize absolute timestamp, preserve time zone/semantics | Never replace confirmed_at with migration timestamp |
| **orders.status** | **orders.status** | Map valid statuses | Never conflate order, payment, and shipment statuses |
| **order_items** | **orders.items[]** | Group by order_id, order by line_no | Never drop lines or multiply rows via unrelated JOINs |
| **order_items.product_id** | **items[].productId** | Keep product reference | Never pull current catalog price when building historical lines |
| **order_items.unit_price_at_confirmation** | **items[].unitPriceAtConfirmation** | Preserve decimal / currency minor units | Never convert through floats causing rounding errors |
| **orders.ship_to_*_at_confirmation** | **shippingAddressAtConfirmation** | Group flat columns into snapshot object | Never substitute the customer's current default address |
| **orders.total_at_confirmation** | **totals.grandTotal** | Map after verifying identical formulas | Never assume every column named “total” shares the same meaning |
| **payment_attempts** | Separate **paymentAttempts** | Preserve IDs, statuses, and payment idempotency | Never embed unbounded webhook/callback logs |
| **shipment_events** | Separate **shipmentEvents** | Keep shipmentId, timestamp, event source | Never store unbounded arrays inside Order |

Mapping a **1:N** relation into an array requires **preserving the right grain**: one source line row becomes one item element, rather than a JOIN with payments multiplying item entries. When aggregating complex tables, build orders and items from cleanly scoped queries or group using strict unique keys.

### 5.1. Row Multiplication Risk When Joining Multiple 1:N Relations

Suppose an order has **3 line items** and **2 payment attempts**. Writing a JOIN across **orders → order_items → payment_attempts** yields **6 rows**. Converting each joined row blindly into an item produces 6 line items instead of 3, corrupting totals.

Safer practices:

- Fetch order and items by **order_id** without joining payments unnecessarily.
- Fetch payments separately by **payment_id / order_id** and store them separately.
- During backfill, reconcile **line COUNT** and order totals per order.
- Enforce **(order_id, line_no)** at the source and stable **lineId** at the target.

## 6. Reading from Documents: Single-Fetch Details, Not Every Query Is Cheap

Querying a single order by key:

~~~javascript
db.orders.findOne(
  { _id: "ord-9001" },
  {
    customerId: 1,
    confirmedAt: 1,
    status: 1,
    currency: 1,
    shippingAddressAtConfirmation: 1,
    items: 1,
    totals: 1
  }
);
~~~

Because **items[]** is embedded in the order, this query returns everything required by the detail page without joining a line-item table. That is a clear win when **most reads need both the order header and its line items**.

However, if an order has thousands of lines and a summary view needs only header metadata and totals, loading the full document wastes bandwidth. Use **projection** to return only needed fields:

~~~javascript
db.orders.find(
  { customerId: "cus-42" },
  {
    _id: 1,
    confirmedAt: 1,
    status: 1,
    currency: 1,
    "totals.grandTotal": 1
  }
)
.sort({ confirmedAt: -1, _id: -1 })
.limit(20);
~~~

Index supporting the customer-chronological read pattern:

~~~javascript
db.orders.createIndex(
  { customerId: 1, confirmedAt: -1, _id: -1 },
  { name: "ix_customer_recent_orders" }
);
~~~

This compound index is a strong candidate because the query filters on **customerId** and sorts by **confirmedAt, _id**. Verify with **explain** and realistic data; do not create every imaginable index upfront. Note: in multi-tenant applications, **tenantId** may be required in logical partition keys, filters, and indexes per access policy.

### 6.1. Finding Orders by Product: Possible, with Trade-offs

~~~javascript
db.orders.find(
  { "items.productId": "prod-501" },
  {
    _id: 1,
    confirmedAt: 1,
    customerId: 1,
    status: 1
  }
).limit(50);
~~~

You can consider a *multikey index* on **items.productId**:

~~~javascript
db.orders.createIndex(
  { "items.productId": 1 },
  { name: "ix_orders_item_product" }
);
~~~

This is **not proof** that product-level analytics will match a flat line-item table: many array elements generate extra index entries, bloating index size, slowing writes, and limiting certain query/sort shapes. Heavy analytical workloads usually fit a separate **fact/order_items** table or analytical pipeline better.

MongoDB also provides the **aggregation pipeline** and **$lookup** joins. Choosing documents does not mean “joins are forbidden”; the measurable benefit comes from **designing frequent read paths to avoid assembling across many sources**, not from an absolute technical ban.

### 6.2. List Pagination and Avoiding Over-Fetching

- Customer order lists usually need only header metadata and totals; use projection.
- For deep pagination, consider **keyset/cursor pagination** over a stable sort pair rather than large **skip** offsets.
- Ensure pagination predicates and sort directions align with the index.
- Never return shipping addresses, phone numbers, internal notes, or full item arrays in public list APIs when screens do not need them.

In document queries, **fewer joins** is a benefit; **returning oversized documents or maintaining excessive indexes** is a cost that can outweigh it.

## 7. Updates and Atomicity Boundaries

MongoDB guarantees atomicity for **a single write operation on a single document**. This is a key reason to embed fields that must mutate together. However, atomicity only ensures fields write **together**—it does not verify whether your pricing formulas are right.

### 7.1. Status Updates with Optimistic Concurrency

For example, canceling an order only succeeds if the current status is **CONFIRMED** and version is **3**:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ord-9001",
    status: "CONFIRMED",
    version: 3
  },
  {
    $set: {
      status: "CANCELLED",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount !== 1) {
  // Status/version changed, or order does not exist:
  // re-read and decide whether to return conflict, idempotent response, or handle otherwise.
}
~~~

**status**, **version**, and **updatedAt** mutate atomically within the Order document. Filtering on status and version stops two workers from reading stale state and blindly overwriting each other.

Yet **canceling an order** may also require refunding payment, releasing inventory, or canceling shipments in other stores. Updating Order alone **does not atomically execute** those external actions. They require stateful workflows, multi-document transactions where appropriate, or saga/outbox/compensation patterns depending on architecture. Never report “refund completed” merely because **orders.status** changed.

### 7.2. Editing Cart Before Confirmation: Mutate Items and Totals Together

If the system edits a cart in a **DRAFT** document, changing quantity or removing a line requires recalculating totals. A clean design:

1. Read the current document version.
2. Verify caller permissions and that status is still DRAFT.
3. Recompute **items[]** and **totals** from authoritative quotes; never trust client-submitted totals.
4. Write **both items and totals in a single version-guarded update/replace**.
5. Check **matchedCount** and retry or reject on conflict.

Example conditional write (once the application has computed valid values):

~~~javascript
db.orders.updateOne(
  { _id: "draft-42", status: "DRAFT", version: 5 },
  {
    $set: {
      items: [
        {
          lineId: "line-1",
          productId: "prod-501",
          productNameQuoted: "A5 Notebook",
          quantity: 3,
          quotedUnitPrice: NumberDecimal("150000.00"),
          quotedLineSubtotal: NumberDecimal("450000.00")
        }
      ],
      totals: {
        itemsSubtotal: NumberDecimal("450000.00"),
        discountTotal: NumberDecimal("0.00"),
        shippingAmount: NumberDecimal("20000.00"),
        taxTotal: NumberDecimal("0.00"),
        grandTotal: NumberDecimal("470000.00")
      },
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
~~~

This illustrates the write pattern, **not building an entire order from untrusted inputs**. **productNameQuoted** and **quotedUnitPrice** on a DRAFT are temporary quotes; at checkout confirmation, re-verify and freeze them into **AtConfirmation** snapshots per the checkout contract. Never mutate prices on **CONFIRMED** lines when Catalog prices change.

If the app edits quantity in one update and updates totals in a second update, even though each command is atomic, **the sequence is no longer atomic**. That is precisely the pitfall you avoid by grouping coupled invariants into one document.

### 7.3. Payment and Inventory Updates Still Keep Separate Boundaries

Suppose confirming an order simultaneously requires:

- Checking current prices or valid quotes.
- Reserving stock across multiple products.
- Persisting the order and line items.
- Initiating a payment request or maintaining idempotency with a payment gateway.

Invariants spanning multiple orders, products, or external systems **cannot be solved by a single Order document alone**. MongoDB supports **multi-document transactions** in supported topologies, yet long transactions, concurrent contention, and external API calls still carry costs and limits. An architecture may require reservations, outboxes, sagas, and compensating actions.

The Order aggregate boundary keeps the order and its line items consistent together; it **does not turn the entire business into one giant aggregate**.

## 8. Preventing Duplicate Orders and Bad Updates from Retries

When a client submits an order confirmation request, the network can time out after the database commits. On client retry, you must not create a second order simply because the request arrived twice.

Assume every Order document includes **customerId** and a stable **clientRequestId** generated per checkout intent:

~~~javascript
db.orders.createIndex(
  { customerId: 1, clientRequestId: 1 },
  { unique: true, name: "ux_order_client_request" }
);
~~~

Business rules:

- Ensure **clientRequestId** is present and non-empty when creating orders under this constraint.
- On duplicate key error, read the existing order matching that key and **compare business intent**; never assume two differing payloads are valid retries of the same request.
- Return the already-created result for valid retries, or return a conflict error if payloads mismatch.
- In multi-tenant deployments, scope uniqueness properly with **tenantId**.

Note that MongoDB has specific semantics for missing/`null` fields in a **unique index**; do not index an optional field expecting it to allow unlimited documents omitting that field. For DRAFT documents lacking a request ID, require the field by document type or use a tested **partial** unique index.

To deduplicate repeated payment webhooks, maintain a separate **payment provider event ID / attempt ID** key at the payment owner. Order creation idempotency does not replace payment-capture idempotency.

## 9. Flexible Document Schemas Do Not Mean Zero Constraints

MongoDB allows more flexible document shapes than many relational schemas, yet applications still need a **schema contract**. Use a **$jsonSchema** validator to catch missing fields or wrong data types:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "customerId", "status", "currency",
        "items", "totals", "version"
      ],
      properties: {
        customerId: { bsonType: "string" },
        status: {
          enum: ["DRAFT", "CONFIRMED", "SHIPPED", "CANCELLED"]
        },
        currency: { bsonType: "string" },
        version: { bsonType: ["int", "long"], minimum: 1 },
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: [
              "lineId", "productId", "quantity"
            ],
            properties: {
              lineId: { bsonType: "string" },
              productId: { bsonType: "string" },
              quantity: {
                bsonType: ["int", "long"],
                minimum: 1
              }
            }
          }
        },
        totals: {
          bsonType: "object",
          required: ["grandTotal"],
          properties: {
            grandTotal: { bsonType: "decimal" }
          }
        }
      }
    }
  }
});
~~~

This validator **illustrates a new collection**, not a complete schema across every lifecycle state. Here, a DRAFT is permitted an **empty items array**; when transitioning to CONFIRMED, the domain layer must verify at least one item, complete snapshot fields, and pricing rules. To avoid colliding with existing collections, do not run **createCollection** on an existing collection; rolling out validators on populated collections requires its own migration workflow.

A validator alone does not prove:

- **lineSubtotal = quantity × unitPriceAtConfirmation**.
- **grandTotal = subtotal − discount + shipping + tax** with proper rounding.
- **lineId** is unique **across elements inside the same items[]**.
- Every **productId / customerId** references a valid document in another collection.
- **CONFIRMED** status is reached only after prices and inventory are verified.

Enforce and test these invariants in the domain layer or via appropriate database mechanisms. In particular, never assume a **unique multikey index** automatically forbids two elements inside **the same document** from sharing the same `lineId`; intra-array uniqueness must be enforced explicitly.

### 9.1. Schema Version and Legacy Data

As the system evolves, older Order documents might omit **shippingAddressAtConfirmation.countryCode** or use **subtotal** instead of **itemsSubtotal**.

Two common strategies:

- **Compatible reads:** the application reads multiple schema versions and normalizes them into one unified DTO.
- **Controlled migration:** add new fields, backfill from authoritative sources, track versions, and retire legacy read branches once complete.

If **schemaVersion** is stored, it tracks **structural** shape—distinct from **version** used for optimistic concurrency. Never overload one version number for both purposes and assume schema upgrades and order mutations share the same ordering.

For historical orders missing locked prices or addresses, **never pull today's price or address to fill in transaction history** without evidence. Mark them unverified and consult invoices, quotes, payment logs, or trustworthy historical records when backfilling.

## 10. Comparing Read Cost, Write Cost, and Document Size

Embedding many line items saves join steps, yet increases the payload stored and touched per order. Measure under representative workloads.

| Criterion | Relational with Separate order_items | Order Document Embedding Items | Hybrid: Order Document + Separate Payment/Shipment |
| --- | --- | --- | --- |
| Single order details | JOIN / batch, typically fast with indexes | Single document fetch | Single fetch for order header/items; extra query for shipment/payment when needed |
| List of 20 orders | Query orders table with column projection | Query orders with field projection | Same as document |
| Change quantity before confirmation | Update row and recompute total in transaction | Single document update mutates items + totals | Same as document |
| Locked price / name | Stored per order_item row | Stored inside items[] elements | Stored in Order |
| Payment and fulfillment | Separate tables, clear keys/transactions | Unbounded embedding causes bloat | Independent lifecycles linked by ID |
| Queries by product / date | Flat line-item table is convenient | Requires multikey / aggregation / unwind | Can emit dedicated fact/read model |
| Concurrent writes by different teams | Update separate rows; still uses transactions/locks | Concurrent updates on same Order contend | Reduces contention by splitting entities |
| Schema evolution | Explicit DDL migrations | Legacy shapes coexist; needs versioning/validation | Manage contracts per collection |
| Referential integrity | Explicit PK/FK/UNIQUE/CHECK | Relies on validation and app logic; joins still possible | Same, with clearer ownership boundaries |
| Size limits | Child rows stored separately | Subject to BSON document size cap | Prevents unbounded arrays |

MongoDB enforces a per-document BSON size limit (commonly **16 MiB**); however, design around **actual line-item and byte distributions**, not merely checking whether you hit the hard cap. A document well below the limit can still incur heavy bandwidth, memory, contention, and indexing costs.

### 10.1. Embedding Does Not Mean Every Mutation Rewrites the Whole Document

MongoDB supports **$set**, **$inc**, and targeted field/array updates. Thus, you should not claim every small edit forces the application to load and replace the entire document.

Still, **one document remains the unit of contention and atomic mutation**, so line items heavily mutated by many actors can contend. Appending array elements, growing document size, and maintaining multikey indexes also carry real costs. Benchmark instead of guessing from storage assumptions.

### 10.2. Foreign Keys, JOINs, and Transactions

- PostgreSQL provides **FKs** protecting links between order_items and orders; MongoDB does not automatically enforce cross-collection FKs simply because **productId** is present.
- MongoDB supports **$lookup** in aggregations; moving to documents does not eliminate every join.
- MongoDB supports **multi-document transactions** in supported topologies; yet transactions incur overhead, operational constraints, and never cover external payment gateways.
- A single-document write is atomic, yet **whether the data is business-valid** still depends on prices, totals, statuses, permissions, and application constraints.

Avoid slogans like “documents always read faster than relational” or “relational is always more reliable.” Measure **your actual workload** and evaluate invariant clarity—not just JOIN counts.

## 11. Analytics and Reporting: The Order Document May Not Be Optimal

Suppose analytics wants sales by **productId** and month. In the Order document, items live inside an array. MongoDB can run an **aggregation pipeline**:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: { $in: ["CONFIRMED", "SHIPPED"] }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: {
        productId: "$items.productId",
        currency: "$currency"
      },
      soldQuantity: { $sum: "$items.quantity" },
      itemGrossAmount: { $sum: "$items.lineSubtotal" }
    }
  }
]);
~~~

This pipeline illustrates summing **line items by productId and currency** for selected statuses. It is **not net revenue**: it does not subtract refunds, allocate discounts/taxes/fees, group by month, or handle cancellations/adjustments per accounting rules. Define formulas and business cutoff rules before using numbers in reports.

Running heavy **$unwind** scans repeatedly across huge histories can be expensive. One pattern emits an **order_line_fact** table or summary into an analytical store at the grain of **one confirmed line item** with lineage back to the order. Operational APIs read the transactional model while analytics queries the analytical model—each optimized for its purpose.

**Never add monetary amounts across different currencies directly.** If orders span both VND and USD, group by currency or convert using explicit exchange rates, timestamps, and rounding rules.

### 11.1. Document and Graph Solve Different Problems

Orders have a clear aggregate structure, making documents a natural fit for lookup by orderId. Queries like “which customers frequently co-purchase these products,” “multi-level referral networks,” or “customer–product–supplier link paths” may fit graph or analytical models better depending on workload.

Do not force every query into one giant document or a graph merely because a tool supports it. Choose models based on **what is read/written together and which relationships must be traversed**.

## 12. Ensuring Post-Migration Data Integrity: Invariants and Reconciliation

Migration must never drop a line item, alter historical prices, or miscalculate order totals.

### 12.1. Minimum Per-Order Invariants

For every confirmed order:

1. **Line count:** `items[]` length equals the source line-item count for that order.
2. **Identity:** each `lineId` maps 1-to-1 to a source `(order_id, line_no)` with no duplicates inside the document.
3. **Quantity:** `quantity > 0`, and `productId/name/price` match the locked values.
4. **Currency:** unit prices match valid currencies or explicit multi-currency rules.
5. **Line subtotal:** each `lineSubtotal` equals `quantity × unitPriceAtConfirmation` per rounding rules.
6. **Order totals:** `grandTotal` matches the finalized formula; subtotal, discount, shipping, tax, and refund remain distinct.
7. **Address:** `shippingAddressAtConfirmation` comes from the transaction snapshot, **never** the current profile.
8. **Uniqueness:** one `orderId` maps to one document, and idempotency keys never allow duplicate orders.
9. **Status:** statuses map accurately without overwriting post-snapshot updates.
10. **Data governance:** sensitive fields are copied, protected, and retained per policy.

Never treat **valid JSON syntax** as a substitute for verifying these invariants.

### 12.2. Source-Side Reconciliation Query Example

~~~sql
SELECT
    o.order_id,
    COUNT(i.line_no)::BIGINT AS source_line_count,
    SUM(i.quantity * i.unit_price_at_confirmation)
        AS source_items_subtotal
FROM orders AS o
LEFT JOIN order_items AS i ON i.order_id = o.order_id
GROUP BY o.order_id;
~~~

Because `LEFT JOIN` yields one row with **`i.line_no = NULL`** for an order with zero items, use **`COUNT(i.line_no)`** instead of `COUNT(*)` to accurately detect 0 lines. **`SUM`** returns `NULL` when no rows exist; define how to interpret that case rather than silently substituting an arbitrary number.

In MongoDB, inspect a document's item count and stored amounts:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-9001" } },
  {
    $project: {
      orderId: "$_id",
      documentLineCount: { $size: "$items" },
      storedItemsSubtotal: "$totals.itemsSubtotal",
      recomputedItemsSubtotal: { $sum: "$items.lineSubtotal" },
      storedGrandTotal: "$totals.grandTotal"
    }
  }
]);
~~~

This checks only **line counts and subtotals inside the document**; individual line values could still share matching errors. Full migration verification compares **lineId, quantity, locked unit price, and total rules** against the relational/authoritative source at the same cutoff point—not merely comparing two totals.

### 12.3. Handling Drift and Late-Arriving Changes

If the source keeps mutating during migration, a backfilled document may lag behind recent writes. Use **versions/checkpoints** or snapshot + catch-up change streaming; never let a stale backfill job overwrite newer writes.

When discrepancies surface:

- Pinpoint which source event/key was actually dropped or duplicated.
- Distinguish errors from **mapping**, **pricing formulas**, **JOIN multiplication**, or **sync lag**.
- Recompute from the authoritative source at a consistent cutoff; never manually patch a total without inspecting line items.
- Log affected record counts, root cause, remediation, and preventive guards.

## 13. Safe Migration Plan from Relational to Document

A reference plan for a live production system:

1. **Inventory use cases and authoritative sources:** confirmed orders/lines, pricing, customers, payments, shipments; decide what belongs in the Order aggregate.
2. **Freeze schema contract:** required fields, money types, time zones, statuses, versioning, historical snapshots, array bounds.
3. **Build sample datasets and invariant tests:** zero-line orders (if allowed), large orders, discounts, customer address edits, product renames, multiple payment attempts.
4. **Build backfill pipeline:** read source tables cleanly and group by **order_id**, avoiding 1:N JOIN multiplication.
5. **Choose snapshot/change checkpoint:** capture and apply mutations occurring mid-backfill; if using CDC/outbox, ensure seamless handoff between snapshot and stream.
6. **Keep one authoritative source during transition:** if dual-writing, only one store defines truth; reconcile duplicate/lagging writes rather than treating both as co-masters.
7. **Automate reconciliation:** order counts, line counts, locked prices, totals, statuses, addresses, missing/duplicate IDs, and orphan references.
8. **Run shadow reads:** read from both old and new systems for sampled traffic and compare normalized DTOs; investigate discrepancies before exposing new reads.
9. **Cut over reads gradually:** ramp by traffic percentage or cohort while monitoring p95/p99 latency, errors, and freshness.
10. **Cut over writes only with a rollback plan:** handle cross-store transactions, events, payments, and statuses; maintain a clear reverse-sync or rollback path.
11. **Monitor and decommission legacy components:** only after verifying zero APIs, reports, batch jobs, or retention policies still depend on them.

Never cut over reads, writes, payments, fulfillment, and reporting to a new document model **in one big-bang step without recovery checkpoints**. Nor treat **dual-writing two databases** as automatically atomic; single-side failures must be detected and repaired.

### 13.1. Choosing a Hybrid Option Instead of Full Migration

If **reading order details** is slow while relational payments and reporting work smoothly, a team can:

- Keep **PostgreSQL Orders + OrderItems** as the authoritative write source.
- Maintain **order_detail_documents** as a read projection keyed by orderId.
- Sync via outbox/CDC with version tracking, lag monitoring, and reconciliation.
- Keep payments, inventory, and reporting on their best-fit models/sources.

This lowers write-migration risk at the cost of projection sync ownership. Choose it only when read gains are substantial and freshness SLOs allow it. If relational JOINs already meet SLOs, do not add a projection just because documents look cleaner.

## 14. Performance Experiment: Compare Both Reads and Writes on the Same Workload

Suppose targets are **order detail API p95 ≤ 120 ms**, **status update p95 ≤ 100 ms**, and recent-20 order list ≤ 150 ms. The numbers below are **purely hypothetical to practice analysis**, not real benchmark measurements.

| Hypothetical Metric | Relational with Optimal Indexes & JOIN | Document with Embedded Items |
| --- | ---: | ---: |
| Order detail p95, 5-line order | 92 ms | 58 ms |
| 20-order list p95 | 76 ms | 71 ms |
| Order status update p95 | 24 ms | 31 ms |
| 1,500-line order: full read p95 | 420 ms | 540 ms |
| Queries needed for detail view | One JOIN or batched fetch | One document |
| Risks to measure | JOINs, N+1, round-trip count | Document size, contention, payload transfer |
| Line-level analytics strength | Direct order_items table | Requires unwind or separate read/fact model |
| Migration & operational cost | Keep existing source | Dual data, mapping, tests, write-path cutover |

Conditional conclusions:

- **Document** can be a strong fit for small/medium orders when detail reads dominate, aggregate boundaries are clear, and operational practices match.
- **Relational** already satisfies several SLOs in this example; there is no basis for migrating every system merely to reduce JOINs.
- For **very large orders**, bloated documents and frequent per-line edits can hurt embedded designs; measure long-tail cardinality.
- For payments, inventory, and analytics, compare **end-to-end business workflows**, not merely order-detail API p95.

A valid benchmark uses identical datasets, line-count distributions, read/write ratios, concurrency, caching policies, indexes, hardware specs, and network conditions. Measure p50/p95/p99, throughput, I/O, CPU, lock/write conflicts, data/index size, rebuild times, and post-sync drift.

## 15. Pre-Migration Design Checklist

| Question | Evidence Required |
| --- | --- |
| Which access patterns need to change? | Current queries, RPS, latency, and SLOs |
| Order aggregate boundary? | Fields read/mutated together and business invariants |
| What data is embedded? | Cardinality, size, lifecycle, write ownership |
| What data is referenced? | Independent Customer/Product/Payment/Shipment records |
| What do prices and addresses mean? | Point-in-time locked values, not live profile/catalog sources |
| Currency, tax, discounts? | Decimal/minor-unit types, formulas, and rounding rules |
| Status / versioning? | Allowed transitions, optimistic concurrency, idempotency |
| Use-case indexes? | Explain plans, query shapes, selectivity, and index overhead |
| Document growth? | Line-item/shipment event distributions and size caps |
| Analytical queries? | Grain, pipelines, fact models, and currency rules |
| Data verified? | Order/line counts, mapping checks, and total validation |
| Cross-source mutations? | Transactions/outbox/sagas, rollback, and recovery |
| PII protection? | Address permissions, retention limits, deletion/masking, audit |
| Reversible rollout? | Shadow reads, gradual traffic shift, source of truth, rollback plan |

## 16. Practice Exercises

### Exercise 1 — Embed or Reference?

A retail order has a median of **4 lines** and a p99 of **18 lines**. Whenever a customer opens order details, the API needs all lines and totals. Products in Catalog frequently change names and prices.

**Question:** Should `items[]` be embedded inside the Order document? Should each item store IDs or current catalog names/prices?

### Exercise 2 — Very Long Payment History

An order can receive thousands of payment provider webhooks due to retries, state updates, and multiple payment attempts. The team wants to embed all webhooks in **orders.paymentEvents[]**.

**Question:** What is the primary risk? Which data should be split vs. embedded?

### Exercise 3 — JOIN Multiplication

Order X has 4 line items and 3 payment attempts. A migration pipeline simultaneously JOINs **order_items** and **payment_attempts**, then pushes an item element per joined row.

**Question:** How many erroneous items can the document end up with, and how do you prevent it?

### Exercise 4 — Atomic Order Update Misses Refund

A worker runs **updateOne** to transition Order to **CANCELLED**. The write succeeds, yet the payment service fails and captured funds remain unrefunded.

**Question:** Why was an atomic document write insufficient, and what workflow is needed?

### Exercise 5 — Order List and Indexes

An API frequently fetches a customer's 20 newest orders, needing only status, confirmedAt, and grandTotal; each Order document carries a large `items[]`.

**Question:** What projection and initial candidate index should the query use?

### Exercise 6 — Revenue Analytics by Product

A report asks for **net revenue after refunds**, grouped by month and currency. One pipeline simply runs **`$unwind: "$items"`** and SUMs `lineSubtotal` across all CONFIRMED orders.

**Question:** Why is that result not net revenue, and which sources and grain must be clarified?

### Exercise 7 — New Schema Lacks Historical Data

During migration, many legacy order lines lack **unit_price_at_confirmation**. The team proposes populating them from **catalog_products.current_unit_price** so every document passes validation.

**Question:** Why is this risky, and what should be done if old receipts are unavailable?

### Suggested Answers

1. **Embedding works well** because line counts are bounded and read together with Order. Keep **productId** as a reference while storing **name/price at confirmation** as historical truth; never sync past orders to Catalog updates.
2. Unbounded event lists bloat the document, increase write contention, and mix payment ownership into Order. Keep **paymentAttempts / paymentEvents** separate with deduplication IDs; Order can hold a summary payment status if backed by clear authority and freshness rules.
3. **4 × 3 = 12** items if pushing every joined row; the true count is **4**. Group by **(order_id, line_no)**, avoid joining two 1:N branches when building items, and reconcile line counts/totals.
4. `updateOne` is atomic **only inside the Order document**, not across the payment gateway. You need controlled intermediate states, refund idempotency keys, outbox/saga coordination, retries, and payment reconciliation before reporting completion.
5. Project only **_id, confirmedAt, status, totals.grandTotal**; filter on customerId, sort by confirmedAt DESC + _id DESC, and evaluate index **`{customerId:1, confirmedAt:-1, _id:-1}`**. Never fetch `items` unnecessarily.
6. Summing `lineSubtotal` yields **gross item sales**, ignoring discounts, refunds, fees, taxes, cancellations, and period cutoffs. Use a defined payment/refund ledger or business events at **month × product × currency** grain with explicit recognition dates and net formulas.
7. Current prices **do not prove historical prices**. Recover prices from invoices, payment records, quotes, or effective price history. If unverifiable, flag missing data per migration policy and exempt legacy records from new required constraints rather than fabricating amounts.

## 17. Key Takeaways

**Translating a relational order model to a document model means redesigning data boundaries around read and mutation patterns—not merely converting rows and columns into JSON syntax.** Confirmed line items and shipping snapshots can fit cleanly inside Order, whereas live customers, Catalog, payments, shipments, and analytics typically have independent lifecycles or invariants.

The **primary strengths** of documents are reading a pre-assembled aggregate and atomically updating multiple fields within that document. The **trade-offs** include document size growth, array updates and contention, lack of cross-collection FK enforcement, line-level query costs, migration complexity, and cross-entity consistency ownership.

Before locking down a schema, answer with concrete numbers and contracts: **“Which APIs truly read together, which data must lock together, which subsets can grow unboundedly, and where does the authoritative source live when verifying or recovering data?”**. With clear answers, relational, document, or hybrid models can all be chosen on solid evidence.
