# @RepositoryRestController and Integration with Base Path, Converters, and Error Handling in Spring Data REST

## Objectives

Spring Data REST automatically exports Spring Data repositories as REST resources. However, there are cases where an application needs a custom endpoint to process business logic, aggregate data, add validation steps, or modify the representation before returning a response.

If the endpoint needs to operate within the Spring Data REST URI space and use the exporter's infrastructure, consider `@RepositoryRestController`. This annotation allows custom controllers to share important Spring Data REST settings such as:

- The API base path configured in `RepositoryRestConfiguration`.
- Message converters and content negotiation from the exporter.
- Spring Data REST's exception handling mechanism.
- CORS policies of the repository associated with the path.
- With JPA, `OpenEntityManagerInViewInterceptor` is applied to matching handlers to support accessing lazy properties during the request.

This lesson explains how to define routes, integrate with the base path, use `DomainClassConverter` and `AggregateReference` to resolve domain objects/URI references, build HAL responses with Spring HATEOAS, and handle errors according to the HTTP contract.

## 1. When Should You Use @RepositoryRestController?

Use `@RepositoryRestController` when a custom handler is tied to a repository resource or needs to blend into the URI space managed by Spring Data REST.

For example, the Order repository is exported at `/orders` and the application wants to add endpoints:

~~~text
GET /api/orders/42/summary
GET /api/orders/search/recent
POST /api/orders/42/recalculate
~~~

These endpoints belong to the Order repository's API area and need to use the exporter configuration.

A controller can be declared as follows:

~~~java
@RepositoryRestController
class OrderCustomController {

    private final OrderRepository repository;

    OrderCustomController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<?> getSummary(@PathVariable Long id) {
        // Read data, apply business logic, and build the representation.
        return ResponseEntity.ok().build();
    }
}
~~~

Import the annotation:

~~~java
import org.springframework.data.rest.webmvc.RepositoryRestController;
~~~

This is a Spring bean created via the `@Component` meta-annotation. The controller still uses standard Spring MVC annotations such as `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam`, and `@RequestBody`.

Crucially, the request mapping must lie within the URI space managed by Spring Data REST. The exporter's handler mapping checks exported repositories by the corresponding path segment. If the path does not belong to an appropriate repository area, the request may be forwarded to other `HandlerMapping` instances or fail to be handled by the custom handler as expected.

## 2. Integrating with the API Base Path

Suppose the application configures:

~~~properties
spring.data.rest.base-path=/api
~~~

Or configures it in Java:

~~~java
@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

With the controller:

~~~java
@RepositoryRestController
class OrderCustomController {

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<?> getSummary(@PathVariable Long id) {
        // ...
        return ResponseEntity.ok().build();
    }
}
~~~

The external URL is:

~~~http
GET /api/orders/42/summary
~~~

Spring Data REST automatically places the controller under the configured base path. Therefore, the mapping method only declares the relative path portion such as `/orders/{id}/summary`; do not repeat `/api` in every annotation.

If you both configure the `/api` base path and write:

~~~java
@GetMapping("/api/orders/{id}/summary")
~~~

the URL may become a duplicated path `/api/api/orders/...` or fail to match the intended URI, depending on the mapping configuration. Let the exporter manage the base path.

You can verify the base path by calling the API root and following HAL links. For custom routes, expose links from related representations if clients need to discover the endpoint instead of constructing URLs manually.

## 3. Distinguishing @RepositoryRestController, @BasePathAwareController, and @RestController

The three annotations serve different scopes:

| Annotation | Suitable Scope | Spring Data REST Infrastructure |
| --- | --- | --- |
| `@RepositoryRestController` | Custom operations tied to a repository's URI space | Yes: base path, message converters, exception handling, and additional exporter features |
| `@BasePathAwareController` | Custom operations under the base path not tied to a specific entity/repository | Placed under the base path; used when building standalone resources or views |
| `@RestController` | Standard Spring MVC API with its own namespace | Does not automatically use Spring Data REST infrastructure |

Example using `@BasePathAwareController` for a general endpoint:

~~~java
@BasePathAwareController
class ApiHealthController {

    @GetMapping("/health")
    ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "UP"));
    }
}
~~~

With base path `/api`, the endpoint resides at `/api/health`. This endpoint belongs to the Spring Data REST namespace, but is not an operation on a specific repository.

Use `@RestController` if you want routes belonging entirely to Spring MVC, such as `/internal-tools/**` or a separate API version. Standard controllers do not automatically receive Spring Data REST's base path, message converters, exception handling, or CORS configuration.

In summary:

- Custom operations around a repository resource: `@RepositoryRestController`.
- General resources under the base path: `@BasePathAwareController`.
- Standalone MVC API: `@RestController`.

## 4. Avoiding Conflicts with Default Repository Routes

Spring Data REST already creates routes for collection, item, search, and association resources. Custom handlers should not accidentally overlap mappings with default endpoints.

For example, an Order repository has:

~~~java
@RepositoryRestResource(path = "orders")
interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

The exporter may use:

~~~text
GET    /api/orders
POST   /api/orders
GET    /api/orders/{id}
PUT    /api/orders/{id}
PATCH  /api/orders/{id}
DELETE /api/orders/{id}
~~~

Custom routes should have a clear suffix or namespace:

~~~java
@GetMapping("/orders/{id}/summary")
@GetMapping("/orders/search/recent")
@PostMapping("/orders/{id}/recalculate")
~~~

Avoid declaring a custom `@GetMapping("/orders/{id}")` unless your goal is to replace the default item resource. When you truly want to override the response handler for a specific resource, you need to understand `HandlerMapping` ordering and exporter behavior on your exact Spring Data REST version.

If a custom operation does not need to be tied to a repository, move it to a `@BasePathAwareController` or a separate MVC controller to avoid URI contention.

## 5. Creating Hypermedia Responses with Spring HATEOAS

Custom handlers can return `ResponseEntity` to control the HTTP status and headers. If the response belongs to a hypermedia API, use Spring HATEOAS model types instead of returning a raw `List<T>`.

Collection example:

~~~java
@RepositoryRestController
class OrderCustomController {

    private final OrderRepository repository;

    OrderCustomController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/search/recent")
    ResponseEntity<CollectionModel<EntityModel<Order>>> recent() {

        List<EntityModel<Order>> items = repository
                .findTop10ByOrderByCreatedAtDesc()
                .stream()
                .map(order -> EntityModel.of(
                        order,
                        linkTo(methodOn(OrderCustomController.class)
                                .getSummary(order.getId()))
                                .withRel("summary")))
                .toList();

        CollectionModel<EntityModel<Order>> model =
                CollectionModel.of(items);

        model.add(linkTo(methodOn(OrderCustomController.class)
                .recent()).withSelfRel());

        return ResponseEntity.ok(model);
    }

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<EntityModel<Order>> getSummary(@PathVariable Long id) {
        Order order = repository.findById(id).orElseThrow();
        return ResponseEntity.ok(EntityModel.of(order));
    }
}
~~~

Commonly used model types:

- `CollectionModel<T>`: representation for a collection.
- `EntityModel<T>`: representation for a single entity/resource.
- `RepresentationModel<T>`: a more general abstraction for resources with links.

Spring Data REST recommends wrapping collections in `CollectionModel`; single items can use `EntityModel` or `RepresentationModel`. Links can be built with `linkTo(methodOn(...))` to avoid hardcoding host, port, or base path.

Common imports:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
~~~

When returning `ResponseEntity`, Spring MVC/Spring Data REST selects the message converter matching the request's `Accept` header. Clients can request HAL using:

~~~http
Accept: application/hal+json
~~~

Do not return internal implementations like `PageImpl` directly if you need a stable JSON contract. For pages, use Spring HATEOAS `PagedModel`/assembler or a clearly designed DTO representation.

## 6. DomainClassConverter: Resolving Path Variables into Entities

Spring Data web support provides `DomainClassConverter`. This converter allows a method parameter to be a repository-managed domain type, rather than receiving an ID and manually calling the repository.

Example:

~~~java
@RepositoryRestController
class PersonCustomController {

    @GetMapping("/people/{id}/card")
    ResponseEntity<PersonCard> getCard(
            @PathVariable("id") Person person) {

        return ResponseEntity.ok(
                new PersonCard(person.getId(), person.getDisplayName()));
    }
}
~~~

When Spring Data web support is enabled and the appropriate converter is registered, Spring MVC performs these steps:

1. Reads the string value from the path variable, e.g. `42`.
2. Uses `ConversionService` to convert the string into the domain type's ID type, e.g. `Long`.
3. Finds the `CrudRepository` managing that domain type.
4. Calls the repository to fetch the corresponding entity.
5. Passes the entity into the controller parameter.

Spring Data web support can be enabled via:

~~~java
@Configuration
@EnableSpringDataWebSupport
class SpringDataWebConfiguration {
}
~~~

In Spring Boot or Spring Data REST applications that already auto-configure web support, check the existing configuration before registering this annotation again to avoid duplicate configuration.

`DomainClassConverter` requires the corresponding repository to implement `CrudRepository` in order to be discovered for conversion. It is especially handy when a custom handler accepts standard resource IDs.

### When Should You Accept an ID and Look Up the Repository Yourself?

Not every case should use a domain parameter. If you want to explicitly handle the not-found case, you can accept the ID and call the repository:

~~~java
@GetMapping("/people/{id}/card")
ResponseEntity<PersonCard> getCard(@PathVariable Long id) {

    Person person = repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Person not found"));

    return ResponseEntity.ok(
            new PersonCard(person.getId(), person.getDisplayName()));
}
~~~

This approach gives the controller explicit control to define the 404 response, check permissions on the entity before returning data, and manage multi-step business logic more easily.

Do not assume every converter turns a string into an entity by the same rules. `DomainClassConverter` uses the repository's ID type; it does not simply parse a JSON body and does not replace authorization logic.

## 7. AggregateReference: Accepting Resource Reference URIs in Spring Data REST

In a custom controller, a request may contain a URI pointing to another aggregate. Starting from Spring Data REST 4.1, you can use `AggregateReference<T, ID>` as a parameter to receive a URI and resolve it into an ID or aggregate.

Example client request:

~~~http
GET /api/scanners?producer=http://localhost:8080/api/producers/15
Accept: application/hal+json
~~~

Controller:

~~~java
@RepositoryRestController
class ScannerController {

    @GetMapping("/scanners")
    ResponseEntity<?> getScanners(
            @RequestParam AggregateReference<Producer, Long> producer) {

        Long producerId = producer.resolveRequiredId();

        // Use producerId to query Scanners by producer.
        return ResponseEntity.ok().build();
    }
}
~~~

You can request the full aggregate:

~~~java
Producer producer = producerReference.resolveRequiredAggregate();
~~~

Key methods:

- `getUri()`: gets the source URI sent by the client.
- `resolveId()`: resolves the identifier, returning null if it cannot be resolved.
- `resolveRequiredId()`: requires that the ID can be resolved.
- `resolveAggregate()`: resolves the aggregate, returning null if not found.
- `resolveRequiredAggregate()`: requires that the aggregate is found.
- `withIdSource(...)`: customizes how the identifier is extracted from URI components.

Import:

~~~java
import org.springframework.data.rest.core.AggregateReference;
~~~

Unlike `DomainClassConverter`, `AggregateReference` works with URIs following the scheme Spring Data REST uses to expose item resources. It fits when the client passes a resource URI instead of sending just a raw ID value.

If using custom identifiers in URIs, such as a username or slug, you may need to customize identifier extraction with `withIdSource`. Check the identifier mapping and repository lookup to ensure URI references resolve consistently.

Do not accept arbitrary URIs from clients and fetch arbitrary URLs yourself. AggregateReference resolves references through Spring Data REST's repository infrastructure; you must still validate domain type, aggregate existence, and access permissions.

## 8. Distinguishing DomainClassConverter and AggregateReference

| Criterion | DomainClassConverter | AggregateReference |
| --- | --- | --- |
| Typical input | Path variable or request parameter containing an ID | URI of an item resource |
| Result | Domain object managed by a repository | URI reference resolvable to an ID or aggregate |
| Mechanism | ConversionService + CrudRepository | Spring Data REST URI resolution |
| Use when | Route has `/{id}` and handler needs the entity directly | Request references another resource by URI |
| Repository type | Requires a discovered CrudRepository | Based on Spring Data REST aggregate/repository mapping |
| Identifier customization | Follows repository ID conversion | Can use `withIdSource` to extract ID from URI |

Short example:

~~~java
// ID in path -> domain object
@GetMapping("/people/{id}/card")
PersonCard getCard(@PathVariable Person person) {
    return mapper.toCard(person);
}

// URI of another resource -> aggregate identifier
@GetMapping("/scanners")
List<Scanner> byProducer(
        @RequestParam AggregateReference<Producer, Long> producer) {
    return repository.findByProducerId(producer.resolveRequiredId());
}
~~~

The two mechanisms address two different input forms. Do not substitute them mechanically.

## 9. Message Converters and Content Negotiation

An important reason to use `@RepositoryRestController` is that custom handlers are processed by Spring Data REST's infrastructure, including message converters and content negotiation settings.

Example endpoint accepting JSON only:

~~~java
@PostMapping(
    path = "/orders/{id}/commands/recalculate",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaTypes.HAL_JSON_VALUE
)
ResponseEntity<EntityModel<OrderSummary>> recalculate(
        @PathVariable Long id,
        @RequestBody RecalculateOrderRequest request) {
    // ...
}
~~~

- `consumes`: restricts the Content-Type accepted by the endpoint.
- `produces`: specifies the response format produced by the endpoint.
- `@RequestBody`: read through the appropriate message converter.
- `ResponseEntity`: controls status, headers, and body.

With the request:

~~~http
POST /api/orders/42/commands/recalculate
Content-Type: application/json
Accept: application/hal+json
~~~

Spring chooses the converter to read the JSON body and the converter to write the response according to the negotiated media type.

If the client sends an unsupported Content-Type, the server may return 415 Unsupported Media Type. If Accept cannot be satisfied, the server may return 406 Not Acceptable.

When using a standard `@RestController`, the controller can use Spring MVC converters registered for MVC, but does not automatically receive all Spring Data REST-specific message converters and representation configuration. This is a practical difference when the endpoint returns HAL or uses custom media types of the exporter.

## 10. Error Handling in Custom Handlers

Custom handlers should translate business errors into clear HTTP responses. For example:

- Resource not found: 404 Not Found.
- Caller lacks permission: 403 Forbidden.
- Invalid request: 400 Bad Request.
- Business state disallows the operation: 409 Conflict.
- Unsupported Content-Type: 415 Unsupported Media Type.

Simple approach for a specific error:

~~~java
@GetMapping("/orders/{id}/summary")
ResponseEntity<OrderSummary> getSummary(@PathVariable Long id) {

    Order order = repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found"));

    return ResponseEntity.ok(mapper.toSummary(order));
}
~~~

For custom errors, you can place `@ExceptionHandler` directly inside the controller:

~~~java
@RepositoryRestController
class OrderCustomController {

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<OrderSummary> getSummary(@PathVariable Long id) {
        // May throw OrderNotAccessibleException.
        return ResponseEntity.ok().build();
    }

    @ExceptionHandler(OrderNotAccessibleException.class)
    ResponseEntity<ProblemDetail> handleNotAccessible(
            OrderNotAccessibleException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.FORBIDDEN,
                "You do not have permission to access this order");

        problem.setTitle("Access forbidden");

        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(problem);
    }
}
~~~

Spring Framework supports `ProblemDetail` for RFC 9457 error responses on compatible versions. If your project uses an older version, you can return a custom error DTO or `ResponseEntity<ApiError>`.

### Using ControllerAdvice for Centralized Handling

You can use `@RestControllerAdvice` to handle exceptions from multiple custom controllers:

~~~java
@RestControllerAdvice(assignableTypes = OrderCustomController.class)
class OrderControllerAdvice {

    @ExceptionHandler(OrderNotAccessibleException.class)
    ResponseEntity<ApiError> handle(OrderNotAccessibleException exception) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(new ApiError(
                        "ORDER_FORBIDDEN",
                        "You do not have permission to access the order"));
    }
}
~~~

If you want the advice to apply to multiple controllers, you can omit `assignableTypes` or use an appropriate `basePackages`. However, global advice can also affect Spring Data REST's own handlers and other controllers. Limit its scope when you need to preserve the exporter's default exception mapping.

Spring Data REST has its own exception handlers for repository resources. `@RepositoryRestController` lets custom controllers share the exporter's exception handling. Regular `@RestController` controllers sit outside that scope and use Spring MVC's exception resolver mechanism.

Do not catch every exception and return 200 or a generic 500. Map exceptions according to HTTP semantics and do not expose stack traces, SQL, table names, or internal data in production responses.

## 11. Validation and Request DTO Integration

Custom endpoints typically execute business logic more complex than repository CRUD. Use a DTO for the request instead of binding the entire entity directly:

~~~java
public record RecalculateOrderRequest(
        @NotBlank String reason,
        @Min(1) int priority
) {}
~~~

~~~java
@PostMapping(
    path = "/orders/{id}/commands/recalculate",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<OrderSummary> recalculate(
        @PathVariable Long id,
        @Valid @RequestBody RecalculateOrderRequest request) {

    OrderSummary summary = orderService.recalculate(id, request);

    return ResponseEntity.ok(summary);
}
~~~

DTOs establish an allowlist of submittable fields. The service is responsible for business validation, authorization, and transactions. Do not let clients submit an entire entity graph or internal fields such as owner, tenant, payment state, or audit metadata if they lack permission to modify them.

When validation fails, Spring MVC can raise the corresponding exception. Test error responses to ensure clients receive helpful field errors without exposing sensitive data.

## 12. CORS, Lazy Loading, and Security

`@RepositoryRestController` is processed by Spring Data REST's dedicated `HandlerMapping` and therefore gains several integrations:

- CORS policies defined for the repository matching the base path segment in the mapping.
- With JPA, `OpenEntityManagerInViewInterceptor` can be applied to support accessing lazy properties during the request.

This does not mean every custom route is automatically secure:

- CORS only controls browser cross-origin access; it does not grant business authorization.
- Open EntityManager in View can allow lazy proxies to be accessed during the request, but does not replace a fetch plan or DTO.
- Spring Security must still protect custom methods and resources.
- If a custom controller accesses a repository directly, it must check tenant/owner/role just like any other API.

With a standalone `@RestController`, you need to configure CORS and transaction/fetch strategies according to the application's MVC/service infrastructure.

## 13. Testing Base Path and Custom Routes with MockMvc

Test routes after applying the base path, rather than only invoking relative mapping paths.

For example, configuring `spring.data.rest.base-path=/api`, test:

~~~java
@SpringBootTest(properties = "spring.data.rest.base-path=/api")
@AutoConfigureMockMvc
class OrderCustomControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void customRouteIsServedUnderRepositoryBasePath() throws Exception {
        mockMvc.perform(get("/api/orders/42/summary")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }
}
~~~

Testing DomainClassConverter:

~~~java
@Test
void resolvesRepositoryManagedDomainFromPathVariable() throws Exception {
    mockMvc.perform(get("/api/people/12/card")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk());
}
~~~

This test assumes web support and repository fixtures are configured, and that a Person with ID 12 exists.

Testing 404 errors:

~~~java
@Test
void returnsNotFoundForUnknownOrder() throws Exception {
    mockMvc.perform(get("/api/orders/999999/summary")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isNotFound());
}
~~~

Testing validation errors:

~~~java
@Test
void rejectsInvalidCommandBody() throws Exception {
    mockMvc.perform(post("/api/orders/42/commands/recalculate")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "reason": "",
                  "priority": 0
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Besides the status code, verify the response body and Content-Type against your chosen error contract. If the route returns HAL, verify the self link and required relations. If the route returns a JSON DTO, verify the allowlisted fields.

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Custom route lacks `/api` | Controller is not handled as RepositoryRestController or mapping belongs to standard MVC | Check the annotation and base path |
| URL becomes `/api/api/...` | Base path repeated in both config and mapping | Declare only the relative route portion in the mapping |
| Handler is not called | Path is outside the repository exporter's URI space or mapping conflicts | Check repository path, mapping, and HandlerMapping |
| `@RestController` does not use exporter message converters | Controller is outside Spring Data REST scope | Use @RepositoryRestController if the endpoint is tied to a repository |
| Cannot resolve `@PathVariable Person` | DomainClassConverter/web support is not registered or repository is unsuitable | Check @EnableSpringDataWebSupport and CrudRepository |
| AggregateReference fails to resolve URI | URI does not follow item resource scheme or identifier extractor is incorrect | Check href and withIdSource configuration |
| Returns collection without links | Handler returns a plain List instead of a HATEOAS model | Use CollectionModel/EntityModel and add links |
| Client receives 406 | Accept does not match produces/converter | Check media type and response model |
| Client receives 415 | Content-Type is not accepted by the endpoint | Declare appropriate consumes and send matching Content-Type |
| Custom error returns 500 | Exception is unmapped | Use @ExceptionHandler, ControllerAdvice, or ResponseStatusException |
| Advice alters exporter errors | Global advice catches exceptions too broadly | Scope advice to specific controllers/packages and preserve appropriate exception mapping |
| LazyInitializationException or N+1 | Accessing associations outside fetch plan or custom route lacks proper persistence context | Use service transactions, DTOs, EntityGraph, and inspect queries |
| CORS does not follow repository policy | Controller is not handled by SDR HandlerMapping or path is not tied to a repository | Check annotation, path, and RepositoryRestConfigurer |

## 15. Custom Endpoint Design Workflow

1. Determine whether the endpoint is truly tied to a repository resource or just needs to sit under the base path.
2. Choose `@RepositoryRestController`, `@BasePathAwareController`, or `@RestController` matching the scope.
3. Configure the base path in one place; mappings declare only the relative path portion.
4. Avoid conflicting with default collection, item, search, and association routes.
5. Choose the appropriate input type: ID, DomainClassConverter, AggregateReference, or DTO.
6. Use Spring HATEOAS models if the response requires hypermedia links.
7. Declare consumes/produces and return ResponseEntity with appropriate status/headers.
8. Map business exceptions to clear HTTP statuses and error bodies.
9. Protect the endpoint with authorization and owner/tenant checks.
10. Test actual URLs after base path, converters, content negotiation, and error mapping.

## References

- [Spring Data REST — Overriding Spring Data REST Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html): `@RepositoryRestController`, base path, message converters, exception handling, HATEOAS models, AggregateReference, and differences from `@BasePathAwareController`.
- [Spring Data REST API — RepositoryRestController](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestController.html): annotation marking controllers managed by Spring Data REST, CORS, and OpenEntityManagerInView integration.
- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): configuring the base path using `spring.data.rest.base-path` or `RepositoryRestConfiguration.setBasePath`.
- [Spring Data Commons — DomainClassConverter](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/support/DomainClassConverter.html): converting inputs into domain objects via ConversionService and CrudRepository.
- [Spring Data JPA — Web Support](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html): `@EnableSpringDataWebSupport`, DomainClassConverter, Pageable/Sort argument resolvers, and how Spring MVC resolves domain objects from path variables.
- [Spring Data REST API — AggregateReference](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/AggregateReference.html): receiving URI references, resolving ID/aggregate, and customizing identifier source.
- [Spring Framework — Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ExceptionHandler`, `@ControllerAdvice`, and ResponseEntity.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse, and ResponseEntityExceptionHandler per RFC 9457.
