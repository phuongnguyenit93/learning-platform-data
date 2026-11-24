# Request Attributes and Passing Data via Reactor Context in Spring WebFlux WebClient

## 1. Objectives

When calling HTTP services with `WebClient`, applications often need to pass additional metadata along with a request: a correlation ID for tracing, a tenant ID, an operation name, tracing data, or data for filters. Some metadata is only needed for **a single outgoing request**; other metadata must travel across the entire reactive sequence, including nested requests called inside `flatMap` or `concatMap`.

Spring WebFlux provides two distinct mechanisms:

- **WebClient request attributes:** store metadata on a specific `ClientRequest`. Filters can read attributes to decide how to handle that request.
- **Reactor Context:** stores metadata scoped to a subscriber/reactive sequence. Operators and WebClient requests composed in the same reactive chain can read the same Context.

The key point to remember is that attributes and Reactor Context are both application-internal metadata. They are **not automatically sent over HTTP**. If the target service needs to receive a value, a filter must convert it into a header, query parameter, cookie, or part of the request body per the API contract.

This lesson focuses on:

- Attaching attributes to a request with `attribute(...)` or `attributes(...)`.
- Reading attributes inside `ExchangeFilterFunction` via `ClientRequest.attribute(...)`.
- Using `defaultRequest(...)` to add default metadata to every request.
- Writing data into Reactor Context with `contextWrite(...)`.
- Reading Context inside a filter with `Mono.deferContextual(...)`.
- Propagating correlation IDs or metadata to nested WebClient calls.
- Understanding `contextWrite` placement, immutability, and propagation boundaries.
- Avoiding reliance on `ThreadLocal` or manual `subscribe()` calls in reactive flows.
- Testing both request attributes and Reactor Context using StepVerifier.

The core APIs in this lesson have existed since Spring Framework 5.x and remain usable on Spring Framework 6.2/7.0. Examples use Java 17+, compatible Spring Boot 3.x/4.x, and Reactor.

## 2. Distinguishing Request Attributes, Reactor Context, and HTTP Headers

The three concepts can carry the same value yet differ in scope and how they propagate:

| Mechanism | Scope | Who can read it? | Automatically sent over the network? |
| --- | --- | --- | --- |
| WebClient request attribute | One outgoing ClientRequest | Filters for that request and components handling ClientRequest | No |
| Reactor Context | One subscriber/reactive chain | Reactor operators, WebClient filters, and Context-integrated libraries | No |
| HTTP header | One actual HTTP request | The receiving server and intermediate proxies | Yes |

For example, suppose you want to send the correlation ID `req-42`:

- An attribute `operation=read-order` may help a filter set an appropriate header only for the current request.
- Reactor Context can hold `correlationId=req-42` across a chain consisting of multiple WebClient requests.
- The header `X-Correlation-Id: req-42` is the data actually sent to the remote HTTP service.

You can visualize this as:

```text
Reactive request chain
        |
        | contextWrite(correlationId = req-42)
        v
  Reactor Context
        |
        +---- WebClient call A
        |         |
        |         +-- request attribute: operation = read-order
        |         |
        |         +-- ExchangeFilterFunction reads attribute
        |         +-- ExchangeFilterFunction reads Context
        |         +-- creates HTTP headers
        |
        +---- flatMap(...)
                  |
                  +---- WebClient call B
                            |
                            +-- reads correlationId again from Context
                            +-- creates HTTP header
```

Call A's request attribute does not automatically appear on call B. Reactor Context can be read by call B if call B is composed within the same reactive chain.

## 3. Request Attributes in WebClient

### 3.1. Adding Attributes to a Request

WebClient provides `attribute(String name, Object value)` on the request specification:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute("operation", "read-order")
        .retrieve()
        .bodyToMono(String.class);
```

The attribute is attached to the request being built. The value can be a String, enum, small record, or other internal object. Prefer small, immutable, well-typed metadata.

Multiple attributes can be attached:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute("operation", "read-order")
        .attribute("tenantId", tenantId)
        .attribute("requestTag", "orders-screen")
        .retrieve()
        .bodyToMono(String.class);
```

Or added via a map Consumer:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attributes(attributes -> {
            attributes.put("operation", "read-order");
            attributes.put("requestTag", "orders-screen");
        })
        .retrieve()
        .bodyToMono(String.class);
```

Both approaches serve the same purpose. Use `attribute(...)` when adding a single value; use `attributes(...)` when adding a group of values.

### 3.2. Reading Attributes in ExchangeFilterFunction

A filter can read an attribute via `ClientRequest.attribute(name)`. The return value is `Optional<Object>`:

```java
WebClient client = WebClient.builder()
        .filter((request, next) -> {
            Optional<Object> operation =
                    request.attribute("operation");

            operation.ifPresent(value ->
                    System.out.println("operation=" + value));

            return next.exchange(request);
        })
        .build();
```

This is a logging illustration. In production, do not log sensitive data or arbitrary attribute values.

If the filter needs to modify the HTTP request, build a new request with `ClientRequest.from(request)`:

```java
ExchangeFilterFunction operationHeaderFilter =
        (request, next) -> {
            ClientRequest.Builder builder =
                    ClientRequest.from(request);

            request.attribute("operation").ifPresent(value ->
                    builder.headers(headers ->
                            headers.set(
                                    "X-Client-Operation",
                                    value.toString())));

            return next.exchange(builder.build());
        };
```

In this example:

1. The filter reads the `operation` attribute from the current request.
2. If present, the filter adds the `X-Client-Operation` header.
3. The filter builds a new ClientRequest and calls `next.exchange(...)`.
4. The target service only sees the HTTP header; it does not see the internal attribute map.

Do not attempt to mutate an already-built ClientRequest. ClientRequest is immutable; use a builder from `ClientRequest.from(request)` to construct a replacement.

### 3.3. Attributes Are Not Headers

If you write:

```java
webClient.get()
        .uri("/orders/42")
        .attribute("tenantId", "tenant-17")
        .retrieve()
        .bodyToMono(String.class);
```

the request does not automatically get a `tenantId: tenant-17` header. The attribute remains strictly inside ClientRequest's internal metadata.

To send that value over HTTP, you must map it explicitly to a request component:

```java
ExchangeFilterFunction tenantHeaderFilter =
        (request, next) -> {
            ClientRequest.Builder builder =
                    ClientRequest.from(request);

            request.attribute("tenantId").ifPresent(value ->
                    builder.headers(headers ->
                            headers.set(
                                    "X-Tenant-Id",
                                    value.toString())));

            return next.exchange(builder.build());
        };
```

Only do so if the target service's contract accepts this header. Never take an arbitrary tenant ID from a client and forward it without verifying tenant access permissions.

### 3.4. Attributes Affect Only the Current Request

Suppose a service executes two requests:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute("operation", "read-order")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(order -> webClient.get()
                .uri("/orders/42/audit")
                .retrieve()
                .bodyToMono(String.class));
```

The first request has the attribute `operation=read-order`. The second request is a brand-new ClientRequest; that attribute is not automatically copied to the second request.

If both requests need the same metadata, you can attach the attribute to each request, use `defaultRequest(...)` for default metadata, or use Reactor Context if the data must propagate across the reactive chain.

### 3.5. defaultRequest to Add Default Attributes

WebClient.Builder has a `defaultRequest(...)` callback to customize every created request:

```java
WebClient client = WebClient.builder()
        .defaultRequest(spec ->
                spec.attribute("clientName", "orders-service"))
        .filter((request, next) -> {
            String clientName = request.attribute("clientName")
                    .map(Object::toString)
                    .orElse("unknown");

            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Client-Name", clientName)
                    .build();

            return next.exchange(updated);
        })
        .build();
```

This fits static or default client metadata such as service name, client type, or API group. It does not replace Reactor Context for data that varies per subscriber/request chain.

## 4. ExchangeFilterFunction and Filter Lifecycle

### 4.1. Filters as a Cross-Cutting Request Hook

`ExchangeFilterFunction` allows intercepting before and after WebClient sends a request:

```java
ExchangeFilterFunction filter =
        (request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Client-Name", "orders-service")
                    .build();

            return next.exchange(updated);
        };
```

Filters are suitable for:

- Adding a correlation ID to requests.
- Adding client/service metadata headers.
- Attaching authentication headers using an appropriate mechanism.
- Logging sanitized request metadata.
- Measuring request duration.
- Handling retries/token refreshes per an explicit contract.

Filters are registered via `WebClient.Builder.filter(...)`. Multiple filters form a chain. Registration order determines the order in which requests pass through the filters.

### 4.2. Preserving the Response Body When a Filter Intervenes

Filters usually return the result of `next.exchange(...)` so WebClient can proceed to decode the response. If a filter reads the response body itself to inspect status or retry, it must consume the body or forward it to the next component.

For example, when receiving 401 and wanting to retry after refreshing a token, release the first response's body before resending:

```java
return next.exchange(request)
        .flatMap(response -> {
            if (response.statusCode().value() == 401) {
                return response.releaseBody()
                        .then(refreshToken())
                        .flatMap(token -> {
                            ClientRequest retryRequest =
                                    ClientRequest.from(request)
                                            .headers(headers ->
                                                    headers.setBearerAuth(token))
                                            .build();

                            return next.exchange(retryRequest);
                        });
            }

            return Mono.just(response);
        });
```

This is an illustrative skeleton; `refreshToken()` must return a publisher and handle tokens safely. Never discard a response body without releasing/consuming it, as doing so can retain connection or buffer resources.

### 4.3. Filters Should Not Subscribe Manually

Incorrect:

```java
.filter((request, next) -> {
    next.exchange(request).subscribe();
    return Mono.empty();
})
```

This creates a separate subscription and drops the response of the request managed by WebClient. Errors, cancellation, and body lifecycle are detached from the caller.

Correct:

```java
.filter((request, next) ->
        next.exchange(request))
```

Or compose pre/post-exchange operations using `flatMap`, `map`, and other Reactor operators and return the publisher to WebClient.

## 5. What Is Reactor Context?

Reactor Context is a key-value structure attached to the **Subscriber** of a reactive sequence. It is designed to pass metadata across an operator chain without relying on the current thread.

Key characteristics:

- Context is attached to the subscriber and accessed during subscription.
- Context is immutable: `put(...)` returns a new Context rather than mutating the existing object.
- Context data propagates from downstream to upstream along the subscription.
- Reactor-native operators can read Context using `deferContextual(...)` or `transformDeferredContextual(...)`.
- WebClient filters can read Context to add metadata to requests.
- Nested WebClient calls in the same reactive chain can receive the same Context.
- Context does not automatically become HTTP headers and does not propagate across an independent subscription.

Simple example:

```java
private static final String USER_KEY = "currentUser";

Mono<String> greeting = Mono.deferContextual(context ->
        Mono.just("Hello " + context.get(USER_KEY)));

Mono<String> result = greeting.contextWrite(context ->
        context.put(USER_KEY, "An"));
```

Upon subscribing, the output is:

```text
Hello An
```

`contextWrite(...)` attaches the Context to the subscription. `deferContextual(...)` reads the value when the publisher is subscribed to, because Context is only available during the subscription lifecycle.

### 5.1. Context Is Not a Directly Mutable Map

Example:

```java
Context updated = Context.empty()
        .put("correlationId", "req-42");
```

`put(...)` returns a new Context. You must use the returned Context:

```java
.contextWrite(context -> context.put("correlationId", "req-42"))
```

Do not expect calling `context.put(...)` to mutate the old Context. Nor should you store mutable objects and mutate their contents while multiple operators read concurrently; prefer immutable records/value objects.

### 5.2. Reading Context with deferContextual

`Mono.deferContextual` creates a publisher based on the Context available at subscription time:

```java
Mono<String> correlationId = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault(
                "correlationId", "not-provided")));
```

If the key is absent, this returns `not-provided`. If you need to distinguish a missing key from a default value, use `hasKey(...)` or `getOrEmpty(...)`.

Inside a WebClient filter, this read pattern allows the filter to receive metadata from the calling chain without passing parameters through every method.

## 6. Writing Data to Context with contextWrite

### 6.1. Placing contextWrite at the End of the Reactive Chain

Example:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(order -> webClient.get()
                .uri("/orders/42/audit")
                .retrieve()
                .bodyToMono(String.class)
                .map(audit -> order + " | " + audit))
        .contextWrite(context ->
                context.put("correlationId", "req-42"));
```

Context is attached at the end of the chain so upstream operators and WebClient calls can read it.

Rule of thumb: **subscription and Context flow from the end of the chain toward the start of the chain**. Thus, the placement of `contextWrite` determines which operators can see the value.

### 6.2. Common Placement Mistake

The example below writes Context too early in the chain:

```java
Mono<String> wrong = Mono.just("start")
        .contextWrite(context ->
                context.put("correlationId", "req-42"))
        .flatMap(value ->
                Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                                "correlationId", "missing"))));
```

The result is:

```text
missing
```

Reason: `contextWrite` sits upstream of the `flatMap` operator in the chain, so its Context is not passed down to flatMap's inner subscriber for that operator to read.

Correct approach:

```java
Mono<String> correct = Mono.just("start")
        .flatMap(value ->
                Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                                "correlationId", "missing"))))
        .contextWrite(context ->
                context.put("correlationId", "req-42"));
```

Result:

```text
req-42
```

When reading Context inside a nested publisher, check which operator creates the subscription and where `contextWrite` sits in that sequence. Do not simply read top-to-bottom code order and assume Context behaves like local variables.

### 6.3. Multiple contextWrite Calls for the Same Key

If the same key is written multiple times, the value an operator sees depends on the positions of the writes in the chain. Context is immutable, and each `contextWrite` creates a new Context for the upstream portion.

Example:

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("message")))
    .contextWrite(context -> context.put("message", "Reactor"))
    .contextWrite(context -> context.put("message", "World"));
```

The `deferContextual` operator sees `Reactor` because that write is closer to it along the propagation path. Avoid writing the same key at multiple layers without a clear reason; establish one owner for metadata so code stays easy to follow.

## 7. Using Reactor Context in a WebClient Filter

### 7.1. Reading Context and Converting It to an HTTP Header

A filter can read a correlation ID from Reactor Context:

```java
private static final Object CORRELATION_ID =
        CorrelationContext.class;

ExchangeFilterFunction correlationFilter =
        (request, next) ->
                Mono.deferContextual(contextView -> {
                    ClientRequest.Builder builder =
                            ClientRequest.from(request);

                    if (contextView.hasKey(CORRELATION_ID)) {
                        String correlationId =
                                contextView.get(CORRELATION_ID);

                        builder.headers(headers ->
                                headers.set(
                                        "X-Correlation-Id",
                                        correlationId));
                    }

                    return next.exchange(builder.build());
                });
```

In this example:

- The Context key is a unique object/class key, avoiding collisions with keys from other libraries.
- `Mono.deferContextual(...)` reads Context only when the request executes.
- The filter builds a new ClientRequest and adds the header.
- The value is only sent over HTTP after the filter maps it into a header.

The header name must match the contract between services. If a gateway or target service uses a different name, agree on it before deployment.

### 7.2. Why Is deferContextual Necessary?

If a filter tries to read Context directly when initializing WebClient or configuring a bean, it has no per-subscription Context. Context is only attached when the reactive chain is subscribed to.

`Mono.deferContextual(...)` defers reading until that moment, allowing a single WebClient to serve many concurrent requests while each request receives its own correlation ID.

Do not store the previous request's correlation ID in a mutable field of a singleton WebClient/filter. A single filter can serve many concurrent requests; shared mutable state causes metadata leakage across requests.

## 8. Attributes and Context in the Same WebClient

Both mechanisms can be used together. Attributes suit an action specific to the current request; Context suits metadata spanning an entire chain.

Example of a filter handling both:

```java
private static final String OPERATION = "operation";
private static final Object CORRELATION_ID = RequestContextKeys.class;

ExchangeFilterFunction metadataFilter =
        (request, next) ->
                Mono.deferContextual(contextView -> {
                    ClientRequest.Builder builder =
                            ClientRequest.from(request);

                    request.attribute(OPERATION).ifPresent(value ->
                            builder.headers(headers ->
                                    headers.set(
                                            "X-Client-Operation",
                                            value.toString())));

                    if (contextView.hasKey(CORRELATION_ID)) {
                        String id = contextView.get(CORRELATION_ID);

                        builder.headers(headers ->
                                headers.set("X-Correlation-Id", id));
                    }

                    return next.exchange(builder.build());
                });
```

When invoked:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute(OPERATION, "read-order")
        .retrieve()
        .bodyToMono(String.class)
        .contextWrite(context ->
                context.put(CORRELATION_ID, "req-42"));
```

The filter produces two headers:

```http
X-Client-Operation: read-order
X-Correlation-Id: req-42
```

The first header comes from the request attribute. The second header comes from Reactor Context.

If a subsequent request is created inside `flatMap`, it still reads the correlation ID from Context. The operation attribute exists only on the request where it was attached; the next request must attach its own attribute if it also needs an operation header.

## 9. Complete Spring Boot WebFlux Example

This example uses Java 17+, compatible Spring Boot 3.x or 4.x, and WebFlux. A service calls a partner service twice: reading an order and then reading its audit log. The correlation ID flows via Reactor Context so both requests share the same ID; the operation attribute is attached only to the order-read request.

### 9.1. Dependencies

The `build.gradle` file requires:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

The project needs the Spring Boot Gradle plugin and compatible dependency management. Use Boot's BOM to manage Spring Framework and Reactor; do not separately override reactor-core or spring-webflux.

### 9.2. Context Key

File `src/main/java/demo/RequestContextKeys.java`:

```java
package demo;

public final class RequestContextKeys {

    public static final Object CORRELATION_ID =
            RequestContextKeys.class;

    private RequestContextKeys() {
    }
}
```

Use a Class object as the key to reduce the risk of name collisions with keys from other libraries. The key must be used consistently by both service and filter.

### 9.3. WebClient Configuration

File `src/main/java/demo/PartnerWebClientConfiguration.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfiguration {

    public static final String OPERATION_ATTRIBUTE = "operation";

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example")
                .filter((request, next) ->
                        Mono.deferContextual(contextView -> {
                            ClientRequest.Builder updated =
                                    ClientRequest.from(request);

                            request.attribute(OPERATION_ATTRIBUTE)
                                    .ifPresent(value ->
                                            updated.headers(headers ->
                                                    headers.set(
                                                            "X-Client-Operation",
                                                            value.toString())));

                            if (contextView.hasKey(
                                    RequestContextKeys.CORRELATION_ID)) {

                                String correlationId =
                                        contextView.get(
                                                RequestContextKeys.CORRELATION_ID);

                                updated.headers(headers ->
                                        headers.set(
                                                "X-Correlation-Id",
                                                correlationId));
                            }

                            return next.exchange(updated.build());
                        }))
                .build();
    }
}
```

Spring Boot provides an auto-configured `WebClient.Builder` when the WebFlux starter is present. If using plain Spring Framework, replace the builder parameter with `WebClient.builder()`.

The filter adds headers only when corresponding data is present. It does not write the correlation ID to a bean field, because the WebClient bean is a singleton used concurrently.

### 9.4. Service Making Two Nested Requests

File `src/main/java/demo/PartnerOrderService.java`:

```java
package demo;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

import static demo.PartnerWebClientConfiguration.OPERATION_ATTRIBUTE;
import static demo.RequestContextKeys.CORRELATION_ID;

@Service
public class PartnerOrderService {

    private final WebClient partnerWebClient;

    public PartnerOrderService(WebClient partnerWebClient) {
        this.partnerWebClient = partnerWebClient;
    }

    public Mono<OrderView> findOrder(
            String orderId,
            String correlationId) {

        return partnerWebClient.get()
                .uri("/orders/{id}", orderId)
                .attribute(OPERATION_ATTRIBUTE, "read-order")
                .retrieve()
                .bodyToMono(PartnerOrder.class)
                .flatMap(order ->
                        partnerWebClient.get()
                                .uri("/orders/{id}/audit", orderId)
                                .retrieve()
                                .bodyToMono(PartnerAudit.class)
                                .map(audit -> new OrderView(
                                        order.id(),
                                        order.status(),
                                        audit.lastAction())))
                .contextWrite(context ->
                        context.put(CORRELATION_ID, correlationId));
    }

    public record PartnerOrder(String id, String status) {
    }

    public record PartnerAudit(String lastAction) {
    }

    public record OrderView(
            String id,
            String status,
            String lastAction) {
    }
}
```

The first request has both the operation attribute and the correlation Context. The second request is created inside `flatMap`: it does not have the first request's operation attribute, yet still receives the correlation ID from Context because the publishers are composed within the same reactive chain.

If you also want the audit request to carry operation metadata, add:

```java
.attribute(OPERATION_ATTRIBUTE, "read-order-audit")
```

to the second request.

### 9.5. Controller Receiving the Correlation ID

File `src/main/java/demo/PartnerOrderController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class PartnerOrderController {

    private final PartnerOrderService service;

    public PartnerOrderController(PartnerOrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<PartnerOrderService.OrderView> find(
            @PathVariable String id,
            @RequestHeader("X-Correlation-Id") String correlationId) {

        return service.findOrder(id, correlationId);
    }
}
```

This is an illustrative input example. In production, the correlation ID should be generated or validated at a trusted filter/gateway; never use a correlation ID to authenticate users or grant permissions.

## 10. Testing Attributes and Context with StepVerifier

You can test filters without real network calls by providing a mock `ExchangeFunction`. The test records the `ClientRequest` instances passed down to the exchange function.

File `src/test/java/demo/WebClientMetadataTest.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static demo.PartnerWebClientConfiguration.OPERATION_ATTRIBUTE;
import static demo.RequestContextKeys.CORRELATION_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class WebClientMetadataTest {

    @Test
    void requestAttributeAppliesOnlyToTheRequestThatCarriesIt() {
        List<ClientRequest> captured = new ArrayList<>();
        WebClient client = createClient(captured);

        Mono<String> result = client.get()
                .uri("https://example.test/first")
                .attribute(OPERATION_ATTRIBUTE, "read-order")
                .retrieve()
                .bodyToMono(String.class)
                .flatMap(first -> client.get()
                        .uri("https://example.test/second")
                        .retrieve()
                        .bodyToMono(String.class)
                        .map(second -> first + second));

        StepVerifier.create(result)
                .expectNext("/first/second")
                .verifyComplete();

        assertEquals(2, captured.size());
        assertEquals(
                "read-order",
                captured.get(0).headers()
                        .getFirst("X-Client-Operation"));
        assertNull(captured.get(1).headers()
                .getFirst("X-Client-Operation"));
    }

    @Test
    void reactorContextPropagatesToNestedWebClientRequests() {
        List<ClientRequest> captured = new ArrayList<>();
        WebClient client = createClient(captured);

        Mono<String> result = client.get()
                .uri("https://example.test/first")
                .retrieve()
                .bodyToMono(String.class)
                .flatMap(first -> client.get()
                        .uri("https://example.test/second")
                        .retrieve()
                        .bodyToMono(String.class)
                        .map(second -> first + second))
                .contextWrite(context ->
                        context.put(CORRELATION_ID, "req-42"));

        StepVerifier.create(result)
                .expectNext("/first/second")
                .verifyComplete();

        assertEquals(2, captured.size());

        assertEquals(
                "req-42",
                captured.get(0).headers()
                        .getFirst("X-Correlation-Id"));

        assertEquals(
                "req-42",
                captured.get(1).headers()
                        .getFirst("X-Correlation-Id"));
    }

    @Test
    void contextWriteMustBeDownstreamOfTheOperatorThatReadsIt() {
        Mono<String> wrong = Mono.just("start")
                .contextWrite(context ->
                        context.put(CORRELATION_ID, "req-42"))
                .flatMap(value ->
                        Mono.deferContextual(context ->
                                Mono.just(context.getOrDefault(
                                        CORRELATION_ID, "missing"))));

        StepVerifier.create(wrong)
                .expectNext("missing")
                .verifyComplete();

        Mono<String> correct = Mono.just("start")
                .flatMap(value ->
                        Mono.deferContextual(context ->
                                Mono.just(context.getOrDefault(
                                        CORRELATION_ID, "missing"))))
                .contextWrite(context ->
                        context.put(CORRELATION_ID, "req-42"));

        StepVerifier.create(correct)
                .expectNext("req-42")
                .verifyComplete();
    }

    private WebClient createClient(List<ClientRequest> captured) {
        ExchangeFunction exchange = request -> {
            captured.add(request);

            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(
                            HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body(request.url().getPath())
                    .build());
        };

        return WebClient.builder()
                .filter((request, next) ->
                        Mono.deferContextual(contextView -> {
                            ClientRequest.Builder updated =
                                    ClientRequest.from(request);

                            request.attribute(OPERATION_ATTRIBUTE)
                                    .ifPresent(value ->
                                            updated.headers(headers ->
                                                    headers.set(
                                                            "X-Client-Operation",
                                                            value.toString())));

                            if (contextView.hasKey(CORRELATION_ID)) {
                                String id = contextView.get(CORRELATION_ID);

                                updated.headers(headers ->
                                        headers.set("X-Correlation-Id", id));
                            }

                            return next.exchange(updated.build());
                        }))
                .exchangeFunction(exchange)
                .build();
    }
}
```

The tests verify:

- Attributes are converted into headers on the request carrying them.
- Nested requests do not automatically inherit the previous request's attributes.
- Reactor Context is visible to both WebClient requests in the same chain.
- Misplacing `contextWrite` prevents the operator from reading the key; placing it at the end of the chain yields the expected result.

Run tests:

```bash
./gradlew test
```

The tests use a mock ExchangeFunction, so no external HTTP service is needed. If you want integration tests through a real server, use WireMock, MockWebServer, or a dedicated test endpoint and verify the received headers.

## 11. Reactor Context, ThreadLocal, and MDC

### 11.1. Why Is ThreadLocal Unsuitable as a Reactive Metadata Source?

In the imperative model, a request is typically handled on one thread; ThreadLocal can hold a request ID on that thread. In a reactive pipeline, a request may continue on another thread after `publishOn`, `subscribeOn`, or when I/O completes.

Therefore, do not assume:

```java
ThreadLocal<String> correlationId = new ThreadLocal<>();
```

will preserve the right request ID throughout a WebFlux pipeline. Many requests can share an event-loop thread; ThreadLocal data risks being lost or mixed up if managed improperly.

Reactor Context attaches to the subscriber rather than the thread, making it a better fit for request-scoped metadata in reactive flows.

### 11.2. Integrating with Micrometer Context Propagation

If you must integrate legacy libraries that rely on ThreadLocal or MDC, you can use `io.micrometer:context-propagation` and corresponding accessors to bridge between Context and ThreadLocal.

Reactor supports this SPI starting in version 3.5. Depending on configuration, there is a bounded default propagation mode or automatic mode via hooks. Enable automatic propagation only after understanding its impact on the entire application and all ThreadLocal-based libraries.

You do not need Context Propagation just to read Reactor Context inside a WebClient filter; `deferContextual(...)` already handles that directly.

### 11.3. Spring Security Uses Reactive Context

Spring Security reactive stores the `SecurityContext` using the reactive context mechanism and provides `ReactiveSecurityContextHolder` for access. When you need identity/authorities, prefer Spring Security APIs rather than placing a user role in an attribute and treating it as proof of authentication.

Reactor Context is a metadata-passing mechanism; it does not authenticate users, encrypt data, or replace authorization.

## 12. Boundaries and Security Principles

### 12.1. Do Not Let Internal Metadata Leak Outbound

An attribute may hold complex objects, internal IDs, or sensitive information. It should only be mapped to HTTP if the contract permits it. Never write a filter that blindly turns every attribute into a header; doing so easily leaks internal metadata or sends invalid values.

Only map allowlisted keys:

```java
request.attribute("correlationId").ifPresent(value ->
        headers.set("X-Correlation-Id", value.toString()));
```

Do not iterate over the entire attributes map and copy it as header names/values.

### 12.2. Do Not Use Unverified Tenant IDs

If Context holds a tenant ID, the value should come from a trusted authentication/authorization layer or be verified before calling downstream services. Do not trust a tenant ID sent by a browser and forward it to a partner service to govern data access.

### 12.3. Do Not Store Large or Mutable Objects in Context

Context travels with the subscription and may be read by many operators. Avoid putting large request bodies, DataBuffers, mutable entities, or short-lived objects in Context. Store only small, immutable metadata meaningful across the chain.

### 12.4. Avoid Logging Secrets

Do not put access tokens, refresh tokens, cookies, session IDs, or personal data in logs merely because filters can read them. When debugging is needed, log the correlation ID and sanitized error codes; never dump the entire Context or attributes map.

### 12.5. Do Not Mix Context Across Requests

Never use a static mutable map to hold request metadata. Each subscriber has its own Context; values from request A must never be written to shared state and read back in request B.

If global caches or configurations need to be shared, use caching/configuration mechanisms with clear concurrency policies, not Reactor Context.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking attributes automatically become HTTP headers | Target service never receives the value | Map attributes to headers/query/body in a filter |
| Using attributes across multiple nested calls | Subsequent requests lack metadata | Attach attributes per request or use Reactor Context |
| Reading Context outside a reactive subscription | No Context exists for the current request | Use deferContextual inside operators/filters |
| Placing contextWrite too early | Downstream operators cannot see the key | Place contextWrite at the end of the corresponding chain |
| Thinking Context is ThreadLocal | Data lost or mixed across thread switches | Use Reactor Context |
| Thinking Context is a mutable Map | Written values do not appear elsewhere | Remember put returns a new Context; compose contextWrite |
| Firing nested WebClient calls via separate subscribe | Context propagation and error/cancel lifecycle break | Return/compose publishers via flatMap/concatMap |
| Storing correlation ID in a singleton filter field | Concurrent requests may use the wrong ID | Read the ID from Context per subscription |
| Converting all attributes into headers | Leaks internal metadata | Allowlist each attribute permitted to travel outbound |
| Using client-supplied tenant ID for authorization | Risk of cross-tenant access | Derive tenant from the authenticated principal |
| Putting access tokens in Context and logging all of it | Credential leakage | Never log Context/attributes containing secrets |
| Filter reads response without releasing body | Retains buffers/connections or causes leaks | Consume, release, or forward the response downstream |
| Filter subscribes manually | Loses connection to caller and HTTP lifecycle | Return the publisher from the filter |
| Using ThreadLocal to store request metadata in WebFlux | Thread-dependent values that can hit the wrong request | Use Reactor Context; bridge intentionally if needed |
| Using Context to pass large payloads | Increases memory usage and complicates lifecycle | Pass payloads via dedicated publishers/bodies |
| Writing the same Context key at multiple layers | Values depend on operator ordering | Use unique keys and a single clear write point |

## 14. Implementation Checklist

Before adding request metadata for WebClient, check:

1. Is the metadata for a single request or must it propagate across multiple nested calls?
2. If for a single request, are `attribute(...)` or `attributes(...)` applied to the right request?
3. If needed across the reactive chain, is Reactor Context used?
4. Does the filter read attributes via `ClientRequest.attribute(...)` and Context via `Mono.deferContextual(...)` within the proper lifecycle?
5. Is `contextWrite(...)` placed where the reading operators can see the values?
6. If the target service needs the value, does the filter explicitly map it to an HTTP header/query/body per contract?
7. Are nested WebClient calls composed via `flatMap`/`concatMap` and returning publishers?
8. Are there any manual `subscribe` or `block` calls breaking Context propagation?
9. Is ThreadLocal/MDC used? If so, has an appropriate bridging mechanism been chosen?
10. Are Context keys unique and values small and immutable?
11. Is sensitive metadata prevented from being logged or sent outbound unintentionally?
12. Do tests verify that request attributes apply only to the current request and Context propagates to nested calls?
13. Does the filter always properly consume/release or forward the response body?
14. Is authorization checked before passing tenant/user metadata to other services?

## 15. API Selection Summary

| Need | Mechanism |
| --- | --- |
| Add metadata to one WebClient request | `RequestHeadersSpec.attribute(name, value)` |
| Add multiple metadata entries to one request | `RequestHeadersSpec.attributes(Consumer<Map<String,Object>>)` |
| Add default metadata to every request | `WebClient.Builder.defaultRequest(...)` |
| Read metadata inside a filter | `ClientRequest.attribute(name)` or `ClientRequest.attributes()` |
| Create a new request inside a filter | `ClientRequest.from(request)` |
| Add metadata to a reactive chain | `contextWrite(...)` |
| Read metadata inside an operator/filter | `Mono.deferContextual(...)` |
| Read Context mid-chain | `transformDeferredContextual(...)` |
| Check whether a key exists | `ContextView.hasKey(...)` |
| Read a value with fallback | `ContextView.getOrDefault(...)` |
| Read a value as Optional | `ContextView.getOrEmpty(...)` |
| Test publishers and Context | `StepVerifier` |
| Bridge ThreadLocal when truly necessary | `io.micrometer:context-propagation` |

## 16. Official References

- [Spring Framework – WebClient Attributes](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-attributes.html): adding attributes to requests, reading in filters, and using defaultRequest.
- [Spring Framework – WebClient Context](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html): why to use Reactor Context for nested requests and how to read it with deferContextual.
- [Spring Framework – WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): ExchangeFilterFunction, modifying ClientRequest, and managing response bodies when filters intervene.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient.Builder, filters, defaultRequest, and WebClient's immutable lifecycle.
- [Reactor Reference – Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): immutable Context, subscriber-scoped, contextWrite, and deferContextual.
- [Reactor Reference – Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): integrating Reactor Context with ThreadLocal via Micrometer Context Propagation.
- [Spring Security – Reactive Security Context](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): accessing SecurityContext in the reactive stack.

## 17. Key Takeaways

**Request attributes are for metadata on a single ClientRequest; Reactor Context is for metadata scoped to a subscriber/reactive chain.** Attributes are useful when a filter needs to know what operation the current request is performing. Context is useful when a chain with multiple nested WebClient calls needs to share a correlation ID, tenant metadata, or tracing info.

Both are internal data. To send values to an HTTP service, explicitly map them to headers, query parameters, or bodies in a filter. Read attributes from `ClientRequest` and read Context via `Mono.deferContextual(...)`. Write Context using `contextWrite(...)` at the end of the chain so upstream operators can see the data. Keep publishers in the same reactive chain so Context propagation works; avoid ThreadLocal, shared mutable state, blocking, and manual subscribing. Test both attribute scoping and Context propagation to prevent missing metadata or leakage across requests.
