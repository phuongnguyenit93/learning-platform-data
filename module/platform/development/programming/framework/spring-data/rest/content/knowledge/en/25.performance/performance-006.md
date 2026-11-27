# Count Query Cost, Page, Slice, and Paginating Large Datasets

Pagination lets an API return data in chunks instead of loading an entire collection. In Spring Data, **Page<T>**, **Slice<T>**, and scrolling mechanisms solve different needs:

- **Page<T>** provides the current content along with total record count and total page count. To obtain an accurate total, the framework typically needs to execute an additional count query.
- **Slice<T>** indicates whether a next page exists without computing the total record count.
- **Keyset scrolling** uses values of the sort columns as a cursor to fetch the next portion of data, well suited for sequential traversal of large datasets.

Choosing the wrong return type or pagination style can turn an apparently simple endpoint into a database bottleneck. Decide based on what information clients genuinely need and how users traverse the data.

## 1. Pagination with Pageable

Spring Data uses **Pageable** to describe the requested page, page size, and sort order.

Repository example:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
~~~

A service can construct a page request:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<Order> page = orderRepository.findByStatus(
    OrderStatus.PAID,
    pageable
);
~~~

Page indices start at **0**. The first page is **PageRequest.of(0, 20)**, and the next page is **PageRequest.of(1, 20)**.

With Spring Data REST, collection resources typically accept query parameters:

~~~http
GET /orders?page=0&size=20&sort=createdAt,desc&sort=id,desc
Accept: application/hal+json
~~~

- **page**: zero-based page index.
- **size**: requested number of elements on a page.
- **sort**: property name and sort direction (**asc** or **desc**); multiple criteria can be passed.

Sorting by multiple properties keeps ordering deterministic. For example, **createdAt** values may collide, so adding **id** as a tie-breaker determines the order among records sharing the same timestamp.

## 2. Page<T> Provides the Total Record Count

**Page<T>** extends the information in a **Slice<T>** with metadata about the entire result set:

- Content of the current page.
- Current page number and page size.
- Number of elements on the page.
- Total number of elements matching the filter criteria.
- Total number of pages.
- First/last page status.

Example:

~~~java
Page<Order> page = orderRepository.findByStatus(
    OrderStatus.PAID,
    PageRequest.of(0, 20)
);

long total = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

The **totalElements** and **totalPages** information is useful when a UI needs to display “1–20 of 8,450 orders”, allow jumping to the last page, or show exact page numbers.

In return, the database must count the total rows matching the condition. For complex queries or large tables, the count query can take substantial time—sometimes slower than the content query itself.

## 3. Why Does Page Usually Trigger a Count Query?

The content query needs to fetch a portion of data, typically using **LIMIT** and **OFFSET** or the database's equivalent syntax. However, that query does not by itself tell how many total records match.

Therefore, Spring Data JPA typically executes two queries:

1. **Content query** to fetch the rows of the current page.
2. **Count query** to count the total rows matching the same filter condition.

Conceptual SQL example:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

Corresponding count query:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

The count query does not need to return entity columns or apply sorting. It only needs to accurately count the result set represented by the content query.

Not every Page invocation necessarily executes a count query in all cases; Spring Data can infer the total count in certain situations from the page content. However, when clients require exact totals, budget for count query cost and measure on realistic data.

## 4. Optimizing Count Queries with @Query

For query methods with complex conditions, Spring Data may not derive an optimal count query from JPQL or native SQL. You can declare a dedicated **countQuery** attribute inside **@Query**.

Example:

~~~java
@Query(
    value = """
        select o
        from Order o
        where o.status = :status
          and o.createdAt >= :from
        """,
    countQuery = """
        select count(o)
        from Order o
        where o.status = :status
          and o.createdAt >= :from
        """
)
Page<Order> findRecentByStatus(
    @Param("status") OrderStatus status,
    @Param("from") Instant from,
    Pageable pageable
);
~~~

The content query may require joins to retrieve data, whereas the count query only needs to count the root entity. If joining a collection causes an order to appear multiple times, consider **count(distinct o.id)** to avoid duplicate counting.

Example:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.product_id = ?;
~~~

When designing a count query:

- Keep the exact same filter conditions so the total matches the content query.
- Omit **ORDER BY** since sorting is unnecessary for counting.
- Omit unnecessary **FETCH JOIN** clauses from the count query.
- Check whether one-to-many joins multiply row counts.
- Use **COUNT(DISTINCT ...)** when query semantics require counting unique entities.
- For native queries, declare an explicit matching count query if the framework cannot derive one accurately.

Do not optimize a count query by dropping filter conditions or counting the wrong dataset. An inaccurate total produces misleading pagination metadata for clients.

## 5. Slice<T> Avoids the Count Query

If the UI only needs to know “is there more data to view?”, **Slice<T>** is often a better fit than **Page<T>**.

Example:

~~~java
import org.springframework.data.domain.Slice;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Slice<Order> findByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
~~~

A Slice provides page content along with details such as:

- **hasNext()** — whether a next slice of data exists.
- **hasPrevious()** — whether a previous slice exists.
- **getNumberOfElements()** — number of elements in the current slice.
- **getSize()** — requested page size.

To determine **hasNext**, Spring Data typically fetches one extra row beyond the requested size. For instance, if the client requests 20 rows, the query may fetch up to 21 rows. If a 21st row exists, Slice knows more data follows; that extra row is excluded from the page content.

This avoids running a full count query over the entire result set. Slice does not provide **totalElements** or **totalPages**, so a UI cannot show exact totals if it relies solely on Slice.

Use Slice for infinite-scroll lists, “Load more” buttons, or interfaces that only need Next/Previous controls.

## 6. Choosing Between Page and Slice Based on UI Needs

| Need | Suitable type | Reason |
|---|---|---|
| Show total results and total page count | **Page<T>** | Total metadata is needed |
| Allow jumping to the last page | **Page<T>** | Total page count must be known |
| “Load more” button or infinite scroll | **Slice<T>** | Only needs to know if a next page exists |
| Sequential traversal of very large data | Keyset scrolling | Avoids growing offsets |
| Bulk data export | Scrolling or batch processing | Avoids loading the entire dataset into memory |

Do not use Page merely because default repository methods are easy to write. If the UI neither displays totals nor needs page jumping, the count query can be pure wasted cost.

Conversely, do not use Slice if the product requires displaying exact totals. In that case, Page or a separate counting strategy is more appropriate.

## 7. Cost of Offset Pagination on Large Datasets

Offset pagination is commonly expressed as:

~~~sql
SELECT *
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 50 OFFSET 500000;
~~~

The database must locate and discard a large number of rows before returning a deep page. As offset grows, cost can increase accordingly even though the client receives only 50 rows.

Offset pagination remains useful when:

- The dataset is moderate in size.
- Users need to jump to arbitrary pages.
- Total page count is required.
- The database has indexes aligned with filter criteria and sort order.

However, for very large tables or sequential browsing flows, deep offsets are usually a poor choice. They can also produce duplicate or skipped results when rows are inserted or deleted between client page requests.

## 8. Maintaining Deterministic Ordering and Creating Appropriate Indexes

A paginated query needs deterministic ordering. Sorting solely by **createdAt** when multiple records share the same timestamp allows the database to return varying orders across calls.

Add a unique key as the final tie-breaker:

~~~java
Pageable pageable = PageRequest.of(
    pageNumber,
    pageSize,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Indexes should align with common filter predicates and sort orders. For example, a query frequently filtering by **status** and sorting by **created_at**, **id** can benefit from a matching composite index:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON orders(status, created_at DESC, id DESC);
~~~

This is only an example; index column ordering should reflect selectivity, actual queries, and the database engine. Use **EXPLAIN** or execution plan analysis tools to confirm the database uses the index as intended.

Also cap page size so clients cannot request tens of thousands of rows in a single request.

## 9. Limiting Page Size in Spring Data REST

Spring Data REST allows configuring default and maximum page sizes:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestRepositoryConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
~~~

With this configuration:

- If a client omits **size**, the server uses the default size of 20.
- Clients cannot request a page larger than the cap of 100 via Spring Data REST's pageable resolver.

Choose limits based on response size, entity complexity, lazy loading, network conditions, and database load. An overly large page size increases memory usage, serialization time, and connection hold duration.

For custom controllers, apply equivalent limits to incoming **Pageable** inputs; do not assume Spring Data REST's limit automatically covers every MVC controller.

## 10. Keyset Scrolling for Large Datasets

Keyset scrolling uses the values of the last row in the current window as a cursor for the next query.

Instead of asking to “skip 500,000 rows”, the client/server asks to “fetch rows after the last seen sort key”.

For example, a query sorted descending by **createdAt** and **id** can use an equivalent continuation condition:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Comparison operators must match the sort direction. For ascending order, the continuation operators reverse.

Spring Data supports a scrolling API with **Window<T>** and **ScrollPosition** in supported versions:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public interface OrderRepository extends Repository<Order, Long> {

    Window<Order> findFirst50ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus status,
        ScrollPosition position
    );
}
~~~

Starting a keyset scroll:

~~~java
Window<Order> window =
    orderRepository.findFirst50ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus.PAID,
        ScrollPosition.keyset()
    );
~~~

You can obtain the last position of the window to continue:

~~~java
if (!window.isEmpty() && window.hasNext()) {
    ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

    Window<Order> nextWindow =
        orderRepository.findFirst50ByStatusOrderByCreatedAtAscIdAsc(
            OrderStatus.PAID,
            nextPosition
        );
}
~~~

Exact syntax and scrolling capabilities depend on the Spring Data module version. Check your project's version API before using it.

For keyset scrolling to work reliably:

- The sort order must be deterministic and end with a unique key, typically the primary key.
- Keyset properties should hold suitable values, avoiding nulls that complicate determining the next position.
- The projection/result must supply the values needed to construct the keyset.
- Database indexes should support the filter and sort columns.
- Cursors must be bound to the query's filter and sort; do not reuse an old cursor for a different query.

Keyset scrolling fits sequential traversal, batch processing, and cursor APIs. It does not inherently supply total page counts and is inconvenient for jumping to arbitrary pages.

## 11. Designing a Cursor API

If you want clients to use a cursor instead of a page number, a custom endpoint can accept an opaque cursor:

~~~http
GET /orders?limit=50&cursor=eyJjcmVhdGVkQXQiOi...
~~~

The response can return the content and next cursor:

~~~json
{
  "items": [
    {
      "id": 1201,
      "status": "PAID"
    }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}
~~~

The cursor should encode or sign the information needed to continue the query, such as the last sort values, filters, sort direction, and cursor version. Avoid letting clients edit internal values directly if doing so could alter query scope.

Handle cases where data changes between calls. Keyset pagination reduces offset-drift issues, yet does not automatically create a consistent snapshot across the entire traversal. If the use case requires snapshot semantics, add appropriate transaction, watermark, or snapshot strategies.

## 12. Testing Pagination Performance

Do not measure only overall API response time. Separate the components:

1. Content query time.
2. Count query time when using Page.
3. Entity and relationship serialization time.
4. Number of SQL statements executed.
5. Response size and memory usage.
6. Query execution plans on the first page and on deep pages.

You can enable SQL logging in development or use datasource metrics to confirm Page executes a count query. Use database **EXPLAIN**/**EXPLAIN ANALYZE** to inspect scans, indexes, joins, and sorts.

A test should compare:

- The first page and a page with a large offset.
- Page versus Slice under the same filter criteria.
- Auto-generated count queries versus custom count queries.
- Offset pagination versus keyset scrolling with the same sort order.

Draw optimization conclusions only after measuring on data whose scale and distribution resemble production.

## 13. Common Errors and Remedies

| Symptom | Possible cause | Remedy |
|---|---|---|
| Endpoint is slow despite returning only 20 rows | Expensive count query | Use Slice if total count is not needed, or optimize **countQuery** |
| Total elements exceeds unique entity count | One-to-many join duplicates rows | Use an appropriate count distinct |
| Deep pages are much slower | Large offset | Use keyset scrolling for sequential traversal flows |
| Records duplicated or skipped across pages | Non-unique sort or mutating data | Add a unique key to sort; consider cursors |
| Client requests an overly large page size | Pageable not bounded | Configure default/max page size |
| Count query includes unnecessary joins/fetches | Suboptimal derived count query | Declare a dedicated **countQuery** |
| Keyset cannot find the next position | Sort lacks a unique key or keyset fields are null | Add a tie-breaker and choose suitable fields |
| Response is too heavy despite small page size | Entity serializes many relationships | Use an appropriate projection, excerpt, or DTO |

## 14. Selection Rules

- Use **Page<T>** when clients genuinely need total elements or total pages.
- Use **Slice<T>** when you only need to know whether more data follows.
- Use offset pagination when arbitrary page jumping is needed and dataset size is appropriate.
- Use keyset scrolling/cursors when sequentially traversing large datasets.
- Declare an explicit **countQuery** when the auto-generated query is inefficient or inaccurate.
- Guarantee deterministic sorting with a unique key.
- Create indexes matching actual filters and sorts; verify with execution plans.
- Cap page sizes to protect database, memory, and network resources.
- Measure content queries, count queries, and serialization separately before optimizing.

Official references:

- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Spring Data JPA — Query Methods and Paging](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
