# Retrieving the Same Instance vs. Creating an Independent Registry

In Resilience4j, a **registry** manages Circuit Breaker instances by name. When retrieving a Circuit Breaker with the same name from the same registry, the application receives the already managed instance, so the CLOSED, OPEN, or HALF_OPEN state, sliding window, metrics, and event listeners all belong to the same object. If an independent registry is created and the same name is requested, the application receives a different Circuit Breaker with its own state and history.

This distinction is important when implementing Circuit Breakers in Spring Cloud. If every request creates a new registry, the application unintentionally fragments failure history across many instances, making the failure rate threshold hard to reach and preventing the OPEN state from being shared across requests. Normally, the registry should be managed as a shared component across the application lifecycle; components calling external services look up instances by name from that registry.

## 1. Registry and Circuit Breaker Instances

`CircuitBreakerRegistry` is where Circuit Breakers are stored and looked up. Each Circuit Breaker has its own name, configuration, and state. The registry allows retrieving an instance by name, listing managed instances, and applying default or specified configurations.

Three concepts to distinguish:

| Component | Role |
| --- | --- |
| Registry | Manages the collection of Circuit Breakers and their identifiers |
| Circuit Breaker instance | Tracks state, sliding window, call outcomes, and emits events |
| Instance name | Key used to look up the corresponding Circuit Breaker within a registry |

For example, the Order service calls the Inventory service. The application retrieves an instance named `inventory` from the registry and uses that instance to wrap calls to Inventory. Other requests must also retrieve the same `inventory` instance from the shared registry to share failure history and circuit state.

A single registry can manage multiple instances:

~~~mermaid
flowchart TD
    A[Shared CircuitBreakerRegistry] --> B[inventory instance]
    A --> C[payment instance]
    A --> D[customer-profile instance]
    B --> E[Sliding window and state of inventory]
    C --> F[Sliding window and state of payment]
    D --> G[Sliding window and state of customer-profile]
~~~

Instances in the same registry have separate names and states. Sharing a registry does not mean all services share one Circuit Breaker; each name still represents an independent object.

## 2. Retrieving the Same Instance with the Same Name

When calling `registry.circuitBreaker("inventory")` multiple times on the same registry, Resilience4j returns the instance already registered under that name if it exists. If it does not exist yet, the registry creates a new instance and manages it.

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import java.time.Duration;

public class InventoryCircuitBreakers {
    private final CircuitBreakerRegistry registry;

    public InventoryCircuitBreakers() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();

        this.registry = CircuitBreakerRegistry.of(config);
    }

    public CircuitBreaker firstLookup() {
        return registry.circuitBreaker("inventory");
    }

    public CircuitBreaker secondLookup() {
        return registry.circuitBreaker("inventory");
    }
}
~~~

The two methods above look up the same registry and the same name. If you call:

~~~java
CircuitBreaker first = inventoryCircuitBreakers.firstLookup();
CircuitBreaker second = inventoryCircuitBreakers.secondLookup();

boolean sameInstance = first == second; // true
~~~

`sameInstance` is `true` because both variables reference the same object. Therefore:

- Calls through `first` and `second` update the same sliding window.
- If a call causes the instance to transition to OPEN, subsequent lookups still see the OPEN state.
- Event listeners registered on that instance receive events from calls going through the same instance.
- Metrics for the instance reflect the aggregated activity recorded by that instance.

This is the required behavior when multiple requests protect the same dependency. The Circuit Breaker must accumulate enough samples from different requests to evaluate the failure rate and slow call rate.

## 3. Same Name in Different Registries Yields Independent Instances

An instance name only has meaning within the registry managing it. Two different registries can both contain the name `inventory`, but each registry creates and manages its own separate Circuit Breaker:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(10))
        .build();

CircuitBreakerRegistry registryA =
        CircuitBreakerRegistry.of(config);
CircuitBreakerRegistry registryB =
        CircuitBreakerRegistry.of(config);

CircuitBreaker inventoryA = registryA.circuitBreaker("inventory");
CircuitBreaker inventoryB = registryB.circuitBreaker("inventory");

boolean sameInstance = inventoryA == inventoryB; // false
~~~

`inventoryA` and `inventoryB` do not share state, sliding windows, or event listeners. If `inventoryA` transitions to OPEN, `inventoryB` can still remain CLOSED because it has not recorded the calls that caused instance A to open.

Comparison diagram:

~~~mermaid
flowchart TD
    A[Registry A] --> B[inventory instance A]
    C[Registry B] --> D[inventory instance B]
    B --> E[State and sliding window A]
    D --> F[State and sliding window B]
    E -. Not shared .- F
~~~

Creating independent registries is appropriate when truly isolated state domains are required, such as two applications or two processing groups with separate lifecycles and policies. Within an application serving the same dependency, creating multiple registries only to look up the same name is usually a design flaw because each registry accumulates separate data.

## 4. What Happens When Creating a New Registry Per Request?

The following example should not be used in a service:

~~~java
public Inventory getInventory(String sku) {
    CircuitBreakerRegistry registry =
            CircuitBreakerRegistry.ofDefaults();
    CircuitBreaker circuitBreaker =
            registry.circuitBreaker("inventory");

    return circuitBreaker.executeSupplier(
            () -> inventoryClient.get(sku));
}
~~~

Each time `getInventory` is called, the code creates a new registry and a new Circuit Breaker. Suppose 100 requests call the Inventory service and 40 fail. Instead of one instance seeing 100 outcomes and potentially reaching a 50% failure threshold, the application may create 100 separate instances, each seeing only one outcome. No instance has enough samples to open the circuit.

Other consequences:

- The OPEN state is not preserved for subsequent requests.
- The sliding window is fragmented, so the failure rate does not reflect overall traffic.
- Event listeners must be registered repeatedly and are hard to manage across their lifecycle.
- Metrics can become inconsistent or create many unnecessary measurement objects.
- Continuously creating registries and instances increases allocation overhead and complicates observability.

Create the registry once during the application lifecycle or use the registry auto-configured by Spring Boot/Resilience4j. On each request, simply look up the instance by name from the shared registry.

## 5. Managing the Registry as a Shared Component in Spring

When an application uses the Resilience4j Spring Boot starter, the registry is typically configured and managed by auto-configuration. Inject the configured registry instead of creating registries inside individual services or requests.

Example of a service receiving the registry via constructor injection:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreaker inventoryCircuitBreaker;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerRegistry registry,
            InventoryClient inventoryClient) {
        this.inventoryCircuitBreaker =
                registry.circuitBreaker("inventory");
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        return inventoryCircuitBreaker.executeSupplier(
                () -> inventoryClient.get(sku));
    }
}
~~~

The constructor runs when Spring creates the bean, so the instance is looked up once and reused across requests. If a service has multiple dependencies, you can retrieve one instance per name and store them in their respective fields.

If the application configures the registry manually instead of relying on auto-configuration, you can declare a singleton bean:

~~~java
@Configuration
public class CircuitBreakerRegistryConfiguration {
    @Bean
    CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();
        return CircuitBreakerRegistry.of(config);
    }
}
~~~

Only declare a manual bean when the application does not have a suitable registry provided by the starter or when intentionally overriding the default configuration. Do not create multiple registry beans for the same purpose without clearly defining which registry gets injected.

## 6. Instance Configuration and Lookup Behavior

Instances can be configured in `application.yml`:

~~~yaml
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
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: default
        failureRateThreshold: 30
        waitDurationInOpenState: 30s
~~~

The registry and Spring integration use instance names to bind calls to their corresponding configurations. For `inventory`, all components looking up the same name in the shared registry share the same instance. `payment` is a separate instance with its own state and window.

One important point is that configuration is attached to an instance when it is created. Do not look up the same name multiple times with different configurations expecting each variable to receive a separate configuration. If different policies are needed for operations with different characteristics, use different instance names, such as `inventory-read` and `inventory-reservation`.

When changing configuration, hot-update behavior depends on how the application reloads configuration and the integration version in use. Do not assume an already created instance automatically picks up every YAML change; verify the refresh or re-initialization mechanism implemented in your specific environment.

## 7. Retrieving an Existing Instance or Creating a New One?

Within the same registry, lookup-by-name methods generally follow get-or-create behavior:

| Operation | Meaning |
| --- | --- |
| `registry.circuitBreaker("inventory")` | Retrieves an existing instance; if absent, creates one using the default configuration |
| `registry.circuitBreaker("inventory", config)` | Retrieves an instance by name or creates a new one using the provided configuration if the name does not exist yet |
| `registry.find("inventory")` | Finds an already existing instance without creating a new one |
| `registry.getAllCircuitBreakers()` | Returns the set of instances currently managed by the registry |

Once the `inventory` instance exists, calling the lookup method with the same name again does not create a new sliding window. Therefore, finalize the configuration before the instance is used for the first time. If you want a Circuit Breaker with separate state, choose a different name or intentionally create a separate registry.

## 8. Attaching Event Listeners to a Shared Instance

A Circuit Breaker provides an event publisher to observe events such as successful, failed, rejected calls, or state transitions. Listeners should be registered once on the shared instance, for example when Spring initializes a bean:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerEventConfiguration {
    @Bean
    CircuitBreaker inventoryCircuitBreaker(
            CircuitBreakerRegistry registry) {
        CircuitBreaker circuitBreaker =
                registry.circuitBreaker("inventory");

        circuitBreaker.getEventPublisher()
                .onStateTransition(event ->
                        log.info("Inventory circuit breaker state transition: {}", event))
                .onError(event ->
                        log.warn("Inventory circuit breaker error: {}", event))
                .onSuccess(event ->
                        log.debug("Inventory circuit breaker success: {}", event));

        return circuitBreaker;
    }
}
~~~

In the example, `log` is the logger of the configuration class. The listener attaches directly to the `inventory` instance; calls passing through that same instance emit events to this listener. If each request creates a new registry and instance, the listener cannot observe a centralized event stream and the application may register many duplicate listeners.

Events can be used to:

- Record when the circuit transitions from CLOSED to OPEN or from OPEN to HALF_OPEN.
- Count errors and rejected calls.
- Emit signals to observability or alerting systems.
- Aid diagnosis when a dependency recovers or continues failing.

Do not perform blocking operations or call back into the dependent service inside an event listener. Listeners should process quickly to avoid slowing down the event-emitting thread. If events must be sent to another system, offload the work to a bounded asynchronous mechanism with its own error handling.

## 9. Registry Events and Circuit Breaker Events Are Different

The two event types have different scopes:

| Event Type | Scope | Example |
| --- | --- | --- |
| Registry event | Lifecycle of entries in the registry | A Circuit Breaker is added to or replaced in the registry |
| Circuit Breaker event | Activity of a specific instance | Call succeeded, failed, was rejected, or state transitioned |

If the goal is to observe the health of the Inventory service, the event publisher of the `inventory` instance is the appropriate source. If the goal is to track the creation and management of instances within the registry, use Resilience4j's corresponding registry event mechanism.

Do not confuse the "instance added to registry" event with the "Circuit Breaker transitioned to OPEN" event. The first reflects configuration lifecycle; the second reflects call status and dependency health.

## 10. Verifying the Two Ways of Retrieving Instances

You can verify identity and state behavior with a simple example:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(5))
        .build();

CircuitBreakerRegistry sharedRegistry =
        CircuitBreakerRegistry.of(config);

CircuitBreaker first = sharedRegistry.circuitBreaker("inventory");
CircuitBreaker second = sharedRegistry.circuitBreaker("inventory");

assert first == second;

CircuitBreakerRegistry isolatedRegistry =
        CircuitBreakerRegistry.of(config);
CircuitBreaker isolated =
        isolatedRegistry.circuitBreaker("inventory");

assert first != isolated;
~~~

To test state, you can generate enough failed calls through `first` to reach the threshold. Then read the state via `second`; because both variables reference the same instance, `second.getState()` will reflect the updated state. Reading `isolated.getState()` still reflects the separate history of the independent registry.

In tests, use a small window configuration and short OPEN duration to observe state transitions quickly. Do not use those test values as production configuration without evaluating actual traffic and latency.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a registry on every request | Each request has its own state and sliding window | Inject a shared registry and look up instances by name |
| Creating the same name in two registries and assuming they share state | One instance is OPEN while the other remains CLOSED | Use the same registry when state needs to be shared |
| Using one name for operations needing separate policies | Operations share state and configuration | Split instance names by dependency or operation group |
| Registering event listeners on every request | Duplicate listeners, duplicated logs or metrics | Register listeners once during bean lifecycle |
| Looking up the same name with different configs expecting to replace the existing config | The already created instance continues to be used | Finalize configuration before creation or use a different name |
| Manually creating a registry even though Spring already provides a configured registry | Multiple places manage state and observability becomes harder | Use the auto-configured registry or override intentionally |
| Not monitoring state transition events | Hard to know when the circuit opens and recovers | Register listeners and monitor metrics |

## 12. Workflow for Choosing Registry and Instances

When implementing a Circuit Breaker for a dependency, follow this sequence:

1. Identify which call groups need to share state and which need independent Circuit Breakers.
2. Use the registry managed by Spring/Resilience4j or create a singleton registry if configuring manually.
3. Choose a stable instance name, such as `inventory`, and declare the corresponding configuration.
4. Look up the instance once when initializing the service or bean; do not create a registry on each request.
5. Register event listeners on the shared instance if you need to track state transitions and call outcomes.
6. Verify that two lookups with the same name in the same registry return the same instance, while independent registries create separate instances.
7. Observe metrics and events to confirm state and sliding windows are shared within the intended scope.

Retrieving the same instance from a shared registry enables requests targeting the same dependency to share state, sliding windows, and events. Creating independent registries is only suitable when intentionally isolating state domains. Managing the registry according to the application lifecycle and registering listeners once keeps Circuit Breakers consistent, observable, and effective at protecting Spring Cloud services from cascading failures.
