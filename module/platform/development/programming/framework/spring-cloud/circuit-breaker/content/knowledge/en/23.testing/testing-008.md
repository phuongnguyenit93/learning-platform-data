# Testing Fallbacks, Timeouts, and Tasks Still Running After Expiration

## Lesson Objectives

When a dependent service is slow or unavailable, the application often must return a fallback or terminate the request with a timeout. However, the caller receiving a timeout does not prove that the underlying work has stopped. An HTTP client may still be reading from a socket, a blocking task may still occupy a worker thread, or a remote server may have already executed a write operation before the connection was closed.

Circuit breaker testing therefore needs to observe multiple layers: the outcome returned to the caller, the breaker state, whether the fallback was called, how many requests were actually sent, and the state of background tasks after a timeout.

After this lesson, you will be able to:

- Test fallbacks when calls fail and when the breaker is OPEN.
- Distinguish HTTP client timeouts, TimeLimiter, and Reactor timeouts.
- Verify the composition order of TimeLimiter and CircuitBreaker so timeouts are recorded accurately.
- Use latches and synchronization signals to test blocking tasks still running after the caller expires.
- Verify that cancellation was issued and determine whether actual work has finished.
- Verify that fallbacks do not mask programming errors or write fallback data into the authoritative cache.
- Design stable tests with proper cleanup that do not depend on arbitrary wait durations.

## 1. A Single Timeout Has Multiple Outcomes to Check

Suppose `order-service` calls `inventory-service` to check stock. The call exceeds an 800 ms deadline. The caller may experience one of the following outcomes:

1. The HTTP client times out and terminates the client-side I/O operation.
2. TimeLimiter completes the CompletionStage with a `TimeoutException` and requests Future cancellation.
3. Reactor timeout emits an error signal and sends cancellation upstream to the source publisher.
4. The caller receives a timeout, yet the underlying blocking task keeps running.
5. The remote server has already received and processed the request, but the response arrives late so the caller never receives the result.

These outcomes are not equivalent. A test that only checks that a response arrives within 800 ms is not enough to prove resources were released.

| What to verify | Testing question |
| --- | --- |
| Caller outcome | Does the caller receive primary data, a fallback, or a timeout exception? |
| Circuit breaker | Was the call a success, failure, slow call, or rejected? |
| Fallback | Was the fallback called exactly once and did it return the appropriate status? |
| HTTP client | Did the connection or response time out as configured? |
| Background task | Has the actual Callable, Future, or request completed? |
| Side effects | Could the server have written data even though the caller timed out? |

A good test clearly identifies which layer's contract is under test. Unit tests can verify fallback decisions; integration tests verify HTTP timeouts and the circuit breaker; thread-controlled tests check tasks still running after the caller expires.

## 2. Isolating Fallback Policy for Independent Testing

Fallbacks often contain cause-classification logic: breaker is OPEN, dependency timed out, HTTP 5xx error, or non-recoverable errors. Extract this decision into a small component so it can be tested independently.

Example:

    public class InventoryFallbackPolicy {

        public InventoryResponse apply(String sku, Throwable error) {
            if (hasCause(error, CallNotPermittedException.class)) {
                return InventoryResponse.unavailable(sku);
            }

            if (hasCause(error, TimeoutException.class)
                    || hasCause(error, ResourceAccessException.class)) {
                return InventoryResponse.unknown(sku);
            }

            throw new InventoryLookupException(
                "Cannot determine inventory for " + sku,
                error
            );
        }

        private boolean hasCause(Throwable error, Class<?> type) {
            Throwable current = error;
            while (current != null) {
                if (type.isInstance(current)) {
                    return true;
                }
                current = current.getCause();
            }
            return false;
        }
    }

The `InventoryResponse` and `InventoryLookupException` types are application-defined components. Exception classification must match the HTTP client and library version in use. Avoid catching every `Throwable` and returning a default value, as programming errors or data errors could be masked.

Unit tests for the policy should cover:

- `CallNotPermittedException` produces the `UNAVAILABLE` state.
- `TimeoutException` produces the `UNKNOWN` state.
- `ResourceAccessException` is handled per the connection-error policy.
- `IllegalArgumentException` or validation errors are not turned into fake inventory results.
- Exceptions wrapped inside `CompletionException` or `ExecutionException` are still classified via the cause chain.

JUnit example:

    class InventoryFallbackPolicyTest {

        private final InventoryFallbackPolicy policy =
            new InventoryFallbackPolicy();

        @Test
        void breakerOpenReturnsUnavailable() {
            CircuitBreaker breaker = CircuitBreaker.ofDefaults("inventory");
            Throwable error =
                CallNotPermittedException.createCallNotPermittedException(breaker);

            InventoryResponse result = policy.apply("SKU-42", error);

            assertEquals(Availability.UNAVAILABLE, result.availability());
        }

        @Test
        void timeoutReturnsUnknown() {
            InventoryResponse result =
                policy.apply("SKU-42", new TimeoutException("deadline exceeded"));

            assertEquals(Availability.UNKNOWN, result.availability());
        }

        @Test
        void programmingErrorIsNotConvertedToFallback() {
            assertThrows(
                InventoryLookupException.class,
                () -> policy.apply("SKU-42", new IllegalArgumentException("bad input"))
            );
        }
    }

If your Resilience4j version uses a different factory method or constructor for `CallNotPermittedException`, adjust the exception creation to match the actual dependency. The goal of the unit test is to verify the application's policy, not lock the test into an unstable exception instantiation API.

## 3. Testing That an OPEN Breaker Does Not Call the Dependency

When the breaker is OPEN, new calls must be rejected before the Supplier executes. This is an essential property to confirm that the circuit breaker protects the dependency.

You can test directly with Resilience4j:

    @Test
    void openBreakerRejectsCallBeforeSupplierRuns() {
        CircuitBreaker breaker = CircuitBreaker.ofDefaults("inventory");
        breaker.transitionToOpenState();

        AtomicBoolean supplierInvoked = new AtomicBoolean(false);

        assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(() -> {
                supplierInvoked.set(true);
                return "inventory";
            })
        );

        assertFalse(supplierInvoked.get());
        assertEquals(
            CircuitBreaker.State.OPEN,
            breaker.getState()
        );
    }

This test verifies the behavior of the Resilience4j breaker. In an application integration test, verify that the factory or Feign integration uses the same breaker instance/configuration that the test opened; do not open a separate registry and assume the application's bean is also OPEN.

For a gateway using Spring Cloud CircuitBreaker, also verify:

- The fallback is invoked when the breaker rejects the call.
- The mock HTTP server receives no additional requests once the breaker is OPEN.
- The fallback result carries the `UNKNOWN` or `UNAVAILABLE` status per contract.
- Metrics or events record an increase in rejected calls.
- When the breaker transitions to `HALF_OPEN`, only the permitted number of probe calls execute per configuration.

So tests do not depend on arbitrary timing and thresholds, you can configure the test breaker with a small `minimumNumberOfCalls` and clear thresholds, or control state through the registry in tests. Do not use long production settings that force tests to wait several seconds to open the breaker.

## 4. Testing Fallbacks After HTTP Errors

Use a mock HTTP server such as WireMock or MockWebServer to control responses. For an inventory read call, create these scenarios:

| Mocked response | Outcome to verify |
| --- | --- |
| HTTP 200 with valid JSON | Returns primary data; fallback is not invoked. |
| HTTP 500 | Handled per server-error policy; fallback is invoked if this error belongs to the allowed group. |
| Connection closed | Client raises a connection error; fallback or exception is handled properly. |
| Response slower than deadline | Timeout occurs; fallback or timeout error is returned per contract. |
| HTTP 404 | Handled per API semantics; do not automatically serve stale cache if 404 means the resource does not exist. |

Example testing a gateway with a mock server:

    @Test
    void serverErrorUsesFallback() {
        wireMock.stubFor(
            get(urlEqualTo("/inventory/SKU-42"))
                .willReturn(aResponse().withStatus(503))
        );

        InventoryResponse result = inventoryGateway.find("SKU-42");

        assertEquals(Availability.UNKNOWN, result.availability());

        wireMock.verify(
            1,
            getRequestedFor(urlEqualTo("/inventory/SKU-42"))
        );
    }

This test assumes the gateway is configured to use the `UNKNOWN` fallback for 503 errors. If the gateway returns a `CompletionStage` or `Mono`, wait for the result using the corresponding test API instead of blocking arbitrarily on an event loop. In reactive tests, use `StepVerifier`.

Verify the request count on the mock server. A successful fallback does not prove only one request was sent; retries may have generated multiple attempts. When testing a circuit breaker, record both logical call counts and HTTP attempt counts.

## 5. Distinguishing HTTP Client, TimeLimiter, and Reactor Timeouts

Different timeouts control different scopes:

| Timeout | Scope | What to test |
| --- | --- | --- |
| Connect timeout | Establishing connection to server. | If connection does not finish within the limit, the client reports an error. |
| Response/read timeout | Waiting for response or data per HTTP client capabilities. | Client stops waiting per config; check whether the socket/request is released. |
| Resilience4j TimeLimiter | Wrapped CompletionStage/Future. | Caller receives timeout; check `cancelRunningFuture` and actual task status. |
| Reactor timeout | Publisher does not emit a signal within the specified duration. | Publisher emits `TimeoutException` and sends cancellation upstream. |
| CircuitBreaker slowCallDurationThreshold | Classifying slow calls in statistics. | Breaker records slow call; does not cancel the call by default. |

Do not use a single test to prove all timeouts work. For example, `Mono.timeout` can cause the publisher to emit an error while the HTTP connector has its own separate timeout configuration. Conversely, `TimeLimiter` can complete the caller-side `CompletionStage` while blocking work inside an executor keeps running.

For each timeout, note the start time, the moment the caller receives the result, and the moment the actual task finishes. These three timestamps help detect work left running past the deadline.

## 6. Testing TimeLimiter and Blocking Tasks Still Running

An important case is when `TimeLimiter` expires yet blocking work does not stop. `CompletableFuture.cancel(true)` does not guarantee that a running task is interrupted; many blocking APIs also do not respond to interrupts or only stop upon socket timeout.

You can test this using `CountDownLatch` instead of `Thread.sleep`. Latches let the test precisely control when the task starts and when it is allowed to finish.

JUnit example with Resilience4j TimeLimiter:

    @Test
    void callerTimesOutWhileBlockingTaskIsStillRunning() throws Exception {
        ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
        ScheduledExecutorService timeoutScheduler =
            Executors.newSingleThreadScheduledExecutor();

        CountDownLatch taskStarted = new CountDownLatch(1);
        CountDownLatch allowTaskToFinish = new CountDownLatch(1);
        CountDownLatch taskFinished = new CountDownLatch(1);

        TimeLimiter limiter = TimeLimiter.of(
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofMillis(100))
                .cancelRunningFuture(true)
                .build()
        );

        try {
            Supplier<CompletionStage<String>> source = () ->
                CompletableFuture.supplyAsync(() -> {
                    taskStarted.countDown();
                    try {
                        allowTaskToFinish.await();
                        return "completed";
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        throw new CompletionException(error);
                    } finally {
                        taskFinished.countDown();
                    }
                }, ioExecutor);

            CompletionStage<String> result =
                limiter.executeCompletionStage(timeoutScheduler, source);

            assertTrue(taskStarted.await(1, TimeUnit.SECONDS));

            ExecutionException timeout = assertThrows(
                ExecutionException.class,
                () -> result.toCompletableFuture().get(1, TimeUnit.SECONDS)
            );

            assertTrue(timeout.getCause() instanceof TimeoutException);
            assertEquals(1L, taskFinished.getCount());

        } finally {
            allowTaskToFinish.countDown();
            assertTrue(taskFinished.await(1, TimeUnit.SECONDS));
            ioExecutor.shutdownNow();
            timeoutScheduler.shutdownNow();
        }
    }

In this test:

- `taskStarted` confirms the task actually started before checking the timeout.
- `TimeLimiter` completes the caller-side stage with a timeout after 100 ms.
- `allowTaskToFinish` has not been opened yet, so the task is waiting and has not finished.
- The test verifies that `taskFinished` has not been counted down at the moment the caller timed out.
- `finally` releases the latch so no blocked worker is left behind.

The example assumes the executor and scheduler are created for the test and closed in `finally`. In a Spring application, manage executors as shared beans with appropriate thread and queue bounds. Never create a new executor per request.

This result illustrates a key point: `TimeLimiter` can finish the caller's wait, but cancelling the Future does not mean the blocking work has stopped. Some Futures or libraries have better cancellation support; verify the specific behavior of the client you use.

## 7. Checking Whether the Task Actually Stops After Cancellation

When testing timeouts, record at least three signals:

1. The caller received the timeout.
2. Cancellation was requested or emitted.
3. Work in the execution layer completed and released resources.

With Reactor, you can record the cancel signal using `doFinally`:

    Mono<String> task = Mono.fromCallable(() -> blockingClient.call())
        .subscribeOn(Schedulers.boundedElastic())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancellationCounter.increment();
            }
        })
        .timeout(Duration.ofMillis(200));

`doFinally` with `SignalType.CANCEL` shows that the publisher received the cancellation signal. It does not prove that `blockingClient.call` stopped executing. To verify that, you need a separate signal at the end of the task, such as a `CountDownLatch`, `AtomicBoolean`, or an active-tasks gauge metric.

If the blocking library supports interrupts, the test can observe `InterruptedException`. However, do not expect every library to respond to interrupts. Some APIs finish only when a socket times out, a transaction completes, or the underlying call returns.

When work continues running after a timeout, examine:

- How long is the worker thread still occupied?
- Is the HTTP connection released or still held in the pool?
- How long is the bulkhead permit held?
- Does the task continue writing to the database or producing side effects?
- Can a timeout be set directly on the client or lower-level API to actually stop the work?
- Is concurrency limiting needed so expired tasks do not accumulate?

Do not count only caller-side timeouts. Observe the actual number of tasks still running past the deadline.

## 8. Testing Reactor Timeouts with StepVerifier

In reactive pipelines, `StepVerifier` lets you test timeouts without waiting long in real time. Use virtual time for publishers built on Reactor's time scheduler:

    @Test
    void reactorTimeoutEmitsTimeoutException() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(5))
                    .thenReturn("inventory")
                    .timeout(Duration.ofSeconds(1))
            )
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify();
    }

Virtual time allows tests to finish quickly and deterministically. `Mono.delay` uses a scheduler that `StepVerifier` can control. With a real HTTP client, do not assume virtual time controls sockets or network response times. Use a mock server with controlled delays and real connector timeouts for integration tests.

You can test a fallback after a timeout:

    @Test
    void timeoutUsesFallbackAfterProtectedPublisher() {
        StepVerifier.withVirtualTime(() ->
                Mono.<InventoryResponse>never()
                    .timeout(Duration.ofSeconds(1))
                    .onErrorResume(
                        TimeoutException.class,
                        error -> Mono.just(InventoryResponse.unknown("SKU-42"))
                    )
            )
            .thenAwait(Duration.ofSeconds(1))
            .assertNext(response ->
                assertEquals(Availability.UNKNOWN, response.availability())
            )
            .verifyComplete();
    }

In a real application, `CircuitBreakerOperator` must sit before the fallback so it records the timeout. Example order:

    Mono<InventoryResponse> protectedCall = primary
        .timeout(Duration.ofMillis(800))
        .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.just(InventoryResponse.unknown(sku))
        );

If the fallback is placed before the breaker and converts the error into a success value, the breaker may never see the timeout. Write tests that verify the failure count or corresponding event after a timeout.

## 9. Testing the Order of TimeLimiter and CircuitBreaker

When using `CompletionStage`, wrap the source with `TimeLimiter` first, then let `CircuitBreaker` observe the time-limited `CompletionStage`:

    Supplier<CompletionStage<InventoryResponse>> source = () ->
        CompletableFuture.supplyAsync(
            () -> blockingClient.find(sku),
            ioExecutor
        );

    Supplier<CompletionStage<InventoryResponse>> timedSource = () ->
        timeLimiter.executeCompletionStage(timeoutScheduler, source);

    Supplier<CompletionStage<InventoryResponse>> protectedCall =
        CircuitBreaker.decorateCompletionStage(circuitBreaker, timedSource);

    return protectedCall.get();

With this composition, the timeout emitted by `TimeLimiter` is the error outcome observed by `CircuitBreaker`. Tests should verify:

- The caller receives `TimeoutException` within the expected duration.
- The breaker's failure metric increases according to the exception configuration.
- After enough samples, the breaker can transition to OPEN.
- When the breaker is OPEN, the source does not launch additional tasks.
- The fallback is invoked after the outcome is determined to be a timeout or call not permitted.

If `TimeLimiter` is placed outside the breaker, the caller still receives a timeout, yet the breaker may not record the timeout as intended. Explicitly define which wrapper observes which outcome and verify with events/metrics rather than checking only the response.

Illustrative Resilience4j configuration:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 4
            minimumNumberOfCalls: 2
            failureRateThreshold: 50
            waitDurationInOpenState: 2s
      timelimiter:
        instances:
          inventory:
            timeoutDuration: 300ms
            cancelRunningFuture: true

This configuration is for testing, with a small window to open the breaker quickly. Do not copy these values verbatim into production without evaluating traffic, SLOs, and dependency characteristics.

## 10. Testing That Fallbacks Neither Mask Errors Nor Corrupt Cache

A fallback should handle only errors that business rules permit recovering from. Include tests confirming that programming errors and invalid data still propagate upward.

If using a cache as a fallback, verify separately:

- Normal cache hits do not call the primary service if policy permits.
- When the primary service times out, only cache entries within the stale window are used.
- When the cache expires, an error or unavailable status is returned per contract.
- Fallback results do not overwrite the authoritative cache.
- When the service recovers, fresh primary data is written to the cache.
- Cache keys do not leak data across tenants or users.

Example test verifying that fallback values are not written to the authoritative cache:

    @Test
    void fallbackValueIsNotStoredAsAuthoritativeData() {
        InventoryResponse fallback =
            InventoryResponse.unknown("SKU-42");

        InventoryResponse result = gateway.applyFallback(
            "SKU-42",
            new TimeoutException("deadline exceeded")
        );

        assertEquals(fallback.availability(), result.availability());
        verify(productCache, never()).putAuthoritative(any());
    }

This example assumes authoritative cache writes occur in the success branch of the primary source, while fallback is a separate branch. If existing code places the cache write after merging primary and fallback, this test will catch fallback data being stored by mistake.

## 11. Testing Timeouts with Write Operations and Idempotency

A timeout does not tell you whether the server executed the write operation. For example, `order-service` sends an inventory reservation command. `inventory-service` may have already updated the quantity, yet the response was lost or arrived past the deadline. The caller receives a timeout and does not know the final outcome.

Do not automatically resend write commands simply because the caller timed out. Tests should simulate the scenario:

1. The server receives the request and commits the operation.
2. The server delays the response past the deadline.
3. The caller receives a timeout.
4. The client retries with the same idempotency key.
5. The server returns the previous operation's result or avoids applying the side effect a second time.

What to verify:

- The same idempotency key does not create two reservations.
- Operation status can be queried after a timeout.
- Fallbacks do not assert that the operation failed when the actual outcome is undetermined.
- Retries stay within defined limits and semantics.
- Logs/traces share the same operation ID to correlate the initial request and retry attempt.

This is a critical test for payments, order creation, inventory reservations, email sending, or other operations with side effects.

## 12. Making Tests Stable and Cleaning Up Resources

Timeout tests are prone to flakiness when using `Thread.sleep` and assuming schedulers always fire at an exact moment. Prefer:

- `CountDownLatch` or `Phaser` to control task start and completion points.
- `StepVerifier.withVirtualTime` for Reactor time operators.
- A mock HTTP server to control response delays and request counts.
- Wait timeouts in tests to prevent tests from hanging indefinitely.
- `finally` blocks to release latches, close servers, and shut down executors.
- Controllable clocks or schedulers if application code allows injection.
- Dedicated test breaker configurations to avoid depending on state from other tests.

Do not share a mutable `CircuitBreakerRegistry` across tests without resetting state. One test opening a breaker can cause the next test to receive `CallNotPermittedException` even when it expects to call the server. Create a separate instance per test or reset explicitly in teardown.

When running tests in parallel, avoid sharing the same server port, the same breaker name in a shared registry, or the same cache key if tests can affect one another. Create isolated fixtures and clean up even when assertions fail.

## 13. Recommended Testing Matrix

You can use the following matrix as a checklist for the inventory gateway:

| Case | What does the caller receive? | Does Supplier/server run? | What should the breaker record? |
| --- | --- | --- | --- |
| Fast success | Primary data | Yes | Success |
| HTTP 503 | Fallback or error per policy | Yes | Error if exception is recorded |
| Breaker OPEN | Fallback unavailable | No | Call not permitted |
| HTTP client timeout | Fallback unknown or timeout error | Request was sent; client stops as capable | Error/timeout per policy |
| TimeLimiter expires, task not interrupted | Caller timeout | Task may still be running | Timeout error |
| Reactor timeout | Timeout or fallback | Publisher receives cancellation; blocking source may continue | Error if breaker wraps timeout |
| Bulkhead out of permits | Busy/fallback | New task is not executed | Bulkhead rejection; do not confuse with breaker OPEN |
| Stale cache used | Data with STALE metadata | Primary may have been called and failed | Breaker records error before fallback |
| Server writes data then response times out | Undetermined result or status lookup | Side effect may have already happened | Timeout/error; retry requires idempotency |

This matrix keeps test authors from stopping at the final response. Verify invocation counts, breaker state, and work still running after a timeout as well.

## 14. Comprehensive Practice Exercise

Build an `InventoryGateway` with HTTP calls to `inventory-service`, `CircuitBreaker`, `TimeLimiter`, and fallback. Carry out the following:

1. Write unit tests for `InventoryFallbackPolicy` with `CallNotPermittedException`, `TimeoutException`, and programming errors.
2. Using a dedicated test breaker, transition the breaker to OPEN and verify the Supplier does not execute.
3. Use a mock HTTP server to return 200, 503, connection close, and delayed responses.
4. Configure an HTTP client timeout, then verify the caller receives the expected error type.
5. Create a `CompletionStage` running a blocking task on a dedicated executor and wrap it with `TimeLimiter`.
6. Use `CountDownLatch` to verify the caller timed out while `taskFinished` has not yet occurred.
7. Release the latch in `finally` and verify the worker finishes so the test does not leak threads.
8. Wrap the timed `CompletionStage` with `CircuitBreaker` and verify the failure metric increases.
9. Trigger enough timeouts for the breaker to OPEN; verify subsequent requests do not launch new tasks.
10. For a `WebClient` pipeline, use `StepVerifier` to verify `Mono.timeout` and fallback after `CircuitBreakerOperator`.
11. Test a write operation with an idempotency key and simulate the server completing before the response times out.
12. Inspect logs, metrics, request counts, and tasks still running past the deadline.

Upon completion, you should be able to answer whether the caller received a timeout, whether cancellation was sent, whether the actual task stopped, and whether the breaker recorded the timeout. These are four distinct questions. Thorough testing uncovers situations where a request has ended while workers, connections, or side effects persist past the deadline.

## References

- Resilience4j TimeLimiter: https://resilience4j.readme.io/docs/timeout
- Resilience4j CircuitBreaker: https://resilience4j.readme.io/docs/circuitbreaker
- Reactor Reference — Handling Errors and Cancellation: https://projectreactor.io/docs/core/release/reference/
- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
