# Replacing Patterns in Bodies or Headers

## 1. Objectives

HTTP requests and responses may contain access tokens, session IDs, API keys, passwords, emails, or internal data. Spring REST Docs captures the operation and generates snippets from that data. Before generating documentation, sensitive values should be replaced with placeholders or removed.

It is important to distinguish two data areas:

- **Headers:** collections of names and values such as Authorization, Cookie, Set-Cookie, and X-Api-Key.
- **Content/body:** the request/response payload, typically JSON, XML, or text.

Spring REST Docs provides two distinct API groups. **modifyHeaders()** adds, sets, or removes headers. **replacePattern(Pattern, String)** replaces regex matches in the request/response content. replacePattern does not operate directly on the header collection.

This lesson belongs to the **Security** chapter of the **SPRING_REST_DOCS** module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; compiles Asciidoctor/Markdown; and integrates with build/CI pipelines.

After this lesson, you will be able to distinguish header and body processing, replace header values with placeholders, mask fields in bodies, combine request/response preprocessors, write a custom preprocessor when regex on headers is needed, and check for secret leaks in CI.

## 2. Identifying Areas to Replace

~~~http
POST /api/profile HTTP/1.1
Authorization: Bearer real-access-token
X-Api-Key: real-api-key
Content-Type: application/json

{
  "email": "person@example.test",
  "password": "plain-or-test-secret",
  "displayName": "An"
}
~~~

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=real-session-id; Path=/; HttpOnly; Secure
Content-Type: application/json

{
  "id": 42,
  "email": "person@example.test",
  "accessToken": "new-access-token",
  "displayName": "An"
}
~~~

| Area | Example | Mechanism |
| --- | --- | --- |
| Request header | Authorization | modifyHeaders set/remove. |
| Request header | X-Api-Key | modifyHeaders set/remove. |
| Response header | Set-Cookie | modifyHeaders set/remove. |
| Request body | password, email | replacePattern or content-aware modifier. |
| Response body | accessToken, PII | replacePattern or content-aware modifier. |
| URL/query | token in request line | Synthetic value or separate URI processing. |

Identify which information must be preserved to explain the contract. You can keep the Authorization header name and Bearer scheme while replacing the credential. Use synthetic addresses for email.

## 3. Replacing Header Values with modifyHeaders()

Spring REST Docs 3.x/4.x provides modifyHeaders() to add, set, and remove request/response headers.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.andDo(document("profile-update",
    preprocessRequest(
        modifyHeaders().set("Authorization", "Bearer <access-token>")
    )
));
~~~

The header still appears in the snippet, but its value has been replaced with a non-functional placeholder. This approach is useful when you want the documentation to show the authentication scheme without exposing a credential.

Replacing an API key:

~~~java
preprocessRequest(
    modifyHeaders().set("X-Api-Key", "<api-key>")
);
~~~

Or removing headers:

~~~java
preprocessRequest(
    modifyHeaders()
        .remove("Cookie")
        .remove("X-Internal-Auth")
);
~~~

### 3.1. Replacing Response Headers

Use the same preprocessor for responses:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.andDo(document("login",
    preprocessResponse(
        modifyHeaders()
            .set("Set-Cookie", "SESSION=<session-id>; HttpOnly; Secure")
            .set("X-Request-Id", "<request-id>")
    )
));
~~~

If you do not need to document the cookie, remove Set-Cookie. If you need to document Path, HttpOnly, Secure, or SameSite, keep the attributes and replace the session value.

### 3.2. Set or Remove?

| Approach | Result | When Appropriate |
| --- | --- | --- |
| set(name, placeholder) | Header retains its name and a dummy value | You want to document the header contract. |
| remove(name) | Header does not appear | Header is unnecessary for the example. |
| No preprocess | Original value is recorded | Only when the value is definitely public. |

Do not remove Content-Type, Accept, Location, or Cache-Control if they are part of the API contract.

## 4. replacePattern() for Bodies

replacePattern() accepts a Java Pattern and a replacement string. It finds matches in the request/response content and replaces them with the new value.

~~~json
{
  "email": "person@example.test",
  "password": "my-secret-password",
  "displayName": "An"
}
~~~

Pattern to mask password:

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

private static final Pattern PASSWORD_FIELD =
    Pattern.compile("(\"password\"\\s*:\\s*\")[^\"]*(\")");

.andDo(document("profile-update",
    preprocessRequest(
        replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
    )
));
~~~

Expected result:

~~~json
{
  "email": "person@example.test",
  "password": "[REDACTED]",
  "displayName": "An"
}
~~~

Group 1 preserves the field name and opening quote; group 2 preserves the closing quote. The replacement maintains the JSON structure and replaces only the value. This pattern is for simple JSON strings; you must verify escaping, multiline values, and actual serialization.

## 5. Masking Multiple Fields

You can use a single pattern with a list of sensitive fields:

~~~java
private static final Pattern SECRET_FIELDS = Pattern.compile(
    "(\"(password|clientSecret|accessToken|refreshToken)\"\\s*:\\s*\")[^\"]*(\")"
);
~~~

Apply to the response:

~~~java
.andDo(document("login",
    preprocessResponse(
        replacePattern(SECRET_FIELDS, "$1[REDACTED]$3")
    )
));
~~~

Field names must match the actual payload. Do not use overly broad patterns such as token if the API has business fields with that name that are not secrets.

If you need to mask both directions, configure each side separately:

~~~java
.andDo(document("credential-exchange",
    preprocessRequest(
        replacePattern(SECRET_FIELDS, "$1[REDACTED]$3")
    ),
    preprocessResponse(
        replacePattern(SECRET_FIELDS, "$1[REDACTED]$3")
    )
));
~~~

A request preprocessor does not automatically apply to the response, and vice versa.

## 6. Combining Header and Body Replacement

~~~java
.andDo(document("login",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .remove("Cookie"),
        replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
    ),
    preprocessResponse(
        modifyHeaders()
            .set("Set-Cookie", "SESSION=<session-id>; HttpOnly; Secure"),
        replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3")
    )
));
~~~

Header transformation and content transformation are applied together to the corresponding request/response. Patterns must match the actual schema and the generated output must be verified.

Keep snippets useful: Content-Type, Accept, field names, status codes, and response shapes; replace credentials with placeholders; and use synthetic data for emails, phone numbers, and customer IDs.

## 7. Regex on Header Values: Limitations and Extensions

replacePattern() processes content bodies; it does not scan header collections. If you know the header name and want to replace the entire value, use modifyHeaders().set():

~~~java
preprocessRequest(
    modifyHeaders().set("Authorization", "Bearer <access-token>")
);
~~~

If you need to replace part of a value using regex, you can write a custom OperationPreprocessor:

~~~java
OperationPreprocessor maskAuthorizationValue = operation -> {
    // Read the operation's headers.
    // Replace the credential in Authorization with a placeholder.
    // Create a new operation, preserving method, URI, body, and remaining metadata.
    return operationWithSanitizedHeaders;
};
~~~

This is pseudocode, not a copy-paste implementation. You need to use the OperationRequest/OperationResponse API and factory/constructor matching your REST Docs version. If you only need to replace the entire value, modifyHeaders().set() is simpler.

### 7.1. Do Not Rely on the HTTP Snippet Text Dump

REST Docs stores headers and content in separate structures. replacePattern() is designed for content. Do not assume it will replace headers just because the final HTTP snippet file displays headers and body in the same text.

## 8. Avoiding Regex That Breaks JSON

Simple regex may be insufficient if a value contains escaped quotes, backslashes, newlines, or nested JSON.

~~~json
{
  "credentials": {
    "password": "secret",
    "metadata": {
      "note": "text with an escaped quote: \"hello\""
    }
  }
}
~~~

For complex JSON, consider ContentModifier:

1. Parse the JSON into a tree using your project's library.
2. Traverse the exact JSON paths that need masking.
3. Replace values with placeholders.
4. Re-serialize the JSON.
5. Check Content-Type and charset.
6. Return the new content to the operation preprocessor.

Spring REST Docs provides ContentModifier and ContentModifyingOperationPreprocessor to modify request/response bodies. This approach is appropriate when JSON structure awareness is needed instead of regex text replacement.

Do not parse every body as JSON. XML, multipart, and binary payloads require separate handling.

## 9. Default Preprocessors Across Multiple Tests

If all operations require the same policy, configure default request/response preprocessors in RestDocumentationConfigurer.

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation)
        .operationPreprocessors()
        .withRequestDefaults(
            modifyHeaders().set("Authorization", "Bearer <access-token>")
        )
        .withResponseDefaults(
            modifyHeaders().set("Set-Cookie", "SESSION=<session-id>")
        ))
    .build();
~~~

Default preprocessors help prevent forgotten redactions. However, if only some endpoints have Authorization or Set-Cookie, a global policy might add unnecessary placeholders. You can combine defaults with operation-specific preprocessors.

WebTestClient and REST Assured also have documentation configurers for configuring default operation preprocessors. Check the exact client instance and version.

## 10. Verifying Generated Snippets

Use a sentinel in your test fixtures:

~~~java
private static final String DOCS_SECRET =
    "DOCS_ONLY_SECRET_92a1";
~~~

After the tests generate snippets, read all output and confirm:

~~~java
assertThat(allGeneratedSnippetText)
    .doesNotContain(DOCS_SECRET)
    .doesNotContain("my-secret-password");
~~~

Verify that the placeholder remains if that is the expected output. Scan everything:

- http-request and http-response.
- curl-request and httpie-request.
- request-body and response-body.
- Request/response headers.
- Custom snippets and assembled Markdown/Asciidoctor pages.
- Rendered HTML if code examples are published.

Do not inspect only the main request/response files; the same operation can generate multiple snippets.

## 11. Examples with MockMvc, WebTestClient, and REST Assured

### 11.1. MockMvc

~~~java
mockMvc.perform(post("/api/profile")
        .header("Authorization", "Bearer DOCS_ONLY_SECRET")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"email\":\"person@example.test\",\"password\":\"DOCS_ONLY_PASSWORD\"}"))
    .andExpect(status().isOk())
    .andDo(document("profile-update",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
        )
    ));
~~~

Use synthetic credentials. If the controller requires authentication, configure the test security context using Spring Security test support; do not obtain a real token just to pass the security filter.

### 11.2. WebTestClient

~~~java
webTestClient.post()
    .uri("/api/profile")
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(profileRequest)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("profile-update-webflux",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
        )
    ));
~~~

Attach preprocessors to the operation recorded by the WebTestClient REST Docs filter.

### 11.3. REST Assured

~~~java
given(specification)
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .contentType("application/json")
    .body(profileRequest)
    .filter(document("profile-update-restassured",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
        )
    ))
.when()
    .post("/api/profile")
.then()
    .statusCode(200);
~~~

The REST Assured documentation filter must use the same REST Docs context. Inspect the output after the filter runs.

## 12. CI: Checking and Blocking Secret Leaks

~~~mermaid
flowchart TD
    A["HTTP tests with synthetic values"] --> B["Apply header preprocessors"]
    B --> C["Apply body pattern/content preprocessors"]
    C --> D["Generate all snippets"]
    D --> E["Assemble final docs"]
    E --> F["Scan sentinels and secret patterns"]
    F --> G{"Secret found?"}
    G -->|Yes| X["Fail CI"]
    G -->|No| H["Render and validate docs"]
    H --> I{"All checks pass?"}
    I -->|No| X
    I -->|Yes| J["Publish"]
~~~

CI should:

1. Use synthetic credentials and dedicated sentinels.
2. Run REST Docs tests.
3. Scan generated snippets before assembly.
4. Assemble the final documentation and scan again.
5. Inspect rendered HTML/artifacts if applicable.
6. Fail the build if a sentinel or secret pattern is detected.
7. Never print raw secrets in logs.
8. Publish only after tests, scanning, and rendering pass.

Scanners can produce false positives. Use a narrow, reviewed allowlist for placeholder fixtures; never allowlist real credentials.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| replacePattern does not change Authorization | Headers are not part of body content | Use modifyHeaders().set/remove(). |
| Header changed but password remains | Only preprocessed headers | Add replacePattern or ContentModifier. |
| Only request was masked | Forgot preprocessResponse | Configure both request and response. |
| JSON corrupted after regex | Pattern does not handle escaping/nested values | Use a JSON-aware ContentModifier. |
| Some operations still contain secrets | Helper/default preprocessors not used | Check the operation and configure defaults. |
| curl snippet still has credentials | Only checked http-request | Scan all snippets. |
| Header contract disappears | Used remove instead of setting a placeholder | Use set when you need to preserve header name/scheme. |
| Placeholder mistaken for real token | Placeholder looks like a valid credential | Use an unmistakable string like <access-token>. |
| CI detects leak after publish | Scan placed after publish | Move leak scan into the publish gate. |
| Regex replaces unrelated business field | Pattern is too broad | Match exact fields/paths and test fixtures. |

## 14. Practice Exercise

Create a login endpoint and a profile update endpoint:

- POST /api/auth/login accepts username/password and returns accessToken.
- PATCH /api/profile accepts Authorization and JSON containing email/password.
- The response includes Set-Cookie and a request ID.

Steps to perform:

1. Write HTTP tests with synthetic credentials.
2. Use modifyHeaders().set() to replace Authorization with a placeholder.
3. Use modifyHeaders().set() or remove() to handle Set-Cookie and X-Api-Key.
4. Use replacePattern() to mask password/accessToken in bodies.
5. For complex nested/escaped JSON, try ContentModifier.
6. Attach preprocessors to requests and responses on the appropriate operations.
7. Generate HTTP, curl, HTTPie, body, and descriptor snippets.
8. Scan snippets and assembled docs with sentinels.
9. Intentionally omit one preprocessor to verify CI detects the leak.
10. Document why header replacement and body replacement use different APIs.

**Completion criteria:** header values are set/removed properly; body fields are replaced via pattern or content-aware modifier; JSON remains valid; no snippets contain sentinels; CI blocks publishing if a secret appears.

## References

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs — ContentModifier API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/ContentModifier.html)
- [Spring REST Docs — HeadersModifyingOperationPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/HeadersModifyingOperationPreprocessor.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
