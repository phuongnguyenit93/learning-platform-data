# `RouterFunction`, Handlers, and Why Extra Metadata Is Needed

Spring WebFlux lets you build endpoints in two main styles: annotated controllers such as `@RestController` and functional endpoints based on `RouterFunction`. With functional endpoints, route predicates determine the HTTP method, path, and request conditions; a handler function takes a `ServerRequest` and produces a `ServerResponse`. This style is flexible, yet details about the HTTP contract are often spread across routes and handlers instead of being centralized on controller annotations.

Springdoc supports documenting functional endpoints via `@RouterOperation` and `@RouterOperations`. These annotations supply OpenAPI details for each route: path, HTTP method, media types, handler method, and `@Operation` metadata such as summary, parameters, request body, responses, tags, or security. As a result, the documentation can clearly describe the contract executed at runtime.

## 1. Three Components of a Functional Endpoint

A WebFlux functional endpoint typically consists of three parts:

| Component | Responsibility |
| --- | --- |
| `RouterFunction<ServerResponse>` | Declares how request predicates map to handlers |
| `HandlerFunction<ServerResponse>` | Processes the request and builds the response asynchronously |
| `ServerRequest` / `ServerResponse` | WebFlux APIs for reading request data and constructing responses |

Simple example:

```java
@Bean
RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .GET("/api/books", handler::findAll)
        .GET("/api/books/{id}", handler::findById)
        .build();
}
```

`GET("/api/books", handler::findAll)` pairs the GET predicate and path with a method reference on the handler. The second route pairs `/api/books/{id}` with `findById`. These route lines themselves do not carry annotations like `@GetMapping`, `@PathVariable`, or `@RequestParam`.

## 2. Handlers Process Requests and Build Responses

A handler is typically a dedicated Spring bean. It receives `ServerRequest`, reads path variables/queries/headers/bodies as needed, calls a service, and returns `Mono<ServerResponse>` per the `HandlerFunction<ServerResponse>` contract.

Example book lookup handler:

```java
package com.example.books;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    private final BookService bookService;

    public BookHandler(BookService bookService) {
        this.bookService = bookService;
    }

    public Mono<ServerResponse> findAll(ServerRequest request) {
        return bookService.findAll()
            .collectList()
            .flatMap(books -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(books));
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return bookService.findById(id)
            .flatMap(book -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(book))
            .switchIfEmpty(ServerResponse.notFound().build());
    }
}
```

In this example, `findAll` returns a list of books as JSON. `findById` reads `id` from the path variable, returns JSON if found, and returns `404 Not Found` if no record exists. Business logic stays in the service; the handler coordinates the request and formats the response.

A response DTO might look like:

```java
public record BookResponse(
    Long id,
    String title
) {}
```

## 3. Why Do Functional Routes Need Extra Metadata?

With annotated controllers, Springdoc can typically read most details directly from method mappings and parameters:

```java
@GetMapping("/api/books/{id}")
public BookResponse findById(@PathVariable long id) { ... }
```

From the annotations and parameter types, Springdoc has what it needs to infer the path, HTTP method, path parameter, and part of the response schema.

In functional endpoints, routing and handling are decoupled:

- The route builder holds the path and HTTP method, without `@GetMapping`.
- Handlers typically take a single `ServerRequest`, so reflection cannot see individual path variables or query parameters as separate Java parameters.
- The handler's return type is usually `Mono<ServerResponse>`, which does not reveal the actual DTO type written into the body.
- `ServerResponse` can be built across multiple branches: JSON, plain text, different status codes, or empty bodies.
- `consumes`, `produces`, header predicates, and business semantics may live in route predicates or handler logic.

Thus, looking solely at the `Mono<ServerResponse>` method signature is insufficient to tell whether the response is `BookResponse`, `List<BookResponse>`, or an empty body. Springdoc needs extra metadata to know how the operation should be documented.

That is why `@RouterOperation` links a route to explicit OpenAPI descriptions. The annotation does not change how the route runs; it adds the contract for documentation and client tooling.

## 4. Documenting a Single Route with `@RouterOperation`

`@RouterOperation` is placed on the `@Bean` method returning `RouterFunction`. It describes one operation and can link to a handler method via `beanClass` and `beanMethod`.

Example for a route listing books:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Bean
@RouterOperation(
    path = "/api/books",
    method = RequestMethod.GET,
    produces = {MediaType.APPLICATION_JSON_VALUE},
    beanClass = BookHandler.class,
    beanMethod = "findAll",
    operation = @Operation(
        operationId = "listBooks",
        summary = "List books",
        description = "Returns the list of books as JSON",
        tags = {"Books"},
        responses = @ApiResponse(
            responseCode = "200",
            description = "List of books",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                array = @ArraySchema(
                    schema = @Schema(implementation = BookResponse.class)
                )
            )
        )
    )
)
public RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .GET("/api/books", handler::findAll)
        .build();
}
```

Key attributes:

| Attribute | Meaning |
| --- | --- |
| `path` | Path of the route being documented |
| `method` | HTTP method such as `GET`, `POST`, `PUT`, `DELETE` |
| `produces` | Advertised response media types |
| `consumes` | Accepted request body media types |
| `headers` | Header conditions if the route restricts by headers |
| `beanClass` | Class containing the linked handler method |
| `beanMethod` | Name of the method handling the route |
| `operation` | Explicit OpenAPI metadata for the operation |

In this example, `beanClass = BookHandler.class` and `beanMethod = "findAll"` help Springdoc associate the operation with the handler method. `@Operation` describes the operationId, summary, tags, and response schema. The response is declared as an array of `BookResponse`, even though the handler's Java return type is `Mono<ServerResponse>`.

## 5. Documenting Multiple Routes with `@RouterOperations`

A `RouterFunction` commonly composes multiple routes. In that case, use `@RouterOperations` to declare metadata for each operation:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.Parameter;
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
        path = "/api/books",
        method = RequestMethod.GET,
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = BookHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "listBooks",
            summary = "List books",
            tags = {"Books"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "List of books",
                content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    array = @ArraySchema(
                        schema = @Schema(implementation = BookResponse.class)
                    )
                )
            )
        )
    ),
    @RouterOperation(
        path = "/api/books/{id}",
        method = RequestMethod.GET,
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = BookHandler.class,
        beanMethod = "findById",
        operation = @Operation(
            operationId = "getBookById",
            summary = "Get book by ID",
            tags = {"Books"},
            parameters = @Parameter(
                name = "id",
                in = ParameterIn.PATH,
                required = true,
                description = "Book ID",
                schema = @Schema(type = "integer", format = "int64", example = "42")
            ),
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Book found",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = BookResponse.class)
                    )
                ),
                @ApiResponse(
                    responseCode = "404",
                    description = "Book not found"
                )
            }
        )
    )
})
public RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .GET("/api/books", handler::findAll)
        .GET("/api/books/{id}", handler::findById)
        .build();
}
```

Each `@RouterOperation` corresponds to a route predicate. Ensure `path`, `method`, `beanClass`, and `beanMethod` match the actual route and handler. If any of these values are missing or wrong, the documentation may omit an operation or attach metadata to the wrong endpoint.

In this example, the list response is represented using `@ArraySchema` with `BookResponse` elements so OpenAPI accurately reflects the array type and each item's schema.

## 6. Documenting Path, Query, and Header Parameters

Functional handlers read parameters from `ServerRequest`, so parameters usually cannot be inferred from Java method signatures as in annotated controllers.

Example handler reading query parameters:

```java
public Mono<ServerResponse> search(ServerRequest request) {
    String keyword = request.queryParam("q").orElse("");
    int page = request.queryParam("page")
        .map(Integer::parseInt)
        .orElse(0);

    return bookService.search(keyword, page)
        .collectList()
        .flatMap(results -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(results));
}
```

In `@Operation` metadata, declare parameters explicitly:

```java
parameters = {
    @Parameter(
        name = "q",
        in = ParameterIn.QUERY,
        required = false,
        description = "Search keyword",
        schema = @Schema(type = "string", example = "spring")
    ),
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        required = false,
        description = "Page number, starting from 0",
        schema = @Schema(type = "integer", minimum = "0", example = "0")
    )
}
```

Common parameter locations include `PATH`, `QUERY`, `HEADER`, and `COOKIE`. Path parameters must be declared `required = true` in OpenAPI. Parameter names must match the names the handler actually reads via `pathVariable`, `queryParam`, `headers`, or cookies.

If a route has a header predicate—for example matching only `X-API-VERSION=v2`—document that condition in the appropriate metadata and consider declaring a header parameter so clients know how to invoke it. An OpenAPI header parameter does not create a routing rule on its own; the runtime route predicate must still be declared separately.

## 7. Documenting Request Bodies and Responses

Because handlers typically accept `ServerRequest`, Springdoc cannot always infer DTO types from a `@RequestBody` parameter. When a route accepts a body, declare the request body in `@Operation` using OpenAPI annotations:

```java
requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
    required = true,
    description = "Book details to create",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateBookRequest.class)
    )
)
```

Similarly, responses must declare actual status codes, media types, and schemas. For instance, a handler might return `201 Created` with `BookResponse`, `400 Bad Request` with an error DTO, and `409 Conflict` when the book code already exists. These branches should be represented with multiple `@ApiResponse` entries.

Do not declare a schema based solely on `Mono<ServerResponse>`. Inspect what body the handler actually writes via `bodyValue`, `body`, `bodyToMono`, or other serialization mechanisms. If a response has no body, declare only status and description without adding fake content.

## 8. Documenting `consumes` and `produces`

Functional routes can restrict media types via predicates or inspect headers in handlers. `@RouterOperation` metadata can describe request/response media types so OpenAPI expresses the true contract.

Example route accepting JSON:

```java
return RouterFunctions.route()
    .POST("/api/books", RequestPredicates.contentType(MediaType.APPLICATION_JSON), handler::create)
    .build();
```

`RequestPredicates.contentType(...)` matches the request `Content-Type` and corresponds to accepting JSON (`consumes`). `RequestPredicates.accept(...)` matches the `Accept` header and corresponds to choosing the response representation (`produces`). For example, if you want a route to handle only requests with a JSON body where the client accepts JSON, you can combine both predicates:

```java
RequestPredicates.contentType(MediaType.APPLICATION_JSON)
    .and(RequestPredicates.accept(MediaType.APPLICATION_JSON))
```

For a route accepting JSON bodies, ensure the handler actually validates/reads the body and runtime only accepts the intended media type. In `@RouterOperation`, declare `consumes = {MediaType.APPLICATION_JSON_VALUE}`; for JSON responses, declare `produces = {MediaType.APPLICATION_JSON_VALUE}`.

Do not confuse `consumes` with `produces`:

| Attribute | Meaning |
| --- | --- |
| `consumes` | Request body format accepted by the operation |
| `produces` | Response body format returned by the operation |

Metadata does not install `HttpMessageReader`, `HttpMessageWriter`, or converters. If an application declares `application/xml` without an XML codec configured, the documentation will advertise a capability that runtime cannot execute.

## 9. Documenting Security for Functional Routes

`@Operation` inside `@RouterOperation` supports `security` just like an annotated controller operation:

```java
operation = @Operation(
    operationId = "listBooks",
    summary = "List books",
    security = @SecurityRequirement(name = "bearerAuth"),
    responses = @ApiResponse(responseCode = "200", description = "Success")
)
```

The `bearerAuth` scheme must be declared in `components.securitySchemes`, for example using `@SecurityScheme`. The referenced name must match the scheme name exactly.

Security metadata only documents security requirements in OpenAPI. WebFlux Security must still configure `SecurityWebFilterChain`, validate tokens, and enforce authorization on actual requests. Do not treat documentation annotations as an access control mechanism.

## 10. Linking Routes to Handlers with `beanClass` and `beanMethod`

These two attributes are helpful when routes use method references or separately declared handler functions:

```java
@RouterOperation(
    path = "/api/books/{id}",
    method = RequestMethod.GET,
    beanClass = BookHandler.class,
    beanMethod = "findById",
    operation = @Operation(summary = "Get book by ID")
)
```

`beanClass` identifies the class containing the handler method; `beanMethod` is the method name. Together they let Springdoc locate the matching method to connect route metadata with the handler. The method name must match the actual Java method.

If there are multiple overloaded methods with the same name or if handlers are created as inline lambdas, binding can become ambiguous. In those cases, extract handlers into clearly named methods and declare explicit metadata for each route. This also makes unit testing handlers and maintaining docs much easier.

## 11. When to Use `@RouterOperation` vs. a Customizer?

| Mechanism | Best Used When |
| --- | --- |
| `@RouterOperation` | Explicitly documenting a single functional route |
| `@RouterOperations` | Documenting multiple routes composed in one `RouterFunction` bean |
| Nested `@Operation` | Supplying summary, tags, parameters, request body, responses, security, and operation metadata |
| `OpenApiCustomizer` | Adjusting the whole document after Springdoc builds the OpenAPI model |

For functional endpoints, `@RouterOperation` is usually the most direct way to bind route predicates and handlers to operations. `OpenApiCustomizer` fits document-wide adjustments or broad conventions, though it does not directly receive handler methods like route-level metadata does.

Do not assume an `OperationCustomizer` meant for annotated controllers works on functional routes. That extension point ties into Spring MVC's `HandlerMethod`; WebFlux functional routes do not necessarily have a corresponding `HandlerMethod`. Use dedicated route annotations or OpenAPI-level customizers depending on your goal.

## 12. Common Pitfalls When Documenting Functional Endpoints

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Route runs but is missing from OpenAPI | Missing `@RouterOperation` or route metadata configuration not detected | Place annotations on the `RouterFunction` bean and verify path/method |
| Operation appears with empty/generic response schema | Handler returns `Mono<ServerResponse>` so body type cannot be inferred | Declare response schemas with `@ApiResponse` and `@Schema` |
| Path parameter is not documented | Handler reads `request.pathVariable()` instead of taking `@PathVariable` | Declare `@Parameter(in = PATH, required = true)` |
| Query parameter is missing | Handler reads `request.queryParam()` | Declare `QUERY` parameters in `@Operation` |
| Metadata bound to wrong handler | Incorrect `beanClass` or `beanMethod` | Cross-check actual class and method names |
| Wrong path or method in documentation | `@RouterOperation` does not match route predicate | Sync `path` and `method` with RouterFunction |
| Request body has wrong schema | Handler reads body manually without `requestBody` metadata | Declare content, media type, and DTO schema |
| Swagger UI shows JSON while runtime returns XML | `produces` or response content mismatches codecs/handler | Align metadata with `ServerResponse` and actual codecs |
| Security not displayed | Missing `security` on operation or undeclared scheme | Declare matching scheme and requirement names |
| Used `OperationCustomizer` without a handler method | Functional route lacks a Spring MVC `HandlerMethod` | Use `@RouterOperation` or `OpenApiCustomizer` instead |

## 13. Inspecting OpenAPI Generated from Functional Routes

After starting the application, open `/v3/api-docs` or the corresponding group document. Verify:

1. Every expected `RouterFunction` route appears under `paths`.
2. HTTP methods match the route predicates.
3. Path parameters are fully declared and required.
4. Query/header parameters have accurate names, locations, types, and descriptions.
5. `requestBody.content` matches the media type and DTO read by the handler.
6. `responses` reflect actual status codes and bodies.
7. Schemas reference the real DTOs rather than merely showing a `ServerResponse` type.
8. Tags, operationId, and security requirements have the right values.

At the same time, invoke the endpoint using an HTTP client or WebTestClient. Example:

```java
webTestClient.get()
    .uri("/api/books/42")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(42);
```

Verify runtime and OpenAPI together: accurate docs do not prove the handler executes correctly, and a working endpoint does not prove the docs fully describe the contract.

## 14. Checklist for `RouterFunction` and Handlers

- [ ] Route predicates clearly specify HTTP method, path, and request conditions.
- [ ] Handlers have dedicated, clearly named methods and process `ServerRequest`/`ServerResponse` per contract.
- [ ] `@RouterOperation` or `@RouterOperations` is placed on the appropriate `RouterFunction` bean.
- [ ] `path` and `method` match runtime route predicates.
- [ ] `beanClass` and `beanMethod` reference the right handler.
- [ ] `@Operation` documents summary, operationId, tags, and security when needed.
- [ ] Path/query/header parameters are declared explicitly when handlers read directly from `ServerRequest`.
- [ ] Request bodies specify media types and schemas matching the DTO.
- [ ] Responses include status codes, media types, and schemas for each branch.
- [ ] `consumes`/`produces` match predicates, codecs, and actual responses.
- [ ] Security schemes are declared and requirements reference exact names.
- [ ] Inspected `/v3/api-docs` and tested routes with WebTestClient or an HTTP client.

`RouterFunction` defines routing, handlers define request processing, and OpenAPI defines the client-facing contract. Because functional endpoints do not rely on mapping annotations on parameters and typically return `Mono<ServerResponse>`, teams need to supply metadata with `@RouterOperation` or `@RouterOperations`. When metadata aligns with actual routes and handlers, Springdoc can produce complete documentation covering paths, methods, parameters, bodies, responses, and security for WebFlux applications.
