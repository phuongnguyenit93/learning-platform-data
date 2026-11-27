# Scope of Configuration Shared Across Implementations

## Objectives

Spring Cloud CircuitBreaker provides an API layer that allows applications to call dependent services through a Circuit Breaker without coupling every call directly to a specific library. This abstraction layer enables reusing calling patterns and code structure, but it does not turn every configuration option from underlying libraries into an identical set of properties.

After this lesson, you will be able to:

- Distinguish the shared API from implementation-specific configuration.
- Use `CircuitBreakerFactory` and `ReactiveCircuitBreakerFactory` to create Circuit Breakers by name.
- Organize instance names, fallbacks, and application policies so implementations can be swapped with minimal changes in the calling layer.
- Configure default and per-instance settings for Resilience4j while recognizing limitations when migrating to another implementation.
- Avoid assuming that timeout, sliding window, bulkhead, retry, and metrics share the same semantics or properties across implementations.

## Common API and Specific Configuration Are Two Distinct Layers

Spring Cloud CircuitBreaker defines an abstraction for applications to use a Circuit Breaker. At the calling layer, application code typically needs to know the dependency name, the operation to execute, and how to handle failures. The concrete implementation is responsible for enforcing the protection policy.

| Part | Can be shared | Implementation-dependent |
|---|---|---|
| Creating the breaker | Created by dependency name via the factory. | Factory beans and starters provided by the chosen implementation. |
| Synchronous calls | Wrapping the operation in `run` and providing a fallback. | Error evaluation, state storage, and internal execution. |
| Reactive calls | Reactive abstraction available when supported by the implementation. | Level of reactive support and publisher integration depend on starter/version. |
| Identifiers | Naming conventions such as `catalog`, `payment`, `inventory`. | Rules for mapping names to instances or configuration groups. |
| Business policies | Target timeout, acceptable error rate, and fallback behavior can be described at the application level. | How each policy is represented and enforced in a specific library. |
| Detailed configuration | Can be centralized in one place for management. | YAML properties, builders, customizers, metrics, and events are generally not directly compatible. |

For example, an application can specify that calls to `catalog` need a wait-time limit, a cache-backed fallback, and independent monitoring. Resilience4j can express this policy using Circuit Breaker, TimeLimiter, and Bulkhead. Another implementation might use a retry policy or a different limiting mechanism. The application's intent remains the same, but you should not assume every implementation offers the same algorithm or the same level of protection.

## Creating a Circuit Breaker via the Factory

For synchronous calls, the application uses `CircuitBreakerFactory` to create a Circuit Breaker by name. This name is a stable identifier for the dependency within the application and is usually also the instance configuration key for the implementation.

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogGateway {
    private final RestClient restClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogGateway(
            RestClient restClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = restClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Product findProduct(String id) {
        CircuitBreaker breaker = circuitBreakerFactory.create("catalog");

        return breaker.run(
                () -> restClient.get()
                        .uri("/products/{id}", id)
                        .retrieve()
                        .body(Product.class),
                error -> Product.unavailable(id));
    }
}
```

`Product` and `Product.unavailable` are example application types. The fallback must share the same return type as the primary call and clearly represent unavailable or cached data. Do not return an object that looks like a complete live result if the application cannot guarantee its accuracy.

The factory can also accept a group name alongside the instance name via `create(id, groupName)` if the implementation supports that mapping. Use a stable `id` per dependency and only use groups when sharing one configuration across multiple instances. Do not generate new names per request, as that can cause Circuit Breaker counts and metrics to grow uncontrollably.

## Reactive API

For Spring WebFlux applications, `ReactiveCircuitBreakerFactory` creates a `ReactiveCircuitBreaker`. Both the call and the fallback remain reactive, avoiding thread blocking via `block()`.

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogGateway {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ReactiveCatalogGateway(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<Product> findProduct(String id) {
        ReactiveCircuitBreaker breaker = circuitBreakerFactory.create("catalog");

        Mono<Product> request = webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class);

        return breaker.run(request, error -> Mono.just(Product.unavailable(id)));
    }
}
```

The reactive abstraction keeps calling structure similar across application modules. However, not every implementation or version supports reactive flows in the same way. Before swapping starters, confirm that the chosen implementation provides `ReactiveCircuitBreakerFactory` and can enforce the required policies in a reactive pipeline.

## Instance Names as the Application Configuration Contract

Standardize Circuit Breaker names by dependent service, for example:

| Name | Dependency | Typical application policy |
|---|---|---|
| `catalog` | Catalog service | Short timeout, cache-backed fallback. |
| `payment` | Payment gateway | SLA-based timeout, never fake a successful transaction on failure. |
| `inventory` | Inventory service | Concurrency limit, fallback indicating indeterminate status. |

The name `catalog` in calling code must match the configured instance name in the implementation. Keeping naming consistent across synchronous code, reactive code, dashboards, and alerts makes changing implementations more manageable.

An instance name should also not represent a single endpoint or varying request parameter. For example, do not create `catalog-product-123` and `catalog-product-456` as two separate Circuit Breakers if both call the same catalog service. A Circuit Breaker typically protects a dependency or a group of behaviors with similar failure characteristics.

## Resilience4j Configuration: A Concrete Example

When choosing Resilience4j, Spring Cloud CircuitBreaker provides the corresponding factory and builder to configure defaults or per-instance settings. This is the configuration API of the Resilience4j integration, not a universal configuration API for all implementations.

Example of default configuration using `Customizer`:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerConfiguration {
    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        return factory -> factory.configureDefault(id ->
                new Resilience4JConfigBuilder(id)
                        .circuitBreakerConfig(CircuitBreakerConfig.custom()
                                .slidingWindowSize(20)
                                .minimumNumberOfCalls(10)
                                .failureRateThreshold(50)
                                .build())
                        .timeLimiterConfig(TimeLimiterConfig.custom()
                                .timeoutDuration(Duration.ofSeconds(2))
                                .build())
                        .build());
    }
}
```

`configureDefault` provides default settings for Circuit Breakers created by the factory. If a dependency needs a different policy, use `configure` to apply a builder to specified IDs:

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreakerConfig() {
    return factory -> factory.configure(builder -> builder
                    .circuitBreakerConfig(CircuitBreakerConfig.custom()
                            .slidingWindowSize(10)
                            .minimumNumberOfCalls(5)
                            .failureRateThreshold(40)
                            .build())
                    .timeLimiterConfig(TimeLimiterConfig.custom()
                            .timeoutDuration(Duration.ofMillis(800))
                            .build()),
            "catalog");
}
```

The per-ID configuration snippet illustrates the Resilience4j integration. Keep imports, builder types, and Spring Cloud versions aligned with your project's dependency management. You cannot transfer `Resilience4JConfigBuilder`, `CircuitBreakerConfig`, or `TimeLimiterConfig` directly to another implementation.

You can declare Resilience4j configuration in YAML to separate operational policy from Java code:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 8s
    instances:
      catalog:
        baseConfig: default
      payment:
        baseConfig: default
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
  timelimiter:
    configs:
      default:
        timeoutDuration: 2s
    instances:
      catalog:
        baseConfig: default
      payment:
        baseConfig: default
        timeoutDuration: 800ms
```

`configs.default` is a base configuration in Resilience4j; each instance can inherit from it using `baseConfig` and override specific properties. `resilience4j.*` is Resilience4j's namespace. If you switch to another implementation, you must map the intent of these values to the new implementation's configuration mechanism; swapping starters does not automatically translate YAML.

## What Can Actually Be Shared?

A sustainable design is to store policies at the application level using concepts the business understands, then map them to the chosen implementation. For example, application configuration can describe dependencies, target wait limits, desired error thresholds, and fallback modes:

```yaml
app:
  dependency-protection:
    catalog:
      timeout: 2s
      fallback: cache
      availability-target: 99.5
    payment:
      timeout: 800ms
      fallback: unavailable
      availability-target: 99.9
```

This is an application-defined namespace, not built-in Spring Cloud CircuitBreaker properties. An application configuration class reads these values, and a Resilience4j adapter translates them into `TimeLimiter`, `CircuitBreaker`, and `Bulkhead`. If another implementation is adopted later, a new adapter translates those application policies into options supported by that implementation.

Do not force every property into a single common model if their meanings differ. For example:

- `slidingWindowSize` is a concept of Circuit Breakers with a statistical sliding window; another implementation may not have the same kind of window.
- `permittedNumberOfCallsInHalfOpenState` describes probe calls in `HALF_OPEN`; not every library shares the same states or admission rules.
- `TimeLimiter` enforces wait limits in its own way; HTTP client or Reactor timeouts do not automatically share the same task-cancellation behavior.
- A bulkhead can use a semaphore or a thread pool. The same concurrency limit does not guarantee the same resource model or queueing behavior.
- Retry and Circuit Breaker can cooperate, but retry policies are not equivalent to a Circuit Breaker's failure thresholds and sliding windows.

Therefore, a shared model should capture application-level intent and only retain properties with consistent definitions. Implementation-specific capabilities should be modeled as optional extensions, verified for implementation support before enabling.

## When Changing Implementations

When replacing the implementation, review layer by layer:

1. **Dependencies and auto-configuration:** select the right starter and inspect the factory bean created. Do not place multiple implementations on the classpath simultaneously if auto-configuration could become ambiguous.
2. **Calling layer:** verify the application depends only on the Spring Cloud CircuitBreaker abstraction where portability is needed. Any code calling Resilience4j APIs directly must be migrated.
3. **Instance names:** keep ID conventions in the calling layer; map them to instances or configuration groups in the new implementation.
4. **Timeout and fallback:** confirm timeout errors flow into the Circuit Breaker as expected, fallbacks receive the right exceptions, and operations cancel properly.
5. **Thresholds and states:** check whether the new implementation has equivalent `CLOSED`, `OPEN`, `HALF_OPEN` states, sliding windows, and probes. If not, pick the closest policy and document the differences.
6. **Bulkhead and retry:** verify concurrency limits, queues, retry counts, backoff, and composition order with the Circuit Breaker.
7. **Metrics and events:** update dashboards, alerts, and event listeners since metric names, tags, and event types may differ.
8. **Behavioral testing:** run the same scenarios—healthy service, continuous errors, slow responses, recovery, and overload—to compare actual outcomes.

Spring Retry is an example of an implementation with its own retry model and policy. Do not copy `resilience4j.circuitbreaker.*` properties into Spring Retry configuration or expect the same sliding window, failure rate, TimeLimiter, and Bulkhead behavior. Configure according to the API and documentation of the exact starter/version in use, then verify behavior through testing.

## Fallback Is an Application Contract

Fallbacks sit at the boundary between technical resilience and product behavior. Several rules remain shared even when the implementation changes:

- The fallback must be compatible with the return type of the primary operation.
- The fallback should not call back into the same failing dependency over an unprotected path.
- Cached data should indicate staleness if that affects business decisions.
- For payments, never return a fake success result when it is unknown whether the transaction was processed.
- Distinguish business errors, input errors, timeout errors, and errors caused by the Circuit Breaker rejecting the call.

The abstraction's fallback API accepts `Throwable`, yet the application should still classify the cause before choosing a response. Not every exception should produce the same default result.

## Monitoring and Testing Configuration

Metric and event names depend on the implementation. With Resilience4j, applications typically observe Circuit Breaker state, call counts by outcome, failure rate, slow-call rate, and rejected call counts via Micrometer. Other implementations may emit metrics with different names, tags, or granularity. If a shared dashboard is required, standardize at the application's observability layer instead of assuming library metric names are always identical.

A configuration test scenario should include:

1. Send successful calls and verify the dependency is invoked normally.
2. Make the dependency return errors to verify the Circuit Breaker records failures and transitions states as configured.
3. Make the dependency respond slowly to verify timeouts, task cancellation, and fallbacks work as intended.
4. Send requests while the circuit is `OPEN` to verify calls fail fast and the fallback satisfies its contract.
5. Restore the dependency and observe `HALF_OPEN` probe calls if the implementation supports that state.
6. Generate concurrent load to test Bulkhead if enabled; verify capacity-exhaustion errors are not mistaken for dependency health failures.
7. Cross-check metrics, logs, and events against actual call counts.

When changing implementations, run the same scenarios under the same load conditions and application policies. Compare both caller-visible behavior and the impact on the dependency: forwarded request counts, wait times, retry counts, fallback rates, and recovery time.

## Common Design Mistakes

- **Confusing abstraction with configuration compatibility:** a common calling API does not mean all YAML properties or builders are shared.
- **Leaking Resilience4j types into the business layer:** this spreads implementation migration changes across many classes.
- **Generating IDs per request:** increases instance counts, metrics, and memory usage.
- **Sharing one timeout across all dependencies:** each service has different SLAs and response characteristics.
- **Fallbacks masking business errors:** callers may receive incorrect results without knowing the actual state.
- **Failing to check reactive support:** can prevent the application from creating the factory or force thread blocking.
- **Copying YAML verbatim to another implementation:** properties may be ignored or carry different meanings.
- **Forgetting to update dashboards after swapping libraries:** metrics stop being emitted as before, rendering alerts ineffective.

Keep the calling layer at the abstraction provided by Spring Cloud CircuitBreaker, use stable dependency identifiers, and express policies at the application level. When fine-grained settings such as sliding windows, probes, TimeLimiter, or Bulkhead are needed, treat them as implementation-specific capabilities and re-verify them whenever changing libraries or versions.
