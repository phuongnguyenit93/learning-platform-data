# Verifying That OPEN Does Not Call the Dependent System Again

When a circuit breaker is in the `OPEN` state, every new synchronous call passing through the breaker must be rejected before the supplier executes. This ensures the application stops calling a degraded dependent service while the circuit remains open. To prove this behavior, you must check how many times calls actually reach the client or dependent system while also verifying that the application still handles requests via the fallback.

A test that only asserts the method returns a fallback value is not enough. A fallback could return the expected value while the supplier is still being invoked underneath. The critical evidence is that the dependency call count does not increase after the breaker has opened.

## 1. Behavior of Synchronous Calls When the Breaker Is OPEN

In the `CLOSED` state, the circuit breaker allows the supplier to call the dependent service and records the outcome. When the failure rate or slow call rate reaches its threshold after collecting at least the minimum number of samples, the breaker transitions to `OPEN`. During this period, new calls are rejected immediately at the breaker:

1. Business code receives a synchronous request.
2. The circuit breaker checks its current state.
3. If the state is `OPEN`, the breaker skips executing the supplier and throws `CallNotPermittedException`.
4. The integration layer or business code can handle the rejection error with a fallback.
5. The fallback result is returned to the caller; the dependent service receives no further requests from that supplier.

```text
Synchronous request
       |
       v
Circuit breaker
       |
       +---- CLOSED ----> Supplier ----> HTTP/RPC client ----> Dependency
       |
       +---- OPEN ------> Fail fast
                              |
                              v
                           Fallback
                              |
                              v
                       Result for caller
```

`OPEN` only prevents new calls passing through the breaker. Calls already permitted before the breaker opened may still be running and finish later. The circuit breaker does not automatically abort in-flight requests. Therefore, tests must distinguish new calls made after opening from calls that started beforehand.

## 2. Preparing a Reproducible Test Configuration

To prevent tests from depending on random traffic, use a small count-based window and a fixed minimum number of calls. For example, place configuration in `src/test/resources/application-test.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 2
        minimumNumberOfCalls: 2
        failureRateThreshold: 50
        waitDurationInOpenState: 1m
        permittedNumberOfCallsInHalfOpenState: 1
```

With this configuration, two consecutive failed calls produce a 100% failure rate in a window of two calls, exceeding the 50% threshold and tripping the breaker to `OPEN`. `waitDurationInOpenState: 1m` keeps the breaker open long enough to test subsequent calls without accidentally transitioning to `HALF_OPEN`.

In production, avoid such a tiny window unless real traffic characteristics justify it. This configuration is specifically for tests; production settings must be based on traffic volume, latency, and service protection goals.

## 3. Testing the Native Resilience4j API with a Call Counter

With the native API, you can construct a circuit breaker directly from `CircuitBreakerConfig`. A counter placed inside the supplier reveals how many times the dependency was actually invoked:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class InventoryCircuitBreakerTest {

    @Test
    void doesNotInvokeDependencyAgainWhileOpen() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
        AtomicInteger dependencyCalls = new AtomicInteger();

        // Two recorded failures transition the breaker to OPEN.
        for (int i = 0; i < 2; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(() -> {
                dependencyCalls.incrementAndGet();
                throw new IllegalStateException("inventory unavailable");
            })).isInstanceOf(IllegalStateException.class);
        }

        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(dependencyCalls.get()).isEqualTo(2);

        // The third call is rejected before the supplier runs.
        assertThatThrownBy(() -> breaker.executeSupplier(() -> {
            dependencyCalls.incrementAndGet();
            return "inventory response";
        })).isInstanceOf(CallNotPermittedException.class);

        assertThat(dependencyCalls.get()).isEqualTo(2);
    }
}
```

The test establishes two separate pieces of evidence: the breaker state is `OPEN`, and the dependency counter remains at `2` after the third call. If the supplier had executed, the counter would have risen to `3`. `CallNotPermittedException` confirms the breaker rejected the call at the protection layer.

In a real project, place the counter at the HTTP/RPC call boundary or use a mock to verify the client method. Do not count only calls to the service facade, since the facade is still invoked when the breaker is open; what must be verified is that the dependent client is not called again.

## 4. Testing the Client with Mockito

When a service uses an injected client, Mockito can verify the exact number of times the client method is invoked. Example test logic includes these steps:

```java
// Assume inventoryClient.fetch(...) throws an exception on the first two calls.
for (int i = 0; i < 2; i++) {
    InventoryResult result = inventoryService.getInventory("SKU-1");
    assertThat(result.isUnavailable()).isTrue();
}

verify(inventoryClient, times(2)).fetch("SKU-1");

// Breaker is OPEN; the new call only executes the fallback.
InventoryResult result = inventoryService.getInventory("SKU-1");

assertThat(result.isUnavailable()).isTrue();
verify(inventoryClient, times(2)).fetch("SKU-1");
verifyNoMoreInteractions(inventoryClient);
```

This snippet assumes `inventoryService` uses the same breaker ID `inventory` throughout the test, the fallback returns `InventoryResult.unavailable(...)`, and the client was stubbed so the first two calls fail. Common Mockito imports:

```java
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
```

If the client is called by another component in the same test, `verifyNoMoreInteractions(...)` may fail due to interactions outside the scope under test. In that case, verify only the exact method call count with `times(2)` or call `clearInvocations(...)` at the appropriate boundary. The key is that the final assertion still proves the dependency call count does not increase after the breaker opens.

## 5. Testing via Spring Cloud CircuitBreaker Factory

When an application uses Spring Cloud's abstraction backed by Resilience4j, test through `CircuitBreakerFactory` to verify both wiring and fallback behavior. Activate the `test` profile to apply the configuration from earlier:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.test.context.ActiveProfiles;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class InventorySpringCloudCircuitBreakerTest {

    @Autowired
    CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    @Test
    void factoryFallbackDoesNotInvokeDependencyWhenOpen() {
        CircuitBreaker breaker = circuitBreakerFactory.create("inventory");
        AtomicInteger dependencyCalls = new AtomicInteger();
        AtomicReference<Throwable> lastFallbackCause = new AtomicReference<>();

        for (int i = 0; i < 2; i++) {
            String result = breaker.run(() -> {
                dependencyCalls.incrementAndGet();
                throw new IllegalStateException("inventory unavailable");
            }, error -> {
                lastFallbackCause.set(error);
                return "fallback";
            });

            assertThat(result).isEqualTo("fallback");
        }

        assertThat(dependencyCalls.get()).isEqualTo(2);

        String result = breaker.run(() -> {
            dependencyCalls.incrementAndGet();
            return "inventory response";
        }, error -> {
            lastFallbackCause.set(error);
            return "fallback";
        });

        assertThat(result).isEqualTo("fallback");
        assertThat(dependencyCalls.get()).isEqualTo(2);
        assertThat(lastFallbackCause.get())
            .isInstanceOf(io.github.resilience4j.circuitbreaker.CallNotPermittedException.class);
    }
}
```

The factory creates a breaker with ID `inventory`, matching the YAML configuration. On the first two calls, the supplier executes and throws an exception; the fallback returns the string `"fallback"`. On the third call, the breaker is `OPEN`, so the fallback receives the rejection error and the supplier does not increment the counter. This test requires the Spring Cloud CircuitBreaker Resilience4j starter and the `test` profile configuration loaded into the Spring test context.

If your project does not expose the fallback cause or wraps it in a separate adapter layer, assert both the fallback result and the client call count at the service boundary. Do not create a separate standalone `CircuitBreakerRegistry` just to read state and assume it is the same instance used by the factory.

## 6. Ensuring the Fallback Does Not Call the Dependency Again

The breaker controls only the wrapped supplier. If the fallback directly invokes the same HTTP client again, that call sits outside the protected boundary and can still hit the dependent service while the breaker is `OPEN`.

Example to avoid:

```java
return breaker.run(
    () -> inventoryClient.fetch(sku),
    error -> inventoryClient.fetchFromPrimaryAgain(sku)
);
```

Here, the fallback calls another endpoint on the same dependency. Although the original supplier does not run when the breaker is open, the fallback still issues a new request. A safer fallback can read from a local cache, return a controlled unavailable state, or use a separately designed independent backup source:

```java
return breaker.run(
    () -> inventoryClient.fetch(sku),
    error -> inventoryCache.find(sku)
        .orElseGet(() -> InventoryResult.unavailable(sku))
);
```

When testing, place mocks or counters on every client capable of reaching the same dependent system, including any client used by the fallback. That way, tests catch cases where the supplier does not run yet the fallback bypasses protection through another client.

## 7. Factors That Can Skew Test Results

| Factor | Why Results Become Misleading | How to Control It |
| --- | --- | --- |
| Creating a new breaker per call | Each instance has separate state and never accumulates enough failures to open | Create the breaker once for the test and reuse the same instance |
| Sharing a registry across multiple tests | `OPEN` state from an earlier test leaks into later tests | Create a fresh instance or reset the registry per test fixture |
| Not reaching `minimumNumberOfCalls` | Failure rate has not been evaluated yet | Set a small, fixed window and minimum call count in the test profile |
| Waiting longer than `waitDurationInOpenState` | Breaker can transition to `HALF_OPEN` and permit trial calls | Use a sufficiently long open duration and assert immediately after opening |
| Having Retry wrapped around the client | A single business request can trigger multiple dependency calls while the breaker is closed | Verify decorator ordering and Retry configuration in tests |
| Fallback calling the same dependency | Supplier is blocked, yet fallback still sends requests | Use cache or an independent backup source; count calls across all clients |
| Checking at the wrong layer | The service facade still receives requests even though the client was never called | Place `verify` on the HTTP/RPC client method or transport boundary |
| Unsynchronized concurrency tests | Calls permitted before opening may still be executing | Use latches/barriers and distinguish in-flight requests from new ones |

In particular, when Retry is present, understand the wrapping order. When the circuit breaker is `OPEN`, the breaker's supplier is not executed. However, if a Retry or fallback sits outside the breaker and is coded to invoke an alternate path, actual request counts can still increase. Testing at the transport boundary gives the clearest proof.

## 8. Verifying HALF_OPEN and the Scope of the Conclusion

After `waitDurationInOpenState` elapses, the breaker can transition to `HALF_OPEN` and permit a number of trial calls configured by `permittedNumberOfCallsInHalfOpenState`. At that point, the dependency is intentionally called again to test recovery. Hence, the statement "OPEN does not call the dependency" holds only while the breaker remains `OPEN`; it does not apply to permitted probes in `HALF_OPEN`.

If you need to test this transition boundary, write a dedicated test: verify calls are rejected during the open window, then advance time or the breaker's clock to transition to `HALF_OPEN`, and confirm that only the permitted number of probes reach the dependency. Avoid arbitrary `Thread.sleep` calls in primary tests because they make timing and state flaky.

For synchronous calls, a request started before the circuit opened may continue running until completion or timeout. The circuit breaker does not automatically cancel that request. To limit resource occupancy duration, configure appropriate timeouts on the HTTP/RPC client or use `TimeLimiter` in an integration model that supports it. `OPEN` tests must count new calls attempted after the state became open, without treating already in-flight requests as new calls.

## 9. Observing Runtime Behavior

In a live environment, combine logs, metrics, and breaker state to verify the system is failing fast. Useful signals include:

- Current circuit breaker state per dependency ID.
- Permitted call counts and success/failure counts.
- Rejected call counts while the breaker is `OPEN`.
- Fallback invocation counts and fallback success rates.
- Business request response times when the dependency is unavailable.

Micrometer and Spring Boot Actuator provide these metrics when the corresponding dependencies and configuration are enabled. Use the exact same breaker ID across YAML, calling code, logs, and dashboards for correlation. Do not infer that the dependency received requests solely from how often the service facade was called; inspect client-side or dependency-side metrics when end-to-end verification is needed.

A solid test proves three things: the breaker genuinely entered `OPEN`, new calls return quickly via fallback or rejection error, and the dependency call count stops increasing. When you need to verify the complete operational flow, add separate tests for `HALF_OPEN`, Retry, timeouts, and fallbacks so each mechanism can be evaluated independently.
