# Pause Listener Container

In Spring Kafka, **pausing a listener container** is the mechanism of temporarily halting the delivery of additional records to the listener while the container and Kafka consumer remain running. An application can call `pause()` when a database or supporting API is overloaded, and then call `resume()` when the system has sufficient capacity to continue processing. This is an important tool for implementing **backpressure**: reducing the intake rate from Kafka instead of letting thousands of concurrent operations put pressure on downstream systems.

Key point to understand: **pause is not stop, is not retry, and does not mean the current record has been processed successfully**. The container remains running and typically continues calling `poll()` to maintain consumer group membership. Records already delivered to the listener or already polled before the pause request may still be processing. Offsets and business side effects must continue to be managed according to the active ack mode, error handler, and transaction configuration.

## 1. Why is pause needed in a system with backpressure?

Suppose the `orders` topic receives 2,000 events/second. The consumer writes results to a database, but the connection pool can only handle 500 writes/second while the database is experiencing an incident. If the listener continues receiving records without throttling:

- The number of requests waiting for a connection increases, causing timeouts or thread starvation.
- Transient errors occur en masse and trigger retries, creating even more load.
- The consumer risks holding the processing thread for too long, affecting `max.poll.interval.ms`.
- Downstream queues or executors can grow unboundedly and lead to OOM.
- Records get routed to the DLT en masse even though they could have succeeded once the database recovered.

Pause allows temporarily reducing intake at the source, while new records continue to be retained by the Kafka broker according to the retention policy.

~~~mermaid
flowchart LR
    K["Kafka orders topic"] --> C["Spring Kafka listener container"]
    C --> L["Business listener"]
    L --> DB["Database / HTTP downstream"]
    DB --> M{"Does downstream still have capacity?"}
    M -->|No| P["Request container pause"]
    M -->|Yes| R["Resume container"]
    P -. "Consumer still polls" .-> C
    R -. "Continue processing backlog" .-> C
~~~

This is **intake-halting** backpressure. It does not automatically scale the database, does not transfer partitions to another consumer, and does not automatically recover failed data.

## 2. How does pause differ from stop?

| Criterion | `pause()` | `stop()` |
|---|---|---|
| Container lifecycle | Still running | Stops the container |
| Consumer poll loop | Continues polling per container mechanism | Ends once stop completes |
| Consumer group | Typically retains membership by continuing to poll | Consumer may leave the group, triggering reassignment |
| Partition assignment | Does not release partitions solely due to pause | Partitions may be reassigned by the group |
| Record delivery to listener | Temporarily halted after pause takes effect | Terminates when the container stops |
| Continuation | `resume()` | `start()` |
| Purpose | Backpressure or short-term suspension | Shutdown, deployment, lifecycle termination |

Pause is not a **failover** mechanism. If pod A is paused while still holding partition 2, pod B in the same group does not automatically take over partition 2 just because pod A is paused. If you want to shift workload to another member, you need to consider lifecycle/rebalance with an explicit strategy.

## 3. The pause/resume API of MessageListenerContainer

Listener containers in Spring Kafka provide the control API:

~~~java
container.pause();
container.resume();

boolean requested = container.isPauseRequested();
boolean effective = container.isConsumerPaused();
~~~

These two states are different:

- `isPauseRequested()` indicates that a pause has been requested.
- `isConsumerPaused()` indicates that the consumer has applied the pause; with a concurrent container, you need to understand the aggregated state of the child consumers.

Calling `pause()` does not necessarily stop every listener invocation immediately. The container receives the request and applies it at a safe point in the poll/dispatch cycle. At that moment, records that have already been polled may still be waiting to be processed.

~~~text
T0  poll() returns records
T1  listener begins processing record A
T2  operator calls pause()
T3  isPauseRequested() = true
T4  listener may finish already-delivered record/batch
T5  consumer actually pauses partitions
T6  isConsumerPaused() = true
T7  poll continues but does not dispatch more paused records
T8  operator calls resume()
T9  consumer resumes processing from the corresponding position
~~~

Therefore, operations systems must distinguish between **pause requested** and **actually paused**. If the goal is to alter a database schema while no transactions are running, you must track in-flight work separately; simply seeing `pause()` return is not enough.

## 4. The consumer still polls while paused

A Kafka consumer must continue participating in the group lifecycle. Calling `Thread.sleep(120_000)` inside a listener to "rest for two minutes" is not equivalent to pausing the container. If the application fails to poll for too long, it can exceed `max.poll.interval.ms` and be considered failing to make polling progress, leading to a rebalance.

Spring Kafka container pause uses the Kafka consumer's pause/resume capability while still actively polling to maintain membership.

~~~text
RUNNING
  poll -> process -> poll -> process -> poll

PAUSED
  poll -> no records from paused partitions -> poll -> poll

BLOCKED THREAD (do not use instead of pause)
  poll -> Thread.sleep too long -> misses next poll
~~~

Pause helps avoid one cause of rebalance, but **it does not guarantee the consumer group will never rebalance**. Network outages, broker/coordinator issues, member joins/leaves, and other scenarios can still change partition assignments.

## 5. Identifying the listener to control the right container

A listener with a stable `id`:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-projection")
    public void onMessage(OrderEvent event) {
        orderService.apply(event);
    }
}
~~~

`KafkaListenerEndpointRegistry` manages containers created via `@KafkaListener`. The registry only holds containers in the **current JVM**. If the service runs five pods, calling the registry on one pod only controls the container on that pod; pausing the entire consumer group requires coordinating all relevant instances.

For manually created containers, the application can hold a direct reference to the container instead of looking it up in the registry.

## 6. Pause and resume service using KafkaListenerEndpointRegistry

Java example:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaIntakeControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaIntakeControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        require("orders-listener").pause();
    }

    public void resumeOrders() {
        require("orders-listener").resume();
    }

    public String ordersStatus() {
        MessageListenerContainer container = require("orders-listener");

        if (!container.isRunning()) {
            return "STOPPED";
        }
        if (container.isConsumerPaused()) {
            return "PAUSED";
        }
        if (container.isPauseRequested()) {
            return "PAUSE_REQUESTED";
        }
        return "RUNNING";
    }

    private MessageListenerContainer require(String id) {
        MessageListenerContainer container = registry.getListenerContainer(id);
        if (container == null) {
            throw new IllegalArgumentException(
                "Kafka container not registered: " + id
            );
        }
        return container;
    }
}
~~~

This is an in-application control API. If exposed over HTTP, actuator, or an admin command, it requires authentication, authorization, and auditing. Do not expose a public endpoint that allows anyone to pause the entire consumer group, because doing so can grow backlog and violate SLOs.

When a container is `STOPPED`, calling `resume()` does not replace `start()`. `resume` only has meaning within the pause mechanism of a running container.

## 7. A pause request may not take effect immediately

Spring Kafka has a gap between when an operator calls pause and when the consumer thread applies it:

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant C as Listener container
    participant L as Listener
    participant K as Kafka consumer
    K-->>C: Poll records
    C->>L: Process record A
    O->>C: pause()
    Note over C: isPauseRequested = true
    L-->>C: Complete in-progress record
    C->>K: Pause assigned partitions
    Note over C: isConsumerPaused = true
    O->>C: resume()
    C->>K: Resume partitions
~~~

With high concurrency, multiple child consumers may apply the pause at different times. If you need to measure "fully paused," observe the effective state and container application events, rather than just recording a single method call.

Pause also does not interrupt an already-open DB transaction or an in-flight HTTP request. For maintenance that requires draining in-flight work, measure the count of incomplete operations before proceeding to the maintenance step.

## 8. The pauseImmediate property

In Spring Kafka versions that support `ContainerProperties#setPauseImmediate`, you can request pausing after processing the **current record**, rather than finishing all records from the previous poll before pausing.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setPauseImmediate(true);
    return factory;
}
~~~

With `pauseImmediate = true`, the number of records that begin processing after a pause request can be lower, especially when `max.poll.records` is large.

However:

- The record currently being processed by the listener is not automatically canceled.
- Pause does not roll back the current DB transaction.
- With a batch listener, semantics differ from a record listener because the method can receive an entire batch.
- Already-fetched records remain managed by the container; pause does not make them disappear.

Before using it, verify the API and behavior against your project's Spring Kafka version.

## 9. Pausing a single partition instead of the entire container

There are cases where only one partition needs to wait while other partitions can still be processed. Supporting versions of Spring Kafka provide a partition-level pause/resume API:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container == null) {
    throw new IllegalStateException("orders-listener not found");
}

TopicPartition target = new TopicPartition("orders", 2);

container.pausePartition(target);

// When downstream for this partition recovers:
container.resumePartition(target);
~~~

Keep in mind:

1. The container must hold the appropriate assignment to pause the intended partition.
2. With a concurrent container, a specific child consumer owns that partition.
3. A rebalance can change assignments; how pause is preserved or re-requested depends on the API and version.
4. If a business tenant has records spread across multiple partitions, pausing one partition is not enough to halt that tenant.
5. Consumer lag for the paused partition must be monitored separately.

Do not use partition pause as a security ACL or a guarantee to completely halt processing for a business key when a producer might send the same key to multiple partitions due to a partition strategy change.

## 10. Automatic backpressure based on downstream health

A common pattern is a periodic control loop that checks connection pools and queue depth, then pauses/resumes the listener:

~~~java
@Component
public class KafkaBackpressureMonitor {

    private final KafkaListenerEndpointRegistry registry;
    private final DependencyCapacityProbe capacityProbe;

    public KafkaBackpressureMonitor(
            KafkaListenerEndpointRegistry registry,
            DependencyCapacityProbe capacityProbe) {
        this.registry = registry;
        this.capacityProbe = capacityProbe;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void reconcile() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        boolean canConsume = capacityProbe.canAcceptMoreWork();

        if (!canConsume && !container.isPauseRequested()) {
            container.pause();
        } else if (canConsume && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

In this example:

- `DependencyCapacityProbe` is an application-defined interface.
- `@Scheduled` requires scheduling to be enabled via `@EnableScheduling` in configuration.
- The listener does not sleep to wait for the database.
- The scheduler control does not block the consumer thread.

A production control loop needs **hysteresis**. For example, pause when downstream queue depth exceeds 5,000 for 10 seconds, but only resume when the queue stays below 1,000 continuously for 30 seconds. These thresholds are illustrative only; measure actual capacity to choose yours.

Do not use the same threshold for both pause and resume, causing the application to oscillate continuously between the two states. This phenomenon is called pause/resume flapping and can make throughput unpredictable.

## 11. Manual pause and auto pause need clear precedence

A dangerous design: an operator pauses for database maintenance, but the health monitor sees the database as "healthy" and calls resume on its own. As a result, intake restarts before maintenance is complete.

You can manage **pause reasons** in a control plane:

~~~text
Pause reasons:
  MANUAL_MAINTENANCE
  DATABASE_OVERLOADED
  DOWNSTREAM_CIRCUIT_OPEN
  RATE_LIMIT_EXCEEDED

If at least one active reason remains -> keep paused.
Only resume when all reasons have been cleared.
~~~

This is application orchestration logic, not a built-in idempotent pause-reason mechanism across all Spring Kafka versions. Control state must be stored in an appropriate place so a scheduler does not accidentally override an operator's decision.

With multiple pods, the control system needs to distribute or synchronize commands per instance; a single JVM registry does not affect other JVMs.

## 12. Pause does not replace retry and error handlers

A serious mistake is catching an exception in the listener, calling pause, and then returning normally:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    } catch (DatabaseUnavailableException ex) {
        intakeControl.pauseOrders();
        // Wrong if returning normally when the DB write has not completed.
    }
}
~~~

In this situation, the container may treat the record as successfully processed and commit its offset. Pause does not reverse that.

To signal that the record has not finished processing:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    } catch (DatabaseUnavailableException ex) {
        intakeControl.pauseOrders();
        throw ex; // Propagate error to Kafka error handling.
    }
}
~~~

Note: this code snippet is illustrative; manually pausing while the error handler wants to retry can create complex interactions. The backpressure monitor and retry mechanism must be aligned so failed records are not held indefinitely.

For a poison record or malformed payload, pausing the entire container is usually inappropriate: that record will not become valid over time. Classify it as non-retryable and handle it via DLT/quarantine. Pause is appropriate when the **overall processing capacity** of a dependency is lacking.

## 13. Pause and error-handler backoff

`DefaultErrorHandler` can retry a record with a `BackOff`. For long wait intervals, Spring Kafka provides `ContainerPausingBackOffHandler` in compatible versions to coordinate pausing/resuming the container rather than merely keeping the consumer thread sleeping for a long time.

Concept:

~~~text
Listener processes record A -> exception
    |
    v
Error handler calculates backoff
    |
    v
Container-pausing backoff
    |
    +--> Pause container / poll to maintain membership
    |
    +--> Due -> resume and retry A
~~~

This is **blocking retry coordinated via pause**, not a non-blocking retry topic. Non-blocking retry moves the record to another Kafka topic, creating a new offset and potentially altering processing order.

The API to initialize `ContainerPausingBackOffHandler` depends on the Spring Kafka version, scheduler, and error handler; verify against your specific project. Do not replace this mechanism with a long `Thread.sleep` inside the listener.

If a container has both retry backoff pause and manual pause, ownership of the pause state must be handled clearly. If two control sources call resume without coordination, the consumer may resume intake while the operator still wants it stopped.

## 14. Pause can increase consumer lag

While the consumer is paused, producers continue sending events to the topic. Backlog can grow:

~~~text
Producer arrival: 2,000 records/second
Pause duration: 60 seconds

Approximate new records: 120,000
Consumer lag can increase accordingly.
~~~

Upon resume, you need to calculate the **backlog drain rate**:

~~~text
Producer continues: 2,000 records/second
Consumer after resume: 3,000 records/second
Backlog drain rate: 1,000 records/second

A backlog of 120,000 records needs about 120 seconds to catch up
(under an ideal model, excluding overhead and errors).
~~~

If downstream can only sustain 2,000 records/second, resuming cannot quickly reduce the backlog because the arrival rate roughly equals the processing rate. You need capacity planning, workload separation, additional resources, or appropriate business-flow prioritization.

Lag increasing during an approved maintenance pause can be **by design**, yet you still need alerts if the duration or backlog exceeds the SLO budget.

## 15. Retention and the risk of data loss during a long pause

Kafka brokers apply retention per topic, independent of a consumer's pause state. If a pause lasts for many hours or days while the topic has a short retention period, some unconsumed records may be deleted before the consumer resumes.

You need to review:

- `retention.ms` and `retention.bytes`.
- Producer rate and number of partitions.
- Disk capacity, replication, and Kafka cluster load capacity.
- Maximum pause duration allowed by SLO.
- Age of unprocessed records and projected catch-up time.
- Replay/restore plan if retention has already caused record loss.

Never promise that pause "can never cause data loss." Pause itself does not delete records, but an overly long backlog may fall outside the Kafka topic's retention window.

## 16. Concurrency and child containers

`ConcurrentMessageListenerContainer` can create multiple child Kafka consumers. When calling `pause()` on the parent container, Spring Kafka coordinates the request down to the child consumers.

~~~text
Concurrent container: concurrency = 3
  |
  +-- Child A: partitions 0 and 3
  +-- Child B: partitions 1 and 4
  +-- Child C: partitions 2 and 5

parent.pause()
  -> Requests pause on child consumers.
~~~

Because each child polls and processes on its own schedule, the paused state may take effect asynchronously. To know that all consumers are paused, check the corresponding container status or application events, not just a single log line from child A.

If you only want to reduce throughput instead of halting all intake, consider other strategies:

- Limit `max.poll.records`.
- Reduce concurrency with an appropriate rebalance plan.
- Use a bounded work queue and rate limiter.
- Pause per partition when independent conditions exist.
- Split topics by priority or SLO.

Changing concurrency/assignments can trigger a rebalance; do not repeatedly scale up/down to simulate a few-second pause.

## 17. Observing via application events

Spring Kafka publishes several application events related to pause/resume depending on the version, such as `ConsumerPausedEvent` and `ConsumerResumedEvent`. You can register a listener to record events:

~~~java
@Component
public class KafkaPauseEventLogger {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaPauseEventLogger.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("Kafka consumer paused: {}", event);
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("Kafka consumer resumed: {}", event);
    }
}
~~~

Beyond container-level events, some versions also provide events for partition-level pause/resume. Event names and getter details must be checked against the API in use.

Operational logs should include listener ID, instance ID, pause reason, requester, timestamp, and resume time. If you need exact partitions, read the event data or container API rather than relying solely on a toString string.

## 18. Key metrics

| Metric | Operational question |
|---|---|
| Container `isRunning` / `isPauseRequested` / `isConsumerPaused` | Is it stopped, pause-requested, or actually paused? |
| Pause duration | Was the container forgotten and left unresumed? |
| Consumer lag by topic/partition | How much has the backlog grown? |
| Oldest unprocessed age | Is it about to breach SLO/retention? |
| Downstream queue depth | Is a pause/resume needed? |
| DB connection pool utilization | Is the database lacking capacity? |
| Retry/error/DLT count | Did pause reduce errors or just mask them? |
| Pause/resume transitions | Is the control loop flapping? |
| Consumer group rebalance count | Is the group still stable? |
| End-to-end processing latency | How long are business events delayed? |

A single `paused=1` metric is not enough to determine whether Kafka has failed. Context is required: whether pause was requested by the backpressure system or an operator, and the corresponding downstream state.

With multiple pods, measure per instance/container or analyze the entire consumer group. Event IDs belong in logs/traces; do not use event IDs as metric labels due to excessive cardinality.

## 19. Pause does not mean there is no in-flight work left

Certain side effects can still occur after an operator requests a pause:

- The listener is processing a record or batch it already received.
- An HTTP request has already been sent downstream.
- A database transaction is already open.
- An async task was submitted by the listener.
- A manual ack is waiting to execute.
- A Kafka transaction is processing output.

If safe maintenance is needed, combine:

1. Request pause.
2. Wait for the effective paused state.
3. Measure the number of in-flight operations.
4. Wait for in-flight to reach 0, or handle timeout/drain per policy.
5. Perform the change.
6. Verify downstream capacity.
7. Resume in a controlled manner.

Do not mistake pause for a transactional barrier that can roll back or cancel work already started.

## 20. Offsets and manual acknowledgment

Example listener using manual acknowledgment:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    containerFactory = "manualAckListenerFactory")
public void onMessage(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment ack) {

    orderService.apply(record.value());
    ack.acknowledge();
}
~~~

Acknowledgment should only happen after required side effects complete according to business semantics. Pausing before or after an ack does not by itself alter the meaning of `ack.acknowledge()`.

If the listener reports success before the DB write commits, the Kafka offset may be confirmed prematurely. Conversely, if the DB write commits and the Kafka offset has not committed yet, the record may be redelivered. Idempotency or an inbox is required for DB writes.

For transactional containers, pause does not automatically commit or abort an open transaction. Kafka offsets, outputs, and rollbacks still follow the configured transaction manager and error-handling flow.

## 21. Distinguishing pause from a single-record error

| Scenario | Appropriate approach |
|---|---|
| Widespread database connection pool exhaustion | Pause or throttle container; monitor to resume |
| Downstream API reporting sustained rate limits | Backpressure, rate limiter, consider pausing |
| A corrupted JSON payload | Non-retryable classification and DLT/quarantine |
| An event violating business rules | Error handler by error type, do not pause all events |
| Brief network blip lasting a few hundred milliseconds | Small retry/backoff may be simpler than pause |
| Controlled database maintenance | Pause and drain in-flight before maintenance |
| Wanting to hand partitions to healthier pods | Planned stop/rebalance, not just pause |
| Retry waiting many minutes while keeping original topic moving | Consider separate retry topic/workflow and ordering tradeoffs |

Pause is best suited when the **work-intake capacity** of the consumer or downstream is changing. It is not the sole tool for every retry scenario.

## 22. Runbook: container is paused and offsets are not advancing

1. Determine whether the container is `STOPPED` or still `RUNNING`.
2. Check `isPauseRequested()` and `isConsumerPaused()`.
3. Check the parent container, child consumers, and partition-level pauses.
4. Identify the source of the request: operator, backpressure monitor, retry backoff handler, or application code.
5. Verify the scheduler/resume task is still running.
6. Check downstream health and hysteresis thresholds.
7. Confirm which pod/instance owns the partitions and whether a rebalance occurred.
8. Inspect pause/resume event logs, lag, and request timestamps.
9. If downstream has recovered, clear the proper pause reason and call resume from the control plane.
10. Confirm new records are being processed and lag begins decreasing.

If the application restarts, in-memory controlled pause state may change. For multi-instance maintenance procedures, determine whether pause state must be persisted or reconstructed from the control plane after restart.

## 23. Runbook: backlog grows after pause

1. Measure ingress rate, consumer processing rate, and backlog.
2. Check topic retention and Kafka storage capacity.
3. Calculate estimated catch-up time based on net throughput.
4. Confirm the database/API has recovered sufficient capacity.
5. Resume in a controlled manner; avoid all pods pushing maximum load simultaneously.
6. Monitor DB connection pool, HTTP 429/503, error handler retries, and DLT.
7. Check for key skew/hot partitions if one partition lags behind despite high concurrency.
8. If recovery past retention is needed, use an audited replay/restore procedure.
9. Never reset consumer offsets just to make a lag dashboard show 0.
10. Tune backpressure thresholds and SLOs to avoid repeating the outage.

A mistake to avoid: resuming before the dependency recovers causes the listener to fail, then the monitor pauses again, creating a pause/resume loop that causes oscillating load.

## 24. Common mistakes

**Calling KafkaConsumer.pause directly from an admin thread:** KafkaConsumer is not thread-safe. When using a Spring listener container, use the container's pause/resume API.

**Using long Thread.sleep inside the listener:** This can affect the poll interval and cause rebalances. Container pause allows the poll loop to continue.

**Assuming pause takes effect immediately:** Already-polled records and in-flight work can still run. Distinguish requested vs. effective.

**Swallowing exceptions after pausing:** The container may commit the offset of an unfinished record. Propagate the exception or handle ack/retry properly.

**Using pause instead of DLT:** A poison record will not become valid after a wait. Classify permanent errors properly.

**Expecting partitions to move to another member:** Pause does not actively release assignments. Only stop or a rebalance can change ownership.

**One pod resumes, assuming the whole group resumed:** The registry is JVM-scoped. Observe all instances.

**Having no limit on pause duration:** Backlog can breach SLO or retention; configure alerts and ownership.

**Auto resume overriding manual maintenance:** Enforce pause-reason precedence or a unified control plane.

## 25. Implementation checklist

- [ ] Use `MessageListenerContainer.pause()/resume()`.
- [ ] Configure a stable `@KafkaListener(id = ...)` to control the right container.
- [ ] Distinguish pause requested from pause effective.
- [ ] Consider `pauseImmediate` when needing to stop starting record processing sooner.
- [ ] Do not confuse container pause with partition pause or container stop.
- [ ] Consumer polling continues to maintain group membership.
- [ ] Do not use `Thread.sleep` in the listener as a substitute for pause.
- [ ] Do not swallow exceptions or ack records not yet processed successfully.
- [ ] Have an error handler and DLT for unprocessable records.
- [ ] Have a control loop with hysteresis and clear pause-reason ownership.
- [ ] Monitor pause duration, lag, retention, and downstream capacity.
- [ ] Have a way to control all pods and track effective state.
- [ ] Have a runbook to drain in-flight work before maintenance.
- [ ] Resume according to actual capacity and monitor backlog drain.

**Conclusion:** Pausing a listener container is an effective backpressure mechanism in Spring Kafka when downstream temporarily lacks capacity. Instead of stopping the consumer group, the container keeps the poll loop active and suspends dispatching records once the pause takes effect. A proper design must distinguish requested vs. effective pause, track in-flight work, bound pause duration, and coordinate resume with dependency health. For failed records, responsibilities for offsets, retries, transactions, DLT, and idempotency must still be handled independently; pause does not replace them by itself.
