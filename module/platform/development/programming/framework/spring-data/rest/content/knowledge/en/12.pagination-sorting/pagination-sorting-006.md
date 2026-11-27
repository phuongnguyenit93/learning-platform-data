# Configuring Default Page Size and Maximum Page Size

## Objectives

Spring Data REST paginates collection resource results when the repository supports `Pageable`. Two key limits are:

- **Default page size:** the number of elements the server returns when the client does not specify `size`.
- **Maximum page size:** the maximum number of elements the server allows in a single page, even when the client requests more.

Configuring these two values gives the API predictable behavior and prevents a single request from loading an excessively large dataset.

## Pagination Parameters

Spring Data REST uses the following query parameters by default:

| Parameter | Meaning | Default Value |
| --- | --- | --- |
| `page` | Page number, starting from `0` | `0` |
| `size` | Requested number of elements in a page | Server's default page size |
| `sort` | Property and sort direction | Unsorted if not specified |

Example retrieving the first page with 10 elements per page:

    GET /api/orders?page=0&size=10

Retrieving the second page and sorting by `createdAt` descending:

    GET /api/orders?page=1&size=10&sort=createdAt,desc

`page=0` is the first page; `page=1` is the second page. If `page` is omitted, the server uses the first page. If `size` is omitted, the server uses the configured default page size.

## Configuring with Spring Boot

In `application.properties`, set the following two properties:

    spring.data.rest.default-page-size=25
    spring.data.rest.max-page-size=100

With this configuration:

- Requests without `size` receive at most 25 elements per page.
- Clients can request a smaller size, for example `size=10`.
- If a client requests `size=500`, the server caps the page size at a maximum of 100.

You can set the same configuration in `application.yml`:

    spring:
      data:
        rest:
          default-page-size: 25
          max-page-size: 100

Spring Data REST typically has a default page size of 20 and a max page size of 2000 if the application does not override the configuration. Set explicit values in your application so the API does not depend on framework-version defaults.

## Configuring with Java

If the application manages Spring Data REST configuration in Java, you can implement `RepositoryRestConfigurer` and set the values on `RepositoryRestConfiguration`:

    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
    import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
    import org.springframework.web.servlet.config.annotation.CorsRegistry;

    @Configuration
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config, CorsRegistry cors) {
            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        }
    }

Choose a single place to manage configuration so values are not overridden or hard to trace at startup. If using multiple Spring Boot profiles, check the configuration of the active profile.

## What Happens When a Client Requests Beyond the Limit?

Suppose the server has `max-page-size=100` and the client sends:

    GET /api/orders?page=0&size=500

The server enforces the maximum limit of 100 elements for the page. This limit protects the API against requests trying to fetch too many records at once, though it does not replace query optimization or access control.

Clients should read the pagination metadata in the response instead of assuming the server always returns the exact `size` requested. The actual number of elements also depends on matching records, the current page, and filter conditions.

## Metadata in the Response

HAL collection resources typically return pagination metadata in the `page` property, for example:

    {
      "_embedded": {
        "orders": [
          { "id": 101 },
          { "id": 102 }
        ]
      },
      "_links": {
        "self": { "href": "http://localhost:8080/api/orders?page=0&size=25" },
        "next": { "href": "http://localhost:8080/api/orders?page=1&size=25" }
      },
      "page": {
        "size": 25,
        "totalElements": 62,
        "totalPages": 3,
        "number": 0
      }
    }

Field meanings:

- `size`: the page size applied to the response.
- `totalElements`: the total number of elements matching the query.
- `totalPages`: the total number of pages.
- `number`: the current page index, starting from `0`.

Clients should prefer the navigation links (`next`, `prev`, `first`, `last`) returned by the server. If the API changes its base path or query parameter names, these links remain a reliable URL source.

## Renaming Query Parameters

Spring Data REST allows customizing the page, size, and sort parameter names. For example, in `application.properties`:

    spring.data.rest.page-param-name=pageNumber
    spring.data.rest.limit-param-name=pageSize
    spring.data.rest.sort-param-name=orderBy

Clients then use the configured names, for example:

    GET /api/orders?pageNumber=0&pageSize=25&orderBy=createdAt,desc

Only rename parameters when there is a clear API compatibility requirement. When renaming, update clients and API documentation together.

## Repositories Must Support Pagination

Pagination only works with repositories that provide `Pageable`/`Page` support. With Spring Data JPA, `JpaRepository` provides this capability out of the box. If a repository only extends a CRUD interface without pagination methods, the collection endpoint may not provide pagination behavior as expected.

Example:

    public interface OrderRepository
            extends JpaRepository<Order, Long> {
    }

Spring Data REST can use the repository's pagination methods to return the collection page by page.

## Verifying the Configuration

1. Start the application with the intended profile and configuration.
2. Call the collection endpoint without `size`, e.g., `GET /api/orders`, then check `page.size` in the response.
3. Send a request with a `size` smaller than the default to confirm clients can choose a smaller page.
4. Send a request with a `size` larger than the max, e.g., `size=500`, then verify the actual size does not exceed the limit.
5. Navigate via the `next` link and confirm `page.number` increments page by page.

Examples with default 25 and max 100:

    GET /api/orders
    GET /api/orders?page=0&size=10
    GET /api/orders?page=0&size=500

## Notes When Choosing Values

- Default page size should be small enough for fast responses and low memory usage, while still meeting the amount of data clients commonly need.
- Max page size should be based on response payload size, query complexity, database load, and application resource limits.
- Increasing max page size does not automatically make queries faster; consider indexes, projections, fetch strategies, and sorting on appropriate columns.
- Clients should iterate through pages rather than requesting one massive page to load all data.
- With continuously changing datasets, offset pages can shift between requests; if stronger consistency is needed, design a query strategy tailored to the business requirements.

Default page size determines the size when the client does not specify one; max page size sets a ceiling for every request. Configure both, then let clients use pagination metadata and links from the response to navigate.