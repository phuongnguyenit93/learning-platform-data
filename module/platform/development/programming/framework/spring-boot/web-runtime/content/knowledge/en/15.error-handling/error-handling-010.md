# Errors After Response Commit or Once Streaming Has Started in Spring Boot WebFlux

## 1. The Problem: Why Does the Server Report an Error While the Client Still Sees HTTP 200?

An HTTP response may already be partially sent before an error happens. For example, a Spring WebFlux endpoint streaming Server-Sent Events (SSE) sends HTTP 200, `Content-Type: text/event-stream`, and two data events, and only then does the data source emit an error. Once the status and headers have committed, the server cannot retract the earlier response and replace it with an HTTP 500 carrying ordinary error JSON.

This is a critical distinction between errors occurring before an HTTP response commits and errors occurring while a body is actively streaming.

Core principles:

- Commit is the point at which status and headers are finalized for the response. After this point, changing the status on the same response is no longer possible.
- Writing the body normally triggers commit; however, a response can also commit without a body, such as via `setComplete`.
- Pre-commit errors can be mapped to HTTP 4xx/5xx by appropriate exception handling.
- Post-commit errors can result in a partial body, stream reset, connection close, or an in-band error event inside the body if the application protocol defines how to represent it.
- HTTP 200 does not necessarily mean the entire stream succeeded. Clients must verify whether they received complete data.
- Not every exception can be fixed with `@RestControllerAdvice`; error-handling callbacks cannot unsend HTTP bytes already written to the wire.

This lesson targets Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+ with Spring WebFlux on Reactor Netty. Alongside theory, it includes a complete Gradle project, SSE examples failing before and after commit, and tests using `WebTestClient`, `StepVerifier`, and `MockServerHttpResponse`.

## 2. Distinguishing Initialization, Commit, Streaming, and Completion

A request may pass through:

~~~text
HTTP request
  -> find handler
  -> compute result or build Mono/Flux
  -> configure HTTP status + headers
  -> commit response
  -> encode / write / flush body
  -> complete or error / cancel
~~~

This is a conceptual sequence, not a strict call stack. Publishers can run asynchronously; encoders, HTTP servers, proxies, and clients each have their own buffering.

| State | Change Status/Headers? | Error-Handling Outcome |
| --- | --- | --- |
| Uncommitted, no data written | Usually still possible | Opportunity to return 400/404/500 and JSON/ProblemDetail |
| Inside `beforeCommit` callback | Can adjust per callback contract | Depends on pipeline and callback completion |
| Headers committed, body not yet written | Cannot change status on the wire | Cannot emit a different status on the same response |
| Writing SSE/NDJSON/binary | Cannot change status | In-band error if format allows; otherwise terminate stream |
| Mid-body write, I/O error | No | Partial content, reset/close, or client-side error |
| Response already completed | No | Cannot write any further error response |

Spring's response commit differs from the client having actually received the bytes. A proxy can buffer and deliver later; a client can lose connectivity right as the server finishes writing. Distinguish Spring state, transport state, and client-side confirmation.

### HTTP/1.1 Example

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Transfer-Encoding: chunked

event: item
data: one

event: item
data: two

~~~

If the data source fails next, you cannot append a second HTTP response:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{"error":"upstream failed"}
~~~

into the middle of the existing body. That is not a valid way to replace an already-sent status.

HTTP/2 uses HEADERS/DATA frames and stream resets instead of HTTP/1.1 wire text, yet the principle stays the same: once response headers are sent, you cannot go back and change the status into a different response.

## 3. What Does ServerHttpResponse.isCommitted() Mean?

In WebFlux:

~~~java
boolean committed = exchange.getResponse().isCommitted();
~~~

`org.springframework.http.server.reactive.ServerHttpResponse` reports whether the response has committed according to framework state. Use this API to observe and classify errors, not as a rollback mechanism.

Common status-setting API:

~~~java
ServerHttpResponse response = exchange.getResponse();

if (!response.isCommitted()) {
    boolean accepted =
            response.setStatusCode(HttpStatus.BAD_GATEWAY);
    // With concurrency, still check the accepted result.
}
~~~

This is a snippet inside a class with `ServerWebExchange` and imports. `setStatusCode(HttpStatusCode)` returns a boolean and does not guarantee the change took effect if the response already committed or is committing concurrently.

Never call `getHeaders().set(...)` and assume the client will see the new header after commit. HTTP headers that have already left the application cannot be changed by mutating a Java map.

### A Common Pitfall

An upstream error may surface inside `doOnError` when `isCommitted()` is `true`. That does not mean the error handler ran late due to a Spring bug; it simply means earlier items were already streamed and the status was already sent.

## 4. beforeCommit(): An Extension Hook at the Right Moment

Spring WebFlux supports:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Response-Phase", "committing");
    return Mono.empty();
});
~~~

This snippet must live inside a method with `exchange` and Reactor `Mono`. `beforeCommit` registers a callback executed right before the response commits.

It is useful when you want to:

- Attach response metadata known prior to commit.
- Apply common headers per application policy.
- Record an observation marker on the response for testing/debugging.
- Run brief, non-blocking logic immediately before commit.

It does not help you:

- Retract a status or body already sent.
- Change status from 200 to 500 after the first SSE event.
- Rewrite a JSON body already serialized and flushed.
- Wait on a database with `Thread.sleep` or `.block()`.
- Prove the client received the data.

If the `beforeCommit` callback fails itself, committing the response can fail. Keep callbacks small, non-blocking, and separately tested for non-trivial logic.

## 5. Error-Handling Flow at the WebFlux Layer

~~~mermaid
flowchart TD
    A["Reactor Netty / HTTP request"] --> B["HttpHandler, WebFilter chain"]
    B --> C["DispatcherHandler"]
    C --> D["Controller returns Mono/Flux"]
    D --> E["HandlerResultHandler / HttpMessageWriter"]
    E --> F{"Committed?"}
    F -->|"No"| G["Exception handler can set error status/body"]
    F -->|"Yes"| H["Status/headers cannot be changed"]
    H --> I{"In-band body error format?"}
    I -->|"Yes"| J["SSE error event or NDJSON error envelope"]
    I -->|"No"| K["Error signal / reset / close stream"]
~~~

In real applications, errors can arise before mapping, during body decoding, in filters, in controllers, during response serialization, in upstream services, or at transport. Error handling may involve `@ExceptionHandler`, `WebExceptionHandler`, Boot's reactive error handler, or Reactor Netty.

The common thread: an error handler can create a new status and body only while the response has not reached a state preventing it.

### Role of Each Component

| Component | Role |
| --- | --- |
| DispatcherHandler | Coordinates WebFlux request processing |
| RequestMappingHandlerAdapter | Invokes controller methods and creates `HandlerResult` |
| HandlerResultHandler | Chooses how to handle the return value |
| HttpMessageWriter/Encoder | Writes response body from Java objects |
| ServerHttpResponse | Status, headers, cookies, body publisher, commit |
| WebFilter | Reactive middleware, can log errors/cancellation |
| @RestControllerAdvice | Handles certain errors tied to annotated controllers |
| WebExceptionHandler | Handles error signals in the `WebHandler` chain |
| Boot reactive error handler | Boot's default error handling when still possible |
| Reactor Netty | Writes bytes and manages transport/channels |

An error already converted into a valid item by `onErrorResume` **is no longer a reactive `onError`** downstream of that operator. Place metrics/observation hooks before recovery if you want to count upstream errors.

## 6. Pre-Commit Errors: Mapping HTTP Status Is Still Possible

Example of a controller creating a response only after confirming a report exists:

~~~java
@GetMapping("/reports/{id}")
public Mono<ResponseEntity<ReportDto>> find(
        @PathVariable("id") String id) {

    return reportService.findById(id)
            .switchIfEmpty(Mono.error(
                    new ReportNotFoundException(id)))
            .map(ResponseEntity::ok);
}
~~~

This is an illustrative method requiring `reportService`, `ReportDto`, and the exception class. When `Mono.empty` or an error occurs before body writing starts, a matching `@ExceptionHandler` can return 404 with valid JSON.

Steps to perform before streaming:

1. Validate inputs, `Content-Type`, and parameters.
2. Perform authentication and authorization.
3. Verify the file/resource exists.
4. Verify required upstreams are reachable.
5. Determine status, content type, caching, and `Content-Disposition`.
6. Choose the stream format and failure behavior if the source breaks mid-stream.

### Limitation

A `Mono<ResponseEntity<Flux<Item>>>` allows deciding metadata **before writing the `Flux` body**, yet does not prove items inside the `Flux` won't fail. Once the `Flux` emits data, the `ResponseEntity`'s status can no longer change.

## 7. Post-Commit Errors: @ExceptionHandler Cannot Fix Them Like Pre-Commit Errors

Example source stream:

~~~java
Flux<String> source = Flux.concat(
        Flux.just("one", "two"),
        Flux.error(new IllegalStateException("upstream unavailable")));
~~~

This is a valid Reactor Publisher with `Flux` imported; it does not create an HTTP response by itself. When turned into a `text/event-stream` response, the first items can be encoded and flushed before the final error appears.

If the response already committed HTTP 200, a later handler cannot turn it into 500 JSON like an unwritten request:

~~~java
@ExceptionHandler(IllegalStateException.class)
public ResponseEntity<String> failed(
        IllegalStateException exception) {
    return ResponseEntity.status(500).body("failed");
}
~~~

This snippet works only when the error is handled at an eligible time and scope. In an already-committed streaming response, the framework cannot send a new status.

This holds whether the error stems from a database, a custom JSON serializer, an upstream `WebClient`, or a client disconnect.

## 8. Should WebExceptionHandler Try to Modify a Committed Response?

`org.springframework.web.server.WebExceptionHandler` has the API:

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

An advanced custom handler must check:

~~~java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(ex);
}

// Only when uncommitted can you consider
// setting an appropriate error status and body.
~~~

This snippet illustrates one branch inside `handle`, not a full implementation.

Propagating the error when the response is already committed is generally better than trying to write a second HTTP response. How the connection/stream ends next depends on the server and transport, with no guarantee the client sees HTTP 500.

Do not add a global `WebExceptionHandler` just to “catch everything”. Understand `@Order`, Boot's default error handler, security filters, and response commitment before customizing.

## 9. Three Strategies After Detecting a Streaming Error

### Strategy A: Validate or Materialize Results Before Commit

For small, bounded results:

~~~java
public Mono<List<ItemDto>> items() {
    return itemService.loadAll()
            .collectList();
}
~~~

If the source Publisher errors before `collectList` finishes, the controller has not begun writing a success list, so returning an HTTP error remains possible. However, `collectList` consumes memory, increases latency, sacrifices streaming, cannot work with infinite streams, and does not guarantee later serialization won't fail.

If an atomic representation is required, you may need to generate/validate/serialize content in a bounded memory buffer or temp file before starting the response. Design size limits, timeouts, checksums, and backpressure accordingly.

### Strategy B: In-Band Errors Inside the Application Protocol

SSE and NDJSON can define error events or error records, for example:

~~~text
event: item
data: one

event: item
data: two

event: stream-error
data: UPSTREAM_UNAVAILABLE

~~~

The HTTP response may remain 200, yet the `stream-error` event signals a **stream-level business error**. Clients must understand this contract and never mark the transfer successful solely because the initial HTTP response was accepted.

With NDJSON, each line is an independent JSON document:

~~~json
{"type":"item","id":"1","value":"one"}
{"type":"item","id":"2","value":"two"}
{"type":"error","code":"UPSTREAM_UNAVAILABLE"}
~~~

These are three separate JSON values on three lines, not a single `application/json` array/object document. If clients need to know the stream completed fully, require a `type=complete` line or a `complete` event.

### Strategy C: Propagate Error and Terminate the Stream

When a binary download has already written partial bytes, the network dropped, or the format lacks error envelopes:

- Let the reactive error signal propagate.
- Log and emit metrics for the error and commit state.
- Let transport close/reset the connection as supported by the server.
- Have the client treat output as partial/incomplete.
- For critical files, only consume the file after verifying length/checksum.
- Design retry/resume with checkpoints or `Range`/`ETag` where appropriate.

Never inject error JSON into the middle of a PNG, ZIP, PDF, or binary format that defines no error syntax.

## 10. Server-Sent Events: Designing Clear Success and Failure Signals

Spring WebFlux provides `org.springframework.http.codec.ServerSentEvent<T>`. An SSE response uses `text/event-stream` and can emit multiple events:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.just(
            ServerSentEvent.<String>builder()
                    .event("item").id("1").data("one").build(),
            ServerSentEvent.<String>builder()
                    .event("complete").id("2").data("done").build());
}
~~~

This is a controller method snippet, not a standalone class.

Define an explicit contract:

| Event | Meaning |
| --- | --- |
| `item` | A valid data item |
| `complete` | Business result fully emitted |
| `stream-error` | Stream failed after starting |
| Neither `complete` nor `stream-error` due to drop | Outcome unknown; resume/retry per policy |

SSE event IDs can support checkpoint/resume when the server implements `Last-Event-ID` handling and retention. Having an `id` field alone does not automatically create safe replay or resume.

### HTTP 200 Does Not Mean Success

If two items are sent followed by `stream-error`, the initial HTTP status is still 200. Clients must track terminal events to distinguish partial failure from completion; HTTP 200 metrics alone are insufficient to measure business success.

### Do Not Write Raw JSON Error Bytes After SSE Events

To signal failure, emit a valid SSE event such as `event: stream-error` and `data: error-code`. Never write an HTTP JSON error body directly into the SSE stream after other events have been sent.

## 11. Reactor Error Operators Require Careful Use

Given a `Flux`:

~~~java
Flux<String> data = Flux.concat(
        Flux.just("one", "two"),
        Flux.error(new IllegalStateException("upstream unavailable")));
~~~

Operators have distinct behaviors:

| Operator | Behavior | Risk |
| --- | --- | --- |
| `doOnError` | Observes/logs `onError` without recovering | Mistakenly believing the error is handled |
| `onErrorResume` | Switches error to another Publisher | Must preserve the stream's schema |
| `onErrorMap` | Replaces exception while keeping error signal | Cannot change HTTP status after commit |
| `onErrorComplete` | Converts error into completion | Easily hides truncated/incomplete data |
| `retry` | Re-subscribes to source | Can re-emit already-sent items, causing duplicates |
| `doFinally` | Observes `COMPLETE`/`ERROR`/`CANCEL` | Does not prove the client received everything |
| `concatWith` | Emits Publishers sequentially | If the latter errors, earlier items may already be sent |
| `collectList` | Buffers entire finite stream into a `List` | Memory/latency cost; invalid for infinite streams |

Example of valid recovery when the body is a line-based protocol:

~~~java
Flux<String> safe = data.onErrorResume(
        IllegalStateException.class,
        error -> Flux.just("ERROR:UPSTREAM_UNAVAILABLE"));
~~~

This works only when clients know how to parse the `ERROR` line per contract. In a strict JSON array, inserting an error string breaks the schema; in a binary stream, never append arbitrary text.

Dangerous example:

~~~java
Flux<String> hidden = data.onErrorComplete();
~~~

If the client receives two items and the server drops the error, the client may believe the stream completed normally. Use only when partial success is an explicitly documented contract.

## 12. JSON Arrays, NDJSON, SSE, and Binary Files

| Format | Can Emit Incrementally? | Mid-Stream Error Strategy |
| --- | --- | --- |
| `application/json` array | Possible, depends on codec | Can leave invalid truncated JSON; hard to inject valid error |
| `application/x-ndjson` | Individual JSON lines | Predefined error envelope line |
| `text/event-stream` | Individual SSE events | `stream-error` event and `complete` marker |
| `text/plain` stream | Lines or bytes | Error marker if defined by protocol |
| `application/octet-stream` | Binary bytes | Typically terminate and verify checksum |
| CSV/ZIP/PDF download | Format-specific | Never inject JSON errors; use temp files/checksums |

A partially sent JSON array becomes malformed JSON if interrupted. If serializing the Nth item fails after earlier items were written, an exception handler cannot switch the status to 500 even though it was an encoder failure rather than a service failure.

## 13. Even the Encoder Can Fail

The data source may return valid Java objects while the HTTP message writer fails:

- A DTO contains a value unsupported by the JSON serializer.
- A custom Jackson serializer throws an exception.
- An object graph has an unconfigured cyclic reference.
- A field violates schema constraints.
- A `DataBuffer`/Netty write fails.
- The client disconnects while the response is being written.
- Resource exhaustion or corrupted byte stream.

If this happens after the body commits, the status cannot change. Ways to reduce risk:

1. Test DTO serialization on realistic data.
2. Validate and normalize items before returning the `Flux` when feasible.
3. For small payloads, prepare the entire representation before writing.
4. For long streams, use envelope schemas and terminal markers.
5. Never perform blocking I/O inside a `JsonSerializer` or encoder.
6. Treat post-commit failures as events needing dedicated logging and metrics.

`collectList` only shifts buffering; if serialization fails later while writing the response, the error can still occur after commit. To guarantee atomic output, prepare the complete output in a bounded way before committing.

## 14. Cancellation and Client Disconnects Are Not Upstream Errors

Clients may navigate away, lose network connectivity, hit a proxy timeout, or encounter graceful server shutdown. These cancel the subscription or raise transport errors.

Example:

~~~java
return stream
        .doOnCancel(() ->
                log.info("client cancelled"))
        .doOnError(error ->
                log.warn("stream failed", error))
        .doFinally(signal ->
                log.debug("stream terminated: {}", signal));
~~~

This snippet requires `stream` and `log` to be declared, not a standalone class.

Notes:

- `SignalType.CANCEL` differs from `ERROR`; not every client disconnect reaches the specific operator you are observing.
- Cancellation propagates upstream, yet does not roll back already-completed side effects.
- An event emitted from a `Flux` does not prove the client received and processed it.
- Proxy buffering can obscure the real flush timing.
- If a client reconnects, it may receive duplicate items if the source retries.

For high-reliability streams, use sequence IDs, checkpoints, cursors, idempotency, and application-level terminal acknowledgments.

## 15. Retries and Resumes Must Have Deduplication Contracts

Suppose a source emits items 1 and 2, then fails. `retry(3)` can re-emit 1 and 2 before advancing to new items. If the client sums quantities blindly, data gets doubled.

To retry safely:

1. Attach a stable ID/sequence number to each item.
2. Persist offsets/cursors when the producer supports replay.
3. Let clients pass `Last-Event-ID` or the corresponding cursor.
4. Define retention windows and expired-cursor handling.
5. Deduplicate on the client or server.
6. Verify idempotency of operations causing side effects.
7. Cap retries and apply backoff.
8. Do not retry schema/validation errors that will never self-heal.

Never treat `retry` as a universal cure for post-commit errors.

## 16. Hands-On Project: Spring Boot 3.3 and Java 17

This example demonstrates two error categories:

- `GET /api/reports/{id}`: `ReportNotFoundException` occurs **before commit**, translated into HTTP 404 with a JSON body.
- `GET /api/events`: on success, emits two items and a `complete` event; when `fail=true`, emits two items followed by a `stream-error` event inside the same HTTP 200 response.
- `GET /api/events-broken`: intentionally emits two items then an unhandled `onError`, used to study error signals and HTTP response boundaries.
- `WebFilter.beforeCommit` attaches a test header.
- `WebTestClient` sends real HTTP over `RANDOM_PORT`; `StepVerifier` inspects the stream error in-JVM; `MockServerHttpResponse` verifies status cannot change after commit.

### 16.1 Directory Structure

~~~text
committed-response-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/stream/
    │   ├── StreamApplication.java
    │   ├── StreamController.java
    │   ├── ReportNotFoundException.java
    │   ├── ErrorAdvice.java
    │   └── CommitMarkerFilter.java
    └── test/java/com/example/stream/
        ├── StreamHttpTests.java
        └── CommitSemanticsTests.java
~~~

### 16.2 settings.gradle

~~~groovy
rootProject.name = 'committed-response-demo'
~~~

### 16.3 build.gradle

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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`starter-webflux` typically uses embedded Reactor Netty. Do not add `spring-boot-starter-web` to this project because Spring Boot defaults to MVC when both web starters exist on the classpath.

### 16.4 StreamApplication.java

~~~java
package com.example.stream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamApplication.class, args);
    }
}
~~~

### 16.5 ReportNotFoundException.java

~~~java
package com.example.stream;

public final class ReportNotFoundException extends RuntimeException {

    public ReportNotFoundException(String id) {
        super("Unknown report: " + id);
    }
}
~~~

### 16.6 StreamController.java

~~~java
package com.example.stream;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamController {

    @GetMapping(
            path = "/reports/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ReportView>> report(
            @PathVariable("id") String id) {

        return Mono.defer(() -> {
            if (!"r1".equals(id)) {
                return Mono.<ResponseEntity<ReportView>>error(
                        new ReportNotFoundException(id));
            }

            return Mono.just(ResponseEntity.ok(
                    new ReportView("r1", "ready")));
        });
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events(
            @RequestParam(
                    name = "fail",
                    defaultValue = "false") boolean fail) {

        Flux<ServerSentEvent<String>> items = Flux.just(
                event("item", "1", "one"),
                event("item", "2", "two"));

        Flux<ServerSentEvent<String>> terminal = fail
                ? Flux.error(
                        new IllegalStateException(
                                "upstream unavailable"))
                : Flux.just(event("complete", "3", "done"));

        return items.concatWith(terminal)
                .onErrorResume(
                        IllegalStateException.class,
                        error -> Flux.just(
                                event(
                                        "stream-error",
                                        "3",
                                        "UPSTREAM_UNAVAILABLE")));
    }

    @GetMapping(
            path = "/events-broken",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> brokenEvents() {

        return Flux.just(
                event("item", "1", "one"),
                event("item", "2", "two"))
                .concatWith(
                        Flux.error(
                                new IllegalStateException(
                                        "upstream unavailable")));
    }

    private static ServerSentEvent<String> event(
            String name, String id, String data) {

        return ServerSentEvent.<String>builder()
                .event(name)
                .id(id)
                .data(data)
                .build();
    }
}

record ReportView(String id, String status) {
}
~~~

In `report`, the error is emitted before any successful HTTP body exists. In `events(true)`, the error is converted into a valid SSE event, so the business outcome is failure despite HTTP 200. In `brokenEvents`, the source emits `onError` after two items with no fallback; HTTP transport may close or reset after partial output.

### 16.7 ErrorAdvice.java

~~~java
package com.example.stream;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(ReportNotFoundException.class)
    public ResponseEntity<ApiError> reportNotFound(
            ReportNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("REPORT_NOT_FOUND"));
    }
}

record ApiError(String code) {
}
~~~

The advice handles only `ReportNotFoundException`. It does not try to catch `Exception` across streaming responses, nor does it echo raw `exception.getMessage()` containing the ID into the public response.

### 16.8 CommitMarkerFilter.java

~~~java
package com.example.stream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class CommitMarkerFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(CommitMarkerFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-Commit-Marker", "applied");
            return Mono.empty();
        });

        return chain.filter(exchange)
                .doOnError(error ->
                        log.error(
                                "Web request failed, committed={}",
                                exchange.getResponse().isCommitted(),
                                error));
    }
}
~~~

The filter neither subscribes manually nor tries to write fresh JSON when the response has committed. It logs unrecovered failures and adds a header inside `beforeCommit`.

## 17. WebTestClient Verifying Pre-Commit Errors and In-Band SSE Errors

### 17.1 StreamHttpTests.java

~~~java
package com.example.stream;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamHttpTests {

    @LocalServerPort
    private int port;

    @Autowired
    private StreamController controller;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    private List<ServerSentEvent<String>> readEvents(
            String path) {

        FluxExchangeResult<ServerSentEvent<String>> result =
                client().get()
                        .uri(path)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().valueEquals(
                                "X-Commit-Marker", "applied")
                        .returnResult(
                                new ParameterizedTypeReference<
                                        ServerSentEvent<String>>() {});

        List<ServerSentEvent<String>> events =
                result.getResponseBody()
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertThat(events).isNotNull();
        return events;
    }

    @Test
    void precommitExceptionBecomesHttp404() {
        client().get()
                .uri("/api/reports/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().valueEquals(
                        "X-Commit-Marker", "applied")
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("REPORT_NOT_FOUND");
    }

    @Test
    void successfulSseHasCompletionMarker() {
        List<ServerSentEvent<String>> events =
                readEvents("/api/events?fail=false");

        assertThat(events).hasSize(3);
        assertThat(events.get(0).event()).isEqualTo("item");
        assertThat(events.get(0).data()).isEqualTo("one");
        assertThat(events.get(1).data()).isEqualTo("two");
        assertThat(events.get(2).event()).isEqualTo("complete");
        assertThat(events.get(2).data()).isEqualTo("done");
    }

    @Test
    void streamingFailureUsesInBandErrorEvent() {
        List<ServerSentEvent<String>> events =
                readEvents("/api/events?fail=true");

        assertThat(events).hasSize(3);
        assertThat(events.get(0).event()).isEqualTo("item");
        assertThat(events.get(1).event()).isEqualTo("item");
        assertThat(events.get(2).event())
                .isEqualTo("stream-error");
        assertThat(events.get(2).data())
                .isEqualTo("UPSTREAM_UNAVAILABLE");
    }

    @Test
    void brokenPublisherHasErrorAfterTwoItems() {
        StepVerifier.create(controller.brokenEvents())
                .expectNextCount(2)
                .expectError(IllegalStateException.class)
                .verify();
    }
}
~~~

`WebTestClient` sends real HTTP over `RANDOM_PORT` to verify pre-commit 404 and SSE 200 with success/error events. The final `StepVerifier` test inspects the underlying Publisher **without** guessing an HTTP status after partial SSE output. Never assert that the broken endpoint must return HTTP 500, as that contradicts response-commit limits.

### 17.2 CommitSemanticsTests.java

~~~java
package com.example.stream;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;

import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;

class CommitSemanticsTests {

    @Test
    void cannotChangeStatusAfterCommit() {
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        assertThat(response.isCommitted()).isFalse();

        response.beforeCommit(() -> {
            response.getHeaders().set(
                    "X-Commit-Marker", "applied");
            return Mono.empty();
        });

        response.setComplete().block();

        assertThat(response.isCommitted()).isTrue();
        assertThat(response.getHeaders()
                .getFirst("X-Commit-Marker"))
                .isEqualTo("applied");

        boolean changed = response.setStatusCode(
                HttpStatus.INTERNAL_SERVER_ERROR);

        assertThat(changed).isFalse();
    }
}
~~~

`MockServerHttpResponse` tests only Spring's response contract in-JVM, not full TCP/TLS/proxy behavior. After `setComplete`, status cannot be modified. This standalone test complements the HTTP tests.

### 17.3 Running Gradle Tests

~~~bash
gradle clean test
~~~

If the project has a wrapper:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Do not present expected results as actual execution logs. Run the command above to verify in your Java/Gradle environment; the app requires no database or external services.

## 18. Using cURL to Observe Three Cases

### 18.1 Starting the Server

~~~bash
gradle bootRun
~~~

With default configuration, Reactor Netty normally binds port 8080 if free.

### 18.2 Pre-Commit Error

~~~bash
curl -i 'http://127.0.0.1:8080/api/reports/missing'
~~~

Expected status: 404, header `X-Commit-Marker: applied`, body equivalent to:

~~~json
{"code":"REPORT_NOT_FOUND"}
~~~

Infrastructure headers and header order may vary.

### 18.3 Successful SSE

~~~bash
curl -i -N 'http://127.0.0.1:8080/api/events?fail=false'
~~~

Body with equivalent semantics:

~~~text
id:1
event:item
data:one

id:2
event:item
data:two

id:3
event:complete
data:done

~~~

Field order or whitespace around SSE fields depends on the encoder; clients should parse SSE events rather than comparing byte-for-byte.

### 18.4 SSE In-Band Error, Status Still 200

~~~bash
curl -i -N 'http://127.0.0.1:8080/api/events?fail=true'
~~~

The client receives two `item` events followed by a `stream-error` event with data `UPSTREAM_UNAVAILABLE`. The HTTP status remains 200. Example contract: only the `complete` event signifies successful completion; `stream-error` signifies a business error.

### 18.5 Unhandled SSE Error

~~~bash
curl -i -N 'http://127.0.0.1:8080/api/events-broken'
~~~

The server may already have sent two items before `onError`. Do not claim cURL will see 500, a JSON error body, or a clean successful response; the exact result depends on server, proxy, and HTTP version. Observe server error logs, client state, event counts, and stream completeness.

## 19. Why Doesn't JSON Error Handling Always Work After Commit?

A server response consists of:

1. Status line or HTTP/2 pseudo-header.
2. Headers such as `Content-Type` and cache metadata.
3. Body bytes.
4. Framing/termination at the HTTP transport layer.

Once the body begins streaming, those earlier parts are fixed. Mutating a Java response object or returning `ResponseEntity.status(500)` in a late callback **cannot rewrite bytes already sent**.

If writing a JSON array:

~~~json
[{"id":1},{"id":2},
~~~

and a later item fails, you cannot append an error JSON object and expect valid JSON output. Clients will hit parse errors or incomplete responses.

If an API requires atomically valid JSON results, consider precomputing within bounded limits, validating serialization beforehand, or switching the contract to an NDJSON envelope with an explicit terminal item.

## 20. File Downloads and Checksums

For large files:

- Verify resource existence and permissions before returning HTTP 200.
- If `Content-Length` is known in advance, clients should verify all expected bytes arrived.
- If checksums/`ETag` or signed manifests are available, clients should verify before consuming the file.
- Write to a temporary file on the client and rename/promote only once download completes.
- If storage fails mid-download, never inject JSON errors into ZIP, PDF, image, or binary files.
- If retrying with HTTP `Range`, ensure snapshot consistency, `ETag`, and `Content-Range` match the contract.
- If an all-or-nothing response is required, generate a bounded temporary file before starting to send.

`Content-Length` is not a checksum; it checks byte length without guaranteeing contents were not altered.

## 21. Metrics: HTTP 200 Is Not Enough to Measure Business Success

Track these separately:

| Metric | Value |
| --- | --- |
| `stream_started` | Streaming session opened |
| `stream_completed` | Emitted terminal `complete` successfully |
| `stream_error_event` | Emitted in-band `stream-error` |
| `stream_aborted` | Stream errored/closed before completion |
| `client_cancelled` | Client disconnected/cancelled where observable |
| `elements_emitted` | Number of items emitted on server |
| `bytes_written` | Number of bytes written by server |
| `upstream_errors` | Failures from service/data source |
| `serialization_errors` | Codec/Jackson failures after writing started |
| `retry_count` | Recovery/reconnect attempts |

HTTP status 200 and `stream_error_event` can both be true at the same time. Do not build dashboards counting only 5xx responses and conclude a streaming API has zero failures.

With Micrometer, use bounded labels such as `error_code` or endpoint template; avoid raw URLs or user IDs as metric tags causing unbounded cardinality.

### doFinally Is Not Client Acknowledgment

`doFinally` receives `COMPLETE`, `ERROR`, or `CANCEL` from the Publisher. It does not prove the client safely stored every byte. If exactly-once or end-to-end acknowledgment is required, build an explicit application protocol.

## 22. Differences from Spring MVC

Spring MVC also has response commit, using the Servlet API:

| Aspect | WebFlux | Spring MVC |
| --- | --- | --- |
| Front controller | `DispatcherHandler` | `DispatcherServlet` |
| Response | `ServerHttpResponse` | `HttpServletResponse` |
| Commit state | `isCommitted()` | `isCommitted()` |
| Pre-commit hook | `beforeCommit(...)` | No exact equivalent hook |
| Streaming | `Flux`, SSE, reactive `DataBuffer` | `SseEmitter`, `ResponseBodyEmitter`, `StreamingResponseBody` |
| Error handling | `WebExceptionHandler`, `@ControllerAdvice` | `HandlerExceptionResolver`, `@ControllerAdvice`, Servlet error dispatch |
| I/O | Reactive non-blocking per runtime | Servlet/async with many blocking writes |
| Post-commit limit | Cannot change sent status | Also cannot change sent status |

In Servlet, `HttpServletResponse.reset()` is valid by contract only before the response commits; after commit it may throw `IllegalStateException`. Do not assume Servlet's `reset()` applies to WebFlux.

MVC can return `Mono`/`Flux` in some cases, so merely having reactive return types does not prove a server runs WebFlux. Spring Boot prefers MVC by default whenever both `starter-web` and `starter-webflux` are on the classpath.

## 23. Step-by-Step Debugging of After-Commit Errors

1. Confirm whether the application uses WebFlux or MVC.
2. Confirm whether the response is SSE, NDJSON, JSON array, or binary.
3. Check whether status/headers were committed before the error occurred.
4. Check whether the source Publisher emitted the error before or after emitting items.
5. Check whether the encoder failed while serializing a specific item.
6. Classify upstream failure, client cancel, transport error, or proxy timeout.
7. Inspect `WebFilter` `doOnError`/`doFinally` and `isCommitted` at callback time.
8. If pre-commit, check whether `@ExceptionHandler` or `WebExceptionHandler` mapped the right status.
9. If post-commit, verify an appropriate in-band error marker or stream abort.
10. Check whether clients require a terminal `complete` marker or checksum.
11. Check whether retries cause duplicate items.
12. Record separate metrics for stream success, error, and cancellation.
13. Test pre-commit errors over HTTP integration.
14. Test SSE success/error events using an event parser.
15. Test broken Publishers separately with `StepVerifier`, without hardcoding HTTP 500 after commit.

Logs generated when streams fail should carry a correlation ID and omit raw `Authorization`, `Cookie`, access tokens, or personal body payloads. If Netty wiretap is enabled in debug environments, scope it tightly and turn it off after investigation.

## 24. Design Mistakes to Avoid

### Mistake 1: Always Returning 500 in Global Advice

A committed response cannot change status. Use global advice for pre-commit errors, and in-band events or transport aborts for post-commit errors.

### Mistake 2: Using onErrorComplete to “Fix” a Stream

It hides partial results, misleading clients into assuming full delivery. Always provide a terminal marker.

### Mistake 3: Returning the Wrong Type in onErrorResume

If `Flux<ItemDto>` serializes NDJSON, never suddenly emit an out-of-contract String. Use an explicit envelope type or SSE event type.

### Mistake 4: Subscribing Manually

~~~java
// Do not use in reactive HTTP controllers:
data.subscribe(this::save);
return Mono.empty();
~~~

Breaks the link to HTTP lifecycle, errors, and cancellation. Return the reactive chain to the framework.

### Mistake 5: Calling block() on the Event Loop

Stalls threads and times out other streams. Use reactive clients/drivers, or offload blocking work properly.

### Mistake 6: Using collectList on Unbounded Sources

May never finish and exhaust memory. Use buffering only on bounded payloads with size and time limits.

### Mistake 7: Uncontrolled Retries

Can re-send already-delivered items. Use sequences, cursors, and deduplication.

### Mistake 8: Writing Error JSON After SSE Items

Breaks protocol syntax and fails to alter status. For SSE failures, emit an event matching your schema.

### Mistake 9: Reading isCommitted Without Checking setStatusCode Return Value

Between check and update, a concurrent commit may occur. Check the boolean return value and design pipelines to avoid races.

### Mistake 10: Treating HTTP 200 as a Stream-Success Metric

A 200 response can carry `stream-error` or miss a `complete` marker. Separate application metrics from HTTP status metrics.

### Mistake 11: Doing Network or Database I/O Inside beforeCommit

Commit callbacks are not the place for blocking operations. They can delay flushing or cause failures mid-commit.

### Mistake 12: Trying to Assert HTTP 500 for Broken SSE

Outcomes depend on protocol, server, and client; assert the data contract and error signal instead of guessing.

## 25. Operational Checklist

- [ ] Identified all preconditions that must be validated before commit.
- [ ] Decided whether the API uses an atomic body or streaming.
- [ ] Defined appropriate error formatting for SSE/NDJSON if used.
- [ ] Included a terminal completion marker so clients know delivery succeeded.
- [ ] Avoided modifying status/headers after commit.
- [ ] Used `beforeCommit` only for appropriate pre-commit logic.
- [ ] Avoided manual `subscribe()`/`block()` or swallowing errors.
- [ ] Defined deduplicating retry/resume/checkpoint contracts.
- [ ] Distinguished upstream errors from client cancellation.
- [ ] Tracked incomplete streams independently of HTTP status.
- [ ] Tested pre-commit and post-commit failures separately.
- [ ] Tested SSE error events, terminal `complete`, and duplicate IDs.
- [ ] Enforced memory bounds wherever buffering is chosen.
- [ ] Verified length/checksum for downloads.
- [ ] Kept stack traces, tokens, and sensitive data out of client responses.
- [ ] Kept code aligned with active Spring Boot and Spring Framework versions.

## 26. Summary

**Once an HTTP response has committed, its status and headers cannot be replaced with another response.** In Spring WebFlux, a `Flux` can emit two items, the server commits HTTP 200, and only then does the Publisher emit `onError`. Adding an `@ExceptionHandler` returning `ResponseEntity.status(500)` cannot take back bytes already sent.

There are three design options: validate and prepare data before commit when an atomic response is required; design streams with in-band error events and terminal `complete` markers so clients understand state; or let the error propagate, close/reset the stream, and let clients detect incomplete output when the protocol cannot embed errors.

Understanding `ServerHttpResponse.isCommitted()`, `beforeCommit`, Reactor's `doOnError`/`onErrorResume`/`doFinally`, HTTP codecs, and the gap between completion and client acknowledgment forms the foundation of safe streaming error handling. On the client side, **never treat HTTP 200 as proof that all data was received**.

## 27. References

- Spring Framework 6.1 — ServerHttpResponse Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Framework — WebFlux Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework — WebExceptionHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html
- Spring Framework — WebFlux Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — Spring MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Reactor — Error Handling Operators: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- MDN — Using Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110