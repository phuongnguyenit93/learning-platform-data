# @RouterOperations for Multiple Routes in One Bean

Spring WebFlux supports declaring endpoints in two main styles: annotations on controllers and functional routing with **RouterFunction**. With functional routing, a single bean can group multiple GET, POST, PUT, or DELETE routes into one router. Because routes are built with a Java DSL rather than @GetMapping or @PostMapping, springdoc-openapi requires explicit metadata to document each operation in OpenAPI.

The **@RouterOperation** annotation describes one route; **@RouterOperations** groups multiple route descriptions on the same bean method returning RouterFunction. Each entry must match the actual route in path and HTTP method, and can point to the handler method so springdoc can gather additional information.

This lesson explains how to map multiple routes in one bean to multiple OpenAPI operations, declare request/response schemas, spot common mismatches between runtime routes and documentation, and inspect the result at the API docs endpoint.

## 1. How Does Functional Routing Differ from Annotated Controllers?

With annotated controllers, Spring identifies routes from method annotations:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> list() {
        // ...
        return List.of();
    }

    @GetMapping("/{id}")
    public ProductResponse findById(@PathVariable UUID id) {
        // ...
        return null;
    }
}
~~~

springdoc can inspect mappings such as @GetMapping and @PathVariable to generate operations.

With functional routing, routes are created with RouterFunctions:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .GET("/api/products/{id}", handler::findById)
        .POST("/api/products", handler::create)
        .build();
}
~~~

Here, there is no @GetMapping or @PostMapping on the handler to describe the route. Handler methods only accept ServerRequest and return Mono<ServerResponse>. Therefore, OpenAPI metadata must be supplied so tooling knows:

- Which path does the route use?
- Which HTTP method is supported?
- What shape do the request body or parameters have?
- Which status codes and schemas does the response return?
- What summary, description, tags, or security requirements apply to the operation?

## 2. @RouterOperation Describes a Single Route

The **@RouterOperation** annotation links a functional route to an OpenAPI operation. Common attributes:

| Attribute | Meaning |
|---|---|
| path | Full published path of the route |
| method | HTTP method such as GET, POST, PUT, PATCH, or DELETE |
| beanClass | Class containing the referenced handler method |
| beanMethod | Name of the method handling the request |
| consumes | Media types accepted by the operation, e.g., application/json |
| produces | Media types returned by the operation, e.g., application/json |
| operation | @Operation annotation containing detailed OpenAPI metadata |

Single-route example:

~~~java
@Bean
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.GET,
    beanClass = ProductHandler.class,
    beanMethod = "list",
    produces = {MediaType.APPLICATION_JSON_VALUE},
    operation = @Operation(
        operationId = "listProducts",
        summary = "List products",
        description = "Returns the list of available products."
    )
)
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .build();
}
~~~

In this example:

- path and method identify the documented operation.
- beanClass and beanMethod point to the handler processing the route.
- produces describes the response media type.
- operation supplies operationId, summary, and description.

The path in the annotation must be the path clients call after applying route predicates or nested prefixes. Do not put the RouterFunction bean method name in beanMethod if you want springdoc to inspect metadata on the handler class.

## 3. Using @RouterOperations for Multiple Routes in One Bean

When a RouterFunction bean contains multiple routes, place **@RouterOperations** on the bean method and declare one **@RouterOperation** per operation:

Key imports used in the example:

~~~java
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
~~~

~~~java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "list",
        produces = {MediaType.APPLICATION_JSON_VALUE},
        operation = @Operation(
            operationId = "listProducts",
            summary = "List products"
        )
    ),
    @RouterOperation(
        path = "/api/products/{id}",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findById",
        produces = {MediaType.APPLICATION_JSON_VALUE},
        operation = @Operation(
            operationId = "getProductById",
            summary = "Get product by ID"
        )
    ),
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.POST,
        beanClass = ProductHandler.class,
        beanMethod = "create",
        consumes = {MediaType.APPLICATION_JSON_VALUE},
        produces = {MediaType.APPLICATION_JSON_VALUE},
        operation = @Operation(
            operationId = "createProduct",
            summary = "Create product"
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .GET("/api/products/{id}", handler::findById)
        .POST(
            "/api/products",
            RequestPredicates.contentType(MediaType.APPLICATION_JSON),
            handler::create
        )
        .build();
}
~~~

The RouterFunction bean above has three runtime routes:

| Runtime Route | Handler | OpenAPI operationId |
|---|---|---|
| GET /api/products | list | listProducts |
| GET /api/products/{id} | findById | getProductById |
| POST /api/products | create | createProduct |

The GET and POST operations sharing the /api/products path are still two distinct operations because their HTTP methods differ. Each route requires its own @RouterOperation entry inside @RouterOperations.

Do not create a single shared @RouterOperation for all three routes. One OpenAPI operation represents only one path and HTTP method pair.

## 4. Handler Class and beanMethod Must Be Referenced Correctly

Functional routes typically reference methods on a handler bean:

~~~java
@Component
public class ProductHandler {

    public Mono<ServerResponse> list(ServerRequest request) {
        // Read data and return the product list
        return ServerResponse.ok().build();
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        String id = request.pathVariable("id");
        // Look up product by id
        return ServerResponse.ok().build();
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        // Read request body and create product
        return request.bodyToMono(CreateProductRequest.class)
            .flatMap(body -> ServerResponse
                .status(HttpStatus.CREATED)
                .build());
    }
}
~~~

In @RouterOperation:

- beanClass is ProductHandler.class.
- beanMethod is the method name list, findById, or create.

The referenced method must exist on a bean class that springdoc can inspect. If you rename a method in the handler, update beanMethod accordingly.

### Can One Handler Method Serve Multiple Routes?

In Java, multiple routes can point to the same handler method. However, if each route has a distinct contract, consider using separate handler methods or documenting each operation clearly with separate metadata per route.

For instance, two paths might call the same method:

~~~java
RouterFunctions.route()
    .GET("/api/products/featured", handler::findFeatured)
    .GET("/api/products/recommended", handler::findFeatured)
    .build();
~~~

OpenAPI still requires two separate path operations if both URLs are exposed. You can use the same beanClass and beanMethod, but each @RouterOperation needs the exact path and a unique operationId.

## 5. Documenting Request Bodies Since ServerRequest Does Not Expose DTOs Directly

Functional handlers normally take a **ServerRequest** object rather than taking a DTO as a method parameter:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateProductRequest.class)
        .flatMap(product -> productService.create(product)
            .flatMap(saved -> ServerResponse
                .status(HttpStatus.CREATED)
                .bodyValue(saved)));
}
~~~

springdoc cannot tell from the ServerRequest type alone that the actual body is CreateProductRequest. Declare the request body in **@Operation**:

~~~java
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.POST,
    beanClass = ProductHandler.class,
    beanMethod = "create",
    consumes = {MediaType.APPLICATION_JSON_VALUE},
    produces = {MediaType.APPLICATION_JSON_VALUE},
    operation = @Operation(
        operationId = "createProduct",
        summary = "Create product",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(
                    implementation = CreateProductRequest.class
                )
            )
        )
    )
)
~~~

The DTO can declare schemas and constraints:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Schema(description = "Product name", example = "Keyboard")
    String name,

    @NotNull
    @Positive
    @Schema(description = "Product price", example = "1250000")
    BigDecimal price
) {}
~~~

@Schema and Bean Validation annotations describe data structure and constraints. Runtime validation still needs to be triggered in the functional endpoint's processing logic if the app must reject invalid payloads; declaring a schema in @RouterOperation does not invoke the Validator automatically.

## 6. Documenting Path Variables, Query Parameters, and Headers

Handlers receive ServerRequest and read parameters manually:

~~~java
public Mono<ServerResponse> findById(ServerRequest request) {
    UUID id = UUID.fromString(request.pathVariable("id"));
    return productService.findById(id)
        .flatMap(product -> ServerResponse.ok().bodyValue(product));
}

public Mono<ServerResponse> search(ServerRequest request) {
    String keyword = request.queryParam("keyword").orElse("");
    String locale = request.headers()
        .firstHeader("X-Locale");
    // ...
    return ServerResponse.ok().build();
}
~~~

Because parameters do not appear as individual Java method parameters, declare them clearly in **@Operation.parameters**:

~~~java
@Operation(
    operationId = "getProductById",
    summary = "Get product by ID",
    parameters = {
        @Parameter(
            name = "id",
            in = ParameterIn.PATH,
            required = true,
            description = "Product UUID",
            schema = @Schema(type = "string", format = "uuid")
        )
    }
)
~~~

For a query parameter:

~~~java
@Parameter(
    name = "keyword",
    in = ParameterIn.QUERY,
    required = true,
    description = "Search keyword",
    schema = @Schema(type = "string", minLength = 1)
)
~~~

For a header:

~~~java
@Parameter(
    name = "X-Locale",
    in = ParameterIn.HEADER,
    required = false,
    description = "Response language",
    schema = @Schema(type = "string", example = "vi")
)
~~~

Declare parameters on the matching operation in @RouterOperation. Path variables in the path must have a matching path parameter marked required per OpenAPI.

## 7. Documenting Response Schemas and Status Codes

Functional handlers typically return **Mono<ServerResponse>**. This return type does not specify the concrete JSON body emitted by the endpoint. Therefore, document responses using @ApiResponse:

~~~java
@Operation(
    operationId = "getProductById",
    summary = "Get product by ID",
    responses = {
        @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Product not found"
        )
    }
)
~~~

For lists, you can use an array schema:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Product list",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
~~~

For POST creation endpoints, document actual status codes like 201 Created, the response body, and potential validation errors. Do not assume every operation returns 200 when the handler returns 201, 204, or 404.

## 8. Keeping consumes and produces Synchronized with Routes

In @RouterOperation:

- **consumes** describes the request body media types accepted by the operation.
- **produces** describes the response media types.

Example:

~~~java
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.POST,
    consumes = {MediaType.APPLICATION_JSON_VALUE},
    produces = {MediaType.APPLICATION_JSON_VALUE},
    beanClass = ProductHandler.class,
    beanMethod = "create"
)
~~~

This metadata must match the route predicates and how the handler constructs responses:

~~~java
RouterFunctions.route()
    .POST(
        "/api/products",
        RequestPredicates.contentType(MediaType.APPLICATION_JSON)
            .and(RequestPredicates.accept(MediaType.APPLICATION_JSON)),
        handler::create
    )
    .build();
~~~

If the route accepts XML while OpenAPI only declares application/json, clients will misunderstand the contract. If the handler returns text/plain while produces declares application/json, documentation and runtime are out of sync.

## 9. Nested Routes and Effective Paths

RouterFunction instances can be organized with nested routes:

~~~java
RouterFunctions.nest(
    RequestPredicates.path("/api"),
    RouterFunctions.route()
        .GET("/products", handler::list)
        .GET("/products/{id}", handler::findById)
        .build()
);
~~~

The effective paths called by clients are:

- /api/products
- /api/products/{id}

When documenting with @RouterOperations, use the full path after combining nested prefixes. Do not write only /products if the endpoint is actually exposed at /api/products.

For routes using complex path predicates, verify the final path generated in /v3/api-docs. If a route is nested across multiple levels, document the effective path clearly to avoid omitting prefixes.

## 10. Multiple Methods on One Path and OpenAPI Constraints

A single path can support multiple HTTP methods:

~~~text
GET    /api/products
POST   /api/products
DELETE /api/products/{id}
~~~

These are distinct operations. OpenAPI models a path item with one operation per HTTP method. Hence, each path/method pair needs its own operation metadata.

Conversely, if runtime has two routes with the same path and same method differing only by secondary predicates, OpenAPI cannot represent two independent operations under the same path/method pair. For example, two GET /api/products routes differing only by an X-Client-Type header cannot become two distinct GET operations under one path item. You can document the header condition inside the same operation via parameters, or split the endpoint paths if the contract requires a clear distinction.

Do not create duplicate operationId values in the same document. Assign stable, unique operationIds, especially when client generators use them to name generated methods.

## 11. Combining Tags, Security, and Response Metadata

@Operation inside @RouterOperation supports standard OpenAPI metadata:

~~~java
@Operation(
    operationId = "createProduct",
    summary = "Create product",
    description = "Creates a new product in the catalog.",
    tags = {"Products"},
    security = @SecurityRequirement(name = "bearerAuth"),
    responses = {
        @ApiResponse(responseCode = "201", description = "Product created"),
        @ApiResponse(responseCode = "400", description = "Invalid request"),
        @ApiResponse(responseCode = "401", description = "Unauthenticated")
    }
)
~~~

If the document defines a bearerAuth security scheme, the requirement must reference the exact declared scheme name. This annotation only documents the security requirement in OpenAPI; Spring Security must still authenticate runtime requests.

Tags help group operations inside the document. GroupedOpenApi can further filter functional routes by path or package, though groups do not replace @RouterOperation operation metadata.

## 12. Dependency Configuration for WebFlux

A Spring WebFlux application needs the WebFlux-specific springdoc starter, for example in Maven:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

The value 2.x.y is an illustrative placeholder; replace it with a springdoc 2.x version compatible with your project's Spring Boot version. Manage versions via a dependency catalog or centralized property instead of scattering version numbers across modules.

Do not arbitrarily combine WebMVC and WebFlux starters in the same application. Choose the starter matching the active web stack to avoid auto-configuration conflicts.

## 13. Inspecting the Generated Documentation

After the application starts, open the default OpenAPI endpoint:

~~~text
http://localhost:8080/v3/api-docs
~~~

Check the paths and methods:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products"]'
~~~

Expected output includes both get and post:

~~~json
{
  "get": {
    "operationId": "listProducts",
    "summary": "List products"
  },
  "post": {
    "operationId": "createProduct",
    "summary": "Create product"
  }
}
~~~

Check parameterized paths:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products/{id}"].get'
~~~

Verify:

1. Every runtime route meant for publication has a matching path/method.
2. No route has a mismatched path or method.
3. operationId values are unique across the document.
4. Request bodies and parameters have accurate schemas.
5. Response status codes, media types, and schemas reflect the handler.
6. Tags and security requirements reference declared metadata accurately.

If using GroupedOpenApi, inspect each group's document URL rather than checking only /v3/api-docs.

## 14. Testing Runtime Routes and OpenAPI Separately

Test functional routes with WebTestClient:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductRoutesTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void productListRouteResponds() {
        webTestClient.get()
            .uri("/api/products")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void openApiContainsProductOperations() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/products'].get.operationId")
            .isEqualTo("listProducts")
            .jsonPath("$.paths['/api/products'].post.operationId")
            .isEqualTo("createProduct");
    }
}
~~~

The two test groups serve different goals:

- Runtime tests confirm that RouterFunction actually handles requests.
- OpenAPI tests confirm that @RouterOperations produces accurate documentation metadata.

One passing test does not substitute for the other. A route may work at runtime while missing from docs; docs may describe a non-existent route due to stale annotations.

## 15. Common Pitfalls When Using @RouterOperations

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Route runs but is missing from OpenAPI | Missing @RouterOperation or @RouterOperations on bean method | Declare metadata for the route |
| Operation has the wrong path | Annotation does not use the effective path after nested routing | Use the full path and verify /v3/api-docs |
| Operation points to the wrong handler | Mismatched beanClass or beanMethod | Check actual class and method names |
| Renaming handler breaks documentation | beanMethod still holds the old name | Update annotations alongside refactoring |
| Request body lacks a schema | Handler only takes ServerRequest | Declare requestBody and @Schema(implementation = ...) |
| Response shows a generic or empty object | Handler returns Mono<ServerResponse> | Declare explicit ApiResponse and schemas |
| Path variable is not documented | ServerRequest.pathVariable is not a Java method parameter | Add @Parameter with in = PATH |
| Query parameter is missing | Handler reads queryParam from ServerRequest | Declare @Parameter with in = QUERY |
| Incorrect consumes/produces | Metadata does not match route predicate or response | Sync annotations, predicates, and handler |
| Two operations share the same operationId | Copied annotation without changing the ID | Assign unique operationIds |
| Two routes with same path/method create confusing docs | OpenAPI allows only one operation per path/method pair | Merge conditions into one operation or design separate paths |
| GroupedOpenApi omits the route | Path/package filter does not match | Check group filters and the right group document |

## 16. Workflow for Adding a New Route to an Existing Bean

When adding a route to a RouterFunction bean that already holds multiple operations:

1. Add the runtime route via RouterFunctions.route or the appropriate builder.
2. Determine the effective path, HTTP method, consumes, and produces.
3. Identify the actual handler class and handler method.
4. Add a new @RouterOperation entry inside @RouterOperations.
5. Declare operationId, summary, parameters, request body, responses, tags, and security as needed.
6. Verify there are no unintended path/method collisions or duplicate operationIds.
7. Invoke the real route with WebTestClient.
8. Inspect /v3/api-docs or the group document to confirm the operation appears accurately.

Treat route predicates and annotations as two representations of the same contract. Whenever paths, methods, or payloads change, update both and verify the output.

## 17. Maintenance Guidelines

- Place @RouterOperations directly on the RouterFunction bean method so metadata stays close to runtime routes.
- One @RouterOperation per published path/method pair.
- Point beanClass and beanMethod to real handler methods.
- Specify full effective paths after combining nested route prefixes.
- Declare explicit request body and response schemas when handlers use ServerRequest/ServerResponse.
- Document path/query/header parameters explicitly if handlers read them directly from ServerRequest.
- Keep consumes and produces aligned with route predicates and actual responses.
- Use unique, stable operationIds.
- Verify both runtime routes and OpenAPI JSON after every change.
- Do not treat documentation annotations as route registration, validation, or authorization mechanisms.

## Conclusion

**@RouterOperation** documents one functional route; **@RouterOperations** aggregates multiple descriptions on the same bean method returning RouterFunction. Each entry must specify the exact path, HTTP method, and handler class/method, then supply @Operation to document requests, responses, parameters, tags, and security. Because handlers take ServerRequest and return Mono<ServerResponse>, schemas usually need explicit declaration since generic reactive types do not expose concrete payloads. Keep metadata aligned with route predicates, verify effective paths after nested routing, and validate both runtime requests and /v3/api-docs so documentation and actual behavior stay in sync.
