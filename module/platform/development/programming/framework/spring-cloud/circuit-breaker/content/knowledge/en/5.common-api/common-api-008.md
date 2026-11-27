# Provider-Specific Features Requiring Direct Access to the Provider API

Spring Cloud CircuitBreaker provides a common API for applications to call services through a Circuit Breaker without depending directly on the underlying implementation library. With the common API, business code can create a circuit via `CircuitBreakerFactory` or `ReactiveCircuitBreakerFactory`, call `run(...)`, and provide a fallback. This approach minimizes the impact on service-calling code when changing backends.

However, the common API only represents capabilities standardized across backends. When you need Resilience4j-specific features—such as registering native event listeners, reading detailed metrics, classifying exceptions with predicates, or tuning a specialized component—the application can access the Resilience4j API through Spring Cloud CircuitBreaker's extension points.

## When Should You Use the Common API vs. the Native API?

Use the common API for standard service-calling flows: creating a Circuit Breaker by name, executing a supplier or publisher, handling fallbacks, and keeping business code independent of the provider.

The native API is appropriate when a requirement needs a backend-specific capability. For example:

- Registering listeners for `CLOSED`, `OPEN`, and `HALF_OPEN` state-transition events.
- Reading detailed metrics such as counts of successful, failed, slow, or rejected calls.
- Using Resilience4j predicates to decide which exceptions are recorded as failures and which are ignored.
- Configuring Resilience4j-specific components that the common abstraction does not expose.
- Integrating Resilience4j events or metrics with an existing observability system.

The native API introduces a direct dependency on the provider. If you later switch to another backend, code using `Resilience4JCircuitBreakerFactory`, `CircuitBreakerRegistry`, or `io.github.resilience4j.*` types will need to be reviewed and replaced. Therefore, keep native integration inside a configuration class or small adapter so business code continues using the common API.

## Spring Cloud CircuitBreaker Extension Points for Resilience4j

When using the Resilience4j backend, Spring Cloud CircuitBreaker provides `Resilience4JCircuitBreakerFactory` for synchronous applications and `ReactiveResilience4JCircuitBreakerFactory` for reactive applications. You can register a `Customizer` bean to configure the factory or customize the native Circuit Breaker after it is created and before the factory returns it to the caller.

Synchronous applications use the `org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j` starter; reactive applications use `org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j`. Manage versions with a Spring Cloud BOM compatible with your project's Spring Boot version rather than picking individual library versions manually.

The `addCircuitBreakerCustomizer(...)` method is a useful extension point for registering event listeners. The callback receives the Resilience4j Circuit Breaker object, so you can invoke `getEventPublisher()` directly.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryCircuitBreakerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryCircuitBreakerConfiguration.class);

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryEvents() {
        return factory -> factory.addCircuitBreakerCustomizer(circuitBreaker ->
            circuitBreaker.getEventPublisher()
                .onStateTransition(event -> log.info(
                    "Circuit Breaker {} transitioned state: {}",
                    event.getCircuitBreakerName(), event.getStateTransition()))
                .onError(event -> log.warn(
                    "Circuit Breaker {} recorded error: {}",
                    event.getCircuitBreakerName(), event.getThrowable()))
                .onCallNotPermitted(event -> log.debug(
                    "Circuit Breaker {} rejected call",
                    event.getCircuitBreakerName())),
            "inventory");
    }
}
```

The customizer above applies only to the Circuit Breaker with id `inventory`. When the factory creates this breaker, listeners are attached to the Resilience4j object's event publisher. State-transition events, recorded errors, and rejected calls can then be logged or forwarded to an observability system.

Do not register listeners on every service call. Register them during application configuration or when the Circuit Breaker is created. If a customization hook is invoked repeatedly on every `run(...)`, adding listeners repeatedly can produce duplicate logs and increase processing overhead.

When customizing native Circuit Breaker instances through a general `Customizer` where the callback may be invoked multiple times, Spring Cloud Commons provides `Customizer.once(...)` to apply the callback only once per key. With Resilience4j, you can use the Circuit Breaker name as the key:

```java
Customizer.once(
    circuitBreaker -> circuitBreaker.getEventPublisher()
        .onStateTransition(event -> log.info(
            "{}: {}", event.getCircuitBreakerName(), event.getStateTransition())),
    io.github.resilience4j.circuitbreaker.CircuitBreaker::getName);
```

Registering by name avoids attaching the same event listener multiple times to a single breaker. In the factory configuration shown earlier, `addCircuitBreakerCustomizer(...)` remains a direct and readable extension point.

For reactive applications, use the corresponding reactive factory. Registering event listeners follows the same pattern:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.ReactiveResilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ReactiveInventoryCircuitBreakerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(ReactiveInventoryCircuitBreakerConfiguration.class);

@Bean
Customizer<ReactiveResilience4JCircuitBreakerFactory> reactiveInventoryEvents() {
    return factory -> factory.addCircuitBreakerCustomizer(circuitBreaker ->
        circuitBreaker.getEventPublisher()
            .onStateTransition(event -> log.info(
                "Reactive Circuit Breaker {}: {}",
                event.getCircuitBreakerName(), event.getStateTransition())),
        "inventory-reactive");
}
}
```

The reactive factory still returns the reactive abstraction to service-calling code; the customizer callback simply serves as the integration point for Resilience4j's native event API.

## Native Configuration When Custom Policies Are Needed

`configure(...)` allows setting dedicated configurations for one or more IDs. For example, an inventory service needing a custom counting window, failure threshold, and exception-classification policy:

```java
import java.io.IOException;
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;

@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryPolicy() {
    return factory -> factory.configure(builder -> builder
        .circuitBreakerConfig(CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .failureRateThreshold(50)
            .recordException(throwable -> throwable instanceof IOException)
            .build())
        .timeLimiterConfig(TimeLimiterConfig.custom()
            .timeoutDuration(Duration.ofSeconds(2))
            .build()),
        "inventory");
}
```

In this example, the Circuit Breaker only records `IOException` according to the configured predicate. Other exceptions that do not satisfy the predicate are not counted as failures under this policy. Clearly identify the exception types thrown by your HTTP or RPC client before applying a predicate; an overly narrow predicate can prevent real failures from raising the failure rate.

Spring Cloud CircuitBreaker also supports configuration via application properties. According to the Resilience4j configuration documentation, property-based configuration takes precedence over Java `Customizer` configuration. When a setting does not take effect as expected, check the ID, group, and loaded properties before concluding that the Java callback is not working.

## Reading Metrics via the Resilience4j API

The native Circuit Breaker object exposes more detailed metrics than the common API requires. If the application has a `CircuitBreakerRegistry` bean provided by Resilience4j configuration and that registry is also used by the factory, you can inject the registry and look up the Circuit Breaker by id:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
class InventoryCircuitBreakerMetrics {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryCircuitBreakerMetrics.class);

    private final CircuitBreakerRegistry registry;

    InventoryCircuitBreakerMetrics(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    void logSnapshot() {
        CircuitBreaker circuitBreaker = registry.circuitBreaker("inventory");
        CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

        log.info("state={}, failed={}, successful={}, notPermitted={}, failureRate={}",
            circuitBreaker.getState(),
            metrics.getNumberOfFailedCalls(),
            metrics.getNumberOfSuccessfulCalls(),
            metrics.getNumberOfNotPermittedCalls(),
            metrics.getFailureRate());
    }
}
```

The snippet above illustrates how to read state and a metrics snapshot. In a production application, use the class-declared logger and export the necessary metrics to Micrometer or a monitoring system rather than calling `logSnapshot()` on every request. Metrics are point-in-time observations; they can change immediately afterward as new calls complete.

When accessing the registry, make sure it is the same `CircuitBreakerRegistry` used by the Spring Cloud CircuitBreaker backend. Do not assume all configurations share one registry if the application declares multiple beans manually. If you create a separate registry or call `CircuitBreaker.of(...)` independently, the application may inadvertently create a different breaker from the one `Resilience4JCircuitBreakerFactory` uses. In that case, the state and metrics read will not reflect actual requests passing through the factory. If you cannot verify a shared registry, read metrics inside the `addCircuitBreakerCustomizer(...)` callback, which receives the exact object created by the factory.

## Keeping the Native API at the Integration Boundary

A maintainable structure is to have business services call the common API while a configuration class or adapter handles integration with the provider API.

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    Inventory find(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.find(sku),
            error -> inventoryCache.find(sku)
                .orElseThrow(() -> new InventoryUnavailableException(sku, error)));
    }
}
```

`InventoryService` only knows `CircuitBreakerFactory` and the fallback contract. It does not need to import `io.github.resilience4j.*`. Event configuration, metrics, and native policies live in a separate configuration class or adapter. If the backend is changed, the service layer is unlikely to need changes; the native integration layer is where adjustments are made.

With the reactive API, keep the same principle: use `ReactiveCircuitBreakerFactory` in `Mono` or `Flux` pipelines, and place provider-specific customizations in the corresponding reactive configuration. Do not convert a reactive publisher into a blocking call just to invoke the native API; doing so can block the event loop and negate the benefits of the reactive model.

## Controlling Native Administrative Operations

Resilience4j provides direct administrative operations such as resetting a breaker or forcing a state transition. These are useful in controlled operational workflows—for example, manually re-opening a breaker during incident mitigation or simulating states for testing. Because these operations mutate the shared state of the Circuit Breaker, they should never be invoked arbitrarily from public endpoints or per-request handling logic.

If you build administrative controls, place them behind proper authentication and authorization, and record audit logs capturing the operator, Circuit Breaker ID, previous state, and requested action. Afterward, continue monitoring events and metrics to confirm the breaker behaves as expected. Do not treat forcing a state as proof that the dependent service is healthy; verify health with probe calls and operational telemetry.

## Common Mistakes When Using the Provider API

| Issue | Common cause | Solution |
|---|---|---|
| Listener logs multiple times | Listener is registered repeatedly on every request or every `run(...)` call | Register inside `Customizer` at breaker creation time; avoid adding listeners repeatedly |
| Metrics do not match traffic | Reading a registry or Circuit Breaker created independently of the factory | Use the shared registry bean auto-configured by the backend and the exact same ID |
| Java configuration does not take effect | Property-based configuration has higher precedence | Inspect the actual instance, group, and ID properties in effect |
| Switching backends causes compilation errors | Business code depends directly on Resilience4j types | Move native code into an adapter/configuration class and keep the common API in services |
| Breaker does not open as expected | Predicate only records a subset of exceptions or ignores failures by mistake | Test representative exception types and verify the failure rate |
| Administrative endpoint triggers unintended changes | Allowing forced state-transition calls from public flows | Isolate admin permissions, enforce access control, and write audit logs |

Before promoting native integrations to production, clearly identify which capabilities the common API does not cover, test with the exact Circuit Breaker ID, verify listeners are registered only once, and compare native metrics against real traffic. Isolating provider dependencies enables taking advantage of advanced features while keeping the bulk of business code stable.

## References

- [Spring Cloud CircuitBreaker – Resilience4J specific configuration](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/specific-circuit-breaker-configuration.html)
- [Spring Cloud Commons – Spring Cloud Circuit Breaker API](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html)
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
