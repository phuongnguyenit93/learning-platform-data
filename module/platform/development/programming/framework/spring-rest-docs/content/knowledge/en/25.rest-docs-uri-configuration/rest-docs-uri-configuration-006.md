# WebTestClient URI Customization

## 1. Learning Objectives

In the **SPRING_REST_DOCS** module, we create verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. These snippets are compiled with Asciidoctor/Markdown and integrated into builds and CI.

With WebTestClient, the URI in request snippets has a default base URL. If left unchanged, documentation often records a `localhost` address even though API consumers need to call a sandbox or public hostname. Spring REST Docs explains how to customize the documented base URL using the `baseUrl(String)` method on `WebTestClient.Builder`.

After this lesson, you will be able to:

- Identify the default base URL of URIs recorded in snippets by WebTestClient.
- Configure scheme, host, and port using `configureClient().baseUrl(...)`.
- Understand the relationship between `bindToApplicationContext`, `bindToController`, `bindToServer`, and the base URL.
- Distinguish the URL in the request builder, the base URL used to connect to a server, and the URI written in documentation.
- Build multiple `WebTestClient` instances with local, sandbox, or public addresses.
- Verify the final URL in `http-request.adoc` and integrate into Asciidoctor/CI.

## 2. Default WebTestClient Base URL

When using WebTestClient with Spring REST Docs, the default documented base URI is:

~~~text
http://localhost:8080
~~~

Example test calling an endpoint:

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get"));
~~~

The request snippet may record:

~~~http
GET http://localhost:8080/api/orders/42 HTTP/1.1
~~~

This address is the default base URL used for the URI written into snippets. When bound to a controller or `ApplicationContext`, WebTestClient creates simulated requests/responses and does not need a network connection to `localhost:8080`. When documentation needs to instruct clients to call a different hostname, set the appropriate base URL before running tests.

## 3. Configuring with baseUrl(String)

Spring REST Docs recommends using `baseUrl(String)` on `WebTestClient.Builder`. For a client bound to an `ApplicationContext`, call `configureClient()` first, then set the base URL and attach the REST Docs filter:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
    .configureClient()
    .baseUrl("https://api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Static import for REST Docs:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
~~~

From this point on, a relative request URI such as `/api/orders/42` is recorded with the base URL `https://api.example.com`.

### 3.1. Setting the Scheme

The scheme is the `http` or `https` part of the URL:

~~~java
.baseUrl("https://api.example.com")
~~~

Choose `https` if clients of the public or sandbox API must connect over TLS. Only use `http` when the documented environment actually allows HTTP, such as an isolated local service.

### 3.2. Setting the Host

The hostname is the server name portion of the base URL:

~~~java
.baseUrl("https://sandbox-api.example.com")
~~~

Use the hostname that matches the documentation set being generated. Avoid letting `localhost`, container IPs, or CI machine names appear in integration guides for external clients.

### 3.3. Setting the Port

If the API is published on a non-default port, include the port in the base URL string:

~~~java
.baseUrl("https://sandbox-api.example.com:8443")
~~~

With the default HTTPS port, `:443` typically does not need to be written:

~~~java
.baseUrl("https://api.example.com")
~~~

`baseUrl(String)` accepts the full base URL string. There are no separate setters like `withScheme()`, `withHost()`, or `withPort()` in this WebTestClient configuration.

## 4. Understanding the Role of Bind Mode

WebTestClient supports several bind modes. The base URL plays a different practical role depending on how the client communicates with the server:

| Bind Mode | How It Works | Role of baseUrl |
| --- | --- | --- |
| bindToController(...) | Tests a controller via mock requests/responses without a running server. | Provides the base for the recorded operation URI and how the client resolves relative URIs. |
| bindToApplicationContext(...) | Tests an application configured in `ApplicationContext` via a mock server adapter. | Allows setting a base URL so snippets use the desired hostname/scheme without making network calls to that hostname. |
| bindToRouterFunction(...) | Tests WebFlux functional endpoints via a mock server. | Used as the client's base URI in the recorded operation. |
| bindToServer() | Connects to a running server and sends real HTTP requests. | Base URL is the real connection target; it must point to a running server. |

Key point: with mock server bindings, the hostname in the base URL mainly shapes the recorded URI as desired; it does not start a server at that hostname. With `bindToServer()`, the base URL must be an actual reachable server address.

## 5. Complete Example with bindToApplicationContext

The following example configures WebTestClient so snippets use a sandbox URL:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class WebTestClientUriDocumentationTest {

    @Autowired
    private ApplicationContext context;

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
            .configureClient()
            .baseUrl("https://sandbox-api.example.com:8443")
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderWithSandboxBaseUrl() {
        this.webTestClient.get()
            .uri("/api/orders/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/get",
                responseFields(
                    fieldWithPath("id").description("Order ID"),
                    fieldWithPath("status").description("Order status")
                )
            ));
    }

    @RestController
    static class OrderController {

        @GetMapping(
            path = "/api/orders/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<Map<String, Object>> getOrder(
                @PathVariable("id") long id) {
            return Mono.just(Map.of(
                "id", id,
                "status", "PAID"
            ));
        }
    }
}
~~~

This example assumes the `ApplicationContext` has a `GET /api/orders/{id}` controller returning status 200. The request snippet is expected to start like:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
Accept: application/json
~~~

The test still handles requests using WebTestClient's mock server adapter. It does not open a network connection to `sandbox-api.example.com`.

## 6. Example with bindToController

When only a single controller needs to be tested, you can bind directly:

~~~java
WebTestClient webTestClient = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .baseUrl("https://api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Then call a relative URI:

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get"));
~~~

The snippet will use the base URL `https://api.example.com`. This binding fits tests focused on a controller; if the endpoint depends on filters, security, routers, or other configuration beans, use `bindToApplicationContext(...)` to test the required infrastructure.

## 7. Example with bindToServer

When WebTestClient connects to a running application, `baseUrl(...)` is the actual connection address:

~~~java
WebTestClient webTestClient = WebTestClient.bindToServer()
    .baseUrl("http://localhost:8080")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Requests are sent over the network to `localhost:8080`. If you change it to `https://api.example.com`, the test will attempt to connect to the server at that address; this is no longer just changing the URL displayed in snippets.

For integration tests using a random server port, obtain the actual port from the test configuration to connect. If you want documentation to show a fixed public hostname while tests connect locally, consider using a mock binding or an operation preprocessing approach suited to the integration flow. Do not pass a public `baseUrl` to `bindToServer()` if the public server is not the actual test target.

## 8. Query Parameters and Paths When Setting Base URL

`baseUrl(...)` only sets the base part of the URL. Each operation's path and query are still determined by the request builder:

~~~java
webTestClient.get()
    .uri("/api/orders/{id}?expand={expand}", 42, "items")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get-expanded"));
~~~

With base URL `https://api.example.com`, the recorded URI looks like:

~~~text
https://api.example.com/api/orders/42?expand=items
~~~

Make sure the path does not duplicate prefixes. For example, if the base URL already includes `/gateway`, do not add `/gateway` again to the request URI unless the endpoint actually has two prefix segments.

Query parameters and path variables are still part of the API contract. Do not remove or alter them just to make snippet URLs shorter.

## 9. Shared Base URL and Multiple Environments

If all operations in a documentation set share one address, configure the base URL once where `WebTestClient` is built:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
    .configureClient()
    .baseUrl("https://sandbox-api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

If separate documentation is needed for local, sandbox, and public, create corresponding configurations/clients or test profiles:

| Documentation Set | Base URL Configuration |
| --- | --- |
| Local | http://localhost:8080 |
| Sandbox | https://sandbox-api.example.com |
| Sandbox on custom port | https://sandbox-api.example.com:8443 |
| Public | https://api.example.com |

Do not share output directories or operation IDs if separate documentation sets are generated with different URIs. Sharing them allows snippets from one set to overwrite those from another.

## 10. Verifying the Recorded URI in Snippets

After tests run, open the file:

~~~text
build/generated-snippets/orders/get/http-request.adoc
~~~

With the sandbox base URL in the example, the first line of the request should look like:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
Accept: application/json
~~~

Check:

1. Whether the scheme is `https`.
2. Whether the host matches the published sandbox hostname.
3. Whether the port is recorded when the API uses a non-default port.
4. Whether path variables are replaced with test values.
5. Whether the query string is complete and properly encoded.

If the snippet still records `http://localhost:8080`, verify that the running client actually calls `baseUrl(...)` after `configureClient()`, that the REST Docs filter is attached to the right client, and that the snippet file you are viewing belongs to the latest run.

## 11. Distinguishing baseUrl(...) and URI Preprocessors

For WebTestClient, the standard way to customize the documented URI in Spring REST Docs is setting the base URL on the builder:

~~~java
WebTestClient.bindToApplicationContext(context)
    .configureClient()
    .baseUrl("https://api.example.com")
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

Difference:

| Approach | Effect |
| --- | --- |
| baseUrl(...) | Sets the base URI in the WebTestClient builder; with mock bindings it adjusts the recorded request URI, while with bind-to-server it is also the connection target. |
| preprocessRequest(...) | Transforms the copy of the request operation used to generate snippets after the request has executed. |

If you only need a consistent hostname/scheme for WebTestClient, prefer `baseUrl(...)`. Preprocessors are useful when you need to transform recorded requests with custom rules, such as normalizing URIs after sending real requests or removing sensitive headers from snippets.

## 12. Integrating Snippets with Asciidoctor

Spring REST Docs creates `http-request.adoc` from the recorded request. Asciidoctor can include the snippet into documentation:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Get Order

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
include::{snippets}/orders/get/response-fields.adoc[]
~~~

The URL in the request snippet must reflect the chosen base URL. As a result, the final documentation contains a stable sandbox/public address rather than an unintended `localhost:8080`.

## 13. Integrating Gradle and CI

Assuming the Asciidoctor plugin and `asciidoctor` task are configured, link the documentation build task to snippet-generating tests:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

In CI:

~~~bash
./gradlew clean test asciidoctor
~~~

Tests run with the configured base URL, REST Docs generates snippets, and Asciidoctor assembles the documentation. When the sandbox/public address changes, update the base URL configuration alongside API documentation changes to avoid stale snippets.

With plain Markdown, Asciidoctor's `include::` syntax is not processed automatically; a separate build step is required to embed snippets or link to generated files.

## 14. Common Errors and How to Fix Them

| Symptom | Cause and Resolution |
| --- | --- |
| Snippet still has localhost:8080 | `baseUrl(...)` was not called, was called on another builder, or the viewed snippet file is stale output. |
| Base URL is not applied | With mock-bound clients, call `configureClient()` before `baseUrl()`; attach the REST Docs filter to the right builder. |
| bind-to-server test fails to connect | `baseUrl()` is a real network target; verify the server is running and host/port are reachable. |
| Request URI duplicates path prefix | Check the base URL and the path passed to `uri()`; do not duplicate gateway/context prefixes. |
| Snippet has CI hostname | Base URL was not fixed on the client used for documentation. |
| Port is missing or wrong | Check the port in the base URL; a port should only be recorded when the public address requires it. |
| Some snippets use a different base URL | Multiple `WebTestClient` instances or test profiles are using different configurations. |
| Snippet is not generated | Check the REST Docs filter, `consumeWith(document(...))`, output directory, and test results. |

## 15. Practice Exercises

1. Create an `ApplicationContext`-bound WebTestClient and run the test without setting a base URL; open `http-request.adoc`.
2. Add `baseUrl("https://sandbox-api.example.com")` after `configureClient()` and confirm the snippet changes the hostname.
3. Try `baseUrl("https://sandbox-api.example.com:8443")` and inspect the port in the URI.
4. Add path variables and query parameters; confirm the base URL does not alter paths/queries.
5. Create `bindToController(...)` and `bindToServer()` clients to compare how `baseUrl` behaves with mock requests versus real HTTP connections.
6. Generate two snippet sets for sandbox and public using separate output directories.
7. Run Gradle/CI and check that snippet URLs do not depend on the build machine's hostname/port.

## 16. Key Takeaways

- The default documented base URI for WebTestClient in Spring REST Docs is `http://localhost:8080`.
- Use `configureClient().baseUrl(String)` to set the scheme, host, and port for the recorded URI.
- `bindToApplicationContext`, `bindToController`, and `bindToRouterFunction` use a mock server adapter; a base URL hostname in snippets does not open a network connection to that hostname.
- With `bindToServer()`, the base URL is the real server address to connect to.
- Operation paths and queries are still defined by `uri(...)`; check carefully to avoid duplicated prefixes.
- Use separate clients/configurations for sandbox and public when generating multiple documentation sets.
- Run tests before Asciidoctor in CI so documentation is always built from fresh snippets.

## 17. References

- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): WebTestClient URI Customization section and configuring `baseUrl(String)`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind modes and client configuration.
