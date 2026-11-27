# Authorization, Correlation IDs, and Business Headers

HTTP headers can carry authentication information, support request tracing, or pass business context that affects how the server processes a request. These three common groups have different purposes and risks: **Authorization** presents credentials; **correlation IDs** link logs and processing steps; **business headers** such as tenant or locale carry API-defined context. Documentation must accurately describe how to send them, required conditions, semantics, and corresponding responses.

In **Spring REST Docs**, headers are documented using `requestHeaders(...)` or `responseHeaders(...)` combined with `headerWithName(...)`. Tests can verify presence, values, or the effect of headers; descriptors generate snippet tables to insert into Asciidoctor/Markdown. This lesson belongs to the **Headers** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates request, response, payload, parameter, and header snippets, and integrates them into builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the purposes of Authorization, correlation IDs, and business headers.
2. Document request headers with `requestHeaders(...)` and response headers with `responseHeaders(...)`.
3. Use assertions to verify required headers and server behavior that depends on headers.
4. Document Bearer tokens without exposing real credentials in snippets.
5. Describe how correlation IDs are generated, propagated, and returned across components.
6. Determine whether tenant, locale, or other custom headers are required, optional, or rejected.
7. Generate header snippets and verify documentation in CI.

## 2. Viewing Headers by Role

A header may appear only in requests, only in responses, or in both directions. Before writing descriptors, determine the right direction and responsibility.

| Group | Common Location | Purpose | Contract Questions |
| --- | --- | --- | --- |
| Authorization | Request | Present authentication credentials | Which scheme, when required, where to get tokens, what errors occur? |
| Correlation ID | Request and/or response | Link logs, traces, and processing steps | Can clients send it, does the server generate one if missing, which header name does the response use? |
| Tenant header | Request | Select tenant/data scope if the API is designed this way | Who is permitted to choose a tenant, how does the server verify against identity? |
| Locale/language | Request; response may include `Content-Language` | Select representation language | What are the default language and fallback? |
| Custom business context | Request or response | Pass domain-specific context | What are the valid values, effects, and permissions? |

Do not create custom headers simply because a value can fit in a header. Determine whether it belongs to HTTP semantics, payload, query parameters, or an authentication mechanism. Only publish custom headers when they have stable semantics and clients need to know how to use them.

## 3. Authorization: Documenting Authentication Without Exposing Credentials

### 3.1. Bearer Tokens in Requests

For APIs using HTTP Bearer authentication, clients typically send:

```http
GET /api/orders/501 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>
```

The `Authorization` header carries the `Bearer` scheme together with an access token. Documentation needs to explain which authorization mechanism issues the token, which header carries it, which endpoints require authentication, and how expired or invalid tokens are handled.

Do not include real tokens, staging/production tokens, or developer tokens in public snippets. Use placeholders such as `Bearer <access-token>` or dummy values used only in tests. If tests generate dynamic tokens, sanitize the values in output before publishing.

### 3.2. Documenting Request Headers with Spring REST Docs

With MockMvc, a test can send a dummy token in the fixture and declare descriptors:

```java
mockMvc.perform(
        get("/api/orders/{orderId}", 501L)
            .header("Authorization", "Bearer docs-test-token")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andDo(document("orders-get-authenticated",
        requestHeaders(
            headerWithName("Authorization")
                .description(
                    "Bearer access token issued to an authenticated client"
                ),
            headerWithName("Accept")
                .description("Response media type accepted by the client")
        )
    ));
```

This example illustrates where to attach descriptors. To prove authentication, tests must run with the security filter chain and an appropriate authentication mechanism. With a standalone controller without security filters, sending the header only proves the header was sent—**not that the server actually authenticated the token**.

Key static imports:

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

If the application uses Spring Security, set up a test context with the filter chain and appropriate authentication fixtures. You can use a dummy test token or test principal; real credentials are not needed to prove the contract.

### 3.3. Checking Authentication Outcomes

| Scenario | Common HTTP Status | What to Verify |
| --- | --- | --- |
| Missing Authorization | 401 Unauthorized | Endpoint requires authentication; error response matches API schema |
| Invalid/expired token | 401 Unauthorized | Server rejects and returns appropriate error |
| Valid token lacking permission | 403 Forbidden | Identity is authenticated but not authorized |
| Valid token with sufficient permission | Success status per operation | Payload contains only permitted data |

Status codes and error bodies depend on the contract. Some systems return 404 to avoid revealing a resource's existence when the caller lacks permission; documentation must reflect the actual policy.

Example test without a token:

```java
@Test
void getOrder_withoutToken() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 501L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isUnauthorized())
        .andDo(document("orders-get-unauthenticated",
            responseFields(
                fieldWithPath("code").description("Error code"),
                fieldWithPath("message").description("Error message")
            )
        ));
}
```

This test assumes the API returns a JSON error with two fields. If the actual response has no body or uses a different schema, adjust the descriptors to match the actual response. Do not declare `Authorization` as a header present in this request.

### 3.4. Keeping Authorization Safe in Snippets

`http-request.adoc`, cURL, and HTTPie snippets can record the headers sent by the test. Therefore:

- Use short-lived dummy tokens valid only in tests.
- Do not read real secrets from developer/CI environment variables into documented requests.
- If tokens are generated dynamically, replace/mask the value in snippets using an appropriate preprocessor.
- Review HTTP, cURL, and HTTPie snippets before publishing.
- Do not commit tokens into test sources, logs, fixtures, or artifacts.

If the goal is to test permissions, you can use a test security context with a dummy principal. If you need to prove Bearer token parsing, use a test-generated dummy valid token and sanitize snippets before publishing.

## 4. Correlation ID: Linking a Request Across Multiple Components

### 4.1. Role and Contract

A correlation ID is an identifier used to link logs or events emitted from the same request or processing flow. Clients may send an ID; the server may preserve it, validate its format, or generate a new ID if missing and return it in the response. The header name is not standardized across all applications; projects may choose `X-Correlation-Id` or `X-Request-Id`.

Request:

```http
GET /api/orders/501 HTTP/1.1
Accept: application/json
X-Correlation-Id: docs-flow-001
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-Id: docs-flow-001

{"id":501,"status":"CONFIRMED"}
```

Documentation must clarify whether the server preserves the ID or replaces it with a server-generated ID, whether the ID is forwarded to downstream services, what format limits exist, and that clients should provide this ID when reporting issues. Do not promise preservation if the gateway/server can generate a different ID.

### 4.2. Recording Both Request and Response Headers

If the contract says the server echoes back the same correlation ID sent by the client, the test can document both directions:

```java
mockMvc.perform(
        get("/api/orders/{orderId}", 501L)
            .header("X-Correlation-Id", "docs-flow-001")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(header().string(
        "X-Correlation-Id", "docs-flow-001"
    ))
    .andDo(document("orders-get-with-correlation",
        requestHeaders(
            headerWithName("X-Correlation-Id")
                .description("Correlation ID provided by the client")
        ),
        responseHeaders(
            headerWithName("X-Correlation-Id")
                .description("Correlation ID returned for log lookup")
        )
    ));
```

This is a specific contract: the server returns the same value. If the server only accepts the ID for logging and returns its own ID, assertions and descriptions must reflect that policy.

### 4.3. Server Generating an ID When the Client Omits It

Another policy is for the server to generate an ID if the request lacks the header:

```java
mockMvc.perform(
        get("/api/orders/{orderId}", 501L)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Correlation-Id"))
    .andDo(document("orders-get-generated-correlation",
        responseHeaders(
            headerWithName("X-Correlation-Id")
                .description("ID generated by the server when the request does not provide one")
        )
    ));
```

If the response always includes the header per contract, a required descriptor and `exists` assertion are appropriate. If the response may omit the ID, the descriptor can use `optional()` and prose must explain the condition. Do not use `optional()` just because a fixture does not yet generate the header while the API commits to always returning it.

### 4.4. Correlation IDs Differ from Access Tokens

| Characteristic | Authorization | Correlation ID |
| --- | --- | --- |
| Purpose | Authenticate or present credentials | Trace and link processing |
| Used for authorization? | Yes, depending on scheme/token and policy | No |
| Is it a secret? | Credentials must be protected | Usually not a credential, though avoid embedding sensitive data |
| Downstream propagation | According to designed identity mechanism | Usually propagated to preserve trace context |
| When missing | May be rejected with 401 | Server may generate or allow absence per contract |

Do not use correlation IDs as proof of authentication. Knowing a request ID does not grant permission to view data or modify resources.

## 5. Business Headers: Tenant, Locale, and API Context

Business headers are custom headers defined by an API to pass context. They should be used selectively, with clear semantics and effects.

### 5.1. Tenant Header

A multi-tenant API might require clients to send:

```http
GET /api/invoices HTTP/1.1
Authorization: Bearer <access-token>
X-Tenant-Id: tenant-demo
Accept: application/json
```

Documentation must specify where the tenant ID is issued, which endpoints require the header, how the server verifies that the tenant belongs to the authenticated principal's scope, and what happens when the tenant is missing, nonexistent, or unauthorized.

**`X-Tenant-Id` is not proof of authorization.** The server must verify that the selected tenant lies within the authenticated identity's scope. Blindly trusting client-supplied values allows users to swap tenant IDs to access unauthorized data.

Example descriptor:

```java
requestHeaders(
    headerWithName("Authorization")
        .description("Bearer token of the authenticated client"),
    headerWithName("X-Tenant-Id")
        .description("Tenant ID within the scope the client is authorized for")
)
```

Tests must cover both valid tenants and unauthorized tenants. A test that merely confirms the server accepts the header does not prove tenant data isolation.

### 5.2. Locale or Language

Some APIs use `Accept-Language` to select the response language. This header has standard HTTP semantics; if an API uses a different custom header, explain precedence rules.

Request:

```http
GET /api/products/7 HTTP/1.1
Accept: application/json
Accept-Language: vi
```

The response may return `Content-Language: vi` to indicate the representation language. Documentation should list supported locales, the default when absent, the fallback when unsupported, and whether locale changes data or only display strings. If representations vary by `Accept-Language`, consider `Vary: Accept-Language` according to how the API is implemented.

### 5.3. Other Custom Business Headers

| Example Header | Possible Purpose | What Needs to Be Documented |
| --- | --- | --- |
| `X-Client-Version` | Client version | Format, whether used for compatibility or telemetry |
| `X-Channel` | Sales channel/request source | Allowed values, business impact, and permissions |
| `X-Region` | Region for rule evaluation | Region codes, fallback, and permission checks |
| `Idempotency-Key` | Identifier for retryable requests | Scope, retention period, and behavior when reused with a different payload |
| `If-Match` | Validator-based update condition | How to obtain ETag and response when validator mismatches |

These are examples of custom/context headers, not Spring REST Docs requirements or mandatory headers for every API. Use them only when your system defines them. If data is a core resource attribute, a request body or query parameter may be more appropriate than a header.

## 6. Combining requestHeaders and responseHeaders in One Operation

A single test can document multiple header groups:

```java
.andDo(document("invoices-get",
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer token for client authentication"),
        headerWithName("X-Tenant-Id")
            .description("Tenant ID within the client's permitted scope"),
        headerWithName("X-Correlation-Id")
            .description("Correlation ID provided by the client")
    ),
    responseHeaders(
        headerWithName("X-Correlation-Id")
            .description("Correlation ID returned in the response"),
        headerWithName("Content-Type")
            .description("Media type of the representation")
    )
));
```

The test can generate both `request-headers.adoc` and `response-headers.adoc` under the same identifier. Raw `http-request.adoc` and `http-response.adoc` still illustrate headers in the HTTP exchange; descriptor tables explain the selected headers.

### 6.1. Required and Optional Headers

Required headers should have a non-optional descriptor and assertions if presence is an important commitment. Optional headers can use:

```java
requestHeaders(
    headerWithName("X-Correlation-Id")
        .description("Correlation ID that the client may provide")
        .optional()
)
```

`optional()` in a descriptor indicates that the header may not appear in the documented message. It does not mean the server ignores all values, skips format validation, or skips authorization. The contract must still explain behavior when missing.

### 6.2. Splitting Operations by Condition

Do not include required descriptors across all scenarios if a header only appears in certain responses. You can create separate operations:

- `orders-get-authenticated`: request includes Authorization.
- `orders-get-unauthenticated`: Authorization not sent, authentication error response.
- `orders-get-with-correlation`: client sends correlation ID.
- `orders-get-generated-correlation`: client omits ID, server generates and returns ID.

Separate operations allow snippets to describe requests/responses accurately and avoid misleading header tables.

## 7. Generating Snippets and Compiling Documentation

When a test invokes `requestHeaders(...)` or `responseHeaders(...)`, Spring REST Docs generates header tables for the corresponding identifier. In standard configurations, the filenames are `request-headers.adoc` and `response-headers.adoc`.

Example output:

```text
target/generated-snippets/
└── invoices-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-headers.adoc
    └── response-headers.adoc
```

Specific filenames depend on the requested descriptors. Do not include a snippet if the test does not generate it.

AsciiDoc can embed the tables alongside HTTP examples:

```asciidoc
=== Authentication and request context

The API requires a Bearer access token. Clients send the token in Authorization.
The tenant ID only selects the processing scope; the server still verifies whether the tenant belongs to
the authenticated identity's permissions.

==== Request headers

include::{snippets}/invoices-get/request-headers.adoc[]

==== Sample request

include::{snippets}/invoices-get/http-request.adoc[]

==== Response headers

include::{snippets}/invoices-get/response-headers.adoc[]

==== Sample response

include::{snippets}/invoices-get/http-response.adoc[]
```

The `snippets` attribute must point to the Spring REST Docs output directory, such as `target/generated-snippets` in Maven or `build/generated-snippets` in Gradle depending on project configuration. For Markdown, a compatible conversion/snippet-inlining step is required; Asciidoctor's include syntax is not a built-in feature of every Markdown renderer.

Handwritten prose must still explain Authorization, correlation ID, and tenant semantics. Snippets do not replace security policies or business rules.

## 8. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Token appears in `http-request.adoc` | Test uses real credentials or lacks snippet sanitization | Use dummy tokens, preprocessors, and inspect HTTP/cURL/HTTPie snippets |
| Authorization descriptor exists but test does not prove auth | Header sent to controller without security filter | Use a test setup with security filter/authorization |
| Missing-token case has Authorization in request snippet | Wrong fixture/test case used | Create an operation that omits the header |
| Correlation ID changes every build | Random value recorded verbatim | Use a fixed ID or normalize the snippet |
| Server returns a different correlation ID while docs say preserved | Description/assertion assumes wrong semantics | Verify ID generation/propagation policy |
| Tenant header treated as access permission | Server trusts client value without checking principal | Enforce tenant authorization and test cross-tenant access |
| Locale header does not change response as documented | Test does not assert content/language | Add assertions and clearly state fallback |
| Header table misses a response header | Descriptor not declared | Add `requestHeaders`/`responseHeaders` if the header belongs to the contract |
| Header snippet does not appear | Test did not run or descriptor was not invoked | Check test reports, `document(...)`, and operation identifier |
| Internal headers published | Recording all headers sent by server | Select only public headers and sanitize raw snippets |
| CI uses stale snippets | Output was not cleaned or tests were skipped | Run a clean build and ensure tests run before rendering |

## 9. Best Practices

1. Identify header direction: Authorization and tenant are usually on the request; correlation IDs can appear on both sides.
2. Document concrete semantics: scheme, token source, ID propagation, tenant scope, and locale fallback.
3. Separate authentication from tracing: correlation IDs are not credentials and do not grant permissions.
4. Never use real secrets; documentation should contain only placeholders or dummy test data.
5. Combine descriptors with assertions to verify important values and security effects.
6. Test tenant isolation; the server must validate the tenant against identity and permissions.
7. Normalize dynamic correlation IDs so snippets remain stable.
8. Split operations by scenarios with/without valid tokens, correlation IDs, or tenants.
9. Only publish custom headers that have a clear contract.
10. Inspect both raw snippets and descriptor tables before publishing.

## 10. Practice Exercise

Document `GET /api/invoices/{invoiceId}` of a multi-tenant API. Hypothetical contract:

- Clients need a valid Bearer token.
- Clients send `X-Tenant-Id` within their authorized scope.
- Clients may send `X-Correlation-Id`; if missing, the server generates an ID.
- The response returns `X-Correlation-Id` so clients can look up the request.
- Invalid or unauthorized tenants are rejected according to the defined error schema.

**Tasks:**

1. Write a success test with a dummy token, a valid tenant, and a fixed correlation ID.
2. Use `requestHeaders(...)` to describe `Authorization`, `X-Tenant-Id`, and `X-Correlation-Id`.
3. Use `responseHeaders(...)` to describe the returned correlation ID.
4. Assert status, response data, and correlation ID according to the chosen policy.
5. Write a test without a token and assert the error response; do not include `Authorization` in the request descriptors for this operation.
6. Write a test with an out-of-scope tenant and assert the server does not return another tenant's data.
7. Write a test without a correlation ID and assert the server generates an ID if that is part of the commitment.
8. Review raw snippets to ensure no real tokens or sensitive tenant data are present.
9. Include both header tables in AsciiDoc, explaining that the tenant header does not replace authorization.
10. Run a clean build and confirm tests generate snippets before rendering.

**Completion criteria:** tests protect the stated rules; descriptors accurately reflect request/response headers; tokens are safe; correlation ID semantics are clear; tenant access is checked against the authenticated identity; documentation renders from current snippets.

## 11. Key Takeaways

- Authorization presents authentication credentials; documentation must describe the scheme and how to obtain tokens, and never publish real credentials.
- Correlation IDs link logs and processing flows; they are not tokens and do not grant permissions.
- Business headers such as tenant, locale, or idempotency key should only be used when semantics and application conditions are clearly defined.
- `requestHeaders(...)` documents headers sent by the client; `responseHeaders(...)` documents headers returned by the server; `headerWithName(...)` creates descriptors for each header.
- Assertions verify values/effects; descriptors generate description tables and check consistency with the tested message.
- Separate operations for scenarios with/without valid tokens, correlation IDs, or tenants; normalize dynamic values and sanitize snippets.
- Connect tests, snippets, Asciidoctor/Markdown, and CI so header documentation is regenerated from tested HTTP exchanges.
