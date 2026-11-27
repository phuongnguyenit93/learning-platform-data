# Response Fields for Error Payloads

## 1. Why Document Error Responses?

In the **SPRING_REST_DOCS** module, Spring REST Docs generates REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Documentation needs to describe not only successful responses, but also authentication errors, validation failures, resource not found errors, conflicts, rate limits, and server errors.

An error response can contain a status, a stable error code, a message, a list of validation field errors, a correlation ID, and support links. If you only write 400 Bad Request without describing the body, clients have to guess the error structure.

Example payload:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more fields failed validation rules.",
  "instance": "/api/accounts",
  "code": "VALIDATION_ERROR",
  "violations": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email format is invalid."
    }
  ]
}
```

Spring REST Docs uses responseFields(...) and fieldWithPath(...) to describe each field. When a test calls document(...), REST Docs validates the payload against the descriptors and generates the response-fields.adoc snippet. This ensures error documentation is verified against actual responses in tests.

## 2. Choosing an Error Payload Structure

Before writing descriptors, determine whether the API uses a standard error format or a custom schema.

### 2.1. Problem Details per RFC 9457

Problem Details provides a standard structure for HTTP errors:

| Field | Meaning |
| --- | --- |
| type | URI identifying the problem type; defaults to about:blank |
| title | Short summary of the problem type |
| status | Corresponding HTTP status |
| detail | Specific explanation for this occurrence of the problem |
| instance | URI referencing the specific occurrence of the problem |

Applications can add extension members such as code, violations, traceId, or errors. Extensions must be documented in the contract.

Example:

```json
{
  "type": "https://api.example.com/problems/not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Order ORD-42 was not found.",
  "instance": "/api/orders/ORD-42",
  "code": "ORDER_NOT_FOUND"
}
```

Do not confuse the HTTP status line with the status field in the body. Tests should check both if the contract requires them to match. Not every API uses every member or extension; only document fields belonging to the actual response.

### 2.2. Custom Error Schema

An API can use a custom envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Submitted data is invalid.",
    "timestamp": "2026-11-17T08:30:00Z",
    "correlationId": "req-123"
  },
  "fieldErrors": [
    {
      "field": "email",
      "rejectedValue": "not-an-email",
      "reason": "INVALID_FORMAT"
    }
  ]
}
```

This schema is also documented with responseFields(...). Use JSON paths matching the real payload; do not force a custom schema to look like Problem Details if the server does not implement that standard.

## 3. Declaring responseFields for Error Payloads

Descriptors for a Problem Details response:

```java
responseFields(
    fieldWithPath("type").description("URI identifying the problem type"),
    fieldWithPath("title").description("Short title describing the error type"),
    fieldWithPath("status").description("HTTP status in the payload"),
    fieldWithPath("detail").description("Explanation for this error occurrence"),
    fieldWithPath("instance").description("URI referencing this error occurrence"),
    fieldWithPath("code").description("Stable error code for client handling")
)
```

responseFields(...) describes the body. It does not automatically describe the status line or headers. If clients need to know the status, Content-Type, Retry-After, or WWW-Authenticate, use http-response.adoc and responseHeaders(...).

Each descriptor must reflect a field present in the payload. If the response has an undeclared extension field, strict payload documentation will fail when the test runs.

## 4. Required, Optional, and Nullable

Not every field is always present. Spring REST Docs allows marking fields as optional:

```java
responseFields(
    fieldWithPath("type").description("URI identifying the problem type"),
    fieldWithPath("title").description("Problem type title"),
    fieldWithPath("status").description("HTTP status"),
    fieldWithPath("detail").description("Error explanation"),
    fieldWithPath("instance").optional()
        .description("URI referencing the error occurrence, if available")
)
```

Distinguish between:
- **Required:** the key must appear in the JSON.
- **Optional:** the key may be absent.
- **Nullable:** the key appears, but its value may be JSON null.
- **Empty:** the key has an empty string, empty array, or empty object value depending on the schema.

optional() states that a field may be omitted. It does not mean nullable. If a field is required but allows null, document the semantics and test the null case; do not mark it optional just to make the test pass.

## 5. Describing Nested Field Errors

Validation errors often contain a list of per-field errors. Use the array JSON path:

```java
responseFields(
    fieldWithPath("code").description("Overall error code"),
    fieldWithPath("violations").description("List of validation violations"),
    fieldWithPath("violations[].field").description("Name of the invalid field"),
    fieldWithPath("violations[].code").description("Stable error code for the field"),
    fieldWithPath("violations[].message").description("Message explaining the error")
)
```

| Path | Meaning |
| --- | --- |
| violations | List of violations |
| violations[].field | Field name |
| violations[].code | Error code |
| violations[].message | Message for client/user |

Deeply nested objects use full paths such as error.code, error.message, or violations[].arguments[].name. Descriptor paths are JSON paths, not Java property names if the serializer renames them.

If an array can be empty, descriptors still describe its elements when present. You should have a test with at least one element so REST Docs verifies the nested paths; a separate test can verify an empty array is a valid response.

## 6. rejectedValue and Sensitive Data

Error payloads sometimes return rejectedValue so clients can display the error. This is useful for harmless data, but dangerous if the field is a password, token, or secret.

Safer payload:

```json
{
  "field": "email",
  "code": "INVALID_FORMAT",
  "message": "Email format is invalid."
}
```

If the contract includes rejectedValue, decide which fields are allowed to be echoed back. Never return entered passwords or tokens. HTTP tests must verify sensitive data is actually absent from the response; merely masking it in snippets is not enough.

For fields allowed to be returned, use a stable dummy fixture:

```java
fieldWithPath("violations[].rejectedValue").optional()
    .description("Rejected value if the contract permits displaying it")
```

Documentation should clarify that clients should not rely on rejectedValue if the server may omit the field or mask values depending on data type.

## 7. Combining responseFields with responseHeaders

An error contract is not just the body. Certain headers affect how clients handle errors:

- Content-Type: error representation format, e.g., application/problem+json.
- Retry-After: timestamp or wait duration before retrying.
- WWW-Authenticate: authentication challenge when receiving 401.
- X-Request-Id or Trace-Id: tracing ID.
- Location: related URI if specified by the contract.

Example:

```java
.andDo(document("orders-not-found",
    responseHeaders(
        headerWithName("Content-Type")
            .description("Media type of the error response"),
        headerWithName("X-Request-Id").optional()
            .description("Request trace ID if provided")
    ),
    responseFields(
        fieldWithPath("type").description("Problem type URI"),
        fieldWithPath("title").description("Error title"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Error details"),
        fieldWithPath("code").description("Application error code")
    )
))
```

responseHeaders(...) and responseFields(...) produce separate snippets. Documentation should include both if clients need both headers and body to handle errors.

## 8. Strict and Relaxed Response Field Documentation

By default, responseFields(...) validates the payload strictly: fields in the payload must be documented and descriptors must match the actual content. This is a good choice for catching new fields or schema changes that have not been updated in documentation.

Use relaxedResponseFields(...) when you only want to describe part of a payload and allow other unlisted fields:

```java
relaxedResponseFields(
    fieldWithPath("type").description("Problem type URI"),
    fieldWithPath("title").description("Error title"),
    fieldWithPath("status").description("HTTP status")
)
```

Relaxed mode is useful for large envelopes or when documentation focuses on only one part. However, if used for the entire error contract, new fields can appear without being documented. Prefer strict descriptors for stable public responses; use relaxed intentionally and state clearly that the snippet only covers a subset.

Distinguish relaxedResponseFields from subsectionWithPath: a subsection describes an object/array region as a single block; relaxed mode allows omitting unlisted fields.

## 9. MockMvc Example: Documenting Validation Errors

This example uses a controller advice that maps a validation exception to a payload with code and violations. The test sends an invalid request, verifies the raw HTTP response, and then generates the response fields snippet.

```java
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ValidationErrorDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .setControllerAdvice(new ApiErrorAdvice())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentsInvalidEmailResponse() throws Exception {
        mockMvc.perform(post("/api/accounts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                            {"email":"not-an-email"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.violations[0].field").value("email"))
                .andDo(document("accounts-create-validation-error",
                        responseFields(
                                fieldWithPath("code").description("Overall error code"),
                                fieldWithPath("message").description("General message"),
                                fieldWithPath("violations").description("List of violating fields"),
                                fieldWithPath("violations[].field").description("Field name"),
                                fieldWithPath("violations[].code").description("Validation error code"),
                                fieldWithPath("violations[].message").description("Description of the field error")
                        )
                ));
    }

    record CreateAccountRequest(@NotBlank @Email String email) {}

    @RestController
    static class AccountController {
        @PostMapping("/api/accounts")
        ResponseEntity<Void> create(@Valid @RequestBody CreateAccountRequest request) {
            return ResponseEntity.noContent().build();
        }
    }

    @RestControllerAdvice
    static class ApiErrorAdvice {
        @ExceptionHandler(MethodArgumentNotValidException.class)
        ResponseEntity<Map<String, Object>> invalid(
                MethodArgumentNotValidException exception) {
            List<Map<String, String>> violations =
                    exception.getBindingResult().getFieldErrors().stream()
                            .map(error -> Map.of(
                                    "field", error.getField(),
                                    "code", "INVALID_FORMAT",
                                    "message", "Invalid value"))
                            .toList();

            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "code", "VALIDATION_ERROR",
                            "message", "Invalid request",
                            "violations", violations
                    ));
        }
    }
}
```

This is an illustrative example. In a real project, error codes should be mapped by constraint/domain rather than hardcoding INVALID_FORMAT for every error. You can use FieldError.getCode() or stable domain codes. A Bean Validation provider dependency is required for @Valid to be enforced.

With a Spring Boot application context, you should test the actual controller advice and validation configuration. Standalone MockMvc requires registering the advice and ensuring a validator is configured if the setup does not auto-detect a provider.

## 10. Documenting Multiple Types of Error Responses

An API typically has multiple error categories:

| Scenario | HTTP status | Example error code |
| --- | --- | --- |
| Unparseable JSON | 400 | MALFORMED_JSON |
| Field validation failure | 400 or 422 per contract | VALIDATION_ERROR |
| Unauthenticated | 401 | UNAUTHENTICATED |
| Insufficient permissions | 403 | FORBIDDEN |
| Resource not found | 404 | RESOURCE_NOT_FOUND |
| State conflict | 409 | STATE_CONFLICT |
| Too many requests | 429 | RATE_LIMITED |
| Server error | 500 | INTERNAL_ERROR |
| Service temporarily unavailable | 503 | SERVICE_UNAVAILABLE |

Use separate snippet identifiers:

```java
document("accounts-create-validation-error")
document("accounts-get-unauthenticated")
document("orders-get-not-found")
document("orders-cancel-conflict")
document("orders-get-rate-limited")
```

Do not lump all errors into one snippet if payloads or headers differ. Splitting by outcome helps clients see the exact status, code, fields, and retry behavior for each case.

## 11. Organizing Error Snippets in Asciidoctor

The generated snippets for the accounts-create-validation-error operation can be included as follows:

```adoc
= Account API

== Errors When Creating an Account

=== HTTP response
include::${snippets}/accounts-create-validation-error/http-response.adoc[]

=== Error response fields
include::${snippets}/accounts-create-validation-error/response-fields.adoc[]
```

Section titles should clearly state the status and outcome, such as “400 — Invalid request”, rather than just “Error”.

When an error schema is shared, describe the envelope once and include specific snippets for each operation. Each operation still needs to document its distinct status, code, and fields.

## 12. Common Pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| responseFields reports undocumented field | Payload contains an undeclared field | Add a descriptor or use relaxed intentionally |
| Snippet missing nested violations | Array JSON path not declared | Use violations[].field and child paths |
| Optional field treated as required | Forgot optional() | Mark optional according to the contract |
| Using optional for nullable | Confusing absent key with null key | Document/test nullable separately |
| Using request descriptors for error body | Wrong payload direction | Use responseFields |
| Documenting only status, omitting body | Error schema not described | Include response-fields.adoc |
| Using relaxed for all errors | Fails to detect new fields | Prefer strict for public contracts |
| Body status differs from HTTP status | Inconsistent exception mapping | Assert both status line and body |
| rejectedValue leaks data | Returning password/token in error | Exclude from response and test absence |
| Error code changes with exception class | Using unstable framework codes | Map to stable domain codes |
| Error response has wrong Content-Type | Advice does not set media type | Check header and contract |
| Stale snippets remain in docs | Tests did not run before Asciidoctor | Configure task dependency |

## 13. Practice Exercise

Using the endpoints POST /api/accounts and GET /api/orders/{id}:

1. Create a validation error response containing code, message, and violations.
2. Use responseFields(...) to describe the envelope and violations[] paths.
3. Remove one field from the descriptors to observe strict mode reporting an undocumented field.
4. Mark instance as optional; test both cases where the key is present and absent.
5. Create a JSON null case to distinguish nullable from optional.
6. Add Content-Type and X-Request-Id response headers using responseHeaders(...).
7. Create a Problem Details response for 404 and describe standard members along with the code extension.
8. Create 401, 403, 409, and 429 cases; use separate snippet identifiers per operation/outcome.
9. Add a fake rejectedValue, then verify that passwords/tokens never appear in the actual HTTP response.
10. Include the error response and response fields in Asciidoctor; run documentation tests before rendering.

**Completion criteria:** You can describe error payloads using responseFields, declare nested JSON paths, distinguish required/optional/nullable, intentionally choose strict or relaxed mode, verify HTTP status/headers/body, and organize error snippets by operation/outcome.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): responseFields, field descriptors, and relaxed payload documentation.
- [Spring REST Docs — Response Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/headers.html): describing response headers.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): Problem Details structure and extension members.
- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): mapping exceptions to HTTP error responses.
