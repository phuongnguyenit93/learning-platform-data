# Preprocessing Responses Before Snippet Generation

The response returned by an application in an HTTP test is evidence of API behavior. Spring REST Docs records the response and generates snippets such as `http-response`, response headers, and response fields. However, the initial message may contain a random request ID, session cookies, internal headers, a test-environment hostname, or a body with fixture data that should not be disclosed. **Response preprocessing** normalizes the response copy that REST Docs uses to generate snippets, making examples readable, consistent, and safe.

Preprocessors only alter the response copy used for documentation. The test still receives the original response, and assertions still verify actual status, headers, and body. Therefore, never use preprocessing to make an invalid response look valid or to hide unsafe application behavior.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module practices creating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating request, response, payload, parameter, and header snippets, then authoring Asciidoctor/Markdown and integrating builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Locate response preprocessing in the test → assertion → document → snippet chain.
2. Use `preprocessResponse(...)` to apply `OperationResponsePreprocessor`.
3. Format JSON/XML response bodies, remove or replace response headers, and normalize dynamic values.
4. Distinguish the real response from the response copy processed for documentation.
5. Keep descriptors, raw snippets, and explanatory prose consistent with the API contract.
6. Handle sensitive data and environment metadata before publishing snippets.
7. Inspect related response files and integrate into builds/CI.

## 2. Where Does Response Preprocessing Fit?

```text
Prepare fixtures and test client
             │
             ▼
Send HTTP request to the application
             │
             ▼
Application processes and returns real response
             │
             ▼
Test receives response and runs assertions
             │
             ▼
Call document(identifier, ...)
             │
             ▼
preprocessResponse(...)
             │
             ▼
REST Docs generates snippets from processed response
             │
             ▼
Asciidoctor / Markdown includes snippets into documentation
```

In MockMvc, the documentation hook is typically inside `andDo(document(...))`. Response processors are passed via `preprocessResponse(...)`. With WebTestClient and REST Assured, the recorder attachment APIs differ, but the principle is the same: processors act on the recorded response copy before snippet generation.

### 2.1. Real Response vs. Response Used for Documentation

Suppose the application returns:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: req-9b7c21
Set-Cookie: SESSION=test-session-9281
X-Internal-Node: app-node-03

{"id":42,"status":"PAID","updatedAt":"2026-11-17T02:14:51.492Z"}
```

Public documentation might need:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: docs-request-id

{
  "id": 42,
  "status": "PAID",
  "updatedAt": "2026-11-17T00:00:00Z"
}
```

The server still returns the original response to the test. The second version is only the post-processed example. If an assertion verifies that `X-Request-Id` exists, it must check the original response, not rely on the `docs-request-id` value substituted into the snippet.

### 2.2. Reasons to Normalize Responses

Unstable or sensitive values can make documentation less useful:

- Request IDs, trace IDs, and timestamps change on every run.
- `Set-Cookie` contains a session identifier or refresh token.
- Debug headers or hostnames reveal internal infrastructure.
- JSON contains personal data or customer data from fixtures.
- Absolute URLs depend on the test machine's hostname/port.
- Compact bodies are hard to read in guide pages.

Response preprocessing handles these cases at a clear point before snippet files are written.

## 3. preprocessResponse(...) and OperationResponsePreprocessor

Spring REST Docs provides APIs in the `org.springframework.restdocs.operation.preprocess` package. `preprocessResponse(...)` accepts one or more response processors and creates a composite processor to attach to the documented operation.

Example:

```java
.andDo(document("orders-get",
    preprocessResponse(prettyPrint())
));
```

`OperationResponsePreprocessor` is the abstraction that processes an `OperationResponse` and returns a processed response. Common built-in helpers include `prettyPrint()`, `removeHeaders(...)`, `modifyHeaders()`, and `replacePattern(...)`.

Illustrative static imports:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

Exact names and builder signatures must match the Spring REST Docs version managed in your project.

## 4. Formatting the Response Body

### 4.1. JSON with prettyPrint()

Compact JSON response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"name":"Notebook","active":true}
```

Attach `prettyPrint()` to the response processor:

```java
.andDo(document("products-get",
    preprocessResponse(prettyPrint())
));
```

The snippet will include indentation and line breaks for easier reading:

```json
{
  "id": 42,
  "name": "Notebook",
  "active": true
}
```

Pretty-printing only changes presentation. It does not check schemas, verify field types, or strip sensitive data. Assertions and descriptors must still be declared separately.

### 4.2. XML Responses

Example XML response:

```xml
<order><id>42</id><status>PAID</status><total>189000</total></order>
```

If the processor and content type support XML formatting in your version, snippets can become more readable:

```xml
<order>
    <id>42</id>
    <status>PAID</status>
    <total>189000</total>
</order>
```

Read the actual snippet to verify encoding, namespaces, and content remain accurate. For XML with whitespace-sensitive content, do not assume reformatting is harmless.

### 4.3. Text and Binary Responses

With plain text, whitespace and newlines may carry meaning, so leaving them intact can be appropriate. With binary responses, images, or streams, do not try to put binary payloads into text snippets. Instead, document relevant metadata such as media type, content length, or download behavior, and use appropriate illustrative examples.

Do not apply pretty-printing blindly to every response body. Check the content type, semantics, and documentation goal before applying it.

## 5. Removing Response Headers That Should Not Be Public

`removeHeaders(...)` removes headers from the response copy written to snippets:

```java
.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Node")
    )
));
```

This is appropriate when session cookies or internal headers do not belong in public API documentation. It only removes headers from the snippet record; the response the application sent to the test still contains those headers.

If the server is returning an internal header that should not be exposed to real clients, evaluate the implementation and fix the application if needed. Preprocessors are not a runtime security fix.

### 5.1. Do Not Remove Headers Clients Need to Understand

Some response headers are part of the contract:

- `Content-Type` indicates the media type.
- `Location` may point to the URI of a newly created resource.
- `ETag` may serve as a validator for conditional requests.
- `Cache-Control` publishes caching policy.
- `Retry-After` may guide when to retry.

Do not remove these headers if clients need to understand their semantics. If values fluctuate or contain private data, replace them with safe sample values while keeping the header name and explaining the behavior accurately.

## 6. Replacing Response Header Values with Sample Data

### 6.1. Normalizing Request IDs

Request IDs often differ across test runs. If readers only need to know that the response returns the header, you can replace it with a stable sample ID:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

Tests still assert that the `X-Request-Id` header exists or check its format on the real response. Snippets show a stable value to avoid noisy diffs.

### 6.2. Preserving Meaningful Formats

If the format is part of the contract—for example, a correlation ID must be a UUID—the sample value should match that format:

```http
X-Correlation-Id: 123e4567-e89b-12d3-a456-426614174000
```

Do not replace with an arbitrary string if doing so contradicts client validation. The prose should note that this is a sample value, not an ID every request will receive.

### 6.3. Replacing Multiple Headers

You can use the same modifier to replace multiple values:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .set("X-Environment", "example")
            .build()
    )
));
```

Only replace headers for a clear reason. If `X-Environment` is not part of the client contract, removing it may be more appropriate than replacing its value.

## 7. Normalizing Dynamic Data in Response Bodies

Response bodies may contain timestamps, UUIDs, callback URLs, or fixture identifiers. `replacePattern(...)` can replace content matching a regular expression in the response copy used for snippets.

Conceptual example replacing a UTC timestamp with a stable value:

```java
.andDo(document("orders-get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}Z"),
            "2026-01-01T00:00:00.000Z"
        )
    )
));
```

The pattern illustrates a UTC timestamp with milliseconds; real code must check escaping, timestamp format, and API version. Apply only to responses where the target location is well understood. A generic regex can accidentally replace business timestamps or strings in other fields.

### 7.1. When to Replace vs. When to Keep

| Data Type | Suggested Handling | Reason |
| --- | --- | --- |
| Runtime-generated timestamp | Replace with a fixed value if exact time is not the focus | Stable snippets |
| Random test ID | Use a fixed fixture or replace with a sample ID | Focus on schema |
| Monetary values, business states | Keep valid representative values | These are response semantics |
| Real customer emails/names | Use dummy data or anonymize | Protect personal data |
| Environment-dependent URLs | Replace hostname with an example domain | Environment-independent docs |
| `ETag` | Keep needed format/semantics or use sample validator | Clients need to understand conditional requests |

Do not normalize away values that are the very content you are trying to teach. For instance, a lesson on currency needs meaningful amounts/currencies; a lesson on timestamps may need to preserve format and timezone even when replacing the specific instant.

## 8. Combining Multiple Response Processors

A response may need body formatting, cookie removal, and ID normalization:

```java
.andDo(document("orders-get",
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie", "X-Internal-Node"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

In this example, `prettyPrint` makes the body readable; `removeHeaders` removes non-public metadata; `modifyHeaders` replaces the dynamic ID with a stable example.

### 8.1. Processor Order

Transformation order can affect the result. If you remove a header first, a later processor no longer has that header to replace. If you edit content before formatting, the formatter applies to the edited content.

Order steps according to your goal, run the test, and read the final response snippet. Verify with your actual Spring REST Docs version.

## 9. Response Preprocessing and Assertions

**Assertions verify the real response; preprocessors normalize the response copy written to snippets.**

Example:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.status").value("PAID"))
    .andDo(document("orders-get",
        preprocessResponse(
            prettyPrint(),
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build()
        )
    ));
```

Assertions run on the response returned by the application. Then the recorder writes the processed response into snippets. If the real response lacks a request ID, the test fails; the preprocessor must never fabricate a header to make a test pass.

Do not use response processors to turn error statuses into success, insert missing required fields, overwrite wrong business values with expected ones, remove required headers to bypass descriptors, or hide implementation leaks.

## 10. Response Descriptors and Raw Snippets

Response preprocessing and descriptors have distinct roles:

| Component | Role |
| --- | --- |
| `preprocessResponse(...)` | Transforms the response used to generate snippets |
| `responseHeaders(...)` | Documents response headers belonging to the contract |
| `responseFields(...)` | Documents the response body structure |
| `http-response.adoc` | Raw response example after preprocessing |
| `response-headers.adoc` | Response header descriptor table |
| `response-fields.adoc` | Response field descriptor table |

Example:

```java
.andDo(document("orders-create",
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI of the newly created order"),
        headerWithName("X-Request-Id")
            .description("Correlation ID for tracing the request")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Order ID"),
        fieldWithPath("status")
            .description("Current status")
    )
));
```

The raw response snippet has the normalized ID and no `Set-Cookie`; the header table explains `Location` and `X-Request-Id`; the body fields table documents the JSON. Descriptors must reflect the contract and must not document a removed header as if it appeared in the raw message.

## 11. Inspecting Response Snippets After Preprocessing

One operation can generate multiple files:

```text
target/generated-snippets/orders-get-success/
├── http-response.adoc
├── response-headers.adoc
├── response-fields.adoc
└── ...
```

After the test, inspect:

- Status and body in `http-response.adoc` still match the contract.
- Sensitive headers like `Set-Cookie` have been removed or safely replaced.
- Request IDs/timestamps have the intended sample values.
- `response-headers.adoc` documents only contract headers.
- `response-fields.adoc` accurately reflects fields and semantics.
- No personal data or real fixture data appears in the body.
- Final HTML/PDF does not retain stale artifacts containing sensitive data.

Do not read only descriptor tables; the raw response is where undocumented headers can leak.

## 12. Differences Across Test Clients

Response preprocessing principles are the same across MockMvc, WebTestClient, and REST Assured, though where the recorder attaches differs:

| Test Client | Documentation Hook | Notes |
| --- | --- | --- |
| MockMvc | `andDo(document(...))` | Configure MockMvc with Spring REST Docs |
| WebTestClient | REST Docs filter/configuration in exchange | Use the WebTestClient module and corresponding API |
| REST Assured | REST Docs filter in request specification | Attach processor to the recorded operation |

Do not copy MockMvc syntax to other test clients. Use the corresponding adapter and document/filter API to pass response preprocessors to the operation recorder.

## 13. Common Errors and Troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Set-Cookie` remains in response snippet | Response processor not attached or wrong header name removed | Check processor and raw snippet |
| Request ID changes every build | Dynamic value not normalized | Use fixed fixture or `modifyHeaders` |
| JSON stays compact | `prettyPrint` not attached to the right operation or body/content type mismatch | Check response content type and snippet |
| Required header disappears | Overly broad removal | Keep contract headers, only replace values if needed |
| Assertion passes but snippet shows different value | Confused post-processed record with real response | Check assertions and snippets separately |
| Example body has wrong semantics | Regex replaced the wrong field | Narrow the pattern and inspect output |
| Descriptor does not match raw response | Header absent or removed by processor | Align descriptors/processors with the contract |
| Internal hostname still appears | URLs in response not handled | Use appropriate response processor or fixture |
| HTML still shows old data | Not re-rendered from fresh snippets | Clean build and check fresh artifacts |
| Personal data still appears | Only cleaned headers, skipped body | Use dummy fixtures and sanitize body snippets |

## 14. Best Practices

1. Use response preprocessors for responses; do not confuse them with request preprocessors.
2. Assert status/headers/body on the real response before generating snippets.
3. Use `prettyPrint` to improve readability, not as validation.
4. Remove `Set-Cookie` and internal headers only when they do not belong in public API docs.
5. Replace dynamic request IDs, timestamps, and hostnames with stable sample values when appropriate.
6. Do not alter business fields that clients need to understand.
7. Keep descriptors consistent with the processed response and contract explanations.
8. Review raw responses, header/field snippets, and HTML/PDF output.
9. Use safe fixtures from the start; preprocessors are an additional safeguard.
10. Run clean tests before rendering in CI to avoid stale output.

## 15. Practice Exercise

Document the `GET /api/orders/{id}` endpoint. The real response contains order JSON, a request ID that changes on each test run, `Set-Cookie` from middleware, and an internal header. Documentation needs readable JSON, a stable sample request ID, and no exposed cookies or internal headers.

**Tasks:**

1. Write a MockMvc documentation test and assert status, ID, and order status.
2. Assert that the response has a request ID on the real message.
3. Use `preprocessResponse(prettyPrint())` for JSON.
4. Use `removeHeaders(...)` to remove `Set-Cookie` and internal headers not belonging to the contract.
5. Use `modifyHeaders()` to replace the dynamic request ID with a sample value.
6. Declare response headers and response fields matching the contract.
7. Run the test and inspect raw response, `response-headers`, and `response-fields` snippets.
8. Confirm sensitive fixture data is no longer in snippets.
9. Include snippets in an AsciiDoc page.
10. Run a clean build and review the final HTML/PDF output.

**Completion criteria:** real response is asserted; response snippets are intentionally formatted and normalized; non-public headers are not leaked; descriptors match the contract; documentation renders from fresh snippets.

## 16. Takeaways

- Response preprocessing transforms the response copy used to generate snippets; it does not modify the response returned by the application to the test.
- `preprocessResponse(...)` attaches one or more `OperationResponsePreprocessor` instances to the documented operation.
- `prettyPrint()` formats bodies; `removeHeaders(...)` removes headers from snippets; `modifyHeaders()` replaces header values; `replacePattern(...)` normalizes pattern-matching content.
- Assertions check real status, headers, and body; preprocessors do not replace assertions.
- Response descriptors explain headers/fields; raw response snippets show the post-processed message.
- Never use processors to hide contract bugs or implementation leaks.
- Review response snippets and rendered artifacts, then run clean builds in CI.
