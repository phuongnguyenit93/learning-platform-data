# End-to-End Capstone: From Controller to a Verified and Published Contract

An API is ready for clients only when three parts agree: the controller executes the right HTTP behavior, OpenAPI accurately describes that behavior, and the release pipeline delivers the verified document. Being able to open Swagger UI or generate a JSON file is not enough to prove a contract is trustworthy. An operation may document the wrong status code, a schema may fail to reflect actual JSON, or the published file may not match the deployed application version.

This hands-on exercise builds an end-to-end workflow using an Order API. We start from business requirements, create request/response DTOs, controller, and exception handler, then generate documentation with springdoc-openapi. Next, we write integration tests for HTTP behavior and the OpenAPI document, run validation and compatibility checks, package artifacts, publish versioned documentation, and verify the documentation endpoints after deployment.

The target outcome is an OpenAPI artifact that can be reviewed, validated, diffed against the previous release, and distributed to clients. The examples use Spring Boot 3, Spring MVC, and Spring Security Resource Server; if your project uses Boot 4 or WebFlux, pick the starters and APIs compatible with your actual platform.

## 1. Target outcomes

After completing this exercise, learners will be able to:

- Define the HTTP contract before implementing the controller.
- Design DTOs separated from entities and persistence structures.
- Document paths, methods, parameters, request bodies, responses, errors, and security.
- Generate OpenAPI JSON/YAML from a Spring Boot application using Springdoc.
- Verify HTTP behavior and OpenAPI content using integration tests.
- Detect differences between the current contract and the published release.
- Classify compatible changes versus breaking changes.
- Package documentation alongside its corresponding version and commit.
- Publish public/internal documentation within the appropriate scope.
- Verify published artifacts are downloadable with the expected content.

## 2. Business context and API scope

The application manages orders for an online store. An authenticated client can create an order, view an order by ID, and request order cancellation. Business rules:

- Clients send customerId and a list of items when creating an order.
- The server generates orderId, initial status, and timestamp.
- Each item must have a productId and a quantity greater than 0.
- An order can be cancelled only while in PENDING status.
- Non-existent orders return 404.
- Orders already processed or cancelled cannot be cancelled again; this case returns 409.
- Invalid requests return 400.
- Endpoints require a Bearer JWT; missing or invalid tokens return 401, insufficient permissions return 403.

Published operations:

| Method | Path | Purpose | Success |
|---|---|---|---|
| POST | /api/orders | Create an order | 201 Created |
| GET | /api/orders/{orderId} | View an order | 200 OK |
| POST | /api/orders/{orderId}/cancel | Cancel a pending order | 200 OK |

Error contract:

| Status | Error code | Condition |
|---|---|---|
| 400 | VALIDATION_FAILED | Request is missing or has invalid data |
| 401 | UNAUTHORIZED | Missing or invalid token |
| 403 | FORBIDDEN | User lacks sufficient permissions |
| 404 | ORDER_NOT_FOUND | Order not found |
| 409 | ORDER_STATE_CONFLICT | Current state does not allow the operation |
| 500 | INTERNAL_ERROR | Unexpected server error |

Status codes are part of the contract. Do not return 200 for all situations and force clients to parse a message string to tell whether a request succeeded or failed.

## 3. Overall workflow

~~~mermaid
flowchart TD
    A["Business requirements and HTTP rules"] --> B["DTOs, validation, and controller"]
    B --> C["Spring handler mappings and security"]
    C --> D["Springdoc metadata analysis"]
    D --> E["OpenAPI JSON/YAML"]
    E --> F["HTTP integration tests"]
    E --> G["OpenAPI validation"]
    F --> H["Contract and compatibility checks"]
    G --> H
    H --> I["Package versioned artifacts"]
    I --> J["Publish to developer portal or artifact store"]
    J --> K["Verify URLs and content after release"]
~~~

Each step produces evidence for the next step. The controller is the runtime implementation; OpenAPI is the published contract; tests prove the two match; only verified artifacts move into the release channel.

## 4. Suggested project structure

~~~text
com.acme.shop
├── ShopApplication.java
├── config
│   ├── OpenApiConfiguration.java
│   └── SecurityConfiguration.java
├── order
│   ├── OrderController.java
│   ├── OrderService.java
│   ├── OrderRepository.java
│   ├── Order.java
│   ├── OrderStatus.java
│   └── dto
│       ├── CreateOrderRequest.java
│       ├── OrderItemRequest.java
│       ├── OrderResponse.java
│       └── OrderItemResponse.java
└── common
    ├── ApiError.java
    ├── FieldViolation.java
    └── ApiExceptionHandler.java
~~~

Separate DTOs from entities so database changes do not automatically change the API. The controller accepts request DTOs, the service executes business logic and returns response DTOs. Springdoc inspects types and annotations on these classes to generate schemas.

## 5. Choosing dependencies matching the platform

With Spring Boot 3 and Spring MVC, use the Springdoc 2.x starter compatible with your running Boot minor version:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x-compatible-version</version>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

The version value above is a placeholder guide. Replace it with the Springdoc release documented as compatible with your project's Spring Boot minor version. For Boot 4, use the Springdoc 3.x line; for Boot 2, check the 1.x line and matching modules.

If you only need OpenAPI JSON/YAML without Swagger UI, pick the matching API-only starter. If the application uses WebFlux, pick the WebFlux starter. Never add both MVC and WebFlux starters unless the application intentionally runs both stacks.

## 6. Defining the contract before writing code

Record API decisions clearly before creating the controller:

| Component | Decision in this exercise |
|---|---|
| ID | Server-generated UUID |
| Create request | customerId and items |
| Quantity | Integer 1 or greater |
| Initial status | PENDING |
| Create response | 201, OrderResponse, and Location |
| Read response | 200, OrderResponse |
| Cancel response | 200, updated OrderResponse |
| Invalid request | 400, ApiError |
| Missing order | 404, ApiError |
| Invalid state transition | 409, ApiError |
| Authentication | HTTP Bearer JWT |

Deciding upfront keeps code and documentation aligned to a single contract. If cancel changes to 204, update the controller, OpenAPI response, and integration tests together.

## 7. Creating the request item DTO

~~~java
public class OrderItemRequest {

    @NotNull
    @Schema(
        description = "Product identifier",
        example = "a1d2c3e4-1111-4222-8333-123456789abc"
    )
    private UUID productId;

    @NotNull
    @Min(1)
    @Schema(
        description = "Quantity must be greater than 0",
        minimum = "1",
        example = "2"
    )
    private Integer quantity;

    // constructors, getters and setters
}
~~~

Bean Validation checks input when requests are processed with @Valid. Springdoc can use common constraints to add metadata to schemas. For custom validators, inspect the OpenAPI output; do not assume every business rule automatically translates into a JSON Schema constraint.

## 8. Creating CreateOrderRequest

~~~java
public class CreateOrderRequest {

    @NotNull
    @Schema(
        description = "UUID of the customer placing the order",
        example = "f5b5e4d1-aaaa-4bbb-8ccc-123456789abc"
    )
    private UUID customerId;

    @NotEmpty
    @Valid
    @Size(max = 50)
    @ArraySchema(
        schema = @Schema(implementation = OrderItemRequest.class),
        arraySchema = @Schema(
            description = "List of items, from 1 to 50 elements"
        )
    )
    private List<OrderItemRequest> items;

    // constructors, getters and setters
}
~~~

Clients do not send orderId, status, totalAmount, or createdAt. These fields are managed by the server. Never use the Order entity as a request just to reduce class count; entities may hold internal fields and persistence relationships that do not belong in the HTTP contract.

## 9. Creating response DTOs

~~~java
public class OrderItemResponse {

    @Schema(format = "uuid")
    private UUID productId;

    @Schema(example = "2")
    private int quantity;

    @Schema(example = "49.95")
    private BigDecimal unitPrice;

    @Schema(example = "99.90")
    private BigDecimal lineTotal;

    // constructors, getters and setters
}
~~~

~~~java
public class OrderResponse {

    @Schema(format = "uuid")
    private UUID orderId;

    @Schema(format = "uuid")
    private UUID customerId;

    @Schema(
        description = "Order status",
        example = "PENDING"
    )
    private OrderStatus status;

    @Schema(example = "99.90")
    private BigDecimal totalAmount;

    @Schema(format = "date-time")
    private Instant createdAt;

    private List<OrderItemResponse> items;

    // constructors, getters and setters
}
~~~

Response schemas must match actual serialized JSON. If Jackson renames properties, omits nulls, or formats timestamps, inspect both the document and HTTP responses to avoid contract mismatches.

## 10. Standardizing the error model

~~~java
public class FieldViolation {

    @Schema(example = "items[0].quantity")
    private String field;

    @Schema(example = "must be greater than or equal to 1")
    private String message;

    // constructors, getters and setters
}
~~~

~~~java
public class ApiError {

    @Schema(format = "date-time")
    private Instant timestamp;

    @Schema(example = "400")
    private int status;

    @Schema(example = "VALIDATION_FAILED")
    private String code;

    @Schema(example = "Request contains invalid fields")
    private String message;

    @Schema(example = "/api/orders")
    private String path;

    private List<FieldViolation> fieldErrors;

    // constructors, getters and setters
}
~~~

Validation error example:

~~~json
{
  "timestamp": "2026-11-20T10:15:30Z",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "path": "/api/orders",
  "fieldErrors": [
    {
      "field": "items[0].quantity",
      "message": "must be greater than or equal to 1"
    }
  ]
}
~~~

Do not include stack traces, SQL, tokens, or secrets in the error body. Public messages should be stable and clear enough for clients to handle; technical details belong in internal logs.

## 11. Creating domain exceptions

~~~java
public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(UUID orderId) {
        super("Order not found: " + orderId);
    }
}

public class OrderStateConflictException extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}
~~~

The service checks order state before cancelling:

~~~java
public OrderResponse cancel(UUID orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    if (order.getStatus() != OrderStatus.PENDING) {
        throw new OrderStateConflictException(
            "Only pending orders can be cancelled"
        );
    }

    order.setStatus(OrderStatus.CANCELLED);
    return mapper.toResponse(repository.save(order));
}
~~~

This is illustrative logic. In production applications, handle concurrency when two requests cancel the same order simultaneously—for instance via optimistic locking or conditional database updates.

## 12. Creating the Controller and Tag

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(
    name = "Orders",
    description = "Create, look up, and cancel orders"
)
@SecurityRequirement(name = "bearerAuth")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

@Tag groups operations in Swagger UI. @SecurityRequirement indicates that the controller's operations require the declared security scheme. If one operation is public, apply security requirements per method instead of at the class level.

## 13. Documenting the create order operation

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Create an order",
    description = "Creates a new order. The server generates the ID, PENDING status, and timestamp."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Missing or invalid token"
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Not authorized to create orders"
    ),
    @ApiResponse(
        responseCode = "500",
        description = "Unexpected server error",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {

    OrderResponse created = orderService.create(request);
    URI location = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .path("/{orderId}")
        .buildAndExpand(created.getOrderId())
        .toUri();

    return ResponseEntity.created(location).body(created);
}
~~~

POST returns 201 Created and a Location header pointing to the newly created resource. The generic type of ResponseEntity tells Springdoc the response body is OrderResponse; @ApiResponse explicitly adds status codes and schemas for key cases.

## 14. Documenting the get order operation

~~~java
@GetMapping("/{orderId}")
@Operation(
    operationId = "getOrderById",
    summary = "Look up an order",
    description = "Returns an order by UUID."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Order found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Missing or invalid token"
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Not authorized to view the order"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Order not found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "500",
        description = "Unexpected server error",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public OrderResponse getById(
        @Parameter(
            description = "UUID of the order",
            example = "4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001"
        )
        @PathVariable UUID orderId) {
    return orderService.findById(orderId);
}
~~~

UUID is used directly in the method signature so Spring and OpenAPI both express type string with format uuid. The path parameter is required because the URL template requires an orderId value.

## 15. Documenting the cancel order operation

~~~java
@PostMapping("/{orderId}/cancel")
@Operation(
    operationId = "cancelOrder",
    summary = "Cancel an order",
    description = "Only orders in PENDING status can be cancelled."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Order transitioned to CANCELLED",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Missing or invalid token"
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Not authorized to cancel the order"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Order not found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Current state does not allow cancellation",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "500",
        description = "Unexpected server error",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public OrderResponse cancel(@PathVariable UUID orderId) {
    return orderService.cancel(orderId);
}
~~~

Cancelling an order is an action with side effects, so using POST for the action endpoint is an understandable choice in this contract. The description states the status precondition; 409 expresses conflict with the resource's current state.

## 16. Assembling the methods into a complete Controller

The three methods create, getById, and cancel belong inside the same OrderController:

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders", description = "Create, look up, and cancel orders")
@SecurityRequirement(name = "bearerAuth")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    // create(...)
    // getById(...)
    // cancel(...)
}
~~~

When assembling the source, preserve the method annotations from previous sections. Do not create two methods with the same mapping and do not place multiple composed mapping annotations on the same method.

## 17. Standardizing exceptions with ControllerAdvice

Validation errors are converted into ApiError:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        List<FieldViolation> violations = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> new FieldViolation(
                error.getField(),
                error.getDefaultMessage()
            ))
            .toList();

        ApiError body = new ApiError(
            Instant.now(),
            400,
            "VALIDATION_FAILED",
            "Request contains invalid fields",
            request.getRequestURI(),
            violations
        );
        return ResponseEntity.badRequest().body(body);
    }
}
~~~

For Java versions that do not support Stream.toList(), use Collectors.toList(). The ApiError structure must match the schema declared in OpenAPI.

## 18. Mapping 404 and 409 errors

~~~java
@ExceptionHandler(OrderNotFoundException.class)
ResponseEntity<ApiError> handleNotFound(
        OrderNotFoundException ex,
        HttpServletRequest request) {

    ApiError body = new ApiError(
        Instant.now(),
        404,
        "ORDER_NOT_FOUND",
        "Order was not found",
        request.getRequestURI(),
        List.of()
    );
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
}

@ExceptionHandler(OrderStateConflictException.class)
ResponseEntity<ApiError> handleConflict(
        OrderStateConflictException ex,
        HttpServletRequest request) {

    ApiError body = new ApiError(
        Instant.now(),
        409,
        "ORDER_STATE_CONFLICT",
        "Current order state does not allow this operation",
        request.getRequestURI(),
        List.of()
    );
    return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
}
~~~

Public messages should not expose internal exception details. Stable error codes let clients branch programmatically instead of matching prose strings.

## 19. Handling unexpected errors

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<ApiError> handleUnexpected(
        Exception ex,
        HttpServletRequest request) {

    log.error("Unhandled API error at {}", request.getRequestURI(), ex);

    ApiError body = new ApiError(
        Instant.now(),
        500,
        "INTERNAL_ERROR",
        "An unexpected error occurred",
        request.getRequestURI(),
        List.of()
    );
    return ResponseEntity.internalServerError().body(body);
}
~~~

The catch-all exception handler is only a fallback layer. Never let public responses expose stack traces, table names, SQL, or credentials. Security exceptions may be handled by Spring Security in the filter chain before reaching ControllerAdvice; test 401/403 at the right layer. In this example, ApiError is used for errors handled by the controller and ControllerAdvice. 401/403 responses are produced in the security layer; if you want them to return ApiError too, configure AuthenticationEntryPoint and AccessDeniedHandler accordingly and document the content schema on those two responses.

## 20. Declaring OpenAPI metadata and Bearer scheme

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop Order API",
        version = "1.0.0",
        description = "API for creating, looking up, and cancelling orders"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

info.version is the version of the published API contract. It does not automatically equal the Maven version, Spring Boot version, or Git tag version. Pick a clear versioning policy and keep it consistent across the document, artifacts, and release notes.

## 21. Configuring Spring Security Resource Server

For a JWT Resource Server, runtime configuration can look like:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/v3/api-docs", "/v3/api-docs/**",
                    "/v3/api-docs.yaml", "/swagger-ui/**",
                    "/swagger-ui.html").permitAll()
                .requestMatchers("/api/orders/**").authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                Customizer.withDefaults()
            ))
            .build();
    }
}
~~~

This is an illustrative configuration. In production, you may need to protect OpenAPI docs or separate public/internal documents according to organizational policy. If docs are public, permit only the endpoints that truly need to be public. If docs are internal, protect JSON, YAML, and Swagger UI alike.

The OpenAPI security scheme only describes how clients send tokens. Spring Security is what validates tokens and enforces authorization. Never put real tokens in examples or OpenAPI files.

## 22. Adding package and path scan configuration

If the application has multiple controllers, restrict documentation scope intentionally via configuration:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.shop.order
  paths-to-match:
    - /api/**
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

Do not use package/path filters to hide an endpoint that the system still leaves accessible when the real goal is security. Filters only control documentation scope.

If you have separate public and internal groups, create separate GroupedOpenApi beans and inspect each document.

## 23. Generating OpenAPI JSON and YAML

Start the application with the profile used for verification:

~~~bash
./mvnw spring-boot:run
~~~

Fetch JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Fetch YAML:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  -o target/openapi.yaml
~~~

Actual paths may vary due to context path, reverse proxy, or springdoc properties. If using groups, request the corresponding group endpoint. Save artifacts from the exact commit and profile being released.

## 24. Inspecting the document structure

Read metadata:

~~~bash
jq '{openapi, info, pathCount: (.paths | length)}' target/openapi.json
~~~

List paths:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Inspect the create order operation:

~~~bash
jq '.paths["/api/orders"].post' target/openapi.json
~~~

Inspect cancel responses:

~~~bash
jq '.paths["/api/orders/{orderId}/cancel"].post.responses' target/openapi.json
~~~

Inspect security schemes:

~~~bash
jq '.components.securitySchemes' target/openapi.json
~~~

The document must contain all three operations, UUID path parameter, request schemas, success responses, errors, and the Bearer scheme. Do not check only that the file exists or parses as JSON; verify contract fields.

## 25. Checking Swagger UI

Open Swagger UI at the configured path, typically:

~~~text
http://localhost:8080/swagger-ui.html
~~~

Verify:

- The Orders tag is present.
- POST create, GET by ID, and POST cancel are all present.
- operationId and summary are meaningful.
- orderId displays as a required path parameter with format UUID.
- The request body shows customerId and items.
- Quantity has minimum 1.
- Responses 201, 200, and error responses have appropriate schemas.
- Security scheme bearerAuth appears under Authorize.

Swagger UI is a visual reader for the OpenAPI document. If the UI does not show an operation, call the JSON endpoint directly to distinguish a document issue from a UI/group-selection issue.

## 26. Writing HTTP integration tests for order creation

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser
    void createOrderReturns201AndLocation() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "f5b5e4d1-aaaa-4bbb-8ccc-123456789abc",
                      "items": [
                        {
                          "productId": "a1d2c3e4-1111-4222-8333-123456789abc",
                          "quantity": 2
                        }
                      ]
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(jsonPath("$.orderId").exists())
            .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
~~~

The example uses a mock user to focus on testing the controller contract. If testing real security tokens, configure a test JWT decoder or test resource server accordingly. Repository data should be isolated so tests are repeatable.

## 27. Testing validation and business errors

~~~java
@Test
@WithMockUser
void invalidOrderReturns400() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "f5b5e4d1-aaaa-4bbb-8ccc-123456789abc",
                  "items": [
                    {
                      "productId": "a1d2c3e4-1111-4222-8333-123456789abc",
                      "quantity": 0
                    }
                  ]
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.fieldErrors").isArray());
}

@Test
@WithMockUser
void unknownOrderReturns404() throws Exception {
    mockMvc.perform(get(
            "/api/orders/00000000-0000-0000-0000-000000000000"
        ))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
}
~~~

Add a 409 test for an order not in PENDING status. The test must establish a reproducible initial state, call cancel, and verify response code ORDER_STATE_CONFLICT.

## 28. Testing authentication and authorization

If the API requires JWTs, test at least:

| Scenario | Expected outcome |
|---|---|
| No token | 401 |
| Invalid signature or expired token | 401 |
| Valid token missing scope/role | 403 |
| Valid token with sufficient permissions | Request processed |

Do not test only with @WithMockUser and conclude the JWT Resource Server is configured properly. @WithMockUser usually tests authorization in the test context; token tests should verify decoder, issuer, audience, and authority mapping per application configuration.

## 29. Writing tests for the OpenAPI document

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentContainsOrderOperationsAndResponses() throws Exception {
        MvcResult result = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode document = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );
        JsonNode paths = document.path("paths");

        assertThat(paths.path("/api/orders").path("post")
            .path("responses").has("201")).isTrue();

        assertThat(paths.path("/api/orders/{orderId}").path("get")
            .path("responses").has("404")).isTrue();

        assertThat(paths.path("/api/orders/{orderId}/cancel").path("post")
            .path("responses").has("409")).isTrue();

        assertThat(document.path("components")
            .path("securitySchemes").has("bearerAuth")).isTrue();
    }
}
~~~

Paths and operations in assertions must match the controller's final mappings. If the code uses a cancel path like /{orderId}/cancel, assert that exact path; the example above shows how to query document structure.

Add assertions for requestBody, OrderResponse schema, ApiError, and path parameters. Document tests must catch cases where an operation exists while its response or security metadata has disappeared.

## 30. Checking JSON and YAML with a validator

Successful JSON parsing does not guarantee OpenAPI compliance. Use a validator compatible with the OpenAPI version emitted by the document.

Example with OpenAPI Generator CLI:

~~~bash
openapi-generator-cli validate -i target/openapi.json
~~~

Example with Redocly CLI:

~~~bash
npx @redocly/cli lint target/openapi.yaml
~~~

Pin tool versions in CI and use the same lint configuration across branches. If the project has custom rules for operationId, tags, security, or error schemas, include those rules in the lint configuration.

Do not turn off rules arbitrarily just to make the pipeline green. If a rule does not fit, document the reason and adjust policy with review.

## 31. Distinguishing OpenAPI bugs from runtime bugs

| Symptom | Where to investigate |
|---|---|
| HTTP route works but operation is missing | @Hidden, package/path filters, groups, or customizers |
| OpenAPI has operation but HTTP returns 404 | Runtime mappings, context path, or running instance |
| OpenAPI says 201 but controller returns 200 | ResponseEntity and status handling |
| Schema states minimum quantity 1 but server accepts 0 | @Valid, validation dependency, and service rules |
| Response body differs from schema | Jackson, DTO mapping, and custom serializers |
| Swagger UI hides operation while JSON has it | UI URL, group selection, or cache |
| Security scheme is in document but endpoint allows anonymous | Spring Security runtime configuration |

Compare three sources: the OpenAPI document, actual HTTP responses, and integration tests. Whenever one source diverges from the other two, the contract is not yet verified.

## 32. Classifying compatible and breaking changes

Before releasing, compare the new document against the published baseline.

| Change | Common impact |
|---|---|
| Add optional query parameter | Usually compatible |
| Add new operation | Usually compatible |
| Add required request field | Potentially breaking for old clients |
| Remove request/response field | Potentially breaking |
| Change data type or format | Breaking |
| Change path or HTTP method | Breaking |
| Change response status or schema | Potentially breaking |
| Add enum value | Can break clients using exhaustive switches |
| Tighten validation | Can break previously valid requests |
| Change security requirement | Can break integrating clients |
| Hide or remove operation | Breaking for clients using that operation |

Not every additive change is safe. For example, adding an enum value can break generated client code if it cannot handle unknown values. Evaluate impact based on how consumers use the contract, not purely by JSON structure.

## 33. Comparing against baseline with a diff tool

Save the baseline of the previous release, such as openapi-released.json. After generating the new document, run a diff tool:

~~~bash
oasdiff breaking openapi-released.yaml target/openapi.yaml
~~~

The command illustrates using the oasdiff CLI; pin the version and check the syntax of your chosen tool release. Some organizations use an OpenAPI diff plugin in Maven or an equivalent CI service.

The pipeline should:

1. Halt release if unapproved breaking changes are present.
2. Allow compatible changes through normal review.
3. Require a new API version or migration plan when a breaking change is approved.
4. Archive the diff report alongside the artifact.

Do not treat diff output as a substitute for business review. Tools detect schema changes, yet do not understand full API semantics.

## 34. Managing contract versions

Distinguish the different versions:

| Version type | Meaning |
|---|---|
| Spring Boot | Application platform |
| Springdoc | OpenAPI generation library |
| OpenAPI specification | Standard version recorded in the document |
| API contract version | Version managed by the API team in info.version or release policy |
| Application build version | Application artifact version |

Do not treat these versions as interchangeable. An application can upgrade Springdoc without changing its contract; likewise, it can change its API contract without upgrading Springdoc.

For breaking changes, choose a clear versioning policy: path versioning such as /api/v2, header-based versioning, or another organizational policy. The document must accurately reflect the published version.

## 35. Packaging OpenAPI artifacts

Once tests and validation pass, create a versioned artifact directory:

~~~text
build/
└── api-contract/
    ├── openapi.json
    ├── openapi.yaml
    ├── compatibility-report.txt
    └── manifest.json
~~~

The manifest can record:

~~~json
{
  "service": "shop-order-api",
  "apiVersion": "1.0.0",
  "applicationVersion": "2026.11.20",
  "sourceRevision": "git-commit-sha",
  "openapiFile": "openapi.yaml"
}
~~~

Manifest values are illustrative metadata. In CI, populate version and commit from the build environment; never hardcode fake commits into artifacts.

Store both JSON and YAML if consumers need both formats. If only one format is canonical, clearly define the canonical format and generate the other from the exact same document to avoid drift.

## 36. End-to-end CI workflow

A minimal pipeline includes these steps:

~~~text
1. Checkout source
2. Resolve dependency versions
3. Compile and unit tests
4. Start application with contract profile
5. Export OpenAPI JSON/YAML
6. Parse and lint document
7. Run HTTP integration tests
8. Run OpenAPI document tests
9. Compare against released baseline
10. Build artifact and manifest
11. Publish artifact after gates pass
12. Verify artifact from published URL
~~~

This can be split across multiple jobs, but the published artifact must be the exact file that passed validation and diffing. Never regenerate the document from a different runtime after checks and publish a different file.

## 37. Example contract verification script in CI

~~~bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="$CONTRACT_BASE_URL"
OUT_DIR="target/api-contract"

mkdir -p "$OUT_DIR"

curl --fail --silent --show-error \
  "$BASE_URL/v3/api-docs" \
  -o "$OUT_DIR/openapi.json"

curl --fail --silent --show-error \
  "$BASE_URL/v3/api-docs.yaml" \
  -o "$OUT_DIR/openapi.yaml"

openapi-generator-cli validate -i "$OUT_DIR/openapi.json"
oasdiff breaking "contracts/released/openapi.yaml" "$OUT_DIR/openapi.yaml"

printf '%s\n' "OpenAPI contract checks passed"
~~~

This is an illustrative command skeleton. A real pipeline must start the application first and set CONTRACT_BASE_URL, configure authentication if documentation endpoints are protected, pin CLI versions, and decide how to handle exit codes when diffs find breaking changes.

If no baseline exists yet for the first release, create the baseline after the contract is reviewed and approved. Never bypass the diff gate permanently just because the first run has no comparison file.

## 38. Publishing documentation

Choose a suitable distribution channel:

- Internal artifact repository.
- Developer portal.
- Static documentation site.
- Object storage with versioned paths.
- API catalog or partner portal.

Example published URLs:

~~~text
https://docs.example.invalid/apis/shop-order/1.0.0/openapi.yaml
https://docs.example.invalid/apis/shop-order/1.0.0/openapi.json
~~~

These are illustrative URLs. When publishing, keep artifacts immutable per version. If a latest alias is needed, update the alias only after the specific version has been published and verified.

Never publish internal groups or documentation containing non-partner details to a public portal. OpenAPI documents can expose endpoints, schemas, and security assumptions even when they contain no live data.

## 39. Post-release verification

After publishing:

1. Download JSON/YAML from the published public or internal URL.
2. Parse the file and verify the OpenAPI version.
3. Check info.title and info.version.
4. Confirm key paths and operationIds.
5. Confirm security schemes.
6. Run the validator on the downloaded artifact.
7. Compare checksums against the CI-verified artifact.
8. Open the developer portal and confirm the right version appears.
9. Test links from guide documentation or SDK generators.

Do not merely confirm the upload command exited 0. Verify that downloaded content matches the exact verified artifact.

## 40. Rollback and handling release errors

If incorrect documentation was published:

- Retain the faulty artifact for audit if policy requires.
- Mark the version or portal entry as withdrawn/deprecated per procedure.
- Restore the latest alias to the previously verified version.
- Publish the corrected artifact under an appropriate version or patch release.
- Rerun the validator and compatibility diff.
- Announce the change through organizationally approved release channels.

Do not silently overwrite a versioned artifact that consumers may already have downloaded. Consumers may have generated SDKs or cached the old contract; mutating immutable files destroys reproducibility.

## 41. Protecting documentation and separating public/internal

OpenAPI is metadata, yet it still reveals the API surface. Before publishing, determine:

- Which documentation is public.
- Which documentation is restricted to staff or partners.
- Whether internal endpoints are excluded from public groups.
- Whether Swagger UI requires authentication.
- Whether JSON/YAML endpoints enforce the same access policy as the UI.
- Whether examples contain real tokens, emails, or production data.
- Whether server URLs point to the appropriate production environment.

Hiding an operation with @Hidden does not replace authorization. Conversely, protecting Swagger UI while leaving JSON endpoints public still exposes the document. Check every documentation URL.

## 42. Pre-release checklist

- [ ] Controller mappings match the approved contract.
- [ ] Request/response DTOs are separated from entities.
- [ ] Validation is enabled at runtime.
- [ ] OperationIds are stable and unique.
- [ ] Request bodies, parameters, and response schemas have descriptions.
- [ ] Success and error status codes match runtime behavior.
- [ ] Security schemes match actual authentication.
- [ ] Public/internal groups are filtered accurately.
- [ ] OpenAPI JSON/YAML is exported from the right profile.
- [ ] OpenAPI validator passes.
- [ ] HTTP integration tests pass.
- [ ] OpenAPI document tests pass.
- [ ] Breaking change diffs are reviewed.
- [ ] Contract version and application build version are tracked separately.
- [ ] Artifacts include manifest and source revision.
- [ ] Artifacts are published under immutable versions.
- [ ] Post-release URLs serve the expected content.

## 43. Troubleshooting table for the end-to-end workflow

| Symptom | Possible cause | What to check |
|---|---|---|
| Path missing from document | Controller not scanned or filtered/hidden | Spring mappings, package scan, groups, and @Hidden |
| Path present but error responses missing | Missing @ApiResponse or advice not reflected | Check operation responses and ControllerAdvice |
| Schema differs from actual JSON | Jackson, DTO mapping, or custom serializer | Compare actual response with components/schemas |
| Validation test does not return 400 | Missing @Valid or validation dependency | Check request binding and validation provider |
| 401/403 differs from documentation | Security filter chain or authority mapping | Test tokens and scopes/roles |
| Validator reports errors | Invalid OpenAPI document or broken schema | Inspect error location and fix metadata |
| Diff reports breaking change | Path, required field, type, response, or security changed | Review baseline and consumer impact |
| Artifact published but portal unchanged | Cache, alias, or wrong version URL | Fetch the specific versioned URL directly |
| Public doc contains internal path | Misconfigured group filter or customizer | Inspect each document group |
| UI mismatches JSON | UI points to different document or cache | Check config URL and fetch JSON directly |

## 44. Extension exercises

After completing the basic flow, extend it with these requirements:

1. Add GET /api/orders supporting pagination and status filtering; document query parameters and page response.
2. Add an idempotency key to POST create; document the header, behavior when resending the same key, and conflict response.
3. Add an endpoint accessible only to ADMIN; declare security requirements and test 403.
4. Create public and internal GroupedOpenApi definitions; verify operations appear only in the right group.
5. Add a status enum and assess the impact of adding new values.
6. Create contract baseline version 1.0.0, then try removing a response field to observe what the diff reports.
7. Design version 2 for a breaking change and publish both documents side by side.
8. Add a checksum to the manifest and verify it after downloading the artifact from the portal.

## 45. Key takeaways

- Define the contract before writing controllers.
- Spring mappings and security drive runtime behavior; OpenAPI annotations document the contract.
- DTOs and Bean Validation supply schemas and input constraints.
- ControllerAdvice standardizes error responses, while security filters can handle 401/403 before controllers.
- Springdoc generates OpenAPI from handler mappings and metadata; JSON/YAML are the artifacts to verify.
- HTTP integration tests verify actual statuses, headers, and bodies.
- OpenAPI document tests verify paths, operations, schemas, responses, and security.
- Validators check structure; compatibility diffs detect changes against the baseline.
- Springdoc version, OpenAPI specification version, API contract version, and application version are distinct version types.
- Publish only artifacts that have passed tests, validation, and review.
- Published artifacts should be immutable and tied to both version and source revision.
- Re-verify URLs after publishing to guarantee consumers receive the exact intended content.
- Hiding operations from documentation never replaces authentication or authorization.

An end-to-end workflow connects controllers, metadata, OpenAPI, tests, and publishing into a verifiable chain. Keep the contract consistent from business decisions to HTTP responses, inspect generated documents instead of only reading annotations, diff against the baseline before release, and verify artifacts after publishing. When these steps are automated, OpenAPI becomes a reviewable, reproducible contract rather than a Swagger page checked manually.

## References

- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc OpenAPI FAQ: https://springdoc.org/faq.html
- Spring Boot testing documentation: https://docs.spring.io/spring-boot/reference/testing/index.html
- Spring Security OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- OpenAPI Generator validation: https://openapi-generator.tech/docs/usage/
- oasdiff: https://github.com/Tufin/oasdiff
- Redocly CLI lint: https://redocly.com/docs/cli/commands/lint
