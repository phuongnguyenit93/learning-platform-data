# Resilience4j @CircuitBreaker Differs from the Spring Cloud CircuitBreaker API

## Two Integration Approaches with Different Goals

In a Spring Cloud system, the name "Circuit Breaker" can refer to two APIs that are commonly used with Resilience4j but have different integration mechanisms:

- `@CircuitBreaker` is a Resilience4j annotation. Spring AOP uses an aspect to intercept method calls, apply the Circuit Breaker, and return the result or invoke a fallback.
- `CircuitBreakerFactory` is the programmatic abstraction of Spring Cloud Circuit Breaker. The application explicitly creates a breaker by name and wraps the call with `run(...)`.

Both can rely on Resilience4j to enforce protection policies, but they are not the same API and do not automatically substitute for each other. The annotation belongs to Resilience4j's AOP integration; `CircuitBreakerFactory` belongs to Spring Cloud's abstraction. Choosing between them affects dependencies, configuration style, where the logic lives, and how call flow is controlled.

| Criterion | Resilience4j `@CircuitBreaker` | Spring Cloud `CircuitBreakerFactory` |
| --- | --- | --- |
| Usage | Annotate the method with an annotation. | Create a breaker and call `run` in application code. |
| Application mechanism | Spring AOP proxy and Resilience4j aspect. | Direct call to the abstraction in code. |
| Fallback | Fallback method with a signature compatible with the original method. | Pass a `Function<Throwable, T>` directly to `run`. |
| Configuration | Resilience4j instances, typically under `resilience4j.circuitbreaker.instances`. | Spring Cloud factory and provider; with Resilience4j, typically customized using `Customizer<Resilience4JCircuitBreakerFactory>`. |
| Provider coupling | Tied directly to Resilience4j. | Allows changing the provider implementation with less impact on calling code. |
| Scope control | By the method intercepted by the aspect. | By the exact supplier block passed to `run`. |

## How Resilience4j @CircuitBreaker Works via Spring AOP

The commonly used annotation is `io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker`. When Spring creates the bean, Resilience4j's aspect applies an interceptor to the annotated method. Calls going through the proxy are wrapped by the Circuit Breaker whose name is specified in the `name` attribute.

Example:

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
    public Inventory find(String sku) {
        return inventoryClient.fetch(sku);
    }

    private Inventory inventoryFallback(String sku, Throwable cause) {
        return Inventory.unknown(sku);
    }
}
```

`name = "inventory"` is the Circuit Breaker instance name. When a method call goes through the proxy, the aspect applies the corresponding breaker. If the supplier fails or the breaker rejects the call, the matching fallback can be invoked. `Inventory` and `InventoryClient` are application-defined types; `Inventory.unknown` should represent an indeterminate state rather than faking a zero-inventory result or claiming the item is out of stock.

### Fallback Signature

The fallback method needs a return type compatible with the original method, accepts the business parameters in the same order, and can then accept an additional exception parameter at the end. The example above uses `Throwable` for illustration. You can declare a more specific exception type if you want to handle a particular group of errors separately.

```java
@CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
public Inventory find(String sku) {
    return inventoryClient.fetch(sku);
}

private Inventory inventoryFallback(String sku, CallNotPermittedException cause) {
    return Inventory.temporarilyUnavailable(sku);
}

private Inventory inventoryFallback(String sku, Throwable cause) {
    return Inventory.unknown(sku);
}
```

When multiple fallback overloads exist, Resilience4j looks for the method matching the exception type and the original method's parameters. Ambiguous overloads should be avoided, and signatures should be verified against the library version in use. If no compatible fallback is found, the call may terminate with a fallback configuration error instead of the intended fallback result.

Fallback handles errors for the caller, whereas `recordException` and `ignoreException` rules determine whether an error is counted in Circuit Breaker statistics. An exception ignored in statistics can still be passed to the fallback or the caller; ignoring it does not mean swallowing the exception.

## Conditions for the Annotation to Take Effect

Because the annotation uses Spring AOP, you must ensure AOP integration is included in the application. Typically, the application uses the Resilience4j Spring Boot module compatible with the Spring Boot version and has Spring AOP on the classpath. For example, a common artifact name is `resilience4j-spring-boot3` for Spring Boot 3; Spring Boot 2 applications use the corresponding artifact line from a Resilience4j version supporting Boot 2. Check the documentation and dependency management of the exact version instead of mixing incompatible lines.

Practical conditions to verify:

- The Resilience4j Spring Boot integration and its corresponding aspect are on the runtime classpath.
- Spring AOP is properly configured; if the starter does not pull in the required AOP support, add a compatible AOP dependency.
- The bean is managed by Spring, and calls to the method go through the proxy.
- The name in `@CircuitBreaker(name = "inventory")` matches a configured instance.
- No exclusion configuration or manual bean creation prevents the aspect from being activated.

Spring AOP is proxy-based by default. Internal calls within the same object such as `this.find(sku)` do not go through the proxy and can therefore bypass the aspect. Example:

```java
public Inventory load(String sku) {
    // This internal call may not go through the Spring proxy.
    return this.find(sku);
}
```

If the interceptor needs to apply, call the protected method through another Spring bean or redesign service boundaries so that the call goes through the proxy. Avoid manually fetching the proxy or using workarounds when simply separating responsibilities between two beans is sufficient.

## Configuring Instances for Resilience4j Annotations

You can configure instances by name in `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
```

In this example, the Circuit Breaker retains up to 20 most recent outcomes and starts evaluating once at least 10 calls have been recorded. When the failure rate reaches or exceeds 50%, the breaker can transition to `OPEN`. After the configured wait duration, it can transition to `HALF_OPEN` to test a limited number of calls according to policy.

The name `inventory` in YAML must match the annotation's `name`. These properties belong to Resilience4j configuration; make sure the Spring Boot integration is loading the right configuration file and the version in use supports the chosen properties.

## Spring Cloud CircuitBreaker Using the Factory Programmatically

Spring Cloud Circuit Breaker provides the `CircuitBreakerFactory` abstraction. The application injects the factory and wraps the exact call that needs protection:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CatalogClient catalogClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogService(
            CatalogClient catalogClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogClient = catalogClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public CatalogItem find(String productId) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.find(productId),
            error -> CatalogItem.unavailable(productId)
        );
    }
}
```

Here, `create("catalog")` creates a breaker identified as `catalog`. The supplier contains only the call to the dependency; the fallback is passed inline as a function taking a `Throwable`. This approach does not require annotating the method and does not depend on whether internal calls go through an AOP proxy.

Because the fallback sits right next to the supplier, readers can easily see which code is protected and what the alternative outcome is. On the other hand, if multiple calls need a similar policy, the application may repeat the `run` block or need a helper to avoid duplication. Keep the supplier scope precise: validation, local data processing, or steps unrelated to the dependency do not necessarily belong inside the Circuit Breaker.

## Customizing the Factory When Using the Resilience4j Provider

If the application uses the Resilience4j starter for Spring Cloud Circuit Breaker, you can customize the factory created by the starter using a `Customizer`:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(
                    CircuitBreakerConfig.custom()
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .failureRateThreshold(50)
                        .build()
                )
                .timeLimiterConfig(
                    TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(3))
                        .build()
                )
                .build()
        );
    }
}
```

This customizer applies a default configuration for IDs created by the factory. `CircuitBreakerConfig` controls the sliding window and failure rate; `TimeLimiterConfig` controls the timeout limit in the corresponding integration. The two mechanisms have distinct roles. The builder class name and package must match the Spring Cloud Circuit Breaker Resilience4j version in use.

The factory also provides an API to configure specific IDs in supported versions. When a dependency needs its own policy, configure it by name instead of inadvertently changing every breaker with a shared default. Do not assume that YAML configuration for Resilience4j annotations and factory Customizer configuration are always applied identically; verify the provider's behavior in your project's version.

## Reactive: Factory and Annotation Require the Right API Type

For WebFlux and Reactor, Spring Cloud Circuit Breaker provides `ReactiveCircuitBreakerFactory`. Example:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public Mono<CatalogItem> findReactive(String productId) {
    Mono<CatalogItem> primary = webClient.get()
        .uri("/catalog/{id}", productId)
        .retrieve()
        .bodyToMono(CatalogItem.class);

    return reactiveCircuitBreakerFactory.create("catalog").run(
        primary,
        error -> Mono.just(CatalogItem.unavailable(productId))
    );
}
```

The reactive factory accepts a publisher and a fallback publisher. The pipeline executes the call only when subscribed to; do not use `block()` to retrieve results on the event loop. For Resilience4j annotations, reactive support depends on the Reactor module and how the aspect in the version in use integrates with publishers. Do not infer that synchronous annotations and the reactive factory are the same API. When choosing annotations for `Mono` or `Flux`, verify the documentation for your exact version and test subscription, cancellation, fallback, and metrics.

## Should Both Annotation and Factory Be Placed on the Same Call?

Normally, you should not wrap the same call with both `@CircuitBreaker` and `CircuitBreakerFactory` without a clear purpose. If a method is protected by an aspect and internally calls a factory for the same dependency, a request can pass through two independent or nested Circuit Breakers. This makes metrics, open thresholds, and fallbacks hard to explain.

Example to avoid:

```java
@CircuitBreaker(name = "inventory")
public Inventory find(String sku) {
    return circuitBreakerFactory.create("inventory").run(
        () -> inventoryClient.fetch(sku),
        error -> Inventory.unknown(sku)
    );
}
```

In this snippet, both the outer aspect and the inner factory can manage the same dependency simultaneously. Choose a single point to apply the policy per call. If multiple decorators such as Retry, RateLimiter, Bulkhead, and Circuit Breaker are needed, determine the ordering and responsibility of each layer, and separately track retry counts and actual calls to the dependency.

## Which Approach to Choose for Your Application?

| Need | Usually Suitable Choice |
| --- | --- |
| Want quick protection for a service method and accept AOP mechanics | Resilience4j `@CircuitBreaker`. |
| Want the supplier and fallback clearly visible right at the call site | Spring Cloud `CircuitBreakerFactory.run`. |
| Want to keep business code less directly coupled to Resilience4j and use the Spring Cloud abstraction | `CircuitBreakerFactory` with a configured provider. |
| Want an API to create breakers for Reactor publishers | `ReactiveCircuitBreakerFactory`. |
| Need to swap providers or standardize call patterns across multiple implementations | Spring Cloud Circuit Breaker abstraction. |
| Need direct access to Resilience4j's registry, aspect, and specific features | Resilience4j Spring Boot integration and annotations. |

The choice should be consistent within each service boundary. Annotations can be concise when a policy naturally attaches to a method; the factory is well suited when you want to explicitly determine the supplier block, fallback, or provider in code. Both still require proper timeouts, exception classification, semantically sound fallbacks, and appropriate metrics.

## Integration Checks and Common Errors

When the annotation does not work, check the AOP dependency, bean proxy, internal calls, instance name, and fallback signature. When the factory cannot be injected, check the Spring Cloud Circuit Breaker starter, selected provider, and auto-configuration. When the reactive fallback does not run, check whether the publisher is subscribed to and whether the right reactive factory type is used.

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `@CircuitBreaker` does not open the circuit | Aspect is not loaded or the call bypasses the proxy. | Check AOP dependency, Spring bean, and self-invocation. |
| Fallback not found | Wrong name, parameters, return type, or exception overload. | Compare the fallback signature against the original method. |
| Cannot inject `CircuitBreakerFactory` | Missing starter/provider or mismatched auto-configuration. | Check runtime dependencies and the condition report. |
| Factory uses unexpected thresholds | Customizer or ID-specific configuration is not applied as expected. | Verify the ID, customizer ordering, and version configuration. |
| Double fallback or confusing metrics | The same call is wrapped multiple times. | Establish a single owner of the Circuit Breaker for that call. |
| Reactive request does not execute | Publisher is not subscribed to or the pipeline is blocked in the wrong place. | Check subscription and avoid calling `block()` on the event loop. |

When testing, create cases for success, timeout, server errors, and an `OPEN` Circuit Breaker. Observe the final response, fallback invocation, breaker state, and dependency metrics. A fallback returning a valid response does not mean the primary call succeeded.

## Key Takeaways

Resilience4j's `@CircuitBreaker` is a declarative way to apply policy using annotations and Spring AOP. Spring Cloud's `CircuitBreakerFactory` is a programmatic approach that creates a breaker and wraps a supplier with `run`. They can use the same Resilience4j provider, yet belong to two different integration layers. Understanding this boundary helps you choose the right dependencies, configure instances accurately, avoid double-wrapping, and keep fallbacks and operational metrics easy to explain.
