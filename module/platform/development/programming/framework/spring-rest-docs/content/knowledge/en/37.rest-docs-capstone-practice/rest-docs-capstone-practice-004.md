# Documenting Resources with Path Parameters and Headers

## 1. Objective

Spring REST Docs creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. This practice uses MockMvc to document the `GET /orders/{orderId}` resource, including path parameter, request headers, and response headers; then it includes the snippets into AsciiDoc.

Sample request:

```http
GET /orders/{orderId}
Accept: application/json
X-Request-Id: req-2026-0042
```

Sample response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-42-v3"
X-Request-Id: req-2026-0042

{"id":"42","status":"PAID","total":125000}
```

## 2. Distinguishing Path Parameters and Headers

| Element | Example | Role |
| --- | --- | --- |
| Path parameter | `orderId` in `/orders/{orderId}` | Selects the resource |
| Request header | `Accept` | Media type desired by the client |
| Request header | `X-Request-Id` | Correlation ID |
| Response header | `Content-Type` | Media type of the response body |
| Response header | `ETag` | Representation validator |
| Response header | `X-Request-Id` | Correlation ID echoed by the server |

A path parameter is part of the URI template; a header is metadata of the HTTP message. In REST Docs, use `pathParameters` for path variables, `requestHeaders` for request headers, and `responseHeaders` for response headers. Do not use `requestParameters` for path variables.

## 3. Test and REST Docs Configuration

The example assumes the project already has Spring REST Docs MockMvc, JUnit 5, and Spring Boot test configured. The common dependency is `spring-restdocs-mockmvc` in test scope.

Complete test:

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.PathParametersSnippet.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class OrderDocumentationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getOrderDocumentsPathAndHeaders() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "42")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "req-2026-0042"))
            .andExpect(status().isOk())
            .andDo(document("orders-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Identifier of the order")
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Media type desired by the client"),
                    headerWithName("X-Request-Id")
                        .description("Identifier used to trace the request")
                ),
                responseHeaders(
                    headerWithName("Content-Type")
                        .description("Media type of the response body"),
                    headerWithName("ETag")
                        .description("Validator of the order representation"),
                    headerWithName("X-Request-Id")
                        .description("Trace identifier echoed by the server")
                )
            ));
    }
}
```

The test snippet illustrates descriptors. The application must actually return the described response headers. If `ETag` or `X-Request-Id` is absent from the response, the header documentation snippet will fail or fail to reflect real behavior.

Static imports can be added automatically by your IDE. If the REST Docs release you are using places factories or snippet types in a different package, use the API of that exact release and verify with the compiler.

## 4. Preparing the Endpoint and Stable Data

The endpoint needs to return stable JSON and echo the correlation ID. Controller sketch:

```java
@GetMapping(value = "/orders/{orderId}", produces = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<OrderResponse> getOrder(
        @PathVariable String orderId,
        @RequestHeader("X-Request-Id") String requestId) {
    OrderResponse order = orderService.findById(orderId);
    return ResponseEntity.ok()
            .eTag(order.etag())
            .header("X-Request-Id", requestId)
            .body(order);
}
```

`OrderResponse` and `orderService` belong to the application domain. Create a fixed fixture for order 42 so the body and `ETag` do not change across runs. If `X-Request-Id` is a required header, also test validation when the header is missing. Never use real tokens, passwords, or personal data in examples.

## 5. Documenting the Path Parameter

Use `pathParameters` and `parameterWithName`:

```java
pathParameters(
    parameterWithName("orderId")
        .description("Identifier of the order")
)
```

The descriptor name must match the placeholder in the URI template: `{orderId}`. If the test calls `/orders/{id}` while the descriptor uses `orderId`, REST Docs cannot match the parameter properly.

With multi-level endpoints such as `/customers/{customerId}/orders/{orderId}`, describe both variables in the same `pathParameters` snippet. Use a URI template and pass separate values:

```java
get("/customers/{customerId}/orders/{orderId}", "C-7", "42")
```

## 6. Documenting Request Headers

Use `requestHeaders` and `headerWithName`:

```java
requestHeaders(
    headerWithName("Accept").description("Media type desired by the client"),
    headerWithName("X-Request-Id").description("Request trace identifier")
)
```

Header names must match the headers actually sent. HTTP headers are case-insensitive, but documentation should use consistent casing.

For optional headers, you can mark them `optional`:

```java
headerWithName("X-Client-Version")
    .description("Client version if provided")
    .optional()
```

`optional` only states that the header may be absent in the documented request; it does not replace validation and does not send the header automatically. If documenting `Authorization`, use a placeholder and keep real bearer tokens out of snippets.

## 7. Documenting Response Headers

Use `responseHeaders` and `headerWithName`:

```java
responseHeaders(
    headerWithName("Content-Type").description("Response media type"),
    headerWithName("ETag").description("Representation validator"),
    headerWithName("X-Request-Id").description("Request trace identifier")
)
```

You can verify the actual response:

```java
.andExpect(header().exists("ETag"))
.andExpect(header().string("X-Request-Id", "req-2026-0042"))
```

`Content-Type` is typically set by the framework when a controller returns JSON. `ETag` must be generated by the application or infrastructure. Do not add an `ETag` descriptor if the endpoint does not emit an `ETag`.

## 8. Combining with Payload Snippets

One operation can generate multiple snippet types. If the JSON response has fields, add `responseFields`:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    fieldWithPath("total").description("Total amount")
)
```

This snippet requires static imports for `responseFields` and `fieldWithPath`. Only include `response-fields` when the test has requested generating that snippet. If you want to document the raw body, include the default `http-request` and `http-response` snippets.

## 9. Generating and Inspecting Snippets

Run a clean test:

```bash
./mvnw clean test
```

Or Gradle:

```bash
./gradlew clean test
```

Output depends on the build configuration. Maven commonly uses `target/generated-snippets`; Gradle typically uses `build/generated-snippets`.

With operation ID `orders-get`, expected files may include:

```text
orders-get/
├── curl-request.adoc
├── http-request.adoc
├── http-response.adoc
├── path-parameters.adoc
├── request-headers.adoc
└── response-headers.adoc
```

The actual list depends on enabled snippet handlers. If you add `responseFields`, `response-fields.adoc` may also be present. Do not assume a file appears if the test has not requested the corresponding snippet.

Check:

- Is the `orders-get` directory present?
- Does the path parameter snippet contain `orderId`?
- Does the request header snippet contain `Accept` and `X-Request-Id`?
- Does the response header snippet contain `Content-Type`, `ETag`, and `X-Request-Id`?
- Has sensitive data been removed?
- Is the output freshly generated after a clean build?

## 10. Authoring AsciiDoc

Create `src/docs/asciidoc/orders.adoc` or add a section to `index.adoc`:

```asciidoc
== Get order

Retrieve an order by its identifier.

=== HTTP request
include::{snippets}/orders-get/http-request.adoc[]

=== Path parameters
include::{snippets}/orders-get/path-parameters.adoc[]

=== Request headers
include::{snippets}/orders-get/request-headers.adoc[]

=== HTTP response
include::{snippets}/orders-get/http-response.adoc[]

=== Response headers
include::{snippets}/orders-get/response-headers.adoc[]

=== Response fields
include::{snippets}/orders-get/response-fields.adoc[]
```

Only include `response-fields` if the test generated that file. Every include path must match the operation ID and generated snippets directory.

Run Asciidoctor after tests:

```bash
./mvnw prepare-package
```

Or Gradle:

```bash
./gradlew asciidoctor
```

## 11. Verifying Results and Troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Missing path parameter | Descriptor does not match placeholder or test does not use a URI template | Use `/orders/{orderId}` and descriptor `orderId` |
| Request header is not documented | Header was not sent or handler was not declared | Send the header and add `requestHeaders` |
| Response header is missing | Endpoint does not return the described header | Check response; fix contract or descriptor |
| `ETag` does not exist | Application does not generate an `ETag` | Remove descriptor or implement `ETag` per contract |
| Snippet does not appear | Test did not run or snippet handler is missing | Check the test and descriptors |
| AsciiDoc include error | Wrong operation ID/path or file not yet generated | Check `orders-get` and build order |
| Header contains a real token | Test uses real credentials | Use fixtures/placeholders and mask sensitive data |

Do not fix includes to point to stale snippets just to make the build pass. Use a clean build and verify the current tests generate all required output.

## 12. Extension Exercises

1. Add `GET /customers/{customerId}/orders/{orderId}`; document both path parameters.
2. Add `X-Tenant-Id` and document required/optional according to the API contract.
3. Add the `Cache-Control` response header and verify the actual value.
4. Create a 404 test; document the error response headers if they are part of the contract.
5. Document `Authorization` while ensuring snippets contain no real bearer tokens.
6. Assemble both operations into the same AsciiDoc page and check navigation.
7. Run a clean build in CI and verify the list of snippets.

**Completion criteria:** documentation test succeeds; `pathParameters` match the URI template; `requestHeaders`/`responseHeaders` describe real headers; snippets are generated under the right operation ID; AsciiDoc includes the right files and the HTML renders completely.

## 13. Self-Check Questions

**1. Which snippet is used to document a path variable?**

`pathParameters` with `parameterWithName`.

**2. Which snippet is used for request headers?**

`requestHeaders` with `headerWithName`.

**3. Which snippet is used for response headers?**

`responseHeaders` with `headerWithName`.

**4. Why must the descriptor match the URI template?**

REST Docs matches the path variable name against the placeholder in the request to generate the proper description.

**5. Can `ETag` be documented even if the response does not have an `ETag`?**

No. Descriptors must reflect the real response; if `ETag` is part of the contract, the endpoint must produce it and the test must verify it.

**6. Is it necessary to document every default header?**

No. Choose headers that matter to the contract and API consumers; avoid cluttering documentation with unstable infrastructure headers.

## References

- [Spring REST Docs — Request Parameters and Path Parameters](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#documenting-your-api-request-parameters): documenting path parameters and request parameters.
- [Spring REST Docs — Headers](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#documenting-your-api-headers): `requestHeaders`, `responseHeaders`, and header descriptors.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): configuring MockMvc and generating snippets.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing Spring MVC with MockMvc.
