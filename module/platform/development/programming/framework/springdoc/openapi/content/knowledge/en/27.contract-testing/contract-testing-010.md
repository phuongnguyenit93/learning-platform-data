# Validating Real HTTP Payloads Against Schemas Instead of Annotations Only

An endpoint can carry complete `@Operation`, `@ApiResponse`, and `@Schema` annotations and still return payloads that violate the OpenAPI contract. Annotations express the API's intent; they do not prove that live HTTP responses carry the expected status, headers, content type, required fields, data types, or JSON structure.

With Spring Boot and springdoc-openapi, verify two distinct artifacts:

1. **The generated specification**: the OpenAPI JSON/YAML document describing operations and schemas.
2. **Actual HTTP exchanges**: incoming requests and outgoing responses serialized and processed through filters, exception handlers, and security.

Contract tests place both artifacts side by side: send requests like a real client, receive responses from Spring MVC/WebFlux, and validate the entire HTTP interaction against OpenAPI. This catches cases where documentation declares `price` as a number while Jackson serializes a string, responses omit required fields, endpoints return undocumented status codes, or query parameters have the wrong types.

## 1. Why Checking Annotations Alone Is Insufficient

Consider a controller declaring:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @Operation(summary = "Get product details")
    @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                    schema = @Schema(implementation = ProductResponse.class)
            )
    )
    @GetMapping("/{id}")
    ProductResponse getProduct(@PathVariable UUID id) {
        return productService.get(id);
    }
}
~~~

Tests checking annotations or invoking the controller method directly do not verify the payload on the wire. Live payloads are also shaped by:

- Jackson `ObjectMapper`, naming strategies, and Java Time modules.
- `@JsonProperty`, `@JsonIgnore`, `@JsonInclude`, and custom serializers.
- Bean Validation and how Spring turns validation errors into HTTP responses.
- `ResponseEntity`, status codes, response headers, and content negotiation.
- `@ControllerAdvice`, exception handlers, and error response DTOs.
- Servlet filters, Spring Security, gateways, or interceptors.
- Active profiles, feature flags, and the running DTO version.

For example, the schema may declare `createdAt` as a `date-time` string while a differently configured `ObjectMapper` serializes an epoch number. The annotation stays intact, Swagger UI still renders, and yet clients fail to parse the payload.

### 1.1. Three Testing Tiers

| Tier | Checks | Catches |
|---|---|---|
| Unit / controller tests | Method logic, service calls, branch behavior | Business logic bugs in methods, without guaranteeing HTTP serialization |
| HTTP contract tests | Live requests/responses via MockMvc or HTTP server validated against OpenAPI | Path, method, parameter, content type, status, header, and body schema mismatches |
| End-to-end tests via proxy/gateway | Real requests crossing network boundaries and deployment components | Path rewrites, auth, gateway headers, TLS, and deployment misconfigurations |

These tiers complement each other. MVC-layer contract tests run faster than end-to-end tests, yet they do not replace gateway tests when gateways rewrite requests or responses.

## 2. What Does Contract Testing Verify?

An OpenAPI-aware validator checks multiple dimensions of an HTTP interaction:

| Dimension | Verification Example |
|---|---|
| HTTP method and path | `GET /api/products/{id}` must match a declared operation. |
| Path parameters | `id` must be present and valid UUID format. |
| Query parameters | `page` is an integer, `size` fits documented bounds. |
| Headers and cookies | Required headers, types, and values match the schema. |
| Request body | JSON has required fields, valid enums, and accurate types. |
| Content-Type | Requests and responses use declared media types. |
| Status code | Responses like `200`, `201`, `400`, `404`, or `default` must be documented. |
| Response headers | Such as `Location`, `ETag`, `Cache-Control`. |
| Response body | Fields, types, formats, `required`, enums, arrays, and object constraints. |
| Security requirements | Presence of API keys or bearer/basic credentials within validator capabilities. |

This differs from tests calling `jsonPath("$.id").exists()`: JSONPath tests check a handful of chosen fields, whereas a contract validator validates the full interaction against the published operation and schemas.

## 3. Using an OpenAPI Artifact as the Reference Baseline

Springdoc typically exposes specifications at:

- JSON: `/v3/api-docs`
- YAML: `/v3/api-docs.yaml`

You can fetch the specification to validate or archive as an artifact:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs.yaml \
  -o build/openapi/catalog.yaml
~~~

In tests, choose the specification source deliberately:

| Specification Source | When Appropriate | Caveats |
|---|---|---|
| Reviewed OpenAPI file stored in test resources | When verifying the current implementation still honors an approved contract. | Must be updated via review when the contract changes. |
| OpenAPI artifact generated by springdoc during build | When verifying HTTP payloads match the docs emitted by the current build. | Diff the new artifact against a released baseline to catch unintended changes. |
| Live `/v3/api-docs` endpoint of the running app | When testing the full doc-generation flow and HTTP runtime in one deployment test. | Because docs come from the same codebase, this alone will not detect unintended annotation changes relative to a prior contract. |

Never fetch the latest OpenAPI solely from the app itself and treat it as full proof of compatibility. That confirms live payloads match today's schema, not whether the schema broke older clients. Keep a baseline artifact or run contract diffs between releases.

Abbreviated contract example for the product lookup endpoint:

~~~yaml
openapi: 3.0.4
info:
  title: Catalog API
  version: 1.4.0
paths:
  /api/products/{id}:
    get:
      operationId: getProduct
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Product found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "404":
          description: Product not found
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
components:
  schemas:
    ProductResponse:
      type: object
      additionalProperties: false
      required:
        - id
        - name
        - price
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
          minLength: 1
        price:
          type: number
          minimum: 0
        createdAt:
          type: string
          format: date-time
    ApiProblem:
      type: object
      required:
        - title
        - status
      properties:
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
~~~

In this schema:

- `id`, `name`, and `price` must be present in success responses.
- `price` must be a non-negative JSON number.
- `createdAt`, if present, must be a `date-time` string.
- `additionalProperties: false` forbids undeclared fields in the response object.
- The `404` response has a dedicated error schema rather than returning an arbitrary object.

## 4. Choosing a Validator by Spring Boot Version and Test Boundary

One Java option is Atlassian's OpenAPI Request Validator. It provides a core validator plus adapters for REST Assured, Spring MockMvc, WireMock, Pact, and several other clients/frameworks.

| Adapter | Usage | Boundary |
|---|---|---|
| `openapi-request-validator-mockmvc` | Add a `ResultMatcher` to MockMvc interactions. | Validates requests/responses in Spring MVC tests without opening HTTP ports. |
| `openapi-request-validator-restassured` | Add `OpenApiValidationFilter` to REST Assured. | Validates requests/responses against a running HTTP server. |
| `openapi-request-validator-wiremock-junit5` | Validates interactions served by WireMock. | Ensures consumer mocks/stubs honor the contract. |
| `openapi-request-validator-pact` | Combines validation with Pact consumer tests. | Adds OpenAPI checks to consumer expectations. |

### 4.1. Mind Library Versions

Artifacts and adapters were renamed in major version 3:

| Platform | Validator Branch | MockMvc Artifact |
|---|---|---|
| Spring Boot 3 / Spring Framework 6 | Validator 2.x branch | `swagger-request-validator-mockmvc` |
| Spring Boot 4 / Spring Framework 7 | Validator 3.x branch | `openapi-request-validator-mockmvc` |

The 3.x branch requires Java 21+ for core and adapters; the new Spring adapter targets Spring Framework 7 and the `jakarta.*` namespace. A Boot 3 application cannot simply swap dependency coordinates to v3 and remain on Spring 6. Select the right major line and check release notes before upgrading.

Maven dependency example for the 3.x branch:

~~~xml
<dependency>
    <groupId>com.atlassian.oai</groupId>
    <artifactId>openapi-request-validator-mockmvc</artifactId>
    <version>${openapi-request-validator.version}</version>
    <scope>test</scope>
</dependency>
~~~

Set `openapi-request-validator.version` to a pinned release compatible with your Java and Spring versions. For Boot 3, use the 2.x branch coordinates per migration docs; do not copy v3 coordinates into a Spring 6 project.

## 5. Validating Requests and Responses with MockMvc

MockMvc dispatches requests through Spring MVC's `DispatcherServlet`, message converters, controllers, validation, exception handlers, and configured test filters. This boundary catches serialization bugs without launching a network server.

Assuming the contract file lives at `src/test/resources/openapi/catalog.yaml`, with the 3.x MockMvc adapter you can attach `openApi().isValid(...)` directly to the interaction:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static com.atlassian.oai.validator.mockmvc.OpenApiValidationMatchers.openApi;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getProductResponseMatchesOpenApiContract() throws Exception {
        UUID productId = UUID.fromString(
                "d9a5c6e8-10b4-4a2a-8d15-4b3d9e7f2a11"
        );

        mockMvc.perform(get("/api/products/{id}", productId)
                        .accept(APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
                .andExpect(openApi().isValid("openapi/catalog.yaml"));
    }
}
~~~

The matcher checks both the outgoing request and incoming response against the operation in the specification. If a path parameter has the wrong format, the response status is undocumented, response headers/content type mismatch, or the body violates the schema, the interaction fails.

### 5.1. Validating Request Body and Response Together

For product creation endpoints, tests should send payloads via the HTTP request builder:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void createProductRequestAndResponseMatchContract() throws Exception {
    mockMvc.perform(post("/api/products")
                    .contentType(APPLICATION_JSON)
                    .accept(APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Mechanical Keyboard",
                              "price": 79.90
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(APPLICATION_JSON))
            .andExpect(openApi().isValid("openapi/catalog.yaml"));
}
~~~

This test validates the actual request body sent, the Spring-serialized response, and the returned status code. If the contract expects `price` as a number while the application serializes `"79.90"` as a string, the validator catches the type mismatch.

### 5.2. Validating Error Responses

Do not test only happy paths. APIs must document and verify meaningful error responses:

- `400 Bad Request`: invalid payload or parameters.
- `401 Unauthorized`: unauthenticated.
- `403 Forbidden`: authenticated with insufficient permissions.
- `404 Not Found`: resource missing.
- `409 Conflict`: business conflict.
- `422 Unprocessable Content`: syntactically valid data violating business rules, if the API uses this status.

Example testing `404`:

~~~java
@Test
void missingProductReturnsDocumentedProblemResponse() throws Exception {
    UUID missingId = UUID.fromString(
            "00000000-0000-0000-0000-000000000099"
    );

    mockMvc.perform(get("/api/products/{id}", missingId)
                    .accept("application/problem+json"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith("application/problem+json"))
            .andExpect(openApi().isValid("openapi/catalog.yaml"));
}
~~~

If the controller returns `404` while OpenAPI declares only `200`, the contract test flags the mismatch. If the error handler returns an object violating `ApiProblem`, the test fails as well.

### 5.3. Separating Invalid-Request Tests from Response Contract Tests

A test intentionally sending a schema-violating request has two distinct goals:

1. Confirm the server rejects the request with the right status and error payload.
2. Confirm the error response matches its documented schema.

A full-interaction validator checks both requests and responses by default, so an intentionally invalid request can fail the test even when the `400` response is completely valid. For negative tests, configure the validator to check responses only or assert the error payload separately as supported by your adapter. Keep positive contract tests proving valid requests succeed.

Never disable request validation across the entire suite just to make negative tests pass easily; doing so misses non-compliant client requests.

## 6. Validating a Live HTTP Server with REST Assured

MockMvc does not open a real HTTP port. To test embedded Tomcat/Jetty/Undertow, servlet containers, filter chains, and network requests, boot the app on a random port and use REST Assured.

The `openapi-request-validator-restassured` adapter supplies `OpenApiValidationFilter`. Example:

~~~java
import com.atlassian.oai.validator.restassured.OpenApiValidationFilter;
import io.restassured.filter.Filter;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static io.restassured.RestAssured.given;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProductHttpContractTest {

    @LocalServerPort
    int port;

    @Test
    void realHttpResponseMatchesOpenApiContract() {
        String specificationUrl =
                "http://localhost:" + port + "/v3/api-docs";

        Filter validation = new OpenApiValidationFilter(specificationUrl);

        given()
                .port(port)
                .filter(validation)
                .accept("application/json")
        .when()
                .get("/api/products/{id}",
                        "d9a5c6e8-10b4-4a2a-8d15-4b3d9e7f2a11")
        .then()
                .statusCode(200);
    }
}
~~~

This example fetches OpenAPI JSON from the running application itself. That helps verify the published specification and HTTP interactions align in the current build. In pipelines checking compatibility with a prior release, point the filter at a reviewed baseline OpenAPI artifact instead of the runtime URL; the new implementation must continue honoring the baseline contract.

If the OpenAPI document is protected by Spring Security, configure test authentication or use a local contract artifact. Never weaken production security just so tests can download `/v3/api-docs`.

## 7. Do Not Inspect Only the JSON Body

A thorough contract test validates the entire HTTP envelope.

### 7.1. Status Codes and Response Headers

OpenAPI responses can declare headers:

~~~yaml
responses:
  "201":
    description: Product created
    headers:
      Location:
        required: true
        schema:
          type: string
          format: uri-reference
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/ProductResponse"
~~~

When the server returns `201`, tests must verify `Location` is present and the body matches its schema. Checking only the JSON body misses missing headers required by clients.

### 7.2. Content Negotiation

When an operation supports `application/json` and `application/problem+json`, tests must send appropriate `Accept` headers and assert returned `Content-Type` headers. An endpoint might return valid JSON with the wrong media type, breaking client decoder selection.

For `204 No Content`, no unexpected JSON body may be returned. For `HEAD`, responses carry no body per HTTP semantics. Document these accurately in OpenAPI and verify live responses.

### 7.3. Parameter Serialization

Test the parameter forms clients actually send:

- Path parameters use proper URL encoding.
- Numeric, boolean, enum, and date/time query parameters follow declared formats.
- Array query parameters follow the declared `style`/`explode`.
- Header parameters are not stripped by proxies or filters.
- Cookie parameters use the right names and transmission style.

Testing `?page=1&size=20` does not prove array parameters like `?tag=a&tag=b` or `deepObject` bind properly. Every important serialization pattern needs its own interaction test.

## 8. Mismatches That Only Surface in Runtime Payloads

| Mismatch | Common Cause | Caught by Contract Test |
|---|---|---|
| Missing required field | `@JsonInclude(NON_NULL)`, mappers, or DTO mapping drops fields | Required property absent from response. |
| Wrong field name | `@JsonProperty`, naming strategies, or serializers | Schema says `productId`, payload emits `product_id`. |
| Wrong numeric type | `BigDecimal` serialized as string | Schema specifies number, payload sends string. |
| Wrong date/time | Epoch numbers, formats, or timezone shifts | Schema specifies `date-time`, payload fails format. |
| Extra fields | DTO leaks internal fields | Closed schema with `additionalProperties: false` fails. |
| New enum value | Code adds enum constant without updating contract | Response emits value outside declared enum. |
| Wrong status | Exception handler returns `200` or `500` instead of documented status | Status code undocumented for operation. |
| Wrong media type | Converter emits `text/plain` or another type | `Content-Type` mismatches `content`. |
| Wrong error shape | `@ControllerAdvice` returns object differing from error schema | Error response violates schema. |
| Missing header | Omitted `Location`, `ETag`, or pagination headers | Required response header absent. |

### 8.1. `required`, Nullable, and Omitted Fields

In OpenAPI, an optional property may be omitted; a nullable property may appear with value `null`. Those behaviors are distinct.

Example response:

~~~json
{
  "id": "d9a5c6e8-10b4-4a2a-8d15-4b3d9e7f2a11",
  "name": "Mechanical Keyboard",
  "price": 79.9
}
~~~

If `createdAt` is not in `required`, omitting it may be valid. Yet if the schema marks `createdAt` as required while runtime uses `@JsonInclude(NON_NULL)` and drops it, contract tests must fail.

### 8.2. Strict Schemas and `additionalProperties`

When a schema sets `additionalProperties: false`, payloads carrying undeclared fields fail validation. This helps keep public responses tightly controlled, though it must be an intentional decision.

If an API intentionally supports extensible metadata, configure `additionalProperties` with an appropriate schema or allow extension fields. Never enable `false` solely to tighten tests when the server legitimately supports extensions.

## 9. Testing Requests and Responses Across Operation Types

A contract test suite should cover operation patterns with distinct serialization risks:

| Operation Group | Cases to Cover |
|---|---|
| `GET` collection | Empty list, populated list, pagination, sorting, filtering. |
| `GET` item | Found, not found, malformed ID format. |
| `POST` | Valid payload, missing required fields, bad enums, wrong body media type. |
| `PUT`/`PATCH` | Full replacement and partial updates, nullability. |
| `DELETE` | Success, not found, `204` bodyless response. |
| Upload | Multipart payloads, file metadata, size limits, media types. |
| Download | `Content-Type`, `Content-Disposition`, binary bodies. |
| Error handlers | `400`, `401`, `403`, `404`, `409`, and documented system errors. |
| Security | Requests with/without credentials and expected status codes. |

You do not need hundreds of redundant tests repeating the same schema. Pick representative cases per operation, critical response code, and specialized serialization branch.

## 10. Validator Limitations and OpenAPI Versions

Not every validator supports all OpenAPI features equally. For Atlassian's OpenAPI Request Validator, current feature documentation notes:

- OpenAPI 3.0: full request/response validation per the feature matrix.
- OpenAPI 3.1: partial support; some JSON Schema 2020-12 keywords are not yet fully enforced.
- JSON Schema draft-07: supports many keywords and compositions such as `$ref`, `allOf`, `oneOf`, `anyOf`, and discriminators.

For example, per the current feature matrix, `contentMediaType` and `contentEncoding` may parse without enforcing values; plural `examples` parses without validating; `unevaluatedItems` has partial support. Check the feature matrix before relying on specific keywords as strict test gates.

### 10.1. Security Validation Does Not Replace Security Testing

Validators may check for the presence of certain security credentials per supported schemes. However, that does not prove:

- Token signatures are valid.
- Tokens have not expired.
- OAuth2 scopes are properly enforced.
- Users are authorized for the target resource.
- Tenant isolation holds.

Use Spring Security integration tests or end-to-end security tests to verify authentication and authorization. OpenAPI contract tests check alignment with docs; they do not replace authorization tests.

### 10.2. REST Assured's JSON Schema Module Differs from an OpenAPI Validator

REST Assured includes a `json-schema-validator` module for checking JSON responses against JSON Schemas. It works well when checking body schemas alone.

However, a standalone JSON Schema validator does not verify:

- Whether HTTP method and path match an operation.
- Whether the status code is documented.
- Response headers and media types.
- Path/query/header/cookie parameters.
- OpenAPI security requirements.

When the goal is validating complete HTTP interactions against OpenAPI, use an OpenAPI validator adapter. Reserve standalone JSON Schema validators for body-level assertions or independently managed schemas.

## 11. Distinguishing OpenAPI Conformance from Consumer-Driven Contracts

Two different practices are often grouped under "contract testing":

| Type | Core Question | Typical Tools |
|---|---|---|
| OpenAPI conformance testing | Do live HTTP requests/responses match the OpenAPI specification? | OpenAPI Request Validator, REST Assured, MockMvc. |
| Consumer-driven contract testing | Does the provider satisfy expectations actual consumers rely on? | Pact or Spring Cloud Contract. |

OpenAPI is a public-facing API contract typically published by the provider. Pact and Spring Cloud Contract verify cross-service expectations, manage stubs, and catch changes impacting specific consumers.

Both can be combined: OpenAPI validators verify all interactions against the specification, while Pact/Spring Cloud Contract verify interactions relied upon by specific consumers. Never treat one as a full replacement for the other.

## 12. Integrating Contract Tests into CI

A basic pipeline:

~~~mermaid
flowchart TD
    A[Build Spring Boot application] --> B[Generate or load reviewed OpenAPI artifact]
    B --> C[Validate OpenAPI document]
    C --> D[Run MockMvc / REST Assured tests]
    D --> E[Validate real requests and responses]
    E --> F[Compare contract with released baseline]
    F --> G[Publish artifact and test report]
~~~

Recommended steps:

1. Build the application and boot test contexts under a defined profile.
2. Generate or load the reviewed OpenAPI JSON/YAML.
3. Validate OpenAPI structure and resolve `$ref` pointers.
4. Run MockMvc contract tests for critical operations.
5. Run REST Assured over a real HTTP port for flows needing containers, filters, or networking.
6. Verify both success and error responses.
7. Diff the OpenAPI artifact against the baseline to catch breaking changes.
8. Archive artifacts, validator versions, and test reports with the build.

Do not trigger these tests only when controllers change. Edits to `ObjectMapper`, DTOs, `@ControllerAdvice`, security filters, Spring dependencies, or serialization settings can all alter wire payloads.

### 12.1. Keeping Tests Deterministic

- Use deterministic test fixtures; avoid relying on wall-clock time or external mutable data.
- Validate against schemas rather than raw JSON strings when field order is insignificant.
- Use `additionalProperties: false` only when the API genuinely commits to no extension fields.
- Standardize date/time formats and timezones in test data.
- Never pull docs from production environments with live auth or shifting data.
- Pin validator versions and OpenAPI artifacts.
- Avoid suppressing validator errors with broad whitelists; any exception must have a clear scope and rationale.
- Save validation reports showing the offending path, method, status, and schema location.

## 13. Common Pitfalls

- **Checking only `@Schema` or `@ApiResponse`**: annotations do not prove runtime payloads match schemas.
- **Checking only one field via JSONPath**: misses extra fields, wrong types, wrong headers, or wrong status codes.
- **Using freshly generated docs as the sole baseline**: misses unintended contract breaks relative to prior releases.
- **Skipping error response tests**: `@ControllerAdvice` may emit bodies violating error schemas.
- **Skipping `Content-Type` checks**: valid JSON bodies can still be served with the wrong media type.
- **Skipping request body validation**: servers may accept payloads violating documented schemas.
- **Using full-interaction matchers on intentionally invalid requests**: validators flag the invalid request itself; split negative tests or validate responses only.
- **Using validator 3.x with Spring Boot 3**: 3.x requires Spring 7/Boot 4 for the MockMvc adapter; Boot 3 requires the 2.x branch.
- **Assuming full OpenAPI 3.1 support**: validator feature matrices may offer only partial coverage.
- **Treating security scheme validation as authorization testing**: test tokens, scopes, and permissions separately.
- **Running only MockMvc and ignoring gateways**: MockMvc does not simulate proxies, TLS, path rewrites, or network policies.
- **Disabling validators on mismatch**: determine whether the bug sits in code, schema, or test setup, and fix the source.
- **Using overly broad whitelists**: hides newly introduced contract regressions.

## 14. Contract Test Review Workflow

1. **Choose the contract baseline**: decide whether tests use a reviewed file, build artifact, or runtime doc.
2. **Verify OpenAPI**: document parses cleanly with complete operations and `$ref`s.
3. **Select test boundaries**: MockMvc for fast MVC interactions; REST Assured for real HTTP servers.
4. **Send realistic requests**: use client-like paths, parameters, headers, media types, and bodies.
5. **Validate live responses**: check status, headers, content type, and body schemas.
6. **Test success/error branches**: cover published response codes.
7. **Check schema edge cases**: `required`, nullability, enums, formats, and `additionalProperties`.
8. **Verify compatibility**: confirm validator version supports the app's OpenAPI dialect and framework.
9. **Run in CI**: archive reports and compare contracts against baselines.
10. **Review mismatches**: fix either implementation or contract per agreed API behavior.

## 15. Review Checklist

- [ ] Tests send HTTP requests through MockMvc or a real HTTP server.
- [ ] Tests validate request parameters and bodies.
- [ ] Tests validate status codes and response headers.
- [ ] Tests validate `Content-Type` and response body schemas.
- [ ] Both success and error responses are tested.
- [ ] DTO serialization and `@ControllerAdvice` sit inside the tested execution path.
- [ ] The OpenAPI artifact is an approved baseline or compared against a baseline.
- [ ] Validator version is compatible with Spring Boot and OpenAPI versions.
- [ ] Used OpenAPI 3.1 keywords fall within the validator's supported feature set.
- [ ] Negative request tests are not mistakenly evaluated as valid requests.
- [ ] Security/authorization have dedicated tests.
- [ ] Gateways/proxies have end-to-end tests when they alter HTTP interactions.
- [ ] Validation reports are archived in CI.
- [ ] Validation error whitelists are tightly scoped with clear justification.

## 16. References

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [Atlassian OpenAPI Request Validator – README](https://github.com/atlassian/openapi-request-validator)
- [Atlassian OpenAPI Request Validator – MockMvc adapter](https://github.com/atlassian/openapi-request-validator/tree/master/openapi-request-validator-mockmvc)
- [Atlassian OpenAPI Request Validator – REST Assured adapter](https://github.com/atlassian/openapi-request-validator/tree/master/openapi-request-validator-restassured)
- [Atlassian OpenAPI Request Validator – Feature support matrix](https://github.com/atlassian/openapi-request-validator/blob/master/docs/FEATURES.md)
- [Atlassian OpenAPI Request Validator – OpenAPI 3 support](https://github.com/atlassian/openapi-request-validator/blob/master/docs/OPENAPIv3.md)
- [Atlassian OpenAPI Request Validator – Release notes and v2 to v3 migration](https://github.com/atlassian/openapi-request-validator/blob/master/RELEASE-NOTES.md)
- [REST Assured – Writing tests](https://rest-assured.io/docs/usage/)
- [REST Assured – JSON Schema validation](https://rest-assured.io/docs/usage/json-schema/)
- [Spring Cloud Contract – Getting Started](https://docs.spring.io/spring-cloud-contract/docs/current/reference/html/getting-started.html)
- [Pact – Documentation](https://docs.pact.io/)

Contract tests matter when they verify the actual HTTP data clients send and receive. Use springdoc to produce or maintain OpenAPI artifacts, dispatch requests through MockMvc or REST Assured, and validate status codes, headers, media types, and payloads against approved schemas. Combining runtime checks with contract diffs catches both current serialization bugs and contract shifts that could break clients.
