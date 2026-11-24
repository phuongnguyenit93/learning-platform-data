# Choosing Explicit SQL, ORM, or Reactive Access by Problem Domain

## 1. Goals and Questions to Answer

In Spring Framework, the same relational database can be accessed via **explicit SQL with JDBC**, **ORM with JPA/Hibernate**, or **non-blocking SQL/data access with R2DBC**. None of these is universally faster, simpler, or more correct in every scenario. The decision must rest on query patterns, domain model, real workload, application interface, transactions, and operational capability.

After this lesson, you should be able to explain and decide:
- When you need direct control over SQL, JOINs, projections, batching, and execution plans.
- When object–relational mapping, dirty checking, and JPA's aggregate model reduce boilerplate.
- When non-blocking access with R2DBC helps, and what is required for a pipeline to be genuinely reactive end-to-end.
- The difference between imperative transactions and transactions bound to a Reactor context.
- How to validate your choice with measurements and tests rather than assuming "ORM is slow" or "reactive is fast."

Context: a Spring Boot/Spring Framework application using PostgreSQL; examples use Java 17+ and APIs common in Spring Framework 6.1+/Spring Boot 3.2+. Snippets annotated with filenames represent code **inside a Spring Boot project with configured dependencies**, not standalone Java programs compiled with plain `javac`.

## 2. Distinguishing the Three Concepts Before Choosing

### Explicit SQL/JDBC

**JDBC** is Java's blocking relational database access API. In Spring, common tools are:
- `JdbcTemplate` and `NamedParameterJdbcTemplate`: execute queries and updates, map `ResultSet`s, and translate JDBC errors to Spring's exception hierarchy.
- `JdbcClient` (Spring Framework 6.1+): a unified fluent interface for many query/update tasks; still runs on JDBC and remains blocking.
- SQL builder tools such as jOOQ, when strong type-safe SQL is desired, serve as complementary options; they do not make JDBC reactive.

"Explicit SQL" means the application owns the query text and decides which columns and rows to fetch. It does **not** mean manual SQL string concatenation: input values must always be bound as parameters.

### ORM/JPA

**ORM** maps objects and object relationships to database tables and rows. In the Spring ecosystem:
- **JPA/Jakarta Persistence** is the specification.
- **Hibernate** is a commonly used JPA provider.
- **Spring Data JPA** builds repositories and query utilities on top of JPA; it is not a completely separate ORM.
- `EntityManager`/the persistence context manages entity state; entity changes synchronize with the database on flush (typically at commit).

JPA still generates and executes SQL over JDBC. Using repositories does not remove the need to understand SQL, indexes, transactions, lazy loading, and the queries being emitted.

**Spring Data JDBC** is an alternative to JPA: simple aggregate mapping over JDBC, with no JPA-like persistence context, lazy loading, or dirty checking. Do not lump Spring Data JDBC and JPA into the same ORM model.

### R2DBC/Reactive Access

**R2DBC** is an SPI/driver for accessing relational databases with asynchronous operations that do not block threads while waiting on I/O when supported by the driver. Spring provides:
- `DatabaseClient` for writing reactive SQL directly.
- `R2dbcEntityTemplate` for entity-based mapping/queries.
- Spring Data R2DBC repositories with `Mono<T>` and `Flux<T>`.

Reactive is **not** "JPA returning `Mono`" or "calling `JdbcTemplate` inside `Mono.fromCallable`." JDBC/JPA remain blocking even when wrapped in reactive types. Spring Data R2DBC supports object mapping, yet lacks a Hibernate-ORM-style persistence context and lazy-loading relationship graph.

## 3. Execution Mechanics and Resources

```text
Explicit SQL (blocking)
HTTP/Service → JdbcClient/JdbcTemplate → JDBC driver
             → JDBC connection → database → RowMapper/DTO

JPA ORM (blocking)
HTTP/Service → Repository/EntityManager → Hibernate
             → generated SQL → JDBC connection → database
             → managed entity/persistence context

R2DBC (non-blocking I/O)
Reactive handler/service → Mono/Flux → DatabaseClient/R2dbcEntityTemplate
                         → R2DBC driver/connection → database
                         → publisher emits rows on demand
```

- **JDBC/JPA:** an operation waiting on I/O typically occupies the calling thread until completion; the connection pool limits concurrent queries. With Java 21 virtual threads, the cost of parking a *platform thread* drops, yet JDBC remains a blocking API and the pool/database still bound capacity.
- **JPA:** beyond SQL cost, there is entity materialization, persistence context tracking, dirty checking, cascading, and relationship loading. These features add value when domain logic needs them, but waste resources when you only need three columns for a report.
- **R2DBC:** can keep many I/O-waiting tasks in flight with fewer threads, yet **it does not make the database execute queries any faster**. Connection counts, transaction limits, locks, indexes, and query latency still matter. `Flux` does not automatically imply unbounded server streaming or full-stack backpressure.

## 4. Comparison for Decision Making

| Criterion | Explicit SQL via JDBC | ORM/JPA (Hibernate) | R2DBC / Spring Data R2DBC |
|---|---|---|---|
| Programming style | SQL + application-controlled mapper/DTO | Entities, relationships, repositories, JPQL/Criteria/native queries | SQL or template/repository returning `Mono`/`Flux` |
| Database I/O | Blocking | Blocking, typically via JDBC | Non-blocking when using a true R2DBC driver |
| SQL control | High, ideal for JOINs/projections/CTEs/vendor features | Present, but requires understanding generated SQL; native SQL possible | High with `DatabaseClient`; depends on driver/dialect support |
| Richly related domain models | Must handle mapping/state updates manually | Strong with identity map, dirty checking, cascading, associations | Simpler mapping; more explicit aggregate/relationship management |
| Transactions | `PlatformTransactionManager`, typically `JdbcTransactionManager`/`DataSourceTransactionManager` | `JpaTransactionManager` and persistence context | `ReactiveTransactionManager`/`R2dbcTransactionManager`, Reactor context |
| Overhead to manage | SQL/mapping and connection lifecycle | N+1, fetch strategies, flushing, persistence context | Reactive composition, subscriptions, context, driver/pool |
| Best suited for | Reporting, tuned SQL, batching, legacy SQL | Domain-driven CRUD and entity lifecycles | Reactive pipelines with high concurrent I/O and compatible drivers |

This table describes tendencies, not speed guarantees. A well-designed JPA query can outperform poorly written manual SQL; an R2DBC query can be slower than JDBC at low load due to coordination overhead.

## 5. Selection Process in Real Projects

Evaluate step by step:

1. **What is the primary read/write workload?** If the focus is multi-table queries, reporting, SQL aggregations, wide projections, and explicit control of indexes/hints/CTEs, favor **explicit SQL**. If the focus is mutating stateful entities tied to business rules and relationships, consider **JPA**.
2. **Is the existing call chain blocking?** Spring MVC apps, blocking HTTP clients, blocking auth libraries, and JDBC databases usually benefit from a simple imperative stack. If you use WebFlux/Reactor with non-blocking I/O across the whole pipeline, **R2DBC** is a strong candidate to evaluate.
3. **Do the driver and database support all required features?** Verify the R2DBC driver for your specific DBMS, pooling, data types, transactions, isolation, batching, timeouts, cancellation, and observability. If critical support is missing, do not force reactive.
4. **What do transactions span?** A JPA/JDBC transaction on a `DataSource` and an R2DBC transaction on a `ConnectionFactory` do not automatically merge into a single ACID transaction. If consistency is needed across both, design clear boundaries or use an appropriate coordination pattern.
5. **Team and system cost?** Weigh SQL/JPA/Reactor expertise, tooling, testing, production troubleshooting, debuggability, and migration cost.
6. **Have you measured under realistic load?** Pick the simplest option that meets requirements first, then justify changes with throughput, p95/p99 latency, pool saturation, SQL plans, and error rates.

### Short Decision Tree

```text
Does the problem require rich relationships/entity lifecycle/dirty checking?
  ├─ Yes → Evaluate JPA as the default
  └─ No  → Evaluate explicit SQL as the default
             ↓
Is the pipeline genuinely reactive end-to-end, I/O-heavy,
and supported by drivers/resources?
  ├─ Yes → Prototype and measure R2DBC; SQL can still use DatabaseClient
  └─ No  → Stay with JDBC or JPA
             ↓
Benchmark and verify exact transaction boundaries
  ├─ Meets SLA, maintainable → Keep the choice
  └─ Falls short → Optimize SQL/indexes/pool, then consider switching tech
```

"Reactive" describes I/O execution; "explicit SQL vs. entity mapping" describes abstraction level. Even with R2DBC, you can still write manual SQL or use templates/repositories.

## 6. A Shared Example Problem: Orders

Assume a minimal PostgreSQL table:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    status VARCHAR(16) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_orders_status_id ON orders (status, id);
```

Two distinct requirements:
- **List screen** needs only `id`, `customer_name`, and `total_amount` for orders with `status = 'NEW'`: clear projection/SQL, no need to materialize an object graph.
- **Order payment** transitions `NEW → PAID` exactly once and requires concurrent update control; this can be expressed via JPA entity behavior or an `UPDATE ... WHERE status = 'NEW'` statement.

Each example below is an **independent implementation option**; do not wire all three into a single transaction. Files belong to package `example.data`; add the matching dependencies, PostgreSQL connection settings, and the schema above before running the application.

### 6.1. Explicit SQL with JdbcClient

Typical Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`OrderView.java`:

```java
package example.data;

import java.math.BigDecimal;

public record OrderView(long id, String customerName, BigDecimal totalAmount) {}
```

`JdbcOrderQuery.java`:

```java
package example.data;

import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderQuery {
    private final JdbcClient jdbc;

    public JdbcOrderQuery(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderView> findByStatus(String status) {
        return jdbc.sql("""
                SELECT id, customer_name, total_amount
                FROM orders
                WHERE status = :status
                ORDER BY id
                """)
            .param("status", status)
            .query((rs, rowNum) -> new OrderView(
                rs.getLong("id"),
                rs.getString("customer_name"),
                rs.getBigDecimal("total_amount")))
            .list();
    }

    public boolean markPaid(long id) {
        int affected = jdbc.sql("""
                UPDATE orders
                SET status = 'PAID', version = version + 1
                WHERE id = :id AND status = 'NEW'
                """)
            .param("id", id)
            .update();
        return affected == 1;
    }
}
```

**Explanation:** `:status`/`:id` are bound parameters, preventing user input from turning into executable SQL. `RowMapper` maps strictly the three returned columns. The status-guarded `UPDATE` acts as a **compare-and-set in the DB**: two concurrent calls cannot both move an order from `NEW` to `PAID`; the second receives `affected = 0`. Distinguish a missing ID from an invalid state if the business interface requires distinct error codes.

If multiple statements must be atomic, place `@Transactional` on a **public service method** invoked through a Spring proxy—for instance, updating the order and inserting an audit row using the same JDBC transaction manager. A single `UPDATE` like the one above is already atomic in PostgreSQL, whereas a multi-statement workflow requires an explicit transaction. For large batches or stored procedures, look at `JdbcTemplate`/dedicated batch APIs rather than forcing everything through one `JdbcClient` method.

### 6.2. JPA for Entity Lifecycle

Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`OrderEntity.java`:

```java
package example.data;

import java.math.BigDecimal;
import jakarta.persistence.*;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_name", nullable = false)
    private String customerName;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Version
    private long version;

    protected OrderEntity() {}

    public OrderEntity(String customerName, BigDecimal totalAmount) {
        this.customerName = customerName;
        this.totalAmount = totalAmount;
        this.status = OrderStatus.NEW;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException("Order is not NEW");
        }
        this.status = OrderStatus.PAID;
    }
}

enum OrderStatus { NEW, PAID }
```

`OrderRepository.java`:

```java
package example.data;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {}
```

`OrderService.java`:

```java
package example.data;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void markPaid(long id) {
        OrderEntity order = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));
        order.markPaid();
        // Managed entity: Hibernate emits UPDATE on flush/commit.
    }
}
```

**Explanation:** Inside the transaction, the entity loaded from the repository is **managed**. Hibernate detects the `status` change and synchronizes it on flush; calling `save` is unnecessary for an already-managed entity. `@Version` detects **optimistic locking conflicts** when two transactions concurrently modify the same version; the application must decide whether to return an error or retry based on business semantics. The version field requires a matching column in the schema.

JPA's strengths shine when entities have rich relationships and domain behavior, though you must actively manage:
- `LAZY`/`EAGER`, `JOIN FETCH`, `@EntityGraph`, and projections tailored to each use case; do not load entire association graphs just to build a list view.
- N+1 queries: e.g., reading 50 orders and lazily accessing each customer inside a loop can emit 50 extra queries. Monitor query counts and tune fetch strategies.
- `flush` synchronizes SQL without necessarily `commit`ting; `@Transactional(readOnly = true)` is an optimization hint / framework contract and should not be treated as a guarantee that the database rejects every write statement.
- Avoid returning entities with lazy associations directly as JSON after the transaction closes; create DTOs in the service or use appropriate projections.

JPA does not forbid explicit SQL: `@Query`, native queries, projections, or `JdbcClient` for a reporting endpoint can coexist cleanly in the same application as long as transaction boundaries are clearly designed.

### 6.3. R2DBC with DatabaseClient

Typical Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
```

For PostgreSQL, configure `spring.r2dbc.url` as `r2dbc:postgresql://host:port/db` along with user/password; this connection is distinct from JDBC's `spring.datasource.url`. Pair with Spring WebFlux when the HTTP pipeline is also reactive; Reactor/R2DBC libraries themselves do not mandate WebFlux controllers.

`ReactiveOrderQuery.java` (reusing `OrderView` from above):

```java
package example.data;

import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;

@Repository
public class ReactiveOrderQuery {
    private final DatabaseClient db;

    public ReactiveOrderQuery(DatabaseClient db) {
        this.db = db;
    }

    public Flux<OrderView> findByStatus(String status) {
        return db.sql("""
                SELECT id, customer_name, total_amount
                FROM orders
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", status)
            .map((row, metadata) -> new OrderView(
                ((Number) Objects.requireNonNull(row.get("id"))).longValue(),
                row.get("customer_name", String.class),
                row.get("total_amount", BigDecimal.class)))
            .all();
    }
}
```

**Explanation:** `Flux<OrderView>` describes the work; the query typically begins upon **subscription**, not necessarily when `findByStatus` is invoked. `all()` emits rows sequentially as a publisher, while actual streaming and backpressure depend on the driver, query, and operator usage. Never call `block()` in a handler or reactive service, and never call manual `subscribe()` just to "trigger" side effects inside a transaction.

A reactive update, invoked via a Spring proxy with an appropriate `R2dbcTransactionManager`, can be written as:

```java
package example.data;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {
    private final DatabaseClient db;

    public ReactiveOrderService(DatabaseClient db) {
        this.db = db;
    }

    @Transactional
    public Mono<Void> markPaid(long id) {
        return db.sql("""
                UPDATE orders
                SET status = 'PAID', version = version + 1
                WHERE id = :id AND status = 'NEW'
                """)
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .flatMap(count -> count == 1
                ? Mono.<Void>empty()
                : Mono.error(new IllegalStateException(
                    "Order not found or not NEW")));
    }
}
```

Here, the reactive transaction binds to the publisher's **Reactor context** and runs upon subscription, rather than relying on an imperative transaction's `ThreadLocal`. If the application has multiple transaction managers, specify the manager explicitly on the method to avoid picking the wrong one. Do not split a transaction via internal `subscribe()` calls, `block()`, or by switching to JDBC mid-chain assuming they share a transaction.

Spring Data R2DBC repositories / `R2dbcEntityTemplate` fit simple CRUD and mapping, yet they do not provide JPA-style lazy-loading graphs, managed-entity dirty checking, or cascade semantics. If business logic demands those capabilities, implement aggregate orchestration explicitly or choose JPA.

## 7. Transactions, Consistency, and Concurrency Handling

### With JDBC

`@Transactional` via an imperative transaction manager binds the JDBC connection to the transaction's execution flow. When multi-table operations must succeed or fail together, place the transaction at the service layer:

```java
@Transactional
public void payOrder(long orderId) {
    // UPDATE orders WHERE status = 'NEW'
    // INSERT payment_audit ...
    // same JDBC transaction manager/DataSource
}
```

This is **structural illustrative code**, not a standalone compilable method (the commented statements must be implemented).

### With JPA

The persistence context is bound to the transaction; `@Version` supports optimistic locking. Under concurrent updates, exceptions can surface at flush or commit time—even after the `order.markPaid()` line. Never catch optimistic locking exceptions and retry infinitely: evaluate idempotency, the updated version, and business meaning.

### With R2DBC

The reactive transaction manager binds the connection to the Reactor context. To keep multiple operations in one transaction, **compose them within a single publisher**:
- Use `then`, `flatMap`/`concatMap`, or `TransactionalOperator` to chain dependent steps.
- Propagate errors to trigger rollback per policy; swallowing errors with `onErrorResume` can cause the transaction to commit if the outcome appears successful.
- Distinguish a single-database transaction from cross-system workflows (DB + message broker/email/REST). Publish events after commit or use a **transactional outbox** when you must avoid DB writes succeeding while event publishing fails.

**No single ACID transaction automatically spans both JDBC/JPA and R2DBC**, even when both point to the same database. Pick one access path per transaction boundary; when combining technologies, design explicit consistency mechanisms.

### Isolation, Locks, and Idempotency

All three stacks are bound by database rules:
- `READ COMMITTED`/`REPEATABLE READ`/`SERIALIZABLE` carry different semantics and overhead across databases.
- You must guard against lost updates, non-repeatable reads, phantoms, deadlocks, and lock waits according to your workload.
- Use state/version predicates in `UPDATE`, unique constraints, or idempotency keys for operations that may be retried.
- Never hold transactions open during external network calls or user waits.
- Retry only retryable errors at safe boundaries, ensuring side effects are never duplicated.

## 8. Reactive Access Only Helps When the Whole Chain Fits

A pipeline aiming to leverage R2DBC should resemble:

```text
WebFlux request → reactive auth/client → reactive service
               → R2DBC driver → database → Flux/Mono response
```

If most calls still use JDBC/JPA, blocking filesystem I/O, blocking HTTP clients, or heavy CPU work on the event loop, converting one repository to `Flux` does not create a non-blocking path. Using `Schedulers.boundedElastic()` to isolate unavoidable blocking APIs is a boundary workaround; it uses threads to run blocking work rather than making the driver non-blocking.

**Backpressure** lets downstream request a bounded number of items in a Reactor pipeline; it does not guarantee the database cancels or shrinks all corresponding work. For large lists, you still need pagination/keyset pagination, result limits, timeouts, and an understanding of driver fetch behavior. Reactive typically pays off when many concurrent requests wait on I/O; it does not replace indexes, SQL plans, or connection pool sizing.

## 9. Query Cost Matters More Than Framework Name

Before switching stacks, measure:
- What actual SQL runs, how many queries per request, and whether N+1 exists.
- `EXPLAIN (ANALYZE, BUFFERS)` on representative queries (in a safe environment, remembering `ANALYZE` executes the query).
- Indexes, join order, selectivity, sorting, row counts, payload size, pagination, and network latency.
- Database CPU/I/O/locks, active/idle/waiting pool connections, timeouts, and transaction durations.
- Throughput, p50/p95/p99 latency, memory/GC, and threads/event loops under identical load and datasets.

**Rule of thumb:** optimize queries, indexes, round trips, and payloads first; choose ORM/JDBC/R2DBC based on technical fit and maintainability. A `SELECT *` returning 10,000 rows is still heavy even behind a `Flux` API; a well-projected ORM query with a sound fetch plan can perform cleanly in production.

## 10. Four Typical Selection Scenarios

**A. Revenue/reconciliation reporting:** requires multi-table `JOIN`s, `GROUP BY`, window functions/CTEs, DTO projections, and DBA SQL review. Favor **JdbcClient/JdbcTemplate** or a SQL DSL if suitable. JPA native queries also work, but do not force an entity graph onto aggregated results.

**B. Order lifecycle management:** orders with many line items, states, invariants, appropriate cascades, optimistic locking, and aggregate-scoped transactions. Favor **JPA/Hibernate** if relationships and domain behavior genuinely benefit; inspect fetching to prevent N+1. For small aggregates, explicit SQL or Spring Data JDBC can be simpler.

**C. WebFlux gateway with high concurrent DB-waiting requests:** the team already uses Reactor, the PostgreSQL R2DBC driver covers required features, and load tests reveal thread/pool pressure. Trial **R2DBC**; measure throughput/latency and connection limits. Do not choose it solely because endpoints return `Mono`.

**D. Low-load internal CRUD where the team knows MVC:** favor the easiest imperative approach to maintain—usually **JPA** for clear domain entities, or **JdbcClient** for simple tables and custom queries. Reactive adds mental overhead and debugging complexity that may bring no benefit.

In large applications, you can combine **JPA for commands/domain writes** with **explicit SQL for read models/reporting**. This is a per-use-case choice rather than forcing one framework across an entire module, provided each operation has clear transaction and data consistency boundaries.

## 11. Designing Tests and Validating Your Choice

### Correctness Testing

- Use real PostgreSQL in Testcontainers when depending on SQL syntax, locks, isolation, enums, indexes, or driver behavior; H2 does not always mirror PostgreSQL.
- JDBC: verify mappers, column names, bound parameters, affected row counts, and rollback on failure.
- JPA: verify entity mapping, cascades, lazy/fetch query counts, flushes, optimistic locking, rollbacks, and N+1 queries. `@DataJpaTest` is a fitting slice test option when required config is loaded.
- R2DBC: verify `Mono`/`Flux` emissions and error/complete signals using `StepVerifier`, subscriptions, transaction rollbacks, and pool/driver behavior. `@DataR2dbcTest` supports slice testing for related components.
- Concurrency: run two concurrent requests updating a `NEW` order to verify only one succeeds; never test sequentially alone.

### Fair Load Testing

1. Use the same PostgreSQL version, schema, dataset, indexes, and business logic.
2. Warm up comparably; separate connection initialization, JIT, and cache warmup latency from steady-state measurements.
3. Configure connection pools and concurrency limits intentionally; do not compare mismatched default settings.
4. Test across multiple load levels, including overload, to observe queuing, timeouts, and degraded behavior.
5. Record p95/p99, throughput, errors, CPU/heap, connection counts, and SQL plans. Verify correctness and eventual resource cleanup as well.
6. Pick the option that meets SLAs, is straightforward to deploy and observe, and carries reasonable operational cost—never rely on a single average number.

A tiny benchmark on a developer laptop does not prove R2DBC or ORM is always faster or slower in production.

## 12. Security and Resilience

- **Bind parameters** for `WHERE`/`INSERT`/`UPDATE` values. Never concatenate input directly into SQL strings. Table names, column names, and `ORDER BY` identifiers cannot be bound as values: pick only from a predefined allowlist.
- Use least-privilege DB users; never grant administrative privileges to application accounts.
- Apply versioned schema migrations via Flyway/Liquibase; an R2DBC application may need a separate JDBC connection for migrations, and migrations do not share transactions with runtime queries.
- Set explicit timeouts for connections, queries, and transactions; distinguish application-side timeouts from actual query cancellation at the driver level.
- Log SQL and metrics judiciously for diagnostics; never log passwords, tokens, sensitive data, or raw parameters containing private information.
- Check which transaction manager is active when multiple `DataSource`/`ConnectionFactory` beans exist; use explicit bean names or qualifiers rather than guessing.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Choosing JPA "to avoid learning SQL" | N+1, hard-to-explain queries, loading unnecessary entities | Read SQL logs/plans, use projections/fetch plans, and understand transactions |
| Choosing JDBC because "manual SQL is always faster" | Repetitive mapping/transaction code; queries can still be poor | Compare per use case; use `JdbcClient` and clean reusable mappers |
| Returning `Mono` from a JDBC call and calling it reactive DB access | Blocking still occupies threads | Use a real R2DBC driver or keep an imperative contract |
| Calling `block()` inside a reactive handler/event loop | Blocks the event loop and degrades capacity | Compose with `flatMap`/`map`/`then`; isolate blocking work at controlled boundaries |
| Calling `subscribe()` manually inside a transactional service | Side effects detach from request lifecycle, errors, and transaction | Return the publisher so the framework or final subscriber manages execution |
| Assuming JDBC and R2DBC on the same database share one transaction | One side commits while the other fails | Separate boundaries; use outbox/compensation where appropriate |
| Returning whole entity graphs for list APIs | Query and serialization explosion | Use projections/DTOs, pagination, and avoid lazy access outside transactions |
| Measuring only average latency | Misses pool starvation, tail latency, and errors | Measure p95/p99, throughput, pool metrics, and database metrics |
| Ignoring locks, isolation, and retry/idempotency | Lost updates, double processing | Use constraints/versioning/conditional updates and concurrency tests |

## 14. Pre-Decision Checklist

- [ ] Clearly describe the hottest queries, data volume, and consistency requirements.
- [ ] Know whether the API/domain needs entity lifecycles or only DTOs/projections.
- [ ] Check blocking vs. reactive call paths and DB driver support.
- [ ] Define transaction manager, scope, isolation, concurrency, and idempotency.
- [ ] Analyze executed SQL, indexes, N+1 patterns, and connection pool behavior.
- [ ] Run tests with realistic data, including rollbacks and concurrent updates.
- [ ] Load test under equal conditions, recording p95/p99 SLAs, throughput, resources, and errors.
- [ ] Assess readability, maintainability, debuggability, and team handoff readiness.

**Technical conclusion:** choose **explicit SQL** when query control and projections are central; choose **JPA** when entity lifecycle and relationship management bring clear value; choose **R2DBC** when there is a genuine requirement and evidence for end-to-end non-blocking I/O. All three require understanding SQL, databases, transactions, and testing under realistic load.

## Official References

- Spring Framework JDBC Core/`JdbcClient`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework Data Access with R2DBC: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Data JPA Reference: https://docs.spring.io/spring-data/jpa/reference/
- Spring Data R2DBC Reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
- Spring Framework Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
