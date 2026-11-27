# Keeping Complex Read Models in SQL or Dedicated Libraries

When migrating an application to **Spring Data JDBC**, you do not have to rewrite every read query as a repository method or force every result into an aggregate. Spring Data JDBC fits aggregate-root persistence; search screens, reports, and multi-table read queries can continue using explicit SQL or a dedicated library such as **JdbcTemplate, MyBatis, or jOOQ**.

This approach enables incremental migration: Spring Data JDBC manages aggregates moved to the new model, while complex read models continue to be served by existing queries. The key is defining clear read/write boundaries, keeping transactions and mappings consistent, and testing data paths that span both technologies.

This lesson explains why complex read queries should often stay as-is, how to pick the right tool, how to organize dedicated read models, how to coordinate with Spring transactions, and how to plan migrations without creating two conflicting sources of persistence rules.

## 1. Not Every Read Query Needs to Materialize an Aggregate

Spring Data JDBC organizes data around aggregate roots. Repositories typically return an aggregate mapped from one root and its owned entities. This suits use cases that read and mutate domain state while enforcing invariants.

An administrative screen may need data from multiple aggregates or tables:

- Order number and status.
- Customer name.
- Payment status.
- Assigned staff name.
- Total line item count.
- Total amount and shipping details.

That result is a **read model** serving the screen, not necessarily an aggregate to be saved. Materializing full `PurchaseOrder`, `Customer`, `Payment`, and child collections just to render a table can over-fetch data and make queries hard to optimize.

A SQL join can fetch the exact projection:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    c.display_name AS customer_name,
    p.payment_status,
    o.total,
    COUNT(l.line_no) AS line_count
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN payments p ON p.order_id = o.id
LEFT JOIN order_lines l ON l.order_id = o.id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
GROUP BY
    o.id,
    o.order_number,
    o.status,
    c.display_name,
    p.payment_status,
    o.total
ORDER BY o.created_at DESC, o.id ASC;
~~~

This query yields a flat result set built for reporting. It does not need to become a domain object graph.

## 2. Separating the Write Model and Read Model

A useful organizational pattern during migration is separating two responsibilities:

- **Write model**: uses aggregate roots, domain rules, optimistic locking, and Spring Data JDBC repositories to modify data.
- **Read model**: uses projections/DTOs tailored to screens, reports, or search needs; queried via SQL or dedicated libraries.

~~~mermaid
flowchart TD
    A[Controller / API / Job] --> B[Application Service]
    B --> C[Write path]
    B --> D[Read path]
    C --> E[Spring Data JDBC Repository]
    E --> F[Aggregate Root]
    D --> G[JdbcTemplate / MyBatis / jOOQ]
    G --> H[DTO / Read Projection]
    F --> I[(Shared Database)]
    H --> I
~~~

This is a separation of concerns at the application level. It does not require two separate databases and does not imply event sourcing. Both paths can read/write the same database, schema, and transaction manager.

Examples:

| Use Case | Good Tool to Start With |
|---|---|
| Create an order and its line items | Spring Data JDBC |
| Change status per domain rules | Spring Data JDBC |
| Load order by ID for business logic | Spring Data JDBC |
| Search table joining customers and payments | SQL projection or MyBatis |
| Monthly revenue reports | SQL, jOOQ, or MyBatis |
| Multi-table summary dashboard | Dedicated read model |
| Specialized bulk updates | Controlled SQL/JDBC, if invariants and versions are protected |

There is no need to force every query into one abstraction. Pick the tool based on result shape and use-case responsibility.

## 3. Why Keep Complex Read SQL During Migration?

A legacy application often has read queries tuned over years. They may use:

- Multi-table JOINs and subqueries.
- Common Table Expressions (CTEs).
- Window functions.
- `GROUP BY`, `HAVING`, and aggregate functions.
- Full-text search or JSON operators.
- Stored procedures or database views.
- Dynamic filters and multi-column sorting.
- Offset or keyset pagination.
- DBMS-specific hints and syntax.
- Narrow projections fetching only a subset of columns.

Rewriting those queries alongside persistence migration increases change scope and makes it harder to isolate regressions if performance or results shift.

Keeping proven read queries provides several benefits:

1. Reduces the number of use cases changed in a single wave.
2. Preserves known execution plans and semantics.
3. Lets you focus on migrating the write path to the aggregate model.
4. Enables comparing old/new outputs with contract tests.
5. Avoids turning read models into aggregates just to fit CRUD repositories.

Keeping legacy SQL does not mean preserving every legacy detail forever. Wrap queries inside adapters with clear contracts, measure performance, and migrate later only with concrete justification.

## 4. Designing Dedicated DTOs for Read Models

Do not reuse aggregate roots as the return type for every screen. A DTO representing the exact query output decouples the UI from the domain model.

Example:

~~~java
import java.math.BigDecimal;

public record OrderSearchRow(
        Long orderId,
        String orderNumber,
        String orderStatus,
        String customerName,
        String paymentStatus,
        BigDecimal total,
        Long lineCount
) {}
~~~

Read service:

~~~java
public interface OrderSearch {
    List<OrderSearchRow> search(OrderSearchCriteria criteria);
}
~~~

Criteria:

~~~java
import java.time.Instant;

public record OrderSearchCriteria(
        String status,
        Instant fromTime,
        Instant toTime,
        String customerName,
        int page,
        int size
) {}
~~~

The DTO holds only data needed for the query. If a screen needs an extra column, you can update the projection and mapper without changing the `PurchaseOrder` aggregate.

A read model may include aggregated values or formatted display fields. Never pass such a DTO into `repository.save` as if it were a full aggregate.

## 5. Choosing Tools Based on SQL Complexity

No single tool fits every query.

| Tool | Best When | Costs to Weigh |
|---|---|---|
| Spring Data JDBC derived query | Simple property-based predicates | Limited query expressiveness |
| Spring Data JDBC `@Query` | Moderate custom SQL with simple result mapping | Hand-written SQL remains DBMS-specific |
| `JdbcTemplate` | Need direct control over SQL and `RowMapper` | Manual mapping and query structure management |
| `NamedParameterJdbcTemplate` | Explicit SQL queries with many parameters | Managing dynamic fragments and mappings |
| MyBatis | Many mappers, dynamic SQL, `resultMap`, or legacy SQL | Maintaining mappers, `TypeHandler`s, and caches |
| jOOQ | Type-safe SQL DSL and complex queries | Managing code generation, setup, and licensing editions |
| Database view | Stable read query reused in multiple places | Schema/view migrations and portability |
| Stored procedure | SQL logic must run close to DB or is a legacy contract | Harder to test and migrate if DBMS-bound |

Start with the simplest tool that meets the requirements. If a query can be expressed cleanly with `JdbcTemplate` and a `RowMapper`, there is no need to add MyBatis or jOOQ just for a `SELECT`.

## 6. Keeping Queries in JdbcTemplate

`JdbcTemplate` fits when explicit SQL is needed but the number of mappers is modest.

`RowMapper`:

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

public class OrderSearchRowMapper
        implements RowMapper<OrderSearchRow> {

    @Override
    public OrderSearchRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new OrderSearchRow(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("order_status"),
                rs.getString("customer_name"),
                rs.getString("payment_status"),
                rs.getBigDecimal("total"),
                rs.getLong("line_count")
        );
    }
}
~~~

Read adapter:

~~~java
@Repository
public class JdbcOrderSearch implements OrderSearch {

    private final NamedParameterJdbcTemplate jdbc;

    public JdbcOrderSearch(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<OrderSearchRow> search(OrderSearchCriteria criteria) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                o.status AS order_status,
                c.display_name AS customer_name,
                p.payment_status,
                o.total,
                COUNT(l.line_no) AS line_count
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN payments p ON p.order_id = o.id
            LEFT JOIN order_lines l ON l.order_id = o.id
            WHERE (:status IS NULL OR o.status = :status)
              AND o.created_at >= :from_time
              AND o.created_at < :to_time
            GROUP BY
                o.id, o.order_number, o.status,
                c.display_name, p.payment_status, o.total
            ORDER BY o.id DESC
            """;

        var parameters = new MapSqlParameterSource()
                .addValue("status", criteria.status())
                .addValue("from_time", criteria.fromTime())
                .addValue("to_time", criteria.toTime());

        return jdbc.query(sql, parameters, new OrderSearchRowMapper());
    }
}
~~~

This is a structural example. Real queries must address paging, sorting, null semantics, and DBMS SQL differences. If `criteria` has many optional filters, assemble fixed fragments and bind values rather than writing a single broad `OR` predicate for every option.

Isolating queries into an adapter keeps application services decoupled from `JdbcTemplate` and lets implementations change later.

## 7. Keeping Queries in MyBatis

MyBatis fits when there are many SQL statements, dynamic SQL, or complex result mappings. A mapper interface defines the contract:

~~~java
@Mapper
public interface OrderSearchMapper {
    List<OrderSearchRow> search(OrderSearchCriteria criteria);
}
~~~

An XML mapper can hold the SQL:

~~~xml
<mapper namespace="com.example.orders.read.OrderSearchMapper">

  <select id="search" resultType="com.example.orders.read.OrderSearchRow">
    SELECT
      o.id AS orderId,
      o.order_number AS orderNumber,
      o.status AS orderStatus,
      c.display_name AS customerName,
      p.payment_status AS paymentStatus,
      o.total AS total
    FROM purchase_orders o
    JOIN customers c ON c.id = o.customer_id
    LEFT JOIN payments p ON p.order_id = o.id
    <where>
      <if test="status != null and status != ''">
        AND o.status = #{status}
      </if>
      <if test="fromTime != null">
        AND o.created_at >= #{fromTime}
      </if>
      <if test="toTime != null">
        AND o.created_at < #{toTime}
      </if>
    </where>
    ORDER BY o.id DESC
  </select>

</mapper>
~~~

MyBatis supports `resultMap` when DTOs require constructor mapping, nested objects, or collections. For flat projections, `resultType` with explicit aliases is usually sufficient.

Use parameter binding for values. Never interpolate request input directly into SQL structure. Dynamic identifiers, sort columns, and sort directions must come from a whitelist.

If the application already has stable MyBatis mappers, keep them during migration and only swap the necessary write paths.

## 8. Keeping Queries in jOOQ

jOOQ provides a structured SQL DSL in Java. When schema code generation is used, tables and columns can be referenced via Java types instead of raw column strings.

Conceptual example:

~~~java
public List<OrderSearchRow> search(OrderSearchCriteria criteria) {
    return dsl
            .select(
                    PURCHASE_ORDERS.ID,
                    PURCHASE_ORDERS.ORDER_NUMBER,
                    CUSTOMERS.DISPLAY_NAME,
                    PURCHASE_ORDERS.TOTAL
            )
            .from(PURCHASE_ORDERS)
            .join(CUSTOMERS)
                .on(CUSTOMERS.ID.eq(PURCHASE_ORDERS.CUSTOMER_ID))
            .where(PURCHASE_ORDERS.STATUS.eq(criteria.status()))
            .fetch(record -> new OrderSearchRow(
                    record.get(PURCHASE_ORDERS.ID),
                    record.get(PURCHASE_ORDERS.ORDER_NUMBER),
                    null,
                    record.get(CUSTOMERS.DISPLAY_NAME),
                    null,
                    record.get(PURCHASE_ORDERS.TOTAL),
                    null
            ));
}
~~~

Generated table/field names depend on your project's package and codegen configuration. This illustrates the DSL style; real queries require full joins, filters, and mappings.

jOOQ reduces column typo bugs in code and supports dialect rendering, though it does not eliminate all schema or semantic differences. Configure `DSLContext` with a Spring-compatible `DataSource`/transaction provider if it must participate in Spring Data JDBC transactions.

## 9. Package Layout to Separate Read Paths from Aggregate Persistence

One possible layout:

~~~text
com.example.orders
  domain/
    PurchaseOrder.java
    OrderLine.java
  application/
    OrderCommandService.java
    OrderSearchService.java
  persistence/
    aggregate/
      PurchaseOrderRepository.java
    read/
      OrderSearch.java
      OrderSearchRow.java
      JdbcOrderSearch.java
      OrderSearchMapper.java
      OrderSearchMapper.xml
~~~

You do not need these exact package names. The goal is making roles immediately obvious:

- Aggregate repositories own domain write operations.
- Read adapters own queries and projections.
- Application services coordinate use cases.
- DTOs are not mistaken for aggregate roots.
- SQL is grouped where it can be reviewed and tested.

If a read adapter serves reporting only, names like `OrderReportQuery` or `OrderSearchReadRepository` communicate intent better than a generic repository name.

## 10. Do Not Use Read Projections to Update Aggregates

A join query may return an `OrderSearchRow` combining fields from multiple tables. That DTO is not the complete state of `PurchaseOrder`.

Do not do this:

~~~java
OrderSearchRow row = orderSearch.search(criteria).getFirst();

// Do not convert a composite DTO directly into an aggregate to save.
purchaseOrderRepository.save(convertToPurchaseOrder(row));
~~~

The DTO may omit versions, child collections, invariants, or domain properties. Reconstructing an aggregate from a projection can overwrite existing data with nulls or defaults.

When a use case needs to mutate an order:

1. Load the aggregate root via its repository.
2. Invoke domain behavior to update state.
3. Save the aggregate via its repository.
4. Re-read the read projection if the response needs joined data.

Keeping read and write models separate prevents updating domain state from an incomplete view of the data.

## 11. Shared Transactions Between Spring Data JDBC and Query Adapters

If a use case writes an aggregate and executes extra SQL in the same transaction, the tools can coordinate through Spring transactions when configured properly.

Key requirements:

- Share the same Spring-managed `DataSource`.
- The transaction manager manages that `DataSource`.
- `JdbcTemplate`/`NamedParameterJdbcTemplate` obtains connections through Spring JDBC.
- MyBatis uses MyBatis-Spring integration such as `SqlSessionTemplate`/mapper proxies.
- jOOQ is configured with a transaction-aware connection/provider.
- Business methods run through a Spring transaction proxy.

Application service example:

~~~java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository orders;
    private final OrderAuditWriter auditWriter;

    public OrderCommandService(
            PurchaseOrderRepository orders,
            OrderAuditWriter auditWriter
    ) {
        this.orders = orders;
        this.auditWriter = auditWriter;
    }

    @Transactional
    public PurchaseOrder approve(Long id) {
        PurchaseOrder current = orders.findById(id).orElseThrow();

        PurchaseOrder approved = current.approve();

        PurchaseOrder saved = orders.save(approved);

        auditWriter.recordApproval(saved.id(), saved.version());

        return saved;
    }
}
~~~

If `auditWriter` uses `JdbcTemplate`/MyBatis/jOOQ configured on the same `DataSource` and transaction manager, the audit write commits or rolls back together with the aggregate save.

If the query adapter uses a different `DataSource`, read replica, or transaction manager, never assume `@Transactional` creates an atomic transaction across data sources.

## 12. Read-After-Write and Consistency

When writing an aggregate and immediately reading a read model, the outcome depends on where the query executes:

- Same primary database and same transaction: the query sees uncommitted writes from that transaction per isolation/database semantics.
- Same primary but separate transaction: sees only committed data per isolation level.
- Read replica: may not yet have received replication events and may return stale data.
- Cache: may return a stale snapshot if not invalidated.
- Materialized view: may require scheduled or explicit refreshes.

For example, a use case creates an order and returns the detail screen. If the read adapter queries a lagging replica, the response might miss the newly created order. You can return the saved aggregate, route that read to the primary, or design an explicit consistency contract.

Never assume a read query run through another library is automatically consistent just because it hits the same database server.

## 13. Caching When Multiple Tools Read and Write

If Spring Data JDBC writes to a table while MyBatis or another read adapter caches results, the cache will not automatically know the data changed.

Possible caches:

- MyBatis local `SqlSession` cache.
- MyBatis second-level cache by mapper namespace, if enabled.
- Application service caches.
- Distributed caches.
- API gateway or client caches.
- Materialized views or asynchronously updated read tables.

If data is written through multiple paths, establish shared invalidation rules. Do not assume an update in one mapper clears another mapper's cache, or that a repository save refreshes a distributed cache.

Approach:

1. Enable caching only when benefits are measured.
2. Identify every writer for the data.
3. Define invalidation events or mechanisms.
4. Test read-after-write behavior across each adapter.
5. Consider an outbox if invalidation must be emitted reliably after commit.

Without a clear need, avoid caching read models modified frequently through multiple persistence paths.

## 14. Database-Specific SQL and Portability

Existing read queries may use vendor features such as:

- JSON operators.
- CTEs or recursive queries.
- Window functions.
- Full-text search.
- Pagination syntax.
- Optimizer hints.
- Stored procedures.
- DBMS-specific functions or types.

Keeping existing queries during migration preserves behavior while keeping database coupling. If the application must support multiple DBMS engines, document which queries are portable and which are vendor-specific.

Options:

- Use standard SQL syntax for common queries.
- Use database views to encapsulate stable projections.
- Split queries per DBMS where differences genuinely require it.
- Use jOOQ dialect rendering when suitable.
- Use custom repository adapters to isolate specialized SQL.
- Run integration tests against every supported DBMS.

Do not test queries only on H2 if production runs PostgreSQL, MySQL, SQL Server, or Oracle. Data types, JSON, time zones, collations, and execution plans can all differ.

## 15. Dynamic Filters and Security

Complex read queries often support dynamic filters and sorting. Bind values using parameters; whitelist identifiers.

`NamedParameterJdbcTemplate` example:

~~~java
StringBuilder sql = new StringBuilder("""
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE 1 = 1
    """);

MapSqlParameterSource parameters = new MapSqlParameterSource();

if (criteria.status() != null) {
    sql.append(" AND status = :status");
    parameters.addValue("status", criteria.status());
}

if (criteria.fromTime() != null) {
    sql.append(" AND created_at >= :fromTime");
    parameters.addValue("fromTime", criteria.fromTime());
}
~~~

For dynamic sorting, map client choices to fixed column names:

~~~java
String sortColumn = switch (requestedSort) {
    case "created" -> "created_at";
    case "number" -> "order_number";
    case "total" -> "total";
    default -> throw new IllegalArgumentException("Unsupported sort");
};
~~~

Never concatenate client-supplied column names directly into SQL. Parameter binding cannot substitute table/column names or keywords.

For multi-tenant data, derive tenant predicates from the authenticated security context rather than trusting an arbitrary tenant ID sent by the client.

## 16. Preserving the Legacy Query Contract

During migration, a query is more than SQL. It carries a contract covering:

- Result field names and data types.
- Nullability.
- Sort ordering.
- Pagination boundaries.
- Empty filter handling.
- Time zones and date ranges.
- Access permissions and tenant filters.
- Aggregation and rounding rules.
- Handling duplicate rows from JOINs.
- Behavior when zero rows match.

For instance, two queries may both return orders, yet one sorts by `created_at` then `id` while the other sorts only by `created_at`. When timestamps collide, page ordering can change.

Write contract tests for outputs, not just tests checking that SQL runs without error. When replacing an old mapper with a new adapter, compare identical inputs and fixtures to verify matching output semantics.

## 17. Partial Migration: Keep Read Queries, Migrate Write Paths

You do not need to migrate the entire application at once. One viable path:

~~~mermaid
flowchart TD
    A[Current system] --> B[Encapsulate read SQL in adapters]
    B --> C[Add contract and integration tests]
    C --> D[Migrate one aggregate write to Spring Data JDBC]
    D --> E[Verify read-after-write and transactions]
    E --> F[Migrate subsequent write use cases]
    F --> G[Evaluate legacy queries and optimize individually with metrics]
~~~

Concrete steps:

1. **Inventory existing queries:** classify aggregate CRUD, searches, reports, bulk operations, and specialized SQL.
2. **Identify owners:** each aggregate has one canonical write path; read adapters only read unless specifically required.
3. **Encapsulate legacy SQL:** move queries into mappers/DAOs/service adapters instead of letting controllers invoke them directly.
4. **Define DTO/read contracts:** specify columns, types, nullability, and sorting clearly.
5. **Write tests before changing code:** verify legacy query results on the target database.
6. **Migrate write paths per aggregate:** use Spring Data JDBC repositories and domain behavior.
7. **Verify transactions:** confirm repositories and SQL adapters roll back together when required.
8. **Verify read-after-write:** check primary, replicas, and caches.
9. **Monitor performance:** measure latency, rows read, execution plans, and connection usage.
10. **Remove legacy code intentionally:** delete old queries only once the new adapter meets the contract and is verified.

Do not change all queries, schemas, and transaction configurations simultaneously unless necessary. Small changes make it easy to pinpoint which change caused a defect.

## 18. Structuring Interfaces for Swappable Implementations

Application services should depend on use-case interfaces rather than directly on a SQL library:

~~~java
public interface OrderSearch {
    Page<OrderSearchRow> search(
            OrderSearchCriteria criteria,
            Pageable pageable
    );
}
~~~

The initial implementation can use MyBatis:

~~~java
@Repository
public class MyBatisOrderSearch implements OrderSearch {
    private final OrderSearchMapper mapper;

    public MyBatisOrderSearch(OrderSearchMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Page<OrderSearchRow> search(
            OrderSearchCriteria criteria,
            Pageable pageable
    ) {
        // Call mapper to fetch content and count per query contract.
        throw new UnsupportedOperationException("Illustrative example");
    }
}
~~~

Later, it can be swapped for `JdbcTemplate` or jOOQ without altering controllers or application services, provided the contract stays unchanged.

The sample implementation intentionally leaves content/count fetching illustrative because paginated SQL and count queries depend on the specific query. In real code, never leave `UnsupportedOperationException`; implement both the data query and count query, or use cursor/keyset pagination if that is the contract.

There is no need to wrap every tiny `SELECT` in an interface. Abstractions pay off when isolating technology or providing genuine multi-implementation/testing seams.

## 19. Count Queries and Pagination

A paginated read model typically requires two queries:

- A query fetching the page's content.
- A query counting total matching rows if the API exposes a total.

With one-to-many JOINs, a naive count can count duplicate rows unless counting by root ID or using a `DISTINCT` subquery. Example:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines l ON l.order_id = o.id
WHERE o.status = :status;
~~~

The content query may use `GROUP BY` or window functions; the count query must maintain the same filter semantics. Do not copy the content query verbatim and simply drop `LIMIT` if it contains complex `GROUP BY`/`HAVING` clauses.

For large datasets, consider `Slice`/cursor or keyset pagination rather than always computing totals. API contracts should state clearly whether totals are included.

## 20. Read Queries Can Use Views or Read Tables

When a projection is shared by many screens and rarely changes, a database view can encapsulate the join logic:

~~~sql
CREATE VIEW order_search_view AS
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    c.display_name AS customer_name,
    o.total
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Adapters can query the view as a read source. Standard views usually reflect current data on query, whereas materialized views may need refreshes and carry staleness lag.

If an aggregate query is very expensive, you can maintain a read table/projection updated by application events or jobs. That requires defining a consistency model, retries, rebuilds, and duplicate-event handling.

Do not introduce a separate read model table just because you can. Use one only when query cost or complexity justifies maintaining a copy of the data.

## 21. Transactions and Multiple DataSources

An application may read from primary and replica instances or multiple databases. Distinguish clearly:

- Same `DataSource` and transaction manager: JDBC operations can share a single Spring transaction.
- Two separate `DataSource`s: a standard local JDBC transaction does not automatically make them atomic.
- Read replica: may return stale data after a write due to replication lag.
- External search engine: requires its own consistency strategy, usually updated asynchronously.

If a use case writes an aggregate and also writes to another database, never assume plain `@Transactional` guarantees atomicity across both sources. Use an appropriate transaction coordinator or an outbox/saga design as business rules require.

If a complex read query only needs committed data, querying a replica may make sense. If the response must immediately reflect a write just performed, read from the primary or use a read-your-writes strategy.

## 22. Measuring Performance and Observing Read Models

Keeping legacy SQL can preserve performance, yet you should continue measuring after modifying write paths or schemas.

Monitor:

- p50, p95, and p99 latency.
- Rows read and columns returned.
- Query count per request.
- Execution plans and index usage.
- Database CPU, I/O, and lock waits.
- Active/pending connection pool usage.
- Cache hit/miss ratios if caching is enabled.
- Replica lag when reading from replicas.
- Timeout and query cancellation rates.

A join query may be fast on small datasets yet slow down as cardinality grows. Run `EXPLAIN`/`EXPLAIN ANALYZE` for your database, verify indexes, and measure on representative data.

Do not log sensitive parameter values in production solely to observe queries. Use metrics, tracing, and properly masked logging.

## 23. Testing When Keeping Read Queries and Migrating Write Paths

An integration test suite should protect contracts across both paths:

| Test | What to Verify |
|---|---|
| Read query baseline | Legacy query returns expected DTOs, filters, and sorting |
| Aggregate save | Spring Data JDBC saves root/children per mapping |
| Read-after-write | Read adapter sees new data per consistency contract |
| Transaction rollback | Aggregate write and auxiliary SQL roll back together when sharing a transaction |
| Versioning | Repository updates preserve optimistic locking |
| Pagination | Content/count stay consistent and sorting is deterministic |
| Nulls/filters | Null, empty, and date-boundary filters have clear semantics |
| Authorization | Tenants/users read only permitted data |
| DB portability | Queries run on every officially supported DBMS |
| Caching | Read adapter does not return stale snapshots after another writer updates |
| Migrations | New schema remains compatible with legacy queries |

You can use Testcontainers to run a production-like database engine and the real JDBC driver. H2 works for fast unit checks, but does not substitute for testing DBMS-specific features.

## 24. Common Pitfalls During Migration

| Symptom | Common Cause | Resolution |
|---|---|---|
| Trying to build huge aggregates for report screens | Confusing read models with write aggregates | Use DTOs/projections and SQL joins |
| New query returns too few or too many rows | Different `JOIN`, `GROUP BY`, or `DISTINCT` mapping from legacy query | Compare contracts on representative fixtures |
| Read-after-write returns stale data | Reading from replica or uninvalidated cache | Read primary/read-your-writes or update cache invalidation |
| Repository and mapper fail to roll back together | Different `DataSource` or transaction manager | Configure shared Spring transaction infrastructure |
| SQL passes on old DB but fails on new DB | Query uses vendor-specific syntax | Split queries by dialect and test target DBMS |
| Pagination count exceeds content | One-to-many JOIN duplicates rows | Use `COUNT(DISTINCT root_id)` or a subquery |
| DTO fields are null | Alias/result mapping mismatch | Use explicit aliases/`resultMap` |
| SQL update bypasses version | Mapper does not check optimistic lock | Keep mapper read-only or implement the version contract explicitly |
| Cache returns stale data after repository save | Writer and cache owner are separate | Design shared invalidation |
| Migration causes performance regression | Different query plan, index, or cardinality | Inspect execution plans and p95/p99 |
| Dynamic query has SQL injection | Concatenating identifiers/values from request | Bind values and whitelist SQL structures |
| Two models write the same aggregate | Unclear ownership | Pick one canonical write path |

## 25. Decision Matrix: Keep or Rewrite a Query?

| Condition | Recommendation |
|---|---|
| Complex, well-tuned SQL with good tests | Keep inside an adapter during migration |
| Multi-table join query serving only a DTO | Keep as a read projection |
| Simple query matching aggregate properties | Consider derived query or `@Query` |
| Legacy SQL is DBMS-specific and app only supports that DBMS | Can keep; document the dependency |
| App must support multiple DBMS engines | Use portable syntax or per-DB query variants |
| Unmaintainable query lacking tests | Put in a separate refactor scope; add contract tests first |
| Heavy query on rarely changing data | Consider views/materialized views or a read model |
| Needs type-safe DSL and multiple dialects | Consider jOOQ |
| Many dynamic mappers and `resultMap`s | Consider MyBatis |
| Short SQL, small count | `JdbcTemplate`/`NamedParameterJdbcTemplate` may suffice |

Base the decision on complexity, performance, testability, and team familiarity. Do not switch technologies merely to standardize library names.

## 26. Practice Exercise: Migrate Write Path, Keep Read Path

Suppose a legacy application has an order search query joining customers and payments.

Steps:

1. Write contract tests for the current query: filters, sorting, pagination, nulls, and DTO fields.
2. Wrap the query inside an `OrderSearch` interface/adapter.
3. Keep the existing SQL/MyBatis/jOOQ implementation intact.
4. Create the `PurchaseOrder` aggregate and Spring Data JDBC repository.
5. Migrate an order-creation use case to `repository.save`.
6. After saving, call the read adapter to fetch the projection by ID.
7. Confirm read-after-write on the primary and within the same transaction where needed.
8. Intentionally trigger a failure in an auxiliary audit/side-effect DB step to verify rollback when sharing a transaction.
9. Run the query against a production-like dataset and compare p95/p99.
10. Rewrite the read query only if measurable benefits arise or query contracts change.

Document what was migrated, what still uses legacy SQL, the `DataSource`/transaction manager of each adapter, and supported DBMS engines. This record will guide subsequent migration waves.

## 27. Rules to Remember

- Spring Data JDBC fits aggregate write models; complex read queries can stay in SQL or dedicated libraries.
- Never construct full aggregates solely to serve a screen needing a multi-table projection.
- Separate DTOs/read models from aggregate roots and never use projections to save domain state.
- `JdbcTemplate` fits explicit SQL; MyBatis fits mappers and dynamic SQL; jOOQ fits type-safe SQL DSLs.
- Keeping legacy queries inside adapters lets you migrate write paths incrementally and reduces regression scope.
- Share the same `DataSource` and transaction manager when repositories and query adapters must commit/roll back together.
- Reading from replicas or caches may not show new writes immediately; define a read-your-writes contract.
- Each aggregate should have one canonical write path; custom SQL writing an aggregate must protect versions and invariants.
- Custom SQL must bind values, whitelist identifiers, and be tested per DBMS.
- Preserve query contracts: fields, types, nullability, filters, sorting, pagination, and authorization.
- Test read-after-write, rollbacks, caching, count queries, and migrations against the target database.
- Rewrite queries only when there is a clear benefit; do not change technologies just for stack uniformity.

When migrating to Spring Data JDBC, let aggregate repositories own domain mutations and keep complex read queries where they are expressed most clearly. A read adapter with stable DTOs and contracts lets teams migrate write paths step by step without rewriting reports, searches, and tuned SQL. Throughout, safeguard transactions, consistency, mappings, access control, and testability against a real database.

## References

- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html)
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [MyBatis 3 Reference](https://mybatis.org/mybatis-3/)
- [MyBatis-Spring Reference](https://mybatis.org/spring/)
- [jOOQ Manual](https://www.jooq.org/doc/latest/manual/)
