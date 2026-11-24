# Monitoring container state

In Spring Kafka, `@KafkaListener` does not directly invoke `KafkaConsumer.poll()` inside business methods. The listener container manages the Kafka consumer, the poll loop, record dispatch, offset commits, and consumer lifecycle. When operating an application, you need to monitor containers to know whether a listener is running, stopped, has a pause requested, or is actually paused, as well as detect situations where records stop arriving or consumers become unresponsive.

Spring Kafka provides `KafkaListenerEndpointRegistry`, APIs on `MessageListenerContainer`, application events, and Kafka client metrics to observe state. Combining these sources helps distinguish a healthy running container on an idle topic from a stuck consumer, lost partition assignment, or connectivity issue.

## 1. What does the listener container manage?

When an application declares `@KafkaListener`, Spring creates a listener endpoint and registers a container managing that endpoint. The container uses `ConsumerFactory` to create Kafka consumers, calls `poll()`, delivers records to the listener, and handles acknowledgments/commits as configured.

With listener concurrency of one, there is typically one `KafkaMessageListenerContainer`. When concurrency is greater than one, Spring creates a `ConcurrentMessageListenerContainer` as the parent container and multiple child containers, each managing its own Kafka consumer.

```text
KafkaListenerEndpointRegistry
          |
          +---- orders-listener
          |          |
          |          +---- ConcurrentMessageListenerContainer
          |                    |
          |                    +---- KafkaMessageListenerContainer (consumer 0)
          |                    +---- KafkaMessageListenerContainer (consumer 1)
          |                    +---- KafkaMessageListenerContainer (consumer 2)
          |
          +---- payments-listener
                     |
                     +---- KafkaMessageListenerContainer
```

The diagram illustrates an application with an orders listener at concurrency three and a payments listener at concurrency one. Each child consumer has its own lifecycle and assignment, while the parent container represents the concurrent listener endpoint.

## 2. Querying containers via KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` manages containers created from listener endpoints, typically endpoints declared with `@KafkaListener`. You can inject the registry to retrieve the list of IDs, look up a container by ID, or iterate over registered containers.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class KafkaContainerStatusService {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerStatusService.class);

    private final KafkaListenerEndpointRegistry registry;

    KafkaContainerStatusService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void logContainerStates() {
        for (String listenerId : registry.getListenerContainerIds()) {
            MessageListenerContainer container =
                    registry.getListenerContainer(listenerId);

            if (container == null) {
                continue;
            }

            log.info(
                    "listenerId={}, running={}, pauseRequested={}, paused={}",
                    listenerId,
                    container.isRunning(),
                    container.isPauseRequested(),
                    container.isContainerPaused()
            );
        }
    }
}
```

Important methods:

| API | Meaning |
|---|---|
| `getListenerContainerIds()` | Retrieves listener IDs registered in the registry |
| `getListenerContainer(id)` | Retrieves a container by listener ID |
| `getListenerContainers()` | Retrieves containers managed by the registry |
| `isRunning()` | Indicates whether the container is running per lifecycle |
| `isPauseRequested()` | Indicates whether a pause has been requested |
| `isContainerPaused()` | Indicates whether the container is actually paused |

The registry manages endpoints registered with it. A `MessageListenerContainer` declared manually as a standalone bean does not necessarily appear in the registry; monitor that bean directly in that case.

## 3. Distinguishing running, pause requested, and paused

Do not collapse all states into a single `running` flag. A container can be running while having received a pause request and waiting for a safe point in the poll loop to pause the consumer.

| Observed state | Interpretation | Next action |
|---|---|---|
| `isRunning() == false` | Container is not started or has stopped | Check lifecycle, startup errors, or stop requests |
| `isRunning() == true`, `isPauseRequested() == false` | Container is active with no pause requested | Monitor assignment, polls, and record throughput |
| `isPauseRequested() == true`, `isContainerPaused() == false` | Pause was requested, but consumer has not finished pausing yet | Wait for pause event or inspect in-flight listener processing |
| `isContainerPaused() == true` | Container is paused | Identify who requested pause and when to resume |

For instance, calling `pause()` does not mean the consumer immediately halts all activity. The container coordinates pausing with the poll loop; the consumer must still maintain group management under Kafka mechanics. Therefore, `isPauseRequested()` and `isContainerPaused()` answer two distinct questions.

To resume receiving records, call `resume()` on the container. When managing via the registry, verify the container exists and check its state before issuing commands:

```java
public void pauseOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container != null && container.isRunning()
            && !container.isPauseRequested()) {
        container.pause();
    }
}

public void resumeOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container != null && container.isRunning()
            && container.isPauseRequested()) {
        container.resume();
    }
}
```

Pause is usually used when load control or a brief processing halt is needed. Stop terminates the container and closes consumers; that is a different lifecycle operation from pause.

## 4. Monitoring parent and child containers

When using `concurrency`, the registry returns the container representing the listener endpoint. If you need granular visibility into each child consumer, check for `ConcurrentMessageListenerContainer` and iterate over its child containers.

```java
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListenerContainer;

public void logChildContainerStates() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container instanceof ConcurrentMessageListenerContainer<?, ?> concurrent) {
        int index = 0;
        for (MessageListenerContainer child : concurrent.getContainers()) {
            log.info(
                    "listenerId=orders-listener, childIndex={}, running={}, paused={}",
                    index++,
                    child.isRunning(),
                    child.isContainerPaused()
            );
        }
    }
}
```

A parent container can be running while one child consumer hits a problem or has no partition assignment. Inspecting each child helps detect imbalance across consumers, especially at higher concurrency. Client ID suffixes and consumer metrics can correlate child entries with Kafka client statistics.

Do not assume child index `0` always reads partition `0`. Partition assignment is decided by the Kafka assignor and can change after rebalances.

## 5. Monitoring state with application events

Spring Kafka publishes application events at key moments of listener container and consumer activity. Applications can listen to these events to log, update dashboards, or trigger alerts.

Useful events include:

| Event | Observed information |
|---|---|
| `ListenerContainerIdleEvent` | Container received no records during the configured idle interval |
| `ListenerContainerNoLongerIdleEvent` | Container resumed receiving records after an idle period |
| `NonResponsiveConsumerEvent` | Consumer did not complete `poll()` within the monitoring interval |
| `ConsumerPausedEvent` / `ConsumerResumedEvent` | Child consumer paused or resumed |
| `ContainerPausedEvent` / `ContainerResumedEvent` | Container completed pausing or resuming |
| `ConsumerStartedEvent` / `ConsumerStoppedEvent` | Child consumer lifecycle started or ended |
| `ContainerStoppedEvent` | Listener container stopped |

Exact event lists and some methods may vary by Spring Kafka version. Consult the API for your project's version when reading additional event attributes.

### Configuring idle events

You can configure `idleEventInterval` on `ContainerProperties` so the container emits `ListenerContainerIdleEvent` when no records arrive during the configured interval.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class KafkaListenerEventConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            eventAwareKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setIdleEventInterval(60_000L);
        return factory;
    }
}
```

The listener uses this factory via the `containerFactory` attribute:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "eventAwareKafkaListenerContainerFactory"
)
public void consume(String payload) {
    process(payload);
}
```

### Receiving idle and non-responsive events

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
class KafkaContainerEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerEventObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listenerId={}, idleTime={}, partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions()
        );
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
                "Kafka consumer not responsive: listenerId={}, timeSinceLastPoll={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions()
        );
    }
}
```

An idle event does not automatically mean the consumer is failing. The topic may produce no data, the consumer group may not have partition assignments yet, or producers may have stopped sending. Conversely, `NonResponsiveConsumerEvent` is a signal to investigate because polling may be stalled or the consumer thread blocked.

Events are typically published on the container/consumer thread. Event listeners should execute quickly and avoid calling external services or performing long blocking work. If forwarding an event to an asynchronous executor, never use the attached `Consumer` object from another thread because Kafka consumers are not thread-safe.

## 6. Monitoring start, stop, pause, and resume lifecycles

Beyond idle and non-responsive events, you can listen to lifecycle events to record when a container or consumer changes state. For instance, `ContainerStoppedEvent` indicates the container has stopped; `ConsumerPausedEvent` and `ConsumerResumedEvent` report child consumer pause states.

Include these identifying fields in lifecycle logs:

- Listener ID to identify which endpoint changed state.
- Client ID or child consumer details if distinguishing concurrent consumers.
- Topic and partition when the event supplies assignment details.
- Event timestamp and stop reason if provided by your version's event API.

Avoid logging a generic message like "Kafka stopped". When multiple listeners exist, logs must identify which container stopped and what its prior state was.

## 7. Metrics that show whether a container is making progress

`isRunning()` only indicates lifecycle state. It does not prove the consumer is receiving records, holds assignments, or is processing successfully. To assess progress, combine Kafka consumer metrics, consumer group lag, and business metrics.

Commonly useful Kafka client metrics include:

| Metric | Operational meaning |
|---|---|
| `records-consumed-rate` | Rate of records read by the consumer |
| `records-lag-max` | Maximum lag between consumer position and log end offset across tracked partitions |
| `fetch-rate` | Frequency of fetch requests |
| `fetch-latency-avg` | Average fetch latency |
| `bytes-consumed-rate` | Rate of bytes read by the consumer |
| `commit-latency-avg` | Average offset commit latency |
| `poll-idle-ratio-avg` | Fraction of time the consumer is idle between polls rather than busy processing records, per Kafka client metric definition |

Metric names, scope, and export availability depend on the Kafka client version, available counters, and metrics system in use. `records-lag-max` must also be interpreted alongside assignment state; when a consumer has no partitions yet, zero lag does not mean the stream is healthy.

You can retrieve metrics from `MessageListenerContainer.metrics()` in Spring Kafka versions supporting this API:

```java
import org.apache.kafka.common.Metric;
import org.apache.kafka.common.MetricName;
import java.util.Map;

public void inspectKafkaMetrics() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container == null) {
        return;
    }

    Map<MetricName, ? extends Metric> metrics = container.metrics();
    metrics.forEach((name, metric) -> {
        log.debug(
                "Kafka metric: name={}, group={}, value={}",
                name.name(),
                name.group(),
                metric.metricValue()
        );
    });
}
```

With concurrent containers, metrics may be aggregated from child consumers and metric names can include a `client-id` tag. Do not dump every metric into logs on every poll; export them through your monitoring system at an appropriate interval and select key metrics for alerting.

## 8. Combining container state with consumer group lag

A solid operational dashboard should combine at least three layers of information:

1. **Lifecycle:** is the container running, paused, or emitting stop or non-responsive events.
2. **Kafka progress:** does the consumer hold assignments, what is the read rate, is lag growing or shrinking, are commits succeeding.
3. **Business processing:** how many events succeed, processing duration, error counts, retries, and dead-letter counts.

Example interpretations:

| Container state | Record rate / lag | How to investigate |
|---|---|---|
| Running, not paused | Record rate 0, lag 0 | Topic may have no new data; check producers and incoming traffic |
| Running, not paused | Record rate 0, lag rising | Check assignments, polling, broker connectivity, blocked listeners, and non-responsive events |
| Running, paused | Lag rising | Identify the pause request, pause duration, and resume condition |
| Stopped | Lag rising | Inspect lifecycle, startup failures, shutdown, or configuration errors |
| Running | High record rate but rising processing errors | Check deserialization, handlers, retries, dependencies, and dead-letter topics |

Never use consumer lag alone to conclude an application is healthy or broken. Zero lag while a topic has no new records is normal; rising lag can also happen when producers emit faster than processing capacity even though consumers are working properly.

## 9. Diagnostic procedure when a container behaves abnormally

When dashboards show a listener is not processing records as expected, check in sequence:

1. Use the registry to locate the right listener ID and confirm the container exists.
2. Check `isRunning()`, `isPauseRequested()`, and `isContainerPaused()`.
3. Inspect start/stop, idle, non-responsive, and pause/resume events near the incident timestamp.
4. Check partition assignments and consumer group membership to verify the consumer owns partitions.
5. Cross-check record rate, lag, fetch latency, poll, and commit metrics.
6. Check listener logs, exceptions, retries, dead-letter traffic, and dependency latency.
7. If the container has stopped, find the startup/shutdown cause or context failure; restart only after understanding the operational state and conditions.

Avoid automatically calling `start()` whenever `isRunning()` returns false without checking why. The container may have been intentionally stopped for maintenance or the application may be shutting down. Auto-restarting in those cases can violate operational intent.

## 10. Common misconceptions

1. **Assuming `isRunning() == true` means the consumer is reading records.** The container can be running without data, without partition assignments, or with polling problems.
2. **Treating pause requested as fully paused.** `isPauseRequested()` and `isContainerPaused()` reflect two different moments in the pause transition.
3. **Treating idle events as errors.** Idle only indicates no records arrived during the configured interval; cross-check incoming traffic and assignments.
4. **Treating a parent container as one consumer when concurrency exceeds one.** Concurrent containers manage multiple child consumers; inspect children when detailed diagnosis is needed.
5. **Doing blocking work inside event listeners.** Events are published in the container context; slow handling can impact the consumer path.
6. **Looking only at consumer lag.** Lag must be read alongside record rate, assignments, lifecycle, and business errors.
7. **Automatically restarting every stopped container.** Containers may be intentionally stopped or shutting down; identify the root cause before starting.

Effective container state monitoring combines lifecycle APIs, application events, Kafka client metrics, and consumer group lag. In Spring Kafka, the registry finds the right listener, container APIs report running/pause states, and events plus metrics show whether the consumer is making real progress or encountering trouble. Together, operations teams can distinguish empty topics, intentional pauses, and consumer incidents to address the true root cause.
