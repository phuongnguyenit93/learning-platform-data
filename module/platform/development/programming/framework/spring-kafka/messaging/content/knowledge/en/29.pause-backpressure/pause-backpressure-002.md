# Resuming a Listener Container

In Spring Kafka, a listener container can be paused and resumed without destroying the consumer or leaving the consumer group. The `pause()` API requests the container to stop receiving additional records; the `resume()` API clears that request so the consumer can resume processing. This provides a way to throttle consumption flow when downstream is overloaded, internal queues are nearly full, or the system needs to temporarily halt processing for a period of time.

Pause/resume differs from stop/start. When a container is paused, the consumer remains part of the consumer group and the container continues polling to maintain liveness; paused partitions return no new records to the listener. When stopped, the consumer is closed and leaves the group, which can trigger a rebalance. Therefore, pause/resume is suitable for temporary throttling, whereas stop/start belongs to deployment and operational lifecycle management.

This lesson belongs to the **Pause and Backpressure** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-producing and event-consuming applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while also covering serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing to operate reliable messaging flows.

## 1. Pause and resume in a listener container

Spring Kafka provides the following APIs on the listener container:

- `pause()`: requests pausing the consumers managed by the container.
- `resume()`: requests resuming consumption.
- `isPauseRequested()`: checks whether the container has a pending pause request.
- `isConsumerPaused()`: checks whether the consumer has actually paused.
- `pausePartition(TopicPartition)`: requests pausing a single partition.
- `resumePartition(TopicPartition)`: requests resuming a single partition.
- `isPartitionPauseRequested(TopicPartition)` and `isPartitionPaused(TopicPartition)`: checks pause status per partition.

State transition example:

~~~text
RUNNING
   |
   | pause()
   v
PAUSE REQUESTED
   |
   | consumer thread applies pause
   v
PAUSED
   |
   | resume()
   v
RESUME REQUESTED
   |
   | consumer thread applies resume
   v
RUNNING
~~~

`pause()` and `resume()` are container control requests. The actual consumer API is invoked on the consumer thread managed by the container. The application can request pause/resume from a management thread, scheduler, or monitoring component without directly calling `KafkaConsumer` from external threads.

## 2. Retrieving a listener container via KafkaListenerEndpointRegistry

A listener declares a stable ID so the application can locate its container:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "order-events",
    groupId = "order-service"
)
public void onOrderEvent(OrderEvent event) {
    orderService.process(event);
}
~~~

Inject `KafkaListenerEndpointRegistry` and retrieve the container by ID:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public void pauseOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

`getListenerContainer(id)` returns the container registered with the matching ID or `null` if not found. In production applications, check for `null` and inspect lifecycle state before issuing control commands.

The `@KafkaListener` ID is the key used to manage the container. Do not rely on the listener class name or topic name to infer the ID; declaring an explicit ID makes operations and monitoring more stable.

## 3. Pause/resume vs. stop/start

These two API pairs serve different purposes:

| Operation | Consumer | Consumer group membership | Rebalance | Purpose |
| --- | --- | --- | --- | --- |
| pause/resume | Keeps consumer open; pauses/resumes receiving records | Retains membership while consumer continues polling on time | Normally does not trigger a rebalance solely from pausing | Backpressure, brief maintenance, load throttling |
| stop/start | Closes consumer and recreates it upon start | Leaves group and rejoins | Can occur | Shutdown, deployment, configuration changes, lifecycle |

Pausing does not erase offsets and does not reset the consumer position. Upon resuming, the consumer continues from its current position according to the committed position and any records already fetched but not yet processed depending on container semantics.

Stopping closes the consumer and releases resources. Upon starting, the consumer joins the group and receives assignments from the coordinator; partitions may be assigned to other members during that time.

Do not use stop/start as a routine backpressure switch if the goal is only to temporarily halt consumption. Repeatedly leaving and joining the group causes rebalances and increases coordination overhead.

## 4. Does pausing stop polling and heartbeats?

Pausing a listener container does not mean stopping the consumer thread. The container continues calling `poll()` in its loop to maintain liveness and membership; paused partitions simply return no new records to the listener.

This matters because a Kafka consumer must be polled within `max.poll.interval.ms`. When a container is paused properly, it keeps polling and the consumer can continue maintaining its group membership.

However, if a listener runs for too long or the thread blocks before the container can perform the next poll, pausing will not solve exceeding `max.poll.interval.ms`. Pausing also does not interrupt an executing listener or abort an HTTP request or database query that has already started.

Key distinctions:

- Pause: tells the consumer not to receive new records from paused partitions.
- Poll: the consumer loop continues running to maintain liveness.
- Heartbeat: the Kafka client maintains group membership according to the poll/heartbeat mechanism of the client version.
- Listener execution: currently running work is not forcibly paused.

Do not call `KafkaConsumer.pause()` or `KafkaConsumer.resume()` directly from application management threads. The consumer is not thread-safe; use the listener container API instead.

## 5. When does a pause request take effect?

`pause()` is requested from an application thread, but calling pause on the consumer happens on the consumer thread. Therefore, pausing does not necessarily interrupt the current poll or a running listener invocation immediately.

Under standard container behavior, the pause request is applied at the next poll boundary. Records already returned by the poll may still be waiting for dispatch or processing. For a record listener, the container may continue delivering records already received from the current poll before the pause state takes full effect; for a batch listener, the current batch has usually already been passed into a single invocation.

Some Spring Kafka versions provide a `pauseImmediate` option to change when the container pauses delivery of already-polled records, such as stopping after the current record instead of waiting to process all records from the poll. Check the API and semantics of your exact version before enabling this option.

Consequently, a backpressure queue must account for in-flight records and already-polled data. Do not set the high watermark equal to the exact maximum capacity of the queue if the listener can still receive additional records before the pause takes effect.

## 6. Resuming a listener container

Once the condition that triggered the container pause has been resolved, call `resume()` on the target container:

~~~java
public void resumeOrders() {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

    if (container == null) {
        throw new IllegalStateException(
            "Listener ordersListener not found"
        );
    }

    container.resume();
}
~~~

After resuming, the consumer thread applies the resumed state and continues receiving records in subsequent polls. There is no need to recreate the container or consumer group.

You can check both the requested state and the actual consumer state:

~~~java
public ListenerPauseStatus status(String listenerId) {
    MessageListenerContainer container =
        registry.getListenerContainer(listenerId);

    if (container == null) {
        return ListenerPauseStatus.NOT_FOUND;
    }

    if (container.isConsumerPaused()) {
        return ListenerPauseStatus.PAUSED;
    }

    if (container.isPauseRequested()) {
        return ListenerPauseStatus.PAUSE_REQUESTED;
    }

    return ListenerPauseStatus.RUNNING;
}
~~~

`isPauseRequested()` and `isConsumerPaused()` reflect two different points in time. A pause may have been requested without the consumer thread having applied it yet; monitoring should reflect this intermediate state rather than reporting fully paused immediately when the method is called.

## 7. Pausing and resuming per partition

When only a single partition has an issue, you can use partition-level APIs instead of pausing the entire listener container.

Example:

~~~java
public void pausePartition(
        String listenerId,
        TopicPartition topicPartition) {

    MessageListenerContainer container =
        registry.getListenerContainer(listenerId);

    if (container == null) {
        throw new IllegalArgumentException(
            "Listener not found: " + listenerId
        );
    }

    container.pausePartition(topicPartition);
}

public void resumePartition(
        String listenerId,
        TopicPartition topicPartition) {

    MessageListenerContainer container =
        registry.getListenerContainer(listenerId);

    if (container == null) {
        throw new IllegalArgumentException(
            "Listener not found: " + listenerId
        );
    }

    container.resumePartition(topicPartition);
}
~~~

Partition-level pausing is useful when one key/partition has a failing downstream dependency, data requiring investigation, or a different processing rate than other partitions. Other partitions can continue processing.

You must track assignments and rebalances. A partition is only consumed by the member currently holding its assignment; after a rebalance, pause state and partition ownership must be re-observed. Do not assume a partition always belongs to the same child consumer or the same pod.

## 8. ConcurrentMessageListenerContainer and multiple consumers

When a listener has concurrency greater than one, Spring Kafka creates a `ConcurrentMessageListenerContainer` managing multiple child containers, each with its own consumer.

Example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Calling `pause()` on the parent container retrieved from the registry applies the pause request to the consumers managed by that container. Calling `resume()` requests resuming the entire container according to its lifecycle.

For partition pausing, Spring Kafka locates the consumer managing that partition. Assignments can change during a rebalance; you need to handle cases where the partition is not currently assigned to the local member.

Avoid deriving child container IDs by manually concatenating suffixes unless necessary. Use the parent container and supported management APIs to avoid depending on the internal structure of concurrent containers.

## 9. What is backpressure and why is pause/resume needed?

Backpressure is a mechanism for regulating producer/consumer rates between components so downstream systems are not overwhelmed. In a Kafka consumer, a listener can receive records faster than a database, HTTP API, or worker pool can process them.

If consumption continues while downstream is slow:

- Internal queues grow continuously.
- Memory can be exhausted.
- Downstream requests time out or get rate-limited.
- Thread pools and connection pools become saturated.
- Processing latency increases and consumer lag can grow along with it.
- If the process crashes, unprocessed data may have to be re-read.

Pause/resume allows the listener container to temporarily stop receiving additional records when the system approaches overload and resume once the internal backlog shrinks.

~~~mermaid
flowchart TD
    A[Kafka records] --> B[Listener container]
    B --> C[Bounded work queue]
    C --> D[Worker pool]
    D --> E[Database or HTTP service]
    C --> F{Queue reaches high watermark?}
    F -->|Yes| G[Pause container]
    G --> H[Workers continue draining queue]
    H --> I{Queue drops to low watermark?}
    I -->|Yes| J[Resume container]
    J --> B
~~~

Pause/resume is a consumption flow-control signal. It does not replace bounded queues, concurrency limits, retries, or idempotency.

## 10. High watermark and low watermark

Do not pause and resume at the exact same threshold. If the queue fluctuates around a single value, the container may repeatedly pause and resume, causing flapping.

Use two thresholds:

- High watermark: when the queue reaches or exceeds this threshold, request a pause.
- Low watermark: only resume when the queue drops below a lower threshold.

Example for a queue with a capacity of 1,000 tasks:

| State | Condition | Action |
| --- | --- | --- |
| RUNNING | Queue from 0 to under 800 | Continue receiving records. |
| PAUSE REQUESTED | Queue reaches 800 | Call pause on container. |
| PAUSED | Queue still above 300 | Continue draining queue, do not receive more. |
| RESUME REQUESTED | Queue drops to 300 or below | Call resume on container. |

Thresholds must account for already-polled records, running listeners, and tasks currently being submitted to the queue. With multiple partitions or multiple consumers, overall queue capacity may differ from per-worker queues.

Add a minimum stabilization period or cooldown if load changes rapidly. Do not use `sleep` inside the listener to wait for the queue to drain, as it blocks the consumer thread and can cause poll interval issues.

## 11. BackpressureController pattern

Example controller monitoring queue depth and controlling the listener container:

~~~java
@Service
@RequiredArgsConstructor
public class BackpressureController {

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 300;

    private final KafkaListenerEndpointRegistry registry;

    public void updateQueueDepth(int queueDepth) {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container == null) {
            return;
        }

        if (queueDepth >= HIGH_WATERMARK
                && !container.isPauseRequested()) {
            container.pause();
            return;
        }

        if (queueDepth <= LOW_WATERMARK
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

This is an illustrative skeleton. In production, queue depth should come from the actual queue or a reliable metric; the controller should be invoked when depth changes or by a lightweight scheduler.

You must distinguish between pause requested and consumer paused. If multiple sources control the same container, one source might call resume while another still requires a pause. Manage pause reasons or use a state coordinator so the container only resumes when all pause conditions are cleared.

## 12. Avoiding conflicting pause controls across multiple components

A listener may need to pause for multiple reasons:

- The internal queue is nearly full.
- The downstream database is under maintenance.
- An HTTP API rate limit has been hit.
- An administrator requested a temporary halt.
- A circuit breaker is open.

If each component calls `pause()` and `resume()` directly, one component could resume the container while another pause reason still remains active.

Use a coordinator that stores the set of pause reasons:

~~~java
public enum PauseReason {
    QUEUE_FULL,
    DOWNSTREAM_UNAVAILABLE,
    RATE_LIMIT,
    OPERATOR_REQUEST
}
~~~

Rules:

1. Whenever any pause reason is present, the container must be paused.
2. Only when all pause reasons have been cleared may the container resume.
3. State updates must be thread-safe.
4. Log pause/resume reasons and change timestamps.
5. When the application restarts, re-evaluate state from actual health/queue status because in-memory pause state is not durable.

Do not let a shared boolean be overwritten by multiple independent control flows. A set of reasons explains why a container is paused and prevents premature resumption.
## 13. Events for observing pause/resume state

Spring Kafka publishes application events when a consumer actually pauses or resumes. Commonly used events include:

- `ConsumerPausedEvent`: the container's consumer has been paused.
- `ConsumerResumedEvent`: the container's consumer has been resumed.
- `ConsumerPartitionPausedEvent`: a partition has been paused.
- `ConsumerPartitionResumedEvent`: a partition has been resumed.

You can listen for them using a Spring event listener:

~~~java
@Component
@Slf4j
public class KafkaContainerEventListener {

    @EventListener
    public void onConsumerPaused(ConsumerPausedEvent event) {
        log.info("Kafka consumer paused: {}", event);
    }

    @EventListener
    public void onConsumerResumed(ConsumerResumedEvent event) {
        log.info("Kafka consumer resumed: {}", event);
    }

    @EventListener
    public void onPartitionPaused(ConsumerPartitionPausedEvent event) {
        log.info("Kafka partition paused: {}", event);
    }

    @EventListener
    public void onPartitionResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resumed: {}", event);
    }
}
~~~

These events are useful for recording metrics and confirming that the consumer has applied the pause/resume request. Do not treat calling `container.pause()` as proof that the consumer is paused; use events or `isConsumerPaused()` to observe the actual state.

Events may be published from the container's processing thread. Handlers should be short and avoid slow queries or synchronous HTTP calls. If external telemetry needs to be sent, offload it to an appropriate executor to avoid blocking the consumer thread.

## 14. Resuming once queue load decreases

The controller needs a signal that the queue has dropped below the low watermark. This can be called from a worker after completing a task or from a scheduler reading queue metrics.

Example update method:

~~~java
public void onWorkCompleted(int remainingQueueDepth) {
    backpressureController.updateQueueDepth(remainingQueueDepth);
}
~~~

If the queue is updated concurrently by multiple workers, depth must be read in a thread-safe manner. For queues that do not support exact snapshots, intentionally use approximate metrics with wide enough thresholds to avoid flapping.

Another way to organize this is to have the controller own both the queue and the pause state. When a worker dequeues an item, the controller updates the depth and decides whether to resume. This prevents multiple components from independently calculating and updating conflicting states.

Do not resume simply because one worker finishes. Verify that the queue has dropped below the low watermark and all pause reasons have been cleared.

## 15. Already-polled records and internal queues

Pausing prevents receiving new records in subsequent polls, but it does not discard data that has already been polled. This is critical when combining a listener with a queue or worker pool.

Suppose a poll returns 200 records. When the queue exceeds the high watermark at the 50th record, the container may still have to finish dispatching the remaining records from that poll before the pause takes effect, depending on the listener mode and `pauseImmediate` configuration. If the queue only has room for 10 more records, the remaining records can exceed the queue's capacity.

How to design for this:

- Use a bounded queue with headroom capacity for in-flight data.
- Set the high watermark below the actual capacity.
- Limit `max.poll.records` to control poll size.
- Limit worker pool concurrency and the number of active tasks.
- Track the number of records currently being processed by the listener outside the queue.
- Consider `pauseImmediate` if your version and listener mode support it, after thorough testing.

Do not use an unbounded queue hoping that pausing will protect memory. Pausing has application latency and cannot reclaim already-fetched records.

## 16. Ack and durability of asynchronous work

A common mistake is having the listener place a record into an in-memory queue and return immediately:

~~~java
@KafkaListener(topics = "order-events", groupId = "order-workers")
public void onOrderEvent(OrderEvent event) {
    workQueue.offer(event);
}
~~~

If the container commits the offset when the listener returns, Kafka may consider the record processed even though the worker has not finished. If the process crashes, items still in memory can be lost while the offset has already advanced.

Pause/resume does not fix this durability problem. You must clearly define when a record is considered accepted for processing responsibility:

- If processing synchronously inside the listener, let the listener return only after durable work completes.
- If handing off to a queue, acknowledge the offset only after the work is durably persisted or completed according to contract.
- If using manual acknowledgment for asynchronous workers, configure `AckMode` and async acknowledgment properly for your version; test ack ordering, rebalances, and shutdowns.
- If a durable queue is needed, use another Kafka topic, a database inbox/outbox, or a durable work queue instead of an in-memory queue.

Do not acknowledge immediately after enqueueing into a RAM queue if the application cannot tolerate losing work on process restart.

## 17. Pause and max.poll.interval.ms

Pausing a container does not replace controlling listener processing time. The Kafka consumer must continue polling within configured limits; if a listener blocks too long and the consumer misses polls, the group may treat the member as dead and trigger a rebalance.

Things to monitor:

- `max.poll.interval.ms`: maximum time allowed between polls.
- `max.poll.records`: maximum number of records returned in a single poll.
- Listener processing time per record/batch.
- Queue depth and number of in-flight tasks.
- Actual pause duration and wait time until resume.

If the listener performs long synchronous processing, increasing `max.poll.interval.ms` may be part of the solution, but it does not replace optimizing the work or limiting batch size. If using an asynchronous worker pool, design acknowledgment and in-flight limits separately.

In a properly paused state, the container keeps polling to keep the consumer alive. However, a thread stuck inside a listener cannot execute the poll loop simply because the application called pause from another thread.

## 18. Pausing when downstream fails or a circuit breaker opens

Pause/resume can work alongside a circuit breaker to reduce pressure on a failing dependency.

Example control flow:

1. The circuit breaker detects an error rate or timeout exceeding the threshold.
2. The backpressure coordinator adds the `DOWNSTREAM_UNAVAILABLE` pause reason.
3. The container pauses and stops receiving new records.
4. Current workers complete or fail according to the timeout/retry policy.
5. The circuit breaker transitions to half-open and allows a probe.
6. When the dependency recovers, the coordinator removes the pause reason.
7. If no other pause reasons remain, the container resumes.

Do not blindly pause all consumers if only one downstream service or one event type is affected. Separate listeners by workload or pause the appropriate partitions if the topology allows.

If downstream fails permanently due to malformed data, pausing the whole container only increases lag without resolving the root cause. For record-specific errors, use bounded retries, DLT, and poison-record handling.

## 19. Pause/resume via administrative API

You can expose pause/resume operations through an internal management service or actuator endpoint depending on your application architecture. If you do:

- Only allow principals with appropriate operational permissions.
- Do not expose consumer control endpoints publicly to the Internet.
- Validate the listener ID and partition before acting.
- Write audit logs capturing actor, reason, timestamp, and before/after state.
- Set a timeout or alert if a listener stays paused too long.
- Provide a safe resume operation in case operators forget to unpause.
- Do not return success merely for sending the request; distinguish REQUESTED from APPLIED.

For example, a service can expose pause and resume operations while the REST controller only checks permissions and delegates to the service. Do not let the controller access `KafkaConsumer` directly.

## 20. Pause state and application lifecycle

Pause state is managed in runtime memory by the listener container. It is not durable configuration stored on the Kafka broker. When a process restarts, the new container starts according to its lifecycle and initial configuration; the application must re-evaluate whether to pause based on queue state, dependency health, or external control state.

`resume()` is not `start()`. If a container has stopped, resuming does not start the consumer. Check `isRunning()` and use lifecycle start/stop appropriately.

During shutdown:

- Stop accepting new work according to lifecycle rules.
- Wait for running listeners/workers within an appropriate grace period.
- Handle acknowledgments according to contract.
- Do not mark in-memory queue items as completed if the work is not yet durable.
- Allow the container to close the consumer cleanly.

During startup, initialize queues/workers before the listener begins receiving records; if downstream is not ready yet, you can keep the container paused after startup or control it via readiness. There must be a mechanism to resume once dependencies are ready.

## 21. Monitoring and alerting on prolonged pauses

Pausing for too long increases consumer lag and can cause processing SLAs to be missed. Monitoring should include:

- Container state: running, pause requested, paused.
- Pause start timestamp and pause duration.
- Active pause reasons currently in effect.
- Queue depth, queue capacity, and in-flight worker count.
- Consumer lag by group/topic/partition.
- Count of pause/resume transitions over a time window.
- Downstream latency, error rate, and circuit breaker state.
- Partition-level pause state if used.
- Number of polled records not yet completed.

Set alerts when a container stays paused beyond expected durations, when the queue fails to drain despite being paused, or when consumer lag crosses a threshold. If pause/resume cycles happen continuously, review your high/low watermarks and worker throughput rather than increasing state-polling frequency.

## 22. Testing pause and resume

Integration tests should verify consumer state and record delivery against real Kafka or Embedded Kafka appropriate for your version.

Scenarios:

1. Start the listener container and verify records are processed.
2. Call pause and wait until the consumer is actually paused.
3. Send additional records while paused and verify the listener does not process them yet.
4. Call resume and verify pending records are subsequently processed.
5. Pause a single partition and verify other partitions continue processing.
6. Use a concurrent container and verify pausing the parent container applies to all child consumers.
7. Call pause while the current poll still has records and verify in-flight record counts match configuration.
8. Call resume when the container is stopped and verify it does not auto-start.
9. Simulate the queue reaching the high watermark and draining to the low watermark; verify no flapping occurs.
10. Verify that a listener handing off to a queue does not commit offsets before work becomes durable per contract.
11. Restart the application while paused and verify the startup policy restores the desired state.
12. Observe `ConsumerPausedEvent`/`ConsumerResumedEvent` if the application relies on them.

Use latches, Awaitility, or timed state conditions. Avoid fixed sleeps because when a pause takes effect depends on the consumer thread and poll cycle. Tests should distinguish pause requested from actual consumer paused state.

## 23. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Listener still receives a few records after calling pause | Records were already polled before pause took effect | Account for in-flight records, lower `max.poll.records`, or check `pauseImmediate` |
| Listener does not run after calling resume | Container is stopped, wrong listener ID, or consumer has not applied resume | Check registry, `isRunning()`, and pause state |
| Consumer leaves group during long pause | Consumer thread is blocked or polling cannot continue | Check listener duration and `max.poll.interval.ms` |
| Queue keeps growing after pause | In-flight records or listener still enqueueing already-polled data | Use a bounded queue and reserve space for poll batches |
| Work lost after restart | Listener committed offset after enqueueing to RAM | Use durable handoff or manual ack with proper semantics |
| Container resumes too early | Multiple components independently controlling pause | Use a pause reason coordinator |
| Continuous pause/resume | Single watermark or thresholds too close together | Use high/low watermarks and a cooldown |
| Pausing whole container affects healthy partitions | Using container pause instead of partition-level pause | Pause the specific partition when appropriate |
| Pause state lost after deployment | State exists only in runtime memory | Restore per policy from health/queue/control store |
| Missing actual pause metrics | Only logging when the API is called | Track consumer pause/resume events and actual state |

## 24. Operations checklist

Before taking pause/resume to production, confirm:

1. Listeners have stable IDs so the registry locates the right container.
2. Container APIs are used instead of calling `KafkaConsumer` from external threads.
3. Pause/resume is clearly distinguished from stop/start.
4. Pause timing across poll cycles and in-flight records is understood.
5. Queues have bounded capacity and high watermarks leave headroom.
6. Low watermarks are set lower than high watermarks.
7. A coordinator exists when multiple reasons can trigger a pause.
8. Consumer threads keep polling and listeners do not block too long.
9. `max.poll.interval.ms` and `max.poll.records` fit the workload.
10. Acknowledgments are not issued before work meets the durability contract.
11. Partition-level pause is used when only one partition needs throttling.
12. Concurrent containers are managed through the parent container or supported APIs.
13. Pause/resume events and durations are observed.
14. Alerts are configured for prolonged pauses or growing lag.
15. Startup/shutdown policies define how pause state is recovered.
16. Integration tests cover pause, resume, in-flight records, queues, and restarts.

`resume()` continues consumption on a paused listener container; it does not create a new consumer and does not replace lifecycle `start()`. Combining pause/resume with bounded queues, high/low watermarks, and a pause reason coordinator lets you throttle load while keeping consumers in the group. To avoid losing work, account for already-polled records, acknowledgments, processing threads, and queue durability before using pause as a backpressure mechanism.



