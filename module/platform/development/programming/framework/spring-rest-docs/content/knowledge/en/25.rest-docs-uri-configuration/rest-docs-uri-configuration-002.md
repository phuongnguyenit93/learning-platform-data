# Setting a Fixed Scheme, Host, and Port

## 1. Learning Objectives

In the **SPRING_REST_DOCS** module, we create verifiable REST API documentation through HTTP tests with MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and generate snippets for requests, responses, payloads, parameters, and headers. These snippets are compiled with Asciidoctor/Markdown and integrated into builds and CI.

When tests run on a developer machine or in CI, requests may target localhost, a container IP, and an automatically assigned port. These addresses are useful for testing, but they are not always the URL that API consumers should call. Spring REST Docs allows normalizing the URI recorded in snippets by setting a fixed scheme, host, and port.

After this lesson, you will be able to:

- Choose a scheme, host, and port that match the documented API environment.
- Use `modifyUris()` to replace address components in request snippets.
- Distinguish between a fixed port, a default port, and `removePort()`.
- Apply configuration for a single operation or as defaults across multiple operations.
- Organize separate configurations for sandbox and public APIs.
- Verify the output in `http-request.adoc` and integrate the rules into Gradle/CI.

## 2. Why Set a Fixed Scheme, Host, and Port?

Suppose a test starts the application on a random port:

~~~text
http://localhost:53127/api/orders/42
~~~

On the next run, the port may be different:

~~~text
http://localhost:60418/api/orders/42
~~~

If snippets keep the raw test URL, documentation generated on different machines may not match. Readers might also copy a localhost URL or CI port that is unreachable from their environment.

Suppose the API has a fixed sandbox address:

~~~text
https://sandbox-api.example.com/api/orders/42
~~~

REST Docs can write this URL into snippets while the test still calls the test server. Benefits:

| Issue | Result When Normalized |
| --- | --- |
| Test port changes | Snippets do not depend on a random port. |
| CI host is an internal IP | Snippets use a hostname intended for integrators. |
| Local tests use HTTP | Snippets still guide HTTPS if the public API requires HTTPS. |
| Developers and CI produce different snippets | Documented URLs remain stable across environments. |

You must choose a URL that reflects the environment the documentation targets. Do not set a production hostname if readers need to connect to sandbox.

## 3. Structure of Scheme, Host, and Port

Consider the URI:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

| Component | Value | Role |
| --- | --- | --- |
| Scheme | https | Protocol the client uses to connect. |
| Host | sandbox-api.example.com | Domain name or API host. |
| Port | 8443 | Port accepting connections. |
| Path | /api/orders/42 | Endpoint path. |

In a full URL, scheme and host identify the protocol and server. The port may be specified explicitly or implied by the scheme. For HTTPS, the default port is typically 443; for HTTP, the default port is typically 80.

The path belongs to the endpoint contract, so this lesson focuses on changing the scheme, host, and port. Do not use a URI modifier to accidentally alter paths or query parameters that the test is verifying.

## 4. Using modifyUris()

Spring REST Docs provides `modifyUris()` in the operation preprocessors group. The URI modifier can set the scheme, hostname, and port for the URI written to snippets.

Import:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
~~~

Example setting HTTPS, sandbox hostname, and port 8443:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .port(8443)
)
~~~

Applying inside `document()`:

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .port(8443)
        )
    ));
~~~

The client still sends the request to the test server. The preprocessor modifies the URI in the operation copy used to generate snippets. The recorded URL will use scheme `https`, host `sandbox-api.example.com`, and port `8443`.

## 5. Setting the Scheme

Use `scheme(...)` when the documented URL needs a fixed protocol:

~~~java
modifyUris().scheme("https")
~~~

Choose the scheme according to how clients must actually connect:

| Scheme in Documentation | Use Case |
| --- | --- |
| https | The API is published over TLS/HTTPS. |
| http | Use only when the target environment actually allows HTTP, such as an isolated local endpoint. |

Do not write HTTPS just to make the URL look like production if the actual sandbox or gateway does not support TLS. Conversely, do not leave snippets using HTTP if the contract requires clients to connect via HTTPS.

When an API sits behind a reverse proxy or API gateway, the public hostname and scheme may differ from the internal address received by the backend application. The URI in documentation should reflect the address clients are expected to use.

## 6. Setting the Host

Use `host(...)` to replace the recorded hostname:

~~~java
modifyUris().host("api.example.com")
~~~

Common hostnames:

| Target | Host in Snippet |
| --- | --- |
| Local API | localhost |
| Sandbox | sandbox-api.example.com |
| Public API | api.example.com |

In tests bound directly to a controller or `ApplicationContext`, the request builder may use a relative URI. The full URI in the snippet can be normalized using a preprocessor.

With a real test server, the client may call `localhost` or a container hostname. Setting the host in `modifyUris()` does not cause the client to connect to the new hostname; it only replaces the host in the documented data.

Do not use a fake hostname that readers cannot resolve. The `example.com` names in this lesson are illustrative data; projects should replace them with published sandbox/public domains.

## 7. Setting a Fixed Port

Use `port(...)` when the documented address needs a specific port:

~~~java
modifyUris()
    .scheme("https")
    .host("sandbox-api.example.com")
    .port(8443)
~~~

Resulting URL:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

The port in the snippet should be a port clients can actually reach. Do not use a random test server port or a CI-assigned port.

### 7.1. When Using a Non-Default Port

If the sandbox API is published on port 8443, keep the port in documentation:

~~~java
modifyUris()
    .scheme("https")
    .host("sandbox-api.example.com")
    .port(8443)
~~~

This port is part of the integration address. Even if a gateway forwards to a different internal port, documentation still uses the public port clients must call.

### 7.2. When Using the Default Port

If the public API uses HTTPS on the default port, the URL can normally be written without `:443`:

~~~text
https://api.example.com/api/orders/42
~~~

You can call `removePort()` to omit the port from the recorded URI:

~~~java
modifyUris()
    .scheme("https")
    .host("api.example.com")
    .removePort()
~~~

Do not remove the port if the public API requires a non-default port. Treat the port as part of the address the client needs to use.

## 8. Choosing Between port(), removePort(), and Keeping the Port

| Configuration | Expected Output | When to Use |
| --- | --- | --- |
| port(8443) | Writes port 8443 | The API is published on a custom port. |
| removePort() | Omits port | The public address uses the default port or documentation does not need a port segment. |
| No port modifier called | Keeps port from source URI | The source port is already a fixed port matching documentation. |

Example choices:

~~~java
// Public HTTPS API on standard port
modifyUris().scheme("https").host("api.example.com").removePort();

// Sandbox HTTPS API on port 8443
modifyUris().scheme("https").host("sandbox-api.example.com").port(8443);
~~~

Do not use both `port(...)` and `removePort()` in the same URI configuration. Choose one clear policy so snippet readers do not have to guess.

## 9. Per-Operation Configuration

When only certain endpoints need different addresses, place the modifier inside the operation's `document(...)`:

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .port(8443)
        )
    ));
~~~

Another operation can use the public hostname:

~~~java
client.get()
    .uri("/api/catalog")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("catalog/list",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

Per-operation configuration makes it clear which snippet uses which hostname. This approach fits when documentation describes multiple API gateways, multiple tenant endpoints, or routes with dedicated domains.

## 10. Default Configuration for Multiple Operations

If all operations in a documentation set share the same scheme, host, and port, set a default preprocessor when configuring the REST Docs filter:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

WebTestClient client = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .filter(documentationConfiguration(restDocumentation)
        .operationPreprocessors()
            .withRequestDefaults(
                modifyUris()
                    .scheme("https")
                    .host("sandbox-api.example.com")
                    .port(8443)
            )
    )
    .build();
~~~

`withRequestDefaults(...)` applies the default URI modifier to request operations documented through this client. Operations sharing the same base endpoint can share one configuration and reduce code duplication.

If an operation has a special address, pass a specific preprocessor to that operation's `document(...)`. When both default and operation-level configurations are used, open the actual snippet to verify the rules apply as expected for your project and REST Docs version.

### 10.1. Request and Response Defaults

Normalizing the URI in HTTP request snippets is the most common case. REST Docs also has response preprocessors for handling response content. If you need default response configuration, use `withResponseDefaults(...)` with appropriate response preprocessors. Do not apply a URI request modifier to the response body; only use it where operation URIs are processed.

## 11. Complete Example with WebTestClient

The following example binds to a controller so the test runs without opening a network port. The request builder uses a relative URI, while the snippet is recorded with a fixed sandbox address.

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class FixedUriDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderWithFixedSandboxAddress() {
        client.get()
            .uri("/api/orders/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/get",
                preprocessRequest(
                    modifyUris()
                        .scheme("https")
                        .host("sandbox-api.example.com")
                        .port(8443)
                ),
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

In the test, the request goes to the test controller and the actual path is `/api/orders/42`. The snippet is normalized to:

~~~http
GET https://sandbox-api.example.com:8443/api/orders/42 HTTP/1.1
Accept: application/json
~~~

Changing the scheme, host, and port only affects the REST Docs operation copy used to generate snippets. The request builder still does not connect to `sandbox-api.example.com`.

## 12. Verifying the Final URL in the Snippet

After the test runs, open:

~~~text
build/generated-snippets/orders/get/http-request.adoc
~~~

With the example configuration, the expected URL is:

~~~text
https://sandbox-api.example.com:8443/api/orders/42
~~~

Check the following points:

1. Scheme is `https`.
2. Host is `sandbox-api.example.com`.
3. Port is `8443`.
4. Path remains `/api/orders/42`.
5. Query parameters (if any) remain intact and properly encoded.

If the snippet URI is incorrect, check whether the request preprocessor was passed to the right `document(...)`, whether the client has the REST Docs filter, and whether the operation identifier you are viewing belongs to the most recent run.

## 13. Organizing Configuration Across Multiple Environments

A project may produce local, sandbox, and public documentation sets. Each documentation set should have its own fixed address:

| Documentation Set | Scheme | Host | Port |
| --- | --- | --- | --- |
| Local | http | localhost | 8080 or fixed guide port |
| Sandbox | https | sandbox-api.example.com | 8443 |
| Public | https | api.example.com | Default HTTPS, omit port from URL |

If multiple snippet sets are needed, use separate profiles or tasks to select preprocessors. Use separate output directories and operation identifiers so documentation for one environment does not overwrite another.

Never use a random test port as a documented port. The address recorded in snippets should be verified against the gateway, DNS, and TLS configuration of the corresponding environment.

## 14. Integrating Asciidoctor, Gradle, and CI

Asciidoctor can include normalized request snippets:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Get Order

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
include::{snippets}/orders/get/response-fields.adoc[]
~~~

Assuming the Asciidoctor plugin and `asciidoctor` task are configured:

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

In CI, run:

~~~bash
./gradlew clean test asciidoctor
~~~

CI generates fresh snippets from tests before building documentation. When the public scheme, hostname, or port changes, update the preprocessor configuration and review snippet URLs alongside infrastructure changes. With plain Markdown, a separate build step is needed to embed or link snippets; `include::` is Asciidoctor syntax.

## 15. Common Errors and How to Fix Them

| Symptom | Cause and Resolution |
| --- | --- |
| Snippet still has localhost | `modifyUris()` was not applied to the operation or the client does not use the REST Docs filter. |
| Snippet still has a random port | Choose a fixed `port(...)` or `removePort()` according to the public address. |
| URL has HTTPS but gateway only supports HTTP | Documented scheme does not reflect the public endpoint; check gateway/TLS configuration. |
| Sandbox host replaced with public host | Check default configuration and operation-specific preprocessors. |
| URL omits port even though API needs port 8443 | Do not use `removePort()`; set `port(8443)`. |
| URL shows `:443` even though default HTTPS format is desired | Use `removePort()` and confirm the gateway allows access on the default port. |
| Actual requests go to the documented host | Modified the client's base URL instead of modifying only the recorded operation via preprocessor. |
| Path was altered | Only modify scheme/host/port; do not rewrite the URI path if the endpoint has not changed. |
| Asciidoctor picks up old snippets | Run `clean` and ensure tests complete before the `asciidoctor` task. |

## 16. Practice Exercises

1. Run a controller-bound WebTestClient test and open `http-request.adoc` before adding a URI modifier.
2. Configure scheme `https`, host `sandbox-api.example.com`, and port `8443`; re-run the test and compare the URL.
3. Replace `port(8443)` with `removePort()`; inspect the port segment in the snippet.
4. Create a public operation using `api.example.com` and omit the default port.
5. Move the sandbox configuration to `withRequestDefaults(...)` on the client; confirm operations share the same address.
6. Create two snippet tasks/profiles for sandbox and public, saving outputs in two separate directories.
7. Run Gradle/CI and verify no snippet contains a random test hostname or port.

## 17. Key Takeaways

- `modifyUris()` sets the scheme, host, and port in the URI written to REST Docs snippets.
- `scheme("https")` and `host("...")` keep documented URLs stable across local machines, containers, and CI.
- `port(8443)` preserves a non-default public port; `removePort()` omits the port from snippets when the address uses the default port.
- Never use a random test port as a documented port, and never set a production hostname if the documentation targets sandbox.
- Configure inside `document(...)` for exceptions; use `withRequestDefaults(...)` for operations sharing one address.
- URI preprocessors do not change the actual request destination; verify the final URL in `http-request.adoc`.
- Run tests before Asciidoctor in CI so documentation is always built from fresh snippets.
