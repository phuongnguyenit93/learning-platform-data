# Documented URI and URI Used in Documentation

## 1. Learning Objectives

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. These snippets are compiled with Asciidoctor/Markdown and then included in builds and CI.

A test can run across multiple environments: local, developer machines, CI, or containers. The actual URL host, port, and scheme may differ even though the endpoint and API contract stay the same. If the raw test address is written directly into snippets, readers may mistake the test host for the API's public address.

This lesson distinguishes the actual request URI from the URI documented in Spring REST Docs, and explains how to normalize URIs in snippets using `modifyUris()`. After this lesson, you will be able to distinguish the two URI types, explain scheme/host/port, apply URI preprocessors per operation or as defaults, and ensure documentation URLs remain stable across builds.

## 2. Actual URI and Documented URI

Suppose a test runs a server at http://localhost:53127 and calls:

~~~java
client.get()
    .uri("/api/orders/42")
    .exchange();
~~~

The initial request snippet might record:

~~~http
GET http://localhost:53127/api/orders/42
~~~

The public address of the API might be:

~~~text
https://api.example.com/api/orders/42
~~~

Both URIs point to the example endpoint, but they serve two different purposes:

| Concept | Example | Purpose |
| --- | --- | --- |
| URI used to send the request | http://localhost:53127/api/orders/42 | Connects to the server running in the test. |
| URI written in the snippet | https://api.example.com/api/orders/42 | Guides clients to call the API via its public address. |

Spring REST Docs preprocessors can modify the operation representation used to generate snippets. Normalizing the URI in documentation does not change the request destination used by WebTestClient, MockMvc, or REST Assured.

~~~mermaid
flowchart TD
    A["Test configures client and base URL"] --> B["Send HTTP request to test server"]
    B --> C["Endpoint processes and returns response"]
    C --> D["REST Docs records HTTP operation"]
    D --> E["Request preprocessor: modifyUris()"]
    E --> F["http-request.adoc with documented URL"]
    F --> G["Asciidoctor / API documentation"]
~~~

The preprocessor only normalizes the documented data. If you change the base URL or URI in the client configuration, the actual request will be sent to the new address.

## 3. URI Structure and Components to Normalize

An HTTP URI can consist of a scheme, authority, path, and query:

~~~text
https://api.example.com:8443/api/orders/42?expand=items
~~~

| Component | Example Value | Meaning |
| --- | --- | --- |
| Scheme | https | Access protocol. |
| Host | api.example.com | Hostname or domain name. |
| Port | 8443 | Port where the server accepts connections. |
| Path | /api/orders/42 | Path to the resource. |
| Query | expand=items | Query parameters. |

When normalizing snippets, typically only the scheme, host, or port is replaced so the actual path/query of the operation is preserved. Do not modify the path/query if they are part of the contract being documented.

For example, test hosts/ports may vary:

- Developer A: http://localhost:8080/api/orders/42
- Developer B: http://localhost:52143/api/orders/42
- CI: http://127.0.0.1:39417/api/orders/42

Snippets should present a consistent sample URL: https://api.example.com/api/orders/42.

## 4. Normalizing URIs with modifyUris()

Spring REST Docs provides `modifyUris()` in the operation preprocessors group. This API returns a URI modifier to set the scheme, host, port, or remove the port from the recorded URI.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
~~~

Example normalizing the URL to a public host:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort()
)
~~~

When used inside `document()`:

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
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

This example assumes the client has already been configured with the REST Docs filter. The HTTP request still goes to the test server, while the URL in the request snippet is recorded with the public scheme/host and without a port.

### 4.1. Choosing the Scheme

~~~java
modifyUris().scheme("https")
~~~

Suitable when documentation describes a public API over HTTPS, while local tests may use HTTP. Only set `https` if that is the protocol clients must use when calling the public API.

### 4.2. Choosing the Host

~~~java
modifyUris().host("api.example.com")
~~~

The host in the snippet no longer depends on localhost, container IPs, or CI hostnames. Use the hostname belonging to the environment the documentation targets; do not default to the production hostname if the documentation is specifically for sandbox.

### 4.3. Setting a Fixed Port

~~~java
modifyUris().port(8443)
~~~

Use this when the API is published on a non-default port and users need to see that port. The port in the snippet is the port documented for clients, not the random port used to run tests.

### 4.4. Removing the Port

~~~java
modifyUris().removePort()
~~~

Use this when you want the documented URI to omit the port, for example when the public address uses the default HTTPS port. If the API must run on a custom port, removing the port can make the guide inaccurate.

## 5. Combining Scheme, Host, and Port

Choose the configuration based on the URL API consumers actually need to call:

| Documentation Goal | Suggested Configuration |
| --- | --- |
| HTTPS on public hostname, standard port | scheme("https"), host("api.example.com"), removePort() |
| HTTPS on custom port | scheme("https"), host("api.example.com"), port(8443) |
| Sandbox host | scheme("https"), host("sandbox-api.example.com"), removePort() |
| Replace hostname only | host("api.example.com") |

Example:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .port(8443)
)
~~~

The snippet will use the hostname and port intended for sandbox. Make sure this address is reachable and supported in the sandbox environment.

Do not set the production host out of habit if readers need sandbox documentation. Identify the target audience before choosing scheme, host, and port.

## 6. Applying Preprocessors to a Single Operation

When only a single endpoint has special URI requirements, configure it directly inside `document()`:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders/create",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

The advantage is that the rule sits close to the operation, making it easy to see which endpoint has a custom documented URL. The drawback is that configuration can be duplicated across many operations.

Multiple request preprocessors can be combined, for example normalizing the URI while removing an internal header:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort(),
    modifyHeaders()
        .remove("X-Internal-Token")
)
~~~

Each preprocessor handles one part of the request representation used in snippets. Do not use a URI preprocessor to alter the actual request or replace endpoint verification assertions.

## 7. Configuring a Default URI for Multiple Operations

If the entire API shares the same documented hostname and scheme, avoid repeating the configuration in every `document()`. You can declare default request preprocessors on the REST Docs configuration filter:

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
                    .host("api.example.com")
                    .removePort(),
                prettyPrint()
            )
    )
    .build();
~~~

`withRequestDefaults(...)` applies preprocessors to request operations documented through this client. The example also adds `prettyPrint()` to format the JSON request body. You can configure separate response defaults with `withResponseDefaults(...)` when needed.

When an operation has a custom rule, pass the specific preprocessor in that operation's `document(...)`. Check the generated snippets to confirm how default and operation preprocessors combine in your project's REST Docs version.

## 8. Complete Example with WebTestClient

This example binds directly to a controller so tests run without opening a network port. The test client uses a relative URI; the preprocessor writes the public hostname into the snippet.

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
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class DocumentedUriTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderUriWithPublicHost() {
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
                        .host("api.example.com")
                        .removePort()
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
        public Mono<Map<String, Object>> getOrder() {
            return Mono.just(Map.of(
                "id", 42,
                "status", "PAID"
            ));
        }
    }
}
~~~

The test calls `/api/orders/42` in a controller test environment; the request snippet is normalized to a URL with `https://api.example.com`. The path still reflects the tested endpoint. The example illustrates URI handling, while the response descriptors document the two fields returned by the controller.

## 9. Comparing Actual URI and Snippet

After running the test, open `build/generated-snippets/orders/get/http-request.adoc`. The expected result looks like:

~~~http
GET https://api.example.com/api/orders/42 HTTP/1.1
Accept: application/json
~~~

| Where Observed | URI |
| --- | --- |
| Request builder | /api/orders/{id} with value 42 |
| Test server receiving request | Path /api/orders/42 in the test's bound environment |
| Request snippet | https://api.example.com/api/orders/42 |

When a test binds to a real server, the actual URL may be `http://localhost:<random-port>`. After `modifyUris()`, the snippet still records the fixed public URL.

If the snippet still records `localhost`, check:

1. Whether the preprocessor was passed into the right `document(...)`.
2. Whether `preprocessRequest(...)` is used for the request snippet rather than mistakenly using `preprocessResponse(...)`.
3. Whether the client has the REST Docs filter attached.
4. Whether another test uses a different client and bypasses the default preprocessor.
5. Whether the operation name and opened snippet correspond to the latest run.

## 10. URIs in MockMvc and REST Assured

The principle of separating the actual URI from the documented URI also applies to other Spring REST Docs integrations.

### 10.1. MockMvc

MockMvc creates requests in a Servlet test environment without opening an HTTP port. You can apply the request preprocessor inside `document()`:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

This snippet assumes `mockMvc` already has the REST Docs MockMvc configuration attached and static imports for `get`, `status`, `document`, `preprocessRequest`, and `modifyUris` are declared.

### 10.2. REST Assured

With REST Assured integration, pass the preprocessor into the corresponding documentation callback:

~~~java
given()
    .accept("application/json")
    .filter(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ))
    .when()
    .get("/api/orders/42")
    .then()
    .statusCode(200);
~~~

This snippet illustrates where to apply the request preprocessor; real tests require the REST Docs `RestAssuredRestDocumentation` filter and appropriate RestAssured configuration. Do not mix WebTestClient filters with MockMvc/REST Assured.

## 11. Deciding Documented URIs Across Multiple Environments

A project may have local, sandbox, and production environments. Do not let URIs in snippets depend on the environment where tests run. Choose a clear documented address:

| Documentation Set | Scheme | Host | Port |
| --- | --- | --- | --- |
| Local guide | http | localhost | Local port specified in the guide |
| Sandbox guide | https | sandbox-api.example.com | Omit port if using default HTTPS port |
| Public guide | https | api.example.com | Omit port if using default HTTPS port |

If you need to generate multiple snippet sets for different environments, create separate tasks/test profiles with separate preprocessors. Use different operation identifiers or separate output directories to prevent one documentation set from overwriting another's snippets.

The address appearing in documentation is an integration guide commitment. Verify it against the gateway, DNS, TLS configuration, and the environment readers are permitted to access.

## 12. Integrating Snippets into Asciidoctor and CI

Asciidoctor references the normalized snippets:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Get Order

include::{snippets}/orders/get/http-request.adoc[]
include::{snippets}/orders/get/http-response.adoc[]
include::{snippets}/orders/get/response-fields.adoc[]
~~~

Assuming the Asciidoctor plugin is configured, you can wire the documentation task to the test task:

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

CI runs tests and generates fresh snippets before building documentation. Because the preprocessor sets a fixed host/scheme/port, URLs in snippets do not depend on random CI ports. When the public hostname changes, update the documentation configuration alongside the API review process.

With plain Markdown, `include::` is not processed automatically. Use a separate build step to embed snippets or link to generated files.

## 13. Common Errors and How to Fix Them

| Symptom | Cause and Resolution |
| --- | --- |
| Snippet contains localhost | `modifyUris()` is not configured or the preprocessor was not applied to the right operation. |
| Snippet contains a random port | Use `removePort()` or set `port(...)` according to the published public address. |
| Snippet shows HTTPS but API only supports HTTP | Documented scheme is wrong; adjust to match the actual contract and gateway. |
| Actual requests go to the wrong host after editing documentation | Changed the client/base URL instead of only preprocessing the operation; restore the test target and place `modifyUris()` in REST Docs. |
| Path or query changed unexpectedly | Check the preprocessor and URI builder; normalize only environment components and keep the operation's path/query. |
| Some snippets are normalized while others are not | A client/test is not using the default preprocessor or an operation did not pass a custom preprocessor. |
| Asciidoctor displays an old URL | Run `clean` and ensure the `test` task runs before Asciidoctor. |
| Multiple environments overwrite snippets | Separate output directories or operation identifiers per documentation set. |

## 14. Practice Exercises

1. Create a WebTestClient test bound to a controller; record the request snippet before normalization.
2. Add `modifyUris().scheme("https").host("api.example.com").removePort()` and re-run the test.
3. Compare the snippet URL with the URI in the request builder; confirm that the path and query are unchanged.
4. Try `port(8443)` and then `removePort()` and compare the snippet outputs.
5. Configure `withRequestDefaults(...)` on the client to normalize URIs across multiple operations; inspect all request snippets.
6. Generate sandbox and public snippet sets with different hostnames using separate output directories.
7. Run `./gradlew clean test asciidoctor` in CI and verify that URLs do not contain random hostnames or ports.

## 15. Key Takeaways

- The actual URI is used to send requests to the test server; the documented URI is the address written into snippets to guide clients.
- `modifyUris()` normalizes the URI in the REST Docs operation copy used to generate snippets; it does not change the actual request destination.
- Use `scheme(...)`, `host(...)`, `port(...)`, or `removePort()` according to the public/sandbox address targeted by the documentation.
- Apply preprocessors per operation for exceptions; use request defaults when multiple operations share the same rule.
- Align scheme/host/port with the environment readers will call; preserve the endpoint's path and query.
- Build/CI runs tests before Asciidoctor so documentation is generated from fresh snippets with stable URIs.
