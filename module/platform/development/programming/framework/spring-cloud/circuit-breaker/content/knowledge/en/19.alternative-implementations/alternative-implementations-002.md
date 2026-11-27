# SpringRetryCircuitBreakerFactory and SpringRetryConfigBuilder

## Spring Retry in Spring Cloud Circuit Breaker

Spring Cloud Circuit Breaker provides a common API for applications to create and invoke a Circuit Breaker via `CircuitBreakerFactory`. One of the implementations that can be chosen is Spring Retry. This implementation combines `SpringRetryCircuitBreakerFactory` with Spring Retry's stateful retry mechanism to both retry calls according to a policy and prevent further calls from reaching the dependency when the circuit is open.

The two main classes have distinct roles:

- **`SpringRetryCircuitBreakerFactory`** is the factory created by Spring from the Spring Retry starter. The application injects this factory, creates a breaker by ID, and uses the `run` API to execute a supplier with a fallback.
- **`SpringRetryConfigBuilder`** builds the configuration for the breaker. The builder accepts a `RetryPolicy`; the factory uses that configuration to create the corresponding `CircuitBreakerRetryPolicy` and `DefaultRetryState`.

Spring Retry implements the circuit breaker using `CircuitBreakerRetryPolicy` combined with stateful retry. The retry policy determines how many times a call is attempted and under what conditions. The stateful portion retains retry outcomes across calls, allowing the factory to recognize that the breaker has opened and fail over quickly to the fallback.

## Adding the Starter and Choosing the Right Version

For a Spring Boot application using Spring Cloud Circuit Breaker and Spring Retry, add the following starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-spring-retry</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-spring-retry'
}
```

Let the Spring Cloud BOM manage the starter version alongside the rest of Spring Cloud. Choose a release train compatible with the Spring Boot version in use; do not manually mix a standalone starter version with Spring Cloud Commons or Spring Retry from another line. After adding the dependency, inspect the runtime dependency graph to verify that Spring Cloud Circuit Breaker Spring Retry and Spring Retry are resolved.

Spring Retry Circuit Breaker is an option for synchronous calls based on `RetryTemplate`. For WebFlux applications or `Mono`/`Flux` publishers, choose an implementation with reactive support, typically the Resilience4j Reactor provider. Do not call `block()` to push a reactive pipeline into `SpringRetryCircuitBreakerFactory`.

## Creating and Using a Circuit Breaker from the Factory

Once the starter is loaded, Spring provides a `CircuitBreakerFactory` bean. You can inject this abstraction into a service:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryService {
    private final RestTemplate restTemplate;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public InventoryService(
            RestTemplate restTemplate,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restTemplate = restTemplate;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Inventory find(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> restTemplate.getForObject(
                "http://inventory-service/items/" + sku,
                Inventory.class
            ),
            error -> Inventory.unavailable(sku)
        );
    }
}
```

`create("inventory")` creates or retrieves the breaker with ID `inventory`. The supplier holds the synchronous call to the inventory service. If the supplier fails or the breaker rejects the call because it is open, the fallback receives the cause and returns an alternative result.

`Inventory` is an application-defined type. `Inventory.unavailable` should clearly indicate an unknown status or temporary service unavailability. Do not return an object with quantity 0 if that would mislead callers into thinking the product is definitely out of stock.

The breaker ID should remain stable per dependency or failure domain. If every request generates a different ID, retry state will be fragmented and the Circuit Breaker will fail to protect the intended group of calls.

## How Does SpringRetryConfigBuilder Create Configuration?

`SpringRetryConfigBuilder` is the builder specific to the Spring Retry implementation. Its key configuration point is `retryPolicy(...)`. The passed-in policy acts as the delegate policy for Spring Retry to decide retry counts and continuation conditions. The factory combines it with `CircuitBreakerRetryPolicy` and `DefaultRetryState` to create a stateful breaker.

Example of setting a default policy for all breakers:

```java
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.springretry.SpringRetryCircuitBreakerFactory;
import org.springframework.cloud.circuitbreaker.springretry.SpringRetryConfigBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.policy.TimeoutRetryPolicy;

@Configuration(proxyBeanMethods = false)
public class SpringRetryCircuitBreakerConfiguration {

    @Bean
    Customizer<SpringRetryCircuitBreakerFactory> defaultRetryCustomizer() {
        return factory -> factory.configureDefault(id ->
            new SpringRetryConfigBuilder(id)
                .retryPolicy(new TimeoutRetryPolicy())
                .build()
        );
    }
}
```

`configureDefault` applies the configuration to IDs without a dedicated configuration. In this example, `TimeoutRetryPolicy` controls Spring Retry's time-bounded retries. Read the Spring Retry documentation for your project's version to understand the default timeout and retry behavior of the selected policy; do not equate the retry policy's timeout with the HTTP client's timeout.

## Choosing the Right RetryPolicy

`RetryPolicy` determines when an invocation is retried. Common policies include:

| Policy | How It Works | Suitable Use Case |
| --- | --- | --- |
| `SimpleRetryPolicy` | Limits the maximum number of attempts. | When you want a finite, predictable number of attempts. |
| `TimeoutRetryPolicy` | Allows retries within a time window defined by the policy. | When you want to bound the retry window by duration. |
| Exception-classifying policy | Retries only on specified error types. | When you want to retry transient connection errors but not validation or business errors. |

Example using `SimpleRetryPolicy` with up to three executions per invocation:

```java
import org.springframework.retry.policy.SimpleRetryPolicy;

new SpringRetryConfigBuilder("inventory")
    .retryPolicy(new SimpleRetryPolicy(3))
    .build();
```

`maxAttempts` includes the initial call. Thus, `new SimpleRetryPolicy(3)` allows up to three total executions, meaning at most two retries after the first attempt. This policy illustrates how to limit attempt counts; in production, choose a policy with exception classification so you do not repeat errors that retrying cannot fix.

Example creating a policy that distinguishes connection errors from input errors:

```java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import org.springframework.retry.RetryPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;

Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
retryable.put(IOException.class, true);
retryable.put(IllegalArgumentException.class, false);

RetryPolicy inventoryRetryPolicy = new SimpleRetryPolicy(
    3,
    retryable,
    true
);
```

The `true` argument instructs the policy to inspect wrapped causes as well. Check the actual exception types thrown by your HTTP client; for instance, `IOException` only represents one category of errors and does not cover all connection or timeout errors across every client.

## Per-ID Configuration

Not every dependency should use the same number of attempts. A catalog service can tolerate a couple of short retries, whereas a payment service needs a more conservative policy to avoid repeating write operations.

You can configure per ID using `factory.configure(...)`:

```java
@Bean
Customizer<SpringRetryCircuitBreakerFactory> serviceRetryPolicies() {
    return factory -> {
        factory.configure(
            builder -> builder
                .retryPolicy(new SimpleRetryPolicy(3))
                .build(),
            "inventory"
        );

        factory.configure(
            builder -> builder
                .retryPolicy(new SimpleRetryPolicy(1))
                .build(),
            "payment"
        );
    };
}
```

For `inventory`, the policy allows up to three executions. For `payment`, `SimpleRetryPolicy(1)` allows only one execution with no additional retries. Per-ID configuration binds to the exact ID passed to `create(...)`; the name in the configuration must match the ID in the calling code.

When the same ID has both a default and a per-ID configuration, the per-ID configuration is selected for that ID. Avoid creating multiple customizers that configure the same ID without a clear intent, as ordering can make the final policy hard to predict.

## RetryTemplate and addRetryTemplateCustomizers

Spring Retry executes calls through `RetryTemplate`. `SpringRetryCircuitBreakerFactory` lets you add customizers to adjust `RetryTemplate` after the breaker configuration is created but before it is used. An application can register a `RetryListener` to observe the retry lifecycle.

```java
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.springretry.SpringRetryCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

@Bean
Customizer<SpringRetryCircuitBreakerFactory> retryListenerCustomizer() {
    return factory -> factory.addRetryTemplateCustomizers(retryTemplate ->
        retryTemplate.registerListener(new RetryListener() {
            @Override
            public <T, E extends Throwable> boolean open(
                    RetryContext context,
                    RetryCallback<T, E> callback) {
                return true;
            }

            @Override
            public <T, E extends Throwable> void close(
                    RetryContext context,
                    RetryCallback<T, E> callback,
                    Throwable throwable) {
                // Record that the invocation has finished.
            }

            @Override
            public <T, E extends Throwable> void onError(
                    RetryContext context,
                    RetryCallback<T, E> callback,
                    Throwable throwable) {
                // Record a failed execution attempt.
            }
        })
    );
}
```

`open` is called when a retry operation starts; return `true` to allow the operation to proceed. `onError` is called when an execution attempt fails. `close` is called when the operation ends. You can use the listener to log or update aggregate metrics, but avoid putting user IDs, full URLs, or exception messages into high-cardinality metric tags.

`addRetryTemplateCustomizers` affects the `RetryTemplate` instances created by the factory. If you need different behavior per dependency, check the per-ID configuration capabilities in your version and avoid applying a global customizer that unintentionally alters all breakers.

## Stateful Retry and Circuit Breaker State

What sets Spring Retry Circuit Breaker apart from an ordinary stateless `RetryTemplate` is that state is preserved across invocations. Spring Cloud creates a `CircuitBreakerRetryPolicy` together with a `DefaultRetryState` for the breaker. When the delegate policy exhausts its retries after failures, the circuit state is marked open. Subsequent invocations during the open period can be rejected early and routed to the fallback instead of continuing to call the dependency.

High-level flow:

```text
Invocation arrives at factory
        |
        v
Check saved retry state
        |
        +---- Circuit is open ----> Skip supplier ----> Fallback
        |
        v
Circuit permits execution
        |
        v
RetryPolicy governs attempts
        |
        +---- Success ------------> Return result
        |
        +---- Retries exhausted --> Record open state --> Fallback
        |
        v
After reset duration, context can be refreshed
        |
        v
Next invocation probes the dependency again
```

In Spring Retry, circuit state is tied to the stateful retry context and the breaker key. When deploying multiple replicas, in-memory state in each process is not automatically synchronized across replicas. One Gateway or service instance may have the circuit open while another instance is still allowing calls. If you need coordinated state across multiple nodes, you must design a separate state-sharing mechanism; do not assume the factory provides distributed state out of the box.

## Do Not Confuse with Resilience4j's Sliding Window

Both Spring Retry Circuit Breaker and Resilience4j can stop calls to a failing dependency, but the mechanism that decides when to open the circuit differs.

| Aspect | Spring Retry Circuit Breaker | Resilience4j Circuit Breaker |
| --- | --- | --- |
| Core mechanism | `CircuitBreakerRetryPolicy` combined with stateful retry and `DefaultRetryState`. | Circuit Breaker state machine with metrics and a sliding window. |
| Failure condition | The delegate retry policy no longer permits further attempts. | Failure rate or slow-call rate reaches its threshold after sufficient minimum samples. |
| Common configuration | `SpringRetryConfigBuilder.retryPolicy(...)`. | `CircuitBreakerConfig`, `failureRateThreshold`, `slidingWindowSize`, `minimumNumberOfCalls`. |
| Retry | Built directly into Spring Retry's policy. | Typically combined via a separate Retry decorator alongside Circuit Breaker. |
| Reactive | This Spring Retry integration relies on synchronous `RetryTemplate`. | Provides a Reactor provider for `Mono` and `Flux`. |

Do not copy properties like `failureRateThreshold`, `slidingWindowSize`, or `minimumNumberOfCalls` over to `SpringRetryConfigBuilder`; those are Resilience4j configurations. With Spring Retry, pick an appropriate retry policy and understand how that policy decides when the stateful circuit opens.

## Distinguishing Spring Retry and Framework Retry

Newer Spring Cloud releases may also provide an implementation called Framework Retry based on Spring Framework 7's retry API. That implementation uses `FrameworkRetryCircuitBreakerFactory` and `FrameworkRetryConfigBuilder`. That is a different provider from this lesson, which uses `SpringRetryCircuitBreakerFactory` and `SpringRetryConfigBuilder` from the Spring Retry module.

When reading examples or upgrading dependencies, match the exact factory, builder, and starter names. Do not replace `SpringRetryCircuitBreakerFactory` with `FrameworkRetryCircuitBreakerFactory` simply because the names look similar; the two providers have separate dependencies and configurations.

## Retries Can Amplify Load: Choosing a Safe Policy

Retries are helpful for transient errors such as connection resets or certain gateway errors, but every extra attempt adds load on the dependency. When a dependency is already overloaded, unbounded retries can turn an incident into a worse outage.

Some principles when choosing a policy:

- Set a finite number of attempts and count the initial execution toward that total.
- Retry only exception types that can recover on their own; do not retry validation, authorization, or business errors that waiting will not change.
- Use backoff so retries do not pile up at the exact same instant. If you need to configure a `BackOffPolicy`, do so through the `RetryTemplate` customization hook supported by your Spring Retry version.
- Configure connect timeout, read timeout, and an overall deadline on the HTTP client. `RetryPolicy` does not replace network call timeouts.
- Retry write operations only when an idempotency key or duplicate-execution protection is in place.
- Coordinate retry counts with the circuit open duration and business SLA so requests do not wait longer than permitted.

For example, a call to fetch product details can safely retry a connection error twice. A payment command should not be automatically re-executed without an idempotency key, because the first attempt may already have been processed on the server while the response was lost.

## Fallback When Retries Are Exhausted or the Circuit Is Open

When a call has exhausted its retries or is rejected by the circuit, the fallback in `run` supplies an alternative result:

```java
public PaymentStatus getStatus(String paymentId) {
    return circuitBreakerFactory.create("payment-status").run(
        () -> paymentClient.getStatus(paymentId),
        error -> PaymentStatus.unknown(paymentId)
    );
}
```

The fallback must convey the true meaning. `unknown` states that the application cannot currently determine the payment status; never return `FAILED` or `SUCCESS` if the payment service has not confirmed it. Especially for write operations, a fallback does not mean the transaction succeeded.

Exception classification in the retry policy also affects fallback behavior. If the policy only retries certain exceptions, other exceptions may go straight to the fallback after the very first execution. Clearly define which exceptions to retry, which not to retry, and what result the fallback is allowed to produce.

## Limitations and Provider Selection

Spring Retry Circuit Breaker fits synchronous applications that already use Spring Retry and want to leverage `RetryPolicy`, stateful retry, and `RetryTemplate`. However, consider the following limitations:

- No sliding-window failure-rate configuration model like Resilience4j.
- Circuit behavior depends on the delegate retry policy and stored retry state.
- Retries can increase total latency; backoff and timeouts must fit within the request deadline.
- In-memory state is not automatically shared across multiple instances.
- This integration is not an option for `Mono`/`Flux` reactive pipelines.
- You must design appropriate observability for retries and circuit state yourself; do not assume the same built-in metrics suite as Resilience4j.

If you need a sliding window, slow-call thresholds, bulkheads, rate limiters, deep built-in metrics, or reactive support, Resilience4j is usually a better fit. If the application has standardized on Spring Retry and needs a stateful retry policy behind the Spring Cloud Circuit Breaker API, the Spring Retry provider remains a viable option to consider.

## Integration Testing

When implementing, test the following scenarios using a mock dependency or test environment:

| Scenario | Expected Outcome to Verify |
| --- | --- |
| Dependency succeeds on the first attempt | Supplier runs once and the result is returned. |
| First attempt has a transient error, next succeeds | `RetryPolicy` permits a retry and the invocation returns the successful result. |
| All attempts fail | Policy exhausts retries, circuit state is updated, and the fallback is invoked. |
| Circuit is open | Supplier is not executed again during the open period; fallback receives the rejection error. |
| Reset duration elapses | The next invocation is permitted to probe the dependency via stateful retry. |
| Non-retryable exception | No unintended retries; fallback or caller receives the error as configured. |
| Multiple application instances | Confirm each process maintains separate state and that this difference is observable. |

When debugging, check whether the factory was injected with the right implementation, whether the ID passed to `create` matches the customizer, and whether the applied policy covers the intended exception types. If retries do not happen, review `RetryPolicy`; if the circuit does not open as expected, inspect stateful retry and how the delegate policy signals exhausted attempts.

## References

- [Spring Cloud Circuit Breaker: Configuring Spring Retry Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-spring-retry.html)
- [Spring Retry: CircuitBreakerRetryPolicy](https://github.com/spring-projects/spring-retry/blob/main/src/main/java/org/springframework/retry/policy/CircuitBreakerRetryPolicy.java)

`SpringRetryCircuitBreakerFactory` bridges Spring Cloud's Circuit Breaker API with Spring Retry's stateful retry mechanism. `SpringRetryConfigBuilder` is where `RetryPolicy` is declared so the factory can build per-ID breakers. By clearly understanding the roles of the retry policy, stored state, and fallback, applications can use this provider deliberately and avoid confusing it with Resilience4j's sliding-window model.
