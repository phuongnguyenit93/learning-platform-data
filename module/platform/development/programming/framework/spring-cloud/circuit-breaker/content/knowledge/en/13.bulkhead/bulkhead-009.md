# Setting Per-Dependency Limits and Coordinating with the HTTP Connection Pool

Bulkhead limits how many operations may run concurrently so a slow dependency does not exhaust the application's resources. An HTTP connection pool, on the other hand, manages how many network connections can be allocated to requests and how many requests must wait for a connection. Both mechanisms protect outbound calls, yet they govern two different resource types.

In Spring Cloud CircuitBreaker with Resilience4j, you should set Bulkhead limits per dependency and configure HTTP connection pools accordingly. If the Bulkhead permits more requests than the pool has connections to serve, requests will queue up inside the pool. If the pool has more connections than the Bulkhead limit, the Bulkhead acts as the primary admission-control gate. Coordinated configuration caps concurrency, prevents hidden queues, and preserves resources for other dependencies.

## 1. Bulkhead Isolates Concurrency by Dependency

Suppose an aggregation service calls three dependencies: inventory, payment, and product recommendations. The recommendation service may respond slowly during peak hours. If all calls share an unbounded resource pool, requests waiting on recommendations can tie up many threads or connections and affect payment calls.

Bulkhead creates separate limits for each call group. For example:

- Inventory is allowed at most 20 concurrent calls.
- Payment is allowed at most 8 concurrent calls.
- Recommendation is allowed at most 5 concurrent calls.

Once recommendation has used all 5 slots, new requests to recommendation are rejected or wait according to the configured policy. Slots reserved for inventory and payment remain available.

~~~mermaid
flowchart TD
    A[Service calls dependencies] --> B{Group by dependency}
    B --> C[Inventory Bulkhead: max 20]
    B --> D[Payment Bulkhead: max 8]
    B --> E[Recommendation Bulkhead: max 5]
    C --> F[Inventory HTTP pool]
    D --> G[Payment HTTP pool]
    E --> H[Recommendation HTTP pool]
    F --> I[Inventory service]
    G --> J[Payment service]
    H --> K[Recommendation service]
~~~

The key point is that limits are bound to a dependency or a group of operations with similar operational characteristics. Do not create a separate Bulkhead per request, as the number of instances and management overhead would grow without bound.

## 2. Bulkhead and HTTP Connection Pool Control Two Different Limits

Bulkhead controls how many operations are allowed to proceed within the application. An HTTP connection pool controls how many connections the HTTP client can lease to requests targeting a remote host.

| Mechanism | Primary limit | When the limit is reached |
|---|---|---|
| Semaphore Bulkhead | Calls currently holding a permit | Reject immediately or wait up to the max duration |
| Thread-pool Bulkhead | Workers and queue capacity of the pool | Reject when both workers and queue are full |
| HTTP connection pool | Connections available to grant to requests | Requests wait for a connection or are rejected when the pending queue hits its limit |
| Circuit Breaker | Eligibility to keep calling a dependency based on recent outcomes | Transitions to OPEN and rejects new calls during wait duration |

A request can acquire a Bulkhead permit and still have to wait for a connection in the HTTP pool. While waiting, that request occupies a Bulkhead slot without having sent data to the server yet. If the pool frequently runs short on connections, that wait reduces the slots available for new requests.

Conversely, if the pool has many connections while the Bulkhead allows only a few concurrent requests, the pool's maximum connections may remain underutilized. That is not necessarily a flaw: the Bulkhead may be intentionally capping load to match what the dependency can tolerate.

With HTTP/1.1, one connection generally serves one active request at a time. With HTTP/2, a single connection can multiplex multiple concurrent streams; therefore, you cannot always set the permit count equal to the connection count. Account for stream limits, client configuration, and server behavior.

## 3. Setting a Separate Bulkhead for Each Dependency

Resilience4j Semaphore Bulkhead is typically configured under the bulkhead section. Each instance can specify maximum concurrent calls and permit wait duration.

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
      payment:
        maxConcurrentCalls: 8
        maxWaitDuration: 0
      recommendation:
        maxConcurrentCalls: 5
        maxWaitDuration: 50ms
~~~

In this example:

- inventory rejects immediately once 20 calls hold permits.
- payment rejects immediately once 8 concurrent calls are active.
- recommendation allows waiting up to 50 milliseconds for a permit; if none is acquired within that window, the call is rejected.

Waiting for a permit can help absorb a short burst, but it also holds resources longer and raises latency. For requests with tight deadlines, failing fast is usually more predictable. If waiting is allowed, the Bulkhead wait duration must fit within the overall deadline budget.

If configuration reuse is needed, you can define shared configs and have instances reference baseConfig using Resilience4j's configuration mechanism:

~~~yaml
resilience4j:
  bulkhead:
    configs:
      default:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
    instances:
      inventory:
        baseConfig: default
        maxConcurrentCalls: 20
      payment:
        baseConfig: default
        maxConcurrentCalls: 8
      recommendation:
        baseConfig: default
        maxConcurrentCalls: 5
~~~

The IDs inventory, payment, and recommendation must match the IDs used in code or the Spring Cloud CircuitBreaker adapter. Verify your starter version and active Bulkhead integration to confirm instance configurations are applied properly.

## 4. Separating HTTP Connection Pools by Dependency

With WebClient and Reactor Netty, you can create a separate ConnectionProvider per dependency. Separating providers lets you set independent connection limits and pending queues.

Example creating a pool for inventory:

~~~java
import java.time.Duration;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class InventoryHttpConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryConnectionProvider() {
        return ConnectionProvider.builder("inventory-pool")
                .maxConnections(20)
                .pendingAcquireMaxCount(10)
                .pendingAcquireTimeout(Duration.ofMillis(100))
                .maxIdleTime(Duration.ofSeconds(30))
                .build();
    }

    @Bean
    WebClient inventoryWebClient(
            ConnectionProvider inventoryConnectionProvider) {
        HttpClient httpClient = HttpClient
                .create(inventoryConnectionProvider)
                .responseTimeout(Duration.ofSeconds(2));

        return WebClient.builder()
                .baseUrl("http://inventory-service")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

Properties in the example:

- maxConnections caps the number of connections allocated in the pool according to the provider's implementation.
- pendingAcquireMaxCount caps the number of requests allowed to wait for a connection.
- pendingAcquireTimeout caps how long a request waits to acquire a connection.
- maxIdleTime caps how long idle connections are retained before eviction under pool policy.
- responseTimeout caps how long to wait for a response under Reactor Netty's policy.

This example uses the Reactor Netty API; verify against the version managed by Spring Boot. ConnectionProvider is a lifecycle-managed resource and must be disposed on application shutdown. In Spring, manage it as a bean with an appropriate destroyMethod.

Create separate providers for payment and recommendation with distinct names, maxConnections, and pending queues. Do not share a single custom pool across all dependencies if the goal is to isolate connection capacity among them.

Note: connection pools typically pool connections per remote host and provider configuration. Having a dedicated provider does not mean every request in the application automatically uses it; the dependency's WebClient must be constructed with the matching HttpClient and ReactorClientHttpConnector.

## 5. Aligning Permit Counts and Connection Counts

With HTTP/1.1, if each call needs a dedicated connection and there is no multiplexing, you can start by setting Bulkhead concurrency close to the number of connections available for the dependency. Example:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 18
        maxWaitDuration: 0
~~~

~~~java
ConnectionProvider inventoryPool = ConnectionProvider.builder("inventory-pool")
        .maxConnections(20)
        .pendingAcquireMaxCount(5)
        .pendingAcquireTimeout(Duration.ofMillis(100))
        .build();
~~~

The Bulkhead permits 18 concurrent calls while the pool allows up to 20 connections. The small margin accommodates other minor operations sharing the pool or brief fluctuations in connection leasing. If the WebClient is dedicated solely to calls protected by this Bulkhead, the two values can be tuned even closer together.

There is no fixed formula that applies to every system. Account for:

- HTTP/1.1 versus HTTP/2.
- Whether a request holds a connection for the entire duration of reading the response body.
- Whether multiple routes or endpoints share the same pool.
- Whether requests bypassing the Bulkhead also use the same provider.
- Whether retries generate additional requests within the same time window.
- Response times and latency variance.
- Connection limits at proxies, load balancers, and the server.

If the Bulkhead is 30 while the pool only has 10 connections, up to 20 calls can wait for a connection while still holding permits. When latency rises, Bulkhead slots remain occupied for longer and new requests can be rejected even though the server has not actually received 30 requests.

If the Bulkhead is 10 while the pool has 100 connections, at most 10 calls pass through the Bulkhead concurrently. The remaining connections can serve other flows if the provider is shared, or simply remain unused.

## 6. Avoiding Hidden Queues in the Connection Pool

A queue inside the HTTP pool can make the system appear to be processing requests normally even though those requests have not yet been sent to the server. Those requests are already occupying Bulkhead permits and burning through their deadline budget.

Example:

- Bulkhead allows 40 concurrent calls.
- HTTP pool only has 10 connections.
- pendingAcquireMaxCount allows 100 waiting requests.
- The dependency begins responding slowly.

There may be 10 requests actively using connections and 30 requests holding permits while waiting for a connection. As earlier requests drag on, subsequent requests pile up. From the caller's perspective, latency climbs; from the server's perspective, active requests can be far lower than the number of calls consuming client-side resources.

To avoid this situation:

1. Set maxConcurrentCalls in line with the dependency's processing capacity and connection capacity.
2. Bound pendingAcquireMaxCount instead of leaving the pending queue unbounded.
3. Set pendingAcquireTimeout shorter than the remaining overall deadline.
4. Monitor requests waiting for connections and acquire wait times.
5. Fail fast when load exceeds processable capacity.
6. Do not retry immediately on pool-exhaustion errors; retries only grow the queue further.

A small queue can absorb brief jitter. A large queue does not increase server throughput; it only keeps more requests sitting in a waiting state.

## 7. Distinguishing Semaphore Bulkhead and Thread-pool Bulkhead

Resilience4j offers two common ways to cap load:

| Characteristic | Semaphore Bulkhead | Thread-pool Bulkhead |
|---|---|---|
| Limiting mechanism | Concurrent permit count | Worker threads and queue |
| Creates separate threads | No | Yes |
| Suited for | Reactive flows or tasks that do not need thread isolation | Blocking tasks requiring thread isolation |
| Queue | No dedicated work queue; can wait for a permit within maxWaitDuration | Has a bounded queue |
| When full | Reject or wait for a permit | Reject when both workers and queue are full |

With WebClient and WebFlux, Semaphore Bulkhead is usually a better fit because you do not need to offload a publisher onto another thread pool merely to limit concurrency. Cancellation signals and publisher lifecycle remain managed within the reactive chain.

Thread-pool Bulkhead is useful when isolating a blocking library or an operation that can occupy a thread for a long time. In that case, bound coreThreadPoolSize, maxThreadPoolSize, and queueCapacity. The queue must be bounded to prevent work accumulation when the dependency slows down.

Example thread-pool Bulkhead configuration:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      legacy-inventory:
        coreThreadPoolSize: 5
        maxThreadPoolSize: 8
        queueCapacity: 10
        keepAliveDuration: 20ms
~~~

Thread-pool Bulkhead and the HTTP connection pool remain two independent layers. A thread pool may have 8 workers while the HTTP pool only has 4 connections; workers will then wait for connections. Conversely, the HTTP pool can be wider than the thread pool. Bound both according to real capacity and avoid building large queues at both layers.

## 8. Applying Bulkhead Explicitly to Reactive WebClient Calls

You can use Resilience4j Reactor's BulkheadOperator to cap publisher concurrency. The example below uses a Semaphore Bulkhead for inventory:

~~~java
import java.time.Duration;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.reactor.bulkhead.operator.BulkheadOperator;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class InventoryClient {

    private final WebClient webClient;
    private final Bulkhead inventoryBulkhead;
    private final ReactiveCircuitBreaker inventoryCircuitBreaker;

    public InventoryClient(
            WebClient webClient,
            ReactiveCircuitBreaker inventoryCircuitBreaker) {
        this.webClient = webClient;
        this.inventoryCircuitBreaker = inventoryCircuitBreaker;

        BulkheadConfig config = BulkheadConfig.custom()
                .maxConcurrentCalls(18)
                .maxWaitDuration(Duration.ZERO)
                .build();

        this.inventoryBulkhead = Bulkhead.of("inventory", config);
    }

    public Mono<Inventory> find(String sku) {
        Mono<Inventory> remoteCall = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        Mono<Inventory> circuitProtected = inventoryCircuitBreaker.run(
                remoteCall,
                error -> Mono.just(Inventory.unavailable(sku))
        );

        return circuitProtected.transformDeferred(
                BulkheadOperator.of(inventoryBulkhead)
        );
    }
}
~~~

In this composition, the Bulkhead wraps the publisher protected by the Circuit Breaker. A permit is acquired before the subscription enters the Circuit Breaker call. If permits are exhausted, the call is rejected at the Bulkhead layer and never reaches the Circuit Breaker. Consequently, rejections caused by local concurrency limits are not mistakenly counted as dependency health failures.

If decorator order changes and the Circuit Breaker observes BulkheadFullException, configure appropriate exception classification or adjust the order so failure rates are not skewed. A Bulkhead rejection signals that the system has hit its admission-control limit; it does not necessarily prove the remote service is failing.

This example illustrates applying Bulkhead directly using Resilience4j Reactor. If the application already uses Spring Cloud CircuitBreaker to apply Bulkhead automatically by ID, avoid wrapping a second Bulkhead unintentionally. Inspect adapter settings and verify active permit counts before combining multiple layers.

## 9. Estimating Initial Concurrency from Traffic and Latency

You can estimate average concurrent calls using Little's Law:

\[
L = \lambda \times W
\]

Where:

- L is the average number of requests in the system.
- λ is the average request arrival rate, in requests per second.
- W is the average time a request spends in the system, in seconds.

For example, inventory receives 40 requests per second and average processing time is 250 milliseconds:

\[
L = 40 \times 0.25 = 10
\]

This means an average of about 10 calls are active concurrently. This is a starting point for evaluating the Bulkhead, not a mandatory maxConcurrentCalls value. Add headroom suited to latency variance and verify the concurrency level the dependency can withstand.

If latency rises from 250 milliseconds to 1 second while request rate remains 40 requests per second:

\[
L = 40 \times 1 = 40
\]

Average concurrent requests rise to 40. If the Bulkhead sets a limit of 20, the system will reject a portion of requests instead of letting concurrency grow without bound. This is precisely how it protects resources and caps pressure on the dependency.

When calculating, use realistic percentile latencies such as p95 or p99 to understand high-load periods rather than relying solely on averages. Account for long-running requests, large response bodies, and retry counts.

## 10. Coordinating with Circuit Breaker and TimeLimiter

Bulkhead, Circuit Breaker, and TimeLimiter complement one another:

- Bulkhead caps the number of calls allowed to run concurrently.
- Circuit Breaker blocks new calls when failure or slow-call rates indicate dependency degradation.
- TimeLimiter caps the wait time for an operation.

Example configuration sharing the same ID:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s

  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 18
        maxWaitDuration: 0

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

The ID inventory associates all policies with the same dependency. However, whether the Spring Cloud CircuitBreaker adapter automatically applies all three modules and which call styles it supports depend on the version, starter, and configuration. Verify the actual integration behavior; do not assume every reactive or synchronous API behaves identically.

Timeouts should be less than or equal to the deadline the caller can tolerate. Bulkhead should cap concurrency before requests pile up in the HTTP pool. Circuit Breaker should observe dependency failures, while distinguishing remote errors from local admission-control rejections.

## 11. Monitoring Both Bulkhead and the Connection Pool

To verify whether configuration layers work together properly, observe metrics from both layers.

For Bulkhead, monitor:

- Permits currently in use.
- Calls rejected due to no available permits.
- Calls waiting for a permit, if waiting is enabled.
- Permit hold duration.
- Rejection rate per dependency.

For the HTTP connection pool, monitor:

- Active and idle connections.
- Maximum connection count.
- Requests waiting to acquire a connection.
- Connection acquire wait duration.
- Acquire timeouts or acquire rejections.
- Connections closed or recreated.

Clearly distinguish the different types of rejections:

| Situation | Possible cause | Resolution |
|---|---|---|
| BulkheadFullException | Concurrency permits exhausted | Review limits, latency, and load to the dependency |
| PoolAcquireTimeoutException | Failed to acquire a connection within timeout | Check maxConnections, pending queue, and connection hold time |
| CircuitBreaker OPEN | Dependency failure or slow-call rate exceeded threshold | Investigate remote errors and Circuit Breaker policy |
| TimeLimiter timeout | Operation exceeded deadline | Review per-layer timeouts and cancellation |

If you only track total timeout counts, it is hard to tell whether requests slowed down because of the Bulkhead, connection pool, network, or server. Correlation IDs and per-dependency metrics help pinpoint the exact bottleneck.

## 12. Common Configuration Mistakes

- **Bulkhead much larger than the HTTP pool**: many calls hold permits while queuing for a connection.
- **Shared HTTP pool across unrelated dependencies**: one dependency can consume most connections and starve other flows.
- **Unbounded pending acquire queue**: requests accumulate, latency climbs, and deadlines expire before requests are even sent.
- **Setting maxConnections too low**: the pool becomes a bottleneck even while the dependency still has capacity.
- **Setting Bulkhead too high**: the limit no longer protects the dependency when latency rises.
- **Confusing Thread-pool Bulkhead with the connection pool**: the thread pool manages workers; the connection pool manages network connections.
- **Using Thread-pool Bulkhead unnecessarily for reactive publishers**: thread switching can add overhead and complicate cancellation.
- **Letting Circuit Breaker count Bulkhead rejections as remote errors**: failure rate can climb even while the dependency is healthy.
- **Retrying when the pool or Bulkhead is already full**: new requests amplify pressure.
- **Failing to dispose ConnectionProvider**: network resources can outlive the managing component's lifecycle.
- **Checking configuration without observing metrics**: static settings do not reflect real behavior under load.

## 13. Per-Dependency Implementation Workflow

When protecting calls to multiple dependencies in Spring Cloud CircuitBreaker, follow this sequence:

1. List each dependency along with its SLA, traffic volume, and p95/p99 latency.
2. Determine an initial concurrency limit based on dependency capacity and caller resource budgets.
3. Create a dedicated Bulkhead per dependency or group of operations with matching characteristics.
4. Create an appropriate WebClient and ConnectionProvider; bound maxConnections, pendingAcquireMaxCount, and pendingAcquireTimeout.
5. Align maxConcurrentCalls with pool capacity, HTTP protocol, and other flows sharing the pool.
6. Configure HTTP client timeouts and overall deadlines so requests never wait indefinitely.
7. Combine with Circuit Breaker to stop new calls when a dependency degrades; separate remote errors from local rejections.
8. Monitor permits, active connections, pending acquires, latency, and rejection counts per dependency.
9. Load-test scenarios where one dependency slows down or loses connectivity; verify other dependencies retain their resources.
10. Tune limits based on production metrics and re-verify whenever changing HTTP/1.1, HTTP/2, or connection pool settings.

Bulkhead and the HTTP connection pool establish two complementary layers of limits. Bulkhead controls how many concurrent calls are allowed to proceed; the connection pool controls connection leasing and how many requests wait for a connection. By isolating limits per dependency, keeping queues bounded, and monitoring both layers, an application can isolate failures more effectively, prevent request buildup, and preserve resources for healthy dependencies.
