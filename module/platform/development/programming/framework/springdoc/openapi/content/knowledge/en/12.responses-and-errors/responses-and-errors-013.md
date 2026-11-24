# Keeping Documented Status Codes Consistent with Actual Responses

A useful OpenAPI specification must accurately describe what clients receive when calling the API. If the documentation says an operation returns HTTP 404 with an ApiError body while the application returns 200 with an empty body, clients will handle it incorrectly even if Swagger UI renders cleanly. Likewise, docs might state 201 while the controller returns 200, or describe a Location header that the actual response omits.

With springdoc-openapi, metadata from controllers and DTOs is converted into OpenAPI documentation. Docs can be inferred from return types, mappings, and annotations; actual responses, meanwhile, are determined by Spring MVC, ResponseEntity, @ResponseStatus, exception handlers, Spring Security, and gateways. This lesson covers how to keep both sides synchronized and verify them through automated tests.

## 1. Distinguishing the Response Contract from Runtime Responses

There are two outputs to compare:

- **OpenAPI contract:** describes status codes, descriptions, response bodies, schemas, media types, and headers that clients can receive.
- **Runtime response:** the actual HTTP response returned by the application or infrastructure when handling a request.

springdoc-openapi builds the contract from source code and metadata. The library does not execute every business branch to verify responses. For instance, declaring @ApiResponse(responseCode = "404") does not make a controller automatically return HTTP 404; declaring the ApiError schema does not create error bodies either.

A response is consistent only when all of the following match:

| Aspect | In OpenAPI | At runtime |
|---|---|---|
| Status code | responses["404"] | Actual HTTP status is 404 |
| Body | content and schema | Actual JSON/XML/text payload sent |
| Media type | application/json, application/pdf... | Content-Type header |
| Headers | headers such as Location, ETag, Retry-After | Actual headers in the response |
| Semantics | description of the response | Corresponding business behavior |
| Trigger conditions | Operation and response descriptions | Controller branch, exception handler, security, or gateway |

Do not compare HTTP status codes alone. Bodies can fail schema compliance, Content-Type can be wrong, or advertised headers can be missing.

## 2. Sources Determining Status Codes in Spring

In a Spring Boot application, status codes can be decided by several mechanisms:

| Mechanism | Effect |
|---|---|
| Normal controller return value | Spring usually returns 200 OK when processing succeeds with a body |
| @ResponseStatus | Sets a fixed status on a marked handler or exception |
| ResponseEntity | Chooses status, headers, and body per branch |
| @ExceptionHandler / @RestControllerAdvice | Maps exceptions to HTTP responses |
| Spring Security | Handles authentication and authorization before or outside controllers |
| Reverse proxy / API gateway | May reject, rate-limit, or generate responses before requests reach the app |

Because multiple sources participate, reading only a controller method is not enough to know every runtime response. Inspect relevant exception handlers, security configurations, and gateway policies as well.

Example of a controller returning an object:

~~~java
@GetMapping("/{id}")
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

If the method returns normally, Spring typically produces a 200 response on success. Yet if the service throws OrderNotFoundException, the status depends on exception handlers or another exception-handling mechanism.

When a controller needs to return multiple status codes based on outcomes, ResponseEntity makes each branch explicit:

~~~java
@GetMapping("/{id}")
public ResponseEntity<?> getOrder(@PathVariable String id) {
    return orderService.findById(id)
        .<ResponseEntity<?>>map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "ORDER_NOT_FOUND",
                "Order not found",
                null
            )));
}
~~~

In this example, the not-found branch returns 404 with an ApiError body. If the API instead chooses ResponseEntity.notFound().build() with no error body, both OpenAPI schemas and tests must reflect a bodyless response.

## 3. @ApiResponse Describes, While @ResponseStatus and ResponseEntity Execute

OpenAPI annotations publish the contract:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Order created",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
~~~

The snippet above only describes a 201 response and the OrderResponse schema. For the controller to actually return 201, you need an execution mechanism, for example:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Or:

~~~java
@PostMapping
public ResponseEntity<OrderResponse> create(
    @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.getId());

    return ResponseEntity.created(location).body(created);
}
~~~

ResponseEntity.created(location) returns 201 Created and the Location header. If OpenAPI documents Location, the runtime response must send that header.

Metadata and implementation can be combined:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Create a new order"
)
@ApiResponse(
    responseCode = "201",
    description = "Order has been created",
    headers = @Header(
        name = "Location",
        description = "URL of the newly created order",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public ResponseEntity<OrderResponse> create(
    @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.getId());
    return ResponseEntity.created(location).body(created);
}
~~~

During code reviews, inspect both annotations and return statements together. Never infer runtime status from responseCode in an annotation.

## 4. Mapping Exceptions to Consistent Responses

Business errors are often represented as exceptions and handled centrally via @RestControllerAdvice. Example:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
        OrderNotFoundException exception
    ) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order not found",
            null
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ApiError> handleConflict(
        OrderConflictException exception
    ) {
        ApiError body = new ApiError(
            "ORDER_CONFLICT",
            "Order has changed",
            null
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
~~~

If an operation can raise both exceptions, the documentation must publish 404 and 409 with the ApiError schema. Declaring responses on the controller does not create exception mappings; declaring @ExceptionHandler does not automatically guarantee every operation has the matching OpenAPI metadata.

A mapping convention a team can adopt:

| Scenario | Typical status | Runtime check |
|---|---|---:|
| Malformed request or failed type conversion | 400 | Jackson/Spring MVC rejects request |
| Data fails validation | 400 or 422 per API policy | Bean Validation and exception handler |
| Unauthenticated | 401 | AuthenticationEntryPoint or security filter |
| Authenticated without permission | 403 | AccessDeniedHandler or security policy |
| Resource does not exist | 404 | Controller or exception handler |
| State or version conflict | 409 | Business rule |
| Rate limit exceeded | 429 | Rate limiter or gateway |
| Unexpected failure | 500 | Exception handler or container |

These are common choices rather than mandatory mappings for every application. What matters is picking a consistent team policy, implementing it faithfully, and documenting that policy in the spec.

## 5. Do Not Forget Responses Produced by Spring Security

Requests blocked by Spring Security may never reach a controller. Consequently, @RestControllerAdvice does not necessarily handle authentication and authorization responses.

Typically:

- AuthenticationEntryPoint determines the response when the caller is unauthenticated or credentials are invalid.
- AccessDeniedHandler determines the response when the caller is authenticated yet lacks permission.

If the API uses a unified JSON error body, configure both handlers to return that same structure or the structure documented in OpenAPI. Verify status, body, Content-Type, and required security headers.

OpenAPI can describe security requirements globally or per operation alongside 401 and 403 responses. However, security schemes only describe how clients send credentials; they do not configure Spring Security.

A public endpoint may have no 401 or 403. An endpoint protected by a bearer token may have both. Publish only the codes matching actual policy.

## 6. Comparing Status Codes with HTTP Semantics

Using accurate status codes helps clients know how to proceed. Common points of confusion:

| Code | Meaning | What to verify |
|---|---|---|
| 200 OK | Request succeeded | Does the body match the schema? |
| 201 Created | Resource created | Is Location returned if committed by the API? |
| 202 Accepted | Request accepted for processing | Is there a way to track the task? |
| 204 No Content | Succeeded, no body | Is the response truly empty? |
| 400 Bad Request | Invalid request | Are parse, binding, and validation errors mapped consistently? |
| 401 Unauthorized | Missing or invalid credentials | Are required challenges/headers present? |
| 403 Forbidden | Access forbidden | Do body and status match security policy? |
| 404 Not Found | Resource or endpoint not found | Does it avoid revealing resources the caller cannot view? |
| 409 Conflict | Conflict with current state | Do clients receive enough detail to resolve the conflict? |
| 422 Unprocessable Content | Understood content cannot be processed by rules | Does the API use 422 consistently instead of 400? |
| 429 Too Many Requests | Too many requests in a time window | Are Retry-After or quota headers included? |
| 500 Internal Server Error | Unexpected server error | Does it avoid leaking stack traces or internal data? |

In particular, 202 does not mean the job has finished; 204 must not carry a response body; 401 and 403 have distinct meanings; 409 is for state conflicts rather than general validation errors.

## 7. Ensuring Bodies and Schemas Match

Suppose OpenAPI describes an error as:

~~~yaml
ApiError:
  type: object
  required:
    - code
    - message
  properties:
    code:
      type: string
    message:
      type: string
    traceId:
      type: string
~~~

The runtime response must have a matching structure:

~~~json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found",
  "traceId": "req-7f9a2c"
}
~~~

If the exception handler actually returns a different object—such as Spring's ProblemDetail with type, title, status, detail, and instance—the ApiError schema fails to describe that response accurately.

With Spring Framework 6+, ProblemDetail is an option for standardizing errors under Problem Details. If your app uses ProblemDetail, describe the matching schema and inspect the serialized JSON. Never declare ApiError simply because the team planned to use that DTO; verify the actual body.

Things to compare:

- Field names, data types, and nesting.
- Required, nullable, and optional fields.
- Enums and date/time formats.
- Validation error list structure.
- Error code names and semantics.
- Sensitive information that must never be sent to clients.

A schema can be syntactically valid yet semantically wrong relative to the runtime body.

## 8. Ensuring Media Types Match Content-Type

In OpenAPI, response content declares media types such as application/json, application/xml, text/csv, or application/pdf. At runtime, the HTTP response carries a matching Content-Type header.

Documentation example:

~~~yaml
responses:
  '200':
    description: Product information
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductResponse'
~~~

If a controller returns JSON while Content-Type is text/plain, client generators may mishandle the body. If an endpoint downloads a PDF while the spec declares application/json, clients may attempt to parse binary bytes as JSON.

Check:

- @RequestMapping(produces = ...) and message converter configuration.
- Actual response Content-Type.
- Request Accept headers if the endpoint supports multiple representations.
- Corresponding schemas for each media type.
- How client generators handle files or streams.

Never declare a media type in OpenAPI solely to show an option in Swagger UI. The application must genuinely support that content type.

## 9. Ensuring Headers Are Documented and Sent at Runtime

Important headers are part of the response contract:

| Header | Purpose |
|---|---|
| Location | Address of newly created resource or task to track |
| ETag | Representation version identifier |
| Retry-After | Duration or timestamp when clients should retry |
| X-Request-Id | Request trace identifier if advertised by the API |
| Cache-Control | Caching policy |

If OpenAPI documents Location for 201, tests must assert the response includes Location. If documentation describes Retry-After for 429, the rate limiter/gateway must emit that header per policy.

Declaration example:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Resource created",
    headers = @Header(
        name = "Location",
        description = "URL of the new resource",
        schema = @Schema(type = "string", format = "uri")
    )
)
~~~

Annotations do not emit headers automatically. Controllers or infrastructure components must send them.

## 10. Writing MockMvc Tests for Actual Responses

MockMvc is well-suited for testing Spring MVC controllers without starting a full server. Tests should assert status, media type, headers, and body.

Example testing the not-found branch:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returns404WithApiErrorWhenOrderDoesNotExist() throws Exception {
        given(orderService.findById("missing"))
            .willReturn(Optional.empty());

        mockMvc.perform(get("/api/orders/{id}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value("Order not found"));
    }
}
~~~

The mock annotation name depends on your Spring Boot and Spring Test versions. Versions without @MockitoBean can use @MockBean. Use the API compatible with your installed dependencies.

A creation test can verify 201 and Location:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":"C-100","items":[{"productId":"P-1","quantity":2}]}
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").isNotEmpty());
~~~

These are illustrative examples; prepare services, DTOs, and test fixtures matching your app. For 204 responses, assert the status and verify an empty body. For validation errors, submit invalid requests and assert both status and the error structure promised by the exception handler.

## 11. Verifying OpenAPI Responses with Tests

Alongside HTTP tests, verify the documentation generated by springdoc. When the test context loads the OpenAPI configuration, /v3/api-docs can be queried via MockMvc:

~~~java
@Test
void openApiDocumentsOrderResponses() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404'].content['application/json'].schema"
        ).exists());
}
~~~

This test verifies that metadata is published, though it does not prove runtime status 404 actually works. Therefore, keep both test suites:

1. **OpenAPI tests:** verify the spec includes required statuses, schemas, media types, and headers.
2. **Runtime tests:** send requests and assert status, body, Content-Type, and headers.

You can add deeper assertions verifying `$ref` targets point to existing components, or run OpenAPI validators in CI. For grouped documentation, query each group's endpoint individually.

## 12. Integration Testing Through a Real Server

MockMvc bypasses deployment infrastructure such as reverse proxies, gateways, TLS termination, or external rate limiters. If the public contract includes responses produced by infrastructure, test in an integrated environment.

For servlet applications, use @SpringBootTest(webEnvironment = RANDOM_PORT) with a test HTTP client calling the running server. For WebFlux, use WebTestClient.

An integration check should verify:

- Public URLs and path prefixes.
- Status codes after requests traverse the gateway.
- Content-Type and body.
- Security, CORS, Location, or Retry-After headers when present.
- Responses when tokens are missing, invalid, or lack permissions.
- Responses when rate limits are exceeded.
- Error responses when backend services are unavailable, if the gateway commits to an error format.

Not every gateway response originates from the Spring app. If a gateway alters statuses or bodies, the public spec must describe what clients actually see, or documentation must clarify the boundary between backend API and gateway.

## 13. Automated Comparison of OpenAPI and Runtime Contracts

One control strategy is saving OpenAPI JSON as an artifact and using test/contract tooling to compare:

- Published status codes against statuses observed in integration tests.
- Response schemas against actual JSON bodies.
- Media types against Content-Type.
- Published headers against actual headers.
- Operations changed compared to the previously released spec.

You can write dedicated tests for critical operations or use contract-testing frameworks to verify consumer/provider alignment. Regardless of tooling, tests must verify against real responses or fixtures derived from the implementation. Comparing an OpenAPI file against itself cannot detect a controller returning the wrong status.

When storing spec snapshots, review diffs whenever modifying controllers, DTOs, exception handlers, security, or gateway rules. Status code changes can be breaking changes because clients branch logic based on HTTP codes.

## 14. Common Mismatches

| Mismatch | Cause | Fix |
|---|---|---|
| Spec lists 201 while runtime returns 200 | Only added @ApiResponse without setting runtime status | Use ResponseEntity.created or @ResponseStatus(CREATED) |
| Spec lists 404 with ApiError while runtime has no body | Controller uses notFound().build() | Return an error body or update schema to bodyless response |
| Runtime returns 409 while spec only lists 400 | Missing business exception documentation | Add @ApiResponse 409 and tests |
| Spec lists Location while runtime lacks header | Only declared metadata | Add header to ResponseEntity and verify in tests |
| Spec lists application/json while runtime returns text/plain | Media type or message converter mismatch | Align produces, Content-Type, and OpenAPI content |
| Security returns 401/403 missing from spec | Security responses not documented | Declare responses and matching security requirements |
| Gateway returns 429 missing from spec | Rate limiting lives outside the app | Update public contract and test through the gateway |
| Error body differs from schema | Exception handler returns a different DTO | Use the matching schema or update response DTO |
| 204 documented with a body | Response annotation declares inappropriate content | Remove content and verify empty body |
| Tests assert only status | Missing body, header, and media type checks | Add assertions for the entire response contract |

## 15. Review Workflow When Changing Responses

When editing controllers or error handling, follow this sequence:

1. Identify every branch returnable from controllers, services, and exception handlers.
2. Check whether security filters, gateways, or rate limiters can produce distinct responses.
3. Update the implementation so status, body, media type, and headers comply with API policy.
4. Update @ApiResponse/@ApiResponses and corresponding schemas.
5. Fetch /v3/api-docs and inspect springdoc's actual output.
6. Run runtime tests for every important status branch.
7. Compare the updated spec against the released version and evaluate client impact.
8. Archive the spec and test results as traceable artifacts.

If a status code can no longer occur, remove or update stale metadata. If a new branch is added, update implementation, documentation, and tests in the same change.

## 16. Consistency Checklist

- [ ] Status codes in @ApiResponse match runtime responses.
- [ ] Every ResponseEntity branch is documented.
- [ ] Exception handlers have matching status and schema mappings.
- [ ] Security responses 401/403 reflect actual configuration.
- [ ] Gateway responses such as 429 are accounted for if part of the public contract.
- [ ] Runtime bodies match schemas, including fields, types, enums, and nullability.
- [ ] Content-Type matches media types in OpenAPI.
- [ ] Headers such as Location, ETag, and Retry-After are sent when advertised.
- [ ] 204 responses have no body.
- [ ] Tests verify status, body, headers, and media type.
- [ ] OpenAPI tests verify responses and schemas at /v3/api-docs.
- [ ] Integration tests cover infrastructure-generated responses if needed.
- [ ] The new spec has been diffed against the previous release.

## 17. References

- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Response Object](https://spec.openapis.org/oas/latest.html#response-object)
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework – Exception handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Security – Exception translation](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [springdoc-openapi – official documentation](https://springdoc.org/)

springdoc-openapi generates documentation from controllers and metadata, while Spring MVC, exception handling, security, and gateways produce runtime responses. Inspect both OpenAPI JSON and actual HTTP responses. When both sides are verified in the same CI pipeline, status or schema drift is caught before clients receive a broken contract.
