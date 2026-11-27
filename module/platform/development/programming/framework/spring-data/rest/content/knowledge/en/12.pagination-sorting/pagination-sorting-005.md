# Page and Slice: Total Element Count, Count Cost, and Navigation Links

## Objectives

After this lesson, you will be able to:

- Configure pagination and sorting for a Spring Data REST collection resource.
- Distinguish between the data and metadata provided by Page and Slice.
- Explain why Page may trigger a COUNT query and when Slice is a better fit.
- Read page metadata along with prev/next links in HAL.
- Design a stable sort order and avoid overly expensive pagination queries.

## 1. Pagination in Spring Data REST

When a repository is exported and supports pagination, Spring Data REST does not need to return all records in a single request. Clients can request a subset of data using query parameters:

| Parameter | Meaning | Common Default |
|---|---|---|
| page | Page index, starting from 0 | 0 |
| size | Maximum number of elements per page | 20 |
| sort | Property and sort direction | Per configuration/query |

Example:

~~~http
GET /orders?page=0&size=20
Accept: application/hal+json
~~~

The request above retrieves the first page, up to 20 orders. The next page has index **page=1**; page indices start from 0, so **page=1** is the second page.

You can combine pagination with multiple sort conditions:

~~~http
GET /orders?page=1&size=10&sort=createdAt,desc&sort=id,desc
Accept: application/hal+json
~~~

Each **sort** parameter describes one criterion. In this example, results are sorted by **createdAt** descending; if multiple records have the same creation timestamp, **id** descending decides the order between them.

Default values can be changed via Spring Data REST configuration. Applications should also limit the maximum page size so a single client cannot request an excessively large amount of data in one request.

## 2. Pageable, Page, and Slice at the Repository Layer

**Pageable** describes the query request: the page to fetch, the page size, and the sort order. **Page** and **Slice** describe the query result at two different metadata levels.

Repository example:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @RestResource(path = "byStatus", rel = "byStatus")
    Page<PurchaseOrder> findByStatus(
            @Param("status") OrderStatus status,
            Pageable pageable
    );

    @RestResource(path = "byCustomer", rel = "byCustomer")
    Slice<PurchaseOrder> findByCustomerId(
            @Param("customerId") Long customerId,
            Pageable pageable
    );
}
~~~

Spring Data REST recognizes search methods with a **Pageable** parameter and a **Page** or **Slice** return type, and exports paginated search resources for them.

Examples calling the two search resources:

~~~http
GET /orders/search/byStatus?status=PAID&page=0&size=20
GET /orders/search/byCustomer?customerId=7&page=0&size=20
~~~

Path and relation names can be customized with **@RestResource**. Clients should discover search links from the resource or API profile published by the server rather than guessing endpoints.

## 3. Page: Has Total Elements and Total Pages

**Page<T>** provides the content of the current page along with information about the entire result set:

- **getContent()**: the elements on the current page.
- **getNumber()**: the current page index, starting from 0.
- **getSize()**: the requested page size.
- **getNumberOfElements()**: the actual number of elements on the current page.
- **getTotalElements()**: the total number of elements matching the query condition.
- **getTotalPages()**: the total number of pages based on total elements and page size.
- **hasNext() / hasPrevious()**: whether there is a next or previous page.

Example of a query with 50 matching orders and a page size of 5:

~~~json
{
  "content": [
    { "id": 101, "status": "PAID" },
    { "id": 102, "status": "PAID" }
  ],
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
~~~

The **content** section above only illustrates part of the data. If the first page has enough data, the actual element count usually equals **size**; **totalElements=50** and **totalPages=10** describe the entire query result.

**Page** is appropriate when the UI genuinely needs to display total results, total pages, the last page number, or a navigation bar that lets users jump to a specific page.

## 4. Why Can Page Incur a COUNT Cost?

To build a **Page**, the system needs to know the total number of records matching the query condition. With Spring Data JPA, this usually requires an extra count query in addition to the data-fetching query.

Conceptually, the two queries look like:

~~~sql
-- Fetch the content of the current page
SELECT *
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;

-- Count total matching records
SELECT COUNT(*)
FROM purchase_order
WHERE status = 'PAID';
~~~

The data query can take advantage of **LIMIT/OFFSET**. The COUNT query must determine the number of matching records across the entire result set. Therefore, on large tables or with complex filter conditions, COUNT can take significant time.

Cost can increase when the query contains:

- Multi-table JOINs or one-to-many relationships that multiply rows.
- **DISTINCT**, **GROUP BY**, subqueries, or complex filter predicates.
- Filters on columns lacking suitable indexes.
- An inferred count query that is inaccurate or less efficient than the data query.

Do not conclude that every Page request always executes two SQL queries in all situations. Spring Data can optimize and infer the total count from the results in certain cases. However, when an exact total is needed, a count query may still be required.

With custom queries, you can explicitly specify a **countQuery** to control the count statement:

~~~java
@Query(
    value = """
        select o
        from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o)
        from PurchaseOrder o
        where o.status = :status
        """
)
Page<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable
);
~~~

The count query must count the exact same result set returned by the main query. If the main query uses DISTINCT or JOINs that alter cardinality, design the COUNT statement accordingly and verify the results against real data.

## 5. Slice: Only Needs to Know Whether More Data Follows

**Slice<T>** focuses on the content of the current data slice and the ability to continue fetching data. It does not provide total elements or total pages for the entire result set.

Commonly used information:

- **getContent()**: the elements in the current slice.
- **getNumber()**, **getSize()**, **getNumberOfElements()**: the position and size of the current slice.
- **hasNext()**: whether there is data in the next slice.
- **hasPrevious()**: whether there is a previous slice.

To determine whether more data exists without counting the entire result set, Spring Data typically fetches one more element than the page size. For example, with a page size of 20, the query may fetch 21 rows. If the 21st row exists, the system knows more data remains and returns only the first 20 rows to the client.

Example:

~~~java
Slice<PurchaseOrder> findByCustomerId(
        Long customerId,
        Pageable pageable
);
~~~

Slice fits infinite scrolling screens, “Load more” buttons, or sequential batch processing when knowing the total result count upfront is unnecessary.

Spring Data REST recognizes methods returning **Slice** and adds previous/next navigation links for the resource. Because Slice itself does not know the global total, clients should not assume accurate **totalElements** or **totalPages** are available for display.

## 6. Comparing Page and Slice

| Criterion | Page | Slice |
|---|---|---|
| Current page content | Yes | Yes |
| Current size and position | Yes | Yes |
| Knows if more data follows | Yes | Yes |
| Total number of elements | Yes | No |
| Total number of pages | Yes | No |
| Need for COUNT query | May be needed | Not needed to determine total |
| Typical cost | Data query plus possible COUNT | Bounded data query, usually fetching one extra row |
| Best suited for | UIs needing totals and page numbers | Infinite scroll, load more, batch processing |

Choose **Page** when business logic or UI needs exact totals. Choose **Slice** when you only need to know whether more items can be loaded. Do not use Page just because you want Next/Previous buttons; Slice already satisfies the requirement of knowing whether more data follows.

## 7. Navigation Links in HAL

Spring Data REST uses HAL to return data together with hypermedia links. A paginated collection response may look like:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders{&sort,page,size}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/orders?page=1&size=5{&sort}",
      "templated": true
    }
  },
  "_embedded": {
    "orders": [
      { "id": 101, "status": "PAID" },
      { "id": 102, "status": "PAID" }
    ]
  },
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
~~~

Key components:

- **_embedded.orders**: data for the current page; the relation name depends on the exported repository.
- **_links.self**: link for the current collection, which may be a URI template.
- **_links.next**: link to the next page if more data remains.
- **_links.prev**: link to the previous page if on a page after the first.
- **page**: Page metadata, consisting of **size**, **totalElements**, **totalPages**, and **number**.

On the first page, the response does not have a **prev** link. On the last page, the response does not have a **next** link. On middle pages, both links can appear together.

When the client needs to switch pages, read **href** from **_links.next** or **_links.prev** and call that exact URL. These links can preserve filter conditions, sort, and page size. This avoids manually assembling query strings and keeps the client less coupled to the server's internal URL structure.

Second page example:

~~~http
GET /orders?page=1&size=5
Accept: application/hal+json
~~~

The response will have a **prev** link pointing back to page 0 and a **next** link pointing to the following page if more data remains. The **page** values in the URL remain 0-indexed.

## 8. Stable Sorting to Avoid Duplicate or Skipped Records

Pagination is only reliable when the data ordering is deterministic. If you sort by a column that has many duplicate values, the order among equal records can change between requests.

Example sorting only by creation time:

~~~http
GET /orders?page=0&size=20&sort=createdAt,desc
~~~

If multiple orders share the same **createdAt**, the database does not guarantee the order among them. When the client moves to the next page, a record might appear twice or be skipped.

You should add a unique property as a secondary criterion:

~~~http
GET /orders?page=0&size=20&sort=createdAt,desc&sort=id,desc
~~~

Points to remember:

- Prefer sorting by properly indexed properties when data is large.
- Use a unique property, usually ID, as the final tie-breaker criterion.
- Spring Data REST supports multiple sort parameters; parameter order determines criterion order.
- You can sort by nested properties using a property path.
- Sorting by an association exported as a link to a top-level resource is not supported as an ordinary sort property.
- Only allow valid sort properties that the API intends to expose; do not let clients freely pick any field if doing so poses performance risks.

Stable ordering makes pagination more consistent. However, if data is inserted or deleted between two requests, the offsets of subsequent pages can still shift. For continuously changing data streams, consider a cursor/keyset strategy or a snapshot mechanism suited to the business requirements.

## 9. Limiting Page Size and Paginating Large Datasets

Pagination limits the number of rows returned per request, but it does not automatically make every query fast.

Implementation guidelines:

1. Set a moderate default page size and enforce a maximum page size limit.
2. Do not allow clients to request hundreds of thousands of records in a single page.
3. Verify indexes for commonly filtered and sorted columns.
4. Inspect the execution plan of both the data query and the COUNT query.
5. For Page queries with complex custom queries, optimize or declare a separate count query.
6. If you only need to know whether more data exists, consider Slice to avoid calculating the total.
7. With very large offsets, note that the database still has to process or skip the records preceding the offset; Slice does not eliminate this limitation.
8. When traversing extremely large datasets, consider cursor/keyset pagination or dedicated batch processing instead of continuously incrementing page numbers.

A maximum page size is a guardrail protecting server resources. It does not replace proper indexing and query design.

## 10. Hands-On with curl

Read the first page of the collection:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders?page=0&size=5&sort=createdAt,desc&sort=id,desc"
~~~

Read the second page:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders?page=1&size=5&sort=createdAt,desc&sort=id,desc"
~~~

Read paginated search results:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders/search/byStatus?status=PAID&page=0&size=10"
~~~

For URLs containing the **&** character, wrap the entire URL in quotes when running curl so the shell does not interpret the parameters as separate commands.

After each request, verify:

- Whether **page.number** matches the requested page.
- Whether **page.size** matches the page size accepted by the server.
- Whether **page.totalElements** and **page.totalPages** are reasonable if the response is a Page.
- Whether the **next** link preserves sort and filter parameters.
- Whether the **prev** link appears when on a page after the first.
- Whether the last page omits the **next** link.

## 11. Practice Exercises

Given a PurchaseOrder repository with thousands of orders:

1. Write a method to find orders by status returning **Page<PurchaseOrder>**.
2. Write a method to find orders by customer returning **Slice<PurchaseOrder>**.
3. Explain why Page may require a COUNT query, whereas Slice usually only fetches one extra row to check **hasNext**.
4. A screen only needs a “Load more” button and does not display the total result count. Would you choose Page or Slice? Explain.
5. A query filtering by status has a very slow COUNT. What factors would you inspect in the execution plan and count query?
6. Why can sorting by **createdAt** alone cause records to repeat or be skipped between two pages? Add a sort criterion to stabilize the order.
7. Describe how a client uses **_links.next.href** to load the next page without assembling URLs manually.

**Key Takeaways:** Page provides the total element count and total page count, so it can incur COUNT cost. Slice only needs to know whether more data follows, making it well suited for load-more flows. In Spring Data REST, clients should navigate using the **next** and **prev** links returned by HAL.

## References

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Commons — Paging, Iterating Large Results, Sorting and Limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
