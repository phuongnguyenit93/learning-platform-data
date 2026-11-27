# Choosing Projections, SQL JOINs, or Single Query Loading Based on Measurements

In **Spring Data Relational JDBC**, there is no single optimal data-reading strategy for every use case. A list screen may need only a few columns, whereas a business command needs the entire aggregate root and its owned entities. A report may need to aggregate data across multiple tables. Using the same loading mechanism for all three often increases SQL statement counts, rows sent over the network, or JVM object allocations.

Three main approaches:

- **Projection/read model:** queries only the columns needed and maps them to DTOs; suitable for lists, reports, and read-only APIs.
- **SQL JOIN:** combines data from multiple tables in one query; effective for to-one relationships or a single collection with bounded cardinality, though joining multiple collections can create duplicate rows or Cartesian products.
- **Single Query Loading:** a Spring Data JDBC feature introduced in version 3.2 that loads aggregates via a single SQL query under supported conditions. Current documentation still describes this feature as experimental and notes limitations around mappings, dialects, and repository methods.

Do not choose an approach merely because it generates fewer SQL statements. Measure response latency, returned row counts, result payload size, database CPU, JVM memory, and scalability under realistic load.

## 1. Start from the Data the Use Case Actually Needs

Suppose an application has this aggregate:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    private String status;

    private LocalDateTime createdAt;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    // constructor, getters, domain methods...
}
~~~

Each `OrderLine` has `product`, `quantity`, and `unitPrice`. An admin page may only need order ID, customer name, status, creation timestamp, line count, and total amount. That screen does not need every individual `OrderLine`, does not need domain behavior on `PurchaseOrder`, and does not need every column of the aggregate.

Conversely, a confirm-order use case may need all order lines to check invariants, recompute totals, update status, and save the aggregate. A DTO with only a few fields will not suffice for that business logic.

| Need | Required data | Usually suitable read approach |
|---|---|---|
| Modify aggregate or run domain behavior | Aggregate root and components needed for invariants | Repository load aggregate |
| List page / summary API | Subset of columns, possibly with count/sum | Projection DTO |
| Multi-table report | Aggregated/grouped columns by filter | SQL JOIN + aggregation + DTO |
| Read full aggregate with collections | Root and owned entities | Default loading or Single Query Loading if eligible |
| Complex custom search | Read model from custom query | Repository fragment / `NamedParameterJdbcTemplate` |

Do not use a projection merely because DTOs are smaller than entities if your code immediately reloads the full aggregate for each result afterward. Account for the total cost of the use case.

## 2. Projections in Spring Data JDBC

A projection is a result type representing only the slice of data the caller needs. With Spring Data JDBC, a clean, explicit way to build a specialized read model is writing explicit SQL and mapping the `ResultSet` to a DTO using a `RowMapper` or `ResultSetExtractor`.

Spring Data JDBC supports custom queries and custom mapping. However, do not blindly transfer every Spring Data JPA projection assumption to JDBC. With string-based queries in Spring Data JDBC, verify the exact columns required by the row mapper; custom queries returning an aggregate root may still load collections via separate queries.

### DTO for a List Screen

~~~java
public record OrderSummary(
        Long orderId,
        String customerName,
        String status,
        LocalDateTime createdAt,
        Long lineCount,
        BigDecimal totalAmount
) {}
~~~

A DTO has no persistence identity, no collections, and needs no separate CRUD repository. It is a read model tailored to a specific query.

### Using a Custom Repository Fragment

When SQL involves JOINs, GROUP BY, pagination, or dynamic filters, a repository fragment keeps the query and mapping in one place:

~~~java
public interface OrderReadOperations {

    List<OrderSummary> findSummaries(
            String status,
            int limit,
            long offset
    );
}
~~~

Implementation:

~~~java
public class OrderReadOperationsImpl implements OrderReadOperations {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReadOperationsImpl(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<OrderSummary> findSummaries(
            String status,
            int limit,
            long offset) {

        String sql = """
                SELECT
                    po.id AS order_id,
                    c.name AS customer_name,
                    po.status,
                    po.created_at,
                    COUNT(ol.id) AS line_count,
                    COALESCE(
                        SUM(ol.quantity * ol.unit_price),
                        0
                    ) AS total_amount
                FROM purchase_order po
                JOIN customer c ON c.id = po.customer_id
                LEFT JOIN order_line ol ON ol.order_id = po.id
                WHERE po.status = :status
                GROUP BY
                    po.id,
                    c.name,
                    po.status,
                    po.created_at
                ORDER BY po.created_at DESC, po.id DESC
                LIMIT :limit OFFSET :offset
                """;

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("status", status)
                .addValue("limit", limit)
                .addValue("offset", offset);

        return jdbc.query(sql, parameters, (rs, rowNum) ->
                new OrderSummary(
                        rs.getLong("order_id"),
                        rs.getString("customer_name"),
                        rs.getString("status"),
                        rs.getTimestamp("created_at").toLocalDateTime(),
                        rs.getLong("line_count"),
                        rs.getBigDecimal("total_amount")
                )
        );
    }
}
~~~

The main repository combines the fragment:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                OrderReadOperations {
}
~~~

The implementation follows the naming convention `OrderReadOperationsImpl`. Spring Data composes the fragment into the repository proxy when the interface and implementation are discovered within the appropriate scan scope.

The SQL example uses PostgreSQL/MySQL `LIMIT/OFFSET`. For other databases, substitute the corresponding paging syntax. The sort order includes `id` as a tie-breaker so pages stay deterministic when multiple orders share the same `created_at`.

**Benefits of projections:**

- Transfers only the columns needed by the DTO.
- Avoids instantiating objects for every child entity when the screen only needs counts/sums.
- Can JOIN and aggregate data from tables outside the aggregate.
- Read models can evolve with screen requirements without bloating domain aggregates.

**Costs to watch:**

- SQL and DTO mapping must be maintained alongside schema changes.
- Queries with heavy JOIN/GROUP BY clauses can consume CPU or require matching indexes.
- DTOs have no domain behavior; do not use them as objects for saving aggregates.
- If multiple read models are needed, keep each query clearly named and scoped rather than creating one giant catch-all DTO for every screen.

## 3. Using @Query with RowMapper for Projections

If you prefer keeping the query on the repository interface, Spring Data JDBC supports `@Query` with `rowMapperRef`, `rowMapperClass`, `resultSetExtractorRef`, or `resultSetExtractorClass`.

Example:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT
                po.id AS order_id,
                c.name AS customer_name,
                po.status,
                po.created_at,
                COUNT(ol.id) AS line_count,
                COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total_amount
            FROM purchase_order po
            JOIN customer c ON c.id = po.customer_id
            LEFT JOIN order_line ol ON ol.order_id = po.id
            WHERE po.status = :status
            GROUP BY po.id, c.name, po.status, po.created_at
            ORDER BY po.created_at DESC, po.id DESC
            """,
        rowMapperRef = "orderSummaryRowMapper"
    )
    List<OrderSummary> findSummaries(@Param("status") String status);
}
~~~

Register the mapper bean:

~~~java
@Configuration
public class QueryMappingConfiguration {

    @Bean
    RowMapper<OrderSummary> orderSummaryRowMapper() {
        return (rs, rowNum) -> new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("customer_name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
        );
    }
}
~~~

With this query, `@Query` returns DTOs; it does not ask Spring Data JDBC to load and assemble the entire `PurchaseOrder` aggregate.

Notes:

- String-based queries in Spring Data JDBC do not automatically rewrite SQL to apply `Pageable`, `Sort`, or `Limit` like derived queries. When paging is needed, place `LIMIT/OFFSET` and corresponding parameters directly in SQL, or use a fragment with a JDBC template.
- Named parameters in Spring Data JDBC use the `:status` syntax.
- Column names/aliases in the `ResultSet` must match the mapper.
- When using custom `RowMapper`/`ResultSetExtractor`, entity callbacks and lifecycle events do not run automatically for the mapped result; the mapper itself is responsible for constructing DTOs.
- If `@Query` returns an aggregate root with the default `RowMapper`, collection entities are still loaded by separate queries according to mapping. Writing a JOIN in SQL alone does not automatically fold collections into the aggregate in one statement.

For dynamic SQL or complex paging logic, a fragment + `NamedParameterJdbcTemplate` is usually easier to manage than a long annotation.

## 4. SQL JOIN: When Is It Effective?

JOIN lets you retrieve data from multiple tables in a single statement. Relationship cardinality determines whether the result stays compact or blows up.

### Joining a To-One Relationship

For example, an order has one Customer:

~~~sql
SELECT
    po.id,
    po.status,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.id = :id;
~~~

Each order matches at most one customer, so the JOIN generally does not multiply root rows. This is an easy win for a JOIN when the caller needs both pieces of information.

### Joining a Single To-Many Collection

If an order has many order lines:

~~~sql
SELECT
    po.id,
    po.status,
    ol.id AS line_id,
    ol.product_id,
    ol.quantity
FROM purchase_order po
LEFT JOIN order_line ol ON ol.order_id = po.id
WHERE po.id = :id;
~~~

An order with 5 lines produces 5 result rows, repeating the `purchase_order` columns. To reconstruct an aggregate or a DTO containing a child list, the application must group rows by root ID.

Do not use a naive `RowMapper` that constructs one `PurchaseOrder` per row; that creates duplicate roots. Use a `ResultSetExtractor` or custom mapper structured by an ID map if the real goal is materializing an object graph.

### Joining Multiple Collections Can Create a Cartesian Product

Suppose each order has 5 `OrderLine`s, 3 `Payment`s, and 4 `Shipment`s. Joining all three collections can produce up to 5 × 3 × 4 = 60 rows for a single order. Line, payment, and shipment fields are cross-multiplied in the output.

~~~mermaid
flowchart TD
    A["PurchaseOrder"] --> B["5 OrderLine"]
    A --> C["3 Payment"]
    A --> D["4 Shipment"]
    B --> E["JOIN all collections"]
    C --> E
    D --> E
    E --> F["Up to 60 result rows for one order"]
~~~

Impacts:

- Excessive duplicate data transferred over the network.
- Database must join and materialize many rows.
- JVM must read and deduplicate rows.
- Aggregations easily become wrong if COUNT/SUM runs over cross-multiplied rows.
- Root-level paging breaks if LIMIT applies to joined rows rather than root rows.

Therefore, do not JOIN multiple collections just to reduce query count. Compare total rows/bytes and CPU against multiple queries or Single Query Loading.

## 5. JOIN and Aggregation for Read Models

For summary screens, you often do not need to build collections in Java. Let the database compute counts/sums/groupings and return a DTO.

~~~sql
SELECT
    po.id,
    po.status,
    COUNT(ol.id) AS line_count,
    COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total_amount
FROM purchase_order po
LEFT JOIN order_line ol ON ol.order_id = po.id
WHERE po.status = :status
GROUP BY po.id, po.status
ORDER BY po.id DESC;
~~~

A few reminders:

- Use `LEFT JOIN` if orders with zero lines still need to appear.
- `COUNT(ol.id)` returns 0 for roots without children; `COUNT(*)` may return 1 because the root row still exists.
- `SUM` may return NULL when there are no children; use `COALESCE` if the DTO expects 0.
- If you JOIN another collection, `COUNT`/`SUM` can be inflated by the Cartesian product.
- If you need to aggregate multiple independent collections, aggregate each table in a subquery/CTE first and then JOIN the collapsed one-row-per-root results.

Example avoiding cross-multiplication via subqueries:

~~~sql
SELECT
    po.id,
    po.status,
    line_stats.line_count,
    line_stats.total_amount,
    payment_stats.payment_count
FROM purchase_order po
LEFT JOIN (
    SELECT
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity * unit_price) AS total_amount
    FROM order_line
    GROUP BY order_id
) line_stats ON line_stats.order_id = po.id
LEFT JOIN (
    SELECT
        order_id,
        COUNT(*) AS payment_count
    FROM payment
    GROUP BY order_id
) payment_stats ON payment_stats.order_id = po.id
WHERE po.status = :status;
~~~

Each subquery returns at most one row per `order_id`; results are not cross-multiplied across individual lines and payments. The database optimizer may choose different execution plans depending on indexes, cardinality, and statistics; measure on real data.

## 6. What Is Single Query Loading?

Spring Data JDBC added **Single Query Loading** in version 3.2. When enabled and the aggregate meets supported criteria, Spring Data JDBC can load multiple aggregates along with their collections in a single SQL SELECT.

The traditional approach loads roots first and then runs separate statements for owned entities. For multiple aggregates, collection loading can cause many round-trips and N+1 queries.

Single Query Loading leverages SQL features such as analytic/window functions to structure the result so collections can be reassembled without a raw JOIN across all collections creating a Cartesian product. Spring Data JDBC then materializes the aggregates from that result set.

Single Query Loading is an **aggregate**-loading strategy, not an arbitrary DTO projection mechanism. It targets supported `CrudRepository` find methods and must satisfy mapping/dialect limits.

### Enabling Single Query Loading

It must be enabled on `JdbcMappingContext`:

~~~java
@Configuration
@EnableJdbcRepositories
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    @Bean
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes) {

        JdbcMappingContext context =
                super.jdbcMappingContext(
                        namingStrategy,
                        customConversions,
                        jdbcManagedTypes
                );

        context.setSingleQueryLoadingEnabled(true);
        return context;
    }
}
~~~

This example uses Java configuration extending `AbstractJdbcConfiguration` to show where the mapping context is configured. In a Spring Boot application, integrate this setting into your existing Spring Data JDBC configuration; avoid registering a second `JdbcMappingContext` or overriding infrastructure beans managed by auto-configuration.

This property was introduced in Spring Data Relational 3.2. If the dialect supports it and the aggregate qualifies, Spring Data JDBC attempts to use Single Query Loading. If any condition is not met, the framework falls back to default loading.

### Current Documented Limitations

According to the Spring Data Relational 4.1 documentation:

1. Aggregates must not have **nested collections**. This limitation includes `Map`.
2. Aggregates must not use **AggregateReference** or embedded entities.
3. The dialect must support the required SQL features, including analytic/window functions. Among built-in dialects, H2 and HSQL are not supported because they lack windowing functions; the remaining built-in dialects are supported.
4. Only **CrudRepository** find methods are supported. Derived query methods and annotated query methods do not use Single Query Loading.
5. The flag must be enabled on `JdbcMappingContext`.

If conditions are not satisfied, the framework falls back to traditional loading. Current documentation still characterizes Single Query Loading as experimental; check your exact Spring Data JDBC version before relying on it in production.

Do not confuse the abbreviation for Single Query Loading with Structured Query Language. The Spring Data documentation recommends writing out the full feature name to avoid ambiguity.

## 7. When to Choose Single Query Loading?

Suitable when:

- The caller needs full aggregates, not just a DTO.
- The aggregate has direct collections but no nested collections.
- Neither `AggregateReference` nor embedded entities are used in the loaded aggregate.
- Queries go through supported `CrudRepository` find methods.
- The database dialect supports window functions and the feature works on your version.
- Measurements show that multiple statements/round-trips are the bottleneck.

Unsuitable or ineffective when:

- The screen only needs a few root columns and counts/sums.
- The query is a derived query or annotated query.
- The aggregate contains nested collections/`Map`, `AggregateReference`, or embedded entities.
- The database uses the built-in H2/HSQL dialects.
- The use case requires a report joining multiple tables outside the aggregate.
- Actual cost comes from large scans, missing indexes, network payload, or object mapping rather than round-trips.

Single Query Loading does not turn a reporting query into a DTO projection, does not replace indexes, and is not guaranteed to be faster for every workload. It changes how aggregates are loaded; measure total cost.

## 8. Comparing the Three Options

| Criterion | Projection DTO | SQL JOIN | Single Query Loading |
|---|---|---|---|
| Goal | Fetch only what caller needs | Combine data from multiple tables | Load full aggregates |
| Result | DTO/read model | DTO or manually grouped object graph | Aggregate root and owned entities |
| Query count | Typically one query for read model | Possibly one query | One query for eligible aggregate loads |
| Data transferred | Minimal if exact columns selected | Can be large due to repeated root/child columns | Cuts round-trips; framework controls result shape |
| Mapping | `RowMapper`/`ResultSetExtractor` | Custom grouping for to-many | Spring Data JDBC materialization |
| Multiple collections | Can aggregate/subquery separately | Risk of Cartesian product | Nested collections unsupported under current limits |
| Custom queries | Very suitable | Very suitable | Not used for derived/annotated queries |
| Domain behavior | DTO is not an aggregate | Depends on mapping; avoid faking aggregates | Returns aggregates suitable for domain behavior |
| Dialect | Depends on hand-written SQL | Depends on hand-written SQL | Requires dialect with window functions |
| SQL control | High | High | Framework generates SQL |

## 9. Choosing by Use Case Type

### List Pages or Summary APIs

Choose a projection DTO when the response needs only a few fields, customer name, and child aggregates. A single query with JOIN/grouping or subqueries is usually sensible. Avoid loading full aggregates for hundreds of results when domain behavior is unnecessary.

### Detail Screens Needing One Full Aggregate

Use the appropriate repository `findById`/`findAll`. If the aggregate has collections and meets constraints, try Single Query Loading. Otherwise, use default loading or a dedicated custom read query for the view.

### Commands Modifying an Aggregate

Load the aggregate via the repository to preserve the domain model, invariants, and optimistic locking. A projection DTO cannot replace the command object. Single Query Loading can reduce round-trips when loading the aggregate if eligible.

### Cross-Aggregate Reports

Use SQL JOINs, CTEs, subqueries, and aggregate functions returning DTOs. There is no need to materialize aggregate roots for reporting. Consider read replicas or materialized views for read-heavy workloads where freshness allows.

### Searches with Dynamic Filters/Sorting

Use a repository fragment with `NamedParameterJdbcTemplate` or an appropriate query builder. Whitelist sort column names; bind filter values via named parameters. Never concatenate user input into SQL identifiers.

## 10. Measure Before Choosing a Strategy

A meaningful benchmark must compare identical business outputs under identical data conditions.

| Metric | Why it is needed |
|---|---|
| SQL statement count | Spot N+1 or excessive round-trips |
| Total query duration | Know how long the database spends processing |
| End-to-end latency p50/p95/p99 | Reflect real experience, especially under load |
| Result row count | Detect JOINs multiplying rows |
| Bytes returned | Estimate network and decoding costs |
| Database CPU/buffer reads | Catch expensive scans, joins, or sorts |
| JVM CPU/heap allocation/GC | Catch excessive object materialization |
| Connection pool usage | Catch queries/transactions holding connections too long |
| Throughput under concurrency | Confirm whether the strategy scales |

### Benchmark Workflow

1. Prepare representative data: root count, average child count, and tail distribution.
2. Run default aggregate loading, projection DTO, JOIN, and Single Query Loading when eligible.
3. Use identical filters, sorting, page sizes, and semantics.
4. Warm up JVM/connection pools and database caches according to a defined script.
5. Run multiple iterations, recording latency percentiles and throughput instead of single runs.
6. Inspect actual SQL, query plans, and returned row counts.
7. Test concurrency close to production levels.
8. Compare CPU, memory, bytes, and database resources alongside latency.
9. Re-run after adding indexes or changing queries to isolate where gains come from.

Do not measure database call counts alone. A single JOIN query returning hundreds of thousands of rows via a Cartesian product can be slower than multiple small, well-indexed queries.

### Measurement Tools

- SQL logging or datasource instrumentation to count statements.
- Micrometer/Actuator and tracing to measure latency by repository/use case.
- Database `EXPLAIN`/`EXPLAIN ANALYZE` to inspect execution plans.
- PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` to check time, rows, and buffer reads.
- Testcontainers to run integration tests on the production DBMS engine.
- JFR or a profiler to observe JVM allocations and GC.

Enable verbose SQL logging in test/benchmark environments; avoid logging sensitive payloads or leaving excessive debug logging enabled long-term in production.

## 11. Example Query Count Measurement for N+1

Suppose a page loads 100 orders and each order has lines. Under traditional loading, you might see:

~~~text
1 query: SELECT purchase_order ...
N queries: SELECT order_line WHERE order_id = ?
~~~

If all 100 orders have collections, total statements can grow with the number of aggregates. If the aggregate has multiple collections, queries can increase further per loaded relationship.

After enabling Single Query Loading for a qualifying aggregate, a supported find method can load those aggregates in one SQL query. However, if the actual query is a derived query or `@Query`, Single Query Loading does not apply; re-measure the exact method being called.

A summary projection can use one `GROUP BY` query to return 100 DTOs without loading any `OrderLine`. This can be the best option when the caller only needs line count and total amount.

Illustrative table, not guaranteed measurements:

| Strategy | Expected statement count | Result rows | Object materialization |
|---|---:|---|---|
| Default aggregate loading | Root query + collection queries | Roots and children across multiple result sets | Full aggregate |
| Projection + aggregate SQL | Typically 1 query | One row/DTO per root | Small DTO |
| JOIN root + one collection | Typically 1 query | Possibly multiple rows per root | Needs grouping if building collections |
| JOIN multiple collections | Possibly 1 query | Can cross-multiply heavily | Expensive mapping/deduplication |
| Single Query Loading | 1 query when eligible | Framework-shaped result set to assemble aggregates | Full aggregate |

Do not turn an illustrative table into a performance guarantee. Actual query counts, rows, and timings depend on the method, mapping, database, dialect, and data.

## 12. Pagination and Collection JOINs

A common mistake is applying `LIMIT/OFFSET` directly to a one-to-many JOIN result:

~~~sql
SELECT po.id, ol.id AS line_id
FROM purchase_order po
LEFT JOIN order_line ol ON ol.order_id = po.id
ORDER BY po.created_at DESC
LIMIT 20 OFFSET 0;
~~~

`LIMIT 20` here caps joined rows, not 20 purchase orders. If an order has 10 lines, a page may return only a few roots.

To paginate by root:

1. Select the page of root IDs/rows first.
2. Then JOIN/fetch details for that set of IDs.
3. Or use an aggregate query returning exactly one row per root.
4. Ensure the count query counts roots, not child rows.

Example using a CTE:

~~~sql
WITH page_orders AS (
    SELECT id, customer_id, status, created_at
    FROM purchase_order
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
)
SELECT
    po.id,
    po.status,
    po.created_at,
    c.name AS customer_name
FROM page_orders po
JOIN customer c ON c.id = po.customer_id
ORDER BY po.created_at DESC, po.id DESC;
~~~

If collection details are needed, query them separately for the IDs on the page or use a `ResultSetExtractor` to group them. For large pages or deep offsets, consider keyset pagination on `(created_at, id)` instead of deep offset.

## 13. Testing Results and Query Counts

Functional tests must verify returned data is correct; performance tests must measure SQL and resource usage.

Cases to cover:

- Aggregates with 0, 1, and many children.
- Aggregates with direct collections and nested collections.
- Projections returning accurate counts/sums when roots have no children.
- One-to-many JOINs not producing duplicate roots.
- Multi-collection JOINs not multiplying totals.
- Pagination returning the exact number of roots, even when roots have many children.
- Single Query Loading enabled and executed on a supported database/dialect.
- Fallback still producing correct results when Single Query Loading criteria are unmet.
- Custom SQL running on a production-compatible database/driver.
- Query plans using indexes aligned with filters/sorts.

### Integration Testing with Testcontainers

Use the same database engine as production to test dialects, window functions, SQL JOINs, paging, and mapping. H2 can be useful for quick tests but does not represent Single Query Loading dialects because the built-in H2/HSQL dialects lack the required windowing support.

In Single Query Loading tests, enable SQL instrumentation or a datasource proxy to verify actual statement counts. Do not assert only `isSingleQueryLoadingEnabled()` is true; the flag only indicates configuration, not that a specific method used that strategy.

## 14. Common Mistakes

| Symptom | Cause | Remedy |
|---|---|---|
| Multiple queries persist after enabling Single Query Loading | Method is derived/`@Query`, dialect unsupported, or aggregate ineligible | Check find method, mapping, dialect, and SQL logs |
| H2 test does not use Single Query Loading | H2 dialect lacks required window functions | Test on a production-compatible database |
| Projection still loads too much data | Query selects too many columns or returns aggregate instead of DTO | SELECT only needed columns and map DTO cleanly |
| `@Query` with JOIN still queries collections separately | Default `RowMapper` handles collections via separate statements | Use DTO/`RowMapper` or custom `ResultSetExtractor` for a single read model |
| One order appears multiple times | One-to-many JOIN creates multiple result rows | Group rows by root ID or aggregate in SQL |
| Totals are multiplied | Joining multiple collections creates a Cartesian product | Aggregate each collection in a subquery/CTE before joining |
| Page has fewer roots than expected | LIMIT applied to joined rows | Paginate root IDs first, then fetch details |
| Single Query Loading does not activate | Nested collection, `Map`, `AggregateReference`, or embedded entity present | Use default loading or custom read model queries |
| SQL JOIN is slow despite single statement | Large scan plan, missing indexes, excessive result rows | Run EXPLAIN, check cardinality/indexes and payload |
| DTO mapping type errors | Alias, JDBC type, or `RowMapper` mismatch | Check ResultSet metadata and mapping |
| Summary query wrong when no children exist | `INNER JOIN` or `COUNT(*)`/`SUM` NULL handling | Use `LEFT JOIN`, `COUNT(child.id)`, `COALESCE` |
| Missing domain data when using DTO for command | DTO lacks invariants/owned entities | Load full aggregate for command use cases |

## 15. Decision Workflow

1. **Determine intent:** does the caller need the aggregate for domain changes, or read-only data?
2. **If only partial data is needed:** design a projection DTO and SELECT only the required columns.
3. **If related tables are needed:** use JOIN for to-one, or aggregate/subquery for to-many.
4. **Check cardinality:** calculate rows after JOIN; avoid cross-multiplying multiple collections.
5. **If full aggregates are needed:** use an appropriate repository find method.
6. **Check Single Query Loading:** version 3.2+, mapping free of restrictions, supported `CrudRepository` method, and dialect with window functions.
7. **Measure actual queries:** count statements, rows, bytes, latency, CPU, and allocations.
8. **Check pagination:** paginate by root, use deterministic sorting, and consider keyset for deep offsets.
9. **Test on target database:** verify SQL, dialect, mapping, counts, and concurrency.
10. **Pick by total cost:** round-trips, data transferred, database CPU, JVM overhead, and maintenance complexity.

### Quick Decision Table

| Situation | Try first |
|---|---|
| List needs only a few fields and summary numbers | Projection DTO + SQL aggregation |
| Need name from a to-one relation alongside root | SQL JOIN |
| Need one collection for read-only detail | JOIN + `ResultSetExtractor` or separate query; measure cardinality |
| Need multiple direct collections on aggregate via supported `CrudRepository` method | Try Single Query Loading if dialect/mapping qualify |
| Contains nested collections, `Map`, `AggregateReference`, or embedded entities | Default loading or custom read model |
| Derived query or `@Query` needing to load aggregate | Default loading; tune queries/indexes or switch to an appropriate fragment |
| Multi-collection JOIN inflates row counts | Subquery/CTE per collection, or Single Query Loading if suitable |
| Command needs invariants/domain behavior | Load full aggregate via repository |
| Multi-table report needing no aggregate behavior | Custom SQL/fragment returning DTO |

**Bottom line:** projection DTOs fit callers needing partial data; SQL JOINs fit bounded relationships and cardinalities; Single Query Loading fits full aggregates when all Spring Data JDBC conditions are satisfied. Choose based on holistic measurements — query counts, rows/bytes, latency, database CPU, and JVM allocations — rather than SQL statement count alone.

## Official References

- [Spring Data Relational — Persisting Entities and Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): traditional aggregate loading, Single Query Loading, limitations, and `JdbcMappingContext` configuration.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): `@Query`, `RowMapper`, `ResultSetExtractor`, collection mapping, and pagination limitations.
- [Spring Data Relational — JdbcMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/JdbcMappingContext.html): `setSingleQueryLoadingEnabled(boolean)`.
- [Spring Data Relational — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html): configuring mapping context and infrastructure.
- [Spring Blog — Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/): background, approach, and initial limitations of Single Query Loading.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): analyzing execution plans and query costs.
- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): analytic/window functions used in advanced SQL strategies.
- [Testcontainers — Database Modules](https://java.testcontainers.org/modules/databases/): integration testing with real database engines.
