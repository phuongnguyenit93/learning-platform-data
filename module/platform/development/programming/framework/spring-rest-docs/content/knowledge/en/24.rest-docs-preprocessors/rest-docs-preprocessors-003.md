# Preprocessing Requests Before Snippet Generation

In Spring REST Docs, the request recorded from an HTTP test may contain details unsuitable for putting directly into documentation as-is: test authentication tokens, session cookies, machine-dependent hostnames/ports, random request IDs, or payloads with fixture data that should not be exposed. **Request preprocessing** lets you normalize the request copy that REST Docs uses to generate snippets before documentation files are written.

The goal is to produce readable, stable, and safe HTTP examples while preserving test verifiability. The test still sends the original request to the application and assertions still verify application behavior. The preprocessor only acts on the request copy used for documentation; it does not change the request sent to the server.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module practices creating verifiable REST API documentation from HTTP tests with MockMvc, WebTestClient, or REST Assured, generating snippets for requests, responses, payloads, parameters, and headers, then authoring Asciidoctor/Markdown and integrating builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what problems request preprocessing solves in Spring REST Docs.
2. Identify the position of a request preprocessor in the send request → assertion → document → snippet chain.
3. Use `preprocessRequest(...)` to attach one or more `OperationRequestPreprocessor` instances.
4. Beautify request bodies, replace/remove headers, and normalize URIs before writing snippets.
5. Distinguish modifying the request copy used for snippets from modifying the real request.
6. Inspect raw HTTP, cURL, HTTPie, and descriptor tables after preprocessing.
7. Organize fixtures and CI so snippets are stable and do not leak sensitive data.

## 2. Where Does Request Preprocessing Fit?

An HTTP documentation test typically performs these steps:

```text
Prepare fixtures and test client
             │
             ▼
Build initial HTTP request
             │
             ▼
Send request to the application
             │
             ▼
Receive response and run assertions
             │
             ▼
Call document(identifier, ...)
             │
             ▼
Request preprocessor processes the recorded request
             │
             ▼
REST Docs generates snippets from the processed request
             │
             ▼
Asciidoctor / Markdown includes snippets into documentation
```

In MockMvc, the documentation hook is usually attached via `andDo(document(...))`. Request preprocessors are passed through `preprocessRequest(...)`. With WebTestClient or REST Assured, how the recorder/filter is attached differs, but it must be configured so the request is recorded and processors are applied before snippets are generated.

### 2.1. Real Request vs. Request Copy Used for Documentation

Suppose the test sends:

```http
GET /api/orders/42 HTTP/1.1
Host: localhost:53128
Authorization: Bearer docs-test-token
Cookie: SESSION=session-for-test
X-Request-Id: 6b49c1f4-volatile
Accept: application/json
```

Public documentation might only need:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

The server receives the first request; snippets can be generated from the second copy after preprocessing. Do not use the processed copy as evidence that the real application received a placeholder or sample hostname.

### 2.2. Why Process Before Generating Snippets?

Request snippets are often copied to try out the API, so inappropriate values can cause issues:

- Credentials or session IDs get exposed.
- Readers copy a hostname that only exists on a developer machine.
- Changing request IDs cause documentation diffs after every build.
- Payloads contain real fixture names, emails, or customer codes.
- URIs contain internal query parameters or unnecessary data.
- cURL/HTTPie snippets reuse sensitive values verbatim.

Preprocessing lets you handle these cases at one clear point before snippet files are written.

## 3. preprocessRequest(...) and OperationRequestPreprocessor

Spring REST Docs provides APIs in the `org.springframework.restdocs.operation.preprocess` package. `preprocessRequest(...)` accepts one or more request preprocessors and builds a composite processor to pass into documentation configuration.

Example:

```java
.andDo(document("orders-get",
    preprocessRequest(prettyPrint())
));
```

`OperationRequestPreprocessor` is the abstraction that processes an `OperationRequest` and returns the processed request. Built-in helpers like `prettyPrint()`, `removeHeaders(...)`, `modifyHeaders()`, and `replacePattern(...)` create composable processors.

Common static imports:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

Method names and builder signatures must match the Spring REST Docs version managed by your project.

## 4. Formatting the Request Body Before Writing Snippets

### 4.1. prettyPrint()

`prettyPrint()` formats the body for readability, especially for JSON/XML. A compact request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":12,"productId":7,"quantity":2}
```

Can become a more readable snippet:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 12,
  "productId": 7,
  "quantity": 2
}
```

Attaching the processor:

```java
.andDo(document("orders-create",
    preprocessRequest(prettyPrint())
));
```

`prettyPrint()` only formats the body; it does not validate that JSON conforms to the contract and does not hide sensitive data. Assertions and descriptors still need to be written separately.

### 4.2. XML and Text Bodies

With XML or plain text, check whether the processor and content type handle formatting as expected. Do not assume every body formats like JSON. For plain text, whitespace or line breaks are sometimes significant, so preserving them as-is may be more accurate.

XML example:

```xml
<order>
    <customerId>12</customerId>
    <quantity>2</quantity>
</order>
```

If the processor supports pretty-printing for this format in your version, snippets can have normalized indentation. Read the generated file to confirm accurate content and encoding.

### 4.3. Do Not Use prettyPrint to Fix Invalid Payloads

If a test request sends the wrong structure, pretty-printing does not make the request right. The preprocessor only formats the received message. Tests need assertions on status and related outcomes; request field descriptors document the contract independently of formatting.

## 5. Cleaning and Normalizing Request Headers

### 5.1. Removing Headers That Should Not Be Public

`removeHeaders(...)` removes headers from the request copy written to snippets:

```java
.andDo(document("orders-get",
    preprocessRequest(
        removeHeaders("Cookie", "X-Internal-Trace")
    )
));
```

This suits session cookies, debug headers, or environment metadata not needed in client guides. It only makes the headers disappear from snippets; the server still received the original request containing those headers.

Do not remove headers that belong to the contract if integrators need to know what to send. For instance, `Authorization` usually needs its name kept in examples while replacing its value with a placeholder.

### 5.2. Replacing Header Values with Placeholders

`modifyHeaders()` allows replacing values in the recorded request copy:

```java
.andDo(document("orders-get-authenticated",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    )
));
```

The request sent to the application still uses the test token; only snippets display the placeholder. This is the right choice when you want readers to understand a header is required without seeing the test credential. Builder syntax must match your library version.

Example with a correlation ID:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("X-Correlation-Id", "docs-correlation-id")
            .build()
    )
));
```

A stable sample value keeps snippets from changing whenever tests generate random IDs. If the ID format is part of the contract, use a dummy value with a matching format, such as a sample UUID.

### 5.3. Required and Optional Headers

Preprocessors do not define whether a header is required or optional. That belongs to the contract and descriptors. If clients must send `Authorization`, documentation must explain the required header and how to obtain a token. If a correlation ID is optionally sent by clients, clearly describe how the server behaves when it is omitted. Removing an internal header from snippets does not mean it is optional for the server.

Do not use `removeHeaders` to avoid documenting a public header that clients are required to send.

## 6. Normalizing URI, Host, and Port

Requests recorded in test environments may use a temporary Host/port, such as a random server port. Spring REST Docs has processors to adjust URIs such as `modifyUris()`.

Example:

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

This transforms the URI written in snippets to the documentation host and scheme. Use an illustrative domain agreed upon by your team; do not change the endpoint into a nonexistent URL if readers need to copy requests to run them directly.

### 6.1. When Should You Normalize URIs?

- Tests run locally with a random port.
- CI has a container hostname different from developer machines.
- Public docs need an official domain instead of `localhost`.
- Requests use absolute URIs, while public endpoints have a unified base URL.

If snippets use relative URIs and only the `Host` header differs, inspect the output to choose the appropriate transformation. Do not alter the path, query, or scheme if they are parts of the contract that need to be shown.

### 6.2. Preserving Request Semantics

Normalizing the hostname must not corrupt the method, path, query parameters, or required headers. For example, if an API distinguishes base paths `/v1` and `/v2`, a preprocessor should not strip the version segment just to shorten the URL.

## 7. Normalizing Dynamic Values in Requests

Requests may contain dynamic data unimportant for examples: timestamps, nonces, correlation IDs, or random fixture codes. `replacePattern(...)` can replace content matching a regular expression with a sample value.

Conceptual example: replacing a dynamic correlation ID with a stable string. For a specific header, `modifyHeaders()` is usually clearer; use regex when the value to process appears in multiple places in the message.

Rules for using regex:

1. Scope the pattern to the exact header or field.
2. Do not replace all alphanumeric strings in the request.
3. Choose a replacement value with an appropriate format.
4. Run tests and read snippets to ensure you did not accidentally alter paths, business IDs, or other payloads.

The `replacePattern(...)` signature and where the pattern applies must match your API version. Do not copy an untested regex and assume it handles every request properly.

## 8. Combining Multiple Request Processors

A request may need multiple processing steps:

```java
.andDo(document("orders-create",
    preprocessRequest(
        prettyPrint(),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-Correlation-Id", "docs-correlation-id")
            .build(),
        removeHeaders("Cookie", "X-Internal-Trace")
    )
));
```

In this example, the body is formatted; the URI is normalized; `Authorization` and correlation ID are replaced with sample values; `Cookie` and internal trace headers are removed from the request snippet.

Do not apply every processing step to every API. One endpoint might need a cookie as part of its public contract; another uses a custom host for routing. Choose processors based on the operation's documentation goal.

### 8.1. Processing Order and Output

Processor order can affect the result. If you remove a header first, a later processor cannot replace that header's value. If you replace text and then pretty-print, formatting applies to the modified body.

Read the final output instead of reasoning solely from configuration. Keep processors in a meaningful order and avoid unnecessary transformation chains that are hard to maintain.

## 9. End-to-End Example with MockMvc

Suppose the API has `GET /api/orders/{orderId}`. The test sends a dummy token and a random correlation ID, while documentation needs an illustrative host and no cookies.

```java
@Test
void getOrder_documentsNormalizedRequest() throws Exception {
    mockMvc.perform(
            RestDocumentationRequestBuilders
                .get("/api/orders/{orderId}", 42L)
                .header("Authorization", "Bearer docs-test-token")
                .header("Cookie", "SESSION=test-session")
                .header("X-Correlation-Id", "run-982761")
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(jsonPath("$.id").value(42))
        .andDo(document("orders-get-success",
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
                removeHeaders("Cookie")
            ),
            pathParameters(
                parameterWithName("orderId")
                    .description("Order identifier")
            )
        ));
}
```

This example illustrates where to attach request processors; a project needs real fixtures/controllers and an appropriate REST Docs setup. Assertions run on the real request/response. After preprocessing, request snippets can display the example host, placeholder token, and fixed correlation ID, with no test cookie left.

### 9.1. Inspecting Output Snippets

After the test runs, inspect the files associated with the identifier:

```text
target/generated-snippets/orders-get-success/
├── http-request.adoc
├── curl-request.adoc
├── httpie-request.adoc
└── path-parameters.adoc
```

Filenames depend on descriptors/templates. Verify:

- `Authorization` no longer contains the fixture token.
- `Cookie` has been removed if it is not part of the example.
- Host/port matches the expected documentation value.
- Correlation ID does not vary between builds.
- Path parameter preserves the right template/value.
- cURL and HTTPie also reflect the normalized request per your library version's processor behavior.

Do not check only `http-request`; users often copy cURL/HTTPie commands directly.

## 10. RequestPreprocessor and Descriptors

Request preprocessors normalize the message; descriptors document the contract. Example:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Client Bearer access token")
    ),
    pathParameters(
        parameterWithName("orderId")
            .description("Order identifier")
    )
));
```

The preprocessor preserves header structure and replaces the credential. `requestHeaders` explains the meaning of `Authorization`. `pathParameters` documents `orderId`. Separate assertions verify that the request succeeds according to the contract.

Using only descriptors without preprocessing can cause raw requests to leak credentials; using only preprocessing without descriptors can leave readers seeing a placeholder without understanding how to use the header. If a processor removes a header, consider whether that header should be documented in the descriptor table. Raw snippets and description tables must be consistent.

## 11. Limitations to Understand

### 11.1. Does Not Modify the Request Received by the Application

A request preprocessor does not replace filters, interceptors, or server logic. If you need to change the actual request, handle it in test setup/client or in the application; do not rely on a preprocessor.

### 11.2. Does Not Replace Assertions

If the server rejects the request but the test does not check status/body, the preprocessor can still generate clean snippets. Assertions must guard important expectations on the real response.

### 11.3. Does Not Hide Contract Errors

Do not rewrite a wrong method, path, required header, or payload into a valid example without fixing the test/API. If the actual request is wrong, fix the fixture or test; documentation must reflect a valid request that clients need to send.

### 11.4. Does Not Remove Information Clients Need

If `Authorization`, `Content-Type`, or `Idempotency-Key` is a required part of the request, keep the header name and replace sensitive values if needed. Do not delete the entire header just to avoid handling secrets.

## 12. Common Errors and Troubleshooting

| Symptom | Cause | Solution |
| --- | --- | --- |
| Token still appears in request snippet | Only omitted descriptor, did not preprocess raw request | Use dummy fixture and replace `Authorization` in request preprocessor |
| Cookie still appears in documentation | Header not removed or processor not attached to operation | Use `removeHeaders("Cookie")`, inspect snippets |
| URI contains `localhost`/random port | Recorded URI not normalized | Use `modifyUris()` with documentation base URL |
| Path parameter wrong/missing template | Request builder did not preserve URI template or preprocessing altered path | Use appropriate REST Docs request builder, avoid unintended path edits |
| cURL still has credentials | Only checked `http-request.adoc` | Review all derived snippets |
| Correlation ID changes every build | Dynamic value recorded verbatim | Use deterministic fixture or replace header |
| Body is not formatted | Content type/body unsupported by processor or processor attached incorrectly | Inspect request and generated files |
| Required header disappears | Overly broad removal | Only remove internal headers, keep contract headers |
| Assertions confused with snippet checks | Used post-processed values to infer original message | Assert on real message; review snippets separately |
| Snippets contain real fixture data | Test used unsafe data | Use dummy data and inspect all output |
| Asciidoctor cannot find snippet | Test did not run, wrong identifier, or wrong output directory | Run tests before rendering and verify paths |

## 13. Best Practices

1. Prefer safe fixtures: never put real tokens/sessions into test requests.
2. Preprocess on the right side: use `preprocessRequest` for request headers/body/URI.
3. Keep the contract understandable: replace sensitive values with placeholders instead of deleting headers clients must send.
4. Normalize the environment: replace `localhost`, random ports, and internal hosts with the published base URL.
5. Use stable IDs to reduce meaningless diffs.
6. Scope regexes narrowly to replace only targeted data regions.
7. Combine with descriptors to explain headers, parameters, and fields.
8. Inspect all derived snippets: HTTP, cURL, and HTTPie may contain the same data.
9. Keep assertions on real results; do not let preprocessing mask incorrect behavior.
10. Run a clean build in CI, regenerating snippets before Asciidoctor renders.

## 14. Practice Exercise

Document `GET /api/orders/{orderId}`. The test sends a dummy Bearer token, a test session `Cookie`, a dynamic correlation ID, and runs the server on a random port. Documentation needs requests with a sample domain, an `Authorization` placeholder, a stable correlation ID, and no `Cookie`.

**Tasks:**

1. Configure MockMvc with Spring REST Docs and write the test.
2. Send a dummy token and dummy cookie; do not use real credentials.
3. Assert status and at least one important response value.
4. Call `preprocessRequest` to replace `Authorization` with a placeholder.
5. Remove `Cookie` from snippets if it is not part of the public contract.
6. Use `modifyUris` to normalize scheme/host/port to the documentation domain.
7. Replace the random correlation ID with a stable sample ID.
8. Declare required path parameter and request header descriptors.
9. Run the test and inspect HTTP, cURL, and HTTPie snippets.
10. Render Asciidoctor, confirm includes work, and ensure no fixture credentials exist in artifacts.

**Completion criteria:** the real request is still sent and verified properly; request snippets have consistent URIs, required headers are kept safely, internal headers are handled intentionally, derived snippets do not leak sensitive values, and the build is reproducible from clean output.

## 15. Takeaways

- Request preprocessing transforms the request copy used to generate snippets; it does not change the request received by the application.
- `preprocessRequest` accepts `OperationRequestPreprocessor` instances and attaches them to the documented operation.
- `prettyPrint` formats bodies; `removeHeaders` removes headers from snippets; `modifyHeaders` changes header values; `modifyUris` normalizes URIs; `replacePattern` replaces pattern-matching content.
- Assertions verify real behavior; preprocessors only normalize the documentation record.
- Descriptors explain headers/parameters/fields; preprocessors control the raw message written out.
- Inspect raw HTTP, cURL, HTTPie, and related snippets after every change.
- Prefer dummy fixtures, placeholders, and stable output; run tests before rendering in CI.
