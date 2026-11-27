# Organizing Profiles and Configuration for Reproducible Behavior

A circuit breaker protects a service as expected only when the application runs with a clearly defined configuration set. The exact same source code can behave very differently across a developer machine, a test environment, and production if `minimumNumberOfCalls`, failure thresholds, wait durations, or timeouts change. In Spring Cloud Circuit Breaker with Resilience4j, we organize these values by Spring profile, use a default configuration as the baseline, apply intentional per-environment overrides, and verify the effective configuration at runtime.

The goal is for a development team to be able to answer three questions: which profile the application is running with, which circuit breakers are configured, and which values govern when the circuit opens. When those conditions can be reproduced, bugs that are hard to replicate in production become easier to investigate in development and test environments.

## 1. Profiles and Externalized Configuration

A Spring profile is a label selecting a group of configurations for a specific environment or execution purpose. Common profiles include:

| Profile | Purpose | Circuit Breaker Configuration Characteristics |
| --- | --- | --- |
| `dev` | Local personal development | Can use mock services, small windows, and short wait durations to observe state transitions quickly. |
| `test` | Automated testing | Uses small sample counts, deterministic thresholds, and mock services so results are repeatable. |
| `staging` | Pre-release verification | Close to production in topology, timeouts, and thresholds; uses test data. |
| `prod` | Serving real users | Thresholds chosen based on traffic, SLOs, and dependent service capacity. |

A profile should not change the meaning of a circuit breaker. For example, the ID `inventory` always represents the circuit breaker protecting calls to the inventory service; only values such as window size or open duration may vary across environments. Using stable IDs ensures configuration, logs, metrics, and calling code all refer to the same object.

Spring Boot loads shared configuration from `application.yml` and can additionally load a file matching the active profile, such as `application-dev.yml` or `application-prod.yml`. Values in the profile-specific file override corresponding values in the shared file. Environment variables and command-line arguments can also override file configuration, so looking at `application.yml` alone is not enough to determine the values the application runs with.

A simple structure can look like this:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
```

Activate the profile from the runtime environment. For example, in PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
./mvnw spring-boot:run
```

On Linux or macOS:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

In containers, set `SPRING_PROFILES_ACTIVE` in the deployment configuration or container environment variables. Do not leave each machine to pick a default profile on its own without documenting that choice in the application runbook.

## 2. Setting a Default Configuration as the Baseline

Declare shared values in `application.yml`. The example below creates a default circuit breaker configuration and attaches it to the `inventory` instance:

```yaml
spring:
  application:
    name: order-service

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
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
    instances:
      inventory:
        baseConfig: default
```

In this example:

- `configs.default` defines a reusable baseline set of values.
- `instances.inventory` creates configuration for a specific circuit breaker and inherits the baseline values via `baseConfig`.
- `slidingWindowType` and `slidingWindowSize` choose how samples are collected.
- `minimumNumberOfCalls` specifies the minimum number of calls before rates are calculated.
- `failureRateThreshold` and `slowCallRateThreshold` define the two conditions that can transition the circuit from `CLOSED` to `OPEN`.
- `slowCallDurationThreshold` defines the duration beyond which a call is considered slow.
- `waitDurationInOpenState` and `permittedNumberOfCallsInHalfOpenState` govern the recovery probing phase after the circuit opens.

When an application has multiple dependent services, you can create separate instances such as `payment`, `catalog`, or `shipping`. Create instances only when independent monitoring or protection is needed. If all calls share a single ID despite having different traffic characteristics and criticality, one failing service can affect protection decisions for another service.

## 3. Applying Intentional Per-Environment Overrides

The `application-dev.yml` file only needs to declare values that differ from the baseline configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        waitDurationInOpenState: 5s
```

When running with the `dev` profile, the properties above override the corresponding values on the `inventory` instance; undeclared properties still come from the baseline configuration. A small window and short open duration make observing the `CLOSED` → `OPEN` → `HALF_OPEN` flow faster during development. This is an experimental choice, not a default meant to be promoted straight to production.

For the `test` profile, we can choose small, fixed numbers so a test can trip the circuit breaker with a known number of calls:

```yaml
# application-test.yml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 100ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 1s
        permittedNumberOfCallsInHalfOpenState: 1
```

With four recorded calls in the window, two failed calls produce a `50%` failure rate and reach the threshold. In tests, you can intentionally fail all four calls for clearer outcomes. `TIME_BASED` is usually suitable when evaluating behavior over real time intervals; `COUNT_BASED` is usually more convenient for tests because sample counts are controlled directly.

The `staging` profile should closely match production on critical limits. If staging uses a 1-second timeout while production uses 5 seconds, slow-call rate test results will not reflect actual behavior. The `prod` profile should override only values with clear operational justification, such as higher traffic, dependent service latency, or different SLO targets. Avoid creating a completely different configuration set for every environment without a specific need.

## 4. Keeping IDs in Calling Code Aligned with Configuration IDs

The instance name in YAML must match the circuit breaker name created in code. Example with the synchronous Spring Cloud CircuitBreaker API:

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

    public InventoryResult getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

Here, `create("inventory")` uses the same ID as `resilience4j.circuitbreaker.instances.inventory`. The fallback returns a backup result when the call fails or the circuit breaker rejects the call because it is `OPEN`. In real applications, the fallback must distinguish valid backup data from unrecoverable errors; do not return a fake value that misleads the calling layer into believing the data is up-to-date.

For reactive calls, use `ReactiveCircuitBreakerFactory` and keep the same `inventory` ID. Per-ID configuration remains the place where circuit breaker thresholds are managed; the reactive API style only changes how operations and fallbacks are expressed using `Mono` or `Flux`. Verify the right Spring Cloud CircuitBreaker Resilience4j starter and a version compatible with your Spring Boot version.

## 5. Configuring Timeouts and Bulkheads Under the Same Convention

A circuit breaker decides whether a new call is allowed to proceed. A timeout bounds how long a single call may wait; a bulkhead limits the number of concurrent tasks or resources allocated to a group of calls. The three mechanisms solve different problems and should be configured explicitly.

Example adding TimeLimiter and bulkhead configuration for the `inventory` instance:

```yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
        cancelRunningFuture: true
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0s
```

The values above illustrate how to structure configuration; adjust them according to your client, synchronous or reactive model, and dependent service capacity. A 3-second timeout only takes effect when the call type and integration in use actually apply TimeLimiter. Likewise, a bulkhead protects only execution segments wrapped by the corresponding bulkhead mechanism. Do not assume declaring properties in YAML automatically limits every HTTP thread or every background task.

When changing timeouts, revisit `slowCallDurationThreshold`. If the timeout is shorter than the slow-call threshold, calls may terminate with a timeout before being recorded as slow calls under that threshold. If the timeout is much longer, slow calls can tie up resources for a long time before the circuit breaker opens. Values should be designed together based on desired response times and the latency budget of the business flow.

## 6. Reproducing Conditions in Tests

A reliable test needs to pin the profile, configuration, dependent service outcomes, and input data. Do not rely on a live external service running normally or random network glitches to test a circuit breaker.

The test example below uses the `test` profile and Resilience4j's `CircuitBreakerRegistry`. It assumes the application already has the corresponding Spring Boot integration dependency to register the registry as a bean:

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
class InventoryCircuitBreakerConfigTest {

    @Autowired
    CircuitBreakerRegistry registry;

    @Test
    void opensWhenFailureRateReachesConfiguredThreshold() {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");
        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.CLOSED);

        for (int i = 0; i < 4; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(() -> {
                throw new IllegalStateException("simulated dependency failure");
            })).isInstanceOf(IllegalStateException.class);
        }

        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
    }
}
```

With `minimumNumberOfCalls: 4` and `failureRateThreshold: 50`, four error outcomes bring the failure rate to `100%`; the circuit breaker transitions to `OPEN`. The test uses an in-process exception so it has no network dependency. If the application configuration has `recordExceptions` or `ignoreExceptions` rules, ensure the test exception is classified as a recorded failure.

To test fallbacks, invoke the service layer through the Spring Cloud CircuitBreaker API and verify the fallback result once the circuit breaker is open. To test timeouts, use a simulated task with controlled execution duration and verify the timeout outcome. To test bulkheads, spawn multiple concurrent tasks with a latch or barrier to control start and completion timing. Each test should focus on one primary mechanism so failure causes are easy to identify.

`waitDurationInOpenState` can make tests time-dependent when verifying transitions to `HALF_OPEN`. For state-transition tests, set a short yet deterministic duration and control invocation timing; for other logic tests, you can use a clock or synchronization mechanism supported by your library version. Avoid long `Thread.sleep` waits for state changes if a cleaner synchronization mechanism is available.

## 7. Verifying Effective Configuration at Runtime

When a circuit breaker does not open as expected, check the following in order:

1. Is the right profile active? Confirm the `spring.profiles.active` value from the startup environment.
2. Does the instance ID match between calling code and YAML? For example, both must use `inventory`.
3. Has `minimumNumberOfCalls` been reached? Without enough samples, the failure rate will not trigger a state transition.
4. Are exceptions being recorded as failures? Ignored exceptions or exceptions outside the recorded group can produce a different rate than expected.
5. Are environment variables, command-line arguments, or external configuration sources overriding YAML?
6. Do timeout, slow-call, and bulkhead settings fit the actual call type?

Spring Boot Actuator can help observe configuration and state. In a development environment, you can enable the necessary endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops,metrics
```

The `env` endpoint helps inspect property sources and effective values; `configprops` helps view bound configurations; `health` and `metrics` help observe application health and integrated metrics. Expose only necessary endpoints, restrict access permissions, and never expose `env` or `configprops` publicly on the Internet because they can reveal sensitive configuration details. You can use Micrometer alongside a monitoring system to track circuit breaker state, succeeded/failed/rejected call counts, and failure or slow-call rates.

When using Spring Cloud Config or a centralized configuration source, record the configuration version or label loaded by the application. When using containers, record the image tag, profile, and relevant environment variables. A useful deployment record should indicate the application version, configuration version, profile, and circuit breaker instance ID. This enables the team to reproduce the configuration when comparing a healthy run against an incident run.

## 8. Conventions for Reproducible Configuration

- Keep a baseline configuration in `application.yml`; override in profiles only when there is a specific reason.
- Keep circuit breaker IDs consistent across YAML, calling code, metrics, and logs.
- Explicitly configure the sliding window, minimum sample count, failure threshold, slow-call threshold, and open wait duration.
- Choose `COUNT_BASED` when you want to control sample counts; choose `TIME_BASED` when evaluating over real time intervals.
- Pin the profile and simulate dependent service outcomes in automated tests.
- Align timeouts, slow-call thresholds, and bulkhead limits with latency budgets and service capacity.
- Manage compatible Spring Boot, Spring Cloud, and Resilience4j versions via dependency management; avoid letting each environment pull different versions.
- Store non-secret configuration in the source repository; place passwords, tokens, and sensitive details in environment variables or a secret manager.
- Monitor effective configuration and circuit breaker state with Actuator, Micrometer, or the corresponding monitoring system.

When these conventions are applied, the team can rerun the exact same scenario with the same profile and configuration set, verifying exactly when the circuit breaker opens, when the fallback is invoked, and how the system recovers. This makes developing, testing, and operating Spring Cloud Circuit Breaker more consistent across environments.
