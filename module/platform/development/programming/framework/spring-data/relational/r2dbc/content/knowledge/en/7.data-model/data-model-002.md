# The Aggregate Concept in Spring Data Relational and R2DBC Support Scope

## 1. Why Use an Aggregate Model When Working with Relational Data?

In a business application, an object rarely exists in isolation. An order can contain multiple order lines; a delivery slip has a shipping address; an account has settings or supplementary details. When persisting data, the application must determine which parts belong to the same business unit and which are merely referenced.

If every table is treated as an independent entity and joined arbitrarily, the business layer easily becomes coupled to the database structure. An update operation might accidentally modify multiple unrelated objects, or loading and saving an object might pull along an overly large data graph.

An **Aggregate** is a way of organizing the domain model into a cluster of objects with a clear boundary. This cluster has an **aggregate root** as its primary access point. Objects inside are managed through the root and belong to the same unit of business consistency.

Spring Data Relational uses an aggregate-centric approach when mapping relational data. Spring Data JDBC and Spring Data R2DBC share this relational mapping model. R2DBC adds reactive, non-blocking I/O execution; it does not turn the aggregate model into a full ORM like JPA/Hibernate.

## 2. Aggregates, Aggregate Roots, and Member Objects

### 2.1. What Is an Aggregate?

An aggregate is a group of entities and value objects treated as a single unit in the domain model. That group is designed around certain business rules that must be protected together.

For example, an order might include:

- The order itself with an order number, status, and creation timestamp.
- Order lines with product code, quantity, and unit price at the time of ordering.
- The shipping address captured at the time of ordering.

These objects are typically created, updated, or deleted as part of the order's lifecycle. The shipping address on the order is historical data of the order; it is not necessarily the same object as the current address in the customer's profile.

~~~text
Order aggregate
       |
       v
+-----------------------------+
| Order (Aggregate Root)      |
| id, status, createdAt       |
|                             |
|  +-----------------------+  |
|  | OrderLine             |  |
|  | sku, quantity, price  |  |
|  +-----------------------+  |
|                             |
|  +-----------------------+  |
|  | ShippingAddress       |  |
|  | street, city, zip     |  |
|  +-----------------------+  |
+-----------------------------+

Order ---- customerId ----> Customer aggregate
          (reference only)
~~~

The aggregate boundary is not simply a way to group tables with foreign keys. It reflects how the business wants to manage lifecycles, consistency, and authority to modify data.

### 2.2. What Is an Aggregate Root?

The aggregate root is the root entity of the aggregate. It has its own identity, typically marked with **@Id**, and serves as the entry point used by other layers to read or modify the aggregate.

In the order example:

- **Order** is the aggregate root.
- **OrderLine** is a member entity inside the Order aggregate.
- **ShippingAddress** can be a value object stored alongside Order.
- **Customer** is a separate aggregate; Order holds the customer identifier it references.

Business rules related to the order should be enforced through Order. For example, an arbitrary layer should not directly update the quantity of an OrderLine while bypassing order status checks, quantity limits, or total calculation rules.

### 2.3. Entities and Value Objects Inside an Aggregate

An entity has an identity used to distinguish the object over time. A value object is identified by the values of its properties and usually has no independent lifecycle.

For example:

| Component | Common Kind | Characteristics |
|---|---|---|
| Order | Aggregate root / entity | Has an ID and manages the order lifecycle |
| OrderLine | Member entity | Belongs to an Order; not an independent module entry point |
| ShippingAddress | Value object | Described by address fields; usually stored with Order |
| Customer | Another aggregate root | Has its own lifecycle and business rules |

An object can be an entity in the Java model yet still be just a member of an aggregate in the domain model. What determines this is the ownership boundary and business lifecycle, not just the class name or whether the table has a primary key.

## 3. Aggregate Boundaries and Business Consistency

Aggregates help pinpoint where invariants (rules that must always hold true) are protected. For example, a paid order must not arbitrarily receive new order lines; each line's quantity must be greater than 0; the total amount must be calculated from valid lines.

If these rules belong to the Order aggregate, modifying operations must go through the Order root. This establishes a clear boundary for validating data before persisting.

The following principles can guide boundary design:

- Place in the same aggregate those objects that must change together as a single business unit.
- Keep aggregates small enough so a single operation does not have to load and write too much data.
- Let the aggregate root control changes to internal members.
- Reference other aggregates by identifier when you do not need to own their lifecycle.
- Avoid creating bidirectional object graph relationships merely because tables have foreign keys.

For example, Order can store a customer ID to indicate which customer placed the order. Changing an email, locking an account, or updating a Customer profile is the responsibility of the Customer aggregate. Do not embed the entire Customer into Order and risk an order save accidentally overwriting customer data.

An aggregate is often considered a consistency boundary in domain-driven design. However, that does not mean a system can never use a database transaction spanning multiple aggregates. If a business action needs to update multiple aggregates in the same database and requires atomicity, the application layer can define an appropriate transaction. The aggregate boundary still defines ownership and how data is modified.

## 4. How Spring Data Relational Views Aggregates

Spring Data Relational provides mapping for Java objects to relational tables and columns. This model is used in both Spring Data JDBC and Spring Data R2DBC.

Some key annotations and APIs:

| Annotation / API | Role |
|---|---|
| **@Table** | Specifies the table corresponding to an entity or aggregate root |
| **@Id** | Marks the identifier of the aggregate root |
| **@Column** | Specifies the column name in the database |
| **@MappedCollection** | Maps a collection of aggregate member objects to a related table |
| **@Embedded** | Maps a value object into columns of the same data row |
| **@Version** | Supports optimistic locking using a version field |
| **AggregateReference** | Represents a reference to another aggregate by identifier |

Spring Data Relational uses mapping metadata to determine tables, columns, and relationships belonging to an aggregate. It does not require a JPA-style persistence context to track every object read throughout a session.

### 4.1. Aggregate Root with @Table and @Id

Example of a simple Order aggregate:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    public Order() {
    }

    public Order(String status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

**@Table("orders")** specifies the aggregate root's table. **@Id** identifies the ID field. Spring Data uses this metadata to generate read or write SQL according to its mapping strategy.

This example uses a class with getters/setters to clearly show how mapping works. Constructors, records, or immutable entities can be used if appropriate for the Spring Data version and application model.

### 4.2. Value Objects with @Embedded

A value object usually does not need its own table or ID if it only exists as part of an aggregate. Its fields can be mapped into the same row of the root table using **@Embedded**.

~~~java
import org.springframework.data.relational.core.mapping.Embedded;

public record ShippingAddress(
        String street,
        String city,
        String postalCode
) {}

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @Embedded(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}
~~~

With the **shipping_** prefix, the properties of ShippingAddress can be mapped to columns such as shipping_street, shipping_city, and shipping_postal_code. The final column names depend on the project's naming strategy and mapping annotations.

Value objects help group fields that always make sense together. For example, instead of keeping street, city, and postalCode scattered in Order, ShippingAddress can be used to represent the shipping address concept.

Not every nested object should use @Embedded. If the object has its own identity and lifecycle, consider whether it is a member entity of the aggregate or another referenced aggregate.

## 5. Mapping Member Entities with @MappedCollection

### 5.1. Collections Belonging to the Aggregate Root

An order can have multiple order lines. If the order lines belong to the order's lifecycle, they can be mapped as a collection using **@MappedCollection**.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
    }
}

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {}
~~~

**idColumn** specifies the column on the member table used to reference the aggregate root's ID. For List collections, **keyColumn** can be used to store the position or key of the element in the collection. Design the schema to match the collection type and project mapping strategy.

An illustrative schema:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

The order_lines table has a foreign key to orders. Each order line belongs to an order. In another model, a Set or a different key structure might be used instead of a List; ensure the mapping and schema remain consistent.

Table names of member objects and column names can be derived via the naming strategy or specified with annotations. The SQL example above shows the desired relational structure; during implementation, verify the exact names produced by the mapping strategy in your Spring Data version.

### 5.2. Lifecycle of Member Entities

OrderLine belongs to the Order aggregate. The business layer interacts with order lines through Order, for example:

~~~java
public void changeQuantity(int lineNumber, int newQuantity) {
    if (newQuantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }

    OrderLine current = lines.get(lineNumber);
    lines.set(lineNumber, new OrderLine(
            current.sku(),
            newQuantity,
            current.unitPrice()
    ));
}
~~~

This example only illustrates replacing an element in a collection; production code should handle line indexes or identifiers appropriate to the model. The quantity rule is placed where the aggregate is controlled so all modifications obey invariants.

Do not create an independent repository for OrderLine just to update it from anywhere if OrderLine has no independent lifecycle. If the business truly needs to access and manage order lines independently, revisit the aggregate boundary rather than adding a repository purely for convenience.

### 5.3. Saving an Aggregate

Repositories are typically declared for the aggregate root:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Flux<Order> findByStatus(String status);
}
~~~

The business layer retrieves Order from the repository, modifies the root or aggregate members, and then saves the root:

~~~java
public Mono<Order> addLine(Long orderId, OrderLine line) {
    return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                if (!"DRAFT".equals(order.getStatus())) {
                    return Mono.error(
                            new IllegalStateException("Order is not editable"));
                }

                order.addLine(line);
                return orderRepository.save(order);
            });
}
~~~

This is a condensed example; in a real application, business methods should be encapsulated within the aggregate and errors handled according to domain conventions. The core idea is that the repository works with the root, while member collections are managed as part of the aggregate.

Spring Data Relational may execute multiple SQL statements to save the root and its members. Do not assume a single save call always maps to exactly one SQL statement or that the framework automatically diffs individual objects like an ORM with dirty checking. Exact collection writes and SQL depend on mapping, version, and entity state; if performance matters, observe the generated SQL and measure with realistic data.

## 6. Referencing Other Aggregates

### 6.1. Do Not Embed Another Entire Aggregate into the Current Aggregate

Suppose Order needs to know which Customer placed the order. Customer has its own lifecycle and is managed by CustomerRepository. If Order embeds the entire Customer object as an owned member, the boundary between the two aggregates becomes blurred.

A suitable approach is to hold the customer ID:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;
}
~~~

In the schema, the customer_id column can be a foreign key to customers.id. Conceptually in the domain model, however, Order only holds a reference to Customer; it does not own Customer's lifecycle.

Spring Data Relational also provides the **AggregateReference** type to more explicitly express a reference to another aggregate root. Conceptual example:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;

    private String status;
}
~~~

When creating an Order, the reference can be assigned from a Customer ID using the factory method **AggregateReference.to(customerId)**. This reference type helps the model show that the property points to another aggregate via ID. It does not mean Spring Data will automatically load Customer when reading Order.

If using a Long customerId field directly, the reference meaning can still be expressed clearly in the field name and domain API. AggregateReference is useful when you want to express aggregate boundaries directly in the data type.

### 6.2. Reading Referenced Aggregates Explicitly

If the business logic needs customer information, query CustomerRepository separately and compose the publishers. The example below assumes Order uses an AggregateReference property with a corresponding getter:

~~~java
public Mono<OrderDetails> findOrderDetails(Long orderId) {
    return orderRepository.findById(orderId)
            .flatMap(order ->
                    customerRepository.findById(order.getCustomer().getId())
                            .map(customer ->
                                    new OrderDetails(order, customer)));
}
~~~

The example assumes Order has a getCustomer method and CustomerRepository returns Mono<Customer>. If Customer does not exist, clearly define whether the business logic should raise an error, return a result with missing info, or use a snapshot stored on the order. If the model uses a Long customerId field directly, pass order.getCustomerId() to findById instead of extracting the ID from AggregateReference.

Explicit reading lets developers see query costs and decide whether another aggregate needs to be loaded. It also prevents a read of Order from unexpectedly pulling in a huge object graph.

### 6.3. Do Not Equate Aggregate References with ORM Relationships

In JPA, a property can be annotated with @ManyToOne or @OneToMany and managed by a persistence context. With Spring Data Relational, do not default to JPA relationship annotations or expect similar lazy loading, cascading, and dirty checking.

Spring Data's relational model focuses on aggregate roots, mapped member entities, and ID references. When data from multiple aggregates needs to be combined, use appropriate queries or compose reactive operations at the application layer.

## 7. Repositories and Aggregate Operation Scope

### 7.1. Repositories Represent Aggregate Roots

A repository is typically created for each aggregate root that needs independent access:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

OrderRepository manages the Order aggregate; CustomerRepository manages the Customer aggregate. Having two repositories expresses two distinct lifecycle boundaries.

CRUD operations of ReactiveCrudRepository return reactive types such as Mono and Flux. Thus, the service layer can chain read, check, modify, and write steps in a single pipeline without blocking threads to retrieve results.

### 7.2. Derived Queries and Custom Queries

Derived queries can be created based on properties of the aggregate root:

~~~java
Flux<Order> findByStatus(String status);
~~~

When custom SQL is needed, **@Query** or **DatabaseClient** can be used. For instance, a query aggregating order counts per customer can be a dedicated SQL query instead of trying to construct a multi-level object graph.

~~~java
@Query("""
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
    """)
Flux<CustomerOrderCount> countOrdersByCustomer();
~~~

The CustomerOrderCount projection can be a record containing customerId and orderCount. The SQL statement must be adjusted to match the actual database, naming, and mapping.

Spring Data Relational does not forbid JOINs or multi-table queries. The distinction to keep in mind is that a SQL JOIN query does not merge aggregates into one aggregate or cause the framework to automatically manage the lifecycle of every object in the result.

### 7.3. When to Use DatabaseClient?

Repositories fit CRUD and queries typically tied to an aggregate root. **DatabaseClient** is useful when you need:

- Complex SQL or database-specific features.
- Reporting and aggregation queries across multiple tables.
- Projections that do not map directly to a single aggregate.
- Batch or specialized data operations requiring SQL control.
- Read-only queries without reconstructing full aggregates.

Using DatabaseClient does not sacrifice reactive benefits. Operations still return Publishers and can be composed in Reactor. However, when writing business data, keep domain rules and transaction boundaries clear; avoid letting arbitrary SQL break aggregate invariants.

## 8. Aggregate Support Scope in Spring Data R2DBC

### 8.1. What R2DBC Supports

Spring Data R2DBC uses the mapping model of Spring Data Relational. At a high level, you can:

- Map aggregate roots to tables via @Table and @Id.
- Map Java properties to columns using naming strategies or @Column.
- Map value objects into the same row using @Embedded.
- Map collections of member entities using @MappedCollection.
- Represent references to other aggregates using IDs or AggregateReference.
- Perform CRUD and queries via ReactiveCrudRepository.
- Use R2dbcEntityTemplate or DatabaseClient for more flexible operations.
- Compose read/write operations using Mono, Flux, and Reactor operators.
- Use a reactive transaction manager when transaction boundaries are needed.

Crucial point: R2DBC does not alter the aggregate-centric principles of Spring Data Relational. The primary difference lies in non-blocking database communication and reactive APIs.

### 8.2. What R2DBC Does Not Provide as a Full ORM

Spring Data R2DBC lacks the persistence-context features commonly found in JPA/Hibernate. Specifically:

- **No JPA-style lazy-loading proxies.** You cannot call a getter on an entity to automatically query an unloaded relationship.
- **No persistence-context dirty checking.** In-memory object mutations are not automatically detected and flushed when a transaction ends.
- **No JPA-style EntityManager or session cache.** Each repository operation is an explicit data operation managed through reactive APIs.
- **No arbitrary cascading graphs across aggregates.** Referencing another aggregate does not cause that aggregate to be automatically saved or deleted.
- **No automatic synchronization of bidirectional object relationships.** Relational models must be designed around relational mapping and the SQL schema.
- **Does not provide all JPA relationship annotations.** Annotations like @OneToMany, @ManyToOne, and @ManyToMany are not the relationship mapping mechanism of Spring Data Relational.
- **Does not automatically turn a multi-table query into an ORM lifecycle object graph.** You must deliberately use projections, JOINs, or composed repository queries.

R2DBC is a reactive database access API. The word reactive does not imply an automatic ORM or fully managed object graphs. You must explicitly design which data belongs to an aggregate, which is a reference, and when other data needs to be queried.

### 8.3. Reading an Aggregate Does Not Mean Lazy Loading

Under the aggregate model, member entities are treated as part of the root. Spring Data Relational can load mapped parts to reconstruct the aggregate upon repository operations. That happens through SQL queries and reactive publishers; it does not create lazy proxies that wait until a getter is called to query.

Therefore, watch aggregate size. A root with a very large collection can make reading the aggregate resource-intensive. If a screen only needs a few fields or a page of child data, consider projections, specialized queries, or pagination rather than loading the entire aggregate.

Exact loading behavior and SQL depend on mapping, driver, and Spring Data version. Confirm with integration tests and observe queries when models have complex relationships.

## 9. Transactions and Optimistic Locking

### 9.1. Multiple SQL Statements in One Aggregate Operation

Saving an aggregate may require writing the root and member entities across multiple tables. If an operation must ensure all changes succeed or roll back together, an appropriate reactive transaction is needed.

Example with a service:

~~~java
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Transactional
public Mono<Order> saveOrder(Order order) {
    return orderRepository.save(order);
}
~~~

In an R2DBC application, a transaction manager must be configured for the ConnectionFactory. For operations combining multiple repositories, place the transaction boundary around the overall publisher:

~~~java
@Transactional
public Mono<Void> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
            .flatMap(order -> {
                order.confirm();
                return orderRepository.save(order);
            })
            .then();
}
~~~

This is an illustrative example; domain and repository methods must exist in the actual application. The publisher must be returned for Spring to manage. Do not call subscribe() yourself inside a transactional method because that subscription might run outside the transaction Spring is coordinating.

If programmatic transaction management is needed, **TransactionalOperator** can be used to wrap a publisher. Transaction scope must be designed around business needs and tested against a real database or Testcontainers.

### 9.2. Optimistic Locking with @Version

When multiple requests can update the same aggregate concurrently, optimistic locking helps detect whether a record has changed since it was last read.

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

Spring Data uses the version field to check and update the version on write. If one process attempts to write with a stale version after another process has updated it, the operation can fail with an optimistic locking error instead of silently overwriting newer data.

The database needs a corresponding version column and the schema must match the mapping. The application should handle conflict errors according to business logic: reload the aggregate, recompute changes, or return a conflict error for the caller to handle.

Optimistic locking does not replace transactions. It resolves concurrent update conflicts by version; transactions ensure the atomicity of a group of database operations.

## 10. Designing Right-Sized Aggregates for R2DBC

### 10.1. Avoid Overly Large Aggregates

An aggregate with tens of thousands of child rows can make loading or saving the root heavy. When using Spring Data Relational, evaluate whether the entire child collection truly needs to be managed alongside the root.

For example, an Order with a few order lines fits well as a collection in an aggregate. A Customer with millions of login events should not load the entire event history as a collection belonging to Customer merely because of a foreign key.

Large datasets, data with independent lifecycles, or data with distinct query needs should be separated into another aggregate or accessed via dedicated queries.

### 10.2. Reference by ID Instead of Large Object Graphs

ID references let an aggregate keep necessary links without owning another aggregate's data. When details are needed, the service queries separately and composes publishers. This clarifies I/O costs and avoids loading data outside the business scope.

### 10.3. Separate Query Models When Read Needs Differ from Write Needs

Aggregate models are typically optimized for write rules and consistency boundaries. Reporting screens may require joining multiple tables or aggregated data that do not fit an aggregate. Do not force every read query to go through an aggregate root repository.

Projections, DatabaseClient, or a dedicated read model can be used for these queries. What matters is that write operations continue to obey domain rules and do not bypass aggregate root controls.

### 10.4. Many-to-Many Relationships

A many-to-many relationship between two aggregates typically requires a join table. Two aggregates should not treat each other as mutually owned collections.

For example, Student and Course can be two separate aggregates, while Enrollment is an associative model that can carry additional attributes like enrolledAt, grade, or status. If Enrollment has its own behavior and lifecycle, it can be modeled as an aggregate root. Querying a student's course list can use a JOIN or dedicated query.

Specific design choices depend on business needs. Spring Data R2DBC allows executing the necessary SQL, but does not provide JPA ORM-style management of many-to-many object graphs.

## 11. Comparing Aggregates in Spring Data Relational vs. JPA/Hibernate

| Criterion | Spring Data Relational / R2DBC | JPA / Hibernate |
|---|---|---|
| Model orientation | Aggregate-centric, root manages aggregate members | Entity graphs and ORM relationships |
| Repository | Repository typically represents an aggregate root | Repository can operate on entities within a persistence context |
| Member collection mapping | @MappedCollection | @OneToMany and relationship annotations |
| Referencing other aggregates | ID or AggregateReference | @ManyToOne, @OneToOne, and related mappings |
| Lazy loading | No JPA-style lazy proxies | Supported based on configuration |
| Dirty checking | No persistence context to automatically detect all changes | Present inside the persistence context |
| Cascade | Manages aggregate members per mapping; not arbitrary cascade graphs across aggregates | Provides ORM cascade options |
| I/O | Non-blocking R2DBC, reactive APIs | Typically blocking JDBC |
| Transaction | Reactive transaction manager and Reactor context | Imperative transactions typically via JDBC/JPA |

Neither technology should be declared universally superior. Spring Data R2DBC fits applications that require reactive relational database access and embrace explicit aggregate management. JPA/Hibernate fits applications needing rich ORM features and a familiar imperative model.

If an application relies on lazy loading, dirty checking, or complex entity graphs, assess whether R2DBC fits that model. You can adapt domain and query designs, but do not expect simply swapping JDBC for R2DBC to preserve all ORM behaviors.

## 12. Practical Implementation Considerations

### 12.1. Design the Schema to Match Aggregate Mapping

Ensure foreign keys, nullability, unique constraints, and column names align with mappings. For member collections, clearly define the root reference column and ordering or key column if required. Database constraints add an extra layer of protection for invariants.

### 12.2. Observe Generated SQL

When an aggregate has multiple collections or nested mappings, the number of SQL statements may exceed expectations. Monitor SQL logs in development, measure latency, and inspect query plans when needed. Do not enable logging of sensitive parameters in production.

### 12.3. Keep Reactive Transactions End-to-End

If multiple operations must be atomic, return the same publisher chain and set an appropriate transaction boundary. Avoid calling subscribe() or block() arbitrarily in the service layer, as they can detach the pipeline or block event-loop threads.

### 12.4. Test Against a Real Database

Use Testcontainers or a dedicated test database to verify mappings, foreign keys, collections, optimistic locking, transactions, and SQL dialects. Mock repositories cannot catch column name mismatches, data types, constraints, or driver behavior.

### 12.5. Do Not Use Mapping to Replace Domain Rules

Annotations only describe how data is persisted. They do not replace checks for order status, ownership, quantity limits, or business invariants. Those rules belong in the domain model or the service responsible for coordinating the aggregate.

## 13. Conclusion

An aggregate is a boundary for organizing data and business behavior. The aggregate root is the primary entry point, managing the lifecycle of member entities and protecting invariants. Other aggregates are referenced by ID to keep ownership and modification scope clear.

Spring Data Relational provides aggregate mapping through APIs such as @Table, @Id, @Embedded, @MappedCollection, and AggregateReference. Spring Data R2DBC applies that mapping model with reactive repositories and publishers, enabling non-blocking relational database access.

This scope of support suffices for many applications that want a clear aggregate model, though it is not a full ORM. R2DBC does not provide a persistence context, lazy-loading proxies, or JPA-style dirty checking. During design, keep aggregates appropriately sized, query other aggregates explicitly, manage reactive transactions carefully, and use specialized queries for multi-table reads or reporting.
