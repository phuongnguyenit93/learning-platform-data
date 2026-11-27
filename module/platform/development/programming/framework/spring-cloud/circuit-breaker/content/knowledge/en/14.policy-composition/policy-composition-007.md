# Ordering Rate Limiter, Bulkhead, TimeLimiter, and Circuit Breaker

Rate Limiter, Bulkhead, TimeLimiter, and Circuit Breaker all protect an application when load spikes or a dependent service fails, yet each mechanism controls a different limit. When combining them, the wrapping order around the call determines which mechanism receives the request first, which wait time counts toward the timeout, and which error types are recorded by Circuit Breaker.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, the goal is to prevent cascading failures when a dependent service is slow or unavailable. A common composition puts Circuit Breaker first to check state, Rate Limiter to control rate, TimeLimiter to set a deadline for the full task submitted to Bulkhead, and then ThreadPoolBulkhead to limit running and queued tasks before calling the dependent service. This is a reference order; adjust it according to your system's timing goals and error classification.

## 1. Each Policy Protects a Different Limit

| Mechanism | Limit controlled | Primary question |
| --- | --- | --- |
| Rate Limiter | Call acceptance rate over a time window | Are we allowed to send another request right now? |
| Bulkhead | Concurrent calls and queued tasks | Is execution capacity or a queue slot still available? |
| TimeLimiter | Maximum time waiting for an asynchronous task | When should waiting stop because the time budget is spent? |
| Circuit Breaker | Health status of the dependent service | Should we keep calling a failing or slow dependency? |

For example, Rate Limiter restricts the Inventory service to at most 30 calls per second. Bulkhead limits how many stock-lookup tasks are running and queued. TimeLimiter limits the wait duration per task. Circuit Breaker tracks failure rate and slow-call rate to open the circuit when the Inventory service degrades.

No single mechanism fully replaces another. Rate Limiter does not cap concurrent running tasks if processing takes a long time; Bulkhead does not detect a dependency continuously returning errors; TimeLimiter does not throttle request rate; Circuit Breaker does not cap total tasks waiting in a queue.

## 2. Reference Order for a Call

For an asynchronous call using ThreadPoolBulkhead, a commonly useful order is:

1. **Circuit Breaker** checks its state. If OPEN, reject fast without taking a pool or queue slot.
2. **Rate Limiter** checks the request budget. If exceeded, reject or wait within the configured interval.
3. **TimeLimiter** starts the time budget for the task, covering both queue wait time and execution time.
4. **ThreadPoolBulkhead** bounds threads and queue depth, then executes the call to the dependent service.
5. Results or exceptions propagate back outward; Circuit Breaker records the outcome per its exception policy and sliding window.

Flow diagram along the request path:

~~~mermaid
flowchart TD
    A[Request arrives] --> B[Circuit Breaker]
    B -->|OPEN| X[Fast reject]
    B -->|CLOSED or HALF_OPEN| C[Rate Limiter]
    C -->|Quota exhausted| Y[Reject or bounded wait]
    C -->|Permitted| D[TimeLimiter starts deadline]
    D --> E[ThreadPoolBulkhead]
    E -->|Pool and queue full| Z[Reject due to overload]
    E -->|Slot available| F[Call dependent service]
    F --> G[Result or error]
    G --> H[Circuit Breaker records outcome]
~~~

In this arrangement, Circuit Breaker is on the outside so an OPEN circuit rejects requests before they consume Rate Limiter quota or occupy Bulkhead slots. Rate Limiter sits before Bulkhead so rate-exceeding requests are shed before touching thread pool resources. TimeLimiter wraps task submission into ThreadPoolBulkhead so queue wait time also falls within the request's budget.

This order is not a rigid rule for every application. If Rate Limiter is placed outside Circuit Breaker, every request still consumes quota even when the circuit is OPEN. That can make sense if the quota governs incoming API traffic, but usually makes less sense if the quota is only meant to regulate requests actually sent to the dependent service.

## 3. Why Is Circuit Breaker Often Placed Before Resource Limits?

When Circuit Breaker is OPEN, it already has evidence that the dependency is failing its health thresholds. New requests should be rejected immediately. If Bulkhead is invoked before Circuit Breaker, a request could occupy a slot or enter a queue before discovering that the circuit is OPEN.

Placing Circuit Breaker on the outermost layer helps:

- Reject early when the dependency is protected by the OPEN state.
- Avoid consuming Rate Limiter quota for requests guaranteed not to reach the dependency.
- Avoid occupying Bulkhead threads or queue positions for calls that Circuit Breaker will block.
- Reduce response time for rejected requests.

However, an outer Circuit Breaker will see exceptions thrown by inner policies. For example, Rate Limiter can throw `RequestNotPermitted`, and Bulkhead can throw `BulkheadFullException`. These are rejections caused by local limits, not necessarily dependent service failures. Exclude these exceptions from failure rate calculations or arrange policies so they are not counted as dependency failures.

## 4. Rate Limiter Placed Before Bulkhead

Rate Limiter caps the number of calls in a time window. Resilience4j commonly uses these properties:

| Property | Meaning |
| --- | --- |
| `limitForPeriod` | Number of call permits granted per cycle |
| `limitRefreshPeriod` | Duration of the permit refresh cycle |
| `timeoutDuration` | Maximum time to wait for a call permit if none is available |

Example limiting to 30 calls per second and rejecting immediately when quota is exhausted:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      inventory:
        limitForPeriod: 30
        limitRefreshPeriod: 1s
        timeoutDuration: 0
~~~

Placing Rate Limiter before Bulkhead filters out over-quota requests before they occupy threads or queue slots. If Rate Limiter is configured to wait for permits, that wait time also consumes the overall response budget. Keep `timeoutDuration` aligned with the request deadline; for latency-sensitive APIs, immediate rejection is usually more predictable than waiting indefinitely.

Rate Limiter does not guarantee a cap on active running tasks. If each call takes 10 seconds, even a rate of 30 requests/second can accumulate hundreds of concurrent tasks. That is why Bulkhead is still needed.

## 5. Bulkhead Limits Concurrency and Queueing

There are two common Bulkhead types in Resilience4j:

| Type | How it limits | When appropriate |
| --- | --- | --- |
| SemaphoreBulkhead | Limits concurrent calls using a semaphore | Synchronous calls or limiting concurrency without switching to a separate thread pool |
| ThreadPoolBulkhead | Uses a dedicated thread pool, max threads, and a bounded queue | Isolating asynchronous or blocking tasks from other processing threads |

ThreadPoolBulkhead example:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

The pool can run up to 8 tasks and hold up to 16 queued tasks. When both limits are full, new tasks are rejected. A bounded queue keeps waiting requests from growing unchecked, while the thread cap keeps one dependency from exhausting the application's execution capacity.

Rate Limiter and Bulkhead solve two different quantities. Rate Limiter limits intake rate over time; Bulkhead limits concurrent and queued tasks. You may need both if a dependent service enforces both a requests-per-second limit and a concurrent connection or task limit.

## 6. TimeLimiter Wraps the Task to Include Queue Wait Time

TimeLimiter bounds the wait time for an asynchronous operation. With Resilience4j, it typically works with `Future` or `CompletionStage`; with WebFlux, Reactor timeouts or reactive-compatible mechanisms can be used.

Example:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

If TimeLimiter starts before the task is submitted to ThreadPoolBulkhead, the deadline includes both queue wait time and the Inventory service call time. This fits when the application wants to bound total elapsed time from receiving the request to obtaining a result.

If TimeLimiter starts only inside the worker after the task leaves the queue, it bounds only execution time and not wait time. A request could time out on the client side while still sitting in the queue. Therefore, explicitly choose whether the deadline measures end-to-end duration or solely dependency call duration.

TimeLimiter does not guarantee stopping every running operation. `cancelRunningFuture` can request Future cancellation, but the underlying HTTP client or task must support cancellation/interruption to actually release resources. Configure matching HTTP client timeouts and verify cancellation behavior in a realistic environment.

For synchronous calls that do not return a `Future` or `CompletionStage`, TimeLimiter does not automatically turn them into async operations. You can rely on HTTP client timeouts or dispatch the task onto a bounded executor and manage the deadline explicitly.

## 7. Circuit Breaker Records Timeouts and Dependency Failures

Circuit Breaker should record outcomes reflecting the health of the dependent service:

- HTTP 5xx, connection errors, and dependency errors mapped to exceptions.
- Dependency call timeouts.
- Calls completing slower than `slowCallDurationThreshold`.

Conversely, rejections caused by local limits should usually not raise the dependency's failure rate:

| Exception or outcome | Source | Recommended handling in Circuit Breaker |
| --- | --- | --- |
| `RequestNotPermitted` | Rate Limiter quota exhausted | Ignore in failure rate; track rate-limited rejections separately |
| `BulkheadFullException` | Pool and queue are full | Ignore in failure rate; monitor local overload state |
| `TimeoutException` | TimeLimiter wait expired | Record as dependency failure if timeout represents an accepted call |
| HTTP 5xx or connection error | Dependent service | Record as failure per exception policy |
| `CallNotPermittedException` | Circuit Breaker itself is OPEN | Request was blocked; not a new call to the dependency |
| Business error such as resource not found | Business outcome | Ignore if it does not reflect infrastructure health |

Local exceptions can be declared in `ignoreExceptions`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        ignoreExceptions:
          - io.github.resilience4j.ratelimiter.RequestNotPermitted
          - io.github.resilience4j.bulkhead.BulkheadFullException
~~~

When using `recordExceptions`, review every exception type that should be counted to avoid accidentally missing dependency errors. Ignored exceptions do not raise the failure rate. However, ignoring them in Circuit Breaker does not mean ignoring them at the API layer: the application still needs to return an appropriate overload code and separately monitor Rate Limiter or Bulkhead rejections.

Set `slowCallDurationThreshold` lower than or equal to the applicable deadline if you want to detect slow calls before TimeLimiter terminates them. If a timeout occurs before the slow-call threshold, Circuit Breaker can still record the timeout error without necessarily counting that call as a slow call.

## 8. Combined Configuration Example

A consolidated configuration can declare each policy under its own prefix:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        ignoreExceptions:
          - io.github.resilience4j.ratelimiter.RequestNotPermitted
          - io.github.resilience4j.bulkhead.BulkheadFullException
  ratelimiter:
    instances:
      inventory:
        limitForPeriod: 30
        limitRefreshPeriod: 1s
        timeoutDuration: 0
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

In this configuration:

- Circuit Breaker monitors failure rate and slow-call rate.
- Rate Limiter grants up to 30 call permits per second and rejects immediately when quota is exhausted.
- TimeLimiter sets a 2-second deadline for the asynchronous task.
- ThreadPoolBulkhead limits execution to at most 8 running tasks and 16 queued tasks.
- Circuit Breaker ignores rejections from Rate Limiter and Bulkhead so local overload is not confused with Inventory service failure.

The values are only examples. Tune them according to dependent service capacity, API time budgets, actual traffic, and caller application resources.

## 9. Illustrating the Order with CompletionStage

With Resilience4j, an asynchronous operation can be wrapped with decorators. The example below illustrates the execution order: Circuit Breaker on the outside, followed by Rate Limiter, TimeLimiter, ThreadPoolBulkhead, and finally the HTTP call.

~~~java
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.timelimiter.TimeLimiter;

import java.util.concurrent.CompletionStage;
import java.util.concurrent.ScheduledExecutorService;
import java.util.function.Supplier;

public CompletionStage<Inventory> getInventory(String sku) {
    Supplier<CompletionStage<Inventory>> bulkheaded =
            () -> threadPoolBulkhead.executeSupplier(
                    () -> inventoryClient.fetch(sku));

    Supplier<CompletionStage<Inventory>> timed =
            TimeLimiter.decorateCompletionStage(
                    timeLimiter,
                    scheduler,
                    bulkheaded);

    Supplier<CompletionStage<Inventory>> rateLimited =
            RateLimiter.decorateCompletionStage(
                    rateLimiter,
                    timed);

    Supplier<CompletionStage<Inventory>> protectedCall =
            CircuitBreaker.decorateCompletionStage(
                    circuitBreaker,
                    rateLimited);

    return protectedCall.get();
}
~~~

`threadPoolBulkhead`, `timeLimiter`, `scheduler`, `rateLimiter`, `circuitBreaker`, and `inventoryClient` are created or injected once from appropriate configuration/registries; do not create a new registry or executor per request. The snippet focuses on demonstrating decorator nesting. Check API overloads for the exact Resilience4j version used by your project.

Reading from outside in, the request goes through Circuit Breaker first. If the circuit is OPEN, the rest does not run. If permitted, Rate Limiter grants quota. TimeLimiter starts the deadline and submits the task to ThreadPoolBulkhead. If the pool and queue are full, bulkhead rejects; if accepted but not completed on time, TimeLimiter completes the stage with a timeout error. Circuit Breaker observes errors from inner policies and applies its recording policy.

In the example, `RequestNotPermitted` and `BulkheadFullException` must be ignored in Circuit Breaker. Timeouts and upstream HTTP errors are counted as failures per the chosen policy. This lets Circuit Breaker measure dependency health instead of also counting internal resource-limiting rejections.

## 10. When Should You Change the Order?

No single order fits every goal. Start by asking what you want to limit and which duration you want metrics to measure:

| Goal | Adjustment to consider | Trade-off |
| --- | --- | --- |
| Limit all incoming requests even when Circuit Breaker is OPEN | Place Rate Limiter before Circuit Breaker | Requests blocked by the circuit still consume quota |
| Reject early when dependency is OPEN | Place Circuit Breaker before Rate Limiter and Bulkhead | Must ignore local rejection errors emitted by inner policies |
| Deadline includes queue wait time | Place TimeLimiter outside submission to ThreadPoolBulkhead | Queue time also consumes timeout budget |
| Limit only execution time after worker starts | Start timeout inside worker task or configure HTTP client timeout | Queue wait time needs its own separate deadline |
| Prevent Bulkhead rejections from affecting failure rate | Place Bulkhead outside Circuit Breaker or ignore BulkheadFullException | Circuit Breaker may check OPEN after acquiring a slot if Bulkhead is outside |

If Bulkhead sits outside Circuit Breaker, a request may acquire a slot before Circuit Breaker rejects due to OPEN, though a full Bulkhead error will bypass Circuit Breaker. If Circuit Breaker sits outside Bulkhead, it rejects OPEN faster but must ignore Bulkhead exceptions to avoid tripping the circuit erroneously. Choose based on priority between fail-fast behavior and metric classification.

When using annotations/AOP, actual runtime order also depends on the library's aspect ordering and application configuration. Do not infer execution order solely from annotation placement on a method. Verify with tests or logs identifying each policy, especially when multiple aspects wrap the same call.

## 11. Common Pitfalls When Composing Policies

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Placing Bulkhead after an unbounded queue | Tasks pile up before reaching the isolation boundary | Apply limits early and use bounded queues |
| Rate Limiter after Bulkhead | Over-quota requests still occupy slots or queues before rejection | Check quota before allocating execution resources |
| TimeLimiter measures only worker execution and ignores queue | Requests can expire while still waiting | Put deadline around submission or set a separate queue deadline |
| Circuit Breaker counts `RequestNotPermitted` as dependency failure | Circuit trips due to exhausted local quota | Ignore the exception and monitor Rate Limiter separately |
| Circuit Breaker counts `BulkheadFullException` as dependency failure | Circuit trips due to full local pool even when dependency is healthy | Ignore the exception or adjust ordering |
| Not setting HTTP client timeouts | Canceling a Future may not stop the network request | Configure timeouts/cancellation in the HTTP client |
| Retrying immediately when Bulkhead is full | Adds extra pressure while the system is overloaded | Reject gracefully or retry with backoff |
| Not monitoring each policy separately | Hard to tell dependency failures apart from local limits | Record metrics and logs per policy |

## 12. Testing and Observing the Actual Order

Test these scenarios with a mock client or staging environment:

1. Circuit Breaker OPEN: verify requests are rejected before Rate Limiter and Bulkhead allocate resources.
2. Rate Limiter quota exhausted: verify no requests reach the dependent service and Circuit Breaker failure rate does not rise.
3. Bulkhead full: verify tasks are rejected, configured thread/queue counts are not exceeded, and the exception does not inflate dependency failure rate.
4. Task waiting in queue too long: verify TimeLimiter expires per the end-to-end deadline.
5. Dependent service returns HTTP 5xx or times out: verify Circuit Breaker records the failures and updates its sliding window.
6. Dependent service recovers: verify HALF_OPEN permits only the configured number of probe calls and transitions state according to results.

Track at minimum:

- Rate Limiter: granted permits, rejected requests, and wait time.
- Bulkhead: active threads, queued tasks, and rejection count.
- TimeLimiter: timeout count, completion duration, and canceled tasks.
- Circuit Breaker: state, failure rate, slow-call rate, rejected call count, and state transitions.

When dashboards show failure rate rising alongside `BulkheadFullException`, inspect your ignore policy before concluding the dependent service is failing. If timeouts rise while queue wait accounts for most of the duration, review pool size, queue capacity, and deadlines rather than simply raising the timeout.

## 13. Ordering Workflow

When composing Rate Limiter, Bulkhead, TimeLimiter, and Circuit Breaker, follow this sequence:

1. Identify dependency limits: request rate, concurrency, response time, and failure thresholds.
2. Choose the right Bulkhead: semaphore for concurrency limits or ThreadPoolBulkhead for an isolated pool and bounded queue.
3. Choose the deadline: decide whether timeout includes queue wait time or only execution time.
4. Place Rate Limiter before resource-consuming regions if the goal is preventing over-quota requests from taking slots.
5. Place Circuit Breaker where it satisfies fail-fast goals; usually on the outside to check OPEN before granting quota and resources.
6. Classify exceptions: record timeouts and dependency errors; ignore or handle Rate Limiter/Bulkhead rejections separately.
7. Test the actual order, measure per-policy metrics, and tune based on traffic and time budgets.

Composing in the right order lets each policy do its intended job: Rate Limiter controls rate, Bulkhead bounds concurrent resources, TimeLimiter enforces deadlines, and Circuit Breaker stops calling degraded dependencies. Most importantly, clearly define what time span and error types each mechanism observes to avoid tripping the circuit on local overload or holding requests longer than the system can sustain.
