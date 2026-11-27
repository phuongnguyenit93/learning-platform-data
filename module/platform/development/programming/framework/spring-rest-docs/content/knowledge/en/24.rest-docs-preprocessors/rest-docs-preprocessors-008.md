# Replacing Patterns in URIs or Bodies

Requests and responses recorded in Spring REST Docs may contain unstable or non-public values: internal hostnames, random ports, callback URLs, tokens in query strings, request IDs, timestamps, or fixture data. Including those values verbatim in snippets can make documentation hard to reuse, create constant diffs, or leak environment details. Operation preprocessors let you normalize the message copy used to generate snippets; `replacePattern(...)` is useful when you need to replace a text pattern with a stable value.

Choose the right processor based on where the data lives. `replacePattern(...)` processes message content matching a pattern; `modifyUris()` is for normalizing the scheme, host, and port of a request URI; `modifyHeaders()` fits replacing a specific header. Paths and query parameters have their own structure, encoding, and semantics. Never apply an overly broad regex across the entire message, as it can accidentally alter business IDs, API versions, or JSON syntax.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating request, response, payload, parameter, and header snippets, then authoring Asciidoctor/Markdown and integrating builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how `replacePattern(...)` works during the preprocessing step before snippet generation.
2. Distinguish body content replacement from request URI and response header normalization.
3. Write narrowly scoped regexes to replace tokens, timestamps, hostnames, or fixture data.
4. Preserve paths, query parameters, and body structures outside the replacement target.
5. Handle URL encoding, special characters, and non-matching pattern cases.
6. Combine preprocessors with assertions and descriptors without hiding API bugs.
7. Inspect raw snippets and rendered artifacts before publishing.

## 2. When Is Pattern Replacement Needed?

A recorded request/response might contain values difficult to use in documentation:

```text
GET http://localhost:53128/api/orders/42?traceId=run-98127 HTTP/1.1
Authorization: Bearer docs-test-token
Accept: application/json
```

The response might contain:

```json
{
  "id": 42,
  "createdAt": "2026-11-17T08:12:42.381Z",
  "callbackUrl": "https://node-17.internal:8443/callback?token=temporary-secret"
}
```

Documentation might need a stable example:

```json
{
  "id": 42,
  "createdAt": "2026-01-01T00:00:00.000Z",
  "callbackUrl": "https://api.example.test/callback?token=<callback-token>"
}
```

Common reasons: test environment host/port differs from published domain; random timestamps/request IDs cause snippets to change; query strings carry tokens or authorization codes; bodies contain private fixture data; callback URLs carry internal hostnames. Not every dynamic value should be replaced. If timestamp format, ID format, `ETag`, or query parameters are what you need to teach, preserve semantics and only replace specific data if needed.

## 3. replacePattern(...) Processes Message Content

Spring REST Docs provides the `replacePattern(Pattern, String)` API under operation preprocessors. It can be combined with `preprocessRequest(...)` or `preprocessResponse(...)` depending on the content to process.

Example replacing a trace ID in response content:

```java
.andDo(document("orders-get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("traceId=[A-Za-z0-9-]+"),
            "traceId=docs-trace-id"
        )
    )
));
```

The processor replaces content matching the pattern in the response copy used to generate snippets. It does not alter the response the controller returned to the test. Assertions still see the original message.

### 3.1. Request Body and Response Body

You can place processors on both sides:

```java
.andDo(document("orders-create",
    preprocessRequest(
        replacePattern(
            Pattern.compile("customer-\\d+"),
            "customer-demo"
        )
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("trace-[A-Za-z0-9-]+"),
            "trace-docs"
        )
    )
));
```

The request processor handles recorded request content; the response processor handles recorded response content. Only apply when you know the value lives in content and replacement will not break payload structure.

### 3.2. Combining with prettyPrint()

If you need to both replace values and format JSON, you can combine processors in the same branch. Order can affect output, so you must run tests and inspect post-processed snippets:

```java
.andDo(document("profile-get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("run-[0-9]+"),
            "docs-run"
        ),
        prettyPrint()
    )
));
```

If a pattern breaks JSON validity or transformation order does not give the expected output, fix the fixture/pattern or change processor order. Do not assume every combination is order-independent.

## 4. Narrowly Scoped Regexes

Suppose a body has:

```json
{
  "requestId": "req-783ad9",
  "status": "ACCEPTED"
}
```

You can replace strings with a matching format:

```java
replacePattern(
    Pattern.compile("req-[A-Za-z0-9-]+"),
    "req-docs"
)
```

This replaces every string in content matching `req-...`, not solely the `requestId` field. If multiple fields share the same format, regex could replace the wrong one. For complex bodies, fixed fixtures or a JSON-aware custom processor can be safer.

### 4.1. Avoiding Overly Broad Regexes

Do not use generic rules like replacing every alphanumeric string or every URI with a placeholder. Overly broad patterns can wipe out resource IDs, business enums, API versions like `/v1/`, query parameters that need documenting, or values needed to illustrate schemas.

Before using a regex, write down at least one input that must be replaced and one similar-looking input that must remain intact. Run tests for both to verify boundaries.

### 4.2. Capturing Groups and Replacements

When you need to preserve part of a string, use capturing groups. For example, keeping the `token` key while replacing only the value:

```java
replacePattern(
    Pattern.compile("([?&]token=)[^&\\s]+"),
    "$1<access-token>"
)
```

The first group preserves `?` or `&` and the parameter name; the value portion is replaced with a placeholder. Test with multiple query parameters, URL-encoded tokens, and cases where `token` is the last parameter. Java replacement strings have special rules for `$` and backslashes; escape appropriately if your replacement contains those characters.

## 5. URIs Are Not Bodies: Choose the Right Processor

A request URI consists of scheme, authority/host, port, path, query, and fragment. `replacePattern(...)` is not a URI parser. To normalize common request URI components, use the dedicated processor:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build()
    )
));
```

This configuration targets the scheme, host, and port of the recorded request URI. It does not define rules for replacing paths or query parameters.

### 5.1. Replacing Host/Port

If tests use `localhost` and a random port while documentation needs a canonical domain, `modifyUris()` is clearer than a message-wide regex. Paths and queries should be preserved:

```http
GET https://api.example.test/v1/orders/42?expand=items HTTP/1.1
```

The path `/v1/orders/42` and query `expand=items` remain part of the contract.

### 5.2. Replacing Paths or Query Parameters

Before replacing, determine which parameters are sensitive or mere test data; whether the key and position must stay in documentation; whether values are URL-encoded; whether duplicate parameter names exist; and whether `&`, `=`, `?`, `#` can appear inside encoded values.

If replacing only a query token, the regex must be scoped to that key's value. If you need to alter multiple URI components or parse complex queries, use a URI-aware custom request preprocessor matching your API version or construct safe URL fixtures from the start. Never replace the whole path if the path is the contract.

## 6. Links in Response Headers

`Location` or `Link` may contain internal hosts, callback URLs, or tokens. For a specific header, it is usually easier to control using `modifyHeaders()`:

```java
.andDo(document("orders-create",
    preprocessResponse(
        modifyHeaders()
            .set(
                "Location",
                "https://api.example.test/api/orders/42"
            )
            .build()
    )
));
```

The example uses a known full value. If the path has a dynamic ID, use deterministic fixtures or a URI-aware custom response processor; avoid hardcoding a sample ID that causes snippets to mismatch the test response.

A `Link` header can contain multiple URIs with `rel` parameters. A simple regex can break angle brackets or `next`/`prev` relations. For this structure, use fixed fixtures or an appropriate parser and inspect the header after processing.

## 7. Replacing URLs or Tokens in JSON/XML/Text Bodies

### 7.1. JSON Bodies

Example response:

```json
{
  "verificationUrl": "https://auth.internal/verify?token=secret-value",
  "status": "PENDING"
}
```

You can replace the hostname/token with a narrow pattern, but you must verify the result remains valid JSON. When you control the fixture, it is safer to construct test responses using dummy domains and tokens from the outset.

For complex JSON, a custom processor that parses JSON, replaces the exact field, and re-serializes is usually more reliable than a string-wide regex. You must preserve data types, escaping, arrays, and nested fields.

### 7.2. XML Bodies

Tokens can appear in text nodes or attributes:

```xml
<verification>
    <url>https://auth.internal/verify?token=secret-value</url>
</verification>
```

Regex can replace strings but does not understand namespaces, entities, or CDATA. For complex XML, use safe fixtures or an XML-parser-based processor to update the exact node/attribute.

### 7.3. Text Bodies

Plain text is better suited for `replacePattern(...)` when the format is simple:

```text
Request req-8912 failed validation
```

Can be normalized to:

```text
Request req-docs failed validation
```

You must still preserve error codes, transaction IDs, or public identifiers that readers need to understand.

## 8. Combining Request and Response Preprocessing

An operation can process both directions:

```java
.andDo(document("verification-create",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        replacePattern(
            Pattern.compile("trace-[A-Za-z0-9-]+"),
            "trace-docs"
        )
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("([?&]token=)[^&\\s]+"),
            "$1<verification-token>"
        ),
        modifyHeaders()
            .set(
                "Location",
                "https://api.example.test/verification/42"
            )
            .build()
    )
));
```

In this example, the request URI is normalized with `modifyUris`; request content is processed by a pattern if a matching string exists; response content replaces the token; response `Location` is replaced directly. Real configurations must place processors on the right side and verify the exact parts replaced.

## 9. Assertions and Descriptors Must Rely on the Real Contract

Preprocessors only transform the message copy used to generate snippets. Test assertions must verify the original response:

```java
mockMvc.perform(get("/api/verification/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("Location"))
    .andExpect(jsonPath("$.status").value("PENDING"))
    .andDo(document("verification-get",
        preprocessResponse(
            replacePattern(
                Pattern.compile("https://[^/]+/verify"),
                "https://api.example.test/verify"
            )
        ),
        responseFields(
            fieldWithPath("status")
                .description("Verification status")
        )
    ));
```

This example shows assertions verifying real status, while the preprocessor replaces the URL in the recorded copy. If `Location` or the verification URL has the wrong path, the test must catch it; never write a regex that rewrites a wrong path into an expected one.

Descriptors such as `requestParameters`, `responseFields`, `requestHeaders`, or `responseHeaders` document the contract. Do not let descriptors describe a URL different from raw snippets or handwritten prose.

## 10. Reviewing and Verifying Snippets After Replacement

After tests run, inspect all files for the identifier, not just one snippet:

```text
target/generated-snippets/verification-create/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
├── response-headers.adoc
└── response-fields.adoc
```

The actual list depends on descriptors. Verify internal hosts/ports are replaced in the right places; tokens/secrets are gone from URLs/queries/bodies; public paths, API versions, and query parameters remain accurate; `Link` preserves `rel` relations; JSON/XML remain valid; business IDs were not accidentally altered; cURL/HTTPie and HTML/PDF also retain no old values.

If sensitive values have already entered artifacts or repositories, fixing new snippets is not enough; handle old artifacts and credentials according to your organization's security procedures.

## 11. Common Errors and Troubleshooting

| Symptom | Cause | Solution |
| --- | --- | --- |
| Request host is still `localhost` | Only used `replacePattern` on body or wrong attachment point | Use `preprocessRequest(modifyUris(...))` |
| Host in `Location` unchanged | Mistakenly thought `modifyUris` processes response headers | Use a response header processor |
| Token remains in query | Regex did not cover actual key/encoding | Review key, encoding, and test pattern |
| Next query parameter lost | Greedy or unbounded regex | Bound value up to ampersand/whitespace |
| Path/API version replaced | Pattern too broad | Narrow replacement scope, preserve contract path |
| `Link` header corrupted | Regex did not preserve multi-link/`rel` syntax | Use fixed fixture or custom parser |
| Invalid JSON | String replacement broke escaping | Validate JSON; prefer dummy data |
| Business ID changed | Multiple values matched the same regex | Narrow pattern or use deterministic fixture |
| Assertion passes but snippet is wrong | Reviewed only output, ignored contract | Assert on real message and review snippets separately |
| HTML/PDF still has old URL | Scanned only one file or stale artifact | Clean, re-render, and scan all artifacts |

## 12. Best Practices

1. Use dummy URL/token fixtures from the start; pattern replacement is an extra normalization layer.
2. Choose processors by location: `modifyUris` for request URIs, `modifyHeaders` for headers, `replacePattern` for content.
3. Scope regexes narrowly and test both matching and non-matching cases.
4. Preserve paths, API versions, and query parameters with business meaning.
5. Watch out for URL encoding, delimiters, fragments, and capturing groups.
6. Use parser-aware processors when JSON/XML/`Link` is complex; regex is not a structural parser.
7. Assertions verify real requests/responses; preprocessors only change the snippet record.
8. Descriptors and handwritten prose must align with post-processed examples.
9. Inspect HTTP, cURL, HTTPie, header/body snippets, and rendered artifacts.
10. Run a clean build and scan secret/link patterns in CI before publishing.

## 13. Practice Exercise

Create a documentation test for `POST /api/verifications`. The response contains `Location` with an internal host, JSON with `verificationUrl` and a random query token, plus a dynamic `requestId`. Documentation needs an example host, a token placeholder, and a stable ID.

**Tasks:**

1. Create dummy request/response fixtures; do not use real tokens.
2. Assert status, `Location` path, verification status, and request ID on the original response.
3. Use `modifyUris` to normalize request URI host/port if needed.
4. Use `modifyHeaders` or a suitable processor to replace the `Location` host.
5. Use `replacePattern` with a narrow pattern to replace the token in the body.
6. Normalize the dynamic request ID if it is not the contract focus.
7. Verify JSON remains valid and public query parameters stay intact.
8. Include raw response, response headers, and response fields in AsciiDoc.
9. Scan snippets and HTML/PDF to ensure no internal tokens/hosts remain.
10. Run a clean build to confirm documentation regenerates from current tests.

**Completion criteria:** sensitive hosts and tokens are not exposed; links keep accurate path/query semantics; bodies are valid; assertions verify real responses; descriptors and snippets are consistent.

## 14. Takeaways

- `replacePattern(Pattern, String)` replaces pattern-matching content in the message copy used to generate snippets.
- `modifyUris()` is specialized for normalizing scheme/host/port of recorded request URIs.
- `modifyHeaders()` fits replacing a specific header like `Location`; do not assume it handles every URL in the body.
- Paths/queries must preserve semantics; regexes must be scoped and account for URL encoding.
- For complex JSON/XML/`Link`, safe fixtures or structure-aware processors are more reliable than broad regexes.
- Assertions check real messages; preprocessing only normalizes the documentation record.
- Review all derived snippets and rendered artifacts before publishing.
