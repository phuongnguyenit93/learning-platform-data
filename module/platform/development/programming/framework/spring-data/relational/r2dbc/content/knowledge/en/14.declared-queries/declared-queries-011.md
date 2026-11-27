# Organizing Complex SQL and Testing Database Portability

In Spring Data Relational R2DBC, declared queries let you place SQL directly beside repository methods. This works well when queries need joins, CTEs, aggregations, conditional expressions, or database-specific features that method names cannot express clearly. As SQL grows, the challenge is no longer just writing valid syntax. Queries must be organized so readers can follow them, parameters are bound safely, results map accurately, and reliance on specific database engines stays controlled.

Database portability does not mean every SQL statement looks identical everywhere. PostgreSQL, MySQL, SQL Server, and other engines differ in data types, functions, pagination syntax, upserts, JSON, generated values, and handling of certain expressions. Spring Data R2DBC abstracts common mapping operations, yet does not automatically translate arbitrary custom SQL into another dialect.

This lesson explains how to organize complex SQL, choose the right place for queries, distinguish portable SQL from vendor-specific parts, and build tests that catch issues early when changing databases.

## 1. When should you use declared SQL?

Derived query methods fit relatively simple conditions with clear property names and minimal transformations. When a query needs specific SQL structure, `@Query` or a custom repository fragment is usually easier to understand.

Signs to consider declared SQL:

- Needing multi-table joins or data across multiple relationships.
- Needing CTEs, subqueries, window functions, or aggregations.
- Needing specialized SQL expressions that Criteria cannot express cleanly.
- Needing exact control over selected columns, join order, or grouping.
- Calling database functions, JSON queries, or full-text search.
- Tuning a query already measured via query plans and real workloads.

For example, the following method still fits derived queries:

```java
Flux<Order> findByCustomerIdAndStatusOrderByCreatedAtDesc(
        Long customerId,
        OrderStatus status);
```

When you need to combine customer details, line item counts, and order totals per order, a SQL statement expresses it more clearly:

```sql
SELECT
    o.id,
    o.status,
    o.created_at,
    c.display_name,
    COUNT(ol.id) AS line_count,
    SUM(ol.quantity * ol.unit_price) AS order_total
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
WHERE o.customer_id = :customerId
GROUP BY
    o.id,
    o.status,
    o.created_at,
    c.display_name
ORDER BY o.created_at DESC;
```

Explicit SQL exposes the join structure and aggregations. In return, the author is responsible for syntax, mapping, column names, and engine differences.

## 2. Choosing the right place for queries

There are three common options in Spring Data R2DBC:

| Implementation choice | Best suited for | Characteristics |
| --- | --- | --- |
| Derived query method | Fixed conditions easily read from property names. | Spring Data derives the query from the method name. |
| `@Query` on repository method | Stable declared SQL tied directly to the repository contract. | SQL sits right next to the method signature and binds parameters. |
| Custom repository fragment with `DatabaseClient` or `R2dbcEntityTemplate` | Dynamic SQL, multiple branches, reusable parts, or fine-grained control. | Queries can be split into small helpers and conditions assembled from input. |

Do not move every query into custom SQL. Keep derived queries when they express intent clearly without hiding logic. Use `@Query` when the SQL is stable enough to live beside the method. Use fragments when queries require multi-step assembly, reuse, or coordinating multiple statements.

### `@Query` for declared queries

Example repository using SQL with joins and aggregation:

```java
import java.math.BigDecimal;
import java.time.LocalDateTime;

import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Flux;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT
            o.id,
            o.status,
            o.created_at AS created_at,
            c.display_name AS customer_name,
            SUM(ol.quantity * ol.unit_price) AS total
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        LEFT JOIN order_lines ol ON ol.order_id = o.id
        WHERE o.created_at >= :from
          AND o.created_at < :to
        GROUP BY
            o.id,
            o.status,
            o.created_at,
            c.display_name
        ORDER BY o.created_at DESC
        """)
    Flux<OrderSummary> findSummaries(
            @Param("from") LocalDateTime from,
            @Param("to") LocalDateTime to);
}
```

This example assumes an `OrderSummary` projection matching the returned columns. The return type must reflect the result shape; avoid mapping aggregated rows into an `Order` entity when columns do not represent a complete entity.

`@Query` keeps SQL close to the query contract. It does not make the SQL portable on its own. If the statement contains PostgreSQL-specific functions or syntax, that method remains tied to PostgreSQL even though it is declared on a Spring Data repository.

### Custom fragments for queries needing dedicated organization

When a query has many optional filters, place it inside a fragment:

```java
public interface OrderSearch {
    Flux<OrderSummary> search(OrderSearchCriteria criteria);
}
```

The main repository combines the fragment:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long>, OrderSearch {
}
```

The implementation uses `DatabaseClient` or `R2dbcEntityTemplate` to construct and execute the query. This separates the repository contract from SQL assembly details and lets you break logic into small helpers by condition group.

## 3. Structuring long SQL statements for readability

A complex query should be formatted with a clear structure readers can trace:

1. Identify the primary dataset in `FROM`.
2. Add `JOIN` clauses and join conditions.
3. Define row filters in `WHERE`.
4. Group and aggregate in `GROUP BY`/`HAVING`.
5. Choose ordering in `ORDER BY`.
6. Apply row limits or pagination.

For example, a reporting query can be organized into meaningfully named CTEs:

```sql
WITH customer_orders AS (
    SELECT
        o.id,
        o.customer_id,
        o.status,
        o.created_at
    FROM orders o
    WHERE o.created_at >= :from
      AND o.created_at < :to
),
order_totals AS (
    SELECT
        ol.order_id,
        SUM(ol.quantity * ol.unit_price) AS total
    FROM order_lines ol
    JOIN customer_orders co ON co.id = ol.order_id
    GROUP BY ol.order_id
)
SELECT
    co.id,
    co.customer_id,
    co.status,
    co.created_at,
    ot.total
FROM customer_orders co
LEFT JOIN order_totals ot ON ot.order_id = co.id
ORDER BY co.created_at DESC;
```

CTEs give names to intermediate data steps. Readers can immediately understand `customer_orders` as orders within the time window and `order_totals` as per-order sums.

CTEs are not always faster than subqueries or joins. Databases may inline, materialize, or optimize them in engine-specific ways. Use CTEs primarily for clarity; evaluate performance using the target database's execution plan.

### Choose clear aliases

Short table aliases help in multi-join queries, but avoid ambiguous names. `orders o`, `customers c`, `order_lines ol` are easy-to-recognize conventions. Qualify shared column names with their table alias.

Set explicit result aliases when projections rely on column names:

```sql
SELECT
    c.display_name AS customer_name,
    COUNT(ol.id) AS line_count
```

Alias names must match the constructor/properties Spring Data uses for projection mapping. For uppercase names or special characters, understand your database engine's folding and quoting rules.

## 4. Keeping projections aligned with SQL results

Aggregate SQL generally returns shapes different from source entities. Create dedicated projections that accurately describe the output.

Record projection example:

```java
import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSummary(
    Long id,
    String status,
    LocalDateTime createdAt,
    String customerName,
    BigDecimal total
) {}
```

The SQL must return columns that map cleanly into the projection constructor:

```sql
SELECT
    o.id AS id,
    o.status AS status,
    o.created_at AS created_at,
    c.display_name AS customer_name,
    COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
GROUP BY o.id, o.status, o.created_at, c.display_name;
```

Exact mapping details can depend on the naming strategy and how your Spring Data version handles constructor projections. If an alias fails to map as expected, adopt clear column naming conventions or inspect mapping metadata and integration tests.

Do not use `SELECT *` in complex declared SQL. When new columns are added to tables or joined tables share column names, results can shift unexpectedly. Listing required columns keeps projections stable and reduces data transferred.

## 5. Binding parameters and keeping SQL safe

User-supplied values must be bound as parameters. Never concatenate input strings directly into SQL:

```java
// Unsafe: input data becomes part of the SQL structure
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
```

Use named parameters:

```java
return databaseClient.sql("""
        SELECT id, email, display_name
        FROM customers
        WHERE email = :email
        """)
    .bind("email", email)
    .map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("email", String.class),
        row.get("display_name", String.class)
    ))
    .one();
```

With repository `@Query`, Spring Data also supports binding parameters by name:

```java
@Query("""
    SELECT id, email, display_name
    FROM customers
    WHERE email = :email
    """)
Mono<CustomerSummary> findSummaryByEmail(
        @Param("email") String email);
```

Named parameters make SQL readable. Spring translates named parameters into the markers used by the specific driver. R2DBC drivers can use different marker syntax, such as `?` or `$1`; applications using Spring APIs should avoid hardcoding native markers inside SQL intended for the named-parameter abstraction.

### Parameters cannot represent column names or keywords

Bind parameters are strictly for values. You cannot use `:columnName` to substitute a column name or `:direction` to substitute `ASC`/`DESC`.

If dynamic sorting is needed, map client choices through an allowlist:

```java
String orderBy = switch (sortField) {
    case "createdAt" -> "created_at";
    case "total" -> "total";
    case "status" -> "status";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String direction = descending ? "DESC" : "ASC";
```

Only application-controlled strings may be spliced into the SQL structure. Filter values must still be bound. Never use arbitrary column names supplied by clients.

### Binding NULL

R2DBC needs to know the data type when binding SQL NULL. With `DatabaseClient`, use `bindNull(name, Type.class)` rather than passing Java `null` directly to `bind`.

```java
databaseClient.sql("""
        SELECT id, display_name
        FROM customers
        WHERE deleted_at IS NOT NULL
           OR :includeActive = TRUE
        """)
    .bind("includeActive", includeActive);
```

This is just an example with a boolean parameter. If a parameter can be null, define its semantics explicitly and use `bindNull` with the matching class. Do not conflate "filter omitted" with "match rows where the column is NULL."

## 6. IN, lists, and optional conditions in declared SQL

A query may accept a list of filter values:

```java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE status IN (:statuses)
    """)
Flux<Order> findByStatuses(
        @Param("statuses") Collection<String> statuses);
```

Spring Data and its named-parameter expansion layer can expand collections into corresponding bind markers. However, behavior for empty collections and element types must be verified against your actual framework/driver version.

Before calling the method, handle empty lists in the application layer:

- If an empty list means no filtering, invoke a query without the status predicate.
- If an empty list means zero results are allowed, return `Flux.empty()` or use an always-false predicate.
- If the list contains nulls, strip or handle null separately per business rules.

Do not assume `IN (:values)` with an empty list always translates into valid syntax on every database.

### Optional filters

A common SQL pattern is:

```sql
WHERE (:status IS NULL OR status = :status)
```

This pattern is convenient, though not always optimal. It relies on NULL-binding support, parameter typing, and the query planner. With many optional filters, conditions like `(:p IS NULL OR column = :p)` can yield less selective plans or hinder index usage.

When assembling many combinations of conditions, a custom fragment using `Criteria` or controlled dynamic SQL is usually cleaner. Above all, distinguish whether null means "omit the filter" or "find rows with NULL columns."

## 7. What Spring Data Dialects do and do not do

Spring Data Relational has a dialect concept to adapt framework-generated SQL operations. A dialect supplies details about engine specifics, such as bind marker syntax, data types, or syntax needed for certain mapping operations.

When using `R2dbcEntityTemplate` or CRUD repositories, Spring Data uses the dialect matching the `ConnectionFactory` to generate statements compatible with the driver and database. This keeps routine CRUD and mapping operations loosely coupled to hand-written SQL syntax.

However, distinguish two cases:

| Case | Role of the dialect |
| --- | --- |
| `repository.save`, `findById`, `R2dbcEntityTemplate` statement generation | Spring Data uses the dialect to generate SQL suited to the driver/database. |
| Verbatim SQL inside `@Query` | The SQL statement must still be valid for the target database. |
| Verbatim SQL inside `DatabaseClient.sql(...)` | Named parameters are handled by Spring, while custom SQL content is not automatically translated to other dialects. |
| Custom fragment using `Criteria`/template | The framework can generate dialect-specific parts; any hand-written SQL in the fragment remains the author's responsibility. |

For instance, a dialect helps Spring Data choose how to construct insert statements. Yet if `@Query` uses a PostgreSQL-only JSONB function, switching the `ConnectionFactory` to MySQL will not rewrite that function into MySQL JSON syntax.

Do not treat a dialect as a general-purpose SQL translator. It is an abstraction for framework-supported extension points, not a converter for arbitrary custom statements.

## 8. Prefer standard SQL for shared parts

If an application may deploy onto multiple database engines, define a baseline SQL subset well-supported across target databases. Standard SQL helps for:

- Basic SELECT, INSERT, UPDATE, DELETE.
- INNER JOIN, LEFT JOIN.
- WHERE, AND, OR, NOT.
- GROUP BY, HAVING, ORDER BY.
- CASE, COALESCE, NULLIF.
- EXISTS and common subquery forms.
- UNION and UNION ALL.
- Standard comparisons and BETWEEN.

Even with standard syntax, details such as data types, collation, NULL ordering, functions, and optimizer behavior can still differ. Treat standard SQL as a baseline that minimizes differences, not a guarantee that every engine produces identical results on all inputs.

For example, `CASE` expresses portable conditional logic:

```sql
SELECT
    id,
    total,
    CASE
        WHEN total >= :highValue THEN 'HIGH'
        WHEN total >= :mediumValue THEN 'MEDIUM'
        ELSE 'LOW'
    END AS order_band
FROM orders;
```

Threshold values are bound. The label strings are application-controlled constants. If labels carry major business significance and appear in multiple places, consider computing them in the domain or storing them as state instead of repeating SQL expressions.

### COALESCE and NULLIF

COALESCE(a, b) returns the first non-NULL argument. NULLIF(a, b) returns NULL when both expressions are equal. These standard SQL functions are often helpful when handling aggregated data or avoiding division by zero:

```sql
SELECT
    customer_id,
    COALESCE(SUM(total), 0) AS total_spent
FROM orders
GROUP BY customer_id;
```

```sql
SELECT
    numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
```

Expression data types must still be compatible. Different databases may apply different casting rules or result types, so test against real column types.

## 9. Areas where SQL commonly differs across database engines

Portability issues typically arise around features where each database defines its own syntax or semantics.

| Topic | Common differences | How to organize |
| --- | --- | --- |
| Identity and generated keys | IDENTITY, AUTO_INCREMENT, sequences, RETURNING, or generated-key APIs. | Put DDL in per-database migrations; check how the driver returns IDs. |
| Upsert | ON CONFLICT, ON DUPLICATE KEY UPDATE, MERGE. | Encapsulate in vendor-specific adapters or repository fragments. |
| Pagination | LIMIT/OFFSET, OFFSET/FETCH, proprietary syntax. | Use framework APIs when suitable or write dialect-specific adapters. |
| Booleans | BOOLEAN types, BIT, literals, and binding behavior. | Use clear Java types and verify mappings and literals. |
| Strings | Concatenation, collation, case-insensitive comparison. | Prefer standard APIs/SQL; isolate engine-specific search. |
| Date and time | With/without time zones, date functions, precision. | Standardize Java types and time zones; filter with ranges. |
| JSON | JSON/JSONB types, operators, functions, and indexes. | Isolate JSON queries by vendor or use bounded abstractions. |
| Full-text search | Tokenizers, syntax, ranking, and dedicated indexes. | Create separate implementations per database engine. |
| Regex and patterns | Different functions, operators, and escaping rules. | Do not assume regex expressions are portable. |
| NULL ordering | NULLS FIRST/LAST support and differing defaults. | Specify ordering explicitly using compatible syntax or separate adapters. |
| Identifier quoting | Double quotes, backticks, brackets, and casing rules. | Avoid reserved words; never splice raw input identifiers. |

### Identity and generated values

PostgreSQL commonly supports RETURNING; MySQL commonly uses AUTO_INCREMENT and a separate generated-key mechanism. Never write `INSERT ... RETURNING` and expect every database to accept it.

If portability is needed, use Spring Data-supported insert operations and verify that the driver returns generated IDs properly. When custom SQL is required, place engine differences inside database-specific implementations.

### Upserts

Upsert is a clear example of syntactic divergence:

```sql
-- PostgreSQL
INSERT INTO customer_setting (customer_id, setting_key, setting_value)
VALUES (:customerId, :key, :value)
ON CONFLICT (customer_id, setting_key)
DO UPDATE SET setting_value = EXCLUDED.setting_value;
```

```sql
-- MySQL
INSERT INTO customer_setting (customer_id, setting_key, setting_value)
VALUES (:customerId, :key, :value)
ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value);
```

Both snippets share the same goal yet differ in syntax and subtle semantics. Do not cram both into a single conditional SQL string. Provide one implementation per dialect or use an appropriate abstraction if the framework/driver fully supports your requirements.

### Booleans and literals

Do not assume every database accepts the same boolean literals. Some engines have native boolean types, while others map booleans to bits or numbers. Bind boolean values using Java `Boolean` so the driver performs the mapping; avoid converting them manually into `"true"` or `"1"` strings without a specific reason.

## 10. Pagination and sorting in custom SQL

Pagination is one of the easiest places for database-dependent SQL to creep in. `LIMIT :limit OFFSET :offset` is common in PostgreSQL and MySQL, whereas SQL Server typically uses `OFFSET ... FETCH` requiring an `ORDER BY`.

If using Spring Data-supported pagination APIs in a given context, verify how your R2DBC version supports them and generates count queries. Do not assume every repository `@Query` automatically shares the exact same pagination behavior as JPA.

When writing custom SQL, always use deterministic ordering:

```sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

Include the ID column as a tie-breaker so rows sharing the same `created_at` do not shuffle arbitrarily across pages. The limit syntax above illustrates databases supporting `LIMIT/OFFSET`; other engines need corresponding adapters.

### Offset pagination vs. keyset pagination

Offset pagination is straightforward, though its cost can grow at deep offsets. Keyset pagination uses values from the last row of the previous page to fetch the next page:

```sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :customerId
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
FETCH FIRST :pageSize ROWS ONLY;
```

The row-limiting clause above is not universal across all databases; the keyset predicate is the reusable idea, while row-limiting syntax must follow the vendor. Keyset pagination requires deterministic ordering and matching cursor columns. It fits large datasets or continuous scrolling, though it cannot replace every case requiring arbitrary page jumps.

## 11. CTEs, window functions, and version support

CTEs and window functions make analytical queries readable:

```sql
WITH ranked_orders AS (
    SELECT
        o.id,
        o.customer_id,
        o.created_at,
        o.total,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.id DESC
        ) AS row_number
    FROM orders o
)
SELECT id, customer_id, created_at, total
FROM ranked_orders
WHERE row_number <= :maxPerCustomer;
```

This example selects the most recent orders per customer. CTEs and `ROW_NUMBER()` are widely supported in modern databases, though exact features, extra clauses, and optimizations depend on version.

When using features like recursive CTEs, `LATERAL`, aggregate `FILTER`, or advanced window frames, verify the minimum supported version of your target database. If an engine lacks support, provide an alternative query or document the version requirement explicitly.

## 12. JSON, arrays, and full-text search

JSON, array, and text-search features are very useful, yet far less portable than core SQL.

For example, PostgreSQL offers `JSONB`, specialized operators, and dedicated indexes. MySQL also provides `JSON` and its own set of JSON functions. Function names, path syntax, return types, and indexing capabilities differ.

Do not place vendor-specific JSON queries in a shared repository expecting a driver swap to handle them. Instead, define an interface matching application needs:

```java
public interface ProductDocumentSearch {
    Flux<Product> findByAttribute(String attribute, String value);
}
```

Then supply an implementation per database engine. Services call the shared contract, while each adapter owns the appropriate JSON SQL. Even if the application targets only one database, placing JSON queries inside a clearly named fragment keeps the dependency visible.

Apply the same principle to arrays, full-text search, spatial types, or regex. Only introduce a shared abstraction when it faithfully covers the semantics your application needs; otherwise, expose the differences cleanly at the repository adapter boundary.

## 13. Isolating vendor-specific SQL into database adapters

If an application deploys on a single known database engine, vendor-specific SQL can stay inside a clearly named repository fragment. If the same application must run across multiple databases, place differences behind replaceable boundaries.

For example, business logic needs to insert or update a setting by unique key. The application contract describes only the behavior:

```java
public interface CustomerSettingWriter {
    Mono<Void> upsert(
        Long customerId,
        String key,
        String value
    );
}
```

The PostgreSQL implementation uses `ON CONFLICT`; the MySQL implementation uses `ON DUPLICATE KEY UPDATE`. Each holds its own SQL while fulfilling the same contract. Implementations can be selected via Spring profiles, conditional configuration, or active database configuration. Ensure only one matching implementation is registered per deployment.

Do not let business services check the database name and assemble vendor SQL inline. That scatters storage logic across layers and makes adding new engines error-prone.

### Keep differences close to the database

One possible package layout:

```text
persistence/
  order/
    OrderRepository.java
    OrderSearch.java
    OrderSearchImpl.java
    OrderProjection.java
  vendor/
    postgres/
      PostgresCustomerSettingWriter.java
    mysql/
      MysqlCustomerSettingWriter.java
    CustomerSettingWriter.java
```

This is an example layout, not a mandatory Spring package convention. The aim is for readers to immediately locate vendor-specific SQL rather than hunting for it inside services or controllers.

If vendor-specific SQL appears in only one method, a dedicated fragment works well. When multiple features depend on the database vendor, database-specific adapters centralize differences and make replacement straightforward.

## 14. Use bounded abstractions

Not every SQL difference warrants a new framework abstraction. An abstraction is helpful when it represents a stable business need that can be fulfilled across target databases.

For example, a contract "find a customer's recent orders" can have separate database implementations if pagination, indexing, or JSON filtering differs. The service simply receives uniformly typed results.

By contrast, an abstraction like "execute any SQL expression across any database" is usually too broad. It forces the application down to the lowest common denominator of features or creates tangled configuration branches.

You can organize queries into three tiers:

| Tier | Examples | Management strategy |
| --- | --- | --- |
| Shared SQL | Common joins, filters, aggregates, and subqueries. | Use `@Query` or fragments with standard SQL; test against every target database. |
| SQL with minor differences | Pagination syntax, generated keys, null ordering. | Use small helpers/adapters in the persistence layer. |
| Vendor-specific features | JSONB, full-text search, upserts, spatial queries. | Separate into dedicated implementations or restrict supported engines. |

Never try to abstract over a feature whose semantics lack equivalence across target databases. If two engines' full-text searches compute ranking and tokenization differently, sharing one method name will not guarantee identical results. Define the exact contract the application needs and which differences are acceptable.

## 15. Managing schemas and migrations per database engine

Query portability is insufficient if the schema itself cannot be created on target databases. Data types, identity columns, indexes, constraints, JSON columns, generated columns, and functions in DDL can all differ.

Use a migration tool to version schema changes. When supporting multiple engines, keep shared migrations for compatible parts and vendor-specific migrations for parts that cannot be shared.

For example, PostgreSQL has a native `UUID` type, whereas MySQL might use `BINARY(16)` or `CHAR(36)`. JSON indexes or expression indexes also use distinct syntax. Represent these differences in controlled migrations rather than hiding them in application startup hooks.

A rollout strategy might include:

1. Identify supported databases and versions.
2. Create baseline migrations for shared tables, columns, and constraints.
3. Add vendor-specific migrations for specialized types, indexes, or functions.
4. Keep entity mappings and converters aligned with each profile's schema.
5. Execute full migrations against target databases in the test pipeline.
6. Deploy application versions in an order compatible with both old and new schemas.

Never edit migrations already deployed to shared environments if your migration tool treats them as immutable. Create new migrations to evolve the schema. If supporting multiple dialects, ensure your CI pipeline actually runs the corresponding migration sets rather than checking compilation alone.

## 16. Testing portability against real databases

Mocking repositories cannot validate SQL syntax, dialects, mappings, data types, or database semantics. For complex declared queries, run integration tests using real drivers and databases.

If the application claims support for multiple database engines, run the same contract test suite against every supported engine. Testcontainers can spin up isolated databases in CI pipelines, provided images and versions match deployment environments.

A test matrix may include:

| Test | What to verify |
| --- | --- |
| Context startup and repository creation | Query methods and repository fragments are configured properly. |
| Executing each `@Query` | SQL is valid, parameters bind, and projections map accurately. |
| Running CTE/window queries | Target database version supports the required syntax. |
| Collection `IN` queries | Normal lists, empty lists, and NULL handling follow expected semantics. |
| Pagination | Deterministic ordering, accurate counts/results, and no duplicates or gaps. |
| Generated keys/upserts | Insert/update behavior and returned IDs match vendor contracts. |
| Data types | Decimals, timestamps, booleans, enums, and JSON map as contracted. |
| Transactions | Related operations commit/roll back as configured. |
| Migrations | Schemas are created and upgraded cleanly on every database. |

You can use a shared test interface or contract suite for adapter implementations. Each database runs the same business cases, supplemented by dedicated tests for vendor-specific features.

Example testing a repository returning a projection:

```java
@Test
void returnsOrderSummaryForCustomer() {
    StepVerifier.create(
            orderRepository.findSummaries(from, to)
        )
        .assertNext(summary -> {
            assertNotNull(summary.id());
            assertNotNull(summary.customerName());
            assertNotNull(summary.total());
        })
        .verifyComplete();
}
```

Test data must be prepared explicitly to verify both matching results and empty-result cases. Do not check only that the publisher completes; assert values and query boundaries.

### Test behavior, not just syntax

Two databases may accept nearly identical syntax yet return different results due to collation, time zones, NULL ordering, precision, or implicit casts. Portability tests must verify business semantics:

- Are strings case-sensitive or case-insensitive?
- Where do NULL values sort?
- In what time zone are timestamps stored and compared?
- What precision/scale does numeric division produce?
- Do LIKE and wildcards follow the same escaping rules?
- Does JSON path extraction return a scalar or a JSON value?
- Do upserts resolve conflicts on the intended constraint?

If differences between databases are acceptable, document them in the contract. If differences are unacceptable, normalize data or expressions to guarantee consistent semantics.

## 17. Using query plans and logging for diagnostics

A SQL statement that runs is not automatically efficient. Use your target database's explain/query-plan tools to see how the optimizer handles joins, filters, indexes, sorting, and aggregations.

When a query is slow:

1. Identify the actual SQL statement and bind values affecting selectivity.
2. Check whether indexes match the filter predicates and ordering.
3. Look for full table scans, large sorts, or inefficient joins.
4. Compare estimated row counts against actual row counts if the tool reports them.
5. Test with data volumes and distributions close to production.
6. Re-measure after modifying indexes or query structure.

Execution plans do not necessarily transfer across databases. Never copy hints or index designs blindly from one engine to another without re-measuring.

SQL logging is helpful during development and debugging. However, control parameter logging because bound values can contain emails, tokens, personal data, or sensitive payloads. Never log all bound values in production without proper redaction policies.

## 18. Workflow for organizing and testing complex queries

When adding a new SQL query, follow this sequence:

1. **Define the result contract clearly:** entity vs. projection, cardinality, and NULL semantics.
2. **Choose the implementation approach:** derived method, `@Query`, or custom fragment.
3. **Sketch the SQL logic:** specify joins, filters, grouping, sorting, and pagination.
4. **Name aliases and returned columns:** ensure clear projection mapping and avoid `SELECT *`.
5. **Bind all values:** never concatenate user data into SQL; guard dynamic identifiers with an allowlist.
6. **Identify vendor dependencies:** functions, data types, upserts, JSON, pagination, and generated values.
7. **Choose portability boundaries:** shared SQL, small adapters, or database-specific implementations.
8. **Manage schemas with migrations:** keep DDL and indexes aligned with queries.
9. **Test on every target database:** verify syntax, mapping, and semantics.
10. **Measure query plans:** optimize for real workloads and document operational assumptions.

Well-organized declared queries make both their purpose and output shape unmistakable. Spring Data R2DBC manages repositories, mapping, and parameter binding; dialects support framework-generated SQL. Hand-written SQL remains responsible for the target database's syntax and semantics. By keeping shared SQL standard, isolating vendor specifics inside adapters, and testing against real databases, applications can handle complex queries while keeping database portability under control.
