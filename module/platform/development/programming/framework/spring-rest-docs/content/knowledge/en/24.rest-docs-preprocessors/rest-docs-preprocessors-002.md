# RequestPreprocessor and ResponsePreprocessor

In Spring REST Docs, the request and response are two independent messages with distinct contents and documentation purposes. When generating snippets, we often need to process each side differently: the request may need `Authorization` replaced, `Host` normalized, or `Cookie` removed; the response may need JSON formatted, a request ID normalized, or `Set-Cookie` removed. The two preprocessor branches allow doing this separately.

Spring REST Docs provides APIs to attach processors via `preprocessRequest(...)` and `preprocessResponse(...)`. In terms of processor types, requests are handled by `OperationRequestPreprocessor` and responses are handled by `OperationResponsePreprocessor`. These processors act on the message copy used to generate snippets. They do not change the request sent to the server or the response returned by the application to the test.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module practices creating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating request, response, payload, parameter, and header snippets, then authoring Asciidoctor/Markdown and integrating into builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the responsibilities of a request preprocessor and a response preprocessor.
2. Understand the roles of `OperationRequestPreprocessor` and `OperationResponsePreprocessor`.
3. Attach processors to the appropriate side using `preprocessRequest(...)` and `preprocessResponse(...)`.
4. Choose suitable processors to format bodies, replace headers, or strip metadata from snippets.
5. Combine multiple processors and inspect the impact of processing order.
6. Keep assertions on real messages and avoid confusing processed records with application behavior.
7. Organize tests, snippets, and CI so requests and responses are documented consistently.

## 2. Two Message Types, Two Processing Branches

An HTTP exchange consists of a request from the client and a response from the server:

```text
HTTP client / test
       │
       │ Request
       ▼
Spring application
       │
       │ Response
       ▼
Test receives result
       │
       ▼
document(identifier, ...)
       │
       ├── preprocessRequest(...)
       │       └── processes the recorded request
       │
       └── preprocessResponse(...)
               └── processes the recorded response
                       │
                       ▼
                 Snippet generation
                       │
                       ▼
               Asciidoctor / Markdown
```

Request processors and response processors cannot be swapped arbitrarily. Some transformations only make sense on requests, such as replacing `Authorization` or removing `Cookie`. Some transformations only make sense on responses, such as normalizing `ETag`, removing `Set-Cookie`, or formatting the body returned by the server.

| Branch | Target Processed | Example Information | Snippets Commonly Affected |
| --- | --- | --- | --- |
| Request | Recorded HTTP request | Method, URI, request headers, request body | `http-request`, cURL, HTTPie, request header/field snippets |
| Response | Recorded HTTP response | Status, response headers, response body | `http-response`, response header/field snippets |

The exact list of files depends on descriptors and test configuration. Raw request/response snippets are example messages; descriptor tables are generated from declarations made in the test.

## 3. RequestPreprocessor and preprocessRequest(...)

### 3.1. Role of a Request Preprocessor

A request preprocessor transforms the recorded request before Spring REST Docs creates snippets. It is appropriate when you want to:

- Beautify JSON/XML request bodies.
- Replace `Authorization` or test API keys with placeholders.
- Remove `Cookie`, internal headers, or environment-specific headers.
- Normalize `Host`, port, or URI in examples.
- Replace dynamic values that readers do not need to see.

It does not alter the request sent to the controller/server. If a test sends a dummy Bearer token, the application receives that value; the preprocessor can replace the value with a placeholder only in snippets.

### 3.2. Attaching a Request Preprocessor

Example using MockMvc:

```java
mockMvc.perform(
        get("/api/orders/{id}", 42L)
            .header("Authorization", "Bearer docs-test-token")
            .header("Cookie", "SESSION=test-session")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andDo(document("orders-get-authenticated",
        preprocessRequest(
            prettyPrint(),
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .build(),
            removeHeaders("Cookie")
        )
    ));
```

In this example:

- `prettyPrint()` formats the request body if a suitable body is present.
- `modifyHeaders()` replaces `Authorization` on the request copy written to snippets.
- `removeHeaders("Cookie")` removes cookies from the request snippet.
- Assertions still observe the result of the request sent with the original test token and cookie.

Builder syntax must match the Spring REST Docs version in use. Tokens and sessions in tests must be dummy fixtures; preprocessors are an extra sanitization layer, never a reason to put real secrets into the test environment.

### 3.3. When to Use a Request Preprocessor

| Scenario | Appropriate Processing | Reason |
| --- | --- | --- |
| Hard-to-read JSON body | `prettyPrint()` | Improves readability |
| Test Bearer token appears in request | Replace `Authorization` | Keeps header name, hides credential value |
| Session cookie unnecessary for integrators | `removeHeaders("Cookie")` | Avoids exposing session identifiers |
| Host/port depends on test machine | Normalize URI/Host with an appropriate processor | Snippets remain stable between local and CI |
| Query/body contains specific fixture data | Replace targeted data intentionally | Avoids leaking unnecessary information |

Do not remove a header just because it looks internal if it is part of the contract that clients need to understand. In that case, keep the header name and replace the value with a clear placeholder.

## 4. ResponsePreprocessor and preprocessResponse(...)

### 4.1. Role of a Response Preprocessor

A response preprocessor processes the response received by the test before generating snippets. It is appropriate when you want to:

- Format JSON/XML responses.
- Remove `Set-Cookie`, trace/debug headers, or non-public metadata.
- Normalize request IDs, timestamps, `ETag`, or environment-dependent values.
- Replace hostnames/absolute URLs with sample values.
- Mask data in the response body when real values are unnecessary for the example.

The real response is still returned to the test and client. If an assertion verifies that the response has `X-Request-Id`, the assertion runs on the real value; the snippet after preprocessing can display `docs-request-id`.

### 4.2. Attaching a Response Preprocessor

Example:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get",
        preprocessResponse(
            prettyPrint(),
            removeHeaders("Set-Cookie", "X-Internal-Trace"),
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build()
        )
    ));
```

Here `prettyPrint` formats the response body, `removeHeaders` removes headers that should not be public, and `modifyHeaders` replaces the dynamic request ID with a stable example. The test still checks status, header presence, and ID in the body on the real response.

### 4.3. When to Use a Response Preprocessor

| Scenario | Appropriate Processing | Reason |
| --- | --- | --- |
| Compact JSON response | `prettyPrint()` | Easy to read, review, and follow |
| `Set-Cookie` contains session | `removeHeaders("Set-Cookie")` if cookies are not part of public examples | Avoids exposing sessions |
| Request ID changes on every run | Replace value with sample ID | Reduces meaningless diffs |
| Internal trace header | Remove or normalize according to documentation policy | Avoids revealing operational internals |
| Response contains environment hostname | Replace host with example name | Avoids tying documentation to a private environment |

If a header or body field is part of the contract that needs to be documented, do not remove it such that clients can no longer see how the API works. You can preserve the structure while using dummy data.

## 5. Comparing the Two Branches

| Characteristic | RequestPreprocessor | ResponsePreprocessor |
| --- | --- | --- |
| Spring REST Docs wrapper | `preprocessRequest(...)` | `preprocessResponse(...)` |
| Processor type | `OperationRequestPreprocessor` | `OperationResponsePreprocessor` |
| Target | Recorded request | Recorded response |
| Common examples | `Authorization`, `Cookie`, `Host`, request body | `Set-Cookie`, request ID, `ETag`, response body |
| Primary raw snippets | `http-request.adoc` and client commands | `http-response.adoc` |
| Effect on real message | None | None |

Some processors can be used on both sides, such as formatting bodies or replacing headers. However, applicability to both does not mean you should apply the same rule to both. Consider the values and semantics of each respective message.

## 6. Using Request and Response Processors Together

An operation often needs to normalize both sides:

```java
.andDo(document("orders-get",
    preprocessRequest(
        prettyPrint(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build(),
        removeHeaders("Cookie")
    ),
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

The two wrappers are independent and can be declared together in a single `document` call. The request keeps the authentication example while replacing the token and dropping session cookies; the response keeps meaningful status/body, drops server cookies, and replaces the dynamic request ID. Separating the two branches helps reviewers see which values are changed on the request and which are changed on the response.

### 6.1. Order of Multiple Processors in the Same Branch

Processor order can affect the output. If the first processor removes a header, a later processor no longer has that header to replace. If a processor alters the body before formatting, formatting is applied to the modified body.

Determine the desired output, place processors in a logical order, run the test, and read the final snippets. Verify on the actual library version instead of inferring all behavior solely from method names.

## 7. Request/Response Processors and Assertions

**Assertions protect API behavior; preprocessors normalize the record used for documentation.**

The real response might be:

```http
HTTP/1.1 200 OK
X-Request-Id: req-8a1f2d
Set-Cookie: SESSION=real-test-session
Content-Type: application/json

{"id":42,"status":"PAID"}
```

Test assertions:

```java
.andExpect(status().isOk())
.andExpect(header().exists("X-Request-Id"))
.andExpect(jsonPath("$.status").value("PAID"))
```

The response snippet after preprocessing might be:

```http
HTTP/1.1 200 OK
X-Request-Id: docs-request-id
Content-Type: application/json

{
  "id": 42,
  "status": "PAID"
}
```

The sample ID and the absence of `Set-Cookie` only describe the documentation record. Do not use the post-processed snippet to claim that the real application returns the sample ID string or does not return `Set-Cookie`. To verify those things, assertions must run on the pre-preprocessed response.

## 8. Descriptors After Applying Processors

Descriptors such as `requestHeaders(...)`, `responseHeaders(...)`, `requestFields(...)`, and `responseFields(...)` document the contract. Preprocessors normalize the request/response used as the source for snippets. The two parts complement each other but do not replace each other.

Example documenting `Authorization` without exposing the token:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token issued by the authentication system")
    )
));
```

The descriptor table explains the header; the raw request snippet shows the processed sample. If you remove `Authorization` completely with `removeHeaders`, consider whether integrators still need to see this header in examples. Do not let the table describe one thing while the raw request illustrates another.

## 9. Writing Custom Processors When Built-Ins Are Not Enough

Built-in processors usually cover common needs. When more complex rules are required, you can create a custom implementation based on the operation preprocessing API of your library version.

A custom processor should:

- Only change the specific headers/body requested.
- Not change status, method, or URI unless there is a clear documentation goal.
- Not alter the original message sent/received by the application.
- Have tests verifying inputs and outputs.
- Have a name and description clearly stating the reason for the transformation.

Conceptual examples: a processor that replaces the hostname in requests with `api.example.test`, or normalizes timestamps in the response body. Interface/factory details must follow the Spring REST Docs API version; avoid writing ad-hoc string-manipulation helpers if built-ins already suffice.

Do not use processors to turn error statuses into success, strip missing required fields, rewrite wrong business values into expected ones, or hide unsafe responses. Those practices conceal bugs and strip documentation of its verifiable value.

## 10. Organizing Helpers by Request/Response Direction

If multiple tests repeat snippet policies, you can create separate helpers for each side:

```java
static OperationRequestPreprocessor publicRequestPreprocessor() {
    return preprocessRequest(
        prettyPrint(),
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
        prettyPrint(),
        removeHeaders("Set-Cookie", "X-Internal-Trace")
    );
}
```

The snippets above illustrate organization; verify return types and imports against your project's Spring REST Docs API. Separating the two helpers clarifies intent and prevents applying response policies to requests.

Do not use an overly broad shared helper if endpoints have different contracts. For example, one operation might need to keep `Set-Cookie` because it documents a cookie mechanism for clients; a helper that removes `Set-Cookie` by default would not fit.

## 11. Differences Across Test Clients

Request/response preprocessing principles do not depend on the test client, though where the recorder is attached differs:

| Client | Where Documentation Is Attached | Notes |
| --- | --- | --- |
| MockMvc | `andDo(document(...))` | Configure MockMvc with REST Docs; use builders that preserve URI templates when needed |
| WebTestClient | Filter/documentation configuration in the exchange chain | Requires WebTestClient module and compatible recorder |
| REST Assured | REST Docs filter in request specification | Attach filter to the configured request before sending |

Do not copy MockMvc syntax to other clients. Use the corresponding integration API to pass processors to the operation recorder.

## 12. Practice Exercise

Document the `GET /api/orders/{id}` endpoint. The request uses a dummy Bearer token and a test session `Cookie`. The response has a dynamic `X-Request-Id`, `Set-Cookie` from middleware, and order JSON.

**Tasks:**

1. Write a test with MockMvc and configure Spring REST Docs.
2. Send a dummy `Authorization` token and dummy `Cookie`.
3. Assert status, presence of the request ID header, and important response fields.
4. Use a request preprocessor to format the body if present, replace `Authorization` with a placeholder, and remove `Cookie`.
5. Use a response preprocessor to format JSON, replace the request ID with a sample ID, and remove `Set-Cookie`.
6. Declare request/response header descriptors matching the public contract.
7. Run the test and inspect `http-request`, `http-response`, cURL/HTTPie, and header tables.
8. Confirm assertions check the real message while snippets show the processed copy.
9. Include snippets in an AsciiDoc page.
10. Run a clean build and verify output; add a secret scan if documentation is published.

**Completion criteria:** the two processor branches are attached to the right sides; secrets are sanitized from snippets; real status/body/headers are still asserted; descriptors are consistent with examples; documentation renders from fresh output.

## 13. Takeaways

- Request and response are two independent messages, so you must choose the right processing branch.
- `preprocessRequest(...)` applies `OperationRequestPreprocessor` to the recorded request; `preprocessResponse(...)` applies `OperationResponsePreprocessor` to the recorded response.
- Request processors typically normalize `Authorization`, `Cookie`, `Host`, URI, and request bodies; response processors typically handle `Set-Cookie`, request IDs, `ETag`, internal headers, and response bodies.
- Both can be attached in the same `document` call, while keeping separate rules per message direction.
- Assertions check real messages; preprocessors only change the snippet record and do not alter the application or data received by clients.
- Descriptors explain the contract; raw snippets show the post-processed request/response. Both must be consistent.
- Verify processor order, all derived snippets, and rendered results in CI before publishing.
