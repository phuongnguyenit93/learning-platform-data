# `operationId` and Schemas That Must Be Declared Explicitly When Inference Is Insufficient

In Spring WebFlux, functional endpoints are typically declared using `RouterFunction<ServerResponse>` and handle requests in handlers returning `Mono<ServerResponse>` or `Mono<Void>`. This style is flexible, but handler signatures often fail to reveal the full HTTP contract. For instance, a `Mono<ServerResponse>` return type does not tell whether the response body is a `ProductResponse`, a list of products, or an error structure. When routes are defined using lambdas or composed from multiple routers, springdoc cannot always infer operation names, parameters, and schemas as it does with annotated controllers.

With springdoc-openapi, you can declare metadata for functional routes using `@RouterOperation` or `@RouterOperations`. Inside that metadata, assign a stable `operationId` and clearly describe requests, responses, content types, and schemas. Documentation generated from these declarations provides a clearer contract for Swagger UI, validators, and client generators.

## 1. Why Do Functional Routes Need Explicit Metadata?

Annotated controllers keep HTTP mappings and OpenAPI descriptions close together:

```java
@GetMapping("/api/products/{id}")
ProductResponse getProduct(@PathVariable UUID id) {
    return productService.getById(id);
}
```

From `@GetMapping`, `@PathVariable`, and the return type, springdoc can infer details such as HTTP method, path parameter, and response schema.

Functional routes are usually declared differently:

```java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/api/products/{id}", handler::getById)
            .build();
}
```

Here, the route is defined in the DSL. The handler accepts `ServerRequest` and builds `ServerResponse` manually. The `Mono<ServerResponse>` signature does not expose the final body type. Path variable info is also read via `request.pathVariable("id")`, so there is no `@PathVariable` for springdoc to inspect.

Therefore, for functional routes, explicitly provide the following parts when reliable inference is not possible:

- HTTP method and path.
- `operationId` and summary.
- Path, query, and header parameters.
- Request body, media types, and schema.
- Response codes, media types, and response schemas.
- Security requirements if the operation requires authentication.

## 2. Role of `@RouterOperation` and `@RouterOperations`

Springdoc provides two primary annotations to bind OpenAPI metadata to functional routes:

| Annotation | Usage |
|---|---|
| `@RouterOperation` | Describes metadata for a single specific route |
| `@RouterOperations` | Groups multiple `@RouterOperation` annotations on a bean declaring multiple routes |

Key attributes of `@RouterOperation` include:

- `path`: route path, which must match the actual route.
- `method`: HTTP method such as `GET`, `POST`, `PUT`, or `DELETE`.
- `beanClass`: class containing the linked handler method.
- `beanMethod`: name of the method handling the route.
- `produces`: response media types, e.g., `application/json`.
- `consumes`: request media types, e.g., `application/json`.
- `operation`: `@Operation` annotation containing `operationId`, descriptions, parameters, request body, responses, and security.

With springdoc-openapi 2.x, router annotations reside in the `org.springdoc.core.annotations` package. The project needs the WebFlux starter matching its installed Spring Boot and springdoc versions.

## 3. `operationId` Is the Operation Identifier

`operationId` is the unique identifier of an operation in an OpenAPI document. SDK generators often use this value to name methods in client code. For example:

```yaml
paths:
  /api/products/{id}:
    get:
      operationId: getProductById
```

An SDK might generate a corresponding method like `getProductById(...)`. If `operationId` changes, the regenerated SDK method name may also change, impacting client source code.

Naming rules to follow:

- Use names describing the action and resource, such as `listProducts`, `getProductById`, `createProduct`.
- Ensure uniqueness within an OpenAPI document.
- Avoid generic names like `handle`, `process`, or `route1`.
- Avoid depending on lambda names or internal method names that easily change.
- Keep it stable when refactoring handler structure without changing the API contract.
- Do not reuse one `operationId` for two different HTTP methods on the same or different paths.

`operationId` is not a URL, not a bean name, and does not replace path/method. It is an identifier in the API contract.

## 4. Linking Metadata to Handler Methods

Example handler with clearly named methods:

```java
import java.net.URI;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
class ProductHandler {

    private final ProductService productService;

    ProductHandler(ProductService productService) {
        this.productService = productService;
    }

    Mono<ServerResponse> list(ServerRequest request) {
        return productService.findAll()
                .collectList()
                .flatMap(products -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(products));
    }

    Mono<ServerResponse> getById(ServerRequest request) {
        UUID id = UUID.fromString(request.pathVariable("id"));
        return productService.findById(id)
                .flatMap(product -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(product))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProductRequest.class)
                .flatMap(productService::create)
                .flatMap(product -> ServerResponse
                        .created(URI.create("/api/products/" + product.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(product));
    }
}
```

`ProductService` is a business service injected into the handler; the example methods return reactive publishers corresponding to product data.

The router bean links each route to its exact handler method:

```java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/api/products", handler::list)
            .GET("/api/products/{id}", handler::getById)
            .POST("/api/products", handler::create)
            .build();
}
```

When documenting OpenAPI, `beanClass` points to `ProductHandler.class`, and `beanMethod` is the matching method name such as `list`, `getById`, or `create`. Placing handlers in beans with clearly named methods makes metadata much easier to link and maintain than defining all logic as anonymous lambdas.

## 5. Declaring `operationId` and Response Schemas for Multiple Routes

The example below documents three product routes using `@RouterOperations`. The metadata sits on the router-creating bean:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "list",
        produces = MediaType.APPLICATION_JSON_VALUE,
        operation = @Operation(
            operationId = "listProducts",
            summary = "List products",
            responses = {
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
            }
        )
    ),
    @RouterOperation(
        path = "/api/products/{id}",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "getById",
        produces = MediaType.APPLICATION_JSON_VALUE,
        operation = @Operation(
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
                @ApiResponse(responseCode = "404", description = "Product not found")
            }
        )
    ),
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.POST,
        beanClass = ProductHandler.class,
        beanMethod = "create",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE,
        operation = @Operation(
            operationId = "createProduct",
            summary = "Create product",
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                required = true,
                content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    schema = @Schema(implementation = CreateProductRequest.class)
                )
            ),
            responses = {
                @ApiResponse(
                    responseCode = "201",
                    description = "Product created",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = ProductResponse.class)
                    )
                ),
                @ApiResponse(responseCode = "400", description = "Invalid data")
            }
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/api/products", handler::list)
            .GET("/api/products/{id}", handler::getById)
            .POST("/api/products", handler::create)
            .build();
}
```

Key points to note:

- Each `@RouterOperation` describes one path and HTTP method pair.
- `path`, `method`, `beanClass`, and `beanMethod` must point to the corresponding route and handler.
- `operationId` is declared explicitly and uniquely.
- The list response uses `@ArraySchema` to represent an array of `ProductResponse`.
- Single responses use `@Schema(implementation = ProductResponse.class)`.
- The `POST` request body references `CreateProductRequest`.
- `produces` and `consumes` describe route media types, while `@Content` describes payload schemas.

If the actual route DSL differs from the metadata, OpenAPI may document the wrong endpoint. Update routes and annotations together.

## 6. Declaring DTO Schemas with `@Schema`

With functional handlers, body schemas should be expressed with concrete DTOs. Example:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Schema(name = "CreateProductRequest", description = "Data for creating a product")
public record CreateProductRequest(
    @Schema(description = "Product name", example = "Mechanical Keyboard")
    @NotBlank
    @Size(max = 120)
    String name,

    @Schema(description = "Selling price", example = "129.90", minimum = "0.01")
    @DecimalMin("0.01")
    BigDecimal price
) {}

@Schema(name = "ProductResponse", description = "Product details")
public record ProductResponse(
    @Schema(description = "Product ID", format = "uuid", example = "8f14e45f-ea4f-4f8d-9b8a-4f4c3a2d1e00")
    UUID id,

    @Schema(description = "Product name", example = "Mechanical Keyboard")
    String name,

    @Schema(description = "Selling price", example = "129.90")
    BigDecimal price,

    @Schema(description = "Creation timestamp", format = "date-time", example = "2026-05-20T10:15:30Z")
    Instant createdAt
) {}
```

`@Schema` describes the name, meaning, format, and example of each field. Bean Validation annotations such as `@NotBlank`, `@Size`, and `@DecimalMin` describe additional input constraints; springdoc can reflect many of these constraints in schemas depending on version and configuration. Even so, runtime validation still needs to be triggered in the application.

Pointing `implementation` to a concrete DTO keeps documentation from having to infer data types from `ServerResponse`. For generic types like `List<ProductResponse>`, use `@ArraySchema` to declare the element schema.

## 7. Declaring Path Parameters Explicitly

Functional handlers usually extract path variables from `ServerRequest`:

```java
String rawId = request.pathVariable("id");
UUID id = UUID.fromString(rawId);
```

Since there is no `@PathVariable`, document the parameter in `@Operation`:

```java
operation = @Operation(
    operationId = "getProductById",
    parameters = {
        @io.swagger.v3.oas.annotations.Parameter(
            name = "id",
            in = io.swagger.v3.oas.annotations.enums.ParameterIn.PATH,
            required = true,
            description = "Product UUID",
            schema = @Schema(type = "string", format = "uuid")
        )
    },
    responses = {
        @ApiResponse(responseCode = "200", description = "Product found")
    }
)
```

The name `id` must match `{id}` in the path. Path parameters are always required in OpenAPI; set `required = true` so metadata reflects that. If the name in the annotation differs from the route variable name, the documentation and actual request will disagree.

## 8. Declaring Query Parameters and Headers

Suppose a handler reads query parameters `page` and `size` via `request.queryParam(...)`. You can document them with `@Parameter`:

```java
parameters = {
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Page number, starting from 0",
        schema = @Schema(type = "integer", minimum = "0", defaultValue = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Number of items per page",
        schema = @Schema(type = "integer", minimum = "1", maximum = "100", defaultValue = "20")
    ),
    @Parameter(
        name = "X-Request-Source",
        in = ParameterIn.HEADER,
        description = "Request origin",
        required = false,
        schema = @Schema(type = "string", example = "admin-console")
    )
}
```

Parameter declarations must accurately reflect how the handler processes requests:

- If `page` is omitted, does the handler actually default to 0?
- If `size` is omitted, what is the runtime default value?
- If `size` exceeds 100, does the handler return an error or cap it?
- Is the header actually read and does it affect business logic?

`defaultValue` in `@Schema` is OpenAPI metadata. It does not automatically assign a value to `ServerRequest`. The handler must apply runtime defaults and validation separately.

## 9. Documenting Request Bodies for POST/PUT/PATCH Routes

With functional endpoints, handlers commonly call `request.bodyToMono(...)`:

```java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateProductRequest.class)
            .flatMap(productService::create)
            .flatMap(product -> ServerResponse
                    .created(URI.create("/api/products/" + product.id()))
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product));
}
```

OpenAPI cannot rely on `Mono<ServerResponse>` to know the body is `CreateProductRequest`. Declare the request body in `@Operation`:

```java
requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Product details to create",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateProductRequest.class)
    )
)
```

For `PUT` or `PATCH`, choose a DTO matching the update semantics. If `PATCH` allows omitting fields, the schema should accurately reflect optional fields and `null` semantics; do not reuse the creation DTO if update rules differ.

## 10. Documenting Response Schemas for `Mono<ServerResponse>`

Handlers can return responses through multiple branches:

```java
Mono<ServerResponse> getById(ServerRequest request) {
    UUID id = UUID.fromString(request.pathVariable("id"));

    return productService.findById(id)
            .flatMap(product -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product))
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

The Java method return type remains `Mono<ServerResponse>`, yet the HTTP response has two cases:

| Status | Body | OpenAPI Description |
|---|---|---|
| `200` | `ProductResponse` | `application/json` with `ProductResponse` schema |
| `404` | No body in this example | Description indicating product not found |

Do not declare only a single `200` response if the handler can return `404`, `400`, `409`, or other statuses. Documentation should list all actual response branches that clients must handle.

## 11. Documenting List Responses and Reactive Publishers

A handler may receive `Flux<ProductResponse>` from the service layer and collect it into a list before writing the response:

```java
Mono<ServerResponse> list(ServerRequest request) {
    return productService.findAll()
            .collectList()
            .flatMap(products -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(products));
}
```

If the HTTP response is a JSON array, the schema must represent an array:

```java
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
```

Do not confuse reactive Java types with JSON structure on the wire. `Mono<T>` usually emits one value; `Flux<T>` can emit many values. Yet the HTTP body can be a JSON object, a JSON array, NDJSON, or Server-Sent Events depending on how the handler writes the response and which media type is selected.

If a route emits `text/event-stream` or `application/x-ndjson`, document the actual media type and event/record structure. Do not describe a stream as a JSON array if clients receive elements in a dedicated streaming format.

## 12. Declaring Errors and Bodyless Responses

A response with no body only needs `description`, without a fake schema. Example:

```java
@ApiResponse(responseCode = "204", description = "Product deleted")
```

For structured errors, use a shared DTO such as `ApiErrorResponse`:

```java
@Schema(name = "ApiErrorResponse", description = "API error details")
public record ApiErrorResponse(
    @Schema(example = "PRODUCT_NOT_FOUND") String code,
    @Schema(example = "Product not found") String message,
    @Schema(format = "date-time") Instant timestamp
) {}
```

Declaring the response:

```java
@ApiResponse(
    responseCode = "404",
    description = "Product not found",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiErrorResponse.class)
    )
)
```

If exception handlers use `ProblemDetail` or another error envelope, declare the schema matching the actual JSON. Do not document `ApiErrorResponse` if runtime returns a different structure.

## 13. Documenting Security Requirements for Functional Routes

Functional routes can still use the same security mechanisms as controller endpoints. You can attach security requirements inside `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@Operation(
    operationId = "deleteProduct",
    summary = "Delete product",
    security = @SecurityRequirement(name = "bearerAuth"),
    responses = {
        @ApiResponse(responseCode = "204", description = "Product deleted"),
        @ApiResponse(responseCode = "401", description = "Unauthenticated"),
        @ApiResponse(responseCode = "403", description = "Insufficient permissions")
    }
)
```

The `bearerAuth` scheme must be declared in `components.securitySchemes` via `@SecurityScheme` or OpenAPI configuration. Security annotations only document the contract; Spring Security must still validate tokens and authorize requests.

If a public route sits inside a document with global security, document that operation as public using an appropriate requirement and verify the `/v3/api-docs` output. Do not assume a route without `@SecurityRequirement` is always public, as it may inherit document-level security.

## 14. Nested Routes and Routers Composed from Multiple Modules

WebFlux applications can split routers by module:

```java
@Bean
RouterFunction<ServerResponse> apiRoutes(
        RouterFunction<ServerResponse> productRoutes,
        RouterFunction<ServerResponse> orderRoutes) {
    return productRoutes.and(orderRoutes);
}
```

Each sub-router can carry its own metadata. When composing routers, ensure metadata annotations sit on beans discoverable by springdoc in your version, and that `path`/`method` still match routes after prefixes or nesting are applied.

With nested routes:

```java
RouterFunctions.route()
    .path("/api/v1", builder -> builder
        .GET("/products/{id}", handler::getById))
    .build();
```

The effective path is `/api/v1/products/{id}`. OpenAPI metadata must describe the effective path called by clients, not only the relative sub-path `/products/{id}`.

If routes are created dynamically from configuration or plugins, consider generating OpenAPI documents via a controlled customizer rather than trying to attach static annotations to non-static routes. Regardless of approach, the final output must be a valid OpenAPI document.

## 15. Inspecting `operationId` and Schemas in OpenAPI Output

After starting the application, download the document:

```bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
```

Inspect operations:

```bash
jq '.paths["/api/products"].get.operationId' openapi.json
jq '.paths["/api/products"].get.responses["200"].content["application/json"].schema' openapi.json
jq '.paths["/api/products"].post.requestBody.content["application/json"].schema' openapi.json
```

Inspect path parameters:

```bash
jq '.paths["/api/products/{id}"].get.parameters' openapi.json
```

Things to confirm in the output:

- Every route has the right HTTP method and path.
- `operationId` exists, has the right name, and is unique.
- Path parameters have names matching the path template and are marked required.
- Query/header parameters have exact locations, types, and defaults/examples.
- Request bodies have the right required flag, media types, and schemas.
- Responses `200`, `201`, `204`, `400`, `404`, etc., have accurate descriptions and schemas.
- Array responses use `type: array` and `$ref` to the element schema.
- All `$ref` pointers resolve to schemas existing in `components.schemas`.

Swagger UI renders results visually, while inspecting raw JSON/YAML directly catches missing metadata or broken links precisely.

## 16. Verifying Route Metadata with Tests

You can write integration tests calling `/v3/api-docs` to assert key fields. Conceptual example with `WebTestClient`:

```java
webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths['/api/products'].get.operationId")
        .isEqualTo("listProducts")
        .jsonPath("$.paths['/api/products'].get.responses['200']")
        .exists();
```

For schemas, you can assert `$ref` and `components.schemas.ProductResponse`. Tests should focus on critical contract guarantees: operationId, request bodies, response schemas, status codes, and security requirements. You do not need to snapshot the entire document if ordering or minor metadata might change without affecting the contract.

Alongside documentation tests, test runtime routes with `WebTestClient`: verify methods/paths, content types, body deserialization, error status mapping, and authorization.

## 17. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Functional route missing from OpenAPI | Missing `@RouterOperation`/`@RouterOperations` or springdoc not detecting router | Check WebFlux starter and metadata on router beans |
| Path exists but `operationId` is missing | `operation.operationId` not declared | Set explicit operationId in `@Operation` |
| Duplicate `operationId` | Reused the same name across multiple routes | Assign unique names across the document and check with a validator |
| Response schema is `ServerResponse` or unclear | Springdoc cannot see bodies constructed dynamically inside handlers | Declare `@Content(schema = @Schema(implementation = ...))` |
| List documented as a single object | Missing `@ArraySchema` | Declare an array schema and element type |
| Request body missing | Handler uses `bodyToMono` without declaring body metadata | Use `@Operation.requestBody` with the DTO schema |
| Path parameter missing from docs | Handler reads from `ServerRequest` | Declare `@Parameter(in = PATH, ...)` |
| Route metadata points to wrong handler | Wrong `beanClass`, `beanMethod`, path, or method | Sync annotations with actual RouterFunction |
| Swagger UI displays wrong content type | `produces`/`consumes` or `@Content.mediaType` mismatch | Verify route media types and actual responses |
| Docs show 200 while runtime returns 404 | Only success response declared | Add all actual response branches |
| Nested route has wrong path in OpenAPI | Metadata specifies only sub-path without prefix | Specify the full effective path clients call |
| Annotations changed yet docs do not update as expected | Cached docs or different group config | Fetch the exact group endpoint and inspect JSON directly |

## 18. Workflow for Designing Routes with Clear Contracts

1. Declare routes with `RouterFunction` and give handler methods clear names.
2. List every HTTP method/path pair and map each to `beanClass`/`beanMethod`.
3. Attach `@RouterOperation` for a single route or `@RouterOperations` for multiple routes.
4. Assign unique, stable `operationId` values meaningful to client generators.
5. Document path/query/header parameters, request bodies, and media types.
6. Declare explicit response codes and schemas; use `@ArraySchema` for arrays.
7. Use dedicated request/response DTOs and add `@Schema` on key fields.
8. Document security requirements and error responses matching runtime.
9. Fetch `/v3/api-docs` and verify `operationId`, `$ref`, parameters, and responses.
10. Run an OpenAPI validator alongside integration tests for both docs and live routes.

## 19. Design Principles

- Treat `RouterFunction` as runtime routing configuration; treat `@RouterOperation` as OpenAPI contract metadata.
- Do not expect `Mono<ServerResponse>` to disclose the body schema on its own.
- Declare stable and unique `operationId` values within the document.
- Keep `path`, `method`, `beanClass`, and `beanMethod` aligned with actual routes and handlers.
- Declare explicit DTO schemas for requests and responses.
- Use `@ArraySchema` for collection responses and document streaming media types properly.
- List every status code the handler can return.
- Keep OpenAPI metadata synchronized with route DSL, validation, and runtime serialization.
- Inspect generated JSON/YAML rather than relying solely on the Swagger UI view.
- Use validators and integration tests to catch duplicate operationIds or invalid schemas.

## Conclusion

Functional routes in Spring WebFlux often lack enough information for springdoc to infer `operationId`, parameters, and body schemas from handler signatures alone. `@RouterOperation` describes a single route; `@RouterOperations` groups metadata for multiple routes. Accurately link path, HTTP method, and handler bean/method, set stable `operationId` values, and declare request/response schemas with `@Schema`, `@Content`, and `@ArraySchema`. When inspecting `/v3/api-docs`, cross-check metadata against the route DSL and actual responses so the OpenAPI contract can be relied upon for Swagger UI, validation, and code generation.
