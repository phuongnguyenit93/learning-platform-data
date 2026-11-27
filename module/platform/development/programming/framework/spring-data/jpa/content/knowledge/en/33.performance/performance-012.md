# Choosing Between Optimizing JPA, Native SQL, and JDBC Access

In a **Spring Data JPA** application, when a screen or data task runs slowly, three approaches are commonly weighed: optimizing existing JPA queries and usage; writing **native SQL** while still executing through JPA; or using **JDBC** directly (often via `JdbcTemplate`). Which path to take depends on the root cause of the slowdown, the required return shape, and transaction consistency requirements—going to a lower layer does not automatically make things faster.

In this lesson, "optimizing JPA" refers to improving JPQL/Criteria, association loading, projections, pagination, persistence context management, and batching; "native SQL" means database-specific SQL run through `EntityManager` or `@Query(nativeQuery = true)`; and "JDBC" means working with `Connection`/`PreparedStatement`/`ResultSet`, commonly assisted by Spring's `JdbcTemplate`. **All three ultimately send SQL to the database**.

## 1. Diagnose Before Picking a Tool

A slow API can stem from very different causes:

| Observed symptom | Where to inspect first |
| --- | --- |
| One request generates hundreds of similar `SELECT`s | N+1, lazy loading, fetch plans, batch fetching; usually fixed in JPA |
| One SQL query is slow even when run directly on the database | Execution plan, indexes, filters, joins, statistics, scanned row counts; switching to JDBC may still be slow |
| SQL is fairly fast, yet mapping tens of thousands of entities spikes memory | Projections, row limits, streaming/DTOs, avoiding oversized persistence contexts |
| Need window functions, complex CTEs, or DB-specific analytical queries | Native SQL can express them clearly and optimize more easily |
| Need to export massive volumes, streaming each row to a file/output | JDBC with callbacks or cursors/fetch sizes can cut ORM overhead |
| Bulk updates spend too much time in flush/dirty checking | JDBC batching, JPQL/native bulk DML, tuning JPA batch/flush and evaluating consistency |

**Minimum measurement steps**:

1. Pick *one* representative task, returned row count, concurrency level, and target latency (e.g., endpoint p95).
2. Measure application duration, SQL statement counts, rows read, network payload size, round-trips, CPU, and memory. Separate connection pool wait time from SQL execution time.
3. Extract the **actual** SQL emitted by Hibernate and inspect the DB query plan. For instance in PostgreSQL, with a safe `SELECT` on test data:
   
   ```sql
   EXPLAIN (ANALYZE, BUFFERS)
   SELECT id, total_amount, created_at
   FROM sales_orders
   WHERE status = 'PAID'
   ORDER BY created_at DESC, id DESC
   LIMIT 100;
   ```
   
   `ANALYZE` executes the query to gather measurements; other database engines have their own tools and syntax. Inspect actual vs. estimated rows, indexes/scans, sorts, buffers, and total duration.
4. Run benchmarks multiple times under identical filters, row/column counts, indexes, data, and concurrency; warm up properly and account for caching. Compare p50/p95 latency, database load, CPU, GC, and memory—not just a single "faster" run.
5. Switch tools only when backed by a measurable hypothesis, such as "90% of time is spent in entity hydration" or "the SQL plan requires a construct awkward to express in JPQL."

Never conclude "JPA is slow" before knowing the SQL, query count, result size, and workload.

## 2. When to Keep JPA and Optimize Usage

**JPA is usually the default choice** for business logic needing entity relationships, state mutations with dirty checking, lifecycle/cascades, optimistic locking, repository abstractions, or domain model reuse. Many performance issues can be solved right here.

### 2.1. Reducing N+1 with Appropriate Fetch Plans

For example, fetching 100 `Order`s and accessing `order.getCustomer().getName()`. If each order issues an extra `SELECT customer`, round-trips spike. Fixes include:

- `JOIN FETCH` or `@EntityGraph(attributePaths = "customer")` when the screen is certain to read `customer`; especially straightforward for **to-one** associations.
- Projections selecting only display columns/properties when managed entities are unnecessary.
- Batch fetching for lazy associations accessed in batches, e.g., tuning Hibernate `hibernate.default_batch_fetch_size` to fit the workload.

Do not flip all associations to `EAGER` to "cure" N+1: doing so can over-fetch data, trigger extra queries, or cause unwanted joins. `JOIN FETCH` across multiple collections simultaneously can multiply rows via Cartesian products; fetching collections alongside pagination risks in-memory pagination or errors depending on Hibernate settings. For paginated screens, typically paginate IDs/pages first and then fetch related data in a controlled manner.

### 2.2. Projections and Pagination Before Abandoning the ORM

When you only need `id`, `total`, and `createdAt`, do not load a heavy entity carrying numerous unused associations. DTO projections in JPQL cut column counts and avoid stuffing all records into the persistence context as managed entities.

- Use `Pageable` to bound row counts; when only a limited list is needed without total page counts, `List<T>` with `Pageable` avoids a count query. `Page<T>` typically needs a total row count; `Slice<T>` fits when you only need to know if a next page exists.
- For deep pagination on large datasets, high offsets are expensive; consider **keyset pagination** over a deterministic sort key pair (`created_at, id`) when business logic permits.
- Include a unique tie-breaker in sorting to prevent unstable ordering when records share identical timestamps.

### 2.3. Optimizing Writes and Persistence Context Lifecycle

- Configuring `hibernate.jdbc.batch_size` and picking an appropriate ID generation strategy lets Hibernate batch `INSERT`/`UPDATE` statements; using `GenerationType.IDENTITY` can prevent standard Hibernate insert batching. `saveAll(...)` **does not guarantee** a single SQL statement.
- For bulk writes, process in chunks and consider deliberate `flush()`/`clear()` calls to bound managed entities. `clear()` detaches managed entities, so account for unflushed data and business logic.
- `@Transactional(readOnly = true)` provides an optimization hint to the framework/provider for read transactions; it is **not** a guarantee of read-only SQL or a substitute for DB permissions.
- Proper indexes matching `WHERE`, `JOIN`, `ORDER BY`, selective predicates, and accurate database statistics often matter far more than JPA vs. JDBC. Every new index also carries storage and write costs.

**Keep optimized JPA** when data genuinely represents entities, lifecycle/transactions/locking are needed, queries express cleanly in JPQL/Criteria, and SQL/row/mapping counts are reasonable.

## 3. When Is Native SQL via Spring Data JPA Appropriate?

Native SQL unlocks database syntax and capabilities: CTEs, window functions (`ROW_NUMBER`, `RANK`), JSON/array operators, recursive queries, hints, PostgreSQL/Oracle/SQL Server specifics, or aggregations awkward to express in JPQL.

Spring Data JPA supports `@Query(value = "...", nativeQuery = true)` and, in supporting versions, `@NativeQuery`. Example:

```java
@Query(
    value = """
        SELECT o.id, o.total_amount
        FROM sales_orders o
        WHERE o.status = :status
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT :limit
        """,
    nativeQuery = true
)
List<Object[]> recentByNativeSql(
        @Param("status") String status,
        @Param("limit") int limit);
```

This is a **repository method snippet**, not a standalone Java program. `LIMIT` illustrates PostgreSQL syntax; SQL, parameter types, and result mappings must match the real database. `Object[]` works for brief demos, but real applications should prefer strongly typed projections/DTOs or result-set mappings.

**Native SQL does not automatically bypass JPA.** If a query returns managed entities, Hibernate still hydrates them and maintains the persistence context. If a native query returns scalar/DTO projections, entity management overhead drops, yet the speedup comes from **the specific SQL and result shape**, not merely the `nativeQuery` flag.

Trade-offs to weigh:

- Coupled to physical schemas, table/column names, and database dialects; entity refactoring does not automatically update SQL strings.
- Native pagination/sorting with complex SQL may require a custom `countQuery` and syntax testing; Spring Data's SQL rewriting does not handle every query shape.
- Column-to-interface-projection/DTO mapping must be explicit, especially aliases and numeric/date-time types; entity mapping and scalar mapping differ.
- Use bind parameters instead of concatenating input values. For dynamic column names or `ORDER BY`, pick only from a controlled whitelist; bind parameters cannot replace SQL identifiers.
- Bulk `UPDATE`/`DELETE` running directly in the DB can leave managed entities in the persistence context **stale**. Consider `flush` before and selective `clear`/`refresh` afterward within proper transaction boundaries.

## 4. When Is JDBC a Sensible Choice?

JDBC fits when you want **direct control over SQL, PreparedStatement, ResultSet, and row-by-row consumption** without entity mapping: large CSV exports, ETL, batch operations on simple tables, flat multi-column reports, or integrating DBA-tuned SQL.

In Spring applications, `JdbcTemplate`/`NamedParameterJdbcTemplate` is usually more convenient than manually opening/closing `Connection`s because it handles resource cleanup, exception translation, and Spring transaction participation when configured properly. Drop to raw JDBC only when you need control the templates do not expose.

However, JDBC **lacks** dirty checking, lazy loading, association mapping, entity lifecycles, and automatic entity-level optimistic locking. You manage SQL, row mapping, locking/version checks, and schema-change impacts yourself. JDBC also **does not guarantee streaming** merely by passing a callback: the driver may buffer the `ResultSet` unless fetch size, cursor type, and transaction settings are configured properly.

**Connection and transaction management:** JPA uses JDBC underneath. Both access paths can participate in the same Spring transaction when using a compatible transaction manager and `DataSource` (e.g., `JpaTransactionManager` exposes the JDBC Connection of the same DataSource). Do not assume sharing a database automatically means sharing a connection/transaction. When mixing JPA + JDBC in one transaction, JPA may hold **unflushed** changes invisible to JDBC queries; conversely, JDBC updates do not automatically refresh already-loaded managed entities.

## 5. Unified Example: Order Data

Suppose a PostgreSQL system has the following table:

```sql
CREATE TABLE sales_orders (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    created_at   TIMESTAMP NOT NULL
);
```

`status` holds string values `PAID` or `CANCELLED`. `created_at` uses timezone-naive `TIMESTAMP` in this example; real systems must standardize time conventions. Minimal JPA model:

```java
// SalesOrder.java — in package com.example.sales
package com.example.sales;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "sales_orders")
public class SalesOrder {
    @Id
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal total;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected SalesOrder() {}
}
```

This entity illustrates **reading** needed fields. For creating/updating orders, an application must also design constructors, domain methods, ID strategies, versioning, and validation. Shared DTO for projections and JDBC:

```java
// OrderRow.java — package com.example.sales
package com.example.sales;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderRow(
        Long id,
        BigDecimal total,
        LocalDateTime createdAt) {}
```

The Spring snippets below are **project-integrated components** requiring Spring Data JPA, Spring JDBC, the PostgreSQL driver, and the schema above; they cannot be compiled and run with `javac` on a single file without dependencies, beans, DB, and connection configuration.

### 5.1. Requirement A: Latest 100 Orders Screen — Prefer JPA Projection

```java
// SalesOrderRepository.java — package com.example.sales
package com.example.sales;

import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    @Query("""
        select new com.example.sales.OrderRow(
            o.id, o.total, o.createdAt)
        from SalesOrder o
        where o.status = :status
          and o.createdAt >= :from
        order by o.createdAt desc, o.id desc
        """)
    List<OrderRow> recentOrders(
            @Param("status") String status,
            @Param("from") LocalDateTime from,
            Pageable pageable);
}
```

Service call with injected `SalesOrderRepository repository`:

```java
var rows = repository.recentOrders(
        "PAID",
        LocalDateTime.of(2026, 1, 1, 0, 0),
        org.springframework.data.domain.PageRequest.of(0, 100));
```

Advantages: JPA instantiates only `OrderRow` with three fields, skipping full entities and associations; `Pageable` bounds rows; query logic uses entity attributes, keeping maintenance simple. There is no reason to switch to native SQL/JDBC if emitted SQL has a good plan and meets latency targets.

In this case, you might evaluate an index, e.g., in PostgreSQL:

```sql
CREATE INDEX idx_sales_orders_status_created_id
    ON sales_orders (status, created_at DESC, id DESC);
```

This index is only a **candidate**: inspect `EXPLAIN` and real read/write workloads before creating it on an active system. If the query matches most of the table or filters have low selectivity, the DB may rightly pick another scan.

### 5.2. Requirement B: Latest PAID Order *Per Customer* — Native SQL Has Expressive Advantage

The problem "one latest order per customer, tie-broken by id" is expressed directly with a window function:

```java
// LatestOrderRepository.java — package com.example.sales
package com.example.sales;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface LatestOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    interface LatestOrderView {
        Long getId();
        Long getCustomerId();
        BigDecimal getTotal();
    }

    @Query(value = """
        WITH ranked AS (
            SELECT o.id, o.customer_id, o.total_amount,
                   ROW_NUMBER() OVER (
                       PARTITION BY o.customer_id
                       ORDER BY o.created_at DESC, o.id DESC
                   ) AS rn
            FROM sales_orders o
            WHERE o.status = :status
        )
        SELECT id AS "id",
               customer_id AS "customerId",
               total_amount AS "total"
        FROM ranked
        WHERE rn = 1
        ORDER BY id
        LIMIT :maxRows
        """, nativeQuery = true)
    List<LatestOrderView> latestByCustomer(
            @Param("status") String status,
            @Param("maxRows") int maxRows);
}
```

Example call `latestByCustomer("PAID", 100)`. `ROW_NUMBER` picks one row per `customer_id`; adding `id DESC` breaks ties when multiple orders share the same `created_at`. The outer `ORDER BY id` makes `LIMIT` deterministic. In PostgreSQL, quoted aliases like `"customerId"` preserve exact property names for interface projections.

The strength here is **SQL expressing the problem clearly**. Do not conclude it is faster than JPA simply because it is native SQL: examine how many rows get ranked, index usage, sort memory, and the actual plan. Outer `LIMIT 100` does not guarantee the database only scans 100 rows inside the CTE.

### 5.3. Requirement C: Exporting Huge Numbers of PAID Orders — JDBC Callback for Row-by-Row Processing

`JdbcTemplate` below uses a `PreparedStatement` with bound parameters, sets fetch size, and invokes `Consumer<OrderRow>` per row instead of building a gigantic `List<OrderRow>`.

```java
// OrderExportJdbc.java — package com.example.sales
package com.example.sales;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.function.Consumer;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class OrderExportJdbc {
    private static final String SQL = """
        SELECT id, total_amount, created_at
        FROM sales_orders
        WHERE status = ? AND created_at >= ?
        ORDER BY id
        """;

    private final JdbcTemplate jdbc;

    public OrderExportJdbc(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public void forEachPaidSince(
            LocalDateTime from,
            Consumer<OrderRow> consumer) {

        jdbc.query(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                    SQL,
                    ResultSet.TYPE_FORWARD_ONLY,
                    ResultSet.CONCUR_READ_ONLY);
            ps.setString(1, "PAID");
            ps.setTimestamp(2, Timestamp.valueOf(from));
            ps.setFetchSize(500);
            return ps;
        }, (RowCallbackHandler) rs -> consumer.accept(
                new OrderRow(
                        rs.getLong("id"),
                        rs.getBigDecimal("total_amount"),
                        rs.getTimestamp("created_at")
                                .toLocalDateTime())));
    }
}
```

Key points:

- `PreparedStatement` guarantees `from` passes through parameter binding; no input is concatenated into SQL.
- `RowCallbackHandler` processes each row as JDBC iterates results. The callback can write sequentially to a service output stream/file; do not accumulate rows in a list if the goal is saving memory.
- `setFetchSize(500)` is a driver hint. With PostgreSQL JDBC, cursor-based streaming also depends on transaction settings (especially auto-commit), result set mode, and driver behavior; measure actual memory.
- `@Transactional(readOnly = true)` maintains operation boundaries when called via Spring proxy and a transaction manager governing the right `DataSource`. Do not hold transactions/connections open too long if the data consumer is very slow.
- `ORDER BY id` ensures deterministic export order by ID; for long exports while the table mutates, also define snapshot/isolation requirements or keyset batching to avoid skipped/duplicated rows.

This snippet has **no entity lifecycle** and hydrates no managed entities. Yet read row counts, SQL plans, network I/O, and output write speed can still outweigh ORM costs as bottlenecks.

## 6. Situational Decision Matrix

| Criterion | Optimize JPA/JPQL | Native SQL via JPA | JDBC/JdbcTemplate |
| --- | --- | --- | --- |
| Best suited for | CRUD, domain relationships, DTO lists expressible in JPQL | Analytical/complex SQL or DB-specific features | Flat reports/exports/batches, per-row and statement control |
| Entity management & dirty checking | Yes when returning managed entities; DTO projections avoid entity management on results | Yes when mapping entities; minimal when fetching scalars/DTOs | No |
| Coupling to DB schema | Usually lower, querying entity attributes | High; SQL tied to tables, columns, dialect | High; manual SQL and mappers |
| Access to DB-specific SQL features | Limited via JPQL/Criteria/provider | Broad | Broad |
| Fetch/cursor & SQL batch control | Via provider and JPA/Hibernate APIs | Partially via JPA/provider | Direct via JDBC/driver/template |
| Primary risks | N+1, over-fetching, collection pagination, large persistence contexts | Less portable SQL, mapping/count quirks, persistence context sync | Manual mappers, transaction/cursor/locking handling, more SQL boilerplate |
| Recommendation | Start here when aligned with the model | Choose when queries/plans need specific SQL | Choose when workloads need row/batch-level control |

**Quick selection flow:**

1. **SQL is already fast, just too many queries?** Fix JPA fetch plans/N+1 and projections.
2. **SQL runs slowly in the database?** Inspect execution plans, indexes, statistics, data, and SQL logic first; running *the same SQL* via native/JDBC rarely fixes a bad plan.
3. **Need window functions/CTEs/dialect-specific queries?** Use native SQL in the repository if you still want Spring Data JPA managing boundaries and mappings.
4. **Need to stream huge row counts, specialized batch SQL, avoiding thousands of managed entities?** Consider JDBC with callbacks/cursors and proper transactions.
5. **Have both entity CRUD and heavy reporting?** Use JPA for domain workflows and JDBC/native for measured hotspots; define data consistency rules across both paths.

## 7. Common Mistakes

**"Native SQL/JDBC is always faster than JPA."** False. Given identical SQL, results, and database paths, gains may be minor; sometimes you merely shift cost into hand-written mappers. Keep comparisons fair across row counts, columns, caching, count queries, and transaction lifecycles.

**"`JOIN FETCH` on all associations reduces queries."** It can cut round-trips while inflating row multipliers, bandwidth, and memory. Be especially careful with multiple to-many associations and collection pagination.

**"Simply using `Pageable` makes queries optimal."** `Page<T>` may run counts; deep offsets are costly. Bound row counts, index `WHERE`/`ORDER BY` properly, and consider keyset pagination when needed.

**"`saveAll` means batch SQL."** Not by default. Check Hibernate batching, ID generation strategies, transaction/flush behavior, and SQL logs.

**"Updating via JDBC and immediately reading a JPA entity shows new data."** Entities already in the persistence context may return stale values; pending JPA changes may not have flushed yet when JDBC runs. Decide flush order, selective refresh/clear, and transaction boundaries before mixing APIs. `clear()` detaches all managed entities; never call it carelessly.

**"`setFetchSize` guarantees low memory."** Depends on the driver and cursor/transaction mode. `RowCallbackHandler` does not automatically stop a driver from buffering rows; verify with large datasets and measure actual heap.

**"`@Transactional(readOnly = true)` forbids data writes."** It is a hint whose exact enforcement depends on transaction manager/provider/database; design authorization and transaction boundaries explicitly.

**"Concatenating user values into native SQL is fast."** String concatenation creates SQL injection risks and hurts query plan reuse. Bind parameters for values; whitelist dynamic table/column/sort identifiers separately.

## 8. Checklist to Validate Performance After Switching Approaches

- **Business correctness:** row sets, duplicates, nulls, tie-breaker ordering, pagination, concurrent updates, and transactional consistency.
- **SQL correctness:** inspect actual emitted SQL, bound parameters, query count, DB execution plans, and whether indexes are chosen.
- **Resource correctness:** p50/p95 latency, application and database CPU, connection-pool waits, heap/GC, rows/bytes transferred.
- **Operational correctness:** load test at realistic data volumes and concurrency; assess write impact of new indexes and connection hold times during streaming.
- **Architectural clarity:** document SQL ownership, DTO mapping, EntityManager/JDBC coordination rules, and how tests update on schema changes.

You do not have to "pick one technology for every query." Within a Spring Data JPA module, a well-grounded rule of thumb is: **fix SQL/fetch plans/indexes and cut redundant data in JPA first; use native SQL for specialized queries; use JDBC when low-level row/batch control is needed and its benefit is proven.** Every choice must be validated on real workloads.

### References

- Spring Data JPA — Query Methods, Native Queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA — Projections: https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html
- Spring Framework — JDBC Core / JdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Hibernate ORM — User Guide (fetching, persistence context, batching): https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html