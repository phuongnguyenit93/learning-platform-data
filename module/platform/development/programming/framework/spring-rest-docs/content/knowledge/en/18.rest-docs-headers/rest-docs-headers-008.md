# Sensitive Header Values Should Not Be Included Verbatim in Documentation

Spring REST Docs records requests and responses to generate snippets such as `http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, and `httpie-request.adoc`. These files are helpful to API integrators, but they can also introduce sensitive data into documentation if tests send or receive real values. An `Authorization` header may contain a bearer token; `Set-Cookie` may carry a session identifier; internal headers may reveal tenants, personal identifiers, or operational details.

Therefore, **never include raw sensitive values in public documentation or published artifacts**. Use dummy fixtures, intentional placeholders, appropriate preprocessors, and output reviews. Masking data must be done deliberately to protect information while preserving the necessary meaning of HTTP examples.

This lesson belongs to the **Headers** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates snippets for requests, responses, payloads, parameters, and headers, and compiles them with Asciidoctor/Markdown into builds and CI. This lesson focuses on identifying sensitive headers, strategies to avoid recording real data, sanitizing output, and checking snippets for leaks.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify headers containing credentials, sessions, personal data, and internal information.
2. Explain why raw HTTP snippets can expose values even when the descriptor table does not list the header.
3. Distinguish data that should be removed, data that can be replaced with placeholders, and metadata that can be retained.
4. Design safe test fixtures instead of real secrets.
5. Use Spring REST Docs preprocessors to remove or replace header values in snippets.
6. Inspect request, response, cURL, HTTPie, and rendered artifacts.
7. Incorporate sensitive-data checks into reviews and CI.

## 2. Why Do Sensitive Headers Easily Leak into Documentation?

A test sends a request, receives a response, and calls `document(...)`. Raw snippets can contain the recorded request line, headers, and body. For example:

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=8f4...
X-Internal-User: user-1042
Accept: application/json
```

Even if `requestHeaders(...)` only documents `Accept`, the raw `http-request.adoc` can still display the other headers. **Descriptor tables and raw HTTP snippets serve different purposes**: descriptors select which headers to explain; raw snippets can show the entire message.

Risks also appear in `http-response.adoc` (`Set-Cookie`, refresh tokens), `curl-request.adoc` and `httpie-request.adoc` (commands containing credentials), body snippets (personal data), descriptor tables, and rendered HTML/PDF/site outputs. Never assume that omitting a header from the description table automatically hides it from raw snippets.

## 3. Identifying Header Groups That Need Protection

| Header or Group | Risk | How to Handle |
| --- | --- | --- |
| `Authorization` | Bearer token, Basic credentials, or other schemes | Do not use real values; replace with a placeholder |
| `Proxy-Authorization` | Credentials sent to a proxy | Do not publish |
| `Cookie` | Session ID, login state | Remove or replace with a placeholder |
| `Set-Cookie` | Session token, refresh token, cookie flags | Do not include real cookies in examples |
| API keys such as `X-API-Key` | Service access key | Use a dummy placeholder |
| CSRF header/token | Session-bound token | Use only dummy values |
| Headers containing email/user ID/tenant | Personal data or identifiers | Anonymize or use dummy data |
| Internal trace/debug headers | Hostname, topology, or operational metadata | Keep only essential parts that have been reviewed |
| Request/correlation ID | May link to internal logs | Use sample IDs, not real IDs |
| `Content-Type`, `Accept` | Usually not secrets | Can be kept if they do not expose private context |

Secrets and personal data are not the same thing. Credentials can be used to access systems; personal data might not grant login access but still must not be published. Operational metadata is sometimes not a secret, yet it can reveal system structure. Therefore, checks should not just look for token-shaped strings.

### 3.1. Classifying Handling Approaches

- **Keep as-is:** only when the value belongs to the public contract and is safe, such as `Content-Type: application/json`.
- **Replace with placeholder:** when you need to show position/format without needing the real value, such as `Authorization: Bearer <access-token>`.
- **Partially mask:** only when the remaining portion cannot be used for identification/access and remains useful.
- **Remove:** internal headers unnecessary for clients or carrying disclosure risk.
- **Avoid generating sensitive data from the start:** prefer dummy fixtures so real secrets never enter recorded messages.

## 4. Prefer Dummy Fixtures from the Start

The safest measure is not putting real secrets into documentation tests. If a test must authenticate to pass a security filter, use a dummy token valid only in the test environment.

```http
GET /api/orders/501 HTTP/1.1
Authorization: Bearer docs-test-token
Accept: application/json
```

Or in reader-facing guides:

```http
GET /api/orders/501 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
```

`docs-test-token` must be a dummy value with no access to real environments. Placeholders simply illustrate where clients must supply their own credentials.

Do not read production secrets from environment variables into documented requests:

```java
String token = System.getenv("PRODUCTION_ACCESS_TOKEN");
mockMvc.perform(
    get("/api/profile").header("Authorization", "Bearer " + token)
);
```

This risks writing credentials into snippets, test reports, or logs. Use a test principal, mock authentication, or a token signed with a test-environment-only key.

If a test only verifies that a tokenless request returns `401`, there is no need to send `Authorization`. When illustrating an authenticated request, use a dummy token or placeholder. You can have two separate operations: `orders-get-unauthenticated` and `orders-get-authenticated`.

## 5. Spring REST Docs Preprocessors

Spring REST Docs supports operation preprocessors to transform requests/responses recorded into snippets. Common APIs in `org.springframework.restdocs.operation.preprocess.Preprocessors` include:

- `preprocessRequest(...)` and `preprocessResponse(...)`: apply processors to the message.
- `removeHeaders(...)`: remove headers you do not want in snippets.
- `modifyHeaders()`: modify headers in the recorded message.
- `replacePattern(...)`: replace content matching a regular expression.
- `prettyPrint()`: format payloads for readability.

Choose handling by goal: remove headers unnecessary for clients; replace values when the header name belongs to the contract but the real value is sensitive.

### 5.1. Removing Headers That Should Not Be Public

Example removing `Cookie` and an internal header from the request snippet:

```java
.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Cookie", "X-Internal-User")
    )
));
```

If the response contains a `Set-Cookie` that should not be displayed:

```java
.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie")
    )
));
```

This operates on **the message copy recorded as a snippet**. It does not strip headers from the actual request/response and does not fix leaks in the implementation. Assertions must still verify the real message.

### 5.2. Replacing Authorization with a Placeholder

If the header belongs to the contract and needs to appear in examples:

```java
.andDo(document("orders-get-authenticated",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    )
));
```

Builder syntax must match your project's Spring REST Docs version. Security assertions still run against the request sent with the initial dummy token; the preprocessor only alters the message used to write snippets. Make sure placeholder values are not accidentally interpreted as AsciiDoc markup; inspect the final output.

### 5.3. Normalizing Dynamic Correlation IDs

If an ID changes on every run but documentation only needs to show the header:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Correlation-Id", "docs-correlation-id")
            .build()
    )
));
```

The test still needs assertions confirming that the response includes an ID or meets the contract format. The snippet uses a stable sample value. If format is part of the contract, use a dummy value in the right format, such as a sample UUID.

### 5.4. Using replacePattern with Narrow Bounds

`replacePattern(...)` is useful when sensitive strings appear inside header values or messages—for example, a callback URI containing temporary query parameters. Regexes must be tightly scoped; overly broad patterns can accidentally alter valid data or make snippets stop representing the request. After running tests, read the snippet file to verify replacements worked correctly.

## 6. Masking Values Differs from Removing Headers

| Approach | Snippet Result | When Appropriate |
| --- | --- | --- |
| Remove header | Header disappears from raw message | Internal headers that clients do not need instructions for |
| Replace value | Keeps header name, replaces with placeholder | Header belongs to contract but real value must not be published |
| Partial mask | Preserves general format, hides sensitive portion | When format matters and the remaining portion is safe |
| Use dummy fixtures | Message contains only test data | Preferred option |
| Omit descriptor | No separate description table | Not a security measure |

**Omitting `requestHeaders(...)` or `responseHeaders(...)` does not hide a header.** Descriptors determine the description table; fixtures and preprocessors determine what raw snippets record. Removing a header from the table while leaving it in `http-request.adoc` can still expose credentials.

## 7. End-to-End Example with MockMvc

Suppose `GET /api/profile` requires a dummy Bearer token and returns a correlation ID. The test uses the application's security setup, yet snippets contain no test token:

```java
@Test
void getProfile_documentsSafeHeaders() throws Exception {
    mockMvc.perform(
            get("/api/profile")
                .header("Authorization", "Bearer docs-test-token")
                .header("X-Correlation-Id", "test-flow-001")
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(header().exists("X-Correlation-Id"))
        .andDo(document("profile-get-success",
            preprocessRequest(
                modifyHeaders()
                    .set("Authorization", "Bearer <access-token>")
                    .set("X-Correlation-Id", "docs-correlation-id")
                    .build()
            ),
            preprocessResponse(
                removeHeaders("Set-Cookie", "X-Internal-Trace")
            ),
            requestHeaders(
                headerWithName("Authorization")
                    .description("Client's Bearer access token"),
                headerWithName("X-Correlation-Id")
                    .description("Correlation ID that the client may provide")
            ),
            responseHeaders(
                headerWithName("X-Correlation-Id")
                    .description("ID used to trace the processing request")
            )
        ));
}
```

This is an example combining descriptors and preprocessors; cross-check imports and builder APIs against your project's Spring REST Docs version. The test must include the security filter chain if it is meant to prove authentication. `docs-test-token` is a dummy fixture with no privileges in real environments.

### 7.1. Assertions Must Verify the Real Message

Preprocessors only affect the snippet copy. Tests need assertions on the actual request/response:

```java
.andExpect(status().isOk())
.andExpect(header().exists("X-Correlation-Id"))
.andExpect(jsonPath("$.id").value("profile-demo"))
```

If the contract requires the server to echo back the exact ID sent by the client, assert equality. If the server generates a new ID, assert the header and proper format. Never treat a placeholder value after preprocessing as proof that the server returned that exact value.

### 7.2. Inspect All Generated Snippets

```text
target/generated-snippets/profile-get-success/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
└── response-headers.adoc
```

The file list depends on descriptors. During review, verify that `Authorization` shows only a placeholder or was removed; `Cookie`/`Set-Cookie` contains no real sessions; correlation IDs use stable dummy values; no unintended internal headers appear; and cURL and HTTPie snippets were processed as well.

## 8. Do Not Forget Derived Snippets

| File | What to Inspect |
| --- | --- |
| `http-request.adoc` | `Authorization`, `Cookie`, API keys, identifier headers |
| `curl-request.adoc` | Copy-pasteable tokens/cookies |
| `httpie-request.adoc` | Credentials embedded in commands |
| `http-response.adoc` | `Set-Cookie`, refresh tokens, trace headers |
| `request-headers.adoc` / `response-headers.adoc` | Descriptors accidentally containing sensitive values |
| Body snippets | Personal data or credentials inside JSON/XML |

If you have custom snippets or a Markdown conversion pipeline, add them to your inspection checklist. Final HTML/PDF outputs can also retain values that appeared in snippets.

## 9. Writing Safe Header Descriptions

Do not put tokens in descriptions:

```java
headerWithName("Authorization")
    .description("Bearer access token issued to the client by the authentication mechanism")
```

Do not put real tenants or customer names in descriptions:

```java
headerWithName("X-Tenant-Id")
    .description("Tenant ID that the client is authorized to operate on")
```

Descriptors are also saved into snippets and may be published, so apply the same data protection principles as for raw messages.

## 10. Security Checks in CI

A pipeline can perform:

```text
Clean build output
       │
       ▼
Run documentation tests with fake credentials
       │
       ▼
Generate request/response snippets
       │
       ▼
Scan snippets for known secrets / forbidden patterns
       │
       ▼
Render Asciidoctor / Markdown
       │
       ▼
Review HTML/PDF and generated artifacts
       │
       ▼
Publish
```

Useful checks:

1. Scan for known secret values or credential patterns used by the organization.
2. Inspect `Authorization`, `Cookie`, `Set-Cookie`, API keys, and trace/debug headers.
3. Inspect raw snippets, descriptor tables, cURL, and HTTPie snippets.
4. Inspect rendered output because conversion can copy content into HTML/PDF.
5. Publish only after scans and reviews pass.

Pattern scanning cannot detect every secret or piece of personal data. It is an additional defense layer, not a replacement for safe fixtures and output review.

### 10.1. If Real Credentials Have Already Been Committed or Published

Treat it as a credential exposure incident: halt publishing, identify the scope of exposed files/artifacts, revoke or rotate credentials if still active, remove/replace values in sources/snippets/artifacts per organizational procedures, inspect commit history and CI logs, and add controls to prevent recurrence. Simply deleting a token from the latest file does not revoke an already-leaked credential.

## 11. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Header table does not mention token, but raw request has token | Only omitted descriptor, did not sanitize raw snippet | Use dummy fixtures and request preprocessors |
| Test token appears in cURL | Only checked `http-request` | Inspect all derived snippets |
| `Set-Cookie` remains in response snippet | Response headers not sanitized | Use response preprocessor or safe fixtures |
| Placeholder breaks auth test | Confused preprocessor with request sent to server | Keep assertions on the real message; replace only in snippets |
| Header disappears even though clients need to know it | Used remove instead of replace | Keep header name, replace value with a placeholder |
| Correlation ID changes every build | Dynamic value recorded verbatim | Use fixed ID or preprocessor |
| Internal header still appears | Only excluded from descriptor | Sanitize raw snippets and review implementation |
| Regex replaces wrong values | Pattern too broad | Narrow regex and test output |
| CI scan passes but secret still leaks | Pattern does not cover all data forms | Combine fixtures, reviews, and artifact checks |
| HTML/PDF still contains token | Stale artifacts or not re-rendered | Clean, regenerate, and scan new artifacts |

## 12. Practice Exercise

Document `GET /api/accounts/me`. The API requires a Bearer token, accepts an optional correlation ID, and response middleware may include `Set-Cookie`.

**Tasks:**

1. Create a security test using a dummy token with permissions valid only in tests.
2. Send `Authorization: Bearer docs-test-token` and `X-Correlation-Id: docs-flow-001`.
3. Assert authentication behavior and response according to the contract.
4. Use `requestHeaders(...)` to describe `Authorization` and correlation ID in prose without writing any token into descriptions.
5. Use a request preprocessor to replace `Authorization` with `Bearer <access-token>` and normalize the correlation ID.
6. Use a response preprocessor to remove `Set-Cookie` if cookies do not belong to the public example.
7. Generate request, response, cURL, HTTPie, and header snippets.
8. Search the entire output for the original fixture value; confirm the token does not appear.
9. Render HTML/PDF and inspect the artifacts.
10. Add corresponding scan/validation steps to CI.

**Completion criteria:** tests still verify real requests/responses with dummy fixtures; snippets contain only safe placeholders or omit unnecessary headers; no real credentials appear in raw snippets, tables, or rendered documentation; the pipeline can reproduce and verify outputs.

## 13. Key Takeaways

- Raw HTTP snippets can record headers even when those headers do not appear in `requestHeaders(...)` or `responseHeaders(...)`.
- Never use real tokens, cookies, API keys, or credentials in documentation tests; prefer dummy fixtures from the outset.
- `removeHeaders(...)` drops headers from snippets; `modifyHeaders()` can replace values with placeholders; `prettyPrint()` only formats messages.
- Preprocessors modify the message copy used to write snippets, not assertions on actual requests/responses.
- Inspect `http-request`, `http-response`, cURL, HTTPie, header tables, and rendered HTML/PDF.
- CI scanning is a supporting layer; safe fixtures, reviews, and artifact checks remain essential.
- If real credentials are exposed, handle it as a security incident and rotate/revoke credentials as appropriate.
