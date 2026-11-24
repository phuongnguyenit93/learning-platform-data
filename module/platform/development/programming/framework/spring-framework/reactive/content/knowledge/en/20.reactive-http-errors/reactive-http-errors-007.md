# Errors Occurring Before and After a Response Has Been Sent in Spring WebFlux

## 1. Why Does the Timing of an Error Matter?

In a Spring WebFlux application, requests are processed through a reactive pipeline. A controller or functional handler can return a Mono/Flux; data is written incrementally to the HTTP response as the publisher emits signals.

This creates a crucial distinction: errors occurring **before the response is committed** can be turned into a new HTTP error response; errors occurring **after the response has already committed** generally cannot change the already-sent status, headers, or body. The server can only terminate the stream/connection, log, and perform appropriate cleanup.

For example:

- A service throws an error before the controller writes any bytes: the server can still return **500 Internal Server Error** with a JSON error description.
- An SSE endpoint has already sent two events when the publisher emits onError: status **200 OK** and the already-sent events cannot be recalled. The server cannot replace that response with a 500 JSON; the client may observe the stream terminating abnormally.
- An endpoint deliberately turns a business error into an SSE event named error and completes: the status remains 200, yet the client receives an application-level error message.

To be precise, distinguish three milestones:

1. **Request handling starts:** the server receives the request and Spring begins running filters/handlers.
2. **Response committed:** status, headers, cookies, and the first portion of the body are applied/written to the transport. Beyond this milestone, HTTP metadata cannot be changed.
3. **Response completed:** the publisher finishes writing the body and the server closes the response normally.

A response can already be committed while the body is still streaming. Hence the key concept is **committed**, not merely "finished sending the entire body".

## 2. What Is Response Commit?

In WebFlux, **ServerHttpResponse** is the server-side HTTP response abstraction. It allows setting status, headers, cookies, and writing the body reactively.

Important APIs:

| API | Role |
| --- | --- |
| **isCommitted()** | Indicates whether the response has committed |
| **setStatusCode(status)** | Sets HTTP status; returns false if status cannot be changed because response already committed |
| **getHeaders()** | Accesses response headers; changes only take effect before headers are committed |
| **addCookie(cookie)** | Adds a cookie; may throw IllegalStateException if response already committed |
| **beforeCommit(action)** | Registers an action to run right before the response commits |
| **writeWith(body)** | Writes body from a Publisher<DataBuffer> |
| **writeAndFlushWith(body)** | Writes groups of DataBuffers and flushes after each group |
| **setComplete()** | Completes the response, including responses without a body |

### 2.1. What Counts as Committed?

A response typically commits when the framework must send status/headers and begin writing the body to the HTTP server. For streaming responses, committing can happen very early, such as when the first event is flushed.

Several scenarios:

- Controller returns a small JSON object: the response usually commits when the writer starts writing the body.
- Controller returns a Flux with a streaming media type like text/event-stream: each event may be flushed; the response commits as soon as the first event is written.
- Controller returns a bodyless response and calls setComplete(): the response still must commit status/headers.
- A filter or handler explicitly flushes the response: commit can occur before all business logic completes.

Exact timing depends on the message writer, server adapter, and transport. Do not infer it merely from the controller method having returned. Check **response.isCommitted()** at the error-handling point.

### 2.2. After Commit, Status and Headers Cannot Change

Example:

~~~java
boolean changed = exchange.getResponse()
    .setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);

if (!changed) {
    // Response is already committed; status cannot be changed.
}
~~~

If the response has already committed, setStatusCode returns false. Adding a cookie after commit can throw IllegalStateException. An already-sent body cannot be replaced with a JSON error document either.

Do not try to set status 500 after already sending part of a 200 response. That cannot fix the status on the wire and may cause secondary errors.

### 2.3. When Is beforeCommit Used?

**beforeCommit(...)** registers an action that runs right before the response commits. It is useful when adding a final header, correlation ID, or metadata known only during response preparation.

Example:

~~~java
String requestId = "req-42";

exchange.getResponse().beforeCommit(() ->
    Mono.fromRunnable(() ->
        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId)
    )
);
~~~

The action must be properly deferred using Mono.defer, Mono.fromRunnable, or a suitable Publisher. Never modify headers after the response has committed and do not use beforeCommit to try altering a response after body writing has started.

## 3. Errors Before Commit: A New Error Response Can Be Created

When an error occurs before commit, Spring still has the chance to choose status, headers, and body for the response. This is the right situation to:

- Convert exceptions into 4xx/5xx.
- Return JSON or ProblemDetail.
- Add a correlation ID.
- Standardize error codes and messages.
- Record logs and metrics.

Errors can arise in many places:

- Controller throws an exception before returning a Publisher.
- Mono/Flux emits onError before the writer writes the body.
- Reactive service fails before response data exists.
- WebFilter rejects the request or raises an error.
- Handler mapping or argument resolution fails.

Whether the error is synchronous or asynchronous, if the response has not yet committed, error handling can still produce a new response.

### 3.1. Using @ExceptionHandler in a Controller

Example:

~~~java
@RestController
@RequestMapping("/api")
public class OrderController {

    @GetMapping("/orders/{id}")
    public Mono<Order> find(@PathVariable String id) {
        return orderService.findById(id)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(id)
            ));
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
        OrderNotFoundException ex
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested order does not exist."
        );

        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

This is an illustrative snippet, assuming Order, OrderService, and OrderNotFoundException exist. **@ExceptionHandler** handles errors originating from handler methods within controller scope. Across multiple controllers, place handlers in **@RestControllerAdvice**.

The response can use the **Problem Details** format per RFC 9457:

~~~json
{
  "type": "about:blank",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order does not exist.",
  "code": "ORDER_NOT_FOUND"
}
~~~

Extension fields such as code can be added to ProblemDetail's properties. Messages returned to clients should be stable and free of stack traces, SQL, internal paths, or sensitive data.

### 3.2. Using @RestControllerAdvice Application-Wide

~~~java
@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> handleBadInput(
        IllegalArgumentException ex
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "The request contains an invalid value."
        );

        problem.setTitle("Invalid request");
        problem.setProperty("code", "INVALID_INPUT");

        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

Controller advice suits standardizing errors across many endpoints. You can add handlers for business exceptions, validation errors, and unexpected errors.

Do not catch Throwable and turn everything into 400. Classify errors according to contract:

- 400 for invalid request data.
- 401/403 for authentication or access permissions.
- 404 for missing resources.
- 409 for business conflicts.
- 429 for rate limiting.
- 5xx for server-side or dependency errors.

Do not let clients dictate arbitrary statuses by sending exception names or error codes in the request.

### 3.3. ProblemDetail and ResponseEntityExceptionHandler

Spring Framework supports **ProblemDetail**, **ErrorResponse**, and **ErrorResponseException** per RFC 9457. You can extend **ResponseEntityExceptionHandler** in a @ControllerAdvice to handle standard WebFlux exceptions and ErrorResponseException.

With Spring Boot, the property:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

can enable Problem Details configuration for built-in exceptions. When overriding handling for a specific exception, pay attention to ControllerAdvice ordering so your custom handler is selected before the auto-configured handler.

ProblemDetail keeps error responses consistent across endpoints, yet it can still only be written when the response has not committed.

## 4. Errors After Commit: The Response Cannot Be Replaced

Once the response has committed:

- HTTP status has already been sent.
- Headers have already been sent.
- Cookies have already been sent.
- Part or all of the body may have already been transmitted.
- The framework cannot go back and create a new 500 response on the same exchange.

Example of a stream:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: started

event: progress
data: halfway

<publisher emits onError>
<response stream terminates abnormally>
~~~

The client has already received status 200 and two events. If the server tries to change the status to 500, that change cannot overwrite the already-sent status.

Depending on the HTTP version and server runtime, the client may observe:

- Body shorter than Content-Length.
- Chunked response ending without a valid terminal chunk.
- HTTP/2 stream reset.
- Client reporting premature close, incomplete response, or body-read error.
- SSE client receiving the emitted events and then the connection closing.

Not every transport manifests the same exception. Treat this as a post-commit stream/transport failure, not a new error response with a different status.

### 4.1. WebExceptionHandler Cannot Undo a Commit

**WebExceptionHandler** is the exception-handling contract in the WebFlux chain of WebFilter and WebHandler. Its method signature is:

~~~java
Mono<Void> handle(
    ServerWebExchange exchange,
    Throwable ex
);
~~~

Convention:

- Publisher completes normally: the exception is considered handled.
- Publisher emits onError: the exception remains unhandled and propagates onward.

A low-level handler can check:

~~~java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(ex);
}
~~~

When the response has committed, return the error so the chain continues handling/logging per runtime mechanisms. Do not return Mono.empty() just to mask the exception when an error response could not actually be completed.

**ResponseStatusExceptionHandler** can map ResponseStatusException to an HTTP status when the response has not committed. If the response has already committed, the error remains unresolved and propagates.

### 4.2. Spring Boot Has a Default Error Handler

Spring Boot provides a **WebExceptionHandler** to handle errors with default configuration:

- Machine clients typically receive JSON containing error info and status.
- Browsers may receive an HTML error page.
- ErrorAttributes can be customized.
- ErrorWebExceptionHandler can be implemented.
- **AbstractErrorWebExceptionHandler** helps build error handlers using functional routing.

These mechanisms apply to errors that can produce a response. They cannot replace an already-committed body/status. If the default error handler cannot write a response either, the error continues propagating to the server runtime and is recorded by its mechanism.

### 4.3. @ExceptionHandler After Commit

An exception emitted by a publisher returned from a controller can still pass through exception resolution. However, if the response has already committed, the handler cannot write a new response as it would before commit.

If using custom advice/handlers, check response state:

~~~java
@ExceptionHandler(IllegalStateException.class)
public Mono<ResponseEntity<ProblemDetail>> handle(
    IllegalStateException ex,
    ServerWebExchange exchange
) {
    if (exchange.getResponse().isCommitted()) {
        return Mono.error(ex);
    }

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.INTERNAL_SERVER_ERROR,
        "The request could not be completed."
    );

    problem.setTitle("Internal server error");

    return Mono.just(
        ResponseEntity.internalServerError().body(problem)
    );
}
~~~

This is an illustrative snippet. When the response has not committed, the handler returns ProblemDetail. Once committed, the handler lets the exception keep propagating instead of trying to write JSON into an already-sent response.

## 5. Streaming: Errors After the First Event

Streaming is the clearest scenario of post-commit errors. A Flux can emit many elements over a long duration. With streaming media types, the server may flush each element so the client receives it immediately.

SSE example:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.concat(
        Flux.just(
            ServerSentEvent.builder("started")
                .id("1")
                .event("progress")
                .build(),
            ServerSentEvent.builder("halfway")
                .id("2")
                .event("progress")
                .build()
        ),
        Flux.error(
            new IllegalStateException("simulated stream failure")
        )
    );
}
~~~

The first two events can be flushed to the client before the publisher emits an error. When the error happens, the HTTP response already has status 200 and two sent events.

### 5.1. Cannot Send a JSON Error Body Instead of Already-Sent Events

If the client is reading text/event-stream, after two events the server cannot suddenly switch Content-Type to application/problem+json and write a JSON document as a new response. The same HTTP response has only one committed status/header set.

If you want the stream to carry application-level error notifications, define a clear protocol and turn source errors into a final event:

~~~java
public Flux<ServerSentEvent<String>> recoverableEvents() {
    return Flux.concat(
        Flux.just("started", "halfway")
            .map(value -> ServerSentEvent.builder(value)
                .event("progress")
                .build()),
        Flux.<String>error(
            new IllegalStateException("source failed")
        )
    )
    .onErrorResume(ex ->
        Flux.just(
            ServerSentEvent.builder(
                "The stream could not finish. Retry the operation."
            )
            .event("error")
            .build()
        )
    );
}
~~~

In this example, the source error is handled before reaching the HTTP writer. The client receives two progress events, one error event, and then the stream completes normally. The HTTP status remains 200 because the response already committed.

This applies only when the application intentionally designs an error event. It cannot recover from socket, codec, or response-writer errors once writing itself has failed.

### 5.2. Defining a Stream Protocol

With SSE, you can define events:

| Event | Meaning | Client Handling |
| --- | --- | --- |
| **progress** | Work in progress | Update UI/status |
| **result** | Final result available | Save result and close UI |
| **error** | Work ended with a business error | Display message, decide on retry |
| **complete** | Work finished per protocol | Stop tracking |

Do not confuse an application error event with HTTP status 500. An error event is data inside a stream that already has a status; the HTTP status typically keeps its value from commit time.

### 5.3. With NDJSON or Streaming JSON

If the API uses NDJSON, a shared event schema can be defined:

~~~json
{"type":"progress","data":{"percent":50}}
{"type":"error","code":"SOURCE_FAILED","message":"The stream could not finish"}
~~~

Clients read line by line and handle by type. Do not send an arbitrary error JSON object if the initial protocol expects each line to follow another schema.

With a regular JSON array, an error after sending the opening bracket and several elements can leave the body as invalid JSON. If recoverable streams are needed, pick NDJSON/SSE or a framing protocol with an explicit terminating error message.

## 6. Distinguishing Exceptions, Cancellation, and Response Write Errors

Not every abnormal termination is the same kind of error.

| Case | Typical Signal | Meaning |
| --- | --- | --- |
| Business/service failure | onError | Logic or dependency emitted an error |
| Timeout | TimeoutException or equivalent error | An operation exceeded its allowed duration |
| Client disconnect | Cancellation or transport error | Client stopped receiving or closed the connection |
| Response write failure | IOException/transport exception | Server could not write body to the socket |
| Serialization failure | Codec/encoder exception | Data could not be encoded in the media type |
| Application cancellation | SignalType.CANCEL | Subscription cancelled by reactive lifecycle |

### 6.1. Cancellation Is Not onError

When a client closes the connection, the publisher may receive cancellation. This is not necessarily a business exception. Do not try to send an error response to a disconnected client.

You can observe the lifecycle with doFinally:

~~~java
return service.stream()
    .doFinally(signalType -> {
        log.info("Stream finished with signal {}", signalType);
    });
~~~

The signal can be ON_COMPLETE, ON_ERROR, or CANCEL. Use it to clean up resources, stop background tasks, or record metrics. Do not assume doFinally always means the business task succeeded.

### 6.2. Timeouts Before and After Commit

Timeout occurring before commit: the application can convert it into 504 Gateway Timeout or an appropriate status per the API contract.

Timeout occurring after commit: already-sent status and headers cannot change. The stream terminates; the client must detect an incomplete body or receive an error event per protocol.

Place timeouts at the right layer:
- Timeout for database/service connections.
- Timeout for the entire request if determinable up front.
- Timeout for idle streams if hung sources must be detected.
- Heartbeat for SSE if clients/proxies may close idle connections.

Timeouts do not replace cancellation and do not guarantee that every blocking library stops immediately upon subscription cancellation.

### 6.3. Serialization Errors After Emitting Part of the Stream

A Flux may emit a valid first element, and then a later element fails to serialize. Once the response has committed, the server cannot replace the body with error JSON. Therefore:

- Validate/normalize data before feeding it into the stream if cost allows.
- Use DTOs with a stable schema.
- Handle per-element errors if the protocol allows.
- Record metrics for encoding errors.
- Test boundary data and codec errors.

## 7. Designing Error Handling by Response Lifecycle

A practical strategy can be split into phases.

### 7.1. Before Calling the Writer

- Validate the request and access permissions.
- Check required dependencies.
- Fetch metadata needed for status/headers.
- Generate a correlation ID.
- Prepare the response model.
- If an error occurs, convert it into an exception or error response before commit.

### 7.2. Right Before Commit

- Set the final status.
- Set Content-Type, Cache-Control, and other headers.
- Set cookies if needed.
- Register beforeCommit for metadata needed at the final step.
- Do not defer status/header decisions until after streaming begins.

### 7.3. After Commit

- Do not try to change status/headers.
- Log the error with request ID and stream info.
- Stop the data source and release resources when needed.
- If the protocol supports it, send a final event with a clear schema before the publisher completes.
- If the error is at the transport/write layer, let the stream/connection end and provide clients with retry/resume mechanisms.
- Never write stack traces or internal details into the remaining body.

### 7.4. Retries Must Be Safe

Clients may retry when a stream is interrupted, yet the server must determine whether the operation is idempotent. A read-only GET request can usually be retried; an order-creating POST request should not be resent automatically if the client does not know whether the previous transaction committed.

For long-running tasks, consider:
- A Job ID for clients to poll status.
- An idempotency key for creation operations.
- Event IDs and replay/resume for SSE.
- Checkpoints/offsets for streams.
- Checksums or content length to detect partial file downloads.

Do not treat a connection retry as a rollback of an already-executed side effect.

## 8. Complete Example: Pre-Commit and Post-Commit Errors

The example uses **Java 17**, **Spring Boot 3.3.5**, and Maven. It has three endpoints:

- **/api/before-commit**: emits an error immediately; ControllerAdvice returns a 500 ProblemDetail.
- **/api/after-commit**: sends two SSE events and then emits onError; client receives status 200 and the stream terminates abnormally.
- **/api/recovered-stream**: turns the source error into a final error event; stream ends normally per the application protocol.

Structure:

~~~text
webflux-response-error-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/responseerror/
    │   │       ├── ResponseErrorApplication.java
    │   │       ├── FailureController.java
    │   │       └── ApiExceptionAdvice.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/responseerror/
                └── FailureControllerTest.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-response-error-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

Spring Boot parent manages compatible dependency versions. Starter WebFlux provides the reactive server; reactor-test supports StepVerifier in tests.

### 8.2. Application Class

File **ResponseErrorApplication.java**:

~~~java
package com.example.responseerror;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseErrorApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ResponseErrorApplication.class,
            args
        );
    }
}
~~~

### 8.3. Controller

File **FailureController.java**:

~~~java
package com.example.responseerror;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class FailureController {

    @GetMapping("/before-commit")
    public Mono<String> beforeCommit() {
        return Mono.error(
            new IllegalStateException("simulated pre-commit failure")
        );
    }

    @GetMapping(
        value = "/after-commit",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> afterCommit() {
        return Flux.concat(
            Flux.just(
                progress("1", "started"),
                progress("2", "halfway")
            ),
            Flux.<ServerSentEvent<String>>error(
                new IllegalStateException("simulated post-commit failure")
            )
        );
    }

    @GetMapping(
        value = "/recovered-stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> recoveredStream() {
        return Flux.concat(
            Flux.just(
                progress("1", "started"),
                progress("2", "halfway")
            ),
            Flux.<ServerSentEvent<String>>error(
                new IllegalStateException("simulated source failure")
            )
        )
        .onErrorResume(ex ->
            Flux.just(
                ServerSentEvent.builder(
                    "The stream could not finish. Retry the operation."
                )
                .event("error")
                .build()
            )
        );
    }

    private ServerSentEvent<String> progress(
        String id,
        String data
    ) {
        return ServerSentEvent.builder(data)
            .id(id)
            .event("progress")
            .build();
    }
}
~~~

Explanation:

- The before-commit endpoint emits onError before any body exists; advice can produce a ProblemDetail response.
- The after-commit endpoint uses text/event-stream; two progress events are sent before the source emits an error.
- The recovered-stream endpoint catches the source error with onErrorResume and emits a final error event.
- **onErrorResume** here handles errors from the source publisher. If socket/codec writing itself fails, source-level recovery cannot fix that transport error.

### 8.4. ControllerAdvice

File **ApiExceptionAdvice.java**:

~~~java
package com.example.responseerror;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalStateException.class)
    public Mono<ResponseEntity<ProblemDetail>> handleIllegalState(
        IllegalStateException ex,
        ServerWebExchange exchange
    ) {
        if (exchange.getResponse().isCommitted()) {
            return Mono.error(ex);
        }

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "The request could not be completed."
        );

        problem.setTitle("Internal server error");
        problem.setProperty("code", "REQUEST_FAILED");

        return Mono.just(
            ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem)
        );
    }
}
~~~

The key point is checking **isCommitted()**:

- Not yet committed: return ProblemDetail with 500.
- Already committed: return the error so the exception continues propagating; do not attempt to write a second response.

The client message contains no internal exception message. The exception message can still be written to server-side logs with a request ID and proper data protection policies.

### 8.5. application.properties

~~~properties
spring.application.name=webflux-response-error-demo
server.port=8080
logging.level.com.example.responseerror=INFO
~~~

### 8.6. Testing with WebTestClient and StepVerifier

File **FailureControllerTest.java**:

~~~java
package com.example.responseerror;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class FailureControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void mapsFailureBeforeCommitToProblemDetail() {
        client.get()
            .uri("/api/before-commit")
            .exchange()
            .expectStatus().isEqualTo(
                HttpStatus.INTERNAL_SERVER_ERROR
            )
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON
                )
            .expectBody()
            .jsonPath("$.title")
                .isEqualTo("Internal server error")
            .jsonPath("$.status").isEqualTo(500)
            .jsonPath("$.code").isEqualTo("REQUEST_FAILED");
    }

    @Test
    void postCommitFailureTerminatesTheSseBody() {
        FluxExchangeResult<ServerSentEvent<String>> result =
            client.get()
                .uri("/api/after-commit")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM
                    )
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<String>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "started".equals(event.data())
            )
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "halfway".equals(event.data())
            )
            .expectError()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void sourceErrorCanBecomeAnApplicationLevelSseEvent() {
        FluxExchangeResult<ServerSentEvent<String>> result =
            client.get()
                .uri("/api/recovered-stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<String>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "started".equals(event.data())
            )
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "halfway".equals(event.data())
            )
            .expectNextMatches(event ->
                "error".equals(event.event())
                    && event.data().contains("could not finish")
            )
            .verifyComplete();
    }
}
~~~

The first test verifies that an error before commit becomes a 500 Problem Details response. The second test verifies that status 200 is received, two SSE events arrive first, and then the body publisher terminates with an error. The specific transport exception type may differ depending on the HTTP client and server runtime. The third test verifies that a source error is converted into an error event and the stream completes normally.

### 8.7. Running the Application

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Calling the pre-commit error endpoint:

~~~bash
curl -i http://localhost:8080/api/before-commit
~~~

Main response:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
~~~

Body:

~~~json
{
  "type": "about:blank",
  "title": "Internal server error",
  "status": 500,
  "detail": "The request could not be completed.",
  "code": "REQUEST_FAILED"
}
~~~

Calling the post-commit failing stream:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/after-commit
~~~

The client may receive:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

id:1
event:progress
data:started

id:2
event:progress
data:halfway
~~~

After two events, the stream terminates abnormally. Curl may report a transfer error because the body is incomplete; exact details and messages depend on the HTTP version, server, and client.

Calling the stream that converts errors into events:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/recovered-stream
~~~

The body has three events:

~~~text
event:progress
data:started

event:progress
data:halfway

event:error
data:The stream could not finish. Retry the operation.
~~~

In this case the publisher handles the source error and completes normally; status remains 200. The client must understand the error event according to the application's SSE protocol.

## 9. Testing and Observing Errors in Real Environments

### 9.1. Checking Response Commit in Logs

Log the following details:

- Request ID/correlation ID.
- URI and HTTP method.
- Status selected before commit.
- Commit timestamp if instrumented.
- Error type and originating layer.
- Whether the response was already committed.
- Terminal signal: complete, error, or cancel.
- Bytes/events sent if safely measurable.

Never log access tokens, cookies, passwords, sensitive raw request bodies, or full personal data.

### 9.2. Metrics Should Distinguish Two Groups

You can track:

- Errors mapped to 4xx/5xx before commit.
- Errors occurring after commit.
- Cancelled streams.
- Response write failures.
- Pre-commit and post-commit timeouts.
- Client retries and resume success rate.

If you count only HTTP 500s, the application will miss stream failures that committed status 200 before the body broke.

### 9.3. Testing with Real Transport

Mock handler tests can verify response logic, yet post-commit errors also depend on the server adapter and transport. For streams, write integration tests starting a real server and using a real client or WebTestClient on a random port.

Test at least:

1. Error occurring before the first event.
2. Error after the first event.
3. Error after multiple events.
4. Client-initiated cancel.
5. Data-source timeout.
6. Mid-stream element encoding error.
7. Source error converted into an error event.
8. Server shutdown while a stream is active.

Do not claim every HTTP client throws the same exception type when a stream is truncated. Verify the actual behavior of the transport your application uses.

## 10. Common Mistakes

| Symptom / Misconception | Solution |
| --- | --- |
| Changing status to 500 after SSE has already sent events | Cannot change committed status; terminate stream or emit an error event per protocol |
| Writing error JSON after part of the body | Can corrupt the response; design framing/event schema from the start |
| Thinking controller return means the response has finished sending | The publisher can keep emitting data after the method returns |
| Thinking a response commits only when the body finishes | Streaming can commit on the very first event/byte |
| Calling setStatusCode and ignoring its boolean return | Check false, meaning status was not updated because response already committed |
| Adding cookies after commit | Can throw IllegalStateException; add cookies before commit |
| Using beforeCommit to alter headers after body writing | Hook only runs before commit; register before the response commits |
| Custom WebExceptionHandler returning Mono.empty even when unhandled | Completion means handled; if unable to handle, propagate the error |
| Catching only WebExchangeBindException or controller exceptions | Distinguish controller exceptions, WebExceptionHandler, codec/write errors, and cancellation |
| Treating cancellation as a business error | Cancellation is a separate lifecycle signal; clean up via doFinally |
| Using onErrorResume after the socket failed to fix the response | Source recovery only handles source errors; cannot fix transport/write failures |
| Client seeing status 200 and assuming download succeeded | Check body completion, Content-Length, checksum, or terminal event |
| Retrying every POST request when a stream drops | Can repeat side effects; use idempotency keys/job IDs |
| Returning stack traces to clients | Use stable error codes and messages; log details on the server |
| Counting only 5xx statuses to track errors | Post-commit failures can keep status 200; add dedicated metrics for stream failures |
| Testing streams by checking only status 200 | Consume the body publisher and verify complete/error/cancel |
| Assuming an error event means HTTP 500 | Events are data inside the stream; status remains the value at commit time |

## 11. Checklist for Designing Streaming Endpoints

- Determine when the response can commit.
- Set status and headers before the stream emits its first data.
- Handle predictable errors before commit.
- Define an event/error schema if the stream needs to report post-commit errors.
- Do not use a JSON error body to replace an already-started stream.
- Configure appropriate timeouts and cancellation.
- Clean up resources in doFinally or an equivalent lifecycle mechanism.
- Check isCommitted before a custom handler attempts to write an error response.
- If the handler handled the error, return completion; if not, propagate the error.
- Record dedicated logs and metrics for post-commit failures.
- Provide retry/resume or idempotency when business requirements demand it.
- Test against a real HTTP server with the body publisher, not just status assertions.
- Never let error responses leak internal data.
- Track serialization and transport errors separately from business errors.

## 12. Hands-On Exercises

**Exercise 1 — Pre-commit error:** Create an endpoint returning Mono.error immediately. Use @RestControllerAdvice to return a 500 ProblemDetail. Verify status, Content-Type, and body.

**Exercise 2 — Post-commit error:** Create an SSE Flux emitting three events and then onError. Use curl -N to observe the client receiving the events before the stream breaks.

**Exercise 3 — Checking commit:** Register beforeCommit to add X-Request-Id. Log isCommitted before writing the body and after the first event is flushed.

**Exercise 4 — Unchanged status:** Try setStatusCode(500) after commit. Observe the boolean return value and actual response status on the client.

**Exercise 5 — Error event:** Use onErrorResume to turn a source error into a final error event. Write a client handling progress, error, and complete events.

**Exercise 6 — Cancellation:** Connect to SSE and disconnect the client after the second event. Observe doFinally receiving CANCEL and ensure the data source is cleaned up.

**Exercise 7 — Timeout:** Create a slow publisher. Place a timeout before the first event and then after the first event; compare the responses.

**Exercise 8 — Write failure:** Write a test where the client disconnects while the server is writing a large body. Distinguish transport errors from service publisher errors.

**Exercise 9 — ProblemDetail:** Enable spring.webflux.problemdetails.enabled and test standard WebFlux exceptions. Add a custom exception with a stable error code.

**Exercise 10 — Retry:** Create a task with a Job ID. When the stream drops, have the client reconnect to check status or resume from an event ID without creating duplicate tasks.

## 13. Key Takeaways

The critical dividing line in WebFlux is **response commit**. Before commit, Spring can change status, headers, and body to build an error response. After commit, already-sent parts cannot be recalled; errors can only be propagated, logged, cleaned up, or expressed via a final message per a designed streaming protocol.

Use **@ExceptionHandler**, **@RestControllerAdvice**, **WebExceptionHandler**, and **ProblemDetail** for errors that can still become responses. Use **isCommitted()** to check whether the response has crossed the boundary for modifying metadata. For SSE/NDJSON, design explicit error events if post-commit errors must be reported; for file downloads, use checksums, retries, or resume to detect and handle incomplete content.

Do not confuse post-commit errors with pre-commit errors, and do not confuse cancellation with onError. Those two distinctions determine how the server terminates responses and how clients recover.

## 14. References

- Spring Boot Reference — Reactive Web Applications / Error Handling: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework Reference — Reactive Core / Exceptions and WebExceptionHandler: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework Reference — WebFlux Error Responses and Problem Details: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework API — ServerHttpResponse: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Framework API — ReactiveHttpOutputMessage: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html
- Spring Framework API — WebExceptionHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebExceptionHandler.html
- Spring Framework API — ResponseStatusExceptionHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/handler/ResponseStatusExceptionHandler.html
- Spring Framework API — ProblemDetail: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- Reactor Reference Guide — Error Handling and Cancellation: https://projectreactor.io/docs/core/release/reference/
