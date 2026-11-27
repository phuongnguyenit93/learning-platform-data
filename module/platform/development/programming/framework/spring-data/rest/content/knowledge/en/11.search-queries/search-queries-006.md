# Single Return Types, Optional, Collections, Page, and Slice in Spring Data REST Search Queries

## Objectives

Spring Data REST exports repository query methods as search resources callable via HTTP GET. A method's return type determines the shape and amount of data that the query endpoint provides.

Five common types:

- **Single entity `T`**: a query expecting at most one result.
- **`Optional<T>`**: also a single-result query, but explicitly represents the not-found case.
- **Collection** such as `List<T>`, `Set<T>`: returns multiple results in one query call.
- **`Page<T>`**: returns a page along with total element count and total page count information.
- **`Slice<T>`**: returns a slice of data and indicates whether a next page exists.

Choosing the right return type affects the API contract, query performance, and how clients build pagination interfaces. This lesson uses `PersonRepository` as an example and explains both repository semantics and the HAL representations produced by Spring Data REST.

## 1. Query methods are exported as search resources

Suppose a repository is declared:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST exposes the search page at:

~~~http
GET /api/people/search
Accept: application/hal+json
~~~

The search page returns links to exported query methods. Each method has its own query method resource and is invoked via GET. A method's path and relation can be customized with `@RestResource`.

For example:

~~~java
@RestResource(path = "by-username", rel = "byUsername")
Optional<Person> findByUsernameIgnoreCase(
        @Param("username") String username);
~~~

The link advertised on the search resource has the `byUsername` relation; the client follows its `href` to execute the query:

~~~http
GET /api/people/search/by-username?username=lan
Accept: application/hal+json
~~~

The return type does not alter the principle of discoverability: the search resource lists links, and the query method resource executes the query. Clients should use the actual URLs in HAL rather than constructing paths from Java method names.

## 2. Example repository with multiple return types

A repository can provide queries with different cardinalities:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-username", rel = "byUsername")
    Optional<Person> findByUsernameIgnoreCase(
            @Param("username") String username);

    @RestResource(path = "latest-active", rel = "latestActive")
    Person findFirstByActiveTrueOrderByCreatedAtDesc();

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findAllByLastNameIgnoreCase(
            @Param("lastName") String lastName);

    @RestResource(path = "by-status-page", rel = "byStatusPage")
    Page<Person> findByStatus(
            @Param("status") PersonStatus status,
            Pageable pageable);

    @RestResource(path = "by-city-slice", rel = "byCitySlice")
    Slice<Person> findByCity(
            @Param("city") String city,
            Pageable pageable);
}
~~~

Key imports:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
~~~

The example assumes the properties `username`, `active`, `createdAt`, `lastName`, `status`, and `city` exist on the domain type. Depending on the store module, supported data types and query operators may vary.

You cannot declare two Java methods that differ only in return type while having the same name and parameter list. If you need to test multiple return types for the same criteria, give the methods different names or use separate repositories in tests.

## 3. Returning a single entity: T

When a method returns the domain type directly, Spring Data expects the query to yield at most one result:

~~~java
Person findByUsername(String username);
~~~

Semantics at the repository layer:

- Exactly one entity found: returns that entity.
- None found: returns `null`.
- More than one entity found: throws `IncorrectResultSizeDataAccessException`.

Therefore, type `T` fits when the query criteria are unique by data design, such as a username with a unique constraint or a unique business identifier.

If the query is not guaranteed unique but business logic only needs the first result, you can use `First` or `Top` limiting:

~~~java
Person findFirstByActiveTrueOrderByCreatedAtDesc();
~~~

This method requests the newest result in the active group and limits the result to at most one record. The ordering must be explicitly declared so the result does not depend on the database's default ordering.

When the query method is exported through Spring Data REST, the found result is represented as a single resource. Illustrative HAL example:

~~~json
{
  "id": 12,
  "username": "lan",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/12"
    }
  }
}
~~~

Do not infer a specific status code or body for the no-result case solely from the Java type `T`. HTTP behavior is also affected by the exporter version and how empty results are handled; test the endpoint on the actual running application.

## 4. Returning Optional<T>

`Optional<T>` represents a query that may not find an entity:

~~~java
Optional<Person> findByUsernameIgnoreCase(String username);
~~~

Repository semantics:

- One result: `Optional.of(person)`.
- No result: `Optional.empty()`.
- Multiple results: `IncorrectResultSizeDataAccessException`.

Compared to returning `T`, Optional makes the possibility of missing data explicit in Java code and forces callers to handle the empty case. It does not turn a multi-result query into a valid one; the method must still have a cardinality of at most one.

An endpoint searching by username fits Optional well when users might enter a non-existent username:

~~~http
GET /api/people/search/by-username?username=lan
Accept: application/hal+json
~~~

When found, the response contains the representation of the matching `Person`. When not found, the repository returns `Optional.empty()`. At the HTTP layer, check and test what status/body your application's version of Spring Data REST actually returns; do not assume every empty Optional always maps to the same status code across all versions.

Do not use `Optional<List<Person>>` to express a regular collection query. For multi-result queries, return `List<Person>` or a suitable collection type directly; an empty collection already expresses the zero-element case.

## 5. Returning a Collection: List, Set, Collection, or Iterable

If a query can return multiple entities and pagination metadata is not needed, use a collection type:

~~~java
List<Person> findAllByLastNameIgnoreCase(String lastName);
~~~

Spring Data also supports Java types such as `Collection<T>`, `Iterable<T>`, `List<T>`, and `Set<T>`, as well as abstractions like `Streamable<T>` and Vavr collections if the store module supports them.

Semantics:

- Results found: returns the entities in the collection.
- No results found: returns an empty collection, such as `List.of()` or a framework-created empty list.
- There is no notion of total pages or next/prev links simply because the method returns a List.

A multi-element query result is represented by Spring Data REST as a collection resource. Illustrative HAL response:

~~~json
{
  "_embedded": {
    "people": [
      {
        "id": 12,
        "username": "lan",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/12"
          }
        }
      },
      {
        "id": 18,
        "username": "minh",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/18"
          }
        }
      }
    ]
  }
}
~~~

The relation name inside `_embedded` depends on the resource/domain type configuration; the example above is illustrative only. For an empty result, the collection is still the result of the query method, though the `_embedded` section may contain no elements or be omitted depending on serialization.

**Note on large datasets:** List typically loads all results into memory. If a query can return thousands or millions of records, use Page or Slice to limit the amount of returned data.

A method taking `Pageable` while returning `List<T>` can limit the slice of data fetched at the repository layer, yet it does not produce full Page/Slice metadata for Spring Data REST. To include navigation links and pagination metadata in the API, declare the return type as `Page<T>` or `Slice<T>`.

## 6. Returning Page<T>: a page with total result count

`Page<T>` represents one page of results and adds information about the entire result set:

~~~java
Page<Person> findByStatus(PersonStatus status, Pageable pageable);
~~~

The method must accept `Pageable`. Spring Data uses this information to determine offset, page size, and sort.

Example endpoint call:

~~~http
GET /api/people/search/by-status-page?status=ACTIVE&page=0&size=20&sort=lastName,asc
Accept: application/hal+json
~~~

Common parameters:

| Parameter | Meaning | Default |
| --- | --- | --- |
| `page` | Page number, zero-based | `0` |
| `size` | Requested number of items per page | `20` |
| `sort` | Property and sort direction | No additional sort |

Multiple sort criteria can be passed by repeating the `sort` parameter, for example `sort=lastName,asc&sort=createdAt,desc`. Property names must be properties the repository can sort on; sorting on linkable associations is not supported under current Spring Data REST rules.

A Page HAL response typically has:

- `_embedded`: entities on the current page.
- `_links.self`: URL or URI template of the current page.
- `_links.next`: next page if available.
- `_links.prev`: previous page if available.
- `page.size`: page size.
- `page.totalElements`: total elements across the entire query.
- `page.totalPages`: total number of pages.
- `page.number`: current page index, zero-based.

Abbreviated example:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/search/by-status-page?status=ACTIVE{&page,size,sort}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/api/people/search/by-status-page?status=ACTIVE&page=1&size=20{&sort}",
      "templated": true
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 12,
        "username": "lan"
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
~~~

On the first page there is no `prev` link; on the last page there is no `next` link. Clients should follow these links rather than calculating the next page URL manually.

To determine `totalElements` and `totalPages`, Spring Data typically needs to run an additional count query. Count queries can be expensive for complex queries, large joins, or datastores where counting is costly. If the client does not need the total result count, consider using Slice.

## 7. Returning Slice<T>: a forward-navigable slice of data

`Slice<T>` also requires `Pageable`, but its goal is to indicate whether more data follows:

~~~java
Slice<Person> findByCity(String city, Pageable pageable);
~~~

Key differences:

- Slice knows whether a next portion exists via `hasNext()`.
- Slice does not provide total element count or total page count like Page.
- Spring Data typically reads one extra item beyond the page size to determine whether more data exists.
- No count query is needed solely to compute the total record count.

Example request:

~~~http
GET /api/people/search/by-city-slice?city=HCMC&page=0&size=20
Accept: application/hal+json
~~~

Spring Data REST recognizes Page/Slice results and adds `prev` and `next` navigation links when applicable. Entity content is represented similarly to a collection result. The client does not have total page counts to show something like "page 1 of 12", but it can render a "Next" button when the `next` link is present.

Slice is well suited for:

- Infinite scrolling lists.
- UIs that only need a load-more button.
- Batch processing iterating sequentially slice by slice.
- Large queries where a count query is unnecessary.

With offset pagination, pages at very large offsets can still be slow because the database must process rows before the offset. If the system needs to traverse large datasets continuously, consider keyset/scrolling queries or a cursor-based approach supported by the store.

## 8. Quick comparison of the five return types

| Return type | Expected result count | Not found | Navigation info | Notable cost |
| --- | --- | --- | --- | --- |
| `T` | At most one | `null` | No Page/Slice links | Single query |
| `Optional<T>` | At most one | `Optional.empty()` | No Page/Slice links | Single query |
| `List<T>` / Collection | Unbounded by return type | Empty collection | No Page/Slice metadata | May load all results |
| `Page<T>` | One page | Empty page | Has next/prev and total metadata | May require count query |
| `Slice<T>` | One slice | Empty slice | Has next/prev when applicable | Typically fetches one extra item to determine hasNext |

Choose according to client needs:

- Need a single unique record by key/username/email: `T` or `Optional<T>`.
- Need a small, naturally bounded list: `List<T>`.
- Need total record count and total page count: `Page<T>`.
- Only need to know whether more data is available to load next: `Slice<T>`.

## 9. Search resource and paginated URI templates

Spring Data REST has two levels of links:

1. The search resource lists exported query methods.
2. The query method resource executes a specific query.

For example:

~~~http
GET /api/people/search
Accept: application/hal+json
~~~

The response may contain:

~~~json
{
  "_links": {
    "byUsername": {
      "href": "http://localhost:8080/api/people/search/by-username{?username}",
      "templated": true
    },
    "byStatusPage": {
      "href": "http://localhost:8080/api/people/search/by-status-page{?status,page,size,sort}",
      "templated": true
    }
  }
}
~~~

A query method accepting `Pageable` and returning Page/Slice will have a URI template containing pagination parameters. Clients must expand the template with appropriate parameter values or use a HAL client to navigate.

Query method resources are read-only and support GET. If a repository has no exported query methods, the search resource may be unavailable; Spring Data REST returns 404 for HEAD on the search resource when no query method resources exist.

## 10. Limiting result count and sorting results

Besides Page/Slice, Spring Data supports limiting results with `First`, `Top`, or `Limit`:

~~~java
Person findFirstByOrderByCreatedAtDesc();

List<Person> findTop10ByStatusOrderByCreatedAtDesc(PersonStatus status);

Slice<Person> findTop3ByStatus(PersonStatus status, Pageable pageable);
~~~

`First` and `Top` can be used interchangeably. If no number is specified, the default limit is 1. Limiting can be combined with Pageable; the limit caps the overall total results first, while Pageable can reduce the amount of data fetched in each query.

Do not combine `Pageable` with `Sort` or `Limit` in the same method because Pageable already includes sort and page limits. If only sorting is needed, use `Sort`:

~~~java
List<Person> findByCity(String city, Sort sort);
~~~

Example dynamic sorting via URL:

~~~http
GET /api/people/search/by-city?city=HCMC&sort=lastName,asc&sort=createdAt,desc
~~~

Sort properties must be valid properties of the domain model. Check the exposure configuration and the store module's sorting rules before exposing them to clients.

## 11. Common errors and how to handle them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Single query throws multiple-results error | Method returns T/Optional but condition is not unique | Add a unique constraint, switch to a collection, or use First/Top if business rules allow. |
| Empty Optional handled wrongly by client | Client assumes a fixed status/body | Test actual HTTP responses for your Spring Data REST version and handle empty results explicitly. |
| Huge List causes slowness or high memory usage | Method returns all results | Use Page or Slice and require Pageable. |
| Page query is slow | Count query is expensive | Switch to Slice if total count is unneeded; optimize query/indexes if Page is required. |
| `next` link missing | Currently on last slice/page or method does not return Page/Slice | Check return type, Pageable, and remaining data count. |
| Page does not accept page/size/sort | Method lacks Pageable or URI has no template | Add Pageable and return Page/Slice; inspect the link on the search resource. |
| GET search returns 404 | No query methods are exported or method is hidden | Check repository methods, @RestResource, and export configuration. |
| Single query throws IncorrectResultSizeDataAccessException | Data has multiple matching rows | Fix uniqueness or use a collection type. |

## 12. Testing query method resources

Both HTTP responses, representation contents, and data states should be tested. Example with Page:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonSearchResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void pageQueryExposesPageMetadata() throws Exception {
        mockMvc.perform(get("/api/people/search/by-status-page")
                .param("status", "ACTIVE")
                .param("page", "0")
                .param("size", "10")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.size").value(10))
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Example testing a collection result:

~~~java
mockMvc.perform(get("/api/people/search/by-last-name")
        .param("lastName", "Nguyen")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());
~~~

For Slice, create a fixture with more than one page, then verify the `next` link on the first page and the absence of a next link on the last slice. For Optional, test both found and not-found cases separately; do not rely on assumptions about status codes without verifying the behavior of the version in use.

In addition to MockMvc, include repository integration tests for:

- Single queries with 0, 1, and multiple results.
- Empty collections and populated collections.
- Page on the first page, middle page, and last page.
- Slice with and without a next slice.
- Valid and invalid sort parameters.
- Queries limited with First/Top.

## 13. Performance notes and store support

Common return types are supported by Spring Data, though the exact list depends on the store module. Check the documentation for Spring Data JPA, MongoDB, JDBC, Redis, or your project's actual module.

Some considerations:

- `List<T>` and `Streamable<T>` usually require the entire result set; this can consume significant memory.
- `Stream<T>` can hold datastore resources such as a cursor or ResultSet. The stream must be closed, typically with try-with-resources; not all modules support it.
- `Page<T>` requires the total result count to build total metadata; the count query can be the expensive part.
- `Slice<T>` only needs to determine whether more data follows, making it suitable when total page count is unnecessary.
- Offset paging can be slow at large offsets; consider scrolling/keyset if the store supports it.
- Reactive return types such as `Mono<T>` and `Flux<T>` belong to reactive repositories; do not arbitrarily substitute them for Page/Slice in imperative repositories.

Do not pick a return type purely out of Java preference. Consider data size, UI requirements, datastore capabilities, and query cost.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): search resource, query method resource, GET results, and media types.
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): using Pageable with Page/Slice, prev/next links, and page metadata.
- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): collection return types, Pageable, Page, Slice, limiting, and query performance.
- [Spring Data JPA — Repository query return types](https://docs.spring.io/spring-data/jpa/reference/repositories/query-return-types-reference.html): semantics of T, Optional, Collection, Page, Slice, and supported return types.
