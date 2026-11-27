# 404 for Missing Resources vs. Queries Returning Empty Collections in Spring Data REST

## Objectives

When working with Spring Data REST, it is necessary to distinguish two situations that may look similar in the UI: a specific resource does not exist, and a valid query finds no matching items.

These two situations have different HTTP meanings:

- Requesting a single resource by identifier when that resource does not exist typically returns **404 Not Found**.
- Requesting a collection resource or a query returning a list when no items match typically returns **200 OK** with an empty collection.

After this lesson, you can identify the type of resource being called, interpret status codes properly, handle empty collections on the client, and test both cases independently.

## 1. Distinguishing item resources and collection resources

Spring Data REST typically publishes two main resource types from a repository:

- **Item resource:** represents a specific entity, usually accessed via a URI with an identifier, such as **/orders/42**.
- **Collection resource:** represents a set of entities, such as **/orders**; may accept query parameters for filtering, paging, or sorting.

Suppose an Order repository is published at **/orders**.

Reading a specific order:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

If the order with id 42 exists, the server returns the order representation, typically with **200 OK**.

If no such order exists, Spring Data REST returns **404 Not Found**, because the item resource requested by the client does not exist.

Conversely, reading the collection:

~~~http
GET /orders
Accept: application/hal+json
~~~

If the repository has no orders yet, the collection still exists. The server can return **200 OK** with a collection containing zero items and the corresponding paging metadata.

Key point: an empty collection is a valid result of reading a collection. It does not mean the collection endpoint is missing.

## 2. A query with no results is still a successful request

Suppose the repository has a method to find orders by status:

~~~java
@RepositoryRestResource
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    Page<Order> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
~~~

Spring Data REST can publish the finder under the search resource. With the default name, the client calls:

~~~http
GET /orders/search/findByStatus?status=CANCELLED&page=0&size=20
Accept: application/hal+json
~~~

If no orders have status **CANCELLED**, the query is still valid. The server returns **200 OK** and an empty collection representation.

Illustrative example of the response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/search/findByStatus?status=CANCELLED"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

This is an illustrative structure. HAL may omit the **_embedded** section when the collection is empty; specific links and metadata depend on the return type, configuration, and Spring Data REST version.

The client should handle responses based on the status code and collection content. The absence of elements in **_embedded** should not be treated as an HTTP error.

## 3. Comparing the two scenarios

Suppose the database currently has orders 10 and 11, but no order 99. At the same time, there are no orders with status CANCELLED.

| Request | Meaning | Typical result |
|---|---|---|
| **GET /orders/10** | Read an existing item resource | **200 OK** |
| **GET /orders/99** | Read a nonexistent item resource | **404 Not Found** |
| **GET /orders?status=CANCELLED** | Read filtered collection, no results | **200 OK**, empty collection if the endpoint supports this filter |
| **GET /orders/search/findByStatus?status=CANCELLED** | Call a finder returning an empty collection or Page | **200 OK**, empty collection |

Collection requests may use finder URLs or query parameters depending on the published API. The examples above illustrate the fundamental difference between an item resource and a collection resource.

You can remember this with a question: is the client requesting **a specific entity** or requesting **a result set**?

- If requesting a specific entity by URI and the entity does not exist, return 404.
- If requesting a result set and no entities match, return 200 with an empty set.

## 4. Watch the return type of finder methods

Not all search methods return a collection. The return type of the repository method affects how Spring Data REST represents the result.

Examples of result forms:

~~~java
List<Order> findByStatus(OrderStatus status);

Page<Order> findByStatus(
        OrderStatus status,
        Pageable pageable);

Optional<Order> findByExternalCode(String code);
~~~

- **List** or **Page** represents multiple results. When there are no elements, the result is an empty collection and the request typically returns **200 OK**.
- **Optional<Order>** represents at most one result. When no entity exists, the result is Optional.empty; how the single resource and status are represented should be verified against the version, finder publication settings, and application configuration. Do not infer that a single-result finder will return an empty collection.
- Methods returning a single entity directly should also be checked when no result is found; do not equate them with finders returning List or Page.

If the API needs list semantics, design the finder with a collection or Page return type. If the API needs single-resource semantics, define the behavior when nothing is found and test the actual status code.

## 5. Case of a page with no items

A collection may return empty content for two different reasons:

1. No records match the filter.
2. The filter has matching data, but the client requested a page beyond the available range.

For example, the database has 35 matching orders with page size 10, yet the client requests page 8:

~~~http
GET /orders/search/findByStatus?status=PAID&page=7&size=10
Accept: application/hal+json
~~~

The requested page may contain no elements, but the collection and query are still valid. The response is still typically **200 OK**. Metadata may indicate **totalElements=35**, **totalPages=4**, and **number=7**.

Therefore, when content is empty, the client should also inspect paging metadata:

- **totalElements = 0:** no records match the query.
- **totalElements > 0** but empty content: the client may have requested a page past the last page.
- **totalPages** and **number:** help determine whether the current page falls within the result range.

Do not turn an empty page into 404 just because the data array has zero elements.

## 6. Client-side handling

The client should branch based on status code and resource type.

General logic example:

~~~text
Send GET request
    |
    +-- 200 OK
    |     |
    |     +-- Item resource: display entity
    |     |
    |     +-- Collection resource:
    |             has items -> display list
    |             empty -> display "No results" state
    |
    +-- 404 Not Found
    |     -> report resource does not exist
    |        or path is not published
    |
    +-- 400 / 401 / 403 / 406 / 5xx
          -> handle the corresponding error
~~~

For an empty collection, the UI should show an appropriate empty state, such as "No orders found matching the filter". This is a normal result state and should not display an error page or a continuous retry button.

For **404**, the client can inform the user that the entity was deleted, the id is invalid, or the URI no longer exists. If reading an item resource after the user selected it from a list, you can refresh the list or return the user to the previous screen.

Do not automatically retry a GET request returning 404 as if it were a transient network error. Check the URI and resource state first.

## 7. 404 is not always just a missing entity

When receiving 404, check exactly which resource is missing:

- **Wrong identifier:** the entity has a different id or was deleted.
- **Wrong path:** the repository path or base path is incorrect.
- **Unpublished repository:** the repository is hidden, not exported, or Spring Data REST configuration did not register the endpoint as expected by the client.
- **Invalid association URI:** the association link or related resource URI is no longer valid.
- **Wrong identifier type:** the path value cannot be converted properly to the domain's id type.
- **Custom exception handling:** the application may map certain business errors to 404.
- **Security policy:** some systems intentionally return 404 to avoid disclosing the existence of resources the caller is unauthorized to view.

Therefore, do not immediately conclude from a 404 status that the entity is absent from the database. Cross-check the URL, repository export, access permissions, and server logs.

Other statuses also carry distinct meanings:

| Status | Common meaning |
|---|---|
| **400 Bad Request** | Invalid query parameter or request data |
| **401 Unauthorized** | Unauthenticated or invalid authentication credentials |
| **403 Forbidden** | Authenticated but not permitted to perform the action |
| **404 Not Found** | Requested resource or endpoint was not found |
| **406 Not Acceptable** | Server cannot fulfill the requested media type |
| **500 Internal Server Error** | Unexpected server processing error |

The error body content may vary by media type, configuration, and exception handler. Clients should rely on status codes and the published API error structure rather than a fixed message string.

## 8. Testing both cases independently

There should be separate integration tests for a missing item resource and a collection query with no results. Example using MockMvc:

~~~java
@Test
void missingOrderShouldReturnNotFound() throws Exception {
    mockMvc.perform(get("/orders/999999")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotFound());
}

@Test
void emptySearchShouldReturnOk() throws Exception {
    mockMvc.perform(get("/orders/search/findByStatus")
            .param("status", "CANCELLED")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk());
}
~~~

This is a guiding example; replace URLs, finder names, parameters, and media types according to your actual repository. An empty collection test should prepare data so that no matching results exist, then verify the response is a valid collection.

You can also test:

- Existing item resource returns 200 and the correct entity.
- Non-empty collection returns 200 and contains the expected items.
- Empty collection returns 200 and empty content.
- Out-of-range page returns 200 with appropriate paging metadata.
- Finder returning a single missing entity behaves according to the chosen contract.
- 401/403 cases are not confused with 404 due to security policies.

## Takeaways

**404 Not Found** is appropriate when the client requests a specific resource that the server cannot find or has not published at that URI. A valid query returning an empty list is still **200 OK**: the server processed it successfully and the result simply has no matching items. Distinguish item resources from collection resources, check finder return types, and read paging metadata before deciding whether to show an empty state or an error to the user.