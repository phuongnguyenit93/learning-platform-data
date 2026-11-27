# Writing a Tested Custom Filter Without Blocking the Event Loop

In this hands-on lab from the **Comprehensive Practice** chapter, you will create a global filter for **Spring Cloud Gateway Server WebFlux**. The filter inspects or generates `X-Request-Id` and attaches the ID to both the request sent to the backend service and the response returned to the client. Then you will write tests confirming that the filter chain continues executing, headers are propagated properly, and the filter code performs no blocking operations on the Reactor non-blocking scheduler.

The Gateway is the entry point for microservices: route predicates select the target service, the filter chain transforms requests/responses, and mechanisms like service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and observability support operations. A custom filter running on every request must be especially lightweight. If it calls `.block()`, performs synchronous file I/O, uses JDBC, or waits on a synchronous HTTP call on the event loop, a single slow request can tie up threads serving many other requests.

## Objectives and Expected Outcomes

After completing this lab, you can:

- Create a `GlobalFilter` and set execution order using `Ordered`.
- Modify immutable requests using `ServerHttpRequest.mutate()` and `ServerWebExchange.mutate()`.
- Propagate a correlation ID through the Gateway to upstream and return it in the response.
- Write unit tests for the filter using `MockServerWebExchange`, `StepVerifier`, and JUnit.
- Use BlockHound to detect blocking calls on Reactor non-blocking threads.
- Offload unavoidable blocking work onto `Schedulers.boundedElastic()` or replace it with reactive APIs.

The end result is that a `GET /api/orders/42` request through the Gateway carries a valid `X-Request-Id` header on both the upstream request and the client response. The filter performs no I/O of its own and always returns the filter chain's `Mono<Void>`.

## 1. Preparing the Project

This lab uses WebFlux because the goal is working properly with the Reactor event loop. The examples use Spring Cloud 2025.0 or later, where starters and namespaces clearly distinguish Gateway Server WebFlux. Pick a Spring Cloud BOM compatible with your project's Spring Boot version; do not pin an individual Gateway version separately.

Add dependencies to Maven `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
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
    <dependency>
        <groupId>io.projectreactor.tools</groupId>
        <artifactId>blockhound</artifactId>
        <version>${blockhound.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Set `blockhound.version` to a BlockHound version compatible with your project's JDK and Reactor versions. The Spring Boot BOM manages common Spring Boot and Reactor dependencies; BlockHound needs its own version property if not managed by your BOM.

If your project uses an older release train, starter names and configuration prefixes may differ. Consult the documentation for your exact release train before copying the examples.

## 2. Declaring a Test Route

Create a route forwarding requests to an orders service running on port `9081`. In `application.yml`:

```yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:9081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
```

With this route, a `GET /api/orders/42` request is forwarded to `http://localhost:9081/orders/42`. `StripPrefix=1` removes the `/api` segment. The `GlobalFilter` in the next section applies to every active route in the Gateway without needing to list the filter name in route YAML.

Make sure the test service exposes `GET /orders/42` and returns a simple response. If you do not have a real service yet, you can point the URI at an HTTP stub in your development environment.

## 3. Writing RequestIdGlobalFilter

Create `RequestIdGlobalFilter.java` in your application package:

```java
package com.example.gateway.filter;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public final class RequestIdGlobalFilter implements GlobalFilter, Ordered {

    public static final String HEADER_NAME = "X-Request-Id";

    private static final Pattern SAFE_REQUEST_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String requestId = resolveRequestId(
                exchange.getRequest().getHeaders().getFirst(HEADER_NAME));

        ServerHttpRequest request = exchange.getRequest().mutate()
                .headers(headers -> headers.set(HEADER_NAME, requestId))
                .build();

        ServerWebExchange updatedExchange = exchange.mutate()
                .request(request)
                .build();

        // Response header is set before the response commits.
        updatedExchange.getResponse().getHeaders().set(HEADER_NAME, requestId);

        // Always return the filter chain publisher; do not block waiting for a result.
        return chain.filter(updatedExchange);
    }

    private String resolveRequestId(String incomingId) {
        if (incomingId != null && SAFE_REQUEST_ID.matcher(incomingId).matches()) {
            return incomingId;
        }
        return UUID.randomUUID().toString();
    }

    @Override
    public int getOrder() {
        // Smaller values execute earlier in the request phase.
        return -100;
    }
}
```

Key points to note:

- `GlobalFilter` runs across Gateway routes. If you only want logic applied to specific routes, consider creating a `GatewayFilterFactory` instead of a global filter.
- Requests in WebFlux are immutable. Use `mutate().build()` to create a new request and attach it to a new exchange.
- Incoming headers are kept only if they match the safe character set and are at most 64 characters long. Invalid values are replaced with a new UUID to avoid injecting arbitrary strings into logs or observability systems.
- The response header is set before the response commits so clients can correlate requests with downstream logs/traces.
- The Request ID is strictly for request correlation. Never use this header as user identity, proof of authentication, or an authorization key.
- `getOrder()` returns `-100` so the filter runs early. When multiple filters exist, check the overall ordering; the response phase executes in reverse order for filters that perform post-chain logic.

The filter only validates a string, generates a UUID, and transforms the request object. It makes no network calls, reads no files, touches no database, and waits on no other threads.

## 4. Writing Unit Tests for the Filter

Create `RequestIdGlobalFilterTest.java` in `src/test/java`:

```java
package com.example.gateway.filter;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import reactor.blockhound.BlockHound;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class RequestIdGlobalFilterTest {

    private final RequestIdGlobalFilter filter = new RequestIdGlobalFilter();

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }

    @Test
    void createsIdAndPassesMutatedExchangeToNextFilter() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42").build());
        var forwardedExchange = new AtomicReference<ServerWebExchange>();

        GatewayFilterChain chain = nextExchange -> {
            forwardedExchange.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain))
                .verifyComplete();

        assertThat(forwardedExchange.get()).isNotNull();
        String requestId = forwardedExchange.get().getRequest()
                .getHeaders().getFirst(RequestIdGlobalFilter.HEADER_NAME);

        assertThat(requestId).isNotBlank();
        assertThatCodeCanParseUuid(requestId);
        assertThat(forwardedExchange.get().getResponse().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME)).isEqualTo(requestId);

        // The original exchange is not mutated directly.
        assertThat(exchange.getRequest().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME)).isNull();
    }

    @Test
    void preservesSafeIncomingId() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42")
                        .header(RequestIdGlobalFilter.HEADER_NAME, "req-42_A.b")
                        .build());
        var forwardedExchange = new AtomicReference<ServerWebExchange>();

        GatewayFilterChain chain = nextExchange -> {
            forwardedExchange.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain)).verifyComplete();

        assertThat(forwardedExchange.get().getRequest().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME)).isEqualTo("req-42_A.b");
    }

    @Test
    void replacesInvalidIncomingId() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42")
                        .header(RequestIdGlobalFilter.HEADER_NAME, "invalid request id")
                        .build());
        var forwardedExchange = new AtomicReference<ServerWebExchange>();

        GatewayFilterChain chain = nextExchange -> {
            forwardedExchange.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain)).verifyComplete();

        String requestId = forwardedExchange.get().getRequest().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME);
        assertThat(requestId).isNotEqualTo("invalid request id");
        assertThatCodeCanParseUuid(requestId);
    }

    @Test
    void runsOnReactorNonBlockingScheduler() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42").build());
        var ranOnNonBlockingThread = new AtomicBoolean(false);

        GatewayFilterChain chain = nextExchange -> {
            ranOnNonBlockingThread.set(Schedulers.isInNonBlockingThread());
            return Mono.empty();
        };

        StepVerifier.create(Mono.defer(() -> filter.filter(exchange, chain))
                        .subscribeOn(Schedulers.parallel()))
                .verifyComplete();

        assertThat(ranOnNonBlockingThread).isTrue();
    }

    private static void assertThatCodeCanParseUuid(String value) {
        assertThat(UUID.fromString(value)).isNotNull();
    }
}
```

The tests use `StepVerifier` to subscribe and verify the publisher completes. The final test runs the filter on `Schedulers.parallel()`, where Reactor marks threads as non-blocking; with BlockHound installed, blocking calls detected by BlockHound on this thread fail the test. These unit tests do not replace integration or load testing, but they catch bugs such as `Thread.sleep`, synchronous file/socket operations, and common blocking APIs early.

If BlockHound fails to install in the test JVM, check the instrumentation compatibility guide for your BlockHound/JDK versions. Never ignore instrumentation failures and treat the test as confirming non-blocking behavior.

## 5. Running and Observing in Practice

Start the orders service on `localhost:9081`, then start the Gateway. Send a request without a request ID:

```bash
curl -i http://localhost:8080/api/orders/42
```

The response must include an `X-Request-Id` header containing a UUID. Check logs or traces in the orders service to confirm upstream also received the same header.

Send a request with a valid ID:

```bash
curl -i -H "X-Request-Id: lab-2026-42" \
  http://localhost:8080/api/orders/42
```

The Gateway preserves `lab-2026-42` on both the upstream request and the response. Send a value containing spaces to confirm the filter replaces it with a new UUID:

```bash
curl -i -H "X-Request-Id: invalid request id" \
  http://localhost:8080/api/orders/42
```

Run the unit tests with Maven:

```bash
mvn -Dtest=RequestIdGlobalFilterTest test
```

If you want to verify that BlockHound genuinely catches blocking calls, you can write a temporary test running `Thread.sleep(...)` on `Schedulers.parallel()` and assert the publisher emits a `BlockingOperationError`. Delete that temporary test afterward or keep it explicitly as an instrumentation check; never put blocking calls into a production filter.

## 6. Coding Patterns That Block the Event Loop

Never write snippets like the following inside a `GlobalFilter` or any callback executing on the event loop:

```java
// Wrong: waits for the publisher to finish synchronously on the current thread.
String body = webClient.get()
        .uri("http://orders-service/health")
        .retrieve()
        .bodyToMono(String.class)
        .block();

// Wrong: blocks the thread while handling a request.
Thread.sleep(100);

// Wrong: blocks waiting on a Future synchronously.
String result = future.get();
```

Instead, compose the publisher into the reactive chain:

```java
return webClient.get()
        .uri("http://orders-service/metadata")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(metadata -> {
            ServerHttpRequest request = exchange.getRequest().mutate()
                    .headers(headers -> headers.set("X-Service-Metadata", metadata))
                    .build();
            return chain.filter(exchange.mutate().request(request).build());
        });
```

If you must invoke a legacy blocking library, wrap the call in a deferred publisher and shift the source to `boundedElastic`:

```java
return Mono.fromCallable(() -> legacyClient.lookupMetadata(serviceId))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(metadata -> {
            ServerHttpRequest request = exchange.getRequest().mutate()
                    .headers(headers -> headers.set("X-Service-Metadata", metadata))
                    .build();
            return chain.filter(exchange.mutate().request(request).build());
        });
```

`Mono.fromCallable` defers the call until subscription; `subscribeOn(Schedulers.boundedElastic())` shifts the blocking source onto the scheduler dedicated to blocking work. Do not call `legacyClient.lookupMetadata(...)` before creating the `Mono`, because then the call executes immediately on the current thread. Also do not treat `publishOn` as a universal fix for blocking calls: it switches downstream signal processing after that operator, but does not move a call that already executed before the publisher was created.

Prefer replacing JDBC or synchronous HTTP clients with R2DBC, `WebClient`, or equivalent reactive APIs when the architecture permits. `boundedElastic` is an isolation boundary for legacy blocking calls, not a license to turn the entire Gateway into a chain of synchronous waits. Set timeouts, cap concurrency, and monitor scheduler queues to avoid exhausting resources when upstream slows down.

## 7. Completion Checklist

- [ ] Gateway uses the proper WebFlux starter and a compatible Spring Cloud BOM.
- [ ] Route `/api/orders/**` forwards requests to the right upstream and rewrites the path accurately.
- [ ] `X-Request-Id` is generated when missing or malformed; valid IDs are preserved.
- [ ] Upstream request and client response carry the same request ID.
- [ ] Unit tests confirm the exchange is mutated, the chain is invoked, and the publisher completes.
- [ ] BlockHound installs cleanly and tests execute on a Reactor non-blocking scheduler.
- [ ] No `.block()`, `Future.get()`, `Thread.sleep`, JDBC, or synchronous I/O exists on the event loop path.
- [ ] Unavoidable blocking work is isolated with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and appropriately bounded.
- [ ] Correlation headers are never used as a substitute for authentication or authorization.

## References

- [Spring Cloud Gateway — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): lifecycle, ordering, and combining global filters with per-route filters.
- [Spring Cloud Gateway — Writing Custom Route Predicate Factories and GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/writing-custom-route-predicate-factories-and-gatewayfilter-factories.html): how to extend per-route filters.
- [Project Reactor — Blocking Can Be Caught](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): guidance on isolating blocking calls with `fromCallable` and `boundedElastic`.
- [BlockHound](https://github.com/reactor/BlockHound): tool for detecting blocking calls on threads where blocking is disallowed.

A well-written custom filter keeps event-loop processing brief, avoids synchronous I/O, and returns the Gateway filter chain publisher. Use unit tests to lock down header and exchange behavior, BlockHound to catch common blocking calls, and integration tests against upstream services to confirm real requests flow through the Gateway as designed.
