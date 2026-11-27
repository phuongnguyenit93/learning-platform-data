# Documentation Testing for Multiple Error Types

## Learning Objectives

In the **SPRING_REST_DOCS** module, APIs do not only return successful data. Clients also need to understand how endpoints respond when input data is invalid, unauthenticated, unauthorized, a resource is not found, a business conflict occurs, or the system is temporarily unavailable. Error documentation tests must verify actual HTTP behavior and generate snippets that accurately describe the error contract.

A good error response typically has a consistent structure: a stable error code, a displayable message, per-field details where appropriate, and non-sensitive tracing info. Each error category has its own status, headers, and content; you should not lump all errors into one generic response that clients cannot handle programmatically.

After this lesson, you will be able to:

- Classify API error categories and select scenarios to document.
- Design tests for validation, authentication, authorization, not found, conflict, rate limit, and server/dependency errors.
- Assert status, headers, and body before invoking REST Docs.
- Use distinct operation IDs for each error scenario.
- Reuse descriptors for shared error schemas while still describing error-specific fields.
- Use MockMvc and WebTestClient to generate error snippets.
- Avoid putting stack traces, tokens, personal data, or internal information into documentation.

## 1. Why Document Multiple Error Types?

If documentation only covers the happy path, integrators will not know what status a request missing a required field receives, how an expired token differs from an insufficiently privileged user, what response structure a nonexistent resource returns, how business conflicts can be resolved, which header provides retry timing on rate limits, or whether external dependency errors should be retried.

Error documentation helps clients distinguish request-fixable errors, access permission errors, resource state errors, and transient errors. This is essential when an API is consumed by multiple applications or development teams.

## 2. Classifying Errors by HTTP Contract

| Error Category | Common Status | Example | What Clients Usually Do |
| --- | --- | --- | --- |
| Validation | 400 or 422 per API convention | Missing name, invalid email format | Fix submitted data |
| Authentication | 401 Unauthorized | Missing token, expired token | Log in or refresh credentials |
| Authorization | 403 Forbidden | User is authenticated but lacks permission | Request permissions or use allowed resources |
| Not found | 404 Not Found | ID does not exist | Verify ID |
| Conflict | 409 Conflict | Duplicate code, state disallows action | Reload state or resolve conflict |
| Rate limit | 429 Too Many Requests | Sending too many requests | Wait according to retry policy |
| Dependency unavailable | 502/503/504 depending on architecture | Dependent service fails/times out | Retry with limits if safe |
| Internal error | 500 Internal Server Error | Unexpected error | Report error, send correlation ID to support |

These are common statuses, not mandatory rules for every API. Exception handlers, gateways, and API policies may map exceptions differently. Documentation tests must verify the responses clients actually receive.

## 3. Designing a Consistent Error Response

An illustrative error schema:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Invalid request",
  "details": [
    {
      "field": "name",
      "reason": "must not be blank"
    }
  ],
  "traceId": "test-trace-001"
}
```

| Field | Role | Contract Notes |
| --- | --- | --- |
| code | Stable machine-readable error code | Independent of display language |
| message | Human-friendly message | May be localized |
| details | Details by field or cause | Structure varies by error type |
| traceId | Support trace ID | Contains no stack traces or secrets |

APIs may also use RFC 9457 Problem Details with media type application/problem+json. Standard fields include type, title, status, detail, and instance; extension members can add code or errors. Document the exact format the application actually uses, without mixing two schemas.

### 3.1. Error Codes Should Be Stable

Clients should rely on machine-readable codes rather than parsing natural-language messages. Examples: VALIDATION_ERROR, UNAUTHENTICATED, ACCESS_DENIED, PRODUCT_NOT_FOUND, PRODUCT_ALREADY_EXISTS, RATE_LIMIT_EXCEEDED, and DEPENDENCY_UNAVAILABLE. Projects should maintain a consistent code catalog.

## 4. Testing Validation Errors

Suppose the product creation endpoint requires name:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": " ",
                  "price": 129.90
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
    .andExpect(jsonPath("$.details[*].field").value(hasItem("name")))
    .andDo(document("products-create-validation-error",
        responseFields(
            fieldWithPath("code").description("Validation error code."),
            fieldWithPath("message").description("Error message."),
            fieldWithPath("details").description("List of error details."),
            fieldWithPath("details[].field").description("Invalid field."),
            fieldWithPath("details[].reason").description("Reason the field is invalid."),
            fieldWithPath("traceId").description("Request trace ID.")
        )));
```

The test verifies status, Content-Type, error code, and details pointing to the name field. Descriptors must match the real payload. If the application returns violations[].message instead of details[].reason, use the actual path.

## 5. Testing Authentication Errors

Unauthenticated requests can return 401:

```java
this.mockMvc.perform(get("/api/me"))
    .andExpect(status().isUnauthorized())
    .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
    .andDo(document("profile-unauthenticated",
        responseFields(
            fieldWithPath("code").description("Authentication error code."),
            fieldWithPath("message").description("Error message."),
            fieldWithPath("traceId").description("Trace ID.")
        )));
```

If the authentication scheme requires a challenge header, assert it:

```java
.andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        startsWith("Bearer")
))
```

401 indicates the request is not validly authenticated. Do not use 403 for all token errors if the contract distinguishes authentication and authorization. Never use real tokens in tests or snippets.

## 6. Testing Authorization Errors

Logged-in users lacking permissions typically receive 403:

```java
this.mockMvc.perform(get("/api/admin/reports")
        .with(user("reader").roles("USER")))
    .andExpect(status().isForbidden())
    .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
    .andDo(document("admin-reports-forbidden",
        responseFields(
            fieldWithPath("code").description("Authorization error code."),
            fieldWithPath("message").description("Error message.")
        )));
```

Tests should create a principal with deterministic permissions, independent of real users or environment roles. If the API intentionally hides whether a resource exists, the status may be 404 per policy; documentation must reflect the chosen behavior.

## 7. Testing Not Found

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
    .andExpect(jsonPath("$.message").isNotEmpty())
    .andDo(document("products-get-not-found",
        responseFields(
            fieldWithPath("code").description("Product not found error code."),
            fieldWithPath("message").description("Error message."),
            fieldWithPath("traceId").description("Request trace ID.")
        )));
```

Do not check only the status. The error code helps clients distinguish a missing product from other 404 errors if the application shares that status across multiple causes.

## 8. Testing Conflicts and Business State Errors

Example when a SKU already exists:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "sku": "KB-001",
                  "name": "Keyboard"
                }
                """))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("PRODUCT_ALREADY_EXISTS"))
    .andDo(document("products-create-conflict",
        responseFields(
            fieldWithPath("code").description("Conflict error code."),
            fieldWithPath("message").description("Error message.")
        )));
```

Conflicts can often be resolved by reloading state or choosing different data. Error messages should provide enough guidance for clients to understand the issue without exposing internal data.

## 9. Testing Rate Limits and Retry Headers

If the API enforces rate limits, 429 responses may include Retry-After:

```java
this.mockMvc.perform(get("/api/reports")
        .header("X-Test-Rate-Limit", "exceeded"))
    .andExpect(status().isTooManyRequests())
    .andExpect(header().exists(HttpHeaders.RETRY_AFTER))
    .andExpect(jsonPath("$.code").value("RATE_LIMIT_EXCEEDED"))
    .andDo(document("reports-rate-limited",
        responseHeaders(
            headerWithName(HttpHeaders.RETRY_AFTER)
                .description("Timestamp or duration the client should wait before retrying.")
        ),
        responseFields(
            fieldWithPath("code").description("Rate limit error code."),
            fieldWithPath("message").description("Error message.")
        )));
```

Retry-After can represent seconds or an HTTP-date. Tests should verify the format/value guaranteed by the API. The X-Test-Rate-Limit header is only a test simulation mechanism and should not become part of the production contract.

## 10. Testing Server and Dependency Errors

Unexpected errors usually return 500; gateway or dependency errors may map to 502, 503, or 504 depending on architecture.

```java
when(inventoryClient.findStock(501))
    .thenThrow(new InventoryUnavailableException());

this.mockMvc.perform(get("/api/products/{id}/availability", 501))
    .andExpect(status().isServiceUnavailable())
    .andExpect(jsonPath("$.code").value("DEPENDENCY_UNAVAILABLE"))
    .andDo(document("product-availability-unavailable",
        responseFields(
            fieldWithPath("code").description("Dependency error code."),
            fieldWithPath("message").description("Error message."),
            fieldWithPath("traceId").description("Trace ID.")
        )));
```

Tests should verify that exception handlers conceal internal details. Never include internal hostnames, SQL statements, stack traces, or credentials in documented error bodies.

## 11. Using RFC 9457 Problem Details

If the application standardizes errors with Problem Details:

```json
{
  "type": "https://api.example.test/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "The requested product was not found.",
  "instance": "/api/products/9999",
  "code": "PRODUCT_NOT_FOUND"
}
```

Test:

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
    .andDo(document("products-get-not-found",
        responseFields(
            fieldWithPath("type").description("URI identifying the problem type."),
            fieldWithPath("title").description("Short title of the problem."),
            fieldWithPath("status").description("HTTP status of the problem."),
            fieldWithPath("detail").description("Specific explanation for this occurrence."),
            fieldWithPath("instance").description("URI referencing the occurrence."),
            fieldWithPath("code").description("Stable API error code.")
        )));
```

This example includes the code extension member. If the payload has other extension or optional fields, descriptors must reflect the real schema; do not copy examples without checking the response.

## 12. Reusing Descriptors for Common Error Schemas

Multiple operations can share an error response structure:

```java
private static final FieldDescriptor[] BASIC_ERROR_FIELDS = {
    fieldWithPath("code").description("Stable error code."),
    fieldWithPath("message").description("Error message."),
    fieldWithPath("traceId").description("Request trace ID.")
};
```

Using it for a not-found operation:

```java
responseFields(BASIC_ERROR_FIELDS)
```

Validation errors can extend the descriptors:

```java
responseFields(
    fieldWithPath("code").description("Error code."),
    fieldWithPath("message").description("Error message."),
    fieldWithPath("traceId").description("Trace ID."),
    fieldWithPath("details").description("List of per-field errors."),
    fieldWithPath("details[].field").description("Invalid field."),
    fieldWithPath("details[].reason").description("Reason the field is invalid.")
)
```

Do not reuse one descriptor array across all error types if the actual schemas differ. Strict REST Docs will detect the discrepancy; separate base descriptors and response-type extensions.

## 13. Separate Operation IDs for Each Error Type

Each response with a different status/schema should have its own operation ID:

| Error Type | Suggested Operation ID |
| --- | --- |
| Validation | products-create-validation-error |
| Unauthenticated | profile-unauthenticated |
| Forbidden | admin-reports-forbidden |
| Not found | products-get-not-found |
| Conflict | products-create-conflict |
| Rate limit | reports-rate-limited |
| Dependency unavailable | product-availability-unavailable |

Example include:

```asciidoc
== Get Product Success
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Product Not Found
include::{snippets}/products-get-not-found/http-response.adoc[]
include::{snippets}/products-get-not-found/response-fields.adoc[]
```

Do not share an operation ID between 200 success and 404 not found. Files such as http-response.adoc or response-fields.adoc can be overwritten.

## 14. Using WebTestClient for Reactive Errors

WebFlux endpoints can emit errors from a publisher:

```java
when(productService.findById(9999))
    .thenReturn(Mono.error(new ProductNotFoundException(9999)));

this.webTestClient.get()
    .uri("/api/products/{id}", 9999)
    .exchange()
    .expectStatus().isNotFound()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
    .consumeWith(document("products-get-not-found",
        responseFields(
            fieldWithPath("code").description("Error code."),
            fieldWithPath("message").description("Error message.")
        )));
```

WebTestClient awaits the response from the publisher and lets you assert status/headers/body before documenting. Standard error responses should have a finite body.

## 15. Data Safety in Error Snippets

Before saving snippets, verify:

- No real access tokens, refresh tokens, session IDs, or cookies.
- No real passwords, API keys, secrets, or authorization headers.
- No stack traces, SQL statements, internal file paths, or internal hostnames.
- No real emails, phone numbers, addresses, or personal data unless necessary.
- Trace IDs in fixtures are dummy values.
- Error messages do not disclose the existence of accounts or resources outside security policy.

REST Docs records the tested exchange; it does not automatically mask all sensitive data. Use dummy fixtures and inspect snippet output before publishing.

## 16. Common Pitfalls

| Symptom | Possible Cause | Solution |
| --- | --- | --- |
| Error test receives 200 instead of 400 | Validation is not enabled or exception handler handles it improperly | Check @Valid, provider, and controller advice |
| 401 and 403 are mixed up | Confusing authentication with authorization | Clarify principal state and security contract |
| Unstable error code | Relying on clients parsing messages | Publish machine-readable codes |
| Error descriptor mismatch | Response schema differs from example | Compare actual payload and fix field paths |
| Error response contains stack trace | Exception handler returns internal details | Standardize public error body |
| Rate-limit test depends on time | Using a real limiter or unfixed clock | Mock policy/clock or use test configuration |
| Error snippet gets overwritten | Multiple error cases share the same operation ID | Separate operation IDs |
| Test checks only status | Code/details/headers not verified | Assert error body and important metadata |
| Documentation contains real token | Fixture copied from a live environment | Replace with dummy data and audit snippets |
| 503 assumed endlessly retryable | No clear retry policy | Document retry limits/backoff and idempotency |

## 17. Practice Exercise

1. Create a unified error response schema with code, message, and traceId.
2. Write a validation error documentation test for POST /api/products; assert 400 and failing fields.
3. Write a 401 test for missing token and a 403 test for a user lacking roles.
4. Write a 404 test for a nonexistent product ID.
5. Write a 409 test for a duplicate SKU.
6. Write a 429 test with Retry-After if the API supports rate limiting.
7. Write a 503 test for dependency unavailable and verify the error body exposes no internal details.
8. Use distinct operation IDs for each error scenario and include snippets in the Error responses section.
9. Inspect generated snippets to ensure no credentials or personal data appear.

**Self-assessment Questions**

1. How does a validation error differ from a business conflict?
2. When should 401 be returned versus 403?
3. Why is a stable error code more useful than having clients parse messages?
4. How does Retry-After help clients handle 429?
5. Why should success and error responses not share an operation ID?
6. When is RFC 9457 Problem Details appropriate?
7. What information should never appear in error snippets?
8. Why assert the error body in addition to asserting the status?

## Official References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): generating snippets from HTTP tests.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): documenting error response fields.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): REST error handling and Problem Details.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standardized error response format.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): meanings of status codes and HTTP headers.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): testing authentication and authorization in Spring Security.

**Practice Conclusion:** Document all public error types that clients need to handle: validation, authentication, authorization, not found, conflict, rate limit, and dependency/server errors. Each test must assert status, headers, and error body per contract before REST Docs generates snippets. Use stable error codes, separate operation IDs, schema-accurate descriptors, and secret-free fixtures so error documentation can be used safely in real integrations.
