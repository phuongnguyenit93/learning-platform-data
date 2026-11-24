# Reading or Adding Headers Without Consuming the Request Body in Spring Boot WebFlux

## 1. Objectives and Real-World Scenario

In an HTTP application, a filter often needs to read metadata such as X-Request-Id, Accept, Content-Type, or Authorization, or add a tracing header before the request reaches the controller. The issue is that **the request body should only be consumed by the component designed to process it**, such as the WebFlux HTTP message reader, the controller, or a dedicated body processor.

A common mistake is writing a filter to log requests by reading the body with subscribe()/block()/DataBufferUtils.join(), while still passing the original request to the controller. Because an HTTP connection body is normally a stream that is **not automatically replayable**, the downstream controller may receive an empty body, fail the request, or exhibit timing-dependent behavior. With Netty pooled buffers, improper retain/release also causes leaks and corruption.

The right solution for header-only needs is **not touching the body**:

- Read headers via exchange.getRequest().getHeaders().
- To alter headers seen by downstream handlers, use ServerHttpRequest.mutate() and ServerWebExchange.mutate().
- To add only response headers, write via response.getHeaders() before commit or register response.beforeCommit(...).
- Always return chain.filter(exchange) or chain.filter(mutatedExchange) as a Mono<Void>; never call subscribe() yourself.
- Never call getBody().subscribe(), collectList().block(), DataBuffer.read(), or DataBufferUtils.join() just to work with headers.

This lesson uses **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x, Reactor Netty, and Spring WebFlux**. Similar concepts exist in Spring MVC, but Servlet Filter/HandlerInterceptor and WebFlux WebFilter are different abstractions.

After this lesson, you will be able to write a WebFilter that reads/modifies request headers, adds response headers, preserves the JSON body intact, understands when body inspection is genuinely required, and tests behavior end-to-end.

## 2. What Does an HTTP Request Contain?

Example:

~~~http
POST /api/echo HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Request-Id: req_123
Content-Length: 30

{"message":"Hello from client"}
~~~

Three parts should be distinguished:

1. **Request line and URI**: method POST, path /api/echo, and query string if any.
2. **Headers**: metadata name/value pairs such as Content-Type, Accept, X-Request-Id.
3. **Body**: JSON, text, multipart, file bytes, or streaming data.

In WebFlux, ServerHttpRequest.getHeaders() provides HttpHeaders containing metadata already parsed by the HTTP server/parser. It **does not require subscribing** to the request body.

Meanwhile, getBody() returns Flux<DataBuffer>. This Flux represents the body data stream and typically reads from the source only when subscribed; reading/subscribing improperly can consume bytes before the framework decoder sees them.

### Do Not Confuse Obtaining a Publisher with Consuming a Publisher

~~~java
Flux<DataBuffer> publisher = exchange.getRequest().getBody();
~~~

The statement above only retrieves the Publisher. However:

~~~java
publisher.subscribe();
~~~

creates an independent subscription. For an HTTP request body, that is a design bug if your goal is only to read headers.

## 3. Where Does WebFilter Sit in WebFlux?

Diagram:

~~~mermaid
flowchart TD
    A["HTTP request / Reactor Netty"] --> B["HttpHandler"]
    B --> C["WebFilter chain"]
    C --> D["ServerWebExchange + ServerHttpRequest"]
    D --> E["DispatcherHandler"]
    E --> F["HandlerMapping / HandlerAdapter"]
    F --> G["HttpMessageReader reads request body"]
    G --> H["@RequestBody DTO or Mono DTO"]
    H --> I["Controller / Service"]
    I --> J["HttpMessageWriter / ServerHttpResponse"]
    J --> K["HTTP response"]
    C --> L["Read/modify request headers"]
    L --> D
~~~

Filters wrap the handler; a WebFilter can run logic **before** calling chain.filter(...) and observation logic **after** the Publisher completes or errors. Depending on its responsibility, a WebFilter can handle access logging, correlation IDs, security metadata, or adding response headers.

Interface:

~~~java
package org.springframework.web.server;

public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
~~~

This is the illustrative WebFilter signature; import Mono from Reactor accordingly.

**Never use javax.servlet.Filter, jakarta.servlet.Filter, or Spring MVC's HandlerInterceptor as a substitute for WebFilter in a reactive web application.** They belong to the Servlet stack, even though they share the names filter/interceptor.

## 4. Reading Headers Safely Without Touching the Body

A WebFilter that only inspects metadata can be written as:

~~~java
@Component
public final class HeaderObservationFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        HttpHeaders headers = exchange.getRequest().getHeaders();
        String contentType = String.valueOf(headers.getContentType());
        String requestId = headers.getFirst("X-Request-Id");

        // Observe needed metadata; do not log Authorization/Cookie.
        return chain.filter(exchange);
    }
}
~~~

The snippet above requires imports and includes illustrative contentType/requestId variables; no extra class is needed to forward the body. Most importantly, the filter **does not call getBody()**.

Commonly used APIs:

| API | Meaning |
| --- | --- |
| request.getHeaders() | Retrieve HttpHeaders |
| headers.getFirst("X-Request-Id") | Read the first value |
| headers.get("X-Request-Id") | Read the list of values |
| headers.getContentType() | Request body MediaType |
| headers.getAccept() | List of media types accepted by the client |
| request.getMethod() | HTTP method |
| request.getURI() | Request URI |
| request.getId() | ServerHttpRequest implementation-specific ID |

Reading a header is not the same as trusting its value. Clients can send arbitrary X-Request-Id, X-User, Forwarded, or custom headers. Never treat them as authoritative without trusted infrastructure verification.

## 5. Reading Headers Without Losing the JSON Body

Example controller:

~~~java
@PostMapping("/echo")
public Mono<EchoResponse> echo(@RequestBody Mono<EchoRequest> input) {
    return input.map(dto -> new EchoResponse(dto.message()));
}
~~~

If the filter only reads request.getHeaders(), WebFlux still lets the Jackson JSON decoder subscribe and decode the body normally.

Verification request:

~~~http
POST /echo HTTP/1.1
Content-Type: application/json
X-Request-Id: abc123

{"message":"Hello"}
~~~

and the controller receives `"Hello"` intact. There is no need to copy raw JSON or manually parse the body inside WebFilter.

### Content-Type and Body Are Not the Same Thing

getHeaders().getContentType() only reads metadata. It does not invoke the JSON parser. If Content-Type does not match an endpoint's `@PostMapping(consumes=application/json)`, the request may receive 415 before the controller decodes anything. That does not mean the filter lost the body.

Similarly, Content-Length is merely metadata about the declared/received length from the HTTP layer; never treat it as proof that the entire body is complete or intact.

## 6. Adding Request Headers for Downstream Handlers

In WebFlux, ServerHttpRequest is generally treated as an immutable request façade; never attempt to mutate a read-only HttpHeaders directly and expect the framework to accept it.

Use the builder:

~~~java
ServerHttpRequest modifiedRequest = exchange.getRequest()
        .mutate()
        .headers(headers ->
                headers.set("X-Request-Id", requestId))
        .build();

ServerWebExchange modifiedExchange = exchange.mutate()
        .request(modifiedRequest)
        .build();

return chain.filter(modifiedExchange);
~~~

This code belongs inside a method with exchange, chain, and requestId; full imports are shown in the complete example.

**Key takeaway**: The request builder creates a decorated request with the updated headers, while the body Publisher is inherited from the original request through standard mutation mechanics. No body reading, copying, joining, or subscribing occurs here.

### Why Choose headers(...).set(...)?

- set(name, value) sets a single header value, **replacing** any prior value.
- add(name, value) can create multi-valued headers; sometimes valid, but undesirable for a correlation ID that should have one value.
- For system metadata such as X-Request-Id, apply a single normalization/generation policy instead of accumulating duplicates from every filter.

Do not mutate sensitive headers like Host, Content-Length, Transfer-Encoding, or Authorization without understanding HTTP semantics, security trust, and proxy topology. This lesson illustrates only X-Request-Id.

## 7. Adding Response Headers: Before Writing and Before Commit

To send X-Request-Id to the client in the HTTP response, you can set it early:

~~~java
exchange.getResponse().getHeaders()
        .set("X-Request-Id", requestId);
return chain.filter(exchange);
~~~

When the filter runs before the controller/response commits, this is normally valid.

When you want to attach metadata right before the response commits, use beforeCommit:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);
    return Mono.empty();
});

return chain.filter(exchange);
~~~

beforeCommit is a hook **before** commit, not permission to alter status/headers **after** commit. Once the response has committed, headers already sent cannot be replaced with new values.

### Request Headers and Response Headers Are Different

- New request headers must be placed on the **ServerHttpRequest** seen downstream.
- Response headers must be placed on **ServerHttpResponse**.
- Adding X-Request-Id to the request does not automatically put it into the response.
- Adding X-Request-Id to the response does not make the controller see it via `@RequestHeader`.
- If you need both, set both in their proper scopes.

## 8. Why Is the Body Considered One-Shot?

For an HTTP request, the body arrives from a socket or transport pipeline. WebFlux represents it as `Flux<DataBuffer>`. Normally, the framework's controller body reader is the **primary consumer**, decoding JSON, multipart, or protobuf per media type into the target DTO or Publisher.

Never assume the original `Flux<DataBuffer>` is replayable or safely subscribable multiple times like `Flux.just(...)`. Although both are `Flux`, **an HTTP network source has its own lifecycle and resources**, often allowing only a single consumption.

Dangerous patterns:

~~~java
exchange.getRequest().getBody().subscribe(
        buffer -> log.debug("body chunk {}", buffer.readableByteCount())
);

return chain.filter(exchange);
~~~

The filter has created a separate subscriber. The downstream controller may receive no body, fail with an error, or hit a race; moreover, `DataBuffer` may use pooled memory requiring proper lifecycle management.

Another example:

~~~java
DataBuffer joined = DataBufferUtils.join(
        exchange.getRequest().getBody()).block();
~~~

This code **must not be used** in a WebFlux filter: `block()` can stall the event loop, `join` consumes the body, and pooled `DataBuffer` instances require proper release. This is not a safe way to "peek and restore the body."

## 9. Never Self-Subscribe and Never Block

In WebFlux, the framework subscribes to the Publisher representing HTTP request processing. A WebFilter must **return** the chain's `Mono<Void>`:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {
    return chain.filter(exchange);
}
~~~

Do not do this:

~~~java
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

With that anti-pattern, the framework loses proper coordination of completion, errors, and cancellation. This can terminate the response prematurely, prevent errors from reaching the client, and leak resources.

Even if a filter never touches the body, a `block()` call to query a database or make an external HTTP call on the event loop still causes latency and timeouts. If header normalization requires I/O, choose appropriate reactive operators/services and chain them inside the same reactive flow.

## 10. WebFilter, HandlerFilterFunction, and MVC HandlerInterceptor

| Tool | Web Stack | Primary Scope |
| --- | --- | --- |
| WebFilter | Spring WebFlux | Filter chain around WebHandler |
| HandlerFilterFunction | Spring WebFlux functional endpoints | Wraps functional HandlerFunction/RouterFunction |
| WebExceptionHandler | Spring WebFlux | Error handling in the WebHandler chain |
| jakarta.servlet.Filter | Servlet/Spring MVC | Servlet filter chain |
| OncePerRequestFilter | Servlet/Spring MVC | Filter supporting once-per-request dispatch semantics |
| HandlerInterceptor | Spring MVC | Around MVC handler execution |
| @RestControllerAdvice | Both MVC/WebFlux with different semantics | Exception handling for annotated controllers |

To add request/response headers for **WebFlux annotated controllers**, WebFilter is the standard choice. Never use a Servlet HandlerInterceptor expecting it to be invoked in a Netty WebFlux runtime.

In WebFlux functional routing, HandlerFilterFunction can also apply header logic to specific route groups:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok().bodyValue("hello"))
        .filter((request, next) -> next.handle(request));
~~~

This illustrative snippet requires appropriate imports and a class with a Bean method. It performs only a pass-through here; when server-wide HTTP request header updates are needed, WebFilter remains the clearer extension point.

## 11. Designing a Correlation ID Without Blindly Trusting Client Input

In our hands-on example, the policy is:

- Accept X-Request-Id if it has **exactly one value**, containing 1–64 ASCII alphanumeric, hyphen, or underscore characters.
- If missing, duplicated, or malformed, generate a new UUID.
- Put the normalized value into the request header so the controller can read it.
- Attach the same value to the response header via beforeCommit.
- Never use client-supplied headers for session identity, authentication, or authorization.
- Never log raw unvalidated values; prevent log injection and high-cardinality metrics.

Regex:

~~~text
[A-Za-z0-9_-]{1,64}
~~~

This is an application-level correlation ID rule, **not the W3C traceparent standard**. If you use Micrometer Tracing or OpenTelemetry, let instrumentation follow standard trace context instead of inventing custom replacements for traceparent/tracestate.

### Multiple Headers with the Same Name

HttpHeaders.getFirst returns only the first value. If a client sends two X-Request-Id header lines, a filter should enforce a clear policy rather than picking one arbitrarily. Example check:

~~~java
List<String> values = headers.get("X-Request-Id");

if (values == null || values.size() != 1) {
    // Generate a new correlation ID instead of accepting ambiguity.
}
~~~

This is a snippet, not a complete method. Note that proxies may coalesce header values under HTTP rules; our example validation rejects commas and any characters outside the allowlist.

## 12. Runnable Spring Boot 3.3 WebFlux Example

We will build a project where:

1. A WebFilter reads X-Request-Id, validates its format, and replaces or generates it.
2. The filter attaches the same X-Request-Id to the HTTP response before commit.
3. The filter **never calls getBody()**.
4. A `@RestController` receives the JSON body via `@RequestBody Mono<EchoRequest>` alongside the normalized `@RequestHeader`.
5. HTTP integration tests prove the body remains intact and request/response headers stay synchronized.
6. Tests verify missing or invalid headers.
7. Tests verify malformed JSON produces a decode error without any body-consuming logic in the filter.

### 12.1 Structure

~~~text
header-preserve-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/header/
    │   ├── HeaderDemoApplication.java
    │   ├── CorrelationHeaderFilter.java
    │   └── EchoController.java
    └── test/java/com/example/header/
        └── HeaderPreservationHttpTests.java
~~~

### 12.2 settings.gradle

~~~groovy
rootProject.name = 'header-preserve-demo'
~~~

### 12.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use only starter-webflux; if spring-boot-starter-web is also present, Spring Boot typically prefers Servlet MVC. Do not override Reactor Netty/Jackson versions outside Boot's dependency management.

### 12.4 HeaderDemoApplication.java

~~~java
package com.example.header;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderDemoApplication.class, args);
    }
}
~~~

### 12.5 CorrelationHeaderFilter.java

~~~java
package com.example.header;

import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public final class CorrelationHeaderFilter implements WebFilter {

    private static final String HEADER = "X-Request-Id";
    private static final Pattern VALID_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = chooseId(
                exchange.getRequest().getHeaders());

        ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers -> headers.set(HEADER, requestId))
                .build();

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .build();

        updated.getResponse().beforeCommit(() -> {
            updated.getResponse().getHeaders()
                    .set(HEADER, requestId);
            return Mono.empty();
        });

        return chain.filter(updated);
    }

    private static String chooseId(HttpHeaders headers) {
        List<String> values = headers.get(HEADER);

        if (values != null && values.size() == 1
                && values.get(0) != null
                && VALID_ID.matcher(values.get(0)).matches()) {
            return values.get(0);
        }

        return UUID.randomUUID().toString();
    }
}
~~~

**Step-by-step explanation:**

1. getHeaders reads metadata directly without consuming the body.
2. chooseId inspects the values list, avoiding picking an ambiguous value.
3. ServerHttpRequest.mutate().headers(...).build() creates a decorated request carrying the normalized header.
4. ServerWebExchange.mutate().request(request).build() produces an exchange so downstream sees the new request.
5. Response.beforeCommit attaches the header right as the response prepares to commit.
6. return chain.filter(updated) preserves the reactive lifecycle.
7. There is no getBody(), subscribe(), block(), DataBufferUtils.join, or raw payload copy in this filter.

Client-supplied headers are correlation metadata; UUID is used as a fallback, not as a session-security credential generator.

### 12.6 EchoController.java

~~~java
package com.example.header;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class EchoController {

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<EchoResponse>> echo(
            @RequestBody Mono<EchoRequest> input,
            @RequestHeader("X-Request-Id") String requestId) {

        return input.map(dto -> ResponseEntity.ok(
                new EchoResponse(
                        requestId,
                        dto.message(),
                        dto.message() == null
                                ? 0
                                : dto.message().length())));
    }

    @GetMapping(path = "/id", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<HeaderResponse> id(
            @RequestHeader("X-Request-Id") String requestId) {

        return Mono.just(new HeaderResponse(requestId));
    }
}

record EchoRequest(String message) {
}

record EchoResponse(String requestId, String message, int length) {
}

record HeaderResponse(String requestId) {
}
~~~

The same file contains one public class EchoController and package-private records. Jackson in Boot 3.3 supports Java 17 records.

- @RequestHeader reads **the header from the mutated request**.
- @RequestBody Mono<EchoRequest> lets the framework's HTTP codec decode JSON from the original body Publisher.
- EchoResponse returns the message and String length measured in Java UTF-16 code units; do not confuse this with UTF-8 byte count or grapheme clusters.
- If requestId is missing or invalid, the filter generates a new value before controller argument resolution.
- If message=null, the demo returns length=0; production APIs generally need explicit validation if message is required.
- The filter performs no authorization; never use requestId as a user ID.

## 13. Integration Tests with WebTestClient Over Real HTTP

File HeaderPreservationHttpTests.java:

~~~java
package com.example.header;

import java.util.Map;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HeaderPreservationHttpTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void validHeaderAndJsonBodyArePreserved() {
        client().post()
                .uri("/api/echo")
                .header("X-Request-Id", "req_123")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "  Hello  "))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Request-Id", "req_123")
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req_123")
                .jsonPath("$.message").isEqualTo("  Hello  ")
                .jsonPath("$.length").isEqualTo(9);
    }

    @Test
    void missingHeaderIsGeneratedButBodySurvives() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "payload"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.message").isEqualTo("payload")
                .jsonPath("$.length").isEqualTo(7)
                .jsonPath("$.requestId").isNotEmpty();
    }

    @Test
    void invalidHeaderIsReplaced() {
        client().post()
                .uri("/api/echo")
                .header("X-Request-Id", "bad id !")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "still intact"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().value("X-Request-Id", value -> {
                    assertThat(value).matches(
                            "[A-Za-z0-9_-]{1,64}");
                    assertThat(value).isNotEqualTo("bad id !");
                })
                .expectBody()
                .jsonPath("$.message").isEqualTo("still intact");
    }

    @Test
    void getWithoutBodyAlsoSeesNormalizedHeader() {
        client().get()
                .uri("/api/id")
                .header("X-Request-Id", "hello_42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("hello_42");
    }

    @Test
    void malformedJsonIsRejectedByCodecNotFilter() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"message\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader().exists("X-Request-Id");
    }

    @Test
    void unsupportedContentTypeDoesNotBecomeBodyLoss() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not JSON")
                .exchange()
                .expectStatus().isUnsupportedMediaType();
    }
}
~~~

The test file has two imports (Pattern and AssertJ) of which only one is used; unused imports can be removed without affecting compilation. The Java compiler does not treat valid unused imports as errors by default. The tests deliberately avoid asserting on full JSON string equality because JSON field order is not part of the contract.

RANDOM_PORT tests use a real embedded HTTP server, going through WebFilter, the Jackson decoder, the controller, and the response writer. That provides much stronger verification than simply calling `new CorrelationHeaderFilter().filter(...)` in a unit test.

The results shown in the code are **expected from the design**, not evidence that Gradle was executed in the current workspace.

## 14. Running the Project and Testing with cURL

### 14.1 Build and Test

Inside the header-preserve-demo directory:

~~~bash
gradle clean test
~~~

If the project has a Gradle wrapper:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

### 14.2 Start

~~~bash
gradle bootRun
~~~

Under default configuration, the server uses port 8080 unless already occupied or overridden.

### 14.3 Request with a Valid Header

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: req_123' \
  -d '{"message":"Hello from client"}'
~~~

Expect HTTP 200; response header X-Request-Id: req_123; JSON body equivalent to:

~~~json
{
  "requestId": "req_123",
  "message": "Hello from client",
  "length": 17
}
~~~

The Java String length of `"Hello from client"` is 17 UTF-16 characters; the JSON response may reorder fields without changing semantics.

### 14.4 Request Without the Header

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -d '{"message":"payload"}'
~~~

Expect HTTP 200, with a UUID-generated X-Request-Id in the response header and body. Message `"payload"` remains intact, length=7. Because the specific UUID varies per run, never assert a hardcoded UUID value.

### 14.5 Request with an Invalid Header

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: bad id !' \
  -d '{"message":"still intact"}'
~~~

The filter rejects the header containing spaces and `!`, replacing it with a fresh UUID. Both the downstream request header and response header use the normalized value.

### 14.6 Malformed JSON

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -d '{"message":'
~~~

HTTP 400 is the normal result because the JSON parser cannot decode the body. Do not blame the header-only WebFilter; inspect the codec exception and request syntax.

## 15. What If a Filter Actually Needs to Read the Body?

When only headers are needed, **not reading the body** is the best design. However, some use cases genuinely require the body, such as HMAC signature verification, policy-mandated payload auditing, security scanning, or custom protocol parsing.

This is a different problem that must be solved deliberately because `Flux<DataBuffer>` from an HTTP request is not replayable by default.

Possible approaches:

1. Move processing into the controller/request DTO or service if sufficient.
2. Use a schema-aware HTTP message reader/decoder if the goal is payload validation.
3. Use standard security/framework APIs instead of hand-parsing Authorization + body.
4. If raw body auditing/verification before the controller is mandatory, build a `ServerHttpRequestDecorator` providing **body replay** while respecting pooled `DataBuffer` semantics, bounded memory, and cancellation.
5. If you only need to **observe the byte count passing through** without reading raw content, decorate `getBody()` and attach `doOnNext` to the same Publisher subscribed to by downstream, without creating a second subscriber.

**Never** call `DataBufferUtils.join(...)` and then invoke `chain.filter(exchange)` with the original request: the body has already been consumed and is no longer available downstream.

## 16. Observing Byte Count Without Separately Consuming the Body

In advanced cases where you want to count the size of DataBuffers requested downstream, you can wrap the request Publisher with a decorator:

~~~java
AtomicLong bytesSeen = new AtomicLong();

ServerHttpRequest counted =
        new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public Flux<DataBuffer> getBody() {
                return super.getBody()
                        .doOnNext(buffer ->
                                bytesSeen.addAndGet(
                                        buffer.readableByteCount()));
            }
        };

ServerWebExchange updated =
        exchange.mutate().request(counted).build();

return chain.filter(updated)
        .doFinally(signal -> log.debug(
                "Observed request bytes={}, signal={}",
                bytesSeen.get(),
                signal));
~~~

This snippet belongs inside a WebFilter with imports for AtomicLong, ServerHttpRequestDecorator, DataBuffer, Flux, and log.

Why does this example not lose the body?

- The decorator **returns the same Flux<DataBuffer> downstream** after doOnNext.
- It does not subscribe independently.
- It only calls readableByteCount(), never calling buffer.read(...) to advance the read position.
- It does not release the DataBuffer prematurely.
- The decoder remains the subscriber of the returned Publisher.

Limitations:

- Observed bytes do not necessarily equal wire bytes due to HTTP framing, content encoding, and implementation details.
- If downstream does not read the body, the counter stays 0.
- If downstream subscribes multiple times or the pipeline alters subscriptions, the counter may double-count.
- The chain's doFinally does not prove the client received the HTTP response.
- Do not use this pattern to copy/log sensitive payloads without policy approval.
- Do not create a decorator just to read headers; header-only cases are solved much more simply via getHeaders()/mutate().

## 17. Body Caching/Replay: When Needed and Mandatory Requirements

For an HMAC signature over a raw request body, a solution may have to read bytes once and then replay them to the decoder. Doing this safely requires several conditions:

### 17.1 Bound Memory Before Aggregating

DataBufferUtils.join(body, maxByteCount) in Spring Framework 6.x can be used for **finite, bounded bodies**. When a body exceeds the limit, fail clearly rather than buffering unboundedly on the heap. Large uploads/multipart bodies may be unsuitable for buffering.

### 17.2 Ownership and Releasing Pooled DataBuffers

Reactor Netty may use pooled buffers. When joining/copying/transforming DataBuffers, manage retain/release properly and never hold references to released buffers. Test cancellation, decode failures, empty requests, and large payloads.

### 17.3 Replay Must Re-Emit Exact Bytes

After inspecting the body, downstream must receive **a fresh Publisher containing the full intact bytes** with proper lifecycle semantics. Do not merely stash a rawBody attribute and continue the chain because `@RequestBody` still reads the request's Publisher. Never subscribe directly to the request source inside a filter without replaying.

### 17.4 Never Cache Bodies on Every Request

- Memory, latency, and CPU costs increase.
- Streaming/multipart uploads lose non-blocking benefits.
- JSON containing sensitive data can linger in RAM or logs.
- Request bodies can be huge, infinite, or aborted mid-stream by the client.
- Codecs must preserve Content-Type, charset, and transfer semantics.
- For HMAC, exact canonicalization, content encoding, signing scope, and verification timing must be defined.

A custom ServerHttpRequestDecorator for body replay must be tested via HTTP integration tests, large bodies, early cancellation, concurrent requests, and memory-leak diagnostics. This lesson **intentionally omits a pseudo-safe body cache**: when the job is only reading/adding headers, none of those steps are needed.

## 18. Common Bug Pattern: Logging the Body and Leaving the Controller Empty

Incorrect pattern:

~~~java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    exchange.getRequest().getBody().subscribe(buffer -> {
        // Subscribed to the request body outside the main pipeline.
        log.debug("bytes={}", buffer.readableByteCount());
    });

    return chain.filter(exchange);
}
~~~

Because two subscriptions compete for the same body source, the controller may fail or receive an incomplete/missing body. You cannot fix this simply by slapping `cache()` on it: cached buffers can be released, retained unboundedly, or lose ownership. Do not assume `Flux.cache()` makes a pooled-memory HTTP request safely replayable.

Fix when only metadata is required:

~~~java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String contentType =
            String.valueOf(exchange.getRequest()
                    .getHeaders()
                    .getContentType());

    return chain.filter(exchange);
}
~~~

The body will now be read normally downstream in the right place.

## 19. Rules for Content-Length, Transfer-Encoding, and Content-Type

Header manipulation can still break requests without touching the body if you alter content-descriptive headers:

- **Content-Length** must match actual body bytes; never set an arbitrary number.
- **Transfer-Encoding** belongs to transport/framing; do not set it arbitrarily in application filters.
- **Content-Type** controls whether the HTTP codec can decode the payload; never rewrite application/json to text/plain just to "work around" another error.
- **Content-Encoding** indicates compression/encoding; if the body is decompressed/recompressed, metadata must stay consistent.
- **Host** carries authority/routing/security meaning; never overwrite it from untrusted client headers.
- **Authorization/Cookie** are sensitive credentials; never log them or reflect them into responses.
- **Forwarded/X-Forwarded-*** are trustworthy only when the proxy chain is properly configured.

X-Request-Id is narrower metadata, yet still requires validation and length limits.

## 20. Header Security and Reverse Proxies

Several security scenarios:

### 20.1 Clients Can Spoof X-User and X-Role

Reading X-User or X-Role does not prove who is logged in. If a gateway authenticates and injects internal headers, the gateway must strip client-supplied versions of those headers before inserting trusted values. Backend apps must restrict direct backend access, define trust boundaries, and authenticate the gateway/backend relationship.

### 20.2 X-Forwarded-For May Be Untrustworthy

Clients can send forged X-Forwarded-For headers. Never take `getFirst("X-Forwarded-For")` and treat it as guaranteed client IP. In Boot, configure a forwarded-headers strategy matching your topology and trust only managed reverse proxies.

### 20.3 Correlation IDs Can Be a Log-Injection Vector

Never log unbounded client-supplied strings verbatim. The simple character allowlist and 64-char cap in the filter mitigate newline/control-character injection. Never attach raw requestIds to high-cardinality metric labels.

### 20.4 Response Headers and CORS

Whether browser JavaScript can read custom response headers depends on **Access-Control-Expose-Headers** under CORS. Returning X-Request-Id from the server does not guarantee cross-origin JavaScript can read it unless CORS exposes it. Never pair `Access-Control-Allow-Origin: *` with an invalid credentials policy. Use proper CORS configuration in Spring Security or WebFlux config.

## 21. Filter Order and Application Scope

WebFilters can be ordered using @Order or Ordered. Spring Security and tracing also register WebFilters with their own orders, and your behavior may depend on execution order.

In the sample project:

~~~java
@Component
@Order(0)
public final class CorrelationHeaderFilter implements WebFilter {
    // ...
}
~~~

If a later filter needs to see the normalized request header, the normalizing filter must sit **before** it in the chain. Never guess ordering solely from one filter's annotation; verify the Spring application context, security chain, and integration tests in the real app.

Notes:

- Never modify Authorization arbitrarily to spoof security context.
- Header normalization for tracing should coordinate with Micrometer Tracing/OpenTelemetry.
- Filter registration here applies only to WebFlux apps; OncePerRequestFilter is for MVC.
- A WebFilter wraps both DispatcherHandler endpoints and functional routes sharing the same WebHandler chain.
- When targeting only specific routes, use route filters/HandlerFilterFunction or intentional path checks rather than ad-hoc regex matching.

## 22. Diagnosing When the Controller Cannot Read the Body

### Step 1: Identify the Stack

Is the app running Servlet MVC or reactive WebFlux? If both starter-web and starter-webflux are present, Boot usually favors MVC; your WebFilter might not even be in the active runtime stack.

### Step 2: Check Whether Any Filter Subscribes to getBody()

Search the codebase for patterns like:

~~~text
getBody().subscribe(...)
getBody().blockFirst()
getBody().collectList().block()
DataBufferUtils.join(request.getBody())
buffer.read(...)
DataBufferUtils.release(buffer)
~~~

Some of these APIs are valid in **proper ownership contexts**, but if they appear in a header-only WebFilter, investigate immediately.

### Step 3: Check Whether Body Decoration Was Done Correctly

If a filter genuinely reads and caches the body, does downstream receive a ServerHttpRequestDecorator with a properly implemented getBody()? Are memory limits, releases, and cancellation handling in place?

### Step 4: Distinguish HTTP Codec Errors

HTTP 400 from malformed JSON, 415 from wrong Content-Type, 413/size limits, 401/403 from security, 404 unmatched route, and 500 server errors each have distinct causes. Do not conclude the body was lost solely from a status code.

### Step 5: Inspect Content-Length / Content-Encoding

A filter or proxy making inconsistent metadata edits can cause the codec to fail decoding even when the raw body is present. Inspect the actual request before and after the gateway.

### Step 6: Test Over Real HTTP

Send JSON containing a distinctive string and assert the echoed response preserves it. Test valid, missing, and invalid headers, moderately large bodies, Unicode, and malformed JSON; test multipart uploads separately.

### Step 7: Use Controlled Logging

Do not enable Netty wiretap broadly in production when payloads carry tokens/PII. Enable targeted debug logging for handler mapping and codecs without dumping full bodies.

## 23. Spring MVC / Servlet Equivalent

If the system uses spring-boot-starter-web and DispatcherServlet, the common filter is OncePerRequestFilter:

~~~java
@Component
public class RequestIdServletFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String id = request.getHeader("X-Request-Id");
        response.setHeader(
                "X-Request-Id",
                id == null ? "server-generated" : id);

        filterChain.doFilter(request, response);
    }
}
~~~

This snippet needs imports: org.springframework.stereotype.Component, org.springframework.web.filter.OncePerRequestFilter, jakarta.servlet.FilterChain, jakarta.servlet.ServletException, jakarta.servlet.http.HttpServletRequest/HttpServletResponse, and java.io.IOException.

In Servlets, `request.getHeader` does not read `ServletInputStream`. However, if you want to **add a request header** so downstream `getHeader` sees a new value, the raw `HttpServletRequest` has no standard `setHeader`; you need a proper `HttpServletRequestWrapper`. Calling `response.setHeader` does not modify `request.getHeader`.

**ContentCachingRequestWrapper** caches data as the body is read, but does not by default make `getInputStream()` re-readable from the start multiple times. If you truly need input stream replay, implement a wrapper following the full contract. Do not port Servlet body wrappers directly to WebFlux; the two stacks have different resource, cancellation, and async semantics.

## 24. Testing Edge Cases

Beyond the main test cases, a production system should verify:

| Case | What to Verify |
| --- | --- |
| Missing X-Request-Id | Server generates a valid ID and returns it |
| Duplicate headers of the same name | Policy rejects or resolves deterministically |
| Very long X-Request-Id | Rejected/replaced with new ID, not leaked into logs |
| Header containing control characters | HTTP server may reject before filter; never log raw |
| JSON with Unicode | Body/charset remains unaltered |
| Nested JSON and arrays | Jackson still parses normally |
| Empty body with required @RequestBody | Clear error contract, not caused by filter consumption |
| Multipart/file upload | Streaming works without unbounded buffering |
| SSE response | Headers attached before commit without disrupting output stream |
| Client disconnect mid-upload | No leaked subscriptions or buffers |
| Cross-origin CORS | Browser allowed to read custom response header if needed |
| Spring Security | Header never treated as unverified authority |
| Reverse proxy | Forwarded headers and correlation policy align |
| Concurrent requests | requestId never held in a mutable singleton field |
| Content-Encoding/compression | Body metadata never modified inconsistently |

Specifically, a filter is an application-wide singleton bean, so **never** store requestId in a shared mutable field. Keep it in a per-request local variable, exchange attributes, or Reactor Context when purposeful.

## 25. Common Design Mistakes and How to Fix Them

**Mistake 1 — getBody().subscribe() to log:** creates a second subscriber so the controller may get no body. Fix: call only getHeaders() when only metadata is needed.

**Mistake 2 — block() inside a WebFilter:** blocks the event loop and consumes the body if blocking on the body Publisher. Fix: return the reactive chain and avoid synchronous I/O.

**Mistake 3 — join the body and pass the original request:** downstream `@RequestBody` has no bytes left to decode. Fix: only use a bounded replay decorator with explicit lifecycle if truly necessary.

**Mistake 4 — manually releasing a pooled DataBuffer:** downstream can read an already-released buffer. Fix: respect ownership semantics; do not release buffers you merely pass through.

**Mistake 5 — buffer.read(...) to "peek" bytes:** `read` advances the read position, starving downstream of data. Fix: avoid reading, or use a proper API that preserves position and avoids retaining buffers past lifecycle.

**Mistake 6 — mutating HttpHeaders directly on a read-only request:** throws UnsupportedOperationException or has no effect. Fix: ServerHttpRequest.mutate().headers(...), then chain.filter(mutatedExchange).

**Mistake 7 — adding a header to the response expecting the controller to read it:** request and response are separate directions. Fix: mutate the request for handlers, use beforeCommit for clients.

**Mistake 8 — modifying response headers after commit:** status/headers are already on the wire; changing Java maps does not update the wire response. Fix: set early or in beforeCommit.

**Mistake 9 — appending duplicate X-Request-Id values:** creates ambiguity and proxy discrepancies. Fix: enforce a single-value policy with headers.set.

**Mistake 10 — trusting client-supplied X-User/X-Forwarded-For:** enables authorization spoofing. Fix: define trusted gateways/proxies and security context.

**Mistake 11 — calling chain.filter(...).subscribe and returning Mono.empty:** framework loses lifecycle and error propagation. Fix: return chain.filter(...).

**Mistake 12 — testing by calling controller methods directly:** bypasses filters and Jackson decoding. Fix: WebTestClient over HTTP on RANDOM_PORT.

**Mistake 13 — assuming malformed JSON means a lost body:** the request parser itself fails on bad syntax. Fix: inspect Content-Type, status, and codec exception.

**Mistake 14 — caching every upload:** spikes memory and latency, leaks easily, and breaks streaming. Fix: cache only bounded payloads when strictly needed; keep multipart/large streams separate.

**Mistake 15 — treating X-Request-Id as authentication:** correlation IDs do not prove identity. Fix: use Spring Security with dedicated authn/authz.

## 26. Implementation Checklist

- [ ] Confirm the server is actually running WebFlux.
- [ ] Use WebFilter instead of Servlet Filter/HandlerInterceptor on the reactive stack.
- [ ] Header-only filters call getHeaders() only and never consume getBody().
- [ ] Update request headers via ServerHttpRequest.mutate if downstream needs to read them.
- [ ] Use ServerWebExchange.mutate().request(...) to pass the updated request.
- [ ] Use headers.set for single-value metadata with a clear policy.
- [ ] Register response.beforeCommit before the chain when adding response headers.
- [ ] Return chain.filter(...), never self-subscribe or block.
- [ ] Client headers are validated, length-bounded, and never used for auth.
- [ ] Never alter Content-Length, Host, or Transfer-Encoding arbitrarily.
- [ ] Never hold per-request data in singleton mutable fields.
- [ ] Never log Authorization, Cookie, or raw bodies indiscriminately.
- [ ] If body access is mandatory, enforce bounded caching/replay and proper DataBuffer ownership.
- [ ] Test JSON body preservation via real HTTP WebTestClient.
- [ ] Test missing, invalid, and duplicate request headers.
- [ ] Test multipart/streaming/cancellation if supported by the app.
- [ ] Ensure CORS exposes custom response headers if browsers must read them.
- [ ] Verify Spring Security/tracing filters cooperate in the intended order.

## 27. Summary

In Spring Boot WebFlux, **reading headers and consuming the body are independent operations**. A WebFilter can read `request.getHeaders()`, normalize a header with `ServerHttpRequest.mutate()`, attach the updated request via `ServerWebExchange.mutate()`, and add a response header in `beforeCommit` **without ever subscribing to `request.getBody()`**. WebFlux's HTTP message reader then receives and decodes the body normally.

The body is a `Flux<DataBuffer>` tied to the network lifecycle, not a default-replayable byte array. Subscribing, blocking, joining, or reading/releasing DataBuffers prematurely can starve controllers of the body, break decoding, or leak resources. Only implement body caching/replay when business requirements strictly demand it, with memory bounds, pooled-buffer management, and error/cancellation testing.

The `CorrelationHeaderFilter` and `EchoController` example illustrates the right extension point: **headers are read and updated while the JSON body stays intact**, request and response share the same `X-Request-Id`, and `WebTestClient` verifies it over real HTTP.

## 28. References

- Spring Framework — WebFlux Web Filters: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Spring Framework — WebFlux Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework 6.1 — WebFilter API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilter.html
- Spring Framework 6.1 — ServerHttpRequest API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html
- Spring Framework 6.1 — ServerHttpRequestDecorator API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequestDecorator.html
- Spring Framework 6.1 — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.1 — ServerHttpResponse API / beforeCommit: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Security — Reactive Web Applications: https://docs.spring.io/spring-security/reference/reactive/index.html
- Reactor Core — Reference Guide: https://projectreactor.io/docs/core/release/reference/
- HTTP Semantics — RFC 9110: https://www.rfc-editor.org/rfc/rfc9110