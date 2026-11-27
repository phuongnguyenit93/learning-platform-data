# Comparing Spring Data JPA with JDBC, Spring Data JDBC, and R2DBC

This document distinguishes four ways of working with relational databases in the Java/Spring ecosystem. The key point to remember is that **JDBC, Spring JDBC, Spring Data JDBC, Spring Data JPA, and R2DBC sit at different abstraction layers**. They may all solve the problem of reading and writing data, but they differ in object mapping, state management, SQL authoring, transactions, and I/O model.

## 1. Clarifying Terminology

- **JDBC (Java Database Connectivity)** is the standard Java API, primarily in `java.sql` and `javax.sql`. Applications work with `Connection`, `PreparedStatement`, `ResultSet`, and a JDBC driver. Typical JDBC calls are synchronous and blocking: the calling thread waits for the database operation to complete.
- **Spring JDBC** is Spring's support layer on top of JDBC, notably featuring `JdbcTemplate`, `NamedParameterJdbcTemplate`, `RowMapper`, and translation of JDBC errors into the `DataAccessException` hierarchy. It reduces boilerplate when managing resources and mapping results, but the application still explicitly writes SQL and decides how to map data.
- **Spring Data JDBC** provides the repository model and object mapping on top of JDBC. It enables aggregate-oriented CRUD operations without implementing JPA's full ORM model. I/O remains blocking JDBC.
- **Spring Data JPA** provides repositories on top of the Jakarta Persistence (JPA) standard. A JPA provider such as Hibernate performs ORM: mapping entities, managing the persistence context, tracking changes, and generating SQL. Spring Data JPA is not a JDBC driver; the provider typically uses JDBC underneath.
- **R2DBC (Reactive Relational Database Connectivity)** is a separate SPI for reactive, non-blocking relational database access. Spring Data R2DBC adds reactive mapping and repositories. R2DBC uses `ConnectionFactory` and R2DBC drivers, not `DataSource`/JDBC drivers in the way JDBC does.

Therefore, when saying "JDBC", you need to specify whether you mean the plain JDBC API or Spring JDBC. Both differ from Spring Data JDBC. Similarly, R2DBC is not an asynchronous mode of JDBC; it is a distinct SPI and driver ecosystem.

## 2. General Processing Flows

**Spring Data JPA**

`Service → JpaRepository → EntityManager → JPA provider (e.g., Hibernate) → JDBC → JDBC driver → Database`

Repositories reduce CRUD code; EntityManager and the provider manage entities, the persistence context, relationships, and synchronization of changes to the database.

**Spring JDBC**

`Service → JdbcTemplate / NamedParameterJdbcTemplate → DataSource → JDBC driver → Database`

The application writes SQL, supplies parameters, and defines how each result row is converted into an object.

**Spring Data JDBC**

`Service → CrudRepository → Spring Data JDBC mapping/template → DataSource → JDBC driver → Database`

Repositories provide aggregate-oriented data operations. Mapping is simpler than JPA and there is no persistence context tracking entities.

**Spring Data R2DBC**

`Service → ReactiveCrudRepository / R2dbcEntityTemplate → DatabaseClient → ConnectionFactory → R2DBC driver → Database`

Operations return reactive publishers such as `Mono` or `Flux`; the pipeline can orchestrate non-blocking I/O and propagate backpressure.

## 3. Quick Comparison Table

| Criterion | Plain JDBC / Spring JDBC | Spring Data JDBC | Spring Data JPA | Spring Data R2DBC |
|---|---|---|---|---|
| Access API | `java.sql`, `JdbcTemplate` | JDBC | JPA via provider, usually using JDBC underneath | R2DBC SPI |
| I/O model | Synchronous, blocking | Synchronous, blocking | Synchronous, blocking in typical usage | Reactive, non-blocking if driver supports it properly |
| How queries are written | Application-written SQL | SQL or appropriate query methods | JPQL, query methods, Criteria/Specification, native SQL | SQL or appropriate query methods |
| Mapping | Custom `RowMapper` or equivalent mapper | Simple entity mapping | Rich ORM | Simple relational mapping |
| Entity state management | None | No JPA-style persistence context/dirty checking | Persistence context, identity map, and dirty checking | No JPA-style persistence context |
| Object relationships | Manual JOIN and mapping | Aggregate-oriented; relationships must be designed explicitly | Supports rich entity relationships | Usually explicit relationship queries; no JPA-style lazy proxies |
| Lazy loading | Not built in | No | Available depending on mapping/provider | No JPA-style lazy loading |
| Transactions | Spring transaction manager for JDBC | JDBC transaction manager | JPA transaction manager | R2DBC transaction manager and reactive context |
| Repository | Self-organized or DAO pattern | Yes | Yes | Reactive repositories available |
| Best suited when | Direct SQL control is needed | Aggregate-oriented domain, clear CRUD | Domain with rich entities and relationships | End-to-end reactive applications with suitable drivers |

This table describes common usage in Spring. Specific capabilities also depend on the framework version, provider, driver, and database management system.

## 4. Differences in Mapping and State Management

### 4.1. Spring Data JPA: ORM and Persistence Context

JPA maps classes to entities and relationships between entities to tables. An entity managed by a persistence context has a stable identity within that context's scope. When the same row is loaded multiple times within the same persistence context, JPA typically returns the same managed instance.

When a managed entity is modified, the provider can detect changes via **dirty checking** and generate SQL statements at flush or commit time. As a result, within a transaction, you often do not need to call a separate update statement for each changed property.

JPA supports relationships such as `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany`, cascades, fetch strategies, inheritance mapping, and lifecycle callbacks. Relationships can be loaded eagerly or lazily depending on configuration and the defaults for each relationship type. Lazy loading must be used deliberately because accessing properties after the persistence context closes can cause errors or unexpected queries.

These powerful conveniences come with management overhead: entity states, flush timing, SQL count, persistence context size, and relationship loading strategies. JPA fits when the domain model genuinely benefits from those ORM capabilities.

### 4.2. Spring Data JDBC: Aggregate-Oriented Mapping

Spring Data JDBC does not try to replicate all of JPA's ORM. Its central model is the **aggregate** and **aggregate root**:

- The aggregate root is the entry point for accessing and saving the aggregate.
- Child objects belonging to the same aggregate are saved together with the aggregate boundary.
- References to other aggregates are typically represented by identifier references rather than an automatically loaded object graph.
- There is no JPA-style persistence context, dirty checking, or automatic lazy proxies. The application modifies objects and calls the repository to save.

This approach encourages defining clear domain consistency boundaries. An overly large aggregate causes each save to pull along too much data; therefore, you should not group every relationship into one aggregate just for mapping convenience.

Spring Data JDBC supports mapping with Spring Data Relational annotations such as `@Table`, `@Id`, and `@MappedCollection`. It can use repositories and query methods while also allowing explicit SQL when needed. It still uses JDBC, so having a repository does not make it reactive.

### 4.3. JDBC / Spring JDBC: SQL at the Center

With plain JDBC or Spring JDBC, the application decides the SQL statements, JOINs, query ordering, and how results become objects. `JdbcTemplate` safely manages opening/closing resources, exception handling, and parameter binding; `RowMapper` converts each `ResultSet` row into an object.

This approach provides very high control over SQL, making it suitable for reporting queries, multi-JOIN queries, stored procedures, bulk operations, or complex schemas. In return, the application takes responsibility for organizing mapping, pagination, relationships, and update operations.

Always pass input values through `PreparedStatement`/template parameters; never concatenate user input directly into SQL strings. This prevents SQL injection and lets the driver handle data types properly.

### 4.4. R2DBC: Simple Mapping in a Reactive Pipeline

Spring Data R2DBC can map rows to objects and provides repositories, but it does not have a persistence context or dirty checking like JPA. Reading related data usually needs to be done with explicit queries or by composing publishers in the service.

Reactive APIs allow an application to avoid holding a thread waiting on I/O while the database works, provided the driver and the entire path are non-blocking. A publisher executes only when subscribed to; data can flow as a stream and be regulated by backpressure.

R2DBC does not make an individual SQL query run faster. Its main benefit lies in efficient resource utilization under high concurrent I/O. If code calls `block()`, uses blocking JDBC, or invokes blocking libraries inside the pipeline, the non-blocking advantage can be lost.

## 5. Queries and Repositories

### Spring Data JPA

- Repositories can be declared with `JpaRepository<Entity, IdType>`.
- Method names can be used to derive queries, such as `findByEmail`.
- `@Query` defaults to JPQL, querying against entities and entity properties; native SQL can be used when needed.
- Projections, Specifications, the Criteria API, entity graphs, and fetch joins can be used to control what data is loaded.

### Spring Data JDBC

- Repositories usually extend `CrudRepository<AggregateRoot, IdType>`.
- Query methods can handle simple queries.
- `@Query` uses SQL, not JPQL.
- When querying across multiple tables or needing specialized projections, consider explicit SQL and appropriate result mapping.

### Spring JDBC

Using a repository framework is not required. DAOs can call `JdbcTemplate.query`, `queryForObject`, `update`, or `batchUpdate`. `NamedParameterJdbcTemplate` allows named parameters instead of positional `?` placeholders. The application controls SQL directly and defines the result structure.

### Spring Data R2DBC

- Reactive repositories usually extend `ReactiveCrudRepository<Entity, IdType>`.
- Methods return reactive types such as `Mono<T>`, `Flux<T>`, or corresponding publishers.
- `@Query` uses SQL; there is no JPQL or `EntityManager` like JPA.
- `R2dbcEntityTemplate` or `DatabaseClient` can be used when finer query control than repositories is needed.

## 6. Representative Code Examples

The snippets below illustrate declarations and queries in a Spring application. They are code fragments requiring an appropriate Spring Boot/Spring project, dependencies, database configuration, and corresponding imports; they are not standalone Java programs that can run using `javac` alone.

### 6.1. Spring Data JPA

Entity using Jakarta Persistence annotations:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

The repository can use query methods:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
    Optional<Customer> findByName(String name);
}
```

When `save` is called, Spring Data JPA chooses a persist or merge operation based on how it detects new entities. For a managed entity, property changes can be written to the database on flush/commit via dirty checking.

### 6.2. Spring JDBC

Using a record as the result type and mapping each row manually:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.Optional;

public record CustomerRow(Long id, String name) {}

@Repository
public class CustomerJdbcQueries {
    private final JdbcTemplate jdbc;

    public CustomerJdbcQueries(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerRow> findById(long id) {
        return jdbc.query(
            "select id, name from customer where id = ?",
            (rs, rowNum) -> new CustomerRow(
                rs.getLong("id"),
                rs.getString("name")
            ),
            id
        ).stream().findFirst();
    }
}
```

Both SQL and mapping are visible directly in the code. For complex queries, you can write JOINs and build dedicated DTOs rather than modeling every query result as an entity.

### 6.3. Spring Data JDBC

Uses Spring Data Relational annotations rather than JPA entity annotations:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(@Id Long id, String name) {}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Here `@Table` and `@Id` come from Spring Data Relational. There is no `@Entity`, `EntityManager`, or dirty checking. For aggregates with child objects, aggregate boundaries and collection mappings must be clearly designed.

### 6.4. Spring Data R2DBC

Relational entities can use similar Spring Data Relational annotations:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> findCustomer(Long id) {
        return repository.findById(id);
    }
}
```

The method returns `Mono<Customer>`; results are emitted in the reactive pipeline when subscribed to. In a reactive application, keep composing publishers rather than blocking the thread with `block()`.

## 7. Transactions and Consistency

**JDBC and Spring Data JDBC:** transactions are typically managed by a transaction manager tied to `DataSource`, such as `DataSourceTransactionManager` or `JdbcTransactionManager`. `@Transactional` on a service groups multiple JDBC statements into a single transaction.

**Spring Data JPA:** typically uses `JpaTransactionManager`. The transaction manages the persistence context; entity changes are synchronized at flush or commit. You need to understand propagation, isolation, flush, and rollback to avoid assuming every repository call is an independent transaction.

**Spring Data R2DBC:** uses `R2dbcTransactionManager` and a reactive transaction context. For reactive methods, the transaction is bound to the pipeline and Reactor Context; return `Mono`/`Flux` from transactional methods or use a reactive transaction operator. Do not rely on the simple ThreadLocal mental model used in imperative code.

Do not assume JDBC and R2DBC automatically participate in the same transaction just because they connect to the same database. They use different APIs, connections, and transaction managers. If a business flow mixes the two models, explicit transaction coordination and thorough rollback testing are required.

## 8. Performance and Common Issues

### JPA

- Significantly reduces mapping and CRUD code when the entity model fits.
- Can suffer from N+1 queries when loading a list of entities and accessing lazy relationships in a loop.
- Loading too many eager relationships or misusing fetch joins can bloat results.
- Large persistence contexts, dirty checking across many entities, and poorly timed flushes can increase overhead.
- Improve using projections, entity graphs, targeted fetch joins, proper pagination, batch fetching, and inspecting actual SQL.

### Spring JDBC

- Direct SQL makes queries predictable and easy to tune for the database.
- Fewer mapping layers than ORM, though it can create boilerplate if every DAO manages mapping manually.
- Null handling, data types, relationship mapping, pagination, and synchronized updates must be handled manually.
- Well suited for bulk updates, reporting queries, and cases needing database-specific features.

### Spring Data JDBC

- Simpler model, fewer implicit behaviors than JPA, and still provides repositories.
- Fits reasonably sized aggregates with clear consistency rules.
- No lazy loading to automatically traverse object graphs; the service must invoke appropriate repositories/queries.
- If aggregates become too large or cross-references complex, save operations and domain modeling can become heavy.

### Spring Data R2DBC

- Can serve many concurrent I/O operations with fewer waiting threads in a truly reactive application.
- Does not guarantee a single SQL statement executes faster than JDBC; CPU, indexes, locks, and query plans still determine much of the performance.
- Depends on the quality and feature set of the R2DBC driver for the chosen database.
- Avoid blocking calls on the event loop; monitor connection pools, backpressure, timeouts, retries, and asynchronous error handling.

No option is universally fastest. Measure on real workloads: query complexity, concurrent connections, data size, database latency, driver behavior, and transaction structure.

## 9. Choosing a Technology by Problem

| Need | Usually suitable choice | Reason |
|---|---|---|
| Domain with rich entities and relationships, needing dirty checking/cascade/lazy loading | Spring Data JPA | ORM manages object graphs and entity state |
| Aggregate-based CRUD, wanting simple mapping and fewer implicit behaviors | Spring Data JDBC | Built-in repositories, clear aggregate model, no persistence context needed |
| Complex SQL, reporting, bulk operations, or control over every query | Spring JDBC | SQL and mapping are controlled directly by the application |
| End-to-end reactive app, high concurrent I/O, database with a suitable R2DBC driver | Spring Data R2DBC | Non-blocking API and reactive publishers |
| Synchronous Spring MVC app, standard business logic, team familiar with JPA | Spring Data JPA or Spring JDBC | Choose based on domain complexity and needed SQL control |
| Project only needs simple CRUD without rich ORM | Spring Data JDBC | Less machinery than JPA while keeping repositories |

Some decision rules:

1. Start from the domain model. If you need to manage entity relationships, lifecycles, dirty checking, and object-graph queries, JPA has an advantage.
2. If the domain has clear aggregates and you want predictable SQL/mapping, consider Spring Data JDBC.
3. If queries are the primary focus—needing JOINs/bulk/reporting or specific SQL optimization—Spring JDBC is usually a better fit.
4. Only choose R2DBC when there is a real reactive requirement and driver support for the target database. Placing a reactive repository layer inside an otherwise blocking application rarely yields significant benefits.
5. Do not choose based on the line count of a CRUD example. Evaluate transactions, relationships, queries, operations, drivers, team skills, and testability.

## 10. Common Design Mistakes and Misconceptions

- **Treating Spring Data JDBC as a lighter JPA:** the two technologies have different persistence models. Spring Data JDBC aggregate designs should not blindly copy JPA object graphs.
- **Thinking Spring Data JPA does not use JDBC:** JPA providers typically use a JDBC driver at the database access layer; JPA adds the ORM and state-management layer.
- **Confusing R2DBC with asynchronous JDBC:** R2DBC has its own SPI and drivers; it does not directly use JDBC `DataSource` or JDBC drivers.
- **Assuming repositories automatically make queries optimal:** query methods are convenient, but you still need to check SQL, indexes, round-trips, and execution plans.
- **Ignoring N+1 in JPA:** inspect actual SQL and design fetch plans per use case.
- **Accessing lazy relations after the transaction/persistence context closes:** determine what data to return inside the service and use an appropriate projection/fetch plan.
- **Calling `block()` in a reactive pipeline:** this blocks the thread and can negate the benefits of R2DBC/WebFlux.
- **Putting blocking libraries on the event loop:** JDBC, blocking file I/O, or blocking HTTP clients must run on an appropriate execution model; do not let them block reactive threads.
- **Mixing JPA annotations with Spring Data Relational:** `jakarta.persistence.Entity`/`Id` are for JPA; Spring Data JDBC/R2DBC use Spring Data Relational mapping annotations and `org.springframework.data.annotation.Id`.
- **Packing too much data into one aggregate:** aggregates should stay small enough to maintain consistency rules and reasonable save operations.
- **Assuming the transaction manager automatically coordinates JDBC and R2DBC:** explicit configuration and design are required; sharing a database does not mean sharing a transaction context.

## 11. Pre-Decision Checklist

- [ ] Does the application use an imperative or reactive model from controller to database?
- [ ] Does the database have a suitable and verified JDBC/R2DBC driver for the required features?
- [ ] Does the domain need ORM, lazy loading, cascade, and dirty checking, or just simple mapping?
- [ ] Are aggregate boundaries and consistency rules clear?
- [ ] Do key queries require JPQL, explicit SQL, complex JOINs, or bulk updates?
- [ ] Have the transaction manager, propagation, isolation, and rollback behavior been defined?
- [ ] Is there a plan to inspect N+1 queries, connection pools, timeouts, indexes, and actual SQL?
- [ ] Can the team operate and debug the chosen persistence model?

## 12. Conclusion

- **Spring Data JPA** fits when you need rich ORM and entity state management.
- **Spring Data JDBC** fits when you want repositories over JDBC with a simple, explicit aggregate model.
- **Spring JDBC / plain JDBC** fits when SQL and query control are the priority.
- **Spring Data R2DBC** fits when you need reactive/non-blocking relational database access with supported drivers.

Choose based on the domain model, queries, transactions, and I/O architecture of the entire application. Do not switch to reactive just to be "faster," and do not adopt a full ORM if the application only needs explicit SQL operations.