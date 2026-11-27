# Placing JdbcClient or Other SQL Libraries Within the Right Responsibility Boundary

Spring Data JDBC provides repositories to read and write aggregates along domain boundaries. In practice, there are still reporting queries, JOIN operations, bulk actions, or specialized SQL statements that standard repositories do not express conveniently. In such cases, you can supplement them with JdbcClient or a specialized SQL library.

What matters is placing the SQL tool in the right layer. JdbcClient, jOOQ, MyBatis, or Jdbi should handle data access inside infrastructure adapters. They should never become the API of the domain model, and they must never create a second write path that bypasses invariants protected by the aggregate root.

This lesson covers how to combine Spring Data JDBC with specialized SQL tools, how to choose boundaries for queries and commands, how to share transactions, and what to control when direct SQL mutates data.

## 1. Why Pair a SQL Tool with Spring Data JDBC?

Spring Data JDBC focuses on aggregates. Repositories provide CRUD operations suitable when the application needs to load an aggregate root, mutate domain objects, and save aggregate state.

However, some use cases have a different shape:

- A screen needs daily revenue totals grouped by status and joined across multiple tables.
- A report needs GROUP BY, window functions, CTEs, or database-specific functions.
- A search requires complex SQL conditions and projection into a DTO.
- A batch job needs to update or delete thousands of records.
- A statement needs RETURNING, UPSERT, locking, or database-specific syntax.
- A query requires fine-grained tuning for indexes and execution plans.

You can address these needs with JdbcClient or a dedicated SQL library while keeping Spring Data JDBC as the persistence tool for aggregates.

For example, an order list screen only needs order codes, statuses, and total amounts. Loading every SalesOrder along with all its OrderLine items just to sum prices can trigger extra queries and materialize unnecessary objects. An aggregate SQL query returning DTOs is usually a better fit.

## 2. Define Responsibility Boundaries Before Choosing a Tool

Start by asking: what does the use case need to do with the data?

| Need | Component That Should Own Responsibility |
|---|---|
| Enforcing business rules and protecting invariants | Aggregate root / domain service |
| Orchestrating a use case | Application service |
| Saving and loading aggregates according to mapping | Spring Data JDBC repository |
| Reporting queries, projections, specialized JOINs | Query adapter using JdbcClient or SQL library |
| Controlled bulk SQL operations | Command adapter in infrastructure |
| Managing transactions across multiple operations on one datasource | Application service with @Transactional |
| Integrating database-specific SQL | Infrastructure adapter |

A sound dependency structure:

~~~text
Web / API
    |
    v
Application service
    |
    +---- Domain model
    |        |
    |        +---- Repository port
    |
    +---- Query / command port
              |
              v
       Infrastructure adapters
              |
              +---- Spring Data JDBC repository
              |
              +---- JdbcClient adapter
              |
              +---- jOOQ / MyBatis / Jdbi adapter
                         |
                         v
                      Database
~~~

The domain model does not need to know whether the application uses JdbcClient, jOOQ, or MyBatis. The domain only needs to know business concepts and the interfaces defined by the application layer.

Never pass ResultSet, JdbcClient, DSLContext, SqlSession, or SQL-library-specific types into entities or domain services. Those types belong to the data access layer.

## 3. What Is JdbcClient?

JdbcClient was introduced in Spring Framework 6.1. It is a fluent API for JDBC that offers a more concise way to write queries by combining capabilities from JdbcTemplate and NamedParameterJdbcTemplate.

You can create the client from either template:

~~~java
@Bean
JdbcClient jdbcClient(NamedParameterJdbcTemplate template) {
    return JdbcClient.create(template);
}
~~~

Or from JdbcTemplate:

~~~java
@Bean
JdbcClient jdbcClient(JdbcTemplate template) {
    return JdbcClient.create(template);
}
~~~

In a Spring Boot application, you can register a JdbcClient bean and inject it into adapters that need SQL queries. Use the same DataSource and transaction manager that Spring Data JDBC uses if operations need to participate in the same transaction.

Typical steps:

1. Declare the SQL with sql(...).
2. Bind parameters with param(...).
3. Choose how to read results via query(...), or perform writes via update().
4. Select a list, single row, or optional result with list(), single(), or optional().

Example reading a list of DTOs:

~~~java
List<OrderSummary> summaries = jdbcClient
        .sql("""
            SELECT id, order_code, status
            FROM sales_orders
            WHERE status = :status
            ORDER BY id DESC
            """)
        .param("status", "OPEN")
        .query((rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("order_code"),
                rs.getString("status")
        ))
        .list();
~~~

Example reading a single scalar value:

~~~java
long count = jdbcClient
        .sql("""
            SELECT COUNT(*)
            FROM sales_orders
            WHERE status = :status
            """)
        .param("status", "OPEN")
        .query(Long.class)
        .single();
~~~

Example update:

~~~java
int changed = jdbcClient
        .sql("""
            UPDATE sales_orders
            SET status = :status
            WHERE id = :id
            """)
        .param("status", "CANCELLED")
        .param("id", orderId)
        .update();
~~~

update() returns the affected row count. The application should verify this value when a use case requires exactly one record to be modified.

## 4. Using JdbcClient for Read Models and Reports

A query serving a UI screen usually does not need to return an aggregate. Create a dedicated DTO:

~~~java
public record OrderSummary(
        Long id,
        String orderCode,
        String status,
        BigDecimal totalAmount
) {
}
~~~

Query adapter:

~~~java
@Repository
public class JdbcOrderSummaryQuery implements OrderSummaryQuery {

    private final JdbcClient jdbcClient;

    public JdbcOrderSummaryQuery(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public List<OrderSummary> findByStatus(String status) {
        return jdbcClient
                .sql("""
                    SELECT
                        o.id,
                        o.order_code,
                        o.status,
                        COALESCE(
                            SUM(l.quantity * l.unit_price),
                            0
                        ) AS total_amount
                    FROM sales_orders o
                    LEFT JOIN order_lines l
                        ON l.order_id = o.id
                    WHERE o.status = :status
                    GROUP BY o.id, o.order_code, o.status
                    ORDER BY o.id DESC
                    """)
                .param("status", status)
                .query((rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_code"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                ))
                .list();
    }
}
~~~

This query performs the JOIN and summation in the database, then transforms only the needed columns into OrderSummary. The application avoids loading every order with all its line items just to sum totals in Java.

You can place an interface in the application layer to maintain dependency inversion:

~~~java
public interface OrderSummaryQuery {
    List<OrderSummary> findByStatus(String status);
}
~~~

JdbcOrderSummaryQuery implements that interface in infrastructure. The application service depends on OrderSummaryQuery, not directly on JdbcClient.

### 4.1. Do Not Turn a Read DTO into a Writable Aggregate

OrderSummary is not SalesOrder. It lacks the data and invariants needed to execute domain behavior.

For example, do not take an OrderSummary from the UI, mutate its status, and try to persist it as an aggregate. When an order needs to change, load SalesOrder through the repository, invoke domain methods, and save the root.

Read models are optimized for reading; aggregates are designed to protect business rules on writes. Both models can represent the same underlying data in different shapes.

## 5. Placing JdbcClient Inside a Custom Repository Fragment

If an additional query is tightly coupled to a repository, you can use a Spring Data custom repository fragment.

Fragment interface:

~~~java
public interface OrderSummaryQueries {

    List<OrderSummary> findSummaries(String status);
}
~~~

Implementation:

~~~java
class OrderSummaryQueriesImpl implements OrderSummaryQueries {

    private final JdbcClient jdbcClient;

    OrderSummaryQueriesImpl(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    @Override
    public List<OrderSummary> findSummaries(String status) {
        return jdbcClient
                .sql("""
                    SELECT
                        o.id,
                        o.order_code,
                        o.status,
                        COALESCE(SUM(l.quantity * l.unit_price), 0)
                            AS total_amount
                    FROM sales_orders o
                    LEFT JOIN order_lines l
                        ON l.order_id = o.id
                    WHERE o.status = :status
                    GROUP BY o.id, o.order_code, o.status
                    ORDER BY o.id DESC
                    """)
                .param("status", status)
                .query((rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_code"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                ))
                .list();
    }
}
~~~

Repository combining CRUD and the fragment:

~~~java
public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long>, OrderSummaryQueries {
}
~~~

Spring Data weaves the fragment implementation into the repository by naming convention—here OrderSummaryQueriesImpl. A different postfix can be configured if the project has its own convention.

This approach fits when the custom query remains part of the repository's query capabilities. If a query serves an independent screen or report, a separate query adapter is usually clearer and keeps the aggregate repository from becoming a dumping ground for every SQL query in the app.

## 6. When to Use a Repository Fragment vs. a Separate Query Adapter?

| Criterion | Repository Fragment | Separate Query Adapter |
|---|---|---|
| Query tightly coupled to aggregate repository | Good fit | Also usable |
| Query serving reports or dashboards | Can bloat the repository | Better fit |
| Multiple tables and dedicated read models | Easy to mix with CRUD | Clear boundary |
| Multiple use cases sharing the query | Reusable | Easy to reuse via port |
| Need to swap SQL tools | Can swap fragment implementation | Easy to swap adapter behind interface |

For example, findByExternalReference can reasonably live on SalesOrderRepository. Meanwhile, findMonthlyRevenueByRegion is an aggregate reporting query; it belongs in a dedicated RevenueReportQuery.

Class and interface names should reflect business intent rather than just library names. RevenueReportQuery states what the use case needs; JdbcRevenueReportAdapter states how it is currently implemented.

## 7. Preserving Transactions When Combining Repositories and JdbcClient

A major advantage of Spring JDBC is that JdbcTemplate, NamedParameterJdbcTemplate, and JdbcClient can participate in Spring transactions when sharing the same DataSource and transaction manager.

Example application service coordinating a repository and a query/audit adapter:

~~~java
@Service
public class OrderApplicationService {

    private final SalesOrderRepository orderRepository;
    private final OrderAuditWriter auditWriter;

    public OrderApplicationService(
            SalesOrderRepository orderRepository,
            OrderAuditWriter auditWriter
    ) {
        this.orderRepository = orderRepository;
        this.auditWriter = auditWriter;
    }

    @Transactional
    public void cancel(Long orderId) {
        SalesOrder order = orderRepository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.cancel();

        orderRepository.save(order);
        auditWriter.recordCancellation(orderId);
    }
}
~~~

If OrderAuditWriter uses JdbcClient with the same datasource and transaction manager, the audit INSERT can join the same transaction as repository.save(order).

If any operation throws an exception triggering rollback, both the root change and the audit record roll back according to the transaction policy.

Ensure that:

- The repository and JdbcClient share the same datasource.
- The transaction manager manages that datasource.
- Methods are invoked within the same transaction boundary.
- Connections are never opened manually with DriverManager inside adapters.
- Separate DataSources are not created per SQL tool.

If two tools connect to two different databases, standard @Transactional does not turn them into a distributed transaction. Design a saga, outbox, or transaction coordinator appropriate to your system requirements.

### 7.1. Read-Only Transactions

Read-only query adapters can be called inside a service:

~~~java
@Transactional(readOnly = true)
public List<OrderSummary> listOpenOrders() {
    return orderSummaryQuery.findByStatus("OPEN");
}
~~~

readOnly = true expresses the use case's intent and allows the transaction manager/driver to apply relevant optimizations. Do not treat it as an absolute security barrier blocking all writes; database permissions and adapter design still need proper controls.

### 7.2. Avoid Manual Connection Management

Never call DataSource.getConnection() and manually commit/close inside a method running under @Transactional, unless you are deliberately integrating with Spring's transaction-aware synchronization.

Doing so can open a connection outside the active transaction. Using JdbcClient or Spring JDBC templates lets Spring manage connections and transaction participation.

## 8. Using JdbcClient for Direct Writes: Protecting Invariants

JdbcClient knows nothing about aggregate roots or domain rules. An UPDATE/DELETE statement can modify child tables without loading the root, calling domain methods, or applying Spring Data JDBC's optimistic locking.

For example, business rules may only allow deleting an order line while the order is in DRAFT status. Do not simply write:

~~~java
jdbcClient.sql("""
    DELETE FROM order_lines
    WHERE order_id = :orderId
      AND line_no = :lineNo
    """)
    .param("orderId", orderId)
    .param("lineNo", lineNo)
    .update();
~~~

That statement checks neither order status, tenant, version, nor dependent records.

If this is an intentional direct command, you can use a conditional UPDATE to check and increment the root version before deleting the child:

~~~java
@Service
public class DirectOrderLineCommands {

    private final JdbcClient jdbcClient;

    public DirectOrderLineCommands(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    @Transactional
    public void deleteDraftLine(
            Long orderId,
            Integer lineNo,
            Long expectedVersion
    ) {
        int claimed = jdbcClient
                .sql("""
                    UPDATE sales_orders
                    SET version = version + 1
                    WHERE id = :orderId
                      AND version = :expectedVersion
                      AND status = 'DRAFT'
                    """)
                .param("orderId", orderId)
                .param("expectedVersion", expectedVersion)
                .update();

        if (claimed != 1) {
            throw new OptimisticLockingFailureException(
                    "Order changed or cannot be edited"
            );
        }

        int deleted = jdbcClient
                .sql("""
                    DELETE FROM order_lines
                    WHERE order_id = :orderId
                      AND line_no = :lineNo
                    """)
                .param("orderId", orderId)
                .param("lineNo", lineNo)
                .update();

        if (deleted != 1) {
            throw new IllegalArgumentException("Order line not found");
        }
    }
}
~~~

Both statements must participate in the same transaction. If the order line does not exist, the exception rolls back the version increment too.

This pattern requires a uniform convention: every write path modifying the aggregate must respect versioning. If another SQL path alters status or child rows without incrementing version, optimistic locking can no longer reliably detect those changes.

After direct SQL mutations, previously loaded aggregate objects may be stale. Do not keep editing old objects and saving them through the repository. Reload the aggregate in subsequent use cases and invalidate caches appropriately.

For standard business operations, prefer domain methods on the aggregate root. Reserve direct SQL for cases with a clear justification such as batching, performance, or a technical operation designed to preserve all invariants.

## 9. Distinguishing Command Adapters from Query Adapters

SQL adapters can be separated by intent:

**Query adapters** read data and return DTOs/read models. They normally do not modify aggregate state.

**Command adapters** mutate data. They must respect invariants, authorization, transactions, concurrency, and use case side effects.

~~~text
Application service
      |
      +---- Query port
      |        |
      |        v
      |    JdbcClient query adapter
      |        |
      |        v
      |    DTO / read model
      |
      +---- Command flow
               |
               v
          Domain invariant
               |
               +---- Repository save
               |
               +---- Direct SQL adapter (only when needed)
                        |
                        v
                   Version / FK / audit
~~~

Do not let a single class handle reporting, mutate child tables, send messages, and house domain rules. Separating by use case keeps transactions and responsibilities clear.

## 10. How to Choose Another SQL Library

JdbcClient is not the only option. Other SQL libraries can be used if the project requires capabilities Spring JDBC APIs do not conveniently provide.

| Tool | Strengths | When Appropriate | Boundary to Maintain |
|---|---|---|---|
| JdbcClient | Concise fluent API, integrates with Spring JDBC and transactions | Direct SQL queries/commands, DTOs | Infrastructure adapter |
| NamedParameterJdbcTemplate | Named parameter binding, mapping, and batch updates | Apps already using Spring JDBC templates | DAO/adapter |
| jOOQ | Type-safe DSL, schema codegen, strong support for complex SQL | Complex queries, database-specific SQL, type safety | Adapter returning DTOs or implementing ports |
| MyBatis | Explicit SQL via mappers/XML/annotations | Heavy SQL, fine control over statements and mapping | Mapper/DAO in infrastructure |
| Jdbi | Concise SQL objects and mappers over JDBC | Keeping SQL explicit with minimal boilerplate | DAO/adapter |
| Querydsl SQL | Type-safe query DSL | Dynamic queries and complex predicates | Query adapter |
| Hibernate/JPA native queries | Usable in systems already running JPA | Projects using JPA for part of persistence | Do not mix entity lifecycles arbitrarily with Spring Data JDBC |

Do not pick a tool solely for feature count. Weigh team familiarity, SQL complexity, testability, schema migrations, operational cost, and transaction integration.

### 10.1. jOOQ for Complex SQL

jOOQ excels when queries use multiple CTEs, window functions, lateral joins, or vendor-specific syntax. Its type-safe DSL and schema code generation help catch table/column naming errors at compile time.

The adapter should translate results to DTOs or read models:

~~~java
public interface RevenueReportQuery {
    List<RevenueByMonth> findRevenue(int year);
}
~~~

~~~java
@Repository
public class JooqRevenueReportAdapter implements RevenueReportQuery {

    private final DSLContext dsl;

    public JooqRevenueReportAdapter(DSLContext dsl) {
        this.dsl = dsl;
    }

    @Override
    public List<RevenueByMonth> findRevenue(int year) {
        // Use jOOQ DSL to build the query and map results
        // to RevenueByMonth.
        return List.of();
    }
}
~~~

The body is omitted because DSL syntax depends on the project's code generation and schema. What matters is that DSLContext never appears in the domain model or controllers.

### 10.2. MyBatis for Explicitly Managed SQL

MyBatis fits when SQL statements are long, need to live in XML mappers, or require complex result mapping.

Example mapper interface:

~~~java
@Mapper
public interface OrderReportMapper {

    List<OrderSummary> findByStatus(
            @Param("status") String status
    );
}
~~~

The SQL can live in XML mappers. The application service depends only on a port or query service; it does not need to know whether statements live in annotations or XML.

MyBatis can participate in Spring transactions when configured with the same datasource and transaction manager.

### 10.3. Jdbi and Querydsl SQL

Jdbi provides SQL objects, named bindings, and row mappers. Querydsl SQL offers a DSL for dynamically built predicates.

Both belong in infrastructure. Do not let query-specific types such as Query, Handle, SQLQuery, or ResultQuery leak into application/domain APIs without a clear architectural reason.

## 11. Do Not Create Two Sources of Truth for the Same Aggregate

A key risk when adding SQL tools is having two write paths operating on the same tables:

- SalesOrderRepository.save(order).
- JdbcClient directly updating sales_orders and order_lines.

If each path follows different rules, the system can suffer from bugs:

- One path increments version, the other forgets.
- One path checks status, the other skips it.
- One path writes audit records, the other omits them.
- One path publishes events, the other does not.
- Caches or read models are updated by only one path.
- The two mapping approaches interpret nulls, enums, keys, or collection ordering differently.

Establish one clear rule for each kind of change. For example:

| Type of Change | Chosen Write Path |
|---|---|
| Business order state transitions | Aggregate root and repository |
| Standard adding/removing of order lines | Domain method on root, followed by save |
| Bulk deletion of expired draft lines | Transactional command adapter with version checks |
| Updating a technical counter outside domain invariants | Explicitly guarded SQL adapter |
| Writing audit/outbox records | Same transaction as the command when atomicity is required |

A table may be read from multiple adapters, but commands mutating it must follow consistent, documented rules.

## 12. Parameter Binding and SQL Injection Prevention

Always bind values rather than concatenating input strings into SQL:

~~~java
jdbcClient
        .sql("""
            SELECT id, order_code
            FROM sales_orders
            WHERE status = :status
              AND customer_id = :customerId
            """)
        .param("status", status)
        .param("customerId", customerId)
        .query((rs, rowNum) ->
                new OrderHeader(
                        rs.getLong("id"),
                        rs.getString("order_code")
                ))
        .list();
~~~

Never write:

~~~java
String sql = "SELECT * FROM sales_orders WHERE status = '"
        + status + "'";
~~~

Parameter binding protects input values and lets the driver handle data types safely.

Table names, column names, sort directions, and SQL keywords generally cannot be bound as values. When dynamic selection is needed, use a whitelist:

~~~java
String orderColumn = switch (sortField) {
    case "createdAt" -> "created_at";
    case "orderCode" -> "order_code";
    default -> throw new IllegalArgumentException(
            "Unsupported sort field"
    );
};
~~~

Then interpolate only the whitelisted identifier into SQL. Never interpolate client-supplied strings directly.

## 13. Result Mapping and Data Type Handling

When mapping a ResultSet manually, the adapter is responsible for converting JDBC types to application types.

For example:

~~~java
OrderSummary mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new OrderSummary(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status"),
            rs.getBigDecimal("total_amount")
    );
}
~~~

Watch out for:

- getLong() returns 0 on SQL NULL; check wasNull() for nullable columns, or use wrapper types through an appropriate mapper.
- BigDecimal suits monetary values; avoid double for exact currency amounts.
- Enums need a stable mapping convention, such as storing business codes rather than relying on ordinal positions.
- TIMESTAMP, DATE, timezone, and Instant require clear conventions between database and application.
- Column aliases must match what the mapper expects.
- If a JOIN produces multiple rows per root, group results via an appropriate mapper/extractor to avoid duplicating roots or children.

Keep JDBC mapping out of domain entities. Entities should receive Java types already converted by adapters.

## 14. Pagination, Batching, and Resource Limits

Query adapters frequently serve large lists. Bound both results and returned payloads.

With SQL supporting LIMIT/OFFSET:

~~~java
List<OrderHeader> page = jdbcClient
        .sql("""
            SELECT id, order_code, status
            FROM sales_orders
            WHERE status = :status
            ORDER BY id DESC
            LIMIT :pageSize OFFSET :offset
            """)
        .param("status", status)
        .param("pageSize", pageSize)
        .param("offset", offset)
        .query((rs, rowNum) -> new OrderHeader(
                rs.getLong("id"),
                rs.getString("order_code"),
                rs.getString("status")
        ))
        .list();
~~~

Validate pageSize and offset against application limits. For large tables and deep pagination, keyset pagination can be more stable and efficient than offset pagination.

For batch writes, chunk data into reasonable batches to avoid:

- Holding transaction locks for too long.
- SQL statements with too many bind parameters.
- Memory spikes from buffering all inputs.
- Rolling back excessively large volumes of data.
- Tying up connection pool connections for prolonged periods.

Batching does not mean skipping validation. Decide clearly whether batches allow partial processing or must be all-or-nothing atomic.

## 15. Testing Adapters and Transaction Boundaries

Query adapters contain concrete SQL, so test them against a database whose dialect matches deployment closely. H2 cannot always substitute for PostgreSQL, MySQL, or SQL Server on syntax, constraints, and execution plans.

Useful test layers:

### 15.1. Unit Tests for Application Services

Mock ports to verify orchestration:

- The use case calls the right query/command ports.
- Business errors propagate accurately.
- Commands are not invoked when validation fails.
- Events/outbox writes are requested per rules.

Unit tests do not prove SQL correctness.

### 15.2. Integration Tests for Adapters

Use an appropriate test database to verify:

- SQL executes on the target dialect.
- Parameters bind with the right types.
- DTOs map cleanly.
- JOINs/GROUP BY return expected results.
- Constraints and affected row counts behave properly.
- Batching and pagination work as intended.

### 15.3. Testing Combined Transactions

A test should confirm that when a second SQL step fails, the first repository or audit step rolls back if they share the same transaction manager.

~~~text
@Transactional use case
    |
    +-- Spring Data JDBC save root
    |
    +-- JdbcClient insert audit
    |
    +-- Failure at final step
             |
             v
         ROLLBACK
    |
    +-- Root unchanged
    +-- Audit does not exist
~~~

### 15.4. Concurrency Testing for Direct Commands

Run two transactions genuinely competing on the same root. Verify the version predicate or lock prevents a stale transaction from overwriting newer changes.

Do not run a single sequential call and conclude optimistic locking works.

## 16. Package Structure to Prevent SQL Library Leakage

Example layout:

~~~text
order/
  domain/
    SalesOrder.java
    OrderLine.java
    OrderRepository.java

  application/
    CancelOrderService.java
    OrderSummaryQuery.java
    OrderSummary.java

  infrastructure/
    jdbc/
      JdbcOrderSummaryAdapter.java
      JdbcOrderLineCommandAdapter.java
    springdata/
      SpringDataSalesOrderRepository.java
    jooq/
      JooqRevenueReportAdapter.java

  web/
    OrderController.java
~~~

A project does not necessarily need every package shown above. Pick a layout fitting your current scale while preserving the core principle: the domain does not depend on specific SQL libraries.

If using Spring Data repositories directly in the application layer, place those interfaces in an appropriate package per project convention. When stricter port-and-adapter architecture is needed, define repository ports in domain/application and implement them in infrastructure.

## 17. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Injecting JdbcClient into domain entities | Domain couples to infrastructure and becomes hard to test | Place inside infrastructure adapters |
| Using direct SQL for all CRUD | Duplicates mapping and bypasses aggregate persistence | Keep Spring Data JDBC for aggregates |
| Returning reporting DTOs and using them for writes | DTO lacks invariants and complete state | Load aggregate root for commands |
| Using two inconsistent write paths | Version, audit, and events drift | Define the command path per change type |
| Manually opening connections inside a transaction | SQL may run outside Spring's transaction | Use JdbcClient/templates with the same datasource |
| Assuming @Transactional spans every database | Multiple datasources do not become one transaction automatically | Configure proper transactions or use outbox/saga |
| Concatenating input strings into SQL | SQL injection | Bind parameters and whitelist identifiers |
| Mapping JOINs arbitrarily into aggregates | Duplicate roots/children or corrupted collections | Use DTOs and controlled mappers/extractors |
| Testing only with H2 | Misses dialect differences | Integration test against target database |
| Choosing libraries by feature count | Increases complexity and operational cost | Pick based on SQL needs and team capability |

## 18. Process for Introducing a SQL Tool into a Project

When a use case needs JdbcClient or another library, proceed in order:

**Step 1 — Identify purpose.** Is this a query/read model or a data-mutating command?

**Step 2 — Check aggregate boundaries.** Does the operation require domain invariants and root behavior?

**Step 3 — Choose the minimal suitable tool.** Use JdbcClient for direct SQL; choose jOOQ/MyBatis/Jdbi when concrete benefits justify it.

**Step 4 — Define interfaces at the right layer.** The application layer depends on query/command ports, not SQL library APIs.

**Step 5 — Write the adapter.** Keep SQL, mapping, parameter binding, and database-specific behavior in infrastructure.

**Step 6 — Define transactions.** Share the datasource/transaction manager when coordinating with Spring Data JDBC.

**Step 7 — Guard commands.** Check authorization, invariants, versions/locks, FKs, affected row counts, and auditing.

**Step 8 — Test real SQL.** Verify dialect, mapping, rollback, and concurrency.

**Step 9 — Measure performance.** Inspect execution plans, row counts, round-trips, memory, and latency.

**Step 10 — Document write paths.** Clarify which adapter may modify each table and how version/events/caches stay synchronized.

~~~text
New use case
    |
    v
Read or write?
    |
    +---- Read ----------------------------+
    |                                      |
    v                                      v
DTO / projection needed?             Full aggregate needed?
    |                                      |
    v                                      v
JdbcClient / SQL library              Spring Data repository
query adapter                         and domain behavior
    |                                      |
    +------------------+-------------------+
                       |
                       v
             Same transaction if needed
                       |
                       v
             Test SQL and mapping
                       |
                       v
             Measure actual performance
~~~

## 19. Reasoning Exercises

**Scenario A — Revenue dashboard**

A dashboard needs monthly totals by order status. Should you load all SalesOrders with OrderLines and sum them in Java?

**Hint:** Usually no. An aggregate query via JdbcClient returning DTOs reduces data transfer and object instantiation.

**Scenario B — Deleting an order line**

An order line can only be deleted when the order is in DRAFT status. Can JdbcClient perform a direct DELETE?

**Hint:** Yes, if it is an explicitly designed command, provided it checks status, root ID, version/lock, FKs, transactions, and affected row count. For normal business operations, a domain method on the root is usually cleaner.

**Scenario C — Query using jOOQ**

An application service needs a report without depending on DSLContext. Where should DSLContext live?

**Hint:** Inside an infrastructure adapter. The application service invokes a query port interface and receives DTOs.

**Scenario D — Two datasources**

A repository uses database A while JdbcClient uses database B. Does a standard @Transactional ensure both databases commit together?

**Hint:** No. You need a transaction coordinator/distributed transaction or an appropriate outbox/saga design.

**Scenario E — Dynamic sorting**

A client sends sortField = "created_at desc; drop table...". Can this string be bound as a parameter in ORDER BY?

**Hint:** Identifiers and sort expressions cannot be bound as values. Use a whitelist of allowed column names and sort directions.

**Scenario F — Using a DTO for updates**

An OrderSummary has id, status, and totalAmount. Can it substitute for SalesOrder when calling repository save?

**Hint:** No. Read DTOs do not represent the full aggregate and do not enforce invariants. Load the root to execute commands.

## 20. Key Takeaways

| Component | Responsibility |
|---|---|
| Aggregate root | Protects invariants and child entity lifecycles |
| Spring Data JDBC repository | Saves/loads aggregates per mapping |
| JdbcClient | Executes JDBC SQL via a fluent API |
| Query adapter | Returns DTOs/read models for screens and reports |
| Command adapter | Executes controlled SQL writes |
| Repository fragment | Adds SQL capabilities to an existing repository |
| jOOQ / MyBatis / Jdbi | Specialized SQL tools placed in infrastructure |
| @Transactional | Coordinates operations sharing a transaction manager |
| Version predicate / lock | Protects direct SQL against concurrent updates |
| Parameter binding | Protects input values and data types |
| Integration test | Verifies SQL, dialect, transactions, and mapping |

**Choose the tool for the job and keep it inside the data access layer.** Spring Data JDBC continues managing aggregates and domain invariants; JdbcClient or another SQL library handles specialized queries, reports, or commands through adapters. When multiple tools participate in one use case, share the transaction manager if atomicity is required, and ensure every write path respects versioning, foreign keys, auditing, and aggregate events.

## References

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcClient, JdbcTemplate, named parameters, row mapping, and JDBC access.
- [Spring Data Relational — Custom Repository Implementations](https://docs.spring.io/spring-data/relational/reference/repositories/custom-implementations.html): repository fragments and custom implementations.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): @Transactional, transaction boundaries, propagation, and rollback.
- [jOOQ Manual](https://www.jooq.org/doc/latest/manual/): SQL DSL, code generation, and mapping.
- [MyBatis Documentation](https://mybatis.org/mybatis-3/): mappers, SQL mapping, and integration.
- [Jdbi Documentation](https://jdbi.org/): SQL objects, parameter binding, and row mapping.
