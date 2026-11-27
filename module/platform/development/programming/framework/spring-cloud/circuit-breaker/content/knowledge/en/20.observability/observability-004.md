# Observing State, Transition Counts, and OPEN Duration

## Lesson Objectives

A circuit breaker protects a system effectively only when operations teams know what state it is in, how many times it transitions, and how long each opening lasts. A dashboard showing only the current error rate cannot answer questions such as: is the breaker currently OPEN, has the dependency recovered yet, is the breaker repeatedly closing and reopening, and for how long are requests being rejected.

Spring Cloud CircuitBreaker combined with Resilience4j provides events and metrics to track this information. You need to understand the limits of each data type: a state metric is a point-in-time snapshot, events capture transition history, and OPEN duration generally must be calculated from transition timestamps.

After this lesson, you will be able to:

- Track the CLOSED, OPEN, and HALF_OPEN states of each breaker.
- Count and analyze state transitions, including repeated opening and closing behavior.
- Distinguish configured `waitDurationInOpenState` from observed OPEN duration.
- Read Resilience4j metrics via Spring Boot Actuator and Micrometer.
- Record timestamps when entering and leaving OPEN, and compute duration for each cycle.
- Design dashboards and alerts around state, rejection count, and open duration.
- Analyze per-pod data without confusing local state for system-wide state.

## 1. What Needs to Be Observed?

A circuit breaker has three primary operational states:

| State | Operational Meaning | What to Observe |
| --- | --- | --- |
| CLOSED | Allows calls through and records outcomes. | Failure rate, slow call rate, latency, and call volume. |
| OPEN | Fast-rejects new calls during the recovery wait period. | Opening timestamp, time spent in OPEN, rejected call count. |
| HALF_OPEN | Allows a limited number of probe calls to evaluate the dependency. | Probe call count, probe outcomes, and resulting next state. |

Resilience4j also provides special states such as FORCED_OPEN, DISABLED, and METRICS_ONLY. When building dashboards, know which library version and states are in use; do not lump all non-CLOSED states under a single error label if they have different operational meanings.

A useful observability suite typically includes these data groups:

- Current state of each breaker.
- Counts of CLOSED → OPEN, OPEN → HALF_OPEN, HALF_OPEN → CLOSED, and HALF_OPEN → OPEN transitions.
- Duration of each OPEN cycle and age of an ongoing OPEN state.
- Counts of successful, failed, slow, and not-permitted calls.
- Failure rate and slow call rate relative to configured thresholds.
- Dependency latency and fallback rate.

These data groups complement one another. Current state tells you where the breaker stands; events show which states it has traversed; call metrics show the impact on requests.

## 2. Distinguishing Current State from Transition History

A state metric is typically a gauge. It represents the state at the moment the metrics system scrapes data. With Micrometer, Resilience4j exports `resilience4j.circuitbreaker.state` tagged with the breaker name and state, such as `name=inventory`, `state=open`.

In Prometheus format, each state may be represented as a separate time series; a value of 1 indicates the state is active and 0 indicates it is inactive. Read the `state` tag together with the gauge value—do not infer state from an unlabeled number.

State metrics are suited to answer:

- Is the `inventory` breaker OPEN right now?
- Are any pods holding the breaker in HALF_OPEN?
- Did the current state change between scrapes?

Gauge metrics do not retain full history. If a breaker opens and closes between two scrapes, a dashboard sampling only state can miss that transition. To know exact transition counts and timestamps, collect events.

State transition events are emitted whenever a breaker changes state. For example:

    CLOSED -> OPEN
    OPEN -> HALF_OPEN
    HALF_OPEN -> CLOSED
    HALF_OPEN -> OPEN

Events can be written to logs, stored in a recent buffer, or converted into counter metrics. This allows operations teams to detect breaker flapping: opening, probing recovery, closing, and opening again repeatedly over a short span.

## 3. Commonly Used CircuitBreaker Metrics

When integrating Resilience4j with Micrometer, common metrics include:

| Metric | Data Type | Meaning |
| --- | --- | --- |
| `resilience4j.circuitbreaker.state` | Gauge | Current state by breaker and state tag. |
| `resilience4j.circuitbreaker.calls` | Timer | Duration and count of calls by outcome, such as successful, failed, or ignored. |
| `resilience4j.circuitbreaker.failure.rate` | Gauge | Current failure rate in the sliding window. |
| `resilience4j.circuitbreaker.slow.call.rate` | Gauge | Current slow call rate in the sliding window. |
| `resilience4j.circuitbreaker.buffered.calls` | Gauge | Number of successful/failed outcomes currently stored in the statistics window. |
| `resilience4j.circuitbreaker.not.permitted.calls` | Counter | Total calls rejected because the breaker denied permission. |
| `resilience4j.circuitbreaker.max.buffered.calls` | Gauge | Maximum configured size of the outcome storage window. |

Exact metric names and tags may vary by Resilience4j version, Micrometer version, and exporter format. Query the application's actual metric list before writing dashboards or alert rules.

The `calls` metric reports outcomes of calls that entered the breaker. `not.permitted.calls` reports fast-rejected calls; these calls never execute the dependency operation, so they must not be interpreted as HTTP requests sent to the server.

Failure rate and slow call rate reflect sliding window data. They are not the overall error rate since application startup. As the window slides, older outcomes drop out of the calculation and rates can change even without a new state transition event.

## 4. Enabling Actuator and Micrometer

In a Spring Boot application, add Actuator and an appropriate Micrometer registry. Maven example:

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>

Resilience4j provides a Micrometer module to bind instance metrics. In many Spring Boot + Resilience4j integrations, binders and endpoints are auto-configured when matching dependencies are present. For applications using a plain Spring Cloud CircuitBreaker factory, verify the dependencies and auto-configuration in use; do not assume every Resilience4j Spring Boot endpoint appears just because the Spring Cloud CircuitBreaker starter is included.

You can expose required management endpoints:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,metrics,prometheus,circuitbreakers,circuitbreakerevents

Commonly used endpoints:

- `/actuator/metrics`: lists registered metrics.
- `/actuator/metrics/resilience4j.circuitbreaker.state`: reads the state metric if the binder registered it.
- `/actuator/metrics/resilience4j.circuitbreaker.calls`: reads call duration and count data.
- `/actuator/prometheus`: exports Prometheus metrics when the corresponding registry is configured.
- `/actuator/circuitbreakers` and `/actuator/circuitbreakerevents`: may be available in Resilience4j Spring Boot/Actuator integrations to view instances and recent events.

Available endpoints depend on the integration version and modules. Check the active endpoint list instead of copying configuration from another version. Protect management endpoints with authentication, network policies, or a separate management port; do not expose internal state and exception details publicly.

## 5. Counting State Transitions

You can register a listener with each breaker's `EventPublisher`. In Spring Cloud CircuitBreaker using Resilience4j, a factory customizer lets you attach a listener when the breaker is created:

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryTransitionListener(
            CircuitBreakerTransitionObserver observer) {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(observer::record),
            "inventory"
        );
    }

This example attaches a listener only to the breaker named `inventory`. If the application creates breakers with other IDs, register each name or register across all instances via the managed registry.

An observer can increment a counter per state pair:

    public void record(CircuitBreakerOnStateTransitionEvent event) {
        StateTransition transition = event.getStateTransition();

        Counter.builder("app.circuitbreaker.state.transitions")
            .tag("breaker", event.getCircuitBreakerName())
            .tag("from", transition.getFromState().name())
            .tag("to", transition.getToState().name())
            .register(meterRegistry)
            .increment();
    }

This custom metric allows querying counts of `CLOSED → OPEN` or `HALF_OPEN → OPEN` transitions. The `from` and `to` tags have a finite set of values, making them suitable for metrics. Never put exception messages, request IDs, SKUs, or full URLs into tags because they can produce very high cardinality.

Listeners run on the event emission thread. Keep callbacks brief: increment a counter or write a small record. Do not make HTTP calls, perform synchronous database writes, or block on an unbounded queue inside a callback. If heavy processing is needed, push a minimal record into a bounded queue and measure dropped events.

## 6. Measuring OPEN Duration

Resilience4j provides current state metrics and transition events, but how long a breaker stayed OPEN in a cycle typically needs to be derived from two timestamps:

1. When the breaker transitioned to OPEN.
2. When the breaker left OPEN, usually transitioning to HALF_OPEN.

Observed duration:

    openDuration = timeLeavingOpen - timeEnteringOpen

This is the actual time the breaker spent in OPEN within the process, which does not necessarily equal `waitDurationInOpenState`.

For example, configuring `waitDurationInOpenState: 10s` sets the wait time before the breaker may transition to HALF_OPEN. If `automaticTransitionFromOpenToHalfOpenEnabled` is false, the breaker typically transitions only when the next call arrives after the wait time has elapsed. If no new requests arrive, the breaker can remain OPEN longer than 10 seconds. When automatic transition is enabled, a scheduler can move the breaker to HALF_OPEN after the wait duration without waiting for an incoming request.

Therefore, dashboards should distinguish:

- **Configured wait:** the configured wait duration before recovery probing is allowed.
- **Observed OPEN duration:** time from the OPEN-entry event to the OPEN-exit event.
- **Current OPEN age:** elapsed time since entering OPEN if the breaker has not yet left that state.

If a breaker is still OPEN when the application restarts, in-memory history from the old process may be lost. For investigation across restarts, write events to logs or a centralized storage system.

## 7. Example: Recording OPEN Duration with Micrometer

The illustrative snippet below stores the OPEN-entry timestamp in memory and records a Timer when the breaker leaves OPEN:

    import io.github.resilience4j.circuitbreaker.event.CircuitBreakerOnStateTransitionEvent;
    import io.github.resilience4j.circuitbreaker.CircuitBreaker;
    import io.github.resilience4j.circuitbreaker.CircuitBreaker.State;
    import io.github.resilience4j.circuitbreaker.CircuitBreaker.StateTransition;
    import io.micrometer.core.instrument.MeterRegistry;
    import io.micrometer.core.instrument.Timer;
    import java.time.Duration;
    import java.time.Instant;
    import java.util.concurrent.ConcurrentHashMap;
    import java.util.concurrent.ConcurrentMap;

    public class CircuitBreakerTransitionObserver {

        private final MeterRegistry meterRegistry;
        private final ConcurrentMap<String, Instant> openedAt =
            new ConcurrentHashMap<>();

        public CircuitBreakerTransitionObserver(MeterRegistry meterRegistry) {
            this.meterRegistry = meterRegistry;
        }

        public void record(CircuitBreakerOnStateTransitionEvent event) {
            StateTransition transition = event.getStateTransition();
            String name = event.getCircuitBreakerName();
            Instant observedAt = Instant.now();

            if (transition.getToState() == State.OPEN) {
                openedAt.put(name, observedAt);
                return;
            }

            if (transition.getFromState() == State.OPEN) {
                Instant start = openedAt.remove(name);
                if (start != null) {
                    Duration duration = Duration.between(start, observedAt);

                    Timer.builder("app.circuitbreaker.open.duration")
                        .description("Observed time spent in OPEN state")
                        .tag("breaker", name)
                        .register(meterRegistry)
                        .record(duration);
                }
            }
        }
    }

This example illustrates the calculation approach. Check the event packages and APIs for your project's Resilience4j version. `Instant.now()` captures when the observer receives the callback; if the event version provides a reliable creation timestamp, you can use it to reduce skew from delayed callback execution.

The `openedAt` map holds state only for the current process. If a breaker never leaves OPEN before the application stops, no Timer entry is recorded for that cycle. Thus, complement it with a `current OPEN age` gauge or log the OPEN-entry timestamp so dashboards still show the age of an ongoing state.

When a breaker is reset or moved into a special state, decide how to end or discard the active measurement cycle. Never allow a stale timestamp to be reused for a new OPEN cycle.

## 8. Tracking Re-Openings and Flapping

A breaker opening once during a dependency incident can be normal behavior. However, if the breaker repeatedly cycles:

    CLOSED -> OPEN -> HALF_OPEN -> CLOSED
                         |
                         +----> OPEN -> HALF_OPEN -> ...

then the dependency or configured thresholds may be oscillating around the boundary. This phenomenon is commonly called flapping.

Indicators that help detect it:

- Number of `CLOSED → OPEN` transitions within 5 or 15 minutes.
- Number of `HALF_OPEN → OPEN` transitions after recovery probes.
- Interval between consecutive openings.
- Proportion of calls rejected while the breaker is OPEN.
- Failure rate and slow call rate immediately prior to opening.
- Dependency latency before, during, and after an open cycle.

If a breaker repeatedly reopens, inspect dependency stability, timeouts, sliding window settings, `minimumNumberOfCalls`, `failureRateThreshold`, and `slowCallRateThreshold`. A window that is too small can overreact to a brief error burst; a window that is too large can react slowly when a service begins degrading.

Do not fix flapping by mechanically increasing `waitDuration`. Review state transition data and latency to determine whether the dependency genuinely has not recovered or whether thresholds are miscalibrated.

## 9. What Components Should a Dashboard Include?

A per-breaker dashboard can be organized into these sections:

| Section | Chart or Information | Operational Question |
| --- | --- | --- |
| Current state | State gauge by breaker and pod | Which breaker is OPEN or HALF_OPEN? |
| State transitions | Counter/rate by `from → to` pair | How many times did the breaker open, and is it flapping? |
| OPEN duration | Timer histogram and current OPEN age | How long does each open cycle last? Which breaker has been OPEN too long? |
| Call outcomes | Successful, failed, ignored, not permitted | To what extent are requests impacted? |
| Dependency quality | Failure rate, slow call rate, p95/p99 latency | Why did the breaker open? |
| Fallback | Fallback count and type | How often are users receiving degraded responses? |

Include filters by service, breaker name, environment, and pod. Avoid cramming every dimension onto a single chart; prioritize displaying trends and provide drill-down links to logs/traces when investigating a specific request.

With multiple pods, each pod's state gauge is local state. Dashboards should preserve the `instance`/`pod` tag so you know which pod is OPEN. To check whether at least one pod is OPEN, use an appropriate aggregation such as `max` over the OPEN state gauge. Do not sum state gauges as if they were transition counts.

## 10. Designing Actionable Alerts

Alerts should indicate what the operator needs to do. Reference rules include:

- **Prolonged OPEN breaker:** alert when a breaker stays OPEN longer than operationally acceptable.
- **Rising `CLOSED → OPEN` transition rate:** detect when a dependency starts becoming unstable.
- **Consecutive `HALF_OPEN` failures:** the dependency has not recovered after the wait period.
- **Sudden `not_permitted` spike:** requests are being fast-rejected in large numbers.
- **High failure rate or slow call rate:** early warning before or as the breaker opens.
- **Increasing OPEN duration across cycles:** dependency recovery time is worsening.

Choose thresholds based on SLOs and business impact. For instance, a breaker protecting an optional feature may only warrant alerting on prolonged OPEN; a breaker protecting payment or authentication steps may require higher priority.

Avoid triggering alerts for every brief OPEN transition. If the breaker works properly to block a transient error burst, continuous alerts create noise. Combine duration, affected request share, fallback usage, and reopen count to determine severity.

## 11. Analyzing Data Per Pod

Circuit breakers typically keep state and sliding windows in each JVM's memory. If `order-service` runs three pods, each pod has its own `inventory` breaker. One pod can be OPEN while the other two remain CLOSED.

This affects how dashboards must be read:

- An OPEN gauge on pod A does not prove the entire service is OPEN.
- A pod with a high error rate may be talking to a different dependency instance or running different configuration.
- Summing `not_permitted` across all pods gives total blocked calls, but retain the pod tag to locate where rejections originate.
- Event history on one pod does not automatically synchronize to other pods.

When system-wide aggregation is needed, keep `breaker` and `pod` labels in the raw data and choose the aggregation per question. For example, use `max` to check if any pod is OPEN; use `sum` for rejected call counters; use histogram aggregation to compute OPEN duration percentiles. Never directly sum percentiles or state gauges across pods.

Metric tags should maintain controlled cardinality. `breaker name`, `service`, and `pod` are typically useful operational dimensions; never add request IDs, user IDs, SKUs, or exception messages as tags.

## 12. Lab Exercise: Observing a Complete OPEN Cycle

Create `order-service` calling `inventory-service` using Spring Cloud CircuitBreaker and Resilience4j. Perform the following steps:

1. Enable Actuator and an appropriate Micrometer registry.
2. Confirm `state`, `calls`, `failure rate`, `slow call rate`, and `not-permitted` metrics appear.
3. Register a listener for state transition events on the `inventory` breaker.
4. Increase load and make `inventory-service` return errors or slow responses until the breaker transitions `CLOSED → OPEN`.
5. Record the OPEN-entry timestamp and verify the `state=open` gauge turns active.
6. Send more requests while OPEN; confirm `not-permitted` rises and the fallback executes.
7. Wait past `waitDurationInOpenState`; check `automaticTransitionFromOpenToHalfOpenEnabled` configuration and determine the exact time it transitions to `HALF_OPEN`.
8. Allow probe calls to succeed so the breaker transitions `HALF_OPEN → CLOSED`.
9. Compute OPEN duration from the two transition events and compare it with configured `waitDuration`.
10. Repeat with failing probe calls so the breaker transitions `HALF_OPEN → OPEN`.
11. Run two pods and observe each pod's independent state and event history.
12. Build a dashboard showing current state, transition rate, open duration, `not-permitted`, and failure/slow-call rates.

Upon completion, you should be able to distinguish state gauges from historical events, understand why observed OPEN time can exceed `waitDurationInOpenState`, and calculate duration from transition events. Use metrics for trends, events for progression, logs/traces for request context, and alerts grounded in actual impact.

## References

- Resilience4j — Micrometer metrics: https://resilience4j.readme.io/docs/micrometer
- Resilience4j — CircuitBreaker state machine and configuration: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Spring Boot Actuator and metrics endpoints: https://resilience4j.readme.io/docs/getting-started-3
- Spring Cloud CircuitBreaker — Resilience4J integration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
