# Boundary Between Circuit Breaking and Time Limiting

## Lesson Objectives

Circuit breakers and TimeLimiter are often used together to protect calls to a dependent service, but they solve two different problems. A circuit breaker observes the outcomes of multiple calls and decides whether to allow a new call to proceed. TimeLimiter limits the wait time of a single asynchronous execution. If the two mechanisms are confused, the application may still wait too long even though the breaker has recorded slow calls, or open the breaker without an actual timeout on the running operation.

In Spring Cloud CircuitBreaker with Resilience4j, you need to clearly identify where I/O is performed, where time is limited, and where outcomes are recorded. After this lesson, you can:

- Distinguish the roles of CircuitBreaker and TimeLimiter in a dependency call.
- Explain why a slow call threshold does not automatically cancel a running operation.
- Configure a timeout for a Future or CompletionStage using Resilience4j TimeLimiter.
- Use Reactor's timeout operator for WebClient calls and place operators in the right order.
- Combine timeouts with CircuitBreaker so that timeouts are recorded according to policy.
- Distinguish HTTP library timeouts from task cancellation or remote request cancellation.

## 1. Two different questions: should we call and how long should we wait?

Suppose order-service needs to call inventory-service to check stock. There are two operational questions:

1. **Should we send a new call?** If recent calls have repeatedly failed or been too slow, the circuit breaker can transition to OPEN and fail fast on subsequent calls.
2. **How long is a single call allowed to run at most?** TimeLimiter or the HTTP client's timeout limits the wait time of the current call.

A circuit breaker primarily makes decisions based on recent history. TimeLimiter sets a time limit for a single execution. A call can be allowed through a CLOSED breaker and still time out because the response takes too long.

| Mechanism | Question it answers | Primary effect |
| --- | --- | --- |
| CircuitBreaker | Should a new call to the dependency be allowed? | Allows, records the outcome, or fails fast when OPEN. |
| TimeLimiter | How long at most does the application wait for an asynchronous task's result? | Completes with a timeout error on expiration and may request canceling the Future. |
| HTTP client timeout | How long at most to connect or wait for a network response? | Stops waiting at the client layer depending on library capabilities. |
| Reactor timeout | How long is a Publisher allowed to emit no signals? | Emits TimeoutException and sends a cancel signal upstream. |

These mechanisms complement each other. A circuit breaker is not a countdown timer for an in-flight call. Likewise, TimeLimiter does not evaluate the failure rate across multiple calls to decide the OPEN state.

## 2. Slow call threshold is not a timeout

Resilience4j CircuitBreaker can mark a call as slow using slowCallDurationThreshold. When execution time exceeds the threshold, the outcome is classified as a slow call. If the slow call rate in the sliding window reaches slowCallRateThreshold after enough samples are collected, the breaker can open.

For example:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            slowCallDurationThreshold: 1500ms
            slowCallRateThreshold: 50
            failureRateThreshold: 50

With this configuration, a call taking 1.8 seconds can be recorded as a slow call even if it still returns a successful result. When the slow call rate exceeds the threshold, the breaker can transition to OPEN to prevent more requests from piling onto a degraded dependency.

However, slowCallDurationThreshold only classifies execution duration. It does not automatically close an HTTP connection, interrupt a thread, or terminate a running Future. If a call takes 30 seconds, the breaker can record it as slow after the call finishes; preventing a 30-second wait still requires a timeout at the execution layer.

Therefore, do not use slowCallDurationThreshold in place of a timeout. Configure both health evaluation thresholds and a per-call deadline.

## 3. TimeLimiter bounds asynchronous tasks

Resilience4j TimeLimiter supports limiting the wait time of a Future or CompletionStage. When the task does not complete within timeoutDuration, TimeLimiter completes the caller-side result with a timeout error. If cancelRunningFuture is enabled, TimeLimiter requests cancellation of the running Future.

Basic configuration in application.yml:

    resilience4j:
      timelimiter:
        instances:
          inventory:
            timeoutDuration: 2s
            cancelRunningFuture: true

timeoutDuration is the maximum time to wait for the result. cancelRunningFuture controls whether to request canceling the Future when a timeout occurs. How effective cancellation is depends on the Future implementation, executor, and library performing the task.

TimeLimiter does not turn a synchronous method into an asynchronous one. If you invoke a blocking method directly on the request thread and only wrap the already-completed result in a Future, a timeout cannot help. The task must be launched as a Future or CompletionStage so TimeLimiter can track its completion time.

## 4. TimeLimiter example with CompletionStage

Suppose the application has a legacy blocking client, but wants to run the work on a dedicated executor and bound the wait time with TimeLimiter. You can use CompletionStage:

    import io.github.resilience4j.timelimiter.TimeLimiter;
    import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
    import java.util.concurrent.CompletableFuture;
    import java.util.concurrent.CompletionStage;
    import java.util.concurrent.Executor;
    import java.util.concurrent.ScheduledExecutorService;
    import java.util.function.Supplier;

    public class InventoryAsyncGateway {

        private final BlockingInventoryClient client;
        private final TimeLimiter timeLimiter;
        private final Executor ioExecutor;
        private final ScheduledExecutorService timeoutScheduler;

        public InventoryAsyncGateway(
                BlockingInventoryClient client,
                TimeLimiterRegistry registry,
                Executor ioExecutor,
                ScheduledExecutorService timeoutScheduler) {
            this.client = client;
            this.timeLimiter = registry.timeLimiter("inventory");
            this.ioExecutor = ioExecutor;
            this.timeoutScheduler = timeoutScheduler;
        }

        public CompletionStage<InventoryResponse> find(String sku) {
            Supplier<CompletionStage<InventoryResponse>> source = () ->
                CompletableFuture.supplyAsync(
                    () -> client.find(sku),
                    ioExecutor
                );

            return timeLimiter.executeCompletionStage(
                timeoutScheduler,
                source
            );
        }
    }

In this example:

- BlockingInventoryClient performs the synchronous call.
- CompletableFuture.supplyAsync offloads the call to ioExecutor without blocking the thread calling find.
- TimeLimiter uses timeoutScheduler to track the deadline.
- executeCompletionStage returns a CompletionStage that completes with either the result or a timeout error.

In a real application, ioExecutor and timeoutScheduler must have their lifecycles managed by Spring, have bounded resources, and be shut down properly when the application stops. Do not create a new executor per request. You also need to configure connect and response timeouts directly on the HTTP client used by BlockingInventoryClient.

If the blocking client does not support interruption or request cancellation, the Future may be marked canceled while the underlying work continues running on the worker until the client itself times out or returns. TimeLimiter limits how long the caller waits; it does not guarantee that the remote server has stopped processing.

## 5. Combining TimeLimiter with CircuitBreaker

When a call is timed out by TimeLimiter, the timeout error can be recorded by the circuit breaker as a failure. For this to happen, CircuitBreaker needs to observe the time-limited CompletionStage.

Example combining Resilience4j components:

    import io.github.resilience4j.circuitbreaker.CircuitBreaker;
    import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
    import io.github.resilience4j.timelimiter.TimeLimiter;
    import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
    import java.util.concurrent.CompletionStage;
    import java.util.concurrent.ScheduledExecutorService;
    import java.util.function.Supplier;

    public CompletionStage<InventoryResponse> find(String sku) {
        CircuitBreaker breaker = circuitBreakerRegistry
            .circuitBreaker("inventory");

        TimeLimiter limiter = timeLimiterRegistry
            .timeLimiter("inventory");

        Supplier<CompletionStage<InventoryResponse>> source = () ->
            CompletableFuture.supplyAsync(
                () -> blockingClient.find(sku),
                ioExecutor
            );

        Supplier<CompletionStage<InventoryResponse>> timedSource = () ->
            limiter.executeCompletionStage(timeoutScheduler, source);

        Supplier<CompletionStage<InventoryResponse>> protectedCall =
            CircuitBreaker.decorateCompletionStage(breaker, timedSource);

        return protectedCall.get();
    }

The order here matters:

1. source launches the remote operation on the executor.
2. TimeLimiter wraps the CompletionStage to raise an error if the deadline is exceeded.
3. CircuitBreaker wraps the time-limited stage and observes the final outcome.

If source succeeds within the deadline, the breaker records a success. If source fails or TimeLimiter raises a timeout, the breaker can record a failure according to its exception configuration. When the breaker is OPEN, the call is rejected before source executes; thus no new tasks are spawned just to wait for a timeout.

You must configure recordExceptions/ignoreExceptions appropriately. If TimeoutException is ignored, the breaker will not count timeouts toward the failure rate. If timeouts reflect a dependency failing to meet its SLO, you typically want the breaker to record them. Verify the actual exception thrown by the integration layer and library version in use.

## 6. Configuring both thresholds within the same time budget

One design approach is to set the slow call threshold lower than the timeout. That way, calls already showing signs of slowness are tracked before hitting the hard limit.

For example:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            slowCallDurationThreshold: 1500ms
            slowCallRateThreshold: 50
            failureRateThreshold: 50
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

      timelimiter:
        instances:
          inventory:
            timeoutDuration: 2s
            cancelRunningFuture: true

In this example:

- A call completing in 900 ms: normal success.
- A call completing in 1.8 seconds: may succeed, but is recorded as a slow call.
- A call not completing within 2 seconds: TimeLimiter raises a timeout.
- When the slow call rate or failure rate exceeds the threshold after enough samples: CircuitBreaker can open.
- When CircuitBreaker is OPEN: new calls fail fast and do not launch the dependent task.

These numbers are for illustration only. Choose timeouts based on the overall request time budget, normal dependency latency, and SLOs. If the inventory timeout is 2 seconds while the order API only has a 1-second budget, the calling layer may time out before TimeLimiter signals. Timeouts must be coordinated from outside in, leaving budget for subsequent steps and fallback handling.

## 7. Timeouts for WebClient and Reactor calls

With WebClient, calls are inherently asynchronous and return a Mono or Flux. You can use Reactor's timeout operator to bound the wait time:

    Mono<InventoryResponse> request = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(2));

If the publisher does not emit a signal within the specified duration, the timeout operator emits TimeoutException and sends a cancellation upstream. Distinguish the overall publisher timeout from HTTP client connect/response timeouts. Configure appropriate connect and response limits on the WebClient connector to handle the network layer properly.

You can combine this with Resilience4j Reactor CircuitBreakerOperator:

    Mono<InventoryResponse> protectedRequest = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(2))
        .transformDeferred(
            CircuitBreakerOperator.of(inventoryCircuitBreaker)
        )
        .onErrorResume(
            error -> Mono.just(InventoryResponse.unknown(sku))
        );

The timeout is placed before CircuitBreakerOperator so the breaker sees TimeoutException as a failed publisher outcome. The fallback is placed after the operator so it does not turn the upstream error into normal completion before the breaker records it. In this example, the illustrative fallback returns an unknown status; a real application should classify errors and only convert business-permitted errors into substitute results.

If you use Spring Cloud's ReactiveCircuitBreakerFactory, you can pass the Mono and fallback into run. How TimeLimiter configuration is supported and applied depends on the starter, Spring Cloud CircuitBreaker version, and implementation in use. For an explicit deadline on a Reactor chain, Mono.timeout is a direct way to express the publisher's time limit; check whether the application adds any built-in TimeLimiter to avoid applying two redundant timeouts.

## 8. Timeout does not mean canceling server-side processing

When TimeLimiter or a Reactor timeout triggers, the caller can stop waiting and receive a timeout error. That does not mean the remote service has stopped working.

There are three scopes of cancellation to distinguish:

1. **Canceling the caller's wait:** the application-side Future or publisher completes with timeout/cancel.
2. **Canceling the operation in the HTTP client:** the client library attempts to close the request, cancel the network subscription, or drop the connection.
3. **Stopping server-side processing:** the server detects that the client disconnected and actively aborts the task; this depends on the protocol and server implementation.

Not every operation can be canceled safely. A data write command may have already been executed by the server before the client timed out. If the client retries immediately, there is a risk of sending the write command a second time. For state-mutating operations, use an idempotency key, a unique request ID, or a status-check mechanism to avoid duplicate side effects.

If a blocking API does not respond to interrupts, the worker can remain occupied after the caller has timed out. HTTP client-side timeouts and concurrency limits remain essential to free actual resources.

## 9. Choosing timeouts by operation type

Not every endpoint needs the same timeout. Base the choice on business characteristics and the dependency's latency distribution:

| Operation | How to choose the timeout |
| --- | --- |
| Simple inventory lookup | Short, based on p95/p99 latency and the order creation request budget. |
| Multi-step pricing calculation | May be longer than a simple lookup, but must still fit within the overall request budget. |
| Loading large reports or datasets | Needs a timeout suited to data size, pagination, or streaming; do not share the short timeout of a lookup API. |
| Sending a stock reservation command | Set a clear deadline and handle idempotency because a timeout does not tell whether the server executed the command. |
| Long-lived event stream | Do not use a short overall timeout to cut off a normal stream; consider connection timeout, heartbeats, and inter-signal timeouts. |

If multiple operations share one breaker, examine whether they share the same latency profile and error policy. A long-running report API should not render a fast lookup API's slow call threshold meaningless. You can use separate IDs and separate configurations for operations with different time budgets.

## 10. Observing timeouts and breakers

To verify that both mechanisms are working together properly, track each type of event separately:

- Number of TimeLimiter timeouts by operation name.
- Number of successes, failures, and slow calls recorded by CircuitBreaker.
- Number of calls rejected when the breaker is OPEN.
- p50, p95, and p99 response times of the dependency.
- Number of Futures or blocking tasks still running after the caller timed out, if the application can measure it.
- Fallback rate and degraded statuses returned by the API.

If timeouts increase while the breaker stays CLOSED, there may not be enough samples yet, the failure rate may not have crossed the threshold, or the timeout exception may be ignored. If the breaker opens yet workers remain occupied, review cancellation capabilities and HTTP client timeouts. If the API returns a fallback while the server still executes the write command, review idempotency and handling of uncertain states.

Resilience4j metrics can be exported via Spring Boot Actuator and Micrometer when the appropriate integration is enabled. Exact metric names depend on the version and registry. Check the actual metrics rather than assuming names are always identical across releases.

## 11. Hands-on exercise: separating timeout from circuit breaking decisions

Create a gateway that calls inventory-service and perform these steps:

1. Configure HTTP client timeouts to bound connection and response wait times.
2. For an asynchronous call, add a TimeLimiter with a timeoutDuration of 2 seconds.
3. Configure CircuitBreaker with slowCallDurationThreshold at 1.5 seconds and an appropriate slowCallRateThreshold.
4. Wrap the CompletionStage already bounded by TimeLimiter with CircuitBreaker.
5. Trigger a call that responds in 800 ms and verify it succeeds.
6. Trigger a call that responds in 1.8 seconds and verify it is recorded as a slow call without timing out.
7. Trigger a call that takes longer than 2 seconds and verify TimeLimiter raises a timeout.
8. Trigger multiple slow/failing calls so the breaker transitions to OPEN; verify new calls fail fast.
9. Recover inventory-service and observe trial calls in HALF_OPEN.
10. Check whether blocking tasks keep running after timeout and adjust HTTP client timeouts, executors, or concurrency if needed.

With WebClient, repeat the exercise using Mono.timeout and CircuitBreakerOperator. Verify that the timeout error passes through the breaker before the fallback handles it. Compare metrics between both approaches to see that TimeLimiter/timeout bounds each individual call, while CircuitBreaker uses outcome history to protect subsequent calls.

When finished, you should be able to explain why a slow call threshold is not a timeout, how TimeLimiter differs from an HTTP client timeout, why cancellation does not guarantee the server stopped processing, and why the breaker must observe timeout errors. Properly separating these responsibilities helps the system bound per-request wait times and prevent an unstable dependency from causing cascading failures.
