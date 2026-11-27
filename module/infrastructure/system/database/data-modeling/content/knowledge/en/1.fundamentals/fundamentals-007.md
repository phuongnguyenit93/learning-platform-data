# End-to-End Example: Customers, Catalog, Orders, Payments, and Inventory

An online retail system usually begins with everyday questions: who is buying, which category does a product belong to, what is in an order, has the customer paid, and does the warehouse have enough stock to fulfill it? When turning those questions into data, we must identify entities, relationships, business rules, how history is preserved, and how concurrent operations are prevented from corrupting numbers.

This lesson uses an online store as an end-to-end example to practice translating business requirements into a data model. We will move from a conceptual model to a relational schema, then compare it against document, graph, and analytical models. The goal is choosing structures aligned with how the system operates, verifiable via constraints, and evolvable as the business changes.

## 1. Starting from Business Requirements

Suppose a store has customers, products, categories, orders, payments, and multiple warehouses. Before creating tables, write the rules in business language. A good model must answer these rules without relying on arbitrary interpretations by individual developers.

| Object | Rules to Capture |
|---|---|
| Customer | A customer has a profile, contact details, and can save multiple shipping addresses. |
| Category | A category can have a parent category and child categories. |
| Product | Each product has a unique SKU; a product can appear in multiple categories. |
| Order | An order belongs to one customer and has at least one line item when confirmed. |
| Line item | Each line records the product, quantity, and price at order time. |
| Payment | An order can have multiple payment attempts, multiple charge transactions, or refunds. |
| Inventory | A product can exist across multiple warehouses; each warehouse tracks on-hand and reserved quantities. |
| Inventory movement | Every receipt, shipment, reservation, release, or adjustment must leave an audit trail. |

The rules above embed several modeling decisions worth stating explicitly:

- A product is assigned to multiple categories. Therefore, the product–category relationship is many-to-many. If the business allows only one primary category, the join table can be replaced with a foreign key on the product.
- A product's current price can change. Orders must preserve the price and product name at purchase time so old invoices do not shift with catalog updates.
- An order can have multiple payment records. A failed payment attempt must never overwrite a subsequent successful one.
- Inventory is managed per warehouse. Sellable quantity equals on-hand quantity minus reserved quantity.
- An order's shipping address is a snapshot at order time. If a customer updates an address in their profile, old orders must retain their original address.

These are the assumptions for this example. On a real project, confirm these points with business stakeholders before locking down the schema.

## 2. Identifying Entities, Attributes, and Relationships

From the requirements, we identify the core entities:

- **Customer:** the buyer.
- **CustomerAddress:** addresses a customer can choose when ordering.
- **Category:** category tree.
- **Product:** products in the catalog.
- **ProductCategory:** associative table linking products and categories.
- **SalesOrder:** order header containing customer, status, timestamp, and totals.
- **OrderItem:** each product line within an order.
- **Payment:** a payment transaction or attempt.
- **Warehouse:** physical storage location.
- **Inventory:** current quantities per product and warehouse.
- **InventoryMovement:** ledger recording inventory changes.

Conceptual diagram:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : appears_in
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
    CATEGORY o|--o{ CATEGORY : parent_of
    SALES_ORDER ||--o{ PAYMENT : has
    PRODUCT ||--o{ INVENTORY : stocked_as
    WAREHOUSE ||--o{ INVENTORY : stores
    PRODUCT ||--o{ INVENTORY_MOVEMENT : changes
    WAREHOUSE ||--o{ INVENTORY_MOVEMENT : records
    SALES_ORDER o|--o{ INVENTORY_MOVEMENT : causes
~~~

Reading the diagram in business terms:

- A customer can have many addresses and many orders; each order belongs to only one customer.
- An order has one or more line items; each line item references one product.
- Products and categories have a many-to-many relationship, implemented via **ProductCategory**.
- A category can have one parent category; a parent category can have many child categories.
- An order can have many payment records.
- A product has its own stock counts at each warehouse. The product–warehouse pair identifies an inventory record.
- Inventory movements indicate the product, warehouse, and cause. A movement may relate to an order, while cycle-count adjustments do not necessarily involve an order.

The conceptual diagram does not yet decide data types, indexes, or partitioning. Those decisions belong to logical and physical design.

## 3. Designing the Relational Schema

### 3.1. Keys and Identifiers

Every table needs a way to uniquely identify a row:

- Use surrogate primary keys such as **customer_id**, **product_id**, or **order_id** for stable identification.
- Use business keys with unique constraints for values that users or external systems recognize, such as **sku**, **order_number**, and payment gateway reference IDs.
- Use composite primary keys for associative tables like **(product_id, category_id)** and inventory tables like **(product_id, warehouse_id)**.
- Use **line_no** combined with **order_id** to identify a line within an order.

Surrogate keys do not eliminate the need to enforce business keys. Without a **UNIQUE** constraint on SKU, two products could accidentally share the same code despite having distinct primary keys.

### 3.2. DDL Example

The following example uses PostgreSQL. It illustrates the stated rules; data types, lengths, and statuses must be adjusted to match real business contracts.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320),
    full_name VARCHAR(200) NOT NULL,
    phone VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Email is case-insensitive.
CREATE UNIQUE INDEX uq_customer_email_ci
    ON customer (lower(email))
    WHERE email IS NOT NULL;

CREATE TABLE customer_address (
    address_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    recipient_name VARCHAR(200) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    address_line1 VARCHAR(250) NOT NULL,
    address_line2 VARCHAR(250),
    ward VARCHAR(120),
    city VARCHAR(120) NOT NULL,
    country_code CHAR(2) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_customer_address_customer
    ON customer_address(customer_id);

CREATE TABLE category (
    category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_category_id BIGINT REFERENCES category(category_id)
        ON DELETE RESTRICT,
    slug VARCHAR(160) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX ix_category_parent
    ON category(parent_category_id);

CREATE TABLE product (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(250) NOT NULL,
    description TEXT,
    current_price NUMERIC(18, 2) NOT NULL CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE product_category (
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    category_id BIGINT NOT NULL REFERENCES category(category_id)
        ON DELETE RESTRICT,
    PRIMARY KEY (product_id, category_id)
);

CREATE INDEX ix_product_category_category
    ON product_category(category_id, product_id);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    status VARCHAR(24) NOT NULL
        CHECK (status IN (
            'DRAFT', 'PENDING_PAYMENT', 'PAID',
            'PROCESSING', 'SHIPPED', 'COMPLETED',
            'CANCELLED', 'REFUNDED'
        )),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    currency CHAR(3) NOT NULL,
    subtotal NUMERIC(18, 2) NOT NULL CHECK (subtotal >= 0),
    discount_total NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (discount_total >= 0),
    shipping_fee NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (shipping_fee >= 0),
    tax_total NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (tax_total >= 0),
    grand_total NUMERIC(18, 2) NOT NULL CHECK (grand_total >= 0),
    delivery_recipient VARCHAR(200) NOT NULL,
    delivery_phone VARCHAR(30) NOT NULL,
    delivery_address TEXT NOT NULL,
    CONSTRAINT ck_order_total
        CHECK (grand_total = subtotal - discount_total
                           + shipping_fee + tax_total)
);

CREATE INDEX ix_order_customer_placed
    ON sales_order(customer_id, placed_at DESC, order_id DESC);

CREATE TABLE order_item (
    order_id BIGINT NOT NULL REFERENCES sales_order(order_id)
        ON DELETE RESTRICT,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    sku_snapshot VARCHAR(80) NOT NULL,
    product_name_snapshot VARCHAR(250) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0),
    line_total NUMERIC(18, 2)
        GENERATED ALWAYS AS (quantity * unit_price - discount_amount)
        STORED,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_order_item_discount
        CHECK (discount_amount <= quantity * unit_price)
);

CREATE INDEX ix_order_item_product
    ON order_item(product_id, order_id);

CREATE TABLE payment (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES sales_order(order_id)
        ON DELETE RESTRICT,
    payment_type VARCHAR(12) NOT NULL
        CHECK (payment_type IN ('CHARGE', 'REFUND')),
    provider VARCHAR(60) NOT NULL,
    provider_reference VARCHAR(160),
    idempotency_key VARCHAR(160) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_reference),
    UNIQUE (provider, idempotency_key)
);

CREATE INDEX ix_payment_order_status
    ON payment(order_id, status);

CREATE TABLE warehouse (
    warehouse_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE inventory (
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    warehouse_id BIGINT NOT NULL REFERENCES warehouse(warehouse_id)
        ON DELETE RESTRICT,
    on_hand_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (on_hand_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, warehouse_id),
    CONSTRAINT ck_inventory_reserved
        CHECK (reserved_quantity <= on_hand_quantity)
);

CREATE INDEX ix_inventory_warehouse
    ON inventory(warehouse_id, product_id);

CREATE TABLE inventory_movement (
    movement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    warehouse_id BIGINT NOT NULL REFERENCES warehouse(warehouse_id)
        ON DELETE RESTRICT,
    order_id BIGINT REFERENCES sales_order(order_id)
        ON DELETE RESTRICT,
    movement_type VARCHAR(24) NOT NULL
        CHECK (movement_type IN (
            'RECEIPT', 'RESERVE', 'RELEASE',
            'SHIP', 'RETURN', 'ADJUSTMENT'
        )),
    on_hand_delta INTEGER NOT NULL DEFAULT 0,
    reserved_delta INTEGER NOT NULL DEFAULT 0,
    reason VARCHAR(250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (on_hand_delta <> 0 OR reserved_delta <> 0)
);

CREATE INDEX ix_movement_stock_time
    ON inventory_movement(product_id, warehouse_id, created_at DESC);
CREATE INDEX ix_movement_order
    ON inventory_movement(order_id)
    WHERE order_id IS NOT NULL;
~~~

Key points to note in this DDL:

1. **PRIMARY KEY**, **UNIQUE**, **NOT NULL**, and **CHECK** turn rules into conditions that the database rejects when data is invalid.
2. **FOREIGN KEY** ensures line items reference real products, orders reference real customers, and inventory references valid warehouses.
3. **ON DELETE RESTRICT** protects transaction history. For customers, products, or warehouses with existing transactions, deactivate or archive them instead of hard-deleting.
4. **order_item** stores snapshots of SKU, name, and unit price. These columns look like duplicated product info, yet they describe a historical purchase event.
5. **sales_order** stores totals at confirmation time. The **CHECK** constraint validates arithmetic among components within the same row. Reconciling the order total against line-item sums must occur in the same transaction via application logic, triggers, or data validation workflows, since a standard **CHECK** cannot aggregate rows from another table.
   In this example, **subtotal** is the sum of line values before discounts; **discount_total** includes line-level discounts (sum of **order_item.discount_amount**) and order-level discounts. **line_total** is a line's value after line-level discount. This convention keeps the order-total formula consistent; when writing an order, the application must still reconcile these totals against line details.
6. **inventory** holds current balances for fast reads; **inventory_movement** records change history. Every balance update must append a corresponding movement in the same transaction.

### 3.3. Why Do We Need Join Tables and Detail Tables?

Do not store a list of categories in a text column like `"phones,accessories"` on a product. Doing so makes querying, foreign-key validation, and category renaming unreliable. The **product_category** table ensures every link is enforced by two foreign keys.

Similarly, do not store all order items in a single JSON column if the system frequently filters, aggregates, validates products, or updates stock line by line. **order_item** gives each line item a clear identity, quantity constraints, and price integrity.

## 4. Normalization and Intentional Copies

Normalization reduces anomalies when inserting, updating, or deleting data.

### 4.1. Reviewing 1NF, 2NF, and 3NF

- **First Normal Form (1NF):** every cell holds a single value from a defined domain; do not pack multiple SKUs or categories into a comma-separated column.
- **Second Normal Form (2NF):** with composite primary keys, non-key attributes must depend on the whole key. In **product_category**, the table holds only the key pair, so no descriptive attribute depends on half the key. Product names belong in **product**; category names belong in **category**.
- **Third Normal Form (3NF):** non-key attributes should not depend transitively on the key. For example, city and country details of an address belong in the address record rather than repeating as descriptive columns dependent on a location code on every order.

Normalization is not an end in itself. Choose a level of normalization sufficient to keep data consistent, and add derived data only when justified by a clear operational reason.

### 4.2. Historical Snapshots Are Not Arbitrary Copies

Suppose a product is named "Headphone A" and priced at 500,000 VND when a customer orders it. Next week, the store renames the product and raises the price to 550,000 VND. If the order merely references **product_id** and reads the current name and price from **product**, old invoices will display wrong history.

Hence, **order_item** stores **sku_snapshot**, **product_name_snapshot**, and **unit_price**. These are facts of the transaction at purchase time, not copies intended to replace the catalog.

### 4.3. Inventory Balances and the Movement Ledger

There are two ways to compute inventory:

- Compute on every read by summing all deltas in **inventory_movement**. This retains complete history but can become slow as the movement ledger grows.
- Store the current balance in **inventory** for fast reads while appending to the movement ledger in **inventory_movement**.

This example uses the second approach. Both places must be updated atomically in the same transaction. Scheduled reconciliation jobs can recompute balances from the movement ledger to catch discrepancies. The movement ledger should be treated as historical data; avoid editing or deleting recorded rows.

## 5. Order Transactions and Safe Inventory Reservation

The data model must withstand multiple customers ordering the same product nearly simultaneously. If two requests both read one unit remaining and both record an order, the store can oversell.

An ordering workflow can proceed as follows:

1. Create the order and line items with prices, names, and SKUs snapshotted at order time.
2. For each selected product and warehouse, conditionally increment the reserved quantity.
3. If any line lacks sufficient available quantity, roll back the entire transaction and report out-of-stock.
4. If all reservations succeed, record the corresponding **inventory_movement** rows and transition the order to **PENDING_PAYMENT**.
5. Commit the transaction. Only afterward call the payment gateway or emit a payment-processing event.

Core reservation statement:

~~~sql
UPDATE inventory
SET reserved_quantity = reserved_quantity + :requested_quantity,
    updated_at = now()
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND on_hand_quantity - reserved_quantity >= :requested_quantity
RETURNING product_id, warehouse_id, on_hand_quantity, reserved_quantity;
~~~

If this statement returns no row, either the inventory row does not exist or available quantity is insufficient. The application must treat that as a reservation failure. Upon success, within the same transaction insert an **inventory_movement** row with **movement_type = 'RESERVE'**, **on_hand_delta = 0**, and **reserved_delta** equal to the reserved quantity.

On shipment, both on-hand and reserved quantities decrease together:

- **on_hand_delta = -quantity**
- **reserved_delta = -quantity**
- **movement_type = 'SHIP'**

On cancellation before shipment, release the reservation:

- **on_hand_delta = 0**
- **reserved_delta = -quantity**
- **movement_type = 'RELEASE'**

For multi-item orders, process **(product_id, warehouse_id)** pairs in a consistent deterministic order across all flows to reduce deadlock risk. Set reservation expiration timeouts and run a job to release expired holds.

Never hold a database transaction open while waiting for a network response from a payment gateway. Create a **PENDING** payment record, commit, call the provider with an idempotency key, and update status based on the response or webhook. Unique constraints on **(provider, idempotency_key)** and **(provider, provider_reference)** prevent duplicate payment records during retries. Webhooks must also be handled idempotently because providers can redeliver events.

## 6. Queries to Validate the Model

A model must support real-world questions.

### 6.1. Customer Purchase History

~~~sql
SELECT
    o.order_number,
    o.placed_at,
    o.status,
    oi.product_name_snapshot,
    oi.sku_snapshot,
    oi.quantity,
    oi.unit_price,
    oi.line_total
FROM sales_order AS o
JOIN order_item AS oi ON oi.order_id = o.order_id
WHERE o.customer_id = :customer_id
ORDER BY o.placed_at DESC, o.order_id DESC, oi.line_no;
~~~

The query reads names and prices from line-item snapshots, so history stays accurate even after catalog changes. The index **(customer_id, placed_at DESC, order_id DESC)** supports fetching a customer's recent orders.

### 6.2. Sellable Quantity of a Product per Warehouse

~~~sql
SELECT
    w.code,
    w.name,
    i.on_hand_quantity,
    i.reserved_quantity,
    i.on_hand_quantity - i.reserved_quantity AS available_quantity
FROM inventory AS i
JOIN warehouse AS w ON w.warehouse_id = i.warehouse_id
WHERE i.product_id = :product_id
ORDER BY w.code;
~~~

Available quantity is a derived value. There is no need to store an extra **available_quantity** column that could drift out of sync with its two constituent columns.

### 6.3. Net Successful Amount Collected for an Order

~~~sql
SELECT
    order_id,
    SUM(CASE
        WHEN payment_type = 'CHARGE' AND status = 'SUCCEEDED'
            THEN amount
        WHEN payment_type = 'REFUND' AND status = 'SUCCEEDED'
            THEN -amount
        ELSE 0
    END) AS net_paid
FROM payment
WHERE order_id = :order_id
GROUP BY order_id;
~~~

This yields the net amount collected from succeeded transactions. It may differ from **grand_total** if the customer underpaid, paid in installments, or received a refund. Order status should transition according to explicit business rules driven by confirmed transactions.

## 7. If Choosing a Document Database

A document database like MongoDB fits well when applications regularly read or write an entire aggregate together, attribute shapes vary, and nested data shares a similar lifecycle.

An order is a strong candidate for storage as a single document because the header, shipping address, and line items are usually read together:

~~~json
{
  "_id": "order-2026-000123",
  "customerId": "customer-42",
  "status": "PENDING_PAYMENT",
  "placedAt": "2026-11-21T12:30:00Z",
  "currency": "VND",
  "deliveryAddress": {
    "recipient": "Nguyen Van A",
    "phone": "0900000000",
    "line1": "12 Nguyen Trai",
    "city": "Ho Chi Minh City",
    "countryCode": "VN"
  },
  "items": [
    {
      "productId": "product-15",
      "skuSnapshot": "HEADPHONE-A",
      "nameSnapshot": "Headphone A",
      "quantity": 1,
      "unitPrice": 500000
    }
  ],
  "totals": {
    "subtotal": 500000,
    "discount": 0,
    "shipping": 20000,
    "tax": 0,
    "grandTotal": 520000
  }
}
~~~

Embedding line items and shipping address lets an order be read in a single query. Line items can also carry historical snapshots just like in the relational model.

However, do not embed the entire product catalog, payment history, and every inventory record inside the order document:

- The catalog is referenced by many orders and evolves independently.
- Payments can occur multiple times, involving webhooks and dedicated reconciliation workflows.
- Inventory is updated concurrently by competing orders. A dedicated inventory document per product–warehouse is far easier to control than inventory copies inside orders.
- Documents with unbounded growing arrays become large, awkward to paginate, and prone to write contention.

You can use documents for orders and separate collections for products, payments, and inventory. Even with a document model, rules like unique SKUs, idempotency, preventing overselling, and preserving history must still be enforced using indexes, transactions, conditional updates, or appropriate application logic.

## 8. If Choosing a Graph Database

A graph database like Neo4j fits when the central questions involve paths and connections across many entities.

Sales data can be modeled with nodes and relationships:

- Nodes: **Customer**, **Product**, **Category**, **Order**, **Warehouse**.
- Relationships: **PLACED**, **CONTAINS**, **BELONGS_TO**, **STOCKED_AT**, **BOUGHT_WITH**.
- Properties on the **CONTAINS** relationship can include quantity and price at purchase time.

For example, to find products frequently bought together with a given product:

~~~cypher
MATCH (p:Product {sku: $sku})<-[:CONTAINS]-(o:Order)
      -[:CONTAINS]->(related:Product)
WHERE related <> p
RETURN related.sku, related.name, count(DISTINCT o) AS orderCount
ORDER BY orderCount DESC
LIMIT 10;
~~~

Graphs make multi-hop traversal queries natural—such as finding customers sharing addresses, co-purchased products, ancestor categories, or fraud networks.

If most operations involve creating orders, recording payments, and updating stock counts, a relational database usually makes foreign keys, transactions, and arithmetic constraints simpler to enforce. A graph can complement the system for recommendations, relationship exploration, or anomaly detection. There is no need to move the entire system to a graph just because data has relationships.

## 9. If Choosing an Analytical Model

Transactional databases optimize for single-order operational workflows. Reports such as monthly revenue, revenue by category, refund rates, or end-of-day inventory typically scan and aggregate large volumes of historical data. A star-schema analytical model serves these questions much more effectively.

Example:

| Analytical Table | Grain | Contents |
|---|---|---|
| **FactSales** | One order line item | Quantity, pre- and post-discount revenue, taxes |
| **FactPayment** | One payment or refund transaction | Amount, status, timestamp, provider |
| **FactInventorySnapshot** | One product at one warehouse at a snapshot time | On-hand, reserved, and available quantities |
| **DimCustomer** | One version of a customer profile | Segment, region, analytical attributes |
| **DimProduct** | One version of a product | SKU, name, brand, product group |
| **DimCategory** | One version of a category | Category hierarchy |
| **DimDate** | One calendar day | Day, week, month, quarter, year |
| **DimWarehouse** | One warehouse | Warehouse code, region |

**FactSales** typically stores keys to dimensions alongside additive measures. **DimProduct** or **DimCustomer** can use Slowly Changing Dimension Type 2 to preserve attribute history: when a product name or customer segment changes, insert a new dimension version with an effective interval instead of overwriting history.

Define the grain before designing any fact table. If one row in **FactSales** represents a line item, never mix in an order-level-only measure and sum across lines, or order totals will be multiplied. Payments and inventory snapshots have different grains and therefore belong in separate fact tables.

Analytical models can be populated in batches or via event streams from transactional systems. Avoid letting heavy reporting queries directly impact order placement and inventory reservation paths.

## 10. Comparing Structures to Choose Wisely

| Criterion | Relational | Document | Graph | Analytical |
|---|---|---|---|---|
| Primary focus | Structured records, relationships, and constraints | Aggregates and nested data | Paths and relationship networks | Historical aggregation and measurement |
| Strengths | Foreign keys, transactions, joins, consistency | Convenient aggregate reads, flexible schema | Natural multi-hop relationship queries | Large-scale scans, aggregation, and analysis |
| Fit in this example | Orders, payments, inventory | Order detail documents | Product recommendations, customer links | Revenue, category performance, stock trends |
| Watch-outs | Join design, indexes, migrations | Document size, concurrent updates, duplication | Sync overhead and balance-update queries | Grain, data latency, dimension history |

A production system may combine multiple models. For example, PostgreSQL serves as the transactional source of truth; an analytical warehouse ingests events or CDC streams; a graph powers recommendations; a document store holds certain flexibly structured content. Every copy requires a defined source of truth, synchronization rules, and late-arriving data handling.

## 11. Designing Indexes from Queries

Indexes must come from real queries. Common patterns include:

- Customer viewing recent orders: **(customer_id, placed_at DESC, order_id DESC)**.
- Looking up a product by SKU: **UNIQUE(sku)**.
- Finding products by category: **(category_id, product_id)** on the join table.
- Listing payments by order and status: **(order_id, status)**.
- Inspecting movements for a product in a warehouse: **(product_id, warehouse_id, created_at DESC)**.
- Fetching inventory for a warehouse: **(warehouse_id, product_id)**.

Do not index every column. Indexes consume storage and slow down `INSERT`, `UPDATE`, and `DELETE`. Once representative data exists, inspect execution plans with **EXPLAIN (ANALYZE, BUFFERS)** and measure latency on critical queries.

Foreign key columns on the referencing side often need indexes when used in joins, filters, or referential checks during parent deletes/updates. PostgreSQL does not automatically create indexes on foreign key columns.

## 12. Making the Model Evolvable

Store operations will evolve. An evolvable model needs strategies for common changes:

- **Adding product variants:** separate **Product** and **ProductVariant** if each color or size has its own SKU and inventory.
- **Multiple price lists:** add **PriceList** or **ProductPrice** with effective timeframes instead of overwriting active prices.
- **Multiple shipping methods:** introduce a separate shipment or delivery entity if one order can split into multiple parcels.
- **Returns:** add **Return** and **ReturnItem**; record a **RETURN** inventory movement when goods are physically restocked.
- **Multi-currency orders:** store currency codes on orders, payment lines, and exchange-rate rules; never add amounts across different currencies directly.
- **Status history:** if auditing is required, add an **OrderStatusHistory** table recording old status, new status, timestamp, and actor.
- **Multiple warehouses or transfers:** record paired outbound and inbound movements in the same transaction or stateful workflow so stock is neither created nor lost mid-transfer.

When running migrations on a live system, favor expand–contract workflows:

1. Add new columns or tables in a state compatible with the currently running application version.
2. Deploy application code able to read/write the new structure; perform controlled dual-writes if needed.
3. Backfill historical data in batches and verify row counts, monetary totals, and foreign keys.
4. Switch read queries to the new structure after reconciliation.
5. Remove old structures only after no running application version uses them.

Never change the meaning of an existing column without data migration and a compatibility plan. For order or payment statuses, enforce valid state transitions; do not let arbitrary endpoints write unconstrained status strings.

## 13. Validating the Model with Questions and Invariants

Before considering the design complete, test whether you can answer these questions through queries or data checks:

- Can an order exist without a valid customer?
- Can two products share the same SKU?
- Can the same product be assigned to the same category twice?
- Can a line item have quantity 0 or a negative price?
- Does the order grand total match subtotal, discounts, shipping fees, and taxes?
- Can two concurrent requests reserve the same item beyond available quantity?
- Can a retried webhook delivery record the same payment twice?
- Does renaming a product alter past invoices?
- Can inventory balances be traced back to recorded movements?
- Does a revenue report double-count order-level totals when joining multiple line items?

Critical invariants should be enforced as close to the data as possible:

| Invariant | Protection Mechanism |
|---|---|
| Unique SKU | **UNIQUE** on **product.sku** |
| Line items belong to valid orders and products | **FOREIGN KEY** |
| Positive line-item quantity | **CHECK (quantity > 0)** |
| Discount does not exceed line value | **CHECK** on **order_item** |
| Reservations never exceed on-hand stock | **CHECK** on **inventory** plus conditional update |
| No duplicate payment processing | Idempotency keys and unique provider references |
| Valid component arithmetic for totals | **CHECK** on order; reconcile line sums inside transaction |
| Auditable inventory changes | Write **inventory_movement** in the same transaction as balance updates |

Periodic checks remain necessary for invariants spanning multiple tables or external systems. For instance, compare **inventory** balances against the sum of **inventory_movement**, compare line-item totals against **sales_order.subtotal**, and reconcile internal payment records against provider settlement reports.

## 14. Practical Workflow for Similar Problems

When facing a new business requirement, follow this sequence:

1. **Gather rules:** explicitly document who creates data, who reads it, its lifecycle, and validity conditions.
2. **Identify entities:** find nouns with distinct identities and lifecycles; avoid turning every attribute group into a table.
3. **Define relationships and cardinality:** one-to-one, one-to-many, or many-to-many; mandatory or optional.
4. **Choose keys:** distinguish technical keys from business codes; define uniqueness scopes.
5. **Normalize:** eliminate repeating groups and improper dependencies; decide which fields are intentional historical snapshots.
6. **Place constraints:** use data types, **NOT NULL**, **CHECK**, **UNIQUE**, and **FOREIGN KEY** to express rules.
7. **Simulate concurrent transactions:** check contested flows like stock reservation, code allocation, and payment recording.
8. **Design indexes from queries:** choose column order from real filters, joins, and sort clauses.
9. **Compare storage models:** use relational, document, graph, or analytical paradigms according to workload; combine them when sync boundaries are clear.
10. **Plan evolution:** migrations, backfills, reconciliation, version compatibility, and rollback capability.

A sound data model lets the team answer business questions accurately, block invalid data at the storage layer, and support change without breaking history. In this retail example, a relational model provides the right foundation for orders, payments, and inventory; document, graph, and analytical models can complement the areas where their access patterns fit better.
