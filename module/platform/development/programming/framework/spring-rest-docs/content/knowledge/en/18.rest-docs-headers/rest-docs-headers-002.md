# Documenting Response Headers with responseHeaders

An HTTP response consists of more than just a status code and a body. Headers also carry metadata so clients can understand the representation, trace requests, manage caching, locate newly created resources, or handle conditional updates. With **Spring REST Docs**, you document these headers using `responseHeaders(...)` and `headerWithName(...)`. The descriptors generate a header table snippet, helping readers understand which headers belong to the contract, what they mean, and under what conditions they appear.

This lesson belongs to the **Headers** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates snippets for requests, responses, payloads, parameters, and headers, and then compiles them with Asciidoctor/Markdown and integrates them into builds and CI. This lesson focuses on **response headers**: declaring descriptors, testing values, handling optional headers, generating snippets, and including the header table in API documentation.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of response headers for clients.
2. Use `responseHeaders(...)` combined with `headerWithName(...)` to generate a description table.
3. Distinguish between the raw HTTP response snippet and the header table generated from descriptors.
4. Combine assertions to verify important headers.
5. Document required and optional headers accurately according to the contract.
6. Handle dynamic, sensitive, or non-public headers.
7. Generate and include `response-headers.adoc` in Asciidoctor, and control snippet generation in CI.

## 2. Response Headers as Part of the HTTP Contract

An HTTP response has a status line, headers, and a body. Headers contain metadata about the representation or instructions for clients and intermediaries. For example:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/501
Cache-Control: no-store
ETag: "order-501-v1"
X-Request-Id: req-demo-001

{
  "id": 501,
  "status": "CREATED"
}
```

| Header | General Meaning | What the Client May Need to Do |
| --- | --- | --- |
| `Content-Type` | Representation type of the response | Choose the appropriate parser |
| `Location` | URI related to the new resource or redirect target | Use the URI to access the resource |
| `Cache-Control` | Caching directive | Follow the caching policy |
| `ETag` | Validator representing the representation | Send the validator in conditional requests if the API supports it |
| `X-Request-Id` | Correlation ID by service convention | Provide the ID when looking up logs or requesting support |

Not every endpoint returns all of these headers. `Location` is typically meaningful when creating a resource; `ETag` is useful if the API supports validators; `Cache-Control` depends on the caching policy. Documentation should only commit to headers that truly belong to the operation's contract.

### 2.1. Standard Headers and API-Specific Headers

`Content-Type`, `Location`, `Cache-Control`, `ETag`, and `Last-Modified` have widely known HTTP semantics. Custom headers such as `X-Request-Id` or `X-RateLimit-Remaining` need clearer explanation: who generates them, whether they always appear, what their format/unit is, whether the client needs to store or resend them, and whether values change across requests.

Do not just write "request ID" if the client needs to know that it is an opaque value, should not be parsed manually, or must be provided to support staff.

## 3. responseHeaders(...) and headerWithName(...)

Spring REST Docs provides the API for documenting response headers in `org.springframework.restdocs.headers.HeaderDocumentation`.

Basic structure:

```java
responseHeaders(
    headerWithName("Location")
        .description("URI of the newly created resource"),
    headerWithName("X-Request-Id")
        .description("Correlation ID of the response")
)
```

- `responseHeaders(...)` accepts a list of response header descriptors.
- `headerWithName("...")` creates a descriptor for a header by name.
- `description(...)` explains the meaning for readers.
- `optional()` marks a header that may be absent in the documented response.

When placed inside `document(...)`, Spring REST Docs generates a header table snippet, typically named `response-headers.adoc`.

Example in an operation:

```java
.andDo(document("orders-create-success",
    responseHeaders(
        headerWithName("Location")
            .description("URI of the newly created order"),
        headerWithName("X-Request-Id")
            .description("ID used to trace the processing request")
    )
));
```

A descriptor documents **which header exists and what it means**. It does not replace assertions that verify the header is present or has the right value. If the contract requires `Location` to point to the newly created order, verify that URI with a dedicated assertion.

Header names are case-insensitive according to HTTP semantics. In code and documentation, keep a consistent casing such as `Content-Type`, `Location`, `ETag`, and `Cache-Control` for readability.

## 4. Example: Documenting Response Headers for Resource Creation

Suppose `POST /api/orders` receives a valid request, creates an order, and returns:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/501
X-Request-Id: req-demo-001

{
  "id": 501,
  "status": "CREATED"
}
```

The test should assert the status, headers, and body, and then declare the descriptors:

```java
@Test
void createOrder_documentsResponseHeaders() throws Exception {
    mockMvc.perform(
            post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":12,"productId":7,"quantity":2}
                    """)
        )
        .andExpect(status().isCreated())
        .andExpect(header().string(
            "Location", "/api/orders/501"
        ))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(jsonPath("$.id").value(501))
        .andDo(document("orders-create-success",
            responseHeaders(
                headerWithName("Location")
                    .description("URI of the newly created order"),
                headerWithName("X-Request-Id")
                    .description("Correlation ID for tracing the response")
            )
        ));
}
```

This is an illustrative test excerpt; the project needs a controller/fixture that produces a deterministic response and a Spring REST Docs setup for MockMvc. Key static imports:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

Other imports such as `MockMvc`, `MediaType`, JUnit annotations, and REST Docs configuration are required. With WebTestClient or REST Assured, the way requests are sent and documentation configuration is attached differs from MockMvc, but response header descriptors keep the same meaning.

### 4.1. Assertions and Descriptors Have Different Responsibilities

| Component | What Is Verified / Generated |
| --- | --- |
| `status().isCreated()` | HTTP status is `201` |
| `header().string("Location", "/api/orders/501")` | `Location` value matches the fixture |
| `header().exists("X-Request-Id")` | Tracing header is present |
| `responseHeaders(...)` | Table describing header meanings in the snippet |

If you omit assertions, the test could record a response with an incorrect `Location` and still generate documentation. If you omit descriptors, the header may appear in `http-response.adoc` without having a dedicated header table. Use both to verify values and explain the contract.

### 4.2. Combining with Body and Request Descriptors

The same operation can document request fields, response headers, and response fields:

```java
.andDo(document("orders-create-success",
    requestFields(
        fieldWithPath("customerId").description("Customer ID"),
        fieldWithPath("productId").description("Product ID"),
        fieldWithPath("quantity").description("Quantity")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI of the new order")
    ),
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Initial status")
    )
));
```

This operation can generate `request-fields.adoc`, `response-headers.adoc`, `response-fields.adoc`, and the default HTTP snippets. Only declare descriptors for parts that are actually present and belong to the contract.

## 5. Required and Optional Headers

A header may only appear in certain responses. For example, `Location` appears in a `201` resource creation response but not in a `400` error response. Descriptors must accurately reflect the conditions under which a header is present.

### 5.1. Required Headers

If every successful response from `POST /api/orders` must contain `Location`, declare the header without `optional()`:

```java
responseHeaders(
    headerWithName("Location")
        .description("URI of the newly created order")
)
```

If the header is missing, documentation generation can fail. Add assertions for the value/format if that is an important commitment.

### 5.2. Optional Headers

If `X-Request-Id` may be absent according to the contract:

```java
responseHeaders(
    headerWithName("X-Request-Id")
        .description("Correlation ID if generated")
        .optional()
)
```

`optional()` allows the header to be absent in the documented operation without being treated as a missing required header. It does not mean the client must send this header in the request, nor does it mean every response is guaranteed to contain it.

Do not use `optional()` just to make a test pass when the header is actually required to always appear. If the contract requires it, keep the descriptor required and add an assertion verifying the header.

### 5.3. Headers Present Only in One Response Type

Do not declare `Location` as required in a shared descriptor used for both success and error responses if it only exists on `201`. Create separate operations:

- `orders-create-success`: has `Location`.
- `orders-create-invalid`: does not have `Location`, only documents headers that actually appear.

Each operation has descriptors tailored to its own response. Avoid shared helper descriptors when header presence conditions differ.

## 6. Common Response Headers

### 6.1. Location

`Location` typically indicates the URI of a created resource or a redirect destination. With `201 Created`, this header helps clients identify the new resource. Documentation should clarify whether the URI is relative or absolute per API behavior, which identifier the path contains, and how clients should use it. If the value is an important part of the contract, assert it directly:

```java
.andExpect(header().string(
    "Location", "/api/orders/501"
))
```

Do not merely assert that the header exists if clients need to rely on that URI.

### 6.2. ETag and Last-Modified

`ETag` and `Last-Modified` can serve as validators to support caching or conditional requests. If the API supports `If-None-Match` or `If-Modified-Since`, explain the relationship: the client receives the validator, stores it per resource/representation, sends it back in a conditional request, and the server may return `304 Not Modified` when the condition holds.

Example descriptor:

```java
responseHeaders(
    headerWithName("ETag")
        .description("Representation validator used with If-None-Match"),
    headerWithName("Last-Modified")
        .description("Last modified timestamp in HTTP-date format")
)
```

Not every API returns both headers. Only document headers that the server actually returns and commits to. If validators change with data, test both data-change scenarios and conditional requests rather than only testing presence.

### 6.3. Cache-Control and Vary

`Cache-Control` describes the caching policy. `Vary` indicates which request headers affect the selected representation. For example:

```java
responseHeaders(
    headerWithName("Cache-Control")
        .description("Cache directive applied to the response"),
    headerWithName("Vary")
        .description("Request header affecting the representation")
)
```

If needed, explain directives such as `no-store` or `max-age` and their scope. The snippet table shows sample values; the explanation must state the committed policy.

### 6.4. Content-Type

`Content-Type` identifies the media type of the representation. For JSON APIs, responses typically use `application/json` or a JSON-suffixed media type. Documentation can state the returned media type, media-type versioning if used, and which parser the client needs to select.

`Content-Type` already typically appears in `http-response.adoc`. If a dedicated header table is needed, you must declare `responseHeaders(...)`; `response-headers.adoc` is not generated automatically just because the raw response contains that header.

### 6.5. Pagination and Rate Limiting

APIs may use `Link` headers for next/previous pages, `X-RateLimit-Limit` and `X-RateLimit-Remaining` for quotas, or `Retry-After` to suggest when to retry. Custom header names and semantics vary across APIs. You need to define the format, units, appearance conditions, and how clients should handle them; do not encourage blind tight retries based only on a sample value.

## 7. Dynamic and Sensitive Headers

Some response headers change across test runs: request IDs, trace IDs, timestamps, ETags, cookies, or environment-dependent metadata. Raw HTTP snippets may display recorded headers, so you must distinguish contractual headers from incidental headers added by a framework, proxy, or container.

Do not include sensitive values in public documentation unless there is a safe purpose:

- `Set-Cookie` containing session identifiers.
- Tokens or authentication credentials.
- Internal headers revealing identities, topology, or infrastructure.
- Trace metadata that could expose operational details.
- Values tied to personal data.

Use dummy fixtures and preprocessors to remove or replace necessary values before writing snippets. Filtering snippets does not replace fixing the real response if the implementation is leaking data.

### 7.1. Normalizing Dynamic Values

You can use `preprocessResponse(prettyPrint())` to format the response cleanly:

```java
.andDo(document("orders-create-success",
    preprocessResponse(prettyPrint()),
    responseHeaders(
        headerWithName("Location")
            .description("URI of the newly created order"),
        headerWithName("X-Request-Id")
            .description("Correlation ID of the response")
    )
))
```

`prettyPrint()` only formats the content; it does not automatically replace dynamic request IDs. If you need to normalize headers, use a replacement preprocessor appropriate for your Spring REST Docs version and verify that the final snippet contains no real data. Assertions must check the original response; do not use preprocessors to mask wrong statuses or headers.

### 7.2. Should Every Header Be Documented?

No. Only select headers that clients need to read or resend, headers affecting caching/redirects/conditional requests/retries, or headers exposed by the API as part of its interface. Unstable infrastructure headers with no contract commitment should not be included in the contract table; raw response snippets should also be reviewed to avoid misleading readers.

## 8. Generating and Reading response-headers.adoc

When a test calls `responseHeaders(...)`, Spring REST Docs creates a header table snippet for the corresponding identifier, typically `response-headers.adoc`.

Example output:

```text
target/generated-snippets/
└── orders-create-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    ├── response-headers.adoc
    └── response-fields.adoc
```

The table may look like:

| Header | Description |
| --- | --- |
| `Location` | URI of the newly created order |
| `X-Request-Id` | Correlation ID for tracing the response |

Detailed structure depends on templates and versions. `response-headers.adoc` is the descriptor table; `http-response.adoc` is the HTTP example with actual headers and body. One file explains the headers, while the other shows how those headers appear in an example.

Common reasons `response-headers.adoc` is missing: the test did not declare `responseHeaders(...)`, the test did not reach `document(...)`, the descriptor was attached to a different identifier, or the test failed before writing snippets. Do not include this file for every operation if the test does not generate it.

## 9. Embedding the Header Table in Asciidoctor

In an AsciiDoc file, place the headers section right after the response example:

```asciidoc
=== Create order

Send a valid request to create a new order.

==== Response

include::{snippets}/orders-create-success/http-response.adoc[]

==== Response headers

The table below describes important headers that the client can use.

include::{snippets}/orders-create-success/response-headers.adoc[]

==== Response fields

include::{snippets}/orders-create-success/response-fields.adoc[]
```

The `{snippets}` attribute must point to the Spring REST Docs output directory, such as `target/generated-snippets` in Maven. For Markdown, a compatible conversion or snippet-inlining step is required; `include::{snippets}/...[]` is Asciidoctor syntax, not a built-in feature of every Markdown renderer.

## 10. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Header appears in raw response but no table exists | `responseHeaders(...)` was not declared | Add descriptors for headers belonging to the contract |
| `response-headers.adoc` does not appear | Test did not run or did not invoke descriptor | Check the test and operation identifier |
| Test fails due to missing header | Required descriptor used but response lacks header | Verify the contract; only use `optional()` if truly optional |
| Header is present with wrong value | Descriptors present, assertions missing | Add assertions for value/format |
| Shared descriptor used for success and error | Header only exists in one response type | Create separate operations |
| Table contains internal headers | Documenting all server headers | Select public headers and sanitize raw snippets |
| Snippet changes on every run | Dynamic request ID/timestamp | Use dummy fixtures or preprocessors |
| Asciidoctor cannot find include | Wrong identifier or output directory | Match `document(...)` with the snippets attribute |
| Raw snippet leaks cookie/token | Recording sensitive headers verbatim | Use dummy data, preprocessors, and inspect output |

## 11. Best Practices

1. Document only headers that belong to the contract; do not turn incidental proxy/container headers into API commitments.
2. Combine descriptors with assertions: descriptors explain, while assertions verify presence and values.
3. Use `optional()` only when a header can genuinely be absent.
4. Separate operations for different responses, such as `201` having `Location` and `400` not having it.
5. Explain semantics so clients know how to use `Location`, `ETag`, `Cache-Control`, `Retry-After`, or request IDs.
6. Normalize dynamic headers and remove sensitive data before publishing.
7. Check both raw responses and header tables to ensure consistency.
8. Wire snippet-generating tests before the rendering step in CI.

## 12. Practice Exercise

Document the `POST /api/orders` endpoint. When creation succeeds, the API returns `201 Created`, `Location`, `X-Request-Id`, and the order JSON. When the request is invalid, the API returns `400 Bad Request` with an error schema and no `Location`.

**Tasks:**

1. Write two separate HTTP tests: `orders-create-success` and `orders-create-invalid`.
2. In the success test, verify the status, the `Location` value, the presence of `X-Request-Id`, and a key body field.
3. Use `responseHeaders(...)` to describe the two headers of the success response.
4. In the error test, document only headers that actually belong to the 400 response; do not use a required descriptor for `Location`.
5. If `X-Request-Id` may be absent according to the contract, use `optional()` and explain the condition.
6. Run the tests and confirm the operation output contains `response-headers.adoc`.
7. Include the header table in the AsciiDoc page under the corresponding response.
8. Verify that snippets contain no cookies, tokens, or request IDs from real environments.
9. Run a clean build and verify the page renders properly.

**Completion criteria:** each operation has appropriate descriptors, important values are verified with assertions, header tables are generated and included properly, optional headers are described accurately, and output exposes no sensitive data.

## 13. Key Takeaways

- `responseHeaders(...)` declares descriptors for response headers; `headerWithName(...)` identifies the header and `description(...)` explains its meaning.
- Descriptors generate `response-headers.adoc`; raw response snippets still record the operation's HTTP example.
- Use dedicated assertions to verify that headers exist and have the right value/format.
- `optional()` should only be used when a header can genuinely be absent under the contract.
- Separate descriptors for different responses, such as `201 Created` with `Location` and `400 Bad Request` without it.
- Publish only headers needed by clients; sanitize dynamic/sensitive headers before publishing.
- Include the header table in Asciidoctor and connect snippet generation into the build/CI so documentation is rebuilt from current tests.
