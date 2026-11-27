# Simplicity Philosophy: No Persistence Context, Dirty Checking, or Lazy Loading

In the Spring ecosystem, **Spring Data JDBC** is a way of mapping relational data to Java objects in a simple, transparent manner that treats the **aggregate** as the unit of work. It provides repositories, table–object mapping, and the necessary data lifecycle management, while intentionally avoiding several complex mechanisms familiar from JPA/Hibernate.

The three most important characteristics of this philosophy are:

1. **No persistence context** in the JPA sense: the framework does not maintain a managed cache of tracked entities across a session.
2. **No dirty checking**: mutating fields on a Java object does not automatically generate an `UPDATE` statement when a transaction ends.
3. **No automatic lazy loading** for mapped relationships: the framework does not create proxies to defer querying associations until a getter is invoked.

These choices are interconnected. When objects are not held inside a persistence context, the framework does not need to retain prior snapshots for comparison, nor does it need to manage proxies and session lifecycles. In return, the application must make explicit **when to read, when to modify, and when to save**.

## 1. Where Does Spring Data JDBC Fit in the Spring Ecosystem?

Spring JDBC, Spring Data JDBC, and Spring Data JPA all help applications work with relational databases, but at different levels of abstraction.

| Technology | Primary way of working | What the developer is typically responsible for |
|---|---|---|
| Spring JDBC / `JdbcTemplate` | Write SQL, pass parameters, map each result row | Designing SQL statements and data mapping |
| **Spring Data JDBC** | Map aggregates to tables, provide repositories and save/find operations | Designing aggregate boundaries, calling `save(...)` explicitly, understanding write cost |
| Spring Data JPA (usually Hibernate) | Map entities and associations per JPA, with a persistence context | Understanding entity states, flush, dirty checking, fetch strategies, and session lifecycle |

Spring Data JDBC is not a stripped-down version of Hibernate. It chooses a different consistent model: **the aggregate root is the entry point for data**, components within the same aggregate share a lifecycle, and references to other aggregates should be expressed by identifier.

For example, a `PurchaseOrder` may own its `OrderLine` items. Conversely, `Customer` is usually an independent aggregate: the order only stores `customerId` rather than loading and managing the entire `Customer` object as an internal component.

## 2. What Does Having No Persistence Context Mean?

### 2.1. Persistence Context in JPA

In JPA, when an entity is loaded and remains in the *managed* state, the persistence context retains information to manage that entity. Within the same persistence context, looking up an entity by the same identifier typically returns the same managed instance. The persistence context also coordinates synchronizing data to the database upon *flush*.

Example of the JPA mindset:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
    // Entity is managed; JPA can automatically detect changes on flush.
}
~~~

Here the `UPDATE` can happen at flush/commit even though the method never calls `save(...)`. That behavior is tied to *managed* state and dirty checking, not an inherent property of every database access technology.

### 2.2. Spring Data JDBC Does Not Manage Objects That Way

With Spring Data JDBC, an object read through a repository is simply the result of mapping existing data. The framework does not maintain a JPA-style identity map to track that instance throughout the transaction.

~~~java
@Transactional(readOnly = true)
public void inspect(Long orderId) {
    PurchaseOrder first = repository.findById(orderId).orElseThrow();
    PurchaseOrder second = repository.findById(orderId).orElseThrow();

    System.out.println(first == second); // Typically: false
}
~~~

Each lookup can query the database and instantiate a fresh object. Because there is no JPA-style persistence context, you do not have workflows built around `attach`, `detach`, `merge`, and `flush` of managed entities.

**Practical consequences:**

- Do not assume repeated loads for the same key share the same Java object reference.
- Do not expect mutations on one instance to appear automatically in an instance loaded earlier.
- When you need the latest data after a write operation, re-query as needed; objects already held in memory are not auto-synchronized.
- A database transaction can still exist, yet that transaction does not turn objects into JPA-tracked managed entities.

> **Distinguish two concepts:** `@Transactional` manages database transactions and connections via Spring infrastructure. JPA's persistence context manages entity state. Spring Data JDBC supports transactions without having a JPA-style persistence context.

## 3. No Dirty Checking: Mutating an Object Does Not Mean Saving Data

*Dirty checking* is the mechanism that detects modified fields on a managed entity and generates write operations during flush. Spring Data JDBC does not do this automatically.

Compare the two methods below:

~~~java
@Transactional
public void addLineWithoutSaving(Long orderId) {
    PurchaseOrder order = repository.findById(orderId).orElseThrow();
    order.addLine("BOOK-01", 2);

    // No repository.save(order).
    // Ending the transaction does not automatically save the added line.
}

@Transactional
public void addLineAndSave(Long orderId) {
    PurchaseOrder order = repository.findById(orderId).orElseThrow();
    order.addLine("BOOK-01", 2);

    repository.save(order); // Tells Spring Data JDBC to write the aggregate.
}
~~~

In the first method, the Java object changed, but the database was never instructed to write. In the second method, calling `save(order)` explicitly marks when the write occurs.

You can picture the flow like this:

~~~text
Repository.findById(id)
        |
        v
Read data from database
        |
        v
Build Java aggregate
        |
        v
Call domain method to change state
        |
        +---- Without save(...) ---> Only changes state in memory
        |
        +---- With save(...) ------> Executes database write operations
                                        |
                                        v
                                  Transaction commit
~~~

A key point is that **transaction commit only confirms SQL operations already executed within the transaction**. It does not scan every loaded Java object to decide which ones should be updated.

### 3.1. `save(...)` Does Not Mean Updating Only Changed Columns

When `save(...)` is called, Spring Data JDBC works with the state of the **aggregate** rather than a list of dirty fields. Depending on the mapping structure and whether the entity is new or existing, it may run `INSERT`, `UPDATE`, or child-element operations.

In particular, when re-saving an aggregate with child entities, the default write strategy may **delete and re-insert child records** to match the new aggregate state. Do not assume a small collection edit always produces a single `UPDATE` on a single child row.

This leads to two design guidelines:

- Aggregates should have sensible boundaries; avoid stuffing a huge object graph under one root.
- Localized updates requiring high write throughput should be verified against actual SQL. When needed, redesign aggregate boundaries or use an explicit update operation.

### 3.2. Return Value of `save(...)`

You should generally use the object returned by `save(...)`, especially with immutable domain designs or auto-generated keys:

~~~java
PurchaseOrder newOrder = new PurchaseOrder("CUSTOMER-42");
PurchaseOrder savedOrder = repository.save(newOrder);

Long generatedId = savedOrder.getId();
~~~

The framework may need to supply an ID or version value after saving. Do not assume every object type is always mutated in place.

## 4. No Lazy Loading: What Data Is Loaded Must Be Designed Explicitly

In JPA/Hibernate, certain associations can be mapped lazily. Accessing the association later can trigger SQL via a proxy or persistent collection, provided access conditions and session state allow it.

~~~java
// Illustrating the JPA/Hibernate concept
Order order = entityManager.find(Order.class, orderId);
List<OrderLine> lines = order.getLines(); // Depending on mapping, may load here.
~~~

Spring Data JDBC does not use automatic lazy-loading proxies for relationships inside an aggregate. When a repository loads an aggregate under standard mapping, components belonging to the aggregate are loaded as part of the read operation. Reading `order.getLines()` afterward simply accesses data already present in the object, without firing a lazy query like JPA.

This brings clear benefits:

- Database access flow is easy to observe: queries happen at repository calls or explicit query invocations.
- No need to rely on an open JPA session to traverse a lazy proxy.
- Domain code never has to worry about a getter unexpectedly executing SQL.

However, avoid misunderstandings:

- **No lazy loading does not mean every aggregate always takes a single SQL query.** Reconstructing an aggregate with collections may still issue multiple queries depending on mapping and loading strategy.
- No lazy loading also does not automatically eliminate **N+1 query** problems. If you load 100 aggregates by calling a repository 100 times in a loop, the application still performs many database round-trips.
- If a screen only needs a few columns, there is no reason to load a large aggregate. Use an explicit query, DTO/projection, or a dedicated read repository.

### 4.1. Relationships to Other Aggregates

Suppose an order needs to know the customer and products. In the Spring Data JDBC model, typically:

~~~text
PurchaseOrder (aggregate root)
    |
    +-- OrderLine         (component belonging to PurchaseOrder)
    |
    +-- customerId        (identifier referencing Customer)

Customer (separate aggregate root)
Product  (separate aggregate root)
~~~

Do not place an independent `Customer` directly into a relationship field on `PurchaseOrder` and expect Spring Data JDBC to treat it like JPA's `@ManyToOne(fetch = LAZY)`. Store the reference key and explicitly look up `Customer` via its repository or an appropriate query when the application actually needs customer data.

Spring Data JDBC also provides `AggregateReference<T, ID>` to represent ID references where appropriate; it does not imply automatically loading the referenced object.

## 5. Complete Example: An Order Aggregate

The example below uses Spring Boot 3.x, Spring Data JDBC, and a simple relational model. Its goal is to show how reading, modifying, and saving happen transparently.

### 5.1. Table Design

Assume a database supporting corresponding identity syntax:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    customer_code VARCHAR(80) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_position INTEGER NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_position),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

The `order_lines` table has foreign key `order_id` pointing to the aggregate root and `line_position` representing the element's position in the list.

`GENERATED BY DEFAULT AS IDENTITY` is an illustrative example; when using PostgreSQL, MySQL, H2, or another engine, choose DDL matching your actual database.

### 5.2. Aggregate Root `PurchaseOrder`

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String customerCode;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_position")
    private List<OrderLine> lines = new ArrayList<>();

    private PurchaseOrder() {
        // Used for materializing the object from the database.
    }

    public PurchaseOrder(String customerCode) {
        if (customerCode == null || customerCode.isBlank()) {
            throw new IllegalArgumentException("Customer code is required");
        }
        this.customerCode = customerCode;
    }

    public void addLine(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        lines.add(new OrderLine(sku, quantity));
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

`@Id` identifies the root's primary key. `@Version` enables **optimistic locking** when saving the aggregate. `@MappedCollection` describes elements owned by the aggregate and the columns storing the link/position.

This is aggregate-ownership mapping: `OrderLine` belongs to the lifecycle of `PurchaseOrder`. The collection is not a lazy-loaded proxy relationship.

### 5.3. Child Component `OrderLine`

~~~java
import org.springframework.data.relational.core.mapping.Table;

@Table("order_lines")
public class OrderLine {

    private String sku;
    private int quantity;

    private OrderLine() {
        // Used for materialization.
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

In this model, `OrderLine` is a component persisted through the aggregate root. The application does not need a standalone repository to manage the lifecycle of individual `OrderLine` items.

### 5.4. Repository

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Spring Data JDBC implements CRUD operations from the repository interface. You do not need to write basic `INSERT` and `SELECT` statements manually for the aggregate.

### 5.5. Application Service Making Write Timing Explicit

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createOrder(String customerCode) {
        PurchaseOrder order = new PurchaseOrder(customerCode);
        PurchaseOrder saved = repository.save(order);
        return saved.getId();
    }

    @Transactional
    public void addProduct(Long orderId, String sku, int quantity) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));

        order.addLine(sku, quantity);
        repository.save(order);
    }

    @Transactional(readOnly = true)
    public PurchaseOrder getOrder(Long orderId) {
        return repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));
    }
}
~~~

When `addProduct(...)` is called, the application executes three clear steps:

1. The repository reads `PurchaseOrder` from the database.
2. The domain method `addLine(...)` mutates the object's state in memory.
3. The repository `save(...)` writes the aggregate state to the database, within the transaction managed by `@Transactional`.

If step 3 is omitted, the change in step 2 is not saved automatically. If saving fails and the transaction rolls back, SQL operations in the transaction are rolled back by the database's transaction mechanism.

> The Java classes above correspond to separate source files in a project. The example focuses on mapping and persistence lifecycle; datasource configuration, dependencies, and migrations are set up as in a standard Spring Boot application.

## 6. What Happens When Saving an Aggregate with a Collection?

Consider an order that currently has two lines, and then a third line is added:

~~~text
Initial database:
  purchase_orders: Order #10
  order_lines:      [A, B]

In Java after addLine(...):
  PurchaseOrder #10
    lines:          [A, B, C]

After repository.save(order):
  Database reflects aggregate state [A, B, C]
~~~

Crucially, the framework **has no JPA-style managed-entity state snapshot** to conclude that only line C changed. Under the aggregate write strategy, child records may be re-processed to recreate the collection.

Therefore, when data includes many child components, consider:

- **Aggregate boundary:** Only include data in the same aggregate if it genuinely needs to be controlled consistently alongside one root.
- **Write frequency:** Large aggregates where a single element changes frequently can incur significant write overhead.
- **Database constraints:** Foreign keys and unique constraints must tolerate the delete/insert ordering when saving collections.
- **Concurrency:** Multiple requests may read and then save the same root; use versioning or appropriate conflict-handling rules.
- **Read models:** For reports and read-only lists, querying a DTO is usually more sensible than materializing full aggregates.

If two objects have independent lifecycles, split them into two aggregates and link them by ID. Writing each aggregate then becomes explicit and easier to reason about for consistency and performance.

## 7. Transactions and Optimistic Locking Still Work

Having no persistence context and no dirty checking **does not mean transactions are unsupported**.

Spring Data JDBC uses Spring's transaction infrastructure. With `@Transactional`, multiple repository calls can share the same transaction when an appropriate transaction manager and datasource are configured.

~~~java
@Transactional
public void changeTwoOrders(Long firstId, Long secondId) {
    PurchaseOrder first = repository.findById(firstId).orElseThrow();
    PurchaseOrder second = repository.findById(secondId).orElseThrow();

    first.addLine("PENCIL", 1);
    second.addLine("PAPER", 2);

    repository.save(first);
    repository.save(second);
    // If an error triggers transaction rollback,
    // SQL operations in the transaction will not be committed.
}
~~~

### 7.1. Optimistic Locking with `@Version`

When a root has a `@Version` field, the repository can verify the current version during updates. If another transaction has modified the aggregate so the version in the database no longer matches, the save operation can fail with an exception in the `OptimisticLockingFailureException` family.

Timeline example:

| Time | Transaction A | Transaction B |
|---|---|---|
| T1 | Reads Order #10, version 3 | |
| T2 | | Reads Order #10, version 3 |
| T3 | Saves change, version increments | |
| T4 | | Attempts to save version 3 copy |
| Result | Write succeeds | Version conflict detected; handle appropriately |

Versioning is a concurrent-write control mechanism, **not** dirty checking. It takes effect when the program explicitly invokes a save operation.

The application must decide whether to report a conflict, reload for user review, or retry according to business rules. Never retry blindly when an operation has side effects.

### 7.2. Transactions Do Not Enable Lazy Loading

A method annotated with `@Transactional` still does not turn `getLines()` into a Hibernate-style lazy getter. Transactions protect executed database operations; they do not create a JPA persistence context or change Spring Data JDBC's fetching model.

## 8. When Should You Choose This Approach?

Spring Data JDBC is often a good fit when:

- The domain has clear aggregate boundaries and well-controlled child relationships.
- The team wants transparent, easy-to-reason-about read/write flows.
- The business model works naturally with calling `save(...)` explicitly after changes.
- You want to avoid SQL statements unexpectedly triggered by accessing lazy proxies.
- Workloads are primarily aggregate-level CRUD, combined with a few custom SQL queries for reporting reads.

JPA/Hibernate may be a better fit when an application requires a rich entity graph, varied fetch strategies, long-lived entity management within transactions, and deep use of ORM features. Those capabilities are valuable in many systems, though they demand clear understanding of entity states and query costs.

For Spring Data JDBC, simplicity lies mainly in the **lifecycle model**; it does not mean schema design, queries, transactions, or performance tuning automatically become effortless.

## 9. Common Misconceptions

| Claim | Accurate understanding |
|---|---|
| "With `@Transactional`, editing an object automatically saves it." | No. An explicit write call like `repository.save(...)` is required. |
| "Without a persistence context, every repository method runs outside a transaction." | No. Spring transactions still manage connections and the atomicity of SQL operations. |
| "No lazy loading means `findById(...)` always runs one SQL query." | No. Loading an aggregate with collections may require multiple SQL queries. |
| "Calling `save(...)` means only modified fields get `UPDATE`d." | There is no dirty checking guaranteeing that; child elements may be rewritten. |
| "Loading the same ID twice always returns the same Java object." | There is no JPA-style identity map guaranteeing that. |
| "Spring Data JDBC is just a renamed `JdbcTemplate`." | No. It provides aggregate mapping, repositories, lifecycles, and optimistic locking at a higher abstraction level. |
| "Without lazy loading, N+1 queries are impossible." | No. Calling a repository repeatedly in a loop can still produce N+1 or excessive queries. |
| "To reference Customer, you must put Customer inside Order." | No. Usually store `customerId` and load Customer explicitly as a separate aggregate. |

## 10. Reasoning Exercises

**Scenario A — forgot to save:** A service calls `findById(...)`, changes `customerCode`, and exits `@Transactional` without calling `save(...)`. Is the database updated?

**Answer:** No automatic update happens just because an object changed. The program must explicitly invoke a write operation.

**Scenario B — reading twice:** Within the same transaction, two `findById(10L)` calls return two distinct Java instances. Is this a mapping bug?

**Answer:** No. Spring Data JDBC does not provide a JPA-style persistence context identity map.

**Scenario C — accessing a collection:** Code already has a `PurchaseOrder` from the repository and calls `getLines()`. Does calling the getter trigger a lazy query by default?

**Answer:** No. Mapped components inside an aggregate are loaded according to the aggregate read mechanism, not via default lazy proxies.

**Scenario D — updating a single order line:** An order has hundreds of `OrderLine` items and the user edits only one quantity. Can we conclude `save(order)` always runs just a single `UPDATE order_lines` statement?

**Answer:** No. Understand the aggregate save strategy and inspect the generated SQL. If small updates happen frequently, reconsider the aggregate boundary or update approach.

## 11. Remembering the Operating Model

~~~text
Spring Data JPA (common illustration)
  load entity -> managed state -> edit fields
                            -> dirty checking / flush -> SQL

Spring Data JDBC
  repository.findById -> construct aggregate -> modify state in Java
                                                 |
                                                 v
                                            repository.save
                                                 |
                                                 v
                                             Execute SQL
~~~

The three choices—**no persistence context, no dirty checking, no automatic lazy loading**—are parts of a single philosophy: Spring Data JDBC prioritizes aggregate boundaries and explicit data operations. When using it, keep aggregates small and business-meaningful, choose when to load and save deliberately, and evaluate the SQL impact of every `save(...)` call.
