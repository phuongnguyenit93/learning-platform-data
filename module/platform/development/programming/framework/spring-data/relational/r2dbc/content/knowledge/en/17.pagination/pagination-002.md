# Querying with Pageable, Sort, and Per-API Limitations

When a table holds a large amount of data, an application should not load every record just to render a single page. Spring Data R2DBC offers several ways to control result sets: sorting with `Sort`, representing a page request with `Pageable`, capping row counts with `limit`, and skipping leading rows with `offset`. These APIs differ in their support scope and semantics.

An important distinction is between **page description** and **query-limiting operations**. `Pageable` holds page number, page size, and sort order; `Sort` only describes ordering; `limit` and `offset` act directly on the query. Not every reactive repository method provides `findAll(Pageable)` or returns `Page<T>`. With Spring Data R2DBC, `R2dbcEntityTemplate` can be used to translate page information into a `Query` with sort, limit, and offset.

## 1. Why Are Pagination and Sorting Needed?

Suppose a `product` table has hundreds of thousands of records. If an endpoint calls:

~~~java
return productRepository.findAll();
~~~

the application may end up consuming the entire result set. This increases network transfer volume, processing time, database resource usage, and application-layer work.

Pagination bounds the number of rows fetched per request. Sorting defines a stable order so users can move from one page to the next.

A page typically involves:

- **Page number:** the page index, usually starting at 0 in Spring Data.
- **Page size:** the maximum number of elements desired in one page.
- **Sort:** one or more properties used for ordering.
- **Offset:** the number of rows skipped before fetching the current page.
- **Limit:** the maximum number of rows to return.

With offset pagination, the common formula is:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

For example, the 3rd page (page number 2) with size 20 has an offset of 40 and a limit of 20.

## 2. Distinguishing Pageable, Sort, limit, and offset

| Component | What Information It Holds | Effect |
| --- | --- | --- |
| `Pageable` | Page, page size, and Sort | Describes a pagination request at the application layer |
| `Sort` | Properties, ascending/descending direction, and tie-breaking order | Defines result ordering |
| `limit` | Maximum row count | Limits rows returned by the database |
| `offset` | Number of rows to skip | Determines the starting position of the page |

Example:

~~~java
Pageable pageable = PageRequest.of(
        2,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
);
~~~

This object describes page number 2, size 20, sorted by `createdAt` descending. Creating a `Pageable` does not execute a query by itself. The data access layer must use the information inside it to build SQL or a `Query`.

## 3. Sort in Reactive Repositories

`Sort` describes the ordering of results. It can sort by a single property:

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "name");
~~~

Or multiple properties:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);
~~~

In reactive repositories, `ReactiveSortingRepository` provides the `findAll(Sort sort)` method:

~~~java
public interface ProductRepository
        extends ReactiveSortingRepository<Product, Long> {
}

Flux<Product> products =
        productRepository.findAll(
                Sort.by(Sort.Order.asc("name"))
        );
~~~

This method sorts the results but does not limit the row count on its own. If the table has 500,000 products, `findAll(sort)` can still emit all 500,000 products in the requested order.

Some repository query methods may also support dynamic sorting via a `Sort` parameter, depending on the query type and Spring Data version. `OrderBy` can be used in the method name if the order is fixed:

~~~java
Flux<Product> findByStatusOrderByCreatedAtDesc(String status);
~~~

Distinguish sorting from pagination: `Sort` is not `Pageable` and does not cap result counts.

## 4. Limitations of Pageable in Reactive Repositories

`ReactiveCrudRepository` does not provide a standard CRUD `findAll(Pageable)` method like some synchronous repositories extending `PagingAndSortingRepository`. `ReactiveSortingRepository` provides `findAll(Sort)`, but that method only sorts.

A `Page<T>` typically holds a content list along with total element count and total page count. To build that metadata, the system generally has to execute an additional count query. With reactive repositories, do not assume every query method can return `Page<T>` or that simply adding a `Pageable` parameter causes Spring Data to automatically run both data and count queries.

Whether `Pageable` can be accepted as a query method parameter and which return types are supported can depend on the Spring Data version, repository type, and query declaration style. Check the API/documentation for your exact version before relying on it. An explicit and controllable approach in Spring Data R2DBC is:

1. Accept `Pageable` in the service or controller.
2. Convert `pageSize`, `offset`, and `sort` into a `Query` or SQL.
3. Return the page content as `Flux<T>` or collect a bounded page.
4. If total element count is needed, run a separate `count` query returning `Mono<Long>`.

Do not mistake `Pageable` for an automatic pagination engine across every API. It is a request descriptor; the data access API must explicitly apply that limit and order.

## 5. Using R2dbcEntityTemplate with Query, Sort, limit, and offset

`R2dbcEntityTemplate` lets you express criteria, sorting, and pagination using `Query`:

~~~java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        ))
        .limit(20)
        .offset(40);

Flux<Product> products = template.select(Product.class)
        .matching(query)
        .all();
~~~

In this example:

- `Criteria` selects only products with status ACTIVE.
- `sort(...)` sorts by creation date descending, then by ID ascending.
- `limit(20)` requests at most 20 rows.
- `offset(40)` skips the first 40 rows.
- `all()` emits matching entities as `Flux<Product>`.

This directly applies pagination details to the R2DBC query. The database only needs to return the page slice of results rather than the whole table.

## 6. Converting Pageable into a Query

You can accept `Pageable` from the calling layer and translate its fields into a `Query`:

~~~java
public Flux<Product> findActiveProducts(Pageable pageable) {
    Criteria criteria = Criteria.where("status").is("ACTIVE");

    Query query = Query.query(criteria)
            .sort(pageable.getSort())
            .limit(pageable.getPageSize())
            .offset(pageable.getOffset());

    return template.select(Product.class)
            .matching(query)
            .all();
}
~~~

This service keeps status filtering logic and applies the page requested by the caller. `Pageable.getOffset()` returns the starting position of the page; `getPageSize()` is the row limit; `getSort()` is the ordering.

If the application wants to let clients omit sort, a default order can be applied:

~~~java
Sort effectiveSort = pageable.getSort().isSorted()
        ? pageable.getSort()
        : Sort.by(Sort.Order.desc("createdAt"));
~~~

A unique property should be appended as a secondary criterion so ordering does not vary arbitrarily when multiple rows share the same sort value, e.g., `createdAt DESC, id ASC`.

## 7. Validating Page Bounds at the API Layer

Never trust client-supplied page sizes directly. A single request could ask for millions of rows and put pressure on the database or memory.

Example of capping page size:

~~~java
private Pageable normalize(Pageable requested) {
    int maxPageSize = 100;
    int pageSize = Math.min(requested.getPageSize(), maxPageSize);

    Sort sort = requested.getSort().isSorted()
            ? requested.getSort()
            : Sort.by(Sort.Order.desc("createdAt"));

    return PageRequest.of(
            requested.getPageNumber(),
            pageSize,
            sort
    );
}
~~~

In practice, verify that page number is non-negative, page size is positive, and offset does not exceed an appropriate system limit. `PageRequest.of(...)` also validates certain invalid values and can throw `IllegalArgumentException`.

The limit of 100 is just an example. The maximum should be based on payload size, entity width, latency, and database capacity.

## 8. Dynamic Sorting and Query Safety

`Sort` is typically built from entity properties. If a client sends `sort=name,asc`, the application can convert it into a `Sort`. However, clients should not be allowed to pass arbitrary column names or SQL expressions.

Whitelist the fields permitted for sorting:

~~~java
private static final Set<String> ALLOWED_SORTS =
        Set.of("name", "price", "createdAt");

private Sort safeSort(String property, Sort.Direction direction) {
    if (!ALLOWED_SORTS.contains(property)) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    return Sort.by(new Sort.Order(direction, property));
}
~~~

Data values in query conditions must be bound. Sort property names are part of the query structure and must be controlled via a whitelist. Never concatenate client sort strings directly into SQL.

When using `DatabaseClient` with hand-written SQL, bound parameters generally cannot substitute column names or `ASC`/`DESC` keywords. Map validated sort choices to one of the fixed SQL expressions.

## 9. Building a Page Response with Content and Total Elements

If an API requires the total count of records matching the filter, two queries must be run:

1. A query fetching the page content.
2. A query counting total rows matching the condition, without limit or offset.

A custom response can be defined:

~~~java
public record PageResult<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        long totalPages
) {}
~~~

Service example:

~~~java
public Mono<PageResult<Product>> findProductPage(
        Pageable pageable) {

    Criteria criteria = Criteria.where("status").is("ACTIVE");
    Query pageQuery = Query.query(criteria)
            .sort(pageable.getSort())
            .limit(pageable.getPageSize())
            .offset(pageable.getOffset());
    Query countQuery = Query.query(criteria);

    Mono<List<Product>> content = template
            .select(Product.class)
            .matching(pageQuery)
            .all()
            .collectList();

    return content.flatMap(items ->
            template.count(countQuery, Product.class)
                    .map(total -> new PageResult<>(
                            items,
                            pageable.getPageNumber(),
                            pageable.getPageSize(),
                            total,
                            total == 0 ? 0 :
                                    (total + pageable.getPageSize() - 1)
                                            / pageable.getPageSize()
                    ))
    );
}
~~~

Here, page content is collected into a `List` bounded by page size. The count query uses the same filter criteria but carries no sort, limit, or offset. Computing `totalPages` uses ceiling integer division.

Never call `collectList()` on an unbounded query. In the example, it collects at most one page bounded by the `Query`.

The data and count queries can observe different states if data changes between the two executions. If the business requires a consistent snapshot, consider a transaction with a database-appropriate isolation level. A transaction does not automatically guarantee the same snapshot under every isolation level.

## 10. How Do Page, Slice, and Flux Differ?

| Type | Content | Total Element Count? | Usage |
| --- | --- | --- | --- |
| `Flux<T>` | Emits elements as a stream | No | Queries returning multiple results, potentially unbounded if the query is unbounded |
| `Mono<List<T>>` | A complete list | Does not include total automatically | Collects an already-bounded set |
| `Page<T>` | Page content and total metadata | Yes | Usually requires an additional count query |
| `Slice<T>` | Page content and whether a next page exists | No full total needed | Can check one extra element to determine `hasNext` |
| `Pageable` | Page request descriptor | No | Used as input to construct queries |

With reactive R2DBC, a common return pattern is `Flux<T>` for data and a separate `Mono<Long>` for count when needed. Both results can be combined into a page DTO at the service layer.

If total element count is not needed, the count query can be avoided by fetching one more row than the page size:

~~~java
public record PageSlice<T>(
        List<T> content,
        int page,
        int size,
        boolean hasNext
) {}
~~~

~~~java
public Mono<PageSlice<Product>> findProductSlice(Pageable pageable) {
    int size = pageable.getPageSize();

    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    )
            .sort(pageable.getSort())
            .limit(size + 1L)
            .offset(pageable.getOffset());

    return template.select(Product.class)
            .matching(query)
            .all()
            .collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > size;
                List<Product> content = hasNext
                        ? rows.subList(0, size)
                        : rows;

                return new PageSlice<>(
                        content,
                        pageable.getPageNumber(),
                        size,
                        hasNext
                );
            });
}
~~~

The query fetches at most `size + 1` rows. If there is an extra row, the current page has a next page. This avoids counting the entire table while providing only `hasNext`, not total page count.

## 11. Pagination with DatabaseClient

When specific SQL is needed, limit and offset can be applied directly in the statement:

~~~java
public Flux<ProductSummary> findPage(
        int page,
        int size,
        String status) {

    long offset = (long) page * size;

    return databaseClient.sql("""
            SELECT id, name, price
            FROM product
            WHERE status = :status
            ORDER BY created_at DESC, id ASC
            LIMIT :limit OFFSET :offset
            """)
            .bind("status", status)
            .bind("limit", size)
            .bind("offset", offset)
            .map((row, metadata) -> new ProductSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("price", BigDecimal.class)
            ))
            .all();
}
~~~

The example uses LIMIT/OFFSET syntax common in PostgreSQL and several other databases. Pagination syntax can vary across RDBMS engines; with hand-written SQL, the application is responsible for using the right dialect. If you want Spring Data to handle mapping and dialect, consider `R2dbcEntityTemplate`.

## 12. Limitations of Each API

Not every API provides all of sort, page, and count:

| API | Sort | Limit/offset | Count metadata |
| --- | --- | --- | --- |
| `ReactiveCrudRepository.findAll()` | No sort parameter | No standard page parameter | No |
| `ReactiveSortingRepository.findAll(Sort)` | Yes | Does not provide page size/offset automatically | No |
| Derived query with `Top/First` | Can combine fixed order in method name or Sort depending on support | Fixed limit per method name | No |
| `R2dbcEntityTemplate` + `Query` | Has `Sort` | Has `limit` and `offset` | Can call count separately |
| `DatabaseClient` | Written in SQL | Written in SQL per dialect | Requires separate count query |
| R2DBC SPI | Controlled at statement/query level | Implement SQL/driver-specific logic yourself | Handle results yourself |

### ReactiveCrudRepository

`findAll()` retrieves all results; it does not accept `Pageable` or `Sort` as a standard method parameter.

### ReactiveSortingRepository

`findAll(Sort)` sorts the results but does not limit the count. It is not equivalent to `findAll(Pageable)`.

### Top and First Derived Queries

If the limit is fixed, the method name can express the intent:

~~~java
Flux<Product> findTop10ByStatusOrderByCreatedAtDesc(String status);

Mono<Product> findFirstByStatusOrderByPriceAsc(String status);
~~~

This is a fixed limit in the query definition, not dynamic pagination driven by the user's page number.

### R2dbcEntityTemplate

The template provides the ability to combine criteria, `Sort`, `limit`, and `offset` in a `Query`. This is a convenient option when dynamic, parameterized pagination is needed.

### DatabaseClient

`DatabaseClient` offers full SQL control. In exchange, the application must manage dialect, column names, parameter binding, projections, and count queries itself.

## 13. Offset Pagination and Cost at Deep Pages

Offset pagination is straightforward to understand:

~~~sql
SELECT id, name
FROM product
ORDER BY id
LIMIT 20 OFFSET 10000;
~~~

The database must locate and skip 10,000 rows before returning the next 20 rows. With very large offsets, cost can grow significantly depending on the execution plan and indexes. Some databases still have to traverse many skipped rows.

Offset pagination can also cause duplicate or skipped data when the table changes between requests:

1. A user fetches page 0.
2. A new row is inserted at the start of the order.
3. The user fetches page 1 with the old offset.
4. A row may reappear or be skipped because row positions shifted.

If data changes infrequently and page depth is modest, offset remains simple and suitable. For large tables or continuously changing data streams, consider keyset pagination.

## 14. Keyset Pagination (Seek Pagination)

Keyset pagination uses values from the last row of the previous page as a cursor for the next page. Instead of skipping N rows, the query asks for rows coming after the cursor in the chosen order.

For example, sorting by `created_at DESC, id ASC`. The cursor from the end of the previous page consists of `lastCreatedAt` and `lastId`. Next-page condition:

~~~sql
SELECT id, name, created_at
FROM product
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id > :lastId)
  )
ORDER BY created_at DESC, id ASC
LIMIT :limit;
~~~

ID serves as the unique secondary criterion to ensure deterministic order when multiple rows share the same `created_at`. Ensure the cursor condition reflects each property's sort direction.

Keyset is typically suited for "Load more" buttons or sequentially browsing large datasets. It is not convenient for jumping straight to page 500 because there is no offset. APIs usually return a next cursor instead of a page number.

A cursor should contain enough sort values from the last row and can be encoded/verified so clients cannot tamper with conditions. When a cursor is returned by a client, validate and bind it like any other parameter.

## 15. Indexes and Sort Order

Sorting and filtering can force the database to sort many rows if no suitable index exists. For example:

~~~sql
SELECT id, name, created_at
FROM product
WHERE status = 'ACTIVE'
ORDER BY created_at DESC, id ASC
LIMIT 20;
~~~

A composite index can be considered:

~~~sql
CREATE INDEX idx_product_status_created_id
    ON product(status, created_at DESC, id ASC);
~~~

An appropriate index can support both filtering and ordering, though actual design depends on the database, cardinality, selectivity, and other queries. Every index adds write overhead and storage footprint. Use EXPLAIN/EXPLAIN ANALYZE on the target database to confirm.

When sorting by multiple columns, column order in the index matters. An index starting with `created_at` may not be optimal for a query filtering on `status` and then sorting by `created_at`.

## 16. Stable Ordering and Null Values

Do not paginate by a column that can have duplicates without adding a unique secondary key. For example:

~~~sql
ORDER BY created_at DESC
~~~

If multiple rows have the same `created_at`, the database may return them in different orders across executions. You should use:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

When sorting on a nullable column, the position of NULLs can differ by database or syntax. If NULL order matters, specify an explicit rule per dialect, such as `NULLS FIRST`/`LAST` if supported by the database. When using `Query`/`Sort`, check the generated SQL and actual driver/database behavior.

## 17. Pagination in WebFlux Controllers

A controller can accept `page` and `size` from query parameters, construct a `Pageable`, and call the service:

~~~java
@GetMapping("/products")
public Flux<Product> findProducts(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    Pageable pageable = PageRequest.of(
            page,
            Math.min(size, 100),
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.asc("id")
            )
    );

    return productService.findProducts(pageable);
}
~~~

This example returns `Flux` directly, so the response contains the page elements without total page count. If metadata is needed, the service can return `Mono<PageResult<Product>>` or `Mono<PageSlice<Product>>` as shown in earlier examples.

In real applications, validate `page` and `size` before calling `PageRequest.of`, handle negative/invalid parameters, and whitelist sort fields if clients are allowed to choose sorting.

## 18. Do Not Use Flux.take() as a Substitute for SQL Limits

One could write:

~~~java
return productRepository.findAll()
        .take(20);
~~~

Subscribers only receive at most 20 items, but `take(20)` is an application-layer Reactor operator. It is not a clear way to instruct the database to execute `LIMIT 20`. Depending on the driver and cancellation timing, the database/driver may have already read or buffered extra data before cancellation is processed.

When the goal is to limit the rows queried, place the limit in `Query` or SQL:

~~~java
Query query = Query.empty()
        .sort(Sort.by("id"))
        .limit(20);

return template.select(Product.class)
        .matching(query)
        .all();
~~~

`take` remains useful for bounding a stream at the application layer, but it does not replace a database-side limit for query optimization.

## 19. Testing Sort and Pagination

Integration tests should verify:

1. Results have at most `page size` elements.
2. Offset selects the right slice of data.
3. Ascending/descending directions are applied properly.
4. Unique secondary ordering keeps rows with duplicate sort values stable.
5. Filters remain identical between content and count queries.
6. The last page has fewer elements than page size, or is empty when out of range.
7. Page size is capped at the API layer.
8. Keyset cursors do not duplicate or skip rows on a stable dataset.
9. Data changing between requests behaves in accordance with consistency requirements.

Test example:

~~~java
StepVerifier.create(productService.findProducts(
                PageRequest.of(0, 2,
                        Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id")))
        ))
        .expectNextMatches(product -> product.name().equals("Alpha"))
        .expectNextMatches(product -> product.name().equals("Beta"))
        .verifyComplete();
~~~

Tests should set up data with deterministic ordering, including duplicate sort values. Run against the target database to confirm dialect, null ordering, indexes, and mapping.

## 20. Common Misconceptions

1. **Assuming `Pageable` automatically paginates every reactive repository.** Verify API support and ensure limit/offset are actually applied.
2. **Assuming `Sort` limits row counts.** `Sort` only orders; it has no page size.
3. **Assuming `findAll(Sort)` returns only one page.** The method can emit the entire sorted result set.
4. **Assuming `Page` and `Flux` are equivalent.** `Page` requires total metadata; `Flux` simply streams data.
5. **Calling `collectList()` on an unbounded query.** This can load the entire table into memory.
6. **Using `take()` instead of `LIMIT`.** `take` limits consumption in Reactor and does not replace database query limits.
7. **Sorting by a non-unique column.** Pages can duplicate or miss rows due to unstable ordering.
8. **Letting clients pass arbitrary column names.** Whitelist sort fields to prevent unsafe SQL structure.
9. **Very large offsets.** The cost of skipping rows can grow; consider keyset pagination.
10. **Counting totals on every request.** Count queries can be expensive; run them only when the UI truly needs total pages.
11. **Content and count queries using different filters.** Page metadata will not match the content.
12. **Not capping page size.** Clients could request an excessively large result set.

## Quick Selection Rules

- Use `Sort` when you only need to order results.
- Use `ReactiveSortingRepository.findAll(Sort)` if you need to fetch all entities in order.
- Use `Top/First` for fixed limits defined directly in the query method.
- Use `R2dbcEntityTemplate` with `Query.sort(...).limit(...).offset(...)` for dynamic pagination.
- Use `Pageable` as a page request descriptor and translate its fields into a `Query` if the repository API does not support it directly.
- Use a separate `Mono<Long>` count combined with content when total element count is required.
- Use `size + 1` to determine `hasNext` when a full count is not needed.
- Use `DatabaseClient` when custom SQL/dialect and manual count query management are required.
- Use keyset pagination for large or frequently changing datasets.
- Always cap page size, whitelist sort fields, and append a unique secondary sort key.

`Pageable`, `Sort`, `limit`, and `offset` address different parts of pagination. `Sort` defines order; `limit` and `offset` restrict the slice of data returned by the database; `Pageable` bundles page information to pass down from the application layer. With Spring Data R2DBC, pay attention to each repository API's limitations and do not assume `findAll(Pageable)` or `Page<T>` is available for every reactive query. Using `R2dbcEntityTemplate` `Query` or SQL via `DatabaseClient` gives explicit control over limits, counts, and ordering while keeping data reactive.
