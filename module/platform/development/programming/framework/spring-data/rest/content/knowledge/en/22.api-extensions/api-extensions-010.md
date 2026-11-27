# Resolving Mapping Conflicts and Intentionally Overriding Default Handlers

## Objectives

Spring Data REST automatically generates HTTP endpoints from exported repositories. When an application needs to handle a special route, add business logic, or replace a default response, custom controllers can overlap URIs with collection, item, or search resources managed by Spring Data REST.

To handle this properly, you need to understand which controller owns a URL, which mapping takes precedence, and which annotation places a custom controller in the right Spring Data REST scope.

Key principles:

- Use `@RepositoryRestController` when the custom handler belongs to an exported repository's URI space and needs Spring Data REST message converters, exception handling, CORS, and integrations.
- Use `@BasePathAwareController` for custom endpoints under the API base path that are not tied to a specific repository resource.
- Use a regular `@Controller` or `@RestController` for standalone Spring MVC endpoints with their own prefix that do not compete with repository URIs.
- If intentionally replacing an auto-generated search endpoint, manage the finder's export status so only one handler owns the route.
- Do not modify `HandlerMapping` ordering or internal implementations just to force a route to execute as desired.

## 1. How Does Spring Data REST Generate Routes from Repositories?

Example repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

With the default base path, Spring Data REST creates the main resources:

| Resource | Example URI | Purpose |
|---|---|---|
| Collection | `/people` | List and create Persons |
| Item | `/people/42` | Read, update, or delete a Person |
| Search collection | `/people/search` | Discover exported finders |
| Search method | `/people/search/findByLastName?lastName=Nguyen` | Execute derived query |

If the base path is configured as `/api`, the corresponding URIs receive that prefix:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

Then the collection is `/api/people`, the item is `/api/people/42`, and the search resource is `/api/people/search`.

Because routes are generated from repositories, a custom MVC controller with a mapping like `/people/{id}` can collide with the very URI managed by Spring Data REST. Before adding a controller, determine the exact collection path, item path, search path, and API base path.

## 2. RepositoryRestHandlerMapping and URL Ownership

Spring Data REST registers its own `RepositoryRestHandlerMapping`. This mapping looks up handlers belonging to Spring Data REST and only accepts requests when the path corresponds to an exported repository.

This has two consequences:

1. URIs inside a repository's namespace may be handled by Spring Data REST, even when the application has other MVC controllers.
2. URIs that do not correspond to an exported repository can be forwarded to other `HandlerMapping` beans for Spring MVC to handle.

For example, when a repository is exported under `people`, requests starting with `/people` belong to the repository's URI space. If the application has a regular controller that also declares `/people/{id}`, do not assume that controller will receive the request.

A custom controller wanting to participate in this URI space must use Spring Data REST's annotations. Declaring the same path on a `@RestController` does not automatically replace the repository's default handler.

Do not modify `HandlerMapping` order or replace Spring Data REST internal beans to resolve ordinary conflicts. Supported extension points are `@RepositoryRestController`, `@BasePathAwareController`, exposure configuration, and repository/finder export status.

## 3. Choosing the Right Annotation for a Custom Controller

Three common choices serve different scopes:

| Annotation | When to Use | Spring Data REST Integration |
|---|---|---|
| `@RepositoryRestController` | Handler tied to a repository's URI space | Includes base path, repository CORS, and JPA OpenEntityManagerInView; uses framework REST configuration |
| `@BasePathAwareController` | Custom endpoint under the base path, not a specific entity operation | Attached to the API base path |
| `@Controller` / `@RestController` | Standalone MVC endpoint separated from repository URI space | Uses standard Spring MVC mechanics, outside REST exporter handling |

### 3.1. @RepositoryRestController

Use when a custom handler overrides or extends behavior for a resource managed by Spring Data REST:

~~~java
@RepositoryRestController
public class PersonSearchController {

    private final PersonRepository repository;

    public PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/search/recent")
    public ResponseEntity<?> findRecentPeople() {
        // Query repository and build custom representation.
        return ResponseEntity.ok(repository.findTop10ByOrderByCreatedAtDesc());
    }
}
~~~

This controller sits inside Spring Data REST's API base path. If the base path is `/api`, the mapping above is accessed at `/api/people/search/recent`.

This annotation also lets the handler receive integrations per repository path:

- CORS configuration defined for the corresponding repository.
- `OpenEntityManagerInViewInterceptor` when using JPA, allowing access to lazy-loaded properties within the request scope.
- Spring Data REST message converters and exception handling.

### 3.2. @BasePathAwareController

Use when you want an endpoint under the base path that is not tied to a specific repository, such as metadata or aggregate operations:

~~~java
@BasePathAwareController
public class ApiMetadataController {

    @GetMapping("/metadata/status")
    @ResponseBody
    public Map<String, String> status() {
        return Map.of("status", "available");
    }
}
~~~

If the base path is `/api`, the endpoint is at `/api/metadata/status`. This is a good fit when the API needs a custom route alongside repository resources.

### 3.3. Regular @RestController

If an endpoint does not belong under the API base path or does not need Spring Data REST integrations, use a separate MVC controller with a clear prefix:

~~~java
@RestController
@RequestMapping("/internal/reports")
public class InternalReportController {

    @GetMapping("/summary")
    public ReportSummary summary() {
        return new ReportSummary("ready");
    }
}
~~~

Do not use a standard MVC controller to compete with URIs exported by Spring Data REST. Standard controllers sit outside Spring Data REST's message converters, exception handling, and repository CORS configuration.

## 4. Intentionally Overriding a Default Search Handler

A clear scenario is when a repository already has a finder, but the default response does not meet requirements. For example, you want to keep `/orders/search/by-status` while adding authorization checks, aggregation, or result transformation.

Repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @RestResource(
        path = "by-status",
        rel = "by-status",
        exported = false
    )
    List<Order> findByStatus(OrderStatus status);
}
~~~

`exported = false` prevents this finder from being published as a default search resource. The Java method still exists and custom controllers can call it via the repository.

Custom handler:

~~~java
@RepositoryRestController
public class OrderSearchController {

    private final OrderRepository repository;

    public OrderSearchController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/search/by-status")
    public ResponseEntity<?> findByStatus(
            @RequestParam OrderStatus status) {

        List<Order> orders = repository.findByStatus(status);
        return ResponseEntity.ok(CollectionModel.of(
            orders.stream().map(EntityModel::of).toList()
        ));
    }
}
~~~

In this setup:

- The public URL remains `/orders/search/by-status`.
- The automatic finder is no longer exported.
- The custom controller handles requests and builds responses.
- The repository method remains usable as an internal application query API.

If the response is a hypermedia collection, add a self link and any required links. For example, use Spring HATEOAS `linkTo(methodOn(...))` to build links rather than concatenating URLs manually.

## 5. Replacing the Response Handler for an Existing Route

When you need to replace the handler for an existing URI, proceed in order:

1. Determine the exact URI after combining API base path, repository path, and resource suffix.
2. Identify the HTTP method to replace, e.g., only GET or only DELETE.
3. Create a `@RepositoryRestController` because the route belongs to the repository's URI space.
4. Declare a specific mapping for that exact URI and method.
5. If the route comes from an auto-exported query method, disable exporting that finder with `@RestResource(exported = false)`.
6. If replacing a CRUD operation, configure repository exposure so the default method is no longer published per your policy.
7. Test the actual route to verify the custom handler is invoked and other methods keep their expected behavior.

Do not disable the entire repository just to replace one search method. `@RepositoryRestResource(exported = false)` hides the entire repository resource; use it only when you intend to stop exporting the whole repository and take full responsibility for providing replacement APIs.

For CRUD operations, `RepositoryRestConfiguration.getExposureConfiguration()` lets you configure exported HTTP methods for collection or item exposure. Scope it strictly to the domain type and resource kind being replaced. Then retest with HTTP requests, because disabling a default method and registering a custom handler are two separate configurations.

Do not let a default finder and a custom controller contend for ownership of the same route without a clear reason. If two handlers are registered in the same mapping context, the application may fail at startup with an ambiguous mapping error or pick a different handler than intended.

## 6. Distinguishing Extending an Endpoint from Replacing an Endpoint

Not every customization requires replacing the default handler.

| Requirement | Appropriate Mechanism |
|---|---|
| Normalize entity before saving | Repository event handler |
| Validate data before writing | Validator or appropriate event handler |
| Add a new search endpoint | Query method or `@RepositoryRestController` with a distinct path |
| Replace response of a search route | Hide default finder, then register custom handler on the same path |
| Add metadata or aggregate endpoint under base path | `@BasePathAwareController` |
| Change HTTP method exposure | `RepositoryRestConfigurer` and exposure configuration |
| Change JSON representation | Projection, excerpt, Jackson customization |
| Change shared repository queries or behavior | Repository fragment or custom repository implementation |
| Build a completely standalone API | `@RestController` with a separate URI prefix |

Use event handlers when hooking into the lifecycle while keeping Spring Data REST's request mapping and response flow intact. Use custom controllers when you need control over request/response handling, status codes, headers, or representation structure.

## 7. Returning Proper Hypermedia Representation Types

Custom controllers under Spring Data REST should generally return `ResponseEntity` and Spring HATEOAS models.

Collection example:

~~~java
@RepositoryRestController
public class ProductSummaryController {

    private final ProductRepository repository;

    public ProductSummaryController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/products/search/featured")
    public ResponseEntity<CollectionModel<EntityModel<Product>>> featured() {

        List<EntityModel<Product>> items = repository.findFeatured()
            .stream()
            .map(EntityModel::of)
            .toList();

        CollectionModel<EntityModel<Product>> model =
            CollectionModel.of(items);

        model.add(linkTo(methodOn(ProductSummaryController.class)
            .featured()).withSelfRel());

        return ResponseEntity.ok(model);
    }
}
~~~

Commonly used model types:

- `EntityModel<T>`: an entity or DTO with links.
- `CollectionModel<T>`: a set of items with collection-level links.
- `RepresentationModel<T>`: base abstraction for representations with links.

If returning a DTO or object directly from a controller annotated with `@RepositoryRestController`, ensure the return value is written to the response. You can use `ResponseEntity` or `@ResponseBody` on the method; `@RepositoryRestController` is not synonymous with `@RestController`.

Do not return raw entities in every case if the API needs field control, links, projections, or protection against unintended lazy loading. Choose the representation matching the API contract clients need.

## 8. Base Path and Mapping Paths

Spring Data REST custom controllers use the API base path from `RepositoryRestConfiguration.setBasePath(...)`. Paths declared on methods are combined with that base path.

Example:

~~~java
config.setBasePath("/api");
~~~

~~~java
@RepositoryRestController
public class InventoryController {

    @GetMapping("/inventory/summary")
    public ResponseEntity<?> summary() {
        return ResponseEntity.ok(Map.of("count", 12));
    }
}
~~~

The actual URL is `/api/inventory/summary`.

For routes inside a repository namespace, use the full path relative to the base path, such as `/orders/search/by-status`. Do not prepend `/api` manually to the method mapping if the base path is already configured as `/api`, as that can produce duplicated prefixes.

When multiple base paths or a servlet context path are present, distinguish them:

- Servlet context path belongs to application deployment configuration.
- Spring Data REST base path belongs to the API exporter.
- Repository path belongs to the repository's annotation or resource mapping.
- Method mapping belongs to the custom controller.

Document each segment clearly in your API docs and verify the final URL with integration tests.

## 9. CORS, Lazy Loading, and Security in Custom Handlers

One benefit of `@RepositoryRestController` is that handlers integrate with several repository settings:

- CORS is applied according to the repository matching the path.
- JPA `OpenEntityManagerInViewInterceptor` supports reading lazy properties during the request.
- Spring Data REST's message converters and exception handling are used.

Even so, custom handlers must still obey the application's security policy. Use Spring Security for authentication and authorization; do not assume an endpoint inside the repository namespace is automatically protected.

If a handler calls a repository method annotated with `@PreAuthorize`, method security continues to apply through the repository proxy. If a handler returns aggregated data, enforce permissions on each dataset and operation according to business rules.

With `@BasePathAwareController` or standard MVC controllers, verify CORS, serialization, exception mapping, and security separately because repository-specific handler integrations may not apply in the same way.

## 10. Detecting Mapping Conflicts

At application startup, Spring MVC registers request mappings from controllers. If two methods in the same mapping context have identical conditions such that they cannot be disambiguated, Spring may report an ambiguous mapping error.

Signs to watch for:

- Startup logs report two handlers mapped to the same path and HTTP method.
- Requests return responses from the default controller instead of the custom controller.
- Custom routes return 404 because the controller is not in the right mapping context.
- GET works, while POST/PUT/DELETE are picked up by a different handler.
- The API base path is duplicated or missing.
- A route only works when the repository is hidden, but loses desired CORS or message converter integration.

How to resolve:

1. Read mapping logs at application startup and identify the two specific handlers.
2. Compare path, HTTP method, request parameter conditions, consumes, and produces.
3. Verify the controller uses the right annotation for its URI space.
4. Check whether the finder/repository is exporting a default route.
5. Disable exporting the default route when a custom handler intentionally replaces that route.
6. Rerun integration tests for the custom route and neighboring routes.

Do not rely on method declaration order in source code to resolve conflicts. Do not alter internal `HandlerMapping` order as a default workaround; that ties routing to framework implementation details.

## 11. Testing Custom Handlers with MockMvc

Test both the replaced route and remaining repository routes.

Example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSearchControllerTests {

    @Autowired
    MockMvc mvc;

    @Test
    void customSearchHandlerReturnsCollection() throws Exception {
        mvc.perform(get("/orders/search/by-status")
                .param("status", "OPEN")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON
            ));
    }

    @Test
    void repositoryCollectionStillWorks() throws Exception {
        mvc.perform(get("/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }
}
~~~

This is a test skeleton; adjust media types to match the controller's actual representation. If the controller returns plain JSON instead of HAL, verify `application/json` and the corresponding DTO structure.

Scenarios to verify:

- The custom handler is actually invoked for the expected URI and HTTP method.
- The default finder is hidden if replacing that finder.
- HAL search links accurately reflect export status.
- Unrelated collection and item resources still function.
- The base path is prepended correctly.
- Responses have the right status, headers, and content type.
- Repository CORS policy applies when using `@RepositoryRestController`.
- Security still blocks unauthorized users.
- No ambiguous mappings occur on startup.

You can use a mock service or spy to verify the custom handler called the expected logic. However, integration tests must go through MockMvc and real Spring MVC mapping to catch route conflicts; invoking Java methods directly does not test routing.

## 12. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Custom `@RestController` does not receive requests under repository path | Spring Data REST owns the repository's URI space | Use `@RepositoryRestController` if integration with the repository is needed |
| Custom controller is not selected | Annotation or mapping context mismatch | Check `@RepositoryRestController`, base path, and repository path |
| Application reports ambiguous mapping | Default finder and custom handler register the same route | Hide default finder with `@RestResource(exported = false)` when replacing it |
| Custom endpoint lacks API prefix | Confused base path with method mapping | Use path relative to base path; do not repeat prefix |
| Response object not serialized as expected | Method lacks response body semantics or returns unsuitable type | Use `ResponseEntity` or `@ResponseBody` |
| CORS differs from default repository | Controller sits outside SDR handler mapping | Use `@RepositoryRestController` or configure CORS separately |
| Lazy property error after returning response | Custom handler lacks JPA OpenEntityManagerInView integration | Use a repository-aware controller or fetch data in an explicit transaction |
| Disabling whole repository breaks CRUD routes | Used `@RepositoryRestResource(exported = false)` too broadly | Disable only the finder/method being replaced or design full replacement APIs |
| Custom GET works but DELETE remains default | Replaced only one HTTP method | Configure each method/exposure being replaced individually |
| Tests miss conflicts | Calling controller method directly | Use MockMvc to test actual routing |

## 13. Checklist for Resolving Mappings and Replacing Handlers

- List exported collection, item, search URIs, and API base path.
- Identify the route and HTTP method to extend or replace.
- Use `@RepositoryRestController` for handlers inside the repository URI space.
- Use `@BasePathAwareController` for custom endpoints under the base path not tied to a specific repository.
- Use `@RestController` with a standalone prefix for MVC APIs outside Spring Data REST.
- When replacing a default finder, set `@RestResource(exported = false)` on that finder.
- When replacing CRUD methods, adjust exposure for the specific resource and HTTP method.
- Do not disable the entire repository when only one route needs replacing.
- Use `ResponseEntity`, `EntityModel`, and `CollectionModel` for appropriate responses.
- Do not prepend the base path twice.
- Verify CORS, JPA lazy loading, and Spring Security for custom handlers.
- Inspect mapping logs and run MockMvc tests for new and neighboring routes.
- Do not modify internal `HandlerMapping` order to work around routine conflicts.

## Conclusion

Mapping conflicts in Spring Data REST arise when custom controllers and repository-generated endpoints compete for the same URI or when a controller is placed in the wrong mapping context. `@RepositoryRestController` is the choice for handlers in a repository's URI space that need REST exporter integrations; `@BasePathAwareController` fits custom endpoints under the base path that are not tied to an entity; standard MVC controllers should use an independent prefix. When replacing a default finder, hide the finder with `@RestResource(exported = false)` and map the custom handler to that route deliberately. For CRUD, adjust exposure per method. Always verify base path, mapping logs, response representations, and remaining routes with integration tests.

## References

- Spring Data REST – Overriding Spring Data REST Response Handlers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
- Spring Data REST – RepositoryRestController API: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositoryRestController.html
- Spring Data REST – Adding Spring Data REST to an Existing Spring MVC Application and RepositoryRestHandlerMapping: https://docs.spring.io/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html
- Spring Data REST – Customizing Spring Data REST and supported HTTP methods: https://docs.spring.io/spring-data/rest/reference/customizing/customizing-sdr.html
