# Collection GET and the findAll Method Used

## Objectives

In Spring Data REST, a collection resource is the endpoint representing the set of entities managed by a repository. Send an HTTP GET to the collection resource to read the list of entities. Spring Data REST performs this operation using the \`findAll(…)\` method provided by the repository.

For example, a repository managing Customer can produce a collection resource:

    GET /customers

If the repository supports pagination, the response contains only one page of results and includes navigation links along with page metadata. If the repository only has a method that reads all entities, the response may contain all entities returned by that method.

When analyzing a GET collection request, you need to determine:

1. Which collection URL is exported?
2. Which \`findAll\` overloads does the repository have?
3. Which overload does the framework select to execute?
4. Are the \`page\`, \`size\`, and \`sort\` parameters supported by the repository?
5. What data, links, and page metadata does the response contain?

## 1. Collection resource and HTTP GET

Spring Data REST creates a collection resource from an exported repository. By default, the path is based on the domain class name after converting it to lowercase and pluralizing it. For example, the domain type Customer is typically exposed at \`/customers\`.

You can customize the path and relation using \`@RepositoryRestResource\`:

    @RepositoryRestResource(
        path = "customers",
        collectionResourceRel = "customers"
    )
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Where:

- \`path\` specifies the collection URL.
- \`collectionResourceRel\` specifies the relation name in HAL \`_links\`.
- Item resources reside under the collection, for example \`/customers/{id}\`.

Path and relation are two separate concepts. Clients should start from the root resource and follow HAL links to obtain the actual URL, rather than inferring the path from the interface name.

### 1.1. Reading a collection with GET

Request:

    curl -H "Accept: application/hal+json" \
      "http://localhost:8080/customers"

GET returns the entities provided by the repository via the \`findAll(…)\` method. If the repository supports pagination, Spring Data REST adds pagination links when needed and metadata describing the current page.

A collection resource supports:

| HTTP method | Meaning |
|---|---|
| GET | Read entities in the collection |
| HEAD | Check whether the collection resource is available |
| POST | Create a new entity from the request body |

Other HTTP methods on a collection typically return \`405 Method Not Allowed\`.

Collection GET differs from item GET:

- \`GET /customers\` reads a collection, using \`findAll(…)\`.
- \`GET /customers/1001\` reads a single entity by ID, using \`findById(…)\`.

Collection GET also differs from a query method resource, such as \`GET /customers/search/by-status?status=ACTIVE\`, which invokes a dedicated query method.

### 1.2. Media types and responses

Collection GET supports common media types:

- \`application/hal+json\`: HAL JSON representation, containing hypermedia links.
- \`application/json\`: JSON representation.

With HAL, a paginated response typically contains these sections:

- \`_links\`: \`self\`, \`next\`, \`prev\` links when applicable, and related links.
- \`_embedded\`: list of entities on the current page.
- \`page\`: metadata about page size, total number of entities, total pages, and current page index.

Abbreviated example:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers?page=0&size=2"
        },
        "next": {
          "href": "http://localhost:8080/customers?page=1&size=2"
        }
      },
      "_embedded": {
        "customers": [
          { "id": 1001, "name": "An" },
          { "id": 1002, "name": "Binh" }
        ]
      },
      "page": {
        "size": 2,
        "totalElements": 5,
        "totalPages": 3,
        "number": 0
      }
    }

This is an illustrative example. Relation names, URLs, properties, and entity contents depend on the domain type and application configuration. For the first page, there will be no \`prev\` link; for the last page, there will be no \`next\` link.

## 2. Selection order for findAll methods

Spring Data REST selects the collection read method in the following descending priority order:

1. \`findAll(Pageable)\`
2. \`findAll(Sort)\`
3. \`findAll()\`

The framework uses the first method that is available and allowed to be exported. This order is important when a repository provides multiple overloads.

### 2.1. findAll(Pageable)

Common signature:

    Page<Customer> findAll(Pageable pageable);

This is the highest-priority choice. \`Pageable\` contains:

- The page number to read.
- The page size.
- Sorting information.

Spring Data REST builds a \`Pageable\` from the request query parameters and passes it to the repository. The \`Page<Customer>\` result provides the page content along with total entity count and total page count.

Example request:

    GET /customers?page=1&size=10&sort=name,asc

With \`page=1\`, \`size=10\`, the repository is asked to read the second page containing up to 10 entities, sorted by \`name\` ascending.

This is usually the best option for collections that can grow large, because the database only needs to return the requested page range instead of loading the entire collection into the application.

### 2.2. findAll(Sort)

Common signature:

    Iterable<Customer> findAll(Sort sort);

This is the second choice when the repository does not have a \`findAll(Pageable)\` overload but has \`findAll(Sort)\`.

This method supports sorting results. It does not accept a page number or page size, so it cannot limit results to a single page on its own like \`findAll(Pageable)\`.

When RepositoryInvoker is called with a \`Pageable\`, if no method accepts \`Pageable\`, it can extract the \`Sort\` part from \`Pageable\` and invoke \`findAll(Sort)\`. That preserves sorting information, but the \`Sort\` method cannot perform page-level limiting.

### 2.3. findAll()

Common signature in CrudRepository:

    Iterable<Customer> findAll();

This is the last choice when the repository has no method accepting \`Pageable\` or \`Sort\`.

This method returns all entities provided by the repository. It does not accept pagination or sorting information, so it cannot perform page/size/sort at the repository method level.

For large collections, loading all data can consume significant memory, time, and database resources. If you need a scalable collection API, add \`Pageable\` or \`Sort\` support appropriate to your requirements.

### 2.4. Comparison table

| Method | Priority | Pagination | Sorting | Returned data |
|---|---:|---|---|---|
| \`findAll(Pageable)\` | 1 | Yes | Yes, via Pageable | A Page |
| \`findAll(Sort)\` | 2 | No | Yes | Sorted entities |
| \`findAll()\` | 3 | No | No | All entities |

This order is Spring Data REST's method selection rule. It does not mean the framework always calls all three methods. For a given request, the highest-priority available method is chosen.

## 3. Declaring a paginated repository

In modern Spring Data, \`PagingAndSortingRepository\` provides pagination and sorting methods. Since Spring Data 3.x, this interface no longer extends \`CrudRepository\`; if a repository needs both CRUD operations and pagination, extend both interfaces:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {
    }

Then the repository has the CRUD methods as well as:

    Page<Customer> findAll(Pageable pageable);
    Iterable<Customer> findAll(Sort sort);

If you want CRUD methods to return \`List\` where appropriate, Spring Data also provides \`ListCrudRepository\`. The exact return types depend on the interfaces the project chooses and the Spring Data version in use.

### 3.1. Illustrative domain type

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
        private String status;

        // constructors, getters and setters
    }

Repository:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {
    }

Spring Data REST can export the collection at \`/customers\`. Collection GET uses \`findAll(Pageable)\` because this method has the highest priority and the repository provides it.

## 4. Query parameters for collection GET

If the repository supports pagination, Spring Data REST accepts the following parameters.

### 4.1. page

\`page\` is the zero-based page index. The default is page 0.

    GET /customers?page=0
    GET /customers?page=1

Page 0 is the first page; page 1 is the second page.

### 4.2. size

\`size\` is the maximum number of entities requested per page. The Spring Data REST default is 20.

    GET /customers?size=5

Applications can configure the default page size and maximum page size limit using \`RepositoryRestConfiguration\`. Therefore, the client-requested value may be capped by server configuration.

Configuration example:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        }
    }

Clients should not be allowed to request an excessively large page size if the endpoint accesses large amounts of data or has expensive queries.

### 4.3. sort

\`sort\` specifies the property to sort by and the sort direction:

    GET /customers?sort=name,asc
    GET /customers?sort=name,desc

- \`asc\`: ascending.
- \`desc\`: descending.

You can sort by multiple properties by passing multiple \`sort\` parameters:

    GET /customers?sort=status,asc&sort=name,desc

You can use nested properties via property paths if the store and mapping support them, for example:

    GET /customers?sort=address.city,asc

Sorting by an association that links to a top-level resource is not supported in the same way as regular property sorting. Properties passed to sort must be valid for the domain model and the store's querying capabilities.

### 4.4. Combining pagination and sorting

Full example:

    curl -H "Accept: application/hal+json" \
      "http://localhost:8080/customers?page=0&size=5&sort=status,asc&sort=name,desc"

This request asks for the first page, at most five entities, sorted by status ascending and then name descending.

When reading \`self\`, \`next\`, or \`prev\` links in the response, use the server-provided links to continue navigating. You do not need to manually rebuild URLs if the response already provides appropriate links.

## 5. Paginated responses and query cost

### 5.1. Page metadata

A \`Page\` typically reports:

- \`size\`: maximum number of entities in a page.
- \`number\`: current page index.
- \`totalElements\`: total number of matching entities.
- \`totalPages\`: total number of pages.

To compute the total number of entities and pages, the implementation may need to execute an additional count query. For large tables or complex queries, the count query can be expensive.

If the application only needs to know whether a next page exists without needing the total number of pages, a Spring Data query method can use \`Slice\`. However, standard collection GET uses the repository's \`findAll(Pageable)\` mechanism; actual result types and metadata depend on the repository contract and Spring Data version.

### 5.2. Why avoid loading the entire collection?

If \`findAll()\` is used on a large table, the repository may have to read every entity before returning the response. This can cause:

- Increased application heap memory usage.
- Increased response times.
- Increased database and network load.
- Large JSON responses that are hard for clients to process.
- Difficulty controlling performance as entity counts grow.

For collections whose data grows over time, design the repository with \`Pageable\` support, set reasonable page size limits, and use stable sorting.

### 5.3. Stable sorting during pagination

When sorting by a non-unique property, multiple entities may share the same value. If data changes between requests, result ordering may shift and clients may see duplicate or skipped records when stepping through pages.

You can append a unique property as the final tie-breaker criterion, such as ID:

    GET /customers?sort=status,asc&sort=id,asc&page=0&size=20

Stable sorting makes pagination order more predictable. It does not replace snapshot or cursor pagination when the system requires strong consistency under continuous write load.

## 6. Controlling findAll export

Repository methods can be hidden from the REST API using \`@RestResource(exported = false)\`.

For example, hiding the paginated method:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {

        @Override
        @RestResource(exported = false)
        Page<Customer> findAll(Pageable pageable);
    }

If all supported \`findAll(…)\` methods are hidden or absent, collection GET may return:

    405 Method Not Allowed

This indicates that the collection resource has no exported collection read method. Check:

- Does the repository extend an interface that provides \`findAll\`?
- Which methods are present: \`findAll(Pageable)\`, \`findAll(Sort)\`, \`findAll()\`?
- Is the method annotated with \`@RestResource(exported = false)\`?
- Does any application exposure configuration alter exportability?

Hiding a \`findAll\` method does not remove the method from the Java interface or the database. It only changes the API exposed by Spring Data REST.

## 7. Verifying which method is actually called

To confirm which overload a collection GET is using, compare the repository contract with the HTTP result.

### Step 1 — Inspect the repository interface

Look for the signatures:

    Page<T> findAll(Pageable pageable);
    Iterable<T> findAll(Sort sort);
    Iterable<T> findAll();

Note which methods are inherited from which interfaces and which methods have been overridden.

### Step 2 — Send a request with page, size, and sort

Example:

    GET /customers?page=1&size=3&sort=name,asc

If the repository has \`findAll(Pageable)\`, this is the prioritized method. The paginated response will show page content, navigation links, and page metadata.

### Step 3 — Cross-check SQL or repository logs

If using Spring Data JPA, enable appropriate logging in the development environment to observe SQL statements. A query with result limiting and offset usually indicates the repository is executing pagination at the database level.

With \`Page\`, an additional count query may appear to compute the total entity count. Do not conclude from a single SQL query alone; cross-check the method signature, request parameters, and response together.

### Step 4 — Check fallback cases

If \`findAll(Pageable)\` is absent, check whether the repository has \`findAll(Sort)\` or only \`findAll()\`.

- Has \`findAll(Sort)\`: the sort method is used if the Pageable overload does not exist.
- Only has \`findAll()\`: the no-argument method is used.
- No read method exported: collection GET may return 405.

### Step 5 — Inspect HAL links

Read \`_links.self\`, \`_links.next\`, and \`_links.prev\` to verify the pagination URLs exposed by the server. If the collection has query methods, the response may also contain a \`search\` link; that is a separate resource for query methods.

## 8. Common errors

| Symptom | Causes to check |
|---|---|
| Collection GET returns 405 | No suitable \`findAll(…)\` exists or the methods have been hidden |
| Request includes page but returns many entities | Repository lacks \`findAll(Pageable)\` and falls back to non-paginated read |
| Sort parameter has no effect | Repository lacks a Sort-supporting overload or sort property is invalid |
| First page has no prev | Normal behavior for the first page |
| Last page has no next | Normal behavior for the last page |
| Large page counts or slow queries | Count query has high cost |
| Duplicate or missing items across pages | Unstable sort or data modified between requests |
| Collection URL differs from expected | Check domain type, \`@RepositoryRestResource(path = "...")\`, and base path |
| Empty collection | There may be no matching entities; check actual data and repository |

## 9. Checklist

1. Find the collection link in the root HAL resource.
2. Identify the repository's domain type and collection path.
3. Check whether the repository has \`findAll(Pageable)\`, \`findAll(Sort)\`, and/or \`findAll()\`.
4. Apply the priority order: Pageable, then Sort, and finally the no-argument method.
5. Check whether the method is exported or hidden via \`@RestResource(exported = false)\`.
6. Send GET with \`page\`, \`size\`, and \`sort\` if supported by the repository.
7. Read \`_embedded\`, \`_links\`, and \`page\` in the response.
8. Cross-check SQL/logs to confirm pagination and count queries.
9. Verify stable sorting if the client traverses multiple pages.
10. If GET returns 405, verify which findAll methods remain exported.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Core — RepositoryInvoker API](https://docs.spring.io/spring-data/rest/reference/data-commons/api/java/org/springframework/data/repository/support/RepositoryInvoker.html)
- [Spring Data Core — PagingAndSortingRepository API](https://docs.spring.io/spring-data/rest/reference/data-commons/api/java/org/springframework/data/repository/PagingAndSortingRepository.html)
- [Spring Data Commons — Query methods and Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
