# ServerHttpRequestDecorator, ServerHttpResponseDecorator, and DataBuffer Handling in Spring WebFlux

In Spring Boot with **Spring WebFlux**, requests and responses flow through reactive HTTP abstractions. When you need to observe bodies, alter headers, enforce response-writing policies, or integrate web-layer tracing/auditing, the primary tools are **`WebFilter`**, **`ServerWebExchange`**, **`ServerHttpRequestDecorator`**, **`ServerHttpResponseDecorator`**, and **`DataBuffer`**.

These belong to the **reactive web stack**, distinct from `HttpServletRequestWrapper`, `HttpServletResponseWrapper`, and Servlet `Filter` in Spring MVC. A WebFlux request can be processed across multiple callbacks and threads; never treat the request body like an `InputStream` that can be read freely multiple times.

Lesson objectives:

1. Understand **where decorators sit** in the pipeline and how to replace the request/response that downstream handlers actually see.
2. Distinguish **observing**, **reading/consuming**, **transforming**, and **caching/replaying** bodies.
3. Master the **`Flux<DataBuffer>`** contract, pooled-buffer lifecycles, and release rules.
4. Properly override `writeWith` and `writeAndFlushWith` when wrapping responses.
5. Build a runnable and testable **Java 17+ / Spring Boot 3.x** example that measures request/response bytes without losing the body.
6. Recognize when **not** to use decorators; identify data loss, double subscription, memory leaks, and committed-response bugs.

**Design principle:** when you only need to meter traffic or track progress, **never read, retain, or decode the full body**. Prefer `doOnNext` to inspect `DataBuffer` sizes and let the framework retain buffer ownership downstream. Only copy/aggregate bytes when genuinely necessary, with strict size bounds and explicit ownership contracts.

## 1. Where Do Decorators Sit in Spring WebFlux?

A request through Reactor Netty typically follows this model:

~~~text
HTTP Client
    |
    v
Reactor Netty HTTP server
    |
    v
ServerWebExchange
    |-- ServerHttpRequest: URL, headers, cookies, Flux<DataBuffer> body
    |-- ServerHttpResponse: status, headers, writes response DataBuffers
    |
    v
WebFilter chain
    |
    +-- construct ServerHttpRequestDecorator
    +-- construct ServerHttpResponseDecorator
    +-- exchange.mutate().request(...).response(...).build()
    |
    v
DispatcherHandler
    |
    +-- HandlerMapping / HandlerAdapter
    +-- @RestController or functional handler
    +-- HttpMessageReader / Decoder reads request body
    +-- HttpMessageWriter / Encoder writes response body
    |
    v
HTTP response to client
~~~

`ServerWebExchange` represents the request/response pair of a reactive HTTP exchange. `WebFilter#filter(ServerWebExchange, WebFilterChain)` can pass a **decorated exchange** down the chain.

**Crucial point:** creating decorators is not enough. You must pass them downstream via a mutated exchange:

~~~java
ServerWebExchange decorated = exchange.mutate()
        .request(decoratedRequest)
        .response(decoratedResponse)
        .build();

return chain.filter(decorated);
~~~

This is a fragment: `decoratedRequest` and `decoratedResponse` must be constructed beforehand. If you still pass the original `exchange` to `chain.filter(exchange)`, downstream handlers will not see the new decorators.

### 1.1. How Does WebFilter Differ from HandlerFilterFunction?

- `WebFilter` wraps processing at the **reactive web application** level, before handler selection. It fits tracing, authentication/security integration, HTTP policies, and request/response wrapping.
- `HandlerFilterFunction` belongs to **functional endpoint routing** and applies to specific HandlerFunctions/RouterFunctions.
- Spring MVC's `HandlerInterceptor` is a separate mechanism on the Servlet stack; never expect it to stand in for WebFilter on Reactor Netty.

A filter can short-circuit a request without calling `chain.filter(...)`. In that case, a created response decorator does not automatically guarantee a body is written; the code must complete the response via the appropriate reactive API.

## 2. How Does ServerHttpRequestDecorator Work?

`org.springframework.http.server.reactive.ServerHttpRequestDecorator` wraps a `ServerHttpRequest`. It delegates all methods to the underlying request except those you override.

Common customization points:

| Method | Purpose |
|---|---|
| `getBody()` | Wrap the request body data publisher |
| `getHeaders()` | Supply an adjusted headers view, kept consistent with the body |
| `getURI()` | Alter the URI view if truly required by design |
| `getMethod()` | Alter method info through supported mechanisms, very rarely needed |
| `getDelegate()` | Access the wrapped underlying request |

A request decorator **does not imply copying the body**. If `getBody()` returns the underlying publisher directly, consumption still follows the semantics of an HTTP connection publisher: it normally streams from the network and must not be casually subscribed to twice.

### 2.1. Observing Without Mutating the Body

Example counting bytes passing through the body as downstream reads:

~~~java
AtomicLong inboundBytes = new AtomicLong();

ServerHttpRequest request = new ServerHttpRequestDecorator(
        exchange.getRequest()) {

    @Override
    public Flux<DataBuffer> getBody() {
        return super.getBody()
                .doOnNext(buffer ->
                        inboundBytes.addAndGet(
                                buffer.readableByteCount()));
    }
};
~~~

This is a fragment requiring imports for `AtomicLong`, `ServerHttpRequest`, `ServerHttpRequestDecorator`, `Flux`, and `DataBuffer`, plus the `exchange` variable. `readableByteCount()` only inspects **how many readable bytes exist**; it does not consume bytes or advance the read index.

`doOnNext` executes when the publisher actually emits a DataBuffer to its subscriber. If the route never reads the body, the counter stays 0. This count measures bytes **observed flowing through the publisher**, not proof that all bytes were successfully parsed by the app or that the client finished sending before cancelling.

### 2.2. Why Can Reading Directly Lose the Body?

A dangerous pattern:

~~~java
return super.getBody().doOnNext(buffer -> {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);  // Consumes readable bytes.
    logDebugLength(bytes.length);
});
~~~

This is an **illustrative broken fragment**, never to be used as-is. `DataBuffer.read(byte[])` advances the buffer's read position. If that same buffer then passes to the JSON decoder, downstream receives an empty or truncated body.

If your goal is solely measuring size, use `readableByteCount()`. If you must inspect content without losing the body, establish an explicit **copy or replay** strategy respecting ownership, max size, charsets, data privacy, and cancellation.

## 3. How Does ServerHttpResponseDecorator Work?

`org.springframework.http.server.reactive.ServerHttpResponseDecorator` wraps a `ServerHttpResponse`. It can observe when the response body is written via a reactive writer, or adjust writing within contract limits.

Common hooks:

- `writeWith(Publisher<? extends DataBuffer> body)`: writes a DataBuffer publisher.
- `writeAndFlushWith(Publisher<? extends Publisher<? extends DataBuffer>> body)`: writes nested publishers, flushing per inner publisher as supported by the implementation.
- `setComplete()`: marks the response complete with no body.
- `beforeCommit(Supplier<? extends Mono<Void>> action)`: registers a pre-commit callback via the response implementation.
- `getHeaders()`, `setStatusCode(...)`: access/modify metadata before the response commits.

**Not every response goes through `writeWith` alone.** Streaming or specialized writers may call `writeAndFlushWith`; bodyless responses may use `setComplete`. Mechanisms like zero-copy file transfers can use separate write paths. Hence, a decorator overriding only `writeWith` **is not a meter for every wire byte**.

### 3.1. Counting Bytes by Wrapping the Publisher

~~~java
AtomicLong outboundBytes = new AtomicLong();

ServerHttpResponse response = new ServerHttpResponseDecorator(
        exchange.getResponse()) {

    @Override
    public Mono<Void> writeWith(
            Publisher<? extends DataBuffer> body) {
        return super.writeWith(
                Flux.from(body)
                    .doOnNext(buffer ->
                            outboundBytes.addAndGet(
                                    buffer.readableByteCount()))
        );
    }
};
~~~

This fragment assumes corresponding imports. The code **does not self-subscribe** to `body`; it passes the operator-decorated publisher down to `super.writeWith`. Never call `body.subscribe(...)` to log and then `super.writeWith(body)`: an HTTP body publisher may not be re-readable and double subscription can break the flow.

The counter reflects **bytes emitted through the hook**; it does not confirm kernel writes, gateway receipt, or full client reads. Under cancellation, network errors, or specialized writers, observed values may differ from bytes delivered to the client.

### 3.2. writeAndFlushWith Must Be Handled for Streaming Observation

For streaming data, the response may use nested publishers:

~~~java
@Override
public Mono<Void> writeAndFlushWith(
        Publisher<? extends Publisher<? extends DataBuffer>> body) {
    return super.writeAndFlushWith(
            Flux.from(body)
                .map(part -> Flux.from(part)
                    .doOnNext(buffer ->
                            outboundBytes.addAndGet(
                                    buffer.readableByteCount())))
    );
}
~~~

This fragment belongs inside the same `ServerHttpResponseDecorator` holding `outboundBytes`. It wraps each inner publisher while **preserving group structure and flushing**; it does not collapse all parts into a single large byte array. Blindly flattening with `Flux.from(body).flatMap(...)` can disrupt chunk flushing and ordering.

**Never write twice.** `writeWith` and `writeAndFlushWith` are entry points chosen by the framework depending on how the response is written. Measure inside whichever entry point is invoked—never call both from application code "just to be safe."

## 4. DataBuffer Represents Streaming Chunks, Not a Single String

`org.springframework.core.io.buffer.DataBuffer` is Spring's byte-buffer abstraction. A body can arrive across multiple DataBuffers:

~~~text
POST /api/echo
      |
      v
Flux<DataBuffer>
   |-- DataBuffer #1: 120 bytes
   |-- DataBuffer #2: 256 bytes
   |-- DataBuffer #3: 76 bytes
      |
      v
Decoder (may aggregate/parse)
      |
      v
Java DTO
~~~

Chunk counts and sizes are purely illustrative; **there is no guarantee each chunk aligns with a TCP packet**, a JSON field, an HTTP chunk, or an NDJSON line.

Key APIs and utilities:

| API | Effect | Notes |
|---|---|---|
| `readableByteCount()` | Check how many readable bytes remain | Non-consuming |
| `read(byte[])` | Read bytes into a byte array | Advances read position |
| `DataBufferUtils.join(...)` | Aggregate buffers into one DataBuffer | Must be size-bounded for untrusted sources |
| `DataBufferUtils.release(...)` | Release when owning a pooled buffer | Avoid leaks or double-release |
| `DataBufferUtils.retain(...)` | Increment reference count when appropriate | Must pair with release |
| `DataBufferUtils.write(...)` | Stream DataBuffers to a destination | Review overloads/lifecycle carefully |
| `doOnDiscard(...)` | Cleanup hook for buffers discarded by operators | Not a catch-all solution for every leak |

On Reactor Netty, buffers may be backed by Netty pooled/direct memory. Memory leaks can manifest in **direct memory**, not just Java heap.

### 4.1. Ownership Rules

A practical question when writing custom filters: **"Which code owns this DataBuffer right now?"**

- If you only run `doOnNext(buffer -> meter.add(...))` and pass the buffer **unchanged** downstream: do not release it in the observation callback.
- If you consume the buffer yourself and **do not forward it** downstream: you must release it per API contract.
- If you call `DataBufferUtils.join` and finish using the resulting buffer: release the joined buffer once your ownership ends.
- If you allocate a new buffer from copied bytes: design clear downstream ownership for that new buffer.
- On cancellation, error, or operator discard: ensure proper cleanup without double-releasing.

**Avoid "sprinkling releases everywhere just in case."** Releasing in the wrong place causes downstream to read freed buffers, producing hard-to-reproduce corruption bugs.

## 5. Complete Example: WebFilter Using Both Decorators to Measure Bytes

This example uses **Spring Boot 3.x**, **Java 17+**, **Spring WebFlux**, and default Reactor Netty. Use a Spring Boot project with plugins and dependency management already configured.

In `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Do not add `spring-boot-starter-web` to this demo project: when both Web MVC and WebFlux are on the classpath, Spring Boot normally infers Servlet MVC by default. This lesson requires a **Reactive WebFlux server**.

File **src/main/java/demo/decorator/DecoratorDemoApplication.java**:

~~~java
package demo.decorator;

import java.util.concurrent.atomic.AtomicLong;

import org.reactivestreams.Publisher;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DecoratorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DecoratorDemoApplication.class, args);
    }
}

record Note(String message) {
}

@Component
class BodyMeterFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        AtomicLong requestBytes = new AtomicLong();
        AtomicLong emittedResponseBytes = new AtomicLong();

        ServerHttpRequest decoratedRequest =
                new ServerHttpRequestDecorator(exchange.getRequest()) {

            @Override
            public Flux<DataBuffer> getBody() {
                return super.getBody()
                        .doOnNext(buffer -> requestBytes.addAndGet(
                                buffer.readableByteCount()));
            }
        };

        ServerHttpResponse decoratedResponse =
                new ServerHttpResponseDecorator(exchange.getResponse()) {

            @Override
            public Mono<Void> writeWith(
                    Publisher<? extends DataBuffer> body) {

                return super.writeWith(
                        Flux.from(body)
                            .doOnNext(buffer ->
                                emittedResponseBytes.addAndGet(
                                    buffer.readableByteCount())));
            }

            @Override
            public Mono<Void> writeAndFlushWith(
                    Publisher<? extends Publisher<? extends DataBuffer>>
                            body) {

                return super.writeAndFlushWith(
                        Flux.from(body)
                            .map(part -> Flux.from(part)
                                .doOnNext(buffer ->
                                    emittedResponseBytes.addAndGet(
                                        buffer.readableByteCount()))));
            }
        };

        // Simple test marker; must be added before response commits.
        decoratedResponse.getHeaders().set("X-Body-Meter", "on");

        ServerWebExchange decoratedExchange = exchange.mutate()
                .request(decoratedRequest)
                .response(decoratedResponse)
                .build();

        return chain.filter(decoratedExchange)
                .doFinally(signal -> System.out.printf(
                        "meter: request=%d responseEmitted=%d signal=%s%n",
                        requestBytes.get(),
                        emittedResponseBytes.get(),
                        signal));
    }
}

@RestController
class DecoratorDemoController {

    @PostMapping(
            path = "/demo/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Note> echo(@RequestBody Mono<Note> input) {
        return input;
    }

    @GetMapping(
            path = "/demo/ping",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    Mono<String> ping() {
        return Mono.just("pong");
    }
}
~~~

### 5.1. Why Does This Example Preserve the Body?

1. `getBody()` only attaches `doOnNext` to the underlying publisher; it **never calls `read(byte[])`**, retains buffers, subscribes independently, or releases buffers.
2. `writeWith(...)` and `writeAndFlushWith(...)` pass the instrumented publisher to `super`. No bytes are copied or replaced.
3. `exchange.mutate()` passes both decorators to downstream filters and handlers.
4. `AtomicLong` tracks observed bytes per **individual filter invocation**, rather than using a static field that mixes concurrent requests.
5. `doFinally` prints counts when the reactive chain terminates with complete, error, or cancel. It reports **chain termination signals**, not a guarantee that all bytes reached the client or received a TCP ACK.
6. The `X-Body-Meter: on` header is a marker to test that the filter ran. In real systems, never use a custom header as security proof or anti-spoofing control.

**Important note:** byte counts are not promised to match exact network wire traffic. Compression, frame/chunk overhead, transfer encoding, zero-copy, and specialized writers can make hook-emitted bytes differ from wire bytes. For bodyless responses, the emitted counter can be 0.

### 5.2. Running and Calling the API

From the project directory containing the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows, you can use `gradlew.bat bootRun`. Once Reactor Netty listens on default port 8080:

~~~bash
curl -i http://localhost:8080/demo/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"message":"hello"}'
~~~

Expect HTTP status **200**, response header `X-Body-Meter: on`, and JSON equivalent to:

~~~json
{"message":"hello"}
~~~

Call the bodyless endpoint:

~~~bash
curl -i http://localhost:8080/demo/ping
~~~

Body is:

~~~text
pong
~~~

The console will show lines starting with `meter: request=... responseEmitted=... signal=...`, though **no fixed numbers are guaranteed**: DataBuffer chunking, response serialization, and cancellation timing vary by client and runtime. For `GET /demo/ping`, the request body is normally empty so observed bytes through `getBody()` can be 0.

### 5.3. What If the Client Sends No Body?

If WebFlux never subscribes to the request body because the handler does not read it, `getBody()` may emit zero buffers. That does not break the filter: `requestBytes` measures **bytes consumed downstream through the decorator**, not bytes a client might have sent at a lower transport layer.

Never force a body subscription just to make the counter match `Content-Length`. Remember that `Content-Length` can be absent, untrusted, or differ from post-transformation payload size.

## 6. Testing WebFilter with WebTestClient

In the same project, add `spring-boot-starter-test`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Create **src/test/java/demo/decorator/DecoratorDemoApplicationTest.java**:

~~~java
package demo.decorator;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class DecoratorDemoApplicationTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void requestAndResponseRemainReadable() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .build();

        client.post()
              .uri("/demo/echo")
              .contentType(MediaType.APPLICATION_JSON)
              .accept(MediaType.APPLICATION_JSON)
              .bodyValue(Map.of("message", "hello"))
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals("X-Body-Meter", "on")
              .expectBody()
              .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void emptyRequestBodyDoesNotBreakResponse() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .build();

        client.get()
              .uri("/demo/ping")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals("X-Body-Meter", "on")
              .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

In this example, `WebTestClient` is imported from **`org.springframework.test.web.reactive.server.WebTestClient`**. `bindToApplicationContext(...)` builds an in-process client wired to the WebFlux infrastructure without requiring an auto-injected HTTP client or opening a real TCP server. The tests verify both that the filter runs **and** that the body still decodes and encodes normally.

Run:

~~~bash
./gradlew test
~~~

The tests do not assert exact byte counts, since the goal is proving **no body corruption**. To verify network-level HTTP behavior, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with a WebTestClient/HTTP client bound to the real port; in-process tests do not replace Reactor Netty TCP/TLS tests.

## 7. Scenarios That Truly Require Reading or Transforming the Body

Observing byte counts is not the same as reading content. Modifying JSON or verifying/adding an HMAC signature is considerably harder:

1. Request publishers are typically **designed for single consumption**. Never subscribe to the body in a filter and expect the controller to read it again.
2. Inspecting the full body normally requires **aggregating** buffers. You must enforce limits and account for large payloads or streaming.
3. If reading a buffer advances its read index, you must create a fresh DataBuffer publisher containing the content for downstream.
4. When changing body length, update `Content-Length` or `Transfer-Encoding`; never leave stale length headers.
5. Charset, compression, and content type must match the replacement bytes.
6. When allocating new buffers, manage ownership/release across completion, errors, and cancellation.
7. Never buffer entire large file uploads or NDJSON streams when streaming processing is intended.
8. Security and tracing should not rely on storing entire sensitive bodies.

### 7.1. Bounded Aggregation Example: Release After Reading

Illustrative fragment for a utility that **copies a small body into a byte array**. This is a bounded aggregation helper, **not** a complete request decorator:

~~~java
static Mono<byte[]> copySmallBody(Flux<DataBuffer> source) {
    int maxBytes = 64 * 1024;

    return DataBufferUtils.join(source, maxBytes)
            .map(joined -> {
                try {
                    byte[] result =
                            new byte[joined.readableByteCount()];
                    joined.read(result);
                    return result;
                } finally {
                    DataBufferUtils.release(joined);
                }
            });
}
~~~

To use this fragment, import `DataBuffer`, `DataBufferUtils`, `Flux`, and `Mono`. `DataBufferUtils.join(source, maxBytes)` caps joined bytes. When exceeding the limit, it emits `DataBufferLimitException` instead of buffering unboundedly; design an appropriate error policy.

On the success path, the code copies bytes into an independent array and **releases the joined buffer in `finally`**. This guarantees no pooled DataBuffer is held once the `byte[]` is extracted. The returned `Mono` completes empty if upstream is empty; endpoints may need explicit empty-body handling per contract.

**Never call this utility and then return `chain.filter(exchange)` with the original request:** the body has already been consumed. If downstream genuinely needs to read it again, build a new `ServerHttpRequestDecorator` whose `getBody()` emits **fresh buffers wrapping the copied bytes**, pass it via `exchange.mutate()`, and verify headers, limits, and cancellation. Add dedicated integration tests for small bodies, large bodies, empty bodies, decode errors, and client cancellation.

### 7.2. Replaying a Byte Array Must Create Fresh DataBuffers per Subscription

Once you own an independent `byte[] bytes`, an illustrative replay publisher fragment:

~~~java
Flux<DataBuffer> replay = Flux.defer(() ->
        Flux.just(exchange.getResponse()
                .bufferFactory()
                .wrap(bytes)));
~~~

This is a fragment assuming `bytes` and `exchange` are in scope. `Flux.defer` creates a fresh DataBuffer wrapper on each subscription instead of re-emitting **the same pooled DataBuffer that was already read or released**. Using the exchange's buffer factory here merely illustrates creating a DataBuffer; production code should verify the appropriate factory, ownership, and framework release behavior.

**Never apply unboundedly:** replay holds the entire `byte[]` in memory until the request/chain drops references, so enforce size and lifetime bounds. Likewise, if the body itself was modified, update request headers accordingly before passing to the decoder.

## 8. Adjusting Content-Length and Content-Type When Transforming Requests

If a filter changes a 20-byte body into 50 bytes while leaving `Content-Length: 20`, downstream may read a truncated payload, hang waiting, or misparse the body. With content encoding/compression, adjusting length alone is still insufficient.

You can provide an updated header view via `ServerHttpRequestDecorator#getHeaders()`, keeping everything consistent:

- `Content-Length` must match the new byte length **if** declaring a fixed length.
- If total length is unknown because the request/response streams, never fabricate `Content-Length`.
- If converting JSON → text or vice versa, update `Content-Type` to match.
- If transfer encoding or content encoding applies, understand transport mechanics before modifying headers.
- For signature verification, preserve exact canonical bytes and signing-scope rules.
- Never alter headers such as `Authorization` or `X-Forwarded-*` arbitrarily, as they carry security and proxy trust-boundary semantics.

For request headers inside a decorator, avoid mutating an immutable or shared collection from the original request. Create an appropriate copy and change only justified headers. For simpler path, query, or header edits without body changes, prefer `ServerHttpRequest.mutate()`; when overriding body reading is necessary, a decorator is the direct extension point.

## 9. DataBufferLimitException and Memory Limits

`DataBufferLimitException` can occur when a codec or operation like `DataBufferUtils.join` exceeds the permitted aggregation byte limit.

For example, Spring Boot WebFlux offers:

~~~yaml
spring:
  codec:
    max-in-memory-size: 256KB
~~~

This illustrates a limit for Boot-configured default codecs, **not a global cap on total HTTP request size**. Custom joins/decoders may use different limits; to protect all requests, combine proxy/ingress, server, multipart, upload, and concurrency limits.

Key rules:

- Do not raise `max-in-memory-size` to tens of megabytes merely to silence errors.
- Avoid unbounded `DataBufferUtils.join(body)` on untrusted inputs.
- Never decode entire file uploads or NDJSON streams into one giant `String` or `byte[]`.
- Account for concurrent requests and container memory budgets.
- Never assume `DataBufferLimitException` always maps to HTTP 413; actual status depends on where it occurs and error handling.
- Aggregation errors in `WebClient` responses differ from server request decoding errors; configure the right client/server codec.

A WebFilter that only counts `readableByteCount()` as in the main example **performs no buffer aggregation**, carrying far lower risk than filters that join entire request bodies.

## 10. Response Decorators and Commit Timing

A response is **committed** once status/headers have been sent or can no longer be altered as before. `ServerHttpResponse#beforeCommit(...)` lets you register a callback invoked prior to commit where supported by the implementation.

Illustrative fragment registering a pre-commit callback:

~~~java
exchange.getResponse().beforeCommit(() -> {
    if (!exchange.getResponse().isCommitted()) {
        exchange.getResponse().getHeaders()
                .add("X-Trace-Layer", "webflux");
    }
    return Mono.empty();
});
~~~

This is a fragment unused in the runnable demo; import `Mono`. When a filter knows from the start that a header is needed, a simpler approach is updating `getHeaders()` **before** `chain.filter(...)`, as shown with `X-Body-Meter` in the demo.

Never arbitrarily set response status/body inside `doFinally`: by then, the response may already be completed, errored, or cancelled. `doFinally` is for metrics and cleanup, not modifying the HTTP body.

### 10.1. Not All Responses Take the Same Write Path

A response may:

- Call `writeWith` to send a DataBuffer stream.
- Call `writeAndFlushWith` for flushable stream batches.
- Call `setComplete` when there is no body, e.g., `204 No Content`.
- Use a specialized writer or zero-copy file transfer that bypasses the hooks you overrode.
- Be aborted/cancelled before body completion.

Therefore, never claim a simple response decorator is an **exact wire-byte meter** for every case. For accurate network-level byte metrics, combine telemetry from Netty, load balancers, proxies, and observability systems.

## 11. Interaction with Spring Security and WebFilter Ordering

In WebFlux reactive security, Spring Security uses a **reactive WebFilter chain**, not the Servlet `FilterChainProxy` execution model of Spring MVC.

Filters can be ordered by the framework or appropriate annotations/configuration. With multiple filters:

~~~text
Outer filter: before
   Security/filter: before
      Controller / functional handler
   Security/filter: after
Outer filter: after
~~~

This is a high-level flow. In reactive pipelines, "before/after" corresponds to subscription, completion, error, or cancellation signals—not simply line-by-line Java execution order when assembling the `Mono`.

If security rejects a request before a body-metering filter or controller runs, the request byte count may be partial or 0. Never self-subscribe to "capture all bytes" if the HTTP body is not read by security or the handler.

**Where should logging/inspection sit?** Consider authentication, authorization, PII, request size, and filter ordering. Never log raw credentials, tokens, cookies, passwords, private keys, or uploaded files. Having access to raw body bytes in a filter does not grant permission to persist them.

## 12. Common Pitfalls When Handling DataBuffers Manually

| Mistake | Consequence | Fix |
|---|---|---|
| `getBody().subscribe(...)` inside WebFilter | Consumes body independently; downstream starves | Compose into `chain.filter`, never self-subscribe |
| `buffer.read(bytes)` then pass same buffer downstream | Decoder sees empty or truncated body | Observe size only, or bounded copy + replay |
| Calling `DataBufferUtils.release` on observed-only buffers | Downstream reads already-freed buffer | Release only when you hold actual ownership |
| Not releasing joined buffer from `join` | Leaks pooled/direct memory | `try/finally` release once done |
| Caching a `DataBuffer` across requests/subscriptions | Double use/release, data corruption | Store bounded `byte[]` and wrap fresh buffer per subscription |
| `join` entire large upload/file | Memory spike, `DataBufferLimitException`/OOM | Stream via multipart/`FilePart.transferTo` |
| Overriding only `writeWith` | Misses streams using `writeAndFlushWith` | Hook the appropriate APIs in use |
| Order-unaware `flatMap` on inner body publishers | Can reorder chunks or break flush boundaries | Preserve inner publishers and ordering when decorating |
| Changing body without updating headers | `Content-Length`/`Content-Type` mismatch | Keep headers synchronized with actual bytes |
| Writing response in `doFinally` | Response may already be committed | Use `beforeCommit` or set before chain |
| Logging full bodies to debug | Sensitive data leak and extra load | Log metadata/size only with controlled sampling |
| Using Servlet wrappers on Reactor Netty WebFlux | Wrong stack | Use reactive `ServerHttpRequest`/`Response` decorators |

### 12.1. What Happens When Reading the Body Twice?

A network-backed request body is typically not a collection replayable at will. If a filter's subscription consumes the bytes first, the second subscription may receive nothing or fail depending on the implementation. Thus, **never promise `getBody()` is re-readable merely because its return type is `Flux`**.

True multi-consumer support requires explicit caching/replay at a clear boundary, size limits, empty-body handling, cancellation, and lifecycle management—never slapping `cache()` blindly onto a `Flux` of pooled `DataBuffer`s.

### 12.2. Does doOnDiscard Prevent Every Buffer Leak?

No. When a reactive operator explicitly drops a `DataBuffer`, `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` can be attached **where data ownership exists**. Yet if the buffer is still used downstream or released elsewhere, adding `doOnDiscard` can cause a double-release. Understand operator semantics and test cancellation/error paths.

### 12.3. Why Might Callback Byte Counts Differ from Content-Length?

- The request may be cancelled or blocked by a filter before the decoder reads all bytes.
- The request body publisher chunks data into multiple `DataBuffer`s at runtime regardless of HTTP headers.
- Compression/content coding can make wire bytes differ from decoded application bytes.
- `Transfer-Encoding`/chunk framing overhead is not part of `DataBuffer` body payloads.
- HTTP responses may use specialized writers or streams not fully observed by the filter.
- `Content-Length` can be absent in chunked/streaming transfers or untrusted from clients.

Accordingly, distinguish **declared content length**, **bytes emitted through publisher**, and **actual network bytes** in metric names.

## 13. When Should You Use a Different Approach?

Do not force every requirement into a custom WebFilter decorator:

- **Only need HTTP request latency/status:** prefer built-in observability/Micrometer/Actuator or tracing; add a custom filter only for specific metadata.
- **Need authentication/authorization:** use reactive Spring Security rather than hand-parsing tokens out of bodies.
- **Need JSON DTO validation:** use Bean Validation and controller/service argument resolution.
- **Need JSON normalization:** use Jackson config/codec customization instead of rewriting raw JSON in a filter.
- **Need response DTO transformation:** handle it in controller/service layers or result handling rather than splicing JSON bytes in a response decorator.
- **Need large file uploads:** use `FilePart.transferTo` or streaming APIs; never hold entire files in `byte[]`.
- **Debugging codec errors:** inspect `DataBufferLimitException`, media types, and `maxInMemorySize` rather than blindly adding body wrappers.
- **Only need filtering on functional endpoints:** consider `HandlerFilterFunction` when its scope fits better than a global `WebFilter`.
- **Need accurate TCP traffic metering:** collect metrics from Netty, proxies, or load balancers rather than counting Spring HTTP writer DataBuffers.

Choose the **lowest-complexity abstraction that suffices**, without dropping down to byte level when DTO/event semantics already cover the requirement.

## 14. Performance, Concurrency, and Cancellation

A single request can traverse multiple threads across scheduler boundaries. Therefore:

- Per-request counters should be thread-safe across callbacks, such as `AtomicLong` or equivalent ordering-safe structures.
- Never store bytes or temporary bodies across requests in a mutable field on a singleton `@Component`.
- Never execute JDBC, blocking HTTP clients, `Thread.sleep`, or heavy CPU work inside callbacks on the Netty event loop.
- When blocking APIs are unavoidable, offload explicitly using deferred sources and bounded schedulers; byte-level decorators are not the place for DB queries.
- Keep byte-counting callbacks lightweight to minimize overhead; re-decoding JSON purely for logging wastes CPU and memory.
- When a client cancels or times out, `doFinally` can receive `cancel`; cleanup must release only resources actually owned.
- Async logging or metric export pipelines also require bounded queues; a "logging-only" filter can still create bottlenecks.

Illustrative fragment distinguishing termination callbacks:

~~~java
return chain.filter(decoratedExchange)
        .doOnError(error -> recordFailure(error))
        .doFinally(signal -> recordTermination(signal));
~~~

This is a fragment; `recordFailure` and `recordTermination` are hypothetical methods, not standalone Java. `doOnError` observes errors; `doFinally` runs on complete/error/cancel. Never conclude `doFinally(ON_COMPLETE)` guarantees the client received the entire response over the network.

## 15. Advanced Pre-Production Testing

Beyond the demo's happy path, test:

1. **Empty body:** GET or bodyless POST produces no unexpected NPE or cancellation.
2. **Valid JSON:** decoder receives the complete body intact through decorators.
3. **Malformed JSON:** WebFlux returns the right status/error without the filter swallowing exceptions.
4. **Large body:** no accidental aggregation; any intentional join enforces a strict cap.
5. **Streaming:** NDJSON/SSE exercises `writeAndFlushWith` where applicable without reordering items.
6. **Cancellation:** client aborts stream mid-flight; no pooled buffers leak and cleanup runs.
7. **Concurrent requests:** `requestBytes`/`responseBytes` never mix across concurrent requests.
8. **Bodyless responses:** 204/304/HEAD work without assuming `writeWith` is always called.
9. **Security rejection:** 401/403 returns before the controller without forcing body reads.
10. **Response commit:** headers are modified only before commit, with no double writes.
11. **Upload/multipart:** files are not buffered in memory; ownership is handled cleanly.
12. **Server/runtime:** run end-to-end through real Reactor Netty and proxies when testing network behavior.

`WebTestClient.bindToApplicationContext` covers many in-process WebFlux pipeline tests; timeouts, pooled Netty memory, and TLS require integration/load tests over real network sockets.

## 16. Safe Decorator Implementation Checklist

- Confirm the application actually runs on the Spring WebFlux reactive stack, not Spring MVC Servlet.
- Understand `ServerHttpRequestDecorator` and `ServerHttpResponseDecorator` only wrap delegates; pass them via `exchange.mutate()`.
- When only measuring size, read `readableByteCount()` in `doOnNext`; never call `read(...)` or self-subscribe.
- Never release pooled buffers you only observe and pass downstream.
- For response streaming, handle `writeWith`, `writeAndFlushWith`, `setComplete`, and account for specialized writers.
- When transforming bodies, enforce max sizes, copy deliberately, emit fresh buffers for replay, synchronize headers, and ensure cleanup.
- Use `DataBufferUtils.join(source, maxBytes)` for bounded aggregation; release the joined buffer once read.
- Never cache/replay a pooled DataBuffer that has already been read or released.
- Protect sensitive data; never dump entire request/response bodies to logs.
- Never modify status/headers in `doFinally` after the response may have committed.
- Use concurrency-safe per-request state and handle cancellation/error signals.
- Test `DataBufferLimitException`, upload/file streaming, and backpressure under large payloads.
- Distinguish DataBuffer byte counts, declared Content-Length, and wire network bytes.
- Add regression tests for JSON echo, plain text, concurrency, empty bodies, cancellation, security rejections, and streaming.
- Prefer Spring Security, Validation, Jackson codecs, or observability abstractions when they solve the problem at a higher, cleaner layer.

**Conclusion:** `ServerHttpRequestDecorator` and `ServerHttpResponseDecorator` wrap reactive HTTP primitives in Spring WebFlux without replacing handlers. `DataBuffer` represents streaming byte chunks that may be pooled and require strict ownership tracking. Observing metadata or sizes **does not require consuming the body**; transforming bodies requires bounds, replay, and precise buffer release. Combining `WebFilter` with `exchange.mutate()`, hooking only the necessary publishers, and testing error/cancellation/streaming paths forms the foundation for safe web-runtime customization.