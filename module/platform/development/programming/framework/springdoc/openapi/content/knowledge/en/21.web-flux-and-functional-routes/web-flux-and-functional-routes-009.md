# Linking beanClass, beanMethod, and Handler Signatures

With Spring WebFlux functional endpoints, routes are declared using a <code>RouterFunction</code> instead of mapping annotations on controllers. springdoc-openapi cannot always infer full operation details from route predicates and method references, so routes must be explicitly documented with <code>@RouterOperation</code> or <code>@RouterOperations</code>.

The two attributes <code>beanClass</code> and <code>beanMethod</code> link an OpenAPI operation to the actual handling method. <code>beanClass</code> identifies the class containing the handler; <code>beanMethod</code> identifies the method within that class. Combined with <code>path</code>, HTTP method, and metadata in <code>@Operation</code>, springdoc can attach documentation to the right functional route.

Functional handlers typically accept a <code>ServerRequest</code> object and return <code>Mono&lt;ServerResponse&gt;</code>. This signature does not directly expose request/response DTOs the way a conventional controller method does. Therefore, parameters, request bodies, and response schemas must be declared explicitly whenever data types cannot be inferred from the handler signature.

## 1. Functional Routes Consist of Route Predicates and Handlers

In WebFlux, a functional endpoint generally has two parts:

- **Route predicate** specifies HTTP method, path, content type, or request conditions.
- **Handler function** receives <code>ServerRequest</code>, processes the request, and builds a <code>ServerResponse</code>.

Example route:

~~~java
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/products/{id}"),
        handler::getById
    );
}
~~~

The predicate <code>GET("/products/{id}")</code> selects matching requests. The method reference <code>handler::getById</code> dispatches the request to the handler. Because the method reference does not carry OpenAPI metadata such as summary, response schema, or operation name, we must link and document it separately.

## 2. Role of beanClass and beanMethod

Inside <code>@RouterOperation</code>:

| Attribute | Meaning | Example |
|---|---|---|
| <code>path</code> | Route path published in OpenAPI | <code>/products/{id}</code> |
| <code>method</code> | HTTP method of the route | <code>RequestMethod.GET</code> |
| <code>beanClass</code> | Spring bean class containing the handler method | <code>ProductHandler.class</code> |
| <code>beanMethod</code> | Name of the request-handling method in the bean class | <code>"getById"</code> |
| <code>produces</code> | Response media type produced by the route | <code>application/json</code> |
| <code>consumes</code> | Request media type accepted by the route | <code>application/json</code> |
| <code>operation</code> | Additional OpenAPI metadata for the operation | <code>@Operation(...)</code> |

<code>beanClass</code> is the class of the invoked handler, not necessarily the configuration class containing the <code>@Bean</code> method. <code>beanMethod</code> is the method name in the handler class, not the name of the factory method creating the <code>RouterFunction</code>.

For example, if the route is registered with <code>handler::getById</code>, the binding is:

~~~java
beanClass = ProductHandler.class,
beanMethod = "getById"
~~~

Do not pass the string <code>"handler::getById"</code> to <code>beanMethod</code>. This attribute expects the Java method name so springdoc can look up handler metadata.

## 3. Documenting a Single Route with @RouterOperation

For a single functional route in a bean method, you can use <code>@RouterOperation</code>:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
class ProductRoutes {

    @Bean
    @RouterOperation(
        path = "/products/{id}",
        method = RequestMethod.GET,
        produces = {"application/json"},
        beanClass = ProductHandler.class,
        beanMethod = "getById",
        operation = @Operation(
            operationId = "getProductById",
            summary = "Get product by ID",
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Product found",
                    content = @Content(
                        mediaType = "application/json",
                        schema = @Schema(
                            implementation = ProductResponse.class
                        )
                    )
                ),
                @ApiResponse(
                    responseCode = "404",
                    description = "Product not found"
                )
            }
        )
    )
    RouterFunction<ServerResponse> productRoute(ProductHandler handler) {
        return RouterFunctions.route(
            RequestPredicates.GET("/products/{id}"),
            handler::getById
        );
    }
}
~~~

Here, <code>path</code> and <code>method</code> describe the HTTP route. <code>beanClass</code> and <code>beanMethod</code> identify the handling method. <code>operation</code> adds operationId, summary, and response schemas.

The <code>path</code> and <code>method</code> values in the annotation must match the predicate in the route builder. If the annotation documents GET while the actual route is POST, the documentation will not accurately reflect the API.

## 4. Documenting Multiple Routes with @RouterOperations

A <code>RouterFunction</code> can compose multiple routes using <code>andRoute</code> or a builder. When doing so, use <code>@RouterOperations</code> to declare one operation per route:

The example below is an alternative configuration to the single-route example above. In your project, keep one route bean matching the actual number of routes; do not declare two beans registering the same path/method.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
class ProductRoutes {

    @Bean
    @RouterOperations({
        @RouterOperation(
            path = "/products/{id}",
            method = RequestMethod.GET,
            produces = MediaType.APPLICATION_JSON_VALUE,
            beanClass = ProductHandler.class,
            beanMethod = "getById",
            operation = @Operation(
                operationId = "getProductById",
                summary = "Get product by ID",
                parameters = {
                    @Parameter(
                        name = "id",
                        in = ParameterIn.PATH,
                        required = true,
                        description = "Product ID",
                        schema = @Schema(type = "string")
                    )
                },
                responses = {
                    @ApiResponse(
                        responseCode = "200",
                        description = "Product found",
                        content = @Content(
                            mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(
                                implementation = ProductResponse.class
                            )
                        )
                    ),
                    @ApiResponse(
                        responseCode = "404",
                        description = "Product not found"
                    )
                }
            )
        ),
        @RouterOperation(
            path = "/products",
            method = RequestMethod.POST,
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE,
            beanClass = ProductHandler.class,
            beanMethod = "create",
            operation = @Operation(
                operationId = "createProduct",
                summary = "Create product",
                requestBody = @RequestBody(
                    required = true,
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(
                            implementation = CreateProductRequest.class
                        )
                    )
                ),
                responses = {
                    @ApiResponse(
                        responseCode = "201",
                        description = "Product created",
                        content = @Content(
                            mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(
                                implementation = ProductResponse.class
                            )
                        )
                    ),
                    @ApiResponse(
                        responseCode = "400",
                        description = "Invalid request"
                    )
                }
            )
        )
    })
    RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
        return RouterFunctions.route(
                RequestPredicates.GET("/products/{id}"),
                handler::getById
            )
            .andRoute(
                RequestPredicates.POST("/products")
                    .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON)),
                handler::create
            );
    }
}
~~~

In this example, the same route bean exposes two operations:

- GET <code>/products/{id}</code> links to <code>ProductHandler.getById</code>.
- POST <code>/products</code> links to <code>ProductHandler.create</code>.

Each <code>@RouterOperation</code> must document the exact path, method, bean class, and bean method of its corresponding route. Do not share one <code>@RouterOperation</code> across multiple routes with different signatures or schemas.

## 5. Handler Signatures and What springdoc Can Infer

A functional handler typically has the form:

~~~java
Mono<ServerResponse> getById(ServerRequest request)
~~~

or:

~~~java
ServerResponse health(ServerRequest request)
~~~

With reactive handlers, the outermost return type is <code>Mono&lt;ServerResponse&gt;</code>. The actual DTO may be constructed inside <code>ServerResponse.bodyValue(...)</code> or <code>body(...)</code>, without appearing in the method's generic return type.

Therefore, do not expect springdoc to infer the entire contract from the signature alone:

| Component | What the Handler Signature Shows | How to Document When Needed |
|---|---|---|
| Path variable | Inside <code>ServerRequest</code> | Declare <code>@Parameter(in = PATH)</code> |
| Query parameter | Read via <code>request.queryParam(...)</code> | Declare <code>@Parameter(in = QUERY)</code> |
| Header | Read from <code>request.headers()</code> | Declare <code>@Parameter(in = HEADER)</code> if part of the contract |
| Request body | Read via <code>bodyToMono(...)</code> or <code>bodyToFlux(...)</code> | Declare <code>requestBody</code> and schema |
| Response body | Wrapped in <code>ServerResponse</code> | Declare response content and schema |
| Status code | Chosen via <code>ServerResponse.ok()</code>, <code>created()</code>, <code>notFound()</code>... | Declare each <code>@ApiResponse</code> |

This is an important distinction between functional endpoints and controller methods taking DTOs directly. The handler signature still needs linking via <code>beanClass</code>/<code>beanMethod</code>, while payload schemas generally must be added via <code>@Operation</code>.

## 6. Example of a Handler with Clear Signatures

A handler can be a standalone Spring bean:

~~~java
import java.net.URI;

import org.springframework.stereotype.Component;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
class ProductHandler {

    private final ProductService service;

    ProductHandler(ProductService service) {
        this.service = service;
    }

    public Mono<ServerResponse> getById(ServerRequest request) {
        String id = request.pathVariable("id");

        return service.findById(id)
            .flatMap(product ->
                ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product)
            )
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProductRequest.class)
            .flatMap(service::create)
            .flatMap(product ->
                ServerResponse.created(
                        URI.create("/products/" + product.productId())
                    )
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product)
            );
    }
}

interface ProductService {
    Mono<ProductResponse> findById(String id);
    Mono<ProductResponse> create(CreateProductRequest request);
}

record CreateProductRequest(String name, Integer price) {}

record ProductResponse(String productId, String name, Integer price) {}
~~~

In this example:

- <code>getById</code> reads the path variable via <code>request.pathVariable("id")</code>.
- <code>create</code> reads the JSON body as <code>CreateProductRequest</code>.
- Both methods return <code>Mono&lt;ServerResponse&gt;</code>, even though the actual payload is <code>ProductResponse</code>.
- GET can return 200 or 404; POST can return 201 or a request error.

When declaring <code>@RouterOperation</code>, specify the response schema as <code>ProductResponse</code> and request schema as <code>CreateProductRequest</code>. Relying solely on <code>Mono&lt;ServerResponse&gt;</code> may leave the documentation without body schemas.

## 7. Documenting Path, Query, and Header Parameters

Handlers take a single <code>ServerRequest</code>, so path/query/header values do not appear as separate Java parameters. Declare them under <code>@Operation.parameters</code>.

Example search route:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Parameter;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.web.bind.annotation.RequestMethod;

@RouterOperation(
    path = "/products",
    method = RequestMethod.GET,
    beanClass = ProductHandler.class,
    beanMethod = "search",
    operation = @Operation(
        operationId = "searchProducts",
        parameters = {
            @Parameter(
                name = "keyword",
                in = ParameterIn.QUERY,
                required = false,
                description = "Search keyword",
                schema = @Schema(type = "string")
            ),
            @Parameter(
                name = "page",
                in = ParameterIn.QUERY,
                required = false,
                description = "Page number starting from 0",
                schema = @Schema(type = "integer", minimum = "0")
            ),
            @Parameter(
                name = "X-Tenant-Id",
                in = ParameterIn.HEADER,
                required = true,
                description = "Tenant identifier",
                schema = @Schema(type = "string")
            )
        }
    )
)
~~~

The parameters in the annotation must correspond to how the handler reads data:

~~~java
Mono<ServerResponse> search(ServerRequest request) {
    String keyword = request.queryParam("keyword").orElse("");
    int page = request.queryParam("page")
        .map(Integer::parseInt)
        .orElse(0);
    String tenantId = request.headers()
        .firstHeader("X-Tenant-Id");
    // ...
}
~~~

If a parameter is required, the handler or validation layer must actually reject requests missing that value. <code>required = true</code> only documents the OpenAPI contract; it does not add validation to functional routes.

Do not declare technical headers such as <code>Host</code>, <code>Content-Length</code>, or browser-managed headers as regular business parameters. For authentication headers, prefer documenting them with security schemes.

## 8. Documenting Request Bodies and Response Bodies

With functional handlers, the request body is usually read inside the method. Declare the schema in <code>@Operation.requestBody</code>:

~~~java
requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
    required = true,
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = CreateProductRequest.class)
    )
)
~~~

Response bodies must be declared inside each <code>@ApiResponse</code>:

~~~java
responses = {
    @ApiResponse(
        responseCode = "201",
        description = "Product created",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request data"
    )
}
~~~

If a response is <code>204 No Content</code>, do not declare a body schema. If a response returns a list, use an array schema or the matching pagination DTO. If there are multiple status codes, declare each separately so consumers know which body may appear.

## 9. Reading Handler Signatures and Choosing Bean Method Styles

springdoc must locate the right method in the class specified by <code>beanClass</code>. Therefore:

- <code>beanClass</code> must point to the exact handler class.
- <code>beanMethod</code> must match the Java method name.
- Methods should have unique, easily recognizable names.
- The handler bean must be Spring-managed and used to build the route.
- If overloaded methods share the same name, metadata lookup can become ambiguous; rename handler methods so each route has its own method.

Examples of clear names:

~~~java
Mono<ServerResponse> getProductById(ServerRequest request)
Mono<ServerResponse> createProduct(ServerRequest request)
Mono<ServerResponse> searchProducts(ServerRequest request)
~~~

Then use the exact method name in the annotation:

~~~java
beanClass = ProductHandler.class,
beanMethod = "getProductById"
~~~

The method name is not the operationId. <code>beanMethod</code> links to the Java handler; <code>operationId</code> is the OpenAPI operation identifier and should follow the project's client code generation conventions.

## 10. When to Use @RouterOperation vs. @RouterOperations?

| Case | Suitable Annotation |
|---|---|
| A single route registered in a bean method | <code>@RouterOperation</code> |
| Multiple routes composed in one <code>RouterFunction</code> bean | <code>@RouterOperations</code> |
| A route needing detailed operation metadata | Place <code>@Operation</code> in the <code>operation</code> attribute |
| Route with parameters/body/responses not inferable from handler | Declare explicitly inside <code>@Operation</code> |

You do not need a separate handler class for every route, though organizing methods cleanly makes linking clear. If a handler class has multiple methods, declare each <code>@RouterOperation</code> with its matching <code>beanMethod</code>.

For nested routes or routes built via helper functions, annotations must still describe the final published path and method. If routes are generated dynamically from runtime config, verify springdoc can see those routes; when it cannot, consider populating OpenAPI via a controlled customizer or suitable static docs config.

## 11. Inspecting the Generated OpenAPI Document

After starting the application, visit the default endpoint:

~~~text
http://localhost:8080/v3/api-docs
~~~

For each functional route, verify:

1. Path and HTTP method match the route predicate.
2. <code>operationId</code> and summary accurately describe the operation.
3. Path/query/header parameters have exact names, locations, and required flags.
4. Request body has the media type and schema matching what the handler reads.
5. Responses have exact status codes, media types, and body schemas.
6. No duplicate or missing operations due to route composition.
7. <code>beanClass</code> and <code>beanMethod</code> link to the right handler.

An expected OpenAPI excerpt for the create-product route may look like:

~~~yaml
paths:
  /products:
    post:
      operationId: createProduct
      summary: Create product
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateProductRequest"
      responses:
        "201":
          description: Product created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "400":
          description: Invalid request
~~~

Then open Swagger UI and run Try it out in a test environment. Verify the actual request hits the right path, method, content type, and body. Compare the runtime response against the generated schema.

## 12. Common Pitfalls

**Using the route bean method name instead of the handler method.** <code>beanMethod</code> must be the request-handling method in <code>beanClass</code>, not the <code>@Bean</code> method returning <code>RouterFunction</code>.

**Setting the wrong beanClass.** If <code>beanClass</code> points to the route configuration class instead of the class containing the handler method, springdoc will not find the desired signature.

**Non-existent or overloaded beanMethod name.** Use the exact method name and prefer a unique method name per route.

**Path or HTTP method does not match the predicate.** Cross-check <code>@RouterOperation.path</code>/<code>method</code> with <code>RequestPredicates</code> or the actual builder.

**Relying solely on ServerRequest to generate parameters.** Path/query/header values are read dynamically inside the handler; declare them explicitly with <code>@Parameter</code> in the operation.

**Missing response schema.** <code>Mono&lt;ServerResponse&gt;</code> does not disclose the DTO written to the body; declare schemas using <code>@ApiResponse</code>.

**Request body missing a schema.** When the handler calls <code>bodyToMono</code>, declare <code>requestBody</code> and the matching schema.

**Annotation documents a route missing from predicates.** OpenAPI metadata does not register runtime routes. Ensure the route builder actually registers the endpoint.

**A RouterFunction has multiple routes but only one operation is documented.** Use <code>@RouterOperations</code> and list each route to publish.

**Documentation and runtime diverge.** Check both <code>/v3/api-docs</code> and real requests in WebTestClient or Swagger UI.

## 13. Pre-Publication Review Checklist

- [ ] Every functional route has matching OpenAPI metadata.
- [ ] <code>beanClass</code> points to the exact handler class.
- [ ] <code>beanMethod</code> points to the exact request-handling method.
- [ ] Handler method names are clear, without overload ambiguity.
- [ ] Path and HTTP method match the route predicate.
- [ ] Parameters are declared explicitly when handlers read from ServerRequest.
- [ ] Request bodies specify appropriate media types and schemas.
- [ ] Responses declare accurate statuses, media types, and schemas.
- [ ] All routes composed in the same RouterFunction have matching operations.
- [ ] Verified <code>/v3/api-docs</code> and Swagger UI.
- [ ] Tested real requests and compared them with the OpenAPI contract.

## References

- [springdoc-openapi – WebFlux functional endpoints](https://springdoc.org/#webflux-fn): documenting functional routes using <code>@RouterOperation</code> and <code>@RouterOperations</code>.
- [Spring Framework – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): route predicates, handler functions, ServerRequest, and ServerResponse.
- [Swagger Core – Operation annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Operation.html): documenting operations, parameters, request bodies, and responses.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): structure of operations in OpenAPI.
