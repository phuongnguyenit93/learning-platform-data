# Comparing Supported Implementations in the Right Spring Cloud Release Train

Spring Cloud Circuit Breaker provides a common API for applications to invoke a Circuit Breaker, while the actual execution is supplied by different implementations. Each Release Train manages a Spring Cloud Circuit Breaker version corresponding to a specific range of Spring Boot and Spring Framework versions. Therefore, the list of implementations, starters, and reactive capabilities must be verified in the documentation of the exact train that the application uses.

You should not take an implementation list from an old documentation page and apply it to every project. For example, older documentation once listed Netflix Hystrix; current Spring Cloud Circuit Breaker documentation has moved on to other implementations. Similarly, Spring Framework Retry only appears in the Spring Framework 7 lines corresponding to Spring Boot 4, not in every Spring Cloud train.

## 1. Identify the Right Release Train Before Choosing an Implementation

Follow this order: identify the application's Spring Boot version, choose a compatible Spring Cloud Release Train, import the Spring Cloud BOM, and then check the `spring-cloud-circuitbreaker` version managed by that train. The project documentation linked from the Release Train page is the primary reference for starters and features.

Examples of GA versions published in the Spring documentation at the time of writing:

| Spring Cloud Release Train | Supported Spring Boot in Train Docs | spring-cloud-circuitbreaker Version | Implementation Catalog in Project Docs |
| --- | --- | --- | --- |
| `2026.0.0` | `4.2.0` | `5.1.0` | Resilience4J, Spring Retry, Spring Framework Retry |
| `2025.1.5` | `4.0.10` | `5.0.3` | Resilience4J, Spring Retry, Spring Framework Retry |
| `2025.0.3` | `3.5.15` | `3.3.3` | Resilience4J, Spring Retry |
| `2024.0.x` | Spring Boot `3.4.x` | Spring Cloud Circuit Breaker `3.2.x` | Refer to the `3.2.x` project documentation |
| `2023.0.x` | Spring Boot `3.3.x`/`3.2.x` | Spring Cloud Circuit Breaker `3.1.x` | Refer to the `3.1.x` project documentation |

This table helps orient your version selection; open the Release Train page and the project reference for the exact patch you are using before adding dependencies. Trains may receive patch updates, and the `current` documentation may already point to a newer train.

The current Release Train page also links directly to the project versions managed by that train. For instance, `2026.0.0` links to Circuit Breaker `5.1.0`, while `2025.1.5` links to `5.0.3`. For `2025.0.3`, the train page links to `3.3.3`. This is more reliable than manually picking a latest starter version from Maven Central.

## 2. Implementations Listed in the Current Circuit Breaker Project

The Spring Cloud Circuit Breaker `5.1.0` documentation lists three implementations: Resilience4J, Spring Retry, and Spring Framework Retry. Both the `5.0.x` and `5.1.x` lines align with Spring Boot 4/Spring Framework 7. The `3.3.x` line documentation for Spring Boot 3.5 lists Resilience4J and Spring Retry; Framework Retry is not in the catalog for that line.

| Implementation | Execution Foundation | Strengths | Limitations to Verify |
| --- | --- | --- | --- |
| Resilience4J | Standalone fault-tolerance library wrapped by Spring Cloud via a factory | Circuit Breaker, sliding window, slow-call detection, TimeLimiter, Bulkhead, RateLimiter; supports blocking and reactive | Must choose the right reactive/non-reactive starter; configuration and extension modules depend on classpath dependencies |
| Spring Retry | `CircuitBreakerRetryPolicy`, stateful retry, and `RetryTemplate` | Fits applications already using Spring Retry that need to reuse `RetryPolicy`, `RetryTemplate`, and listeners | API is centered on synchronous calls; do not assume a reactive factory exists in the train unless stated in the docs |
| Spring Framework Retry | Native Spring Framework 7 `RetryTemplate` and `RetryPolicy`, augmented with Circuit Breaker state by Spring Cloud | Clean integration with Spring Framework 7, offering retry policy, backoff, and open-circuit timeout | Only for trains using Spring Framework 7; does not support reactive applications |

All three implementations are accessed through the Spring Cloud abstraction, but they do not share the same configuration model. Resilience4J uses `resilience4j.circuitbreaker.*` and `resilience4j.timelimiter.*` properties; Spring Retry uses `SpringRetryConfigBuilder`; Framework Retry uses `FrameworkRetryConfigBuilder`. Do not copy Resilience4J YAML to the two Retry implementations and expect it to bind.

## 3. Resilience4J: The Full-Featured Option for Blocking and Reactive

Resilience4J has the broadest feature set in the Spring Cloud Circuit Breaker catalog. It fits when an application needs a sliding-window Circuit Breaker, slow-call classification, TimeLimiter, Bulkhead, or RateLimiter, or needs the same implementation for both Spring MVC and WebFlux.

Spring Cloud provides two starters:

```groovy
dependencies {
    // Spring MVC or synchronous calls
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'

    // WebFlux/Reactor
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j'
}
```

Add only the starter matching the type of calls you need to protect. The non-reactive starter provides `Resilience4JCircuitBreakerFactory`; the Reactor starter provides `ReactiveResilience4JCircuitBreakerFactory`. If your application requires both call styles, check the guide for your exact train to see whether both starters and their corresponding factory beans can be used simultaneously.

Example of configuring a Circuit Breaker by ID:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

The ID `inventory` must match the ID passed to `circuitBreakerFactory.create("inventory")` or `reactiveCircuitBreakerFactory.create("inventory")`. These properties are Resilience4J configuration; they do not automatically apply to Spring Retry or Framework Retry.

Example of customizing the synchronous factory:

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryCustomizer() {
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
```

For reactive code, use `ReactiveResilience4JCircuitBreakerFactory` and return `Mono`/`Flux` through `ReactiveCircuitBreaker`. Do not use the synchronous `CircuitBreakerFactory.run` to wrap a publisher and assume the asynchronous outcome is observed.

Resilience4J Bulkhead is only applied by Spring Cloud when the `resilience4j-bulkhead` module is on the classpath and Bulkhead integration is enabled. The Resilience4J documentation describes `SemaphoreBulkhead` and `FixedThreadPoolBulkhead`; verify the default configuration for your exact train before relying on a specific implementation.

## 4. Spring Retry: Reusing RetryTemplate and Stateful Retry

Spring Retry provides `CircuitBreakerRetryPolicy` combined with `DefaultRetryState`. Spring Cloud creates `SpringRetryCircuitBreakerFactory`, allowing you to configure `RetryPolicy` via `SpringRetryConfigBuilder` and customize `RetryTemplate` after creation.

The published starter for Spring Retry:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-spring-retry'
}
```

Example of setting a default retry policy:

```java
@Bean
Customizer<SpringRetryCircuitBreakerFactory> retryCustomizer() {
    return factory -> factory.configureDefault(id ->
            new SpringRetryConfigBuilder(id)
                    .retryPolicy(new SimpleRetryPolicy(2))
                    .build());
}
```

The example above illustrates configuring `RetryPolicy`; choose a retry policy based on the service's exceptions, retry count, and backoff. You can add a `RetryListener` via `addRetryTemplateCustomizers` to observe attempts or attach operational behavior.

Spring Retry fits when the system has standardized on Spring Retry-based retry policies or needs `RetryTemplate` integration. When comparing it with Resilience4J, evaluate how the implementation tracks failures and transitions states, retry counts, backoff, fallback, and reactive support. Do not assume it shares the same `slidingWindowSize`, `slowCallRateThreshold`, or `TimeLimiter` properties as Resilience4J.

## 5. Spring Framework Retry: Implementation Based on Spring Framework 7

Spring Framework 7 adds native retry with `RetryTemplate` and `RetryPolicy`. Spring Cloud Circuit Breaker provides the Framework Retry implementation to add `CLOSED`, `OPEN`, and `HALF_OPEN` states to this retry mechanism.

Starter:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-framework-retry'
}
```

Example of default configuration:

```java
@Bean
Customizer<FrameworkRetryCircuitBreakerFactory> frameworkRetryCustomizer() {
    return factory -> factory.configureDefault(id ->
            new FrameworkRetryConfigBuilder(id)
                    .retryPolicy(RetryPolicy.withMaxRetries(3)
                            .withBackoff(Duration.ofMillis(100), 2.0))
                    .openTimeout(Duration.ofSeconds(20))
                    .resetTimeout(Duration.ofSeconds(5))
                    .build());
}
```

Key properties:

| Property | Meaning |
| --- | --- |
| `retryPolicy(...)` | Defines the retry count, max duration, backoff, and exception types eligible for retry |
| `openTimeout(...)` | Duration the Circuit Breaker stays in `OPEN` before transitioning to `HALF_OPEN`; current docs state a default of 20 seconds |
| `resetTimeout(...)` | Time window used to automatically reset to `CLOSED` according to the implementation's rules; current docs state a default of 5 seconds |

Framework Retry has different semantics from Resilience4J's sliding window. An execution is considered failed once all retries are exhausted, at which point the circuit opens. While `OPEN`, calls are rejected and the fallback can run. After `openTimeout` elapses, one call is permitted in `HALF_OPEN` to test recovery; if it succeeds the circuit closes, and if it fails it opens again.

This implementation does not support reactive applications. Choose it only when the project uses Spring Framework 7 and the protected calls are blocking/imperative. For WebFlux needing a reactive Circuit Breaker, use Resilience4J according to the train's guide.

## 6. Sentinel and Names Appearing in the Spring Cloud Commons Documentation

The Spring Cloud Commons page describes the common abstraction and lists Resilience4J, Sentinel, and Spring Retry. That page also links to the Spring Cloud Alibaba Sentinel guide. This list has a broader scope than the catalog of implementations packaged in the Spring Cloud Circuit Breaker project in a specific Release Train.

Therefore, when considering Sentinel, verify the starter and compatibility matrix from Spring Cloud Alibaba corresponding to the Spring Boot/Spring Cloud versions in use. Do not take an entry from the Commons page and infer that the current train ships a Sentinel starter published by the `spring-cloud-circuitbreaker` project.

Netflix Hystrix appears in older Spring Cloud documentation, but it is not in the implementation catalog of the current Circuit Breaker documentation referenced in this article. Do not add Hystrix to a new project just because you found an example from Hoxton or historical documentation.

## 7. Comparing by Application Needs

| Need | Recommended Direction | Reason |
| --- | --- | --- |
| Needs WebFlux/Reactor and `Mono`/`Flux` | Resilience4J reactive starter | Project docs confirm blocking and reactive support; provides `ReactiveCircuitBreakerFactory` |
| Needs sliding window, slow-call threshold, TimeLimiter, Bulkhead, and RateLimiter | Resilience4J | Rich fault-tolerance feature set and per-instance configuration |
| Project already has `RetryTemplate`, `CircuitBreakerRetryPolicy`, and Spring Retry listeners | Spring Retry | Reuses existing retry policies and stateful retry mechanism |
| Boot 4/Spring Framework 7 app wanting native RetryPolicy and lightweight imperative Circuit Breaker | Framework Retry | Uses Spring Framework 7's native retry API and `openTimeout`/`resetTimeout` configuration |
| Needs Sentinel | Check Spring Cloud Alibaba for the matching train | This is a separate ecosystem integration; verify starter and compatibility matrix independently |

Do not compare based solely on feature count. Evaluate open-circuit semantics, failure accounting, recovery probing, timeouts, retries, bulkheads, reactive support, metrics, operability, and code migration cost.

## 8. Importing the BOM and Declaring the Right Starter

To let Spring Cloud manage starter versions compatible with the train, import the `spring-cloud-dependencies` BOM. Gradle Groovy example:

```groovy
ext {
    set('springCloudVersion', '2026.0.0')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
}
```

This example is for a project using a Spring Boot version compatible with Spring Cloud `2026.0.0`; current train documentation pairs this train with Spring Boot `4.2.0`. If the project uses Boot 3.5, pick a compatible train such as `2025.0.x` and use the starter/version managed by that train's BOM.

With Maven, the equivalent configuration is:

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

<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
  </dependency>
</dependencies>
```

Do not arbitrarily pin a `spring-cloud-starter-circuitbreaker-*` version alongside the BOM without a verified compatibility reason. Avoid mixing starters from multiple Release Trains in the same application.

## 9. Verifying the Actually Resolved Implementation

After declaring the dependency, inspect the dependency tree to confirm the BOM resolved the expected version and see which modules the starter pulled in.

With Gradle:

```bash
./gradlew dependencyInsight --dependency spring-cloud-starter-circuitbreaker --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

With Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud,io.github.resilience4j,org.springframework.retry
```

Check the following points:

1. Is the Spring Boot version in the Release Train's compatibility matrix?
2. Does the `spring-cloud-dependencies` BOM match the exact train and patch in use?
3. Does the `spring-cloud-circuitbreaker` version managed by the BOM match the train's project reference?
4. Does the resolved starter match the intended provider and reactive/non-reactive type?
5. Did the dependency tree accidentally pull in two provider starters that both create `CircuitBreakerFactory` in the same application?
6. If using Framework Retry, are Spring Framework 7 and Spring Boot 4 actually present in the dependency graph?
7. If using Sentinel, are the starter and Spring Cloud Alibaba version compatible with the train?

At runtime, check which factory bean the application injects. For imperative Resilience4J, it is `Resilience4JCircuitBreakerFactory`; for reactive Resilience4J, `ReactiveResilience4JCircuitBreakerFactory`; for Spring Retry, `SpringRetryCircuitBreakerFactory`; for Framework Retry, `FrameworkRetryCircuitBreakerFactory`. You can verify this via the Spring Boot Actuator `beans` endpoint in a protected development environment or with an ApplicationContext integration test.

Typically, an application should pick one implementation for `CircuitBreakerFactory`. Do not add multiple imperative starters and expect the framework to choose an implementation per ID automatically. If you need both imperative and reactive, use the exact factory pair supported by the train's documentation; Resilience4J provides two separate factories for the two call styles.

## 10. Testing Behavior Before Committing to a Choice

Run the same set of scenarios against the candidate implementation to compare behavior:

1. Call the dependency successfully in a row and confirm normal state, latency, and metrics.
2. Make the dependency return controlled errors; confirm the `CLOSED` to `OPEN` transition condition according to the implementation's semantics.
3. Send additional requests while `OPEN`; confirm requests are rejected and the fallback is invoked without adding load to the dependency.
4. Wait for the open duration to elapse; confirm the number of probe calls in `HALF_OPEN` and the conditions for closing or reopening.
5. Make the dependency slow; confirm whether the implementation classifies slow calls or triggers TimeLimiter as configured.
6. Test Retry and backoff; confirm total requests do not exceed limits and do not stretch past the external request's deadline.
7. With WebFlux, test `Mono`/`Flux`, subscription, and non-blocking fallback. If the provider lacks reactive support, rule it out for this flow.
8. Inspect metrics, events, health indicators, logs, and traceability by dependency ID.

Do not compare configuration keys with similar names without considering their semantics. For example, Resilience4J's `slidingWindowSize` is a measurement window by sample count or time; Framework Retry's `openTimeout` is how long the circuit stays open; they are not equivalent parameters.

## 11. Common Selection Mistakes

- Choosing a Spring Cloud Release Train incompatible with the existing Spring Boot version and trying to fix it by pinning a starter individually.
- Using the `/current` page to decide dependencies for a project on an older train.
- Assuming every implementation has a reactive factory because the common abstraction includes `ReactiveCircuitBreakerFactory`.
- Using `resilience4j.circuitbreaker.*` configuration for Spring Retry or Framework Retry.
- Choosing Framework Retry in a WebFlux application even though this implementation does not support reactive.
- Confusing Spring Retry with Spring Framework Retry; the two implementations use different APIs and builders.
- Seeing Sentinel on the Spring Cloud Commons page and assuming it has a starter from the current train's Circuit Breaker project.
- Adding two imperative provider starters and letting auto-configuration compete to register the same factory type.
- Relying on old Hystrix documentation instead of the implementations published for the current Release Train.

## References

- [Spring Cloud Release – 2026.0.0](https://docs.spring.io/spring-cloud-release/reference/index.html): current Release Train, compatible Spring Boot, and Circuit Breaker project version.
- [Spring Cloud Release – 2025.1.5](https://docs.spring.io/spring-cloud-release/reference/2025.1/index.html): example of a Boot 4 and Circuit Breaker 5.0.x train.
- [Spring Cloud Release – 2025.0.3](https://docs.spring.io/spring-cloud-release/reference/2025.0/index.html): example of a Boot 3.5 and Circuit Breaker 3.3.x train.
- [Spring Cloud Circuit Breaker – Implementations](https://docs.spring.io/spring-cloud-circuitbreaker/reference/): current implementation catalog and per-provider configuration pages.
- [Spring Cloud Circuit Breaker – Resilience4J](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): imperative/reactive starters, Customizer, Bulkhead, and properties.
- [Spring Cloud Circuit Breaker – Spring Retry](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-spring-retry.html): `CircuitBreakerRetryPolicy`, `DefaultRetryState`, and `SpringRetryConfigBuilder`.
- [Spring Cloud Circuit Breaker – Framework Retry](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-framework-retry.html): Spring Framework 7, starter, retry policy, open/reset timeout, and reactive limitation.
- [Spring Cloud Commons – Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): factory abstraction, fallback, and ecosystem integrations.
