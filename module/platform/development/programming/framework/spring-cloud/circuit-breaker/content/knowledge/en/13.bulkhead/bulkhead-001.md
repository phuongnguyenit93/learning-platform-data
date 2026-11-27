# Resource Isolation So a Failing Dependency Does Not Exhaust Capacity

In a microservices system, a service often calls multiple downstream dependencies to complete a single request. If one dependency responds very slowly, waiting calls can exhaust the calling service's threads, connections, or queues. When shared resources are depleted, features unrelated to that dependency can also stop serving traffic.

Bulkhead is a resource-isolation pattern that limits the blast radius of a failing component. The name comes from watertight bulkheads in a ship's hull: if one compartment floods, the bulkheads keep water from spreading throughout the entire ship. In software, each dependency or workload group is given its own resource budget, such as a maximum number of concurrent calls, a dedicated thread pool, and a bounded queue.

In Spring Cloud CircuitBreaker, Resilience4j provides Bulkhead mechanisms to limit concurrency. This lesson focuses on why isolation is needed, the two implementation approaches—Semaphore Bulkhead and Thread Pool Bulkhead—how to configure them per dependency, and how to combine Bulkhead with Circuit Breaker, timeouts, and fallbacks.

## 1. Why Is a Circuit Breaker Not Enough?

A Circuit Breaker tracks call outcomes and latency. When the failure rate or slow-call rate exceeds a threshold, it can transition to OPEN and reject new calls. This mechanism stops sending requests to a dependency that is already showing signs of ill health.

However, before the Circuit Breaker trips open, many calls may already be waiting in flight. A slow dependency that has not yet accumulated enough samples to open the circuit can still tie up threads and connections. In addition, a single request may call multiple dependencies; an outage in one dependency should not consume all resources meant for the remaining dependencies.

Bulkhead solves a different part of the problem:

- Limits the number of calls executing concurrently against a dependency.
- Can isolate a dedicated thread pool and queue for a group of calls.
- Rejects early once the resource budget is full.
- Preserves processing capacity for other dependencies or features.

For example, Order calls Inventory and Payment. If Inventory is slow, a bulkhead limiting calls to Inventory can prevent inventory requests from exhausting the threads serving Payment. A Circuit Breaker can short-circuit Inventory calls once it detects a high failure rate; a Bulkhead caps resource consumption while the dependency is slow or during a traffic spike.

## 2. How Does a Bulkhead Work?

An application can partition resources across dependencies as follows:

~~~text
                    Order Service
                          |
             +------------+------------+
             |                         |
             v                         v
       Bulkhead Inventory        Bulkhead Payment
       max 10 concurrent         max 8 concurrent
             |                         |
             v                         v
       Inventory Service          Payment Service
~~~

Each bulkhead has its own limit. When Inventory stops responding, at most 10 calls are allowed to consume the Inventory bulkhead's budget. Additional calls beyond the limit are rejected or wait up to the configured duration. The Payment bulkhead still retains its own budget.

A bulkhead does not fix the dependency, nor does it guarantee that requests succeed. It protects the caller's resources by controlling how much work is allowed to enter an execution region.

There are two main strategies in Resilience4j:

| Strategy | Isolation mechanism | Characteristics |
| --- | --- | --- |
| Semaphore Bulkhead | Uses a semaphore to limit concurrent calls on the current calling thread | Lightweight, no separate thread pool; when permits are exhausted, it can reject or wait up to a configured duration |
| Thread Pool Bulkhead | Runs work in a dedicated thread pool and bounded queue | Isolates both execution capacity and queuing; incurs thread management overhead and requires context propagation |

## 3. Semaphore Bulkhead

Semaphore Bulkhead limits concurrent calls using a fixed number of permits. Each call must acquire a permit before executing. Upon completion, the permit is released. If no permit is available, new calls are either rejected immediately or wait for up to the configured duration.

For example, if maxConcurrentCalls is 10, at most 10 Inventory calls are allowed to run concurrently through that bulkhead. The 11th call does not execute until a permit becomes available again.

### 3.1. Configuration in Java

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;

import java.time.Duration;

BulkheadConfig config = BulkheadConfig.custom()
    .maxConcurrentCalls(10)
    .maxWaitDuration(Duration.ZERO)
    .build();

Bulkhead inventoryBulkhead = Bulkhead.of("inventory", config);

InventoryResponse response = inventoryBulkhead.executeSupplier(
    () -> inventoryClient.getInventory("SKU-001")
);
~~~

The configuration above allows at most 10 concurrent calls. Setting maxWaitDuration to 0 means calls do not wait for a permit; when permits are exhausted, calls fail fast. For an API that needs a very brief wait for a slot to be freed, you can set a small maxWaitDuration, but it must fit within the overall request latency budget.

When a permit cannot be acquired, Resilience4j throws BulkheadFullException. The application can catch this exception to return an appropriate response, such as notifying the caller that the service is overloaded or returning a fallback result if business logic permits.

### 3.2. Configuration via application.yml

With Resilience4j Spring Boot integration, bulkheads can be declared by instance name:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0

      payment:
        maxConcurrentCalls: 8
        maxWaitDuration: 20ms
~~~

In this example, Inventory does not wait for a permit once the limit is reached; Payment is allowed to wait up to 20 ms. Values should be chosen based on target response time and the load tolerance of each dependency.

Key properties:

- maxConcurrentCalls: maximum number of concurrent calls.
- maxWaitDuration: maximum time to wait for a permit when none is available.

Semaphore Bulkhead does not create a thread pool. The supplier runs on the calling thread. Therefore, it is well suited when you want to limit concurrency while keeping the existing execution model and avoiding the overhead of creating and managing a separate pool.

## 4. Thread Pool Bulkhead

Thread Pool Bulkhead creates an isolated execution region with a dedicated thread pool and bounded queue. Calls are submitted to the pool instead of running directly on the calling thread. This bounds the number of threads allocated to the dependency and prevents slow calls from consuming all request-handling threads.

For example, an Inventory bulkhead has 4 core threads, at most 8 threads, and a queue of 20 tasks. When all 8 threads are busy, up to 20 subsequent tasks can wait in the queue. When both threads and queue are full, new tasks are rejected.

### 4.1. Configuration in Java

~~~java
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;

import java.time.Duration;
import java.util.concurrent.CompletionStage;

ThreadPoolBulkheadConfig config = ThreadPoolBulkheadConfig.custom()
    .coreThreadPoolSize(4)
    .maxThreadPoolSize(8)
    .queueCapacity(20)
    .keepAliveDuration(Duration.ofSeconds(20))
    .build();

ThreadPoolBulkhead inventoryBulkhead =
    ThreadPoolBulkhead.of("inventory", config);

CompletionStage<InventoryResponse> result =
    inventoryBulkhead.executeSupplier(
        () -> inventoryClient.getInventory("SKU-001")
    );

result.whenComplete((response, error) -> {
    if (error != null) {
        // Log the error or transition to appropriate fallback handling.
        log.warn("Inventory task failed", error);
    }
});
~~~

Thread Pool Bulkhead returns a CompletionStage because work executes asynchronously on the pool. You should not call join() or get() immediately on the HTTP request-handling thread if the goal is to keep that thread non-blocking; doing so turns the asynchronous benefit into a synchronous wait.

Key parameters:

- coreThreadPoolSize: baseline number of threads kept alive.
- maxThreadPoolSize: maximum number of threads.
- queueCapacity: maximum number of tasks that can wait in the queue.
- keepAliveDuration: how long excess idle threads may stay alive when there is no work, depending on pool thread management.

Both the thread pool and the queue must be bounded. An overly large queue can hold too many requests for a long time, increasing latency and memory consumption. Failing fast is usually better than queuing unboundedly behind a slow dependency.

### 4.2. Configuration via application.yml

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

Thread pool bulkhead configuration is independent of semaphore bulkhead configuration. Choose the strategy that fits your application's execution model. Do not assume that configuring both instance groups with the same name automatically creates two chained isolation layers; you must understand which provider Spring Cloud CircuitBreaker is actually using.

## 5. Choosing Semaphore or Thread Pool Bulkhead?

Both strategies limit work, but they use threads differently.

| Criterion | Semaphore Bulkhead | Thread Pool Bulkhead |
| --- | --- | --- |
| Execution thread | Current calling thread | Thread from a dedicated pool |
| Thread isolation | No | Yes |
| Concurrency limit | Yes | Yes, via thread count and queue |
| Dedicated queue | No separate work queue | Has a bounded queue |
| Resource overhead | Lower, fewer components | Higher due to pool and queue management |
| ThreadLocal context | Usually preserved on the same thread | Requires context propagation |
| Return model | Synchronous | Asynchronous via CompletionStage |
| Best suited for | Synchronous calls where you want to cap in-flight requests | Needing a dedicated pool for thread isolation or integrating asynchronous work |

Semaphore is a good fit when the application already has a request-serving thread pool and only needs to cap the number of calls to a dependency. It does not protect the calling thread from being held for a long time by an HTTP request; an HTTP client timeout is still necessary.

Thread Pool Bulkhead is a good fit when you need to decouple a dependency's execution capacity from the request-receiving threads. In return, the application must handle asynchronous results, propagate context, and manage pool lifecycle.

There is no single best strategy for every service. Choose based on latency, concurrency, how the HTTP client executes, and request context preservation requirements.

## 6. Integrating Bulkhead in Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker provides an abstraction for invoking a Circuit Breaker. When using the Resilience4j provider, bulkhead integration can be enabled to limit calls by Circuit Breaker name.

The Spring Cloud CircuitBreaker Resilience4j starter brings the required Bulkhead and TimeLimiter modules onto the classpath. By default, when Resilience4j Bulkhead is present, Spring Cloud CircuitBreaker uses FixedThreadPoolBulkhead. You can select Semaphore Bulkhead as the default with the property:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

Verify this property against the Spring Cloud version you are using. When enabled, calls use a semaphore bulkhead by default instead of a fixed thread pool bulkhead.

A service can continue using CircuitBreakerFactory:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

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

The name inventory is the identifier used to associate the call with the instance configuration. Configure the Bulkhead under that same name in application.yml. When the bulkhead is full, calls can be rejected and the fallback receives the error if the provider routes rejection exceptions through the fallback path. Check the exact behavior for your Spring Cloud CircuitBreaker version and chosen bulkhead type.

Example semaphore configuration for the call above:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true

resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
~~~

If semaphore default is not enabled, a thread pool bulkhead configuration can be used instead:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

The two snippets above illustrate the two options. When deploying, confirm which bulkhead provider is actually active, that the instance name matches the Circuit Breaker name, and that the configuration properties bind properly.

## 7. Sizing Limits Based on Actual Capacity

Do not pick maxConcurrentCalls or queueCapacity by guesswork. A limit that is too low rejects requests even when the dependency still has capacity to serve them. A limit that is too high defeats isolation and can overload the dependency.

You can start with Little's Law to estimate the average number of concurrent calls:

\[
L = \lambda \times W
\]

Where:

- L is the average number of requests in the system.
- λ is the arrival rate of requests, in requests per second.
- W is the average processing time, in seconds.

For example, if Inventory receives 40 requests per second and the average processing time is 0.2 seconds:

\[
L = 40 \times 0.2 = 8
\]

This means an average of about 8 calls are processing concurrently. This is only a baseline reference; when choosing limits you must also account for burst traffic, high-percentile latency, connection pool limits, and Inventory's actual capacity.

A sizing process can include:

1. Measure the dependency's request rate and processing time under normal load.
2. Determine the maximum concurrency the dependency can serve reliably.
3. Choose an initial limit less than or equal to the validated budget.
4. Choose a bounded queue if using a thread pool, based on the latency budget.
5. Apply gradually increasing load and observe rejection rates, latency, and resource usage.
6. Adjust one parameter at a time and re-measure.

For a semaphore, maxWaitDuration should be shorter than the remaining time in the latency budget. If the caller only has 100 ms left before its deadline, the bulkhead should not wait 500 ms for a permit.

For a thread pool, queueCapacity needs to be large enough to absorb short bursts, but not so large that requests wait too long. A queue does not replace processing capacity; if the arrival rate continuously exceeds the completion rate, the queue will still fill up eventually.

## 8. Coordinating Bulkhead, Circuit Breaker, and Timeout

The three mechanisms address three different constraints:

| Mechanism | Question to answer |
| --- | --- |
| Bulkhead | How many calls are allowed to occupy resources at the same time? |
| Circuit Breaker | When a dependency shows signs of failure, should we keep sending calls? |
| Timeout / TimeLimiter | How long is a single call allowed to wait at most? |

For example, Order calls Inventory with the following limits:

- Bulkhead allows at most 10 concurrent calls.
- HTTP client times out after 800 ms.
- Circuit Breaker opens if the failure rate or slow-call rate exceeds the threshold.

When Inventory is slow, timeouts release calls that have exceeded the wait limit. The Bulkhead caps the number of calls consuming resources while waiting. The Circuit Breaker observes failures or slow calls and can short-circuit new calls for a period of time.

Avoid letting BulkheadFullException be counted as a dependency failure if the Circuit Breaker's goal is to assess Inventory's health. A full bulkhead may indicate that the caller has exhausted its own concurrency budget, while Inventory is not necessarily failing. You can configure the Circuit Breaker to ignore this exception type if appropriate for your application's integration and error classification. If you want alerts on local overload, monitor Bulkhead rejection metrics separately.

Timeouts must also be configured sensibly. The HTTP client timeout caps waiting at the network layer. TimeLimiter caps the completion time of an asynchronous task. They can work together, but neither can always cancel work already running on the dependency; check cancellation support in both the HTTP client and the executor.

## 9. Context Propagation When Using Thread Pool Bulkhead

Thread Pool Bulkhead executes the supplier on a separate thread. MDC and SecurityContext typically rely on ThreadLocal, so they are not automatically present in the thread pool.

If logs need a correlation ID, or calls need the authenticated identity, configure appropriate context propagation. You can use Micrometer Context Propagation and Spring integration mechanisms, or pass the required values explicitly as parameters.

For SecurityContext, if the executor is managed by the application, you can use Spring Security wrappers such as DelegatingSecurityContextExecutor. If Resilience4j manages the thread pool, identify the propagation hooks supported by your integration version. Do not assume an executor wrapper automatically wraps the library's internal pool.

Do not use InheritableThreadLocal as a general solution for pools that reuse threads. Context can outlive the request lifecycle and cause identity mix-ups across tasks. Always clear context after a task completes.

Semaphore Bulkhead does not switch threads, so existing ThreadLocals can usually still be read inside the supplier. Even so, ensure filters and middleware properly clean up context after the request.

## 10. Observing Bulkhead

A properly configured Bulkhead needs to be monitored. Useful metrics include:

- Number of calls currently using permits or threads.
- Number of available permits.
- Number of calls rejected because the bulkhead is full.
- Active thread count and queue size.
- Wait time in the queue or waiting for a permit.
- Dependency execution latency.
- Fallback rate caused by bulkhead rejections versus dependency errors.

Resilience4j integrates with Micrometer to export metrics. Spring Boot Actuator can expose the metrics endpoint if the dependency and exposure configuration are enabled. Exact metric names and tags depend on the version, so query the actual metrics list rather than assuming fixed names.

Dashboards should distinguish dependency errors from bulkhead rejections. If the Bulkhead frequently fills up while the Circuit Breaker remains CLOSED, the caller may be receiving traffic beyond its concurrency budget. If dependency error rates rise alongside bulkhead rejections, check the provider's latency and health.

Alerts should be based on trends and operational thresholds, such as sustained increases in rejection rate or a queue that is consistently near full. A few rejections during a brief burst do not necessarily mean the configuration is wrong.

## 11. Hands-On Simulation of a Full Bulkhead

You can experiment using a simulated slow endpoint and a small bulkhead limit:

- Configure maxConcurrentCalls to 2.
- Have the provider take 3 seconds to complete each request.
- Send 5 concurrent requests from the client.
- Observe two requests allowed to run and the excess requests either rejected or waiting according to maxWaitDuration.
- Send requests to another dependency to verify its budget is not consumed by the Inventory bulkhead.

With Thread Pool Bulkhead, you can set coreThreadPoolSize and maxThreadPoolSize to 2, and queueCapacity to 1. When two threads are busy and one task is in the queue, the next task may be rejected. Exact results also depend on request submission timing and how the pool accepts tasks.

During the test, record:

1. Timestamp when each request is sent.
2. Number of requests accepted by the provider.
3. Number of requests rejected at the caller.
4. Response times of successful requests and fallback requests.
5. Concurrency, queue, and rejection metrics.

Then increase the limit from 2 to 4 and repeat the test. Compare rejection rates, latency, and in-flight request counts to see the effect of the configuration. Do not look only at successful request counts; observe both latency and dependency resource usage.

## 12. Common Issues and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Requests rejected even though the dependency is healthy | maxConcurrentCalls too low or burst traffic | Measure concurrency and tune according to the latency budget |
| Calling threads still held for a long time | Semaphore only caps concurrency, not wait time | Configure timeouts on the HTTP client |
| Queue grows continuously | Arrival rate exceeds processing rate or queueCapacity is too large | Reduce queue size, throttle load, and inspect the dependency |
| MDC or SecurityContext is lost | Thread Pool Bulkhead switches to another thread | Configure context propagation or pass context explicitly |
| Circuit Breaker opens due to full bulkhead | BulkheadFullException is counted as a dependency failure | Classify exceptions and consider ignoring the appropriate exception |
| Metrics are missing | Micrometer is not enabled or Actuator endpoint is not exposed | Check dependencies, registry, and metrics endpoint exposure |
| Configuration does not take effect | Instance name mismatch between code and YAML or a different bulkhead type is active | Verify instance name and default bulkhead provider |
| Many requests wait too long | maxWaitDuration or queueCapacity exceeds the latency budget | Reduce wait time and configure a bounded queue |

## 13. Design Principles

- Allocate separate resource budgets for each critical dependency.
- Choose semaphore when you only need to limit concurrency on the calling thread.
- Choose thread pool when thread isolation is required and an asynchronous model is acceptable.
- Bound queues to prevent request buildup and uncontrolled memory consumption.
- Set permit wait times and timeouts within the overall latency budget.
- Distinguish dependency failures from rejections caused by a full bulkhead.
- Verify how Bulkhead combines with Circuit Breaker and fallback in your exact Spring Cloud version.
- Propagate MDC, trace context, and SecurityContext when work moves to a thread pool.
- Monitor concurrency, rejections, queues, and latency to tune settings based on data.
- Test with ramping load and slow-dependency scenarios before deploying to production.

Bulkhead prevents a slow or overloaded dependency from exhausting the calling service's capacity. Semaphore Bulkhead caps the number of calls running on the current thread; Thread Pool Bulkhead additionally isolates dedicated threads and a queue. Combined with Circuit Breaker, timeouts, and fallbacks, a Spring Cloud application can control workload concurrency, wait time, and response behavior when a dependency fails.

## References

- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html)
- [Resilience4j Micrometer metrics](https://resilience4j.readme.io/docs/micrometer)
