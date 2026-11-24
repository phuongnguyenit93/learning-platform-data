# Modifying the Exchange via Mutate and Decorator

**Module:** Spring Framework – reactive  
**Parent topic:** Filters and Sessions

## Learning Objectives

After this lesson, you can:

1. Explain why request, response, and exchange in WebFlux are usually wrapped with decorators instead of mutating the original object in place.
2. Use `ServerHttpRequest.mutate()` and `ServerWebExchange.mutate()` to create a new request/exchange with replaced headers, method, URI, or response.
3. Distinguish the convenient builders from `ServerHttpRequestDecorator`, `ServerHttpResponseDecorator`, and `ServerWebExchangeDecorator`.
4. Pass the mutated exchange to downstream filters and handlers with `chain.filter(updatedExchange)`.
5. Intervene in the response before commit, observe the body publisher, and handle `DataBuffer` without breaking backpressure or ownership.
6. Choose the right abstraction to add internal headers, rewrite requests, record metrics, replace the response body, or integrate an intermediary HTTP layer.
7. Test mutate/decorator behavior with `WebTestClient` and identify common mistakes such as forgetting to use the new exchange, modifying headers after commit, reading the body multiple times, or subscribing yourself.

## 1. Why Does WebFlux Use Mutate and Decorator?

In WebFlux, `ServerHttpRequest`, `ServerHttpResponse`, and `ServerWebExchange` are abstractions of one HTTP exchange. Many implementations are provided by the server adapter and can be viewed as objects representing the current request/response. They are not designed for the application to arbitrarily modify every internal property.

For example, request headers are usually exposed as non-modifiable directly. If a `WebFilter` needs to add an internal header for a downstream handler, the appropriate approach is to create a new request based on the current request. `mutate()` provides a builder for that.

A decorator solves a broader need: creating an object that wraps the original object, forwarding most behavior to the delegate, while overriding the exact methods that need to be changed or observed. For example, a response decorator can count the number of buffer bytes written, add metadata before commit, or adjust how the body is written.

The two mechanisms often go together:

- **mutate/builder:** creates a new request or exchange with some properties changed.
- **decorator:** wraps a request/response/exchange to change or observe behavior at a specific boundary.

Both preserve the reactive contract. They do not make a new HTTP request to the client, do not send a response by themselves, and do not start a separate subscription. Changes only take effect when the new object is passed into the next part of the pipeline.

## 2. Architecture of a Wrapped Exchange

A `ServerWebExchange` contains the request and response for the same HTTP handling pass. A filter can create a request decorator, a response decorator, and then build a new exchange:

```text
HTTP server adapter
        |
        v
  Original Exchange
   |            |
   v            v
 Request      Response
   |            |
 mutate()     decorator
   |            |
   v            v
Updated Request + Decorated Response
          |
          v
 exchange.mutate().request(...).response(...).build()
          |
          v
 Updated ServerWebExchange
          |
          v
 chain.filter(updatedExchange)
          |
          v
 Next filter / Handler / Controller
```

Points to remember:

1. The original request/response remains the delegate of the wrapper objects.
2. The new exchange provides the request/response that downstream will see.
3. The current filter must return the publisher from `chain.filter(updatedExchange)` so the lifecycle continues to be managed.
4. Components already holding a reference to the old exchange do not automatically switch to the new exchange.
5. Nothing here alters the HTTP bytes the client already sent before the request reached the server.

## 3. ServerHttpRequest.mutate(): Creating a Modified Request

`ServerHttpRequest.mutate()` returns a `ServerHttpRequest.Builder`. The builder lets you adjust several common request parts and then create a new request with `build()`.

Important operations include:

| Builder method | Effect |
| --- | --- |
| `method(HttpMethod)` | Change the method seen by downstream. |
| `uri(URI)` | Change the exposed request URI. |
| `path(String)` | Change the path via the builder API. |
| `headers(Consumer<HttpHeaders>)` | Adjust the headers copy used for the new request. |
| `build()` | Create a new request based on the current request. |

Example of adding an internal header:

```java
ServerHttpRequest updatedRequest = exchange.getRequest()
        .mutate()
        .headers(headers ->
                headers.set("X-Internal-Request", "checked"))
        .build();
```

This is an illustrative snippet in a `WebFilter`. The new request preserves the remaining properties through the builder/decorator mechanism, while downstream can read `X-Internal-Request`. This header is added by the server; it must not be confused with headers sent by the client or used as proof of authentication.

### 3.1. Modifying the Method or URI

The builder also allows changing the method/URI that downstream components see:

```java
ServerHttpRequest rewritten = exchange.getRequest()
        .mutate()
        .method(HttpMethod.GET)
        .uri(URI.create("https://internal.example/api/items"))
        .build();
```

This is an **illustrative snippet**, not a complete proxy configuration. Changing the URI in the request object does not automatically send a request to the new host. It only changes the metadata exposed to subsequent components; routing, reverse proxying, or an outbound client must be designed separately.

When changing the URI/path, pay attention to:

- The URI may contain a query string, encoded path, and context path.
- Changing the path does not automatically change every related component such as route predicates, forwarded headers, or security decisions that already ran earlier.
- Do not concatenate path strings from untrusted input without normalization; avoid path traversal and mismatches between encoded/decoded paths.
- If rewriting the method, check whether the body and headers such as `Content-Length`, `Content-Type`, and `Transfer-Encoding` are still appropriate.
- Changing the request in a filter only affects downstream; filters that ran earlier already observed the initial request.

For complex rewrites, use the appropriate URI API and test with cases containing encoded paths, multi-value queries, context paths, and slashes.

### 3.2. Adding or Replacing Headers

`headers(Consumer<HttpHeaders>)` lets you modify the headers copy that the builder uses to create the new request:

```java
ServerHttpRequest request = exchange.getRequest()
        .mutate()
        .headers(headers -> {
            headers.remove("X-Client-Override");
            headers.set("X-Internal-Source", "gateway");
            headers.add("X-Trace-Tag", "reactive");
        })
        .build();
```

In the example:

- `remove` removes headers that downstream should not receive.
- `set` replaces all current values with a single value.
- `add` appends a new value and keeps existing values.

Headers can have multiple values. Choosing `set` or `add` must follow the semantics of that header. For example, `Set-Cookie` can have multiple lines; merging them wrongly can break the response. For security or identity headers, do not trust client-sent values when a server-authoritative value is needed: remove or overwrite them at a defined trust boundary.

### 3.3. Attaching the New Request to the Exchange

After building the request, create a new exchange:

```java
ServerWebExchange updated = exchange.mutate()
        .request(request)
        .build();

return chain.filter(updated);
```

You can write this shorter using the builder-consumer overload:

```java
ServerWebExchange updated = exchange.mutate()
        .request(builder ->
                builder.headers(headers ->
                        headers.set("X-Internal-Request", "checked")))
        .build();

return chain.filter(updated);
```

Both ways create a new exchange with the adjusted request. The second way is convenient when the change stays inside the request builder. If you have already created your own `ServerHttpRequest` decorator, pass that object using the `request(ServerHttpRequest)` overload.

**Common mistake:** calling `exchange.mutate().request(...).build()` and then still calling `chain.filter(exchange)`. In that case downstream keeps receiving the old exchange and does not see the change. Always pass the right new object.

## 4. ServerWebExchange.mutate(): Replacing Request, Response, or Principal

`ServerWebExchange.mutate()` returns a `ServerWebExchange.Builder`. The builder can replace the exchange's request, response, and principal:

| Builder method | Meaning |
| --- | --- |
| `request(ServerHttpRequest)` | Use the new request. |
| `request(Consumer<ServerHttpRequest.Builder>)` | Adjust the request through the builder. |
| `response(ServerHttpResponse)` | Use the new response or response decorator. |
| `principal(Mono<Principal>)` | Replace the principal publisher exposed by the exchange. |
| `build()` | Create the new exchange decorator. |

Example combining request and response:

```java
ServerHttpRequest request = exchange.getRequest()
        .mutate()
        .headers(headers ->
                headers.set("X-Internal-Request", "checked"))
        .build();

ServerHttpResponse response =
        new ServerHttpResponseDecorator(exchange.getResponse());

ServerWebExchange updated = exchange.mutate()
        .request(request)
        .response(response)
        .build();

return chain.filter(updated);
```

The new exchange maintains its link to the original exchange and provides the replaced request/response. The current request's attributes still belong to the exchange scope; do not use them as a global cache or state shared across many requests.

### 4.1. Replacing the Principal Needs Intention

The builder has the `principal(Mono<Principal>)` overload. It is meant for integrations that need the exchange to expose a different principal, for example an authentication adapter layer that has verified the identity and provides the principal via a reactive pipeline.

Do not use it to spoof login or escalate privileges. The principal must be created from a trusted authentication result; authorization still needs to be controlled by Spring Security/policy. If you only want to read the current user, use `exchange.getPrincipal()` or the reactive SecurityContext; there is no need to mutate the principal.

### 4.2. A New Exchange Is Not a New Request Scope

`exchange.mutate().build()` does not create a new session, does not create a new HTTP request, and does not reset all attributes. It creates a wrapper for the current exchange, replacing the components specified by the builder. Session, principal, locale, and other data still follow the original request's lifecycle, unless you explicitly replace the corresponding part.

If you need to store metadata used within the same request, you can use `exchange.getAttributes()`. If data must follow reactive subscribers across operators, consider Reactor `Context`. Do not put request-specific state in mutable fields of a singleton filter.

## 5. What Is a Decorator?

A decorator is an object that implements the same abstraction as the wrapped object and holds a delegate inside. When behavior does not need to change, the decorator forwards the call to the delegate. When it needs to intervene, it overrides the exact method.

Spring provides ready-made base classes:

| Decorator | Wrapped object | Common goals |
| --- | --- | --- |
| `ServerHttpRequestDecorator` | `ServerHttpRequest` | Adjust request metadata or body for downstream. |
| `ServerHttpResponseDecorator` | `ServerHttpResponse` | Intervene in headers, body writes, flush, or response completion. |
| `ServerWebExchangeDecorator` | `ServerWebExchange` | Change how the exchange exposes request/response or broader exchange behavior. |

A decorator is usually passed into `exchange.mutate()` for downstream handlers to use:

```java
ServerHttpRequest request =
        new ServerHttpRequestDecorator(exchange.getRequest());

ServerHttpResponse response =
        new ServerHttpResponseDecorator(exchange.getResponse());

ServerWebExchange updated = exchange.mutate()
        .request(request)
        .response(response)
        .build();
```

The base decorators already delegate most methods to the original object. You only need to override the parts with new behavior. If you override nothing, the wrapper is practically just a pass-through layer; use the builder directly when you only need to change a few standard properties.

## 6. ServerHttpRequestDecorator: Deeper Request Intervention

`ServerHttpRequestDecorator` is useful when the builder is not enough to change how the request is read. It lets you override methods of `ServerHttpRequest` such as `getHeaders()`, `getURI()`, or `getBody()`.

### 6.1. Decorating Headers

Example creating a request wrapper that adds a header without mutating the original object:

```java
ServerHttpRequest decoratedRequest =
        new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public HttpHeaders getHeaders() {
                HttpHeaders headers = new HttpHeaders();
                headers.putAll(super.getHeaders());
                headers.set("X-Internal-Request", "checked");
                return HttpHeaders.readOnlyHttpHeaders(headers);
            }
        };
```

This is an **illustrative snippet**. The wrapper returns a new headers instance, copies the original headers, and adds the value. Returning read-only headers prevents downstream from directly modifying the metadata copy provided by the decorator.

For ordinary header changes, `request.mutate().headers(...)` is shorter and less error-prone. Use a decorator when you need to customize how the request is exposed or combine multiple overridden behaviors.

### 6.2. Decorating URI or Path

A decorator can override `getURI()` or `getPath()` to provide a different view of the request. When doing so, keep the APIs consistent: if the URI changes while the path still returns the old value, routing and metadata-reading code may see two conflicting pieces of information.

Do not construct URIs by simple string concatenation when encoded characters, query parameters, or a context path are present. Use a URI builder, preserve the parts that must be kept, and test cases with spaces, Unicode, percent signs, slashes, and repeated queries.

### 6.3. Decorating the Request Body

`getBody()` returns a `Flux<DataBuffer>` publisher. A request decorator can wrap this publisher to observe or transform the byte stream:

```java
@Override
public Flux<DataBuffer> getBody() {
    return super.getBody()
            .doOnNext(buffer ->
                    log.debug("request chunk: {} bytes",
                            buffer.readableByteCount()));
}
```

This is an **illustrative snippet inside `ServerHttpRequestDecorator`**. It only observes the number of readable bytes in each buffer, does not read the contents, and does not consume the buffer. One chunk does not correspond to one JSON object or one HTTP packet.

If you want to modify the body, you must account for these factors:

- The body is a single-use stream. A separate subscription to log or cache can leave downstream with no data.
- Buffers may use pooled/native memory. Do not hold buffers beyond their lifecycle, do not double-release, and do not read past bounds.
- When changing the byte count, headers such as `Content-Length` may no longer be accurate.
- The body can be large or unbounded; gathering it all into memory loses the benefits of streaming and risks running out of memory.
- Errors/cancel must propagate properly through the publisher; do not swallow errors or subscribe yourself.

If you need to read the body again, you must build a bounded cache/replay strategy and create new buffers properly. Do not just call `getBody()` twice and assume the server will replay the bytes from the start.

## 7. ServerHttpResponseDecorator: Intervening in the Response

`ServerHttpResponseDecorator` is commonly used when you need to observe or adjust how the response is written. Important methods inherited from `ServerHttpResponse`/`ReactiveHttpOutputMessage`:

- `getHeaders()` and `getCookies()` to access response metadata.
- `beforeCommit(...)` to register a reactive operation right before commit.
- `writeWith(Publisher<DataBuffer>)` to write the body.
- `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` to write buffer groups and flush per group.
- `setComplete()` to complete a response with no application-written body.

### 7.1. Adding a Response Header Before Commit

Example registering a header on a response decorator:

```java
ServerHttpResponseDecorator decorated =
        new ServerHttpResponseDecorator(exchange.getResponse());

decorated.beforeCommit(() -> {
    decorated.getHeaders().set("X-Response-Decorator", "applied");
    return Mono.empty();
});

ServerWebExchange updated = exchange.mutate()
        .response(decorated)
        .build();

return chain.filter(updated);
```

The `beforeCommit` callback returns `Mono<Void>`. The header is added before the response commits so it can be sent to the client. Do not call `subscribe()` inside the callback; the framework composes and executes the commit publisher.

Do not modify the status/headers after the response has committed. Once body streaming has started, the server cannot go back and change the status already sent. If you need to add metadata on every response branch, register the callback before calling the chain so it covers both responses with bodies and empty responses.

### 7.2. Observing the Body Written with writeWith

A decorator can wrap the body publisher to record metrics without consuming the buffer:

```java
@Override
public Mono<Void> writeWith(Publisher<? extends DataBuffer> body) {
    return super.writeWith(
            Flux.from(body)
                    .doOnNext(buffer ->
                            bytesWritten.addAndGet(
                                    buffer.readableByteCount())));
}
```

This is an **illustrative snippet inside a response decorator**; `bytesWritten` is a counter created specifically for the request. `Flux.from(body)` converts the input publisher into a Flux to attach a side effect, then still passes the same buffer down to the delegate. It only reads `readableByteCount`, without calling `read` to consume bytes.

### 7.3. Must Also Handle writeAndFlushWith When Supporting Streaming

Some streaming responses write the body in groups of buffers via `writeAndFlushWith`. If the decorator only overrides `writeWith`, metrics or observation logic may miss the grouped write path.

```java
@Override
public Mono<Void> writeAndFlushWith(
        Publisher<? extends Publisher<? extends DataBuffer>> body) {

    return super.writeAndFlushWith(
            Flux.from(body)
                    .map(group -> Flux.from(group)
                            .doOnNext(buffer ->
                                    bytesWritten.addAndGet(
                                            buffer.readableByteCount()))));
}
```

This is an **illustrative snippet**. Each inner publisher represents a group of buffers; the decorator wraps each group and forwards it to the delegate. Do not flatten all groups if per-group flush semantics matter to the streaming protocol.

### 7.4. Limitations of the DataBuffer Counting Metric

The sum of `readableByteCount()` is the number of buffer bytes the response decorator observes at that position. It does not necessarily equal the final number of bytes the client receives over the network, because the server may compress, apply TLS encryption, add framing, or hit an error/cancel after part of the body.

For an empty response, the metric may be 0. For a cancelled streaming response, it only reflects the buffers that passed through the decorator up to the moment of cancellation. If you need bytes on the wire, you need metrics at the transport/server or appropriate proxy infrastructure.

### 7.5. DataBuffer Ownership

The decorator must preserve proper buffer ownership:

- If only observing metadata such as `readableByteCount`, pass the buffer unchanged down to the delegate.
- Do not hold references to pooled buffers after the write finishes.
- Do not release buffers yourself that the delegate/downstream still owns.
- If creating replacement buffers, clearly define who releases the old buffer and the new buffer.
- Handle error, cancel, and discard using the appropriate `DataBufferUtils`/Reactor APIs.

A decorator that reads the body to log it can accidentally shift the read position, causing the codec or server to write incomplete data. Logging a byte stream needs to be designed as a streaming operation with clear ownership.

## 8. ServerWebExchangeDecorator: Wrapping the Whole Exchange

`ServerWebExchangeDecorator` is useful when you want to create an exchange wrapper with custom behavior beyond replacing the request/response with the builder. It takes the original exchange as a delegate and lets you override `getRequest()`, `getResponse()`, or other exchange methods.

Conceptual example:

```java
ServerWebExchange decoratedExchange =
        new ServerWebExchangeDecorator(exchange) {
            @Override
            public ServerHttpRequest getRequest() {
                return decoratedRequest;
            }

            @Override
            public ServerHttpResponse getResponse() {
                return decoratedResponse;
            }
        };

return chain.filter(decoratedExchange);
```

This is an **illustrative snippet**, assuming `decoratedRequest` and `decoratedResponse` were already created. By default the decorator delegates other methods back to the original exchange. If you additionally override session/principal/attributes, you must preserve the corresponding semantics and lifecycle.

In most regular filters, `exchange.mutate().request(...).response(...).build()` is sufficient and easy to read. Write a `ServerWebExchangeDecorator` yourself when you need a specialized exchange abstraction, such as a test adapter or an integration layer with many related behaviors.

## 9. Example WebFilter Combining Mutate and Decorator

The filter below does three things:

1. Adds an internal header to the request so a downstream controller can read it.
2. Wraps the response to add a header before commit and count the buffer bytes written.
3. Logs the outcome together with the byte count after the chain completes or is cancelled.

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.reactivestreams.Publisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ExchangeMutationFilter implements WebFilter {
    private static final Logger log =
            LoggerFactory.getLogger(ExchangeMutationFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        AtomicLong bytesWritten = new AtomicLong();

        ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers ->
                        headers.set("X-Internal-Request", "checked"))
                .build();

        ServerHttpResponseDecorator response =
                new ServerHttpResponseDecorator(exchange.getResponse()) {

            @Override
            public Mono<Void> writeWith(
                    Publisher<? extends DataBuffer> body) {

                return super.writeWith(
                        Flux.from(body)
                                .doOnNext(buffer ->
                                        bytesWritten.addAndGet(
                                                buffer.readableByteCount())));
            }

            @Override
            public Mono<Void> writeAndFlushWith(
                    Publisher<? extends Publisher<? extends DataBuffer>> body) {

                return super.writeAndFlushWith(
                        Flux.from(body)
                                .map(group -> Flux.from(group)
                                        .doOnNext(buffer ->
                                                bytesWritten.addAndGet(
                                                        buffer.readableByteCount()))));
            }
        };

        response.beforeCommit(() -> {
            response.getHeaders()
                    .set("X-Response-Decorator", "applied");
            return Mono.empty();
        });

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .response(response)
                .build();

        return chain.filter(updated)
                .doFinally(signal -> log.info(
                        "method={} path={} bytes={} signal={}",
                        request.getMethodValue(),
                        request.getURI().getPath(),
                        bytesWritten.get(),
                        signal));
    }
}
```

This is a **complete WebFilter class**. `AtomicLong` is created inside each filter invocation handling an exchange, so the counter is not shared across requests. `doFinally` attaches to the chain's publisher to record `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`.

The filter does not subscribe to the chain itself. The wrapped request and response are attached to the new exchange, and then the new exchange is passed down with `chain.filter(updated)`. Downstream endpoints will see the internal request header and the response decorator will participate in writing the body.

The byte metric only counts the buffers the decorator observes; it is not a network-wire metric. If the application uses SSE or streaming, override both `writeWith` and `writeAndFlushWith` to cover both write paths.

## 10. A Runnable Spring Boot 3.3.5 Program

The example below uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, and `spring-boot-starter-webflux`. It has a WebFilter that mutates the request and decorates the response, a controller that reads the internal header, and two integration tests checking the response.

Structure:

```text
exchange-mutate-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ExchangeMutationApplication.java
    │   ├── ExchangeMutationFilter.java
    │   └── DemoController.java
    └── test/java/demo/
        └── ExchangeMutationIntegrationTest.java
```

### 10.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>exchange-mutate-demo</artifactId>
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
```

### 10.2. ExchangeMutationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExchangeMutationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExchangeMutationApplication.class, args);
    }
}
```

### 10.3. ExchangeMutationFilter.java

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.reactivestreams.Publisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ExchangeMutationFilter implements WebFilter {
    private static final Logger log =
            LoggerFactory.getLogger(ExchangeMutationFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        AtomicLong bytesWritten = new AtomicLong();

        ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers ->
                        headers.set("X-Internal-Request", "checked"))
                .build();

        ServerHttpResponseDecorator response =
                new ServerHttpResponseDecorator(exchange.getResponse()) {
            @Override
            public Mono<Void> writeWith(
                    Publisher<? extends DataBuffer> body) {
                return super.writeWith(
                        Flux.from(body)
                                .doOnNext(buffer ->
                                        bytesWritten.addAndGet(
                                                buffer.readableByteCount())));
            }

            @Override
            public Mono<Void> writeAndFlushWith(
                    Publisher<? extends Publisher<? extends DataBuffer>> body) {
                return super.writeAndFlushWith(
                        Flux.from(body)
                                .map(group -> Flux.from(group)
                                        .doOnNext(buffer ->
                                                bytesWritten.addAndGet(
                                                        buffer.readableByteCount()))));
            }
        };

        response.beforeCommit(() -> {
            response.getHeaders()
                    .set("X-Response-Decorator", "applied");
            return Mono.empty();
        });

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .response(response)
                .build();

        return chain.filter(updated)
                .doFinally(signal -> log.info(
                        "method={} path={} bytes={} signal={}",
                        request.getMethodValue(),
                        request.getURI().getPath(),
                        bytesWritten.get(),
                        signal));
    }
}
```

### 10.4. DemoController.java

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    public record InspectResult(
            String method,
            String path,
            String internalRequestHeader) {}

    @GetMapping("/inspect")
    public Mono<InspectResult> inspect(ServerHttpRequest request) {
        return Mono.just(new InspectResult(
                request.getMethodValue(),
                request.getPath().value(),
                request.getHeaders().getFirst("X-Internal-Request")));
    }

    @PostMapping(
            value = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(@RequestBody Mono<String> body) {
        return body.map(value -> "echo: " + value);
    }

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> events() {
        return Flux.just("first", "second", "third");
    }
}
```

### 10.5. ExchangeMutationIntegrationTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeMutationIntegrationTest {
    @Autowired
    WebTestClient client;

    @Test
    void mutatedRequestAndDecoratedResponseAreVisible() {
        client.get()
                .uri("/inspect")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Decorator", "applied")
                .expectBody()
                .jsonPath("$.method").isEqualTo("GET")
                .jsonPath("$.path").isEqualTo("/inspect")
                .jsonPath("$.internalRequestHeader").isEqualTo("checked");
    }

    @Test
    void responseDecoratorPreservesBodyAndAddsHeader() {
        client.post()
                .uri("/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Decorator", "applied")
                .expectBody(String.class)
                .isEqualTo("echo: hello");
    }
}
```

Run the application:

```bash
mvn spring-boot:run
```

Send test requests:

```bash
curl -i http://localhost:8080/inspect
curl -i -X POST http://localhost:8080/echo \
  -H "Content-Type: text/plain" \
  --data "hello"
curl -i -N http://localhost:8080/events
```

Expected results to observe:

- `GET /inspect` returns JSON with `method` as `GET`, `path` as `/inspect`, and `internalRequestHeader` as `checked`.
- Both endpoints with a body return the `X-Response-Decorator: applied` header added by the `beforeCommit` callback.
- `POST /echo` returns the processed content `echo: hello` intact; the decorator observes the buffer without consuming the body.
- `GET /events` returns three events in `text/event-stream` format. The streaming write path may go through `writeAndFlushWith`.
- The filter log includes the method, path, observed buffer byte count, and terminal signal. The byte value depends on encoding/body and does not include framing/TLS/network overhead.

Run the integration tests:

```bash
mvn test
```

The two tests confirm that the new request reaches the controller, the response decorator adds the header before commit, and the body is still written intact. The example does not test raw body rewriting or custom pooled buffer management; those operations require separate tests for error/cancel and ownership.

## 11. When to Use Builder, When to Use Decorator?

| Need | Suitable approach | Reason |
| --- | --- | --- |
| Add/remove/replace request header | `request.mutate().headers(...)` | Concise, clearly expresses metadata changes. |
| Change method or URI | `request.mutate()` | The builder has standard APIs for these properties. |
| Replace the request object completely | `exchange.mutate().request(request)` | Downstream receives the prepared request. |
| Add a response header before commit | `beforeCommit` on the response or response decorator | Ensures the operation happens before headers are sent. |
| Count/observe response DataBuffers | `ServerHttpResponseDecorator` | Can wrap `writeWith` and `writeAndFlushWith`. |
| Change how the request body is read | `ServerHttpRequestDecorator` | Override `getBody()` when truly needed. |
| Broader exchange customization | `ServerWebExchangeDecorator` | Wrap the whole exchange and override specific behavior. |
| Only store a trace ID for filters/controller of the same request | `exchange.getAttributes()` or Reactor `Context` | No need to create a decorator just to store metadata. |

The builder is the first choice for common metadata changes. A decorator is suitable when you need to intervene in method or stream behavior. A decorator that merely forwards every call without adding behavior usually provides no clear value.

## 12. Filter Order and Scope of Changes

A filter only affects components that run **after it** in the chain. If filter A mutates the request and calls filter B, filter B and the handler can read the new request. Filters running before A already observed the original request.

Example:

```text
Filter A
  |
  v
Filter B: adds X-Internal-Request
  |
  v
Filter C: reads X-Internal-Request = checked
  |
  v
Controller: reads X-Internal-Request = checked
```

If a filter needs to run before Spring Security or after authentication, filter order must be configured intentionally. Do not assume a header added in an arbitrary filter will be available to every security decision; decisions that already happened earlier do not automatically re-run after mutation.

Similarly, a response decorator installed in an outer filter wraps the response from inner filters/handlers. If an inner filter replaces the response itself again, the order and delegate chain determine which decorator observes the write. Test according to the application's actual filter order.

## 13. Common Mistakes and How to Handle Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a new exchange but still calling `chain.filter(exchange)` | Downstream does not see the mutated request/response | Pass the right `updatedExchange` into the chain. |
| Thinking `mutate()` modifies the original object in place | Components holding the old reference do not see changes | Treat the result of `build()` as a new wrapper object and pass it forward. |
| Adding headers after the response commits | Headers are no longer sent or changes are ignored | Register `beforeCommit` before the chain starts writing the response. |
| Only overriding `writeWith` when the application streams | Misses the `writeAndFlushWith` path | Override both when metrics/transforms must cover streaming. |
| Calling `subscribe()` inside a decorator | Detaches body writing from the response lifecycle | Return the publisher from `super.writeWith`/`super.writeAndFlushWith`. |
| Reading a DataBuffer to log and then forwarding | Can shift the read position and cause missing body bytes | Only observe metadata or copy/release with clear ownership. |
| Releasing a buffer the delegate is still using | Double release or response write failure | Only release when code truly owns the buffer and per the right API. |
| Unbounded caching of the entire request body | Increases memory and loses streaming | Set body limits, consider streaming or bounded replay. |
| Changing the body while keeping the old Content-Length | Server/client may read the wrong size | Update/remove length metadata to match the new body. |
| Changing URI by simple string concatenation | Broken encoded path, query, or context path | Use a URI builder and test edge cases. |
| Using client-sent request headers as authentication info | May trust spoofed data | Verify at the trust boundary and use Spring Security. |
| Using a mutable field in a filter to store the current request | Concurrent requests overwrite state | Create local state per filter invocation or use exchange attributes/Context. |
| Using a decorator just to add a simple header | More verbose code than necessary | Use the request builder or response headers before commit. |
| Thinking mutating the principal authenticates the user | May create an untrusted principal | Only replace the principal from verified authentication. |
| Recording a byte metric and calling it the bytes the client received | Ignores transport, compression, TLS, and cancel | Name it accurately as buffer bytes observed at the decorator. |
| Not testing cancellation/error | Decorator may hold resources or produce wrong metrics | Test complete, error, cancel, and streaming when behavior affects the lifecycle. |

## 14. Self-Check Questions

**Question 1.** What does `ServerHttpRequest.mutate()` return and what is it used for?  
**Answer:** It returns a builder to create a new request with certain properties such as method, URI, path, or headers adjusted.

**Question 2.** Why must `chain.filter(updatedExchange)` be called after mutating?  
**Answer:** Because the new object only takes effect for downstream when passed into the chain. If the original exchange is passed, the handler does not see the changes.

**Question 3.** Which components can `ServerWebExchange.mutate()` replace?  
**Answer:** It can replace the request, response, and principal publisher and then build a new exchange wrapper.

**Question 4.** When should you use `ServerHttpRequestDecorator` instead of the builder?  
**Answer:** When you need to override request behavior such as how headers, URI, or body are exposed that the builder cannot express.

**Question 5.** Why should response headers be added in `beforeCommit`?  
**Answer:** The callback runs before the response commits, so the header can still be sent. After commit, sent headers cannot be changed.

**Question 6.** Why does a streaming decorator need to consider `writeAndFlushWith`?  
**Answer:** Some streaming bodies are written in buffer groups and flushed per group through this method; observing only `writeWith` can miss them.

**Question 7.** Does reading `readableByteCount()` consume the DataBuffer?  
**Answer:** No; it returns the number of readable bytes. Do not call byte-reading operations if the goal is only to count.

**Question 8.** Does a decorator automatically make the request body readable multiple times?  
**Answer:** No. The request body remains a publisher stream with its own lifecycle. To replay, you must cache/recreate the body with bounds and manage DataBuffers properly.

**Question 9.** Does the byte metric in a response decorator equal the bytes the client receives on the wire?  
**Answer:** Not necessarily. It counts buffer bytes at the decorator position, before transport, framing, compression, or TLS layers.

**Question 10.** Should you mutate the principal just to add a username to logs?  
**Answer:** No. Read the authenticated principal and log it. Only replace the principal when a trusted integration needs to provide a different principal to downstream.

## Key Takeaways

- `mutate()` creates a builder and `build()` creates a new wrapper object. Changes reach downstream only when the filter passes the right new exchange into `chain.filter(updated)`.
- Use `ServerHttpRequest.mutate()` or `exchange.mutate().request(...)` for ordinary changes to method, URI, path, and headers.
- Use `ServerHttpRequestDecorator` when you need to override request behavior, especially `getBody()`; the body remains a single-use stream and DataBuffers have ownership.
- Use `ServerHttpResponseDecorator` to observe or intervene in `writeWith`/`writeAndFlushWith`. Register headers via `beforeCommit` before the response commits.
- `ServerWebExchangeDecorator` lets you wrap the entire exchange; `exchange.mutate()` is usually enough for ordinary request/response replacement needs.
- Always preserve the reactive lifecycle: return/compose the publisher, do not subscribe or block yourself; handle error/cancel and pooled DataBuffers properly.

### References

1. [Spring Framework – ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): mutate builder, request, response, and principal.
2. [Spring Framework – ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): request builder and metadata.
3. [Spring Framework – ServerHttpRequestDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequestDecorator.html): decorator for request.
4. [Spring Framework – ServerHttpResponseDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponseDecorator.html): decorator for response.
5. [Spring Framework – ServerWebExchangeDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchangeDecorator.html): wrapper for exchange.
6. [Spring Framework – ReactiveHttpOutputMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html): beforeCommit, writeWith, writeAndFlushWith, and setComplete.
7. [Spring Framework – WebFlux Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): filter concepts and reactive chain patterns.
