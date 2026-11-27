# Paginating Native Queries and Declaring countQuery

## 1. Why Do Native Queries Need Attention to countQuery?

Spring Data JPA lets you write native SQL with `@Query(nativeQuery = true)` to leverage database-specific syntax or features, handle complex queries, CTEs, window functions, hints, or SQL structures that JPQL cannot express conveniently.

When results need pagination, the repository method typically accepts a `Pageable` and returns `Page<T>`. A page carries two pieces of information:

- **Content:** the list of records for the current page.
- **Metadata:** total elements, total pages, current page number, page size, and whether a next page exists.

To build the total metadata, Spring Data needs the total number of rows matching the filter criteria. For native queries, automatically deriving a count query from arbitrary SQL structures is not always reliable. Therefore, you should declare `countQuery` explicitly for native queries, especially when `JOIN`, `DISTINCT`, `GROUP BY`, CTEs, or subqueries are involved.

A paginated native query typically consists of two statements with distinct purposes:

1. A data query retrieving the exact rows belonging to the current page.
2. A count query returning the total number of logical results matching the filter criteria.

Both queries must describe the exact same result set. If the content query filters by status and creation date while the count query omits a condition, total pages will be wrong even when the current page's data is right.

## 2. Pageable, Page, and Pagination Mechanics

### 2.1. Pageable

`Pageable` describes a pagination request:

- `pageNumber`: page index, starting from `0`.
- `pageSize`: maximum number of elements in a page.
- `sort`: sorting information if supported by the query.

Creating a page request:

```java
Pageable pageable = PageRequest.of(0, 20);
```

This requests the first page with up to 20 results. The second page:

```java
Pageable pageable = PageRequest.of(1, 20);
```

Do not confuse Spring Data's zero-based page numbers with 1-based page numbers displayed in user interfaces.

### 2.2. Page

`Page<T>` contains both content and total metadata:

```java
Page<PurchaseOrder> page =
    repository.searchOrders("PAID", from, PageRequest.of(0, 20));

List<PurchaseOrder> orders = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Because `Page` provides total elements and total pages, the framework generally needs to execute a count query. Spring Data can optimize certain cases by inferring the total from the content, but you should not design under the assumption that the count query will always be skipped.

### 2.3. Slice

If the UI only needs to know whether more data is available to load next and does not need the total record count, you can use `Slice<T>`. A `Slice` typically fetches one extra element to determine if a next page exists and avoids the total count query.

With native queries, `Slice` support depends on how the query is declared and the Spring Data JPA version. If you want explicit control, you can use `Pageable` with a custom repository or a size-limited query checking for an extra row. Choose `Page` when total page counts actually matter to the user.

### 2.4. Who Applies LIMIT/OFFSET?

When passing `Pageable` to a repository query, Spring Data JPA applies the starting position and maximum results through the JPA query API. The JPA provider, such as Hibernate, translates those into pagination syntax suitable for the database dialect.

Consequently, the native query can keep just the filtering and sorting SQL; you do not need to append `LIMIT`/`OFFSET` to the SQL string when `Pageable` is already applied. The actual syntax is determined by the dialect. Manually adding `LIMIT`/`OFFSET` alongside `Pageable` can paginate twice or produce wrong results.

## 3. Basic Native Query With countQuery

Suppose the `purchase_order` table stores orders with columns `id`, `order_no`, `status`, `created_at`, and `total_amount`. The `PurchaseOrder` entity is fully mapped to this table.

The repository can be written as:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            select o.*
            from purchase_order o
            where o.status = :status
              and o.created_at >= :from
            order by o.created_at desc, o.id desc
            """,
        countQuery = """
            select count(*)
            from purchase_order o
            where o.status = :status
              and o.created_at >= :from
            """,
        nativeQuery = true
    )
    Page<PurchaseOrder> searchOrders(
        @Param("status") String status,
        @Param("from") LocalDateTime from,
        Pageable pageable
    );
}
```

This example targets Spring Data JPA using Java text blocks. The corresponding imports and entity must exist in the project.

Key points to note:

- `nativeQuery = true` marks both `value` and `countQuery` as database SQL.
- `value` fetches data for the current page.
- `countQuery` counts all results matching the same criteria.
- `@Param` binds SQL parameter names to method parameters.
- `Pageable` is used by Spring Data to restrict the page window.
- `order by o.created_at desc, o.id desc` guarantees a deterministic order when multiple orders share the same creation timestamp.

Because the query returns `PurchaseOrder`, `SELECT` must return all columns required by the entity mapping. `o.*` works when the table matches the entity's persistent columns and joins do not introduce column name collisions. For multi-table join queries, explicitly select the root entity's columns or use a DTO projection.

Invocation:

```java
Pageable firstPage = PageRequest.of(0, 20);

Page<PurchaseOrder> result =
    repository.searchOrders(
        "PAID",
        LocalDateTime.of(2026, 1, 1, 0, 0),
        firstPage
    );

System.out.println(result.getNumber());
System.out.println(result.getSize());
System.out.println(result.getNumberOfElements());
System.out.println(result.getTotalElements());
System.out.println(result.getTotalPages());
```

Printed values depend on the data in the database; fixed stdout cannot be shown without a concrete fixture. In real code, content and metadata are typically returned to a service or controller rather than printed to the console.

## 4. countQuery Must Count the Exact Result Set

### 4.1. Preserve Filter Conditions

The most important rule is that the content query and count query must share the exact same filter conditions.

Content example:

```sql
select o.*
from purchase_order o
where o.status = :status
  and o.created_at >= :from
order by o.created_at desc, o.id desc
```

Corresponding count:

```sql
select count(*)
from purchase_order o
where o.status = :status
  and o.created_at >= :from
```

The count query does not need `ORDER BY`, because ordering does not affect total row count and only adds unnecessary work.

Never omit a filter in the count query. If the content query filters by tenant, access permissions, status, or date, the count query must apply those same filters so it does not leak total record counts outside the user's permitted scope.

### 4.2. JOINs Can Multiply Rows

Suppose an order has multiple line items. Query:

```sql
select o.*
from purchase_order o
join order_item i on i.order_id = o.id
where i.sku = :sku
order by o.created_at desc, o.id desc
```

If an order has multiple items with the same SKU, a single order can appear multiple times in the join result. If the goal is to paginate by order, deduplicate the content query:

```sql
select distinct o.*
from purchase_order o
join order_item i on i.order_id = o.id
where i.sku = :sku
order by o.created_at desc, o.id desc
```

The count query must count unique order IDs:

```sql
select count(distinct o.id)
from purchase_order o
join order_item i on i.order_id = o.id
where i.sku = :sku
```

Using `count(*)` in this example would count joined rows rather than orders. `totalElements` and `totalPages` would therefore exceed the actual entity count.

Another option is using `EXISTS` to avoid row multiplication:

```sql
select o.*
from purchase_order o
where exists (
    select 1
    from order_item i
    where i.order_id = o.id
      and i.sku = :sku
)
order by o.created_at desc, o.id desc
```

Corresponding count:

```sql
select count(*)
from purchase_order o
where exists (
    select 1
    from order_item i
    where i.order_id = o.id
      and i.sku = :sku
)
```

`EXISTS` cleanly expresses "orders having at least one matching line item" and avoids duplicate root rows. Actual performance depends on indexes and the query optimizer.

### 4.3. DISTINCT and Count Distinct

When a content query returns `DISTINCT` root entities, the count query needs to count unique root entities. `count(distinct o.id)` is not always sufficient if the projection is a combination of multiple columns or an aggregated group. Identify the exact unit `Page` is paginating: an entity, a DTO, or an aggregated group.

If the query returns one row per `GROUP BY` group, the count query must count the number of groups rather than total source rows. You can use a subquery:

```sql
select count(*)
from (
    select o.status
    from purchase_order o
    where o.created_at >= :from
    group by o.status
) grouped_result
```

This illustrates SQL for databases supporting derived tables in `FROM`. For complex queries, writing an explicit count query or using a custom repository is clearer than relying on automatic SQL rewriting.

## 5. Native Queries With JOIN, CTE, and Complex Structures

Native SQL can use CTEs, window functions, database functions, or specialized syntax not conveniently supported by JPQL. These constructs make automatic count query derivation harder.

CTE example:

```sql
with recent_orders as (
    select o.id, o.status, o.created_at
    from purchase_order o
    where o.created_at >= :from
)
select r.id, r.status, r.created_at
from recent_orders r
where r.status = :status
order by r.created_at desc, r.id desc
```

The count query must count the same result set after all filters:

```sql
with recent_orders as (
    select o.id, o.status, o.created_at
    from purchase_order o
    where o.created_at >= :from
)
select count(*)
from recent_orders r
where r.status = :status
```

You cannot mechanically strip `SELECT` or `ORDER BY` when a query uses `DISTINCT`, `GROUP BY`, `HAVING`, `UNION`, or nested subqueries. The count query must preserve every clause that affects the resulting row set.

Some Spring Data JPA versions include a query enhancer/parser to help rewrite simple or complex native SQL. Capabilities depend on the version and which parser is on the classpath. For complex queries, declaring `countQuery` explicitly is the easiest approach to control and review.

## 6. Sorting in Native Queries

### 6.1. Fixed ORDER BY

The simplest option is placing the ordering directly in SQL:

```sql
order by o.created_at desc, o.id desc
```

Then pass a `Pageable` without `Sort`:

```java
Pageable pageable = PageRequest.of(0, 20);
```

The ordering should include a unique tie-breaker, usually the primary key. If you sort only by `created_at` and multiple rows share the same timestamp, the database may return them in varying order across executions. When paging, rows can be duplicated or skipped.

### 6.2. Dynamic Sorting Depends on Version and Query Parser

Whether dynamic `Sort` can be injected into a native query depends on the Spring Data JPA version and its SQL parsing/rewriting mechanism. Simple queries may be handled, whereas complex SQL, aliases, CTEs, or vendor-specific syntax can cause rewriting to fail or generate invalid SQL.

If an API requires multiple sort options, verify your framework version and test each option. Safe alternatives include defining separate query variants for supported sort fields or using a custom repository that selects SQL from an allowlisted set of columns and sort directions.

Never bind column names or `ASC`/`DESC` keywords as ordinary SQL parameters. Parameter binding is for values only. If you must build dynamic `ORDER BY`, use only identifiers and sort directions from an application-defined allowlist; never concatenate user-supplied sort strings directly into SQL.

### 6.3. Count Queries Do Not Need Sorting

A count query only returns the total element count and does not need `ORDER BY`. Including an unnecessary `ORDER BY` in a count query can cause extra database work or trigger syntax errors depending on query structure.

## 7. Mapping Native Query Results

### 7.1. Returning Entities

When a method returns `Page<PurchaseOrder>`, the native query must supply enough columns for Hibernate to hydrate the entity.

Example:

```sql
select o.*
from purchase_order o
where o.status = :status
```

If you select only `o.id, o.order_no` while the entity has additional required persistent fields, the provider may throw an error or fail to map completely. When joining multiple tables, avoid selecting two columns with the same name without distinct aliases.

Do not use a native entity query just to select a few columns and treat the result as a full entity. When only partial data is needed, use a projection or DTO.

### 7.2. Interface Projections

You can return an interface projection if column aliases match the getter names:

```java
public interface OrderSummary {
    Long getId();
    String getOrderNo();
    BigDecimal getTotalAmount();
}
```

Query:

```java
@Query(
    value = """
        select
            o.id as id,
            o.order_no as orderNo,
            o.total_amount as totalAmount
        from purchase_order o
        where o.status = :status
        order by o.created_at desc, o.id desc
        """,
    countQuery = """
        select count(*)
        from purchase_order o
        where o.status = :status
        """,
    nativeQuery = true
)
Page<OrderSummary> findSummariesByStatus(
    @Param("status") String status,
    Pageable pageable
);
```

Aliases must be chosen according to how your Spring Data/provider version maps projections. On databases that distinguish identifier casing or fold unquoted aliases to lowercase, test the actual mapping behavior.

### 7.3. DTO Classes and SqlResultSetMapping

For DTO classes or results with complex types, you can use JPA's `@SqlResultSetMapping` and `@ConstructorResult`, or a custom repository to read native results and map explicitly.

Do not assume all native queries automatically map DTO constructors identically across Spring Data JPA versions. For complex mappings, integration tests are essential.

## 8. Page and Count Queries Have Separate Costs

A `Page` call typically requires:
- A content query for the current page.
- A count query to compute total rows.

The count can be significantly expensive if the query has multiple `JOIN`s, `DISTINCT`, `GROUP BY`, CTEs, or unindexed filters. Do not optimize only the content query while ignoring the count query.

Ways to reduce overhead:

1. Use `Slice` if the total element count is unnecessary.
2. Write a minimal count query that still counts the exact logical result set.
3. Use `EXISTS` when you only need to check whether related records exist.
4. Add indexes for filter conditions and join columns.
5. Avoid unnecessary `JOIN`s in both content and count queries.
6. Inspect execution plans separately for both SQL statements.
7. Cap page size at the API layer.

A count query may have to scan many rows to return an exact total. If the UI does not truly require the last page number, `Slice` or keyset pagination may be a better fit.

## 9. Offset Pagination and Frequently Changing Data

`PageRequest` uses page number and page size, corresponding to offset pagination. For example, page `100` with size `20` must skip roughly 2,000 rows before returning results.

Large offsets can become slow because the database still has to locate and discard many rows. Additionally, if data changes between two requests, inserting a new record near the top can cause subsequent pages to repeat or skip rows.

To mitigate these risks:
- Always use a deterministic `ORDER BY` with a unique tie-breaker.
- Use an appropriate transaction/snapshot if multiple pages must remain consistent within a read session.
- For large datasets or rapidly changing data, consider keyset/seek pagination.

Keyset example by `created_at` and `id`:

```sql
select o.*
from purchase_order o
where o.created_at < :lastCreatedAt
   or (
       o.created_at = :lastCreatedAt
       and o.id < :lastId
   )
order by o.created_at desc, o.id desc
fetch first :limit rows only
```

Row-limiting syntax depends on the database; the SQL above illustrates the key-pair seek concept. Keyset pagination does not naturally yield total page counts like `Page`, but it works well for "load more" flows over large datasets.

## 10. Testing Native Pagination

Tests should verify both content and metadata. Example using the repository from earlier:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void returnsPageAndCorrectTotal() {
        LocalDateTime from = LocalDateTime.of(2026, 1, 1, 0, 0);

        repository.saveAll(List.of(
            new PurchaseOrder("PO-001", "PAID", from.plusDays(1)),
            new PurchaseOrder("PO-002", "PAID", from.plusDays(2)),
            new PurchaseOrder("PO-003", "PAID", from.plusDays(3)),
            new PurchaseOrder("PO-004", "CANCELLED", from.plusDays(4))
        ));

        Page<PurchaseOrder> page = repository.searchOrders(
            "PAID",
            from,
            PageRequest.of(0, 2)
        );

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
        assertThat(page.hasNext()).isTrue();
    }
}
```

This is an illustrative example; `PurchaseOrder`'s constructor and mapping must match the test schema. If using an embedded database, native SQL must be compatible with its dialect. For vendor-specific SQL, run integration tests against the same database engine used in production.

Additional scenarios worth testing:

- First page, middle page, and last page.
- Page index beyond the available pages.
- Empty result sets.
- Two or more rows sharing the same sort value.
- `JOIN` multiplying root entities.
- `DISTINCT` and count distinct.
- Nullable filters if the query supports optional parameters.
- Page size `1` and the maximum allowed page size.
- Content and count queries enforcing identical tenant/access filters.

## 11. Common Pitfalls

| Error | Cause | Resolution |
|---|---|---|
| Total pages higher than reality | `countQuery` uses `count(*)` after a one-to-many `JOIN` | Use `count(distinct root.id)` or `EXISTS` |
| Content is right but total is wrong | `countQuery` is missing a filter condition | Synchronize all predicates between both queries |
| Query does not paginate | Method omits `Pageable` or is invoked improperly | Add `Pageable` to the repository method and pass `PageRequest` |
| Paginated twice | SQL already contains `LIMIT`/`OFFSET` while `Pageable` is also applied | Let the provider apply `Pageable` or manage pagination in a custom query—never both |
| Entity mapping error | Native `SELECT` omits columns or has alias collisions | Select all entity columns or use projection/DTO |
| Dynamic sort fails | Parser cannot rewrite complex native SQL | Use fixed `ORDER BY` or a custom repository with an allowlist |
| Pages duplicate or skip rows | `ORDER BY` lacks a unique tie-breaker or data changed | Add primary key to ordering; consider snapshots/keyset |
| Slow count query | `JOIN`, `DISTINCT`, or unindexed filter | Simplify count query, use `EXISTS`, inspect execution plan |
| Wrong total with `GROUP BY` | Counting source rows instead of groups | Count a subquery containing the same `GROUP BY` |
| Query works locally but fails in production | SQL/dialect/alias/collation differences | Run integration tests on the same database engine as production |

## 12. Checklist Before Deploying Native Pagination to Production

- [ ] Content query returns the right unit to paginate: entity, DTO, or group.
- [ ] `countQuery` counts the exact same result set.
- [ ] Every filter and access-control condition appears in both queries.
- [ ] One-to-many `JOIN`s do not multiply root rows when paginating roots.
- [ ] `count(distinct ...)` or `EXISTS` is used where appropriate.
- [ ] Count query omits unnecessary `ORDER BY`.
- [ ] Content `ORDER BY` includes a unique tie-breaker.
- [ ] `Pageable` is applied only once.
- [ ] Dynamic sorting only accepts allowlisted values and is compatible with the parser.
- [ ] Entity mapping selects all required columns; projections have clear aliases.
- [ ] Total count is actually required for `Page`; otherwise consider `Slice` or keyset.
- [ ] Execution plans inspected separately for content and count queries.
- [ ] Integration tests run on a database matching production.

## 13. Conclusion

Paginating native queries in Spring Data JPA requires a SQL statement for content and a `countQuery` that accurately counts total results. `Pageable` describes page index and size; the JPA provider applies dialect-specific pagination. `countQuery` must preserve the same filter conditions and count the right logical unit, especially when `JOIN`, `DISTINCT`, or `GROUP BY` are present.

For simple queries, `count(*)` may suffice. For one-to-many `JOIN`s, `count(distinct root.id)` or `EXISTS` is typically needed. For grouped queries, a count subquery must count groups. Complex native queries should declare `countQuery` explicitly for predictability.

Use deterministic ordering, verify sorting behavior for your Spring Data version, map results with accurate types, measure count overhead separately, and consider `Slice` or keyset pagination when total pages are unnecessary or offsets grow large. Integration tests on a real database provide final verification for syntax, dialect, mapping, and pagination metadata.