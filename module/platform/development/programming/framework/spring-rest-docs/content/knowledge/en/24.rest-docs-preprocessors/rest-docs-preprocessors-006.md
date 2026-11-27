# Masking Links to Remove Hosts or Tokens

HTTP snippets may contain full URLs so readers can understand or retry requests. However, links recorded in test environments can carry internal hostnames, random ports, private callback URLs, or tokens embedded in query strings. Responses may return a `Location` header pointing to the test machine, or a body containing a temporary verification link. Publishing these links as-is can leak environment topology, produce non-reusable documentation, or inadvertently publish credentials.

In Spring REST Docs, you can **mask or normalize links in the message copy used to generate snippets**. For request URIs, `modifyUris()` can normalize the scheme, host, and port. For URLs inside headers/bodies or tokens embedded in query strings, you can use `modifyHeaders()` or `replacePattern(...)` to replace values with safe samples. These changes only affect the documentation record; the actual request/response and test assertions remain unchanged.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module practices creating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating request, response, payload, parameter, and header snippets, then authoring Asciidoctor/Markdown and integrating builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify internal hosts, random ports, callback URLs, and tokens embedded in links.
2. Distinguish normalizing request URIs from masking URLs in headers/bodies.
3. Use `modifyUris()` to replace scheme/host/port in request snippets.
4. Use `modifyHeaders()` and `replacePattern(...)` to clean links or tokens in messages.
5. Write narrowly scoped replacement rules that preserve path/query semantics needing disclosure.
6. Verify assertions on real messages and review all derived snippets.
7. Integrate link and secret review steps into builds/CI.

## 2. Why Mask Hosts or Tokens in Links?

A URL can contain multiple components:

```text
https://internal-api.example.local:53128/api/auth/callback
    ?tenant=tenant-test
    &access_token=eyJhbGciOi...
    &state=5f3c...
```

| Component | Risk or Impact | Handling in Documentation |
| --- | --- | --- |
| Scheme | Shows how clients connect | Keep faithful to contract; only change if canonical URL is needed |
| Host | Reveals private hostname or is unusable outside test env | Replace with agreed documentation domain |
| Port | May be a test random port | Remove or normalize if not part of contract |
| Path | Usually identifies endpoint and route | Keep intact if part of API contract |
| Regular query parameter | May contain tenant/filter/business state | Keep structure; use dummy data if private |
| Token/secret | May grant access or continue an auth flow | Remove or replace with placeholder |
| Fragment | May contain state or client-side data | Inspect before publishing |

Not every long URL is sensitive. The host may need to be kept if it is an official public domain; query parameters may be part of the contract that must be documented. Determine what readers must understand versus what is purely test-environment or credential data.

## 3. Identifying Where Links Appear

| Location | Example | Processing Approach |
| --- | --- | --- |
| Request URI | GET to `localhost` and random port | Request URI preprocessor |
| `Host` header | `localhost:53128` | Normalize URI/host per API |
| Response `Location` | `http://app-node:8080/api/items/42` | Replace response header or normalize link |
| Response `Link` | Next/prev page URLs | Preserve `rel` and path, replace host |
| JSON body | `verificationUrl` containing token | Response body processor |
| HTML/text body | Confirmation or callback link | Replace exact URL, keep remaining content |

`modifyUris()` primarily adjusts the recorded request URI. Do not assume it will find and replace every URL in the response body, `Location`, or `Link`. For those locations, use appropriate response/header/body processors and inspect output snippets.

## 4. Normalizing Request URIs with modifyUris()

When request snippets record `localhost` or a random port, `modifyUris()` helps create stable example URIs:

```java
.andDo(document("items-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build()
    )
));
```

In snippets, scheme/host/port are adjusted as configured. Path and query are preserved unless modified by another processor.

Use a fixed host when tests run locally with a random port, CI uses a container hostname different from developer machines, or public documentation needs a canonical domain. Only use an agreed illustrative domain; if documentation must be copy-pasteable for live execution, use a confirmed public base URL. Do not guess production domains.

### 4.1. Preserving Paths and API Versions

Normalizing the host must not corrupt paths, queries, or API versions. Example:

```http
GET https://api.example.test/v1/orders/42?expand=items HTTP/1.1
Accept: application/json
```

The path `/v1/orders/42` and query `expand=items` remain part of the contract. Do not shorten them just to make the URL look tidier.

## 5. Masking Hosts in Response Headers

Response headers that may contain URLs include `Location`, `Link`, `Content-Location`, or custom callback headers. Example of a real response:

```http
HTTP/1.1 201 Created
Location: http://orders-service.internal:8080/api/orders/42
Content-Type: application/json
```

If documentation needs to keep `Location` while replacing the host, you can replace the header value in a response preprocessor:

```java
.andDo(document("orders-create",
    preprocessResponse(
        modifyHeaders()
            .set(
                "Location",
                "https://api.example.test/api/orders/42"
            )
            .build()
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI of the newly created order")
    )
));
```

The example uses a known full value. If the path has a dynamic ID, use deterministic fixtures or a narrow replacement rule; avoid hardcoding a sample ID that causes snippets to mismatch the test response.

### 5.1. Link Headers with Multiple URIs

A `Link` header may contain multiple URLs and `rel` parameters like `next`, `prev`, `first`, or `last`. When masking the host, preserve angle brackets, relations, and parameters. Replacing the entire header with a single URL can lose pagination semantics.

If the structure is complex or contains multiple dynamic URLs, use deterministic fixtures or a custom response preprocessor specialized for `Link` syntax instead of a broad regex. Inspect output to confirm all links remain valid.

## 6. Masking Tokens in Query Strings

Tokens often appear in verification, password reset, invitation, or callback links:

```text
https://api.example.test/verify-email?token=eyJhbGciOiJIUzI1NiJ9.secret.signature
```

Never publish real tokens, even if expired. Use a placeholder:

```text
https://api.example.test/verify-email?token=<verification-token>
```

If the token is in a response header, you can replace the value with `modifyHeaders()`. If the token is in the body or URI text, you can use `replacePattern(...)` with a specific pattern.

Conceptual example replacing the `token` query parameter value in a response:

```java
.andDo(document("verification-link",
    preprocessResponse(
        replacePattern(
            Pattern.compile("([?&]token=)[^&\\s]+"),
            "$1<verification-token>"
        )
    )
));
```

The pattern replaces the value of the `token` query key up to the next ampersand or whitespace. Check escaping, encoding, and the actual response; if tokens are URL-encoded or contain special delimiters, adjust the pattern. When you control the fixture, prefer generating safe dummy tokens from the start.

### 6.1. Other Query Keys to Review

It is not just `token`. Links can contain `access_token`, `refresh_token`, `code`, `authorization_code`, `api_key`, `signature`, `state`, `nonce`, `ticket`, `session`, or `key`. Identify which keys can grant access or identify sessions and mask them according to agreed rules. Do not replace every parameter just because it has a generic name if it belongs to the contract and is non-sensitive.

Keys such as `email`, `userId`, `tenantId`, or `invitee` should also be evaluated since they can reveal personal data even when not credentials. Use dummy data or placeholders when specific values are unnecessary for the example.

## 7. Using replacePattern in a Controlled Way

`replacePattern(...)` is useful when the same pattern appears in the body or raw message. Good rules should:

1. Target the exact location to replace, such as the `token` query key.
2. Replace only the value, keeping the parameter name and neighboring parameters intact.
3. Not break URL encoding, `&`, `?`, fragments, or JSON.
4. Be tested with short tokens, long tokens, and URLs with multiple query parameters.
5. Be verified by reading post-processed snippets, not just relying on passing tests.

Conceptual example replacing a URL authority in response text:

```java
.andDo(document("callback-info",
    preprocessResponse(
        replacePattern(
            Pattern.compile("https?://[^/\\s]+"),
            "https://api.example.test"
        )
    )
));
```

This pattern only illustrates a simple URL authority. URLs with user-info, IPv6, ports, line breaks, or multiple URLs in a body require careful handling. When replacing hosts inside JSON, ensure string replacement does not break JSON escaping or structure.

### 7.1. When Regex Is Not Suitable

A simple regex is not a URI parser. When messages have many URLs, complex encoding, or multi-part `Link` syntax, consider:

- Using fixtures with well-formed dummy URLs.
- Using `modifyHeaders()` when replacing a single header.
- Writing a custom preprocessor using a proper URI API.
- Splitting operations if cases have different semantics.

The goal is to replace the exact sensitive portion without breaking link syntax or meaning.

## 8. End-to-End Example with MockMvc

Suppose the order creation endpoint returns `201`, `Location` has an internal host, and the body contains a payment link with a test token. The test uses dummy fixtures; documentation needs an example domain and placeholder:

```java
@Test
void createOrder_documentsSafeLinks() throws Exception {
    mockMvc.perform(
            post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":12,"productId":7,"quantity":2}
                    """)
        )
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"))
        .andExpect(jsonPath("$.paymentUrl").exists())
        .andDo(document("orders-create-success",
            preprocessResponse(
                modifyHeaders()
                    .set(
                        "Location",
                        "https://api.example.test/api/orders/42"
                    )
                    .build(),
                replacePattern(
                    Pattern.compile("([?&]token=)[^&\\s]+"),
                    "$1<payment-token>"
                )
            ),
            responseHeaders(
                headerWithName("Location")
                    .description("URI of the newly created order")
            ),
            responseFields(
                fieldWithPath("paymentUrl")
                    .description("Payment link provided by the API")
            )
        ));
}
```

This is an illustrative example; a test needs deterministic ID/link fixtures and a corresponding real response. Assertions must check the real response, such as verifying `Location` has the right resource path and the payment URL conforms to the contract. The preprocessor only replaces the host/token in snippets. If the ID varies, use a deterministic fixture or custom processor instead of hardcoding `/42`.

### 8.1. Inspecting Snippet Files

After the test, verify:

- `Location` uses the documentation domain with no internal hostname remaining.
- Path and API version remain accurate.
- The `token` query parameter contains only the placeholder.
- Other public query parameters still appear properly.
- The body remains valid JSON after replacing URLs/tokens.
- `response-headers.adoc` documents `Location` semantics.
- No tokens remain in other snippets or rendered output.

## 9. Choosing the Right Processor Side

| Target | Processing Approach | Notes |
| --- | --- | --- |
| Request URI host/port | `preprocessRequest(modifyUris()...)` | Normalizes request URI in snippets |
| `Authorization` request header | Request header modifier | Preserves scheme, replaces credential |
| Token in request URI | Suitable request processor or dummy fixture | Do not alter unrelated query parameters |
| `Location` in response | `preprocessResponse(modifyHeaders()...)` | Preserves resource path/semantics |
| `Link` in response | Response processor or custom processor | Preserves `rel` and each URI |
| URL in JSON response | Response `replacePattern` or custom processor | Preserves JSON/escaping |
| URL in text/HTML response | Appropriate response processor | Avoids altering non-link content |

Do not use a request preprocessor to process response headers; likewise, do not assume `modifyUris` automatically locates URLs in every body field.

## 10. Assertions, Descriptors, and Preprocessors

| Component | Role | Example |
| --- | --- | --- |
| Assertion | Verify URLs/tokens in real response against contract | Verify `Location` points to right resource |
| Preprocessor | Mask hosts/tokens in snippet record | Replace host and query token with placeholder |
| Descriptor | Explain headers/fields to integrators | Document `Location` or `paymentUrl` |

If the server returns `Location` with the wrong path, the test must fail even if the preprocessor replaces the host with the right domain. Never write a preprocessor that rewrites a wrong path into an expected path; that hides API bugs.

If documentation uses a `payment-token` placeholder, the description must explain that clients obtain tokens via the documented flow and how to use the link. Never let readers think the placeholder is a usable literal value.

## 11. Common Errors and Troubleshooting

| Symptom | Cause | Solution |
| --- | --- | --- |
| Request snippet still shows `localhost`/random port | Request URI not normalized | Use `modifyUris` in request preprocessor |
| Response `Location` still has internal hostname | Only used `modifyUris` for request | Process response headers separately |
| Token still exposed in URL | Regex did not cover actual key or encoding | Review key, fixture, and pattern |
| Replacing token drops next query parameter | Greedy/unbounded regex | Limit match up to ampersand/whitespace |
| Path replaced along with host | Pattern too broad | Use URI-aware processor or replace authority only |
| `Link` header broken | Regex did not preserve multi-link/`rel` syntax | Use deterministic fixture or custom parser |
| Invalid JSON | String replacement broke escaping | Validate JSON; prefer dummy data |
| Descriptors and raw snippet differ | Hardcoded ID/value does not match fixture | Use stable fixtures and thorough assertions |
| HTML/PDF still contains token | Only checked one snippet or stale artifact | Scan all snippets and perform clean re-render |
| Public host replaced even though needed | Over-masking | Only replace private environment hosts |

## 12. Best Practices

1. Prefer dummy URL/token fixtures; masking is an extra safety layer.
2. Distinguish request URIs from URLs inside response headers/bodies.
3. Use `modifyUris` to normalize request scheme/host/port when appropriate.
4. Use `modifyHeaders` for specific response headers such as `Location`.
5. Use `replacePattern` with narrow regexes for tokens in queries/bodies.
6. Do not replace business query parameters readers need to understand.
7. Preserve encoding, query delimiters, fragments, and `Link` syntax.
8. Assertions check real links; preprocessors only normalize the snippet record.
9. Review HTTP, cURL/HTTPie, header/body snippets, and HTML/PDF.
10. Run a clean build and scan URL/secret patterns before publishing.

## 13. Practice Exercise

Document the `POST /api/orders` endpoint. The response has `Location` containing an internal hostname and JSON containing `paymentUrl` with a dummy query token. Tests run on a random port.

**Tasks:**

1. Create a MockMvc documentation test with an order fixture and dummy token.
2. Assert status, `Location` path, resource ID in body, and payment URL against the contract.
3. Use request URI preprocessing if the request snippet shows `localhost`/random port.
4. Use a response preprocessor to replace the `Location` host with the documentation domain.
5. Use `replacePattern` or a custom processor to replace the query token in `paymentUrl` with a placeholder.
6. Keep paths and other public query parameters intact.
7. Include response header/body snippets in AsciiDoc.
8. Inspect HTTP, cURL/HTTPie, response headers, and body snippets.
9. Scan generated docs to confirm no internal hostname or fixture token remains.
10. Run a clean build and review final HTML/PDF before publishing.

**Completion criteria:** private environment hosts do not appear unnecessarily; tokens are not exposed; links keep paths, parameters, and semantics; assertions check real responses; snippets and final docs are consistent.

## 14. Takeaways

- URLs can appear in request URIs, `Location`, `Link`, `Content-Location`, or bodies; pick the processor for the right location.
- `modifyUris()` is useful for normalizing scheme/host/port of recorded request URIs.
- `modifyHeaders()` fits replacing specific response headers like `Location`.
- `replacePattern(...)` can mask tokens or hosts in raw messages, but regexes must be narrow and tested.
- Do not assume a request URI processor automatically handles URLs in response headers or payloads.
- Assertions check real links; preprocessors only transform the snippet record.
- Review derived snippets and rendered artifacts, not just a single HTTP file.
