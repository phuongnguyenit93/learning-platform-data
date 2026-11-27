# Choosing Between Template Dynamic Queries and Hand-Written SQL

In Spring Data R2DBC, a search request often involves multiple optional filters: status, customer, time range, keyword, sort order, and result limit. Queries can be built using `R2dbcEntityTemplate`'s `Query`/`Criteria` API, or by writing SQL directly via `DatabaseClient` or `@Query` in a Repository.

Both approaches have their place. The template fits entity-centric queries using standard filter conditions, sorting, and pagination. Hand-written SQL fits when you need control over query structure, joins, aggregations, CTEs, window functions, or database-specific features. The choice should rest on query complexity, readability, performance requirements, portability, and result mapping.

## 1. The Two Approaches

### 1.1. Dynamic Queries with R2dbcEntityTemplate

`R2dbcEntityTemplate` is Spring Data R2DBC's higher-level API for working with entities. It uses Spring Data mapping metadata and the database dialect to generate SQL statements from query objects.

Commonly used components:

- `Criteria`: represents filter conditions on properties/columns.
- `Query`: combines conditions with sort, limit, and offset.
- `Update`: describes properties to update.
- `R2dbcEntityTemplate`: executes select, insert, update, and delete using entity mapping.

Example query with status and time conditions:

```java
Criteria criteria = Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID")
        .and("createdAt").greaterThanOrEquals(from);

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt"),
                      Sort.Order.desc("id")))
        .limit(20)
        .offset(0);

return template.select(query, OrderEntity.class);
```

The template generates the query from `OrderEntity`'s mapping, executes it via R2DBC, and maps result rows into entities. In this example, names like `tenantId` and `createdAt` are Java entity properties; mapping metadata handles their relationship to column names per configuration.

### 1.2. Hand-Written SQL via DatabaseClient

`DatabaseClient` provides a direct SQL execution API. The developer controls tables, joins, expressions, aliases, ordering, and statement structure. Input values must still be bound as parameters to prevent SQL injection and ensure proper driver typing.

Example:

```java
return databaseClient.sql("""
        SELECT id, order_code, status
        FROM orders
        WHERE tenant_id = :tenantId
          AND status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """)
    .bind("tenantId", tenantId)
    .bind("status", status)
    .bind("limit", 20)
    .bind("offset", 0)
    .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_code", String.class),
            row.get("status", String.class)))
    .all();
```

Here, the code writes the SQL directly and maps results into `OrderSummary`. `DatabaseClient` does not infer entity mapping for arbitrary custom projections inside a `map` callback; the author must specify how columns are read and results constructed.

### 1.3. SQL Declared in Repositories Using @Query

If custom SQL has a fixed structure, it can be declared directly with `@Query` on a Repository method:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    @Query("""
        SELECT * FROM orders
        WHERE tenant_id = :tenantId
          AND status = :status
        ORDER BY created_at DESC
        """)
    Flux<OrderEntity> findByTenantAndStatus(
            Long tenantId, String status);
}
```

`@Query` is useful when the SQL is known ahead of time and does not need structural assembly at runtime. When the number of condition combinations is large or multiple statement parts vary per filter, use `DatabaseClient` to build parameterized SQL or fall back to Criteria if the query belongs to the group the Template handles well.

## 2. Building Optional Filters with Criteria

Dynamic queries typically start with mandatory conditions, then add optional conditions if the user supplies corresponding values. For example, every query must be scoped to a tenant; status and time range are optional.

### 2.1. Filter Model

```java
public record OrderFilter(
        Long tenantId,
        String status,
        Instant createdFrom,
        Instant createdTo,
        int limit,
        long offset
) {
}
```

Tenant is a mandatory condition scoping the dataset. Status and time bounds are added only when present.

### 2.2. Conditionally Appending Criteria

```java
public Flux<OrderEntity> search(OrderFilter filter) {
    Criteria criteria = Criteria.where("tenantId").is(filter.tenantId());

    if (filter.status() != null && !filter.status().isBlank()) {
        criteria = criteria.and("status").is(filter.status());
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("createdAt")
                .greaterThanOrEquals(filter.createdFrom());
    }

    if (filter.createdTo() != null) {
        criteria = criteria.and("createdAt")
                .lessThan(filter.createdTo());
    }

    Query query = Query.query(criteria)
            .sort(Sort.by(Sort.Order.desc("createdAt"),
                          Sort.Order.desc("id")))
            .limit(filter.limit())
            .offset(filter.offset());

    return template.select(query, OrderEntity.class);
}
```

This snippet demonstrates chaining conditions onto `Criteria`. `Criteria` represents conditions; each time you append a condition, retain the returned instance so the final query contains all predicates. Never discard the result of `and(...).is(...)`.

In real applications, validate that `limit` falls within a sensible cap, `offset` is non-negative, and time ranges are valid before building the query. Never let clients pass an unbounded `limit` that forces the application to read hundreds of thousands of records in one request.

### 2.3. Common Criteria Operators

| Need | Expression |
|---|---|
| Equal to value | `Criteria.where("status").is("PAID")` |
| Not equal to value | `Criteria.where("status").not("CANCELLED")` |
| Greater than | `Criteria.where("totalAmount").greaterThan(amount)` |
| Greater than or equal to | `greaterThanOrEquals(value)` |
| Less than | `lessThan(value)` |
| Within range | `between(min, max)` |
| In set of values | `in(values)` |
| Not in set of values | `notIn(values)` |
| Null value | `isNull()` |
| Non-null value | `notNull()` |
| Pattern match | `like(pattern)` or supported equivalent operator |

Verify exact method names and available operators against your project's Spring Data Relational version. Comparison syntax can also be affected by column types and the database.

### 2.4. Distinguishing Skipping a Filter from Searching for NULL

An omitted filter usually means not adding that condition to the query. It does not mean searching for rows with a `NULL` column.

For example:

- `status == null` in request: omit the status filter.
- Explicit request for `status IS NULL`: add `Criteria.where("status").isNull()`.

If an API needs to distinguish these two cases, the DTO should express intent clearly—for instance via an `onlyWithoutStatus` flag or a filter type with states `ANY`, `IS_NULL`, `EQUALS`. Never use one null value for two different meanings.

### 2.5. Combining AND and OR

Simple conditions typically combine with AND. When OR logic is involved, group conditions to preserve logical precedence. For instance, finding orders with status `PAID` or `SHIPPED` within the same tenant. Use Criteria groups via the `or`/`and` APIs supported by your Spring Data version.

For multi-layered logical expressions, write out the condition on paper before translating it to the API. A query shaped like:

```sql
WHERE tenant_id = :tenantId
  AND (status = 'PAID' OR status = 'SHIPPED')
  AND created_at >= :from
```

is not equivalent to:

```sql
WHERE (tenant_id = :tenantId AND status = 'PAID')
   OR (status = 'SHIPPED' AND created_at >= :from)
```

If the Criteria API becomes hard to express or read for nested expressions, hand-written SQL can make the intent clearer.

## 3. Using Template for Select, Update, and Delete

`R2dbcEntityTemplate` is not limited to searching. It also provides data manipulation APIs backed by entity metadata.

### 3.1. Selecting One or Many Entities

```java
Mono<OrderEntity> findOne(Long id) {
    Query query = Query.query(Criteria.where("id").is(id));
    return template.selectOne(query, OrderEntity.class);
}

Flux<OrderEntity> findRecent(Long tenantId) {
    Query query = Query.query(Criteria.where("tenantId").is(tenantId))
            .sort(Sort.by(Sort.Order.desc("createdAt")))
            .limit(50);

    return template.select(query, OrderEntity.class);
}
```

`selectOne` returns `Mono` because at most one entity is expected; `select` returns `Flux` for zero or more results. If a condition is non-unique when using `selectOne`, understand how the API handles multiple rows and design conditions accordingly.

### 3.2. Conditional Update

```java
Mono<Long> markAsExpired(Instant cutoff) {
    Query query = Query.query(
            Criteria.where("status").is("PENDING")
                    .and("expiresAt").lessThan(cutoff));

    Update update = Update.update("status", "EXPIRED");

    return template.update(query, update, OrderEntity.class);
}
```

The Template API can generate an `UPDATE` statement from conditions and the set of modified properties. The result typically reports affected row count. This is convenient for simple updates on a single entity type.

Note that Query-based updates operate directly on matching rows. They do not necessarily load individual entities, invoke domain methods on each instance, or follow the same pipeline as reading an entity and calling `save`. If business rules require per-order state transition checks, emitting domain events, or per-entity optimistic locking, design an appropriate read/update flow and verify the versioning behavior of the API used.

### 3.3. Delete by Criteria

```java
Mono<Long> deleteExpiredDrafts(Instant cutoff) {
    Query query = Query.query(
            Criteria.where("status").is("DRAFT")
                    .and("createdAt").lessThan(cutoff));

    return template.delete(query, OrderEntity.class);
}
```

Query-based deletion fits when the exact target row set can be specified via conditions. For bulk deletes, consider foreign keys, auditing, retention policies, and event publishing requirements. If individual entities must be processed before deletion, do not replace that with a bulk delete merely because it is shorter.

## 4. When Is Hand-Written SQL More Suitable?

Criteria has expressive limits. Certain queries require explicit SQL structures that do not fit the query-by-entity model well.

### 4.1. Multi-Table JOINs and Aggregated Projections

For example, an admin screen needs a list of orders along with customer name and line item count:

```sql
SELECT o.id,
       o.order_code,
       c.display_name AS customer_name,
       COUNT(ol.id) AS line_count
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
WHERE o.tenant_id = :tenantId
GROUP BY o.id, o.order_code, c.display_name
ORDER BY o.created_at DESC, o.id DESC
```

This query combines multiple tables and aggregation. Hand-written SQL expresses joins, grouping, and aliases directly. Results should be mapped into a projection/DTO without needing to construct a full entity graph.

### 4.2. CTEs, Window Functions, and Analytical Queries

Requirements such as fetching the latest record per customer, ranking by revenue, computing running totals, or querying hierarchies commonly use CTEs and window functions. When a query relies on these constructs, direct SQL is usually easier to control.

For example:

```sql
WITH ranked_orders AS (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.created_at DESC, o.id DESC
           ) AS row_number
    FROM orders o
    WHERE o.tenant_id = :tenantId
)
SELECT id, customer_id, order_code, created_at
FROM ranked_orders
WHERE row_number = 1
```

Not all databases or versions support identical syntax. Hand-written SQL lets you leverage features of the target database while increasing coupling to that engine.

### 4.3. Database-Specific Functions and Data Types

If JSON operators, full-text search, array operations, spatial functions, locking clauses, or specialized hints are needed, hand-written SQL may be necessary. The Template can leverage dialects for supported differences, yet it is not a universal SQL builder covering every feature of every database.

### 4.4. Optimizing Measured Queries

When execution plans show that Template-generated queries do not meet requirements, hand-written SQL lets you tune joins, projections, predicates, hints, or subquery structure. However, do not switch to manual SQL purely on the assumption that it is always faster. First measure timings, read execution plans, check indexes, inspect rows scanned, and check data returned.

## 5. Building Safe Dynamic SQL

Dynamic SQL is useful when the number of filters varies per request. The golden rule is concatenating only SQL structural fragments controlled by the application; all data values must be bound via parameters.

### 5.1. Appending Optional Conditions and Binding Parameters

```java
public Flux<OrderSummary> search(OrderFilter filter) {
    StringBuilder sql = new StringBuilder("""
            SELECT id, order_code, status
            FROM orders
            WHERE tenant_id = :tenantId
            """);

    if (filter.status() != null && !filter.status().isBlank()) {
        sql.append(" AND status = :status");
    }

    if (filter.createdFrom() != null) {
        sql.append(" AND created_at >= :createdFrom");
    }

    if (filter.createdTo() != null) {
        sql.append(" AND created_at < :createdTo");
    }

    sql.append(" ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset");

    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql.toString())
            .bind("tenantId", filter.tenantId())
            .bind("limit", filter.limit())
            .bind("offset", filter.offset());

    if (filter.status() != null && !filter.status().isBlank()) {
        spec = spec.bind("status", filter.status());
    }
    if (filter.createdFrom() != null) {
        spec = spec.bind("createdFrom", filter.createdFrom());
    }
    if (filter.createdTo() != null) {
        spec = spec.bind("createdTo", filter.createdTo());
    }

    return spec.map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_code", String.class),
            row.get("status", String.class)))
        .all();
}
```

Each condition is added to SQL only when the corresponding parameter has a value; at the same time, the code binds that exact parameter. This avoids binding a parameter not present in the statement. If binding `NULL` intentionally is needed, R2DBC usually requires `bindNull(name, Type.class)` instead of `bind(name, null)`.

### 5.2. Never Concatenate User Input Directly into SQL

Do not write:

```java
String sql = "SELECT * FROM orders WHERE status = '" + status + "'";
```

If `status` comes from a request, input can break SQL structure and introduce an injection vulnerability. Use parameters:

```java
databaseClient.sql("SELECT * FROM orders WHERE status = :status")
        .bind("status", status);
```

Parameter binding applies only to data values. Table names, column names, operators, and sort directions are SQL structural elements; they cannot be replaced with standard bind parameters.

### 5.3. Whitelisting Column Names and Sort Directions

If an API allows choosing a sort field, map input to a fixed set of choices:

```java
String orderBy = switch (filter.sortBy()) {
    case CREATED_AT -> "created_at";
    case ORDER_CODE -> "order_code";
    case STATUS -> "status";
};

String direction = filter.descending() ? "DESC" : "ASC";
sql.append(" ORDER BY ").append(orderBy).append(' ').append(direction);
```

`sortBy` here is an application-defined enum. Never append an arbitrary client-supplied column string to SQL. With Template, use `Sort` and allowed sortable properties to minimize manual column-name handling.

### 5.4. NULL Parameters and Optional Conditions

You can write a fixed SQL statement like:

```sql
WHERE (:status IS NULL OR status = :status)
```

However, this requires binding null with the exact type via `bindNull` and can prevent optimizers from leveraging indexes as effectively as a concrete predicate depending on the database. A dynamic query that adds predicates only when filters are provided is often easier to read and can yield better execution plans. Measure on your target database.

## 6. Comparing Template and Hand-Written SQL

| Criterion | R2dbcEntityTemplate with Criteria | Hand-Written SQL via DatabaseClient / @Query |
|---|---|---|
| Entity-based CRUD queries | Very suitable | Possible, but involves more mapping boilerplate |
| Simple optional filters | Easy to compose with Criteria | Must manage SQL and parameters manually |
| Sort, limit, offset | Directly supported by Query API | Written explicitly in SQL |
| Multi-table joins | Not Criteria's strength | Flexible and explicit |
| Group by, aggregates, window functions | Limited by query API | Suitable |
| Database-specific features | Depends on dialect and API support | Can be leveraged directly |
| Entity mapping | Based on entity metadata | `@Query` can map entities; DatabaseClient callbacks usually map manually |
| Custom projections | May require extra mapping | Full control over aliases and DTO mapping |
| Portability | Generally higher for standard operations | Tied to the SQL syntax written |
| SQL control | Framework generates SQL | Developer controls the statement |
| Maintainability | Concise for entity-centric queries | Good when complex SQL is named and organized clearly |

Neither option is universally better. Template reduces boilerplate and utilizes mapping metadata. Hand-written SQL provides expressiveness and granular control. Both still require testing against the real driver and database.

## 7. Practical Selection Criteria

### Choose Template When

- Queries primarily retrieve a single entity type.
- Filter conditions are equality, comparisons, ranges, or value sets.
- Filters can be toggled on/off per request.
- Standard sorting, limits, and pagination suffice.
- Updates/deletes can be expressed with a clear set of conditions.
- You want to leverage mapping metadata and reduce manual column mapping.

### Choose Hand-Written SQL When

- Multi-table joins or aggregated data are needed.
- CTEs, window functions, complex subqueries, or database-specific expressions are needed.
- Read-only projections with explicit aliases and calculations are needed.
- Exact SQL control is needed to optimize after measuring and analyzing execution plans.
- Operations cannot be expressed by the Criteria API or doing so makes code hard to read.

### Combining Both Approaches in One Application

A module can use Repositories for basic CRUD, Template for filtered searches, and `DatabaseClient` for reports or specialized queries. This is completely normal when boundaries are clear:

- Repositories hold data operations tied to an aggregate.
- A query service or custom repository holds complex queries.
- Business services coordinate results and enforce business rules.

Do not invent an overly complex unified query abstraction just to force every query through the same API. Let query form reflect actual needs.

## 8. Pagination and Sorting

### 8.1. Deterministic Sorting

When using `limit` and `offset`, a deterministic sort order is required. If sorting only by `createdAt` and multiple rows share the same timestamp, their relative order can shift between runs. Add a unique key as a secondary criterion, such as `id`, to keep ordering deterministic:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));
```

SQL equivalent:

```sql
ORDER BY created_at DESC, id DESC
```

### 8.2. Offset Pagination

Offset pagination suits small datasets and UIs requiring jumping to specific pages. However, large offsets force the database to read and skip many rows before returning results. As data grows, measure performance and consider keyset pagination.

### 8.3. Keyset Pagination

Keyset pagination uses the last values of the previous page as a marker. For example, sorting descending by `created_at`, then `id`:

```sql
SELECT id, order_code, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
```

Tuple comparison syntax is not supported identically across all databases; the equivalent condition can be written using an `OR` expression:

```sql
AND (created_at < :lastCreatedAt
     OR (created_at = :lastCreatedAt AND id < :lastId))
```

Template can express simple keyset conditions with nested/composed Criteria if your framework version's API supports it clearly. When conditions grow hard to read or need specific tuple comparisons, hand-written SQL is easier to control.

### 8.4. Counting Total Results

To display total pages, a `COUNT(*)` query with the same filters may be needed. For complex queries with joins/grouping, the count query may need a different structure than the data query. Do not assume every Template query automatically provides total row counts when using `limit`/`offset`. Determine whether the API truly needs a total count or only needs to know if a next page exists.

## 9. Mapping Hand-Written SQL Results

When using `DatabaseClient`, choose the result type based on need:

- Entity if results include all required columns and appropriate entity mapping is desired.
- DTO/projection if results come from joins, aggregations, or a subset of columns.
- Scalar if the query returns a single value like `COUNT(*)`.

DTO example for a join query:

```java
public record OrderSummary(
        Long id,
        String orderCode,
        String customerName,
        Long lineCount
) {
}
```

With mapping callbacks, SQL aliases should be clear and consistent with DTO field names:

```sql
SELECT o.id,
       o.order_code AS order_code,
       c.display_name AS customer_name,
       COUNT(ol.id) AS line_count
FROM ...
```

Read columns by alias inside the callback and convert to appropriate Java types. Some databases/drivers may return different numeric types for aggregate expressions; verify the actual runtime type instead of casting blindly.

## 10. Performance and Maintainability

### 10.1. Measure Before Optimizing

Hand-written SQL is not inherently faster than Template-generated SQL. Performance depends on indexes, row counts, predicate selectivity, join order, database statistics, connection pool, and payload transferred to the application. Use execution plans and metrics to locate bottlenecks before changing query approaches.

### 10.2. Fetch Only Needed Columns

For summary screens, projections reading only used columns reduce I/O and network traffic. When using full entities, check whether entities contain large fields or data unneeded by the use case.

### 10.3. Avoid N+1 Queries

Reading a list of orders and then firing a customer query per order scales query count linearly with rows. Consider SQL joins/projections or a single batch query fetching customers by ID set. R2DBC is a non-blocking API, yet it does not make hundreds of redundant queries free.

### 10.4. Naming and Organizing Queries

Long SQL queries belong in custom repositories or query services named after business intent. Avoid assembling SQL in controllers or scattering query builder snippets across services. For Criteria, extract predicate builder methods if filters are reused while keeping intent clear.

### 10.5. Cross-Database Portability

Template leverages dialects for supported abstraction operations, reducing cross-database differences. Hand-written SQL must be verified when switching databases: functions, data types, paging syntax, JSON operators, locking clauses, and comparison rules can differ. If a project targets a single database, engine-specific SQL can be reasonable when benefits are clear.

## 11. Common Mistakes

### Using Criteria for Overly Complex Queries

When simulating multiple joins, aggregates, and nested conditions takes layers of builder code, SQL intent becomes obscured. Use direct SQL if it expresses the query more clearly.

### Using Hand-Written SQL for Every Simple Operation

CRUD and basic filters can be handled concisely by Repositories or Template. Writing custom SQL for every operation adds unnecessary mapping code and maintenance overhead.

### Concatenating Input Values into SQL Strings

This is a source of injection bugs. Bind all values via named or positional parameters. Concatenate only fixed structures controlled by the application; whitelist column names and sort directions.

### Omitting Tenant or Access Control Conditions

Dynamic queries with many branches can easily drop data-scoping conditions by mistake. Security constraints like tenant, owner, or permission scope must be enforced in every query branch and tested explicitly.

### Using Column Names Instead of Property Names in Criteria

Criteria works with entity mapping metadata. Check property/column naming rules of your version, especially when using snake_case or `@Column`. Integration tests help catch wrong column name errors.

### Paginating Without Deterministic Sorting

Results can duplicate or disappear between pages when multiple rows share sort values. Add a unique key as a secondary criterion and consider keyset pagination for large offsets.

### Assuming Template Update Always Equals Read-Then-Save

Query-based bulk updates bypass per-entity domain behaviors. If per-object validation, auditing, or optimistic locking is needed, choose the appropriate flow and verify exact API behavior.

## 12. Workflow for Selecting and Implementing Queries

1. Identify output data: full entity, projection, or scalar.
2. List mandatory conditions, optional conditions, and authorization rules.
3. Check whether the query is clearly expressible with `Criteria` or requires joins/aggregates/specialized SQL.
4. Choose Template for simple entity-centric queries; choose hand-written SQL when query structure needs direct control.
5. Bind all input values; whitelist identifiers and sort options.
6. Design deterministic sorting, cap page sizes, and choose offset or keyset appropriately.
7. Verify indexes and execution plans against realistic data.
8. Test empty data, nulls, combined filters, tenant boundaries, and multi-row cases.
9. Test against the target database/driver and monitor query durations in production.

## 13. Summary Checklist

- [ ] Criteria fits simple predicates and optional filters.
- [ ] Query supports sort, limit, and offset for standard pagination.
- [ ] Hand-written SQL fits joins, aggregates, CTEs, window functions, and database-specific features.
- [ ] Appropriate result type chosen: entity, DTO/projection, or scalar.
- [ ] All data values bound via parameters; never concatenated directly into SQL.
- [ ] Dynamic column names and sort directions chosen from a whitelist.
- [ ] Tenant and access-control conditions present in every query branch.
- [ ] Omitted filters distinguished from `NULL` search conditions.
- [ ] Deterministic sort and sensible page limits in place.
- [ ] Complex queries verified with execution plans and proper indexes.
- [ ] Integration tests run against the target database/driver.

Template and hand-written SQL are complementary tools in Spring Data R2DBC. Use Criteria when queries center on entities and standard conditions; use direct SQL when joins, aggregations, or database features must be expressed precisely. Safe parameter handling, clear mapping, and testing against a real database keep dynamic queries both maintainable and operationally sound.
