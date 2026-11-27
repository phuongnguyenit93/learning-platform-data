# The first, prev, next, and last Links in Paginated Results

## Context

When Spring Data REST exports a repository that supports pagination, a GET request to the collection resource can return a single page of data instead of all records. The HAL representation contains not only the elements of the current page, but also navigation links so the client can move to the first page, previous page, next page, and last page.

Four common relations are:

- `first`: the first page.
- `prev`: the page immediately before the current page.
- `next`: the page immediately after the current page.
- `last`: the last page.

For example, the collection resource `/orders` may return the links:

    /orders?page=0&size=10
    /orders?page=1&size=10
    /orders?page=2&size=10

Clients should use the `href` provided by the server in HAL for navigation. These links reflect the pagination configuration, sorting, base path, and data state published by the server.

## 1. Enabling Pagination on a Repository

Spring Data REST automatically exports repository resources. If a repository supports `PagingAndSortingRepository` or an interface extending paging/sorting capabilities such as `JpaRepository`, the collection resource can be queried by page.

Example:

    @Entity
    public class Order {

        @Id
        @GeneratedValue
        private Long id;

        private String status;

        private Instant createdAt;

        // constructors, getters and setters
    }

    @RepositoryRestResource(path = "orders")
    public interface OrderRepository
            extends JpaRepository<Order, Long> {
    }

With the repository above, the collection resource has the path:

    http://localhost:8080/orders

Paginated request:

    GET /orders?page=0&size=10
    Accept: application/hal+json

Two main parameters:

| Parameter | Meaning |
| --- | --- |
| `page` | Page index, starting from 0 |
| `size` | Maximum number of elements requested for a page |

Because the page index starts at 0, `page=0` is the first page and `page=1` is the second page. `size=10` requests at most 10 elements per page. The last page may contain fewer elements if the total number of records is not divisible by the page size.

## 2. Reading the HAL Structure of a Page

An abbreviated response might look like:

    {
      "_embedded": {
        "orders": [
          { "id": 41, "status": "PAID" },
          { "id": 42, "status": "NEW" }
        ]
      },
      "_links": {
        "first": {
          "href": "http://localhost:8080/orders?page=0&size=2"
        },
        "prev": {
          "href": "http://localhost:8080/orders?page=2&size=2"
        },
        "self": {
          "href": "http://localhost:8080/orders?page=3&size=2"
        },
        "next": {
          "href": "http://localhost:8080/orders?page=4&size=2"
        },
        "last": {
          "href": "http://localhost:8080/orders?page=6&size=2"
        }
      },
      "page": {
        "size": 2,
        "totalElements": 13,
        "totalPages": 7,
        "number": 3
      }
    }

This hypothetical example is on the page with `number=3`, meaning the fourth page in human counting. Each page has at most 2 elements, with 13 elements and 7 pages in total.

Key parts:

- `_embedded.orders` holds the records belonging to the current page. The relation name inside `_embedded` is usually based on the repository's collection relation.
- `_links` holds the navigation URIs. Each link has a relation name and an `href`.
- `page.size` is the applied page size.
- `page.totalElements` is the total number of elements matching the query.
- `page.totalPages` is the total number of pages.
- `page.number` is the current page index, starting from 0.

In real responses, besides pagination links there may also be `self`, `profile`, `search`, or other links. Do not assume the response only contains the exact fields shown in the example.

## 3. Meaning of Each Relation

### first — go back to the first page

`first` points to the first page of the result set. With the default convention, the first page typically has `page=0`.

Example:

    "_links": {
      "first": {
        "href": "http://localhost:8080/orders?page=0&size=10"
      }
    }

Clients can use this link when the user selects the “First” button or wants to return to the beginning of the list after viewing later pages.

### prev — go to the immediately preceding page

`prev` points to the page immediately before the current page.

If the client is on `page=3`, the `prev` link usually points to `page=2`. This is one step backward, not a link to the first page.

On the first page there is no previous page, so the server typically omits the `prev` relation. Clients should interpret the absence of this link as having no backward step available.

### next — go to the immediately following page

`next` points to the page immediately after the current page.

If the client is on `page=3`, the `next` link usually points to `page=4`. When the user chooses “Next”, the client requests the exact URI in `next.href`.

On the last page there is no next page, so the server typically does not return the `next` relation. The UI can disable the “Next” button when this link does not exist.

### last — go to the last page

`last` points to the last page of the result set. For example, when `totalPages=7`, the last page has a 0-based index of 6.

The client does not need to calculate `totalPages - 1` and assemble the URL itself. Using `last.href` ensures the client follows the actual URI generated by the server.

### self — current page

In addition to the four relations above, `self` represents the URI of the current page. This link is useful for saving or sharing the current list state, including the parameters applied by the server.

## 4. Calling the Collection Resource and Following Links

You can use curl to fetch the first page:

    curl -i       -H "Accept: application/hal+json"       "http://localhost:8080/orders?page=0&size=10"

The response contains links in `_links`. To switch pages, take the `href` value of the desired relation and send a GET request to that URI:

    curl -i       -H "Accept: application/hal+json"       "http://localhost:8080/orders?page=1&size=10"

The second example illustrates a URI that can be called; in a real application, the client should take the URI from `_links.next.href` of the previous response instead of constructing `page=1` manually.

A simple JavaScript client can work like this:

    async function loadPage(url) {
      const response = await fetch(url, {
        headers: {
          Accept: "application/hal+json"
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return response.json();
    }

    const current = await loadPage(
      "http://localhost:8080/orders?page=0&size=10"
    );

    const nextHref = current._links?.next?.href;

    if (nextHref) {
      const nextPage = await loadPage(nextHref);
      console.log(nextPage._embedded?.orders ?? []);
    }

The snippet checks for the existence of `next.href` before calling. If there is no link, the client does not attempt to navigate to the next page.

In applications with a base URL, context path, or reverse proxy, use the URI in the link as-is. Do not prepend the hostname or prefix a second time if `href` is already a full URI.

## 5. Combining Pagination with Sorting

Spring Data REST supports the `sort` parameter alongside `page` and `size`.

Example:

    GET /orders?page=0&size=10&sort=createdAt,desc

This request asks to sort by `createdAt` descending. You can combine multiple criteria by repeating the `sort` parameter:

    GET /orders?page=0&size=10&sort=status,asc&sort=createdAt,desc

When generating pagination links, the server can preserve the active page size and sorting criteria. Therefore, `next.href` and `prev.href` are a safe way to move within the same result set.

To keep ordering across pages stable when multiple records share the same sort value, you should add a unique tie-breaking criterion, such as ID:

    GET /orders?page=0&size=10&sort=createdAt,desc&sort=id,desc

If you sort only by a field with many duplicate values, the order among records with the same value may be unstable between requests. This can cause records to appear on different pages when data changes or when the database returns a non-deterministic order for equal values.

Property names used in `sort` are properties recognized by Spring Data in the domain model, not database column names by default.

## 6. Navigation on the First, Middle, and Last Pages

Links may appear differently depending on the page position:

| Position | first | prev | next | last |
| --- | --- | --- | --- | --- |
| First page | Usually present | Absent | Present if more pages follow | Usually present if determinable |
| Middle page | Usually present | Present | Present | Usually present if determinable |
| Last page | Usually present | Present if a previous page exists | Absent | Usually present |
| Only one page | May be present | Absent | Absent | May point to the same single page |

This is a semantic reading guide. Clients must check the actual links in each response; do not require the server to always return all four relations. Inapplicable links may be omitted from `_links`.

If the collection is empty, metadata may indicate `totalElements=0` and `totalPages=0`. In that case there is no next data page to navigate to. The client should display an empty state rather than concluding that a missing link is a network error.

## 7. Using Links to Drive the UI

A list UI can display:

- A “First” button based on `_links.first`.
- A “Previous” button based on `_links.prev`.
- A “Next” button based on `_links.next`.
- A “Last” button based on `_links.last`.
- “Page X / Y” info from `page.number` and `page.totalPages`.

Since `page.number` starts from 0, if you want to show a user-friendly page number, you can display `page.number + 1`. This is only for presentation; when calling the API, the client still uses URIs from HAL.

Example display logic:

    const pageNumberForUser = page.page.number + 1;
    const totalPages = page.page.totalPages;

    const canGoFirst = Boolean(page._links?.first?.href);
    const canGoPrevious = Boolean(page._links?.prev?.href);
    const canGoNext = Boolean(page._links?.next?.href);
    const canGoLast = Boolean(page._links?.last?.href);

The UI should rely on actual existing links to enable/disable buttons. Do not rely solely on `number < totalPages - 1` and build the next URI manually; doing so bypasses the URIs and configuration published by the server.

## 8. Configuring Sizes and Parameter Names

Spring Data REST can configure the default page size and maximum size limit. With Spring Boot, commonly used properties in `application.properties` include:

    spring.data.rest.default-page-size=20
    spring.data.rest.max-page-size=100

The default size is applied when the client does not send `size`. The maximum limit helps the server guard against requests asking for too many elements. Specific values should be chosen based on the application's data volume and query cost.

Default pagination/sorting parameter names are usually:

- `page`: page index.
- `size`: page size (limit parameter).
- `sort`: sorting criteria.

Spring Data REST also allows customizing parameter names via repository REST configuration, such as `setPageParamName`, `setLimitParamName`, and `setSortParamName` on `RepositoryRestConfiguration`. When parameter names are changed, the URIs emitted by the server reflect that configuration. This is another reason for clients to follow links rather than concatenating query strings themselves.

## 9. Notes When Data Changes

The `first`, `prev`, `next`, and `last` links describe navigation across the result set produced by the server at the time of the request. They do not guarantee that a data snapshot is preserved across multiple requests.

For example, the client is viewing the second page. Meanwhile, a new order is inserted at the top of a list sorted descending. When the client calls the `next` link, records may shift between pages. Some records may be repeated or skipped between loads if the data changes enough.

Ways to mitigate this issue:

1. Use stable sorting with a unique field as the final criterion.
2. Keep the page size consistent throughout a traversal pass.
3. When business requirements demand a consistent snapshot, design appropriate APIs and transactions rather than expecting pagination links to provide a snapshot automatically.
4. For very large datasets or continuous traversal in write-heavy environments, consider cursor/keyset pagination with an appropriate API. Default Spring Data REST HAL links usually model page/size pagination.

## 10. Common Issues

| Symptom | What to Check |
| --- | --- |
| No `next` link | On the last page, only one page exists, or no data; check `page.totalPages` and the remaining links |
| No `prev` link | On the first page; this is usually a valid state |
| No `first` or `last` link | Check the actual response, resource type, configuration, and page determinability; client must tolerate missing links |
| 400 Bad Request | Invalid `page`, `size`, `sort` values, or unsupported sort property name |
| Fewer elements than `size` | Possibly on the last page; `size` is a maximum, not a guarantee that every page is full |
| Link is unreachable | Check base path, proxy, hostname, authentication, and access permissions |
| Duplicate or missing records across pages | Check whether sorting is stable and whether data changed between requests |

When debugging, follow this order:

1. Send a GET to the collection resource with `Accept: application/hal+json`.
2. Read `page.number`, `page.totalPages`, and `page.totalElements`.
3. Check whether the needed relation is present in `_links`.
4. Call the exact `href` and preserve any required authentication/representation headers.
5. If the link returns an error, inspect the external URL, base path, reverse proxy, and Spring Security.

## 11. Hands-On Exercise

Suppose the repository `OrderRepository` is exported at `/orders`. There are 23 orders, and the client requests 5 orders per page, sorted by newest creation time first:

    GET /orders?page=0&size=5&sort=createdAt,desc
    Accept: application/hal+json

Tasks:

1. Call the request above and read `page.totalElements`, `page.totalPages`, and `page.number`.
2. Take `_links.next.href` and call that link to load the next page.
3. From a middle page, use `_links.prev.href` to go back.
4. Use `_links.first.href` to return to the start of the list.
5. Use `_links.last.href` to go to the last page.
6. On the last page, confirm the `next` relation is absent if there is no subsequent page.
7. Try adding `sort=id,desc` to create a stable order when `createdAt` values collide.
8. Try calling the API with a page size exceeding the configured limit and observe how the server handles it.

Self-check questions:

- Why is `page=0` the first page?
- How does the `prev` relation differ from `first`?
- Why should a client call `next.href` instead of incrementing `page` itself?
- When does `next` not appear in the response?
- What problem does stable sorting help reduce when navigating multiple pages?

## References

- [Spring Data REST Reference — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data Commons Reference — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
