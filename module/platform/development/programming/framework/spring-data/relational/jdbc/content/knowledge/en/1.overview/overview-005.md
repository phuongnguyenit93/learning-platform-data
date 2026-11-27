# Comparing Plain JDBC, Spring JDBC, Spring Data JDBC, JPA, and R2DBC

When building a Java application that uses a relational database, five names—**plain JDBC**, **Spring JDBC**, **Spring Data JDBC**, **JPA**, and **R2DBC**—frequently come up in the same conversation. However, they solve problems at different layers: some provide database connectivity, some reduce query boilerplate, some manage data models, and some change how the application performs I/O.

Within the **Spring Data Relational** ecosystem, distinguishing clearly between these options is especially important. **Spring Data JDBC** targets a simple, predictable *aggregate* model with explicit SQL and data relationships. It is not a stripped-down version of JPA, nor is it synonymous with Spring JDBC or Spring Data R2DBC.

## 1. Distinguishing by Technology Layer

**JDBC (Java Database Connectivity)** is Java's standard API for working with relational databases synchronously. Applications use `Connection`, `PreparedStatement`, `ResultSet`, and a JDBC driver to send SQL and receive data.

**Spring JDBC** is a utility layer on top of JDBC, notably featuring `JdbcTemplate`, `NamedParameterJdbcTemplate`, and, in supported Spring Framework versions, `JdbcClient`. It manages resources, translates exceptions, and simplifies SQL execution. The developer remains responsible for writing queries and mapping most results.

**Spring Data JDBC** is a Spring Data module that uses JDBC/Spring JDBC infrastructure to map objects within an *aggregate* and automatically generate SQL for common save, read, and delete operations. It provides repositories and an object model, **without JPA-style persistence context, lazy loading, or dirty checking**.

**JPA (Jakarta Persistence)** is an ORM (Object–Relational Mapping) specification, not a specific driver or query library. Providers such as **Hibernate** manage entities, associations, object state, and corresponding SQL statements. In Spring applications, developers commonly encounter JPA through **Spring Data JPA** with `JpaRepository`.

**R2DBC (Reactive Relational Database Connectivity)** is a specification for accessing relational databases *reactively*, supporting non-blocking I/O at the application layer when the corresponding driver implements that model properly. You can use the R2DBC SPI directly, Spring R2DBC (`DatabaseClient`), or **Spring Data R2DBC** (`ReactiveCrudRepository`). R2DBC is a different connectivity branch from JDBC, not a higher ORM tier above JPA.

~~~mermaid
flowchart TD
    A["Java / Spring Application"] --> B["Plain JDBC"]
    A --> C["Spring JDBC"]
    A --> D["Spring Data JDBC"]
    A --> E["Spring Data JPA"]
    A --> F["Spring Data R2DBC"]
    D --> C
    E --> G["JPA provider (e.g., Hibernate)"]
    B --> H["JDBC driver"]
    C --> H
    G --> H
    F --> I["R2DBC driver"]
    H --> DB[("Relational database")]
    I --> DB
~~~

The diagram shows the common components in a Spring application. A JPA provider typically executes SQL over JDBC; Spring Data JDBC uses JDBC infrastructure; Spring Data R2DBC uses an R2DBC driver. An engine like PostgreSQL can be accessed via both JDBC and R2DBC, though the APIs and transaction management differ.

## 2. Quick Comparison Table

| Criterion | Plain JDBC | Spring JDBC | Spring Data JDBC | JPA / Spring Data JPA | R2DBC / Spring Data R2DBC |
|---|---|---|---|---|---|
| Layer | SQL connectivity API | Utilities over JDBC | Aggregate mapping and repositories | ORM per JPA specification | Reactive connectivity API; repositories with Spring Data |
| Execution model | Synchronous, blocks calling thread | Synchronous, blocks calling thread | Synchronous, blocks calling thread | Typically synchronous over JDBC | Reactive, non-blocking I/O when stack supports it |
| Who writes SQL? | Developer | Primarily developer | Framework generates CRUD SQL; custom SQL when needed | ORM generates SQL; supports JPQL, Criteria, native SQL | Framework generates CRUD; custom queries via SQL |
| Data mapping | Manual `ResultSet` reading | `RowMapper`, helper mappers | Entity/aggregate mapping | Entities, associations, persistence context | Simple entity mapping; relationships typically handled explicitly |
| Relationship management | SQL JOINs and Java code | SQL JOINs and mappers | Aggregate boundaries, child entities, ID references | `@OneToMany`, `@ManyToOne`, cascade, fetch | Multi-table links via explicit queries or pipelines |
| Object change tracking | No | No | Not JPA-style | Dirty checking on managed entities | Not JPA-style |
| Relationship lazy loading | Build manually if needed | Build manually if needed | No JPA-style lazy loading | Yes, depending on mapping and provider | No JPA-style lazy loading |
| Typical transactions | Manual `commit` / `rollback` | `@Transactional` with JDBC transaction manager | `@Transactional` with JDBC transaction manager | `@Transactional` with JPA transaction manager | Reactive transaction manager, Reactor context |
| SQL control | Very high | Very high | High with custom SQL; generated CRUD | Controllable, though requires understanding ORM-generated SQL | High with explicit SQL |
| Learning curve | SQL and resource management | SQL and Spring APIs | SQL, repositories, aggregates | ORM, entity lifecycle, fetch, cascade, sessions | Reactive Streams, Reactor, reactive drivers and transactions |

**Naming note:** when comparing "JPA" with "Spring Data JDBC," the corresponding choice in a Spring project is usually **Spring Data JPA + Hibernate**. Similarly, when mentioning "R2DBC" in a Spring application, distinguish **R2DBC SPI**, **Spring R2DBC**, and **Spring Data R2DBC**.

## 3. Same Problem: Reading a Customer by ID

Suppose a sales management system has the table:

~~~sql
CREATE TABLE customers (
    id   BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);
~~~

Auto-increment syntax can vary across database engines. In the example, the task is to find the customer with `id = 10`. The snippets focus only on the core APIs; imports and connection configuration are omitted for easier comparison.

### 3.1. Plain JDBC: Controlling Resource Lifecycle Manually

~~~java
record CustomerRow(Long id, String name) {}

Optional<CustomerRow> findById(DataSource dataSource, long id)
        throws SQLException {
    String sql = "SELECT id, name FROM customers WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, id); // Parameterized, do not concatenate ID into SQL

        try (ResultSet rs = statement.executeQuery()) {
            if (rs.next()) {
                return Optional.of(
                    new CustomerRow(rs.getLong("id"), rs.getString("name"))
                );
            }
            return Optional.empty();
        }
    }
}
~~~

Here, the author is responsible for preparing SQL, binding parameters, acquiring a connection, closing resources, reading each column, and handling `SQLException`. `try-with-resources` closes the connection, statement, and result set even when errors occur. Control is high, but repeating this pattern across dozens of repositories quickly makes the application cumbersome.

### 3.2. Spring JDBC: Still Writing SQL, Less Boilerplate

~~~java
record CustomerRow(Long id, String name) {}

@Repository
class CustomerJdbcDao {
    private final JdbcTemplate jdbcTemplate;

    CustomerJdbcDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    Optional<CustomerRow> findById(long id) {
        return jdbcTemplate.query(
            "SELECT id, name FROM customers WHERE id = ?",
            (rs, rowNum) ->
                new CustomerRow(rs.getLong("id"), rs.getString("name")),
            id
        ).stream().findFirst();
    }
}
~~~

`JdbcTemplate` borrows and returns connections in alignment with transaction management, manages statements/result sets, executes SQL, and translates many `SQLException` errors into Spring's `DataAccessException` hierarchy. The SQL remains explicit and mapping is still defined by the developer. For queries with many named parameters, `NamedParameterJdbcTemplate` is often easier to read than positional `?` placeholders.

### 3.3. Spring Data JDBC: Repositories and Aggregates

~~~java
@Table("customers")
record CustomerJdbc(@Id Long id, String name) {}

interface CustomerRepository extends CrudRepository<CustomerJdbc, Long> {
}

// Inside a Spring service:
Optional<CustomerJdbc> result = customerRepository.findById(10L);
CustomerJdbc created =
    customerRepository.save(new CustomerJdbc(null, "Lan"));
~~~

Spring Data JDBC maps data rows to `CustomerJdbc` and generates the SQL needed for common repository operations. `@Id` marks the primary key; `null` in this example indicates a new object using a database-generated ID. Because a record is immutable, use the value **returned from `save`** to obtain the object containing the updated ID.

The main benefit is not merely fewer lines of code: the repository operates on an **aggregate root** with clear child-entity ownership rules. When specialized queries are needed, you can still write `@Query` or use Spring JDBC alongside the repository.

### 3.4. JPA / Spring Data JPA: ORM-Managed Entities

~~~java
@Entity
@Table(name = "customers")
class CustomerJpa {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected CustomerJpa() {} // JPA requires a no-arg constructor

    CustomerJpa(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}

interface CustomerJpaRepository extends JpaRepository<CustomerJpa, Long> {
}

// Example inside a transactional service:
CustomerJpa customer = customerJpaRepository.findById(10L)
    .orElseThrow();
customer.setName("Lan updated");
// Managed entity can be written to DB via dirty checking on flush.
~~~

With JPA, an entity managed in a *persistence context* can have its changes tracked. At `flush` time, the provider determines the appropriate `UPDATE` statement; calling `save` after every setter on a managed entity is not strictly required. This is convenient for domain models with rich associations, yet requires understanding managed vs. detached entity states, flush timing, and fetch/cascade effects.

### 3.5. Spring Data R2DBC: Repositories Returning Publishers

~~~java
@Table("customers")
record CustomerReactive(@Id Long id, String name) {}

interface CustomerReactiveRepository
        extends ReactiveCrudRepository<CustomerReactive, Long> {
}

Mono<CustomerReactive> result =
    customerReactiveRepository.findById(10L);

Mono<CustomerReactive> created =
    customerReactiveRepository.save(new CustomerReactive(null, "Lan"));
~~~

`Mono<CustomerReactive>` represents an asynchronous result with 0 or 1 element; `Flux<CustomerReactive>` represents multiple elements. Constructing a publisher usually **does not execute the query yet**; the operation is triggered upon subscription. In a web application using Spring WebFlux, the framework generally handles subscription and streams results to the client.

Do not call `block()` to turn every `Mono` into a synchronous result, especially on WebFlux event-loop threads: doing so loses asynchronous benefits and can stall threads. When coordinating multiple queries, use operators such as `flatMap`, `map`, and `zip` according to data dependencies.

## 4. Core Differences: Data Model and Object Lifecycle

### 4.1. Plain JDBC and Spring JDBC: Query-Centric

With these two options, the developer decides exactly what data is retrieved and how results are shaped. A single SQL statement can join multiple tables and return a DTO tailored for a screen, report, or API:

~~~sql
SELECT o.id, o.created_at, c.name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = ?;
~~~

This model is particularly well suited for reports, complex read models, or applications where SQL is the primary interface to the database. On the flip side, updating an entire object structure such as an order with multiple lines must be orchestrated by the application.

### 4.2. Spring Data JDBC: Aggregate as the Consistency Boundary

Suppose an order contains multiple order lines and references a customer:

~~~text
Order (aggregate root)
├── id, customerId, status
├── OrderLine #1 (productId, quantity, unitPrice)
└── OrderLine #2 (productId, quantity, unitPrice)

Customer (another aggregate root)
└── id, name
~~~

In Spring Data JDBC:

- `Order` is the *aggregate root*, responsible for the business invariants of its `OrderLine` items.
- `OrderLine` is a child entity within `Order`'s lifecycle; ownership can be mapped with `@MappedCollection`.
- `Customer` is a separate aggregate. `Order` typically stores only `customerId` or uses `AggregateReference<Customer, Long>`, rather than embedding the full `Customer` entity in the ownership graph.
- Repositories are normally designed around the **aggregate root**, not around every child entity. Changes within the aggregate are persisted inside an appropriate transaction.

Conceptual model example:

~~~java
@Table("orders")
class Order {
    @Id Long id;
    Long customerId; // Reference to the Customer aggregate via ID

    @MappedCollection(idColumn = "order_id")
    Set<OrderLine> lines;
}

@Table("order_lines")
class OrderLine {
    Long productId;
    int quantity;
}
~~~

This example illustrates **ownership relationships**; the actual schema must also align with foreign key, primary key, and ID generation columns for each table. For child entities with their own ID, you may need an additional `@Id` declaration and matching persistence strategy.

Spring Data JDBC has no persistence context tracking individual object mutations. When calling `save(order)`, the framework executes SQL operations to save the aggregate state. **Depending on mapping and operations, updating child collections can involve deleting and re-inserting child rows**, rather than updating only the modified attributes like JPA's dirty checking. This makes aggregate boundaries, collection size, and write cost very important.

One positive consequence: retrieving an aggregate never silently triggers JPA lazy loading when reading attributes later. Queries crossing aggregate boundaries should be executed explicitly, such as via a dedicated repository or query for a view.

### 4.3. JPA: Object Graph, Associations, and Persistence Context

JPA lets you express associations such as `@OneToMany`, `@ManyToOne`, `@OneToOne`, and `@ManyToMany` with fetch, cascade, and entity management options. This is convenient when many business operations traverse object relationships.

In return, you must understand several mechanisms:

**Persistence context:** stores and manages loaded entities within a unit of work; for the same identifier, it typically maintains a single managed instance in the context.

**Dirty checking:** at flush time, the provider inspects managed entities for changes to decide write statements.

**Lazy loading:** can defer querying an association until it is accessed. Accessing it outside an active context can fail or fail to load data.

**N+1 queries:** when fetching N entities and then accessing each entity's association, the application can fire many more queries than expected. Choose fetch joins, entity graphs, projections, or batch fetching depending on the situation.

Therefore, stronger ORM capabilities do not automatically yield operationally simpler code. You must observe actual SQL and understand when reads and writes happen.

### 4.4. Spring Data R2DBC: Lightweight Mapping, Reactive Pipelines

Spring Data R2DBC maps SQL rows to objects and provides repositories, but does not offer JPA's full ORM machinery. Multi-table relationships are typically handled via separate queries, JOINs with suitable mappers, or combining publishers. Do not assume all aggregate/collection management annotations from Spring Data JDBC behave identically in R2DBC.

When designing reactively, the key question is not only "which rows to fetch?" but also "how are dependent reads/writes chained into a pipeline?" For example, use `flatMap` to execute a query after a prior query emits a result; creating two separate `Mono` values and ignoring the second publisher will never execute that step.

## 5. How Do Transactions Differ?

All of the technologies above can participate in database transactions, but how contexts and connections are managed varies.

| Option | Common transaction management | Key things to remember |
|---|---|---|
| Plain JDBC | `Connection#setAutoCommit(false)`, `commit()`, `rollback()` | All statements need the same connection; must handle errors/closing connections |
| Spring JDBC | `@Transactional` + `JdbcTransactionManager` or `DataSourceTransactionManager` | JDBC operations join the thread-bound transaction via Spring's mechanism |
| Spring Data JDBC | Same as Spring JDBC | Aggregate `save`/`delete` calls need business-aligned transaction boundaries |
| JPA | `@Transactional` + `JpaTransactionManager` | Persistence context, flush, and transactions are closely tied yet distinct |
| Spring Data R2DBC | `R2dbcTransactionManager`, `@Transactional` with reactive publishers, or `TransactionalOperator` | Transaction propagates via the reactive context, not via `ThreadLocal` like traditional JDBC |

Example of an operation that updates an order and deducts inventory using Spring JDBC:

~~~java
@Service
class CheckoutService {
    private final JdbcTemplate jdbc;

    CheckoutService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void checkout(long orderId, long productId, int quantity) {
        int updated = jdbc.update(
            """
            UPDATE inventory
            SET stock = stock - ?
            WHERE product_id = ? AND stock >= ?
            """,
            quantity, productId, quantity
        );
        if (updated != 1) {
            throw new IllegalStateException("Insufficient stock");
        }
        jdbc.update(
            "UPDATE orders SET status = ? WHERE id = ?",
            "CONFIRMED", orderId
        );
    }
}
~~~

If both statements share the same Spring-managed transaction, throwing a runtime exception will by default trigger a transaction rollback. The example assumes tables and constraints are already prepared; in a real system, also check updated row counts, idempotency, and concurrency rules.

With R2DBC, the same idea can be expressed using `TransactionalOperator`:

~~~java
Mono<Void> checkout =
    updateInventory(productId, quantity)
        .then(confirmOrder(orderId))
        .as(transactionalOperator::transactional);
~~~

Here `updateInventory` and `confirmOrder` are assumed to return reactive publishers and emit an error if the business rule fails. The transaction boundary wraps the **subscribed reactive chain**. JDBC and R2DBC APIs do not automatically share the same local transaction just because both are annotated with `@Transactional`; mixing them requires dedicated design.

## 6. SQL, Performance, and Predictability

No single technology is always fastest. Performance depends on database round-trips, indexes, queries, transactions, connection pools, aggregate/object-graph size, and concurrency levels.

### SQL Control

- **Plain JDBC / Spring JDBC:** developer-written SQL is the primary source of behavior. Ideal when you need JOINs, CTEs, window functions, analytical reports, or engine-specific tuned statements.
- **Spring Data JDBC:** routine CRUD is generated from mapping; custom SQL can be added. Usually easier to predict than an ORM object graph with lazy associations, though you must still watch SQL counts when loading and saving large aggregates.
- **JPA:** ORM can save considerable effort on association-rich domain models, while also emitting non-obvious SQL due to flush, cascade, fetch, and N+1 issues. Projections, JPQL, native SQL, and SQL logs help retain control.
- **R2DBC:** supports SQL queries and reactive pipelines, but does not magically make inefficient queries fast. Driver, database, and pipeline design determine actual throughput.

### Blocking vs. Non-Blocking

JDBC, Spring JDBC, Spring Data JDBC, and most common JPA implementations are **blocking at the database call site**. While waiting for the database response, the thread executing the operation is typically held. Connection pools like HikariCP enable connection reuse, but do not turn JDBC calls into non-blocking I/O.

R2DBC allows the application to express waiting on I/O via publishers and continue serving other work on a limited number of threads. This can help under high concurrent request loads or in applications already using Spring WebFlux end-to-end. Even so:

1. The database still has limits on CPU, locks, connections, and throughput.
2. Drivers and pipeline stages must genuinely support non-blocking execution; putting JDBC or long blocking work on an event loop breaks that assumption.
3. Reactive programming adds complexity around data flows, context, error handling, backpressure, and debugging.

For a traditional MVC application with moderate request volume, Spring JDBC or Spring Data JDBC is often a completely sound choice. Rewriting an entire system to reactive solely to speed up a simple query rarely fixes root causes such as missing indexes or N+1 queries.

## 7. When to Choose Which Technology?

| Context | Usually suitable choice | Why |
|---|---|---|
| Small utility, needing direct JDBC understanding or driver control | Plain JDBC | Full visibility into connections, statements, result sets, and transactions |
| Custom SQL APIs, reporting, complex JOINs | Spring JDBC | SQL-centric, less resource-management boilerplate |
| Aggregate-oriented business services, moderate model, avoiding ORM complexity | Spring Data JDBC | Concise repositories, clear ownership rules, no JPA lazy loading |
| Domain with many object relationships, needing cascade/fetch and tracked entity changes | JPA / Spring Data JPA | Rich ORM tooling, persistence context, and relationship mapping |
| End-to-end reactive application, suitable R2DBC driver, high concurrent I/O | Spring Data R2DBC / Spring R2DBC | Reactive database connectivity and query processing |
| Same system has reporting queries and aggregate writes | Combine Spring Data JDBC with Spring JDBC | Repositories manage aggregates, dedicated SQL serves read screens |

This is a decision starting point, not a rigid rule. A JPA application can still use native SQL for reporting. A Spring Data JDBC service can use `JdbcTemplate` for queries that do not fit a repository. You can also use JPA in a simple domain, provided the team understands and controls its ORM behavior.

### Three Illustrative Scenarios

**Scenario A – Order Management:** `Order` controls status and `OrderLine` items, while `Customer` and `Product` have independent lifecycles. Spring Data JDBC is a strong candidate if aggregates remain compact and child updates are not too expensive. Revenue statistics pages can use Spring JDBC with dedicated SQL.

**Scenario B – Student Records System:** many interconnected entities and workflows navigating across the object graph, requiring cascading or traversing associations per use case. JPA can be more convenient, provided fetch plans and transactions are designed carefully to avoid N+1 queries.

**Scenario C – Reactive Gateway/API:** the system already runs on WebFlux, calls multiple non-blocking I/O sources, and the database has a reliable R2DBC driver. Spring Data R2DBC preserves the reactive pipeline end-to-end. If business logic demands rich JPA ORM features, weigh the trade-offs rather than assuming JPA maps directly onto R2DBC.

## 8. Common Misconceptions

**"Spring Data JDBC = Spring JDBC plus a few repositories?"** Incomplete. Spring Data JDBC introduces the aggregate root concept, mapping, and whole-aggregate persistence. Spring JDBC focuses on executing SQL; the two complement each other at different abstraction levels.

**"Spring Data JDBC is like Spring Data JPA, just lighter?"** No. JPA uses a persistence context, managed entities, dirty checking, and association mapping; Spring Data JDBC treats an aggregate as the unit of persistence rather than managing an ORM object graph. Switching between them can require redesigning the model.

**"Spring Data JDBC doesn't support JOINs?"** You can use SQL JOINs in custom queries, especially returning DTOs/read models. What you should not assume is that a repository turns every JOIN relationship into an entity graph with JPA-style lazy loading and cascading.

**"Using a repository means you don't need to know SQL?"** False for Spring Data JDBC, JPA, and R2DBC alike. Indexes, transactions, locks, isolation levels, and actual SQL still determine correctness and performance.

**"JPA always means Hibernate?"** Hibernate is a very common provider in Spring Boot, but JPA is a specification and other providers exist. `JpaRepository` is a Spring Data JPA API, not part of the Jakarta Persistence specification itself.

**"R2DBC is always faster than JDBC?"** No. R2DBC addresses I/O programming models and resource utilization under concurrency, without guaranteeing lower latency per SQL query. If the database is the bottleneck, swapping the connectivity API may not increase throughput.

**"Using WebFlux forces you to use R2DBC?"** Not strictly, though calling blocking JDBC directly on an event loop is problematic. Blocking work can be isolated onto an appropriate scheduler in some systems, yet that does not make JDBC reactive and comes with its own limits. When an end-to-end non-blocking database stack is needed, R2DBC is a better fit.

## 9. Suggested Learning Path in Spring Data Relational

To build a durable understanding of Spring Data JDBC, learn concepts in order:

1. **SQL and JDBC basics:** understand connections, parameter binding, transactions, indexes, JOINs, and primary/foreign keys.
2. **Spring JDBC:** run queries/updates with `JdbcTemplate`; distinguish SQL, mappers, and transaction boundaries.
3. **Spring Data JDBC:** design aggregate roots, child entities, `@Table`, `@Id`, `@MappedCollection`, `@Version`, repositories, and custom queries; inspect SQL during `save`.
4. **Compare with JPA:** try the same `Order–OrderLine` relationship to see the difference between aggregate persistence and a persistence context; analyze fetch, dirty checking, and cascade.
5. **Approach R2DBC when reactive needs arise:** understand `Mono`, `Flux`, subscription, transaction context, and the impact of blocking code in a pipeline.

Specifically for **Spring Data Relational JDBC**, the crucial design question is usually: *"Which data must change consistently together inside one aggregate, and which data should be referenced by ID or read via separate queries?"* Answering that question helps define repository boundaries and prevents pulling a huge entity web into a single `save` call.

## 10. Conclusion

Plain JDBC gives direct control over SQL and resources; Spring JDBC retains a SQL-first approach with less boilerplate; Spring Data JDBC adds repositories and an explicit aggregate model; JPA adds ORM power and rich entity lifecycle machinery; and R2DBC shifts connectivity and execution to a reactive model. Choosing a technology based on **business model, SQL requirements, transactions, application style, and real workload** is far more valuable than choosing by annotation count or assuming newer technology is always better.
