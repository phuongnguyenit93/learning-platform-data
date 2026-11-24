# Verifying Requests, Responses, and Error Schemas

An OpenAPI document is only valuable when it accurately reflects what the API actually accepts and returns. Contract testing must verify both sides: valid and invalid requests are handled according to published rules, and success and error responses carry the status codes, headers, media types, and schemas promised in the documentation.

With Spring Boot and springdoc-openapi, verify three layers:

1. **HTTP runtime contract:** endpoints accept the expected methods, paths, query/header parameters, content types, and request bodies, and return the expected statuses, headers, media types, and response bodies.
2. **OpenAPI document contract:** `/v3/api-docs` accurately describes operations, parameters, request schemas, response schemas, and errors.
3. **Consistency between runtime and documentation:** every significant server behavior is documented, and every published contract is executable or clearly accounted for.

A test checking only HTTP 200 is insufficient. An endpoint might return 200 while omitting a required field or returning the wrong content type, or OpenAPI might still describe a request body different from the runtime DTO. Likewise, clean schemas in docs mean nothing if the controller never enabled Bean Validation and still accepts invalid data.

## 1. What Does a Request Contract Include?

A request contract defines how clients are allowed to call an operation. For each endpoint, verify:

| Component | What to Verify | Example |
|---|---|---|
| HTTP method and path | Matches published operation | `POST /api/products` |
| Path parameters | Name, type, format, and `required` | `id` is a UUID |
| Query parameters | Name, type, defaults, bounds | `page >= 0`, `size <= 100` |
| Headers | Required or optional headers | `Idempotency-Key` |
| Content-Type | Supported request body format | `application/json` |
| Accept | Client-requested response format | `application/json` |
| Request body | Schema, required fields, constraints | `name`, `price`, `category` |
| Security | Authentication and authorization | Bearer token with appropriate scope |

A valid request must satisfy both structural and business rules. For example, `price` may be a positive number per the schema, yet the server may still check for duplicate SKUs or whether the product belongs to an active category. Those rules need separate documentation and tests.

## 2. Response Contracts Include Status, Headers, and Body

A response contract is more than a JSON schema. It also covers status codes, media types, headers, and the conditions under which responses occur.

| Outcome | Common Status | What to Verify |
|---|---:|---|
| Resource created successfully | `201 Created` | New body and `Location` |
| Resource retrieved successfully | `200 OK` | Response schema |
| Deleted successfully without body | `204 No Content` | No response body |
| Malformed structure or validation failure | `400 Bad Request` | Error schema and field violations |
| Unauthenticated | `401 Unauthorized` | Authentication challenge if applicable |
| Insufficient permissions | `403 Forbidden` | Error response per security policy |
| Not found | `404 Not Found` | Error schema |
| Business conflict | `409 Conflict` | Error code and conflict details |
| Unsupported request media type | `415 Unsupported Media Type` | Request `Content-Type` |
| Cannot produce requested representation | `406 Not Acceptable` | `Accept` header |
| Syntactically valid request violating policy | `422 Unprocessable Content` | Only if the API specifies this status |

These are common choices, not mandatory status codes for every API. Pick statuses matching your application's semantics, then apply them consistently across controllers, exception handlers, OpenAPI, and tests.

For example, an API may return `400` for all validation errors or `422` for certain semantic errors. The key is never to document `422` while runtime always returns `400`.

## 3. Bean Validation Must Match the Request Schema

Springdoc can infer certain constraints from Bean Validation annotations. Yet OpenAPI annotations only describe the contract; Bean Validation enforces constraints on incoming requests.

Add the validation dependency if missing:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Example DTO:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(min = 1, max = 80)
    @Schema(
        description = "Display name of the product.",
        example = "Ballpoint pen",
        minLength = 1,
        maxLength = 80
    )
    String name,

    @NotNull
    @Positive
    @Digits(integer = 8, fraction = 2)
    @Schema(
        description = "Selling price must be greater than 0.",
        example = "12500.00",
        minimum = "0",
        exclusiveMinimum = true
    )
    BigDecimal price,

    @NotNull
    @Schema(description = "Product category.", example = "STATIONERY")
    ProductCategory category
) {}
~~~

The controller must enable validation with `@Valid`:

~~~java
@PostMapping("/api/products")
ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());
    return ResponseEntity.created(location).body(created);
}
~~~

Without `@Valid`, DTO constraints may not be enforced at the request boundary as intended. Adding `@Schema(minLength = 1)` without `@NotBlank` or an equivalent validator causes documentation to forbid empty strings while the server still accepts them.

For Spring Boot 3 and above, Bean Validation uses the `jakarta.validation.*` package. Spring Boot 2 projects use `javax.validation.*`. Never mix both namespaces in the same application.

### Distinguishing `required` from `nullable`

A property may be:

- Required to appear in the request.
- Allowed to appear with a `null` value.
- Optional and allowed to be omitted.

`@NotNull` and `@NotBlank` affect runtime validation. `@Schema` and Java types influence how OpenAPI describes the field. Inspect `required` in generated schemas, especially when using records, constructor binding, Jackson settings, or custom converters.

## 4. Testing Valid Requests

In Spring MVC, use `MockMvc` to dispatch requests through the MVC stack and verify responses:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsProductWithValidRequest() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Ballpoint pen",
                      "price": 12500.00,
                      "category": "STATIONERY"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(jsonPath("$.id").isNotEmpty())
            .andExpect(jsonPath("$.name").value("Ballpoint pen"))
            .andExpect(jsonPath("$.price").value(12500.00))
            .andExpect(jsonPath("$.category").value("STATIONERY"));
    }
}
~~~

This test verifies method, path, content type, status, headers, and key response fields. In real tests, choose a test database or mock service matching your scope: controller contract testing vs. full persistence integration testing.

When responses include `Location`, verify the URL points to the newly created resource. If the API uses `ETag`, pagination headers, or correlation IDs, include those headers in contract tests.

## 5. Testing Invalid Requests and Validation Errors

A request test suite should cover these cases:

- Missing required fields.
- Empty or whitespace-only strings.
- Out-of-range numbers.
- Non-existent enum values.
- Malformed UUIDs or date/time formats.
- Malformed JSON syntax.
- Unsupported `Content-Type`.
- Missing or out-of-bounds query parameters.

Example request with blank `name` and negative `price`:

~~~java
@Test
void rejectsInvalidProductRequest() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .content("""
                {
                  "name": " ",
                  "price": -10,
                  "category": "STATIONERY"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.title").value("Request validation failed"))
        .andExpect(jsonPath("$.errors").isArray())
        .andExpect(jsonPath("$.errors.length()").value(2));
}
~~~

The violation count depends on validators, DTOs, and application configuration. This example assumes two violating fields and an exception handler collecting errors into an `errors` array. If your implementation returns only the first error, write tests matching that policy and document it accurately in OpenAPI.

Never assert status `400` alone. Without a stable error schema, consumers must guess body structure or code custom handling per endpoint.

## 6. Standardizing Error Responses with Problem Details

Spring Framework 6 provides `ProblemDetail` to represent HTTP errors per Problem Details for HTTP APIs, now standardized in RFC 9457. With Spring Boot 3+, use `ProblemDetail` as the body for HTTP errors.

A Problem Details document typically contains these fields:

| Field | Meaning |
|---|---|
| `type` | URI identifying the problem type; often a link to error documentation |
| `title` | Short summary of the error type |
| `status` | Corresponding HTTP status code |
| `detail` | Specific explanation for this error occurrence |
| `instance` | URI identifying this specific occurrence |
| Extension members | API-defined extra fields, such as `errors` or `traceId` |

Example validation response:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/products",
  "errors": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Name must not be blank."
    },
    {
      "field": "price",
      "code": "Positive",
      "message": "Price must be greater than zero."
    }
  ]
}
~~~

`application/problem+json` is the media type for Problem Details. Do not document this error body as `application/json` if runtime returns `application/problem+json`.

### Defining a Clear Schema for Validation Errors

Because `ProblemDetail` supports dynamic extension members, define DTOs strictly for OpenAPI schema documentation:

~~~java
@Schema(name = "ValidationProblem", description = "Problem Details for validation errors.")
public record ValidationProblem(
    URI type,
    String title,
    Integer status,
    String detail,
    URI instance,
    List<FieldViolation> errors
) {}

@Schema(name = "FieldViolation", description = "A single field validation error.")
public record FieldViolation(
    String field,
    String code,
    String message
) {}
~~~

These DTOs describe the wire shape the application commits to returning. When runtime returns `ProblemDetail` with an `errors` extension, ensure actual JSON field names, types, and nullability match `ValidationProblem`. Never use an illustrative schema that differs from live responses.

## 7. Building a Consistent Exception Handler

`@RestControllerAdvice` can translate validation and business exceptions into Problem Details:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(
        MethodArgumentNotValidException exception,
        HttpServletRequest request
    ) {
        List<Map<String, String>> errors =
            exception.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "code", error.getCode() == null ? "Invalid" : error.getCode(),
                    "message", error.getDefaultMessage() == null
                        ? "Invalid value"
                        : error.getDefaultMessage()
                ))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "One or more request fields are invalid."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/validation-error"
        ));
        problem.setTitle("Request validation failed");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(
        ProductNotFoundException exception,
        HttpServletRequest request
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested product does not exist."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/product-not-found"
        ));
        problem.setTitle("Product not found");
        problem.setInstance(URI.create(request.getRequestURI()));

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

This is a Spring MVC example. For WebFlux, use the reactive equivalents without depending on `HttpServletRequest`. When reporting validation errors, include only public field names, codes, and approved messages; never return stack traces, SQL, internal class names, or secrets from the request.

Other exceptions such as JSON parse errors, type mismatches, constraint violations, or conflicts may need dedicated handlers. To keep a uniform error schema across the entire API, define explicit mappings for each exception group and test every group.

## 8. Documenting Error Schemas in OpenAPI with `@ApiResponse`

Controllers should advertise both success responses and possible error responses:

~~~java
@Operation(
    operationId = "createProduct",
    summary = "Create a new product"
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Product created",
        headers = @Header(
            name = "Location",
            description = "URL of the newly created product.",
            schema = @Schema(type = "string", format = "uri")
        ),
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request body",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ValidationProblem.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "SKU already exists",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ApiProblem.class)
        )
    )
})
@PostMapping("/api/products")
ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    // Implementation
}
~~~

Example using `ApiProblem` for general business errors:

~~~java
@Schema(name = "ApiProblem", description = "Problem Details for API errors.")
public record ApiProblem(
    URI type,
    String title,
    Integer status,
    String detail,
    URI instance
) {}
~~~

When controllers declare responses with `@ApiResponse`, verify that status codes and content types match the exception handler. Do not declare the 400 schema as `ValidationProblem` if the handler actually returns a different object.

For errors common to many endpoints, use controller-level `@ApiResponse` or an `OpenApiCustomizer` to standardize them. Only advertise shared responses when runtime can actually return them; avoid attaching a generic list of status codes to every operation blindly.

## 9. Spring Security Errors Sit Outside Normal Controller Advice

A request may be rejected before ever reaching a controller. Authentication and authorization typically run in the Spring Security filter chain via `AuthenticationEntryPoint` or `AccessDeniedHandler`. Therefore, `@RestControllerAdvice` does not always intercept `401` and `403`.

Verify these independently:

- Requests lacking a token or carrying an invalid token return `401` per security policy.
- Authenticated users lacking required permissions return `403`.
- Responses include appropriate challenge headers if required by the HTTP authentication scheme.
- Error bodies match the schema published in OpenAPI.
- `/v3/api-docs` and Swagger UI are protected under their own policy.

If the API uses Problem Details for security errors, configure `AuthenticationEntryPoint` and `AccessDeniedHandler` to emit the same media type and schema. If Spring Security returns a different default body, either document that body or standardize the implementation; do not assume controller advice alters responses generated by the filter chain.

## 10. Testing Malformed JSON and Type Conversion Errors

Validation runs only after the request body parses into an object. Malformed JSON, unknown enums, or invalid UUIDs can fail before Bean Validation is invoked.

Malformed JSON example:

~~~java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{ \"name\": "))
        .andExpect(status().isBadRequest());
}
~~~

Unknown enum example:

~~~java
@Test
void rejectsUnknownCategory() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Ballpoint pen",
                  "price": 12500,
                  "category": "UNKNOWN"
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Both tests check the minimum status expectation. If the API promises Problem Details for all parse errors, add assertions for content type, `type` URI, `title`, and `status` in the body. Common exceptions include `HttpMessageNotReadableException`, `MethodArgumentTypeMismatchException`, and `ConstraintViolationException`; the exact exception depends on binding site and Spring configuration.

Do not collapse all errors into one status without a policy. For instance, malformed JSON is typically `400`; unsupported `Content-Type` is `415`; incompatible `Accept` can be `406`. Test them separately to catch unintended converter or content-negotiation changes during Spring upgrades.

## 11. Testing Content Negotiation

An endpoint may support multiple media types. Tests must verify both supported and rejected cases:

~~~java
@Test
void rejectsUnsupportedRequestContentType() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.TEXT_PLAIN)
            .content("name=Ballpoint pen"))
        .andExpect(status().isUnsupportedMediaType());
}

@Test
void rejectsUnacceptableResponseType() throws Exception {
    mockMvc.perform(get("/api/products")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isNotAcceptable());
}
~~~

This example assumes the operation supports JSON only. If your application has an XML converter or wildcard mapping, statuses may differ; verify the actual runtime setup. OpenAPI `content` must list only media types the server genuinely supports.

## 12. Verifying the Generated OpenAPI Document

Springdoc generates the document from Spring mappings, annotations, models, and configuration. Add tests directly against `/v3/api-docs` instead of only visually checking Swagger UI.

Example verifying request body, success response, and error schema:

~~~java
@Test
void publishesProductRequestAndResponseSchemas() throws Exception {
    mockMvc.perform(get("/v3/api-docs")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath("$.paths['/api/products'].post").exists())
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.requestBody.required"
        ).value(true))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.requestBody.content['application/json'].schema.$ref"
        ).value("#/components/schemas/CreateProductRequest"))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['201'].content['application/json'].schema.$ref"
        ).value("#/components/schemas/ProductResponse"))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['400'].content['application/problem+json'].schema.$ref"
        ).value("#/components/schemas/ValidationProblem"));
}
~~~

Component schema names may be derived by springdoc from class names or customized via `@Schema(name = ...)`. If your project uses another schema naming strategy, update assertions to match the desired document; never skip checks merely because component names shifted unintentionally.

### Checking Schema Constraints

Verify that OpenAPI reflects key constraints:

~~~java
@Test
void publishesProductValidationConstraints() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.CreateProductRequest.properties.name.minLength"
        ).value(1))
        .andExpect(jsonPath(
            "$.components.schemas.CreateProductRequest.properties.name.maxLength"
        ).value(80));
}
~~~

Which constraints appear in OpenAPI depends on annotations, Bean Validation integration, schema version, and springdoc configuration. Assert the API's most critical constraints rather than locking tests to every internal detail that could shift across dependency upgrades.

### Checking Error Schemas

~~~java
@Test
void publishesValidationProblemSchema() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.ValidationProblem.properties.type"
        ).exists())
        .andExpect(jsonPath(
            "$.components.schemas.ValidationProblem.properties.status.type"
        ).value("integer"))
        .andExpect(jsonPath(
            "$.components.schemas.ValidationProblem.properties.errors.type"
        ).value("array"))
        .andExpect(jsonPath(
            "$.components.schemas.FieldViolation.properties.field.type"
        ).value("string"));
}
~~~

These document tests only prove schemas are published. The runtime tests in earlier sections verify that live responses match those shapes. Both are necessary to prevent cases where docs are right while handlers are wrong, or handlers are right while docs lack schemas.

## 13. Verifying Live Error Responses Match the Schema

After checking the OpenAPI document, send an invalid request and verify the body:

~~~java
@Test
void validationProblemMatchesPublishedShape() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .content("""
                {
                  "name": "",
                  "price": 0,
                  "category": "STATIONERY"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/validation-error"
        ))
        .andExpect(jsonPath("$.title").value("Request validation failed"))
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.detail").isNotEmpty())
        .andExpect(jsonPath("$.instance").value("/api/products"))
        .andExpect(jsonPath("$.errors[0].field").isNotEmpty())
        .andExpect(jsonPath("$.errors[0].code").isNotEmpty())
        .andExpect(jsonPath("$.errors[0].message").isNotEmpty());
}
~~~

For resilient tests, assert `errors` ordering only if the API guarantees order. Otherwise, parse the array and locate entries by field. Avoid comparing the entire JSON string literally when fields like `instance`, timestamps, or trace IDs vary.

Error schemas should remain stable on fields clients branch on programmatically: `type` URI, `status`, error `code`, and `field` name. Human-readable `message` text may change or be localized; clients should never branch business logic on message prose.

## 14. Using `WebTestClient` for WebFlux Applications

If the application runs on WebFlux, use `WebTestClient` instead of `MockMvc` to exercise the reactive web stack:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveProductContractTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void rejectsInvalidRequestWithProblemDetails() {
        webTestClient.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue("""
                {
                  "name": "",
                  "price": -1,
                  "category": "STATIONERY"
                }
                """)
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            )
            .expectBody()
            .jsonPath("$.status").isEqualTo(400)
            .jsonPath("$.errors").exists();
    }

    @Test
    void exposesOpenApiDocument() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/products'].post").exists();
    }
}
~~~

Do not mix `MockMvc` and `WebTestClient` arbitrarily. Use the test client matching the active web stack so requests flow through the real filter chain, codecs, and message readers/writers.

## 15. Distinguishing OpenAPI Syntax Checks from HTTP Contract Checks

A syntactically valid OpenAPI document does not guarantee it describes the server accurately. Separate your checks into layers:

| Check Type | What It Catches | What It Cannot Prove |
|---|---|---|
| Parse/validate OpenAPI | Malformed JSON/YAML, invalid structure, unresolved references | Whether runtime controllers return expected responses |
| OpenAPI lint | Missing `operationId`, descriptions, responses, naming rules, or org policies | Whether live requests/responses satisfy the schema |
| HTTP contract validation | Live requests/responses diverging from published paths, statuses, headers, media types, or schemas | Whether business logic is commercially correct |
| Business integration tests | Business rules and service/database interactions | Whether all external consumers use the contract properly |

For example, a JSON document may parse cleanly while omitting a `400` response. Conversely, OpenAPI may document `400` perfectly while the runtime exception handler emits HTML or a stack trace. Run the test layers matching your API's risk profile.

### Validating the OpenAPI Document in CI

After exporting the document from `/v3/api-docs`, you can run OpenAPI Generator CLI for baseline validation:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.json
~~~

For YAML:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.yaml
~~~

The validator checks specification structure within the capabilities of that tool version. It does not replace contract tests against real HTTP responses. If your organization uses a custom linter, pin its ruleset and version for reproducible CI results.

## 16. Comparing the OpenAPI Document Against a Baseline

When an API evolves, you need to know which edits affect consumers. Store the latest released OpenAPI document as a baseline and diff it against the current branch's document.

Changes requiring attention:

- Removing a path or HTTP method.
- Removing a parameter or changing a parameter from optional to required.
- Changing request/response property types or formats.
- Narrowing enum values that older clients may send or receive.
- Changing response statuses or media types.
- Changing security requirements or OAuth scopes.
- Changing nullability, required fields, or pagination semantics.
- Removing an error response handled by clients.

Even adding a new response status or property must be evaluated against how clients deserialize payloads. Some seemingly additive changes break strict clients encountering new enum values or unknown fields. Do not rely solely on a diff tool's breaking/non-breaking labels; evaluate how actual consumers generate code and parse JSON.

In CI, run a diff step after generating the new document:

~~~text
OpenAPI current
      |
      v
Parse and lint
      |
      v
Compare with released baseline
      |
      +---- breaking change ----> fail or require explicit approval
      |
      +---- compatible change --> continue
      |
      v
Run runtime contract tests
      |
      v
Publish build artifact
~~~

The baseline must be the document actually released to consumers, not an arbitrary stale file in the workspace. When an API has multiple groups or versions, compare matching document pairs.

## 17. Verifying Response Schemas Against Live Payloads

OpenAPI schemas describe response shapes. Runtime tests should verify:

- Required properties are present when mandated by the contract.
- JSON types are accurate: string, number, integer, boolean, object, or array.
- Formats match: `date`, `date-time`, `uuid`, `uri`, or custom formats.
- Enum values fall within the published set.
- Nullability matches the schema.
- Array items conform to the expected item structure.
- No internal fields or sensitive data leak outside the contract.

Example checking a list response:

~~~java
mockMvc.perform(get("/api/products")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items[0].id").isNotEmpty())
    .andExpect(jsonPath("$.items[0].name").isString())
    .andExpect(jsonPath("$.items[0].price").isNumber());
~~~

Path assertions keep tests readable. For large schemas, many operations, or rich response examples, supplement them with a validator that reads the OpenAPI document and validates response JSON against the schema to reduce manual assertions.

Never assume an undocumented property is automatically forbidden. OpenAPI Schema Objects may permit additional properties depending on schema configuration. If you want to forbid unknown fields or enforce strict shapes, state the policy explicitly and use an appropriate validator.

## 18. Testing Business Errors and System Errors

Not every error is a validation error. Categorize errors so schemas and tests reflect root causes:

| Error Category | Example | Contract to Verify |
|---|---|---|
| Request syntax | Malformed JSON, unparseable UUID | Status, Problem Details `type`, and message |
| Request validation | Blank name, negative price | Field violations and error codes |
| Resource lookup | Product ID does not exist | `404` and error `type` |
| Business conflict | SKU already in use | `409` and conflict code |
| Authentication | Missing or expired token | `401` and authentication challenge |
| Authorization | User lacks permission | `403` |
| Dependency failure | Database or downstream service unavailable | `5xx` per policy, no internal leaks |

Never return `500` for input errors the server can identify as `400`. Never return `404` for authorization failures merely to mask resource existence unless security policy explicitly specifies it. Security decisions may choose different responses, provided they are documented clearly in the contract.

For `5xx` errors, Problem Details should supply a stable `type`/`title` and a correlation ID if helpful for operations. Never include stack traces, internal hostnames, SQL queries, secrets, or raw exception messages in `detail`.

## 19. Verifying Error Schemas Do Not Leak Data

A helpful client error body does not need to expose implementation details. Tests should verify:

- No `stackTrace`, `exceptionClass`, or SQL statements.
- No echoing back of passwords, access tokens, cookies, or secrets from the request.
- No unnecessary personal data.
- Messages contain no table names, package names, or internal service addresses.
- Field-level errors expose only public field names and stable error codes.
- Correlation IDs follow expected formats without acting as credentials.

Example test checking for stack trace leaks:

~~~java
@Test
void doesNotExposeInternalExceptionDetails() throws Exception {
    MvcResult result = mockMvc.perform(
            get("/api/products/00000000-0000-0000-0000-000000000000")
        )
        .andExpect(status().isNotFound())
        .andReturn();

    String body = result.getResponse().getContentAsString();
    assertThat(body).doesNotContain("java.lang.");
    assertThat(body).doesNotContain("SELECT ");
    assertThat(body).doesNotContain("password");
    assertThat(body).doesNotContain("Bearer ");
}
~~~

Tests must use an endpoint and fixture that reproduce the error deterministically. Avoid asserting on overly generic substrings that legitimate business messages could contain; in real projects, asserting against internal fields like `stackTrace` or validating against an allowlisted schema is more accurate.

## 20. Testing Security Responses Separately

If Spring Security uses a custom `AuthenticationEntryPoint` and `AccessDeniedHandler`, write dedicated tests for both:

To use MockMvc's `user(...)` request post-processor in tests, add `spring-security-test` in test scope if not already present:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~java
@Test
void unauthenticatedRequestUsesDocumentedErrorContract() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
        .andExpect(status().isUnauthorized())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(401))
        .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/unauthorized"
        ));
}

@Test
void forbiddenRequestUsesDocumentedErrorContract() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
            .with(user("reader").roles("READER")))
        .andExpect(status().isForbidden())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(403));
}
~~~

These tests assume security configuration returns Problem Details with the stated media type. If your policy returns empty `401`/`403` bodies or a custom schema, align OpenAPI and tests with your actual policy. Also check `WWW-Authenticate` when the authentication scheme requires that header.

## 21. Request/Response/Error Test Matrix

A concise matrix helps the team test systematically:

| Group | Request | Runtime Expectation | OpenAPI Expectation |
|---|---|---|---|
| Happy path | Valid JSON | `2xx`/`201`, right body and headers | Complete request/response schemas |
| Required field | Missing required property | `400` or chosen policy | `required` list and error response |
| Constraint | Blank string, negative number, out of bounds | `400`/`422` per policy | `min`/`max`, `pattern`, `format` |
| Parse | Invalid JSON, invalid enum/UUID | `400` | Error schema for parse/type errors |
| Content-Type | Unsupported media type sent | `415` | Request `content` lists only supported media types |
| Accept | Unsupported representation requested | `406` | Response `content` lists accurate media types |
| Not found | Non-existent ID | `404` | `404` error response |
| Conflict | Duplicate data or conflicting state | `409` | `409` error response |
| Security | Missing token or missing role | `401`/`403` | Security requirements and error responses |
| Server error | Dependency failure | `5xx` per policy | Error response leaks no internal details |

You do not need to test every possible combination. Prioritize tests by risk, published contract branches, and past production defects.

## 22. Notes by Spring Boot Version and Web Stack

Some error APIs and packages differ across major versions:

| Platform | How to Implement Error Responses |
|---|---|
| Spring Boot 3 / Spring Framework 6+ | Can use `ProblemDetail` and `application/problem+json` |
| Spring Boot 2 / Spring Framework 5 | No `ProblemDetail` in Spring Framework; use a custom error DTO or suitable library |
| Spring MVC | Use `@RestControllerAdvice`, `HandlerExceptionResolver`, and Servlet Security handlers |
| Spring WebFlux | Use reactive exception handling, `WebExceptionHandler`, and WebFlux Security handlers |

Never copy `ProblemDetail` code verbatim into a Spring Boot 2 project. If you need a consistent error contract across multiple major versions, define a framework-independent error DTO and write adapters per web stack.

In Spring MVC, request body validation typically throws `MethodArgumentNotValidException`. Method-parameter or controller-method validation may throw different exceptions depending on Spring version and `@Validated` usage. In WebFlux, exception types and response-writing mechanisms differ from MVC. Write tests targeting final HTTP behavior rather than coupling tightly to internal exception class names.

## 23. Integrating Contract Checks into CI

A CI pipeline should run these steps in order:

1. Compile and run unit tests.
2. Start the application with a test profile and deterministic data setup.
3. Fetch OpenAPI JSON/YAML from the runtime endpoint.
4. Parse and validate the OpenAPI document.
5. Run linting and policy checks for operations, parameters, schemas, and error responses.
6. Diff the document against the released baseline to catch breaking changes.
7. Run HTTP contract tests for happy paths and negative cases.
8. Verify error schemas, security responses, and content negotiation.
9. Archive the OpenAPI document and test reports as build artifacts.

Never publish documentation just because `/v3/api-docs` returned `200`. Publish only when the document parses cleanly, passes linting policies, and key runtime tests succeed.

Example pipeline gates:

~~~text
Build application
       |
       v
Start test server
       |
       v
Export OpenAPI document
       |
       v
Validate + lint + compare baseline
       |
       v
Run HTTP contract tests
       |
       v
Stop test server
       |
       v
Publish OpenAPI + test reports
~~~

If a Maven plugin starts the test server, ensure cleanup runs even when an intermediate pipeline step fails. When using backing databases or containers, manage lifecycle and test data so results do not depend on prior runs.

## 24. Common Pitfalls When Testing Requests, Responses, and Error Schemas

| Symptom | Possible Cause | Resolution |
|---|---|---|
| OpenAPI has `minLength` yet server accepts blank strings | Only `@Schema` was added, missing Bean Validation or `@Valid` | Add runtime constraints and activate validation |
| Invalid request returns `500` | Validation/parse exception is not mapped properly | Add exception handler and test status |
| Invalid request body returns HTML | Default error handling or another filter writes response | Standardize error responses and content types |
| `400` response lacks schema in OpenAPI | Missing `@ApiResponse` or customizer | Declare Problem Details schema |
| OpenAPI says `application/json` yet runtime returns `problem+json` | Annotations disagree with exception handler | Declare `application/problem+json` media type |
| Test never sees `401`/`403` in `@RestControllerAdvice` | Security filter chain handles it before controller | Test and configure `AuthenticationEntryPoint`/`AccessDeniedHandler` |
| JSONPath test depends on `errors` array order | Violations array has no guaranteed contract order | Match elements by field/code instead of fixed index |
| `ValidationProblem` schema differs from live body | Schema DTO is merely illustrative or extension properties differ | Align fields/types/nullability and test live JSON |
| Swagger UI shows right schema yet server is wrong | Only checked docs without HTTP testing | Add runtime contract tests |
| Response test checks only status | Missing header, content type, and body assertions | Verify the full response contract |
| Error body leaks stack trace or SQL | Returned raw internal exception message | Use public error codes/messages and test for leaks |
| New enum breaks old clients | Consumers parse enums strictly | Plan enum evolution and versioning policy |
| OpenAPI diff reports noisy unrelated changes | Non-deterministic generator/configuration | Standardize schema naming, ordering, and build environment |
| Tests pass locally yet fail in CI | Unstable profile, locale, clock, or seed data | Pin test config, fixtures, and timezone |

## 25. End-to-End Testing Workflow for an Operation

For each critical operation, follow this sequence:

1. Read the OpenAPI operation: method, path, security, parameters, request body, and responses.
2. Send a valid request and verify status, headers, media type, and body.
3. Send requests missing required fields and violating constraints.
4. Send malformed JSON and invalid enum or path/query parameter types.
5. Send unsupported `Content-Type` and `Accept` headers.
6. Test business errors such as not found and conflict.
7. Test `401`/`403` through the security filter chain.
8. Verify every error response carries the expected `type`, `title`, `status`, `detail`, `instance`, and extension fields.
9. Fetch `/v3/api-docs` and verify request, success response, and error response schemas.
10. Validate/lint the document and diff against the baseline in CI.

For public APIs or APIs with many consumers, store request/response examples as fixtures so contract tests detect unintended shifts. When schemas change, review both the OpenAPI diff and the impact on consumer SDK code generation.

## 26. References

- [Springdoc OpenAPI – Getting Started and Features](https://springdoc.org/): how springdoc generates OpenAPI from Spring Boot, annotations, and models.
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html): frequently asked questions on schemas, responses, and configuration.
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Bean Validation integration in Spring.
- [Spring Framework – Request Body Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): controller method and request body validation in Spring MVC.
- [Spring Framework – WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): validation in WebFlux controllers.
- [Spring Framework – Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, and REST error handling.
- [Spring Security – Authentication Entry Point](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): handling authentication in the security filter chain.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): describing request bodies.
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object): describing responses by status code.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): schemas, properties, `required`, and constraints.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): structured error response format and `application/problem+json`.
- [OpenAPI Generator – Validate](https://openapi-generator.tech/docs/usage/#validate): validating OpenAPI documents in builds/CI.
