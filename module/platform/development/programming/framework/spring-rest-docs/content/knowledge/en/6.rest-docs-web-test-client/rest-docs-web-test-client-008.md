# Preprocessing URIs, Headers, and Bodies in WebTestClient

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we generate verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and generate snippets for requests, responses, payloads, parameters, and headers; then Asciidoctor/Markdown assembles the snippets in the build and CI.

In the **WebTestClient** chapter, you must distinguish two activities: preparing the actual request so the application receives the right URI, headers, and body; and normalizing the request/response recorded by Spring REST Docs into snippets. Published documentation should feature stable URLs, readable payloads, and no leaked tokens, cookies, or internal data.

After this lesson, you will be able to build URIs from templates/paths/queries; set headers per request or as client defaults; send JSON, strings, and reactive publishers; distinguish the real request from the preprocessed version written to snippets; and normalize URIs, remove internal headers, and format/mask bodies using REST Docs preprocessors.

## 2. Two Processing Layers to Distinguish

| Layer | Tools | Purpose |
| --- | --- | --- |
| **Preparing the request sent to the application** | uri(...), headers(...), header(...), contentType(...), bodyValue(...), body(...) | Defines the actual HTTP request received by the endpoint. |
| **Preprocessing data for documentation** | preprocessRequest(...), preprocessResponse(...), modifyUris(), modifyHeaders(), prettyPrint(), replacePattern(...) | Normalizes or removes data from the request/response written to snippets. |

~~~mermaid
flowchart TD
    A["WebTestClient request builder"] --> B["Actual HTTP request"]
    B --> C["WebFlux endpoint"]
    C --> D["Actual HTTP response"]
    D --> E["Assertions"]
    E --> F["consumeWith(document(...))"]
    F --> G["REST Docs preprocessors"]
    G --> H["Request/response snippets"]
    H --> I["Asciidoctor / CI"]
~~~

For example, the Authorization header is set via the request builder so the endpoint can authenticate the call. A request preprocessor can remove Authorization from **snippets** so the documentation contains no credentials. The preprocessor does not strip that header from the request sent to the application; assertions still verify the actual response returned by the application.

Important principle: **do not confuse modifying the real request with modifying the copy used to generate documentation**. If you modify a header or URI on the WebTestClient side, the endpoint receives the modified value. If you use a REST Docs preprocessor, the goal is to adjust the documented data.

## 3. Building Request URIs

### 3.1. URI Templates and Path Variables

Using URI templates keeps test code readable and aligns with the path parameters REST Docs needs to describe:

~~~java
client.get()
    .uri("/api/orders/{orderId}", 42)
    .exchange()
    .expectStatus().isOk();
~~~

The value 42 is bound to the {orderId} variable. When using pathParameters(...) inside document(...), the descriptor names must match the variable names in the URI template and endpoint contract.

### 3.2. Query Parameters

You can embed query parameters directly in the URI:

~~~java
client.get()
    .uri("/api/orders?status={status}&page={page}", "PAID", 0)
    .exchange()
    .expectStatus().isOk();
~~~

Or use UriBuilder when the URI has multiple parameters:

~~~java
client.get()
    .uri(builder -> builder
        .path("/api/orders")
        .queryParam("status", "PAID")
        .queryParam("page", 0)
        .queryParam("size", 20)
        .build())
    .exchange()
    .expectStatus().isOk();
~~~

UriBuilder avoids manual query string concatenation, especially when values need encoding. When documenting query parameters, use the descriptor suited to your project's Spring REST Docs version and ensure the actual request includes those parameters.

### 3.3. Base URLs and Default URIs

When tests frequently call the same API prefix, you can configure a base URL when building the client:

~~~java
WebTestClient client = WebTestClient.bindToServer()
    .baseUrl("http://localhost:8080")
    .build();
~~~

This example uses a running HTTP server. For clients bound to a controller, router, or ApplicationContext in tests, relative URIs such as /api/orders are commonly used. If you need to test a real host/port, pick the appropriate binding mode.

The base URL is part of the actual request address. REST Docs can normalize the host, scheme, or port in the recorded output so snippets do not depend on the CI machine; doing so does not change the address WebTestClient called.

## 4. Setting Request Headers

### 4.1. Per-Request Headers

Use header(name, values...) when an operation requires specific headers:

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .header("X-Request-Id", "test-req-001")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk();
~~~

### 4.2. Setting Multiple Headers

headers(...) lets you modify HttpHeaders inside a callback:

~~~java
client.post()
    .uri("/api/orders")
    .headers(headers -> {
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.set("X-Request-Id", "test-req-002");
    })
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated();
~~~

Supporting imports:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
~~~

### 4.3. Client Default Headers

When multiple tests share the same header, set a default header when building WebTestClient:

~~~java
WebTestClient client = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .defaultHeader("X-Client-Name", "documentation-test")
    .build();
~~~

Default headers apply to requests made by the client unless overridden in ways supported by the API. Never place personal tokens, passwords, or shared secrets into default headers or documentation. Use dummy credentials dedicated to tests and remove them from snippets.

## 5. Sending Request Bodies

### 5.1. JSON with bodyValue(...)

When the body is a simple object, bodyValue(...) is the direct approach:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
        "productId", "BOOK-01",
        "quantity", 2
    ))
    .exchange()
    .expectStatus().isCreated();
~~~

The WebFlux codec serializes the object into JSON according to Content-Type and codec configuration. When documenting the request, requestFields(...) describes the body structure; request-body.adoc displays the captured payload depending on snippets and configuration.

### 5.2. Strings or Plain Text Content

For endpoints accepting plain text:

~~~java
client.put()
    .uri("/api/notes/{id}", 7)
    .contentType(MediaType.TEXT_PLAIN)
    .bodyValue("Note content")
    .exchange()
    .expectStatus().isNoContent();
~~~

Content-Type must reflect the body type and be compatible with the endpoint's consumes declaration. Do not send JSON while declaring text/plain, or vice versa.

### 5.3. Reactive Publishers as the Body

When input data is a publisher, use body(...) with BodyInserters:

~~~java
Flux<OrderLine> lines = Flux.just(
    new OrderLine("BOOK-01", 2),
    new OrderLine("BOOK-02", 1)
);

client.post()
    .uri("/api/orders/import")
    .contentType(MediaType.APPLICATION_JSON)
    .body(BodyInserters.fromPublisher(lines, OrderLine.class))
    .exchange()
    .expectStatus().isAccepted();
~~~

The example assumes the import endpoint accepts streamed JSON data and that the OrderLine/service classes are defined. You must import BodyInserters and Flux. Determine whether the endpoint expects a finite JSON array, NDJSON, or a streaming body; the media type and encoding affect what the server receives. Snippets should represent a reproducible sample request, avoiding random data sources across runs.

## 6. Normalizing URIs in Snippets with REST Docs

Tests bound to a real server may record different hosts and ports across local machines, CI, and test runners. Use modifyUris() to normalize the address **in snippets**:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

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

This is the end of a test already configured with the REST Docs filter. The real request is still sent to the test server; the generated http-request.adoc is normalized to the example URL https://api.example.com/api/orders/42.

| Method | Effect on Snippet |
| --- | --- |
| scheme("https") | Replaces the recorded scheme. |
| host("api.example.com") | Uses a fixed documentation hostname. |
| port(443) | Records the chosen port. |
| removePort() | Removes the port from the recorded URI. |

Choose a combination matching your API's public address. Do not use a misleading host that confuses readers about the production endpoint; clearly document the sample base URL when necessary.

## 7. Removing or Modifying Headers in Snippets

Real requests may contain Authorization, Cookie, X-Internal-Token, or X-Request-Id. Not every header needs to be published. Spring REST Docs provides preprocessors to edit headers **in the recorded documentation**.

### 7.1. Removing Sensitive Headers

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.consumeWith(document("orders/get",
    preprocessRequest(
        modifyHeaders()
            .remove("Authorization")
            .remove("Cookie")
            .remove("X-Internal-Token")
    )
));
~~~

This snippet illustrates the end of a GET test; the actual request can still send whatever headers authentication requires. Only those headers are removed from the recorded snippet. Check the modifyHeaders() API in your project's Spring REST Docs version if signatures differ.

### 7.2. Documenting Public Headers

If the API contract requires documenting X-Request-Id, use a descriptor:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Request tracking ID")
)
~~~

Descriptors state what a header means in the API; preprocessors decide which headers appear in the normalized request record. Do not strip a header from snippets if users need it to call the endpoint or if a descriptor expects that header to be documented.

### 7.3. Replacing Sensitive Header Values

If you want to keep the header name but replace its value with a safe example, use the header-editing API for your library version or supply dummy credentials from the start in tests. The safest and most maintainable approach is never to use real secrets in tests; preprocessors should not be your sole defense against credential leaks.

## 8. Formatting and Masking Data in Body Snippets

### 8.1. Formatting JSON

Use prettyPrint() to generate readable JSON snippets:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.consumeWith(document("orders/create",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    requestFields(
        fieldWithPath("productId").description("Product ID"),
        fieldWithPath("quantity").description("Quantity")
    )
));
~~~

This attaches to a POST test whose JSON body contains productId and quantity. prettyPrint() improves snippet formatting; it does not alter the actual body sent or received.

### 8.2. Replacing Sensitive Strings in the Body

When an example response contains data that should be hidden, replacePattern(...) can replace regex matches in the recorded output:

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

.consumeWith(document("profile/get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("\"email\"\\s*:\\s*\"[^\"]+\""),
            "\"email\":\"user@example.test\""
        ),
        prettyPrint()
    )
));
~~~

This example applies to a JSON response containing an email field, replacing its value with a sample address. In real code, verify the regex and preprocessor ordering so the resulting JSON remains valid. Best practice is to build fixtures with fake data from the start; never use real personal data in sample responses.

### 8.3. Per-Operation Preprocessing vs. Client Defaults

| Scope | Configuration | When to Use |
| --- | --- | --- |
| Single operation | document(..., preprocessRequest(...), preprocessResponse(...)) | An endpoint needs special rules. |
| All client operations | operationPreprocessors().withRequestDefaults(...).withResponseDefaults(...) | Shared rules such as pretty printing or URI normalization. |

Example default configuration:

~~~java
client = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .filter(documentationConfiguration(restDocumentation)
        .operationPreprocessors()
            .withRequestDefaults(prettyPrint())
            .withResponseDefaults(prettyPrint()))
    .build();
~~~

This configuration replaces client initialization inside @BeforeEach. When an individual operation needs extra processing, you can add preprocessors directly inside its document(...) call.

## 9. Integrated Example: Normalizing Requests and Generating Snippets

The following example assumes a POST /api/orders endpoint accepting JSON, requiring a request ID, and returning the new resource. The client is already configured with the REST Docs filter.

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.http.MediaType;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

client.post()
    .uri("/api/orders")
    .headers(headers -> {
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.set("X-Request-Id", "doc-test-001");
        headers.setBearerAuth("test-token");
    })
    .bodyValue(Map.of(
        "productId", "BOOK-01",
        "quantity", 2
    ))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals("Location", "/api/orders/42")
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(document("orders/create",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort(),
            modifyHeaders()
                .remove("Authorization")
        ),
        preprocessResponse(prettyPrint()),
        requestHeaders(
            headerWithName("X-Request-Id")
                .description("Request trace ID")
        ),
        requestFields(
            fieldWithPath("productId").description("Product ID"),
            fieldWithPath("quantity").description("Quantity")
        ),
        responseHeaders(
            headerWithName("Location")
                .description("URI of the created order")
        ),
        responseFields(
            fieldWithPath("id").description("Order ID")
        )
    ));
~~~

This snippet combines the techniques covered:

1. headers(...) sends Content-Type, Accept, X-Request-Id, and Authorization to the endpoint.
2. bodyValue(...) sends the JSON request.
3. exchange() executes the HTTP request; expect...() calls verify the response.
4. preprocessRequest(...) normalizes the URI and removes Authorization from the snippet.
5. preprocessResponse(prettyPrint()) formats the JSON response in the snippet.
6. Descriptors describe request headers, request fields, response headers, and response fields.

In the sample test environment, test-token is a dummy credential; never copy real tokens into examples or documentation repositories. Removing Authorization from snippets does not bypass authentication on the endpoint.

## 10. Common Errors

| Symptom | Cause and Resolution |
| --- | --- |
| Request hits the wrong endpoint | Check the URI template, base URL, path variables, and query parameters; avoid manual string concatenation when encoding is needed. |
| Server returns 400 due to query parameter | Check parameter names, types, encoding, and values via UriBuilder. |
| Server returns 415 | Content-Type does not match the body or the endpoint's consumes mapping. |
| Server returns 406 | Accept is incompatible with the endpoint's produces/codecs. |
| Default header causes inconsistent test behavior | Check defaultHeader(...) and overridden headers; avoid carrying unnecessary headers across all operations. |
| Snippets show random host/port | Use REST Docs modifyUris() to normalize recorded URIs while keeping the real base URL for tests. |
| Snippets contain Authorization or Cookie | Use dummy credentials, strip headers from snippets, and inspect generated files before sharing. |
| Body snippet is hard to read | Apply prettyPrint() in document(...) or default preprocessors. |
| Body after replace is no longer valid JSON | Check the regex, replacement content, and preprocessor order; prefer fixtures free of sensitive data. |
| Descriptors do not match request/response | Update requestFields, responseFields, requestHeaders, responseHeaders, and parameters to match actual HTTP traffic. |

## 11. Integrating Snippets into Asciidoctor and CI

For the operation with identifier orders/create, typical snippets are saved under:

~~~text
build/generated-snippets/
└── orders/
    └── create/
        ├── http-request.adoc
        ├── http-response.adoc
        ├── request-headers.adoc
        ├── request-fields.adoc
        ├── response-headers.adoc
        └── response-fields.adoc
~~~

These are representative files; other default snippets may appear depending on configuration and request/response types.

Asciidoctor references the files:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Create an order

include::{snippets}/orders/create/http-request.adoc[]
include::{snippets}/orders/create/request-headers.adoc[]
include::{snippets}/orders/create/request-fields.adoc[]
include::{snippets}/orders/create/http-response.adoc[]
include::{snippets}/orders/create/response-headers.adoc[]
include::{snippets}/orders/create/response-fields.adoc[]
~~~

With Gradle (assuming the Asciidoctor plugin is configured and provides the asciidoctor task):

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

CI can run ./gradlew clean test asciidoctor once plugins/tasks are declared. Tests verify requests/responses, preprocessors normalize snippet content, and Asciidoctor builds pages from fresh results. With plain Markdown, a separate build step is needed to embed or link snippets; the include:: syntax belongs to Asciidoctor.

## 12. Practice Exercises

1. Send a GET with a path variable and query parameters via uri(...)/UriBuilder; assert the actual URL and document the parameters in REST Docs.
2. Add X-Request-Id and a dummy Authorization header to a POST request; verify the server receives the request properly and the snippet omits Authorization.
3. Use modifyUris() to change the host/port in http-request.adoc; compare the URL called in the test with the URL recorded in the snippet.
4. Send JSON via bodyValue(...), enable prettyPrint(), and inspect request-body.adoc.
5. Try replacePattern(...) with a fake email fixture, then verify the JSON in the snippet remains valid.
6. Configure default preprocessors for the client, build Asciidoctor, and confirm snippets contain no tokens or random hostnames.

## 13. Key Takeaways

- Use uri(...)/UriBuilder to construct clear URIs; use header(...), headers(...), and defaultHeader(...) to prepare the actual outgoing headers.
- Choose bodyValue(...) for simple objects/values and body(...) for appropriate publishers or body inserters.
- Request builders determine what data the application receives; REST Docs preprocessors adjust the request/response recorded in snippets.
- modifyUris() normalizes URLs; modifyHeaders() strips unwanted headers; prettyPrint() formats bodies; replacePattern() replaces matching text in recorded output.
- Use fake data in tests, inspect snippets before sharing, and never rely solely on preprocessors to protect secrets.
- Configure CI to run tests before Asciidoctor so documentation is generated from verified requests and responses.
