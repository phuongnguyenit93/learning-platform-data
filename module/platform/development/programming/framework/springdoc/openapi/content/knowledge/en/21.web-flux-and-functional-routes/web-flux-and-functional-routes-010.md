# Identifying Routes by Path, HTTP Method, consumes, and produces

In Spring WebFlux, a functional endpoint is built from router functions and handler functions. The router decides which requests are dispatched to which handler based on the path, HTTP method, and other request conditions. When using springdoc-openapi, these routing conditions must be accurately reflected in OpenAPI so integrators know which endpoints exist, what content types to send, and what content types they can receive.

Four elements must be distinguished:

- **Path** identifies the resource or action being invoked.
- **HTTP method** specifies the operation such as GET, POST, PUT, PATCH, or DELETE.
- **Consumes** describes the request content types accepted by the endpoint, typically based on the Content-Type header.
- **Produces** describes the response content types provided by the endpoint, typically selected via the Accept header and written by the handler.

In functional routing, these elements are commonly combined into a RequestPredicate. In OpenAPI, they are represented as paths, operations, requestBody content, and response content. Documentation must describe the actual runtime route; OpenAPI annotations only supply metadata and do not create or alter routes.

## 1. How Is a Route Identified?

An HTTP request has multiple attributes. The router may inspect one or more attributes before selecting a handler:

| Condition | Data Source | Question |
|---|---|---|
| Path | URI path | Which resource is the request calling? |
| HTTP method | GET, POST, PUT, PATCH, DELETE... | What action does the client want to perform? |
| Consumes | Content-Type header | What format is the submitted body in? |
| Produces | Accept header | What response format does the client accept? |
| Query parameter | Query part of URI | Which filter or pagination parameters are present? |
| Header | HTTP request headers | Does the request satisfy header constraints? |

Example request:

~~~http
POST /api/products HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "name": "Mechanical Keyboard",
  "price": 1250000
}
~~~

The router can match this request if the path is /api/products, the method is POST, Content-Type is compatible with application/json, and Accept indicates the client accepts application/json. Once matched, the handler reads the body, runs business logic, and produces the response.

## 2. Path and HTTP Method Identify an Operation

Path and method together identify an operation. The same path can have multiple operations:

| Path | Method | Meaning |
|---|---|---|
| /api/products | GET | List products |
| /api/products | POST | Create product |
| /api/products/{id} | GET | Get product details |
| /api/products/{id} | PUT | Replace product details |
| /api/products/{id} | DELETE | Delete product |

In OpenAPI, each path is a Path Item, and each method is an Operation inside that Path Item. Thus, GET and POST sharing /api/products are documented as two separate operations.

Do not create two routes with the same path and method differing only by handler without clear distinguishing conditions. If routes differ by media type, query parameter, or header, those conditions must be documented and tested.

## 3. Distinguishing Annotated Controllers from Functional Endpoints

With annotated controllers, Spring WebFlux usually detects routes from annotations:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    Flux<ProductResponse> list() {
        return productService.findAll();
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ProductResponse> create(
            @RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
~~~

Annotations like @GetMapping, @PostMapping, consumes, and produces participate in both Spring's request mapping and springdoc's metadata analysis.

Functional endpoints declare routes with a Java DSL:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/products",
            accept(MediaType.APPLICATION_JSON),
            handler::list
        )
        .POST(
            "/api/products",
            contentType(MediaType.APPLICATION_JSON)
                .and(accept(MediaType.APPLICATION_JSON)),
            handler::create
        )
        .build();
}
~~~

Here routes are not declared with @GetMapping or @PostMapping. Springdoc requires RouterOperation/RouterOperations metadata to bind routes to OpenAPI operations. This is an important difference when documenting functional endpoints.

## 4. Building Routes with RequestPredicate

Spring WebFlux provides built-in predicates in RequestPredicates. Common functions:

| Predicate | Purpose |
|---|---|
| GET(path) | Matches path and HTTP GET |
| POST(path) | Matches path and HTTP POST |
| PUT(path) | Matches path and HTTP PUT |
| PATCH(path) | Matches path and HTTP PATCH |
| DELETE(path) | Matches path and HTTP DELETE |
| path(pattern) | Matches path by pattern |
| contentType(mediaTypes) | Checks the request Content-Type |
| accept(mediaTypes) | Checks the request Accept header |
| headers(predicate) | Checks conditions on request headers |
| queryParam(name, predicate) | Checks query parameters |

Predicates can be composed using and, or, and negate. Example:

~~~java
RequestPredicate jsonRequest =
    contentType(MediaType.APPLICATION_JSON)
        .and(accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> routes =
    RouterFunctions.route(
        POST("/api/products").and(jsonRequest),
        handler::create
    );
~~~

The example above selects the handler only when every condition in the predicate is true. If any condition fails to match, RouterFunction may continue checking other composed routes or result in no matching route.

## 5. Identifying Routes by Path

Paths can be static or contain path variables:

~~~java
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .GET("/api/products/{id}", handler::get)
        .DELETE("/api/products/{id}", handler::delete)
        .build();
}
~~~

Handlers read path variables from ServerRequest:

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    String id = request.pathVariable("id");

    return productService.findById(id)
        .flatMap(product -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(product))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

In OpenAPI, path variables must appear as parameters with location path and marked required. springdoc may infer some metadata from route configurations, but for functional endpoints it is best to declare parameters explicitly in @Operation so the docs have exact names, descriptions, data types, and required flags.

Example documenting a path parameter:

~~~java
@Operation(
    operationId = "getProduct",
    summary = "Get product details",
    parameters = {
        @Parameter(
            name = "id",
            in = ParameterIn.PATH,
            required = true,
            description = "Product identifier."
        )
    }
)
~~~

The parameter name must match the variable in the path, such as {id}. If the path uses {productId} while the documentation declares productID or id, client generators may generate method signatures that do not match the endpoint.

## 6. Identifying Routes by HTTP Method

The HTTP method indicates the kind of operation requested by the client. When declaring functional routes, use specific predicates like GET, POST, PUT, PATCH, and DELETE so a handler does not accidentally match multiple methods.

~~~java
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products/{id}", handler::get)
        .PUT("/api/products/{id}", handler::replace)
        .PATCH("/api/products/{id}", handler::update)
        .DELETE("/api/products/{id}", handler::delete)
        .build();
}
~~~

In OpenAPI, each method is documented individually with its corresponding summary, request body, responses, and security requirements. Do not document a GET route as POST just because the handler performs a write internally; the method in the contract must match the method the router actually accepts.

If the API supports HEAD or OPTIONS, inspect the actual routes and runtime behavior and document them as needed. Do not assume every GET route is documented or handles HEAD identically.

## 7. Consumes Is a Condition on the Request Body

Consumes describes the media types an endpoint accepts from clients. In HTTP, this information usually arrives in the Content-Type header.

Example route accepting only JSON:

~~~java
RouterFunction<ServerResponse> createRoute(ProductHandler handler) {
    return RouterFunctions.route(
        POST("/api/products")
            .and(contentType(MediaType.APPLICATION_JSON)),
        handler::create
    );
}
~~~

A valid request might look like:

~~~http
POST /api/products
Content-Type: application/json

{"name":"Keyboard","price":1250000}
~~~

A request sending Content-Type: text/plain does not satisfy the JSON predicate. In functional routing, contentType is a route-selection predicate. If no fallback route or error handler exists, the request may end up with no matching route; do not assume the predicate automatically generates 415 Unsupported Media Type as in some annotation-mapping cases.

If an API must support multiple body types, declare separate routes or combine predicates intentionally, then document all supported media types under OpenAPI requestBody.content.

## 8. Produces Is a Condition on Response Representation

Produces describes the response types an endpoint can return. Clients commonly send an Accept header listing the media types they can process:

~~~http
GET /api/products
Accept: application/json
~~~

Functional routes can use the accept predicate:

~~~java
RouterFunction<ServerResponse> listRoute(ProductHandler handler) {
    return RouterFunctions.route(
        GET("/api/products")
            .and(accept(MediaType.APPLICATION_JSON)),
        handler::list
    );
}
~~~

The handler must still construct a response with a matching Content-Type:

~~~java
Mono<ServerResponse> list(ServerRequest request) {
    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(productService.findAll(), ProductResponse.class);
}
~~~

The accept predicate checks what media types the client accepts. It does not convert bodies into JSON on its own, nor does it replace setting the response Content-Type. Body serialization also depends on codecs and data types supported by WebFlux.

If Accept is incompatible with the route, the predicate may fail to match and the router will try subsequent routes. If none match, the result may be 404. To return an explicit 406 Not Acceptable, design a fallback or error handler rather than relying on the accept predicate alone.

## 9. Combining Path, Method, consumes, and produces

A product creation endpoint can require all four conditions:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    RequestPredicate jsonInputAndOutput =
        contentType(MediaType.APPLICATION_JSON)
            .and(accept(MediaType.APPLICATION_JSON));

    return RouterFunctions.route()
        .POST("/api/products", jsonInputAndOutput, handler::create)
        .build();
}
~~~

The conditions can be broken down as:

| Component | Value |
|---|---|
| Path | /api/products |
| Method | POST |
| Consumes | application/json |
| Produces | application/json |
| Handler | ProductHandler.create |

Clients must send JSON and accept JSON responses. The handler reads the body into a DTO, invokes business logic, and returns a JSON response. When documented in OpenAPI, the POST operation must specify application/json for both request body content and response content.

Do not advertise one media type in OpenAPI if runtime only supports another. For instance, a route accepting only JSON whose requestBody also advertises XML will lead clients to send unprocessable requests.

## 10. Documenting Functional Routes with @RouterOperation

Springdoc supports documenting functional endpoints via @RouterOperation. This annotation binds a route to the corresponding handler bean and method while supplying OpenAPI operation metadata.

For a single route:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.web.bind.annotation.RequestMethod;

@Bean
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.GET,
    produces = {MediaType.APPLICATION_JSON_VALUE},
    beanClass = ProductHandler.class,
    beanMethod = "list",
    operation = @Operation(
        operationId = "listProducts",
        summary = "List products",
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Product list."
            )
        }
    )
)
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/products",
            accept(MediaType.APPLICATION_JSON),
            handler::list
        )
        .build();
}
~~~

Key attributes:

- path must match the router path.
- method must match the HTTP method accepted by the route.
- consumes describes accepted request media types.
- produces describes response media types.
- beanClass identifies the class containing the handler.
- beanMethod identifies the corresponding handling method.
- operation supplies OpenAPI metadata such as operationId, summary, parameters, request body, responses, and security.

@RouterOperation is metadata for springdoc. If path or method in the annotation differs from the actual route, the documentation may describe a non-existent endpoint or omit a real one.

## 11. Using @RouterOperations for Multiple Routes

A RouterFunction bean often contains multiple routes. In that case, use @RouterOperations to document each operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.web.bind.annotation.RequestMethod;

@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = ProductHandler.class,
        beanMethod = "list",
        operation = @Operation(
            operationId = "listProducts",
            summary = "List products",
            responses = @ApiResponse(
                responseCode = "200",
                description = "Product list."
            )
        )
    ),
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.POST,
        consumes = {MediaType.APPLICATION_JSON_VALUE},
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = ProductHandler.class,
        beanMethod = "create",
        operation = @Operation(
            operationId = "createProduct",
            summary = "Create product",
            responses = @ApiResponse(
                responseCode = "201",
                description = "Product created."
            )
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/products",
            accept(MediaType.APPLICATION_JSON),
            handler::list
        )
        .POST(
            "/api/products",
            contentType(MediaType.APPLICATION_JSON)
                .and(accept(MediaType.APPLICATION_JSON)),
            handler::create
        )
        .build();
}
~~~

Both operations share the same path with different methods, so they must be declared as two separate RouterOperation entries. POST has consumes application/json; both operations declare produces application/json.

When there is a request body, add @Operation(requestBody = ...) with @Content and @Schema to document the DTO. When there are path variables, declare @Parameter with in = ParameterIn.PATH and required = true. Responses should also carry schemas matching the types the handler actually returns.

## 12. Documenting Request Bodies and Response Content

Consumes on @RouterOperation informs springdoc of the request media type. To give the docs a useful request body schema, add metadata inside @Operation:

~~~java
@Operation(
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
            description = "Product created.",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ProductResponse.class)
            )
        )
    }
)
~~~

The annotation snippet above requires @Content and @Schema imports from Swagger annotations. Use the fully qualified name for RequestBody to avoid confusion with Spring's RequestBody annotation.

Schemas must reflect the DTOs that the handler actually reads and returns. If the handler accepts CreateProductRequest while OpenAPI documents ProductResponse as the request body, clients will construct invalid payloads. If the handler returns Mono<ProductResponse> while docs declare a list, the response contract is also inaccurate.

## 13. Multiple Media Types and Alternative Routes

An endpoint can support multiple representations, such as JSON and XML. Predicates can be combined:

~~~java
RequestPredicate jsonOrXml =
    contentType(MediaType.APPLICATION_JSON)
        .or(contentType(MediaType.APPLICATION_XML));

RouterFunction<ServerResponse> routes =
    RouterFunctions.route(
        POST("/api/imports").and(jsonOrXml),
        handler::importData
    );
~~~

The handler must actually be able to decode both formats, usually via the corresponding codecs. Adding an XML predicate does not install an XML decoder or encoder automatically.

For responses, routes can be declared per Accept header:

~~~java
RouterFunction<ServerResponse> exportRoutes(ExportHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/reports",
            accept(MediaType.APPLICATION_JSON),
            handler::asJson
        )
        .GET(
            "/api/reports",
            accept(MediaType.TEXT_CSV),
            handler::asCsv
        )
        .build();
}
~~~

Both routes share the same path and method while differing in Accept predicate. In OpenAPI, this is normally still one GET operation whose response content includes both application/json and text/csv if the same operation supports both representations. Create two separate operations only if they genuinely differ in path or method.

If multiple routes have overlapping predicates, define their ordering and composition clearly. Do not let a broad catch-all route intercept requests ahead of a more specific route.

## 14. Route Ordering and Overlapping Conditions

When composing multiple RouterFunctions, order can affect which route matches if several predicates evaluate to true. Place specific routes before general ones and avoid unnecessary overlapping conditions.

Example placing detailed routes first:

~~~java
RouterFunction<ServerResponse> routes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products/search", handler::search)
        .GET("/api/products/{id}", handler::get)
        .GET("/api/**", handler::fallbackGet)
        .build();
}
~~~

The /api/products/search route has specific semantics. If a catch-all route is placed ahead of it with a broader matching predicate, requests may be dispatched to an unintended handler.

With nested routes or routes composed from multiple modules, inspect the complete final RouterFunction. Do not read individual beans in isolation because composition can alter ordering and matching scope.

## 15. Responding When Media Types Do Not Match

In functional routing, contentType and accept are route-selection predicates. When a predicate fails to match, the router tries the next route; if none match, the request may reach the no-handler-found branch.

This differs from assuming that merely adding consumes or produces causes the framework to always return 415 or 406. If the contract demands explicit status codes, design fallbacks and document those responses.

Example fallback for a POST request to the same path that does not match the JSON route:

~~~java
RouterFunction<ServerResponse> routes(ProductHandler handler) {
    return RouterFunctions.route()
        .POST(
            "/api/products",
            contentType(MediaType.APPLICATION_JSON),
            handler::create
        )
        .route(
            request -> request.method() == HttpMethod.POST
                && request.path().equals("/api/products"),
            handler::unsupportedMediaType
        )
        .build();
}
~~~

The fallback handler can return 415:

~~~java
Mono<ServerResponse> unsupportedMediaType(ServerRequest request) {
    return ServerResponse.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
        .bodyValue("Unsupported Content-Type.");
}
~~~

Similarly, if you want to return 406 when Accept is unsupported, add a fallback matching the path and method after valid media-type routes fail, and return NOT_ACCEPTABLE. Be careful not to let a broad fallback intercept requests already handled by valid routes.

In OpenAPI, document 415 for unsupported request body Content-Type and 406 for unacceptable response representations if runtime actually returns those codes. If runtime returns 404 when no route matches, the documentation must reflect actual behavior or the application must add fallback handling.

## 16. Integrating springdoc with WebFlux Functional Endpoints

For Spring Boot 3 and springdoc 2.x, WebFlux applications typically use the springdoc-openapi-starter-webflux-ui starter. This starter integrates documentation and Swagger UI for WebFlux. Choose the WebFlux starter instead of WebMVC when running on the reactive stack.

Functional endpoints are documented with RouterOperation/RouterOperations. For annotated controllers, springdoc can usually inspect mapping annotations directly. For RouterFunction, verify that metadata annotations cover the intended routes and handlers.

Implementation steps:

1. Create a RouterFunction bean with predicates reflecting path, method, consumes, and produces.
2. Separate handlers into beans with clearly named methods.
3. Attach @RouterOperation or @RouterOperations to the route bean.
4. Declare path, method, consumes, and produces matching the router.
5. Declare request body, path parameters, response schemas, and error responses in @Operation.
6. Start the application and inspect the OpenAPI JSON.
7. Open Swagger UI and test each operation with the matching media types.

If springdoc fails to detect a route, check the starter dependency, annotation placement, beanClass, beanMethod, and version compatibility across Spring Boot, Spring Framework, and springdoc.

## 17. Inspecting the Generated OpenAPI Document

After the application starts, fetch the document:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Inspect paths and methods:

~~~json
{
  "paths": {
    "/api/products": {
      "get": {
        "operationId": "listProducts"
      },
      "post": {
        "operationId": "createProduct",
        "requestBody": {
          "content": {
            "application/json": {}
          }
        }
      }
    }
  }
}
~~~

This snippet illustrates the structure, not full output. In the real document, verify:

- Paths in OpenAPI match registered routes.
- Methods use the right HTTP verbs.
- Path parameters have exact names, locations, and required flags.
- Request body content lists only media types supported by the handler.
- Response content reflects exact media types and schemas.
- operationId is unique across the entire document.
- Error responses such as 400, 404, 406, or 415 are present when supported at runtime.
- Security requirements match the route's policy.

Cross-check OpenAPI JSON against actual runtime behavior. Annotations do not verify that routes work or that handlers serialize the expected format.

## 18. Testing Routes with WebTestClient

WebTestClient can test functional routes without starting a full server:

~~~java
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.reactive.server.WebTestClient.bindToRouterFunction;

class ProductRoutesTest {

    private final WebTestClient client =
        bindToRouterFunction(productRoutes).build();

    @Test
    void createsProductWithJson() {
        client.post()
            .uri("/api/products")
            .contentType(APPLICATION_JSON)
            .accept(APPLICATION_JSON)
            .bodyValue(new CreateProductRequest("Keyboard", 1250000))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON);
    }

    @Test
    void listsProductsAsJson() {
        client.get()
            .uri("/api/products")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON);
    }
}
~~~

The example assumes productRoutes is a RouterFunction configured with an appropriate test service. Add tests for missing paths, unsupported methods, incompatible Content-Type, incompatible Accept, and 406/415 fallbacks if your application implements them.

Besides route tests, write documentation tests: call /v3/api-docs, parse the JSON, and assert paths, methods, consumes, produces, and schemas. The two test suites complement each other: WebTestClient verifies route behavior, while OpenAPI checks verify the published contract.

## 19. Common Pitfalls

| Error | Consequence | Fix |
|---|---|---|
| Declaring only RouterFunction without RouterOperation | Functional routes may not appear completely in OpenAPI | Add @RouterOperation or @RouterOperations |
| Path in annotation differs from runtime path | Documentation points to a non-existent endpoint | Sync paths in router and metadata |
| Wrong method in annotation | Swagger UI sends the wrong HTTP method | Verify RequestMethod against route predicates |
| Missing consumes | Clients do not know which body format is accepted | Declare consumes and requestBody.content |
| Declaring consumes that the handler cannot decode | Requests fail while decoding the body | Verify codecs and DTO types |
| Confusing Accept with Content-Type | Routes match wrong media type conditions | Use contentType for requests and accept for response negotiation |
| Assuming accept predicate automatically returns 406 | Non-matching requests may fall through to 404 | Design a fallback if an explicit 406 is needed |
| Assuming contentType predicate automatically returns 415 | Requests may fail to find a route | Design a fallback if an explicit 415 is needed |
| Handler returns Content-Type mismatching produces | Clients fail to process responses | Set ServerResponse.contentType properly and check codecs |
| Missing path parameter in OpenAPI | Client generators create operations missing parameters | Declare @Parameter with in PATH |
| Overlapping routes | Unintended handler handles requests | Narrow predicates and order specific routes first |
| Documenting one operation per media type for same path/method | Duplicate or malformed documentation | List multiple media types in the same requestBody/response content when appropriate |

## 20. Takeaways

- Path and HTTP method identify the operation matched by the router.
- Consumes relates to the request body's Content-Type.
- Produces relates to Accept and the response media type.
- RequestPredicates supplies path, method, contentType, and accept; combine them with and/or/negate.
- Handlers must read and write the proper media types; predicates do not serialize bodies automatically.
- Functional endpoints need @RouterOperation or @RouterOperations so springdoc binds routes to OpenAPI metadata.
- Path, method, consumes, produces, beanClass, and beanMethod in annotations must match actual routes and handlers.
- Clearly document path parameters, request bodies, response schemas, and error responses.
- Unmatched predicates can route elsewhere or return 404; implement fallbacks if explicit 406/415 statuses are needed.
- Test both routes with WebTestClient and generated documentation at /v3/api-docs.

When building WebFlux functional endpoints, explicitly define the path, HTTP method, accepted request Content-Type, and supported response Accept media types. Then link each route with @RouterOperation so springdoc publishes accurate operations, media types, and schemas. Cross-check OpenAPI JSON with WebTestClient so the documented contract matches actual behavior.
