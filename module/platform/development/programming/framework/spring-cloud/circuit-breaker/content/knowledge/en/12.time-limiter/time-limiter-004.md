# Slow Call Threshold Does Not Automatically Stop a Running Call

In Spring Cloud Circuit Breaker with Resilience4j, `slowCallDurationThreshold` helps identify a call that takes too long. When the call finishes, the circuit breaker records it as a slow call and updates `slowCallRate`. If the slow call rate reaches the threshold, the breaker can transition from `CLOSED` to `OPEN` to block new calls. However, this threshold **does not automatically stop an in-flight call**.

To limit wait time, you need a timeout mechanism such as `TimeLimiter` for asynchronous tasks or a timeout supported directly by the HTTP/RPC client. The three mechanisms are related but handle different tasks: the circuit breaker evaluates dependency health, TimeLimiter bounds task wait time, and client timeouts bound wait time at the connection and data-transfer layer.

## 1. Slow call threshold only classifies outcomes

Resilience4j measures the execution duration of a protected call. `slowCallDurationThreshold` defines the duration at which a call is classified as slow. `slowCallRateThreshold` sets the maximum acceptable percentage of slow calls in the sliding window before the circuit breaker opens.

Example configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        failureRateThreshold: 50
```

With this configuration, a call lasting more than one second is considered slow. If at least five calls have been recorded and the slow call rate reaches 50% in the window, the circuit breaker can transition to `OPEN`. This mechanism evaluates the outcome and duration after the call finishes; it does not send a cancellation signal to the HTTP client, interrupt the thread, or release the socket of a call still waiting.

Imagine the dependency takes eight seconds to reply. With `slowCallDurationThreshold: 1s`, the call can still keep waiting for the full eight seconds. Only once it completes does the circuit breaker have the execution duration to record it as a slow call. New requests may be blocked after the slow-call rate hits the threshold, but calls previously permitted continue running.

## 2. Distinguishing slow-call threshold, TimeLimiter, and client timeout

| Mechanism | Purpose | Effect on an in-flight call |
| --- | --- | --- |
| `slowCallDurationThreshold` | Classifies slow calls to compute `slowCallRate` | Does not automatically stop the call; only records duration when an outcome arrives |
| `slowCallRateThreshold` | Decides when the slow-call rate is high enough to open the circuit breaker | Blocks new calls after the breaker opens; does not cancel already-permitted calls |
| Resilience4j `TimeLimiter` | Bounds wait time of a `Future` or `CompletionStage` | Completes the wrapped operation with a timeout; may request canceling the `Future` depending on config |
| HTTP/RPC client timeout | Bounds connect, response-wait, or data-read time at the transport layer | The client can terminate the I/O operation according to implementation capabilities |

These mechanisms complement each other. Slow-call thresholds detect a slowing service and open the circuit when there is enough evidence. TimeLimiter keeps the caller from waiting indefinitely on asynchronous tasks. Client timeouts set practical limits on network operations, such as connect timeout, response timeout, or read timeout.

Do not set `slowCallDurationThreshold` in place of a timeout. With only a slow-call threshold, handler threads can still be held for a long time and many slow calls together can exhaust the thread pool.

## 3. TimeLimiter works with asynchronous tasks

Resilience4j TimeLimiter supports task types based on `Future` and `CompletionStage`. It schedules a timeout deadline. If the task has not finished when time expires, the result is completed with a timeout error. Depending on configuration, TimeLimiter also requests canceling the running `Future`.

Example configuration for the `inventory` instance:

```yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
```

`timeoutDuration` is the maximum time the caller waits for the wrapped task's result. `cancelRunningFuture` indicates whether TimeLimiter requests canceling the future on timeout. This cancellation is a signal to the task; it does not guarantee that all underlying I/O operations have stopped. The running thread must be able to react to interrupts or the client must support request cancellation.

### Example with Future and executor

For a blocking task without an asynchronous API, you can run the task on an executor and wrap the `Future` with TimeLimiter:

```java
import io.github.resilience4j.timelimiter.TimeLimiter;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeoutException;

public class InventoryGateway {

    private final ExecutorService workers = Executors.newFixedThreadPool(20);
    private final ScheduledExecutorService timer =
        Executors.newScheduledThreadPool(1);

    private final TimeLimiter timeLimiter = TimeLimiter.of(
        TimeLimiterConfig.custom()
            .timeoutDuration(Duration.ofSeconds(2))
            .cancelRunningFuture(true)
            .build()
    );

    public InventoryResult fetch(String sku) throws Exception {
        Callable<InventoryResult> limitedCall =
            TimeLimiter.decorateFutureSupplier(
                timeLimiter,
                timer,
                () -> workers.submit(() -> inventoryClient.fetch(sku))
            );

        return limitedCall.call();
    }
}
```

The snippet illustrates how the APIs fit together; `inventoryClient` needs to be injected and executors need their lifecycles managed as beans or application resources. After two seconds, the caller receives a timeout error. With `cancelRunningFuture(true)`, TimeLimiter invokes cancellation on the `Future` returned by the executor.

Do not create a new executor per request. Use a bounded executor and monitor the queue and active threads. If the task does not react to interrupts, the thread may keep running after the caller receives a timeout. Then old tasks continue consuming resources and can exhaust the thread pool.

### CompletionStage when the client already supports async

If the client returns a `CompletionStage`, there is no need to offload the task to a blocking thread just to use TimeLimiter:

```java
import io.github.resilience4j.timelimiter.TimeLimiter;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ScheduledExecutorService;
import java.util.function.Supplier;

public CompletionStage<InventoryResult> fetchAsync(String sku) {
    Supplier<CompletionStage<InventoryResult>> request =
        () -> inventoryClient.fetchAsync(sku);

    return timeLimiter.executeCompletionStage(timer, request);
}
```

In this example, `inventoryClient.fetchAsync(...)` represents a client API returning a `CompletionStage`. TimeLimiter bounds the stage completion time observed by the caller. Whether the underlying request can be canceled still depends on the stage and client implementation; verify whether canceling the stage propagates to the network request or only completes the application-side stage early.

## 4. Why cancel(true) does not guarantee stopping I/O

When `cancelRunningFuture` is enabled, TimeLimiter requests canceling the future. For a `Future` returned by `ExecutorService.submit(...)`, cancellation can send an interrupt to the running thread. However:

- Blocking code only stops when the API being called reacts to interrupts or checks interrupt status.
- Some I/O libraries do not immediately close sockets when a thread is interrupted.
- `CompletableFuture.cancel(true)` does not mean the thread executing the computation is guaranteed to be interrupted.
- If the HTTP client has its own request cancellation mechanism, verify that the cancellation signal reaches the client.

Therefore, client-layer timeouts remain essential. Set connect timeout to limit connection setup time, response/read timeout to limit data wait time, and an overall deadline suited to the business request's latency budget. Exact property names and behavior depend on the HTTP/RPC client in use.

Example of timing relationships:

```text
Business request starts
       |
       +---- HTTP connect timeout
       |
       +---- HTTP response/read timeout
       |
       +---- TimeLimiter timeout (2 seconds)
       |          |
       |          +--> Caller receives TimeoutException
       |          +--> May request canceling Future
       |
       +---- Dependency actually finishes (may be later if not cancelable)
```

If TimeLimiter finishes at two seconds while I/O runs for another ten seconds, the caller is freed but execution resources may still be held. A timeout is only fully effective when the underlying mechanism can genuinely stop or bound the operation.

## 5. Combining TimeLimiter with CircuitBreaker

Circuit breaker and TimeLimiter solve two different problems. TimeLimiter causes the wrapped task to end with a timeout when the deadline is exceeded. The circuit breaker records that timeout as an error outcome if the exception is classified as a failure, and can also record the call as slow if the measured duration exceeds `slowCallDurationThreshold`.

Example configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
```

In this example, a call completing after 1.5 seconds may be recorded as slow yet still succeed. A call not completing after two seconds will be terminated by TimeLimiter with a timeout. If the timeout exception is recorded by the circuit breaker, it increases the failure rate; depending on the duration the circuit breaker observes and how decorators are composed, it may also be classified as a slow call.

When composing decorators or integrations, ensure the circuit breaker observes the outcome of the timeout-wrapped operation so timeouts are counted in failure statistics. Wrapping order affects the duration and exceptions each mechanism observes. With Spring Cloud CircuitBreaker Resilience4j, configure `resilience4j.timelimiter.instances` with the same ID as the circuit breaker and verify actual behavior for the synchronous or reactive API the application uses. Do not assume every synchronous call is automatically moved onto an executor so TimeLimiter can interrupt it.

If the application uses a Spring Cloud factory for asynchronous tasks, choose an API or overload supporting `Future`/`CompletionStage` for the version in use. For direct blocking calls, configure timeouts on the HTTP client and consider a bounded executor if offloading tasks to asynchronous execution.

## 6. For reactive calls, timeout emits an upstream cancel signal

In Reactor, the `timeout(...)` operator limits a publisher's wait time. On expiration, the subscriber receives a timeout error and Reactor sends a cancel signal upstream:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<InventoryResult> fetchInventory(String sku) {
    return inventoryClient.fetch(sku)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            java.util.concurrent.TimeoutException.class,
            error -> Mono.just(InventoryResult.unavailable(sku))
        );
}
```

This is an example of applying a timeout at the Reactor layer. With Resilience4j, you can configure TimeLimiter and appropriate reactive integration; choose one consistent place to manage deadlines to avoid overlapping timeouts where it is unclear which one raises the error. The cancel signal only takes effect if the upstream publisher and HTTP client support cancellation. If the publisher wraps a non-interruptible blocking task, underlying work may still continue.

Do not call `block()` on an event loop to turn a reactive call into a synchronous one. Doing so can block the event loop during the wait and impact other requests. Use the client's non-blocking API, transport timeouts, and appropriate reactive operators.

## 7. Setting thresholds based on the latency budget

Values must be chosen together based on how long the business flow can wait. For example, if the overall API has a three-second deadline and needs to keep one second for remaining processing, the inventory call should not have a timeout exceeding two seconds.

| Property | Example | Role |
| --- | ---: | --- |
| `slowCallDurationThreshold` | 800 ms | Marks a call as starting to run slow relative to target |
| `timeoutDuration` | 1.5 s | Bounds wait time of the asynchronous task |
| HTTP response/read timeout | 1.4 s | Bounds response wait at the HTTP client layer |
| API deadline | 3 s | Overall budget of the business request |

The values above only illustrate ordering and relationships. HTTP client timeouts typically need to be less than or equal to TimeLimiter so I/O finishes before the caller expires. The slow-call threshold can be lower than the timeout to detect degradation before calls time out. The API deadline must include internal processing, retries, serialization, and other dependencies.

Avoid setting each dependency's timeout equal to the entire API deadline. If a request sequentially calls three services, each waiting up to three seconds will push total time far past the deadline. Propagate or compute remaining time budget for each dependency, and consider skipping retries when insufficient time remains.

## 8. Test proving slow-call threshold does not cancel a call

A test should distinguish two facts: the circuit breaker records a slow call after it completes, and TimeLimiter can end waiting before the task completes. With the native API, you can use a latch to keep the supplier running past the threshold:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);
ExecutorService executor = Executors.newSingleThreadExecutor();

CircuitBreaker breaker = CircuitBreaker.of(
    "inventory",
    CircuitBreakerConfig.custom()
        .slowCallDurationThreshold(Duration.ofMillis(100))
        .slowCallRateThreshold(50)
        .slidingWindowSize(1)
        .minimumNumberOfCalls(1)
        .build()
);

Future<String> call = executor.submit(() -> breaker.executeSupplier(() -> {
    started.countDown();
    try {
        release.await();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(ex);
    }
    return "ok";
}));

try {
    assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();
    // Keep supplier waiting at least 150 ms, longer than the 100 ms threshold.
    assertThat(release.await(150, TimeUnit.MILLISECONDS)).isFalse();
    assertThat(call.isDone()).isFalse();
    release.countDown();
    assertThat(call.get(1, TimeUnit.SECONDS)).isEqualTo("ok");
    assertThat(breaker.getMetrics().getNumberOfSlowCalls()).isEqualTo(1);
} finally {
    release.countDown();
    executor.shutdownNow();
}
```

This illustrative snippet should be placed inside a test with proper executor management and wait timeouts to avoid hanging if an assertion fails. While the supplier is still waiting on `release`, the circuit breaker does not release it merely because 100 ms has elapsed. Only after the supplier completes does the metric reflect the slow call.

A separate TimeLimiter test can use an incomplete `Future` and verify the caller receives a timeout after the configured duration. When testing `cancelRunningFuture`, verify both the future state and whether the task actually stopped; do not rely solely on `Future.isCancelled()` because canceled state does not prove underlying I/O stopped.

## 9. Common mistakes

- **Using `slowCallDurationThreshold` as a timeout:** the call keeps running until the client finishes or times out on its own.
- **Wrapping a blocking task without a proper executor:** the calling thread remains blocked or a new thread pool is exhausted when the dependency slows down.
- **Assuming `cancelRunningFuture: true` definitely closes sockets:** canceling a Future only requests task cancellation; the client and underlying code must support cancellation.
- **Omitting timeouts on the HTTP/RPC client:** the caller may receive a timeout while I/O keeps consuming resources.
- **Setting TimeLimiter longer than the business deadline:** the outer calling layer expires before the dependency is released.
- **Allowing retries to continue after timeout:** new attempts can add load to an already degraded dependency; bound retry count and remaining deadline.
- **Confusing slow calls with failed calls:** a slow call can still return a success; failure rate and slow-call rate are two separate metrics.

## 10. Implementation rules

- Use `slowCallDurationThreshold` to detect abnormal latency and help the circuit breaker open when the slow-call rate exceeds the threshold.
- Use TimeLimiter for `Future` or `CompletionStage` when you need to bound wait time of an asynchronous task.
- Set connect, response/read timeouts, or deadlines on the HTTP/RPC client to bound actual I/O operations.
- Enable `cancelRunningFuture` only when you understand how the task and client react to cancellation.
- Use a bounded executor for blocking tasks offloaded to asynchronous execution; monitor queues and running threads.
- With Reactor, use non-blocking timeout/cancel and a client supporting cancellation; do not block the event loop.
- Test slow-call classification, timeout, cancellation, and circuit breaker state transitions separately.

The slow-call threshold tells you how slow the dependency has become; it is not a command to stop work. Combining circuit breaker, TimeLimiter, and client-side timeouts under a shared latency budget helps the application detect degradation, bound wait times, and control resources held by unfinished calls.
