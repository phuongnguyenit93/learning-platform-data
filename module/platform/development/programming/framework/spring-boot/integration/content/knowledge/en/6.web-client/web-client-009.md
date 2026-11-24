# Propagating Reactor Context and Correlation IDs Across HTTP Calls

> **Chapter:** WebClient  
> **Scope:** Spring Boot Integration — inter-service HTTP integration, context propagation across reactive flows, header contracts, error handling, and observability.

When a request travels through an API Gateway, order service, inventory service, and finally a payment system, logs and errors may span multiple machines, threads, and HTTP connections. A **correlation ID** links events belonging to the same business request. With Spring WebFlux and `WebClient`, that ID must cross two distinct boundaries:

1. **Within a reactive process:** store the ID in the **Reactor Context** so operators belonging to the same subscription can read it.
2. **Between two services:** read the ID from the Reactor Context, place it into an **HTTP request header**; on the receiving side, read the header and put the ID into a new Reactor Context.

Reactor Context **does not automatically cross the network**. Nor is it a global variable, a `ThreadLocal`, or a complete distributed tracing mechanism.

## 1. What Problem Does Reactor Context Solve?

Reactor Context is a key-value data structure attached to a **Subscriber/subscription**, used to pass auxiliary metadata without adding extra parameters to every method. Common values include correlation IDs, observability data, and metadata needed for asynchronous processing.

Suppose a flow calling `WebClient` hops from an event-loop thread to another scheduler. If you store the correlation ID manually in `ThreadLocal` or MDC right before constructing the `Mono`, the thread executing the HTTP call may differ from the thread that set the value. Logs can easily lose the ID or mix IDs across concurrent requests. Reactor Context travels with the **reactive chain** and can be read at subscription time.

| Component | Scope | Propagated Over HTTP Automatically? | Role |
| --- | --- | --- | --- |
| Reactor Context | One reactive subscription inside the JVM | No | Carries metadata across Reactor operators |
| HTTP header **X-Correlation-ID** | One HTTP request/response | Yes, when explicitly set by the application | Inter-service contract for a business ID |
| MDC / `ThreadLocal` | Current thread | No | Adds attributes to logs on that thread |
| W3C **traceparent** / **tracestate** | Distributed tracing context | Yes, when tracer/instrumentation is configured properly | Links spans across services |
| W3C **baggage** | Metadata carried alongside a trace | Yes, with matching propagation configuration | Carries selected attributes across service boundaries |

**Principle:** A correlation ID can serve as a stable business log search key across a request's entire journey; trace IDs and span IDs serve distributed tracing. They can be related, but should not be assumed identical by default.

## 2. In Which Direction Is Context Written and Read?

The two most important APIs are:

- **Mono.deferContextual(...)** or **Flux.deferContextual(...)**: reads `ContextView` at subscription time, well suited for filters and gateways.
- **contextWrite(...)**: adds/overrides context visible to **operators upstream** within the same subscription. When reading a fluent chain top-to-bottom, this operator is normally placed near the bottom so earlier steps see the data.

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Object key = new Object();

Mono<String> operation = Mono.deferContextual(context ->
    Mono.just("correlationId=" + context.<String>get(key))
);

Mono<String> requestA = operation
    .contextWrite(Context.of(key, "req-101"));

Mono<String> requestB = operation
    .contextWrite(Context.of(key, "req-202"));

// Each subscription reads its own context:
// requestA -> "correlationId=req-101"
// requestB -> "correlationId=req-202"
~~~

**Common misconception:** Context is semantically immutable; **contextWrite** produces an updated view for the subscription without mutating a shared variable. Calling **Mono.just(...)** when assembling a pipeline does not execute HTTP calls or read Context. Fetching data inside **deferContextual** ensures it is read at the right time.

An operator outside the upstream path of **contextWrite** will not automatically see the new key. Branches started via independent **subscribe()** calls or handed off to **CompletableFuture**/executors outside Reactor also require explicit context bridging.

## 3. Flow of ID Propagation Between Service A and Service B

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant A as Service A (WebFlux)
    participant W as WebClient in A
    participant B as Service B
    C->>A: GET /api/inventory/42<br/>X-Correlation-ID: req-101
    Note over A: WebFilter validates header<br/>contextWrite(correlationId=req-101)
    A->>W: Call gateway via Mono
    Note over W: deferContextual reads req-101
    W->>B: GET /v1/inventory/42<br/>X-Correlation-ID: req-101
    Note over B: WebFilter creates Reactor Context<br/>for the new subscription
    B-->>W: 200 OK
    W-->>A: Response body
    A-->>C: HTTP response<br/>X-Correlation-ID: req-101
~~~

Each service owns a separate Reactor Context for its own request/subscription. The bridge between the two contexts is the header sent over HTTP. **Service B must implement its own inbound handling** if it needs to preserve the same correlation ID for subsequent calls.

## 4. Correlation ID Contract at the HTTP Boundary

Standardize on one header name across services, such as **X-Correlation-ID**. This is an application convention, not a mandatory HTTP standard header. Define rules clearly:

| Rule | Rationale |
| --- | --- |
| Reuse a valid incoming ID; otherwise generate a new one | Enables cross-system correlation while ensuring logs always have a trustworthy value |
| Accept only allowed characters and enforce length limits | Prevents log injection, malformed headers, and oversized metadata |
| Keep the same ID across sub-calls and retries of one request | Allows finding the full sequence of related events |
| Return the ID in the response header | Lets clients and operations teams look up errors when reported |
| Never put tokens, emails, personal data, or secrets in the ID | Prevents leaking sensitive data into logs, traces, and downstream systems |
| Send the header only to authorized downstreams | Avoids leaking metadata to user-controlled URLs |

In environments behind an API Gateway, you may **always regenerate** the ID at the trusted edge to prevent clients from forging or colliding IDs. The example below reuses the header **after validation**; trust-boundary policies should be uniform across the system.

### 4.1. Context Key and Validation Rules

File **CorrelationId.java**:

~~~java
package example.integration;

import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationId {
    public static final String HEADER = "X-Correlation-ID";

    // Dedicated key object to avoid collisions with string keys from other libraries.
    public static final Object CONTEXT_KEY = new Object();

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    private CorrelationId() {
    }

    public static String fromIncomingHeader(String candidate) {
        if (candidate != null && SAFE_ID.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Generating a UUID when the header is missing or invalid ensures the application always has an ID for the request. The regex is just an **example contract**; if you use standard UUIDs, ULIDs, or another format, apply the same rule consistently across all services and gateways.

### 4.2. Reading the ID and Writing Reactor Context with WebFilter

This example targets **Spring WebFlux** applications. The filter runs at the HTTP server boundary, sets the response header, and creates the Context for downstream processing.

File **CorrelationWebFilter.java**:

~~~java
package example.integration;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class CorrelationWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String incoming = exchange.getRequest()
                .getHeaders()
                .getFirst(CorrelationId.HEADER);

        String correlationId =
                CorrelationId.fromIncomingHeader(incoming);

        exchange.getResponse()
                .getHeaders()
                .set(CorrelationId.HEADER, correlationId);

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put(CorrelationId.CONTEXT_KEY, correlationId));
    }
}
~~~

**Why is `contextWrite` placed after `chain.filter`?** On subscription, context provided by a downstream operator is visible to upstream processing, including controllers, services, and `WebClient` calls in that chain. There is no need to thread a correlation ID parameter through every layer.

**Limitation:** `WebFilter` applies only to WebFlux servers. If your application uses Spring MVC/Servlet, you need Servlet-compatible filter and context-bridging mechanisms; simply adding a `WebFilter` class will not activate it for MVC requests.

### 4.3. Reading Reactor Context in a WebClient ExchangeFilterFunction

`WebClient` uses **ExchangeFilterFunction** to inspect or modify requests before sending and handle responses. Because `ClientRequest` is immutable, create a copy with **ClientRequest.from(...)** and add the header.

File **CorrelationWebClientFilter.java**:

~~~java
package example.integration;

import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

public final class CorrelationWebClientFilter {
    private CorrelationWebClientFilter() {
    }

    public static ExchangeFilterFunction outbound() {
        return (request, next) -> Mono.deferContextual(contextView -> {
            if (!contextView.hasKey(CorrelationId.CONTEXT_KEY)) {
                // Background jobs/schedulers without context should be assigned
                // their own ID at flow startup if correlation is desired.
                return next.exchange(request);
            }

            String correlationId =
                    contextView.get(CorrelationId.CONTEXT_KEY);

            ClientRequest withCorrelation = ClientRequest.from(request)
                    .headers(headers ->
                            headers.set(CorrelationId.HEADER, correlationId))
                    .build();

            return next.exchange(withCorrelation);
        });
    }
}
~~~

Here **Mono.deferContextual** lives **inside** the filter, so each subscription or retry reads the current call's context. The filter holds no static `currentId` field, does not treat MDC as the source of truth, and cannot carry over a previous request's ID.

When the context key is absent, the example intentionally leaves the request untouched. If a background job also requires a correlation ID, generate the ID and attach the Context at job startup (see section 6) rather than letting individual filters invent unrelated random IDs.

### 4.4. Registering WebClient and Calling the Downstream Service

File **HttpClientConfiguration.java**:

~~~java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {
    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .filter(CorrelationWebClientFilter.outbound())
                .build();
    }
}
~~~

Use the **Spring Boot-managed `WebClient.Builder`** to retain application customizers and observability configuration. Attach the filter to clients targeting trusted endpoints; avoid broadcasting headers indiscriminately to arbitrary URLs.

File **InventoryGateway.java**:

~~~java
package example.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryGateway {
    private final WebClient client;

    public InventoryGateway(
            @Qualifier("inventoryWebClient") WebClient client) {
        this.client = client;
    }

    public Mono<String> getInventory(String sku) {
        return client.get()
                .uri("/v1/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

File **InventoryController.java**:

~~~java
package example.integration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class InventoryController {
    private final InventoryGateway inventoryGateway;

    public InventoryController(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    @GetMapping("/api/inventory/{sku}")
    public Mono<String> inventory(@PathVariable String sku) {
        return inventoryGateway.getInventory(sku);
    }
}
~~~

The controller simply returns the `Mono`; when WebFlux subscribes to the chain, **CorrelationWebFilter** supplies the ID, and **CorrelationWebClientFilter** reads it and sends the header. `String` keeps the example concise; in real integrations, define DTOs, timeouts, HTTP status handling, and explicit error contracts.

Sample inbound request:

~~~http
GET /api/inventory/SKU-42 HTTP/1.1
Host: service-a.internal
X-Correlation-ID: order-2026-00042
~~~

Outbound call from Service A to Service B:

~~~http
GET /v1/inventory/SKU-42 HTTP/1.1
Host: inventory-service
X-Correlation-ID: order-2026-00042
~~~

When Service B uses the same logic from section 4.2, it establishes a **new Reactor Context** carrying the same ID for the received request. The response from Service A includes **X-Correlation-ID** so callers can provide it to support teams.

## 5. Logging Safely from Reactor Context

Reading the ID directly inside **deferContextual** is straightforward when only a few log points are needed:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;

private static final Logger log =
        LoggerFactory.getLogger(InventoryGateway.class);

public Mono<String> getInventoryWithLog(String sku) {
    return Mono.deferContextual(context -> {
        String correlationId =
                context.getOrDefault(CorrelationId.CONTEXT_KEY, "missing");
        log.info("Calling inventory sku={}, correlationId={}",
                sku, correlationId);

        return client.get()
                .uri("/v1/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(String.class);
    });
}
~~~

**MDC is `ThreadLocal`-backed**, so calling **MDC.put("correlationId", ...)** at the start of a controller and expecting every reactive callback to see it is unsafe. If you want context automatically populated in all logs, configure and test **Micrometer Context Propagation / Reactor context propagation** appropriate for your Spring Boot, Reactor, tracing, and logging versions. Propagating MDC/`ThreadLocal` and translating **custom business keys** to HTTP headers are two separate responsibilities.

Never log full HTTP headers, tokens, or sensitive bodies just to inspect a correlation ID. Attach **correlationId** as a structured log field.

## 6. Explicitly Creating Context for Batch Jobs or Schedulers

For work not triggered by a WebFlux request, no **CorrelationWebFilter** exists to supply an ID. Create the context at the job boundary:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public Mono<Void> refreshInventoryJob() {
    String correlationId = UUID.randomUUID().toString();

    return inventoryGateway.getInventory("SKU-42")
            .then()
            .contextWrite(Context.of(CorrelationId.CONTEXT_KEY,
                                     correlationId));
}
~~~

One job execution uses one ID; if a job fans out into multiple branches belonging to the same logical task, apply Context outside the group of branches. Never call **subscribe()** inside a service just to fire off HTTP calls: detached subscriptions lose error handling, cancellation, and lifecycle control. Let the orchestrating layer subscribe or return the `Publisher` to the framework.

## 7. Relationship with Spring Boot Distributed Tracing

In systems configured with Micrometer Observation/Tracing and a tracer, HTTP client/server instrumentation can create spans and propagate W3C **traceparent**. This serves a related but distinct purpose from a business correlation ID.

~~~text
X-Correlation-ID: order-2026-00042
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- **X-Correlation-ID**: a business key that the application decides how to generate, validate, and forward.
- **traceparent**: trace ID, span ID, and trace flags managed by instrumentation; never assemble or overwrite it manually to match a correlation ID.
- **baggage**: include only attributes genuinely needed across services, watching cardinality, header size, and security.

Using the Spring Boot-provided `WebClient.Builder` preserves observation configuration for `WebClient`. Never assume that merely adding a tracing starter sends **every Reactor Context key** as an HTTP header: the business filter from section 4.3 is still needed if you adopt the **X-Correlation-ID** contract. Verify over real HTTP that trace headers and correlation headers coexist and propagate through gateways/proxies as expected.

## 8. Context Across Retries, Timeouts, Errors, and Concurrency

| Scenario | Guarantee Required |
| --- | --- |
| **retryWhen** re-calls downstream | Each resubscription still reads the same correlation ID for that request; never generate a new ID per retry |
| Timeout, 4xx, 5xx, or connection refused | ID must still appear in error logs and Service A's error response if the response is not yet committed |
| **flatMap** running multiple concurrent calls | Branches within one request may share the same ID; two independent requests must never mix IDs |
| **publishOn** / **subscribeOn** | Reactor Context travels with the subscription across standard Reactor operators; not tied to a fixed thread |
| **Mono.cache()**, shared Publishers, or multiple subscriptions | Audit subscription scope and shared data; avoid caching responses carrying another request's metadata |
| `CompletableFuture`, callback libraries, or external executors | Require explicit context bridging or tested context-propagation libraries |
| Streaming/SSE or cancelled requests | Correlation ID still aids log lookup, while cleanup/metrics must honor cancel signals |

Example attaching an ID across a pipeline with retries:

~~~java
import java.time.Duration;
import reactor.util.context.Context;
import reactor.util.retry.Retry;

Mono<String> result = inventoryGateway.getInventory("SKU-42")
        .timeout(Duration.ofSeconds(3))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(error -> isTransientFailure(error)))
        .contextWrite(Context.of(CorrelationId.CONTEXT_KEY, "req-101"));
~~~

Here **isTransientFailure(...)** represents the application's error-classification policy (retrying only transient failures). Timeout values are illustrative, not mandatory defaults. Do not retry non-idempotent writes without an idempotency/deduplication contract. **Correlation IDs do not replace idempotency keys**: the two serve different purposes and correlation IDs do not prevent duplicate writes.

## 9. Testing Filters Without a Real Network

You can create a fake **ExchangeFunction** to inspect the `ClientRequest` produced by the filter. Example using JUnit 5, Reactor Test, and AssertJ:

~~~java
package example.integration;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

import static org.assertj.core.api.Assertions.assertThat;

class CorrelationWebClientFilterTest {
    @Test
    void addsCorrelationHeaderFromReactorContext() {
        AtomicReference<String> captured = new AtomicReference<>();

        ExchangeFunction fakeTransport = request -> {
            captured.set(request.headers()
                    .getFirst(CorrelationId.HEADER));

            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body("ok")
                    .build());
        };

        WebClient client = WebClient.builder()
                .exchangeFunction(fakeTransport)
                .filter(CorrelationWebClientFilter.outbound())
                .build();

        Mono<String> call = client.get()
                .uri("http://inventory.internal/test")
                .retrieve()
                .bodyToMono(String.class)
                .contextWrite(Context.of(CorrelationId.CONTEXT_KEY,
                                         "req-789"));

        StepVerifier.create(call)
                .expectNext("ok")
                .verifyComplete();

        assertThat(captured.get()).isEqualTo("req-789");
    }
}
~~~

Additional scenarios to include in your integration test suite:

1. **Missing inbound X-Correlation-ID:** `WebFilter` generates a valid ID, the response echoes that ID, and downstream receives the same ID.
2. **Malformed ID** (whitespace, control characters, longer than 64 characters): not forwarded verbatim; generates a new ID or rejects per contract.
3. **Two concurrent requests** with distinct IDs: each downstream call receives its own exact ID, even with **flatMap**, scheduler hops, or retries.
4. **No Reactor Context** in a background client call: the filter adds no header per example policy, and attaching Context in the job causes the header to be sent.
5. **Downstream error:** logs and error responses can be correlated by ID; sensitive request contents never leak into error messages.
6. **Tracing enabled:** verify W3C trace headers are propagated separately by instrumentation and not overwritten by custom filters.

For end-to-end HTTP tests, use **WebTestClient** against the WebFlux server and a mock HTTP server/stub for downstream, verifying the actual outbound request headers, response headers, and logged values for the same request.

## 10. Common Implementation Mistakes

**Reading Context during bean initialization:** filter setup when building `WebClient` does not represent a subscription. Use **Mono.deferContextual(...)** inside the filter lambda.

**Storing the ID in a static variable or mutable singleton field:** concurrent requests will overwrite one another. Use per-subscription Context.

**Using MDC.get(...) as the header source:** `ThreadLocal` values may be empty or leak across tasks when threads change. Read from Reactor Context before setting the header on `ClientRequest`.

**Setting only Reactor Context and expecting Service B to receive the ID:** Context lives inside one JVM; translate it to an HTTP header and re-establish it on the receiving side.

**Configuring tracing and assuming X-Correlation-ID appears automatically:** `traceparent` is not the business header. If `X-Correlation-ID` is required, define how it is issued and forwarded.

**Adding the ID once in defaultHeader on a singleton WebClient:** the ID becomes frozen across requests. Per-request correlation IDs must be read from Context at exchange time.

**Blindly forwarding arbitrary headers from the Internet:** risks header injection, oversized headers, leaking sensitive credentials, or broadcasting headers to untrusted domains. Validate at the edge and restrict allowed downstreams.

**Generating a new ID on every outbound retry:** one business flow fractures into unrelated log chains. Generate the ID at the request or job boundary and let the filter reuse it.

## 11. Production Readiness Checklist

- Services agree on header name, max length, ID format, and reuse/regeneration rules at the trust boundary.
- WebFlux servers write the ID into Reactor Context; `WebClient` reads it via **deferContextual** and sets it per subscription on `ClientRequest`.
- The HTTP client configures timeouts, error classification, conditional retries, and error-contract handling; correlation IDs are logged at key observation points.
- No tokens, user data, or sensitive payloads appear in correlation IDs, logs, or tracing baggage.
- Gateways/proxies do not accidentally strip required headers and do not forward metadata to untrusted targets.
- Concurrency tests, error tests, missing-Context tests, and real-HTTP propagation tests all pass.
- Logs, traces, and metrics can be queried by ID while keeping correlation IDs distinct from trace IDs and idempotency keys.

## References

- [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Framework Reference — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html)
- [Spring Framework Reference — Context Propagation](https://docs.spring.io/spring-framework/reference/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)

**Remember:** Reactor Context carries metadata **inside** a subscription; `ExchangeFilterFunction` turns a selected value into an **HTTP header**; the receiving service reads the header and sets up Context for its own subscription. That complete chain is what links logs reliably across asynchronous `WebClient` calls.
