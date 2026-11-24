# Distinguishing HTTP Protocol Errors from Publisher Stream Errors

In a reactive application using Spring WebFlux, an endpoint may return `Mono<T>` or `Flux<T>`. When handling errors, you must distinguish an **HTTP error response** from a **Publisher terminal error signal**. The two phenomena can be related, but they are not synonymous:

- An HTTP error response is a valid HTTP response with a status such as 400, 404, or 500. The client still receives a status, headers, and possibly an error body.
- A Publisher error is an `onError` signal that terminates a reactive stream. This signal itself carries no HTTP status. Spring can translate the error into an HTTP response if the error is handled before the response is committed.
- A transport error occurs when no HTTP response is received, for example connection refused, timeout, or an unexpectedly closed connection.

In this article, the phrase "HTTP error" refers to a response with a 4xx/5xx status. That is still a valid HTTP response, not a protocol syntax or framing error such as a malformed status line or header.

When testing with `WebTestClient`, you must identify whether you are checking the response status, an error emitted while reading the body Publisher, or a connection failure. Conflating them into a single concept can lead tests to wrongly assume an HTTP 200 always has a successful body or that every `onError` must become an HTTP 500.

## 1. What is an HTTP error response?

An HTTP response has a status code, headers, and optionally a body. The status code describes the processing outcome at the HTTP layer:

| Status family | Meaning | Examples |
|---|---|---|
| 2xx | The request was processed successfully. | 200 OK, 201 Created, 204 No Content. |
| 3xx | The client needs to follow redirection or take further action. | 301 Moved Permanently, 302 Found, 304 Not Modified. |
| 4xx | There is a client-side issue with the request or the requested resource/precondition is invalid. | 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found. |
| 5xx | The server could not fulfill the request due to a server or upstream error. | 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable. |

A 404 response is not a Publisher error. The server sent a valid HTTP response whose status is 404. The client can read the status and error body just like with any other response.

Example:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ITEM_NOT_FOUND",
  "message": "Item does not exist"
}
~~~

In tests, we verify the status and body directly:

~~~java
client.get()
    .uri("/items/999")
    .exchange()
    .expectStatus().isNotFound()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
~~~

`WebTestClient.exchange()` lets you assert 4xx/5xx statuses as part of the response. Unlike `WebClient.retrieve()`, which typically turns error statuses into exceptions by default when reading the response, `WebTestClient` expects you to use `expectStatus()` to verify the status per the API contract.

## 2. What is a Publisher error?

Reactive Streams defines three core signals:

- `onNext(value)`: the Publisher emits an element.
- `onComplete()`: the Publisher finishes normally.
- `onError(error)`: the Publisher terminates with an error.

`onError` is a terminal signal: after emitting `onError`, the Publisher does not emit further `onNext` or `onComplete` signals.

Example:

~~~java
Flux<Integer> numbers = Flux.concat(
    Flux.just(1, 2),
    Flux.error(new IllegalStateException("calculation failed"))
);
~~~

Signal flow:

~~~text
onSubscribe
    |
    v
onNext(1)
    |
    v
onNext(2)
    |
    v
onError(IllegalStateException)
~~~

This Publisher does not produce an HTTP 500 on its own. It simply emits two elements and terminates with an error. When a Publisher is used as a response body in WebFlux, Spring must translate that reactive signal into HTTP behavior appropriate for the current response state.

## 3. How does Spring WebFlux translate a Publisher error into an HTTP response?

The outcome depends on when the error occurs and whether the response has already been committed.

### Error occurring before the response is committed

If the Publisher errors before the server sends status/headers or writes body data that commits the response, Spring WebFlux still has an opportunity to handle the exception. Mechanisms such as `@ExceptionHandler`, `@RestControllerAdvice`, or `WebExceptionHandler` can translate the error into an HTTP response with an appropriate status.

Example controller returning a Mono:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ItemController {

    private final ItemService itemService;

    ItemController(ItemService itemService) {
        this.itemService = itemService;
    }

    @GetMapping("/items/{id}")
    Mono<Item> findById(@PathVariable long id) {
        return itemService.findById(id)
            .switchIfEmpty(Mono.error(new ItemNotFoundException(id)));
    }
}
~~~

Exception handler converting the business error to HTTP 404:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(ItemNotFoundException.class)
    ResponseEntity<ApiError> handleItemNotFound(ItemNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("ITEM_NOT_FOUND", exception.getMessage()));
    }
}

record ApiError(String code, String message) {}
~~~

The service Publisher emits an error, yet Spring handles the error before writing the response. The client ultimately receives an HTTP 404 with an error body.

Test:

~~~java
client.get()
    .uri("/items/999")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
~~~

What the test verifies is the HTTP contract the client receives. It does not need to know whether the service internally used `Mono.error(...)`, threw a synchronous exception, or produced the error through another mechanism.

### Error occurring after the response has been committed

Once the response is committed, the HTTP status and headers can no longer be changed. If the body Publisher emits some elements and then emits `onError`, the server cannot go back to change status 200 to 500 or retract the body already sent.

This situation commonly occurs with streaming responses, such as NDJSON or Server-Sent Events, where data may be flushed incrementally to the client.

Example:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class NumberStreamController {

    @GetMapping(value = "/numbers", produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Integer> numbers() {
        return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("stream failed"))
        );
    }
}
~~~

When the stream begins sending data, the response may already be committed with status 200. Then the Publisher fails. The client may receive the already emitted elements and then encounter an error while reading the remainder. The HTTP layer cannot change the already sent status to 500.

Exact client-side behavior depends on the media type, message writer, connector, and commit timing. With streaming responses, the client may observe an abnormally terminated stream; with some body types buffered before writing, the framework may detect the error earlier and still produce an error response. Therefore, do not draw conclusions based solely on whether the Publisher emitted `onNext`; consider the actual response commitment state.

## 4. Comparison table of error types

| Scenario | Is there an HTTP response? | What does the client observe? | How to test |
|---|---|---|---|
| Controller returns 404 with error body | Yes | Status 404 and error body. | `expectStatus().isNotFound()`, check body. |
| Publisher errors before commit and is mapped by exception handler | Yes | Status chosen by handler, e.g., 400 or 500. | Check status and error body with WebTestClient. |
| Body Publisher errors after response commit | Response started; status/headers are fixed. | May receive partial body, then body stream terminates with error. | Check initial status and use StepVerifier on response body Publisher. |
| Publisher error recovered via onErrorResume | Normal response if recovery succeeds. | Fallback values or replacement data. | Check normal status and body. |
| Connection refused or timeout before receiving response | No. | Exchange fails with transport exception. | Check client-side failure or integration test with server/connector. |

A 500 status is still an HTTP response. An `onError` is still a reactive signal. A connection reset is still a transport error. They may stem from the same incident, yet each must be tested at the proper layer.

## 5. Using onErrorResume to recover a Publisher

If an error can be handled inside the reactive pipeline, you can replace the error with a value or another Publisher before it reaches the HTTP layer.

Example:

~~~java
Flux<Integer> numbers = Flux.concat(
        Flux.just(1, 2),
        Flux.error(new IllegalStateException("temporary failure"))
    )
    .onErrorResume(error -> Flux.just(-1));
~~~

Observed output:

~~~text
onNext(1)
onNext(2)
onNext(-1)
onComplete()
~~~

The original error was handled inside the pipeline. Downstream subscribers do not receive `onError`, receiving the fallback value and `onComplete` instead.

A controller can apply the same pattern:

~~~java
@GetMapping("/numbers/recovered")
Flux<Integer> recoveredNumbers() {
    return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("temporary failure"))
        )
        .onErrorResume(error -> Flux.just(-1));
}
~~~

Test:

~~~java
client.get()
    .uri("/numbers/recovered")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("[1, 2, -1]");
~~~

This response succeeds because the Publisher recovered before Spring completed the response. There is no HTTP error status, and the client receives no Publisher error either.

### Common error-handling operators

| Operator | Behavior |
|---|---|
| `onErrorReturn(value)` | Replaces the error with a fallback value and completes normally. |
| `onErrorResume(error -> publisher)` | Switches to another Publisher to recover or replace the stream. |
| `onErrorMap(error -> mapped)` | Transforms the exception and continues propagating the new error. |
| `doOnError(consumer)` | Observes the error, often for logging/metrics; does not recover from the error. |
| `retry(...)` | Resubscribes on error according to a retry policy. |

Example:

~~~java
return itemService.findById(id)
    .doOnError(error -> log.warn("Cannot load item {}", id, error))
    .onErrorMap(TimeoutException.class,
        error -> new UpstreamUnavailableException("Item service timeout", error));
~~~

`doOnError` does not make the Publisher succeed. `onErrorMap` does not recover either; it only changes the exception type. If the exception is mapped to a domain error and reaches an exception handler, Spring can still map it to an appropriate HTTP response.

Do not use `onErrorResume` to mask every error with a generic default value. Fallbacks must match business meaning and the API contract. If fallback data could mislead clients into thinking an operation succeeded, return an explicit HTTP error response instead of silently substituting data.

## 6. Testing HTTP error statuses with WebTestClient

For an error mapped to an HTTP response, tests should verify both status and error body structure:

~~~java
client.get()
    .uri("/items/999")
    .exchange()
    .expectStatus().isNotFound()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND")
    .jsonPath("$.message").isNotEmpty();
~~~

Other status groups can also be verified:

~~~java
client.get().uri("/validation-error")
    .exchange()
    .expectStatus().isBadRequest();

client.get().uri("/forbidden")
    .exchange()
    .expectStatus().isForbidden();

client.get().uri("/upstream-unavailable")
    .exchange()
    .expectStatus().is5xxServerError();
~~~

Do not check only that a status is 4xx or 5xx if the API defines a specific status. For instance, missing resources should typically return 404, invalid input data 400, and upstream errors 502 or 503 depending on the contract.

## 7. Testing Publisher errors directly with StepVerifier

If the goal is to verify that a service or Publisher emits the right reactive signals, test the Publisher directly with `StepVerifier`. This isolates reactive behavior from HTTP serialization and response commitment.

Example service:

~~~java
import reactor.core.publisher.Flux;

class NumberService {

    Flux<Integer> stream() {
        return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("stream failed"))
        );
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import java.time.Duration;

class NumberServiceTests {

    private final NumberService service = new NumberService();

    @Test
    void emitsValuesThenTerminatesWithError() {
        StepVerifier.create(service.stream())
            .expectNext(1, 2)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && error.getMessage().equals("stream failed"))
            .verify(Duration.ofSeconds(5));
    }
}
~~~

Steps of StepVerifier:

1. Subscribe to the Publisher.
2. Assert emitted elements in order.
3. Assert the terminal signal is `onError` with the expected exception.
4. Call `verify()` to actually execute the scenario and await the terminal signal.

Common expectations:

| API | Purpose |
|---|---|
| `expectNext(value)` | Verifies the next element. |
| `expectNext(a, b)` | Verifies multiple elements in order. |
| `expectNextCount(n)` | Verifies the count of next elements. |
| `expectNextMatches(predicate)` | Verifies an element matches a predicate. |
| `expectComplete()` | Verifies `onComplete`. |
| `expectError()` | Verifies `onError` occurred. |
| `expectError(Class)` | Verifies the exception type. |
| `expectErrorMessage(message)` | Verifies the error message. |
| `expectErrorMatches(predicate)` | Verifies the exception with a predicate. |
| `verify(Duration)` | Runs and sets a wait timeout. |

StepVerifier verifies Publisher signals. It does not check HTTP status, headers, JSON serialization, or connector behavior.

## 8. Testing errors in a response body stream

If an endpoint returns a streaming response, you can assert the status first and then obtain the response body Publisher to verify elements and the terminal error.

Controller:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class StreamController {

    @GetMapping(value = "/stream", produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Integer> stream() {
        return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("stream failed"))
        );
    }
}
~~~

Test with WebTestClient and StepVerifier:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToController;

class StreamControllerTests {

    private final WebTestClient client = bindToController(new StreamController())
        .build();

    @Test
    void responseBodyTerminatesWithErrorAfterStreamingValues() {
        FluxExchangeResult<Integer> result = client.get()
            .uri("/stream")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .returnResult(Integer.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(1, 2)
            .expectError()
            .verify();
    }
}
~~~

This test shows two assertions at two layers:

- `expectStatus().isOk()` verifies the HTTP response began with status 200.
- StepVerifier verifies the body Publisher emitted two values and then terminated with an error.

With a mock WebTestClient binding, the error may be forwarded directly through the response body Publisher. When testing against a real server, an error after response commit may be observed as a body-read failure or abrupt connection close; the exact exception class depends on the connector and client. Thus, if the goal is to verify a Publisher's terminal error, testing the service directly with StepVerifier is more reliable. If the goal is to verify network transfer behavior when a stream fails, use an integration test with a real server and assertions tailored to the connector in use.

If you use `expectBodyList(...)` to collect the entire stream into a list, the body Publisher must complete normally. When it emits `onError`, aggregation fails. For streaming responses where you need to verify individual items and terminal signals, use `returnResult(...)` and StepVerifier on `getResponseBody()`.

## 9. Why can the status be 200 even if the body Publisher errors?

HTTP status and headers are typically written before or alongside sending the body. With streaming responses, the server may send status 200 and start writing the first elements. When the Publisher later emits an error, the status has already been sent and cannot be altered.

Example:

~~~text
Server sends:
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

1
2

Publisher emits onError(...)
~~~

The client already received status 200 and two lines of data. The rest of the body did not complete normally. This is not a 500 response; it is a 200 response whose body stream terminated abnormally.

If an API needs to report a business error inside a stream that has already started, design the body protocol to represent errors as data items, or terminate the stream according to a convention understood by clients. The HTTP status cannot be changed after the response is committed.

For instance, an event stream can use a dedicated event type to describe business errors:

~~~text
event: data
data: {"value": 1}

event: error
data: {"code": "UPSTREAM_FAILED"}
~~~

This is a streaming payload convention, not a new HTTP error status. Clients must understand that event type and handle it per the stream's contract.

## 10. Errors occurring before any response exists

A request can fail before the server returns an HTTP response:

- DNS cannot resolve the hostname.
- TCP connection is refused.
- TLS handshake fails.
- Client times out waiting for connection or response.
- Connection is reset before receiving the status line.

In these cases, there is no status code to check. `expectStatus()` cannot assert 500 if the server never sent a 500 response.

With WebTestClient connected to a real server, exchange failures can be verified via client-layer assertions or test-framework exception assertions:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

WebTestClient client = WebTestClient.bindToServer()
    .baseUrl(unavailableBaseUrl)
    .build();

assertThatThrownBy(() ->
    client.get()
        .uri("/")
        .exchange()
)
    .isInstanceOf(RuntimeException.class);
~~~

In the example, `unavailableBaseUrl` is a test address configured with no listening server. The snippet should be adjusted to match the actual exception type of the client/connector and WebTestClient configuration. Do not lock tests to an internal exception class when the error type depends on the runtime. In integration tests, clearly distinguish whether the target scenario is connection refused, timeout, or mid-response closure.

## 11. Comparing WebTestClient and WebClient on HTTP errors

The two APIs handle responses differently:

| API | Default behavior on receiving 4xx/5xx |
|---|---|
| `WebTestClient.exchange()` | Returns a response spec for asserting status, headers, and body. |
| `WebClient.retrieve().bodyToMono(...)` | By default turns 4xx/5xx statuses into `WebClientResponseException` when the body is read through the retrieve pipeline. |
| `WebClient.exchangeToMono(...)` | Lets you inspect ClientResponse yourself and decide how to handle status/body. |

WebClient example:

~~~java
webClient.get()
    .uri("/items/999")
    .retrieve()
    .bodyToMono(Item.class)
    .onErrorResume(WebClientResponseException.NotFound.class, error -> Mono.empty());
~~~

In this snippet, HTTP 404 is converted by WebClient `retrieve()` into a specialized exception. This is behavior of the WebClient retrieval API, not an indication that the server emitted a Publisher `onError` from the response body. The server simply returned an HTTP 404 response; WebClient chose to represent that status as an exception for the caller.

When using WebTestClient to test endpoints, assert the status directly. When testing client code using WebClient, verify how the client handles the corresponding response status and body.

## 12. Distinguishing request body Publisher errors from response body Publisher errors

A reactive client can also send a request body using a Publisher. If the request body Publisher emits `onError` during transmission, the failure occurs on the client-to-server side:

~~~java
client.post()
    .uri("/imports")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(Flux.concat(
        Flux.just(new ImportLine("A")),
        Flux.error(new IllegalStateException("upload stream failed"))
    ), ImportLine.class)
    .exchange();
~~~

This is a failure while the client produces/sends the request body. The server may have received part of the body, may cancel reading, or may return an error response depending on timing and the connector. You cannot assume the client will receive an HTTP 500.

Conversely, a response body Publisher emitting an error is a server-to-client failure. Identify which Publisher is failing before analyzing logs or writing assertions.

| Data direction | Publisher belongs to | Failure location |
|---|---|---|
| Request body | Client sending request | While encoding or sending the body to the server. |
| Response body | Server returning response | While serializing or streaming the body to the client. |
| Service Publisher | Server-side application logic | While calling dependencies, querying data, or running business logic. |

A Service Publisher error can become a response error if it occurs before commit and is handled by the framework. It can also become a response body stream error if it occurs after commit.

## 13. Choosing error handling in a reactive pipeline

Not every error should become HTTP 500. Classify errors by meaning:

| Error type | Typically suitable handling |
|---|---|
| Invalid input data | Return 400 with controlled validation details. |
| Resource not found | Return 404. |
| Unauthorized access | Return 401 or 403 depending on authentication context. |
| Upstream dependency unavailable | May return 502 or 503 per the API contract. |
| Unexpected programming bug | Let exception handler produce 500 and log thoroughly on the server. |
| Recoverable in-stream error | Use an appropriate fallback with onErrorResume or bounded retry. |
| Error after stream has started | Design a stream-level error convention or accept terminal error; committed status cannot change. |

Example mapping a technical error to a domain error:

~~~java
import java.util.concurrent.TimeoutException;

return upstreamClient.fetchItem(id)
    .onErrorMap(TimeoutException.class,
        error -> new UpstreamUnavailableException(
            "Inventory service timed out",
            error
        ));
~~~

Then an exception handler can map the error:

~~~java
@ExceptionHandler(UpstreamUnavailableException.class)
ResponseEntity<ApiError> handleUpstreamUnavailable(
    UpstreamUnavailableException exception
) {
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .body(new ApiError("UPSTREAM_UNAVAILABLE", exception.getMessage()));
}
~~~

Error translation should preserve the original cause so logs and system observability retain full context. Never include stack traces or internal sensitive information in error bodies sent to clients.

## 14. Common mistakes when writing tests

### Assuming every Publisher error is HTTP 500

A Publisher error can be mapped to 400, 404, 503, or another status; it can also occur after response commit when there is no longer a status to alter. Determine the error timing and exception mapping.

### Asserting only status while ignoring the body stream

With streaming responses, status 200 does not guarantee the body completed normally. If the body Publisher is part of the contract, retrieve the response body Publisher and use StepVerifier to verify elements and the terminal signal.

### Using StepVerifier to verify HTTP status

StepVerifier checks Reactive Streams signals. It does not inspect status, headers, or HTTP serialization. Use WebTestClient for HTTP responses and StepVerifier for Publishers.

### Using WebTestClient to infer Publisher root causes

The client may observe decode or transport errors after a stream is cut off. The client-side exception class is not necessarily the original exception emitted by the server Publisher. If you need to verify the original exception, test the Publisher/service directly with StepVerifier.

### Using doOnError and assuming the error was handled

`doOnError` only observes the error. The Publisher still emits `onError`. To recover, use `onErrorResume`, `onErrorReturn`, or another suitable operator.

### Unbounded retries or business-inappropriate fallbacks

Unbounded retries can hold requests open too long and exhaust resources. Arbitrary fallbacks can cause clients to receive wrong data while believing the call succeeded. Set retry limits, timeouts, and fallback policies according to the business contract.

### Expecting to change status after a stream has sent data

Once the response is committed, status/headers cannot change. If error details must be communicated after that point, represent them in the stream protocol or terminate the stream with an observable error.

## 15. Suggested testing matrix

| Scenario | Primary assertions | Tool |
|---|---|---|
| Resource does not exist | HTTP 404 and error body matching schema. | WebTestClient `expectStatus`, `expectBody`. |
| Validation fails | HTTP 400 and field errors. | WebTestClient + JSONPath. |
| Publisher errors before commit, mapped | Status specified by exception handler. | WebTestClient. |
| Service Publisher emits specific error | Values before error and terminal exception. | StepVerifier. |
| Publisher recovers | Fallback values and `onComplete`. | StepVerifier; WebTestClient for response contract. |
| Streaming response errors after commit | Initial status, received values, and body terminal error. | WebTestClient + StepVerifier. |
| Cannot connect to server | No HTTP status; exchange fails. | WebTestClient with real server/connector. |
| Request body Publisher errors | Failure sending request and server behavior on partial body. | Integration test with real client/server. |

A good test should only assert what the layer under test can observe. HTTP tests do not need to know every internal detail of the service Publisher; Publisher tests do not need to start an HTTP server when the goal is only to verify reactive signals.

## 16. Analysis workflow when a test fails

When a reactive test fails, identify in order:

1. **Was an HTTP response received?** If not, investigate connection, timeout, TLS, or transport.
2. **What is the status code?** If 4xx/5xx was received, it is an HTTP response; check exception mapping and error body.
3. **Is the body a Publisher/stream?** If so, verify the terminal signal with StepVerifier or an appropriate body consumer.
4. **Was the response committed before the error occurred?** If already committed, status cannot change; the error may surface only when the client reads the body.
5. **Was the Publisher error recovered?** Check `onErrorResume`, `onErrorReturn`, retry, and mapping operators.
6. **Is the test checking the right layer?** Use WebTestClient for HTTP, StepVerifier for Publishers, and integration tests for transport/containers.

HTTP status describes the response the server sent. Publisher `onError` describes how a reactive stream terminates. Transport errors describe communication failing to complete at the connection layer. Separating these three layers helps build proper exception handling and write WebFlux tests that accurately reflect what clients or subscribers actually observe.
