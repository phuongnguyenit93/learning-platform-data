# Hiding Stack Traces and Internal Data

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we generate verifiable REST API documentation through HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. Snippets are compiled with Asciidoctor/Markdown and integrated into the build and CI pipeline.

API requests and responses may contain access tokens, session cookies, API keys, emails, phone numbers, payment data, or internal information. These values sometimes appear in headers, query strings, or JSON bodies. If REST Docs writes them verbatim into snippets and puts them into CI artifacts or public documentation, sensitive data can be leaked.

This lesson guides you through documenting security errors and sensitive information by sanitizing data before snippet generation. After this lesson, you will be able to:

- Identify sensitive data in requests, responses, headers, and bodies.
- Distinguish data that should be removed from data that should be kept as placeholders.
- Use operation preprocessors to remove headers or replace sensitive values.
- Write tests that verify security behavior without recording real credentials in documentation.
- Inspect snippets and artifacts to detect unintended leaks.
- Integrate sanitized documentation generation into Asciidoctor and CI.

## 2. Risks of Recording Raw Requests/Responses in Documentation

Example authenticated request:

~~~http
GET /api/profile HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.real-access-token
Cookie: SESSION=real-session-secret
X-Api-Key: live-api-key-value
Accept: application/json
~~~

The response may contain a session cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=server-session-secret; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{
  "email": "person@example.com",
  "phone": "+84901234567",
  "displayName": "Nguyen An"
}
~~~

If snippets contain the values above, readers could copy credentials or view personal data outside the scope of documentation. Even if a token is only a test fixture, snippets are easily mistaken for usable credentials and may be unintentionally reused.

Principles:

1. Never use real secrets in test fixtures.
2. Only record headers/body fields needed to explain the contract.
3. Remove or replace sensitive data before snippets are written.
4. Inspect the actual output instead of merely trusting that a preprocessor is configured.
5. Keep test assertions on the original response/request; preprocessing only serves documentation.

Preprocessors do not sanitize logs, traces, databases, test reports, or requests/responses stored elsewhere. Those storage channels must be managed separately.

## 3. Classifying Data to Protect

Before writing preprocessors, list where data can appear:

| Data Category | Common Locations | Documentation Handling |
| --- | --- | --- |
| Access tokens, refresh tokens, API keys | Authorization, X-Api-Key, query, JSON | Remove header or replace value with a placeholder. |
| Session identifiers | Cookie, Set-Cookie | Remove entire cookie header or mask specific values. |
| Passwords, client secrets | JSON request, form body | Never use real values; replace with placeholders in snippets. |
| Email, phone number, address | JSON request/response | Use dummy fixtures; mask or replace if real examples are unnecessary. |
| Payment data | Card number, bank account, payment token | Use provider-approved test data; show only required parts. |
| Personal identifiers | Government ID, date of birth | Remove or use controlled dummy values. |
| Internal hostname/IP | URI, Location, hypermedia links | Normalize host or substitute documentation-environment URI. |
| Stack traces and implementation details | Error body, debug headers | Do not include in public responses; document only error codes and trace references. |

Not all personal data is a secret, yet purpose, access permissions, and documentation retention still matter. Prefer properly shaped dummy data over real data before reaching for masking.

## 4. Choosing Between Removing Headers and Replacing Values

There are two common approaches:

- Remove the entire header when its value is unnecessary to understand the API, such as Authorization, Cookie, or Set-Cookie.
- Replace the value with a placeholder when the header name and presence are part of the contract, such as Authorization: Bearer [REDACTED].

| Need | Approach | Expected Outcome |
| --- | --- | --- |
| No need to display cookies | modifyHeaders().remove("Cookie").remove("Set-Cookie") | Header does not appear in snippets. |
| Need to show endpoint requires Bearer authentication | modifyHeaders().set("Authorization", "Bearer [REDACTED]") | Header still shows scheme, token replaced with placeholder. |
| Need to document API key header without exposing key | Replace X-Api-Key value with [REDACTED] | Header name remains, secret does not appear. |
| Need to preserve error body structure while hiding email | replacePattern(...) with a specific pattern or custom structured preprocessor | Field remains present with replaced value. |

Do not remove a required header from documentation if clients need to know they must send it. In that case, keep the header name and explain the mechanism, while using a placeholder for the credential value.

## 5. Removing or Replacing Request Headers with modifyHeaders()

Spring REST Docs provides modifyHeaders() to add, reset, or remove headers from an operation before generating snippets. Since Spring REST Docs 3.0, this API replaces the deprecated removeHeaders(...) factory method.

Imports:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
~~~

Example removing Authorization, Cookie, and API key:

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("Cookie", "SESSION=test-session")
        .header("X-Api-Key", "test-api-key"))
    .andExpect(status().isOk())
    .andDo(document("profile/get",
        preprocessRequest(
            modifyHeaders()
                .remove("Authorization")
                .remove("Cookie")
                .remove("X-Api-Key")
        )
    ));
~~~

The request is still sent with these headers so the application performs authentication. The preprocessor strips them from the operation copy used to write snippets. As a result, the documentation does not expose credentials.

If you want to document that the API uses Bearer authentication, do not remove Authorization completely. Use a dummy test value and mask the token portion so the snippet still demonstrates the scheme.

## 6. Removing Response Headers with modifyHeaders()

Responses may contain Set-Cookie, debug headers, or internal headers. Use a response preprocessor:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(post("/api/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content(loginRequest))
    .andExpect(status().isOk())
    .andDo(document("auth/login",
        preprocessResponse(
            modifyHeaders()
                .remove("Set-Cookie")
                .remove("X-Internal-Debug")
        )
    ));
~~~

If Set-Cookie is not part of the integration guide, remove it from snippets. If cookies are the authentication mechanism clients need to know about, document the cookie name, attributes like HttpOnly/Secure/SameSite, and usage with a sanitized dummy example; never publish real session IDs.

Headers removed from snippets still exist in the raw response. Tests should assert required cookies/flags on the actual response when they are part of security requirements.

## 7. Masking Header Values with modifyHeaders()

replacePattern(...) only modifies request or response content/body, not headers. To keep the header name and scheme while replacing the credential, use modifyHeaders().set(...):

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

preprocessRequest(
    modifyHeaders().set("Authorization", "Bearer [REDACTED]")
)
~~~

For requests with an API key:

~~~java
preprocessRequest(
    modifyHeaders().set("X-Api-Key", "[REDACTED]")
)
~~~

modifyHeaders().set(...) replaces the entire header value with the specified value. If a header has multiple values, set(...) resets the value list; preserve any parameters required by the contract.

In test fixtures, it is still best to use obvious dummy strings like test-token; preprocessors are an extra safeguard for snippets, not an excuse to put real secrets in tests.

## 8. Masking Data in JSON Bodies

removeHeaders(...) does not process JSON bodies. For bodies, you can use replacePattern(...) to replace values with a stable pattern.

Original response:

~~~json
{
  "id": 42,
  "email": "person@example.com",
  "phone": "+84901234567",
  "status": "ACTIVE"
}
~~~

Example replacing email:

~~~java
preprocessResponse(
    replacePattern(
        Pattern.compile("person@example\\.com"),
        "[REDACTED_EMAIL]"
    )
)
~~~

Snippet after preprocessing:

~~~json
{
  "id": 42,
  "email": "[REDACTED_EMAIL]",
  "phone": "+84901234567",
  "status": "ACTIVE"
}
~~~

If phone also should not be published, add a separate pattern:

~~~java
preprocessResponse(
    replacePattern(
        Pattern.compile("person@example\\.com"),
        "[REDACTED_EMAIL]"
    ),
    replacePattern(
        Pattern.compile("\\+84901234567"),
        "[REDACTED_PHONE]"
    )
)
~~~

replacePattern(...) performs regex string replacement without parsing JSON. Overly broad patterns can accidentally replace the same string in other fields or break JSON. For complex payloads, frequently changing schemas, or many fields requiring masking, consider writing a custom OperationPreprocessor that parses JSON, replaces specific keys, and serializes it back. Either way, inspect the final snippet.

## 9. Combining Request and Response Preprocessors

Both sides can be sanitized independently:

~~~java
mockMvc.perform(post("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("Cookie", "SESSION=test-session")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "email": "person@example.com",
              "displayName": "An"
            }
            """))
    .andExpect(status().isOk())
    .andDo(document("profile/update",
        preprocessRequest(
            modifyHeaders()
                .remove("Cookie")
                .set("Authorization", "Bearer [REDACTED]"),
            replacePattern(
                Pattern.compile("person@example\\.com"),
                "[REDACTED_EMAIL]"
            )
        ),
        preprocessResponse(
            modifyHeaders()
                .remove("Set-Cookie")
                .remove("X-Internal-Debug"),
            replacePattern(
                Pattern.compile("person@example\\.com"),
                "[REDACTED_EMAIL]"
            )
        )
    ));
~~~

The request preprocessor only sanitizes the request snippet copy; the response preprocessor only sanitizes the response snippet copy. If the API echoes input data, both sides must be processed because the same value can appear in both request and response.

## 10. Protecting Error Responses

Error responses are places where internal information can easily leak by accident:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "Database connection failed at db-prod-01.internal:5432",
  "debug": "org.example.OrderRepository.findById(OrderRepository.java:87)",
  "traceId": "req-test-001"
}
~~~

A public API should return safe information:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred.",
  "traceId": "req-test-001"
}
~~~

Prioritize fixing the exception handler so stack traces, internal hostnames, or SQL statements are never placed in the response. Preprocessors can mask a value in snippets, but they do not replace fixing an unsafe response contract.

If traceId is allowed to be published as a reference, keep a stable dummy value in snippets. Do not expose trace tokens or data that could be used to access internal systems.

### 10.1. Never Return Stack Traces in Public Error Responses

Stack traces are helpful to developers diagnosing internal errors, but they are not data for API consumers. They can reveal:

- Package, class, and method names, and source code structure.
- Frameworks, libraries, and versions in use.
- Database names, hostnames, file paths, or internal topology.
- Queries, table names, or implementation details appearing in exception messages.
- Input values or sensitive information embedded in exceptions.

A public response should keep only status, error code, safe message, and correlation ID:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
X-Request-Id: req-test-500

{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred.",
  "traceId": "req-test-500"
}
~~~

Full stack traces are written to access-controlled server-side logs, linked with the same trace/correlation ID. Never send stack traces to clients expecting REST Docs to mask them; production responses must already be safe before reaching documentation.

### 10.2. Testing That Stack Traces Do Not Appear

MockMvc tests can verify the response does not contain debug fields:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isInternalServerError())
    .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
    .andExpect(jsonPath("$.stackTrace").doesNotExist())
    .andExpect(jsonPath("$.debug").doesNotExist())
    .andDo(document("orders/internal-error"));
~~~

If the API has a fixed schema, document the permitted fields and let REST Docs catch any undocumented fields. Additional assertions explicitly express the requirement not to expose stackTrace/debug.

Never document a fake stack trace as if it were part of the error contract. If troubleshooting guidance is needed, explain how to provide the trace ID and contact support.

## 11. Testing Security Behavior Without Recording Real Secrets

Tests should use dummy credentials created specifically for tests:

~~~java
private static final String TEST_TOKEN = "test-token-not-valid-outside-tests";
~~~

Verify the application still enforces authentication:

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer " + TEST_TOKEN))
    .andExpect(status().isOk())
    .andDo(document("profile/get",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer [REDACTED]")
        )
    ));
~~~

This illustrates an authenticated request. In real tests, security configuration may use mock users, test JWT decoders, or test authentication providers. Never use production credentials or copy tokens from live environments into source code, logs, or fixtures.

If the goal is to test that an endpoint rejects requests without a token, create a separate operation documenting the 401 response. Do not use a preprocessor to erase evidence that the endpoint requires authentication.

## 12. Inspecting Snippets After Sanitization

After tests run, inspect both request and response snippets, not just response-fields:

~~~text
build/generated-snippets/profile/update/
├── http-request.adoc
├── http-response.adoc
├── request-fields.adoc
└── response-fields.adoc
~~~

Verification checklist:

1. No real access tokens, refresh tokens, API keys, or session IDs remain.
2. Authorization still shows the scheme if documentation needs to describe Bearer authentication.
3. Cookie/Set-Cookie headers have been intentionally removed or replaced.
4. Emails, phones, addresses, and payment data in bodies use dummy fixtures or placeholders.
5. No internal hostnames, IPs, stack traces, SQL, or debug headers remain.
6. JSON remains valid and essential fields are preserved.
7. Required statuses, error codes, and security headers remain documented.

Search for known sensitive strings across the generated-snippets directory and packaged artifacts. A correct preprocessor on one operation does not guarantee other operations have been sanitized.

## 13. Organizing Shared Sanitization Policies

If multiple tests share the same rules, create a helper so each operation does not handle sanitization differently:

~~~java
static OperationRequestPreprocessor sanitizeRequest() {
    return preprocessRequest(
        modifyHeaders()
            .remove("Cookie")
            .remove("X-Internal-Debug")
            .set("Authorization", "Bearer [REDACTED]")
    );
}
~~~

This helper only illustrates the organizational idea; the exact return type and preprocessor composition must match the actual API of your project's Spring REST Docs version. You can create separate helpers for requests and responses and invoke them in each documented operation.

A shared policy should maintain a clear list of:

- Headers always removed.
- Headers kept by name with masked values.
- JSON fields replaced with placeholders.
- Internal hostnames requiring normalization.
- Fields preserved intact because they are essential to examples.

Do not apply global masking blindly. Certain headers like Content-Type, WWW-Authenticate, or Retry-After are contractually meaningful and must be preserved.

## 14. Asciidoctor and CI Integration

Asciidoctor includes sanitized snippets:

~~~asciidoc
== Update Profile

=== HTTP request
include::{snippets}/profile/update/http-request.adoc[]

=== HTTP response
include::{snippets}/profile/update/http-response.adoc[]
~~~

Assuming the Asciidoctor plugin is configured:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Run:

~~~bash
./gradlew clean test asciidoctor
~~~

CI should perform an additional artifact verification step:

- Scan for disallowed fixture tokens, API key patterns, and session cookies.
- Check for internal hostnames and debug information.
- Review snippet diffs when tests or error schemas change.
- Publish documentation only after both tests and output checks pass.

With plain Markdown, Asciidoctor's include:: syntax is not processed automatically; a separate build step is needed to embed snippets or link to generated files.

## 15. Common Pitfalls and Troubleshooting

| Symptom | Cause and Solution |
| --- | --- |
| Authorization still appears in snippets | Request preprocessor was not attached to the right document operation or pattern did not match actual header. |
| Set-Cookie remains in response | Only request was processed; add a response preprocessor or remove the header from responses. |
| JSON body still has real email | modifyHeaders does not process bodies; use dummy fixtures or replacePattern/custom JSON preprocessor. |
| Regex accidentally replaces multiple fields | Pattern is too broad; restrict by value/key and inspect snippets afterward. |
| JSON becomes unparseable after masking | Replacement altered structural characters; use valid placeholders and validate payload. |
| Removed a header needed by clients | Distinguish secret values from header semantics; keep the header and replace values when necessary. |
| Test token mistaken for real credential | Name fixtures clearly, use values invalid outside tests, and note this in documentation. |
| Snippets are clean but artifacts still have secrets | Check test reports, logs, archives, and other outputs; preprocessors only sanitize operation snippets. |
| One operation missed masking | Use shared helpers/policies and audit all documented operations. |

## 16. Practice Exercise

1. Create an endpoint requiring Bearer authentication and write a test with a dummy token.
2. Use modifyHeaders().remove("Cookie") to strip Cookie from the request snippet.
3. Use modifyHeaders().set("Authorization", "Bearer [REDACTED]") to keep the scheme while replacing the token.
4. Create a response with Set-Cookie and verify how to strip the header from the response snippet.
5. Create a JSON response containing a dummy email; replace the value with a placeholder in the snippet.
6. Create an error response with a debug field and fix the exception handler so internal details are not returned.
7. Create shared sanitization helpers for requests and responses.
8. Run Gradle/CI and search generated-snippets and artifacts for sensitive fixture strings.

## 17. Key Takeaways

- Never put real credentials or real personal data into test fixtures and documentation.
- modifyHeaders() adds, replaces, or removes headers from the documented operation copy; apply separately for requests or responses.
- replacePattern() replaces regex-matched content/body; keep patterns narrow to avoid corrupting payloads.
- Keep contractually meaningful headers and mask secret values when clients need to know the header exists.
- Sanitize both requests and responses because APIs may echo input data.
- Preprocessors only affect snippets; they do not sanitize logs, traces, test reports, or external storage.
- Inspect generated snippets and artifacts before publishing documentation.

## 18. References

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): operation preprocessors and transforming requests/responses before documenting.
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): factory methods such as modifyHeaders and replacePattern.
- [Spring REST Docs — HeadersModifyingOperationPreprocessor](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/HeadersModifyingOperationPreprocessor.html): set, add, remove, and removeMatching operations for headers.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): principles for managing secrets in applications and development workflows.
