# Combining Multiple Preprocessors in Order

A request or response recorded in Spring REST Docs may need multiple normalization steps before generating snippets. A request may need `Authorization` replaced with a placeholder, `Cookie` removed, and the host normalized; a response may need JSON formatted, internal headers stripped, and a dynamic request ID replaced. These operations are combined within the same operation, and **processor order matters**: each step operates on the result of the previous step, so one step can alter or remove data that the next step needs to process.

Spring REST Docs lets you pass multiple operation preprocessors via `preprocessRequest(...)` and `preprocessResponse(...)`. The list of processors within a branch is applied in configured order. To keep the processing pipeline maintainable, determine the final output, order transformations by data dependencies, run tests, and read actual snippets to verify.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests with MockMvc, WebTestClient, or REST Assured, generating request, response, payload, parameter, and header snippets, then authoring Asciidoctor/Markdown and integrating builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why multiple preprocessors need to be combined in a single operation.
2. Order request and response preprocessor chains deliberately.
3. Recognize dependencies among removing headers, modifying headers, replacing patterns, normalizing URIs, and formatting bodies.
4. Distinguish processor order within one branch from independent request and response processing.
5. Design reusable helpers for processing chains while still allowing customization.
6. Verify actual output without hiding assertion failures or corrupting API semantics.
7. Check snippets and builds to detect unintended ordering changes.

## 2. Why Does Processor Order Matter?

Consider this sequence of operations:

1. Replace `Authorization` with a placeholder.
2. Remove `Cookie` from the request.
3. Normalize the URI.
4. Write request snippets.

If you delete `Cookie` first and then try to replace the `Cookie` value, the replacement step has no data left to process. Similarly, if a pattern alters the body before pretty printing, formatting applies to the modified content. Order determines the snippet result.

### 2.1. Sequential Processing Model

```text
Recorded message
        │
        ▼
Preprocessor A
        │
        ▼
Message after A
        │
        ▼
Preprocessor B
        │
        ▼
Message after B
        │
        ▼
Preprocessor C
        │
        ▼
Final message
        │
        ▼
Snippet generation
```

Each processor operates on the current result of the chain. Later processors cannot see data removed by earlier processors unless the earlier processor replaced it with another value.

### 2.2. Choosing Order by Dependency

Before writing the chain, ask: which steps need a header or text segment to still exist; which steps delete data and should run after replacements; should body formatting run before or after replacements; does any processor alter content so it no longer matches the next step's pattern?

A practical rule of thumb is to run transformations that depend on original data first, deletions afterward, and verify final formatting. This is a design guideline, not an absolute rule: exact order must be based on the actual data and processors.

## 3. Combining Processors in Requests

A request might need URI normalization, credential replacement, and removal of non-public headers:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-Correlation-Id", "docs-correlation-id")
            .build(),
        removeHeaders("Cookie", "X-Internal-Trace"),
        prettyPrint()
    )
));
```

This chain performs: normalizing scheme/host/port of the request URI; replacing `Authorization` and correlation ID in the request copy used for snippets; removing `Cookie` and trace headers; formatting the request body if an eligible body exists.

Configuration should match the actual contract. If `Cookie` belongs to the API contract and clients must know how to send it, do not remove it just to shorten snippets. If a correlation ID can be omitted, tests and descriptors must document that condition.

### 3.1. Replacing a Header Before Removing Headers

If you want to keep the `Cookie` header name while replacing its value with a placeholder, replace it and do not remove that same header:

```java
preprocessRequest(
    modifyHeaders()
        .set("Cookie", "SESSION=<session-cookie>")
        .build(),
    removeHeaders("X-Internal-Trace")
)
```

If `Cookie` is removed first, a later replacement step has no header left to process. Conversely, if the goal is to eliminate `Cookie` completely, simply remove it and skip replacing a value for that header.

### 3.2. URI Processor and Content Replacement

`modifyUris()` handles request URI components such as scheme, host, and port. `replacePattern(...)` replaces pattern-matching content in the message. If you only want to change the request URI host, prefer the URI processor instead of a message-wide regex.

You can combine both steps when the request also has dynamic strings in the body:

```java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.test")
        .removePort()
        .build(),
    replacePattern(
        Pattern.compile("trace-[A-Za-z0-9-]+"),
        "trace-docs"
    ),
    prettyPrint()
)
```

The pattern is only an example. Confirm the string to replace lives inside request content and does not collide with other business IDs. For complex JSON, stable fixtures or a JSON-aware processor may be better than regex.

## 4. Combining Processors in Responses

A response might need body formatting, dynamic value replacement, and removal of non-public metadata:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build(),
        removeHeaders("Set-Cookie", "X-Internal-Node"),
        replacePattern(
            Pattern.compile("run-[0-9]+"),
            "docs-run"
        ),
        prettyPrint()
    )
));
```

This example chain replaces the request ID, removes cookies and internal headers, normalizes dynamic `run` strings, and finally formats the body. If a pattern needs to target a request ID inside the body rather than a header, configure the right content scope. Do not treat `replacePattern(...)` and `modifyHeaders()` as interchangeable APIs.

### 4.1. Replace Then Remove vs. Remove Then Replace?

| Goal | Processing Chain |
| --- | --- |
| Replace header with placeholder and keep name | Modify header; do not remove the same header |
| Completely strip header from snippets | Remove header; no need to modify value |
| Replace value then remove header from snippets | Only needed if an intermediate step depends on the value; usually reconsider design |
| Keep public header, remove internal header | Modify public header; remove internal header |

Avoid configuring a chain that replaces a header with a placeholder and immediately deletes that very header without a specific reason. The final output will not contain the placeholder, making the replacement step redundant.

## 5. Order Between Pattern Replacement and Pretty Print

For bodies, the order of pattern replacement and formatting can make a difference.

### 5.1. Replace First, Format Later

When a pattern needs to match strings on a compact body, you can replace first and then pretty-print:

```java
preprocessResponse(
    replacePattern(
        Pattern.compile("trace-[A-Za-z0-9-]+"),
        "trace-docs"
    ),
    prettyPrint()
)
```

The pattern can match the single-line body directly; afterward, `prettyPrint` makes the body readable.

### 5.2. Format First, Replace Later

If the pattern is written to match the formatted structure, you can format first. However, regexes on JSON tend to be brittle when whitespace, newlines, or field order change. Prefer patterns less sensitive to whitespace or custom JSON-aware processors.

There is no single always-correct order. Choose based on the real input each processor receives and inspect final snippets.

### 5.3. Non-JSON Content

For XML, plain text, or bodies where whitespace carries meaning, pretty print may not be appropriate. If a body contains signatures, signed payloads, or strings where individual bytes/whitespace matter, do not format merely to make snippets look prettier.

## 6. Request and Response Are Two Independent Chains

Both branches can be declared in the same operation:

```java
.andDo(document("verification-create",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build(),
        removeHeaders("Cookie")
    ),
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build(),
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        replacePattern(
            Pattern.compile("([?&]token=)[^&\\s]+"),
            "$1<verification-token>"
        ),
        prettyPrint()
    )
));
```

Processors in the request chain only process the recorded request; processors in the response chain only process the recorded response. Declaring both branches does not mean the last request processor continues running on the response. Keep rules aligned with message direction so reviewers know which side is being normalized.

## 7. Assertions Still Verify the Real Message

Preprocessors are attached during documentation, not as a replacement for assertions:

```java
mockMvc.perform(get("/api/orders/{id}", 42L)
        .header("Authorization", "Bearer docs-test-token"))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get",
        preprocessResponse(
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build()
        )
    ));
```

The test confirms that the real response has the request ID and the right order ID. Post-processed snippets show the sample request ID. If the real response lacks the header, assertions must fail; preprocessors must never inject a fake header to make tests pass.

Never rewrite error statuses into success, insert missing fields, fix wrong resource IDs, or mask data-leaking responses using a processor chain. Those practices destroy the verifiable value of REST Docs.

## 8. Designing Reusable Helpers

When many tests share the same policy, you can package request/response processors into separate helpers. Example:

```java
static OperationRequestPreprocessor publicRequestPreprocessor() {
    return preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build(),
        removeHeaders("Cookie")
    );
}
```

```java
static OperationResponsePreprocessor publicResponsePreprocessor() {
    return preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build(),
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        prettyPrint()
    );
}
```

Return types and imports should match your project's Spring REST Docs version. Keep separate helpers for requests and responses to avoid applying the wrong policy. If an operation has a different contract, allow custom helpers or per-operation processors.

### 8.1. Avoid Overly Generic Helpers

A public helper should not automatically delete every unrecognized header or replace all URLs in bodies. Overly broad rules easily corrupt examples for specialized operations. A good helper has a clear scope, an intent-revealing name, and readable steps.

## 9. Verifying Order via Output

Reading configuration is not enough to verify a processor chain. After tests run, inspect the snippets:

```text
target/generated-snippets/orders-get/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
├── response-headers.adoc
└── response-fields.adoc
```

Checklist:

- Placeholders appear on the right headers and test credentials are gone.
- Removed headers are genuinely absent from raw snippets.
- Host/port are normalized while path/query remain accurate.
- Patterns replaced only target values without altering business IDs.
- Bodies after `prettyPrint` remain valid and preserve semantics.
- Descriptor tables match the processed raw request/response.
- cURL/HTTPie and HTML/PDF contain no stale data.
- Two clean builds with deterministic fixtures yield consistent output.

If output is wrong, adjust processor order or scope and re-run tests. Never edit generated snippets by hand because the next build will regenerate them.

## 10. Common Design Mistakes

| Configuration | Issue | Fix |
| --- | --- | --- |
| Remove header then modify same header | Header already deleted, no value left to replace | Modify first if keeping a placeholder; or only remove |
| Modify header then immediately remove | Modify step has no effect on final output | Remove redundant step or clarify goal |
| Token-replacing regex runs after header/body stripped | Content no longer exists for regex to match | Put replace before remove or use fixtures |
| Pretty print before regex that expects single-line string | Added whitespace breaks pattern match | Replace first or write whitespace-tolerant pattern |
| Regex runs across entire body | May accidentally alter business IDs/fields | Narrow pattern or use parser-aware processor |
| Using `modifyUris` to replace URLs inside JSON | Request URI processor does not handle all URLs in payloads | Use an appropriate body processor |
| Using the same chain for every operation | May drop headers belonging to another endpoint's contract | Split helpers and configure per operation |
| Treating snippets as assertion evidence | Normalized values may differ from real message | Assert on original response |
| Reviewing only `http-request` | Credentials may remain in cURL/HTTPie | Review all derived output |

## 11. Best Practices

1. Define the desired final output before choosing order.
2. Process data that must be kept or replaced before deleting it.
3. Only use `remove` when the goal is to omit headers from snippets.
4. Use URI processors for request URIs; use header/body processors for other locations.
5. Choose the order of pattern replacement and pretty print based on the content shape the pattern expects.
6. Narrow regexes and use fixtures/parsers when structure is complex.
7. Keep assertions on real requests/responses, independent of processed snippets.
8. Separate request chains and response chains; build narrowly scoped helpers.
9. Inspect all derived snippets and the final rendered output.
10. Run clean builds in CI to confirm the processor chain produces stable output.

## 12. Practice Exercise

Document the `POST /api/orders` endpoint. The test request uses a dummy Bearer token, a dummy `Cookie`, and a dynamic correlation ID. The response contains order JSON, a dynamic request ID, `Set-Cookie`, and `Location`. Documentation needs a sample host, placeholder token, stable IDs, readable JSON, and no `Cookie`/`Set-Cookie`.

**Tasks:**

1. Write a MockMvc documentation test and assert status, order ID, `Location`, and request ID on the real message.
2. Request chain: normalize URI; replace `Authorization` and correlation ID; remove `Cookie`.
3. Response chain: replace request ID; remove `Set-Cookie` and internal headers; format JSON after target values are processed.
4. Verify order by reading raw request and response snippets.
5. Confirm contract path/query remain unchanged.
6. Check request/response header descriptors match raw snippets.
7. Review cURL, HTTPie, and body/field snippets.
8. Extract dedicated helpers if a chain is reused.
9. Run clean tests twice and compare output to catch any leftover dynamic data.
10. Render Asciidoctor and inspect final artifacts.

**Completion criteria:** each chain processes the right direction; ordering has a clear rationale and output is verified; assertions protect real messages; snippets leak no credentials; contract and example data are consistent; builds regenerate stable output.

## 13. Takeaways

- Multiple preprocessors in the same branch run in configured order; each step processes the previous step's output.
- `preprocessRequest(...)` and `preprocessResponse(...)` form two independent chains for requests and responses.
- You cannot replace a header after removing it; avoid modifying then removing the same header unless an intermediate step requires it.
- The order of pattern replacement and pretty printing depends on the content format the pattern matches.
- Use `modifyUris()` for request URI components; use appropriate processors for response headers and bodies.
- Assertions check real messages; preprocessors only normalize the snippet record.
- Re-read raw HTTP, cURL, HTTPie, descriptors, and rendered docs to verify final output.
