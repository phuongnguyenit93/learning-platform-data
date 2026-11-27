# Flow of Inserting the Aggregate Root First and Then Writing Child Entities

In Spring Data Relational JDBC, an **aggregate** is persisted through its aggregate root. When an application creates a new order containing general header information and multiple order lines, Spring Data JDBC writes the root row first, retrieves the root's identifier, and then uses that identifier to write the child entities into their corresponding table.

This ordering ensures that the foreign key column in the child table can reference an existing parent row. It also reflects the aggregate boundary: the application issues a single save operation on the root, while Spring Data JDBC coordinates writing the components that belong to the aggregate.

This lesson follows the insert flow of a new aggregate, from Java objects to conceptual SQL statements, explaining how the ID is propagated to child entities, the role of `@MappedCollection`, transactions, and error handling when part of the data cannot be inserted.

## 1. Aggregate root and child entities

Suppose a sales application has an order consisting of general information and multiple order lines:

- `PurchaseOrder` is the **aggregate root**, representing the order and serving as the entry point for persisting the aggregate.
- `OrderLine` is a child entity belonging to the lifecycle of the order.
- A single order can contain multiple order lines.
- Each order line must reference the exact order that owns it.

Relational model:

~~~mermaid
erDiagram
    PURCHASE_ORDERS ||--o{ ORDER_LINES : contains
    PURCHASE_ORDERS {
        bigint id PK
        bigint customer_id
        varchar status
    }
    ORDER_LINES {
        bigint id PK
        bigint order_id FK
        integer line_no
        varchar sku
        integer quantity
    }
~~~

The `purchase_orders` table stores one row per order. The `order_lines` table stores multiple rows, each representing an order line. The `order_lines.order_id` column is a foreign key pointing to `purchase_orders.id`.

In Spring Data JDBC, the aggregate root is the object that the repository persists. Child entities are declared through mappings within the aggregate, without needing to create an independent repository just to save individual order lines belonging to an order.

### Aggregate root is not synonymous with parent table in every model

An aggregate is a consistency boundary in the business domain model. In this example, it corresponds to one root table and one child table. An aggregate can also have embedded value objects stored in the same root row, multiple types of child entities in different tables, or nested child entities, as long as they belong to the same aggregate boundary.

Another aggregate such as `Customer` has an independent lifecycle. An order can store the customer ID as a reference, but saving an order does not automatically insert or update the customer aggregate.

## 2. Mapping root and child with Spring Data JDBC

The aggregate root uses `@Table` to specify the table and `@Id` to mark the identifier. The child entity collection uses `@MappedCollection` to specify the foreign key column in the child table.

### 2.1. Child entity

~~~java
import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    @Column("sku")
    private String sku;

    @Column("quantity")
    private int quantity;

    @Column("unit_price")
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be non-negative");
        }

        this.sku = sku;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
~~~

`OrderLine.id` is the order line row's own identifier. It is not the foreign key pointing to the order. The child's foreign key is managed by Spring Data JDBC through the collection mapping.

### 2.2. Aggregate root

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Long customerId, List<OrderLine> lines) {
        this.customerId = Objects.requireNonNull(customerId);
        this.status = "NEW";
        this.lines = new ArrayList<>(Objects.requireNonNull(lines));

        if (this.lines.isEmpty()) {
            throw new IllegalArgumentException("An order needs at least one line");
        }
    }

    public void addLine(OrderLine line) {
        lines.add(Objects.requireNonNull(line));
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Key details:

- `@Id` on `PurchaseOrder.id` marks the root's identifier.
- `@MappedCollection(idColumn = "order_id")` specifies the column in the child table that holds the root's ID.
- `keyColumn = "line_no"` specifies the column that stores the element's position in the `List`.
- `OrderLine` does not need to declare a Java `orderId` field just to repeat the back reference that the collection mapping already manages.
- `PurchaseOrderRepository` is the entry point for persisting the aggregate.

`idColumn` is the column name **in the child table**, not the Java property name of the root. With the mapping above, each order line is written to `order_lines` with `order_id` equal to the ID of `purchase_orders`.

If you use `Set<OrderLine>` instead of `List<OrderLine>`, there is no stable element position like a list. If you use `Map<K, OrderLine>`, the key column stores the map key. Choose the collection based on business semantics and design the schema accordingly.

## 3. The relational schema must exist first

Spring Data JDBC maps objects to the schema; it does not automatically create tables or constraints just because entities have annotations. Use migrations (Flyway, Liquibase, or your project's schema management tool) to create the tables and foreign keys.

PostgreSQL example:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 4) NOT NULL CHECK (unit_price >= 0),

    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id),

    CONSTRAINT uq_order_lines_position
        UNIQUE (order_id, line_no)
);
~~~

Here:

- The root has an auto-generated primary key.
- The child has its own auto-generated primary key.
- `order_lines.order_id` is a foreign key to the root.
- `line_no` stores the order of elements in the `List`.
- `UNIQUE(order_id, line_no)` prevents two lines from occupying the same position within one order.
- `CHECK(quantity > 0)` enforces the quantity rule at the database level.

Table and column names must match Spring Data JDBC's mapping, including the naming strategy and identifier quoting rules if the project has custom configuration.

### Why is a foreign key column needed in the child table?

An `order_lines` row must identify which order it belongs to. When the root is inserted, the database generates an ID. The subsequent child insert writes this ID into `order_id`.

Without a foreign key, the application could create an order line pointing to a non-existent order. SQL constraints serve as the final line of defense, even when data is written through a tool outside Spring Data JDBC.

### Why is the position column part of the schema?

A `List` is ordered. If you want that order to be stored and restored, the child table needs a key/index column, such as `line_no`. A unique constraint on the pair `(order_id, line_no)` guarantees that a position is not duplicated within the same order.

Do not place `UNIQUE(line_no)` alone: doing so would prevent two different orders from both having a line at position 0, even though that is completely valid.

## 4. General insert flow: root first, children second

When a repository saves a new aggregate, the conceptual sequence is:

1. Spring Data JDBC receives the aggregate root.
2. The framework determines that the aggregate is new based on identifier/version metadata or the newness strategy.
3. The framework generates an insert statement for the root table.
4. The database inserts the root and generates an ID if using auto-generation.
5. Spring Data JDBC receives the generated ID value and updates/propagates that value into the aggregate persistence process.
6. The framework inserts the child entities, setting the back-reference column to the root's ID.
7. Nested child entities continue to be written according to the relational structure and foreign key dependency order.
8. The transaction completes with a commit if all operations succeed.

~~~mermaid
sequenceDiagram
    participant App as Application Service
    participant Repo as PurchaseOrderRepository
    participant SD as Spring Data JDBC
    participant DB as Database

    App->>Repo: save(newOrder)
    Repo->>SD: persist aggregate
    SD->>DB: INSERT purchase_orders
    DB-->>SD: generated order id
    SD->>SD: associate generated id with aggregate
    loop each OrderLine
        SD->>DB: INSERT order_lines(order_id, line_no, ...)
        DB-->>SD: child result / generated child id
    end
    SD-->>Repo: saved aggregate
    Repo-->>App: savedOrder
~~~

Root-first makes direct sense for foreign keys: a child can only reference a root after the root has been created. Spring Data JDBC does not require the application to manually insert the root, retrieve the ID, and then call a child repository step by step; the framework orchestrates saving the components belonging to the aggregate.

### Conceptual SQL executed

The exact statements depend on the database dialect, key generation mechanism, and framework version. Logically, it is equivalent to:

~~~sql
INSERT INTO purchase_orders (customer_id, status)
VALUES (42, 'NEW')
RETURNING id;
~~~

Assuming the database returns order ID `9001`, the subsequent order lines look like:

~~~sql
INSERT INTO order_lines
    (order_id, line_no, sku, quantity, unit_price)
VALUES
    (9001, 0, 'BOOK-01', 2, 120000.00);

INSERT INTO order_lines
    (order_id, line_no, sku, quantity, unit_price)
VALUES
    (9001, 1, 'PEN-02', 3, 15000.00);
~~~

`9001` is only an illustrative ID. The application must never guess the ID or hardcode assumed values for children. The actual ID comes from the database during the root insert.

Some databases/drivers use a mechanism for retrieving generated keys other than the `RETURNING` syntax. Therefore, do not assume that SQL logs across all database systems will look identical to the PostgreSQL example.

## 5. How is the root's ID propagated to children?

For a root using an auto-generated ID, before inserting, the new object's ID property usually has no value:

~~~java
PurchaseOrder order = new PurchaseOrder(customerId, lines);

assert order.getId() == null;
~~~

When the root insert succeeds, the database returns the ID. Spring Data JDBC uses that ID as the back-reference column value for the children in the aggregate.

~~~text
Before insert:

PurchaseOrder.id = null
  ├── OrderLine[0]
  └── OrderLine[1]

After inserting root, database returns id = 9001:

PurchaseOrder.id = 9001
  ├── OrderLine[0] -> order_id = 9001
  └── OrderLine[1] -> order_id = 9001
~~~

The child's foreign key takes the root's ID, not the child's own ID. Each child may have its own ID generated by the `order_lines` table.

### Auto-generated ID vs. pre-assigned ID

There are two common cases:

| Root identification approach | Before saving | Insert flow |
| --- | --- | --- |
| Database-generated ID | Usually null for wrapper types like Long | Insert root, retrieve ID, then insert children |
| Application-assigned ID | Already has a valid ID | Insert root with assigned ID, then insert children using that ID |

Example of an application-assigned ID:

~~~java
PurchaseOrder order = new PurchaseOrder(9001L, customerId, lines);
repository.save(order);
~~~

The constructor and newness strategy must match pre-assigned IDs. Spring Data JDBC needs to know whether the aggregate is new or already exists; do not simply change an ID from null to an arbitrary value without understanding the rules for determining an entity's new state.

With wrapper types like `Long`, null is typically a convenient signal for an ungenerated ID. With primitive `long`, the default value is 0, so you must understand how the framework detects newness and consider `@Version` or `Persistable` when the ID strategy requires it.

### Using the aggregate returned from save

You should use the return value from the repository:

~~~java
PurchaseOrder saved = repository.save(order);

Long orderId = saved.getId();
~~~

For immutable entities or mappings using constructors/property accessors to create new instances, the framework may return a new instance containing the generated ID rather than mutating the original object in place. Therefore, do not assume the original `order` variable is always updated with the ID in every model.

## 6. Repositories only save the aggregate root

The repository can be declared simply:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

The service creates the root and children and calls `save` once:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long placeOrder(Long customerId) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK-01", 2, new BigDecimal("120000.00")),
            new OrderLine("PEN-02", 3, new BigDecimal("15000.00"))
        );

        PurchaseOrder order = new PurchaseOrder(customerId, lines);
        PurchaseOrder saved = orders.save(order);

        return saved.getId();
    }
}
~~~

A business operation that creates an order only needs to save the aggregate root. Spring Data JDBC is responsible for writing the child entities declared inside the aggregate.

There is no need for the manual approach: inserting the root first, retrieving the ID, and calling another repository for each child. That approach detaches child writes from the aggregate, exposes foreign keys, and forces the application to manage ordering and transactions manually. It also stops reflecting the domain meaning that order lines belong to the order's lifecycle. Only use a separate repository for a child when the model truly defines it as an independent aggregate root.

### Other aggregates are not automatically inserted

Suppose `PurchaseOrder` has `customerId` or `AggregateReference<Customer, Long>`. This is a reference to a separate customer aggregate. When saving the order:

- Spring Data JDBC uses the customer ID to write the `customer_id` column.
- It does not automatically insert `Customer` if that ID does not exist yet.
- If the database has a foreign key, a non-existent customer ID will cause the root insert to be rejected.
- Creating a customer is a separate operation aligned with aggregate and business boundaries.

This differs from `OrderLine`, which is declared as a child entity in `@MappedCollection`.

## 7. @MappedCollection determines the link columns

`@MappedCollection` describes how a child entity collection is stored in another table:

~~~java
@MappedCollection(
    idColumn = "order_id",
    keyColumn = "line_no"
)
private List<OrderLine> lines;
~~~

The two attributes have distinct meanings:

- `idColumn`: the column name in the child table that holds the aggregate root's ID.
- `keyColumn`: the column name that holds the collection key; for a `List`, this is the element's position.

Child table example:

~~~sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL
);
~~~

In the `OrderLine` class, it is not necessary to have an `orderId` field. Spring Data JDBC knows the linking column through the root's collection mapping.

### List collections

With `List`, element ordering is meaningful:

~~~java
List<OrderLine> lines = List.of(
    new OrderLine("A", 1, new BigDecimal("10.00")),
    new OrderLine("B", 2, new BigDecimal("20.00"))
);
~~~

The framework stores the corresponding key/index in the `line_no` column. When reading the aggregate, elements are reconstructed according to the collection key.

If business ordering must remain stable, the schema should protect the `(order_id, line_no)` pair with a unique constraint. If the ordering is merely for temporary presentation, decide whether it needs to be persisted at all.

### Set and Map collections

`Set` does not represent position like `List`. If ordering is not meaningful, using a Set may be appropriate. Child equality/hashCode must be designed carefully, especially when entities have database-generated IDs that only exist after insert.

With `Map<K, OrderLine>`, the key column stores the map key. The key type must map to an appropriate SQL type. Declare `keyColumn` explicitly when the schema has a specific business column name.

## 8. Root with embedded value objects and child entities

An aggregate can contain both embedded objects and child entities:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

The write flow involves two kinds of data:

- Properties of `Address` are written to the `shipping_*` columns in the root row.
- `OrderLine` instances are written as separate rows in the `order_lines` table, with `order_id` pointing to the root.

There is no separate insert for `Address` because it is not a child entity in another table. This is an important distinction when reading SQL logs: the number of insert statements depends on the aggregate structure and mapping types.

## 9. Transactions protect the entire write flow

Saving an aggregate can execute multiple SQL statements:

1. Insert the root.
2. Insert the first child.
3. Insert the second child.
4. Insert nested child entities if present.

Repository write operations are managed within transactions according to Spring Data JDBC configuration; services can use `@Transactional` to extend the boundary across multiple business operations.

Example:

~~~java
@Transactional
public Long placeOrder(Long customerId) {
    PurchaseOrder order = buildOrder(customerId);
    PurchaseOrder saved = orders.save(order);

    auditRepository.save(
        OrderAudit.created(saved.getId())
    );

    return saved.getId();
}
~~~

This snippet assumes the audit record is written to the same database and uses the same transaction manager. If both saving the order and writing the audit record belong to the same transaction, a failure in the audit step can roll back the entire order.

### What happens if a child insert fails?

Suppose the second order line violates a unique constraint or check constraint. If the entire flow is within a transaction:

- The database rejects the second insert.
- The exception is translated through the Spring JDBC/Spring Data layer.
- The transaction manager rolls back the transaction.
- The root row and any previously inserted child rows within the same transaction are also rolled back.

If code catches an exception and swallows it inside a transaction without marking rollback, the application may cause the transaction to commit in an unintended state. Let the exception propagate out or mark rollback according to appropriate rules.

### Same DataSource and transaction manager

For operations to participate in the same transaction:

- Repositories and JDBC operations must use the same DataSource.
- The transaction manager must manage that DataSource.
- Calls must occur within the same Spring transaction context.
- Do not manually open an independent connection via `DriverManager` and commit separately.

A standard JDBC transaction is bound to the execution thread. Offloading child writes to an asynchronous thread does not automatically propagate the caller's transaction.

## 10. Insert ordering and foreign key constraints

Because children reference the root, the insert order is root first and children second. Attempting to insert a child first with a non-existent `order_id` is rejected by the database due to the foreign key.

~~~sql
-- Invalid if order_id 9001 does not exist yet.
INSERT INTO order_lines(order_id, line_no, sku, quantity, unit_price)
VALUES (9001, 0, 'BOOK-01', 2, 120000.00);
~~~

After the root is inserted:

~~~sql
INSERT INTO purchase_orders(customer_id, status)
VALUES (42, 'NEW')
RETURNING id;
~~~

and the database returns a valid ID, the child inserts can then reference that ID.

Do not disable foreign keys or defer constraints merely to allow out-of-order inserts. Spring Data JDBC already organizes the write flow according to aggregate relationships; the schema should accurately reflect these relationships.

### Multiple levels of child entities

Suppose an aggregate has a root, order lines, and a set of child attributes per line:

~~~mermaid
flowchart TD
    A["PurchaseOrder"] --> B["OrderLine 1"]
    A --> C["OrderLine 2"]
    B --> D["LineAdjustment 1"]
    B --> E["LineAdjustment 2"]
    C --> F["LineAdjustment 3"]
~~~

Each level has its own table and back-reference column. A child entity's parent row must be created before writing any rows that depend on it. When designing multi-level hierarchies, clearly define aggregate boundaries, foreign keys, and collection mappings; avoid modeling every object association as a nested aggregate if they have independent lifecycles.

## 11. Generated ID of child entities

A child can have its own ID:

~~~java
@Id
private Long id;
~~~

If the schema defines an auto-generated ID, each child insert can receive an ID from the database. This ID is distinct from `order_id`:

| Column | Meaning |
| --- | --- |
| `order_lines.id` | Identifier of the order line |
| `order_lines.order_id` | ID of the order owning the line |
| `order_lines.line_no` | Position of the order line in the List |

A child row might have:

~~~text
id = 501
order_id = 9001
line_no = 0
sku = BOOK-01
~~~

`501` is the order line's own ID; `9001` is the root ID. Do not confuse these two values just because both are numbers.

Not every child entity is required to have its own separate business ID. Depending on the model and mapping, another key or suitable column combination may be used. Whichever structure you choose, ensure child rows can be identified and updated/deleted in a manner compatible with Spring Data JDBC and the schema.

## 12. What the insert flow does not do

| Assumption | Reality |
| --- | --- |
| Calling `save(root)` only inserts one row | If the aggregate has children, the framework also writes the child entities belonging to the aggregate |
| Spring Data JDBC auto-creates tables and FKs | The schema must be created using migrations/schema management tools |
| Children automatically know the root ID via a mandatory field | Collection mapping provides the back reference via `idColumn` |
| Saving root auto-inserts a referenced Customer | Other aggregates have separate lifecycles; references only use IDs |
| `@MappedCollection` is identical to JPA's `@OneToMany` | This is a Spring Data JDBC mapping with its own aggregate semantics |
| `@Embedded Address` is inserted into an `addresses` table | Embedded fields reside in the root row |
| Generated IDs always mutate the original object | Always use the aggregate returned from `save`, especially for immutable objects |
| Catching every exception and continuing is safe | May cause the transaction to commit incorrectly if not rolled back |
| Disabling FKs makes inserts easier | Removes an essential layer of data integrity protection |

Spring Data JDBC is not an ORM with a JPA-style persistence context. It persists aggregates through repositories following the aggregate model, rather than tracking arbitrary objects across the entire application.

## 13. Error handling and observing the insert flow

Some common issues:

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Root insert succeeds but children are not written | Children are not declared as persistent properties/collection mappings | Check `@MappedCollection` and property types |
| Child insert fails with FK violation | Wrong `idColumn`, invalid root ID, or wrong schema FK | Match mapping against DDL |
| Child written into wrong back-reference column | `idColumn` name does not match schema | Explicitly declare `idColumn` |
| List ordering is lost | Missing or misconfigured `keyColumn` | Use an appropriate key/index column |
| Two children share the same position | Key column is not unique per root | Create `UNIQUE(root_id, key)` |
| Root insert fails with unique violation | Root data violates constraint | Validate data and translate to appropriate business error |
| Saving child fails but root remains | Operations are outside a shared transaction or use an independent connection | Check transaction manager/DataSource |
| ID missing on the original object | Immutable entity or `save` returns a new instance | Use the object returned from `save` |
| Repository cannot find table/column | Mapping names do not match migration | Check `@Table`, `@Column`, NamingStrategy, and schema |

### Observing SQL in development environments

You can enable Spring JDBC logging when using Spring Boot:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

Logs help verify:

- The root insert executes first.
- The root ID value is used for child inserts.
- Table and column names match the schema.
- Bound parameters have expected values.

SQL logs can contain sensitive data in bound parameters. Only enable detailed levels in development environments and control logging in production.

### Verifying data after insert

With PostgreSQL:

~~~sql
SELECT id, customer_id, status
FROM purchase_orders
ORDER BY id DESC
LIMIT 5;

SELECT id, order_id, line_no, sku, quantity
FROM order_lines
WHERE order_id = 9001
ORDER BY line_no;
~~~

Replace `9001` with the actual ID returned from the repository. This query confirms that the root and children belong to the same aggregate.

## 14. Designing services and transactions properly

A service should place transactions at business boundaries, such as order creation:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        List<OrderLine> lines = command.lines().stream()
            .map(line -> new OrderLine(
                line.sku(),
                line.quantity(),
                line.unitPrice()
            ))
            .toList();

        PurchaseOrder order = new PurchaseOrder(
            command.customerId(),
            lines
        );

        return orders.save(order).getId();
    }
}
~~~

Transactions ensure aggregate creation completes as an atomic unit. The service is also the appropriate place to enforce cross-data business rules, though critical constraints such as FKs, unique constraints, and checks must still be enforced in the database.

If the service needs another operation such as writing an outbox record to the same database, that operation can be placed in the same transaction. If sending emails or calling external APIs, do not assume a JDBC transaction can roll back external side effects. For events that must be published after commit, consider a transactional outbox or an appropriate after-commit mechanism.

### Avoid splitting aggregate persistence operations

If each order line were saved using an independent repository, the application would have to ensure on its own that:

- The root already exists.
- The root ID is passed correctly.
- All children share the same transaction.
- Collection positions do not collide.
- When one child fails, previous operations roll back.

Saving through the root keeps orchestration responsibility in one place with Spring Data JDBC. Split a child out of an aggregate only when the business domain model truly requires that child to have an independent lifecycle.

## 15. Hands-on exercises

### Exercise 1 — Observing SQL order

Create a `PurchaseOrder` aggregate with two `OrderLine` instances. Enable SQL logging and call repository `save` once. Record the order of insert statements and explain why the root must be inserted before the children.

### Exercise 2 — Tracking generated IDs

Leave `PurchaseOrder.id` null before saving. After saving, inspect the ID in the returned object and the `order_id` values in the `order_lines` table. Explain why IDs must not be hardcoded.

### Exercise 3 — Changing the back-reference column

Change `@MappedCollection(idColumn = "order_id")` to another name without changing the schema. Observe the error. Then update the migration and explain the relationship between the annotation and the physical column.

### Exercise 4 — List and key column

Use `List<OrderLine>` with `keyColumn = "line_no"`. Save three order lines, read the aggregate back, and confirm the order. Try creating a unique constraint on `(order_id, line_no)` and manually inserting two rows at the same position.

### Exercise 5 — Transaction rollback

Create a constraint that causes the second child to fail (for example, quantity must be greater than 0). Verify that repository `save` fails and no root/child rows are committed in the transaction. Run this in a test database.

### Exercise 6 — Aggregate reference

Add `customerId` to the root and create an FK to the `customers` table. Try saving an order with a non-existent customer ID. Explain why Spring Data JDBC does not automatically create `Customer` when saving `PurchaseOrder`.

### Exercise 7 — Embedded and child table

Add an embedded `Address` to the root alongside `List<OrderLine>`. Observe the number of tables/insert statements and distinguish which data resides in the root row versus which data is inserted as separate rows.

## 16. Official references

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): aggregate mapping, entity references, and collections.
- [Spring Data Relational — JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html): how repositories persist aggregates.
- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): how Spring Data instantiates objects and manages mapping metadata.
- [Spring Data Relational — `@MappedCollection` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/MappedCollection.html): declaring linking ID and key columns for collections.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries and behavior of `@Transactional`.

Inserting the root first and then writing child entities is how Spring Data JDBC maintains aggregate relationships: the root is created to obtain an ID, that ID becomes the foreign key for the children, and the entire operation runs within an appropriate transaction. When collection mappings, FK schemas, and transaction boundaries are designed consistently, the application can persist an aggregate with a single repository call while still protecting data integrity.
