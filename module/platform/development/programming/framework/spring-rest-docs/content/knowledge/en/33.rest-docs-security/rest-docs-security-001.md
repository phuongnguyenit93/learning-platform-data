# Masking Authorization, Session Cookies, and Tokens

## 1. Objectives and Context

HTTP requests and responses frequently contain authentication data or session identifiers: the Authorization header, JSESSIONID cookie, access token, refresh token, session ID, CSRF token, and API key. Spring REST Docs captures operations from HTTP tests and generates snippets for requests, responses, headers, bodies, curl, or HTTPie. If these values are written into snippets and then committed, attached as CI artifacts, or published, sensitive information can be exposed.

This lesson belongs to the **Security** chapter of the **SPRING_REST_DOCS** module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; compiles Asciidoctor/Markdown; and integrates with build/CI pipelines.

After this lesson, you will be able to identify authentication data; use operation preprocessors to remove or replace sensitive data; mask Authorization, Cookie, Set-Cookie, CSRF headers, and tokens in the body; inspect all snippet types; and configure CI to detect leaked secrets.

> Mask data before writing snippets. Do not rely on manually deleting files after the build because the request/response may have already appeared in logs, reports, or other artifacts.

## 2. Data That Needs Protection

| Location | Common Names | Risk |
| --- | --- | --- |
| Request header | Authorization | Bearer token, Basic credentials, or a custom scheme. |
| Request header | Cookie | Session identifier and authentication cookies. |
| Response header | Set-Cookie | Session ID/token issued by the server. |
| Request/response header | X-CSRF-TOKEN, X-XSRF-TOKEN | Anti-CSRF token. |
| JSON request body | password, clientSecret, refreshToken | Submitted credentials/tokens. |
| JSON response body | access_token, refresh_token, id_token | Tokens returned by the server. |
| URL query/path | code, ticket, signed value | Can appear in the request line and curl command. |
| Log/metadata | Fixture, exception text | May inadvertently contain secrets. |

Data classification:
- **Secrets to remove/replace:** password, private key, client secret, access/refresh token, session ID, API key.
- **Identifiers to consider hiding:** email, phone number, internal user ID, customer reference.
- **Information that can be public:** field names, Bearer scheme, cookie names, placeholders, and synthetic data created specifically for tests.

Test data is not automatically safe to publish. Use synthetic data that is not tied to real accounts or individuals.

## 3. Redaction Using Operation Preprocessors

Spring REST Docs allows applying operation preprocessors before snippets are written. Two commonly used operations are `Preprocessors.removeHeaders(...)` to remove headers and `Preprocessors.replacePattern(...)` to replace content by pattern. They can be applied separately to requests or responses using `preprocessRequest(...)` and `preprocessResponse(...)`.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("sessions-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie", "X-CSRF-TOKEN")
    ),
    preprocessResponse(
        removeHeaders("Set-Cookie", "Authorization")
    )
));
~~~

This is an illustrative example of attaching a preprocessor to an operation; static imports must match the project's Spring REST Docs version. Removed headers will not appear in snippets generated from the preprocessed operation.

### 3.1. Preprocessing Before Writing Snippets

An operation can generate multiple snippets from the same request/response: HTTP request, HTTP response, curl, HTTPie, request body, and response body. A preprocessor at the operation layer processes the operation before the snippets are rendered.

If you only delete Authorization from the http-request file after the build, the value may still remain in curl-request, httpie-request, or logs. Therefore, redaction must be performed at the preprocessing step.

### 3.2. Selecting Headers to Remove

| Header | Handling Approach |
| --- | --- |
| Authorization | Remove or replace with a non-functional placeholder. |
| Cookie | Remove if it contains session/authentication cookies. |
| Set-Cookie | Remove because it may contain a new session/token. |
| X-CSRF-TOKEN | Remove or replace with a placeholder. |
| X-XSRF-TOKEN | Remove or replace with a placeholder. |
| Proxy-Authorization | Remove proxy credentials. |
| X-Api-Key | Remove the API key. |

Do not remove headers indiscriminately. Content-Type, Accept, Location, Cache-Control, or request ID may be part of the API contract. Define your system's list of secret headers and apply it consistently.

## 4. Masking Authorization and Session Cookies

An authenticated request may contain:

~~~http
GET /api/orders/101 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...secret...
Accept: application/json
Cookie: JSESSIONID=abc123secret
~~~

**Approach 1 — remove headers from the snippet:**

~~~java
.andDo(document("orders-get",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie")
    )
));
~~~

The HTTP request snippet still shows the method, path, and non-sensitive headers. The operation explanation describes that the endpoint requires Bearer authentication.

**Approach 2 — tests use synthetic values:** the request can send a value with no real access privileges, such as `Bearer DOCS_ONLY_TOKEN`. For public documentation, you should still preprocess or replace it with a placeholder so readers do not mistake it for a valid credential.

Do not use developer tokens, CI tokens with real permissions, or cookies copied from a logged-in browser session in test fixtures.

### 4.1. Cookie and Set-Cookie

A session cookie may be issued in the response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=server-session-secret; Path=/; HttpOnly; Secure
Content-Type: application/json
~~~

Remove Set-Cookie in the response preprocessor:

~~~java
.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie")
    )
));
~~~

If the documentation needs to explain cookie attributes, describe them separately or test the attributes without recording the session identifier. You can present Path, HttpOnly, Secure, and SameSite without exposing the cookie value.

### 4.2. CSRF and Custom Auth Headers

A system may use custom headers such as X-CSRF-TOKEN, X-Api-Key, or Proxy-Authorization. Include sensitive header names in the removal list. If the header name is part of the contract, describe it separately and use a non-functional placeholder for the sample value.

## 5. Masking Tokens in Request/Response Bodies

Removing headers is not enough if the body contains tokens. For example, a login response:

~~~json
{
  "token_type": "Bearer",
  "access_token": "actual-access-token",
  "refresh_token": "actual-refresh-token",
  "expires_in": 900
}
~~~

You can use `replacePattern(Pattern, String)` on a request/response preprocessor to replace values before the snippet is written.

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

private static final Pattern ACCESS_TOKEN =
    Pattern.compile("(\"access_token\"\\s*:\\s*\")[^\"]*(\")");

private static final Pattern REFRESH_TOKEN =
    Pattern.compile("(\"refresh_token\"\\s*:\\s*\")[^\"]*(\")");

.andDo(document("login-success",
    preprocessResponse(
        replacePattern(ACCESS_TOKEN, "$1[REDACTED]$2"),
        replacePattern(REFRESH_TOKEN, "$1[REDACTED]$2")
    )
));
~~~

The example uses regex for specific JSON string fields. You must check the actual output of the REST Docs version in use and ensure the pattern matches serialization. For complex escaping or nested structures, a simple regex may not be sufficient.

Do not replace every generically named field such as token if the application also has business fields that are not secrets.

### 5.1. Keeping the Schema Understandable After Redaction

The redacted snippet can preserve the structure:

~~~json
{
  "token_type": "Bearer",
  "access_token": "[REDACTED]",
  "refresh_token": "[REDACTED]",
  "expires_in": 900
}
~~~

If the token does not need to be published, you can omit the field or write a custom body preprocessor. Documentation must accurately reflect the contract: placeholders preserve the schema without disclosing the value.

## 6. URLs and Query Parameters

Tokens are sometimes placed in the URL:

~~~http
GET /api/callback?code=authorization-code-secret&state=opaque-state HTTP/1.1
~~~

The URL appears in the request line, curl, and HTTPie snippets. RemoveHeaders cannot mask the query string. Avoid passing access tokens or session secrets via the URL. For temporary authorization codes, use a synthetic code dedicated to documentation tests or preprocess the request content appropriately.

URLs can be stored in access logs, proxy logs, browser history, analytics, and monitoring. REST Docs redaction only protects snippets generated from preprocessed operations; it does not automatically mask application logs, test failure reports, HTTP client wire logs, CI debug output, caches, or other artifacts.

## 7. Shared Helpers for Security Preprocessing

If multiple tests require the same policy, create a helper:

~~~java
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

private static OperationRequestPreprocessor sanitizeRequest() {
    return preprocessRequest(
        removeHeaders(
            "Authorization",
            "Cookie",
            "X-CSRF-TOKEN",
            "X-XSRF-TOKEN",
            "X-Api-Key",
            "Proxy-Authorization"
        )
    );
}

private static OperationResponsePreprocessor sanitizeResponse() {
    return preprocessResponse(
        removeHeaders("Set-Cookie", "Authorization")
    );
}
~~~

Use in an operation:

~~~java
.andDo(document("orders-create",
    sanitizeRequest(),
    sanitizeResponse(),
    requestFields(...),
    responseFields(...)
));
~~~

Imports and helper signatures must match the project's REST Docs API. You can add body redaction for login/token operations instead of applying unnecessary patterns to every endpoint.

Do not over-redact: Content-Type, Accept, Location, or headers describing the contract should still be kept if they do not contain secrets. Review the list against the actual system.

## 8. Using Synthetic Credentials in Tests

Test credentials should be designed so that even if they leak into a snippet, they do not grant real access:

- Use dummy tokens that are meaningful only inside tests.
- Use a mock authentication principal instead of a developer token.
- Do not read production/CI secrets and embed them into test requests.
- Do not commit .env files, keystores, or credentials.
- Do not use cookies from a browser session.
- If a test signs JWTs, use a separate test signing key.
- Restrict wire/debug logging that could print requests.

A fake JWT signed with a real private key is still dangerous. Separate the test signing key and restrict the fixture's issuer, audience, and permissions.

## 9. Verifying That Snippets Contain No Secrets

Use a sentinel that only appears in test fixtures:

~~~java
private static final String TEST_SECRET =
    "DOCS_ONLY_SECRET_7f91c2";
~~~

After REST Docs generates the snippets, verify that none of the output contains the sentinel. Illustrative assertion:

~~~java
assertThat(allGeneratedSnippetText)
    .doesNotContain(TEST_SECRET)
    .doesNotContain("JSESSIONID=session-secret");
~~~

Check for the exact secret sentinel rather than banning the word Authorization, because the docs may need to mention header names or authentication schemes. You can verify that the `[REDACTED]` placeholder remains if that is the expected content.

### 9.1. Inspecting Every Snippet Type

Search across all generated output, not just the HTTP request:

- http-request and http-response.
- curl-request and httpie-request.
- request-body and response-body.
- request-fields and response-fields.
- Header/parameter/custom snippets.
- Assembled Markdown/Asciidoctor pages.

A token may have been masked in the request snippet yet remain in the curl or body snippet if the preprocessor was not applied to the right operation or content.

## 10. Applying to Each HTTP Test Client

### 10.1. MockMvc

~~~java
mockMvc.perform(get("/api/orders/101")
        .header("Authorization", "Bearer DOCS_ONLY_SECRET")
        .cookie(new Cookie("JSESSIONID", "DOCS_SESSION_SECRET")))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        preprocessRequest(
            removeHeaders("Authorization", "Cookie")
        ),
        preprocessResponse(
            removeHeaders("Set-Cookie")
        )
    ));
~~~

The example uses synthetic values. If the controller requires authentication, configure the test security context using the appropriate Spring Security test mechanism; do not fetch a real token just to pass the security filter.

### 10.2. WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders/101")
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-get-webflux",
        preprocessRequest(
            removeHeaders("Authorization")
        ),
        preprocessResponse(
            removeHeaders("Set-Cookie")
        )
    ));
~~~

Use the WebTestClient REST Docs filter matching your Spring REST Docs version. Redaction must be attached to the operation before the snippet is written.

### 10.3. REST Assured

~~~java
given(specification)
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .filter(document("orders-get-restassured",
        preprocessRequest(
            removeHeaders("Authorization")
        ),
        preprocessResponse(
            removeHeaders("Set-Cookie")
        )
    ))
.when()
    .get("/api/orders/101")
.then()
    .statusCode(200);
~~~

The specification must configure the server/base URI, port, and REST Docs context. The filter must be used on every authenticated operation; redaction can be placed in a shared helper or filter.

## 11. Writing the Authentication Section Without Exposing Credentials

Documentation still needs to explain the scheme. Use clear placeholders in the guide section, and do not include raw headers from tests:

~~~markdown
## Authentication

This endpoint requires a Bearer token in the Authorization header.

Example header value: Bearer <access-token>
~~~

If you want to display request headers in the documentation, write a separate placeholder example after redaction. Do not include any value that previously held a real credential.

## 12. CI: Detecting Secrets in Documentation Output

~~~mermaid
flowchart TD
    A["HTTP tests with synthetic credentials"] --> B["Apply preprocessors"]
    B --> C["Generate snippets"]
    C --> D["Assemble Markdown/Asciidoctor"]
    D --> E["Scan snippets and final docs"]
    E --> F{"Sensitive value found?"}
    F -->|Yes| X["Fail build"]
    F -->|No| G["Render documentation"]
    G --> H{"Render and links pass?"}
    H -->|No| X
    H -->|Yes| I["Publish docs"]
~~~

CI needs to:
1. Use synthetic data and clear sentinels.
2. Generate all REST Docs snippets.
3. Assemble the final pages.
4. Scan the generated directory and final docs.
5. Run a secret scanner according to organizational policy.
6. Fail the build if any sentinel or suspicious secret is found.
7. Never print the raw secret in logs when reporting an error.
8. Publish only when tests, scans, and rendering all pass.

Scanners can produce false positives, such as synthetic tokens in guides. Use a narrow, clearly scoped, and reviewed allowlist; never allowlist real credentials.

### 12.1. Multi-Layer Scanning

Scan generated snippets, assembled Markdown/Asciidoc, rendered HTML if it contains code examples, and attached CI artifacts. If a real secret is detected, rotate/revoke it according to policy. Deleting files in the working tree does not remove Git history, CI caches, or already-published artifacts.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Authorization remains in curl | Preprocessor not attached to the operation | Check document(...) and all snippets. |
| Cookie exposed in response | Only removed request Cookie, forgot Set-Cookie | Preprocess both request and response. |
| Token remains in body | Only removed headers | Use appropriate body replacement. |
| Query token still present | Secret is in the request line | Do not use secret URLs; use synthetic codes and process the content. |
| Regex masks JSON incorrectly | Pattern does not match serialization | Test with the actual payload and verify output. |
| Docs do not explain auth | Removed header without documenting the scheme | Add a description and placeholder. |
| CI fixture uses real secret | Used credentials from the environment | Create synthetic identities and tokens. |
| Leak discovered only after publish | Did not scan generated/final docs | Add a scan before the publish gate. |
| Scanner false positive | Pattern is too broad | Use sentinels and a narrow allowlist. |
| Secret remains in Git history | File was previously committed or stored in an artifact | Rotate credentials and clean up history/artifacts. |

## 14. Practice Exercise

Create two hypothetical endpoints:

- POST /api/auth/login returning an access token and refresh token.
- GET /api/orders/101 requiring Bearer authentication; the application may return Set-Cookie if managing sessions.

Steps to perform:

1. Write HTTP tests with dedicated synthetic credentials.
2. Remove Authorization, Cookie, Set-Cookie, and CSRF headers using preprocessors.
3. Mask access_token, refresh_token, and password in body snippets.
4. If a token appears in a query parameter or request line, use synthetic data and handle it separately.
5. Generate HTTP, curl, HTTPie, request/response body, and descriptor snippets.
6. Verify that no snippet still contains the sentinel.
7. Write the Authentication section using placeholders and scheme descriptions.
8. Assemble the final documentation and scan it again.
9. Configure CI to fail before publishing if a sentinel or secret is detected.
10. Intentionally omit one preprocessor in a test run to confirm the leak check catches the sentinel.

**Completion criteria:** the documentation accurately explains how to authenticate without exposing credentials; headers and bodies are sanitized; all snippets and final pages are scanned; tests use synthetic credentials; CI blocks publishing if a secret is detected.

## References

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Spring REST Docs — Operation Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
