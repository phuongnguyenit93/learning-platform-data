# Limits on Modifying HTTP Status and Reporting Mid-Stream Errors in Spring WebFlux

In an ordinary HTTP response, the server prepares status and headers, then writes the body. With a streaming response, the body is sent in multiple parts over time. Once the server has sent the headers or first bytes and the response is **committed**, the status and headers have already become part of the response on the network. The server cannot change status from 200 to 500 just because the publisher emits an error mid-stream.

This is an important constraint when building endpoints returning Flux, NDJSON, or Server-Sent Events (SSE). An error from a Reactor publisher is still a terminal error signal ending the stream, yet if the response is already committed the framework cannot go back to change the status line or replace the already-sent body. The application must decide up front how mid-stream errors are represented: emit a protocol-level error record, close the connection, or let the client resume from a checkpoint.

This lesson belongs to **Continuous Data Streaming**, focusing on the HTTP response commit boundary, status modification before/after commit, reactive error handling, and error-reporting contracts for clients reading streams.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain response commit and the point when status/headers can no longer be changed.
- Use ServerHttpResponse.isCommitted() and setStatusCode() properly.
- Register a beforeCommit callback to prepare status/headers before the response is sent.
- Distinguish errors occurring before writing the body from errors occurring after the stream has emitted data.
- Understand why @ExceptionHandler or WebExceptionHandler cannot replace an already-committed response.
- Distinguish doOnError, onErrorMap, onErrorResume, and retryWhen.
- Design error records for NDJSON or error events for SSE.
- Handle preflight errors with Mono<ResponseEntity<Flux<T>>>.
- Understand the risks of a mid-flight broken JSON array.
- Design cancellation, logging, checkpoints, and reconnects for streams.
- Write a Java 17+ Spring Boot WebFlux example with WebTestClient.

## 2. HTTP responses have a commit boundary

An HTTP response consists of status code, headers, and body. The server must send status and headers before the body. Once this metadata is written to the network, the response is committed.

~~~text
Before commit
    |
    | Can choose status
    | Can modify headers
    | Can turn errors into another response
    v
Commit response
    |
    | Status + headers are sent
    v
Writing body / stream
    |
    | Can send more data per protocol
    | Can detect errors and log
    | Cannot change already-sent status/headers
    v
Completes or connection is terminated
~~~

With WebFlux, the response is typically committed when the framework begins writing the body or flushes headers. For streams, this moment can arrive as soon as the first element is written. A controller method may have already returned a Flux beforehand, yet the publisher is only subscribed to while the framework writes the response.

Distinguish:

- **Controller method returned:** the Java method has returned the publisher.
- **Publisher emitted:** upstream has emitted one or more elements.
- **Response committed:** status and headers have been sent; from this point they cannot be altered.

These three events are related but not synonymous. A Flux can be created early, subscribed to later, and only then emit its first element. An error in the publisher may occur before commit or after commit depending on write timing and how the writer handles the media type.

### Which APIs does ServerHttpResponse provide?

| API | Meaning |
| --- | --- |
| isCommitted() | Reports whether the response has already committed |
| setStatusCode(status) | Sets status if uncommitted; returns boolean indicating whether it could be set |
| getStatusCode() | Reads the current status |
| getHeaders() | Accesses response headers |
| beforeCommit(action) | Registers work to run before the response commits |
| writeWith(body) | Writes a DataBuffer publisher to the body |
| writeAndFlushWith(body) | Writes DataBuffer groups and flushes per group |
| setComplete() | Completes the response without writing more body |

Crucially, **setStatusCode returns a boolean**. If it returns false, the status was not changed, usually because the response already committed. Do not call setStatusCode and assume the new status was applied.

~~~java
ServerHttpResponse response = exchange.getResponse();

boolean changed = response.setStatusCode(HttpStatus.BAD_GATEWAY);

if (!changed) {
    log.warn("Response already committed; status cannot be changed");
}
~~~

This is an illustrative fragment; it requires importing HttpStatus and configuring a logger. Whenever possible, choose the status before starting to write the body rather than waiting until an error occurs.

## 3. beforeCommit: preparing status and headers before sending

ServerHttpResponse.beforeCommit accepts a Supplier returning Mono<Void>. The callback runs right before the response commits. This is the right place to add final headers or finalize metadata depending on processing outcomes.

~~~java
response.beforeCommit(() ->
    Mono.fromRunnable(() ->
        response.getHeaders().set("X-Stream-State", "starting")));
~~~

The action must be placed inside the publisher returned from the callback. This lets the framework execute the work as part of the commit lifecycle. Do not trigger an async side effect outside the publisher and expect the framework to wait for it to finish.

You can set the status inside the callback if the status has not yet been chosen:

~~~java
response.beforeCommit(() ->
    Mono.fromRunnable(() -> {
        response.setStatusCode(HttpStatus.ACCEPTED);
        response.getHeaders().set("X-Stream-State", "ready");
    }));
~~~

In most controllers, a more readable approach is using ResponseEntity to declare status and headers when building the response:

~~~java
return ResponseEntity.accepted()
    .header("X-Stream-State", "ready")
    .body(eventFlux);
~~~

If you need to check an asynchronous condition before starting the stream, you can return Mono<ResponseEntity<Flux<T>>>. The Mono decides response metadata; the inner Flux is the body written afterward.

~~~java
public Mono<ResponseEntity<Flux<Event>>> stream() {
    return verifySourceIsAvailable()
        .then(Mono.fromSupplier(() ->
            ResponseEntity.ok()
                .contentType(MediaType.valueOf("application/x-ndjson"))
                .body(eventSource())));
}
~~~

If verifySourceIsAvailable() fails before ResponseEntity is built and the response commits, an exception handler can still return 503 or another error response. If eventSource() fails after emitting the first record, the status has already been sent and cannot be changed.

**Preflight only confirms conditions at check time.** It does not guarantee the data source will not fail later. A long stream still needs a mid-stream error policy.

## 4. Errors before commit and errors after commit

These two situations require different handling.

### Errors before response commit

Examples:

- Stream source not found.
- Insufficient access permissions.
- Invalid query parameters.
- Unable to open upstream connection.
- Quota or business state check failed.

In these cases, the server has not sent status/headers/body yet. A normal error response can be returned:

~~~java
@ExceptionHandler(StreamUnavailableException.class)
public ResponseEntity<ApiError> handleUnavailable(
        StreamUnavailableException exception) {

    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .body(new ApiError(
            "STREAM_UNAVAILABLE",
            "The stream source is temporarily unavailable"));
}
~~~

Spring WebFlux can route exceptions to @ExceptionHandler/@RestControllerAdvice or WebExceptionHandler. As long as the response has not committed, this mechanism can generate a replacement response with an appropriate status.

### Errors after response commit

Examples:

- Upstream database or message broker disconnects after sending several events.
- A subsequent record fails to decode.
- A remote API emits an error mid-stream.
- A reactive transformation fails after the client has already received data.

At that point, the status has already been sent. You cannot turn 200 into 500 or replace the already-emitted body with a new JSON error object.

~~~text
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"type":"data","id":"evt-1"}
{"type":"data","id":"evt-2"}
<upstream fails here>
~~~

Without recovery, the client may see the stream terminate abnormally after the second record. The HTTP status remains 200 because that status was sent when the stream started.

You can log the error, close the connection, or emit an error record according to the NDJSON/SSE contract. The choice depends on whether the client can understand and handle an error event within the same stream.

### Exception handlers cannot roll back a response

@RestControllerAdvice is very useful for errors occurring before commit. Once the body publisher has started writing, an exception reaching an error handler does not mean the framework can send a new response.

Depending on the server and timing of the error, WebFlux may log the error, stop writing the body, or close the connection. The client may receive a partial body or a truncated stream. Never assume the client will see a new JSON error response or status 500.

## 5. Reactor error signals and common operators

In Reactor, an error is a terminal signal. After a publisher emits onError, that publisher does not continue emitting onNext normally. To continue, the application must substitute another publisher or convert the error into a domain value.

| Operator | Role | Replaces error with data? |
| --- | --- | --- |
| doOnError | Observes errors for logs/metrics | No |
| onErrorMap | Transforms exception type | No; still emits onError |
| onErrorResume | Switches to a fallback publisher | Can do so |
| retryWhen | Resubscribes to source per policy | Not directly; may re-emit data |

### doOnError only observes

~~~java
Flux<Event> events = upstream
    .doOnError(error ->
        log.error("Stream failed", error));
~~~

doOnError does not handle the error. After logging, the error continues downstream and terminates the publisher. If the response already committed, merely adding a log cannot produce status 500.

### onErrorMap transforms exceptions without recovering

~~~java
Flux<Event> events = upstream
    .onErrorMap(
        IOException.class,
        error -> new UpstreamUnavailableException(error));
~~~

onErrorMap is useful for translating technical errors into application-semantic exceptions. It still emits onError, so without a subsequent handling operator, the response body stream still ends in error.

### onErrorResume substitutes a publisher on error

~~~java
Flux<Event> events = upstream
    .onErrorResume(error -> fallbackEvents());
~~~

onErrorResume switches to a fallback publisher. The fallback publisher must match the downstream data type. If the response already committed, fallback data becomes the continuation of the already-started body; it does not alter the already-sent status.

This is the basis for emitting a final error record in NDJSON or an error event in SSE. Only use this approach when the API contract specifies that the client must recognize error records/events.

### retryWhen can re-emit data

~~~java
Flux<Event> events = upstream
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200)));
~~~

Retry can fit when upstream has transient errors and supports resubscription. However, if the stream already emitted evt-1, evt-2 and then failed, retrying may emit evt-1, evt-2 again. The client may receive duplicate data.

Only retry when the source has explicit replay semantics, or each event carries an ID/sequence so the client can deduplicate and resume. With non-replayable sources, automatic retries can lose or duplicate data.

### onErrorResume does not turn cancellation into an error

When a client closes the connection, downstream may send cancel. Cancellation is not onError, so onErrorResume is not the hook for handling client disconnects. Use doOnCancel or doFinally to observe cancellation and release resources.

~~~java
Flux<Event> events = upstream
    .doOnCancel(() -> log.info("Client cancelled stream"))
    .doFinally(signal -> log.info("Stream finished: {}", signal));
~~~

doFinally receives COMPLETE, ERROR, and CANCEL alike. Do not hold sockets, subscriptions, or resources past the lifecycle once the client has cancelled.

## 6. Reporting errors in NDJSON via a protocol record

NDJSON represents each record as a JSON value on a single line. When a stream errors after several records, the server can emit a final record describing the error, if the stream schema allows it.

~~~text
{"type":"data","id":"evt-1","code":null}
{"type":"data","id":"evt-2","code":null}
{"type":"error","id":null,"code":"UPSTREAM_INTERRUPTED"}
~~~

The client reads line by line, distinguishing type=data and type=error. The HTTP status remains 200 because the response committed when the stream began. The error record is **application-protocol data**, not a new HTTP error response.

An explicit data type:

~~~java
public record StreamMessage(
    String type,
    String id,
    String code
) {
    public static StreamMessage data(String id) {
        return new StreamMessage("data", id, null);
    }

    public static StreamMessage error(String code) {
        return new StreamMessage("error", null, code);
    }
}
~~~

The publisher can convert errors into a final record:

~~~java
Flux<StreamMessage> messages = upstreamEvents
    .map(event -> StreamMessage.data(event.id()))
    .onErrorResume(error -> {
        log.warn("Event stream interrupted", error);
        return Flux.just(
            StreamMessage.error("UPSTREAM_INTERRUPTED"));
    });
~~~

This produces a complete stream conforming to the NDJSON schema. The client must still inspect each record's type and not treat error records as ordinary business data.

### Choosing stable error codes

Do not send raw exception messages or stack traces to the client. Send stable error codes, such as:

- UPSTREAM_INTERRUPTED
- SOURCE_TEMPORARILY_UNAVAILABLE
- STREAM_CHECKPOINT_EXPIRED
- STREAM_RATE_LIMITED

Detailed technical information should be logged server-side with a correlation ID. The client can display a friendly message or decide to retry based on the code.

### Do not emit error records if the client does not know the schema

If an API published an NDJSON contract containing only Event, suddenly sending a JSON object with a different structure can break client decoding. Define an envelope from the start, such as every record having type, payload, and error, or define a union schema clearly understood by the client.

## 7. Reporting errors in Server-Sent Events

SSE is a streaming protocol over text/event-stream. An event can carry an event name, ID, retry hint, and data. Therefore, a dedicated event can be defined for mid-stream errors.

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<StreamMessage>> events() {
    return upstreamEvents()
        .map(event -> ServerSentEvent.builder(
                StreamMessage.data(event.id()))
            .id(event.id())
            .event("message")
            .build())
        .onErrorResume(error -> Flux.just(
            ServerSentEvent.builder(
                    StreamMessage.error("UPSTREAM_INTERRUPTED"))
                .event("stream-error")
                .build()));
}
~~~

In the example, data events use the event name message. When upstream errors, the publisher emits an SSE with event name stream-error and then completes. The HTTP status remains the initial status.

The JavaScript client can register a dedicated event listener:

~~~javascript
const source = new EventSource("/events");

source.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  console.log("data", message);
});

source.addEventListener("stream-error", event => {
  const message = JSON.parse(event.data);
  console.error("stream interrupted", message.code);
});
~~~

This is client-side illustrative code. EventSource also has its own built-in error event related to connection/transport state; the server-defined business event stream-error is an application-protocol message. These two are not the same.

### IDs and resumption

SSE supports event IDs. If the server attaches increasing IDs or a replayable cursor, the client can reconnect and send Last-Event-ID to resume from the right position. This requires the server to retain checkpoints or be able to re-query events after that ID.

Do not emit arbitrary IDs without resume semantics. An ID is only helpful when the server knows how to resume without losing or duplicating data.

## 8. Why can a JSON array break when a stream fails?

A Flux<Event> returned with application/json is typically collected by the Jackson encoder into a List and serialized as a JSON array. The client receives a complete JSON document once writing finishes.

If a system actually streams a JSON array incrementally, an error after sending a few elements can leave a half-written body:

~~~text
[
  {"id":"evt-1"},
  {"id":"evt-2"},
~~~

This is not a valid JSON document because the closing array bracket and remaining elements were never sent. Client parsers may report syntax errors or unexpected end-of-input.

Distinguish the two cases:

- With the default encoder collecting Flux into a List for application/json, data may be buffered before writing; this reduces element-by-element streaming while increasing memory and potentially delaying the response.
- With streaming media types such as application/x-ndjson or text/event-stream, each record/event can be written and flushed independently. Mid-stream errors can be represented by a final record/event or by closing the connection.

Do not choose an application/json array if the product requirement is sending continuous records over time and having clients process each record immediately on arrival. Choose NDJSON or SSE with a published error schema.

## 9. When to return an error status vs. emit an error record?

| Situation | Appropriate handling |
| --- | --- |
| Unable to authenticate request before stream | Return 401/403 before commit |
| Lacks permission to view resource | Return 403 before commit |
| Stream source not ready | Return 503 before commit |
| Invalid query/filter | Return 400 before commit |
| Upstream error before response body begins | Use exception handler to return error status if uncommitted |
| Upstream error after records have been sent | NDJSON error record, SSE error event, or close connection per contract |
| Client closes connection | Cancel upstream and release resources; do not try to emit error record |
| Timeout before commit | Can return 504 if response is uncommitted |
| Timeout after commit | Record error and terminate or emit error signal inside stream |

This decision must be designed into the API contract. Clients need to know whether errors are expressed via HTTP status, a final record, a dedicated event, or connection closure. Clients should never have to guess from a stream abruptly stopping.

## 10. Complete Java 17+ example with Spring Boot WebFlux

This example provides four endpoints:

- GET /streams/preflight: checks the source before creating a response; if unavailable, returns 503 via exception advice.
- GET /streams/ndjson: emits two data records and then simulates an upstream error; the error becomes a final NDJSON record.
- GET /streams/sse: emits one data event and then simulates an error; the error becomes an SSE event named stream-error.
- GET /streams/accepted: selects status 202 and adds a response header via beforeCommit before the body starts writing.

### Project structure

~~~text
webflux-stream-error-demo/
├── pom.xml
└── src
    ├── main/java/com/example/stream
    │   ├── StreamDemoApplication.java
    │   ├── StreamController.java
    │   ├── StreamMessage.java
    │   ├── ApiError.java
    │   └── StreamExceptionAdvice.java
    └── test/java/com/example/stream
        └── StreamControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-stream-error-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot 3.3.5 manages compatible versions of Spring Framework, Reactor, and Jackson. The example uses Java 17 and Spring WebFlux.

### StreamDemoApplication.java

~~~java
package com.example.stream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamDemoApplication.class, args);
    }
}
~~~

### StreamMessage.java

~~~java
package com.example.stream;

public record StreamMessage(
    String type,
    String id,
    String code
) {
    public static StreamMessage data(String id) {
        return new StreamMessage("data", id, null);
    }

    public static StreamMessage error(String code) {
        return new StreamMessage("error", null, code);
    }
}
~~~

### ApiError.java

~~~java
package com.example.stream;

public record ApiError(String code, String message) {
}
~~~

### StreamController.java

~~~java
package com.example.stream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/streams")
public class StreamController {

    private static final Logger log =
        LoggerFactory.getLogger(StreamController.class);

    private static final String NDJSON_VALUE =
        "application/x-ndjson";

    private static final MediaType NDJSON =
        MediaType.valueOf(NDJSON_VALUE);

    @GetMapping("/preflight")
    public Mono<ResponseEntity<Flux<StreamMessage>>> preflight() {
        return verifySource()
            .then(Mono.fromSupplier(() ->
                ResponseEntity.ok()
                    .contentType(NDJSON)
                    .body(Flux.just(StreamMessage.data("evt-ready")))));
    }

    private Mono<Void> verifySource() {
        return Mono.error(new StreamUnavailableException());
    }

    @GetMapping(
        value = "/ndjson",
        produces = NDJSON_VALUE)
    public Flux<StreamMessage> ndjson() {
        return simulatedMessages()
            .onErrorResume(StreamInterruptedException.class, error -> {
                log.warn("NDJSON source interrupted", error);
                return Flux.just(
                    StreamMessage.error("UPSTREAM_INTERRUPTED"));
            });
    }

    private Flux<StreamMessage> simulatedMessages() {
        return Flux.concat(
            Flux.just(
                StreamMessage.data("evt-1"),
                StreamMessage.data("evt-2")),
            Mono.<StreamMessage>error(
                new StreamInterruptedException()));
    }

    @GetMapping(
        value = "/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<StreamMessage>> sse() {
        Flux<ServerSentEvent<StreamMessage>> source = Flux.concat(
            Flux.just(
                ServerSentEvent.builder(StreamMessage.data("evt-1"))
                    .id("1")
                    .event("message")
                    .build()),
            Mono.<ServerSentEvent<StreamMessage>>error(
                new StreamInterruptedException()));

        return source.onErrorResume(
            StreamInterruptedException.class,
            error -> {
                log.warn("SSE source interrupted", error);
                return Flux.just(
                    ServerSentEvent.builder(
                            StreamMessage.error("UPSTREAM_INTERRUPTED"))
                        .id("2")
                        .event("stream-error")
                        .build());
            });
    }

    @GetMapping(
        value = "/accepted",
        produces = NDJSON_VALUE)
    public ResponseEntity<Flux<StreamMessage>> accepted(
            ServerHttpResponse response) {

        response.beforeCommit(() ->
            Mono.fromRunnable(() ->
                response.getHeaders().set(
                    "X-Stream-State", "starting")));

        return ResponseEntity.accepted()
            .contentType(NDJSON)
            .body(Flux.just(StreamMessage.data("evt-accepted")));
    }
}

class StreamUnavailableException extends RuntimeException {
}

class StreamInterruptedException extends RuntimeException {
}
~~~

Points to note:

1. **preflight** simulates an error before ResponseEntity is created. The Mono emits an error so StreamExceptionAdvice can return 503 while the response is uncommitted.
2. **ndjson** emits two records and then emits an error. onErrorResume replaces the error signal with a StreamMessage having type=error. The client receives three NDJSON lines; the status remains 200.
3. **sse** emits one message event and then one stream-error event. Event names help the client distinguish data from stream error notifications.
4. **accepted** declares status 202 via ResponseEntity and adds a header inside beforeCommit. The callback runs before status/headers are sent.
5. The two simulated exceptions are kept package-private in the same file to keep the example concise. In a real application, exceptions can live in their own package.

### StreamExceptionAdvice.java

~~~java
package com.example.stream;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class StreamExceptionAdvice {

    @ExceptionHandler(StreamUnavailableException.class)
    public ResponseEntity<ApiError> unavailable(
            StreamUnavailableException exception) {

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError(
                "STREAM_UNAVAILABLE",
                "The stream source is temporarily unavailable"));
    }
}
~~~

The advice handles the preflight error. StreamInterruptedException inside the body publisher is handled right within the NDJSON/SSE pipeline because it can occur after the response has committed.

### StreamControllerTests.java

~~~java
package com.example.stream;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@WebFluxTest(StreamController.class)
@Import(StreamExceptionAdvice.class)
class StreamControllerTests {

    private static final MediaType NDJSON =
        MediaType.valueOf("application/x-ndjson");

    @Autowired
    private WebTestClient client;

    @Test
    void preflightFailureCanReturnServiceUnavailable() {
        client.get()
            .uri("/streams/preflight")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("STREAM_UNAVAILABLE");
    }

    @Test
    void lateNdjsonFailureBecomesAnErrorRecord() {
        WebTestClient.ResponseSpec response = client.get()
            .uri("/streams/ndjson")
            .accept(NDJSON)
            .exchange()
            .expectStatus().isOk();

        response.expectHeader().contentTypeCompatibleWith(NDJSON);

        FluxExchangeResult<StreamMessage> result =
            response.returnResult(StreamMessage.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                StreamMessage.data("evt-1"),
                StreamMessage.data("evt-2"),
                StreamMessage.error("UPSTREAM_INTERRUPTED"))
            .verifyComplete();
    }

    @Test
    void beforeCommitCanSetHeaderAndResponseStatus() {
        WebTestClient.ResponseSpec response = client.get()
            .uri("/streams/accepted")
            .accept(NDJSON)
            .exchange()
            .expectStatus().isAccepted();

        response.expectHeader()
            .valueEquals("X-Stream-State", "starting");

        FluxExchangeResult<StreamMessage> result =
            response.returnResult(StreamMessage.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(StreamMessage.data("evt-accepted"))
            .verifyComplete();
    }

    @Test
    void lateSseFailureBecomesNamedErrorEvent() {
        ParameterizedTypeReference<ServerSentEvent<StreamMessage>> eventType =
            new ParameterizedTypeReference<>() {};

        FluxExchangeResult<ServerSentEvent<StreamMessage>> result =
            client.get()
                .uri("/streams/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(eventType);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "message".equals(event.event()) &&
                StreamMessage.data("evt-1").equals(event.data()))
            .expectNextMatches(event ->
                "stream-error".equals(event.event()) &&
                StreamMessage.error("UPSTREAM_INTERRUPTED")
                    .equals(event.data()))
            .verifyComplete();
    }
}
~~~

Run tests in the directory containing pom.xml:

~~~bash
mvn -q test
~~~

If all four tests pass, Maven exits with code 0. The tests verify:

- Pre-commit errors can be turned into HTTP 503.
- Mid-NDJSON-stream errors are represented by a final record without changing status 200.
- beforeCommit adds headers before the response is sent and ResponseEntity preserves status 202.
- SSE streams can emit a stream-error event so clients recognize data source failures.

### Running the application and calling it

Start:

~~~bash
mvn spring-boot:run
~~~

Test preflight error:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/streams/preflight
~~~

Main result: HTTP 503 Service Unavailable and JSON with code STREAM_UNAVAILABLE.

Read NDJSON:

~~~bash
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/streams/ndjson
~~~

The body has three records: evt-1, evt-2, and the error record UPSTREAM_INTERRUPTED. Response status is 200 because the stream has already started.

Read SSE:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/streams/sse
~~~

The client receives a message event, followed by a stream-error event. Depending on the client, read the event name and parse data to identify the error.

## 11. What if an error record cannot be emitted?

Not every stream allows inserting an error record. For example, the client may only accept an Event schema with no type/error fields; or upstream has failed so badly that another reliable message cannot be produced.

Several options exist then:

1. **Terminate the stream:** let the publisher emit an error and close the connection. The client must recognize the stream is incomplete rather than treating already-received data as the complete result.
2. **Send a terminal marker if the protocol defines one:** a final record such as type=end or type=error can confirm whether the stream ended normally or failed.
3. **Reconnect from a checkpoint:** the client sends the last-seen event ID/sequence so the server resumes from the last received position.
4. **Use a dedicated SSE event:** if the protocol is SSE, emit a stream-error event while writing is still possible.
5. **Use HTTP status on the next connection:** if the old stream already committed, the client can open a new request and the new request returns 503/429/401 depending on cause.

Do not pretend a stream completed successfully if data was lost. If an error marker cannot be sent, the client needs a way to detect that the connection dropped before a terminal marker or before receiving a completion checkpoint.

### Terminal markers and sequence numbers

An NDJSON protocol can define records:

~~~json
{"type":"data","sequence":41,"payload":{"id":"evt-41"}}
{"type":"data","sequence":42,"payload":{"id":"evt-42"}}
{"type":"end","lastSequence":42}
~~~

If the source fails:

~~~json
{"type":"error","lastSequence":42,"code":"UPSTREAM_INTERRUPTED"}
~~~

The client knows the last acknowledged record reached sequence 42. When reconnecting, the client can request sequences greater than 42 if the server supports replay. This distinguishes a successfully completed stream, a failed stream, and an abruptly severed connection.

### Do not send a new HTTP status inside the body

A record with field status=500 is merely application data. It does not replace the already-sent HTTP status line. You can use a code or type field to describe the error, but do not refer to that as changing the HTTP status.

## 12. Timeouts, cancellation, and upstream resources

A streaming request can live longer than a typical request-response. When an error or cancellation occurs, upstream resources must be cleaned up.

### Timeouts before and after commit

A timeout before commit can be turned into status 504 Gateway Timeout if the response has not started. A timeout after commit cannot change status; emit an error record/event if the protocol supports it or close the connection.

~~~java
Flux<StreamMessage> messages = upstream
    .timeout(Duration.ofSeconds(30))
    .onErrorResume(TimeoutException.class, error ->
        Flux.just(StreamMessage.error("STREAM_TIMEOUT")));
~~~

This example turns a timeout into an error record if the publisher can still write to the body. Choose timeouts based on semantics: first-byte timeout, inter-event timeout, and total stream lifetime are distinct policies.

### Client cancellation

When a client closes the connection, WebFlux can cancel the subscription. Upstream should receive cancellation to stop queries, listeners, or consumers that are no longer needed.

~~~java
Flux<Event> events = eventSource()
    .doOnCancel(() -> subscriptionRegistry.remove(requestId))
    .doFinally(signal -> metrics.record(signal));
~~~

If upstream is a message broker consumer, database cursor, or external resource, register cleanup in using/usingWhen or an appropriate lifecycle mechanism. Do not rely on onErrorResume to clean up cancellation because cancel is not an error signal.

### Do not hold resources solely to attempt sending an error notice

If the socket is already closed, building another error record accomplishes nothing. Prioritize cancelling upstream, releasing buffers, closing cursors, and logging sufficient correlation IDs for investigation. The client can reconnect at a checkpoint when the service is ready.

## 13. Logging, metrics, and correlation IDs

A stream can run for many minutes. A log saying only “request failed” is not enough to identify the last event sent.

Record:

- Request/correlation ID.
- Stream ID or subscription ID.
- Route and media type.
- Last event ID/sequence confirmed sent.
- Start time, active duration, and end time.
- Terminal outcome: complete, error, or cancel.
- Stable error code, not the entire payload.
- Number of records sent and reconnect count if tracked by the system.

Terminal signals can be observed with doFinally:

~~~java
Flux<Event> stream = source
    .doOnError(error ->
        log.warn("Stream failed, streamId={}", streamId, error))
    .doOnCancel(() ->
        log.info("Stream cancelled, streamId={}", streamId))
    .doFinally(signal ->
        log.info("Stream ended, streamId={}, signal={}",
            streamId, signal));
~~~

Do not log entire event payloads if payloads contain personal data or secrets. Use IDs, sequences, error codes, and correlation IDs for tracing.

## 14. Common mistakes and fixes

1. **Trying to change status after the stream sent its first bytes.** setStatusCode may return false because the response already committed. Decide status before writing the body.
2. **Assuming @ExceptionHandler always produces a 500 response.** Advice cannot alter an already-committed status/body; late errors need an in-stream error protocol or connection termination.
3. **Using doOnError as a recovery mechanism.** doOnError only observes; the error still terminates the publisher.
4. **Using onErrorMap and thinking the stream continues.** onErrorMap only transforms the exception; it is still a terminal error.
5. **Using onErrorResume without defining an error schema.** The fallback may emit an object the client cannot decode. Publish error records/events in the contract.
6. **Sending a JSON error object mid-way through an NDJSON stream containing only Event.** The client may not understand the new schema. Use an envelope/union schema from the start.
7. **Sending an error record while claiming the HTTP status changed to 500.** The record is application data; the status remains the committed status.
8. **Using application/json for a stream needing per-element flushing.** The default encoder may collect the Flux into a List before writing an array. Choose NDJSON or SSE for streaming.
9. **Leaving a half-written JSON array after an error.** The client may receive invalid JSON. Design terminal markers or choose record-based framing.
10. **Retrying unconditionally after emitting some records.** Retries can re-emit data and cause duplicates. Use IDs/sequences, replay, and deduplication.
11. **Swallowing errors with onErrorResume(Mono.empty()).** The client may think the stream completed successfully even though data was lost.
12. **Sending exception messages/stack traces to clients.** Easily leaks internal structure or sensitive data. Use stable error codes.
13. **Trying to emit an error event when the client already cancelled.** No downstream remains to receive data; clean up resources.
14. **Using a total timeout on a stream designed to be infinite.** Separate idle timeout, first-event timeout, and lifetime timeout.
15. **Missing heartbeats on long-lived connections.** Proxies or load balancers may close idle connections; consider protocol-appropriate heartbeats.
16. **Not saving checkpoints.** The client does not know where to resume after an error or disconnect. Use event IDs/sequences with clear semantics.
17. **Using beforeCommit to run side effects without returning a publisher.** The framework does not await work detached from the Mono<Void> callback.
18. **Not checking the boolean returned by setStatusCode.** Code may assume status changed while the response had already committed.
19. **Not distinguishing preflight errors from body publisher errors.** The two errors hit different commit timing and require two response policies.
20. **Not testing errors after the first element.** Tests checking only status 200 miss whether error records/events are emitted properly.

## 15. Stream error design checklist

Before releasing a streaming endpoint, establish:

- **Commit boundary:** at what point are status and headers decided?
- **Preflight:** can permissions, parameters, quotas, and source availability be validated before commit?
- **Late error contract:** NDJSON error record, SSE error event, terminal marker, or closing the connection?
- **Schema:** can the client distinguish data, error, and end records?
- **Status:** can HTTP status reflect all errors, or only pre-commit errors?
- **Media type:** is a JSON array truly suitable, or are NDJSON/SSE needed?
- **Fallback:** does onErrorResume emit schema-compliant data?
- **Retry:** is the source replayable? Are IDs/sequences present to prevent data loss or duplication?
- **Cancellation:** does client disconnect cancel upstream and release resources?
- **Timeout:** are idle, first-event, and total lifetime configured separately?
- **Observability:** do logs/metrics include stream ID, correlation ID, last sequence, and terminal signal?
- **Security:** do error payloads avoid stack traces, credentials, and rejected data?
- **Client behavior:** does the client recognize terminal markers, error events, and reconnect policies?
- **Tests:** are there tests for pre-commit errors, errors after several records, SSE error events, and beforeCommit?

## 16. Self-check exercises

**Exercise 1.** The server has already sent status 200 and two NDJSON records. Upstream emits onError. Can the status be changed to 500?  
**Answer:** No. The response is already committed; setStatusCode cannot change the already-sent status.

**Exercise 2.** The server wants to return 503 if the stream source cannot be opened. When should that condition be checked?  
**Answer:** Before creating/starting the response body, such as in Mono<ResponseEntity<Flux<T>>> or a preflight step.

**Exercise 3.** What is beforeCommit used for?  
**Answer:** Registering work to run before the response commits, such as finalizing headers or status. The callback must return Mono<Void> so the framework can manage it.

**Exercise 4.** Does doOnError make the stream continue?  
**Answer:** No. It only observes the error; onError remains a terminal signal.

**Exercise 5.** Does onErrorMap turn an error into a record?  
**Answer:** No. It only transforms the exception. To emit a fallback publisher, use onErrorResume.

**Exercise 6.** If onErrorResume emits an error record in NDJSON after two data records, what is the HTTP status?  
**Answer:** The initially committed status, usually 200. The error record is protocol data.

**Exercise 7.** Why can SSE emit a stream-error event?  
**Answer:** SSE supports event names and data; the server can define a dedicated event to report errors inside the stream.

**Exercise 8.** Why can a JSON array become malformed when an error happens mid-stream?  
**Answer:** The body may lack the closing array bracket or final elements, so it is no longer a valid JSON document.

**Exercise 9.** What risk does retryWhen pose after emitting several events?  
**Answer:** Upstream may re-emit older events, causing duplicates. Replay semantics, IDs/sequences, and deduplication are needed.

**Exercise 10.** Does client cancellation trigger onErrorResume?  
**Answer:** No. Cancellation is a cancel signal; use doOnCancel/doFinally and appropriate cleanup.

**Exercise 11.** Does a JSON record with field status=500 change the HTTP status?  
**Answer:** No. That is merely application data inside the body.

**Exercise 12.** Why are checkpoints or Last-Event-ID needed?  
**Answer:** So clients can reconnect from their last received position, reducing the risk of losing or duplicating events.

## 17. Key takeaways

HTTP status and headers can only be modified before the response commits. In WebFlux, ServerHttpResponse.isCommitted() reports the state; setStatusCode() returns a boolean indicating whether status could be set; beforeCommit() lets you finalize metadata right before sending the response.

Errors occurring before commit can be handled via @RestControllerAdvice or WebExceptionHandler to return statuses such as 400, 403, 503, or 504. Errors occurring after the stream has started cannot change status or replace already-sent body content. doOnError only observes, onErrorMap only transforms exceptions, while onErrorResume can switch to a fallback publisher.

For NDJSON, define an error record; for SSE, define a stream-error event. If the protocol does not support reporting errors inside the body, terminate the connection and let the client recognize the stream is incomplete, then reconnect from a checkpoint if possible. Design status, media types, error schemas, retries, cancellation, and observability as part of the streaming contract.

### References

- Spring Framework, [WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- Spring Framework, [WebFlux Return Values and Reactive Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
- Spring Framework, [WebFlux Streaming and Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework Javadoc, [ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html).
- Spring Framework Javadoc, [ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html).
- Project Reactor, [Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor, [Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- MDN, [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events).
