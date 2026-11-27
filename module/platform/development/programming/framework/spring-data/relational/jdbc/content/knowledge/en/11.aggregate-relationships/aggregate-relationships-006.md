# Back-Reference Columns and Foreign Key Relationships on Child Tables

In a relational model, the relationship **one order has many order lines** is typically stored using a foreign key placed on the child table. Each row in the `order_lines` table has an `order_id` column pointing back to the primary key `purchase_orders.id`. This column is a **back-reference column** from the child table's perspective: given an order line, we know which order it belongs to.

With **Spring Data JDBC**, this ownership relationship is expressed on the aggregate root via `@MappedCollection(idColumn = "order_id")`. Spring Data JDBC uses that metadata to write and read the child rows belonging to the aggregate. Two parts must be distinguished: the annotation describes how objects map to columns; the DDL statements or migrations are what actually create the tables, columns, and `FOREIGN KEY` constraints in the database.

This lesson uses `PurchaseOrder` as the aggregate root and `OrderLine` as the child entity. We will look at table design, declaring `@MappedCollection`, saving and reading the aggregate, JOIN queries, and cases where an object should be split into an independent aggregate.

## 1. Why does the foreign key live on the child table?

Suppose an order can contain multiple order lines:

~~~text
PurchaseOrder 1 -------------- N OrderLine

purchase_orders                 order_lines
-------------------             ----------------------
id (PK)                         id (PK)
order_number                    order_id (FK)
status                          product_id
                                quantity
                                unit_price
~~~

An order can have many order lines, but each order line in this model belongs to exactly one order. Therefore, the `order_id` column is placed in the `order_lines` table:

~~~sql
SELECT id, order_id, product_id, quantity
FROM order_lines;
~~~

Sample data:

| purchase_orders.id | order_number | status |
|---:|---|---|
| 1001 | SO-2026-001 | DRAFT |
| 1002 | SO-2026-002 | SUBMITTED |

| order_lines.id | order_id | product_id | quantity |
|---:|---:|---:|---:|
| 1 | 1001 | 501 | 2 |
| 2 | 1001 | 502 | 1 |
| 3 | 1002 | 501 | 4 |

From the data above:

- Order `1001` has two order lines because two `order_lines` rows share `order_id = 1001`.
- Order `1002` has one order line.
- Order line `1` references order `1001`, without needing columns like `line_id_1`, `line_id_2`... in the parent table.

This is the standard representation of a **one-to-many** relationship in a relational database. The table on the "many" side holds the foreign key to the table on the "one" side.

## 2. Distinguishing a back-reference column from a bidirectional Java relationship

The term "back-reference" sometimes makes learners think the child class must have a field pointing back to the parent object:

~~~java
class OrderLine {
    private PurchaseOrder order;
}
~~~

With aggregate ownership relationships in Spring Data JDBC, **there is no need to create a `PurchaseOrder order` field inside `OrderLine`**. The relationship is described on the root's collection. Spring Data JDBC knows the `order_id` column lives on the child table via `@MappedCollection`.

Java model:

~~~text
PurchaseOrder (aggregate root)
    |
    | Set<OrderLine>
    |
    +------ OrderLine
    +------ OrderLine

Database:

purchase_orders.id
        ^
        |
order_lines.order_id
~~~

The diagram shows two different directions of representation:

- In Java, the root holds a collection of elements belonging to the aggregate.
- In the database, each child row holds a foreign key value referencing the parent row.

There is no need to build a bidirectional object graph just so the database has a foreign key. This unidirectional design fits how Spring Data JDBC organizes aggregates: the root is the access point and controls the lifecycle of child elements.

### 2.1. A foreign key is not a set of child ID columns on the parent table

An unsuitable design is creating fixed columns such as:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    line_id_1 BIGINT,
    line_id_2 BIGINT,
    line_id_3 BIGINT
);
~~~

This approach caps the number of lines, makes the schema hard to extend, and inverts the one-to-many relationship. The parent table does not need to know upfront how many child rows exist. Each child row carries its own `order_id`.

### 2.2. One foreign key can be viewed from two perspectives

From the parent table, we want to find the child lines:

~~~sql
SELECT *
FROM order_lines
WHERE order_id = 1001;
~~~

From the child table, we want to find the order that owns that line:

~~~sql
SELECT o.*
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.id = 1;
~~~

That is the same foreign key relationship, not two opposing foreign keys.

## 3. Creating a schema with the foreign key on the child table

The example uses Spring Boot, Spring Data JDBC, and H2. The following DDL creates a primary key on the parent table, a primary key on the child table, and the foreign key `order_id` pointing to the parent.

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_order_lines_purchase_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id),
    CONSTRAINT ck_order_lines_quantity
        CHECK (quantity > 0)
);

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);
~~~

Explanation:

- `purchase_orders.id` is the primary key of the aggregate root.
- `order_lines.id` is the primary key of each order line.
- `order_lines.order_id` is the foreign key referencing `purchase_orders.id`.
- `NOT NULL` ensures every order line must have an owning order.
- `FOREIGN KEY` prevents an order line from pointing to a nonexistent order.
- The index on `order_id` supports querying lines belonging to an order and joining on the foreign key.
- `CHECK (quantity > 0)` is an extra data constraint; business rules should still be enforced in domain objects.

`GENERATED BY DEFAULT AS IDENTITY` is syntax suitable for H2 and many modern databases, though ID generation syntax can vary across engines. When moving to PostgreSQL, MySQL, or SQL Server, adjust the DDL for the target database.

### 3.1. Why does `order_id` need `NOT NULL`?

In this model, `OrderLine` only exists as part of `PurchaseOrder`. An order line without a parent order is orphaned data, invalid in the domain. `NOT NULL` combined with a foreign key ensures:

1. The order line always has a reference value.
2. The reference value must match an existing primary key.

If the business allows an order line not yet attached to an order (e.g., an independent draft cart item), that may be a different model with a different lifecycle; do not relax `order_id` to nullable just to avoid aggregate design.

### 3.2. Is `ON DELETE CASCADE` required?

Declaring `ON DELETE CASCADE` is not mandatory. Spring Data JDBC understands the ownership relationship via aggregate mapping and coordinates saving/deleting the components belonging to the aggregate. The foreign key still protects integrity in the database.

If `ON DELETE CASCADE` is added, the database will automatically delete child rows when the parent row is deleted directly. This is a database-layer decision that can be helpful in some systems, but you must understand its impact on triggers, audits, and delete paths outside the application. Do not use cascade as a substitute for declaring the relationship properly in Spring Data JDBC.

## 4. Mapping `@MappedCollection` on the aggregate root

### 4.1. Child entity `OrderLine`

Create `src/main/java/com/example/orders/domain/OrderLine.java`:

~~~java
package com.example.orders.domain;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    @Column("product_id")
    private Long productId;

    private int quantity;

    @Column("unit_price")
    private BigDecimal unitPrice;

    protected OrderLine() {
        // For Spring Data JDBC mapping mechanism.
    }

    OrderLine(Long productId, int quantity, BigDecimal unitPrice) {
        if (productId == null) {
            throw new IllegalArgumentException("productId must not be null");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be greater than 0");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice is invalid");
        }
        this.productId = productId;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public Long getProductId() {
        return productId;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

`OrderLine` has `@Id` because each child row has its own identifier in the table. However, **having `@Id` does not automatically turn it into an aggregate root and does not mean an `OrderLineRepository` is needed**.

Notably, the class has no `orderId` property and no `PurchaseOrder order` field. The `order_id` column will be declared in the collection metadata on the root.

### 4.2. Aggregate root `PurchaseOrder`

Create `src/main/java/com/example/orders/domain/PurchaseOrder.java`:

~~~java
package com.example.orders.domain;

import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderLine> lines = new LinkedHashSet<>();

    protected PurchaseOrder() {
        // For Spring Data JDBC mapping mechanism.
    }

    private PurchaseOrder(String orderNumber) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("orderNumber is invalid");
        }
        this.orderNumber = orderNumber;
        this.status = "DRAFT";
    }

    public static PurchaseOrder draft(String orderNumber) {
        return new PurchaseOrder(orderNumber);
    }

    public void addLine(
            Long productId,
            int quantity,
            java.math.BigDecimal unitPrice) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                "Order lines can only be added when the order is in DRAFT status");
        }
        lines.add(new OrderLine(productId, quantity, unitPrice));
    }

    public void submit() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Order is not in DRAFT status");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Cannot submit an order without order lines");
        }
        status = "SUBMITTED";
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public Set<OrderLine> getLines() {
        return Collections.unmodifiableSet(lines);
    }
}
~~~

The most important part is:

~~~java
@MappedCollection(idColumn = "order_id")
private Set<OrderLine> lines;
~~~

- `@MappedCollection` states that `lines` is a collection of elements belonging to the aggregate root.
- `idColumn = "order_id"` specifies the foreign key column name on the table mapped for child elements.
- `order_id` resides in the `order_lines` table, not in `purchase_orders`.
- When saving the aggregate, Spring Data JDBC uses `PurchaseOrder`'s ID to attach the `OrderLine` rows to the root.

`@MappedCollection` **does not create tables or run DDL automatically**. It describes the mapping. The schema must still have the `order_id` column with a compatible type and a real foreign key as shown earlier.

### 4.3. Why not declare `orderId` inside `OrderLine`?

In this ownership mapping, the parent-child relationship is defined by the root's collection. If you both declare `@MappedCollection(idColumn = "order_id")` and add an independent `orderId` property writing to the same column, you can create duplicate or conflicting mappings.

If business logic needs to know the parent in domain logic, you can usually pass the root into a business method or work through the root. There is no need to duplicate the foreign key into a Java field just for the database to have a relationship.

## 5. The repository is created for the aggregate root

Create `src/main/java/com/example/orders/repository/PurchaseOrderRepository.java`:

~~~java
package com.example.orders.repository;

import java.util.Optional;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

There is no need for an `OrderLineRepository` simply because there is an `order_lines` table. The repository operates on the root, and Spring Data JDBC knows the child collection through `@MappedCollection`.

Conceptual flow:

~~~text
PurchaseOrderRepository.save(order)
             |
             v
        PurchaseOrder
             |
             +---- lines: Set<OrderLine>
                         |
                         v
                   order_lines
                   order_id = order.id
~~~

The exact number of SQL statements depends on the mapping and operation. The diagram illustrates the responsibility for saving the aggregate, not a claim that the framework always uses a single SQL statement for both root and children.

## 6. Saving and reading the aggregate to observe the back-reference column

### 6.1. Service creating an order

Create `src/main/java/com/example/orders/service/OrderService.java`:

~~~java
package com.example.orders.service;

import java.math.BigDecimal;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.repository.PurchaseOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder createExampleOrder() {
        PurchaseOrder order = PurchaseOrder.draft("SO-2026-001");

        order.addLine(501L, 2, new BigDecimal("120000.00"));
        order.addLine(502L, 1, new BigDecimal("90000.00"));

        return orders.save(order);
    }
}
~~~

The service creates the root, adds order lines via the root's method, and calls the repository once to save the aggregate. `@Transactional` defines the transaction boundary for the use case when the method is called through a Spring proxy.

### 6.2. Reading the root back

~~~java
PurchaseOrder saved = orderService.createExampleOrder();

PurchaseOrder loaded = repository.findById(saved.getId())
    .orElseThrow();

System.out.println(loaded.getOrderNumber());
System.out.println(loaded.getLines().size());
~~~

When loading an aggregate root, Spring Data JDBC loads the mapped components belonging to the aggregate. This collection is not a JPA-style lazy-loaded relationship; do not design code assuming that accessing `getLines()` later will automatically trigger a lazy query.

### 6.3. Inspecting `order_id` values directly

Use `JdbcTemplate` to inspect the child table:

~~~java
List<Map<String, Object>> rows = jdbcTemplate.queryForList(
    """
    SELECT id, order_id, product_id, quantity, unit_price
    FROM order_lines
    ORDER BY id
    """
);

rows.forEach(System.out::println);
~~~

Illustrative output:

~~~text
{ID=1, ORDER_ID=1, PRODUCT_ID=501, QUANTITY=2, UNIT_PRICE=120000.00}
{ID=2, ORDER_ID=1, PRODUCT_ID=502, QUANTITY=1, UNIT_PRICE=90000.00}
~~~

Both order lines have `ORDER_ID = 1`, because both belong to the order with ID `1`. This is direct proof that `idColumn = "order_id"` mapped the back-reference column in the child table.

## 7. How do `idColumn` and `keyColumn` differ?

`@MappedCollection` can declare both `idColumn` and `keyColumn`. These two attributes serve two different meanings:

| Attribute | Meaning | Example |
|---|---|---|
| `idColumn` | Column in the child table storing the aggregate root's ID | `order_id` |
| `keyColumn` | Column storing the collection key when the structure needs a key, such as `Map` or position for `List` | `line_position` |

With `Set<OrderLine>`, usually only `idColumn` is needed. If using `List<OrderLine>` and needing to persist order, `keyColumn` can be declared:

~~~java
@MappedCollection(idColumn = "order_id", keyColumn = "line_position")
private List<OrderLine> lines = new ArrayList<>();
~~~

Then the child table needs an additional `line_position` column of an appropriate integer type:

~~~sql
ALTER TABLE order_lines
ADD COLUMN line_position INTEGER;
~~~

`line_position` does not replace `order_id`: one column identifies **which root the line belongs to**, while the other identifies **the position/key in the collection**. If using `Map`, the key column stores the entry's key according to the mapping. Check the DDL and generated data whenever changing collection types.

## 8. JOIN queries still use the foreign key like standard SQL

`@MappedCollection` serves aggregate mapping when saving and reading the root. It does not prohibit the application from writing SQL JOINs. For example, a report of orders and line counts:

~~~sql
SELECT
    o.id,
    o.order_number,
    o.status,
    COUNT(l.id) AS line_count
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id, o.order_number, o.status
ORDER BY o.id;
~~~

JOIN condition:

~~~sql
ON l.order_id = o.id
~~~

This is the exact pair of columns declared by the foreign key. You can use `JdbcTemplate`/`NamedParameterJdbcTemplate` to map results into a DTO/read model. There is no need to create a CRUD repository for `OrderLine` just to read reports.

### Querying lines belonging to an order

~~~sql
SELECT l.id, l.product_id, l.quantity, l.unit_price
FROM order_lines l
WHERE l.order_id = :orderId
ORDER BY l.id;
~~~

In Spring JDBC, `:orderId` can be bound using `NamedParameterJdbcTemplate`. With plain JDBC SQL, use `?` and positional parameter binding. Never concatenate input values directly into SQL strings.

## 9. When should `@MappedCollection` NOT be used?

Not every foreign key represents a child entity belonging to an aggregate root.

### 9.1. Referencing another aggregate

Suppose an order references a customer:

~~~text
PurchaseOrder  ------ customer_id ------> Customer
    root                                separate root
~~~

`Customer` has its own lifecycle and is referenced by many orders. Do not put the entire `Customer` inside an owned collection of `PurchaseOrder`. Usually just store the ID:

~~~java
private Long customerId;
~~~

Or use Spring Data Relational's `AggregateReference<Customer, Long>` type if you want to express aggregate-reference semantics explicitly. Each aggregate root has its own repository when access is needed.

### 9.2. Many-to-many relationships

If a product appears in many orders and an order has many products, the domain relationship is usually not "one OrderLine shared by many Orders". Each order line is part of one order; it holds `order_id` and `product_id`, while `product_id` references a separate `Product` aggregate.

~~~text
PurchaseOrder 1 --- N OrderLine N --- 1 Product
~~~

These are two many-to-one relationships from `OrderLine` to the `PurchaseOrder` root (ownership) and the `Product` root (reference). There is no need for an owned `Product` entity inside each order.

### 9.3. Objects with an independent lifecycle

If an entity can be created, updated, deleted, and managed independently of the current root, consider making it a separate aggregate root. In that case, the database relationship may still be a foreign key, while in the domain model it is referenced by ID rather than an owned collection.

For example, `Shipment` with shipping status, tracking events, and an independent update workflow can be a separate aggregate, even though it references `purchase_order_id`.

## 10. Common errors

| Symptom | Cause | How to resolve |
|---|---|---|
| Saving root fails because `order_id` column does not exist | DDL or migration for child table has not been created | Add `order_id` column to `order_lines` |
| Foreign key error when inserting order lines | Root ID does not exist yet or reference type/column mismatches | Let Spring Data JDBC save the aggregate per mapping; check ID type and DDL |
| `order_id` is always null | `idColumn` does not match column name or collection mapping is wrong | Set `@MappedCollection(idColumn = "order_id")` and verify schema |
| Order lines fail to load when reading root | Child table, table name, or reference column mismatches mapping | Check `@Table`, `idColumn`, FK data, and SQL logs |
| Created an extra `OrderLineRepository` just to save child lines | Confusing an entity having `@Id` with an aggregate root | Perform order line changes through `PurchaseOrder` |
| Added `orderId` field to child and got duplicate mapping | Declaring the column via both collection and separate property mapping | Choose one consistent mapping model; for owned children use `idColumn` |
| Mistakenly used `@OneToMany`/`@JoinColumn` | Applying JPA annotations to Spring Data JDBC | Use Spring Data Relational's `@MappedCollection` |
| Slow root queries when aggregate has many children | Aggregate designed too large or missing FK index | Revisit aggregate boundaries, index `order_id`, check query plans |

### Distinguishing the right annotation package

In Spring Data JDBC, commonly used annotations are:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;
~~~

Do not confuse them with:

~~~java
// These annotations belong to JPA:
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.JoinColumn;
~~~

Spring Data JDBC has its own aggregate model. Merely swapping package imports while keeping JPA's bidirectional object-graph/lazy-loading mindset will lead to unexpected mapping and behavior.

## 11. Workflow for designing a parent-child relationship

When encountering a child table in a Spring Data JDBC domain, follow this sequence:

1. **Determine ownership:** does the child table truly belong to the aggregate root's lifecycle?
2. **Choose the root:** which operations need to protect the invariants of this data group?
3. **Place the FK on the many side:** the child table holds a column referencing the parent table's primary key.
4. **Declare schema:** create the column with matching type, `NOT NULL` if mandatory, foreign key, and index where appropriate.
5. **Map the collection:** declare `@MappedCollection(idColumn = "...")` on the root.
6. **Create a repository for the root:** do not derive repositories from the number of tables.
7. **Test save/read:** inspect FK data and try reloading the aggregate.
8. **Separate read queries when needed:** use JOIN/DAO for reporting without altering ownership.

## 12. Practice exercises

### Exercise 1 — Building the order and order-line relationship

- Create the two tables `purchase_orders` and `order_lines` following the DDL in this lesson.
- Declare `PurchaseOrder` with `Set<OrderLine>` and `@MappedCollection(idColumn = "order_id")`.
- Create `PurchaseOrderRepository`.
- Save an order with two order lines.
- Query `order_lines` directly and verify both rows share the same `order_id`.

### Exercise 2 — Changing the reference column name

Rename the `order_id` column to `purchase_order_id` in the database. Update `@MappedCollection(idColumn = "purchase_order_id")` and the corresponding migration. Explain why changing only the annotation without updating the DDL causes an error.

### Exercise 3 — Collection ordering

Replace `Set<OrderLine>` with `List<OrderLine>`, adding `keyColumn = "line_position"` and the corresponding column. Save three lines in order, reload the aggregate, and observe the stored positions. Explain why `keyColumn` is not the foreign key to the root.

### Exercise 4 — Splitting an aggregate

Suppose `Shipment` is updated independently after an order has been submitted. Design a `shipments` table with `purchase_order_id` referencing `purchase_orders.id`, but create a separate `ShipmentRepository`. Explain the difference between a database foreign key and aggregate ownership.

## 13. Conclusion

In a one-to-many relationship, **the child table is where the foreign key pointing back to the parent table lives**. With Spring Data JDBC, the aggregate root declares the child collection via `@MappedCollection(idColumn = "order_id")`; `idColumn` names the reference column in the child table. The child entity does not need a Java property pointing back to the root just to maintain the foreign key.

The annotation describes the object-relational mapping, while DDL/migrations must create the `order_id` column, foreign key, data types, and appropriate indexes. When the root is saved or loaded, Spring Data JDBC handles the components belonging to the aggregate per the mapping. When reports or JOINs are needed, you can still query directly via SQL without creating a CRUD repository for every table.

Remember to separate three decisions: **where the foreign key lives in the database, which object owns which object in the aggregate, and which repository serves as the business entry point**. They are related, but they are not the same concept.
