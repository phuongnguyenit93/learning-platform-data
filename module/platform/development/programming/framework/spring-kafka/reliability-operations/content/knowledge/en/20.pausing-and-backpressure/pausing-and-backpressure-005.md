# Polling While the Container Is Paused

In **Spring Kafka**, a listener container can be **paused** to temporarily stop forwarding new Kafka records to the **@KafkaListener** method without completely stopping the consumer. Key point: **the container continues calling KafkaConsumer.poll() while paused**. These polls keep the consumer active with the Kafka broker and consumer group; they do not mean the listener continues receiving new records from paused partitions.

That behavior is the foundation of **backpressure**: when a database, HTTP API, thread pool, or memory is under overload, the application can temporarily stop taking on new work while still attempting to retain partition ownership for fast recovery after **resume()**.

Three things to distinguish right from the start:

1. **pause() is not stop()**: the container stays running and keeps polling.
2. **pause() is not acknowledgment or offset commit**: unprocessed records are not automatically confirmed.
3. **pause() does not immediately interrupt every running listener**: records already polled earlier may still be dispatched or retained depending on configuration.

This lesson explains the poll loop while paused, why group membership is preserved, where pause/resume takes effect, per-partition control, interactions with acks/transactions/retries, and how to operate backpressure safely.

## 1. Normal Kafka consumer polling

A consumer in a group normally operates in a loop:

~~~mermaid
flowchart TD
    A["Container RUNNING"] --> B["KafkaConsumer.poll()"]
    B --> C{"Any records?"}
    C -->|Yes| D["Invoke listener"]
    D --> E["Ack / commit per config"]
    E --> B
    C -->|No| F["Continue poll loop"]
    F --> B
~~~

In a single poll, the Kafka client does more than fetch records. It also participates in group coordination, assignment, heartbeat state, and internal processing. The Kafka client has a background heartbeat mechanism aligned with the group protocol, yet the application must still continue calling poll to meet progress requirements.

In particular, **max.poll.interval.ms** limits how long a consumer is allowed between poll calls under standard group management. If the listener stays blocked for too long before returning to poll, the consumer may lose timely liveness and trigger a group rebalance.

That is why using a long **Thread.sleep() inside the listener** to shed load is not equivalent to pausing the container.

## 2. What happens when container.pause() is called?

Spring Kafka provides **MessageListenerContainer.pause()** to request pausing all partitions managed by the container.

The pause command is typically invoked from a controller, scheduler, or downstream-monitoring service. The container records the request; the consumer thread applies the pause at an appropriate point in its processing loop.

~~~mermaid
flowchart TD
    A["Consumer polling and processing"] --> B["Controller calls pause()"]
    B --> C["Container records pause request"]
    C --> D["Consumer thread applies pause"]
    D --> E["Partitions are paused"]
    E --> F["poll() continues"]
    F --> G["No new records dispatched from paused partitions"]
    G --> F
    H["Controller calls resume()"] --> I["Consumer thread applies resume"]
    I --> J["Poll and dispatch continue"]
~~~

Once the pause takes effect, KafkaConsumer.poll() continues to be called so the consumer is not considered to have stopped polling. If all assigned partitions are paused, subsequent polls normally return no new records from them. If only some partitions are paused, poll can still return records from the remaining partitions.

A pause request can arrive while the listener is processing records from an older poll. Therefore, distinguish **pause request** from **actual pause applied by the consumer**.

## 3. Why poll when all partitions are paused?

A Kafka consumer group needs its members to keep participating in group management. If the consumer thread stops polling altogether while waiting on downstream, the application risks exceeding **max.poll.interval.ms**, leading to a rebalance and transferring partitions to another consumer.

A bad example:

~~~text
Downstream overloaded
  -> listener sleeps 10 minutes
  -> cannot return to poll during that time
  -> max.poll.interval.ms exceeded
  -> partitions may be revoked/reassigned
~~~

With Spring Kafka pause:

~~~text
Downstream overloaded
  -> container applies pause
  -> consumer thread keeps polling periodically
  -> fetches no new records from paused partitions
  -> can keep group membership stable
  -> resumes after downstream recovers
~~~

**Pause reduces the risk of rebalances caused by failing to poll**, but does not absolutely guarantee the consumer will never rebalance. Causes such as network failures, coordinator restarts, other members leaving the group, rolling deployments, or session timeouts can still change assignments.

Also do not confuse continued polling with the consumer doing business work. A consumer can poll steadily while having zero listener invocations during a pause.

## 4. KafkaConsumer.pause vs. Spring container.pause

The raw Kafka client provides APIs:

~~~java
consumer.pause(partitions);
consumer.resume(partitions);
~~~

They affect fetching for the `TopicPartition`s assigned to that `KafkaConsumer`. However, `KafkaConsumer` is generally **not thread-safe** to call arbitrarily across different threads.

In Spring Kafka, the container owns the consumer thread. Therefore, the standard approach is:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

container.pause();
container.resume();
~~~

Advantages of the container API:

- Dispatches the request in harmony with the framework-managed consumer loop.
- Avoids manipulating the raw `KafkaConsumer` from an HTTP thread or scheduler.
- Exposes requested/actual state observations.
- Emits pause/resume application events.
- Better compatibility with listener lifecycle, child containers, and container concurrency.

Only call raw `KafkaConsumer.pause()` directly if writing your own Kafka consumer loop or inside a callback specifically designed to run on the owning consumer thread, with clear knowledge of ownership.

## 5. Requested pause vs. actual paused

Spring Kafka distinguishes two phases:

| State | Meaning |
|---|---|
| **Pause requested** | Application called pause(); container has an active pause request |
| **Consumer paused** | Kafka consumer has actually been placed in the paused state by the container |
| **Resume requested** | Application called resume(); container needs to clear the pause |
| **Consumer resumed** | Consumer has applied resume and can fetch/dispatch again |

Example:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

container.pause();

boolean requested = container.isPauseRequested();
boolean actual = container.isConsumerPaused();
~~~

Right after `pause()`, the result may be:

~~~text
isPauseRequested() == true
isConsumerPaused()  == false
~~~

That alone does not prove an error. The container may still be processing already-polled records or has not yet reached the pause application point on the consumer thread.

Similarly, `resume()` returning does not mean the listener has immediately received the next record. Wait for the container to apply the resume and for a Kafka poll to have matching data.

For containers with concurrency greater than one, aggregate state must be interpreted across the child consumers. When needing per-partition observation, use the partition-specific APIs/events of your Spring Kafka version.

## 6. Controlling via KafkaListenerEndpointRegistry

A listener with a stable ID:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-processor"
    )
    public void onOrder(OrderEvent event) {
        service.handle(event);
    }
}
~~~

Control service:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class OrderConsumerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public OrderConsumerControlService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause() {
        findContainer().pause();
    }

    public void resume() {
        findContainer().resume();
    }

    public boolean pauseRequested() {
        return findContainer().isPauseRequested();
    }

    public boolean consumerPaused() {
        return findContainer().isConsumerPaused();
    }

    private MessageListenerContainer findContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException(
                    "Listener container is not registered"
            );
        }
        return container;
    }
}
~~~

The control service can be invoked by a health manager, an operator API, or a backpressure controller. When returning an HTTP response, report **PAUSE_REQUESTED** first, and report **PAUSED** only after observing actual state. Do not return "fully paused" immediately upon calling `pause()` if the consumer has not yet applied the command.

## 7. Container-wide pause vs. per-partition pause

Spring Kafka provides TopicPartition-level control APIs in supporting versions:

~~~java
import org.apache.kafka.common.TopicPartition;

MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

TopicPartition partition =
        new TopicPartition("orders.events", 2);

container.pausePartition(partition);

// Once this partition is no longer under backpressure:
container.resumePartition(partition);
~~~

Comparison:

| API | Scope | Use case |
|---|---|---|
| pause() | All partitions of the listener container | System-wide database pool overload |
| resume() | Clears the container-wide pause request | Shared dependency recovers |
| pausePartition(tp) | Single TopicPartition | Individual partition is throttled |
| resumePartition(tp) | Single TopicPartition | Hot partition is eligible again |
| stop() | Stops container lifecycle | Maintenance, shutdown, or config changes |

If `pausePartition(partition 2)` is called, **poll can still return records from partition 0, 1, or other unpaused partitions**. This is an important difference from container-wide pause.

Partition-level pause and container-level pause can coexist. Resuming one partition does not always override an active global pause request. Command ownership must be controlled to prevent premature resuming.

## 8. Polling when only some partitions are paused

Suppose a consumer is assigned partitions P0, P1, and P2:

~~~text
P0: RUNNING
P1: PAUSED
P2: RUNNING
~~~

KafkaConsumer.poll() is still invoked. Under Kafka client pause behavior, P1 stops delivering new records while paused; P0 and P2 can still supply records to the listener.

~~~mermaid
flowchart LR
    A["poll()"] --> P0["P0 active"]
    A --> P1["P1 paused"]
    A --> P2["P2 active"]
    P0 --> L["@KafkaListener"]
    P2 --> L
    P1 --> W["Wait for resume"]
~~~

If a record from P1 was already returned in the poll before partition pause was applied, it may still be in flight and processed/retained per configuration.

Do not infer a paused partition merely from a drop in record rate. Observe actual partition paused state/events or container diagnostic logs.

## 9. Records already polled before pause

Suppose a poll returns four records:

~~~text
orders.events-0, offsets 100, 101, 102, 103
Listener is processing offset 100
Controller calls pause()
~~~

The Kafka client has already handed all four records to the container. A pause requested afterward does not "recall" these records from memory.

Depending on Spring Kafka version and pause policy:

- The container may finish processing all records of the current poll before applying pause.
- Or with **pauseImmediate** supported, the container can pause after the currently processing record and retain the remaining records to dispatch upon resume.

Consequently, right after `container.pause()`, the listener **may still be called** for records fetched from the prior poll. Do not fire error alerts just because listener invocation count rises a few times right after a pause request.

To confirm actual pause, wait for the consumer paused state or an event reflecting that the container applied the pause.

## 10. pauseImmediate

In versions supporting **ContainerProperties.setPauseImmediate(true)**, you can change the pause application point to reduce the number of records continuing to be processed after a request.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setPauseImmediate(true);

    return factory;
}
~~~

When using this factory, `@KafkaListener` must declare `containerFactory="ordersFactory"` or the application must configure it as the appropriate default factory.

Comparison:

| Mode | Characteristics |
|---|---|
| Default pause | Typically waits to finish remaining records from the prior poll before pausing |
| pauseImmediate=true | Can pause after the current record, holding remaining records from the poll for processing after resume |

**pauseImmediate does not interrupt/cancel a running listener**. If the listener gets stuck in an overly long HTTP call, the container cannot return to the poll loop to apply the pause and still risks exceeding `max.poll.interval.ms`.

Verify the API of your deployed Spring Kafka version. In older versions, `pauseImmediate` may not exist yet.

## 11. pollTimeoutWhilePaused

In supporting Spring Kafka versions, **ContainerProperties.setPollTimeoutWhilePaused(long)** adjusts the poll timeout while the consumer is paused.

~~~java
factory.getContainerProperties()
        .setPollTimeoutWhilePaused(100L);
~~~

The illustrative value is in milliseconds. Some versions use a default around 100 ms while paused.

Distinct configurations:

| Configuration | Role |
|---|---|
| pollTimeout | Normal poll timeout |
| pollTimeoutWhilePaused | Poll timeout when paused |
| max.poll.interval.ms | Time limit between polls |
| heartbeat.interval.ms | Heartbeat cadence per group protocol/client |
| session.timeout.ms | Session liveness limit enforced by broker |

Poll timeout is not the same as the interval between polls or the duration a consumer remains paused. Setting `pollTimeoutWhilePaused` too low can spin the poll loop too frequently; setting it too high can slow resume responsiveness and affect version-specific poll mechanics. Measure poll rate, CPU, and pause/resume application time.

Do not implement backpressure by calling `Thread.sleep(pollTimeoutWhilePaused)` in the listener. While sleeping, the consumer thread is not polling.

## 12. max.poll.interval.ms: what pause helps with and what it does not

Suppose:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 200
~~~

`max.poll.interval.ms` equals five minutes. If the listener takes longer than five minutes to process one poll, it may fail to return to poll on time even if a controller sent a pause request from another thread.

Pause is effective when:

- The listener finishes its current work.
- The container consumer thread continues running.
- The pause is applied in the next poll cycle.
- Subsequent polls continue executing periodically.

Pause does not directly solve:

- Deadlocks inside the listener.
- HTTP clients without timeouts.
- Unbounded blocking `Future.get()` calls.
- Overly large batches whose processing before the next poll exceeds the limit.
- Severe consumer thread starvation.

Complementary measures include capping `max.poll.records`, reducing per-record processing time, setting timeouts, circuit breakers, controlling in-flight jobs, and using proper acknowledgment semantics for async processing.

## 13. Poll rate keeps climbing while the listener receives no records

When all partitions are paused:

~~~text
Container RUNNING: true
Pause requested: true
Consumer paused: true
Poll calls: continue
New data delivery: none from paused partitions
Listener processing: no further calls once drained/held in-flight
Consumer lag: may rise as producers keep sending
~~~

A dashboard looking only at **poll-rate** might see the consumer "still active" without understanding why **records-consumed-rate** dropped to zero. This is expected behavior when paused.

Conversely, **records-consumed-rate=0** does not prove the consumer is paused; the topic might have no records or the container might not have assigned partitions yet.

To diagnose accurately, combine poll metrics, pause requested/actual state, assigned partitions, consumer lag, and listener processing metrics.

## 14. Does pausing commit offsets?

No. **Pause is not a Kafka offset acknowledgment**.

Offset commits depend on the container `AckMode`, whether the listener succeeded, manual acks, and the transaction manager if present.

Example:

~~~text
Poll receives offsets 100, 101, 102
Listener successfully processed 100
Controller calls pause()
~~~

In that state:

- Offset 100 may be acked/committed per `AckMode`.
- Offsets 101, 102 may be processed before pause or retained per `pauseImmediate`.
- If 101 and 102 are not yet processed, they are not automatically treated as finished just because the container is paused.
- If the listener uses manual acks, pending acknowledgments must follow container policy.
- With Kafka transactions, pause does not call `commitTransaction` or `sendOffsetsToTransaction` on the listener's behalf.

Do not call `Consumer.commitSync()` from an arbitrary thread to "advance offsets" while paused. That can violate threading rules and checkpoint past unprocessed records.

## 15. Manual acknowledgment and async processing

An anti-pattern:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.handle(event));
    // Method returned, but async task has not finished yet.
}
~~~

If the container treats normal return as successful processing, offsets may be acked/committed before the task actually succeeds. When the task fails, Kafka will not necessarily redeliver the event.

Pause does not prevent this bug by itself.

When using async processing:

1. Only ack a record after side effects are durably complete.
2. Use manual acknowledgment or async listener support per version.
3. Ensure ack/offset ordering per partition.
4. Track in-flight counts and use a bounded executor queue.
5. Pause when in-flight exceeds a high watermark.
6. Resume when in-flight drops below a low watermark.
7. During shutdown/rebalance, handle pending tasks and offsets safely.

Spring Kafka includes **asyncAcks** in some versions: it supports out-of-order acknowledgments within a poll and includes a mechanism to temporarily pause receiving additional data when needed. Do not manually mix multiple pause layers with `asyncAcks` without clearly understanding pause ownership and when the container can resume.

## 16. Backpressure using hysteresis

The system can pause when backlog is high and resume when backlog is low:

~~~text
executor queue capacity = 1000
PAUSE_AT  = 800
RESUME_AT = 300
~~~

This is hysteresis: preventing the queue from oscillating around a single threshold and making the container pause/resume repeatedly.

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> PAUSE_REQUESTED: backlog >= 800
    PAUSE_REQUESTED --> PAUSED: pause applied
    PAUSED --> PAUSED: poll continues
    PAUSED --> RESUME_REQUESTED: backlog <= 300
    RESUME_REQUESTED --> RUNNING: resume applied
~~~

Choose thresholds based on executor queue, memory, database pool, and downstream capacity. The 800/300 example is illustrative only, not a recommended setting for every workload.

## 17. Example backpressure controller

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class BackpressureController {

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 300;

    private final KafkaListenerEndpointRegistry registry;
    private final AtomicBoolean requested = new AtomicBoolean();

    public BackpressureController(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void updateQueueDepth(int pendingTasks) {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return;
        }

        if (pendingTasks >= HIGH_WATERMARK
                && requested.compareAndSet(false, true)) {
            container.pause();
        } else if (pendingTasks <= LOW_WATERMARK
                && requested.compareAndSet(true, false)) {
            container.resume();
        }
    }
}
~~~

The code above illustrates only the **pause/resume control** part; it does not replace the acknowledgment mechanism for asynchronous business processing.

`AtomicBoolean` prevents issuing duplicate requests for the same reason. If multiple pause reasons can coexist, a single boolean is **not enough**: you need a shared pause-reason manager or state machine.

## 18. Multiple simultaneous pause reasons

Example:

~~~text
Pause reason A: DATABASE_POOL_EXHAUSTED
Pause reason B: PAYMENT_API_RATE_LIMIT
~~~

When the database pool recovers while the payment API is still rate limiting, the container must remain paused. If controller A calls `resume()` without checking B, the consumer will take more records and generate errors.

A flow-control service should manage a set of reasons:

~~~text
pauseReasons = {DATABASE_POOL, PAYMENT_API}
DATABASE_POOL resolved
pauseReasons = {PAYMENT_API}
=> remain paused

PAYMENT_API resolved
pauseReasons = {}
=> request resume
~~~

With multiple partitions, global pause reasons and partition-specific pause reasons should be managed separately. When an operator uses manual pause, the health manager must not auto-resume on dependency recovery while ignoring the operator's request.

If the system needs to survive restarts, define which pause states are runtime-only conditions and which are maintenance intents that must be persisted durably.

## 19. Pause/resume application events

Spring Kafka provides events to observe the pause/resume lifecycle in supporting versions:

- **ConsumerPausedEvent**
- **ConsumerResumedEvent**
- **ConsumerPartitionPausedEvent**
- **ConsumerPartitionResumedEvent**

Example:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerPauseEvents {

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused partitions={}",
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed partitions={}",
                event.getPartitions()
        );
    }
}
~~~

The `log` field must be declared by the class (e.g., SLF4J). Events may be published on the consumer thread context when the event multicaster is synchronous. Do not perform HTTP calls, database calls, or heavy blocking operations inside event callbacks.

Events show actual transitions; pause reasons may be managed by the application controller and attached to separate structured logs/metrics.

## 20. Pause and rebalance

While paused, the consumer can keep stable assignments because it still polls; however, rebalances can still happen for other reasons.

For example:

- Another replica joins the group.
- A rolling deployment causes a member to leave the group.
- Coordinator or network interruption.
- Session timeout.
- Partition metadata/assignment changes.

With per-partition pause, post-rebalance assignments may differ from before. Verify the pause status of each `TopicPartition` in the new assignment according to the API/version in use.

Operational procedure:

1. Monitor partition assigned/revoked events or container assignments.
2. Check which pause reasons remain active.
3. Verify actual pause on newly assigned partitions.
4. Ensure in-flight tasks for revoked partitions are handled/canceled per policy.
5. Do not auto-resume just because a rebalance finished if downstream has not recovered.

In large consumer groups, a partition may move to a different child container after rebalance; do not rely on old `KafkaConsumer` references to manage pauses.

## 21. Pause vs. stop, idle, seek, and retry

| Mechanism | Keeps polling? | Primary impact |
|---|---|---|
| **pause()** | Yes, while container thread is active | Stops fetching/dispatching new records from paused partitions |
| **resume()** | Yes | Allows processing to resume |
| **stop()** | Stops polling once stopped | Stops container, consumer leaves current lifecycle |
| **Idle** | Yes | Polls, but topic/assignment has no records |
| **seek()** | Yes if container is running | Changes partition read position |
| **DefaultErrorHandler retry** | Per container retry/backoff mechanism | Redelivers failed record, does not imply global pause |
| **@RetryableTopic** | Separate retry containers | Routes failed records to retry topics |

Pause is usually best for temporary backpressure. Stop fits shutdowns or maintenance. Seek is for controlled replay/offset recovery; pause does not rewind offsets automatically.

If using non-blocking retry topics, pausing the main listener does not implicitly pause all retry-topic listener containers and DLT consumers. Identify which containers share the overloaded downstream.

## 22. Impact on consumer lag

While the consumer is paused, producers can continue writing to Kafka. Committed offsets do not advance past unprocessed records, so **consumer lag increases**.

This is an acceptable consequence when protecting downstream, yet it must be bounded by SLAs:

- Short few-second pause: backlog can drain quickly.
- Multi-minute pause: lag/oldest record age rises, requires monitoring.
- Multi-hour pause: can affect retention and business SLAs.

Upon resuming, a consumer may drain backlog very quickly and overload downstream again. You need rate limiting, bounded processing, high/low watermarks, and tuned `max.poll.records`/concurrency based on capacity.

Do not use pause to hide a permanent error without an owner or alert. Pause buys time; it does not eliminate the records needing processing.

## 23. Pausing in a transactional listener

With a Kafka-aware transactional listener container, transaction boundaries are managed by the container and `KafkaTransactionManager`. Pause does not automatically:

- Commit or abort a Kafka transaction.
- Commit consumer offsets within the transaction.
- Roll back a database transaction.
- Delete already-sent output records.
- Replace `AfterRollbackProcessor`.

If the listener is executing inside a Kafka transaction and the controller requests pause, the current transaction must still finish via its normal or exception path before the container can apply pause at an appropriate point.

When the listener throws an exception, the transaction aborts and `AfterRollbackProcessor` can coordinate seek/redelivery/recovery. Pause does not fix a failed transaction and must not replace exception handling.

With database transactions inside the listener, keep transactions short so the consumer thread quickly returns to poll. A DB transaction stuck in deadlock or a long lock wait will not be resolved by calling pause once the listener is already blocked.

## 24. When is pause not enough to prevent overload?

A scenario:

~~~text
poll returned 500 records
listener pushed 500 jobs to executor
queue is full
controller calls pause
~~~

Pause stops accepting new records after being applied, but **does not cancel the 500 already-dispatched jobs**.

The system can still OOM or overload the database if:

- The queue is unbounded.
- Multiple other Kafka listeners also submit work to the same executor.
- The listener returns before async work completes and acks prematurely.
- Jobs lack timeouts/circuit breakers.
- Downstream has no capacity cap.

Complementary measures include bounded queues, in-flight limiters, idempotency, proper framework manual/async acks, retry/backoff, and measuring transaction duration. For data requiring ordering, take special care not to commit past unprocessed offsets.

## 25. Monitoring while the container is paused

A useful dashboard should combine:

| Metric | Meaning |
|---|---|
| pause_requested | Application requested pause |
| consumer_paused | Consumer is actually paused |
| pause_duration | How long work intake has been paused |
| pause_reason | Backpressure/maintenance reason |
| poll_rate | Poll loop remains active |
| records_consumed_rate | Actual records received |
| consumer_lag | Backlog in Kafka |
| oldest_unprocessed_age | Delay of the oldest record |
| listener_processing_duration | Whether any listener is blocked |
| executor_queue_depth | Backlog inside the application |
| database_pool_waiters | Wait time for DB connections |
| rebalance_count | Consumer group churn |

The `pause_*` metric names here are **suggested custom metrics**, not mandatory built-in Spring Kafka defaults. Distinguish application metrics, Spring container metrics, and Kafka client JMX/Micrometer metrics.

Only use bounded-cardinality tags such as service, listener ID, topic, environment, and pause reason. Never put event IDs, offsets, or customer IDs into metric tags.

## 26. Useful logs for diagnostics

Example:

~~~text
event=consumer_pause_requested
service=orders-service
listener_id=ordersListener
reason=DATABASE_POOL_SATURATED
queue_depth=850
pause_requested=true
consumer_paused=false
~~~

After actual pause:

~~~text
event=consumer_paused
listener_id=ordersListener
assigned_partitions=6
polling_continues=true
consumer_paused=true
~~~

After resume:

~~~text
event=consumer_resumed
listener_id=ordersListener
reason=ALL_PAUSE_REASONS_CLEARED
paused_duration_ms=12000
~~~

Logs are illustrative formats. When seeing poll-rate climb while listener throughput is zero, check pause state and reason before concluding the consumer is broken. When seeing lag climb, determine whether pause is intentional or the container is stalled by network/authorization/thread blocking.

## 27. Integration test: container keeps polling while paused

To test real semantics, use a Kafka broker from EmbeddedKafka or Testcontainers and a dedicated test consumer group.

Procedure:

1. Create a topic and start the listener container.
2. Wait for the listener to be assigned partitions.
3. Send a valid record and verify the listener processes it.
4. Call `container.pause()`.
5. Wait for `isConsumerPaused()` or `ConsumerPausedEvent`.
6. Send another record to the paused partition.
7. During the pause window, verify the listener has not processed the new record (after accounting for in-flight records).
8. Observe poll metrics or instrumentation showing the poll loop remains active.
9. Verify group membership is not lost solely from being paused in a stable test.
10. Call `container.resume()`.
11. Wait for the actual resumed state.
12. Verify the record sent while paused is processed after resume.
13. Verify acknowledgment/offset commits per policy.
14. Clean up consumer group/topic fixtures.

Do not check only `container.isRunning()`: running does not prove poll rate. If the goal is proving polling actually continues, observe Kafka client poll metrics or appropriate instrumentation.

Tests should use polling assertions with timeouts rather than relying on fixed `Thread.sleep` as a pass condition.

## 28. Integration test: pauseImmediate and already-polled records

A separate test should coordinate when a pause request occurs mid-poll across multiple records:

~~~text
Poll returns offsets 100, 101, 102, 103
Listener starts offset 100
Test requests pause while offset 100 is processing
~~~

With default pause, the container may finish all records from the poll before actually pausing. With `pauseImmediate` on supporting versions, pause can take effect after the current record and retain remaining records until resume.

Assertions:

- Listener is not interrupted uncontrollably.
- Actual pause state appears per policy.
- No records are lost.
- No acks advance past unfinished records.
- After resume, remaining records are processed under proper semantics.
- No unintended duplicate side effects are produced.

When concurrency is greater than one, monitor each child container and corresponding partition; do not infer solely from total invocation counts.

## 29. Integration test: pausePartition

With a topic of at least two partitions:

1. Wait for the container to be assigned P0 and P1 appropriately.
2. `pausePartition(P0)`.
3. Wait for partition P0 to be actually paused.
4. Send record A to P0 and record B to P1.
5. Verify B continues to be processed.
6. Verify A is not processed while P0 is paused.
7. `resumePartition(P0)`.
8. Verify A is processed.
9. Verify offsets and per-partition ordering.

The goal is proving **polling continues working for unpaused partitions**, not just observing container-level paused state.

## 30. Production pause/resume runbook

When downstream is overloaded and a Kafka listener must be paused temporarily:

1. Identify service, listener ID, consumer group, and assigned partitions.
2. Inspect consumer lag, oldest record age, processing duration, and in-flight count.
3. Determine whether global pause or partition-specific pause is needed.
4. Confirm this is temporary backpressure, not a shutdown.
5. Record pause reason and owner.
6. Call `container.pause()` or `pausePartition(tp)` via registry.
7. Wait for appropriate requested/actual paused states.
8. Observe whether records already fetched in the old poll are still processing.
9. Confirm the poll loop continues and no abnormal rebalances occur.
10. Monitor lag, pause duration, downstream health, and recovery metrics.
11. Once the dependency recovers, remove the exact pause reason.
12. Request resume only if no other reasons remain.
13. Wait for actual resumed state and check listener invocations/throughput.
14. Monitor lag drain rate, avoiding retry storms and re-overload.
15. Record pause duration, root cause, and actions to tune thresholds.

If the container is not running or has no assigned partitions, pause/resume may not produce the expected effect. Check lifecycle and errors before sending repeated commands.

## 31. Common misconceptions

**Pause will stop polling.** Incorrect: Spring Kafka containers keep polling to stay active with the consumer group.

**Pause is stop.** Incorrect: stop ends the lifecycle; pause keeps the container running.

**Calling pause() immediately stops all listener callbacks.** Records from the prior poll may continue processing, depending on `pauseImmediate`.

**pauseImmediate interrupts the current listener.** No: it only shifts the pause point to right after the current record.

**Poll-rate staying high means pause failed.** Continued polling is expected behavior; inspect actual paused state.

**Rising lag proves pause isn't working.** Rising lag can be the normal consequence of temporarily halting consumption.

**Pause commits offsets.** Pause does not ack/commit on behalf of the listener.

**Using a long Thread.sleep instead of pause.** Can exceed `max.poll.interval.ms` and trigger rebalances.

**KafkaConsumer.pause can be called from any thread.** No: `KafkaConsumer` has threading constraints; use the container API.

**Pausing one partition means pausing the whole consumer.** Other partitions can still fetch/deliver records.

**Pausing the main listener automatically pauses retry-topic consumers.** Each listener container has its own lifecycle.

**Resume always triggers an immediate callback.** There may be no records, partition pauses remaining, or changed assignments.

**Pause guarantees zero rebalances ever.** Rebalances can still occur due to group/network/other lifecycle events.

**Pause solves all async overload.** Already-dispatched in-flight tasks still exist; you need bounded capacity and proper acks.

## 32. Implementation checklist

**Container lifecycle**

- [ ] Listener ID is stable and controllable via registry.
- [ ] Distinguish pause requested vs. actual paused.
- [ ] Have a way to observe pause/resume events.
- [ ] Know version support for `pauseImmediate` and `pollTimeoutWhilePaused`.
- [ ] Distinguish global pause vs. per-`TopicPartition` pause.

**Polling and group management**

- [ ] `max.poll.interval.ms` fits listener processing duration.
- [ ] Do not sleep/block the consumer thread indefinitely.
- [ ] Know polling continues while paused and have metrics to observe it.
- [ ] Rebalances remain handled properly.
- [ ] Do not use poll-rate alone as proof of data processing.

**Backpressure and offsets**

- [ ] Have high/low thresholds and prevent flapping.
- [ ] Have bounded queues and in-flight limits.
- [ ] Do not ack before async work finishes.
- [ ] Do not commit past unprocessed offsets.
- [ ] Pause reasons are centrally managed.
- [ ] Have recovery logic after resume/restart.

**Operations**

- [ ] Dashboard shows pause duration, reason, consumer lag, and throughput.
- [ ] Alerts exist for prolonged pauses or breached record-age SLAs.
- [ ] Integration tests cover global pause, partition pause, and `pauseImmediate`.
- [ ] Tests cover resuming and processing records sent while paused.
- [ ] Tests cover listener blocking to distinguish pause from `max.poll.interval` expiry.

## 33. Conclusion

**Polling while the container is paused** is the mechanism allowing Spring Kafka to stop taking on more work from Kafka partitions in a controlled manner while **the `KafkaConsumer.poll()` loop continues**. Thus the consumer can normally retain group membership and resume processing quickly after resume, instead of causing rebalances merely because the application temporarily paused data intake.

To use it properly, distinguish **pause request** from **actual paused state**, understand that records from a prior poll may still be in flight, and know that **pauseImmediate** does not interrupt a running listener. Pause does not automatically ack, commit offsets, roll back transactions, or erase consumer lag. Nor does it replace designing bounded queues, idempotency, timeouts, and retries.

In production, control pause/resume via the Spring Kafka container, observe poll-rate alongside pause state and listener throughput, use hysteresis with pause reasons to avoid premature resuming, and test actual behavior with a Kafka broker. This enables the system to apply backpressure **without turning a temporary halt in record intake into stopping the entire consumer group**.
