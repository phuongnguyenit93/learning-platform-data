# Thread Safety and Synchronization Scope in Resilience4j

A Spring application typically processes multiple requests concurrently across multiple threads. If requests call Inventory or Payment through a single Circuit Breaker, multiple threads simultaneously read the state and update the outcomes of one Resilience4j instance. Therefore, it is important to understand which parts of Resilience4j are designed to be thread-safe, which parts are synchronized, and which responsibilities still belong to application code.

Resilience4j's Circuit Breaker is designed for a single instance to be shared across multiple threads. However, that does not mean the Circuit Breaker locks the entire remote call or automatically limits the number of concurrent in-flight requests. Permitted calls can execute concurrently; outcome recording and state transitions are safely managed by internal mechanisms. If concurrency limiting is needed, the application must combine it with a Bulkhead.

This lesson covers the scope of thread safety and synchronization in Resilience4j within a Spring Cloud CircuitBreaker application, race conditions when multiple requests arrive concurrently, how to write thread-safe services and callbacks, and how to handle context when work moves across threads.

## 1. Why Thread Safety Matters

Suppose a Spring Boot service has an `InventoryGateway` bean created once at application startup. Multiple HTTP requests can concurrently invoke the same `getInventory` method. If the Circuit Breaker is retrieved from the registry by the name `inventory`, those requests typically share the same Circuit Breaker instance.

The execution flow can look like this:

~~~text
HTTP request A ----\
HTTP request B -----+--> InventoryGateway (Spring singleton)
HTTP request C ----/             |
                                  v
                         CircuitBreaker inventory
                                  |
                    +-------------+-------------+
                    |             |             |
                    v             v             v
                 Thread A      Thread B      Thread C
                    |             |             |
                    +-------------+-------------+
                                  |
                                  v
                           Inventory service
~~~

Threads accessing the same instance may concurrently:

- Check whether the Circuit Breaker permits a new call.
- Start calling the dependency.
- Record a success, failure, or slow call outcome.
- Update the sliding window and metrics.
- Emit state transition events.

If these operations were not managed in a synchronized way, counts could be corrupted or state transitions could become inconsistent. Resilience4j provides internal mechanisms to handle these concurrent accesses. Application code must still protect any mutable data it manages itself.

## 2. Circuit Breaker Is Thread-Safe, Not Call-Serializing

Resilience4j's `CircuitBreaker` is designed to be thread-safe. Multiple threads can use the same instance without creating a separate Circuit Breaker per request.

This does not mean all calls are executed sequentially. The Circuit Breaker does not hold a lock across the supplier or function for the duration of the dependency call. When the state permits, multiple threads can be granted permission simultaneously and execute the remote call concurrently.

For example:

~~~java
CircuitBreaker inventoryBreaker =
    circuitBreakerRegistry.circuitBreaker("inventory");

public InventoryResponse getInventory(String sku) {
    return inventoryBreaker.executeSupplier(
        () -> inventoryClient.getInventory(sku)
    );
}
~~~

If 20 requests invoke the method above at the same time while the Circuit Breaker is CLOSED, multiple calls can reach Inventory concurrently. The Circuit Breaker records outcomes and manages state; by default, it does not limit how many calls are in flight.

Distinguish between these concepts:

- **Thread safety:** multiple threads can share an object without corrupting its internal state.
- **Synchronization:** specific shared-data operations are protected so updates remain consistent.
- **Concurrency limit:** the number of calls allowed to run concurrently. This is the responsibility of a Bulkhead or another load-limiting mechanism.
- **Serialization:** forcing all calls to run one after another. Circuit Breaker does not provide this behavior.

If you want at most 10 concurrent calls to Inventory, configure a Bulkhead with the appropriate limit. Do not rely on a Circuit Breaker to enforce concurrency limits.

## 3. Synchronization Scope Inside the Circuit Breaker

A Circuit Breaker must manage at least two groups of state: the current state such as CLOSED, OPEN, or HALF_OPEN, and the statistical data in the sliding window.

Conceptually:

- The state machine must ensure threads observe a consistent state and perform state transitions according to the rules.
- The sliding window must update total calls, failures, and slow calls without losing or duplicating outcomes due to thread contention.
- Metrics must reflect the recorded outcomes.
- Calling the dependency supplier executes outside the state/window synchronization region, so a slow network call does not hold the Circuit Breaker's lock for the entire wait duration.

Resilience4j uses synchronization mechanisms and thread-safe data structures for the state machine and sliding window. Implementation details can vary across versions, so business code should not depend on a specific lock type or internal structure.

The key takeaway from the application perspective is: outcome recording is protected, while business work can still run in parallel. The Circuit Breaker does not turn a service method into a single critical section.

~~~text
Thread A                  CircuitBreaker                 Thread B
   |                            |                           |
   |---- check permission ----->|<----- check permission ---|
   |<--- allowed ---------------|------------- allowed ---->|
   |                            |                           |
   |---- call Inventory         |          call Inventory --|
   |                            |                           |
   |---- record outcome ------->|<-------- record outcome --|
   |                            |                           |
   |                     update window/state                |
~~~

Two calls can run simultaneously. When one outcome causes the Circuit Breaker to transition to OPEN, new calls arriving after the transition are rejected. Calls that already received permission beforehand are not automatically cancelled.

## 4. In-Flight Calls When the Circuit Breaker Transitions to OPEN

A common scenario is that several requests are permitted while in the CLOSED state, and then some of them fail and cause the Circuit Breaker to transition to OPEN.

For example:

1. Requests A, B, and C are granted permission while the Circuit Breaker is CLOSED.
2. All three start calling Inventory.
3. A and B return errors, pushing the failure rate past the threshold.
4. The Circuit Breaker transitions to OPEN.
5. Request D arrives afterward and is rejected.
6. Request C, which started before the circuit opened, can still continue until completion or timeout.

The Circuit Breaker cannot automatically cancel an already-running HTTP request simply because its state moved to OPEN. Stopping an in-flight call is the responsibility of timeouts, cancellation, and the HTTP client. Therefore, Circuit Breaker should be paired with timeouts to bound how long resources remain held.

This also explains why dependency logs may still show a few requests arriving right after the Circuit Breaker opens—those requests were already dispatched before the state transition. Do not conclude that the Circuit Breaker is broken just because an in-flight call finishes after the circuit opens.

## 5. HALF_OPEN and Concurrent Probe Calls

In HALF_OPEN, the Circuit Breaker allows only a configured number of probe calls. The `permittedNumberOfCallsInHalfOpenState` property limits how many calls are permitted during this phase.

For example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

After the OPEN duration elapses, up to three probe calls are allowed according to the configuration. Other requests during this period may be rejected until the Circuit Breaker decides to transition back to CLOSED or return to OPEN.

When multiple threads concurrently request permission in HALF_OPEN, the state machine ensures that no more than the configured number of permits are granted. The application does not need to add its own synchronization to count probes as long as it uses the official Circuit Breaker API.

However, note that the three probes can run concurrently. If the dependency can only tolerate one probe request at a time, reduce `permittedNumberOfCallsInHalfOpenState` to 1 or pair it with an appropriate Bulkhead.

In a multi-replica deployment, each replica typically has its own Circuit Breaker instance and state. If multiple replicas transition to HALF_OPEN at nearly the same time, the total number of probes hitting the dependency can exceed the per-instance configured value. Account for the aggregate probe load across the entire system.

## 6. Sharing Instances in Spring Singleton Beans

Spring typically manages service beans with singleton scope. A single service instance is used by many requests concurrently. This is normal and compatible with Resilience4j as long as the service does not store per-request mutable data in shared fields.

Appropriate example:

~~~java
@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResponse getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getInventory(sku),
            error -> InventoryResponse.unavailable(sku)
        );
    }
}
~~~

Dependencies are injected through the constructor and never change after the bean is created. Each request passes its own SKU via a method parameter. The Circuit Breaker instance is managed by name and does not need to be recreated on every call.

Unsafe example:

~~~java
@Service
public class UnsafeInventoryGateway {

    private String currentSku;

    public InventoryResponse getInventory(String sku) {
        currentSku = sku;
        return inventoryClient.getInventory(currentSku);
    }
}
~~~

If two threads call this at the same time, Thread A might set `currentSku` to `SKU-A`, and Thread B overwrites it to `SKU-B` before A uses the value. The result may query the wrong SKU.

Avoid storing request-specific data in fields of a singleton bean. Pass data through method parameters or use an execution context with an appropriate lifecycle.

## 7. Which Objects Must Be Protected on the Application Side?

Circuit Breaker's thread safety does not automatically extend to objects used by suppliers, fallbacks, or listeners.

| Component | Risk Under Concurrent Thread Access | Design Approach |
| --- | --- | --- |
| CircuitBreaker instance | Multiple threads concurrently read state and record outcomes | Use Resilience4j API; instances are designed to be shared |
| Singleton service | Mutable fields written concurrently by multiple requests | Prefer `final` fields and immutable data |
| HTTP client | Sharing an unsuitable client or mutating config mid-call | Use a framework-managed client configured before serving requests |
| Cache or business map | Race conditions during reads/writes | Use `ConcurrentHashMap`, concurrency-safe caches, or proper locking |
| Custom counters | Lost updates when multiple threads increment concurrently | Use `AtomicLong`, `LongAdder`, or Micrometer `Counter` |
| Fallback callback | Multiple requests execute fallback concurrently | Do not use shared mutable state without synchronization |
| Event listener | Slow callbacks increase latency on event-emitting threads | Keep listeners brief; avoid blocking I/O |
| Request context | `MDC` or `SecurityContext` leaks or mixes across thread switches | Use context propagation and lifecycle-scoped cleanup |

Do not put `synchronized` on an entire service method just to protect a small variable. Doing so can serialize requests and reduce throughput. Choose thread-safe data structures or synchronize only the exact update section that requires protection.

## 8. Thread Safety of Retry and Other Policies

Resilience4j typically manages policy instances via registries so multiple requests can share configuration and metrics. Retry, RateLimiter, and Bulkhead are also designed to be used concurrently through the library's APIs.

However, distinguish between the policy instance and per-execution data:

- Retry configuration can be shared across requests.
- Each Retry execution has its own sequence of attempts and outcomes.
- One retrying request must not share a mutable attempt counter variable with another request.
- Bulkhead manages permits or a thread pool per instance.
- RateLimiter manages permissions by cycle and instance configuration.
- Callbacks supplied by the application must still be thread-safe if multiple requests invoke them concurrently.

Example of why you should not use an instance field to count attempts:

~~~java
@Service
public class UnsafeRetryService {

    private int attempt;

    public InventoryResponse load() {
        attempt = 0;
        // Retry callback increments attempt and calls dependency.
        return performCall();
    }

    private InventoryResponse performCall() {
        attempt++;
        return inventoryClient.getInventory();
    }
}
~~~

Two concurrent requests can overwrite and increment the shared `attempt` variable. If you need the attempt number, store it in a local variable scoped to the execution or use per-execution metadata.

Do not assume every custom object passed into Retry, Circuit Breaker, or Bulkhead is thread-safe simply because Resilience4j's policy objects are thread-safe. Suppliers, fallbacks, and listeners can all be invoked concurrently.

## 9. Circuit Breaker Does Not Replace Bulkhead

A Circuit Breaker controls whether new calls are permitted based on recent statistical outcomes. A Bulkhead controls how many calls can execute concurrently or isolates execution resources dedicated to a dependency.

The two mechanisms solve different problems:

| Question | Mechanism |
| --- | --- |
| The dependency is failing; should we keep calling it? | Circuit Breaker |
| How many calls are allowed to run concurrently? | Bulkhead |
| How long may a single call wait at most? | HTTP client timeout or TimeLimiter |
| Should transient errors be retried? | Retry |

Example using a Semaphore Bulkhead:

~~~java
BulkheadConfig bulkheadConfig = BulkheadConfig.custom()
    .maxConcurrentCalls(10)
    .maxWaitDuration(Duration.ZERO)
    .build();

Bulkhead inventoryBulkhead =
    Bulkhead.of("inventory", bulkheadConfig);

Supplier<InventoryResponse> protectedCall =
    Bulkhead.decorateSupplier(
        inventoryBulkhead,
        () -> inventoryClient.getInventory("SKU-001")
    );

InventoryResponse response = protectedCall.get();
~~~

At most 10 calls are allowed through the bulkhead at the same time. Calls exceeding the limit are rejected immediately because `maxWaitDuration` is zero. A Circuit Breaker can be nested with a Bulkhead to both monitor dependency health and limit concurrency.

When combining them, decide whether `BulkheadFullException` should count as a dependency failure. A full bulkhead may indicate caller overload rather than an unhealthy Inventory service. You can configure the Circuit Breaker to ignore this exception type if that matches your policy and decorator nesting order.

## 10. Synchronization and I/O Calls

A key rule is never to hold an application lock while making a remote service call.

Example to avoid:

~~~java
public synchronized InventoryResponse loadInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

The `synchronized` keyword locks the entire method on the same instance. If Inventory takes 3 seconds to respond, other requests calling this method must wait for the lock, even if they are processing a different SKU. This turns the service into a sequential queue and can create a bottleneck on the caller.

If you need to protect a small update, keep the critical section short:

~~~java
private final Object lock = new Object();
private volatile String lastSuccessfulSku;

public InventoryResponse loadInventory(String sku) {
    InventoryResponse response = inventoryClient.getInventory(sku);

    synchronized (lock) {
        lastSuccessfulSku = sku;
    }

    return response;
}
~~~

The example above only illustrates a small lock scope after the remote call completes. In real applications, if you only store the latest value, you can use `AtomicReference` instead of `synchronized`:

~~~java
private final AtomicReference<String> lastSuccessfulSku =
    new AtomicReference<>();

public void recordSuccess(String sku) {
    lastSuccessfulSku.set(sku);
}
~~~

Choose synchronization mechanisms based on the invariant that needs protection. If an operation must update multiple fields atomically, a short lock or a specialized data structure may be more appropriate. Never hold locks across HTTP I/O, database queries, or long blocking waits.

## 11. Fallbacks and Event Listeners Can Also Run Concurrently

Fallbacks do not run sequentially by default. If multiple requests fail at the same time or the Circuit Breaker is OPEN, multiple fallback invocations can occur nearly simultaneously.

A fallback should:

- Not write to shared mutable fields without synchronization.
- Return an immutable result or construct a fresh response per request.
- Avoid slow I/O if the fallback's purpose is to shed load from the dependency.
- Not call back into the same Circuit-Breaker-protected dependency through an uncontrolled path.
- Log enough context to distinguish fallbacks triggered by errors, timeouts, or Circuit Breaker rejections.

Event listeners should also be kept concise. Example of a listener logging state transitions:

~~~java
inventoryBreaker.getEventPublisher()
    .onStateTransition(event ->
        log.warn(
            "Inventory CircuitBreaker state transition: {}",
            event.getStateTransition()
        )
    );
~~~

Do not run database queries, HTTP calls, or heavy synchronous notifications directly inside a listener. If long-running processing is required, push the event onto a bounded queue or an appropriate asynchronous processor. When offloading events to another thread, consider event ordering, potential event loss, and context propagation.

## 12. MDC, SecurityContext, and ThreadLocal

SLF4J's `MDC` and Spring Security's `SecurityContextHolder` typically rely on `ThreadLocal` in the default servlet model. When a Circuit Breaker call runs on the calling thread, the current context is usually accessible. However, if the application uses a Thread Pool Bulkhead or an executor, work moves to another thread and `ThreadLocal` values are not copied automatically.

Common scenarios:

- Semaphore Bulkhead limits concurrency, but the supplier still runs on the calling thread; `ThreadLocal` context usually remains intact.
- Thread Pool Bulkhead runs the supplier on a dedicated thread pool; `MDC` and `SecurityContext` require context propagation.
- Fallbacks may run in a different execution context depending on how decorators and APIs are composed; do not assume `ThreadLocal` is always present.
- Reactive pipelines may switch threads across operators; Reactor Context and propagation mechanisms must be used appropriately.

For application-managed executors, Spring Security provides wrappers such as `DelegatingSecurityContextExecutor`. For Spring task executors, `ContextPropagatingTaskDecorator` can be used when Micrometer Context Propagation is configured. If Resilience4j manages its own pool, check the integration hooks supported by the version in use.

Do not enable `InheritableThreadLocal` as a blanket workaround for pooled threads. Context can outlive a request's lifecycle or leak across unrelated tasks. Always restore or clear context in a `finally` block.

## 13. Reactive Execution and Thread Safety

In WebFlux applications, never assume a request stays on the same thread. Reactor can switch execution across schedulers and threads. `ThreadLocal` is not a reliable place to store context across a reactive pipeline.

When using a reactive Circuit Breaker, use the corresponding reactive API from Spring Cloud CircuitBreaker or Resilience4j's Reactor integration. Do not call `block()`, `Future.get()`, or `join()` on an event-loop thread to wait for a remote call; doing so can stall the event loop.

Reactor Context is the mechanism for storing subscriber-scoped metadata. Micrometer Context Propagation can bridge with `ThreadLocal` when configured, though you should verify compatibility with your Spring Boot, Reactor, and Micrometer versions. For `SecurityContext`, use Spring Security's reactive integration rather than manually reading `ThreadLocal` inside operators.

Key principles:

- Use `Mono` or `Flux` end to end throughout the reactive processing path.
- Do not hold shared mutable state across subscribers.
- Use Reactor Context for per-subscriber data.
- Use thread-safe operators and avoid sharing unprotected mutable collections.
- Limit concurrency with a Bulkhead or reactive operator concurrency limits where appropriate.
- Avoid blocking I/O on event-loop schedulers.

## 14. Testing Concurrent Behavior

Concurrency tests should verify both outcomes and resource bounds. A simple test can use `CountDownLatch` to make multiple threads start calling at the same time, then inspect the number of concurrent calls reaching the supplier.

Example test harness:

~~~java
CountDownLatch ready = new CountDownLatch(workerCount);
CountDownLatch start = new CountDownLatch(1);
AtomicInteger activeCalls = new AtomicInteger();
AtomicInteger maxObserved = new AtomicInteger();

Runnable task = () -> {
    ready.countDown();

    try {
        start.await();

        circuitBreaker.executeRunnable(() -> {
            int active = activeCalls.incrementAndGet();
            maxObserved.accumulateAndGet(active, Math::max);

            try {
                remoteCallWithControlledDelay();
            } finally {
                activeCalls.decrementAndGet();
            }
        });
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
    }
};
~~~

Once all workers are ready, the test releases the `start` latch so calls run concurrently. With only a CLOSED Circuit Breaker and no Bulkhead, `maxObserved` can be greater than 1. This demonstrates that the Circuit Breaker does not serialize the supplier.

If wrapped with a Semaphore Bulkhead with `maxConcurrentCalls` set to 5, the test can verify that concurrent calls passing through the bulkhead never exceed that limit. Distinguish between rejected calls and calls that actually executed.

Scenarios worth testing:

1. Multiple threads calling the same Circuit Breaker in CLOSED state.
2. Multiple concurrent failures transitioning the Circuit Breaker to OPEN.
3. New requests being rejected after the circuit becomes OPEN.
4. Calls permitted before OPEN still able to complete.
5. HALF_OPEN probe count not exceeding the configured limit.
6. Bulkhead enforcing concurrency limits as configured.
7. Fallbacks and event listeners not misusing shared mutable state.
8. `MDC` and `SecurityContext` being cleaned up after each task.
9. Reactive pipelines not blocking the event loop.
10. Metrics and event listeners not being registered multiple times at application startup.

When testing, use a fake dependency with controllable latency and deterministic error responses. Avoid relying on arbitrary timing, as tests may become flaky across runs.

## 15. Common Pitfalls

| Symptom | Likely Cause | Remedy |
| --- | --- | --- |
| Many requests still hit the dependency concurrently in CLOSED | Circuit Breaker is not a concurrency limiter | Use a Bulkhead if concurrent call limits are required |
| Some requests still complete after state is OPEN | They were granted permission and started before the circuit opened | Use timeouts/cancellation to bound in-flight calls |
| SKU or request data gets mixed up | Singleton service stores request-specific state in a field | Pass data via parameters or per-call context |
| Fallback overwrites another request's data | Callback uses shared mutable state | Construct separate responses and use thread-safe structures |
| Logs lose correlation ID after using a thread pool | `MDC` is not propagated to the new thread | Configure context propagation and cleanup |
| `SecurityContext` is empty inside the supplier | `ThreadLocal` is not transferred to the executor | Use Spring Security context wrappers or compatible propagation |
| Event listener increases latency | Listener performs blocking I/O or heavy work | Keep listeners short and offload with bounded queues |
| Reactive requests hang or lose throughput | Calling `block`/`get`/`join` on the event loop | Use reactive APIs end to end |
| `synchronized` service degrades throughput | Lock spans the entire I/O call | Shrink critical sections or use atomic/concurrent data structures |
| HALF_OPEN creates a large burst | Multiple replicas probe at once or probe count is too high | Limit per-instance probes and account for system-wide load |

## 16. Design Principles

- Share Circuit Breaker instances managed by the registry; do not create a new instance per request.
- Treat Resilience4j's thread safety as protecting internal policy state, not all application data.
- Do not assume a Circuit Breaker serializes suppliers or limits concurrency.
- Use a Bulkhead to limit concurrent calls.
- Use timeouts to bound the duration of in-flight calls.
- Never hold locks during HTTP calls, database queries, or slow I/O.
- Keep Spring singleton services stateless or restricted to immutable/thread-safe data.
- Design fallbacks and event listeners to tolerate concurrent execution.
- Propagate `MDC`, `SecurityContext`, and tracing context when execution switches threads.
- Use Reactor Context and reactive APIs in WebFlux; avoid blocking on the event loop.
- Test race conditions, in-flight calls, HALF_OPEN behavior, and Bulkhead limits under controlled concurrent load.

Resilience4j provides thread-safe policy instances designed for sharing across concurrent requests. A Circuit Breaker synchronizes state and statistics management, yet it neither locks remote calls nor restricts the number of concurrent requests in flight. Application code must keep singleton services thread-safe, manage mutable state properly, and combine Bulkhead and timeouts when resource control is needed. Understanding this boundary enables Spring Cloud CircuitBreaker applications to handle concurrency reliably without mistaking thread safety for load limiting.

## References

- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Security concurrency support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Project Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
