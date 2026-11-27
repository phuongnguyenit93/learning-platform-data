# Extending Registry or Event Consumers Without Blocking the Main Processing Path

A Circuit Breaker emits events when calls succeed, fail, are marked slow, or when the breaker transitions between CLOSED, OPEN, and HALF_OPEN states. These events help applications observe dependency health, update metrics, and trigger alerts. However, Resilience4j listeners are typically invoked directly on the thread emitting the event. If a listener performs synchronous logging, HTTP calls, message publishing, or database queries, observability itself can slow down the protected call.

In the **Registry and Events** chapter of the SPRING_CLOUD_CIRCUIT_BREAKER module, this lesson covers how to extend CircuitBreakerRegistry to track both existing and subsequently created instances, how to use EventConsumerRegistry to keep a bounded event history, and how to offload expensive work to a bounded asynchronous queue. The goal is to observe the system without turning event listeners into a new dependency on the request processing path.

## 1. Event Types to Observe

A Circuit Breaker emits several event categories during its lifecycle:

| Event Group | Examples | Operational Meaning |
|---|---|---|
| Call outcome | success, error, ignored error | Know what outcomes the dependency is returning |
| Latency | slow call, slow call rate exceeded | Detect a slow-responding dependency before widespread timeouts |
| State | state transition | Know when the breaker transitions CLOSED, OPEN, or HALF_OPEN |
| Call rejection | call not permitted | Count fast-failed requests when the breaker is OPEN |
| Registry lifecycle | entry added, entry removed, entry replaced | Track when breakers are created, removed, or replaced |

Events can be used to:

- Update counters, timers, and gauges in Micrometer.
- Record state transitions so operations knows which dependencies are OPEN.
- Trigger alerts when a breaker stays open too long or oscillates repeatedly.
- Preserve incident trails for correlation with logs and distributed traces.
- Analyze failure rates, slow calls, and rejected request counts.

Not every event needs to be sent to an external system. For metrics, updating in-memory counters is usually sufficient. For logs or notifications, send only meaningful events with rate control to avoid flooding during a dependency outage.

## 2. Distinguishing Registry Events and Circuit Breaker Events

There are two distinct layers of events:

- **Registry events** describe the lifecycle of entries in the registry, such as a new Circuit Breaker being added or removed.
- **Circuit Breaker events** describe the activity of an instance, such as successful calls, errors, slow calls, or state transitions.

If you only register listeners directly on a pre-created Circuit Breaker, the application will not automatically track instances created later. To extend coverage across the entire registry, register the lifecycle listener first, then attach operational listeners to each new entry.

Example with Resilience4j CircuitBreakerRegistry:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import jakarta.annotation.PostConstruct;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerRegistryObserver {
    private final CircuitBreakerRegistry registry;
    private final CircuitBreakerEventBridge eventBridge;
    private final Set<String> attached = ConcurrentHashMap.newKeySet();

    public CircuitBreakerRegistryObserver(
            CircuitBreakerRegistry registry,
            CircuitBreakerEventBridge eventBridge) {
        this.registry = registry;
        this.eventBridge = eventBridge;
    }

    @PostConstruct
    void subscribeToRegistry() {
        // Track instances added after the listener is registered.
        registry.getEventPublisher()
            .onEntryAdded(event -> attach(event.getAddedEntry()));

        // Attach listeners to already existing instances.
        registry.getAllCircuitBreakers().forEach(this::attach);
    }

    private void attach(CircuitBreaker circuitBreaker) {
        // Prevent duplicate registration if an entry appears in both steps concurrently.
        if (!attached.add(circuitBreaker.getName())) {
            return;
        }

        circuitBreaker.getEventPublisher()
            .onEvent(eventBridge::enqueue);
    }
}
~~~

The registry listener is registered before iterating over existing entries. If a new entry appears while the loop is running, it might be seen in both places; the `ConcurrentHashMap`-backed set prevents attaching the listener twice.

In a Spring Cloud CircuitBreaker application, ensure the registry injected here is the exact same registry the factory uses to create the instances you want to observe. How a registry is created and shared depends on the starter version and application configuration. If the factory uses a different internal registry, listeners on a separate registry will not receive events from breakers created by the factory. Configure a shared registry or register directly on instances provided by the factory.

## 3. EventPublisher and Limits of Synchronous Listeners

Resilience4j provides an EventPublisher on each Circuit Breaker. You can register callbacks per event type:

~~~java
circuitBreaker.getEventPublisher()
    .onSuccess(event -> metrics.recordSuccess(event))
    .onError(event -> metrics.recordError(event))
    .onStateTransition(event -> metrics.recordTransition(event))
    .onCallNotPermitted(event -> metrics.recordRejected(event));
~~~

Or register a single consumer for all events:

~~~java
circuitBreaker.getEventPublisher()
    .onEvent(event -> eventBridge.enqueue(event));
~~~

Note that callbacks are typically invoked synchronously when Resilience4j emits an event. Depending on the event type and version, callbacks can run on the thread executing the protected call or the thread performing a state transition. Therefore, treat listeners as code capable of impacting the latency of the event-emitting thread.

The following operations should not run directly inside a callback:

- Making HTTP calls to a monitoring server or notification service.
- Sending messages synchronously to a broker.
- Writing data to a database via blocking I/O.
- Reading files or calling external services.
- Running aggregation queries or heavy data processing.
- Waiting on locks, semaphores, or queue slots for long durations.

If a callback takes 100 ms to send an alert, the protected dependency call may have to wait an extra 100 ms even after the response has already arrived. If the dependency fails en masse and every request emits an event, the added time can propagate the incident to the calling service.

Listeners should do minimal work: extract needed fields, update lightweight counters, or push the event onto a bounded queue and return.

## 4. Using EventConsumerRegistry to Store Bounded History

Resilience4j provides EventConsumerRegistry and EventConsumer to retain a fixed number of recent events in memory. This is a convenient way to inspect recent events or supply data to a diagnostic endpoint.

Example:

~~~java
import io.github.resilience4j.core.EventConsumer;
import io.github.resilience4j.core.EventConsumerRegistry;
import io.github.resilience4j.circuitbreaker.event.CircuitBreakerEvent;

EventConsumerRegistry<CircuitBreakerEvent> consumers =
    new EventConsumerRegistry<>();

EventConsumer<CircuitBreakerEvent> recentEvents =
    consumers.createEventConsumer("catalog-read-events", 100);

circuitBreaker.getEventPublisher().onEvent(recentEvents);
~~~

With the configuration above, the consumer retains up to 100 of the most recent events for the attached Circuit Breaker. You can read a history snapshot using:

~~~java
List<CircuitBreakerEvent> events = recentEvents.getBufferedEvents();
CircuitBreakerEvent latest = recentEvents.getLatestEvent();
~~~

EventConsumerRegistry is helpful for short-term in-memory history, but you must understand its limits:

- The buffer has a fixed size; old events are evicted when the buffer fills up.
- Data does not persist across application restarts.
- The buffer is not a message broker and does not guarantee at-least-once or exactly-once processing.
- Registering an EventConsumer does not automatically create an asynchronous worker to process events.
- The consumer receives events on the event-emitting path; writing into the buffer does not turn the callback into a background I/O pipeline.

Therefore, use EventConsumerRegistry to review recent events, support debugging, or display current status. If you need to ship data to another system or perform expensive processing, offload the work to a separate asynchronous mechanism.

## 5. Offloading Heavy Processing to a Bounded Queue

A common pattern is using an executor with a bounded queue. The listener only calls execute to hand off the event to a worker; the worker then performs logging, message sending, or external system updates.

Executor configuration:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class CircuitBreakerEventExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor circuitBreakerEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("cb-event-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}
~~~

In this example, the queue holds 500 items with up to two worker threads. When the queue is full, AbortPolicy rejects new tasks instead of running them on the event-emitting thread. This is crucial: using CallerRunsPolicy could force the callback to run heavy work itself when the executor is overloaded, defeating the goal of keeping the main processing path non-blocking.

Bridge that receives events and submits them to the executor:

~~~java
import io.github.resilience4j.circuitbreaker.event.CircuitBreakerEvent;

import java.util.concurrent.atomic.LongAdder;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerEventBridge {
    private final ThreadPoolTaskExecutor executor;
    private final CircuitBreakerEventHandler handler;
    private final LongAdder droppedEvents = new LongAdder();

    public CircuitBreakerEventBridge(
            ThreadPoolTaskExecutor circuitBreakerEventExecutor,
            CircuitBreakerEventHandler handler) {
        this.executor = circuitBreakerEventExecutor;
        this.handler = handler;
    }

    public void enqueue(CircuitBreakerEvent event) {
        try {
            executor.execute(() -> handler.handle(event));
        } catch (TaskRejectedException rejected) {
            // Do not block on the queue and do not run the handler on the request thread.
            droppedEvents.increment();
        }
    }

    public long getDroppedEventCount() {
        return droppedEvents.sum();
    }
}
~~~

Handler running on a worker thread:

~~~java
@Component
public class CircuitBreakerEventHandler {
    public void handle(CircuitBreakerEvent event) {
        // Perform potentially slow work here:
        // update telemetry systems, write selective logs, or send notifications.
        // If I/O fails, record event-handling errors and apply separate retries.
    }
}
~~~

In practice, expose metrics for dropped event counts, queue depth, processing duration, and handler error counts. A bounded queue forces the system to have a clear policy when event emission outpaces processing. For critical metrics such as OPEN transitions, you can update a lightweight counter directly in the listener and send notifications asynchronously. For detailed per-request logs, apply sampling or rate limiting.

## 6. Never Use an Unbounded Queue

An unbounded queue may seem to guarantee the listener can always enqueue events, but when a dependency suffers an outage, event volume can grow faster than the worker can drain it. The queue keeps expanding, consuming heap memory and introducing huge lag. The system can run out of memory or process stale alerts long after the incident has ended.

When sizing queue capacity, consider:

- Normal and incident-peak event emission rates.
- Average time for a worker to process one event.
- Number of worker threads and downstream I/O capacity.
- Importance of each event type.
- Behavior when the queue is full: drop, sample, coalesce, or record summary metrics.

Not all events carry equal value. For instance, thousands of success events per minute can be aggregated into counters; OPEN or HALF_OPEN state transitions carry higher diagnostic value and may warrant priority. You can use a dedicated queue for state events or maintain local counters so vital information is not lost when the queue fills up.

If critical events must survive restarts, use an appropriate durable mechanism and account for the I/O cost, without writing directly to durable storage on the request thread. An outbox or message broker may fit when high reliability is required; design bounds, retries, and deduplication at the worker layer.

## 7. Tracking Entries Added to and Removed from the Registry

When a registry manages multiple Circuit Breakers by ID, you can attach listeners when an entry is created and clean up related resources when an entry is removed. For example:

~~~java
registry.getEventPublisher()
    .onEntryAdded(event -> {
        CircuitBreaker added = event.getAddedEntry();
        eventBridge.attach(added);
    })
    .onEntryRemoved(event -> {
        CircuitBreaker removed = event.getRemovedEntry();
        eventBridge.detach(removed.getName());
    });
~~~

Method names on entry events may depend on the registry type and Resilience4j version; use the corresponding API in the project's managed version. The principle is that lifecycle listeners should track both entry additions and removals. If the application can replace entries, also handle replacement events to attach listeners to the new instance.

A set of already-attached names prevents duplicate registration. When an entry is removed, update the tracking set and release subscriptions or references if your version's API provides listener removal. Do not hold references indefinitely to removed breakers, as a dynamic registry could leak memory over time.

If registries are recreated per context or tenant, scope the event bridge lifecycle accordingly. Avoid a static registry or static map shared across all application contexts, which can easily leak state across tests, tenants, or restarts.

## 8. Keep Callbacks Small and Avoid Event Loops

An event handler can inadvertently generate more events. For example, when a breaker transitions to OPEN, the handler calls a monitoring endpoint; that endpoint in turn calls the protected dependency and generates more events. Or the handler writes to a service that is itself protected by the Circuit Breaker being observed. This can create feedback loops or make metrics hard to interpret.

To avoid this:

- Never call a protected dependency from that same breaker's callback.
- Never use an event handler to execute a fallback for the request that emitted the event.
- Never record metrics via a synchronous HTTP client inside a callback.
- Use a separate dependency ID for telemetry if network calls are necessary.
- Apply timeouts, Bulkheads, and Circuit Breakers to the telemetry path as an independent dependency.
- Never re-emit the same event in a way that causes the handler to trigger itself infinitely.

Events are observational signals, not a place to orchestrate request business logic. Fallback logic belongs in the protected call; telemetry logic should remain isolated and able to fail without affecting the primary outcome.

## 9. Avoiding High Cardinality When Turning Events into Metrics

When converting Circuit Breaker events into metrics, choose tags with a finite set of values. The breaker name is usually a helpful tag when the number of breakers is bounded. Event type and outcome are also tags with small value domains.

Avoid using the following values as metric tags:

- User ID or account ID.
- Request ID or correlation ID.
- Full URLs containing path parameters.
- Exception messages containing dynamic data.
- Product ID, order ID, or transaction ID.

Tags with unbounded values create high cardinality, increasing memory usage and metrics backend costs. Information needed to trace individual requests belongs in logs or traces, not in counter tags.

One way to categorize metrics:

| Metric | Appropriate Tags |
|---|---|
| State transition count | breaker name, from state, to state |
| Failed call count | breaker name, error category |
| Rejected call count | breaker name |
| Dropped event count | queue/consumer name |
| Event handling duration | handler name, outcome |

When using Micrometer, counters and timers can be updated inside listeners with brief operations. Exporting or pushing data to backends is handled separately by the registry and exporter—never make manual HTTP calls inside a listener.

## 10. Verifying That Listeners Do Not Slow Down the Main Processing Path

A test suite should verify both event correctness and latency impact:

1. Create a Circuit Breaker and register listeners; verify listeners receive success, error, and state transition events.
2. Create an additional breaker after the registry listener is registered; verify the new instance also receives the event listener.
3. Generate multiple events in succession; verify the EventConsumer buffer retains only the configured limit.
4. Intentionally slow down the worker handler; verify protected requests do not wait on handler I/O.
5. Fill the executor queue; verify callbacks return quickly, the dropped event count rises, and handlers do not run on the caller thread.
6. Remove or replace an entry; verify the new listener is attached and old references are managed.
7. Test shutdown; verify workers stop within the bounded timeout without hanging the application indefinitely.

Measure call latency with and without listeners under identical load conditions. Because the listener only enqueues, the added overhead should be tiny and stable. If latency rises significantly, check whether callbacks serialize large payloads, wait on locks, write synchronous logs, or use a CallerRuns rejection policy.

## 11. Asynchronous Event Consumer Architecture Diagram

~~~mermaid
flowchart TD
    A["Call protected by Circuit Breaker"] --> B["Resilience4j emits event"]
    B --> C["Short listener: enqueue"]
    C --> D{"Bounded queue has space?"}
    D -- "Yes" --> E["Worker thread takes event"]
    E --> F["Metrics, logs, or notifications"]
    D -- "No" --> G["Drop/sample and increment dropped counter"]
    G --> H["Request continues without waiting for worker"]
    F --> I["Track handler errors separately"]
~~~

This architecture decouples event emission from expensive processing. The bounded queue protects memory; rejections do not run the handler on the event-emitting thread; the worker processes independently and can be monitored separately.

## Conclusion

CircuitBreakerRegistry can be extended with lifecycle listeners to automatically attach event consumers to both existing and subsequently created instances. EventConsumerRegistry is well suited for retaining recent history in a bounded buffer, though it is neither an asynchronous queue nor durable storage. Because event callbacks typically run on the event-emitting thread, keep listeners brief and offload I/O or heavy processing to an executor with a bounded queue. Monitor dropped events, queue depth, and handler latency; avoid CallerRuns, unbounded queues, and high-cardinality metric tags. When telemetry stays within its own resource bounds, observing a Circuit Breaker will never become the bottleneck slowing down the main processing path.
