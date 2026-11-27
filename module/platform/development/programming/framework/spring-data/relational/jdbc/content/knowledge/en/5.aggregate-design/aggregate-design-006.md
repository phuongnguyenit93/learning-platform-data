# Designing Repositories for Aggregate Roots Instead of Every Table

In an application using **Spring Data JDBC**, a database table does not necessarily correspond to a repository. A repository should represent an **aggregate root** — the primary entry point to a group of objects that must change consistently according to business rules. This is a key architectural decision when designing aggregates in Spring Data Relational JDBC.

For example, an order may be stored across two tables `purchase_orders` and `order_lines`. If every table has an independent repository and services update each table arbitrarily, the application easily bypasses rules like "items cannot be added to a submitted order" or "a submitted order must have at least one line." A better model treats `PurchaseOrder` as the aggregate root and operates through `PurchaseOrderRepository`, while `OrderLine` is a component belonging to the order's lifecycle.

This lesson shows how to identify aggregate roots, map owned relationships with Spring Data JDBC, design repositories and services, handle multi-table reads, and clarify cases where a separate repository **should** exist.

## 1. What Does a Repository Represent in Spring Data JDBC?

### 1.1. Tables, Entities, Aggregates, and Repositories Are Distinct Concepts

| Concept | Role | Examples |
|---|---|---|
| **Table** | Stores data in a relational structure | `purchase_orders`, `order_lines`, `customers` |
| **Entity** | Object with identity in the domain; can be root or child element | `PurchaseOrder`, `OrderLine` |
| **Value object** | Value identified by attributes, usually without independent identity | `Money`, `Address` |
| **Aggregate** | Ownership and consistency protection boundary for a group of objects | An order together with its order lines |
| **Aggregate root** | Entity used as the entry point to modify the aggregate | `PurchaseOrder` |
| **Repository** | Interface for saving, reading, and deleting an **aggregate root** | `PurchaseOrderRepository` |

**An aggregate can span multiple tables**, and **a database can contain many aggregates**. Therefore, the number of repositories does not have to equal the number of tables.

Spring Data JDBC uses the Spring Data repository abstraction, yet differs from JPA in how it manages object graphs. It **has no JPA-style persistence context, dirty checking, or lazy loading**. When saving an aggregate, Spring Data JDBC treats the aggregate as the unit the repository operates on and executes the SQL statements required according to the mappings of components owned by the root.

### 1.2. Repositories Organized Around Roots

~~~mermaid
flowchart TB
    S["OrderApplicationService"] --> R["PurchaseOrderRepository"]
    R --> A["PurchaseOrder\naggregate root"]
    A --> L1["OrderLine #1"]
    A --> L2["OrderLine #2"]
    A -. "customerId" .-> C["Customer\nother aggregate root"]
    R --> P[("purchase_orders")]
    R --> Q[("order_lines")]
    CR["CustomerRepository"] --> C
    CR --> T[("customers")]
~~~

In the diagram:

- `PurchaseOrderRepository` is the gateway for writing and loading orders, including `OrderLine` items belonging to the aggregate.
- No `OrderLineRepository` is needed merely to add, edit, or delete individual lines within an order.
- `Customer` has its own lifecycle and business logic, so it can have its own `CustomerRepository`.
- `customerId` is a reference to another aggregate; it does not make `Customer` a child entity of `PurchaseOrder`.

The goal is not to minimize interface count at all costs. The goal is to **keep data modification paths aligned with the boundaries that protect business rules**.

## 2. Why Does the "One Repository Per Table" Design Easily Cause Bugs?

Suppose the database has three tables:

~~~text
purchase_orders
├── id
├── customer_id
└── status

order_lines
├── id
├── order_id
├── product_id
└── quantity

customers
├── id
└── name
~~~

A table-based repository split looks like:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {}

// Example of an inappropriate split when OrderLine belongs to the PurchaseOrder aggregate:
interface OrderLineRepository
        extends CrudRepository<OrderLine, Long> {}

interface CustomerRepository
        extends CrudRepository<Customer, Long> {}
~~~

*The snippet above illustrates a design decision to evaluate, not complete files to copy into a project.*

When `OrderLine` can be updated independently through its own repository, a service might accidentally:

1. Insert an additional line into an order already in `SUBMITTED` status, even though business rules forbid it.
2. Delete the last line without checking the order's minimum-lines rule.
3. Modify quantity in a transaction disconnected from checking the order's status.
4. Allow multiple places in the system to invent their own `OrderLine` save logic, scattering business rules.

The database can still enforce foreign keys and `NOT NULL`, yet not every business rule can be expressed with those constraints. Root-based repositories route modification operations through domain methods such as `addLine`, `changeQuantity`, `submit`, and `cancel`.

Moreover, in Spring Data JDBC, a child entity mapped via `@MappedCollection` normally has a foreign key column to the root managed by the mapping mechanism. If you turn a child entity into a separate aggregate root with another `CrudRepository`, you must redesign ownership and how the foreign key is written; it is not merely adding an interface.

## 3. How to Determine Aggregate Boundaries Before Writing Code

You should answer the following four groups of questions **before** creating repositories:

### 3.1. Which Object Enforces Business Invariants?

An *invariant* is a condition that must always hold true after a business change completes.

Example with orders:

- An order in `SUBMITTED` status must not allow adding order lines.
- Each order line's quantity must be positive.
- An order must have at least one line before submission.
- An order line belongs to exactly one order; it is not arbitrarily moved to another order.

`PurchaseOrder` is the root candidate because it must inspect both status and the set of lines before accepting changes.

### 3.2. Which Objects Have Independent Lifecycles?

`OrderLine` is typically created, changed, and deleted alongside `PurchaseOrder`. When an order is deleted, its lines are normally handled along with the order.

Conversely, a `Product` can be sold in thousands of orders and continues to exist when an order is deleted. Therefore, `Product` is a separate aggregate, and the order only stores `productId` plus transaction-time pricing details if the business requires it.

### 3.3. What Needs Consistency Within the Same Operation?

If the order's status and line list must be checked and saved consistently together, consider placing them in one aggregate. If two objects can change independently and are only combined when reading, they should usually be split into two aggregates.

Do not infer aggregate boundaries solely from foreign keys, JOIN structures, or relational ER diagrams. Foreign keys represent data links and constraints; they **do not automatically determine domain ownership**.

### 3.4. Is the Aggregate Too Large?

An aggregate spanning every related table can cause SQL statement counts during load and save to spike. In Spring Data JDBC, updating an aggregate with child collections can lead to **deleting and re-inserting child rows** per the aggregate persistence mechanism, rather than tracking per-object changes like JPA.

Thus, boundaries should be large enough to protect invariants, yet compact enough that a save does not turn into rewriting thousands of rows unnecessarily.

| Object | Belongs to `PurchaseOrder` aggregate? | Reason |
|---|---|---|
| `PurchaseOrder` | Yes, it is the root | Controls order status and order rules |
| `OrderLine` | Usually yes | Part of the order, lacking an independent business lifecycle |
| `Customer` | No | Customer profile changes independently |
| `Product` | No | Product exists independently and is referenced by many orders |
| `Payment` | Depends on domain | If payment has its own lifecycle, retries, refunds, and handling, it is usually another aggregate |
| `Shipment` | Depends on domain | If fulfillment is managed independently, consider a separate boundary |

The last two rows are domain-dependent design decisions. There is no rigid rule that names like `Payment` or `Shipment` always sit inside or outside `PurchaseOrder`.

## 4. Sample Design: PurchaseOrder and OrderLine

The hands-on section uses **Spring Boot, Spring Data JDBC, and H2**. The goal is to illustrate a repository managing a root across two tables. You can apply the same structure to PostgreSQL or MySQL by changing the driver and adjusting DDL for your database.

### 4.1. Required Dependencies

Create a Java 17+ project with Spring Initializr and select **Spring Data JDBC** and **H2 Database**. In Maven, the dependencies look like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Keep the parent and plugins generated by Spring Initializr so Spring Boot manages compatible dependency versions.

### 4.2. Schema for the Two Tables

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

The tables use H2 auto-generated IDs. The `order_id` column in `order_lines` is the foreign key for the owned relationship. `customer_id` and `product_id` here store only reference identifiers to other aggregates; for simplicity, the example omits creating customer and product tables.

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orderdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always

logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

In-memory H2 is suited for practice; data does not persist after the process ends. For production applications, use a durable database and manage schemas with a migration tool such as Flyway or Liquibase.

### 4.3. Order Status Enum

Create `src/main/java/com/example/orders/domain/OrderStatus.java`:

~~~java
package com.example.orders.domain;

public enum OrderStatus {
    DRAFT,
    SUBMITTED,
    CANCELLED
}
~~~

With a simple enum type, Spring Data JDBC can store the enum name in the `status` column and convert from the string column back to the enum when reading. If the database uses status codes different from enum names, configure a converter or appropriate mapping.

### 4.4. Child Entity OrderLine

Create `src/main/java/com/example/orders/domain/OrderLine.java`:

~~~java
package com.example.orders.domain;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    private Long productId;
    private int quantity;
    private BigDecimal unitPrice;

    protected OrderLine() {
        // For Spring Data's data mapping mechanism.
    }

    OrderLine(Long productId, int quantity, BigDecimal unitPrice) {
        if (productId == null) {
            throw new IllegalArgumentException("Missing productId");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid unit price");
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

Note: `OrderLine` **is still an entity** and has `@Id` because each order line has identity in the database. Yet it **is not an aggregate root** in this example. Therefore, having `@Id` does not mean creating `OrderLineRepository`.

In this class, there is no need to declare an `orderId` field. The ownership relationship will be declared on the root's collection with `@MappedCollection(idColumn = "order_id")`; Spring Data JDBC takes care of mapping the foreign key column in the child table when saving and reading the aggregate.

The constructor creating `OrderLine` is package-private. Domain methods on the root in the same `domain` package can instantiate lines, while external code should call the root's API.

### 4.5. Aggregate Root PurchaseOrder

Create `src/main/java/com/example/orders/domain/PurchaseOrder.java`:

~~~java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;
    private OrderStatus status;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderLine> lines = new LinkedHashSet<>();

    protected PurchaseOrder() {
        // For Spring Data JDBC.
    }

    private PurchaseOrder(Long customerId) {
        if (customerId == null) {
            throw new IllegalArgumentException("Missing customerId");
        }
        this.customerId = customerId;
        this.status = OrderStatus.DRAFT;
    }

    public static PurchaseOrder forCustomer(Long customerId) {
        return new PurchaseOrder(customerId);
    }

    public void addLine(Long productId, int quantity, BigDecimal unitPrice) {
        requireDraft();
        lines.add(new OrderLine(productId, quantity, unitPrice));
    }

    public void submit() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Cannot submit an order with no order lines");
        }
        status = OrderStatus.SUBMITTED;
    }

    public void cancel() {
        if (status == OrderStatus.CANCELLED) {
            return;
        }
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "This example only allows cancelling orders in DRAFT status");
        }
        status = OrderStatus.CANCELLED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only orders in DRAFT status can be modified");
        }
    }

    public Long getId() {
        return id;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Set<OrderLine> getLines() {
        return Set.copyOf(lines);
    }

    public BigDecimal total() {
        return lines.stream()
            .map(OrderLine::subtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
~~~

Here, `PurchaseOrder` is the root because critical mutating operations must pass through it:

- `forCustomer` creates an order in `DRAFT` status.
- `addLine` checks order status and line conditions.
- `submit` prevents submitting an empty order and transitions status.
- `cancel` defines the example's cancellation rule.
- `getLines` returns an unmodifiable set externally, preventing `getLines().clear()` from bypassing the root's rules.

A real-world system also typically includes `removeLine`, `changeQuantity`, line-count limits, total checks, and state transition rules. When adding such features, implement them as methods on the root rather than letting services mutate collections directly.

**Limitation of this example:** `Set<OrderLine>` is used to illustrate an owned collection. It does not automatically enforce that a `productId` appears only once; if that is a business invariant, the root must check or merge lines for the same product. If line ordering must be preserved, consider `List` and a corresponding position column mapping.

## 5. Create a Repository Only for PurchaseOrder

Create `src/main/java/com/example/orders/repository/PurchaseOrderRepository.java`:

~~~java
package com.example.orders.repository;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Spring Data JDBC automatically generates the bean implementing this repository. From `CrudRepository`, the application can use:

| Method | Meaning in this example |
|---|---|
| `save(order)` | Saves the `PurchaseOrder` state and its owned `OrderLine` items |
| `findById(id)` | Loads a `PurchaseOrder` by ID, with mapped components belonging to the aggregate |
| `findAll()` | Loads multiple roots; evaluate cost for large aggregates |
| `existsById(id)` | Checks whether an order exists |
| `count()` | Counts order roots |
| `deleteById(id)` | Deletes the aggregate according to repository behavior |

Having the repository target `PurchaseOrder` instead of `OrderLine` does not mean the database only uses the `purchase_orders` table. Spring Data JDBC relies on `@MappedCollection` to know there are child entities to handle through the `order_lines` table.

Keep a unified mental model:

~~~text
PurchaseOrderRepository
    save(PurchaseOrder)
        ├── writes root to purchase_orders
        └── writes OrderLine items to order_lines

    findById(orderId)
        ├── reads root from purchase_orders
        └── reads OrderLine items belonging to root from order_lines
~~~

The exact number of SQL statements depends on the mapping, Spring Data JDBC version, and operation. The diagram above merely expresses the save/load boundary, not a promise that each branch is always exactly one SQL statement.

### No Repository Implementation Class Needed

An interface extending `CrudRepository` is automatically processed by Spring Data via Spring Boot's repository configuration. In a typical package layout, the class with `@SpringBootApplication` lives in `com.example.orders` and sub-classes sit in `com.example.orders.domain`, `com.example.orders.repository`, and `com.example.orders.service`.

Make sure to import Spring Data annotations:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.relational.core.mapping.MappedCollection;
~~~

Do not replace them with `jakarta.persistence.Id`, `jakarta.persistence.Entity`, or `jakarta.persistence.OneToMany`; that is the JPA model, which differs from Spring Data JDBC.

## 6. Let the Application Service Orchestrate Operations Through the Root

The aggregate root holds business rules; the **application service** receives requests, loads the root, and asks the repository to save the new state. This is the right place to define use-case transaction boundaries.

Create `src/main/java/com/example/orders/service/OrderApplicationService.java`:

~~~java
package com.example.orders.service;

import java.math.BigDecimal;
import java.util.List;
import java.util.NoSuchElementException;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.repository.PurchaseOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    public record NewLine(
            Long productId,
            int quantity,
            BigDecimal unitPrice
    ) {}

    @Transactional
    public Long createDraft(Long customerId, List<NewLine> items) {
        if (items == null) {
            throw new IllegalArgumentException("Missing order line list");
        }

        PurchaseOrder order = PurchaseOrder.forCustomer(customerId);
        for (NewLine item : items) {
            order.addLine(item.productId(), item.quantity(), item.unitPrice());
        }

        PurchaseOrder saved = orders.save(order);
        return saved.getId();
    }

    @Transactional
    public void submit(Long orderId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() ->
                new NoSuchElementException("Order not found: " + orderId));

        order.submit();
        orders.save(order);
    }
}
~~~

Both methods depend on **only a single repository for the root**. Even though `submit` must inspect order lines, it inspects the collection already belonging to the aggregate after loading the root, rather than querying a separate `OrderLineRepository` and assembling results manually.

The `createDraft` operation accepts prices to simplify the example. In a real sales application, **do not trust unit prices supplied by clients**: prices must be fetched and verified from a trusted business source, then persisted as the finalized price of each line.

### Running a Short Example

Create `src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.List;

import com.example.orders.repository.PurchaseOrderRepository;
import com.example.orders.service.OrderApplicationService;
import com.example.orders.service.OrderApplicationService.NewLine;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            OrderApplicationService service,
            PurchaseOrderRepository repository) {
        return args -> {
            Long orderId = service.createDraft(
                101L,
                List.of(
                    new NewLine(501L, 2, new BigDecimal("120000.00")),
                    new NewLine(502L, 1, new BigDecimal("90000.00"))
                )
            );

            service.submit(orderId);
            var savedOrder = repository.findById(orderId).orElseThrow();

            System.out.println("Order ID: " + savedOrder.getId());
            System.out.println("Status: " + savedOrder.getStatus());
            System.out.println("Line count: " + savedOrder.getLines().size());
            System.out.println("Total: " + savedOrder.total());
        };
    }
}
~~~

With the Maven Wrapper on Windows, run:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

On macOS or Linux:

~~~bash
./mvnw spring-boot:run
~~~

Expected business output (ID may differ):

~~~text
Order ID: 1
Status: SUBMITTED
Line count: 2
Total: 330000.00
~~~

When `submit` runs, `order.submit()` decides whether the state transition is valid. The repository is only responsible for **persisting the domain-controlled aggregate**; it does not need to know each order status rule.

### Role of `@Transactional`

`@Transactional` on the service ensures reads, checks, and writes within the same use case participate in an appropriate transaction when invoked through a Spring proxy. If a method throws an unchecked exception, Spring rolls back the transaction by default.

However, a transaction **does not by itself prevent all concurrency conflicts**. Two requests can read the same `DRAFT` state and both attempt to update it. When parallel changes must be detected, add optimistic locking or a synchronization mechanism suited to business needs.

## 7. When Should Another Table Have Its Own Repository?

A good rule of thumb is: **each aggregate root needs a clear data access path; do not create a repository merely because a new table appears**.

For instance, `Customer` can have its name, address, or account status edited without depending on a specific order. In that case, it is a separate root:

~~~java
// Domain: mapped to the customers table (illustrative).
@Table("customers")
class Customer {
    @Id Long id;
    String name;
}

// Repository for an independent root.
interface CustomerRepository extends CrudRepository<Customer, Long> {
}
~~~

Imports for the two types above follow `org.springframework.data.annotation.Id`, `org.springframework.data.relational.core.mapping.Table`, and `org.springframework.data.repository.CrudRepository`. This snippet illustrates the idea of splitting aggregates; it is not meant to be added to run the H2 example above.

Between `PurchaseOrder` and `Customer`, store the ID:

~~~java
private Long customerId;
~~~

Spring Data Relational can also express this reference with `AggregateReference<Customer, Long>`. Whether choosing `Long` or `AggregateReference`, the architectural meaning remains: **the order only holds a reference and does not own the entire Customer**.

### Repository Decision Matrix

| Question | If the answer is "Yes" | Design implication |
|---|---|---|
| Can the object be created, modified, or deleted independently in business workflows? | E.g., `Customer`, `Product` | Consider a separate aggregate root and repository |
| Must the object always be modified through a parent object? | E.g., `OrderLine` | Place inside the parent's aggregate |
| Does the object have invariants checked by a parent? | Do not add lines after submitting an order | Expose methods on the root; avoid independent write repositories for children |
| Are aggregates only connected by ID? | `PurchaseOrder.customerId` | Each aggregate gets its own repository if access is needed |
| Does a screen need joined data from multiple tables? | Order list with totals | Create a read query/DAO/projection; no need to create a repository per table |
| Does an aggregate hold too many rows making updates expensive? | Thousands of delivery history records | Re-examine aggregate boundaries and read/write models |

When an entity that used to be a child begins having an independent lifecycle, splitting it into a root **can make sense**. Yet that is a change to the domain model, transactions, foreign keys, and state synchronization—not merely adding a repository.

## 8. Without a Repository Per Table, How Do You Read JOIN Data?

A common question: a screen needs a list of orders with total amounts, while an aggregate spans `purchase_orders` and `order_lines`. Must an `OrderLineRepository` be created just to query the child table?

**No.** Repository boundaries for domain operations do not force every read query to pass through the root's object graph. You can use **Spring JDBC** alongside Spring Data JDBC to build a **read model** with SQL tailored to the screen.

Example of a read-only DAO:

~~~java
package com.example.orders.read;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReadDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record OrderSummary(
            Long orderId,
            String status,
            long lineCount,
            BigDecimal totalAmount
    ) {}

    public List<OrderSummary> findSummaries() {
        String sql = """
            SELECT o.id AS order_id,
                   o.status AS status,
                   COUNT(l.id) AS line_count,
                   COALESCE(SUM(l.quantity * l.unit_price), 0)
                       AS total_amount
            FROM purchase_orders o
            LEFT JOIN order_lines l ON l.order_id = o.id
            GROUP BY o.id, o.status
            ORDER BY o.id
            """;

        return jdbc.query(sql, (rs, rowNum) ->
            new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("status"),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
            )
        );
    }
}
~~~

This DAO returns `OrderSummary`, not `PurchaseOrder` for the application to edit. Multi-table read SQL is convenient for aggregations and pagination, while business mutations continue going through `PurchaseOrderRepository`. This is a simple separation of **write model** and **read model**; it does not require implementing full CQRS or using two databases.

For large queries, pagination, an index on `order_lines.order_id`, and inspecting query plans are also needed. Repositories do not replace SQL tuning.

### Can `@Query` Be Used in Repositories?

Yes. Spring Data JDBC supports `@Query` for custom SQL as well as suitable derived queries. For a read query belonging to the aggregate itself, you can place the query on the root repository. When results are complex JOIN reports, returning DTOs/projections through a dedicated read DAO usually avoids mistaking it for an aggregate that can be saved back via `save`.

The main point is: **you do not need a CRUD repository for a child entity just to SELECT from the child table**.

## 9. How Spring Data JDBC Aggregate Persistence Shapes Design

### 9.1. No JPA Dirty-Checking Mechanism

With JPA, entities managed in a persistence context can have their changes tracked and flushed. Spring Data JDBC does not provide that mechanism.

~~~java
PurchaseOrder order = orders.findById(orderId).orElseThrow();
order.addLine(productId, 1, price);

// The object changed in memory, but DB persistence has not been requested yet.
orders.save(order);
~~~

After calling `save`, Spring Data JDBC processes the root along with mapped components belonging to the aggregate. If you forget `save`, modifying a Java object does not automatically write to the database just because the service has `@Transactional`.

### 9.2. Child Collections May Be Deleted and Re-Inserted on Update

For aggregates with child entities, Spring Data JDBC can delete child rows and re-insert them per the collection state when updating the root. This behavior simplifies consistency modeling, with consequences:

- Adding a single line to a large aggregate can produce more write statements than expected.
- Child entity IDs or external links relying on those IDs can run into issues if the model depends on preserving child row identities.
- Audits, triggers, and foreign keys referencing child entities must be considered.
- Choosing an overly large aggregate can affect performance and transaction contention.

If an order line must be referenced directly by other systems using a stable identity, or updated independently of the order, **revisit the aggregate boundary** rather than trying to treat the child entity as a root while keeping the old ownership mapping.

### 9.3. Distinguishing "Has an ID" From "Existing Data"

By default, Spring Data JDBC uses information such as `@Id` to identify whether an aggregate is new or existing. With a `Long id` key, `null` usually indicates a new object. After saving, use the value from:

~~~java
PurchaseOrder saved = orders.save(newOrder);
Long generatedId = saved.getId();
~~~

Do not assume assigning an arbitrary ID and calling `save` is guaranteed to work as an *upsert*. With a non-existent ID, the update operation may fail depending on the persistence mechanism and database constraints.

### 9.4. Adding Optimistic Locking to the Aggregate Root

If the business needs to detect two requests modifying the same order concurrently, `@Version` can be added to the root:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

And add the corresponding column to `purchase_orders`:

~~~sql
ALTER TABLE purchase_orders ADD COLUMN version BIGINT;
~~~

This is an **optional change** to the example: add the annotation only after the database has the matching column. Spring Data JDBC uses the version to detect stale updates and can throw `OptimisticLockingFailureException` on conflict. The application needs to decide whether to report a conflict error, reload data, or retry according to business rules; never retry indefinitely automatically.

## 10. Transactions Across Multiple Aggregates

Aggregate boundaries and transaction boundaries are related, though not identical.

Within one aggregate, changes need to be persisted consistently together. When a service performs operations across **two different aggregates** (such as creating an order and reserving stock), determine the desired consistency:

- If both live in the same database and must succeed/fail together, a JDBC transaction in the service can wrap both repositories. However, that increases lock scope and coupling.
- If inventory has an independent lifecycle, high traffic, or lives in another service/database, design an appropriate coordination mechanism: events, outbox, idempotency, reservations, or sagas when truly required.
- Do not make one aggregate the root of every object merely to use one large transaction.

With Spring JDBC and Spring Data JDBC, transactions are typically managed by Spring over the connection. Place `@Transactional` on services invoked through Spring proxies. Pay attention to self-invocation, rollback exceptions, and isolation levels under high contention.

An aggregate root protects invariants inside itself; correctness across multiple aggregates also requires appropriate coordination rules at the application/domain layer.

## 11. Signs of Poorly Designed Repositories

| Sign | Possible issue | Remedy |
|---|---|---|
| `XRepository` exists for every table, including detail tables | Ignores ownership boundaries and invariants | Identify the root; route detail changes through the root |
| Service calls `OrderLineRepository.save` directly after order submission | Status-checking logic becomes scattered | Invoke domain methods on `PurchaseOrder` |
| Loading all related tables into one huge aggregate | Expensive queries and updates; child collections get rewritten | Shrink aggregate; use read models and ID references |
| Mapping `Customer` as a child entity of `PurchaseOrder` | Accidentally treats independent data as owned | Store `customerId` or `AggregateReference` |
| Calling `save` without calling invariant-protecting methods | Root becomes an open DTO for arbitrary edits | Put invariants and behavior on the root; limit public setters |
| Using a repository to fetch multi-table JOIN reports and then editing/saving DTOs | Confuses read models with write aggregates | Read-only DAO/projections; business writes via root repository |
| Seeing `@Id` on a child entity and creating a new repository | Equates database identity with a root | Check lifecycle and boundaries before creating a repository |
| Expecting `@Transactional` to automatically sync modified objects | Confuses Spring Data JDBC with JPA dirty checking | Call `save` on the root after changes |
| Update conflicts cause lost changes | No concurrency strategy | Consider `@Version`, transaction isolation, and retry rules |

### When Does a Repository for a Child Entity Make Sense?

If, according to business rules, an object once considered a "child" actually has **an independent lifecycle and invariants**, it can become a new aggregate root. For example, a `Shipment` whose status is updated multiple times by a shipping system after an order is submitted may merit its own `ShipmentRepository`. In that case:

1. Redefine ownership and invariants of `Shipment`.
2. Remove the mapping that causes `Shipment` to be persisted as a child collection of `PurchaseOrder`.
3. Reference between aggregates via ID.
4. Define how events/states related to the order are synchronized.
5. Create `ShipmentRepository` for the new aggregate.

That is a design decision with a concrete business rationale, different from creating a repository for the `shipments` table merely because the table exists.

## 12. Practice Analyzing Another Domain

Suppose an online learning platform has the following tables:

~~~text
courses
lessons
students
enrollments
lesson_progress
payments
~~~

Do not immediately create six repositories. Examine:

**Course–Lesson:** if `Lesson` is authored and published through `Course`, `Course` can be the root and `Lesson` a child entity. If lessons have independent publishing, reuse, and permission lifecycles, consider a separate root.

**Student:** the student profile is an independent aggregate with its own identifier.

**Enrollment:** enrollment has its own status, timestamps, and business rules; it is usually worth considering as an aggregate root referencing `courseId` and `studentId`.

**LessonProgress:** if learning progress is updated at high frequency, consider a separate boundary suited to the workload rather than attaching every progress record to a giant `Course` or `Student` aggregate.

**Payment:** if there are refunds, reconciliation, and callbacks from payment providers, it very likely needs an independent lifecycle and its own repository.

There is no single answer based solely on table names. The outcome depends on business invariants, data volume, update frequency, and consistency requirements.

### Self-Implementation Exercises

1. Add a `removeLine(Long lineId)` method to `PurchaseOrder`, allowing deletion only when `status == DRAFT`.
2. Do not create `OrderLineRepository`. Every line-deletion operation must go through a service that loads the root, calls `removeLine`, and then calls `save` on the root.
3. Add a rule: an order can only be submitted when total amount is greater than 0; check this inside `submit`.
4. Observe the SQL when changing one order line and saving the aggregate; compare with changing only `status`.
5. Create a read-only DAO returning line count and total amount per order, without allowing the DAO to update `order_lines`.
6. Discuss what changes if `OrderLine` must be referenced by ID by a shipping partner and updated independently.

## 13. Closing Principle

In **Spring Data Relational JDBC**, repositories should be designed around **aggregate roots** because the root protects invariants and governs child entity lifecycles. A table is a storage structure; a repository is a data access boundary at the domain level. An aggregate may map across multiple tables, yet domain callers interact through the root.

In the order example, `PurchaseOrderRepository` manages `PurchaseOrder` and `OrderLine` mapped via `@MappedCollection`; `Customer` and `Product` exist independently and are referenced by ID. When JOINs or aggregations are needed, a dedicated read DAO can query multiple tables without spawning CRUD repositories for every table.

**The design question to ask before creating a repository is:** *"Which object is responsible for protecting business rules and is changed as one consistent unit?"* The answer leads to the aggregate root, and from the aggregate root follows the repository.
