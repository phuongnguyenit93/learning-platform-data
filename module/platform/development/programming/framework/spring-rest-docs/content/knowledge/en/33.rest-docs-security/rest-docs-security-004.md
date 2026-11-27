# Do Not Record Secrets in Generated Snippets

## 1. Why Do Generated Snippets Need Protection?

Spring REST Docs captures HTTP requests and responses from tests to generate API documentation. Snippets such as `http-request.adoc`, `request-headers.adoc`, `request-body.adoc`, `http-response.adoc`, and `response-body.adoc` can contain sensitive data if tests send real credentials or payloads.

A token that slips into a snippet may be committed to Git, attached to a CI artifact, published to a documentation website, or stored in caches. Deleting the value from the file in a later commit does not automatically remove it from history or already-published artifacts. Therefore, protecting snippets must start with test data, continue at the preprocessing step, and conclude with output verification before publishing.

In **SPRING_REST_DOCS**, HTTP tests use MockMvc, WebTestClient, or REST Assured as the source for generating snippets for requests, responses, payloads, parameters, and headers. The **Security** chapter focuses on ensuring generated documentation contains no secrets. This lesson guides you through identifying sensitive data, using preprocessors, protecting custom snippets, inspecting generated files, and organizing a secure CI pipeline.

After this lesson, you will be able to:

- Identify secrets that may appear in requests, responses, and custom snippets.
- Use synthetic data or short-lived test credentials.
- Remove or replace sensitive headers before snippets are written.
- Mask data in bodies, URIs, cookies, and multipart metadata.
- Inspect all output to guarantee no secret values appear.
- Protect CI logs and artifacts, and respond properly when a secret has been leaked.

## 2. Locations Where Secrets Can Leak

| Location | Example | Risk |
| --- | --- | --- |
| Request header | `Authorization: Bearer ...`, `X-API-Key` | Exposes API access credentials |
| Cookie | `Cookie`, `Set-Cookie`, session ID | Session hijacking |
| Query string | `?access_token=...` | URI is recorded in HTTP snippets and logs |
| Request body | `password`, `clientSecret`, `refreshToken` | Exposes authentication credentials |
| Response body | access token, reset token, API key | Exposes newly issued credentials |
| Multipart | real files, personal metadata, sensitive filenames | Exposes content or identifiers |
| Custom snippet | dumping all headers/body | Bypasses standard snippet redaction |
| CI | console output, test reports, artifacts | Expands leak blast radius |

Tokens are not the only secrets. Email addresses, phone numbers, physical addresses, customer IDs, medical records, or payment details may also be data requiring protection under organizational policy.

## 3. Start with Safe Test Data

Redaction is an additional layer of defense. The best approach is never putting real secrets into documentation tests.

- Use mock principals, mock authentication, or tokens valid only in tests.
- If you need to test Bearer authentication, generate tokens using a dedicated test key; do not read production tokens from a developer machine.
- Use synthetic data such as `user@example.test`, fake phone numbers, and harmless fixture files.
- Do not use a copy of the production database as test fixtures.
- Do not write credentials into source files, `application-test.yml`, build files, or test reports.

Example dummy token:

```java
String testToken = "test-only-token-123";

mockMvc.perform(get("/api/profile")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
```

This token is only for test illustration. If a test requires a validly signed token, sign it with a test key or use the framework's security test mechanisms. Never reuse credentials that grant permissions in a real environment.

## 4. Removing Sensitive Request Headers

Spring REST Docs provides request preprocessors that run before snippets are written. Use `removeHeaders(...)` when a header does not need to appear in documentation:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie", "X-API-Key")
    )
));
```

The preprocessor modifies the copy of the request used for documentation. The actual request is still sent with the token so authentication executes; the header value is stripped from the recorded snippet.

If the documentation needs to indicate that an endpoint requires a header, you can document the header using `requestHeaders(...)` without putting secret values in the example. Removing the value alone is sufficient when readers do not need to see the header; if you need to keep the name and replace the value, use `modifyHeaders(...)`.

## 5. Replacing Header Values with Placeholders

`modifyHeaders()` lets you set safe values in the recorded request:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-API-Key", "<api-key>")
    )
));
```

The output still shows the headers the client needs to send, while the real value is omitted from the snippet. You can combine this with removing cookies:

```java
.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Cookie"),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
    )
));
```

Check the builder API for your project's Spring REST Docs version. Avoid writing placeholders that resemble live credentials; use values clearly marked as placeholders like `<access-token>`.

## 6. Protecting Response Headers

Responses may contain `Set-Cookie`, new tokens, or internal headers. Use `preprocessResponse(...)` separately:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Token")
    )
));
```

If you need to document cookie or token headers in the contract, replace values with placeholders and disclose only non-sensitive attributes. Do not assume `preprocessRequest(...)` automatically applies to responses; each side must be configured explicitly.

## 7. Masking Data in Request and Response Bodies

Header preprocessing does not mask fields inside JSON. Example login body:

```json
{
  "username": "demo-user",
  "password": "test-password-value",
  "clientSecret": "test-client-secret"
}
```

For simple JSON, `replacePattern(...)` can replace sensitive strings before the snippet is written:

```java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

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
```

A similar approach can be applied to responses:

```java
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
```

Regex is only suitable for known, simple structures. Escaped JSON, nested objects, or varying formatting can cause regex to miss matches. For complex payloads, use a JSON parser to replace values by path and re-serialize, or design fixtures without secrets from the start. Do not treat regex as a general-purpose security filter.

## 8. Avoiding Secrets in URIs and Query Parameters

Do not pass access tokens or API keys in query strings. URIs are frequently recorded in `http-request.adoc`, access logs, reverse proxies, and monitoring systems.

If an existing API must accept a secret in a query parameter:

- Prefer updating the API to use the Authorization header.
- If it cannot be changed yet, use a request preprocessor to replace the query value before writing snippets.
- Inspect both `http-request.adoc` and the `request-parameters.adoc` snippet.
- Do not put raw query strings into custom snippets.

Redaction on headers does not mask query strings. URIs and parameters must be checked separately.

## 9. Multipart Parts and File Uploads

Multipart requests can contain real files, filenames containing customer names, or JSON metadata with private data. Use synthetic fixture files and dummy metadata. Custom snippets should limit information to part name, media type, and size if those fields are sufficient for the documentation.

Do not pass `part.getContent()` or `getContentAsString()` directly into a custom snippet without redaction rules. Filenames are also client-supplied data; do not assume they are always harmless.

If you need to illustrate a file upload, use a public fixture or generate random data in the test. Never take documents, profile photos, or uploaded files from production to generate docs.

## 10. Custom Snippets Must Use an Allowlist

Custom snippets can read `OperationRequest`, `OperationResponse`, and headers directly. Putting the entire `HttpHeaders` into the model can leak data even when standard snippets have been preprocessed.

Avoid:

```java
model.put("headers", operation.getRequest().getHeaders());
```

Instead, explicitly select the values allowed to be published:

```java
HttpHeaders headers = operation.getRequest().getHeaders();

model.put("accept", headers.getFirst(HttpHeaders.ACCEPT));
model.put("contentType", headers.getContentType());
model.put("authorizationPresent",
        headers.containsKey(HttpHeaders.AUTHORIZATION));
model.put("authorizationValue", "<access-token>");
```

This is an allowlist: only selected keys are passed to the template. Apply the same principle to response headers, cookies, URIs, query parameters, and multipart metadata. If a custom snippet reads raw operation data directly, ensure it uses sanitized data or performs its own redaction before building the model.

## 11. Verifying Generated Snippets After Writing

Preprocessors can be forgotten when a new test is added. Therefore, add assertions on the generated output rather than only checking that the code calls `removeHeaders(...)`.

Example after tests generate snippets:

```java
Path operationDir = snippetsDir.resolve("profile-get");
String request = Files.readString(
        operationDir.resolve("http-request.adoc"));

assertThat(request)
        .doesNotContain("test-only-token-123")
        .doesNotContain("test-api-key")
        .doesNotContain("test-session")
        .contains("<access-token>");
```

Also inspect `request-headers.adoc`, body snippets, and custom snippets if they are generated. You can scan all files in the operation directory:

```java
try (Stream<Path> paths = Files.walk(operationDir)) {
    List<String> contents = paths
        .filter(Files::isRegularFile)
        .map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })
        .toList();

    assertThat(contents)
        .noneMatch(content -> content.contains("test-only-token-123"));
}
```

Do not include secret values in assertion failure messages or logs. The test only needs to report which file violated the check and what category of data was detected.

## 12. Managing Secrets in CI

Snippet redaction does not replace credential management. The pipeline should:

1. Use test principals or dedicated test credentials.
2. Not print raw requests/responses when tests fail.
3. Run documentation tests and generate snippets.
4. Scan generated files before rendering or publishing.
5. Restrict read permissions on CI artifacts.
6. Not publish raw test directories without passing secret checks.
7. Save scanner logs without re-printing detected values.

A secret scanner is an additional layer. Generic scanners may not recognize organization-specific token formats; assertions on specific test values remain necessary.

## 13. Handling a Secret That Has Slipped Into a Snippet

If a real credential is detected in a snippet or artifact:

1. Stop publishing or sharing the affected artifact.
2. Identify the secret type, access scope, and all locations where copies were stored.
3. Revoke or rotate the credential if it is still active.
4. Fix the test/preprocessor and regenerate clean snippets.
5. Check Git history, CI artifacts, documentation websites, and caches.
6. Follow your organization's incident/security process if the secret left controlled boundaries.
7. Add assertions or scanners to prevent recurrence.

Simply deleting the file from the working tree does not remove the secret from Git history or published artifacts. History cleanup must follow your organization's approved process after the credential has been revoked.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Token appears in HTTP request snippet | Request was not preprocessed | Use `removeHeaders` or `modifyHeaders` |
| Cookie still appears | Only masked Authorization | Handle `Cookie` and `Set-Cookie` separately |
| Password appears in body | Only redacted headers | Use a body preprocessor or synthetic fixture |
| Access token appears in response | Only preprocessed request | Use `preprocessResponse` |
| Custom summary exposes token | Dumped raw headers | Use an allowlist and placeholders |
| Query token remains intact | Did not check URI | Do not pass secrets via query; redact URI if mandatory |
| File upload contains real data | Used production fixture | Replace with synthetic file |
| Test passes but snippet still leaks secret | Did not assert on output | Scan the entire operation directory |
| Secret appears in CI logs | Reporter prints request/response on failure | Use synthetic data and disable raw logging |
| Deleted only the latest file | Secret remains in history/artifacts | Rotate and clean history/artifacts per incident process |

## 15. Asciidoctor and Build/CI

Preprocessed snippets are still included as usual:

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

With Gradle and the configured Asciidoctor plugin:

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

CI flow:

```text
Documentation HTTP tests
        |
        v
Request/response preprocessors
        |
        +--> Remove or replace sensitive headers
        +--> Redact sensitive body values
        |
        v
Generated snippets
        |
        v
Secret assertions + scanner
        |
        v
Asciidoctor / Markdown build
        |
        v
Artifact review and publish
```

The secret scan must run after snippets are generated and before artifacts are published. A successful documentation build does not prove the content is safe; secret checking is a separate gate.

## 16. Practice Exercise

For an endpoint `GET /api/profile` requiring a Bearer token:

1. Create a synthetic token dedicated to tests.
2. Send the token in `Authorization` and use `modifyHeaders()` to replace it with `<access-token>` in the snippet.
3. Send a dummy session cookie and API key; ensure they are removed or replaced.
4. Create a JSON request with `password` and `clientSecret`; redact them before writing the body snippet.
5. Create a response with `accessToken`; use a response preprocessor to mask the value.
6. Write a custom snippet that takes only allowlisted headers.
7. Scan the entire operation directory and assert that secret test values do not appear.
8. Add a secret scanner in CI before Asciidoctor/publishing.
9. Verify that logs on test failure do not print raw requests or responses.
10. Temporarily remove one preprocessor to confirm that the assertion fails the build.

### Self-Assessment Questions

- Why do `Authorization`, `Cookie`, and `Set-Cookie` need separate handling?
- How does `removeHeaders(...)` differ from `modifyHeaders()` in snippet output?
- Does a request preprocessor mask the response body?
- Why does a custom snippet need an allowlist even when standard snippets have been preprocessed?
- When is regex redaction unsafe for JSON?
- Why are assertions on generated files needed after running tests?
- Should secret scanning run before or after snippet generation?
- If a real secret was committed, why is deleting the file in a new commit not enough?
- How do you show a required header without exposing its value?

**Remember:** Treat generated snippets as artifacts that can be committed and published. Use synthetic data, preprocess both requests and responses, restrict custom snippets with an allowlist, and inspect output after generation. Redaction does not replace secret management; if a real credential has entered history or artifacts, revoke it and follow incident procedures.

## References

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): request/response preprocessors.
- [Spring REST Docs — `Preprocessors` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): `removeHeaders`, `modifyHeaders`, `replacePattern`, and related helpers.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): documenting request/response headers.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): managing and rotating secrets.
