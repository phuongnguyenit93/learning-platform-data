# Preprocessing to Mask or Replace Headers

## Learning Objectives

After this lesson, you will be able to:

- Explain why HTTP requests/responses need preprocessing before Spring REST Docs writes snippets.
- Distinguish masking a header value, replacing a value, removing a single header, and removing headers matching a pattern.
- Use `preprocessRequest(...)` and `preprocessResponse(...)` to apply preprocessors on the right side.
- Protect `Authorization`, `Cookie`, API keys, session identifiers, and internal data while retaining useful information for documentation.
- Recognize when removing a header prevents a descriptor from finding the header to be documented.
- Inspect output snippets and integrate secret-detection checks into review/build/CI workflows.

## 1. Why Do Headers Need Preprocessing?

Spring REST Docs records HTTP exchanges during documentation tests. Requests and responses can contain headers required for the system to function whose raw values should not appear verbatim in published documentation.

Example authenticated request:

```http
GET /api/me HTTP/1.1
Accept: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.production-like-secret
X-Internal-Tenant: tenant-7842
X-Request-Id: 9c0d8d9f-4e5a-4b83-9b01-0a0021f12a18
```

Some values in the example may:

- Be credentials or tokens that grant access.
- Be internal identifiers not intended for consumers.
- Change on every test run, making snippets hard to read and review.
- Contain environment, tenant, or other information that should not be published.

If the raw exchange is saved as-is, these values can flow into `http-request.adoc`, `http-response.adoc`, or other snippets, and then get included in documentation pages. **Preprocessing produces a safer and more stable representation before generating snippets.**

Preprocessing is one protective layer in the documentation pipeline. It does not replace using dummy fixtures, protecting secrets in CI, reviewing artifacts, or managing documentation access permissions.

## 2. Where Does REST Docs Preprocessing Fit in Snippet Generation?

A typical HTTP documentation test:

1. Builds a request with the necessary headers/body.
2. Sends the request via MockMvc, WebTestClient, or REST Assured.
3. Checks status, headers, and body using assertions.
4. Calls `document(...)` to record the exchange and generate snippets.

When preprocessors are added, the flow looks like:

```mermaid
flowchart TD
    A[HTTP request with test values] --> B[Execute request]
    B --> C[Receive response]
    C --> D[Assertions on verified behavior]
    D --> E[Preprocess request and/or response]
    E --> F[REST Docs records processed exchange]
    F --> G[HTTP/header/body snippets]
    G --> H[Asciidoctor or Markdown renderer]
```

Two key functions for attaching preprocessors:

| Function | Target Processed | Example |
| --- | --- | --- |
| `preprocessRequest(...)` | Request recorded into snippets | Mask `Authorization`, replace API key, or remove internal headers |
| `preprocessResponse(...)` | Response recorded into snippets | Mask `Set-Cookie`, returned tokens, or internal identifier headers |

Only process the side that contains data needing protection. If a secret exists only in the request, there is no need to apply the same rule to the response; if the response contains cookies/session tokens, process the response separately.

## 3. Header Processing Strategies

There are four common options. Choose based on the documentation's goal.

| Strategy | How It Works | Result |
| --- | --- | --- |
| Replace pattern value | Use `replacePattern(...)` to replace sensitive parts | Header still appears; value is masked or replaced with a placeholder |
| Replace entire header value | Use a header-value replacement preprocessor if provided by your API/version | Keeps header name, replaces value |
| Remove specific headers | Use `removeHeaders(...)` | Header is removed from the recorded exchange |
| Remove headers by pattern | Use `removeMatchingHeaders(...)` | Headers whose names match the pattern are removed |

For API documentation, **replacing the value is often more useful than removing the header** when readers need to know the header must be sent. For example, `Authorization` may still need to appear in the sample request to show the `Bearer` scheme, while the token is replaced with a dummy value.

Removing a header is appropriate when the header does not belong in consumer-facing documentation at all, such as `X-Internal-Debug` or internal routing headers. Do not remove a required API header if the page needs to instruct clients to send it.

## 4. Replacing Sensitive Values While Keeping Header Names

### 4.1. Replacing a Token with a Placeholder

Example with MockMvc, using `replacePattern(...)` inside a request preprocessor:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

import java.util.regex.Pattern;

mockMvc.perform(get("/api/me")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-access-token")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("current-user",
        preprocessRequest(
            replacePattern(
                Pattern.compile("Bearer [^\\s]+"),
                "Bearer <REDACTED>"
            )
        ),
        requestHeaders(
            headerWithName(HttpHeaders.AUTHORIZATION)
                .description("Bearer access token; required for this endpoint")
        )
    ));
```

Here:

- The test still sends dummy credentials so the security layer can process the request.
- The request preprocessor replaces the token string in the content written to snippets.
- The `Authorization` name remains, so snippets still illustrate how authentication works.
- The `requestHeaders(...)` descriptor continues documenting the header.

Regular expressions must be tested against the credential format used by your project. The example above only illustrates a `Bearer` token value; API keys, Basic credentials, signatures, or custom schemes require matching patterns.

In Java source code, regex backslashes must be escaped in string literals. The sample pattern above illustrates matching the token portion after the `Bearer` scheme; replace it with another pattern if your project's credential format differs.

### 4.2. Using Dummy Values Right in the Test

Preprocessors are not an excuse to use production secrets in tests. Prefer:

```java
.header(HttpHeaders.AUTHORIZATION, "Bearer documentation-test-token")
```

Then replace it with a placeholder in snippets if that value does not need to be shown:

```text
Authorization: Bearer <REDACTED>
```

If a dummy token can be used to access a shared test environment, still treat it as a credential: restrict permissions, lifetime, and usage scope. Never commit an active token into a repository merely because it is called a test token.

## 5. When Should Headers Be Removed?

### 5.1. Removing Specific Headers

If a header serves only internal purposes and should not appear in documentation:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

document("orders-get",
    preprocessRequest(
        removeHeaders("X-Internal-Tenant", "X-Debug-Route")
    )
)
```

These headers are removed from the request written to snippets. Make sure they are not part of the public contract that consumers must send.

### 5.2. Removing Headers by Pattern

When there is a group of internal headers following a clear naming convention, you can use `removeMatchingHeaders(...)`:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeMatchingHeaders;

document("orders-get",
    preprocessRequest(
        removeMatchingHeaders("X-Internal-.*", "X-Debug-.*")
    )
)
```

Patterns must be narrow enough not to accidentally remove public headers like `X-Request-Id` or custom headers clients need to know about. Before applying pattern-based rules, review the set of headers that can appear in tests.

### 5.3. Be Careful with Authorization

If the endpoint documentation needs to tell clients they must authenticate, do not remove `Authorization` and merely write "token required" in prose if the request snippet is expected to illustrate the full call. Replace the value to keep:

```http
Authorization: Bearer <REDACTED>
```

If a public endpoint does not require authentication or the header does not belong in the example, removal may be appropriate. The decision depends on what the documentation page needs to communicate.

## 6. Handling Response Headers and Cookies

A response may contain a session cookie:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: session=opaque-session-value; HttpOnly; Secure; Path=/
X-Request-Id: req-9281

{"id":"user-42","name":"Lan"}
```

If the API page does not need cookie values, you can remove `Set-Cookie` from the response snippet:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

document("login",
    preprocessResponse(removeHeaders("Set-Cookie"))
)
```

If you want to keep the information that the server issues a cookie without revealing its value, use a value-replacement approach suited to `Set-Cookie` content and inspect the output. Do not combine multiple `Set-Cookie` headers into a single comma-separated string; each cookie is a separate field value and the `Expires` attribute can contain commas.

For `X-Request-Id`, if the value changes on every run while the header name matters, you can replace it with a stable placeholder using a preprocessor. This makes snippets easier to review and avoids giving the false impression that the sample ID is always fixed.

## 7. Keeping Descriptors When Preprocessing

A common pitfall: preprocessors are applied to the exchange before REST Docs generates snippets. Therefore, if you **remove** a header before snippet generation while still declaring a descriptor for that exact header, the descriptor may no longer find the corresponding header.

Bad example if you want to document `Authorization`:

```java
document("current-user",
    preprocessRequest(removeHeaders("Authorization")),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token")
    )
)
```

The header has been removed from the processed request, yet the descriptor still requires documenting it. The test may fail because the header is no longer in the exchange observed by REST Docs.

If you need to keep the header in the table, replace its value instead of removing it:

```java
document("current-user",
    preprocessRequest(
        replacePattern(
            Pattern.compile("Bearer [^\\\\s]+"),
            "Bearer <REDACTED>"
        )
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token; required")
    )
)
```

If the header does not need to be published, you can remove it and omit its descriptor. Ensure prose still thoroughly describes other authentication requirements if the endpoint enforces them.

## 8. Preprocessing Request and Response in the Same Test

A single request/response may require processing on both sides:

```java
document("current-user",
    preprocessRequest(
        replacePattern(
            Pattern.compile("Bearer [^\\\\s]+"),
            "Bearer <REDACTED>"
        ),
        removeHeaders("X-Internal-Tenant")
    ),
    preprocessResponse(
        removeHeaders("Set-Cookie"),
        replacePattern(
            Pattern.compile("req-[A-Za-z0-9-]+"),
            "req-<ID>"
        )
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token")
    ),
    responseHeaders(
        headerWithName("X-Request-Id")
            .description("Response tracing ID")
    )
)
```

This example illustrates combining preprocessors; adjust regexes to match actual formats and retain headers that have descriptors. If the response contains `X-Request-Id` and the replacement pattern turns the entire value into `req-<ID>`, the descriptor still documents the right header while the snippet no longer exposes a specific ID.

Do not apply an overly broad regex across the entire exchange if it might erase or alter unrelated JSON values, URIs, or headers. Prefer narrow rules and test with predictable mock data.

## 9. Changing Structured Values and Other Sensitive Cases

### 9.1. API Keys in Custom Headers

Example:

```http
X-Api-Key: live-key-value
```

If the header is an integration requirement, keep the name and replace the value:

```java
preprocessRequest(
    replacePattern(
        Pattern.compile("live-key-value"),
        "<REDACTED>"
    )
)
```

In practice, use dummy fixtures or a pattern following the key structure; do not rely on a literal string that might change without anyone noticing.

### 9.2. User or Tenant Identifiers

Headers like `X-Tenant-Id` and `X-User-Id` may be part of an internal API's contract or merely metadata injected by a gateway. Decide carefully:

- If consumers must send it, keep the name and use a dummy value like `tenant-demo`.
- If an internal header is added by a gateway, usually remove it from consumer-facing snippets.
- If a value is needed to explain behavior, replace it with a meaningful placeholder rather than a real value.

Do not assume every `X-`-prefixed header is secret or internal. Determine ownership and intended users for each header.

### 9.3. Correlation IDs

Correlation IDs are often helpful in operational docs, while API documentation may only need to state that the response provides a tracing ID. You can replace a random value with a fixed illustrative ID:

```http
X-Request-Id: req-example
```

If clients need to pass this ID to support teams, state clearly that the header is returned in the response and should be saved when reporting issues.

## 10. Verifying That Preprocessors Actually Work

Do not just look for green tests. Open the snippets after tests run and verify:

| Artifact | What to Check |
| --- | --- |
| `http-request.adoc` | No real tokens/API keys; public headers still appear |
| `request-headers.adoc` | Descriptors still cover all selected headers |
| `http-response.adoc` | Cookie/session values and internal IDs have been processed |
| `response-headers.adoc` | Only headers within documentation scope remain |
| Final Asciidoctor page | No sensitive data appears via another include |

Some preprocessors apply across multiple snippets generated from the same operation. Therefore, when changing rules, inspect HTTP exchanges, header tables, and body snippets if tests generate them.

### 10.1. Testing Data-Masking Patterns

Create dummy values structured like real data without real access privileges, for example:

```text
Bearer documentation-only-token-123
```

After running tests, search within the generated snippets directory to confirm:

- The original fixture string does not appear.
- The expected placeholder appears.
- The header name still appears if it needs to be published.
- Unrelated parts remain intact.

This is a safe artifact check that can be automated in CI. Never feed real secrets into tests just to prove that a regex masks them.

## 11. Build and CI

Preprocessing is part of snippet generation, so it is typically verified when documentation tests run:

```mermaid
flowchart TD
    A[HTTP test using dummy fixtures] --> B[Behavior assertions]
    B --> C[Request/response preprocessors]
    C --> D[Generate snippets]
    D --> E[Verify artifacts contain no secrets]
    E --> F[Asciidoctor or Markdown]
    F --> G[Review and store documentation]
```

A pipeline can perform:

1. Run documentation tests against dummy data.
2. Generate snippets into a clean output directory.
3. Search for known dummy secret strings to guarantee they do not appear in artifacts.
4. Verify required public headers remain present.
5. Render Asciidoctor/Markdown.
6. Review HTML/PDF and snippets before publishing.

Do not scan only `http-request.adoc`; secrets can appear in `http-response.adoc`, `curl-request.adoc`, body snippets, test logs, or other debug files. Check scope should cover all published artifacts.

## 12. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Authorization` descriptor cannot find header | `removeHeaders("Authorization")` removed the header before snippet creation | Replace the value instead, or omit the descriptor if the header is not published |
| Token still appears in snippet | Regex does not match real format or preprocessor is attached to the wrong side | Inspect actual request/response, pattern, and where it is applied |
| Response snippet still has session cookie | Only preprocessed request, not response | Process response using `preprocessResponse(...)` |
| Internal header still appears in output | Removal list does not cover that header | Inspect actual headers; add a narrow rule and test |
| Public header removed by mistake | Removal pattern too broad | Narrow pattern and verify header contract |
| Header name vanishes from HTTP request | Used remove instead of replace | Replace value with a placeholder when the header still needs illustration |
| `Set-Cookie` corrupted after processing | Merged cookies or misparsed commas | Keep each field value separate; handle cookies according to their own syntax |
| HTML is clean but raw snippets still contain secrets | Only checked rendered output, skipped snippets directory | Scan all artifacts before packaging |

## 13. Header Preprocessing Checklist

- [ ] Identify headers containing secrets, personal data, or internal metadata.
- [ ] Determine whether each header belongs to the contract clients need to know.
- [ ] Use replace/mask when you need to keep the header name; only remove when the header should not appear.
- [ ] Choose the right `preprocessRequest(...)` or `preprocessResponse(...)`.
- [ ] Ensure descriptors do not point to removed headers.
- [ ] Use dummy fixtures from the outset; never put production secrets in tests.
- [ ] Inspect HTTP snippets, header snippets, body snippets, and final artifacts.
- [ ] Confirm masked values cannot be recovered from logs or auxiliary files.
- [ ] Automate searching for original fixtures/secret markers in CI.

## 14. Practice Exercise

The `GET /api/profile` endpoint has:

- Request header `Authorization: Bearer ...`, required for authentication.
- Request header `X-Internal-Tenant`, added by a gateway and not part of the public contract.
- Response header `Set-Cookie`, containing a session cookie.
- Response header `X-Request-Id`, which clients can use when requesting support.

Perform the following:

1. Write a test using a dummy token and verify the profile status/body.
2. Use a request preprocessor to replace the `Authorization` value with `Bearer <REDACTED>` while keeping the header name.
3. Remove `X-Internal-Tenant` from the request snippet if consumer-facing documentation does not need it.
4. Use a response preprocessor to handle `Set-Cookie`; decide whether to keep a placeholder or remove it completely based on documentation page requirements.
5. Replace the random `X-Request-Id` with a stable sample value and keep the header in the response snippet.
6. Include request/response/header snippets in Asciidoctor.
7. Add a CI step searching all outputs for original fixture values and failing the build if they still appear.

**Self-check question:** If you have used `removeHeaders("Authorization")`, can you still declare `headerWithName("Authorization")` in `requestHeaders(...)` so the documentation table tells clients they must send a token? You should not. The preprocessor has already removed the header from the exchange used to generate snippets, so the descriptor may fail to match. When you want to both keep the header and hide its value, replace the value; if removing because it is unpublished, omit the corresponding descriptor and document security in the appropriate section.

## Conclusion

Preprocessing helps Spring REST Docs generate safe and stable snippets from HTTP exchanges. Use `preprocessRequest(...)` for requests and `preprocessResponse(...)` for responses; replace values when you need to keep header names in documentation, and remove headers when they fall outside consumer scope. Exercise extra caution with `Authorization`, API keys, `Cookie`, `Set-Cookie`, and internal identifiers. Because preprocessors alter the exchange observed by REST Docs, removing a header can prevent its descriptor from matching. Use dummy fixtures, inspect raw snippets and rendered pages, and automate artifact scanning in CI before publishing.
