# Designing Order and OrderItem as a Single Persistence Unit

In **Spring Data Relational JDBC (Spring Data JDBC)**, an order typically consists of header information such as the customer and status along with multiple order lines. These two kinds of objects may be stored in **two tables**, yet from a business perspective they should be treated as **one aggregate**: `Order` is the **aggregate root**, while `OrderItem` is a component owned by the order.

This lesson builds an `Order`–`OrderItem` model from business requirements, maps it using Spring Data JDBC, persists it to a relational database, and explains what actually happens when calling `repository.save(order)`. The focus is on designing **a consistent unit of persistence**, not merely joining two tables with a foreign key.

## 1. Why Design Them as the Same Aggregate?

Suppose a sales system allows:

- Creating an order in `DRAFT` status.
- Adding or removing products before confirmation.
- Each line holding a product code (SKU), quantity, and unit price finalized at the time it is added to the order.
- Disallowing transitioning an order to `CONFIRMED` if it has no lines.
- Disallowing modifying the line list after confirmation.

These rules simultaneously involve the state of **Order** and the list of **OrderItem** entries. If different places updated individual lines and updated the order arbitrarily, a `CONFIRMED` order with no items could arise, or prices and quantities could change after order finalization.

Therefore, we choose:

**Order is the aggregate root.** Every business operation that changes order lines goes through methods on `Order`. `OrderItem` lives within the order's boundary and is not created or saved independently by normal use cases.

### Model Map

~~~mermaid
flowchart TB
    Service["OrderApplicationService<br/>create / confirm order use cases"] --> Repository["OrderRepository<br/>CrudRepository<Order, Long>"]
    Repository --> Root

    subgraph Aggregate["AGGREGATE: Order"]
        Root["Order<br/>Aggregate Root<br/>id, version, customerId, status"]
        Root -->|"owns 0..N"| Item["OrderItem<br/>id, sku, quantity, unitPriceCents"]
    end

    Root -. "customerId" .-> Customer["Customer<br/>Other aggregate"]
    Item -. "sku" .-> Product["Product<br/>Other aggregate"]
    Root --> Orders[("shop_orders")]
    Item --> Items[("order_items")]
    Items -->|"order_id (FK)"| Orders
~~~

The diagram highlights two separate aspects:

1. **Domain model:** `Order` owns `OrderItem`s; `Customer` and `Product` have independent lifecycles, so the order stores only the identifier values needed.
2. **Storage model:** one `Order` and its `OrderItem`s are written as rows across two tables. The `order_id` foreign key links child records to the root record.

**One aggregate does not mean one table.** Boundaries are decided by business rules and ownership, whereas database tables are how aggregate state is represented.

## 2. Dividing Responsibilities Between Order and OrderItem

| Component | Role in domain | Responsibilities | Write access path |
|---|---|---|---|
| `Order` | Entity and aggregate root | Holds order identity, status, item list; protects invariants | Through `OrderRepository` |
| `OrderItem` | Child entity inside aggregate | Holds data for one line and calculates subtotal | Through `Order` methods |
| `Customer` | Independent aggregate | Manages customer profile/lifecycle | Customer's repository |
| `Product` | Independent aggregate | Manages product, sale status, list price | Product's repository |

In this lesson, each `OrderItem` has an `id` to identify the child row when mapped to the table. That does **not** mean an order item needs its own repository. It remains a child entity, accessed and modified within the scope of the `Order` root.

At order creation time, `OrderItem` records `sku` and `unitPriceCents`. Afterward, `Product`'s list price may change without automatically altering the price locked into the order. This is an example of a **transaction data snapshot**: keeping only the required product information inside Order without embedding the entire Product aggregate.

### Invariants to Protect

For this illustrative design, we specify:

1. `customerId` must be valid per input rules (for example, greater than 0).
2. When adding a line, the SKU must not be blank, quantity must be positive, and unit price must be non-negative.
3. Each SKU appears at most once in the same order. To increase the quantity of an existing SKU, an explicit business operation would be needed; this illustrative version rejects duplicates.
4. Only `DRAFT` orders may add or remove lines.
5. `confirm()` succeeds only when the order has at least one item and is in `DRAFT`.
6. Total amount is computed from the items' quantities and unit prices, rather than allowing callers to pass an inconsistent total.

Distinguish **in-memory invariants** from **database constraints**. For instance, `CHECK (quantity > 0)` protects quantity data in the table, while the rule "only modify items while Order is DRAFT" must be enforced by domain operations and proper write paths.

## 3. Java Model of the Aggregate

The following example uses Java and Spring Data JDBC. Classes sit in the same `com.example.sales.order` package to simplify the illustration; in a real project you can split domain, application, and persistence packages further.

### OrderStatus.java

~~~java
package com.example.sales.order;

public enum OrderStatus {
    DRAFT,
    CONFIRMED
}
~~~

### OrderItem.java

~~~java
package com.example.sales.order;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_items")
public class OrderItem {

    @Id
    private Long id;

    private String sku;
    private int quantity;
    private long unitPriceCents;

    protected OrderItem() {
        // Spring Data JDBC reconstructs the object when reading from the database.
    }

    OrderItem(String sku, int quantity, long unitPriceCents) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPriceCents < 0) {
            throw new IllegalArgumentException("Unit price must be non-negative");
        }
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public long getUnitPriceCents() {
        return unitPriceCents;
    }

    public long subtotalCents() {
        return Math.multiplyExact(unitPriceCents, quantity);
    }
}
~~~

Notable points:

- `@Id` is the persistence ID of the order line. The ID is typically database-generated when inserting the record.
- `OrderItem` properties have no public setters. External use cases cannot modify quantity, price, or SKU directly on objects returned by the root.
- `subtotalCents()` calculates the value from current data; `Math.multiplyExact` detects integer overflow instead of silently producing an incorrect sum.
- The line-creation constructor is package-private (not public), expressing that creating order lines is the root's responsibility.

### Order.java

~~~java
package com.example.sales.order;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("shop_orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private Long customerId;
    private OrderStatus status;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_position"
    )
    private List<OrderItem> items = new ArrayList<>();

    protected Order() {
        // Constructor used by the Spring Data JDBC mapper.
    }

    public static Order draftFor(long customerId) {
        if (customerId <= 0) {
            throw new IllegalArgumentException("Invalid customer ID");
        }
        Order order = new Order();
        order.customerId = customerId;
        order.status = OrderStatus.DRAFT;
        return order;
    }

    public void addItem(String sku, int quantity, long unitPriceCents) {
        requireDraft();
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (items.stream().anyMatch(item -> item.getSku().equals(sku))) {
            throw new IllegalArgumentException("Duplicate SKU in order");
        }
        items.add(new OrderItem(sku, quantity, unitPriceCents));
    }

    public void removeItem(String sku) {
        requireDraft();
        boolean removed = items.removeIf(item -> item.getSku().equals(sku));
        if (!removed) {
            throw new IllegalArgumentException("SKU is not in the order");
        }
    }

    public void confirm() {
        requireDraft();
        if (items.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        status = OrderStatus.CONFIRMED;
    }

    public long totalCents() {
        long total = 0;
        for (OrderItem item : items) {
            total = Math.addExact(total, item.subtotalCents());
        }
        return total;
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

    public List<OrderItem> getItems() {
        return List.copyOf(items);
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is not editable");
        }
    }
}
~~~

Here, **Order guards modification rights over the list**. `getItems()` returns an unmodifiable list copy; combined with `OrderItem` exposing no setters, callers can only change order lines through the root's domain methods.

`@Version` manages the aggregate root version to detect concurrent updates to the same order. The version is handled by Spring Data JDBC upon saving; the application does not increment this number manually.

### Why Not Put Add/Remove Operations in an OrderItemRepository?

If `orderItemRepository.deleteById(id)` were allowed, another piece of code could delete the last item from an already `CONFIRMED` order. That bypasses `Order.requireDraft()` and the rule "a confirmed order must have at least one item." Under the current model, **only create `OrderRepository`**; when adding/removing items is needed, load Order, invoke the root's method, and save Order.

## 4. Mapping One Aggregate to Two Tables

Spring Data JDBC maps `Order` to the `shop_orders` table and the `OrderItem` list to the `order_items` table. Using PostgreSQL in this example:

~~~sql
CREATE TABLE shop_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED'))
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES shop_orders(id),
    line_position INTEGER NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL
        CHECK (unit_price_cents >= 0),
    CONSTRAINT uq_order_line_position
        UNIQUE (order_id, line_position),
    CONSTRAINT uq_order_sku
        UNIQUE (order_id, sku)
);

CREATE INDEX idx_order_items_order_id
    ON order_items(order_id);
~~~

**Note:** this is sample PostgreSQL DDL for practice. When using MySQL, replace the auto-generated ID syntax with `AUTO_INCREMENT` and choose an engine supporting foreign keys, such as InnoDB. Do not run `CREATE TABLE` against existing tables without a migration plan.

| In Java | In database | Meaning |
|---|---|---|
| `Order.id` | `shop_orders.id` | Primary key of the aggregate root |
| `Order.version` | `shop_orders.version` | Version for optimistic locking |
| `Order.customerId` | `shop_orders.customer_id` | ID reference to the customer |
| `Order.status` | `shop_orders.status` | Status of the order |
| `Order.items` | Rows in `order_items` | Components owned by the root |
| `@MappedCollection(idColumn = "order_id")` | `order_items.order_id` | Column linking each item to Order |
| `@MappedCollection(keyColumn = "line_position")` | `order_items.line_position` | Element position in the `List` |
| `OrderItem.id` | `order_items.id` | Primary key of the order line row |

`idColumn` in `@MappedCollection` specifies **the column in the child table** holding the root's ID; it does not have to be declared as a back-reference property on `OrderItem`. Spring Data JDBC manages that FK column when writing the aggregate.

With `List`, `keyColumn` stores element ordering, starting at position **0** in this example. If the business does not care about ordering, consider another collection type and adjust the mapping accordingly; do not confuse list position with the durable identity of an order line.

### The Database Does Not Decide Ownership

Two tables with a foreign key can still belong to **two independent aggregates** if each side has its own lifecycle. Conversely, `Order` and `OrderItem` here belong to one aggregate because:

- Items only make sense when attached to an Order.
- Adding, removing, or adjusting items is subject to Order status conditions.
- When deleting an entire Order in the business domain, items belonging to the Order must also be handled accordingly.
- Mutation operations must maintain invariants spanning both the root and order lines.

A foreign key is a tool for relational integrity, whereas **aggregate decisions** come from the business domain.

## 5. Creating a Repository for the Aggregate Root

Write `OrderRepository.java`:

~~~java
package com.example.sales.order;

import org.springframework.data.repository.CrudRepository;

public interface OrderRepository extends CrudRepository<Order, Long> {
}
~~~

The repository takes root type `Order` and ID type `Long`. With Spring Data JDBC, basic operations include:

- `save(order)`: writes the aggregate state starting from the root and its mapped child parts.
- `findById(id)`: loads the root together with its mapped aggregate parts.
- `delete(order)` or `deleteById(id)`: deletes the aggregate through the repository.

No `OrderItemRepository` needs to be defined to interact with `order_items`. When queries are needed for reporting or searching metrics across multiple tables, dedicated read models/queries can be built; that does not change the rule that **business mutations go through Order**.

## 6. Executing Use Cases Through an Application Service

The application service orchestrates loading, modifying, and saving the aggregate. Every operation must use `Order`'s domain methods rather than constructing SQL to update individual rows externally.

~~~java
package com.example.sales.order;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createDraft(
            long customerId,
            String firstSku,
            int quantity,
            long unitPriceCents) {
        Order order = Order.draftFor(customerId);
        order.addItem(firstSku, quantity, unitPriceCents);

        Order saved = orders.save(order);
        return saved.getId();
    }

    @Transactional
    public void addItem(
            Long orderId,
            String sku,
            int quantity,
            long unitPriceCents) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        order.addItem(sku, quantity, unitPriceCents);
        orders.save(order);
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        order.confirm();
        orders.save(order);
    }
}
~~~

For the confirmation use case:

1. `OrderRepository.findById(orderId)` loads the root and item list.
2. `order.confirm()` verifies the invariant "order is DRAFT and has at least one line."
3. `OrderRepository.save(order)` writes the aggregate back to the database.

`@Transactional` sets the transaction boundary at the application service, useful when a use case makes multiple repository calls or related SQL operations. Loading and saving inside one transaction **does not by itself replace** concurrent update control; for example, `@Version` is also used on the root.

### Illustrating an Order's Lifecycle

~~~java
Long orderId = service.createDraft(
    101L,
    "JAVA-BOOK",
    2,
    150_000L
);

service.addItem(orderId, "NOTEBOOK", 1, 40_000L);
service.confirm(orderId);

Order saved = orders.findById(orderId).orElseThrow();

System.out.println(saved.getStatus()); // CONFIRMED
System.out.println(saved.getItems().size()); // 2
System.out.println(saved.totalCents()); // 340000
~~~

The final snippet assumes `service` and `orders` have been supplied by Spring via dependency injection. It only illustrates usage flow, not a complete standalone application with all variables and beans.

The value `340000` is computed as `2 × 150000 + 1 × 40000`. After confirmation, `service.addItem(...)` on the same order will be rejected by `Order.requireDraft()`.

## 7. What Does "One Unit of Persistence" Mean During `save`?

Imagine a new Order with two items:

~~~text
Order (no id yet)
  status = DRAFT
  customerId = 101
  items
    - JAVA-BOOK, quantity=2, unitPriceCents=150000
    - NOTEBOOK, quantity=1, unitPriceCents=40000
~~~

When calling `orders.save(order)`, conceptually Spring Data JDBC performs the steps needed to persist:

~~~mermaid
sequenceDiagram
    participant App as Application Service
    participant Repo as OrderRepository
    participant DB as Relational Database
    App->>Repo: save(order)
    Repo->>DB: INSERT shop_orders (...)
    DB-->>Repo: generated order id
    Repo->>DB: INSERT order_items (..., order_id, line_position=0)
    Repo->>DB: INSERT order_items (..., order_id, line_position=1)
    Repo-->>App: saved Order
~~~

This is a **conceptual** diagram, not an exact guarantee of SQL statement count or internal ordering across all versions, configurations, and aggregate shapes. The takeaway is that the repository knows the items **belong to** the root because they are declared in `Order`'s mapping.

If the transaction fails before committing, writes in the same transaction are rolled back by the database mechanism. The goal is to keep the tables of **one aggregate** in a consistent state after each successful save.

### When an Order Already Exists and Items Change

Spring Data JDBC **does not use a JPA-style persistence context and dirty checking**. For an existing aggregate, the default save strategy may **delete referenced child records and re-insert child records matching the current state**. Therefore:

- `save(order)` does not mean "UPDATE only the single item row that changed."
- A small change to a child collection can generate multiple write operations.
- Database-assigned IDs for `OrderItem` can change if child rows are deleted and re-inserted.
- You should not use `order_items.id` as a durable identity referenced by other aggregates when designing around this persistence model.

If each item has a long lifecycle, is referenced by multiple parties, and needs updates independent of Order, that is a signal to **re-examine aggregate boundaries** instead of keeping a large owned relationship by default.

Deleting/rewriting items also affects triggers, audit logs, and performance. In systems with large item counts or very frequent saves, measure actual SQL volume and consider an appropriate persistence model. In this lesson, an order with a moderate number of lines is an appropriate model for illustration.

## 8. Ensuring Consistency and Handling Concurrent Updates

### Invariants on the Root

Calling `order.confirm()` on an order with no items throws `IllegalStateException`. Because `save` has not been called, the database is never written with invalid state. This rule sits on the root because only the root simultaneously knows **the order status** and **the list of order lines**.

### Database Constraints

Conditions in DDL add a second layer of protection:

- `NOT NULL` prevents required fields from being omitted.
- `CHECK (quantity > 0)` and `CHECK (unit_price_cents >= 0)` prevent invalid numbers.
- `UNIQUE (order_id, sku)` prevents duplicate SKUs in the same order.
- `FOREIGN KEY (order_id)` prevents items from referencing a non-existent Order.

Some rules such as "a CONFIRMED order cannot modify items" or "a CONFIRMED order must have at least one item" require domain logic and write policies, because single-column constraints cannot fully express those semantics.

### Concurrent Updates and `@Version`

Suppose two requests concurrently load `Order(id=15, version=4)`:

~~~text
Request A                       Request B
load Order version=4            load Order version=4
addItem("PEN", ...)             confirm()
save Order                      save Order
version changes to 5           stale version detected -> conflict
~~~

With `@Version` on the root, Spring Data JDBC uses optimistic locking when updating. The later save using the stale version receives an exception in the `OptimisticLockingFailureException` family. The application should return a conflict notice, reload fresh data, and ask to retry the action per business rules; do not silently overwrite the outcome of the request that already succeeded.

**Do not rely solely on `@Transactional` to prevent lost updates.** Transactions wrap operations, whereas version checks detect when two parties acted on two stale reads of the same aggregate.

### Boundaries With Product, Customer, and Inventory

`Order` can reference `Customer` via `customerId` and `Product` via `sku`/`productId`, but **do not embed these two independent aggregates as object lists inside Order**. When confirming an order needs to decrement inventory, an application service must coordinate with the inventory aggregate and appropriate transaction/event policies.

A single use case using both Order and Inventory **does not automatically turn them into one aggregate**. When drawing boundaries, ask: which invariants strictly must be maintained together, and which objects truly have independent lifecycles?

## 9. Design Choices Worth Weighing

### Is OrderItem an Entity or a Value Object?

In this lesson, `OrderItem` has an ID and is modeled as a **child entity**. This is useful if the business distinguishes individual lines and wants states or operations targeting a specific line.

In a simpler model, an order line is merely a `(sku, quantity, price)` tuple needing no individual identity. In that case, lines can be designed as immutable **value objects**. Even so, how they map into a collection and table keys must fit Spring Data JDBC. **Do not equate a domain value object with being forced to store it in the same row.**

### Should Order Contain Full Customer/Product Objects?

Usually **no** if Customer/Product are independent aggregates. Keeping ID references and snapshots of required transaction data gives Order a clean write scope, reduces lifecycle coupling, and avoids traversing an object graph across boundaries.

### Should Every Entity Have Its Own Repository?

No. The repository in the current model belongs to **Order**. If the UI needs to search items by SKU, you can write read queries over the tables or projections for reporting. Read queries do not have to pass through aggregate write methods, whereas **business mutation operations** must preserve the root's invariants.

### Should `totalCents` Be Stored in the Order Table?

This example **computes the total from items** to avoid out-of-sync updates. If query performance or reporting requires storing a precomputed total, ensure a mechanism always computes/updates the total within the same business flow. Never expose a public setter allowing clients to write an arbitrary total.

### When Is This Aggregate Too Large?

If an Order contains thousands of items and is updated frequently, the cost of saving the entire aggregate can grow. Then evaluate realistic item counts, Spring Data JDBC's write behavior, invariants to protect, and ways to split responsibilities. Do not split an aggregate merely because there are two tables; likewise, do not keep every related object inside Order just to load them with one repository.

## 10. Common Implementation Mistakes

| Practice | Consequence | Design approach in this lesson |
|---|---|---|
| Creating `OrderItemRepository` and editing items directly | Bypasses Order status and invariants | Change items via `Order.addItem/removeItem` |
| Treating one table as one aggregate | Splits tightly coupled business operations | One `Order` owns many items across two tables |
| Using `@OneToMany`/`@ManyToOne` like JPA | Misunderstands Spring Data JDBC's mapping model | Use `@MappedCollection` and boundary-proper ID references |
| Putting `Customer`/`Product` directly into the owned object graph | Unintentionally expands aggregate scope | Hold customerId/SKU or productId |
| Letting clients mutate the returned `List<OrderItem>` | Can alter state outside root rules | Return an unmodifiable copy; only root mutates |
| Assuming `save(order)` minimally updates each item | Surprised by SQL volume and child IDs | Understand Spring Data JDBC aggregate persistence |
| No concurrency control | Two requests can overwrite older data | `@Version` on Order, handle optimistic lock errors |
| Putting constraints only in code or only in DB | Missing protection in domain or data layer | Combine root invariants with FK/CHECK/UNIQUE |
| Always embedding current Product price in Order | Past order totals change when catalog updates | Store snapshot unit price inside `OrderItem` |

## 11. Practice Exercises and Self-Check Questions

From the template above, work through the following steps in order:

1. Create a `DRAFT` order for customer `101` and add `SKU-A` quantity `2`, price `120000`; add `SKU-B` quantity `1`, price `50000`. Verify the total is `290000`.
2. Save the order through `OrderRepository`, then use `findById` to verify the root and both items are read back from the child table.
3. Query `shop_orders` and `order_items` in SQL; confirm both lines share the same `order_id`, and `line_position` is `0` then `1`.
4. Try adding `SKU-A` a second time. Identify which invariant blocks the operation before any SQL is generated.
5. Confirm the order, then try removing `SKU-B`. Predict which method will throw the exception.
6. Open two sessions editing the same Order; in the first, add an item and save; in the second, save from the stale version. Observe how `@Version` detects the conflict.
7. Discuss: if an `OrderItem` needs independent shipping, refunds, and standalone lookup over many years, is the current aggregate boundary still appropriate?

A SQL query to inspect data across both tables:

~~~sql
SELECT
    o.id AS order_id,
    o.status,
    o.version,
    i.line_position,
    i.sku,
    i.quantity,
    i.unit_price_cents
FROM shop_orders o
JOIN order_items i ON i.order_id = o.id
WHERE o.id = :order_id
ORDER BY i.line_position;
~~~

In the query above, `:order_id` is an **illustrative named parameter**; when running directly in a SQL client, replace it with a real ID or bind the parameter using the corresponding tool. Compare the returned rows with `saved.getItems()` to see the difference between **an aggregate's object graph** and **relational table rows**.

## 12. Remembering the Model

The core relationships in this lesson can be read as follows:

~~~text
Use case
   -> OrderRepository.findById(...)
   -> Order.addItem(...) / Order.removeItem(...) / Order.confirm()
   -> OrderRepository.save(order)
       -> shop_orders       (root)
       -> order_items       (components owned by the root)
~~~

Designing `Order` and `OrderItem` as **a single persistence unit** means choosing **Order as the sole entry point for business changes to the order**, preserving invariants across both the root and the item list, while letting Spring Data JDBC manage mapping them across multiple tables. One repository, one aggregate, and one consistency boundary can span multiple entities, multiple data rows, and multiple SQL statements.
