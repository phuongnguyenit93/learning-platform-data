# Conditions for a Collection Resource to Support Pagination and Sorting

## Objectives

When Spring Data REST exports a repository as a REST API, the collection resource endpoint can return all records or a subset of results by page. Pagination limits the amount of data in each response; sorting lets clients request result ordering without creating separate endpoints for each sort order.

These two capabilities only appear when the repository and the method used by Spring Data REST provide the corresponding support. Simply having an endpoint shaped like `GET /people` does not automatically guarantee that it accepts `page`, `size`, and `sort`.

## 1. The Repository Must Be Exported by Spring Data REST

Spring Data REST only creates a collection resource for repositories that are discovered and allowed to be exported. For example, the repository below is exported at the path `/people`:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

If `path` is not declared, Spring Data REST automatically derives the path from the domain type name or repository configuration. You can use `@RepositoryRestResource(exported = false)` to disable exporting for the entire repository.

The list-reading method must also be exported. If `findAll(...)` methods do not exist or are hidden using `@RestResource(exported = false)`, a GET request to the collection resource may receive `405 Method Not Allowed`.

## 2. The Repository Must Provide Pagination or Sorting Methods

Spring Data REST selects the collection-reading method in the following priority order:

1. `findAll(Pageable)`: supports pagination and can include sorting.
2. `findAll(Sort)`: supports sorting but does not provide pagination.
3. `findAll()`: returns a list without dynamic pagination or sorting capabilities.

Therefore, for a collection resource to support both capabilities, the repository must have a `findAll(Pageable)` method and the corresponding Spring Data infrastructure must implement that method. When this method is present and exported, Spring Data REST can convert HTTP parameters into a `Pageable` object; this object contains the page number, page size, and sorting information.

Example with Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

`JpaRepository` provides CRUD, pagination, and sorting capabilities for JPA repositories. For generic repositories, you can extend `PagingAndSortingRepository<T, ID>` to get `findAll(Pageable)` and `findAll(Sort)`.

**Note for Spring Data 3.x:** `PagingAndSortingRepository` no longer extends `CrudRepository`. If you need both CRUD and pagination/sorting when using generic interfaces, combine the two interfaces or use a store-specific abstraction such as `JpaRepository`.

Example combining generic interfaces:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {
}
~~~

Execution capability also depends on the storage module in use. A JPA repository must be implemented by Spring Data JPA; repositories for MongoDB, JDBC, or other stores must use the corresponding abstraction that supports `Pageable` and `Sort`. Merely adding the parameter type to a custom-implemented method does not make the underlying query automatically paginate or sort.

## 3. Custom Query Methods Must Declare the Correct Signature

Query methods are exported by Spring Data REST as search resources under the `/search` path. For a query method to support pagination, the method signature must:

- Accept an additional parameter of type `Pageable`.
- Return `Page<T>` or `Slice<T>`, instead of returning only `List<T>`.
- Be exported and callable via the REST repository.

Example:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    Page<Person> findByLastNameStartingWithIgnoreCase(
            @Param("prefix") String prefix,
            Pageable pageable);
}
~~~

Spring Data REST can export the method above as a search endpoint similar to:

~~~http
GET /people/search/by-last-name?prefix=Ng&page=0&size=5
~~~

Clients can add the `sort` parameter to the same URL. If a method accepts `Pageable` but returns `List<T>`, Spring Data may limit the data according to Pageable in some internal invocations, but Spring Data REST does not have a `Page` or `Slice` type to fully represent paginated results and navigation links. Therefore, for query methods exported through Spring Data REST, use `Page<T>` or `Slice<T>` when pagination is needed.

If only sorting is needed for a query method, it can accept a `Sort` parameter:

~~~java
List<Person> findByActiveTrue(Sort sort);
~~~

This method supports dynamic sorting; it does not automatically provide total page count information. When both pagination and sorting are needed, use `Pageable`.

## 4. HTTP Parameters Accepted by a Collection Resource

When a repository has pagination capability, Spring Data REST accepts the following parameters by default:

| Parameter | Meaning | Default Value |
|---|---|---|
| `page` | Page number, starting from 0 | `0` |
| `size` | Maximum number of records per page | `20` |
| `sort` | Property and sort direction | No dynamic sorting |

Example fetching the first page, up to 10 people, sorted by last name ascending:

~~~http
GET /people?page=0&size=10&sort=lastName,asc
~~~

Sort by multiple properties by repeating the `sort` parameter. The order of directives in the query string is preserved in the sort object:

~~~http
GET /people?page=0&size=10&sort=lastName,asc&sort=firstName,desc
~~~

In the example above, the system sorts by `lastName` ascending; if multiple records share the same last name, it continues sorting by `firstName` descending.

Property names must match domain model properties that Spring Data can query, not arbitrary SQL column names. You can use a property path for nested properties. Spring Data REST does not support sorting directly by an association that is exported as a link to a top-level resource.

To keep results stable across pages when multiple records share the same sort values, you should add a discriminating property as the final criterion, for example:

~~~http
GET /people?page=0&size=10&sort=lastName,asc&sort=id,asc
~~~

## 5. Configuring Page Size and Parameter Names

The default value is 20 records per page. You can change the default size and maximum limit to prevent clients from requesting an overly large page. This can be configured with Spring Boot properties:

~~~properties
spring.data.rest.default-page-size=25
spring.data.rest.max-page-size=100
~~~

If the API requires different parameter names, you can configure them through `RepositoryRestConfigurer`:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
        config.setPageParamName("p");
        config.setLimitParamName("limit");
        config.setSortParamName("order");
    }
}
~~~

After this configuration, clients use `p`, `limit`, and `order` instead of `page`, `size`, and `sort`. Parameter names must be consistent between the server and client.

## 6. Indicators in the HAL Response

A paginated response typically contains:

- `_embedded`: the elements belonging to the current page.
- `_links.self`: the link to the current page, often a URI template for optional parameters.
- `_links.next` and `_links.prev`: links to the next or previous page when they exist.
- `page`: information about page size, total elements, total pages, and current page number.

Abbreviated example:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people{&sort,page,size}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/people?page=1&size=10{&sort}",
      "templated": true
    }
  },
  "_embedded": {
    "people": []
  },
  "page": {
    "size": 10,
    "totalElements": 52,
    "totalPages": 6,
    "number": 0
  }
}
~~~

The page number in the response is also 0-based. On the first page there is no `prev` link; on the last page there is no `next` link. With `Page<T>`, the response can provide the total number of elements and total pages. `Slice<T>` is useful when you only need to know whether a next page exists and do not need to count the total number of records.

## 7. How to Troubleshoot When an Endpoint Does Not Accept Pagination or Sorting

| Symptom | Cause to Check |
|---|---|
| Collection GET returns all data without page links | The repository does not have or does not export `findAll(Pageable)`; the repository only has `findAll()` or only basic CRUD. |
| Collection GET returns `405 Method Not Allowed` | There is no suitable `findAll(...)` method or those methods have export disabled. |
| Query method ignores `page` and `size` | The method does not accept `Pageable`, or does not return `Page<T>`/`Slice<T>`. |
| Query method ignores the `sort` parameter | The method signature lacks `Pageable` or `Sort`, or the method is not exported. |
| Sort reports a property error | The property name does not exist in the domain model, has an incorrect property path, or is sorting by an association linked to another resource. |
| Client requests a large page but server returns fewer records | Check the `maxPageSize` limit and page size configuration. |

When diagnosing, inspect the exact repository interface and method signature that Spring Data REST actually invokes. Do not check only the client URL: the `page`, `size`, and `sort` parameters only take effect when the server-side method is capable of accepting and processing them.

## Key Takeaways

A collection resource supports **pagination** when the exported method is capable of accepting `Pageable`, typically `findAll(Pageable)`. It supports **sorting** when the invoked method can accept `Sort`, or accept `Pageable` containing sort information. For custom query methods, you must declare `Pageable` and return `Page<T>` or `Slice<T>` so Spring Data REST represents paginated results properly. The repository must be exported and the store implementation must be able to execute those abstractions.

## References

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/4.5/repository-resources.html)
- [Spring Data — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
