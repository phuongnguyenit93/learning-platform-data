# Migrating from Direct Provider APIs to an Abstraction When Appropriate

When an application uses Resilience4j directly, services typically depend on types such as CircuitBreakerRegistry, CircuitBreaker, and Resilience4j's execution APIs. This approach gives deep control over configuration, state, events, and metrics. However, it also couples business code directly to a specific library. Spring Cloud CircuitBreaker provides a common abstraction so applications can invoke protection through factories and interfaces while the underlying implementation can be Resilience4j or another Spring Cloud-supported provider.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, migrating from direct provider APIs to the abstraction makes sense when you want to standardize invocation patterns across services, leverage Spring Cloud's OpenFeign integration, or reduce the business layer's coupling to Resilience4j. The migration must be deliberate: the abstraction exposes a common API surface, but it does not automatically turn every provider-specific configuration, annotation, event, and feature into a provider-neutral capability.

## 1. Distinguishing Direct APIs from the Spring Cloud Abstraction

The two approaches have different dependency boundaries:

| Criterion | Direct Resilience4j API | Spring Cloud CircuitBreaker Abstraction |
| --- | --- | --- |
| Injected types | CircuitBreakerRegistry, CircuitBreaker | Spring Cloud's CircuitBreakerFactory and CircuitBreaker interface |
| Instance creation | Look up in the Resilience4j registry | Call factory.create(name) |
| Call execution | executeSupplier, executeCallable, or decorators | run with supplier and fallback |
| Configuration | Resilience4j config, registry, and provider APIs | Configured around the factory abstraction; can still use implementation properties |
| Provider coupling | Calling code directly knows Resilience4j | Calling code depends on Spring Cloud interfaces |
| Advanced feature access | Direct access to state, metrics, events, and registry APIs | Only common surface; provider-specific features require integration or provider APIs |
| Spring Cloud integration | Manual wiring or separate integrations | Shared integration point for clients and services in the Spring Cloud ecosystem |

For example, code using Resilience4j directly might obtain an instance from the registry and call executeSupplier. When migrating to the abstraction, code obtains a Circuit Breaker from the factory and calls run. Both protect an operation, but the object types and API surface differ.

Do not treat the abstraction as a zero-design-cost wrapper. It reduces provider coupling in calling classes, yet configuration and observability pieces may still reflect traits of the underlying implementation.

## 2. When Should You Migrate to the Abstraction?

Migration is generally appropriate when:

- Services invoke Resilience4j in inconsistent ways and need standardized creation, execution, and fallback patterns.
- You want to use built-in Circuit Breaker integration from Spring Cloud OpenFeign or other Spring Cloud components.
- You want the business layer to know only a common Circuit Breaker interface, leaving implementation choice to application configuration.
- You want to reduce provider-specific imports and types in service gateways or adapters.
- The application may switch implementations in the future and you want to confine changes to configuration and integration layers.

Keeping the direct API can be reasonable when:

- Code needs advanced operations on Resilience4j's registry, state machine, event publishers, or custom metrics.
- You rely on specialized Resilience4j decorators or modules that the abstraction does not expose equivalently.
- You need fine-grained control over combining multiple policies and already have a Resilience4j-based architecture.
- Adding an abstraction does not meaningfully reduce coupling or introduces unnecessary translation layers.

Base the decision on the needs of the calling layer. There is no need to rewrite every Resilience4j call site solely for uniform imports if those call sites need the direct API and there is no requirement to swap providers.

## 3. Structure Before Migration

Example of a service depending directly on Resilience4j:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerRegistry registry;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerRegistry registry,
            InventoryClient inventoryClient) {
        this.registry = registry;
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");
        return breaker.executeSupplier(
                () -> inventoryClient.get(sku)
        );
    }
}
~~~

The service directly knows Resilience4j's registry and Circuit Breaker. That is not wrong if Resilience4j is a fixed architectural choice. However, if many services follow this pattern, callers become coupled to the provider and must be updated if moving to the abstraction.

One important note: never create a new registry per request. The registry should be Spring-managed or created once for the application's lifecycle. The example above injects a shared registry and looks up the instance by name.

## 4. Adding the Spring Cloud CircuitBreaker Resilience4j Starter

If the application selects Resilience4j as the implementation for Spring Cloud CircuitBreaker, add the corresponding starter and manage its version through a Spring Cloud release train BOM compatible with Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Do not pick an arbitrary starter version on your own. Use the Spring Cloud BOM matching your project's Spring Boot version and inspect the dependency tree to avoid mixing incompatible release trains or Resilience4j versions.

If the application uses OpenFeign, the OpenFeign dependency is still managed separately. The CircuitBreaker starter provides the implementation for the abstraction; enabling OpenFeign integration is a separate configuration step and must be checked against your Spring Cloud version.

## 5. Migrating from CircuitBreakerRegistry to CircuitBreakerFactory

Once the starter is in place, the caller can depend on Spring Cloud's factory abstraction:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.get(sku),
                failure -> Inventory.unavailable(sku)
        );
    }
}
~~~

Key differences:

1. The caller injects Spring Cloud's CircuitBreakerFactory.
2. The factory creates or retrieves a Circuit Breaker by logical name.
3. The Circuit Breaker interface provides the run method to wrap the supplier.
4. The fallback function receives a Throwable and returns a result of the same type as the primary call.

In the example, InventoryClient is an adapter calling the Inventory service. The fallback returns an unavailable status rather than turning a dependency error into zero stock. In real applications, cached data may be returned if still within business freshness limits.

Do not accidentally import both Resilience4j's CircuitBreaker and Spring Cloud's CircuitBreaker in the same class. Once migrated to the abstraction, calling code should use interfaces from the org.springframework.cloud.client.circuitbreaker package.

## 6. Migrating Fallbacks and Error Semantics

The direct API might call executeSupplier and handle exceptions at the call site:

~~~java
try {
    return breaker.executeSupplier(() -> inventoryClient.get(sku));
} catch (Exception failure) {
    return fallbackInventory(sku, failure);
}
~~~

With the Spring Cloud abstraction, you can pass the fallback directly to run:

~~~java
return circuitBreaker.run(
        () -> inventoryClient.get(sku),
        failure -> fallbackInventory(sku, failure)
);
~~~

When migrating, preserve the error classification policy:

- HTTP 5xx, connectivity errors, and timeouts typically indicate dependency trouble and can be recorded as failures.
- Business errors such as resource-not-found are not necessarily dependency health failures.
- Rejections from Rate Limiter or Bulkhead represent local capacity limits and must be distinguished from external service errors.
- Fallbacks must return the expected data type, preserve business semantics, and never call the failing dependency again.

The abstraction passes a Throwable to the fallback. If the application needs to distinguish specific exceptions, inspect the type or translate the exception into an internal error model before handling it. Do not lose the root cause when migrating from the direct API to the abstraction.

## 7. Keeping Instance-Level Resilience4j Configuration

When the underlying implementation remains Resilience4j, instance configurations can stay in application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

The name passed to factory.create("inventory") must match the configured instance. During migration, do not rename instances arbitrarily because existing dashboards, metrics, and configurations may rely on that name.

Important differences to note:

- Resilience4j config remains provider-specific even though calling code uses the abstraction.
- TimeLimiter, Bulkhead, and other policies can be configured or combined according to the Spring Cloud integration and implementation.
- Configuration via properties vs. Java Customizer follows precedence rules that depend on the Spring Cloud CircuitBreaker version; verify the documentation for your release train.
- Do not assume every Resilience4j property is exposed through the common abstraction.

If you later swap implementations, you will need to re-map policies to the new provider's capabilities. The abstraction does not automatically translate COUNT_BASED semantics, slow-call thresholds, or TimeLimiter into equivalent configurations across all implementations.

## 8. Default Configuration with Customizer

Spring Cloud CircuitBreaker with Resilience4j supports programmatic customization via the factory. Example default configuration for instances:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerDefaults {
    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCustomizer() {
        return factory -> factory.configureDefault(id ->
                new Resilience4JConfigBuilder(id)
                        .circuitBreakerConfig(
                                CircuitBreakerConfig.custom()
                                        .slidingWindowSize(20)
                                        .minimumNumberOfCalls(10)
                                        .failureRateThreshold(50)
                                        .build())
                        .timeLimiterConfig(
                                TimeLimiterConfig.custom()
                                        .timeoutDuration(Duration.ofSeconds(2))
                                        .build())
                        .build());
    }
}
~~~

Customizer is a Resilience4j-bound configuration mechanism, not a provider-neutral API. If the goal is to keep the business layer unaware of the provider, place Customizer classes in configuration packages or infrastructure adapters rather than injecting Resilience4JCircuitBreakerFactory into business services.

When the same property is declared in both properties and a Java Customizer, precedence may vary by Spring Cloud CircuitBreaker version. Do not mix both approaches without explicitly verifying the final effective configuration source. For environment-specific tuning, properties are usually easier to manage; for conditional programmatic setup, a Customizer can be more appropriate.

## 9. Migrating Reactive Calls

If a service uses WebClient and Reactor, use ReactiveCircuitBreakerFactory instead of direct Resilience4j Reactor APIs:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInventoryGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final WebClient inventoryWebClient;

    public ReactiveInventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            WebClient inventoryWebClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<Inventory> getInventory(String sku) {
        ReactiveCircuitBreaker breaker =
                circuitBreakerFactory.create("inventory");

        Mono<Inventory> primary = inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        return breaker.run(
                primary,
                failure -> Mono.just(Inventory.unavailable(sku))
        );
    }
}
~~~

A WebClient publisher is lazy and executes upon subscription. ReactiveCircuitBreaker wraps the primary Mono, and the fallback must return a Mono of the same type. Never call block() or subscribe() manually inside a WebFlux service.

If the application uses Flux streaming, verify which overloads are supported by your version of the Spring Cloud abstraction. Some abstraction APIs focus on Mono; for long-lived or unbounded Flux streams, you may need Resilience4j's Reactor integration directly. That is a valid case for keeping provider-specific APIs inside a dedicated adapter.

## 10. Migrating from Provider-Specific Annotations

An application might currently use Resilience4j's annotation:

~~~java
@io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker(
        name = "inventory",
        fallbackMethod = "fallbackInventory")
public Inventory getInventory(String sku) {
    return inventoryClient.get(sku);
}
~~~

This annotation belongs to Resilience4j and is processed via AOP. It does not automatically become a provider-neutral Spring Cloud CircuitBreaker annotation simply because you added the abstraction starter.

When migrating to the abstraction, you typically move call protection into a gateway or adapter using CircuitBreakerFactory:

~~~java
public Inventory getInventory(String sku) {
    return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.get(sku),
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

If you still retain Resilience4j annotations in some classes, document the usage boundary clearly. Avoid wrapping the same call with both an annotation and the factory abstraction unintentionally; two nested Circuit Breakers create two state machines, two sliding windows, two sets of metrics, and unpredictable fallback behavior.

When migrating off annotations, re-check self-invocation edge cases, AOP ordering, fallback method signatures, and which exceptions are retried or ignored. An integration test should confirm that the fallback still receives the right root cause and that state updates on the intended instance.

## 11. OpenFeign Integration via the Abstraction

Spring Cloud OpenFeign can integrate with Circuit Breakers through Spring Cloud CircuitBreaker when the corresponding feature is enabled:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Once enabled, Feign methods can be wrapped by Circuit Breakers created from the abstraction. Instance names depend on the naming resolver and Spring Cloud version; verify runtime IDs against Resilience4j configuration keys.

This integration is helpful when you want consistent Circuit Breaker protection across Feign calls. However, do not manually wrap a Feign call with an outer service-level Circuit Breaker while also letting OpenFeign wrap the same call, unless you intentionally want two independent protection layers. Double wrapping makes failure rates, fallbacks, and timeouts hard to reason about.

## 12. Safe Migration Roadmap

You do not need to change the entire system at once. Migrate dependency by dependency:

1. List all places injecting CircuitBreakerRegistry or using Resilience4j annotations.
2. Separate call sites that only need basic execution and fallback from those requiring advanced APIs like events, state access, or Reactor operators.
3. Pick one representative gateway to migrate to CircuitBreakerFactory.
4. Add the Spring Cloud CircuitBreaker Resilience4j starter and confirm compatible dependency versions.
5. Keep instance names stable and verify YAML keys against the names created by the factory.
6. Migrate the supplier, fallback, and exception mapping; ensure result semantics remain unchanged.
7. Check TimeLimiter, Bulkhead, Retry, and policy ordering if the call combines multiple mechanisms.
8. Test success, HTTP 5xx, timeout, OPEN, HALF_OPEN, and fallback paths.
9. Compare metrics before and after migration to catch changes in instance counts, tags, or failure rates.
10. Migrate subsequent gateways once the first pattern is proven.

During the transition, avoid routing the same request through both the old and new Circuit Breakers. If behavioral comparison is needed, run controlled tests or shadow measurements rather than stacking two active protection layers in production without an explicit design.

## 13. Post-Migration Verification

After migrating a call to the abstraction, verify:

| Item | Expected Outcome |
| --- | --- |
| Dependency injection | Caller receives CircuitBreakerFactory or ReactiveCircuitBreakerFactory |
| Instance name | Factory ID matches configured instance |
| Configuration | Window, thresholds, wait duration, and timeout match the previous policy |
| Success | Supplier returns result and Circuit Breaker records success |
| Dependency failure | Exception flows through the abstraction and is recorded per policy |
| Fallback | Triggered at the right time, returns the right type, and does not re-call the failing dependency |
| OPEN | Calls are rejected before reaching the dependency |
| HALF_OPEN | Trial call count follows configuration |
| Metrics and events | Instance names, states, and metrics are observed accurately |
| Additional policies | Retry, TimeLimiter, and Bulkhead are neither lost nor applied twice |

Do not verify solely that the final API returns HTTP 200. A fallback can make the request succeed at the protocol level while the dependency is failing. Inspect state, metrics, fallback counts, and root-cause logs.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Changing only imports while keeping old instance creation | Caller remains coupled to the provider or bypasses the factory | Switch to CircuitBreakerFactory and Spring Cloud interfaces |
| Confusing Resilience4j's CircuitBreaker with Spring Cloud's | Wrong API types or calling the wrong methods | Use the proper package along the abstraction boundary |
| Assuming the abstraction translates all config automatically | Thresholds or timeouts stop matching | Cross-check properties and runtime config |
| Renaming instances during migration | Configurations and dashboards no longer match | Keep IDs stable or update everything in sync |
| Wrapping the same call twice | Overlapping state machines, fallbacks, and metrics | Keep one protection layer per target |
| Keeping the annotation and adding the factory on the same method | AOP and the abstraction both wrap one call | Define clear migration boundaries |
| Migrating fallback while losing the original exception | Difficult to distinguish business errors from dependency errors | Preserve Throwable and classify explicitly |
| Using the abstraction for unexposed advanced APIs | Loss of needed events or operators | Keep provider APIs inside a clearly bounded adapter |
| Converting Flux streaming to Mono via unbounded collectList | Buffers entire stream in memory | Collect only when bounded; otherwise use a Flux-capable integration |
| Skipping checks on Retry/TimeLimiter/Bulkhead ordering | Behavior and metrics shift after migration | Test execution ordering and exception types |

## 15. Conclusion

The Spring Cloud CircuitBreaker abstraction fits best when calling code only needs a uniform contract to create Circuit Breakers, execute suppliers, and handle fallbacks. It reduces provider coupling and connects cleanly with Spring Cloud integrations. Direct Resilience4j APIs remain valuable when the application needs specialized registries, events, state access, operators, or policies.

A sound migration preserves protection semantics: instance names, sliding windows, failure thresholds, timeouts, fallbacks, and exception classification. Migrate one gateway at a time, verify runtime behavior and metrics after each step, and confine provider-specific APIs to the infrastructure layer whenever the abstraction does not cover a requirement. This lets the application benefit from the abstraction while retaining full control over service protection behavior.
