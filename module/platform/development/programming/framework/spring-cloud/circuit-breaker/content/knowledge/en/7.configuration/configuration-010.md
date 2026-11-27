# Limitations on Updating Configuration of Existing Instances in the Registry

In Resilience4j, `CircuitBreakerRegistry` manages Circuit Breaker instances by name. The registry lets multiple components in an application retrieve the same instance so that a dependency's state, sliding window, and metrics are shared consistently.

This name-based management has an important consequence: configuration is used when the instance is created. If a Circuit Breaker already exists in the registry, calling a lookup method again with a new `CircuitBreakerConfig` generally just returns the existing managed instance; it does not automatically reconfigure that instance. Changing YAML, shared configuration, or a Java `Customizer` therefore does not mean running instances update immediately.

This lesson explains this limitation, distinguishes the configuration used to create an instance from the running instance itself, and presents controlled replacement strategies when a new configuration truly needs to take effect.

## 1. The registry manages instances by name

`CircuitBreakerRegistry` acts as both factory and store for Circuit Breakers. When requesting an instance by name, the registry will:

1. Look up an instance with that name in the registry.
2. If it already exists, return the existing instance.
3. If it does not exist, create a new instance with the selected configuration and store it in the registry.

Example:

~~~java
CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();

CircuitBreaker inventory = registry.circuitBreaker("inventory");
CircuitBreaker payment = registry.circuitBreaker("payment");
~~~

The two names `inventory` and `payment` represent two different dependencies. Each instance has its own state, counters, and sliding window.

You can ask the registry to retrieve or create an instance with a specific configuration:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .failureRateThreshold(40)
    .waitDurationInOpenState(Duration.ofSeconds(15))
    .build();

CircuitBreaker inventory = registry.circuitBreaker("inventory", config);
~~~

This method means **get the already-managed instance or create a new instance**. If the name `inventory` already exists, the registry returns that instance. The passed-in configuration is not an update command for an existing instance.

This is a common source of confusion when an application initializes Circuit Breakers in multiple places. One component may create `inventory` first with configuration A; another component calls the same name with configuration B and assumes B will be applied. In reality, both may receive the same instance created with configuration A.

## 2. Configuration and instance are two different objects

`CircuitBreakerConfig` describes rules such as:

- `failureRateThreshold`: failure rate threshold to transition to OPEN.
- `slowCallRateThreshold`: slow call rate threshold.
- `slowCallDurationThreshold`: duration from which a call is considered slow.
- `slidingWindowType` and `slidingWindowSize`: calculation mode and size of the evaluation window.
- `minimumNumberOfCalls`: minimum number of samples before evaluating rates.
- `waitDurationInOpenState`: wait duration before allowing recovery probing.

Configuration is constructed using a builder and used as a specification at the moment the Circuit Breaker is created. The running instance retains the configuration it was initialized with. Changing an external configuration source does not automatically transform an old instance into a new instance.

You can visualize the initialization flow as follows:

~~~text
application.yml / Java configuration
                 |
                 v
       CircuitBreakerConfig
                 |
                 v
       CircuitBreakerRegistry
                 |
          create by name
                 |
                 v
       CircuitBreaker instance
       - state
       - sliding window
       - metrics
       - event publisher
~~~

Therefore, distinguish two actions:

- **Changing source configuration:** updating values in YAML, shared configuration, or Java code that builds the config.
- **Changing the running instance:** making actual calls use a Circuit Breaker created with the new configuration.

Doing the first does not automatically guarantee the second.

## 3. Why calling the registry again with a new config does not update the instance

Suppose `inventory` was created with a 50% failure threshold:

~~~java
CircuitBreakerConfig firstConfig = CircuitBreakerConfig.custom()
    .failureRateThreshold(50)
    .build();

CircuitBreaker first = registry.circuitBreaker("inventory", firstConfig);
~~~

Later, the application creates a new config with a 30% failure threshold and calls the registry again:

~~~java
CircuitBreakerConfig secondConfig = CircuitBreakerConfig.from(firstConfig)
    .failureRateThreshold(30)
    .build();

CircuitBreaker second = registry.circuitBreaker("inventory", secondConfig);
~~~

`second` is still the instance already managed by the registry under the name `inventory`. Do not infer that the instance's threshold switched from 50% to 30% just because the second call passed `secondConfig`.

You can verify by reading the instance's current configuration:

~~~java
float currentThreshold = second.getCircuitBreakerConfig()
    .getFailureRateThreshold();

System.out.println(currentThreshold);
~~~

The output reflects the configuration attached to the returned instance, not necessarily the configuration passed in the most recent call.

This rule applies to overloads that retrieve an instance by name: configuration is used only when the registry needs to create a new entry. When configuration changes are needed, there must be an instance replacement strategy or an update mechanism explicitly supported by the library and version in use.

## 4. Shared configuration also does not automatically update old instances

Resilience4j allows registering shared configurations so multiple new instances can reuse them:

~~~java
CircuitBreakerConfig standardConfig = CircuitBreakerConfig.custom()
    .failureRateThreshold(50)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .build();

registry.addConfiguration("standard", standardConfig);

CircuitBreaker inventory = registry.circuitBreaker("inventory", "standard");
CircuitBreaker shipping = registry.circuitBreaker("shipping", "standard");
~~~

In this example, `inventory` and `shipping` are created from the `standard` configuration.

If the application re-registers a configuration under the same name with new values, that change affects the configuration stored by the registry under the name `standard`. Circuit Breakers already created from the earlier configuration still keep the configuration they received at initialization.

Calling to retrieve an existing instance by name and shared configuration is not an instance refresh operation either:

~~~java
registry.addConfiguration("standard", updatedConfig);

// If inventory already exists, the registry still returns the managed instance.
CircuitBreaker inventoryAgain = registry.circuitBreaker("inventory", "standard");
~~~

Thus, shared configuration standardizes instance creation, but it is not a mechanism that automatically synchronizes configuration to every running instance.

## 5. Configuration in Spring Boot and Spring Cloud

In Spring Boot, Resilience4j typically receives configuration from `application.yml`:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s

      cautious:
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 30

    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: cautious
~~~

`configs` declares reusable configurations. `instances` declares per-instance configuration and can inherit using `baseConfig`.

Spring Cloud CircuitBreaker with Resilience4j also allows default configuration via `Customizer<Resilience4JCircuitBreakerFactory>` and configuration via properties. According to Spring Cloud documentation, property configuration takes precedence over Java `Customizer` when determining Circuit Breaker configuration.

However, precedence when merging configuration at startup does not mean automatically updating an already-created instance. For example:

- The application starts, and the registry creates `inventory` from properties.
- An external configuration source changes `failureRateThreshold`.
- Environment or configuration-properties beans may receive the new value depending on the refresh mechanism in use.
- The `inventory` instance in the registry remains the existing object until the application replaces or recreates it through an explicit process.

Do not treat editing `application.yml`, updating Config Server, or calling a refresh endpoint as proof that the running Circuit Breaker has picked up the new configuration. Clarify which component reloads properties, which component creates the registry, and how instances are replaced in the library version in use.

## 6. Simplest approach: restarting the application

For applications that do not require threshold changes while running, restarting is the easiest approach to control:

1. Update `application.yml` or the corresponding configuration source.
2. Verify the new configuration is valid and compatible with the library version.
3. Deploy or restart the application according to operational procedures.
4. Let Spring Boot initialize the registry and Circuit Breakers from the new configuration.
5. Verify the actual configuration of instances after startup.

When the application reinitializes, new instances are created from the new configuration. The old instance's current state and sliding window are also not preserved as part of the new instance. If protection state or metric history matters operationally, account for this when planning deployment.

For many systems, a rolling deployment across multiple replicas applies configuration changes gradually while maintaining availability. Ensure replicas do not run with differing configurations longer than acceptable.

## 7. Replacing an instance in the registry when runtime updates are required

Resilience4j Registry provides entry management operations such as `remove(name)` and `replace(name, newEntry)`. They let the application proactively replace the instance managed by the registry. Confirm these methods exist in the `resilience4j-core` version your project uses before implementing.

You can build a new configuration from the current one to change only a few properties:

~~~java
CircuitBreaker current = registry.circuitBreaker("inventory");

CircuitBreakerConfig updatedConfig = CircuitBreakerConfig
    .from(current.getCircuitBreakerConfig())
    .failureRateThreshold(30)
    .waitDurationInOpenState(Duration.ofSeconds(20))
    .build();

CircuitBreaker replacement = CircuitBreaker.of("inventory", updatedConfig);

registry.replace("inventory", replacement)
    .orElseThrow(() -> new IllegalStateException(
        "Circuit Breaker inventory was not present in the registry"
    ));
~~~

This example creates a new instance with the new configuration and replaces the entry named `inventory` in the registry. `replace` returns the old entry if replacement succeeds.

In this example, `CircuitBreaker.of` creates the object directly. If the application relies on registry tags, customizers, or registry event consumers to attach metrics and listeners on entry creation, ensure those metadata and listeners are also applied to the replacement instance. Check how the registry handles `REPLACED` events in the exact version in use.

If the version in use lacks `replace`, you can consider `remove` followed by recreation:

~~~java
registry.remove("inventory")
    .orElseThrow(() -> new IllegalStateException(
        "Circuit Breaker inventory was not present"
    ));

CircuitBreaker replacement = registry.circuitBreaker("inventory", updatedConfig);
~~~

The `remove` then recreate approach has a window of time where the instance name does not exist. If multiple threads can access the registry concurrently, another thread could create a new instance during that gap. Therefore, do not execute this sequence arbitrarily in a live request-handling path under traffic.

`replace` also needs controlled execution. Replacing an entry in the registry does not automatically redirect Java references still holding the old instance to the new instance.

## 8. Stale references and in-flight calls

Suppose a service fetches the Circuit Breaker once in its constructor:

~~~java
@Service
public class InventoryGateway {

    private final CircuitBreaker inventoryBreaker;

    public InventoryGateway(CircuitBreakerRegistry registry) {
        this.inventoryBreaker = registry.circuitBreaker("inventory");
    }

    public InventoryResponse getInventory(String sku) {
        return inventoryBreaker.executeSupplier(
            () -> loadInventoryFromRemote(sku)
        );
    }

    private InventoryResponse loadInventoryFromRemote(String sku) {
        // HTTP call to the Inventory service
        return new InventoryResponse(sku, 25);
    }
}
~~~

If the registry replaces the `inventory` entry with a new instance, the `inventoryBreaker` field in the service still points to the old object. Calls through this field continue using the old instance's configuration and state.

You can avoid holding stale references by looking up the registry at call time:

~~~java
@Service
public class InventoryGateway {

    private final CircuitBreakerRegistry registry;

    public InventoryGateway(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public InventoryResponse getInventory(String sku) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        return breaker.executeSupplier(
            () -> loadInventoryFromRemote(sku)
        );
    }

    private InventoryResponse loadInventoryFromRemote(String sku) {
        // HTTP call to the Inventory service
        return new InventoryResponse(sku, 25);
    }
}
~~~

With this approach, each service call fetches the entry currently in the registry. After a successful entry replacement, subsequent lookups can receive the new instance.

Another approach is using an indirection layer such as `AtomicReference<CircuitBreaker>` to manage the active reference. When replacing the instance, the application updates the reference atomically. This suits situations where you want precise control over switch timing without looking up the registry on every request.

Either way, calls already started before instance replacement may continue running on the old Circuit Breaker. No entry replacement operation migrates an in-flight call onto the new object.

## 9. Consequences of replacing an instance

Replacing a Circuit Breaker with a new instance can change more than just configuration thresholds.

| Aspect | When replaced with a new instance |
| --- | --- |
| Configuration | The new instance uses the new configuration. |
| State | The new instance starts in the initial state; OPEN or HALF_OPEN state from the old instance is not transferred automatically. |
| Sliding window | Call history from the old instance does not automatically carry over to the new window. |
| Metrics | Counters and data bound to the old instance do not automatically merge into the new instance. |
| Event publisher | Listeners registered directly on the old instance do not automatically transfer to the new instance; they must be re-registered per the application's management mechanism. |
| Java references | Components still holding the old instance continue using it until updated. |

Therefore, replacing an instance can discard history needed to make decisions. For example, if the old Circuit Breaker was OPEN due to a high failure rate, creating a new instance in CLOSED will let calls pass through under the new configuration. This may be intentional during recovery, or it may send traffic back to a dependency that is still unstable.

Before replacing an instance, decide whether you should:

- Wait for in-flight calls on the old instance to finish.
- Pause or throttle traffic during the transition.
- Preserve current state via a separate operational workflow if business requirements demand it.
- Re-register metrics publishers and event consumers for the new instance.
- Update all references holding the old instance.

## 10. Example of a service managing configuration changes

An administrative class can build a new configuration, create a replacement instance, and update the registry. The following example illustrates the idea; authorization checks for changes, concurrency control, metrics, and event consumers must be added according to the real system.

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class CircuitBreakerConfigurationManager {

    private final CircuitBreakerRegistry registry;

    public CircuitBreakerConfigurationManager(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public void updateInventoryThreshold(float failureThreshold) {
        if (failureThreshold <= 0 || failureThreshold > 100) {
            throw new IllegalArgumentException(
                "failureThreshold must be greater than 0 and at most 100"
            );
        }

        CircuitBreaker current = registry.find("inventory")
            .orElseThrow(() -> new IllegalStateException(
                "Circuit Breaker inventory does not exist"
            ));

        CircuitBreakerConfig newConfig = CircuitBreakerConfig
            .from(current.getCircuitBreakerConfig())
            .failureRateThreshold(failureThreshold)
            .waitDurationInOpenState(Duration.ofSeconds(20))
            .build();

        CircuitBreaker replacement = CircuitBreaker.of(
            "inventory",
            newConfig
        );

        registry.replace("inventory", replacement)
            .orElseThrow(() -> new IllegalStateException(
                "Circuit Breaker inventory could not be replaced"
            ));
    }
}
~~~

The method validates the threshold before building the config to avoid introducing invalid values into the system. The new configuration inherits the remaining properties from the current configuration and changes the two specified properties.

In production systems, do not let arbitrary requests invoke this method. Restrict administrative permissions, log before and after values, track configuration versions, and ensure replicas receive the same decision. When using a Spring Cloud CircuitBreaker factory, verify that the factory and services retrieving Circuit Breakers all use the exact registry being replaced.

## 11. Choosing a strategy according to needs

| Need | Suitable strategy | Points to watch |
| --- | --- | --- |
| Periodic configuration updates, infrequent changes | Update properties and redeploy the application | Simple, easy to control versioning and instance lifecycle |
| Threshold changes required while application is running | Build new config and replace entry in registry | Manage stale references, state, metrics, and in-flight calls |
| Multiple services sharing a rule set | Use named shared configuration | Shared configuration mainly serves instance creation; does not auto-update old instances |
| Want to keep existing instance and state | Use direct update mechanism only if library version provides official API support for the target property | Check documentation and API for exact version; do not assume every property is mutable |
| Synchronized changes across multiple replicas | Centralized configuration management and rollout process | Avoid replicas applying different thresholds unexpectedly |

Not every application needs to swap Circuit Breakers at runtime. If configuration only changes across releases, restarting the application is usually easier to operate and verify. Build dynamic instance replacement only when there is a real requirement, traffic can be controlled, and outcomes are observable.

## 12. Post-update verification checklist

After applying a new configuration, verify in order:

1. **Right instance name:** services and registry use the exact same Circuit Breaker name.
2. **Right registry:** the factory, services, and administrative layer all operate on the application-managed registry.
3. **Right new configuration:** read `getCircuitBreakerConfig()` from the active instance and verify critical values.
4. **Right references:** services do not unexpectedly continue holding the old instance.
5. **Right state:** determine what state the new instance starts in and how it behaves when the dependency fails.
6. **Right metrics:** confirm metrics publishers and event consumers track the active instance.
7. **Right traffic:** verify new requests flow through the new instance while in-flight requests on the old instance complete as planned.
8. **Rollback readiness:** prepare a way to revert to the previous configuration if new thresholds cause the Circuit Breaker to open too frequently or fail to open when needed.

A useful test is recording `failureRateThreshold` before and after replacing the instance, then sending a request sequence with a controlled failure rate to observe when the circuit opens. Remember that the new instance's window starts with fresh history; you cannot directly compare sample counts of old and new instances as if they were a single continuous window.

## Conclusion

Resilience4j's registry manages Circuit Breakers by name and returns the existing instance when that name is requested again. Passing a new configuration into an instance lookup call does not automatically update the running object. Shared configurations and Spring Boot properties standardize initialization, yet an explicit process is still needed to apply changes to existing instances.

For infrequently changing configurations, redeploying the application is the simplest way to produce consistent new instances. When runtime changes are necessary, you can replace the registry entry with a new instance while managing stale references, in-flight calls, sliding windows, state, metrics, and event listeners. Understanding this limitation helps Spring Cloud CircuitBreaker applications using Resilience4j perform controlled configuration updates and avoid situations where YAML changed yet runtime protection behavior still retains the old configuration.

## References

- [Resilience4j CircuitBreaker — Registry and configuration](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Registry API — remove and replace](https://javadoc.io/doc/io.github.resilience4j/resilience4j-core/latest/io/github/resilience4j/core/Registry.html)
- [Resilience4j CircuitBreakerRegistry API](https://javadoc.io/doc/io.github.resilience4j/resilience4j-circuitbreaker/latest/io/github/resilience4j/circuitbreaker/CircuitBreakerRegistry.html)
- [Spring Cloud CircuitBreaker — Resilience4j configuration](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html)
