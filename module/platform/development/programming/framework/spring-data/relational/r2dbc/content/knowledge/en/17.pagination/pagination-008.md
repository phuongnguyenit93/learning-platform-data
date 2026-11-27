# Pagination with Dynamic Filters, Joins, and Aggregate Queries

A list screen in an application often needs more than a simple `SELECT` query. Users may filter by status, date range, customer, or keyword; results may also need customer names from a related table, line-item counts, or grouped revenue totals. As record volumes grow, the application must also bound returned results page by page.

In Spring Data R2DBC, this type of query can be built using `R2dbcEntityTemplate` with `Query`/`Criteria`, or using custom SQL via `DatabaseClient`/`@Query`. Whichever API you choose, a complete paginated query usually needs to solve three separate concerns: accurately defining the filtered result set, sorting/paginating deterministically, and counting total elements at the right business grain.

## 1. Components of a Paginated Query

A paginated result typically comprises:

- **Filters:** mandatory and optional conditions supplied by the use case.
- **Ordering:** allowlisted sort fields plus a secondary key to ensure deterministic order.
- **Current page:** page number and page size, or a keyset pagination cursor.
- **Page data:** rows or aggregated groups belonging to that page.
- **Total count:** total number of logical rows matching the filter, if the UI needs total pages.

For example, an order admin screen needs to filter by tenant, status, and date range, displaying order code, customer name, line-item count, and total amount. Results must be sorted newest first and return 20 orders per page.

```text
Request filters + page/sort
           |
           v
   Validate and normalize
           |
           v
      Build predicates
           |
      +----+----------------+
      |                     |
      v                     v
 Content query          Count query
 filters + joins        same logical filters
 sort + limit/offset    count logical results
      |                     |
      v                     v
  Page rows             Total count
      |                     |
      +----------+----------+
                 |
                 v
       Page response / DTO
```

For simple single-entity queries, Repositories or Templates may suffice. When multi-table joins and aggregations are needed, hand-written SQL usually expresses the data shape more accurately.

## 2. Designing Pagination Requests and Responses

### 2.1. Filter Object

Bundle search criteria into a dedicated type rather than passing many loose parameters across layers:

```java
public record OrderSearchFilter(
        Long tenantId,
        String status,
        Long customerId,
        Instant createdFrom,
        Instant createdTo,
        int page,
        int size,
        OrderSort sort
) {
}

public enum OrderSort {
    CREATED_DESC,
    CREATED_ASC,
    AMOUNT_DESC
}
```

`tenantId` is a mandatory data-scope condition. `status`, `customerId`, and timestamps can be optional. `sort` is an application-controlled enum; never accept arbitrary SQL column names directly from clients.

Before querying, validate:

- `page` is non-negative.
- `size` is greater than 0 and does not exceed the application's allowed cap.
- `createdFrom` is not after `createdTo`.
- `tenantId` comes from the authenticated context or is authorization-checked; never trust a client-supplied tenant ID blindly.
- Status values belong to the valid set of statuses.

### 2.2. Page Response

Spring Data R2DBC uses reactive types such as `Mono` and `Flux`. For paginated queries with total counts, you can define a custom response:

```java
public record PageResult<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        long totalPages
) {
}
```

`PageResult` is an application/API DTO, not an entity. Total pages is derived from `totalElements` and `size`; if the API only needs a "Load more" button, you can omit the count query and use `size + 1` to determine whether more data remains.

### 2.3. Safe Offset Calculation

With offset pagination, the formula is:

\[
\text{offset} = \text{page} \times \text{size}
\]

Use overflow-checked multiplication and cap pages at the request layer:

```java
long offset = Math.multiplyExact((long) filter.page(), filter.size());
```

If values are too large, return a validation error instead of letting a negative or overflowed offset enter the query. Very large offsets can also be slow even without overflowing; consider keyset pagination in such cases.

## 3. Single-Entity Pagination with R2dbcEntityTemplate

For queries filtering on a single entity type, `R2dbcEntityTemplate` and `Criteria` can build both the content query and count query from the same conditions.

### 3.1. Building Shared Criteria

```java
private Criteria buildCriteria(OrderSearchFilter filter) {
    Criteria criteria = Criteria.where("tenantId").is(filter.tenantId());

    if (filter.status() != null && !filter.status().isBlank()) {
        criteria = criteria.and("status").is(filter.status());
    }

    if (filter.customerId() != null) {
        criteria = criteria.and("customerId").is(filter.customerId());
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("createdAt")
                .greaterThanOrEquals(filter.createdFrom());
    }

    if (filter.createdTo() != null) {
        criteria = criteria.and("createdAt")
                .lessThan(filter.createdTo());
    }

    return criteria;
}
```

The tenant condition is always included. Other conditions are added only when values are present. Distinguish clearly between "filter not provided" and "find rows where column is `NULL`"; those two cases require separate request representations if the business needs both.

Names in `Criteria` are entity property names, such as `createdAt` or `customerId`. Spring Data's mapping metadata maps them to database columns. Verify `Criteria` APIs and property names against your project's Spring Data Relational version.

### 3.2. Building Content Query and Count Query

```java
public Mono<PageResult<OrderEntity>> search(OrderSearchFilter filter) {
    Criteria criteria = buildCriteria(filter);
    long offset = Math.multiplyExact((long) filter.page(), filter.size());

    Query contentQuery = Query.query(criteria)
            .sort(Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")))
            .limit(filter.size())
            .offset(offset);

    Query countQuery = Query.query(criteria);

    return template.select(contentQuery, OrderEntity.class)
            .collectList()
            .flatMap(content -> template.count(countQuery, OrderEntity.class)
                    .map(total -> new PageResult<>(
                            content,
                            filter.page(),
                            filter.size(),
                            total,
                            total / filter.size()
                                    + (total % filter.size() == 0 ? 0 : 1))));
}
```

The content query includes sort, limit, and offset. The count query uses the same `Criteria` without sort, limit, or offset. As a result, `totalElements` reflects all entities matching the filter rather than just the current page's row count.

The example uses `flatMap` to run count after the content query finishes. This sequential flow is easy to manage when queries share a single reactive transaction/connection. If no transaction is required and the two queries are independent, consider `Mono.zip(contentMono, countMono)` for concurrent execution; verify driver limits, connection pool capacity, and transaction behavior before doing so.

### 3.3. Count Query Must Strip Pagination

A common mistake is reusing a `Query` that already has limit/offset for counting. The count may then reflect only the rows on the page rather than the full result set. The count query must keep identical predicates while stripping sort, limit, and offset.

If filters might mutate between constructing the two queries, build both from a single validated/normalized filter object. Never maintain two independent condition builders that could drift apart.

## 4. Dynamic Filters with Joins Using Custom SQL

When results need data from multiple tables or aggregate calculations, `DatabaseClient` can be used. For example, an orders page displaying customer name, line-item count, and total amount per order.

### 4.1. Result DTO

```java
public record OrderPageRow(
        Long id,
        String orderCode,
        String status,
        String customerName,
        Instant createdAt,
        Long lineCount,
        BigDecimal totalAmount
) {
}
```

This is a read projection. It can combine columns from multiple tables and aggregate values that do not exist on `OrderEntity`.

### 4.2. Content SQL

```sql
SELECT o.id,
       o.order_code,
       o.status,
       c.display_name AS customer_name,
       o.created_at,
       COUNT(ol.id) AS line_count,
       COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total_amount
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
WHERE o.tenant_id = :tenantId
  AND o.status = :status
GROUP BY o.id, o.order_code, o.status,
         c.display_name, o.created_at
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset
```

`LEFT JOIN` preserves orders that have no line items yet. `COUNT(ol.id)` returns 0 for orders without lines; `COALESCE` turns a null sum into 0. Non-aggregated selected columns must be listed in `GROUP BY` per your database's SQL syntax.

### 4.3. Count SQL for the Same Set of Orders

In this example, each order has exactly one customer and filters only touch columns on `orders`. Orders can be counted directly:

```sql
SELECT COUNT(*)
FROM orders o
WHERE o.tenant_id = :tenantId
  AND o.status = :status
```

Do not include `order_lines` in the count merely because the content query joins it. If the count query joins a one-to-many table, each order with multiple lines can be counted multiple times. When a join is required for filtering, use `COUNT(DISTINCT o.id)` or an appropriate `EXISTS` to count logical orders accurately.

### 4.4. Assembling Filters and Binding Parameters

With optional filters, construct the `WHERE` clause dynamically from fixed SQL fragments and bind every value:

```java
StringBuilder where = new StringBuilder(" WHERE o.tenant_id = :tenantId ");

if (filter.status() != null && !filter.status().isBlank()) {
    where.append(" AND o.status = :status ");
}
if (filter.customerId() != null) {
    where.append(" AND o.customer_id = :customerId ");
}
if (filter.createdFrom() != null) {
    where.append(" AND o.created_at >= :createdFrom ");
}
if (filter.createdTo() != null) {
    where.append(" AND o.created_at < :createdTo ");
}
```

Use the exact same `where`-building helper for both content and count queries so the two queries never apply different filters. Only fixed, application-controlled syntax fragments are appended to SQL; request values are always bound via named parameters.

Parameter binding example:

```java
DatabaseClient.GenericExecuteSpec bindFilters(
        DatabaseClient.GenericExecuteSpec spec,
        OrderSearchFilter filter) {

    spec = spec.bind("tenantId", filter.tenantId());

    if (filter.status() != null && !filter.status().isBlank()) {
        spec = spec.bind("status", filter.status());
    }
    if (filter.customerId() != null) {
        spec = spec.bind("customerId", filter.customerId());
    }
    if (filter.createdFrom() != null) {
        spec = spec.bind("createdFrom", filter.createdFrom());
    }
    if (filter.createdTo() != null) {
        spec = spec.bind("createdTo", filter.createdTo());
    }

    return spec;
}
```

Do not call `.bind(name, null)` to represent null. For intentional null parameters, use `bindNull(name, type)` or design the predicate accordingly. When null means "do not apply filter", the clearest pattern is omitting both the predicate and that parameter.

### 4.5. Whitelisting Dynamic Sorts

Column names and sort directions are SQL structure, not values bindable via `:sortColumn`. Map client choices against an allowlist:

```java
String orderBy = switch (filter.sort()) {
    case CREATED_ASC -> "o.created_at ASC, o.id ASC";
    case CREATED_DESC -> "o.created_at DESC, o.id DESC";
    case AMOUNT_DESC -> "total_amount DESC, o.id DESC";
};
```

Use only constant SQL strings inside the switch. Never concatenate arbitrary column names or `ASC`/`DESC` strings from the request into queries.

## 5. Counting Accurately When Joins Are Present

The count query is the easiest part to get wrong when paginating with joins. Before writing the count, determine the unit the UI is paginating: orders, customers, order lines, or aggregated groups.

### 5.1. One-to-Many JOINs Multiply Rows

Suppose an order has 4 order lines. The query:

```sql
SELECT o.id, ol.id
FROM orders o
JOIN order_lines ol ON ol.order_id = o.id
```

returns 4 rows for the same `o.id`. `COUNT(*)` over the joined result counts 4, while the list page may display only one order.

When paginating by order, the count must count unique orders:

```sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_lines ol ON ol.order_id = o.id
WHERE o.tenant_id = :tenantId
```

If you only need to check whether an order has at least one matching line, `EXISTS` often avoids row multiplication:

```sql
SELECT COUNT(*)
FROM orders o
WHERE o.tenant_id = :tenantId
  AND EXISTS (
      SELECT 1
      FROM order_lines ol
      WHERE ol.order_id = o.id
        AND ol.product_code = :productCode
  )
```

Choose `COUNT(DISTINCT ...)` or `EXISTS` based on query structure and execution plans. The goal is counting the exact logical unit.

### 5.2. LEFT JOIN and COUNT

With `LEFT JOIN`, `COUNT(*)` still counts one row for an order without child lines because the parent row remains present. `COUNT(ol.id)` counts only child rows with non-null IDs and returns 0 when none exist. When counting line items, use `COUNT(ol.id)` instead of `COUNT(*)`.

### 5.3. DISTINCT Can Change Meaning

`COUNT(DISTINCT o.id)` is right when paginating by order. If the UI actually paginates individual order lines, count by order line. Never add `DISTINCT` just to make numbers look reasonable; clarify what record type each row on the page represents.

## 6. Paginating Aggregate Queries

A report may paginate by group, such as total revenue per customer. Each result row is then a `customer_id` group, not an individual order.

### 6.1. Grouped Query

```sql
SELECT o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.total_amount) AS revenue
FROM orders o
WHERE o.tenant_id = :tenantId
  AND o.created_at >= :from
  AND o.created_at < :to
GROUP BY o.customer_id
ORDER BY revenue DESC, o.customer_id ASC
LIMIT :limit OFFSET :offset
```

Pagination is applied after `GROUP BY` and `ORDER BY`. Limiting orders before grouping produces aggregates over a partial subset rather than the full requested period.

### 6.2. Count Groups, Not Individual Orders

To compute total page elements, count the customers forming groups:

```sql
SELECT COUNT(*)
FROM (
    SELECT o.customer_id
    FROM orders o
    WHERE o.tenant_id = :tenantId
      AND o.created_at >= :from
      AND o.created_at < :to
    GROUP BY o.customer_id
) grouped_customers
```

The count query must apply the exact same filters and group definition. `COUNT(*) FROM orders` would count orders, not customers in the report.

### 6.3. HAVING and Filtering on Aggregates

If the report only shows customers whose revenue exceeds a threshold, that condition belongs in `HAVING`:

```sql
SELECT o.customer_id,
       SUM(o.total_amount) AS revenue
FROM orders o
WHERE o.tenant_id = :tenantId
GROUP BY o.customer_id
HAVING SUM(o.total_amount) >= :minimumRevenue
```

The count query must apply the same `HAVING`, typically by counting rows from a subquery containing `GROUP BY` and `HAVING`:

```sql
SELECT COUNT(*)
FROM (
    SELECT o.customer_id
    FROM orders o
    WHERE o.tenant_id = :tenantId
    GROUP BY o.customer_id
    HAVING SUM(o.total_amount) >= :minimumRevenue
) result_groups
```

Conditions on aggregates cannot be replaced by `WHERE` before grouping. `WHERE` filters input rows; `HAVING` filters groups after aggregation.

## 7. Content Query and Count Query in a Reactive Pipeline

### 7.1. Combining Results

With custom SQL, create two publishers: one fetching the current page's rows and one fetching the total count. Then combine them into `PageResult`.

```java
Mono<List<OrderPageRow>> contentMono = contentSpec
        .map((row, metadata) -> new OrderPageRow(
                row.get("id", Long.class),
                row.get("order_code", String.class),
                row.get("status", String.class),
                row.get("customer_name", String.class),
                row.get("created_at", LocalDateTime.class)
                        .toInstant(ZoneOffset.UTC),
                row.get("line_count", Long.class),
                row.get("total_amount", BigDecimal.class)))
        .all()
        .collectList();

Mono<Long> countMono = countSpec
        .map((row, metadata) -> row.get("total", Long.class))
        .one()
        .defaultIfEmpty(0L);

return contentMono.flatMap(content -> countMono.map(total ->
        new PageResult<>(content, filter.page(), filter.size(), total,
                total / filter.size()
                        + (total % filter.size() == 0 ? 0 : 1))));
```

The time-mapping snippet illustrates columns read as `LocalDateTime`; actual types depend on the database, driver, and time zone conventions. In applications, standardize temporal types and converters instead of assuming every database returns the same type.

The example runs content before count to demonstrate sequential execution. If both publishers are independent and do not share a transaction/connection, `Mono.zip(contentMono, countMono)` can run them concurrently. Inside a reactive transaction—especially when both queries share one connection bound via Reactor Context—avoid assuming the driver allows two simultaneous statements on a single connection. Sequentializing queries within a transaction is more predictable.

### 7.2. Why Can Count and Content Disagree?

If records are inserted or deleted between the two queries, content and total can reflect two different states. This is often acceptable for continuously changing lists. If the business requires a consistent snapshot, run both queries in a reactive transaction and select an isolation level suited to your database.

`@Transactional(readOnly = true)` expresses read-only intent but does not guarantee snapshot isolation by itself. Consistency guarantees depend on the actual isolation level and database engine. For strict consistency requirements, configure isolation explicitly, verify driver behavior, and weigh the cost of holding transactions.

### 7.3. Not Every API Needs a Total Count

A count query can be as expensive as or more expensive than the content query, especially when filters involve joins, distinct, or group by. For infinite-scroll UIs, usually only whether more data remains is needed:

1. Query `size + 1` rows.
2. If more than `size` rows return, set `hasNext = true`.
3. Return only the first `size` rows to the client.

This eliminates the count query and usually fits large data streams better. Choose a response with `hasNext` over `totalPages` if the UI does not need total page counts.

## 8. Offset Pagination and Keyset Pagination

### 8.1. Offset Pagination

Offset fits UIs with page numbers where users need to jump directly to any page:

```sql
ORDER BY created_at DESC, id DESC
LIMIT :size OFFSET :offset
```

Advantages are simplicity and easy integration with table UIs. Disadvantages are that large offsets can force the database to traverse and skip many rows; inserts/deletes while users browse pages can also cause rows to repeat or be skipped.

### 8.2. Keyset Pagination

Keyset uses the last values from the previous page as a cursor. With `created_at DESC, id DESC`, the next-page condition is:

```sql
WHERE o.tenant_id = :tenantId
  AND (
      o.created_at < :lastCreatedAt
      OR (o.created_at = :lastCreatedAt AND o.id < :lastId)
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT :size
```

The cursor must contain all sort fields to identify a unique position, including the secondary key `id`. If it holds only `created_at` and multiple orders share the same timestamp, the next page can skip or duplicate records.

Keyset pagination is generally more efficient for deep traversal and less prone to shifts from new records added ahead of the cursor. It is inconvenient for jumping straight to page 80 because you need the previous page's cursor.

### 8.3. Keyset with Dynamic Filters

The cursor predicate is combined alongside filter predicates:

```sql
WHERE o.tenant_id = :tenantId
  AND (:status IS NULL OR o.status = :status)
  AND (
      o.created_at < :lastCreatedAt
      OR (o.created_at = :lastCreatedAt AND o.id < :lastId)
  )
```

In dynamic SQL, you can append the status predicate only when the user supplies that filter. The cursor must be generated from the same sort mode and filter context as the previous page; never reuse a cursor when the user changes filters or sort order.

### 8.4. Keyset When Sorting by Aggregates

If sorting by `SUM(total_amount)`, the cursor must contain the aggregate value and a unique tie-breaker key, such as `(revenue, customer_id)`. The cursor predicate must be applied after grouping or inside a CTE containing the aggregated results. This is a case where hand-written SQL is typically easier to control than `Criteria`.

## 9. Stable Sorting and Allowlisting

Every pagination query needs a deterministic order. When sorting by a non-unique column, add a unique key as a tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

For dynamic sorting, allowlist supported combinations:

```java
String orderBy = switch (filter.sort()) {
    case CREATED_DESC -> "o.created_at DESC, o.id DESC";
    case CREATED_ASC -> "o.created_at ASC, o.id ASC";
    case AMOUNT_DESC -> "total_amount DESC, o.id DESC";
};
```

Never bind column names via placeholders and never concatenate raw sort strings from requests. Bind parameters are only for values, never identifiers or SQL syntax.

When sorting by an aggregate alias, verify that the alias is in query scope and that the database syntax permits using aliases in `ORDER BY`. Otherwise, repeat the expression or wrap the query in a CTE/subquery.

## 10. Indexes and Query Optimization

Queries with dynamic filters, joins, and aggregates must be tuned against realistic data:

- Create indexes matching common conditions, e.g., `(tenant_id, status, created_at)` when queries frequently filter by tenant and status and sort by time.
- Index foreign keys used in joins, e.g., `orders(customer_id)` or `order_lines(order_id)`.
- Select only the columns needed for the page DTO, avoiding unused large columns.
- Evaluate indexes by selectivity and execution plans; too many indexes increase write cost and storage.
- Inspect the count query separately since count can produce a different execution plan than the content query.
- For aggregates, evaluate group/sort cost and consider summary tables or materialized views if workload demands it.
- Use production-scale datasets to measure latency, rows read, and rows returned.

Do not assume hand-written SQL is always faster than Templates. Templates can generate good SQL for standard queries; custom SQL helps when it addresses expressiveness or measured optimization needs.

## 11. Common Mistakes

### Count Query Uses Different Filters

When content filters by status and count omits that filter, totals will be wrong. Build a shared predicate or SQL `WHERE` helper for both queries.

### Counting Joined Rows Instead of Logical Items

One-to-many joins cause a parent entity to appear multiple times. Use `COUNT(DISTINCT parent.id)` or `EXISTS` when paginating by parent entity.

### Paginating Before GROUP BY

Limiting source rows before aggregation changes group results. If each page row is a group, apply group/having first and then sort and limit/offset.

### Counting Rows Instead of Groups

A customer revenue report needs the count of customers satisfying `GROUP BY`/`HAVING`, not the count of source orders. Count from a group-producing subquery.

### Using WHERE Instead of HAVING

`WHERE` filters rows before aggregation; `HAVING` filters grouped results. Conditions on `SUM`, `COUNT`, or `AVG` belong in `HAVING`.

### Omitting the Sort Tie-Breaker

If multiple rows share the same sort value, page ordering becomes unstable. Append a unique key as a secondary criterion.

### Accepting Sort Column Names from Clients

Identifiers cannot be bound as values. Use an enum/allowlist for supported sort options.

### Running Count and Content Inconsistently

Two queries can observe different data under concurrent updates. Accept eventual page metadata or use an appropriate transaction/isolation level.

### Collecting Too Much Data Before Paginating

Never load all entities and use Java `subList` to slice a page. Push filters, sort, and limit down to the database to bound I/O and memory.

## 12. Workflow for Building a Paginated Endpoint

1. Identify the paginated unit: parent entity, joined row, or aggregate group.
2. Design the filter DTO and validate mandatory conditions, authorization, and page size.
3. Pick offset pagination for page-numbered UIs; pick keyset for deep traversal or continuous scrolling.
4. Pick Template for simple entity-centric queries; pick SQL for complex joins, projections, or aggregates.
5. Build the content query with predicates, deterministic sort, and limit/cursor.
6. Build a separate count query if the API needs totals; ensure it counts the right logical unit and omits pagination.
7. For one-to-many joins, use `DISTINCT`, `EXISTS`, or subqueries to avoid over-counting.
8. For aggregates, count groups from a subquery with the same `GROUP BY` and `HAVING`.
9. Bind all values and allowlist sort identifiers.
10. Combine publishers in Reactor; choose sequential or parallel based on transactions and connection pool behavior.
11. Check transaction/isolation if content and count require the same snapshot.
12. Inspect execution plans, verify indexes, and benchmark on realistic data.

## 13. Checklist

- [ ] Filters are validated and normalized before building queries.
- [ ] Tenant/authorization conditions are always applied.
- [ ] Content query and count query share the exact same logical filters.
- [ ] Count query omits sort, limit, and offset.
- [ ] One-to-many JOINs do not over-count parent entities.
- [ ] Aggregate pagination counts groups, keeping identical `GROUP BY` and `HAVING` in count.
- [ ] Limit/offset are applied after determining the proper result set or groups.
- [ ] Sort includes a unique tie-breaker key and dynamic options use an allowlist.
- [ ] All input values are bound as parameters.
- [ ] Offset is computed safely and page size is capped.
- [ ] Keyset cursors contain all sort fields and are never reused when filters/sort change.
- [ ] Content/count are composed in a reactive pipeline without internal `block()` or `subscribe()` calls.
- [ ] Transaction/isolation meets the consistency level required by the business.
- [ ] Integration tests cover joins, count distinct, group/having, and filter combinations.
- [ ] Indexes and execution plans have been reviewed with representative data.

Paginating with dynamic filters, joins, and aggregate queries requires pinning down the exact result grain before writing content and count queries. When filters are shared, joins do not inflate logical items, aggregates are paginated after grouping, and ordering stays deterministic, an API can return consistent data with bounded query costs. In Spring Data R2DBC, Templates fit straightforward entity queries, while custom SQL fits when explicit control over joins, aggregates, and counting semantics is needed.
