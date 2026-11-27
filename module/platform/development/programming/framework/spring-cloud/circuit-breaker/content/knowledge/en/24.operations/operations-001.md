# Implementing Circuit Breaker Configuration by Profile and Service Scope

In a Spring Cloud system, each service calls one or more dependencies with different traffic levels, latencies, and criticality. A circuit breaker needs to be configured according to the runtime environment and the exact call boundary it protects. Profiles help select the appropriate configuration set for `dev`, `test`, `staging`, or `prod`; instance IDs help separate policies for each dependency or operation group within the calling service.

With Resilience4j, configuration is typically loaded into each Spring Boot process. Therefore, the same profile can provide identical thresholds for replicas, while the `CLOSED`/`OPEN`/`HALF_OPEN` state and sliding window remain local data per replica. Profile-based configuration does not create a cluster-wide shared circuit breaker.

## 1. Separating Three Concepts: Application, Profile, and Breaker Instance

These three concepts address three different questions:

| Concept | Example | Role |
| --- | --- | --- |
| Application name (`spring.application.name`) | `order-service` | Identifies the running service and is typically used to select service-specific configuration in the deployment environment or Config Server |
| Spring profile | `dev`, `test`, `staging`, `prod` | Selects configuration values suited to the environment or execution purpose |
| Circuit breaker instance ID | `inventoryRead`, `inventoryReserve`, `paymentAuthorize` | Defines the dependency or operation boundary that a breaker protects within the current process |

For example, `order-service` may call Inventory Service to read inventory and reserve stock. The two operations have different characteristics: reading inventory can tolerate short-term caching, whereas reserving stock is a command with side effects and requires stricter timeout, retry, and fallback policies. Two separate breakers can be created: `inventoryRead` and `inventoryReserve`.

Do not use profiles as a substitute for instance IDs. Profiles select value sets for an environment; instance IDs separate call boundaries within the same service. Also do not create a separate breaker per user, order, or request, as that causes uncontrolled growth in instances and metrics while leaving each breaker with too few samples to evaluate.

## 2. Placing Base Configuration in application.yml

Place shared default values in `src/main/resources/application.yml`. Use `configs` to define policy sets and `instances` to assign those policies to each dependency:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    configs:
      readDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
      writeDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 40
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
    instances:
      inventoryRead:
        baseConfig: readDefault
      inventoryReserve:
        baseConfig: writeDefault
      paymentAuthorize:
        baseConfig: writeDefault
```

In this example:

- `readDefault` is used for read operations; the window has 20 calls and requires at least 10 samples before calculating rates.
- `writeDefault` uses more conservative thresholds for write operations and fewer `HALF_OPEN` probes.
- `inventoryRead`, `inventoryReserve`, and `paymentAuthorize` are the IDs used by the calling code.
- `baseConfig` enables policy reuse while allowing each instance to override specific properties when needed.

The values above are illustrative only. Window size, minimum samples, failure threshold, slow-call threshold, and wait duration should be chosen based on traffic, SLOs, client timeouts, and dependency capacity. Do not copy the exact same set of thresholds across all services if their dependencies have different characteristics.

## 3. Overriding by Profile

Spring Boot can load profile-specific configuration files such as `application-dev.yml` or `application-prod.yml`. Properties declared in a profile file take precedence over the corresponding values in the base configuration. Properties that are not overridden continue using the base values.

Example `application-dev.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowSize: 6
        minimumNumberOfCalls: 3
        waitDurationInOpenState: 3s
      inventoryReserve:
        slidingWindowSize: 6
        minimumNumberOfCalls: 3
        waitDurationInOpenState: 5s
```

In a development environment, small windows and short open durations make state transitions easy to observe quickly. These values are for experimentation and should not be promoted automatically to production because dev traffic is usually low and unrepresentative of real request distributions.

Example `application-test.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 1m
        permittedNumberOfCallsInHalfOpenState: 1
```

The test profile uses a small, fixed sample count for repeatable state-transition tests. For example, four failed calls in a four-sample window yield a 100% failure rate, exceeding the 50% threshold and opening the breaker.

Example `application-prod.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowSize: 50
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
      paymentAuthorize:
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 30
        slowCallDurationThreshold: 900ms
        slowCallRateThreshold: 40
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
```

Production uses sample counts and thresholds chosen according to each dependency's actual behavior. For example, payment may require different thresholds and probe counts than inventory because the impact of a payment command and the dependency's processing capacity differ. Evaluate changes using metrics and load testing before releasing.

## 4. Activating the Right Profile in Each Environment

Profiles can be selected via environment variables, command-line arguments, or deployment configuration. PowerShell example:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
./mvnw spring-boot:run
```

Linux/macOS example:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
```

Profiles can also be passed via application arguments:

```bash
java -jar order-service.jar --spring.profiles.active=staging
```

In Kubernetes or container platforms, set `SPRING_PROFILES_ACTIVE` in the deployment manifest, Helm values, or environment configuration. Do not let individual pods choose different profiles unintentionally; replicas of the same deployment generally need the same profile and the same configuration version.

Configuration precedence is also affected by environment variables, command-line arguments, external configuration sources, and the configuration-loading mechanism enabled by the application. When a value does not behave as expected, inspect the effective configuration sources rather than reading `application.yml` alone.

## 5. IDs in Calling Code Must Match Configured Instances

When using Spring Cloud CircuitBreaker with the Resilience4j backend, the ID passed to the factory must match the name under `resilience4j.circuitbreaker.instances`:

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
        return circuitBreakerFactory.create("inventoryRead").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

`create("inventoryRead")` uses the exact instance declared in YAML. If the calling code uses `inventory` while YAML only defines `inventoryRead`, the application may create or use a default configuration unexpectedly. Keep IDs consistent across YAML, calling code, fallbacks, logs, and dashboards.

With the Resilience4j native API or annotations, the same principle applies: the name passed to `registry.circuitBreaker("...")` or `@CircuitBreaker(name = "...")` must match the configured ID. Within a service, keep the list of IDs in an easily inspectable place and avoid scattering inconsistent names.

## 6. Choosing Instance Scope by Dependency and Operation

A single dependency does not always need only one breaker. Separate instances when two groups of calls have clearly different protection goals:

| Boundary | Example ID | Reason to Separate |
| --- | --- | --- |
| Read inventory data | `inventoryRead` | Can use caching and tolerate different latency than write commands |
| Reserve or release stock | `inventoryReserve` | Has side effects, requiring different error classification and fallbacks |
| Authorize payment | `paymentAuthorize` | Has specific idempotency and business consequences |
| Look up payment status | `paymentStatusRead` | May have a different SLO and timeout than the authorize command |

Separating breakers prevents one slow call flow from raising the failure rate of another flow. However, creating too many breakers also reduces the sample count per instance, increases metric volume, and complicates operations. Only split when traffic, SLOs, error types, or recovery policies genuinely differ.

A circuit breaker lives on the caller and protects calls made by that caller. An `inventoryRead` breaker in Order Service does not automatically protect Inventory Service from other callers. Each microservice must manage configuration for the dependencies it calls itself; do not treat one service's profile file as automatically applying to every service in the system.

## 7. Coordinating Circuit Breaker with Timeout and Bulkhead

Profiles should manage related limits together. The circuit breaker stops new calls after detecting dependency degradation; timeouts limit request wait time; bulkheads limit the concurrent resources a dependency can consume.

Example configuration for `inventoryRead`:

```yaml
resilience4j:
  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 900ms
        cancelRunningFuture: true
  bulkhead:
    instances:
      inventoryRead:
        maxConcurrentCalls: 30
        maxWaitDuration: 0ms
```

TimeLimiter settings apply to asynchronous task types supported by the integration, such as `Future` or `CompletionStage`. For blocking HTTP clients, connect/response/read timeouts still need to be configured directly on the client; do not assume TimeLimiter automatically stops every blocked thread. A semaphore bulkhead limits concurrent calls through the instance; if using a thread-pool bulkhead, configure the pool and queue to match the execution model.

Keep IDs consistent across the circuit breaker, TimeLimiter, and bulkhead when they protect the same boundary. Also check Retry/Bulkhead/TimeLimiter ordering and do not retry rejections caused by exhausted permits or `CallNotPermittedException` if retrying cannot help.

## 8. Centralized Configuration and Cross-Service Consistency

In a multi-microservice system, configuration can be managed by application name and profile using Spring Cloud Config or the platform's centralized configuration mechanism. For example, Order Service receives its configuration set for `inventoryRead` and `paymentAuthorize`, while Catalog Service can have its own IDs and thresholds for the dependencies it calls.

A centralized configuration workflow should have:

1. A clear, stable application name to select the right service configuration.
2. Explicitly chosen profiles per environment.
3. Traceable configuration versions or labels.
4. Threshold changes reviewed and tested before release.
5. Canary deployment or controlled rollout when changes affect dependency load.
6. A rollback plan to the previous configuration version.

Do not assume remote configuration refresh automatically updates every existing circuit breaker instance. Refresh capability depends on the integration and version; verify the runtime update mechanism your application uses. If safe live updates are not supported, apply changes via a controlled rollout/restart so every replica loads the same configuration version.

Profiles only select configuration values; they do not synchronize state or sliding windows across replicas. After deployment, pods may share the same configuration while still being in different breaker states due to different call histories.

## 9. Verifying Effective Configuration

When a breaker opens too early, fails to open when expected, or does not apply the right profile, check in order:

1. Does `spring.application.name` match the deployed service name?
2. Is `spring.profiles.active` set to the expected profile?
3. Are external configuration sources, environment variables, or command-line arguments overriding properties?
4. Does the ID in calling code match `instances` in YAML?
5. Is the instance inheriting the expected `baseConfig`?
6. Has `minimumNumberOfCalls` been reached, and does the sliding window have enough traffic?
7. Are exceptions recorded or ignored according to configuration?
8. Do timeout and bulkhead share the same boundary as the breaker?

In development environments, Spring Boot Actuator can help inspect active properties and metrics. The `env` or `configprops` endpoints can expose sensitive configuration values; enable them only when needed, restrict access, and never expose them publicly. For production, prefer structured startup logs containing the application name, active profile, configuration version, and list of breaker IDs (without logging secrets).

Metrics per breaker ID can be checked to confirm the instance is in use. Combining metrics with state transition events reveals whether a breaker opened due to failure rate, slow-call rate, or administrative action.

## 10. Testing Profiles and Breaker Policies

Each profile should have a clear purpose. Use `@ActiveProfiles("test")` to ensure tests load the test configuration instead of accidentally using `dev` or `prod`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@ActiveProfiles("test")
class InventoryCircuitBreakerProfileTest {

    @Autowired
    CircuitBreakerRegistry registry;

    @Test
    void testProfileOpensInventoryBreakerAfterConfiguredSamples() {
        CircuitBreaker breaker = registry.circuitBreaker("inventoryRead");

        for (int i = 0; i < 4; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(() -> {
                throw new IllegalStateException("simulated inventory failure");
            })).isInstanceOf(IllegalStateException.class);
        }

        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
    }
}
```

This example assumes the Spring Boot Resilience4j integration has registered `CircuitBreakerRegistry` and `application-test.yml` sets `minimumNumberOfCalls: 4`, `slidingWindowSize: 4`, and `failureRateThreshold: 50`. Four failing supplier calls yield a 100% failure rate, so the breaker opens. Use an exception configured as a failure; if `ignoreExceptions` or `recordExceptions` is set, adjust the test to match the actual classification rules.

Beyond state tests, add tests verifying that:

- The `dev` profile uses small windows for quick experimentation.
- The `prod` profile uses reviewed values appropriate for real traffic.
- IDs in calling code create the expected configured instances.
- Two dependencies with distinct policies do not unintentionally share a breaker.
- Fallbacks and timeouts conform to the business contract.
- Configuration changes do not trigger probe bursts or traffic spikes beyond dependency capacity.

Do not share breaker instances across tests without resetting state or creating fresh fixtures. An `OPEN` state left over from a previous test can cause subsequent tests to receive `CallNotPermittedException` even when testing the supplier itself.

## 11. Rolling Out Configuration Changes Safely

Changing `failureRateThreshold`, `slowCallRateThreshold`, `minimumNumberOfCalls`, or `waitDurationInOpenState` can significantly alter the volume of requests reaching a dependency. Follow a rollout workflow:

1. Identify the affected dependency and breaker IDs.
2. Use current metrics to inspect traffic, latency distribution, and failure rates.
3. Change a cohesive group of related properties and document the rationale.
4. Validate with the test profile and load tests using representative request distributions.
5. Deploy to a canary or subset of replicas first if the platform supports it.
6. Monitor state transitions, call-not-permitted counts, fallbacks, p95/p99 latency, and dependency-side metrics.
7. Expand the rollout or roll back if dependency load increases, breakers open too frequently, or end-to-end requests degrade.

Do not close all breakers or reset statistics merely to make dashboards look clean after changing configuration. Resetting discards accumulated metrics and reopens call paths; perform it only for a clear operational reason. Once new configuration is loaded, observe actual behavior and maintain logs/audit records of the deployed configuration version.

## 12. Common Configuration Mistakes

- **Using one configuration for every environment:** thresholds suited to test or dev may be too sensitive or too slow in production.
- **Using one breaker for multiple dependencies:** failures in one dependency can open the breaker for another.
- **YAML ID not matching calling code:** the intended instance may never be used.
- **Setting `minimumNumberOfCalls` too high:** insufficient traffic prevents the breaker from evaluating rates.
- **Setting `minimumNumberOfCalls` too low:** a few random errors can trip the breaker prematurely.
- **Assuming profiles synchronize state:** replicas still maintain separate states and sliding windows.
- **Assuming Config refresh always updates running instances:** verify integration runtime support or use an appropriate rollout.
- **Using the `dev` profile in production:** small windows and short open durations can cause continuous state flapping.
- **Not versioning configuration:** makes it hard to trace why two replicas behave differently.

## 13. Operational Rules

- Use `spring.application.name` to identify the service and Spring profiles to select environment configuration.
- Use stable breaker IDs scoped to each dependency or operation with distinct SLOs or error policies.
- Define base configurations with `configs` and wire instances via `baseConfig`; override per profile only with good reason.
- Keep profiles consistent across replicas of the same deployment, unless running an intentional canary.
- Check effective configuration, instance IDs, and override sources when investigating incidents.
- Manage timeouts, bulkheads, and retries along the same boundary as the circuit breaker.
- Never treat profiles as a state-sharing mechanism across processes.
- Manage centralized configuration with traceable versions, reviews, and rollback plans.
- Monitor state, failure rate, slow-call rate, not-permitted calls, fallbacks, and end-to-end latency after every change.

Implementing configuration by profile and service scope allows each microservice to apply environment-appropriate thresholds while separating protection policies per dependency. When IDs are managed consistently, configurations are versioned, and local states are observed individually, operations teams can adjust circuit breaker policies while keeping dependency impact and user experience under control.
