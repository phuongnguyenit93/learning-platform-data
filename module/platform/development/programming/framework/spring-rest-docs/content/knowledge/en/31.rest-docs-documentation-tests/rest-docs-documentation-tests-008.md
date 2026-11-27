# Security Tests to Keep Tokens Out of Snippets

## 1. Why Should Snippets Be Checked for Security?

Spring REST Docs records requests and responses from HTTP tests to generate API documentation. This is very useful because snippets reflect data that actually passed through the tested operation. However, requests/responses can contain information that must never be published: access tokens, refresh tokens, session cookies, API keys, real emails, phone numbers, personal data, or sensitive JSON fields.

If a test uses real credentials or a preprocessor fails to mask data before writing snippets, these values can appear in `http-request.adoc`, `request-headers.adoc`, `request-body.adoc`, custom snippets, or CI artifacts. Generated documentation is often committed, published, or stored as artifacts; a secret that leaks into it can persist long after the credential is revoked.

In **SPRING_REST_DOCS**, HTTP tests using MockMvc, WebTestClient, or REST Assured serve as the source of snippets for requests, responses, payloads, parameters, and headers. This lesson belongs to the **Documentation Tests** chapter and focuses on ensuring sensitive data is stripped or replaced before writing snippets, as well as inspecting outputs to catch leaks.

After this lesson, you will be able to:

- Identify where tokens and sensitive data can leak into snippets.
- Use request/response preprocessors to strip or replace headers.
- Mask sensitive fields in request and response bodies.
- Protect custom snippets using an allowlist approach.
- Verify that generated snippets and CI artifacts contain no secrets.
- Distinguish dummy test data from real runtime credentials.
- Respond to incidents if a secret has already been committed or published.

## 2. Where Secrets Can Leak

Sensitive information does not only live in `Authorization`. Check every piece of data that a test or custom snippet might emit.

| Location | Examples | Risk |
| --- | --- | --- |
| Request headers | `Authorization: Bearer ...`, `X-API-Key` | Exposes API credentials |
| Cookies | `JSESSIONID`, session cookie | Exposes login session |
| Request body | `password`, `refreshToken`, `clientSecret` | Exposes authentication credentials |
| Query parameters | `?access_token=...` | Secret embedded in URI |
| Response body | access token, reset token, personal data | Exposes credentials or PII |
| Multipart parts | files containing real data, sensitive metadata | Exposes uploaded content |
| Custom snippets | dumping all headers or body | Bypasses masking configured for default snippets |
| CI logs/artifacts | test failures printing requests, generated snippets | Secret spreads into logs or artifacts |

Establish an allowlist of data permitted for publication. For example, request documentation can keep `Accept`, `Content-Type`, and a dummy correlation header; there is no need to record `Authorization` values or session cookies.

Do not use production data to generate snippets. Test fixtures should use synthetic data, dummy domains, and test-only credentials.

## 3. Masking Request Headers with Preprocessors

Spring REST Docs provides request preprocessors to transform requests before snippets are written. Two common choices are `removeHeaders(...)` and `modifyHeaders(...)`.

### 3.1. Removing Sensitive Headers

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie", "X-API-Key")
    ),
    requestHeaders(
        headerWithName("Accept").description("Response format")
    )
));
```

`removeHeaders(...)` deletes headers from the copy of the request written to snippets. It does not remove headers from the actual request the test sends to the application; the operation still authenticates with the required credentials, while documentation omits those values.

If a header does not need to appear in documentation, removing the entire header is the simplest option. If you want to keep the header name while replacing its value with a placeholder, use `modifyHeaders(...)`.

### 3.2. Replacing Values with Placeholders

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <redacted>")
            .set("X-API-Key", "<redacted>")
    )
));
```

This lets readers see which headers the endpoint requires without seeing real credentials. Check `modifyHeaders()` syntax against your project's Spring REST Docs version; the builder API supports setting, removing, or modifying headers.

### 3.3. Combining Multiple Operations

```java
.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Cookie"),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-API-Key", "<api-key>")
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer token for authentication"),
        headerWithName("Accept")
            .description("Response format")
    )
));
```

The `Cookie` header is removed; `Authorization` and `X-API-Key` remain with placeholder values. `requestHeaders(...)` documents the header contract, while the preprocessor controls the recorded values. Never put real tokens inside descriptions or examples.

## 4. Masking Response Headers

Responses can also contain sensitive data such as `Set-Cookie`, new tokens, or internal headers. Use the corresponding response preprocessor:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Token")
    ),
    responseHeaders(
        headerWithName("Content-Type")
            .description("Response format")
    )
));
```

If the response contract needs to show the presence of `Set-Cookie`, replace its value with a placeholder rather than deleting the header, and describe only non-sensitive attributes. Cookie values, session identifiers, and tokens must never enter snippets.

Do not assume a request preprocessor applies to responses. Configure both `preprocessRequest(...)` and `preprocessResponse(...)` for the data that needs protection.

## 5. Masking Secrets in Request and Response Bodies

Header preprocessing does not protect JSON bodies. If a request contains:

```json
{
  "username": "demo-user",
  "password": "correct-horse-battery",
  "clientSecret": "secret-value"
}
```

sensitive values must be replaced before generating snippets. Spring REST Docs provides `replacePattern(...)` to substitute regex-matched strings in preprocessed content.

Example:

```java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

.andDo(document("oauth-token",
    preprocessRequest(
        replacePattern(
            Pattern.compile("\"password\"\\s*:\\s*\"[^\"]*\""),
            "\"password\":\"<redacted>\""
        ),
        replacePattern(
            Pattern.compile("\"clientSecret\"\\s*:\\s*\"[^\"]*\""),
            "\"clientSecret\":\"<redacted>\""
        )
    )
));
```

You can apply `preprocessResponse(...)` similarly if a response body contains tokens:

```java
.andDo(document("oauth-token",
    preprocessResponse(
        replacePattern(
            Pattern.compile("\"accessToken\"\\s*:\\s*\"[^\"]*\""),
            "\"accessToken\":\"<redacted>\""
        ),
        replacePattern(
            Pattern.compile("\"refreshToken\"\\s*:\\s*\"[^\"]*\""),
            "\"refreshToken\":\"<redacted>\""
        )
    )
));
```

The regexes above only illustrate simple JSON. For deeply nested JSON, complex escaping, or varying structure, regexes can miss matches or replace the wrong content. Consider preprocessing with a JSON parser, traversing the tree, and replacing values by JSON path. Whenever possible, use fixtures free of secrets from the outset; redaction is an extra layer of defense.

### 5.1. Do Not Confuse Redaction with Validation

Preprocessors only modify the operation copy written to snippets. They do not prove that the endpoint encrypts or protects secrets properly, nor do they replace application security tests.

For instance, replacing `"password":"..."` with a placeholder in snippets does not mean the server stores passwords securely. Storage, hashing, transport, and authentication require separate tests and controls.

## 6. MockMvc Example: Request Has a Token, Snippet Does Not

Suppose an endpoint requires a Bearer token for access. The test uses dummy test-only credentials:

```java
@Test
void documentProfileWithoutLeakingAccessToken() throws Exception {
    String testToken = "test-only-token-123";

    mockMvc.perform(get("/api/profile")
            .header("Authorization", "Bearer " + testToken)
            .header("X-API-Key", "test-api-key")
            .cookie(new Cookie("JSESSIONID", "test-session"))
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("profile-get",
            preprocessRequest(
                removeHeaders("Cookie"),
                modifyHeaders()
                    .set("Authorization", "Bearer <access-token>")
                    .set("X-API-Key", "<api-key>")
            ),
            requestHeaders(
                headerWithName("Authorization")
                    .description("Authentication Bearer token"),
                headerWithName("X-API-Key")
                    .description("Application API key"),
                headerWithName("Accept")
                    .description("Response format")
            ),
            responseFields(
                fieldWithPath("id").description("User ID"),
                fieldWithPath("displayName").description("Display name")
            )
        ));
}
```

The actual request still sends the test token so authentication succeeds. The recorded request snippet uses placeholders and omits cookies. For real tokens, never rely solely on the test masking them afterward; documentation tests must use mocked credentials or ephemeral credentials generated strictly for testing.

If the system uses a security filter, you can use a test security principal or a token signed with a test key. Never call a production authentication service merely to generate snippets.

## 7. Verifying Generated Snippets Contain No Secrets

Redaction should be verified as a test requirement. After running the document operation, read the relevant snippets and assert that sensitive values do not appear.

Example:

```java
Path operationDir = snippetsDir.resolve("profile-get");

String requestSnippet = Files.readString(
        operationDir.resolve("http-request.adoc")
);

assertThat(requestSnippet)
        .doesNotContain("test-only-token-123")
        .doesNotContain("test-api-key")
        .doesNotContain("test-session")
        .contains("<access-token>")
        .contains("<api-key>");
```

If other snippets can also record headers, check `request-headers.adoc`, custom summaries, or corresponding body files as well. Do not check only `http-request.adoc`.

You can write a helper that scans the entire operation directory:

```java
try (Stream<Path> files = Files.walk(operationDir)) {
    List<String> generated = files
            .filter(Files::isRegularFile)
            .map(path -> {
                try {
                    return Files.readString(path);
                } catch (IOException exception) {
                    throw new UncheckedIOException(exception);
                }
            })
            .toList();

    assertThat(generated)
            .noneMatch(content -> content.contains("test-only-token-123"));
}
```

To detect multiple kinds of secrets, you can check a list of dummy values used in tests. Avoid printing the secret itself in assertion failure messages or logs; report only the data category and affected file.

## 8. Protecting Custom Snippets with an Allowlist

Custom snippets can read `OperationRequest.getHeaders()`, `OperationResponse.getHeaders()`, or the body directly. If the code dumps all headers, it can bypass the redaction configured for default snippets.

Avoid:

```java
model.put("requestHeaders", operation.getRequest().getHeaders());
```

Instead, explicitly select allowed headers:

```java
HttpHeaders headers = operation.getRequest().getHeaders();

model.put("accept", headers.getFirst("Accept"));
model.put("contentType", headers.getFirst("Content-Type"));
model.put("correlationId", headers.getFirst("X-Correlation-Id"));
```

This is an allowlist: only selected entries make it into the template. If a custom snippet needs to show that an Authorization header is present, pass a boolean or placeholder into the model rather than the real value:

```java
model.put(
    "authorizationPresent",
    headers.containsKey(HttpHeaders.AUTHORIZATION)
);
model.put("authorizationValue", "<redacted>");
```

Apply allowlists to response headers, cookies, query parameters, and multipart part metadata as well. Do not include raw request/response bodies in custom snippets unless truly necessary and paired with an appropriate redaction strategy.

## 9. Sensitive Data in Query Strings, Multipart, and Responses

### 9.1. Query Parameters

Avoid passing tokens via query strings. URLs can be recorded in `http-request.adoc`, server logs, proxies, and monitoring. If a legacy API must accept a query secret, replace the value in a request preprocessor or avoid including the full URI; prefer redesigning it to use the `Authorization` header.

### 9.2. Multipart Parts

Uploaded files can contain real data. Use dummy fixtures rather than real ID documents, contracts, customer records, or production files. Custom snippets should only record part name, media type, and size; do not dump raw bytes or part contents unnecessarily.

### 9.3. Response Body

Endpoints for login, token refresh, password reset, or API key generation often return credentials in the response body. Use a response preprocessor to replace tokens with placeholders before generating `response-body.adoc` or the HTTP response snippet. If schema documentation is needed, `responseFields(...)` can describe the token field without exposing real values; tests should use dummy tokens.

### 9.4. Personal Data

Emails, phone numbers, addresses, and personal identifiers must also be handled according to organizational data policies. Replace them with consistent synthetic data, such as `user@example.test`; do not use production data expecting regexes to mask every occurrence.

## 10. Protecting Secrets in Test Configuration and CI

Snippet redaction does not replace credential management:

- Never hard-code production credentials in source code, test fixtures, or build files.
- Use test principals, mock authentication, or tokens signed with a test-only key.
- If tests need temporary secrets, pull them from the CI environment's secret store with least privilege.
- Never print raw headers/bodies to the console on test failures.
- Restrict access to CI artifacts containing generated snippets.
- Never publish raw test artifacts without running a secret check step first.
- Revoke or rotate credentials if a real value is discovered in a repository or artifact.

For documentation tests, fixed dummy credentials are usually preferable to shared environment secrets. The goal is testing the authentication flow without creating sensitive data that holds real value.

## 11. Responding When a Secret Leaks into Snippets

If a token or sensitive data is found in generated documentation:

1. Stop publishing the affected artifacts.
2. Identify the credential type, scope, and where it has been stored or shared.
3. Revoke/rotate the credential if it is still active.
4. Remove the value from source files and generated snippets; regenerate artifacts once redaction is fixed.
5. Inspect commit history, CI artifacts, published packages/sites, and caches.
6. Follow your organization's incident/security process if data escaped controlled boundaries.
7. Add test assertions or scanners to prevent recurrence.

Deleting a file only from the working tree does not erase a secret from Git history or published artifacts. If a real secret was committed, follow an organization-approved revocation and history-cleanup process; do not treat fixing a new commit as sufficient.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Token appears in `http-request.adoc` | Request was not preprocessed | Use `removeHeaders` or `modifyHeaders` |
| Token still appears in custom summary | Custom snippet reads raw headers from operation | Switch to allowlist and placeholders |
| Cookie appears even though Authorization is masked | Only one header was handled | Strip/mask both `Cookie` and `Set-Cookie` |
| Password appears in request body | Only headers were redacted | Use a body preprocessor or dummy fixture |
| Access token appears in response body | Only request was preprocessed | Use `preprocessResponse(...)` |
| Regex misses nested JSON | Regex does not understand JSON structure | Parse JSON and replace by path |
| Test passes yet snippet contains secret | No assertions on generated output | Scan the entire operation directory |
| Secret leaks in CI logs | Test failure dumps request/response | Disable raw logging, use dummy data, control reporters |
| Real token used for documentation tests | Reusing environment credentials | Use a mock principal or test token |
| Snippet deleted only on a new branch | Secret remains in history/artifacts | Rotate and clean history/artifacts per incident process |

## 13. Asciidoctor and Build/CI

Preprocessed snippets are included as usual:

```adoc
= Profile API
:toc: left

== Get Profile

=== HTTP request
include::{snippets}/profile-get/http-request.adoc[]

=== Request headers
include::{snippets}/profile-get/request-headers.adoc[]

=== Response fields
include::{snippets}/profile-get/response-fields.adoc[]
```

Recommended CI workflow:

```text
Documentation HTTP tests
        |
        v
Request/response preprocessors
        |
        +--> Remove or replace sensitive headers
        +--> Redact sensitive body fields
        |
        v
Spring REST Docs generated snippets
        |
        v
Secret scan + assertions on generated files
        |
        v
Asciidoctor / Markdown build
        |
        v
Artifact review and publish
```

With Gradle and the Asciidoctor plugin configured:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

The secret scan should run after tests generate snippets and before artifacts are published. A scanner is an extra safeguard; test assertions checking specific test values remain necessary because generic scanners can miss custom-formatted tokens.

Do not store generated snippets containing secrets in public caches. When a build fails due to a detected secret, logs should report only the file/path and violated rule, never reprinting the detected value.

## 14. Hands-On Exercise

For a `GET /api/profile` endpoint requiring a Bearer token:

1. Create a test-only dummy token and send it via `Authorization`.
2. Use `preprocessRequest(removeHeaders(...))` or `modifyHeaders()` to strip/replace the token.
3. Add a dummy session cookie and API key; ensure they are also masked.
4. Create a JSON request with `password` and `clientSecret` fields; use a body preprocessor to replace values before writing snippets.
5. Create an endpoint response containing `accessToken`; use `preprocessResponse(...)` to mask the response body.
6. Add a custom snippet reading only allowlisted headers; do not dump raw `HttpHeaders`.
7. After the test, scan the entire operation directory and assert sensitive dummy values do not appear.
8. Run a secret scanner over generated snippets before Asciidoctor/publish.
9. Verify CI logs do not print raw requests or responses on test failure.
10. Temporarily omit a preprocessor to confirm the security assertion fails the build.

### Self-Assessment Questions

- Why must `Authorization` and `Cookie` be handled before writing snippets?
- How does `removeHeaders(...)` differ from `modifyHeaders()`?
- Does a request preprocessor mask the response body?
- Why must custom snippets be checked separately?
- When is regex redaction unsafe for JSON?
- Why do dummy test values still need assertions on generated output?
- At which step in CI should secret scanning run?
- If a real secret was committed, why is deleting the current file insufficient?
- How can you keep a header name in documentation without exposing its value?

**Remember:** Treat generated snippets as artifacts that may be committed and published. Use dummy data, preprocess both requests and responses, prefer allowlists for custom snippets, and verify output after generation. Documentation redaction does not replace secret management, and any real token leaked into history or artifacts must be revoked and handled as a security incident.

## References

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): request/response preprocessors and modifying content before snippet generation.
- [Spring REST Docs — `Preprocessors` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): `removeHeaders`, `modifyHeaders`, `replacePattern`, and helpers.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): documenting request/response headers.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): managing, rotating, and protecting secrets.
