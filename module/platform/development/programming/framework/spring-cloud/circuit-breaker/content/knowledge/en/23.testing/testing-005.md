# Testing That OPEN Does Not Execute the Original Supplier or Publisher

When a Circuit Breaker is in the OPEN state, new calls must be rejected before executing work against the dependency. With the synchronous API, the original Supplier is not invoked. With the reactive API, the original Publisher is not subscribed to. If the application configures a fallback, the fallback still executes to produce an alternative result for the caller.

This is a critical invariant to verify in Spring Cloud CircuitBreaker: once the circuit is open, requests must not continue reaching the downstream service. A test that only checks that the caller receives a fallback is insufficient. A fallback can be returned while the original code still accidentally runs if the processing chain is wired incorrectly. The test must directly observe the invocation count of the Supplier, the subscription count of the Publisher, and, when possible, the number of HTTP requests actually sent.

## 1. Behavior to Verify in the OPEN State

A Circuit Breaker has three main states:

- **CLOSED**: allows calls through to the dependency and records outcomes.
- **OPEN**: fast-rejects new calls. Original work is not executed.
- **HALF_OPEN**: allows a limited number of probe calls to test whether the dependency has recovered.

This test focuses on OPEN. When a call passes through an OPEN Circuit Breaker:

1. The Circuit Breaker checks its state before invoking the original work.
2. The call is rejected with an error such as `CallNotPermittedException` in Resilience4j.
3. If a fallback is present, the fallback function is invoked to produce an alternative result.
4. The original Supplier is not executed; for reactive, the original Publisher is not subscribed to.
5. No new request is sent to the HTTP client from the rejected call.

This can be represented by the following diagram:

~~~mermaid
flowchart TD
    A[Caller invokes through Circuit Breaker] --> B{Breaker state}
    B -- CLOSED --> C[Execute Supplier or subscribe to Publisher]
    B -- HALF_OPEN --> D[Allow probe call if permits remain]
    B -- OPEN --> E[Reject call]
    E --> F{Has fallback?}
    F -- Yes --> G[Execute fallback]
    F -- No --> H[Throw CallNotPermittedException]
    G --> I[Return alternative result]
    C --> J[Outcome from dependency]
    D --> J
~~~

An important distinction: OPEN prevents the original work, not all request code. Fallbacks, logging, metrics, and error handling can still run. Therefore, assertions must target the original Supplier or Publisher rather than expecting every counter to be zero.

## 2. Distinguishing Synchronous Supplier and Reactive Publisher

The two APIs have different ways of determining whether the original work ran:

| Call type | Unit protected by Circuit Breaker | How to prove it did not run |
|---|---|---|
| Synchronous | Supplier<T> | Counter inside the Supplier remains 0 |
| Reactive | Mono<T> or Flux<T> | Counter inside defer remains 0, proving the Publisher was not subscribed to |
| HTTP client | Call creating the request inside Supplier or Publisher | Mock server receives zero requests |

With a Supplier, simply place a counter inside the lambda passed to `run`. If the breaker is OPEN, that lambda is not invoked.

With Reactor, Publishers are typically lazy: constructing a Mono or Flux does not mean the inner work has executed. To inspect the exact execution point, use `Mono.defer` or `Flux.defer` and increment the counter when the Publisher factory is invoked. If the breaker is OPEN, the original Publisher is not subscribed to, so the counter remains 0.

Do not place the side effect being verified outside the Supplier or outside `defer`. Code placed outside may execute before the Circuit Breaker checks its state and cause the test to draw a false conclusion.

## 3. Preparing Tests with Resilience4j

When Spring Cloud CircuitBreaker uses the Resilience4j implementation, you can obtain the core Circuit Breaker from `CircuitBreakerRegistry` to control state in tests.

Typically needed components:

- Spring Cloud CircuitBreaker starter for Resilience4j.
- `CircuitBreakerFactory` for the synchronous API.
- `ReactiveCircuitBreakerFactory` for the reactive API.
- `CircuitBreakerRegistry` to access the corresponding Resilience4j instance.
- JUnit 5 and AssertJ for assertions.
- Reactor Test to verify Mono or Flux.

For example, Maven dependencies for an application using both synchronous and reactive APIs must be chosen according to the corresponding starters. For the reactive part, use the Reactor Resilience4j starter; for the synchronous part, use the standard Resilience4j starter. Manage versions through the Spring Cloud BOM compatible with your project's Spring Boot version.

It is crucial in integration tests that the factory and registry use the same `CircuitBreakerRegistry`. If the test manipulates a different registry from the one used by the factory, transitioning to OPEN will not affect the breaker invoked in the test.

## 4. Opening the Circuit Breaker Deterministically in Tests

It is not necessary to send multiple failing requests and wait for counters to reach the threshold every time you test OPEN behavior. To test solely the invariant that OPEN does not invoke the original work, you can transition the breaker to OPEN directly.

Resilience4j provides a state-transition method:

~~~java
coreBreaker.transitionToOpenState();
~~~

Example retrieving an instance by ID:

~~~java
String breakerId = "inventory-open-supplier-test";

org.springframework.cloud.client.circuitbreaker.CircuitBreaker springBreaker =
        circuitBreakerFactory.create(breakerId);

io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
        circuitBreakerRegistry.circuitBreaker(breakerId);

coreBreaker.transitionToOpenState();
~~~

Create the wrapper from the factory first, then look up the same ID from the registry and transition that instance to OPEN. This lets the test control the exact breaker that Spring Cloud CircuitBreaker will use, provided the injected registry is the registry of the active implementation.

Use a separate ID per test or reset the state after the test so it does not affect other tests. Assert that the state is OPEN right before calling `run`.

Direct state transition is suited for unit tests or integration tests of rejection behavior. Another test can verify the full `CLOSED` to `OPEN` transition caused by the failure rate reaching its threshold. Those two objectives should be separated so tests do not depend on unintended timing or request counts.

## 5. Testing That the Original Supplier Is Not Invoked

The example below uses synchronous Spring Cloud CircuitBreaker. The `supplierCalls` counter increments only if the original Supplier actually executes.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;

import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OpenSupplierCircuitBreakerTest {

    private static final String BREAKER_ID =
            "inventory-open-supplier-test";

    @Autowired
    CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    @Autowired
    CircuitBreakerRegistry circuitBreakerRegistry;

    @Test
    void openBreakerDoesNotInvokeOriginalSupplier() {
        CircuitBreaker springBreaker =
                circuitBreakerFactory.create(BREAKER_ID);

        io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
                circuitBreakerRegistry.circuitBreaker(BREAKER_ID);

        coreBreaker.transitionToOpenState();

        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);

        AtomicInteger supplierCalls = new AtomicInteger();
        AtomicInteger fallbackCalls = new AtomicInteger();

        String result = springBreaker.run(
                () -> {
                    supplierCalls.incrementAndGet();
                    return "inventory-from-remote";
                },
                error -> {
                    fallbackCalls.incrementAndGet();
                    return "inventory-fallback";
                }
        );

        assertThat(result).isEqualTo("inventory-fallback");
        assertThat(supplierCalls.get()).isZero();
        assertThat(fallbackCalls.get()).isEqualTo(1);
        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);
    }
}
~~~

The assertions prove three distinct facts:

- The caller receives the fallback result.
- The original Supplier did not run, because `supplierCalls` stays at 0.
- The fallback ran exactly once.

Do not check only that `result` equals `inventory-fallback`. If you check only the result, the test can miss a bug where the Supplier actually ran and its outcome was later replaced by the fallback.

The ID must match between `factory.create` and `circuitBreakerRegistry.circuitBreaker`. If you use a per-ID configuration, make sure that configuration is loaded in the test context.

## 6. Testing When No Fallback Is Declared

If no fallback is provided, the rejected call must propagate the error to the caller. The original Supplier is still not executed.

~~~java
@Test
void openBreakerRejectsCallWithoutInvokingSupplier() {
    CircuitBreaker springBreaker =
            circuitBreakerFactory.create(BREAKER_ID);

    io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
            circuitBreakerRegistry.circuitBreaker(BREAKER_ID);

    coreBreaker.transitionToOpenState();

    AtomicInteger supplierCalls = new AtomicInteger();

    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            springBreaker.run(() -> {
                supplierCalls.incrementAndGet();
                return "remote";
            })
    ).satisfies(error ->
            assertThat(hasCause(
                    error,
                    io.github.resilience4j.circuitbreaker.CallNotPermittedException.class
            )).isTrue());

    assertThat(supplierCalls.get()).isZero();
}
~~~

The `hasCause` helper can walk the cause chain in case an adapter wraps the exception:

~~~java
private static boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {

    Throwable current = error;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }

        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    return false;
}
~~~

In some adapters, the exception may be propagated directly; in others, it may be wrapped. Inspecting the cause chain keeps the assertion focused on the actual rejection cause rather than depending on a specific wrapper.

If the API or version in use has different overloads, preserve the same testing goal: the rejection error is propagated to the caller and the original Supplier counter is 0.

## 7. Testing That the Original Publisher Is Not Subscribed To

With a reactive Circuit Breaker, creating a Mono does not prove the Publisher ran. Use `Mono.defer` so the counter increments only when there is a subscription to the original work.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;

import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OpenReactiveCircuitBreakerTest {

    private static final String BREAKER_ID =
            "inventory-open-publisher-test";

    @Autowired
    ReactiveCircuitBreakerFactory<?, ?> reactiveCircuitBreakerFactory;

    @Autowired
    CircuitBreakerRegistry circuitBreakerRegistry;

    @Test
    void openBreakerDoesNotSubscribeToOriginalPublisher() {
        ReactiveCircuitBreaker reactiveBreaker =
                reactiveCircuitBreakerFactory.create(BREAKER_ID);

        io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
                circuitBreakerRegistry.circuitBreaker(BREAKER_ID);

        coreBreaker.transitionToOpenState();

        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);

        AtomicInteger originalSubscriptions = new AtomicInteger();
        AtomicInteger fallbackSubscriptions = new AtomicInteger();

        Mono<String> originalPublisher = Mono.defer(() -> {
            originalSubscriptions.incrementAndGet();
            return Mono.just("inventory-from-remote");
        });

        Mono<String> protectedPublisher = reactiveBreaker.run(
                originalPublisher,
                error -> Mono.defer(() -> {
                    fallbackSubscriptions.incrementAndGet();
                    return Mono.just("inventory-fallback");
                })
        );

        StepVerifier.create(protectedPublisher)
                .expectNext("inventory-fallback")
                .verifyComplete();

        assertThat(originalSubscriptions.get()).isZero();
        assertThat(fallbackSubscriptions.get()).isEqualTo(1);
        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);
    }
}
~~~

`StepVerifier` subscribes to the protected Publisher. Because the Circuit Breaker is OPEN, it rejects before subscribing to the original Publisher. The fallback is subscribed to and emits the alternative value.

The two counters have distinct meanings:

- `originalSubscriptions` equals 0: there was no subscription to the original work.
- `fallbackSubscriptions` equals 1: the fallback ran exactly once.

If `originalSubscriptions.incrementAndGet()` is placed outside `Mono.defer`, the counter increments as soon as the Publisher is constructed and the test no longer accurately measures subscription.

## 8. Testing Flux Under the Same Principle

With Flux, use `Flux.defer` so the counter increments only when the original Publisher is subscribed to:

~~~java
AtomicInteger originalSubscriptions = new AtomicInteger();

Flux<String> originalPublisher = Flux.defer(() -> {
    originalSubscriptions.incrementAndGet();
    return Flux.just("item-1", "item-2");
});

Flux<String> protectedPublisher = reactiveBreaker.run(
        originalPublisher,
        error -> Flux.just("fallback-item")
);

StepVerifier.create(protectedPublisher)
        .expectNext("fallback-item")
        .verifyComplete();

assertThat(originalSubscriptions.get()).isZero();
~~~

The expected result is the same as with Mono: when the breaker is OPEN, the original Flux is not subscribed to. The fallback Flux can be subscribed to and emit the alternative elements.

Ensure the fallback returns the matching publisher type. `Mono<T>` uses a `Mono<T>` fallback; `Flux<T>` uses a `Flux<T>` fallback. Do not change types in tests just to simplify assertions.

## 9. Verifying That No Actual HTTP Request Is Sent

Counters inside a Supplier or `defer` prove the original code did not run at the application level. For HTTP integration tests, you can use `MockWebServer` or WireMock to verify that no requests reach the mock server.

Example with `WebClient` and `MockWebServer`:

~~~java
MockWebServer server = new MockWebServer();
server.start();

try {
    WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

    AtomicInteger publisherFactoryCalls = new AtomicInteger();

    Mono<String> original = Mono.defer(() -> {
        publisherFactoryCalls.incrementAndGet();

        return webClient.get()
                .uri("/inventory")
                .retrieve()
                .bodyToMono(String.class);
    });

    Mono<String> protectedCall = reactiveBreaker.run(
            original,
            error -> Mono.just("fallback")
    );

    StepVerifier.create(protectedCall)
            .expectNext("fallback")
            .verifyComplete();

    assertThat(publisherFactoryCalls.get()).isZero();
    assertThat(server.getRequestCount()).isZero();
} finally {
    server.shutdown();
}
~~~

If the breaker is OPEN, `Mono.defer` does not execute and `MockWebServer` receives zero requests. Asserting `getRequestCount` equals 0 provides proof at the HTTP boundary that the call never left the application.

When using `WebClient`, constructing the request specification outside `defer` usually does not send an HTTP request yet because reactive `WebClient` is lazy. However, placing the entire publisher construction and execution inside `defer` makes the test boundary clearer and avoids premature side effects.

For synchronous calls, you can use a similar mock HTTP server and assert that the request count is 0 after calling an OPEN Circuit Breaker.

## 10. Observing the CallNotPermitted Event

Resilience4j Circuit Breaker provides an event publisher to observe calls rejected while the circuit is OPEN. You can register a listener before invoking:

~~~java
AtomicInteger rejectedCalls = new AtomicInteger();

coreBreaker.getEventPublisher()
        .onCallNotPermitted(event -> rejectedCalls.incrementAndGet());
~~~

After invoking through Spring Cloud CircuitBreaker and verifying the fallback, you can assert:

~~~java
assertThat(rejectedCalls.get()).isEqualTo(1);
~~~

This event provides additional evidence that the Circuit Breaker rejected the call. However, the event does not replace the Supplier or Publisher counter:

- `CallNotPermitted` proves the breaker rejected the call.
- A Supplier counter of 0 proves the original Supplier did not run.
- A subscription counter of 0 proves the original Publisher was not subscribed to.
- An HTTP request count of 0 proves no request reached the mock server.

Combining these assertions lets the test verify both the Circuit Breaker's decision and the actual effect on the original work.

## 11. Avoiding Flaky Tests Caused by Timing

Do not use `Thread.sleep` hoping the Circuit Breaker transitions to OPEN before calling it. Time-based tests are prone to flakiness due to machine speed, schedulers, and execution time of other tests.

To test rejection behavior in isolation:

1. Create a breaker with a unique ID.
2. Retrieve the exact instance from the registry used by the factory.
3. Call `transitionToOpenState()`.
4. Assert that the current state is OPEN.
5. Invoke the protected Supplier or subscribe to the protected Publisher.
6. Verify the fallback or rejection exception.
7. Assert that the original-work counter is 0.

If you need to test automatic opening based on the failure threshold, write a separate test with a small window configuration and a deterministic number of failed calls. That test checks the state transition; the current test checks behavior once the state is OPEN.

Avoid sharing IDs across tests running in parallel. One test can accidentally reset or alter the state of another test if both use the same registry instance. Use a unique ID per test or reset the breaker after each test finishes.

## 12. Distinguishing OPEN and HALF_OPEN in Assertions

A common mistake is asserting that the Supplier is not called after waiting a long time. Once `waitDurationInOpenState` elapses, the Circuit Breaker can transition from OPEN to HALF_OPEN. HALF_OPEN allows a limited number of probe calls, so the Supplier or Publisher may be executed.

Therefore, confirm the exact state before asserting:

~~~java
assertThat(coreBreaker.getState())
        .isEqualTo(
                io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);
~~~

Do not rely solely on call timing or prior failure counts. If a test runs right at the state transition boundary, the outcome can change.

With Resilience4j, you can configure `waitDurationInOpenState` long enough in the test environment to reduce the risk of automatic state transition during assertions. Even so, still use a dedicated ID and perform the check immediately after explicitly transitioning to OPEN.

In HALF_OPEN, the testing objective is different: verifying the permitted number of probe calls and whether their outcomes transition the breaker back to CLOSED or return it to OPEN. Do not assert that the Supplier is always 0 for HALF_OPEN.

## 13. Common Mistakes in OPEN Tests

- **Checking only the fallback result**: does not prove the original Supplier or Publisher did not run.
- **Placing the counter outside the Supplier**: the counter increments before the Circuit Breaker checks its state.
- **Using `Mono.just` with eager side effects executed earlier**: the Publisher may have already built data or run an eager call at assembly time; use `Mono.defer`.
- **Not using the same registry as the factory**: the test opens one breaker while the application invokes another.
- **Not confirming OPEN state before calling**: the breaker may have already transitioned to HALF_OPEN.
- **Sharing IDs across tests**: parallel tests can interfere with each other's state.
- **Fallback calling the original dependency again**: HTTP requests still appear due to the fallback itself, even though the original Supplier or Publisher was blocked.
- **Counting only `CallNotPermitted` events**: the event confirms rejection but does not prove no side effects occurred elsewhere.
- **Failing to distinguish assembly from subscription**: creating a Mono does not mean a request has been sent.
- **Using sleep for synchronization**: tests depend on environment speed and easily become flaky.
- **Forgetting to reset the breaker or use unique IDs**: the OPEN state can affect subsequent tests.
- **Asserting that HALF_OPEN also never executes original work**: HALF_OPEN permits configured probe calls.

## 14. Verification Workflow in Spring Cloud CircuitBreaker

When writing tests for OPEN behavior, you can follow this sequence:

1. Identify whether the API under test is synchronous `CircuitBreakerFactory` or reactive `ReactiveCircuitBreakerFactory`.
2. Ensure the Resilience4j starter and corresponding registry are configured in the test context.
3. Create the breaker via the factory using a test-specific ID.
4. Retrieve the same instance from `CircuitBreakerRegistry` and transition it to OPEN.
5. Verify the OPEN state immediately before invoking.
6. For the synchronous API, increment a counter inside the Supplier and invoke `run`.
7. For the reactive API, place the counter inside `Mono.defer` or `Flux.defer`, then use `StepVerifier` to subscribe to the protected publisher.
8. Verify that the fallback runs properly or `CallNotPermittedException` is propagated.
9. Assert that the Supplier was not invoked or the original Publisher was not subscribed to.
10. If needed, use `MockWebServer`/WireMock and verify zero HTTP requests.
11. Register an event publisher to check `CallNotPermitted`.
12. Use unique IDs or reset the breaker to isolate state across tests.

A reliable OPEN test must prove both state and effect. The state must be OPEN at the time of the call; the caller receives the fallback or rejection error; the original Supplier invocation count is 0; the original Publisher subscription count is 0; and zero HTTP requests are sent from the blocked execution path. By cleanly separating original work from fallback, using `Mono.defer` for reactive code, and controlling state through the registry on the exact instance, tests accurately confirm that the Circuit Breaker prevents new requests from reaching the dependency while the circuit is OPEN.
