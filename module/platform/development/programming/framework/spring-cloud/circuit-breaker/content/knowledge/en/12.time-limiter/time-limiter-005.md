# Coordinating TimeLimiter with Future or CompletionStage

`TimeLimiter` limits how long an application waits for the result of a dependent call. In Java, Resilience4j provides two common integration styles: `Future` for synchronous waiting flows and `CompletionStage` for asynchronous processing flows. Choosing the right style helps Spring Cloud Circuit Breaker protect latency while still keeping control over threads, fallbacks, and error outcomes.

Keep in mind that TimeLimiter bounds the caller's wait time. It does not automatically create workers to run a blocking task, nor does it guarantee that all work on the dependency stops immediately upon expiration. To protect resources, combine an appropriate executor, client timeouts, and a Bulkhead.

## 1. Distinguishing Future and CompletionStage

`Future<T>` represents a result that will be available in the future. The caller usually retrieves the result using `get()`, or `get(timeout, unit)`. These operations block the calling thread until a result, error, or timeout occurs.

`CompletionStage<T>` represents a step in an asynchronous processing chain. The caller registers callbacks such as `thenApply`, `thenCompose`, `handle`, or `whenComplete`; the calling thread does not need to wait for the result. `CompletableFuture<T>` implements both `Future<T>` and `CompletionStage<T>`, though how it is used with TimeLimiter depends on the API chosen.

| Criterion | Future | CompletionStage |
| --- | --- | --- |
| How results are retrieved | `get()` blocks the thread | Callbacks/chains run when the stage completes |
| TimeLimiter API | `executeFutureSupplier` or `decorateFutureSupplier` | `executeCompletionStage` or `decorateCompletionStage` |
| Scheduler | No separate scheduler needed to wait for timeout | Requires `ScheduledExecutorService` to trigger timeout |
| Where does the actual work run? | The executor that created the Future | The executor or asynchronous HTTP client that created the CompletionStage |
| Behavior on timeout | Can call `Future.cancel(true)` per configuration | The stage completes with a timeout error; stopping the source task depends on the execution API |

Choose `Future` when the existing API is synchronous and the caller accepts waiting on a thread. Choose `CompletionStage` when you need to return results asynchronously, compose multiple steps, or avoid holding request threads while waiting on I/O.

## 2. Configuring TimeLimiter

Resilience4j lets you set the deadline and Future cancellation policy via `TimeLimiterConfig`. For example:

```java
TimeLimiterConfig config = TimeLimiterConfig.custom()
        .timeoutDuration(Duration.ofMillis(800))
        .cancelRunningFuture(true)
        .build();

TimeLimiter timeLimiter = TimeLimiter.of("pricing", config);
```

`timeoutDuration` is the maximum time the caller waits. `cancelRunningFuture` requests canceling the running Future when the Future branch expires. Resilience4j's defaults are one second and `cancelRunningFuture` set to `true`; configure them explicitly based on each dependency's SLA instead of relying on defaults.

In a Spring Boot application, you can declare instances in `application.yml`:

```yaml
resilience4j:
  timelimiter:
    instances:
      pricing:
        timeoutDuration: 800ms
        cancelRunningFuture: true
```

The ID `pricing` must match the instance name used in code or annotations. With Spring Cloud CircuitBreaker, `resilience4j.timelimiter.instances.pricing` is also the TimeLimiter configuration for a breaker created with ID `pricing`. Properties configuration takes higher precedence than a Java `Customizer`; if runtime values differ from your customizer bean, inspect the instance configuration and property sources.

Spring Cloud CircuitBreaker enables TimeLimiter by default for executions of the Resilience4j implementation. It can be disabled globally with `spring.cloud.circuitbreaker.resilience4j.disable-time-limiter: true`, or toggled per instance/group via `disable-time-limiter-map`. Disable it only when the HTTP client layer or another mechanism already enforces an equivalent deadline.

## 3. Using TimeLimiter with Future

`executeFutureSupplier` accepts a `Supplier<Future<T>>`. Resilience4j obtains the Future from the supplier and waits for its result within the configured deadline. The caller thread is blocked during that wait; if it expires, TimeLimiter throws `TimeoutException` and calls `future.cancel(true)` when `cancelRunningFuture` is `true`.

Example calling the pricing service using a synchronous client while offloading the work to a worker pool:

```java
public Price getPrice(String isbn) {
    try {
        return timeLimiter.executeFutureSupplier(
                () -> pricingExecutor.submit(() -> pricingClient.fetch(isbn))
        );
    } catch (TimeoutException ex) {
        return Price.unavailable(isbn);
    } catch (Exception ex) {
        throw new IllegalStateException("Failed to fetch book price", ex);
    }
}
```

`pricingExecutor` is an `ExecutorService` managed by the application lifecycle; `pricingClient.fetch` is a blocking call. The supplier merely creates the Future and hands the work to the executor. `executeFutureSupplier` waits for the Future to finish, so the `getPrice` method remains synchronous.

When a timeout occurs, `cancel(true)` requests that the thread running the Future receive an interrupt. This is a cooperative cancellation mechanism, not a forced stop command. A task sleeping or waiting on an interrupt-aware API can stop; CPU loops, libraries ignoring interrupts, or non-cancelable I/O may still keep running. If `cancelRunningFuture` is `false`, the Future continues running and the caller simply stops waiting for the result.

Therefore, configure separate timeouts on the HTTP client, JDBC driver, or SDK. If TimeLimiter returns a fallback after 800 ms while the HTTP client still holds the socket for 30 seconds, the worker and connection can remain occupied after the caller has received the fallback result.

## 4. Using TimeLimiter with CompletionStage

With CompletionStage, use `executeCompletionStage(scheduler, supplier)`. The method returns a stage immediately; a task on `ScheduledExecutorService` tracks the deadline and completes the stage with `TimeoutException` if the deadline arrives before the source completes.

The scheduler is used only to trigger the timeout. It does not execute the dependency call itself. The work must be performed by a separate executor or an asynchronous HTTP client. For example:

```java
public CompletionStage<Price> getPriceAsync(String isbn) {
    Supplier<CompletableFuture<Price>> request = () ->
            CompletableFuture.supplyAsync(
                    () -> pricingClient.fetch(isbn),
                    pricingExecutor
            );

    return timeLimiter.executeCompletionStage(timeoutScheduler, request)
            .exceptionally(error -> Price.unavailable(isbn));
}
```

`pricingExecutor` runs the actual work; `timeoutScheduler` only schedules the expiration task. These two executors have distinct responsibilities and should be created, configured, and closed according to the application lifecycle, not created fresh for every request.

Do not write `CompletableFuture.completedFuture(pricingClient.fetch(isbn))` if `fetch` is blocking. Java must execute `fetch` before creating `completedFuture`, so the calling thread is still blocked before TimeLimiter can apply a deadline. Use `supplyAsync` with a separate executor or an HTTP API that returns a genuine CompletionStage.

On the CompletionStage path, a timeout causes the protected stage to complete exceptionally. That does not mean the source task has stopped. `CompletionStage` does not have a task cancellation contract like `Future.cancel`; if you need to stop I/O, use the HTTP client's or driver's cancellation API and set timeouts on the client itself.

When a caller needs to retrieve the result in a test or at a synchronous boundary, `stage.toCompletableFuture().get()` will block and may throw `ExecutionException` with `TimeoutException` as its cause. In asynchronous application code, continue with `thenApply`, `handle`, or `exceptionally` instead of calling `get()` or `join()`.

## 5. Combining CompletionStage with Circuit Breaker

Using TimeLimiter alone gives the application a timeout, but not a sliding window or `CLOSED`/`OPEN`/`HALF_OPEN` states. For Circuit Breaker to record a timeout as a failed execution, wrap the CompletionStage with both decorators. Circuit Breaker must observe the stage already bounded by TimeLimiter:

```java
Supplier<CompletionStage<Price>> request = () ->
        CompletableFuture.supplyAsync(
                () -> pricingClient.fetch(isbn),
                pricingExecutor
        );

Supplier<CompletionStage<Price>> timedRequest =
        timeLimiter.decorateCompletionStage(timeoutScheduler, request);

Supplier<CompletionStage<Price>> protectedRequest =
        CircuitBreaker.decorateCompletionStage(circuitBreaker, timedRequest);

return protectedRequest.get()
        .exceptionally(error -> Price.unavailable(isbn));
```

In this example, TimeLimiter completes the stage with a timeout if the call takes too long; Circuit Breaker receives the stage result and records the error. The fallback is applied after Circuit Breaker so the timeout error is still recorded in statistics. Converting an error into a successful result before Circuit Breaker observes the stage can cause the breaker to record a success and stay closed even when the dependency is slow.

Decorator order determines which layer sees the error. When also combining Retry, Bulkhead, or RateLimiter, define clearly how a single attempt is counted and whether the total duration of all attempts can exceed the outer request's deadline.

## 6. Using the @TimeLimiter annotation in Spring Boot

The Resilience4j Spring Boot starter provides `@TimeLimiter` via Spring AOP. For a Spring Boot 3 application, you need the `resilience4j-spring-boot3` starter, Actuator, and AOP. For example:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-spring-boot3'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

The annotation fits methods returning `CompletionStage` or `CompletableFuture`. For example:

```java
@Service
public class PricingService {
    private final PricingClient pricingClient;
    private final Executor pricingExecutor;

    public PricingService(PricingClient pricingClient, Executor pricingExecutor) {
        this.pricingClient = pricingClient;
        this.pricingExecutor = pricingExecutor;
    }

    @TimeLimiter(name = "pricing", fallbackMethod = "priceFallback")
    public CompletableFuture<Price> getPrice(String isbn) {
        return CompletableFuture.supplyAsync(
                () -> pricingClient.fetch(isbn),
                pricingExecutor
        );
    }

    private CompletableFuture<Price> priceFallback(String isbn, Throwable error) {
        return CompletableFuture.completedFuture(Price.unavailable(isbn));
    }
}
```

The fallback has the same parameters as the original method plus an extra exception parameter at the end. Its return type must be compatible with the protected method. In the example, the fallback accepts `Throwable` to handle timeouts and other execution errors.

The protected method must be on a Spring bean invoked through an AOP proxy. An internal call from another method in the same bean can bypass the proxy. Nor does the annotation turn a blocking method returning `Price` into an asynchronous one: if the method body runs blocking work before returning a CompletionStage, the calling thread is still blocked. Construct a genuine CompletionStage using an executor or an async client.

Do not use `@TimeLimiter` on methods returning a plain value or `Future` in the Spring AOP integration. For a plain `Future`, use the `TimeLimiter.executeFutureSupplier` API; for `CompletableFuture`, use `@TimeLimiter` or `executeCompletionStage` depending on your integration style.

## 7. Coordinating with Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker provides `Resilience4JCircuitBreakerFactory` for synchronous calls and configures TimeLimiter by ID. Example instance configuration:

```yaml
resilience4j:
  timelimiter:
    instances:
      pricing:
        timeoutDuration: 800ms
        cancelRunningFuture: true

  circuitbreaker:
    instances:
      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
```

For synchronous calls via `circuitBreakerFactory.create("pricing").run(...)`, Spring Cloud applies the `pricing` instance's TimeLimiter and returns results via the synchronous API. Per-instance properties configuration takes higher precedence than a Java `Customizer`.

If a service already uses CompletionStage and needs to protect the asynchronous result, use Resilience4j's CompletionStage API directly or Spring Boot's `@TimeLimiter` as in the earlier examples. Do not wrap a CompletionStage inside `CircuitBreakerFactory.run` as if it were a synchronous value and expect the breaker to wait for the stage to complete; use the CompletionStage decorator so Circuit Breaker observes the final outcome.

## 8. Choosing timeouts and managing resources

Deadlines must match the SLA and normal latency of the dependency. If the timeout is too short, valid requests turn into errors; if too long, callers hold resources too long and fallbacks arrive late. Timeouts can be set per instance rather than sharing one value across all services.

Distinguishing the limits:

| Limit | Scope |
| --- | --- |
| Connect timeout | Time to establish a connection to the service |
| Read/response timeout | Time waiting for response data from the HTTP client |
| TimeLimiter | Wait time of the protected call at the application layer |
| Request/gateway deadline | Total request processing time, possibly spanning multiple dependencies and retries |

Client timeouts should generally expire before or align with TimeLimiter so sockets and connections are released. The gateway deadline must cover internal processing while staying within what the caller accepts.

With `Future`, the caller thread is blocked while waiting. With `CompletionStage`, the caller can continue asynchronously, yet workers and connections remain held if the source task does not stop. Use a Bulkhead to cap concurrent running tasks, monitor queues, and reject early when the system is out of capacity.

## 9. Monitoring and verification

Resilience4j emits `SUCCESS`, `ERROR`, and `TIMEOUT` events for TimeLimiter. With Actuator and `resilience4j-micrometer`, you can monitor metrics such as `resilience4j.timelimiter.calls` by instance name and outcome type. Correlate metrics with timeout counts, fallback counts, and tasks still running in the executor.

A verification scenario should cover both API styles:

1. Create a task that finishes faster than the timeout; verify the Future path returns the result and CompletionStage completes normally.
2. Create a task slower than the timeout; verify the Future path throws `TimeoutException` after the deadline and inspect Future status/interrupt flag.
3. Repeat the Future path with `cancelRunningFuture: false`; verify the caller stops waiting while the source task can still finish afterward.
4. Test the CompletionStage path; verify the method returns a stage immediately, the stage errors with timeout, and check whether the source task keeps running.
5. Combine with Circuit Breaker; verify timeouts are recorded as errors, fallback does not mask errors before the breaker updates stats, and the circuit transitions state upon reaching thresholds.
6. Inspect the executor, scheduler, connection pool, and Bulkhead under concurrent load to detect work left behind after timeouts.

In tests, you can wait for results with `Future.get` or `CompletionStage.toCompletableFuture().get` to assert completion timing. Use blocking operations like this only in tests or at intentional synchronous boundaries; do not introduce them into the application's asynchronous flow.

## 10. Common mistakes

- Using `Future.get()` and forgetting that the calling thread is blocked for the entire wait.
- Assuming `TimeLimiter` automatically spawns a worker thread to run a blocking call.
- Using CompletionStage's scheduler as an I/O executor; the scheduler should only handle short timeout tasks.
- Wrapping a blocking call in `CompletableFuture.completedFuture(...)`, causing work to run before the stage is created.
- Assuming `cancelRunningFuture: true` guarantees every source task stops immediately; `Future.cancel(true)` only sends an interrupt and CompletionStage has no source-task cancellation guarantee.
- Applying a fallback before Circuit Breaker, causing timeouts to be converted into successes and not recorded as errors.
- Using `@TimeLimiter` on a method that does not return CompletionStage/CompletableFuture or calling it internally so Spring AOP does not apply.
- Setting TimeLimiter longer than the gateway timeout or too short compared to the dependency SLA.
- Failing to shut down executors and schedulers when the application shuts down.

## References

- [Resilience4j – TimeLimiter](https://resilience4j.readme.io/docs/timeout): `TimeLimiterConfig`, `Future`, `CompletionStage`, scheduler, and how to decorate calls.
- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): instance configuration, `@TimeLimiter` annotation, fallback, and metrics.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): per-instance TimeLimiter configuration, Customizer, and factory integration.
- [Java – CompletionStage](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html): asynchronous processing contract and callback chaining.
- [Java – Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): retrieving results, timeouts, and cancellation.
