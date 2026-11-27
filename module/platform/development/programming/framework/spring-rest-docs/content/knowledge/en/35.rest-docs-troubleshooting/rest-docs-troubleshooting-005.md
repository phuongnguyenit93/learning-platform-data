# URI Contains localhost or Unexpected Port

## 1. Why Do Snippets Show `localhost` or Random Ports?

Spring REST Docs creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. When tests run, requests often go through a local address, an embedded server, or a test client with its own base URI. Consequently, `http-request.adoc`, `curl-request.adoc`, or `http-response.adoc` snippets sometimes show URIs such as:

```http
GET http://localhost:53821/api/books/42 HTTP/1.1
Host: localhost:53821
```

In published documentation, the team may want to display:

```http
GET https://api.example.com/api/books/42 HTTP/1.1
Host: api.example.com
```

Random ports typically come from an embedded server running on a random port; `localhost` is an internal test address, not the API's public host. The URI in a snippet reflects the request sent by the test or the request metadata provided by the test client. It does not automatically know the production domain.

This is usually a **documentation example normalization** issue rather than an endpoint bug. Distinguish the actual URI used to send the test request from the representative URI you want to publish. Do not alter server configuration or production DNS just to make snippets look prettier.

## 2. Identifying Where the URI Comes From

Different test clients build request URIs in different ways:

| Test client | Common source of host/port | What to check |
| --- | --- | --- |
| MockMvc | Mock servlet request and test setup; default URI sometimes contains `localhost`. | URI passed to `get/post`, servlet context path, and request builder. |
| WebTestClient | Configured client base URL or URI; bind-to-server may use a random port. | `baseUrl`, `bindToServer`, `bindToApplicationContext`, and per-request URI. |
| REST Assured | `baseURI`, `port`, `basePath`, or `RequestSpecification` configuration. | Shared specification, random port, and URI passed to `.get(...)`. |

Before preprocessing, read `http-request.adoc` to see which exact part is unwanted: scheme, host, port, path, query, or the `Host` header. Normalize only what is necessary; do not strip path or query parameters that are part of the API contract.

## 3. Normalizing URIs with a Request Preprocessor

Spring REST Docs provides `modifyUris()` to transform URI components in the documented request. You can apply `preprocessRequest(...)` inside `document(...)`:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

filter(document("books-get",
        preprocessRequest(
                modifyUris()
                        .scheme("https")
                        .host("api.example.com")
                        .removePort())));
```

This example normalizes the scheme to `https`, the host to `api.example.com`, and removes the port from the URI written to snippets. The path, query string, and other URI components are preserved. If the API is published on a non-default port, you can set the intended port via `port(...)` instead of removing it.

The preprocessor only affects the request representation used to generate documentation. It does not change the address the test called, the listening server, or any proxy/DNS configuration.

## 4. Sharing Preprocessors Across MockMvc, WebTestClient, and REST Assured

Because preprocessors attach at the document operation level, the usage pattern is similar across different test clients.

### MockMvc

```java
mockMvc.perform(get("/api/books/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort())));
```

### WebTestClient

```java
webTestClient.get()
        .uri("/api/books/{id}", 42)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("books-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort())));
```

### REST Assured

```java
given(this.specification)
        .filter(document("books-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort())))
.when()
        .get("/api/books/{id}", 42)
.then()
        .statusCode(200);
```

These snippets are abbreviated to show where the preprocessor attaches. Use the filter/configuration and static imports suitable for your Spring REST Docs module, test client, and project version.

## 5. Choosing the Port: Remove or Replace with the Published Port?

If the public API uses HTTPS on the default port 443, the URI normally does not need to display a port. In that case, `.removePort()` is appropriate. If the API is published on another port, set it explicitly:

```java
preprocessRequest(
        modifyUris()
                .scheme("https")
                .host("api.example.com")
                .port(8443))
```

Only include a port in documentation when clients actually need to use it. Never publish a random port like `53821` from an embedded server in API docs, because that value can change on every test run.

| Test URI | Desired documentation URI | Handling |
| --- | --- | --- |
| `http://localhost:53821/api/books/42` | `https://api.example.com/api/books/42` | Change scheme/host and remove port. |
| `http://127.0.0.1:8080/api/books` | `https://api.example.com:8443/api/books` | Change scheme/host and set port 8443. |
| `http://localhost/api/books` | `https://api.example.com/api/books` | Change scheme/host; port may not need adjustment. |

## 6. Do Not Confuse the URI with the `Host` Header

The URI and the HTTP `Host` header are two separate parts of the request representation. `modifyUris()` normalizes the URI displayed in request snippets. Depending on how the test client builds the request and snippet templates, the `Host` header may still reflect the original value or be processed separately.

Inspect both lines in `http-request.adoc`:

```http
GET https://api.example.com/api/books/42 HTTP/1.1
Host: localhost:53821
```

If the URI is right while `Host` still shows a test address, decide whether that header should be documented. If it is not something clients need to configure explicitly, you can remove the header from snippets using an appropriate request preprocessor or customize the template to match your documentation goals. Do not fabricate a production header value if doing so misrepresents the request a client actually needs to send.

When an API relies on virtual hosting or routing via the `Host` header, the `Host` value may be part of the public contract. In that case, document the exact required host and verify it in corresponding tests.

## 7. Preserving Path, Query, and Context Path

Normalizing the host does not mean stripping the rest of the URI. For example:

```text
Test URI:
http://localhost:53821/store/api/books/42?view=full

Document URI:
https://api.example.com/store/api/books/42?view=full
```

Context path `/store`, API path `/api/books/42`, and query `view=full` are preserved. If the documentation intends to omit the context path or change the API version, that is a separate decision and must be handled deliberately. Never strip query parameters, as they can be critical inputs to the operation.

If the URI in the snippet is missing path segments, inspect the request builder, `basePath`, or context path before using `modifyUris()`. The preprocessor rewrites the URI as configured; it does not fix incorrect endpoint mappings or requests sent to the wrong URL by the test.

## 8. Using a Shared Preprocessor to Avoid Repetition

If many operations share the same public base URI, create a helper:

```java
private static OperationRequestPreprocessor publicApiUri() {
    return preprocessRequest(
            modifyUris()
                    .scheme("https")
                    .host("api.example.com")
                    .removePort());
}
```

Then:

```java
filter(document("books-get",
        publicApiUri(),
        responseFields(
                fieldWithPath("id").description("Book ID"))));
```

```java
filter(document("orders-create",
        publicApiUri(),
        requestFields(
                fieldWithPath("customerId").description("Customer ID"))));
```

Place the helper in shared test support so every operation normalizes consistently. If the documentation covers multiple API hosts or versions, pass configuration per service rather than hard-coding a single host for all.

## 9. Selecting the Host by Build Environment

Not every project has a single published hostname. You can configure the host via a Gradle/Maven property or test system property, provided the documentation output remains reproducible.

Example Java helper reading a property with a safe documentation default:

```java
private static String docsApiHost() {
    return System.getProperty("docs.api.host", "api.example.com");
}

private static OperationRequestPreprocessor publicApiUri() {
    return preprocessRequest(
            modifyUris()
                    .scheme("https")
                    .host(docsApiHost())
                    .removePort());
}
```

You can pass the property when running tests:

```bash
./gradlew test -Ddocs.api.host=api.example.com
```

If sourcing the host from an environment or CI variable, do not let internal or staging hostnames slip into public documentation. Set an explicit default and inspect snippets in the build artifact before publishing. Never place secrets or tokens into properties written to snippets.

## 10. Normalizing Response Links and Absolute URLs

A hypermedia response may contain absolute links in JSON, for example:

```json
{
  "_links": {
    "self": { "href": "http://localhost:53821/api/books/42" }
  }
}
```

`modifyUris()` in `preprocessRequest(...)` handles the request snippet URI; do not assume it automatically replaces every absolute URL inside the response body. If response JSON contains `localhost` in `href`, inspect how links are generated:

- How does the server build links from the request host and scheme?
- Do tests send forwarded headers (`X-Forwarded-Host`, `X-Forwarded-Proto`), and does the application trust them?
- Can the public base URI be configured in application or test settings?
- Should a response preprocessor replace the host solely for documentation?

A response preprocessor can alter body content, for instance, but take care to replace only the host values that need normalization without distorting payload semantics. The best approach is to configure link generation to match how the application is intended to be deployed and assert the response `href` in tests.

Do not assume response hypermedia links are normalized just because you applied `modifyUris()` on the request. Open `http-response.adoc` and verify the actual JSON/XML.

## 11. Avoid Misleading HTTP Examples

A preprocessor is a documentation presentation tool, not a way to hide configuration bugs. Before changing the host or port, confirm:

- The request path and query remain accurate.
- The published scheme/host is the real endpoint API consumers will call.
- The port is removed only when it does not need to be published.
- The `Host` header does not conflict with the URI if that header is displayed.
- Absolute links in responses are verified separately.
- cURL and HTTP request examples do not leak internal tokens or cookies.

If the documentation is meant as a guide for running local integration tests, you can keep `localhost` and explain that the port is dynamically allocated. If the documentation is a public API reference, normalizing to the public base URI is usually much easier to use. Choose based on the target audience and documentation purpose.

## 12. Diagnosing When the URI Remains Wrong After Preprocessing

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Snippet still contains `localhost` | Preprocessor not passed to the right `document(...)` call, or operation uses another configuration. | Check that operation's filter/document call. |
| Host is right, port still remains | Forgot `removePort()`, or `port(...)` is set by another configuration. | Pick one explicit port strategy and inspect URI output. |
| Scheme is still `http` | Preprocessor not applied or overridden per operation. | Verify `.scheme("https")` is inside the active request preprocessor. |
| URI is right, `Host` header is wrong | Header is recorded separately and does not match the rewritten URI. | Inspect the request headers snippet and handle the header deliberately. |
| Request URI is right, response `_links` still has `localhost` | Response body contains server-generated absolute URLs. | Check link generation/forwarded headers or a dedicated response preprocessor. |
| Path/query disappeared | Request builder or custom preprocessing altered more than the host. | Compare raw request with snippet; preserve path and query segments. |
| Right locally, wrong in CI | Different host property/environment, or operation bypasses shared helper. | Print non-sensitive configuration and standardize properties in CI. |
| Random port reappears on one operation | That operation does not use the shared preprocessor. | Use the shared helper and audit all document calls. |

## 13. End-to-End Troubleshooting Workflow

1. Run tests and open `http-request.adoc` for the affected operation.
2. Identify whether the wrong part is the scheme, host, port, path, query, or `Host` header.
3. Locate the URI configuration source in MockMvc/WebTestClient/REST Assured.
4. Decide on the public base URI the documentation should publish.
5. Attach `preprocessRequest(modifyUris()...)` to the operation or a shared helper.
6. Re-run tests to regenerate snippets; never edit generated files manually.
7. Re-read `http-request.adoc`, `curl-request.adoc`, and any related header snippets.
8. Inspect `http-response.adoc` separately if hypermedia `href` links also contain `localhost`.
9. Render Asciidoctor and verify HTML/PDF displays the right URI.

## 14. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Public docs expose `localhost` | Snippets record the raw test URI. | Use a request preprocessor to normalize scheme/host. |
| Random port appears | Embedded server uses a random port. | Use `.removePort()` or set the published port. |
| Only some operations are normalized | Preprocessor attached to only a few document calls. | Create a shared helper and apply it consistently. |
| `Host` header mismatches URI | URI and header are processed separately. | Inspect header snippets, document or preprocess per contract. |
| JSON `_links.href` still shows `localhost` | Request preprocessor does not rewrite response bodies. | Fix link generation or use controlled response preprocessing. |
| Staging domain appears in public docs | Wrong CI/environment property. | Use a dedicated documentation property with a safe default/allowlist for published hosts. |
| Manual edits to snippets vanish after tests | Generated output gets overwritten. | Update the preprocessor or template in test sources. |

## 15. Practical Checklist

- [ ] Identified whether the wrong URI is in the request snippet or in an absolute `href` in the response body.
- [ ] Checked the test client's host/port source.
- [ ] Selected the public scheme, host, and port appropriate for the published documentation.
- [ ] Applied `preprocessRequest(modifyUris()...)` for request URIs where appropriate.
- [ ] Preserved path, query, and context path.
- [ ] Explicitly decided whether to remove the port or set the published port.
- [ ] Checked the `Host` header separately if it appears in snippets.
- [ ] Checked response hypermedia links separately; did not assume request preprocessors edit the body.
- [ ] Operations share a common helper or unified configuration.
- [ ] Re-ran tests, read newly generated snippets, and rendered HTML/PDF before publishing.
- [ ] Ensured no internal hostnames, tokens, or sensitive cookies leak into documentation.

URIs containing `localhost` or random ports usually originate from the test environment. Spring REST Docs lets you normalize request URIs with `preprocessRequest(modifyUris()...)` so documentation shows the appropriate public scheme, host, and port without changing the executed test request. Inspect the URI, `Host` header, and absolute response links separately; each may require its own handling. After preprocessing, always re-run tests and inspect the new snippets before rendering documentation.

## References

- [Spring REST Docs – Preprocessors](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs – Preprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs – OperationRequestPreprocessor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/OperationRequestPreprocessor.html)
