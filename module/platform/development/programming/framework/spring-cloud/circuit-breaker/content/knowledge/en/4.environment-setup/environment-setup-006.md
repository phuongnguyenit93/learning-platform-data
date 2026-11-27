# Adding Actuator, Micrometer, and Required Dependencies for Each Experiment

When implementing Spring Cloud CircuitBreaker, an application needs an implementation library to protect calls to dependent services. To observe the protection mechanism, you need to add Spring Boot Actuator and Resilience4j's metrics integration with Micrometer. If you want Prometheus to collect metrics, the application also needs the corresponding registry. Each experiment may require additional specific dependencies, such as the reactive starter or a library for testing `Mono` and `Flux` flows.

This lesson prepares the baseline dependencies and configuration for the **SPRING_CLOUD_CIRCUIT_BREAKER** module. The goal is to enable the application to run synchronous or reactive circuit breaker experiments, inspect state via Actuator, and export metrics to observe service protection effectiveness.

## 1. Role of Each Component

| Component | Role in the Experiment |
|---|---|
| Spring Cloud CircuitBreaker | Provides a unified API for wrapping calls to dependent services. |
| Resilience4j | Implements the circuit breaker and mechanisms such as Retry, Bulkhead, TimeLimiter, and RateLimiter. |
| Spring Boot Actuator | Provides management endpoints such as `/actuator/health`, `/actuator/metrics`, and the Prometheus endpoint when an appropriate registry is present. |
| Micrometer | Provides a metrics API for applications and libraries to record metrics in a backend-agnostic manner. |
| Micrometer Prometheus Registry | Converts Micrometer metrics into a format that Prometheus can scrape. |
| Spring WebFlux and Reactor | Provides the reactive model for practicing asynchronous calls with `Mono` or `Flux`. |

Actuator and Micrometer have different roles. Actuator publishes management endpoints; Micrometer collects and standardizes metrics. Adding Actuator alone does not mean all Resilience4j-specific metrics are registered. A Resilience4j-Micrometer integration compatible with your library version is required.

## 2. Managing Versions Before Adding Dependencies

Spring Boot, Spring Cloud, and Resilience4j have version relationships. Before adding libraries, identify your project's Spring Boot version and use a compatible Spring Cloud BOM to manage Spring Cloud starters. Do not arbitrarily mix Spring Cloud release trains or override transitive Resilience4j versions with a different version.

With Maven, the project usually already declares the Spring Boot parent or Spring Boot dependency management and the Spring Cloud BOM in `dependencyManagement`. An example Spring Cloud BOM declaration looks like:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

The `spring-cloud.version` value must be a release train compatible with the Spring Boot version in use. If the project already has a BOM, keep a single consistent version management source rather than declaring duplicate BOMs. When you need to add a Resilience4j module directly, use the BOM or version management mechanism chosen by the project so Resilience4j modules share the same version.

## 3. Baseline Dependencies for Circuit Breaker and Observability

For a Spring MVC application or imperative calls, basic Maven dependencies may include:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Meaning of the dependencies:

- `spring-cloud-starter-circuitbreaker-resilience4j` provides the Spring Cloud CircuitBreaker integration with Resilience4j for imperative calls.
- `spring-boot-starter-actuator` enables Spring Boot's management components and metrics integration.
- `resilience4j-micrometer` provides the adapter from Resilience4j metrics to Micrometer. Check the dependency tree to see if the starter or current configuration already provides this module; avoid duplicate declarations or forcing incompatible versions.
- `micrometer-registry-prometheus` provides the registry to export metrics in Prometheus format. This dependency serves the Prometheus scenario; if using another backend, choose the corresponding registry or omit the Prometheus registry.

If you only need to inspect health and metrics through Actuator without exporting metrics to Prometheus, you may skip `micrometer-registry-prometheus` for now. If the application does not automatically configure a Resilience4j metrics binder from the current setup, add `resilience4j-micrometer` according to the guide for the Resilience4j version in use.

## 4. Adding Dependencies Per Experiment

Not every application needs every starter. Choose dependencies based on the call model and practice content:

| Experiment | Dependencies or Components to Add | Notes |
|---|---|---|
| Imperative circuit breaker | `spring-cloud-starter-circuitbreaker-resilience4j` | Used for synchronous calls, such as a client returning a direct result object. |
| Reactive circuit breaker | `spring-cloud-starter-circuitbreaker-reactor-resilience4j` | Used when calls return `Mono` or `Flux`; requires WebFlux/Reactor in the application. |
| Health and metrics | `spring-boot-starter-actuator`, `resilience4j-micrometer` | Actuator exposes endpoints; the binder records Resilience4j metrics into Micrometer. |
| Scraping with Prometheus | `micrometer-registry-prometheus` | Add only when you want to export metrics in Prometheus format. |
| Application testing | `spring-boot-starter-test` with scope `test` | Provides the Spring Boot, JUnit, and Mockito testing foundation per project configuration. |
| Reactive testing | `reactor-test` with scope `test` | Supports testing publishers with `StepVerifier`. |
| Dependent service fault testing | Mock client, WireMock, or MockWebServer | Choose a suitable tool to simulate timeouts, HTTP errors, and recovery. |

If using reactive, the corresponding Spring Cloud dependency is:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
```

Do not replace the imperative starter with the reactive one just because the application uses `CompletableFuture`. The reactive starter is for Reactor flows; the choice depends on the client's data types and execution model. If the same application has both types of calls, verify compatible starters in the dependency tree and configure only the parts actually used.

For Retry, Bulkhead, TimeLimiter, or RateLimiter experiments, Spring Cloud CircuitBreaker and Resilience4j may provide part of the integration through the starter. If the exercise calls Resilience4j APIs directly, you may need corresponding modules such as `resilience4j-retry`, `resilience4j-bulkhead`, `resilience4j-timelimiter`, or `resilience4j-ratelimiter`. Inspect existing modules in the dependency tree before adding them manually. Modules in the same family must use synchronized versions.

## 5. Configuring Actuator and Micrometer

After adding dependencies, configure the needed endpoints in `application.yml`:

```yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
  metrics:
    tags:
      application: ${spring.application.name}

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 8
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
```

In the configuration above:

- `health` provides application health information and registered health indicators.
- `metrics` allows querying meters via Actuator.
- `prometheus` exposes the Prometheus endpoint when the corresponding registry is present.
- `application` is a common tag helping distinguish metrics from different applications pushed to the same backend.
- `registerHealthIndicator: true` registers a health indicator for the `inventory` circuit breaker if the integration version in use supports this setting.

Expose only necessary endpoints. In environments using Spring Security, configure access permissions for management endpoints according to your application's policy; do not leave endpoints containing sensitive operational information publicly accessible. `show-details: when-authorized` restricts showing health details according to the configured authentication and authorization mechanism.

A circuit breaker's health indicator reflects dependency status via the circuit. An `OPEN` circuit may cause the dependent component's health to report unhealthy even though the application process continues running normally. When deploying readiness and liveness probes, clearly decide whether circuit breaker state should affect traffic readiness. You should not let a single dependent service's failure cause a liveness probe to repeatedly restart an application that can still serve other functions.

## 6. Verifying Endpoints After Startup

After running the application with an appropriate configuration profile, you can inspect the exposed endpoints. For example, when Actuator uses the default port and context path:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
```

Expected results:

- `/actuator/health` returns aggregated health status. If the Resilience4j health indicator is enabled, check the corresponding details when using an authorized account.
- `/actuator/metrics` lists registered meters. You can query a specific meter using a name returned in the list.
- `/actuator/prometheus` returns text data for Prometheus scraping, if the Prometheus registry is added and the endpoint is exposed.

Specific meter names and tags depend on the Resilience4j version, Micrometer, and binder configuration. Metric groups commonly monitored include succeeded, failed, and rejected-when-open call counts, failure rate, slow-call rate, and circuit breaker state. Do not assume a meter exists just because the Actuator endpoint returns HTTP 200; inspect the meter list and confirm numbers change when running test calls.

If `/actuator/metrics` works but circuit breaker metrics are missing, check the `resilience4j-micrometer` module, binder auto-configuration, instance name, and whether calls actually pass through the circuit breaker. If `/actuator/prometheus` returns 404, check the Prometheus registry and exposure configuration. If endpoints are denied, check security rules, management port, and context path.

## 7. Preparing the Circuit Breaker and Fallback Experiment

A basic experiment needs a client calling a dependent service and a named circuit breaker. You can use a mock client in a unit test or a mock service to deliberately produce success, error, and latency responses.

Example declaring an imperative service:

```java
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

    public Stock findStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.findStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
```

In the experiment, vary the behavior of `InventoryClient` across scenarios:

1. Return successful results to observe successful call counts and the `CLOSED` state.
2. Throw exceptions or return connection errors enough times to exceed the threshold, then confirm the circuit transitions to `OPEN` and subsequent calls are rejected early.
3. Let the primary call fail to confirm the fallback returns a business-meaningful fallback state.
4. Restore the client after the wait duration to observe probe calls in `HALF_OPEN`.

Cross-reference each scenario with `/actuator/health`, `/actuator/metrics`, or Prometheus data. Metrics should change in step with actual calls; a fallback being invoked does not mean the call to the dependent service succeeded.

## 8. Preparing the Reactive Experiment

If the application uses WebFlux, the client should return `Mono` or `Flux` and the service should use `ReactiveCircuitBreakerFactory`. Add `reactor-test` in `test` scope to test publishers without calling `block()`.

Example test with `StepVerifier`:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveInventoryServiceTest {
    @Test
    void returnsFallbackWhenDependencyFails() {
        Mono<Stock> result = Mono.just(Stock.unavailable("SKU-1"));

        StepVerifier.create(result)
            .expectNextMatches(stock -> !stock.isAvailable())
            .verifyComplete();
    }
}
```

The test snippet above illustrates how to assert that a publisher emits a fallback result; in a complete practice exercise, replace the directly constructed `Mono` with a service call wrapped by a circuit breaker and mock the client to control failures. Use `StepVerifier` to verify values, errors, and completion signals according to reactive semantics. Do not block the event loop with `block()` in the application's reactive code.

## 9. Checking Dependencies and Troubleshooting Configuration Errors

Once dependencies are added, you can use Maven to inspect the actual modules the project receives:

```bash
mvn dependency:tree
```

Look for `spring-cloud-starter-circuitbreaker`, `resilience4j`, `spring-boot-starter-actuator`, `micrometer-core`, and the chosen registry. If the same module appears with multiple versions, review the BOM and any overriding dependencies. Do not manually add a new version just to work around a runtime error without identifying the cause of the conflict.

Some common situations:

| Symptom | Points to Check |
|---|---|
| Cannot inject `CircuitBreakerFactory` | Is the Resilience4j starter on the runtime classpath; are the dependency and Spring Cloud versions compatible? |
| Cannot inject `ReactiveCircuitBreakerFactory` | Have the reactive starter and required Reactor dependencies been added? |
| Health does not display the circuit breaker | Is `registerHealthIndicator` enabled on the instance; does the provider version have a corresponding health indicator? |
| Circuit breaker metrics do not appear | Are `resilience4j-micrometer` and a compatible binder present; do calls go through the circuit breaker? |
| Prometheus endpoint does not exist | Has `micrometer-registry-prometheus` been added and `prometheus` exposed? |
| Application cannot access endpoints | Check security, management port, base path, and exposed endpoint list. |

## 10. Checklist Before Starting Practice

- [ ] Spring Boot and Spring Cloud use compatible versions, consistently managed by a BOM.
- [ ] The application has the Resilience4j starter matching its imperative or reactive call style.
- [ ] Actuator is added and only necessary endpoints are exposed.
- [ ] Resilience4j-Micrometer is integrated to record circuit breaker metrics.
- [ ] Prometheus registry is added if the experiment requires Prometheus scraping.
- [ ] Circuit breaker instance configuration has a name matching the identifier in code.
- [ ] A mock client or service is available to produce success, failure, timeout, and recovery.
- [ ] For reactive, `reactor-test` is present and publishers are tested with `StepVerifier`.
- [ ] Endpoints and metrics have been confirmed to update after running an actual call.

Once these preparation steps are complete, the environment has a solid foundation for practicing circuit breaker states, fallbacks, timeouts, bulkheads, and observing protection effectiveness. Add dependencies per experiment, keep versions synchronized, and verify numbers with the configured endpoints before introducing protection mechanisms into real services.
