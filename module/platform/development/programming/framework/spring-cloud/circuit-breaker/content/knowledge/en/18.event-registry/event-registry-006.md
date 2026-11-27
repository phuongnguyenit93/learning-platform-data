# Managing Event Buffer Capacity and Processing Cost

## Lesson Objectives

Circuit breakers and Resilience4j mechanisms emit events when calls succeed, fail, are rejected, time out, or when states change. Events help development teams diagnose incidents and observe recovery. However, storing too many events or processing them too heavily can increase application memory usage and latency.

In Spring Cloud CircuitBreaker with Resilience4j, distinguish the buffer storing event history from the sliding window used to compute failure and slow-call rates. These two structures serve different purposes and must be tuned independently.

After this lesson, you will be able to:

- Describe the roles of CircuitBreakerRegistry, EventConsumerRegistry, and CircularEventConsumer.
- Configure eventConsumerBufferSize for an instance's event history.
- Distinguish event buffer capacity from slidingWindowSize.
- Estimate memory impact when running many breakers and multiple application instances.
- Register event listeners without slowing down the call path.
- Choose which events to log, record as metrics, or offload to asynchronous processing.
- Use Actuator event endpoints to investigate incidents and protect observability data.

## 1. When Are Resilience4j Events Emitted?

A circuit breaker emits events describing call outcomes and state. For example:

| Event Group | Meaning | Operational Value |
| --- | --- | --- |
| SUCCESS | A call completed successfully. | Track normal operation and recovery. |
| ERROR | A call failed and was recorded per configuration. | Find network errors, HTTP errors, or dependency processing failures. |
| IGNORED_ERROR | An error classified as ignored. | Confirm the exception does not affect the failure rate. |
| CALL_NOT_PERMITTED | The breaker rejected a call, usually because it is OPEN or not permitted at that moment. | Measure protection level and fast-rejected request counts. |
| STATE_TRANSITION | The breaker transitioned between CLOSED, OPEN, and HALF_OPEN. | Identify when it opened, started probing, and closed again. |
| RESET | The breaker was reset. | Track operational actions or intentional state resets. |

Specific event types and enum names can vary across Resilience4j versions. Use the API of the version managed in your project and subscribe only to the event types you need.

Events can include the instance name, event type, occurrence timestamp, call duration, and exception details. This is observability data. Events are not business data, not a durable message queue, and not a replacement for aggregated metrics.

Other mechanisms also emit events, such as Retry, RateLimiter, Bulkhead, and TimeLimiter. Each has its own event group: Retry reports retry attempts, Bulkhead reports permitted or rejected calls, and TimeLimiter reports timeouts. When implementing observability, keep mechanism and instance names clear so event types do not get mixed up.

## 2. Distinguishing Registry and Event Consumer

Resilience4j has a registry that manages instances of each mechanism. For example, CircuitBreakerRegistry manages circuit breakers by name. An application can obtain the inventory breaker from the registry or listen to events when instances are added, replaced, or removed.

An event consumer is responsible for receiving events emitted by an instance. In Resilience4j's Spring Boot integration, EventConsumerRegistry manages consumers bound to instance names. For CircuitBreaker, the consumer is typically connected to a circular buffer to retain recent history and supply data to observability endpoints.

You can picture it as:

    CircuitBreakerRegistry
        |
        +-- inventory CircuitBreaker
        |       |
        |       +-- EventPublisher
        |               |
        |               +-- EventConsumerRegistry
        |                       |
        |                       +-- Circular buffer (inventory)
        |
        +-- pricing CircuitBreaker
                |
                +-- EventPublisher
                        |
                        +-- EventConsumerRegistry
                                |
                                +-- Circular buffer (pricing)

Each component has a distinct responsibility:

- CircuitBreakerRegistry manages the lifecycle of breaker instances.
- EventPublisher emits events from a specific breaker.
- EventConsumerRegistry manages event-receiving consumers by instance name in the Spring Boot integration.
- CircularEventConsumer holds a fixed number of recent events in memory.

EventConsumerRegistry is not a distributed messaging system. It does not automatically synchronize history across pods, does not persist across restarts, and does not guarantee delivery to external systems. If you need long-term history or multi-instance aggregation, forward selected data to logging, metrics, tracing, or a centralized collection platform.

## 3. Circular Buffer Retains the Most Recent Events

CircularEventConsumer is a fixed-capacity consumer. When the buffer is not yet full, new events are appended. Once full, new events overwrite the oldest ones. Thus, the buffer always retains at most N recent events.

For example, a buffer with capacity 4:

    Incoming events: E1, E2, E3, E4
    Buffer:          [E1, E2, E3, E4]

    Event E5 arrives:
    Buffer:          [E2, E3, E4, E5]

    Event E6 arrives:
    Buffer:          [E3, E4, E5, E6]

This storage model works well for quickly viewing what happened right before a breaker opened or after a dependency recovered. It is not a processing backlog queue: the consumer does not retain every event indefinitely and does not guarantee the application can replay complete history.

You can use CircularEventConsumer directly:

    CircularEventConsumer<CircuitBreakerEvent> recentEvents =
        new CircularEventConsumer<>(50);

    circuitBreaker.getEventPublisher().onEvent(recentEvents);

    List<CircuitBreakerEvent> snapshot =
        recentEvents.getBufferedEvents();

This example creates a 50-event buffer for a breaker. When the 51st event arrives, the oldest event is replaced. Choose the capacity based on event emission rate and the investigation window needed. If you only need a few events leading up to opening, a small buffer may suffice. If you want to inspect a longer window during high traffic, use a larger capacity or forward selected data to a centralized observability system.

## 4. Configuring eventConsumerBufferSize

When using Resilience4j's Spring Boot integration, you can configure the event consumer buffer size per instance in application.yml:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            eventConsumerBufferSize: 100
          pricing:
            slidingWindowType: TIME_BASED
            slidingWindowSize: 10
            minimumNumberOfCalls: 10
            failureRateThreshold: 40
            eventConsumerBufferSize: 30

In this example:

- inventory retains at most 100 recent events in its event consumer buffer.
- pricing retains at most 30 recent events.
- slidingWindowSize is still configured separately to compute circuit breaker state.

eventConsumerBufferSize configures event history capacity in Resilience4j's Spring Boot/Actuator integration. If an application only uses Spring Cloud CircuitBreaker's factory without Resilience4j Spring Boot's event consumer auto-configuration, do not assume this property automatically creates event endpoints. In that case, the application can register consumers via EventPublisher or create a CircularEventConsumer itself.

Resilience4j documentation describes the event endpoint as returning recent events by default; the default value is commonly 100 in the Spring Boot integration. Verify the actual value for your version and configuration. Explicitly declaring eventConsumerBufferSize for instances you investigate avoids relying on defaults.

## 5. Event Buffer Differs from Sliding Window

Both structures have a size, but they are not interchangeable:

| Property | eventConsumerBufferSize | slidingWindowSize |
| --- | --- | --- |
| Purpose | Retains recent event history for observation. | Computes failure rate and slow-call rate. |
| Data | Event objects such as SUCCESS, ERROR, STATE_TRANSITION. | Call outcomes aggregated by count or time buckets. |
| When full | Oldest event is replaced in the circular buffer. | Old samples age out according to the sliding window mechanism. |
| Impact on OPEN decision | Does not directly determine breaker state. | Serves as input data for threshold evaluation. |
| Where used | Event endpoints, diagnostics, and listeners. | CircuitBreaker statistical logic. |

For example, slidingWindowSize of 20 means the breaker evaluates the 20 most recent calls when using COUNT_BASED. eventConsumerBufferSize of 100 means the event consumer keeps at most 100 events. A single call can emit multiple events over its lifecycle and other mechanisms have their own buffers, so the event count does not equal the sample count in the sliding window.

Do not increase eventConsumerBufferSize to change when a breaker opens. To change breaker opening behavior, adjust slidingWindowType, slidingWindowSize, minimumNumberOfCalls, and thresholds. To retain more event history for investigation, adjust eventConsumerBufferSize.

## 6. Estimating Memory Usage

Each event buffer holds references to event objects and associated data. Actual memory consumption depends on event type, exception metadata size, implementation details, JVM, and instance count. Therefore, capacity cannot be calculated solely from N.

You can use an initial estimation model:

    Total event slots
      = number of breaker instances x eventConsumerBufferSize

    Approximate memory
      = total event slots x average cost per event

For example, an application with 12 breakers where each buffer keeps 100 events holds up to roughly 1,200 event slots for those breakers. Increasing each buffer to 1,000 raises total slots to around 12,000. This is only a slot count calculation, not exact heap bytes.

When estimating, account for:

- Actual number of breaker instances, including dynamically created ones.
- Number of resilience mechanism types that have their own event buffers.
- Size of events and exception metadata.
- Number of running pods or JVMs.
- Memory allocated for caches, requests, responses, and other structures.

Buffers typically live in process memory. If 5 pods are running, each pod maintains separate buffers for its own breakers. System-wide capacity is roughly the sum across all pods. History in one pod does not automatically appear in another.

Do not create thousands of breakers keyed by request ID or user ID. Excessive instance creation raises both registry/metric cardinality and multiplies event buffers. Name breakers stably by dependency or operationally meaningful operation.

## 7. Sizing Capacity by Emission Rate and Investigation Window

Appropriate capacity depends on events per second and how far back you need to inspect. If a breaker emits an average of 20 events per second and its buffer holds 100 events, history only covers about 5 seconds. With a 1,000-slot buffer, theoretical retention grows to about 50 seconds at the same rate.

Approximate calculation:

    Retention window (seconds)
      = eventConsumerBufferSize / events per second

This is an estimate. Emission rates vary with traffic and event types; a call can emit SUCCESS or ERROR, and a state transition can add extra events. Do not treat this formula as a strict retention guarantee.

Some sizing guidelines:

- **Low traffic, quick triage:** a small or default buffer may be sufficient.
- **High traffic:** increase capacity if more history is needed, while checking heap usage and instance count.
- **Long-term history needed:** forward key events to logging or a centralized observability platform; do not rely on an in-memory ring buffer.
- **Many breakers:** prefer tuning buffers selectively for critical instances instead of raising all buffers uniformly.
- **Test environments:** small buffers can make testing overwrite behavior and event ordering easier.

If the buffer is too small, critical events may be overwritten before operators inspect the endpoint. If too large, the application retains many objects in memory while still lacking durable history. Size capacity according to practical triage windows and monitor heap usage after deployment.

## 8. Registering Listeners with Low Overhead

Resilience4j allows registering consumers directly with EventPublisher. With Spring Cloud CircuitBreaker, you can attach listeners when a breaker is created using addCircuitBreakerCustomizer:

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryEventCustomizer() {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(event ->
                    logger.info(
                        "inventory breaker transition: {}",
                        event.getStateTransition()
                    )
                )
                .onCallNotPermitted(event ->
                    metrics.counter("dependency.calls.rejected",
                        "dependency", "inventory").increment()
                )
                .onError(event ->
                    metrics.counter("dependency.calls.failed",
                        "dependency", "inventory").increment()
                ),
            "inventory"
        );
    }

This example shows a listener for the breaker named inventory. logger and metrics are application-configured components. Record only necessary details and use bounded-cardinality tags. Do not place SKU, userId, requestId, or payloads in metric tags.

Listeners can be invoked directly during event emission on the emitting thread. Therefore, treat callbacks as part of the execution path that must stay fast. Avoid doing the following inside callbacks:

- Making HTTP calls to logging or monitoring systems.
- Writing synchronously to a database.
- Waiting on locks or another thread.
- Serializing large payloads or complex exception graphs.
- Performing unnecessary CPU-intensive calculations.
- Throwing exceptions back into the event-emitting flow.

A slow listener can increase latency for protected calls or stall event delivery. A listener's goal is fast recording, not becoming a new dependency on the processing path.

## 9. Offloading Heavy Processing from Callbacks

If heavy event processing is required, push a small record onto a bounded internal queue and let a dedicated worker process it. The callback should only build a small event record and attempt a non-blocking enqueue:

    record ResilienceEventRecord(
        String breakerName,
        String eventType,
        Instant occurredAt
    ) {}

    void onCircuitBreakerEvent(CircuitBreakerEvent event) {
        ResilienceEventRecord record = new ResilienceEventRecord(
            event.getCircuitBreakerName(),
            event.getEventType().name(),
            event.getCreationTime()
        );

        if (!eventQueue.offer(record)) {
            droppedEventCounter.increment();
        }
    }

This is an illustrative example. Getter signatures and event names can differ depending on the Resilience4j version. eventQueue should be a bounded queue, such as ArrayBlockingQueue. offer does not block when the queue is full; the callback increments a counter to track dropped events.

A separate worker can batch records and ship them to an observability system. When designing this, decide clearly:

- When the queue is full, which events to drop, coalesce, or count.
- Whether STATE_TRANSITION, ERROR, and CALL_NOT_PERMITTED should take priority over SUCCESS.
- When the worker fails, whether to perform bounded retries or drop data.
- On application shutdown, whether to drain a final batch of events.
- Whether outbound data needs sensitive information scrubbed.

Never use an unbounded queue. If the downstream destination slows down, the queue will grow continuously and move the problem from callback latency to heap exhaustion. Never block the event-emitting thread waiting for queue space; doing so can increase latency on protected requests.

In reactive applications, you can convert EventPublisher into a Reactor stream and use an appropriate scheduler for downstream processing. However, manage subscriptions, backpressure, and bounded queues carefully. Do not subscribe to an uncontrolled event stream and leave an unbounded consumer running.

## 10. Selecting Events for Logs and Metrics

Not every event needs to be logged at INFO level. At high throughput, logging every SUCCESS can generate log volume far outweighing its diagnostic value.

A practical operational policy:

| Event | Recommended Observation |
| --- | --- |
| STATE_TRANSITION | Log at an appropriate level because this marks a major change in protection behavior. |
| ERROR | Increment counters and log in a controlled manner; avoid flooding logs with repeated stack traces. |
| CALL_NOT_PERMITTED | Increment counters to measure calls blocked by the breaker; can be aggregated over intervals. |
| SUCCESS | Primarily use aggregated metrics; logging every call is unnecessary. |
| IGNORED_ERROR | Track separately to detect exceptions excluded from failure rate. |
| RESET | Record the operational action and reason if the application supports a reset workflow. |

Events and metrics serve different goals. Events help inspect specific occurrences; metrics help aggregate trends over time and power alerts. Do not use the event buffer as the sole data source for long-term dashboards, as old events will be overwritten.

For metrics, use breaker names or service groups with finite cardinality. Avoid attaching exception messages as tags. For logs, you can keep exception classes and correlation IDs per security policy, but never log tokens, cookies, sensitive payloads, or unnecessary personal data.

## 11. Viewing Events via Spring Boot Actuator

When using Resilience4j's Spring Boot integration with Actuator, endpoints may be available to list instances and events. For example:

- /actuator/circuitbreakers lists circuit breaker names.
- /actuator/circuitbreakerevents returns recent circuit breaker events.
- Other mechanisms have corresponding endpoints for Retry, RateLimiter, Bulkhead, and TimeLimiter when integrated.

You can configure which endpoints to expose:

    management:
      endpoints:
        web:
          exposure:
            include: health,metrics,circuitbreakers,circuitbreakerevents

Available endpoints and endpoint names can vary by version, dependencies, and Actuator configuration. Verify the actual endpoints after starting the application. eventConsumerBufferSize controls the event consumer buffer capacity in the corresponding integration; how many events an endpoint returns also depends on the endpoint implementation and version.

Event endpoints can expose instance names, timestamps, exception messages, and durations. Protect them with authentication, network policies, or a dedicated management port. Do not expose management endpoints publicly just for debugging convenience. In production, expose only truly necessary endpoints and review event data before sharing externally.

## 12. Checking Behavior When Multiple Application Instances Run

Each JVM typically has its own registry and event consumer buffers. If order-service runs across multiple pods, each pod can have an inventory breaker with the same name but independent state and event history.

For example:

    order-pod-1: inventory buffer [E1, E2, E3]
    order-pod-2: inventory buffer [E4, E5, E6]
    order-pod-3: inventory buffer [E7, E8, E9]

These are local histories. An endpoint on pod 1 does not automatically return events from pod 2 and pod 3. During an investigation, identify which pod or application instance served the request. If you need a system-wide view, ship logs/metrics/traces from every pod to a centralized platform.

Do not use an in-memory EventConsumerRegistry to replace an event broker or durable log store. If events must be retained for auditing or long-term investigation, use a storage system with proper retention, access control, and query capabilities.

## 13. Lab: Tuning Buffers and Measuring Overhead

Create an application with two breakers: inventory and pricing. Perform the following:

1. Enable Resilience4j event integration and configure eventConsumerBufferSize to 5 for inventory and 20 for pricing.
2. Register listeners for STATE_TRANSITION, ERROR, and CALL_NOT_PERMITTED on inventory.
3. Send sequential successful calls, failed calls, and enough failures for the breaker to transition to OPEN.
4. Read CircularEventConsumer or the Actuator event endpoint to inspect the most recent events.
5. Generate more than 5 events and confirm the inventory buffer retains only the 5 newest events.
6. Change slidingWindowSize while keeping eventConsumerBufferSize unchanged; confirm the two settings have different effects.
7. Increase traffic and compare response times when the listener only increments a metric versus when it writes synchronous logs.
8. Try a consumer backed by a bounded queue; slow down the worker to verify the callback does not block and dropped events are counted.
9. Run multiple pods and verify each pod's event history does not merge automatically.
10. Check Actuator endpoint access controls and strip sensitive details from events/logs.

Upon completion, you should be able to explain that eventConsumerBufferSize retains history for observation, slidingWindowSize drives breaker decisions, a circular buffer overwrites old events when full, and heavy listeners can slow down requests. Choose buffer capacity based on breaker count, event rate, and investigation window; rely on metrics and centralized logging for long-term storage needs.

## References

- Resilience4j — CircuitBreaker: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Getting Started and event endpoints: https://resilience4j.readme.io/docs/getting-started-3
- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
