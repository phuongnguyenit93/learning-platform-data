# Documenting the Same API Domain on MVC and WebFlux

A business domain can be served through two Spring Boot applications: one using Spring Web MVC on the Servlet stack and another using Spring WebFlux on the reactive stack. Even though request processing differs, consumers must see the exact same HTTP contract: paths, methods, parameters, request bodies, response schemas, status codes, security, and validation rules.

springdoc-openapi provides separate starters for MVC and WebFlux. Each application generates an OpenAPI Description from its own controllers and runtime configuration. Therefore, both adapters should be designed to publish the same contract, and then both documents and actual responses should be verified with the same contract test suite.

This hands-on exercise uses a Catalog domain with three operations:

| Operation | Method and path | Purpose |
|---|---|---|
| Get product | GET /api/products/{id} | Return a single product |
| Search products | GET /api/products?keyword=... | Return a list of products |
| Create product | POST /api/products | Create a new product |

Both applications share the same API DTOs and business rules. MVC and WebFlux have separate controller adapters, web stacks, springdoc configurations, and runtimes.

## 1. Distinguishing the two web stacks

Spring Web MVC runs on the Servlet API. Requests are handled by a Servlet container such as Tomcat or Jetty; controllers typically return objects, ResponseEntity, or asynchronous types supported by the framework.

Spring WebFlux is a reactive, non-blocking web framework. It typically runs on Reactor Netty, though it can also run on Tomcat or Jetty via a reactive adapter. Controllers can return Mono or Flux; functional endpoints use RouterFunction and HandlerFunction.

| Aspect | Spring MVC | Spring WebFlux |
|---|---|---|
| Runtime model | Servlet, request threads managed under the Servlet model | Reactive Streams, non-blocking event loop |
| Starter | spring-boot-starter-web | spring-boot-starter-webflux |
| Body conversion | HttpMessageConverter | HttpMessageReader and HttpMessageWriter |
| Common controllers | @RestController and @RequestMapping | @RestController and @RequestMapping |
| Reactive return types | Can support Mono/Flux via ReactiveAdapterRegistry | Supports Mono/Flux natively |
| Functional endpoints | MVC.fn has its own model | WebFlux.fn uses RouterFunction |
| springdoc API starter | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webflux-api |
| springdoc UI starter | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webflux-ui |

Key point: both stacks use many of the same controller annotations, but they do not share the same runtime. MVC uses message converters; WebFlux uses codecs. Having the same @GetMapping does not guarantee every parameter type, return type, streaming behavior, or custom converter works identically.

## 2. Why separate into two applications or two deployable adapters?

Spring Boot selects the web application type at startup. If a classpath contains both spring-boot-starter-web and spring-boot-starter-webflux, Boot auto-configures Spring MVC by default. A common reason is that many MVC apps add WebFlux solely to use WebClient.

You can force the application type to REACTIVE, but that still selects only one stack for the running application. A standard Spring Boot application context does not automatically spin up two independent HTTP servers to serve MVC and WebFlux simultaneously.

For the problem of verifying the same API domain on both stacks, the cleanest approach is creating two separate deployables:

~~~mermaid
flowchart TB
    subgraph Shared["Shared contract and application"]
      DTO["API DTO / validation"]
      USE["Use cases / domain services"]
      RULES["Business rules"]
    end
    subgraph MVC["Catalog MVC application"]
      MC["MVC controller adapter"]
      MD["springdoc WebMVC"]
      MS["Servlet server"]
      MC --> MD
      MC --> MS
    end
    subgraph FLUX["Catalog WebFlux application"]
      FC["WebFlux controller adapter"]
      FD["springdoc WebFlux"]
      FS["Reactive server"]
      FC --> FD
      FC --> FS
    end
    DTO --> MC
    DTO --> FC
    USE --> MC
    USE --> FC
    RULES --> USE
~~~

Example multi-module structure:

~~~text
catalog/
  catalog-contract/
    ProductRequest.java
    ProductResponse.java
    ApiError.java
  catalog-application/
    CatalogUseCases.java
    CatalogService.java
  catalog-mvc-app/
    ProductMvcController.java
    OpenApiConfiguration.java
    application.yml
  catalog-webflux-app/
    ProductWebFluxController.java
    OpenApiConfiguration.java
    application.yml
  contract-tests/
    CatalogContractTest.java
~~~

The two apps can share DTOs, validation constraints, service ports, and business policies. Each app installs only its matching web adapter and springdoc starter. CI starts the two apps on separate ports or in separate jobs.

Do not add both web starters to a single app just so you can write two sets of controllers. Doing so makes auto-configuration depend on the classpath and makes it harder to tell which stack is running.

## 3. Locking down a shared HTTP contract

Before writing controllers, define the contract both adapters must obey. For the Catalog API:

| Component | Contract |
|---|---|
| Base path | /api/products |
| Get by ID | GET /api/products/{id} |
| Search | GET /api/products?keyword=... |
| Create | POST /api/products |
| ID | UUID |
| Product name | Non-blank string, max 120 characters |
| Price | Decimal number, non-negative |
| Created | 201 Created and ProductResponse |
| Not found | 404 and ApiError |
| Validation failed | 400 and ApiError |
| Content type | application/json |

The contract should clearly specify:

- Stable operationIds independent of internal method names.
- Clearly named schemas and component names.
- Consistent required fields, nullability, enums, and formats.
- Response codes and response bodies for every scenario.
- A uniform error format, such as RFC 9457 Problem Details or a custom ApiError schema.
- Security schemes and corresponding access permissions.
- Pagination, sorting, and filtering rules.

OpenAPI describes the HTTP interface observed by clients. It does not describe thread models, event loops, backpressure, or whether internal services use blocking or reactive repositories.

## 4. Sharing DTOs and validation

Place request/response DTOs in the contract module so both applications use the exact same definitions:

~~~java
package example.catalog.contract;

import java.math.BigDecimal;
import java.util.UUID;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "CreateProductRequest")
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Product name displayed to buyers.",
        example = "Mechanical Keyboard"
    )
    String name,

    @DecimalMin("0.00")
    @Schema(
        description = "Selling price in the store's currency.",
        example = "1250000.00"
    )
    BigDecimal price
) {}

@Schema(name = "ProductResponse")
public record ProductResponse(
    @Schema(example = "e8b2f4a0-13b7-4c65-9c3f-1c7e6d4a0001")
    UUID id,

    @Schema(example = "Mechanical Keyboard")
    String name,

    @Schema(example = "1250000.00")
    BigDecimal price
) {}
~~~

In real code, each public Java type lives in its own file. The snippet above combines both records to illustrate shared DTOs.

Validation annotations can be used by springdoc to infer schema constraints and enforced at runtime when controllers enable @Valid. Still, both must be tested separately:

- OpenAPI must show maxLength, minimum, and required accurately.
- Runtime MVC/WebFlux must actually return 400 when a request violates constraints.
- JSON serialization on both stacks must preserve the same field names, number formats, null handling, and date/time formats.

If the contract module uses @Schema, it needs the compatible swagger-annotations dependency. Keep that dependency inside the API contract module; do not pull the full springdoc runtime into the domain/application core.

## 5. Separating application use cases from web adapters

Controllers should not contain business rules themselves. Both applications call the same application service or two implementations adhering to the same port.

A simple port:

~~~java
public interface CatalogUseCases {
    ProductResponse getProduct(UUID id);
    List<ProductResponse> searchProducts(String keyword);
    ProductResponse createProduct(CreateProductRequest request);
}
~~~

If the service uses JDBC or blocking libraries, MVC can call it directly. The WebFlux adapter must never call blocking databases/clients on an event-loop thread. You can temporarily offload blocking calls:

~~~java
Mono.fromCallable(() -> catalogUseCases.getProduct(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is a transitional bridge when using a blocking application service. It does not turn the persistence layer non-blocking. For a truly reactive WebFlux stack, design ports and implementations returning Mono/Flux, use reactive drivers, and keep the pipeline non-blocking end to end.

What matters for API documentation is that publisher wrappers are not part of the JSON contract. Clients receive ProductResponse or a list of ProductResponse, not a Mono or Flux object.

## 6. Installing the right springdoc starter

Choose the starter based on the web stack and documentation needs:

| Need | MVC | WebFlux |
|---|---|---|
| Export OpenAPI JSON/YAML only | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webflux-api |
| With Swagger UI | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webflux-ui |
| With Scalar UI | springdoc-openapi-starter-webmvc-scalar | springdoc-openapi-starter-webflux-scalar |

Maven example for Spring Boot 3.5.x and springdoc 2.10.0:

~~~xml
<!-- catalog-mvc-app -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

~~~xml
<!-- catalog-webflux-app -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

If you only need JSON/YAML for CI extraction, use the api starter instead of ui. This avoids packaging Swagger UI into runtimes that do not need a UI.

With Spring Boot 4.x, use springdoc 3.x and verify the release compatibility matrix. Current documentation illustrates springdoc 3.2.0 for Boot 4; Boot 3 applications continue using the springdoc 2.x branch. Do not share a single springdoc version if the two applications are on different Spring Boot major versions without verifying the compatibility matrix.

Each app declares only the starter matching its own web stack.

## 7. Configuring identical OpenAPI metadata

Both apps should publish the same title, description, version, tags, and security schemes. Separate server URLs per environment or configure them per app.

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Catalog API",
        version = "v1",
        description = "API for managing and querying products."
    )
)
public class OpenApiConfiguration {
}
~~~

If the API has multiple domains or audiences, use consistently named groups:

~~~java
@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi catalogApi() {
        return GroupedOpenApi.builder()
            .group("catalog")
            .pathsToMatch("/api/products/**")
            .build();
    }
}
~~~

Place equivalent configuration in both the MVC app and the WebFlux app. When the group is named catalog, documents are typically served at:

~~~text
/v3/api-docs/catalog
/v3/api-docs.yaml/catalog
~~~

Group paths and YAML endpoints can depend on springdoc configuration. Verify each app's actual URLs after startup.

If the same OpenApiGroupConfiguration class is packaged in a shared module, make sure both apps component-scan that bean. If configured separately per app, keep contents and group names synchronized.

## 8. Writing the MVC controller for Catalog

The MVC controller uses the shared DTOs and application service. Example:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Query and manage products.")
public class ProductMvcController {

    private final CatalogUseCases catalog;

    public ProductMvcController(CatalogUseCases catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Get product by ID"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Product not found",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public ProductResponse getById(@PathVariable UUID id) {
        return catalog.getProduct(id);
    }

    @GetMapping
    @Operation(
        operationId = "searchProducts",
        summary = "Search products by keyword"
    )
    public List<ProductResponse> search(
            @RequestParam(required = false) String keyword) {
        return catalog.searchProducts(keyword);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        operationId = "createProduct",
        summary = "Create product"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Product created successfully",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Invalid request data",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public ProductResponse create(
            @Valid @RequestBody CreateProductRequest request) {
        return catalog.createProduct(request);
    }
}
~~~

Set explicit operationIds so operation names in OpenAPI do not change when Java method names are refactored. Important responses should be explicitly documented with @ApiResponse rather than relying solely on return types.

## 9. Writing the WebFlux controller for the same contract

The WebFlux controller uses the same paths, HTTP methods, DTOs, validation, and operationIds. The example below assumes a blocking application service and illustrates offloading it from the event loop:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Query and manage products.")
public class ProductWebFluxController {

    private final CatalogUseCases catalog;

    public ProductWebFluxController(CatalogUseCases catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Get product by ID"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Product not found",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public Mono<ProductResponse> getById(@PathVariable UUID id) {
        return Mono.fromCallable(() -> catalog.getProduct(id))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping
    @Operation(
        operationId = "searchProducts",
        summary = "Search products by keyword"
    )
    public Mono<List<ProductResponse>> search(
            @RequestParam(required = false) String keyword) {
        return Mono.fromCallable(() -> catalog.searchProducts(keyword))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        operationId = "createProduct",
        summary = "Create product"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Product created successfully",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Invalid request data",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public Mono<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        return Mono.fromCallable(() -> catalog.createProduct(request))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

The snippet requires Reactor imports such as Mono and Schedulers, plus the same Spring and Swagger annotations as the MVC controller. Depending on the Spring Framework version, reactive types on @RequestBody parameters are directly supported by WebFlux.

If the application service is already reactive, do not wrap it in fromCallable/boundedElastic. Return Mono/Flux directly from the port to stay non-blocking. Never run blocking JDBC or RestTemplate on an event-loop thread.

Both controllers do not need identical Java method signatures. What must match is the HTTP contract and JSON payload observed by clients.

## 10. Checking schemas generated from reactive return types

OpenAPI documents the serialized response value, not the Reactor wrapper:

| Java signature | Schema clients must see |
|---|---|
| MVC: ProductResponse | ProductResponse object |
| WebFlux: Mono<ProductResponse> | ProductResponse object |
| MVC: List<ProductResponse> | Array of ProductResponse |
| WebFlux: Mono<List<ProductResponse>> | Array of ProductResponse |

If the document exposes a Mono or Flux schema as a regular object, check dependencies, generic type resolution, and the springdoc version. Do not patch the schema by hiding wrappers before understanding the root cause.

Set @Schema(name = "ProductResponse") and @Schema(name = "CreateProductRequest") on DTOs if stable component names are needed. Check components.schemas in both documents after export.

## 11. Documenting identical error responses

MVC and WebFlux handle exceptions differently at the runtime layer, yet consumers should receive the same error contract. You can use a shared DTO:

~~~java
@Schema(name = "ApiError")
public record ApiError(
    String code,
    String message,
    String traceId
) {}
~~~

Both apps map business exceptions to the same status and ApiError. You can use @RestControllerAdvice for annotated controllers, but test exception mapping separately on each stack. WebFlux functional handlers may need a WebExceptionHandler or error handling inside RouterFunction.

Document the response on operations:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Invalid request data",
    content = @Content(
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Do not merely declare 400 responses in OpenAPI. Send actual invalid requests to both apps and verify status, content type, fields, and messages according to API policy.

## 12. Validation and binding must be verified on both stacks

Sharing the same DTOs shares constraints, yet binding and validation still traverse different infrastructure:

- MVC uses HttpMessageConverter and MVC validation integration.
- WebFlux uses HttpMessageReader/HttpMessageWriter and reactive validation integration.
- Custom Jackson configuration may be applied via different converter or codec settings.
- Method parameter constraints may depend on @Validated and method validation configuration.

Test at least:

1. Missing required field.
2. String exceeding maxLength.
3. Negative numeric value.
4. Malformed UUID.
5. Malformed JSON.
6. Unsupported Content-Type.
7. Empty request body.

Both stacks must return the same status code and error schema per the contract. If one side returns 400 while the other returns 500, that is contract drift even if their OpenAPI documents are identical.

## 13. Response streaming requires separate documentation

For ordinary collections, use application/json and an array schema to maintain the same response shape. Do not pick Flux merely because the application uses WebFlux.

If an API genuinely streams:

- WebFlux can emit items from a Flux using reactive streaming.
- Spring MVC also supports reactive return types and streaming responses, though buffering/flushing behavior depends on media types and return value adapters.
- text/event-stream is commonly used for Server-Sent Events.
- application/x-ndjson or other streaming media types must be agreed upon by client and server.

OpenAPI must declare the exact produces media type, response content type, and schema of each event/item. Documentation does not automatically describe backpressure, emission rate, retries, reconnects, or buffer limits.

Do not document a streaming endpoint as a regular JSON array if clients actually must read individual events. Test with a real client and inspect Content-Type, framing, flush behavior, and mid-stream error handling.

## 14. WebFlux functional endpoints

WebFlux can declare routes using RouterFunction instead of annotated controllers. In that case there is no @GetMapping method for springdoc to inspect the same way it inspects annotated controllers.

Springdoc supports documenting functional routes via @RouterOperation, @RouterOperations, and OpenApiCustomizer. When using this approach, explicitly declare:

- Path and HTTP method.
- OperationId, summary, and description.
- Request parameters or request body.
- Response codes, media types, and schemas.
- Security requirements.

Example route:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products/{id}", handler::getById)
        .POST("/api/products", handler::create)
        .build();
}
~~~

The route above defines runtime routing. To produce complete OpenAPI operations, add metadata using annotations/configuration supported by your springdoc version. Do not assume RouterFunction alone is enough to generate accurate request/response schemas.

If an API domain mixes annotated controllers and functional routes, follow the same naming conventions, schemas, and operationIds. Verify no path/method is declared twice.

## 15. Dividing OpenAPI groups identically

Both applications should use the same group name and path filters:

~~~java
@Bean
GroupedOpenApi productsApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/products/**")
        .build();
}
~~~

If the MVC app uses group catalog while the WebFlux app uses group products, pipelines and portals will have to handle two different conventions. Keeping group names consistent helps export scripts, dashboards, and consumers locate documentation at the same URL pattern.

If each app has distinct internal APIs, place them in separate groups and exclude them from the public contract. Do not let an app accidentally publish actuator, admin, or debug endpoints merely because it scans the whole application.

## 16. Ensuring consistent server URLs and metadata

The two applications often run on different hosts or ports:

~~~text
MVC:     http://localhost:8081/v3/api-docs/catalog
WebFlux: http://localhost:8082/v3/api-docs/catalog
~~~

These are the URLs for downloading documentation. The servers field in the OpenAPI document is the base URL clients use to call the API. If two apps serve the same API contract on different hosts, server URLs can differ while paths and schemas stay identical.

When comparing contracts:

- Keep the original documents intact to inspect deployment URLs.
- Compare servers separately to verify each environment.
- Create normalized copies solely for semantic diffing, removing servers if differing hosts are intentional.
- Do not strip paths, security, schemas, or responses just to shrink the diff.
- Keep info.title, info.version, tags, and operationIds uniform.

If the two apps have different base paths, determine whether that constitutes a different contract. Do not strip prefixes automatically during normalization if consumers must call different paths.

## 17. Generating OpenAPI documents from both applications

Start MVC and WebFlux on separate ports with the same API group:

~~~bash
# MVC app
./gradlew :catalog-mvc-app:bootRun --args='--server.port=8081'

# WebFlux app, run in a separate terminal/job
./gradlew :catalog-webflux-app:bootRun --args='--server.port=8082'
~~~

Download both documents:

~~~bash
mkdir -p build/openapi

curl -fsS http://localhost:8081/v3/api-docs/catalog \
  -o build/openapi/catalog-mvc.json

curl -fsS http://localhost:8082/v3/api-docs/catalog \
  -o build/openapi/catalog-webflux.json
~~~

If using custom group or API docs paths, substitute the corresponding URLs. Check that the files exist, are non-empty, and parse cleanly:

~~~bash
test -s build/openapi/catalog-mvc.json
test -s build/openapi/catalog-webflux.json

jq -e '.openapi and .info.title and (.paths | length > 0)' \
  build/openapi/catalog-mvc.json

jq -e '.openapi and .info.title and (.paths | length > 0)' \
  build/openapi/catalog-webflux.json
~~~

## 18. Comparing the two OpenAPI documents

First compare high-level information:

~~~bash
jq -r '.info.title, .info.version, (.paths | keys[])' \
  build/openapi/catalog-mvc.json

jq -r '.info.title, .info.version, (.paths | keys[])' \
  build/openapi/catalog-webflux.json
~~~

Verify key elements:

- Same OpenAPI version and info.version.
- Same paths and HTTP methods.
- Same operationIds.
- Same request parameters, required flags, and schemas.
- Same request body content types and schemas.
- Same response codes, media types, and schemas.
- Same security schemes and operation-level security.
- Same component schema names, properties, enums, and validation constraints.

If only the server URL differs, create normalized copies for comparison:

~~~bash
jq 'del(.servers)' build/openapi/catalog-mvc.json \
  > build/openapi/catalog-mvc-normalized.json

jq 'del(.servers)' build/openapi/catalog-webflux.json \
  > build/openapi/catalog-webflux-normalized.json
~~~

Keep both original files. Use normalized copies solely to compare host-independent contract sections:

~~~bash
oasdiff diff \
  build/openapi/catalog-mvc-normalized.json \
  build/openapi/catalog-webflux-normalized.json
~~~

If you need to check for breaking changes against an approved baseline:

~~~bash
oasdiff breaking \
  api/openapi/catalog-baseline.yaml \
  build/openapi/catalog-mvc-normalized.json

oasdiff breaking \
  api/openapi/catalog-baseline.yaml \
  build/openapi/catalog-webflux-normalized.json
~~~

An empty diff or zero breaking changes is a good signal, but it does not prove runtime behavior matches. Run contract tests against both apps.

## 19. Running the same runtime contract test suite

Decouple test cases from the web stack. Each test case defines:

- HTTP method and path.
- Headers and query parameters.
- Request body.
- Expected status.
- Expected content type.
- JSON assertions or schemas.
- Security requirements.

Then run the same test data against both the MVC and WebFlux base URLs.

Example test matrix:

| Test | Request | Expected outcome |
|---|---|---|
| Get existing product | GET /api/products/{id} | 200, ProductResponse |
| Get missing product | GET /api/products/{unknown} | 404, ApiError |
| Search products | GET /api/products?keyword=keyboard | 200, JSON array |
| Create product | POST with valid request | 201, ProductResponse |
| Missing name | POST missing name | 400, ApiError |
| Invalid UUID | GET with malformed UUID | 400, error contract |
| Unsupported media type | POST with unsupported content type | 415 |
| Unauthorized | Call secured operation without token | 401 |
| Forbidden | Token with insufficient permissions | 403 |

MVC is commonly tested with MockMvc or a real HTTP client. WebFlux can use WebTestClient. You can share the same JSON fixtures and assertion layer, swapping only the test client or base URL.

Do not test only the response body. Compare status codes, Content-Type, Location/ETag headers, pagination metadata, error structures, and serialization.

## 20. Checking security parity

If both apps expose the public API, they must share the same authentication/authorization contract:

- Same security schemes in OpenAPI.
- Same scopes/roles required per operation.
- Same 401 and 403 responses.
- Same CORS policy for cross-origin consumers.
- Neither app's docs group exposes internal endpoints.

Runtime security configurations may differ in implementation: MVC uses a servlet SecurityFilterChain; WebFlux uses a reactive security chain and WebFilter. Do not copy MVC security configuration verbatim into WebFlux.

OpenAPI security schemes describe the credentials clients must send. They do not replace Spring Security at runtime. Run tests with no token, valid token, expired token, and insufficient-scope token on both apps.

## 21. Serialization parity between converters and codecs

MVC uses HttpMessageConverter; WebFlux uses HttpMessageReader/HttpMessageWriter. Identical DTOs do not guarantee identical JSON if the two apps configure serialization differently:

- Property naming strategy.
- Null inclusion.
- Enum serialization.
- Date/time formats and timezones.
- BigDecimal scale and number serialization.
- Custom serializers/deserializers.
- Polymorphic type metadata.
- Registered Jackson modules.

Place serialization policies in a shared configuration module where appropriate, while still verifying each app's effective converters/codecs. In particular, if customizing an MVC HttpMessageConverter or WebFlux Codec, verify springdoc and runtime use the same data representation.

## 22. Aligning exceptions and response documentation

Both apps need the same business error mappings:

| Error | HTTP status | Response |
|---|---|---|
| Product not found | 404 | ApiError or ProblemDetail |
| Request validation failed | 400 | ApiError or ProblemDetail |
| Missing authentication | 401 | Security error |
| Insufficient permissions | 403 | Security error |
| Unsupported Content-Type | 415 | ApiError or ProblemDetail |
| Unexpected error | 500 | Error response without leaking stack trace |

If one app uses @RestControllerAdvice and the other uses WebExceptionHandler, both can still produce the exact same body. What needs verification is the HTTP contract, not whether exception-handling classes share the same name.

Declare response codes in @ApiResponses or an OpenApiCustomizer so OpenAPI does not document only 200. Avoid exposing stack traces or internal exception messages in production.

## 23. CI pipeline for both stacks

CI should build and export independently, then compare:

~~~yaml
steps:
  - name: Test MVC
    run: ./gradlew :catalog-mvc-app:test

  - name: Test WebFlux
    run: ./gradlew :catalog-webflux-app:test

  - name: Export MVC OpenAPI
    run: ./gradlew :catalog-mvc-app:generateOpenApiDocs

  - name: Export WebFlux OpenAPI
    run: ./gradlew :catalog-webflux-app:generateOpenApiDocs

  - name: Compare contracts
    run: ./scripts/compare-catalog-openapi.sh
~~~

Task names and plugin configuration must match the actual Gradle plugin in each module. Each app must use the right springdoc starter, port, profile, and API docs URL. If tasks start the apps themselves, ensure the two tasks do not contend for the same port.

CI must fail or require review when:

- A path/method is missing on either stack.
- operationId changes unexpectedly.
- Request/response schemas differ.
- Security requirements differ.
- Either stack exports an internal endpoint outside its group.
- Runtime contract tests produce different results for the same fixture.

Archive both original documents, the normalized diff, and test reports as artifacts attached to the same commit.

## 24. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| App expected to be WebFlux runs MVC | Both web starters are present and Boot picks MVC | Separate deployables or set application type explicitly |
| MVC has docs but WebFlux does not | Wrongly used webmvc starter in WebFlux app | Switch to webflux-api or webflux-ui |
| Both documents have different operationIds | Let springdoc auto-generate from method names | Set explicit operationIds |
| WebFlux document exposes Mono/Flux schemas | Incorrect generic type resolution or dependency | Check starter, return types, and schema components |
| Same DTOs produce different JSON | Different converters/codecs or Jackson config | Compare actual responses and unify serialization |
| WebFlux is slow or blocks the event loop | Calling blocking services on the event loop | Use reactive I/O or offload blocking work |
| MVC returns a list while WebFlux streams | Different media type/Flux semantics | Lock down collection vs. streaming contract explicitly |
| Functional routes missing from OpenAPI | RouterFunction lacks metadata | Use @RouterOperation(s) or OpenApiCustomizer |
| Two docs groups contain different path sets | Out-of-sync pathsToMatch/packagesToScan | Use the same group name and filters |
| Same security scheme behaves differently | Different runtime security chains | Test MVC servlet security and WebFlux reactive security |
| Error bodies differ | Separate exception mappings out of sync | Use shared error DTO and contract tests |
| Diff differs only on host | servers differ per deployment | Compare servers separately and normalize for contract diff |

## 25. Complete practice workflow

1. Write the contract for the Catalog domain before choosing a web stack.
2. Create a shared module for DTOs, validation, and schemas.
3. Create an application service or port independent of MVC/WebFlux.
4. Create the MVC app with the springdoc WebMVC starter.
5. Create the WebFlux app with the springdoc WebFlux starter.
6. Set identical paths, methods, operationIds, tags, responses, and security metadata.
7. Configure identical OpenAPI groups.
8. Run each app separately and download JSON/YAML.
9. Compare the documents and inspect schemas.
10. Run the same contract fixtures against both runtimes.
11. Verify validation, serialization, errors, security, and streaming.
12. Save a shared baseline and add comparison to CI.

After changing a DTO or controller, rerun both test suites. Do not update the baseline just because one stack generated a different document; first determine whether the change is intentional or contract drift.

## 26. Pre-publication checklist

- [ ] MVC and WebFlux are separate deployables with clearly defined web stacks.
- [ ] Both web starters are not accidentally added to one app assuming Boot runs both stacks in parallel.
- [ ] Both apps share DTOs, validation rules, and application contracts.
- [ ] Each app uses the matching springdoc starter.
- [ ] The springdoc version is compatible with each app's Spring Boot version.
- [ ] OpenAPI info, group names, tags, and operationIds are consistent.
- [ ] Paths, methods, parameters, request bodies, and response schemas match.
- [ ] Security scheme and runtime authorization parity have been tested.
- [ ] Error statuses and error bodies match.
- [ ] Converters and codecs serialize the same DTOs consistently.
- [ ] WebFlux does not run blocking work on the event loop.
- [ ] Streaming endpoints declare accurate media types and behavior.
- [ ] Functional routes have explicit OpenAPI metadata.
- [ ] Both OpenAPI documents are validated and semantically diffed.
- [ ] Runtime contract tests run against both MVC and WebFlux.
- [ ] Baselines and artifacts are tied to the same commit.

## 27. Official references

- [springdoc-openapi Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): springdoc branches mapped to Spring Boot.
- [springdoc-openapi Current Documentation](https://springdoc.org/): starters and configuration for the Boot 4 branch.
- [springdoc-openapi Modules](https://springdoc.org/v2/modules.html): WebMVC/WebFlux, API-only, and UI starters for Spring Boot 3.
- [springdoc-openapi FAQ](https://springdoc.org/v2/faq.html): GroupedOpenApi, path/package filters, and doc generation notes.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/reactive.html): WebFlux, annotated controllers, and behavior when MVC/WebFlux starters coexist.
- [Spring Framework – WebFlux Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): annotated controllers and path mapping.
- [Spring Framework – WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): Mono/Flux, streaming, and response encoding.
- [Spring Framework – MVC Return Values](https://docs.spring.io/spring-framework/reference/7.1/web/webmvc/mvc-controller/ann-methods/return-types.html): reactive return types and HttpMessageConverter.

## Conclusion

To document the same API domain on MVC and WebFlux, start from a shared HTTP contract and implement two independent web adapters. Share DTOs, validation, and use cases; pick the matching springdoc WebMVC or WebFlux starter for each app; keep paths, operationIds, schemas, security, and error responses stable. Then generate both OpenAPI documents, compare them, and run the same contract test suite against both runtimes. OpenAPI shows the contract clients see, while HTTP testing confirms both implementations actually obey that contract.
