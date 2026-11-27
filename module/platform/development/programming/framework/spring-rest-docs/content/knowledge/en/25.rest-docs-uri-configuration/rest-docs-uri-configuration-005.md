# REST Assured URI Customization with Spring REST Docs

## 1. Why Customize URIs in REST Assured?

REST Assured sends real HTTP requests to a running service. In tests, the service may start on loopback, a random port, or an internal hostname:

```text
http://localhost:53142/api/products/42
```

External API consumers may call the public endpoint:

```text
https://api.example.com/v1/products/42
```

Both URIs may represent the same operation, but they serve two different purposes. The first URI is the address the test needs to send requests to the service. The second URI is the address that should appear in public documentation. If snippets record the raw test address, generated curl commands may contain a random port or a hostname that only exists on the internal network.

When using REST Assured, distinguish two configuration layers:

- **REST Assured request configuration:** determines where the request is actually sent, via base URI, port, base path, and request specification.
- **Spring REST Docs URI preprocessing:** changes how the URI is presented in snippets after the operation has been executed.

Customizing the documented URI does not redirect requests to a different server. It only changes the request/response representation written into documentation. This is the focus of the **REST Assured URI customization** lesson in the **URI configuration** chapter of the **SPRING_REST_DOCS** module. This module generates verifiable REST API documentation from HTTP tests with MockMvc, WebTestClient, or REST Assured, producing snippets for requests/responses and compiling them with Asciidoctor/Markdown and build/CI.

After this lesson, you will be able to:

1. Configure REST Assured's request destination using `RequestSpecification`.
2. Use Spring REST Docs' URI preprocessor to normalize scheme, host, and port in snippets.
3. Apply request preprocessors and response preprocessors separately.
4. Distinguish the authority from base path, route, and query string.
5. Verify `http-request`, `curl-request`, and response snippets before publishing.

## 2. REST Assured Sends Real Requests

REST Assured is an HTTP client used in tests. When calling:

```java
given()
    .baseUri("http://localhost")
    .port(8080)
    .basePath("/api")
    .when()
    .get("/products/42");
```

the request is actually sent to:

```text
http://localhost:8080/api/products/42
```

REST Assured does not create simulated requests like MockMvc. Therefore, Spring REST Docs cannot apply MockMvc's URI defaults approach to the outgoing request. The URI in the operation comes from the actual HTTP exchange; to change the documented URI, preprocessing is required after the exchange and before writing snippets.

### 2.1. URI Components

| Component | Example | Related REST Assured Configuration |
| --- | --- | --- |
| Scheme | http | `baseUri` or absolute URL |
| Host | localhost | `baseUri` or absolute URL |
| Port | 53142 | `port` |
| Base path | /api | `basePath` |
| Resource path | /products/42 | Path passed to `get`, `post`, `patch` |
| Query | ?view=summary | `queryParam` or query string |

The example public URI `https://api.example.com:443/v1/products/42` has scheme `https`, host `api.example.com`, port `443`, base path `/v1`, and resource path `/products/42`. Do not confuse the base path with the host or port.

## 3. Configuring the Request Target with RequestSpecification

Spring REST Docs does not choose the server that REST Assured calls. That responsibility belongs to REST Assured.

Example using a dedicated `RequestSpecification` for tests:

```java
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.specification.RequestSpecification;

RequestSpecification requestSpec = new RequestSpecBuilder()
        .setBaseUri("http://localhost")
        .setPort(8080)
        .setBasePath("/api")
        .build();
```

Using the specification:

```java
given(requestSpec)
        .accept("application/json")
        .when()
        .get("/products/42")
        .then()
        .statusCode(200);
```

In test applications using a random port, obtain the port from the running test server or test configuration and pass it into `RequestSpecification`. Do not hard-code random ports into documentation.

### 3.1. Use RequestSpecBuilder Instead of Mutating Global State

REST Assured has static properties like `RestAssured.baseURI`, `RestAssured.port`, and `RestAssured.basePath`. This approach is concise:

```java
RestAssured.baseURI = "http://localhost";
RestAssured.port = 8080;
RestAssured.basePath = "/api";
```

However, static values affect subsequent tests and can cause conflicts when tests run in parallel or when each class needs a different server/port. `RequestSpecification` encapsulates configuration in an explicitly passed object:

```java
RequestSpecification localService = new RequestSpecBuilder()
        .setBaseUri("http://127.0.0.1")
        .setPort(serverPort)
        .setBasePath("/api")
        .build();
```

`serverPort` here must be the actual port the test server is listening on. Retrieve the value from the project's server startup mechanism.

## 4. Configuring Spring REST Docs for REST Assured

Spring REST Docs' REST Assured integration is registered as a REST Assured `Filter`. With JUnit 5, `RestDocumentationExtension` provides `RestDocumentationContextProvider` to configure snippet output:

```java
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.specification.RequestSpecification;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;

import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class ProductRestAssuredDocumentationTest {

    private RequestSpecification spec;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.spec = new RequestSpecBuilder()
                .setBaseUri("http://localhost")
                .setPort(8080)
                .setBasePath("/api")
                .addFilter(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

In this configuration:

1. `setBaseUri`, `setPort`, and `setBasePath` determine where tests send requests.
2. `documentationConfiguration(restDocumentation)` adds the filter that records operations and generates snippets.
3. Tests use `given(this.spec)` to reuse the configuration.

Test dependencies must include the corresponding integration module, typically `spring-restdocs-restassured`, alongside REST Assured and JUnit 5. The versions of Spring REST Docs and REST Assured must be compatible with the project's Spring/Java platform.

## 5. Using modifyUris() to Replace URIs in Snippets

Spring REST Docs provides `modifyUris()` in `org.springframework.restdocs.operation.preprocess.Preprocessors`. This preprocessor replaces one or more of the scheme, host, and port components of the documented URI.

For example, tests call a local server while public documentation uses HTTPS:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

given(this.spec)
        .filter(document("product-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .port(443)
                )))
        .when()
        .get("/products/42")
        .then()
        .statusCode(200);
```

Suppose the real request is sent to:

```text
http://localhost:8080/api/products/42
```

The request snippet generated after preprocessing has the URI:

```text
https://api.example.com:443/api/products/42
```

Default port 443 is often rendered without `:443`, depending on URI serialization; the final URL may appear as:

```text
https://api.example.com/api/products/42
```

The request is still sent to `localhost` on port `8080`. `modifyUris()` only replaces the URI used in documentation, without altering the network destination of the completed exchange.

### 5.1. Configuring the Port

If documentation needs a non-default public port:

```java
modifyUris()
        .scheme("https")
        .host("partner-api.example.com")
        .port(8443)
```

If the public URL has no explicit port:

```java
modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort()
```

Only choose a port matching the endpoint customers actually use. Never carry random or backend ports into public documentation.

## 6. Applying Preprocessors After the Operation Completes

This is an important distinction for REST Assured. REST Assured executes real HTTP exchanges; URI customization must happen after the operation on the service completes, but before Spring REST Docs creates snippets. Configuration can be attached directly to the `document` filter:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(this.spec)
        .filter(document("product-list",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .get("/products")
        .then()
        .statusCode(200);
```

`document(...)` is the filter from the REST Assured integration. The request preprocessor is passed into this filter to normalize the request operation before writing snippets.

### 6.1. Modifying URIs in Responses When Needed

Responses may contain absolute URIs, such as a `Location` header or hypermedia links. Using only `preprocessRequest(...)` will not modify URIs in the response. If the documentation contract requires public URIs in both the request and the response, apply both:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

given(this.spec)
        .filter(document("product-create",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                ),
                preprocessResponse(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .body("{\"name\":\"Keyboard\"}")
        .post("/products")
        .then()
        .statusCode(201);
```

`UriModifyingOperationPreprocessor` can modify URIs in the request URI, request headers/content, request part headers/content, and response headers/content. Therefore, if a response has an absolute URI in `Location` or body links, inspect the snippets after preprocessing to ensure the address is normalized properly.

Only apply response preprocessing when the response contract needs URI replacement. Do not mechanically replace arbitrary strings in responses; only URIs should be normalized.

## 7. Distinguishing baseURI/basePath from modifyUris()

These are two configuration groups that are easy to confuse:

| Configuration | When Does It Take Effect? | Does It Change the HTTP Target? | Does It Affect Snippet URIs? |
| --- | --- | --- | --- |
| setBaseUri(...) | When REST Assured builds the request | Yes | The recorded actual URI carries that base URI |
| setPort(...) | When REST Assured builds the request | Yes | The recorded actual URI carries that port |
| setBasePath(...) | When REST Assured builds the request | Yes | The recorded request path includes the base path |
| modifyUris().scheme(...) | When Spring REST Docs preprocesses the operation | No | Yes, replaces scheme in snippets |
| modifyUris().host(...) | When Spring REST Docs preprocesses the operation | No | Yes, replaces host in snippets |
| modifyUris().port(...) | When Spring REST Docs preprocesses the operation | No | Yes, replaces port in snippets |
| modifyUris().removePort() | When Spring REST Docs preprocesses the operation | No | Yes, removes port in snippets |

Correct example with local tests and public documentation:

```java
RequestSpecification spec = new RequestSpecBuilder()
        .setBaseUri("http://localhost")
        .setPort(8080)
        .setBasePath("/internal-api")
        .build();

given(spec)
        .filter(document("customer-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .get("/customers/42")
        .then()
        .statusCode(200);
```

Result:

- The test sends the request to `http://localhost:8080/internal-api/customers/42`.
- The preprocessor produces a snippet URI of `https://api.example.com/internal-api/customers/42`.

This example is only accurate if the public API actually exposes `/internal-api/customers/42`. If the public gateway uses `/v1/customers/42`, replacing host/scheme/port is not enough to turn an internal path into a public path. Configure test routes to match the external contract or organize dedicated confirmed documentation/paths.

## 8. Path, Query String, and URL Encoding

`modifyUris()` focuses on scheme, host, and port. It is not a tool for renaming resource paths, version prefixes, or query parameters.

Example:

```java
given(this.spec)
        .queryParam("q", "spring rest docs")
        .queryParam("page", 2)
        .filter(document("product-search",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .get("/products/search")
        .then()
        .statusCode(200);
```

The preprocessor replaces the authority while keeping the request's path and query:

```text
https://api.example.com/api/products/search?q=spring%20rest%20docs&page=2
```

Encoding details depend on how REST Assured builds query strings and URL encoding configuration. When documenting, use `queryParam(...)` to express parameter semantics and inspect `http-request.adoc`/`curl-request.adoc` after running tests. Do not manually concatenate query strings if parameter values contain characters requiring encoding.

### 8.1. When Public Path Differs from Internal Path

Example:

| Environment | Path |
| --- | --- |
| Internal backend | /internal/products/42 |
| Public gateway | /v1/products/42 |

If tests call the backend directly, snippets preprocessed only for host/scheme/port will still contain `/internal/products/42`. Do not use `modifyUris()` and assume the documentation now has the public route. You can test through a test gateway, or document the public route via verified documentation while keeping test snippets aligned with actual request/response payloads. Avoid rewriting paths with broad pattern replacements, as they can accidentally alter payloads, links, or data values.

## 9. Using Shared Preprocessors Across a Test Suite

If all operations need the same public authority, you can create a helper returning request/response preprocessors:

```java
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

final class PublicApiDocumentationUris {

    private PublicApiDocumentationUris() {}

    static OperationRequestPreprocessor publicRequestUri() {
        return preprocessRequest(
                modifyUris()
                        .scheme("https")
                        .host("api.example.com")
                        .removePort()
        );
    }

    static OperationResponsePreprocessor publicResponseUris() {
        return preprocessResponse(
                modifyUris()
                        .scheme("https")
                        .host("api.example.com")
                        .removePort()
        );
    }
}
```

Usage in tests:

```java
given(this.spec)
        .filter(document("product-detail",
                PublicApiDocumentationUris.publicRequestUri(),
                PublicApiDocumentationUris.publicResponseUris()
        ))
        .when()
        .get("/products/42")
        .then()
        .statusCode(200);
```

The benefit is that the public host is declared in one central place. If there are multiple API hosts, create per-service configurations or load values from test properties/environment. Avoid global static mutable variables that other tests could modify during parallel execution.

## 10. Using a Custom Preprocessor for a Single Operation

Not every operation needs the same authority. For example, a gateway dedicated to file uploads might have its own domain:

```java
given(this.spec)
        .filter(document("file-upload",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("upload-api.example.com")
                                .removePort()
                )))
        .when()
        .multiPart("file", new File("report.pdf"))
        .post("/files")
        .then()
        .statusCode(201);
```

Other operations can continue using `api.example.com`. Placing the preprocessor directly on the exception operation's filter expresses intent much more clearly than mutating the global REST Assured base URI.

## 11. Impact on Response Links and Location

URIs can appear outside the request line. A resource creation response might return:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/products/42
Content-Type: application/json

{
  "id": "42",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    }
  }
}
```

If public documentation needs the gateway URI:

```text
Location: https://api.example.com/api/products/42
```

Apply the response preprocessor alongside the request preprocessor as shown earlier. Then review `http-response.adoc`, `response-body.adoc`, and any related hypermedia snippets. Ensure the URI modifications match the links real clients will receive from the public API. If the application already returns the right public URI in production, consider testing through a gateway or adjusting application/proxy configuration instead of relying on snippet rewriting to mask incorrect runtime responses.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Actual requests go to public host instead of test server | Changed `baseURI` instead of preprocessing snippets only | Keep the test base URI; modify the URI inside the `document` filter |
| Snippet still contains localhost | `document` filter did not receive `preprocessRequest(modifyUris()...)` | Check the method overload and import the right preprocessor |
| Random port still appears | Only replaced scheme/host without setting or removing port | Use `port(...)` or `removePort()` |
| Request line is right but Location still has local host | Only preprocessed the request | Add `preprocessResponse(modifyUris()...)` if response URIs need normalization |
| Host is right but path is still internal route | `modifyUris()` does not change base path or resource path | Test via public gateway or determine the external path separately |
| Query string is double-encoded | Manually encoded before passing to `queryParam` | Pass raw values to REST Assured and inspect the generated URL |
| Parallel tests leak base URI/port | Used REST Assured static global configuration | Use a separate `RequestSpecification` per test/client |
| Response links altered unintentionally | Preprocessor modifies URIs inside response content | Apply response preprocessing only when needed and inspect snippets |
| API returns redirect but snippet shows wrong URL | Did not review `Location` header and redirect response | Check response headers, body, and both request/response preprocessors |

## 13. Build, Asciidoctor, and CI

Workflow:

1. Configure REST Assured with the test service's base URI, port, and base path.
2. Register `documentationConfiguration(restDocumentation)` as a filter to generate snippets.
3. Attach request/response URI preprocessors to `document(...)` per operation or via a shared helper.
4. Run tests to generate `http-request.adoc`, `curl-request.adoc`, `http-response.adoc`, and payload snippets.
5. Render Asciidoctor and inspect host/port/path in the output.
6. In CI, scan public documentation for internal hostnames, loopback, and test ports; allow them in local setup guides if clearly marked.

Gradle example once tasks are configured:

```bash
./gradlew test asciidoctor
```

The snippet directory is typically `build/generated-snippets` with Gradle or `target/generated-snippets` with Maven, depending on extension configuration. `asciidoctor` must depend on the `test` task so it reads newly generated snippets.

Manual scan example:

```bash
grep -RniE 'localhost|127\.0\.0\.1|0\.0\.0\.0|:8080|:5[0-9]{4}' build/generated-snippets
```

Matches should be reviewed in context. An internal test snippet or local guide may be valid; public API pages should not tell readers to connect to loopback or ephemeral test ports.

## 14. Practice Exercise

A catalog application runs in tests at:

```text
http://localhost:53142/internal-api
```

The public API is published at:

```text
https://catalog.example.com/v2
```

The public endpoint is:

```text
GET /v2/products/{productId}
```

Complete the following steps:

1. Create a `RequestSpecification` pointing to the actual test host and port.
2. Add `documentationConfiguration(restDocumentation)` to the REST Assured filter chain.
3. Use `preprocessRequest(modifyUris()...)` to replace scheme/host/port in snippets.
4. Verify whether the test path actually corresponds to the public path. If the internal path differs from the external path, decide whether to test through a gateway or organize documentation/paths according to the confirmed contract.
5. Create an operation returning `Location` and hypermedia links; apply a response preprocessor if response URIs need normalization.
6. Run tests, check `curl-request`, and render Asciidoctor in CI.

**Completion criteria:** REST Assured still calls the test server; snippets show the correct public scheme, host, and port; paths/queries are not altered unexpectedly; URIs in `Location` and response links are consistent with public documentation.

## 15. Key Takeaways

REST Assured sends real HTTP requests, so base URI, port, and base path configuration determines which server receives requests. Spring REST Docs URI preprocessing runs after the operation and before snippet generation, allowing you to replace scheme, host, or port without changing the HTTP destination. Use `preprocessRequest(modifyUris()...)` for requests; add `preprocessResponse(modifyUris()...)` if responses also contain URIs needing normalization. `modifyUris()` does not automatically fix resource paths or gateway contracts. Keep `RequestSpecification` isolated, inspect URLs in request/response snippets, and add CI scans for test hosts/ports so documentation reflects the exact address integrators should use.

### References

- [Spring REST Docs — REST Assured URI Customization](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#configuration-uris-rest-assured)
- [Spring REST Docs — Modifying URIs](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#customizing-requests-and-responses-modifying-uris)
- [Spring REST Docs — REST Assured integration](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#getting-started-setting-up-your-tests)
- [REST Assured — Usage and Request Specification](https://github.com/rest-assured/rest-assured/wiki/Usage)
