# `@RouterOperation` for a Single Functional Route

Spring WebFlux supports declaring endpoints in two main styles. With annotated controllers, we use `@RestController`, `@GetMapping`, or `@PostMapping`. With functional endpoints, we combine `RouterFunction` to route requests and `HandlerFunction` to process those requests. The second style describes routes using a Java DSL, but lacks mapping annotations on the handler like a traditional controller.

`springdoc-openapi` provides `@RouterOperation` to attach OpenAPI metadata to a functional route. The annotation is usually placed on the `@Bean` method returning `RouterFunction`. It describes the path, HTTP method, and media types, and links the route to the handling method in the handler bean. The `operation` attribute lets you declare details such as operation ID, summary, parameters, request body, and responses.

## 1. Functional Endpoints Consist of RouterFunction and HandlerFunction

In WebFlux functional routing, two components have distinct responsibilities:

- `RouterFunction<ServerResponse>` determines which requests match the route and which handler is invoked.
- `HandlerFunction<ServerResponse>` receives `ServerRequest`, performs processing, and returns `Mono<ServerResponse>`.

Example route to fetch a customer by ID:

```java
@Bean
RouterFunction<ServerResponse> customerRoutes(CustomerHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/api/customers/{id}"),
        handler::getById
    );
}
```

The code above creates a GET route. The path is declared via `RequestPredicates.GET`, while `handler::getById` is the handling method. There is no `@GetMapping` on the handler method, so the API documentation needs separate metadata to describe this route.

## 2. `@RouterOperation` Adds OpenAPI Metadata

For a single functional route, place `@RouterOperation` on the `@Bean` method creating the `RouterFunction`:

```java
@Configuration
class CustomerRoutes {

    @Bean
    @RouterOperation(
        path = "/api/customers/{id}",
        method = RequestMethod.GET,
        produces = MediaType.APPLICATION_JSON_VALUE,
        beanClass = CustomerHandler.class,
        beanMethod = "getById",
        operation = @Operation(
            operationId = "getCustomerById",
            summary = "Get customer by ID",
            description = "Returns customer information matching the given ID.",
            tags = {"Customers"},
            parameters = @Parameter(
                name = "id",
                in = ParameterIn.PATH,
                required = true,
                description = "Customer UUID",
                schema = @Schema(type = "string", format = "uuid")
            ),
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Customer found",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = CustomerResponse.class)
                    )
                ),
                @ApiResponse(
                    responseCode = "404",
                    description = "Customer not found"
                )
            }
        )
    )
    RouterFunction<ServerResponse> getCustomerByIdRoute(CustomerHandler handler) {
        return RouterFunctions.route(
            RequestPredicates.GET("/api/customers/{id}"),
            handler::getById
        );
    }
}
```

Key attributes:

| Attribute | Role |
| --- | --- |
| `path` | Public path of the route, matching the path in the Router DSL. |
| `method` | HTTP method of the route, such as `RequestMethod.GET`. |
| `produces` | Media type returned by the route, matching the actual response. |
| `consumes` | Request media type accepted by the route, commonly used for POST/PUT with bodies. |
| `beanClass` | Handler class containing the method that handles the route. |
| `beanMethod` | Name of the handling method in the handler bean. |
| `operation` | `@Operation` annotation containing detailed OpenAPI metadata. |

`@RouterOperation` describes the route for springdoc. It does not create a runtime route and does not replace `RouterFunctions.route(...)`. If the annotation declares `/api/customers/{id}` while the Router DSL registers `/api/customer/{id}`, the documentation and application will be out of sync.

## 3. Linking the Route to a Handler Bean

The handler should be a Spring bean with clearly named handling methods:

```java
@Component
class CustomerHandler {

    private final CustomerService customerService;

    CustomerHandler(CustomerService customerService) {
        this.customerService = customerService;
    }

    Mono<ServerResponse> getById(ServerRequest request) {
        UUID id = UUID.fromString(request.pathVariable("id"));

        return customerService.findById(id)
            .flatMap(customer -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(CustomerResponse.from(customer)))
            .switchIfEmpty(ServerResponse.notFound().build());
    }
}
```

In `@RouterOperation`, `beanClass = CustomerHandler.class` and `beanMethod = "getById"` link metadata to this method. The method name must match the actual handler exactly. If there are multiple overloaded methods with the same name or if the handler is created with a lambda lacking a clear bean method, parameter and return-type inference becomes harder; in that case, explicitly declare `@Parameter`, `@RequestBody`, and response schemas in `operation`.

The example above uses `ServerRequest`, so Springdoc cannot infer the `UUID` type from a separate Java parameter as with `@PathVariable`. Therefore, an annotation explicitly describing `id` is required. It also declares the `CustomerResponse` response because the handler returns a generic `ServerResponse`.

## 4. Path and HTTP Method Must Match the Runtime Route

When writing functional routes, the path can be defined via a direct predicate:

```java
RequestPredicates.GET("/api/customers/{id}")
```

Or composed from a prefix and nested route:

```java
RouterFunctions.route()
    .path("/api/customers", builder -> builder
        .GET("/{id}", handler::getById))
    .build();
```

In both cases, the effective path is `/api/customers/{id}`. `@RouterOperation.path` must specify the full path after applying prefixes and nesting, not just the sub-path `/{id}`.

Likewise, the method must match the actual predicate. If the Router DSL uses `POST(...)` while the annotation states `RequestMethod.GET`, the docs will publish the wrong operation. Check both method and path after composing nested routes.

## 5. Documenting Request Body and Media Types

For a POST route accepting JSON, declare `consumes` on `@RouterOperation` and the request body in `@Operation`:

```java
@Bean
@RouterOperation(
    path = "/api/customers",
    method = RequestMethod.POST,
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE,
    beanClass = CustomerHandler.class,
    beanMethod = "create",
    operation = @Operation(
        operationId = "createCustomer",
        summary = "Create customer",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateCustomerRequest.class)
            )
        ),
        responses = @ApiResponse(
            responseCode = "201",
            description = "Customer created",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CustomerResponse.class)
            )
        )
    )
)
RouterFunction<ServerResponse> createCustomerRoute(CustomerHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.POST("/api/customers")
            .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON)),
        handler::create
    );
}
```

Here, `consumes` describes the request body media type; `produces` describes the response. The `contentType(...)` predicate in the Router DSL also constrains requests by `Content-Type`. Keep both parts aligned so clients know to send JSON and the server actually accepts JSON.

If a route accepts multipart, XML, or multiple media types, declare matching `consumes` and `@Content` entries. Do not add media types to OpenAPI if your handler and WebFlux codecs do not yet support those formats.

## 6. Using `@RouterOperations` When a RouterFunction Contains Multiple Routes

A `@Bean` method can return a RouterFunction composed of multiple operations. In that case, a single `@RouterOperation` is not enough to describe all routes. Use `@RouterOperations` to declare each operation:

```java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/customers",
        method = RequestMethod.GET,
        beanClass = CustomerHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "findCustomers",
            summary = "List customers",
            responses = @ApiResponse(responseCode = "200", description = "Customer list")
        )
    ),
    @RouterOperation(
        path = "/api/customers/{id}",
        method = RequestMethod.GET,
        beanClass = CustomerHandler.class,
        beanMethod = "getById",
        operation = @Operation(
            operationId = "getCustomerById",
            summary = "Get customer by ID",
            responses = @ApiResponse(responseCode = "200", description = "Customer")
        )
    )
})
RouterFunction<ServerResponse> customerRoutes(CustomerHandler handler) {
    return RouterFunctions.route()
        .GET("/api/customers", handler::findAll)
        .GET("/api/customers/{id}", handler::getById)
        .build();
}
```

Each `@RouterOperation` represents one path and HTTP method pair. `@RouterOperations` is a container for attaching multiple descriptions to the same bean method. If a bean has only one route, using `@RouterOperation` directly is simpler. If a route group grows large, you can split it into multiple beans to keep metadata and code structure easy to follow.

## 7. Dependency Configuration for WebFlux

An application using Spring WebFlux needs the matching springdoc starter. For Spring Boot 3 and springdoc 2.x, the UI example uses:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

If you only need the OpenAPI JSON/YAML endpoints without Swagger UI, use the `springdoc-openapi-starter-webflux-api` artifact. Pick a springdoc version compatible with Spring Boot and avoid mixing WebFlux and WebMVC starters in the same application unless a special supported architecture requires it.

With Spring Boot 2 and springdoc 1.x, artifact names and configuration differ. Follow the documentation for your major branch instead of copying 2.x dependencies into an older project.

## 8. Inspecting the Generated OpenAPI Document

After starting the application, open `/v3/api-docs` or your configured endpoint. For the GET route in the first example, the document should have a structure similar to:

```yaml
paths:
  /api/customers/{id}:
    get:
      operationId: getCustomerById
      summary: Get customer by ID
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Customer found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CustomerResponse'
        '404':
          description: Customer not found
```

Component names and how springdoc generates `$ref` may vary by version or configuration. Things to confirm:

- Path and method under `paths` match the Router DSL.
- `operationId` is unique within the document.
- Path parameter `id` has `required: true` and a UUID schema.
- Response codes and schemas match handler behavior.
- `produces` and `consumes` reflect actual media types.
- No duplicate or missing operations caused by documenting routes multiple times.

## 9. Verifying Runtime and Documentation Separately

`@RouterOperation` only describes the contract; it does not verify that the runtime route is properly registered. Test actual requests as well:

1. Call `GET /api/customers/{id}` with an existing ID and verify a `200` response with JSON body.
2. Call with a non-existent ID and verify a `404` response as documented.
3. Send a malformed ID and verify the application returns the designed input error.
4. Call `/v3/api-docs` and verify the operation appears with the right path, method, parameters, and responses.
5. If using Swagger UI, try **Try it out** and compare the actual request against the route.

Example verifying the document with `WebTestClient` in a WebFlux application:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CustomerOpenApiTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void documentsFunctionalCustomerRoute() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/customers/{id}'].get.operationId")
            .isEqualTo("getCustomerById");
    }
}
```

This test verifies the documentation. You should also have separate tests for `/api/customers/{id}` to confirm the handler and RouterFunction process real requests.

## 10. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Route works at runtime but is missing from OpenAPI | Missing `@RouterOperation`, annotation on wrong bean method, or springdoc did not detect the functional route | Place the annotation on the `@Bean` method returning RouterFunction and check `/v3/api-docs`. |
| OpenAPI path differs from runtime route | `path` in annotation does not match Router DSL or omitted prefix/nested path | Write the full effective path and compare with real requests. |
| Operation uses the wrong HTTP method | `method` in annotation differs from GET/POST/PUT/DELETE predicate | Sync `RequestMethod` with Router DSL. |
| Path parameter is not documented | Handler accepts only `ServerRequest` so path variable types are not inferred like controllers | Declare `@Parameter` explicitly inside `@Operation`. |
| Response schema is `ServerResponse` or unclear | Handler returns a generic wrapper type | Declare response content and `@Schema(implementation = ...)`. |
| Swagger UI shows the wrong media type | `consumes`/`produces` differs from runtime codecs or predicates | Sync annotations, predicates, and `ServerResponse.contentType(...)`. |
| Multiple routes in one bean produce only one operation | Used a single `@RouterOperation` for a composed RouterFunction | Use `@RouterOperations` or split each route into its own bean. |
| Duplicate operations | Same path/method discovered from multiple configurations or repeated declarations | Inspect annotations and group customizers. |
| `beanMethod` fails to resolve | Wrong method name, wrong handler class, or overloaded methods causing ambiguity | Check `beanClass`, method name, and use distinct handler methods. |
| `/v3/api-docs` errors when resolving routes | Incompatible WebFlux/WebMVC or springdoc dependencies | Use the proper WebFlux starter and a version compatible with Spring Boot. |

## 11. Guidelines for Application

- Use `@RouterOperation` on the `@Bean` method returning a single RouterFunction to document.
- Set `path` and `method` to match the actual route in the Router DSL.
- Link to the proper handler using `beanClass` and `beanMethod`.
- Use `operation` to declare operation ID, summary, tags, parameters, request body, and responses.
- Declare path parameters explicitly when the handler receives `ServerRequest`.
- Document concrete response schemas rather than letting the generic `ServerResponse` type dictate the contract.
- Align `consumes` and `produces` with predicates, codecs, and response content types.
- Use `@RouterOperations` when a single bean method exposes multiple routes.
- Install the right WebFlux starter and a compatible springdoc version.
- Verify both `/v3/api-docs` and runtime requests with `WebTestClient`.

`@RouterOperation` connects routes declared with the WebFlux functional DSL to OpenAPI metadata. When path, method, handler, and operation metadata align, springdoc can publish a clear contract for the route even though the handler does not use controller annotations. The generated specification should still be checked alongside runtime requests to ensure clients see the exact endpoints, parameters, media types, and responses the application actually provides.

## References

- [Springdoc OpenAPI – Official Documentation](https://springdoc.org/)
- [Springdoc OpenAPI FAQ – Functional Endpoints and `@RouterOperation`](https://springdoc.org/faq.html)
- [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework – `RouterFunction`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunction.html)
- [Swagger Annotations – `@Operation` and `@ApiResponse`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
