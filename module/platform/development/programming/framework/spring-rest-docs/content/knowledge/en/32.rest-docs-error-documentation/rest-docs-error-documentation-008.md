# Documenting Authentication, Authorization, and Not Found Errors

## Learning Objectives

After this lesson, you will be able to:

- Distinguish authentication errors (401), authorization errors (403), resource not found errors (404), and invalid request errors (400).
- Design consistent error responses with stable error codes and useful information for consumers.
- Use Spring Security to describe behavior when credentials are missing, invalid, or lack permissions.
- Use Spring REST Docs to record error responses using responseFields, responseHeaders, and HTTP response snippets.
- Write MockMvc documentation tests for 401, 403, and 404 scenarios.
- Organize separate document identifiers for each error scenario and include them into Asciidoctor.
- Avoid putting stack traces, tokens, session IDs, or internal details into error documentation.

## 1. Why Document Errors?

API documentation is incomplete if it only describes successful requests. Consumers need to know how the server responds when:

- No credentials are sent.
- Invalid, expired, or revoked credentials are sent.
- Authenticated, but lacking permission to perform the operation.
- The resource does not exist or the caller is not permitted to know whether it exists.
- The request is malformed or violates validation rules.

If documentation only states “returns an error when the request is invalid”, consumers do not know which status code to handle, which fields appear in the error body, which error code to branch on, or when to ask the user to log in again.

Spring REST Docs generates documentation from tested HTTP exchanges. Therefore, every error document should start from a test with explicit assertions on status, headers, and body. Descriptors describe the contract; they do not define how Spring Security or controllers handle errors.

## 2. Distinguishing 400, 401, 403, and 404

These statuses represent distinct situations:

| Status | Meaning | What Consumers Usually Do |
| --- | --- | --- |
| 400 Bad Request | Request is invalid, missing/wrong parameters, or payload fails validation | Fix input and resend |
| 401 Unauthorized | Request lacks valid credentials or credentials are rejected | Log in / obtain a new token and retry |
| 403 Forbidden | Caller is authenticated but lacks permission to perform the action | Check roles/scopes or request permissions |
| 404 Not Found | Resource does not exist or API intentionally hides resource existence | Verify ID or access rights per API policy |

401 in HTTP means the request has not been validly authenticated. For HTTP authentication schemes, a 401 response typically needs a WWW-Authenticate header indicating the appropriate challenge. With Bearer tokens, a resource server may return WWW-Authenticate: Bearer along with specified error parameters.

403 typically indicates the server understood the request but refuses to fulfill it due to insufficient permissions. Do not use 401 and 403 interchangeably because consumers handle them differently.

404 does not always prove the resource never existed. Some systems return 404 instead of 403 to avoid disclosing private resources. This must be a consistent policy, tested and documented.

## 3. Designing a Consistent Error Response

A useful error response typically includes:

- A stable type or error code so machines can classify it.
- A short title or message for human readers.
- status matching the HTTP status.
- detail explaining the error at a safe level.
- instance or request identifier for looking up logs when needed.
- field errors if the request has validation errors.

Example JSON in Problem Details style:

```json
{
  "type": "https://api.example.test/problems/insufficient-scope",
  "title": "Insufficient permission",
  "status": 403,
  "detail": "The caller does not have permission to read this order.",
  "instance": "/api/orders/42",
  "code": "ORDER_READ_FORBIDDEN"
}
```

RFC 9457 defines Problem Details for HTTP APIs and obsoletes RFC 7807. Many existing systems still refer to Problem Details/RFC 7807 in documentation or use the application/problem+json media type. For new designs, reference RFC 9457; if an API follows RFC 7807, document the exact contract version implemented.

Not every error response needs every field. Choose a consistent schema and clearly define which fields are required, optional, or extended.

### 3.1. Keep Internal Details Out of detail

Error messages should not contain:

- Stack traces or internal class names.
- SQL queries or database table names.
- Secrets, tokens, cookies, or session identifiers.
- Filesystem paths or internal hostnames.
- Personal information of other users.

Server logs may record technical details according to security policy. API responses should provide enough information for consumers to handle the error along with a request/correlation ID for operations teams to investigate.

## 4. Defining the Contract for Each Scenario

An Orders API might publish:

| Scenario | HTTP status | Sample Error Code | Cause |
| --- | --- | --- | --- |
| Missing Bearer token | 401 | AUTHENTICATION_REQUIRED | No credentials |
| Invalid or expired token | 401 | INVALID_ACCESS_TOKEN | Token rejected |
| Missing scope to read order | 403 | ORDER_READ_FORBIDDEN | Authenticated but lacks permission |
| Order does not exist | 404 | ORDER_NOT_FOUND | Resource not found |
| Invalid order creation payload | 400 | VALIDATION_FAILED | Input violates contract |

The codes in the table are examples. Actual codes must match the error handler and tested responses. If a resource-hiding policy returns 404 to unauthorized callers, clearly document the difference between endpoints that may disclose existence and those that do not.

## 5. How Spring Security Produces 401 and 403

In Spring Security, two key extension points are:

- AuthenticationEntryPoint handles unauthenticated requests and usually returns 401.
- AccessDeniedHandler handles cases where the caller is authenticated but lacks sufficient permissions, and usually returns 403.

With OAuth2 Resource Server, BearerTokenAuthenticationEntryPoint and BearerTokenAccessDeniedHandler can generate responses compliant with the Bearer token protocol. If the application uses a custom error schema, configure the corresponding handlers and verify the WWW-Authenticate header is neither lost nor malformed.

Conceptual configuration example:

```java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_ADMIN")
        .anyRequest().authenticated()
    )
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(problemAuthenticationEntryPoint)
        .accessDeniedHandler(problemAccessDeniedHandler)
    );
```

This is a structural example; bean names and DSL depend on the Spring Security version, authentication type, and how the application standardizes Problem Details.

Do not write a custom controller to catch all authentication errors if the Spring Security filter chain already handles requests before they reach controllers. Documentation tests must run through the real security filter chain to verify behavior.

## 6. Documenting 401 Errors: Missing or Invalid Credentials

Suppose GET /api/orders/42 requires a Bearer token. When no token is provided, the API returns 401.

Example response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid access token is required.",
  "code": "AUTHENTICATION_REQUIRED"
}
```

Not every scheme uses WWW-Authenticate: Bearer. The header must reflect the API's authentication scheme. For Bearer errors, the challenge content may include additional error/error_description parameters per the Bearer token standard.

### 6.1. MockMvc Test for 401

Example test running through Spring Security:

```java
@Test
void returnsUnauthorizedWhenBearerTokenIsMissing() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE,
                    startsWith("Bearer")
            ))
            .andExpect(jsonPath("$.status").value(401))
            .andExpect(jsonPath("$.code")
                    .value("AUTHENTICATION_REQUIRED"))
            .andDo(document("orders-get-unauthorized",
                    responseHeaders(
                            headerWithName(HttpHeaders.WWW_AUTHENTICATE)
                                    .description("Bearer authentication challenge")
                    ),
                    responseFields(
                            fieldWithPath("type").description("URI identifying the problem type"),
                            fieldWithPath("title").description("Error title"),
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("detail").description("Safe description for consumers"),
                            fieldWithPath("code").description("Stable error code")
                    )
            ));
}
```

This test illustrates the descriptors. You will need the appropriate static imports, security test configuration, and error handlers for your project. If the application returns an empty body or a different schema, adjust the test/documentation to match actual behavior rather than forcing an assumed response.

### 6.2. Invalid or Expired Token

Have a separate scenario if the contract distinguishes invalid tokens:

```java
@Test
void returnsUnauthorizedForInvalidToken() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-test-token")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isUnauthorized())
            .andDo(document("orders-get-invalid-token",
                    responseFields(
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("code").description("Stable error code"),
                            fieldWithPath("detail").description("Safe handling information")
                    )
            ));
}
```

If the resource server verifies real JWT signatures, a dummy token string might trigger different behavior. Use a test decoder/key or an intentional token fixture. Do not disable the entire security filter just to make a test return 401.

## 7. Documenting 403 Errors: Authenticated but Insufficient Permissions

Example where the caller has a valid token but lacks the ORDER_READ scope:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/insufficient-scope",
  "title": "Insufficient permission",
  "status": 403,
  "detail": "The caller does not have permission to read this order.",
  "code": "ORDER_READ_FORBIDDEN"
}
```

With Bearer tokens, WWW-Authenticate may be used to describe insufficient_scope per the protocol. Check the actual response from Resource Server and custom handlers; do not add an illustrative header if the server does not emit it.

### 7.1. MockMvc Test for 403

```java
@Test
@WithMockUser(authorities = "SCOPE_PROFILE_READ")
void returnsForbiddenWhenScopeIsInsufficient() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.code").value("ORDER_READ_FORBIDDEN"))
            .andDo(document("orders-get-forbidden",
                    responseFields(
                            fieldWithPath("type").description("URI identifying the problem type"),
                            fieldWithPath("title").description("Error title"),
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("detail").description("Description of missing permission"),
                            fieldWithPath("code").description("Stable error code")
                    )
            ));
}
```

@WithMockUser creates a test principal and does not verify Bearer JWT signatures. If you need to verify full resource server authentication, use JWT test support or a token fixture signed with a test key. The goal of this example is to illustrate an authorization failure after the principal is authenticated.

### 7.2. Distinguishing 401 and 403 in Tests

| Test setup | Typical Expected Outcome |
| --- | --- |
| No authentication | 401 |
| Invalid authentication | 401 |
| Valid authentication, missing authority | 403 |
| Valid authentication, sufficient authority | Request proceeds to controller |

Some configurations may return different statuses depending on entry points, exception translation, or resource-hiding policies. Assert according to the chosen contract.

## 8. Documenting 404 Errors: Resource Not Found

Example:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with the supplied identifier.",
  "code": "ORDER_NOT_FOUND"
}
```

Do not put sensitive IDs or data from other resources into detail. If the API has a policy of hiding resources when the caller lacks permission, the same 404 status can be used for both nonexistence and lack of permission to know existence. The contract must be consistent and avoid side channels via messages or timing.

### 8.1. MockMvc Test for 404

```java
@Test
@WithMockUser(authorities = "SCOPE_ORDER_READ")
void returnsNotFoundForUnknownOrder() throws Exception {
    mockMvc.perform(get("/api/orders/{id}", 999999)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
            .andDo(document("orders-get-not-found",
                    responseFields(
                            fieldWithPath("type").description("URI identifying the problem type"),
                            fieldWithPath("title").description("Error title"),
                            fieldWithPath("status").description("HTTP status"),
                            fieldWithPath("detail").description("Description of not found"),
                            fieldWithPath("code").description("Stable error code")
                    )
            ));
}
```

Ensure ID 999999 does not exist in the test database. Reset the database or use namespaced fixtures so tests do not depend on leftover data.

## 9. Documenting 400 and Validation Errors

400 errors typically occur when the payload has invalid formatting, misses required fields, or fails validation rules.

Example response with a list of field errors:

```json
{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "customerEmail",
      "code": "Email",
      "message": "must be a well-formed email address"
    }
  ]
}
```

In REST Docs, describe nested fields:

```java
responseFields(
    fieldWithPath("type").description("URI identifying the problem"),
    fieldWithPath("title").description("Error title"),
    fieldWithPath("status").description("HTTP status"),
    fieldWithPath("code").description("Error code"),
    fieldWithPath("fieldErrors").description("List of per-field errors"),
    fieldWithPath("fieldErrors[].field").description("Name of the invalid field"),
    fieldWithPath("fieldErrors[].code").description("Validation code"),
    fieldWithPath("fieldErrors[].message").description("Validation message")
)
```

If the API uses Problem Details extension members, clearly document the fieldErrors extension. Do not confuse HTTP status with the status field in JSON; both values must be consistent per contract.

## 10. Organizing Shared Error Descriptors

Many error responses share the same schema. You can create a helper to avoid repeating descriptors:

```java
static FieldDescriptor[] problemFields() {
    return new FieldDescriptor[] {
        fieldWithPath("type").description("URI identifying the problem type"),
        fieldWithPath("title").description("Short title"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Safe description"),
        fieldWithPath("code").description("Stable error code")
    };
}
```

Use the helper:

```java
document("orders-get-not-found",
    responseFields(problemFields())
)
```

This is a helper example; you need to import FieldDescriptor and the corresponding static descriptors. If a scenario has its own extension members, add dedicated descriptors for that scenario. Do not use relaxedResponseFields just to skip describing an undescribed field if that field is part of an important contract.

## 11. Document Identifiers for Error Scenarios

Each error exchange should have its own identifier:

| Scenario | Document identifier |
| --- | --- |
| Missing credentials | orders-get-unauthorized |
| Invalid token | orders-get-invalid-token |
| Insufficient scope | orders-get-forbidden |
| Order not found | orders-get-not-found |
| Validation failed | orders-create-validation-error |

Do not share the identifier orders-get for both success and 404 if they are different exchanges. Snippets with the same name can overwrite each other or make documentation unclear about which scenario is shown.

## 12. Embedding Error Snippets in Asciidoctor

An operation page can group responses into success and error sections:

```asciidoc
[[orders-get]]
=== Get Order Details

==== Success response
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]

==== Authentication required
include::{snippets}/orders-get-unauthorized/http-response.adoc[]
include::{snippets}/orders-get-unauthorized/response-fields.adoc[]

==== Insufficient permission
include::{snippets}/orders-get-forbidden/http-response.adoc[]
include::{snippets}/orders-get-forbidden/response-fields.adoc[]

==== Order not found
include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]
```

Only include snippet files actually generated by tests. If a test does not generate response-fields.adoc, Asciidoctor will fail the include. Check generated-snippets after running tests and keep include names synchronized.

### 12.1. Shared Error Responses Page

If multiple resources share the same error schema, you can create an overview page:

```asciidoc
= Error Responses

[[errors-authentication]]
== Authentication errors

Missing or invalid credentials typically return 401.

[[errors-forbidden]]
== Authorization errors

Authenticated callers with insufficient permissions typically receive 403.

[[errors-not-found]]
== Resource not found

Nonexistent resources or resources hidden by API policy return 404.

[[errors-validation]]
== Validation errors

Requests failing the contract return 400 with field error details.
```

Operations can link to the shared error section via xref/cross-reference. However, it is still good practice to place concrete exchange snippets under the endpoint's operation identifier to ensure documentation reflects tested responses.

## 13. Checking Error Headers and Media Types

Error responses also have a header contract:

| Header | When to Document |
| --- | --- |
| Content-Type | When the API returns application/problem+json or a custom error media type |
| WWW-Authenticate | When the authentication scheme requires a challenge |
| Retry-After | When the error can be retried after a delay |
| X-Request-Id | When consumers need to provide a trace ID to support |
| Cache-Control | When error responses should not be cached or follow a specific cache policy |

Example descriptors:

```java
responseHeaders(
    headerWithName(HttpHeaders.CONTENT_TYPE)
        .description("Media type of the error response"),
    headerWithName(HttpHeaders.WWW_AUTHENTICATE)
        .description("Authentication challenge when returning 401")
)
```

Do not document WWW-Authenticate on every error response if the server does not emit that header. REST Docs strict descriptors help tests detect response changes; only declare headers that actually belong to the scenario.

## 14. Protecting Data and Error Information

Before publishing error snippets:

- Use dummy IDs and payloads.
- Do not record real tokens or cookies in request snippets.
- Do not include stack traces, SQL, filesystem paths, or internal hostnames in detail.
- Do not allow responses to contain real emails/phone numbers of other people.
- Mask request/correlation identifiers if they contain internal identifying info.
- Inspect both http-response.adoc and response-fields.adoc after preprocessing.

A good error example shows consumers how to handle errors without revealing how internal systems are implemented.

## 15. Common Pitfalls

| Symptom | Possible Cause | Solution |
| --- | --- | --- |
| Missing token returns 403 | Misconfigured entry point/security chain or leftover test principal | Run unauthenticated test through the real filter chain |
| Valid token with missing scope returns 401 | Wrong authentication converter/authority mapping | Check scope claim and authority mapping |
| 404 produces no error body | Exception handler does not catch the exception or container returns default error | Standardize exception mapping and test response |
| REST Docs reports missing field | Actual response differs from descriptors | Compare JSON body and update contract/test |
| WWW-Authenticate missing from snippet | Handler does not emit header or preprocessor removed it | Check actual response and security entry point |
| Error code varies across environments | Message/exception mapping depends on locale or config | Use stable codes, separate display messages |
| Error snippet overwrites success snippet | Shared document identifier | Assign distinct identifiers per scenario |
| Error detail exposes stack trace | Returning exception message directly | Use safe Problem Details, log details server-side |
| 404 test fails when running full suite | ID assumed nonexistent was created by another fixture | Isolate/reset database and use deterministic IDs |

## 16. Error Documentation Checklist

- [ ] Clearly distinguish 400, 401, 403, and 404.
- [ ] Error schema and error codes are stable.
- [ ] JSON status matches HTTP status.
- [ ] 401 describes the challenge appropriate to the authentication scheme.
- [ ] 403 shows an authenticated principal lacking permission.
- [ ] 404 follows the resource disclosure/hiding policy.
- [ ] MockMvc tests exist for each important scenario through the security filter chain.
- [ ] Response fields and headers are documented with REST Docs.
- [ ] Each error exchange has its own document identifier.
- [ ] Asciidoctor includes the exact generated snippets.
- [ ] No tokens, PII, stack traces, or internal details appear in artifacts.
- [ ] CI runs tests and renders documentation to catch contract drift.

## 17. Practice Exercise

The Orders API has the endpoint GET /api/orders/{id}, requiring scope ORDER_READ. Create documentation for four scenarios:

1. No token sent: 401 with code AUTHENTICATION_REQUIRED.
2. Valid token without scope: 403 with code ORDER_READ_FORBIDDEN.
3. Sufficient scope, nonexistent order ID: 404 with code ORDER_NOT_FOUND.
4. Order creation request missing customerEmail: 400 with code VALIDATION_FAILED and fieldErrors.

Tasks:

- Write MockMvc tests running through the security filter chain.
- Use appropriate test principal/JWT fixtures for each scenario.
- Assert status, Content-Type, WWW-Authenticate if applicable, and error code.
- Use responseFields(...) to document Problem Details along with extension members.
- Use responseHeaders(...) to document actual headers.
- Assign a distinct document identifier for each exchange.
- Include the snippets into the Error responses section in Asciidoctor.
- Run tests and verify snippets contain no tokens, stack traces, or real data.

**Self-check question:** Why should you not return 401 when a user is already logged in but lacks permission to read an order? Because consumers need to distinguish a request to log in / re-issue credentials from a request for permission grants. 401 indicates authentication has not succeeded; 403 indicates the caller is authenticated but not permitted to perform the action. Resource-hiding policies may use 404, but must be designed and documented consistently.

## Conclusion

Documenting authentication, authorization, and not found errors must accurately reflect the HTTP behavior consumers will encounter. Distinguish 401 for authentication failure, 403 for authorization denial, 404 for nonexistent or hidden resources, and 400 for invalid requests. Standardize error schemas, stable error codes, and appropriate headers; use Spring Security entry points/access denied handlers to produce consistent responses. Write MockMvc tests through the real filter chain, document bodies/headers with Spring REST Docs, and assign distinct document identifiers for each scenario. Finally, include error snippets into Asciidoctor and audit sensitive data so documentation helps consumers handle errors without exposing internal details.
