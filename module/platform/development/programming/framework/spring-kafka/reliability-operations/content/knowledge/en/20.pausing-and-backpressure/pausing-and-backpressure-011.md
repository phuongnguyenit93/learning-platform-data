# Container Pause Events

## 1. What is a container pause event?

In Spring Kafka, a listener container owns the Kafka consumer's `poll()` loop and invokes the `@KafkaListener` method when records arrive. When the application needs to temporarily stop accepting more work—for example, because a database is overloaded or a processing queue is nearly full—the application can request to **pause the listener container** instead of stopping the consumer entirely.

Once the pause request is actually applied by the container onto its assigned partitions, Spring Kafka publishes a **`ConsumerPausedEvent`**. When the container is resumed and the resume actually takes effect, it publishes **`ConsumerResumedEvent`**. These are Spring application events reflecting the state of the listener container; they are not messages published to a Kafka topic.

Key meanings to remember:

- `container.pause()`: **requests** stopping further fetching/delivery for the relevant partitions.
- `ConsumerPausedEvent`: notifies that the container **has applied** pause to the partitions named in the event.
- `container.resume()`: requests resuming processing.
- `ConsumerResumedEvent`: notifies that the container has executed the resume.
- Pause is not stop: the container still exists, keeps its right to participate in the consumer group, and normally keeps calling `poll()` in the paused state to maintain group membership.

Container pause events are very useful in reliability operations because they let you distinguish a control action that was **requested** from a state that has **actually taken effect**. If you merely log right after `pause()` claiming the consumer has completely stopped receiving records, the log can be inaccurate during the transition window.

## 2. Context: backpressure in consumers

**Backpressure** is proactively reducing or temporarily halting the rate of accepting work when downstream cannot keep up. With Spring Kafka, downstream can be:

- Exhausted database connection pools.
- Slow HTTP services or services returning 429/503.
- Nearly full in-memory queues of business workers.
- Bottlenecked file/object storage writers.
- High application CPU/heap utilization.
- Internal work needing a temporary halt during controlled maintenance.

Example:

~~~text
Kafka topic "orders"                   Spring application
  P0, P1, P2            poll()                  |
     | ---------------------------> @KafkaListener
     |                                    |
     |                                    v
     |                             Database / HTTP API
     |                                    |
     |                             Temporary overload
     |                                    |
     |                         Backpressure controller
     |                                    |
     |                         container.pause()
     |                                    |
     |                   ConsumerPausedEvent is published
     |                                    |
     |                Temporarily stop receiving from partitions
     |                                    |
     |                          Downstream recovers
     |                                    |
     |                         container.resume()
     |                                    |
     |                  ConsumerResumedEvent is published
     |                                    |
     |                          Processing resumes
~~~

An intentional pause stops pulling more data into the listener while the system sheds load. It **does not** slow down producers writing to the topic; backlog typically stays in Kafka and consumer lag may climb.

If a pause lasts too long, topic retention can delete unread data, or processing latency can breach SLAs. Therefore, pause should be a conditional throttling measure with a resume plan, not a way to mask a permanently broken downstream.

## 3. Distinguishing pause requests from pause events

A common operational mistake is treating a `pause()` call as meaning the consumer stopped at the exact instant of the call.

In Spring Kafka, the container can receive a pause command from a thread other than the consumer thread. The command records a request; the container applies the pause at a safe point in the processing loop, normally before the next `poll()`.

~~~mermaid
sequenceDiagram
    participant O as Operator / controller
    participant C as Listener container
    participant P as Consumer thread
    participant E as Spring event listener

    O->>C: pause()
    Note over C: pause requested = true
    C-->>O: Returns from pause()
    P->>P: Finish required work from current poll
    P->>P: KafkaConsumer.pause(assigned partitions)
    P->>E: Publish ConsumerPausedEvent
    Note over C: consumer actually paused = true
    P->>P: Continue polling while paused to keep membership
    O->>C: resume()
    P->>P: KafkaConsumer.resume(partitions)
    P->>E: Publish ConsumerResumedEvent
    Note over C: consumer paused = false
~~~

This diagram shows the general flow; exact record-processing boundaries also depend on `pauseImmediate`, listener type, and Spring Kafka version.

### 3.1. isPauseRequested()

`isPauseRequested()` reflects whether the container holds a pause request. It can become true before the consumer thread applies the pause command.

### 3.2. isConsumerPaused()

`isConsumerPaused()` indicates whether the container/consumer is in the paused state per container mechanics. With a concurrent container, the aggregate meaning depends on child containers' states; do not rely solely on one boolean if you need to know exactly which partitions paused.

### 3.3. ConsumerPausedEvent

The event indicates that the pause operation has been executed. Upon receiving the event, you can log it and update observed state. The topic-partition names in the event help pinpoint pause scope at that instant.

### 3.4. ConsumerResumedEvent

The event indicates that the container resumed the corresponding partitions. Do not immediately conclude the backlog is gone or the listener finished processing records; resume simply reopens the fetch/dispatch pipeline on the poll schedule.

| Signal | What does it prove? | What does it **not** prove? |
|---|---|---|
| `pause()` returned | A pause request was sent to the container | That the consumer paused every partition |
| `isPauseRequested() == true` | Container has a pending pause request | That zero records are still processing |
| `ConsumerPausedEvent` | Pause was applied to the reported partitions | That downstream recovered or queues emptied |
| `isConsumerPaused() == true` | Consumer/container is in the actual paused state | That Kafka producers stopped writing too |
| `ConsumerResumedEvent` | Resume was applied | That the next record succeeded |
| `container.stop()` | Requested container lifecycle stop | Equivalent to a membership-preserving pause |

## 4. Which events does Spring Kafka publish?

### 4.1. ConsumerPausedEvent

`ConsumerPausedEvent` is published by Spring Kafka when the container actually pauses partitions. The event carries information about paused partitions and links to the source container.

It can be used to:

- Log when the pause took effect.
- Update status displayed on dashboards.
- Count backpressure-triggered pauses.
- Measure elapsed duration from pause to resume.
- Separate requested state from actual state.

### 4.2. ConsumerResumedEvent

`ConsumerResumedEvent` is published when paused partitions are resumed. It typically fires after a `resume()` call or an equivalent container action.

It can be used to:

- Mark when the consumer resumed reading.
- End pause-duration measurements.
- Confirm that a load-shedding period ended.
- Monitor cases where a resume request was never applied.

### 4.3. Per-partition events

Spring Kafka also provides events for pausing/resuming individual partitions:

- `ConsumerPartitionPausedEvent`
- `ConsumerPartitionResumedEvent`

They fit when the application explicitly calls `pausePartition(TopicPartition)` and `resumePartition(TopicPartition)` instead of pausing the whole container.

Distinguish container-wide events from per-partition events so you do not mistakenly count "entire consumer stopped processing" when only one partition paused.

### 4.4. Which events are not pause events?

Several other Spring Kafka events reflect distinct states:

- `ListenerContainerIdleEvent`: listener container is idle per observation threshold; does not by itself prove the container is paused.
- `ListenerContainerNoLongerIdleEvent`: container is no longer idle.
- `NonResponsiveConsumerEvent`: signals an unresponsive consumer poll under certain conditions per Spring Kafka monitoring.
- `ConsumerStoppedEvent` / `ContainerStoppedEvent`: lifecycle stopped, distinct from pause.
- Partition assignment/revocation callbacks: tied to consumer group rebalances, not pause events.

Do not conclude a consumer is paused merely because no new records arrive, since the topic may genuinely have no data or the listener container may have another issue.

## 5. Configuring and receiving events with @EventListener

Spring Kafka publishes container events through `ApplicationEventPublisher`. In Spring Boot, a bean can receive events via `@EventListener`.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPauseEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseEventLogger.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.warn(
            "Kafka consumer PAUSED, partitions={}",
            event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
            "Kafka consumer RESUMED, partitions={}",
            event.getPartitions()
        );
    }
}
~~~

The example above only observes state. Consumer pause events hold the `TopicPartition` collection to identify scope. Depending on the Spring Kafka version, events also expose appropriate source/container metadata to distinguish listener containers.

**Operational note:** by default, a Spring application event listener can execute synchronously on the publishing thread. When the Kafka container publishes from the consumer thread, the `@EventListener` callback may run directly on the consumer thread. Keep callbacks short—do not make slow HTTP or database calls, wait indefinitely on latches, or invoke unsafe `KafkaConsumer` methods.

If the application uses an asynchronous `ApplicationEventMulticaster` or `@Async` to receive events, callbacks run on another thread. In that case, you must definitely not grab `KafkaConsumer` from the event to call non-thread-safe methods. Use container-level APIs such as `pause()`/`resume()` through supported mechanisms.

## 6. Issuing pause/resume via KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` manages listener containers created for `@KafkaListener`s with IDs. You can look up the container by ID and request pause/resume from a Spring service.

### 6.1. Declaring a listener with an ID

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

The `orders-listener` ID lets control components retrieve the exact listener container. If the application has multiple listeners, assign distinct IDs; never reuse the same ID across endpoints.

### 6.2. Container control service

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaPauseController {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaPauseController(
        KafkaListenerEndpointRegistry registry
    ) {
        this.registry = registry;
    }

    private MessageListenerContainer ordersContainer() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalStateException(
                "Listener container orders-listener does not exist"
            );
        }
        return container;
    }

    public void requestPause() {
        ordersContainer().pause();
    }

    public void requestResume() {
        ordersContainer().resume();
    }

    public boolean isPauseRequested() {
        return ordersContainer().isPauseRequested();
    }

    public boolean isActuallyPaused() {
        return ordersContainer().isConsumerPaused();
    }
}
~~~

Container-level `pause()`/`resume()` is the right way for external control threads to issue requests. Never grab the container's `KafkaConsumer` directly and call `pause()` from a REST controller or scheduler thread; `KafkaConsumer` has strict thread-ownership rules.

### 6.3. Which containers does the registry hold?

The registry manages containers bound to Kafka listener endpoints. If the application declares a container bean manually in Java instead of creating it via `@KafkaListener`, that container may be managed by another bean/lifecycle and not necessarily retrievable under the same registry ID.

Locate the right container before acting. In multi-replica deployments, one JVM's registry only controls listener containers **inside that JVM**; calling pause in Pod A does not automatically pause Pod B.

## 7. What happens when pause() is called?

A simple mental model:

~~~text
1. Backpressure controller sees queue nearly full.
2. Controller calls container.pause().
3. Container records pause requested.
4. Container reaches a safe point in the poll loop.
5. Container pauses currently assigned partitions.
6. ConsumerPausedEvent is published.
7. Container keeps polling in paused state to keep group.
8. After downstream recovers, controller calls resume().
9. Container executes resume.
10. ConsumerResumedEvent is published.
11. Listener resumes receiving/dispatching new records.
~~~

Important notes:

- Pause usually takes effect at poll boundaries, not necessarily at the exact instant the caller invokes the method.
- Records currently being processed by the listener are not canceled or rolled back automatically by pausing.
- Records already returned in an earlier poll may still be processed by the container before pause takes effect.
- After resume, the consumer may receive a large backlog; throttle downstream rate rather than resuming blindly into unsustainable load.

## 8. pauseImmediate and already-polled records

Under traditional container behavior, pause is applied after finishing **all remaining records from the current poll**. If a single poll returned many records and the controller requests pause mid-way, unprocessed records from that poll may still be delivered to the listener before pause takes effect.

Starting in Spring Kafka 2.9, `pauseImmediate` can be configured so the container pauses after the **currently processing record**, instead of waiting to finish all records returned by the poll. Unprocessed records from that poll can be retained by the container for processing after resume.

Container factory configuration example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setPauseImmediate(true);

    return factory;
}
~~~

This mode helps when backpressure must react quickly, yet involves trade-offs:

- The container must hold already-fetched but undispatched records in memory.
- The currently processing record must still finish or fail via the error handler; pause does not cut off a service method mid-execution.
- Batch listeners and record listeners have different semantics per callback.
- Memory and poll sizing must be managed when payloads are large.

Do not treat `pauseImmediate=true` as an immediate execution interrupt or a transaction cancellation. It configures when the container applies pause within the record-delivery cycle.

## 9. Container keeps polling while paused to prevent rebalances

Kafka separates two concepts:

1. The consumer **stops receiving additional records to process** from paused partitions.
2. The consumer must still **preserve group membership** via the liveness/poll contract.

Spring Kafka containers are designed to continue calling `poll()` while the consumer is paused, maintaining group activity and preventing rebalances triggered simply by proactively halting reads. The Kafka consumer handles heartbeats/group coordination while returning no new records from paused partitions.

~~~text
Container PAUSED:
    KafkaConsumer.poll()  -> may continue running
    Assigned partitions   -> still owned by consumer
    Record delivery       -> suspended per pause scope
    Group membership      -> maintained
    Consumer lag          -> may increase
~~~

However, **pausing does not guarantee group stability** across every failure. If the JVM hits a stop-the-world pause, the consumer thread cannot poll, the coordinator stops responding, or networking drops for too long, `session.timeout.ms` or `max.poll.interval.ms` violations can still occur.

Therefore, never use pause to mask a listener blocked indefinitely. If a business callback hangs, a pause request from another thread cannot force the listener out so the container can poll again.

## 10. Pause is not stop, unsubscribe, or shutdown

| Operation | Expected impact | Group membership | Key caveats |
|---|---|---|---|
| `container.pause()` | Stops taking more records from container's partitions once effective | Usually retained, as polling continues | Already-polled records may still exist |
| `container.resume()` | Allows fetching/dispatching again | Continues | Does not fix downstream overload on its own |
| `container.stop()` | Stops listener container lifecycle | Consumer may leave group | Can trigger rebalance |
| `container.start()` | Starts listener container | Joins/rejoins group | Assignments may change |
| Kafka `consumer.unsubscribe()` | Cancels consumer subscription | Loses membership under old subscription | Not a normal backpressure control API |
| `pausePartition(tp)` | Pauses only one topic-partition | Keeps consumer and other partitions active | Requires tracking per-partition state |

If the goal is temporarily shedding load for a few seconds or minutes, `pause`/`resume` usually fits better than `stop`/`start` because it avoids unnecessary group join/leave churn.

For extended maintenance, infrastructure disconnection, or rollouts, `stop`/`start` and lifecycle orchestration may be more appropriate. Avoid using indefinite pause as a substitute for deployment lifecycle operations.

## 11. Container-wide pause vs. per-partition pause

Spring Kafka supports pause/resume at two different scopes.

### 11.1. Whole listener container

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

container.pause();
~~~

This command applies the pause request across that container's child consumers. With `ConcurrentMessageListenerContainer`, there can be multiple child containers, each owning its own partition set.

As each child actually pauses, corresponding events may be published; do not assume a single pause call on a concurrent parent container always yields exactly one Spring event.

### 11.2. A single partition

Example pausing `orders-2` specifically:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.MessageListenerContainer;

MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

TopicPartition partition = new TopicPartition("orders", 2);

container.pausePartition(partition);
~~~

When ready to continue:

~~~java
container.resumePartition(
    new TopicPartition("orders", 2)
);
~~~

In versions supporting these APIs, you can use `isPartitionPauseRequested(tp)` and `isPartitionPaused(tp)` to distinguish requested state from actual state.

When partition pause takes effect, Spring may publish `ConsumerPartitionPausedEvent`; when resume takes effect, it publishes `ConsumerPartitionResumedEvent`.

### 11.3. When to pause per partition?

Per-partition throttling helps when:

- One partition has a hot key generating abnormal load.
- Downstream only struggles with data for a single tenant routed mainly to one partition.
- You want to halt one partition to handle an incident while other partitions keep moving.
- One partition waits on an external dependency while other partitions are independent.

However, if all partitions share one exhausted database pool, per-partition pausing may not suffice; throttle at the container or instance scope.

### 11.4. Rebalances change partition ownership

When a group rebalances, a partition can move to another child consumer or instance. A pause request recorded on the old container does not mean it automatically transfers to the new consumer under a distributed business policy.

If backpressure policy must survive reassignments, add a mechanism to reapply policy on new assignments, or use a controller/coordination store shared across instances. Never assume a pause event from one pod controls the whole consumer group.

## 12. Capturing partition pause events too

If an application uses both container pause and per-partition pause, observe them separately:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionPauseLogger {

    @EventListener
    public void onPartitionPaused(ConsumerPartitionPausedEvent event) {
        log.warn("A Kafka partition was paused: {}", event);
    }

    @EventListener
    public void onPartitionResumed(ConsumerPartitionResumedEvent event) {
        log.info("A Kafka partition was resumed: {}", event);
    }
}
~~~

This example logs the entire event to avoid depending on version-specific accessor methods across Spring Kafka releases. When extracting topic/partition or container ID into structured fields, use the accessors provided by your deployed version.

Never confuse a "one partition paused" event with "all consumer partitions paused." Dashboards need explicit scope, such as `scope=container` or `scope=partition`.

## 13. Queue-threshold backpressure controller

A common strategy uses a **high-watermark** to pause and a **low-watermark** to resume.

Example:

- Queue capacity: 1,000 tasks.
- When queue size reaches 800: request pause.
- When queue size drops to 300: request resume.

The gap between the two thresholds creates **hysteresis**, preventing rapid pause/resume toggling when the queue hovers around a single threshold.

~~~text
Queue size
  1000 |             capacity
   800 |----- PAUSE threshold -----------
       |        /------ paused
   300 |----- RESUME threshold ----------
       |                    \--- resumed
     0 +--------------------------------> Time
~~~

### 13.1. Illustrative controller

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class QueueBackpressureController {

    private static final int PAUSE_AT = 800;
    private static final int RESUME_AT = 300;

    private final KafkaListenerEndpointRegistry registry;
    private final WorkQueueMetrics queueMetrics;
    private final AtomicBoolean pauseRequested =
        new AtomicBoolean(false);

    public QueueBackpressureController(
        KafkaListenerEndpointRegistry registry,
        WorkQueueMetrics queueMetrics
    ) {
        this.registry = registry;
        this.queueMetrics = queueMetrics;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void regulate() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        int pending = queueMetrics.pendingCount();

        if (pending >= PAUSE_AT &&
                pauseRequested.compareAndSet(false, true)) {
            container.pause();
        } else if (pending <= RESUME_AT &&
                pauseRequested.compareAndSet(true, false)) {
            container.resume();
        }
    }
}
~~~

Using `@Scheduled` requires enabling Spring scheduling appropriately, such as `@EnableScheduling`. `WorkQueueMetrics` is an illustrative application-provided abstraction measuring pending tasks; it is not a built-in Spring Kafka class.

**Important:** the example above is a starting point for a simple single instance, not a complete production state machine. `pauseRequested` reflects the controller's decision, not the consumer's actual state. Even after receiving `ConsumerPausedEvent` or `ConsumerResumedEvent`, verify the event matches the intended listener container and partitions.

### 13.2. Include a safety margin

When the controller measures queue size = 800 and requests pause, already-polled records or in-flight work may continue entering the queue before pause actually takes effect.

Therefore, the high-watermark must sit **far enough below capacity** to absorb in-flight items:

~~~text
Queue capacity = 1,000
Pause at       =   800
Safety margin  =   200 jobs
~~~

Base the margin on `max.poll.records`, concurrency, replica count, batch size, scheduler latency, and tasks submitted during transition. Do not copy 800/300 mechanically if your workload uses large batches or heavy bursts.

### 13.3. Ensure resume conditions are reachable

If the controller pauses because the queue is full while queue workers have died, queue size will never drop to the low-watermark. The container can stay paused for a very long time.

Add health checks, alerts, SLO timeouts, and operator intervention mechanisms. Never unconditionally resume while the database is still down just to clear a "paused" status; doing so can recreate overload.

## 14. Event callbacks are not for heavy business logic

A common mistake:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {
    database.recalculateLargeReport(); // Can block for a very long time
}
~~~

If the callback executes synchronously on the consumer thread, that call can keep the consumer from returning to `poll()` on time. Instead of observing pause, the event listener accidentally causes `max.poll.interval.ms` violations or destabilizes the group.

Safer approach:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {
    metrics.counter("kafka.consumer.pause.events").increment();
    log.info("Consumer paused partitions={}", event.getPartitions());
}
~~~

Heavy work should be offloaded to an independently managed service/scheduler with timeouts and durable queues where needed. If dispatching asynchronously, still manage ordering, thread safety, and lifecycle; never call `KafkaConsumer` directly from another event-consumer thread.

## 15. Using events as state confirmation

Suppose an operational REST API calls `container.pause()` and returns immediately.

If the API returns:

~~~json
{
  "status": "PAUSED"
}
~~~

right after the call without checking actual state, it may be inaccurate. At that instant, the container has only received the request.

A more accurate API can return:

~~~json
{
  "desiredState": "PAUSED",
  "observedState": "RUNNING",
  "note": "Pause requested; not yet observed"
}
~~~

Only after receiving `ConsumerPausedEvent` or confirming `isConsumerPaused()` does the observed state transition to `PAUSED`.

A minimal state machine:

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> PAUSE_REQUESTED: pause()
    PAUSE_REQUESTED --> PAUSED: ConsumerPausedEvent
    PAUSED --> RESUME_REQUESTED: resume()
    RESUME_REQUESTED --> RUNNING: ConsumerResumedEvent
    PAUSE_REQUESTED --> RESUME_REQUESTED: resume() before pause applied
    RESUME_REQUESTED --> PAUSE_REQUESTED: pause() before resume applied
~~~

This is a conceptual model. If stops, rebalances, consumer loss, startup failures, or multiple child containers occur, real state tracking may require extra branches and per-partition tracking.

### 15.1. ConcurrentMessageListenerContainer

When `concurrency > 1`, a parent container owns multiple child consumers. One child can finish pausing before another. If a dashboard wants to report the local group as paused, confirm all relevant child containers/partitions have paused rather than treating the first event as overall confirmation.

### 15.2. Filtering events for the right container

Spring application events can be received by many beans in the same `ApplicationContext`. When an application defines multiple `@KafkaListener`s, an observing handler receives events from different containers.

Filter by source/container ID or a deterministic event-to-container mapping supported by your Spring Kafka version. Otherwise, a pause on the `payments` listener could be misreported by the dashboard as `orders` pausing.

### 15.3. Synchronous vs. asynchronous events

When the multicaster dispatches events synchronously, observed callback order closely matches publish order on the consumer thread. Switching to an asynchronous multicaster can reorder delivery to UI/monitoring listeners due to thread scheduling.

Therefore, correlate **desired state**, **observed state**, and current container state instead of blindly relying on event timestamps to determine final state.

## 16. What happens to already-fetched records?

### 16.1. In-progress records do not disappear

Pausing prevents fetching/dispatching more records within scope, yet does not automatically roll back an executing database transaction.

~~~text
Consumer poll receives offsets 20, 21, 22
  |
  +-- listener processes 20
  |
  +-- controller calls pause()
  |
  +-- container may continue processing 21, 22
      before pause actually takes effect
~~~

That is why you must understand pause timing and `pauseImmediate`.

### 16.2. Retained records and memory

In certain container modes, records already polled but not yet dispatched may be retained in memory until resume. Memory footprint depends on record size, `max.poll.records`, concurrency, and active errors/retries.

Monitor heap/GC and do not treat pause as a way to buffer unbounded batches. If a memory queue is already near overflow, calling pause too late can still let the application OOM before pause takes effect.

### 16.3. Offset commits still follow successful-processing rules

Pause does not permit the container to commit offsets for unprocessed records. Completed records may commit per `AckMode`, while in-flight or unprocessed records must be managed consistently.

If the listener dispatches to its own executor thread and returns before the task finishes, the container may commit early under listener-return semantics; pause events cannot fix that bug.

## 17. Interactions with retries, error handlers, and DLTs

Pause/backpressure and retry/error handling serve two distinct objectives:

- **Pause/backpressure**: curbs intake of new workload when downstream is overloaded.
- **Retry**: decides how to reattempt a failed record.
- **DLT/recovery**: routes unprocessable records onto a recovery path.

Slow-database example:

1. A record fails with a timeout.
2. `DefaultErrorHandler` decides to retry per `BackOff`.
3. A controller sees the database connection pool saturating and calls `pause()`.
4. The container must coordinate retrying the failed record with pause state upon reaching the poll boundary.
5. Once downstream recovers and the controller calls `resume()`, the container continues dispatching per retry/ack semantics.

Pause does not replace error handlers. Never catch an exception in the listener and return success merely to "reduce errors" while the container is paused.

### 17.1. Blocking retries can still stall polling

If a listener or error handler blocks for a long time on the consumer thread, the container may not reach the pause application point. Bound listener duration, `BackOff`, and downstream calls; pause is a throttle mechanism, not an interrupt for an already-running blocking operation.

### 17.2. Non-blocking retries differ from pause

With non-blocking retries, failed records move to retry topics and resume processing after a delay. Pause suspends a container/topic subscription's consumer; it does not create retry topics, move records to a DLT, or schedule retries.

If long retries are needed while keeping the main topic moving, consider retry topics; if intake must halt due to shared overload, consider pausing. The two strategies have different scopes and need separate monitoring.

## 18. Multi-instance: pausing in one JVM does not pause another JVM

Suppose the `orders-service` group runs three pods:

~~~text
orders-service group
  Pod A: Listener container A
  Pod B: Listener container B
  Pod C: Listener container C
~~~

If a REST endpoint in Pod A calls:

~~~java
registry.getListenerContainer("orders-listener").pause();
~~~

it affects only **Pod A's** container. Pod B and Pod C keep reading their partitions. For a shared-database failure, load can remain too high.

To pause the whole service, use a control plane or shared configuration so each instance applies the policy to its local container:

~~~text
Shared policy: orders-consumption = PAUSE
    |
    +-- Pod A -> local container.pause()
    +-- Pod B -> local container.pause()
    +-- Pod C -> local container.pause()
~~~

To avoid split-brain state, the control system must observe confirmations from every instance, handle pod restarts/rebalances, and handle offline pods.

Never assume the Kafka group coordinator propagates a "pause command" across members. Kafka pause is a consumer/client operation, not a group state distributed automatically by Kafka.

## 19. Relationship with rebalances and partition assignments

While a container is paused, the consumer can still participate in a rebalance if:

- Another member joins or leaves the group.
- Topic partition count changes.
- Broker/group coordinator needs to change assignments.
- Consumer hits session timeout or poll interval violation.
- Group protocol or membership changes.

After a rebalance, assigned partitions can differ. Therefore, a prior `ConsumerPausedEvent` describes partitions paused **at the time of that event**, not an immutable contract that those partitions forever belong to the container.

Upon receiving new assignments, backpressure policies must be applied appropriately to new partitions if the container still holds a pause request. Inspect both requested state and new assignments, especially when using `pausePartition` on a specific partition list.

### 19.1. Pause and heartbeats

Normally the container keeps polling to maintain group membership; hence intentional pausing does not itself trigger session timeouts. However, if the JVM freezes or networking breaks, the group can still rebalance.

### 19.2. Pause and commits after revoke

A consumer that lost partition ownership must not attempt committing that partition's offsets as if it still owned it. Protect side effects via idempotency and manage in-flight tasks when rebalances occur.

### 19.3. Missing resume events on failure

If a container stops while paused or partitions are reassigned, do not assume every `ConsumerPausedEvent` has a matching `ConsumerResumedEvent` within the same lifecycle. Dashboards may need to observe `ContainerStoppedEvent` or refreshed container states so they do not display paused forever.

## 20. Monitoring container pause events

Metrics worth tracking:

| Metric / log | Purpose |
|---|---|
| Pause requested count | How many times the controller requested pause |
| `ConsumerPausedEvent` count | How many times the container executed pause |
| Resume requested count | How many times resume was requested |
| `ConsumerResumedEvent` count | How many times resume actually occurred |
| Pause duration | Length of effective pause intervals |
| Time from request to event | Latency to apply pause/resume |
| Paused partition count | Scope of paused partitions |
| Consumer lag by partition | Evaluate backlog growth while paused |
| Downstream queue utilization | Signal triggering backpressure |
| Database pool usage / API latency | Confirm downstream recovery |
| JVM heap/GC | Detect retained records or memory pressure |
| Rebalance count / commit failures | Distinguish pause from lost membership |

Not all of these metrics are emitted out of the box by Spring Kafka under exact names. Pause duration or request-to-event latency may require custom application instrumentation.

### 20.1. Metrics with safe cardinality

Attach labels such as application, listener ID, topic, pause reason, and outcome. Never use event IDs or business keys as metric labels because cardinality can grow unboundedly.

Record exact topic-partitions in structured logs/traces when investigating incidents. If partition counts are very large, consider aggregating in metrics to avoid excessive cardinality.

### 20.2. Avoid confusing rising lag with broken pause

While a consumer is paused, producers keep writing to Kafka. Rising lag is predictable. Alerts should evaluate:

- Is the pause intentional?
- Did queues/downstream recover while the container stayed paused?
- Is lag breaching processing deadlines or retention?
- Did pause duration breach SLO?
- Are there signs of consumer crash or stalled polling instead of a valid pause?

High lag alone does not prove pause is broken, though an endlessly prolonged pause is not an acceptable default state either.

## 21. Operational procedure when pausing is needed

A concise runbook:

1. Identify listener ID, group ID, instance, and topic-partitions.
2. Confirm the backpressure cause via queues, DB latency, HTTP errors, or memory.
3. Record baseline lag and processing rate.
4. Request `container.pause()` or `pausePartition(tp)` with the right scope.
5. Check `isPauseRequested()` to confirm the command was accepted.
6. Wait for/observe `ConsumerPausedEvent` or the container's actual paused state.
7. Monitor health, lag, retention budget, and downstream while paused.
8. When downstream has sufficient headroom, request resume.
9. Verify `ConsumerResumedEvent` and actual paused state returning to false.
10. Monitor lag drain rate, listener errors, and recurring backpressure.
11. If resume fails or the container stopped, investigate lifecycle/rebalances instead of looping resume endlessly.
12. Record reason, operator, pause duration, and outcome in the incident log.

When pausing for controlled maintenance, define a **pause expiration** criterion or alert if left forgotten too long. Never auto-resume against safety rules while downstream remains unready.

## 22. Testing container pause events

To validate behavior, use a test Kafka broker or an integration environment with dedicated topics/groups. Verify the lifecycle, not merely that `pause()` is callable.

### 22.1. Pausing a listener

1. Create a test topic with several partitions and a `@KafkaListener` with a clear ID.
2. Send a few records and confirm the listener received them.
3. Call `container.pause()` from a controller/test thread.
4. Confirm `isPauseRequested()` becomes true.
5. Wait for `ConsumerPausedEvent` or `isConsumerPaused()` to become true.
6. Send additional records.
7. Confirm the listener stops dispatching new records during effective pause (accounting for earlier polled records).
8. Call `container.resume()`.
9. Confirm `ConsumerResumedEvent` or paused state returning to false.
10. Confirm waiting records are processed and offsets advance per policy.

### 22.2. Pausing while polled records remain

1. Increase `max.poll.records` so one poll returns multiple records.
2. Have the listener process each record with a controlled delay.
3. Request pause mid-batch.
4. Observe how many records continue processing before the pause event.
5. Repeat with `pauseImmediate=true` on supporting versions.
6. Correlate event timestamps with in-flight records.

### 22.3. Pausing per partition

1. Create a topic with at least two partitions.
2. Call `pausePartition()` for one partition.
3. Wait for the partition pause event.
4. Send records to both paused and unpaused partitions.
5. Confirm the other partition keeps processing.
6. Resume the paused partition and confirm queued data resumes processing.

### 22.4. Multi-instance and rebalance

1. Run two consumer instances in the same group.
2. Pause one instance's container.
3. Confirm the other instance does not pause automatically.
4. Trigger a controlled rebalance.
5. Record new assignments and corresponding pause states.
6. Confirm backpressure policy stays accurate after reassignment.

### 22.5. Avoid tests relying only on fixed sleeps

`pause()` is applied asynchronously relative to the caller. In tests, wait for a state/callback with a timeout, using `CountDownLatch`, Awaitility, or polling `isConsumerPaused()`. Fixed millisecond sleeps easily produce flaky CI tests.

Tests must clean up final pause state; if sharing a consumer group across tests, remember to resume or stop the container cleanly per lifecycle so later tests are unaffected.

## 23. Common design mistakes

**Calling `pause()` and immediately treating the consumer as paused:** it is only a request; wait for the event or actual state.

**Listening to `ConsumerPausedEvent` while ignoring partitions/source:** multi-container applications can report incorrect status.

**Confusing `ConsumerPausedEvent` with `ListenerContainerIdleEvent`:** idle does not mean paused.

**Assuming pause stops Kafka producers:** producers keep writing; lag can increase.

**Assuming pause equals stop:** paused containers usually keep polling and preserve group membership.

**Expecting the handler to terminate right after `pause()`:** in-progress records are not canceled.

**Failing to account for already-polled records:** queues can keep growing during the transition window.

**Calling `KafkaConsumer.pause()` directly from external threads:** `KafkaConsumer` is not thread-safe; use container-level APIs.

**Putting heavy database logic inside `@EventListener`:** synchronous callbacks can block the consumer thread.

**Enabling `@Async` and accessing `KafkaConsumer` from events:** consumers must not be manipulated arbitrarily on other threads.

**Pausing one pod and assuming the whole group paused:** the registry controls only the local instance.

**Failing to resume when downstream recovers:** creates prolonged backlogs and retention risk.

**Skipping hysteresis:** minor queue oscillations cause continuous pause/resume flapping.

**Using pause instead of an error handler:** failed records still need retry/recovery/DLT.

**Using pause to fix overly long listener blocking:** the container may fail to reach a poll boundary to apply pause.

**Marking records successful before background tasks finish:** offsets can commit early; pause events do not fix this.

**Assuming a resume event always follows a pause event:** stops, rebalances, or lifecycle shifts can break one-to-one pairing expectations.

## 24. Quick decision table

| Context | Appropriate tool | Verification to observe |
|---|---|---|
| Shared database overloaded | Pause containers across relevant instances | `ConsumerPausedEvent`, lag, DB headroom |
| Only one hot partition | `pausePartition(tp)` | Partition pause event, other partitions advancing |
| Need brief halt while keeping group membership | `container.pause()` | Actual paused and heartbeat/group stability |
| Need full listener halt during deploy | `container.stop()` and lifecycle orchestration | Stopped event, group reassignment |
| Queue has high/low watermarks | Backpressure controller + hysteresis | Queue capacity, pause duration, resume |
| Need to stop right after current record | `pauseImmediate=true` if supported | In-flight records and retained memory |
| Record fails business rules | `DefaultErrorHandler` / retry / DLT | Retry attempts and recovery outcome |
| Need long retry delay while main topic advances | Retry topic for record listener when appropriate | Retry lag, DLT, ordering |
| Need to confirm pause actually took effect | `ConsumerPausedEvent` or `isConsumerPaused()` | Matching container and partition scope |
| Need to know if listener is idle vs. paused | Separate idle events from pause events | Container state and assignments |

## 25. Operational principles in production

- Use `KafkaListenerEndpointRegistry` and container-level `pause()/resume()` to control listeners; never touch `KafkaConsumer` from external threads.
- Separate **desired pause request** from **observed actual pause**; use `ConsumerPausedEvent` and `ConsumerResumedEvent` to record state transitions.
- With concurrent containers, track child consumers' and partitions' states rather than treating the first event as a full group pause.
- Separate container-wide pause from per-partition pause; scope events accurately.
- Understand pause does not cancel in-progress records and may not stop already-polled records.
- For faster reaction, consider `pauseImmediate` alongside memory bounds for retained records.
- Keep event listener callbacks brief so they never block the consumer thread.
- Use high/low watermarks and safety margins to curb oscillation and prevent queue overflow.
- Monitor consumer lag, pause duration, DB/HTTP headroom, and retention while paused.
- Ensure resume conditions, long-pause alerts, and recovery plans exist when containers stop/rebalance.
- In multi-replica apps, design distributed control if service-wide pausing is required.
- Never replace error handlers, idempotency, Kafka offset correctness, or transaction boundaries with pause.
- Test request-to-event timing, in-flight records, rebalances, and resumes in integration environments.

**Conclusion:** `ConsumerPausedEvent` and `ConsumerResumedEvent` enable Spring Kafka to inform applications when a listener container actually applies or lifts a pause. They are critical signals for building reliable backpressure: avoiding premature status reporting, observing exact partition scope, and bounding pause durations. Still, pause remains a consumption-lifecycle control, not a guarantee that every side effect has stopped, every record committed, or the group will never rebalance.
