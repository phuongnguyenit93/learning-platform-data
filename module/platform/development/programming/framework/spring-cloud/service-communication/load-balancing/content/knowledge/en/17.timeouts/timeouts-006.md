# Designing Timeouts for Multi-Service Call Chains

In a microservices architecture, a single user request can pass through an API Gateway, `order-service`, `inventory-service`, `pricing-service`, and several other services. Each call may use RestClient, WebClient, or OpenFeign together with **Spring Cloud LoadBalancer** to select a `ServiceInstance` by service ID. If every service sets a timeout independently without accounting for the time earlier steps already consumed, the overall request can wait far too long, hold resources across multiple services, or fail even though each individual call stayed within its own timeout.

This lesson in the **Timeouts** chapter focuses on designing an **end-to-end time budget**: defining the request's deadline, allocating portions across hops, keeping a reserve, bounding retries, aligning waits with infrastructure, and tracking where budget is consumed. The goal is **stable inter-service communication**, not merely adding a `readTimeout` value to `application.yml`.

## 1. The Problem: Right Timeout per Hop, Wrong Across the Whole Chain

Consider a request:

~~~mermaid
flowchart LR
    U["User"] --> G["API Gateway"]
    G --> O["order-service"]
    O --> I["inventory-service"]
    I --> P["pricing-service"]
    P --> D["price database"]
~~~

Suppose every client configures a 2-second read timeout:

~~~text
Gateway -> Order:     up to 2 seconds
Order   -> Inventory: up to 2 seconds
Inventory -> Pricing: up to 2 seconds
Pricing -> Database:  up to 2 seconds
~~~

You cannot conclude the user always receives a response within 2 seconds. If calls execute sequentially and work happens at each hop, total latency can be significantly larger. Moreover, a transport's `read timeout` is not always a deadline spanning the whole request. It may exclude connection pool waits, service discovery, token acquisition, executor queues, serialization, backoff, or retry counts.

There is another dangerous situation: the gateway already gave up waiting at the 2-second mark while downstream services keep performing expensive work until second 7, even though nobody needs the result anymore.

**Principle:** per-hop timeouts protect local resources; an **overall deadline** expresses how long the caller is still willing to wait for the entire business operation.

## 2. Distinguishing Types of Timeouts

| Type | Scope | Example scenario |
|---|---|---|
| **Connection acquisition timeout** | Waiting to lease an available connection from the pool | Pool exhausted; requests queue before network I/O |
| **Connect timeout** | Establishing a TCP connection to an instance | One instance address does not open the port |
| **TLS handshake timeout** | Completing the TLS handshake when configured | Network connects, but handshake hangs |
| **Response/read timeout** | Waiting for response data per HTTP transport semantics | Backend received request, returns no response |
| **Write timeout** | Time spent writing the request body if client supports it | Large payload upload stalls |
| **Discovery timeout** | Looking up the `ServiceInstance` list from service discovery | Registry responds slowly |
| **LoadBalancer selection time** | Time spent fetching/filtering/picking an instance | Supplier/caching/health filtering is slow |
| **Retry backoff** | Waiting before executing the next attempt | Transient failure, waiting 100–300 ms |
| **Request/operation deadline** | Total acceptable time for an entire business operation | Gateway wants a response within 1,200 ms |
| **Server execution timeout** | Server/framework-side processing bound when supported | Server refuses to hold a request too long |

There is no single Spring Cloud configuration property that automatically applies all of these limits uniformly across RestClient, WebClient, and OpenFeign.

Key distinctions:

- `spring.cloud.loadbalancer.health-check.interval` controls the instance health-probe cadence, **not** the HTTP read timeout.
- `spring.cloud.loadbalancer.cache.ttl` controls cached instance data lifetime, **not** the request deadline.
- `spring.cloud.loadbalancer.service-discovery.timeout`, on release trains that support it, governs discovery retrieval, **not** HTTP transport timeouts.
- A server returning `504 Gateway Timeout` usually indicates a gateway/proxy timed out waiting on upstream, without guaranteeing downstream stopped processing.
- `503 Service Unavailable` can stem from LoadBalancer finding no instance, the backend, or a proxy; check logs/tracing to tell them apart.

## 3. What Is an End-to-End Deadline?

Suppose a user tolerates at most 1,200 ms from the moment a request hits the gateway until receiving the result. At the start, the system establishes a **deadline**:

\[
D = t_{\text{start}} + B
\]

where:

- `B` is the maximum budget, e.g., 1,200 ms.
- `D` is the timestamp by which work must finish.
- `t_{\text{start}}` is when measurement begins.

At a given time `t`, remaining budget is:

\[
R(t) = \max(0, D - t)
\]

If one hop already took 350 ms, remaining budget is no longer 1,200 ms but roughly 850 ms, before subtracting reserves that must be kept.

An HTTP client at the next hop should apply an effective cap:

\[
T_{\text{hop}} =
\min\big(T_{\text{cap, hop}},\;\max(0, R-\Delta_{\text{reserve}})\big)
\]

Here `T_cap, hop` is the target service's own cap, while `Δ_reserve` is the time reserved for remaining work, returning the response, serialization, and network overhead.

**Never set every hop to exactly 1,200 ms** assuming layers automatically know how many stages the request has already passed through.

### Example Allocation of a 1,200 ms Budget

Consider a sequential chain: Gateway → Order → Inventory → Pricing.

| Activity | Planned budget |
|---|---:|
| Gateway + network ingress/egress | 100 ms |
| Local processing at order | 180 ms |
| Calling inventory and handling response | 350 ms |
| Calling pricing and handling response | 300 ms |
| Reserve for jitter, serialization, and brief hiccups | 270 ms |
| **Total** | **1,200 ms** |

This is a **design example**, not Spring Cloud default measurements. Allocated limits must reflect actual latency distributions, SLAs/SLOs, and dependencies. Do not assign numbers mechanically if inventory has p99 = 600 ms while business still expects a 1,200 ms deadline.

Reserves must also account for steps **not yet executed**. If order already spent 550 ms on the first operation, it makes no sense to send a new request with an 800 ms timeout when total remaining budget is only 650 ms and the response still needs serialization.

## 4. Timeout and Deadline: Local or Cross-Service?

A **relative timeout** such as 300 ms answers: “How much longer can I wait starting now?” An **absolute deadline** answers: “By what point in time must I finish?”

Within a single JVM, you can use the monotonic clock `System.nanoTime()` to compute remaining time. It is suited for measuring elapsed time and is immune to system clock jumps from NTP.

Across multiple machines, **never send raw `System.nanoTime()`**: this timestamp has no shared meaning between two JVMs. If propagating an absolute wall-clock deadline, account for clock skew, NTP, and network delay. A simple strategy is passing a **capped remaining budget** to the next hop through a trusted internal context, subtracting elapsed time before sending. A more standardized strategy is using deadline propagation built into an RPC/tracing stack if the project has one.

Illustrative internal header example:

~~~http
X-Request-Timeout-Ms: 620
~~~

**Do not treat this header as a Spring Cloud standard or an automatic mechanism.** If an application adopts it, it must build explicit policy enforcement in the gateway/callers. Never trust values sent by Internet users unconditionally; enforce min/max bounds and validate provenance at the trust boundary. If a caller sends the header after spending 100 ms preparing the request, the budget must reflect that elapsed time rather than forwarding the old number.

## 5. Modeling a Local Deadline in Java

The goal of the following class is managing **remaining time within one JVM**, not replacing HTTP client timeouts:

~~~java
import java.time.Duration;

public final class DeadlineBudget {

    private final long deadlineNanos;

    private DeadlineBudget(Duration total) {
        if (total.isZero() || total.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }

        // Suitable for short, bounded request budgets.
        this.deadlineNanos = System.nanoTime() + total.toNanos();
    }

    public static DeadlineBudget start(Duration total) {
        return new DeadlineBudget(total);
    }

    public Duration remaining() {
        long nanosLeft = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, nanosLeft));
    }

    public Duration allowanceForHop(
            Duration hopMaximum,
            Duration reservedForLater) {

        Duration available = remaining().minus(reservedForLater);

        if (available.isNegative() || available.isZero()) {
            throw new IllegalStateException("Request deadline exhausted");
        }

        return available.compareTo(hopMaximum) < 0
                ? available
                : hopMaximum;
    }
}
~~~

Example:

~~~java
DeadlineBudget budget =
        DeadlineBudget.start(Duration.ofMillis(1200));

// After doing some work in the caller:
Duration inventoryAllowance = budget.allowanceForHop(
        Duration.ofMillis(350),
        Duration.ofMillis(250)
);
~~~

The returned value is the **allowed budget** for inventory at that instant. You must feed this value into the HTTP client's actual timeout mechanism, as there is no single unified API across RestClient/WebClient/OpenFeign. This class is illustrative only and does not automatically cancel requests or propagate deadlines over the network.

When the budget is exhausted, **fail fast** per the business contract instead of sending a new request just to “try your luck.” In production, define a dedicated exception/response and combine with tracing to distinguish an exhausted deadline from a backend 500.

## 6. Sequential Chain: Cumulative Total Latency

For example, `order-service` calls inventory and then pricing, where the pricing step depends on the stock data just received:

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant O as order-service
    participant I as inventory-service
    participant P as pricing-service

    G->>O: GET /quote
    O->>I: GET /stock
    I-->>O: Stock result
    O->>P: GET /price
    P-->>O: Price result
    O-->>G: Quote
~~~

For three sequential stages with latencies `L1`, `L2`, `L3`:

\[
L_{\text{total}} \approx L_1 + L_2 + L_3 + L_{\text{overhead}}
\]

Here overhead includes network, serialization, scheduling, instance selection, and work outside those three calls. Retries increase total duration further.

For example, if inventory took 400 ms out of a 1,000 ms overall request budget, pricing must not set a 900 ms timeout even if its default config is 900 ms. The pricing hop must be bounded by the time actually left after inventory.

**Recommended approach:**

1. Start the deadline at a trusted boundary, such as the gateway or ingress service.
2. Record time before and after each stage.
3. Before every outbound call, recompute remaining budget and keep a reserve.
4. If insufficient time remains for the next step, return a timeout error or policy-defined degraded response.
5. If retries are permitted, fit backoff and all attempts inside the **existing** deadline rather than starting a fresh deadline.

## 7. Parallel Fan-Out: Never Simply Add All Timeouts

Suppose `order-service` calls inventory, pricing, and promotions **in parallel**:

~~~mermaid
flowchart TB
    O["order-service"] --> I["inventory-service"]
    O --> P["pricing-service"]
    O --> M["promotion-service"]
    I --> J["Join results"]
    P --> J
    M --> J
    J --> R["Response"]
~~~

If all start nearly simultaneously and order requires all three results, the fan-out latency is roughly:

\[
L_{\text{fanout}} \approx \max(L_I,L_P,L_M) + L_{\text{join}}
\]

Not `L_I + L_P + L_M` as in a sequential chain. Still, every branch must share the **same common deadline**, and none may extend its own budget when another branch runs slow.

Example with WebClient:

~~~java
Mono<Inventory> inventory = inventoryClient.getInventory(sku);
Mono<Price> price = pricingClient.getPrice(sku);
Mono<Promotion> promotion = promotionClient.getPromotion(sku);

return Mono.zip(inventory, price, promotion)
        .map(tuple -> new Quote(
                tuple.getT1(),
                tuple.getT2(),
                tuple.getT3()
        ))
        .timeout(Duration.ofMillis(900));
~~~

This is illustrative code; classes `Inventory`, `Price`, `Promotion`, and `Quote` must match the project's model. `Mono.zip` emits once all three branches succeed, and the outer `timeout` bounds the **wrapped portion of the pipeline**. If one branch fails, zip typically terminates with an error and may cancel subscriptions on the remaining branches.

Cancelling a subscription **does not guarantee** the backend stopped processing. Downstream services need their own deadline/cancellation policy if operations are expensive or have side effects.

### Fan-Out Increases the Probability of Hitting Tail Latency

If eight independent services each have a 99% chance of completing before a time threshold, the probability that **all eight** finish before the threshold is only about:

\[
0.99^8 \approx 0.9227 \;(92.27\%)
\]

This is a simplified model assuming independence; in reality, services may share a database or network, creating correlated failures. Never assume a multi-branch chain's p99 equals a single downstream service's p99. For wide fan-outs, evaluate which data is mandatory, apply graceful degradation and caching, and prune non-essential calls.

## 8. Retries Can Multiply Cost and Break Deadlines

Retries help recover from transient faults, yet each attempt costs time, resources, and sometimes triggers side effects. If one request tries three times (initial + two retries), and every layer in A→B→C independently retries three times, total attempts at the deepest layer can multiply across retry budgets in matching failure scenarios:

\[
3 \times 3 \times 3 = 27
\]

The number 27 only illustrates **multi-layer retry amplification across three tiers**, not a fixed Spring Cloud attempt count. Actual retry behavior depends on configuration, retry placement, error types, and stop conditions. Yet the lesson is clear: **never configure unbounded or uncoordinated multi-layer retries**.

A safer policy:

- Designate one layer responsible for retries whenever possible.
- Only retry transient errors and operations that are safe to repeat.
- Bound total attempts, backoff, jitter, and the end-to-end deadline.
- After each attempt, measure `remaining budget` before deciding whether enough time remains for another attempt.
- Avoid retrying when processing cost is high or the target system is overloaded.
- Distinguish connect errors, read timeouts, HTTP 429/503, and business errors; do not retry all 4xx/5xx statuses.
- For POST/PUT with side effects, use idempotency keys and consistent cross-service policies.

An error-prone timeline:

~~~text
Total budget: 1200 ms
Attempt #1: 500 ms -> timeout
Backoff #1: 200 ms
Attempt #2: 500 ms -> timeout
Backoff #2: 200 ms
Attempt #3: still wants to run 500 ms
           -> exceeds deadline even before Attempt #3 finishes
~~~

Even a 500 ms per-attempt timeout does not guarantee a retry chain completes within 1,200 ms.

## 9. Allocating Timeouts by Dependency Type

Not every downstream dependency needs the same timeout.

| Dependency | Characteristics | Design suggestion |
|---|---|---|
| Inventory stock read | Multiple replicas, typically idempotent on GET | Short timeout aligned to p99; bounded retries allowed |
| Payment transaction creation | Has side effects; cannot be repeated arbitrarily | Explicit deadline, idempotency key, restrict retries |
| Pricing calculation | May aggregate multiple data sources | Optimize dependencies; dedicated sub-budget inside total deadline |
| Recommendation | Usually non-essential for order placement | Short timeout and fallback omitting recommendations |
| Out-of-band reporting | Does not need to hold an HTTP request open | Queue/event; separate deadline/TTL for background processing |
| Identity provider | Issues tokens for service clients | Dedicated timeout and connection pool; cache valid tokens |

When designing SLOs, inspect each service's actual latency histogram (p50, p95, p99, p99.9), false-timeout rate, and business goals. Pick timeouts by balancing **false timeouts** (cutting off a request that would have succeeded) against **wasted work** (waiting too long on a request unlikely to succeed).

Do not blindly set timeouts equal to p99 assuming the SLO will always be met. One dependency's p99 may exceed the entire business deadline; in that case, redesign the architecture or accept fallback/degradation rather than just bumping a config number.

## 10. LoadBalancer Picks the Instance; The Caller Still Owns the Deadline

Spring Cloud LoadBalancer is responsible for picking a `ServiceInstance` from the list provided by `ServiceInstanceListSupplier`, potentially via discovery, caching, health checks, zone/hint filtering, and retry-aware logic. It is **not an end-to-end deadline system**.

~~~text
Caller with remaining budget
  -> service ID: inventory-service
      -> DiscoveryClient / ServiceInstanceListSupplier
      -> (cache / health / zone / hint if enabled)
      -> RoundRobin / Random / custom algorithm
      -> select ServiceInstance
      -> HTTP transport
      -> response / timeout / retry
  -> update remaining budget before next business step
~~~

Never treat health-endpoint probe intervals as business request limits:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        interval: 25s
~~~

`25s` here is the health-check cadence, **not** how long WebClient or OpenFeign can wait on inventory.

Similarly, cache TTL can delay instance-list updates; a recently disconnected replica may still be selected until discovery or the health supplier refreshes. Transport timeouts and controlled retries help recover from picking an unreachable instance, provided they stay within the remaining deadline.

Even when both services have multiple replicas, load may not balance evenly by completion time: Round Robin distributes selection counts fairly evenly without guaranteeing equal backend latency. Therefore, base timeouts on the service ID's SLO and latency distribution rather than expecting LoadBalancer policies to replace performance engineering.


## 11. Configuring Connect/Read Timeouts for RestClient

`RestClient` is Spring Framework's synchronous HTTP client. With `@LoadBalanced RestClient.Builder`, Spring Cloud LoadBalancer resolves the URI by service ID, and the request factory sends the HTTP request to the chosen instance.

Example of a RestClient for inventory:

~~~java
package com.example.order.http;

import java.time.Duration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(Duration.ofMillis(250));
        requestFactory.setReadTimeout(Duration.ofMillis(700));

        return builder
                .requestFactory(requestFactory)
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

- `@LoadBalanced` causes `inventory-service` to be resolved as a service ID.
- `connectTimeout` applies to establishing connections under this request factory.
- `readTimeout` bounds reading according to transport semantics, **not** the entire business operation's deadline.
- `SimpleClientHttpRequestFactory` illustrates the API. Production typically requires an HTTP transport with connection pooling, pool-acquire timeouts, TLS, connection reuse, and proper metrics.
- If sharing one builder across multiple clients, manage scoping or clone the builder so changing base URL or request factory does not affect other clients.

Calling inventory:

~~~java
public InventoryResponse getStock(
        RestClient inventoryRestClient,
        String sku) {

    return inventoryRestClient.get()
            .uri("/api/items/{sku}", sku)
            .retrieve()
            .body(InventoryResponse.class);
}
~~~

If the request's remaining overall deadline is only 300 ms, a 700 ms read timeout will not stop the caller after 300 ms. You must track remaining budget and configure timeouts/cancellation at the appropriate transport or execution layer. Merely wrapping a blocking call in `CompletableFuture.orTimeout` does not guarantee the HTTP request or backend work is aborted when the future times out.

## 12. WebClient: Transport Timeouts and Full Reactive Pipeline Timeouts

With Reactor Netty as the transport, WebClient can configure connect and response timeouts:

~~~java
package com.example.order.http;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {

        HttpClient transport = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 250)
                .responseTimeout(Duration.ofMillis(700));

        return builder.clone()
                .clientConnector(new ReactorClientHttpConnector(transport))
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

These two limits govern the HTTP transport per Reactor Netty semantics. They do not necessarily include pool wait, instance selection, access token retrieval, or work done before calling HTTP.

### Placing Timeout Outside Retry

If an inventory GET is permitted one retry on transient network errors:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<InventoryResponse> getWithinDeadline(
        String sku,
        DeadlineBudget budget) {

    return Mono.defer(() -> {
        Duration allowance = budget.allowanceForHop(
                Duration.ofMillis(800),
                Duration.ofMillis(150)
        );

        return inventoryWebClient.get()
                .uri("/api/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class)
                .retryWhen(
                        Retry.backoff(1, Duration.ofMillis(100))
                                .filter(error ->
                                        error instanceof WebClientRequestException)
                )
                .timeout(allowance);
    });
}
~~~

`InventoryResponse` is an application DTO; `inventoryWebClient` is an injected field. `Mono.defer` computes the allowance at subscription time, avoiding capturing a stale budget during reactive pipeline assembly.

Here, there is at most one retry, and the filter matches only `WebClientRequestException` rather than retrying every HTTP 503. `timeout(allowance)` sits **outside** `retryWhen`, so it covers all attempts and backoff inside the publisher. Reversing the timeout/retry order applies the timeout per individual subscription, extending total duration.

Reactive cancellation does not guarantee the backend stopped processing. If an operation has side effects, use idempotency or post-timeout result verification.

If the budget is already exhausted after an earlier step, `allowanceForHop` fails fast instead of starting a new GET with a default timeout.

## 13. OpenFeign: Configuring connectTimeout and readTimeout

With Spring Cloud OpenFeign, timeouts can be declared per Feign client/service ID:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 250
            readTimeout: 700
          payment-service:
            connectTimeout: 350
            readTimeout: 1100
~~~

These example values use **milliseconds** per standard OpenFeign configuration. Tune them using actual system latency and SLOs rather than treating them as universal defaults for every service.

These limits do not automatically include fetching access tokens, waiting on connection pools, discovery, backoff, retries, or business logic before/after the Feign call. Feign offers `Request.Options` and HTTP transport customizations, but there is no universal Spring Cloud OpenFeign property that automatically propagates the remaining end-to-end deadline to every call. If a **dynamic per-invocation timeout** is needed, design an abstraction or client customization matching your transport and version.

Simply adding `X-Request-Timeout-Ms` via a `RequestInterceptor` also **does not** make the HTTP client enforce that value. A header is only a contract; both server and caller must enforce the deadline.

Be careful with payments: the backend may commit a transaction right before the caller experiences a read timeout. Never retry POST blindly; use idempotency keys, status checks, and reconciliation.

## 14. Passing Budgets Across Hops Is an Application Design

When order calls inventory and inventory calls pricing, pricing knows nothing about the user's deadline if upstream only sends a URI and JSON.

~~~text
Gateway: creates a 1200 ms budget at the trust boundary

Order: spent 150 ms
       -> ~1050 ms remaining
       -> calls inventory with capped remaining budget

Inventory: spends another 250 ms
       -> ~800 ms remaining
       -> calls pricing with updated remaining budget

Pricing: derives database timeout from remaining time
       -> does not reset budget back to 1200 ms
~~~

An internal header can serve as the contract:

~~~http
X-Request-Timeout-Ms: 800
~~~

This is **not a standard automatic header in Spring Cloud LoadBalancer**. If you design it yourself, follow these rules:

1. The gateway must never trust arbitrary headers from Internet clients; strip or overwrite at the trust boundary.
2. Parse and clamp values within allowed min/max bounds; reject or cap negative, oversized, or malformed values.
3. Subtract time spent in the current hop before forwarding; never copy the old number untouched.
4. Keep a reserve to return the response and finish remaining work.
5. Receiving the header does not mean the transport or server automatically enforces the timeout.
6. Never send `System.nanoTime()` across machines; monotonic timestamps only have local meaning.
7. Wall-clock deadlines across hosts must account for clock skew and proper NTP synchronization.

If using an RPC stack with built-in deadline propagation, prefer that over inventing a custom protocol. For RestClient, WebClient, and HTTP Feign, the solution requires application-layer integration.

## 15. Coordinating Gateway, Caller, and Downstream Timeouts

One guiding rule is that **layers closer to the user need enough time to return a controlled error response** before a reverse proxy or gateway terminates waiting on its own.

Example:

~~~text
External client timeout:                1600 ms
Gateway upstream timeout:               1450 ms
Order end-to-end processing budget:     1250 ms
Inventory per-hop timeout cap:           450 ms
Pricing per-hop timeout cap:             350 ms
Reserve for response/jitter:             remainder
~~~

These are illustrative numbers only. If the gateway waits less time than internal processing budgets, the gateway may return 504 while order still holds threads/connections and calls downstream services.

Additional places to check:

- Server-side timeouts do not always abort synchronous business code; a Spring MVC async timeout property does not automatically interrupt every blocking call.
- A client timeout closing a connection or throwing an exception does not mean downstream stopped processing.
- Connection pool acquire timeouts and queuing time can drain the deadline before network I/O even begins.
- Executor saturation and queue wait times must also be counted inside the deadline.
- Both the gateway and services may have retries enabled, so audit the total attempt count across layers.

If a piece of data is non-essential, such as recommendations, prefer a short timeout and an acceptable partial result or fallback instead of holding up the entire business operation.


## 16. Cancellation Does Not Mean Rollback

Timeouts do not guarantee all resources and side effects are rolled back. A payment request can commit a transaction even if the caller never receives the response:

~~~mermaid
sequenceDiagram
    participant U as User
    participant O as order-service
    participant P as payment-service
    participant D as Payment database

    U->>O: POST /orders (deadline 1200 ms)
    O->>P: POST /payments
    P->>D: Begin transaction
    Note over O: Deadline exhausted
    O-->>U: Timeout response
    P->>D: Commit transaction
    D-->>P: Commit OK
    Note over P: Side effect may already have occurred
~~~

When a WebClient publisher is cancelled or RestClient/OpenFeign throws a timeout, the backend **may still continue** executing; never assume network cancellation automatically rolls back a database transaction.

For write operations:

- Use an **idempotency key** to detect duplicate requests.
- Persist enough transaction state to query the outcome after a timeout.
- Never blindly retry POST requests for payments, order creation, or stock updates.
- Consider sagas/compensation or reconciliation mechanisms.
- If work takes longer than HTTP can reasonably wait, return `202 Accepted` with a job ID, followed by polling, webhooks, or async processing.
- Servers may support deliberate cancellation checks, stopping only at safe checkpoints.

## 17. Combining Timeouts with Circuit Breakers, Bulkheads, and Load Shedding

Timeouts bound **wait time**, while complementary mechanisms address related failure modes:

| Mechanism | Key question |
|---|---|
| Deadline/timeout | How long are we still allowed to wait? |
| Circuit breaker | Should we keep calling a dependency that is failing heavily? |
| Bulkhead/semaphore | How many concurrent calls are permitted? |
| Rate limiting/load shedding | Should we accept more load when already saturated? |
| Retry/backoff | Should we retry? How many times and with what spacing? |
| Spring Cloud LoadBalancer | Which instance should be chosen from candidates? |
| Health-check supplier | Which instances are currently considered healthy enough? |
| Idempotency | Is sending the same request multiple times safe? |

For example, pricing is slow and 200 concurrent requests arrive: a 10-second read timeout can still tie up huge numbers of threads and connections to pricing. Combining short timeouts, bulkheads, and circuit breakers prevents pool exhaustion from taking down unrelated features in `order-service`.

Do not enable retries + circuit breakers across multiple layers without observability. An open circuit breaker failing fast even when deadline budget remains is often the right protective behavior.

## 18. Observing Latency, Retries, and Remaining Time

If logs contain only `"request timed out"`, you cannot tell whether the fault occurred in discovery, pooling, connect, TLS, backend processing, the token server, or backoff. Good observability captures:

| Data group | Question to answer |
|---|---|
| End-to-end latency histogram | How long did users wait; do p95/p99 meet the SLO? |
| Remaining budget at each hop | Which leg consumed too much time? |
| Connection pool acquire latency | Is the pool exhausted and queuing requests? |
| Connect/TLS duration | Is connection setup slow? |
| Time to first byte / response latency | Is the backend slow or is the network slow? |
| Service discovery/selection latency | Is the registry or LoadBalancer supplier slow? |
| Retry count, backoff | How many attempts did a single business operation actually send? |
| Error category | How do connect timeouts, read timeouts, overall deadlines, and HTTP 503/504 differ? |
| Service ID / instance ID | Are errors concentrated on one replica or across all instances? |
| Cancelled / late work | Did the backend keep working after the caller abandoned the result? |

Use Micrometer Observation/Tracing, Spring Cloud LoadBalancer lifecycle metrics, and HTTP-client instrumentation suited to your version. Never put bearer tokens, sensitive query strings, or raw user IDs into metric labels or unrestricted logs.

Always distinguish **logical requests** from **HTTP attempts**:

~~~text
1 logical quote request
   -> inventory logical call
        -> attempt 1: connect timeout
        -> attempt 2: 200 OK
   -> pricing logical call
        -> attempt 1: 200 OK

Logical quote requests:       1
Downstream HTTP attempts:     3
~~~

If order counts only logical calls while the inventory backend counts every attempt, numbers will differ without any bug. Use consistent metric names and logging, correlated via trace/correlation IDs, without treating trace context as authorization data.

## 19. Hands-On Lab: One Slow Backend in a Call Chain

Use `SimpleDiscoveryClient` in order-service to register two inventory replicas:

~~~yaml
server:
  port: 8080

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

In inventory-service, add a delay-simulating endpoint, **strictly for test environments**:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DelayController {

    private final Environment environment;

    public DelayController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/demo/delay")
    public Map<String, Object> delay(
            @RequestParam(defaultValue = "100") long delayMs)
            throws InterruptedException {

        // Allow only a small range in the lab; never expose publicly.
        long boundedDelay = Math.max(0L, Math.min(delayMs, 1500L));
        Thread.sleep(boundedDelay);

        return Map.of(
                "instance", environment.getProperty(
                        "server.port", "unknown"),
                "delayMs", boundedDelay
        );
    }
}
~~~

Run the same inventory artifact on ports 8081 and 8082. In order-service, use load-balanced RestClient/WebClient or OpenFeign to call `http://inventory-service/demo/delay?delayMs=...`, and expose `GET /orders/demo-delay?ms=...` as a proxy. This endpoint is something **to implement** in the lab, not a built-in Spring Cloud feature.

Test three scenarios:

1. **Normal:** inventory delays 100 ms, caller deadline is 900 ms; request succeeds with spare budget remaining.
2. **Slow backend:** inventory delays 1,100 ms, caller hop cap is 450 ms. Observe connect/read/response/total timeouts and note that the backend may continue processing after the caller gives up.
3. **One replica down:** stop port 8082; static discovery may still return that address. Observe connect failure, bounded retries, and health supplier behavior if configured.

Illustrative PowerShell command for measuring external timing:

~~~powershell
Measure-Command { try { Invoke-RestMethod -Uri "http://localhost:8080/orders/demo-delay?ms=1100" -TimeoutSec 3 | Out-Null } catch { Write-Host $_.Exception.Message } }
~~~

`-TimeoutSec 3` controls only the **PowerShell client** timeout; it does not set timeouts on RestClient, WebClient, or Feign inside order-service.

Record your measurements:

| Case | Overall deadline | Hop cap | Backend delay | Attempts | Actual latency | Result |
|---|---:|---:|---:|---:|---:|---|
| Normal | 900 ms | 450 ms | 100 ms | Measure | Measure | Expected success |
| Slow backend | 900 ms | 450 ms | 1,100 ms | Measure | Measure | Expected timeout |
| One replica down | 900 ms | 450 ms | — | Measure | Measure | Depends on discovery/retry |

Do not fill in fake latencies or attempts without running the lab. Measure on both caller and backend to compare attempts against logical requests.

## 20. Common Timeout Design Mistakes

| Symptom | Common mistake | How to fix |
|---|---|---|
| Gateway returns 504, order keeps running | Gateway timeout shorter than internal budget | Coordinate deadlines, handle cancellation and late work |
| Each hop times out at 2s, total request takes 6s | No end-to-end budget | Create an overall deadline and compute remaining before each hop |
| WebClient retries drag past the deadline | `timeout` placed inside retry or deadline reset | Wrap the entire retry chain with the original deadline |
| OpenFeign readTimeout does not stop hung token server | Token acquisition sits outside Feign transport | Set token endpoint timeouts and an overall deadline |
| Pool waits long despite short connect timeout | No limit on connection pool acquisition | Configure pool/acquire timeout and concurrency |
| HTTP 503 mistaken for read timeout | No instance / proxy / backend returned status | Classify selection, status, and transport errors separately |
| Health-check interval treated as request timeout | Confusing probe schedule with HTTP timeout | Configure transport timeouts explicitly |
| Duplicate transactions created | Retrying POST after response timeout | Idempotency key, outcome check, and reconciliation |
| Every service retries multiple times | Retry amplification across tiers | Designate the retry tier and total attempt budget |
| Backend receives more requests than caller metrics show | One logical call generates multiple HTTP attempts | Separate logical and attempt metrics |
| Budget grows across hops | Resetting budget or copying stale headers | Decrement remaining, clamp headers, and keep reserves |
| Payment still commits after timeout | Caller timeout does not roll back transactions | Design cancellation/side-effect handling explicitly |
| Fan-out p99 worse than individual services | Multiple branches must all finish | Reduce fan-out; add fallbacks for non-essential branches |

## 21. Pre-Release Checklist

- [ ] Clear end-to-end SLO/deadline for every API.
- [ ] Distinguish sequential chains, parallel fan-outs, and async jobs.
- [ ] Every hop uses remaining budget rather than resetting to default timeouts.
- [ ] Keep reserves for remaining work and returning responses.
- [ ] Separate connection pool acquire, connect, TLS, response/read, discovery, and total timeouts.
- [ ] RestClient/WebClient/OpenFeign transport timeouts match requirements.
- [ ] Retries have bounded attempts, backoff, and fit inside the original deadline.
- [ ] Never retry side effects without idempotency/reconciliation.
- [ ] Gateway, callers, and downstream services have aligned limits.
- [ ] Servers do not assume caller timeouts cancel backend work.
- [ ] If using a deadline header, validate, clamp, and decrement by elapsed time.
- [ ] Never transmit `System.nanoTime()` directly across machines.
- [ ] Dedicated timeouts exist for token servers, databases, queues, and pools.
- [ ] Evaluate bulkheads/circuit breakers/load shedding to prevent cascading failures.
- [ ] Metrics distinguish logical calls, attempts, and each timeout type.
- [ ] Test slow backends, dead replicas, pool exhaustion, slow token servers, and multi-tier retries.
- [ ] Verify behavior with p95/p99 end-to-end load testing, not just reading YAML.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstance`, discovery, caching, health checks, and retries.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient and request factories.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive client, statuses, filters, and timeouts.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign client, connect/read timeouts, and LoadBalancer.
- [Reactor Core — Reference](https://projectreactor.io/docs/core/release/reference/): `Mono.timeout`, retries, cancellation, and composition.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics and distributed tracing.

**Conclusion:** In a multi-service chain, the question is not just “what should `readTimeout` be?” but “how much of the **remaining budget** from a shared-deadline request may each leg spend?” Transport timeouts protect local resources; end-to-end deadlines protect SLOs; retries, LoadBalancer, health checks, circuit breakers, and observability must all operate within that budget. Computing remaining time at the right moment, never resetting deadlines, and controlling post-timeout side effects will cut tail latency, retry amplification, and cascading failures.
