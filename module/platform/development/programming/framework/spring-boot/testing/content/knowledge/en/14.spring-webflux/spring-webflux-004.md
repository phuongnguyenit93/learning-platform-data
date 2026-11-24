# Spring WebFlux: Sending Requests and Asserting Status, Headers, and Body with WebTestClient

## 1. Goal of Reactive HTTP Testing

When a Spring WebFlux API receives `GET /api/widgets/W-1` or `POST /api/widgets/echo`, the test must prove the **HTTP contract**: the request is sent with the right method, URI, headers, and payload; the response returns the right **status**, **headers**, and **body**. A service returning the right `Mono<Widget>` is not enough to prove the router/controller, JSON codecs, content negotiation, or HTTP error mapping are correct.

Spring's central tool is **`WebTestClient`** (package `org.springframework.test.web.reactive.server`). It uses a request-building style similar to `WebClient` while adding a specialized DSL for asserting responses:

~~~java
webTestClient.get()
        .uri("/api/widgets/W-1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("W-1");
~~~

The snippet above is **illustrative code inside a test that already has `WebTestClient`, `MediaType` imports, and a matching API**; it is not a standalone program. It shows the flow **request → exchange → assertions**, without reducing HTTP semantics to a plain Java unit test.

By the end of this lesson, you will know how to:

- Choose a **mock WebFlux server**, **application context**, or **real HTTP server** to test an API.
- Send `GET`/`POST`, path variables, query params, `Accept`, `Content-Type`, request headers, and JSON bodies.
- Assert statuses `200/400/404/415`; assert header presence/absence, exact values, and content types.
- Assert JSON with `jsonPath`, typed objects with `expectBody(Class)`, lists with `expectBodyList(Class)`, and empty bodies with `isEmpty()`.
- Distinguish HTTP response testing from `Mono`/`Flux` testing with `StepVerifier`, and understand limits with non-terminating streams.
- Write a Java 17+/Spring Boot 3.5.x example suite including `@WebFluxTest` with a mock service and `@SpringBootTest(RANDOM_PORT)` with a real HTTP server.

## 2. Where Does WebTestClient Operate in the Stack?

`WebTestClient` is a **test client**, not a renamed production `WebClient`. It uses a familiar request-building API and then inspects `ExchangeResult` via Spring Test's assertion DSL. It can bind to a **mock server** or a **server listening on TCP**.

~~~text
JUnit Jupiter @Test
       |
       v
WebTestClient.get()/post()/...
       |
       v
ExchangeFunction / request + body encoder
       |
       +---- Mock binding --------------+
       |                                 |
       |     WebFlux Handler/Router/Controller
       |     codecs, filters, advice...
       |     no TCP port opened
       |
       +---- Live server binding -------+
                                         |
                                         v
                             HTTP client sends over TCP
                                         |
                                         v
                             Embedded server Netty/Tomcat...
                                         |
                                         v
                              WebFlux Handler/Controller
       |
       v
.exchange()
       |
       v
ResponseSpec
   .expectStatus()
   .expectHeader()
   .expectBody()/expectBodyList()
~~~

In mock mode, the web framework pipeline can still be verified — mapping, validation, JSON serialization, some filters — yet it **does not prove** TCP listeners, TLS, proxies, web server ports, or real network transport. In live mode, both the HTTP server and client actually run, usually with higher startup cost.

### Three Ways to Bind WebTestClient

| Setup Method | Scope | Real Server? | When Appropriate |
| --- | --- | --- | --- |
| `WebTestClient.bindToController(controller).build()` | Specific controller with matching WebFlux infrastructure | No | Fast test of one controller, usually without a Spring Boot context |
| `WebTestClient.bindToApplicationContext(context).build()` | Created WebFlux context, via mock request/response | No | Testing web configuration/filters/controllers in a context |
| `WebTestClient.bindToServer().baseUrl("http://localhost:...").build()` | Running HTTP server | **Yes** | Testing real HTTP, server behavior, out-of-process contracts |

In Spring Boot:

- `@WebFluxTest(WidgetController.class)` **auto-configures `WebTestClient`** for the WebFlux slice; calling `bindToController` manually is usually unnecessary.
- `@SpringBootTest` can use `@AutoConfigureWebTestClient` to bind the test client to the WebFlux application **in a mock environment**, without a real server.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts an embedded HTTP server; Boot can inject a `WebTestClient` already targeting the real port, using relative URIs. This is the path needed when proving behavior over HTTP.

**Do not confuse `@WebFluxTest` with `@WebMvcTest`:** they select different web stacks. `WebTestClient` can also test a Spring MVC server with an appropriate binding, but this lesson focuses on **Spring WebFlux**.

## 3. Standard Structure of a Test Request

The fluent interface reads left to right:

~~~text
webTestClient
  .get() / .post() / .put() / .delete()
  .uri(...)
  .header(...) / .headers(...)
  .accept(...) / .contentType(...)
  .bodyValue(...) / .body(...)
  .exchange()                 <- sends and retrieves response
  .expectStatus()...          <- HTTP status
  .expectHeader()...          <- response headers
  .expectBody()...            <- JSONPath / raw body
~~~

**The transition point is `exchange()`**: before it you build the request, after it you assert the response. If you forget `exchange()`, the request is not executed as expected. Do not call `expectBody` on a production `WebClient.ResponseSpec`: that is a different API.

### 3.1 Method and URI

~~~java
// GET a resource by ID.
client.get()
      .uri("/api/widgets/{id}", "W-1")
      .exchange();

// GET with query parameter.
client.get()
      .uri(builder -> builder
              .path("/api/widgets")
              .queryParam("limit", 20)
              .build())
      .exchange();

// DELETE resource.
client.delete()
      .uri("/api/widgets/{id}", "W-2")
      .exchange();
~~~

The snippets above are **syntax illustrations in a test with a `WebTestClient` variable `client`**. They only show how to build requests, without assertions yet. Only call endpoints that actually exist in the application under test; the complete example in Section 8 uses the implemented GET/POST endpoints.

The URI template `/api/widgets/{id}` binds path variables properly, avoiding manual string concatenation with special characters. For queries, use `uri(builder -> ...)` for proper encoding and clean parameter addition. Consider edge cases like empty path variables, Unicode characters, or slashes: if constraints exist, test the API in properly encoded form.

### 3.2 Request Headers, Accept, and Content-Type

~~~java
client.post()
      .uri("/api/widgets/echo")
      .header("X-Trace-Id", "trace-42")
      .contentType(MediaType.APPLICATION_JSON)
      .accept(MediaType.APPLICATION_JSON)
      .bodyValue(new EchoRequest("hello"))
      .exchange();
~~~

**`Accept`** describes the media types the client wants to **receive**. Request **`Content-Type`** describes the media type of the body **being sent**. They are two headers with distinct meanings.

- `GET` without a body typically only needs `accept(...)`, and does not need `contentType(...)` forced.
- `POST` with JSON should set `contentType(MediaType.APPLICATION_JSON)` and `bodyValue(requestDto)`.
- Response `Content-Type` should be checked in `expectHeader()`, not inferred from request `Accept`.
- `header("X-Trace-Id", "...")` may be used by a controller/filter as part of the contract; tests should check whether the response echoes or propagates it properly when required.
- Never put real tokens/passwords into logs or test fixtures; if auth is used, use fake test tokens or appropriate security test support.

### 3.3 Sending Objects, Publishers, Forms, and Raw Strings

`bodyValue(dto)` is usually most convenient for regular JSON requests. For a reactive source:

~~~java
client.post()
      .uri("/api/widgets/echo")
      .contentType(MediaType.APPLICATION_JSON)
      .body(Mono.just(new EchoRequest("hello")), EchoRequest.class)
      .exchange();
~~~

This is an **illustrative pattern**, requiring `reactor.core.publisher.Mono` and `EchoRequest` from the application. `body(Publisher, Class)` is useful when the input is already a `Mono`/`Flux`. For single DTOs, `bodyValue(...)` is easier to read.

Do not use an unbounded `Flux` as a request body in a test without limits; it can prevent the request from completing or require handling as a streaming protocol. For forms/multipart, use the appropriate media type and body inserters rather than hand-crafting arbitrary JSON.

## 4. Checking HTTP Status: Assert Exactly Instead of Just "No Error"

After `exchange()`, common checks include:

~~~java
.expectStatus().isOk()             // HTTP 200
.expectStatus().isCreated()        // HTTP 201
.expectStatus().isNoContent()      // HTTP 204
.expectStatus().isBadRequest()     // HTTP 400
.expectStatus().isUnauthorized()   // HTTP 401
.expectStatus().isForbidden()      // HTTP 403
.expectStatus().isNotFound()       // HTTP 404
.expectStatus().isEqualTo(415)     // HTTP 415
~~~

This is a **list of alternative choices**, not a chain of assertions applied simultaneously to one response. `isEqualTo(int)` also works for specific status codes without a dedicated shortcut.

Set statuses according to the contract:

| Scenario | Typically Correct Status | Assertion |
| --- | --- | --- |
| Read an existing widget | 200 OK | `isOk()` |
| Create a new resource successfully | 201 Created, often with `Location` | `isCreated()` |
| Command succeeds and returns no body | 204 No Content | `isNoContent()` and `expectBody().isEmpty()` |
| Invalid payload | 400 Bad Request or 422 per contract | `isBadRequest()` or `isEqualTo(422)` |
| Unauthenticated | 401 Unauthorized | `isUnauthorized()` |
| Authenticated but lacking permission | 403 Forbidden | `isForbidden()` |
| ID does not exist | 404 Not Found | `isNotFound()` |
| Request media type unsupported | 415 Unsupported Media Type | `isEqualTo(415)` |
| Client requests an unproducible response media type | 406 Not Acceptable | `isEqualTo(406)` |
| Unhandled server error | 500 Internal Server Error | `is5xxServerError()` or specific code |

Codes **depend on the application's contract**; not every POST returns 201 and not every validation uses 400. Do not change a test's expected status to 200 just because a controller uses `ResponseEntity.ok()` when the specification requires 201.

**`is2xxSuccessful()`**, `is4xxClientError()`, or `is5xxServerError()` are convenient for category checks, but when an API needs to distinguish 400 from 404, an **exact-code assertion** is far more valuable. A test returning 404 must not count as PASS merely because "it's a 4xx error".

## 5. Checking Response Headers

`expectHeader()` returns assertions dedicated to response headers:

~~~java
client.get()
      .uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectHeader().exists("X-Trace-Id")
      .expectHeader().valueEquals("X-Trace-Id", "trace-42")
      .expectHeader().contentTypeCompatibleWith(
              MediaType.APPLICATION_JSON);
~~~

This is an **illustrative snippet** assuming the controller returns `X-Trace-Id: trace-42`. The complete example in Section 8 sends the matching request header.

Distinguish the assertion types:

- `exists("X-Trace-Id")`: only ensures the header is present, **does not prove its value is right**.
- `valueEquals("X-Trace-Id", "trace-42")`: checks the expected value, suitable for correlation IDs and custom headers.
- `contentType(MediaType.APPLICATION_JSON)`: requires an exact media type match per API comparison rules.
- `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`: suitable when parameters such as charset may vary while the media type remains compatible.
- `location("/api/widgets/W-3")` or `valueEquals("Location", "...")`: useful with 201 responses.
- Cache-control, CORS, ETag, retry-after, security headers, etc. should only be asserted if they are part of the contract.

HTTP header names are **case-insensitive** per protocol. Do not write assertions that depend on header order or the entire header set when the server/framework can add valid headers. For cookies with `HttpOnly`, `Secure`, `SameSite` attributes, assert the relevant contract attributes rather than mere presence.

**Note on `Location`:** 201 Created typically includes a header containing the newly created resource's URI. A POST that only echoes back a payload without **creating a resource** should normally return 200 rather than attaching 201 just to "test another status". The example in Section 8 intentionally returns 200 for echo.

## 6. Checking the Body: JSONPath, Typed Objects, Lists, and Empty Bodies

### 6.1 JSONPath When Only Certain Fields Matter

~~~java
client.get()
      .uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.id").isEqualTo("W-1")
      .jsonPath("$.name").isEqualTo("Pen");
~~~

`$` is the JSON root. `$.id` selects the `id` field; `$.items[0].id` selects `id` in the first element of the `items` array. JSONPath is useful when a test only cares about specific public fields without locking property order or whitespace.

To assert field presence/absence, use assertions like `exists()` and `doesNotExist()` from the JSONPath API. For numeric values, note that JSON number decoding may use Integer/Long/Double types; pick type-appropriate assertions or decode into a DTO if type conversion matters.

### 6.2 Comparing Full JSON When the Contract Requires It

~~~java
client.get()
      .uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .json("{\"id\":\"W-1\",\"name\":\"Pen\"}");
~~~

`json(...)` uses semantic JSON comparison, unlike raw string comparison that breaks on field order or whitespace. Use it only when data is truly deterministic and you want to verify the entire relevant structure. If a valid new field is added to the response, the JSON comparison strictness mode determines whether the test fails; pick the mode matching your contract.

### 6.3 Decoding to a Java Type

~~~java
WidgetResponse actual = client.get()
        .uri("/api/widgets/W-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(WidgetResponse.class)
        .returnResult()
        .getResponseBody();

assertEquals(new WidgetResponse("W-1", "Pen"), actual);
~~~

This is **illustrative code inside a test that imports `WidgetResponse` and JUnit's `assertEquals`**. `expectBody(Class<T>)` decodes the response using the test client's codecs. When a record implements value-based `equals`, object comparison is clearer than JSONPath if the whole DTO matters.

Another style:

~~~java
client.get().uri("/api/widgets/W-1")
      .exchange()
      .expectBody(WidgetResponse.class)
      .isEqualTo(new WidgetResponse("W-1", "Pen"));
~~~

For generic types such as `List<ApiEnvelope<WidgetResponse>>`, use the appropriate `ParameterizedTypeReference<T>` overload instead of expecting the JVM to retain full generic type information via `Class<T>`.

### 6.4 Decoding a Finite List

~~~java
client.get()
      .uri("/api/widgets")
      .exchange()
      .expectStatus().isOk()
      .expectBodyList(WidgetResponse.class)
      .hasSize(2)
      .contains(new WidgetResponse("W-1", "Pen"));
~~~

This makes sense when the API returns a **finite** JSON array. `expectBodyList` must collect the body to decode it; do not use it for an **infinite** `Flux`/SSE stream.

### 6.5 Empty Body

~~~java
client.delete()
      .uri("/api/widgets/W-2")
      .exchange()
      .expectStatus().isNoContent()
      .expectBody().isEmpty();
~~~

This is an **illustration for a DELETE endpoint with a 204 contract**, not an endpoint implemented in the Section 8 example. Checking `isEmpty()` catches controllers that accidentally serialize an object/body despite a no-content contract.

### 6.6 Custom Assertions When the DSL Is Not Enough

~~~java
client.get().uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectBody(WidgetResponse.class)
      .consumeWith(result -> {
          WidgetResponse body = result.getResponseBody();
          assertNotNull(body);
          assertTrue(body.id().startsWith("W-"));
      });
~~~

This is an **illustrative snippet** (requiring `assertNotNull`, `assertTrue`). `consumeWith` lets you write custom assertions; there is no need to cram every rule into a complex JSONPath expression. You can also use `returnResult()` and assert outside the fluent DSL as in Section 6.3.

## 7. WebFlux Testing Levels and Their Impact on Results

The same `WebTestClient` assertion can execute in different environments, yielding **different evidence**:

| Environment | What Starts Up? | What It Proves | What It Does Not Automatically Prove |
| --- | --- | --- | --- |
| `bindToController(...)` | WebFlux handler infrastructure for the given controller | Controller mapping and handling under mock config | Spring Boot app wiring, server, infrastructure |
| `@WebFluxTest(WidgetController.class)` | WebFlux slice, codecs, controller, selected filters/advice | Request/response at the web layer, mocked/imported dependencies | Real service/repository, TCP |
| `@SpringBootTest + @AutoConfigureWebTestClient` with mock environment | More application beans, mock-bound `WebTestClient` | Context wiring and web behavior without TCP | Server port, TLS/network |
| `@SpringBootTest(RANDOM_PORT)` | Full context and real HTTP server | HTTP request/response over loopback and server | Production DB, reverse proxy, production auth if unconfigured |

In `@WebFluxTest`, a controller's `@Service` dependency is normally filtered out. Use **`@MockitoBean`** (Spring Framework 6.2+/Spring Boot 3.4+) to supply the mock **directly inside the `ApplicationContext`**; plain Mockito `@Mock` does not create a bean in the Spring context.

If service logic is the target, test it separately with JUnit/Mockito using `Mono`/`Flux` and `StepVerifier`. If the bug is in codecs, routing, or HTTP status, use `WebTestClient`. If you need to test HTTP transport/server behavior, use `RANDOM_PORT`. Do not default to full-context tests for every service branch.

### Different Examples of the Same Request

- `@WebFluxTest` mocks `WidgetService.findById("W-1")` returning `Mono.just(...)`. The test proves the controller picks the right status/header/body when the service emits data.
- `@SpringBootTest(RANDOM_PORT)` uses the real `InMemoryWidgetService` to return the widget; the test verifies both wiring and the loopback HTTP server.
- A database integration test would need a real repository/DB if queries or transactions are the target. Just because `WebTestClient` returns 200 does not mean SQL was tested.

## 8. Complete Example: Spring Boot 3.5.x + Java 17 + WebFlux + WebTestClient

This hands-on example provides **production code** in `src/main/java` and **two test classes** in `src/test/java`. It uses `spring-boot-starter-webflux`, `spring-boot-starter-test`, JUnit Jupiter, and Mockito. No database, Docker, or external network services are required. One test class uses only the mock WebFlux server; the other starts an embedded HTTP server on a random port.

API Scope:

| Method/URI | Behavior | Status | Body |
| --- | --- | --- | --- |
| `GET /api/widgets/W-1` | Return existing widget | 200 | `{"id":"W-1","name":"Pen"}` |
| `GET /api/widgets/not-found` | Widget missing | 404 | Empty |
| `GET /api/widgets` | List widgets | 200 | Two-element JSON array |
| `GET /api/widgets/ping` | Text ping | 200 | `pong` |
| `POST /api/widgets/echo` with valid message | Trim text and echo | 200 | JSON message + length |
| `POST /api/widgets/echo` with blank message | Reject | 400 | Empty |
| `POST /api/widgets/echo` with `text/plain` | Wrong media type | 415 | Error body per handling mechanism |

### 8.1 Directory Tree

~~~text
src/
  main/
    java/example/webflux/
      WebFluxDemoApplication.java
      Widget.java
      WidgetResponse.java
      EchoRequest.java
      EchoResponse.java
      WidgetService.java
      InMemoryWidgetService.java
      WidgetController.java
  test/
    java/example/webflux/
      WidgetControllerSliceTest.java
      WidgetHttpIntegrationTest.java
~~~

**All files** use the `example.webflux` package. Keep tests under the same package hierarchy as the root `@SpringBootApplication` so Spring Boot locates the main configuration. Java records require Java 17+.

### 8.2 WebFluxDemoApplication.java

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` allows Spring to scan `@RestController` and `@Service`. The project should use only `spring-boot-starter-webflux` for this example; if `spring-boot-starter-web` (MVC) is also added, Boot normally prefers the MVC web application type unless configured otherwise.

### 8.3 Widget.java

~~~java
package example.webflux;

public record Widget(String id, String name) {
}
~~~

### 8.4 WidgetResponse.java

~~~java
package example.webflux;

public record WidgetResponse(String id, String name) {
}
~~~

`WidgetResponse` is the HTTP response DTO, separated from the `Widget` domain record. Jackson encodes it to JSON with `id` and `name`, without requiring mock records.

### 8.5 EchoRequest.java

~~~java
package example.webflux;

public record EchoRequest(String message) {
}
~~~

### 8.6 EchoResponse.java

~~~java
package example.webflux;

public record EchoResponse(String message, int length) {
}
~~~

With the trimmed message `"xin chào"`, `String.length()` returns **8 UTF-16 code units** in this case. This is not a universal Unicode grapheme-counting rule for all languages; real payloads may contain emojis/surrogate pairs. In this exercise, the value 8 is deterministic.

### 8.7 WidgetService.java

~~~java
package example.webflux;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface WidgetService {
    Mono<Widget> findById(String id);
    Flux<Widget> list();
}
~~~

The interface returns `Mono` for at most one widget and `Flux` for the list. This is the boundary allowing `@WebFluxTest` to replace the service with a Mockito mock while keeping the controller real.

### 8.8 InMemoryWidgetService.java

~~~java
package example.webflux;

import java.util.List;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InMemoryWidgetService implements WidgetService {

    private static final List<Widget> DATA = List.of(
            new Widget("W-1", "Pen"),
            new Widget("W-2", "Notebook"));

    @Override
    public Mono<Widget> findById(String id) {
        return Flux.fromIterable(DATA)
                .filter(widget -> widget.id().equals(id))
                .next();
    }

    @Override
    public Flux<Widget> list() {
        return Flux.fromIterable(DATA);
    }
}
~~~

The production service runs for real under `@SpringBootTest(RANDOM_PORT)`. It uses **immutable** in-memory data, so two HTTP tests can read without order dependence or database cleanup. This is not a real Reactive Repository example or proof of non-blocking database I/O.

### 8.9 WidgetController.java

~~~java
package example.webflux;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/widgets")
public class WidgetController {

    private final WidgetService service;

    public WidgetController(WidgetService service) {
        this.service = service;
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<WidgetResponse>> findById(
            @PathVariable("id") String id,
            @RequestHeader(name = "X-Trace-Id",
                    defaultValue = "missing") String traceId) {

        return service.findById(id)
                .map(widget -> ResponseEntity.ok()
                        .header("X-Trace-Id", traceId)
                        .body(new WidgetResponse(
                                widget.id(), widget.name())))
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<WidgetResponse> list() {
        return service.list()
                .map(widget -> new WidgetResponse(
                        widget.id(), widget.name()));
    }

    @GetMapping(path = "/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<EchoResponse>> echo(
            @RequestBody Mono<EchoRequest> requestBody) {

        return requestBody.map(request -> {
            if (request.message() == null
                    || request.message().isBlank()) {
                return ResponseEntity.badRequest()
                        .<EchoResponse>build();
            }

            String value = request.message().trim();
            return ResponseEntity.ok()
                    .header("X-Handler", "echo")
                    .body(new EchoResponse(value, value.length()));
        });
    }
}
~~~

Mechanics:

- `findById` receives the path variable and request header; when the service returns a widget, the response is 200 with `X-Trace-Id` and JSON DTO; when `Mono.empty()`, it returns 404 with no body.
- `list` maps each domain `Widget` to `WidgetResponse`, and Spring WebFlux serializes it into a JSON array once the `Flux` completes.
- `ping` returns `text/plain`, illustrating a non-JSON body.
- `echo` accepts the request body as `Mono<EchoRequest>`, trims the message, returns 200 + `X-Handler` + JSON; blank/empty messages return 400. `consumes` restricts the request content type, resulting in 415 when a client sends `text/plain`.
- Never call `block()` or `subscribe()` manually inside the controller. WebFlux manages the subscription for the response publisher when handling the request.

**Note on error bodies:** the framework or an application-wide `@ControllerAdvice` may generate a JSON error response for 400/415 statuses. When the contract only specifies **status**, do not assert the error body must be empty unless you deliberately designed the controller to do so.

### 8.10 Slice Test — WidgetControllerSliceTest.java

~~~java
package example.webflux;

import java.util.Optional;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(WidgetController.class)
@DisplayName("WebFlux slice: status, headers, body")
class WidgetControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    WidgetService service;

    @Test
    @DisplayName("GET found: 200, X-Trace-Id and JSON")
    void getFoundWidget() {
        when(service.findById("W-1"))
                .thenReturn(Mono.just(new Widget("W-1", "Pen")));

        client.get()
                .uri("/api/widgets/{id}", "W-1")
                .header("X-Trace-Id", "slice-42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Trace-Id", "slice-42")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("W-1")
                .jsonPath("$.name").isEqualTo("Pen");

        verify(service).findById("W-1");
    }

    @Test
    @DisplayName("GET not found: 404 and empty body")
    void getMissingWidget() {
        when(service.findById("missing"))
                .thenReturn(Mono.empty());

        client.get()
                .uri("/api/widgets/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();

        verify(service).findById("missing");
    }

    @Test
    @DisplayName("GET list: decode typed JSON array")
    void getWidgetList() {
        when(service.list()).thenReturn(Flux.just(
                new Widget("W-1", "Pen"),
                new Widget("W-2", "Notebook")));

        client.get()
                .uri("/api/widgets")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBodyList(WidgetResponse.class)
                .hasSize(2)
                .contains(
                        new WidgetResponse("W-1", "Pen"),
                        new WidgetResponse("W-2", "Notebook"));

        verify(service).list();
    }

    @Test
    @DisplayName("POST JSON: 200, custom response header, typed body")
    void echoValidJson() {
        EchoResponse actual = client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("  xin chào  "))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Handler", "echo")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(EchoResponse.class)
                .returnResult()
                .getResponseBody();

        assertEquals(new EchoResponse("xin chào", 8), actual);
    }

    @Test
    @DisplayName("POST blank message: 400 and empty body")
    void echoRejectsBlankMessage() {
        client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("   "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody().isEmpty();
    }

    @Test
    @DisplayName("POST text/plain: 415 because consumes is JSON")
    void echoRejectsUnsupportedMediaType() {
        client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not-json")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    @DisplayName("GET ping: 200, text/plain, String body")
    void pingReturnsPlainText() {
        client.get()
                .uri("/api/widgets/ping")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN)
                .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

**There are 7 `@Test` methods**. `@WebFluxTest` creates the WebFlux slice and auto-configures `WebTestClient`, without opening a TCP port. `@MockitoBean` creates a mock `WidgetService` in the Spring test context, because the regular `@Service InMemoryWidgetService` is not part of the slice; if only Mockito's `@Mock` were used on a field, the controller would still lack a bean.

Assertions are split by purpose:

1. `getFoundWidget`: sends a request header, verifies status 200, response header echoing the exact value, and two JSON fields; verifies the service receives the exact ID.
2. `getMissingWidget`: service returns `Mono.empty()`, controller must emit 404 with an empty body.
3. `getWidgetList`: mock returns a finite `Flux`, `WebTestClient` decodes into `List<WidgetResponse>`, checks size and contents.
4. `echoValidJson`: verifies request DTO serialization, server decoding, trimming, and typed response encoding; also verifies `X-Handler`.
5. `echoRejectsBlankMessage`: blank input must not succeed; asserts status 400 and an empty body since the controller returns `ResponseEntity.badRequest().build()`.
6. `echoRejectsUnsupportedMediaType`: `text/plain` request body does not match `consumes=application/json`, asserts only 415 to stay independent of default error body formatting.
7. `pingReturnsPlainText`: shows responses can be `text/plain` instead of JSON, using `expectBody(String.class)`.

**QA note:** the `java.util.Optional` import in the class above is unused and can be removed when applying to a project; an extra import does not fail Java compilation, though keeping code clean is best. Mock methods are only stubbed when a code path actually invokes the service, avoiding unnecessary setup in `@BeforeEach`.

### 8.11 HTTP Integration Test — WidgetHttpIntegrationTest.java

~~~java
package example.webflux;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("Real WebFlux HTTP on random port")
class WidgetHttpIntegrationTest {

    @Autowired
    WebTestClient client;

    @LocalServerPort
    int port;

    @Test
    @DisplayName("GET over real server: status, header, JSON")
    void liveServerGetWorks() {
        assertTrue(port > 0);

        client.get()
                .uri("/api/widgets/W-1")
                .header("X-Trace-Id", "wire-7")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Trace-Id", "wire-7")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("W-1")
                .jsonPath("$.name").isEqualTo("Pen");
    }

    @Test
    @DisplayName("POST over real HTTP: JSON round-trip")
    void liveServerPostWorks() {
        client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest(" hello "))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Handler", "echo")
                .expectBody(EchoResponse.class)
                .isEqualTo(new EchoResponse("hello", 5));
    }
}
~~~

**There are 2 `@Test` methods**. In Spring Boot 3.5.x, with `RANDOM_PORT` and WebFlux on the classpath, Boot supplies a `WebTestClient` pre-configured for the running server that supports relative URIs. The port is OS-assigned, not hardcoded to 8080. `@LocalServerPort` confirms the server bound a real port.

In the real HTTP test, `InMemoryWidgetService` **runs for real** through the controller, not mocked. However, it only holds a fixed list and does not test a database or external network service.

**Do not equate the two test types:** `@AutoConfigureWebTestClient` is for a `WebTestClient` bound directly to a mock application in eligible contexts; `RANDOM_PORT` creates a real embedded server. When you need to be certain a test traverses TCP, check the server mode and client configuration rather than just seeing an injected `WebTestClient`.

### 8.12 Gradle: Dependencies and Run Commands

In a **Spring Boot 3.5.x** project that already has the Gradle plugin, dependency management, and Java 17 toolchain, `build.gradle` needs:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **configuration fragment**, not a full build file; if you want to use `StepVerifier` in a separate publisher test, you can add `testImplementation 'io.projectreactor:reactor-test'` if the starter/project does not already provide that dependency.

Run using the Gradle wrapper at the project root:

~~~bash
./gradlew test --tests example.webflux.WidgetControllerSliceTest --tests example.webflux.WidgetHttpIntegrationTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.webflux.WidgetControllerSliceTest --tests example.webflux.WidgetHttpIntegrationTest
~~~

**Expected outcome** in an environment with matching dependencies and WebFlux: **9 JUnit Jupiter methods PASS** (7 in slice, 2 in HTTP integration). The tests print no custom stdout; Gradle/IDE may display totals and `BUILD SUCCESSFUL`, while random ports and startup logs vary. No Testcontainers or DB are needed.

If a project already has both `spring-boot-starter-web` and WebFlux, Spring Boot normally prefers Servlet MVC. To learn the reactive stack properly, **do not add the MVC starter** in this mini project, or configure `spring.main.web-application-type=reactive` when there is a specific reason and compatible dependencies.

## 9. Advanced Assertion Techniques: Keeping Contracts Clear and Reducing Brittle Tests

### 9.1 Checking Status, Headers, and Body in One Flow

Writing assertions close to the request lets readers see **the exact contract of an endpoint**:

~~~java
client.get().uri("/api/widgets/W-1")
      .header("X-Trace-Id", "t-1")
      .exchange()
      .expectStatus().isOk()
      .expectHeader().valueEquals("X-Trace-Id", "t-1")
      .expectBody()
      .jsonPath("$.id").isEqualTo("W-1");
~~~

If multiple independent assertions should run together so you see all failures in one response, `WebTestClient.ResponseSpec.expectAll(...)` is supported by Spring Framework:

~~~java
client.get().uri("/api/widgets/W-1")
      .exchange()
      .expectAll(
          spec -> spec.expectStatus().isOk(),
          spec -> spec.expectHeader()
                      .contentTypeCompatibleWith(
                              MediaType.APPLICATION_JSON));
~~~

This is a **syntax illustration**; the endpoint needs a matching real/mock service before making the request. `expectAll` helps collect multiple assertion failures; do not use it to replace test organization or skip body assertions.

### 9.2 Do Not Assert Raw JSON Strings Unless Whitespace/Order Is Part of the Contract

JSON strings can differ in field order while having the exact same meaning. `jsonPath`, `json(...)`, or typed bodies are usually more resilient:

~~~java
.expectBody()
.jsonPath("$.id").isEqualTo("W-1")
.jsonPath("$.name").isEqualTo("Pen");
~~~

If an API has a rule "the `secret` field must never appear", add `jsonPath("$.secret").doesNotExist()` to the appropriate test rather than only checking the two valid fields.

If a response contains timestamps, UUIDs, or random values, do not assert them against an uncontrolled literal. Inject a `Clock`/`IdGenerator` or verify format/range and the deterministic parts per contract.

### 9.3 Checking the Location Header When Creating Resources

For a real resource-creation API:

~~~java
client.post().uri("/api/widgets")
      .contentType(MediaType.APPLICATION_JSON)
      .bodyValue(new CreateWidgetRequest("Pen"))
      .exchange()
      .expectStatus().isCreated()
      .expectHeader().exists("Location");
~~~

This is an **illustration for a different API**, since the mini project in Section 8 only has POST echo. `CreateWidgetRequest` and `POST /api/widgets` must be defined by the application to run. In production tests, also assert a valid `Location` value, the ID in the body, and that reading back the created resource returns the expected state.

### 9.4 Checking Response Cookies and Caching

When the contract involves security cookies, `ETag`, or `Cache-Control`, assert the exact fields and attributes rather than only status 200. For example, checking a custom header:

~~~java
client.get().uri("/api/widgets/W-1")
      .header("X-Trace-Id", "t-2")
      .exchange()
      .expectHeader().valueEquals("X-Trace-Id", "t-2");
~~~

For cookies, avoid logging session secrets. Do not assert every header produced by Netty/codecs because a valid framework upgrade can add headers or change ordering without breaking the API.

## 10. Flux Streaming and SSE: Do Not Wait for an Infinite Response to End

`expectBodyList(WidgetResponse.class)` and `expectBody()` suit **finite bodies**. If an API returns an infinite `Flux` or SSE `text/event-stream`, trying to collect everything into a list can **wait forever**, time out, or exhaust memory.

For streaming responses, use `returnResult(SomeType.class)` to get a `Flux<T>` and `StepVerifier` to check the initial events and cancel the subscription once satisfied:

~~~java
Flux<WidgetResponse> events = client.get()
        .uri("/api/widgets/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(WidgetResponse.class)
        .getResponseBody();

StepVerifier.create(events.take(2))
        .expectNext(
                new WidgetResponse("W-1", "Pen"),
                new WidgetResponse("W-2", "Notebook"))
        .verifyComplete();
~~~

**This is a separate illustration**, not runnable against the Section 8 project because it does not declare `/api/widgets/stream`. Using it requires adding a real SSE endpoint, importing `Flux`/`StepVerifier`, and adding the `reactor-test` dependency. `take(2)` consumes only two elements and cancels upstream instead of waiting for an infinite stream to complete on its own.

**Testing backpressure and timing** are additional concerns:

- `WebTestClient` checks the HTTP contract; `StepVerifier` checks item ordering and publisher completion/error signals.
- To test operator timeouts/delays, use `StepVerifier.withVirtualTime(...)` when the logic supports a virtual scheduler, avoiding `Thread.sleep`.
- With streaming over a real server, buffering/proxies/flushing can make behavior differ from mock binding. If the SSE contract is critical, keep at least one integration test over TCP.
- Never call `block()` on the Netty event loop inside a controller to "simplify" tests; that can break the non-blocking model.

## 11. Error Handling: Test Errors Too, Without Depending on Default Error Bodies

WebFlux has several sources of errors:

1. Resource not found: controller can return `ResponseEntity.notFound()`, as in the example.
2. Malformed payload: codec can throw a decode error; the framework picks 400.
3. Unsupported request media type: `consumes` mapping can lead to 415.
4. Incompatible response `Accept`: can return 406.
5. Bean/service failure: can be handled by `@RestControllerAdvice` per contract or fall back to 500.
6. Missing permissions: Spring Security WebFlux filters can return 401/403.

**You cannot assume all errors share the same body by default**. Spring Boot error handlers, Problem Details (`application/problem+json`), custom `@RestControllerAdvice`, locale, and framework version can alter the error body. If the API has a formal error schema, create typed DTO or JSONPath assertions for `code`, `message`, correlation ID, and `Content-Type` per contract. If only checking rejection, a status assertion may suffice.

Example pattern when the contract defines a JSON error:

~~~java
client.post().uri("/api/orders")
      .contentType(MediaType.APPLICATION_JSON)
      .bodyValue(new OrderRequest(""))
      .exchange()
      .expectStatus().isBadRequest()
      .expectBody()
      .jsonPath("$.code").isEqualTo("INVALID_ORDER");
~~~

This is an **illustration** for an API with `OrderRequest`/`/api/orders`/custom error mapping, not the default response of the mini project. Do not copy this assertion onto a controller that does not define an error DTO.

With `@WebFluxTest`, web-layer `@ControllerAdvice`s can be picked up; if production advice is filtered out or not auto-loaded, import the required configuration and test the real error contract. Do not mock the error mapper itself when the goal is to test it.

## 12. Spring Security, Authentication, and CSRF in WebFlux Tests

When an application uses reactive Spring Security, `@WebFluxTest` or full-context WebFlux tests may enforce security filters. A request expecting 200 may return **401/403** due to missing authentication or CSRF; do not solve that by disabling all filters without understanding the scope.

For security testing:

- Use `spring-security-test` compatible with reactive `WebTestClient`.
- Use `SecurityMockServerConfigurers.mockUser()` or appropriate test configurers for identity/authorities.
- For methods requiring CSRF, use the `csrf()` test configurer when policy demands it.
- Assert 401/403, response headers, and error bodies per the security contract.

Syntax example (not standalone; project must include Spring Security and its test dependency):

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

WebTestClient authorizedClient = client.mutateWith(
        mockUser("tester").roles("READER"));

authorizedClient.get()
        .uri("/api/widgets/W-1")
        .exchange()
        .expectStatus().isOk();
~~~

A test requiring role `ADMIN` while granted only `READER` may fulfill the contract when receiving 403. Do not try fixing `@MockitoBean` for the service when the security filter rejects the request **before the controller ever calls the service**.

## 13. Timeouts and Stability of WebTestClient

`WebTestClient` enforces a time limit waiting for a response. Against a real test server, duration depends on startup, CI load, thread scheduling, and I/O. Do not use tight millisecond timeouts to prove production latency.

Manual configuration when binding to a live server:

~~~java
WebTestClient live = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
~~~

This is **illustrative code**; a real server must be listening on port 8080 and `java.time.Duration` must be imported. With `@SpringBootTest(RANDOM_PORT)`, **do not hardcode 8080**: use the Boot-injected client or `@LocalServerPort`.

When a test fails with a timeout:

1. Check whether the server bound a real port and the controller responded.
2. Check whether `Mono`/`Flux` completes or is an intentionally long stream.
3. Check for blocking calls on the event loop or deadlocks.
4. Check whether real external dependencies have deadlines on their HTTP client/DB driver, rather than merely increasing the test timeout.
5. If a mock service returns `Mono.never()`, the client will wait until timeout; a business-error test should stub a deterministic publisher like `Mono.error(...)`.
6. Avoid `Thread.sleep`, random delays, or shared mutable state to wait for an event. Use `StepVerifier`, virtual time, or synchronization signals when testing reactive publishers.

Configure timeouts at the right layer: `WebTestClient`'s timeout is **the observation deadline for the HTTP test response**, and does not safely cancel every downstream task or roll back side effects.

## 14. Common Mistakes When Sending Requests and Asserting Responses

**Mistake 1 — Forgetting `exchange()`.**  
You built the request without triggering the exchange and obtaining `ResponseSpec`, so there is no response to assert.

**Mistake 2 — Confusing request `Content-Type` with `Accept`.**  
POST's `Content-Type` says the outgoing body is JSON; `Accept` expects JSON back. If `consumes` does not match, the server may return 415; if no response media type satisfies `Accept`, it may return 406.

**Mistake 3 — Asserting only `is2xxSuccessful()`.**  
You can miss distinctions between 200, 201, or 204 that are core to the contract. Use specific status assertions.

**Mistake 4 — Checking only header existence.**  
`exists("X-Trace-Id")` does not prove the server echoed the request's exact trace ID. Use `valueEquals` when the value is part of the contract.

**Mistake 5 — Overly rigid raw JSON string comparison.**  
Field order or whitespace can differ while the JSON remains equivalent. Use JSONPath, typed objects, or semantic JSON comparison.

**Mistake 6 — Asserting framework error bodies must be empty.**  
Boot may add JSON error details or Problem Details. Only assert `isEmpty()` when the controller/contract explicitly specifies an empty body.

**Mistake 7 — Mocking the controller itself.**  
The test no longer tests real mapping/codecs/controller code. Keep the controller real in `@WebFluxTest`, mocking only collaborators like `WidgetService`.

**Mistake 8 — Using only Mockito `@Mock` while the controller still lacks a bean.**  
`@Mock` does not register with the Spring context. Use `@MockitoBean` in Boot 3.4+/Framework 6.2 or a test-config bean.

**Mistake 9 — Thinking `@WebFluxTest` runs a Netty/TCP server.**  
That is a mock web environment. To test a real HTTP server, use `@SpringBootTest(RANDOM_PORT)` or `bindToServer` pointing at the right endpoint.

**Mistake 10 — Using `expectBodyList` for non-terminating SSE/Flux.**  
The body collector waits for completion; switch to `returnResult` and `StepVerifier` with an event limit and cancel the subscription.

**Mistake 11 — Calling `block()` in a reactive controller.**  
Even if a small test passes, blocking on the event loop breaks the non-blocking model and can cause low throughput or deadlocks at runtime.

**Mistake 12 — Having both Spring MVC and WebFlux installed and assuming Boot picks WebFlux.**  
When both web stacks are on the classpath, Spring MVC usually wins. Check the web application type setting and dependencies.

**Mistake 13 — Mistaking 401/403 responses for a missing bean.**  
Security filters may block before the controller. Use Spring Security Test with the required identity/roles/CSRF rather than disabling filters blindly.

**Mistake 14 — Not testing producer code and only stubbing expected outcomes.**  
A slice test with a mock service proves the controller contract, not the real service or database. Add unit/integration tests at the right layers.

**Mistake 15 — Hardcoding random port 8080 in integration tests.**  
`RANDOM_PORT` picks an available port. Use the injected `WebTestClient` with relative URIs or `@LocalServerPort`.

**Mistake 16 — Forgetting state cleanup when a live server test writes data.**  
With a real HTTP server, handlers run on a different thread from the test; test-method transaction rollback does not cover server transactions. Use an isolated test database and explicit cleanup.

## 15. Workflow for Building an Effective WebFlux API Test

Suppose the contract is "GET widget by ID returns 200 + JSON if it exists, 404 if missing; request trace ID is echoed":

1. **Write out the public contract**: URI, method, request headers, media types, status, response schema.
2. **Choose the scope**: controller only → `@WebFluxTest`; controller + real HTTP server → `@SpringBootTest(RANDOM_PORT)`.
3. **Prepare collaborators**: `@MockitoBean` with `Mono.just(...)`/`Mono.empty()`, or the real service in integration tests.
4. **Build the request**: `get()`, `uri(...)`, `header(...)`, `accept(...)`.
5. **Trigger `exchange()`** and assert status first for clear failure messages.
6. **Assert headers**: custom trace, `Content-Type`, `Location`/cache/security when part of the contract.
7. **Assert body**: JSONPath for key fields, typed DTO for the whole object, list for finite `Flux`, `isEmpty` for genuinely empty bodies.
8. **Test error branches**: not found, malformed JSON, unsupported media type, unauthorized/forbidden per contract.
9. **Test streaming separately**: do not collect indefinitely; use `StepVerifier` and limit event counts.
10. **Ensure repeatability**: fixed data, no dependence on current time, static random ports, or production networks.
11. **Cross-check with other layer tests**: service logic and downstream DB/HTTP must have their own tests rather than relying on mock controller tests.
12. **Run in CI**: verify startup, codec modules, Spring Boot version, response timeout, and active profile.

### Pre-Commit Checklist

- [ ] Clearly specified request method, URI/path/query, `Accept`, and `Content-Type`.
- [ ] `exchange()` is called before `expect...`.
- [ ] Asserted **specific HTTP codes** required by the contract, not just any 2xx.
- [ ] Response headers use `valueEquals` when exact values matter; `Content-Type` checked with the appropriate media type.
- [ ] Body uses JSONPath, typed DTO, or typed list properly; empty bodies verified when required by the contract.
- [ ] Error paths have assertions for 400, 404, 415, or matching statuses/formats.
- [ ] In `@WebFluxTest`, controller is real and collaborators use `@MockitoBean` or appropriate test beans.
- [ ] Mock binding is not confused with an HTTP network test.
- [ ] With `RANDOM_PORT`, 8080 is not hardcoded; injected client/real port is used.
- [ ] `expectBodyList` is not used for infinite streams; cancellation/timeout strategy is in place.
- [ ] Spring Security, CSRF, and error advice are properly tested when in scope.
- [ ] No blocking calls inside reactive controllers.
- [ ] No credentials/secrets exposed in test logs, headers, or payloads.
- [ ] Real HTTP tests have isolated fixtures and explicit cleanup for side effects.
- [ ] Separate tests exist for services, repositories, transactions, or downstream protocols when those are the risk source.

**Remember:** `WebTestClient` expresses a full HTTP check as **request builder → `exchange()` → `expectStatus()` / `expectHeader()` / `expectBody()`**. With `@WebFluxTest`, you test the web contract fast without opening a server; with `@SpringBootTest(RANDOM_PORT)`, you test the application's actual HTTP transport. Pick the body assertion style matching the response shape, and claim only what the test environment truly proves.

### Official References

- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-controller/context/server, request building, status/headers/body assertions, JSON, typed responses.
- [Spring Framework — WebTestClient API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html): `exchange()`/`expectStatus()`/`expectHeader()`/`expectBody()` DSL.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@MockitoBean`, `@SpringBootTest(RANDOM_PORT)`, and auto-configured test clients.
- [Spring Boot 3.5 API — @WebFluxTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html): WebFlux test slice and `WebTestClient`.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): request mappings, content negotiation, response bodies.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, and testing reactive publishers.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): mock users, CSRF, and `WebTestClient` security configurers.
