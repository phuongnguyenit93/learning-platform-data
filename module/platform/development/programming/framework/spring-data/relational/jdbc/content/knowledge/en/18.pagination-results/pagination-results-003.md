# `Page`, `count` Queries, and Total Result Counts

In **Spring Data Relational JDBC**, pagination is more than just limiting the number of SQL rows returned. When a repository method returns `Page<T>`, the application also receives metadata about the current page and the total number of results matching the query criteria. To know the total count, Spring Data JDBC may run an additional `COUNT` statement alongside the `SELECT` statement that fetches the page content.

Three result types commonly need to be distinguished:

- **`Page<T>`**: page content, navigation info, and total element/total page counts. May require an additional `COUNT` query.
- **`Slice<T>`**: page content and whether a next page exists. Typically fetches one extra element (`pageSize + 1`) to determine `hasNext()`, without needing the overall total.
- **`List<T>` combined with `Pageable`**: fetches only the data within the page range; does not create `Page` metadata and does not need a count query.

Choose the return type based on what the UI or use case actually needs. If the screen needs “page 2 of 14” and “273 results”, use `Page`. If it only needs a “Load more” button, `Slice` is usually more economical. If it only needs a bounded list, `List` with `Pageable` avoids the cost of counting totals.

## 1. `Pageable` Represents a Pagination Request

`Pageable` is an object carrying the page number, page size, offset, and sorting details. Spring Data uses it to build query limits.

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
);
```

Values in the example:

| Component | Value | Meaning |
|---|---:|---|
| Page number | `0` | First page; page numbers start at 0 |
| Page size | `20` | At most 20 elements on a page |
| Offset | `0` | Skip 0 elements before fetching the page |
| Sort | `createdAt DESC, id ASC` | Newest first, using ID to break ties |

Offset is calculated from page number and page size:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

For example, `PageRequest.of(2, 20)` requests the third page (in user-facing counting), corresponding to `OFFSET 40` and `LIMIT 20` in SQL. Do not confuse the API's zero-based page number with the 1-based page numbers usually shown in UIs.

`Pageable` also holds `Sort`, so do not pass an extra `Sort` parameter on a method that already accepts `Pageable`. APIs accepting `Pageable` expect a non-null value; if you truly do not want pagination, use `Pageable.unpaged()` on APIs that support it.

## 2. Declaring a Repository Returning `Page<T>`

Spring Data JDBC supports query methods returning `Page<T>` with a `Pageable` parameter. Example simple entity:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @Column("created_at")
    private Instant createdAt;

    // constructors, getters, domain methods...
}
```

Repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface PurchaseOrderRepository extends
        CrudRepository<PurchaseOrder, Long>,
        PagingAndSortingRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(String status, Pageable pageable);
}
```

`PagingAndSortingRepository` provides pagination/sorting abstractions; `CrudRepository` provides `save`, `findById`, `delete`, and CRUD operations. In modern Spring Data versions, these two interfaces are separate contracts, so declare both if you need both CRUD and paging/sorting.

Calling the repository:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
);

Page<PurchaseOrder> page = purchaseOrderRepository.findByStatus("OPEN", pageable);

List<PurchaseOrder> orders = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

`findByStatus` is a **derived query**: Spring Data parses the method name to build `status = ?`, then applies pagination. Spring Data JDBC currently limits query derivation to simple properties directly on the aggregate root; it does not automatically generate JOINs to query properties of other aggregates or child entities.

## 3. What Metadata Does `Page` Provide?

`Page<T>` extends `Slice<T>` and adds the total result count. Commonly used methods:

| Method | Meaning |
|---|---|
| `getContent()` | List of elements on the current page |
| `getNumber()` | Current page number, starting at 0 |
| `getSize()` | Requested page size |
| `getNumberOfElements()` | Actual number of elements on the current page |
| `getTotalElements()` | Total number of matching elements across the entire result set |
| `getTotalPages()` | Total number of pages given the page size |
| `hasNext()` / `hasPrevious()` | Whether there is a next/previous page |
| `isFirst()` / `isLast()` | Whether it is the first/last page |
| `getSort()` | Applied sorting information |

Example with 237 matching orders, 20 elements per page:

| Metadata | Value |
|---|---:|
| Current page | 1 / 12 |
| Total results | 237 |
| Page size | 20 |
| Displayed range | 1–20 |

Page count is rounded up:

\[
\text{totalPages} = \left\lceil \frac{\text{totalElements}}{\text{pageSize}} \right\rceil
\]

With 237 elements and page size 20, the total page count is 12. The last page has only 17 elements. If there are no results, total elements is 0 and total pages is 0.

`getTotalElements()` is not the element count of the current page; use `getNumberOfElements()` for the actual content size. Distinguishing these two values avoids mistakenly displaying “20 results” when the system actually has thousands of results.

## 4. Why Can `Page` Run an Extra `COUNT` Query?

To return `Page<T>`, the framework needs to know:

1. Which rows belong to the requested page.
2. The total number of matching rows, unbounded by `LIMIT/OFFSET`.

Therefore, a single request may generate two logical queries:

```sql
-- Fetch the content of the current page
SELECT id, status, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id ASC
LIMIT :pageSize OFFSET :offset;

-- Count total orders matching the condition
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status;
```

The `COUNT` query must use **the same filter conditions** as the content query. It must not apply `LIMIT/OFFSET`; otherwise `totalElements` would only reflect the page's row count rather than the total results.

Spring Data JDBC can derive the count query from a derived query. The documentation describes `Page` as *potentially* requiring a count query; depending on the case, the framework may infer enough metadata from the page result and skip executing a count. Therefore, do not write tests or optimizations assuming every `Page` call always emits exactly two statements in every scenario.

### Count Must Count Aggregate Roots, Not Duplicated JOIN Rows

In a multi-table model, a JOIN can duplicate root rows. For example, an order with three line items produces three rows when joining `purchase_order` with `order_line` for the same order. If you need to count the number of **orders**, `COUNT(*)` over the JOIN could count three.

In custom SQL, choose a counting approach matching the object the API returns:

```sql
-- Count aggregate roots, avoiding duplication from child rows
SELECT COUNT(DISTINCT o.id)
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE l.product_id = :productId;
```

Or use `EXISTS` when only checking for a matching child:

```sql
SELECT COUNT(*)
FROM purchase_order o
WHERE EXISTS (
    SELECT 1
    FROM order_line l
    WHERE l.order_id = o.id
      AND l.product_id = :productId
);
```

Counting the right target is essential for `totalElements` and `totalPages` to be meaningful.

## 5. Default Count Query of Derived Queries

With a method like:

```java
Page<PurchaseOrder> findByStatusAndCreatedAtAfter(
        String status,
        Instant from,
        Pageable pageable
);
```

Spring Data JDBC generates the content query based on the conditions:

```sql
WHERE status = :status
  AND created_at > :from
```

The count query is derived from the same predicate, omitting page limits and sorting:

```sql
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status
  AND created_at > :from;
```

You do not need to declare a `countBy...` method just for `Page` to work. If you want an independent count in another use case, the repository can declare `long countByStatus(String status)` or use `count(...)` at the appropriate layer.

Example:

```java
public interface PurchaseOrderRepository extends
        CrudRepository<PurchaseOrder, Long>,
        PagingAndSortingRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(String status, Pageable pageable);

    long countByStatus(String status);
}
```

`countByStatus` is an independent count query; it does not load entities into Java to count them. With derived queries, conditions still must reference valid properties on the aggregate root per Spring Data JDBC's query derivation constraints.

## 6. `Slice<T>` When Total Count Is Not Needed

`Slice<T>` only needs to know whether a next element exists. To determine that, Spring Data JDBC may fetch `pageSize + 1` rows. For example, with page size 20, the framework reads up to 21 rows:

- 21 rows returned → content keeps the first 20 rows and `hasNext()` is `true`.
- 20 or fewer rows returned → no extra row, `hasNext()` is `false`.

```java
Slice<PurchaseOrder> findByStatus(String status, Pageable pageable);
```

Example call:

```java
Slice<PurchaseOrder> slice = repository.findByStatus(
        "OPEN",
        PageRequest.of(0, 20, Sort.by("id").ascending())
);

List<PurchaseOrder> content = slice.getContent();
boolean hasNext = slice.hasNext();
```

`Slice` does not provide `getTotalElements()` or `getTotalPages()` because it does not have the overall total. This fits feeds, activity lists, scrollable histories, or “Load more” UIs.

## 7. `List<T>` with `Pageable`: Limiting Data Without Counting

If a method returns `List<T>` and accepts `Pageable`, Spring Data still applies offset, limit, and sort, without creating `Page` metadata. Consequently, no count query needs to run:

```java
List<PurchaseOrder> findByStatus(String status, Pageable pageable);
```

This is a good choice when the caller only needs the page content and manages navigation itself or does not need to know whether a next page exists. However, `List` lacks `hasNext()`; if knowing whether more data remains is needed, choose `Slice`.

### Comparing the Three Return Types

| Type | Content | Knows if next page exists? | Knows total count? | Count query |
|---|---|---|---|---|
| `Page<T>` | Yes | Yes | Yes | May be needed |
| `Slice<T>` | Yes | Yes | No | Not needed to determine `hasNext()` |
| `List<T>` + `Pageable` | Yes | No | No | No |

If the count query is the most expensive part of the request, switching from `Page` to `Slice` can substantially reduce cost. Only do so when the UI/business logic genuinely does not need the total count.

## 8. Stable Sorting to Prevent Duplicate or Missing Rows

Offset-based pagination requires a deterministic order. If you sort by a non-unique column such as `createdAt DESC`, multiple orders with the same timestamp can appear in different orders across two requests. Under concurrent inserts/updates, users may see an item repeated across two pages or skipped.

Add a unique tie-breaker key:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        )
);
```

`id` makes the order deterministic when multiple rows share the same `createdAt`. Sort properties use the **Java property name** in the domain mapping, not the SQL column name if the two differ. For example, if property `createdAt` maps to `created_at`, use `Sort.by("createdAt")`.

A stable sort does not turn multiple page requests into a consistent snapshot. If data changes between when the client loads page 0 and page 1, offsets can still shift. If a consistent snapshot is needed, use appropriate transaction/read isolation or design a cursor/keyset based on a stable sort key.

## 9. Offset Pagination and Deep-Page Costs

SQL using `LIMIT/OFFSET` is easy to use:

```sql
SELECT id, status, created_at
FROM purchase_order
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 200000;
```

However, at large offsets, the database may still have to read/scan and discard many rows before returning the desired page. Hence the first page is typically much faster than a very deep page.

Options when offsets become expensive:

- Use `Slice` to skip the total count if the UI only needs to continue forward.
- Use keyset/seek pagination based on the last values of the previous page.
- Cap the maximum page number or require narrower filters.
- Create indexes aligned with filter conditions and sort order.
- Use specialized queries for reporting rather than loading full aggregates.

Spring Data Commons provides scrolling/keyset abstractions in certain modules and versions, though support depends on the store implementation. Do not assume all `ScrollPosition` or keyset APIs are supported identically in Spring Data JDBC; check the API for your exact version. If keyset is needed in Spring Data JDBC, you can implement a custom repository query with an explicit seek predicate.

Example keyset SQL by `(created_at, id)` descending/ascending respectively:

```sql
SELECT id, status, created_at
FROM purchase_order
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at DESC, id ASC
LIMIT :pageSize;
```

The seek predicate must match the sort order exactly and handle nulls consistently. Keyset works well for “next page” traversal, but is inconvenient for jumping directly to page 500 like offset pagination.

## 10. `@Query` in Spring Data JDBC Does Not Automatically Support `Pageable`

This is a key difference to watch out for if you are familiar with Spring Data JPA. Current Spring Data JDBC documentation explicitly states that **string-based queries declared with `@Query` do not support pagination and do not accept `Sort`, `PageRequest`, or `Limit` as special parameters**. The framework does not rewrite your custom SQL string to add limit/offset.

The following is not a valid way to ask Spring to automatically add pagination to a SQL string:

```java
// Do not use this approach with Spring Data JDBC string-based @Query.
@Query("SELECT * FROM purchase_order WHERE status = :status")
List<PurchaseOrder> findByStatus(String status, Pageable pageable);
```

In addition, Spring Data JDBC's `org.springframework.data.jdbc.repository.query.Query` annotation **does not have a `countQuery` attribute** like Spring Data JPA's `@Query`. Do not copy JPA examples containing `countQuery = "SELECT COUNT..."` into JDBC.

When complex SQL is needed alongside pagination and total counts, two common approaches are:

1. Write a custom repository implementation using `NamedParameterJdbcTemplate`, adding `LIMIT/OFFSET` yourself and writing a `COUNT` query with the same predicate.
2. For mapping queries using Spring Data Relational `Query`, use `Query.with(pageable)` to limit/sort, call `JdbcAggregateOperations.findAll(Query, Class)` for content and `count(Query, Class)` for total, and construct `PageImpl`.

### Approach A: Custom Repository with Separate SQL and Count

Example DTO for a list screen:

```java
public record OrderSummary(Long id, String status, Instant createdAt) {}
```

Content SQL and count SQL must share the same conditions:

```sql
-- Content query
SELECT id, status, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id ASC
LIMIT :limit OFFSET :offset;

-- Count query
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status;
```

In the custom repository, execute both queries and construct `Page`:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("status", status)
        .addValue("limit", pageable.getPageSize())
        .addValue("offset", pageable.getOffset());

List<OrderSummary> content = namedParameterJdbcTemplate.query(
        contentSql,
        params,
        (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toInstant()
        )
);

Long total = namedParameterJdbcTemplate.queryForObject(
        countSql,
        new MapSqlParameterSource("status", status),
        Long.class
);

return new PageImpl<>(content, pageable, total == null ? 0 : total);
```

This snippet illustrates code inside a custom repository implementation; `contentSql` and `countSql` are declared SQL constants, and sorting must be translated into a **whitelisted** list of columns/directions. Never concatenate client-supplied column names directly into SQL because sort identifiers cannot be bound like regular parameters and can introduce SQL injection. For APIs allowing limited sorting, map an API enum/field to fixed SQL identifiers.

If the query performs a one-to-many JOIN, count roots using `COUNT(DISTINCT root.id)` or `EXISTS` as shown earlier; otherwise, the total can exceed the actual number of DTOs/roots.

### Approach B: `JdbcAggregateOperations` and `Query.with(Pageable)`

For queries using Criteria/mapping metadata, Spring Data JDBC provides `JdbcAggregateOperations` with `findAll(Query, Class)` and `count(Query, Class)`. Direct pagination APIs such as `findAll(Query, Class, Pageable)` were deprecated as of Spring Data Relational 4.0; the current API guidance is to combine a query with offset/limit and a separate count to construct `Page`.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

public Page<PurchaseOrder> findOpenOrders(Pageable pageable) {
    Query filter = Query.query(Criteria.where("status").is("OPEN"));

    List<PurchaseOrder> content = aggregateOperations.findAll(
            filter.with(pageable),
            PurchaseOrder.class
    );

    long total = aggregateOperations.count(filter, PurchaseOrder.class);

    return new PageImpl<>(content, pageable, total);
}
```

`Query.with(pageable)` carries offset, limit, and sort into the query. Use the original `filter` for the count so the total is not bounded by the page. This is Spring Data Relational's query-mapping API, distinct from the repository string-based `@Query` annotation.

## 11. The Count Query Can Be the Most Expensive Part

A content query can use an index and stop after fetching 20 rows. A count query has to count all rows satisfying the predicate, potentially scanning a large data range. On tables with millions of rows, `COUNT(*)` is not always cheap, especially with complex filter conditions or JOINs.

Ways to reduce cost:

- If the UI does not need the total count, return `Slice` or `List` + `Pageable`.
- Optimize predicates and indexes for filter conditions.
- With JOIN queries, write count queries that count the root accurately, avoiding unnecessary joins.
- Do not request repeated counts across services/UI if the result can be reused within the same response.
- For large dashboards/reports, consider summary tables/materialized views or separately updated aggregate metrics.
- If the total count is only informational and staleness is acceptable, consider caching or a suitable projection; make the semantics clear to users.

Do not use a cached count value to replace an exact total in business logic enforcing quotas/limits if the cache can be stale. UI pagination and business-rule checks are two distinct use cases.

## 12. Consistency Between Content Query and Count Query

`Page` comprises content and total count, yet the two SQL queries may execute as two separate statements. If data changes between the two statements, content and total may not reflect the same snapshot depending on transaction/isolation level.

Example:

1. Content query fetches 20 orders.
2. Another transaction inserts 5 matching orders.
3. Count query runs afterward and returns the new total.

In this case, `Page` has content from the first point in time but `totalElements` from the second. For most list screens, small transient discrepancies are acceptable. If a consistent snapshot is required, design transaction/read isolation suitable for the database and use case while weighing the cost of holding the transaction.

Do not keep a long transaction open while a user navigates across multiple pages. Each page request is typically an independent unit of read work; if a snapshot across multiple requests is required, a dedicated snapshot/version/cursor strategy is needed.

## 13. Testing Pagination and Total Counts

Tests should verify both content and count:

```java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired PurchaseOrderRepository repository;

    @Test
    void returnsPageContentAndTotalCount() {
        repository.save(new PurchaseOrder("OPEN"));
        repository.save(new PurchaseOrder("OPEN"));
        repository.save(new PurchaseOrder("OPEN"));
        repository.save(new PurchaseOrder("CLOSED"));

        Page<PurchaseOrder> page = repository.findByStatus(
                "OPEN",
                PageRequest.of(0, 2, Sort.by("id").ascending())
        );

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
        assertThat(page.hasNext()).isTrue();
    }
}
```

The example requires a corresponding `purchase_order` schema and a `PurchaseOrder` constructor allowing status initialization. Tests should also cover:

- The last page having fewer than `pageSize` elements.
- A page beyond the total results returning empty content while total remains accurate.
- Zero matching results (`totalElements = 0`, `totalPages = 0`).
- Multiple rows sharing the same sort value; ID tie-breaker preserving deterministic order.
- Count and content filters not drifting out of sync.
- Count over a JOIN not double-counting aggregate roots.
- `Slice` determining `hasNext()` accurately without needing a total count.

To prove whether a count query was actually executed, use SQL logging or a datasource proxy/statement-counting instrumentation. Receiving the right `Page` values alone does not prove the expected query count, as the framework may optimize away the count in certain cases.

## 14. Common Errors

| Symptom | Possible cause | Solution |
|---|---|---|
| `totalElements` equals only the number of elements on the page | Caller counted `content.size()` instead of using Page metadata, or the count query was limited | Use `Page<T>` with a derived query or an unpaged count query |
| Wrong `totalPages` | Count query uses a different predicate from content query | Synchronize filter conditions and bind parameters |
| Unusually large total count | Count on a one-to-many JOIN duplicated roots | Use `COUNT(DISTINCT root.id)` or `EXISTS` |
| No total count available | Method returns `Slice` or `List` | Use `Page` if total metadata is truly required |
| `@Query` ignores `Pageable` | Spring Data JDBC string-based `@Query` does not support pagination | Write custom repository SQL + count or use `JdbcAggregateOperations` with `Query.with(pageable)` |
| `countQuery` is not recognized | Confusing JDBC annotation with Spring Data JPA | JDBC `@Query` has no `countQuery` attribute; write the count query in a custom implementation |
| Deep pages run slowly | Large offset | Use keyset/seek pagination, cap deep pages, and add indexes |
| Duplicate/missing rows across pages | Non-unique sort or data changes between requests | Add a unique tie-breaker, consider cursor/snapshot |
| Sort property does not exist | Using SQL column name instead of Java property or typo in field | Use domain property name and verify mapping |
| H2 tests pass but production is slow/fails | Different dialect, execution plan, or indexes | Test against production database/driver using Testcontainers |

## 15. Workflow for Choosing `Page`, `Slice`, or `List`

1. **Identify what the UI/use case needs.** Are exact total counts and page counts needed?
2. **If totals are needed:** declare a derived method returning `Page<T>` and taking `Pageable`; the framework may generate a count query.
3. **If only knowing whether more data remains is needed:** use `Slice<T>` to fetch one extra element and check `hasNext()`.
4. **If only bounded content is needed:** use `List<T>` with `Pageable`, generating no metadata or count.
5. **If using `@Query` SQL:** remember string-based queries do not support `Pageable`/`Sort`/`Limit`; implement custom limit/offset SQL and count separately or use the query mapping API.
6. **Choose a stable sort:** add a unique key as a tie-breaker.
7. **Measure count and offset costs:** inspect execution plans, indexes, statement counts, and page depth.
8. **Test totals:** especially with JOINs, filters, last page, empty pages, and concurrent data changes.

### Quick Decision Table

| Requirement | Return type / approach |
|---|---|
| Need `totalElements` and `totalPages` | `Page<T>` |
| Only need `hasNext()` | `Slice<T>` |
| Only need a partial list | `List<T>` + `Pageable` |
| Simple derived query on root properties | Repository method + `Pageable` |
| Custom SQL with JOIN/aggregation | Custom repository + separate content SQL and count SQL |
| Criteria-mapped query | `Query.with(pageable)` + `findAll(Query, type)` + `count(Query, type)` + `PageImpl` |
| Very large datasets, deep offsets | Keyset/seek pagination or appropriate cursor |

**Core takeaway:** `Page` provides total result counts and therefore may require an extra `COUNT` query; `Slice` only checks whether a next page exists; `List` + `Pageable` fetches only bounded content. In Spring Data JDBC, derived repository queries support `Pageable`, whereas string-based `@Query` does not automatically support pagination and lacks JPA's `countQuery` attribute. When custom SQL is required, explicitly control both the content query and count query and ensure both use identical filter conditions.

## Official References

- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): `Page`, `Slice`, `Pageable`, `List` with pagination and limitations of string-based `@Query`.
- [Spring Data Commons — Query Methods Details](https://docs.spring.io/spring-data/relational/reference/data-commons/repositories/query-methods-details.html): choosing `Page`, `Slice`, `List`, count cost, and offset pagination.
- [Spring Data JDBC — `JdbcAggregateOperations` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): `findAll(Query, Class)`, `count(Query, Class)`, and template pagination APIs deprecated since 4.0.
- [Spring Data Relational — `Query` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html): `with(Pageable)`, `limit`, `offset`, and `sort`.
- [Spring Data JDBC — `@Query` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Query.html): JDBC annotation attributes; no `countQuery`.
- [Spring Data Commons — `Page` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html): total count metadata and page navigation.
- [Spring Data Commons — `PageRequest` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html): creating zero-based pagination requests.
