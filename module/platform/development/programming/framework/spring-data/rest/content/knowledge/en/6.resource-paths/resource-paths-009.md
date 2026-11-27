# Avoiding Path Collisions Between Repositories and Custom Controllers

## Objectives

When Spring Data REST exports a repository, it automatically creates endpoints for collections, items, search, and associations. If an application also declares a custom Controller with the same path, requests may be handled by Spring Data REST's handler mapping instead of the Controller the developer intended.

To prevent routing errors, clearly define which URI space belongs to repositories and which belongs to custom APIs. When you truly want to add or override an operation within a repository's URI space, use the appropriate Spring Data REST Controller type.

## 1. Exported Repositories Create Their Own URI Space

For example:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

With default configuration, the repository can provide endpoints such as:

| URI | Meaning |
|---|---|
| `/people` | Collection resource |
| `/people/{id}` | Single item by ID |
| `/people/search` | Entry point for exported query methods |
| `/people/search/findByLastName?lastName=Nguyen` | Search by last name |
| `/people/{id}/orders` | Association resource if the domain model has an exported relationship |

If `spring.data.rest.base-path=/api` is configured, these URIs are placed under the base path, e.g., `/api/people` and `/api/people/42`.

The collection path name can be changed with `@RepositoryRestResource(path = "...")`. Search resource names can be customized with `@RestResource(path = "...")` on query methods. Therefore, you must check the actual paths exported by repositories before defining mappings for other Controllers.

## 2. Why Can Two Controllers Compete for the Same Request?

Spring MVC uses `HandlerMapping` implementations to find a handler for each request. Spring Data REST registers `RepositoryRestHandlerMapping` for Controllers and endpoints within the REST repository scope.

This handler mapping inspects the URL path and exported repository names. If the path belongs to an exported repository, Spring Data REST claims the request. If no matching repository exists, the handler mapping returns `null` so other `HandlerMapping` instances can continue looking for a handler.

Documentation on integrating Spring Data REST into a Spring MVC application notes that `RepositoryRestHandlerMapping` is configured with order `Ordered.LOWEST_PRECEDENCE - 100` and is typically consulted before application mappings. For example, when a repository is exported under the name `person`, requests starting with `/person` belong to Spring Data REST's space and a regular application MVC Controller will not receive those requests.

Confusing example:

~~~java
@RestController
@RequestMapping("/people")
class PersonController {

    @GetMapping("/{id}")
    PersonView getPerson(@PathVariable Long id) {
        // custom response
    }
}
~~~

If a repository is also exported under `/people`, this Controller's `GET /people/{id}` mapping collides with the repository's URI space. Do not assume Spring will always pick the custom Controller method or always report an ambiguous mapping error at startup. The outcome depends on Controller type, registered `HandlerMapping` beans, mapping order, and application version/configuration.

Within a single `HandlerMapping`, two identical request mappings may trigger an ambiguous mapping error during registration. However, when handlers reside in different `HandlerMapping` instances, duplicate checking does not necessarily happen in the same registry. As a result, the application may still start while requests are routed to a different handler than intended.

## 3. Plan Namespaces Before Writing Controllers

The easiest approach to manage is dedicating separate root paths to each API group:

| URI Space | Owner | Example |
|---|---|---|
| `/api/people/**` | `PersonRepository` repository | `GET /api/people/42` |
| `/api/orders/**` | `OrderRepository` repository | `GET /api/orders/15` |
| `/api/reports/**` | Custom Controller | `GET /api/reports/daily` |
| `/api/admin/**` | Custom Controller | `POST /api/admin/reindex` |

For example, if `people` and `orders` are repository paths, do not place regular MVC Controllers at `/api/people/**` or `/api/orders/**`. Place independent features at `/api/reports/**` or a separate namespace suited to your application.

Some concrete guidelines:

- Use stable, meaningful repository collection names and avoid colliding with Controller root paths.
- Reserve `/search/**` paths and association paths under a repository for features belonging to that resource.
- Do not create a catch-all Controller with `@RequestMapping("/api")` and redeclare sub-paths already owned by repositories.
- If changing `@RepositoryRestResource(path = "...")`, check existing clients, HAL links, API documentation, and Controllers.
- Do not rely on two paths having slightly different names. Clearly identify the first segment after the base path and all exported sub-paths.

## 4. Choosing the Right Annotation for Custom Controllers

Spring Data REST provides different annotations depending on your goal.

### 4.1. @RepositoryRestController: Operations Inside a Repository's URI Space

Use `@RepositoryRestController` when you want to write a handler for a specific resource, use Spring Data REST's REST configuration, and place the mapping within the URI space managed by a repository.

Example adding a custom search operation for people:

~~~java
@RepositoryRestController
class PersonSearchController {

    private final PersonRepository repository;

    PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/search/active")
    ResponseEntity<?> findActive() {
        var people = repository.findByActiveTrue();

        var result = people.stream()
            .map(EntityModel::of)
            .toList();

        return ResponseEntity.ok(CollectionModel.of(result));
    }
}
~~~

The actual path is Spring Data REST's base path plus `/people/search/active`. For example, if the base path is `/api`, the request is `GET /api/people/search/active`.

This is the right approach when an endpoint belongs to a repository resource and needs Spring Data REST's related configuration. Spring Data REST documentation states that this type of Controller is handled by a dedicated handler mapping and can apply the corresponding repository's CORS rules as well as `OpenEntityManagerInViewInterceptor` when using JPA.

If a custom mapping overlaps an already exported search endpoint, treat it as an intentional override: document the endpoint contract clearly, ensure the mapping registers as expected, and write tests for the active handler. If you only want to add new functionality, pick a path not already used by the repository.

### 4.2. @BasePathAwareController: Custom Controllers Under the Base Path

Use `@BasePathAwareController` when building custom operations under Spring Data REST's base path that are not specific to a single repository—such as reports, aggregated resources, or orchestration endpoints.

~~~java
@BasePathAwareController
class ReportController {

    @ResponseBody
    @GetMapping("/reports/daily")
    DailyReport dailyReport() {
        return reportService.createDailyReport();
    }
}
~~~

With base path `/api`, the endpoint is `GET /api/reports/daily`. The `reports` namespace is dedicated to the Controller so it does not compete with `/people` or `/orders`.

### 4.3. @RestController: Standalone Spring MVC APIs

Use `@RestController` for standard Spring MVC API endpoints outside the processing scope of Spring Data REST.

~~~java
@RestController
@RequestMapping("/internal")
class InternalController {

    @GetMapping("/health")
    HealthStatus health() {
        return new HealthStatus("UP");
    }
}
~~~

This Controller uses Spring MVC's mapping. It does not automatically inherit Spring Data REST's base path and does not automatically use Spring Data REST's message converters, exception handling, or CORS configuration. If you want it under the same base path, configure the application prefix consistently or consider `@BasePathAwareController`.

Do not use a plain `@RestController` intending to override a repository endpoint and expect Spring Data REST to recognize it. If you want to handle requests within a repository's URI space, use `@RepositoryRestController`.

## 5. Before-and-After Design Example

Suppose a repository exports:

~~~java
@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

The repository endpoints already occupy `/products`:

- `GET /api/products`
- `POST /api/products`
- `GET /api/products/10`
- `PUT /api/products/10`
- `PATCH /api/products/10`
- `DELETE /api/products/10`
- Exported search and association paths.

Collision-prone design:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductDetails details(@PathVariable Long id) {
        // custom details
    }

    @PostMapping
    ProductView create(@RequestBody ProductInput input) {
        // custom create flow
    }
}
~~~

Both `GET /api/products/{id}` and `POST /api/products` collide with repository functionality. Clients may hit the wrong handler or receive a response differing from the expected HAL format.

Namespace-separated design:

~~~java
@RestController
@RequestMapping("/api/product-operations")
class ProductOperationsController {

    @GetMapping("/{id}/summary")
    ProductSummary summary(@PathVariable Long id) {
        // custom summary
    }

    @PostMapping("/{id}/recalculate")
    RecalculationResult recalculate(@PathVariable Long id) {
        // custom operation
    }
}
~~~

Specialized operations live at `/api/product-operations/**`; the repository still manages `/api/products/**`. If you want these operations under the base path managed by Spring Data REST, you can use `@BasePathAwareController` with `/product-operations/**` instead of hardcoding `/api`.

## 6. When You Need to Customize a Repository Endpoint Itself

There are business cases requiring you to keep the repository URI intact while handling requests differently from the default endpoint. For example, a query method may return data filtered by extra rules, or a response may aggregate data from multiple repositories.

In that case:

1. Identify the exact URI and HTTP method exported by the repository.
2. Create a `@RepositoryRestController` with a mapping inside the same URI space.
3. Avoid registering a regular `@RestController` on the same path expecting it to override Spring Data REST's handler.
4. Return a representation suited to the API. With Spring HATEOAS, use `EntityModel` for a single resource and `CollectionModel` for a collection where appropriate.
5. Write tests confirming requests actually reach the custom handler and responses do not break the HAL contract clients rely on.

If the goal is simply renaming or hiding a repository endpoint, consider repository or query method export configuration before creating a new Controller. Adding extra handlers for an existing URI can increase routing complexity.

## 7. How to Check for Colliding Paths

### 7.1. Inspect the Actual Registered Mappings

When Spring Boot Actuator is enabled and the mappings endpoint is exposed, you can inspect:

~~~http
GET /actuator/mappings
~~~

Search for paths related to repositories and custom Controllers. This endpoint can display handler methods along with registered mappings. Only expose Actuator mappings in appropriate environments and to authorized users because this information reveals the application's internal structure.

You can enable detailed logging for mapping registration and handler selection in development environments:

~~~properties
logging.level.org.springframework.web.servlet.handler=DEBUG
logging.level.org.springframework.data.rest.webmvc=DEBUG
~~~

Exact logger names and log verbosity may vary across Spring Framework / Spring Data REST versions.

### 7.2. Testing with MockMvc

Do not merely check that the application starts successfully. Send requests to important URIs and verify the handler, status, and response:

~~~java
@WebMvcTest
class RepositoryRouteTests {

    @Autowired
    MockMvc mvc;

    @Test
    void repositoryCollectionUsesSpringDataRest() throws Exception {
        mvc.perform(get("/api/people"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON));
    }

    @Test
    void customReportUsesItsOwnNamespace() throws Exception {
        mvc.perform(get("/api/reports/daily"))
            .andExpect(status().isOk());
    }

    @Test
    void customRepositoryOperationUsesExpectedHandler() throws Exception {
        mvc.perform(get("/api/people/search/active"))
            .andExpect(status().isOk());
    }
}
~~~

This is an illustrative skeleton. Add mock repositories/services, Spring Data REST configuration, and body/link assertions matching your real application. If using `@WebMvcTest`, ensure the slice test imports all required configuration; an integration test with `@SpringBootTest` and `@AutoConfigureMockMvc` may be more appropriate when testing both repository handler mappings and MVC handler mappings together.

Points to confirm:

- Repository collection and item URIs still return expected responses.
- Default search endpoints still work if not intentionally overridden.
- Custom endpoints route to the intended Controller.
- Requests with unsupported HTTP methods return appropriate statuses.
- Base path is applied properly to both repositories and annotated Controllers.
- No legacy or other endpoints accidentally occupy the same path.

## 8. Checklist Before Adding a Controller

- Document Spring Data REST's base path, e.g., `/api`.
- Document the actual collection path of each exported repository.
- List important item, search, and association paths.
- Choose a separate namespace for independent business Controllers.
- Use `@RepositoryRestController` when handling requests inside a repository's URI space.
- Use `@BasePathAwareController` for custom operations under the base path not tied to a single repository.
- Use `@RestController` for standalone Spring MVC APIs outside repository scope.
- Inspect actual mappings and run request tests for every path at risk of collision.
- When changing a repository path, update clients, API docs, and related links.

## Conclusion

Spring Data REST owns the URI space generated from exported repositories. Custom Controllers need their own namespace if they provide independent functionality. When you need a custom handler inside a repository's URI space, use `@RepositoryRestController`; when you need shared endpoints under the base path, use `@BasePathAwareController`; and plain `@RestController` is for standalone Spring MVC mappings. Verify routes via actual mappings and MockMvc/integration tests to ensure each request reaches the intended handler.

## References

- Spring Data REST – Overriding Spring Data REST Response Handlers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
- Spring Data REST – Adding Spring Data REST to an Existing Spring MVC Application: https://www.springframework.org/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html
- Spring Data REST – Getting Started and Changing the Base URI: https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html
