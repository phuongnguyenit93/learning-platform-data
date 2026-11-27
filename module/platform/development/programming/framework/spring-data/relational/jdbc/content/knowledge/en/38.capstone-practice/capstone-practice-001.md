# Order Management Problem Analysis and Aggregate Boundary Identification

When designing an order management system with Spring Data JDBC, the first critical decision is not how many tables or repositories to create. You need to determine **which data must always stay consistent within a single business change**, which object owns that data, and which parts have an independent lifecycle.

An order typically involves customers, products, inventory, payments, and shipping. If you bundle everything into one large aggregate, every operation can become heavy and cause contention. If you split every table into a separate aggregate without considering invariants, the system can easily end up in an inconsistent state.

In Domain-Driven Design, an aggregate is a consistency boundary. The aggregate root is the single entry point for modifying entities belonging to the aggregate. Spring Data JDBC is built on this model: one repository represents one aggregate root; entities referenced from the root are treated as part of the aggregate and are persisted along with the root.

This lesson uses the order management problem to analyze requirements, identify invariants, choose aggregate roots, distinguish entities/value objects/references, and design repositories and transaction boundaries suited for Spring Data JDBC.

## 1. Order management problem description

An online store needs to support the following business operations:

- Customers browse products and selling prices.
- Customers create an order with multiple product lines.
- The system stores the shipping address and price information at the time the order is placed.
- The system checks and reserves inventory.
- The order is confirmed and paid.
- The warehouse prepares the items, creates a shipment, and updates the delivery status.
- Customers can cancel an order in permitted statuses.
- Staff can view history and process refunds.

An order can contain multiple products. A product can appear in multiple orders. A customer can have multiple orders. A product can have multiple price and inventory updates.

These relationships show that the relational model has many foreign keys, yet they do not tell us which aggregate should contain which.

### 1.1. Business concepts

| Concept | Meaning |
| --- | --- |
| Customer | Buyer and customer account information |
| Product | Product in the catalog, description, and current price |
| InventoryItem | Stock quantity of a SKU at a warehouse |
| Order | Order and business status of the order |
| OrderLine | A product line within an order |
| Payment | Payment transaction and payment status |
| Shipment | Delivery batch and shipping status |
| Address | Shipping or billing address |
| Money | Monetary amount along with currency unit |

This is a candidate list. Not every concept needs its own aggregate root; the final decision depends on lifecycles, invariants, and update patterns.

### 1.2. Order lifecycle

A simple order flow:

~~~text
DRAFT
  |
  v
PENDING_PAYMENT
  |
  +---- payment failed ----> PAYMENT_FAILED
  |
  v
PAID
  |
  v
FULFILLING
  |
  v
SHIPPED
  |
  v
DELIVERED
~~~

Order cancellation may be allowed from certain statuses, such as DRAFT or PENDING_PAYMENT. Once an order is SHIPPED, a cancellation request may need to become a return or refund workflow.

These states are domain rules. Every service should not be allowed to arbitrarily update a status column without checking state transitions.

## 2. An aggregate is a consistency boundary

An aggregate is a group of entities guaranteed to be consistent within a single atomic change. An aggregate has exactly one root; every modification to internal entities must go through the root.

Classic example:

~~~text
Order aggregate
      |
      +-- Order
      |
      +-- OrderLine 1
      |
      +-- OrderLine 2
      |
      +-- OrderLine 3
~~~

If an order has a `totalAmount` attribute, changing quantities or adding/removing order lines must update the total amount in the same domain operation. This is an invariant between Order and OrderLine, so they belong to the same aggregate.

Conversely, Customer and Product have their own lifecycles. A customer can have their address or status updated without needing to load and re-save all orders. A product can change its description or current price without altering already placed orders.

Therefore, Customer and Product should be separate aggregates, referenced by Order via ID.

### 2.1. The aggregate root is the gateway for changes

A service should not fetch an OrderLine from a separate repository and update it independently. Changes to order lines must go through Order:

~~~java
order.addLine(productId, quantity, priceSnapshot);
order.changeQuantity(lineNumber, newQuantity);
order.removeLine(lineNumber);
order.confirm();
~~~

The root's methods can enforce:

- Lines can only be added to a DRAFT order.
- Quantity must be greater than 0.
- An empty order cannot be confirmed.
- Snapshot price cannot be changed after the order is confirmed.
- A delivered order cannot be cancelled.

As a result, invariants are protected in one place.

### 2.2. One aggregate can map to multiple tables

An aggregate does not mean a single table. Order and OrderLine can reside in two separate tables while still belonging to the same aggregate.

Similarly, one table can hold multiple rows belonging to different aggregate roots.

Aggregate boundaries are determined by the domain and consistency requirements, not by the number of tables or foreign key relationships.

## 3. Identify invariants before splitting aggregates

List the rules that must always hold true after a command.

| Invariant | Related data | Suggested boundary |
| --- | --- | --- |
| The quantity of each order line must be positive | OrderLine | Order aggregate |
| An order cannot be confirmed without order lines | Order, OrderLine | Order aggregate |
| Total amount must equal the sum of lines and discounts | Order, OrderLine | Order aggregate |
| Price at order time does not change when Product price changes | OrderLine snapshot, Product | Order keeps snapshot; Product separate |
| Inventory stock cannot be negative | InventoryItem | Inventory aggregate |
| A payment cannot be recorded as successful twice | Payment | Payment aggregate or payment provider |
| Shipment can only be created when the order is eligible for fulfillment | Order, Shipment | Coordinated by application service/process manager |
| Shipping address of a placed order must remain unchanged | Order address snapshot | Order aggregate |

The key point is that not every invariant must live inside a single aggregate. Some rules can be enforced within a database transaction spanning multiple repositories; some distributed rules require a Saga, outbox, or compensating workflow.

### 3.1. Intra-aggregate invariants

For example: the total amount of an order must equal the sum of its order lines.

If a line is changed without updating the total amount, the data is immediately wrong after the command. Because Order owns OrderLine, the root can perform both changes together.

### 3.2. Cross-aggregate invariants

For example: an order cannot be confirmed if inventory is insufficient.

Order and InventoryItem have separate lifecycles. You should not merge all of inventory into Order just to perform this check.

An application service can coordinate two aggregates in the same transaction if they share a database resource and the business requirement demands simultaneous commit. If inventory lives in a different service/database, you need a distributed workflow, typically using a Saga or reservation workflow.

Aggregate boundaries do not forbid a service from coordinating multiple roots; they define which boundary is responsible for protecting local invariants.

## 4. Defining the Order aggregate

Order is typically the central aggregate root of this problem.

Order owns:

- Order status.
- List of order lines.
- Shipping address snapshot.
- Billing address snapshot if required by the business.
- Finalized total amount, tax, and discount.
- Creation/confirmation timestamps.
- Customer reference via ID.
- Version for optimistic locking.

OrderLine belongs to Order because it has no independent lifecycle outside the order. If an order is deleted per business policy, its order lines are handled along with the aggregate.

### 4.1. Is OrderLine a child entity or a value object?

An order line can be modeled as an internal entity if it needs a stable identity within the order scope, such as `lineNumber`. If it does not need an independent identity, it can also be treated as a value object.

In Spring Data JDBC, both cases can be mapped as nested entities belonging to the aggregate. The important thing is not to create a separate `OrderLineRepository` if lines do not have an independent lifecycle.

### 4.2. Product data snapshot

You should not store only the Product ID and read the current price from Product every time the order is displayed.

Suppose a customer orders a product priced at 100,000 VND. The next day, the catalog price changes to 120,000 VND. The old order must still show the 100,000 VND price from the time it was placed.

OrderLine should store a snapshot of:

- Product ID.
- SKU at order time.
- Product name at order time.
- Unit price.
- Currency unit.
- Quantity.
- Tax/discount if needed.

Product ID is a reference to the Product aggregate. The descriptive values and selling price are a snapshot owned by OrderLine.

### 4.3. Shipping address as a snapshot

A customer might change their default address after placing an order. The old order must still be delivered to the address confirmed when the order was placed.

Therefore, Order should hold its own Address value object:

~~~java
public record Address(
        String recipientName,
        String phone,
        String street,
        String city,
        String postalCode,
        String countryCode
) {
}
~~~

Address does not need its own repository or ID. It belongs to Order and is mapped into the same Order table using `@Embedded` or an appropriate value object structure.

## 5. Defining the other aggregates

### 5.1. Customer aggregate

Customer has its own lifecycle:

- Register an account.
- Change name, email, or phone number.
- Change active status.
- Manage default addresses.
- Update notification preferences.

Order should not contain the entire Customer object. It only needs the customer ID and any snapshots required for order history.

Example:

~~~java
AggregateReference<Customer, Long> customer;
~~~

When creating an Order:

~~~java
AggregateReference<Customer, Long> customerRef =
        AggregateReference.to(customerId);
~~~

`AggregateReference` is a wrapper around the ID of another aggregate. It clearly expresses that Order references Customer without owning Customer.

### 5.2. Product aggregate

Product manages:

- SKU.
- Name and description.
- Current price.
- Selling status.
- Catalog attributes.
- Category or classification information.

Product is not part of the Order aggregate. If the product price changes, old orders still keep the finalized price snapshot.

OrderLine can store `productId` as a `Long` or an `AggregateReference<Product, Long>`. `AggregateReference` helps clearly express the type of the referenced aggregate.

### 5.3. InventoryItem aggregate

InventoryItem has its own invariants:

- `availableQuantity` must not be negative.
- `reservedQuantity` must not exceed total stock.
- A reservation must be released or confirmed according to workflow.
- Stock updates require concurrency control.

It can be modeled by SKU and warehouse:

~~~java
@Table("inventory_items")
public record InventoryItem(
        @Id Long id,
        String sku,
        Long warehouseId,
        int availableQuantity,
        int reservedQuantity,
        @Version Long version
) {
}
~~~

If inventory changes frequently, InventoryItem can experience high contention. Separating it from Order ensures stock updates do not require loading and re-saving the entire order.

### 5.4. Payment aggregate

Payment has its own states and lifecycle:

- INITIATED.
- AUTHORIZED.
- CAPTURED.
- FAILED.
- REFUNDED.

An order can have multiple payment attempts or refunds. Payment needs to be tracked independently and have an idempotency key to prevent duplicate payment processing.

Do not place card details or sensitive payment data inside the Order aggregate. Order only keeps a payment reference and the necessary business status.

### 5.5. Shipment aggregate

Shipment manages:

- Carrier.
- Tracking number.
- Packages.
- Handover timestamp.
- Delivery status.
- Tracking history.

Shipment can be created, updated, or cancelled independently according to shipping workflows. Order keeps a shipment reference or an aggregated fulfillment status if needed.

## 6. Proposed aggregate diagram

An initial design:

~~~text
Customer aggregate
  Customer
    |
    +-- Addresses (if addresses belong to customer profile)
          |
          v
     CustomerRepository

Product aggregate
  Product
    |
    +-- Catalog attributes
          |
          v
     ProductRepository

Inventory aggregate
  InventoryItem
          |
          v
     InventoryRepository

Order aggregate
  Order
    |
    +-- OrderLine 1
    +-- OrderLine 2
    +-- OrderLine 3
    +-- ShippingAddress snapshot
          |
          v
      OrderRepository

Payment aggregate
  Payment
          |
          v
     PaymentRepository

Shipment aggregate
  Shipment
          |
          v
    ShipmentRepository
~~~

Aggregates reference each other by ID. The application service coordinates use cases that span multiple aggregates.

### 6.1. Aggregate boundary table

| Aggregate root | Owned components | Outgoing references |
| --- | --- | --- |
| Customer | Profile and customer-owned data | Does not need to contain Order |
| Product | Catalog and current price | Category ID if Category is a separate aggregate |
| InventoryItem | Quantities and reservations for a SKU/warehouse | Product ID |
| Order | OrderLine, address snapshot, total amount, order status | Customer ID, Product ID, Payment ID, Shipment ID |
| Payment | Payment attempts, status, provider reference | Order ID |
| Shipment | Packages, tracking, and delivery status | Order ID |

This table is a starting design. If your domain has different rules, adjust according to actual invariants and lifecycles.

## 7. Mapping the Order aggregate in Spring Data JDBC

### 7.1. OrderLine

~~~java
import java.math.BigDecimal;

public record OrderLine(
        Long productId,
        String skuSnapshot,
        String productNameSnapshot,
        BigDecimal unitPrice,
        String currency,
        int quantity
) {

    public OrderLine {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive"
            );
        }

        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "Unit price must not be negative"
            );
        }
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(
                BigDecimal.valueOf(quantity)
        );
    }
}
~~~

OrderLine does not have its own repository. It is persisted together with the Order root.

### 7.2. Order root

Simplified example:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.jdbc.core.mapping.AggregateReference;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;

    private OrderStatus status;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;

    @MappedCollection(
            idColumn = "order_id",
            keyColumn = "line_number"
    )
    private List<OrderLine> lines = new ArrayList<>();

    private Instant createdAt;

    @Version
    private Long version;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            AggregateReference<Customer, Long> customer,
            Address shippingAddress,
            Instant createdAt
    ) {
        this.customer = customer;
        this.shippingAddress = shippingAddress;
        this.createdAt = createdAt;
        this.status = OrderStatus.DRAFT;
    }

    public void addLine(OrderLine line) {
        ensureDraft();
        lines.add(line);
    }

    public void removeLine(int index) {
        ensureDraft();
        lines.remove(index);
    }

    public BigDecimal totalAmount() {
        return lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public void confirm() {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot confirm an empty order"
            );
        }

        status = OrderStatus.PENDING_PAYMENT;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Order can only be changed while in DRAFT"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

This example focuses on aggregate boundaries. A production implementation needs appropriate constructors/persistence mapping, state transition methods, currency/tax/discount handling, and input validation.

### 7.3. Status enum

~~~java
public enum OrderStatus {
    DRAFT,
    PENDING_PAYMENT,
    PAID,
    FULFILLING,
    SHIPPED,
    DELIVERED,
    CANCELLED,
    PAYMENT_FAILED
}
~~~

Services should not be allowed to set arbitrary statuses. Domain methods like `confirm()`, `markPaid()`, and `cancel()` should check the current state and transition conditions.

### 7.4. Repositories are only for aggregate roots

~~~java
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Do not create an `OrderLineRepository` if `OrderLine` is a child belonging to the `Order` aggregate.

Other repositories:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}

public interface ProductRepository
        extends CrudRepository<Product, Long> {
}

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {
}
~~~

Each repository manages one aggregate root. An application service can coordinate multiple repositories in a single use case.

## 8. Corresponding relational schema

An illustrative schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    current_price DECIMAL(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    warehouse_id BIGINT NOT NULL,
    available_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    UNIQUE (sku, warehouse_id),
    CHECK (available_quantity >= 0),
    CHECK (reserved_quantity >= 0)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    shipping_recipient_name VARCHAR(200),
    shipping_phone VARCHAR(40),
    shipping_street VARCHAR(250),
    shipping_city VARCHAR(120),
    shipping_postal_code VARCHAR(30),
    shipping_country_code CHAR(2),
    version BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    sku_snapshot VARCHAR(80) NOT NULL,
    product_name_snapshot VARCHAR(200) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_number),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
);
~~~

The schema above illustrates mapping and constraints. Identity, boolean, and timestamp DDL may need adjustment depending on the database vendor.

### 8.1. Why does order_lines have order_id?

OrderLine is an entity owned by Order. Spring Data JDBC uses the back-reference column to locate children belonging to the root.

With `@MappedCollection`:

- `idColumn` specifies the column holding the aggregate root's ID.
- `keyColumn` stores the List index or Map key.

OrderLine does not need its own repository and must not be updated independently from Order.

### 8.2. Why is customer_id a reference?

Customer is a different aggregate. Order holds an ID referencing Customer.

`AggregateReference<Customer, Long>` makes the reference type explicit in Java. It does not automatically load Customer when reading Order; if customer details are needed, the application service or an appropriate query must read Customer separately.

A database foreign key can be declared to protect referential integrity, but you should not cascade delete from Customer to Order if order history must be preserved.

## 9. How does Spring Data JDBC manage aggregates?

Spring Data JDBC persists the aggregate root and owned entities starting from the root.

When inserting a new aggregate:

1. INSERT the root.
2. Obtain the root ID.
3. INSERT child entities with foreign keys pointing to the root.

When updating an existing aggregate, the current implementation may delete the referenced entities, update the root, and re-insert the child entities according to the new aggregate state.

This has several implications:

- Changing one OrderLine may cause multiple child rows to be rewritten.
- An overly large aggregate makes save operations heavy.
- Do not put shipping history or millions of events into a collection on Order.
- Child entities should not be updated via an independent repository.
- The aggregate root must enforce collection invariants.

If an Order has tens of thousands of lines or unbounded change history, consider modeling the independently growing data as a separate aggregate.

## 10. Defining transaction boundaries for use cases

### 10.1. Creating an order

The create-order use case can:

1. Load Customer.
2. Check that Customer is active.
3. Load Product for each line.
4. Capture price, name, and SKU into the OrderLine snapshot.
5. Create the Order root.
6. Save the Order aggregate.

Service example:

~~~java
@Service
public class CreateOrderService {

    private final CustomerRepository customerRepository;
    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;
    private final Clock clock;

    public CreateOrderService(
            CustomerRepository customerRepository,
            ProductRepository productRepository,
            OrderRepository orderRepository,
            Clock clock
    ) {
        this.customerRepository = customerRepository;
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.clock = clock;
    }

    @Transactional
    public PurchaseOrder create(CreateOrderCommand command) {
        Customer customer = customerRepository
                .findById(command.customerId())
                .orElseThrow();

        if (!customer.isActive()) {
            throw new IllegalStateException(
                    "Customer is not active"
            );
        }

        PurchaseOrder order = new PurchaseOrder(
                AggregateReference.to(customer.getId()),
                command.shippingAddress(),
                Instant.now(clock)
        );

        for (CreateOrderLineCommand line : command.lines()) {
            Product product = productRepository
                    .findById(line.productId())
                    .orElseThrow();

            if (!product.isActive()) {
                throw new IllegalStateException(
                        "Product is not available"
                );
            }

            order.addLine(new OrderLine(
                    product.getId(),
                    product.getSku(),
                    product.getName(),
                    product.getCurrentPrice(),
                    product.getCurrency(),
                    line.quantity()
            ));
        }

        order.confirm();

        return orderRepository.save(order);
    }
}
~~~

This is an illustrative example. Command DTOs and getters/domain methods must be defined in a real application.

The transaction spans reading Customer/Product and writing Order if all repositories use the same DataSource and transaction manager. Only needing a snapshot of product data at order time does not mean Product becomes part of the Order aggregate.

### 10.2. Reserving inventory

Reserving inventory is a change on the Inventory aggregate. It can have its own service:

~~~java
@Transactional
public void reserve(
        String sku,
        Long warehouseId,
        int quantity
) {
    InventoryItem inventory = repository
            .findBySkuAndWarehouseId(sku, warehouseId)
            .orElseThrow();

    repository.save(inventory.reserve(quantity));
}
~~~

The Inventory root protects the non-negative invariant and uses `@Version` or appropriate locking to handle concurrency.

Do not pull all of inventory into the Order aggregate just to avoid a repository call.

### 10.3. When multiple aggregates need to commit together

If Order and Inventory reside in the same database and the business requires order creation and stock reservation to commit/rollback together, the application service can place `@Transactional` around both repositories.

However, doing so holds locks across multiple aggregates at once and can increase contention. Evaluate:

- Number of inventory rows that need to be locked/updated.
- Transaction duration.
- Likelihood of optimistic conflicts.
- Lock acquisition order.
- Connection pool capacity.
- How to roll back if one product is out of stock.

If the process is long-running or involves external systems, reservation state, outbox, and Saga are usually more appropriate.

### 10.4. Payment and shipping

Do not hold a JDBC transaction open while calling a payment gateway or carrier API.

A common flow:

1. Create Order in `PENDING_PAYMENT` status.
2. Write an outbox event in the same transaction.
3. Commit.
4. A worker calls the payment provider with an idempotency key.
5. Record the Payment result and update Order in a new transaction.
6. Upon payment success, start fulfillment.
7. Shipment is created and managed by the Shipment aggregate.

A database transaction cannot roll back side effects that have already occurred at a payment provider. Therefore, idempotency, outbox, and compensating workflows are required.

## 11. When should OrderLine be split into a separate aggregate?

Normally OrderLine belongs to Order. However, it may need to be split if order lines have:

- An independent lifecycle that extends after Order finishes.
- Separate workflows and multiple independent writers.
- Large data volume with high update frequency.
- Multiple other aggregates directly referencing individual lines.
- Separate invariants that do not require loading the entire Order.

If split, Order only holds references to the OrderLine aggregate or line IDs. Note, however, that order total and order status will no longer be automatically protected within one aggregate.

Do not split just because you want one repository per table. Repositories in Spring Data JDBC should represent aggregate roots, not every table.

## 12. Designing commands and domain behavior

The application service coordinates aggregates; domain methods protect invariants inside the root.

Command example:

~~~java
public record CreateOrderCommand(
        Long customerId,
        Address shippingAddress,
        List<CreateOrderLineCommand> lines
) {
}

public record CreateOrderLineCommand(
        Long productId,
        int quantity
) {
}
~~~

Some domain methods:

~~~java
public void addLine(OrderLine line) {
    ensureDraft();
    lines.add(line);
}

public void confirm() {
    ensureDraft();

    if (lines.isEmpty()) {
        throw new IllegalStateException(
                "An order must contain at least one line"
        );
    }

    status = OrderStatus.PENDING_PAYMENT;
}

public void markPaid() {
    if (status != OrderStatus.PENDING_PAYMENT) {
        throw new IllegalStateException(
                "Only pending orders can be paid"
        );
    }

    status = OrderStatus.PAID;
}

public void cancel() {
    if (status != OrderStatus.DRAFT
            && status != OrderStatus.PENDING_PAYMENT) {
        throw new IllegalStateException(
                "Order cannot be cancelled in current state"
        );
    }

    status = OrderStatus.CANCELLED;
}
~~~

Placing state transitions in the root prevents the repository from becoming a place for business logic.

## 13. Questions to answer before finalizing aggregate boundaries

| Question | Design signal |
| --- | --- |
| Must the data change together to preserve an invariant? | If yes, consider the same aggregate |
| Does the object have its own lifecycle? | If yes, consider a separate aggregate |
| Are there multiple places updating it independently? | Avoid oversized aggregates |
| Does it need to be referenced from multiple other aggregates? | Use ID/`AggregateReference` |
| Does the data need a historical snapshot? | Store a snapshot inside the business aggregate |
| Is there an unboundedly growing collection? | Split out the growing part or use an event store |
| Is atomic commit required across multiple aggregates? | Application transaction or Saga |
| Are external services called? | Outbox/idempotency; do not keep DB transactions open |
| Is there high contention? | Review aggregate size, version, and locking strategy |
| Will Spring Data JDBC have to rewrite the entire child collection? | Evaluate aggregate save cost |

## 14. Common design mistakes

**"Every table must have a repository."** No. Spring Data JDBC recommends repositories for aggregate roots. Child entities belonging to an aggregate are manipulated through the root.

**"Order must contain the full Customer and Product objects."** No. These are separate aggregates; Order should store reference IDs and necessary snapshots.

**"OrderLine needs its own repository to update quantity."** Not if OrderLine belongs to Order. Call a method on the Order root to protect invariants.

**"Foreign key means same aggregate."** No. A foreign key is a database relational constraint; an aggregate is a consistency boundary in the domain.

**"The larger an aggregate, the easier it is to keep consistent."** No. Overly large aggregates make transactions heavy, increase contention, and cause saves to rewrite many child rows.

**"Order price is always read from the current Product."** No. OrderLine needs a snapshot of price and descriptive details at order placement time.

**"Order and Inventory must be in the same aggregate because placing an order reserves stock."** Not necessarily. They have different invariants and lifecycles; the application service coordinates operations between roots.

**"You can call the payment API inside `@Transactional`."** You shouldn't. JDBC rollback does not undo transactions at the payment provider.

**"`AggregateReference` automatically loads the referenced aggregate."** No. It represents the ID of another aggregate; to read its data you must query separately.

**"Every cross-aggregate rule must be eventually consistent."** No. If they share the same database and require atomicity, the service can use one transaction across multiple repositories. Still, aggregate boundaries remain separate.

**"Store the entire OrderStatus history in an unbounded collection."** No. History can grow without bound; consider a separate audit/event table or event store.

## 15. Process for analyzing and identifying aggregates

1. **Gather use cases:** create order, confirm, pay, reserve stock, ship, cancel, and refund.
2. **Build a glossary:** agree on Order, OrderLine, Product, Inventory, Payment, Shipment.
3. **List invariants:** identify which rules must hold after each command.
4. **Group consistent data:** entities that must change atomically belong to the same aggregate.
5. **Identify the root:** choose the entity responsible for protecting invariants.
6. **Separate independent lifecycles:** Customer, Product, Inventory, Payment, and Shipment can be separate aggregates.
7. **Define references:** use IDs or `AggregateReference` for relationships between aggregates.
8. **Define snapshots:** store price, SKU, name, and address at the time the order is finalized.
9. **Design repositories:** one repository per aggregate root.
10. **Design transactions:** determine which operations need the same transaction and same DataSource.
11. **Assess contention:** check aggregate size, collection growth, and optimistic locking.
12. **Design integration flows:** use outbox/Saga for steps contacting external systems.
13. **Test invariants:** unit test domain logic, integration test mapping and transactions.
14. **Review against workload:** adjust boundaries as data volume or update frequency changes.

~~~mermaid
flowchart TD
    A["Analyze order management use cases"] --> B["List entities, value objects, and operations"]
    B --> C["Identify invariants that must hold together"]
    C --> D{"Must objects change atomically?"}
    D -->|Yes| E["Group into one aggregate"]
    D -->|No| F["Split into separate aggregates"]
    E --> G["Select aggregate root"]
    F --> H["Reference via ID/AggregateReference"]
    G --> I["Design repository for root"]
    H --> I
    I --> J["Define transactions and integration flows"]
    J --> K["Test invariants, mapping, and concurrency"]
~~~

## 16. Practice exercises

Design a sales application with Customer, Product, InventoryItem, Order, Payment, and Shipment.

### Exercise 1: Requirements analysis

1. Write the create-order use case.
2. Write the confirm-order use case.
3. Write the payment use case.
4. Write the cancel-order use case.
5. Write the shipping use case.
6. List the invariants for each use case.

### Exercise 2: Selecting aggregate roots

1. Determine whether Order owns OrderLine.
2. Determine whether Customer belongs inside the Order aggregate.
3. Determine whether Product belongs inside the Order aggregate.
4. Determine whether InventoryItem belongs inside the Order aggregate.
5. Explain the reasoning based on lifecycles and invariants.
6. Create a table mapping aggregate roots to repositories.

### Exercise 3: Designing the domain model

1. Create the Order root.
2. Create the OrderLine child entity/value object.
3. Create the Address snapshot.
4. Create separate Customer and Product aggregates.
5. Use `AggregateReference` or IDs for cross-aggregate references.
6. Write `addLine()`, `confirm()`, and `cancel()` methods to protect invariants.

### Exercise 4: Spring Data JDBC mapping

1. Use `@Table` for each aggregate root.
2. Use `@MappedCollection` for OrderLine.
3. Use `@Embedded` for Address.
4. Use `@Version` on Order and InventoryItem.
5. Create the schema and foreign keys.
6. Verify saving/loading the entire Order aggregate.

### Exercise 5: Designing transaction boundaries

1. Create Order along with OrderLines in a single transaction.
2. Coordinate inventory reservation via `InventoryRepository`.
3. Create the Payment flow with an outbox.
4. Define rollback behavior when an internal step fails.
5. Define Saga/compensation when the payment provider fails.
6. Verify no JDBC transaction is held open during HTTP calls.

### Exercise 6: Testing aggregates

1. Unit test that an empty Order cannot be confirmed.
2. Unit test invalid quantities.
3. Unit test that Order cannot be modified after confirmation.
4. Integration test that Order saves along with OrderLines.
5. Integration test that changing Product price does not alter the OrderLine snapshot.
6. Integration test optimistic locking for Order.
7. Integration test rollback when order creation fails.

## 17. Key takeaways

- An aggregate is a consistency boundary; the aggregate root is the sole gateway for modifications.
- One aggregate can map to multiple tables; a single table does not determine aggregate boundaries.
- Order and OrderLine typically belong to the same aggregate because total amount, status, and order lines must stay consistent.
- Customer, Product, InventoryItem, Payment, and Shipment typically have separate lifecycles and are separate aggregates.
- Cross-aggregate references should use IDs or `AggregateReference`, not embedded full objects.
- OrderLine needs snapshots of SKU, name, price, currency, and business data at the time of ordering.
- Shipping address should be stored as a snapshot in Order if history must be preserved.
- Spring Data JDBC recommends one repository per aggregate root.
- `@MappedCollection` maps a child collection using a foreign key and a key column.
- `@Embedded` maps a value object into the same table as the root.
- Spring Data JDBC may currently delete and recreate owned entities when saving an aggregate; avoid overly large aggregates or unboundedly growing collections.
- An application service can coordinate multiple aggregates in one transaction if they share a resource and the business requires atomicity.
- Payment and external shipping systems require idempotency, outbox, or Saga; JDBC transactions cannot roll back remote side effects.
- Determine boundaries from invariants, lifecycles, concurrency, and workload—not just from table diagrams.

**Good aggregate boundaries keep data that must be consistent together under one root, while allowing parts with independent lifecycles to be updated independently.** With Spring Data JDBC, this decision directly shapes repositories, mappings, transactions, and how the application coordinates order management workflows.

## References

- [Spring Data Relational 4.1.2 — Domain Driven Design and Relational Databases](https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html)
- [Spring Data Relational 4.1.2 — Mapping and Aggregate References](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data Relational 4.1.2 — AggregateReference API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/AggregateReference.html)
- [Spring Data Relational 4.1.2 — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational 4.1.2 — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html)
