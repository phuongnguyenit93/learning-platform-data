# Post-Creation Circuit Breaker Customizers and Event Listeners

Spring Cloud CircuitBreaker provides a factory to create circuit breakers by ID. When using Resilience4j, the application can also customize an instance after the factory creates it and register event listeners to know when calls fail, are rejected, or when the circuit state changes.

Both tasks are typically accomplished with a Spring bean of type `Customizer`. Threshold configuration determines how the circuit breaker behaves; post-creation customizers add behavior to the created instance, such as attaching listeners to log or update metrics. As a result, business code does not need to manage listener registration every time it calls a service.

## Circuit breaker creation lifecycle

A call goes through the factory with a stable ID, such as `inventory-read`. The factory selects the corresponding configuration, creates or retrieves the circuit breaker instance, and applies registered customizers. The factory then returns the Spring Cloud CircuitBreaker object for application code to execute calls.

~~~mermaid
flowchart TD
    A[Application calls factory with ID] --> B[Factory selects configuration]
    B --> C[Create Resilience4j instance]
    C --> D[Run post-creation customizer]
    D --> E[Register event listener]
    E --> F[Return circuit breaker to application]
    F --> G[Execute protected calls]
    G --> H[Emit events on outcomes or state transitions]
    H --> I[Listener logs or updates metrics]
~~~

In the Spring Cloud CircuitBreaker integration with Resilience4j, the commonly used synchronous factory is `Resilience4JCircuitBreakerFactory`. You can declare a `Customizer<Resilience4JCircuitBreakerFactory>` bean to customize the factory.

The key point is that the customizer is registered at the application configuration level. The factory applies the callback when creating the matching circuit breaker; the application does not need to re-attach listeners on every request. With a specific ID, the callback only applies to the designated instances.

## Distinguishing pre-creation configuration and post-creation customizer

Spring Cloud CircuitBreaker provides several extension points. Choose the right point for your purpose:

| Mechanism | Timing and target | Purpose |
|---|---|---|
| `configureDefault(...)` | Default configuration for IDs when the factory builds configuration | Sets common policies such as sliding window, failure rate, and timeout. |
| `configure(..., "id")` | Configuration for one or more specified IDs | Overrides or adds a dedicated policy for a specific call flow. |
| `addCircuitBreakerCustomizer(..., "id")` | Callback on the Resilience4j instance after the instance is created | Attaches event listeners or adds behavior requiring access to the created instance. |

Pre-creation configuration determines the operational parameters of the circuit breaker. The post-creation customizer receives the Resilience4j instance to register listeners. Do not use listeners to replace configuring failure rate, slow call rate, sliding window, or timeout.

## Setting configuration for an ID

The example below sets a dedicated configuration for inventory read calls. The ID in the factory and the instance name in configuration must be consistent.

~~~java
import java.time.Duration;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

@Configuration
public class InventoryCircuitBreakerConfiguration {

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory>
            inventoryCircuitBreakerConfiguration() {

        CircuitBreakerConfig circuitBreakerConfig =
                CircuitBreakerConfig.custom()
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .failureRateThreshold(50)
                        .slowCallDurationThreshold(Duration.ofMillis(800))
                        .slowCallRateThreshold(60)
                        .build();

        TimeLimiterConfig timeLimiterConfig =
                TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(2))
                        .build();

        return factory -> factory.configure(
                builder -> builder
                        .circuitBreakerConfig(circuitBreakerConfig)
                        .timeLimiterConfig(timeLimiterConfig)
                        .build(),
                "inventory-read"
        );
    }
}
~~~

This is an example of Java-based configuration. If the project already manages parameters in `application.yml`, choose one clear configuration source and avoid accidentally creating two conflicting sets of values. Java configuration can be appropriate when configuration must be built conditionally or when sharing configuration objects.

You can set a default configuration for all IDs with `configureDefault`:

~~~java
@Bean
public Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfiguration() {
    return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                    .circuitBreakerConfig(CircuitBreakerConfig.ofDefaults())
                    .timeLimiterConfig(
                            TimeLimiterConfig.custom()
                                    .timeoutDuration(Duration.ofSeconds(3))
                                    .build()
                    )
                    .build()
    );
}
~~~

When a dedicated configuration exists for an ID, check the ordering and how customizers are applied according to the Spring Cloud CircuitBreaker version in use. Do not rely implicitly on bean declaration order if multiple customizers modify the same configuration.

## Registering listeners after instance creation

To attach listeners to a Resilience4j instance, use `addCircuitBreakerCustomizer`. The following example registers listeners for ID `inventory-read`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerEventConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(CircuitBreakerEventConfiguration.class);

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory>
            inventoryCircuitBreakerEvents() {

        return factory -> factory.addCircuitBreakerCustomizer(
                circuitBreaker -> circuitBreaker.getEventPublisher()
                        .onStateTransition(event ->
                                log.info(
                                        "Circuit breaker {} changed state: {}",
                                        event.getCircuitBreakerName(),
                                        event.getStateTransition()
                                )
                        )
                        .onError(event ->
                                log.warn(
                                        "Circuit breaker {} recorded an error: {}",
                                        event.getCircuitBreakerName(),
                                        event.getThrowable().toString()
                                )
                        )
                        .onCallNotPermitted(event ->
                                log.warn(
                                        "Circuit breaker {} rejected a call",
                                        event.getCircuitBreakerName()
                                )
                        )
                        .onFailureRateExceeded(event ->
                                log.warn(
                                        "Circuit breaker {} exceeded failure rate",
                                        event.getCircuitBreakerName()
                                )
                        )
                        .onSlowCallRateExceeded(event ->
                                log.warn(
                                        "Circuit breaker {} exceeded slow call rate",
                                        event.getCircuitBreakerName()
                                )
                        ),
                "inventory-read"
        );
    }
}
~~~

The callback receives the Resilience4j instance after the factory creates it. `getEventPublisher()` provides listener registration points. The trailing ID parameter scopes the customizer to the `inventory-read` instance; other circuit breakers do not automatically receive this listener.

The listener methods in the example reflect different event types:

| Listener | When is it invoked? | Can be used to |
|---|---|---|
| `onStateTransition` | When the circuit transitions between CLOSED, OPEN, and HALF_OPEN. | Track state and trigger alerts when the circuit opens. |
| `onError` | When a call is recorded as a failure. | Record dependency errors or classify root causes. |
| `onCallNotPermitted` | When a call is rejected because the circuit does not permit execution. | Count fail-fast rejections and track fallback usage. |
| `onFailureRateExceeded` | When the failure rate exceeds the threshold. | Identify that the circuit opened due to failures. |
| `onSlowCallRateExceeded` | When the slow call rate exceeds the threshold. | Detect dependency latency degradation even when responses still return. |

The `onError` event describes a single failed call outcome. The `onFailureRateExceeded` event describes that the failure rate in the window has exceeded the threshold. The two events mean different things: a single error does not necessarily open the circuit.

Similarly, a slow call can complete successfully. The `onSlowCallRateExceeded` listener only signals when the slow call rate crosses the threshold, whereas `onStateTransition` indicates whether the actual state of the circuit changed.

## Use listeners for observability, not business flow control

Event listeners are suitable for recording activity, updating metric counters, or emitting signals to observability systems. Do not put critical business logic inside a listener, because listeners are invoked as part of event publication and are not the primary request control point.

For example, you can increment a counter when the circuit breaker rejects a call:

~~~java
.onCallNotPermitted(event ->
        rejectedCallsCounter.increment()
)
~~~

In this example, `rejectedCallsCounter` is a metric object already initialized and tagged appropriately in the application. Use tags with bounded cardinality, such as the circuit breaker ID and event type. Do not attach user IDs, order IDs, or parameterized URLs to metric tags because cardinality can grow rapidly.

Some principles when implementing listeners:

- Keep callbacks short and avoid blocking the thread publishing the event.
- Avoid calling the protected dependent service back from inside a listener.
- Do not perform database queries or synchronous HTTP calls inside callbacks.
- Do not allow logging errors or metrics errors to disrupt the main processing flow.
- Use structured logs and stable metric tags to aggregate by ID.
- Avoid logging every successful event in high-traffic systems; prefer aggregated metrics.

If events must be sent to an external system, offload the work to an asynchronous mechanism with a bounded queue and a defined policy when the queue is full. Do not turn an event listener into a new network dependency on the request path.

## Monitoring circuit breaker state and outcomes

Event listeners can be combined with Spring Boot Actuator, Micrometer, and log/metric collection systems. Events tell you what just happened; aggregated metrics help observe trends over time.

At a minimum, track:

- Current state and state transition counts for each ID.
- Counts of successful, failed, slow, and rejected calls.
- Failure rate, slow call rate, and latency.
- Number of times fallback is invoked.
- Time spent by the circuit breaker in the OPEN state.
- Frequency of re-opening after HALF_OPEN probes.

When the circuit transitions to OPEN, distinguish whether the cause was failure rate or slow call rate. If due to errors, check exceptions, connection errors, or business errors. If due to slow calls, examine network latency, database queries, dependent service resources, and queues. When a circuit repeatedly flips between OPEN and CLOSED, re-evaluate the sliding window, minimum sample count, thresholds, and wait duration.

Event listeners do not replace health checks or metrics. Listeners reflect emitted events; health indicators provide status signals for health checks; metrics support trend analysis and alerting. Combining these sources helps operations teams understand both current state and transition history.

## Scope and lifecycle of listeners

Post-creation customizers are registered on the factory and applied when the factory creates a matching instance. Therefore, do not place listener registration calls inside every controller or service method invoked per request. Doing so can cause repeated registrations, obscure lifecycle management, and create operational noise.

Place customizers in a Spring configuration class, scope them to specific IDs, and let the factory manage instance lifecycles. If multiple customizers apply to the same ID, organize them clearly to avoid registering the same action twice or logging duplicates.

In applications running multiple replicas, each process typically has its own circuit breaker instance and event publisher. A listener on one replica does not automatically receive events from another replica. When system-wide visibility is needed, ship logs or metrics from all replicas to a centralized platform and preserve consistent ID conventions for aggregation.

When using a reactive circuit breaker, the specific factory and configuration API depend on the backend and Spring Cloud CircuitBreaker version. Use the corresponding reactive factory for reactive calls and check the extension points provided by that version; do not wrap a reactive call in a synchronous circuit breaker or call `block()` just to reuse a listener.

## Testing customizers and event listeners

Integration testing can be performed by creating a stub dependency that can return success, throw errors, or respond slowly. Use the configured ID and observe whether listeners receive the expected events.

| Scenario | Event or outcome to observe |
|---|---|
| Call completes successfully | Success outcome recorded; state remains CLOSED unless open conditions were already met. |
| Call throws an error | `onError` listener receives the error event. |
| Failure rate exceeds threshold | `onFailureRateExceeded` listener is invoked and circuit transitions to OPEN. |
| Slow call rate exceeds threshold | `onSlowCallRateExceeded` listener is invoked and circuit transitions to OPEN. |
| Call while circuit is OPEN | `onCallNotPermitted` listener receives the rejection event. |
| OPEN wait duration expires and recovery is attempted | Observe transition to HALF_OPEN, then CLOSED or OPEN depending on probe results. |
| Calling another ID | Confirm listeners scoped to `inventory-read` are not mistakenly applied to other IDs. |

In addition to checking events, confirm that listeners do not noticeably increase request latency, do not create circular dependency calls, and do not generate excessive log volume. If metrics are used, verify numbers increment accurately per event and tags contain no per-request identifying data.

## Implementation checklist

1. Define a stable ID for each call flow that needs protection.
2. Configure failure rate, slow call rate, sliding window, and timeout at the appropriate configuration point.
3. Use `addCircuitBreakerCustomizer` to attach listeners after the factory creates the Resilience4j instance.
4. Register listeners only for IDs that need monitoring and avoid duplicate registrations.
5. Keep callbacks short, non-blocking, and free of synchronous network calls.
6. Combine events with metrics, logs, and health indicators to track trends.
7. Test fast failures, slow calls, fail-fast rejections, and HALF_OPEN recovery separately.

Post-creation customizers add behavior to the right circuit breaker instance; event listeners provide signals on call outcomes and state changes. When placed in configuration classes, scoped to stable IDs, and kept lightweight, Spring Cloud applications can observe Resilience4j clearly without complicating business code.
