# Testing Search, Parameter Conversion, Pagination, and Sorting in Spring Data REST

## Goal

After this lesson, you will be able to:

- Discover search resources and invoke query methods exported by Spring Data REST.
- Test converting query parameters from URL strings into Java types.
- Test pagination using page, size, and Page metadata.
- Test single-property and multi-property sorting using sort.
- Write integration tests with MockMvc to verify the actual HTTP contract of repository resources.
- Distinguish query, conversion, paging, and sorting errors to pinpoint root causes.

## 1. Testing Scope

Spring Data REST publishes repositories as HTTP resources. Alongside collection and item resources, repositories with exported query methods provide search resources:

- Collection: GET /people
- Search index: GET /people/search
- Query method: GET /people/search/by-status

The search index returns links to query method resources. Query method resources execute the corresponding repository method and return results. Search and query method resources are read-only resources, so testing primarily uses GET.

A query method can accept standard parameters such as String, Long, Boolean, enum, or LocalDate. Spring converts string values in the query string into the appropriate Java types before calling the repository method. If the method accepts Pageable or Sort, Spring Data REST also converts the page, size, and sort query parameters into pagination/sorting directives.

Test each layer of behavior separately:
1. Does the search index publish the right link?
2. Are query parameters bound and converted accurately?
3. Does the repository return the right result set?
4. Are page metadata and navigation links accurate?
5. Does the result order match the sort directives?

## 2. Preparing a Repository with Query Methods

Suppose the application manages Orders. The entity has state and priority; the repository needs to support querying by state, pagination, and sorting.

    public enum OrderState {
        OPEN,
        IN_PROGRESS,
        CLOSED
    }

Illustrative repository:

    import org.springframework.data.domain.Page;
    import org.springframework.data.domain.Pageable;
    import org.springframework.data.jpa.repository.JpaRepository;
    import org.springframework.data.repository.query.Param;
    import org.springframework.data.rest.core.annotation.RepositoryRestResource;
    import org.springframework.data.rest.core.annotation.RestResource;

    @RepositoryRestResource(
        path = "orders",
        collectionResourceRel = "orders"
    )
    public interface OrderRepository
            extends JpaRepository<Order, Long> {

        @RestResource(path = "by-state", rel = "by-state")
        Page<Order> findByState(
            @Param("state") OrderState state,
            Pageable pageable
        );
    }

With this configuration, Spring Data REST can expose the query resource at:

    GET /orders/search/by-state?state=IN_PROGRESS

@RepositoryRestResource sets the collection path and relation. @RestResource sets the path/relation for the query method. @Param defines the query parameter name that clients must send.

JpaRepository provides CRUD, paging, and sorting operations. If you use a different repository interface, ensure it includes the necessary methods. For query methods requiring pagination, a Pageable parameter must be present and the return type should be Page or Slice so the framework can return the corresponding pagination metadata.

## 3. Verifying the Search Resource

Before calling a specific query, check whether the search index publishes the query method.

Example:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/orders/search

The HAL response will contain `_links`. Locate the `by-state` relation and inspect its href or URI template. If the query method accepts parameters, the link may represent those parameters as template variables.

With MockMvc:

    @Test
    void searchIndexExposesByStateQuery() throws Exception {
        mockMvc.perform(get("/orders/search")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.by-state").exists());
    }

If the link does not appear, check:
- Is the repository exported by Spring Data REST?
- Is the query method recognized by Spring Data?
- Is `@RestResource(exported = false)` hiding the method?
- Is the repository detection strategy or `@RepositoryRestResource` restricting exposure?
- Do path and rel match the actual configuration?

Having a link in the search index proves the method is published. It does not prove the query executes properly; you still need to call the query method resource and inspect returned data.

## 4. Testing Query Parameter Conversion

Query parameters in URLs are always passed as text. Spring MVC and Spring Data REST use ConversionService to convert text into the Java types of repository parameters.

Common types:

| Query parameter | Java type | Example |
|---|---|---|
| page | int | page=0 |
| size | int | size=10 |
| enabled | boolean | enabled=true |
| id | Long | id=42 |
| createdAfter | LocalDate | createdAfter=2026-01-01 |
| state | enum | state=IN_PROGRESS |

Example query method:

    Page<Order> findByState(
        @Param("state") OrderState state,
        Pageable pageable
    );

Request:

    GET /orders/search/by-state?state=IN_PROGRESS

Spring converts the string `IN_PROGRESS` into `OrderState.IN_PROGRESS` before executing the method.

### Registering a custom converter

When the URL contract uses client-friendly values that do not match enum constant names, you can register a Converter. For instance, clients want to send `state=in-progress`, while the enum has constant `IN_PROGRESS`.

    import java.util.Locale;

    import org.springframework.core.convert.converter.Converter;

    public final class StringToOrderStateConverter
            implements Converter<String, OrderState> {

        @Override
        public OrderState convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException(
                    "state must not be blank");
            }

            String normalized = source.trim()
                .replace('-', '_')
                .toUpperCase(Locale.ROOT);

            return OrderState.valueOf(normalized);
        }
    }

Registering the converter with Spring Data REST:

    import org.springframework.context.annotation.Configuration;
    import org.springframework.core.convert.support.ConfigurableConversionService;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

    @Configuration
    public class RepositoryRestConfiguration
            implements RepositoryRestConfigurer {

        @Override
        public void configureConversionService(
                ConfigurableConversionService conversionService) {
            conversionService.addConverter(
                new StringToOrderStateConverter());
        }
    }

Then the following request can be converted to `OrderState.IN_PROGRESS`:

    GET /orders/search/by-state?state=in-progress

Only add converters to the ConversionService configured by Spring Data REST. Do not create a separate ConversionService expecting the framework to pick it up automatically. Converters should reject invalid values with clear messages; do not silently fall back to a default enum because that can cause queries to return wrong results.

### Testing conversion over HTTP

A unit test for the converter only proves the conversion logic of that class. An integration test through the endpoint proves Spring Data REST actually registered and used that converter.

    @Test
    void convertsFriendlyStateParameter() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.totalElements").value(3));
    }

Assume the test data contains exactly three Orders with state `IN_PROGRESS`. If the converter is not registered, the query string may fail to convert to the enum and the request will fail instead of returning three results.

Also test invalid values:

    @Test
    void rejectsUnknownStateParameter() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "unknown-state")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isBadRequest());
    }

The exact status may be affected by custom exception handling depending on application configuration. What needs to be verified is that invalid values are rejected and not coerced into another valid state.

## 5. Testing Pagination

Spring Data REST accepts standard query parameters:

- page: 0-based page index; default is 0.
- size: maximum number of items per page; default is typically 20.
- sort: sorting directive.

Example:

    GET /orders/search/by-state?state=in-progress&page=1&size=2

With `page=1` and `size=2`, the server returns the second page, containing at most two items. If the repository query returns `Page`, the HAL response can contain metadata:

    {
      "page": {
        "size": 2,
        "totalElements": 5,
        "totalPages": 3,
        "number": 1
      }
    }

Explanation:
- size is the requested page size.
- totalElements is the total number of items matching the query.
- totalPages is the total number of pages.
- number is the current 0-based page number.

Spring Data REST also provides `first`, `prev`, `self`, and `next` links appropriate to the current page position. Clients should follow these HAL links instead of assembling next-page URLs manually.

### Testing page metadata

Prepare five Orders with state `IN_PROGRESS`, then invoke:

    GET /orders/search/by-state?state=in-progress&page=1&size=2

Test:

    @Test
    void returnsRequestedPageAndMetadata() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .param("page", "1")
                .param("size", "2")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.number").value(1))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.totalElements").value(5))
            .andExpect(jsonPath("$.page.totalPages").value(3))
            .andExpect(jsonPath("$._links.self").exists());
    }

Expected values must match fixture data. If data can be altered by other tests, prepare and clean up data per test for deterministic results.

### Page vs. Slice differences

- Page provides total element counts and total page counts; usually requires an extra count query depending on repository/datastore.
- Slice indicates whether a next page exists without computing full element/page totals.
- List does not carry pagination metadata like Page. If a query method only returns List, having Pageable in the method signature does not mean the response will contain full Page metadata.

Choose the return type based on client needs and query cost. If clients need total page counts to render navigation, Page is more suitable. If knowing whether more data exists is enough, Slice can save count query overhead.

## 6. Testing Sorting

The `sort` parameter uses property name and sort direction:

    sort=priority,desc

- priority is the domain model property name.
- desc is descending.
- asc is ascending.

Example:

    GET /orders/search/by-state?state=in-progress&sort=priority,desc

To sort by multiple criteria, pass multiple `sort` parameters:

    GET /orders/search/by-state?state=in-progress&sort=priority,desc&sort=id,asc

In this example, descending priority is the primary criterion. If multiple Orders share the same priority, ascending id breaks ties. Secondary sorting keeps results deterministic when duplicate values exist.

Property paths can be used for nested properties, depending on datastore and mapping capabilities. Do not assume you can sort by an association represented only as a resource link. Verify actual property paths and repository sorting support.

### Testing result ordering

Suppose five IN_PROGRESS Orders have priorities 1, 2, 3, 4, 5 respectively. Request descending priority and ascending id:

    GET /orders/search/by-state?state=in-progress&sort=priority,desc&sort=id,asc

A test can check the first element:

    @Test
    void sortsByPriorityDescendingThenIdAscending() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .param("sort", "priority,desc")
                .param("sort", "id,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.orders[0].priority")
                .value(5));
    }

To test the secondary criterion, create at least two records with the same priority and confirm their ids are in ascending order. Checking only the first element is not enough to prove full ordering when ties exist.

## 7. Using MockMvc for Integration Testing

To verify that search resources, ConversionService, Pageable, and Sort work together properly, test the real Spring Data REST application inside a Spring test context.

Example setup:

    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.test.web.servlet.MockMvc;

    @SpringBootTest
    @AutoConfigureMockMvc
    class OrderRepositoryRestTests {

        @Autowired
        MockMvc mockMvc;

        @Autowired
        OrderRepository repository;

        // Prepare deterministic repository data before each test.
    }

MockMvc executes the Spring MVC processing flow without opening a real HTTP port. @SpringBootTest loads the application context so Spring Data REST auto-configuration, repositories, and RepositoryRestConfigurer are applied. @AutoConfigureMockMvc supplies MockMvc for sending requests.

Do not default to `@WebMvcTest` for this kind of test. It is a slice test focused on Spring MVC controllers; it may not load all repositories and Spring Data REST auto-configuration needed by endpoints. If you deliberately use a slice test, you must import the right configurations and components; for repository REST contracts, an integration test is usually easier to reason about.

### Preparing test data

Fixture concept example:

    @BeforeEach
    void prepareData() {
        repository.deleteAll();

        repository.saveAll(List.of(
            new Order(OrderState.IN_PROGRESS, 1),
            new Order(OrderState.IN_PROGRESS, 2),
            new Order(OrderState.IN_PROGRESS, 3),
            new Order(OrderState.IN_PROGRESS, 4),
            new Order(OrderState.IN_PROGRESS, 5),
            new Order(OrderState.CLOSED, 6)
        ));
    }

Constructors in the example should be adjusted to match the actual entity. What matters is that test data deterministically sets record counts per state and priority ordering.

If tests use a real database or run in parallel, isolate data. Do not rely on fixed IDs if the ID generation strategy does not guarantee identical values across runs.

## 8. Combining Behaviors in One Test

A single request can test parameter conversion, pagination, and sorting together:

    @Test
    void searchesConvertsPaginatesAndSorts() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .param("page", "1")
                .param("size", "2")
                .param("sort", "priority,desc")
                .param("sort", "id,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.number").value(1))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.totalElements").value(5))
            .andExpect(jsonPath("$.page.totalPages").value(3))
            .andExpect(jsonPath("$._embedded.orders").isArray())
            .andExpect(jsonPath("$._embedded.orders.length()").value(2));
    }

This combined test is helpful to verify the full flow. However, when it fails, keep separate small tests for search links, conversion, paging, and sorting. That way you immediately know which layer of behavior broke.

## 9. Verifying HAL Links and Media Types

Spring Data REST typically returns HAL JSON when clients request:

    Accept: application/hal+json

For paginated collections/query results, the response can include:
- _embedded: elements of the current page.
- _links.self: URI of the current page.
- _links.next: next page if more data exists.
- _links.prev: previous page if past the first page.
- _links.first and _links.last: first/last links when determinable.
- page: Page metadata.

Avoid rigidly asserting the entire JSON response when property ordering or links can change. Assert key contract elements: status, content type, page metadata, relations, and a few representative values.

Clients should prefer following `next`/`prev` links returned by the server. This makes clients less coupled to how the server constructs URIs and configured query parameter names.

## 10. Common Pitfalls

| Symptom | Possible cause | How to resolve |
|---|---|---|
| /search lacks query link | Query method is not exported or hidden | Check repository, @RestResource, and exported |
| Query returns 400 | Query parameter cannot be converted or invalid value | Check @Param, Java type, and Converter |
| Query returns empty result | Conversion succeeded but value does not match data | Check enum mapping, fixture, and query condition |
| page is always 0 | Test did not send page or parameter name changed in RepositoryRestConfiguration | Check query string and parameter name configuration |
| size has no effect | Query method does not accept Pageable or repository method does not support paging | Use Pageable and appropriate Page/Slice return type |
| No page metadata | Query method returns List or response is not a paged result | Use Page or Slice and inspect response |
| Sort does not change order | Wrong property name, wrong direction, or unsupported sort property | Use domain model property name and ensure data has distinct ordering values |
| Multi-criteria sort is unstable | Missing tie-breaker criterion when primary values are duplicated | Add sort by ID or unique property |
| Test endpoint returns 404 | Wrong base path or repository not exported | Check application properties, repository detection, and path |
| MockMvc test does not see Spring Data REST | Test slice does not load repository REST configuration | Use @SpringBootTest and @AutoConfigureMockMvc or explicitly import required configurations |

## 11. Testing Checklist

- [ ] Search index returns links to exported query methods.
- [ ] Query methods use accurate path, rel, and @Param.
- [ ] String parameters are converted to desired Java types.
- [ ] Custom converters are registered in Spring Data REST's ConversionService.
- [ ] Invalid query parameter values are explicitly rejected.
- [ ] page starts at 0 and size limits returned item counts.
- [ ] Page metadata accurately reflects fixtures.
- [ ] next/prev links appear appropriately for page position.
- [ ] asc/desc sorting returns accurate ordering.
- [ ] Multiple sort directives are applied in priority order.
- [ ] Tests verify HAL responses without depending on insignificant JSON ordering.
- [ ] Test data is prepared and isolated for repeatable, stable results.

## Conclusion

Testing Spring Data REST requires exercising real HTTP resources. Confirm that the search index publishes query methods, query parameters convert to the right Java types, Pageable produces accurate page metadata and navigation links, and Sort yields ordering matching the contract. MockMvc combined with @SpringBootTest and @AutoConfigureMockMvc provides a practical way to test the full flow without running a standalone HTTP server.

Keep small focused tests per behavior alongside a combined integration test. When a test fails, you can distinguish export, conversion, query, paging, or sorting defects instead of staring at an unexpected JSON response.

## References

- Spring Data REST — Repository resources and search/query method resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST — Paging and Sorting: https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html
- Spring Data REST — RepositoryRestConfigurer API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html
- Spring Boot 3.3 — Testing Spring Boot Applications and MockMvc: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — MockMvc: https://docs.spring.io/spring/reference/testing/mockmvc.html
