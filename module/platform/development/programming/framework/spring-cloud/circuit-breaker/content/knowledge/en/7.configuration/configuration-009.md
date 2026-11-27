# Enabling or Disabling Integrations by Feature and Version

Spring Cloud Circuit Breaker provides a common API yet supports multiple backends and accompanying features. In a Spring application, enabling or disabling part of the system generally depends on the starter on the classpath and auto-configuration properties. Three scopes must be distinguished: selecting the circuit breaker backend, enabling or disabling a feature of that backend, and choosing blocking vs. reactive execution.

With the `SPRING_CLOUD_CIRCUIT_BREAKER` module, the appropriate configuration depends on the stack your application uses: Resilience4j, Spring Retry, or Framework Retry. Not every property applies to every backend. For example, properties under `spring.cloud.circuitbreaker.resilience4j` only control the Resilience4j integration; they do not change the policy of `SpringRetryCircuitBreakerFactory` or `FrameworkRetryCircuitBreakerFactory`.

## Choosing the starter by application model

Starters bring the implementation and corresponding auto-configurations onto the classpath. For Resilience4j, Spring Cloud Circuit Breaker publishes two starters:

| Starter | When to use | Typical factory |
|---|---|---|
| `spring-cloud-starter-circuitbreaker-resilience4j` | Synchronous, blocking calls | `Resilience4JCircuitBreakerFactory` |
| `spring-cloud-starter-circuitbreaker-reactor-resilience4j` | Reactive calls with Reactor | `ReactiveResilience4JCircuitBreakerFactory` |

When using the Spring Cloud BOM, declare the dependency without specifying a separate version manually:

```xml
<dependencies>
    <!-- Choose the blocking starter if the application calls the synchronous API. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <!-- For reactive applications, use the Reactor starter instead of the blocking starter. -->
    <!--
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
    -->
</dependencies>
```

The two dependencies in the example illustrate the two choices. Choose the starter matching your application's call style and Spring Cloud BOM version; do not add both just to see which auto-configuration wins. If an application genuinely needs both blocking and reactive APIs, check which factories are created and how they are injected in the context for the version in use.

## Disabling all Resilience4j auto-configuration

If the application does not want Spring Cloud Circuit Breaker to automatically create Resilience4j integration beans, set the following property:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enabled: false
```

The property `spring.cloud.circuitbreaker.resilience4j.enabled=false` disables auto-configuration for the Resilience4j integration. Its scope is the Resilience4j backend; it is not a global switch to disable every Spring Cloud Circuit Breaker implementation. Setting this property also does not remove dependencies from the classpath. If the application no longer uses Resilience4j anywhere, you can remove the starter or exclude unnecessary dependencies via dependency management.

If you want to keep using the circuit breaker and only disable a specific feature such as TimeLimiter or Bulkhead, use that feature's dedicated switch. Disabling all auto-configuration prevents the Resilience4j factory from being auto-configured, so feature-level properties cannot substitute for enabling the backend.

## Enabling or disabling TimeLimiter by scope

In the Resilience4j integration, TimeLimiter is enabled by default. You can disable TimeLimiter across the entire application with `spring.cloud.circuitbreaker.resilience4j.disable-time-limiter`:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        disable-time-limiter: true
```

When only certain services do not need TimeLimiter, use `disable-time-limiter-map` to set values by group or instance:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        disable-time-limiter: false
        disable-time-limiter-map:
          catalog: false
          batchGroup: true
          legacyReport: true
```

In this example, `catalog` keeps TimeLimiter enabled, while `batchGroup` and `legacyReport` disable TimeLimiter. A value of `true` in the map means disabled; `false` means enabled. When using `factory.create(id, groupName)`, the key can represent an instance or a group. The precedence order is **instance > group > global**. If there is no specific entry in the map, the application uses the global value; if the global switch is not set, TimeLimiter remains enabled by default.

These TimeLimiter disable properties belong to Spring Cloud Circuit Breaker and apply to both the standard and reactive Resilience4j integrations. Disabling TimeLimiter does not disable CircuitBreaker: `CLOSED`, `OPEN`, `HALF_OPEN` states, sliding windows, and failure thresholds continue to operate. However, the application must have appropriate timeouts on the HTTP client or network calling layer if you do not want requests to wait indefinitely.

## Enabling or disabling Bulkhead

If `resilience4j-bulkhead` is present on the classpath, Spring Cloud Circuit Breaker Resilience4j automatically wraps calls with a Bulkhead. You can disable Bulkhead integration with its dedicated property:

```yaml
spring:
  cloud:
    circuitbreaker:
      bulkhead:
        resilience4j:
          enabled: false
```

This is Bulkhead's switch; it does not disable CircuitBreaker or TimeLimiter. When Bulkhead is enabled, Resilience4j provides two types:

| Type | Mechanism | Suitable when |
|---|---|---|
| `FixedThreadPoolBulkhead` | Uses a thread pool and bounded queue | You need to isolate execution in a dedicated pool and control queued tasks |
| `SemaphoreBulkhead` | Uses a semaphore to limit concurrent calls | You want to limit concurrency without offloading execution to a separate thread pool |

By default, Spring Cloud Circuit Breaker Resilience4j uses `FixedThreadPoolBulkhead`. To change the default to `SemaphoreBulkhead`, set:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
```

Choosing semaphore changes resource isolation and concurrency handling. Inspect the blocking/reactive nature of your calls, concurrency limits, queues, and executor behavior before switching Bulkhead types. Properties like `maxConcurrentCalls`, `maxThreadPoolSize`, and `coreThreadPoolSize` are policies for individual Bulkhead instances; they are not auto-configuration enable/disable switches.

## Enabling metrics with required dependencies

Resilience4j metrics are auto-configured when the required dependencies are on the classpath. To collect metrics, add Spring Boot Actuator and Resilience4j Micrometer:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>
</dependencies>
```

`spring-boot-starter-actuator` already brings in `micrometer-core`, so you do not need to declare it separately just to enable Resilience4j metrics. Having the dependencies does not mean every Actuator endpoint is exposed publicly; configure endpoint exposure and security according to your application's operational policy.

## Distinguishing backends and version requirements

Spring Cloud Circuit Breaker has multiple implementations. The table below helps choose the right integration and avoid applying properties to the wrong backend:

| Implementation | Dependency/starter | Scope and conditions |
|---|---|---|
| Resilience4j blocking | `spring-cloud-starter-circuitbreaker-resilience4j` | Blocking API; supports CircuitBreaker, TimeLimiter, Bulkhead, and metrics when corresponding dependencies are present |
| Resilience4j reactive | `spring-cloud-starter-circuitbreaker-reactor-resilience4j` | Reactor API; uses `ReactiveResilience4JCircuitBreakerFactory` and the supported Resilience4j property groups |
| Spring Retry | `spring-cloud-starter-circuitbreaker-spring-retry` | Uses `SpringRetryCircuitBreakerFactory` and `SpringRetryConfigBuilder`; configured separately via the Spring Retry API |
| Framework Retry | `spring-cloud-starter-circuitbreaker-framework-retry` | Based on Spring Framework 7's retry API; does not support reactive |

Framework Retry is an integration tied to Spring Framework 7. It is suitable only when your application's Spring Boot, Spring Framework, and Spring Cloud release train versions are compatible. Applications using Spring Framework 6 or Spring Boot 3 cannot simply add the Framework Retry starter to gain this feature. When reactive support is needed, choose Resilience4j reactive instead of Framework Retry.

Spring Retry and Framework Retry are two distinct integrations. `spring.cloud.circuitbreaker.resilience4j.enabled`, `disable-time-limiter`, `disable-time-limiter-map`, and the Bulkhead switches above are Resilience4j-specific properties; do not use them to configure `SpringRetryCircuitBreakerFactory` or `FrameworkRetryCircuitBreakerFactory`. For retry backends, pick the right starter, inject the right factory, and configure via `SpringRetryConfigBuilder` or `FrameworkRetryConfigBuilder` according to the documentation for that version.

Current Spring Cloud Circuit Breaker documentation lists Resilience4j, Spring Retry, and Framework Retry. Framework Retry relies on Spring Framework 7, so the list of available implementations may differ in older release trains. Properties such as `disable-time-limiter-map` must also be checked against the documentation for the exact dependency version; do not assume a newer property exists in every 3.x or 4.x release.

To manage versions safely:

1. Use the Spring Cloud BOM compatible with the running Spring Boot version to manage starter versions.
2. Consult documentation for your exact Spring Cloud Circuit Breaker release, not just the `current` page when the application is on an older release train.
3. Check the Spring Framework major version before selecting Framework Retry.
4. Inspect the dependency tree to see which starters and optional modules are actually on the classpath.
5. After changing flags, confirm the corresponding factory is created or excluded from the application context and verify runtime behavior.

## Environment-based configuration example

An application can keep Resilience4j enabled, disable TimeLimiter only for a batch group, and disable Bulkhead if thread-pool/semaphore isolation is not desired:

```yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enabled: true
        disable-time-limiter: false
        disable-time-limiter-map:
          catalog: false
          batchGroup: true
        enableSemaphoreDefaultBulkhead: false
      bulkhead:
        resilience4j:
          enabled: false
```

In this configuration, Resilience4j still provides the circuit breaker; TimeLimiter remains active for `catalog` and instances without overrides; TimeLimiter is disabled for the `batchGroup` group; Bulkhead auto-configuration is disabled. To use semaphore Bulkhead by default, enable Bulkhead and set `enableSemaphoreDefaultBulkhead: true`.

Do not toggle features merely to get the application to start without assessing the impact. Disabling TimeLimiter can let requests hang; disabling Bulkhead can allow too many calls to contend for resources simultaneously; disabling Resilience4j auto-configuration can remove the factory that code injects. Every change should be paired with network-layer timeouts, concurrency limits, or an appropriate alternative implementation.

## Verification after enabling or disabling

After modifying dependencies or properties, verify in order:

1. **Dependencies:** confirm the right starter is in the dependency tree and its version is managed by the Spring Cloud BOM.
2. **Auto-configuration:** enable Spring Boot's condition evaluation report or inspect startup logs to see which Resilience4j, Spring Retry, or Framework Retry configuration was applied.
3. **Factory:** confirm the factory injected by services matches the intended backend; for reactive, check `ReactiveResilience4JCircuitBreakerFactory`.
4. **TimeLimiter:** trigger a task slower than the timeout; confirm a timeout occurs when enabled and the task is not bounded by TimeLimiter when that feature is disabled.
5. **Bulkhead:** generate concurrency exceeding the limit; confirm calls are rejected by Bulkhead when enabled and check alternative limits when disabled.
6. **Circuit breaker:** trigger a failure sequence to confirm the breaker still transitions states when only TimeLimiter or Bulkhead is disabled.
7. **Metrics:** confirm Actuator and Resilience4j Micrometer are loaded if you need to track call counts, failures, slow calls, and state.

The expected outcome is that each switch affects only the exact scope described in the documentation. If changing a property does not produce the corresponding behavior, check property spelling, Spring Cloud Circuit Breaker version, classpath dependencies, and auto-configuration conditions before inventing a new key.

## References

- [Spring Cloud Circuit Breaker — Resilience4j starters and auto-configuration](https://docs.spring.io/spring-cloud-circuitbreaker/docs/current/reference/html/spring-cloud-circuitbreaker-resilience4j.html)
- [Spring Cloud Circuit Breaker — TimeLimiter and Bulkhead configuration](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html)
- [Spring Cloud Circuit Breaker — current implementations](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Cloud Circuit Breaker — Spring Retry](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-spring-retry.html)
- [Spring Cloud Circuit Breaker — Framework Retry and Spring Framework 7 requirement](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-framework-retry.html)
