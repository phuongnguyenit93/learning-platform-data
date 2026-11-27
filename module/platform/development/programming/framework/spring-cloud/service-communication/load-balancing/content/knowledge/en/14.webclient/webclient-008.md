# Timeouts, Cancellation, and Impact on In-Flight Calls

In Spring Cloud LoadBalancer, `WebClient` can call a service by service ID, such as `http://inventory-service`, instead of a fixed IP address. LoadBalancer picks an appropriate `ServiceInstance` from discovery, yet **selecting an instance does not guarantee the request will complete on time**. A replica may respond slowly, the connection may drop, the client may lose interest in the result, or the target service may be removed from the registry while the request is running.

This lesson belongs to the **WebClient** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The module's goal is understanding client-side load balancing by service ID, discovery, health checks, and routing policies, combining `RestClient`, `WebClient`, OpenFeign, retries/timeouts, and error observability for resilient service communication. This lesson dives into three easily conflated topics: **timeouts**, **cancelling a subscription** in reactive programming, and **impact on an already-started HTTP call**.

In the Reactor/WebClient context, *cancellation* primarily means **cancelling or disposing a `Subscription`**, indicating the consumer no longer wants results from the `Publisher`. It is **different** from *deregistering* a `ServiceInstance` from a service registry. This lesson distinguishes both meanings and explains how each affects an *in-flight request*.

## 1. Expected Outcomes

After this lesson, you will be able to:

- Explain why `WebClient` returns a `Mono` or `Flux` and when the HTTP request actually starts.
- Distinguish connect timeout, response/read timeout, Reactor pipeline timeout, and overall *deadline*.
- Understand how `timeout(...)` emits an error downstream while cancelling the upstream subscription.
- Separate **the client stopping waiting**, **the transport being released**, and **the server stopping processing**: these three are not synonymous.
- Design retries, timeouts, and fallbacks without generating duplicate requests or overloading target replicas.
- Verify cancellation behavior with `doOnCancel`, `doFinally`, reactive tests, and server observation.
- Explain what happens if a `ServiceInstance` is deregistered while a request to that instance is already in flight.

## 2. What Is the Lifecycle of a WebClient Request?

Suppose `order-service` has a client calling `inventory-service`:

~~~java
Mono<StockResponse> result = webClient.get()
    .uri("http://inventory-service/api/stock/{sku}", "SKU-42")
    .retrieve()
    .bodyToMono(StockResponse.class);
~~~

This expression describes a reactive pipeline. **Creating a `Mono` does not by itself mean an HTTP request has been sent immediately.** With `WebClient`, the request is triggered when a subscriber subscribes: the WebFlux runtime subscribes to the `Mono` returned by a controller, or another component calls `subscribe()`, `block()` in a permitted context, or uses an equivalent operator leading to subscription.

~~~mermaid
sequenceDiagram
    participant App as Order application
    participant M as Mono/Subscriber
    participant LB as Reactive LoadBalancer
    participant Sup as Instance supplier
    participant Inv as Inventory replica
    App->>M: Build WebClient pipeline
    Note over App,M: No HTTP request yet necessarily
    App->>M: Subscribe
    M->>LB: Start request to inventory-service
    LB->>Sup: Fetch ServiceInstance
    Sup-->>LB: Candidate set
    LB->>LB: Select inv-b
    LB->>Inv: HTTP request to host:port
    Inv-->>LB: HTTP response
    LB-->>M: Body / completion or error
    M-->>App: onNext, onComplete / onError
~~~

If the same cold `Mono` (*cold publisher*) is subscribed to multiple times, each subscription can start **a separate HTTP call**. This matters especially with retries, `repeat`, or code that manually subscribes while the WebFlux framework also subscribes.

### Key States

| State | Description | Cancellable? |
|---|---|---|
| Pipeline merely created | No subscription yet | No running HTTP request to cancel |
| Waiting for instance selection | Querying supplier/LoadBalancer | Cancellation may stop waiting before sending HTTP |
| Waiting for connection | Pool is leasing or opening a connection | Cancellation may cancel connection demand, depending on transport |
| Request sending/sent | Server may already have received the request | Client can cancel subscription, but cannot guarantee server stops |
| Reading response body | Data may stream in multiple chunks | Cancellation usually stops reading remaining client-side data |
| Completed or errored | Pipeline already terminated | Subsequent cancellation does not undo effects that occurred |

`Mono` represents at most one data element, while `Flux` can emit multiple elements. Both follow Reactive Streams `Subscription` semantics and can receive cancellation signals.

## 3. Timeout Is Not a Single Configuration

During an HTTP call, several distinct stages occur:

~~~text
Subscribe
   |
   +--> Select ServiceInstance via LoadBalancer
   +--> DNS / resolve physical address
   +--> Wait to acquire connection from pool
   +--> Establish TCP and TLS (if using HTTPS)
   +--> Send request
   +--> Wait for response headers
   +--> Read response body
   +--> Deserialize / run reactive operators
   |
   v
Complete / Error / Cancel
~~~

Each timeout typically covers a different portion:

| Type | Point Applied | When Expired |
|---|---|---|
| **Connect timeout** | Time to establish TCP connection | Transport emits connection error |
| **Pool acquisition timeout** | Waiting for a connection from pool | Fails to acquire connection in time |
| **TLS handshake timeout** | TLS negotiation phase | Handshake/transport error |
| **Response/read timeout** | Waiting for or reading response per HTTP client semantics | Transport timeout error |
| **`Mono.timeout(Duration)`** | Time waiting for upstream signal per Reactor operator | Downstream receives `TimeoutException`; upstream is cancelled |
| **Overall deadline** | Time budget for the entire business operation | Must be designed across attempts, backoff, processing, and downstream |

Two timeout errors do not necessarily produce the same exception. `Mono.timeout(Duration)` uses Reactor's timeout mechanism; a Netty or pool timeout can emit a different exception type, potentially wrapped in an HTTP client exception.

**Never set only a response timeout and claim the call has an overall deadline.** Pool waits, instance selection, handshakes, decoding, and retries may not be covered equally. Conversely, `Mono.timeout` times the pipeline rather than directly configuring all underlying socket timeouts.

## 4. Integrating WebClient with Spring Cloud LoadBalancer

Example using WebClient in `order-service` to call the logical hostname `inventory-service`.

For dependencies, the caller needs compatible Spring Boot/Spring Cloud versions, Spring WebFlux's WebClient, and Spring Cloud LoadBalancer. An illustrative Gradle configuration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Manage the Spring Cloud BOM compatibly with Spring Boot. If using Eureka/Consul/Kubernetes, add the matching discovery adapter; if using `SimpleDiscoveryClient` for a lab, declare a static instance list.

Declare a load-balanced `WebClient.Builder`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

When configured properly, Spring Cloud attaches `ReactorLoadBalancerExchangeFilterFunction` or equivalent integration to `WebClient.Builder` beans marked with `@LoadBalanced`. The hostname `inventory-service` is interpreted as a **service ID** to choose a `ServiceInstance`; the final request is still HTTP to the chosen host/port.

Simple local configuration:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Both target replicas must actually run on those ports. `SimpleDiscoveryClient` only supplies static addresses; it does not automatically remove an instance that just died. Nor does `@LoadBalanced` automatically add business-appropriate timeouts or retries.

## 5. Timeout Using Reactor Operators

Suppose `inventoryWebClient` is the `WebClient` bean configured above:

~~~java
import java.time.Duration;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryGateway {

    private final WebClient inventoryWebClient;

    public InventoryGateway(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<StockResponse> getStock(String sku) {
        return inventoryWebClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class)
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

The response contract might be:

~~~java
public record StockResponse(
        String sku,
        boolean available,
        int quantity
) {}
~~~

Here `timeout(Duration.ofSeconds(2))` applies to the response `Mono`. If upstream fails to emit the required signal within the specified time, downstream receives `TimeoutException`, while Reactor sends a **cancel** signal upstream.

For a `Mono` that only produces a result after reading and decoding the entire response, the timeout can cover waiting **until the Mono emits an item or completes**. For `Flux`, the standard `timeout(Duration)` overload monitors the wait for the first signal and intervals between signals—**not always the total duration of the entire stream**. If an overall streaming-session deadline is needed, design specifically for it instead of assuming an inter-element timeout suffices.

### Placing Timeout Before or After Processing?

Example:

~~~java
return inventoryWebClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofSeconds(2))
        .map(this::normalize);
~~~

In this example, `timeout` sits before `map`. It monitors the upstream pipeline up to receiving the response, without imposing a separate deadline on downstream `normalize` work. To cover reactive post-response processing as well, place `timeout` outside the chain containing that processing step.

Operator placement is part of the timing contract, not just code formatting.

## 6. Cancellation: What Does Cancelling a Subscription Mean?

In Reactor, `subscribe()` creates a subscription to a publisher. The `subscribe(...)` API typically returns a `Disposable`; calling `dispose()` is an explicit way to request cancelling that subscription.

Example **for illustration only**, not recommended for controller code:

~~~java
import reactor.core.Disposable;

Disposable subscription = inventoryWebClient.get()
        .uri("/api/stock/SKU-42")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .subscribe(
            response -> System.out.println(response),
            error -> System.err.println(error)
        );

// When the result is genuinely no longer needed:
subscription.dispose();
~~~

If `dispose()` is called before the pipeline completes, the subscriber stops receiving results. In WebFlux, **do not manually call `subscribe()` in a controller** just to kick off a request and return; return `Mono` or `Flux` so the framework manages the lifecycle and propagates cancellation when the upstream client disconnects.

Distinguish three cases:

1. **Complete**: the publisher emitted results and terminated normally.
2. **Error**: the publisher terminated with an error signal.
3. **Cancel**: downstream declared it is no longer interested in upstream data.

Cancellation is **not** `onError`. When a subscriber cancels on its own, it normally does not receive `onError` or `onComplete` afterward. At a `timeout` operator, downstream sees a timeout error while upstream gets cancelled; the two signals occur on **opposite sides of the operator**.

## 7. How Do `timeout()` and `doOnCancel()` Differ?

Example observing both sides of a timeout:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

Mono<StockResponse> source =
    inventoryWebClient.get()
        .uri("/api/stock/SKU-42")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .doOnCancel(() ->
            System.out.println("Upstream cancelled"))
        .doFinally(signal ->
            System.out.println("Upstream: " + signal));

Mono<StockResponse> result = source
    .timeout(Duration.ofSeconds(2))
    .doFinally(signal ->
        System.out.println("Downstream: " + signal));
~~~

If `source` produces no result within 2 seconds:

- The `timeout` operator emits `TimeoutException` downstream.
- `source` upstream receives a cancellation signal.
- Upstream `doOnCancel` can execute.
- `doFinally` placed **before** `timeout` observes `SignalType.CANCEL`.
- `doFinally` placed **after** `timeout` typically observes `SignalType.ON_ERROR`.

This situation easily leads to seemingly contradictory logs: the same request shows **CANCEL** upstream and **ERROR** downstream. In reality, those are two views of the exact same timeout event at two points in the operator chain.

`doFinally` also runs when a publisher completes normally, making it suitable for releasing resources or recording completion signals. However, never put blocking or heavy I/O directly into the callback in a way that stalls the event loop.

## 8. Does Cancelling a Subscription Stop the HTTP Request on the Server?

This is the most critical distinction.

~~~mermaid
sequenceDiagram
    participant Caller as Order WebClient
    participant Netty as HTTP transport
    participant Server as Inventory service
    Caller->>Netty: Subscribe, send GET/POST
    Netty->>Server: HTTP request
    Note over Server: Server begins processing
    Note over Caller: 2-second deadline expires
    Caller->>Caller: timeout -> downstream onError
    Caller->>Netty: Cancel upstream
    Netty--xServer: May close/abort HTTP exchange
    Note over Server: Processing may have already run or committed
    Note over Caller,Server: Cancellation is not a transaction rollback
~~~

The transport mechanism, such as Reactor Netty, can react to cancellation by stopping response reads, aborting unsent requests, or closing/releasing network resources depending on current state. However, **there is no general guarantee that the server stops work immediately**.

If the server already received `POST /orders`, it may have written to the database before the caller timed out. The caller not receiving a response **does not prove the server did not process it**.

| Point of Cancellation | What May Happen | What Must Not Be Assumed |
|---|---|---|
| Before connection acquired | Stops waiting for connection | An HTTP request already hit the server |
| Before full request sent | Stops further transmission | Server definitely received nothing |
| After server received request | Client stops waiting/reading | Server automatically aborts business logic |
| After server committed | Caller can still report timeout | Transaction was rolled back |
| While streaming body | Stops receiving remaining chunks | All downstream work was cancelled |

Therefore, separate three operational questions: *is the client still waiting?*, *is the connection/stream still active?*, and *did the server finish the business operation?* All three answers can differ.

## 9. Configuring Timeouts at the HTTP Transport: Reactor Netty

Alongside Reactor pipeline timeouts, you can configure transport-level timeouts directly when the application uses Reactor Netty:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpTimeoutConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
    }
}
~~~

With this configuration:

- `CONNECT_TIMEOUT_MILLIS` bounds one phase of establishing the TCP connection.
- Reactor Netty's `responseTimeout(Duration)` applies a response timeout per the transport version's semantics.
- Timeouts from Netty may carry a different exception type than `java.util.concurrent.TimeoutException` emitted by Reactor `Mono.timeout`.
- These timeouts do not govern all steps from instance selection, pool waits, retries, to deserialization under one combined budget.

**This is an alternative configuration** to the `@LoadBalanced WebClient.Builder` bean in section 4, not a second bean of the same type to declare side by side. When using one `WebClient` across multiple services, consider sharing connectors and connection pools rather than creating a new `HttpClient` per request.

Some systems use other HTTP client implementations. In those cases, timeout properties and specific exception types depend on the actual transport; do not force Reactor Netty configuration onto every WebClient.

## 10. Overall Call Deadline and Retry Chains

Per-attempt timeout and overall deadline are two separate concepts.

Suppose each attempt is allowed up to 800 ms, with up to 1 retry and backoff. Without an overall deadline, total time can far exceed 800 ms.

~~~mermaid
flowchart LR
    A["Subscribe"] --> B["Attempt 1: timeout 800ms"]
    B --> C{"Succeeded?"}
    C -- No --> D["Backoff"]
    D --> E["Attempt 2: timeout 800ms"]
    E --> F["Result"]
    C -- Yes --> F
    G["Deadline 2s"] -.-> B
    G -.-> D
    G -.-> E
~~~

Example:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<StockResponse> getStockWithRetry(String sku) {
    Mono<StockResponse> oneAttempt = Mono.defer(() ->
        inventoryWebClient.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(StockResponse.class)
            .timeout(Duration.ofMillis(800)));

    return oneAttempt
        .retryWhen(Retry.backoff(1, Duration.ofMillis(150))
            .filter(TimeoutException.class::isInstance))
        .timeout(Duration.ofSeconds(2));
}
~~~

Here:

1. `Mono.defer` recreates the HTTP call upon subscription for each attempt.
2. The `800 ms` timeout sits **inside** `retryWhen`, so it applies individually to each attempt.
3. `Retry.backoff(1, ...)` permits at most one retry after the initial call for filtered errors; maximum two attempts total.
4. The `2-second` timeout sits **outside** `retryWhen`, so it bounds both attempts and backoff in this chain.

This is a directional example, not a policy suitable for every API. Connect timeout errors from the HTTP client may be a different exception type and thus not matched by `TimeoutException.class::isInstance`. Identify actual exception types and bound retries per error class.

If the overall timeout fires during backoff or mid-attempt, the upstream subscription is cancelled. Retries should not launch new attempts once the caller's deadline has expired and the chain is cancelled.

## 11. Placing `retryWhen` Before or After `timeout`?

The two arrangements below have different semantics:

**Per-attempt timeout; retries allowed after timeout:**

~~~java
source.timeout(Duration.ofMillis(800))
      .retryWhen(retrySpec);
~~~

An attempt's timeout error passes into the retry operator, allowing a new subscription/request if policy permits.

**Entire-retry-chain timeout:**

~~~java
source.retryWhen(retrySpec)
      .timeout(Duration.ofSeconds(2));
~~~

The outer deadline cancels the retry chain once total time exceeds the limit.

In real applications, you typically need **both a per-attempt budget and an overall budget** (as in the earlier example), while also accounting for retries in proxies, service meshes, or downstream layers. Retries at every layer can multiply calls to servers and rapidly amplify load.

For read-only `GET`s, controlled retries are usually more reasonable. For `POST`s creating orders, payments, or writing data, require idempotency keys, transaction status checks, or explicit retry contracts. **Timeouts do not make an operation with side effects safe to resend.**

## 12. Fallbacks Do Not Mean the Server Stopped Processing

Example fallback when a pipeline times out:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

public Mono<StockResponse> getStockOrUnknown(String sku) {
    return inventoryWebClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            TimeoutException.class,
            ex -> Mono.just(new StockResponse(sku, false, -1))
        );
}
~~~

In this example, `quantity=-1` is an illustrative sentinel code for an unknown state, **not a valid stock count**. If business logic must distinguish out-of-stock from unknown-due-to-timeout, use a DTO explicitly representing `UNKNOWN`, `AVAILABLE`, `UNAVAILABLE` rather than overloading a boolean value.

Even when the caller receives a fallback, the original request may have reached the server. For write operations, never report "definitely failed, nothing written" solely because the client timed out.

Also distinguish `onErrorResume` from `onErrorReturn`: both handle downstream error signals, but neither creates new guarantees about server state or already-sent network requests.

## 13. Deregistering from a Service Registry Is a Different Matter

In service discovery systems, "cancelling registration of an instance" can also mean **deregistering a `ServiceInstance` from Eureka, Consul, or the platform's endpoint list**. This action is completely different from Reactor's `Subscription.cancel()`.

Suppose:

~~~text
t0: order-service selects inv-b from discovery
t1: HTTP request has been sent to inv-b
t2: inv-b is removed from registry or marked not-ready
t3: inv-b is still processing the received request
t4: request succeeds or fails depending on actual state
~~~

Deregistration primarily affects **new instance selections after discovery/supplier updates**. It **does not automatically abort open sockets, HTTP exchanges, or transactions** on `inv-b`.

~~~mermaid
sequenceDiagram
    participant O as Order WebClient
    participant LB as LoadBalancer
    participant R as Registry
    participant I as inv-b
    O->>LB: Call inventory-service
    LB->>R: Currently known instance list
    R-->>LB: inv-a, inv-b
    LB->>I: Send HTTP request to inv-b
    Note over I: Request is being processed
    I-->>R: Deregister / Not-ready
    Note over R,LB: Discovery/cache may update with delay
    I-->>O: May still return response
~~~

Actual impact depends on server shutdown behavior:

- **Graceful shutdown / connection draining**: allows in-flight requests to finish within a window while refusing new requests per policy.
- **Immediate kill**: can sever in-flight requests, causing connection errors on callers.
- **Slow registry/cache updates**: callers may continue picking a departing instance until lists refresh.
- **Retries**: if configured, the next attempt may pick another instance; this does not guarantee the first attempt caused no side effects.

Therefore, coordinate readiness, deregistration, drain time, termination grace periods, and client timeouts. The goal is reducing new traffic to a shutting-down replica while giving in-flight requests a chance to complete.

## 14. WebClient `Flux` and Mid-Stream Cancellation

With streaming responses (Server-Sent Events, NDJSON, or item streams), subscription cancellation can happen **after partial data has already arrived**.

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

public Flux<EventDto> streamEvents() {
    return inventoryWebClient.get()
        .uri("/api/events")
        .retrieve()
        .bodyToFlux(EventDto.class)
        .take(10);
}
~~~

`take(10)` can send cancellation upstream after receiving 10 items, because downstream needs no further items. Not every cancellation is an error: stopping consumption of a long stream once a goal is met can be intended behavior.

If replaced with:

~~~java
return inventoryWebClient.get()
    .uri("/api/events")
    .retrieve()
    .bodyToFlux(EventDto.class)
    .timeout(Duration.ofSeconds(3));
~~~

then `Flux` timeout typically fires when waiting for the first item or **the interval between items** exceeds the limit. A stream emitting items continuously can run longer than 3 seconds without timing out.

When an overall stream duration limit is needed, implement a session-wide lifecycle/timer policy while clearly specifying natural completion, cancellation, and error behavior. On large streams, avoid accidentally calling `collectList()` just to make timeouts easier, as it buffers all data in memory.

## 15. Cancellation and Resources: Connections, DataBuffers, Transactions

A resilient reactive system monitors not only exceptions but also resource release.

| Resource or Work | When Cancellation Occurs | What to Verify |
|---|---|---|
| Pending connection lease | Waiting may stop | Does pending acquire drop? Does the pool leak? |
| Active connection | Transport may finish exchange, close, or return connection to pool when safe | Monitor active/idle connections and transport errors |
| Streaming response body | Stops reading remainder | No retained references to unreleased body/`DataBuffer` |
| Reactive server handler | May receive cancellation if downstream connection propagates signal | Does business work actually stop or keep running? |
| Server-side database transaction | No cross-network rollback solely from client cancel | Verify idempotency, commits, and outcome state |
| Observability tracing | Client span may end in timeout while server continues | Correlation IDs and timing across spans |

When using `retrieve().bodyToMono(...)` or `bodyToFlux(...)`, Spring WebFlux/HTTP clients manage bodies normally. When manually working with `ClientResponse`, `DataBuffer`, or lower-level streaming APIs, follow the API's buffer consumption and release rules; never retain buffers past cancellation without proper release mechanisms.

Never use `Thread.interrupt()` as a general substitute for reactive cancellation. WebClient uses Reactor protocols and event loops; a cancellation signal is not equivalent to interrupting a single thread executing all work.

## 16. Observing Accurately: CANCEL, TIMEOUT, HTTP 5xx, and Transport Errors

One timeout can surface in multiple log or metric forms. Separate them:

| Observation | May Indicate | Does Not Necessarily Indicate |
|---|---|---|
| `TimeoutException` after `Mono.timeout` | Reactor operator timed out waiting on upstream | Server never received the request |
| Upstream `doOnCancel` | Downstream no longer needs the result | Remote transaction rolled back |
| `doFinally(CANCEL)` | That pipeline segment was cancelled | HTTP `5xx` business failure |
| `WebClientResponseException` | Server sent an error HTTP response handled by `retrieve()` | Network connection failed to establish |
| Network/connect/read timeout | Transport phase failed or expired | Always safe to retry |
| `No servers available` / no-instance | No candidates in LoadBalancer | Server returned a successful HTTP response |

Example per-subscription instrumentation:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

Mono<StockResponse> monitored = inventoryWebClient.get()
    .uri("/api/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(StockResponse.class)
    .doOnSubscribe(s -> log.debug("inventory request subscribed"))
    .doOnCancel(() -> log.info("inventory upstream cancelled"))
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            log.info("inventory upstream finished: cancel");
        }
    })
    .timeout(Duration.ofSeconds(2));
~~~

In this snippet, `log` is assumed to be an existing logger in the class. Callbacks placed **before** `timeout` observe the upstream side; downstream receives `TimeoutException` if this operator expires.

Measure durations with client-layer metrics recording service ID, business purpose, error type, and terminal state. Control cardinality: never use full URLs with dynamic IDs, trace IDs, or request IDs as unbounded metric labels. Correlation IDs belong in structured logs and traces.

When investigating a real request, cross-check at least two sides: caller logs/traces and server transaction logs. A `TimeoutException` alone only tells you **the caller stopped waiting according to its own rule**.

## 17. Testing Cancellation Without Sending Real HTTP Requests

Reactor semantics can be verified using `reactor-test` and virtual time. Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorCancellationTest {

    @Test
    void timeoutCancelsUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(5))
                    .doOnCancel(() -> cancelled.set(true))
                    .timeout(Duration.ofSeconds(1)))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify();

        assertTrue(cancelled.get());
    }
}
~~~

This test only proves **timeout sends cancel to the Reactor upstream**. It does not prove connections closed or the server stopped processing. For end-to-end HTTP testing, you need an environment where server response speed is controllable (e.g., a test server with a delay endpoint), then verify:

1. Requests route to the right service ID and instance.
2. Callers time out at configured thresholds.
3. The connection pool does not hold resources indefinitely after cancel.
4. Whether the server continues work after the caller times out.
5. Whether retries trigger follow-up attempts and duplicate requests.
6. How deregistering/stopping an instance mid-request affects in-flight and new requests.

When using virtual time, construct scheduler-dependent publishers and operators inside the `withVirtualTime` lambda as shown, so the test actually controls time. For real network testing, virtual time cannot replace socket timeouts and HTTP transport scheduling.

## 18. Practice Exercise: Timeout After Instance Selection

Suppose there are two `inventory-service` replicas:

~~~text
inv-a: localhost:8081 — responds fast in about 50ms
inv-b: localhost:8082 — simulates slow processing around 5s
~~~

Configure `SimpleDiscoveryClient` on the caller pointing to both instances as in earlier sections. Both serve the endpoint:

~~~http
GET /api/stock/SKU-42
~~~

The caller applies `Mono.timeout(Duration.ofSeconds(2))` to the request.

**Steps:**

1. Call multiple times and record instance IDs in responses/traces, wait times, and `onComplete`/`onError` outcomes.
2. When a request hits `inv-a`, expect a result before the deadline if infrastructure is healthy.
3. When a request hits `inv-b`, expect `Mono.timeout` to trigger if upstream emits no signal within 2 seconds.
4. Observe `doOnCancel` upstream and `onError` downstream.
5. Inspect `inv-b` server logs: the server may still finish processing all 5 seconds or notice client disconnect, depending on how the server handles it.
6. Try adding bounded retries and count attempts rather than just business requests.
7. Stop `inv-b` while a request is processing; compare graceful shutdown against abrupt termination if the test environment supports it.
8. Tune the timeout from 2 seconds to a sensible value, evaluating false errors against user latency.

**Observation log template:**

| Scenario | Client Observation | Reactor Upstream | Server Observation |
|---|---|---|---|
| Fast instance | Complete | Complete | Finished request |
| Instance slower than deadline | `TimeoutException` | CANCEL | May continue or stop |
| Caller explicitly calls `dispose()` | Stops receiving response | CANCEL | No rollback guarantee |
| Connection failure | Transport error | Error/cancel depending on operator | May not have received request |
| Instance deregistered mid-request | Depends on connection and server | May complete/error | In-flight request may continue |

The "may" outcomes are intentional: no actual test run is implied, and behavior depends on transport, server, shutdown policy, and event timing.

## 19. Common Design Mistakes

- **Calling `block()` on an event-loop thread.** This can error or stall non-blocking threads; in WebFlux compose `Mono`/`Flux` instead of blocking.
- **Creating a `Mono` and assuming the request already ran.** Without subscribing, no HTTP call necessarily happens; repeated subscriptions can fire multiple calls.
- **Setting only connect timeout and forgetting an overall deadline.** Callers can still wait indefinitely in pools, responses, or retries.
- **Setting only `Mono.timeout` and assuming the network always closes immediately.** Cancellation is best-effort toward transport; release timing depends on state.
- **Treating a timeout as a definitive business answer.** The server may have completed writing data even though the client timed out.
- **Retrying every `POST` after timeout.** Risks duplicate side effects; requires idempotency and attempt limits.
- **Treating `doFinally(CANCEL)` as an HTTP error.** Stream cancellation can be intentional, such as after `take(10)`.
- **Using `Flux.timeout(Duration)` as a total streaming duration cap.** It is normally a per-signal wait limit, not total stream duration.
- **Assuming deregistration immediately cuts in-flight requests that already selected the instance.** Discovery changes mainly affect new selections; in-flight requests need graceful draining.
- **Creating a new client/connection pool per request.** Inflates connection counts and complicates timeout and resource management.
- **Masking errors with fallbacks that conflate UNKNOWN and FAILED.** Leads business layers to draw unsupported conclusions.

## 20. Pre-Production Checklist

| Item | Verification Question |
|---|---|
| Service ID | Is WebClient using the right logical hostname and `@LoadBalanced` builder? |
| Supplier | Are discovery, cache, health checks, and policies returning a valid candidate set? |
| Timeouts | Have connect, pool, response, and Reactor timeouts been distinguished? |
| Deadline | Do all attempts and backoff fit within an appropriate total budget? |
| Retries | Are error types filtered, attempts bounded, and idempotency addressed? |
| Cancellation | Is it understood that downstream ERROR differs from upstream CANCEL? |
| Remote side effects | Is there a mechanism to verify transaction status after timeouts? |
| Streaming | Is inter-element timeout distinguished from total stream deadline? |
| Graceful shutdown | Are readiness/deregistration, drain time, and termination grace period configured? |
| Observability | Are metrics present for latency, timeouts, cancellations, selected instance, and attempt count? |
| Resources | Are connection pools, body streams, and `DataBuffer`s released properly? |
| Testing | Have fast/slow instances, timeouts, cancellations, retries, and deregistration been tested? |

## 21. Summary

- `WebClient` builds a reactive pipeline; HTTP requests are normally triggered upon **subscription**.
- `Mono.timeout(Duration)` emits `TimeoutException` downstream when upstream expires and **cancels upstream**.
- `dispose()` or subscriber cancellation signals that the client no longer needs results, **but does not guarantee the server stops processing or rolls back data**.
- HTTP transport timeouts and pipeline deadlines have different scopes; coordinate them rather than confusing them.
- The placement of `timeout` relative to `retryWhen` determines whether timeout applies **per attempt** or to the **entire retry chain**.
- `Flux.timeout` has signal-waiting semantics; design separately if you need to limit **total stream duration**.
- **Deregistering a `ServiceInstance` from a registry is completely different from cancelling a Reactor `Subscription`**. Deregistration does not automatically abort open HTTP exchanges; graceful shutdown protects in-flight calls.
- Combine timeouts, sensible retries, timely health/discovery updates, idempotency, connection draining, and observability for reliable service-to-service communication.

Understanding cancellation and timeouts properly helps applications using Spring Cloud LoadBalancer know when to stop waiting, when to retry safely, and why an HTTP call on the server can still continue even after WebClient is no longer listening for its result.
