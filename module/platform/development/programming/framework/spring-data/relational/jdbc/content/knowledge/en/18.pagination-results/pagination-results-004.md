# Slice and How to Determine Whether a Next Page Exists

In **Spring Data Relational JDBC (Spring Data JDBC)**, a paginated query can return `Slice<T>` when the UI only needs to display a chunk of data and know **whether more results exist beyond it**. `Slice` provides the content of a data slice, current page information, and the `hasNext()` status without needing to know the total record count of the entire query.

This is a suitable choice for a **Load more** button, infinite scroll, or lists with Previous/Next buttons that do not need to show “Page 2 of 37”. When you only need to determine whether a next page exists, `Slice` avoids counting the total number of rows as `Page` does.

## 1. What Is Slice?

`Slice<T>` belongs to Spring Data Commons and represents a bounded slice of results. A Slice typically includes:

- The list of elements in the current slice.
- The current page number and page size.
- The `hasNext()` and `hasPrevious()` states.
- Navigation helpers such as `nextPageable()` and `previousPageable()`.

For example, an application displays open orders, fetching 20 orders at a time. The UI does not need to know the total number of orders in the system; it only needs to know whether any orders remain after these 20 in order to show a “Load more” button.

~~~mermaid
flowchart TB
    Request["Request: page=0, size=20"]
    Repo["OrderRepository"]
    DB[("Database")]
    Fetch["Fetch at most 21 rows"]
    Slice["Slice<Order><br/>content at most 20"]
    More{"Is there a 21st row?"}
    Next["hasNext() = true<br/>show Load more"]
    End["hasNext() = false<br/>reached the end"]

    Request --> Repo --> DB --> Fetch --> Slice --> More
    More -->|Yes| Next
    More -->|No| End
~~~

The key point to remember is that `Slice` answers **“are there more results next?”**, not **“how many total results exist?”**.

## 2. Declaring a Repository Method Returning Slice

Suppose the `Order` entity has properties `id`, `status`, and `createdAt`. The repository can declare:

~~~java
package com.example.sales.order;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository extends CrudRepository<Order, Long> {

    Slice<Order> findByStatus(String status, Pageable pageable);
}
~~~

Two key parts:

- `Slice<Order>` indicates that results are returned in slices with navigation metadata.
- `Pageable` carries the page number, page size, and sort information.

`Pageable` is a special parameter recognized by Spring Data; it does not become an ordinary entity filter condition. The method name `findByStatus` still describes the condition on the `status` property.

Sorting can be declared right in the method name to ensure a default order:

~~~java
Slice<Order> findByStatusOrderByCreatedAtDescIdDesc(
    String status,
    Pageable pageable
);
~~~

Or pass `Sort` through `Pageable` to choose the order at the call site. Property names in query methods and `Sort` are **Java properties** of the entity, such as `createdAt`; the framework maps properties to the corresponding SQL columns per the mapping.

## 3. Pageable and PageRequest

`Pageable` describes a pagination request. The common way to construct one is `PageRequest.of(pageNumber, pageSize)`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable firstPage = PageRequest.of(0, 20);
Pageable secondPage = PageRequest.of(1, 20);
~~~

Page numbers start at **0**:

| pageNumber | pageSize | Offset | First row position |
|---:|---:|---:|---:|
| 0 | 20 | 0 | 1 |
| 1 | 20 | 20 | 21 |
| 2 | 20 | 40 | 41 |

Offset is calculated as:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

`PageRequest` also accepts sorting information:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

This example sorts newest orders first; if two orders share the same creation timestamp, descending ID determines the order between them.

## 4. How Does Spring Data Determine hasNext()?

To determine whether a next page exists without counting all results, the `Slice` mechanism typically fetches **one more row than the requested page size**:

\[
\text{maxResults} = \text{pageSize} + 1
\]

With a page size of 20:

- The database is asked for at most 21 matching rows.
- If 21 rows are returned, the framework knows for certain that at least one row follows the first 20.
- The framework keeps the first 20 rows in content and uses the 21st row to set `hasNext = true`.
- If 0 to 20 rows are returned, there is no extra row proving a subsequent page exists, so `hasNext = false`.

Example:

| Rows returned by query | Rows in Slice | `hasNext()` | Meaning |
|---:|---:|---|---|
| 21 | 20 | `true` | At least one more row exists |
| 20 | 20 | `false` | Reached the last page |
| 7 | 7 | `false` | Last page only has 7 rows remaining |
| 0 | 0 | `false` | No results for this page |

Suppose exactly 40 orders match the condition, with page size 20:

1. Page 0 fetches up to 21 rows, receives 21; content keeps 20 and `hasNext = true`.
2. Page 1 fetches up to 21 rows starting at offset 20, receives only 20; content keeps 20 and `hasNext = false`.

There is no need to run an extra `SELECT COUNT(*)` to compute the total order count. This is the critical difference between `Slice` and `Page`.

### Illustrative SQL

On PostgreSQL or MySQL, the first-page query might correspond to:

~~~sql
SELECT id, customer_id, status, created_at
FROM sales_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 21 OFFSET 0;
~~~

Next page:

~~~sql
SELECT id, customer_id, status, created_at
FROM sales_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 21 OFFSET 20;
~~~

This SQL **illustrates the semantics** of Slice pagination. Spring Data JDBC and its dialect are responsible for generating query limits for repository methods; you do not manually add `LIMIT pageSize + 1` to a derived query.

## 5. Reading a Slice and Determining the Next Page

Example service fetching the first page:

~~~java
package com.example.sales.order;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    public Slice<Order> findOpenOrders(int page, int size) {
        Pageable pageable = PageRequest.of(page, size);
        return orders.findByStatusOrderByCreatedAtDescIdDesc(
            "OPEN",
            pageable
        );
    }
}
~~~

The controller or caller can read the result:

~~~java
Slice<Order> slice = orderQueryService.findOpenOrders(0, 20);

slice.getContent().forEach(order ->
    System.out.println(order.getId())
);

if (slice.hasNext()) {
    System.out.println("Can load the next page");
}
~~~

Commonly used methods:

| Method | Meaning |
|---|---|
| `getContent()` | List of elements in the Slice |
| `getNumber()` | Current page number, starting at 0 |
| `getSize()` | Requested page size |
| `getNumberOfElements()` | Actual number of elements in content |
| `hasNext()` | Whether there is a next page |
| `hasPrevious()` | Whether there is a previous page |
| `nextPageable()` | Pageable for the next page |
| `previousPageable()` | Pageable for the previous page |
| `isFirst()` | Whether it is the first page |
| `isLast()` | Whether it is the last page |

Only call `nextPageable()` when `hasNext()` is true:

~~~java
if (slice.hasNext()) {
    Pageable nextPageable = slice.nextPageable();
    Slice<Order> nextSlice =
        orderRepository.findByStatusOrderByCreatedAtDescIdDesc(
            "OPEN",
            nextPageable
        );
}
~~~

`nextPageable()` only describes the request for the next page; it **does not execute a query itself**. The application must pass that `Pageable` into the next repository call.

## 6. How Does Slice Differ from Page and List?

The three return types have different contracts:

| Criterion | `List<T>` | `Slice<T>` | `Page<T>` |
|---|---|---|---|
| Result content | Yes | Yes | Yes |
| Current page number | No | Yes | Yes |
| Knows if next page exists | Not automatically | Yes | Yes |
| Knows total element count | No | No | Yes |
| Knows total page count | No | No | Yes |
| Usually needs count query | No | No | May be needed |
| Suitable for | Small/unpaginated lists | Load more, infinite scroll | UIs needing total page count |

### Page Has Total Counts

Example:

~~~java
Page<Order> findByStatus(String status, Pageable pageable);
~~~

`Page<Order>` adds:

- `getTotalElements()`: total number of rows matching the condition.
- `getTotalPages()`: total number of pages.

To know the exact total, the framework typically needs a separate count query or an equivalent counting mechanism. With large tables and complex conditions, the count query can take significant time.

### Slice Only Needs to Know Whether More Data Remains

~~~java
Slice<Order> findByStatus(String status, Pageable pageable);
~~~

No total count is required; the framework only needs to know whether an extra row exists beyond the page size. This is usually a better fit for scrolling experiences or a “Load more” button.

### List with Pageable

A method returning `List<T>` can use `Pageable` to limit and fetch a subset of results, but the list itself carries no `hasNext` information. The caller cannot tell for sure whether a next page exists just from receiving `pageSize` rows.

If only content and a next-page flag are needed, `Slice` expresses the intent more clearly.

## 7. Building a “Load More” Endpoint

An example API response can return the content and a boolean flag:

~~~java
public record OrderSliceResponse(
    List<OrderSummary> content,
    int page,
    int size,
    boolean hasNext
) {}

public record OrderSummary(
    Long id,
    String status
) {}
~~~

The service converts the `Slice` into the response:

~~~java
public OrderSliceResponse getOpenOrderSlice(int page, int size) {
    Slice<Order> slice =
        orderRepository.findByStatusOrderByCreatedAtDescIdDesc(
            "OPEN",
            PageRequest.of(page, size)
        );

    List<OrderSummary> content = slice.getContent().stream()
        .map(order -> new OrderSummary(
            order.getId(),
            order.getStatus()
        ))
        .toList();

    return new OrderSliceResponse(
        content,
        slice.getNumber(),
        slice.getSize(),
        slice.hasNext()
    );
}
~~~

Client sends:

~~~http
GET /api/orders/open?page=0&size=20
~~~

Example response:

~~~json
{
  "content": [
    { "id": 501, "status": "OPEN" },
    { "id": 498, "status": "OPEN" }
  ],
  "page": 0,
  "size": 20,
  "hasNext": true
}
~~~

The response illustrates only the first two elements for readability; in practice, content contains up to 20 elements per the requested size. The client tracks the current page; when the user clicks “Load more”, it increments page by 1 and calls the endpoint again. When `hasNext` is false, it hides the button or stops loading.

You do not have to serialize the entire `Slice` object directly to JSON. A DTO lets you control the API contract and avoid exposing Spring Data internals.

## 8. Stable Sorting Is Crucial

Pagination is meaningful only when results are consistently ordered. Without `ORDER BY`, the database does not guarantee row order. Two calls for page 0 and page 1 could receive rows in different orders.

Recommended example:

~~~java
Pageable pageable = PageRequest.of(
    page,
    size,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

`createdAt` can collide across multiple `Order` records. Adding `id` as a unique secondary key establishes a more deterministic order.

Rules:

- Always have an explicit order for paginated queries.
- Add a unique key as the final tie-breaker.
- Use Java property names in `Sort`, not SQL column names if the naming strategy differs.
- Do not change the sort order across requests within the same pagination sequence.

## 9. Offset Pagination and Data Changes Between Loads

Standard `PageRequest` uses **offset pagination**. For instance, page 2 with size 20 corresponds to offset 40. This is easy to understand and fits many admin screens, yet it has two limitations.

### Large Offsets Can Be Costly

When a user requests a very deep page, the database may have to scan through many skipped rows before returning results. Proper indexes help, but do not make all deep offset queries free.

### New Data Can Shift Positions

Suppose page 0 returned the 20 newest orders. Before the client loads page 1, a new order is inserted at the top of the list. At offset 20, the next page may repeat the last row of the previous page or cause a row to be skipped, depending on the order and query timing.

Each Slice request is typically a separate query; it does not maintain a snapshot across the entire scroll session. If the application needs to traverse a stable dataset while mutations occur, consider an appropriate transaction/snapshot or a cursor/keyset design.

## 10. Keyset Pagination When Offset Is No Longer Suitable

For large or rapidly changing lists, **keyset pagination** can be used: instead of saying “skip 40 rows”, the next request sends the key values of the last received row.

Suppose the order is `created_at DESC, id DESC`. If the last row of the current page has `created_at = :lastCreatedAt` and `id = :lastId`, the next page filters:

~~~sql
SELECT id, customer_id, status, created_at
FROM sales_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

The comparison predicate must match the exact sort order and null handling of the sort columns. With multi-column sorts, the cursor expression must carry enough values to identify a unique position.

Keyset can reduce the cost of skipping rows on deep pages and reduce shifting caused by inserts at the front of the list. However:

- It requires a cursor holding the last page's key values.
- Data modifications or deletions can still affect results.
- It does not support jumping directly to page 50 the way offset pagination does.
- Implementation may require custom queries/repositories depending on the Spring Data JDBC API and version.

**Slice does not mean keyset pagination.** A `Slice` using `Pageable`/`PageRequest` still normally uses offset; keyset requires explicitly designing cursors and query predicates.

## 11. Capping Page Size

Do not let clients request an arbitrary page size, such as hundreds of thousands of records. That can overload the database, network, and application heap.

Example limit in the service:

~~~java
private static final int DEFAULT_SIZE = 20;
private static final int MAX_SIZE = 100;

public Slice<Order> findOpenOrders(int page, int requestedSize) {
    if (page < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }

    int size = requestedSize <= 0
        ? DEFAULT_SIZE
        : Math.min(requestedSize, MAX_SIZE);

    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    );

    return orderRepository.findByStatus("OPEN", pageable);
}
~~~

In practice, decide explicitly whether an invalid size falls back to a default or returns HTTP 400. Never allow a client to request an enormous page and accidentally trigger a heavy query.

## 12. Slice with `@Query` or Custom SQL

When using custom SQL, a method can still accept `Pageable` and return `Slice` if the query method and Spring Data JDBC version support that return type. Example:

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM sales_orders
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    """)
Slice<Order> findOpenOrders(
    @Param("status") String status,
    Pageable pageable
);
~~~

The `@Query` example illustrates explicitly declared SQL; do not add a fixed `LIMIT` inside the SQL while also delegating `Pageable` handling to the framework, as they can conflict. Check `Pageable`/`Slice` support in your exact Spring Data JDBC version and inspect the actual SQL in logs when needed.

If the query contains joins or returns a projection, ensure result mapping is compatible with the return type. Paginating joined results can cause root duplication when an `Order` joins to multiple child rows; in that case, design the query so pages are determined over unique roots, such as selecting root IDs first and then fetching the needed display data.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `Page` when only checking if more data exists | May incur unnecessary count queries | Use `Slice` if total count is not needed |
| Using `List` and checking `size()` | No certainty about whether a next page exists | Use `Slice` or design a `pageSize + 1` query yourself |
| Thinking `hasNext()` is the total page count | Misunderstanding the `Slice` contract | `hasNext` is only a boolean |
| Forgetting `ORDER BY` order | Rows may repeat or be skipped | Sort stably and add a unique tie-breaker |
| Using 1-based page numbers | Off-by-one page retrieval | `PageRequest` starts at 0 |
| Calling `nextPageable()` when there is no next page | Invalid or meaningless navigation | Check `hasNext()` first |
| Thinking `nextPageable()` loads data automatically | No new query is executed | Call the repository with the new `Pageable` |
| Overly large page size | Exhausts memory and database resources | Cap size at the API/service layer |
| Using deep offsets on large tables | Slow queries | Consider keyset/cursor pagination |
| Using `Slice` assuming a cross-request snapshot | Data mutations can shift pages | Choose snapshot or cursor based on consistency requirements |
| Manually adding `LIMIT` alongside `Pageable` | Overlapping limits or invalid SQL | Let the framework apply `Pageable` or manage all custom SQL manually |

## 14. Practice Exercises

1. Create a repository method `Slice<Order> findByStatus(String status, Pageable pageable)`.
2. Call it with `PageRequest.of(0, 5)` and inspect `getContent().size()` and `hasNext()`.
3. Prepare 12 OPEN orders. Fetch page 0 size 5, page 1 size 5, and page 2 size 5. Predict the row count and `hasNext` for each page.
4. Change the method to return `Page<Order>`. Observe `getTotalElements()`, `getTotalPages()`, and the difference in counting needs.
5. Try returning `List<Order>` with `Pageable`. Why doesn't `List` provide `hasNext`?
6. Remove `ORDER BY` and invoke repeatedly. Explain why you should not rely on arbitrary database ordering.
7. Use sort `createdAt DESC, id DESC`. Verify that rows with the same `createdAt` maintain a deterministic order.
8. While the client is loading page 1, insert a new order at the top of the list. Observe the effect of offset pagination.
9. Write a keyset query by `created_at` and `id` using the last row of the previous page as the cursor.
10. Add a maximum page size cap of 100 in the service and test sending a larger size request.

Example results with 12 orders and page size 5:

| Page | Rows received from query (max 6) | Returned content | `hasNext` |
|---:|---:|---:|---|
| 0 | 6 | 5 | `true` |
| 1 | 6 | 5 | `true` |
| 2 | 2 | 2 | `false` |

## 15. Key Takeaways

`Slice<T>` is suitable when the application needs to fetch a subset of data and know whether a next page exists without needing the total element count. Spring Data determines `hasNext` by fetching one extra row beyond the page size: if the extra row is present, it retains `pageSize` items in content and marks that more pages exist; if not, this is the final slice.

`Page` provides totals and typically requires a count query; `List` provides only the elements. With `Slice`, use `Pageable`/`PageRequest`, sort stably with a unique key as a tie-breaker, and check `hasNext()` before calling `nextPageable()`. If data is very large or frequently mutated, evaluate the limits of offset pagination and consider appropriate keyset/cursor pagination.
