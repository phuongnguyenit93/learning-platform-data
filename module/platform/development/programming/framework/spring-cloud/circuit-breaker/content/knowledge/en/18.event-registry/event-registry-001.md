# CircuitBreakerRegistry and Named Instance Lifecycle

Resilience4j manages circuit breakers through `CircuitBreakerRegistry`. A registry is where instances are created, looked up, and managed by name. The instance name identifies a specific state machine along with its sliding window, counters, `CLOSED`/`OPEN`/`HALF_OPEN` state, and event listeners.

The key point is that **the same name in the same registry represents the same instance**. Calls that share an instance share state and metrics. Two instances with different names can use the same configuration while maintaining independent state machines. Therefore, names should reflect failure boundaries and dependency protection policies, and the registry should have a lifecycle suited to the application.

## How the Registry Manages Instances

A registry can be created directly using the Resilience4j API:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import java.time.Duration;

CircuitBreakerConfig defaultConfig = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .slowCallRateThreshold(50)
        .slowCallDurationThreshold(Duration.ofSeconds(2))
        .waitDurationInOpenState(Duration.ofSeconds(10))
        .permittedNumberOfCallsInHalfOpenState(3)
        .build();

CircuitBreakerRegistry registry =
        CircuitBreakerRegistry.of(defaultConfig);

CircuitBreaker catalogBreaker = registry.circuitBreaker("catalog");
CircuitBreaker pricingBreaker = registry.circuitBreaker("pricing");
```

The registry holds instances by name. `catalogBreaker` and `pricingBreaker` are two independent state machines, even though both are created from the default configuration. If `catalog` transitions to `OPEN`, that state does not automatically cause `pricing` to transition to `OPEN`.

When the same name is requested again on the same registry, the registry returns the already registered instance instead of creating a new state machine:

```java
CircuitBreaker first = registry.circuitBreaker("catalog");
CircuitBreaker again = registry.circuitBreaker("catalog");

assert first == again;
```

Therefore, do not call `CircuitBreakerRegistry.ofDefaults()` or create a new registry on every request. Doing so continuously creates a fresh set of state machines; requests no longer share failure history, and the breaker struggles to gather enough data to protect the dependency.

## Separating Shared Configuration from Specific Instances

The registry allows registering a named configuration and using it to create multiple instances. Instances can share thresholds while keeping their state independent:

```java
CircuitBreakerConfig remoteReadConfig = CircuitBreakerConfig.custom()
        .slidingWindowSize(30)
        .minimumNumberOfCalls(15)
        .failureRateThreshold(40)
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .build();

CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();
registry.addConfiguration("remoteRead", remoteReadConfig);

CircuitBreaker catalog = registry.circuitBreaker("catalog", "remoteRead");
CircuitBreaker pricing = registry.circuitBreaker("pricing", "remoteRead");
```

`remoteRead` is the configuration name; `catalog` and `pricing` are the instance names. When catalog experiences many failures, the catalog breaker can open while the pricing breaker stays closed. This is the difference between **sharing configuration policy** and **sharing state**.

Configurations should only be shared when dependencies have similar characteristics in latency, acceptable failure rate, and recovery budget. If one dependency typically responds in 50 ms while another normally takes several seconds, they may need different `slowCallDurationThreshold` values even if they share some common settings.

## Choosing Instance Names by Failure Boundary

Instance names should be stable, meaningful, and bounded in number. For example:

| Instance Name | Protected Scope | Reason for Separation |
|---|---|---|
| `catalog` | Catalog read calls | May have distinct latency and failure thresholds |
| `pricing` | Pricing calculation calls | Different timeout policy and criticality than catalog |
| `payment-authorize` | Payment authorization commands | Need to monitor a sensitive failure domain |

If multiple methods call the same dependency and need to share one policy, they can use the same name. In that case, failures on one call path can contribute to opening the breaker for other call paths sharing that instance. This is the desired behavior when they depend on the same system and belong to the same failure domain.

If endpoints have different capacities or protection requirements, use separate instances so statistics do not mix. Avoid constructing names from `userId`, `requestId`, product ID, or arbitrary caller data. Each new name can create another instance, sliding window, event stream, and metric; unbounded name cardinality increases memory usage and metric time-series count.

## Registry and Breaker Lifecycle

In a Spring application, the registry should typically be a singleton bean whose lifecycle is tied to the application context. Services obtain instances by name from the shared registry. A typical lifecycle includes:

1. **Application startup:** default and named configurations are registered; the registry is created once.
2. **Service initialization:** services retrieve instances such as `catalog` from the registry and hold a reusable reference.
3. **During runtime:** all calls within the same failure boundary use that instance; the breaker accumulates results and transitions states.
4. **Observability:** listeners receive state transition, error, success, or call-not-permitted events; metrics reflect aggregated counts.
5. **Application shutdown:** Spring closes the application context and releases beans/resources according to their lifecycle.

Example of configuring a registry as a bean:

```java
@Configuration
public class CircuitBreakerRegistryConfiguration {

    @Bean
    public CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();

        return CircuitBreakerRegistry.of(config);
    }
}
```

A service can receive the registry via constructor injection and obtain the instance once:

```java
@Service
public class CatalogService {

    private final CircuitBreaker catalogBreaker;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerRegistry registry,
            CatalogClient catalogClient) {
        this.catalogBreaker = registry.circuitBreaker("catalog");
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String productId) {
        return catalogBreaker.executeSupplier(
                () -> catalogClient.findProduct(productId)
        );
    }
}
```

The example above illustrates manually creating a registry bean. If the application already uses the Resilience4j Spring Boot starter and the registry is auto-configured from properties, inject the registry provided by the starter instead of declaring a competing registry. Choose one consistent configuration source so services, annotations, and metrics all observe the exact same instances.

## Configuring Instances with application.yml

With the Resilience4j Spring Boot integration, shared configurations can be declared under `configs` and instances under `instances`:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      remoteRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        slowCallRateThreshold: 50
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 15s
    instances:
      catalog:
        baseConfig: remoteRead
      pricing:
        baseConfig: remoteRead
      payment-authorize:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
```

`catalog` and `pricing` inherit the `remoteRead` configuration while keeping separate instances. `payment-authorize` declares its own policy because payment commands may require different thresholds and recovery durations. When using properties, the registry created by the Spring Boot integration receives configurations according to the Resilience4j version in use.

Do not confuse Resilience4j registry configuration with Spring Cloud Circuit Breaker's `CircuitBreakerFactory` configuration. The factory is Spring Cloud's abstraction; it accepts an ID and delegates to the corresponding backend. The registry is Resilience4j's instance management API. If a service uses `CircuitBreakerFactory.create("catalog")`, let the backend/factory manage instances via its own mechanism. If a service injects `CircuitBreakerRegistry` directly, use that registry consistently across the call path. Do not wrap the same operation with both mechanisms just to add another layer of protection.

## Inspecting and Observing Instances

The registry lets you list all registered breakers. This is useful when checking how many instances exist or building operational views:

```java
registry.getAllCircuitBreakers().forEach(circuitBreaker -> {
    log.info("Circuit breaker {} is {}",
            circuitBreaker.getName(),
            circuitBreaker.getState());
});
```

Avoid listing all instances on every request. Use it for administrative endpoints, diagnostic checks, or observation tasks at an appropriate cadence. The state at read time is only a snapshot; it can change immediately afterward as other requests complete.

You can register listeners on an instance's event publisher:

```java
CircuitBreaker catalog = registry.circuitBreaker("catalog");

catalog.getEventPublisher()
        .onStateTransition(event -> log.info(
                "{} transitioned: {}",
                event.getCircuitBreakerName(),
                event.getStateTransition()))
        .onCallNotPermitted(event -> log.warn(
                "{} rejected a call because it is not permitted",
                event.getCircuitBreakerName()))
        .onError(event -> log.warn(
                "{} recorded a failed call",
                event.getCircuitBreakerName(),
                event.getThrowable()));
```

Register listeners once during bean creation or service initialization, not on every method call. Keep callbacks lightweight and do not perform slow I/O directly on the request-handling thread. If you need to send notifications or store audit records, forward events to a bounded asynchronous mechanism.

Events describe what just happened, such as a transition from `CLOSED` to `OPEN`. Metrics provide aggregated figures such as successful, failed, slow, or rejected call counts. Both data sources complement each other: events help reconstruct a timeline, while metrics help evaluate trends.

## Removing or Replacing Instances

A registry can support removing an instance by name. This is a lifecycle operation, not a way to reset a breaker after each request. Before removing an instance, know which services hold references to it.

When an instance is removed from the registry, previously obtained Java references do not automatically disappear. A service holding a reference can continue calling the old instance, while a new lookup with the same name can create a different instance. The system could then have two state machines with the same name across different references, making metrics and events hard to interpret.

Therefore:

- Do not remove an instance actively used by services just to return the breaker to `CLOSED`.
- Use supported reset/state transition APIs if the goal is state recovery, after evaluating the operational impact.
- If configuration changes are needed, use the configuration update mechanism supported by your Resilience4j version or run a coordinated replacement process; ensure all consumers switch to the same new instance.
- Only remove an instance when it is no longer in use, no requests are in flight, and there is a plan for handling old listeners, metrics, and references.

An in-JVM registry does not share state with registries in other replicas. If an application runs four pods, each pod has its own `catalog` instance, sliding window, and breaker state. One pod may be `OPEN` while another remains `CLOSED`. This is a local protection mechanism; it is not a distributed state machine or a cluster-wide state coordinator.

## Common Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Creating a registry on every request | Failure history is fragmented; the breaker cannot accumulate enough samples | Use a singleton registry scoped to the application context |
| Building instance names from request/user IDs | Instance and metric counts grow without bound | Use fixed names aligned with dependency/failure domain |
| Sharing one instance across independent dependencies | Failures in dependency A can trip calls to dependency B | Split instances along failure boundaries |
| Creating same-named instances across multiple registries | State machines do not share state despite having the same name | Use a single, centrally managed registry |
| Removing a registry entry while services keep old references | The same name can exist on different instances simultaneously | Coordinate lifecycle and update consumers |
| Registering event listeners on every request | Callbacks fire repeatedly and waste resources | Register listeners once during initialization |
| Assuming the registry synchronizes across pods | Misdiagnosis when replicas show different states | Observe state per instance/replica |

## Testing the Registry and Lifecycle

A test suite should verify instance identity, state machine independence, and how listeners are registered:

1. Retrieve `catalog` twice from the same registry and verify both references point to the same instance.
2. Retrieve `catalog` and `pricing`; verify the two instances are independent even when sharing configuration.
3. Trigger enough failures on `catalog`; verify `catalog` transitions state according to thresholds and `pricing` is unaffected.
4. Register a listener once; verify state transition events are received the expected number of times.
5. Inspect the registry listing after creating instances to confirm names and counts are accurate.
6. If testing remove/recreate, verify services no longer use the old reference before switching to the new instance.
7. Run multiple replicas in integration tests if you need to verify that state is local to each JVM.

Example testing identity and independence:

```java
@Test
void registryReusesNamedInstanceButSeparatesDifferentNames() {
    CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();

    CircuitBreaker firstCatalog = registry.circuitBreaker("catalog");
    CircuitBreaker secondCatalog = registry.circuitBreaker("catalog");
    CircuitBreaker pricing = registry.circuitBreaker("pricing");

    assertSame(firstCatalog, secondCatalog);
    assertNotSame(firstCatalog, pricing);
    assertEquals(2, registry.getAllCircuitBreakers().size());
}
```

When testing state transitions, configure `minimumNumberOfCalls` and thresholds appropriately so tests can trigger transitions deterministically. Avoid relying on long sleep durations; use small configurations in tests and observe events or state directly.

## Operational Principles

Treat the registry as an application-scoped instance store, and the instance name as the identifier of a failure boundary. Create the registry once, reuse instances by name, share configurations when policies match, and separate state machines when dependencies are independent. Observe events and metrics from the exact same instance that services actually use; any instance change or removal must include a plan to update all references. Managing instances this way ensures `CLOSED`, `OPEN`, and `HALF_OPEN` reflect the history of the right dependency and keeps protection behavior consistent throughout the application's lifecycle.
