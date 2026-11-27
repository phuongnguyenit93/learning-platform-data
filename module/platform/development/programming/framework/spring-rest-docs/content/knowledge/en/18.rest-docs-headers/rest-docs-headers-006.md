# Content-Type, Location, ETag, and Cache-Control

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we create verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, verify responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. The snippets are compiled with Asciidoctor/Markdown and integrated into the build and CI.

The **Headers** chapter examines metadata that affects how clients send data, locate resources, and cache responses. This lesson focuses on four HTTP headers:

- `Content-Type`: indicates the representation type of the message body.
- `Location`: provides a URI related to the request outcome, typically the newly created resource or redirect destination.
- `ETag`: provides a validator for a representation so clients can check versions.
- `Cache-Control`: specifies caching policies for a request or response.

After this lesson, you will be able to accurately explain these four headers, distinguish their roles in requests versus responses, assert their values using WebTestClient, and generate request/response header snippets with Spring REST Docs.

## 2. Viewing the Four Headers in an HTTP Exchange

Example of a client creating an order:

~~~http
POST /api/orders HTTP/1.1
Accept: application/json
Content-Type: application/json

{"productId":"BOOK-01","quantity":2}
~~~

The server may return:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/42
Cache-Control: no-store

{"id":42,"productId":"BOOK-01","quantity":2}
~~~

| Header | Sender | Meaning |
| --- | --- | --- |
| `Content-Type` | Client and server | Client sends JSON; server returns JSON. Each message has its own body and declares that body's content type. |
| `Location` | Server | Tells the client the URI of the newly created order. |
| `ETag` | Usually server | A validator the client can resend in `If-Match` or `If-None-Match` on subsequent requests. |
| `Cache-Control` | Client or server | Expresses caching directives for a request or response; meaning depends on direction and directives. |

Not every endpoint uses all four headers. REST Docs should document headers that genuinely belong to the operation's contract, rather than putting all of them into every table.

## 3. Content-Type: Data Type of the Message Body

`Content-Type` indicates the representation format sent in the body. It does not describe the format the client wishes to receive; that purpose belongs to `Accept`.

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Spring REST Docs"}
~~~

The response also has its own `Content-Type`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Spring REST Docs"}
~~~

| Media type | Content |
| --- | --- |
| `application/json` | JSON |
| `application/xml` | XML |
| `text/plain` | Plain text |
| `text/html` | HTML |
| `application/x-www-form-urlencoded` | URL-encoded form |
| `multipart/form-data` | Multipart form, commonly with file uploads |

### 3.1. Distinguishing Content-Type and Accept

| Header | Question Answered |
| --- | --- |
| `Content-Type` | What format is the current message body encoded in? |
| `Accept` | Which format does the client want the server to choose for the returned representation? |

If a request declares `Content-Type: application/json` but the endpoint does not support that media type, the server may return `415 Unsupported Media Type`. If `Accept` is incompatible with representations the server can produce, the server may return `406 Not Acceptable`.

### 3.2. Charset Parameter

A header may contain media type parameters:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

In tests, `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` is appropriate if you only need to verify a compatible media type without comparing all parameters. Choose a stricter assertion if charset or other parameters are part of the contract.

## 4. Location: Resource URI or Redirect Destination

`Location` is a response header containing a URI related to the request result. A common case is the server returning `201 Created` after creating a resource:

~~~http
HTTP/1.1 201 Created
Location: /api/books/42
Content-Type: application/json
~~~

The client can use this URI to read or interact with the newly created resource. `Location` is also used in certain redirect responses; in those cases, the URI indicates the destination the client should look at next.

### 4.1. Documenting Location in REST Docs

~~~java
responseHeaders(
    headerWithName("Location")
        .description("Relative URI of the newly created resource; clients can use this URI to query the resource.")
)
~~~

A useful description should explain whether the URI is absolute or relative, what kind of resource it points to, and how clients use it.

### 4.2. Verifying Location with WebTestClient

~~~java
client.post()
    .uri("/api/books")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("title", "Spring REST Docs"))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals("Location", "/api/books/42");
~~~

The expected value must match the URI actually produced by the endpoint. If the server uses an absolute URI, verify scheme/host as well if that is part of the contract. If the host changes across test environments, REST Docs can normalize the URI in snippets using a preprocessor.

## 5. ETag: Representation Validator

`ETag` is a validator associated with a representation. The server typically returns an ETag for the client to store and reuse in later requests.

~~~http
HTTP/1.1 200 OK
ETag: "book-v42"
Content-Type: application/json

{"id":42,"title":"Spring REST Docs"}
~~~

An ETag is typically represented as a quoted entity-tag; the server may also use a weak validator with the `W/` prefix, such as `W/"book-v42"`. The value is opaque to the client: the client stores and resends the exact validator without inferring internal structure.

### 5.1. Conditional GET with If-None-Match

The client sends the stored ETag in `If-None-Match` when asking the server whether the representation has changed:

~~~http
GET /api/books/42 HTTP/1.1
If-None-Match: "book-v42"
~~~

If the validator still matches according to HTTP rules, the server can return `304 Not Modified` without resending the representation. The client continues using its cached copy. If the representation has changed, the server returns the new representation along with a new ETag.

### 5.2. Conditional Update with If-Match

The client sends `If-Match` when it only wants to update if the resource is still the version the client previously read:

~~~http
PUT /api/books/42 HTTP/1.1
If-Match: "book-v42"
Content-Type: application/json

{"title":"Spring REST Docs, updated edition"}
~~~

If the validator no longer matches, the server typically returns `412 Precondition Failed`. This mechanism helps avoid overwriting another client's changes. `If-Match` and `If-None-Match` are request headers; `ETag` is normally sent by the server in the response.

### 5.3. Documenting ETag in REST Docs

~~~java
responseHeaders(
    headerWithName("ETag")
        .description("Validator of the current representation; clients resend it in If-Match or If-None-Match when making conditional requests.")
)
~~~

Do not describe ETag as a resource code or business ID unless the API specifically defines it that way. Clients should treat the value as opaque and send it back verbatim.

## 6. Cache-Control: Caching Policy Directives

`Cache-Control` can appear in both requests and responses. Specific directives govern caching behavior; you should not describe all `Cache-Control` values as if they meant the same thing.

### 6.1. Common Response Directives

| Directive | General Meaning |
| --- | --- |
| `no-store` | Caches must not store the message under this directive. |
| `no-cache` | Caches must revalidate with the origin before using a stored representation; it does not mean "never store". |
| `private` | The response is intended only for a private cache, not a shared cache. |
| `public` | Allows shared caches to store the response under defined conditions. |
| `max-age=60` | Maximum freshness lifetime is specified as 60 seconds. |
| `must-revalidate` | Once the representation becomes stale, caches must revalidate before using it per the directive. |

Example of a response that should not be stored:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Example of a response that may be retained briefly by a private cache:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, max-age=60
~~~

### 6.2. Request Directives

Clients can also send `Cache-Control` to control how caches handle the request:

~~~http
GET /api/books/42 HTTP/1.1
Cache-Control: no-cache
~~~

Here, the client asks caches to revalidate freshness before serving a stored representation according to HTTP rules. A request with `Cache-Control: no-store` indicates that the client does not want caches to store the request or corresponding response per this directive.

### 6.3. Documenting Cache-Control in REST Docs

~~~java
responseHeaders(
    headerWithName("Cache-Control")
        .description("Response cache policy; this endpoint uses private, max-age=60 to restrict caching to private caches for 60 seconds.")
)
~~~

Descriptions should specify the directives actually used by the endpoint and what they mean to clients and proxies. If caching policies vary by resource type, document them in each corresponding operation.

## 7. Descriptors for the Four Headers

Static imports:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
~~~

Example request header table:

~~~java
requestHeaders(
    headerWithName("Content-Type")
        .description("Content type of the request body; endpoint requires application/json."),
    headerWithName("Accept")
        .description("Media type accepted by the client; endpoint returns application/json.")
)
~~~

Example response header table:

~~~java
responseHeaders(
    headerWithName("Content-Type")
        .description("Response representation type; endpoint returns application/json."),
    headerWithName("Location")
        .description("Relative URI of the newly created resource."),
    headerWithName("ETag")
        .description("Representation validator, used for conditional requests."),
    headerWithName("Cache-Control")
        .description("Caching policy that clients and intermediate caches must follow.")
)
~~~

Only pass headers that actually exist in the operation's request/response. A required descriptor whose header does not appear can cause documentation tests to fail. Use `.optional()` when a header is permitted to be absent; use `.ignored()` when a header should be intentionally omitted from the description table.

## 8. Complete Example: Testing GET and POST with WebTestClient

The example below includes two operations:

- `POST /api/books` accepts JSON and returns `201 Created`, `Location`, and `Content-Type`.
- `GET /api/books/42` returns JSON along with `ETag` and `Cache-Control`.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

Spring Boot normally manages compatible dependency versions. The example uses JUnit 5 and WebFlux.

### 8.2. Test and Controller

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class StandardHeadersDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new BookController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsCreateBookHeaders() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Spring REST Docs"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/books/42")
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("books/create",
                requestHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Content type of the request body; endpoint requires application/json."),
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type accepted by the client; endpoint returns application/json.")
                ),
                responseHeaders(
                    headerWithName(HttpHeaders.LOCATION)
                        .description("Relative URI of the newly created book; use this URI to query the book."),
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Response representation type; endpoint returns application/json.")
                ),
                requestFields(
                    fieldWithPath("title").description("Book title")
                ),
                responseFields(
                    fieldWithPath("id").description("ID of the newly created book"),
                    fieldWithPath("title").description("Book title")
                )
            ));
    }

    @Test
    void documentsGetBookCachingHeaders() {
        client.get()
            .uri("/api/books/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(HttpHeaders.ETAG, "\"book-v42\"")
            .expectHeader().exists(HttpHeaders.CACHE_CONTROL)
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("books/get",
                requestHeaders(
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type accepted by the client; endpoint returns application/json.")
                ),
                responseHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Response representation type; endpoint returns application/json."),
                    headerWithName(HttpHeaders.ETAG)
                        .description("Representation validator; clients resend it in If-None-Match or If-Match when making conditional requests."),
                    headerWithName(HttpHeaders.CACHE_CONTROL)
                        .description("Response cache policy; private, max-age=60 allows private caches to store the representation for 60 seconds.")
                ),
                responseFields(
                    fieldWithPath("id").description("Book ID"),
                    fieldWithPath("title").description("Book title")
                )
            ));
    }

    @RestController
    static class BookController {

        @PostMapping(
            path = "/api/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<ResponseEntity<Map<String, Object>>> create(
                @RequestBody Map<String, String> request) {
            Map<String, Object> body = Map.of(
                "id", 42,
                "title", request.get("title")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/books/42"))
                    .body(body)
            );
        }

        @GetMapping(
            path = "/api/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<ResponseEntity<Map<String, Object>>> get(
                @PathVariable("id") long id) {
            Map<String, Object> body = Map.of(
                "id", id,
                "title", "Spring REST Docs"
            );
            return Mono.just(
                ResponseEntity.ok()
                    .eTag("\"book-v42\"")
                    .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60)).cachePrivate()
                    )
                    .body(body)
            );
        }
    }
}
~~~

The assertions and descriptors reflect the responses produced by the controller:

1. POST verifies status `201`, the `Location` header, `Content-Type`, and the JSON body.
2. GET verifies ETag, the presence of `Cache-Control`, `Content-Type`, and the JSON body.
3. `requestHeaders(...)` documents headers sent by the client; `responseHeaders(...)` documents headers returned by the server.
4. `consumeWith(document(...))` writes snippets after key assertions have run.

The example only checks the presence of `Cache-Control`, while the descriptor records the actual server-returned value into the snippet. If a specific directive is a contract requirement to protect, add an assertion comparing the value in the application's normalized format.

## 9. Using ETag in Conditional Requests

Once an ETag is read from a response, a subsequent test can send that validator in a request:

~~~java
client.get()
    .uri("/api/books/42")
    .header(HttpHeaders.IF_NONE_MATCH, "\"book-v42\"")
    .exchange()
    .expectStatus().isNotModified();
~~~

The snippet above illustrates the case where the representation has not changed and the endpoint actually handles conditional GET. For conditional updates:

~~~java
client.put()
    .uri("/api/books/42")
    .header(HttpHeaders.IF_MATCH, "\"book-v42\"")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("title", "New title"))
    .exchange()
    .expectStatus().isNoContent();
~~~

The success status depends on the endpoint contract. If the ETag does not match, the server usually returns `412 Precondition Failed`; tests should verify the application's actual behavior. When documenting these operations, describe `If-None-Match`/`If-Match` with `requestHeaders(...)`, and `ETag` with `responseHeaders(...)`.

## 10. Generated Descriptors and Snippets

For the two operations in the example, typical snippets may reside under:

~~~text
build/generated-snippets/
└── books/
    ├── create/
    │   ├── http-request.adoc
    │   ├── request-headers.adoc
    │   ├── request-fields.adoc
    │   ├── http-response.adoc
    │   ├── response-headers.adoc
    │   └── response-fields.adoc
    └── get/
        ├── http-request.adoc
        ├── request-headers.adoc
        ├── http-response.adoc
        ├── response-headers.adoc
        └── response-fields.adoc
~~~

Actual files depend on the request/response types and descriptors. Asciidoctor can assemble them:

~~~asciidoc
= Books API
:snippets: build/generated-snippets

== Create book
include::{snippets}/books/create/http-request.adoc[]
include::{snippets}/books/create/request-headers.adoc[]
include::{snippets}/books/create/request-fields.adoc[]
include::{snippets}/books/create/http-response.adoc[]
include::{snippets}/books/create/response-headers.adoc[]

== Get book
include::{snippets}/books/get/http-request.adoc[]
include::{snippets}/books/get/request-headers.adoc[]
include::{snippets}/books/get/http-response.adoc[]
include::{snippets}/books/get/response-headers.adoc[]
include::{snippets}/books/get/response-fields.adoc[]
~~~

Operation names in `document("books/create", ...)` and `document("books/get", ...)` must match the include paths.

## 11. Common Errors

| Symptom | Cause and Resolution |
| --- | --- |
| Server returns 415 | Request `Content-Type` is not supported by the endpoint or the body does not match the declared media type. |
| Server returns 406 | `Accept` requests a representation the endpoint cannot provide. |
| POST returns 201 without `Location` | Check whether the handler builds the resource URI and puts it in the response header. |
| `Location` differs from documented value | Check relative/absolute URI, context path, and base URL; normalize snippets if the test host varies. |
| ETag fails assertion | Check the representation, validator generation rules, and quotes/weak validator prefix. |
| Conditional GET returns 200 instead of 304 | Check whether the server processes `If-None-Match` and whether the validator matches the current representation. |
| Conditional update does not return 412 | Check whether the handler/service enforces `If-Match` and handles version conflicts. |
| Response cached unexpectedly | Check `Cache-Control` in the actual response; distinguish `no-cache` from `no-store` and verify private/shared cache rules. |
| REST Docs reports missing header | Request/response did not send a required descriptor header, or the descriptor was placed on the wrong direction. |
| Snippet is not generated | Check the REST Docs filter, operation identifier, and `consumeWith(document(...))` callback. |

## 12. Integrating Gradle and CI

Once the Asciidoctor plugin and `asciidoctor` task are configured, wire the documentation task to the snippet-generating test task:

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

CI can run:

~~~bash
./gradlew clean test asciidoctor
~~~

Tests assert status, headers, and payload; REST Docs validates descriptors and generates snippets; Asciidoctor compiles the documentation. When the contract for `Content-Type`, `Location`, `ETag`, or `Cache-Control` changes, update tests/descriptors together with the documentation. With plain Markdown, a separate build step is required to embed or link snippets; `include::` syntax belongs to Asciidoctor.

## 13. Practice Exercises

1. Run the two tests `books/create` and `books/get`, and open `request-headers.adoc` and `response-headers.adoc`.
2. Change the POST request's `Content-Type` to `text/plain` while keeping the JSON body; observe the response when the endpoint only accepts JSON, then restore the valid header.
3. Change the `Location` URI in the controller and confirm `expectHeader().valueEquals(...)` catches the change.
4. Change the ETag from `"book-v42"` to `"book-v43"`; verify that a conditional GET test using the old validator accurately reflects the representation state.
5. Try `Cache-Control: no-store` and `private, max-age=60`; write descriptions distinguishing the two policies.
6. Add `If-Match`/`If-None-Match` tests, documenting request headers and response `ETag` in REST Docs.
7. Build Asciidoctor from the new snippets and configure CI to run tests before building documentation.

## 14. Key Takeaways

- `Content-Type` describes the body type of a message; `Accept` describes the representation the client wants to receive.
- `Location` typically provides the URI of a newly created resource or a redirect destination.
- `ETag` is an opaque validator of a representation; clients can send it back via `If-None-Match` or `If-Match` for conditional requests.
- `Cache-Control` carries directives for caches; accurately explain the differences among `no-store`, `no-cache`, `private`, `public`, and `max-age`.
- Use `requestHeaders(...)` for client-sent headers and `responseHeaders(...)` for server-returned headers.
- WebTestClient assertions verify behavior; REST Docs descriptors document headers and check contract compliance before snippets enter documentation.
- Build/CI must run tests before Asciidoctor so documentation is generated from freshly verified HTTP exchanges.
