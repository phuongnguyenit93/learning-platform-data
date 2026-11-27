# Distinguishing Repository Testing, REST Export Configuration, and HTTP Contracts in Spring Data REST

Spring Data REST automatically exports Spring Data repositories as REST resources through Spring MVC. Therefore, a passing repository test only proves that the data access layer works; it does not prove that the repository is exported properly, the URL is configured correctly, or the client receives an HTTP response matching the contract.

When designing a test suite, separate three questions:

1. Does the repository read, write, and query data correctly?
2. Does Spring Data REST detect and export the right repositories, paths, query methods, and HTTP methods?
3. Does the client receive the expected status, headers, media type, HAL links, and data over HTTP?

The three groups can share sample data, but each group protects a different boundary.

## 1. Test Type Selection Matrix

| Scope | What needs to be proven | Appropriate testing approach |
|---|---|---|
| Repository | Mapping, CRUD, derived queries, custom queries, paging/sorting, and database behavior | Spring Data test slice, e.g. `@DataJpaTest` |
| REST export configuration | Whether the repository is exported; collection path/rel; base path; search endpoints; method exposure; projections and `RepositoryRestConfigurer` configuration | Start the real application context with `@SpringBootTest`, send requests using `MockMvc` |
| HTTP contract | URLs, HTTP methods, statuses, request/response headers, media types, JSON/HAL body, links, paging, validation, ETag, and security | `MockMvc` for MVC integration testing; `WebTestClient` or an HTTP client against a real server for end-to-end |

Do not use one test type as a substitute for all three. For example, a repository might save data while the endpoint returns 404 because the repository is not exported. Conversely, a GET endpoint might return 200 while a query method still queries the wrong data.

## 2. Repository Testing

### Goals and scope

Repository tests focus on the persistence layer:

- Saving, reading, updating, and deleting entities.
- Derived queries like `findByTitleContainingIgnoreCase`, custom queries, and query parameters.
- Entity relationships, cascades, lazy loading, column mappings, and data constraints.
- Results when records are not found, data is duplicated, or inputs violate constraints.
- Paging and sorting at the repository level when the repository supports the corresponding abstractions.

With Spring Data JPA in Spring Boot, `@DataJpaTest` is the default choice for this group. The test slice scans entities and configures Spring Data JPA repositories; if an embedded database is on the classpath, Boot can configure that database. Tests typically run in a transaction and roll back after each test. `TestEntityManager` is useful when you need to prepare entities directly.

The example below assumes the project already has a `Book` entity and a `BookRepository` repository with the `findByTitleContainingIgnoreCase` method:

```java
@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository books;

    @Test
    void findsBooksByTitleIgnoringCase() {
        books.saveAndFlush(new Book("Spring Data REST"));

        assertThat(books.findByTitleContainingIgnoreCase("rest"))
            .extracting(Book::getTitle)
            .containsExactly("Spring Data REST");
    }
}
```

This test proves that the repository query returns the right data. It does not start the full Spring Data REST exporter and does not prove that the `/books` URL exists.

If you need to verify behavior that depends on the production database such as dialect, constraints, data types, or native queries, run additional tests with the actual database. With Boot, you can use `@AutoConfigureTestDatabase(replace = Replace.NONE)` together with Testcontainers or a configured test database. Embedded databases are suitable for fast tests, but they do not replace real database compatibility testing.

If you use another Spring Data module, choose the corresponding test slice, such as `@DataMongoTest`, `@DataJdbcTest`, or `@DataR2dbcTest`. Do not use `@DataJpaTest` for repositories belonging to other stores.

## 3. Testing Repository Export Configuration as REST Resources

### Configurations to protect

Spring Data REST decides which repositories are exported using `RepositoryDetectionStrategy`. The meaningful strategies are:

- `DEFAULT`: exports public repositories or repositories annotated with `@RepositoryRestResource`, provided `exported` is not `false`.
- `ALL`: exports all Spring Data repositories, regardless of visibility or annotations.
- `VISIBILITY`: exports only public repositories, regardless of annotations.
- `ANNOTATED`: exports only repositories with `@RepositoryRestResource` that do not have `exported = false`.

In addition to the detection strategy, verify the following points:

- Are the path name and collection relation matching the published API?
- Is the base path applied?
- Are internal repositories unintentionally exported?
- Do query methods appear at the search resource?
- Which CRUD methods are allowed to be called over HTTP?
- Are projections, association links, and custom configurations loaded in the application context?

Example of declaring a repository with explicit path and search endpoints:

```java
@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {

    @RestResource(path = "by-title", rel = "by-title")
    List<Book> findByTitleContainingIgnoreCase(@Param("q") String q);
}
```

The search method in the example above is exposed at a path such as `/books/search/by-title?q=...`. The default collection path can also be customized via `@RepositoryRestResource`; do not assume pluralized names if the project defines a custom path.

You can hide an entire repository using `@RepositoryRestResource(exported = false)`. You can hide a single method from the REST exporter using `@RestResource(exported = false)`, for example when the application still needs that method for internal processing. For broader HTTP method rules, use `RepositoryRestConfiguration.getExposureConfiguration()` inside `RepositoryRestConfigurer`.

Example of setting the strategy to export only annotated repositories:

```java
@Configuration
class RestExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setRepositoryDetectionStrategy(
            RepositoryDetectionStrategy.RepositoryDetectionStrategies.ANNOTATED
        );
    }
}
```

### Testing configuration with a real application context

To test the exporter, load the real application configuration. A common approach is `@SpringBootTest` combined with `@AutoConfigureMockMvc`. Example of checking the collection relation at the root resource:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryExposureTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publishesBooksCollection() throws Exception {
        mvc.perform(get("/api").accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.books.href").exists());
    }

    @Test
    void doesNotPublishInternalNotes() throws Exception {
        mvc.perform(get("/api/internal-notes")
                .accept("application/hal+json"))
            .andExpect(status().isNotFound());
    }
}
```

In the example, `/api` is an assumed base path. If the application does not configure a base path, use the root path `/`; if the repository has a different path or relation, update the URL and link name according to the actual configuration. Tests for unexported endpoints should use a known path that is not claimed by another controller.

This is an export configuration test because it verifies the outcome after Spring loads repositories, annotations, and `RepositoryRestConfigurer`. A test that merely instantiates the config object or checks annotations via reflection does not prove that endpoints are actually registered.

## 4. Testing the HTTP Contract

### Contract to verify

Test the response as seen by an external client, rather than only checking that internal methods executed:

- **URLs and links:** collection, item, search, association, self links, and navigation links.
- **HTTP methods:** GET/POST on collections; GET/PUT/PATCH/DELETE on items if permitted by the repository and configuration.
- **Status:** 200 for successful reads; 201 and Location when resource creation succeeds; 404 when the resource does not exist or is not exported; 405 when a method is not supported; validation/security statuses per application configuration.
- **Headers and media types:** Accept, Content-Type, Location, ETag, Cache-Control if present, and relevant security headers.
- **Body:** data fields, data types, nullability, validation errors, and HAL structure.
- **Paging/sorting:** page metadata, next/prev links, and page/size/sort parameters.
- **Conditional updates:** ETag, If-Match, If-None-Match, and 412/304 statuses where applicable.

Spring Data REST typically represents hypermedia using HAL JSON. When checking links, explicitly send Accept as `application/hal+json`, then verify the relations inside `_links`; avoid asserting a large raw JSON string because field ordering or host URLs may vary.

Example of verifying a collection response, media type, and pagination:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BookHttpContractTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void returnsHalCollectionWithPagingMetadata() throws Exception {
        mvc.perform(get("/api/books")
                .param("size", "2")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/hal+json")))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$.page.size").value(2));
    }

    @Test
    void rejectsDeleteOnCollection() throws Exception {
        mvc.perform(delete("/api/books"))
            .andExpect(status().isMethodNotAllowed());
    }
}
```

The `$.page.size` assertion assumes the repository supports paging. If the project changes the base path or collection path, replace the URL according to configuration. By default, collection resources support GET and POST; other methods on collections return 405. Item resources typically support GET, PUT, PATCH, and DELETE, unless repository methods or exposure configuration disable them.

Example of testing resource creation:

```java
@Test
void createsBookAndReturnsLocation() throws Exception {
    mvc.perform(post("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept("application/hal+json")
            .content("""
                {"title":"Spring Data REST"}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"));
}
```

The JSON body must match the writable fields of the actual entity/projection. If the entity has validation or required associations, prepare a valid payload according to the application's model.

### ETag and conditional updates

If an entity has a version field annotated with `@Version`, Spring Data REST can return an ETag corresponding to the resource version. Clients can send that ETag in the `If-Match` header during PUT, PATCH, or DELETE. If the resource has been updated by another client, the old ETag no longer matches and the server returns 412 Precondition Failed.

There should be tests verifying both scenarios: updating with the current ETag succeeds; updating with a stale ETag is rejected. The test must retrieve the ETag from a GET response and preserve the exact resource URI. For GET with `If-None-Match`, the response may be 304 Not Modified when the representation has not changed.

### MockMvc or real server?

- `MockMvc` runs full Spring MVC request processing with mock requests/responses without starting a servlet container. It is the fast choice for most export and HTTP contract tests.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real server on a random port. Combine it with an HTTP client or `WebTestClient.bindToServer()` to verify the end-to-end path.
- `WebTestClient` can also bind to a mock server; with Spring MVC you can use the MockMvc bridge. Choose the binding configuration explicitly so it is clear whether the test runs against a mock or a real server.

MockMvc does not test full server/container behavior, actual context paths, proxies, TLS, or network configurations. Therefore, keep a small number of end-to-end tests for critical flows. If a test uses RANDOM_PORT/DEFINED_PORT, client requests and server processing run on different threads/transactions; test transaction rollback will not automatically roll back operations committed on the server. Use an isolated database or clean up data after the test.

## 5. How Should the Test Suite Be Organized?

A practical structure can include:

| Test group | Relative quantity | Verification examples |
|---|---:|---|
| Repository | Many, fast-running | Derived queries, mappings, constraints, paging, and sorting |
| Export configuration | Few, targeted | Repositories exported/not exported, base path, custom path, search rel, hidden methods |
| HTTP contract with MockMvc | Moderate | GET/POST/PATCH/DELETE, statuses, headers, HAL links, validation, paging |
| End-to-end with real server | Few, focused | Critical create/read/update flows, security filters, context path, and deployment environment |

Keep fixtures small and independent. Each test should create the data it needs and not depend on execution order or leftover data from other tests. Use identifiers returned from POST/GET instead of hard-coding database-generated IDs. For HAL, prefer checking relations and following links; avoid hard-coding hosts, ports, or full absolute hrefs.

For dependencies, use test artifacts managed by the exact Spring Boot version. Boot 3 typically uses `spring-boot-starter-test`; Boot 4 splits test modules by capability, such as `spring-boot-data-jpa-test` and `spring-boot-webmvc-test`. Do not mix imports or versions from different major releases; let the Spring Boot BOM manage compatible versions.

## 6. Troubleshooting

| Symptom | Common cause | How to check |
|---|---|---|
| Repository test passes but GET collection returns 404 | Test only loads the JPA slice; repository is not exported; wrong base path or path | Run `@SpringBootTest` with MockMvc; check detection strategy, visibility, `exported`, `@RepositoryRestResource`, and base path |
| Repository does not appear at HAL root | Detection strategy is ANNOTATED but repository lacks annotation; relation was changed | Check `RepositoryDetectionStrategy`, `collectionResourceRel`, and links in the root response |
| Request returns 405 | Method is not supported or has been hidden | Check if the repository has the corresponding CRUD method, `@RestResource(exported = false)`, and `ExposureConfiguration` |
| Test does not see `_links` | Client is requesting plain JSON or endpoint is not an SDR resource | Send `Accept: application/hal+json`; check Content-Type and endpoint |
| Paging test does not see `page` | Repository/query method does not return a paging-capable type or test calls the wrong endpoint | Check `PagingAndSortingRepository`, `Pageable`, `Page`/`Slice` return type, and the `size` parameter |
| MockMvc passes but calling real server fails | MockMvc does not start a container; differences in context path, filters, proxy, or server config | Add RANDOM_PORT/WebTestClient tests against a real server and check deployment configuration |
| Data from HTTP tests remains in the database | Server handles requests in a different transaction than the test transaction | Use a dedicated test database, delete fixtures, or clean up after each test |
| Update receives 412 | ETag in If-Match is stale or belongs to the wrong resource URI | GET the resource again, obtain the new ETag, and send to the right URI; if testing concurrency, 412 is expected |
| Validator does not run | Bean name is not tied to an event or validator is not registered | Use an event prefix like `beforeCreateBookValidator`, or register via `configureValidatingRepositoryEventListener` |
| Query works on H2 but fails on production database | Differences in dialect, constraints, collation, or native SQL | Run additional tests with a real database/Testcontainers and configure `replace = NONE` |

## 7. Pre-Completion Checklist

- [ ] Repository tests cover important queries and mappings.
- [ ] Export tests prove intended repositories are present and internal repositories are not exposed.
- [ ] Tests verify base path, collection path/rel, search endpoints, and method exposure.
- [ ] HTTP tests verify status, headers, Content-Type/Accept, and body.
- [ ] HAL tests verify required self/association/search/paging links.
- [ ] Validation, security, and input errors have tests matching the published contract.
- [ ] If using ETag, both fresh and stale ETags are tested.
- [ ] At least some end-to-end tests exist for critical flows if the system needs real container/network verification.
- [ ] Tests are independent, prepare their own data, and clean up properly.

## 8. Official Documentation

- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/) — overview of exporter, resources, representations, validation, security, and customization.
- [Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html) — collection/item resources and supported HTTP methods.
- [Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html) — detection strategies and exposure configuration.
- [Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html) — page/size/sort parameters and navigation links.
- [Validation](https://docs.spring.io/spring-data/rest/reference/validation.html) — registering validators by event.
- [ETags and other conditionals](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html) — ETag, If-Match, If-None-Match, and conditional statuses.
- [Testing Spring Boot applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@SpringBootTest`, web environment, and test slices.
- [Spring Boot test modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html) — feature-based test modules.
- [MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) — testing Spring MVC with mock requests/responses.
- [MockMvc vs end-to-end tests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/vs-end-to-end-integration-tests.html) — limitations and differences between mock MVC and a real server.
- [WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — testing with a mock server or live server.
- [Spring REST Docs: Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html) — extracting and verifying HAL links in API documentation.
