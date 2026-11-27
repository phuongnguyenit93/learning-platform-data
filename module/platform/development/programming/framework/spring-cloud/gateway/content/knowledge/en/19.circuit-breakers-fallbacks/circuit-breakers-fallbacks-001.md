# The Role of a Circuit Breaker in a Gateway Call Chain

## 1. Why Does an API Gateway Need a Circuit Breaker?

In a microservices architecture, a request from a client can pass through **Spring Cloud Gateway** and then reach an Order service, Inventory service, or Payment service. The gateway selects a route using predicates, applies a filter chain, transforms the path/headers, and resolves `lb://service-id` to a specific backend. When a backend loses connectivity or processes requests very slowly, requests passing through the gateway risk waiting, failing, or holding onto resources for too long.

A **circuit breaker** is a protective mechanism at the service call boundary: it observes call outcomes, **temporarily rejects new calls** if the failure rate or slow-call rate exceeds a threshold, and then allows a few calls through to assess recovery. Instead of letting every request continue pouring into a degraded dependency, the gateway can **fail fast** and use a controlled fallback.

For example:

~~~text
Client -> Gateway -> Orders service
            |
            +-- normal: proxy requests to Orders
            |
            +-- Orders fails consecutively:
                  Circuit breaker OPEN
                  -> skip new calls to Orders
                  -> return an appropriate error or fallback
~~~

A circuit breaker is very useful in **Spring Cloud Gateway** because the gateway is often a shared entry point for many routes and many clients. However, it is **not a backend healing solution**, and it does not replace authentication, rate limiting, timeouts, retries, service discovery, or request monitoring.

### After This Lesson, You Will Be Able To

1. Explain the role of a circuit breaker in the **filter chain** and the **CLOSED, OPEN, HALF_OPEN** states.
2. Distinguish upstream errors from user errors, and understand **which outcomes are counted as failures**.
3. Configure the **CircuitBreaker GatewayFilter Factory** with **Spring Cloud CircuitBreaker + Resilience4j** on Gateway Server WebFlux.
4. Create an internal fallback using `fallbackUri: forward:/...` while keeping status, headers, and body consistent.
5. Explain the relationships between a circuit breaker, timeouts, retries, load balancing, TLS, and connection pools.
6. Choose an appropriate configuration for a dependency; avoid lumping failures of multiple services into a single circuit breaker.
7. Verify OPEN/HALF_OPEN transitions, blocked requests not reaching the upstream, recovery, and user impact.
8. Safely read metrics/events to diagnose incidents instead of looking only at the final HTTP status code.

> **Scope:** This lesson belongs to the **Circuit Breakers and Fallbacks** chapter and uses **Spring Cloud Gateway Server WebFlux**, Spring Cloud CircuitBreaker, and Reactor/Resilience4j. Server Web MVC uses a different mechanism. Starter names, YAML namespaces, properties, and detailed feature support depend on the version; verify them against the dependency BOM in use.

## 2. Which Layers Does a Call Pass Through?

In Gateway Server WebFlux, a request is matched to a route and then passes through **GlobalFilter** and **GatewayFilter** instances. When a route attaches `CircuitBreaker`, the filter wraps the downstream processing in the chain that it controls.

~~~mermaid
flowchart TD
    C[Client request] --> S[Spring Security / WebFlux filters]
    S --> M[RoutePredicateHandlerMapping]
    M --> H[FilteringWebHandler]
    H --> P[Path, header filters]
    P --> B[CircuitBreaker GatewayFilter]
    B --> Q{Circuit permits call?}
    Q -->|CLOSED or permitted probe| D[Downstream filter chain]
    D --> L[LoadBalancer if lb scheme]
    L --> N[Netty HTTP routing]
    N --> U[Orders upstream]
    U --> R[Gateway response]
    Q -->|OPEN, call denied| F[Short-circuit / fallback]
    F --> R
~~~

The diagram illustrates the logical relationship and **does not replace the exact filter ordering** in an application. The gateway includes components such as `RouteToRequestUrlFilter`, `ReactiveLoadBalancerClientFilter`, `NettyRoutingFilter`, and `NettyWriteResponseFilter`. Some filters can run pre/post logic differently depending on their order; to understand which calls are observed by the breaker, you must check the **filter order** and the types of errors that actually occur.

### Wrapping a Reactive Publisher

In WebFlux, `GatewayFilter.filter(exchange, chain)` returns a `Mono<Void>`. This publisher represents the asynchronous lifecycle of the request; it does not mean the response has no body.

~~~java
// Conceptual code, not the implementation of CircuitBreaker GatewayFilter:
Mono<Void> downstream = chain.filter(exchange);
return protectWithCircuitBreaker(downstream);
~~~

The protection layer monitors **completion/error signals** or HTTP outcomes configured to be counted as failures. If the breaker is OPEN, it can prevent the corresponding downstream flow from starting and switch immediately to the fallback branch. You should not manually call `subscribe()` or `block()` inside a GatewayFilter, because doing so can break lifecycle management, backpressure, and cancellation.

### Three Independent Decisions in a Request

| Component | Question It Answers | What It Does Not Do on Its Own |
| --- | --- | --- |
| Route predicate | Which route does the request match? | Does not verify identity or guarantee that the backend is healthy |
| Authentication/authorization | Does the caller have permission to access this API? | Does not protect against slow connections or failing backends |
| Circuit breaker | Should calls to this dependency continue right now? | Does not grant permissions, fix requests, or automatically generate a valid business response |

**A circuit breaker must complement security policies**, not create a bypass. For example, a fallback must not return sensitive order information to an unauthenticated user just because the Orders backend is unavailable.

## 3. The CLOSED, OPEN, and HALF_OPEN States

The standard circuit breaker model consists of three states:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure rate / slow-call rate exceeds threshold after enough samples
    OPEN --> HALF_OPEN: Wait duration expires, with probing attempt
    HALF_OPEN --> CLOSED: Probes meet recovery criteria
    HALF_OPEN --> OPEN: Probes indicate the dependency is still degraded
~~~

| State | New Requests | What Is Recorded |
| --- | --- | --- |
| **CLOSED** | Normally allowed through to downstream | Successes, failures, and possibly slow calls in the sliding window |
| **OPEN** | Protected calls are typically rejected immediately | Number of unpermitted calls, wait time until the recovery phase |
| **HALF_OPEN** | Only a limited number of probe calls are allowed through | Probe outcomes determine whether to transition back to CLOSED or return to OPEN |

**CLOSED does not mean the backend is always healthy.** It only indicates that the breaker still allows calls based on current metrics and conditions. A single error does not necessarily open the circuit. Before `minimumNumberOfCalls` is reached, the circuit breaker typically does not have enough samples to evaluate the failure rate threshold.

**OPEN does not mean the gateway returns HTTP 503 in every configuration.** The outcome depends on whether `fallbackUri` is configured, how the fallback constructs the status/body, and the error handler. A blocked call is typically represented by an exception type such as `CallNotPermittedException` at the Resilience4j layer; the final status must be explicitly designed rather than inferred solely from the OPEN state.

**HALF_OPEN does not mean traffic is fully reopened.** Only a limited number of requests are allowed through as probes; other requests may continue to be rejected. Once enough results are collected, the breaker decides whether to return to CLOSED or OPEN according to its policy.

### Illustrative Timeline

~~~text
00:00  CLOSED      Orders requests pass through
00:10  CLOSED      Failure rate rises, but not enough samples yet
00:15  OPEN        Enough samples collected and failure threshold exceeded
00:16  OPEN        New requests fail fast / fallback; Orders is not called
00:45  HALF_OPEN   A limited number of probe calls are permitted
00:46  CLOSED      Probes succeed sufficiently, normal traffic resumes
~~~

The timestamps above are **illustrative only**, not default per-second behavior. Transition timing, probe scheduling, and rate calculation depend on configuration such as `slidingWindowSize`, `minimumNumberOfCalls`, `failureRateThreshold`, `waitDurationInOpenState`, and `permittedNumberOfCallsInHalfOpenState`. Some implementations transition OPEN → HALF_OPEN **when a call arrives after the wait duration**, rather than proactively via a timer.

### Special States

Resilience4j also provides special states such as `DISABLED`, `FORCED_OPEN`, and `METRICS_ONLY` depending on the API/version and management operations. They have different semantics from the normal CLOSED/OPEN/HALF_OPEN cycle; only use them with proper operational procedures, authorization, and monitoring. **Do not treat FORCED_OPEN as a maintenance tool without consequences for clients.**

## 4. When Is a Call Counted as a Failure?

A common mistake is assuming that "any HTTP 4xx/5xx opens the breaker." **Which signals the breaker counts as failures depend on the GatewayFilter layer, exceptions, and configuration.**

For example:

| Outcome | Should It Count as a Dependency Failure? | Reason |
| --- | --- | --- |
| Connection refused | Usually yes | The dependency is unreachable |
| TCP connect / TLS handshake failure | Usually yes | The gateway cannot establish a valid connection |
| HTTP client response timeout | Usually yes when it emits an exception tracked by the breaker | The upstream did not respond within the deadline |
| HTTP 503 returned by backend | Possibly, if configured to treat this status as a failure | Backend reports it is unavailable |
| HTTP 502 returned by proxy/backend | Possibly, depending on contract/statusCodes | Gateway/upstream chain error |
| Backend HTTP 500 | Possibly, if the error is a type that needs protection | Internal server error requiring investigation |
| HTTP 404 because an order does not exist | **Usually no** | Normal business outcome for a resource lookup API |
| HTTP 400 due to an invalid request | **Usually no** | Caller must fix input, not a broken backend |
| HTTP 401/403 due to missing permissions | **Should not** | AuthN/AuthZ is a security boundary; do not turn it into a successful fallback |
| HTTP 429 due to Gateway rate limit | **Should not** | Edge traffic protection, does not prove upstream failure |
| Client cancels request | Depends on configuration and cause | Not a backend failure by default; cancellation should be observed |

With the **CircuitBreaker GatewayFilter**, exceptions emitted during downstream processing can typically be counted as failures. If the backend returns **a normal HTTP response with status 500**, it can still be a reactive stream that completes normally in terms of signals; to make the breaker classify certain statuses, Gateway versions support the `statusCodes` argument on the filter to trigger the corresponding handling.

Therefore, you cannot just see a client receiving 500 and conclude that Resilience4j's failure count increased. Configure **which codes truly need to be counted**, verify with metrics/events, and avoid dumping all 4xx responses into circuit breaking.

### Why Not "Catch Everything" as a Fallback?

If the circuit breaker wraps exceptions from authentication or request validation logic in the filter chain, a caller-induced error can be turned into an upstream error and trigger a fallback. That distorts status codes, blurs audit logs, and risks masking security errors. Limit the filter scope, decide which exception/status types should be recorded, and let Spring Security handle 401/403 at the proper layer.

## 5. How a Circuit Breaker Differs from Timeouts, Retries, Rate Limiters, and Load Balancers

Multiple mechanisms address reliability, yet they answer different questions:

| Mechanism | Primary Goal | If Missing or Misused |
| --- | --- | --- |
| **Connect/response timeout** | Limit how long an operation can wait | Requests can hold connections and resources for too long |
| **Retry** | Retry a transient failure under specific conditions | Can amplify load, create duplicate requests, or repeat side effects |
| **Circuit breaker** | Temporarily stop calling a degraded dependency | Does not set timeouts or fix a broken backend on its own |
| **Rate limiter** | Limit client traffic entering the Gateway | Does not detect whether a service is broken on its own |
| **Load balancer** | Select a ServiceInstance | Does not guarantee the selected instance is healthy |
| **Bulkhead** | Limit resources/concurrency per group | Circuit breaker does not replace isolation |
| **Fallback** | Produce an alternative outcome with a clear contract | Can mask errors or return invalid data |
| **Health/readiness** | Reflect the readiness of an instance/service | Registry can remain stale in the short term |

### Without Timeouts, the Circuit May Open Very Slowly

Suppose many requests are sent to a backend that **hangs indefinitely** without emitting an error. Without a timeout, long-waiting calls may not yet produce a failure outcome for the circuit breaker to evaluate. A circuit breaker **does not automatically turn every call into a call with a deadline**. In some Resilience4j configurations, slow-call thresholds measure completed durations, so a hanging call does not automatically become a failure just because it is "slow."

A solution usually needs an **appropriate response timeout/TimeLimiter** alongside the circuit breaker. You must understand timeouts set by the HTTP client, Gateway route, proxy, TimeLimiter, or client; they may have different semantics regarding when the clock starts and how they react to streams.

### Retries Can Overload an Already Weak Backend

If a request goes through a Retry filter and is sent 3 times, a burst of 1,000 client requests can generate up to thousands of additional backend calls. A circuit breaker can prevent load piling up when a dependency fails, but **the order of Retry and CircuitBreaker in the filter chain** determines whether the breaker sees each individual attempt or a single combined result. You must verify based on the application's actual filter order, not guess from textual order in YAML.

**Do not arbitrarily retry payment/order-creation POSTs.** If the backend already processed the request but the response was lost, a retry can create duplicate side effects. An idempotency key, deadline, restricted retry policy, and testing are required.

## 6. Underlying Technologies: Spring Cloud CircuitBreaker and Resilience4j

In Spring Cloud Gateway Server WebFlux, the **CircuitBreaker GatewayFilter Factory** builds on the **Spring Cloud CircuitBreaker** abstraction. A common implementation is **Resilience4j**, which provides the state machine, sliding windows, thresholds, and metrics/events.

~~~mermaid
flowchart LR
    G[Gateway CircuitBreaker filter] --> A[Spring Cloud CircuitBreaker abstraction]
    A --> R[Resilience4j reactive implementation]
    R --> W[Sliding window + thresholds]
    W --> S[CLOSED / OPEN / HALF_OPEN]
    R --> M[Events / metrics]
~~~

A common Maven dependency when the project already manages versions via the Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

In addition to that dependency, the application needs the **Spring Cloud Gateway Server WebFlux starter**, a compatible Spring Boot version, and an appropriate HTTP proxy mechanism. Gateway starter names may vary across release trains; do not arbitrarily pin a Resilience4j version detached from the project's dependency management.

### Concepts That Must Be Distinguished

| Name | Role |
| --- | --- |
| **Spring Cloud Gateway CircuitBreaker filter** | Wraps downstream calls belonging to a route |
| **Spring Cloud CircuitBreaker** | API abstraction for using a backend resiliency implementation |
| **Resilience4j CircuitBreaker** | State machine + conditions to permit/reject calls |
| **Resilience4j TimeLimiter** | Can limit the duration of an operation when properly integrated |
| **Micrometer/Actuator** | Collects and exposes appropriate metrics/events when enabled |

A circuit breaker does not **automatically know** the state of the entire cluster. Statistics are normally tied to the **instance/application process** or the circuits created within it. If the Gateway has 5 replicas, circuits with the same breaker name across 5 replicas do not share a distributed counter by default. That affects when circuits open when each replica observes different traffic.

## 7. Declaring a CircuitBreaker GatewayFilter for a Route

For example, the Orders service is registered in service discovery with the service ID `orders-service`. Clients call `GET /api/orders/42`, while the backend exposes `GET /orders/42`. The Gateway uses `StripPrefix=1` to drop `api` before proxying:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
                - name: CircuitBreaker
                  args:
                    name: ordersCircuitBreaker
                    fallbackUri: forward:/internal/fallback/orders
                    statusCodes:
                      - 500
                      - 502
                      - 503
~~~

**The components:**

- `id: orders-read` is the route name for tracking traffic and configuration; it is not the breaker name.
- `uri: lb://orders-service` uses **Spring Cloud LoadBalancer** together with a ServiceInstance source to select an instance. Appropriate load balancer and discovery/supplier dependencies are required.
- `Path=/api/orders/**` and `Method=GET` define the set of requests passing through the route. Restricting to GET in the example helps the fallback maintain a clear contract.
- `StripPrefix=1` causes the backend to receive `/orders/42` instead of `/api/orders/42`. It does not itself decide errors or fallbacks.
- `name: ordersCircuitBreaker` identifies the breaker so the corresponding Resilience4j configuration can be applied.
- `fallbackUri: forward:/internal/fallback/orders` points to an **internal handler** inside the Gateway application via the `forward:` mechanism; it is not calling an arbitrary Internet URL.
- `statusCodes` specifies upstream statuses that the Gateway can treat as failures to trigger the breaker/fallback mechanism, if the version of the CircuitBreaker GatewayFilter in use supports this syntax.

**Special note about status codes:** An HTTP 500 or 503 response from the backend does not necessarily produce a reactive `onError`. `statusCodes` bridges HTTP status interpretation with the breaker mechanism. However, not all errors—such as a valid 404 or a 401/403 from Spring Security—should be added to this list.

### Version and Environment Compatibility

In some earlier **Gateway Server WebFlux** versions, routes reside under:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        # route definitions for the corresponding version
~~~

In newer lines, it may be `spring.cloud.gateway.server.webflux.routes`. **Do not copy both namespaces at the same time expecting automatic compatibility across all releases.** Check the starter, configuration metadata, and actual loaded routes. You should also verify the CircuitBreaker/statusCodes API of the version in use. The example is a practical design, **not a configuration that has been run and certified on every Spring Cloud Gateway release**.

### If You Need a Fallback in Another Service

The Gateway CircuitBreaker `fallbackUri` in WebFlux lines typically requires the `forward:` scheme to dispatch to a **handler inside the Gateway application**. If you want to call another fallback service, you need to design an appropriate intermediate route/forward handler, handle outbound authentication and authorization, and protect against the fallback itself failing. Do not simply change `fallbackUri` to `http://other-service` and assume the factory will support it.

## 8. Configuring Resilience4j for the Declared Breaker Name

Resilience4j thresholds and sliding windows can be declared via configuration. For example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      ordersCircuitBreaker:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

The values above are **illustrative numbers**, not suitable defaults for every service:

| Parameter | Meaning in the Example |
| --- | --- |
| `slidingWindowType: COUNT_BASED` | Evaluates the most recent calls by count, rather than a time-based window |
| `slidingWindowSize: 20` | Examines up to the 20 most recent call outcomes in the window |
| `minimumNumberOfCalls: 10` | Waits for at least 10 recorded calls before evaluating thresholds |
| `failureRateThreshold: 50` | Percentage threshold of calls considered failures |
| `slowCallRateThreshold: 70` | Percentage threshold of slow calls |
| `slowCallDurationThreshold: 2s` | Calls completing slower than this threshold are considered slow |
| `waitDurationInOpenState: 30s` | Duration in OPEN before transitioning to attempt recovery |
| `permittedNumberOfCallsInHalfOpenState: 3` | Limit on the number of probe calls in HALF_OPEN |

### Reading Thresholds Through Numbers

Suppose 10 calls are recorded, with 6 failures matching the failure policy:

~~~text
Recorded calls        : 10
Counted failures      :  6
Failure rate          : 60%
Illustrative threshold: 50%
Result                : Eligible to open the circuit
~~~

If only 4/10 calls fail (40%), the illustrative configuration has not reached the **failure-rate threshold**; however, it could still reach the **slow-call-rate threshold** if many requests take longer than 2 seconds to complete. A request can be both slow and failed; how statistics and windows are calculated is governed by Resilience4j.

**Do not confuse minimumNumberOfCalls with maxConcurrency.** A breaker is not a semaphore bulkhead; `minimumNumberOfCalls` is the minimum sample count for rate evaluation, **not** a limit of 10 concurrent requests.

### Questions to Ask Before Choosing Thresholds

1. How many requests per second does the service receive, and are there large bursts?
2. Which exceptions and status codes represent genuine dependency failures?
3. What is the latency SLO? The slow-call threshold should reflect actual serving behavior, not an arbitrary 2 seconds.
4. Once OPEN, is there a fallback that is **truly safe** to return to clients?
5. How many probes can HALF_OPEN allow without causing a sudden load spike?
6. Are there multiple Gateway replicas? Each replica may open its circuit at a different time.
7. Does any dependency require separate breakers per tenant/service operation?

When request volume is low, a breaker with a very short window can open due to a few isolated errors, while a very long window can react too slowly. Test against realistic traffic and observe false positives/false negatives.

## 9. Writing an Internal Fallback That Follows the HTTP Contract

If the `orders-read` route cannot call Orders, the Gateway can forward to a local WebFlux handler and send a clear, consistent response:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class OrdersFallbackController {

    @GetMapping(
            path = "/internal/fallback/orders",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<Map<String, Object>>> ordersUnavailable() {
        Map<String, Object> payload = Map.of(
                "code", "ORDERS_TEMPORARILY_UNAVAILABLE",
                "message", "Unable to retrieve orders at this time",
                "retryable", true
        );

        return Mono.just(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .cacheControl(CacheControl.noStore())
                        .body(payload)
        );
    }
}
~~~

The snippet above returns **503 Service Unavailable**, a JSON body, and `Cache-Control: no-store`. It does not pretend that the order was queried successfully and does not expose stack traces or tokens. `Content-Length` can be calculated/adjusted by the framework when serializing the body; do not set it manually based on Vietnamese character count.

**Important:** This controller **should only be invoked through a controlled fallback flow**. Because a local WebFlux endpoint can also be called directly if the application exposes an entry path, you must restrict external HTTP access to `/internal/fallback/orders` with appropriate routing/security protection. Do not allow anyone to call the fallback directly to obtain sensitive data. When using `forward:`, how WebFilters/security are re-triggered on an internal dispatch may differ from a fresh HTTP request; test both the **direct call** and **internal forward** paths.

### Fallbacks Should Not Always Return Fake Data

| API or Scenario | Potentially Appropriate Fallback | What Not to Do |
| --- | --- | --- |
| Public product list | Return valid cached data, explicitly marking staleness if the contract allows | Return current inventory from an old cache and assert it as certain |
| Reading personal orders | 503 + retry notice or verified data from a trusted backup source | Fabricate a "not found" order to hide an upstream error |
| Pricing/promotions | Verified fallback data per policy | Send incorrect prices that lead to wrong purchasing decisions |
| Placing orders, payments | Usually return a temporary error or a system-confirmed pending state | Return 200/201 success when the actual operation has not been confirmed |
| Authentication/authorization | Maintain a fail-closed model when the authority source is unavailable | Use a fallback to grant access or skip JWT verification |

**The fallback is part of the API contract.** It must accurately communicate "the request has not been processed," "the data is temporarily unavailable," or "cached data may be stale" depending on the situation. Do not turn write operations into "success" just so clients do not see 5xx.

### Is Retry-After Needed?

With 503, `Retry-After` can be sent if there is a **reasonable basis** to guide clients. Do not set `Retry-After: 30` solely because `waitDurationInOpenState=30s`: the breaker's OPEN duration is an internal mechanism and **does not guarantee** that Orders will recover in exactly 30 seconds or that all Gateway replicas share the same state.

## 10. Request Sequences for Success, Failure, and OPEN Circuit

With the route and fallback above, there are three important branches.

### 10.1. CLOSED and Upstream Is Working

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant CB as CircuitBreaker
    participant O as Orders
    C->>G: GET /api/orders/42
    G->>CB: Protected downstream call
    CB-->>G: Permit call (CLOSED)
    G->>O: GET /orders/42
    O-->>G: 200 order JSON
    G-->>C: 200 order JSON
~~~

A 200 at the client does not by itself prove the breaker recorded a success for the backend: you need to check status/error classification and timing. In the common case, however, a normally completed downstream call is recorded by the breaker as a success.

### 10.2. CLOSED but Upstream Returns a Configured Failure

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant CB as CircuitBreaker
    participant O as Orders
    participant F as Local fallback
    C->>G: GET /api/orders/42
    G->>CB: Protected call
    CB-->>G: Permit
    G->>O: GET /orders/42
    O-->>G: 503 Service Unavailable
    G->>CB: Classified failure (configured 503)
    CB-->>G: Fallback path
    G->>F: forward:/internal/fallback/orders
    F-->>C: 503 JSON fallback
~~~

When a status is configured as a breaker failure, the call can increment the failure metric and enter the fallback. How status codes are translated into failures and routed to the fallback depends on the Gateway filter implementation/version; **test with a backend stub instead of relying only on diagrams**.

### 10.3. OPEN: Blocked Before Calling Orders

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant CB as CircuitBreaker
    participant O as Orders
    participant F as Local fallback
    C->>G: GET /api/orders/42
    G->>CB: Request permit
    CB-->>G: Denied (OPEN)
    Note over G,O: No HTTP call to Orders is made
    G->>F: forward:/internal/fallback/orders
    F-->>C: 503 JSON fallback
~~~

**Core value:** when OPEN, protected requests **do not continue to the dependency** on that branch. This allows the Gateway to reduce waiting and reduce traffic to the degraded service. That does not mean all requests to the Gateway are blocked: other routes, and even other breakers, can continue operating normally.

## 11. Gateway Fallback vs. Backend Fallback

A service may have its own fallback logic—for example, Orders calls Inventory and then replaces inventory data with a cache. If the Gateway also has a circuit breaker on the Orders route, you must understand both layers of protection:

~~~mermaid
flowchart LR
    Client --> GatewayCB[Gateway breaker: Orders API]
    GatewayCB --> Orders[Orders service]
    Orders --> ServiceCB[Orders breaker: Inventory dependency]
    ServiceCB --> Inventory[Inventory service]
    ServiceCB --> LocalCache[Approved local fallback]
    GatewayCB --> GatewayFallback[Gateway fallback: 503 / safe degraded response]
~~~

- **The breaker at the Gateway** observes **Gateway → Orders** calls and reduces impact on clients, connection pools, and the Gateway when Orders becomes unavailable.
- **The breaker at Orders** observes **Orders → Inventory** calls, has finer-grained business context, and can use an appropriate cache/alternative source.
- If Orders returns **200 with degraded data** due to an internal fallback, the breaker at the Gateway may treat that request as successful. Therefore, **separate metrics/tags for degraded/fallback responses** are needed rather than relying solely on HTTP status.
- A circuit breaker at the Gateway cannot know whether a transaction in Orders already committed to the DB if the response was lost. Never use a fallback to conclude that a write operation completely failed.

**Place breakers according to dependency boundaries.** The Gateway is well suited for protecting the proxy layer and API routes; services are usually better suited for business-aware fallbacks and data consistency control.

## 12. Combining a Circuit Breaker with Timeouts

A breaker works more effectively when every call has an **appropriate time limit**. In Spring Cloud Gateway Server WebFlux, the HTTP client is typically configured through Gateway/Reactor Netty properties:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 3000
            response-timeout: 5s
~~~

The example above illustrates **TCP connect timeout** and **HTTP client response timeout** at the backend call layer. The exact interpretation of `response-timeout` and the unit of `connect-timeout` depend on the version. In older Gateway versions, the prefix may be `spring.cloud.gateway.httpclient`. Do not assume that `response-timeout: 5s` is a total end-to-end deadline from when the client starts sending the request until the body finishes across all traffic types.

### Why Timeouts Help the Circuit Breaker

Suppose Orders normally responds in 150 ms, but when degraded it can send zero bytes for minutes:

~~~text
Without timeout:
Gateway -> Orders -> waits a very long time...
                  -> few completed errors for the breaker to measure
                  -> resources remain tied up

With an appropriate timeout:
Gateway -> Orders -> response deadline expires
                  -> timeout error
                  -> breaker records failure (if policy counts that error type)
                  -> can OPEN when threshold is reached
~~~

**Having a circuit breaker does not mean the Gateway automatically creates a timeout.** Nor should you set timeouts so short that valid requests are cut off, increasing false failures and causing the breaker to open unnecessarily.

### Different Kinds of Timeouts

| Timeout | Which Stage Failure Does It Cap? | Notes |
| --- | --- | --- |
| Pool acquire | Waiting for an available connection in the Reactor Netty pool | Not TCP connect |
| TCP connect | Creating a new socket to the instance | Can fail before the HTTP request is sent |
| TLS handshake | Negotiating TLS with an HTTPS upstream | Certificate/hostname errors cannot be fixed by infinite retries |
| HTTP response | Waiting for a response or data progress per API/version | Not automatically synonymous with a full-request deadline |
| TimeLimiter | Limiting the duration of a publisher/operation when integrated | Requires proper configuration; not every breaker has it by default |
| Client deadline | End-to-end limit enforced by the client | The Gateway does not control all of it |
| Ingress/mesh timeout | Limit enforced by an intermediate proxy | Can return errors before the Gateway or backend |

**Streaming is an important exception:** SSE, WebSocket, NDJSON, and large downloads can stay open for a long time. A response timeout tuned for short JSON APIs can cut off healthy active streams. Separate routes/policies by workload and also test when a stream **stops sending data for a period**.

### Defining Failure for Timeouts

Timeouts emitted by the HTTP client can be turned into exceptions in the pipeline; Resilience4j can typically record them as failures when the exception belongs to the counted group. However, timeouts that occur **before the breaker**, **outside the filter scope**, or are converted by another filter into a response with an uncounted status can prevent the breaker from seeing the error. Verify using real events/metrics.

## 13. Combining Circuit Breakers and Retries Without Causing a Retry Storm

In Gateway Server WebFlux, a route can also declare the **Retry GatewayFilter Factory** to handle transient errors. However, the interaction between Retry and CircuitBreaker must be clearly designed.

~~~mermaid
flowchart TD
    A[Client request] --> R{Retry policy}
    R --> CB[Circuit breaker]
    CB --> L[Load balancer / HTTP upstream]
    L --> X{Outcome}
    X -->|Success| S[Return response]
    X -->|Transient retryable failure| T{Retry budget remaining?}
    T -->|Yes| R
    T -->|No| F[Error / fallback]
    CB -->|OPEN| F
~~~

The diagram shows **one logical arrangement** and does not claim that all filter orders or implementations always match it. The two wrapping orders produce different statistical outcomes:

1. **Retry outside the breaker:** Each retry attempt can pass through the breaker and be recorded as a separate call; the breaker can open faster if many attempts fail.
2. **Breaker outside retry:** The breaker can see the **combined outcome** of a retried operation; the backend may still receive multiple attempts before the operation is considered failed.

Filter ordering is determined by the Gateway via the order of `GatewayFilter`/`GlobalFilter`, which is not always simply the visual position a reader sees in a file. You must measure **how many times the upstream is called**, the breaker state, and metrics when testing the actual configuration.

### Only Retry When Correctness Is Guaranteed

| Request | Can Retry Be Considered? | Conditions |
| --- | --- | --- |
| `GET /catalog/products/42` | Usually yes, with limits | GET has no side effects; requires timeout/deadline |
| `GET /orders/42` | Yes with limits | Avoid exposing stale/wrong-tenant data, limit backend load |
| `PUT /preferences` | Depends on API contract | Ensure business-level idempotency, verify update conditions |
| `POST /orders` | **Not by default** | Requires an idempotency key and business-level exactly-once semantics |
| `POST /payments` | **High risk** | Only use a policy permitted by the payment system, with deduplication |
| Already open WebSocket/SSE | Do not retry like a short request | Requires protocol/application-level reconnect/resume |

Once OPEN, pointless retries can repeatedly trigger `CallNotPermittedException` and increase log/CPU usage even without calling the upstream. Avoid retrying "call not permitted" exceptions, and configure backoff, deadlines, and a limit on total attempts.

### Example Consequence of Retries

Suppose clients send 500 GET/s, errors occur continuously, and each request is allowed up to 3 attempts. Before the breaker opens or before the budget runs out, the backend can receive up to:

~~~text
500 requests/s × 3 attempts = 1,500 upstream attempts/s
~~~

This number only illustrates the **theoretical limit of the policy**, before accounting for breaker OPEN, throttling, concurrency, and timeouts. For an already degraded backend, tripling the load can worsen the outage. Track **client request rate** and **upstream attempt rate** separately.

## 14. Load Balancing: Is the Breaker Tracking a Service or an Instance?

When the route URI is `lb://orders-service`, **ReactiveLoadBalancerClientFilter** picks a specific ServiceInstance and then the routing filter calls its host/port. However, the circuit breaker name in the example is `ordersCircuitBreaker`, which is attached to the route:

~~~text
Route orders-read
  Circuit name = ordersCircuitBreaker
  lb://orders-service
       |-- instance A (healthy)
       |-- instance B (unavailable)
       +-- instance C (healthy)
~~~

With standard declarations, the breaker can **aggregate call outcomes across the route/circuit name**, rather than automatically creating separate breakers for A, B, and C. If B fails frequently, the route's breaker can OPEN, causing **requests that would have chosen healthy A/C** to be blocked as well.

This is not always wrong: a circuit protecting the entire **Orders dependency** at the service level may be intentional. However, when only one instance is broken, you should complement it with **readiness, health filtering, service discovery, load balancing, and connection management** to remove that instance from the list, rather than relying on the breaker alone to block the entire service.

### Choosing an Appropriate Granularity

| Granularity | Strengths | Risks |
| --- | --- | --- |
| One breaker per route/service | Simple, easy to observe and react to the overall dependency | Failures in one operation/instance can affect the entire group |
| One breaker per operation group | Separates read GETs and write POSTs or paths with different SLOs | More configuration and metrics |
| One breaker per upstream instance | Isolates individual instance failures if the implementation truly supports it | High cardinality, scale/registry churn, requires lifecycle management |
| One shared breaker for all services | Minimal initial config | **Not recommended:** one failing service can lock out all other APIs |

Do not put the same `sharedCircuitBreaker` name on every route just for convenience. When routes do not share the same dependency/trust/SLI, sharing a breaker distorts the blast radius and causes **cascading degradation**.

### Multiple Gateway Replicas

Suppose the Gateway runs three replicas G1/G2/G3. Breaker statistics are normally **per process**:

~~~mermaid
flowchart LR
    LB[Ingress] --> G1[Gateway G1: CLOSED]
    LB --> G2[Gateway G2: OPEN]
    LB --> G3[Gateway G3: HALF_OPEN]
    G1 --> Orders[Orders service]
    G2 -. Fallback .-> F[Local response]
    G3 --> Orders
~~~

At the same moment, a client routed through G1 may receive a real response, while a client routed through G2 receives a fallback. Metrics segmented by **gateway instance and route/circuit** are needed to distinguish behavior; do not assume breaker state is synchronized via Redis or service discovery.

## 15. Fallback Responses: Status, Headers, Body, and Security

A circuit breaker is usually an infrastructure mechanism, but **the fallback is the HTTP interface that users see**. A good response must have clear semantics and never accidentally turn into a fake success.

### Response Decision Table

| Scenario | Usually Reasonable Handling | Why |
| --- | --- | --- |
| Orders is down | 503, concise error body, appropriate cache-control | Cannot provide accurate order status |
| Catalog fails but allowed cache exists | Return cached data with stale metadata per contract, or 503 | Only use cache if data age and access permissions are controlled |
| Payment timeout | Return unknown/processing status per contract; avoid claiming payment succeeded | Backend may have processed it before the response was lost |
| Request sends an expired token | 401 from authentication layer, no 200-style fallback | Do not let auth errors open a path for the request |
| User lacks admin permissions | 403, do not call admin backend | Circuit breaker does not replace authorization |
| Client sends invalid data | 400 per validation contract | Do not count as dependency unavailable |
| Gateway is rate-limited | 429 and Retry-After if policy has a sound basis | 429 does not prove upstream failure |

### Once a Response Is Committed, Its Status Cannot Be Changed

For short JSON responses, the breaker can catch errors before the Gateway sends the status/body. But for **SSE, NDJSON, or large downloads**, the Gateway may already have sent HTTP 200 and part of the data:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

<upstream disconnected>
~~~

Once the response is committed, the Gateway **cannot go back, change the status to 503, and start a different JSON body**. You must define reconnect/resume semantics and partial stream handling; do not use a fallback to append a JSON error into the middle of an SSE stream and claim the response is still valid.

### Do Not Let Fallbacks Leak Sensitive Data

A fallback should not:

- Echo `Authorization`, `Cookie`, or query strings containing tokens into responses/logs.
- Send stack traces/exception classes containing internal URIs or credentials back to the client.
- Return cached data belonging to **another user** if the authentication layer lacks sufficient context.
- Forward the original request's token to a fallback service without a valid audience.
- Turn 401/403 into 200 and accidentally allow unauthorized access.

If you need to diagnose exceptions in a fallback, **log safely** with the route ID, a normalized error category, and a controlled trace ID—do not log full headers/bodies. Some Gateway mechanisms can place the exception in an exchange attribute or pass exception details via `FallbackHeaders`; if used, never expose raw exception contents containing URLs, tokens, or sensitive data externally.

## 16. Observing States and Degradation

An HTTP status of 200/503 from the client is **not enough** to know whether the breaker is working. A fallback can return 200 from a cache while the service is still failing; a 503 response can also come from having no ServiceInstance rather than an OPEN breaker.

Signals to monitor:

| Signal | Question |
| --- | --- |
| Circuit state (CLOSED/OPEN/HALF_OPEN) | Is the route/dependency breaker currently rejecting calls? |
| Failure rate and slow-call rate | What are the failure/slow ratios in the current window? |
| Calls permitted / not permitted | How many requests called upstream vs. were rejected by OPEN? |
| Fallback invocations | How many responses were generated from the fallback branch? |
| Upstream HTTP status | Is the backend returning 5xx or 4xx? |
| Connection/timeout/TLS failures | At which hop are connection or response-wait errors happening? |
| Gateway route request rate | Which route is experiencing a traffic spike or impact? |
| Retry attempts | How many upstream attempts does each client request generate? |
| End-to-end latency p95/p99 | Is fail-fast reducing client wait times? |
| Availability and SLO | Are clients actually receiving outcomes matching the committed contract? |

Spring Cloud Gateway, Spring Cloud CircuitBreaker, and Resilience4j can integrate with **Micrometer/Actuator** with appropriate dependencies and configuration. Exact metric names, tags, and event exposure capabilities **depend on the version**; inspect the actual metrics of the running version.

### Hints for Reading the Signs

| Observation | Likely Cause to Investigate |
| --- | --- |
| Failure rate rises, breaker stays CLOSED | `minimumNumberOfCalls` not yet met, threshold config, or errors outside scope |
| Backend returns 500, but failure metric does not increase | Missing appropriate `statusCodes` or status is not translated into a failure |
| OPEN rises, backend attempts drop | Breaker is achieving its load-shedding effect |
| Continuously OPEN even though upstream recovered | HALF_OPEN probes not permitted/failing, mismatched policy, or different instance source |
| Gateway stays slow while breaker is OPEN | Fallback is slow/hanging, another filter is blocking, or pool/ingress causes latency |
| High HTTP 200, but degraded traffic increases | Fallback is returning alternative data; separate metric needed to avoid hiding outages |
| G1 OPEN, G2 CLOSED | Gateway replicas have different breaker metrics/states |
| 503 rises, but breaker state is unchanged | No instance available, HTTP routing failure, or another error handler |

**Avoid high-cardinality metrics** such as raw URL, user ID, token, session ID, or dynamic upstream IP as tags. Route ID, breaker name, and status are generally more useful, provided route/circuit names are bounded. Disable or secure administrative Actuator endpoints; do not allow Internet users to read or manipulate breaker state arbitrarily.

### Treating an Open Breaker as a Significant Event

A useful alert can combine **sustained OPEN breaker state**, rejected call rate, upstream availability, and fallback outcomes. Do not alert solely on every individual `CallNotPermittedException` error log, because while OPEN, each newly rejected request can generate many identical logs even though the mechanism is doing its protective job properly.

## 17. Testing the Circuit Breaker with a Mock Backend

To verify a circuit breaker, you should not just check that application startup says "route loaded." You must simulate upstream outcomes that count as failures and **count the requests that actually reach the backend**.

### Test Environment

Suppose there are three processes:

~~~text
Test client / WebTestClient
          |
          v
Gateway :8080
  GET /api/orders/42
  CircuitBreaker = ordersCircuitBreaker
          |
          +--> Orders stub :9001
          |      Modes: 200 / 503 / delayed / connection reset
          |
          +--> Local fallback
                 GET /internal/fallback/orders
~~~

In a simple lab, replace `uri: lb://orders-service` with `uri: http://localhost:9001` to isolate load balancing, or configure a single ServiceInstance for `orders-service`. **You do not need a registry to understand the state machine**, but you must have an HTTP stub that lets you control failures and count requests.

For easy observation, you can start from `minimumNumberOfCalls: 10`, `failureRateThreshold: 50`, `waitDurationInOpenState: 30s`, and `permittedNumberOfCallsInHalfOpenState: 3` from Section 8. In practice, when OPEN occurs also depends on samples already in the sliding window, concurrent requests, and slow-call policies.

### Testing Basic Scenarios

| Test Case | Stub/Backend | What to Observe |
| --- | --- | --- |
| **A. Normal success** | Returns fast 200 JSON | Client receives 200, breaker CLOSED, requests reach backend |
| **B. A few errors, low sample count** | Returns 503 a few times | Do not assume OPEN before reaching minimum calls |
| **C. Errors reach threshold** | Returns 503 enough times per config | Failure metric increases; breaker can transition to OPEN |
| **D. OPEN rejects calls** | Keep stub in failure mode | Subsequent requests do not increment backend request counter; client receives designed fallback |
| **E. HALF_OPEN probing** | Wait for OPEN wait duration and switch stub to 200 | Only a limited number of calls are permitted to backend; outcome decides CLOSED |
| **F. Backend still fails during probes** | Keep returning 503 | Breaker returns to OPEN if probes fail criteria |
| **G. Valid 404 error** | Returns 404 for nonexistent order | Should not increase failure metric if 404 is not configured as a failure |
| **H. Timeout** | Delay past response deadline | Timeout exception matching policy must be recorded; fallback has valid status |
| **I. Anonymous/insufficient permissions** | No need to call stub | Security 401/403, request never reaches upstream |
| **J. Interrupted streaming** | Send a few events then disconnect | Must not try to change an already committed response into a 503 JSON |

### Using curl in a Lab Environment

~~~bash
# When the stub returns 200:
curl -i 'http://localhost:8080/api/orders/42'

# After switching the stub to return 503:
curl -i 'http://localhost:8080/api/orders/42'
curl -i 'http://localhost:8080/api/orders/42'
curl -i 'http://localhost:8080/api/orders/42'

# Check another route that does not use the Orders breaker:
curl -i 'http://localhost:8080/api/public/products/42'
~~~

The commands above are **operational instructions**, not executed results. Three failing requests are **not enough** to guarantee the breaker will open if `minimumNumberOfCalls` is 10. Use a stub with a request counter and send the configured number of calls in an automated test; avoid typing manually with hard-to-control timing and guessing results.

### WebTestClient to Verify the Fallback Contract

Assuming the Gateway and stub are already running in an integration test, an HTTP assertion can look like this:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class OrdersGatewayFallbackHttpTest {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void returnsSafeFallbackWhenOrdersIsUnavailable() {
        // Test precondition: Orders stub is returning an error handled by the breaker/fallback.
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectHeader().valueEquals("Cache-Control", "no-store")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("ORDERS_TEMPORARILY_UNAVAILABLE");
    }
}
~~~

This is an **assertion example**, not a complete runnable integration test. It requires the Gateway running on port 8080, a stub producing the right failure condition, Spring Test/JUnit dependencies, and the corresponding CircuitBreaker configuration. Depending on serialization/framework behavior, `Cache-Control` may contain additional directives; in that case, adjust the assertion to the contract instead of forcing an unnecessary exact string.

**More important test:** When the breaker is OPEN, record the stub's counter before and after a batch of requests; if no probe is permitted, **the counter must remain unchanged**. A test that only sees JSON 503 without measuring the counter does not prove the breaker short-circuited: the backend could simply be returning 503 on every call.

### How to Test State Transitions Deterministically

There are two complementary layers of testing:

1. **Resilience4j unit tests:** Use a controllable clock/state/circuit configuration to verify state transitions and call permissions without HTTP.
2. **Gateway integration tests:** Use an HTTP stub, response delays, fixed test configuration, controlled request counts, and metrics/state checks; avoid depending on the unpredictable ordering of concurrent requests.

Some libraries allow controlling state in tests to focus on testing the OPEN/HALF_OPEN branches, but **do not use state-forcing commands or management endpoints in production** without operational procedures and authorization. End-to-end tests must still confirm the right outcome when the backend actually fails.

## 18. Common Anti-Patterns and How to Fix Them

| Anti-Pattern | Consequence | Better Approach |
| --- | --- | --- |
| Same breaker name for Catalog, Orders, and Payments | One failing service causes other services to be blocked | Separate breakers by dependency/operation group |
| Counting all HTTP 4xx as failures | Client 400/401/403/404 opens the breaker | Specify exceptions/statuses that reflect upstream degradation |
| Falling back every exception to HTTP 200 | Masks errors, misleading clients | Keep business-accurate status and body, track degraded responses separately |
| Returning uncontrolled cached data for personal Orders | Stale data or wrong user's data | Verify permissions and clear cache policy; prefer 503 when uncertain |
| Using a breaker instead of a timeout | Hanging operations keep resources tied up | Add appropriate connect/response timeouts or TimeLimiter |
| Retrying endlessly after OPEN | Logs/CPU spike while still unable to call backend | Have a retry budget/backoff, exclude call-not-permitted from retries |
| Retrying payment POSTs without idempotency | Transactions can be duplicated | Idempotency key, backend dedupe, dedicated policy |
| Relying on `SetStatus=200` to patch fallback | Status and body become inconsistent | Return a unified response from the handler and contract |
| Treating every 503 as breaker OPEN | Misses no-instance, backend 503, timeouts | Separate route, circuit, load-balancer, and HTTP error metrics |
| Opening the circuit due to one failing instance in a cluster | Blocks healthy instances too | Combine readiness/registry filtering and choose appropriate granularity |
| Exposing sensitive data in a public fallback | Creates an unauthenticated bypass | Secure the handler/entry path and never return secrets |
| Logging raw exceptions/`Authorization` | Leaks JWTs, internal URLs, or sessions | Log normalized metadata and safe trace IDs |
| Using a short response timeout for SSE | Streams get cut off, breaker may open unreasonably | Separate policies for streaming and heartbeat/reconnect |
| Not measuring the upstream request counter | Fails to prove short-circuiting | Use stub/metrics for attempt counts and state |
| Very low thresholds on low traffic | Breaker flaps due to small sample sizes | Set minimum samples/window based on traffic |
| Forced OPEN/RESET exposed on Internet endpoints | Outsiders can disrupt operations | Secure the management plane and audit changes |

### Scenario: 503s Increase, but the Circuit Breaker Does Not Open

At least four causes can occur:

1. 503 is a normal HTTP response and has not been marked as a failure in `statusCodes`.
2. `minimumNumberOfCalls` has not been reached or the window has too few samples.
3. 503 originates from another layer outside the publisher scope observed by the breaker.
4. There are multiple Gateway replicas, each with different statistics.

**How to investigate:** check the route, breaker name, statusCodes, and timeouts; then inspect failure/slow-call metrics, state, request count to the stub/backend, and replica count. Do not "fix" it by lowering thresholds near 0 without knowing the cause.

## 19. Operational Runbook When a Breaker Stays Open

When the Orders circuit breaker transitions to OPEN and stays in that state for a long time, do not simply force the breaker CLOSED. The root cause is usually in the dependency or failure-detection configuration:

1. **Determine the blast radius:** Only `orders-read` or all routes? Is any breaker sharing the same name?
2. **Check the upstream:** Are instances healthy/ready? Is there a DB, DNS, TLS, connection pool, timeout, or deployment issue?
3. **Inspect state and failure rate:** Is it caused by exceptions, configured HTTP 5xx, or the slow-call threshold?
4. **Check retries:** Is a retry storm increasing latency/errors and causing the breaker to repeatedly reopen?
5. **Evaluate the fallback:** Are clients receiving a semantically correct 503, or is cache/stale data causing confusion?
6. **Observe HALF_OPEN:** Are probes reaching healthy instances? Are they failing again due to rate limits, timeouts, or stale service discovery?
7. **Fix the dependency or adjust policy with evidence:** Recovery must be verified via real health/traffic, not by a single state-reset command.
8. **Post-incident follow-up:** Add alerts, runbooks, safe chaos tests, and SLOs for degraded responses.

### Choosing a Fallback Strategy When a Critical Service Fails

Not every API needs a complex fallback body. For Orders, 503 may be the right response. For Catalog, an approved cached snapshot may be helpful. For Payment, you should not guess payment status; you may need to return a `pending` result if the backend has genuine tracking/idempotency mechanisms, or ask the client to query status later through a reliable endpoint.

**Business correctness matters more than the HTTP 200 rate.** A fallback that succeeds at the HTTP level while reporting the wrong transaction state can be worse than returning a clear temporary error.

### Securing the Management Plane

Actuator endpoints, registries, route-definition APIs, and circuit reset/force mechanisms must have strict authentication and authorization. Do not expose admin routes, breaker controls, or endpoints returning environment/secrets on a public `Path=/**`. Changing breaker policies during an incident requires an owner, auditing, and rollback.

## 20. Capstone Lab: Fault-Tolerant Orders API Against Upstream Failures

**Context:** An e-commerce system has Catalog, Orders, and Payment services. Clients access them through Spring Cloud Gateway. The Orders route uses service discovery, JWT, rate limiting, and CircuitBreaker; the backend occasionally returns 503 or times out during rollouts.

### Part A — Define the Protection Contract

1. Choose an **order-reading GET** as the primary scenario, because retry/fallback behavior without side effects is easier to define.
2. Document the route name, service ID, timeouts, statusCodes, failure/slow-call thresholds, minimum samples, and OPEN duration.
3. Decide which errors must **not** be counted: valid application 400, 401, 403, 404 responses.
4. Design a 503 fallback returning concise JSON, exposing no order details or tokens, with an appropriate cache policy.
5. Keep Spring Security handling 401/403 before allowing proxied requests and fallbacks.

### Part B — Configure the Gateway

1. Add the compatible **Spring Cloud CircuitBreaker Reactor Resilience4j** dependency.
2. Declare the `orders-read` route with `CircuitBreaker`, `name: ordersCircuitBreaker`, and `fallbackUri: forward:/internal/fallback/orders`.
3. Configure Resilience4j following the example in Section 8, choosing thresholds suited to the lab.
4. Add the local handler returning 503 and the JSON message from Section 9; protect the internal endpoint from unintended direct calls.
5. Configure appropriate HTTP client timeouts; verify the namespace belongs to the version in use.
6. Enable safe metrics/tracing and confirm the route is loaded and dependencies are present.

### Part C — Simulate the Circuit Lifecycle

| Phase | Action | Evidence to Capture |
| --- | --- | --- |
| 1. Healthy | Stub returns fast 200 | Status 200, breaker CLOSED |
| 2. Degraded | Stub returns 503 matching `statusCodes` | Failure metric rises, fallback matches contract |
| 3. Threshold | Send enough failure samples | Breaker transitions to OPEN per policy |
| 4. Fail fast | Continue sending GETs during OPEN | Backend counter does not increase; fast fallback |
| 5. Recovery | Switch stub back to 200; wait long enough | HALF_OPEN allows a limited number of probes |
| 6. Restore | Probes succeed | Breaker returns to CLOSED; requests reach upstream again |
| 7. No recovery | Keep stub returning errors | Breaker transitions back to OPEN |

Do not simulate failures by attacking a production system; only use a backend stub, a test environment, or a bounded chaos scenario authorized by your organization.

### Part D — Verify Errors Are Not Improperly Masked

1. Return 404 for a nonexistent order; confirm it does not accidentally trigger the 503 fallback when 404 is not in the policy.
2. Send anonymous and insufficiently privileged requests; check that 401/403 never reach the Orders backend.
3. Intentionally trigger a GET timeout in the lab; verify the error is classified at the right layer with a valid response status.
4. Enable GET retries up to a few attempts with appropriate backoff; measure **backend attempts vs. client requests** and compare breaker state.
5. Simulate an error after the backend has streamed part of the response; confirm an already committed HTTP status cannot be changed.
6. If using multiple Gateway replicas, inspect state and metrics per replica, avoiding assuming they are synchronized.
7. Verify the 503 fallback does not log Authorization, Cookie, raw queries, or full exceptions in logs/traces.

### Evaluation Criteria

A lab meets requirements when it demonstrates:

- The breaker **only measures the defined failure group**, not opening due to valid client 400/401/403/404 responses.
- When CLOSED, requests pass through and clients receive normal backend responses.
- When OPEN, requests do not reach the backend on the protected branch; clients receive the contract-compliant error/fallback.
- When HALF_OPEN, a limited number of probes are selected and the state recovers according to results.
- Timeouts, retries, load balancing, and SecurityWebFilterChain **do not break flow correctness**.
- Metrics, logs, and stub counters allow distinguishing **upstream outage, no-instance, breaker rejection, and fallback** without leaking sensitive data.

## 21. Summary

- **A circuit breaker in Spring Cloud Gateway is a protection mechanism at the backend call boundary.** It does not fix service bugs; instead, it temporarily halts calls likely to keep failing, reducing wait times and pressure on dependencies.
- The three primary states are **CLOSED** (permits and measures), **OPEN** (rejects most protected calls), and **HALF_OPEN** (allows limited probes to determine recovery).
- The **Gateway Server WebFlux** CircuitBreaker GatewayFilter integrates **Spring Cloud CircuitBreaker** with an implementation such as **Resilience4j**; route configuration, breaker names, and thresholds must match the version.
- **Not every HTTP status is counted as a failure.** Choose the right exceptions/statusCodes; do not lump valid 400/401/403/404 responses into dependency failures.
- **A circuit breaker does not replace timeouts, retries, load balancing, or bulkheads.** Combine proper ordering, deadlines, and retry budgets; do not retry operations with side effects when idempotency is missing.
- **Fallbacks must preserve accurate HTTP and data semantics**: typically 503 for an unavailable service, or fallback data with a clear contract. Never return a fake 200 success or leak sensitive information.
- A **route/dependency** breaker can aggregate failures across multiple ServiceInstances, and each Gateway replica has its own state. Combine health, readiness, discovery, and metrics to avoid over-blocking.
- **Test OPEN using upstream counters and metrics**, not just by looking at 503 responses. Verify HALF_OPEN/recovery, timeouts, Security 401/403, post-commit streaming errors, and safe tracing/logging.

A resilient API Gateway is one that **knows when to stop calling a dependency**, **reports honest outcomes to clients**, and **recovers verifiably** when the service returns to health.
