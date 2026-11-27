# From Business Requirements to Aggregate Diagrams and Relational Schemas

In Spring Data JDBC, data modeling should begin from **business rules and consistency boundaries** before moving to Java classes and SQL tables. If you start from a list of tables or foreign key relationships, it is easy to turn a large relational graph into a single aggregate, making reading, saving, and change control expensive.

This lesson walks through a repeatable process:

1. Gather usage scenarios and domain terminology.
2. Write down **invariants** that must always hold true.
3. Choose the **aggregate root** and identify the data it owns.
4. Distinguish **aggregate members** from **references to other aggregates**.
5. Draw the aggregate diagram, then map it to tables, primary keys, and foreign keys.
6. Implement the model with Spring Data JDBC, repositories, and transactions.
7. Anticipate the impact of design decisions on queries, concurrent updates, and schema changes.

The running example is a sales system allowing customers to create draft orders, add products, adjust quantities, and confirm orders. Names such as `SalesOrder`, `OrderLine`, `Customer`, and `Product` are merely sample names; the same design process applies to bookings, stock receipts, invoices, or other business records.

## 1. Start With Business Requirements, Not Entities

Suppose the product team describes the system as follows:

> A customer can create many orders. Each order has many product lines. While an order is in draft status, the customer may add, edit, or remove lines. An order line must have a positive quantity and a selling price locked at the time it is added to the order. An empty order cannot be confirmed. After confirmation, users cannot arbitrarily alter order lines. Customers and the product catalog are managed independently of orders.

Before writing `@Table` or DDL, break the description into boundary-deciding questions:

- **Which operations need immediate consistency guarantees?** For example, preventing empty order confirmation, or preventing line edits on a confirmed order.
- **Which objects share a lifecycle?** An order line belongs to exactly one order; if the order is deleted, the line usually loses independent meaning.
- **Which objects have their own lifecycle?** Customers and products continue existing even if an order is cancelled.
- **What historical data must remain unchanged?** Product prices inside placed orders must not silently change when the current price list updates.
- **What happens concurrently?** Two operations may edit the same order simultaneously; overwriting each other's changes must be prevented.
- **Read-only or write?** Analytics screens may need to join multiple tables, yet joining on reads does not mean those tables belong to one aggregate.

These questions help avoid equating a business relationship with an ownership relationship in the aggregate model.

## 2. Translate Requirements Into Use Cases and Invariants

A **use case** describes what a user or system wants to accomplish. An **invariant** describes what must always hold true after a business operation completes.

| Use case | Data read/modified | Invariant to protect |
|---|---|---|
| Create draft order | Selected customer, order status | Order belongs to a valid customer |
| Add product | Order lines, current product price info | Quantity > 0, non-negative price, order must still be draft |
| Edit quantity | One line in the order | Confirmed orders cannot be edited; new quantity is valid |
| Remove line | Line list | Only editable while order is draft |
| Confirm order | Status and all lines | Do not confirm an empty order; every line is valid |
| Display order history | Order and locked-in price info | Catalog price changes do not alter prices on old orders |
| Rename customer | Customer profile | No need to rewrite all of the customer's orders |

Invariants guide the decision: if a rule requires simultaneously inspecting order status and order lines, that data is a strong candidate to sit **inside the same aggregate**.

Conversely, renaming a customer does not require simultaneously updating every placed order. This supports keeping `Customer` as a separate aggregate.

### 2.1. Distinguishing Aggregate Invariants From Cross-Aggregate Rules

Rules can be divided into two groups:

**Internal invariants of an order**

- An order has a clear status: `DRAFT`, `CONFIRMED`, or `CANCELLED`.
- Every line has a positive quantity.
- Confirmed orders disallow modifying lines via draft-editing operations.
- An order without lines cannot be confirmed.

These can be enforced directly by methods on `SalesOrder`.

**Rules involving other aggregates**

- `customerId` must point to a customer allowed to purchase.
- `productId` must correspond to an orderable product.
- Price is retrieved from the product catalog when added to the order.
- Inventory checking and reservation follow the warehouse system's rules.

These rules require application services, other repositories, or workflow coordination. A single `orderRepository.save(order)` call does not by itself verify, update, or lock every other aggregate.

## 3. Choose Aggregate Roots Based on Consistency Boundaries

An **aggregate** is a collection of domain objects treated as one consistency unit when making changes. The **aggregate root** is the entry point responsible for controlling modifications within that collection.

For the sales example:

- `SalesOrder` is the **aggregate root**: owns order status and the list of lines.
- `OrderLine` is a member inside the `SalesOrder` aggregate and must not be changed arbitrarily outside the root's domain methods.
- `Customer` is an independent aggregate root.
- `Product` is an independent aggregate root.

An order line normally does not need its own repository; to update a line, the application loads `SalesOrder`, invokes domain behavior, and saves `SalesOrder` back.

Conceptual diagram:

~~~mermaid
flowchart LR
    subgraph OA["Aggregate: SalesOrder"]
        O["SalesOrder (root)"]
        L["OrderLine (0..n)"]
        O -->|"owns, controls lifecycle"| L
    end

    subgraph CA["Aggregate: Customer"]
        C["Customer (root)"]
    end

    subgraph PA["Aggregate: Product"]
        P["Product (root)"]
    end

    O -.->|"customerId"| C
    L -.->|"productId"| P
~~~

Solid arrows represent **ownership within the same aggregate**. Dashed arrows represent **references by identifier to another aggregate**.

This is a business boundary diagram, not yet a database ERD. ID-based references can still be protected in the database by foreign keys without merging both sides into the same aggregate.

### 3.1. Why Not Put Customer and Product Inside SalesOrder?

Suppose an order contains 20 products. Pulling every `Product` along with stock details, current prices, categories, and history into `SalesOrder` would bloat the aggregate. Every time the order is edited, loading and saving could touch large amounts of data outside the order's lifecycle.

Furthermore, the same `Product` is referenced by many orders. Changing a product's name or price should not require updating every existing order aggregate.

Thus, each `OrderLine` holds `productId` and **snapshot** information needing historical preservation, such as `skuSnapshot` and `unitPrice`. Current name/price remain in the `Product` aggregate.

### 3.2. An Aggregate Is Not Synonymous With One Table

One aggregate can span multiple tables: `SalesOrder` has a root table and a line-items table. Conversely, a database can establish a foreign key between two tables belonging to **two different aggregates**.

Relational tables describe data integrity at the storage level. Aggregates describe which **business operations must be managed within a single consistency boundary**.

## 4. Write the Domain Model Before Writing the Schema

From the analysis above, the model can be summarized in a design table:

| Concept | Role | Key attributes | Who has authority to change? |
|---|---|---|---|
| `SalesOrder` | Aggregate root | `id`, `version`, `customerId`, `status`, `lines` | Behaviors on `SalesOrder` |
| `OrderLine` | Member of the order | `productId`, `skuSnapshot`, `quantity`, `unitPrice` | Through the `SalesOrder` root |
| `Customer` | Independent aggregate | `id`, customer profile | Customer management workflows |
| `Product` | Independent aggregate | `id`, `sku`, current price | Product catalog workflows |

**Behavior matters more than getters/setters.** Instead of letting the application service call `order.getLines().clear()` or `order.setStatus(...)`, the root can provide:

~~~text
SalesOrder.createDraft(customerId)
SalesOrder.addLine(productId, skuSnapshot, quantity, unitPrice)
SalesOrder.changeQuantity(lineIndex, newQuantity)
SalesOrder.removeLine(lineIndex)
SalesOrder.confirm()
SalesOrder.totalAmount()
~~~

Each method protects its relevant business rules. Collection fields should be encapsulated so external code cannot mutate them directly while bypassing root checks.

### 4.1. Current Price vs. Historical Price

The current price lives on `Product`; the actual price chosen for an order line lives on `OrderLine.unitPrice`.

Example:

~~~text
Day 1: Product #20 costs 120.000
       Order #15 adds Product #20
       OrderLine.unitPrice = 120.000

Day 8: Product #20 changes price to 135.000
       Order #15's OrderLine still keeps price 120.000
~~~

If you only stored `productId` and always joined `Product` to fetch price when calculating totals, order history would change unintentionally. Price snapshotting is a business decision, not merely query optimization.

### 4.2. Total Amount: Derived From Lines or Stored as a Column?

In this example, the order total is derived from the lines:

\[
\text{totalAmount}=\sum_{i=1}^{n} \text{quantity}_i\times\text{unitPrice}_i
\]

You can implement `totalAmount()` on the root and omit a `total_amount` column to avoid maintaining two data sources that might drift out of sync.

If reporting or performance requirements genuinely demand storing the total amount, add a rule to **recalculate the total alongside every line change** and consider how to verify consistency. Adding a precomputed column is not mandatory in every design.

## 5. From Aggregate Diagram to Relational Schema

Only once boundaries are clear do we decide tables and keys.

Proposed mapping:

| Aggregate / member | Relational table | Key | Link |
|---|---|---|---|
| `Customer` | `customers` | `id` | Independent |
| `Product` | `products` | `id` | Independent |
| `SalesOrder` | `sales_orders` | `id` | `customer_id` references `customers.id` |
| `OrderLine` in order | `sales_order_lines` | `(order_id, line_no)` | `order_id` links to root; `product_id` references `products.id` |

In this example, an `OrderLine` is identified within an order by its `line_no` position in the list. It has no separate lifecycle or repository. If business rules require a stable identifier for each line regardless of reordering, pick a different key design instead of treating list position as an immutable business ID.

Relational diagram:

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ SALES_ORDERS : "customer_id"
    SALES_ORDERS ||--o{ SALES_ORDER_LINES : "order_id"
    PRODUCTS ||--o{ SALES_ORDER_LINES : "product_id"

    CUSTOMERS {
        bigint id PK
        varchar display_name
    }
    PRODUCTS {
        bigint id PK
        varchar sku
        numeric current_price
    }
    SALES_ORDERS {
        bigint id PK
        bigint version
        bigint customer_id FK
        varchar status
    }
    SALES_ORDER_LINES {
        bigint order_id PK,FK
        integer line_no PK
        bigint product_id FK
        varchar sku_snapshot
        integer quantity
        numeric unit_price
    }
~~~

Connectors in the ERD are **physical data relationships**. The `Customer → SalesOrder` or `Product → OrderLine` connector does not imply that Customer or Product is owned by the order aggregate.

### 5.1. Sample DDL for PostgreSQL

The SQL below is a minimal starting schema. In production applications, manage it using Flyway or Liquibase.

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    current_price NUMERIC(15, 2) NOT NULL
        CHECK (current_price >= 0)
);

CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_order_status
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
);

CREATE TABLE sales_order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    sku_snapshot VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,

    CONSTRAINT pk_order_line
        PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES sales_orders (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_order_line_product
        FOREIGN KEY (product_id) REFERENCES products (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_order_line_no
        CHECK (line_no >= 0),
    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_line_price
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_sales_orders_customer
    ON sales_orders (customer_id);

CREATE INDEX idx_order_lines_product
    ON sales_order_lines (product_id);
~~~

**Meaning of the constraints:**

- `PRIMARY KEY (order_id, line_no)`: each line position appears at most once per order.
- `FOREIGN KEY (order_id)`: every line must belong to an existing order.
- `ON DELETE CASCADE` on `order_id`: at the database level, lines are not orphaned if an order is deleted. This is a data safety net; Spring Data JDBC still manages child component lifecycles per the aggregate.
- `FOREIGN KEY (customer_id)` and `FOREIGN KEY (product_id)`: protect referential integrity when aggregates share the same database and business rules require it.
- `ON DELETE RESTRICT` for Customer/Product: prevents deleting records still referenced by historical orders. Systems can use soft deactivation instead of physical deletion.
- `CHECK`: reinforces invariants verifiable within a single SQL row.
- `version`: supports optimistic locking on the aggregate root.

**Limitation of CHECK:** `CHECK (quantity > 0)` validates each individual row; however, "only confirm when there is at least one line" depends on root state and child row count. With this simple schema, that rule is protected primarily at the domain/application layer; if multiple direct database write paths exist, additional enforcement mechanisms are needed.

### 5.2. Ordering and Lifecycle of OrderLine

The `line_no` column pairs with Java's `List<OrderLine>`, reflecting element positions. Ordering can shift when removing, inserting, or reordering list items. Consequently:

- Do not use `line_no` as a long-lived identifier when other systems hold references to individual lines.
- If the business needs to edit a line using a stable code, design a dedicated identifier and check how Spring Data JDBC maps child keys.
- Do not automatically add a separate repository for OrderLine if it still belongs to SalesOrder's lifecycle.

Other collection types such as `Set` or `Map` lead to different key mappings; design columns and uniqueness accordingly.

## 6. Mapping the Aggregate With Spring Data JDBC

The example uses Spring Data Relational annotations:

- `@Table`: table name.
- `@Id`: primary key of the aggregate root.
- `@Version`: optimistic locking control.
- `@Column`: column name when specified explicitly.
- `@MappedCollection`: how a child collection links to the root via ID column and element key.

Do not use JPA's `@OneToMany` or `@ManyToOne` expecting Spring Data JDBC to provide a Hibernate-like persistence context, lazy proxies, or cascade strategies.

### 6.1. Order Status Enum

~~~java
package com.example.shop.order.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

In this example, the status maps to the enum name matching the `status` column values in DDL.

### 6.2. OrderLine Component

~~~java
package com.example.shop.order.domain;

import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_order_lines")
public class OrderLine {

    @Column("product_id")
    private Long productId;

    @Column("sku_snapshot")
    private String skuSnapshot;

    private int quantity;

    @Column("unit_price")
    private BigDecimal unitPrice;

    private OrderLine() {
        // For the materialization mechanism when reading from the database.
    }

    public OrderLine(
            Long productId,
            String skuSnapshot,
            int quantity,
            BigDecimal unitPrice
    ) {
        if (productId == null) {
            throw new IllegalArgumentException("Product id is required");
        }
        if (skuSnapshot == null || skuSnapshot.isBlank()) {
            throw new IllegalArgumentException("SKU snapshot is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        Objects.requireNonNull(unitPrice, "Unit price is required");
        if (unitPrice.signum() < 0 || unitPrice.scale() > 2) {
            throw new IllegalArgumentException(
                    "Unit price must be non-negative and have up to 2 decimals"
            );
        }

        this.productId = productId;
        this.skuSnapshot = skuSnapshot;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getProductId() {
        return productId;
    }

    public String getSkuSnapshot() {
        return skuSnapshot;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }

    public OrderLine withQuantity(int newQuantity) {
        return new OrderLine(
                productId, skuSnapshot, newQuantity, unitPrice
        );
    }
}
~~~

This class has no `@Id` of its own. In this example, it is managed as a member belonging to `SalesOrder`. When modifying quantity, the root can replace the `OrderLine` at that index so invariant checks remain inside the root's domain method.

**Note on currency:** `NUMERIC(15,2)` is used to keep the example simple. Systems handling multiple currencies or differing rounding rules should add a currency field and a dedicated money data type/value object; do not casually assume every currency uses two decimal places.

### 6.3. Aggregate Root SalesOrder

~~~java
package com.example.shop.order.domain;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    @Column("customer_id")
    private Long customerId;

    private OrderStatus status;

    @MappedCollection(
            idColumn = "order_id",
            keyColumn = "line_no"
    )
    private List<OrderLine> lines = new ArrayList<>();

    private SalesOrder() {
        // Used when Spring Data JDBC constructs the aggregate from persisted data.
    }

    public SalesOrder(Long customerId) {
        if (customerId == null) {
            throw new IllegalArgumentException("Customer id is required");
        }
        this.customerId = customerId;
        this.status = OrderStatus.DRAFT;
    }

    public void addLine(
            Long productId,
            String skuSnapshot,
            int quantity,
            BigDecimal unitPrice
    ) {
        requireDraft();
        lines.add(new OrderLine(
                productId, skuSnapshot, quantity, unitPrice
        ));
    }

    public void changeQuantity(int lineIndex, int newQuantity) {
        requireDraft();
        OrderLine current = lines.get(lineIndex);
        lines.set(lineIndex, current.withQuantity(newQuantity));
    }

    public void removeLine(int lineIndex) {
        requireDraft();
        lines.remove(lineIndex);
    }

    public void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot confirm an order without lines"
            );
        }
        status = OrderStatus.CONFIRMED;
    }

    public BigDecimal totalAmount() {
        return lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be changed"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

`confirm()` forces the root's status and lines to stay consistent. `getLines()` returns a list that cannot be mutated directly from outside; business code must call the aggregate's methods.

Pay attention to `@MappedCollection`:

- `idColumn = "order_id"`: each child line stores the parent `SalesOrder`'s ID.
- `keyColumn = "line_no"`: column recording the positional key for `List<OrderLine>`.
- `OrderLine` is an **owned** member of the root, unlike an independent `Product` referenced via `productId`.

In Spring Data JDBC, child collections belonging to an aggregate are loaded via the aggregate read operation, not via JPA-style lazy proxies. When re-saving an existing aggregate, Spring Data JDBC may delete and recreate child rows to match the collection state; it does not dirty-check individual fields of each entity like JPA. Anticipate this cost when deciding aggregate size.

### 6.4. Repository Only for the Aggregate Root

~~~java
package com.example.shop.order.repository;

import com.example.shop.order.domain.SalesOrder;
import org.springframework.data.repository.CrudRepository;

public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {
}
~~~

We save the aggregate via its root:

~~~java
SalesOrder order = new SalesOrder(customerId);
order.addLine(productId, "SKU-100", 2, new BigDecimal("125.00"));

SalesOrder saved = salesOrderRepository.save(order);
Long orderId = saved.getId();
~~~

The snippet above assumes `customerId` and `productId` have already been validated at the application layer. Always use the object returned by `save(...)`, especially in immutable models or when IDs/versions are generated by the persistence layer.

Avoid creating an `OrderLineRepository` just to call `save(line)` directly if `OrderLine` is a component that must not change independently. Doing so can bypass root invariants.

## 7. Application Service Connects Aggregates via IDs

The aggregate root protects **internal** invariants. The application service coordinates repositories and transactions to execute use cases.

The product repository can be declared independently:

~~~java
package com.example.shop.catalog.repository;

import com.example.shop.catalog.domain.Product;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {
}
~~~

In the example, `Product` is a separate aggregate with getters `getId()`, `getSku()`, and `getCurrentPrice()`. To add a product to an order, the service reads Product's current price and copies that price into OrderLine:

~~~java
package com.example.shop.order.service;

import com.example.shop.catalog.domain.Product;
import com.example.shop.catalog.repository.ProductRepository;
import com.example.shop.order.domain.SalesOrder;
import com.example.shop.order.repository.SalesOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final SalesOrderRepository orderRepository;
    private final ProductRepository productRepository;

    public OrderApplicationService(
            SalesOrderRepository orderRepository,
            ProductRepository productRepository
    ) {
        this.orderRepository = orderRepository;
        this.productRepository = productRepository;
    }

    @Transactional
    public Long createDraft(Long customerId) {
        // Validate customerId beforehand according to business policy.
        SalesOrder order = new SalesOrder(customerId);
        return orderRepository.save(order).getId();
    }

    @Transactional
    public void addProduct(
            Long orderId,
            Long productId,
            int quantity
    ) {
        Product product = productRepository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + productId
                ));

        SalesOrder order = orderRepository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId
                ));

        order.addLine(
                product.getId(),
                product.getSku(),
                quantity,
                product.getCurrentPrice()
        );
        orderRepository.save(order);
    }

    @Transactional
    public void confirm(Long orderId) {
        SalesOrder order = orderRepository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId
                ));

        order.confirm();
        orderRepository.save(order);
    }
}
~~~

Flow for adding a product:

~~~text
ApplicationService.addProduct(orderId, productId, quantity)
        |
        +-- ProductRepository.findById(productId)
        |      -> read SKU and current price
        |
        +-- SalesOrderRepository.findById(orderId)
        |      -> load root and aggregate members
        |
        +-- SalesOrder.addLine(productId, sku, quantity, price)
        |      -> validate internal invariants
        |
        +-- SalesOrderRepository.save(order)
               -> persist aggregate state
~~~

Reading `Product` is solely to **retrieve current product information**, not to bring Product under SalesOrder's ownership. After saving, OrderLine holds the price snapshot used by the order.

### 7.1. How to Handle Concurrent Price Changes?

If a product's price changes after the service loads `Product` but before saving `SalesOrder`, the system needs a clear policy: accept the price snapshot at read time, re-verify at confirmation, or use a price-list version/locked quote from a pricing service.

There is no single "right" aggregate boundary that solves every pricing policy. What matters is that business requirements explicitly specify **the moment price becomes a commitment** along with an appropriate consistency mechanism.

### 7.2. Inventory Does Not Automatically Live Inside the Order

Inventory usually belongs to another aggregate or service. Order confirmation may need to reserve stock, pre-authorize payment, or reject when out of stock.

If orders and inventory reside in the same database, the application service can coordinate multiple repository operations in one transaction if atomicity requirements and locking strategies permit. If components reside in different services/databases, a recoverable workflow such as reservations, events, and an outbox is needed.

**One transaction can touch multiple aggregates, yet Spring Data JDBC does not automatically construct cross-aggregate workflows from ID references alone.** That remains an architectural decision driven by business requirements.

## 8. Controlling Concurrent Updates With @Version

Suppose two requests concurrently load Order #15 while it is still on an older version:

~~~text
Transaction A            Transaction B
-------------            -------------
Read Order #15, v3       Read Order #15, v3
Add line A               Add line B
save(order) -> succeeds
                         save(order) -> version conflict
~~~

Without a mechanism to prevent lost updates, the later write can overwrite the state from the earlier write. `@Version` on the root allows Spring Data JDBC to perform **optimistic locking**: the update succeeds only if the persisted version still matches; if the version changed, the framework can throw an `OptimisticLockingFailureException`-family error.

Invariants and versioning solve two different problems:

- Domain methods ensure **a single order's state is valid**.
- Optimistic locking helps prevent **two users editing the same stale copy from silently overwriting each other**.

The application must choose a conflict-handling policy: notify the user, reload and ask for confirmation, or retry when the operation is safe and idempotent. Never blindly retry operations with side effects such as submitting payments.

`@Transactional` still manages transactions and rollbacks when needed, even though Spring Data JDBC has no JPA-style persistence context or dirty checking. Mutating a Java object does not automatically write SQL; the service must call `save(...)`.

## 9. Aggregate Persistence Cost and Size Decisions

Spring Data JDBC prioritizes aggregate consistency lifecycles. When saving an existing aggregate with a child entity collection, the framework often performs child writes such as deleting and re-inserting to reflect the new state, rather than tracking field-level diffs like JPA dirty checking.

With a 5-line order, re-saving the collection is acceptable. With an aggregate containing 50,000 lines changing one line per second, this design can produce excessive SQL operations.

Evaluate before placing a collection under the same root:

| Question | If the answer is "yes" |
|---|---|
| Must elements be kept consistent with the root in a single business operation? | Strong reason for them to share an aggregate |
| Do elements have independent lifecycles needing edits by separate use cases? | Consider a separate aggregate |
| Can element count grow very large? | Measure read/write costs and review boundaries |
| Is only a multi-table report needed? | Build a read query/DTO; no need to merge aggregates |
| Do other systems directly reference individual elements? | Consider stable IDs and an independent lifecycle |
| Is a transaction spanning multiple aggregates required? | Design application services and explicit consistency |

For example, a bank account with years of history should not by default keep every ledger entry in a child collection loaded and re-saved on every balance update. The nature of the domain may call for a different aggregate model or a dedicated append-only mechanism.

## 10. Schemas for Writing and Queries for Reading

Aggregates govern how **write operations are protected**, without prohibiting SQL joins on reads.

For example, an order history screen needs ID, status, line count, and total amount:

~~~sql
SELECT
    o.id,
    o.customer_id,
    o.status,
    COUNT(l.line_no) AS line_count,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM sales_orders o
LEFT JOIN sales_order_lines l ON l.order_id = o.id
WHERE o.customer_id = :customerId
GROUP BY o.id, o.customer_id, o.status
ORDER BY o.id DESC;
~~~

You can use `NamedParameterJdbcTemplate` or an appropriate repository query/DTO to fetch this report, instead of instantiating every full `SalesOrder` just to display a few columns.

Notably, read queries can join `Customer` and `Product` too without **altering aggregate boundaries**. The aggregate diagram is the consistency model for writes; SQL projections are optimized read models for specific screens.

In large systems, designing dedicated read models can be helpful; in simpler systems, an explicit SQL query may already suffice.

## 11. Common Design Mistakes

### 11.1. "There Is a Foreign Key, So They Must Share One Aggregate"

Flawed reasoning. The foreign key `sales_orders.customer_id → customers.id` protects reference validity, yet `Customer` can still be an independent aggregate.

Determine ownership via lifecycle and invariants, not solely from table relationships.

### 11.2. "Every Table Needs a Repository"

Not necessary. `OrderLine` belongs to `SalesOrder` and is therefore normally operated on through `SalesOrderRepository`. Creating independent CRUD for `OrderLine` can undermine root control.

### 11.3. "One Aggregate Always Equals One Table"

Incorrect. `SalesOrder` and `OrderLine` belong to the same aggregate yet are stored across two separate tables.

### 11.4. "Every Related Object Must Be Embedded Inside the Aggregate"

No. `Product` is referenced by many orders and has its own lifecycle. Storing `productId` alongside a historical snapshot is more natural than putting the full Product inside SalesOrder.

### 11.5. "With @Transactional, Mutated Objects Save Automatically"

No. Spring Data JDBC does not use JPA-style dirty checking. After calling domain methods, the application service must still call a write operation such as `repository.save(order)`.

### 11.6. "save Only Updates the Single Changed Row"

You cannot assume this for collections belonging to an aggregate. Understand Spring Data JDBC's persistence strategy and inspect SQL volume when choosing aggregate size.

### 11.7. "Everything Must Be Consistent Inside One Aggregate"

Expanding an aggregate to swallow customers, orders, products, inventory, and payments can make the system very hard to operate. Keep only invariants that truly must be controlled with the root; cross-aggregate workflows are handled with appropriate transactions or orchestration.

### 11.8. "The Schema Enforces All Business Logic on Its Own"

SQL constraints protect `NOT NULL`, `UNIQUE`, `CHECK`, and `FOREIGN KEY` well. Yet rules depending on multiple rows, business timing, or external systems generally require domain and application-layer logic, sometimes paired with locking or advanced database constraints.

## 12. A Design Process Applicable to Other Projects

When translating a new requirement into a Spring Data JDBC aggregate, you can write a design note following this template:

**Step 1 — Summarize a business scenario.** State who acts, expected outcomes, and which states are allowed to change.

**Step 2 — List invariants.** Phrase them as verifiable statements, such as "Cannot confirm an empty voucher", "Total equals sum of lines", "Cannot edit voucher after locking."

**Step 3 — Identify lifecycles.** Which objects are created/deleted together? Which objects are referenced by multiple workflows or other aggregates?

**Step 4 — Choose the root and child members.** The root should provide purposeful domain behaviors. Do not let external code arbitrarily mutate collections and status.

**Step 5 — Mark cross-aggregate references.** Use IDs rather than nesting full domain objects. Decide whether historical data snapshots are needed.

**Step 6 — Draw the aggregate diagram.** Show ownership boundaries and ID reference paths using two distinct line styles.

**Step 7 — Translate to schema.** Choose tables, columns, keys, indexes, foreign keys, delete policies, and constraints pushable to the database.

**Step 8 — Map in Spring Data JDBC.** Use `@Id`, `@Table`, `@MappedCollection`, and `@Version` where appropriate. Repositories are created for roots.

**Step 9 — Design services and transactions.** Services coordinate independent aggregates; roots protect internal invariants.

**Step 10 — Review change scenarios.** Estimate child row counts, write frequencies, concurrent contention, reporting read needs, and external system limits.

Minimum expected flow:

~~~text
Business requirements
    |
    v
Use cases + invariants
    |
    v
Aggregate boundary
    |       \
    |        \--> Other aggregates referenced only by ID
    v
Root + owned children diagram
    |
    v
Relational schema + constraints
    |
    v
Spring Data JDBC mapping
    |
    v
Repository + application service + transaction
~~~

## 13. Exercise: Reasoning From Another Requirement

Suppose a library system has:

- `Book`: book title info, shared across multiple branches.
- `LibraryMember`: reader info.
- `Loan`: borrowing slip, containing borrowed book lines and due date.
- Rules: cannot confirm an empty borrowing slip; after confirmation, borrowed lines cannot be altered arbitrarily; return status can be updated per business rules.

Determine for yourself:

1. Which aggregate root manages the borrowed book lines?
2. Should `Book` and `LibraryMember` live inside the `Loan` aggregate or be referenced by ID?
3. Which primary keys and foreign keys do the tables need?
4. Which rules belong in domain methods, and which belong in SQL constraints?
5. If borrowed lines could grow to tens of thousands, would the aggregate boundary still be appropriate?

One starting option makes `Loan` the root with `LoanItem` lines owned by the root, while `Book` and `LibraryMember` are independent aggregates. However, tracking returns per physical copy, preventing double-borrowing the same copy, or capping active borrowed books can lead to different aggregate boundaries and coordination mechanisms; always return to **actual invariants** before locking down the design.

## 14. Connecting the Decisions

When implementing the sales problem, the chain of decisions can be recorded as:

| Decision | Business rationale | Technical consequence |
|---|---|---|
| `SalesOrder` is the aggregate root | Order status and lines must stay consistent | Create `SalesOrderRepository` |
| `OrderLine` belongs to `SalesOrder` | Does not live independently of the order | `@MappedCollection`, child table has `order_id` |
| `Customer` is a separate aggregate | Customer profile has an independent lifecycle | Store `customerId`, optionally use foreign key |
| `Product` is a separate aggregate | Price/catalog is managed independently | Store `productId` and price snapshot |
| Order price is locked per line | Catalog price changes do not alter history | `unit_price` column in line table |
| `@Version` on the root | Prevent lost updates on concurrent edits | `version` column and optimistic locking handling |
| Total derived from lines | Avoid drift in precomputed values | Compute in domain or SQL projection |
| Independent reporting queries | Screens do not need to load full aggregate details | Read-only SQL joins/DTOs |

**Core mindset:** start from business operations and invariants, pick the root and child members, keep other aggregates as ID references, and only then draw ERDs and write mappings. With Spring Data JDBC, this approach aligns with aggregate-based persistence, keeping consistency boundaries clear and read/write costs predictable.
