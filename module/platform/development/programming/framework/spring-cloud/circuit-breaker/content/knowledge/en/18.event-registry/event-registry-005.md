# Listening to State Transitions and Avoiding Duplicate Listener Registration

A circuit breaker provides more than just the outcome of individual calls. It also emits events when a call succeeds, fails, is rejected, or when the state transitions from `CLOSED` to `OPEN`, `HALF_OPEN`, and back. Listening to these events helps development teams know when a dependency begins degrading, when the circuit breaker starts blocking requests, and when the service shows signs of recovery.

With Spring Cloud CircuitBreaker using Resilience4j, listeners can be registered on the event publisher of each `CircuitBreaker`. When using `CircuitBreakerRegistry` directly, you can listen to registry entry-added events and attach listeners to new instances. The key is registering listeners according to the circuit breaker's lifecycle—typically during configuration or when the registry creates an entry—rather than re-registering on every request. If the same listener is attached repeatedly, a single state transition can produce duplicate logs, notifications, or side effects.

## 1. CircuitBreaker Events

Resilience4j emits events describing circuit breaker activity. Those most useful in operations include:

| Event | Meaning | Operational Value |
|---|---|---|
| `onSuccess` | A protected call completed successfully. | Track successful call count and latency. |
| `onError` | A call ended with a recorded error. | Investigate exceptions from the supplier and dependency failures. |
| `onIgnoredError` | The supplier threw an exception configured to be ignored. | Separate business errors that do not affect the failure rate. |
| `onCallNotPermitted` | The circuit breaker rejected a call before the supplier ran. | Know when requests are blocked while open or out of probe permissions. |
| `onStateTransition` | The circuit breaker state changed. | Track when the circuit opens, begins probing, or closes again. |
| `onFailureRateExceeded` | The failure rate exceeded the configured threshold. | Investigate why the circuit transitioned to `OPEN`. |
| `onSlowCallRateExceeded` | The slow-call rate exceeded the threshold. | Detect a slow-responding dependency before many exceptions occur. |
| `onReset` | The circuit breaker was reset. | Recognize reset operations during maintenance or testing. |

The `onStateTransition` event is especially valuable because it describes actual state changes. For example, `CLOSED_TO_OPEN` indicates the circuit breaker cut off calls; `OPEN_TO_HALF_OPEN` indicates the circuit began its probing phase; `HALF_OPEN_TO_CLOSED` indicates probe calls met the configured requirement.

Some Resilience4j versions also include special states such as `METRICS_ONLY`, `DISABLED`, or `FORCED_OPEN`. When building dashboards and alerts, account for these states rather than assuming the circuit breaker only has three standard states.

## 2. Registering Listeners with Spring Cloud CircuitBreaker Customizer

When using Spring Cloud CircuitBreaker's Resilience4j starter, you can use `Customizer<Resilience4JCircuitBreakerFactory>` to attach listeners to circuit breakers by ID. The factory invokes the customizer when creating the corresponding instance; listeners are registered on that instance's event publisher.

Example listening only to state transitions of the `inventory` circuit breaker:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CircuitBreakerEventConfiguration {
    private static final Logger log =
        LoggerFactory.getLogger(CircuitBreakerEventConfiguration.class);

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryStateListener() {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(event -> log.warn(
                    "Circuit breaker {} transitioned state: {}",
                    event.getCircuitBreakerName(),
                    event.getStateTransition()
                )),
            "inventory"
        );
    }
}
```

In this example, the listener is attached only to the circuit breaker with ID `inventory`. When its state changes, the log records the circuit breaker name and transition. You can apply the same approach to a list of IDs or create separate customizers per dependency group.

If the application creates circuit breakers with other IDs, such as `payment` or `shipping`, the customizer registered for `inventory` does not automatically apply to those IDs. Use the exact identifiers passed into `CircuitBreakerFactory.create(...)` and keep them aligned with Resilience4j configuration.

## 3. Listening to Multiple Event Types on One Instance

A single configuration can register multiple event consumers on the same event publisher. For example:

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryEventListeners() {
    return factory -> factory.addCircuitBreakerCustomizer(
        circuitBreaker -> circuitBreaker.getEventPublisher()
            .onStateTransition(event -> log.warn(
                "{} state transition: {}",
                event.getCircuitBreakerName(),
                event.getStateTransition()
            ))
            .onCallNotPermitted(event -> log.info(
                "{} rejected call because circuit breaker did not grant permission",
                event.getCircuitBreakerName()
            ))
            .onError(event -> log.debug(
                "{} recorded call error: {}",
                event.getCircuitBreakerName(),
                event.getThrowable().toString()
            )),
        "inventory"
    );
}
```

This snippet illustrates combining listeners for state transitions, rejections, and execution errors. In deployment, enable only the required log levels. Never log full request bodies, tokens, personal information, or sensitive data in event logs.

Note that `onError` and `onCallNotPermitted` describe two different situations. `onError` reflects an execution that started and ended with a recorded error; `onCallNotPermitted` reflects the circuit breaker rejecting the call before the supplier ran. Merging both events into a single "downstream error" category on a dashboard can mislead operations into thinking the target service received additional requests and failed them.

## 4. Listening for Entries Added to CircuitBreakerRegistry

When an application uses Resilience4j's `CircuitBreakerRegistry` directly, the registry has its own event publisher. You can listen for when a new circuit breaker is added and attach listeners to that instance:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class Resilience4jRegistryConfiguration {

    @Bean
    CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();

        registry.getEventPublisher().onEntryAdded(event -> {
            CircuitBreaker circuitBreaker = event.getAddedEntry();
            circuitBreaker.getEventPublisher().onStateTransition(stateEvent ->
                System.out.printf(
                    "Circuit breaker %s transitioned state: %s%n",
                    stateEvent.getCircuitBreakerName(),
                    stateEvent.getStateTransition()
                )
            );
        });

        return registry;
    }
}
```

The registry listener is registered once when the registry bean is created. Each time the registry adds a new entry, the callback receives the newly added instance and attaches the state transition listener to it. Circuit breakers that already existed before `onEntryAdded` was registered do not replay add events; if the registry was initialized earlier, attach listeners to existing entries using the appropriate registry query API.

The example above illustrates working directly with the registry. In a Spring Cloud CircuitBreaker application, the factory may manage creating and caching circuit breakers itself. Do not create an isolated registry and assume breakers created by the factory will automatically appear in it. Choose the instance management mechanism the application actually uses.

## 5. Why Do Listeners Get Registered Repeatedly?

A common mistake is calling `getEventPublisher().onStateTransition(...)` inside a business method or on every request. An example to avoid:

```java
public Stock getStock(String sku) {
    var circuitBreaker = circuitBreakerFactory.create("inventory");

    circuitBreaker.getEventPublisher().onStateTransition(event ->
        log.warn("Inventory state: {}", event.getStateTransition())
    );

    return circuitBreaker.run(
        () -> inventoryClient.getStock(sku),
        error -> Stock.unavailable(sku)
    );
}
```

Each call to `getStock` adds another event consumer. Because a circuit breaker instance is long-lived and reused, old listeners continue receiving events. After 100 requests, a single state transition can generate 100 identical log lines. If the listener also sends alerts or writes records, one event can trigger numerous duplicate actions.

Common causes:

- Registering listeners inside controllers, service methods, or request filters.
- Creating configuration beans multiple times due to multiple application contexts or duplicate configuration imports.
- Attaching listeners via both a registry event consumer and a factory customizer for the same circuit breaker unintentionally.
- A component re-registering listeners upon re-initialization without lifecycle control.
- Registering listeners inside a loop every time an instance is fetched from the registry.

## 6. Placing Listeners in the Right Lifecycle

For Spring Cloud CircuitBreaker, the appropriate choice is usually a Spring-managed `Customizer` bean. For a direct Resilience4j registry, the appropriate choice is usually a registry event consumer registered when creating the registry or a listener attached right when creating the instance.

| Registration Location | When Appropriate | What to Avoid |
|---|---|---|
| `Customizer<Resilience4JCircuitBreakerFactory>` bean | Application uses the Spring Cloud CircuitBreaker factory. | Declaring multiple customizers attaching the same listener to the same ID. |
| `CircuitBreakerRegistry` event publisher | Application manages Resilience4j instances directly. | Creating a separate registry that does not contain the instances used by the application. |
| Instance factory function or registry-managing component | Application explicitly controls circuit breaker lifecycle. | Re-registering on every business call. |
| Controller/service request method | Never appropriate for registering listeners. | Attaching consumers on the request-handling path. |

A standard Spring configuration bean has singleton scope. Placing listener registration inside a configuration bean ensures listeners are wired to the application lifecycle rather than the request lifecycle. If an application has multiple application contexts, understand which context creates the factory and avoid loading the same configuration multiple times into the same factory.

## 7. Ensuring Idempotent Registration for Dynamic Instances

In systems that create circuit breakers dynamically per tenant, endpoint, or new service, you may need a guard so the same instance does not receive duplicate listeners. A listener registrar can track already registered IDs:

```java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class CircuitBreakerListenerRegistrar {
    private final Set<String> registeredIds = ConcurrentHashMap.newKeySet();

    public void registerOnce(
            String id,
            io.github.resilience4j.circuitbreaker.CircuitBreaker circuitBreaker) {
        if (!registeredIds.add(id)) {
            return;
        }

        circuitBreaker.getEventPublisher().onStateTransition(event ->
            logStateTransition(id, event.getStateTransition().toString())
        );
    }

    private void logStateTransition(String id, String transition) {
        // Forward to the configured logger or event sink.
    }
}
```

`ConcurrentHashMap.newKeySet()` keeps ID insertion thread-safe when multiple threads request registration concurrently. Only the thread that successfully adds the ID attaches the listener. This example fits when ID lifecycles do not change and each circuit breaker has one listener by policy.

If the registry allows replacing or removing and recreating entries with the same ID, storing only the ID is insufficient. In that case, track instance identity or entry lifecycle, handle `onEntryRemoved`/`onEntryAdded` accordingly, and clear old registration state when an instance is replaced. Do not retain an unbounded set of IDs if the system generates millions of dynamic IDs; enforce an eviction policy or lifecycle limit.

For typical applications with a fixed set of circuit breakers, building a custom registrar is unnecessary. A centralized customizer created once is usually simpler.

## 8. Listeners Should Not Slow Down Protected Calls

Event consumers are typically invoked on Resilience4j's event-emitting path. Therefore, listeners should be brief, non-blocking, and must never call back into the protected dependency itself. A listener performing HTTP requests, database queries, or waiting synchronously on a queue can add latency to requests or alter the very behavior the circuit breaker is measuring.

Best practices:

- Extract only needed fields from the event and write concise logs.
- Never call back into a failing dependency from a listener.
- Avoid slow I/O or long lock waits inside callbacks.
- If notifications must be sent to another system, push a small event onto a bounded queue or use an appropriate metrics/monitoring mechanism.
- Add error handling for the event sink so logging or alerting failures do not disrupt the main execution path.
- Never create metric tags from high-cardinality data such as request IDs, user IDs, or URLs with dynamic parameters.

State transition events are not the place to handle request fallbacks. Fallbacks belong on the call execution path; listeners should serve only for non-blocking observation and operational reaction.

## 9. Using Events to Observe State Without Replacing Metrics

Event listeners are well suited for logs, audits, and state transition notifications. Metrics are well suited for time-based aggregation, dashboards, and rate-based alerts. Do not use event listeners as the sole mechanism to compute success counts or failure rates, because Resilience4j and Micrometer already provide dedicated metrics for that purpose.

One way to divide responsibilities:

| Need | Suitable Mechanism |
|---|---|
| Recording when `CLOSED` transitions to `OPEN` | `onStateTransition` and structured logging. |
| Counting successful/failed calls | Resilience4j Micrometer metrics. |
| Tracking rejected calls | Not-permitted metric and/or `onCallNotPermitted` event. |
| Alerting on prolonged open circuits | State metrics, duration, and alert rules. |
| Investigating a specific request | Distributed traces and logs with correlation IDs. |
| Notifying operations on state changes | Event listener sending async messages through a bounded event sink. |

When a circuit breaker repeatedly cycles `OPEN`, `HALF_OPEN`, and `OPEN`, state transition logs pinpoint when oscillation occurred. Metrics for failure rate, slow-call rate, and probe calls help identify the cause. Combining both is far more effective than firing an alert on every exception.

## 10. Avoiding Duplicate Notifications Across Multiple Replicas

Listeners are registered once per process, yet production systems typically run multiple replicas. If there are 5 replicas and each has its own circuit breaker instance, the same degrading dependency can cause all 5 instances to emit `CLOSED_TO_OPEN` events. This is not duplicate listener registration within a process; it is five local circuit breakers observing the same dependency.

Make this distinction:

- **Duplicate listener in one process:** one circuit breaker emits one event, but multiple identical callbacks execute due to repeated registration.
- **Events from multiple replicas:** each process has its own circuit breaker and listener, so the same change produces multiple logs/events.

Do not suppress valid events from replicas merely because their content looks similar. If the system needs a consolidated alert, group by service, circuit breaker ID, and state in the alerting system; apply a deduplication key and an appropriate window at the notification layer. Logs should still preserve instance/replica metadata to investigate failure distribution.

Resilience4j circuit breakers normally keep state local to each process. Local listeners do not create a cluster-wide shared breaker state. If system-wide state coordination is required, that is a separate design with different consistency and availability requirements.

## 11. Testing That a Listener Is Registered Only Once

Test both conditions: the listener receives events when state changes, and a single state transition triggers the listener only once.

With Resilience4j, you can create a test circuit breaker, register the listener once, and drive the instance to open via appropriate configuration and call outcomes. A simpler unit test approach uses `AtomicInteger` to count callbacks:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.junit.jupiter.api.Test;

class CircuitBreakerEventListenerTest {

    @Test
    void invokesOneListenerForOneStateTransition() {
        CircuitBreaker circuitBreaker = CircuitBreaker.ofDefaults("inventory");
        AtomicInteger transitionCount = new AtomicInteger();

        circuitBreaker.getEventPublisher().onStateTransition(event ->
            transitionCount.incrementAndGet()
        );

        circuitBreaker.transitionToOpenState();

        assertEquals(1, transitionCount.get());
    }
}
```

The test above demonstrates registering a listener once and counting a single state transition event. When testing real integration behavior, also verify that the `Customizer` bean is loaded only once in the application context and that multiple requests do not increase the number of registered callbacks.

Useful test cases:

1. Transition `CLOSED` to `OPEN`: listener receives one event with the right breaker ID.
2. Transition `OPEN` to `HALF_OPEN`: listener receives the subsequent event.
3. Send multiple requests in the same state: no extra state transitions are emitted and callback count does not multiply.
4. Create multiple breaker IDs: listeners are attached only to the configured IDs.
5. Initialize a registry with new entries: the registry listener attaches consumers to each new entry exactly once.
6. Run multiple replicas: distinguish events from different instances from duplicate callbacks registered within one process.

## 12. Error Handling and Listener Lifecycle Changes

The event publisher retains registered consumers on the instance. Therefore, a listener should have a lifecycle matching the circuit breaker. If an instance is removed or replaced, check the Resilience4j version's API to handle listeners and related references. Avoid letting a registrar hold references to removed instances indefinitely.

If a listener sends messages to another system, handle cases where the notification target is unavailable. You can use a bounded queue, separate retries for the event sink, or accept dropping non-critical notifications. Never let notification failures alter business call outcomes or exhaust the event-emitting thread's resources.

For critical alerts, do not rely solely on an in-memory event callback. Combine periodically scraped metrics and alert rules so state can still be detected after a process restart or temporary event sink failure. Event listeners add timing and context; metrics provide a more durable aggregated view.

## 13. Implementation Workflow in a Spring Application

You can implement this in the following sequence:

1. Identify the circuit breaker IDs to monitor, such as `inventory` and `payment`.
2. If using Spring Cloud CircuitBreaker, create a `Customizer<Resilience4JCircuitBreakerFactory>` bean to attach listeners by ID.
3. If using a Resilience4j registry directly, register a registry event consumer once when creating the registry and attach listeners for new entries.
4. Listen only to the events actually needed; prefer state transitions for status notifications and metrics for quantitative data.
5. Ensure callbacks are brief, non-blocking, and never call back into degrading dependencies.
6. Test callback counts, IDs, state transitions, and behavior under multiple requests.
7. When running multiple replicas, tag logs/traces with instance metadata and handle deduplication in the alerting system if needed.

## 14. Checklist for Avoiding Duplicate Listeners

- [ ] Listeners are registered in configuration or during registry creation, not inside request methods.
- [ ] Each circuit breaker ID has only the listeners required by design.
- [ ] The same listener is not attached via both a factory customizer and a registry event consumer for one instance.
- [ ] Configuration beans are not unintentionally imported or instantiated multiple times.
- [ ] If creating dynamic IDs, registration and instance lifecycle are explicitly controlled.
- [ ] Listeners are non-blocking, do not call back into dependencies, and do not perform slow I/O.
- [ ] Event logs distinguish execution errors from rejected calls.
- [ ] Metrics continue to be used for dashboards and quantitative alerts.
- [ ] Logs include breaker ID and replica metadata without containing sensitive data.
- [ ] Tests prove that a single state transition triggers only the expected number of callbacks.

Listening to state transition events enables Spring Cloud CircuitBreaker applications to explain when circuits open, start probing, and recover. Bind listeners to the factory or registry lifecycle, register once per instance, keep callbacks concise, and use metrics for aggregated counts. By distinguishing execution errors, rejected calls, and events across multiple replicas, operations teams can monitor circuit breakers accurately without generating duplicate logs or tasks.
