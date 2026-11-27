# Reconciling Desired Configuration with Existing Runtime Instances

A syntactically valid YAML file does not guarantee that a Circuit Breaker is running with the intended policy. The application may load a different profile, override properties via environment variables, create an instance under a different name, or have initialized the instance before configuration changed. Therefore, when operating Resilience4j in Spring Cloud, reconcile the desired configuration with the actual configuration of the existing runtime instance, while also inspecting state and metrics to understand current behavior.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, this reconciliation helps identify why a Circuit Breaker transitioned to OPEN, why thresholds are not taking effect, or why a call is falling back to default configuration. Distinguish three layers of information: declared configuration, final effective configuration attached to the runtime instance, and dynamic state produced by calls that have occurred.

## 1. Three Layers of Information to Reconcile

| Layer | Example | Meaning |
| --- | --- | --- |
| Desired configuration | YAML declares window size 40 and failure threshold 45% | The policy the development team intends to use |
| Effective instance configuration | CircuitBreakerConfig attached to instance inventory-read | The values Resilience4j actually uses after binding, inheritance, and application |
| Runtime state | CLOSED, OPEN, HALF_OPEN; call counts and failure rate | Operational outcome at observation time, changing with traffic |

Do not conclude configuration is wrong merely because an instance is OPEN. An instance may be using the exact 45% threshold and have recorded enough errors to open the circuit. Conversely, an instance in CLOSED does not prove configuration was applied properly; it may not have accumulated enough samples yet or may be using default thresholds.

The verification sequence should answer in order:

1. Did the application load the expected configuration and profile?
2. Does the instance name in code match the key under resilience4j.circuitbreaker.instances?
3. What configuration values does the existing instance actually hold?
4. What do state and metrics show happened to recent calls?

## 2. Identifying the Exact Instance Name

Resilience4j looks up configuration by instance name. For example, if the code uses:

~~~java
CircuitBreaker circuitBreaker =
        circuitBreakerRegistry.circuitBreaker("inventory-read");
~~~

then the corresponding configuration must sit under:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 40
        minimumNumberOfCalls: 20
        failureRateThreshold: 45
~~~

The name must match the exact identifier used by the application. With Spring Cloud CircuitBreaker, the name passed to the factory such as create("inventory-read") must match the instance used by the Resilience4j implementation. With OpenFeign, names may be generated from client and method via a naming resolver; verify the runtime ID rather than guessing from the service name.

A common mistake is configuring instances.inventory while code creates inventory-read, or a resolver generating a normalized ID that differs from the YAML key. In that case, the intended instance may go unused and the application falls back to default configuration.

## 3. Checking Effective Configuration from the Spring Environment

Spring Boot can load multiple configuration sources: default files, profile-specific files, environment variables, command-line arguments, and external configuration sources. Effective values can differ from values visible in a single YAML file.

For example, the prod profile may override failureRateThreshold; environment variables can also override file properties. Identify the active profile and the final value supplied by the Spring Environment.

You can use Binder to read a property under Spring Boot's relaxed binding rules:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerPropertyInspector {
    private final Environment environment;

    public CircuitBreakerPropertyInspector(Environment environment) {
        this.environment = environment;
    }

    public Integer configuredWindowSize() {
        return Binder.get(environment)
                .bind(
                        "resilience4j.circuitbreaker.instances.inventory-read.sliding-window-size",
                        Integer.class)
                .orElse(null);
    }
}
~~~

The returned value shows what was bound from active property sources. If an instance uses baseConfig, properties may be inherited from a shared config rather than appearing directly under the instance key. Therefore, reading one individual property from Environment is not enough to confirm the full effective configuration.

When you need to see which source provided an override, the Actuator env endpoint can help inspect property sources and origins if enabled. This endpoint can expose sensitive configuration details; expose it only within a controlled scope protected by appropriate authentication and authorization. Never open configuration environment endpoints publicly merely for debugging convenience.

## 4. Reading Configuration Attached to the Runtime Instance

A more direct check is retrieving the existing instance from CircuitBreakerRegistry and reading its attached CircuitBreakerConfig. Use find(name) to check whether an instance has been created; do not call circuitBreaker(name) just to probe, because that method can create a new instance if none exists yet.

Example:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerRuntimeInspector {
    private static final Logger log =
            LoggerFactory.getLogger(CircuitBreakerRuntimeInspector.class);
    private final CircuitBreakerRegistry registry;

    public CircuitBreakerRuntimeInspector(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public void inspectInventory() {
        CircuitBreaker breaker = registry.find("inventory-read")
                .orElseThrow(() ->
                        new IllegalStateException(
                                "Circuit Breaker inventory-read has not been created yet"));

        CircuitBreakerConfig config =
                breaker.getCircuitBreakerConfig();

        log.info(
                "CircuitBreaker name={}, state={}, windowType={}, windowSize={}, "
                        + "minimumCalls={}, failureThreshold={}, slowCallThreshold={}, "
                        + "slowCallRateThreshold={}, halfOpenPermits={}",
                breaker.getName(),
                breaker.getState(),
                config.getSlidingWindowType(),
                config.getSlidingWindowSize(),
                config.getMinimumNumberOfCalls(),
                config.getFailureRateThreshold(),
                config.getSlowCallDurationThreshold(),
                config.getSlowCallRateThreshold(),
                config.getPermittedNumberOfCallsInHalfOpenState()
        );
    }
}
~~~

This snippet illustrates inspecting the configuration and state of an existing instance. Verify getter APIs against the Resilience4j version your project uses; if signatures differ across versions, use the corresponding API for that version.

If find("inventory-read") does not find an instance, check whether any call has executed yet, whether the factory created an instance under a different ID, and whether the injected registry is the same registry used by the integration. Do not create a new instance during diagnosis and conclude production configuration was loaded.

## 5. Reconciling Each Critical Parameter

Create an expected-values table for each instance and compare it against runtime configuration:

| Property | Example Desired Value | What to Confirm |
| --- | --- | --- |
| Instance name | inventory-read | Matches the ID used when creating the Circuit Breaker |
| slidingWindowType | COUNT_BASED | Window unit is call count |
| slidingWindowSize | 40 | Window size is the latest 40 outcomes |
| minimumNumberOfCalls | 20 | Rates are not evaluated before 20 samples |
| failureRateThreshold | 45 | Circuit opens at 45% failure rate |
| slowCallDurationThreshold | 1500ms | Calls exceeding 1.5 seconds count as slow |
| slowCallRateThreshold | 60 | Slow-call rate threshold is 60% |
| waitDurationInOpenState | 10s | Wait duration before recovery probing |
| permittedNumberOfCallsInHalfOpenState | 3 | Maximum of 3 trial calls permitted |

Not every property has a getter returning the exact same type across all versions. For example, OPEN wait duration may be represented as a duration or an interval function. When comparing, normalize to the same unit and check semantics rather than just comparing formatted strings.

## 6. Reading State and Metrics Separately from Configuration

After verifying configuration, read metrics to understand why the instance is in its current state:

~~~java
CircuitBreaker breaker = registry.find("inventory-read")
        .orElseThrow();

CircuitBreaker.Metrics metrics = breaker.getMetrics();

log.info(
        "name={}, state={}, bufferedCalls={}, failedCalls={}, "
                + "successfulCalls={}, failureRate={}, slowCallRate={}, rejectedCalls={}",
        breaker.getName(),
        breaker.getState(),
        metrics.getNumberOfBufferedCalls(),
        metrics.getNumberOfFailedCalls(),
        metrics.getNumberOfSuccessfulCalls(),
        metrics.getFailureRate(),
        metrics.getSlowCallRate(),
        metrics.getNumberOfNotPermittedCalls()
);
~~~

Metrics are a statistical snapshot at read time. Depending on version and state, some rates may lack sufficient samples and be represented as undefined or sentinel values. Handle such values properly in dashboards and logs instead of interpreting missing data as a 0% rate.

Distinguish:

- state shows whether the Circuit Breaker is currently CLOSED, OPEN, or HALF_OPEN.
- bufferedCalls shows how many outcomes are currently retained in the window.
- failedCalls and successfulCalls show recorded outcomes.
- failureRate and slowCallRate show statistical rates.
- rejectedCalls shows how many calls were rejected when the circuit disallowed execution.

An OPEN instance with a 70% failure rate and a 45% threshold may be operating strictly according to policy. A CLOSED instance with 3 failed calls when minimum calls is 20 may also be correct, because it has not reached enough samples for evaluation.

## 7. Inspecting via Spring Boot Actuator

If the application includes Actuator and the matching Resilience4j Actuator integration dependencies, dedicated endpoints can assist operations:

- circuitbreakers: view Circuit Breaker instances and current state.
- circuitbreakerevents: view events such as successes, errors, rejections, and state transitions.
- metrics: inspect Micrometer-registered meters.
- env: inspect property sources and effective configuration values if enabled.

Example exposing required endpoints in a management environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,circuitbreakers,circuitbreakerevents
~~~

Exact endpoint names and payloads depend on dependencies, Spring Boot/Resilience4j versions, and exposure settings. Check the application's actual endpoint list. Expose only required endpoints and protect them via management networks, authentication, and authorization.

Actuator helps inspect state, events, and metrics; not every endpoint displays the entire merged configuration of an instance. When you need to confirm runtime slidingWindowSize, minimumNumberOfCalls, or thresholds, use a registry inspector to read the config directly attached to the instance.

## 8. Distinguishing Non-Existent Instances from Instances Using Defaults

These cases are easily confused:

| Situation | Symptom | Resolution |
| --- | --- | --- |
| Instance not yet created | registry.find(name) returns empty | Check call path, factory name, and when the instance is created |
| Instance created under another name | Registry has a similar instance but not the exact name | Log actual runtime ID and compare against resolver |
| Instance exists but uses defaults | Runtime config differs from desired YAML | Check property binding, baseConfig, profile, and key names |
| Instance uses right config but is OPEN | Runtime config matches; metrics exceed threshold | Investigate dependency errors/latency; do not change config just because state is OPEN |
| Existing instance retains prior config | File changed but runtime config did not | Check refresh mechanism and when the instance was initialized |

Never use registry.circuitBreaker(name) as an existence check. That method can create a new instance and mutate what is being observed. Use find(name) or enumerate getAllCircuitBreakers() to inspect registered instances.

## 9. Understanding baseConfig and Configuration Loading Order

An instance can inherit policy from configs:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
      inventory-policy:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 40
        minimumNumberOfCalls: 20
        failureRateThreshold: 45
        waitDurationInOpenState: 10s
    instances:
      inventory-read:
        baseConfig: inventory-policy
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
~~~

In this example, inventory-policy is a named config containing full base values for inventory read operations; the inventory-read instance references that config and adds instance-specific properties. When reconciling, inspect the final merged configuration after baseConfig is applied rather than reading a single YAML block.

Profiles or external configuration sources can override properties. If runtime values differ from expectations, check active profiles, loaded configuration files, environment variables, and deployment arguments. Do not tune thresholds before identifying which source is supplying the final value.

## 10. Configuration Changes While Instances Already Exist

Editing application.yml does not automatically update a Circuit Breaker that has already been created. A Resilience4j instance retains the configuration attached when it was initialized; hot-update capability depends on the refresh mechanism, integration, and application version.

When changing configuration, verify:

1. The new file or configuration source has been loaded.
2. Spring Environment returns the desired value.
3. The integration supports refreshing existing instances.
4. The registry inspector shows the config attached to the instance has changed.
5. Whether existing state is preserved or the instance is recreated/reset by the update mechanism.

Without a supported, verified refresh mechanism, redeploy the application via standard rollout procedures so instances are built from the new configuration. Avoid deleting or recreating instances arbitrarily in production, as doing so can discard sliding window history, events, and state needed for investigation.

## 11. Example Test Verifying Configuration

A test in a Spring context can confirm configuration bound properly and the runtime instance received the expected values:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class InventoryCircuitBreakerConfigurationTest {
    @Autowired
    CircuitBreakerRegistry registry;

    @Test
    void inventoryInstanceUsesExpectedConfiguration() {
        CircuitBreaker breaker = registry.find("inventory-read")
                .orElseThrow();
        CircuitBreakerConfig config =
                breaker.getCircuitBreakerConfig();

        assertEquals(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED,
                config.getSlidingWindowType());
        assertEquals(40, config.getSlidingWindowSize());
        assertEquals(20, config.getMinimumNumberOfCalls());
        assertEquals(45.0f, config.getFailureRateThreshold());
    }
}
~~~

This test requires the test context configuration to define the inventory-read instance with the desired values. It checks runtime configuration, not merely that a YAML file exists. If the project uses multiple profiles, run tests with the relevant profile or write dedicated tests for each critical profile.

When testing state transitions, use dedicated test instances and do not let tests mutate state on a registry shared across tests. Keep configuration verification separate from testing that a Circuit Breaker opens after a sequence of failures.

## 12. Workflow When Desired Configuration and Runtime Mismatch

When a discrepancy is detected, proceed in order:

1. Verify the exact instance name from calling code or naming resolver.
2. Use registry.find(name) to confirm the instance already exists.
3. Read the runtime configuration attached to the instance.
4. Reconcile against desired configuration, including baseConfig and overrides.
5. Inspect profiles, environment variables, deployment flags, and external config sources.
6. Check when the instance was created and whether the integration supports refresh.
7. Read state, sliding window metrics, and events to understand current behavior.
8. Only change configuration after identifying the source of mismatch; after deployment, re-read the instance to confirm.

An operational reconciliation sheet should record instance name, profile, window type, window size, minimum calls, failure threshold, slow-call threshold, OPEN wait duration, current state, and observation timestamp. This lets teams compare dev, staging, and production without confusing dynamic state with static configuration.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Reading YAML only without inspecting the instance | Misses overriding profiles or property sources | Read the config attached to the runtime instance |
| Using the wrong instance name | Calls use default configuration or another instance | Reconcile names across code, factory, and YAML |
| Calling circuitBreaker(name) to check existence | Accidentally creates a new instance during diagnosis | Use find(name) or list the registry |
| Confusing OPEN state with misconfiguration | Unnecessary threshold changes | Compare config first, then read metrics and events |
| Looking only at CLOSED state | Misses that the instance lacks samples or uses defaults | Check config and recorded sample count |
| Assuming YAML edits update instances immediately | Runtime keeps using old configuration | Verify refresh support or redeploy via rollout |
| Exposing Actuator env unprotected | Can leak sensitive configuration data | Limit exposure, enforce authentication and authorization |
| Comparing durations in different units | False conclusion that runtime values mismatch | Convert to the same unit before comparing |

## 14. Takeaways

Reconciling desired configuration with existing runtime instances requires examining both effective configuration and runtime state. Use exact instance names, retrieve existing instances with find, read CircuitBreakerConfig and metrics, and check Spring Boot profiles and override sources. Once static configuration is clearly separated from dynamic state, operations teams can determine whether a Circuit Breaker is enforcing the intended policy or running with the wrong instance/configuration, enabling safe, evidence-based adjustments.
