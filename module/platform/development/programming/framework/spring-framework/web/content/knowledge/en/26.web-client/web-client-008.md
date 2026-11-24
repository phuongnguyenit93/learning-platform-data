# WebClient: Consuming or Releasing the Response Body to Reuse Connections

## 1. Why Does the Response Body Govern Connection Lifecycle?

When using Spring `WebClient` for HTTP calls, receiving the status and headers **does not mean the response has been completely read**. The response body is a data stream that may not yet have been received, decoded, or discarded. If an application inspects only the status and abandons the body, an HTTP/1.1 connection can still have unread response bytes; that connection cannot safely be reused for the next request.

With connectors using a connection pool (such as Reactor Netty), the normal lifecycle of a finite response is:

1. Acquire a connection from the pool or open a new one; send the request.
2. Receive response status, headers, and the body stream.
3. **Read the entire body** if the content is needed, or **release/discard the body via the appropriate API** if it is not.
4. Complete or cancel the response according to the HTTP client's rules; if the protocol and server permit, the connection can return to the pool for reuse.

Three concepts must be distinguished:

- **Consume:** subscribe to and process the body stream through completion, such as `bodyToMono(String.class)` or `bodyToFlux(Item.class)`.
- **Release/discard:** handle/dispose of an unneeded body through APIs like `ClientResponse.releaseBody()` or `toBodilessEntity()`. This closes out the response lifecycle when the application only needs status/headers.
- **Reuse:** the underlying physical connection is actually used again. Proper consume/release is an important prerequisite, **not a guarantee** of reuse: the server may send `Connection: close`, the connection may error or expire, the request may be cancelled mid-flight, or the pool may evict the connection; HTTP/2 also has multiplexing characteristics distinct from HTTP/1.1.

`Mono` and `Flux` describe asynchronous work: normally a request does not run just because you called `retrieve()` or built a pipeline. There must be a subscription (for instance, the WebFlux framework subscribing when returning a publisher from a handler, or `block()` in a demo outside the event loop).

## 2. Choosing the Right API to Manage the Body

| Need | Recommended usage | What to understand |
| --- | --- | --- |
| Need an object or text from the body | `retrieve().bodyToMono(T.class)` | Reads and decodes the body into a value; `Mono` completes after receiving/decoding via codec. |
| Need all items of a finite streaming response | `retrieve().bodyToFlux(T.class)` and consume to completion | Use streams as intended; avoid cutting off arbitrarily if HTTP/1.1 connection reuse is a priority. |
| Need only status/headers, discard body | `retrieve().toBodilessEntity()` | Returns `ResponseEntity<Void>`; suitable when payload is unneeded. Default `retrieve()` treats 4xx/5xx as errors. |
| Need custom branching by HTTP status | `exchangeToMono(response -> ...)` or `exchangeToFlux(response -> ...)` | Decide body handling inside the callback. Spring checks and releases any unused body after the callback's returned publisher completes. |
| Inside a callback with `ClientResponse` and intentionally discarding body | `response.releaseBody()` | Returns `Mono<Void>`; must be **chained** into the returned publisher, not called and ignored. |
| Need status/headers and a `Flux` body | `retrieve().toEntityFlux(T.class)` | `ResponseEntity` holds a `Flux`: **must subscribe/consume the inner Flux**, otherwise related resources are not properly released. |

The older `exchange()` API was deprecated in Spring 5.3 because it was easy to omit the consume/release step. For modern code, prefer `retrieve()` or `exchangeToMono`/`exchangeToFlux`.

Note: `bodyToMono(Void.class)` can be used when **no body is genuinely expected**. If the server unexpectedly sends bytes, using `Void` to "skip" does not guarantee draining all data to reuse an HTTP/1.1 connection; the connector may close the connection. When a response **may have a body that you do not need**, `toBodilessEntity()` or `releaseBody()` expresses the intent more clearly.

## 3. Writing Code When Content Is Needed vs. Unneeded

### 3.1. Content Needed: Decode the Body Normally

~~~java
WebClient client = WebClient.create("https://api.example.com");

// Mono<String> will read/decode the content when subscribed.
Mono<String> payload = client.get()
        .uri("/orders/42")
        .retrieve()
        .bodyToMono(String.class);

// In a WebFlux app, return the payload via the reactive chain for the framework to handle.
// Avoid calling subscribe() manually in a service just to "trigger" the request.
~~~

By default, `retrieve()` turns 4xx/5xx statuses into `WebClientResponseException` when a subscriber requests the response. If you need the error code and error body, use the provided error APIs rather than reading the response twice.

### 3.2. Payload Unneeded: Return a Bodiless Response

~~~java
Mono<ResponseEntity<Void>> response = client.delete()
        .uri("/orders/42")
        .retrieve()
        .toBodilessEntity();
~~~

Even when the caller only cares about the HTTP status code, the publisher must still be subscribed to for the request and cleanup to run. In Spring WebFlux, return the publisher up to the controller rather than calling `.block()` on the event loop.

### 3.3. Handling Status Yourself: Consume or Release Inside the Callback

~~~java
Mono<String> result = client.get()
        .uri("/orders/42")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(String.class);
            }
            return response.createError();
        });
~~~

In this example, the success branch reads the body; the error branch creates a reactive error from the response. With `exchangeToMono`/`exchangeToFlux`, if the callback returns a publisher that completes without consuming the body, Spring releases the unused portion to avoid holding resources. **Do not pass `ClientResponse` itself out of the callback** and try to read the body downstream: the body is no longer guaranteed accessible once the callback publisher ends.

If you only want the status and do not need the body:

~~~java
Mono<Integer> status = client.get()
        .uri("/health")
        .exchangeToMono(response ->
                response.releaseBody()
                        .thenReturn(response.statusCode().value()));
~~~

`releaseBody()` only returns a `Mono<Void>`, so a buggy pattern is calling `response.releaseBody();` and then immediately `return Mono.just(status);`: the created cleanup publisher is never subscribed to or chained. `thenReturn(...)` forces the release work to become part of the result chain.

If you want different branches for errors, keep the difference clear: `retrieve()` automatically errors on 4xx/5xx; `exchangeToMono()` delegates the decision to the callback. Choose each branch's policy explicitly.

### 3.4. A Filter Intercepting a Response Must Release It

~~~java
ExchangeFilterFunction rejectBusy = (request, next) ->
        next.exchange(request).flatMap(response -> {
            if (response.statusCode().value() == 429) {
                return response.releaseBody()
                        .then(Mono.error(
                                new IllegalStateException("Upstream too busy")));
            }
            return Mono.just(response);
        });
~~~

This is an illustrative filter snippet: the filter **replaces the response with an error**, so it must clean up the body before emitting the error. In the `Mono.just(response)` branch, the filter passes the response downstream to continue body processing; do not release early because downstream still needs it.

## 4. Runnable Demo with Java 17 and Spring WebFlux

The example below creates an internal HTTP server returning a fixed-length body. It demonstrates three ways to complete a response lifecycle, without claiming to measure connection reuse.

**Requirements:** JDK 17+, a Maven/Gradle project with `spring-boot-starter-webflux` (Spring Boot 3.x) or full `spring-webflux` plus an HTTP connector, running `ResponseBodyLifecycleDemo` from an IDE. This is a complete Java program within a project declaring dependencies; bare `javac` lacks the classpath for Spring/Reactor.

Save the file `src/main/java/ResponseBodyLifecycleDemo.java`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;

public class ResponseBodyLifecycleDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/data", exchange -> {
            byte[] body = "payload-ready".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });

        server.start();
        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            WebClient client = WebClient.create(baseUrl);

            String body = client.get()
                    .uri("/data")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(Duration.ofSeconds(5));
            System.out.println("body = " + body);

            Integer bodilessStatus = client.get()
                    .uri("/data")
                    .retrieve()
                    .toBodilessEntity()
                    .map(entity -> entity.getStatusCode().value())
                    .block(Duration.ofSeconds(5));
            System.out.println("bodiless status = " + bodilessStatus);

            Integer releasedStatus = client.get()
                    .uri("/data")
                    .exchangeToMono(response ->
                            response.releaseBody().thenReturn(
                                    response.statusCode().value()))
                    .block(Duration.ofSeconds(5));
            System.out.println("released status = " + releasedStatus);
        } finally {
            server.stop(0);
        }
    }
}
~~~

Expected output when all three requests succeed:

~~~text
body = payload-ready
bodiless status = 200
released status = 200
~~~

Explanation:

- Request 1 needs the body, so `bodyToMono(String.class)` reads and decodes `payload-ready`.
- Request 2 does not need the body, so `toBodilessEntity()` returns status and headers without allocating a payload for the caller.
- Request 3 uses `exchangeToMono` to capture the status and chain `releaseBody()`.
- `block(Duration...)` serves only the synchronous `main` in the demo; do not use `block()` in controllers/services running on the Reactor event loop.
- The server uses port `0` so the OS picks a free port. This verifies **response handling**, not proof that a TCP socket was reused; confirming reuse requires inspecting the pool and connection/channel identifiers.

## 5. Error-Prone Scenarios and Consequences

### Reading Only Headers/Status and Abandoning the Response

Legacy code might call `exchange()`, inspect the status, and return another value without touching the body. An unhandled response stream can then retain resources and cause pool exhaustion under load. Switch to `exchangeToMono(...)`, use `retrieve().toBodilessEntity()`, or chain `releaseBody()` in branches that intentionally discard the payload.

### Returning a `Flux` That Nobody Subscribes To

With `toEntityFlux(...)`, the response entity wraps a `Flux` that is not automatically read. If you read only the status from `ResponseEntity` and forget the `Flux`, associated resources may remain unreleased. Consume the `Flux` or choose `toBodilessEntity()` if the content is truly unneeded.

### Stopping Mid-Stream via `take(1)`, `next()`, Timeout, or Cancellation

Cancelling a body stream before reading to the end is not the same as consuming through EOF. The framework/connector must clean up resources; with HTTP/1.1, it may have to abort/close the connection rather than returning a connection with leftover bytes to the pool. **Cancellation does not automatically mean a memory leak**, but you should not expect the socket to be reused. For infinite streams (SSE), the connection may stay held until the caller cancels and cleanup runs along the cancellation path.

### Touching Low-Level `DataBuffer` Without Releasing

`bodyToFlux(DataBuffer.class)` hands buffers directly to your code. With pooled buffers, holding or dropping a buffer improperly risks native memory leaks—which is **different** from a TCP connection failing to return to the pool. When handling buffers manually, read and then call `DataBufferUtils.release(buffer)` in `finally`, and consider `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` if operators can drop buffers on filters, errors, or cancellations. With standard codecs decoding directly to POJO/String, the framework normally manages buffers for you; never release a buffer already owned/released by the framework.

### Confusing 4xx/5xx Errors with Bodies That Need No Handling

`retrieve()` has default error handling, whereas `exchangeToMono()` requires you to branch yourself. When using `onStatus` or a filter to read an error message, never read the body twice; to put error details into an exception, consume the body on the error path. Never create a release publisher and leave it unchained.

## 6. Practical Observations When a Connection Pool Misbehaves

When you observe many requests waiting to acquire connections, unexpected timeouts, or active connections climbing without dropping:

1. Audit every code path: success, 4xx/5xx, retries, timeouts, cancellations, filters, and header-only branches. Ask explicitly: was the body consumed to completion or released via the API?
2. Distinguish valid long-lived streams from stuck connections. SSE and streaming responses can hold connections for long periods.
3. Read Reactor Netty connection provider metrics (active/idle/pending, if metrics are enabled), log request start/end times, and enable controlled debug logs. Rely on actual **channel/connection IDs** if verifying reuse.
4. Use a keep-alive HTTP/1.1 test server to exercise sequential and concurrent load; compare finite bodies read to completion against early cancellations. Do not draw conclusions from three 200 responses alone.
5. Check other causes: undersized pool, timeouts, server `Connection: close`, proxies, network faults, or a slow server. Increasing pool size cannot fix abandoned body streams.

**Decision rule:** if you need the payload, decode and consume it; if you do not need the payload, use `toBodilessEntity()` or chain `releaseBody()`; when customizing status handling, keep all body processing inside the `exchangeToMono`/`exchangeToFlux` callback. Completing the response lifecycle lets the pool function properly, while actual reuse depends on transport and server behavior.

## 7. Primary Documentation

- Spring Framework, WebClient — Exchange: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework, WebClient — retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework, Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework, ClientResponse JavaDoc (releaseBody, toBodilessEntity): https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/reactive/function/client/support/ClientResponseWrapper.html
- Spring Framework, ResponseSpec JavaDoc (toEntityFlux): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html
