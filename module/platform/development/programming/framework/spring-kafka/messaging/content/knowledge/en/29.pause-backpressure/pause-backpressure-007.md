# Difference Between Pause and Stop

When downstream processing slows down or an application needs to temporarily halt receiving additional records, Spring Kafka provides two easily confused operations: `pause()` and `stop()`. Both stop the listener from processing new records for a period of time, but they have very different effects on the Kafka consumer, the poll loop, the consumer group, and how processing resumes.

`pause()` suspends fetching records from partitions while keeping the listener container and consumer active. The container continues polling to maintain consumer group liveness. `stop()` shuts down the container and closes the consumer; the consumer leaves the group, which can trigger a rebalance. Therefore, pause is suited for temporary backpressure, whereas stop is suited for ending or reconfiguring the listener lifecycle.

## 1. Distinguishing pause and stop

| Criterion | `pause()` | `stop()` |
| --- | --- | --- |
| Purpose | Temporarily stop receiving new records | Stop the listener container |
| Kafka consumer | Remains alive and continues polling | Closed when the container stops |
| Consumer group | Consumer maintains membership under normal operation | Consumer leaves the group; a rebalance may occur |
| Partition assignment | Typically retained during the pause | May be reassigned to another consumer |
| Offsets | Not committed merely by pausing; follows current AckMode | Committed offsets are preserved; uncommitted records may be redelivered upon startup |
| Resuming | Call `resume()` | Call `start()` to recreate/restart the consumer |
| Suitable scenarios | Downstream queue nearly full, short-term dependency overload | Disabling a subscription, maintenance, configuration changes, or application shutdown |

Pause is a temporary state of a running consumer. Stop is a container lifecycle change. Do not use stop/start as a routine load-throttling mechanism because leaving and rejoining the consumer group can trigger rebalances, shift partition assignments, and increase latency.

## 2. Pause keeps the poll loop active

When `pause()` is called, Spring Kafka instructs the container to pause the partitions being consumed. Pausing is applied on the consumer thread when the container handles the next poll; it does not abort an active listener invocation and cannot revoke records already delivered to the listener.

While paused, the container keeps calling `poll()` to keep the consumer alive and handle Kafka coordination events. Paused partitions return no new records to the listener, while the consumer maintains its connection and group membership as long as polling/heartbeats function normally.

This is crucial for backpressure. If a listener simply needs a breather so an internal queue can drain, pausing lets the consumer keep its current assignment. Once load decreases, calling `resume()` allows the container to continue receiving records from those partitions.

```text
RUNNING
   |
   | downstream queue nearly full
   v
PAUSE REQUESTED
   |
   | container applies pause before next poll
   v
PAUSED (consumer still polls, no new records delivered)
   |
   | queue drops to low threshold
   v
RESUME REQUESTED
   |
   | container applies resume
   v
RUNNING
```

Pause is not a new storage queue. Kafka continues retaining records in the topic per retention rules; the consumer simply stops fetching new records from paused partitions. During a prolonged pause, the consumer must still keep polling per configuration, and the system must monitor lag, retention, and downstream health.

## 3. Calling pause and resume via the listener container

For listeners declared with `@KafkaListener`, you can retrieve the container from `KafkaListenerEndpointRegistry` and control its lifecycle:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    OrderListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
```

The ID `orders-listener` must match the `id` of `@KafkaListener` or the registered endpoint. `pause()` and `resume()` are called on the container; never obtain `KafkaConsumer` and call it directly from another business thread. A Kafka consumer is not safe to manipulate arbitrarily across threads, whereas the container knows how to forward requests onto the proper consumer thread.

You can inspect both the pause request state and actual pause state using status APIs on `MessageListenerContainer`, such as `isPauseRequested()` and `isContainerPaused()` in supported versions. Submitting a pause request does not mean the container has finished applying it at the moment the method returns.

## 4. Pause the whole container or pause a single partition?

If only one partition has a slow downstream or a specific key group needs throttling, you can pause just that partition instead of halting the whole container. The `pausePartition(TopicPartition)` and `resumePartition(TopicPartition)` APIs are available on Spring Kafka versions supporting partition-level control.

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.MessageListenerContainer;

TopicPartition slowPartition = new TopicPartition("orders", 2);

MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null && container.isRunning()) {
    container.pausePartition(slowPartition);
}

// When downstream for this partition has recovered:
if (container != null && container.isRunning()) {
    container.resumePartition(slowPartition);
}
```

With `ConcurrentMessageListenerContainer`, one endpoint can manage multiple child containers/consumers. Verify how your Spring Kafka version applies full-container and partition-level pauses across child consumers. If a partition is not yet assigned to the container, pausing that partition may not take effect until an appropriate assignment occurs.

Pausing one partition lets the other partitions continue processing. However, if all partitions are paused, the result is effectively similar to pausing the entire container. Monitor per-partition lag so a partition does not remain paused too long without resuming.

## 5. Stop closes the consumer and affects the consumer group

When `stop()` is called, the listener container goes through its shutdown lifecycle. The consumer is woken from polling, the container stops processing, and the consumer is closed per Spring Kafka's shutdown sequence. When the consumer leaves the group, the coordinator can reassign its partitions to remaining or new consumers.

```java
public void stopOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");
    if (container != null && container.isRunning()) {
        container.stop();
    }
}

public void startOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");
    if (container != null && !container.isRunning()) {
        container.start();
    }
}
```

`stop()` keeps the registered endpoint/container in the registry so it can be started again later. If you want to permanently remove a dynamic listener endpoint from the registry, unregister it via the corresponding API after stopping the container. Stopping a listener declared with `@KafkaListener` does not automatically remove its bean or annotation from the application.

When started again with the same group ID, the consumer joins the group and resumes from committed offsets per configuration. Records already polled but uncommitted may be redelivered. With a new group ID, the consumer has no prior committed offsets and its starting position depends on `auto.offset.reset`.

Stopping can trigger rebalances and disrupt other consumers in the group. If you only need to temporarily pause record ingestion while waiting for downstream, pausing is usually far less disruptive.

## 6. Offsets and in-flight records

Pausing does not automatically acknowledge offsets. Records already processed by the listener are still committed according to the container's `AckMode`, transactions, and acknowledgment timing. Records sitting in an internal queue must also be treated as unfinished if the application merely enqueued them without durable persistence.

Stopping likewise does not guarantee all polled records are committed. The outcome depends on whether records finished processing, the acknowledgment mode, transactions, and how the container stopped. If records were not acknowledged before the consumer closed, Kafka can redeliver them once this consumer or another group member resumes.

| Record state | When paused | When stopped and restarted |
| --- | --- | --- |
| Processed and offset committed | Not re-read per committed offset | Continues after committed offset |
| Polled but listener not yet finished | No new records fetched; current record continues through processing flow | May be redelivered if offset is uncommitted |
| Processed by listener but uncommitted | Committed per current AckMode/transaction | May be redelivered after restart if commit did not complete |
| Paused before next poll | Remains in Kafka | New consumer reads from committed offset |

If a listener places records into an in-memory queue and returns normally, the container may commit offsets before workers finish processing. Neither pause nor stop fixes this automatically. Only acknowledge after work is durably stored, or use appropriate inbox/outbox, durable queues, and idempotency.

## 7. Using pause to implement backpressure

Backpressure regulates producer/consumer rates when downstream components cannot handle current load. A common pattern uses a bounded queue and two thresholds:

- **High watermark:** when the queue hits the high threshold, request pausing the consumer.
- **Low watermark:** when the queue drops to the low threshold, request resuming the consumer.

Two separate thresholds create hysteresis, preventing continuous pause/resume oscillation when queue depth fluctuates around a single value.

```java
import java.util.concurrent.BlockingQueue;
import org.springframework.kafka.listener.MessageListenerContainer;

class QueueBackpressureController {

    private final BlockingQueue<OrderCreated> queue;
    private final MessageListenerContainer container;
    private final int highWatermark;
    private final int lowWatermark;

    QueueBackpressureController(
            BlockingQueue<OrderCreated> queue,
            MessageListenerContainer container,
            int highWatermark,
            int lowWatermark) {
        this.queue = queue;
        this.container = container;
        this.highWatermark = highWatermark;
        this.lowWatermark = lowWatermark;
    }

    public void afterEnqueue() {
        if (queue.size() >= highWatermark && container.isRunning()) {
            container.pause();
        }
    }

    public void afterWorkCompleted() {
        if (queue.size() <= lowWatermark
                && container.isRunning()
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
```

This is an illustrative example; in real applications, the controller should manage containers by ID or be injected directly, while synchronizing pause/resume decisions if multiple workers update the queue concurrently. The listener should only call `afterEnqueue()` after the record is accepted into the queue. If `queue.offer()` fails, the listener must preserve the record via a retry/recovery mechanism or throw an exception for the container to handle; never return normally and lose the record.

Thresholds should be based on queue capacity, average processing speed, consumer count, and downstream recovery time. Monitor both queue depth and Kafka lag: a shrinking queue does not necessarily mean Kafka lag has decreased, and vice versa.

## 8. Avoiding common pitfalls with pause/resume

1. **Calling pause and expecting the container to be paused immediately.** Pause is a request applied on the consumer thread; observe actual pause state or corresponding events.
2. **Resuming on a condition without hysteresis.** A queue fluctuating around one threshold can trigger continuous pause/resume cycling; use high/low watermarks.
3. **Pausing while letting the queue grow unbounded.** Pause only stops fetching new records; queued work still needs processing and queues must be bounded.
4. **Using stop for routine load throttling.** Stop causes the consumer to leave the group and can trigger rebalances.
5. **Calling `KafkaConsumer.pause()` from a business thread.** Control via `MessageListenerContainer` so the container executes on the consumer thread.
6. **Assuming pause cancels in-flight records.** Active listener invocations are not aborted simply because pause was called.
7. **Returning from the listener after submitting async work without durable storage.** Offsets may be committed before the work completes.
8. **Lacking a recovery path if the application fails while paused.** Monitor pause state and establish recovery procedures if a controller stops mid-flight.

Do not use `Thread.sleep()` inside a listener to simulate pausing. A blocked listener thread can delay polling, exceed `max.poll.interval.ms`, and cause the consumer to be considered dead. Use the container's pause API for backpressure.

## 9. Lifecycle events and observing state

Spring Kafka emits events related to consumer pause/resume such as `ConsumerPausedEvent` and `ConsumerResumedEvent` in supported versions. You can use event listeners to update metrics or operational state. When monitoring, distinguish the pause request from the moment all consumers/partitions have actually paused.

Metrics to capture:

- Container state: running, pause requested, paused, or stopped.
- Pause duration and number of pause/resume transitions over a time window.
- Queue depth, queue capacity, and downstream processing times.
- Consumer lag by topic/partition.
- Count of records in progress and records waiting in internal queues.
- Rebalance counts, consumer restarts, and start/stop errors.

If a container stays paused beyond an operational threshold, trigger an alert and inspect downstream, queue workers, resume failures, or coordination issues. Do not auto-resume purely on a timer if downstream remains overloaded.

## 10. When to pause vs. when to stop

| Scenario | Choice | Reason |
| --- | --- | --- |
| Internal processing queue nearly full | Pause | Keeps consumer in the group and temporarily stops fetching new records |
| Downstream service briefly overloaded | Pause | Allows resuming on the same assignment after recovery |
| Only one partition is congested | Pause partition | Other partitions can continue processing |
| Disabling a tenant subscription | Stop or unregister | Ends container activity per lifecycle |
| Maintenance or changing consumer configuration | Stop then start again | Consumer must be recreated with new configuration |
| Application shutdown | Stop per lifecycle | Closes consumers and releases resources |
| Retrying failed records | Error handler/retry topic | Pausing the whole container does not replace per-record retry policies |

If you want to permanently halt a dynamic subscription, stop the container and unregister the endpoint when it no longer needs to restart. If you only want to wait for a system to recover, pause/resume is the better choice.

## 11. Testing pause and stop

Integration tests with Kafka should verify listener behavior, offsets, and consumer group dynamics:

1. Send multiple records, call pause, and verify the listener receives no new records once pause takes effect.
2. While paused, verify the consumer maintains liveness/polling and does not cause rebalances solely from pausing.
3. Call resume and verify the listener resumes receiving records from its current assignment.
4. Call stop and verify the container stops, the consumer leaves the group, and rebalances may occur.
5. Restart with the same group ID; verify the consumer continues from committed offsets and uncommitted records can be redelivered.
6. Test `AckMode` and transactions to verify which records commit when pause/stop occurs during active work.
7. Simulate the queue exceeding the high watermark and dropping below the low watermark; verify pause/resume is requested only at the exact thresholds.
8. Simulate downstream worker failures or enqueue failures; verify records are not acknowledged before being safely persisted.

## 12. Implementation checklist

- [ ] Use `pause()`/`resume()` for temporary backpressure and `stop()`/`start()` for lifecycle management.
- [ ] Control via `MessageListenerContainer` or the registry; never manipulate the consumer directly from other threads.
- [ ] Understand that pause applies on the consumer thread and does not abort active listener invocations.
- [ ] Use high/low watermarks to prevent continuous pause/resume cycling.
- [ ] Bound downstream queues and handle enqueue failures safely.
- [ ] Acknowledge offsets only when work is completed or durably persisted per design.
- [ ] Monitor pause duration, queue depth, Kafka lag, and rebalances.
- [ ] Have a recovery procedure if a container remains paused too long or fails to resume.
- [ ] Test pause/resume, stop/start, redelivery, and acknowledgments under realistic configurations.

Pause keeps the consumer and poll loop alive while temporarily suspending record delivery; stop terminates the consumer and alters group membership. Properly distinguishing the two helps applications control backpressure without causing unnecessary rebalances while preserving offsets and handling in-flight records per configured policy.
