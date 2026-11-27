# http-request, http-response, and curl-request

## 1. Roles of the Three Snippets

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Default Snippets** chapter, HTTP tests generate documentation fragments to describe the REST API contract. Three snippets commonly used together are:

| Snippet | Question It Answers | Typical Audience |
| --- | --- | --- |
| `http-request.adoc` | Which HTTP request did the client send? | Developers, API debuggers, HTTP contract reviewers |
| `http-response.adoc` | Which HTTP response did the server return? | Developers, API integrators, status/header/body verifiers |
| `curl-request.adoc` | What cURL command can resend that request? | API integrators, people testing the API from a terminal |

These three files describe the same operation recorded by the test, in three different forms. `http-request` is the request message at the HTTP level; `http-response` is the response message; `curl-request` is the CLI command that reproduces the request. They complement each other rather than representing three independent API calls.

Spring REST Docs generates these snippets when the test executes a request and invokes the documentation mechanism, typically `document(...)`. Adding the dependency to the project without calling `document(...)` in a test will not automatically generate snippets for an endpoint. The actual content depends on the method, URI, headers, body, response, and URI/preprocessor configuration on the operation.

Examples in this lesson use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. Similar principles apply to WebTestClient and REST Assured, though test syntax and integration packages vary by client.

## 2. http-request.adoc: The HTTP Message Sent by the Test

`http-request.adoc` represents the request as an HTTP message. It helps readers inspect the method, request target, HTTP version, headers, and body recorded by the operation.

GET request example:

```http
GET /api/products/42 HTTP/1.1
Accept: application/json
Host: api.example.com
```

POST request with body example:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json
Host: api.example.com

{"name":"Mechanical Keyboard","price":89.5}
```

Elements to inspect:

- **Method**: GET, POST, PUT, PATCH, DELETE, or another method sent by the test.
- **Request target/path**: the path and query string. Path templates may have already been expanded with actual parameter values.
- **HTTP version**: the protocol version recorded in the snippet.
- **Headers**: e.g., Accept, Content-Type, Authorization, If-Match, or application-added headers.
- **Body**: the payload sent to the server, if the request has a body.

For a request with a query string, the message looks like:

```http
GET /api/products?category=keyboard&active=true HTTP/1.1
Accept: application/json
```

The snippet shows how the actual request was constructed. It does not explain the business meaning of category, active, or headers on its own. To generate a table describing parameters/headers, declare dedicated descriptors such as queryParameters(...) or requestHeaders(...).

## 3. http-response.adoc: The HTTP Message Returned by the Server

`http-response.adoc` represents the response received after the test sends the request. It usually includes the status line, response headers, and body.

Successful response example:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 47

{"id":42,"name":"Mechanical Keyboard"}
```

Resource creation example:

```http
HTTP/1.1 201 Created
Location: /api/products/42
Content-Type: application/json

{"id":42,"name":"Mechanical Keyboard"}
```

Resource not found example:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"title":"Not Found","status":404}
```

When reading the response, the status code indicates the HTTP-level outcome; headers provide metadata such as Content-Type, Location, ETag, Cache-Control; the body contains data or error details if the endpoint returns a body.

Not every response has a body. An endpoint returning 204 No Content may have only status and headers. `http-response.adoc` is still useful because it records the HTTP result even without JSON.

The snippet reflects the response received by the test; it does not prove that every possible response of the endpoint has been tested. Write assertions for important status codes/headers/bodies and create separate operations for success, not found, unauthorized, or validation failure.

## 4. curl-request.adoc: Command to Resend the Request

`curl-request.adoc` converts the request recorded by the test into a cURL command. Example:

```bash
curl 'https://api.example.com/api/products/42' \
  -i \
  -H 'Accept: application/json'
```

With POST JSON:

```bash
curl 'https://api.example.com/api/products' \
  -i \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Mechanical Keyboard","price":89.5}'
```

| cURL Part | Meaning |
| --- | --- |
| Quoted URL | Request address and path/query |
| -i | Displays response headers along with the response body |
| -X POST | Specifies the method when the method needs to be shown explicitly |
| -H 'Name: value' | Sends an HTTP header |
| -d '...' | Sends body data |
| --data-binary | Sends the body as binary data |

REST Docs generates this command from the recorded operation. Readers can copy and run it in a terminal, though the URL, token, and test data may need to be adapted to their environment.

### How Do cURL and HTTP Request Differ?

`http-request.adoc` shows the request as an HTTP message; `curl-request.adoc` shows the command to construct the request using the cURL tool.

| Comparison | http-request.adoc | curl-request.adoc |
| --- | --- | --- |
| Format | HTTP message | Shell command line |
| Focus | Protocol structure | How to resend the request |
| Copy and run directly? | Not a shell command | Yes, after adjusting host/credentials if needed |
| Used when | Reviewing/debugging the protocol | Trying out the API or sharing examples |

## 5. Example Generating All Three Snippets with MockMvc

### Dependencies

For a Spring MVC application using Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Illustrative controller:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductResponse find(@PathVariable long id) {
        return new ProductResponse(id, "Mechanical Keyboard");
    }

    record ProductResponse(long id, String name) {}
}
```

### Test and document(...)

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets/products")
class ProductDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void findProduct() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 42)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
            .andDo(document("products-find"));
    }
}
```

When the test passes, the files focused on in this lesson are located under:

```text
build/generated-snippets/
  products/
    products-find/
      http-request.adoc
      http-response.adoc
      curl-request.adoc
```

REST Docs can also generate other default snippets for the operation, such as HTTPie and body snippets. This lesson focuses on the three files above.

`outputDir` is the root directory; `products-find` is the operation ID passed to `document(...)` and becomes the subdirectory. If outputDir is omitted, Spring Boot uses the default based on the build tool in common configurations. If the operation ID changes, include paths in the documentation must also change.

### Adding Descriptors for Parameters and Fields

The three basic HTTP snippets do not automatically generate tables explaining parameters or JSON fields. For more complete documentation, add descriptors:

```java
.andDo(document("products-find",
    pathParameters(
        parameterWithName("id")
            .description("Product identifier")
    ),
    responseFields(
        fieldWithPath("id").description("Product ID"),
        fieldWithPath("name").description("Product name")
    )
));
```

Then the operation directory also gets path-parameters.adoc and response-fields.adoc. Descriptors complement the raw request/response: HTTP snippets show the data sent/received, while descriptors generate tables explaining the contract.

## 6. Effects of Method, URI, Headers, and Body

The three snippets are generated from the recorded operation, so changing the request changes the corresponding content.

| Change in Test | http-request.adoc | http-response.adoc | curl-request.adoc |
| --- | --- | --- | --- |
| Change GET to POST | Method changes | Response may change status/header/body | cURL command reflects POST |
| Add query parameter | Request target includes query string | Response may differ due to parameter | cURL URL includes query |
| Add Accept | Request header changes | May change content negotiation/response | Adds header option |
| Add Content-Type | Request header changes | Result depends on how server reads body | Includes corresponding header |
| Add JSON body | Request body appears | Server may return different data/status | Command includes body sending part |
| Configure snippet URI | URI in message changes | URI/host may be normalized | URL in cURL command changes |

Do not confuse effects in snippets with effects on the application. Changing uriHost in REST Docs configuration only changes the recorded URI; it does not cause the client to send requests to the new host.

## 7. Normalizing URIs and Protecting Sensitive Information

When using RANDOM_PORT, the actual request may go to localhost with a dynamic port. Putting that raw address into public documentation makes cURL examples unsuitable for API integrators.

You can configure the displayed URI in Spring REST Docs:

```java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets/products",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
```

Snippets can display the public host while tests still call the local embedded server. The uriScheme, uriHost, and uriPort values do not enable TLS and do not change the server port.

If there is an Authorization header, cookie, or sensitive data, do not put real credentials into snippets. Use dummy tokens dedicated to tests and redact request headers before writing documentation. cURL is a command that can be copied directly, so inspect it carefully to avoid leaking tokens or internal URLs.

## 8. Including the Three Snippets in Asciidoctor

Place a source file, for example src/docs/asciidoc/products.adoc:

```asciidoc
= Products API
:toc: left

== Find product

=== HTTP request
include::{snippets}/products/products-find/http-request.adoc[]

=== cURL
include::{snippets}/products/products-find/curl-request.adoc[]

=== HTTP response
include::{snippets}/products/products-find/http-response.adoc[]
```

The {snippets} attribute must point to the root directory build/generated-snippets. The path after the attribute must match outputDir and the operation ID. In this example:

- Root directory: build/generated-snippets.
- Custom output: products.
- Operation ID: products-find.
- HTTP request path: build/generated-snippets/products/products-find/http-request.adoc.

There is no need to include every snippet on every page. Integration guides might prioritize cURL and response fields; internal debugging docs might show raw request/response messages and headers.

## 9. Gradle, Maven, and CI

Gradle Groovy DSL example:

```groovy
configurations {
    asciidoctorExt
}

dependencies {
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    attributes 'snippets': snippetsDir.get().asFile
}
```

Run a clean build:

```bash
./gradlew clean test asciidoctor
```

Gradle needs to know that test produces snippets and Asciidoctor consumes that directory. When tests fail, the documentation build step should not use stale snippets to produce new artifacts.

With Maven, the Asciidoctor Maven Plugin needs to read target/generated-snippets; the documentation goal must run after the test group that generates snippets. If snippets come from Failsafe integration tests, place the compilation step after those tests rather than in an earlier phase.

CI should run tests and build documentation in the same pipeline; only upload/publish HTML after both succeed. Avoid skipping tests with -x test or -DskipTests if required snippets are only generated by tests.

## 10. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Missing http-request.adoc | Test has not called document(...), did not run, or stopped before documentation step. | Check test report and placement of andDo(document(...))/corresponding API. |
| Request lacks expected query string | Test builds a different URI than intended or passes parameters incorrectly. | Inspect actual URI in test and snippet after running. |
| http-response.adoc has different status than designed | Application returns a different status or test does not assert status. | Add status assertion and fix handler/contract or documentation to match expected result. |
| cURL fails on reader's environment | Local host/port, dummy token, or environment-dependent data. | Configure public URI and instruct readers to substitute credentials/data. |
| cURL is missing body | Request sends no body or body was created in another operation. | Check method, content, and documented operation. |
| Request contains sensitive header | Test records real token/cookie. | Redact header or use dummy test data. |
| Asciidoctor cannot find snippet | Wrong snippets attribute, changed outputDir, or mismatched operation ID. | Compare actual file paths against include directives. |
| Snippet shows localhost/dynamic port | URI not normalized in REST Docs. | Configure uriScheme, uriHost, uriPort, or preprocessor. |

## 11. Hands-on Exercise

Create two operations for the Catalog API:

1. GET /api/products/{id}: assert status 200, send Accept, record http-request, http-response, and curl-request.
2. POST /api/products: send a JSON body with Content-Type, verify status 201 and Location; regenerate the three snippets.
3. Compare the GET and POST requests in the snippet directory. Point out where method, headers, URI, and body differ.
4. Add path parameter and request/response field descriptors; identify the additional files that appear.
5. Configure a public URI in REST Docs, run the test on a local port, and check the cURL snippet.
6. Include all three snippets in Asciidoctor, run clean test asciidoctor, then verify that HTML contains the new request, response, and cURL command.

**Completion criteria:** explain the differences among the three snippets; read method/path/headers/body and status/response; understand how cURL reproduces the request; generate and include the right files by operation ID; documentation does not leak credentials or depend on local ports.

## 12. References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
