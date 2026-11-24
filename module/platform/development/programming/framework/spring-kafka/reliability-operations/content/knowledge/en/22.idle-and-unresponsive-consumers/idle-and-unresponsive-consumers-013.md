# Actions when a consumer is non-responsive

In **Spring Kafka Reliability Operations**, a **non-responsive** consumer is an incident requiring investigation because the Kafka consumer or listener container is not advancing its **`poll()`** loop on the expected cadence. This differs from **idle** (the topic has no data) and **pause** (the container intentionally stops delivering new records while continuing to poll). If a consumer goes without polling for too long, it stops processing records, builds backlog, or loses partition ownership after breaching **`max.poll.interval.ms`**.

Spring Kafka provides **`NonResponsiveConsumerEvent`** as an early-warning signal when time elapsed since the last poll exceeds the monitor threshold. This event **does not by itself prove** the Kafka broker is down, pinpoint exactly where a thread is stuck, or automatically restart the container. Recovery must rely on actual root causes alongside offset, transaction, and side-effect state.

Guiding principle: **observe → classify → gather evidence → choose the lowest-risk action → verify data and consumer recovery**. Never turn a warning into a restart loop, and never skip records by arbitrarily committing offsets.

## 1. The operational problem

Suppose `order-service` reads `orders.events`. Initially the consumer processes 1,000 events/minute. At some point, operations observes:

- Producers continue writing records to Kafka.
- Group committed offsets stop advancing.
- Consumer lag climbs.
- The container may still report `running`.
- No new success logs appear from `@KafkaListener`.
- Spring Kafka begins emitting `NonResponsiveConsumerEvent`.

You must determine whether the consumer is stuck inside **`KafkaConsumer.poll()`**, inside the **business listener**, inside the **error handler/backoff**, undergoing a **rebalance**, or simply **paused**. Only then can you decide whether to fix a downstream dependency, shed load, restart a listener container, or escalate.

Taking the wrong action can cause repeated redeliveries, duplicate database charges or inventory holds, aborted Kafka transactions, or continuous rebalances across the entire consumer group.

## 2. Distinguishing idle, paused, slow, and non-responsive

| State | Consumer polling | Listener receiving records | Meaning |
|---|---|---|---|
| Idle | Usually keeps polling steadily | Receives no records because none exist | May be completely normal |
| Paused | Usually keeps polling to retain membership | Receives no more records from paused partitions | Intentional backpressure or maintenance |
| Slow listener | Next poll is delayed | Currently processing a slow record | Risk of exceeding `max.poll.interval.ms` |
| Poll stuck | Poll fails to return on cadence | No further dispatch | Suspected network/client/coordinator issue |
| Rebalance | Poll coordinates group | Delivery may pause briefly | Check assignments and callbacks |
| Container stopped | Stops polling once stop finishes | Receives no records | Lifecycle state, not idle |

**`ListenerContainerIdleEvent`** reports that the container received no data over a period. **`NonResponsiveConsumerEvent`** concerns **abnormal gaps without polling**. A consumer can stay idle for hours and remain completely healthy because polling keeps running.

~~~mermaid
flowchart TD
    A["No records being processed"] --> B{"Container RUNNING?"}
    B -->|No| C["Check lifecycle and startup"]
    B -->|Yes| D{"Polling still running on cadence?"}
    D -->|Yes| E{"Paused or no records?"}
    E -->|Yes| F["Idle / intentional backpressure"]
    E -->|No| G["Check lag, retries, deserialization, assignment"]
    D -->|No| H["Non-responsive / poll gap"]
    H --> I["Thread dump, broker, network, listener duration"]
    I --> J["Controlled recovery"]
~~~

Never draw conclusions from consumer lag alone. Lag can also grow when producers outpace processing capacity or during an intentional pause.

## 3. What does NonResponsiveConsumerEvent mean?

Spring Kafka runs a monitor that checks elapsed time since the consumer's last poll. When that duration crosses the threshold, it can publish **`NonResponsiveConsumerEvent`**.

The event typically exposes the following details, depending on version:

- **`listenerId`**: ID of the observed listener/container.
- **`timeSinceLastPoll`**: elapsed time since the last poll, usually in milliseconds.
- **`topicPartitions`**: relevant `TopicPartition` entries.
- **`consumer`**: consumer reference when provided by the API.
- Spring application event source/container metadata.

Key points to remember:

1. The event is a **warning signal**; verify poll metrics and thread state.
2. Events can **repeat** while a consumer remains non-responsive.
3. Receiving an event does not mean the consumer already left the consumer group.
4. The event does not prove records were lost or transactions failed.
5. The event does not automatically stop, seek, commit, or restart anything.
6. In concurrent containers, a single child consumer can fail independently.

A monitor watching poll gaps also fires when a listener simply takes too long to process; thus "consumer hasn't polled again" does not guarantee `poll()` itself deadlocked inside the Kafka client.

## 4. Detection thresholds: pollTimeout, noPollThreshold, monitorInterval

Key properties:

| Spring Kafka property | Effect |
|---|---|
| `pollTimeout` | Duration a poll call may wait for data per container config |
| `noPollThreshold` | Multiplier to classify an abnormal no-poll gap |
| `monitorInterval` | Cadence at which the monitor checks consumer state |

Illustrative example:

~~~text
pollTimeout     = 5,000 ms
noPollThreshold = 3.0
monitorInterval = 10 seconds

Reference monitor threshold: 3 x 5,000 = 15,000 ms.
Because the monitor runs periodically, the event may fire later
than when the threshold was first crossed, not at exact millisecond 15,000.
~~~

Spring Kafka compares time since poll against `noPollThreshold × pollTimeout` in supported versions. Defaults can change across framework generations; verify your current dependency.

**This is a framework monitoring threshold, not the Kafka client's `max.poll.interval.ms`.** Tuning `monitorInterval` only affects detection/alert timing, not the timeout enforced by the consumer group.

## 5. Listener factory configuration example

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class OrderKafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties().setPollTimeout(5_000L);
        factory.getContainerProperties().setMonitorInterval(10);
        factory.getContainerProperties().setNoPollThreshold(3.0f);

        return factory;
    }
}
~~~

The listener must bind to this exact container factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProcessor processor;

    public OrderListener(OrderProcessor processor) {
        this.processor = processor;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "orderListenerFactory"
    )
    public void onOrder(OrderEvent event) {
        processor.process(event);
    }
}
~~~

`OrderEvent` and `OrderProcessor` are illustrative domain classes. When using Spring Boot auto-configuration or multiple factories, verify the listener is bound to the intended factory.

Setting thresholds too low creates false positives during JVM GC pauses or legitimate slower processing. Setting them too high delays detection, potentially until after the group has already rebalanced.

## 6. Listening to events via @EventListener

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerPollHealthObserver {

    private static final Logger log =
        LoggerFactory.getLogger(ConsumerPollHealthObserver.class);

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {

        log.warn(
            "Kafka consumer not responsive: listenerId={}, sincePollMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions()
        );
    }
}
~~~

Your initial reaction should be **lightweight logging/metrics/diagnostic triggers**, never immediate restarts. Event callbacks must not invoke synchronous monitoring APIs with long timeouts or run heavy business queries.

Getter names and metadata availability must match your Spring Kafka version. If you need group ID, instance ID, or pause reasons, enrich from application config or container inspection rather than assuming the event supplies everything.

## 7. KafkaConsumer thread safety

In Spring Kafka, the consumer thread is managed by the listener container. `KafkaConsumer` is generally **not thread-safe** for arbitrary poll, seek, commit, pause, or resume calls from other threads.

A `NonResponsiveConsumerEvent` may be published from a monitor thread. Even if the event carries a `KafkaConsumer` reference, do not do this:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Unsafe if called from a thread that does not own the consumer:
    // event.getConsumer().commitSync();
    // event.getConsumer().seek(...);
}
~~~

To control lifecycle, use **`MessageListenerContainer`** or **`KafkaListenerEndpointRegistry`**; to control partition processing, use the APIs exposed by the Spring Kafka container.

Never keep a raw `KafkaConsumer` in a singleton to call from a recovery REST endpoint. Respect consumer thread confinement and transaction/ack ownership.

## 8. IdleEvent, PauseEvent, and NonResponsiveEvent

| Event | Interpretation scope |
|---|---|
| `ListenerContainerIdleEvent` | No new records received during idle interval |
| `ListenerContainerNoLongerIdleEvent` | Records resumed after an idle period |
| `NonResponsiveConsumerEvent` | Failed to poll again within monitor threshold |
| `ConsumerPausedEvent` | Container/consumer paused |
| `ConsumerResumedEvent` | Container/consumer resumed |
| `ConsumerStoppedEvent` | Consumer stopped |
| `ConsumerPartitionPausedEvent` | A specific partition paused, if supported by version |

Example: a topic is empty for an hour while the consumer keeps polling normally—`IdleEvent` may appear, not necessarily `NonResponsiveEvent`.

Example: a consumer is stuck on an untimed SQL lock wait—the topic still has records, yet the listener never returns to poll, so `NonResponsiveEvent` may appear.

A dashboard collapsing all events into "consumer offline" will not help operators choose the right action.

## 9. Slow listener processing is a common cause

Example:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) throws Exception {

    // Missing a timeout is a blocking risk.
    downstreamFuture.get();

    orderService.save(event);
}
~~~

If `downstreamFuture` never completes, the thread never returns to poll. Common blocking sources:

- HTTP calls lacking connect/read timeouts.
- JDBC queries waiting on locks or exhausted connection pools.
- `CompletableFuture.get()`/`join()` without deadlines.
- `CountDownLatch.await()` without timeouts.
- `synchronized` locks or `ReentrantLock` deadlocks.
- Manual retries using long `Thread.sleep` calls.
- Batches containing too many records.
- Heavy CPU/GC preventing the thread from being scheduled.

Remediation: enforce timeouts, circuit breakers, bounded executors, shorter transactions, and measure listener processing latency. Never just raise `noPollThreshold` to mute alerts.

## 10. Consumer stuck in poll or group coordination

Some causes do not originate in the business listener:

1. Broker or coordinator unavailable.
2. Unstable DNS or TCP connectivity.
3. TLS/SASL authentication failures.
4. Network partitions or packet loss.
5. Broker quotas/throttling.
6. Partition leader changes.
7. Overly slow rebalance callbacks.
8. Blocking custom interceptors or deserializers.
9. Kafka client or framework version issues.
10. JVM stop-the-world GC or CPU starvation.

If **multiple consumers across multiple services report simultaneously**, inspect shared brokers/networking before mass-restarting applications.

If only one child consumer inside a single JVM is affected, prioritize its thread dump, listener processing, and partition assignments.

## 11. max.poll.interval.ms and heartbeats

Kafka consumers can be configured as:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

In this example, `max.poll.interval.ms` is 5 minutes. If a consumer fails to return to poll in time due to slow processing, the consumer group may rebalance or transfer partitions.

Distinguish clearly:

| Setting | Function |
|---|---|
| `max.poll.interval.ms` | Maximum time between polls for group membership progress |
| `session.timeout.ms` | Session liveness limit under the group protocol |
| `heartbeat.interval.ms` | Heartbeat cadence where applicable to the protocol |
| `pollTimeout` | Single-poll wait time on the listener container |
| `noPollThreshold` | Spring monitor multiplier flagging abnormal poll gaps |
| `monitorInterval` | Spring monitor check cadence |

Raising `max.poll.interval.ms` never cures deadlocks; it only delays failover. Raising `noPollThreshold` does not alter broker behavior.

## 12. Batch processing causing poll gaps

Suppose poll returns 300 records and each record takes 2 seconds:

~~~text
poll() returns 300 records
listener processes sequentially: 300 x 2 seconds = 600 seconds
consumer does not return to poll until the batch finishes
~~~

With `max.poll.interval.ms` at 300 seconds, the consumer risks breaching the limit. `NonResponsiveConsumerEvent` may also fire.

Solutions:

- Lower `max.poll.records`.
- Optimize database/API calls.
- Enforce per-record time budgets.
- Partition batches/scopes appropriately.
- Test what happens when one record fails mid-batch.
- Ensure offsets are never committed past unprocessed records.
- Use idempotency to survive redeliveries after rollbacks or rebalances.

Never grab the highest offset in a batch and commit it while some records remain unfinished.

## 13. Database deadlocks and lock waits

A listener can enter a database transaction and block on a lock:

~~~text
Kafka record
 -> Spring @Transactional service
 -> UPDATE inventory
 -> Database lock wait
 -> Listener does not return
 -> Poll gap climbs
 -> NonResponsiveConsumerEvent
~~~

Investigate:

- DB deadlock logs and lock-wait timeouts.
- Slow SQL queries and missing indexes.
- Connection pool active/waiting counts.
- Consistent lock acquisition ordering across services.
- Concurrent records targeting the same aggregate/key.
- Transaction duration.
- Rollback before retry.
- Database isolation levels and retry budgets.

If the database rolls back a deadlock, bounded retries may be valid. If a thread blocks forever due to missing timeouts, restarting the Kafka consumer does not replace fixing the SQL/transaction.

## 14. Rebalance callbacks can block polling

`ConsumerRebalanceListener` or group-coordination callbacks must never perform unbounded remote work:

~~~java
@Override
public void onPartitionsRevoked(
        Collection<TopicPartition> partitions) {

    // Risky if the remote service has an outage.
    remoteCheckpointService.flushBlocking();
}
~~~

Keep callbacks short, bounded with timeouts, and clear on state/offset ownership semantics. Continuous rebalances can stem from restarting members, `max.poll.interval` expirations, unstable networking, or scaling.

If a consumer stops polling because a callback is stuck, fix the callback rather than simply raising `pollTimeout`.

## 15. Container pause vs non-responsive

When **`container.pause()`** is applied, Spring Kafka typically keeps calling **`poll()`** to preserve consumer group membership while halting record dispatch from paused partitions. That is the right backpressure tool when consumer threads are still healthy.

~~~text
DOWNSTREAM OVERLOAD:
container.pause() -> consumer keeps polling -> no new work
container.resume() -> resumes receiving records

THREAD DEADLOCK:
controller calls pause() -> consumer thread never returns
actual pause may not have taken effect yet
non-responsiveness still occurs
~~~

A pause request cannot interrupt an already-blocked listener. To diagnose, monitor `isPauseRequested()`, `isConsumerPaused()`, poll metrics, and listener durations.

Never use long `Thread.sleep` calls inside a listener instead of container pause; sleeping delays the next poll.

## 16. Retries, BackOff, and error handlers

In standard listeners, **`DefaultErrorHandler`** governs retries and recovery when a listener fails. A long `BackOff` or custom handler blocking the consumer thread can stretch poll gaps.

Verify:

1. Which exception types trigger retries.
2. Attempt counts and total `BackOff` duration.
3. Whether the error handler seeks/redelivers or holds records.
4. Whether container-pausing backoff is used for long delays.
5. Whether the DLT recoverer and producer are working.
6. Whether a failing record loops endlessly.
7. Whether `AckMode` and offset recovery match policy.

When using **`@RetryableTopic`**, main, retry, and DLT listeners can run as separate containers. A `NonResponsiveConsumerEvent` from a retry container does not prove the main consumer group is also stuck.

Never swallow every exception and return normally just to let the container advance offsets. Doing so marks records successful while business work remains incomplete.

## 17. Capturing thread dumps

When a consumer is suspected stuck and the JVM is alive, thread dumps provide critical evidence. Reference JDK commands:

~~~text
jcmd <pid> Thread.print
jstack <pid>
~~~

These are operational tool examples, **not commands you must blindly run in Step 4**. Minimal container images may omit `jcmd`/`jstack`.

Capture a couple of snapshots spaced briefly apart to see whether threads advance or stay frozen. Correlate with CPU, GC pauses, thread states, lock owners, JDBC/HTTP timeouts, and timestamped logs.

Thread dumps can contain sensitive details. Store them under incident IDs per security policy and avoid collecting them overly frequently across the entire fleet.

## 18. First response after the event

A safe response flow:

~~~mermaid
flowchart TD
    A["NonResponsiveConsumerEvent"] --> B["Log / metric / firstSeen"]
    B --> C{"Poll self-recovers within observation window?"}
    C -->|Yes| D["Record as transient"]
    C -->|No| E["Check running, paused, lag, assignment"]
    E --> F{"Widespread broker/DB/network outage?"}
    F -->|Yes| G["Fix dependency"]
    F -->|No| H["Thread dump and listener diagnostics"]
    H --> I{"Can fix the blocker?"}
    I -->|Yes| J["Fix timeout/lock/dependency"]
    I -->|No| K["Consider bounded restart"]
    K --> L["Verify poll, offsets, processing, duplicates"]
~~~

Never auto-restart on the first sighting without evidence. A brief GC pause or transient downstream timeout may self-recover, whereas restarting causes unnecessary rebalances.

## 19. Event listeners should not run synchronous recovery

A handler should simply enqueue an observation:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class NonResponsiveConsumerHandler {

    private static final Logger log =
        LoggerFactory.getLogger(NonResponsiveConsumerHandler.class);

    private final ConsumerRecoveryCoordinator coordinator;

    public NonResponsiveConsumerHandler(
            ConsumerRecoveryCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @EventListener
    public void onEvent(NonResponsiveConsumerEvent event) {

        String listenerId = event.getListenerId();
        long sincePollMs = event.getTimeSinceLastPoll();

        log.warn(
            "Kafka poll gap: listenerId={}, sincePollMs={}",
            listenerId, sincePollMs
        );

        coordinator.observe(listenerId, sincePollMs);
    }
}
~~~

`ConsumerRecoveryCoordinator` is an application-implemented domain component. `observe` must be fast: update metrics/state or enqueue **a bounded job**. Never run restarts, HTTP calls, or lengthy database work directly inside the event callback.

## 20. Recovery state machine

You can model states as:

~~~text
HEALTHY
  |
  +-- NonResponsiveConsumerEvent --> SUSPECT
                                    |
                                    +-- poll restored --> HEALTHY
                                    |
                                    +-- sustained stall --> DIAGNOSING
                                                            |
                                                            +-- dependency outage --> WAIT_DEPENDENCY
                                                            |
                                                            +-- listener blocked --> FIX_OR_CANCEL
                                                            |
                                                            +-- stuck container --> RESTART_REQUESTED
                                                                                     |
                                                                                     +-- success --> HEALTHY
                                                                                     |
                                                                                     +-- failed --> MANUAL_REVIEW
~~~

These are application states, not a built-in Spring Kafka enum.

A production coordinator needs single-flight per listener, cooldowns, max attempts, audit trails, outage classification, and post-restart health verification.

A burst of events from the same monitor must never spawn a burst of restart jobs.

## 21. Finding containers with KafkaListenerEndpointRegistry

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public MessageListenerContainer find(String id) {
        return registry.getListenerContainer(id);
    }

    public void inspect(String id) {
        MessageListenerContainer container = find(id);

        if (container == null) {
            return;
        }

        boolean running = container.isRunning();
        boolean requested = container.isPauseRequested();
        boolean paused = container.isConsumerPaused();

        // Log/record metrics for running, requested, paused.
    }
}
~~~

When concurrency exceeds 1, events may carry child listener IDs. The registry typically manages logical listener containers, so map IDs to child containers carefully. Never strip suffixes blindly and restart multiple containers by mistake.

One stuck child consumer does not automatically justify restarting the entire service.

## 22. Conditions permitting a restart

A restart can be justified when:

- The poll gap persists and the consumer fails to self-recover.
- Thread dumps/metrics confirm a stuck state.
- Brokers/downstream are not in a widespread outage that restarting cannot fix.
- In-flight work can be rolled back or reconciled.
- The consumer is designed to be idempotent.
- No other restart is already in progress.
- Cooldowns and restart budgets permit it.
- Assignment, polling, and business processing can be verified post-restart.

Do not restart when the container is shutting down/deploying, a previous stop has not finished, side effects are indeterminate, or the root cause is a cluster-wide broker outage.

**Restart is a conditional recovery action, not the default semantics of `NonResponsiveConsumerEvent`.**

## 23. Stopping/starting via lifecycle

`MessageListenerContainer` exposes lifecycle APIs. Sketch:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {

    container.stop(() -> {
        restartExecutor.execute(() -> {

            if (!container.isRunning()
                    && recoveryPolicy.mayRestart("ordersListener")) {
                container.start();
            }
        });
    });
}
~~~

`restartExecutor` and `recoveryPolicy` are illustrative domain components. Production needs single-flight guards, cooldowns, shutdown guards, logging, and error handling.

Never call `stop(); start();` back-to-back assuming stop finished immediately. Stop can be asynchronous; consumer threads may still be blocked.

If stop fails to complete, escalate; never start a new consumer over an unclear state or force-kill with `Thread.stop()`.

## 24. Stopping a container vs restarting the JVM

| Action | Appropriate situation | Risk |
|---|---|---|
| Wait with alerts | Transient GC/network stall | May impact SLA if waited too long |
| Fix dependency | DB/HTTP/broker outage | May not rescue an already deadlocked thread |
| Pause/resume | Backpressure while polling continues | Does not rescue a blocked thread |
| Restart listener container | Single stuck consumer replaceable | Rebalance, redeliveries, transaction aborts |
| Restart application instance | Unrecoverable JVM/runtime state | Impacts multiple listeners |
| Rolling restart service | Fleet-wide config/runtime issue | Risk of thundering herd |
| Manual reconciliation | Indeterminate side effects/commits | Needs operators and domain expertise |

Prefer the smallest scope that recovers safely. Liveness probes should never kill pods solely because consumer lag grew; that turns backpressure into a crash loop.

## 25. Offsets, duplicates, and idempotency

Restarting can redeliver uncommitted records. For instance, a consumer updates a database and crashes before committing Kafka offsets. When the group re-reads the record, side effects will execute again unless guarded.

A common solution is an inbox table:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

~~~java
@Transactional
public void processIdempotently(OrderEvent event) {

    boolean first = processedEvents.insertIfAbsent(
        "orders-service", event.eventId()
    );

    if (!first) {
        return;
    }

    orderRepository.apply(event);
}
~~~

Production requires real domain repositories and unique constraints. Both the marker and business side effect must commit inside the same database transaction.

When calling external APIs, pass stable idempotency keys. When updating a DB and publishing to Kafka, consider the outbox pattern. Never reset offsets to `latest` to dodge a stuck record; that silently drops unprocessed data.

## 26. Transactional listeners require extra caution

With transactional Kafka listener containers, the container commits Kafka outputs and input offsets in a single Kafka transaction. On listener errors, the transaction aborts; **`AfterRollbackProcessor`** can seek/redeliver or route failing records to recovery per configuration.

When non-responsive, inspect:

- Transaction timeouts.
- Producer fencing and `transactional.id`.
- Consumer group generations/rebalances.
- Transaction commit/abort outcomes.
- Whether Kafka input offsets were sent to the transaction.
- Downstream `read_committed` visibility.
- DLT/recovery publish success.
- External DB/API side effects outside Kafka transactions.

Never manually call `commitSync()` to advance offsets inside a transactional pipeline. That breaks atomicity of Kafka-to-Kafka processing.

After restarts, records can redeliver; Kafka EOS does not mean external side effects execute only once.

## 27. Async processing does not guarantee correctness just because polling stays steady

An anti-pattern:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Listener returns before the async task actually completes.
}
~~~

The container may treat a normal method return as successful record handling, depending on `AckMode`. If the async task fails after offsets commit, the event risks losing its chance at redelivery.

You need:

1. Bounded executor queues and max in-flight caps.
2. Acknowledgments only after durable processing succeeds.
3. Per-partition offset ordering.
4. Flow-control pause/resume at high/low queue watermarks.
5. Rebalance/shutdown handling for in-flight tasks.
6. Idempotency when tasks re-execute.
7. Never touching `KafkaConsumer` from worker threads.

`NonResponsiveConsumerEvent` measures poll responsiveness—**it does not prove business processing is correct**. Healthy poll rates can coexist with incomplete side effects if async semantics are broken.

## 28. Important metrics

| Metric | Purpose |
|---|---|
| Non-responsive event count | Frequency of flagged poll gaps |
| Time since last poll | Duration of suspected stall |
| Poll-rate, poll-latency | Monitor poll loop |
| Listener processing p95/p99 | Spot lengthening business execution |
| `max.poll.interval` violations | Group membership risk |
| Rebalance count | Assignment churn |
| Container running/paused | Lifecycle and backpressure |
| Partition assignments | Whether consumer still owns partitions |
| Consumer group lag | Input backlog |
| Oldest unprocessed age | Business SLA |
| Database pool waiters | DB saturation |
| HTTP timeout/error rate | Downstream reliability |
| JVM GC pause/CPU | Runtime stalls |
| Transaction abort/fencing | Transactional health |
| Recovery/DLT backlog | Unrecovered failing records |
| Restart count/outcome | Whether auto-recovery works |

Some names are **illustrative metrics**, not all built-in out of the box from Spring Kafka. Distinguish Kafka client JMX/Micrometer metrics from custom application observations.

Never put event IDs, offsets, keys, or exception messages into metric tags due to high cardinality.

## 29. Structured logging

Example:

~~~text
event=kafka_consumer_non_responsive
service=orders-service
instance=orders-pod-3
listener_id=ordersListener-1
group_id=orders-service
time_since_last_poll_ms=48000
poll_timeout_ms=5000
monitor_interval_s=10
no_poll_threshold=3.0
container_running=true
pause_requested=false
consumer_paused=false
assigned_partition_count=2
~~~

Supplemental fields such as group ID, pause reason, and assignments may need to be pulled from config/container state. This is not a default built-in log format.

Include `firstSeen`, `lastSeen`, and an incident ID to group consecutive events. Never log payloads or credentials. When tracing an in-flight record is needed, use controlled structured tracing with topic/partition/offset.

## 30. Reducing noise and preventing restart storms

A stuck consumer can emit multiple `NonResponsiveConsumerEvent` instances over several minutes. Paging or restarting on every event causes alert storms and rebalance churn.

Sensible policies:

- Group alerts by `service + instance + listener ID`.
- Tier severity by **stall duration + lag + business SLA**.
- Enforce cooldowns between recovery attempts.
- Single-flight: one recovery job per container.
- Correlate widespread broker/DB outages.
- Never restart the whole fleet during cluster-wide faults.
- Cap max restart attempts before escalating.
- Verify polling/throughput recovery before closing incidents.

If multiple restarts fail to improve things, pause automated restarts and investigate deeper. A consumer that stalls repeatedly almost always points to an unresolved root cause.

## 31. Integration testing NonResponsiveConsumerEvent emission

Use EmbeddedKafka or Testcontainers to prove realistic interaction between the monitor and consumer container:

1. Create a dedicated test topic/group.
2. Configure `pollTimeout`, `monitorInterval`, and `noPollThreshold`.
3. Wait for the container to receive assignments.
4. Block the listener on a latch **with a finite timeout**.
5. Wait for `NonResponsiveConsumerEvent` via a polling assertion with timeout.
6. Verify listener ID and `timeSinceLastPoll`.
7. Release the latch in `finally` so tests never hang.
8. Verify the consumer returns to polling.
9. Send another record and verify processing/offsets per policy.
10. Clean up containers and test resources.

A blocked-listener test demonstrates **a processing-induced poll gap**. It does not prove every event stems from an internal `KafkaConsumer.poll()` bug.

## 32. Testing idle, pause, and stuck separately

Include comparative tests:

**Idle:** keep the topic empty, enable `ListenerContainerIdleEvent`, verify polling continues. Do not expect `NonResponsiveConsumerEvent` solely from empty traffic.

**Pause:** call `container.pause()`, wait for actual paused state, verify polling continues without dispatching new records from paused partitions. Resume and verify records process.

**Stuck:** block the listener in a test with timeout, verify poll gap grows and monitor events fire. Release the block and verify recovery.

**Rebalance:** alter group membership cleanly in a test, verify the listener container handles reassignment without committing past incomplete records.

**Transactional:** induce an error inside a Kafka transaction, verify abort/`AfterRollbackProcessor` and record redelivery or recovery per policy.

Tests should use timeout-bounded assertions—never rely solely on fixed `Thread.sleep` calls or `container.isRunning()`.

## 33. Production runbook

**Detection**

1. Record listener ID, service instance, group ID, and topics/partitions.
2. Capture `timeSinceLastPoll`, `firstSeen`, and repeated event counts.
3. Inspect poll rate, listener duration, lag, and recent deployments.
4. Determine whether one consumer or multiple groups are affected.

**Classification**

5. Check running/paused state.
6. Check group assignments, rebalances, and broker/network health.
7. Check database locks/pools, HTTP timeouts, and JVM GC/CPU.
8. Capture a thread dump if the stall persists.
9. Check error handler `BackOff` and transaction state.
10. Classify as poll stuck, business processing block, or dependency outage.

**Recovery**

11. Fix the root cause first whenever possible.
12. Allow bounded self-recovery for transient glitches.
13. If restarting, target the exact container with cooldown/single-flight.
14. Wait for stop completion before starting again.
15. Never reset offsets or manually commit to skip records.
16. If stop hangs, transaction outcomes are unclear, or external side effects are risky, escalate.

**Verification**

17. Container holds assignments and steady poll rates.
18. Listener success rate rises and group lag drops.
19. Inspect DLT/retry backlogs and transactional commits.
20. Verify duplicate side-effect protection via event IDs/inbox.
21. Record root cause and preventive action items.

## 34. When stopping the container fails to complete

A thread deadlock or infinite blocking call can prevent container stop from finishing. In that situation:

- Never start a new container over the same object before stop completes.
- Never use `Thread.stop()` to force-kill threads.
- Never delete committed offsets or local Kafka files.
- Never call `commitSync()` from an arbitrary thread.
- Capture thread dumps and GC/CPU/network logs.
- Assess whether external side effects may already have committed.
- Escalate to restarting the application instance if runbooks permit.
- With multiple replicas, avoid killing all pods at once.
- After failover, check rebalances, transaction recovery, and idempotency.

`KafkaConsumer.wakeup()` has poll-interruption semantics where supported by the Kafka API, yet Spring Kafka's container owns the consumer lifecycle. Never blindly call wakeup on consumers from off-thread event handlers as a cure-all.

## 35. Common mistakes

**Treating idle as non-responsive.** Empty topics can still poll normally.

**Restarting immediately on the very first event.** Can trigger unnecessary rebalances.

**Only raising `noPollThreshold`.** Hides warnings without curing deadlocks.

**Raising `max.poll.interval.ms` infinitely.** Fails to fix blocking calls and delays failover.

**Using long `Thread.sleep()` inside listeners to shed load.** Delays polls; use container pause where appropriate.

**Calling `KafkaConsumer.commit/seek/pause` on event threads.** Violates threading rules.

**Calling `stop(); start();` back-to-back.** Causes lifecycle races without waiting for stop completion.

**Skipping thread dumps before recovery.** Destroys root-cause evidence.

**Looping restarts infinitely.** Makes incidents worse.

**Manually committing offsets to skip failing records.** Causes business data loss.

**Swallowing listener exceptions.** Allows the container to ack/commit despite failed processing.

**Omitting idempotency.** Restarts/rebalances cause duplicate side effects.

**Ignoring transactional listener semantics.** Can break atomic Kafka offsets/outputs.

**Restarting all pods when only one child consumer is stuck.** Causes needless group churn.

**Failing liveness probes on consumer lag.** Turns backpressure into a crash loop.

## 36. Pre-production checklist

**Detection**

- [ ] `monitorInterval`/`noPollThreshold`/`pollTimeout` settings are clearly understood.
- [ ] `NonResponsiveConsumerEvent` is handled by a lightweight listener.
- [ ] Dashboards separate idle, paused, slow, and stuck states.
- [ ] Poll-rate and listener-processing metrics are instrumented.
- [ ] Alerts include deduplication and SLA-based severity.

**Processing safeguards**

- [ ] HTTP/DB calls enforce finite timeouts.
- [ ] `max.poll.interval.ms` fits listener durations.
- [ ] `max.poll.records`/batch sizes are bounded.
- [ ] Async processing acks only upon completion.
- [ ] Consumer side effects are idempotent.
- [ ] Offset commits never break transaction semantics.

**Recovery**

- [ ] Runbooks cover thread dumps and broker/network diagnostics.
- [ ] Recovery coordinator enforces single-flight, cooldowns, and max attempts.
- [ ] Child listener IDs map accurately to containers.
- [ ] Stop/start waits for lifecycle completion.
- [ ] Manual review exists when stop fails.
- [ ] Post-restart checks verify assignment, polling, lag, and processing.
- [ ] Rollback/reconciliation plans exist for transactions and external side effects.

**Testing**

- [ ] Tests cover `NonResponsiveConsumerEvent` caused by listener blocking.
- [ ] Tests differentiate idle from non-responsive.
- [ ] Tests verify paused containers still poll.
- [ ] Tests cover long batch processing and `max.poll.interval`.
- [ ] Tests verify restarts do not create duplicate side effects.
- [ ] Tests cover broker outages/rebalances and escalation.

## 37. Conclusion

**Actions when a consumer is non-responsive** must begin with **diagnosis**, not restarts. Spring Kafka provides `NonResponsiveConsumerEvent` to warn about poll gaps based on `monitorInterval`, `noPollThreshold`, and `pollTimeout`. However, the same event can stem from slow listener processing, Kafka client/networking, rebalances, JVM GC, or stuck downstream dependencies.

During an incident, separate idle/pause from stalled polling, gather metrics and thread dumps, fix root causes wherever possible, and restart containers only conditionally with clear cooldowns, ownership, and lifecycle sequencing. After any restart, verify partition assignments, consumer lag, committed offsets, retry/DLT flows, and external side effects.

A consumer is truly recovered only when **the poll loop advances steadily, records process accurately, offsets never skip unfinished work, and uncontrolled business duplicates are prevented**.
