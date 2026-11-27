# Learning Roadmap and Prerequisites

Spring Data Relational R2DBC enables Java applications to work with relational databases through reactive APIs, making it well-suited for systems that require asynchronous I/O and non-blocking data streams. To learn it effectively, you need to understand the relational data model, how Spring Data maps data, and how Reactor operates reactive flows. Simply memorizing annotation names or repository declarations is not enough: the hardest parts usually lie in understanding a reactive stream's lifecycle, transaction boundaries, and query organization.

The roadmap below progresses from fundamentals to building a production-ready application. You may skip sections you already master, but keep the dependency order across SQL, reactive programming, R2DBC, and Spring Data R2DBC.

## 1. Understanding R2DBC's Place in a Spring Application

R2DBC stands for *Reactive Relational Database Connectivity*. It is a specification for Java applications to access relational databases reactively. R2DBC drivers implement this specification for individual database management systems, such as PostgreSQL, Microsoft SQL Server, MySQL, or H2. Spring Data R2DBC provides a higher-level integration layer: object mapping, repositories, querying, and reactive transaction support.

You can visualize the layers in an application as follows:

```text
HTTP request / message / scheduled task
                 |
          Application service
                 |
        Spring Data R2DBC
        /               \
  Reactive Repository   DatabaseClient
        \               /
            R2DBC SPI
                 |
         Database driver
                 |
        Relational database
```

Each layer solves a different problem:

- **R2DBC SPI** defines the contract for connecting, creating statements, binding parameters, and receiving results asynchronously.
- **R2DBC driver** translates SPI operations into concrete communication with a specific database management system.
- **Spring Data Relational** provides the relational data mapping model and rules for working with aggregates.
- **Spring Data R2DBC** combines the Spring Data Relational model with R2DBC, delivering reactive repositories and lower-level query APIs.
- **Reactor** provides the reactive types and operators used by Spring Data R2DBC APIs, primarily `Mono` and `Flux`.

Traditional JDBC usually performs database calls by blocking the calling thread until results arrive. R2DBC provides an asynchronous, non-blocking API at the data access layer. This can help applications serve more concurrent I/O operations with better thread efficiency, provided the rest of the execution path is also designed appropriately. A `.block()` call or a blocking JDBC library can still stall the processing flow.

Spring Data R2DBC is not a reactive clone of JPA/Hibernate. It does not offer full ORM mechanisms such as a persistence context, dirty checking, lazy loading, or automatic object relationship management the way JPA typically does. Developers must proactively design SQL queries, aggregate boundaries, and how related data is loaded.

## 2. Prerequisites to Prepare

### 2.1. Java and Development Tools

Before learning R2DBC, you should be comfortable reading, writing, and debugging a typical Spring application in Java. Your JDK version must be compatible with your chosen Spring Boot version.

Java topics to know:

- Classes, interfaces, enums, records, generics, and annotations.
- Lambda expressions, method references, and functional interfaces.
- Collections, `Optional`, exceptions, and error handling.
- Constructor injection and package organization.
- Maven or Gradle, dependency management, and runtime configuration.
- Reading stack traces, setting breakpoints, and using logs to diagnose issues.

You do not need deep multithreading expertise upfront, though you should understand threads, blocking I/O, concurrency, and why a slow I/O operation can tie up processing resources.

### 2.2. Relational Databases and SQL

This is a mandatory foundation. R2DBC changes how an application sends statements to and receives results from the database; it does not replace knowledge of relational modeling or SQL.

You should be proficient in the following topics:

| Topic | Knowledge Needed | Why It Matters |
|---|---|---|
| Relational model | Tables, rows, columns, data types, primary keys, and foreign keys | Understand how data is stored and linked |
| Schema design | Basic normalization, `NOT NULL`, `UNIQUE`, and `CHECK` constraints | Protect data integrity directly at the database |
| CRUD | `INSERT`, `SELECT`, `UPDATE`, `DELETE` | Understand the operations repositories execute |
| Querying | `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING`, aggregate functions | Build queries matching business requirements |
| Joining tables | `JOIN`, one-to-one, one-to-many, and many-to-many relationships | Read and write data across multiple tables |
| Transactions | `COMMIT`, `ROLLBACK`, isolation levels, and locking | Ensure consistency across multiple data operations |
| Performance | Indexes, execution plans, pagination, and result limits | Avoid slow queries or loading excessive data |

Practice directly against the database management system you plan to use in your project. Know how to create schemas, insert sample data, run queries, and read SQL errors. If you cannot yet write a simple `JOIN` query or do not understand foreign keys, strengthen your SQL before diving deep into Spring Data R2DBC.

### 2.3. Spring Framework and Spring Boot

Spring Data R2DBC lives inside the Spring ecosystem. Learners should understand the foundational mechanisms before exploring database-specific configurations:

- IoC container, dependency injection, and basic bean lifecycles.
- Configuration annotations such as `@Configuration`, `@Bean`, `@Component`, and how component scanning works.
- Application configuration via `application.yml` or `application.properties`.
- Spring Boot auto-configuration and how classpath dependencies influence configuration.
- Constructor injection and layering across controllers, services, and repositories.
- Managing profiles, environment variables, and connection credentials.

If you have never built a Spring Boot application, build a small app with a controller, a service, and an external configuration first. Doing so helps distinguish Spring configuration issues from R2DBC connection issues when you begin working with the database.

### 2.4. Reactive Programming and Project Reactor

This is where you should invest the most time if you have previously worked only with JDBC or synchronous programming.

Spring Data R2DBC returns Reactor reactive types:

- `Mono<T>` represents a result that can emit zero or at most one value.
- `Flux<T>` represents a stream that can emit zero to many values.

Publishers are generally lazy: describing a pipeline does not mean the operation has run. A pipeline executes when subscribed to. Therefore, understand subscriptions, signals, completion, errors, and how operators compose together.

Reactor concepts to learn in order:

1. Creating and reading `Mono` / `Flux`.
2. Transforming data with `map` and `flatMap`.
3. Combining multiple publishers with `zip`, `concat`, or `merge` when appropriate.
4. Handling errors with `onErrorMap`, `onErrorResume`, and related operators.
5. Understanding `switchIfEmpty`, `defaultIfEmpty`, and publishers that complete without emitting a value.
6. Understanding subscription, cancellation, and backpressure well enough to predict data flow.
7. Distinguishing synchronous, asynchronous, and blocking operations.

For example, two query operations can be composed into a single pipeline:

```java
Mono<Customer> customerMono = customerRepository.findById(customerId);

Mono<CustomerProfile> profileMono = customerMono.flatMap(customer ->
    addressRepository.findPrimaryByCustomerId(customer.id())
        .map(address -> new CustomerProfile(customer, address))
);
```

`flatMap` is used because the inner function returns another publisher. Using `map` would produce a nested publisher, such as `Mono<Mono<CustomerProfile>>`, instead of a flat `Mono<CustomerProfile>`.

Two habits to build early:

- In services, prefer returning `Mono` or `Flux` so the caller decides how to compose and handle results.
- Never call `subscribe()` arbitrarily in controllers or services to fire off work and discard the stream. Doing so breaks error coordination, completion, and the request lifecycle of the pipeline.

Avoid `.block()` in the application's reactive processing path, especially on Spring WebFlux's event loop. `.block()` can be useful at certain imperative boundaries or in appropriate tests, but it should not become the way you connect steps in a service.

### 2.5. WebFlux and Reactive HTTP Handling

Spring WebFlux is frequently paired with Spring Data R2DBC to build a non-blocking path from HTTP to the database. Know how controllers return `Mono` or `Flux`, how HTTP errors are mapped, and how data streams are transmitted.

WebFlux is not mandatory for using Spring Data R2DBC. An application can use R2DBC in other components or alongside Spring MVC. However, if your goal is an end-to-end reactive application, understand WebFlux and keep blocking operations out of the same request path.

### 2.6. Operations and Testing Knowledge

Once CRUD works, add the operational knowledge needed to keep the application stable:

- Connection pools, connection limits, timeouts, and resource closing.
- Reactive transactions and transaction context propagation.
- Logging, metrics, and query failure observability.
- Testing publishers with `StepVerifier` from `reactor-test`.
- Integration testing against the exact database type and driver planned for deployment.
- Schema management and migrations aligned with the project's deployment workflow.

## 3. Stage-by-Stage Learning Roadmap

### Stage 1: Review SQL and Data Modeling

**Goal:** Independently design a small schema and write queries to serve business requirements.

Practice with a familiar domain, such as managing customers and orders. Create `customers`, `orders`, and `order_items` tables; declare primary keys, foreign keys, and necessary constraints. Write queries to fetch a customer's orders, order totals, and orders filtered by status.

Finish this stage when you can explain table relationships, write `JOIN`s, know when indexes are needed, and understand how transactions protect a group of write operations.

### Stage 2: Learn Reactor Before Using a Reactive Database

**Goal:** Read and compose publishers without relying on `block()`.

Build database-independent examples: transform a value into a `Mono`, process lists with `Flux`, call two simulated data sources and combine their results, and handle empty cases and errors. Use `StepVerifier` to observe the signals emitted by publishers.

Finish this stage when you can explain why `map` differs from `flatMap`, when a pipeline executes, and how errors propagate through a pipeline.

### Stage 3: Understand the R2DBC SPI and Drivers

**Goal:** Understand the underlying mechanism Spring Data uses to communicate with the database.

Learn the concepts of `ConnectionFactory`, `Connection`, `Statement`, `Result`, and parameter binding. You do not need to start by implementing a driver. Simply understand that the driver connects the R2DBC specification to the database's protocol, and each database may support features differently.

Pick a concrete database, add its R2DBC driver, and verify the application can connect. Use a database close to your real deployment environment to uncover differences in data types, SQL syntax, and driver behavior early.

### Stage 4: Build CRUD with Spring Data R2DBC

**Goal:** Map a table to an entity and operate on it via a reactive repository.

Learn the core building blocks:

- `@Table`, `@Id`, and `@Column` to map entities to tables and columns.
- `ReactiveCrudRepository` for basic CRUD operations.
- Derived query methods to generate queries from method names.
- `@Query` to declare SQL when query control is needed.
- `DatabaseClient` when SQL operations are needed below the repository level.

Minimal entity and repository example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    String email,
    @Column("display_name") String displayName
) {}
```

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByEmailContaining(String keyword);
}
```

Repositories return publishers; invoking a method does not necessarily execute the query right away. When combining repositories with services, keep passing publishers through the layers instead of blocking to unwrap objects.

### Stage 5: Queries, Aggregates, and Transactions

**Goal:** Handle workflows involving multiple tables or multiple write operations consistently.

Learn to write custom queries, bind parameters, map results, and handle relationships across tables. Spring Data Relational organizes writes around aggregates. Therefore, identify the aggregate root and the boundaries of data belonging to an aggregate instead of expecting an ORM to automatically load all relationships.

For multi-table queries, write explicit SQL or use `DatabaseClient`. For workflows requiring multiple writes to succeed or fail together, learn `R2dbcTransactionManager`, `@Transactional` on methods returning publishers, and `TransactionalOperator` when programmatic control is needed.

Reactive transactions are tied to the reactive context. Do not split a step out of a transaction by manually calling `subscribe()`, as that step may fall outside the transaction context. Test both success paths and mid-operation failures to confirm rollback behaves as expected.

### Stage 6: Integrating with WebFlux

**Goal:** Build a non-blocking processing flow from HTTP requests through services to the database.

Create endpoints to create a customer, find by ID, search by criteria, and delete a record. Controllers return publishers; services compose repository operations; business errors map to appropriate HTTP statuses. Test missing data, invalid input, and temporary database unavailability.

Next, add an endpoint returning multiple results and observe how `Flux` is written to the response. Only use streaming when response formats and business requirements fit; not every list endpoint needs incremental streaming.

### Stage 7: Testing and Operations

**Goal:** Catch bugs in reactive pipelines, SQL queries, and real connections.

- Unit test services using simulated publishers or appropriate mocks.
- Use `StepVerifier` to assert values, signal order, errors, and completion.
- Write integration tests against a real database or database container matching the target environment.
- Test transaction rollbacks, data constraints, and custom queries.
- Configure connection pools, timeouts, and load limits based on database capacity.
- Monitor query durations, active connections, and connection errors.

Test on the same database type and driver you will use in production. Passing tests on H2 are not enough to guarantee SQL syntax, data types, or transaction behavior on PostgreSQL or SQL Server.

## 4. End-to-End Practice Project

A small project connects topics far better than studying annotations in isolation. You can implement it across these milestones:

| Milestone | Feature | Concepts Practiced |
|---|---|---|
| 1 | Create a customer table and CRUD | SQL, entity mapping, `ReactiveCrudRepository` |
| 2 | Search by email and status | Derived queries, `@Query`, parameter binding |
| 3 | Create an order with line items | Aggregates, table relationships, transactions |
| 4 | API returning customer and order details | `Mono`, `Flux`, `flatMap`, WebFlux |
| 5 | Handle missing records and database errors | Empty publishers, error handling, HTTP mapping |
| 6 | Test the order creation flow | `StepVerifier`, integration tests, rollback |
| 7 | Optimize queries and connection limits | Indexes, execution plans, connection pools, timeouts |

Do not start with a system containing dozens of tables or microservices. A small schema keeps focus on how R2DBC works. Once you understand CRUD and transactions, gradually increase query and business complexity.

## 5. Minimal Learning Environment Setup

A basic practice environment includes:

1. A JDK compatible with your Spring Boot version.
2. Maven or Gradle and an IDE with Java support.
3. A relational database management system, running locally or in a container.
4. Spring Boot with the Spring Data R2DBC dependency.
5. The R2DBC driver matching your chosen database.
6. A database management tool to create schemas and inspect data.

Example PostgreSQL connection setup in `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/learning
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Typical dependencies are the Spring Data R2DBC starter and the database driver, such as `org.postgresql:r2dbc-postgresql` for PostgreSQL. If the application exposes reactive HTTP APIs, add Spring WebFlux. Let Spring Boot dependency management manage compatible versions instead of picking arbitrary versions per library.

R2DBC uses URLs with the `r2dbc:` scheme; JDBC URLs starting with `jdbc:` belong to JDBC drivers and cannot be substituted directly. Exact settings also depend on the database, credentials, SSL, and deployment environment. Never put real passwords in source code; use environment variables or a secret manager.

Creating and upgrading schemas should be governed by a clear migration workflow. In some projects, migrations run via a JDBC-based tool at deployment time while the application uses R2DBC for runtime data access. Both roles can coexist.

## 6. Common Mistakes When Getting Started

### Assuming R2DBC Automatically Makes the Whole App Non-Blocking

R2DBC provides a non-blocking database access API. If a service calls blocking libraries, reads files synchronously, or calls `.block()` on the event loop, the application still has blocking bottlenecks. Inspect the entire request path from input to database.

### Treating `Mono` or `Flux` as Ready-Made Data

A publisher describes a data emission process. It may not run until subscribed to, may complete without emitting a value, or may emit an error. Understand signals instead of treating a publisher like a `List` or a regular object.

### Expecting Entity Relationships to Behave Like JPA

Spring Data R2DBC does not provide lazy loading or a persistence context like JPA. When you need data from another table, design explicit queries or access steps. Under the aggregate model, identify which data belongs to the aggregate root and how it is persisted.

### Using `subscribe()` to Bypass Reactive Return Types

Calling `subscribe()` manually inside a service usually detaches the work from the active request or transaction. Return the publisher to the caller and compose steps using Reactor operators.

### Testing Only Against an In-Memory Simulated Database

Different databases vary in SQL syntax, data types, driver capabilities, and transaction behavior. Integration testing against the target database reveals mismatches that unit tests cannot catch.

### Ignoring Resource Limits

Non-blocking does not mean infinite resources. Connection pools still have limits; long-running queries, emitting excessive data, or holding transactions open too long can still slow the system down. Limit results, configure timeouts, and monitor real workloads.

## 7. Choosing a Learning Order Based on Experience

- **New to Java or Spring:** Learn Java, SQL, Spring Boot, and the controller–service–repository architecture first; then learn Reactor, and only then move to R2DBC.
- **Experienced with Spring MVC and JDBC or JPA:** Review SQL and transactions, focus on Reactor and the differences between Spring Data R2DBC and JPA, then migrate a small CRUD use case to R2DBC.
- **Already familiar with Reactor or WebFlux:** Review SQL, the aggregate model, and the R2DBC SPI; then learn mapping, repositories, custom queries, and reactive transactions.
- **Already using R2DBC but facing production issues:** Prioritize inspecting the driver, transaction context, connection pool, timeouts, SQL queries, and any blocking sections in the pipeline.

## 8. Readiness Checklist for Learning Spring Data R2DBC

Before moving on to advanced lessons, check whether you can:

- [ ] Write an SQL query with `JOIN`, filtering conditions, and sorting.
- [ ] Explain primary keys, foreign keys, indexes, and transactions.
- [ ] Create and configure a simple Spring Boot application.
- [ ] Explain `Mono`, `Flux`, `map`, and `flatMap`.
- [ ] Explain why `.block()` can cause issues in a reactive flow.
- [ ] Distinguish between an R2DBC driver, the R2DBC SPI, and Spring Data R2DBC.
- [ ] Connect an application to a database using an R2DBC URL and appropriate driver.
- [ ] Write a simple entity and reactive repository.
- [ ] Test publishers with `StepVerifier` and test queries against a database.

You do not need to master every item before starting. However, if you cannot yet write basic SQL or read a `Mono` / `Flux` pipeline, spend time solidifying those two foundations first. Once you have them down, Spring Data R2DBC annotations and APIs will be much clearer, and you will be better able to judge when a reactive model benefits your application.
