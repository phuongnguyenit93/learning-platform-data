# Distinguishing the Spring Cloud Starter from the Direct Resilience4j Starter

In Spring Cloud Circuit Breaker, Resilience4j is a Circuit Breaker execution engine; Spring Cloud adds a unified API layer for the application to invoke the breaker. Both the Spring Cloud CircuitBreaker starter and the Resilience4j Spring Boot starter can bring Resilience4j into an application, yet they provide different integration styles and APIs.

Distinguishing these two options right at the environment setup step helps avoid declaring unnecessary dependencies, calling the wrong API, or accidentally wrapping a call with multiple Circuit Breakers. The goal of both is to protect slow or unavailable dependent services, curb cascading failures, and allow the application to return a controlled fallback.

## 1. Two Starters Solve Two Different Integration Needs

**Spring Cloud CircuitBreaker with Resilience4j** places an abstraction layer between application code and the Circuit Breaker library. The application creates breakers via `CircuitBreakerFactory` or `ReactiveCircuitBreakerFactory`. The starter auto-configures the Resilience4j implementation and provides the corresponding factories. This approach is useful when an application wants to use Spring Cloud's API and maintain lower coupling to the underlying implementation.

**The direct Resilience4j Spring Boot starter** integrates Resilience4j into Spring Boot directly. The starter provides auto-configuration, registries, and annotations such as `@CircuitBreaker`, `@Retry`, `@RateLimiter`, and `@Bulkhead` via Spring AOP. The application uses Resilience4j annotations or APIs directly, which fits when you want to use library-specific capabilities without the Spring Cloud abstraction layer.

| Criterion | Spring Cloud CircuitBreaker + Resilience4j | Direct Resilience4j Spring Boot |
| --- | --- | --- |
| Primary API | `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory` | `@CircuitBreaker`, `CircuitBreakerRegistry`, Resilience4j API |
| How calls are protected | Wrap calls using the factory and a fallback callback | Annotate methods or call the registry/API directly |
| Integration scope | Spring Cloud abstraction layer with the selected implementation | Direct integration of the Resilience4j library into Spring Boot |
| Reactive | Use the Reactor starter and `ReactiveCircuitBreakerFactory` | Add `resilience4j-reactor` to support Reactor `Mono`/`Flux` |
| Configuration | Use Resilience4j properties and optionally customize the factory with `Customizer` | Use Resilience4j properties and the library's customizers/registries |

Neither option is automatically better in every project. Choose based on the API your application code needs to use and your existing Spring architecture.

## 2. Declaring Dependencies for Spring Cloud CircuitBreaker

For a Spring MVC application or synchronous calls, use the non-reactive starter:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
}
```

For a WebFlux application using Reactor, replace it with the reactive starter:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j'
}
```

In both cases, manage Spring Cloud versions with a Spring Cloud BOM compatible with your project's Spring Boot version. Example Gradle Groovy configuration:

```groovy
ext {
    set('springCloudVersion', '<compatible-spring-cloud-release-train>')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}
```

Replace the placeholder with a compatible release train published in the support matrix for your project's Spring Cloud and Spring Boot versions. Do not pick individual starter versions on your own or mix different release trains.

### Spring Cloud Factory API

Example protecting an inventory lookup call with `CircuitBreakerFactory`: 

```java
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

    public Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
```

`create("inventory")` retrieves the breaker with ID `inventory`. The first function executes the call to the dependent service; the second handles errors to produce a fallback result. When the breaker is `OPEN`, the call is rejected fast and the fallback can return an undetermined stock state. When `HALF_OPEN`, only permitted probe calls reach the service.

With Reactor, use `ReactiveCircuitBreakerFactory` to wrap `Mono` or `Flux`. Choose the reactive starter when the application needs this API; do not assume that merely having WebFlux in the application means every call is automatically protected.

## 3. Declaring Dependencies for Direct Resilience4j

With Spring Boot 3, the direct starter is `io.github.resilience4j:resilience4j-spring-boot3`. The Resilience4j documentation requires Actuator and Spring AOP to be present at runtime:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-spring-boot3'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Manage Resilience4j module versions with the Resilience4j BOM so modules in the same family use compatible versions:

```groovy
dependencyManagement {
    imports {
        mavenBom "io.github.resilience4j:resilience4j-bom:${resilience4jVersion}"
    }
}
```

Choose the starter matching your Spring Boot major version. For Spring Boot 2, Resilience4j documentation uses the `resilience4j-spring-boot2` module; for Spring Boot 3, use `resilience4j-spring-boot3`. Do not guess module names if the project uses a different version line.

If the application uses WebFlux and needs to protect `Mono`/`Flux` via Resilience4j's Reactor integration, add the module:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-reactor'
}
```

### Resilience4j Annotation API

The direct starter allows placing annotations on Spring-managed methods:

```java
@Service
public class InventoryService {
    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    Stock inventoryFallback(String sku, Throwable cause) {
        return Stock.unavailable(sku);
    }
}
```

`fallbackMethod` must have the original method's parameters plus an exception parameter at the end; its return type must match the protected method. Annotations are applied via Spring AOP, so the method must be invoked through the Spring proxy. Self-invocation calls such as `this.getStock(...)` inside the same bean bypass the AOP proxy normally and can skip the aspect.

If you want programmatic control instead of annotations, you can retrieve an instance from `CircuitBreakerRegistry` and call `executeSupplier`, `executeCallable`, or the corresponding API. That is Resilience4j's API, not Spring Cloud's `CircuitBreakerFactory`.

## 4. Configuring Circuit Breaker Properties

Both integration approaches can use Resilience4j instance configuration in `application.yml`. For example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

The ID `inventory` must match the instance name referenced in code. In this configuration, the breaker records up to 20 outcomes in a count-based window, evaluates failure rate only after at least 10 calls, and opens the circuit when the failure rate reaches the 50% threshold. After at least 15 seconds in `OPEN`, up to three calls are permitted to probe in `HALF_OPEN`.

With Spring Cloud CircuitBreaker, you can create default or per-ID configuration using `Customizer<Resilience4JCircuitBreakerFactory>`; for reactive, use `Customizer<ReactiveResilience4JCircuitBreakerFactory>`. Spring Cloud CircuitBreaker properties take precedence over Java `Customizer` configuration. Therefore, if the running values differ from those in a customizer bean, check the properties configuration by ID and group.

With direct Resilience4j, properties bind to Resilience4j's Spring Boot configuration. Specialized customizers such as `CircuitBreakerConfigCustomizer` can be used to tailor instances when needed. Avoid declaring multiple configuration sources for the same property unless the development team has a clear convention on precedence.

## 5. Choosing a Starter by Application Style

**Choose Spring Cloud CircuitBreaker** when the application already uses Spring Cloud, wants to invoke Circuit Breakers via a factory, wants to keep code at the Spring Cloud abstraction layer, or needs the option to swap implementations supported in the release train.

**Choose direct Resilience4j Spring Boot** when the application wants to use the `@CircuitBreaker` annotation, registries, or Resilience4j-specific APIs; when Spring Cloud's factory abstraction is not needed; or when configuring Resilience4j modules directly.

**For reactive applications**, decide based on the desired API: Spring Cloud uses the `reactor-resilience4j` starter and `ReactiveCircuitBreakerFactory`; direct Resilience4j requires the `resilience4j-reactor` module for Reactor integration. Check both method return types and how fallbacks are written to avoid unintentionally converting `Mono`/`Flux` to synchronous types.

Do not wrap the same call with both a Spring Cloud Circuit Breaker and a Resilience4j `@CircuitBreaker` annotation without a clear design. Two protection layers can have independent sliding windows, failure thresholds, and states, making blocked call counts or fallbacks hard to explain. If a project has a reason to use both APIs in different areas, clearly establish which layer owns each call.

## 6. Actuator, Health, and Metrics

Actuator provides health endpoints and integration points for application observability. To export Resilience4j metrics via Micrometer, add `spring-boot-starter-actuator` and `resilience4j-micrometer` according to the guide for your version. With `registerHealthIndicator: true`, Circuit Breaker state can be included in health information if the health endpoint is configured accordingly.

Example metrics dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.github.resilience4j:resilience4j-micrometer'
}
```

Monitor at least the number of `CLOSED`/`OPEN`/`HALF_OPEN` transitions, succeeded and failed call counts, rejected call counts, fallback counts, and dependent service latency. Seeing the health endpoint up is not enough to conclude the Circuit Breaker is protecting properly; verify metrics and actual call behavior.

Do not expose detailed Actuator endpoints to public networks without proper authentication and authorization mechanisms. Expose only the endpoints needed for the deployment environment.

## 7. Verifying Configuration After Adding a Starter

Run verification in a development or test environment with a simulated dependent service:

1. Inspect the dependency tree to confirm only starters and versions compatible with the chosen Spring Boot/Spring Cloud versions are present. For Spring Cloud, confirm the BOM manages the right release train; for direct Resilience4j, confirm modules share an appropriate BOM.
2. Start the application and confirm Spring creates the corresponding factory bean or required Resilience4j beans/registries. If using annotations, verify Spring AOP is present and methods are invoked through the proxy.
3. Configure an instance with ID `inventory`, induce controlled errors in the mock service, and send enough calls to cross the threshold. Confirm the circuit transitions from `CLOSED` to `OPEN`.
4. Send calls while the circuit is `OPEN`; confirm the dependent service receives no further requests and the fallback returns the expected format.
5. After the wait duration, send probe calls; confirm recovery outcomes return the circuit to `CLOSED`, while continued errors send the circuit back to `OPEN`.
6. Check health and metrics if Actuator/Micrometer is configured; confirm the displayed ID matches the instance in configuration.

## 8. Common Configuration Mistakes

- Mistakenly using the non-reactive starter when the code requires `ReactiveCircuitBreakerFactory`, or missing `resilience4j-reactor` when integrating Reactor directly.
- Mixing a Spring Cloud release train with an incompatible Spring Boot version, or manually pinning starter versions so the dependency tree drifts out of sync.
- Declaring `@CircuitBreaker` without `spring-boot-starter-aop`, or calling a method via self-invocation so Spring AOP does not apply the aspect.
- An ID in code differing from the ID in `resilience4j.circuitbreaker.instances`, causing the intended configuration not to apply to the running instance.
- Having multiple Circuit Breaker layers wrap the same call, making states, fallbacks, and metrics hard to track.
- Assuming a fallback execution means the dependent service has recovered. A fallback only handles the outcome of a protected call; service health and call outcomes must be observed separately.

## References

- [Spring Cloud CircuitBreaker – Spring Cloud Commons](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): Abstraction API, `CircuitBreakerFactory`, and integration concepts.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/docs/current/reference/html/spring-cloud-circuitbreaker-resilience4j.html): Reactive/non-reactive starters, factories, properties configuration, customizers, and metrics.
- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): Direct dependencies, Actuator, AOP, Reactor, and annotations.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): States, sliding windows, failure thresholds, and state machine configuration.
