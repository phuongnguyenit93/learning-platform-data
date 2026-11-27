# What Is a Preprocessor and When Does Processing Happen

Spring REST Docs generates snippets from the request and response recorded when an HTTP test runs. However, the raw message is sometimes not suitable to include directly in documentation: hard-to-read JSON, headers with a random request ID, requests containing cookies that should not be exposed, or responses carrying a test-environment hostname. A **Preprocessor** lets you transform the request or response copy used to generate snippets, making examples more readable, stable, and secure.

The key point is understanding the timing: a preprocessor is applied during the operation recording/documentation step, when Spring REST Docs is preparing to generate snippets. It is not middleware handling requests in the application, and it does not change the response that the controller sent back to the test. Therefore, assertions still need to verify actual behavior; the preprocessor only adjusts the message copy used for documentation.

This lesson belongs to the **Preprocessors** chapter of the `SPRING_REST_DOCS` module. The module practices creating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generating request, response, payload, parameter, and header snippets, then authoring Asciidoctor/Markdown and integrating into builds and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what problem preprocessors solve in Spring REST Docs.
2. Identify when a preprocessor runs in the test → assertion → document → snippet chain.
3. Distinguish request and response processing via `preprocessRequest(...)` and `preprocessResponse(...)`.
4. Use common processors to format, remove, or modify information in the recorded message copy.
5. Understand the relationship between preprocessors, assertions, and descriptors.
6. Avoid using preprocessors to hide implementation bugs or alter real data in the application.
7. Verify snippets and integrate the processing step into builds/CI.

## 2. What Is a Preprocessor?

A preprocessor is a processing component called by Spring REST Docs on a request or response before generating snippets. It receives the recorded message, applies one or more transformations, and passes the processed result to the documentation generation step.

Example of an original JSON response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"name":"Notebook","active":true}
```

After formatting, the snippet can display:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "name": "Notebook",
  "active": true
}
```

The application's response is still the message that the test received. The processor only makes the recorded snippet easier to read.

### 2.1. A Preprocessor Is Not Application Middleware

| Component | Where It Runs | Purpose |
| --- | --- | --- |
| Application filter/interceptor | Inside the server's request/response processing flow | Authentication, logging, adding headers, or modifying real HTTP messages |
| Test assertion | Inside the test after executing the request | Verifying status, headers, body, and behavior |
| Spring REST Docs preprocessor | Inside the operation documentation step | Normalizing the request/response copy written into snippets |

If you use a filter to remove a response header, real clients may no longer receive that header either. If you use a preprocessor to remove a header from snippets, the real response remains unchanged. The two operations have different impacts.

### 2.2. Why Are Preprocessors Needed?

Common use cases:

- Formatting JSON/XML so readers can follow it easily.
- Normalizing environment-dependent hostnames, ports, or URLs.
- Replacing request IDs, timestamps, or test tokens with stable sample values.
- Removing cookies, credentials, or internal headers from public snippets.
- Adjusting example bodies to hide unnecessary data.
- Keeping snippets stable across builds, reducing meaningless diffs.

You do not need a preprocessor for every operation. Only add one when needed; unnecessary transformation chains can make examples diverge far from the tested message.

## 3. When Does a Preprocessor Run?

Overview flow of an operation:

```text
1. Prepare fixtures and test client
             │
             ▼
2. Send HTTP request to the application
             │
             ▼
3. Application processes and returns response
             │
             ▼
4. Assertions verify status/headers/body
             │
             ▼
5. Call document(identifier, ...)
             │
             ▼
6. Preprocessors transform the recorded message copy
             │
             ▼
7. Descriptors and snippet generation create documentation files
             │
             ▼
8. Asciidoctor/Markdown includes snippets into pages
```

This is a conceptual model. With MockMvc, the hook is typically attached via `andDo(document(...))`; WebTestClient and REST Assured use their corresponding integration APIs/filters. In all three cases, the processor participates in the documentation step after the operation's message has been recorded.

### 3.1. Assertions Verify Actual Results

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get",
        preprocessResponse(prettyPrint())
    ));
```

Assertions verify the request result in the test. Then `document` applies `prettyPrint` to the response copy used to generate snippets. If the server returns the wrong status or misses a required header, the test must fail even though the preprocessor could produce clean output.

### 3.2. Preprocessors Do Not Modify Data Received by the Client

Suppose the server returns:

```http
X-Request-Id: req-actual-8791
```

The preprocessor replaces the value in the snippet with:

```http
X-Request-Id: docs-request-id
```

The sample value only appears in the snippet. Real clients and assertions still work with the value the server actually returned. Do not treat the normalized value as proof that the server always returns that exact sample string.

## 4. Two Main Attachment Points: preprocessRequest and preprocessResponse

Spring REST Docs provides two ways to wrap processors:

- `preprocessRequest(...)`: applies one or more processors to the recorded request.
- `preprocessResponse(...)`: applies processors to the recorded response.

Example:

```java
.andDo(document("orders-get",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint())
));
```

The two sides are independent. An operation may only need to prettify the request, only clean up the response, or apply different processors to each side.

### 4.1. Common API Imports

With MockMvc, static imports typically look like:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
```

In addition, you can import `removeHeaders`, `replacePattern`, or header modification APIs depending on the transformations needed and library version.

## 5. Common Preprocessors

### 5.1. prettyPrint()

`prettyPrint()` formats the body for readability, often useful for JSON/XML:

```java
.andDo(document("products-get",
    preprocessResponse(prettyPrint())
));
```

`prettyPrint()` does not change payload semantics. It does not automatically mask sensitive data, does not fix data types, and does not validate schemas. For bodies in unsupported formats, check the actual output.

### 5.2. removeHeaders(...)

`removeHeaders(...)` removes headers from the message written into snippets. For example, removing `Cookie` from the request and `Set-Cookie` from the response:

```java
.andDo(document("session-info",
    preprocessRequest(removeHeaders("Cookie")),
    preprocessResponse(removeHeaders("Set-Cookie"))
));
```

The header is only removed from raw HTTP snippets; it may still exist in the real request/response. Use this when a header is unnecessary for readers or contains data that should not be made public. If the header is part of the contract and clients need guidance on it, replace its value with a placeholder instead of removing the header name.

### 5.3. modifyHeaders(...)

`modifyHeaders()` allows changing headers in the message copy written to snippets, such as replacing `Authorization` with a placeholder:

```java
.andDo(document("orders-get-authenticated",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    )
));
```

The exact builder syntax must match your Spring REST Docs version. The goal is to preserve the header name and request structure while keeping test credentials out of the documentation. Authentication assertions must still run on the original request using the test token; the preprocessor does not test the server with the placeholder.

### 5.4. replacePattern(...)

`replacePattern(...)` replaces content matching a regular expression in the message. It is useful when sensitive strings appear in header values or the body and need rule-based replacement.

When using regex:

- Scope the pattern to the exact field that needs processing.
- Choose a meaningful replacement that does not mislead readers.
- Test both matching and non-matching cases.
- Read the snippets after the test to ensure no other data was unintentionally replaced.

Do not use overly broad regexes because they can corrupt business IDs or payload examples.

## 6. Combining Multiple Processors

An operation can apply multiple transformations:

```java
.andDo(document("profile-get",
    preprocessRequest(
        prettyPrint(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    ),
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

In the example, the request is formatted and `Authorization` is replaced in the snippet copy. The response is formatted, some headers are removed, and the request ID is normalized. Only keep necessary steps; too many transformations can make the documented message differ significantly from the real message.

### 6.1. Processor Order Can Affect the Result

Transformation order can matter. If the first processor removes a header, a subsequent processor will no longer have that header to replace its value. If a processor alters the body before beautifying, formatting operates on the modified body.

Determine the desired output, place steps in a logical order, run the test, and read the final snippets. When the order does not produce the expected result, adjust the processors and re-verify on the actual library version.

## 7. Preprocessors and Descriptors Have Distinct Roles

A preprocessor alters the message used for snippets. A descriptor describes the API components that readers need to understand. The two components complement each other but do not replace each other.

| Component | Role | Example |
| --- | --- | --- |
| Assertion | Verify actual behavior | `status().isOk()`, header/body checks |
| Preprocessor | Normalize message copy for documentation | `prettyPrint()`, `removeHeaders(...)` |
| Descriptor | Document fields, parameters, or headers | `responseFields(...)`, `requestHeaders(...)` |
| Raw snippet | Request/response example after processing | `http-request.adoc`, `http-response.adoc` |
| Asciidoctor include | Embed snippets into source pages | `include::{snippets}/...[]` |

Example of removing `Set-Cookie` from the response snippet while still documenting `Content-Type`:

```java
.andDo(document("login",
    preprocessResponse(removeHeaders("Set-Cookie")),
    responseHeaders(
        headerWithName("Content-Type")
            .description("Response media type")
    )
));
```

Not declaring a descriptor for `Set-Cookie` does not guarantee the header disappears from the raw response. Conversely, removing a header in a preprocessor does not mean the application does not return that header.

### 7.1. Checking Descriptors When Messages Are Processed

When a preprocessor removes or alters a part that descriptors need to document, check how your library version handles snippets. A header removed from the recorded message copy will no longer appear as the previous raw header.

If you need to document `Authorization`, you can keep a descriptor explaining the scheme, replace the credential with a placeholder, and use assertions to verify that the test request sent the dummy token and the server handled it properly.

## 8. Preprocessors Across Test Clients

The principle is independent of the test client, though how the recorder is attached differs:

| Test Client | Common Documentation Hook | What to Ensure |
| --- | --- | --- |
| MockMvc | `andDo(document(...))` | MockMvc is configured with REST Docs; use request builders that preserve URI templates when needed |
| WebTestClient | Filter/documentation configuration in the exchange chain | Client has REST Docs integrated and the recorder receives the response |
| REST Assured | REST Docs filter attached to the request specification | Filter is added to the right request and the operation has an identifier |

Do not copy MockMvc's `andDo` syntax to WebTestClient or REST Assured. Use the module/API for the corresponding test client and attach processors to the documented operation.

## 9. Limitations to Understand

### 9.1. Preprocessors Do Not Fix the Application

If the real response contains an internal header that should not be returned to clients, `removeHeaders` only hides it in snippets. You must fix the implementation if that header should not be present in the real HTTP response.

### 9.2. Preprocessors Do Not Replace Assertions

If the test does not check status, body, or headers, processed snippets may still look valid even if the implementation returns wrong data. Assertions must confirm important expectations on the real message.

### 9.3. Preprocessors Do Not Define the Contract

Replacing a token with a placeholder only produces a safer example. Authors still need to explain the scheme, how clients obtain tokens, and authentication requirements.

### 9.4. Do Not Over-Transform

If you remove too many headers or replace meaningful values, readers can no longer see how the API works. Only process parts that should not be disclosed or dynamic parts that carry no meaning for the example.

## 10. Complete Hands-On Example

Suppose the `GET /api/orders/{id}` endpoint requires Bearer authentication and returns order JSON and `X-Request-Id`. Test middleware may add `Set-Cookie`. Public snippets need an `Authorization` placeholder, a stable request ID, and no cookies.

```java
@Test
void getOrder_createsCleanDocumentation() throws Exception {
    mockMvc.perform(
            RestDocumentationRequestBuilders
                .get("/api/orders/{id}", 42L)
                .header("Authorization", "Bearer docs-test-token")
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(jsonPath("$.id").value(42))
        .andDo(document("orders-get-success",
            preprocessRequest(
                prettyPrint(),
                modifyHeaders()
                    .set("Authorization", "Bearer <access-token>")
                    .build()
            ),
            preprocessResponse(
                prettyPrint(),
                removeHeaders("Set-Cookie"),
                modifyHeaders()
                    .set("X-Request-Id", "docs-request-id")
                    .build()
            ),
            requestHeaders(
                headerWithName("Authorization")
                    .description("Client Bearer access token")
            ),
            responseHeaders(
                headerWithName("X-Request-Id")
                    .description("Identifier used for request tracing")
            ),
            responseFields(
                fieldWithPath("id")
                    .description("Order identifier")
            )
        ));
}
```

This is an example combining processors, assertions, and descriptors; a project needs a security filter chain setup if it wants to demonstrate authentication. `docs-test-token` must be a dummy fixture used only in tests. Cross-check imports and builder APIs against your project's Spring REST Docs version.

After the test runs, verify:

- `http-request.adoc` has the `Authorization` placeholder and no fixture token.
- `http-response.adoc` has the sample request ID and no `Set-Cookie`.
- `request-headers.adoc` and `response-headers.adoc` describe semantics accurately.
- `response-fields.adoc` reflects the response structure.
- cURL/HTTPie snippets also no longer contain the original credential.

## 11. Documentation Integration and CI

After the test, Asciidoctor can include the processed snippets:

```asciidoc
=== Retrieve an Order

==== Request

include::{snippets}/orders-get-success/http-request.adoc[]

==== Request headers

include::{snippets}/orders-get-success/request-headers.adoc[]

==== Response

include::{snippets}/orders-get-success/http-response.adoc[]

==== Response headers

include::{snippets}/orders-get-success/response-headers.adoc[]
```

The pipeline needs to run tests before rendering:

```text
Clean generated output
       │
       ▼
Run HTTP documentation tests
       │
       ▼
Apply preprocessors and generate snippets
       │
       ▼
Validate snippets (secret scan / content checks)
       │
       ▼
Render Asciidoctor or Markdown
       │
       ▼
Review final artifact
       │
       ▼
Publish
```

With Markdown, Asciidoctor's include syntax is not a built-in feature; an appropriate insertion/conversion step is required. Preprocessors only create safer snippets; CI should still inspect both generated snippets and the final HTML/PDF artifact before publishing.

## 12. Common Errors and Troubleshooting

| Symptom | Cause | Solution |
| --- | --- | --- |
| Hard-to-read JSON snippet | `prettyPrint` not applied | Use `preprocessResponse(prettyPrint())` |
| Token remains in raw request | Only omitted descriptor, did not sanitize raw message | Use dummy fixture and request preprocessor |
| Removed header still appears in real response | Confused processor with application filter | Processor only affects snippets; fix server if needed |
| Assertion passes despite normalized snippet | Treated placeholder as proof of server value | Assert on real message, review snippets separately |
| Other data got replaced | Regex or processor too broad | Narrow the rule and inspect output |
| Header needing documentation is missing | Used remove instead of replace | Keep header name and replace its value |
| Snippets change on every build | Dynamic timestamp/ID not normalized | Stabilize fixture or preprocessor |
| cURL still has token even though HTTP snippet is clean | Only checked one output type | Review derived snippets |
| Preprocessor does not run | Attached at wrong place or wrong client API | Confirm document hook/filter |
| Documentation has stale output | Did not clean or test did not run | Clean, run tests, and render in the same lifecycle |

## 13. Practice Exercise

Create documentation for the `GET /api/accounts/me` endpoint. The test uses a dummy token and a dynamic request ID; the response may contain `Set-Cookie` from test middleware.

**Tasks:**

1. Configure a documentation test with MockMvc or an appropriate test client.
2. Send the request using a dummy token without reading real environment secrets.
3. Assert status, a body field, and the presence of the request ID on the real response.
4. Use a request preprocessor to replace `Authorization` with a placeholder.
5. Use a response preprocessor to remove `Set-Cookie` and normalize the request ID.
6. Add request/response header descriptors for contract headers.
7. Run the test and inspect raw HTTP, cURL, HTTPie, and header table snippets.
8. Confirm the fixture token is gone and the request ID has a stable sample value.
9. Include snippets in AsciiDoc or use a snippet insertion pipeline if targeting Markdown.
10. Run a clean build and add an output verification step to CI.

**Completion criteria:** tests verify the real message; preprocessors only normalize the recorded copy; required headers remain documented; sensitive credentials/cookies do not leak into snippets; documentation is rendered from fresh test output.

## 14. Takeaways

- Preprocessors transform requests/responses used to generate snippets; they are not application middleware.
- `preprocessRequest(...)` processes the recorded request; `preprocessResponse(...)` processes the recorded response.
- `prettyPrint()` formats payloads; `removeHeaders(...)` removes headers from snippets; `modifyHeaders()` modifies header values in the recorded copy; `replacePattern(...)` replaces pattern-matching content.
- Assertions still verify real requests/responses; preprocessors do not alter the message clients receive and do not replace assertions.
- Descriptors explain fields/headers/parameters; preprocessors normalize messages; raw snippets show processed examples.
- Choose processors deliberately, check their order, and review all derived snippets before publishing.
- Connect tests, preprocessors, snippets, Asciidoctor/Markdown, and CI so documentation is reproducible and does not leak sensitive data.
