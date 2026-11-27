# Sensitive Headers or Cookies Exposed in Spring REST Docs

## 1. Why Does Sensitive Data Appear in Documentation?

Spring REST Docs creates snippets from requests and responses recorded by the test client. A request may contain:

```http
GET /api/profile HTTP/1.1
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=abc123; refresh_token=secret-value
X-Api-Key: live-key-value
Accept: application/json
```

If a test records all request headers without filtering, authentication values can appear in `http-request.adoc`, `curl-request.adoc`, or other snippets. Responses can also contain `Set-Cookie`, new tokens, session identifiers, or internal headers. When documentation is committed, uploaded to an artifact server, or published publicly, sensitive data can be shared beyond its intended scope.

The **SPRING_REST_DOCS** module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests generate snippets for requests, responses, payloads, parameters, and headers, which are then assembled into Asciidoctor/Markdown in build/CI. This lesson belongs to the **Troubleshooting** chapter and focuses on detecting and removing sensitive headers/cookies before snippets are published.

After this lesson, you will be able to:

1. Identify headers, cookies, and payloads that may contain secrets.
2. Use operation preprocessors to remove or replace sensitive values.
3. Distinguish synthetic test data from real credentials.
4. Inspect both request and response snippets.
5. Add secret-leak checks in CI before publishing documentation.

## 2. What Data Should Be Considered Sensitive?

| Header/cookie | Risk |
| --- | --- |
| Authorization | Bearer token, Basic credentials, access token |
| Proxy-Authorization | Authentication credentials for a proxy |
| Cookie | Session ID, refresh token, CSRF token |
| Set-Cookie | New session, token, security-scoped cookie |
| X-Api-Key, Api-Key | Client or service API key |
| X-Auth-Token | Application-specific authentication token |
| X-Amz-Security-Token | Temporary cloud credential |
| Forwarded, X-Forwarded-* | May reveal internal addresses and topology |
| Location | May contain tokens in URLs if the application has an insecure design |

Bodies can also contain passwords, emails, phone numbers, access tokens, private keys, or personal data. Redacting headers does not automatically protect payloads.

### 2.1. Cookies Must Be Checked in Both Directions

Requests use the `Cookie` header:

```http
Cookie: SESSION=abc123; theme=dark
```

Responses use `Set-Cookie`:

```http
Set-Cookie: SESSION=xyz789; Path=/; HttpOnly; Secure; SameSite=Lax
```

If you only redact the request `Cookie`, the response `Set-Cookie` can still expose the session identifier. Check both directions.

## 3. Preprocessing in Spring REST Docs

Spring REST Docs lets you transform an operation before generating snippets:

- `preprocessRequest(...)` for requests.
- `preprocessResponse(...)` for responses.
- `removeHeaders(...)` to strip headers.
- `replacePattern(...)` to replace content matching a pattern.
- `modifyHeaders()` to modify header values.

Preprocessors only alter the data used to generate snippets. They do not change the request sent to the server or the response returned by the application. Redacting in documentation does not replace protecting credentials in test runtime, logs, CI environments, or source control.

## 4. Removing Sensitive Headers with `removeHeaders()`

MockMvc example:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("X-Api-Key", "test-api-key")
        .header("Cookie", "SESSION=test-session"))
    .andDo(document("profile",
        preprocessRequest(
            removeHeaders("Authorization", "X-Api-Key", "Cookie")
        )
    ));
```

These headers are stripped from the request snippets. The server still receives the request as sent by the test; only the representation saved in documentation omits those headers.

### 4.1. Removing Headers on Responses

Example of a response containing `Set-Cookie`:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(post("/api/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"username":"demo","password":"test-password"}
                """))
    .andDo(document("login",
        preprocessResponse(
            removeHeaders("Set-Cookie", "Authorization", "X-Internal-Token")
        )
    ));
```

If the documentation needs to describe the cookie without exposing its actual value, replace the value rather than deleting the entire header. Removing `Set-Cookie` also removes `HttpOnly`, `Secure`, `SameSite`, `Path`, and `Max-Age`; retain non-sensitive attributes if they belong to the contract being documented.

## 5. Replacing Values with Placeholders

In many docs, readers need to know that a header is present and its general format, without seeing real credentials:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer abc.def.ghi"))
    .andDo(document("profile",
        preprocessRequest(
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .set("X-Api-Key", "<api-key>")
        )
    ));
```

The placeholder should indicate the format clients must send. For example, `Authorization: Bearer <access-token>` shows the Bearer scheme without exposing a token.

`modifyHeaders().set(...)` sets a new header value. If the original header was absent, the preprocessor may add that header to the snippet. Use it only for headers that truly belong to the request contract; do not inject illustrative headers that the real request does not send.

## 6. Partially Redacting Values with Patterns

You can preserve the header structure while replacing the token:

```java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer abc.def.ghi"))
    .andDo(document("profile",
        preprocessRequest(
            replacePattern(
                Pattern.compile("(?i)(Bearer\\s+)[A-Za-z0-9._~-]+"),
                "$1<redacted>"
            )
        )
    ));
```

Expected output:

```http
Authorization: Bearer <redacted>
```

This pattern only illustrates Bearer-style tokens. Real tokens may contain other characters or structures; do not treat a single regex as a comprehensive secret detector. For public docs, removing the header entirely or using a fixed placeholder is usually easier to control.

Do not replace overly broad strings. A generic pattern can corrupt business IDs, URLs, non-sensitive JSON fields, or checksums. Write patterns targeting specific headers/fields and test the output after preprocessing.

## 7. Creating Shared Preprocessors

If multiple operations need to strip the same group of headers, encapsulate the configuration:

```java
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

final class DocumentationRedaction {
    private DocumentationRedaction() {}

    static OperationRequestPreprocessor safeRequest() {
        return preprocessRequest(removeHeaders(
                "Authorization", "Proxy-Authorization", "Cookie",
                "X-Api-Key", "X-Auth-Token"));
    }

    static OperationResponsePreprocessor safeResponse() {
        return preprocessResponse(removeHeaders(
                "Set-Cookie", "Authorization", "X-Internal-Token"));
    }
}
```

Usage in a test:

```java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("Cookie", "SESSION=test-session"))
    .andDo(document("profile",
        DocumentationRedaction.safeRequest(),
        DocumentationRedaction.safeResponse()
    ));
```

The list of headers to redact must be based on your project's contract and security policy. Add custom headers such as `X-Company-Secret` or `X-Service-Credential` if your system uses them. Do not assume every system only uses common header names.

## 8. Cookies: Redacting Values While Preserving Security Attributes

If you need to document cookie attributes, deleting the entire `Set-Cookie` header loses important details. One option is replacing the value with a placeholder while keeping attributes:

```text
Set-Cookie: SESSION=<redacted>; Path=/; HttpOnly; Secure; SameSite=Lax
```

You can use a preprocessor that replaces specific header content or build an operation preprocessor that parses cookie headers. When handling cookies:

- Keep the cookie name if that name is part of the contract.
- Replace the value with a placeholder.
- Keep `HttpOnly`, `Secure`, `SameSite`, `Path`, `Domain`, and `Max-Age` if needed for documentation.
- Check multiple `Set-Cookie` headers; do not merge them into one value if that changes semantics.

Do not rely on a naive regex to split every cookie when values have complex delimiters or encodings. Use a proper parser or dedicated preprocessor and test cases with multiple cookies.

## 9. Payloads and Query Parameters Can Also Contain Secrets

Redacting headers does not protect the body. For example:

```json
{
  "username": "demo",
  "password": "real-password",
  "accessToken": "eyJhbGciOi...",
  "email": "person@example.com"
}
```

Documentation should not use real production data. Use synthetic fixtures not tied to real individuals:

```json
{
  "username": "demo-user",
  "password": "<password>",
  "accessToken": "<access-token>",
  "email": "user@example.test"
}
```

If a test needs a secret to verify behavior, pull it from the CI secret store or generate a short-lived dummy token during test setup. Do not write secrets into fixtures, logs, or snippets. When payloads contain sensitive fields, use fake data or a body preprocessor/descriptors to replace values before saving documentation.

Query strings can also expose tokens:

```text
GET /download?access_token=secret-value
```

Prefer sending credentials via appropriate headers instead of URLs when API design permits. URLs can be recorded in access logs, browser history, and snippets.

## 10. REST Assured and WebTestClient

The test clients differ, yet the preprocessing principles are the same.

### 10.1. REST Assured

```java
given()
        .header("Authorization", "Bearer test-token")
        .cookie("SESSION", "test-session")
        .filter(document("profile",
                preprocessRequest(
                        removeHeaders("Authorization", "Cookie")
                )))
        .when()
        .get("/api/profile")
        .then()
        .statusCode(200);
```

If the response includes `Set-Cookie`, add `preprocessResponse(...)` to the document filter. Make sure you use the operation preprocessors from the Spring REST Docs REST Assured integration.

### 10.2. WebTestClient

```java
webTestClient.get()
        .uri("/api/profile")
        .headers(headers -> headers.setBearerAuth("test-token"))
        .cookie("SESSION", "test-session")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("profile",
                preprocessRequest(
                        removeHeaders("Authorization", "Cookie")
                )));
```

For responses, apply a response preprocessor in the same document operation if `Set-Cookie` or other sensitive headers need redaction.

## 11. Do Not Document Test Secrets Like Real Credentials

Test data should remain safe even if read in logs or build artifacts:

1. Never use production access tokens in documentation tests.
2. Never commit secrets into source code, fixtures, `.env`, or test reports.
3. Use test credentials with minimal scope and short lifetimes if calling real services is necessary.
4. Redact before snippets are written to disk.
5. Do not enable debug logging that records request headers or bodies containing secrets.
6. If you suspect a real credential leaked into an artifact, revoke/rotate the credential and handle the artifact per your organization's incident process.

Redaction in Spring REST Docs does not remove secrets from HTTP client logs, test failure output, proxy logs, or CI traces. Control those storage locations separately.

## 12. Inspecting Snippets After Redaction

After running tests, open the files:

```text
build/generated-snippets/profile/http-request.adoc
build/generated-snippets/profile/curl-request.adoc
build/generated-snippets/login/http-response.adoc
```

Verify that `Authorization` no longer contains runtime tokens, `Cookie` has no session/refresh tokens, `Set-Cookie` does not leak values, API keys/custom auth headers are handled, `curl-request` does not re-expose secrets, and payloads/query strings contain no real passwords or tokens.

Do not inspect only `http-request.adoc`. The cURL snippet can carry the same sensitive headers; response snippets can leak new cookies; payload snippets can contain tokens inside the body.

## 13. Adding Leak Checks to CI

After tests generate snippets, run a step to check for secret patterns:

```bash
grep -RniE \
  'Bearer [A-Za-z0-9._~-]{12,}|SESSION=[^;[:space:]]+|refresh_token=[^;[:space:]]+|X-Api-Key: [^<[:space:]]+' \
  build/generated-snippets
```

This is only a heuristic check, not a replacement for a secret scanner. You can integrate your organization's secret-scanning tool on both output snippets and rendered documentation.

CI should run tests, perform leak scanning across all `generated-snippets`, scan rendered documentation, fail the build if an unredacted credential is found, and store diagnostic logs without re-printing the secret value.

Do not echo tokens in CI error messages. Report only the filename, pattern type, and match location.

## 14. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Token appears in `http-request` | Request not preprocessed or wrong `document` overload used | Attach `preprocessRequest(...)` to the operation |
| cURL still has `Authorization` | Checked only the `http-request` snippet | Check `curl-request` and the entire output root |
| Request `Cookie` hidden but `Set-Cookie` exposed | Redacted only the request | Use `preprocessResponse(...)` |
| Cookie attributes lost | Removed the entire `Set-Cookie` header | Replace the value and keep attributes that need documenting |
| Token still present in JSON | Only headers were redacted | Use synthetic fixtures or body redaction |
| Custom API key not caught | Incomplete header list | Add header names per contract |
| Secret appears in logs despite clean snippets | Redaction only affects the REST Docs operation | Control HTTP client/debug/CI logging separately |
| Regex corrupts valid payloads | Pattern is too broad | Scope the pattern to specific headers/fields and test output |

## 15. Hands-On Exercise

A profile endpoint requires a Bearer token and a session cookie. The login response returns:

```http
HTTP/1.1 200 OK
Set-Cookie: SESSION=temporary-session; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"accessToken":"temporary-access-token","expiresIn":900}
```

Perform the following:

1. Write tests using dummy tokens/cookies, never real credentials.
2. Document both request and response with Spring REST Docs.
3. Redact `Authorization`, `Cookie`, and `Set-Cookie`.
4. If cookie policy needs to be documented, replace the value with `<redacted>` while keeping attributes.
5. Handle the token in the JSON response body using dummy data or a body preprocessor.
6. Inspect `http-request`, `curl-request`, `http-response`, and response body snippets.
7. Add a CI leak check to fail if test tokens or cookie values appear.

**Completion criteria:** Snippets retain the necessary contract without containing credential or session values; response cookie attributes remain documented when needed; no secrets appear in cURL, payloads, logs, or artifacts.

## 16. Key Takeaways

Spring REST Docs records requests and responses, so headers and cookies can be saved verbatim into snippets if left unhandled. Use `preprocessRequest(removeHeaders(...))` for `Authorization`, `Cookie`, and API keys; use `preprocessResponse(...)` for `Set-Cookie` and response headers. When you need to preserve the contract, replace the value with a placeholder instead of deleting the whole header. Inspect HTTP request, cURL, response, and payload snippets; use synthetic test data, control logs separately, and add leak scanning in CI before publishing documentation.

### References

- [Spring REST Docs — Preprocessing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses/preprocessors.html)
- [Spring REST Docs — Operation Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
