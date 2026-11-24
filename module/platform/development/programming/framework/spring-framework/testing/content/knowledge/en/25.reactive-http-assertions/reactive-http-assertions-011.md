# Consuming or Releasing the Body and Related Resources

## Why must a response body have a consumer?

In reactive HTTP testing with WebTestClient, receiving a 200 OK status or expected headers does not mean the response has been completely processed. The body may still contain unread data, an open data stream, or buffers that must be released.

Spring WebFlux processes data using a reactive model. Bodies are typically represented as Publisher, Mono, Flux, or DataBuffer instances. When data arrives over the network or is managed by a reference-counted implementation, reading and cancelling the stream directly affects resource lifecycles.

In tests, clearly choose one of these goals:

- Read and assert the entire body.
- Verify that the response has no body.
- Retrieve the decoded result for inspection with other assertions.
- Consume a multi-element response stream.
- Intentionally discard the body when its content is unneeded, while still releasing resources.
- Read data at the DataBuffer level and take direct responsibility for buffer lifecycles.

The general rule is that every response body must have a clear handling path. If a test only checks status/headers, add a body consumption or release step when required by the API. If a test needs to inspect data, read the body once and reuse the obtained result across assertions.

## Consuming the body in WebTestClient

WebTestClient provides `expectBody`, `expectBodyList`, and `returnResult` APIs to read response bodies in tests. These APIs handle consuming and converting the body to the desired type.

### Reading the body into a specific type

When a response is a JSON object, it can be decoded directly into a DTO:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .returnResult();

OrderResponse body = result.getResponseBody();

assertThat(body).isNotNull();
assertThat(body.id()).isEqualTo(42L);
assertThat(body.status()).isEqualTo("PAID");
~~~

expectBody(OrderResponse.class) reads the body and uses a message codec to convert it into OrderResponse. returnResult() returns EntityExchangeResult<OrderResponse> containing response metadata alongside the decoded body. The test can store the result and run multiple assertions on the object without re-reading the HTTP body.

If you only need to verify JSON without a DTO, you can use the JSON matcher:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 42,
                  "status": "PAID"
                }
                """);
~~~

The json(...) matcher also consumes the body to compare contents. You can combine body assertions within the same BodyContentSpec, but should not call body-reading APIs repeatedly as if the response could be re-read from the start.

### Reading a list or collection

For a JSON array, expectBodyList(...) decodes the body into a list:

~~~java
EntityExchangeResult<List<OrderResponse>> result = webTestClient.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(OrderResponse.class)
        .returnResult();

List<OrderResponse> orders = result.getResponseBody();

assertThat(orders)
        .extracting(OrderResponse::id)
        .containsExactly(101L, 102L);
~~~

Here the test checks both decoded data and element order. If the API does not guarantee order, use order-independent collection assertions matching the contract. Regardless of the assertion style chosen, the body has already been read during the expectBodyList step.

### Retrieving the consumed result with returnResult

returnResult() is useful when you want metadata and the body after WebTestClient performs the reading step:

~~~java
EntityExchangeResult<byte[]> result = webTestClient.get()
        .uri("/api/export")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .returnResult();

byte[] bytes = result.getResponseBody();

assertThat(bytes).isNotEmpty();
assertThat(result.getResponseHeaders())
        .containsKey(HttpHeaders.CONTENT_DISPOSITION);
~~~

In this example, expectBody() reads the response into byte[]; returnResult() returns the read data so the test can check size or file contents. This works well for moderately sized binary responses. If a response is very large or unbounded, consider streaming checks instead of buffering the entire content in memory.

## Responses without a body

Some endpoints return 204 No Content, HEAD, or header-only responses. Tests should verify that the body is genuinely empty:

~~~java
webTestClient.delete()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody()
        .isEmpty();
~~~

expectBody().isEmpty() consumes the body and confirms there is no content. This both checks the HTTP contract and makes clear that the test handled the response body.

If a test only checks status or headers without needing the body, do not stop right after expectStatus() or expectHeader() if the body still needs consumption. Add an appropriate body step, such as expectBody().isEmpty() for responses expected to be empty. If the response is expected to have content, read and verify that content.

## Consuming or discarding the body when using WebClient

WebTestClient is a testing API; WebClient is the reactive HTTP client commonly used in applications. Both share reactive client infrastructure, though their response-handling APIs differ.

With WebClient, retrieve() is suitable when you want to decode the body into a specific type:

~~~java
Mono<OrderResponse> order = webClient.get()
        .uri("/api/orders/42")
        .retrieve()
        .bodyToMono(OrderResponse.class);
~~~

When subscribing to the publisher, the body is read and decoded into OrderResponse. For responses where no content is needed, you can use toBodilessEntity():

~~~java
Mono<ResponseEntity<Void>> deleted = webClient.delete()
        .uri("/api/orders/42")
        .retrieve()
        .toBodilessEntity();
~~~

If you need control over status and response handling, use exchangeToMono(...) or exchangeToFlux(...):

~~~java
Mono<OrderResponse> order = webClient.get()
        .uri("/api/orders/42")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(OrderResponse.class);
            }
            return response.createError();
        });
~~~

The exchangeToMono callback returns a publisher representing response processing work. Once that publisher completes, WebClient checks whether the body was consumed and releases any remaining body if the callback did not read it all. exchangeToFlux follows a similar rule for streams.

This prevents resource leaks when a processing branch only cares about status/headers or reads only part of a response. Nevertheless, if the callback needs body data, decode or consume the body inside the callback and return that publisher; do not hold onto ClientResponse and try reading the body after the callback completes.

### Explicitly releasing an unneeded body

Inside an exchangeToMono callback, if you determine the response content is not needed, you can call releaseBody():

~~~java
Mono<Void> deleteOrder = webClient.delete()
        .uri("/api/orders/42")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.releaseBody();
            }
            return response.createError().then();
        });
~~~

releaseBody() returns Mono<Void> and must be composed into the reactive chain for the release to actually execute. Calling the method without subscribing or composing its publisher does not guarantee the operation runs.

Do not call releaseBody() after the body has already been fully read via bodyToMono(...) or bodyToFlux(...). Choose one clear handling path: decode the body, convert to a bodiless result, or release the unused body.

## Streaming responses: must subscribe and consume the stream

For streaming responses, the body is not collected into a single object. For example, a server may emit multiple events or JSON items over time. In WebTestClient, returnResult(...) can return FluxExchangeResult<T> so the test receives the response body publisher:

~~~java
FluxExchangeResult<ServerSentEvent<Notification>> result =
        webTestClient.get()
                .uri("/api/notifications/stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(new ParameterizedTypeReference<
                        ServerSentEvent<Notification>>() {});

StepVerifier.create(result.getResponseBody())
        .assertNext(event -> {
            assertThat(event.data()).isNotNull();
            assertThat(event.data().message()).isEqualTo("created");
        })
        .assertNext(event ->
                assertThat(event.data().message()).isEqualTo("updated"))
        .thenCancel()
        .verify();
~~~

In the example, returnResult(...) provides a Flux not yet fully consumed by the test. StepVerifier subscribes to getResponseBody() and inspects events. thenCancel() cancels the subscription after the asserted events; this is an intentional action for streams that could otherwise keep emitting indefinitely.

For finite streams, verify completion:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextMatches(item -> item.id() == 1L)
        .expectNextMatches(item -> item.id() == 2L)
        .verifyComplete();
~~~

verifyComplete() proves the publisher terminated normally after the expected items. If a test only inspects a few items of an infinite stream, cancel the subscription explicitly. Do not call subscribe() standalone and abandon the subscription, because the test could exit while the stream remains active.

If you need to limit wait time, configure a timeout on StepVerifier or use verify(Duration) so the test does not hang indefinitely when the server fails to emit data or complete.

## DataBuffer bodies and memory ownership

At the lower layer of WebFlux, data can be represented by DataBuffer. Some implementations, especially Netty-based buffers, use reference counting. When a buffer is retained or discarded, reference count management determines when underlying memory is reclaimed.

Whenever possible, decode the body into a DTO, String, byte[], or application type. Message codecs and the framework handle conversion at a higher level. Work directly with DataBuffer only when you need byte-stream control, data forwarding, or low-level codecs/handlers.

When code takes ownership of a DataBuffer and does not pass it to another component, release it after use:

~~~java
DataBuffer buffer = ...;
try {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);
    process(bytes);
} finally {
    DataBufferUtils.release(buffer);
}
~~~

DataBufferUtils.release(buffer) releases the buffer according to its implementation's mechanism. Using finally ensures the buffer is released even if processing throws an exception.

If you only want to discard buffers from a publisher, you can use the consumer provided by Spring:

~~~java
Flux<DataBuffer> body = ...;

Mono<Void> discard = body
        .doOnNext(DataBufferUtils.releaseConsumer())
        .then();
~~~

This snippet creates a Mono<Void> for the caller to compose into a pipeline or subscribe at the appropriate execution boundary. doOnNext(...) releases each buffer as it is emitted; then() turns the outcome into a completion signal carrying no data. Do not create a detached side subscription outside the main control flow. Compose the consumption step into the caller-managed pipeline, or use a high-level response API with built-in release handling. A publisher should be subscribed to in a controlled manner; stray subscriptions complicate error handling, cancellation, and request lifecycles.

### Do not double-release and do not use a buffer after release

Buffer ownership must be clear:

- A component receiving a buffer for processing must know whether it owns the buffer or only reads it temporarily.
- If passing a buffer downstream for further use, do not release it before downstream finishes.
- Once released, do not continue reading from or writing to that buffer.
- If calling retain() to keep a buffer beyond its current lifecycle, something must be responsible for releasing the retained reference.

Do not blindly call DataBufferUtils.release(...) on every buffer appearing in a pipeline. The framework or an operator may already manage ownership. Release only when your code genuinely owns releasing that buffer.

### Joining multiple buffers with DataBufferUtils.join

DataBufferUtils.join(...) combines incoming buffers into a single composite buffer:

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(dataBufferPublisher);
~~~

The join API manages the component buffers per its contract; the caller receives the composite buffer and must manage the resulting buffer's lifecycle. If the caller holds or reads the composite buffer, release it when done:

~~~java
Mono<byte[]> bytes = DataBufferUtils.join(dataBufferPublisher)
        .map(buffer -> {
            try {
                byte[] content = new byte[buffer.readableByteCount()];
                buffer.read(content);
                return content;
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

Do not manually release individual source buffers after passing them into DataBufferUtils.join(...) unless the API contract for your exact version explicitly requires it. Let the operator manage the input buffers and manage the composite buffer received by the caller.

## Cancellation, errors, and timeouts are also part of the lifecycle

A response stream can end in several ways:

- The Publisher emits all data and completes.
- The Publisher emits an error.
- The consumer explicitly cancels.
- The test times out.

These termination paths must be considered when managing resources. If a test stops reading a stream after one element, cancel the subscription. If an exchangeToMono or exchangeToFlux callback finishes before the body is consumed, WebClient's mechanism releases the remaining body. If code manages DataBuffer directly, ensure complete, error, and cancel branches leave no retained references behind.

A streaming test can verify cancellation using StepVerifier:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

This test confirms the consumer received two elements and cancelled the subscription within a bounded time. If the application performs side effects when a client disconnects, add separate assertions verifying that background work stops or upstream resources close. Client-side cancellation does not automatically prove every external operation stopped; that depends on how the publisher and application propagate cancellation signals.

## Common mistakes

### Asserting only status and forgetting the body

expectStatus() and expectHeader() check response metadata. If the response has a body, the test still needs to read the body or apply appropriate handling to release resources. For responses without content, use expectBody().isEmpty().

### Reading the body multiple times

An HTTP response body is a one-shot stream. Once expectBody(...), expectBodyList(...), or a decoder consumes the body, you cannot assume another matcher can re-read it from the beginning. Decode once, call returnResult(), and reuse the resulting object or byte array across multiple assertions.

### Calling releaseBody and then trying to decode

releaseBody() is for bodies that will not be used. After releasing, you cannot subsequently call bodyToMono(...) to extract that content. Choose either decode or release per processing branch.

### Forgetting to subscribe to the publisher returned by exchangeToMono

WebClient is reactive. Publishers like Mono and Flux are lazy; if not subscribed to or composed into an active chain, neither the request nor the release step may execute.

### Obtaining FluxExchangeResult without consuming the response body

returnResult(...) for streaming returns a publisher. Use StepVerifier or a managed subscriber to read the stream to completion or cancel explicitly. Obtaining FluxExchangeResult alone does not mean data has been consumed.

### Releasing a DataBuffer managed by the framework

Releasing a buffer with wrong ownership can cause downstream code to read an already freed buffer. Identify where ownership begins and ends before adding release calls.

### Buffering huge responses entirely in memory

expectBody() and collection-decoding APIs suit payloads of controllable size. For large files or long streams, use streaming consumption to avoid memory growth proportional to total response size.

## Choosing the API by goal

| Goal | Suitable handling |
| --- | --- |
| Verify JSON or text in WebTestClient | expectBody() then assert contents |
| Decode a single DTO | expectBody(MyDto.class).returnResult() |
| Decode a JSON array | expectBodyList(MyDto.class).returnResult() |
| Inspect a small binary response | expectBody().returnResult() to get byte[] |
| Verify response has no body | expectBody().isEmpty() |
| Read SSE or streaming response | returnResult(...) then consume getResponseBody() with StepVerifier |
| WebClient needs to decode response | retrieve().bodyToMono(...) or bodyToFlux(...) |
| WebClient needs to branch on status/headers | exchangeToMono(...) or exchangeToFlux(...) |
| WebClient does not need response body | toBodilessEntity() or releaseBody() inside appropriate callback |
| Handle low-level byte streams | DataBuffer with ownership rules and DataBufferUtils.release(...) |

## Body testing and management workflow

1. Determine whether the response has a single body, an empty body, or a multi-element stream.
2. Pick a consumption API matching the size and data type: expectBody, expectBodyList, returnResult, or streaming result.
3. Read the body once and reuse the decoded result for assertions.
4. If the body is unneeded, verify an empty body or release the body using the client API.
5. If receiving a Flux or DataBuffer, explicitly manage subscription, cancellation, and ownership.
6. For self-managed buffers, release exactly once when no consumer still needs them.
7. Test complete, error, and cancel branches to ensure resources are not held beyond the request lifecycle.

Consuming the response body is part of reactive HTTP testing, not just fetching data for assertions. When tests read, decode, discard, or cancel the body according to the proper API and ownership rules, they both verify the HTTP contract and keep buffers and related resources strictly bounded.
