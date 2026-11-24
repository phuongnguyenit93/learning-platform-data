# Resuming a Specific Partition

Within a consumer group, a single listener container may read from multiple partitions simultaneously. When one partition builds up a large backlog or the downstream system temporarily lacks capacity to process it, the application can pause just that partition and continue reading the remaining ones. Once processing capacity recovers, the application calls `resumePartition()` so the consumer resumes fetching records from that exact paused partition.

Spring Kafka provides the `pausePartition(TopicPartition)` and `resumePartition(TopicPartition)` APIs on `MessageListenerContainer`. These APIs allow partition-level control without stopping the entire listener container. `resumePartition()` requests the consumer to resume reading the partition once the container handles the next poll; it does not commit offsets on its own and does not reassign the partition to another consumer.

## 1. When do you need to resume a specific partition?

Suppose the `orders-listener` is reading four partitions of the `orders.events` topic. Partition 2 has many orders that need updates in a slow downstream system, while the other partitions are processing normally.

Instead of pausing the entire container, the application can pause just `orders.events-2`. Once downstream finishes draining the backlog, the application resumes partition 2 to continue reading.

```text
orders.events
  P0  ---> consumer keeps reading
  P1  ---> consumer keeps reading
  P2  ---> PAUSED ---- downstream backlog shrinks ----> RESUMED
  P3  ---> consumer keeps reading
```

Common scenarios:

- One partition has an asynchronous processing queue that is nearly full.
- A downstream service is rate-limiting ingestion for a specific key group or partition.
- One partition needs maintenance or controlled backlog drainage.
- The system wants to apply per-partition backpressure rather than halting the entire consumer.

If all partitions are affected by the same unavailable dependency, pausing the entire container may be more appropriate. If only one partition has a backlog, per-partition pause/resume lets the rest keep making progress.

## 2. Requirements and API versions

The `pausePartition()`, `resumePartition()`, `isPartitionPauseRequested()`, and `isPartitionPaused()` APIs have been available since Spring Kafka 2.7. They are exposed on `MessageListenerContainer` and can be used with the corresponding listener containers.

`TopicPartition` uniquely identifies a partition by topic name and partition number:

```java
import org.apache.kafka.common.TopicPartition;

TopicPartition partition = new TopicPartition("orders.events", 2);
```

Partition numbers start at `0`. Therefore, partition number 2 is the third partition of the topic.

The partition must be assigned to a consumer belonging to the listener container being controlled. Specify the correct listener ID, topic, and partition; do not assume partition 2 always belongs to a specific consumer because assignments can change after a rebalance.

## 3. Retrieving the listener container from the registry

For listeners declared with `@KafkaListener`, you can obtain the container via `KafkaListenerEndpointRegistry`. Set an explicit `id` on the annotation so the application has a stable identifier for control operations:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void consume(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Process order event.
    }
}
```

Control service retrieving the container by ID:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class PartitionControlService {

    private final KafkaListenerEndpointRegistry registry;

    PartitionControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer getContainer(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                    "Unknown Kafka listener: " + listenerId
            );
        }
        if (!container.isRunning()) {
            throw new IllegalStateException(
                    "Kafka listener is not running: " + listenerId
            );
        }
        return container;
    }
}
```

This example focuses on locating the container and checking its lifecycle state. A container declared directly as a bean rather than created via `@KafkaListener` may need to be injected and controlled directly, as it will not necessarily appear in the registry.

## 4. Pausing and resuming the right partition

When you need to pause a partition, call `pausePartition()`. When the backpressure condition clears, call `resumePartition()` with the same `TopicPartition`:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class OrderPartitionController {

    private final KafkaListenerEndpointRegistry registry;

    OrderPartitionController(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pausePartition(int partitionNumber) {
        MessageListenerContainer container = requireContainer("orders-listener");
        TopicPartition partition = new TopicPartition("orders.events", partitionNumber);
        container.pausePartition(partition);
    }

    public void resumePartition(int partitionNumber) {
        MessageListenerContainer container = requireContainer("orders-listener");
        TopicPartition partition = new TopicPartition("orders.events", partitionNumber);
        container.resumePartition(partition);
    }

    private MessageListenerContainer requireContainer(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        if (container == null || !container.isRunning()) {
            throw new IllegalStateException(
                    "Listener is missing or stopped: " + listenerId
            );
        }
        return container;
    }
}
```

In production, resolve the topic and partition from validated metadata rather than letting a public API accept arbitrary partition numbers. Also restrict which listener IDs are allowed to be controlled so an administrative request cannot accidentally pause the wrong data stream.

## 5. Pause request vs. actual paused state

`pausePartition()` is a request sent to the listener container. The container processes the request on the consumer thread at a poll boundary; therefore, the state does not necessarily change at the exact moment the method is called.

Two APIs help distinguish the state:

| API | Meaning |
|---|---|
| `isPartitionPauseRequested(partition)` | A pause request exists for this partition |
| `isPartitionPaused(partition)` | The partition is actually paused |

Verification example:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.MessageListenerContainer;

MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");
if (container == null) {
    throw new IllegalStateException("orders-listener was not found");
}

TopicPartition partition = new TopicPartition("orders.events", 2);

container.pausePartition(partition);

boolean requested = container.isPartitionPauseRequested(partition);
boolean paused = container.isPartitionPaused(partition);
```

Immediately after calling `pausePartition()`, `requested` may be `true` while `paused` is still `false`. Only after the consumer handles the next poll and the pause takes effect does `isPartitionPaused()` reflect the actual state.

After calling `resumePartition()`, monitor the resumed event or poll `isPartitionPaused()` until it returns `false`. Do not treat the method returning as proof that the partition has already started receiving new records.

## 6. Resuming a partition in ConcurrentMessageListenerContainer

When `@KafkaListener` uses `concurrency` greater than one, Spring Kafka creates a `ConcurrentMessageListenerContainer` as the parent container with multiple child containers. Each child consumer holds its own assignment.

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        concurrency = "3"
)
public void consume(String payload) {
    process(payload);
}
```

You can retrieve the parent container from the registry and call `pausePartition()` or `resumePartition()` on it. Spring Kafka coordinates the request to the child consumer currently owning the specified partition.

Do not assume `orders.events-2` always belongs to the consumer with suffix `-2` or child container index 2. The Kafka partition assignor determines assignments and they can change after a rebalance. For deeper inspection, use assignments and client ID metrics to identify which child consumer currently owns the partition.

## 7. Partition pause is not container pause

Spring Kafka provides both `pause()`/`resume()` for controlling the entire container and `pausePartition()`/`resumePartition()` for controlling a single partition:

| API | Scope | When to use |
|---|---|---|
| `pause()` | All partitions managed by the container | The entire listener needs to temporarily stop receiving records |
| `resume()` | Resumes all paused partitions in the container | The entire listener is ready to process again |
| `pausePartition(tp)` | One specific partition | Only one partition has a backlog or needs rate limiting |
| `resumePartition(tp)` | One specific partition | That partition is eligible to resume |

Pausing a partition does not move the assignment to another consumer. The partition stays with the consumer group member holding it; the consumer continues polling to maintain group liveness without fetching further records from the paused partition. Other partitions assigned to the consumer can still be read.

Because the partition remains assigned, lag on that partition may grow while paused. This is intentional backpressure behavior; monitor lag and pause duration to avoid holding a partition too long.

## 8. Pause/resume does not automatically commit offsets

Pausing or resuming only controls record fetching. It does not change committed offsets and does not automatically acknowledge processed records.

Offsets continue to be managed according to the listener container's acknowledgement mode and transaction configuration:

- Records finished before the pause may be committed according to `AckMode`.
- Records already polled or queued for processing prior to the pause may still be in-flight.
- When the partition resumes, the consumer continues reading from its current position and committed offset per Kafka/Spring Kafka semantics.
- With asynchronous processing, ensure commits never advance past incomplete records.

Do not call `commitSync()` or manually alter offsets just because you paused a partition. If you need to replay, reset offsets, or seek, use dedicated mechanisms and understand their impact on consumer group progress.

## 9. Pause takes effect at poll boundaries

`pausePartition()` is thread-safe, and the actual pause executes on the consumer thread before the next `poll()`. Likewise, `resumePartition()` takes effect after a poll according to the container lifecycle.

This has an important consequence: pausing does not cancel an active listener invocation and does not revoke records already polled before the pause took effect. If a single poll returned multiple records for the same partition, the container may still have to process the remaining records from that poll result depending on listener configuration.

With batch listeners or asynchronous processing, account for records already received prior to the pause. Pausing stops fetching new data in future polls; it does not drain queues or cancel submitted tasks.

## 10. Using pause/resume for per-partition backpressure

A common approach is tracking processing queue depth per partition. When the queue exceeds a high watermark, pause the corresponding partition. When the queue drops to a low watermark, resume the partition.

Example:

```java
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class PartitionBackpressureController {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionBackpressureController.class);

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 300;

    private final KafkaListenerEndpointRegistry registry;

    PartitionBackpressureController(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void onQueueDepth(
            String listenerId,
            TopicPartition partition,
            int queueDepth
    ) {
        MessageListenerContainer container = requireRunningContainer(listenerId);

        if (queueDepth >= HIGH_WATERMARK
                && !container.isPartitionPauseRequested(partition)
                && !container.isPartitionPaused(partition)) {
            container.pausePartition(partition);
            log.warn("Pause requested: partition={}, queueDepth={}", partition, queueDepth);
        } else if (queueDepth <= LOW_WATERMARK
                && (container.isPartitionPauseRequested(partition)
                    || container.isPartitionPaused(partition))) {
            container.resumePartition(partition);
            log.info("Resume requested: partition={}, queueDepth={}", partition, queueDepth);
        }
    }

    private MessageListenerContainer requireRunningContainer(String listenerId) {
        MessageListenerContainer container = registry.getListenerContainer(listenerId);
        if (container == null || !container.isRunning()) {
            throw new IllegalStateException("Listener is missing or stopped: " + listenerId);
        }
        return container;
    }
}
```

This example assumes queue depth is tracked separately per `TopicPartition` and a monitoring component calls `onQueueDepth()` whenever queue depth changes. High watermark 800 and low watermark 300 are illustrative numbers that should be tuned based on actual queue capacity and processing speed.

Two distinct thresholds provide hysteresis: the system does not repeatedly pause and resume when the queue oscillates around a single value. You can add a minimum stabilization window, cooldown, or transition rate limit to prevent thrashing.

The high watermark should sit far enough below the queue's hard limit to leave room for records already polled in the current batch and tasks submitted but not yet finished. If the queue only has a few slots left when sending the pause request, in-flight records can still overflow the queue before the pause takes effect.

## 11. Backpressure must coordinate with queues and async processing

If the listener receives records and submits tasks to an executor, pausing the partition when the queue fills is only part of the solution. The entire pipeline must be designed carefully:

1. Queues must have bounded capacity; an unbounded queue merely hides that downstream cannot keep up.
2. Track queue depth per partition or business flow to know precisely which partition is causing pressure.
3. Upon hitting the high watermark, request a partition pause before fetching more batches.
4. Wait for running tasks to complete and the queue to drop to the low watermark.
5. Resume the partition once the system has sufficient capacity.
6. Bound in-flight task counts and handle task failures before acknowledging offsets.

If multiple partitions share a single global queue, it can be hard to determine which partition to pause. If a queue belongs to a single partition, you can map `TopicPartition` directly to that queue.

Do not commit offsets right after submitting a task if the task is incomplete and business rules require successful processing before acknowledgment. If tasks complete out of order, maintain a mechanism to track contiguous completed offsets per partition; never commit past a pending record.

## 12. Observing pause/resume with application events

Spring Kafka emits events when the consumer pauses or resumes a partition:

- `ConsumerPartitionPausedEvent` is emitted when the partition is actually paused.
- `ConsumerPartitionResumedEvent` is emitted when the partition is resumed.

These events have been available since Spring Kafka 2.7 and are useful for logging, updating dashboards, or confirming that backpressure actions have taken effect.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;

@Component
class PartitionPauseEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionPauseEventObserver.class);

    @EventListener
    public void onPartitionPaused(ConsumerPartitionPausedEvent event) {
        log.info("Kafka partition paused: {}", event);
    }

    @EventListener
    public void onPartitionResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resumed: {}", event);
    }
}
```

With `ConcurrentMessageListenerContainer`, events may be emitted by a child container; the event also provides a reference to the parent container. Log listener ID, topic, and partition to correlate events with queue depth, consumer lag, and client ID.

Do not log only when sending the request. Pause/resume events confirm the consumer's actual state, whereas `isPartitionPauseRequested()` indicates the request has been registered.

## 13. Safe partition resume workflow

When downstream recovers, you can follow this sequence:

1. Identify the exact listener ID and paused `TopicPartition`.
2. Verify the listener container is still running and the partition still belongs to the appropriate assignment.
3. Confirm queue depth has stayed below the low watermark for a stabilization period.
4. Call `resumePartition(topicPartition)`.
5. Monitor `ConsumerPartitionResumedEvent` or wait for `isPartitionPaused()` to return `false`.
6. Observe record rate, queue depth, and consumer lag to confirm the partition is making progress.
7. If the queue exceeds the high watermark again, re-pause using the same policy.

If a partition was revoked due to a rebalance, the previous consumer is no longer the owner. After an assignment change, determine which container/consumer currently owns the partition before issuing further control actions. Never keep fixed assumptions about child consumers across rebalances.

Pausing a partition alone does not cause the consumer to leave the group or trigger a rebalance. The consumer keeps polling to maintain group membership; the partition stays assigned until another membership or assignment change occurs.

## 14. Testing partition pause/resume

Run integration tests against a Kafka broker or embedded broker to verify real container behavior:

- Send records to at least two partitions.
- Pause one partition and confirm it stops receiving new records once the pause takes effect.
- Confirm the remaining partition continues to be processed.
- Resume the paused partition and confirm the consumer resumes reading records.
- Verify `ConsumerPartitionPausedEvent` and `ConsumerPartitionResumedEvent`.
- Check `isPartitionPauseRequested()` and `isPartitionPaused()` at the corresponding stages.
- Confirm pausing does not trigger a rebalance solely from pausing the partition.
- Confirm offsets are still committed per `AckMode` and do not advance past unfinished async tasks.
- Run tests with `concurrency` greater than one to verify parent/child containers and assignments.

Do not merely mock `MessageListenerContainer` and conclude that backpressure works. Mocking is suitable for verifying the controller calls the right API; integration tests are what verify polling, events, and real consumer behavior with partitions.

## 15. Common mistakes

1. **Calling `resumePartition()` on the wrong listener ID.** The partition may belong to another container; identify the exact endpoint.
2. **Assuming the method returning means the partition has resumed.** Requests are processed at poll boundaries; observe events or actual state.
3. **Confusing partition pause with container pause.** `resumePartition()` only resumes one partition, while `resume()` affects the container scope.
4. **Assuming pausing moves the partition to another consumer.** The partition keeps its assignment in the group; lag may grow while paused.
5. **Assuming pausing automatically commits offsets.** Offsets still follow `AckMode`/transaction configuration.
6. **Assuming pausing discards already-polled records.** In-flight or queued records still need to be processed by design.
7. **Calling `KafkaConsumer.resume()` directly from business threads.** The consumer is not thread-safe; use the listener container's thread-safe API.
8. **Resuming while the queue is still high.** Backpressure loses effectiveness and the queue may refill immediately.
9. **Using a single threshold for pause/resume.** A queue oscillating around the threshold can trigger constant pause/resume cycling; use high/low watermarks.
10. **Not handling rebalances.** Assignments can change; re-identify the container currently owning the partition.

`resumePartition()` lets you restore consumption on a single partition without resuming the entire listener container. Use `KafkaListenerEndpointRegistry` to look up the right container, construct the exact `TopicPartition`, track both requested and actual state, and resume only when downstream has sufficient capacity. Combined with high/low watermarks, bounded queues, in-order offset handling, and application events, per-partition pause/resume becomes an observable and safely operable backpressure mechanism.

Official documentation: [Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html) and [MessageListenerContainer API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/listener/MessageListenerContainer.html).
