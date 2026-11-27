# Combining Domain Parameters with Pageable and Sort

A search endpoint in Spring Data REST often needs to accept both domain criteria and paging/sorting requests. For example, a client wants to find paid orders for a customer, retrieve only 20 results per page, and sort by newest creation date. Domain parameters determine **which records match**; `Pageable` and `Sort` determine **how the results are paginated and ordered**.

## 1. Separating filter parameters from pagination parameters

Suppose the domain has an `Order` entity with `status`, `customer`, and `createdAt` properties. A query might need:

- Domain parameter: `status` to filter order status.
- Domain parameter: `customerId` to filter by customer.
- Pagination parameter: `page` to select the page.
- Pagination parameter: `size` to limit the number of items per page.
- Sorting parameter: `sort` to choose the property and sort direction.

Example request:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
```

In this request, `status` and `customerId` are the application's search criteria. `page`, `size`, and `sort` are Spring Data infrastructure parameters that control how results are fetched.

Separating these two groups keeps the API clean: adding a domain filter does not alter how pagination works, and changing page size or sort does not alter the filter criteria.

## 2. Declaring a query method accepting Pageable

Spring Data repositories support passing `Pageable` into query methods. For example:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    Page<Order> findByStatusAndCustomer_Id(
        @Param("status") OrderStatus status,
        @Param("customerId") Long customerId,
        Pageable pageable
    );
}
```

Here:

- `findByStatusAndCustomer_Id` is a derived query method: Spring Data parses the method name to create filter conditions on status and the customer's id.
- `@Param("status")` advertises the `status` query parameter name.
- `@Param("customerId")` advertises the `customerId` query parameter name.
- `Pageable pageable` instructs Spring Data to apply page, size, and sort to the query.
- `Page<Order>` indicates the result includes page information, including item count and total query results.

The `Pageable` parameter is a special Spring Data parameter. You do not need to declare it as a domain parameter with `@Param`. Spring Data REST recognizes paging and sorting parameters and converts them into a `Pageable` object when calling the repository method.

If you want a more readable search method URL, you can customize the path and relation:

```java
@RestResource(
    path = "by-status-and-customer",
    rel = "byStatusAndCustomer"
)
Page<Order> findByStatusAndCustomer_Id(
    @Param("status") OrderStatus status,
    @Param("customerId") Long customerId,
    Pageable pageable
);
```

The search link advertised in HAL is the discovery point for the endpoint. Actual path and relation depend on export configuration; the example above illustrates one naming choice.

## 3. Pageable controls page and size

`Pageable` bundles the information needed to fetch a subset of results:

- `page`: page index, zero-based.
- `size`: maximum number of items to retrieve on a page.
- `sort`: sort order before slicing into pages.

For example:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=1&size=20
Accept: application/hal+json
```

`page=1` means the second page under zero-based indexing. With `size=20`, the client requests up to 20 orders on that page.

Spring Data REST has a configurable default page size and maximum limit. These can be adjusted through `RepositoryRestConfiguration`, for example:

```java
@Configuration
public class RestConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
```

The values 20 and 100 in the example are illustrative configuration choices, not fixed limits in Spring Data REST. Set the max page size according to response payload size, query performance, and client capabilities. This limit prevents requests from asking for an overly large page that causes unnecessary load.

If `page` or `size` is omitted, Spring Data REST uses the configured defaults. Clients should not assume the default page size is the same across every environment.

## 4. Sort orders results before pagination

`Sort` describes the properties to sort by and the sort direction. For Spring Data REST URL parameters, the common format is:

`sort=property,direction`

Where:

- `property` is the domain property name to sort by.
- `direction` is `asc` (ascending) or `desc` (descending).

Example sorting by newest creation date:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc
```

Multiple sort criteria can be passed by repeating the `sort` parameter:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc&sort=id,asc
```

This example prioritizes `createdAt` descending; if multiple orders share the same creation timestamp, `id` ascending is used as the tie-breaker. Adding a stable secondary criterion keeps pagination from shifting erratically when many records share the primary sort value.

The sort name is normally a property path in the domain model, not an SQL column name or a renamed field in the JSON representation. For instance, `customer.name` can be a property path if the query and mapping support it. Use properties that the repository can sort on; non-existent fields or properties that do not support sorting can cause the request to fail.

Sorting should also be controlled according to API needs. Do not allow clients to arbitrarily request expensive or sensitive properties; you can restrict supported sort keys at the API/service layer and optimize database indexes for commonly used sort orders.

## 5. Combining filters, Pageable, and Sort in one request

A complete request can include multiple domain parameters alongside pagination parameters:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc&sort=id,asc
Accept: application/hal+json
```

Conceptually, the server processes this as:

1. Bind `status` and `customerId` to the query method parameters.
2. Convert `page`, `size`, and `sort` into a `Pageable`.
3. The repository executes the query with the domain criteria and paging/sorting instructions.
4. Spring Data REST renders the results and page metadata according to the configured representation.

Filter criteria determine the matching set. Sorting is applied to the matching set before slicing elements for the page. Therefore, page 0 and page 1 must use the same filter criteria and sort order if the client wants to browse a consistent result set.

If the client changes `status` or `customerId` while on page 4, it should reset to page 0 because the result set has changed. Similarly, changing the sort order can shift page boundaries.

## 6. Distinguishing Page, Slice, List, and Sort

The return type of a query method determines the metadata the client receives:

| Return type | Meaning |
|---|---|
| `Page<T>` | Includes page content and metadata such as total elements and total pages |
| `Slice<T>` | Includes content and whether a next page exists; does not require total element count across the whole set |
| `List<T>` | List of results; no page metadata like `Page` |
| `T` or `Optional<T>` | A single result or possibly no result; not a paginated collection |

When a UI needs to show the total result count, total pages, and page-jump controls, `Page<T>` is usually appropriate. If it only needs to know whether more items can be loaded and wants to avoid a total count query, `Slice<T>` may be a better fit when the repository and endpoint support that return type.

A query method accepting `Sort` can be used when only sorting is needed without page/size. If `Pageable` is used, sort information is already inside pageable; there is no need to declare a separate `Sort` parameter on the same method. Pick one mechanism based on the method's needs and Spring Data's support.

## 7. Paginated responses in HAL

For a query method returning `Page<Order>`, Spring Data REST can return a HAL collection representation, including navigation links and page metadata. Abbreviated example:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20"
    },
    "next": {
      "href": "https://api.example.test/orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=1&size=20"
    },
    "profile": {
      "href": "https://api.example.test/profile/orders"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": 501,
        "status": "PAID"
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 47,
    "totalPages": 3,
    "number": 0
  }
}
```

This is an illustrative response. Actual collection relation names, links, fields, and metadata depend on the repository resource rel, projection configuration, and Spring Data REST version.

Clients should follow the `next` or `prev` links provided by the server when present, preserving domain parameters and sort. Do not manually construct the next page URL in a way that drops the current filters or sort.

## 8. Common errors and how to handle them

| Issue | Possible cause | Resolution |
|---|---|---|
| Search method does not appear | Method is not exported or repository does not expose query methods | Check `@RestResource`, repository export, and search links |
| Domain parameter fails to bind | Query parameter name mismatches `@Param` name or type cannot be converted | Check parameter names and converters |
| Page always returns the first page | Missing `page` or client sends incorrect page index | Send `page` as zero-based |
| Result has fewer items than size | Last page, filter lacks enough results, or server enforces max page size | Read page metadata and limit configuration |
| Sort does not work or throws an error | Wrong property path or method does not support sorting on that property | Use a valid domain property name |
| Pages duplicate or skip items when data changes | Unstable sort or records inserted/deleted between requests | Add a unique secondary sort criterion and consider an appropriate snapshot/scroll mechanism |
| Slow query | Filter, sort, or count query lacks suitable indexes | Inspect the execution plan and optimize indexes |

In particular, offset-based pagination does not automatically guarantee a consistent snapshot when data changes continuously. If a new record is inserted before the current position between two page loads, clients may observe duplicate or skipped items. A stable sort with a unique secondary key reduces shuffling caused by duplicate values, though it does not replace snapshot or cursor-based pagination if business requirements demand traversing a continuously changing dataset.

## 9. Complete example from repository to client

Repository:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(
        path = "by-status-and-customer",
        rel = "byStatusAndCustomer"
    )
    Page<Order> findByStatusAndCustomer_Id(
        @Param("status") OrderStatus status,
        @Param("customerId") Long customerId,
        Pageable pageable
    );
}
```

Client:

```bash
curl -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "status=PAID" \
  --data-urlencode "customerId=42" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" \
  --data-urlencode "sort=createdAt,desc" \
  --data-urlencode "sort=id,asc" \
  https://api.example.test/orders/search/by-status-and-customer
```

This request filters orders by status and customer, fetches the first page with up to 20 items, and sorts by creation date descending then id ascending. The server can return a HAL collection with pagination metadata so the client can continue following navigation links.

## 10. Search endpoint design checklist

1. Put domain criteria into query method parameters with clear names.
2. Use `@Param` to advertise stable query parameter names for clients.
3. Use `Pageable` when page, size, and sort are needed together; use `Sort` when only sorting is needed.
4. Return `Page<T>` when clients need total element count and total page count.
5. Configure default page size and max page size appropriate for system load.
6. Expose the search method via repository export and customize path/relation when needed.
7. Only support appropriate sort properties, adding a unique secondary criterion when stable ordering is required.
8. When browsing subsequent pages, preserve filters and sort or directly follow HAL navigation links.
9. Verify indexes and count queries for commonly used filter/sort combinations.

When domain parameters are properly combined with `Pageable` and `Sort`, a search method can serve a specific query while still supporting consistent pagination and sorting. The client controls search criteria via query parameters, while Spring Data REST and Spring Data handle pagination, ordering, and hypermedia navigation under the advertised contract.
