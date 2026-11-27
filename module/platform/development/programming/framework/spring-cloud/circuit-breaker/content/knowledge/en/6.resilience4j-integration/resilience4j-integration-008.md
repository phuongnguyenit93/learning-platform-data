# Distinguishing the Spring Cloud Wrapper from Native Resilience4j CircuitBreaker

In Spring Cloud applications, there are two common ways to invoke a circuit breaker provided by Resilience4j. The first uses **Spring Cloud CircuitBreaker** as a unified API layer, then selects Resilience4j as the implementation. The second calls the **Resilience4j** API directly through `CircuitBreaker`, `CircuitBreakerRegistry`, decorators, or library annotations.

Both approaches can protect calls to the same service and use concepts such as `CLOSED`, `OPEN`, `HALF_OPEN`, failure rate, slow-call rate, and sliding windows. The difference lies in which API layer application code depends on, how instances are created and managed, how fallbacks are attached, and the level of granular control the application needs. Choosing one clear approach per call boundary prevents accidentally creating two independent circuit breakers or wrapping the same call multiple times.

## 1. Where do the two layers sit in the architecture?

Spring Cloud CircuitBreaker provides an abstraction so applications invoke circuit breakers with minimal coupling to a specific library. The application interacts with APIs such as `CircuitBreakerFactory` or `ReactiveCircuitBreakerFactory`. Spring Cloud selects the corresponding backend, such as Resilience4j, to execute the protection mechanism.

Resilience4j is the library that directly provides the protection components. The native circuit breaker API lives in the `io.github.resilience4j.circuitbreaker` package, comprising `CircuitBreaker`, `CircuitBreakerConfig`, and `CircuitBreakerRegistry`. The library also includes Spring Boot integrations, annotations, Reactor support, and modules such as Retry, RateLimiter, Bulkhead, and TimeLimiter.

```text
Business code
    |
    +-- Spring Cloud CircuitBreaker API
    |       CircuitBreakerFactory / ReactiveCircuitBreakerFactory
    |                    |
    |                    v
    |          Resilience4j implementation
    |                    |
    +-- Resilience4j native API
            CircuitBreaker / Registry / Decorators
                         |
                         v
                Dependent service
```

The diagram shows two different access paths to the Resilience4j mechanism. When using the Spring Cloud abstraction, business code calls through the Spring Cloud layer. When using the native API, business code interacts directly with Resilience4j objects. There is no need to create an extra native circuit breaker outside just to use Resilience4j if Spring Cloud has already configured this backend for the call.

## 2. Comparing APIs and responsibilities

| Criterion | Spring Cloud CircuitBreaker | Native Resilience4j |
| --- | --- | --- |
| Primary API | `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory` | `CircuitBreaker`, `CircuitBreakerRegistry`, `CircuitBreakerConfig` |
| Coupling | Depends on Spring Cloud abstractions; backends can be swapped with fewer application code changes | Depends directly on Resilience4j APIs and types |
| Instance creation | Calls `factory.create("inventory")` | Retrieves instance from `CircuitBreakerRegistry` or builds from configuration |
| Fallback | Typically passes a fallback function directly to `run(...)` | Handled manually via `try/catch`, decorators, annotation fallback, or application logic |
| Deep customization | Uses Spring Cloud configuration and backend customizers | Can configure directly, listen to events, use decorators, and access the registry |
| Reactive | Uses `ReactiveCircuitBreakerFactory` | Uses the Reactor module and `CircuitBreakerOperator`, or corresponding native integration |
| Best suited when | You want a unified API across the Spring Cloud ecosystem | You need direct Resilience4j control or use libraries outside Spring Cloud |

Spring Cloud CircuitBreaker does not replace the Resilience4j engine in this setup; it provides the invocation layer and backend integration. Native Resilience4j does not automatically become a Spring Cloud abstraction just because the application has a Resilience4j dependency. The two APIs expose different object types, even though the backend may be the same library.

## 3. Using Spring Cloud CircuitBreaker with the Resilience4j backend

For Spring Cloud applications, add the corresponding Resilience4j starter and manage the Spring Cloud version via a BOM compatible with your project's Spring Boot version:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
```

If the application uses reactive APIs, use the corresponding reactive Resilience4j starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
```

Do not pick an arbitrary starter version on your own; use the Spring Cloud release train compatible with Spring Boot and let dependency management resolve related versions.

### Creating and calling a circuit breaker via the factory

Spring Cloud provides `CircuitBreakerFactory`. The instance name passed to `create(...)` must match the name in the Resilience4j configuration:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

`create("inventory")` asks the factory to provide the circuit breaker with ID `inventory`. The first function executes the call to the inventory service. The second function is the fallback, invoked when the task fails or the circuit breaker disallows the call because it is `OPEN`. The example uses a fallback result representing an undetermined data state; a real application must clearly define whether that data is permissible for business use.

### Configuring the instance for the backend

The Resilience4j backend reads configuration by instance ID. For example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

`minimumNumberOfCalls` sets the minimum sample size before evaluation. `failureRateThreshold` and `slowCallRateThreshold` are the two thresholds that can transition the circuit breaker from `CLOSED` to `OPEN`. `waitDurationInOpenState` and `permittedNumberOfCallsInHalfOpenState` govern the recovery attempt phase. These properties belong to the Resilience4j backend configuration; the Spring Cloud abstraction does not alter their semantics.

### Customizing the backend

When you need to apply default configurations or customize by ID, Spring Cloud CircuitBreaker allows configuring the factory with customizers. The following example illustrates setting a default configuration for IDs without a dedicated configuration:

```java
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
                .circuitBreakerConfig(
                    io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
                        .custom()
                        .failureRateThreshold(50)
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .build()
                )
                .build()
        );
    }
}
```

This is customization at the Spring Cloud factory layer. In real projects, pick one intentional configuration source—such as environment-specific YAML or per-ID customizers—and avoid letting multiple sources override the same property without a clear convention. When a specific instance needs dedicated settings, use per-ID configuration or `configure(...)` appropriately instead of changing the default for all instances.

## 4. Using Resilience4j CircuitBreaker and Registry directly

When you need to interact with the native API, the application obtains the circuit breaker from `CircuitBreakerRegistry`. The registry manages instances by name and lets components share the same protection state.

Example of creating a registry with programmatic configuration in a plain Java application:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;

import java.time.Duration;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .failureRateThreshold(50)
    .slowCallDurationThreshold(Duration.ofSeconds(2))
    .slowCallRateThreshold(60)
    .waitDurationInOpenState(Duration.ofSeconds(15))
    .build();

CircuitBreakerRegistry registry = CircuitBreakerRegistry.of(config);
CircuitBreaker inventoryBreaker = registry.circuitBreaker("inventory");
```

The registry and breaker should be created once at application scope and injected into services that need them. Do not create a new registry per request or per method call; each registry can manage an isolated group of instances, fragmenting states and metrics.

In a plain Java application, the core module required is `io.github.resilience4j:resilience4j-circuitbreaker`. If using Spring Boot for YAML property binding and annotations, choose `resilience4j-spring-boot3` or the starter matching your project's Spring Boot version.

### Wrapping calls with the native API

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;

public InventoryResult getInventory(
        String sku,
        CircuitBreaker inventoryBreaker,
        InventoryClient inventoryClient) {
    try {
        return inventoryBreaker.executeSupplier(
            () -> inventoryClient.fetch(sku)
        );
    } catch (CallNotPermittedException ex) {
        // Circuit breaker is OPEN and rejects new calls.
        return InventoryResult.unavailable(sku);
    }
}
```

`executeSupplier(...)` executes the task within the circuit breaker's scope and records outcomes according to configuration. `CallNotPermittedException` indicates the breaker rejected the call because it is in a non-permitting state. The example only falls back on rejection; exceptions from the dependent service still propagate outward. If you also want fallbacks for service failures, handle those exception groups according to an explicit business policy to avoid accidentally masking programming bugs or data errors.

You can use decorators instead of `executeSupplier(...)` when combining multiple mechanisms:

```java
import java.util.function.Supplier;

Supplier<InventoryResult> inventoryCall =
    CircuitBreaker.decorateSupplier(
        inventoryBreaker,
        () -> inventoryClient.fetch(sku)
    );

InventoryResult result = inventoryCall.get();
```

The decorator returns a `Supplier` wrapped by the circuit breaker. You can combine decorators from Retry, Bulkhead, or RateLimiter in the desired order. Wrapping order determines which mechanism observes the outcomes and timing of another; clarify the goal before stacking multiple decorators.

## 5. Native Resilience4j annotations in Spring Boot

Resilience4j provides the `@CircuitBreaker` annotation via its Spring Boot integration. This is a Resilience4j annotation, not the Spring Cloud CircuitBreaker factory API. It is typically implemented with Spring AOP, so methods must be invoked through a Spring proxy for advice to apply; internal self-calls via `this.someMethod()` can bypass the proxy.

```java
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public InventoryResult getInventory(String sku) {
        return inventoryClient.fetch(sku);
    }

    private InventoryResult inventoryFallback(String sku, Throwable cause) {
        return InventoryResult.unavailable(sku);
    }
}
```

An annotation fallback must have business parameters matching the original method plus an exception parameter at the end. Resilience4j resolves the fallback method compatible with the signature and exception type. In the example, `Throwable` is the general type; narrower exception types can be used to apply different policies for rejections, timeouts, or service errors.

To use the annotation, the application needs the Resilience4j Spring Boot starter matching its Spring Boot version and AOP configured per that version's guide. For example, Spring Boot 3 uses `resilience4j-spring-boot3`; Spring Boot 2 uses the corresponding Boot 2 starter. If you only use the Spring Cloud CircuitBreaker factory, there is no need to add annotations just for fallbacks because the `run(...)` API already accepts a fallback function.

Example dependencies for a Spring Boot 3 application using native annotations:

```xml
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-spring-boot3</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Manage the Resilience4j version through your project's dependency management and use the artifact matching your Spring Boot version; do not mix a Boot 2 starter into a Boot 3 application.

## 6. Reactive calls: abstraction vs. native API

For `Mono` or `Flux`, Spring Cloud provides `ReactiveCircuitBreakerFactory`. For example:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public Mono<InventoryResult> getInventory(String sku) {
    return reactiveCircuitBreakerFactory.create("inventory").run(
        inventoryClient.fetch(sku),
        error -> Mono.just(InventoryResult.unavailable(sku))
    );
}
```

When using native Resilience4j with Reactor, add the Reactor integration module and apply `CircuitBreakerOperator`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Mono;

public Mono<InventoryResult> getInventory(
        String sku,
        CircuitBreaker inventoryBreaker) {
    return inventoryClient.fetch(sku)
        .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
        .onErrorResume(
            io.github.resilience4j.circuitbreaker.CallNotPermittedException.class,
            error -> Mono.just(InventoryResult.unavailable(sku))
        );
}
```

`transformDeferred(...)` applies the operator when subscription occurs, matching Reactor's lazy execution model. `onErrorResume(...)` in the example only handles cases where the circuit breaker rejects the call; if fallback is also needed for failures from the dependent service, add the corresponding handling branch and preserve cause information for observability. Do not call `block()` inside a reactive flow just to use the synchronous API, as that can block the event loop.

## 7. Proper configuration and state sharing

When using Spring Cloud CircuitBreaker, configure instances by the IDs the factory creates. When using the Resilience4j Spring Boot starter, configuration can also be bound into the registry managed by the integration. Example YAML configuration that can serve as a baseline for the `inventory` instance:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
    instances:
      inventory:
        baseConfig: default
```

If you use the Spring Boot starter and want YAML applied, inject the Spring-configured registry. Do not manually call `CircuitBreakerRegistry.ofDefaults()` and expect it to automatically pick up YAML properties; a manually created registry with default configuration does not automatically inherit settings managed by another bean.

A common point of confusion is that two breakers with the same name do not necessarily share the same state. If the Spring Cloud factory manages one instance while the application creates an independent registry and retrieves another `inventory`, those can be two distinct objects. They will have separate counters, states, and metrics. If the intent is to share a single state, unify where instances are created and inject the same object or use the exact registry/backend managed by the integration.

Avoid wrapping the same call simultaneously with a Spring Cloud circuit breaker, a native annotation, and another native decorator unless intentional. Otherwise, a single error may be counted multiple times across different breakers; an outer fallback may mask state from an inner breaker; and metrics become hard to interpret. Typically, choose one mechanism at the service call boundary and give the instance a name that clearly describes the protected dependency.

## 8. Monitoring, testing, and choosing an integration approach

Both access paths can expose Resilience4j metrics and events when the backend is configured accordingly. Use Micrometer and a monitoring system to track state, as well as successful, failed, slow, and rejected call counts. When using the Spring Cloud abstraction, verify that the ID created by the factory matches the configured ID. When using the native API, verify the service receives the exact instance from the expected registry.

Tests should verify at least three behaviors: calls proceed when the breaker is `CLOSED`; new calls are rejected when the breaker is `OPEN`; and the fallback or error handler returns the policy-compliant result upon rejection. With the native API, you can use `CircuitBreakerRegistry` to fetch the breaker and inspect its state. With the Spring Cloud abstraction, test through the service using the factory to verify both wiring and fallback. Use small windows and sample counts in test profiles for deterministic results, and reset or create fresh instances between tests so state does not leak across test cases.

| Need | Suitable choice |
| --- | --- |
| Spring Cloud application wanting an API less coupled to the implementation | Spring Cloud CircuitBreaker with the Resilience4j backend |
| Wanting to swap backends or keep an abstraction at the business layer | Spring Cloud CircuitBreaker |
| Needing direct access to registry, events, config, and decorators | Native Resilience4j API |
| Using the `@CircuitBreaker` annotation and method-level fallbacks | Resilience4j Spring Boot integration |
| Using Reactor with the Spring Cloud abstraction | `ReactiveCircuitBreakerFactory` |
| Using Reactor directly with a native breaker | `CircuitBreakerOperator` from the Reactor module |

Prefer Spring Cloud CircuitBreaker when an application wants to keep dependency boundaries at the Spring Cloud abstraction and only needs call execution, fallbacks, and per-ID configuration. Choose Resilience4j's native API when you need deep interaction with the registry, events, decorators, or library annotations. Whichever approach you choose, centralize instance management, use consistent configuration, define business-appropriate fallbacks, and monitor actual runtime state. This ensures the circuit breaker properly protects dependent calls without introducing hard-to-control state into a Spring Cloud application.
